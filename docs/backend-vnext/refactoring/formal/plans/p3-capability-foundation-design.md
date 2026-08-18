# Phase 3 Capability Foundation Design

状态：正式设计基线（Accepted）

日期：2026-08-18

阶段：Phase 3 design complete；implementation authorization pending

Owner：Backend vNext Capability Architecture

## 1. Purpose

Phase 3 建立 backend vNext 的 capability foundation，并为后续 Preview vertical slice
提供稳定、可验证、可跨语言实现的数据面合同。本文拥有 Phase 3 的范围、依赖、交付物和
退出标准；字段级语义由各 owning contract 拥有。

Phase 3 不接 HTTP、Workspace、Submit application flow、durable Operation Runtime 或
生产 PostgreSQL。它可以提供 reference planner、Dolt renderer 和 fault-injectable
external executor，供后续阶段验证和接入。

## 2. First consumer and main chain

首个真实 consumer 是 `BuildUploadPreview`。`FULL` 与 `MODIFIED_ONLY` 共用 capability
主链，`INITIALIZE_BASELINE` 延后到 Workspace/Application flow。

```text
table_access/parser
  -> source materialization
  -> SnapshotTableArtifact
  -> storage/comparison projection
  -> comparison
  -> risk
  -> surface
  -> bundle
```

同一 source 只解析和物化一次；多个 pair 共享 immutable `SnapshotTableArtifact`。Preview
同步阶段只计算前端所需 comparison/risk/surface/bundle；cache、replay、mutation planning
和 external ChangeSet 留在后续异步阶段。

## 3. Capability ownership

| Capability | Phase 3 responsibility | Later consumer |
| --- | --- | --- |
| Source/package admission | format, type, size, diagnostics contract | P5A HTTP/Workspace |
| Source materialization | canonical table and derived-table semantics | P5A Preview/Submit |
| Snapshot artifact | immutable rows, summary, retention profile | P4/P5 runtime |
| Storage projection | canonical key/schema/content digest | P5 Submit/Repository |
| Comparison | standard records and surface facts | P5 Preview |
| Risk | declarative ruleset input and actual evaluation | P5 Preview/Review |
| Bundle | closure and references | P5 PreviewResult |
| Mutation planning | rebuild/patch/no-op plan and ChangeSetArtifact | P5 Submit/external sync |

Composite/derived tables are special only during source materialization. After materialization,
`composite_signal_point` and all other canonical tables use the same storage, comparison,
risk, mutation and transaction contracts as ordinary tables.

## 4. Accepted design decisions

- First HTTP package is `TAR_GZ`; internal fixture/staging may use zstd without adding a formal
  `TAR_ZST` package kind.
- Source compressed ingress is `256 MiB`; expanded SourcePackage is initially `1 GiB` and is
  benchmarked before further tightening.
- Repository import upload is `256 MiB`; `manifest.json` is `16 MiB`; `replay.sql` is
  `200 MiB`; exceeding the replay limit is direct rejection, never split or fallback.
- Unknown SQL types and invalid/missing key semantics fail closed at Submit/storage effect;
  Preview may expose bounded table-level degradation.
- Preview may retain summary/lightweight artifacts, but Submit only reuses a complete bound
  artifact; otherwise it materializes from durable source or asks for a new upload.
- Python owns control plane and reference semantics; Rust owns proven data-plane hotspots.
  Provider language and implementation identity do not enter semantic digests.
- `REBUILD_ALWAYS` is the initial production default. `ADAPTIVE_PATCH` may be globally enabled
  after validation; global enable activates planning and does not force every table to patch.
- History compare uses the program's current default ruleset; historical ruleset snapshots are
  provenance only and do not create a mismatch branch.
- The repository/Dolt commit is authoritative. External targets are asynchronous consumers;
  no two-phase commit is introduced.

## 5. Phase 3 deliverables

1. Capability contracts and stable failure taxonomy.
2. Python reference providers and deterministic fixtures.
3. Snapshot/materialization, storage projection, comparison, risk, surface and bundle conformance.
4. `StorageMutationPlan` and `ChangeSetArtifact` contracts plus Python reference planner.
5. Deterministic Dolt renderer and golden replay fixtures.
6. Target-neutral external executor contract and fault-injectable reference executor.
7. Golden, differential, malformed-input, capacity, cancellation and fault-injection tests.
8. Benchmark harness for pair concurrency, memory bounds and provider comparison.

## 6. Explicit phase boundaries

| Item | Owning phase | P3 treatment |
| --- | --- | --- |
| Durable Operation Runtime, drain, checkpoint, takeover | P4 | capability cancellation/checkpoint contract only |
| Workspace, HTTP, PreviewResult, artifact retention wiring | P5A | no application integration |
| Submit/finalize, Dolt effect and external ChangeSet wiring | P5B | renderer/reference executor only |
| Rust coverage expansion and risk kernels | P6 | profile and provider boundary only |
| global concurrency/cache tuning | P7 | benchmark inputs and resource contract only |
| shadow traffic/cutover | P8 | deferred |
| cleanup/production hardening | P9 | deferred |
| production PostgreSQL adapter/e2e | future target-specific work | contract and reference executor only |
| online ruleset watcher/hot activation | future optional work | immutable snapshot/activation boundary only |
| `STORAGE_BREAKING` ruleset migration executor | future migration work | impact classification and gating only |

## 7. Phase 3 exit criteria

Phase 3 may be declared complete only when:

- contracts have one owner and no unresolved architecture blocker;
- outputs are deterministic across provider language, thread count and input ordering;
- Python reference and production candidate pass golden/differential fixtures;
- incomplete artifacts cannot be published or used as cache hits;
- cancellation, timeout, panic/OOM mapping and retry semantics are bounded and stable;
- `ADAPTIVE_PATCH` mixed plans, key changes, guards and renderer capability failures are tested;
- reference external executor covers transaction, idempotency, drift, readback and unknown outcome;
- concurrency benchmark records wall time, CPU, RSS, queue wait and cancellation latency;
- HTTP/application integration remains outside the P3 implementation diff.

## 8. Non-goals and reopen conditions

No formal compatibility matrix, live ruleset watcher, automatic Python runtime fallback,
compute network service, production PostgreSQL adapter, 2PC, arbitrary SQL stringify fallback,
or full migration executor is introduced in Phase 3. A future design must reopen the owning
contract/ADR before changing these boundaries.

## 9. Normative owners

- [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)
- [Storage Mutation and Change Set](../contracts/storage-mutation-and-change-set.md)
- [External Target Sync and Recovery](../contracts/external-target-sync-and-recovery.md)
- [Operation Lifecycle and Integrity Incident](../contracts/operation-lifecycle-and-integrity.md)
- [Ruleset Activation and Migration](../contracts/ruleset-activation-and-migration.md)
- [Implementation Stages](implementation-stages.md)

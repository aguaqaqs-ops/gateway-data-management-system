# P3-R5 Comparison Handoff

状态：`pass`（R5 module gate；R6 entry。不是 Phase 3 全部实现授权，不含 risk/surface/bundle
production integration）

日期：2026-08-21

Owner：Backend vNext Comparison Capability

本文是 P3-R6 的默认 R5 入口。它记录 R5 module gate 的 source candidate、验证证据、稳定
`ComparisonFacts` / records / neutral-cache boundary、限制和 R6 prerequisites。Risk、surface、
bundle、HTTP、Workspace、Submit、Repository/Dolt 和 Operation Runtime production integration
仍不属于 R5；不得从本 handoff 推断已获授权。过程证据见 R5 execution plan 的 S0、S5、S6
和 S7 记录。

设计基线：[P3-R5 Comparison Design Baseline](p3-r5-comparison-design.md)
过程证据：R5 执行计划与 S0 freeze 已归档；恢复见 tag `docs/p3-p4-cleanup-pre-20260823` 与
[p3-p4-cleanup-manifest.yaml](p3-p4-cleanup-manifest.yaml)。
上游 handoff：[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)

```yaml
handoff_kind: p3_r5_comparison
round: P3-R5-S8
s6_review: pass
s7_review: pass
p3_r5_exit: pass
p3_r6_ready: yes
p3_implementation_authorized: no
worktree_at_validated_tip: clean_committed_on_7cb90e6
validated_code_sha: 7cb90e6f3e3707de856da0aabb43f7d519b9f1f3
s0_entry_sha: ca22491e02464970627a8b43e7e16e1404acedb6
s1_code_sha: 2963963c9cb707c9584aac8778eb07e8d6d40782
s7_reviewed_tip: 7cb90e6f3e3707de856da0aabb43f7d519b9f1f3
s8_tests_rerun: yes
container_rebuild: required_deferred
benchmark: measurement_only_no_gate
r6_entry_sha: 500ca11
handoff_documentation_sha: 500ca11
```

`validated_code_sha` 是 S7 findings remediation 封存后、S8 复跑通过的 source SHA，不是本
handoff 文档的 commit SHA。`r6_entry_sha` / `handoff_documentation_sha` 已封存为本 handoff
documentation commit `500ca11`，不在本文件中自引用。`p3_r5_exit: pass` 表示
R5 source/module gate 的 staged implementation surface 通过；Rust/Cargo 触发的 backend
image/container gate 仍是必须执行的 deferred gate，不被该 pass 隐式关闭。

## 1. Gate identity

```yaml
branch: phase1/gate-ownership-repair
s0_record: sealed_in_this_handoff; archived_basename p3-r5-s0-entry-and-budget-freeze.md
s6_review_record: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r5-comparison-execution-plan.md
s7_review_record: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r5-comparison-execution-plan.md
s8_record: p3-r5-comparison-handoff.md
container_rebuild_reason: R5 adds Rust Parquet records reader and Cargo lock/dependency changes copied and built by vnext/backend/Dockerfile
last_validated_image_revision: none
container_validation_deferred_to: Docker daemon availability and the P3 final candidate gate
benchmark_reason: R5 freezes measurement-only profiles but has no independent benchmark runner in this candidate
```

```text
Current sealed source candidate: 7cb90e6f3e3707de856da0aabb43f7d519b9f1f3
Worktree at S8 rerun: clean
Container rebuild required: yes
Container result: deferred; `docker info` cannot connect to /var/run/docker.sock
Last verified image revision: none
Container gate for current source: not passed; mandatory deferred gate
Deferred gate owner/action: backend image owner must rebuild vnext/backend/Dockerfile from this source and rerun the relevant container gates when Docker is available
```

## 2. Commit lineage

核对命令：

```bash
git log --reverse --format='%H %s' \
  4effb6eefa16d246e75213212f884b2546e6d6ef..7cb90e6f3e3707de856da0aabb43f7d519b9f1f3
```

```yaml
commit_lineage_count: 5
commit_lineage:
  r4_handoff_to_r5:
    stage_entry_tip: ca22491e02464970627a8b43e7e16e1404acedb6
    subject: "docs(p3-r5): accept comparison design, execution plan and S0 freeze"
    stage_exit: pass
  s1:
    stage_final_reviewed_tip: 2963963c9cb707c9584aac8778eb07e8d6d40782
    subject: "feat(p3-r5-s1): add Arrow batch boundary and comparison provider port"
    stage_exit: pass
  s1_documentation:
    reviewed_tip: d61199f3b4a3425272b7b152da3dd16142542770
    subject: "docs(p3-r5-s1): seal S1 verification SHA and rerun evidence"
    stage_exit: pass
  s2_s7:
    stage_final_reviewed_tip: b39ebe3126e935cf027d4f7256dc4fafb74d1035
    subject: "feat(p3-r5): complete comparison core and cache"
    stage_exit: pass_with_s7_findings
  s7_remediation_and_s8_candidate:
    reviewed_tip: 7cb90e6f3e3707de856da0aabb43f7d519b9f1f3
    subject: "fix(p3-r5): enforce table record budgets in closure"
    stage_exit: pass
    note: S7-001 and S7-002 were remediated in the artifact owner and the S8 candidate was rerun
  s8:
    reviewed_tip: 7cb90e6f3e3707de856da0aabb43f7d519b9f1f3
    stage_exit: pass
    note: this handoff documentation follows the sealed source candidate and is not this SHA
```

## 3. Changed paths

R5 implementation, test and vector surface sealed in `4effb6e..7cb90e6`:

```text
vnext/backend/src/gateway_backend/cache/__init__.py
vnext/backend/src/gateway_backend/cache/comparison_core.py
vnext/backend/src/gateway_backend/capabilities/comparison/
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/  # additive public batch/provenance changes only
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_comparison_artifacts.py
vnext/backend/tests/test_comparison_batch_boundary.py
vnext/backend/tests/test_comparison_blank.py
vnext/backend/tests/test_comparison_cache.py
vnext/backend/tests/test_comparison_ordered.py
vnext/backend/tests/test_comparison_planning.py
vnext/backend/tests/test_comparison_records.py
vnext/backend/tests/test_comparison_standard.py
vnext/backend/tests/test_snapshot_artifact_roundtrip.py
vnext/fixtures/vectors/comparison/records/blank-v1.parquet.b64
vnext/fixtures/vectors/comparison/records/ordered-v1.parquet.b64
vnext/fixtures/vectors/comparison/records/standard-v1.parquet.b64
vnext/rust/Cargo.toml
vnext/rust/Cargo.lock
vnext/rust/gateway-compute-core/Cargo.toml
vnext/rust/gateway-compute-core/src/lib.rs
vnext/rust/gateway-compute-core/src/records.rs
```

R5 formal/design and entry-coordination documentation in the same lineage includes the R5 design,
discussion summary, execution plan, S0 freeze, project-identity boundary, formal README/active
context index and the R4-to-R5 entry corrections. This handoff is the S8 documentation addition.

No HTTP route, Workspace/Submit business state, Repository Service/Dolt adapter, Operation Runtime,
risk provider, surface/bundle production integration, legacy production import, new service/helper or
new security principal was introduced.

## 4. Commands and results

S8 confirmatory rerun was executed against the clean source candidate
`7cb90e6f3e3707de856da0aabb43f7d519b9f1f3` on 2026-08-21. Python commands used
`UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline` because the default uv cache is not the
authoritative writable cache in this environment.

| Command | Result |
| --- | --- |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit tests/test_comparison_cache.py tests/test_comparison_artifacts.py tests/test_comparison_records.py tests/test_comparison_standard.py tests/test_comparison_ordered.py tests/test_comparison_blank.py tests/test_comparison_planning.py tests/test_comparison_batch_boundary.py tests/test_snapshot_artifact_roundtrip.py tests/test_architecture.py` | **112 passed** in 4.46s |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit` | **640 passed, 58 pre-existing legacy-oracle failures, 1 warning** in 7.41s; failures are confined to `tests/test_table_rules_resolver.py` loading absent/incompatible `legacy/backend_vnext` paths/symbols and are not R5 regressions |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit --ignore tests/test_table_rules_resolver.py` | **564 passed, 1 warning** in 3.39s |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check .` | **passed** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline mypy` | **passed**; 155 source files |
| `cd vnext/rust && cargo fmt --all -- --check` | **passed** |
| `cd vnext/rust && cargo clippy -p gateway-compute-core --all-targets -- -D warnings` | **passed** |
| `cd vnext/rust && cargo test -p gateway-compute-core` | **82 passed, 0 failed** |
| `cd vnext/rust && cargo test -p gateway-compute-python` | **3 passed, 0 failed** |
| Python/Rust Parquet record vectors | STANDARD `sha256:22bfb26abb0aaeb3d279cdae0614d2733bebbd8cdf8021cfa6751c690db561d4`; ORDERED `sha256:887e686f96583a28c31f82788608ebd10491b80eb98dc9ab2ada7389ec50468b`; BLANK `sha256:5f7d095129a4fdbeba84392206fa857740ecdca6b466f9cc8177d2264bf9c17a`; all equal |
| `docker info` | **deferred/exit 1**; Docker client exists but daemon is unavailable at `/var/run/docker.sock` |
| `git diff --check` at source candidate | **passed**; clean worktree before this documentation change |

The focused suite covers pair applicability/identity continuation, standard keyed/keyless/schema
semantics, ordered/blank records, typed values, records publication/readback/tamper/budget/cancel
paths, neutral cache restore/rebinding and architecture imports. Rust record tests read the Python
Parquet vectors and recompute the same logical content digests. The enabled Rust surface is the
language-neutral records reader and coarse Arrow provider boundary; no semantic Rust comparison
provider is enabled, so no production-scale native differential claim is made.

No command used Dolt, Repository Service, HTTP application flow, Workspace, Submit, Operation Runtime
or an external parser process. No R5 comparison test uses `integration` or fixed-timeout `serial`
behavior; no separate `serial -n 0` run is required.

### 4.1 Benchmark disposition

S0 defines deterministic `comparison_tiny` through `comparison_large` measurement profiles, but this
candidate contains no independent benchmark runner or accepted workload generator. Accordingly the
measurement fields are not applicable for this gate: no duration/CPU/RSS/spill/artifact-byte/record-
count/cancellation-latency number is presented as a result. Benchmark remains measurement-only and
has no fixed performance threshold or authorization effect.

## 5. Findings closure and deferred register

| ID | Status |
| --- | --- |
| `S7-001` | **Closed**; closure/artifact reopen checks Parquet footer, manifest and entry counts against `max_records_per_table` before row materialization; regression test passes |
| `S7-002` | **Closed**; publication and reopen aggregate standard/ordered/blank family counts by table before accepting the closure; regression tests pass |
| S7 other findings | **None**; no P1/P2, contract ambiguity, digest mismatch, hidden dependency, forbidden import, partial-publication or marker finding remains open |
| `R5-D01` | **Deferred**; semantic Rust comparison provider and production-scale differential execution; existing coarse Arrow/Parquet boundary and records-reader vectors pass |
| `R5-D02` | **Required/deferred**; backend image rebuild and container gate for Rust/Cargo changes; Docker daemon unavailable, so no image revision or container pass is claimed |
| `R5-D03` | **Deferred**; independent benchmark runner and numeric measurement output; S0 measurement-only policy remains unchanged |
| `R5-D04` | **Deferred**; static risk rules/aggregation, surface/bundle integration, table-level cache promotion/eviction, independent compute worker/service and provider-specific raw cache |
| `R5-D05` | **Deferred**; unreferenced artifact reclamation remains lifecycle work under ADR 0012; publication is fail-closed and never returns an orphan ref |
| `R5-D06` | **Known external fixture gap**; `legacy/backend_vnext` oracle used by 58 existing table-rules tests is absent/incompatible in this checkout; excluded from R5 ownership and does not fail the R5 focused gate |

**R5 source/module gate decision: PASS.** The deferred container gate is explicitly carried forward and
must be closed before an image/release/final production candidate is claimed. No R5 owning contract or
ADR was reopened; frozen budgets and the global `p3_implementation_authorized: no` decision are
unchanged.

## 6. Stable public boundary and downstream seams

R6 may consume only these immutable/public surfaces:

```text
snapshot_materialization
  SnapshotTableArtifact / SnapshotTable / SnapshotTableReader
  SnapshotTableBatchReader / SnapshotTableBatchMetadata
  SnapshotTable.batch_reader

comparison
  PairExecutionInput / PairExecutionResult
  bind_pair_input / plan_pair
  ComparisonFacts / ComparisonTableFact / ComparisonSummary
  ComparisonRecordsClosure / RecordsArtifactManifest / RecordsClosureEntry
  publish_records_closure / open_records_closure / restore_records_closure
  PythonReferenceBatchProvider / RustArrowBatchProvider
  COMPARISON_CONTRACT_VERSION = backend-vnext/comparison/v2
  RECORDS_ARTIFACT_CONTRACT_VERSION = backend-vnext/comparison-records/v1
  RECORDS_CLOSURE_CONTRACT_VERSION = backend-vnext/comparison-records-closure/v1
  STANDARD_RECORDS_SCHEMA_VERSION = standard-records/v1
  ORDERED_RECORDS_SCHEMA_VERSION = ordered-records/v1
  BLANK_RECORDS_SCHEMA_VERSION = blank-records/v1

cache
  ComparisonCoreCache / ComparisonCoreCacheKey / ComparisonCoreCacheValue
  COMPARISON_CORE_CACHE_CONTRACT_VERSION = backend-vnext/comparison-core-cache/v1
```

`ComparisonFacts` is the semantic authority for facts/counts/digests. `ComparisonRecordsClosure` is
the immutable typed Parquet closure; operation-local refs may be rewritten on restore without changing
semantic content digests. `INITIAL_SNAPSHOT`, `DATASET_REPLACEMENT`, `IDENTITY_GATE_BLOCKED`,
`CANCELLED` and `FAILED` do not gain detailed records through cache or publication shortcuts.

R6 downstream seam status:

- risk comparison may consume `ComparisonFacts` and the records closure through public contracts;
- static risk consumes immutable snapshot artifacts independently and does not mutate `ComparisonFacts`;
- surface/bundle receives future risk/comparison contracts and is not activated by R5;
- R5 provides no HTTP, Workspace, Submit, Repository/Dolt, Operation Runtime or business-state adapter.

The comparison capability must not import R4 private modules, snapshot Parquet internals, `legacy`,
`gateway_repository_service`, `dolt`, HTTP/application modules, host-path helpers or test support.

## 7. R6 entry prerequisites

R6 may create its own detailed plan and obtain a separate implementation authorization after accepting:

- immutable `ComparisonFacts` plus optional `ComparisonRecordsClosure`, with `records_ref` treated as
  an opaque operation-local artifact ref;
- contract/version and digest layering, including the no-cycle manifest/closure rule;
- `PairExecutionResult` applicability, replacement, identity-gate, cancellation and failure semantics;
- R5 table/pair/records/spill/cancellation budgets and fail-closed publication behavior;
- neutral cache restore rebinding: identity, continuation policy, assessment and operation-local closure
  are fresh bindings, never cache authority;
- the deferred register above, especially the mandatory backend image/container gate and the absence
  of a semantic Rust provider.

R5 does not authorize R6 production integration, risk rules, surface/bundle assembly, HTTP flow or
Repository/Operation Runtime effects.

## 8. Non-goals and authorization

R5 handoff does not authorize:

- changing `p3_implementation_authorized` to `yes`;
- semantic Rust fallback or automatic provider substitution after a selected provider failure;
- risk/static-risk rules, annotation persistence, surface/bundle production integration;
- comparison/table cache retention, eviction, quota or distributed ownership;
- Repository Service/Dolt reads/writes, HTTP, Workspace, Submit, Archive or Operation Runtime state;
- a new helper/service/security principal, public JSONL artifact, host-path identity or private-module
  dependency.

```yaml
p3_r5_exit: pass
p3_r6_ready: yes
p3_implementation_authorized: no
```

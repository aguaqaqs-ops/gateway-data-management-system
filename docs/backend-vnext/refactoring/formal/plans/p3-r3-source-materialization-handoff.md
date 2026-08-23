# P3-R3 Source Materialization and Snapshot Handoff

状态：`pass`（R3 module gate；R4 entry。不是 Phase 3 全部实现授权，不含 storage projection）

日期：2026-08-19

Owner：Backend vNext Source Materialization

本文是 P3-R4 的**默认 R3 入口**。它记录 R3 gate 身份、稳定 public Snapshot/Artifact
boundary、测试证据、限制和 R4 prerequisites。canonical storage key/schema、
`CanonicalizationManifest` 和 RepositoryImportArtifact 仍由 R4 owner 拥有；不得从
R3 私有 digest/Parquet 模块猜测。过程证据见 S0 freeze、S6/S7 reviews 和 R3 执行计划。

上级计划：[P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)
过程证据：R3 执行计划、S0 freeze 与 S6/S7 review 已归档；恢复见 tag
`docs/p3-p4-cleanup-pre-20260823` 与 [p3-p4-cleanup-manifest.yaml](p3-p4-cleanup-manifest.yaml)。
设计基线：[P3 Capability Foundation Design §4.2](p3-capability-foundation-design.md#42-p3-r3-source-materialization-and-snapshot-design-baseline)

```yaml
handoff_kind: p3_r3_source_materialization
round: P3-R3-S8
s6_review: pass
s7_review: pass
p3_r3_exit: pass
p3_r4_ready: yes
p3_implementation_authorized: no
worktree_at_validated_tip: clean_after_implementation_commit
validated_code_sha: 7989e47d08c48fda46e7d8b6b3550ef9ee266d92
s0_entry_sha: 3c142f8e7616fb4cc2594a61128b2ccce494dd46
container_rebuild: no
benchmark: not_applicable
```

`validated_code_sha` 是 S6/S7 已审且本 S8 复跑通过的代码 SHA，不是本 handoff
文档 commit SHA。S8 开始时工作树含未提交的 R3 实现与 S0–S7 记录；它们已收进
`validated_code_sha`。文档提交完成后成为 `r4_entry_sha` /
`handoff_documentation_sha`，不在本文件中自引用。

## 1. Gate identity

```yaml
branch: phase1/gate-ownership-repair
s6_reviewed_tip: 7989e47d08c48fda46e7d8b6b3550ef9ee266d92
s6_review_record: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r3-s6-focused-review.md
s7_review_record: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r3-s7-independent-review.md
s0_record: sealed_in_this_handoff; archived_basename p3-r3-s0-entry-and-budget-freeze.md
s8_tests_rerun: yes
container_rebuild_reason: R3 candidate is pure Python capability/test/docs and does not touch image, deployment, or container-only runtime boundaries
last_validated_image_revision: none; source-tree validation is the authoritative evidence
container_validation_deferred_to: a later R if an image/deployment/container boundary is introduced, or the P3 final candidate
benchmark_reason: S0/S1 did not add an independent benchmark runner; no numeric performance claim
```

```text
Current HEAD at S8 rerun: worktree that became 7989e47d08c48fda46e7d8b6b3550ef9ee266d92
Container rebuild required: no
Reason: no Dockerfile, lock, entrypoint, Compose, UID/GID, volume, or container-only runtime change
Last verified image revision: none
Last verified source-tree/image id: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: none
Required execution point: later R if an image/deployment/container boundary is introduced, or P3 final candidate
```

## 2. Commit lineage

核对命令：

```bash
git log --reverse --format='%H %s' \
  3c142f8e7616fb4cc2594a61128b2ccce494dd46..7989e47d08c48fda46e7d8b6b3550ef9ee266d92
```

```yaml
commit_lineage_count: 1
commit_lineage:
  s0_s7:
    stage_final_reviewed_tip: 7989e47d08c48fda46e7d8b6b3550ef9ee266d92
    subject: "feat(backend): add P3-R3 source materialization and snapshot artifacts"
    stage_exit: pass
    note: S0–S7 were executed and reviewed in-tree before this single implementation commit; S6/S7 records are separate files
  s8:
    reviewed_tip: 7989e47d08c48fda46e7d8b6b3550ef9ee266d92
    stage_exit: pass
    note: S8 independently retested this tip; the S8 handoff documentation commit follows and is not this SHA
```

## 3. Changed paths

Cumulative implementation/test/docs surface in `3c142f8e..7989e47`, plus this S8
handoff documentation commit:

```text
vnext/backend/src/gateway_backend/capabilities/source_package_staging/
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/
vnext/backend/src/gateway_backend/capabilities/composite_signal/
vnext/backend/src/gateway_backend/capabilities/table_rules/
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_source_package_*.py
vnext/backend/tests/test_snapshot_materialization_*.py
vnext/backend/tests/test_composite_signal_*.py
vnext/backend/tests/test_repository_ref_materialization_*.py
vnext/backend/tests/test_snapshot_artifact_*.py
vnext/backend/tests/test_table_rules_contracts.py
vnext/backend/tests/support/source_package_fixtures.py
vnext/backend/tests/support/snapshot_materialization.py
vnext/backend/tests/support/snapshot_artifact.py
vnext/backend/tests/support/repository_ref_materialization.py
vnext/backend/tests/support/composite_signal.py
vnext/fixtures/golden/snapshot-materialization/
vnext/fixtures/golden/composite-signal/
docs/backend-vnext/refactoring/formal/plans/p4-active-context-index.md
# archived process records: p3-r3-source-materialization-execution-plan.md, p3-r3-s0-entry-and-budget-freeze.md,
#   p3-r3-s6-focused-review.md, p3-r3-s7-independent-review.md (tag docs/p3-p4-cleanup-pre-20260823)
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

S1 已登记 `tests/test_architecture.py` 与 `table_rules` 注入面。S7 新增登记
independent-review 记录。S8 新增登记本 handoff。S0 冻结的
`vnext/fixtures/vectors/snapshot-materialization/` 与
`vnext/fixtures/vectors/composite-signal/` 根目录本轮未落地文件。

No HTTP, Workspace, Submit, Operation Runtime, storage/comparison projection,
production Repository Service/Dolt adapter, production retention, formal
`TAR_ZST` package admission, or new security principal was introduced.

## 4. Commands and results

S8 confirmatory rerun against the worktree that became `validated_code_sha`
`7989e47`（2026-08-19）。pytest/ruff/mypy 使用 `UV_CACHE_DIR=/tmp/gateway-data-uv-cache`
与 `uv run --offline`，因为默认 `/root/.cache/uv` 在本环境只读。

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run --offline pytest -m unit` | **372 passed**（1.40s）；1 pre-existing Starlette deprecation warning |
| `cd vnext/backend && uv run --offline pytest -m unit --deselect tests/test_app.py::test_healthz_uses_injected_settings` | **371 passed**, 1 deselected（1.35s） |
| `cd vnext/backend && uv run --offline ruff check . && uv run --offline mypy` | **passed**；mypy 121 source files |
| `git diff --check` | **passed** |

S7 recorded `S7-V01`：full unit 中的
`tests/test_app.py::test_healthz_uses_injected_settings` 在当时环境挂起。S8 对该
nodeid 做了 20 秒超时探测（**1 passed**，0.38s），随后完整 `pytest -m unit`
在 1.40s 内结束。S8 以 372 passed 为权威门禁证据；不把 S7 的环境限制表述为本轮
full-suite 失败。

No command used Dolt, Repository Service, HTTP application flow, Workspace,
Submit, an operation runtime, or an external parser process. No
`@pytest.mark.serial` or `@pytest.mark.integration` test was added, so no
`uv run pytest -m serial -n 0` or Dolt integration nodeid run was required.
Timeout/cancel tests use already-expired `deadline_monotonic` or cooperative
probes, not a sleep/join budget.

## 5. Findings closure and deferred register

| ID | Status |
| --- | --- |
| `S6-001` | Closed; ZIP/TAR documents read with incremental document budget; unit rerun passes |
| `S6-002` | Closed; artifact-store verification maps to result-level `FAILED` with no public refs; unit rerun passes |
| `S6-003` | Closed; SourcePackage staging checkpoints cancel/deadline at entry and each artifact-write boundary; unit rerun passes |
| `S6-004` | Deferred as `R3-D03`; fail-closed publication verified; durable orphan cleanup remains ADR 0012 lifecycle work |
| S7 implementation findings | None; S6 closures remain covered |
| `S7-V01` | Did not reproduce in S8; full unit is 372 passed. Historical S7 verification-environment note only; not an R3 finding |
| `R3-D01` | Deferred；formal `TAR_ZST` SourcePackage admission |
| `R3-D02` | Deferred；Repository Service/Dolt production adapter and hidden-summary write |
| `R3-D03` | Deferred；retention, pinning, eviction, quota and durable artifact lifecycle |
| `R3-D04` | Deferred to R4；storage projection, canonical storage key/schema, CanonicalizationManifest |
| `R3-D05` | Deferred；projection cache and export-format matrix |
| `R3-D06` | Deferred to P6+；Rust materializer/provider and automatic fallback |
| `R3-D07` | Deferred to P4；durable cancellation/checkpoint/takeover |
| `R2-D04` | Closed in R3-S3；`composite_signal` business materializer |
| `R2-D05` | Protocol + fake provider closed in R3-S4；real Dolt remains `R3-D02` |
| `R2-D06` | R3 owns Snapshot/raw/business digest；storage projection remains `R3-D04` / R4 |

**No-open-blocker.** 无未处理 P1/P2 finding、contract ambiguity、import cycle、
unbounded path 或 hidden Repository/application dependency。S8 未 reopen ADR 或
owning contract；S0 numeric budgets 未修订。

权威延后表：本 handoff §5 deferred register 与
[P3 design §4.2](p3-capability-foundation-design.md#42-p3-r3-source-materialization-and-snapshot-design-baseline)。

## 6. Contract, ADR and fixture references

```text
# archived: p3-r3-s0-entry-and-budget-freeze.md (tag docs/p3-p4-cleanup-pre-20260823)
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md
docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md
docs/backend-vnext/refactoring/formal/contracts/fixture-oracle-and-conformance.md
docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md
docs/backend-vnext/refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md
docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md
docs/backend-vnext/contracts/source-package.md
docs/backend-vnext/contracts/snapshot.md
docs/backend-vnext/contracts/snapshot-table-access.md
docs/backend-vnext/artifacts.md
vnext/fixtures/golden/snapshot-materialization/package/valid/
vnext/fixtures/golden/snapshot-materialization/sql/valid/
vnext/fixtures/golden/snapshot-materialization/sql/partial/
vnext/fixtures/golden/snapshot-materialization/sql/malformed/
vnext/fixtures/golden/snapshot-materialization/business/valid/
vnext/fixtures/golden/snapshot-materialization/business/partial/
vnext/fixtures/golden/composite-signal/xml/valid/
vnext/fixtures/golden/composite-signal/xml/malformed/
```

S0 resource budgets remain the authority and were not revised in S8. Fixture
naming and parameter-table ownership remain `source_package_staging`、
`snapshot_materialization` 与 `composite_signal`。

## 7. Stable public boundary

R4 可消费下列 public surface 与各 owner 的 `contracts.py`。不得 import
`_digest`、`_parquet`、`_reader`、`_catalog`、`_ruleset`、`_archive`、`_paths`、
`_ast`、`_bind`，也不得依赖 `tests/support` fake provider 或 Parquet 内部 API。

Public entrypoints and result types：

```text
source_package_staging
  stage_source_package(SourcePackageInput) -> SourcePackageStagingResult
  resolve_sql_dump_source(...)
  RESOURCE_BUDGETS / StagingStatus / PackageKind / SourceDocumentRef

snapshot_materialization
  materialize_sql_snapshot(SqlSnapshotMaterializationRequest) -> SnapshotMaterializationResult
  materialize_business_snapshot(BusinessSnapshotMaterializationRequest) -> SnapshotMaterializationResult
  materialize_repository_ref(RepositoryRefMaterializationRequest) -> SnapshotMaterializationResult
  publish_snapshot_table_artifact / open_snapshot_table_artifact / validate_snapshot_table_artifact
  SnapshotTableArtifactCache
  Snapshot / SnapshotSummary / SnapshotTableSet / SnapshotTable / SnapshotTableArtifact
  SnapshotMaterializationStatus: COMPLETE | PARTIAL | FAILED
  MaterializationStage: PROVISIONAL | FINAL
  CacheTrustLevel: PROVISIONAL | CONTENT_VERIFIED | COMMIT_VALIDATED
  SnapshotTableReader (contracts.py Protocol; not re-exported in __all__)
  RepositoryTableAccessProvider / RepositoryRefSession / RepositoryTableReader
    (contracts.py Protocols; not re-exported in __all__)

composite_signal
  materialize_composite_signal(CompositeSignalRequest) -> CompositeSignalResult
  empty_composite_logic_source / present_composite_logic_source

table_rules
  TableRulesetSnapshot / TABLE_RULESET_VERSION / TableCompareKey

artifacts
  four-field ArtifactRef; no host path
```

`SnapshotTable[].reader` 在 READY 表上发布 `SnapshotTableReader`。R4 应对该协议
编程，不构造 `BoundSnapshotTableReader` 或读取 Parquet schema。Artifact consumer
只用 reader 与 opaque `ArtifactRef`。

Capability DAG 不变：

```text
source_package_staging          leaf
table_access                    leaf
table_rules                     leaf
composite_signal             -> table_access
snapshot_materialization     -> table_access, table_rules, source_package_staging, composite_signal
storage_projection           -> table_rules, snapshot_materialization   # registered, not implemented in R3
```

Architecture tests 覆盖 forbidden tokens（`dolt`、`gateway_repository`、
`host_path`、HTTP/application、SQL execution、external XML resolver）。

## 8. Known limitations and deferred items

- 正式 SourcePackage 仅 `TAR_GZ`；`ZIP`/`DIRECTORY` 为 capability/local fixture；
  `SQL_FILE`/`SQL_GZ` 为 test/benchmark；zstd 只作内部 staging/fixture transport
  （`R3-D01`）。
- RepositoryRef 使用 protocol-conformant in-memory fake；真实 Repository
  Service/Dolt adapter 与 hidden FINAL summary **写入** 是 `R3-D02`。
- R3 不实现 retention/eviction/quota 或 durable artifact lifecycle（`R3-D03` /
  ADR 0012）。失败后不可达的 L3 object 不通过 public ref 暴露。
- R3 拥有 materialization/`fast_row`/`raw_content`/`business_content`/
  `snapshot_digest`；storage projection、canonical storage key/schema 与
  `CanonicalizationManifest` 是 `R3-D04`。
- projection cache 与 export-format matrix 是 `R3-D05`。
- 无 Rust materializer 或 automatic fallback（`R3-D06`）。
- in-process cancel/deadline only；durable cancellation/checkpoint/takeover 是
  `R3-D07`。
- 无独立 materializer benchmark runner；不得从本 handoff 读取 numeric
  performance claim。
- `COMMIT_VALIDATED` 不能由 `materialize_*` 自提升；必须有匹配的
  `CacheAuthorityInput`。

## 9. R4 entry prerequisites

R4 仍须先写详细计划再实现。R4 entry 必须拿到并保持：

- stable public Snapshot / SnapshotSummary / SnapshotTableSet /
  `SnapshotTableArtifact`（manifest + Parquet rows）与 opaque `ArtifactRef`（§7）；
- `COMPLETE | PARTIAL | FAILED` 与 staging write → manifest/descriptor/digest
  validation → atomic publish；失败表无 partial reader 或 artifact；
- raw/business/`snapshot_digest` 由 R3 拥有；R4 **不得复制** materialization
  digest 逻辑，只做 storage key/schema、`CanonicalizationManifest` 与
  RepositoryImportArtifact；
- cache miss 必须能从 source package 或 pinned RepositoryRef 重建；
- `COMMIT_VALIDATED` 不可自提升；
- no Repository/HTTP/application implementation dependency in R3 capabilities；
- `R3-D01`–`R3-D07` explicitly linked（§5）；
- R4 只消费 §7 public surface 与 `contracts.py`，不 import R3 private modules。

本 handoff 不授权 storage projection、canonical storage key/schema、
comparison projection 或其他 P3 capability 算法。

## 10. Non-goals and authorization

R3 未做、R4 不得从本文推断为已授权：

- storage projection、canonical storage key/schema、`CanonicalizationManifest`、
  RepositoryImportArtifact（`R3-D04`）；
- projection cache 与 export-format matrix（`R3-D05`）；
- 真实 Repository Service/Dolt production adapter（`R3-D02`）；
- HTTP、Workspace、Submit、PreviewResult、Operation Runtime；
- production retention/cleanup、新的安全主体、container/image validation；
- formal `TAR_ZST` SourcePackage admission（`R3-D01`）；
- Rust materializer 或 automatic fallback（`R3-D06`）。

```yaml
p3_r3_exit: pass
p3_r4_ready: yes
p3_implementation_authorized: no
```

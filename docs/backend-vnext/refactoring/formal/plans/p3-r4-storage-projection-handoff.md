# P3-R4 Storage Projection and Canonicalization Handoff

状态：`pass`（R4 module gate；R5 entry。不是 Phase 3 全部实现授权，不含 comparison projection）

日期：2026-08-20

Owner：Backend vNext Table Rules / Storage Projection

本文是 P3-R5 的**默认 R4 入口**。它记录 R4 gate 身份、稳定 public projection/artifact
boundary、测试证据、限制和 R5 prerequisites。comparison records、`FULL`/`MODIFIED_ONLY`
和 display/risk semantics 仍由 R5/R6 owner 拥有；不得从 R4 私有 digest/ordered/view
模块或 `LegacyRuleDecision` 推断 storage drop。过程证据见 S0 freeze、S6/S7 reviews
和 R4 执行计划。

上级计划：[P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)
过程证据：R4 执行计划、S0 freeze 与 S6/S7 review 已归档；恢复见 tag
`docs/p3-p4-cleanup-pre-20260823` 与 [p3-p4-cleanup-manifest.yaml](p3-p4-cleanup-manifest.yaml)。
设计基线：[P3-R4 Storage Projection Design Baseline](p3-r4-storage-projection-design.md)
R3 入口：[P3-R3 Source Materialization and Snapshot Handoff](p3-r3-source-materialization-handoff.md)

```yaml
handoff_kind: p3_r4_storage_projection
round: P3-R4-S8
s6_review: pass
s7_review: pass
p3_r4_exit: pass
p3_r5_ready: yes
p3_implementation_authorized: no
worktree_at_validated_tip: clean_committed_on_4effb6e
validated_code_sha: 4effb6eefa16d246e75213212f884b2546e6d6ef
r3_handoff_documentation_sha: f07c387f513ee735fe69e65c94804d7c63115f0d
s8_source_tip: 4effb6eefa16d246e75213212f884b2546e6d6ef
container_rebuild: no
benchmark: not_applicable
r5_entry_sha: pending_handoff_documentation_commit
handoff_documentation_sha: pending_handoff_documentation_commit
```

`validated_code_sha` 现已封存为 `4effb6e`：该提交包含此前 S6/S7 审查过的 R4 实现、
测试、审查记录和原始 handoff。当前文件的证据修正尚未提交，因此
`r5_entry_sha` / `handoff_documentation_sha` 在本次文档修正提交完成后再回填；
`validated_code_sha` 只有在 R4 代码改变时才需要变化。

## 1. Gate identity

```yaml
branch: phase1/gate-ownership-repair
s6_reviewed_tip: 4effb6eefa16d246e75213212f884b2546e6d6ef (sealed reviewed implementation)
s6_review_record: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r4-s6-focused-review.md
s7_review_record: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r4-s7-independent-review.md
s0_record: sealed_in_this_handoff; archived_basename p3-r4-s0-entry-and-budget-freeze.md
s8_tests_rerun: historical_yes_current_focused_yes_full_unit_incomplete
container_rebuild_reason: R4 candidate is pure Python capability/test/docs and does not touch image, deployment, or container-only runtime boundaries
last_validated_image_revision: none; source-tree validation is the authoritative evidence
container_validation_deferred_to: a later R if an image/deployment/container boundary is introduced, or the P3 final candidate
benchmark_reason: S0/S1 did not add an independent benchmark runner; no numeric performance claim
```

```text
Current sealed implementation HEAD: 4effb6eefa16d246e75213212f884b2546e6d6ef
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
git log -1 --format='%H %s'
git status --short
```

```yaml
commit_lineage_count: 2
head_at_s8: 4effb6eefa16d246e75213212f884b2546e6d6ef
head_subject: "feat(backend): add P3-R4 storage projection and module gate"
commit_lineage:
  r3_s8:
    stage_final_reviewed_tip: f07c387f513ee735fe69e65c94804d7c63115f0d
    subject: "docs(backend): complete P3-R3-S8 module gate and R4 handoff"
    note: R3 handoff documentation SHA; R4 S0 started from this tip
  s0_s7:
    stage_final_reviewed_tip: 4effb6eefa16d246e75213212f884b2546e6d6ef
    stage_exit: pass
    note: S0–S7 were executed and reviewed in-tree; sealed by the R4 implementation commit
  s8:
    reviewed_tip: 4effb6eefa16d246e75213212f884b2546e6d6ef
    stage_exit: pass
    note: S8 evidence was recorded before sealing; current handoff correction is a subsequent documentation change
```

## 3. Changed paths

Cumulative implementation/test/docs surface sealed in `4effb6e` plus this subsequent
handoff evidence correction:

```text
vnext/backend/src/gateway_backend/capabilities/table_rules/
vnext/backend/src/gateway_backend/capabilities/storage_projection/
vnext/backend/src/gateway_backend/repository_import_artifact.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_table_rules_*.py
vnext/backend/tests/test_storage_projection_*.py
vnext/backend/tests/test_canonicalization_manifest.py
vnext/backend/tests/test_repository_import_artifact_*.py
vnext/backend/tests/support/storage_projection.py
vnext/backend/tests/support/table_rules.py
vnext/backend/tests/support/table_rules_legacy_oracle.py
vnext/fixtures/golden/storage-projection/
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-design.md
# archived: p3-r4-storage-projection-execution-plan.md, p3-r4-s0-entry-and-budget-freeze.md,
#   p3-r4-s6-focused-review.md, p3-r4-s7-independent-review.md (tag docs/p3-p4-cleanup-pre-20260823)
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-handoff.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p4-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md
docs/backend-vnext/refactoring/formal/contracts/ruleset-activation-and-migration.md
docs/backend-vnext/refactoring/formal/README.md
docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md
```

S0 已登记根 `canonicalization_cells.py` / `canonicalization_manifest.py` 为 identity-projection
helper，不是 migrated fallback；本轮未改这两文件。`repository_import_artifact.py` 在 S5
改为 thin wrap capability packer。S8 新增登记本 handoff。S0 冻结的
`vnext/fixtures/vectors/storage-projection/` 根目录本轮未落地文件。

No HTTP, Workspace, Submit, Operation Runtime, comparison projection,
production Repository Service/Dolt adapter, production retention, formal
`TAR_ZST` package admission, or new security principal was introduced.

## 4. Commands and results

原 S8 confirmatory rerun 针对 `f07c387` 加 dirty R4 worktree（2026-08-20）；该实现
随后封存为 `4effb6e`。本次证据修正又针对 sealed HEAD 做了 focused/静态复核。
pytest/ruff/mypy 使用 `UV_CACHE_DIR=/tmp/gateway-data-uv-cache` 与 `uv run --offline`，
因为默认 `/root/.cache/uv` 在本环境只读。

| Command | Result |
| --- | --- |
| 原 S8：`cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -m unit`（`f07c387` + dirty R4 worktree） | **609 passed**（2.36s）；1 pre-existing Starlette deprecation warning；历史 gate 证据 |
| 当前 sealed HEAD：`cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit tests/test_architecture.py tests/test_table_rules_*.py tests/test_storage_projection_*.py tests/test_repository_import_artifact_*.py tests/test_canonicalization_manifest.py` | **268 passed**（1.47s） |
| 当前 sealed HEAD：`cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check . && uv run --offline mypy` | **passed**；mypy 139 source files |
| 当前 sealed HEAD：`cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache timeout 60s uv run --offline pytest -q -m unit` | **未完成（exit 124）**；停在既有 `tests/test_app.py::test_healthz_uses_injected_settings`，无断言失败输出 |
| 当前文档修正工作树：`git diff --check` | **passed** |

Focused suite covers migrated legacy parity and selector collisions, explicit
key/keyless/row-integrity, ordered gid/no, schema/content/ordering/manifest
digests, two-entry package safety, atomic publication failures and architecture
boundaries. All are pure unit tests using in-memory readers/stores and
`tmp_path`.

No command used Dolt, Repository Service, HTTP application flow, Workspace,
Submit, an operation runtime, or an external parser process. No
`@pytest.mark.serial` or `@pytest.mark.integration` test was added, so no
`uv run pytest -m serial -n 0` or Dolt integration nodeid run was required.
Timeout/cancel tests use already-expired `deadline_monotonic` or cooperative
probes, not a sleep/join budget.

## 5. Findings closure and deferred register

| ID | Status |
| --- | --- |
| `S6-001` | Closed; reader lifecycle/I/O exceptions map to `BINDING_INVALID` FAILED result; unit rerun passes |
| `S6-002` | Closed; durable manifest write/decode enforce 16 MiB `manifest.json` limit; unit rerun passes |
| `S6-003` | Closed; final publication checkpoint runs after package validation and before COMPLETE; unit rerun passes |
| `S6-004` | Deferred as `R4-D03`; fail-closed publication verified; durable orphan cleanup remains ADR 0012 lifecycle work |
| S7 implementation findings | None; S6 closures remain covered |
| `R3-D04` | **Closed in R4**; storage projection, canonical storage key/schema, CanonicalizationManifest and RepositoryImportArtifactInput |
| `R3-D01` | Deferred；formal `TAR_ZST` SourcePackage admission |
| `R3-D02` | Deferred；Repository Service/Dolt production adapter and hidden-summary write |
| `R3-D03` | Deferred；retention, pinning, eviction, quota and durable artifact lifecycle |
| `R3-D05` | Deferred；projection cache and export-format matrix |
| `R3-D06` | Deferred to P6+；Rust materializer/provider and automatic fallback |
| `R3-D07` | Deferred to P4；durable cancellation/checkpoint/takeover |
| `R4-D01` | Deferred；Repository Service/Dolt production adapter and commit/readback write |
| `R4-D02` | Deferred；protected hidden ruleset metadata commit integration |
| `R4-D03` | Deferred；retention, pinning, eviction, quota, durable operation ownership |
| `R4-D04` | Deferred to P3-R7；mutation plan, ADAPTIVE_PATCH and replay renderer |
| `R4-D05` | Deferred to P6+；Rust storage provider/automatic fallback |
| `R4-D06` | Deferred；online ruleset watcher and migration executor |
| `R4-D07` | Deferred；formal TAR_ZST SourcePackage admission |
| `R4-D08` | Deferred to P3-R5/R6；comparison projection/display/risk semantics beyond LegacyRuleDecision |

**No-open-blocker.** 无未处理 P1/P2 finding、contract ambiguity、import cycle、
unbounded path 或 hidden Repository/application dependency。S8 未 reopen ADR 或
owning contract；S0 numeric budgets 未修订。完整 migrated matrix 52 条规则；
legacy oracle parity 与 ignored-column → `DROP_FROM_STORAGE` 映射保持。

权威延后表：本 handoff §5 deferred register 与
[P3-R4 Storage Projection Design Baseline](p3-r4-storage-projection-design.md)。

## 6. Contract, ADR and fixture references

```text
# archived: p3-r4-s0-entry-and-budget-freeze.md (tag docs/p3-p4-cleanup-pre-20260823)
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-design.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md
docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md
docs/backend-vnext/refactoring/formal/contracts/ruleset-activation-and-migration.md
docs/backend-vnext/refactoring/formal/contracts/fixture-oracle-and-conformance.md
docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md
docs/backend-vnext/refactoring/formal/adr/0004-raw-source-artifact-and-canonical-dolt-storage.md
docs/backend-vnext/refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md
docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md
docs/backend-vnext/refactoring/formal/adr/0015-ruleset-activation-and-migration.md
vnext/fixtures/golden/storage-projection/ruleset/valid/s1-net-cfg/
vnext/fixtures/golden/storage-projection/ruleset/valid/s2-migrated-matrix/
vnext/fixtures/golden/storage-projection/ruleset/malformed/s1-duplicate-selector/
vnext/fixtures/golden/storage-projection/manifest/valid/s5-durable-roundtrip/
vnext/fixtures/golden/storage-projection/package/valid/s5-structural-shape/
```

S0 resource budgets remain the authority and were not revised in S8. Fixture
naming and parameter-table ownership remain `table_rules` 与 `storage_projection`。

## 7. Ruleset and storage projection identity

```text
ruleset_id                     = backend-vnext/table-ruleset
ruleset_version                = v2
table_ruleset_contract_version = gateway-vnext.table-ruleset:v1
table_ruleset_version          = 1    # R3 injection; additive only
storage_projection_version     = 1
canonicalization_manifest_contract = 3.0.0
migrated_rule_count            = 52
migrated_ruleset_digest        = sha256:6f74c8659fe677f2ac1f882e648fdc722a28ab501955a2f9d2b5ae68c7a0da80
```

`ruleset_digest` 是 canonical ruleset document 的 RFC8785-JCS SHA-256，不加
manifest 域前缀。manifest digest 保持
`SHA256(b"gateway-vnext:canonicalization-manifest:v1\0" || RFC8785-JCS(document))`。
R3 拥有 raw/business/`snapshot_digest`；R4 拥有 schema/content/ordering/storage/manifest
digest，不复制 R3 私有算法。

## 8. Stable public boundary

R5 可消费下列 public surface 与各 owner 的 `contracts.py`。不得 import
`storage_projection._digest`、`_ordered`、`_runtime`、`view.py`，也不得 import R3
`_digest`、`_parquet`、`_reader`、`_catalog`、`_ruleset`、`_archive`、`_paths`、
`_ast`、`_bind`，不得依赖 `tests/support` 或把根 `canonicalization_manifest.py`
identity-projection 当作 migrated fallback。

Public entrypoints and result types：

```text
table_rules
  migrated_table_ruleset_snapshot() -> TableRulesetSnapshot
  resolve_table_rule(...)
  table_ruleset_document / table_ruleset_from_document / compute_ruleset_digest
  TableRulesetSnapshot / LegacyRuleDecision / StorageRuleView / ResolvedTableRule
  RULESET_ID / RULESET_VERSION / TABLE_RULESET_CONTRACT_VERSION
  TABLE_RULESET_VERSION / STORAGE_PROJECTION_VERSION
  TableCompareKey / TableRuleSelector / TableRuleRecord

storage_projection
  project_storage(ProjectionRequest) -> ProjectionResult
  publish_canonicalization(...) -> CanonicalPublicationResult
  open_canonicalization_manifest / open_repository_import_package
  durable_manifest_bytes / canonicalization_manifest_from_bytes
  build_repository_import_package / validate_repository_import_package
  repository_import_manifest_bytes / repository_import_input_from_bytes
  ProjectionStatus: COMPLETE | FAILED
  CanonicalizationManifest / CanonicalizationManifestTable
  RepositoryImportArtifactInput / RepositoryImportTable / RepositoryImportColumn
  STORAGE_PROJECTION_VERSION / CANONICALIZATION_MANIFEST_CONTRACT
  MAX_MANIFEST_JSON_BYTES / MAX_REPLAY_SQL_BYTES

snapshot_materialization (R3 public; unchanged)
  Snapshot / SnapshotTableArtifact / SnapshotTableReader
  publish_snapshot_table_artifact / open_snapshot_table_artifact
```

`ProjectionResult` 在 `FAILED` 时不发布 manifest 或 import input。表级 diagnostics
允许；任一 required 表失败使结果 `FAILED`。R4 从不发布 partial Repository import
closure。`COMMIT_VALIDATED` 永不由 R4 自提升。

Capability DAG：

```text
source_package_staging          leaf
table_access                    leaf
table_rules                     leaf
composite_signal             -> table_access
snapshot_materialization     -> table_access, table_rules, source_package_staging, composite_signal
storage_projection           -> table_rules, snapshot_materialization
```

Architecture tests 覆盖 forbidden tokens（`dolt`、`gateway_repository`、
`host_path`、HTTP/application、SQL execution、external XML resolver）。

## 9. Known limitations and deferred items

- 真实 Repository Service/Dolt adapter、commit/readback 与 hidden ruleset metadata
  write 是 `R4-D01` / `R4-D02`。
- R4 不实现 retention/eviction/quota 或 durable artifact lifecycle（`R4-D03` /
  ADR 0012）。失败后不可达的 L3 object 不通过 public ref 暴露。
- mutation plan、`ADAPTIVE_PATCH` 与 replay SQL generation 是 `R4-D04` / P3-R7；
  R4 只接受调用方显式 `replay.sql` bytes 并做 envelope 校验，不生成、不执行 SQL。
- 无 Rust storage provider 或 automatic fallback（`R4-D05`）。
- online ruleset watcher 与 `STORAGE_BREAKING` migration executor 是 `R4-D06`。
- 正式 SourcePackage 仍仅 `TAR_GZ`（`R4-D07` / `R3-D01`）。
- comparison projection、display 与 risk semantics 超出 `LegacyRuleDecision` 的
  部分是 `R4-D08`。R5 可用 comparison key/scope/`UPDATE_ONLY`；不得把 comparison
  metadata 推断为 storage drop。
- 无独立 projection benchmark runner；不得从本 handoff 读取 numeric performance
  claim。
- `COMMIT_VALIDATED` 不能由 `project_storage` / `publish_canonicalization` 自提升。

## 10. R5 entry prerequisites

R5 仍须先写详细计划再实现。R5 entry 必须拿到并保持：

- stable public canonical storage projection、`CanonicalizationManifest` 与
  `RepositoryImportArtifactInput`（§8）；
- `COMPLETE | FAILED` 与 staging write → validation → atomic publish；失败无
  public manifest/import ref；
- canonical schema/key/row/content/ordering facts 与 opaque manifest digest binding；
- explicit ruleset/storage_projection/source artifact bindings；
- every legacy ignored column is `DROP_FROM_STORAGE` with
  `legacy_ignored_column:<selector>` reason and is absent from Repository
  structural schema/rows；
- cache miss 必须能从 source package 或 pinned RepositoryRef 重建；
- `COMMIT_VALIDATED` 不可自提升；
- no Repository/HTTP/application implementation dependency in R4 capabilities；
- `R4-D01`–`R4-D08` explicitly linked（§5）；
- R5 只消费 §8 public surface 与 `contracts.py`，不 import R4 private modules。

本 handoff 不授权 comparison projection、HTTP/Workspace/Submit、Repository effect
或其他 P3 capability 算法。

## 11. Non-goals and authorization

R4 未做、R5 不得从本文推断为已授权：

- comparison projection、standard diff、row records、`FULL`/`MODIFIED_ONLY`
  （`R4-D08`）；
- 真实 Repository Service/Dolt production adapter（`R4-D01`）；
- HTTP、Workspace、Submit、PreviewResult、Operation Runtime；
- mutation/replay renderer（`R4-D04`）；
- production retention/cleanup、新的安全主体、container/image validation；
- formal `TAR_ZST` SourcePackage admission（`R4-D07`）；
- Rust storage provider 或 automatic fallback（`R4-D05`）。

```yaml
p3_r4_exit: pass
p3_r5_ready: yes
p3_implementation_authorized: no
```

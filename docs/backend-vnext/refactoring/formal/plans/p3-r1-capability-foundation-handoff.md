# P3-R1 Capability Foundation Handoff

状态：`pass`（R1 module gate；R2 entry。不是 Phase 3 全部实现授权，不含 parser 实现）

日期：2026-08-19

Owner：Backend vNext Capability Architecture

本文是 P3-R2 的**默认 R1 入口**。它记录 R1 gate 身份、稳定边界、测试证据、限制和
R2 prerequisites。字段级 parser/table-access 语义仍由 P3 owning contracts 拥有；不得
从 R1 skeleton 猜测。过程证据见 S0 inventory、S4/S6 reviews 和 R1 执行计划。

上级计划：[P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)
过程证据：R1 执行计划与 S0 inventory 已归档；恢复见 tag `docs/p3-p4-cleanup-pre-20260823` 与
[p3-p4-cleanup-manifest.yaml](p3-p4-cleanup-manifest.yaml) `paths.archive_from_default`。

```yaml
handoff_kind: p3_r1_capability_foundation
round: P3-R1-S7
s6_review: pass
p3_r1_exit: pass
p3_r2_ready: yes
p3_implementation_authorized: no
worktree_at_validated_tip: dirty_docs_only
validated_code_sha: fc5159576b30de5bd8c1428446537aa92a23642b
s0_entry_sha: d43207360e51ee2e246b83134828bf98195b0768
container_rebuild: no
benchmark: not_applicable
```

`validated_code_sha` 是 S6 已审且本 S7 复跑通过的代码 SHA，不是本 handoff 文档 commit
SHA。S7 开始时工作树仅有未提交的 S6 文档（无 `vnext/` 代码变更）；文档提交完成后成为
`r2_entry_sha` / `handoff_documentation_sha`，不在本文件中自引用。

## 1. Gate identity

```yaml
branch: phase1/gate-ownership-repair
s6_reviewed_tip: fc5159576b30de5bd8c1428446537aa92a23642b
s6_review_record: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r1-s6-independent-review.md
s4_review_record: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r1-s4-focused-review.md
s0_inventory: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r1-s0-asset-inventory.md
s5: not_required
s7_tests_rerun: yes
container_rebuild_reason: R1 candidate does not touch image, deployment, or container-only runtime boundaries
last_validated_image_revision: none; source-tree validation is the authoritative evidence
container_validation_deferred_to: a later R if an image/deployment/container boundary is introduced
benchmark_reason: R1 is contract/test foundation only; no data-plane parser/projection/comparison path
```

## 2. Commit lineage

核对命令：

```bash
git log --reverse --format='%H %s' \
  d43207360e51ee2e246b83134828bf98195b0768..fc5159576b30de5bd8c1428446537aa92a23642b
```

```yaml
commit_lineage_count: 5
commit_lineage:
  s0:
    stage_final_reviewed_tip: 1cbae04bcc97a64751634a561003993bda87e4c6
    subject: "docs(backend): record P3-R1-S0 asset inventory"
    stage_exit: pass
  s1:
    stage_final_reviewed_tip: 908d5ea2140154c7efb162c020acbca9809651a7
    subject: "feat(backend): add P3-R1-S1 capability ownership skeleton"
    stage_exit: pass
  s2:
    stage_final_reviewed_tip: 91c8e81dc78a3316e7888fa20008b18b794650b2
    subject: "test: close P3-R1-S2 shared-primitive gap with conformance checks"
    stage_exit: pass
  s3:
    stage_final_reviewed_tip: e3542ecac3076ae25a51d65f029fb6b852e88665
    subject: "test(backend): close P3-R1-S3 artifact staging conformance"
    stage_exit: pass
  s4:
    stage_final_reviewed_tip: fc5159576b30de5bd8c1428446537aa92a23642b
    subject: "docs(backend): complete P3-R1-S4 focused review"
    stage_exit: pass
  s5:
    stage_exit: not_required
  s6:
    reviewed_tip: fc5159576b30de5bd8c1428446537aa92a23642b
    stage_exit: pass
    note: S6 independently retested this tip; the S6 review record was uncommitted at S7 start and is included with this handoff documentation commit
```

## 3. Changed paths

Cumulative implementation/test/docs surface in `d432073..fc51595`:

```text
vnext/backend/src/gateway_backend/capabilities/
vnext/backend/src/gateway_backend/canonical_row_hash_ipc.py
vnext/backend/src/gateway_backend/infrastructure/artifact_store/local_store.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_artifact_boundary.py
vnext/backend/tests/test_artifact_ref_conformance.py
vnext/backend/tests/support/artifact_staging.py
vnext/backend/tests/test_artifact_staging_conformance.py
vnext/shared_kernel/tests/conftest.py
docs/backend-vnext/refactoring/formal/plans/p3-*.md
```

No parser, source materialization, storage projection algorithm, comparison, risk,
mutation planner, application flow, HTTP, Workspace, Submit, Operation Runtime,
retention policy, or new security principal was introduced.

## 4. Commands and results

S7 confirmatory rerun against `validated_code_sha` `fc51595`（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit` | **81 passed**（0.58s） |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_artifact_boundary.py tests/test_artifact_ref_conformance.py tests/test_artifact_staging_conformance.py` | **62 passed**（0.42s） |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**; no issues in 55 source files |
| `cd vnext/shared_kernel && uv run pytest -m unit` | **242 passed**（0.82s） |
| `cd vnext/shared_kernel && uv run ruff check . && uv run mypy` | **passed**; mypy 34 source files |
| `cd vnext/rust && cargo test -p gateway-shared-kernel --locked` | **passed**; Rust lib 82, vector conformance 3, SQL ENUM/SET 3 |
| `git diff --check d432073..HEAD` | **passed** |

No command used Dolt, Repository Service, HTTP, Workspace, Submit, an operation
runtime, or an external process beyond the locked Rust package tests. Tests use
in-memory/local stores and `tmp_path`.

## 5. Inventory and decision register

权威盘点：R1 S0 asset inventory 已归档；恢复见 tag `docs/p3-p4-cleanup-pre-20260823`。

KEEP/EXTEND 的 foundation：`gateway_shared_kernel` canonical primitives；Backend
四字段 `ArtifactRef` / `ArtifactStorePort`；`LocalArtifactStore` 仅作 bounded
local/test staging；capability 语义 metadata 留在 concrete owner；repository-level
golden/vectors 与 owner-specific loaders。

DEFER：canonicalization/manifest/import writer 到 R4/R7（`F-002`）；production
artifact retention/cleanup 到后续 lifecycle owner（`F-004`，ADR 0012）。

REMOVE/禁止：`capabilities/common`、`capabilities/utils`、万能 provider base、
root-level compatibility alias、新的 shared primitive。

| ID | Status |
| --- | --- |
| `D-001`–`D-007` | Accepted；S2 确认无 shared-primitive gap |
| `F-001` | Closed in S3 |
| `F-002` | Deferred to R4 |
| `F-003` | Closed in S1 |
| `F-004` | Deferred to later lifecycle owner |
| `S4-001`–`S4-004`, `S4-006`–`S4-008` | Closed; no S6 regression |
| `S4-005` | Accepted non-blocking limitation |

**No-open-blocker.** 无未处理 P1/P2 finding、contract ambiguity、import cycle、
artifact identity violation 或 test-classification blocker。

## 6. Contract, ADR and fixture references

```text
docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md
docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md
docs/backend-vnext/refactoring/formal/contracts/canonical-row-hash-compute-boundary.md
docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md
docs/backend-vnext/refactoring/formal/contracts/fixture-oracle-and-conformance.md
docs/backend-vnext/refactoring/formal/adr/0010-minimal-golden-and-ordinary-ci.md
docs/backend-vnext/refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md
vnext/fixtures/golden/canonical-row-hash/mixed-scalars/
vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/
vnext/fixtures/vectors/compute/canonical-row-hash/v1/
```

R1 未新增 golden/vector corpus，也未修订 owning contract/ADR。

## 7. Stable public boundary

R2 可消费下列边界；不得把 skeleton 当作 parser 合同。

Owner packages under `vnext/backend/src/gateway_backend/capabilities/`：

```text
canonical_row_hash
table_access
table_rules
snapshot_materialization
storage_projection
comparison_projection
comparison
risk_evaluation
business_projection
surface_assembly
bundle_assembly
mutation_planning
```

Each owner has public `contracts.py`. There is no `capabilities/common`,
`capabilities/utils`, `_internal`, or generic provider base.
`table_access/contracts.py` does not pre-declare TableReader/parser field types.

Allowed downstream → upstream `contracts` only（与
`vnext/backend/tests/test_architecture.py` 的 `ALLOWED_UPSTREAM_OWNERS` 一致）：

```text
snapshot_materialization -> table_access, table_rules
storage_projection -> table_rules, snapshot_materialization
comparison_projection -> table_rules, snapshot_materialization
comparison -> comparison_projection
risk_evaluation -> comparison
business_projection -> comparison
surface_assembly -> comparison, risk_evaluation, business_projection
bundle_assembly -> surface_assembly
mutation_planning -> storage_projection
canonical_row_hash -> (none; Shared Kernel + artifacts envelope only)
table_access, table_rules -> (none at capability layer)
```

Test staging helper contract（R2–R7 import；不拥有 capability content schema、
production retention 或 cleanup policy）：

```text
vnext/backend/tests/support/artifact_staging.py
```

Helper 覆盖 `tmp_path` layout、fresh-store reopen、object/sidecar paths、minimal-ref
host-path assertions。`ArtifactRef` 仍是 `artifact_id/media_type/size_bytes/raw_sha256`。

## 8. Known limitations and deferred items

- `S4-005`：`LocalArtifactStore` process-local ref cache is adapter state, not
  coordination or recovery. Fresh-store conformance covers on-disk identity after
  reopen.
- `F-002`：Storage Projection key/row-loss/structural policy matrix belongs to R4.
- `F-004`：Production artifact retention/cleanup remains the later lifecycle owner
  under ADR 0012.
- Canonical row-hash algorithm modules remain at backend root
  (`canonical_row_hash_ipc.py` / compute) until a later capability R.
- Phase 1 canonicalization/manifest/import writer remains R4/R7 evidence only.

## 9. R2 entry prerequisites

R2 详细计划可以创建。R2 entry 必须拿到并保持：

- stable public owner/import checks（上节 DAG 与 architecture tests）；
- accepted shared primitive inventory（`D-001`/`D-007`；无新 primitive）；
- artifact/staging helper contract（`tests/support/artifact_staging.py`）；
- no-open-blocker statement（§5）；
- R2-specific parser questions **重新从 P3 contracts 读取**，而不是从 R1
  `table_access` skeleton 或内部实现猜测。

R2 仍须先写详细计划再实现。本 handoff 不授权 SQL/XML parser、source
materialization 或其他 P3 capability 算法。

## 10. Non-goals and authorization

R1 未做、R2 不得从本文推断为已授权：

- SQL/XML parser、table access protocol 字段、bounded row stream；
- source materialization / snapshot / storage projection / comparison / risk /
  mutation planner / application flow；
- HTTP、Workspace、Submit、Operation Runtime、Repository business semantics、Dolt
  fixtures in pure capability tests；
- production retention/cleanup、新的安全主体、container/image validation。

```yaml
p3_r1_exit: pass
p3_r2_ready: yes
p3_implementation_authorized: no
```

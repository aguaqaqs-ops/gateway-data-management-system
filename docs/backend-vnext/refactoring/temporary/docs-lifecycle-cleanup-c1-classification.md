# Documentation Lifecycle Cleanup — C1 Authority and Consumer Classification

状态：`complete`（`c1_continue_plan: yes`；`unresolved_escalations: 0`）

日期：2026-08-17

本记录确认每个文档的 owner、consumer、保留义务，以及与 S11 / formal README / package README 的状态关系。没有修改 `vnext/**`、没有打 tag、没有重跑测试。分类供 C2 组装 P3 index 与 compact P2 handoff；C4 不得删除带 `must_retain_source_pointer` / `leave_in_vnext` / `retain_oracle` 的路径。

权威计划：[Documentation Lifecycle Cleanup Execution Plan](all-documentation-lifecycle-cleanup-execution-plan.md) §5 C1
上游 C0：[docs-lifecycle-cleanup-c0-inventory.md](docs-lifecycle-cleanup-c0-inventory.md)
机器可读表：[docs-lifecycle-cleanup-c1-classification.json](docs-lifecycle-cleanup-c1-classification.json)
P2 完成权威：[p2-r6-s11-final-handoff.md](p2-r6-s11-final-handoff.md)

## Continue / stop

```yaml
c1_status: complete
c1_continue_plan: yes
unresolved_escalations: 0
source_build_deployment_delta: no
unique_temporary_only_code_consumer: recorded_and_retained
unformalized_p3_business_semantics: retained_as_oracle_not_deleted
readme_status_conflict: recorded_s11_is_authority
```

会挡住 **C4 删除** 的条件已经出现，但不挡住 C1/C2：vnext/pytest 的唯一引用和尚未 formalize 的 P3 业务语义都标了保留动作。Package README 与 S11 的状态冲突已登记；S11 写明该 README 不是 Phase 2 完成 authority，因此不构成“三个权威互相矛盾、无法继续分类”。

## Status consistency

| 来源 | 宣称 | C1 判定 |
| --- | --- | --- |
| S11 final handoff | `phase_2_complete: yes`；candidate/image `2ef88427` / `4b8f88ed` | **P2 完成与身份的 authority** |
| formal README 当前阶段段 | 同样列出 S11 pass / P3 next | 与 S11 一致 |
| formal README「完整handoff」链接 | 仍指向 P2-R5-S7 | **索引漂移**；C2/C4 改链到 compact handoff |
| `vnext/repository_service/README.md` | P2-R5 / `phase_2_complete=no` | **不是**完成状态 authority；本计划不得修改 |
| Architecture / Implementation Stages 状态行 | 下一入口 P2-R2 | 过期散文；阶段语义仍 NORMATIVE |
| architecture-simplification plan | D01 READY / P2 PENDING | 过期；工作已完成 |
| decision ledger R8 | ACL ACCEPTED | 已被 ADR 0009 / RS contract 否定；不是未 formalize 的现行语义 |

## Confirmed counts

| 分类 | C0 初步 | C1 确认 |
| --- | ---: | ---: |
| `NORMATIVE` | 25 | 26 |
| `ACTIVE_INTERFACE` | 9 | 43 |
| `EVIDENCE` | 62 | 63 |
| `HISTORICAL` | 154 | 169 |
| `REDUNDANT` | 1 | 1 |
| `ESCALATE` | 49 | 0 |

C0 `ESCALATE` 49 项已全部给出 owner 与 C4 动作（resolved 49）。文件级剩余 ESCALATE：0。

### C4 action counts

| action | 含义 | 数量 |
| --- | --- | ---: |
| `archive` | C4 从默认树移除；Git tag/history 保留 | 224 |
| `leave_in_vnext` | 位于 candidate source digest，本计划不改 | 6 |
| `must_retain_source_pointer` | vnext 或 pytest 唯一引用，不能删/移 | 3 |
| `retain_active` | 留在默认检索树 / P3 RS allowlist | 30 |
| `retain_in_place` | 保留在 formal ADR/contract 系列，不进 P3 默认入口 | 5 |
| `retain_oracle` | 留在树中供 P3 capability 设计，不进 RS 默认入口 | 34 |

## Unique source-tree / test consumers

这些引用使对应文档不能在本计划中删除或改路径：

| 文档 | consumer | 动作 |
| --- | --- | --- |
| `p2-r1-runtime-provider-feasibility.md` | `vnext/repository_service/tests/test_p2_r1_audit_corrective.py` 读取 methodology version | `must_retain_source_pointer` |
| `p2-r5-commit-pinned-read-execution-plan.md` | `vnext/repository_service/README.md` 当作完整handoff | `must_retain_source_pointer` |
| `repository-service.md` 等 formal contracts | Service README、sql-enum-set fixture README | `retain_active` |
| `p2-r9-s2-step-e-container-gate.md` | `vnext/deploy/p2r1-cache/README.md` | `must_retain_source_pointer` |
| `testing-conventions.md` | `AGENTS.md` | `retain_active` |

CI 工作流目录不存在。无 GitHub Actions 文档引用。

## Decision ledger

三份 ledger 无 `OPEN` / `DEFERRED`。Round 8–11 全部 `ACCEPTED`，但其中认证/ACL/ResourcePolicy 条款与现行
[Repository Service Contract](../formal/contracts/repository-service.md)（不提供 CallerIdentity / per-repository ACL）和
[ADR 0009](../formal/adr/0009-proportional-assurance-and-trusted-internal-repository.md) 冲突。
这不是“仍未 formalize、删除会丢语义”，而是 **过期 ACCEPTED 未改 SUPERSEDED**。
C1 将其标为 `HISTORICAL` / `archive`。C2 不得把 ledger 当作 P3 规则。

## P3 capability oracles

Architecture Plan 已声明旧 `docs/backend-vnext/contracts|capabilities|adr|flows|operations` 只是 legacy 证据。
它们仍包含 Snapshot / Comparison / Risk / Flow 等尚未进入 `refactoring/formal/contracts` 的业务语义。
C1 标为 `ACTIVE_INTERFACE` / `retain_oracle`：P3 Capability Foundation 设计需要它们，但它们不是 Repository Service wire authority，也不进入 C2 的默认 RS allowlist。

## Findings

### `package-readme-stale-p2r5`

- 路径：`vnext/repository_service/README.md`
- 事实：仍写 P2-R5 functional exit、`production_retest_required=yes`、`phase_2_complete=no`。
- 权威：S11 handoff 声明本 README 不是 Phase 2 完成 authority；本计划不得改 `vnext/`。
- C2：在 P3 index / compact handoff 中警告。不要改写 package README。

### `formal-readme-handoff-link`

- 路径：`docs/backend-vnext/refactoring/formal/README.md`
- 事实：已列出 S11 pass / `phase_2_complete: yes`，但「完整handoff」仍链到 P2-R5-S7。
- 权威：S11 handoff 才是当前 P2 完成记录。
- C2：把该链接改到 C2 compact P2 interface handoff（docs-only）。

### `architecture-and-stages-next-entry`

- 路径：`docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md and implementation-stages.md`
- 事实：状态散文仍把 P2-R2 写成下一入口。
- 权威：S11 `phase_2_complete: yes`；下一步是 Phase 3 full design。
- C2：改索引时只刷新状态行，不改阶段语义。

### `decision-ledger-accepted-vs-adr-0009`

- 路径：`docs/backend-vnext/refactoring/temporary/phase-2/decision-ledger-round-8-to-11.md`
- 事实：全部 `ACCEPTED`，含 per-repository ACL（P2-R8-D02）。现行 RS contract 禁止 CallerIdentity / per-repository ACL。无 OPEN/DEFERRED。
- 权威：ADR 0009 + Repository Service Contract。
- C2：不得把 ledger 当作 P3 规则。归档 ledger。reopen 条件以 ADR 0009 / RS contract 为准，写入 compact handoff。

### `pytest-bound-p2-r1-feasibility`

- 路径：`docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md`
- 事实：`test_authority_methodology_version_matches_settings` 读取该文件。
- 权威：该文件 + Performance Measurement contract；测试消费者阻止归档。
- C2：保持路径稳定。C4 不得归档。

### `vnext-pointer-p2-r9-step-e`

- 路径：`docs/backend-vnext/refactoring/temporary/p2-r9-s2-step-e-container-gate.md`
- 事实：`vnext/deploy/p2r1-cache/README.md` 的唯一 runbook 指针。
- 权威：S11 image 身份是 `2ef88427`；该记录是历史 `e78b564` 证据。
- C2：在 owning stage 改掉 vnext 指针之前必须保留。不是当前 image identity。

### `vnext-pointer-p2-r5-plan`

- 路径：`docs/backend-vnext/refactoring/formal/plans/p2-r5-commit-pinned-read-execution-plan.md`
- 事实：package README 把它当作完整handoff 的唯一指针。
- 权威：S11 handoff。
- C2：保留该文件。P3 真正入口是 compact handoff。

### `missing-client-readme`

- 路径：`vnext/repository_client/README.md`
- 事实：P3 active-context 点名 Client README，文件不存在。
- 权威：Repository Service Contract + client 包源码。
- C2：在 docs-only 的 P3 index / compact handoff 描述 client 表面。本计划不得创建 `vnext/repository_client/README.md`。

### `formal-links-into-temporary`

- 路径：`docs/backend-vnext/refactoring/formal/plans/* and adr/0013`
- 事实：formal plans 与 ADR 0013 深链 temporary handoff 和 EXT-W1 stage 记录。
- 权威：本清理计划 C4：删除 temporary 文件前必须改链到 compact handoff / manifest / tag。
- C2：compact P2 handoff 成为存活指针。

### `openapi-wire-authority`

- 路径：`vnext/repository_service/src/gateway_repository_service/http/openapi.py`
- 事实：RS contract 规定激活的 FastAPI OpenAPI 才是 HTTP wire authority。文档里没有第二份手写 schema。
- 权威：Repository Service Contract 的 wire 条款。
- C2：P3 index 只链到 contract + 生成 OpenAPI 的源，不复制字段表。

## Classification by class

### `NORMATIVE` (26)

| 路径 | owner | role | C4 | vnext/test |
| --- | --- | --- | --- | --- |
| `docs/backend-vnext/refactoring/formal/adr/0001-python-rust-hybrid-compute-strategy.md` | ADR 0001 | `active_adr` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/adr/0002-minimal-persisted-business-state.md` | ADR 0002 | `active_adr` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/adr/0003-external-effect-reconciliation.md` | ADR 0003 | `active_adr` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/adr/0004-raw-source-artifact-and-canonical-dolt-storage.md` | ADR 0004 | `active_adr` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/adr/0005-shared-canonical-encoding.md` | ADR 0005 | `active_adr` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/adr/0009-proportional-assurance-and-trusted-internal-repository.md` | ADR 0009 | `active_adr` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/adr/0010-minimal-golden-and-ordinary-ci.md` | ADR 0010 | `active_adr` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md` | ADR 0012 | `active_adr` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md` | ADR 0013 | `active_adr` | `retain_active` | yes |
| `docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md` | Architecture and Refactoring Plan | `architecture_boundary` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md` | this file (business-lifecycle-and-state) | `formal_contract` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/contracts/canonical-row-hash-compute-boundary.md` | this file (canonical-row-hash-compute-boundary) | `formal_contract` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md` | this file (canonical-storage-and-repository-boundary) | `formal_contract` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md` | this file (contract-taxonomy-and-ownership) | `formal_contract` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/contracts/external-effect-and-recovery.md` | this file (external-effect-and-recovery) | `formal_contract` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/contracts/fixture-oracle-and-conformance.md` | this file (fixture-oracle-and-conformance) | `formal_contract` | `retain_active` | yes |
| `docs/backend-vnext/refactoring/formal/contracts/performance-measurement-and-baseline.md` | this file (performance-measurement-and-baseline) | `formal_contract` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/contracts/repository-service.md` | this file (repository-service) | `formal_contract` | `retain_active` | yes |
| `docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md` | this file (shared-canonical-encoding) | `formal_contract` | `retain_active` | yes |
| `docs/backend-vnext/refactoring/formal/plans/dx-cross-phase-interface-reconciliation.md` | DX Cross-Phase Interface Reconciliation | `shared_interface_baseline` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/plans/implementation-stages.md` | Implementation Stages | `stage_sequence_and_p3_entry` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md` | P2-R1 feasibility + Performance Measurement contract | `pytest_bound_methodology_version` | `must_retain_source_pointer` | yes |
| `docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md` | proportional-assurance-and-risk-based-verification-policy | `cross_stage_policy` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/policies/rust-safety-and-performance-policy.md` | rust-safety-and-performance-policy | `cross_stage_policy` | `retain_active` | no |
| `docs/backend-vnext/testing-conventions.md` | Testing Conventions | `test_and_container_gate` | `retain_active` | no |
| `docs/backend-vnext/testing-fixtures.md` | Testing Fixtures | `fixture_material_owner` | `retain_active` | no |

### `ACTIVE_INTERFACE` (43)

| 路径 | owner | role | C4 | vnext/test |
| --- | --- | --- | --- | --- |
| `AGENTS.md` | Engineering / AGENTS.md | `contributor_constraint` | `retain_active` | no |
| `docs/backend-vnext/README.md` | Backend vNext Architecture | `documentation_index` | `retain_active` | no |
| `docs/backend-vnext/adr/0001-snapshot-table-and-dolt-import-boundary.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/adr/0002-comparison-hash-sqlite-mode-selection.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/adr/0003-dolt-native-provider-selection.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/artifacts.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/bundle-assembly.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/business-projection.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/comparison-compute.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/composite-signal-device.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/dolt-native-provider.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/ordered-diff-compute.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/project-identity-and-dataset-replacement.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/repository-import.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/repository-ref-materialization.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/risk-evaluation.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/snapshot-materialization.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/surface-assembly.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/table-presentation-large-data-report.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/capabilities/table-presentation.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/contracts/comparison-bundle.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/contracts/comparison-surface.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/contracts/comparison.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/contracts/ordered-diff.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/contracts/risk.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/contracts/snapshot-table-access.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/contracts/snapshot.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/contracts/source-package-and-snapshot.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/contracts/source-package.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/contracts/table-presentation.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/flows.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/frontend-surface-simplification.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/glossary.md` | Architecture (shared vocabulary) | `glossary` | `retain_active` | no |
| `docs/backend-vnext/identity-and-digests.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/implementation-boundary.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/modules.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/operations.md` | P3 Capability Foundation design (not yet formalized); Architecture Plan demotes these to legacy oracles | `p3_capability_oracle` | `retain_oracle` | no |
| `docs/backend-vnext/refactoring/README.md` | Backend vNext Architecture | `documentation_index` | `retain_active` | no |
| `docs/backend-vnext/refactoring/formal/README.md` | Backend vNext Architecture | `documentation_index` | `retain_active` | no |
| `vnext/fixtures/vectors/compute/canonical-row-hash/v1/README.md` | Fixture-oracle contract / ADR 0013 | `fixture_vector_readme` | `leave_in_vnext` | no |
| `vnext/fixtures/vectors/repository/sql-enum-set/v1/README.md` | Fixture-oracle contract / ADR 0013 | `fixture_vector_readme` | `leave_in_vnext` | no |
| `vnext/repository_service/README.md` | Repository Service Contract (wire); this README is not P2-complete authority | `package_surface_stale_status` | `leave_in_vnext` | yes |
| `vnext/shared_kernel/README.md` | Shared Canonical Encoding Contract | `package_readme` | `leave_in_vnext` | no |

### `EVIDENCE` (63)

| 路径 | owner | role | C4 | vnext/test |
| --- | --- | --- | --- | --- |
| `docs/backend-vnext/dolt-test/dolt-import-provider-functional-test-result-2026-06-20.md` | capability/dolt notes as oracle | `historical_functional_test` | `archive` | no |
| `docs/backend-vnext/dolt-test/dolt-native-diff-functional-test-result-2026-06-21.md` | capability/dolt notes as oracle | `historical_functional_test` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-audit-correction-2026-08-02.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/a-paired/a-devnull.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/a-paired/a-devnull.summary.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/a-paired/a-paired-review-summary.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/b-restart/b-restart.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/b-restart/b-restart.summary.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/paired-analysis.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-19fb10f-failure-analysis-2026-08-04.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-19fb10f-run-report-2026-08-04.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-19fb10f-summary-2026-08-04.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-80858ca-2026-08-04/p2-r1.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-80858ca-2026-08-04/p2-r1.summary.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-80858ca-2026-08-04/review-summary.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-no-go-decision-2026-08-04.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-provider-decision-2026-08-02.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-provider-summary-2026-08-02.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-target-image-summary-2026-08-02.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-authority-and-implementation-brief.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-formal-80aff3e-2026-08-05/README.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-formal-80aff3e-2026-08-05/p2-r1-v8.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-formal-80aff3e-2026-08-05/p2-r1-v8.summary.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-go-decision-2026-08-05.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-00232da-2026-08-05/README.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-00232da-2026-08-05/v8-smoke-00232da-a2/a-w0.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-00232da-2026-08-05/v8-smoke-00232da-a2/a-w0.summary.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-00232da-2026-08-05/v8-smoke-00232da-b/b-w0.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-00232da-2026-08-05/v8-smoke-00232da-b/b-w0.summary.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-36f8c2f-2026-08-05/README.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-36f8c2f-2026-08-05/v8-smoke-36f8c2f-a/a-w0.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-36f8c2f-2026-08-05/v8-smoke-36f8c2f-a/a-w0.summary.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-36f8c2f-2026-08-05/v8-smoke-36f8c2f-b/b-w0.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-36f8c2f-2026-08-05/v8-smoke-36f8c2f-b/b-w0.summary.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-80aff3e-2026-08-05/README.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-80aff3e-2026-08-05/v8-smoke-80aff3e-a/a-w0.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-80aff3e-2026-08-05/v8-smoke-80aff3e-a/a-w0.summary.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-80aff3e-2026-08-05/v8-smoke-80aff3e-b/b-w0.md` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-80aff3e-2026-08-05/v8-smoke-80aff3e-b/b-w0.summary.json` | S11 lineage / P2-R1 go-decision | `completed_gate_archive` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-external-descriptor.yaml` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-k-final-handoff.md` | S11 compact P2 handoff to be assembled in C2 | `stage_handoff_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-final-handoff.md` | S11 compact P2 handoff to be assembled in C2 | `stage_handoff_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-final-handoff.md` | S11 compact P2 handoff to be assembled in C2 | `stage_handoff_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-lineage-inventory.json` | S11 compact P2 handoff to be assembled in C2 | `stage_handoff_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-final-handoff.md` | S11 compact P2 handoff to be assembled in C2 | `stage_handoff_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-final-handoff.md` | S11 compact P2 handoff to be assembled in C2 | `stage_handoff_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw-rerun/g1-verification-level.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw-rerun/g2-effect-state.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw-rerun/g3-cas-store.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw-rerun/g4-path-version.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw-rerun/g5-wire-readback.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw/g1-verification-level.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw/g2-effect-state.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw/g3-cas-store.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw/g4-path-version.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw/g5-wire-readback.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-final-handoff.md` | S11 compact P2 handoff to be assembled in C2 | `stage_handoff_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-old-reference-raw/g1-verification-level.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-old-reference-raw/g2-effect-state.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-old-reference-raw/g3-cas-store.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-old-reference-raw/g4-path-version.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-old-reference-raw/g5-wire-readback.txt` | owning stage handoff | `raw_or_generated_evidence` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r9-s2-step-e-container-gate.md` | ADR 0012 (semantics); this file is a historical container-gate record | `historical_container_gate` | `must_retain_source_pointer` | yes |

### `HISTORICAL` (169)

| 路径 | owner | role | C4 | vnext/test |
| --- | --- | --- | --- | --- |
| `docs/backend-vnext/implementation-plan.md` | Implementation Stages (replacement) | `pre_p2_module_plan` | `archive` | no |
| `docs/backend-vnext/notes/archive-parity-audit.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/cache-contract-cleanup-execution-plan.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/comparison-bundle-formal-contract-scheme.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/comparison-bundle-migration-execution-plan.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/comparison-bundle-oracle-audit.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/composite-signal-device-execution-plan.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/formal-contract-migration-execution-plan.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/preview-bundle-parquet-reuse-note.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/registry-v1-schema-memo.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/snapshot-materialization-benchmark-readiness.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/snapshot-materialization-decision-memo.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/snapshot-materialization-implementation-notes.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/test-suite-runtime-investigation.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/upload-benchmark-console-capture.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/upload-benchmark-gateway2-large-pairs-runbook.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/upload-benchmark-gateway2-runbook.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/notes/upload-performance-optimization-roadmap.md` | none | `implementation_note` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/adr/0006-language-neutral-fixture-oracle.md` | replacement ADR listed in formal README (0006) | `superseded_adr` | `retain_in_place` | no |
| `docs/backend-vnext/refactoring/formal/adr/0007-vnext-performance-baseline-authority.md` | replacement ADR listed in formal README (0007) | `superseded_adr` | `retain_in_place` | no |
| `docs/backend-vnext/refactoring/formal/adr/0008-generic-dual-store-and-caller-selected-rigor.md` | replacement ADR listed in formal README (0008) | `superseded_adr` | `retain_in_place` | no |
| `docs/backend-vnext/refactoring/formal/adr/0011-artifact-directory-broker-reclaim.md` | replacement ADR listed in formal README (0011) | `superseded_adr` | `retain_in_place` | no |
| `docs/backend-vnext/refactoring/formal/contracts/canonical-encoding-normative-vector-schema.md` | ADR 0010 + fixture-oracle contract (replacement) | `superseded_contract` | `retain_in_place` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-execution-plan.md` | owning contract/ADR/S11 handoff | `completed_execution_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md` | Repository Service Contract / ADR 0009 / ADR 0013 as applicable | `completed_p2_design` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r5-commit-pinned-read-execution-plan.md` | S11 handoff (P2 complete authority); R5 plan is ancestor exit | `completed_execution_plan` | `must_retain_source_pointer` | yes |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-ext-w1-enum-set-import-design.md` | Repository Service Contract / ADR 0009 / ADR 0013 as applicable | `completed_p2_design` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md` | owning contract/ADR/S11 handoff | `completed_execution_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md` | owning contract/ADR/S11 handoff | `completed_execution_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md` | Repository Service Contract / ADR 0009 / ADR 0013 as applicable | `completed_p2_design` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md` | owning contract/ADR/S11 handoff | `completed_execution_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s11-build-context-external-provenance-handoff-execution-plan.md` | owning contract/ADR/S11 handoff | `completed_execution_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s7-compose-lifecycle-design.md` | Repository Service Contract / ADR 0009 / ADR 0013 as applicable | `completed_p2_design` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md` | owning contract/ADR/S11 handoff | `completed_execution_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s8-full-regression-design.md` | Repository Service Contract / ADR 0009 / ADR 0013 as applicable | `completed_p2_design` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s8-full-regression-execution-plan.md` | owning contract/ADR/S11 handoff | `completed_execution_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s9-final-candidate-seal-design.md` | Repository Service Contract / ADR 0009 / ADR 0013 as applicable | `completed_p2_design` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md` | owning contract/ADR/S11 handoff | `completed_execution_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-versioned-repository-execution-checklist.md` | owning contract/ADR/S11 handoff | `completed_execution_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/p2-versioned-repository-implementation-design.md` | Repository Service Contract / ADR 0009 / ADR 0013 as applicable | `completed_p2_design` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/phase-1-implementation-design-and-delivery-plan.md` | formal README already labels 历史设计 | `historical_phase1_design` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/phase-2-implementation-design-and-delivery-plan.md` | Repository Service Contract / ADR 0009 / ADR 0013 as applicable | `completed_p2_design` | `archive` | no |
| `docs/backend-vnext/refactoring/formal/plans/s02-code-cleanup-execution-checklist.md` | owning contract/ADR/S11 handoff | `completed_execution_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/README.md` | none (temporary index) | `temporary_index` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/all-documentation-lifecycle-cleanup-execution-plan.md` | this cleanup plan | `cleanup_process` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/architecture-simplification-execution-plan.md` | ADR 0009 / DX plan / S02 checklist | `stale_active_process_plan` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/docs-lifecycle-cleanup-c0-inventory.json` | this cleanup plan | `cleanup_process` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/docs-lifecycle-cleanup-c0-inventory.md` | this cleanup plan | `cleanup_process` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-a-entry-reconciliation.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-freeze.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-review-2.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-c-parser-model.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-d-arrow-provider-verification.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-e-implementation-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-f-five-fixture-packages.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-g-production-validator.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-h-validator-gate-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-i-concurrency-matrix.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-i-s6-capacity.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-i-w2.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-j-final-image-lifecycle.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-audit-adapter-review-rerun-2.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-audit-adapter-review-rerun.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-audit-adapter-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-design-review-rerun.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-design-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-final-gate-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-0-entry-preflight-attempt-1.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-0-entry-preflight.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-2-audit-adapter-attempt-1.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-2-audit-adapter-attempt-2.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-2-audit-adapter.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-4-final-artifacts.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-5-no-ignore-compose.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-6-w1-w2-production-repeat-attempt-1.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-6-w1-w2-production-repeat.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-7-w0-smoke.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-8-v8-formal.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-9-final-packet.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-handoff-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-step-0-entry-reconciliation.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-step-1-provenance-packet.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-step-2-documentation-boundary.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-step-4-post-commit.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-step-4-precommit-checks.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s3-step-e-container-gate.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s4-step-e-container-gate.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s5-step-e-container-gate.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s6-entry-readiness.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-1-design-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-10-blocker-repair.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-10-lifecycle-rereview.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-10-lifecycle-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-4-harness-final-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-4-harness-rereview.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-4-harness-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-5-provisional-image.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-6-import-restart-replay.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-7-pinned-read.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-9-restored-lifecycle.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-design-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-implementation-rereview.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-implementation-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-0-entry-reconciliation.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-2-classification-and-static.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-2-classification-repair.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-3-worker-convergence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-4-source-full-regression-rerun.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-4-source-full-regression.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-hygiene-and-candidate-preparation.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-hygiene-rerun.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-candidate-seal-review-rerun.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-candidate-seal-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-design-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-0-entry-preflight.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-2-provisional-image.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-3-no-ignore-regression.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-candidate-seal-packet.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/p2-r9-s2-cooperative-cleanup-simplification-plan.md` | ADR 0012 + Repository Service Contract | `stale_pending_implementation_guide` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-0/baseline-and-oracle-notes.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1-environment-execution-ledger.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/executable-contracts-and-walking-skeleton-notes.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/implementation-design-and-delivery-plan-notes.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/phase-1-closure-signoff.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp0-dependency-inventory.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r1-dependency-inventory.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r2-dependency-inventory.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r3-3a-dependency-inventory.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r3-3b-dependency-inventory.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r4-dependency-inventory.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r5-dependency-inventory.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r6-normative-publication.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r7-repository-consumer.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r1-arrow-pyo3-design.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r2-rust-core-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r3-pyo3-adapter-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r4-kernel-component-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r5-dependency-inventory.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r5-kernel-native-signoff.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-wp5-checkout-plan.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp4-r1-artifact-api-design.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp4-r1-artifact-api-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp4-r2-artifact-round-trip-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp4-r3-ipc-negative-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp4-r4-artifact-path-closure.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r1-scenario-schema-closure-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r2-runner-lifecycle-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r3-canonical-row-hash-scenario-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r4-profile-matrix-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r5-phase1-exit-evidence.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/README.md` | none (temporary index) | `temporary_index` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/bounded-phase-3-consumer-adequacy-check.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/caller-responsibility-scan-round-0-to-6.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/consolidated-design-review.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/decision-ledger-round-0-to-3.md` | ADR 0009 + Repository Service Contract (replacement) | `superseded_interview_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/decision-ledger-round-4-to-7.md` | ADR 0009 + Repository Service Contract (replacement) | `superseded_interview_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/decision-ledger-round-8-to-11.md` | ADR 0009 + Repository Service Contract (replacement) | `superseded_interview_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/interactive-design-session-guide.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/p2-r3-implementation-task-prompts.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/p2-r3-synchronous-create-upload-execution-plan.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s3-staged-execution-guide.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s4-staged-execution-guide.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s5-staged-execution-guide.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/round-11-convergence-readiness-scan.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/phase-2/t2-simplification-implementation-checklist.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/refactoring/temporary/project-environment-preparation.md` | none (temporary execution record) | `temporary_execution_record` | `archive` | no |
| `docs/backend-vnext/repository-import-benchmark-runbook.md` | Performance measurement contract | `benchmark_runbook` | `archive` | no |
| `vnext/deploy/p2r1-cache/README.md` | S10/S11 image provenance (not this file) | `stale_deploy_runbook` | `leave_in_vnext` | yes |

### `REDUNDANT` (1)

| 路径 | owner | role | C4 | vnext/test |
| --- | --- | --- | --- | --- |
| `vnext/backend/README.md` | none | `empty_package_readme` | `leave_in_vnext` | no |

## C1 exit

```yaml
c1_status: complete
c1_continue_plan: yes
confirmed_normative: 26
confirmed_active_interface: 43
confirmed_evidence: 63
confirmed_historical: 169
confirmed_redundant: 1
confirmed_escalate: 0
unresolved_escalations: 0
next: C2
```


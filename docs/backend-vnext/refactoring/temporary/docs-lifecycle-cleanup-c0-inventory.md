# Documentation Lifecycle Cleanup — C0 Freeze and Inventory

状态：`complete`（`c0_continue_plan: yes`；preliminary classification only）

日期：2026-08-17

本记录只冻结当前文档 worktree / candidate / image 身份，并用 `git ls-files` 枚举文档。没有修改 `vnext/**`、Dockerfile、Compose、lockfile、entrypoint 或 candidate checkout，没有创建 git tag，没有重跑测试或重建 image。初步分类供 C1 确认，不是最终 authority。

权威计划：[Documentation Lifecycle and Active-Context Cleanup Execution Plan](all-documentation-lifecycle-cleanup-execution-plan.md) §5 C0
机器可读清单：[docs-lifecycle-cleanup-c0-inventory.json](docs-lifecycle-cleanup-c0-inventory.json)
上游 P2 身份：[p2-external-interface-handoff.md](../formal/plans/p2-external-interface-handoff.md)

## Freeze identity

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 1420eaddaffb506d6c209862b9daeb510b7fc230
documentation_head_role: docs_only_not_image_input
documentation_head_subject: 'docs(repository): record S11-4 post-commit Phase 2 decision'
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_is_ancestor: yes
candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_worktree_head: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_worktree_clean: yes
post_candidate_committed_delta: docs-only
vnext_delta_vs_candidate: empty
production_code_dirty: no
service_image: gateway-repository-service:p2-r6-final
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
image_identity_source: S11 final handoff; local docker inspect unavailable
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
provenance_documentation_sha: bb00f9386cc4e0763040ee436c0132224d45323d
phase_2_complete: yes
proposed_pre_cleanup_tag: docs/p2-p3-cleanup-pre-20260817
pre_cleanup_tag_exists: no
pre_cleanup_tag_create_gate: C3
c0_artifacts_in_freeze_head: no
```

`git worktree list`：

```text
/root/gateway-data-management-system 1420eadd [phase1/gate-ownership-repair]
/root/gateway-s9-candidate-2ef88427  2ef88427 (detached HEAD)
```

文档 worktree `git status --porcelain=v1`（C0 开始时，不含本 inventory 产物）：

```text
 M docs/backend-vnext/refactoring/temporary/README.md
?? docs/backend-vnext/refactoring/temporary/all-documentation-lifecycle-cleanup-execution-plan.md
```

脏文件全部位于 `docs/`，是本清理计划及其 temporary README 索引。这不构成 source/build/deployment delta。

## Stop conditions

| 条件 | 结果 |
| --- | --- |
| source/build/deployment delta vs candidate `2ef88427` | 无；`git diff --name-status candidate..HEAD -- vnext` 为空 |
| 非 docs 的已跟踪/未跟踪脏文件 | 无 |
| candidate detached worktree 干净且 HEAD 匹配 | 是 |
| 提议的 pre-cleanup tag `docs/p2-p3-cleanup-pre-20260817` 已存在 | 否；C3 再创建 |
| 继续本计划 | **yes** |

本机没有 S11 记录的 image ID。C0 不重建、不 retag image；身份以 S11 handoff 为准。本 inventory 与后续 C1/C2 文档不是 `validated_code_sha` 或 image input。

## Coverage

- tracked documentation files (`git ls-files`): **299**
- untracked in-scope files: **1**
- inventory rows: **300**
- RST files: **0**
- 范围：`docs/**` 的 Markdown/JSON/YAML/TXT、仓库根 `AGENTS.md`、以及 `vnext/**/README.md`
- 未把 `vnext/**` 源码、OpenAPI 生成器、lockfile 或 fixture payload 当作文档行

缺失但被 P3 active-context 点名的入口：

- `vnext/repository_client/README.md` — 不存在。C2 若补 README，写入 `vnext/` 会触发 source delta，必须停止本计划并回到 owning stage。
- `vnext/repository_contracts/README.md` — 不存在。

## Preliminary classification counts

| 分类 | 数量 |
| --- | --- |
| `NORMATIVE` | 25 |
| `ACTIVE_INTERFACE` | 9 |
| `EVIDENCE` | 62 |
| `HISTORICAL` | 154 |
| `REDUNDANT` | 1 |
| `ESCALATE` | 49 |

分类是路径启发式，不是 C1 结论。同一文件只标一个主分类。`vnext/**/README.md` 列入 inventory，但带 `cleanup_must_not_modify`：它们在 candidate source digest 内。

链接图只统计 Markdown `[text](url)` / reference-style 定义，以及 JSON/YAML 中的文档路径字符串。大量索引（尤其 `docs/backend-vnext/README.md`）用反引号路径而不是链接，因此 `incoming=0` **不能**当成无 consumer。C1 必须以引用检索为准，不能只看本表 in/out。

## C1 watchlist

C0 已看到、必须由 C1 确认的事项：

1. `vnext/repository_service/README.md` 仍写 P2-R5 functional exit / `phase_2_complete=no`；S11 已 `phase_2_complete: yes`。本计划不得改 `vnext/`。
2. `docs/backend-vnext/refactoring/formal/README.md` 在声明 S11 完成后，仍把「完整handoff」链到 P2-R5-S7。
3. `docs/backend-vnext/contracts/` 与 `refactoring/formal/contracts/` 两套 contract 树并存。
4. `docs/backend-vnext/adr/` 与 `refactoring/formal/adr/` 两套 ADR 树并存。
5. `docs/backend-vnext/capabilities/`、`flows.md`、`operations.md` 等可能仍是 P3 业务设计输入。
6. `temporary/phase-2/decision-ledger-round-*.md` 是否还有未 formalize 的条款。
7. `architecture-simplification-execution-plan.md` 仍为 Active，但 Phase 2 已 complete。
8. `p2-r9-s2-*` 仍为 implementation pending，与已封印的 P2-R6 不是同一轮。
9. 缺失 Client README；补文件若落在 `vnext/` 则超出本计划。
10. 被替代的 formal ADR 0006/0007/0008/0011 与 superseded vector-schema contract 的残留引用。

启发式 flag 计数：

| flag | 数量 |
| --- | --- |
| `active_index` | 3 |
| `cleanup_must_not_modify` | 6 |
| `completed_stage_process_doc` | 10 |
| `empty_file` | 1 |
| `formal_readme_marks_superseded` | 4 |
| `implementation_pending` | 2 |
| `in_candidate_source_tree` | 6 |
| `legacy_adr_tree` | 3 |
| `legacy_contract_tree` | 10 |
| `marked_superseded` | 1 |
| `may_still_be_p3_design_input` | 8 |
| `not_p2_r6_sealed_round` | 2 |
| `p2_final_evidence` | 2 |
| `p3_business_capability_candidate` | 14 |
| `phase_2_already_complete` | 1 |
| `stale_p2r5_status` | 1 |
| `stale_pre_s11_status` | 2 |
| `status_may_predate_p2_complete` | 5 |
| `status_still_active` | 1 |
| `still_linked_from_formal_index` | 3 |
| `temporary_index` | 2 |
| `this_cleanup_plan` | 1 |
| `unformalized_decision_ledger` | 3 |

含 unresolved 文档链接的文件：14（C5 再验收，C0 不断言 broken_links=0）

## ESCALATE files

| 路径 | 状态字段 | 理由 | flags |
| --- | --- | --- | --- |
| `docs/backend-vnext/adr/0001-snapshot-table-and-dolt-import-boundary.md` |  | Pre-refactor ADR tree vs formal/adr. | legacy_adr_tree |
| `docs/backend-vnext/adr/0002-comparison-hash-sqlite-mode-selection.md` |  | Pre-refactor ADR tree vs formal/adr. | legacy_adr_tree |
| `docs/backend-vnext/adr/0003-dolt-native-provider-selection.md` |  | Pre-refactor ADR tree vs formal/adr. | legacy_adr_tree |
| `docs/backend-vnext/artifacts.md` |  | Artifact taxonomy vs ADR 0004 and canonical storage contract. |  |
| `docs/backend-vnext/capabilities/bundle-assembly.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/business-projection.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/comparison-compute.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/composite-signal-device.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/dolt-native-provider.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/ordered-diff-compute.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/project-identity-and-dataset-replacement.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/repository-import.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/repository-ref-materialization.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/risk-evaluation.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/snapshot-materialization.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/surface-assembly.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/table-presentation-large-data-report.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/capabilities/table-presentation.md` |  | Capability design; possible P3 input. Confirm vs formal contracts. | p3_business_capability_candidate |
| `docs/backend-vnext/contracts/comparison-bundle.md` |  | Pre-refactor contract tree; formal README treats as oracle until replaced. | legacy_contract_tree |
| `docs/backend-vnext/contracts/comparison-surface.md` |  | Pre-refactor contract tree; formal README treats as oracle until replaced. | legacy_contract_tree |
| `docs/backend-vnext/contracts/comparison.md` |  | Pre-refactor contract tree; formal README treats as oracle until replaced. | legacy_contract_tree |
| `docs/backend-vnext/contracts/ordered-diff.md` |  | Pre-refactor contract tree; formal README treats as oracle until replaced. | legacy_contract_tree |
| `docs/backend-vnext/contracts/risk.md` |  | Pre-refactor contract tree; formal README treats as oracle until replaced. | legacy_contract_tree |
| `docs/backend-vnext/contracts/snapshot-table-access.md` |  | Pre-refactor contract tree; formal README treats as oracle until replaced. | legacy_contract_tree |
| `docs/backend-vnext/contracts/snapshot.md` |  | Pre-refactor contract tree; formal README treats as oracle until replaced. | legacy_contract_tree |
| `docs/backend-vnext/contracts/source-package-and-snapshot.md` |  | Pre-refactor contract tree; formal README treats as oracle until replaced. | legacy_contract_tree |
| `docs/backend-vnext/contracts/source-package.md` |  | Pre-refactor contract tree; formal README treats as oracle until replaced. | legacy_contract_tree |
| `docs/backend-vnext/contracts/table-presentation.md` |  | Pre-refactor contract tree; formal README treats as oracle until replaced. | legacy_contract_tree |
| `docs/backend-vnext/flows.md` |  | Business flows; possible P3 input overlapping later contracts. |  |
| `docs/backend-vnext/frontend-surface-simplification.md` |  | Frontend surface strategy; possible P3 input. |  |
| `docs/backend-vnext/identity-and-digests.md` |  | Identity/digest design vs formal encoding/storage contracts. |  |
| `docs/backend-vnext/implementation-boundary.md` |  | Implementation boundary may predate independent-container P3 assumption. |  |
| `docs/backend-vnext/modules.md` |  | Target module map; C1 confirm vs architecture plan. |  |
| `docs/backend-vnext/operations.md` |  | Operation runtime design; may overlap formal effect/recovery contract. |  |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md` | Accepted; v8 formal decision approved; P2-R2 authorized | Formal plan with unclear remaining authority. |  |
| `docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md` | Accepted — S10 Closure Ready | Formal design document; C1 decide remaining P3 authority vs history. | may_still_be_p3_design_input |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-ext-w1-enum-set-import-design.md` | Frozen（独立 Contract review 通过；允许进入 Stage C） | Formal design document; C1 decide remaining P3 authority vs history. | may_still_be_p3_design_input |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md` | Design baseline frozen by discussion; independent design review required | Formal design document; C1 decide remaining P3 authority vs history. | may_still_be_p3_design_input |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s7-compose-lifecycle-design.md` | Design baseline frozen by discussion; independent review required before implementation | Formal design document; C1 decide remaining P3 authority vs history. | may_still_be_p3_design_input |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s8-full-regression-design.md` | Design baseline frozen by discussion; independent design review required before implementation | Formal design document; C1 decide remaining P3 authority vs history. | may_still_be_p3_design_input |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s9-final-candidate-seal-design.md` | Design baseline frozen by discussion; independent design review required | Formal design document; C1 decide remaining P3 authority vs history. | may_still_be_p3_design_input |
| `docs/backend-vnext/refactoring/formal/plans/p2-versioned-repository-implementation-design.md` | Accepted — P2-R6-S0 design freeze complete, S1 ready | Formal design document; C1 decide remaining P3 authority vs history. | may_still_be_p3_design_input |
| `docs/backend-vnext/refactoring/formal/plans/phase-2-implementation-design-and-delivery-plan.md` | Accepted — Complete P2 Design | Formal design document; C1 decide remaining P3 authority vs history. | may_still_be_p3_design_input |
| `docs/backend-vnext/refactoring/temporary/architecture-simplification-execution-plan.md` | Active / Design Before Combined Code Cleanup | Still marked Active after phase_2_complete; C1 archive vs leftover work. | status_still_active,phase_2_already_complete |
| `docs/backend-vnext/refactoring/temporary/p2-r9-s2-cooperative-cleanup-simplification-plan.md` | Temporary execution guide — implementation pending | Temporary R9 cleanup guide still pending; confirm owner and whether it is in-scope leftover or a later implementation track. | implementation_pending,not_p2_r6_sealed_round |
| `docs/backend-vnext/refactoring/temporary/p2-r9-s2-step-e-container-gate.md` | Executed | Temporary R9 cleanup guide still pending; confirm owner and whether it is in-scope leftover or a later implementation track. | implementation_pending,not_p2_r6_sealed_round |
| `docs/backend-vnext/refactoring/temporary/phase-2/decision-ledger-round-0-to-3.md` | **Draft / Active Interview Record** | Decision ledger; C1 check remaining unformalized clauses. | unformalized_decision_ledger |
| `docs/backend-vnext/refactoring/temporary/phase-2/decision-ledger-round-4-to-7.md` | **Draft / Active Interview Record** | Decision ledger; C1 check remaining unformalized clauses. | unformalized_decision_ledger |
| `docs/backend-vnext/refactoring/temporary/phase-2/decision-ledger-round-8-to-11.md` | **Draft / Active Interview Record** | Decision ledger; C1 check remaining unformalized clauses. | unformalized_decision_ledger |

## Inventory by class

完整 outgoing/incoming 链接见 JSON。下表是 C0 枚举面。

### `NORMATIVE` (25)

| 路径 | bytes | last commit | 状态字段 | in | out | unresolved |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `docs/backend-vnext/refactoring/formal/adr/0001-python-rust-hybrid-compute-strategy.md` | 12004 | `fc6a0c9c` | Accepted | 9 | 8 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0002-minimal-persisted-business-state.md` | 2374 | `28732db0` | Accepted | 4 | 1 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0003-external-effect-reconciliation.md` | 2915 | `c253d699` | Accepted | 7 | 1 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0004-raw-source-artifact-and-canonical-dolt-storage.md` | 3517 | `c253d699` | Accepted | 4 | 1 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0005-shared-canonical-encoding.md` | 2683 | `fc6a0c9c` | Accepted | 5 | 2 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0009-proportional-assurance-and-trusted-internal-repository.md` | 12158 | `d46500da` | Accepted | 16 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0010-minimal-golden-and-ordinary-ci.md` | 8560 | `fc6a0c9c` | Accepted | 19 | 2 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md` | 8131 | `c6369a3b` | Accepted | 11 | 5 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md` | 5676 | `d03e8e94` | Accepted（独立 Contract review 通过；允许进入 Stage C） | 14 | 8 | 0 |
| `docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md` | 33331 | `d46500da` | 正式设计基线（Accepted Baseline） | 10 | 21 | 0 |
| `docs/backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md` | 8347 | `c253d699` | 正式设计（Accepted） | 6 | 6 | 0 |
| `docs/backend-vnext/refactoring/formal/contracts/canonical-row-hash-compute-boundary.md` | 12977 | `d03e8e94` | 正式设计（Accepted） | 15 | 4 | 0 |
| `docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md` | 14048 | `d03e8e94` | 正式设计（Accepted） | 16 | 9 | 0 |
| `docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md` | 26303 | `d46500da` | 正式设计（Accepted） | 8 | 5 | 0 |
| `docs/backend-vnext/refactoring/formal/contracts/external-effect-and-recovery.md` | 7775 | `b06ce5b1` | 正式设计（Accepted） | 12 | 8 | 0 |
| `docs/backend-vnext/refactoring/formal/contracts/fixture-oracle-and-conformance.md` | 7223 | `d03e8e94` | 正式设计（Accepted Simplified Baseline） | 18 | 6 | 0 |
| `docs/backend-vnext/refactoring/formal/contracts/performance-measurement-and-baseline.md` | 4575 | `fc6a0c9c` | 正式设计（Accepted Simplified Baseline） | 9 | 4 | 0 |
| `docs/backend-vnext/refactoring/formal/contracts/repository-service.md` | 39618 | `d03e8e94` | Accepted Simplified Baseline | 40 | 9 | 0 |
| `docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md` | 16579 | `d03e8e94` | 正式设计（Accepted） | 23 | 9 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/dx-cross-phase-interface-reconciliation.md` | 12110 | `c253d699` | Accepted — DX Complete | 10 | 6 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/implementation-stages.md` | 45294 | `d46500da` | 正式设计基线（Accepted Baseline） | 16 | 18 | 0 |
| `docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md` | 11273 | `d46500da` | 正式跨阶段政策（Accepted） | 11 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/policies/rust-safety-and-performance-policy.md` | 5337 | `fc6a0c9c` | 正式设计（Accepted Simplified Baseline） | 10 | 4 | 0 |
| `docs/backend-vnext/testing-conventions.md` | 14281 | `1bfa1d7f` | 2026-08-07 建立；2026-08-09 增补P2后半段container gate合并规则； | 12 | 5 | 0 |
| `docs/backend-vnext/testing-fixtures.md` | 2063 | `aa33d116` | 已按简化后的 Phase 0–1 formal contract 更新 | 1 | 4 | 0 |

### `ACTIVE_INTERFACE` (9)

| 路径 | bytes | last commit | 状态字段 | in | out | unresolved |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `AGENTS.md` | 6708 | `d46500da` |  | 0 | 3 | 0 |
| `docs/backend-vnext/README.md` | 9169 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/glossary.md` | 30870 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/README.md` | 3118 | `dbddfc25` |  | 0 | 21 | 0 |
| `docs/backend-vnext/refactoring/formal/README.md` | 8208 | `bb00f938` |  | 1 | 49 | 0 |
| `vnext/fixtures/vectors/compute/canonical-row-hash/v1/README.md` | 1904 | `b9c47256` |  | 0 | 0 | 0 |
| `vnext/fixtures/vectors/repository/sql-enum-set/v1/README.md` | 2455 | `02502f9a` |  | 0 | 4 | 0 |
| `vnext/repository_service/README.md` | 18778 | `2264ecc7` |  | 0 | 3 | 0 |
| `vnext/shared_kernel/README.md` | 363 | `3d20dd44` |  | 0 | 0 | 0 |

### `EVIDENCE` (62)

| 路径 | bytes | last commit | 状态字段 | in | out | unresolved |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `docs/backend-vnext/dolt-test/dolt-import-provider-functional-test-result-2026-06-20.md` | 6690 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/dolt-test/dolt-native-diff-functional-test-result-2026-06-21.md` | 45293 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-audit-correction-2026-08-02.md` | 12281 | `ce9e6e96` | 薄复审通过，formal exit 保持 `no-go`；未选择 provider，未进入 P2-R2 | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/a-paired/a-devnull.md` | 734 | `09099e13` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/a-paired/a-devnull.summary.json` | 5160 | `09099e13` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/a-paired/a-paired-review-summary.md` | 16415 | `09099e13` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/b-restart/b-restart.md` | 734 | `09099e13` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/b-restart/b-restart.summary.json` | 4938 | `09099e13` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-diagnostics-50f05cf-2026-08-04/paired-analysis.md` | 18931 | `09099e13` |  | 0 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-19fb10f-failure-analysis-2026-08-04.json` | 471380 | `49687073` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-19fb10f-run-report-2026-08-04.md` | 759 | `49687073` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-19fb10f-summary-2026-08-04.json` | 5985 | `49687073` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-80858ca-2026-08-04/p2-r1.md` | 758 | `19ed70d7` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-80858ca-2026-08-04/p2-r1.summary.json` | 5956 | `19ed70d7` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-formal-rerun-80858ca-2026-08-04/review-summary.md` | 7129 | `19ed70d7` |  | 0 | 2 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-no-go-decision-2026-08-04.md` | 6548 | `969b3691` |  | 1 | 4 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-provider-decision-2026-08-02.md` | 10468 | `096f052b` |  | 0 | 2 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-provider-summary-2026-08-02.json` | 1514 | `3fe59f0f` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-target-image-summary-2026-08-02.json` | 1514 | `096f052b` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-authority-and-implementation-brief.md` | 18801 | `969b3691` | 审核通过的 v8 实现基线；formal decision 已完成并纳入 authority。 | 3 | 1 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-formal-80aff3e-2026-08-05/README.md` | 3796 | `67a0d053` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-formal-80aff3e-2026-08-05/p2-r1-v8.md` | 656 | `d7a0aa7a` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-formal-80aff3e-2026-08-05/p2-r1-v8.summary.json` | 10334 | `d7a0aa7a` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-go-decision-2026-08-05.md` | 3169 | `969b3691` | Accepted — v8 formal decision approved | 6 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-00232da-2026-08-05/README.md` | 1211 | `d4490fb9` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-00232da-2026-08-05/v8-smoke-00232da-a2/a-w0.md` | 730 | `d4490fb9` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-00232da-2026-08-05/v8-smoke-00232da-a2/a-w0.summary.json` | 4606 | `d4490fb9` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-00232da-2026-08-05/v8-smoke-00232da-b/b-w0.md` | 631 | `d4490fb9` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-00232da-2026-08-05/v8-smoke-00232da-b/b-w0.summary.json` | 478 | `d4490fb9` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-36f8c2f-2026-08-05/README.md` | 1354 | `6c80143b` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-36f8c2f-2026-08-05/v8-smoke-36f8c2f-a/a-w0.md` | 640 | `6c80143b` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-36f8c2f-2026-08-05/v8-smoke-36f8c2f-a/a-w0.summary.json` | 3788 | `6c80143b` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-36f8c2f-2026-08-05/v8-smoke-36f8c2f-b/b-w0.md` | 631 | `6c80143b` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-36f8c2f-2026-08-05/v8-smoke-36f8c2f-b/b-w0.summary.json` | 478 | `6c80143b` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-80aff3e-2026-08-05/README.md` | 3433 | `fb692167` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-80aff3e-2026-08-05/v8-smoke-80aff3e-a/a-w0.md` | 478 | `fb692167` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-80aff3e-2026-08-05/v8-smoke-80aff3e-a/a-w0.summary.json` | 2976 | `fb692167` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-80aff3e-2026-08-05/v8-smoke-80aff3e-b/b-w0.md` | 409 | `fb692167` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-v8-smokes-80aff3e-2026-08-05/v8-smoke-80aff3e-b/b-w0.summary.json` | 504 | `fb692167` |  | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-external-descriptor.yaml` | 2682 | `0b4969fe` |  | 3 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-k-final-handoff.md` | 5305 | `0b4969fe` | pass | 6 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-final-handoff.md` | 18846 | `a72227ae` | pass | 6 | 21 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-final-handoff.md` | 8603 | `bb00f938` | pass`（`S11_exit: pass`；`phase_2_complete: yes`） | 6 | 8 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-lineage-inventory.json` | 19379 | `bb00f938` |  | 4 | 0 | 18 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-final-handoff.md` | 13961 | `1bfa1d7f` | pass | 11 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-final-handoff.md` | 13099 | `71da5061` | pass | 6 | 22 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw-rerun/g1-verification-level.txt` | 22459 | `2ef88427` |  | 2 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw-rerun/g2-effect-state.txt` | 37500 | `2ef88427` |  | 2 | 2 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw-rerun/g3-cas-store.txt` | 93224 | `2ef88427` |  | 2 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw-rerun/g4-path-version.txt` | 73385 | `2ef88427` |  | 2 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw-rerun/g5-wire-readback.txt` | 2104 | `2ef88427` |  | 2 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw/g1-verification-level.txt` | 8810 | `6ddd94d7` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw/g2-effect-state.txt` | 15511 | `6ddd94d7` |  | 1 | 2 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw/g3-cas-store.txt` | 38370 | `6ddd94d7` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw/g4-path-version.txt` | 27602 | `6ddd94d7` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-old-reference-raw/g5-wire-readback.txt` | 620 | `6ddd94d7` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-final-handoff.md` | 15035 | `21c99ef3` | pass | 7 | 18 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-old-reference-raw/g1-verification-level.txt` | 192356 | `21c99ef3` |  | 2 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-old-reference-raw/g2-effect-state.txt` | 257452 | `21c99ef3` |  | 2 | 2 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-old-reference-raw/g3-cas-store.txt` | 673842 | `21c99ef3` |  | 2 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-old-reference-raw/g4-path-version.txt` | 315690 | `21c99ef3` |  | 2 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-old-reference-raw/g5-wire-readback.txt` | 5830 | `21c99ef3` |  | 2 | 0 | 0 |

### `HISTORICAL` (154)

| 路径 | bytes | last commit | 状态字段 | in | out | unresolved |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `docs/backend-vnext/implementation-plan.md` | 26265 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/archive-parity-audit.md` | 29936 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/cache-contract-cleanup-execution-plan.md` | 7937 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/comparison-bundle-formal-contract-scheme.md` | 9807 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/comparison-bundle-migration-execution-plan.md` | 21410 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/comparison-bundle-oracle-audit.md` | 21874 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/composite-signal-device-execution-plan.md` | 6858 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/formal-contract-migration-execution-plan.md` | 191196 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/preview-bundle-parquet-reuse-note.md` | 1371 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/registry-v1-schema-memo.md` | 3972 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/snapshot-materialization-benchmark-readiness.md` | 17227 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/snapshot-materialization-decision-memo.md` | 19028 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/snapshot-materialization-implementation-notes.md` | 10493 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/test-suite-runtime-investigation.md` | 10784 | `aa33d116` |  | 1 | 1 | 0 |
| `docs/backend-vnext/notes/upload-benchmark-console-capture.md` | 3627 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/notes/upload-benchmark-gateway2-large-pairs-runbook.md` | 3298 | `6121f612` |  | 1 | 1 | 0 |
| `docs/backend-vnext/notes/upload-benchmark-gateway2-runbook.md` | 8270 | `6121f612` |  | 2 | 0 | 0 |
| `docs/backend-vnext/notes/upload-performance-optimization-roadmap.md` | 25807 | `6121f612` |  | 0 | 2 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0006-language-neutral-fixture-oracle.md` | 2736 | `fc6a0c9c` | Superseded by ADR 0010 | 5 | 2 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0007-vnext-performance-baseline-authority.md` | 2888 | `fc6a0c9c` | Superseded by ADR 0010 | 3 | 2 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0008-generic-dual-store-and-caller-selected-rigor.md` | 3225 | `f7c3678a` | Superseded after WP1-R1 checkpoint by | 3 | 2 | 0 |
| `docs/backend-vnext/refactoring/formal/adr/0011-artifact-directory-broker-reclaim.md` | 4740 | `c6369a3b` | Superseded by [ADR 0012](../formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md) | 2 | 4 | 0 |
| `docs/backend-vnext/refactoring/formal/contracts/canonical-encoding-normative-vector-schema.md` | 1310 | `fc6a0c9c` | Superseded by | 6 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-execution-plan.md` | 147814 | `f346ef94` | Accepted — Ready for staged implementation | 5 | 2 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r5-commit-pinned-read-execution-plan.md` | 51098 | `1fc69258` | Accepted — P2-R5 functional exit complete, P2-R6 ready | 8 | 4 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md` | 19990 | `0b4969fe` | Stage K complete; R6-EXT-W1 handoff pass; phase_2_complete = no | 16 | 15 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md` | 49088 | `bb00f938` | Accepted — P2-R6-S0 design freeze complete；2026-08-13按ADR 0012修订cleanup私有协议 | 26 | 18 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md` | 26474 | `0f9536c2` | Ready for independent design review | 22 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s11-build-context-external-provenance-handoff-execution-plan.md` | 12882 | `bb00f938` | S11 complete; S11_exit: pass; phase_2_complete = yes | 9 | 2 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md` | 22586 | `34801a16` | Ready for independent design review | 11 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s8-full-regression-execution-plan.md` | 18708 | `77a43ebe` | Ready for independent design review | 12 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md` | 17872 | `21c99ef3` | Ready for independent design review | 10 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-versioned-repository-execution-checklist.md` | 23302 | `24f7a374` | Accepted | 16 | 6 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/phase-1-implementation-design-and-delivery-plan.md` | 19831 | `fc6a0c9c` | Historical — superseded by ADR 0010 | 6 | 7 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/s02-code-cleanup-execution-checklist.md` | 6990 | `66b6793a` | Completed | 3 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/README.md` | 2011 | `f7c3678a` |  | 1 | 7 | 0 |
| `docs/backend-vnext/refactoring/temporary/all-documentation-lifecycle-cleanup-execution-plan.md` | 9182 | `untracke` | Draft / Ready for inventory review | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-a-entry-reconciliation.md` | 10938 | `2fe7b1fe` | complete | 1 | 2 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-freeze.md` | 6121 | `d03e8e94` | review_pass | 4 | 10 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-review-2.md` | 7758 | `d03e8e94` | pass | 2 | 8 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-review.md` | 9167 | `d03e8e94` | fail | 3 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-c-parser-model.md` | 3483 | `8425c41b` | complete | 2 | 4 | 1 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-d-arrow-provider-verification.md` | 3518 | `02502f9a` | complete | 2 | 4 | 2 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-e-implementation-review.md` | 9128 | `02502f9a` | pass | 2 | 6 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-f-five-fixture-packages.md` | 6540 | `b1192213` | complete | 4 | 3 | 4 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-g-production-validator.md` | 6619 | `7f068a24` | complete | 3 | 3 | 1 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-h-validator-gate-review.md` | 8771 | `108cb90d` | pass | 3 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-i-concurrency-matrix.md` | 3955 | `656a66bf` | pass | 6 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-i-s6-capacity.md` | 5739 | `656a66bf` | pass | 9 | 5 | 2 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-i-w2.md` | 4138 | `656a66bf` | pass | 7 | 3 | 1 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-j-final-image-lifecycle.md` | 8285 | `352d9097` | pass | 4 | 5 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-audit-adapter-review-rerun-2.md` | 7810 | `a72227ae` | pass | 2 | 5 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-audit-adapter-review-rerun.md` | 9155 | `a72227ae` | pass | 4 | 4 | 12 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-audit-adapter-review.md` | 11356 | `a72227ae` | fail | 4 | 3 | 17 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-design-review-rerun.md` | 10570 | `a72227ae` | pass | 3 | 5 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-design-review.md` | 12144 | `0f9536c2` | fail | 3 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-final-gate-review.md` | 8490 | `a72227ae` | pass`（`finding_count: 0`；仅授权 S10-11 external seal） | 2 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-0-entry-preflight-attempt-1.md` | 24240 | `0f9536c2` | complete`（入口记录完成；`S10_entry_ready: no`） | 3 | 12 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-0-entry-preflight.md` | 9757 | `0f9536c2` | complete`（`S10_entry_ready: yes`；attempt-2 rerun after S10-1 fail） | 5 | 5 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-2-audit-adapter-attempt-1.md` | 8519 | `a72227ae` | complete`（`adapter_ready_for_independent_review: yes`；无 W1/W2 production claim） | 3 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-2-audit-adapter-attempt-2.md` | 7982 | `a72227ae` | complete`（attempt-2 after S10-3 fail；`adapter_ready_for_independent_review: yes`；无 W1/W2 production claim） | 2 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-2-audit-adapter.md` | 6068 | `a72227ae` | complete`（attempt-3 after S10-6 leftover volume；`adapter_ready_for_independent_review: yes`；无 W1/W2 production claim） | 5 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-4-final-artifacts.md` | 14540 | `a72227ae` | pass`（仅 S10-4 final artifact identity；不授予 no-ignore、W1/W2、v8、S10 exit 或 Phase 2） | 3 | 5 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-5-no-ignore-compose.md` | 15433 | `a72227ae` | pass`（仅 S10-5 no-ignore / Compose；不授予 W1/W2、v8、S10 exit 或 Phase 2） | 4 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-6-w1-w2-production-repeat-attempt-1.md` | 11581 | `a72227ae` | fail`（adapter 缺陷；attempt-1 已保全；不授予 W1/W2 production pass、v8、S10 exit 或 Phase 2） | 2 | 4 | 1 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-6-w1-w2-production-repeat.md` | 11724 | `a72227ae` | pass`（仅 S10-6 W1/W2 production repeat；attempt-2；不授予 v8、S10 exit 或 Phase 2） | 5 | 6 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-7-w0-smoke.md` | 10911 | `a72227ae` | pass`（仅 S10-7 Candidate A W0 diagnostic smoke；attempt-5；不授予 v8 formal、S10 exit 或 Phase 2） | 3 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-8-v8-formal.md` | 8298 | `a72227ae` | pass`（仅 S10-8 Candidate A 66-record v8 formal；attempt-1；不授予 S10 exit 或 Phase 2） | 2 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-9-final-packet.md` | 10358 | `a72227ae` | pass`（packet complete、hash consistent、zero owned residual；不授予 | 2 | 7 | 1 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-handoff-review.md` | 7550 | `bb00f938` | pass`（`finding_count: 0`；仅授权 S11-4 final docs-only commit） | 3 | 7 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-step-0-entry-reconciliation.md` | 11415 | `bb00f938` | complete`（`S11_entry_ready: yes`；`s11_documentation_attempt: attempt-1`） | 4 | 7 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-step-1-provenance-packet.md` | 9029 | `bb00f938` | complete`（packet assembled；`phase_2_complete: no`） | 3 | 5 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-step-2-documentation-boundary.md` | 7218 | `bb00f938` | complete`（`documentation_boundary: pass`；`phase_2_decision_ready: yes`） | 2 | 6 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-step-4-post-commit.md` | 3573 | `1420eadd` | pass`（post-commit checks pass；`phase_2_complete: yes`） | 0 | 5 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s11-step-4-precommit-checks.md` | 3417 | `bb00f938` | complete`（S11-3 `allow_phase_2_complete: yes`；pre-commit checks pass） | 2 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s3-step-e-container-gate.md` | 5024 | `f63c39df` | Executed | 2 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s4-step-e-container-gate.md` | 5447 | `c421700b` | Executed | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s5-step-e-container-gate.md` | 10054 | `b5b4cca3` | Executed | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s6-entry-readiness.md` | 8531 | `0b4969fe` | stage_k_handoff_pass | 1 | 9 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-1-design-review.md` | 8766 | `30cbd470` | pass | 1 | 5 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-10-blocker-repair.md` | 13149 | `5f474ce2` | pass`（关闭 F-001/F-002；不是 S7 四 nodeid 聚合 PASS，不授予 S7-11） | 1 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-10-lifecycle-rereview.md` | 6282 | `1bfa1d7f` | pass`（F-001/F-002 已关闭；允许进入 S7-11，不授予 S7 exit） | 3 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-10-lifecycle-review.md` | 8018 | `5f474ce2` | fail`（独立审核发现阻塞项；不授予 S7-11 final gate） | 2 | 6 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-4-harness-final-review.md` | 4445 | `0826b2da` | pass | 3 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-4-harness-rereview.md` | 5202 | `0826b2da` | fail | 0 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-4-harness-review.md` | 8089 | `0826b2da` | fail | 1 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-5-provisional-image.md` | 8285 | `0826b2da` | pass`（仅 S7-5 preflight；不授予 S7 Compose PASS 或 S7 exit） | 5 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-6-import-restart-replay.md` | 2560 | `0826b2da` | pass`（单 nodeid；不是 S7 四 nodeid 聚合 PASS） | 1 | 2 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-7-pinned-read.md` | 5296 | `0826b2da` | pass`（两条 per-node 记录均独立通过；不是 S7 四 nodeid 聚合 PASS） | 1 | 2 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-9-restored-lifecycle.md` | 7793 | `a396a926` | pass`（单 nodeid；不是 S7 四 nodeid 聚合 PASS） | 2 | 2 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-design-review.md` | 8564 | `97f0f454` | pass | 3 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-implementation-rereview.md` | 7569 | `71da5061` | pass | 1 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-implementation-review.md` | 8731 | `71da5061` | fail | 4 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-0-entry-reconciliation.md` | 12581 | `77a43ebe` | complete | 3 | 12 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-2-classification-and-static.md` | 9332 | `be2d1a03` | pass | 4 | 4 | 1 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-2-classification-repair.md` | 4327 | `2ef88427` | pass | 4 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-3-worker-convergence.md` | 8009 | `a27fe004` | pass | 4 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-4-source-full-regression-rerun.md` | 3765 | `2ef88427` | pass | 4 | 2 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-4-source-full-regression.md` | 7916 | `8e42bdd6` | pass | 3 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-hygiene-and-candidate-preparation.md` | 11534 | `6ddd94d7` | pass | 2 | 14 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-5-hygiene-rerun.md` | 4514 | `2ef88427` | pass | 2 | 9 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-candidate-seal-review-rerun.md` | 6822 | `21c99ef3` | pass | 2 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-candidate-seal-review.md` | 8825 | `21c99ef3` | fail | 4 | 6 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-design-review.md` | 8041 | `21c99ef3` | pass | 3 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-0-entry-preflight.md` | 16095 | `21c99ef3` | complete | 4 | 5 | 1 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-2-provisional-image.md` | 12162 | `21c99ef3` | pass`（仅 S9-2 preflight；不授予 no-ignore regression、candidate seal、S9 exit 或 S10） | 4 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-3-no-ignore-regression.md` | 14775 | `21c99ef3` | pass | 5 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-4-candidate-seal-packet.md` | 14219 | `21c99ef3` | pass`（packet complete；不授予 independent seal review、S9 exit 或 S10） | 4 | 12 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-0/baseline-and-oracle-notes.md` | 168554 | `28732db0` | Draft | 1 | 15 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1-environment-execution-ledger.md` | 6092 | `9b4adbcb` | **Verified / Resolved**（Phase 1 closed 2026-07-27） | 0 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/executable-contracts-and-walking-skeleton-notes.md` | 61686 | `571e6fc6` | Resolved（2026-07-19；讨论证据，正式规则见第 20 节映射） | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/implementation-design-and-delivery-plan-notes.md` | 7941 | `9c3f38d0` | Resolved（2026-07-20；讨论与可行性证据） | 0 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/phase-1-closure-signoff.md` | 5147 | `9b4adbcb` | **COMPLETED / ACCEPTED** | 4 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp0-dependency-inventory.md` | 3659 | `ec13288c` | WP0 evidence | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r1-dependency-inventory.md` | 2682 | `ccfa3271` | WP2 R1 evidence | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r2-dependency-inventory.md` | 4544 | `7171e6d2` | WP2 R2 evidence | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r3-3a-dependency-inventory.md` | 1565 | `bef97234` | WP2 R3-3A evidence | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r3-3b-dependency-inventory.md` | 1564 | `bef97234` | WP2 R3-3B evidence | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r4-dependency-inventory.md` | 5879 | `342d598c` | WP2 R4 evidence（policy §6 crypto review 补齐） | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r5-dependency-inventory.md` | 9620 | `342d598c` | WP2 R5 evidence（vector consumer / conformance harness） | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r6-normative-publication.md` | 15893 | `eda8b57d` | WP2 R6 evidence（首次 normative vector publication） | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp2-r7-repository-consumer.md` | 6845 | `7b0f0296` | WP2 R7 evidence（Repository Service dev-side vector conformance consumer） | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r1-arrow-pyo3-design.md` | 33449 | `cf45e007` | WP3 R1 design evidence（**rev.3，待人工 re-review**） | 5 | 7 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r2-rust-core-evidence.md` | 6137 | `b9c47256` | R2 implementation evidence（post-audit remediation, round 2） | 2 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r3-pyo3-adapter-evidence.md` | 12675 | `6e14f91c` | R3 implementation evidence（post external audit remediation, round 6） | 1 | 4 | 1 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r4-kernel-component-evidence.md` | 10853 | `6e14f91c` | R4 sign-off evidence（seventh external-review remediation, worktree — **未提交**） | 1 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r5-dependency-inventory.md` | 28496 | `49118e3a` | WP3 R5 evidence（dependency / safety inventory 定稿） | 1 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-r5-kernel-native-signoff.md` | 17509 | `49118e3a` | R5 sign-off evidence（pre-commit capture） | 1 | 14 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp3-wp5-checkout-plan.md` | 9462 | `cf45e007` | 临时实施计划（checkout 拆分与对话边界，**已定稿**） | 7 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp4-r1-artifact-api-design.md` | 7398 | `9dcb7d25` | R1 design authority（WP4 R1 checkout） | 1 | 5 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp4-r1-artifact-api-evidence.md` | 14983 | `9dcb7d25` | R1 strict review / sign-off evidence | 2 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp4-r2-artifact-round-trip-evidence.md` | 15001 | `6310ee96` | R2 component sign-off evidence | 1 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp4-r3-ipc-negative-evidence.md` | 20237 | `6bb0606d` | R3 component sign-off evidence（三轮外部审核修复后） | 1 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp4-r4-artifact-path-closure.md` | 19339 | `f1a6135e` | R4 evidence — **sign-off passed**（外部重审 findings 全部闭合；最终门禁独立重跑 2026-07-23） | 1 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r1-scenario-schema-closure-evidence.md` | 23105 | `4df45e41` | **PASS — EXT-REVIEW-REAUDIT-6 signed off; ready to enter WP5 R2** | 1 | 7 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r2-runner-lifecycle-evidence.md` | 12361 | `97720ea1` | **PASS — independent external review accepted** | 0 | 7 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r3-canonical-row-hash-scenario-evidence.md` | 4878 | `9b4adbcb` | **ACCEPTED / RESOLVED**（2026-07-27 Phase 1 closure review） | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r4-profile-matrix-evidence.md` | 7499 | `9b4adbcb` | **ACCEPTED / RESOLVED**（2026-07-27 Phase 1 closure review） | 0 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r5-phase1-exit-evidence.md` | 8851 | `9b4adbcb` | **PASSED / ACCEPTED**（clean exact-commit three-gate closure） | 0 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/README.md` | 9902 | `c038d4f3` | **Historical after WP1-R1 checkpoint / Superseded by ADR 0009** | 1 | 18 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/bounded-phase-3-consumer-adequacy-check.md` | 9992 | `3485dcf4` | **Confirmed PASS / Formalization Authorized** | 2 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/caller-responsibility-scan-round-0-to-6.md` | 6384 | `3485dcf4` | **Resolved / Review Complete** | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/consolidated-design-review.md` | 23886 | `3485dcf4` | **Resolved Review / Formalized** | 2 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/interactive-design-session-guide.md` | 21072 | `8de8fd16` | **Resolved / Formalized** | 5 | 7 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/p2-r3-implementation-task-prompts.md` | 14126 | `4c33e2d0` | Draft / Active temporary execution prompts | 1 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/p2-r3-synchronous-create-upload-execution-plan.md` | 17524 | `4c33e2d0` | Draft / Active temporary execution coordinator | 2 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s3-staged-execution-guide.md` | 34864 | `715353aa` | Temporary execution coordinator — implementation pending | 4 | 9 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s4-staged-execution-guide.md` | 27862 | `5bc9e52d` | Temporary execution coordinator — implementation pending | 3 | 8 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s5-staged-execution-guide.md` | 34700 | `c038d4f3` | Temporary execution coordinator - implementation pending | 1 | 7 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/round-11-convergence-readiness-scan.md` | 7597 | `3485dcf4` | **Resolved / Round 11 confirmed / Consolidated Review pending** | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/t2-simplification-implementation-checklist.md` | 7029 | `f7c3678a` | READY FOR CROSS-PHASE DESIGN / CODE EXECUTION BLOCKED | 2 | 3 | 0 |
| `docs/backend-vnext/refactoring/temporary/project-environment-preparation.md` | 22009 | `414d56ca` | Draft | 1 | 0 | 0 |
| `docs/backend-vnext/repository-import-benchmark-runbook.md` | 18387 | `1399dbaa` |  | 0 | 0 | 0 |
| `vnext/deploy/p2r1-cache/README.md` | 18908 | `a25f46e6` |  | 3 | 0 | 0 |

### `REDUNDANT` (1)

| 路径 | bytes | last commit | 状态字段 | in | out | unresolved |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `vnext/backend/README.md` | 0 | `414d56ca` |  | 0 | 0 | 0 |

### `ESCALATE` (49)

| 路径 | bytes | last commit | 状态字段 | in | out | unresolved |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `docs/backend-vnext/adr/0001-snapshot-table-and-dolt-import-boundary.md` | 2202 | `1399dbaa` |  | 1 | 0 | 0 |
| `docs/backend-vnext/adr/0002-comparison-hash-sqlite-mode-selection.md` | 3489 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/adr/0003-dolt-native-provider-selection.md` | 3494 | `1399dbaa` |  | 2 | 0 | 0 |
| `docs/backend-vnext/artifacts.md` | 21395 | `6121f612` |  | 1 | 0 | 0 |
| `docs/backend-vnext/capabilities/bundle-assembly.md` | 6169 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/capabilities/business-projection.md` | 5073 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/capabilities/comparison-compute.md` | 38625 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/capabilities/composite-signal-device.md` | 6599 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/capabilities/dolt-native-provider.md` | 11438 | `1399dbaa` |  | 0 | 1 | 0 |
| `docs/backend-vnext/capabilities/ordered-diff-compute.md` | 16615 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/capabilities/project-identity-and-dataset-replacement.md` | 12495 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/capabilities/repository-import.md` | 31179 | `1399dbaa` |  | 1 | 0 | 0 |
| `docs/backend-vnext/capabilities/repository-ref-materialization.md` | 21398 | `1399dbaa` |  | 1 | 0 | 0 |
| `docs/backend-vnext/capabilities/risk-evaluation.md` | 12810 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/capabilities/snapshot-materialization.md` | 26980 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/capabilities/surface-assembly.md` | 7151 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/capabilities/table-presentation-large-data-report.md` | 100094 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/capabilities/table-presentation.md` | 2330 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/contracts/comparison-bundle.md` | 14753 | `6121f612` |  | 1 | 0 | 0 |
| `docs/backend-vnext/contracts/comparison-surface.md` | 12768 | `6121f612` |  | 1 | 0 | 0 |
| `docs/backend-vnext/contracts/comparison.md` | 22542 | `6121f612` |  | 1 | 0 | 0 |
| `docs/backend-vnext/contracts/ordered-diff.md` | 11761 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/contracts/risk.md` | 14704 | `1399dbaa` |  | 1 | 0 | 0 |
| `docs/backend-vnext/contracts/snapshot-table-access.md` | 7956 | `6121f612` |  | 1 | 0 | 0 |
| `docs/backend-vnext/contracts/snapshot.md` | 12849 | `6121f612` |  | 1 | 0 | 0 |
| `docs/backend-vnext/contracts/source-package-and-snapshot.md` | 3750 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/contracts/source-package.md` | 8907 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/contracts/table-presentation.md` | 1902 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/flows.md` | 10623 | `6121f612` |  | 1 | 0 | 0 |
| `docs/backend-vnext/frontend-surface-simplification.md` | 9381 | `1399dbaa` |  | 0 | 0 | 0 |
| `docs/backend-vnext/identity-and-digests.md` | 9455 | `6121f612` |  | 0 | 0 | 0 |
| `docs/backend-vnext/implementation-boundary.md` | 12896 | `6121f612` |  | 1 | 0 | 0 |
| `docs/backend-vnext/modules.md` | 19774 | `6121f612` |  | 1 | 0 | 0 |
| `docs/backend-vnext/operations.md` | 14135 | `6121f612` |  | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md` | 27150 | `969b3691` | Accepted; v8 formal decision approved; P2-R2 authorized | 5 | 7 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md` | 58814 | `74ccbebe` | Accepted — S10 Closure Ready | 4 | 8 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-ext-w1-enum-set-import-design.md` | 5712 | `d03e8e94` | Frozen（独立 Contract review 通过；允许进入 Stage C） | 14 | 7 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md` | 16203 | `0f9536c2` | Design baseline frozen by discussion; independent design review required | 19 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s7-compose-lifecycle-design.md` | 12691 | `34801a16` | Design baseline frozen by discussion; independent review required before implementation | 5 | 6 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s8-full-regression-design.md` | 11286 | `77a43ebe` | Design baseline frozen by discussion; independent design review required before implementation | 11 | 7 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s9-final-candidate-seal-design.md` | 9128 | `21c99ef3` | Design baseline frozen by discussion; independent design review required | 6 | 3 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/p2-versioned-repository-implementation-design.md` | 16124 | `d46500da` | Accepted — P2-R6-S0 design freeze complete, S1 ready | 12 | 8 | 0 |
| `docs/backend-vnext/refactoring/formal/plans/phase-2-implementation-design-and-delivery-plan.md` | 14179 | `24f7a374` | Accepted — Complete P2 Design | 7 | 12 | 0 |
| `docs/backend-vnext/refactoring/temporary/architecture-simplification-execution-plan.md` | 7280 | `f7c3678a` | Active / Design Before Combined Code Cleanup | 2 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r9-s2-cooperative-cleanup-simplification-plan.md` | 20682 | `c6161c81` | Temporary execution guide — implementation pending | 0 | 4 | 0 |
| `docs/backend-vnext/refactoring/temporary/p2-r9-s2-step-e-container-gate.md` | 4456 | `76b07460` | Executed | 1 | 0 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/decision-ledger-round-0-to-3.md` | 97250 | `3485dcf4` | **Draft / Active Interview Record** | 2 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/decision-ledger-round-4-to-7.md` | 82294 | `3485dcf4` | **Draft / Active Interview Record** | 2 | 1 | 0 |
| `docs/backend-vnext/refactoring/temporary/phase-2/decision-ledger-round-8-to-11.md` | 140283 | `3485dcf4` | **Draft / Active Interview Record** | 2 | 1 | 0 |

## C0 exit

```yaml
c0_status: complete
c0_continue_plan: yes
freeze_head: 1420eaddaffb506d6c209862b9daeb510b7fc230
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
proposed_pre_cleanup_tag: docs/p2-p3-cleanup-pre-20260817
pre_cleanup_tag_created: no
inventory_rows: 300
next: C1
```

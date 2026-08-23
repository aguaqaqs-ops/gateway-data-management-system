# P3→P4 Context and Code Consolidation Handoff

状态：C7 **PASS**；`p3_p4_cleanup_exit: pass`；不是 P4 implementation authorization

日期：2026-08-23

Owner：Backend vNext Architecture / Cleanup Implementer

本文封存 P3→P4 context and code consolidation 的 final candidate、scope、recovery 与
P4 entry boundary。它不拥有 contract、wire、state machine 或 operation runtime 语义。
独立验收见
[p3-p4-cleanup-c7-independent-acceptance.md](p3-p4-cleanup-c7-independent-acceptance.md)、
[p3-p4-cleanup-implementer-evidence-report.md](p3-p4-cleanup-implementer-evidence-report.md)
与 manifest
[p3-p4-cleanup-manifest.yaml](p3-p4-cleanup-manifest.yaml)。

P4 默认入口：[P4 Active Context Index](p4-active-context-index.md)

```yaml
handoff_kind: p3_p4_context_code_consolidation
baseline_sha: 31409c8e0c37d8c12a323269ddeefebdb9927955
candidate_sha: 5687e275be8f3cb54ed9bdbe429ea6380c8577b7
pre_cleanup_tag: docs/p3-p4-cleanup-pre-20260823
pre_cleanup_commit: 8682b1c6873e056386b007b3b8eb9e3d14c624a4
final_cleanup_tag: docs/p3-p4-cleanup-final-20260823
final_tag_sha: 7c751ba86237cacf5fdc223d479d063112d9fe0b
p3_exit: pass
p4_ready: yes
p3_p4_cleanup_exit: pass
p4_entry_context_ready: yes
p4_implementation_authorized: no_until_p4_entry_acceptance
public_semantics_changed: false
```

## 1. Scope

| 类别 | 数量 | 说明 |
| --- | ---: | --- |
| C3 归档 P3 过程文档 | 26 | 离开默认树；恢复见 pre-tag 与 manifest `archive_from_default` |
| C6 移除 cleanup 过程材料 | 9 | 离开默认树；恢复见 pre-tag 或 persist commit（下表） |
| 代码 bundle 实施 | 0 | C4 批准 `approved_code_change_bundles: 0`；C5 `not_applicable` |
| 代码 bundle 保留 | 3 | evidence tool、P3 reference executor、`target_gate` |
| 代码 bundle 延期 | 4 | synthetic W2、shared-kernel testing、matrix harness、corrective test |

`vnext/**`、Dockerfile、Compose、依赖与测试在 C5/C6 未变更。

## 2. P4 默认读取与未授权边界

默认读取顺序见 [P4 Active Context Index §1](p4-active-context-index.md#1-默认从这里开始)。
约 10 个直接文档即可进入 P4 设计对话，无需加载 P3 step/review matrix 或 cleanup 过程记录。

仍未授权：

- P4 Operation Store、worker、lease、heartbeat、takeover、drain；
- P5 Workspace/Submit/finalize、occupancy、T1/T3；
- 改变 P3 public contract、digest、reference executor 或 Repository reconciliation authority。

`p4_implementation_authorized: no_until_p4_entry_acceptance`。

## 3. Deferred code bundles（C4 裁定，C5 未实施）

| Bundle | C4 决策 | Owner / reopen |
| --- | --- | --- |
| `MOVE_REMOVE_CANDIDATE` — `synthetic_w2.py`, `run_r6_s6_evidence.py` | `DEFER` | owner-approved test-support/evidence migration |
| `MOVE_CANDIDATE` — `gateway_shared_kernel.testing/*` | `DEFER` | package/install + fixture-path proof |
| `RETIRE_DECISION_REQUIRED` — `matrix.py`, `workflow.py`, `workflow_worker.py` | `DEFER` | explicit P2-R1 harness/profile decision |
| `FOLLOW_HARNESS_DECISION` — `test_p2_r1_audit_corrective.py` | `DEFER` | follow harness decision; do not delete alone |

完整 consumer 图见 manifest `code_bundles`。

## 4. Recovery

### 4.1 P3 过程文档（C3）

```bash
git show docs/p3-p4-cleanup-pre-20260823:docs/backend-vnext/refactoring/formal/plans/p3-r2-s0-entry-and-budget-freeze.md
```

manifest：`paths.archive_from_default`（26 paths，`recovery_tag: docs/p3-p4-cleanup-pre-20260823`）。

### 4.2 Cleanup 过程材料（C6）

| Path | Recovery |
| --- | --- |
| `temporary/p3-p4-context-and-code-consolidation-execution-plan.md` | pre-tag |
| `temporary/p3-p4-context-code-consolidation-c0-inventory.md` | pre-tag |
| `temporary/p3-p4-context-code-consolidation-c0-inventory.json` | pre-tag |
| `temporary/p3-p4-context-code-consolidation-c1-classification.md` | pre-tag |
| `temporary/p3-p4-context-code-consolidation-c1-classification.json` | pre-tag |
| `temporary/generate_p3_p4_c0_inventory.py` | pre-tag |
| `temporary/generate_p3_p4_c1_classification.py` | pre-tag |
| `temporary/p3-p4-context-code-consolidation-c4-consumer-audit.md` | commit `1a519a29530d7906227a66bbe731babf32bd412f` |
| `temporary/p3-p4-context-code-consolidation-c5-implementation.md` | commit `274a72ca9d05dfcc1fb6a184407bf9ab673c9b65` |

示例：

```bash
git show docs/p3-p4-cleanup-pre-20260823:docs/backend-vnext/refactoring/temporary/p3-p4-context-and-code-consolidation-execution-plan.md
git show 1a519a29530d7906227a66bbe731babf32bd412f:docs/backend-vnext/refactoring/temporary/p3-p4-context-code-consolidation-c4-consumer-audit.md
```

## 5. C7 independent acceptance

独立验收记录：[C7 Independent Acceptance](p3-p4-cleanup-c7-independent-acceptance.md)。
该记录确认 candidate、pre/final tag、path/hash、link closure、deferred code disposition
和 P4 boundary 均一致；`p4_implementation_authorized` 仍为
`no_until_p4_entry_acceptance`。

## 6. C7 independent acceptance inputs

- final candidate SHA 与 `docs/p3-p4-cleanup-final-20260823`
- pre-tag `docs/p3-p4-cleanup-pre-20260823`
- [p3-p4-cleanup-manifest.yaml](p3-p4-cleanup-manifest.yaml)
- 本文与 [implementer evidence report](p3-p4-cleanup-implementer-evidence-report.md)
- C4/C5 结论（已摘要于 manifest `code_bundles` 与本 handoff §3）
- applicable gate logs（docs-only；container rebuild `not_applicable`）

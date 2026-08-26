# P4 Active Context Index

状态：P4-R5-S0 independent acceptance pass；S1a authorized；implementation otherwise not authorized

日期：2026-08-25

Owner：Backend vNext Architecture

本文是 Phase 4 设计的**默认入口**。它只组织检索边界，不拥有 wire、字段、状态机、
operation runtime 或错误矩阵。精确语义由列出的 normative owner 拥有。不得把本文当作
contract，也不得直接开始 P4 implementation，除非另有 implementation authorization。

上游身份：[P3 Final Closure and P4/P5 Entry Handoff](p3-final-closure-handoff.md)
清理动作：[P3→P4 Cleanup Handoff](p3-p4-cleanup-handoff.md) · [Manifest](p3-p4-cleanup-manifest.yaml)
阶段顺序：[Implementation Stages §7 Phase 4](implementation-stages.md#7-phase-4durable-operation-runtime)

```yaml
p3_exit: pass
p4_ready: yes
p3_p4_cleanup: complete
p3_p4_cleanup_exit: pass
p4_entry_context_ready: yes
p4_entry_acceptance: pass
p4_r1_s0: accepted
p4_r1_s1a: pass
p4_r1_s1b: pass
p4_r1_s2a: pass
p4_r1_s2b: pass
p4_r1_s3a: pass
p4_r1_s3b: pass
p4_r1_s4: pass_after_s5
p4_r1_s5: pass
p4_r1_s6: pass_after_f2_f3_remediation
p4_r1_s7: pass
p4_implementation_authorized: r5_s0_discussion_only
r1_s1a_authorized: yes
r1_s1b_authorized: yes
r1_s2a_authorized: yes
r1_s2b_authorized: yes
r1_s3a_authorized: yes
r1_s6_remediation_authorized: yes
r1_s7_authorized: yes
p4_r2_entry_discussion_authorized: yes
p4_r2_s0: accepted
p4_r2_s1a: pass
p4_r2_s1a_authorized: yes
p4_r2_s1b: pass
p4_r2_s1b_authorized: yes
p4_r2_s2a: pass
p4_r2_s2a_authorized: yes
p4_r2_s2b: pass
p4_r2_s2b_authorized: yes
p4_r2_s3a: pass
p4_r2_s3a_authorized: yes
p4_r2_s3b: pass
p4_r2_s3b_authorized: yes
p4_r2_s4: pass_after_s5_f1_follow_up
p4_r2_s4_authorized: yes
p4_r2_s5: pass
p4_r2_s5_authorized: yes
p4_r2_s6: pass_after_finding_scoped_remediation
p4_r2_s6_authorized: yes
p4_r2_s7: pass
p4_r2_authorized: no
p4_r3_entry_discussion_authorized: yes
p4_r3_s0_design: accepted
p4_r3_execution_plan: accepted
p4_r3_s0_acceptance: accepted
p4_r3_s1a: pass
p4_r3_s1b: pass
p4_r3_s2a: pass
p4_r3_s2b: pass
p4_r3_s3a: pass
p4_r3_s3b: pass
p4_r3_s4: pass_after_s5
p4_r3_s5: pass
p4_r3_s6: pass
p4_r3_s7: pass
p4_r3_exit: pass
p4_r3_validated_code_sha: acb3efca06a02aadaa5ce6d1e2a815e85d36e6af
p4_r3_implementation_authorized: no_further_r3_work
p4_r4_entry_discussion_authorized: yes
p4_r4_s0_design: accepted
p4_r4_execution_plan: accepted
p4_r4_s0_acceptance: accepted
p4_r4_s1a: pass
p4_r4_s1b: pass
p4_r4_s2a: pass
p4_r4_s2b: pass
p4_r4_s3a: pass
p4_r4_s3b: pass
p4_r4_s3c: pass
p4_r4_s4: pass_after_s5
p4_r4_s5: pass
p4_r4_s6: pass_after_s5_remediation
p4_r4_s7: pass
p4_r4_exit: pass
p4_r4_validated_code_sha: d1d929dcee3b0620b649a248079d846dfbe7aba1
p4_r4_s1a_authorized: yes_completed
p4_r4_implementation_authorized: no_further_r4_work
p4_r5_entry_discussion_authorized: yes
p4_r5_s0_design: discussion_converged
p4_r5_s0_acceptance: accepted
p4_r5_execution_plan: accepted
p4_r5_documentation_seal: be1b70c
p4_r5_document_set_hash: 1c00f80e1f3b33ffdcf45aef049775678aaad068e3347d8772286831623afcd2
p4_r5_s1a_authorized: yes
p4_r5_implementation_authorized: s1a_only
p5_implementation_authorized: no
p3_production_integration_authorized: no
default_retrieval: this_index
public_semantics_changed_in_c2: no
pre_cleanup_tag: docs/p3-p4-cleanup-pre-20260823
final_cleanup_tag: docs/p3-p4-cleanup-final-20260823
```

## 1. 默认从这里开始

按这个顺序读。不要从 P3 step/review/execution plan、`temporary/` 过程记录或
`vnext/repository_service/README.md` 的状态行开始。

1. 本 index。
2. [P3 Final Closure and P4/P5 Entry Handoff](p3-final-closure-handoff.md)：sealed
   candidate、deferred register、P4/P5 entry boundary。
3. [P3-FINAL F5 Independent Acceptance Record](p3-final-closure-f5-independent-acceptance.md)：
   Phase 3 exit pass；`p4_ready: yes`；P4 implementation 未授权。
4. [Implementation Stages §7 Phase 4](implementation-stages.md#7-phase-4durable-operation-runtime)：
   Durable Operation Runtime 目标、交付物与退出条件。
5. [P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)：
   已确认的 P4 总体设计、边界、状态和恢复不变量。
6. [P4 Durable Operation Runtime Execution Plan](p4-durable-operation-runtime-execution-plan.md)：
   六个初始模块、S-step 模板、测试策略和 entry/exit gate。
7. [P4 Entry Acceptance Candidate](p4-entry-acceptance.md)：
   当前候选的 gate 检查、provenance、独立 acceptance 和实现授权边界。
8. [P4-R1-S0 Entry Brief](p4-r1-s0-entry-brief.md)：
   R1 的范围、owner、适用 steps、测试和 handoff 前置条件。
9. [P4-R1 Runtime Contract and State Detailed Execution Plan](p4-r1-runtime-contract-state-execution-plan.md)：
   可由短提示逐 step 执行的路径、contract、测试、review 和 handoff authority。
10. [P4/R1 Runtime Contract and State Handoff](p4-r1-runtime-contract-state-handoff.md)：
    R1 tested tip、module gate与R2 entry boundary。
11. [P4-R2-S0 Entry Brief](p4-r2-s0-entry-brief.md)：R2 owner、schema、transaction、
    budgets、applicable steps与implementation boundary。
12. [P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)：
    R2逐step paths、gates、review、handoff与reopen authority。
13. [P4/R2 Durable Store and Atomic Transition Handoff](p4-r2-durable-store-atomic-transition-handoff.md)：
    R2 S7 tested tip、module gate、known limits与R3-S0 entry boundary。
14. [P4/R2-S0 Independent Entry Acceptance](p4-r2-s0-entry-acceptance.md)：
    R2 design acceptance与S1a未授权边界。
15. [P4-R3-S0 Entry Brief](p4-r3-s0-entry-brief.md)：R3 worker、lease session、
    process-local lifecycle、startup gate、single-worker deployment与reopen边界的accepted design；
    S7 module gate已通过。
16. [P4-R3 Worker and Process Lifecycle Detailed Execution Plan](p4-r3-worker-lifecycle-execution-plan.md)：
    按现有R1/R2、bootstrap、tests和image接缝拆分的逐step实施、审核、module gate和handoff记录。
17. [P4/R3-S0 Independent Entry Acceptance](p4-r3-s0-entry-acceptance.md)：
    R3 owner、lifecycle、transaction、deployment和step/gate的独立acceptance。
18. [P4/R3 Worker Lifecycle Handoff](p4-r3-worker-lifecycle-handoff.md)：S7 module gate、
    current-HEAD image provenance、container smoke与R4-S0 entry boundary。
18a. [P4-R4-S0 Entry Brief](p4-r4-s0-entry-brief.md)：JobDefinition、payload、checkpoint、READY
     closure、successor、stub、cancel和R4/R5/P5 owner boundary。
18b. [P4-R4 JobDefinition and Checkpoint Detailed Execution Plan](p4-r4-jobdefinition-checkpoint-execution-plan.md)：
     可用短提示词逐step推进、review rounds、conversation strategy、gates和reopen authority。
18c. [P4-R4-S0 Independent Entry Acceptance](p4-r4-s0-entry-acceptance.md)：R4设计/plan已接受。
18d. [P4/R4 JobDefinition and Checkpoint Handoff](p4-r4-jobdefinition-checkpoint-handoff.md)：
     S7 module gate、current-HEAD image provenance、container smoke与P4-R5-S0 entry boundary。
18e. [P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)：
     retry/takeover/reconcile、identity、budget、operator port和owner boundary。
18f. [P4-R5-S0 Entry Brief](p4-r5-s0-entry-brief.md)：
     R5 entry identity、accepted defaults、S0 checks和implementation authorization boundary。
18g. [P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)：
     S1a-S3c step split、review rounds、markers、container gate和handoff schema。
19. [Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)：
   operation/step 状态、integrity 与 recovery owner。
20. [External Effect and Recovery](../contracts/external-effect-and-recovery.md)：
   external effect evidence、reconciliation 与 recovery owner。
21. [Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)：
   business object、occupancy、freeze point 与 T1/T3 owner。
22. [Repository Service Contract](../contracts/repository-service.md)：Repository
   operation、marker/ref/CAS、reconciliation authority；P4 lease 不改变其语义。
23. [P3 Capability Foundation Design](p3-capability-foundation-design.md)：P3 capability
   设计 authority 与 P4 直接依赖的 capability contracts 索引。
24. [Proportional Assurance and Risk-Based Verification Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)：
    跨阶段保障与测试取舍。

可选（贡献者/实现约束）：

- [AGENTS.md](../../../../../AGENTS.md)
- [Testing Conventions](../../../testing-conventions.md)

## 2. P4 entry prerequisites 与 non-goals

P3 已交付 capability foundation；P4 建立 **durable operation runtime**，为 Phase 5
业务纵切提供可持久化、可重试、可接管的执行机制。完整边界见
[final handoff §6](p3-final-closure-handoff.md#6-p4p5-entry-boundary)。

P3 **不交付、不授权**（P4 也不得静默改变其 owner）：

- durable Operation Store、worker、lease、heartbeat、takeover；
- Workspace/HTTP/PreviewResult、Submit/finalize、confirmation、occupancy、T1/T3；
- production external-target adapter 或 multi-target durable schema；
- Repository Service reconciliation（control DB/marker/ref/CAS）——仍由 Repository
  contract 拥有；P4 lease 不改变 Repository operation authority。

P4-R1已exit；P4-R2已完成S7 module gate；P4-R3已完成S7 module gate；P4-R4已完成S7
module gate。`p4_r2_authorized: no`、`p4_r4_implementation_authorized: no_further_r4_work`、
`p4_r5_s0_acceptance: accepted`；当前仅 P4-R5-S1a 获授权，R5后续步骤与 P5/P5B
implementation仍未授权。

## 3. P3 handoff 指针

| 材料 | 角色 |
| --- | --- |
| [P3 Final Closure Handoff](p3-final-closure-handoff.md) | sealed SHA、benchmark/container provenance、deferred register |
| [P3-FINAL F5 Acceptance](p3-final-closure-f5-independent-acceptance.md) | 独立 exit pass 记录 |
| [P3-R7 Mutation and Target Closure Handoff](p3-r7-mutation-target-closure-handoff.md) | 最近 module gate；P4/P5 entry prerequisites |
| [P2 External Interface Handoff](p2-external-interface-handoff.md) | Repository wire、支持面、限制与 reopen |

关键 identity（不重述证据正文）：

```text
tested_candidate_sha: 13ce18b8b2d689bc7a4087e0072d485891740c0c
f3/f4_validated_source_sha: a28d88a85793017716029638155687ca17e4b5ed
handoff_record_sha: b0ac984507056fb10c17c07243330b20a315c2c8
```

## 4. Phase 4 目标摘要

Phase 4 交付 Durable Operation Runtime、JobDefinition registry、worker entrypoint，以及
crash/lease/retry/duplicate delivery/cancellation tests。详细目标、交付物与退出条件见
[Implementation Stages §7](implementation-stages.md#7-phase-4durable-operation-runtime)。

Operation 与 business execution/effect evidence 的分界以
[External Effect and Recovery](../contracts/external-effect-and-recovery.md) 为准。

## 5. 按需参考（非默认读取）

需要 capability 模块边界、deferred register 或 benchmark 证据时再读；**不要**把下列
材料当作 P4 默认规则。

| 类别 | 入口 |
| --- | --- |
| P3 module handoff | R1–R7 `p3-r*-handoff.md`（见 formal README module 列表） |
| P3 module design | R4–R7 `p3-r*-design.md` |
| P3 capability execution | [P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md) |
| Benchmark evidence | [p3-final-closure-benchmark.json](p3-final-closure-benchmark.json) |
| Architecture 总纲 | [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md) |
| Contract taxonomy | [Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md) |

已完成 P3 S-step、review、round execution plan 是过程证据，不在默认树检索；恢复见
§6。

## 6. 不是默认上下文

以下材料**不要**当作 P4 默认规则。需要时走 handoff、manifest 或 Git tag。

| 材料 | 原因 |
| --- | --- |
| `p3-active-context-index.md` | 历史 P3 默认入口；已归档，恢复见 tag `docs/p3-p4-cleanup-pre-20260823` 与 manifest `archive_from_default` |
| P3 S0/review/execution plan 过程文档 | 已完成过程记录；见 manifest `archive_from_default` |
| P3→P4 cleanup 过程材料（C0–C5 记录与执行计划） | 已离开默认树；恢复见 [cleanup handoff](p3-p4-cleanup-handoff.md) §4 与 manifest `archive_from_default` |
| `vnext/repository_service/README.md` 状态行 | 冻结在 P2-R5；不是 phase authority |
| decision ledger、旧 `docs/backend-vnext/contracts/` 作 RS wire | 过期或降为 oracle |

恢复介质：

```text
pre_cleanup_tag: docs/p3-p4-cleanup-pre-20260823
final_cleanup_tag: docs/p3-p4-cleanup-final-20260823
manifest: p3-p4-cleanup-manifest.yaml paths.archive_from_default
handoff: p3-p4-cleanup-handoff.md
```

示例：`git show docs/p3-p4-cleanup-pre-20260823:docs/backend-vnext/refactoring/formal/plans/p3-r2-s0-entry-and-budget-freeze.md`

## 7. 贡献者约束

实现与测试约束见 [AGENTS.md](../../../../../AGENTS.md) 与
[Testing Conventions](../../../testing-conventions.md)。比例化保障见
[Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)。

# Formal Refactoring Documents

本目录保存已经讨论收口、作为后续设计和实现依据的正式重构文档。

正式文档必须：

- 声明状态、owner 或适用阶段。
- 只记录最终规则，不复制讨论过程。
- 明确依赖方向、兼容性和验收标准。
- 发生关键变更时同步更新 contract tests、golden fixtures 或 ADR。

当前内容：

- [P4 Active Context Index](plans/p4-active-context-index.md)（P4 设计默认入口）
- [P4 Durable Operation Runtime Design Baseline](plans/p4-durable-operation-runtime-design.md)
- [P4 Durable Operation Runtime Execution Plan](plans/p4-durable-operation-runtime-execution-plan.md)
- [P4 Entry Acceptance Candidate](plans/p4-entry-acceptance.md)
- [P4-R1-S0 Entry Brief](plans/p4-r1-s0-entry-brief.md)
- [P4-R1 Runtime Contract and State Detailed Execution Plan](plans/p4-r1-runtime-contract-state-execution-plan.md)
- [P4/R1 Runtime Contract and State Handoff](plans/p4-r1-runtime-contract-state-handoff.md)
- [P4-R2-S0 Entry Brief](plans/p4-r2-s0-entry-brief.md)
- [P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](plans/p4-r2-durable-store-atomic-transition-execution-plan.md)
- [P4/R2 Durable Store and Atomic Transition Handoff](plans/p4-r2-durable-store-atomic-transition-handoff.md)
- [P4/R2-S0 Independent Entry Acceptance](plans/p4-r2-s0-entry-acceptance.md)
- [P2 External Interface Handoff](plans/p2-external-interface-handoff.md)（封印 candidate/image、支持面、限制、reopen）
- [P2–P3 Cleanup Manifest](plans/p2-p3-cleanup-manifest.yaml)
- [P3→P4 Cleanup Manifest](plans/p3-p4-cleanup-manifest.yaml)
- [P3→P4 Cleanup Handoff](plans/p3-p4-cleanup-handoff.md)（P4 entry cleanup boundary）
- [P3→P4 Cleanup Implementer Evidence Report](plans/p3-p4-cleanup-implementer-evidence-report.md)
- [P3→P4 Cleanup C7 Independent Acceptance](plans/p3-p4-cleanup-c7-independent-acceptance.md)
- [Architecture and Refactoring Plan](architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](plans/implementation-stages.md)
- [DX Cross-Phase Interface Reconciliation](plans/dx-cross-phase-interface-reconciliation.md)
- [P2-R1 Runtime and Provider Feasibility Contract](plans/p2-r1-runtime-provider-feasibility.md)（pytest methodology 指针；不是设计入口）
- [P2-R5 Commit-pinned Read Staged Execution Plan](plans/p2-r5-commit-pinned-read-execution-plan.md)（package README 唯一指针；不是 Phase 2 完成 authority）
- [P3 Capability Foundation Design](plans/p3-capability-foundation-design.md)
- [P3 Capability Foundation Execution Plan](plans/p3-capability-foundation-execution-plan.md)
- [P3 Final Closure and P4/P5 Entry Handoff](plans/p3-final-closure-handoff.md)（P3 exit / P4 entry boundary）
- [P3-FINAL F5 Independent Acceptance Record](plans/p3-final-closure-f5-independent-acceptance.md)（Phase 3 exit pass）
- P3 module handoffs：R1–R7 `p3-r*-handoff.md`
- P3 module designs：R4–R7 `p3-r*-design.md`
- [Proportional Assurance and Risk-Based Verification Policy](policies/proportional-assurance-and-risk-based-verification-policy.md)
- [Rust Safety and Performance Policy](policies/rust-safety-and-performance-policy.md)
- [Contract Taxonomy and Ownership](contracts/contract-taxonomy-and-ownership.md)
- [Business Lifecycle and State Contract](contracts/business-lifecycle-and-state.md)
- [External Effect and Recovery Contract](contracts/external-effect-and-recovery.md)
- [Operation Lifecycle and Integrity Contract](contracts/operation-lifecycle-and-integrity.md)
- [Shared Canonical Encoding Contract](contracts/shared-canonical-encoding.md)
- [Canonical Encoding Vector Schema — Historical](contracts/canonical-encoding-normative-vector-schema.md)
- [Canonical Row Hash Compute Boundary Contract](contracts/canonical-row-hash-compute-boundary.md)
- [Correctness Golden and Fixture Contract](contracts/fixture-oracle-and-conformance.md)
- [Canonical Storage and Repository Boundary Contract](contracts/canonical-storage-and-repository-boundary.md)
- [Storage Mutation and Change Set Contract](contracts/storage-mutation-and-change-set.md)
- [External Target Sync and Recovery Contract](contracts/external-target-sync-and-recovery.md)
- [Ruleset Activation and Migration Contract](contracts/ruleset-activation-and-migration.md)
- [Repository Service Contract](contracts/repository-service.md)
- [Performance Measurement Guidance](contracts/performance-measurement-and-baseline.md)
- [ADR 0001](adr/0001-python-rust-hybrid-compute-strategy.md)–[ADR 0016](adr/0016-graceful-lifecycle-and-integrity-recovery.md)

历史 P3 过程文档（S0、review、round execution plan）已离开默认树；恢复见
[P3→P4 Cleanup Manifest](plans/p3-p4-cleanup-manifest.yaml) `paths.archive_from_default` 与
tags `docs/p3-p4-cleanup-pre-20260823`、`docs/p3-p4-cleanup-final-20260823`。

## 权威关系

- Architecture 定义总体边界与依赖方向；Implementation Stages 定义交付顺序和 gate。
- Cross-stage policy定义不属于业务contract、但必须由工程和CI持续执行的安全、工具链与实现约束。
- 比例化保障与风险验证policy适用于Phase 0–9及后续维护；专项ADR/contract只能在有明确
  威胁、损失或consumer依据时提高保障，不能在实现评审中静默扩大威胁模型。
- Contract 是字段语义、状态、byte contract、artifact、fixture 和 measurement 的 normative owner；ADR 只记录为何选择该方案，并链接 contract，不复制精确状态表或字段表。
- 同一规则只在 owning contract 中定义。Architecture、计划和其他 contract 只引用，不建立第二份规范。
- `temporary/` 不拥有正式语义。P4 默认入口是本目录的
  [P4 Active Context Index](plans/p4-active-context-index.md)、P2 handoff、cleanup manifest，
  以及 annotated tags `docs/p2-p3-cleanup-pre-20260817`、`docs/p2-p3-cleanup-final-20260817`、
  `docs/p3-p4-cleanup-pre-20260823`、`docs/p3-p4-cleanup-final-20260823`。不得为保留历史再复制一套 authority。
- Legacy 只作为行为与 fixture 发现 oracle，不拥有 vNext 内部结构或性能目标。

正式文档之间发生冲突时，应先暂停实现，明确语义 owner，并通过修改正式文档或新增 ADR 收口；不能依靠兼容代码长期维持两套含义。

当前阶段：`phase_2_complete: yes`；P3 final closure `p3_exit: pass`、`p4_ready: yes`；
P4-R1 module gate `pass`；P4-R2 module gate `pass`，当前仅开放 R3-S0 entry discussion。
全局`p3_implementation_authorized: no`。默认入口见
[P4 Active Context Index](plans/p4-active-context-index.md)。完整对外接口见
[P2 External Interface Handoff](plans/p2-external-interface-handoff.md)。

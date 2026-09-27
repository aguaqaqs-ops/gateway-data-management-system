# Formal Refactoring Documents

本目录保存已经讨论收口、作为后续设计和实现依据的正式重构文档。

正式文档必须：

- 声明状态、owner 或适用阶段。
- 只记录最终规则，不复制讨论过程。
- 明确依赖方向、兼容性和验收标准。
- 发生关键变更时同步更新 contract tests、golden fixtures 或 ADR。

当前内容（仓库 P5 默认入口）：

- [P5 Business Vertical Slices Design Baseline](plans/p5-business-vertical-slices-design.md)
- [P5-5D Slice Exit — Final](plans/p5-5d-slice-exit-final.md)（`p5_5d_slice_exit: pass`）
- [P5-5D Independent Docs Acceptance](plans/p5-5d-s0-independent-docs-acceptance.md)（docs review pass；四项 finding closed）
- [P5-5D-S0 Entry Brief](plans/p5-5d-s0-entry-brief.md)（accepted；独立文档审核通过，implementation 未授权）
- [Business Lifecycle 固定 scope 归属补充](contracts/business-lifecycle-and-state.md#repository-scope-ownership-amendment)（3.0.0 accepted；S1 Contract 前置已满足）
- [P5-5D Archive Detailed Design](plans/p5-5d-archive-design.md)（accepted；独立文档审核通过，implementation 未授权）
- [P5-5D Archive Execution Plan](plans/p5-5d-archive-execution-plan.md)（completed；slice exit pass）
- [P5-5E Independent Docs Acceptance](plans/p5-5e-s0-independent-docs-acceptance.md)（docs review pass v3.6；S1 实现已授权）
- [P5-5E-S0 Entry Brief](plans/p5-5e-s0-entry-brief.md)（accepted；S1 kickoff pass）
- [P5-5E History Compare Detailed Design](plans/p5-5e-history-compare-design.md)（accepted；S1 实现已授权）
- [P5-5E History Compare Execution Plan](plans/p5-5e-history-compare-execution-plan.md)（accepted；**S1–S4 权威执行入口**）
- [P5-5E-S1 Kickoff Gate](plans/p5-5e-s1-kickoff.md)（pass）
- [P5 架构收口 S0 Entry Brief](plans/p5-arch-closure-s0-entry-brief.md)、
  [详细设计](plans/p5-arch-closure-design.md)、[执行计划](plans/p5-arch-closure-execution-plan.md)、
  ADR [0018](adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)–[0021](adr/0021-flow-neutral-comparison-entry.md)
  （S0 文档 r4 于 2026-09-27 由 owner 接受，ADR Accepted；Business Lifecycle 与 Canonical Storage 升至 3.1.0；实现未授权）
  - [S0 独立文档审核报告](plans/p5-arch-closure-s0-independent-docs-review.md)（r1 @ `3e5d5807e5`：定向修订；含 2026-09-26 复核补充）
  - [r2 独立复审（第一份）](plans/p5-arch-closure-s0-independent-rereview.md)（@ `5858eaaa08`：定向修订）
  - [r2 独立复审（第二份）](plans/p5-arch-closure-s0-independent-rereview-2.md)（@ `5858eaaa08`：定向修订；O1–O5 已决议为 DC23–DC27）
  - [r3 独立复审（第一份）](plans/p5-arch-closure-s0-independent-rereview-r3.md)（@ `ffba1138ef`：通过，含一项非阻塞）
  - [r3 独立复审（第二份）](plans/p5-arch-closure-s0-independent-rereview-r3-2.md)（@ `ffba1138ef`：定向修订，两项阻塞）
  - [r4 独立核对](plans/p5-arch-closure-s0-independent-rereview-r4.md)（@ `2f38b301a6`：通过，两项非阻塞已吸收）
  - [S0 Owner 决议记录](plans/p5-arch-closure-s0-owner-decisions.md)（DC10–DC27 已决议；含真实数据存放约定）
  - [S0 修订处置表](plans/p5-arch-closure-s0-revision-disposition.md)（r2：F1–F11、N1–N6、DC10–DC22；r3：两份 r2 复审的 findings 与 DC23–DC27；r4：两份 r3 复审的 findings；§10 接受记录）
- [P5-5C-S5 Independent Slice Exit Acceptance](plans/p5-5c-s5-independent-acceptance.md)（`p5_5c_slice_exit: pass`）
- [P5-5C-S0 Entry Brief](plans/p5-5c-s0-entry-brief.md)（historical entry input）
- [P5-5C Review Detailed Design](plans/p5-5c-review-design.md)（accepted；slice completed）
- [P5-5C Review Execution Plan](plans/p5-5c-review-execution-plan.md)（completed；slice exit pass）
- [P5-5B-S8 Independent Slice Exit Acceptance](plans/p5-5b-s8-independent-acceptance.md)（`p5_5b_slice_exit: pass`）
- [P5-5B-S8 Handoff](plans/p5-5b-s8-handoff.md)（gate evidence @ `460d6f5b`）
- [P5-5B-S0 Entry Brief](plans/p5-5b-s0-entry-brief.md)（historical entry input）

P4-R6 exit（**pass** on sealed candidate `7fbddc73`；解除 5B source/test/deployment 硬前置）：

- [P4-R6-S7 Final Handoff](plans/p4-r6-s7-final-handoff.md)（`p4_r6_exit: pass`）
- [P4-R6-S6 Container and Provenance Evidence](plans/p4-r6-s6-container-provenance-evidence.md)
- [P4-R6-S4 Independent Review](plans/p4-r6-s4-independent-review.md)（F1 closed）
- [P4-R6-S0 Independent Entry Acceptance](plans/p4-r6-s0-independent-entry-acceptance.md)
- [P4-R6-S0 Finding Disposition](plans/p4-r6-s0-finding-disposition.md)（historical reopen；remediation已闭合）

P5-5A historical input（slice exit pass；container gate pass）：

- [P5-5A Baseline Acceptance](plans/p5-5a-baseline-acceptance.md)
- [P5-5A-S0 Entry Brief](plans/p5-5a-s0-entry-brief.md)
- [P5-5A Upload/Preview Detailed Design](plans/p5-5a-upload-preview-design.md)
- [P5-5A Upload/Preview Execution Plan](plans/p5-5a-upload-preview-execution-plan.md)
- [P5-5A Remediation Review](plans/p5-5a-remediation-review.md)（remediation pass；superseded by S6）
- [P5-5A S6 Handoff](plans/p5-5a-s6-handoff.md)（slice exit pass；container gate pass）

P4 专用入口仍为 [P4 Active Context Index](plans/p4-active-context-index.md)；**P4-R6 exit pass**。
P5-5B/5C/5D slice exit pass；5E docs accepted（v3.6），S1 实现已授权（kickoff pass）；5E S2+、production deployment 与新的 Repository effect 未授权。
P4 Active Context Index 不覆盖 P5 semantic default entry。
以下清单保留 P4/P3 设计和 handoff 的可达性，但不改变上述 P5 默认顺序：

- [P4 Active Context Index](plans/p4-active-context-index.md)（P4 专用入口；不是仓库当前默认入口）
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
- [P4-R3-S0 Entry Brief](plans/p4-r3-s0-entry-brief.md)（S0 design accepted；S7 module gate pass）
- [P4-R3 Worker and Process Lifecycle Detailed Execution Plan](plans/p4-r3-worker-lifecycle-execution-plan.md)（S7 module gate pass）
- [P4/R3-S0 Independent Entry Acceptance](plans/p4-r3-s0-entry-acceptance.md)（pass）
- [P4/R3 Worker Lifecycle Handoff](plans/p4-r3-worker-lifecycle-handoff.md)（S7 module gate、current-HEAD image与R4-S0 entry boundary）
- [P4-R4-S0 Entry Brief](plans/p4-r4-s0-entry-brief.md)（JobDefinition/checkpoint设计与R4/R5/P5 owner boundary）
- [P4-R4 JobDefinition and Checkpoint Detailed Execution Plan](plans/p4-r4-jobdefinition-checkpoint-execution-plan.md)（S7 module gate pass）
- [P4-R4-S0 Independent Entry Acceptance](plans/p4-r4-s0-entry-acceptance.md)（pass）
- [P4/R4 JobDefinition and Checkpoint Handoff](plans/p4-r4-jobdefinition-checkpoint-handoff.md)（S7 module gate、current-HEAD image与P4-R5-S0 entry boundary）
- [P4-R5 Retry, Takeover and Effect Recovery Design](plans/p4-r5-retry-takeover-effect-recovery-design.md)（design accepted；S7 module gate pass）
- [P4-R5-S0 Entry Brief](plans/p4-r5-s0-entry-brief.md)（S0 accepted；owner/reopen和authorization boundary）
- [P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](plans/p4-r5-retry-takeover-effect-recovery-execution-plan.md)（S7 module gate pass）
- [P4-R5-S0 Independent Entry Acceptance](plans/p4-r5-s0-entry-acceptance.md)（pass）
- [P4/R5 Retry, Takeover and Effect Recovery Handoff](plans/p4-r5-retry-takeover-effect-recovery-handoff.md)（S7 module gate、current-HEAD image与P4-R6-S0 entry boundary）
- [P4-R6-S0 Entry Brief](plans/p4-r6-s0-entry-brief.md)（historical entry brief；S0已由独立acceptance接受）
- [P4-R6/R1 Registry-Name Contract Reopen](plans/p4-r6-r1-registry-name-contract-reopen.md)（bounded `/` grammar amendment）
- [P4-R6-S0 Finding Disposition](plans/p4-r6-s0-finding-disposition.md)（historical reopen；remediation已闭合）
- [P4-R6-S0 Independent Entry Acceptance](plans/p4-r6-s0-independent-entry-acceptance.md)（pass）
- [P4-R6-S6 Container and Provenance Evidence](plans/p4-r6-s6-container-provenance-evidence.md)（container gate pass）
- [P4-R6-S7 Final Handoff](plans/p4-r6-s7-final-handoff.md)（`p4_r6_exit: pass`）
- [P5 Business Vertical Slices Design Baseline](plans/p5-business-vertical-slices-design.md)（总体设计accepted；implementation等待P4-R6 exit）
- [P5-5A Baseline Acceptance](plans/p5-5a-baseline-acceptance.md)（historical；superseded by 5A slice exit / 5B-S0）
- [P5-5A-S0 Entry Brief](plans/p5-5a-s0-entry-brief.md)（historical input；superseded by P5-5B-S0）
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
- [纵切与阶段设计、执行计划及独立审核指南](guides/slice-design-execution-and-review-guide.md)（参考指南；含定向修订与整体返工标准）
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
- [ADR 0001](adr/0001-python-rust-hybrid-compute-strategy.md)–[ADR 0017](adr/0017-sql-spelling-declared-type-unification.md)

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

正式文档之间发生冲突时，应先暂停实现，明确语义 owner，并通过修改正式文档或新增 ADR 收口；
不能依靠兼容代码长期维持两套含义。`docs/backend-vnext/contracts/`、`capabilities/`、
`flows.md`、`operations.md`、`artifacts.md`、`identity-and-digests.md`、
`implementation-boundary.md`和`modules.md`是non-authoritative historical oracle，只用于行为与
fixture追溯；其中的同步Preview、`START_REVIEW`、Archive/Repository ref写入或旧状态名不得反向
覆盖当前P5 authority。

当前阶段：`phase_2_complete: yes`；P3 final closure `p3_exit: pass`；P4-R1至P4-R6均已
exit/pass。P5总体设计基线accepted；P5-5A slice exit `pass`；P5-5B gate evidence @
`460d6f5b` 经独立 acceptance 复核，`p5_5b_slice_exit: pass`。P5-5B 的历史 implementation
authority 已消费并关闭；5B exit 本身不授权新的 P5-5B 改动、P5-5C 或 production deployment。
其后 P5-5C 已完成并由 [S5 Independent Acceptance](plans/p5-5c-s5-independent-acceptance.md)
声明 `p5_5c_slice_exit: pass`，历史 implementation authority 已消费并关闭。
5D 文档及固定归属 Contract 3.0.0 已接受，四项文档 finding 全部关闭；5D implementation 与 production deployment 未授权。
全局 `p3_implementation_authorized: no`。P4 专用入口见
[P4 Active Context Index](plans/p4-active-context-index.md)；当前默认入口是 P5 baseline、5D accepted 文档入口与 5C exit。

完整对外接口见
[P2 External Interface Handoff](plans/p2-external-interface-handoff.md)。

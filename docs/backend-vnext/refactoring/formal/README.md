# Formal Refactoring Documents

本目录保存已经讨论收口、作为后续设计和实现依据的正式重构文档。

正式文档必须：

- 声明状态、owner 或适用阶段。
- 只记录最终规则，不复制讨论过程。
- 明确依赖方向、兼容性和验收标准。
- 发生关键变更时同步更新 contract tests、golden fixtures 或 ADR。

当前内容：

- [Architecture and Refactoring Plan](architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](plans/implementation-stages.md)
- [DX Cross-Phase Interface Reconciliation](plans/dx-cross-phase-interface-reconciliation.md)
- [S02 Code Cleanup Execution Checklist](plans/s02-code-cleanup-execution-checklist.md)
- [Phase 1 Implementation Design and Delivery Plan](plans/phase-1-implementation-design-and-delivery-plan.md)（历史设计）
- [Phase 2 Implementation Design and Delivery Plan](plans/phase-2-implementation-design-and-delivery-plan.md)
- [P2-R1 Runtime and Provider Feasibility Contract](plans/p2-r1-runtime-provider-feasibility.md)
- [P2-R1 v8 Formal Go Decision](plans/p2-r1-v8-go-decision-2026-08-05.md)
- [P2-R1 v8 Formal Archive](plans/p2-r1-v8-formal-80aff3e-2026-08-05/README.md)
- [P2 Versioned Repository Implementation Design](plans/p2-versioned-repository-implementation-design.md)
- [P2 Versioned Repository Execution Checklist](plans/p2-versioned-repository-execution-checklist.md)
- [P2-R4 Async Versioned Import Detailed Implementation Design](plans/p2-r4-async-versioned-import-implementation-design.md)
- [P2-R4 Async Versioned Import Staged Execution Plan](plans/p2-r4-async-versioned-import-execution-plan.md)
- [P2-R5 Commit-pinned Read Staged Execution Plan](plans/p2-r5-commit-pinned-read-execution-plan.md)
- [P2-R6 Operational Closure Staged Execution Plan](plans/p2-r6-operational-closure-execution-plan.md)
- [P2-R6-EXT-W1 ENUM/SET Import Design](plans/p2-r6-ext-w1-enum-set-import-design.md)
- [P2-R6-EXT-W1 ENUM/SET Import Execution Plan](plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
- [Proportional Assurance and Risk-Based Verification Policy](policies/proportional-assurance-and-risk-based-verification-policy.md)
- [Rust Safety and Performance Policy](policies/rust-safety-and-performance-policy.md)
- [Contract Taxonomy and Ownership](contracts/contract-taxonomy-and-ownership.md)
- [Business Lifecycle and State Contract](contracts/business-lifecycle-and-state.md)
- [External Effect and Recovery Contract](contracts/external-effect-and-recovery.md)
- [Shared Canonical Encoding Contract](contracts/shared-canonical-encoding.md)
- [Canonical Encoding Vector Schema — Historical](contracts/canonical-encoding-normative-vector-schema.md)
- [Canonical Row Hash Compute Boundary Contract](contracts/canonical-row-hash-compute-boundary.md)
- [Correctness Golden and Fixture Contract](contracts/fixture-oracle-and-conformance.md)
- [Canonical Storage and Repository Boundary Contract](contracts/canonical-storage-and-repository-boundary.md)
- [Repository Service Contract](contracts/repository-service.md)
- [Performance Measurement Guidance](contracts/performance-measurement-and-baseline.md)
- [ADR 0001: Python/Rust Hybrid Compute Strategy](adr/0001-python-rust-hybrid-compute-strategy.md)
- [ADR 0002: Minimal Persisted Business State](adr/0002-minimal-persisted-business-state.md)
- [ADR 0003: Evidence-First External Effect Reconciliation](adr/0003-external-effect-reconciliation.md)
- [ADR 0004: Raw Source Artifact and Canonical Dolt Storage](adr/0004-raw-source-artifact-and-canonical-dolt-storage.md)
- [ADR 0005: Shared Canonical Encoding](adr/0005-shared-canonical-encoding.md)
- [ADR 0006: Language-Neutral Fixture Oracle](adr/0006-language-neutral-fixture-oracle.md)（被ADR 0010替代）
- [ADR 0007: vNext Performance Baseline Authority](adr/0007-vnext-performance-baseline-authority.md)（被ADR 0010替代）
- [ADR 0008: Generic Dual-Store Repository and Caller-Selected Rigor](adr/0008-generic-dual-store-and-caller-selected-rigor.md)（WP1-R1后被替代）
- [ADR 0009: Proportional Assurance and Trusted Internal Repository](adr/0009-proportional-assurance-and-trusted-internal-repository.md)
- [ADR 0010: Minimal Golden and Ordinary CI](adr/0010-minimal-golden-and-ordinary-ci.md)
- [ADR 0011: Artifact Directory-Broker Reclaim](adr/0011-artifact-directory-broker-reclaim.md)（被ADR 0012替代）
- [ADR 0012: Cooperative Artifact Cleanup and Proportional Assurance](adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)
- [ADR 0013: ENUM/SET v1 Import Semantics](adr/0013-enum-set-v1-import-semantics.md)

## 权威关系

- Architecture 定义总体边界与依赖方向；Implementation Stages 定义交付顺序和 gate。
- Cross-stage policy定义不属于业务contract、但必须由工程和CI持续执行的安全、工具链与实现约束。
- 比例化保障与风险验证policy适用于Phase 0–9及后续维护；专项ADR/contract只能在有明确
  威胁、损失或consumer依据时提高保障，不能在实现评审中静默扩大威胁模型。
- Contract 是字段语义、状态、byte contract、artifact、fixture 和 measurement 的 normative owner；ADR 只记录为何选择该方案，并链接 contract，不复制精确状态表或字段表。
- 同一规则只在 owning contract 中定义。Architecture、计划和其他 contract 只引用，不建立第二份规范。
- `temporary/` 只保存活动中的讨论或执行协调，不拥有正式语义。结论formalized且执行
  完成后应删除过期材料，Git历史作为归档；不得为保留历史再复制一套authority。
- Legacy 只作为行为与 fixture 发现 oracle，不拥有 vNext 内部结构或性能目标。

正式文档之间发生冲突时，应先暂停实现，明确语义 owner，并通过修改正式文档或新增 ADR 收口；不能依靠兼容代码长期维持两套含义。

当前阶段：S02已完成，P2整体设计已收口。旧traceability/F0 report、generic
conformance architecture、formal baseline lifecycle和exact-commit exit不再是
authority。P2-R1 v8 formal 已通过，默认 provider 为Candidate A offline CLI，
Candidate B保留但默认禁用；P2-R2至P2-R4已通过。P2-R5 functional exit complete，
P2-R6-S0 design freeze complete、S1 implementation ready；R6-EXT-W1 Stage H
独立 validator gate review `pass`，五份 v1 digest 已发布；下一步为 Stage I
S6 capacity / W2；`R6-EXT-W1=no`，
`P2-R6-S6_ready=yes`；`production_retest_required=yes`，
`phase_2_complete=no`；
P3 design尚未开始。完整handoff见
[P2-R5 Commit-pinned Read Staged Execution Plan — P2-R5-S7 final handoff — 2026-08-12](plans/p2-r5-commit-pinned-read-execution-plan.md#p2-r5-s7-final-handoff--2026-08-12)。
R6执行边界见
[P2-R6 Operational Closure Staged Execution Plan](plans/p2-r6-operational-closure-execution-plan.md)。
P3完整设计只在P2-R6通过后开始，并从全局比例化保障policy的轻量风险登记开始；不得把
Repository专项历史安全机制复制为P3默认边界。

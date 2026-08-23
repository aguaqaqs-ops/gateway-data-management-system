# Formal Refactoring Documents

本目录保存已经讨论收口、作为后续设计和实现依据的正式重构文档。

正式文档必须：

- 声明状态、owner 或适用阶段。
- 只记录最终规则，不复制讨论过程。
- 明确依赖方向、兼容性和验收标准。
- 发生关键变更时同步更新 contract tests、golden fixtures 或 ADR。

当前内容：

- [P3 Active Context Index](plans/p3-active-context-index.md)（P3 设计默认入口）
- [P2 External Interface Handoff](plans/p2-external-interface-handoff.md)（封印 candidate/image、支持面、限制、reopen）
- [P2–P3 Cleanup Manifest](plans/p2-p3-cleanup-manifest.yaml)
- [Architecture and Refactoring Plan](architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](plans/implementation-stages.md)
- [DX Cross-Phase Interface Reconciliation](plans/dx-cross-phase-interface-reconciliation.md)
- [P2-R1 Runtime and Provider Feasibility Contract](plans/p2-r1-runtime-provider-feasibility.md)（pytest methodology 指针；不是 P3 设计入口）
- [P2-R5 Commit-pinned Read Staged Execution Plan](plans/p2-r5-commit-pinned-read-execution-plan.md)（package README 唯一指针；不是 Phase 2 完成 authority）
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
- [P3-R4 Storage Projection Design Baseline](plans/p3-r4-storage-projection-design.md)
- [P3-R4 Storage Projection Execution Plan](plans/p3-r4-storage-projection-execution-plan.md)
- [P3-R4 Storage Projection and Canonicalization Handoff](plans/p3-r4-storage-projection-handoff.md)
- [P3-R5 Comparison Design Baseline](plans/p3-r5-comparison-design.md)（R5 formal design；detail plan accepted for staged planning）
- [P3-R5 Comparison Execution Plan](plans/p3-r5-comparison-execution-plan.md)（S8 module gate complete；R5 gate pass；implementation authorization pending）
- [P3-R5 Comparison Handoff](plans/p3-r5-comparison-handoff.md)（R5 gate / R6 entry；source SHA、验证证据、deferred register）
- [P3-R5-S0 Entry and Budget Freeze](plans/p3-r5-s0-entry-and-budget-freeze.md)（S0 complete；不授权实现）
- [P3-R6 Risk, Surface and Bundle Design Baseline](plans/p3-r6-risk-surface-bundle-design.md)（R6 accepted design；不授权实现）
- [P3-R6 Risk, Surface and Bundle Execution Plan](plans/p3-r6-risk-surface-bundle-execution-plan.md)（S0-S7 complete/pass；current-candidate gate revalidated；implementation authorization pending）
- [P3-R6-S0 Entry and Budget Freeze](plans/p3-r6-s0-entry-and-budget-freeze.md)（S0 complete；不授权实现）
- [P3-R6 Risk, Surface and Bundle Handoff](plans/p3-r6-risk-surface-bundle-handoff.md)（R6 gate pass；R7 entry；不授权全局实现）
- [P3-R7 Mutation and Target Closure Design Baseline](plans/p3-r7-mutation-target-closure-design.md)（R7 accepted design；S0 complete；不授权实现）
- [P3-R7 Mutation and Target Closure Execution Plan](plans/p3-r7-mutation-target-closure-execution-plan.md)（S0-S7 complete/pass；R7 gate pass；implementation authorization pending）
- [P3-R7-S0 Entry and Budget Freeze](plans/p3-r7-s0-entry-and-budget-freeze.md)（S0 complete；R6 upstream applicability re-attested；不授权实现）
- [P3-R7-S6 Independent Owner, Import, Digest and Recovery Review](plans/p3-r7-s6-independent-review.md)（S6 complete/pass；不授权实现）
- [P3-R7 Mutation and Target Closure Handoff](plans/p3-r7-mutation-target-closure-handoff.md)（R7 gate pass；upstream evidence refreshed；no R7 rework；不授权进入 P4）
- [P3 Final Closure and P4/P5 Handoff Execution Plan](plans/p3-final-closure-execution-plan.md)（F0–F5 complete/pass；`p3_exit: pass`；`p4_ready: yes`）
- [P3 Final Closure and P4/P5 Entry Handoff](plans/p3-final-closure-handoff.md)（P4/P5 entry boundary）
- [P3-FINAL F5 Independent Acceptance Record](plans/p3-final-closure-f5-independent-acceptance.md)（Phase 3 exit pass）
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
- `temporary/` 不拥有正式语义。P3 清理入口是本目录的 P3 Active Context Index、
  P2 External Interface Handoff、cleanup manifest，以及 annotated tag
  `docs/p2-p3-cleanup-pre-20260817` 与 `docs/p2-p3-cleanup-final-20260817`。
  不得为保留历史再复制一套 authority。
- Legacy 只作为行为与 fixture 发现 oracle，不拥有 vNext 内部结构或性能目标。

正式文档之间发生冲突时，应先暂停实现，明确语义 owner，并通过修改正式文档或新增 ADR 收口；不能依靠兼容代码长期维持两套含义。

当前阶段：S02已完成，P2整体设计已收口。旧traceability/F0 report、generic
conformance architecture、formal baseline lifecycle和exact-commit exit不再是
authority。P2-R1 v8 formal 已通过，默认 provider 为Candidate A offline CLI，
Candidate B保留但默认禁用；P2-R2至P2-R4已通过。P2-R5 functional exit complete，
P2-R6-S0 design freeze complete、S1-S7 implementation/evidence gates complete；R6-EXT-W1 Stage I
S6 capacity / W2 / concurrency matrix `pass`，`R6-EXT-W1=yes`，
`P2-R6-S6_ready=yes`；S7 final handoff `S7_exit: pass`、`S8_ready: yes`；S8 final
handoff `S8_exit: pass`、`S9_ready: yes`；S9 final handoff `S9_exit: pass`、
`candidate_seal: pass`、`S10_ready: yes`；S10 final handoff `S10_exit: pass`、
`S11_ready: yes`；S11 final handoff `S11_exit: pass`、`phase_2_complete: yes`；
`production_retest_required=no`。P3 design 已完成；P3-R4 module gate `p3_r4_exit: pass`；
P3-R5 module gate `p3_r5_exit: pass`、`p3_r6_ready: yes`；P3-R6 S0-S7 complete/pass，
current candidate `f2d48d876c40dd918878a6e5215c57daf7920766` 已重新验收；P3-R7 upstream
applicability 已在同一候选重新确认，R7 无需返工且未进入 P4。P3 final closure
`p3_exit: pass`、`p4_ready: yes`；`p4_implementation_authorized: no_until_p4_entry_acceptance`。
全局 `p3_implementation_authorized: no`，不得把任何 P3 module handoff 当作 Phase 3 production
integration authorization。默认入口见
[P3 Active Context Index](plans/p3-active-context-index.md)。完整对外接口见
[P2 External Interface Handoff](plans/p2-external-interface-handoff.md)。
P2-R5 execution plan 仍被 package README 引用，但不是 Phase 2 完成 authority。
R5 implementation 从 R5 详细计划开始，并从全局比例化保障 policy 的轻量风险
登记开始；不得把 Repository 专项历史安全机制复制为 P3 默认边界。

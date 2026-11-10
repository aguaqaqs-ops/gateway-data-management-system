# Formal Refactoring Documents

本目录保存正式 Contract、政策、ADR、架构、阶段计划与历史证据。正式语义应声明状态和 owner，并明确依赖方向与验收标准；阶段记录中的历史结论按其固定候选解释。

## 当前默认入口

[Current Context Index](plans/current-context-index.md) 是当前检索入口。2026-11-10 已核 P6 exit；P7-S1a A 文档/设计入口已获 A_GO 并合入 main，Contract 目标仍待实现，不表示 B–G 产品或 S1a exit 已通过。该索引给出固定提交、核收依据及当前授权适用边界，不复制产品规则。

## 现行 owner 导航

| 问题 | 权威入口 |
| --- | --- |
| 规则归属与分类 | [Contract Taxonomy and Ownership](contracts/contract-taxonomy-and-ownership.md) |
| 业务对象、scope、Head、提交与归档 | [Business Lifecycle and State](contracts/business-lifecycle-and-state.md) |
| 存储、artifact 与 Repository 边界 | [Canonical Storage and Repository Boundary](contracts/canonical-storage-and-repository-boundary.md) |
| operation、checkpoint、恢复与完整性 | [Operation Lifecycle and Integrity](contracts/operation-lifecycle-and-integrity.md) |
| 外部 effect 与恢复 | [External Effect and Recovery](contracts/external-effect-and-recovery.md) |
| mutation / ChangeSet | [Storage Mutation and Change Set](contracts/storage-mutation-and-change-set.md) |
| Repository Service | [Repository Service](contracts/repository-service.md) |
| 编码与 fixture | [Shared Canonical Encoding](contracts/shared-canonical-encoding.md)、[Correctness Golden and Fixture](contracts/fixture-oracle-and-conformance.md) |
| 外部同步、ruleset | [External Target Sync and Recovery](contracts/external-target-sync-and-recovery.md)、[Ruleset Activation and Migration](contracts/ruleset-activation-and-migration.md) |
| 测量 | [Performance Measurement Guidance](contracts/performance-measurement-and-baseline.md) |
| 跨阶段工程保障 | [Proportional Assurance and Risk-Based Verification Policy](policies/proportional-assurance-and-risk-based-verification-policy.md)、[Rust Safety and Performance Policy](policies/rust-safety-and-performance-policy.md) |

总体模块与依赖方向见 [Architecture and Refactoring Plan](architecture/architecture-and-refactoring-plan.md)，交付顺序见 [Implementation Stages](plans/implementation-stages.md)。两文档的阶段同步由原 owner 负责；当前阶段先核上方索引。参考方法见 [纵切与阶段设计、执行计划及独立审核指南](guides/slice-design-execution-and-review-guide.md)。

ADR 按问题追溯：[0001 Python/Rust](adr/0001-python-rust-hybrid-compute-strategy.md)、[0009 比例化保障](adr/0009-proportional-assurance-and-trusted-internal-repository.md)、[0010 Golden/CI](adr/0010-minimal-golden-and-ordinary-ci.md)、[0012 Cleanup](adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)、[0017 SQL 类型](adr/0017-sql-spelling-declared-type-unification.md)、[0018 Comparison](adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)–[0021 Flow-neutral Entry](adr/0021-flow-neutral-comparison-entry.md)。其他正式 ADR 继续保留在 `adr/`。

## 历史入口与恢复

- P6：附注 tag `p6-exit` → `b0fc25e881cb4ce39b1cc847bad92b4ccb06b809`；[最终报告与 receipt map](plans/p6-s6-report.md)、[III 执行与失败记录](plans/p6-s6-iii-execution.md)、[协调记录](plans/p6-s6-coordination.md)。tag 仅签署所列六包、本地容器及 fresh t4 最小链，历史失败/UNKNOWN/取消项与维护限制仍保留。
- P5：tag `p5-exit`；[Exit Review](plans/p5-exit-review.md)、[修复 handoff](plans/p5-exit-fix-handoff.md)、[架构收口设计](plans/p5-arch-closure-design.md)、[执行计划](plans/p5-arch-closure-execution-plan.md)及[治理记录](plans/p5-arch-closure-post-s1-governance-plan.md)。各纵切最终结果见 [5A handoff](plans/p5-5a-s6-handoff.md)、[5B S8 handoff](plans/p5-5b-s8-handoff.md)、[5C 独审](plans/p5-5c-s5-independent-acceptance.md)、[5D exit](plans/p5-5d-slice-exit-final.md)、[5E exit](plans/p5-5e-slice-exit-final.md)。这些是已结束阶段，不授予新的产品或 production 权限。
- P4：[Active Context Index](plans/p4-active-context-index.md) 为 P4 专用入口；[R2 最终 handoff](plans/p4-r2-durable-store-atomic-transition-handoff.md)、[R2 S6 独审](plans/p4-r2-s6-independent-review.md)与 [R6 最终 handoff](plans/p4-r6-s7-final-handoff.md)继续保留。R1–R6 其他最终交接仍在 `plans/`。
- P3：[Final Closure and P4/P5 Entry Handoff](plans/p3-final-closure-handoff.md)、[最终独审](plans/p3-final-closure-f5-independent-acceptance.md)；各模块 handoff、设计与 capability oracle 保留。
- P2：[External Interface Handoff](plans/p2-external-interface-handoff.md)；[Runtime/Provider Feasibility](plans/p2-r1-runtime-provider-feasibility.md)有测试/闭包消费者，[Commit-pinned Read Plan](plans/p2-r5-commit-pinned-read-execution-plan.md)保留 package README 指针。
- 历史归档：[P2→P3 manifest](plans/p2-p3-cleanup-manifest.yaml)、[P3→P4 manifest](plans/p3-p4-cleanup-manifest.yaml)、[P3→P4 handoff](plans/p3-p4-cleanup-handoff.md)。原 tag 不变。
- 本次归档：[P6→P7 manifest](plans/p6-p7-documentation-cleanup-manifest.tsv)逐行给出原路径/source_commit/blob/SHA256，恢复见 [当前索引](plans/current-context-index.md#历史追溯与恢复)。三份已关闭中间记录离开当前树，最终原审、handoff、成功和失败证据继续保留。

## 权威关系

Architecture 定义总体边界与依赖方向，Implementation Stages 定义交付顺序和 gate；当前任务的明确授权和固定阶段记录决定执行范围。跨阶段政策规定工程约束；Contract 拥有字段、状态、byte contract、artifact、fixture 与 measurement 语义。ADR 记录选择理由并引用 Contract。计划、索引和 `temporary/` 不建立第二份规范。

旧 `docs/backend-vnext/contracts/`、`capabilities/`、flows/operations/artifacts 等文档作为行为与 fixture oracle；S1a 已合入的目标补充仍须按索引区分“待实现”目标和现行行为，不能把它当已生效源码。Legacy 不拥有 vNext 内部结构或性能目标。正式文档冲突先明确 owner，按适用变更流程收口；不依靠兼容层维持两套含义。

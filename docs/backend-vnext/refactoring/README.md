# Backend vNext Refactoring

本目录集中保存 backend vNext 整体重构文档。这里描述目标架构和实施路线，不替代 capability、flow、operation、contract 或 ADR 的专项设计。

文档分为两类：

- [Formal](formal/README.md)：已经讨论收口、作为设计和实现依据的正式文档。
- [Temporary](temporary/README.md)：讨论提案、开放问题、实验和阶段性结论，不作为正式 contract。

## 阅读顺序

1. [P3 Active Context Index](formal/plans/p3-active-context-index.md)：P3 设计默认入口与 allowlist。
2. [P2 External Interface Handoff](formal/plans/p2-external-interface-handoff.md)：封印 candidate/image、支持面、限制与 reopen。
3. [Architecture and Refactoring Plan](formal/architecture/architecture-and-refactoring-plan.md)：目标架构、模块职责、依赖规则、Python/Rust 分工和独立 Repository Service 边界。
4. [Implementation Stages](formal/plans/implementation-stages.md)：从现状基线到生产切换的阶段顺序、交付物、门禁和纵向业务切片。
5. [Operations](../operations.md)、[Flows](../flows.md)：P3 capability 设计 oracle，不是 Repository Service wire。

Phase 1 正式设计：

- [Contract Taxonomy and Ownership](formal/contracts/contract-taxonomy-and-ownership.md)：Contract 分类、语义 owner、ownership matrix、版本和变更治理。
- [ADR 0001: Python/Rust Hybrid Compute Strategy](formal/adr/0001-python-rust-hybrid-compute-strategy.md)：Python 控制面、Rust 数据面、首版内核选择和跨语言门禁。

Repository 专项参考：

- [Repository Import](../capabilities/repository-import.md)
- [Repository Ref Materialization](../capabilities/repository-ref-materialization.md)
- [Repository Import Boundary ADR](../adr/0001-snapshot-table-and-dolt-import-boundary.md)
- [Dolt Native Provider ADR](../adr/0003-dolt-native-provider-selection.md)

Capability 和数据契约参考：

- [Target Modules](../modules.md)
- [Artifacts](../artifacts.md)
- [Snapshot Contract](../contracts/snapshot.md)
- [Snapshot Table Access Contract](../contracts/snapshot-table-access.md)
- [Comparison Contract](../contracts/comparison.md)
- [Risk Contract](../contracts/risk.md)
- [Comparison Surface Contract](../contracts/comparison-surface.md)
- [Comparison Bundle Contract](../contracts/comparison-bundle.md)

## 文档权威顺序

- 本目录总纲决定整体模块边界和长期依赖方向。
- `formal/plans/implementation-stages.md` 决定重构执行顺序和阶段门禁。
- `formal/contracts/` 决定重构后的稳定 contract 分类与语义；后续正式 capability contract 也必须位于 `refactoring/formal/` 体系或由其明确引用。
- 旧 `contracts/` 和 capability 专项文档只作为业务语义、fixture 和实现 oracle，直到对应正式重构 contract 完成替代。
- ADR 决定已经收口的关键技术选择。
- 历史 `notes/` 与已完成 execution/review 已归档到 tag `docs/p2-p3-cleanup-pre-20260817`，不自动提升为长期架构约束。

发现冲突时，不通过代码兼容层同时保留两套含义；先记录冲突，明确 owner，再更新总纲、专项 contract 或新增 ADR。

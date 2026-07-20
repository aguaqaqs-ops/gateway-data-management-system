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
- [Rust Safety and Performance Policy](policies/rust-safety-and-performance-policy.md)
- [Contract Taxonomy and Ownership](contracts/contract-taxonomy-and-ownership.md)
- [Business Lifecycle and State Contract](contracts/business-lifecycle-and-state.md)
- [External Effect and Recovery Contract](contracts/external-effect-and-recovery.md)
- [Shared Canonical Encoding Contract](contracts/shared-canonical-encoding.md)
- [Canonical Encoding Normative Vector Schema](contracts/canonical-encoding-normative-vector-schema.md)
- [Canonical Row Hash Compute Boundary Contract](contracts/canonical-row-hash-compute-boundary.md)
- [Fixture Oracle and Conformance Contract](contracts/fixture-oracle-and-conformance.md)
- [Canonical Storage and Repository Boundary Contract](contracts/canonical-storage-and-repository-boundary.md)
- [Performance Measurement and Baseline Contract](contracts/performance-measurement-and-baseline.md)
- [ADR 0001: Python/Rust Hybrid Compute Strategy](adr/0001-python-rust-hybrid-compute-strategy.md)
- [ADR 0002: Minimal Persisted Business State](adr/0002-minimal-persisted-business-state.md)
- [ADR 0003: Evidence-First External Effect Reconciliation](adr/0003-external-effect-reconciliation.md)
- [ADR 0004: Raw Source Artifact and Canonical Dolt Storage](adr/0004-raw-source-artifact-and-canonical-dolt-storage.md)
- [ADR 0005: Shared Canonical Encoding](adr/0005-shared-canonical-encoding.md)
- [ADR 0006: Language-Neutral Fixture Oracle](adr/0006-language-neutral-fixture-oracle.md)
- [ADR 0007: vNext Performance Baseline Authority](adr/0007-vnext-performance-baseline-authority.md)

## 权威关系

- Architecture 定义总体边界与依赖方向；Implementation Stages 定义交付顺序和 gate。
- Cross-stage policy定义不属于业务contract、但必须由工程和CI持续执行的安全、工具链与实现约束。
- Contract 是字段语义、状态、byte contract、artifact、fixture 和 measurement 的 normative owner；ADR 只记录为何选择该方案，并链接 contract，不复制精确状态表或字段表。
- 同一规则只在 owning contract 中定义。Architecture、计划和其他 contract 只引用，不建立第二份规范。
- `temporary/` 保存讨论证据与 formalization mapping，不因内容 formalized 而移动、改名或删除；若 temporary 与旧 formal 冲突，以已经 Accepted 的 owner contract/ADR 为准。
- Legacy 只作为行为与 fixture 发现 oracle，不拥有 vNext 内部结构或性能目标。

正式文档之间发生冲突时，应先暂停实现，明确语义 owner，并通过修改正式文档或新增 ADR 收口；不能依靠兼容代码长期维持两套含义。

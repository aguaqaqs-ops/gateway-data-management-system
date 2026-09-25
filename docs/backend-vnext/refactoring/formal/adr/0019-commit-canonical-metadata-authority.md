# ADR 0019: Commit Canonical Metadata Authority

状态：Proposed（repository owner 决定 2026-09-25；待 P5 架构收口 S0 独立文档审核）

日期：2026-09-25

决策 owner：Backend vNext Snapshot Materialization / Submission Application / History Application

关联阶段：P5 架构收口 S2；取代 P3-R3 hidden summary 条款与 5E 设计 §6.6 的相应部分

## Context

- P3-R3 规定 Repository-ref 物化以 hidden FINAL SnapshotSummary 为权威，缺失即失败，不从 catalog 与行重建。
- 实际上全仓没有写入方（R3-D02 一直延期），HTTP Arrow adapter 改为从行重建 summary，版本字段取运行时常量，`repository_ref.py` 随后再读一遍全表做交叉校验。结果是：
  - 每次物化都要全表读两遍；
  - 交叉校验等于同一数据读两次；
  - 无法得知 commit 是按哪版规则生成的；
  - 5E-S2 围绕这项校验建立的 integrity incident 机制，没有可靠的证据来源。
- 另外，`NO_CANONICAL_CHANGE` 用的是 Preview bundle digest 与“基线自比流水线”的 bundle digest，AcceptSubmit T1 需要物化基线。
- 与此同时，每个 Submission 已经持久化了 `CanonicalizationManifest` 的 ref 与 digest。

## Decision

1. **commit 规范元数据的权威是 Backend 持有的 `CanonicalizationManifest`**，经 Submission 取得。供给时的初始空 BaselineNode 定义为与规则集无关的空规范状态。
   - Repository 中不写隐藏表，Repository wire 不变。
2. **Repository-ref 物化改为单遍读取。**
   - provider 协议删除 hidden summary；`canonical_binding` 由 Application 按 commit 元数据提供；
   - catalog 行数与读取行数不一致时，作为普通失败处理；
   - adapter 只负责传输，不计算摘要。
3. **不做读回校验。** 规范编码的一致性由共享编码、契约与 golden 测试以及 Repository STRUCTURAL 校验保证。
4. **`NO_CANONICAL_CHANGE` 由 Preview 计算的两侧规范状态摘要判定**，二者都持久化到 PreviewResult；AcceptSubmit 不再物化基线。
5. **History 的规则集校验改用真实的 commit 元数据。**
6. **删除以 hidden summary 为生产者的 History compare integrity incident**（记录、受理阻断、ack 路由、control DB 表），读取不一致作为普通失败处理。ADR 0016 的 Operation integrity 不受影响。

## Alternatives

- **按原设计在 Dolt 中写隐藏 summary 表**：放弃。Repository 会混入业务专属表，需要从业务 catalog 过滤，而且与已持久化的 manifest 重复。
- **不设任何摘要权威**：放弃。无变化判定仍需全量读基线，也无法回答 commit 的规则版本。
- **Submit 完成时做一次读回校验**：暂不采用。它是唯一有依据的读回场景（ADR 0017 类漂移），代价是每次提交多一次全量读；如再次出现写入形态漂移，按下方重开条件处理。

## Consequences

- Preview 基线物化与 History 节点物化各减少一次全表读取；T1 不再执行比较流水线。
- 5E-S2 的 integrity 机制与 v6 表被移除（在 5E slice exit 之后执行）。
- 未来的 `SYSTEM_MIGRATION` commit 必须同时登记 manifest。

## Required Verification

- 单遍物化：读取次数、行数不一致失败、`snapshot_id` 确定性。
- `NO_CANONICAL_CHANGE` 判定及过期 Preview 被拒绝。
- History 在节点规则集 digest 不一致时稳定失败。
- 删除 integrity 后 OpenAPI 与路由测试同步更新。

## Reopen conditions

- 出现 Repository 写入形态与 Backend 规范形态漂移的可复现故障，此时评估在 Submit 完成时读回。
- 出现不经 Submit 产生的业务 commit，且无法登记 manifest。
- 需要从 Repository 独立恢复 commit 元数据（例如 control DB 丢失后的重建）。

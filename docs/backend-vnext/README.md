# 后端 vNext

本目录保存 gateway 后端 vNext 的设计、Contract 与阶段记录。vNext 不保留旧后端兼容或数据迁移路径；旧系统只作行为与数据格式参考。

## 当前默认入口

从 [Current Context Index](refactoring/formal/plans/current-context-index.md) 开始。最近核对为 2026-11-10：P6 已退出；P7-S1a A 文档/设计入口已获 A_GO 并合入 main，Contract 目标仍待实现；这不表示后续产品或 S1a exit 通过。固定来源和核收依据见该索引。

- [Formal 文档入口](refactoring/formal/README.md)：现行 owning Contract、政策、ADR、阶段与历史恢复。
- [Refactoring 说明](refactoring/README.md)：文档角色与阅读顺序。
- [测试约定](testing-conventions.md)及仓库 [AGENTS](../../AGENTS.md)：执行要求；当前任务的明确授权与适用范围仍须先核对。

## 文档角色

- `refactoring/formal/contracts/` 拥有正式字段、状态、artifact、byte contract 与边界语义；政策规定跨阶段工程要求，ADR 记录选择理由。按 [Contract Taxonomy and Ownership](refactoring/formal/contracts/contract-taxonomy-and-ownership.md) 找唯一 owner。
- `refactoring/formal/architecture/` 与 `plans/` 保存总纲、交付顺序及阶段证据；当前状态沿 Current Context Index 查，不能从历史的“下一步”推导本轮授权。
- `contracts/`、`capabilities/`、`flows.md`、`operations.md`、`artifacts.md`、`identity-and-digests.md`、`implementation-boundary.md` 和 `modules.md` 保留业务/fixture oracle。其历史描述不覆盖现行 formal owner；S1a 已合入的目标补充仍标“待实现”，不能当作当前源码已生效行为。
- `glossary.md` 是术语入口；`testing-fixtures.md` 说明 fixture 材料语义。源码在仓库 `vnext/`，前端独立在 `frontend/`。

## 历史与恢复

P5/P4/P3 的最终交接与原始成功/失败继续保留，阶段入口见 [formal 历史导航](refactoring/formal/README.md#历史入口与恢复)。历史授权仅适用其阶段与时点，不构成本轮实施许可。

本次三份已关闭中间记录的原路径、完整来源提交、blob 与 SHA256 见 [P6→P7 归档清单](refactoring/formal/plans/p6-p7-documentation-cleanup-manifest.tsv)。恢复方式见 [当前索引](refactoring/formal/plans/current-context-index.md#历史追溯与恢复)。更早归档见 [P2→P3 manifest](refactoring/formal/plans/p2-p3-cleanup-manifest.yaml) 和 [P3→P4 handoff](refactoring/formal/plans/p3-p4-cleanup-handoff.md)。

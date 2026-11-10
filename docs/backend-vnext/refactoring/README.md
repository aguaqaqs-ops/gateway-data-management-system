# Backend vNext Refactoring

本目录集中保存后端重构的目标架构、实施路线与阶段记录。字段、状态与字节语义由专项 owning Contract 定义。

## 阅读顺序

1. [Current Context Index](formal/plans/current-context-index.md)：当前默认入口；P6 已退出，P7-S1a A_GO 与已合入 main 的设计目标、固定核收依据在此核对；产品实现另行验收。
2. [Formal](formal/README.md)：政策、Contract、ADR、总纲及阶段最终交接导航。
3. [Contract Taxonomy and Ownership](formal/contracts/contract-taxonomy-and-ownership.md)：按业务问题找到唯一语义 owner，再读对应源码。
4. [Architecture and Refactoring Plan](formal/architecture/architecture-and-refactoring-plan.md) 与 [Implementation Stages](formal/plans/implementation-stages.md)：总体边界及交付顺序；历史阶段状态不替代当前任务授权，尚待原 owner 同步的状态不在本轮代改。

## 文档权威关系

- `formal/contracts/` 拥有稳定 Contract；跨阶段政策与正式 ADR 的职责见 [formal 权威关系](formal/README.md#权威关系)。计划和索引只引用，不复制规则成为第二权威。
- 旧 `contracts/`、capability、[Operations](../operations.md)、[Flows](../flows.md) 是行为、fixture 与实现 oracle；与 formal owner 冲突时先明确归属。
- [Temporary](temporary/README.md) 不拥有正式语义；已完成过程记录沿 manifest/Git 对象恢复，不能从旧“下一步”推导当前授权。
- [P4 Active Context Index](formal/plans/p4-active-context-index.md) 和 [P2 External Interface Handoff](formal/plans/p2-external-interface-handoff.md) 保留各自历史边界，不是仓库当前默认入口。

当前规则入口和 S1a 特定节点/DC68 输入须分别核对；本轮文档整理角色与静态验证授权来自 [cleanup 提示词](formal/plans/p6-p7-documentation-cleanup-prompt.md)。发现语义冲突时交实际 owner，不通过兼容代码保留两套含义。

# Table Presentation

Backend 的进程内展示 resolver 位于 `capabilities/table_presentation/`。metadata 承接精确 manifest 的冻结注释，resolver 将双侧 raw descriptor 与 metadata 合为 surface 所需的列展示字段。正式字段、列序、固定列、replacement 侧隔离与验证 owner 见 [Table Presentation Contract](../contracts/table-presentation.md)。

BE-b B2 已提供 resolver 与二十条业务列重排；B3/B4 负责 Surface v4 和 Preview/History 发布接线。没有 width、align、hidden、preview-index 专用投影或独立 table-presentation 产物。历史宽度报告只作历史参考，不恢复其生成机制。展示不进入规范状态、comparison 或 risk 身份。

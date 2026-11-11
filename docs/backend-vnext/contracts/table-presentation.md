# Table Presentation Contract

Owner：Backend Table Presentation。当前 resolver 由共同 Preview/History pair pipeline 接入 Surface v4；阶段验收与对外交付状态见 BE-b 交付记录。

展示 metadata 来自精确 frozen CanonicalizationManifest 的 presentation；注释与规范业务 schema、比较键、canonical IPC/Parquet 和 cache identity 分开。metadata 缺注释时合法回退；损坏或缺 required manifest 字段由原 owner 拒绝，不从另一历史版本补写。

`present_columns(table_name, before, current, before_presentation, current_presentation, side)` 产生两侧 raw descriptor 列名并集，每个名字一个 `PresentedColumn`：`name, display_name, scalar_type, nullable, present_in, pinned, display_order`。不根据 comparison selected 列裁剪；before-only、被排除比较和只供浏览的列仍保留。

普通 pair 的数组按列名 UTF-8 字节排序；类型/nullable 有 current 时取 current，否则 before。列名优先 current 非空注释、before 非空注释、标识符。current 列先按业务列序中实际存在的列，再追加 current DDL 次序的未列出列；before-only 按 before DDL 次序追加。无 current 表时，全部按 before 业务规则/DDL 排列。`display_order` 从 0 起唯一连续。固定列为存在的 `no` 与 `name`；缺 `name` 时固定存在的 `description`。

replacement 指定 `side=BEFORE|CURRENT` 时只使用本侧 descriptor 和注释，`present_in` 固定本侧，列序独立从 0 起；不能借对侧同名列注释。表名规则同样优先 current/before/标识符；分侧标题只传本侧 metadata。Surface replacement summary 的字段 owner 见 [Comparison Surface](comparison-surface.md)。

列序 registry 使用 `PRESENTATION_RULES_VERSION=1`，只保留确认的二十条业务重排（九类 IEC104 转发表、device、八类装置测点、fault_msg_cfg、IEC61850 dev_cfg）。规则结果进入 surface 展示字段；不改变 canonical/comparison ruleset digest，也没有独立 table-presentation wire selector。列宽、对齐由前端计算，不提供 hidden/width/align 或旧 preview-index 投影。

权威验证为 `tests/test_table_presentation_resolver.py`；列并集、注释、before-only、分侧和固定列均为纯逻辑，不建 Dolt。Surface 序列化、v4 digest 与 golden 由 Surface owner 和后端 presentation generator 覆盖。

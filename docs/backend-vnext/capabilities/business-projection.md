# Business Projection Capability

本文定义 comparison surface 到业务视图 projection 的实现边界，重点覆盖 secondary-device 的 per-device/per-tab changes 与 risk 聚合。

## 输入与输出

输入由 flow 从 comparison records、risk annotation artifacts、before/current table metadata 和 surface visible tables 构造。输出包含 forward channels、secondary devices、communication protocols、global parameters 和 unparsed tables 五类 projection artifact。

Business projection 不重新计算 diff 或 risk；它只把 canonical records/risk 挂载到业务身份。输出 contract 和各 projection schema version 不因内部索引方式变化。

## 复合信号特殊装置

`SECONDARY_DEVICES` v2 在 `metadata:device` 后插入唯一的 `presentation_kind=COMPOSITE_SIGNAL` item，并从普通装置 item 中剔除 `dev_addr=65532`；原始 `device` 总表与 `device_*` 表不改写。

特殊 item 的 tabs/列继续沿用原始 point table，展示行由 pair-local points artifact 提供。Projection 只合并原始 `device_*` canonical records 与 `composite_signal_point` 公式事实，不在前端重算 diff。points/formulas artifact 构建必须先按 `(source_table, point_gid)` 建立索引，禁止 devices × formulas 交叉扫描。详细合同见 `composite-signal-device.md`。

Dataset Replacement 为 before/current 分别生成 supplemental artifacts；每个特殊 item 只引用所属 side，不构造跨 side 公式 UPDATE。

## Secondary-device 身份规则

- `device_st`、`device_mx`、`device_co` 等 point tables 以 `dev_addr` 归属设备。
- `device_cfg` 以 `gid` 归属设备。
- 一个 change 的 before/current 身份都参与匹配，支持 point 在设备间移动。
- risk annotation 先通过其 entity/row identity keys 连接 canonical change 的 `row_identity`，再按 change 的 before/current 设备身份挂载。
- metadata table `device` 的 change/risk 只进入 metadata item，不广播到普通设备 tabs。
- annotation 在单个 tab 内保持输入顺序并去重；设备 risk summary 由所属 tabs 聚合，保持风险等级和 reason code 的既有顺序语义。

## Secondary-device Tab 可用性

- `tabs[]` 是当前 device 的权威可用 Tab 集合，不表示候选表的全局列表；前端不得再次扫描共享大表推断 Tab。
- before 或 current 任一侧的身份行数大于零，或 canonical records 已提供该身份的 change 证据时，输出对应 Tab；两侧计数均完整且为零时省略。
- metadata-only 明细表由 flow 通过 `SnapshotTableReader.count_column_values()` 获取完整身份计数摘要；摘要存在但为空表示已确认无有效身份行，摘要缺失表示未知。
- 未知侧不得被当作空表。Assembler 保守保留候选 Tab，并按 table/side 输出一次 `SECONDARY_TAB_AVAILABILITY_UNKNOWN` diagnostic。
- 普通 device 可以输出空 `tabs[]`；装置实体仍然保留，由前端显示无明细数据空状态。

## 索引与复杂度

Assembler 在构建 secondary projection 前一次性建立：

```text
table -> changes
table -> risk annotations
table + row_identity -> changes
table + identity_column + identity_value -> before/current row counts
table + identity_column + identity_value -> has_change / risk annotations
```

设备循环只能做索引查询，不允许在每个设备/tab 内重新扫描整表 changes 或 annotations。目标复杂度为 `O(rows + changes + annotations + devices * tabs)`；禁止 `devices * annotations * changes` 的交叉扫描。

metadata-only 表的身份计数只保留 `identity value -> count`，不得在 projection input 中保留整表行。SQL 只解析 `dev_addr/gid` literal，Parquet 只读取目标列，repository-ref 使用 `GROUP BY + COUNT(*)`；任一路径失败时回退完整 row stream，保证结果优先于性能。

计数结果使用独立 cache，key 为不可变 table content digest、compare schema digest 和 canonical column name。正式 upload 使用 artifact store 下的持久 cache；同一 flow 没有可靠摘要时只允许操作级内存复用。cache 不读取 comparison projection intermediate，也不进入 business projection、comparison 或 snapshot digest。

## Flow 埋点

Upload preview 在调用 assembler 前记录 `upload_preview.business_projection.start`，包含 records/risk artifact 数量及 record/annotation 数量；完成后记录 `upload_preview.business_projection` 和 duration。每次身份计数另记录 table、side、column、strategy、cache hit、fallback 和 duration；该性能事件不进入 projection。只有 start 没有 completion 时，可将卡点定位到 business projection，而不是 bundle download 或 frontend parsing。

## 测试要求

- per-device/per-tab change/risk 不广播。
- before/current 身份变化和 annotation 多 key 正确归属且去重。
- duplicate `dev_addr`/`gid` diagnostics 保持。
- 规模测试覆盖约 153 devices、14,790 changes/annotations，并用线性调用次数约束防止交叉扫描回归。

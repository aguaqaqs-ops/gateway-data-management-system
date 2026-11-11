# Row location in Comparison Surface v4

本合同是 [Comparison Bundle v4](comparison-bundle.md#be-b-v4实施中) 的普通行定位部分，没有独立 HTTP 接口或版本轴。`row_location` 在共享 pair pipeline 的 records/risk 之后、surface/bundle 发布之前运行；Preview 与 History 使用同一路径。BE-b 的 fixture/golden、集中门禁与退出仍按[执行计划](../refactoring/formal/plans/be-b-execution-plan.md)收口，本文不构成阶段通过记录。

## 载荷与存在性

locator 是五列 Parquet，字段顺序固定：

| 字段 | Arrow 类型 | nullable |
| --- | --- | --- |
| row_identity | binary(32) | false |
| before_row_index | int64 | true |
| current_row_index | int64 | true |
| before_filter_context_json | utf8 | true |
| current_filter_context_json | utf8 | true |

按 row_identity 原始字节升序，每条实际发布的 STANDARD 普通 ROW_ADDED、ROW_DELETED、ROW_MODIFIED 一行，不能有重复身份。schema/degraded 记录不占行；ordered/blank 使用各自原有位置语义。无已发布普通行记录、replacement 或没有对应 STANDARD family 时不发 locator。发布数量与 native family 的实际数量必须相符。

## 身份与最终位置

唯一身份 owner 是 Rust `comparison/standard.rs`：比较与 `StandardIdentityScanner` 共用 `frame_for`、`row_digest`、`occurrence_digest` 及 keyless selected/excluded 列选择。helper 只编码，不重新执行比较；Python 与浏览器不实现生产身份算法。

每个存在的 bundle 快照侧按**最终选定的 Parquet ref**扫描，包括 export cache 命中与 shared 文件。位置按 file/row-group/batch 的物理遍历计全局 0 起下标。每条记录的每个逻辑存在侧必须恰好匹配一次；缺失、重复或与 ROW_ADDED/ROW_DELETED 侧存在性矛盾都失败，不静默撤去 locator。

keyless occurrence 在同一表/侧跨 batch 与 row group 保持计数。第 0 次用规范 row digest，第 n>0 次复用现有 occurrence domain 与 ULEB128(n)。只为命中已发布记录的身份保留位置；同值副本的物理顺序只决定等价副本的位置，不改变 comparison 身份。

最终 Parquet 用同侧 canonical descriptor 校验 raw SHA/size、物理 schema、encoding metadata 与行数。整数 UTF8、float bits、SET 等 client 表示恢复为现有 native canonical profile；规范 scalar 校验与 whole-row framing 仍归原 native owner。原始 DDL 列序与 canonical IPC 列序可以不同，client export 按 canonical_name 取列，再按原输出 schema 写出。

## 缺快照侧上下文

逻辑行存在、没有该侧 bundle 快照且实际导航发布过滤 tabs 时，从同侧已有 canonical 输入经同一个 native identity/occurrence 流取得最小身份上下文，如 `{"gid":7}`。缺列为 `{}`，SQL NULL 为 `{"gid":null}`。类型、安全整数、身份参与比较资格由 [Business Navigation](business-navigation.md) 的原 owner 约束；不从只包含 changed columns 的 records 猜旧值。

有快照侧的 context=null，消费者从 index 对应行取得值；逻辑不存在侧的 index/context 均 null。缺 bundle 快照侧永远不造 index。导航最终为整表入口时，两个 context 字段均 null。producer 先准备位置与证据，待导航决定实际过滤表后只发布一次最终 locator，不发布占位文件。

## 预算与生命周期

所有扫描共享现有 operation M、取消、deadline 与 scratch。native occurrence 状态先预留后增长，每次 batch 的输出、whole-row order keys 及边界副本有 admission；每表/侧 scanner 结束即释放。Parquet raw/footer 与最大 row group 在解码前向同一个 M 预留，输出受既有 records 数量/字节与 scratch 上限约束。

普通表定位发布后清空中间 backing 并归还表级 admission；共享表供 B2 消费 `FilterRecord`，导航完成并发布后释放。operation.resources 保留兜底清理 callback；callback 仅持已清空的壳对象，不能先归还预算仍保留实际 backing。没有跨 operation locator cache、新数据库或恢复状态机。

locator ref 位于 comparison 逻辑位置，完整进入 surface 遍历/重写、ROW_LOCATOR bundle closure、raw 完整性与既有 READY/下载保护。locator 内无 ref；surface digest 排除整个 locator ref，bundle digest 仍绑定其实际 raw 字节。

## 验证 owner

- `test_row_identity_native.py`：独立 Python Shared Kernel oracle 对照 keyed/keyless/columns_added 编码与第三次 occurrence；Rust standard tests 覆盖跨 batch、计数预算与取消。
- `test_row_location.py`：最终重排与跨 row group、混合标量、keyless 多副本、缺 before 快照上下文、不可匹配/歧义拒绝及 backing/admission 释放。
- `test_business_presentation_flow.py`：实际 gid 变化与未改/已改 cfg、EXACT 计数、locator/context、生产 bundle closure。
- 现有 Preview/History、bundle/download/protection 测试拥有 flow 与 lifecycle，不另复制全量 filesystem 故障矩阵。B4 的固定输入/生成输出与 B5 集中门禁仍需各自真实证据。

## 进程内 owner 边界

`row_location/contracts.py` 拥有五列 schema 和 admitted `RowLocationResult`；application 从 row_location root 消费定位/扫描/发布入口。身份策略与 scanner 由 comparison root 提供，`standard_identity_policy` 复用同一 comparison schema/selected/excluded 决定，不让 locator 访问 comparison 私有 row_encoding。现有有界 Parquet writer 由 comparison 公开，最终 client 物理 schema 由 snapshot_materialization 的 `client_parquet_schema` 单一 owner 提供；不复制 codec 或绕过预算。

架构测试登记三个 BE-b owner 及其实际有向依赖，并仅允许 comparison adapter 使用既定 `_standard_identity_scanner_native` 粗粒度入口。table_presentation 合同为纯叶，不反向读取 snapshot；row_location 可消费 navigation/comparison/snapshot/Surface 合同与同 operation 的 Table Access 预算。新调用均走 owner root 或 contracts，既有架构 baseline 保持为空，无新增私有导入豁免。

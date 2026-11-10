# FE3 Q21 比较诊断码后端答复

日期：2026-11-09。接收方：owner 与前端设计会话。

本答复固定核对 FE3b 后端树 `56720104af34a1eb677336f57bdbc07444a56615` 到
FE3c 后端树 `6368c9c40cf08a97eecf2a0c457a6c16ce448080`。
前者取自 `fe-fe3b-exit`（提交 `ed5d2c24e97199db8c9ca840e474a1fdf3633373`），
后者取自提交 `fd9e383d76642037e4b3246c847222ea9483e033`，也等于 `p6-s4-exit:vnext`。
以下新树文件链接和行号均以 **`fd9e383d76`** 为准；标为“旧树”的行号以
**`fe-fe3b-exit`** 为准。后续 main 的 S5 改动不在本答复范围内。

结论：前端可以删除 Q21 所列三个旧码的文案；四个新码若触发，生产入口会转成表级
`DEGRADED` 诊断，而非因这些码使 operation 失败。多列有序行标识并未成为新能力：
两棵树的有效 Table Rules 都限定有序表以 `gid` 标识行、以 `no` 表示位置。

## 1. ROW_IDENTITY_UNSUPPORTED 与多列行标识

**`ROW_IDENTITY_UNSUPPORTED` 已无产生点。** 旧树
`vnext/backend/src/gateway_backend/capabilities/comparison/ordered.py:358–360,420–423`
确实在 `_read_ordered_rows` 中用 `_single_column` 拒绝长度不为 1 的 `row_identity_key`；
该实现已删除，新树的 backend 源码与 Rust 源码均不再包含此码。

需要区分以下三个情况：

| 输入情况 | 新树的处理与依据 |
| --- | --- |
| 合法有序表的 **DDL 主键多列** | 比较仍使用规则确定的单列 `gid`，走正常详细比较；不会因 DDL 主键多列自动产生一个替代码，也不因此使操作失败。Table Rules 的显式键不从 DDL 主键取值：[`table_rules/registry.py:227–240`](../../../../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py#L227-L240)、[`table_rules/resolver.py:178–197`](../../../../../vnext/backend/src/gateway_backend/capabilities/table_rules/resolver.py#L178-L197)（仅 `RAW_PRIMARY_KEY` 使用 DDL 键）；解析后的 key 进入 ordered row identity 见同文件 `92–100`。具体表状态仍由实际 schema、行内容和已有校验决定。 |
| 规则声明有序表的 **有效行标识多列** | 这不是两棵树接受的合法规则。[`table_rules/contracts.py:690–702`](../../../../../vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py#L690-L702) 要求 `compare_key_columns == ("gid",)`，否则规则构造时 `ValueError("ordered rules require key column gid")`；并要求 `gid_no_v1` 和 `position_column == "no"`。此校验在两棵树间未改动，所以不能将旧 helper 的可触发条件等同于旧生产规则可达。它不会先进入比较再输出某个 manifest/surface 表诊断。 |
| 绕开规则校验，手工伪造内部 `OrderedTablePolicy.row_identity_key` 为多列 | 新 Python schema 检查会检查这些列是否存在，但不再检查键长度（[`comparison/ordered.py:80–101`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/ordered.py#L80-L101)）。Rust 的 ordered policy 不接收任意行标识/位置列选择，直接读取 `gid`、`no`（[`comparison/policy.rs:44–64`](../../../../../vnext/rust/gateway-compute-core/src/comparison/policy.rs#L44-L64)、[`comparison/ordered.rs:1843–1848`](../../../../../vnext/rust/gateway-compute-core/src/comparison/ordered.rs#L1843-L1848)），身份摘要也仅编码 `gid`（同文件 `1949–1956`）。如果实际 `gid/no` 与数据合法，可继续详细比较，但这不能作为“支持复合行标识”的承诺。若复合键整体唯一而 `gid` 重复，则按 `gid` 重复降级为 `ROW_IDENTITY_DUPLICATE`，而非继续按复合键配对。 |

规划器把已解析规则传给 ordered policy 的位置是
[`comparison/pair_planning.py:117–140`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/pair_planning.py#L117-L140)，
其中 `order_key=(ordered.position_column,)`、`row_identity_key=ordered.row_identity_key or None`。
没有新增“多列行标识不支持”的替代码；缺列仍用 `ORDERED_REQUIRED_COLUMN_MISSING`，
`gid` 重复仍用 `ROW_IDENTITY_DUPLICATE`，诊断位置见 §3.1。

现有测试依据：

- [`test_table_rules_comparison_view.py:14–38`](../../../../../vnext/backend/tests/test_table_rules_comparison_view.py#L14-L38)
  明确断言真实规则的 effective key 与 ordered row identity 都是 `("gid",)`，位置列是 `no`。
- [`ordered/tests.rs:268–285`](../../../../../vnext/rust/gateway-compute-core/src/comparison/ordered/tests.rs#L268-L285)
  断言 `gid` 重复输出 `DEGRADED`、`ROW_IDENTITY_DUPLICATE`、replay `UNSUPPORTED`，位置重复输出
  `ORDER_KEY_DUPLICATE`。
- [`test_comparison_s3_d_production.py:442–470`](../../../../../vnext/backend/tests/test_comparison_s3_d_production.py#L442-L470)
  覆盖 `gid/no` 有序比较的生产路径，与冻结的事实摘要、ordered/blank summary 核对。
  这些测试不构成对伪造复合行标识的支持证明。

## 2. COMPARISON_MODE_NOT_DETAILED 与 ORDER_KEY_UNSUPPORTED

**二者都可以按已删除处理，无新替代码。**

- `COMPARISON_MODE_NOT_DETAILED`：旧树 `comparison/standard.py:167–174` 在先分流
  `DATASET_REPLACEMENT` 后，拒绝非 `DETAILED` 模式，返回的是 pair 的 `FailedResult`，
  并非正常表诊断。两棵树的 `ComparisonMode` 都只有上述两个值，新树定义见
  [`comparison/contracts.py:44–46`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/contracts.py#L44-L46)。
  新生产入口在 [`comparison/production.py:910–919`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L910-L919)
  处理 replacement，其余走详细比较，已删除该防御分支与码。
- `ORDER_KEY_UNSUPPORTED`：旧树 `comparison/ordered.py:358,420–423` 拒绝非单列
  `order_key`。合法规划始终构造单元素 tuple（`pair_planning.py:128`），规则还将位置列
  限定为 `no`（`table_rules/contracts.py:701–702`）。这两项约束在两棵树间未变；
  新 Rust 路径直接读取 `no`，不再产生这个码。

## 3. 四个新码的最终出口与真实数据可达性

### 3.1 共同出口：表降级，诊断进入 surface

[`comparison/errors.py:6–7`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/errors.py#L6-L7)
的 `StandardComparisonError` 继承 `ValueError`；
[`comparison/ordered.py:20–21`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/ordered.py#L20-L21)
的 `OrderedComparisonError` 又继承 `StandardComparisonError`。
生产入口逐表执行时在
[`comparison/production.py:985–1038`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L985-L1038)
捕获这些异常，保留 `str(exc)` 为原始诊断码：

1. 产生 `ComparisonTableFact(status=DEGRADED, diagnostics=(code,))` 和一条
   `STANDARD` 族 `TABLE_DEGRADED` 记录，其 `diagnostics` 含此码。
2. 若有 ordered policy，调用
   [`comparison/ordered.py:104–140`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/ordered.py#L104-L140)
   的 `_degraded_fact`，同时设置 ordered/blank extension 为降级、replay `UNSUPPORTED`，
   两个 extension 的内部 `diagnostics` 也含此码。
3. 表诊断汇入 `ComparisonFacts.diagnostics`（[`comparison/standard.py:261–280`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/standard.py#L261-L280)），
   pair 保持 `DetailedFactsResult`；存在降级表时 summary status 为 `DEGRADED`
   （同文件 `291–306`；[`comparison/production.py:1085–1091`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L1085-L1091)）。

前端可见 JSON 的具体位置如下：

| 文档/制品 | 诊断字段 |
| --- | --- |
| 每个 pair 的 `comparison-surface.json` | `tables[].diagnostics.diagnostics_summary[]`；ordered 降级时还在 `tables[].ordered_extension.diagnostics[]`。映射见 [`surface_assembly/_assembly.py:373–382,417,471–485`](../../../../../vnext/backend/src/gateway_backend/capabilities/surface_assembly/_assembly.py#L373-L382)。 |
| 同一 surface 的 pair 摘要 | `diagnostics.diagnostics_summary[]` 与 `view.diagnostics_summary[]`，经去重/稳定排序汇总；见同文件 [`113–121,141–151,177–179`](../../../../../vnext/backend/src/gateway_backend/capabilities/surface_assembly/_assembly.py#L113-L121)。 |
| `STANDARD` records Parquet | `TABLE_DEGRADED` 那一行的 `diagnostics`；元数据记录发布保留此字段，见 [`comparison/artifacts.py:1091–1109`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/artifacts.py#L1091-L1109)。 |
| records manifest JSON | **没有诊断字段**；仅描述表、族、schema、记录数与摘要，见 [`comparison/artifacts.py:1178–1188`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/artifacts.py#L1178-L1188)。 |
| bundle manifest JSON | 根 `diagnostics[]` 从 **failed pairs** 汇集，不复制成功产出 surface 的表诊断；见 [`bundle_assembly/_assembly.py:167–174`](../../../../../vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_assembly.py#L167-L174)。`pairs[]` 只带状态/summary/摘要等，见 [`bundle_assembly/_digest.py:62–85`](../../../../../vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_digest.py#L62-L85)。因此这四个码的表降级不自动进入 bundle manifest 根 `diagnostics` 或 `failed_pairs`。 |

**这四个码本身没有对应的 HTTP 错误码或 operation 失败码。** 它们按上述表降级继续处理；
不能因为源码写的是 `raise` 就把它们列为操作失败。
现有生产测试 [`test_comparison_s3_d_production.py:1172–1207`](../../../../../vnext/backend/tests/test_comparison_s3_d_production.py#L1172-L1207)
用 `TABLE_READER_UNAVAILABLE` 证明同一 ordered 降级出口同时保留标准、ordered、blank 三组事实。

### 3.2 各码的触发条件

| 新码与产生点 | 何时触发 | 正常真实数据路径是否触发 |
| --- | --- | --- |
| `ORDERED_PROVENANCE_MISSING`，[`comparison/production.py:615–617`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L615-L617) | 有序比较构造 native policy 时，所需 `SnapshotTable` 或其 `ordered_metadata` 为 `None`。完整双侧路径取两侧；unchanged 快路只取 current（同文件 `638–641,841–844`）。 | 不是由 SQL 行内容直接触发。正常物化/投影会提供 provenance；若 owning producer 丢失元数据，可在真实运行中作为表诊断出现，不能宣称永不可达。 |
| `ORDERED_PROVENANCE_INVALID`，[`comparison/production.py:618–623`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L618-L623) | 元数据存在，但 provenance 不是 `SOURCE_MISSING_STABLE_KEY` 或 `CANONICAL_PSEUDO_GID`。 | 合法对象构造下不可达：枚举只有这两项及 `NONE`，而 `SnapshotTableOrderedMetadata` 拒绝 `NONE` 和非枚举值。需绕过对象校验/内部缺陷才可能到此处。 |
| `METADATA_ROUTE_REQUIRES_NATIVE_ROWS`，[`comparison/ordered.py:24–32`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/ordered.py#L24-L32)、[`comparison/standard.py:66–118`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/standard.py#L66-L118) | 双侧 ordered 任务误送入只处理单侧的 metadata helper；或需要行比较的 standard 任务误送入 metadata helper。 | 正常生产路由不可达：[`comparison/production.py:759–805`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L759-L805) 只把单侧、standard 快路、无效/变化键、无共有列等可仅用 metadata 处理的任务交给该 helper；双侧 ordered 和其他行比较走 native。 |
| `METADATA_ROLE_REQUIRES_NATIVE_ROWS`，[`comparison/standard.py:191–206`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/standard.py#L191-L206) | BROWSE_ONLY/SNAPSHOT_ONLY 的 `COLUMNS_ADDED` 任务误送入 metadata helper；判断共有列内容变化仍需要读行。 | 正常生产路由不可达：[`comparison/production.py:763–783`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L763-L783) 对此做 native keyless probe，然后调用另一个 `_compare_task_metadata_nonrecord`，不进入该异常分支。 |

provenance 的类型/合法性依据：
[`snapshot_materialization/contracts.py:107–116,858–868`](../../../../../vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/contracts.py#L107-L116)。
源数据物化写 `SOURCE_MISSING_STABLE_KEY`：
[`snapshot_materialization/materialize.py:322–334`](../../../../../vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/materialize.py#L322-L334)；
有序 canonical 投影写 `CANONICAL_PSEUDO_GID`：
[`storage_projection/arrow.py:74–79`](../../../../../vnext/backend/src/gateway_backend/capabilities/storage_projection/arrow.py#L74-L79)。
已有角色测试
[`test_comparison_rule_roles.py:178–199`](../../../../../vnext/backend/tests/test_comparison_rule_roles.py#L178-L199)
断言 BROWSE_ONLY/SNAPSHOT_ONLY 增列时仍正确计算共有列内容变化且不产生行记录。
当前没有直接按这四个新字符串断言的测试；上述四码出口/可达性结论来自调用链核对，不能称为四码逐项运行验证。

### 3.3 与 BLANK_PROVENANCE 系列的关系

不能把四个新码统称为旧 blank provenance 码的替代品。两个 `METADATA_*` 与 blank 无关；
`ORDERED_PROVENANCE_*` 是 Python 到 Rust 的 **policy 元数据准入**，其余码还要区分层次：

| 旧码 | 新树的实际情况 |
| --- | --- |
| `BLANK_PROVENANCE_MISSING` | Rust 仍主动产生：[`ordered.rs:211–212`](../../../../../vnext/rust/gateway-compute-core/src/comparison/ordered.rs#L211-L212)（unchanged summary 的错误），[`852–864`](../../../../../vnext/rust/gateway-compute-core/src/comparison/ordered.rs#L852-L864)（双侧比较直接生成降级结果），以及 `1909–1910`。现有 [`ordered/tests.rs:310–320`](../../../../../vnext/rust/gateway-compute-core/src/comparison/ordered/tests.rs#L310-L320) 断言 core 的 `BlankProvenance::Missing` 输出该码。**正常 Python 生产 adapter 不传 Missing**：先在 `production.py:615–623` 校验并只传 `source/canonical`，Rust policy parser 也只接受这两项（[`policy.rs:115–119`](../../../../../vnext/rust/gateway-compute-core/src/comparison/policy.rs#L115-L119)）。所以旧 Python“缺 ordered metadata”的位置如今输出 `ORDERED_PROVENANCE_MISSING`，但 Rust 码并未删除。 |
| `BLANK_PROVENANCE_INVALID` | 旧 Python `ordered.py:452` 的主动产生点已删除；新 backend/Rust 中只在 [`production.py:49–56`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L49-L56) 的 `_OLD_CODED_ERRORS` 出现。**这是保留 ValueError 原文的名单，不是产生点。** 当前生产实现没有主动产生此码；Python 元数据非法时使用 `ORDERED_PROVENANCE_INVALID`。 |
| `CANONICAL_BLANK_PROVENANCE_INVALID` | 仍有真实行校验产生点：canonical provenance 下 `gid` 为 null/0，见 [`ordered.rs:1894–1916`](../../../../../vnext/rust/gateway-compute-core/src/comparison/ordered.rs#L1894-L1916)。双侧读行错误转成表降级（同文件 `891–911`）；unchanged 路径向 Python 抛出的该码也由 `_OLD_CODED_ERRORS` 保留。它没有被新码替代，语义仍是“canonical 空行标记与实际行值矛盾”。正常投影会分配 pseudo gid；损坏/不一致的 canonical 输入仍需此校验。 |

真实源行中的负 gid、保留 pseudo gid、缺位置、重复 gid 等，仍对应其行数据诊断，
不应翻译成 provenance 元数据缺失。现有
[`ordered/tests.rs:105–119`](../../../../../vnext/rust/gateway-compute-core/src/comparison/ordered/tests.rs#L105-L119)
区分 source/canonical 的非法 gid，`290–306` 区分 source 保留 pseudo gid 与合法 canonical 空行。

## 4. 其他诊断码差异与前端处理

对 comparison、risk evaluation、surface/bundle assembly 的两树差异及 native 错误出口核对后，
除了 §1–§3 所述，需向前端补充以下事项：

| 项目 | 结论与依据 |
| --- | --- |
| `DUPLICATE_EFFECTIVE_KEY:<table_name>` | 对外码与含义未变。Rust 的无表名 `DUPLICATE_EFFECTIVE_KEY` 在 [`production.py:1000–1004`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L1000-L1004) 补回表名；现有 [`test_comparison_s3_d_production.py:1247–1267`](../../../../../vnext/backend/tests/test_comparison_s3_d_production.py#L1247-L1267) 与旧 Python 冻结结果逐项核对。不要把无表名 native token 当成新增表码。 |
| schema、keyless、ordered 行校验及风险提示 | 除本文单列事项外，未发现其他新增/删除的业务诊断码。例如 schema 码仍由 [`row_encoding.py:111–125`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/row_encoding.py#L111-L125) 产生；ordered 的缺列/类型/空选择/缺身份检查见 `ordered.py:80–101`；`DEGRADE_NO_COMPARE_KEY` 见 `production.py:809–817`。`SET_VALUE_INVALID`、`SCALAR_*` 等原 Python 编码诊断转到 Rust，未因 Python 产生点删除而消失（[`ordered.rs:2027–2053`](../../../../../vnext/rust/gateway-compute-core/src/comparison/ordered.rs#L2027-L2053)、`2094–2145,2232,2282,2327,2340–2385`）。surface/bundle assembly 与 replacement 实现在两棵树间未改动。 |
| `ORDER_KEY_INVALID` 的位置范围校验 | 新 Rust 明确将位置转换成 `i64`，越界产生 `ORDER_KEY_INVALID`（[`ordered.rs:1868–1877`](../../../../../vnext/rust/gateway-compute-core/src/comparison/ordered.rs#L1868-L1877)），随后按 `891–911` 转成表降级。旧 Python `ordered.py:426–431,455–467` 的位置解析只检查整数及正数，没有这个上界检查；不能把旧 helper 无上界解读为旧完整制品链支持任意大整数。前端已有“序号缺失、无效或重复”的文案可覆盖新校验。此边界差异来自源码核对，现有测试没有对 `no > 2^63-1` 作两树差分断言，本轮也不宣称真实数据出现过。 |
| native 内部校验 token 与通用异常名 | 并非每个 Rust 大写错误都原样成为前端码。native 抛出的普通错误映射为 `ValueError`（[`comparison_records.rs:394–409`](../../../../../vnext/rust/gateway-compute-python/src/comparison_records.rs#L394-L409)），Python 仅保留指定码，其余用异常类名（`production.py:996–1006`）。例如新增的 canonical profile 校验错误通常对外是已有的 `ValueError`，现有 [`test_comparison_s3_d_production.py:352–392`](../../../../../vnext/backend/tests/test_comparison_s3_d_production.py#L352-L392) 明确断言此结果。不要为所有内部 token 添加 surface 文案。 |
| 意外异常的处理范围 | 旧树 `comparison/standard.py:203–208` 将除取消/超时/内存外的任意 `Exception` 变成表诊断类名。新 `production.py:994–1006` 只捕获所列的表数据/读取异常；意外 `RuntimeError`、`TypeError` 等会向 operation 层传播。它们不再保证作为表诊断出现；现有前端通用异常名文案不意味着后端仍保证逐项产生。四个新码属于已捕获的 `StandardComparisonError`，不受此差异影响。 |
| `ORDERED_PROVIDER` | Python 字面量删除，但 Rust [`ordered.rs:1031,1086`](../../../../../vnext/rust/gateway-compute-core/src/comparison/ordered.rs#L1031) 仍在有序表的标准新增/删除记录诊断中写它；不是新表诊断，也不是删码。 |
| `RECORDS_PUBLICATION_CANCELLED` | 旧树 `comparison/artifacts.py:213–217` 的 publication `CancelledResult` 兜底字符串已随旧发布入口删除；它不是表降级码。新生产发布入口 [`comparison/artifacts.py:592–600`](../../../../../vnext/backend/src/gateway_backend/capabilities/comparison/artifacts.py#L592-L600) 返回 `DetailedFactsResult`，不再构造这个取消结果。不可把它列成新增的 surface 提示。 |

前端按当前产生点维护文案时，可以执行以下调整：

- 删除 `ROW_IDENTITY_UNSUPPORTED`、`ORDER_KEY_UNSUPPORTED`、`COMPARISON_MODE_NOT_DETAILED`；
  `BLANK_PROVENANCE_INVALID` 也已无主动产生点，可一起清理。
- 为 `ORDERED_PROVENANCE_MISSING`、`ORDERED_PROVENANCE_INVALID` 补“有序表缺少/具有无效的空行来源信息，无法可靠比较”类文案。
- 两个 `METADATA_*` 可共用“比较时发生内部错误”；它们是内部路由保护，不能提示用户修正业务数据。
- 保留 `CANONICAL_BLANK_PROVENANCE_INVALID` 等仍有产生点的码；`BLANK_PROVENANCE_MISSING` 的
  core 产生点仍在，但当前 Python 生产适配层会先用新码拒绝缺元数据，不要将两个码视为同层必然并存。

本答复只提供后端事实与文案分类依据；前端 `diagnostics.ts` 和 kickoff Q21 状态由前端设计会话据此更新。

## 5. 核对与交付范围

本轮仅静态阅读两棵 Git 树的源码和现有测试，并核对差异、引用与行号；没有运行产品代码、测试、
编译、容器门禁或真实数据旅程，不新增运行通过/真实数据诊断出现次数的声明。
现有测试在本答复中作为断言内容依据引用，不表示本会话重新运行过它们。

提交基底/源码 HEAD 为 `fd9e383d76642037e4b3246c847222ea9483e033`；
工作目录 `/home/dev/gdds-p6-fe3-q21-answer`，短分支 `p6-fe3-q21-answer`。
仅新增本文，不修改产品/测试或前端文件，不触发镜像重建；无本轮 image revision/source-tree
验证结果可报告，也不宣称 carried。未操作开发主机主工作区或 S5 main worktree 的文件与检出状态。
未推送，由 owner 转交前端设计会话。

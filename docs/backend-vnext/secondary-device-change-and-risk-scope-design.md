# 二次装置变化归属与风险范围修正设计

状态：可实施设计候选，独立审核后收口；本轮授权限文档和设计审核，不含产品实施、部署或联调数据写入。

本设计修正共享测点表变化与风险向无关装置扩散的问题，同时覆盖二次装置相关表仅修改 `name` 的低风险规则，以及转发有序表尾部空点风险。继续由 Comparison、Risk、Navigation 各自拥有比较、风险与归属，前端统一按发布的范围展示。无法定位的风险集中说明，不能隐藏，也不能当作每台装置的已确认风险。根据 Owner 后续讨论，当前推荐完整保留相关标准表增删事实与展示数据，但增删本身不生成风险；保留必要展示成本，省去无业务需要的风险标注，见 §3.1。

## 1 核实范围与证据

源码基线为人工联调分支 `gw08-dual-env` 的 `0c34339a12`，工作区 `/home/dev/gdds-gw08-dual-env`。用户提供的根工作区当前在其他分支且有在途修改，本次不切换它、不修改其文件。目标工作区原有两份未跟踪的 Preview 诊断计划也不属于本次范围。

已阅读仓库 AGENTS、比例化保障政策、Comparison、Risk、Ordered Diff、Business Navigation、Row Location Contract，以及相关实现和前端消费代码。本次只做源文件与文档核对、原始 SQL 文本解析，没有运行产品代码、测试、构建、lint、部署或线上数据写入。下列 SQL 统计不是物化/导入链路通过的证据。

### 1.1 已确认的原始数据事实

输入为 `/home/dev/gateway-data-management-system/legacy/data/com_cfg_test/{1,2}/sql/dbcfg.sql`。按各自 CREATE TABLE 列序读取 INSERT 元组，以 `gid` 对照 `device_mx`：

| 项目 | 第 1 份 | 第 2 份 |
| --- | --- | --- |
| device_mx 行数 | 2223 | 2221 |
| gid 1753–1757 | dev_addr=34 | dev_addr=9234，其他列相同 |
| gid 5009 | dev_addr=65532，name=#1主变档位 | 无此行 |
| gid 5012 | dev_addr=65532，name=#2主变档位 | 无此行 |
| device_mx 新增 | — | 0 行 |
| device 行数 | 100 | 100 |
| device gid=1721 | dev_addr=34，description=35kV分段330备投RCS9651B | dev_addr=9234，description=(废弃)35kV分段330备投RCS9651B |

因此不是单纯的测点地址变化：注册装置本身也发生地址与描述变化。34 和 9234 两侧均有各自合法注册依据；2 行删除应归复合虚装置，不能散到其他装置。这里没有声称其他表也只发生这些变化。

### 1.2 已确认的实现机制

| 证据 | 确认结论 |
| --- | --- |
| [table_rules/registry.py](../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py) 的 `DEVICE_POINT_UPDATE_ONLY_TABLE_NAMES`、`_device_point_records` | 十类共享测点表含 device_mx 均按 gid 比较，artifact_scope=UPDATE_ONLY；device_cfg 的常量虽带 UPDATE_ONLY 名字，实际 scope 已为 ALL_CHANGES，比较键为 (gid,page_no,option_name)，no 排除比较 |
| [NavigationEvidence.fallback_reason](../../vnext/backend/src/gateway_backend/capabilities/business_navigation/contracts.py)、[business_presentation.py](../../vnext/backend/src/gateway_backend/application/business_presentation.py) | suppressed 增删只要非零即 RECORDS_UNAVAILABLE；记录计数不符、locator 不完整、风险归属不完整、降级等也可触发 fallback |
| [producer.py](../../vnext/backend/src/gateway_backend/capabilities/business_navigation/producer.py) 的 `devices`、`summarize` | 同表所有筛选页签统一 TABLE_FALLBACK；非空页签摘要使用整表 change_kind/risk_level，因此多个装置出现相同风险符合当前 Contract |
| [risk_evaluation/_engine.py](../../vnext/backend/src/gateway_backend/capabilities/risk_evaluation/_engine.py) 的 `_emit_row_risks` | 抑制行记录时，风险可能是 TABLE target 加 coverage=ROW_RECORDS_SUPPRESSED；COUNTS_ONLY 则用 ROW_COUNTS。TABLE target 不一定意味着业务上的整表固有风险 |
| Navigation producer 的 `reduce_table_risks` 及 application 接线 | 当前只按 TABLE/COMPARISON target 归约，粗粒度行风险也可能进入 table_scope；不能继续把两者等同 |
| [ComparisonPage.tsx](../../frontend/src/pages/ComparisonPage.tsx) 的 `tabRiskLevel`、`tabChangeKind`、table-info | 局部风险 null 经 `??` 回落整表风险；变化优先取整表；详情页头直接显示整表徽标和统计。即使后端 EXACT，仍可能产生局部与整表混淆 |
| [model.ts](../../frontend/src/features/view-model/model.ts) 的 `navigationTabHasDifferences` | 差异过滤已区分 EXACT，但页签徽标等没有使用同一口径；导航项又直接使用服务端 summary |
| Risk `_emit_row_risks` 与默认 ruleset | 普通行修改默认 MEDIUM_HIGH，无二次装置 `name` 专项；有序行已对仅 name 修改使用 LOW |
| Risk `_emit_blank_intervals`、[pair_pipeline.py](../../vnext/backend/src/gateway_backend/application/pair_pipeline.py) 的 `_ordered_position_maxima` | 目前以该侧全部行最大 no 为界，仅 `interval.end == maximum` 算尾部，否则为中间；其余移动、替换、行增删规则独立叠加 |

### 1.3 尚未验证的现场假设

尚未读取本次实际导入对应的 operation/pair、ComparisonFacts、records、locator、typed annotations、navigation 和 diagnostics；未确认浏览器所见结果的源码、Rust 扩展及规则身份。交接区的历史记录不是这一次导入的直接证据。

从 SQL 与源码可以推出：若本次确实按上述输入、方向、默认规则完成普通比较，2 行删除会被抑制并足以触发测量类 fallback，5 行地址修改会产生行修改风险。**尚不能认定这是现场提示的全部原因**：还可能有其他表变化、身份/locator/annotation 不完整、比较降级或旧结果复用。空点误判也没有取得具体表、前后 no 与风险 reason，不能认定仅由末端判定造成。当前基线已经包含骨架区间内替换配对修复，不应把旧的绝对 no 配对问题再当成本次已确认根因。

实施前先定位已有结果并只读核对以上链路；若已有产物足够，不重新导入。现场资料无法唯一定位时，由 Owner 提供 A/B 环境、装置/项目、操作时间或 pair/operation 入口。记录原件位置于仓库外交接区，不复制凭据及业务全量载荷入设计。

## 2 已固定的产品决策与范围

1. 十类测点表 `device_st/device_mx/device_co/device_sg/device_sp/device_cnt/device_sn/device_tap/device_other/device_disturb` 改 ALL_CHANGES。`device_cfg` 保持现有 ALL_CHANGES 与业务键。完整保留新增、删除、修改的 facts/records、必要原侧值和 locator，现有 bundle 闭合展示数据。无新账本、第二套 diff 或删除行专用 bundle。
2. 上述十一张 STANDARD 表的普通 ROW_ADDED/ROW_DELETED **不生成风险**，但计入变化、统计、归属、差异过滤。其他表的普通增删、整表新增/删除、schema/降级/一致性风险、有序表专项规则不变。键变化仍由 owning Comparison 识别，不猜测增删行之间存在修改关系。
3. 十类测点表只有 name 修改为 LOW；混合修改依原修改规则。device.description、device_cfg、composite_signal_point.point_name 不纳入本次降级；其中 point_name 现有排除比较规则不改。
4. 正常尾部空点增删 LOW；中间插空改变后续有效点地址保留 MEDIUM_HIGH。中间空点但地址未变仍沿用当前中间风险，不引入尚未确认的进一步降级。全空表的纯空点容量变化归尾部 LOW。
5. 所有已有确认风险继续在整体报告可见。装置个人风险只来自有依据的装置行/定义归属；真正表级风险和待定位风险独立展示。未知不等于无风险，也不凭空生成 UNKNOWN。
6. 无旧 DTO/载荷兼容、历史结果回填或存量数据迁移。本次只定设计与实施计划；产品实施和08部署不因设计审核通过自动获授权。

## 3 Comparison 与删除行展示

只将十类测点表 scope 改为 ALL_CHANGES，并将误导性的 UPDATE_ONLY 常量重命名为按业务表集合命名。device_cfg 不再改 scope；不得把其业务键改回 gid。更新 registry、contracts 中有效规则不变量及对应 golden/测试。

Comparison 已做两侧键匹配并计增删，改变 scope 主要增加记录保留和下游工作。保留 native row_identity、标准 counts 与 suppressed 定义；这十表正常 suppressed=0。生产展示链路固定现有 FULL_BEFORE_AFTER_VALUES，ROW_DELETED 保留 selected 展示列的 before_values，ROW_ADDED 保留 current_values；物理缺列与 SQL NULL 区分。COUNTS_ONLY/缺载荷仍是能力边界，不能伪装完整详情。

定位复用 Row Location 五列 schema 和现有 canonical scanner：每条发布的普通行 record 有且只有一个 locator，新增只存在 current，删除只存在 before，修改两侧存在；缺 bundle 快照侧只有 filter context，无伪造 index。context 提供归属，完整旧值由 records 或真实 before snapshot 提供。不为删除行补导出所有表完整 before 快照。

前端删除行值来源顺序固定为：真实 before snapshot 行；否则已验证 record.before_values。filter context 仅用于身份筛选和一致性核对，不替代完整行。两者重叠身份值矛盾为解码错误；确实无完整值时显示不可得，不把缺值当 NULL。修改行继续按现有 current+before changed values 重建，受原身份复用资格约束。

## 4 Risk 规则和缓存

### 4.1 使用现有冻结规则参数

不向风险层传前端分组名。ROW_ADDED、ROW_DELETED 的 RiskRuleSpec.params 各增加十一项 `("exclude_table:<exact_name>", true)`；新增 STANDARD_NAME_UPDATE rule/reason，target_scope=STANDARD_ROWS、默认 LOW，params 用十项 `("include_table:<exact_name>", true)`。使用现有标量参数类型，不嵌 JSON 字符串、不添 profile ID。规则 validator 严格核对允许参数名、集合和 true 值，未知参数拒绝，不允许调用方靠漏规则关闭未授权范围。

Risk owner 的单一解析函数从 frozen rules 和实际 table_name 得到三个 boolean：`emit_standard_added`、`emit_standard_deleted`、`standard_name_low`。它同时供 evaluator 和 cache key 使用。只在 STANDARD_ROWS 分支应用；ordered 与 structural 分支不受表名规则影响。

`_emit_row_risks` 在按 kind 遍历/计数兜底前跳过被排除的增删 kind；COUNTS_ONLY、抑制记录、缺记录都不得把这两个 kind 重新发成 TABLE/UNKNOWN。修改逐条核 changed_columns：集合恰为 {name} 且适用专项则只发 STANDARD_NAME_UPDATE，否则发 ROW_MODIFIED。没有修改列证据时仍按修改默认风险，不能猜 LOW。缺/无效 records、真实任务失败仍按原 Contract 处理，排除风险不代表允许损坏记录进入展示。

正常被排除的增删返回 complete=true 的空风险 outcome。RiskAttribution.observe 不要求每个 record 都有 annotation；记录完整性由 Comparison/locator owner 校验，风险完整性由 evaluator outcome 的 complete 提供。annotation 不存在时 risk_level=null，而非 LOW 或 UNKNOWN。空 baseline 原有全无风险语义保留。

### 4.2 缓存输入闭合

`risk_evaluation/candidates.py::optional_candidate_input` 当前删除 table_name，使同语义表可共享纯结果；新增按表规则后，必须把上述三个适用 boolean 放入 facts_jcs 的 `standard_rule_applicability`。不得只将统一 ruleset digest 加入 key：所有表共享 ruleset，仍不足区分适用与非适用表。候选 replay 经过同一适用性检查，空 outcome 也可合法命中。

有序空点规则的新输入 `ordered_tail_bounds`（§7）也进入此 key，包含当前表实际两侧边界/证据是否完整；不把整个映射塞入单表 key。不使用 host path/operation ID，不为此另加缓存版本轴。

## 5 Navigation v4 载荷与归属

### 5.1 变化与风险完整性分别表达

沿用 facts.basis=EXACT|TABLE_FALLBACK，**v4 下它仅表达局部变化完整性**：成功比较、可用身份、真实 counts 与 records 相符、无 suppressed、locator/context 完整且非不支持的降级。风险不完整不再抹掉可确认的变化。

筛选 facts 固定为：

```text
{basis, change_kind, risk_level, risk_complete,
 before_row_count, current_row_count, table_scope,
 membership_changed, membership_complete,
 row_changes: null | {added, deleted, modified, moved_in, moved_out}}
```

- EXACT 要求 change_kind 非 null、row_changes 为非负整数对象；TABLE_FALLBACK 要求二者为 null。counts 可保留已知值。row_changes 的 modified 包含迁移行，moved_in/out 是其子集，不再与 modified 相加。
- risk_level 是已确认且可定位到本页的最高行风险；risk_complete=false 时可能仍有非 null 的已知风险，也可能是 null。不能用 null 宣布没有风险。已知 records 逐条绑定可定位，不能用不完整全表推定未知余量的归属。
- membership_changed 是已证明的注册归属改变；membership_complete=false 表示不能完整判断。它不伪造 Comparison ROW_MODIFIED，也不产生新的风险。
- table_scope 复用 `{change:boolean,risk_level:RiskLevel|null}`，只存真正表级/比较级事实。同表全部 facts 一致。不存在公共事实时为 null。
- 整表 tab 与 replacement 的 facts 仍为 null。replacement 不产生本轮行比较、个人风险或归属迁移。

局部 change_kind：存在内容 records 或 membership_changed 时，局部旧计数0/新>0为 ADDED，旧>0/新0为 DELETED，其余为 UPDATED；无二者为 UNCHANGED。文案区分“本装置移入/移出”和“新建/删除测点”。任何一侧命中筛选即展示同一成对行，不只按 current 过滤。

保留 DEVICE_TAB_FACTS_UNAVAILABLE 用于变化 fallback，原因 RECORDS_UNAVAILABLE/TABLE_DEGRADED；新增 DEVICE_TAB_RISK_UNAVAILABLE 用于 risk_complete=false、DEVICE_MEMBERSHIP_UNAVAILABLE 用于 membership_complete=false。均按表唯一诊断、side=null、同现有 group/table target，参数为 identity_column 与固定 reason；后端/前端严格同步。资源/I/O/内部错误不能伪装成未知诊断。

### 5.2 表公共提示

普通导航根新增 `table_notices`，按 table_id UTF-8 排序、唯一；无提示为 []。每项：

```text
{table_id,
 table_scope: null | {change, risk_level},
 unlocated_row_risk: null | {risk_level: RiskLevel|null,
   count: integer|null, reason_codes: [string]},
 risk_complete: boolean}
```

table_scope 与 facts 中同表值一致，含非空真正表事实时发布。unlocated_row_risk 表达已输出但不能归属到装置的风险，或者风险评估不完整：后者 risk_level/count 均可 null，原因用已有诊断，不能合成 UNKNOWN。count 只在事件互斥且语义单位相同时相加，否则 null。reason_codes 去重排序。不存在公共事实、待定位风险或不完整风险时不发布该项。

该新归约和table_notices仅适用于十一类共享标准表（包括其降级整表入口）。其他整表/通道表沿用原有风险展示，ordered ROW_INTERVAL继续由有序消费路径处理，不落入本节未知target兜底；device行风险由定义变化引用专门接线。COMPARISON全局风险只投影到这些实际相关共享表，整体RiskReport仍保留全部表事实。

typed outcome 按以下优先序归约，不读混合 RiskReport.tables[].risk_level 反推：

| target/evidence | 归约 |
| --- | --- |
| TABLE + coverage=ROW_COUNTS/ROW_RECORDS_SUPPRESSED/ROW_RECORDS_UNAVAILABLE | 待定位行风险 |
| TABLE + 已知 structural/degraded reason，或 COMPARISON | 真正表级/比较级风险；全局按实际目标表投影 |
| ROW/ROW_PAIR + 可用 identity 与已验证两侧上下文 | 局部行风险；无任何装置命中则归公共待定位入口 |
| 其余无法解释的 target/coverage/reason | 保留等级到待定位范围，risk_complete=false |

即使 RiskAttribution 完整，所有 row identities 也要在 locator 消费后检查未绑定集合；不能让“annotation有identity但无record”悄悄丢风险。新生成和 cache replay 共用此归约。完整性不足时不把已知局部风险升级成整个表的个人风险。

Item.summary 仅汇总非空 tabs 的局部变化/已确认行风险，不合并 table_scope，也不在 fallback 回填整表 change_kind/risk_level。TABLE item 仍用整表 summary；filtered fallback 的变化通过公共诊断表示未知。summary 新增 `change_complete`、`risk_complete`，为非空筛选页签相应完整性的 AND，空集合 true。非空计数、empty 规则不改。全空项仍 []/null/0；表公共提示独立于是否隐藏空页签。

replacement 根 table_notices=[]、device_definition_changes=[]，保留原两侧 group/facts=null 规则。新字段均必填，禁止旧载荷缺省兼容。

### 5.3 注册装置和未变化测点的归属

装置 item_key 继续按 dev_addr，device_cfg 按本侧有效 gid 集，65532 规则不变。注册表全行仍在装置总表显示。普通导航根增加 `device_definition_changes`：

```text
[{record_identity, change_kind: ADDED|DELETED|UPDATED,
  before_item_key: string|null, current_item_key: string|null,
  before_dev_addr: integer|null, current_dev_addr: integer|null,
  risk_level: RiskLevel|null, risk_complete:boolean}]
```

来源是 device 的实际标准 record 和两侧 locator/snapshot，不是按描述匹配。before/current item_key 仅在本侧地址有效且已发布时填写；重复地址可指同项但保持原重复诊断。按 record_identity 排序唯一，不包含路径，不造新身份。使用现有 device before snapshot 与 locator，application 提取两侧地址，record_identity 继续由 native owner 提供。定义变化列表独立于 tab summary；前端显示“装置定义变化”入口及链接，差异/风险过滤也包含其已确认信息，不用它改变非空页签计数。

仅 registry 变而测点未变时，基于已验证可复用的同一测点身份值，比较同侧谓词命中集合：`owners_before(value) != owners_current(value)` 表示 membership_changed。利用现有扫描 histogram 和两个 owner 集，逐值比较，不保存全量行身份。只统计真实有行的值；不能只比较总数。同一装置内 registry记录变动但最终所属集合相同不产生测点归属变化。

部分内容变化的表中，先从两侧histogram分别减去实际发布records的各侧贡献，得到无record行的身份值分布；完整比较证明其为未变化部分后再判断registry-only归属变化，两侧剩余分布须一致。不能把已迁移/新增/删除行再次计成未改归属变化。

有变化的测点用实际 record.before/current context；无变化行仅在旧 FE-BEB-12 全部身份/比较条件满足且物理身份列共存时复用 current 值。风险不完整本身不阻止内容身份复用；变化记录不完整、suppressed、schema/身份不适用仍阻止。不能把 membership_changed 作为新的行级高风险来源；实际 device 修改风险由定义变化入口可达。

无法精确复用时 membership_complete=false，保留已确认 records 和注册变更来源，不能标为已无归属变化。重复地址/gid保持覆盖集合与歧义提示，不借对侧有效身份解释本侧。

### 5.4 未归属浏览

复用 DEVICE_ROWS_UNASSIGNED 的逐侧计数及整表浏览动作，不增加虚构装置 item。动作增加本地浏览状态 `{table_id, unassigned_side: BEFORE|CURRENT}`，使用已发布的该侧全部谓词覆盖集合取补集，复用同一 scalar decoder；只对完整可用的同侧身份条件启用。NULL 身份不匹配任何谓词，应显示为未归属。无有效谓词、身份超域/不支持或物理缺列时只提供整表入口并解释原因，不猜筛选结果。

未归属浏览仍显示成对行，按选定侧判定命中，不能将任一侧的 orphan 都混入本侧计数；若 Preview 缺 before snapshot，仅能显示有 before record/context 的行，不声称展示全部旧未归属未变化行。全量旧孤儿计数和可浏览行数必须分开。changed_row_count 继续表示内容 records，不把 registry-only 变化塞入该字段。

## 6 前端统一展示判定

在 model.ts 定义一个范围选择器，供 navigationTabHasDifferences、徽标、页头、过滤和统计使用，禁止 `facts.risk_level ?? table.riskLevel` 或优先取 table.changeKind。

| 对象 | 变化/风险来源 |
| --- | --- |
| 整表入口 | 原 Surface/RiskReport 及整表统计 |
| EXACT 筛选页 | facts.change_kind、row_changes、risk_level/risk_complete；公共提示另列 |
| fallback 筛选页 | 变化未知、已知风险及完整性；不显示整表为个人结果 |
| 定义变化入口 | device_definition_changes 的实际记录及风险 |

显示“本页”统计与“整表”统计时明确标签；局部差异统计不得使用整表 stats。EXACT null且risk_complete=true显示未生成风险标注；risk_complete=false显示风险信息不完整。没有局部变化但有公共风险时二者并列，空页签隐藏不隐藏公共提示。

“有风险”默认筛选保留已确认个人风险、相关公共/待定位风险入口及定义风险。只带共享提示的装置用范围提示标记，不能用个人彩色风险徽标。差异过滤包括局部内容变化、归属变化、定义变化、比较未知及公共表变化入口。定义变化涉及的空项可由独立定义入口打开，不更改服务端 empty/nonempty计数。风险详情、原因、定位逐条依实际作用域，不给所有行染色。

有序blank records每条显示一条“空点区间变化”摘要，包含before/current受影响范围、原occupancy差count、方向与风险；不得用start+offset推造具体新增/删除空点行，也不以physical index+1代替业务no。真实snapshot行继续原样浏览。摘要进入差异/风险过滤与变化定位，按no定位最近真实行；不计作新增业务行数。ROW_INTERVAL风险仅挂到对应区间摘要，不再经intervalRiskAnnotation给范围内真实新增有效点或全部行染色，其自身ROW风险仍按原annotation呈现。无需为匿名空点创造行身份或补全before快照。

前端 decoder 同步 v4 必填字段、唯一性、引用表/项存在性、数值与summary一致性。row scope摘要校验不再假定 fallback 风险必为null；Preview/History/提交绑定审核消费同一个文档。修改 frontend/ 前按 AGENTS 告知前端设计会话范围并列入审核，本轮只改文档，无需假装已通知。

## 7 有序空点的精确尾部判据

本次只改 BLANK interval 风险分类，不改非空行新增/删除、替换配对、移动及 Comparison 顺序算法。空点沿用 canonical pseudo-gid/provenance，不能用 name为空识别。

替换 `_emit_blank_intervals` 的 `end==整表最大no` 判据：对于插入使用current、删除使用before；若该侧变化空区间之后仍有**保留的有效测点**，归中间 MEDIUM_HIGH，否则尾部 LOW。保留指真实非空业务行在两侧均存在，包含已移动行；新建/删除有效点另有原专项风险，不能当保留锚点。

为避免二次LCS或全表gid字典，复用实际 ordered records：收集 ROW_ADDED 的 current_position、ROW_DELETED 的 before_position 集（替换伙伴也仍计入增删），随后扩展原 `_ordered_position_maxima` 双侧流式扫描，跳过 canonical blank 与本侧纯增删位置，得到各侧最大保留有效位置。空间 O(增删位置数)，扫描一次两侧，不建全量行索引。移动实体不在纯增删位置集合，仍作为保留点。集合与record counts相符、位置有效且输入非降级才证据完整；否则边界未知。

RiskEvaluationInput 使用现有字段位置的目标形态 `ordered_tail_bounds[table] = {before_max_position,current_max_position,before_last_retained_position,current_last_retained_position,complete}`，替代 ordered_position_maxima，无别名。原非空行规则继续只读max_position，空点新规则读last_retained_position：complete=true且该侧last为null或last<start则LOW，否则MEDIUM_HIGH。若保留有效点位于区间内部，同样按中间处理，不将跨越保留点的区域整体降LOW。完整性不足时发原 ORDERED_RISK_UNKNOWN，不猜尾部。

已核实 native `blank_extension_work/blank_gaps`：before/current_start/end 是同一骨架间隙的空点包围范围，可能跨越非骨架行或稀疏no；row_count是两侧占用数差的绝对值，不是end-start+1。保持该Contract，既不按跨度算新增/删除数量，也不按last切分后伪造精确变动区间。RiskTarget区间表示受影响区域，evidence.count保留原row_count；界面须写清区域与变化数量，不能声称区域内每个位置都被删除。start/end只用于有无后续/区域内保留有效点的分类。

例：旧 A@1,B@2，当前 A@1,blank@2,B@3，中间风险；旧 A@1，当前 A@1,blank@2..3，为LOW；旧 A@1,blank@2..5，当前 A@1,blank@2..3，删除尾部4..5为LOW；尾部追加有效点前的填充空点后面只有新点，空点本身LOW，新增点仍按原规则；真实move/替换风险不因空点LOW被删除。稀疏no不把不存在的行当blank。

## 8 身份和复用边界

| 现有身份 | 目标变更与核对者 |
| --- | --- |
| table rules digest | 十表scope改变，registry snapshot/golden重算，Comparison planner/cache核对 |
| Risk ruleset/rule v7→v8，risk-model v4→v5 | 表适用和空点风险改变；rules validator、candidate key及RiskEvaluation digest核对；不额外增加版本轴 |
| BusinessNavigation v3→v4 | 字段/摘要语义变化，pydantic strict/extra=forbid、前端decoder、golden核对 |
| Preview assemble-state v10→v11；History v7→v8 | checkpoint恢复解码拒绝旧组装状态；不改变READY closure wire格式 |
| History job contract v2→v3；Preview job contract v4→v5 | History受理指纹绑定job contract；Preview既有capability_contract_versions写入risk model、risk ruleset digest、navigation版本并由worker/result reader核对，job decoder拒绝旧版本；不改变调用方请求幂等指纹或Comparison core contract |

不修改 canonical storage、原始SQL、普通records/locator物理schema；有序新边界为operation-local输入，不建独立artifact。Risk candidate key显式绑定§4/§7输入。Surface projection raw digest与bundle闭包重算；已发布旧bundle不被原地重写。History新语义不跨键复用旧成功作业。Preview当前没有跨键成功结果复用：新键新建operation，旧键相同请求仍返回原operation，不把服务器语义版本塞入HTTP请求幂等指纹。旧结果不作为当前语义的可提交Preview：既有结果读取、T1/finalize与审核绑定校验增加当前job/capability版本检查，不符走现有PreviewBindingConflict/结果不可用路径并要求新键重新预览，不原地改旧bundle或同键改绑。活跃旧作业版本不符按既有失败路径，不自动删除数据或重置控制库。

## 9 验收与风险

唯一权威测试owner和命令见[实施计划](secondary-device-change-and-risk-scope-implementation-plan.md)。真实输入1→2必须确认 device_mx +0/-2/修改5，1753–1757命中旧34/新9234，5009/5012只属65532且删除值可见、没有普通删除风险；未受影响装置不继承测量整表风险。其他表风险不能被这个断言覆盖。

必须覆盖纯增删无风险但EXACT、name-only LOW/混合修改、registry-only归属变化且计数相同、孤儿与重复身份、缺before快照、风险不完整与变化精确并存、剩余suppressed、真正表级/全局风险、跨表风险cache适用性、空点尾部/中间/跨界/稀疏/全空/混合move、各入口冷生成和cache replay、旧语义结果不复用。

主要为C类可重算派生结果；内部转换D类。本次不改commit/main/审批授权/控制DB schema。若实施发现必须改权威绑定的事务/跨scope逻辑，则拆A/B包逐包独审；不能借修改常量扩大写边界。保持N1、M24GiB、32GiB worker envelope/8GiB reserve。

性能接受必要records/locator/bundle成本，明确省去普通增删annotations；不能宣称性能无退化。先以现有真实样本和产物规模验证资源边界，仅在明确问题时另定一个高增删样本的有限对照，不默认大量合成、全量profiling或重复采样。所需内容无法在现有预算完整生成时如实失败，不静默截断后宣称EXACT。

## 10 实施授权及尚缺现场证据

本设计已把产品取舍固定到可编写代码的程度，不把上次候选方案继续作为待定实现分支。仅有现场证据和运行范围待补：实际导入pair、实际空点误判表及Owner核收的最小真实验收范围。它们用于复现与退出，不阻止已明确Contract的后续编码准备，也不把未测结论写通过。若现场揭示来源冲突或超出本设计业务语义，再交Owner决定。

建议真实范围：两份数据一次普通比较，旧/新装置、65532与一个测量类未受影响装置；一个实际空点误判表；Preview与History同pair一致性。产品实施、最终候选验证与08联调部署分开授权；当前只完成文档与独立设计审核。

规范：[Business Navigation](contracts/business-navigation.md)、[Comparison](contracts/comparison.md)、[Risk](contracts/risk.md)、[Ordered Diff](contracts/ordered-diff.md)、[Row Location](contracts/row-location.md)、[测试规范](testing-conventions.md)、[比例化保障](refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md)。

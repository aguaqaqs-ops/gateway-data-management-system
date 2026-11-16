# Business Navigation Contract

状态：BE-b B2 已实现 v1 producer/validator；B3 已将实际 canonical streams、比较/locator 完整性与 typed Risk outcome（含 cache replay）接入 Preview/History，成功 surface 强制恰一个导航 projection。B4 已提供真实 fixture generator、17 场景及五类 golden，见 [前端交付](../refactoring/formal/plans/be-b-frontend-delivery.md)；集中验收、最终身份/OpenAPI 原件与阶段独审尚待完成，当前实施事实不表示 BE-b 已退出。

Owner：Backend Business Navigation。业务分组规则来自[第一步 §4.3–4.7](../../frontend-vnext/be-b-navigation-and-presentation-draft.md)，实现边界、预算与激活依赖见[第二步 §4/5/7](../refactoring/formal/plans/be-b-second-step-design.md)。本合同拥有导航载荷、筛选、局部事实与诊断；Surface 拥有引用与展示表，Bundle 拥有物理闭包。导航只消费已完成的 comparison/risk 事实，不重新计算两者。

## 载荷与唯一性（FE-BEB-11）

```text
BusinessNavigation:
  contract_version: backend-vnext/business-navigation/v4
  groups: [Group]
  replacement_sides: null | {before: [Group], current: [Group]}
  table_notices: [TableNotice]
  device_definition_changes: [DeviceDefinitionChange]
Group: {group_key, label, items: [Item], nonempty_item_count}
Item: {item_key, item_kind, label, attributes, tabs: [Tab], summary}
Tab: {tab_key, label, table_id, row_filter, facts, empty}
summary: {change_kinds: [SurfaceChangeKind], risk_level: RiskLevel|null, nonempty_tab_count, change_complete: boolean, risk_complete: boolean}
```

每个成功 surface 恰好一个 projection：`projection_id=business_navigation`、`projection_kind=BUSINESS_NAVIGATION`、`projection_digest=SHA256(JCS bytes)`、`risk_summary_ref=null`；诊断通过独立 `diagnostics_ref` 引用，无诊断时为 null。缺失或重复导航是 Contract 违例，消费者拒绝该 pair 并进入既有无法打开结果路径。退役 B9、`fallbackNavigation`、`preview-no-navigation` 和缺 `display_order` 时猜列序的分支；没有生产或 fixture 隐藏导航开关。

普通模式 `replacement_sides=null`，`groups` 按顺序始终含 FORWARD_CHANNELS、SECONDARY_DEVICES、COMMUNICATION_PROTOCOLS、GLOBAL_PARAMETERS、OTHER_TABLES 五组，允许空 items。固定认领也按该顺序；未认领表进入 OTHER_TABLES。item_kind 为 FORWARD_CHANNEL、DEVICE、COMPOSITE_SIGNAL_DEVICE、PROTOCOL_CHANNEL、TABLE。item/tab key、label、attributes、业务排序与十个原导航诊断按第一步；同侧重复业务键用规范标量整行字节序最小者提供 label/attributes，筛选仍覆盖全部有效身份集合。

通道表使用 `b<board>_n<link_no>_<后缀>` 或 `b<board>_c<com_no>_<后缀>`，数字按数值关联对应 net_cfg / com_cfg，范围为 `[0, 9007199254740991]`。超域、不合形状的表保留 OTHER_TABLES。仅 exe 非空配置行建立通道；重复行按规范整行排序选代表。net_cfg 固定首项，com_cfg 任一侧有非空 exe 时为第二项，否则保留在其他表。网络通道排在串口前，各按数字排序。

当前存在侧（否则前侧）的真实 COMMENT 含“引用表”时归转发通道，去掉该字样作为 tab 标签；无同侧有效注册行则保留其他表及孤儿诊断。普通通道表按对应侧配置的协议映射前缀认领所有匹配表，不限 cfg 后缀。实际表名为 tab key，COMMENT 为标签，空则回退表名；前后同表仅认领一次。replacement 两侧独立，普通 pair 当前 COMMENT 为空时不借前侧分类。映射及详细归属见[通道规则设计](../channel-table-rules-refactoring-design.md)。v3 由后端及前端严格核对，防止旧消费者将串口诊断解释为网口。

APP_TABLE_CFG_MISSING / APP_TABLE_CFG_DUPLICATE / APP_TABLE_NOT_FOUND 的 app_name 是展示用 string|null；原 app_cfg.app_name 为整数时仅在该展示/诊断边界格式化为十进制文本，string 原样保留，NULL 或非展示标量使用既有 null；全局参数项的 app_name 标签采用同一规则。此格式化不改变比较键、row_filter、规范值或表数据，不因展示标签类型而使 pair 失败。


每表整表 tab 最多一个，整表与筛选 tab 不并存；同表全部筛选 tab 只属一组。导航保留所有可认领页签，不按空行集删除。无装置可承载时，在 SECONDARY_DEVICES 用 `item_key=table:<表名>`、`item_kind=TABLE`、`tab_key=table`、`row_filter=null`、`attributes={}` 提供唯一整表入口。孤儿与诊断仍依实际谓词归属，不因空标记丢失。

`empty` 是每个 tab 必填的严格 boolean。普通比较中，至少一个逻辑侧存在，且每个存在侧的本 tab 行数已知并为 0 时为空；不存在侧不计，存在但计数未知的侧不能以 0 代替。整表用已绑定 descriptor 行数，筛选页用自己的筛选计数；表新增/删除、降级、行/表风险不影响判定。原始结构变化（原始 SCHEMA_CHANGED/SCHEMA_ONLY_CHANGED、schema change source 或双存在侧业务 schema 差异）与 DATASET_REPLACEMENT 始终不空。原始结构证据在 Comparison C 的只审计展示投影前读取；保留页签不恢复被 C 隐藏的变化或 schema 风险。

项 `summary` 只汇总 `empty=false` 的 tab 的局部变化和已确认行风险，不合并 table_scope，也不在筛选 fallback 时回填整表变化或风险。`change_complete`、`risk_complete` 分别是非空筛选 tabs 对应完整性的 AND，空集合为 true；整表项继续使用整表摘要。`change_kinds` 去重排序，`risk_level` 取已确认行风险最高值，全空项或无 tab 项为 `[]/null/0`。`nonempty_item_count` 仅统计含非空 tab 的项；公共提示独立存在，不因隐藏空页签而消失。Preview、History 与提交绑定审核共用同一 producer/document。

对发布筛选的每张共享表，各侧满足“已发布谓词覆盖行集合的并集大小 + 同侧孤儿行数 = 该侧总行数”。重复命中不累加为重复行。消费者只在有该侧快照且计数精确时核等式；缺快照侧由后端合同验证。诊断的查看整表是额外浏览入口，不另生成导航整表 tab。

## 双侧筛选与标量（FE-BEB-13）

```text
row_filter = null | {before: Predicate|null, current: Predicate|null}
Predicate = {column: string, values: [string] | [integer]}
```

整个 null 表示整表；对象中单侧 null 表示本侧无匹配身份，两侧不可同时 null。values 非空、同类型、去重；整数数值升序、字符串 UTF-8 字节升序。device_cfg 收集装置在本侧的全部有效 gid；其他共享测点表按本侧 dev_addr。两侧值相同仍发布两个谓词。配对行任一半命中即显示整对，不能假定 ROW_MODIFIED records 携带未改身份列。

| 同侧规范类型 | 谓词/context JSON | client Parquet 与消费 |
| --- | --- | --- |
| STANDARD signed/unsigned integer；SQL TINYINT/SMALLINT/MEDIUMINT/INT/BIGINT 及 parser 规范别名 | `[-9007199254740991,9007199254740991]` 内整数；unsigned 非负 | BYTE_ARRAY(UTF8) 十进制 string；按同侧已校验 `gateway.sta.enc.v1` 的 logical_type/declared_type/physical_type 严格转 BigInt，核声明位宽、符号及 safe 范围 |
| STANDARD string；SQL CHAR/VARCHAR/TINYTEXT/TEXT/MEDIUMTEXT/LONGTEXT | string | UTF8 string 原值比较；不 trim，不把数字外观文本当整数 |
| BOOLEAN、DECIMAL、FLOAT/DOUBLE、时日期、BINARY/BLOB/BIT、ENUM/SET、JSON、未知/缺 declared type 等 | 不生成谓词 | UNSUPPORTED_TYPE，按下述规则整表降级 |

整数文本必须全串是规范十进制：只允许 `0`、无前导零的正数或负数；拒绝负零、空白、小数、指数或尾随字符。JSON integer 先校验 safe number，再转 BigInt；禁止 Number/parseInt 猜类型、字符串/数字宽松相等，以及用 current 优先的联合 SurfaceColumn 类型解释 before。先校验 raw SHA/closure，再解码**同侧** metadata。物理类型、声明、值或谓词类别矛盾是 bundle 解码错误，不静默当无匹配。SQL NULL/物理缺列不匹配；已整表降级者不执行谓词断言。本功能不改 export 物理 schema 或缓存身份。

超范围/不支持类型/身份列被有效比较排除时，普通 pair 的该表撤去全部筛选 tabs，保留上述唯一整表入口。每个受影响存在侧各发一条 `DEVICE_FILTER_VALUE_UNSUPPORTED`，`side=BEFORE|CURRENT`，target 指整表项，`params={identity_column, reason:INTEGER_OUT_OF_RANGE|UNSUPPORTED_TYPE|IDENTITY_EXCLUDED}`，不回传原值，也不再发此表孤儿/局部事实诊断。共同 pair 规则排除两存在侧时发两条；不存在侧不发。物理缺列/NULL 不归为 IDENTITY_EXCLUDED。装置键超域时不构造该装置项或数值 attributes，device 整表入口保留；依赖表同样降级。replacement 仅对受影响侧应用上述降级及诊断规则，另一侧按其本侧资格独立处理；不套跨侧比较资格，只核本侧读取/筛选资格。

## 无记录行与完整性（FE-BEB-12）

两逻辑侧都存在时，有键筛选身份列须实际共存、类型兼容且参加有效比较，不在 ignored/compare_excluded/incompatible；有效键本身成立。keyless 身份列须进入 native 实际 identity frame（columns_added 分支为 selected 减 excluded），不能只核列名在 selected 中。B2 对 registry 和 schema 变化分支作此断言。整表新增/删除按存在侧筛选，不要求不存在侧有列。

普通 pair 缺 before 快照时，当前未命中 row record 的行，仅在以下**全部**成立时才能以同一身份值执行 before/current 谓词：

1. 两逻辑侧存在，身份列具备上述实际比较资格。
2. 比较成功且非 schema-only、无降级；实际 suppressed_added_count、suppressed_deleted_count 都为 0。
3. 已发布 records 按 kind 的数量与 row_change_stats 真实 added/deleted/modified 计数完全一致。
4. 已有记录的 locator 完整，且成功绑定对应快照行。

零行变化允许空 records/null locator，但须由成功比较和真实零计数证明。null ref、facts.basis=EXACT、display.replay_guarantee=EXACT 单独均不证明完整性。资格及记录完整性归后端 owner，消费者不重新计算规范行身份。

gid 7→8 而 cfg gid=7 未改，或地址 49→50 而测点未改时，满足前提的行仍可命中 before 谓词；这仅复用筛选身份，不恢复全部旧值。UPDATE_ONLY 实际抑制增删、records 截断/缺失、比较降级时，不将无 record 当前行伪造为 before；表局部事实 TABLE_FALLBACK，消费者只按可得侧、已有记录/context 浏览并明示改前对应不可确定。已知 before 计数不承诺完整改前行可浏览。不增加 before 全表导出或全行 locator 账本。

## 局部事实与表级事实

普通筛选 tab 的 facts required；整表/replacement 为 null：

```text
{basis: EXACT|TABLE_FALLBACK, change_kind: UNCHANGED|ADDED|DELETED|UPDATED|null,
 risk_level: RiskLevel|null, risk_complete: boolean,
 before_row_count: integer|null, current_row_count: integer|null,
 table_scope: null|{change: boolean, risk_level: RiskLevel|null},
 membership_changed: boolean, membership_complete: boolean,
 row_changes: null|{added, deleted, modified, moved_in, moved_out}}
```

`basis` 只表达变化完整性。EXACT 要求非 null 的 change_kind 和非负 row_changes；TABLE_FALLBACK 要求二者为 null，保留已知计数。modified 包含迁移行，moved_in/out 是其子集。risk_level 是已确认且可定位的最高行风险；risk_complete=false 时可有已知风险，null 不证明无风险。membership_changed 表示已证明的注册归属改变，membership_complete=false 表示无法完整判断；它不生成比较修改或新风险。存在内容记录或 membership_changed 时按局部前后计数确定 ADDED/DELETED/UPDATED，否则 UNCHANGED。table_scope 只存真正表级/比较级事实，同表一致。

变化不完整时每表一条 DEVICE_TAB_FACTS_UNAVAILABLE，reason 为 RECORDS_UNAVAILABLE 或 TABLE_DEGRADED。风险不完整和归属不完整分别发布 DEVICE_TAB_RISK_UNAVAILABLE 和 DEVICE_MEMBERSHIP_UNAVAILABLE，三者均 side=null、target 为共享表、params 为 identity_column 与固定 reason。资源和内部错误仍失败，不能伪装成未知。

普通导航根的 table_notices 按 table_id UTF-8 排序且唯一，元素为 `{table_id, table_scope, unlocated_row_risk, risk_complete}`；unlocated_row_risk 为 null 或 `{risk_level: RiskLevel|null, count: integer|null, reason_codes: [string]}`，原因去重排序，不能可靠相加时 count=null。仅十一类共享标准表归约公共风险：可定位的 ROW/ROW_PAIR 属局部，未命中任何装置或缺身份者进入待定位入口；TABLE 的记录数量/抑制/缺失覆盖属于待定位风险，真正 structural/degraded TABLE 或 COMPARISON 风险属于 table_scope。未知 target 保留已知等级并标记 risk_complete=false。新生成与缓存 replay 共用归约，不由混合表风险反推个人风险。所有 identity 须在 locator 消费后核对未绑定集合。

根的 device_definition_changes 按 record_identity 排序唯一，元素为 `{record_identity, change_kind: ADDED|DELETED|UPDATED, before_item_key: string|null, current_item_key: string|null, before_dev_addr: integer|null, current_dev_addr: integer|null, risk_level: RiskLevel|null, risk_complete: boolean}`。来源是 device 的实际 record 和逐侧 locator/snapshot；仅有效且已发布的本侧地址生成 item_key，不猜未改地址。定义变化独立于 tab summary。

对可复用的未变化行，按实际有行的身份值比较两侧 owner 集合，集合不同才标记 membership_changed；部分变化表须先从各侧 histogram 减去已发布 records 的贡献，并证明剩余分布相同。不能精确复用则 membership_complete=false。风险不完整本身不阻止内容身份复用。

孤儿按本侧实际发布谓词覆盖集合判定，逐侧 `DEVICE_ROWS_UNASSIGNED`。changed_row_count 无法精确证明时为 null，不填 0。计数未知仅按既有 `DEVICE_TAB_COUNT_UNKNOWN`，可与事实不可用同时存在；资源/I/O/取消/超时/内部 bug 按任务失败处理，不伪装计数未知。诊断排序、去重、target、十个原码及中文归属依第一步 §4.7；中文由前端维护，params 不含 host path/异常全文。

## Replacement

`replacement_sides != null ⇔ comparison_mode=DATASET_REPLACEMENT ⇔ groups=[]`。replacement 的 table_notices 和 device_definition_changes 均为 []。存在侧各自保留五组，缺侧列表=[]；独立认领、列展示和 key namespace，不对齐两数据集。筛选仅填本侧谓词，facts=null，无普通 diff/行风险，也无 DEVICE_TAB_FACTS_UNAVAILABLE；孤儿 changed_row_count=null。所有诊断 side 必填实际 BEFORE/CURRENT；URL、浏览状态与查看整表 key 包含 side。同名 item/tab 跨侧不冲突。分侧表名/列取 replacement_summary 本侧，不借对侧注释。

## 验证 owner 与生命周期

B2 的 business_navigation unit/contract 共享参数表权威验证认领、集合覆盖、table_scope、FE12 资格/抑制反例与 FE13 逐侧诊断；纯逻辑不建 Dolt。B3 的 row_location 验证最终文件身份/occurrence/context；B4 的真实 bundle fixture 验证 producer→decoder 互通，前端 FE4b 验证 BigInt/同侧 metadata、负向缺导航与 ref/closure。不重复实现 canonical 编码。

每表每侧有界扫描，共享 operation M/scratch/cancel/deadline；导航 16 MiB、诊断 4 MiB，计入既有 N1/M24 GiB、worker envelope32/reserve8。无跨操作新缓存或独立恢复状态机。导航/诊断位于 S1a comparison 逻辑位置，由现有 ref/保护/READY/bundle 路径管理；新增 ref 的遍历/重写及清理由 B3/B4 同轮接入。

## B2 实施接线边界

`build_navigation` 接受 `NavigationTable` 双侧、`NavigationEvidence` 和同 operation 的 `check`/`reserve`/`resources`；有界状态与序列化缓冲先向既有 M 预留，成功后将 reservation 保留至原 operation.resources 结束；失败立即释放，不建立新资源 owner。代表行的完整 canonical_order_key、值及容器在保留前计账，替换时释放旧计账；返回的 JCS bytes 在 admission 内生成并复用。流式行只保留 registry/装置代表与实际谓词身份计数，孤儿身份只聚合总数。无变化共享表从 current 单次扫描为两侧谓词分别计数，不打开 before 行流。`canonical_order_key` 必须由现有规范标量整行编码提供，producer 不另造 row identity。

`identity_excluded_sides(task,fact,column)` 核实际 selected、effective key、incompatible 与 compare_excluded，含 keyless COLUMNS_ADDED 的 selected 减 excluded 分支；物理不存在侧不报排除。`FilterRecord` 的两侧 context 来自 locator/原快照，不能从只含 changed columns 的 records 猜；`NavigationEvidence` 默认不足，实际 record-kind 数、suppressed 和 locator 证明不足时变化 fallback；风险和归属完整性独立表达。NavigationTable.local_fallback_reason 是局部 facts 与复用 guard 的共同判据，包含该表实际身份列的 record context 完整性；物理缺列单独禁止双侧复用。registry 身份值与目标本侧 declared type 类别/宽度不符时以 UNSUPPORTED_TYPE 整表呈现，不作数值/文本转换。`reduce_table_risks` 只接实际 typed TABLE/COMPARISON 事件，不读混合 summary；共享 pair pipeline 的 RiskAttribution 从 evaluator attribution_observer 接实际 typed outcome（含 cache replay），在 annotation artifact 缺失/降级时保守标记完整性不足；不读混合 RiskReport 汇总反推 scope。

B3 共享 application/business_presentation 接上述输入，实际发布恰一个 projection，导航/诊断/locator 进入已有 closure/ref/保护路径。定位算法和预算由 [Row Location](row-location.md) 拥有；完整交付与退出仍须 B4/B5 证据，不能以 helper 单测替代。

复合虚装置不依赖 device 的 65532 行；该特殊项在存在的共享测点侧使用 dev_addr=65532，不凭空构造 device_cfg 的 gid。无装置承载的共享表保留唯一整表入口，已知空行集只加 empty 标记，整表 tab 不产生局部事实不可用诊断。

## 纯结构变化投影（2026-11-13）

后台导航与风险、surface、摘要共用 Comparison v4 的统一展示判定。已证明的纯增删列不产生 table_change、变化标记或统计；表仍保留 current 浏览，不能把不同的 canonical 快照身份误宣称相同或构造缺失 before。其他真实行、有序、身份字段及诊断语义保留。v2 导航保留原始结构变化的非空标记；projection digest 依实际产物重新生成。


## F 身份与严格解码（2026-11-13）

v2 防止缺少 empty/summary 的旧文档被当作新规则结果，由后端 pydantic strict/extra=forbid 与前端 decoder 核对。导航 JCS raw SHA 进入现有 projection digest、Surface digest、bundle 物理闭包及 D Preview/READY 完整绑定，消费者继续核全部引用与摘要，不新增仅计算的身份轴。比较事实/缓存未变，不改 comparison digest 或强行禁用缓存；既有 Preview assemble-state v6、History assemble-state v3 防止恢复旧版导航的 assemble checkpoint，由各自 state decoder 校验。没有兼容路径或旧结果迁移。

验证 owner 为 business_navigation 参数表（标记/保留/非空汇总/未知/孤儿）、pair pipeline 贯通（原始结构与 C 隐藏共存、Preview/History）、提交绑定结果贯通（不可变完整闭包）和前端 decoder/展开交互。golden 与真实 producer fixture 必须一并重建，生成过程本身不算测试通过。


上一版 producer/consumer golden 位于 `vnext/fixtures/golden/presentation/be-b/v3/`，19 场景的五类文件由同一真实 producer 两次独立生成且逐字节相同；manifest 保存来源提交、输入摘要和逐文件摘要。v1、v2 保留历史向量，v3 当时的 owning consumer 不再读取它们。前端 fixture 替换由同一生成归档提供，前端接入前不把后端生成成功宣称前端已兼容。


F 前端消费者（Owner 2026-11-13 直接授权）严格要求 v2 的 empty、summary 与组非空计数，缺失/错误类型/非中性全空摘要拒绝打开；不再按 Surface 行数或展示 change kind 推导空页签。默认隐藏及显式展开只影响可见项/页签，不改变服务端摘要或非空组计数；筛选未知计数显示“—”，不借整表行数。replacement 分侧解析后合并同名导航时仅按已发布标记做集合去重，仍保留每侧原文；后端绑定及审计不由前端重建。

F 前端复审修复（2026-11-14）：URL 按 node+tab 精确恢复，包括默认隐藏的空页签；无效 tab 先留在原项，无效 node 不借其他项的同名 tab。全空 pair 保留首个页签与展开入口。用户显式隐藏当前空页签时切换到可见非空项；没有非空项时保留可访问的空页签。组头展示当前搜索/“仅差异”过滤后列表中的非空项数，展开空页签不增加该数；服务端 nonempty_item_count 仍描述完整组，消费者不改写它。

F 能力边界修复（2026-11-14）：`change_kind` 的唯一语义词汇仍由 [Surface Contract](comparison-surface.md) 定义。导航的 `NavigationChangeKind` 仅为自身 typed 输入与严格 summary 校验所需的局部契约表示，不引入独立状态或词汇来源；Application 将 Surface owner 的已归并值显式转换后传给导航。导航不得反向依赖 Surface Assembly，也不将有业务归属的类型移入 Shared Kernel。导航测试同时核对双方完整值集相等、逐个 Surface kind 的非空汇总 wire 值不变及未知值拒绝；新增/删除 Surface kind 时必须同步该边界表示，不能单独扩展导航词汇。本次不改文档版本、wire 值、摘要预像、cache 或 golden。


## 未启用应用的可选参数表（Owner 2026-11-14）

app_cfg 投影读取 app_name、table_cfg、enable。每个逻辑侧 enable 精确为 0:NO 的模块，
table_cfg 为空或本侧目标表不存在均属正常配置，不发布 APP_TABLE_CFG_MISSING / APP_TABLE_NOT_FOUND。
已存在的目标表仍可浏览；重复引用诊断保留。1:YES、NULL、缺列或未知值不推断为未启用，沿用原诊断。
目标存在性按引用行所在侧判断，不能用另一侧同名表替代。诊断文档形状与版本不变；结果由现有 projection digest
绑定，旧 assemble checkpoint 的拒绝策略见 Risk Contract 本轮修订。

正常导航提示与比较降级/失败的视觉分类归前端呈现；本次后端先修正无效告警，不将真正比较错误降为正常提示。

## v4 身份与消费者

v4 标识本合同的局部变化、风险和归属完整性分离及根级公共提示。后端文档边界以 pydantic strict/extra=forbid 解码，前端严格检查同一必填形状；旧文档不能冒充 v4。导航字节由现有 projection digest、surface 与 bundle 闭包核对。Preview job/capability、History job 和组装 checkpoint 的版本绑定见 [Bundle](comparison-bundle.md)；已冻结 Submission 审核保留原绑定身份，不以当前规则版本重判准入。v4 producer golden 和真实 fixture 须与消费者一同更新。

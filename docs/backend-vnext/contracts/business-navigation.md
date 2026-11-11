# Business Navigation Contract

状态：BE-b B2 已实现 v1 producer/validator；B3 已将实际 canonical streams、比较/locator 完整性与 typed Risk outcome（含 cache replay）接入 Preview/History，成功 surface 强制恰一个导航 projection。B4 fixture/golden、集中验收与阶段独审尚待完成；当前实施事实不表示 BE-b 已向前端正式交付。

Owner：Backend Business Navigation。业务分组规则来自[第一步 §4.3–4.7](../../frontend-vnext/be-b-navigation-and-presentation-draft.md)，实现边界、预算与激活依赖见[第二步 §4/5/7](../refactoring/formal/plans/be-b-second-step-design.md)。本合同拥有导航载荷、筛选、局部事实与诊断；Surface 拥有引用与展示表，Bundle 拥有物理闭包。导航只消费已完成的 comparison/risk 事实，不重新计算两者。

## 载荷与唯一性（FE-BEB-11）

```text
BusinessNavigation:
  contract_version: backend-vnext/business-navigation/v1
  groups: [Group]
  replacement_sides: null | {before: [Group], current: [Group]}
Group: {group_key, label, items: [Item]}
Item: {item_key, item_kind, label, attributes, tabs: [Tab]}
Tab: {tab_key, label, table_id, row_filter, facts}
```

每个成功 surface 恰好一个 projection：`projection_id=business_navigation`、`projection_kind=BUSINESS_NAVIGATION`、`projection_digest=SHA256(JCS bytes)`、`risk_summary_ref=null`；诊断通过独立 `diagnostics_ref` 引用，无诊断时为 null。缺失或重复导航是 Contract 违例，消费者拒绝该 pair 并进入既有无法打开结果路径。退役 B9、`fallbackNavigation`、`preview-no-navigation` 和缺 `display_order` 时猜列序的分支；没有生产或 fixture 隐藏导航开关。

普通模式 `replacement_sides=null`，`groups` 按顺序始终含 FORWARD_CHANNELS、SECONDARY_DEVICES、COMMUNICATION_PROTOCOLS、GLOBAL_PARAMETERS、OTHER_TABLES 五组，允许空 items。固定认领也按该顺序；未认领表进入 OTHER_TABLES。item_kind 为 FORWARD_CHANNEL、DEVICE、COMPOSITE_SIGNAL_DEVICE、PROTOCOL_CHANNEL、TABLE。item/tab key、label、attributes、业务排序与十个原导航诊断按第一步；同侧重复业务键用规范标量整行字节序最小者提供 label/attributes，筛选仍覆盖全部有效身份集合。

每表整表 tab 最多一个，整表与筛选 tab 不并存；同表全部筛选 tab 只属一组。已认领但无可见 tab 的表不由前端自动补入 OTHER_TABLES。省略表须两侧已知零行、局部 EXACT 且无变化/风险、整表 UNCHANGED/BUSINESS_EQUIVALENT 且无风险。表级 schema/风险、空 sg_cfg 或共享表不能因空行集消失；无装置可承载时，在 SECONDARY_DEVICES 用 `item_key=table:<表名>`、`item_kind=TABLE`、`tab_key=table`、`row_filter=null`、`attributes={}` 提供唯一整表入口。

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
{basis: EXACT|TABLE_FALLBACK,
 change_kind: UNCHANGED|ADDED|DELETED|UPDATED|null,
 risk_level: RiskLevel|null,
 before_row_count: integer|null, current_row_count: integer|null,
 table_scope: null|{change: bool, risk_level: RiskLevel|null}}
```

EXACT 下 change_kind 非 null，risk_level=null 表示无行级归属风险。TABLE_FALLBACK 下两者必须 null（未知），能确定的计数保留。变化/行风险按 records.row_identity 和两侧身份归属，同 tab 去重。表新增/删除/schema change 进入 table_scope.change；单纯行变化不进入。table_scope 风险只从实际 TABLE/COMPARISON typed 风险归约获取，含 cache replay/typed 降级，禁止由混合 RiskReport.tables[].risk_level 反推。同表筛选 tabs 的 table_scope 一致；comparison 全局目标应用所有表，带 table_id 的目标只应用该表。fallback 下保留已知表事实，null 不证明无风险。

records/annotations/归属不完整且现有有界事实不足以证明 EXACT 时，全表筛选 tabs 统一 TABLE_FALLBACK，每表恰一条 `DEVICE_TAB_FACTS_UNAVAILABLE`：`side=null`、target={group_key:SECONDARY_DEVICES,item_key:null,tab_key:null,table_id}、params={identity_column,reason:RECORDS_UNAVAILABLE|RISK_ATTRIBUTION_UNAVAILABLE|TABLE_DEGRADED}，多原因按所列顺序择首。存在筛选 tabs 时，此码存在 iff 全表 TABLE_FALLBACK。前端用整表 surface/RiskReport 参与汇总/筛选并提示按整表，不给全部行涂整表风险；fallback tabs 保留。

孤儿按本侧实际发布谓词覆盖集合判定，逐侧 `DEVICE_ROWS_UNASSIGNED`。changed_row_count 无法精确证明时为 null，不填 0。计数未知仅按既有 `DEVICE_TAB_COUNT_UNKNOWN`，可与事实不可用同时存在；资源/I/O/取消/超时/内部 bug 按任务失败处理，不伪装计数未知。诊断排序、去重、target、十个原码及中文归属依第一步 §4.7；中文由前端维护，params 不含 host path/异常全文。

## Replacement

`replacement_sides != null ⇔ comparison_mode=DATASET_REPLACEMENT ⇔ groups=[]`。存在侧各自保留五组，缺侧列表=[]；独立认领、列展示和 key namespace，不对齐两数据集。筛选仅填本侧谓词，facts=null，无普通 diff/行风险，也无 DEVICE_TAB_FACTS_UNAVAILABLE；孤儿 changed_row_count=null。所有诊断 side 必填实际 BEFORE/CURRENT；URL、浏览状态与查看整表 key 包含 side。同名 item/tab 跨侧不冲突。分侧表名/列取 replacement_summary 本侧，不借对侧注释。

## 验证 owner 与生命周期

B2 的 business_navigation unit/contract 共享参数表权威验证认领、集合覆盖、table_scope、FE12 资格/抑制反例与 FE13 逐侧诊断；纯逻辑不建 Dolt。B3 的 row_location 验证最终文件身份/occurrence/context；B4 的真实 bundle fixture 验证 producer→decoder 互通，前端 FE4b 验证 BigInt/同侧 metadata、负向缺导航与 ref/closure。不重复实现 canonical 编码。

每表每侧有界扫描，共享 operation M/scratch/cancel/deadline；导航 16 MiB、诊断 4 MiB，计入既有 N1/M24 GiB、worker envelope32/reserve8。无跨操作新缓存或独立恢复状态机。导航/诊断位于 S1a comparison 逻辑位置，由现有 ref/保护/READY/bundle 路径管理；新增 ref 的遍历/重写及清理由 B3/B4 同轮接入。

## B2 实施接线边界

`build_navigation` 接受 `NavigationTable` 双侧、`NavigationEvidence` 和同 operation 的 `check`/`reserve`/`resources`；有界状态与序列化缓冲先向既有 M 预留，成功后将 reservation 保留至原 operation.resources 结束；失败立即释放，不建立新资源 owner。代表行的完整 canonical_order_key、值及容器在保留前计账，替换时释放旧计账；返回的 JCS bytes 在 admission 内生成并复用。流式行只保留 registry/装置代表与实际谓词身份计数，孤儿身份只聚合总数。无变化共享表从 current 单次扫描为两侧谓词分别计数，不打开 before 行流。`canonical_order_key` 必须由现有规范标量整行编码提供，producer 不另造 row identity。

`identity_excluded_sides(task,fact,column)` 核实际 selected、effective key、incompatible 与 compare_excluded，含 keyless COLUMNS_ADDED 的 selected 减 excluded 分支；物理不存在侧不报排除。`FilterRecord` 的两侧 context 来自 locator/原快照，不能从只含 changed columns 的 records 猜；`NavigationEvidence` 默认不足，实际 record-kind 数、suppressed、locator 及风险完整性证明不足时统一 fallback。NavigationTable.local_fallback_reason 是省略、局部 facts 与复用 guard 的共同判据，包含该表实际身份列的 record context 完整性；物理缺列单独禁止双侧复用。registry 身份值与目标本侧 declared type 类别/宽度不符时以 UNSUPPORTED_TYPE 整表呈现，不作数值/文本转换。`reduce_table_risks` 只接实际 typed TABLE/COMPARISON 事件，不读混合 summary；共享 pair pipeline 的 RiskAttribution 从 evaluator attribution_observer 接实际 typed outcome（含 cache replay），在 annotation artifact 缺失/降级时保守标记完整性不足；不读混合 RiskReport 汇总反推 scope。

B3 共享 application/business_presentation 接上述输入，实际发布恰一个 projection，导航/诊断/locator 进入已有 closure/ref/保护路径。定位算法和预算由 [Row Location](row-location.md) 拥有；完整交付与退出仍须 B4/B5 证据，不能以 helper 单测替代。

复合虚装置不依赖 device 的 65532 行；该特殊项在存在的共享测点侧使用 dev_addr=65532，不凭空构造 device_cfg 的 gid。无装置承载的空共享表只有完整 EXACT/无变化/无风险证明才可省略；证明不足时保留唯一整表入口，整表 tab 不产生局部事实不可用诊断。

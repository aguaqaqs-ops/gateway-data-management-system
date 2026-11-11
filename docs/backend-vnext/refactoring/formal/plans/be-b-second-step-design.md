# BE-b 第二步：导航、展示元数据与行定位设计

日期：2026-11-10；2026-11-11 按首轮后端独审修订。状态：**设计候选；待后端复审与前端定向核对，不代表产品已实施**。

Owner 本轮授权：落成第二步设计/执行计划，启动 GPT-6-Astra 后端独审，提供前端定向核对提示词，由 Owner 转交并带回结果。授权不含产品编码、上线或 push。Owner 同意前轮建议：历史展示元数据冻结；仅注释变化用于当前 Preview，不回写旧历史，不创造规范业务变化。

业务依据：[第一步 §4–§6](../../../../frontend-vnext/be-b-navigation-and-presentation-draft.md)、[FE4 kickoff §4/§5.3](../../../../frontend-vnext/fe4-kickoff.md)。实现基线 B=`42780a12303c8040526bf5dc8f9c6f0acb12dbb1`（main、`p7-s1a-exit`），`vnext` tree=`bd452d67dc4bfe7ae99c13fea80d474d372b69ca`。S1a 独审 EXIT_GO 与实际变化清单在 `/home/dev/gdds-stage-exchange/p7-s1a/`；不把 B 的验证当作 BE-b 验证。

执行与验收见[执行计划](be-b-execution-plan.md)。本文只定义目标；Accepted owning Contract 在相应实现包中同步激活，旧生产状态不提前改写。审核、提示词、原件和追加日志放 `/home/dev/gdds-stage-exchange/be-b/`。

## 1. 范围与设计决定

完整交付第一步 §4.1–§4.10：五个业务分组、列中文名/列序/固定列、导航诊断、Preview 改前公式及名称映射、普通表行定位、pair/view ID 修复、surface 诊断稳定编码。FE4b 在 BE-b exit 后接入；P7-S1b 不构成本阶段依赖。

不增加按行 HTTP API、后台取数、隐藏列、列宽规则、新服务/数据库、迁移兼容层、全量遥测或多 worker。保留正式无导航/无注释/无 locator 时的展示回退；它们不是旧格式双读。

| 决定 | 目标 |
| --- | --- |
| BD1 注释 | 单独的展示元数据随 canonical manifest 冻结，禁止写入 Dolt DDL COMMENT；规范行/IPC/Parquet 不携带注释 |
| BD2 计算 | Application 编排共用 pair pipeline；新 capability 产出导航/展示/locator；surface 仍不读表、不算 diff/risk |
| BD3 资源 | 一次建索引、按表/侧处理、同一个 operation M/scratch/cancel/deadline；保留 DC39 |
| BD4 缓存 | 复用既有 comparison/risk、canonical 与 Parquet export cache；首版不新增跨操作导航或 locator cache |
| BD5 物理行序 | locator 对最终 Parquet 解码行号；表内容的语义绑定与物理文件完整性分开，详见 §6 |
| BD6 历史 | Submission 的精确 manifest ref 是注释权威，不能按 snapshot digest 查“最新注释”；INITIAL 无注释时按标识符回退 |
| BD7 前端形状补足 | §4.2 的双侧筛选、§4.3 的 replacement 分侧、§6 的表语义绑定须前端定向核对；不存在默许旧消费者可直接读取的承诺 |

风险：历史绑定与 canonical identity 边界 A；checkpoint/READY 的完整引用 B；导航、定位和 export 中间数据 C；纯列规则 D。沿用 S1a 单组单 worker 信任域、位置 codec、协作发布和保护 UoW。失败按现有 operation 失败/重试，不建立独立投影恢复状态机。

## 2. 已核源码与责任边界

以下路径相对仓库根，均核自 B：

| 实际入口 | 现状与改动责任 |
| --- | --- |
| `vnext/rust/gateway-compute-core/src/table_access/{statements,model,types}.rs` | COMMENT 当前跳过；保留标识符语义，新增注释字段与预算核算 |
| `vnext/backend/src/gateway_backend/capabilities/table_access/{contracts,native}.py` | Rust Arrow adapter 是生产 SQL 路径；`tests/support/table_access_sql.py` 也调用 native，并非独立 Python parser |
| `capabilities/storage_projection/{contracts,_digest,package,arrow,publish}.py`（以下 backend 路径省略同前缀） | manifest 当前 `3.3.0`；其完整 JSON 除 manifest_digest 外直接参与 manifest digest，需要分离展示字段 |
| `application/canonical_metadata/*`、`infrastructure/control_db/sqlite_commit_metadata.py` | repository+commit+scope → finalized Submission → 精确 manifest ref；沿用此权威链 |
| `infrastructure/repository_write/import_publication.py`、`application/submit_jobs.py` | PrepareImport 输入/输出 manifest、checkpoint 验证与最终 Submission 绑定必须保留展示字段 |
| `application/pair_pipeline.py` | 共用 compare→records→risk→surface；新增 projection/locator 在 surface 前计算 |
| `application/history/compare_jobs.py` | 多节点需求/导出可复用；不按 pair 重复读取同一节点数据 |
| `capabilities/surface_assembly/*`、`capabilities/bundle_assembly/*` | 新显式输入、ref 遍历/重写、digest；bundle 只闭合已完成产物 |
| `capabilities/snapshot_materialization/{artifact,canonical_store,_parquet}.py` | canonical cache 与最终 export 行序不能混为一谈；已有 display_name 是 DDL 标识符，不能直接覆盖为 COMMENT |
| `vnext/rust/gateway-compute-core/src/comparison/standard.rs` | 唯一 standard/keyless row identity、occurrence 编码 owner，定位复用该 owner |

新增 capability 目标为 `business_navigation/`、`table_presentation/`、`row_location/`。名称不是强制目录模板，可按现有架构规则合并小模块；禁止导入 `legacy` 或复制生产编码。第一步引用的旧 capability 文档不作为当前实现事实。

## 3. 展示元数据：解析、保存、精确绑定

### 3.1 字段与解析

SourceTableDescriptor / SourceColumnDescriptor 增加 `comment: str | None`；已有 `display_name` 保持原 DDL 标识符，不改列身份/碰撞判定。新增 flow-neutral `PresentationMetadata`：

```text
tables: [{table_name, comment: string|null,
          columns: [{name, comment: string|null}]}]
```

表按 canonical name UTF-8 字节序，列按 DDL ordinal；完整覆盖输出 canonical 表/列，无 COMMENT 显式 null。被 storage projection 删除的列不进入最终展示元数据；派生 `composite_signal_point` 无源注释的字段为 null，按已确认回退规则显示。业务列规则只作用于 surface，不重排规范表。

只捕获已支持 CREATE TABLE 中表/列 COMMENT 字符串，使用现有 SQL 字符串转义和字符集规则；SQL 行注释/块注释不是展示注释。不引入 ALTER COMMENT/新语句 allowlist。空串或去掉首尾空白后为空视为 null，其他内容保留解码值；前端按文本渲染，禁止 HTML 解释。多个 COMMENT 使用最后一个，Rust/Python oracle 同规则；NUL 和非法字符串按 parser 既有 malformed 分类拒绝。注释长度计入既有 max_field_bytes、statement/source 和 operation 内存预算；不无界积累或静默截断。

当前主线已经删除 Python 生产 SQL parser。第一步“同时加入 Python 参照”落实为**测试专用、独立的 COMMENT 提取 oracle 和共享手写向量**，不恢复第二条生产解析路径。oracle 只覆盖本次 CREATE/COMMENT 字面值子集，与 native 输出逐项比对；其余语法仍由现有全量 golden/conformance 约束。不得把同一 native adapter 调两次称为差分。不改 legacy 文件。

### 3.2 持久化与摘要

CanonicalizationManifest `3.4.0` 新增 required `presentation`（上述对象），保留既有 ArtifactRef/位置与 Submission ref 字段，不增加独立元数据表或新 ref。durable serializer 编码所有字段；`compute_manifest_digest` 使用显式 canonical 字段白名单，排除 `presentation`。Contract 版本变化会一次性改变 manifest_digest；在同一新版本内，仅改注释不改变该摘要。

`source_artifact_digest` 保持现有 raw snapshot 业务摘要来源，不改成含注释的 SQL 文件 SHA。SourcePackage 的原始输入 SHA 本来会变化，不宣称其稳定。规范状态、table/business schema、raw_content、comparison 与 risk 的业务输入都不接收 presentation；row codec、Dolt replay SQL、canonical IPC、Parquet schema metadata 继续使用不含 COMMENT 的 descriptor。

manifest raw SHA/size/ArtifactRef 保护完整展示载荷。不能只校验不含 presentation 的 manifest_digest：精确 ref 的 raw SHA 校验、typed decode、完整表列集合校验仍执行。读取到缺字段/旧版本/损坏 manifest 按现有 metadata error 拒绝；“注释 null”可回退，不能把 manifest 丢失当无注释。

传递路径：SQL parse → raw materialization 的独立 presentation 值 → canonical projection manifest → Preview 冻结 manifest ref/closure → Submit PrepareImport 的输出 manifest → finalized Submission。raw materialization 的 in-memory table-set result 显式携带 presentation，canonical projection 按保留列变换后写 manifest；不塞入逐表 canonical wrapper/IPC，也不在 table-set closure 再保存一份。pair pipeline 增加显式 before/current_presentation 参数，排除 snapshot/comparison 输入身份。

Preview FULL 的 initial 和 modified 已各有 canonical manifest ref，分别提供展示值；MODIFIED_ONLY 的 initial 与 baseline 共用 commit metadata 来源。baseline/History 通过 scope+commit resolver 获取；INITIAL 用空来源。`_materialized_preview_inputs_from_checkpoint` 重开精确的 initial/modified manifest 并从冻结 baseline commit 重取 presentation，不从 canonical cache 的 descriptor 猜注释；不使用新上传覆盖已冻结侧。PrepareImport 保留现有 frozen_manifest 原对象传递方式，新 durable serializer 完整编码 presentation。所有 producer/decoder 同轮修改，只支持目标格式。

History 通过现有 commit metadata resolver 加载精确 manifest 的 presentation，作为独立参数传入展示 resolver；不修改 canonical binding 的业务 StorageRuleView。相同 canonical digest 的两个上传可以拥有不同 presentation；从一个版本读取的值不污染另一个。INITIAL 使用当前正式 INITIAL Contract，缺少历史展示来源时空 presentation/标识符回退，不取当前上传补写 INITIAL。不存在新“latest comments”索引。

### 3.3 业务行为

- 同一业务内容仅改注释：本次 Preview 显示新注释，原 comparison/risk/规范状态不变；Submit 仍返回 `NO_CANONICAL_CHANGE`，无新 Dolt commit/Submission/历史覆盖。
- 注释与业务内容一起变化：新 Submission 的 manifest 保存该上传的全量展示元数据，包括本次未发生业务变化的表；旧节点仍取旧 manifest。
- 标签采用当前侧非空注释 → 基线侧非空注释 → 标识符。replacement 分侧浏览则仅取本侧注释，不跨无关联数据集借名称。
- Preview 冻结与 T1/PrepareImport 恢复继续使用同一个精确 ref；不引入仅为了注释的跨 DB/文件事务。

## 4. 导航、列展示与诊断

### 4.1 正常 directed pair

BusinessNavigation v1 保持第一步的 `groups/items/tabs`、五个 group、item_kind/attributes 和诊断编码。一个 pair 一份导航 JCS JSON；`projection_id=business_navigation`、`projection_kind=BUSINESS_NAVIGATION`、`projection_digest=SHA256(JCS bytes)`，risk_summary_ref=null；诊断另行引用。无诊断 diagnostics_ref=null。

固定认领顺序：FORWARD_CHANNELS → SECONDARY_DEVICES → COMMUNICATION_PROTOCOLS → GLOBAL_PARAMETERS → OTHER_TABLES。保留第一步已认领但无可见页签的通道表，验收按内部认领账本而非“每表必须出现在可见 tabs”判定。`app_cfg` 指向已认领表时不重复认领，按 APP_TABLE_CFG_DUPLICATE 提示。任何未被认领表进入 OTHER_TABLES。

组顺序固定上述顺序；通道按 board/link_no 数值、装置按 dev_addr 数值、全局固定项在先随后按目标表名 UTF-8 排序、其他表按 canonical name 排序。item/tab key 使用第一步键规则。两侧同一项的 label 优先 current 非空业务名称，再 before，再稳定标识；同侧重复业务键使用规范标量编码的整行字节序最小者提供 label/attributes，与 SQL 行序无关。代表行只决定显示 label/attributes，不能代替筛选集合；每侧收集该 dev_addr 的全部有效 gid，筛选按 §4.2 的集合谓词。重复地址/gid 仍出既定诊断，同一 tab 的行/风险去重，不丢弃行。

数据异常使用第一步十个导航编码，另按 §4.2 增补局部事实不可用编码；无法按身份列计数（列缺失、已知不可解码/表降级）才产生 DEVICE_TAB_COUNT_UNKNOWN。资源不足、I/O、取消、超时、内部 bug 不伪装为“计数未知”；按现有任务失败/取消处理。诊断排序、去重、target 校验、中文文案归属沿用第一步。params 无服务器路径、异常全文。

### 4.2 双侧筛选补足（需前端核对）

第一步单一 `{column,value}` 无法表达同一 dev_addr 的 device_cfg 筛选 gid 前后变化。直接将新 v1 的目标形态定为：

```text
row_filter = null                         # 整表
           | { before: Predicate|null, current: Predicate|null }
Predicate = { column: string, values: [string] | [integer] }
```

row_filter 对象里的 null 表示本侧没有匹配身份，**不是整表**；对象两侧不可同时 null。整个 row_filter=null 才是整表。values 非空、同类型、去重，整数数值升序、字符串 UTF-8 字节升序；谓词是该列的集合成员判断，通常为单元素。普通共享测点表按各侧 dev_addr，device_cfg 按各侧该装置的全部有效 gid；两侧相等仍写两个谓词。类型必须与规范身份列值一致，不做字符串/数字宽松相等。缺失/无效身份不造匹配。

**可达性与孤儿诊断：** 对每张共享表，分别用本侧实际发布 tab 谓词的覆盖集合判断未分配行，取代第一步“两侧装置总表都不存在”的条件。before 有装置而 current 已删、current 测点仍残留，或 gid 7→8 后 current cfg 残留 gid 7，均触发本侧 DEVICE_ROWS_UNASSIGNED，提供既有“查看整表”。重复地址 49 对应 gid 7/8 时一个 tab 的 values=[7,8] 覆盖两组；不同装置共用 gid 时行可同时出现在各自 tab，但每 tab 内仅计一次。筛选/计数/变化归属共用同一谓词，不能按代表行重新算。按每表每侧集合线性扫描；未知计数的 tab 不省略；仅两侧已知零且确定无变化才可省略，因此省略项不藏行。

普通 pair 的筛选 tab 必须提供：

```text
facts:
  basis: EXACT | TABLE_FALLBACK
  change_kind: UNCHANGED | ADDED | DELETED | UPDATED | null
  risk_level: <现有 RiskLevel> | null
  before_row_count: integer|null
  current_row_count: integer|null
```

EXACT 的 change_kind 非 null，risk_level=null 才表示精确的无风险；行数 unknown 用 null。缺侧已知零与有侧零由谓词区分。变化按记录两侧身份分别加入，地址/gid 变化可影响两个装置 tab，同一 tab 去重；风险按相同归属连接，不能只取 current。精确变化类型：无归属变化 UNCHANGED；before=0 且 current>0 为 ADDED；current=0 且 before>0 为 DELETED；其余有归属变化 UPDATED。

records/annotations 不完整、table degraded 或缺少可用身份连接时，若现有有界计算结果仍足以证明全部局部变化与风险，可输出 EXACT；否则输出 TABLE_FALLBACK，局部 change_kind/risk_level **必须 null，表示未知而非无变化/安全**，计数能确定仍保留。前端按 basis 用 surface/RiskReport 的**整表**变化/风险参与页签标记、分组汇总与“只看变化/风险”筛选，并提示“此页签按整表提示，变化或风险无法精确归属”；不把整表风险涂到全部局部行。TABLE_FALLBACK 保留页签，即使局部已知零也不由未知事实推断无变化。

新增稳定诊断 `DEVICE_TAB_FACTS_UNAVAILABLE`：target 指向该 tab 与 table，side=null，params={identity_column: string, reason: RECORDS_UNAVAILABLE|RISK_ATTRIBUTION_UNAVAILABLE|TABLE_DEGRADED}；多原因按此顺序择一最先项，不重复输出同一提示。中文文案由前端维护；未知编码仍按既定回退显示。COUNT_UNKNOWN 仅计数问题，二者可以同时出现。既有 DEVICE_ROWS_UNASSIGNED 的 row_count 为已知未覆盖行数；changed_row_count 改为 integer|null，null 明示“变化数未知”，不能填 0；发布被截断时不得从部分 records 冒充精确计数。上述 basis 与新增码一并送前端核对。

这是对第一步不充分形状与孤儿判定的明确修订，须更新第一步/Business Navigation Contract 与 FE4b；不同时保留旧 `{column,value}` 解码。

### 4.3 Dataset Replacement 的分侧形状（需前端核对）

仍每 pair 一份导航，而不是两个同 kind projection 让前端 `.find()` 任取其一：

```text
BusinessNavigation:
  contract_version: backend-vnext/business-navigation/v1
  groups: [Group]
  replacement_sides: null | { before: [Group], current: [Group] }
```

普通比较 replacement_sides=null；replacement 时 groups=[]，两侧独立构造、独立认领、独立 key namespace，不跨侧对齐装置/通道。每侧 item/tab 仍是相同结构；筛选只设置本侧谓词，另一侧 null，按本侧实际覆盖集合判孤儿。分侧浏览的筛选 tab 不输出普通 diff `facts`（null），UI 使用本侧表/行计数，不展示增删变化/行风险，不产生 DEVICE_TAB_FACTS_UNAVAILABLE；孤儿 changed_row_count=null，不将替换行称为普通改动行。diagnostic.side 必须是 BEFORE/CURRENT，target 在对应侧解析。此规则是第一步“分别生成、不跨侧连接”的序列化补足；前端需要按模式选分侧导航。

分侧列展示复用已有 `replacement_summary.before/current.columns`，在各自 SurfaceColumn 上写本侧 display_name/pinned/display_order。各侧 `SurfaceReplacementSide` 增加 `display_name`，取本侧表注释或标识符；navigation 的整表 item/tab label 取同一来源，业务项/固定页签名称仍按第一步。表头、浏览标题、“查看整表”和带 side 的诊断表名读取该侧 replacement_summary.display_name；顶层 SurfaceTable.display_name 仅为 pair 总览标签，不能替代分侧标题。缺侧 summary=null，没有字段时的旧格式不双读。

### 4.4 列展示与稳定诊断

SurfaceColumn 新增 required `pinned: bool` 与 `display_order: int`（0 起，表内唯一连续）。`columns` 数组原有 canonical/兼容语义不变；DDL 顺序由独立元数据取得，不能把数组原本的字母序当 DDL 顺序。有业务列序规则先排规则中的现存列，剩余按 DDL ordinal；只在 before 存在的列按 before ordinal 追加。固定列仍为 no、name，否则 description。列宽/对齐归前端，无隐藏。

列序 registry 属于 table_presentation，使用显式 `presentation_rules_version=1`，不修改 canonical/comparison ruleset digest。业务导航产物本身的字节与最终列字段已包含规则结果，不添加仅为缓存的版本轴。

surface diagnostics_summary 保持 string 编码数组，参数不另增 DTO；表名来自所在 SurfaceTable，根级仅汇总 code。替换：

| 原生产输出 | 新 code |
| --- | --- |
| `DUPLICATE_EFFECTIVE_KEY:<table>` | `DUPLICATE_EFFECTIVE_KEY` |
| `max_annotations_per_pair exceeded` | `RISK_ANNOTATION_LIMIT_EXCEEDED` |
| `risk diagnostics truncated` | `RISK_DIAGNOSTICS_TRUNCATED` |
| 未分类比较异常的 Python 类名 | `COMPARISON_INTERNAL_ERROR` |

已有稳定 typed code 保持；cancel/deadline/resource 不落入 generic internal error。日志仍可保留受控内部错误上下文，不进入面向用户产物。实施包必须按生产 emit 点盘点完整代码表、删除替代分支并输出机器可核列表；上表不承诺源码之外不存在其他遗留 emit 点。导航诊断仍保留结构化 params，不与 surface 诊断混为一类。

## 5. 计算顺序、定位与复用

### 5.1 共享 pair pipeline

1. 读取两侧 metadata/presentation，构造 comparison plan；复用当前 native task session 与结构性过滤。
2. compare → records publication → risk 保持既有顺序；复用已算的有界身份计数/变化归属，不因 records 截断丢失表级“有变化”事实；未具备精确局部聚合时按 §4.2 TABLE_FALLBACK，不为完整聚合建立另一套全量 records。
3. 明确最终表交付集合并取得 export refs。Preview：current 全表、整表删除的 before，以及双侧浏览表的 changed before；History/replacement 保持所有可用侧。双侧浏览表当前只有 device/composite_signal_point。changed 指完整可浏览内容/声明不等，不能只看排除 formula_ast_json 后的 comparison changed_count。完全相同身份时两侧绑定同一 export ref。
4. 在最终 export refs 上计算 row locator；计算导航/诊断、列展示；将只含值/refs 的结果交给 surface assembly。
5. surface READY 后按现有 closure/重写路径组装 bundle；operation READY 与保护移交必须覆盖所有新 ref。不会在下载 HTTP 中现算导航或定位。

只为导航读取 net_cfg/device/app_cfg 的必要列和已认领共享表的身份列；相同表身份可复用 current 计数。表未变化时不额外取 before 行；变化表按侧处理。History 三节点按节点/表/侧复用任务内计数。先按记录 identity 索引，再按身份汇总风险，禁止“装置×记录×标注”扫描。

业务导航按行数据量为线性扫描；最终有限项排序、JCS 编码及 locator 输出排序不冒称零成本。若需要跨全量行持久索引或新数据库才能满足预算，停止该方案并重新设计，不默认引入通用索引平台。

### 5.2 RowLocator 的算法与绑定

形状按第一步：Parquet，`row_identity: binary(32) not null`、`before_row_index: int64 nullable`、`current_row_index: int64 nullable`；按 row_identity 字节升序，每条**已发布普通行级记录**一行。schema 级记录不占 locator 行；有序/blank 专用记录走原位置语义；无 row records、超发布上限、replacement 都为 null ref。

先读取已发布标准记录的 identity 集，预留其有界字典空间；按最终 Parquet 的 row-group/batch/file 顺序计全局 0 起 index，用同一 native standard row encoder 编码键。只为命中的记录保存 index；每侧每条记录必须匹配恰好一次，存在但无法绑定是 producer 错误，不能静默降级成无 locator。

keyless 使用 `standard.rs` 的 selected/excluded columns 与 `occurrence_digest`，每侧相同值第 0、1…次按该文件物理遍历顺序计数；记录 occurrence 从两侧计数差产生，不能把重复行一律指向第一行。该遍历只决定相同规范值的等价副本位置，不改变比较身份。计数表受 operation M 约束；释放上一表后处理下一表。无快照侧字段 null；新/删记录不存在的一侧也 null。风险标注经 records.row_identity 关联，不新增另一套定位标识。

新 native helper 抽取并复用 standard 编码函数，接受解码后的批与 comparison schema，不能让 Python/浏览器重新实现规范标量算法。最终 export 经现有 SnapshotTable 解码适配恢复 NULL/decimal/ENUM/SET/binary 等类型，禁止直接把 Parquet 字符串当规范值。

首版直接有界扫描最终 Parquet，确保 export cache 命中和 shared 去重后的文件位置正确；不假定比较时 Arrow 行序就是下载行序。任务内可复用完全相同 `(records内容, before/current raw SHA+size, 比较规则绑定)` 的 locator 结果；跨操作不缓存。不改变 records 文档/内容摘要，也不把位置写入 comparison digest。

### 5.3 预算与失败

默认保持 N=1、M=24 GiB、worker envelope=32 GiB、reserve=8 GiB，不以节点 64 GiB 扩大产品预算。所有 native/Python retained metadata、哈希表、Parquet 解码、排序和 JSON 输出在操作预算中先申请后分配；批边界检查取消/deadline。新导航 JSON 上限 16 MiB、导航诊断 4 MiB，surface 继续 16 MiB；超过上限按资源错误失败，不截断产生不可达表。metadata/manifest 总限沿用 16 MiB，注释增加的实际大小计入该限。

locator 输出受既有 records 发布数量/字节上限与 M 双重约束；Parquet writer 使用现有受限 scratch/file 发布。空输出不发 artifact。索引无法在 M 中容纳时显式失败，不能不计账堆内存或把一半 locator 当完整结果。大数据实测若暴露不可接受失败，再根据明确输入改批处理策略，不提前承诺所有容量。

计时只增加现有边界 monotonic spans：presentation metadata、navigation+diagnostics、locator、surface/export、bundle；说明父子关系，不重复求和。记录新增扫描行数、产物字节与 charged high-water。纳入完整 Preview/History 运行耗时，性能值报告而非新门槛，不复活已关闭 DC74 或创建遥测持久化。

## 6. Surface 语义与 bundle 完整性（需前端核对）

B 的 `_digest.py` 把 table_refs 的 Parquet raw SHA/size 放进 surface_digest。因此仅“排除 row_locator_ref”不足以满足第一步 §4.8 的行文件重排不变性。本次 surface v4 必须同时作下面的窄调整：

SurfaceTable 新增 required `table_content_bindings`，含 before/current/browse 三个 nullable 值，与三种 table_ref 一一对应。非 null 值为：

```text
{ business_schema_digest, raw_content_digest, row_count,
  source_schema_digest, canonical_schema_digest,
  storage_rule_digest, storage_projection_version }
```

这些都是已有 owner 的规范内容/schema/规则字段，不创造另一套行哈希。不能只用 comparison digest：被排除比较的可浏览单元格仍须绑定。`source_schema_digest` 在 B 实际来自 compare_schema_digest，绑定列名/比较键而非完整类型或 DDL 序，保持该现状，不为字段名扩大其算法；`canonical_schema_digest` 绑定规范列的 SQL 类型/nullable及列序，`business_schema_digest` 绑定业务 schema 且有意忽略物理列序；DDL 展示次序另由 presentation 列数组表达。raw_content 保留重复行且无序。table_ref=null iff 对应 binding=null；同 ref 被复用时两侧绑定须相容。typed 输入由已验证物化/export 路径提供，surface 不读表重算。

v4 digest preimage 用上述 binding 取代表文件 raw SHA/size；`row_locator_ref` 整项排除。其他 records/risk/projection 的现有摘要规则保持，不顺带重构全部摘要。表文件和 locator 的 raw SHA/size 仍完整存在 ref、bundle closure 和 bundle digest 中；浏览器安装必须先校验 closure。改文件内容会改变 bundle 完整性，不能只验证 surface 就信任下载行文件。

| 变化（同一目标版本内） | 规范状态/comparison | surface | bundle |
| --- | --- | --- | --- |
| 只改 COMMENT | 不变；risk 业务结果不变 | 展示改变则变 | 变 |
| 普通表同内容仅物理重排，records/risk/navigation 字节不变 | 不变 | 不变 | 表文件/locator 变则变 |
| 只改 locator 或导航诊断 | 不变 | 不变 | 变 |
| 导航/列序/固定列改变 | 不变 | 变 | 变 |
| 新增双侧表绑定 | 不变 | 绑定集合变则变 | 变 |
| view_id 改写 | 不变 | view_id 原已排除，不因这一字段直接变 | surface 原字节变，bundle 变 |
| risk 原自由文本改稳定码 | 业务风险级别不变 | 被引用 risk raw bytes 可能传播改变 | 变 |

版本提升本身影响摘要，不能拿跨版本输出宣称上述不变。尤其 S1a 物理 ID 的历史传播结果保持为事实，本节不追改 S1a golden 或证据。

## 7. 发布、保护、版本与消费者

导航/诊断/locator 使用 S1a comparison 逻辑位置；canonical manifest 沿用 durable 位置；最终 bundle 沿用 export，scratch 由现有 operation owner 管理。具体 kind→location registry、所有 ref 枚举器、bundle binding kind、表绑定、保护移交与下载均需加入新 ref。locator kind 使用 `ROW_LOCATOR`，导航 `PROJECTION`、诊断既有 `DIAGNOSTICS`；路径统一从现有 safe path builder 生成，不插入原始用户标识符。

surface 遍历/重写必须包括 row_locator_ref，并在 operation-relative→bundle-relative 后保持语义摘要相等；locator 内只有 identity/index，无需 ref 重写。导航内 table_id 是同 pair surface 的逻辑表 ID。final tar 中引用指向唯一的实际成员或 existing shared binding，不能指回 canonical/scratch。

| Contract/组件 | 目标变更 |
| --- | --- |
| Business Navigation | 新 `backend-vnext/business-navigation/v1`，第一步规则加双侧筛选/replacement 明确形状 |
| Comparison Surface | v3→v4：pinned/display_order、locator ref、table_content_bindings、projection 输入与 digest |
| Comparison Bundle | v3→v4：ROW_LOCATOR closure kind、双侧浏览表与 final ref 绑定规则 |
| CanonicalizationManifest | 3.3.0→3.4.0：required presentation、explicit digest 白名单与 raw 完整性 |
| Table Access / Snapshot closure | 新 comment/presentation typed 字段；内部载荷 selector 同轮提升实际受影响版本，不改变 scalar/digest/storage projection version |
| Preview flow envelope/History checkpoint | 更新精确 payload decoder 和当前 Contract selector；只有实际 wire shape 受影响才提升外层版本，不盲升无关 HTTP DTO |
| Repository import/ChangeSet | 不加 COMMENT、不变 replay 行/schema；manifest version/digest 引用变化按实际 golden 更新 |

Preview pair/view 使用 baseline_to_initial、initial_to_modified；MODIFIED_ONLY 只有其实际单 pair。History 两节点 left_to_right，三节点 left_to_middle/middle_to_right。operation id 不拼进 pair_id；保证同 bundle view_id 唯一，不支持旧别名。

应修订的 owning 文档：comparison-surface、comparison-bundle、snapshot-table-access、snapshot 的 COMMENT/身份边界、Canonical Storage、ADR0019 的 metadata 解释，以及第一步 §4/§5。Table Access typed Contract 位于 `capabilities/table_access/contracts.py`，历史 parser handoff 不追改为新验收。替换过时 business-projection、table-presentation、table-presentation Contract、composite-signal-device 的 points/formulas 描述；旧离线宽度报告明确历史参考，不恢复其生成机制。FE4 kickoff 由前端设计 owner 改。

## 8. 验证 owner 与交付

每条不变量一个权威 owner；普通纯函数测试不创建 Dolt。验证集中项如下：

| 不变量 | 权威验证 |
| --- | --- |
| COMMENT 正确捕获且不污染业务 | parser conformance：转义/Unicode/空值/伪 COMMENT/上限；独立 Python oracle；同值改注释业务 digest 对照 |
| 精确历史元数据、no-op 不回写 | backend integration：同内容不同注释 Preview；NO_CANONICAL_CHANGE；业务变更后两个历史版本；PrepareImport/restart 保留 ref；损坏 frozen manifest 拒绝 |
| 五组认领/过滤/诊断/计数 | business_navigation unit/contract 共享参数表：gid/地址变化、重复地址多 gid、删装置/换 gid 后本侧孤儿行、未知计数、空页签、replacement 分侧；records 截断与 annotations 不完整分别走 TABLE_FALLBACK，不误报无变化/无风险 |
| locator 绑定正确 | row_location contract：混合标量、keyless 第三次出现、添加/删除/修改、缺侧、缓存命中/shared、跨 row group；重排后 index 改而新版本 comparison/surface 不变 |
| 闭包/完整性/生命周期 | backend bundle/operation integration：新 ref 遍历重写、混合 root 下载校验、保护后 cleanup、取消重试；不复制 S1a 全量 filesystem 故障矩阵 |
| 前后端互通 | 固定上传输入→真实后端 bundle fixture→前端 loader/摘要交叉实现；禁止手写导航伪造生产结果 |

后端 fixture 入口目标 `vnext/scripts/generate-presentation-fixtures.py --output-root <external-empty-dir>`，输出独立于 frontend 工程，供现有前端生成器调用；具体参数和输入清单随实施固定。包括普通两 pair、History 三节点、replacement、gid 变化/重复、孤儿诊断、TABLE_FALLBACK、keyless、改前公式；共享最小输入避免排列爆炸。同输入在同一版本重复生成逐字节相同；fixture harness 除 operation/repository 外也须显式固定所有 opaque artifact ID allocator 和时间等输入，并记录其 fixture-only 控制方式，不能只固定 operation ID，不能改生产身份算法。fresh 生产旅程不使用此确定性替身，也不将其 IDs 引起的差异隐去。

交付必须含 FE4 kickoff §4 全七项：正式 Contract、五类 golden、生成入口/输入、main SHA/vnext tree/exit tag/必要镜像身份、生产 OpenAPI 原件、完整稳定编码替换表、相对 FE3c `6368c9c40c` 的差异。S1a 与 BE-b 分栏，分别列 OpenAPI、logical_path 集合、manifest 字段、ArtifactRef/surface 和 regenerated fixture；不只比较 OpenAPI。

后端真实数据/最终门禁与前端正式 t1 截图各有 owner，范围见执行计划。前端核对返回前，只能称后端设计候选或后端独审通过；不能写成双方已接受、产品实现完成或 FE4b 可启动。

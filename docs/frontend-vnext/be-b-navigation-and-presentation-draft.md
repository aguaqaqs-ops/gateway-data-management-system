# BE-b 设计草案（第一步）：业务导航与表格展示

- **状态：** 第一步已确认（owner，2026-11-02，§6）；作为 BE-b 的业务与数据结构依据。§4.7 导航诊断为设计会话对 FE1 审核 D1 的答复（2026-11-02），新增编码 `DEVICE_ROWS_UNASSIGNED` 已由 owner 确认（2026-11-02）。
- **日期：** 2026-11-02。
- **范围：** [前端 kickoff](frontend-kickoff.md) FD6、FD8 与 §5 BE-b 的第一步：数据结构与业务规则。实现层面的设计（在哪个 step 计算、缓存、计时预算、golden 组织、History 侧的持久化方式）在 P6 S5 接近完成时定稿（第二步）；实现在 P6 退出后、Phase 8 前进行。
- **依据：** `legacy/backend_vnext/capabilities/{business_projection,table_presentation}/`、`legacy/backend_vnext/flows/business_projection.py`、`legacy/frontend/src/workbench/`（`legacy/` 不在 Git 中）；[Comparison Surface](../backend-vnext/contracts/comparison-surface.md)；[Composite Signal Device](../backend-vnext/capabilities/composite-signal-device.md)；[Frontend Surface Simplification](../backend-vnext/frontend-surface-simplification.md)；ADR 0018、ADR 0019。

## 1. 结论摘要

1. 缺口有两处，第二处比预期深：
   - 业务分组：legacy 的 `business_projection` 在 P5 收口时作为无使用方的占位删除（ADR 0018 第 7 项）。
   - 中文表名与列名：legacy 取自上传 SQL 的 `COMMENT`；vnext 的 Python 与 Rust 两个 SQL 解析器都丢弃注释，快照描述中没有注释字段。t1 样本（`small-1`）216 张表全部带表注释，约 2,635 个列定义带列注释。即使补回展示规则，也没有中文名称的数据来源。
2. vnext surface 已有可用的位置，不需要新的顶层结构：
   - `ComparisonSurface.projections`（`SurfaceProjectionRef`）已在 Contract、digest 与 ref 改写中实现，当前恒为空；业务导航产物挂在这里。
   - `SurfaceTable.display_name` 与 `SurfaceColumn.display_name` 已存在，当前填的是 DDL 标识符；改为填注释。
3. legacy 的列展示规则中，列序是业务规则，应保留：可核对的 40 条规则里有 20 条调整了列序，覆盖 9 类转发表、`device` 与各装置测点表（如把 `name` 提前、`dev_addr` 前移）。其余部分可以精简：列宽全部是像素值，可交给前端；没有一条规则隐藏列；固定列只有 `no`、`name`、`description` 三种取值。
4. 所有数据都在 bundle 内，前端本地按身份过滤行，不需要向后端取数（FD3）。

## 2. legacy 现状

### 2.1 业务分组

前端固定六个分组槽位；后端产出五类投影，各自落入一个槽位。

| 前端分组 | 投影 | 项（item） | 项的页签 | 数据依赖 |
| --- | --- | --- | --- | --- |
| 转发通道 | `FORWARD_CHANNELS` | `net_cfg` 中 `exe=iec104` 且 `tab_num>0` 的通道，键 `b{board}_n{link_no}`，名称取 `channel_desc` | 9 类转发表 `b{board}_n{link_no}_iec104_{syx,dyx,yc,syk,dyk,yt,ym,sc,yp}_list`，固定中文页签名（单点遥信、双点遥信、遥测等），只列存在的表；表注释为“遥测引用表”等较长名称，legacy 不使用 | `net_cfg` 两侧行 |
| 二次装置列表 | `SECONDARY_DEVICES` | ① `装置总表`（`device` 整表）；② 复合信号虚装置（`dev_addr=65532`）；③ 其余装置按 `dev_addr` 排序，名称取 `description` | 11 类测点表（`device_st` 状态类 … `device_disturb` 扰动数据按 `dev_addr`，`device_cfg` 按 `gid`）；同一张共享表按装置身份过滤行；两侧计数完整且为 0 且无变化时省略该页签 | `device` 两侧行；各测点表按身份列的两侧计数；逐行记录与风险标注按身份归属 |
| 通讯规约列表 | `COMMUNICATION_PROTOCOLS` | ① `网口配置表`（`net_cfg` 整表）；② 每个通道，名称取 `channel_desc` + `protocol_name` | 候选表 `{通道键}_{规约段}_cfg`、`{通道键}_{规约段}_dev_cfg`；规约段取 `exe` 小写，`dev103` 映射为 `nr103d` | `net_cfg` 两侧行 |
| 全局参数 | `GLOBAL_PARAMETERS` | `project`、`prot_list` 固定项；`app_cfg` 整表；`app_cfg` 每行 `table_cfg` 指向的表，名称取 `app_name` | 各一个整表页签 | `app_cfg` 两侧行 |
| 转发通道分组信息 | — | **没有任何投影产出，legacy 中恒为空** | — | — |
| 未解析表 | `UNPARSED_TABLES` | 以上未认领的其余表，名称为表名 | 整表 | 无 |

另：

- 各投影输出诊断（重复 `dev_addr`/`gid`、规约候选表缺失、`app_cfg.table_cfg` 缺失或重复等），整体有诊断时加 `PROJECTION_PARTIAL`。
- 二次装置的页签与装置带变化类型与风险汇总；其他分组的页签由前端从表级事实读取。
- legacy preview bundle 的 `sidebar_trees` 只是把全部表平铺进“转发通道”的回退形态；正式工作台使用上述投影。
- 每个 IEC104 转发通道还有一张 `b{board}_n{link_no}_sg_cfg`（表注释“定值”），legacy 不认领，落入“未解析表”。t1 `small-1`/`small-2`、t3、t4 中，含 `sg_cfg` 的通道与 IEC104 转发通道完全一致。

### 2.2 复合信号虚装置

二次装置组中的特殊项（`presentation_kind=COMPOSITE_SIGNAL`），页签只列含特殊测点的测点表。legacy 另产出两份 pair 级产物：points（各测点表两侧行与行级变化）与 formulas（两侧公式 AST，加两侧 `device` 名称映射），供前端的“合成公式”列与查看器使用。

### 2.3 表格展示

| 属性 | legacy 来源 | 实际内容 |
| --- | --- | --- |
| 表名 | DDL 表注释，缺失时对 `device`、`net_cfg`、`app_cfg`、`project`、`prot_list` 用固定中文名 | 示例：`device`→装置总表、`net_cfg`→网口配置表、`device_st`→状态类 |
| 列名 | DDL 列注释，缺失时用列标识符 | 示例：`dev_addr`→装置地址 |
| 列序 | 规则 `column_order`（43 条） | 用 t1 样本核对 40 条：20 条与 DDL 顺序相同，20 条不同，均为核心业务表：9 类 IEC104 转发表、`device`、`device_{st,mx,co,sg,sp,cnt,sn,tap}`、`fault_msg_cfg`、IEC61850 `dev_cfg`。legacy 能力文档称“保持 descriptor 原始顺序”，与规则不符 |
| 列宽、对齐 | 44 条规则加按类型的默认值；默认居中 | 全部为像素宽度 |
| 隐藏 | 规则 `hidden_fields` | 没有规则使用 |
| 固定 | 规则 `pinned_fields`（20 条） | 只有 `(no, name)` 9 条、`(name)` 8 条、`(description)` 3 条 |
| 键列 | descriptor 主键与有效比较键 | — |

## 3. vnext 现状

- `capabilities/business_projection/` 已删除；surface 的 `projections` 恒为空。
- `SnapshotTableDescriptor` 有 `display_table_name`，`SurfaceColumn` 有 `display_name`，填入的都是 DDL 标识符；Python 与 Rust SQL 解析器都把 `COMMENT` 当作可忽略的选项跳过。
- History 的快照描述来自 Repository catalog 与 Backend 持有的 `CanonicalizationManifest`（ADR 0019），两者都没有注释。
- `composite_signal_point` 是派生快照表（`ALL_CHANGES`，含 `point_payload_json`、`formula_ast_json`），作为普通表进入比较、风险与 bundle；没有 points/formulas 产物。
- `docs/backend-vnext/capabilities/business-projection.md`、`capabilities/table-presentation.md`、`contracts/table-presentation.md`、`capabilities/table-presentation-large-data-report.md` 仍是现行文档，描述的是未迁移的实现。

## 4. 目标数据结构（草案）

### 4.1 表名与列名

不新增产物，填入 surface 已有字段：

```text
SurfaceTable.display_name    = 当前侧表注释 ?? 基线侧表注释 ?? 表标识符
SurfaceColumn.display_name   = 当前侧列注释 ?? 基线侧列注释 ?? 列标识符
SurfaceColumn.pinned         新增，bool
SurfaceColumn.display_order  新增，int；业务列序
```

规则：

- 注释只用于展示：不进入 snapshot、规范状态、comparison、risk 的身份与摘要，注释变化不产生差异与风险，也不影响 `NO_CANONICAL_CHANGE`。它们进入 surface 摘要（surface 的展示负载本来就计入摘要）。
- 固定列（§6 Q4）：表中存在 `no` 时固定 `no`；存在 `name` 时固定 `name`，否则存在 `description` 时固定 `description`。
- 列序：有业务列序规则的表按规则（规则中不存在的列忽略，未列出的列按 DDL 顺序追加），其余按 DDL 顺序；以 `display_order` 表达，不改变 `columns` 的现有顺序语义。列序规则由后端随规则集版本维护，迁移 legacy 中与 DDL 顺序不同的规则。
- 列宽与对齐由前端按类型与内容计算；不提供隐藏。
- 键列沿用 surface 现有比较键信息，不重复。

### 4.2 业务导航产物

每个 pair 一份，经 `SurfaceProjectionRef` 引用（`projection_kind = BUSINESS_NAVIGATION`，一份产物含全部分组，取代 legacy 的五份），进入 bundle 闭包与 surface 摘要：

```text
BusinessNavigation:
  contract_version            backend-vnext/business-navigation/v1
  groups: [Group]             按后端给出的顺序展示，见 4.3；空组保留，前端可隐藏
                              诊断不在本产物内，见 §4.7

Group:
  group_key                   当前取值：FORWARD_CHANNELS | SECONDARY_DEVICES | COMMUNICATION_PROTOCOLS
                              | GLOBAL_PARAMETERS | OTHER_TABLES；可扩展（§4.6）
  label                       分组显示名，由后端给出
  items: [Item]

Item:
  item_key                    pair 内稳定，如 channel:b1_n2、device:addr:49、device:table、
                              device:composite、protocol:b1_n2、protocol:table、global:project、table:<表名>
  item_kind                   FORWARD_CHANNEL | DEVICE | COMPOSITE_SIGNAL_DEVICE | PROTOCOL_CHANNEL | TABLE
  label                       业务名称（通道描述、装置描述等；整表项为表的 display_name）
  attributes                  按 item_kind 的业务身份：board、link_no、protocol、dev_addr、gid
  tabs: [Tab]

Tab:
  tab_key                     item 内稳定
  label                       页签名（固定中文页签名，或表的 display_name）
  table_id                    指向 surface 中的表
  row_filter                  null | { column, value }    前端在本地按此过滤该表的行
  facts                       仅 row_filter 非空时提供：
    change_kind               UNCHANGED | ADDED | DELETED | UPDATED
    risk_level                该身份下的最高风险等级，无则为 null
    before_row_count          已知时提供
    current_row_count         已知时提供
```

规则：

- **不重复事实：** 整表页签（`row_filter = null`）不带变化与风险，前端从 surface 与 `RiskReport` 读取；只有按身份过滤的页签需要后端按身份汇总，才带 `facts`。项与分组的汇总由前端从页签计算。
- **每张表最多被一个分组认领：** 未被认领的表全部进入 `OTHER_TABLES`；被身份过滤的共享表（如 `device_st`）可出现在多个装置项下，但只认领一次。
- **页签可用性：** 沿用 legacy：两侧身份计数都已知且为 0、且没有该身份的变化时省略；计数未知时保留页签并输出诊断。
- **风险归属：** 风险标注按其行身份连接到逐行记录，再按记录两侧的身份值归属到装置；同一页签内去重，保持输入顺序。
- **数据集替换模式**（`DATASET_REPLACEMENT`）：两侧分别生成，不跨侧连接。
- **History 三节点：** 每个 pair 一份。
- **诊断：** 放在 `SurfaceProjectionRef.diagnostics_ref` 指向的独立产物中，结构与编码见 §4.7。

### 4.3 分组规则

| 分组 | 处理 | 说明 |
| --- | --- | --- |
| 转发通道 | KEEP，增加“定值”页签 | 规则同 §2.1；另见 §4.5 |
| 二次装置列表 | KEEP | 装置总表在首位，其次复合信号虚装置，再按 `dev_addr` 排序的装置 |
| 通讯规约列表 | KEEP | 网口配置表在首位 |
| 全局参数 | KEEP | — |
| 转发通道分组信息 | 暂不输出 | 后续要扩展的功能（owner 2026-11-02）；当前没有数据来源，不输出空组。按 §4.6 的扩展约定在后续版本加入 |
| 未解析表 | SIMPLIFY | 改为 `OTHER_TABLES`，界面名“其他表” |

**转发通道项的两侧判定**（设计会话 2026-11-02，沿用 legacy）：

- **转发通道条件：** `net_cfg` 中该通道行的 `exe` 为 `iec104`，且 `tab_num` 大于 0。
- **通道集合：** 取两侧 `net_cfg` 的并集，按通道键 `b{board}_n{link_no}` 对齐。
- **满足条件：** 通道在任一侧满足转发通道条件，且 surface 中至少有一张该通道的 9 类转发表或 `sg_cfg` 时，生成一个转发通道项，并认领该通道的这些表。
  - 页签是否显示（§4.5）不影响认领。
  - 项没有可显示的页签时，由后端省略该项，但它的表仍算已认领，不进入“其他表”。
- **两侧不同：** 例如基线侧满足、上传侧把 `tab_num` 改成 0，或者反过来，仍然生成项，不输出导航诊断。`net_cfg` 行的变化由比较与风险表达，导航不重复。
- **都不满足：** 通道在两侧都不满足条件（包括两侧 `net_cfg` 都没有该通道）时，不生成项，该通道的表进入“其他表”，并输出 `CHANNEL_TABLE_UNCLAIMED`（§4.7）。

### 4.4 复合信号虚装置（SIMPLIFY；Preview 基线侧补齐，owner 2026-11-02）

- 保留为二次装置组中的特殊项（`COMPOSITE_SIGNAL_DEVICE`），页签按 `dev_addr=65532` 过滤各测点表，与普通装置相同。
- 不再产出 points/formulas 两份产物，前端在本地按 `(source_table, point_gid)` 从 `composite_signal_point` 取公式（`formula_ast_json`），从同侧 `device` 表组装装置名称映射。
- `composite_signal_point` 由该特殊项认领，不进入“其他表”。
- 公式查看器的展示规则沿用 [Composite Signal Device](../backend-vnext/capabilities/composite-signal-device.md) §Frontend 中的公式展示与名称映射规则；该文档中 points/formulas 产物的描述已过时（§7）。

**各侧数据的可得性**（2026-11-02 核对；此前版本称“bundle 已含两表整表”，对 Preview 不成立，已更正）：

| 场景 | 改后侧 | 改前侧 |
| --- | --- | --- |
| History（含审核） | 节点整表 | 节点整表 |
| Preview，表未变化 | 上传侧整表 | 与上传侧相同，用上传侧整表 |
| Preview，表有变化 | 上传侧整表 | **当前 bundle 没有。** 修改行的记录只带参与比较的列：`formula_ast_json` 被排除在比较之外，只有 `formula_digest` 的前后值；删除行带基线侧的选中列 |

**BE-b 补齐（owner 2026-11-02：提交人需要在提交前看到改前公式）：**

- Preview bundle 对“双侧浏览表”在表有变化时同时闭合基线侧整表，作为该 pair 改前侧的表绑定。双侧浏览表当前为 `composite_signal_point`（改前公式）与 `device`（改前侧装置名称）。
- 只在表有变化时附带：有变化的表本来就要读基线侧做比较，不为此额外读取未变化的表，不影响结构性过滤（DC39）。
- 这会改变 Comparison Bundle 的闭包规则（[comparison-bundle.md](../backend-vnext/contracts/comparison-bundle.md) 中“Preview bundle 闭合上传侧全部表以及被删除表的基线侧数据”一条）与 bundle 摘要，随 BE-b 在 P6 退出后实现。

**名称映射：** 每一侧只用本侧的 `device` 表，`dev_addr` 唯一且装置描述非空时映射，否则显示原文 `Device N:测点`。

**BE-b 实现前的前端行为：** Preview 中公式有变化的测点只显示上传侧公式，以 `formula_digest` 前后值不同标示“公式已改”；删除的测点显示删除记录中的基线侧内容；History 完整对照。BE-b 落地后，Preview 改为与 History 相同的改前、改后对照。

### 4.5 转发通道的“定值”页签（owner 2026-11-02）

- 表 `b{board}_n{link_no}_sg_cfg` 作为同一通道转发通道项的页签，排在 9 类转发表页签之后。
- 页签名取该表注释（当前为“定值”）；注释缺失时用“定值”。9 类转发表页签沿用固定中文名，不取注释（注释为“遥测引用表”等较长名称）。
- 两侧都为 0 行时不显示该页签；任一侧有行（包括整表删除前有行）时显示。
- 只挂到转发通道项，项的生成按 §4.3 的两侧判定。所属通道在两侧都不满足转发通道条件时，表留在“其他表”，并输出诊断 `CHANNEL_TABLE_UNCLAIMED`（§4.7）。
- 由转发通道认领后，不再进入“其他表”。

### 4.6 分组的扩展约定

为“转发通道分组信息”等后续分组预留：

- `group_key` 是可扩展的取值集合。新增分组只在产物中增加一个 Group，提升 `business-navigation` Contract 的次版本号；已有分组与项的结构不变。
- 分组名与顺序都由后端给出。前端按 `groups` 列表通用渲染，不写死分组槽位或分组名；遇到未知 `group_key` 时按通用分组显示，不报错。
- 新分组认领的表从“其他表”中移出，仍满足“每张表最多被一个分组认领”。
- 前端的推导、筛选与命令层（UI 优化方向 §5.1）按 `group_key` 与 `item_key` 寻址，不依赖分组位置。

### 4.7 导航诊断（设计会话 2026-11-02，答复 FE1 审核 D1）

**位置：** 诊断不放在 `BusinessNavigation` 内，而是放进 `SurfaceProjectionRef.diagnostics_ref` 指向的独立产物。这个字段现在已经存在。

原因：按 [Comparison Surface](../backend-vnext/contracts/comparison-surface.md) 的现行规则，`surface_digest` 不含诊断。表级和根级诊断都排除在外，`SurfaceProjectionRef.diagnostics_ref` 在摘要中也置空。如果诊断写进导航产物，就会经 `projection_ref` 的完整性进入 surface 摘要，与现行规则不一致。

诊断产物属于 bundle 闭包（`bundle_assembly/_refs.py` 已闭合 `projection.diagnostics_ref`），因此进入 bundle 摘要。没有诊断时 `diagnostics_ref` 为 null，不产出该产物。

```text
BusinessNavigationDiagnostics:
  contract_version            backend-vnext/business-navigation/v1（与导航产物同一 Contract）
  diagnostics: [Diagnostic]   非空

Diagnostic:
  code                        取值见下表；大写字母、数字、下划线
  target:                     定位，四个键都必须出现，值可为 null
    group_key                 null | 分组键
    item_key                  null | 项键
    tab_key                   null | 页签键；非空时 item_key 必须非空
    table_id                  null | surface 表 id
  side                        null | BEFORE | CURRENT；只与一侧数据有关时给出
  params                      对象；键集合按 code 固定（见下表），值为 string、int、null 或 string 列表
```

**规则：**

- **文案由前端维护（C6）：** 诊断不带 `message`，前端按 `code` 映射中文文案，把 `params` 代入。
  - User 模式显示中文文案；Debug 模式显示 `code`、`target`、`side`、`params` 原值。
  - 后端不给文案，原因有两点：界面统一用中文，而后端 Contract 文本是英文；改文案不应改变产物字节和 bundle 摘要。
  - 前端维护“编码 → 文案”表，同一张表也覆盖 surface `diagnostics_summary` 中的编码。单元测试检查 v1 的全部编码都有文案，且文案的占位符与该编码的 `params` 键一致（测试 owner：view-model）。
- **不分级：** 导航诊断只表示导航不完整或不精确，不阻断提交与审核，数据仍可在 bundle 中查看。前端用提示样式展示，不使用风险色。将来需要分级时，按 §4.6 的方式提升次版本号并加字段。
- **定位：**
  - `target` 指向能定位到的最具体节点。前端在该节点（页签、项或分组）上就地提示，在分组头汇总个数；四个键全为 null 时提示显示在侧栏顶部。
  - `target` 中非空的键必须存在于同一 pair 的导航产物或 surface 中，由后端校验。
  - 表留在“其他表”时，`item_key` 为 `table:<表名>`。
- **排序与去重：** 每条诊断按 JCS 规范化；按规范化字节序排序，完全相同的条目只保留一条；产物以 JCS 编码写出。
- **未知编码：** 前端显示通用文案“导航提示（{code}）”，原值放进 Debug，不报错。新编码随 Contract 次版本号加入，与 §4.6 相同。
- **数据集替换模式：** 两侧分别生成，诊断带对应的 `side`。

**v1 编码：**

`{侧}` 按 `side` 取“改前侧”或“改后侧”，`side` 为 null 时省略。`{表}` 由前端按 `table_id` 取 surface 的 `display_name`。

| code | 产生条件 | target | side | params | 中文文案（初稿，前端可调整） | legacy |
| --- | --- | --- | --- | --- | --- | --- |
| `DEVICE_ADDRESS_DUPLICATE` | 某侧 `device` 表中 `dev_addr` 重复 | `SECONDARY_DEVICES`，`device:addr:{dev_addr}` | 有 | `dev_addr` | {侧}装置总表中装置地址 {dev_addr} 重复 | `DUPLICATE_DEVICE_ADDRESS` |
| `DEVICE_GID_DUPLICATE` | 某侧 `device` 表中 `gid` 重复 | `SECONDARY_DEVICES`，`table_id=device` | 有 | `gid` | {侧}装置总表中 gid {gid} 重复，按 gid 筛选的页签可能不准确 | `DUPLICATE_DEVICE_GID` |
| `DEVICE_TAB_COUNT_UNKNOWN` | 测点表在某侧存在，但无法按身份列统计计数；页签保留（§4.2） | `SECONDARY_DEVICES`，`table_id` | 有 | `identity_column` | {侧}{表}无法按 {identity_column} 统计行数，装置页签已保留，内容可能为空 | `SECONDARY_TAB_AVAILABILITY_UNKNOWN` |
| `DEVICE_ROWS_UNASSIGNED` | 测点表中有行的身份值在两侧装置总表中都不存在，在任何装置页签中都看不到 | `SECONDARY_DEVICES`，`table_id` | 有 | `identity_column`、`row_count`、`changed_row_count` | {侧}{表}有 {row_count} 行不属于任何装置（其中 {changed_row_count} 行有变化），可查看整表 | 无，新增（owner 2026-11-02 确认） |
| `CHANNEL_TABLE_UNCLAIMED` | 9 类转发表或 `sg_cfg` 按名称属于某个通道，但该通道在两侧都不满足转发通道条件，包括两侧 `net_cfg` 都没有该通道（§4.3） | `OTHER_TABLES`，`table:<表名>`，`table_id` | null（两侧合并判定） | `board`、`link_no` | {表}按名称属于通道 b{board}_n{link_no}，但网口配置表中没有该通道，或该通道不满足转发通道条件（规约为 IEC104 且 tab_num 大于 0），已放入“其他表” | 无（§4.5；范围扩大到 9 类转发表，legacy 中这些表直接进入“未解析表”） |
| `PROTOCOL_EXE_MISSING` | 某侧 `net_cfg` 通道的 `exe` 为空 | `COMMUNICATION_PROTOCOLS`，`protocol:b{board}_n{link_no}` | 有 | `board`、`link_no` | {侧}通道 b{board}_n{link_no} 未配置规约，无法确定规约表 | `MISSING_PROTOCOL_EXE` |
| `PROTOCOL_TABLE_NOT_FOUND` | `exe` 有值，但候选规约表都不存在 | 同上 | 有 | `board`、`link_no`、`protocol`、`expected_tables` | {侧}通道 b{board}_n{link_no} 的规约 {protocol} 没有对应的规约表（{expected_tables}） | `CANDIDATE_TABLE_NOT_FOUND` |
| `APP_TABLE_CFG_MISSING` | 某侧 `app_cfg` 行的 `table_cfg` 为空 | `GLOBAL_PARAMETERS`，`app_cfg` 整表项，`table_id=app_cfg` | 有 | `app_name` | {侧}全局参数 {app_name} 未指定参数表 | `MISSING_TABLE_CFG` |
| `APP_TABLE_CFG_DUPLICATE` | 多行 `table_cfg` 指向同一张表 | 同上 | 有 | `app_name`、`table_cfg` | {侧}全局参数 {app_name} 指向的参数表 {table_cfg} 已被其他行使用，只显示一次 | `DUPLICATE_TABLE_CFG` |
| `APP_TABLE_NOT_FOUND` | `table_cfg` 指向的表不存在 | 同上 | 有 | `app_name`、`table_cfg` | {侧}全局参数 {app_name} 指向的参数表 {table_cfg} 不存在 | `TARGET_TABLE_NOT_FOUND` |

`CHANNEL_TABLE_UNCLAIMED` 的文案不区分原因：两侧的原因可能不同，例如一侧没有该通道、另一侧 `exe` 不是 IEC104。用户可以在“通讯规约列表”的网口配置表中查看该通道两侧的 `exe` 与 `tab_num`。`exe` 为空时，同一通道还会按侧输出 `PROTOCOL_EXE_MISSING`。

`params` 的类型：`dev_addr`、`gid`、`board`、`link_no`、`row_count` 和 `changed_row_count` 为 int；`app_name` 可为 null；`expected_tables` 为 string 列表；其余为 string。

`DEVICE_ROWS_UNASSIGNED` 是新增编码（owner 2026-11-02 确认）。按 §4.2 的规则，共享测点表只能经装置页签浏览；身份值不对应任何装置的行在导航里无法到达，审核时可能漏看其中的变化。

前端在该提示上提供“查看整表”：按 `table_id` 在本地打开 `row_filter = null` 的整表视图。这不改变“每张表最多被一个分组认领”的规则。计数遵守 §5 的 DC39 约束：表未变化时只用当前侧计数，`changed_row_count` 取自该表的逐行记录。

**不保留的 legacy 编码：**

- `PROJECTION_PARTIAL`：有诊断就说明导航不完整，不需要单独的汇总标记。
- `TARGET_TABLE_FILTERED`、`CANDIDATE_TABLE_FILTERED`：vnext 的 surface 包含 pair 的全部表，不存在“表存在但不在 surface 中”的情况。
- `REPLACEMENT_PROJECTION_SIDE_FAILED`：数据异常都由上表的编码表达；组装过程的其他异常按所在步骤失败处理，不降级成诊断。第二步结合计算位置确认。
- `COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED`：这是风险 reason code，不是导航诊断。

**不作为诊断：**

- 注释缺失：回退到标识符是既定规则（§4.1）。按列提示会产生大量无用提示，Debug 模式可直接显示标识符。
- 表进入“其他表”：这是正常分组。只有按名称应该归属某组、却无法归属时（`CHANNEL_TABLE_UNCLAIMED`）才提示。

**与 surface `diagnostics_summary` 的关系：** 保持不变，不属于 BE-b 范围。两者的产出方和事实都不同：surface 记录比较与风险过程中的降级，导航诊断记录导航构造中的数据问题。导航诊断不复制进 surface 的 `diagnostics_summary`，同一事实只有一处。

两者在前端的文案层统一，共用一张“编码 → 文案”表。surface 中少数条目是自由文本而不是编码，例如风险引擎的 `max_annotations_per_pair exceeded`，以及比较失败时的异常文本。前端对这类未知字符串显示通用文案“比较提示”，原文放进 Debug。把这些自由文本收敛为编码是另一个后端清理项（kickoff §9），不阻塞前端。

**占位 fixture 示例**（前端可直接使用）：

```json
{
  "contract_version": "backend-vnext/business-navigation/v1",
  "diagnostics": [
    {"code": "CHANNEL_TABLE_UNCLAIMED", "params": {"board": 2, "link_no": 1}, "side": null,
     "target": {"group_key": "OTHER_TABLES", "item_key": "table:b2_n1_sg_cfg", "tab_key": null, "table_id": "b2_n1_sg_cfg"}},
    {"code": "DEVICE_ADDRESS_DUPLICATE", "params": {"dev_addr": 49}, "side": "CURRENT",
     "target": {"group_key": "SECONDARY_DEVICES", "item_key": "device:addr:49", "tab_key": null, "table_id": null}}
  ]
}
```

## 5. 留给第二步的约束

第二步在 P6 S5 接近完成时定稿，以下约束现在先固定：

- **整包与本地过滤（FD3）：** 导航产物与表数据都在 bundle 内；`row_filter` 只由前端在本地执行。
- **不破坏结构性过滤（DC39）：** 未变化的表两侧计数相同，只用当前侧计算，不为导航读取基线行；只有变化的表需要两侧计数。
- **线性复杂度：** 沿用 legacy 的一次性索引要求，禁止“装置 × 变化 × 标注”的交叉扫描。
- **计入计时预算：** 导航在 Preview 与 History 的组装路径上计算，其耗时计入 W1–W4、H1–H3；放在哪个 step、是否缓存在第二步决定。
- **History 的注释来源：** History 节点来自 Repository，需要为历史 commit 保存注释。候选：随 `CanonicalizationManifest` 保存展示元数据（不计入规范摘要），或写入 Dolt DDL 的 `COMMENT`。倾向前者：写入 Dolt DDL 会让只改注释的上传变成 Dolt schema 变化，与“注释不产生差异”冲突，并改变 S1a 冻结的导入包字节。第二步定稿。
- **解析器：** S2a 冻结的解析语义不在 P6 内改动；注释捕获在 BE-b 实现时同时加入 Rust 解析器与 Python 参照，并补差分用例。
- **导航诊断：** 与导航在同一遍计算中产生，不另外扫描；`DEVICE_TAB_COUNT_UNKNOWN` 的具体触发情形随计数的计算位置确定，编码与形状按 §4.7 固定。

## 6. owner 决定（2026-11-02）

| ID | 问题 | 决定 |
| --- | --- | --- |
| Q1 | 分组集合 | 保留转发通道、二次装置列表、通讯规约列表、全局参数；“转发通道分组信息”是后续要扩展的功能，当前不输出，按 §4.6 保证可扩展；“未解析表”改名“其他表” |
| Q2 | 通道的 `sg_cfg` | 作为转发通道项的“定值”页签，规则见 §4.5 |
| Q3 | 中文表名与列名的来源 | A：取自上传 SQL 的 `COMMENT`；History 侧的保存方式在第二步定稿（§5） |
| Q4 | 列展示精简 | 同意：保留后端的业务列序规则（只迁移与 DDL 顺序不同的规则）；列宽、对齐由前端计算；取消隐藏；固定列按 §4.1 的规则 |
| Q5 | 复合信号虚装置 | 同意 §4.4：保留特殊项，不再产出 points/formulas 产物，由前端在本地组装。补充（2026-11-02，FE0 审核 D1）：提交人需要在提交前看到改前公式，Preview bundle 为 `composite_signal_point`、`device` 在表有变化时补齐基线侧整表，并入 BE-b |
| Q6 | 转发通道的范围 | 同意：保留 legacy 规则（`exe=iec104` 且 `tab_num>0`） |
| Q7 | 导航诊断的结构与编码（FE1 审核 D1） | 设计会话答复（2026-11-02），见 §4.7；新增编码 `DEVICE_ROWS_UNASSIGNED` 由 owner 确认（2026-11-02） |

## 7. 后续

- §6 确认后，前端占位数据按 §4 的结构构造（kickoff §4.5）。
- 第二步定稿时，同步替换 §3 列出的四份过时文档，以及 [Composite Signal Device](../backend-vnext/capabilities/composite-signal-device.md) 中描述 points/formulas 产物的部分（§Secondary-device Projection 的产物引用、§Frontend 与 §Dataset Replacement 中对这两份产物的依赖）；修订 Comparison Surface（`projection_kind`、`SurfaceColumn.pinned`、`SurfaceColumn.display_order`；导航诊断使用已有的 `SurfaceProjectionRef.diagnostics_ref`，不改结构）与 Comparison Bundle Contract（Preview 双侧浏览表的闭包规则，§4.4）。在此之前，前端以本草案为准。

# BE-b 设计草案（第一步）：业务导航与表格展示

- **状态：** 第一步已确认（owner，2026-11-02，§6）；作为 BE-b 的业务与数据结构依据。
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
  diagnostics: [Diagnostic]

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

### 4.3 分组规则

| 分组 | 处理 | 说明 |
| --- | --- | --- |
| 转发通道 | KEEP，增加“定值”页签 | 规则同 §2.1；另见 §4.5 |
| 二次装置列表 | KEEP | 装置总表在首位，其次复合信号虚装置，再按 `dev_addr` 排序的装置 |
| 通讯规约列表 | KEEP | 网口配置表在首位 |
| 全局参数 | KEEP | — |
| 转发通道分组信息 | 暂不输出 | 后续要扩展的功能（owner 2026-11-02）；当前没有数据来源，不输出空组。按 §4.6 的扩展约定在后续版本加入 |
| 未解析表 | SIMPLIFY | 改为 `OTHER_TABLES`，界面名“其他表” |

### 4.4 复合信号虚装置（SIMPLIFY）

- 保留为二次装置组中的特殊项（`COMPOSITE_SIGNAL_DEVICE`），页签按 `dev_addr=65532` 过滤各测点表，与普通装置相同。
- 不再产出 points/formulas 两份产物：bundle 已含 `composite_signal_point` 与 `device` 的整表数据及逐行记录，前端在本地按 `(source_table, point_gid)` 关联公式，从 `device` 表组装装置名称映射。
- `composite_signal_point` 由该特殊项认领，不进入“其他表”。
- 公式查看器的展示规则沿用 [Composite Signal Device](../backend-vnext/capabilities/composite-signal-device.md) §Frontend。

### 4.5 转发通道的“定值”页签（owner 2026-11-02）

- 表 `b{board}_n{link_no}_sg_cfg` 作为同一通道转发通道项的页签，排在 9 类转发表页签之后。
- 页签名取该表注释（当前为“定值”）；注释缺失时用“定值”。9 类转发表页签沿用固定中文名，不取注释（注释为“遥测引用表”等较长名称）。
- 两侧都为 0 行时不显示该页签；任一侧有行（包括整表删除前有行）时显示。
- 只挂到已存在的转发通道项（`exe=iec104` 且 `tab_num>0`）。所属通道没有转发通道项时，留在“其他表”，并输出诊断 `CHANNEL_TABLE_UNCLAIMED`。
- 由转发通道认领后，不再进入“其他表”。

### 4.6 分组的扩展约定

为“转发通道分组信息”等后续分组预留：

- `group_key` 是可扩展的取值集合。新增分组只在产物中增加一个 Group，提升 `business-navigation` Contract 的次版本号；已有分组与项的结构不变。
- 分组名与顺序都由后端给出。前端按 `groups` 列表通用渲染，不写死分组槽位或分组名；遇到未知 `group_key` 时按通用分组显示，不报错。
- 新分组认领的表从“其他表”中移出，仍满足“每张表最多被一个分组认领”。
- 前端的推导、筛选与命令层（UI 优化方向 §5.1）按 `group_key` 与 `item_key` 寻址，不依赖分组位置。

## 5. 留给第二步的约束

第二步在 P6 S5 接近完成时定稿，以下约束现在先固定：

- **整包与本地过滤（FD3）：** 导航产物与表数据都在 bundle 内；`row_filter` 只由前端在本地执行。
- **不破坏结构性过滤（DC39）：** 未变化的表两侧计数相同，只用当前侧计算，不为导航读取基线行；只有变化的表需要两侧计数。
- **线性复杂度：** 沿用 legacy 的一次性索引要求，禁止“装置 × 变化 × 标注”的交叉扫描。
- **计入计时预算：** 导航在 Preview 与 History 的组装路径上计算，其耗时计入 W1–W4、H1–H3；放在哪个 step、是否缓存在第二步决定。
- **History 的注释来源：** History 节点来自 Repository，需要为历史 commit 保存注释。候选：随 `CanonicalizationManifest` 保存展示元数据（不计入规范摘要），或写入 Dolt DDL 的 `COMMENT`。倾向前者：写入 Dolt DDL 会让只改注释的上传变成 Dolt schema 变化，与“注释不产生差异”冲突，并改变 S1a 冻结的导入包字节。第二步定稿。
- **解析器：** S2a 冻结的解析语义不在 P6 内改动；注释捕获在 BE-b 实现时同时加入 Rust 解析器与 Python 参照，并补差分用例。

## 6. owner 决定（2026-11-02）

| ID | 问题 | 决定 |
| --- | --- | --- |
| Q1 | 分组集合 | 保留转发通道、二次装置列表、通讯规约列表、全局参数；“转发通道分组信息”是后续要扩展的功能，当前不输出，按 §4.6 保证可扩展；“未解析表”改名“其他表” |
| Q2 | 通道的 `sg_cfg` | 作为转发通道项的“定值”页签，规则见 §4.5 |
| Q3 | 中文表名与列名的来源 | A：取自上传 SQL 的 `COMMENT`；History 侧的保存方式在第二步定稿（§5） |
| Q4 | 列展示精简 | 同意：保留后端的业务列序规则（只迁移与 DDL 顺序不同的规则）；列宽、对齐由前端计算；取消隐藏；固定列按 §4.1 的规则 |
| Q5 | 复合信号虚装置 | 同意 §4.4：保留特殊项，不再产出 points/formulas 产物，由前端在本地组装 |
| Q6 | 转发通道的范围 | 同意：保留 legacy 规则（`exe=iec104` 且 `tab_num>0`） |

## 7. 后续

- §6 确认后，前端占位数据按 §4 的结构构造（kickoff §4.5）。
- 第二步定稿时，同步替换 §3 列出的四份过时文档，并修订 Comparison Surface（`projection_kind`、`SurfaceColumn.pinned`、`SurfaceColumn.display_order`）与 Comparison Bundle Contract。

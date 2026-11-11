# Composite Signal Device Capability

本文定义“复合信号虚装置”从 SourcePackage 到 Snapshot/Dolt、comparison、business projection、bundle 和前端公式查看的正式边界。

## 业务不变量

- `device` 表非空时，必须且只能存在一个同时满足 `dev_addr=65532` 与 `description="复合信号虚装置"` 的装置。
- 特殊装置测点来自 `device_st`、`device_mx`、`device_co`、`device_sg`、`device_sp`、`device_cnt`、`device_sn`、`device_tap`、`device_other`、`device_disturb`。
- 公式文件固定为可选 `/comps/logic/logics.xml`；缺失等价于合法空公式集。
- 测点按 XML 解码后的名称精确匹配公式，不 trim、不忽略大小写；测点无公式合法。
- 重复顶层公式名、重复特殊测点名、孤儿公式、特殊装置身份不满足不变量时终止 preview materialization。

## Source 与 AST

### Catalog 的过滤边界（S2b B）

catalog 可由 Rust 在 Arrow 表上验证、筛选后提供给 Python composite binder，但必须携带必填 `source_device_row_count`：它是过滤前实际读取并验证的 device 行数，表缺失/确实为空时为 0；不能用筛选结果长度推断原表为空。`devices` 可以只含命中的特殊设备，`points` 只含对应特殊地址测点；不制造 sentinel device 或兼容回退。既有 Python extractor 同样按实际读取结果填写该字段，所有内部构造方同步更新。

筛选前验证全部 device 行的 gid/dev_addr/description 类型与非 NULL（合法空 description 仍合法）；point 表先验证必需 gid/name/dev_addr 列与全部 dev_addr 类型，NULL addr 沿既有语义跳过，只有命中行再验证 gid/name 值。错误仍属于既有 catalog/materialization 诊断。

Python `_require_special_device` 只在 `source_device_row_count == 0` 时走原空表分支；原表非空时仍要求实际精确命中恰一个设备。零/多个命中的身份错误仍在原 binder 时点判定，不能为 Rust 筛选而提前到 XML/AST 校验之前。Python 继续负责 XML、AST、公式绑定及 derived rows；既有业务不变量、诊断优先级和 digest/version 不变。

### XML

XML parser 独立于 SQL parser。`SourceDocumentRef.document_kind` 支持 `XML`，文件缺失使用稳定 EMPTY source digest。

AST 节点只有三类：

```text
EXPRESS(operator, optional name, ordered children)
POINT(name)
DIGITAL(value)
```

`Logic_Set.Time` 不进入 AST 或 digest；嵌套 `Express.Name` 与子节点顺序保留。未知 `Operator_Type` 值（包括业务文件中的空字符串）原样保存，属性本身缺失仍为错误。解析器拒绝 DTD、ENTITY、未知元素、缺失必要属性、空顶层名称和非法根结构，并限制文件大小、节点数和嵌套深度。

## Snapshot 与 Dolt 表

派生表名固定为 `composite_signal_point`，主键为 `(source_table, point_gid)`：

```text
source_table          VARCHAR/TEXT NOT NULL
point_gid             BIGINT NOT NULL
dev_addr              BIGINT NOT NULL
device_gid            BIGINT NOT NULL
point_name            TEXT NOT NULL
point_payload_json    LONGTEXT NOT NULL
formula_digest        TEXT NULL
formula_ast_json      LONGTEXT NULL
```

`point_payload_json` 与 `formula_ast_json` 使用 canonical JSON。原始 `device_*` 表和行不删除、不改写。

该表使用 `ALL_CHANGES` 与显式 compare key。`point_payload_json`、`formula_ast_json`、装置归属和名称只用于展示/绑定，不参与 value comparison；公式只比较 `formula_digest`：

- catalog row 出现/消失：`ROW_ADDED` / `ROW_DELETED`；
- 相同 catalog row 的公式从无到有、有到无或内容改变：`ROW_MODIFIED`；
- 普通测点字段更新仍由原始 `device_*` comparison records 表达。

业务 Snapshot source digest 组合 SQL digest、XML digest 或 EMPTY marker、SQL/composite parser version 和 materializer version。SQL-only benchmark helper 仍保持 SQL-only 输入身份。

## Risk

`composite_signal_point` 的任意可见变化只产生一个表级：

```text
risk_level: UNKNOWN
reason_code: COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED
```

evidence 保存 added/deleted/updated/formula-updated count。UNKNOWN 正常聚合，不增加确认或阻断流程。原始 `device_*` 更新继续使用既有风险规则。

## Business Navigation 与双侧普通表

特殊装置由 [Business Navigation](../contracts/business-navigation.md) 的 COMPOSITE_SIGNAL_DEVICE item 表达。二次装置组依次为 device 总表、特殊虚装置、普通装置；原始 device 总表保留 65532 行。虚装置不依赖该物理行，不伪造 gid。

特殊项只有 `composite_signal_point` 一个整表 tab；其他共享测点按本侧 dev_addr=65532 筛选。device/composite_signal_point 有逻辑 before 时必须绑定 before_table_ref；有变化独立导出，未变可别名 current，新增无 before。名称查找使用同侧 device；点 payload、formula availability 和 AST 使用同侧 composite_signal_point。两者均通过 [Bundle](../contracts/comparison-bundle.md) 普通表 ref 及 closure 交付。没有独立 points/formulas 产物、ref 或 decoder。

## Frontend

特殊 tab 使用同侧 composite_signal_point 普通表构建只读 grid，并增加虚拟“合成公式”入口。该列按稳定字段 `point_name` 插在“测点描述”后，冻结范围覆盖 debug meta、“测点描述”和“合成公式”；普通 grid 不启用此特殊列策略。两侧都没有公式时显示“未配置”且禁用；至少一侧有公式时可打开查看器。

查看器从本地 bundle/OPFS 懒加载同侧 composite_signal_point 的 formula_ast_json 与同侧 device 名称，支持 `COMPARE`、`BEFORE`、`CURRENT`，默认 `COMPARE`。展示层将连续同类 `|`、`+`、`*` 链按原顺序压平为空间充足的逐行业务公式；空操作符单子节点直接展开，POINT/DIGITAL 只显示原值，一元操作符显示为前缀。嵌套命名表达式生成带父运算符的独立分组标题（例如 `| 名称 =`），内部操作数在下一层继续逐行完整展开，不设置条目上限、折叠或截断。公式弹窗通过滚动承载长内容，不修改 canonical AST 或 digest。

POINT 名称仅在精确匹配 `^Device ([0-9]+):(.*)$` 时使用同侧 device 的映射显示为 `装置名称:测点`；未匹配或地址未解析时保留原文。结构化展示行保存 kind、depth、基于原始 POINT 的 comparison text、名称化 display text 和稳定 alignment key。COMPARE 使用 occurrence-aware 的有序锚点对齐，两个锚点之间再按位置表达修改或单侧增删，避免中间插入信号后整段错位高亮；单纯修改 `device.description` 仍不构成公式变化，也不产生 composite risk。“测点不存在”和“测点存在但未配置公式”分别表达。不提供原始 XML、AST JSON、代数化简或引用跳转。

公式正文使用 13px 中文无衬线字体、1.6 行高和分组层级缩进；命名分组标题采用较高字重，差异行使用背景色和左侧强调边框。英文装置名称只在单词边界不足时换行，不允许任意字符间断行。

## Dataset Replacement

Dataset Replacement 继续按 before/current side 隔离生成导航与普通表。特殊装置仍独立展示，但不构造跨 side 的详细 formula UPDATE；公式查看只展示 item 所属 side。

# Composite Signal Device Capability

本文定义“复合信号虚装置”从 SourcePackage 到 Snapshot/Dolt、comparison、business projection、bundle 和前端公式查看的正式边界。

## 业务不变量

- `device` 表非空时，必须且只能存在一个同时满足 `dev_addr=65532` 与 `description="复合信号虚装置"` 的装置。
- 特殊装置测点来自 `device_st`、`device_mx`、`device_co`、`device_sg`、`device_sp`、`device_cnt`、`device_sn`、`device_tap`、`device_other`、`device_disturb`。
- 公式文件固定为可选 `/comps/logic/logics.xml`；缺失等价于合法空公式集。
- 测点按 XML 解码后的名称精确匹配公式，不 trim、不忽略大小写；测点无公式合法。
- 重复顶层公式名、重复特殊测点名、孤儿公式、特殊装置身份不满足不变量时终止 preview materialization。

## Source 与 AST

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

## Secondary-device Projection

`SECONDARY_DEVICES` 输出顺序固定为：

1. `metadata:device` 装置总表；
2. `presentation_kind=COMPOSITE_SIGNAL` 的特殊装置；
3. 排除 `dev_addr=65532` 后的普通装置。

装置总表仍保留 65532 行。特殊装置内部 tab 名称、列和顺序复用原始 point table registry，固定从状态类、测量类、控制类、定值等业务顺序筛选实际存在特殊测点的 tab；不生成空 tab。

特殊装置 item 引用两个 pair-relative artifact：

```text
composite_signal_points_ref
composite_signal_points_digest
composite_signal_formulas_ref
composite_signal_formulas_digest
```

points artifact 按 source table 保存 before/current point payload、行级 ADD/DELETE/UPDATE、changed columns 和两侧 formula availability；formulas artifact v2 按 `(source_table, point_gid)` 保存 before/current AST，并增加从两侧 `device` 表独立生成的展示名称映射：

```json
{
  "device_names": {
    "before": { "49": "#1主变本体测控PCS-9705-GA-1" },
    "current": { "49": "#1主变本体测控PCS-9705-GA-1" }
  }
}
```

映射只收录地址唯一且 `description` 非空的装置；缺失、空名称或重复地址不阻止 preview，而是省略对应映射。两类 artifact 均进入 bundle closure。formulas artifact v1 不兼容，既有本地 bundle 需要重新生成。

## Frontend

特殊 tab 使用 points artifact 构建与原始表相同的只读 grid，并增加虚拟“合成公式”入口。该列按稳定字段 `name` 插在“测点描述”后，冻结范围覆盖 debug meta、“测点描述”和“合成公式”；普通 grid 不启用此特殊列策略。两侧都没有公式时显示“未配置”且禁用；至少一侧有公式时可打开查看器。

查看器从本地 bundle/OPFS 懒加载 formulas artifact，支持 `COMPARE`、`BEFORE`、`CURRENT`，默认 `COMPARE`。展示层将连续同类 `|`、`+`、`*` 链按原顺序压平为空间充足的逐行业务公式；空操作符单子节点直接展开，POINT/DIGITAL 只显示原值，一元操作符显示为前缀。嵌套命名表达式生成带父运算符的独立分组标题（例如 `| 名称 =`），内部操作数在下一层继续逐行完整展开，不设置条目上限、折叠或截断。公式弹窗通过滚动承载长内容，不修改 canonical AST 或 digest。

POINT 名称仅在精确匹配 `^Device ([0-9]+):(.*)$` 时使用当前 side 的映射显示为 `装置名称:测点`；未匹配或地址未解析时保留原文。结构化展示行保存 kind、depth、基于原始 POINT 的 comparison text、名称化 display text 和稳定 alignment key。COMPARE 使用 occurrence-aware 的有序锚点对齐，两个锚点之间再按位置表达修改或单侧增删，避免中间插入信号后整段错位高亮；单纯修改 `device.description` 仍不构成公式变化，也不产生 composite risk。“测点不存在”和“测点存在但未配置公式”分别表达。不提供原始 XML、AST JSON、代数化简或引用跳转。

公式正文使用 13px 中文无衬线字体、1.6 行高和分组层级缩进；命名分组标题采用较高字重，差异行使用背景色和左侧强调边框。英文装置名称只在单词边界不足时换行，不允许任意字符间断行。

## Dataset Replacement

Dataset Replacement 继续按 before/current side 隔离生成 projection。特殊装置仍独立展示，但不构造跨 side 的详细 formula UPDATE；公式查看只展示 item 所属 side。

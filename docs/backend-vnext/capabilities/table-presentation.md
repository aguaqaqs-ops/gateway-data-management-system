# Table Presentation

> BE-b B0 核对：本页旧 `backend_vnext/`、analysis/宽度规则和 hidden summary 路径不代表当前 S1a 实现。BE-b resolver 的输入为独立 before/current presentation 与 descriptor，输出 SurfaceColumn 的名称/并集/present_in/pinned/display_order；显式 presentation_rules_version=1，只包含业务列序，不改 canonical/comparison ruleset digest。列宽/对齐由前端计算，无隐藏；旧离线报告仅历史参考。目标规则以 [Surface Contract](../contracts/comparison-surface.md#be-b-v4-目标b0-固定尚未激活) 和 [第二步 §4.4](../refactoring/formal/plans/be-b-second-step-design.md#44-列展示与稳定诊断) 为准，B3/B4 同实现替换旧正文，不恢复这些路径。

## Capability Boundary

实现位于 `backend_vnext/capabilities/table_presentation/`，提供 flow-neutral、无 IO 的确定性 resolver：

```text
before/current SnapshotTableDescriptor
effective diff key
versioned presentation registry
  -> TablePresentationResolver
  -> TablePresentation
```

该能力不读取旧后端模块，不修改 comparison/table rules/risk，不写 artifact，也不依赖 upload token、workspace 或 repository session。首期由 upload preview delivery 使用，history 可在需要时复用同一输出。

离线默认值生成只在 `backend_vnext/capabilities/table_presentation/analysis.py` 中进行，使用真实 `business_large` 数据集并在正式 projection 的 `unparsed_tables` 之外取样。生成结果与分析报告已检查入库，报告位置为 `docs/backend-vnext/capabilities/table-presentation-large-data-report.md`。

## Resolution Policy

规则优先级：精确表规则、正则表规则、字段类型默认值、全局默认值。精确规则未声明的属性可以继续从匹配的正则规则获取；未命中规则的列保持 descriptor 原顺序。

当前 ruleset `backend-vnext/table-presentation-rules/v2` 包含：

- 全局列宽 160、默认居中，以及 STRING/INT64/FLOAT64/DECIMAL/ENUM/DATE/DATETIME/TIME/YEAR/BOOLEAN/JSON/BINARY 类型宽度。
- `cdc_index` 的 `cdc_index`、`cdc_name` 列宽和对齐。
- 由 `business_large` 离线报告生成的 family/exact 表展示默认值，保持 descriptor 原始顺序，不隐藏或冻结任何字段。

规则中不存在于 descriptor 的列被忽略；descriptor 中未声明的列按原顺序追加。表名和字段匹配均大小写不敏感。

## Data Flow

SQL snapshot parser 将列注释单独保存为 `SnapshotTableColumn.column_comment`；`display_name` 继续表示原始 DDL 标识符，避免破坏 repository import 的混合大小写列名。Hidden snapshot summary 保存 column comment，repository-ref materialization 使用 summary descriptor 恢复它。

Formal upload 在 comparison 完成后按 pair 读取 `ComparisonTableFact.before_descriptor/current_descriptor`，生成 view/table presentation mapping，并将其作为 `UploadPreviewBundlePayloadInput` 的必需输入。Payload mapper 只验证和序列化完整展示元数据。

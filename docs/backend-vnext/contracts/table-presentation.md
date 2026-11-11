# Table Presentation Contract

> BE-b B0 核对：下文为被替代的旧设计，并非 S1a 产品已实现的能力。BE-b 目标只提供 surface 的 display_name/present_in/pinned/display_order；不实现旧 width/align/hidden、从 10 递增的序号或 preview-index 专属投影。目标语义与激活边界由 [Comparison Surface 的 BE-b v4 目标](comparison-surface.md#be-b-v4-目标b0-固定尚未激活) 拥有，B3/B4 与实现一起替换本文正文；不单独激活旧 table-presentation/v1。COMMENT 从精确 canonical manifest 取，不从 hidden summary 恢复。

本文定义表格列展示投影的正式跨模块契约。该契约只表达展示默认值，不参与 snapshot、comparison、risk 或 repository 业务身份。

## Contract

当前版本：`backend-vnext/table-presentation/v1`。

```text
TablePresentation:
  contract_version
  ruleset_version
  table_name
  columns:
    - name
      display_name
      type
      display_order
      width
      align: left | center | right
      hidden
      pinned
      primary_key
      diff_key
```

约束：

- `table_name`、`columns[].name` 使用 canonical identifier；同表列名不得重复。
- 列集合来自 raw `SnapshotTableDescriptor`，不得使用 comparison `selected_columns` 代替。ignored、before-only 或仅用于浏览的列仍可进入展示。
- current descriptor 存在时以 current 为展示主体；deleted/before-only 表回退 before descriptor。
- `display_name` 按 `column_comment > 原始 DDL 标识符 > canonical name` 解析。
- `primary_key` 来自 descriptor 的 raw `primary_key_columns`；`diff_key` 来自 comparison effective compare key，两者不得混用。
- `display_order` 从 10 开始按 10 递增；`width` 为正整数，四个 flag 必须显式输出 bool。
- Presentation metadata 不进入 compare schema、raw/business content、projection、risk 或 row-layout digest。它可以改变 preview bundle 内容与 presentation ruleset version。

## Preview Index Mapping

Upload preview delivery 必须为每个 `(view_id, table_name)` 提供一个 `TablePresentation`，并逐字段写入 `preview-index/v3 tables[].columns`。缺少 view、table 或任一必需列字段时 bundle assembly 必须失败，不得回退到 `type=unknown` 或由前端推断样式。

第一版不改变 dataset-replacement 双侧专用 grid，也不把 presentation 写入 generic `ComparisonSurface` 或 `surface_digest`。

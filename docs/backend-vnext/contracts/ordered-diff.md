# Ordered Diff Contract

本文定义 backend vNext 第一版有序表 diff contract。它补充 `comparison.md` 中普通 key-based row diff 不能表达的 position、move、interval 和 blank slot 语义。

Ordered diff 是 comparison 的扩展事实，不是前端 UI contract，也不是 Dolt native provider contract。实现设计见 `../capabilities/ordered-diff-compute.md`。

旧实现映射和 feature parity 目标见 `../contracts/ordered-diff.md`。vNext 可以优化模块边界和实现阶段，但 IEC104 ordered family 的业务规则、pseudo blank 处理和 tail/middle/move 风险语义需要完整保留。

## 范围

Ordered diff 负责表达：

- 有序表的行顺序变化。
- 中间插入、删除、尾部追加、尾部删除。
- 同一业务行的 position change / move。
- 有序区间变化。
- 空位、blank row 或 slot repair 的诊断。
- ordered records artifacts 和 ordered summary。

Ordered diff 不负责：

- 选择哪些表是有序表。
- 选择 ruleset。
- 读取 SourcePackage、RepositoryRef 或 Dolt raw diff。
- 组装 ComparisonSurface 或 WorkbenchBundle。
- 计算 risk level。
- 定义 Dolt native 加速。

## 输入模型

Ordered diff 只消费 projection-ready table data。

```text
OrderedDiffInput:
  table_name
  before_projection_table optional
  current_projection_table optional
  ordered_table_policy
  comparison_contract_version
  ordered_diff_contract_version
  scalar_encoding_version
  row_diff_detail_policy
  artifact_policy
  diagnostics optional
```

`ordered_table_policy` 由 flow 选择并冻结到 table ruleset 中：

```text
OrderedTablePolicy:
  policy_id
  policy_version
  policy_digest
  order_key
  row_identity_key optional
  stable_key_candidates optional
  value_columns
  ignored_columns
  blank_row_policy
  pseudo_key_start optional
  tail_change_policy
  move_policy
  ambiguity_policy
  table_processing_mode_policy
```

规则：

- `policy_digest` 进入 comparison digest。
- Capability 只应用 policy，不决定业务 profile。
- `order_key` 是 position/order 字段或字段组合。
- `row_identity_key` 用于识别同一业务行；没有时只能输出有限 interval/position 语义。
- `ignored_columns` 不参与 value change。
- `value_columns` 是 ordered value compare 的列集合，默认来自 projection selected columns 减 ignored columns 和 order/key columns。

IEC104 list family 默认策略沿用旧规则：

```text
table selector: ^b\d+_n\d+_<iec104_family>$
row_identity_key: gid
stable_key_candidates: [gid]
order_key: no
ignored_columns: [no]
blank_row_policy: PSEUDO_BLANK_BY_MISSING_STABLE_KEY
pseudo_key_start: 2000000000
```

规则：

- 第一批 ordered diff 仍以 IEC104 list family 为主。
- 缺失/空 `gid` 的 blank row 需要按 pseudo blank 处理，不默认降级。
- 位置字段 `no` 参与 ordered sequence，不参与 content update 判定。

## Output

Ordered diff 输出挂在 `ComparisonTableFact` 的 ordered extension 中。

```text
OrderedDiffResult:
  table_name
  status:
    ORDERED_UNCHANGED
    ORDERED_CHANGED
    ORDERED_BUSINESS_EQUIVALENT
    ORDERED_DEGRADED
  ordered_summary
  ordered_records_ref optional
  ordered_records_manifest_digest optional
  ordered_diagnostics
  ordered_table_fact_digest
```

建议 `ComparisonTableFact` extension：

```text
ordered_extension:
  ordered_diff_contract_version
  ordered_policy_digest
  before_ordered_digest optional
  current_ordered_digest optional
  stable_key_field optional
  position_field optional
  ordered_summary
  ordered_records_ref optional
  ordered_records_manifest_digest optional
  replay_guarantee
  table_processing_mode optional
  ordered_preprocess_applied optional
  diagnostics
```

`ordered_records_ref` 不进入 digest；`ordered_records_manifest_digest` 可以进入 table fact digest。
`stable_key_field` 和 `position_field` 会透传到 surface/preview index，用于 ordered records 的前端定位展示。

## Ordered Summary

```text
OrderedSummary:
  row_added_count
  row_deleted_count
  row_modified_count
  row_moved_count
  position_changed_count
  interval_inserted_count
  interval_deleted_count
  blank_changed_count
  degraded_count
```

规则：

- counts 由 ordered records 或 ordered algorithm 重新计算，不从 Dolt native/stat 直接继承。
- 普通 row add/delete/modify counts 可以同时汇总到 comparison summary，但必须在 diagnostics 中标明来自 ordered provider。
- move/position/interval counts 是 ordered extension 专属。

## Ordered Records

正式 ordered records 使用 Parquet artifact，独立于普通 `ComparisonRecord` 的内存对象，但共享 records artifact writer/closure 的基础能力。

```text
OrderedRecord:
  table_name
  record_kind:
    ORDERED_ROW_ADDED
    ORDERED_ROW_DELETED
    ORDERED_ROW_MODIFIED
    ORDERED_ROW_MOVED
    ORDERED_POSITION_CHANGED
    ORDERED_INTERVAL_INSERTED
    ORDERED_INTERVAL_DELETED
    ORDERED_BLANK_CHANGED
    ORDERED_TABLE_DEGRADED
  semantic_kind:
    DATA_INSERT
    DATA_DELETE
    MOVE
    CONTENT_UPDATE
    BLANK_INSERT_INTERVAL
    BLANK_DELETE_INTERVAL
  entity_key_kind:
    REAL_STABLE
    PSEUDO_BLANK
  row_identity optional
  before_position optional
  current_position optional
  before_values optional
  current_values optional
  interval optional
  changed_columns optional
  diagnostics optional
```

`OrderedInterval`：

```text
OrderedInterval:
  before_start optional
  before_end optional
  current_start optional
  current_end optional
  row_count
  interval_digest
```

规则：

- records 输出必须 canonical order。
- Canonical order 第一版建议为 `record_kind` priority、position tuple、row identity。
- `semantic_kind` 必须保留旧 ordered semantic kind，供 risk/surface/bundle 恢复旧行为。
- `entity_key_kind=PSEUDO_BLANK` 表示由缺失/空 stable key 派生的 blank row。
- 如果同一事件可表达为 move 或 delete+add，由 `move_policy` 决定；不能在同一 policy 下不稳定输出。
- row values 只包含 projection selected/value columns，不包含 ignored columns。

## Table Processing Mode

`table_processing_mode` 保留旧 ordered 展示和风险语义。

```text
table_processing_mode:
  ORDERED_TAIL_SEGMENT
  ORDERED_LOCAL_PATCH
  ORDERED_SHIFT_REPAIRED
  ORDERED_REORDER_COMPLEX
  DEGRADED
```

规则：

- 尾部新增/删除/blank interval 输出 `ORDERED_TAIL_SEGMENT`。
- 中间局部结构或内容变化输出 `ORDERED_LOCAL_PATCH` 或 `ORDERED_SHIFT_REPAIRED`。
- move / reorder / topology changed 输出 `ORDERED_REORDER_COMPLEX`。
- 无法可靠分类时输出 `DEGRADED`，不伪装成低风险模式。

## Replay Guarantee

```text
replay_guarantee:
  EXACT
  PARTIAL
  UNSUPPORTED
```

含义：

| Value | 说明 |
| --- | --- |
| `EXACT` | ordered records 足以复现 before -> current 的有序变化。 |
| `PARTIAL` | records 可解释主要变化，但存在 ambiguity 或降级片段。 |
| `UNSUPPORTED` | 不能可靠表达有序语义，只能要求人工检查或 fallback。 |

规则：

- 第一版默认只在 order key、row identity 和 position 都可靠时输出 `EXACT`。
- duplicate position、duplicate identity、missing order key 等情况输出 `PARTIAL` 或 `UNSUPPORTED`。
- `UNSUPPORTED` 不应伪装成普通 key-based success。

## 降级原因

Reason code 继续分层，但 P1 / P2 边界要明确区分输入问题和 planner 问题。

| Reason | 触发条件 |
| --- | --- |
| `ORDER_KEY_MISSING` | order key 任一侧不存在。 |
| `ORDER_KEY_NULL` | policy 不允许空 order key，但出现 NULL。 |
| `ORDER_KEY_DUPLICATE` | policy 要求唯一 order key，但任一侧重复。 |
| `ROW_IDENTITY_MISSING` | policy 要求 row identity，但字段不存在。 |
| `ROW_IDENTITY_DUPLICATE` | 投影后 row identity 重复。 |
| `ORDERED_AMBIGUOUS_MOVE_PLAN` | 局部证据不足，move 需要进入 P2 planner 才能稳定判定。 |
| `ORDERED_BACKBONE_NON_UNIQUE` | P2 planner 的 backbone 候选不唯一，不能安全收敛。 |
| `ORDERED_BUDGET_EXCEEDED` | P2 planner 超过 step / time / candidate 预算。 |
| `BLANK_POLICY_UNSUPPORTED` | blank row/slot repair 不满足第一版策略。 |
| `ORDERED_PROVIDER_MISSING` | ruleset 要求 ordered diff，但 provider 未启用。 |

## Digest

Current ordered diff contract version: `backend-vnext/ordered-diff/v2`.

`ordered_schema_digest` 输入：

```text
canonical table name
order_key
row_identity_key optional
value_columns
ignored_columns
ordered_diff_contract_version
ordered_policy_digest
scalar_encoding_version
```

`ordered_logical_digest` 输入：

```text
ordered_digest_contract_version
canonical table name
side
stable key field
position field
ordered_policy_digest optional
ordered_row_content_digest
```

规则：

- 与普通 `projection_logical_digest` 不同，ordered logical digest 对 row order 敏感。
- v2 ordered row content digest 不含 table name，可在同一次 comparison run 内复用。
- v2 final ordered digest 仍含 canonical table name，因此 before/current ordered digest 仍是 table-specific。
- ignored columns 不进入 ordered value digest。
- diagnostics、artifact refs、host path 不进入 digest。
- records manifest digest 可以进入 ordered table fact digest。

## 与 Comparison / Risk / Surface 的关系

Comparison：

- 实际进入 `ORDERED_TABLE_COMPARE` provider 的表输出 `ComparisonTableFact.ordered_extension`。
- 完全未变化并被 `SUMMARY_EARLY_EXIT` 短路的 ordered 表可省略 `ordered_extension`，不输出 ordered records，也不触发 ordered row-level risk。
- 如果 ordered provider 未启用，表输出 `DEGRADED` 并保留 ordered diagnostics；不再使用旧的 ordered 未启用占位状态作为表级结果。
- 第一版不把普通 key-based fallback 作为 ordered provider 的默认退路。

Risk：

- ordered provider 完成前，risk 对 ordered unsupported 输出 review-required。
- ordered provider 完成后，risk 可消费 `ordered_summary`、ordered records 和 interval/move target。

Surface / Bundle：

- Surface 只展示 ordered extension，不定义 ordered algorithm。
- Bundle 只闭合 ordered records/risk artifacts，不解释算法。

## 第一版取舍

第一版固定：

- 只支持从 `SnapshotTableReader` / projection table 读取 ordered rows。
- 不使用 Dolt native raw diff 作为 ordered algorithm。
- records format 使用 Parquet。
- 保留 IEC104 默认规则、pseudo blank preprocessing 和旧 ordered semantic kind。
- 遇到 ambiguous move、duplicate key 或复杂 blank repair 时降级。
- 不做复杂最小编辑距离全局优化，除非业务数据证明需要。

后续可能变化：

- 增加更复杂的 move/interval algorithm。
- 增加 ordered records 压缩或列式格式。
- 增加 ordered projection artifact cache。
- 增加 surface ordered navigation 和 Workbench adapter 输出文件。
- 增加 risk `ROW_INTERVAL` target 的正式规则。

## 验收标准

- tail insert/delete 可稳定输出 interval 或 row added/deleted。
- middle insert/delete 可稳定输出 interval changed。
- 同一 row identity 的 position change 可输出 move/position changed。
- value change 不被误判为 move。
- ignored columns 不触发 ordered value modified。
- duplicate position/identity 输出 degraded，不产生不稳定 records。
- 缺失/空 `gid` 的 IEC104 blank row 可按 pseudo blank 进入 interval diff。
- `table_processing_mode` 能区分 tail segment、local patch、shift repaired、complex reorder 和 degraded。
- ordered logical digest 对 row order 敏感。
- ordered records refs 可通过 artifact closure 恢复为 operation-local refs。

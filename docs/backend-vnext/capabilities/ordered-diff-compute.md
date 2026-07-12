# Ordered Diff Compute Capability

本文定义 `ORDERED_TABLE_COMPARE` provider 的第一版实现设计。Contract 见 `../contracts/ordered-diff.md`。

Ordered diff compute 是 `comparison_compute` 的一个 provider。它保持 flow-neutral：不关心 upload、submit、history compare，也不读取业务状态。

旧实现映射和 feature parity 目标见 `../contracts/ordered-diff.md`。本 capability 的主要目标是优化模块边界和可测试性，不削减 IEC104 ordered family 的业务规则。

## 设计原则

- Flow 负责选择 ordered table policy，并将其冻结在 table ruleset 中。
- Capability 只消费 projection-ready rows 和 ordered policy。
- Ordered provider 不依赖 Dolt native provider。
- Ordered provider 不直接调用 repository server。
- Ordered provider 不组装 risk、surface 或 bundle。
- 输出必须是 canonical ordered facts 和 records artifact。
- 第一版保留 IEC104 默认规则、pseudo blank 处理和旧 semantic kind。
- 第一版宁可降级，也不猜测复杂 move/slot repair；降级项必须进入 parity matrix。

## 模块落点

建议代码落点：

```text
gateway-data-management-system/backend/backend_vnext/capabilities/comparison/ordered/
  __init__.py
  provider.py
  models.py
  policy.py
  preparation.py
  classifier.py
  replay.py
  records.py
  digest.py
```

`providers/ordered_table_compare.py` 可以作为薄 provider shim：

```text
providers/ordered_table_compare.py
  -> ordered.provider
```

依赖方向：

```text
ordered_table_compare
  -> ordered.policy
  -> ordered.preparation
  -> ordered.classifier
  -> ordered.replay
  -> ordered.records
  -> ordered.digest
  -> projection
  -> artifacts.records
  -> core digest/diagnostics
```

模块职责：

| Module | 职责 |
| --- | --- |
| `ordered.policy` | IEC104 family selector、`gid/no/ignored no/pseudo blank` 默认策略、policy digest 输入。 |
| `ordered.preparation` | ordered row preparation、position 校验、`gid=0/NULL/空` 转 pseudo blank、blank signature。 |
| `ordered.classifier` | sequence compare、tail/middle/move、`table_processing_mode` 分类和 degraded reason。 |
| `ordered.replay` | semantic replay validation，决定 `EXACT` / `PARTIAL` / `UNSUPPORTED`。 |
| `ordered.records` | ordered records canonical order、manifest payload、JSONL artifact 写入。 |
| `ordered.digest` | ordered schema/logical/table fact/records digest。 |
| `risk_evaluation` 的 ordered 风险扩展 | ordered tail/middle/move/name/content/pseudo blank 风险分级。 |

拆分原则：

- 规则变化优先落在 `ordered.policy` 和后续 ordered 风险扩展。
- 算法升级优先落在 `ordered.classifier`，不影响 policy、records、replay、risk、surface/bundle contract。
- `ordered.classifier` 可以先实现 P1 简化分类，后续再增加 bounded LIS/backbone planner。

禁止依赖：

```text
flows
operations
risk_evaluation
surface_assembly
bundle_assembly
repository_server
dolt_native raw provider
旧业务模块
```

## 输入输出

```text
OrderedTableCompareInput:
  table_name
  before_reader optional
  current_reader optional
  projection_schema
  ordered_table_policy
  row_diff_detail_policy
  artifact_policy
  runtime_policy optional
```

```text
OrderedTableCompareResult:
  table_fact
  ordered_summary
  ordered_records_artifact optional
  before_ordered_digest optional
  current_ordered_digest optional
  replay_guarantee
  table_processing_mode optional
  ordered_preprocess_applied optional
  diagnostics
```

冻结约定：

- `OrderedTableCompareResult` 是 ordered provider 的 canonical table-level 输出。
- `diagnostics` 使用通用 `DiagnosticRecord` 形状，不引入独立诊断对象。
- `table_processing_mode`、`replay_guarantee` 和 `ordered_preprocess_applied` 是 v1 的稳定输出字段。
- ordered provider 的结果形状不随 planner / risk / surface 的实现细节变化。

规则：

- 新增表可以只读 current，输出 ordered row added 或 interval inserted。
- 删除表可以只读 before，输出 ordered row deleted 或 interval deleted。
- 两侧都存在时，必须先构造 projection rows，再执行 ordered algorithm。
- `row_diff_detail_policy=COUNTS_ONLY` 时可以不写 full values，但仍需稳定 counts 和 digest。

## Planner 接入

Planner 遇到 table ruleset 标记 ordered role 时：

```text
if ordered provider enabled:
  provider = ORDERED_TABLE_COMPARE
else:
  provider = DEGRADED
```

规则：

- `SNAPSHOT_TABLE_COMPARE` 不自动解释 ordered semantics。
- 第一版不把普通 key-based fallback 作为默认退路。
- Dolt native provider 第一版不处理 ordered table；ordered table 默认走 reader/projection path。

## 第一版算法

第一版使用保守 sequence compare。

IEC104 默认 policy：

```text
row_identity_key: gid
stable_key_candidates: [gid]
order_key: no
ignored_columns: [no]
blank_row_policy: PSEUDO_BLANK_BY_MISSING_STABLE_KEY
pseudo_key_start: 2000000000
move_policy: IDENTITY_POSITION_CHANGE
```

步骤：

```text
read/project before rows
read/project current rows
validate ordered policy
preprocess pseudo blank rows
build before sequence by order_key
build current sequence by order_key
build row identity index when row_identity_key exists
classify add/delete/modify/move/position change
build interval records for contiguous changes when possible
write ordered records artifact
compute ordered digests and summary
```

Validation：

- `order_key` 必须存在。
- 如果 policy 要求唯一 order key，任一侧重复则降级。
- 如果 policy 要求 row identity，任一侧缺失或重复则降级。
- ignored columns 不参与 value digest。
- blank row 按 `blank_row_policy` 处理；IEC104 默认使用 pseudo blank，不默认降级。
- position sequence 不连续、position 重复或 position 非正数时降级。

Classification：

| Case | 第一版判定 |
| --- | --- |
| identity 只在 current | `ORDERED_ROW_ADDED` |
| identity 只在 before | `ORDERED_ROW_DELETED` |
| identity 两侧存在，position 变化 | `ORDERED_ROW_MOVED` 或 `ORDERED_POSITION_CHANGED` |
| identity 两侧存在，value digest 变化 | `ORDERED_ROW_MODIFIED` |
| 连续新增 position 区间 | `ORDERED_INTERVAL_INSERTED` |
| 连续删除 position 区间 | `ORDERED_INTERVAL_DELETED` |
| 缺失/空 stable key 的 blank row 变化 | `BLANK_INSERT_INTERVAL` / `BLANK_DELETE_INTERVAL` semantic kind |
| 无法唯一匹配 | `ORDERED_TABLE_DEGRADED` |

Move policy：

```text
move_policy:
  DISABLED
  IDENTITY_POSITION_CHANGE
```

第一版建议默认 `IDENTITY_POSITION_CHANGE`，仅在 stable row identity 存在时输出 move。没有 row identity 时，不做复杂 move 推断。

Blank row policy：

```text
blank_row_policy:
  TREAT_AS_ROW
  IGNORE_BLANK_ROWS
  PSEUDO_BLANK_BY_MISSING_STABLE_KEY
  UNSUPPORTED
```

IEC104 第一版默认 `PSEUDO_BLANK_BY_MISSING_STABLE_KEY`，沿用旧 pseudo blank 处理。非 IEC104 ordered table 未显式配置时可使用 `UNSUPPORTED`，避免误把未知业务空位修复解释为安全变化。

Table processing mode：

```text
ORDERED_TAIL_SEGMENT
ORDERED_LOCAL_PATCH
ORDERED_SHIFT_REPAIRED
ORDERED_REORDER_COMPLEX
DEGRADED
```

第一版必须输出该字段。复杂 topology 无法可靠分类时输出 `DEGRADED`。

### Move 与 Topology

P1 move 定义沿用旧实现的谨慎语义：

- 仅同一 `gid` 的 position 变化，不一定是 move。
- 如果 before/current shared real rows 的相对顺序不变，只是因中间插入、删除或 blank interval 导致 position shift，则不输出 `MOVE`。
- 只有 shared real rows 的相对拓扑顺序改变，才进入 move/reorder 判断。
- P1 只要求支持简单、可唯一解释的 move；复杂 reorder、多个候选解释或超预算 topology change 输出 `DEGRADED`。
- 这里的 move 判定单位是“独立的局部 move 证据”，不要求整表只出现一个 move；如果一组 move 需要 LIS / backbone / 全局 topology 选择才能成立，就应留到 P2。

示例：

```text
before: A B C
after:  A X B C
```

`B` / `C` 的 position 变化由 middle insert 引起，不算 move，应输出 structural change，并使用 `ORDERED_SHIFT_REPAIRED`。

```text
before: A B C
after:  B A C
```

shared real rows 相对顺序改变，进入 move/reorder 语义。P1 能唯一解释时输出 `MOVE`，否则输出 `DEGRADED`。

### Middle Insert/Delete Mode

Middle insert/delete 默认使用 `ORDERED_SHIFT_REPAIRED`，而不是 `ORDERED_LOCAL_PATCH`。

理由：

- 它表达的是结构变化引发 position shift，并且可以通过 ordered semantic replay 修复。
- 风险层仍按 tail/middle 判断，middle structural change 默认高于 tail structural change。
- `ORDERED_LOCAL_PATCH` 保留给局部内容变化或不引发 position shift 的局部变更。

分类建议：

| 场景 | `table_processing_mode` |
| --- | --- |
| 只有尾部新增/删除/blank interval | `ORDERED_TAIL_SEGMENT` |
| 中间新增/删除/blank interval，shared order 不变且 replay 通过 | `ORDERED_SHIFT_REPAIRED` |
| 内容字段更新，无结构 shift | `ORDERED_LOCAL_PATCH` |
| shared real rows 相对顺序改变，且可唯一解释为 move/reorder | `ORDERED_REORDER_COMPLEX` |
| 无法唯一解释或 replay 失败 | `DEGRADED` |

### P1 / P2 Planner Boundary

P1 只接受“局部、可唯一证明”的 move 证据，不做全局 topology 选择。

P1 允许：

- 单个 row identity 的局部 move 证据。
- middle insert/delete / blank interval 导致的 position shift，但不把它们误判成 move。
- replay 通过后输出稳定 records / summary。

P1 不负责：

- block-move。
- 多候选 move 组的全局消歧。
- LIS / backbone 选择。
- 依赖全局 topology 的 blank interval synthesis。

P2 负责：

- block-move / group-move 的全局 topology planner。
- bounded LIS / backbone 选择。
- 多候选解释的唯一化。
- 预算、候选数和 topology 复杂度更高时的 planner 级降级。

建议的诊断分层：

- `ORDERED_AMBIGUOUS_MOVE_PLAN`：P1 局部证据不足，不能安全输出 move。
- `ORDERED_BACKBONE_NON_UNIQUE`：P2 planner 候选 backbone 非唯一。
- `ORDERED_BUDGET_EXCEEDED`：P2 planner 超过 step/time/candidate 预算。

P1 保留 `ordered.classifier` 作为 seam，但不应依赖完整 planner 才能完成常见 ordered slice。后续如果 benchmark 或 fixture 证明必须恢复完整 planner，只替换/扩展 P2 边界内的 planner 实现，不应影响 policy、preparation、records、replay、risk、surface 或 bundle。

## Digest

实现需要计算：

```text
ordered_schema_digest
before_ordered_digest
current_ordered_digest
ordered_table_fact_digest
ordered_records_content_digest
```

规则：

- ordered digest 对行顺序敏感。
- row value digest 使用 projection selected/value columns。
- ignored columns 不参与 value digest。
- records refs、host path、diagnostics 不进入 digest。
- records manifest digest 可进入 ordered table fact digest。

## Records Artifact

第一版复用 `artifacts.records` 基础能力，但 ordered records 使用独立 record contract version。

建议 layout：

```text
comparison/
  ordered-records/
    <table>.ordered.records.jsonl
    <table>.ordered.records.manifest.json
```

Manifest：

```text
OrderedRecordsArtifactManifest:
  table_name
  record_format: JSONL
  ordered_record_contract_version
  ordered_policy_digest
  record_count
  records_content_digest
  ordered_schema_digest
  diagnostics
```

规则：

- 写入失败必须 cleanup partial files。
- closure restore 可复用 `ComparisonRecordsClosure` 的通用 artifact closure 能力，或后续扩展 ordered records closure member。
- 第一版不要求单独 `ordered_core_cache`。

## Cache

第一版 ordered diff 不单独定义 cache。

可复用：

- `comparison_core_cache`：保存包含 ordered extension 的 canonical `ComparisonFacts + RecordsClosure`。
- `projection_table_cache`：可以直接复用 compare-ready projection artifact 命中，作为 ordered provider 的输入加速；只要命中条件仍然是 raw identity + projection contract/ruleset exact match，就不需要额外 ordered 专用 cache key。

规则：

- Cache key 必须包含 ordered policy digest / table ruleset digest。
- provider name 不默认进入 `comparison_core_cache` key。
- 如果 ordered provider 与普通 provider 输出语义不同，差异应由 ruleset/policy/options 体现，而不是 provider name。

后续可能增加：

- table-level ordered diff cache。
- ordered projection table cache。
- ordered records artifact dedup。

## 与 Dolt Native 的关系

第一版 ordered diff 与 Dolt native 分离：

- Dolt native 不解释 ordered move/interval。
- Projection/ignored columns 仍在 vNext canonicalizer 中处理。
- 即使 repository pair 可 native diff，ordered table 默认走 ordered reader/projection path。

后续只有在 Dolt native 可以稳定提供 ordered provider 所需的完整 before/current row、position 和 identity 信息时，才考虑 native 加速 ordered diff。

## 测试

Unit tests：

- IEC104 selector 默认 policy：`gid` / `no` / ignored `no`。
- order key missing/null/duplicate。
- row identity missing/duplicate。
- missing/empty `gid` -> pseudo blank。
- ignored columns 不触发 modified。
- ordered digest 对 row order 敏感。
- records canonical order 稳定。

Contract tests：

- tail insert/delete。
- middle insert/delete。
- position changed。
- move with stable identity。
- shared order unchanged with position shift is not move。
- shared order changed enters move/reorder semantics。
- value modified without move。
- pseudo blank insert/delete interval。
- added/deleted table。
- degraded table 不阻塞其他表。
- table processing mode：tail/local/shift/complex/degraded。

建议 fixture：

| Fixture | 目标 |
| --- | --- |
| `ordered_iec104_unchanged` | IEC104 默认 policy + unchanged digest。 |
| `ordered_tail_insert` | tail structural + `ORDERED_TAIL_SEGMENT` + LOW risk。 |
| `ordered_tail_delete` | tail delete + `ORDERED_TAIL_SEGMENT`。 |
| `ordered_middle_insert` | middle insert + `ORDERED_SHIFT_REPAIRED` + middle risk。 |
| `ordered_middle_delete` | middle delete + `ORDERED_SHIFT_REPAIRED`。 |
| `ordered_content_update_name_only` | `ORDERED_NAME_UPDATE`。 |
| `ordered_content_update_other_column` | `ORDERED_CONTENT_UPDATE`。 |
| `ordered_position_shift_not_move` | shared order unchanged，不输出 move。 |
| `ordered_move_simple` | simple unique move / reorder。 |
| `ordered_pseudo_blank_insert` | pseudo blank interval insert。 |
| `ordered_pseudo_blank_delete` | pseudo blank interval delete。 |
| `ordered_duplicate_gid_degraded` | duplicate real stable key 降级。 |
| `ordered_duplicate_position_degraded` | duplicate position 降级。 |
| `ordered_position_gap_degraded` | position 不连续降级。 |
| `ordered_complex_reorder_degraded` | P1 不可解释 reorder 降级。 |

Integration tests：

- SQL -> Snapshot -> ordered comparison。
- RepositoryRef -> Snapshot -> ordered comparison。
- ordered unsupported -> risk review-required -> surface degraded notice。

## 第一版取舍与后续演进

第一版固定：

- 只实现 reader/projection path。
- 不做 Dolt native ordered acceleration。
- 不做复杂最小编辑距离或完整旧 bounded LIS/backbone planner。
- 保留旧 semantic kind、pseudo blank preprocessing 和 table processing mode。
- 不实现 ordered-specific cache。
- 不直接输出前端 navigation。

后续可能变化：

- 增加更强的 interval/move algorithm，逐步关闭 `contracts/ordered-diff.md` 中的 P2 parity 项。
- 增加 bounded LIS/backbone planner 或等价复杂 reorder classifier。
- 增加 ordered records artifact closure 的专用 manifest。
- 增加 risk `ROW_INTERVAL` target。
- 增加 surface ordered extension builder。
- 增加 Workbench adapter ordered navigation。
- 基于 benchmark 决定是否引入外部执行引擎或 native acceleration。

## 验收标准

- 有序表可以直接输出 ordered facts，必要时也可以真实 `DEGRADED`。
- 常见尾部追加/删除、中间插入/删除、position change、value change 可稳定表达。
- 不稳定或歧义输入降级，不产生误导性 records。
- ordered facts 能进入 `ComparisonFacts`，risk/surface/bundle 可按 contract 消费。
- Capability 不依赖 flow、operation、repository_server 或旧业务模块。

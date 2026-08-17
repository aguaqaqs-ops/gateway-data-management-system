# Dolt Native Provider Capability

本文基于 [ADR 0003](../adr/0003-dolt-native-provider-selection.md) 定义 `DOLT_NATIVE` comparison provider 的第一版设计。它是 `history compare` 在 cache miss 时的可选加速路线，主要用于 `Dolt -> Dolt` comparison；最终输出仍必须归一化为 `ComparisonFacts + ComparisonRecordsClosure`。

Contract 见：

- `../contracts/comparison.md`
- `comparison-compute.md`
- `repository-ref-materialization.md`

验证记录已归档到 tag `docs/p2-p3-cleanup-pre-20260817` 的
`docs/backend-vnext/dolt-test/dolt-native-diff-functional-test-result-2026-06-21.md`。

## 设计结论

Dolt native provider 可以进入后续 benchmark/design，但第一版必须保持保守：

- Dolt native 是 provider，不是 comparison contract。
- 第一版只服务 `history compare` cache miss 下的 `Dolt -> Dolt` 场景。
- provider decision layer 位于 compare flow 之上，native eligibility 不挂到 `runtime_policy`。
- repository-backed comparison context 是 comparison-side context，不是 `SnapshotSourceContext` 的替代品。
- Dolt raw diff 不是 comparison core cache 的 value。
- Ignored columns、projection schema、effective key、scalar encoding、schema policy 和 records canonical order 仍由 vNext comparison core 负责。
- 普通 repository-backed eligible table 默认优先尝试 `DOLT_NATIVE`；history compare 只是第一批落点，不是唯一适用场景。
- Projection 表默认仍优先通过 `SnapshotTableReader` / readback 路径处理；Dolt native 只在能安全归一化时作为优化。
- ordered / topology-sensitive 表第一版继续走 fallback 或 readback 路径，不把复杂 reorder 语义硬塞进 native provider。
- 重复表若能在同一比较运行内共享 canonical 结果，只做运行期物理复用，不做长期业务表合并；后续 regroup 重新跑 planner 时会重新判定。
- Provider performance benchmark 应在正式 `snapshot_materialization`、`repository_ref_materialization`、`comparison_compute`、records artifact 和 cache restore 能力落地后重新编写。

## 功能测试结论

测试环境：

```text
Dolt 2.1.8
run_root: /tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt
summary_json: /tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/summary.json
```

总体结果：

```text
total: 18
passed: 11
failed: 0
unsupported: 2
fallback_required: 4
provider_neutral_core_cache_ok: 11
provider_local_only: 4
needs_design: 1
```

可作为第一版 native 候选：

- 标准主键表的 row add/delete/modify。
- 复合主键表。
- 表新增/删除。
- ignored columns 变化经过 post-filter 后 business equivalent。
- 字段长度、comment、engine、charset 等 metadata-only schema 差异经过 vNext schema policy 后 business equivalent。
- NULL、引号、逗号、UTF-8、tinyint 等标量值可映射到 vNext scalar encoding。

必须 fallback 或降级：

- 没有稳定 compare key，且 ruleset 未提供 compare key。
- Projection 后 effective key 重复。
- 主键变化；Dolt native 可能不输出可用的数据 diff。
- case-only table/column rename；Dolt 名称大小写不敏感，测试中不支持该类 rename。

需要后续业务规则决定：

- true table rename。Dolt 可以暴露 rename，但 vNext 第一版尚未定义表 rename 业务语义，默认不作为 native provider-neutral core cache 候选。

测试中还确认：

- `dolt diff --stat` 的 cell/row count 不适合作为 vNext canonical row counts，第一版只能作为 diagnostics。
- Native output order 在测试环境中稳定，但 vNext 不能依赖 raw order；records writer 必须 canonical sort 或使用 order-insensitive digest。
- 多表 pair 可以 per-table 混合 native/fallback，但只有完整 canonical pair result 才能写入 `comparison_core_cache`。

## 范围

Dolt native provider 负责：

- 判断 `history compare` cache miss 的 repository-backed input pair 是否可尝试 native diff。
- 调用 repository/Dolt 的 native diff 能力取得 raw diff。
- 把 raw diff 交给 `NativeDiffCanonicalizer`。
- 生成与 `SNAPSHOT_TABLE_COMPARE` 等价的 `ComparisonTableFact` 和 records artifact。
- 输出 provider diagnostics、fallback reason 和 timing。

不负责：

- 解析 SourcePackage 或 SQL。
- 物化 Snapshot。
- 选择业务 ruleset。
- 执行 ignored columns / projection 的业务规则选择。
- 写 Dolt repository 或创建 commit/ref。
- 生成 risk、surface 或 bundle。
- 直接写 provider-neutral `comparison_core_cache` raw value。

## 输入边界

`ComparisonInput` 仍固定以 Snapshot 为输入。`SnapshotSourceContext` 继续只负责 snapshot provenance，不承载 native eligibility。

`DOLT_NATIVE` 使用单独的 comparison-side repository-backed context；它是 compare planning 的附加上下文，而不是 snapshot provenance 的默认替代。

建议 optional context：

```text
RepositoryBackedComparisonContext:
  repository_id
  resolved_commit_hash
  repository_server_contract_version
  dolt_version
  native_diff_access_ref
  diagnostics optional
```

规则：

- 缺少该 context 时，`DOLT_NATIVE` 不可选。
- context 只能用于 provider 优化和 diagnostics，不替代 `SnapshotSummary`。
- 表清单仍来自 `ComparisonInput.summary`。
- comparison digest 仍由 Snapshot digest、ruleset、contract version 和 canonical facts 决定。
- repository_server 不产出 `ComparisonFacts`；它只提供 repository-local native diff/read access。

## Eligibility

Pair 级条件：

| 条件 | 第一版要求 |
| --- | --- |
| 输入来源 | before/current 都是 repository-backed Snapshot。 |
| repository | 同一个 `repository_id`。 |
| ref | 两侧都解析为 immutable commit hash。 |
| Dolt 能力 | 当前 Dolt 版本通过功能测试矩阵。 |
| 表清单 | 可从 `SnapshotSummary` 对齐。 |

表级条件：

| 条件 | 第一版要求 |
| --- | --- |
| 表类型 | 普通表或表新增/删除。 |
| ordered table | 不走 native，交给 `ORDERED_TABLE_COMPARE` 或 unsupported fallback。 |
| projection | native raw diff 必须能被 projection/canonicalizer 完整处理。 |
| effective key | key 存在、未被忽略、投影后不重复。 |
| key change | 主键或 effective key 改变时默认 fallback/degraded。 |
| schema policy | schema 差异可按 vNext schema policy 归一化。 |
| rename | true rename 和 case-only rename 第一版不作为 provider-neutral cache 候选。 |

可选放宽：

- 如果 Dolt raw diff 可以提供完整 before/current row，且 ruleset 提供稳定 compare key，即使 Dolt 原表无主键，也可以通过 canonicalizer 将 raw add/delete 配对为 modified。
- 该放宽必须先验证 duplicate effective key；失败时 fallback。

## Canonicalization

执行链路：

```text
DoltNativeRawDiff
  -> NativeDiffCanonicalizer
  -> ProjectionSchema
  -> ComparisonRecord JSONL
  -> ComparisonTableFact
```

`NativeDiffCanonicalizer` 负责：

- canonicalize table/column name。
- 按 vNext `ProjectionSchema` 过滤 ignored columns。
- 应用字段交集和 schema policy。
- 使用 `scalar_encoding` 归一化标量值。
- 构造 effective row identity。
- 检查 missing/ignored/duplicate key。
- 把 provider raw add/delete/modify 映射为 `ROW_ADDED` / `ROW_DELETED` / `ROW_MODIFIED`。
- 重新计算 row counts、records count 和 projection logical digest。
- 按 canonical order 写 records。

禁止：

- 使用 Dolt `--stat` 作为 canonical counts。
- 把 Dolt raw schema diff 直接等同于 vNext schema change。
- 把 raw diff output path、raw order 或 provider chunk 信息写入 digest。

## Provider Planning

history compare planner 建议生成表级 decision：

```text
ProviderDecision:
  table_name
  provider: DOLT_NATIVE | SNAPSHOT_TABLE_COMPARE | ORDERED_TABLE_COMPARE | SUMMARY_EARLY_EXIT | DEGRADED
  eligibility
  fallback_provider optional
  reason
  diagnostics
```

冻结约定：

- `ProviderDecision` 是 native planner 的 canonical table-level 决策形状。
- `diagnostics` 使用通用 `DiagnosticRecord` 形状，不引入 provider 专属诊断对象。
- `reason` 是 v1 稳定字符串桶；具体桶值由 phase 0 冻结，不在实现阶段临时增删或重命名。
- 决策形状不依赖 native raw diff 的物理输出格式。

规则：

- `DOLT_NATIVE` 只在 `history compare` cache miss 且 pair 满足 repository-backed eligibility 时进入 planning。
- Planner 可以在同一个 pair 中混合 native 与 fallback。
- mixed pair 中，native table 的 raw output 不单独写入 provider-neutral core cache。
- 只有所有表都产生完整 canonical facts/records 后，pair-level `comparison_core_cache` 才能写入；它写入的是 core cache，不是 pair-total delivery cache。
- 如果某表 native canonicalization 失败，应按表 fallback；如果 fallback 也失败，该表降级，不阻塞其他表。

## Cache

Provider-neutral cache 规则：

- `comparison_core_cache` key 默认不包含 provider name。
- `comparison_core_cache` value 必须是 canonical `ComparisonFacts + ComparisonRecordsClosure`。
- SQL path、Snapshot path、Dolt native path 只有在 canonical facts/records 等价时才能共享命中。
- provider raw diff 如需缓存，应单独命名为 provider-local cache，例如 `dolt_native_raw_diff_cache`，第一版不实现。

第一版写入条件：

- 所有表输出 canonical table facts。
- records artifacts 已通过 manifest/content digest 校验。
- row counts、degraded reason、schema diagnostics、scalar encoding 与 `SNAPSHOT_TABLE_COMPARE` 语义一致。
- records order 已 canonicalized。

禁止写入 provider-neutral core cache：

- 只拥有 Dolt raw diff，未归一化。
- 只完成部分表，pair result 不完整。
- native 与 snapshot 路径在 schema policy、row identity 或 counts 上不能对齐。
- 表 rename 语义未决。

## 第一版取舍

第一版实现时可以先不做：

- native raw diff cache。
- provider-local export cache。
- Dolt native 的性能 ranking。
- ordered semantic diff。
- true table rename semantic。
- case-only rename handling。
- Dolt native 对 projection table artifact 的直接消费。

第一版必须做：

- native eligibility diagnostics。
- fallback reason。
- canonicalizer 单元测试。
- 与 `SNAPSHOT_TABLE_COMPARE` 的 canonical result 对照测试。
- 禁用 `dolt diff --stat` 作为 canonical count。

## Benchmark 计划

Dolt native 性能 benchmark 需要独立 runner。正式 benchmark 应在以下能力落地后编写：

- `repository_ref_materialization`
- `comparison_compute`
- `DOLT_NATIVE` provider
- `NativeDiffCanonicalizer`
- records artifact / closure
- `comparison_core_cache` lookup/restore/write

## 验收标准

- 功能测试矩阵中的 provider-neutral cases 可由 native provider 输出与 snapshot compare 等价的 `ComparisonFacts`。
- ignored columns 变化可归一化为 business equivalent。
- schema metadata-only 变化按 vNext schema policy 归一化。
- duplicate effective key、no key、PK change、case-only rename 均不会误写 provider-neutral core cache。
- `dolt diff --stat` 只进入 diagnostics。
- records manifest digest 在不同 provider 输出顺序下保持稳定。
- mixed pair 能正确标记 table-level provider/fallback，并只在完整 canonical pair result 后写 cache。

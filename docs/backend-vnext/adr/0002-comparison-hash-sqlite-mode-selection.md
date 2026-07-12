# ADR 0002: Comparison Hash / SQLite Mode Selection

## 状态

Accepted

## 背景

`SNAPSHOT_TABLE_COMPARE` 需要在两个内部执行模式之间切换：

- `HASH_STREAM_COMPARE`: 先构建 before 侧内存字典，再流式匹配 current 侧，作为默认快路径。
- `SQLITE_SPOOL_COMPARE`: 把投影结果落到临时 SQLite，再借助索引和 join/lookup 生成 diff，作为受控落盘路径。

这两个模式必须输出同一组 canonical `ComparisonFacts`、`ComparisonSummary` 和 records contract。模式选择属于运行时资源策略，不属于 comparison 语义本身，也不应影响 digest 或 cache key。

benchmark 阶段需要可重复、可解释的切换准则，不能依赖模糊的“看起来像大表”的人工判断。

## 决策

1. `runtime_policy.preferred_internal_mode` 保留为显式覆盖入口。
2. `AUTO` 按下面顺序决策：
   - 如果 caller 明确指定 `HASH_STREAM_COMPARE` 或 `SQLITE_SPOOL_COMPARE`，直接遵从。
   - 如果提供了 `memory_budget_bytes`，先估算 `projected_payload_bytes`。
     - `projected_payload_bytes <= 0.75 * memory_budget_bytes` 时，使用 `HASH_STREAM_COMPARE`。
     - `projected_payload_bytes >= 1.0 * memory_budget_bytes` 时，使用 `SQLITE_SPOOL_COMPARE`。
     - 介于两者之间时，仍默认 `HASH_STREAM_COMPARE`，并记录灰区诊断。
   - 如果没有 `memory_budget_bytes`，默认保持 `HASH_STREAM_COMPARE`。
     - 只有当 `projected_payload_bytes` 明显超过一个实现默认 spill floor 时，才切到 `SQLITE_SPOOL_COMPARE`。
     - 第一版 benchmark 默认 spill floor 取 `64 MiB`，后续可通过 benchmark 结果下调或上调，但不进入 contract。
3. `row_count` 只作为 fallback 输入，前提是 projected payload 无法从 projection schema 和 reader metadata 得到可信估算。
4. 估算器可以迭代，但决策输入的优先级必须保持稳定：
   - 显式 override
   - budget-aware estimate
   - `row_count` fallback
5. 选中的 mode、spill reason、估算值必须进入 diagnostics，但不能改变 `ComparisonFacts`、`ComparisonDigest`、`ComparisonCoreCacheKey` 或 records contract。

## Benchmark 口径

- `business_small_cut` 和 `business_small` 主要用来验证 hash baseline 和固定行为。
- `business_medium` 和 `business_large` 应尽量同时跑 forced hash 与 forced SQLite，用来测 crossover，而不是只测单一自动路径。
- `AUTO` 的 benchmark 结果只在 forced hash 与 forced SQLite 的 canonical facts 和 records contract 一致时才可接受。
- 如果 benchmark 表明 SQLite 在某一数据带已经明显优于 hash，而当前 spill floor 仍然过高，应先下调实现默认值，再重新跑矩阵，不要改 comparison 语义。

## 后果

正向：

- hash 保持默认快路径，便于小中型数据集的吞吐优化。
- SQLite 作为受控 spill 路径，能明确承载高 payload 或显式落盘需求。
- benchmark 结果可复现，因为 mode 选择和诊断口径稳定。

代价：

- 需要维护一个明确的估算器和诊断字段。
- benchmark 需要覆盖 forced hash / forced SQLite 两条控制路径，不能只依赖 AUTO。

## 验证

- 同一 fixture 在 forced hash 和 forced SQLite 下必须产出相同的 canonical facts、summary 和 records digest。
- diagnostics 必须包含 mode、reason 和 payload estimate。
- 任何阈值调整都要先更新这份 ADR，再把值用于 benchmark 默认配置。

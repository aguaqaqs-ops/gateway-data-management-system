# ADR 0003: DOLT_NATIVE Provider Selection 与历史比较加速

## 状态

Proposed

## 背景

随着 comparison core、snapshot materialization、repository_ref materialization 和 cache 逐步成型，Dolt native diff 可以作为一条可选加速路线，但它不应和 vNext 的 comparison contract、snapshot provenance、records contract 混为一体。

当前已经达成的共识是：

- `DOLT_NATIVE` 的首个验证/落地路径是 `history compare` cache miss 的回退加速，但 provider 语义本身面向 `Dolt -> Dolt` comparison pair，不局限于 `history compare`。
- 该 provider 的比较方向是 `Dolt -> Dolt`，不是通用 snapshot-to-anything 路径。
- provider 决策应位于 compare 流程之上，保持薄层；`runtime_policy` 不承担正式的 native eligibility 载体职责。
- snapshot provenance 继续由 `SnapshotSourceContext` 负责；native eligibility 通过独立的 comparison-side repository-backed context 传递。

## 决策

1. `DOLT_NATIVE` 作为可选优化 provider 存在，不引入新的 comparison contract。
2. 初始验证先从 `history compare` cache miss 下的 `Dolt -> Dolt` comparison 开始；只要 pair 满足 repository-backed eligibility，后续也可以在其他 flow 复用同一 provider 语义。
3. provider decision layer 位于 compare flow 之上，负责判断是否尝试 native、失败如何 fallback，以及 diagnostics；native eligibility 不内嵌到 snapshot provenance。
4. `RepositoryBackedComparisonContext` 作为 comparison-side context 使用，`SnapshotSourceContext` 继续只表示 snapshot provenance。
5. `DOLT_NATIVE` 的输出必须归一化为 `ComparisonFacts + ComparisonRecordsClosure`；raw diff 不是 core cache value，也不是 cache key。
6. 第一版先不覆盖 ordered table native path、case-only rename 和 true rename semantic；这些仍按 fallback / degraded 处理。
7. `ProviderDecision` 维持表级决策形状，便于 history compare planner 在同一 pair 内混合 native 与 fallback。
8. `comparison_core_cache` 仅接受 canonical 结果；native pair 的 raw 产物如果要缓存，必须是独立 provider-local cache，第一版不做。
9. 对于 ordinary repository-backed eligible table，pair 一旦满足 native 条件，默认优先尝试 `DOLT_NATIVE`；history compare 只是首个落点，不限定该语义只在 history compare 生效。
10. 重复表的物理复用只作用于当前比较运行中的 canonical materialization，不是长期业务表合并；后续 regroup / 重新提交时会重新评估，不会沿用上一轮的“已合并”状态。

## 后果

正向：

- history compare 的 cache miss 路径有了明确的可选加速点。
- provider 决策层与 snapshot provenance 解耦，后续扩展其他 repository-backed 优化时边界更清晰。
- canonical result 仍然保持唯一入口，避免 raw diff 污染 core cache。

代价：

- 需要维护一条独立的 native eligibility / fallback 语义链。
- 第一版必须接受 ordered、rename 和部分 schema 语义继续走 fallback，而不是尝试一次性覆盖全部 native 场景。

## 验证

- history compare cache miss 场景下，只有满足 repository-backed eligibility 的 pair 才进入 native planner。
- 同一 fixture 在 native path 和 snapshot path 下必须产出一致的 canonical facts、records 和 digest。
- 任何 fallback 都必须在 diagnostics 中明确可见，不能静默进入 core cache。

# Cache Contract Cleanup Execution Plan

本文收口 backend vNext cache contract 化的短期执行计划。它不是新的长期 contract，而是把下一轮大改动拆成可 review、可回归的步骤，避免 cache 边界整理和 registry/cleanup 等后续议题混在一起。

## 背景

当前 cache 已经承担正式语义，但实现边界仍偏临时：

- `cache.comparison_core` 直接依赖 comparison capability runtime model，并用 pickle 持久化 `ComparisonCoreCacheEntry`。
- `cache.projection_table` 直接依赖 `ProjectionSchema`、`ProjectionTable`、`ProjectionRowsReader` 和 `SnapshotTableColumn`。
- comparison engine 通过 cache protocol 接入 projection cache，同时 cache 又 import comparison model，形成较强的双向认知。
- docs 已要求 cache-local refs 命中后恢复为 operation-local refs，但代码中的 cache value / artifact closure 边界还不够显式。
- `PROVISIONAL`、`CONTENT_VERIFIED`、`COMMIT_VALIDATED` 等可信等级已有设计描述，但代码层还没有统一 contract。

## 本轮目标

- 先 contract 化 cache key/value 边界，不改变 benchmark/worktree/target-branch 语义。
- 保留现有 comparison core cache 与 projection table cache 的命中行为、diagnostic code 和 benchmark 统计口径。
- 将 cache 的长期公共形状从 capability runtime class 中抽出来，后续再处理 registry、TTL、cleanup、跨进程锁和远端 cache。

## 执行阶段

### 1. 定义 cache contract v1

新增 cache contract DTO 和枚举，正式落点固定为 `backend_vnext/contracts/cache.py`。

最小内容：

- `CacheValidationStatus`
- `CacheLookupPolicy`
- `ComparisonCoreCacheKeyPayload`
- `ComparisonCoreCacheEntryPayload`
- `ProjectionTableCacheKeyPayload`
- `ProjectionSchemaPayload`
- `ProjectionTableColumnPayload`
- `ProjectionTableCacheEntryManifest`

约束：

- contract DTO 只依赖 `core`、`artifacts` 和标准库。
- 不 import comparison/snapshot capability runtime model。
- payload 必须可 JSON 序列化并可稳定 digest。

### 2. 收口 comparison core cache

- 保留现有 public cache protocol 名称和调用方行为。
- `ComparisonCoreCacheKey` 内部可以继续提供 Python convenience API，但 digest payload 应委托给 contract DTO。
- filesystem cache 的 manifest metadata 和 key/value digest 先走 contract payload；`entry.pkl` 保留为临时 runtime serialization。
- `entry.pkl` 的删除条件是 `ComparisonFacts`、records closure、records artifact refs 可以无损 JSON roundtrip，并且 cache hit 后能稳定恢复当前 operation-local records refs。
- cache entry 的长期正式内容应表达 canonical `ComparisonFacts` payload、records closure ref/payload 和 records artifact refs，而不是 provider raw output。
- cache hit 后仍必须能恢复为当前 operation 可消费的 records closure；不把 cache-local path 暴露给 flow/surface/bundle contract。

### 3. 收口 projection table cache

- 保留 `manifest.json + rows.parquet` 的物理形态。
- manifest 改为 contract payload，至少包含：
  - source raw content digest
  - projection schema digest
  - projection/scalar versions
  - selected columns / column metadata
  - row count
  - rows content digest
- cache 实现不应要求外部理解 `ProjectionTable` / `ProjectionRowsReader` 的内部结构。
- 本轮仍由 cache 实现把 `manifest.json + rows.parquet` materialize 回当前 runtime 使用的 `ProjectionTable`；后续若引入 adapter，可再把 runtime 重建逻辑移到 comparison 边界。

### 4. 补齐 trust / promotion 字段

- 先把 status enum 和字段落到 contract，不急着扩大策略。
- preview/cache warmup 写入可以继续沿用当前行为，但语义上标记为 provisional。
- submit finalize rekey/promotion 是写入 canonical repository-backed key 的权威点。
- history compare 后续默认应只读 commit-validated cache；本轮不改变读取策略，只保留 `validation_status` 字段和测试锚点，避免改变 benchmark 命中语义。

### 5. 读取策略、promotion 不降级和 comparison-core registry

第一轮 contract 化后，comparison core cache 进一步收口为以下规则：

- `COMMIT_VALIDATED` 表示 cache key 已绑定到 canonical commit identity，不替代 repository import validation policy，也不表达业务数据必然正确。
- `CacheLookupPolicy.READ_ANY` 是默认兼容策略，preview/upload 继续使用它读取和写入 `PROVISIONAL`。
- `CacheLookupPolicy.READ_COMMIT_VALIDATED_ONLY` 用于 repository-backed history compare；已有 provisional entry 会按 `VALIDATION_STATUS_POLICY_MISS` 处理，允许 flow 重算并写入 commit-validated entry。
- validation status 是单调等级：`PROVISIONAL < CONTENT_VERIFIED < COMMIT_VALIDATED`。同 key 同内容只能升级或保持，普通写入不得降级；同 key 不同内容仍按 cache conflict 处理。
- submit finalize promotion 通过 rekey 写入 `COMMIT_VALIDATED`，provenance 为 `SUBMIT_FINALIZE_PROMOTION`。
- history compare 在 commit-only 策略下完成重算时，若 before/current 都具备 repository-backed resolved commit identity，则写入 `COMMIT_VALIDATED`，provenance 为 `HISTORY_COMPARE_COMPUTE`。
- `comparison-core-cache/registry.json` 是可重建索引，记录 cache key、entry content digest、validation status、provenance 和可选 source key；manifest 与 entry 文件仍是权威真相源。
- registry 缺失或损坏不应导致 cache miss；lookup/write 可从 manifest 修复 registry。
- `clear()` 是显式 reset，允许 benchmark cold / warm-partial 删除已有 commit-validated entry；reset 后重新计算的 canonical history compare entry 仍应写回 `COMMIT_VALIDATED`。

## 暂不处理

- cache registry 总线化。
- TTL、pin、eviction、quota、cleanup。
- 跨进程锁、并发 writer 协调。
- 远端 cache / object storage。
- table-level comparison facts cache。
- risk/surface/bundle cache。
- repository_server table cache cleanup 或 export artifact cache。
- projection table cache registry。

## 暂停条件

遇到以下情况先暂停讨论，不继续扩大实现：

- comparison core cache 的 JSON payload 无法无损表达当前 `ComparisonFacts` / records closure。
- projection table cache manifest 无法稳定重建当前 `ProjectionTable`，或会改变 projection digest/row ordering。
- 去 pickle 会破坏现有 benchmark cache hit/rekey 语义，且无法通过双读或一次性迁移平滑处理。
- 移动 projection runtime adapter 会牵动 comparison engine 调用面或改变 projection digest/row ordering。
- trust status 引入后 preview、submit finalize、history compare 的读取策略出现冲突。
- 需要新增 registry、TTL、cleanup 或跨进程锁才能保持测试通过。

## 回归测试

每个阶段至少跑：

```bash
.venv/bin/python -m compileall -q backend_vnext
.venv/bin/pytest tests/backend_vnext/unit/test_comparison_projection_table_cache.py tests/backend_vnext/unit/test_comparison_risk_flow.py -q
.venv/bin/pytest tests/backend_vnext/unit/test_upload_preview_flow.py tests/backend_vnext/unit/test_history_compare_flow.py -q
.venv/bin/pytest tests/backend_vnext/unit/test_workflow_ladder_benchmark.py tests/backend_vnext/unit/test_flow_journey_benchmark.py -q
.venv/bin/pytest tests/backend_vnext/integration/test_repository_import_provider_runner.py -q
```

阶段完成后跑完整 vNext unit：

```bash
.venv/bin/pytest tests/backend_vnext/unit -q
```

## 完成标准

- cache contract DTO 不依赖 capability runtime model。
- comparison core cache 和 projection table cache 的 key/value digest 与现有测试预期保持稳定，或变更有明确测试和文档说明。
- benchmark cache hit/miss/rekey 统计不发生非预期变化。
- docs 中 cache 边界与代码落点一致，后续 registry/cleanup 议题仍保持独立。

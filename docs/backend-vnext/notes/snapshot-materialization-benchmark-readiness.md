# Snapshot Materialization Benchmark Readiness Memo

本文记录 `snapshot_materialization` 相关的 benchmark readiness 判断，并给出当前这批外部业务数据是否已经具备测试条件的结论。它不是 contract，也不是临时草案；它的定位是可复用的阶段性决策备忘录。

## 结论

当前这批业务数据已经具备 benchmark 测试条件。

理由是：

- 数据目录结构与 `repository-import-benchmark-runbook.md` 的推荐结构一致。
- 四个规模层级都已就位：`business_small_cut`、`business_small`、`business_medium`、`business_large`。
- 每个规模目录都包含默认入口 `dbcfg.sql`。
- 每个规模目录下还有对应的业务子目录和 `.pmc` 文件，说明不是只有空壳目录。
- 文件体量已经拉开层级，足以支撑 smoke、baseline 和 large-data 对比。

但需要区分两件事：

- “具备 benchmark 测试条件”。
- “已经足以决定默认并行策略”。

前者现在是成立的，后者还需要实际跑数。

当前这份基线已经切到默认 `table_rule_registry`，因此表计数和耗时都反映了新规则集下的默认行为，而不是全表无差别 materialization。

## 已核对的数据形态

当前外部数据根位于：

```text
/home/issac/test-dir/business-benchmark-data/
```

观察到的目录结构：

```text
business_small_cut/dbcfg.sql
business_small/dbcfg.sql
business_medium/dbcfg.sql
business_large/dbcfg.sql
```

每个目录下面还有一个对应规模的业务子目录，例如：

```text
business_small_cut/small_cut/
business_small/small/
business_medium/medium/
business_large/large/
```

并且每个子目录下都有至少一个 `.pmc` 文件作为业务样本。

当前磁盘体量大致为：

```text
business_small_cut  7.9M
business_small     78M
business_medium   274M
business_large    380M
```

这组规模对比已经足够支撑以下问题的实测：

- 单包串行处理的基线时间。
- 双包串行处理的总耗时。
- 双包按 dataset 维度并行处理的潜在收益。
- large 数据下的时间和内存放大趋势。

## 为什么说现在可以测

从当前文档契约看，benchmark 只要求：

- 数据根在仓库外。
- 每个 dataset 目录能被识别。
- 默认入口文件是 `dbcfg.sql`，或通过 `dataset.yaml` 显式指定。
- 需要的话可以记录 `validation_tables`。

这些条件当前都已满足到足够开始跑的程度。

另外，`dataset.yaml` 这里不是硬要求，因为当前目录名和文件名已经满足默认约定。后续如果想显式记录验证表、脱敏说明或额外元数据，再补 `dataset.yaml` 就行。

## 已执行基线

我已经用新增的测试入口跑过一轮单次 wall-clock materialization 基线，测试代码位于：

```text
gateway-data-management-system/backend/tests/backend_vnext/integration/test_snapshot_materialization_business_benchmark.py
```

本轮基线使用的是：

- `materialize_sql_file(...)`
- 单次顺序处理
- 不做并行拆分
- 不设置额外性能阈值

实测结果如下：

| Dataset | Elapsed | Table Count | Row Count Total |
| --- | ---: | ---: | ---: |
| `business_small_cut` | `706 ms` | `124` | `3,727` |
| `business_small` | `10,648 ms` | `208` | `73,648` |
| `business_medium` | `29,949 ms` | `191` | `122,251` |
| `business_large` | `49,132 ms` | `311` | `246,359` |

这说明：

- 现在的数据根确实可以支撑 benchmark。
- `business_large` 已经足够大到需要把性能观察单独拿出来看。
- 仅靠“可以跑通”还不足以决定默认并行策略，后续仍然应该比较串行与 dataset 级并行。
- 默认规则注册表会跳过 8 个 `SKIP` 表，所以当前 table_count 和 row_count_total 比先前无规则版本更低。

### `business_large` 分阶段拆分

我又把 `business_large` 进一步拆成更细的阶段。这里的 `reader_init` 已包含 in-memory reader 的内容指纹校验，所以它会体现出一部分 digest 成本。

结果如下：

| Phase | Elapsed |
| --- | ---: |
| `resolve_sql_dump_source` | `963 ms` |
| `parse_mysql_dump` | `20,441 ms` |
| `table_decision` | `4 ms` |
| `raw_content_digest` | `11,930 ms` |
| `schema_digest` | `15 ms` |
| `descriptor_init` | `10 ms` |
| `reader_init` | `11,735 ms` |
| `table_wrap` | `1 ms` |
| `source_context` | `0 ms` |
| `state_digests` | `1 ms` |
| `summary_snapshot_assembly` | `0 ms` |
| `total` | `45,103 ms` |

对应计数：

- `parsed_tables` = `319`
- `materialized_tables` = `311`
- `skipped_by_rule` = `8`

这个拆分说明：

- `parse_mysql_dump` 仍然是最大头。
- `raw_content_digest` 和 `reader_init` 是 materialize 阶段的两大主要成本。
- 规则决策、descriptor 装配、summary 装配都只是很小的开销。
- 如果后续要继续优化，优先级应该落在 parser 和 row digest/reader 路径，而不是 summary 组装。

## 追加对比

我又补了一轮重复性和双包并行对比，测试代码位于：

```text
gateway-data-management-system/backend/tests/backend_vnext/integration/test_snapshot_materialization_parallelism_benchmark.py
```

### `business_large` 重复基线

这轮重复了 5 次 `business_large` 的单包顺序 materialization，用来观察 warm-cache 下的稳定性。

结果如下：

| Run | Elapsed |
| --- | ---: |
| 1 | `45,368 ms` |
| 2 | `47,007 ms` |
| 3 | `48,858 ms` |
| 4 | `48,262 ms` |
| 5 | `47,597 ms` |

汇总：

- `min` = `45,368 ms`
- `median` = `47,597 ms`
- `p95` = `48,739 ms`
- `mean` = `47,418 ms`
- `max` = `48,858 ms`

这组数据说明 `business_large` 的重复运行相当稳定，当前波动主要在 1 到 2 秒量级。

### 双包串行 vs 并行

当前数据集中没有单独标注的 `initial/modified` 配对样本，所以我先用 `business_small` + `business_medium` 作为两份独立业务包的代理对比，重点看“两个包能不能并行处理”。

结果如下：

| Mode | Elapsed |
| --- | ---: |
| 串行 | `39,232 ms` |
| 并行 | `32,843 ms` |

粗略 speedup：

```text
1.195x
```

这说明：

- dataset 级并行确实有可见收益。
- 但收益并不夸张，属于“有用的优化”，不是“必须默认的基础语义”。
- 如果要把并行正式引入前端打包或后端解析，最好只放在双包场景，并保持单包路径简单。
- 对于单包 `modified-only` 上传，不存在跨包并行空间，默认仍应串行。
- 这组结果同样是在默认 `table_rule_registry` 接入后测得，因此已经包含规则过滤带来的基础耗时下降。

### 解释口径

这两轮对比都是基于当前的 SQL snapshot materialization 入口完成的，不涉及 repository-backed 路径。

- `business_large` 重复基线更接近 repeatability / warm-cache 稳定性观察。
- 双包对比是 proxy benchmark，不是正式业务 `initial -> modified` fixture。
- 如果后续补到真正的 `initial/modified` 配对数据，可以直接复用同样的测试模式再跑一轮。

## 2026-06-22 优化探针

在补上 `table_raw_sql_digest`、`base_table_fingerprint`，并把 `INSERT ... VALUES` 行解析改成更直接的扫描式实现后，又跑了一轮 `business_large`。

### 单次阶段拆分

| Phase | Elapsed |
| --- | ---: |
| `resolve_sql_dump_source` | `972 ms` |
| `parse_mysql_dump` | `18,005 ms` |
| `table_decision` | `6 ms` |
| `raw_content_digest` | `12,081 ms` |
| `schema_digest` | `11 ms` |
| `descriptor_init` | `5 ms` |
| `reader_init` | `11,950 ms` |
| `table_wrap` | `1 ms` |
| `source_context` | `0 ms` |
| `state_digests` | `1 ms` |
| `summary_snapshot_assembly` | `0 ms` |
| `total` | `43,035 ms` |

对应计数：

- `parsed_tables` = `319`
- `materialized_tables` = `311`
- `skipped_by_rule` = `8`

### 重复基线

结果如下：

| Run | Elapsed |
| --- | ---: |
| 1 | `44,184 ms` |
| 2 | `45,550 ms` |
| 3 | `47,192 ms` |
| 4 | `46,384 ms` |
| 5 | `45,656 ms` |

汇总：

- `min` = `44,184 ms`
- `median` = `45,656 ms`
- `p95` = `47,030 ms`
- `mean` = `45,793 ms`
- `max` = `47,192 ms`

这说明：

- 第二段解析优化已经把 `business_large` 的总耗时压下来了。
- `parse_mysql_dump` 仍然是最大热点，但已经比优化前更低。
- `raw_content_digest` 和 `reader_init` 仍然占有可见比例，后续若继续优化，应该继续围绕这两段，而不是 summary 组装。

## 2026-06-22 流式路径优化

在把 `parse_mysql_dump` 改成逐语句迭代消费，并把 table 级 raw SQL digest 改成增量更新后，又跑了一轮 `business_large`。

### 单次阶段拆分

| Phase | Elapsed |
| --- | ---: |
| `resolve_sql_dump_source` | `99 ms` |
| `parse_mysql_dump` | `17,050 ms` |
| `table_decision` | `6 ms` |
| `raw_content_digest` | `12,912 ms` |
| `schema_digest` | `12 ms` |
| `descriptor_init` | `5 ms` |
| `reader_init` | `10,838 ms` |
| `table_wrap` | `1 ms` |
| `source_context` | `0 ms` |
| `state_digests` | `1 ms` |
| `summary_snapshot_assembly` | `0 ms` |
| `total` | `40,962 ms` |

对应计数：

- `table_count` = `311`
- `row_count_total` = `246,359`

### 重复基线

结果如下：

| Run | Elapsed |
| --- | ---: |
| 1 | `43,594 ms` |
| 2 | `43,713 ms` |
| 3 | `43,840 ms` |
| 4 | `44,438 ms` |
| 5 | `45,489 ms` |

汇总：

- `min` = `43,594 ms`
- `median` = `43,840 ms`
- `p95` = `45,279 ms`
- `mean` = `44,215 ms`
- `max` = `45,489 ms`

和上一轮对比：

- `parse_mysql_dump` 从 `18,005 ms` 降到 `17,050 ms`。
- `total` 从 `43,035 ms` 降到 `40,962 ms`。
- 重复基线 `median` 从 `45,656 ms` 降到 `43,840 ms`。
- `reader_init` 也有可见下降，说明流式路径对整体 materialization 进入了更轻的状态。

### fast digest 阶段验收

为了把 `fast_row_digest` / `table_raw_sql_digest` 单独拆出来验证，我又跑了一次只覆盖 parse / fast-digest 的阶段性 benchmark。这个测试只计时 `parse_sql_dump_source(...)`，不包含后续 `raw_content_digest` 计算和 `reader_init`。

结果如下：

| Phase | Elapsed |
| --- | ---: |
| `parse_fast_digest` | `17,819 ms` |

对应计数：

- `table_count` = `319`
- `row_count_total` = `436,714`
- `table_raw_sql_digest_count` = `319`

这说明：

- upload 阶段的 fast digest 路径已经具备单独验收条件。
- 当前 parse 成本仍然明显，但它已经可以作为 upload-local 的唯一判据来源，不必等 canonical row digest 才做阶段内去重和路由。
- 后续若继续优化，应该把 `raw_content_digest` 流式/分块化和 `reader_init` 一起作为下一轮 benchmark 目标，再比较全链路收益。

### 真实 upload 顺序

如果按真实 upload 同步链路来写 benchmark 口径，应该把 `reader_init` 视为同步路径的一部分，但它仍然不等于 canonical digest 校验。推荐顺序是：

1. `resolve_sql_dump_source`
2. `parse_fast_digest`，产出 provisional summary
3. `table_decision` / upload-local dedup
4. `lightweight reader_init`
5. preview / front-end packaging
6. 异步 `raw_content_digest` / final summary / cache generation

在实现层面，这通常对应 `materialize_sql_snapshot_preview(...)` 和 `finalize_snapshot_materialization(...)` 两段式调用，而不是把 canonical digest 重新塞回同步链路。

这意味着后续的正式 benchmark 最好拆成三条线：

- `fast digest` 的 parse-only 基线。
- `upload sync` 的 `fast digest + lightweight reader_init + preview packaging` 基线。
- `finalization` 的 `raw_content_digest + summary finalization + cache generation` 基线。

其中 `reader_init` 的度量应尽量保持轻量，只反映表对象准备和 row stream 连接，不要再和 canonical digest 校验混在同一个计时段里。

### reader_init 拆分后的再跑基线

在把 `reader_init` 和 canonical digest 校验拆开之后，我又复跑了一次 `business_large` 的 5 次重复基线，用来确认同步 materialize 路径的实际变化。

结果如下：

| Run | Elapsed |
| --- | ---: |
| 1 | `33,017 ms` |
| 2 | `32,968 ms` |
| 3 | `32,729 ms` |
| 4 | `30,980 ms` |
| 5 | `31,717 ms` |

汇总：

- `min` = `30,980 ms`
- `median` = `32,729 ms`
- `p95` = `33,007 ms`
- `mean` = `32,282 ms`
- `max` = `33,017 ms`

和拆分前相比：

- `median` 从 `43,840 ms` 降到 `32,729 ms`。
- 这说明 `reader_init` 里的内容指纹校验成本已经从同步构造路径中移除，新的初始化阶段确实变轻了。
- 当前同步 materialize 仍然包含 canonical `raw_content_digest`，所以后续若要继续降低 upload 端延迟，下一步还是要把 canonical validation / finalization 再拆到异步路径里。

## 仍然需要的运行前提

数据条件满足，不代表环境条件自动满足。正式跑 benchmark 前还应确认：

- `gateway-data-management-system/backend/.venv/` 可用。
- `dolt` 和 `mysql` 命令可执行。
- `PYTHONPATH` 能正确指向 `gateway-data-management-system/backend`。
- `run_root` 有足够磁盘空间，尤其是 `business_large` 相关实验。
- 结果输出和日志目录没有被旧 run 污染。

这些属于运行环境前提，不属于数据 readiness 本身。

## 对并行策略的判断

现在的数据已经足以测试“是否要做多 worker 并行”，但不够直接推出“应该默认并行”。

更合理的测试顺序是：

1. 先跑单包串行基线。
2. 再跑双包串行。
3. 再跑双包 dataset 级并行。
4. 对比 large 数据上的 P50、P95、峰值内存和资源占用。

判断标准应以测得结果为准，而不是先验假设。

## 推荐的下一步

1. 先跑 `business_small_cut` 作为 smoke。
2. 再跑 `business_small` 和 `business_medium`，确认稳定性和回归情况。
3. 最后用 `business_large` 做多次重复测试，观察是否存在足够稳定的并行收益。
4. 如果 dataset 级并行没有稳定收益，就保持默认串行，避免把复杂度提前引入 front-end packaging 和 backend parsing。

### row-lazy parser 的最新复跑

在把 `ParsedTableBundle.rows` 和 `SnapshotTableReader` 都改成按需展开之后，我又针对 `business_large` 补跑了一次分段 benchmark。

结果如下：

| Phase | Elapsed |
| --- | ---: |
| `parse_fast_digest` | `6,536 ms` |
| `preview` | `7,545 ms` |
| `finalize` | `20,112 ms` |
| `preview + finalize` | `27,657 ms` |
| `full sync` | `28,445 ms` |

其中：

- `parse_fast_digest` 现在只做 statement stream 扫描、table facts 收集和 row_count 统计，不再为所有 INSERT 提前展开 row values。
- `preview` 对应 upload 同步路径，仍然包含 parse、table rule 判断和轻量 reader 构造，但 rows 现在保持 deferred，只有真正被读取时才 materialize。
- `finalize` 是异步补齐 canonical digest 的阶段，这一步会触发真正需要的 row materialization，并收口为 FINAL snapshot/summary。
- `full sync` 也因此继续下降，但总耗时仍主要由 row materialization 和 canonical digest 组成。

同一次复跑里，`business_large` 的 5 次 full materialization 重复基线是：

- `28,556 ms`
- `27,167 ms`
- `27,208 ms`
- `28,230 ms`
- `28,759 ms`

汇总：

- `min` = `27,167 ms`
- `median` = `28,230 ms`
- `p95` = `28,718 ms`
- `mean` = `27,984 ms`
- `max` = `28,759 ms`

这组结果说明：

- row-lazy parser 和 row-lazy reader 一起把 preview 同步路径从最重的 row materialization 里拆出来了。
- upload 同步路径现在真正只保留 facts + lazy reader 句柄，canonical digest 和实际 row materialization 主要被推到了异步 finalization。
- 下一步如果还要继续压 upload 延迟，重点应放在“只对真正需要访问的表展开 rows”以及进一步减少 finalization 的重排/解析成本。

### 最新复跑：`business_large` + `large-1`

在仓库外数据目录里补充了 `business_large/large-1` 之后，我又补跑了一轮和当前关心点一致的 benchmark。

结果如下：

| Case | Elapsed |
| --- | ---: |
| `business_large` `preview_elapsed_ms` | `8,840 ms` |
| `business_large` `finalize_elapsed_ms` | `22,205 ms` |
| `business_large` `full_elapsed_ms` | `31,071 ms` |
| 双 large preview 串行 | `15,415 ms` |
| 双 large preview 并行 | `8,824 ms` |
| 双 large preview speedup | `1.747x` |

对应结论：

- 现在已经具备重跑完整 benchmark 的条件。
- upload 同步部分的耗时已经可以单独报告，不再和 canonical digest / finalize 混在一起。
- 双 large preview 的并行确实有收益，但还不足以直接推导“默认必须并行”，后续仍应结合内存和资源占用一起看。

补充一个边界说明：

- 这轮 `backend_vnext` benchmark 统计的是 snapshot materialization / reader 准备阶段，不是最终 preview bundle 的 parquet 物化验收。
- `backend_vnext` 这条路径会产出 provisional summary、table_set 和轻量 reader 句柄；真正把 snapshot/input table 写成 parquet 的动作，仍然在 `backend/preview/bundle_builder.py` 的 bundle assembly 里完成。
- 所以本轮 benchmark 可以证明 upload 同步阶段的 reader/materialization 行为和耗时，但不能单凭它断言“已经在该阶段完成 parquet 落盘”。

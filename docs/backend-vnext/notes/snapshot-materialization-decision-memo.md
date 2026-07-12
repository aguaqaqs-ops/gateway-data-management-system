# Snapshot Materialization Decision Memo

本文收口前面几轮关于 `Snapshot Materialization` 的设计讨论。它是决策备忘录，不是新的 capability contract；如果后续实现发现新约束，先更新这份 memo，再同步正式文档。

## 结论

当前已经达成一致的方向是：

- `base table / fingerprint` 语义必须存在，不能省略。
- summary 只对当前 commit 负责，保持轻量，不保存历史 `table_artifact_refs` 列表。
- 可以保留一个“上一版映射”指针，但只保留单跳链路，不做完整历史表。
- `content_hash` 不应被改造成原始 SQL 文本 hash；它应继续代表 canonical row 级语义 digest。
- upload 解析阶段可以增加一个更便宜的 provisional fast hash，作为快速去重和加速输入；provenance / diagnostics 信息单独携带。
- row file / export IO cache 应使用 `row_layout_digest`，而不是 `compare_schema_digest`，作为物理复用键。
- bundle assembly 默认仍采用磁盘型物化，不把内存打包设为主路径；内存打包只作为受控优化项和 benchmark 对照项。
- Snapshot Materialization SQL Path 的默认同步输出应保持 row-stream-first，CSV/TSV/Parquet 作为下游 staging / export 能力按需开启，不应被视为同步阶段的默认 contract。
- 如果一次 upload 同时携带两份独立业务数据，默认调度策略可以是并行，但这是 flow / orchestration 层的责任，不是 capability 的内部分支。
- bundle 体积的主要来源是多份导出格式叠加，而不是 Parquet 本身：当前 single bundle round 的磁盘输出大约在 `148M` 量级，其中 `replay.sql`、`rows.csv`、`rows.tsv` 占了绝大部分；`rows.parquet` 和 JSON 元数据只占很小一部分。若按多个 round / 多份数据累加，目录总量很容易超过 `300M`。
- streaming / 按需解析、以及更细的并行策略，留到 identity / hash 语义收口后再做。

## Revisit Point

这份 memo 里的“row-stream-first + staging files 按需开启”结论是阶段性结论，不是最终版的端到端 trade-off。

在后续把 `Snapshot Materialization SQL Path`、`diff compute`、`risk` 和 `bundle` 串起来之后，应重新评估：

- 哪些 row staging 文件需要继续保留为默认产物。
- 哪些 staging / export 步骤可以继续后移到更下游的 capability。
- 哪些场景需要把文件物化前移以满足 benchmark、provider 对照或离线导出需求。

## Provenance / Diagnostics

业务上这层语义是必须的，原因有三类：

- 表去重会直接影响写入和导出表数。
- 前端展示需要稳定的 table identity。
- 跨 commit 取表需要一种可追踪、可串联的 table-level 关联方式。

### 推荐边界

- `base_table_fingerprint` 或 `table_fingerprint`：稳定的逻辑表身份，用于展示和诊断。
- `table_raw_sql_digest`：parser 级 raw SQL hash，用于回放、定位和粗粒度排查。
- `canonical_artifact_ref`：当前 commit 下这张表对应的 canonical artifact。
- `previous_canonical_artifact_ref`：可选的单跳历史指针，仅表示“上一次映射”。

不建议做成：

- `table_artifact_refs[]` 的完整历史数组。
- 把 fingerprint 直接等同于 artifact path。
- 在 summary 里放一长串历史引用链。

### 语义说明

- summary 只对当前 commit 的 table state 负责。
- 如果某张表的映射发生变化，可以把上一版映射通过 `previous_canonical_artifact_ref` 串起来。
- 这样既保留了可追踪性，又不会把 summary 做成历史日志。
- 若后续确实需要多跳历史，可以通过链式 `previous_canonical_artifact_ref` 继续追溯，而不是一次性写入历史数组。

### 落地口径

- `base_table_fingerprint` 只承担稳定逻辑表身份 / provenance 职责，不承担 canonical ref 职责。
- `canonical_artifact_ref` 只表示当前 commit 下这张逻辑表对应的主引用，由 submit / finalize 阶段生成。
- `previous_canonical_artifact_ref` 只保留单跳历史指针，由 submit / finalize 阶段在“本轮 canonical 映射相对上一轮发生变化”时写入。
- 同一 commit 内，按 `base_table_fingerprint` 分组后，第一张可复用的表作为 canonical head，组内后续重复表都指向同一个 `canonical_artifact_ref`。
- 如果后续提交里分组关系变化，则生成新的 `canonical_artifact_ref`，并把上一版 head 写入 `previous_canonical_artifact_ref`。
- 如果后续再次恢复到原始分组，也不要回指旧 head，继续沿着新的单跳链路推进，保证 base 表语义只新增、不回收。
- summary 里不引入 `table_artifact_refs[]` 这类完整历史数组。
- `base_table_fingerprint` 不参与 cache key 计算，只作为身份、展示、诊断和上游复用的输入。

### 判据分层

- upload 的 SQL 路径只计算 `fast_row_digest` 和其他轻量 provenance / diagnostics，不计算 `canonical_artifact_ref`。
- `fast_row_digest` 只作为 upload-local 的 provisional dedup / routing / cache 预筛输入，不能替代 finalized summary 的 canonical 身份。
- `sql -> sql` 场景先比较两侧的 `fast_row_digest`；两侧完全一致时，可以直接视为重复表，不必重复计算。
- `dolt -> sql` 场景比较 SQL 侧 `fast_row_digest` 与 repository-backed summary 中携带的 `fast_row_digest`；两侧完全一致时，可以直接复用。
- 只有双方都已经是 finalized summary 时，才把 `canonical_artifact_ref` 作为主身份判据。
- 如果任一侧还是 provisional / 未 finalization，仍然优先使用 `fast_row_digest`，必要时再回退到 `row_layout_digest` 或 materialization 结果判断。
- `canonical_artifact_ref` 只应该在 submit / finalize 阶段生成，不应该从 upload preview 路径提前推导出来。

## Summary-Driven Duplicate Table Virtualization

重复表优化的目标不是在某一次运行里临时少算几张表，而是把重复表从“多张真实表”降级为“一份 canonical 数据 + 多个 logical alias”。这条关系必须由 summary 表达，后续 preview、compare、history、archive 和 repository readback 都通过 summary / resolver 消费 logical table 到 canonical table 的映射。

### 权威分组

- FINAL duplicate group 是业务事实，不能仅按当前表内容即时重算。
- 同一 FINAL summary 内，`canonical_artifact_ref` 相同的 descriptors 可推导为同一 `CANONICAL` group。
- `canonical_artifact_ref` 是当前分组主引用；`previous_canonical_artifact_ref` 是上一版映射的单跳指针。
- 不新增 `duplicate_group_policy_version`，也不新增完整 group history 数组。
- 后续提交如果发生 split / merge / schema 不兼容 / ruleset 不兼容，则生成新的 `canonical_artifact_ref`，并把旧 ref 写入 `previous_canonical_artifact_ref`。
- 分组发生变化后，即使后续内容再次相同，也不自动回退旧 ref；只有显式业务规则或人工 resolution 才能重新 merge。

### 两类 alias scope

- `PROVISIONAL_FAST`：只用于 upload preview、preview cache 和 preview bundle 体积优化。它可以基于 `fast_row_digest`、`compare_schema_digest`、row count、table rules / compare mode 等快判据生成，但不得写成 FINAL `canonical_artifact_ref`。
- `CANONICAL`：只来自 submit finalize / repository readback 的 FINAL summary。history compare、archive graph 和正式 cache 只能消费这类 alias 作为权威事实。

### 应用层解析

- Repository 物理层不需要创建 Dolt SQL view，也不要求每个 logical table 都有实体表。
- 应用层应提供 summary-driven resolver，把 `logical_table_name` 解析为 canonical table，再按需派生展示用的 logical table projection。
- preview bundle 可以只携带 canonical records 和 alias mapping；前端展示 logical table，读取 canonical records。
- comparison/cache 只对 canonical table 做真实 compare 和 records/cache 生成；alias member 通过 summary-driven mapping 派生 table fact。
- `SKIP`、`BROWSE_ONLY`、`SNAPSHOT_ONLY` 等表规则仍优先决定是否进入业务 compare，不能被 duplicate alias 覆盖。

## Implementation Readiness

当前已经具备实现这套偏差收口的条件，原因是：

- summary / descriptor / payload 的序列化边界已经存在，新增字段不会破坏架构层次。
- table ruleset、summary-first compare 路由、row_layout_digest 物化复用、comparison_core cache 都已经是独立 seam。
- 当前缺失的是字段承载和生成逻辑，不是整体架构或数据流。

因此可以直接进入实现，不需要再单独等待一轮新的设计讨论。

### 推荐实现顺序

1. 先冻结字段归属和判据分层，明确 upload preview 只产出 `fast_row_digest` / `PROVISIONAL`，finalize 才产出 `canonical_artifact_ref` / `previous_canonical_artifact_ref`。
2. 再扩展 summary / descriptor / payload，补齐 canonical ref 字段与序列化规则，同时保持 `base_table_fingerprint` 只承担 provenance。
3. 接着在 submit / finalize 阶段实现 canonical head 选择、单跳历史指针写入和分组变化判定。
4. 然后把 `Open Current Ref` / readback / compare 的消费路径改成分层判据：provisional 走 `fast_row_digest`，finalized 走 `canonical_artifact_ref`，必要时再 selective materialize，最后才 fallback 全量物化。
5. 再把 benchmark / report 口径同步到新的 canonical ref 语义，补齐 cache hit / miss 与异步补 cache 的观测。
6. 最后补测试，优先覆盖 SQL->SQL、Dolt->SQL、finalized snapshot reuse、分组变化、恢复分组、重复表复用、fallback 物化这几类场景。

## Hash Strategy

这里最关键的是把“快 hash”和“语义 hash”分开。

### 现有语义保持不变

- `raw_content_digest` 继续表示 canonical row digest。
- 如果某处还保留短名 `content_hash`，它也应该等价于 `raw_content_digest`。
- 不要把 `content_hash` 重新定义成原始 SQL 文本 hash。

### 新增快路径

upload 解析阶段可以增加一个更便宜的 table-level raw hash，用于：

- 快速判断是否明显重复。
- 作为 base table / fingerprint 计算的加速输入。
- 为后续 async / commit 阶段的完整 canonical digest 提供预筛。

推荐字段名：

- `fast_row_digest`
- `raw_content_digest`
- `row_layout_digest`
- `content_hash`

`fast_row_digest` 表示只看 INSERT 数据块的 upload 快路径 hash。

如果实现上拿到的是 canonical row digest 或 layout digest 的最终结果，也应分别进入上面的对应字段，不要混成一个字段。

### Provenance / Diagnostics

- `table_raw_sql_digest`：parser 级 raw SQL hash，用于回放、定位和粗粒度排查。
- `base_table_fingerprint`：表级 provenance / 身份元数据，用于展示和诊断。
- 这两类信息都不进入主判据链。

### 推荐流程

1. upload parse 阶段先算 `fast_row_digest`，尽量减少重排、规范化和 digest 成本；provenance / diagnostics 信息可并行保留。
2. 异步阶段或 commit 阶段再算完整 `raw_content_digest`。
3. 下游流程继续只依赖 canonical digest 作为语义真值。

### 影响边界

这个拆分是合理的，但必须明确限制：

- 在 upload 阶段，`fast_row_digest` 可以作为该阶段内的主要判据来源，覆盖 SQL->Dolt 与 SQL->SQL 两条上传路径的去重、路由和缓存预筛。
- provenance / diagnostics 元数据可以并行保留，但不进入主判据链。
- canonical digest 仍然是最终校验结果。
- cache、summary、comparison、export 不应只依赖 raw hash。
- 如果 raw hash 与 canonical digest 的结论不一致，以 canonical digest 为准。
- `row_layout_digest` 应作为 row file / export IO cache 的物理复用键；它应由 canonical raw content digest 和 canonical export schema content 组成，不应混入 table name 或 compare schema 语义。
- 因此，upload 阶段允许接受少量与后续 canonical 重算不完全一致的情况，但这种差异必须被视为“阶段内 provisional 决策”和“最终事实”之间的正常收敛，而不是同一事实源的冲突。

### 实际数据验证

对 `business_large` 和 `business_large/large-1` 做过一次离线对照后，可以确认“只看 INSERT 数据块”的 fast hash 不能直接作为 row file / export IO cache 的唯一命中键。

- 当前 `row_layout_digest` 分组：`146` 个 cache entry，`165` 次复用命中。
- 仅按 INSERT 数据块构造的临时 fast digest：`116` 个分组，`203` 次复用命中。
- 其中存在 `13` 组把不同 schema / layout 的表误合并到同一个 key，最明显的一组甚至把 `155` 张空表合并在一起。

结论是：

- fast hash 可以保留为 upload-local 的前置判据或预筛输入。
- 但它不能替代 `row_layout_digest` 作为物理 row file 复用键。
- 如果要提升 cache 命中效率，应该在 `fast_row_digest` 之后继续保留 schema / layout 维度，而不是把 layout 直接删掉。

## Two-Stage Summary

如果 upload 阶段先使用 `fast_row_digest`，summary 也建议拆成两段，而不是在同一条 summary 上原地补齐。

### 推荐形态

- 阶段 1：upload / parse 产出 `fast_row_digest`，并形成 `provisional summary` 或等价的轻量中间态。
- 阶段 2：异步阶段或 commit 阶段补算 `raw_content_digest`，写入 `final summary`。

### 为什么不建议原地补写

当前 summary store 是按 summary artifact digest 寻址和写入的，`store_summary()` 逻辑本身是“写一次、按摘要定位”，不是“先写一半再 patch 同一条记录”。

因此如果要做两阶段，应该明确成下面两种之一：

- 两个 artifact state: `provisional` / `final`
- 或者两个不同 logical ref，前者只做早期路由，后者作为正式事实

不建议把 `fast_row_digest` 和 `raw_content_digest` 混到同一个正式 summary 语义里，再依赖后续补丁把它“修正回来”。

### 消费边界

- `fast_row_digest` 只能给 upload 期的快速判断、去重和缓存预筛使用。
- 在 upload / preview 阶段，它也可以作为前端默认表去重的 provisional key，但只能表示“当前阶段的最佳判据”，不能表示最终身份。
- `raw_content_digest` 仍然是 compare / export / final summary 的权威输入。
- 只有 final summary 才应该进入后续稳定读路径。
- provisional summary 可以存在，但它不应被当作最终事实对象。

### Reader Init / Canonical Validation

真实的 upload 同步路径建议拆成下面几步：

1. `resolve_sql_dump_source`
2. `parse_fast_digest`，产出 provisional summary
3. `table_decision` / upload-local dedup
4. `lightweight reader_init`，准备 preview / front-end packaging 所需的 table 句柄和元数据
5. 返回 upload 响应
6. 异步 `raw_content_digest` / canonical digest validation / final summary / cache generation

实现上已经可以把这条链路拆成两个显式 entrypoint：

- `materialize_sql_snapshot_preview(...)` 负责同步 preview，只产出 `PROVISIONAL` 结果。
- `finalize_snapshot_materialization(...)` 负责异步补齐 canonical `raw_content_digest` 并收口为 `FINAL` 结果。

这里的 `reader_init` 只负责把表事实、列信息、row stream 句柄和预览所需元数据准备好，不应隐式承担 canonical digest 校验。canonical digest 校验是独立阶段，可以在异步 finalization 或显式 validation pass 中完成。

### 语义建议

- `fast_row_digest`：upload 阶段快速判据。
- `raw_content_digest`：canonical row digest，最终真值。
- `summary_state`：建议显式区分 `PROVISIONAL` / `FINAL`，避免上层误用。

## Streaming / Parallelism

当前先不把 streaming / 按需解析作为前置条件。

建议顺序是：

1. 先把 base table / fingerprint 语义收口。
2. 再把 raw hash 和 canonical digest 的职责切开。
3. 最后再做 streaming parser、按需 materialization 和更细粒度并行。

原因很简单：

- 没有稳定 identity，streaming 只会把复杂度提前。
- 没有 hash 分层，优化后也很难判断收益来自语义还是实现细节。
- benchmark 已经表明 parser 和 canonical digest 是主要成本，后续优化应围绕这些热路径展开。
- benchmark 口径也应分开记录 `fast digest`、`lightweight reader_init` 和 `canonical digest validation`，否则 upload 与 finalization 的收益会混在一起。

## 字段名建议

| 语义 | 推荐字段名 | 说明 |
| --- | --- | --- |
| 当前 canonical artifact | `canonical_artifact_ref` | 当前 commit 的主引用。 |
| 上一版映射 | `previous_canonical_artifact_ref` | 只保留单跳，不存完整历史列表。 |
| 快速 raw hash | `fast_row_digest` | upload parse 阶段的 INSERT 数据块快路径输入。 |
| canonical row digest | `raw_content_digest` | 继续作为语义真值。 |
| row file 复用键 | `row_layout_digest` | 物理 row file / export IO cache 的命中依据。 |
| `content_hash` 旧短名 | 保持等价于 `raw_content_digest` | 不要重定义成 raw SQL hash。 |

### Provenance / Diagnostics Fields

| 语义 | 推荐字段名 | 说明 |
| --- | --- | --- |
| 稳定逻辑表身份 | `base_table_fingerprint` / `table_fingerprint` | 用于 table 去重、前端展示和跨 commit 关联。 |
| raw SQL hash | `table_raw_sql_digest` | parser 诊断、回放和粗粒度路由输入。 |

## 当前建议

- 先以这份 memo 作为讨论收口。
- 实现时优先补 `fast_row_digest` 的快路径，并把 provenance / diagnostics 信息放在独立段落。
- 等 benchmark 重新验证后，再把正式 contract 反映到 `snapshot-materialization.md`、`identity-and-digests.md` 和相关 summary 文档里。

## Repository Ref Materialization Ready

在 `RepositoryRef Materialization` 进入实现前，当前已经足够收口的点是：

- 对外 `source_kind` 统一使用 `IMMUTABLE_REPOSITORY_REF`。
- `digest_contract_version` 进入 `snapshot_digest` 语义，不再隐式跳过。
- scalar encoding 作为共享能力收口，优先复用给 SQL path、repository ref path 和 repository import readback。
- `requested_tables` 维持当前“子集选择 + warning 诊断”的简单行为，不额外拆成纯 hint。
- 类型覆盖遵循“表级降级优先、不可稳定归一化则 unsupported”的策略。

建议的执行顺序只有三步：

1. 冻结文档口径，把 repository ref / snapshot digest / scalar encoding 的一致性写清楚。
2. 实现共享 scalar encoding 与 repository ref materialization 主路径。
3. 补齐类型覆盖、requested_tables、catalog 单次加载和降级路径的测试。

不需要再单独新建一个临时执行文档；这份 memo 加上 capability 设计文档已经足够支撑直接执行。

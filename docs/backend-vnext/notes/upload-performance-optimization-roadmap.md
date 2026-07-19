# Upload 性能优化总列表

## 当前基线

基线来自 2026-07-12 手测日志：

- Backend log: `gateway-data-management-system/backend/logs/formal-upload-benchmark-gateway2.log`
- Frontend console: `gateway-data-management-system/backend/logs/formal-upload-benchmark-frontend-console.jsonl`

| 场景 | 用户体感前端 total | 后端 READY total | 主要瓶颈 |
| --- | ---: | ---: | --- |
| `INITIALIZE_BASELINE` large | 32.7s | 19.3s | 前端打包 7.1s、SQL parse/materialize 9.6s、snapshot parquet encode 8.6s、OPFS write 1.5s |
| `FULL` large-1 + large-2 | 85.6s | 63.1s | 前端双包串行打包 10.6s、后端双 SQL materialize 19.0s、baseline snapshot rows restore 15.1s、双 pair preview 29.0s、OPFS write 3.5s |

已确认不是主要瓶颈：

- bundle assemble / tar create / bundle write：INITIALIZE 约 0.1s，FULL 约 0.3s。
- workbench model build：两条路径均小于 10ms。
- comparison core 已明显下降，FULL 双 pair 合计约 11s，暂不作为第一优先级。

## 为什么 FULL 改造会影响 INITIALIZE

虽然很多问题是由 FULL large-1 + large-2 暴露出来的，但实现落点大量位于通用 upload preview contract，因此 INITIALIZE 也会承担这些成本：

- 表格可读性修复后，upload preview 不再允许 descriptor 占位；所有 visible table row refs 必须在 READY 前闭合为真实 Parquet。INITIALIZE 也必须导出 snapshot parquet，因此产生约 8.6s 的 `upload.preview.snapshot_parquet_encode`。
- preview bundle assembler、surface、business projection、risk report、closure validation 已统一为正式 vNext 路径。INITIALIZE 只有一个 pair，但仍走同一套正式 bundle 组装与 artifact closure。
- 服务端 source package streaming 主要减少服务端内存复制和二次落盘，不代表浏览器上传时服务端已经开始 SQL parse。当前 INITIALIZE 仍是前端先完整 package，再上传，后端再 parse/materialize。
- 多 surface 支持本身不是 INITIALIZE 的主要拖慢点；当前 bundle assemble/tar/write 仍是百毫秒级，主要耗时来自前端打包、SQL parse/materialize、snapshot parquet encode 和 OPFS write。

因此后续优化应同时看两条收益线：

- INITIALIZE 优先收益：前端打包、snapshot parquet encode、SQL parse/materialize。
- FULL 优先收益：前端双包并行、baseline snapshot rows restore、跨 pair snapshot parquet 复用、双份 SQL materialize 争用。

## 优先级列表

### P1：前端 FULL 双包并行打包

目标：让 initial / modified package 在浏览器端并行准备，避免服务端在前端串行打包期间空等。

实现建议：

- `runFullUploadFlow()` 中将 initial / modified 的 `packageWorkbenchDirectory()` 改为 `Promise.all`。
- 保留 `package_role=initial|modified` 的 benchmark 事件。
- `frontend.upload_flow.total.package_total_ms` 保留两个 package duration 之和，同时新增 `package_wall_ms` 表示并行打包墙钟耗时，避免并行后汇总口径误导。

预期收益：

- FULL 前端 package 从约 10.6s 降到约 5.5–7s。
- FULL 体感总耗时预计下降 4–5s。

验收：

- `frontend.upload_flow.package` 仍分别输出 initial / modified。
- `frontend.upload_flow.package_wall` 与 `frontend.upload_flow.total.package_wall_ms` 能反映并行打包墙钟耗时。
- FULL 上传结果、bundle 下载和双 pair 切换不变。

### P2：减少前端打包 bytes copy

目标：降低 large 包浏览器端内存复制、主线程占用和上传前额外拷贝。

实现建议：

- P2a 先做低风险 copy 收口：`packageWorkbenchDirectory()` 直接返回 `payloadBlob`，formal upload、FULL upload、submit 和 dev upload 都复用该 Blob，不再把已有 `Uint8Array` 复制到新 `ArrayBuffer` 后再上传。
- `sha256Hex()` 对完整 `Uint8Array` 直接使用底层 `ArrayBuffer`，只在 subarray 场景做必要 slice，去掉常规路径中的 digest 输入全量复制。
- 新增 `frontend.package.blob_create` benchmark 事件，用于确认 Blob 准备耗时和 payload size。
- 保持 benchmark 拆分 `read_files/build_tar/gzip_store/sha256`，确认具体热点。
- 本轮不改变 tar/gzip 格式、不做 streaming tar/gzip；若 P2a 收益有限，再进入 P2b 评估 chunk 化或 Web Worker 打包。

预期收益：

- 主要降低内存峰值和卡顿；耗时收益依赖浏览器，预计 0.5–2s。

验收：

- package sha256、size、server staging 结果不变。
- benchmark 中 package 子阶段不回退。
- `frontend.package.blob_create` 应为低毫秒级；FULL `upload_api_wait` 或 total 不应回退。

### P3：baseline snapshot rows restore 懒恢复

目标：让 FULL baseline archive 命中真正跳过重 SQL parse/materialize，而不是用 15s eager restore 替代它。

实现建议：

- P3a 将 restore 改为 file-backed / lazy reader：summary、descriptor 与 logical table map 立即恢复，rows 在 comparison/snapshot export 读取时按需展开。
- restore 阶段不再逐表读取 parquet 并重算 row digest；完整性边界由 artifact store 的 archive content digest 保证，单表 parquet 在首次读取时校验 schema 和 row_count。
- 临时解压目录只做可重建 cache；使用 `.restore-complete.json` marker 记录 artifact manifest/content digest，marker 缺失或不匹配时重新解包。
- benchmark 增加 `cache_status`、`artifact_read_ms`、`archive_extract_ms`、`metadata_load_ms`、`reader_bind_ms`、`eager_validate_ms`，用于区分 cold/warm cache 和 eager validation 是否已归零。
- 本轮不做 tar 内单表 lazy extraction；archive 仍整包解压到 restore cache。

预期收益：

- FULL `upload.full.baseline_snapshot_rows_restore` 从 9–15s 降到 cold 2–4s、warm 0.5–2s。
- FULL 后端 total 预计下降 6–10s。

验收：

- restore HIT 时不产生 baseline SQL parse/materialize。
- restore HIT 时 `eager_validate_ms=0`，且 restore 阶段不读取 parquet rows。
- `cache_status` 可正确区分 cold/warm。
- restored `SnapshotTableSet` 的 row_count、descriptor、alias/logical table map 与原 FINAL snapshot 一致。
- comparison/risk/snapshot parquet 输出不变。

### P4：FULL 双 pair snapshot parquet 跨 pair 复用

目标：避免 FULL 中 `baseline_to_initial` 与 `initial_to_modified` 对同一 initial snapshot side 重复 encode parquet。

实现建议：

- P4-0 已补 dry-run 指标，不改 bundle 内容：所有 pair prepare 完成后扫描 pair-local snapshot export tasks，按 fast candidate key 统计跨 pair 可复用 task/row/bytes/top groups。
- dry-run 事件为 `upload.preview.snapshot_parquet_cross_pair_reuse_dry_run`，至少输出 `pair_count`、`snapshot_export_task_count_total`、`cross_pair_reusable_task_count`、`cross_pair_reusable_row_count`、`cross_pair_reusable_estimated_size_bytes` 和 `top_cross_pair_reuse_groups`。
- P4-0 在 large FULL 中观察到 `202` 个 snapshot export task 里约 `97` 个可跨 pair 复用，超过进入 P4-1 的阈值。
- P4-1 在单个 FULL preview bundle 内引入 shared snapshot artifact refs：相同 side + fast candidate key 的表统一指向 `shared/snapshot-tables/{side}/{digest}.parquet`，只 encode 一次。
- P4-1 仍必须保持 comparison/risk/records identity 不变；只共享前端 browse snapshot parquet，不共享 records/risk/projection。
- 实际复用事件为 `upload.preview.snapshot_parquet_cross_pair_reuse`，输出 `shared_snapshot_ref_count`、`cross_pair_reused_export_task_count`、`cross_pair_reused_row_count`、`cross_pair_reused_estimated_size_bytes` 和 `shared_snapshot_groups`。

预期收益：

- P4-0 无性能收益，只给出上限判断。
- P4-1 命中充分时，FULL snapshot parquet encode 预计下降 4–5s，OPFS entry/bytes 可能同步下降。

验收：

- 两个 pair 的同名 initial-side browse table 均可打开。
- `artifact_count_by_kind.snapshot_parquet` 应从约 `202` 降到约 `105` 左右，或 snapshot encode duration 明显下降。
- preview_index refs 全部闭合且为真实 parquet。

### P5：FULL 双 pair preview prepare 并行

目标：在 P4 shared snapshot refs 稳定后，评估并并行化两个 pair 的 preview prepare 段，优先降低串行 `run_upload_preview` / comparison / risk / projection 放大。

实现建议：

- P5-0 先补结构确认指标，不改执行顺序：
  - `upload.preview.prepare_pair_total`
  - `upload.preview.run_upload_preview`
  - `upload.preview.records_copy`
  - `upload.preview.finalize_pair_total`
- P5-1 已用 2 worker 并行 prepare 做过实验；snapshot shared ref rewrite、snapshot parquet export、records/risk/projection artifact publish、bundle assemble 仍保持串行。
- 20260713q benchmark 结论：两个 `comparison_core.total` 从约 3.5–3.9s 放大到约 7.5–7.8s，`upload.preview.total` 从约 14.11s 到约 14.18s，收益为负。
- 因此 P5-1 实现不保留；后续不要继续沿“线程并行 pair prepare”方向推进，除非先解决 comparison core 的 CPU/reader 争用。

预期收益：

- 当前 P5-1 无保留收益；优化重心转向 SQL/materialize 或 comparison algorithm。

验收：

- P5-0 指标保留，用于后续判断瓶颈。
- P5-1 代码保持回退状态；FULL 输出与 P4-1 串行 preview 行为一致。

### P6：SQL parse/materialize 继续压缩

目标：继续降低 INITIALIZE 首传与 FULL initial/modified 的 SQL parse/materialize 成本。

实现建议：

- P6-0 先补观测，不改行为：
  - `snapshot_materialize.parse_sql` 增加 statement/INSERT 字节量、最大 INSERT statement、按表聚合的 top INSERT rows/bytes，以及 `parser_known_phase_duration_ms` / `parser_unattributed_duration_ms`。
  - `snapshot_materialize.table_loop` 增加 requested filter skip、rule decision、materialization error、work item count、top row-count tables，以及 top slow table 的 descriptor/reader/row finalize/digest phase breakdown。
  - `upload_benchmark_summary.py` 展示 `resolve_sql_source`、`sql_source_open`、`parse_sql` 与 `table_loop` 细分字段。
  - 不记录原始 SQL、VALUES 内容或业务行数据，只记录表名、计数、字节数和耗时。
- P6-1 fast-seek scanner 实验已回退：
  - 20260713s benchmark 显示 large INSERT 场景下 `parser_statement_scan_duration_ms` 放大到 199–250s，INITIALIZE `parse_sql` 回退到约 202s。
  - 后续不再沿多 token `str.find()` fast-seek 方向优化 Python text scanner。
- P6-1b 仅做低风险 record/metrics 收口：
  - 恢复原单 pass char-loop scanner。
  - 内部 parse 使用 statement record，复用已 trim statement、byte size 和 segment count，避免 parse loop 二次 `strip()` 与基础元数据重复计算。
  - `snapshot_materialize.parse_sql` 增加 `parser_statement_scan_duration_ms`、`parser_statement_materialize_duration_ms`、`parser_statement_trim_duration_ms`、`parser_chunk_count`、`parser_statement_segment_count_total`、`parser_max_statement_segment_count`。
- P6-2 只补 FULL materialize 并发/争用诊断，不改变默认并行策略：
  - FULL initial / modified stage+materialize worker 输出 `upload.full.stage_materialize_worker`，记录 `worker_strategy`、`thread_id`、`start_offset_ms`、stage/materialize duration 和 source size。
  - `snapshot_materialize.*` 子事件带 `upload_kind` 与 `materialize_pair_run_id`，便于区分 initial / modified。
  - `BACKEND_VNEXT_FULL_MATERIALIZE_WORKERS=1` 可强制串行用于 A/B；unset 或 `2` 保持当前双线程。
- 复核 FULL 双 worker 并发时单份 parse 是否因 CPU/IO 争用从 INITIALIZE 的 9.6s 放大到 17s。
- 若并发争用明显，评估 materialize worker 策略：串行 parse + 并行后段，或限制 concurrent parse。
- 继续推进 parser streaming 热点：减少大 INSERT 字符串复制、减少 rows 展开、保持 lazy reader。

预期收益：

- INITIALIZE parse/materialize 从 9.6s 继续下降。
- FULL `upload.full.stage_materialize_pair` 从 19s 降到 12–15s。

验收：

- P6-0 完成后，`gateway2-rerun-20260713r` 这类 slice 的 summary 能直接回答：
  - parse 总耗时是否由已打点 phase 解释；
  - 是否由少数大 INSERT 表主导；
  - table loop 中 reader build、row finalize、row digest、descriptor finalize 的占比；
  - FULL 两份 SQL parse/materialize 是否各自独立耗时。
- P6-1b 完成后，`gateway2-rerun-20260713t` 这类 slice 必须先证明 INITIALIZE 没有 200s 级回退；若收益噪声级但不回退，可保留作为指标/小清理。
- P6-2 完成后，分别跑默认并行与 `BACKEND_VNEXT_FULL_MATERIALIZE_WORKERS=1` 串行 FULL，对比 `stage_materialize_pair`、单份 `parse_sql` 与 `upload.total`。
- `snapshot_materialize.parse_sql`、`snapshot_materialize.total` 下降。
- table_count、row_count、digest、preview rows 不异常偏移。

### P7：Snapshot parquet encode / bundle entry 优化

目标：先解释 `upload.preview.snapshot_parquet_encode` 的 5–7s 内部组成，再决定是否进入低复杂度优化；同时关注 READY 后前端 bundle 落盘成本。

实现建议：

- P7-0 只补观测，不改变 READY 契约、bundle refs、前端读取接口或 snapshot export worker 策略：
  - `_write_snapshot_table_parquet()` 返回每张表的 phase timing。
  - 每张表记录 `row_iter_duration_ms`、`scalar_normalize_duration_ms`、`dataframe_build_duration_ms`、`parquet_write_duration_ms`、`row_count`、`column_count`、`size_bytes` 与 `empty_table`。
  - `upload.preview.snapshot_parquet_encode` 聚合输出 `row_iter_duration_ms`、`scalar_normalize_duration_ms`、`dataframe_build_duration_ms`、`parquet_write_duration_ms`、`empty_table_count`、`non_empty_table_count`。
  - `top_slow_tables` 带同样的 phase breakdown，用于判断热点集中在 `device_st/device_mx/b*_iec104_syx_list` 这类大表，还是分散在 parquet writer / DataFrame 构造。
- P7-0 之后再决定 P7-1：
  - 如果主要是 `scalar_normalize_duration_ms`，优先考虑按列类型批量 normalize 或减少 Python scalar 转换。
  - 如果主要是 `dataframe_build_duration_ms`，优先评估 Arrow/Polars 构造路径。
  - 如果主要是 `parquet_write_duration_ms`，再考虑 writer 参数、文件布局或少量可控并行。
  - 如果主要是 `row_iter_duration_ms`，回到 SQL/materialize reader 路径评估。
- P7-1a 只补 reader 来源诊断，不改变导出行为：
  - per-table `top_slow_tables` 增加 `reader_kind`、`source_kind`、`reader_row_cache_state`、`insert_statement_count`。
  - aggregate 增加 `reader_kind_counts`、`source_kind_counts`、`lazy_sql_table_count`、`lazy_sql_insert_statement_count`、`parquet_archive_table_count`。
  - 若 INITIALIZE 和 FULL 第一 pair 的热点主要为 `lazy_sql`，P7-1b 优先做 `LazySnapshotTableReader` columnar export fast path。
  - 若热点主要为 `parquet_archive`，优先评估 snapshot rows archive parquet passthrough / columnar read。
- P7-1b 为 `LazySnapshotTableReader` 增加 snapshot export 专用列式 fast path：
  - 只改变 upload preview snapshot parquet export 内部收集列数据的方式，不改变 `iter_rows()`、comparison/risk/records 或 bundle refs。
  - full-width INSERT 直接按列 append normalized value；column-list INSERT 对未出现列 append `None`，保持旧 row expansion 语义。
  - benchmark 增加 `snapshot_export_path`、`lazy_sql_columnar_fast_path_table_count`、`lazy_sql_columnar_fast_path_row_count`、`lazy_sql_columnar_fast_path_duration_ms` 和 `generic_iter_rows_table_count`。
- 优先通过后端减少 bundle entry 数：snapshot parquet 复用、减少重复 pair artifacts。
- 后续再评估前端 lazy extract：先保存 tar，再按需解包 table parquet；该方案会改变本地读取模型，需单独设计。

预期收益：

- INITIALIZE OPFS write 从 1.5s 降低到 1s 左右。
- FULL OPFS write 从 3.5s 降低到 1.5–2.5s，取决于 entry 数下降幅度。

验收：

- P7-0 benchmark 中 `upload.preview.snapshot_parquet_encode` 能直接展示 row iteration / scalar normalize / DataFrame build / parquet write 四段占比。
- P7-0 本身不应让 snapshot encode 明显回退，允许小幅日志噪声。
- P7-1a benchmark 中 `reader_kind_counts` 与 `top_slow_tables[*].reader_kind` 能直接解释 row iteration 热点来源。
- `frontend.bundle.opfs_write` 下降。
- bundle reload、table load、risk/diff records 读取不回退。

### P8：Comparison core 后续优化

目标：在 IO/restore/snapshot export 大头处理后，再优化 comparison core。

候选方向：

- ordered semantic result run-local template cache。
- projection build 算法级优化。
- 谨慎评估 pair/table-level 并行；之前微观对象优化和部分并行尝试收益不稳定，需先有 benchmark guard。

预期收益：

- FULL comparison core 当前双 pair 合计约 11s；只有当前面 P1–P6 完成后仍是主要瓶颈时再进入。

验收：

- records count、table status、risk row-level annotation 不回退。
- ordered diff 展示与旧实现语义一致。

## 执行默认顺序

1. P1 前端 FULL 双包并行打包。
2. P2 前端打包 bytes copy 小优化。
3. P3 baseline snapshot rows lazy restore。
4. P4 FULL 双 pair snapshot parquet 跨 pair 复用。
5. P5 FULL 双 pair preview prepare 并行。
6. P6 SQL parse/materialize 争用与 streaming 热点。
7. P7 OPFS / bundle entry 优化。
8. P8 comparison core。

每完成一项后复跑两条固定场景：

- large `INITIALIZE_BASELINE`
- large-1 + large-2 `FULL`

并记录：

- backend `upload.total`
- backend `snapshot_materialize.*`
- backend `upload.full.baseline_snapshot_rows_restore`
- backend `upload.preview.snapshot_parquet_encode`
- frontend `frontend.upload_flow.total`
- frontend `frontend.upload_flow.package`
- frontend `frontend.bundle.opfs_write`

标准输出目录建议固定为 `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/`，并至少保留：

- `backend.log`
- `frontend-console.raw.jsonl`
- `frontend-console.events.jsonl`
- `initialize_large-summary.md/json`
- `full_large_pair-summary.md/json`
- `compare-initialize-vs-full.md`

## 前后端联合 benchmark 模板

后续每一项优化都应同时采集后端 benchmark 与前端 console benchmark。只看 backend 会漏掉前端 package / OPFS，单看前端又无法定位 READY 前阶段。

> 实际复跑时，建议优先执行 `gateway-data-management-system/backend/tools/upload_benchmark_run_gateway2.sh` 一次性完成 reset、启动后端、前端自动化和 summary/compare；如果需要分步排查，再参考 [gateway2 upload benchmark runbook](./upload-benchmark-gateway2-runbook.md) 手工拆开流程。现在这条模板链路是 fail-closed 的，会先预检 frontend / control plane，再在 backend 就绪后继续，collect 也会在缺日志时直接失败。

> 如果你要直接做三对 `large` 的独立 A/B 复测，优先看 [gateway2 large pair benchmark runbook](./upload-benchmark-gateway2-large-pairs-runbook.md)，它固定了 `large-1 -> large-2`、`large-1 -> large-4`、`large-1 -> large-5` 三轮的执行顺序和产物布局。

### 模板 A：INITIALIZE_BASELINE large

用途：

- 观察首传体感耗时。
- 验证前端打包、SQL parse、snapshot parquet encode、OPFS write 是否回归。

前置：

- 后端启动时设置 `BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1`。
- 浏览器 console 执行 `localStorage.setItem("formalUploadBenchmark", "1")`。
- 使用全新 workspace，避免旧 preview bundle 或本地 OPFS 状态影响结果。

输入：

- `business_large/large`

记录字段：

| 来源 | 字段 |
| --- | --- |
| backend | `run_id` |
| backend | `upload.total` |
| backend | `route.multipart_spool` |
| backend | `source_package.stage.total` |
| backend | `snapshot_materialize.parse_sql` |
| backend | `snapshot_materialize.total` |
| backend | `comparison_core.total` |
| backend | `upload.preview.snapshot_parquet_encode` |
| backend | `upload.preview.bundle_assemble` / `tar_create` / `bundle_write` |
| frontend | `frontend_run_id` |
| frontend | `frontend.upload_flow.total` |
| frontend | `frontend.upload_flow.package` |
| frontend | `frontend.upload_flow.upload_api_wait` |
| frontend | `frontend.bundle.total` |
| frontend | `frontend.bundle.opfs_write` |
| frontend | `frontend.upload_flow.stored_bundle_reload` |
| frontend | `frontend.upload_flow.build_workbench_model` |

验收关注：

- `backend_run_id` 能对应 backend `run_id`。
- `frontend.upload_flow.upload_api_wait` 应接近 backend `upload.total` 加网络/operation polling 开销。
- 如果 `frontend.upload_flow.total - backend_wait_ms` 变大，优先看 package / OPFS。

### 模板 B：FULL large-1 + large-2

用途：

- 观察第二次双份业务数据上传体感耗时。
- 验证 baseline restore、双份 materialize、双 pair preview、FULL 前端 package 是否回归。

前置：

- 后端启动时设置 `BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1`。
- 浏览器 console 执行 `localStorage.setItem("formalUploadBenchmark", "1")`。
- 先完成一次可提交/可 archive 的 baseline，确保 FULL baseline restore 有机会命中 snapshot rows archive。

输入：

- initial: `business_large/large-1`
- modified: `business_large/large-2`

记录字段：

| 来源 | 字段 |
| --- | --- |
| backend | `run_id` |
| backend | `upload.total` |
| backend | `upload.full.stage_materialize_pair` |
| backend | `upload.full.baseline_snapshot_rows_restore` |
| backend | `snapshot_materialize.parse_sql` 两条 |
| backend | `snapshot_materialize.total` 两条 |
| backend | `comparison_core.total` 两条 |
| backend | `upload.preview.prepare_pair_total` 两条 |
| backend | `upload.preview.run_upload_preview` 两条 |
| backend | `upload.preview.pair_total` 两条 |
| backend | `upload.preview.snapshot_parquet_encode` 两条 |
| backend | `upload.preview.records_copy` 两条 |
| backend | `upload.preview.finalize_pair_total` 两条 |
| backend | `upload.preview.snapshot_parquet_cross_pair_reuse_dry_run` |
| backend | `upload.preview.snapshot_parquet_cross_pair_reuse` |
| backend | `upload.preview.bundle_assemble` / `tar_create` / `bundle_write` |
| frontend | `frontend_run_id` |
| frontend | initial / modified `frontend.upload_flow.package` |
| frontend | `frontend.upload_flow.upload_api_wait` |
| frontend | `frontend.upload_flow.total` |
| frontend | `frontend.bundle.total` |
| frontend | `frontend.bundle.opfs_write` |

验收关注：

- `upload.full.baseline_snapshot_rows_restore.status` 应为 `HIT`；如果 miss/fallback，不能用该轮判断 restore 优化收益。
- `frontend.upload_flow.package` 应区分 initial / modified；并行打包后需要额外记录 `frontend.upload_flow.package_wall` 和 `package_wall_ms`。
- `upload.preview.snapshot_parquet_encode` 两条合计用于判断跨 pair parquet 复用收益。
- `upload.preview.snapshot_parquet_cross_pair_reuse_dry_run.cross_pair_reusable_task_count` 用于评估理论上限。
- `upload.preview.snapshot_parquet_cross_pair_reuse.cross_pair_reused_export_task_count` 和 `artifact_count_by_kind.snapshot_parquet` 用于验证 P4-1 实际命中。

### 模板 C：单项优化 A/B 对照

用途：

- 每完成一个优化 slice 后，用相同数据、相同 workspace 前置条件和相同浏览器环境做 before/after 对照。

记录格式：

| 场景 | 指标 | Before | After | Delta |
| --- | --- | ---: | ---: | ---: |
| INITIALIZE | frontend total |  |  |  |
| INITIALIZE | backend upload.total |  |  |  |
| INITIALIZE | target metric |  |  |  |
| FULL | frontend total |  |  |  |
| FULL | backend upload.total |  |  |  |
| FULL | target metric |  |  |  |

执行规则：

- 每轮只评价当前 slice 的 target metric，不把其他噪声当作结论。
- 如果 target metric 下降但总耗时不降，继续查看下游是否出现新瓶颈。
- 如果 target metric 未下降或总耗时明显回退，应优先回退或暂停讨论，不继续叠加下一项优化。

建议保存产物：

- 后端日志：`gateway-data-management-system/backend/logs/upload-benchmark/<slice>/backend.log`
- 前端 console 原始日志：`gateway-data-management-system/backend/logs/upload-benchmark/<slice>/frontend-console.raw.jsonl`
- 前端 console 事件流：`gateway-data-management-system/backend/logs/upload-benchmark/<slice>/frontend-console.events.jsonl`
- 简短结果表：追加到本文件或对应 slice execution note。

## 标准化脚本入口

后续每个优化 slice 建议配套保存一份可重复生成的 summary 和 compare 结果，统一通过下面的脚本完成：

- `gateway-data-management-system/backend/tools/upload_benchmark_summary.py`
- `gateway-data-management-system/backend/tools/upload_benchmark_compare.py`
- `gateway-data-management-system/backend/tools/upload_benchmark_collect.sh`
- `docs/backend-vnext/notes/upload-benchmark-console-capture.md`

推荐目录结构：

- `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/<scenario>-backend.log`
- `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/<scenario>-frontend.jsonl`
- `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/<scenario>-summary.md`
- `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/<scenario>-summary.json`

约定：

- `summary.json` 作为 A/B 对照的输入。
- 如果前后端无法自动对齐，summary 会标记为 `best_effort`，不要把这轮结果直接当成严格对照。
- 每个 slice 的结论优先贴 summary markdown，不要只留截图或手工抄数。

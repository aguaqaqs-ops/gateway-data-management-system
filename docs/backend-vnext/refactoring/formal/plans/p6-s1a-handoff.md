# Phase 6 S1a handoff

## 阶段结果

S1a 产品候选为 `af559ae3d274e3e9df687b448edd331cdc6d7412`（分支 `p6-s1a-impl`）。此前该候选上的实现与验收已收敛；本次新增的归因计时只存在于独立诊断分支 `p6-s1a-timing-diag`，不合入候选。诊断分支 HEAD 为 `e52ad2c48b7c28137bc7f135b89b2da22f467947`，仅加结构化计时日志；计时不记录行值、SQL 值、表内容或其他数据值。

本 handoff 是候选 `af559ae3` 的阶段交接文档，文档提交不改变候选产品代码。没有推送或打 tag。

## S1a Contract、实现与 golden

- 每表存储摘要统一为 `raw_content_digest`，`STORAGE_PROJECTION_VERSION` 为 `"3"`；删除 `ordering_digest` 及 `infrastructure/repository_write/import_publication.py` 中的传递，删除重复摘要计算。按 DC58 删除 `fast_row_digest` 的计算、字段、checkpoint/manifest 序列化和 Contract 条文。
- Snapshot digest 每表只输入无需读取行即可获得的事实：表名、比较 schema 摘要、业务 schema 摘要、比较键、行数、表摘要。Repository 侧 row-free 描述和 rowful 描述同算法、逐字段相同；Preview 基线、History 两侧、上传侧共用算法，不用提交元数据的 `snapshot_digest` 代替计算，也不在 `CanonicalBinding` 中保留该字段。
- `raw_state_digest_of` 保留。它仍被 snapshot materialization 与 Repository reference materialization 用于比较 schema-independent 的原始表状态，并由 composite、snapshot-summary/checkpoint codec、`preview_jobs` canonical input、repository import source/readback 校验消费。该摘要刻意不含 schema，与规范状态摘要语义不同；有独立生产使用方，删除会改变这些 Contract/校验职责。
- Preview 与 History 按完整表摘要、schema digest、storage view、投影版本判定未变化。Preview 未变表不读基线行、不比较行。History 未变 ordered 表以当前侧规范行、由两侧描述符构造本次有效 pair 策略计算逻辑摘要和 occupancy；使用规范 provenance、按既有结构填充 facts、保留 degraded 语义，没有复用 `_compare_single_side`。变化表与删除表通过 Repository Service 逐表读取基线行。
- Submit 生产 policy 为 `ADAPTIVE_PATCH`；`GID_NO_V1` ordered 表允许行级修改；parent 行通过 Repository Service 路径读取并按 parent manifest 校验；prepare checkpoint 绑定 parent manifest digest；包 manifest 仍列出全部表。阈值和批规则见下节。
- Contract 直接改到目标形态：Canonical Storage、Storage Mutation、Ordered Diff、ADR 0014 生产路径、ADR 0019 说明、snapshot materialization 文档及 control DB 基线 schema。未增加兼容层、双读写或旧字段别名。
- Golden 变化仅限 S1a 范围的 23 个 fixture：`mutation` 12 个、`snapshot-materialization` 5 个、`storage-projection` 6 个。原因是表摘要、投影版本、移除 fast/order digest 与 mutation SQL 形态变化。导入包 golden 字节不变；其余 comparison/risk/surface/bundle fixtures 未新增或修改。没有 S1a 范围外的 golden 变更。

## 基线行消费者盘点

| 消费者 | 跳过未变表的处理 | 对应测试/覆盖 |
| --- | --- | --- |
| Preview 基线物化与行比较 | 逻辑需求为 `X∪D`；未变/新增表不读取旧行，仍从 catalog/manifest 得到全表身份摘要。 | `test_unchanged_preview_table_does_not_read_baseline_rows`、`test_preview_reads_changed_and_deleted_baseline_tables_only`、`test_requested_tables_only_open_selected_rows_and_keep_full_catalog_summary`。 |
| 项目身份评估 `version_manager` | 未变表复用当前侧规范行；变化表保留旧行读取。 | `test_unchanged_identity_table_reuses_current_rows_without_baseline_read` 与 changed/deleted 选择测试。 |
| Composite signal | 未变表使用当前侧规范表；变化/删除服从普通 selector，没有始终读取旧 composite 的旁路。 | `test_full_materialize_publishes_checkpoint_and_assemble_successor`、`test_missing_logics_xml_materializes_stable_empty_source`、t4 History 旅程。 |
| History 变化表行比较 | 未缓存的 X 需要 old-X 与 current-X；按 `(commit, 内容身份)` 合并去重。 | `test_changed_history_table_reads_both_pair_sides`。 |
| History 未变 ordered 单侧摘要 | 使用当前侧规范行，pair 策略仍从两侧描述符构造；规范 provenance/facts/degraded 行为保留。 | `test_unchanged_ordered_history_reads_current_side_and_preserves_facts`。 |
| History 删除表 | D 仍读取旧侧规范行，供整表浏览、导出与风险。 | `test_deleted_history_table_reads_only_the_old_pair_side`。 |
| `DATASET_REPLACEMENT` | 未变表复用当前 artifact；变化/删除表按替换所需读取旧侧。 | `test_dataset_replacement_reuses_current_artifact_for_unchanged_table`。 |
| checkpoint 与恢复 | 已发布 checkpoint 含物化侧 artifact，恢复 assemble 直接读 checkpoint；checkpoint 缺失才按 selector 重做必要读取。 | `test_assemble_resumes_from_checkpoint_when_repository_is_unavailable`、`test_assemble_resumes_from_materialized_sides_with_runtime_ruleset`、`test_full_materialize_publishes_checkpoint_and_assemble_successor`。 |
| Submit parent 行校验 | 独立于 Preview/History 的未变过滤，只读取需 mutation 的变化表并验证 parent manifest。 | `test_repository_base_digest_reaches_mutation_planner` 及 Submit prepare/recovery focused tests；t4 v2 parent rows 经 RS 产品路径成功读取。 |
| 规则/catalog 绑定 | 只读 catalog、描述符、provenance、规则，不消费 baseline snapshot rows。 | projection 与 ruleset focused tests。 |

盘点未发现需要修改 §4.2 规则或 §16.2 计数口径的消费者。

## 计数断言与保值

设计 §16.2 计数在 focused 测试中按公式成立，覆盖手算示例、边界、表添加/删除及跳过表发布：

- Preview：基线逻辑读取需求 `X∪D`，实际读取不超过 `|X|+|D|`；行比较派发数 `=|X|`；表级处理数 `=|A|+|D|`；kernel 调用不超过 `|X|`。
- Submit：表级计划为 `X∪A∪D`；净行变更计数遵守 key 变化计 DELETE+INSERT；重建写入 target 行数；删表 DROP 一次且写入零行。
- focused 断言：`test_submit_count_examples_match_hand_computed_net_changes`、`test_submit_table_level_counts_for_added_and_deleted_tables`、`test_threshold_boundary_cases`、`test_skipped_table_does_not_break_publication`。Preview 另有上表的 baseline read/selector 断言。
- `55363b37e1` 上较早 focused 记录：05，149 passed / 50 deselected，16.56 秒，日志 `/home/dev/gdds-p6-logs/s1a/05-focused-55363b37e1-20261026.log`。DC58 最终 focused 在 05、HEAD `af559ae3`，backend 462 passed；另有 Ruff 与 backend/repository_service mypy 通过，日志 `/home/dev/gdds-p6-logs/s1a/05-dc58-final-focused-af559-20261027.log`。

保值核对：规范状态摘要、snapshot digest、bundle digest、ordered 逻辑摘要、occupancy 摘要、comparison records/facts、risk、surface、bundle 内容及 HTTP DTO 均未观察到非预期变化；DC58 摘要字段按设计更新。golden 仅改变本阶段指定的三组。t1–t4 业务 journey 中 Preview/History 与 Submit 结果符合候选 Contract。重复 Submit 都没有 Repository operation：`NO_CANONICAL_CHANGE`。

## Dolt 语句预检、阈值与表哈希

- 预检节点 `ct108-gw-dms-05`（hostname `gw-dms-test-05`），Dolt `2.1.11`，HEAD `ec689eda0aa520050fdf1f01a35422adc7e281d5`，2026-10-26T23:59:29Z–2026-10-27T00:00:24Z，exit 0。日志 `/home/dev/gdds-p6-logs/s1a/05-dc57-preflight-ec689eda0a-20261027.log`，报告 `/home/dev/gdds-p6-logs/s1a/05-dc57-preflight-dolt-ec689eda0a/report.json`。
- 合成表覆盖单列主键、复合主键、ordered `GID_NO_V1`（gid 为存储键）。对按批 DELETE+INSERT、upsert+DELETE、生产候选 CASE UPDATE+DELETE+多值 INSERT 逐类验证语法、主键查找计划、与逐行形式相同的表哈希及同键行在 `dolt_diff` 中显示 modified。该 Dolt CLI 的经典 DML `EXPLAIN` 输出为空，使用等价主键谓词的 `EXPLAIN ANALYZE SELECT` 验证索引查找而非全表扫描。
- 冻结阈值：仅当变化行数 `<= 1,000` 且 `变化行数 / max(before_rows, after_rows, 1) <= 1%` 时使用 PATCH_DML，否则重建表。INSERT、UPDATE、DELETE 每批最多 256 行且 SQL 不超过 4 MiB，任何上限先到即拆批。规划器逻辑和 §16.2 计数不变。
- 正式阈值复测：ct108、Dolt 2.1.11，候选 `af559ae3`，2026-10-27T06:45:15Z–07:16:22Z，exit 0。日志 `/home/dev/gdds-p6-logs/s1a/ct108-af559-mutation-replay-20261027.log`，JSON `/home/dev/gdds-p6-logs/s1a/ct108-af559-mutation-replay-20261027.json`。所有回放在 Dolt 仓库副本进行；parent rows 经 RS HTTP Arrow 产品路径读取，`repository_main_unchanged=true`。
- 1% 样本 `b1_n11_iec104_syx_list`：parent 9,822、target 9,828；98 个合成净变化（0.99715%，92 UPDATE + 6 INSERT），patch/rebuild 交替三轮。中位数分别 0.605835s / 1.235459s，三轮每次表哈希相同；patch 快约 51%。
- 1,000 行附近：同表 1,000 个合成变化、变化率 10.175%，超过比例门槛，ADAPTIVE_PATCH 选择重建；adaptive / full rebuild 分别 1.277966s / 1.252483s，哈希一致。
- t4 v2 全表：27 张 `X∪D` 表，目标 312 表。按批 ADAPTIVE_PATCH 与全表重建结果 312/312 表哈希相同；耗时 2.514646s / 27.384033s。Adaptive 计划重建 15 表，行级操作 21,974 DELETE、22,054 INSERT、84 UPDATE；整表重建写入 246,874 行。批量合成样本证明 256 行/4 MiB 上限下批量语句远快于逐行执行，近 4 MiB 样本 4,194,048 字节。

## 候选 `af559ae3` 的 t1–t4 真实旅程

以下均为完整旅程、同一候选 HEAD；真实数据未进入 Git。日志记录节点 hostname、HEAD、时间与 exit。t4 测量期间独占 ct108。所有阶段结果 PASS。

| 档位 | 节点；UTC 起止；exit | 结果摘要 | 日志 |
| --- | --- | --- | --- |
| t1 | 05 (`gw-dms-test-05`)，05:22:37–05:27:38，0 | v1 Preview 42.161s、Submit 42.190s；重复 Preview 32.118s（0/125 changed）；重复 Submit 无 Repository operation；v2 Preview 38.140s、Submit 42.189s；History 22.071s。 | `/home/dev/gdds-p6-logs/s1a/05-af559-t1-candidate-journey-20261027.log` |
| t2 | 05，05:31:02–06:06:07，0 | v1 Preview 433.540s、Submit 182.801s；重复 Preview 222.789s；v2 Preview 377.328s（57/220 changed）、Submit 343.484s；History 282.825s。 | `/home/dev/gdds-p6-logs/s1a/05-af559-t2-full-journey-20261027.log` |
| t3 | 05，06:37:56–07:47:06，0 | v1 Preview 732.534s、Submit 351.515s；重复 Preview 531.860s；v2 Preview 858.991s（54/193 changed）、Submit 564.403s；History 563.617s。 | `/home/dev/gdds-p6-logs/s1a/05-af559-t3-full-journey-20261027.log` |
| t4 | ct108 (`gw-dms-test`)，05:10:27–06:40:01，0 | source 320 tables / 437,149 rows，canonical 312 tables；v1 changed 312、degraded 0；重复 v1 Preview 0/312 changed、重复 Submit 无 Repository operation；v2 changed 26/312、degraded 0；History 168 records，composite signal 435 rows。正式候选耗时：v1 Preview 1503.877s、Submit 561.741s；重复 Preview 852.508s；v2 Preview 989.222s、Submit 287.924s；History 310.876s。 | `/home/dev/gdds-p6-logs/s1a/ct108-af559-t4-full-journey-20261027.log` |

V5b 六段测量在同一候选 `af559ae3`、ct108 完成，2026-10-27T07:17:34Z–07:55:56Z，exit 0：`/home/dev/gdds-p6-logs/s1a/ct108-af559-v5b-segments-20261027.log`，JSON 同名 `.json`。v1 full baseline 312 tables / 246,794 rows，materialize 276.855s，其中 Repository 57.474s、Python materialize/digest 211.805s；v2 selected baseline 27 tables / 139,838 rows，69.485s，其中 RS 9.934s、Python remainder 58.729s。v1 pair pipeline 500.863s、record closure 318.699s、读回 98.506s、bundle 43.284s；v2 分别 38.223s、1.073s、0.098s、2.004s。Submit build-input 仍需对冻结 312 表做验证；该项不是 Preview/History 的未变表读取。

## 诊断分支：计时范围与代码边界

诊断分支以 `af559ae3d274e3e9df687b448edd331cdc6d7412` 为基点。分支提交：

- `8f429a18bef832dc4a66ea62384810120d500c09`：计时插桩；
- `2e2289bad54237e2cae1d31549776d93974d837c`：Ruff 修正；
- `e52ad2c48b7c28137bc7f135b89b2da22f467947`：strict mypy 修正，诊断 HEAD。

相对候选的 diff 文件清单（共 9 个，均在 backend）：

1. `vnext/backend/src/gateway_backend/application/pair_pipeline.py`
2. `vnext/backend/src/gateway_backend/application/preview_jobs.py`
3. `vnext/backend/src/gateway_backend/application/submit_jobs.py`
4. `vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_assembly.py`
5. `vnext/backend/src/gateway_backend/capabilities/comparison/artifacts.py`
6. `vnext/backend/src/gateway_backend/diagnostic_timing.py`（新文件）
7. `vnext/backend/src/gateway_backend/infrastructure/repository_write/import_publication.py`
8. `vnext/backend/src/gateway_backend/operations/lease_session.py`
9. `vnext/backend/src/gateway_backend/operations/worker_runtime.py`

未改测试、RS 源码、Dockerfile、锁文件、design/plan/decision 或 golden。时间围栏只包围既有阶段调用，额外计数只记录阶段名、行/表/artifact 数和耗时；未改变 policy、分支条件、事务边界、输入/输出或 Repository 行为。少量空白/导入顺序和把原表达式移入局部变量以围住计时范围。调试节点 05（`gw-dms-test-05`）上 Ruff 与 strict mypy 均通过，2026-10-27T10:17:41Z–10:18:20Z，日志 `/home/dev/gdds-p6-logs/s1a/05-timing-diag-ruff-mypy-e52ad2-20261027.log`（487 files）。诊断分支未合入，分支提交均带要求的 Co-Authored-By trailer。

## 计时诊断旅程与逐项归因

ct108 上以 e52ad2 新起隔离 Compose 项目 `p6-s1a-timing-e52ad2`；旧 `p6-s1a-af559-t4` 未改动。backend 镜像由诊断 HEAD 构建，Repository Service 镜像沿用候选 RS 源码。无 py-spy 附着的完整 t4 诊断旅程：hostname `gw-dms-test`，2026-10-27T10:24:18Z–11:53:26Z，HEAD e52ad2，exit 0，`conclusion=PASS`；日志 `/home/dev/gdds-p6-logs/s1a/ct108-timing-diag-full-t4-e52ad2-retry2-20261027.log`。初始 launcher 两次在 Compose 前失败，不是旅程证据，见过程记录。

该诊断旅程 v1 Preview 1503.917s、v1 Submit 565.788s、重复 v1 Preview 852.507s（0/312 changed）、v2 Preview 987.186s（26/312）、v2 Submit 289.944s、History 310.881s（168 records）。正式候选的耗时以 `af559ae3` 的上表为准；此诊断只用于归因。脱敏证据：worker timing `/home/dev/gdds-p6-logs/s1a/ct108-timing-diag-worker-e52ad2-20261027.log`，RS summary `/home/dev/gdds-p6-logs/s1a/ct108-timing-diag-rs-summary-e52ad2-20261027.log`，control DB 时间线 `/home/dev/gdds-p6-logs/s1a/ct108-timing-diag-control-timeline-e52ad2-20261027.log`。

| 项目与来源 | 实测与计数 | 削减方向；处理阶段；owner |
| --- | --- | --- |
| v1 Preview `materialize_inputs`，上传包 SQL/business/canonical stages | worker 765.659s；上传侧 764.832s、312 canonical tables / 246,794 rows。SQL parse 174.973s / 79,446,967 bytes；business snapshot 238.008s / 320 tables / 437,149 rows；canonical projection 143.627s / 312 tables；canonical snapshot 207.326s / 312 tables；包 staging 0.636s、XML parse 0.074s、baseline rows 0.116s、publish manifest 0.135s。 | 这解释 Preview materialize 的主要时间；与 S1a baseline skip 无关。后续性能阶段优化 parser/materialization 的多次全表遍历和摘要生成；阶段 S2b/S3；owner 为 backend ingestion 与 canonical snapshot/compute owner。 |
| v1 assemble checkpoint read | 45.110s，读 3 sides / 312 table summaries。 | checkpoint 中重复/宽描述的读写及解码可在后续存储阶段压缩/按需加载；阶段 S1b/S2b；owner 为 backend artifact/checkpoint owner。 |
| v1 pair comparison（约 180s 残差） | `preview.pair.compare` 184.992s，312 comparison tables；这是旧分段汇总未单独归出的约 180s 主要来源。整个 pair pipeline 625.544s，其中 record closure 生成 397.315s（223 record entries / 250,470 records；standard 218.267s、ordered 177.884s）、risk 42.423s、surface assembly 0.405s。 | 比较是计算主项，优化算法和批处理；记录 closure 的序列化/写入需流式或降低重复物化。阶段 S3 comparison/compute 与 S1b artifact output；owner 分别为 comparison kernel 与 backend artifact owner。 |
| v1 bundle 与 assemble 收尾 | bundle 总 51.393s；其内部 plan/read source 23.370s（1,071 artifacts / 82,781,386 bytes）、publish 13.369s（1,074 artifacts / 86,083,925 bytes）、readback validation 1.101s；ready closure 0.503s（1,618 artifacts）、state artifact 0.061s、checkpoint prepare 0.011s。`assemble_preview` 全 step 723.046s。 | 减少 artifacts 的重复扫描/读回，批量或流式发布；阶段 S1b；owner 为 bundle/artifact owner。DB publish 操作本身低于 0.1s，不是残差来源。 |
| v2 Preview assemble（约 72s 残差） | 全 step 111.196s；checkpoint read 58.656s（3 sides / 936 side-table descriptors）；pair pipeline 49.335s，其中 compare 47.158s、records 1.160s、risk 0.342s，surface 0.325s；bundle 2.442s，ready/state/checkpoint 合计约 0.27s。相对 V5b 的 38.223s pair pipeline，残差约 72s 可分解为 checkpoint 58.656s、诊断运行中约 11s 的 pair pipeline 增量与约 2–3s 收尾。 | 主要收益来自 checkpoint 不必反复读三侧全描述；次要是 comparison。阶段 S1b checkpoint/storage 与 S3 comparison；owner 为 backend artifact/checkpoint 与 comparison kernel owner。 |
| v1 Submit `prepare_import` | 469.094s；打开 312 表冻结投影输入 44.637s；建 frozen projection 39.231s；build after snapshots 82.731s；parent rows 0；plan/render mutations 299.196s（312 changed / 312 rebuild）；package publish 0.354s，包 2,363,395 bytes。 | 大头是整表级 projection/snapshot 与 312 表计划/渲染。ADAPTIVE_PATCH 的变化表实测已在 S1a 验收；后续降低冻结输入重复读和投影物化成本，阶段 S2b；owner 为 Submit/backend mutation 与 snapshot owner。 |
| v2 Submit `prepare_import` 中约 36s 的部分 | prepare 全 step 212.327s；打开 312 表输入 45.201s，build 27 个变化表 frozen projection 10.571s、after snapshots 27.447s；通过 RS 读取 25 表 / 129,426 rows 的 parent rows 90.520s；plan/render 36.357s（27 changed / 15 rebuild）；其余 canonicalize/DB/publish 为亚秒级。 | 36s 被 mutation plan/render 明确定位；继续优化渲染的算法与按表批处理，阈值已冻结，不改变判定。90.520s parent rows 是必要的 RS product read，可优化 Arrow 流吞吐/关闭开销但不能绕过 RS 或削弱 parent manifest 校验；后续性能阶段 S2b；owner 为 mutation renderer 与 Repository Service。 |
| Submit 到 Repository operation | v1 `submit_import` worker 0.270s，RS POST 约 0.035s；await 先 `repository_wait` 60.001s timeout，随后重试等待 0.431s（第二 attempt 的 worker 时间 0.533s），checkpoint/DB 读取与终态写入合计几十 ms。v2 `submit_import` 0.244s，await `repository_wait` 49.706s。RS cgroup CPU 分别约 179.458s / 183.478s，耗时主要是 RS/Dolt 异步导入回放，worker 在等待。 | 异步回放自身由 Repository Service/Dolt owner 优化；worker await 按当前 retry/lease Contract 工作，不为了缩短数字而放宽成功/恢复语义。后续 RS 性能阶段；owner 为 Repository Service/Dolt。 |
| step 领取、执行开始、完成及相邻 step 间隔 | claim SQL 约 19–40ms（首个 26.330ms），claim 后 execution start 约 2–3ms。常见 step 完成至下一个执行开始为 2.6–9.95s：例如 v1 materialize→assemble 4.88s、assemble→publish 7.65s、prepare→submit 9.95s、submit→await 9.73s；v2 各相邻步骤约 8.7–9.75s；History materialize→assemble 约 8.1s、assemble→publish 约 8.3s。 | 已定位到 `WorkerRuntime._run_claim`：非 drain 路径等待 `_wait_interruptibly(timeout, ...)` 至下一 heartbeat（默认约 10s），等待不观察 executor 的 `completed` event，因此完成后仍可能等到 timeout。后续 worker runtime/performance 阶段让 executor 完成可唤醒 supervisor，同时保留 heartbeat/drain/lease 语义；owner 为 backend Worker Runtime/Operations。 |
| Submit 后长间隔、History 前长间隔与 harness polling | v1 await 后到下一操作约 79.6s，其中另行经 RS 产品路径做 v1 repository row verification 75.197s；v2 对应约 78.3s，其中 row verification 76.372s、approval 0.674s及 harness 调度约 1s。`real_dump_journey.py::_poll_operation` 每次 2s 轮询，最多带来约一个轮询周期的结果发现延迟。 | 大间隔是验收 harness 明确发起的 Repository row verification，不是 worker step 空转；保持验证时，可把这部分移出 operation elapsed 的展示口径但不可省略校验。阶段 benchmark harness；owner 为性能测量工具 owner。2s poll 仅是可选的 harness 响应优化。 |
| Control DB 与 RS read-stream 诊断 | heartbeat 每约 10s 一次，单事务约 0.15–0.20s；各 job 累计 3.3–25.3s 且与 executor 并行。RS summary 有 37 条 Arrow bridge worker 30s join timeout warning；相关 rows HTTP 请求均为 200（526 请求），旅程与 History 成功。警告来自 `arrow_bridge.py::_await_close_outcome` 达到 30s join timeout 后的 warning/owned stream terminate 路径；没有按 request 记录的 duration，无法把 37 次相加为 wall-time。 | heartbeat DB 不解释 residual，不建议削弱 lease。Arrow warning 是已定位的 stream close 性能问题，不是请求中止或表特异错误；精确并发占比需 RS 单请求关闭阶段计时。阶段 Repository Service 后续性能诊断；owner 为 RS owner。S1a 没改 RS 路径。 |

step 切换间隔与 harness 的 2s poll 已按 control DB/worker/RS 时间线区分。v1 与 v2 的 assemble/prepare 残差均有可定位阶段；本诊断没有遗留未定位的 S1a 阻断项。RS 37 次 close warning 的精确 wall 占比未量化，列为后续 RS 性能诊断，不与已解释的 assemble 残差混算。

## 权威 runner 与容器门禁

- ct108-gw-dms-04（hostname `gw-dms-test-04`）在候选 `af559ae3d274e3e9df687b448edd331cdc6d7412` 的 clean、已提交 detached worktree 中重建 repository-service 镜像，DC48 环境下六包权威 runner exit 0。时间 2026-10-27T05:04:39Z–05:43:18Z；日志 `/home/dev/gdds-p6-logs/s1a/04-af559-six-package-runner-20261027.log`。六包逐包结果：Rust fmt/clippy/test 通过；shared_kernel 242 passed；repository_contracts 152；repository_client 154；backend parallel 2,940 + serial 39 passed；repository_service parallel 1,741 passed / 1 skipped + serial 206 passed。runner 起止 HEAD 均为 af559，worktree clean。
- repository-service 镜像构建日志 `/home/dev/gdds-p6-logs/s1a/04-af559-rs-image-20261027.log`，runner_exit 0；revision af559，image ID `sha256:14c4dde24fa90208869cf442f52ab381532efa6c277963bbbbba8b3cc6e94ee9`，source-tree `sha256:fddb1e93...`。RS 源码在诊断分支未变化，因此诊断 Compose 沿用该 RS 镜像；诊断 backend 镜像由 e52ad2 单独构建，记录见 `/home/dev/gdds-p6-logs/s1a/ct108-timing-diag-image-build-e52ad2-20261027.log`。
- 04 门禁 detached worktree 保留到阶段 exit 合入之后（DC51）。诊断 branch 未做 runner，不属于 S1a 产品候选或 runner 证据。

## 过程记录

- 较早 History digest 停止发生在 `8e64af7`；DC58 决定 row-free snapshot identity 后已在 af559 修正，最终候选 focused 与旅程均通过。历史日志在 `/home/dev/gdds-p6-logs/s1a/04-focused-history-digest-debug3-8e64af7ca4-20261027.log`。
- run3/run4 Arrow stream 中止根因为旧测量工具以 root 经 `docker exec` 改写 RS 正在服务的 Dolt 仓库文件，造成文件属主与 gateway euid 不一致；修复后回放只在 scratch 仓库副本进行，parent rows 经 RS 产品路径。旧测量日志保留在 `/home/dev/gdds-p6-logs/s1a/`，复测成功记录见 `ct108-af559-mutation-replay-20261027.log`。
- 早前 py-spy 附着探测没有形成可用剖析证据（权限/目标识别探测未能得到 profile）。按 owner 新授权改用独立诊断分支的结构化阶段计时；没有用剖析耗时替代正式 t4 证据。
- e52ad2 首次 journey launcher 因 uv script path 和 shell quoting 在 Compose 前失败；修正后 retry2 的完整旅程 exit 0。日志：`ct108-timing-diag-full-t4-e52ad2-20261027.log`、`...retry1-20261027.log`、`...retry2-20261027.log`。最终 candidate 的 S1a 验收仍以 af559 对应的正式 runner、t1–t4、V5b 与阈值测量为准。

## 需要 owner 后续清理的内容

以下对象均保留，按 owner 的清理决定与 DC51 时点处理。本次未停止或清理栈、volume、bundle、ref、scratch。需如实记录：重写本 handoff 时补丁工具先移除了旧 handoff 文件，再添加最终文档；除此之外未执行文件清理。

### py-spy 与诊断日志/临时文件

- ct108 仓库外工具目录：`/home/dev/gdds-p6-logs/s1a/py-spy-042-tool/py-spy`、`py-spy-tool/py-spy`、`py-spy-bin/py-spy`、`py-spy-042-bin/py-spy`。
- profile、pid 与探测日志：`/home/dev/gdds-p6-logs/s1a/ct108-af559-pyspy-*`，含 speedscope JSON；保留的诊断 worker/RS/control 时间线见上文。
- 诊断 Compose override、resolved Compose、launcher：`compose-timing-diag-port-20261027.yaml`、`compose-timing-diag-resolved-20261027.yaml`、`run-t4-timing-diag-20261027.py`，均在 `/home/dev/gdds-p6-logs/s1a/`。
- t4 real-dump state/output：`/home/dev/gateway-real-dumps/runs/p6-s1a-*`，包括 `p6-s1a-timing-e52ad2/t4.state.json`；不得纳入 Git。

### Compose stacks 与 volumes

各项目的三个 volume 后缀均为 `backend-artifacts`、`backend-control`、`repository-service-data`。现有容器/volumes 保留：

- ct108 仍运行：`p6-s1a-timing-e52ad2`（本次诊断栈）与 `p6-s1a-af559-t4`（正式候选栈）。
- ct108 profiler A/B 停止但保留：`p6-s1a-af559-t4-prof-20261027-a`、`p6-s1a-af559-t4-prof-20261027-b`。
- ct108 其他保留栈：`p6-s1a-final-t4-retry-8e64af7ca4`、`p6-s1a-t4-97a4f5c`、污染后停止的 `p6-s1a-t4-clean-55363b37`、`p6-s1a-t4-measure-085b54ffdc`。
- ct108 已退出的回放容器与副本：`p6s1a-dolt-replay-654f114f5c80`、`p6s1a-dolt-replay-25d56605b4d8` 及各自 scratch。
- 05 已退出：`p6-s1a-af559-t1`、`p6-s1a-af559-t2`、`p6-s1a-af559-t3`、`p6-s1a-base-t1-5a2989`、`p6-s1a-final-t1-retry-8e64af7ca4`、`p6-s1a-final-t2-retry-8e64af7ca4`、`p6-s1a-final-t3-retry-8e64af7ca4`、`p6-s1a-t3-55363b37`。
- 04 当前没有 S1a Compose stack/volume；保留其 gate worktree。

### Worktrees、branches、bundles 与 refs

- 开发主机 worktrees：`/home/dev/gateway-data-management-system`（当前主 checkout）、`/home/dev/gdds-p6-logs/s1a/impl-wt-553`、`/home/dev/gdds-p6-logs/s1a/timing-diag-wt`。impl worktree 保留当前 handoff 提交；诊断 worktree/branch 不合入。另有原并行 S1a task worktrees，按下面各节点清单处理。
- 04 worktrees：`04-final-wt-10753e7e5c`、`04-final-wt-8e64af7ca4`、`04-wt-55363b37`、`04-wt-6ea89b1c`、`04-wt-97a4f5c`、`final-af559-wt`。门禁 worktree 按 DC51 留到阶段 exit 合入后。
- 05 worktrees：`05-dc57-focused-wt-cbe32df8bb`、`05-dc57-preflight-wt-6c770d963b`、`05-dc57-preflight-wt-7b552981f8`、`05-dc57-preflight-wt-ec689eda0a`、`05-dc58-focus-wt-030e`、`05-final-wt-10753e7e5c`、`05-final-wt-8e64af7ca4`、`05-focus-wt-ac73504ad8`、`05-focused-wt-085b54ffdc`、`05-static-wt-04124576`、`05-static-wt-04dd7c3b78`、`05-static-wt-749e9bb5df`、`05-static-wt-f3e7fe7c74`、`05-wt`、`05-wt-10d21c0`、`05-wt-26b8db7`、`05-wt-2a7ad7b`、`05-wt-3332606`、`05-wt-478fa4d19b`、`05-wt-6ea89b1c`、`05-wt-7f43d2e`、`05-wt-97a4f5c`、`05-wt-a6938`、`05-wt-d05a29f646`、`05-wt-d84c2a7`、`05-wt-e868b1ad`、`05-wt-efd4b88`、`base-5a2989-wt`、`final-af559-wt`、`timing-diag-wt-2e2289`、`timing-diag-wt-8f429`、`timing-diag-wt-e52ad2`。
- ct108 worktrees：`ct108-final-wt-10753e7e5c`、`ct108-final-wt-8e64af7ca4`、`ct108-measure-wt-04dd7c3b78`、`ct108-measure-wt-085b54ffdc`、`ct108-measure-wt-48cb02c5`、`ct108-real-wt-55363b37`、`ct108-wt`、`ct108-wt-55363b37`、`ct108-wt-97a4f5c`、`final-af559-wt`、`timing-diag-wt-e52ad2`。
- 分支/ref：保留 `p6-s1a-impl` 与 `p6-s1a-timing-diag`（含各节点的分支/commit refs）及由 S1a linked worktrees 建立的 `p6-s1a-*` refs；不移动或删除。
- 主 checkout bundles：`.p6-s1a-10d21c0.bundle`、`.p6-s1a-26b8db7.bundle`、`.p6-s1a-2a7ad7b.bundle`、`.p6-s1a-3332606.bundle`、`.p6-s1a-7f43d2e.bundle`、`.p6-s1a-97a4f5c.bundle`、`.p6-s1a-a6938cd.bundle`、`.p6-s1a-d84c2a7.bundle`、`.p6-s1a-efd4b88.bundle`；`.p6-s1a-a6938cd.bundle` 的 05 日志目录副本也保留。
- `/home/dev/gdds-p6-logs/s1a/` 内所有 `*.bundle` 均列入清理候选，包括 `55363b37e1.bundle`、`af559-s1a-candidate.bundle`、`e868b1ad47.bundle`、所有 `impl-*`、`p6-s1a-candidate-*`、`p6-s1a-impl-*` 与 `p6-s1a-timing-diag-{8f429,2e2289,e52ad2}.bundle`。不得因本 handoff 提交而删除。

### Dolt refs 与 scratch

- 正式复测 refs：`p6s1a-measure-t4-v2-adaptive-4aa81c6c`、`p6s1a-measure-t4-v2-full-rebuild-d8051f1c`、`p6s1a-measure-one-percent-patch-5ca1060d`、`p6s1a-measure-one-percent-rebuild-f6b95153`、`p6s1a-measure-one-percent-patch-03104a47`、`p6s1a-measure-one-percent-rebuild-33260200`、`p6s1a-measure-one-percent-patch-a68c2883`、`p6s1a-measure-one-percent-rebuild-d94da7c8`、`p6s1a-measure-one-thousand-row-adaptive-464fa520`、`p6s1a-measure-one-thousand-row-rebuild-38ea0ee6`。
- 更早测量 refs：`p6s1a-measure-t4-v2-adaptive-9b743a3d`、`p6s1a-measure-t4-v2-full-rebuild-29ac9934`、`p6s1a-measure-one-percent-patch-2d2aa789`、`p6s1a-measure-one-percent-rebuild-d6744040`、`p6s1a-measure-one-percent-rebuild-48bb801d`、`p6s1a-measure-one-percent-patch-3b78d6bb`、`p6s1a-measure-one-percent-patch-7fae7b47`、`p6s1a-measure-one-percent-rebuild-92f23a4e`，以及批量预检 synthetic refs 与 scratch copy 内全部 Dolt refs。
- scratch：`af559-dolt-batch-preflight`、ct108 `ct108-af559-mutation-replay-scratch-20261027`、V5b scratch、Dolt replay copy；所有相关日志、JSON、profiling artifacts 与 `/home/dev/gdds-p6-logs/s1a/` 内其他 S1a 证据文件保留。

清理均留待 owner。该 handoff 不授权清理或改写阶段 refs。

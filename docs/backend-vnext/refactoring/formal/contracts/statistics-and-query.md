# 基础统计与只读查询 Contract

Owner：backend statistics；RS feed owner：Repository Service。版本：1。状态：S1b 实施。
依据：[详细设计](../plans/p7-s1b-statistics-and-query-design.md)、[实施计划](../plans/p7-s1b-execution-plan.md)。

统计是可丢失、不可重建历史的 derived data，不进入业务 digest、事务、lease、CAS、保护或恢复判定。
业务回调只 nonblocking offer 有界标量，普通统计 Exception 不改变业务控制流；编码、SQL、扫描由后台完成。
本阶段默认 N=1，无新服务、UID、outbox、ack、兼容数据路径或自动 migration。

## 身份、结构和公开边界

环境和组来自已加载 DeploymentConfig。每次进程启动新建 process_instance_id；worker_id 是既有 worker 身份。
执行窗口键 `(operation_id, step_id, claim_version)`，claim_version 固定取 claim 时 StepRecord.optimistic_version，
不能随着 heartbeat 更新。attempt_count 不是窗口唯一键；健康 handoff 可在同 attempt 下再次 claim。
submit_attempt_id 仅关联 SubmitAttempt，不能充当执行键。时间为 INTEGER UTC 微秒，耗时为单调时钟毫秒，
CPU 为微秒，空间/I/O 为 bytes，count 为非负整数；净变化允许负数。未执行/无来源/丢失为 null，有效完整零才为 0。

独立库路径为 be-metadata/telemetry/statistics.sqlite3；DDL owner 为
`infrastructure/statistics/schema.py`，user_version=1，四表/索引与执行计划 §4 一致。
category固定为repository/durable/canonical/comparison/export/scratch/metadata/public_unknown/filesystem。
filesystem记录repository_id为null、filesystem_id非空、object/logical/allocated/unverified_reference字段为null；
其他类别的filesystem_id/total_bytes/available_bytes/available_inodes为null。
库不符/损坏只禁用统计，人工修复并重启；不自动删除/迁移，不影响 control DB 的严格校验。
首次 recorded_at_us 非空且 upsert 不刷新；end 缺 start 保持 partial，不编造时间。相同窗口只补已知字段。

`statistics/models.py` 定义固定记录和 D23 metrics；`http/schemas/statistics.py` 定义公开查询/分页/曲线 DTO。
字段不得增加自由 JSON，metrics 最多12KiB，整条事件16KiB；表数组100项，UTF-8表名256 bytes。
先保留固定标量，按现有稳定顺序放表项，超限跳过整项并设置 tables_truncated；固定字段仍超限则该 metrics
缺失且 partial/budget_exceeded。tables_total 是截断前总表项数，不能拿截断数组重新算输入规模。
API JSON 中 metrics 同对象嵌套，CSV 将同对象放标准转义 JSON 单元格。指标不复制原始 SQL/业务 payload/路径/秘密。

七个 GET 路由、分页、SQL/输出上限、导出与错误语义以实施计划 §6 为准。公开 DTO 只供已授权查询使用：
repository 三接口要求 workspace_read 和当前 enabled mapping 精确匹配；operation 两接口复用 owning read，
History 单独 read_project_history + acceptance。普通 session 的 statistics_read_group 只授组容量/服务指标，
组 DTO 无 repository/operation/表名；它不是 internal recovery bearer，不能授予恢复写入或所有设备访问权。
GET 只读已生成记录，不触发扫描/GC/配置修改。DB 正常但空返回200 not_collected；禁用/坏库503 STATISTICS_UNAVAILABLE。

RS `/v1/statistics/observations` 复用 require_bearer_token。`repository_contracts/statistics.py` 是 feed DTO owner，
现有 import/get_operation 不变。kind 是 repository_storage/write/resource/filesystem_capacity 的 discriminated union。
随机 observation_id 去重；sequence 只用于实例内临时分页，重启或环满允许丢失，reset/truncated 明示，无 ack/replay。
同 observation 后续完成以新 sequence 追加，backend 用 observation_id 补已知字段且保留首次记录时间。
参数只为 instance_id/after_sequence/limit，不接受路径或扫描指令；最多100条/1MiB，客户端读取必须有同一上限。
backend 入库前校验当前 environment/group 和 repository UUID，feed 不充当用户授权。

`StatisticsConfig` 的 GATEWAY_STATISTICS_ 前缀配置按正常重启生效；默认和上限见执行计划 §5。
2GiB 是初始工程预算，DB page上限占一半，WAL软阈值 min(128MiB,budget/16)，不是7天保证或硬配额。
E 用真实 schema 在节点测量后校准；容量压力先丢旧曲线，仍不足停新增样本，保留真实缺失，不扩大业务预算。

## D23 字段到现成来源

下面是 B/C 接线所采用的来源，均只使用调用中已有结果。未到达/未观察到的字段保留 null，不另读大对象。
路径前缀为 `vnext/backend/src/gateway_backend/`。

| 字段 | 函数、变量与固定 scope |
| --- | --- |
| table_count / total_rows / max_table_rows | `application/preview_jobs.py::_bound_from_materialization` 收到 `SnapshotMaterializationResult.summary.tables` 的 descriptors，使用 table_name、row_count；取本次当前侧（MODIFIED）的唯一输入 identity，一输入跨 pair 只计一次。History 同理取 `application/history/compare_jobs.py` 当前侧已物化描述符；catalog-only或缺完整描述符则 null。 |
| sql_bytes | Preview `_materialize_uploaded_side` 的 `staged.required_sql_document_ref.size_bytes` / 已有 `sql_bytes` 长度（`capabilities/source_package_staging/_archive.py::_single_sql_member` 已记录）；按当前侧唯一输入 identity 计一次，不算压缩包大小。History/仅 repository ref 输入无 SQL 来源则 null。 |
| changed_tables / changed_rows | `application/pair_pipeline.py` 的 pair完成路径 已有 `native_comparison.result` 中 ComparisonTableFact 的 row_added_count/row_deleted_count/row_modified_count 及 table变化事实；按已有pair/table保留计数，changed_rows为上述三类之和。只有完整比较事实才给总量；DATASET_REPLACEMENT 使用 `capabilities/comparison/replacement.py::compare_dataset_replacement` 现成 facts.summary.changed_table_count 和 facts.tables 行计数，按整表替换口径（当前所有行新增、原侧所有行删除，modified=0），不是逐行内容差异。 |
| ordered_table_rows | 同 pair 的 `ComparisonTableFact.ordered_extension` 对应 ORDERED 行数，使用当前侧已知 row_count；按当前输入/table identity 去重，不把多个pair的相同当前表相加；无法完整判断则 null。 |
| parse | Preview `preview_jobs.py::_materialize_uploaded_side` 的 `parse_arrow_sql`/`parse_xml` 调用边界；每次已执行调用 perf_counter 差累加；不包括 checkpoint restore，未解析为 null。 |
| materialize | `materialize_business_snapshot` / `materialize_canonical_snapshot` / `materialize_repository_ref` 调用边界；同窗口已执行调用累加，不含 parse；含 canonical cache 验证/恢复成本。History `application/history/compare_jobs.py::_materialize_commit` 的 `describe_repository_ref` 计入该阶段的元数据描述成本；`_ensure_history_demands` 的实际按需物化也按已有调用边界计时，不冒称 describe 已读取全表。checkpoint restore 未重新调用边界时为null。 |
| compare / risk / export | `compare_plan_native`、`evaluate_risk`和`pair_pipeline.py::_surface_table_artifacts`的现有调用边界，用finally记录单调窗口毫秒（下游阶段失败仍保留已完成耗时）。不同pair累加；export可嵌套在surface内，不把这些阶段相加冒充总执行时长。 |
| bundle | Preview `preview_jobs.py::_assemble_preview` 中已有 bundle_started 到 `assemble_bundle` 返回（导入别名指向 `application/kernel_execution.py::assemble_operation_bundle`）；History 相同 bundle builder 边界；仅发生时记录。 |
| rs_import | `submit_jobs.py` 已有 repository client submit_versioned_import/wait_operation 调用边界的客户端端到端时间（含网络/等待），只累计本窗口实际调用；健康handoff未执行的等待不伪造，绝非 Dolt 内部耗时。 |
| finalize | `application/submission/finalize.py::finalize_submit` 及调用的既有 finalize 事务边界，单调计时；仅本窗口实际执行，未执行为 null。 |
| canonical lookups/hits | `capabilities/snapshot_materialization/artifact.py::publish_canonical_tables` 现有 lookup 分支：每 key 查找一次，完成验证并实际复用 cached ref 才计 hit；不能把 restore 尝试当 hit。 |
| comparison lookups/hits | `capabilities/comparison/production.py::_compare_plan_native_once` 对每 task 的 persistent/session lookup 分支；使用同一个逐task分母，实际 `cached` 复用分支 `metrics.cache_hits` 为命中。现有 persistent_cache_lookups/cache_restores 是辅助事实，不能拿它们与混合命中构造不同scope比率。 |
| risk_candidate lookups/hits | `capabilities/risk_evaluation/persistence.py::PersistentRiskCandidates.lookup` 和 `ComparisonTaskSession` risk候选 lookup：实际每次候选查询分母，返回验证过可用 events 为hit（含会话复用），failed/无lease/解码失败非hit；关闭该层为 null。 |
| snapshot_export lookups/hits | `capabilities/snapshot_materialization/client_parquet.py::lookup_snapshot_table_parquet` 的 lookup_many 和已验证 cached 返回以及 `capabilities/snapshot_materialization/artifact.py` 的批量 snapshot 导出 lookup_many 分支；每 key 计一次，验证后实际复用才是hit，外层返回不重复计。 |
| tables | `ComparisonTableFact.table_name`、现有 request.pair_id/request.mode.value、前后描述符 row_count、上面三类变化行和；不重读表。按现有pair/table稳定顺序保留，超条目/字节设置截断。 |

阶段 scope 为单 claim 窗口，嵌套不作总耗时，cache lookups/hits 也是同窗口同层。
未观察层为 null；完整已观测而查找/命中为零可填0；只有分母>0且范围相同才由客户端算命中率。
迁出 `s3_pair_metrics` 时 B 删除旧临时日志，不解析业务日志作来源。

## 占用候选的封闭来源

只按 enabled provisioned_scope_mappings 的 repository 分页读取，短事务后 stat，单轮有限去重
(service_owner,artifact_id)，上限10000；无可靠归属进public_unknown。C 不递归探索任意业务 JSON。

| 来源 | 结构字段与已有 decoder |
| --- | --- |
| canonical_table_cache | artifact_id/media_type/size_bytes/raw_sha256，`sqlite_canonical_tables.py` 当前行解码；repository 关联直接用 canonical_table_cache.repository_id；canonical_commit_tables 仅是用途关联，不重复计量。 |
| snapshot_table_export_cache | artifact_id/media_type/size_bytes/raw_sha256 + repository_id；`sqlite_snapshot_export_cache.py` 既有cache行构造 ArtifactRef。 |
| computation_cache_entries | manifest_artifact_id/media_type/size_bytes/raw_sha256 及 member_refs_json；`computation_cache.py::_entry_from_row` / `_parse_entry_row` 复用固定格式 decode；不打开manifest内容。 |
| UploadRevision | source_artifacts；`sqlite_workspace.py::upload_revision_from_row` / `_decode_source_artifacts` 得到 SourceArtifactBinding，使用其现有 ref。 |
| PreviewResult | bundle_artifact_id、ready_closure_artifact_id、canonical.canonical_table_set_closure_ref、canonical.canonicalization_manifest_ref 和 identity_pairs[].assessment_ref；`sqlite_workspace.py::preview_result_from_row` 的固定binding格式和 `_preview_artifact_ref_from_document`；只取decoder明确提供ref，不读bundle。 |
| SubmitAttempt/Submission | source_artifact_refs、canonicalization_manifest_ref、prepared_canonicalization_manifest_ref；`sqlite_submission.py::submit_attempt_from_row/submission_from_row` 固定decoder；仅ID时由artifact store owning stat取得尺寸，不用业务字段猜大小。SubmitAttempt.repository_import_artifact_ref为BE对象；repository_artifact_ref为RS对象，不在BE重复计。 |
| Operation | artifact_refs；`sqlite_operations.py::operation_record_from_row`；由 business_refs 对应 owning业务记录取得简单repository关联，无法便宜关联则公共，不递归读取payload/checkpoint。 |
| Head | baseline_head_records 仅指 baseline_node_id，不直接持有对象ref；不为统计追踪无限祖先/历史bundle，该源不新增字节，当前已有对象由上述固定来源覆盖。 |

所有候选必须通过 LocalArtifactStore.observe_object 当前可见stat后才计 measured bytes；旧ref不存在记 stale，不能按ref.size永久累加。
RS库候选仅从成功 create_repository 的 MutationStore keyset页得resource_id，经DurableLayout.published_repository定位。
扫描不跟随symlink、不执行Dolt、不创建/修复库，before/after不等待业务；计时cutoff和缺失语义以实施计划 §3 为准。

## B 运行接点与近似范围

`operations/worker_runtime.py` 仅捕获专用 sink 的普通 Exception，executor 原异常与原 observer
继续按既有规则传播；begin 紧邻真实 executor 调用，end 位于 finally 且 completed/wake 必达。
`statistics/metrics.py` 是无业务依赖、无 I/O/编码的有限标量 hook；capability 仅可依赖这个窄模块。
active sink 与 SQLite/采样实现在 `infrastructure/statistics/`，bootstrap 可注入，进程启停由 E 接线。

回调缓冲按整条最大记录字节保守计费，表项额外保守限制在10KiB以内；后台再按实际12KiB metrics、
16KiB record、batch字节校验编码。固定字段过大则丢载荷并明确 partial。相同输入形态不跨pair相加，
一个claim出现多个不同当前输入时形态为null；changed统计按pair计量。ordered当前表去重集合最多100项，
超过则ordered总量为null。表项保留pair标识，条目/字节截断不改变tables_total。

parse/materialize/bundle在现有公开调用边界计时；History按需读取边界单独计时。finalize实际计时入口
为`application/submission/finalize_transaction.py::finalize_submit_transaction`，包含现有事务，避免与其
内部纯finalize重复累计。rs_import在HTTP adapter的submit_versioned_import/wait_operation调用计时。
comparison每个已执行task记录一次查找，验证后实际cached复用才命中；risk候选在session统一记录
查询与验证返回，避免再在持久层重复统计。未触达的cache层为null。

资源读取仅在后台进行，CPU/I/O摘要使用同实例、同执行窗口内实际采样点之间的差值，不外推至
未采样的头尾区间；摘要为partial/counter_unavailable，短窗口无两个有效点则差值为null。RSS与
cgroup内存为采样峰值，未扫描scratch则该峰值为null。业务结果没有可靠已提交结果来源时保持unknown。
原始样本保留各自时间，计数下降或实例改变不相减。

空间压力同时检查DB/WAL物理长度和main的page_count/freelist_count，预留一个有限batch及索引页。
有限保留清理后先PASSIVE checkpoint；WAL达到软阈值时再做busy_timeout=0的机会式TRUNCATE
checkpoint，无可截断窗口则暂停、以后维护周期重试，不等待读者、不做VACUUM。SQLite页满的
竞态失败同样触发一次有限旧曲线清理后再重试，不以总预算尚有余量为由忽略main页上限。

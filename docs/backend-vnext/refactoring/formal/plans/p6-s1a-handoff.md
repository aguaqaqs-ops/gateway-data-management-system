# Phase 6 S1a handoff

## 候选与审核修订

S1a 最终产品候选为 7d0ce6220ac2541b76ab75191d43ce6113003966，分支 p6-s1a-impl。本 handoff 文档在该候选之后单独提交；产品代码仍以 7d0ce622 为准，未推送、未打 tag。独立审核报告为 p6-s1a-review 分支提交 852eef4a95，结论是定向修订。

| Finding | 修复与验证 |
| --- | --- |
| F1 | vnext/backend/src/gateway_backend/capabilities/comparison/ordered.py 对满足 _can_table_early_exit 的未变化 ordered 表直接构造相同两侧 facts。ordered 逻辑摘要与 occupancy 摘要各由当前侧规范行计算一次后赋给两侧；保留双侧描述符产生的有效 pair 策略、规范 provenance、schema/读取 degraded 分支及原 facts 结构。此分支不建两侧键映射、不逐列比较、不调用 LIS、不生成记录，也不复用 _compare_single_side。现有 ordered 测试以普通双侧路径作逐字段 oracle，并 mock 计数完整比较与 _backbone_indices；候选 focused 测试通过。 |
| F2 | _repository_replay_renderer.py 对 INSERT、CASE UPDATE、DELETE 统一按完整 UTF-8 SQL 语句字节计数（前缀、分隔符、值和 ;\n）。多行批次最多 256 行、4 MiB；加入下一行将超限时先 flush 当前批次。单行本身超过 4 MiB 时单独成句，不失败。Storage Mutation Contract 已按此规则更新。每种语句都覆盖恰好上限、超限 1 字节及单行超限测试；Repository Service 实际回放路径上的 5 MiB INSERT 与 CASE UPDATE 成功，表哈希分别与逐行形式相同。 |
| F3 | vnext/backend/benchmarks/dc58_content_compare.py 使用明确字段 allowlist，不按任意 _id 后缀或 64 位十六进制值屏蔽。对内容寻址引用实际解引用并按逻辑角色比较产物内容。5a2989 的既有 t1 与候选 7d0ce622 的 t1、全部 golden fixtures 的核对结果见下文。审核者的两个反例均被判为不同。 |
| N1 | handoff 中原始数字、时间、目录路径及 image ID 均按节点原始日志修正；原始日志未改。修正明细与本候选最终测量分列于下文。 |
| N2 | 清理清单补入实际存在于 S1a 日志目录之外的 s4-stall-* 诊断目录，并补入 reviewfix worktrees、栈、volumes、Dolt refs 与 scratch。 |

审核修订涉及的产品、Contract、测试与工具文件：ordered.py、_repository_replay_renderer.py、storage-mutation-and-change-set.md、test_comparison_ordered.py、test_dolt_renderer.py、test_import_worker_integration.py、dc58_content_compare.py、real_dump_journey.py 与 test_real_dump_journey.py。F1/F2 未增加生产计时或兼容路径。golden 未因 F1/F2 增加变化；S1a 相对基线累计变化为 23 个 fixture：mutation 12、snapshot-materialization 5、storage-projection 6。导入包 golden 未变。

S1a 其余目标保持：每表存储摘要为 raw_content_digest、storage projection version 为 3；删除 fast_row_digest 与 ordering_digest；snapshot digest 每表只使用无需读行的事实；Preview/History 完整结构过滤；Submit 仅写变化、使用 ADAPTIVE_PATCH、按 parent manifest 校验 RS 读取的 parent rows、prepare checkpoint 绑定 parent manifest digest，包 manifest 列出全部表。未新增双读写或旧字段兼容路径。

### Contract 与摘要消费方

S1a Contract 直接更新到目标形态：Canonical Storage §4、§6.1，Storage Mutation §2、§3 与 ADR 0014 生产路径条款，Ordered Diff，ADR 0019 说明，snapshot-materialization 文档和 control DB 基线 schema。F2 将完整 SQL 字节批规则补入 Storage Mutation Contract。删除 fast_row_digest 的计算、字段、checkpoint/manifest 序列化与 Contract 条文；production 中无旧字段别名或双算。ordering_digest 与 import_publication.py 的传递也删除。

raw_state_digest_of 保留。它由 snapshot materialization 与 Repository reference materialization 生产，用于 schema-independent 的原始表状态；composite、snapshot-summary/checkpoint codec、preview_jobs canonical input、repository import source/readback 校验仍消费它。它不含 schema，与含 schema 的规范状态摘要语义不同，并有独立用途。

### 基线 snapshot 行消费者盘点

| 消费者 | 未变化表的处理 | 对应测试/覆盖 |
| --- | --- | --- |
| Preview 基线物化与行比较 | 逻辑需求为 X∪D；未变化/新增表不读旧行，从 catalog/manifest 得到全表身份摘要。 | test_unchanged_preview_table_does_not_read_baseline_rows、test_preview_reads_changed_and_deleted_baseline_tables_only、test_requested_tables_only_open_selected_rows_and_keep_full_catalog_summary。 |
| version_manager 项目身份评估 | 未变化表复用当前侧规范行；变化/删除表按 selector 读取基线行。 | test_unchanged_identity_table_reuses_current_rows_without_baseline_read 与 changed/deleted 选择测试。 |
| Composite signal | 未变化表使用当前侧规范表；变化/删除服从普通 selector，没有始终读旧 composite 的旁路。 | test_full_materialize_publishes_checkpoint_and_assemble_successor、test_missing_logics_xml_materializes_stable_empty_source、候选 t4 History journey。 |
| History 变化表行比较 | X 需要 old-X 与 current-X；按 commit 与内容身份合并去重。 | test_changed_history_table_reads_both_pair_sides。 |
| History 未变 ordered 摘要 | 使用当前侧规范行；pair 策略仍由两侧描述符构造，规范 provenance、facts 与 degraded 行为保留。 | test_unchanged_ordered_history_reads_current_side_and_preserves_facts；另有本轮 F1 facts oracle/LIS mock 测试。 |
| History 删除表 | D 仍读旧侧规范行，用于整表浏览、导出和风险。 | test_deleted_history_table_reads_only_the_old_pair_side。 |
| DATASET_REPLACEMENT | 未变表复用当前 artifact；变化/删除表按替换需求处理旧侧。 | test_dataset_replacement_reuses_current_artifact_for_unchanged_table。 |
| checkpoint 与恢复 | 已发布 checkpoint 含物化侧 artifact，恢复 assemble 直接读取 checkpoint；缺 checkpoint 时按 selector 重做必要读取。 | test_assemble_resumes_from_checkpoint_when_repository_is_unavailable、test_assemble_resumes_from_materialized_sides_with_runtime_ruleset、test_full_materialize_publishes_checkpoint_and_assemble_successor。 |
| Submit parent 行校验 | 与 Preview/History 未变过滤独立；仅为要 mutation 的变化表通过 RS 产品路径读取并校验 parent manifest。 | test_repository_base_digest_reaches_mutation_planner、Submit prepare/recovery focused tests、候选 t4 v2 完整旅程。 |
| 规则/catalog 绑定 | 读 catalog、描述符、provenance、规则，不消费 baseline snapshot rows。 | projection/ruleset focused tests。 |

盘点未发现需要改变设计 §4.2 规则或 §16.2 计数口径的消费者。

## 计数断言与保值

设计 §16.2 计数公式在候选 focused 与全量 runner 中通过，手算示例覆盖：

- Preview 基线逻辑读取需求为 X∪D，实际读取不超过 |X|+|D|；行比较派发 =|X|；表级处理 =|A|+|D|；kernel 调用不超过 |X|。
- Submit 表级计划覆盖 X∪A∪D；键变化按 DELETE+INSERT 计数；重建写入 target 行数；删除表 DROP 一次、写入零行。
- focused 用例 test_submit_count_examples_match_hand_computed_net_changes、test_submit_table_level_counts_for_added_and_deleted_tables、test_threshold_boundary_cases 在 05、候选 7d0ce622 上 6 passed。日志：/home/dev/gdds-p6-logs/s1a/05-reviewfix-count-assertions-r1-20261027.log。
- F1/F2 focused 与五包 Ruff/mypy 在 05、候选 7d0ce622 上通过：backend focused 7 passed，Repository Service oversized replay 1 passed；五包 Ruff/mypy 均通过（backend 486 source files，Repository Service 200）。日志：/home/dev/gdds-p6-logs/s1a/05-reviewfix-focused-static-20261027.log。
- t4 journey 记录 v1 312/312 changed、repeat Preview 0/312、v2 26/312 changed、degraded 0，以及 v2 Submit 的 RS parent 行读取和 History 结果；完整运行日志见旅程表。

内容保值项：规范表内容、ordered 逻辑内容与 occupancy、comparison records/facts、risk、surface、bundle 与 snapshot-materialization 内容及 HTTP DTO 在 DC58 屏蔽口径下相同。摘要/哈希字段自身按批准口径屏蔽；其引用产物仍逐个解引用比较内容。S1a 摘要字段按目标形态的变化不作为内容差异。数据读取、摘要和产物的核对方法如下。

## DC58 内容保值核对

### 字段路径 allowlist

比较脚本对 JSON 使用以下精确字段名清单。机器报告的 masked_field_paths 列出了实际 t1/golden 内容中全部具体路径实例（15,692 条，数组下标规范为 [*]）；没有通过通用后缀、值形状或任意 ID 规则扩大屏蔽范围。

- 摘要/哈希字段（对象键精确匹配）：after_manifest_digest, after_storage_projection_digest, artifact_content_digest, assessment_digest, base_repository_ref_digest, before_manifest_digest, before_entry_set_digest, before_ordered_digest, before_row_digest, before_snapshot_digest, before_storage_projection_digest, baseline_canonical_state_digest, bundle_digest, bundle_manifest_digest, business_schema_digest, canonical_business_digest, canonical_schema_digest, canonical_state_digest, canonical_table_set_closure_digest, canonicalization_manifest_digest, capability_digest, change_set_digest, closure_manifest_digest, compare_schema_digest, composite_logic_source_digest, comparison_digest, content_digest, current_entry_set_digest, current_ordered_digest, current_snapshot_digest, facts_core_digest, fast_row_digest, identity_assessment_set_digest, initial_canonicalization_manifest_digest, input_canonicalization_manifest_digest, input_digest, manifest_digest, modified_canonical_state_digest, ordering_digest, package_raw_sha256, parent_manifest_digest, policy_digest, project_identity_assessment_digest, projection_logical_digest, projection_schema_digest, raw_content_digest, raw_sha256, raw_state_digest, records_content_digest, records_manifest_digest, repository_import_artifact_raw_sha256, request_fingerprint, risk_digest, risk_evaluation_digest, ruleset_digest, sha256, sql_source_digest, snapshot_digest, source_artifact_digest, source_digest, source_identity_digest, source_schema_digest, storage_projection_ruleset_digest, storage_projection_digest, storage_rule_digest, surface_digest, table_ruleset_digest, table_schema_digest.
- 摘要 map 字段：source_digests。
- 内容寻址/运行实例 ID 字段（对象键精确匹配）：acceptance_id, archive_plan_id, archive_result_id, artifact_id, attempt_id, based_on_baseline_node_id, baseline_node_id, baseline_commit_id, business_baseline_node_id, business_baseline_commit_id, bundle_artifact_id, commit_id, current_preview_result_id, current_upload_revision_id, before_commit, current_commit, expected_commit_id, expected_parent_commit_id, initial_commit_id, node_id, operation_id, pair_id, preview_result_id, ready_closure_artifact_id, ref_id, released_workspace_ids, repository_commit_id, repository_expected_commit_id, repository_id, request_artifact_id, resolved_commit_hash, snapshot_id, submit_attempt_id, submission_id, selected_submission_id, surface_id, upload_revision_id, view_id, workspace_id.
- 时间/耗时字段：accepted_at, accepted_at_us, archived_at, archived_at_us, completed_at, completed_at_us, created_at, created_at_us, duration_ms, duration_seconds, elapsed_ms, elapsed_seconds, finished_at, finished_at_us, occurred_at_us, started_at, started_at_us, thread_cpu_seconds, timestamp, updated_at, updated_at_us, wall_seconds。
- 路径字段只有 logical_path，且只将其中匹配 op-[0-9a-f]{12,} 的运行实例 token 替换为 <OPERATION>，保留路径其他内容。
- 位置约束：repository_ref 只在 $.source_context.repository_ref 屏蔽；artifact_id 仅在引用位置（父键 artifact_ref、*_ref、required_refs、refs、row_file_refs 或 source_artifacts）屏蔽，其它 artifact_id 保留比较。
- business_project_id、table_id、annotation_id、rule_id 明确不屏蔽。遇到清单外的 _digest、_sha256、_hash 或时间类字段，脚本报错，不静默忽略。64 位十六进制值按普通字符串比较。

反例检查证明：改动 business_project_id 会被判为内容不同；把普通业务字段 value 从一个 64 位十六进制字符串改为另一个也会被判为不同。两例均为合成反例，不含真实行值。

### t1、规范表与导出产物

- 比较脚本：vnext/backend/benchmarks/dc58_content_compare.py。候选 7d0ce622 在 05 的 t1 state/volumes 与既有 5a2989 t1 state/volumes 比较；未重跑 baseline。机器报告：/home/dev/gdds-p6-logs/s1a/05-dc58-final-corrected-path-5a2989-vs-7d0ce622-20261027.json；运行日志：/home/dev/gdds-p6-logs/s1a/05-dc58-final-corrected-path-20261027.log。
- 对齐对象按表名、记录族、产物种类和逻辑角色，不按运行 ID 或 artifact ID 对齐。比较前按上述 allowlist 规范 JSON；binary/非 JSON 内容逐字节比较。对内容寻址引用逐个加载被引用产物，再比较其内容。HTTP journey DTO 也按同一字段清单比较。
- snapshot-materialization：按 side/table 对齐 1,125 个描述比较、399 个表产物；302 个非空 row-free 描述没有单独行载体，使用对应 canonical table artifact 与 Repository Service 产品路径导出的表内容按表名解析并比较；无 unresolved。250 个 canonical table-set artifacts 内容相同。由此既比较描述摘要事实，也比较规范表行内容，不以表数或摘要相等替代内容比较。
- facts 与记录族：没有独立的 facts 全量表产物时，其实际载体是 records closure 中的 facts/record-family members；逐个解引用并按记录族和逻辑角色比较。risk annotation、surface、bundle members 同样逐个载入并比较。
- Repository 导出表：baseline/candidate 的 v1 各 125 张表、3,733 行，v2 各 125 张表、3,731 行；按表名对齐导出内容，逐表相同。导出通过 Repository Service 产品路径取得。
- v1 Preview 330/330、v2 Preview 9/9、History 8/8 个 bundle closure entries 均按逻辑角色内容相同；嵌套引用无 unresolved。保存的 HTTP DTO 屏蔽后相同。比较报告的 canonical table、facts、risk、surface、bundle、snapshot 与导出内容均无保值差异。
- 72 个 golden fixtures 全部按同一 allowlist 比较：56 个屏蔽后相同；16 个未被屏蔽的差异逐项映射如下。snapshot-materialization 的内容及其 20 个 golden 屏蔽后相同；其它未列 fixture 也相同。未发现 S1a 批准变更范围以外的 golden 差异。

| # | Golden fixture（相对 vnext/fixtures/golden/） | 差异 | 对应批准变更 |
| --- | --- | --- | --- |
| 1 | mutation/renderer/capability-failures/source-literal-anomaly/closure.json | max_patch_change_ratio 0.05→0.01 | §4.3 / DC57：阈值 1% |
| 2 | mutation/renderer/valid/destructive-delete/closure.json | max_patch_change_ratio 0.05→0.01 | §4.3 / DC57：阈值 1% |
| 3 | mutation/renderer/valid/first-load-insert/closure.json | max_patch_change_ratio 0.05→0.01 | §4.3 / DC57：阈值 1% |
| 4 | mutation/renderer/valid/mixed-scalars/closure.json | max_patch_change_ratio 0.05→0.01 | §4.3 / DC57：阈值 1% |
| 5 | mutation/renderer/valid/multi-table-patch/closure.json | max_patch_change_ratio 0.05→0.01 | §4.3 / DC57：阈值 1% |
| 6 | mutation/renderer/valid/patch-single-update/closure.json | max_patch_change_ratio 0.05→0.01 | §4.3 / DC57：阈值 1% |
| 7 | mutation/renderer/valid/rebuild-replace-rows/closure.json | max_patch_change_ratio 0.05→0.01 | §4.3 / DC57：阈值 1% |
| 8 | mutation/renderer/valid/destructive-delete/expected.sql | 批量 DELETE SQL | DC57：按批渲染 |
| 9 | mutation/renderer/valid/mixed-scalars/expected.sql | 批量 DELETE SQL | DC57：按批渲染 |
| 10 | mutation/renderer/valid/multi-table-patch/expected.sql | CASE UPDATE SQL | DC57：按批渲染 |
| 11 | mutation/renderer/valid/patch-single-update/expected.sql | CASE UPDATE SQL | DC57：按批渲染 |
| 12 | mutation/renderer/valid/rebuild-replace-rows/expected.sql | 批量 DELETE SQL | DC57：按批渲染 |
| 13 | storage-projection/manifest/valid/s5-durable-roundtrip/document.json | contract_version 3.2.0→3.3.0；storage_projection_version 2→3 | §4.1：projection 3 |
| 14 | storage-projection/ruleset/malformed/s1-duplicate-selector/document.json | storage_projection_version 2→3 | §4.1：projection 3 |
| 15 | storage-projection/ruleset/valid/s1-net-cfg/document.json | storage_projection_version 2→3 | §4.1：projection 3 |
| 16 | storage-projection/ruleset/valid/s2-migrated-matrix/document.json | storage_projection_version 2→3 | §4.1：projection 3 |

以上 16 处差异与阈值、批渲染和 projection/contract version 一一对应；不将屏蔽口径作为解释未知 golden 差异的依据。

## Dolt 语句规则、阈值实测与哈希核对

- 语句形式预检使用 Dolt 2.1.11 合成表，覆盖单列键、复合键、GID_NO_V1（gid 为存储键）。比较按批 DELETE+INSERT、upsert+DELETE 与按批 CASE UPDATE+DELETE+INSERT。语法、主键查找计划、逐行哈希一致、dolt_diff 同键行为均通过；使用等价主键谓词的 EXPLAIN ANALYZE SELECT 检查索引查找，因为该版本 Dolt 的经典 DML EXPLAIN 无计划输出。预检日志 /home/dev/gdds-p6-logs/s1a/05-dc57-preflight-ec689eda0a-20261027.log，报告目录见 N1 更正表。
- F2 单行超过 4 MiB 的 5 MiB INSERT 与 CASE UPDATE 在 05 经 Repository Service 实际回放成功；与逐行形式哈希相同。focused renderer 测试覆盖 INSERT/UPDATE/DELETE 各自恰好上限、超限 1 字节、单行超限独立成句。
- 冻结规则：ADAPTIVE_PATCH 仅在变化行数 ≤1,000 且变化行数 / max(before_rows, after_rows, 1) ≤1% 时逐行 patch；否则整表重建。三种 DML 单句行数 ≤256；多行语句完整 UTF-8 ≤4 MiB；如果下一行会超过字节上限，先结束当前批次；大于 4 MiB 的单行单独成句。
- 最终候选阈值与表哈希复测：ct108（gw-dms-test），Dolt 2.1.11，HEAD 7d0ce622，2026-10-27 16:32:37–17:04:34 UTC，exit 0。日志 /home/dev/gdds-p6-logs/s1a/ct108-reviewfix-threshold-and-hashes-20261027.log；JSON /home/dev/gdds-p6-logs/s1a/ct108-reviewfix-mutation-replay-7d0ce622-20261027.json。parent 行通过 RS 产品路径 Arrow 读取；所有回放仅在 repository copy /home/dev/gdds-p6-logs/s1a/ct108-reviewfix-mutation-replay-scratch-7d0ce622/repository-copy 执行，repository_main_unchanged=true。
- 1% 样本 b1_n11_iec104_syx_list：parent 9,822 行、target 9,828 行；98 个合成净变化（0.99715099%，92 UPDATE + 6 INSERT），交替三轮，patch/rebuild 中位数 0.612836s / 1.227434s，三轮表哈希均相等。1% patch 快于重建约 50.1%，未触发设计 §17 停止项。
- 1,000 行上限样本：同表 1,000 个合成变化、变化率 10.175%，比例条件不满足，策略选择重建；adaptive/full rebuild 1.302775s / 1.260042s，哈希相等。该结果符合冻结的双门槛策略，不代表 1% 样本慢于重建。
- t4 v2 全表对照：27 张 X∪D 表，目标 312 张。按批 ADAPTIVE_PATCH、整表重建与 current 表逐张 312/312 哈希相同；ADAPTIVE_PATCH 2.511356s、整表重建 27.414983s。Adaptive 重建 15 表；行级语句覆盖 21,974 DELETE、22,054 INSERT、84 UPDATE；full rebuild 写入 246,874 行。
- N1 指出的早期 af559 复测原始数值已按原始 JSON 更正，但不作 7d0ce622 的最终候选证据；当前最终候选只引用本节三个新复测结果。

## Worker step 归因（沿用已接受 DC59，未重跑）

按 owner 要求，本次不重跑 worker 归因。以下阶段级分解来自已接受的 DC59 诊断：独立分支 p6-s1a-timing-diag，HEAD e52ad2c48b7c28137bc7f135b89b2da22f467947；该分支只增加阶段名、耗时和计数日志，未进入 S1a 候选。日志：ct108-timing-diag-full-t4-e52ad2-retry2-20261027.log、ct108-timing-diag-worker-e52ad2-20261027.log、ct108-timing-diag-rs-summary-e52ad2-20261027.log、ct108-timing-diag-control-timeline-e52ad2-20261027.log。V5b 与 worker 同代码，但 stage boundary、artifact store 和是否把 readback/finish 计入汇总不同；墙钟差额不能归因到单一函数或 I/O 根因。

### Assemble / Preview

| 段 | v1 worker / V5b / 差额（秒） | v2 worker / V5b / 差额（秒） | 来源与后续处理 |
| --- | --- | --- | --- |
| checkpoint read | 45.110388 / V5b 不含 | 58.655686 / V5b 不含 | 读取 worker checkpoint；V5b 的 pair/bundle 汇总不含此阶段。S1b artifact/checkpoint；backend artifact/checkpoint owner。 |
| pair pipeline 总计 | 625.543636 / 500.862901 / +124.680735 | 49.334631 / 38.223066 / +11.111565 | 包含 planning、compare、record closure、risk、surface；两种运行的具体速度差未隔离。S3 comparison/compute；backend comparison/compute owner。 |
| planning | 0.167553 / 0.134448 / +0.033105 | 0.172608 / 0.139477 / +0.033131 | 同上；按阶段复测，不推断为单一根因。S3；backend comparison/compute owner。 |
| compare | 184.992010 / 146.716866 / +38.275144 | 47.157924 / 36.261424 / +10.896500 | compare 在 V5b 中也执行，不能把全量差额记为 compare。S3；backend comparison/compute owner。 |
| records closure generation | 397.315471 / 318.699340 / +78.616131 | 1.159850 / 1.072630 / +0.087220 | V5b 含 records closure 生成；v1 另测 full-readback validation 98.506376s（223 entries / 250,471 records），它在 V5b 聚合段外。S3；backend comparison/compute owner。 |
| risk | 42.422923 / 34.724948 / +7.697975 | 0.341929 / 0.337177 / +0.004752 | V5b 包含 risk，不是跳过。S3；backend risk/comparison owner。 |
| surface | 0.404734 / 0.328366 / +0.076368 | 0.324848 / 0.260593 / +0.064255 | V5b 包含 surface，不是跳过。S3；backend surface/comparison owner。 |
| 未分配 pair 计时余量 | 0.240945 / 0.258933 / −0.017988 | 0.177472 / 0.151765 / +0.025707 | 聚合计时边界余量，不再分摊。S3 复测时保留此项。 |
| bundle | 51.392878 / 43.284187 / +8.108691 | 2.442234 / 2.004048 / +0.438186 | worker 写 Compose backend-artifacts volume；V5b 使用测量 scratch 的 FileMeasurementArtifactStore。worker plan/read/publish/readback 与 V5b bundle write/readback 计数口径不同，已有数据不能认定差额由存储位置造成。S1b artifact/checkpoint；backend artifact/checkpoint owner。 |
| finish | 0.999274 / V5b 不含 | 0.763653 / V5b 不含 | ready closure、state artifact、checkpoint prepare 和剩余收尾。S1b；backend artifact/checkpoint owner。 |
| 合计 | worker 723.046176；V5b pair+bundle 544.147088；差额 178.899088 | worker 111.196204；V5b pair+bundle 40.227114；差额 70.969090 | worker 分解分别为 checkpoint + pair + bundle + finish。差额分别为 checkpoint 45.110388 + pair 124.680735 + bundle 8.108691 + finish 0.999274；以及 checkpoint 58.655686 + pair 11.111565 + bundle 0.438186 + finish 0.763653。 |

worker 使用 Compose artifact volume；V5b 使用 measurement scratch。V5b 包含 compare、risk、surface 与 records closure 生成，但把 v1 records-closure full-readback validation（98.506376s）和 bundle readback validation（1.038912s）单独记录，不计入 pair+bundle 汇总。worker 的 checkpoint read 和 finish 也不在该 V5b 汇总中。由此可解释统计段不同，尚不能定量解释同一阶段的环境/存储速度差：artifact/checkpoint 相关在 S1b，由 backend artifact/checkpoint owner 跟进；pair 内子项速度差在 S3，由 backend comparison/compute owner 跟进。需测量工具支持的阶段级拆分已经完成，无 S1a 未解释残差。

### Submit、await、step 间隔与剩余诊断

| 项 | 观测来源与耗时 | 削减方案、阶段与 owner |
| --- | --- | --- |
| v1 Submit prepare_import | 469.094s；打开 312 表冻结输入 44.637s；frozen projection 39.231s；after snapshots 82.731s；parent rows 0；plan/render 299.196s（312 changed / 312 rebuild）；package publish 0.354s。 | 减少冻结输入重复读与投影物化。S2b；Submit/backend mutation 与 snapshot owner。 |
| v2 Submit prepare_import | 全 step 212.327s；打开 312 表 45.201s；27 个变化表 frozen projection 10.571s、after snapshots 27.447s；RS parent rows 25 表 / 129,426 行 / 90.520s；plan/render 36.357s（27 changed / 15 rebuild）；剩余 canonicalize/DB/publish 亚秒级。 | 优化渲染和按表批处理；优化 Arrow throughput/关闭，但保留 RS 路径与 parent manifest 验证。S2b；mutation renderer 与 Repository Service owner。 |
| Repository async import / await | v1 submit_import worker 0.270s、RS POST 约 0.035s；repository_wait 首次 60.001s timeout，重试 0.431s；v2 submit_import 0.244s、await 49.706s。RS cgroup CPU 约 179.458s / 183.478s，主要时间是 RS/Dolt 异步回放，worker 在等待。 | 优化 Dolt 回放并保留 await/retry/lease 语义。后续 RS 性能阶段；Repository Service/Dolt owner。 |
| claim 与 step dispatch | claim SQL 19–40ms（首个 26.330ms），claim 后 execution start 2–3ms。普通 step 完成至下个 execution start 约 2.6–9.95s：v1 materialize→assemble 4.88s、assemble→publish 7.65s、prepare→submit 9.95s、submit→await 9.73s；v2 相邻步骤约 8.7–9.75s；History materialize→assemble 约 8.1s。 | WorkerRuntime._run_claim 非 drain 路径等待下一 heartbeat timeout（约 10s），等待未观察 executor completed event。让 executor 完成可唤醒 supervisor，同时保留 heartbeat/drain/lease。后续 worker runtime/performance；backend Worker Runtime/Operations owner。 |
| operation 后的 repository verification 与 harness poll | v1 await 后到下一操作约 79.6s，含 RS 产品路径行验证 75.197s；v2 约 78.3s，含 row verification 76.372s、approval 0.674s 和 harness 调度约 1s。real_dump_journey.py::_poll_operation 每 2s poll，最多贡献一个 poll 周期的结果发现延迟。 | 保留验证，可把验证与 operation elapsed 分开呈现；poll 周期可调。benchmark harness 阶段；性能测量工具 owner。 |
| Control DB 与 RS stream close | heartbeat 约每 10s 一次，单事务 0.15–0.20s；每 job 累计 3.3–25.3s，与 executor 并行。RS 有 37 次 Arrow bridge 30s join-timeout warning、526 次 rows HTTP 200；无逐请求 close duration，不能将 37×30s 相加为 wall time。 | 不削弱 lease。后续 RS 诊断按请求加关闭阶段计时；Repository Service owner。 |

上述归因仍符合 DC59 阶段级分解。worker/V5b 同代码阶段内的速度差是已知待办，不冒充已确认的具体根因；在 S1b/S3 跟进。F1/F2 后未重跑 worker timing attribution；本候选 t4 实际耗时见上表，作为本轮性能记录，不把它与旧 run 的差异单独归因给 F1/F2。

## 最终候选真实数据旅程

真实数据只保留在测试节点 volumes 与日志中，不进入 Git。所有旅程日志记录 hostname、HEAD、起止时间与 exit；运行期间各自使用该节点上候选 7d0ce622 的栈。

| 档位 | 节点、UTC 起止、exit | Preview / Submit / History 摘要 | 日志 |
| --- | --- | --- | --- |
| t1 | 05 gw-dms-test-05，16:30:34–16:35:42，0；随后导出采集至16:36:09 | v1 Preview 42.161s、Submit 42.190s；repeat Preview 32.118s（0/125 changed）；repeat Submit 无 Repository operation；v2 Preview 38.140s、Submit 42.189s；History 22.071s。 | /home/dev/gdds-p6-logs/s1a/05-reviewfix-t1-full-20261027.log；导出 /home/dev/gdds-p6-logs/s1a/05-reviewfix-t1-exports-20261027.log |
| t2 | 05，16:38:40–17:13:49，0 | v1 Preview 433.507s、Submit 182.827s；repeat Preview 220.775s；v2 Preview 379.341s（57/220 changed）、Submit 345.485s；History 282.818s。 | /home/dev/gdds-p6-logs/s1a/05-reviewfix-t2-full-r1-20261027.log |
| t3 | 05，17:13:51–18:22:51，0 | v1 Preview 722.504s（192/192 changed）、Submit 355.543s；repeat Preview 531.869s（0/192）；v2 Preview 858.998s（54/193）、Submit 562.431s；History 553.593s。Repository reads 41.051s / 40.287s；offline composite compare 444.662s；census 无 mismatch。 | /home/dev/gdds-p6-logs/s1a/05-reviewfix-t3-full-r1-20261027.log |
| t4 | ct108 gw-dms-test，17:06:41–18:37:38，0 | source 320 表 / 437,149 行，canonical 312 表 / 246,794 行。v1 Preview 1,546.088s（312/312 changed、degraded 0）、Submit 579.863s、repository read 75.076s；repeat Preview 872.580s（0/312）；v2 Preview 1,007.306s（26/312、degraded 0）、Submit 289.942s、repository read 76.337s；History 312.889s，168 records，composite signal 435 rows unchanged。 | /home/dev/gdds-p6-logs/s1a/ct108-reviewfix-t4-full-20261027.log |

相较 af559 的正式 t4：v1 Preview 1503.877→1546.088s、v1 Submit 561.741→579.863s、repeat Preview 852.508→872.580s、v2 Preview 989.222→1007.306s、v2 Submit 287.924→289.942s、History 310.876→312.889s。运行间环境与运行态变化未隔离，因此只把 7d0ce622 数值作为本候选最终记录，不将差值断言为 F1/F2 的单独因果效应。

t1 baseline volume/state 来自 5a2989 已有旅程；本候选 t1 已完整重跑，F3 比较复用了该 baseline 与新 candidate 的 state/volumes。t1/t2/t3 journey wrapper 收尾后栈容器为 Exited；volumes 保留。t4 验收结束后仅用 docker stop 停止该候选的三个容器，三个 volumes 保留。该停栈不移除容器或 volumes。

## 权威 runner 与 repository-service 镜像

04（hostname gw-dms-test-04）在 clean、已提交的 detached worktree /home/dev/gdds-p6-logs/s1a/04-reviewfix-7d0ce622-wt 上重建 repository-service 镜像并运行 DC48 环境六包 runner；worktree 保留至阶段 exit 合入后（DC51）。运行环境：umask 022、HOME=/root、LC_ALL=C.UTF-8、TMPDIR=/home/dev/gdds-test-tmp、PATH 以 /home/dev/.cargo/bin 开头。起止 HEAD 均为 7d0ce622，worktree clean，runner 期间未改 worktree。

| 步骤/包 | 节点、时间、exit | 结果 | 日志 / 镜像 |
| --- | --- | --- | --- |
| repository-service 镜像重建 | 04，16:30:48–16:30:56，0 | image sha256:9ca7474e1aa5a12004b176063617f856d6fdea03a097814502af0fc32429f07a；source-tree sha256:255d603d3261e867d3d48b1f7bb35664f39cf2769bf7d3beba7d3be082574d14；build-input revision 90efd8161afbf28c8b1b6c679974f885b6f856df；product revision 7d0ce622。 | /home/dev/gdds-p6-logs/s1a/04-reviewfix-rs-image-20261027.log |
| 六包权威 runner | 04，16:30:56–17:10:40，0 | 起止 HEAD 7d0ce622。 | /home/dev/gdds-p6-logs/s1a/04-reviewfix-six-package-runner-20261027.log |
| rust | 同上，0 | fmt、clippy、test 均通过。 | 同上 |
| shared_kernel | 同上，0 | 242 passed。 | 同上 |
| repository_contracts | 同上，0 | 152 passed。 | 同上 |
| repository_client | 同上，0 | 154 passed。 | 同上 |
| backend | 同上，0 | parallel 2,944 passed、serial 39 passed；64 warnings。 | 同上 |
| repository_service | 同上，0 | parallel 1,741 passed / 1 skipped；serial 207 passed。 | 同上 |

六包 runner 内的 Compose 测试也通过，满足当前候选容器门禁。runner 与镜像均绑定 7d0ce622；没有将旧候选 carried 到本次结果。

## 过程记录

- 独立审核报告 852eef4a95 的三项阻塞与两项非阻塞 finding 均按上表关闭。初次比较调用因相对路径从 backend cwd 解析而得到错误的空 fixture 范围；日志 /home/dev/gdds-p6-logs/s1a/05-dc58-final-t1-vs-5a2989-20261027.log。改为显式 golden 路径后，以正式 comparator 重跑成功，日志 /home/dev/gdds-p6-logs/s1a/05-dc58-final-corrected-path-20261027.log、报告 /home/dev/gdds-p6-logs/s1a/05-dc58-final-corrected-path-5a2989-vs-7d0ce622-20261027.json。第一次 t2 调用在 Compose 启动前被中断（exit 130），日志 /home/dev/gdds-p6-logs/s1a/05-reviewfix-t2-full-20261027.log；随后 t2 在 7d0ce622 上完整重跑通过，日志 /home/dev/gdds-p6-logs/s1a/05-reviewfix-t2-full-r1-20261027.log。最终证据只引用成功日志与报告。
- DC58 初次 baseline export 环境缺少 httpx，失败日志 05-dc58-baseline-exports-20261027.log；经受控同步后由 05-dc58-baseline-exports-retry-20261027.log 成功采集，不影响候选 t1 或最终 F3 报告。
- run3/run4 Arrow stream abort 的根因是回放测量工具以 root 经 docker exec 对 RS 正在服务的 Dolt 仓库执行 branch/checkout/sql/add/commit，改变了 .dolt/noms/manifest、repo_state.json、.dolt/tmp 的属主/权限；RS 以 gateway 用户运行，之后请求在约 40ms 即中止。故障与变化表无关。修正工具只在仓库副本回放；本轮 parent rows 经 RS 产品路径，repository_main_unchanged=true，阈值测量与 t4 journeys 成功。S1a 不需要扩大 RS 修复范围。
- py-spy 采样落后最高约 287.6s，worker heartbeat 被拖延后 lease 丢失，harness 判定 stalled；运行停在 materialize_inputs，未到 assemble_preview，不作耗时证据。日志：/home/dev/gdds-p6-logs/s1a/ct108-af559-pyspy-v1preview-v2preview-20261027.log、/home/dev/gdds-p6-logs/s1a/ct108-af559-journey-v1preview-v2preview-20261027.log、/home/dev/gdds-p6-logs/s1a/real-dump-t4-20261027T091816908320Z.compose.log。
- DC59 产品级计时诊断分支 p6-s1a-timing-diag 的 HEAD e52ad2c48b7c28137bc7f135b89b2da22f467947；对 af559ae3 的 diff 仅限 9 个 backend 文件，加入阶段名/耗时/计数日志。该分支未合入候选。诊断 t4 retry2 于 10:24:18–11:53:26 UTC 完整通过；阶段归因只沿用其阶段级结果，没有重跑采样或计时。
- 本 handoff 之前另有一次计数 focused 命令使用错误的相对 wrapper 路径，未运行 pytest（exit 127），日志 /home/dev/gdds-p6-logs/s1a/05-reviewfix-count-assertions-20261027.log；改正为 vnext/scripts/uv-consume.sh 后在同一候选运行成功，日志 /home/dev/gdds-p6-logs/s1a/05-reviewfix-count-assertions-r1-20261027.log。

### N1 原始记录更正

以下是独立报告指出的旧 handoff 抄录错误，按原始证据修正；原日志和原始 JSON 未编辑。表中历史 af559 数值仅用于说明更正，不作为本次 7d0ce622 验收证据。

| 项目 | 原始证据中的正确值 |
| --- | --- |
| ec689 Dolt 预检时间 | 2026-10-27 00:02:05–00:03:01 UTC |
| ec689 预检报告目录 | /home/dev/gdds-p6-logs/s1a/05-dc57-preflight-dolt-ec689eda0a-20261027/ |
| af559 1% patch/rebuild 中位数 | 0.614698s / 1.221495s |
| af559 1,000 行 adaptive/rebuild | 1.287732s / 1.242391s |
| af559 t4 v2 adaptive/full rebuild | 2.536123s / 27.481748s |
| af559 04 RS image ID | sha256:14c4dde24fa90208869cf442f52ab381532efa6c277963bbbbba8b3cc6e94ee4 |

## 需要 owner 后续清理的内容

本清单中的对象全部保留，交 owner 按阶段 exit 与 DC51 时点清理。本轮未删除文件、worktree、volume、container 或 Git/Dolt ref。t1–t3 journey wrapper 与 t4 docker stop 只停止容器；节点盘点时 S1a 项目容器均为 Exited，volumes 仍存在。04 门禁 worktree 保留到阶段 exit 合入之后。

### 日志目录之外的诊断目录

ct108 上实际存在，尚未清理：

- /home/dev/gdds-p6-logs/s4-stall-20261027T091815873258Z
- /home/dev/gdds-p6-logs/s4-stall-20261027T094919180432Z
- /home/dev/gdds-test-tmp/s4-stall-20261026T142723567891Z

### Py-spy、比较报告与 scratch

- ct108 仓库外工具：/home/dev/gdds-p6-logs/s1a/py-spy-042-tool/py-spy、py-spy-tool/py-spy、py-spy-bin/py-spy、py-spy-042-bin/py-spy。
- profiles、pid、采样与诊断日志：/home/dev/gdds-p6-logs/s1a/ct108-af559-pyspy-*、ct108-timing-diag-* 及对应 worker、RS、control 时间线日志；包括 speedscope JSON。
- DC58 comparator/report 与首次失败日志：vnext/backend/benchmarks/dc58_content_compare.py、/home/dev/gdds-p6-logs/s1a/05-dc58-final-t1-vs-5a2989-20261027.log、05-dc58-final-corrected-path-20261027.log、05-dc58-final-corrected-path-5a2989-vs-7d0ce622-20261027.json、05-reviewfix-t1-exports-20261027.json、05-dc58-baseline-exports-20261027.log、05-dc58-baseline-exports-retry-20261027.log、05-dc58-baseline-exports-20261027.json。
- t4 replay measurement：/home/dev/gdds-p6-logs/s1a/ct108-reviewfix-mutation-replay-scratch-7d0ce622/（含 repository copy）、对应 JSON 与日志，以及较早 af559/V5b/synthetic scratch。count focused logs（成功与首次 wrapper-path 失败）也保留。
- timing diag override/resolved Compose 与 launcher：compose-timing-diag-port-20261027.yaml、compose-timing-diag-resolved-20261027.yaml、run-t4-timing-diag-20261027.py。
- real-dump states/output：/home/dev/gateway-real-dumps/runs/p6-s1a-*，包括候选 t1–t4 state 文件；不得纳入 Git。

### Compose 容器与 volumes

各 Compose project 的 volume 后缀为 _backend-artifacts、_backend-control、_repository-service-data。以下项目在节点 docker ps -a 清单中保留；当前均已 Exited，volumes 未删除：

- ct108：p6-s1a-reviewfix-t4-7d0ce622、p6-s1a-af559-t4、p6-s1a-af559-t4-prof-20261027-a、p6-s1a-af559-t4-prof-20261027-b、p6-s1a-final-t4-retry-8e64af7ca4、p6-s1a-t4-97a4f5c、污染后停止的 p6-s1a-t4-clean-55363b37、p6-s1a-t4-measure-085b54ffdc、p6-s1a-timing-e52ad2。Docker replay containers：p6s1a-dolt-replay-654f114f5c80、p6s1a-dolt-replay-25d56605b4d8、p6s1a-dolt-replay-aee4cc1562fc。
- 05：p6-s1a-reviewfix-t1-7d0ce622、p6-s1a-reviewfix-t2-r1-7d0ce622、p6-s1a-reviewfix-t3-r1-7d0ce622、p6-s1a-af559-t1、p6-s1a-af559-t2、p6-s1a-af559-t3、p6-s1a-base-t1-5a2989、p6-s1a-final-t1-retry-8e64af7ca4、p6-s1a-final-t2-8e64af7ca4、p6-s1a-final-t3-8e64af7ca4、p6-s1a-t3-55363b37。
- 04：当前无 S1a Compose container/volume；保留门禁 worktree。

### Worktrees、branches、bundles 与 refs

- worktrees：开发主 checkout /home/dev/gateway-data-management-system；implementation /home/dev/gdds-p6-logs/s1a/impl-wt-553（handoff commit 在此）；诊断 /home/dev/gdds-p6-logs/s1a/timing-diag-wt。新增 reviewfix detached worktrees：05 /home/dev/gdds-p6-logs/s1a/05-reviewfix-7d0ce622-wt、ct108 /home/dev/gdds-p6-logs/s1a/ct108-reviewfix-7d0ce622-wt、04 /home/dev/gdds-p6-logs/s1a/04-reviewfix-7d0ce622-wt。04 门禁 worktree 按 DC51 保留。
- 04 旧 worktrees：04-final-wt-10753e7e5c、04-final-wt-8e64af7ca4、04-wt-55363b37、04-wt-6ea89b1c、04-wt-97a4f5c、final-af559-wt。
- 05 旧 worktrees：05-dc57-focused-wt-cbe32df8bb、05-dc57-preflight-wt-6c770d963b、05-dc57-preflight-wt-7b552981f8、05-dc57-preflight-wt-ec689eda0a、05-dc58-focus-wt-030e、05-final-wt-10753e7e5c、05-final-wt-8e64af7ca4、05-focus-wt-ac73504ad8、05-focused-wt-085b54ffdc、05-static-wt-04124576、05-static-wt-04dd7c3b78、05-static-wt-749e9bb5df、05-static-wt-f3e7fe7c74、05-wt、05-wt-10d21c0、05-wt-26b8db7、05-wt-2a7ad7b、05-wt-3332606、05-wt-478fa4d19b、05-wt-6ea89b1c、05-wt-7f43d2e、05-wt-97a4f5c、05-wt-a6938、05-wt-d05a29f646、05-wt-d84c2a7、05-wt-e868b1ad、05-wt-efd4b88、base-5a2989-wt、final-af559-wt、timing-diag-wt-2e2289、timing-diag-wt-8f429、timing-diag-wt-e52ad2。
- ct108 旧 worktrees：ct108-final-wt-10753e7e5c、ct108-final-wt-8e64af7ca4、ct108-measure-wt-04dd7c3b78、ct108-measure-wt-085b54ffdc、ct108-measure-wt-48cb02c5、ct108-real-wt-55363b37、ct108-wt、ct108-wt-55363b37、ct108-wt-97a4f5c、final-af559-wt、timing-diag-wt-e52ad2。
- branches/refs 保留：p6-s1a-impl、p6-s1a-timing-diag、审核分支 p6-s1a-review 与 S1a linked worktrees 建立的 p6-s1a-* refs；不移动、不删除。
- main checkout bundles：.p6-s1a-10d21c0.bundle、.p6-s1a-26b8db7.bundle、.p6-s1a-2a7ad7b.bundle、.p6-s1a-3332606.bundle、.p6-s1a-7f43d2e.bundle、.p6-s1a-97a4f5c.bundle、.p6-s1a-a6938cd.bundle、.p6-s1a-d84c2a7.bundle、.p6-s1a-efd4b88.bundle；.p6-s1a-a6938cd.bundle 的 05 日志目录副本也保留。
- /home/dev/gdds-p6-logs/s1a/ bundles（各节点存在的副本均保留）：55363b37e1.bundle、af559-s1a-candidate.bundle、e868b1ad47.bundle、impl-04124576d1.bundle、impl-04dd7c3b78.bundle、impl-30458dc835.bundle、impl-48cb02c5fb.bundle、impl-749e9bb5df.bundle、impl-f3e7fe7c74.bundle、p6-s1a-candidate-085b54ffdc.bundle、p6-s1a-candidate-10753e7e5c.bundle、p6-s1a-candidate-8e64af7ca4.bundle、p6-s1a-r5.bundle、p6-s1a-reviewfix-7d0ce622.bundle、p6-s1a-timing-diag-e52ad2.bundle、p6-s1a-timing-diag-{8f429,2e2289}.bundle、p6-s1a-impl-* bundles。
- Dolt measurement refs（保留）：p6s1a-measure-t4-v2-adaptive-4aa81c6c、p6s1a-measure-t4-v2-full-rebuild-d8051f1c、p6s1a-measure-one-percent-patch-5ca1060d、p6s1a-measure-one-percent-rebuild-f6b95153、p6s1a-measure-one-percent-patch-03104a47、p6s1a-measure-one-percent-rebuild-33260200、p6s1a-measure-one-percent-patch-a68c2883、p6s1a-measure-one-percent-rebuild-d94da7c8、p6s1a-measure-one-thousand-row-adaptive-464fa520、p6s1a-measure-one-thousand-row-rebuild-38ea0ee6；较早 refs p6s1a-measure-t4-v2-adaptive-9b743a3d、p6s1a-measure-t4-v2-full-rebuild-29ac9934、p6s1a-measure-one-percent-patch-2d2aa789、p6s1a-measure-one-percent-rebuild-d6744040、p6s1a-measure-one-percent-rebuild-48bb801d、p6s1a-measure-one-percent-patch-3b78d6bb、p6s1a-measure-one-percent-patch-7fae7b47、p6s1a-measure-one-percent-rebuild-92f23a4e；最终复测新增 p6s1a-measure-t4-v2-adaptive-bf271c37、p6s1a-measure-t4-v2-full-rebuild-88fca639、p6s1a-measure-one-percent-patch-0e863cc1、p6s1a-measure-one-percent-rebuild-151f22c2、p6s1a-measure-one-percent-patch-40b7fe80、p6s1a-measure-one-percent-rebuild-17090f1f、p6s1a-measure-one-percent-patch-06f50f48、p6s1a-measure-one-percent-rebuild-154d3b2c。synthetic preflight refs 与 scratch copy 内其它 refs 一并留给 owner。
- scratch：af559-dolt-batch-preflight、ct108-af559-mutation-replay-scratch-20261027、ct108-reviewfix-mutation-replay-scratch-7d0ce622、V5b scratch、旧 Dolt replay copies、py-spy/tool scratch 与其日志/JSON/profile artifacts；全部保留。

清理、ref 删除或栈/volume 移除均留待 owner 决定；本 handoff 不授权这些操作。

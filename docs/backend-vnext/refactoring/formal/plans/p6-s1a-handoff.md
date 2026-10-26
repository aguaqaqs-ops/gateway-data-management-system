# Phase 6 S1a handoff

状态：**STOPPED，S1a 未完成、未交独立阶段审核。** t4 v2 的 1% ordered-table patch 中位耗时高于整表重建，触发设计 §17 第 4 项停止条件。按要求未继续 worker step 归因、04 权威 runner、镜像重建或 Compose 门禁；本文记录现状并交 owner 决定后续设计/阶段处理。

## 候选与提交

- S0 比较基线：`5a2989bec2fbc269b0e567bcee4cc309513f90e4`。
- 实现分支：`p6-s1a-impl`。请求的 `p6-s1a` 名称已被既有 ref 占用，因此使用独立短期分支；主 checkout 的并行文档工作未触碰。
- S1a 产品实现提交：`55363b37e17be5a172262a6574e346dfd90c10d9`。
- 测量工具提交：`04124576d1a662280a8ac39bfb688a4a07c824dd`（ImportReplay→Mutation 行快照转换）、`749e9bb5df7148f6591a39f749eb40e77c08396f`（改用支持的 Dolt 命令）、`f3e7fe7c749a15cb313872f272d1c1fd17caa498`（只读取 parent X 行并为 D 保留 manifest 描述）、`04dd7c3b78f09c03dc78434e7f179108aee769e8`（从已验证 V5b artifact store 复用 parent snapshot）、`30458dc83517b742ac620a8eb16e17fd50752d2c`（读取 `SnapshotTable.descriptor`）。这些提交仅改 `vnext/backend/benchmarks/`，不改产品路径。
- 最后候选（未通过阶段验收）：`30458dc83517b742ac620a8eb16e17fd50752d2c`。另有本文档提交待写入；未推送、未打 tag、未改写已引用提交。上述提交均含要求的 `Co-Authored-By` trailer。

## Contract 与 golden

- Manifest 每表统一使用 `raw_content_digest`；`STORAGE_PROJECTION_VERSION` 为 `3`；移除 `ordering_digest` 与其 publication 传递，保留 `fast_row_digest`，去掉重复摘要计算。
- Preview / History 用表摘要、schema digest、storage view 与投影版本判定 U/X/A/D。Preview 的未变表不读取旧侧行；History 未变 ordered 表用当前侧规范行，并按两侧描述符形成的有效 pair 策略重算逻辑摘要与 occupancy 摘要。变化表与删除表按设计读取旧侧行。
- Submit 使用 `ADAPTIVE_PATCH`；有序 `GID_NO_V1` 表可按行修改。变化表依据 parent manifest 校验 parent 行，并在 prepare checkpoint 绑定 parent manifest digest；包 manifest 仍列全表。
- 直接修订 Canonical Storage、Storage Mutation、Ordered Diff、ADR 0014 与 ADR 0019 中标记 S1a 的条款；control DB 基线 schema 直接更新。没有兼容字段或双读写路径。
- Golden 只改 `storage-projection` 与 `mutation` 两组。7 个 mutation closure 与 6 个 storage-projection 文档更新，反映摘要/投影 Contract 的变化。导入包 golden 未变：该组 fixture 的最终包字节没有变化。未改其他 golden。

## 基线行消费者盘点

| 消费者 | 对未变表跳过的影响与处理 | 对应验证 |
| --- | --- | --- |
| Preview 基线物化与行比较 | 基线侧逻辑需求严格为 X∪D；U/A 不开旧表行。表级身份摘要仍由 catalog/manifest 提供。 | `test_unchanged_preview_table_does_not_read_baseline_rows`、`test_preview_reads_changed_and_deleted_baseline_tables_only`、`test_requested_tables_only_open_selected_rows_and_keep_full_catalog_summary`。 |
| 项目身份评估中的 `version_manager` | U 时复用当前侧规范行；身份变化落入 X 时仍读取旧行。不是可无条件跳过的旁路读取。 | `test_unchanged_identity_table_reuses_current_rows_without_baseline_read`，以及 changed/deleted 选择测试。 |
| Composite signal | 生成后的 composite canonical table 走同一套当前侧表身份与选择路径；U 从当前规范行复用/计算，X 与 D 按普通选择器读取旧侧。没有独立“始终读旧 composite”路径。 | `test_full_materialize_publishes_checkpoint_and_assemble_successor` 验证 materialize/checkpoint 中 composite 表；`test_missing_logics_xml_materializes_stable_empty_source` 验证稳定空 composite 来源；另有 t4 完整旅程覆盖 composite History。 |
| History 行比较 | 未缓存的 X 需 old-X 与 current-X；pair cache 命中可减少 kernel 比较，但不能改变层级逻辑需求。读取按 `(commit, 内容身份)` 合并去重。 | `test_changed_history_table_reads_both_pair_sides`。 |
| History 未变 ordered 单侧摘要 | U 中 ordered 表只用当前侧规范行；pair 有效策略仍由两侧描述符构造，provenance 规范化、facts 按既有结构填充，保留 degraded 语义。未复用 `_compare_single_side`。 | `test_unchanged_ordered_history_reads_current_side_and_preserves_facts`。 |
| History 删除表 / 表级处理 | D 需旧侧规范行用于整表浏览、导出和风险；不能因 Preview 的 U 过滤而跳过。 | `test_deleted_history_table_reads_only_the_old_pair_side`。 |
| DATASET_REPLACEMENT | 对 U 复用当前 artifact；X/D 依照替换所需的 pair 与表级输出读取旧侧。 | `test_dataset_replacement_reuses_current_artifact_for_unchanged_table`。 |
| checkpoint 与恢复 | 已发布 checkpoint 含物化侧 artifact，assemble 恢复直接读 checkpoint，不再访问 Repository；checkpoint 缺失时按 selector 重做需要的表。改变不增加新 baseline 行消费者。 | `test_assemble_resumes_from_checkpoint_when_repository_is_unavailable`、`test_assemble_resumes_from_materialized_sides_with_runtime_ruleset`、`test_full_materialize_publishes_checkpoint_and_assemble_successor`。 |
| Submit parent 行校验 | 属于 §4.3 单独需求：只对需要 mutation 的变化表读取 parent 行，并按 parent manifest 校验；不是 Preview/History U 过滤的例外。 | `test_repository_base_digest_reaches_mutation_planner`、Submit prepare/recovery focused tests；真实 t4 replay 尚待完成。 |
| 运行时规则与 catalog 绑定 | 只读取 catalog/描述符、provenance 与规则，不消费 baseline snapshot rows。 | projection / ruleset focused tests。 |

盘点未发现需修改 §4.2 过滤规则或 §16.2 计数口径的消费者。

## 计数断言与保值核对

计数按设计 §16.2：Preview 基线逻辑需求 `X∪D`，实际读取 `≤ |X|+|D|`；行比较派发 `=|X|`，表级处理 `=|A|+|D|`，kernel 调用 `≤|X|`。Submit 的表级计划为 `X∪A∪D`；patch 逻辑变更数按净 diff（key 变化计 DELETE+INSERT），重建写入 target 行数，删除表 DROP 一次且写入零行。focused 测试覆盖手算示例、边界阈值、增删表与跳过发布：

- `test_submit_count_examples_match_hand_computed_net_changes`
- `test_submit_table_level_counts_for_added_and_deleted_tables`
- `test_threshold_boundary_cases`
- `test_skipped_table_does_not_break_publication`

focused backend 运行：CT108-05，HEAD `55363b37e1`，149 passed / 50 deselected，16.56 秒；日志 `/home/dev/gdds-p6-logs/s1a/05-focused-55363b37e1-20261026.log`。t1–t4 完整旅程均 PASS；重复 Submit 均未产生 Repository operation。真实旅程计数见各自日志。受停止条件影响，未完成把每条 t4 worker step 与 §16.2 断言、History 实际读取计数逐项对账；不能把该项记作阶段验收通过。

保值项：focused Contract/golden 检查和 t1–t4 业务旅程中未观察到规范状态摘要、snapshot 与 bundle digest、ordered 逻辑摘要或 HTTP DTO 的变化；golden 变化仅在 S1a 指定的 mutation 与 storage-projection 两组。权威 runner 未运行，因此保值清单尚未完成最终门禁确认。原样重传 Submit：t1、t2、t3、t4 repeat-v1-submit 均无 Repository operation；t4 返回 `NO_CANONICAL_CHANGE`。

## 阈值、批量与 Dolt 表哈希

- 预期冻结规则：`changed_row_count <= 1,000` 且 `changed_row_count / max(before_rows, after_rows, 1) <= 1%`；INSERT 每条语句最多 256 行、最多 4 MiB。
- CT108，`gw-dms-test`，HEAD `30458dc83517b742ac620a8eb16e17fd50752d2c`，2026-10-26T19:45:35Z–20:16:51Z，测量工具 exit 1（工具在阈值失败时主动非零退出）。JSON：`/home/dev/gdds-p6-logs/s1a/ct108-s1a-mutation-replay-rerun6-30458dc835-20261026.json`；日志：`/home/dev/gdds-p6-logs/s1a/ct108-s1a-mutation-replay-rerun6-30458dc835-20261026.log`。
- 1% 边界样本为 `b1_n11_iec104_syx_list`：parent 9,822 行，target 9,828 行；t4 实际净变化 13 行，合成后为 98/9,828 = 0.99715%。Patch 为 92 UPDATE + 6 INSERT；整表重建为 9,822 DELETE + 9,828 INSERT。三轮交替总耗时：patch 1.530375 / 1.425461 / 1.457966 秒，中位数 **1.457966 秒**；重建 1.255599 / 1.210597 / 1.238513 秒，中位数 **1.238513 秒**。Patch 慢 **17.7%**，触发设计 §17 第 4 项；S1a 在此停止，阈值不得在本次验收中静默下调。三轮各自的 patch/rebuild table hash 均相等。
- t4 v2 全表 hash 对照：ADAPTIVE_PATCH 与整表重建分别对 312 张表全部匹配当前 t4 v2；两条路径相互等价。回放总耗时分别为 3.164501 秒与 27.446389 秒。此项通过，但不能抵消 1% 边界失败。
- 实测 INSERT 批量规则：上限 256 行 / 4 MiB；t4 自适应计划生成 108 条 INSERT 语句，最大语句 256 行 / 34,476 字节；全表重建生成 1,077 条，最大语句 256 行 / 399,520 字节。仍冻结为 256 行 / 4 MiB。
- 基线读取计时复用 CT108 V5b 成功报告（HEAD `48cb02c5fb0f6e157f703a9903ad2158fd28c81d`）：27 张 `X∪D` 表、139,838 行，74.857846 秒；mutation replay parent rows 从该已验证 artifact store 加载，并逐表以 v1 manifest 的 raw digest 与行数校验。
- 非证据的工具失败均保留：run1（17:13:10Z–17:39:30Z，ImportReplay/Mutation 行类型不匹配）；run2（17:43:31Z–18:18:18Z，不支持的 Dolt `symbolic-ref`）；run3（18:21:29Z–18:42:51Z，误读未变化 `adv_app_list` 时 Repository Service Arrow 流中止）；run4（18:50:26Z–19:11:52Z，读取变化表 `b1_n11_iec104_syx_list` 的 Arrow 流三次中止，发生在 replay refs 创建前）；run5（19:22:01Z–19:44:00Z，辅助代码错误访问 `SnapshotTable.manifest`，refs 创建前失败）。全部 JSON 与日志路径保留在 `/home/dev/gdds-p6-logs/s1a/`。最终 rerun6 完成全表 hash 与三轮阈值 replay，但因 §17.4 失败而非零退出。

## t1–t4 真实旅程

所有旅程使用同一 S1a 产品代码树 HEAD `55363b37e1`；后续提交只调整 benchmark 工具。真实数据不进入 Git。

| 档位 | 节点与运行 | Preview / Submit / History 摘要 | 证据 |
| --- | --- | --- | --- |
| t1 | CT108-05，2026-10-26 12:49:07–12:54:12Z，PASS | v1 Preview 42.156s、Submit 42.190s；重复 Preview 32.119s、changed=0/125 表；重复 Submit 42.194s，无 Repository operation；v2 Preview 38.142s、changed=4/125；Submit 42.194s；History 22.072s。 | `/home/dev/gdds-p6-logs/s1a/05-t1-55363b37e1-20261026.log` |
| t2 | CT108-05，2026-10-26 12:54:55–13:31:52Z，PASS | v1 Preview 453.613s、Submit 194.850s；重复 Preview 240.847s、changed=0/209；v2 Preview 399.400s、changed=57/220；Submit 357.538s；History 292.849s。 | `/home/dev/gdds-p6-logs/s1a/05-t2-55363b37e1-20261026.log` |
| t3 | CT108-05，2026-10-26 13:33:41–14:45:47Z，PASS | v1 Preview 772.693s、Submit 351.518s；重复 Preview 571.996s、changed=0/192；v2 Preview 909.172s、changed=54/193；Submit 556.391s；History 583.668s。 | `/home/dev/gdds-p6-logs/s1a/05-t3-55363b37e1-rerun-20261026.log` |
| t4 | CT108，2026-10-26 14:41:11–16:14:21Z，PASS | 320 source tables，composite 435 rows；v1 Preview 1565.362s、Submit 564.415s；重复 Preview 903.121s、changed=0/312；重复 Submit `NO_CANONICAL_CHANGE`、无 Repository operation；v2 Preview 1057.637s、changed=26/312；Submit 289.241s；History 320.906s、168 records。 | `/home/dev/gdds-p6-logs/s1a/ct108-t4-clean-55363b37-20261026.log` |

此前 t3 第一次运行因缺少 `GATEWAY_REAL_DUMP_ROOT` 在 Compose 前退出，随后完整 rerun PASS；此前两次 t4 探索运行曾中止，均非验收证据。当前 t4 PASS 是完整独立旅程。

## V5b 与 worker step 归因

V5b 正确 endpoint 的完整测量：CT108，HEAD `48cb02c5fb`，2026-10-26T16:32:02Z–17:12:05Z，exit 0，六段，JSON `/home/dev/gdds-p6-logs/s1a/ct108-s1a-v5b-rerun2-48cb02c5.json`，日志 `/home/dev/gdds-p6-logs/s1a/ct108-s1a-v5b-rerun2-48cb02c5-20261026.log`。

- v1 full baseline：312 tables / 246,794 rows，294.414s wall / 235.041s thread CPU；其中 Repository reads、Python materialize/digest、artifact I/O 待由 JSON 分项列出。
- v2 S1a selected baseline：27 个逻辑变化/删除表、139,838 rows，74.858s / 65.526s CPU；catalog 仍有 312 tables，Catalog/RS 查找 9.712s，Python materialize/digest 64.496s。26 张变化表加 1 张删除表，`X∪D=27`。
- v1 Preview pair pipeline 501.204s；records closure 生成 316.683s、全量回读 98.328s、bundle 41.946s。v2 pair pipeline 39.906s，records closure 生成 1.073s、回读 0.097s、bundle 2.002s。
- Submit build-input 测量仍逐表读取并验证冻结的 312 张表、246,874 rows，用时 66.068s；这属于 Submit 当前冻结行校验成本，不计作 Preview/History 的 U baseline 读取。
- V5b 旧报告中的约 75s baseline 残差由 selected baseline materialization 解释。约 100s assemble 与约 36s Submit prepare 的最终 S1a worker step 对照、每段 step 间隔来源、削减方案/处理阶段/owner 尚未完成；由于 §17.4 已触发停止，未继续读取 control DB 时间线或添加产品插桩。该项交 owner 决定如何处理后续阶段。

V5b 第一次调用错误地把 backend host `127.0.0.1:8000` 当成 Repository Service endpoint，运行 640.034s 后在 catalog load 失败；API 缺少 RS 协议头，未作为测量证据。修正为实际 RS 容器 IP 后，上述 rerun PASS。失败日志与数据保留。

## Runner、镜像与门禁

- 五个 Python 包 Ruff + mypy：CT108-05，HEAD `30458dc83517b742ac620a8eb16e17fd50752d2c`，2026-10-26T19:45:06Z–19:45:08Z，exit 0；backend 486 source files、repository_service 200 source files。日志 `/home/dev/gdds-p6-logs/s1a/05-static-30458dc835-20261026.log`。较早 HEAD `04124576d1` 与 `749e9bb5df` 的静态检查也通过，日志见 `/home/dev/gdds-p6-logs/s1a/`。
- 04 六包权威 runner、逐包 manifest、repository-service 镜像重建及 Compose 门禁均**未运行**：§17.4 已要求停止后续验收。不得将 S1a 标为通过。

## 偏差、未决与保留内容

- `p6-s1a` branch 名被已有 ref 占用，使用 `p6-s1a-impl`；没有删除或移动 refs。
- 用户要求本任务不再运行任何删除文件或 ref 的命令；所有 bundles、refs、worktrees、Dolt refs、scratch 与日志均保留。Owner 后续清理清单：主 checkout `.p6-s1a-a6938cd.bundle`、05 副本、`impl-04124576d1.bundle`、`impl-749e9bb5df.bundle`、`impl-f3e7fe7c74.bundle`、`impl-04dd7c3b78.bundle`、`impl-30458dc835.bundle` 及其测试节点副本；S1a 分支 refs（包括本地 `p6-s1a-impl`、05/CT108 的 `p6-s1a-impl-04dd7c3b78` 与 `p6-s1a-impl-30458dc835`）；下列 mutation refs；所有 05/CT108/04/本地 worktrees、t4 Compose 栈与 volumes、artifact scratch、失败/成功日志、profile、静态检查环境。**本任务没有清理这些内容。**
- Mutation Dolt refs：`p6s1a-measure-t4-v2-adaptive-9b743a3d`、`p6s1a-measure-t4-v2-full-rebuild-29ac9934`、`p6s1a-measure-one-percent-patch-2d2aa789`、`p6s1a-measure-one-percent-rebuild-d6744040`、`p6s1a-measure-one-percent-rebuild-48bb801d`、`p6s1a-measure-one-percent-patch-3b78d6bb`、`p6s1a-measure-one-percent-patch-7fae7b47`、`p6s1a-measure-one-percent-rebuild-92f23a4e`。
- 05 早前创建 `legacy` symlink 时曾误用 `ln -sfn`；目标仍指向既有 `legacy` 目录。后续均先检查路径再创建，不替换 symlink。
- 本阶段运行生成的 t4 Compose 栈、Dolt 测量分支、profile/diagnostic 文件、benchmark scratch、静态检查环境及测试节点工作树均保留，不在本任务内删除。
- 阶段审核未启动，因为验收按设计 §17.4 停止；owner 需先决定 1% 规则的设计处理方式，再明确是否继续 S1a 或修订设计后重启验收。本文不是阶段退出证据。

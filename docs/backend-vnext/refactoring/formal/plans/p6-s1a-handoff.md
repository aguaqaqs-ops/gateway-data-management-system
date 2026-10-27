# Phase 6 S1a handoff

## 当前停止状态（2026-10-27）

状态：**S1a 未完成，未交独立阶段审核。** 04 六包权威 runner 在候选 HEAD `8e64af7ca43438a8e2b40e59d0bf86e7e404c244` 上 exit 1；History Compose focused 复现 comparison digest 不保值，触发 §4.1 停止条件。停止后续验收，不启动 V5b、不重跑门禁。阈值复测与 t4 v2 Dolt 表哈希通过，见下文。

- 实现分支 `p6-s1a-impl`；已用 merge commit 合入 `main` 的 `45b169de6a`：`8b18758fd20d7a4fdc8250e16ff30e444f45da77`，无 rebase；未推送、未打 tag。
- 最终候选同 HEAD 真实旅程：t1、t2 在 05 PASS；t3 在 v2 Preview、t4 在 v2 Preview 期间按停止条件中断。t1 start 02:54:47Z、History 成功于 02:59:49.951Z，benchmark 输出 `conclusion=PASS`（其 wrapper 未写 end/exit 标记）；t2 start 03:01:29Z、end 03:37:57Z、exit 0。日志：`/home/dev/gdds-p6-logs/s1a/05-t1-final-retry-8e64af7ca4-20261027.log`、`05-t2-final-8e64af7ca4-20261027.log`、`05-t3-final-8e64af7ca4-20261027.log`、`ct108-t4-final-retry-8e64af7ca4-20261027.log`。t3 脚本 exit 130；t4 被 SIGINT，日志未写脚本 exit 标记。两栈仅停止服务，容器与 volumes 保留。
- 04 固定 DC48 环境六包 runner：rust、shared_kernel、repository_contracts、repository_client、repository_service 通过；backend 的 `test_compose_history_compare_journey_zero_write_restart` 失败，整轮 `runner_exit=1`。日志 `/home/dev/gdds-p6-logs/s1a/04-runner-retry-8e64af7ca4-20261027.log`，2026-10-27T03:16:20Z–03:51:34Z。第一次 runner 因残留 `GATEWAY_DOCKER_BUILD_NETWORK=host` 导致 BuildKit `network.host` 权限错误，exit 1，日志 `/home/dev/gdds-p6-logs/s1a/04-runner-8e64af7ca4-20261027.log`；随后清除此变量重跑。
- History focused 在 04 clean detached worktree 中复现，日志 `/home/dev/gdds-p6-logs/s1a/04-focused-history-digest-debug3-8e64af7ca4-20261027.log`，04:09:52Z–04:13:39Z，exit 1。checkpoint 与本地 oracle 的表名、行数、`raw_content_digest` 相同；checkpoint 两侧 snapshot digest 为 `sha256:d679512e7025c931a6a366e3da24bfa2fd47226cc992aa732337c8aacc1d0379` / `sha256:2c99660c0927056f5b13740dfaef86e8d40942881db98ecbf950f99e0f4e29e0`，本地完整行重算为 `sha256:f197994536a19425a2feb32e8a353b9618cda5075ad79046c7abf8ce247bb83f` / `sha256:101cd0a307d70ea1e398f814f42dad515f2269b1edc78bc3b1cd241eddf4b7b7`。S1a 的 `canonical_binding_for_commit` 将提交元数据的 `snapshot_digest` 传入 History materializer；comparison digest 直接包含两侧 snapshot digest。该差异违反 §4.1 comparison digest 保值项；需要 owner 决定后续处理，本阶段未修改设计、计划、决议或 golden。
- 04 已重建 repository-service 镜像，日志 `/home/dev/gdds-p6-logs/s1a/04-rebuild-8e64af7ca4-20261027.log`；image revision 为 `8e64af7ca43438a8e2b40e59d0bf86e7e404c244`，image ID `sha256:d351b00712f15e30bb54f2d3566bc857fbf5ce78a2e9f9a187c43f68cddea077`。失败 runner 不是本阶段门禁通过证据。
- 相对 `55363b37e1` 的 `55363b37e1..8e64af7ca4` 变更文件完整清单：
  - 合并自 `main` 的文档：`docs/backend-vnext/refactoring/formal/plans/p6-design.md`、`p6-execution-plan.md`、`p6-s0-owner-decisions.md`、`p6-forwardtable-blank-rows.md`、`p6-keyless-candidate-census.md`、`p6-keyless-candidate-rules-review.md`、本 handoff。
  - Benchmark：`vnext/backend/benchmarks/p6_s1a_dolt_batch_preflight.py`、`p6_s1a_mutation_replay_measurement.py`、`real_dump_forwardtable_blank.py`、`real_dump_journey.py`、`s5_v5b_segment_measurement.py`。
  - 产品源码：`vnext/backend/src/gateway_backend/capabilities/mutation_planning/_repository_replay_renderer.py` 与 `vnext/repository_service/src/gateway_repository_service/versioned_read/arrow_bridge.py`。第二项只在 Arrow worker 捕获异常时记录异常类型与消息，不记录行数据。
  - 测试与 golden：`vnext/backend/tests/test_dolt_renderer.py`；`vnext/fixtures/golden/mutation/renderer/valid/destructive-delete/expected.sql`、`mixed-scalars/expected.sql`、`multi-table-patch/expected.sql`、`patch-single-update/expected.sql`、`rebuild-replace-rows/expected.sql`。
- DC57 变更提交：合并 `8b18758fd2`；预检工具 `7b552981f8`、边界修正 `24136e4e53`、隔离 Dolt 配置 `6c770d963b`、逐候选 EXPLAIN 证据 `ec689eda0a`；渲染器实现与 mutation golden `cbe32df8bb`。RS/回放修复提交为 `085b54ffdc746d2ea3b7ccd1a610c629ddd4d28a`，t4 操作计时工具提交为 `ac73504ad8b44f43322aaf12a8df38caf3800a57`，当前 HEAD 为 `8e64af7ca43438a8e2b40e59d0bf86e7e404c244`。提交均带规定的 Co-Authored-By trailer，未推送、未打 tag。

### Dolt 批量语句预检

- 节点 `ct108-gw-dms-05`（hostname `gw-dms-test-05`），Dolt `2.1.11`，HEAD `ec689eda0aa520050fdf1f01a35422adc7e281d5`；2026-10-26T23:59:29Z–2026-10-27T00:00:24Z，exit 0。日志 `/home/dev/gdds-p6-logs/s1a/05-dc57-preflight-ec689eda0a-20261027.log`，JSON `/home/dev/gdds-p6-logs/s1a/05-dc57-preflight-dolt-ec689eda0a-20261027/report.json`。
- 合成表覆盖单列主键 `id`、复合主键 `(k1,k2)` 和 `gid` 为存储主键的 ordered/GID_NO_V1 形态。分别执行逐行基准、按批 DELETE+INSERT、按批 upsert+DELETE，以及生产候选 CASE UPDATE+DELETE+普通 INSERT。所有形式在三种表形态上可执行；结果表哈希与逐行基准相同，`dolt_diff` 将 256 个同键行标为 modified，并正确报告 256 removed / 256 added；单行字节边界样本也显示 modified。
- 查询计划：Dolt 2.1.11 对经典 `EXPLAIN` 的 DML/SELECT 在此 CLI 返回空计划，因此预检用 `EXPLAIN ANALYZE SELECT` 对每条候选完全相同的主键谓词检查查找计划。单列、复合元组 IN、ordered gid 查找均显示 `IndexedTableAccess`，无 `TableScan`。这是本版本可取得的主键访问证据；DML 本身的经典 EXPLAIN 不提供可读计划。
- 256 UPDATE + 256 DELETE + 256 INSERT 场景耗时：逐行 768 条语句约 4.45–4.85 秒；CASE UPDATE 三条、DELETE+INSERT 四条、upsert 三条分别约 0.12–0.16 秒。另测接近 4 MiB 的 payload（4,194,048 字节），候选语句不超过 4,194,304 字节，哈希和 diff 等价。选择生产 CASE 批量 UPDATE + 主键 IN 批量 DELETE，INSERT 保持 256 行 / 4 MiB：保留 UPDATE/DELETE/INSERT 的独立语义，避免以 DELETE+INSERT 代替更新，也不把 INSERT 语义折叠进 upsert。
- 预检第一次运行在测试工具批边界生成重复主键，exit 非零；修复后正式运行通过。探索性 smoke 曾因隔离 Dolt HOME 缺少身份失败，后续补上固定配置；上述均不是产品失败。工具与合成 repository/ref 保留。

### 渲染器与 focused 验证

- 同一表的 UPDATE 与 DELETE 按最多 256 行或最多 4 MiB 语句字节分批；复合键 DELETE 使用 tuple IN，UPDATE 用 CASE 并以主键 IN 限定行；keyless 整表 DELETE 语义及表/op 顺序保留。INSERT 规则沿用 256 行 / 4 MiB。规划器与 §16.2 计数逻辑未改。
- focused 测试覆盖 257 行批边界、复合键、ordered gid 主键、混合 DELETE/UPDATE/INSERT 与 UPDATE/DELETE 字节边界；只更新 mutation renderer 的五个 expected.sql golden。
- 节点 `ct108-gw-dms-05`，HEAD `cbe32df8bbff5ffe247044390dc3f0c9fff3ba45`，2026-10-27T00:07:38Z–00:08:20Z，Ruff backend 全包与 mypy（486 source files）通过；focused pytest 80 passed、1 deselected，5.52 秒。日志 `/home/dev/gdds-p6-logs/s1a/05-dc57-focused-cbe32df8bb-20261027.log`。`test_submit_prepare_removed_tables.py` 带 integration marker，在本次 `-m unit` 命令中 deselected。

### RS Arrow 中止调查与影响

- **已确认根因：测量工具污染了 RS 正在服务的 Dolt 仓库文件属主。** run3/run4 的回放工具曾以 root 经 `docker exec` 在该 live repository 上执行 `dolt branch/checkout/sql/add/commit`，把 `.dolt/noms/manifest`（模式 600）、`repo_state.json`、`.dolt/tmp` 等改成 root 所有；以 `gateway` 用户运行的 RS 随后读取失败，请求开始约 40 ms 即中止。run1/run2 之前的 t4 旅程与 V5b RS 读取成功；run3/run4 的中止与表无关，不能作为某张表或 RS 正常产品读取路径失败的证据。
- **测量工具已修正：** `085b54ffdc` 起，live repository 仅经 RepositoryClient resolve main，并在测量前后核对 ref；工具用 `docker cp` 把仓库复制到 scratch，在 `--network none` 的隔离容器中进行 branch/checkout/SQL/add/commit/hash 回放。parent rows 通过 RS HTTP Arrow 产品路径读取，不从 V5b 存储加载；其输出确认 requested/materialized 均为全部 27 张 `X∪D` 表。scratch 与隔离容器信息见 `/home/dev/gdds-p6-logs/s1a/ct108-mutation-replay-085b54ffdc.json`。
- **RS 诊断已加：** `arrow_bridge.py` 的 `_run_worker` 捕获异常时记录异常类型和消息，不记录行数据；focused 测试断言日志不含合成行值。CT108-05 的 2 个 focused 用例通过，repository_service Ruff 与 strict mypy 通过，日志 `/home/dev/gdds-p6-logs/s1a/05-focused-085b54ffdc-20261027.log`。变更是诊断，不改 RS 读取语义或重试策略。
- 被污染的旧栈 `p6-s1a-t4-clean-55363b37` 已按 owner 授权仅执行 `docker compose stop`，三个容器和 volumes 均保留；停止记录 `/home/dev/gdds-p6-logs/s1a/ct108-stop-contaminated-55363b37-20261027.log`。其后新建栈 `p6-s1a-t4-measure-085b54ffdc`，t4 完整旅程 PASS；阈值回放全程只对仓库副本写入，live main 前后相同。
- 最终候选上的 t3 栈 `p6-s1a-final-t3-8e64af7ca4` 与 t4 栈 `p6-s1a-final-t4-retry-8e64af7ca4` 均在 2026-10-27T04:16:33Z 后停止服务，保留容器和 volumes。t4 的 `docker compose stop` exit 0；t3 的 Compose stop 客户端挂起，随后对其三个容器执行 `docker stop --timeout 1`，命令 exit 0，容器状态为 worker 137、backend 0、repository-service 137。没有删除容器、volume、ref 或文件。
- Submit 的 `import_publication._materialize_parent_rows` 对变化且可 patch 的表经 RS 读 parent rows，再按 parent manifest 校验；27 张 `X∪D` 全部读成功，其中含 `b1_n11_iec104_syx_list`。History 的 `_materialize_commit` 请求 X 两侧、D 旧侧和未变 ordered 当前侧。候选 t4 在 v1 Preview/Submit、重复 v1 Preview 后进入 v2 Preview；因 History comparison digest 保值失败而提前中断，未完成候选上的 v2、History 或归因。
- 对应测试：`test_requested_tables_only_open_selected_rows_and_keep_full_catalog_summary`、`test_changed_history_table_reads_both_pair_sides`、`test_deleted_history_table_reads_only_the_old_pair_side`、`test_unchanged_ordered_history_reads_current_side_and_preserves_facts`、Arrow bridge worker failure focused test、repository client 的 before/after-bytes retry 测试。它们验证选择与错误传播；本次 27/27 产品路径读取是 t4 实测证据。

### 尚未完成的验收及资源

- 目前已在新渲染器与 RS 正式读取路径上完成阈值复测与 t4 v2 全表哈希复核；数值见“阈值、批量与 Dolt 表哈希”。1,000 行样本在 9,822 行表上占 10.175%，故按双门槛选择重建；未把它描述成 1% patch 性能样本。
- 候选 `8e64af7ca4` 的 t1/t2 PASS，t3/t4 因 History 保值停止条件中断；04 镜像重建已完成但六包 runner exit 1；V5b 最终候选补测、worker step 归因和阶段门禁未完成。未完成前不交独立阶段审核。
- `p6-s1a-t4-clean-55363b37` 旧污染栈已停止但保留；`p6-s1a-t4-measure-085b54ffdc`、`p6-s1a-final-t3-8e64af7ca4`、`p6-s1a-final-t4-retry-8e64af7ca4` 均保留容器与 volumes。所有 worktrees、Dolt refs、日志、artifact scratch、bundles 与 Git refs 由 owner 后续清理；本任务不运行任何删除文件或 ref 的命令。原 `.p6-s1a-a6938cd.bundle` 主 checkout 副本及 05 日志目录副本继续保留。

---

## DC57 之前的阶段记录（历史）

以下记录来自 DC57 合入前的候选 `30458dc83517b742ac620a8eb16e17fd50752d2c`。其中“1% 慢于重建并触发停止”针对旧逐行 renderer；按 DC57 必须在批量 renderer 上复测，不能沿用为当前阈值结论。

历史状态：**STOPPED，S1a 未完成、未交独立阶段审核。** t4 v2 的 1% ordered-table patch 中位耗时高于整表重建。按当时的设计版本未继续 worker step 归因、04 权威 runner、镜像重建或 Compose 门禁。

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

- 冻结策略：仅当 `changed_row_count <= 1,000` **且** `changed_row_count / max(before_rows, after_rows, 1) <= 1%` 时使用 PATCH_DML。INSERT、UPDATE、DELETE 每条语句均最多 256 行且不超过 4 MiB；超出任一批边界时拆分。该规则与 mutation planner / renderer 常量一致；§16.2 的逻辑变更计数不变。
- 正式阈值复测：ct108（hostname `gw-dms-test`），Dolt `2.1.11`，HEAD `085b54ffdc746d2ea3b7ccd1a610c629ddd4d28a`，测量 JSON 时间 2026-10-27T02:10:20Z–02:42:47Z、exit 0。日志 `/home/dev/gdds-p6-logs/s1a/ct108-mutation-replay-direct-085b54ffdc-20261027.log`；JSON `/home/dev/gdds-p6-logs/s1a/ct108-mutation-replay-085b54ffdc.json`。测量工具完整运行 1,955.187 秒；测量前后 RS main ref 一致；所有 Dolt mutations、branches 和 hash replay 仅在 scratch 仓库副本执行。
- RS parent read：请求并成功物化全部 27 张 `X∪D` 表，合计 139,838 行（26 张 X + 1 张 D），含 `b1_n11_iec104_syx_list`。RS HTTP Arrow 产品路径总读取约 9.797 秒，ArtifactStore 与 readback 合计约 0.75 秒；Python materialize/digest remainder 约 63.895 秒。`repository_main_unchanged=true`，副本回放容器已停止并保留。
- 1% 边界样本 `b1_n11_iec104_syx_list`：parent 9,822 行、target 9,828 行、t4 实际净变化 13 行；测试净变化 98 行，即 0.99715%。Patch 为 92 UPDATE + 6 INSERT；整表重建为 9,822 DELETE + 9,828 INSERT。交替三轮 patch 总耗时 0.600049 / 0.605835 / 0.619870 秒，中位数 **0.605835 秒**；重建为 1.255938 / 1.194844 / 1.235459 秒，中位数 **1.235459 秒**。Patch 中位数快约 51%；每轮 patch/rebuild 表哈希相等。1% 未触发 §17.4 停止条件。
- 1,000 行上限样本：同一表合成 1,000 个变化，parent 9,822 / target 9,828，变化率 10.175%。由于超过 1% 比例门槛，ADAPTIVE_PATCH 正确回退为 REBUILD_TABLE；adaptive 与重建哈希相等，耗时分别 1.277966 / 1.252483 秒。该样本验证 1,000 变化数下双门槛派发正确；它不是 1% patch 的性能样本。
- t4 v2 全表哈希：26 张 X + 1 张 D，目标共 312 张表。ADAPTIVE_PATCH 与整表重建各自对当前 t4 v2 匹配 **312/312**，两条路径结果相同；回放总耗时分别 **2.514646 秒**与 **27.384033 秒**。Adaptive 计划 15 张整表重建，行级 mutation 为 21,974 DELETE、22,054 INSERT、84 UPDATE；整表重建写入 246,874 行。
- 批量实测：合成预检在单列键、复合键与 GID_NO_V1 ordered 三类表验证每种批量语句语法、主键查找计划、Dolt 哈希与 diff；生产形式 CASE UPDATE + 主键 IN DELETE + 多值 INSERT 均通过。256 UPDATE + 256 DELETE + 256 INSERT 场景，生产候选用约 0.12–0.16 秒，逐行 768 语句约 4.45–4.85 秒；近 4 MiB 样本为 4,194,048 字节且仍在限制内。故冻结三类 mutation 每批 256 行 / 4 MiB。
- 之前按逐行 renderer 测得 1% 慢约 17.7% 的结果保留为 DC57 历史依据，不再作为当前停止条件；本次同样本批量复测已通过。此前 run1–run5、测量 launcher import 失败及 DC57 预检探索失败日志均保留。run3/run4 的 Arrow 中止根因是 root 写 live RS repo 后污染文件属主，非表特异；细节见“RS Arrow 中止调查与影响”。

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
- 04 已重建 repository-service 镜像，并运行六包权威 runner；该轮 exit 1（backend History Compose digest assertion failed，其余五包通过）。逐包 manifest 与 Compose provenance 保留在节点日志/worktree 外部位置。因为 §4.1 保值项失败，不得将该轮标为门禁通过，也不得继续 S1a 阶段审核。

## 偏差、未决与保留内容

- `p6-s1a` branch 名被已有 ref 占用，使用 `p6-s1a-impl`；没有删除或移动 refs。
- 用户要求本任务不再运行任何删除文件或 ref 的命令；所有 bundles、refs、worktrees、Dolt refs、scratch 与日志均保留。Owner 后续清理清单：主 checkout `.p6-s1a-a6938cd.bundle`、05 副本、`impl-04124576d1.bundle`、`impl-749e9bb5df.bundle`、`impl-f3e7fe7c74.bundle`、`impl-04dd7c3b78.bundle`、`impl-30458dc835.bundle` 及其测试节点副本；S1a 分支 refs（包括本地 `p6-s1a-impl`、05/CT108 的 `p6-s1a-impl-04dd7c3b78` 与 `p6-s1a-impl-30458dc835`）；下列 mutation refs；所有 05/CT108/04/本地 worktrees、t4 Compose 栈与 volumes、artifact scratch、失败/成功日志、profile、静态检查环境。**本任务没有清理这些内容。**
- Mutation Dolt refs：`p6s1a-measure-t4-v2-adaptive-9b743a3d`、`p6s1a-measure-t4-v2-full-rebuild-29ac9934`、`p6s1a-measure-one-percent-patch-2d2aa789`、`p6s1a-measure-one-percent-rebuild-d6744040`、`p6s1a-measure-one-percent-rebuild-48bb801d`、`p6s1a-measure-one-percent-patch-3b78d6bb`、`p6s1a-measure-one-percent-patch-7fae7b47`、`p6s1a-measure-one-percent-rebuild-92f23a4e`。
- 05 早前创建 `legacy` symlink 时曾误用 `ln -sfn`；目标仍指向既有 `legacy` 目录。后续均先检查路径再创建，不替换 symlink。
- 本阶段运行生成的 t4 Compose 栈、Dolt 测量分支、profile/diagnostic 文件、benchmark scratch、静态检查环境及测试节点工作树均保留，不在本任务内删除。
- 阶段审核未启动，因为验收按设计 §17.4 停止；owner 需先决定 1% 规则的设计处理方式，再明确是否继续 S1a 或修订设计后重启验收。本文不是阶段退出证据。

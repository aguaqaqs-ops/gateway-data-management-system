# Phase 6 S1b 第 1 次独立复审

- 结论：**定向修订**。
- 日期：2026-10-28。
- 代码候选 H：`afbfaea8e2154326e25c29091f34ffb3c12cd8ab`；handoff 提交：`b96258c768d7e7bd8ea888587bfb4f09c650b927`。
- 复审区间：`705b17c1a137ede6b4339376527b30a4c58288f7..afbfaea8e2154326e25c29091f34ffb3c12cd8ab`；handoff 后续提交仅更新文档。
- 依据：[首次审核](p6-s1b-independent-review.md)、[第二审核人报告](p6-s1b-independent-review-b.md)、[handoff](p6-s1b-handoff.md)、P6 设计 §5.1/§5.2/§5.4/§16.2、DC62、Comparison Bundle Contract。

## 1. 结论摘要

F1–F3 关闭。F4 的 repository cache hit 免读路径已实现，但恢复 History 比较的按需选择后，未变化表被同时排除在整表导出和 bundle 之外；新增 F5 阻塞 S1b exit。N1-2 的真实缓存复用证据可关闭，N1-1 仍待 owner 处置。当前不能打 exit tag 或进入下一实施阶段。

本次在 05 独立复跑相关测试，159 passed、1 warning；另用现有 History harness 复现 F5。权威 runner 与 t1–t4 的成功记录属实，但现有测试没有验证最终 History bundle 的全表绑定覆盖，不能据此关闭 F5。

## 2. Findings 与关闭判定

### F1：关闭——取消等待覆盖线程和请求准入生命周期

`multipart_upload.py:55–90` 将受理放入独立 task，以 `asyncio.shield` 等待；收到原生 cancellation 后继续等待该 task，取出结果或异常，再传播取消，最后清理暂存目录。外层 route 的准入上下文因此保持到等待结束。正常返回和异常路径亦保留 finally 清理。

独立复跑 `test_direct_task_cancellation_waits_for_upload_acceptance_before_cleanup` 通过：Event 暂停线程，直接取消外层 task 后仍保留暂存文件和准入名额，完成后才释放。该测试 mock 同步受理函数，证明生命周期和清理次序；不把它表述为真实 DB 事务故障注入。同步事务实现未在本轮改变。

### F2：关闭——共有完整行投影保留排除列与行的关联

`standard.py` 与 `ordered.py` 的新增分支改为共有完整行 multiset。交换 aux 值时 id/gid 等共有行信息仍进入摘要；新列不进入投影，物理顺序不影响结果。keyless additive 分支同时按非排除共有列判定行记录，再以完整共有行投影保留 summary-only 变化。

独立复跑 keyed/keyless 共享参数案例、ordered 案例及 surface/risk 测试通过：交换排除值得到内容变化，只有新增列和物理重排仍未变化。

### F3：关闭——标签精确比较，兼顾不新增列的替换

`row_encoding.py:410` 起的 `_column_signature` 先解析 ENUM/SET，返回规范化的类型关键字与原始标签 tuple；不再将标签整体 upper。原始大小写/改名替换不能短路为兼容。真正严格增加标签仍由 `_enum_set_addition` 判定。

独立复跑新增共享参数、risk 与 surface 案例通过，覆盖带/不带新增列的替换及真正只增标签，满足第二审核人扩大的关闭标准。

### F4：免读机制已修正，但整体关闭受 F5 阻塞

`repository_ref.py:223–325` 在读表前由 canonical identity、目录 schema、ordered metadata 等构造精确 cache key；命中经 `open_cached_snapshot_table` 校验后复用 Parquet，miss 回退 reader。focused 计数案例证明选中表的 hit 不建 reader，miss 只读对应表并回填；原来的 repository 行读取后才查缓存问题已修正。

然而 `_history_requested_tables` 只表达“比较需要哪些行”，其输出目前也决定“哪些表可以进入 bundle”，见 F5。因此不将 F4 整体登记为已关闭。修正应同时满足免读和完整输出，不能通过跳过输出降低耗时。

### S1b-F5 [P2]：History 恢复按需读取后，bundle 丢失未变化表

- 类型：已证实回归；阻塞：是。
- 位置（H）：`vnext/backend/src/gateway_backend/application/history/compare_jobs.py:751–761`、`:798–801`；相关消费路径为 `snapshot_materialization/repository_ref.py:244`、`:328–341` 和 `application/preview_jobs.py:1729` 起的 `include_all_tables` 分支。
- 依据：设计 §5.2 与 `contracts/comparison-bundle.md:229` 要求 **History 每个节点闭合全部表**，内容共享不丢失各节点/侧的表名绑定。§16.2 的免读要求不取消整表打包。
- 触发：两个 History 节点都只有同一张普通表 `t`、同一行 `(1,)`，schema/content/storage view 均相同。无论缓存冷暖，该表都不会进入 `requested_by_commit`。
- 根因：`_history_requested_tables` 对未变化普通表执行 `continue`；repository cache 查询也只遍历 `selected_set`。未选中的表只有 summary descriptor，`table=None`，不进入 `table_set.tables`。随后 `include_all_tables=True` 仅遍历这个已经裁剪的 table set，无法恢复遗漏表，也不检查它是否覆盖 summary 中所有表。未变化 ordered 表还存在只选 current、遗漏 before 绑定的同类路径。
- 本次最小复现：在 H 的 clean detached worktree，用已有 `build_history_compare_harness` 和 `run_full_history_compare_job` 跑默认双节点单表场景。operation 为 **SUCCEEDED**，bundle 为 **READY**，pair summary 为 **table_count=1 / changed_table_count=0**；最终 `closure_entries` 仅含 **SURFACE、RECORDS_CLOSURE** 两项，**SNAPSHOT_TABLE=0**。预期至少有一份 Parquet row file，并保留 `t` 的 before/current 两个绑定（允许共享同一文件）。
- 证据：开发节点 `/home/dev/gdds-p6-logs/s1b/review-r1-history-repro.log`；执行节点 `gw-dms-test-05`，2026-10-28 20:59:51 UTC，起始 H，结束 clean。仅使用合成数据，未读取真实行值。
- 测试缺口：`test_two_node_compare_job_succeeds` 现在断言两侧 reader 列表均为空，但只验证 operation/publish 成功，没有检查 bundle 表覆盖；`test_unchanged_ordered_history_bundles_both_sides_and_preserves_facts` 也只核对 reader 和 comparison digest，名称所称的双侧打包没有对应断言。此次两项均通过，不能证明完整输出。
- 最小修正方向：区分比较行需求和全表导出需求。History 各节点全部表都须获取或生成可绑定的 Parquet；精确 cache hit 不读 Dolt，miss 回退导出。同内容复用时补齐各节点/侧绑定，不需要对未变化表执行完整比较。
- 关闭标准：在最终 History bundle 上断言普通/ordered 未变化表的全节点绑定和可读取数据；覆盖冷缓存 miss 与暖缓存 hit，前者按需读取并回填，后者不调用表 reader。可扩展已有 History 行为测试，避免再增只检验私有选择函数的证明。最终候选重新判定包闭包，并在受影响真实旅程核对 History bundle 的表绑定覆盖。

### N1

- **N1-2 关闭**：已读取最终四档 cache-count 原始日志。651/651 cache 项同时有 protection intent 和 manifest 引用；1,129 个 distinct row files 中 587 个被多个 manifest 引用。结合 miss mint 新 row-file ID 的实现，这支持真实导出跨 manifest 复用。此计数证明缓存复用，不证明每个 History bundle 完整。
- **N1-1 未关闭，待 owner 处置**：现有 step timestamp 无法拆出 checkpoint-read 与 bundle 的独立子段，handoff 已明确说明，未用 aggregate 冒充同口径结果。本轮未增加产品插桩或新性能门槛。即使 owner 接受该测量限制，F5 仍须修正。

## 3. 门禁、真实数据与性能证据

| 项目 | 本次核对 |
| --- | --- |
| 来源 V | `91401f014699cf99feba05675762cada2847e459`，04 原始 runner 六包 passed、runner_exit=0、起止 V，结束 verified clean。 |
| V→H carried | 04 同 worktree compare：rust/shared_kernel/repository_contracts/repository_client 的 changed_components 为空；backend/RS 为“运行”，并有 runtime/docker 环境变化。未将变化包沿用。 |
| H runner | 04 18:16:11–18:36:27 UTC，起止 H，backend/RS passed、runner_exit=0；与 handoff 一致。 |
| t1–t3 | 05 最终旅程日志起止 H、exit_code=0，结束时间分别 18:26:02、18:52:41、19:49:18 UTC。 |
| t4 | ct108 最终旅程 18:37:01–19:45:30 UTC，起止 H、exit_code=0。 |
| 缓存计数 | 05/ct108 最终 N1-2 日志均绑定 H，19:51:27–19:51:28 UTC、exit_code=0，计数与 handoff 一致。 |

上述记录支持“现有门禁和旅程通过”，不支持“最终 History bundle 已包含全部表”。t4 History API 162.472s、materialize_inputs 78.822s 是当前实现的实测结果；由于 F5 改变了实际输出覆盖，不能将其直接作为满足完整输出 Contract 后相对旧 H/S1a 的性能结论。修正后再更新该对照；repeat Preview 的既有计时记录本身没有被否定。

## 4. 实际执行的检查

- 本地只读 detached worktree：`/home/dev/gdds-p6-logs/s1b/review-r1-wt`，位于 handoff；05 同路径新建 detached worktree 于 H。均链接各自主参考 legacy，运行后 clean。未改变旧审核 worktree。
- 三节点 SSH BatchMode 连接通过。05 测试前无其他 pytest/runner/旅程/Dolt server 或 active Docker 容器。使用该节点 `05-bae1eb1944-wt` 已同步 H 的本地五包环境，无下载或构建；handoff 说明 LAN cache HTTP 服务已停，本次不需要该端点，不恢复公网访问。
- 05 21:00:12–21:00:22 UTC：以 H backend 环境运行审核 worktree 的 upload streaming、standard/ordered comparison、risk、surface、export cache、History jobs 共七个文件，`-n 0`，**159 passed、1 warning，FOCUSED_EXIT=0**。warning 是现有 Starlette/httpx 弃用提示。日志 `05:/home/dev/gdds-p6-logs/s1b/review-r1-focused.log`。
- 05 21:00:51–21:01:14 UTC：在同一 H 审核 worktree 分别使用五包现有环境执行 `python -m ruff check . --no-cache` 与 `python -m mypy --cache-dir /home/dev/gdds-test-tmp/s1b-r1-mypy/<包>`，全部通过，命令 exit 0；日志 `05:/home/dev/gdds-p6-logs/s1b/review-r1-static.log`。focused/static 日志均复制至开发节点同路径留存。
- F5 复现使用同一 H 环境及审核 worktree 源码；复现程序正常结束，输出错误业务结果，未将该结果记作验收通过。
- 禁止 bytecode 写入，TMPDIR 使用 `/home/dev/gdds-test-tmp`，pytest/Hypothesis 缓存放在 worktree 外。未运行全量 runner、Compose 或新一轮真实旅程。
- 只读抽查日志：04 `04-runner-final-91401f0146.log`、`04-runner-final-afbfaea8.log`、`04-compare-afbfaea8-to-914-final.log`；05 `05-t[1-3]-final-afbfaea8.log`、`05-N1-2-row-cache-counts-afbfaea8.log`；ct108 `ct108-t4-final-afbfaea8.log`、`ct108-N1-2-row-cache-counts-afbfaea8.log`。本次没有打开真实数据 control DB 或修改保留卷。

## 5. 镜像、交付及剩余前置

- 本次只出审核报告，不触发镜像重建。最终代码审核对象仍为 H；没有修改生产代码、依赖、容器 harness 或冻结 golden。
- 04 `docker image inspect` 复核 RS image ID `sha256:5cae950cc93b5f053ff9959e7273db28e0b3c351ef85a6e7c43144bc655c133e`，build-input revision `4158ea39d48157081c24d03a294c5a7eb3f866a0`，source-tree `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`，与 handoff 一致。H 的 backend/RS 容器证据取自本次最终 runner，没有重新 tag 或构建。
- 下一步只需定向修正 F5，补足完整 bundle 行为证明；保留 F1–F3 关闭结论，F4 随完整输出修正复核。N1-1 仍由 owner 明确处置。
- 新增清理项：本地/05 `review-r1-wt`，05 `/home/dev/gdds-test-tmp/s1b-r1-*`（含合成 History 临时目录与检查缓存），本次 `review-r1-*` 日志。未清理原有 ref/worktree/卷/制品，未推送或打 tag。主 checkout 原有 AGENTS.md 与 testing-conventions.md 修改未触碰。

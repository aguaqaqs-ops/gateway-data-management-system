# Phase 6 S1b 独立审核（首次，第二审核人）

- 结论：**定向修订**（与同日首次审核 `p6-s1b-independent-review.md` 一致）。
- 日期：2026-10-28。
- 代码候选 H：`705b17c1a137ede6b4339376527b30a4c58288f7`；handoff：`2599799b53c2950c48e4564af65460e3ae7b34e0`；分支 `p6-s1b-impl`。
- 审核区间：`ae3301d6d8..705b17c1a137`（实施）；kickoff 修订 `p6-s1a-exit..ae3301d6d8` 只作依据。
- 依据：P6 设计 §4.2、§5.1–§5.8、§16.2；执行计划 §2 S1b；DC40、DC41、DC49、DC56、DC61、DC62；owning Contracts；比例化保障政策；S1b handoff。
- 与首次审核的关系：本审核独立阅读代码并复核首次审核的 F1–F3、N1，另增 F4，并为 N1 第 2 项补充了直接证据。

## 1. 结论摘要

- 首次审核的 F1–F3 均成立：F2、F3 在 05 上独立复现；F1 的机制已从锁定的 anyio 4.14.2 源码确认。F3 的关闭标准需要扩大（见下）。
- 新增 F4：导出缓存在读取之后才查询，命中只省去 Parquet 写入，不省 Dolt 读取；History 又取消了 S1a 的按需读取。这与设计 §5.2、§16.2 不符，也解释了 t4 History 从 312.9 s 变为 744.1 s，handoff 没有说明这一点。需修订，或由 owner 明确接受延期到 S2b。
- N1 第 2 项（真实旅程中重复导出命中缓存）可以关闭：t1–t4 保留卷中，随机 ID 的行文件被多个 manifest 共同引用，计数见 §3。N1 第 1 项（checkpoint 与 bundle 子段对照）仍需 owner 处置。
- 下列关注点核对后没有问题：Submit 对只增列表照常写入；共享行文件的 protection 安全；worker 唤醒没有丢失唤醒的窗口；镜像脚本 EXIT trap；DC56 名单；解析器各项与 FLOAT32 舍入算法。

## 2. Findings

### F1（复核首次审核 S1b-F1）：取消上传时暂存目录先于线程结束被删除

- 结论：成立。`multipart_upload.py:55–69` 用 `anyio.to_thread.run_sync(..., abandon_on_cancel=False)`；anyio 4.14.2 的 `run_sync_in_worker_thread` 只用 `CancelScope(shield=True)` 包住 `await future`。这个 scope 拦不住原生 `task.cancel()`，外层 `finally` 会立即 `rmtree(parsed.staging_dir)`，而线程仍在运行。
- 严重度：建议 P2，不是 P1；仍阻塞，因为设计 §5.4 明确要求保留完成与取消边界。触发需要请求 task 被原生取消（例如服务关闭）；control DB 事务是原子的，最坏结果是该次上传失败，加上若干孤儿 artifact，由 TTL 回收。由 owner 定级。
- 补充：`acquire_new_work` 的准入名额同样会在线程结束前释放。修正时应让名额释放和暂存清理都等到同步工作结束（例如等待线程完成后再传播取消）。

### F2（复核首次审核 S1b-F2）：只增列时排除列 multiset 丢失行关联

- 独立复现（05，H，合成数据）：`aux` 为排除列，两行交换 `aux` 值，同时新增 `note`，结果为 `UNCHANGED / COLUMNS_ADDED / content_changed=False`；不加 `note` 时为 `content_changed=True`。
- 位置：`standard.py:667–690`、`ordered.py:692–709`。修正方向与关闭标准同首次审核。

### F3（复核首次审核 S1b-F3，扩大关闭标准）：ENUM/SET 标签按大写比较

- 独立复现：`ENUM('a','b')` 改为 `ENUM('A','b')` 并新增列，结果为 `COLUMNS_ADDED`、无 schema 风险。
- **扩大：** 同样的标签改名但不新增列，结果是 `UNCHANGED / schema_evolution=NONE`，也没有 schema 风险。旧路径早已如此（`_column_signature` 第 410 行整串 `upper()`），但 S1b 把 `schema_evolution` 定为稳定 facts 字段并冻结 golden，`NONE` 在这里是错的分类。
- 关闭标准增补：只改标签大小写或改名（不论是否新增列）都分类为 `INCOMPATIBLE` 并产生 schema 风险；真正只增标签/成员（含中间插入）仍为 `COLUMNS_ADDED`。修正点应在 `_column_signature` / `_column_signatures_compatible`（第 410–424 行），只规范化类型关键字，不改写字符串字面量。

### F4 [P2，新增]：导出缓存命中不省读取；History 全量读取 Dolt，与 §5.2、§16.2 不一致

- 类型：设计符合性缺口，加上未说明的性能回退；阻塞：需修订，或 owner 明确接受延期。
- 依据：设计 §5.2 写“避免整表反复读取与校验……未命中时从规范表读取并导出、回填”；§16.2 History“整表打包：两个节点全部表的导出，命中导出缓存则不读表”。
- 代码事实（H）：
  - `repository_ref.py:229` 对每张选中的表调用 `_read_and_materialize_table`，读出全部行并重算 `raw_content_digest`；之后 `_with_artifacts` → `publish_ready_tables`（`artifact.py:446–478`）才计算 cache key 并 `lookup_many`。命中只跳过 Parquet 写入与 put，命中后还要再解码并校验一次缓存文件。
  - S1b 删除了 History 的 `_history_requested_tables`（`compare_jobs.py`），`requested_tables` 变为全部表，于是每个节点的每张表都要从 Dolt 读一遍。
  - 读取并不是计算 key 的前提：`_describe_without_rows`（`repository_ref.py:249/328`）已经用 canonical metadata 的 `identity.raw_content_digest` 构造 descriptor，不读行。
- 影响（handoff 数据，t4）：History 312.889 s → 744.135 s（+138%），其中 `materialize_inputs` 595.122 s；repeat Preview 的 `materialize_inputs` 仍为 616.207 s。handoff 对 History 的变化没有给出说明。
- 最小修正方向：对 repository 侧的表，先用 canonical identity 与目录 schema 计算 row-layout key 并查询缓存，只读取未命中的表（ordered metadata 若必须读行才能得到，就按表说明）；变化表的读取需求保持 S1a 的按需规则。不新增机制。
- 关闭标准：一个 focused 测试证明缓存命中的表不调用表读取（计数），未命中时回退读取并回填；t4 重测 History，或由 owner 书面接受“S1b 只省写入，读取留给 S2b 规范表存储”，并在 handoff 中写明 History 回退的原因。

### N1（复核首次审核 N1）

- 第 2 项（真实旅程重复导出命中缓存）：**已有直接证据，可以关闭。** 行文件 ID 是 `sta-rows-<secrets.token_hex(8)>`，每次导出都生成新 ID；同一次物化中 `lookup_many` 先于 `store_many`，所以同一个行文件被多个 manifest 引用只能来自跨操作的缓存命中。计数见 §3。
- 第 1 项（t4 checkpoint 读取与 bundle 子段对照）：维持首次审核意见，交 owner 处置。F4 的修正会直接改变 History 与 repeat Preview 的 `materialize_inputs`，建议在修正后的候选上一并记录。

## 3. 核对结果

| 项目 | 结果 |
| --- | --- |
| 只增列后 Submit 是否仍写入 | 通过。mutation planner 按 `canonical_schema_digest` 与行摘要判断（`_planner.py:297–344`），`NO_CANONICAL_CHANGE` 按 canonical 状态摘要判断，不依赖 comparison status；t3 v2 Submit 有 commit。 |
| t3 只增列计数 | handoff 的 33 张与 DC40 的“32 张只增列 + 2 张 ENUM”对得上：原始 schema 差分为 32 + 2（`bay_name_cfg`、`bay_voltage_cfg`），两张 ENUM 表都分类为 `COLUMNS_ADDED`；`device_model_table` 属于 `DEFAULT_SKIPPED_TABLE_NAMES`，不进入比较。建议 handoff 补一句说明。 |
| 导出缓存真实命中（N1-2） | t1：629 个 manifest 只引用 164 个行文件，其中 134 个被 ≥2 个 manifest 引用；t2：1095 / 321 / 166；t3：1015 / 307 / 189；t4：1587 / 455 / 195。cache 行数 136 / 184 / 207 / 207，每行都有对应的 protection intent 并被 manifest 引用。 |
| 共享行文件与清理 | 安全。protection 按 artifact_id 计算（`bounded_store.classify_cleanup`）；Preview/History 的 pin 集合包含 `row_file_refs`（`preview_jobs.py:2176`、`compare_jobs.py:1367`），所以任一 owner 都能保住共享文件。 |
| 表级失败与全表 bundle | 不可达。上传侧投影在任一表 `TABLE_FAILED` 时整体失败（`storage_projection/project.py:1159`），不会进入 `_surface_table_artifacts` 的“缺 artifact”错误分支。 |
| worker 唤醒 | 没有丢失唤醒：每轮循环开头都重新检查 `completed` 与 `drain_requested()`（电平判断），`wait` 与 `clear` 之间的置位不会丢。heartbeat/drain 截止计算不变。 |
| 镜像脚本 | EXIT trap 在 `mktemp` 之前安装，脚本内没有其他 EXIT trap；保留原 exit code。 |
| DC56 | 11 张显式键表与 17 张 BROWSE_ONLY 名单逐一与 DC56/DC62 对上；`forwardtbl_lst_*` 为 8 个精确名。 |
| 解析器 | DC62 2a–2g 逐项对上代码；JSON 深度检查与孤立代理检查都是迭代实现。 |
| FLOAT32 | `_float32_bits_from_decimal`：指数 floor、次正规（含舍入到最小正规数 `0x00800000`）、上溢（舍入到 2^128 时报错）、ties-to-even 都正确；负值下溢为 `+0`，与零的处理一致。 |
| 门禁日志抽查 | 04 V runner 与 H 选包 runner：hostname、起止 HEAD、`EXIT=0`/`RUNNER_EXIT=0` 与 handoff 一致；compare 四包为“可沿用”，backend/RS 为“运行”。 |

## 4. 观察（不阻塞）

- O1：`request_drain` 信号处理器（`operation_worker.py:706–711`）在主线程调用 `Event.set()`，而 supervisor 也在主线程反复执行 `wait`/`clear`。如果信号恰好在主线程持有该 Event 内部锁的几条字节码之间到达，处理器会在同一把非可重入锁上自锁。窗口极窄，且旧代码对 `stop_requested` 已有同样模式；最坏结果是 drain 卡住，直到 SIGKILL 后由 lease 过期接管。记录在此，不要求本阶段处理。
- O2：JSON `1e400` 经 `json.loads` 得到 `inf`，不走 `parse_constant`，所以会被接受；MySQL 拒绝。JSON 以文本保存，不会引起下游异常；DC62 也没有列这一项。供 S2a 差分时注意。

## 5. 实际执行的检查

本地只读阅读审核 worktree `/home/dev/gdds-p6-logs/s1b/review-initial-wt`（detached，位于 handoff 提交，clean）。没有在开发主机运行测试。

| 检查 | 节点 / 时间（UTC） | 结果 |
| --- | --- | --- |
| F2/F3 及 ENUM 变体复现 | 05 `gw-dms-test-05`，14:37:13–14:37:14，H 审核 worktree，`05-wt` 的 backend venv，`-B` | 5 个用例输出符合上文；审核 worktree 运行后仍 clean |
| t3 原始 schema 差分（只输出表名与计数） | 05，14:32:58 | 32 张只增列 + 2 张 ENUM 只增标签 |
| t3 surface 中的 schema_evolution（只输出表名与分类） | 05，14:33:35 | v2 Preview 33 张 `COLUMNS_ADDED`，160 张 `NONE` |
| 行文件复用与 cache 表计数 | 05 t1–t3 14:35:32–14:35:33；ct108 `gw-dms-test` t4 14:36:14 | 见 §3 |
| 门禁日志抽查 | 04 只读 grep | 见 §3 |

日志与脚本：本机 `/home/dev/gdds-p6-logs/s1b/review2-claude/`；05 与 ct108 上的 `/home/dev/gdds-test-tmp/s1b-review2/`。

**对证据卷的影响：** 05 上 t1–t3 的 control DB 用 `mode=ro` 打开，SQLite 因此刷新了 `control.sqlite3-shm` 的 mtime（共享内存索引）；主库文件与 WAL 的大小和 mtime 都没有变。t4 改用 `immutable=1`，三个文件都没有变化。没有写入、停止或删除任何卷、镜像、worktree、ref 或缓存。

## 6. 镜像记录与下一步

- 本次只出审核报告，没有改动代码、依赖、deployment 或 harness，不触发镜像重建。最后验证的 RS build-input revision `4158ea39d481`，source-tree `sha256:1d23f369…8e00`，与 handoff 及首次审核一致。
- 下一步：实施会话修正 F1–F4（F4 也可以由 owner 选择延期），在 05 上做 focused 验证；最终候选按既有规则重判包闭包与容器边界，并重跑受影响的真实数据档（F4 修正后至少 t4 History）。N1 第 1 项交 owner 处置。修正后交复审。
- 待 owner 清理：本机 `review2-claude/`，05 与 ct108 的 `/home/dev/gdds-test-tmp/s1b-review2/`。

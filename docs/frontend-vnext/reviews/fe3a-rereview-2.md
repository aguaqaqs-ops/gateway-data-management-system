# FE3a 复审报告（第 2 轮）

- **复审对象：** 开发主机分支 `fe-vnext`。
  - 代码候选 `09715b22057fb67798428319a330136fb93bef81`，`frontend/` 树 `8a9f11c84f`；
  - handoff 提交 `58c6c9e29fd2d0a036a6c4ec00ad549d0896d54e`（只改 handoff，`frontend/` 树相同）。
- **范围：** `76cce6814f..58c6c9e29f`，共 2 个提交，改动 3 个文件：
  - `frontend/scripts/run-real-backend-e2e.sh`；
  - `frontend/e2e-real/smoke.spec.ts`；
  - `docs/frontend-vnext/fe3a-handoff.md`。

  `vnext/` 树仍为 `2791d3ff3d`，没有改产品代码和打包代码。
- **依据：** [复审第 1 轮](fe3a-rereview-1.md) §3、§4。
- **日期：** 2026-11-05。
- **结论：通过。** R1、R2 已修复，我在 05 上的 runner、smoke 与中断探针都符合预期（§2）。可以去 04 取证。
  handoff 剩一处措辞错误（§3 N1），在取证 handoff 中改正即可。

## 1. 核对

| 项 | 核对 | 结论 |
| --- | --- | --- |
| R1 | 以下各项同时成立才判为通过，任一不满足都写一行 `suite_fail_reason=<项>`：<br>- `PLAYWRIGHT_EXIT == 0`；<br>- 结果文件存在且能解析，否则 code 2；<br>- `unexpected`、`flaky`、`skipped` 都为 0；<br>- 顶层 `errors` 为空；<br>- `expected > 0`。 | **通过** |
| R2 | `runInputScope` 增加了 `mode`：<br>- MODIFIED_ONLY 断言恰好一个比较对，0→1；<br>- FULL 断言恰好两个，按 `before_input_index` 排序后为 0→1、1→2；<br>- FULL 在点击上传前，等到页面显示“原始备份 + 本次归档”。 | **通过** |
| N1 | `Identity.scope` 已补；映射后的比较对保留 `pair_id`，断言消息带比较对名 | **通过** |
| N2 | 改记 Preview 结果的 `bundle_digest`，5 个输入 scope 都写进了日志 | **通过** |
| N3、N4 | 过时的注释已删除；宿主机上的 `python3` 都加了 `-I` | **通过** |
| N6 | §6 的提交号、§0.1 中 N2 的说明已改正；§9 第 5 项见 §3 N1 | 部分 |
| N7 | `/home/dev/gdds-fe-m1-05`、`/home/dev/gdds-fe-smoke-05` 已删除；复审用的 worktree 未动 | **通过** |

handoff §0.4 列出的 3 份日志（runner、smoke、R1 探针）在 05 上的 SHA256 与 handoff 一致。

## 2. 我在 05 上的核对

- **源码：** 经 bundle 传到 05。
  - bundle：`/home/dev/gdds-fe-logs/fe3a/fe3a-rereview2-58c6c9e29f.bundle`，SHA256 `69cd6073…cc32887e`，ref `refs/fe3a-rereview2/candidate`；
  - worktree：`/home/dev/gdds-fe-fe3a-rereview2`，detached `58c6c9e29f`，运行前后都是 clean。
- **驱动：** 脚本 `/home/dev/gdds-fe-logs/fe3a/rereview2-run.sh`，输出在 `rereview2-run.out`。
- **占用：** 运行前 05 没有占用标记，也没有容器。
  - runner 前，由驱动脚本用 `mkdir /home/dev/gdds-node-busy.d` 手工获取占用，标记写明 owner `fe3a-rereview`、用途 `fe3a-rereview2-runner` 与开始时间。11:26:50 获取，11:28:06 删除标记并 `rmdir`；
  - smoke 与探针由脚本自己获取和释放，标记内容记在各自日志的 `occupancy_marker=` 行。

| 运行 | 起止（UTC） | 结果 | 日志 / SHA256 |
| --- | --- | --- | --- |
| runner `--e2e --screenshots` | 11:27:13–11:28:06 | exit 0；截图 96 张 | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261105T112713Z.log`，`fac35150…bc66ba7` |
| 真实 smoke，`--session fe3a-rereview` | 11:28:06–11:29:46 | exit 0；`expected=9 unexpected=0 skipped=0 flaky=0 errors=0`；`openapi_compare=match`；`cleanup_status=ok` | `/home/dev/gdds-fe-logs/fe3a/rereview2-smoke-58c6c9e29fd2/real-backend-e2e-smoke-fe3a-rereview-58c6c9e29f-20261105T112806Z-1406862.log`，`db2c862c…13c85a6a` |
| R1 中断探针，`--session fe3a-rereview-int` | 11:29:46–11:31:08 | 脚本 exit 1；`playwright_process_exit=130`；`expected=3 skipped=6`；两行失败原因：`skipped=6`、`playwright_exit=130`；`cleanup_status=ok` | `/home/dev/gdds-fe-logs/fe3a/rereview2-probe-int-58c6c9e29fd2/real-backend-e2e-smoke-fe3a-rereview-int-58c6c9e29f-20261105T112946Z-1413647.log`，`1eef668a…43aa844` |

- **探针做法：** 用 Python `start_new_session` 启动脚本。看到日志出现 `suite_start=` 后等 6 秒，再执行 `docker exec <项目>-toolchain pkill -INT -f "playwright test"`。
  与实施方的探针相比，中断时间点不同（实施方中断时已跑完 1 个用例，我这次已跑完 3 个），结论相同。
- **smoke 的 5 个输入 scope：** 与 handoff §0.4 一致，`bundle_digest` 也相同：
  - A、B②、C：0→1，changed 9；
  - D：0→1，changed 4；
  - B FULL：0→1 changed 9，1→2 changed 5；
  - 所有 scope 的 `failed_pairs` 与 `failed_table_count` 都为 0。
- **运行后：** 05 没有占用目录，没有本前缀的容器、卷、网络，也没有 RS 临时 tag。

## 3. 非阻塞意见

| # | 意见 |
| --- | --- |
| N1 | handoff §9 第 5 项现在写“用生产构建而非开发构建测量；这是 §8.4 的明确要求”，与事实相反。kickoff §8.4（第 606 行）写的是 FE3a 用**开发构建**测量，生产构建是偏差。应改为：“§8.4 写的是开发构建，实际用了生产构建（更接近用户拿到的产物），作为偏差列出，交 owner 确认。” 在 04 取证的 handoff 中改正即可 |

## 4. 下一步

1. **04 取证：**
   - 在 04 的 clean detached worktree 上，以 `58c6c9e29f` 为准运行：
     - `frontend/scripts/run-tests.sh --e2e --screenshots <04 上 worktree 外的目录>`，运行前手工获取占用，写明 owner、用途、开始时间，结束后释放；
     - `frontend/scripts/run-real-backend-e2e.sh --suite smoke --session fe3a-evidence`，由脚本获取和释放占用；
   - 记录节点、起止时间与 HEAD、exit code、日志 SHA256、工具链与依赖镜像身份、npm 缓存来源；
   - 04 上需要的镜像与缓存按 DC67 预填充；缓存缺失即停止。
2. **owner 看图：**
   - M7：`submit-summary-workspace-*`，以及因编号变化的组态树截图；
   - n8：`submit-manual-recovery-*`，含复审第 1 轮 N8 提到的灰色底。
   - owner 同时确认 M1 用生产构建这一偏差（§3 N1）。
3. **取证核对：** 由审核会话完成，然后进入 FE3a 退出。
4. **复审资源：** 05 上的复审 worktree `/home/dev/gdds-fe-fe3a-review`、`-rereview`、`-rereview2`，ref `refs/fe3a-review*/*`，以及 bundle，保留到取证核对完成后清理。

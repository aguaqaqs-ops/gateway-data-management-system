# FE0 证据核对（第 1 轮）

- **核对对象：** FE0 在 04 上的阶段退出取证。被测提交为 `e22f510a82a143ccee76a1b3b3b6c854aa755129`，`frontend/` 树为 `47e901a848`；
  handoff 提交为 `502064a47cde45f6bb2fa5de4dc15ae4db7857a7`，父提交即被测提交。
- **依据：** kickoff §6；[FE0 复审第 1 轮](fe0-rereview-1.md) §4、§5。
- **日期：** 2026-11-02。
- **结论：PASS。** 04 的权威运行有效，可以作为 FE0 阶段退出证据。FE0 可以交 owner 确认退出。

## 1. 范围

`e22f510a82..502064a47c` 只改动了 `docs/frontend-vnext/fe0-handoff.md`，代码没有变化，04 运行所绑定的提交就是复审通过的代码。

## 2. 04 权威运行

运行日志为 04 上的 `/home/dev/gdds-fe-logs/fe0/exit-04/frontend-tests-20261102T103234Z.log`，SHA256
`31c8e57c458570e00b2ea6ad6004f958a599985b1da9cabc818a78b8b2f9083b`，与 handoff 一致。我在 04 上逐项读取了日志内容：

| 项 | 日志内容 |
| --- | --- |
| 节点 | 起止的 hostname 都是 `gw-dms-test-04.lan` |
| 时间 | `10:32:34Z`–`10:32:45Z` |
| HEAD | 起止都是 `e22f510a82`；包装日志另记 `frontend/` 树起止都是 `47e901a848` |
| 工具链 | 七个 RootFS DiffID 与固定值一致（runner 检查通过） |
| 缓存 | 路径为默认的 `/home/dev/gdds-fe-cache/frontend/npm-cache`，归档 SHA256 `0d861824…089f4`，来源提交 `a2fb4a027a`（R1 已处理） |
| lock source | `package_lock_resolved_count=305`，通过官方源检查 |
| 网络 | `docker_network=none` |
| 步骤 | 离线安装 280 个包；typecheck、lint、build 通过；Vitest 没有测试文件（N1 留到 FE1）；e2e 用例“打开应用显示工作台骨架页”`1 passed` |
| 结果 | `exit_code=0`，包装日志记录 `runner_exit_code=0` |

- 构建产物的文件名哈希（`index-DwKvav20.js`、`index-BliSb9Th.css`）与 05 上的各次运行相同，三台机器（CT201 生成、05、04）的构建结果一致。
- 权威 runner 只运行了一次。

## 3. 制品与环境身份

- **工具链镜像：** 04 上的归档 SHA256 为 `5babfc35…be163c`，与 CT201 原归档相同。`toolchain-loaded-metadata.txt` 中的 config digest 是 `sha256:a0d7b2b4…a1017`。
  我另外在 04 上用 `docker image inspect .RootFS.Layers` 核对，七个 DiffID 的顺序和值都一致。没有比较 inspect ID。04 宿主机上没有 Node.js。
- **npm 缓存：** 04 的默认路径下有 603 MB 缓存；`/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz` 的 SHA256 为 `0d861824…089f4`，与 CT201 原归档相同。
- **源码：** 两端 bundle 的 SHA256 都是 `9d4375f8…5171c`。由于引用和基点相同，它与我复审时生成的 bundle 也相同。
  04 的 worktree `/home/dev/gdds-fe-fe0-exit-04` 是 detached HEAD `e22f510a82`，clean，`legacy` 符号链接指向主仓库的 `legacy/`。
- **节点占用：** 预检和我核对时（10:41Z），占用标记都不存在。

## 4. 日志 SHA256

- **04 侧：** `/home/dev/gdds-fe-logs/fe0/exit-04/` 下全部 `.sha256` 文件用 `sha256sum -c` 校验通过。handoff 列出的日志 SHA256 也都一致，包括：
  - `04-preflight`、`toolchain-load-verify`、`npm-cache-prefill`；
  - `bundle-fetch` 及第一次尝试的两份日志、`worktree-add`、`main-movement-investigation`；
  - `runner-precheck`、`runner-invocation.meta`；
  - `postrun-evidence-check` 及其失败日志。
- **CT201 侧：** 全部 `.sha256` 校验通过。`ct201-preflight`、`toolchain-transfer-04`、`npm-cache-transfer-04`、`source-bundle-ct201`、`source-bundle-transfer-04` 的 SHA256 与 handoff 一致。

## 5. 04 main 被推进

- 04 的 reflog 显示：`main@{2026-11-02T18:28:44+08:00}`（即 `10:28:44Z`）执行了 `pull -q --ff-only /home/dev/sync-17cc76174b.bundle main`，把 main 从 `bb6a09252a` 推进到 `17cc76174b`。
  这是另一会话推送 `17cc76174b`（P6 DC68 澄清，只改 `docs/backend-vnext/`）后做的节点同步，不是实施会话的操作。
- **对证据没有影响：**
  - 被推进的是共享主仓库的 main worktree，前端运行没有使用它。
  - 被测的 detached worktree 在推进之后（`10:31:16Z`）才创建，并固定在 `e22f510a82`。
  - fetch、runner 前后的检查都确认 main 停在 `17cc76174b`，被测 HEAD 和 `frontend/` 树没有变化。
  - 这也符合 `17cc76174b` 中 DC68 澄清第 2 项的界限：不对正在使用的 worktree 拉取或写入。
- **勘误（非阻塞）：** handoff 中“reflog 时间 `10:28:10Z`”写的其实是 `17cc76174b` 的提交时间，实际推进时间是 reflog 中的 `10:28:44Z`。不影响结论，本报告记录勘误，不要求修改 handoff。

## 6. DC68 记录

- **bundle fetch 第一次尝试：** 实施会话自己加的保护检查发现 main 已经移动，于是在 verify 和 fetch 之前停止（exit 21），没有副作用。失败日志已保留，从 verify 开始重做。
  按 `17cc76174b` 的澄清，代码传输准备本来就不受“重做一次”的次数限制，这样处理是正确的。
- **运行后的只读查询误用 `rg`：** 这是只读的后处理，没有触及被测对象，修正后重新查询。按 DC68 澄清（只读后处理不计次数），处理正确。

## 7. 复审意见的处理

| 项 | 状态 |
| --- | --- |
| R1 缓存来源提交 | 已处理：04 运行记录 `a2fb4a027a`，handoff 写明了它与 `62cd5d5641` 的 blob 相同；缓存放在默认路径 |
| R2 日志记录 `frontend/` 树 id | 按约定留到 FE1。本次由包装日志记录了 `frontend_tree`，作为过渡 |
| R3 handoff 中 D1 的状态 | 已同步为 KEEP，引用 `bb6a09252a` |

## 8. FE0 退出

kickoff §7 的 FE0 退出条件都已满足：

- 05 上入口可以运行；
- 能力清单中没有未判定项（D1 已由设计会话定为 KEEP）；
- 04 有一次完整的前端测试与 e2e 运行作为证据。

建议：

1. owner 确认 FE0 退出后，由设计会话把附注 tag `fe-fe0-exit` 打在 `502064a47c` 上（handoff 提交，父提交即被测提交），然后合入 `main`。
2. **带入 FE1 的事项：**
   - N1：加入单元测试后去掉 `--passWithNoTests`；
   - R2：runner 日志记录 `frontend/` 树 id；
   - 前端不暴露 `RETURN_FOR_REVISION`；BE-a 之后刷新 OpenAPI 快照；
   - `frontend-surface-simplification.md` 中关于兼容层的过时表述，由设计会话或治理会话处理。
3. **合入后可以清理：**
   - 开发主机：`/home/dev/gdds-fe-review-fe0-6c5dbcb1c4`；
   - 05：`/home/dev/gdds-fe-review-fe0-6c5dbcb1-05`、`/home/dev/gdds-fe-rereview1-fe0-e22f510a-05`，以及实施会话的 `/home/dev/gdds-fe-fe0-05`、`/home/dev/gdds-fe-fe0-fix1`；
   - 04：`/home/dev/gdds-fe-fe0-exit-04`。

   证据目录 `/home/dev/gdds-fe-logs/fe0/` 和各节点的工具链镜像、npm 缓存保留，供 FE1 使用。

# FE2b 证据核对（第 1 轮）

- **核对对象：** FE2b 在 04 上的阶段退出取证。
  - 被测代码候选：`5d1749675621a020a052690b95d55111af5509f9`，`frontend/` 树 `a0f8ce750b`；
  - handoff 提交：`31f4310ff8c56a3bd08ef9bac404c03dd7d4c7a7`，父提交为 `7682297b72`（复审第 1 轮的终点）。
- **依据：** FE2 kickoff §7.3、§7.4、§9 Q15；[FE2b 复审第 1 轮](fe2b-rereview-1.md) §2.1、§4、§5。
- **日期：** 2026-11-03。
- **结论：PASS。** 04 的权威运行有效，可以作为 FE2b 阶段退出证据。owner 看截图确认后即可退出（§4）。

## 1. 范围

- `7682297b72..31f4310ff8` 只改动了 `docs/frontend-vnext/fe2b-handoff.md`，`frontend/` 树仍是 `a0f8ce750b`，与复审第 1 轮通过的代码一致。
- 04 运行检出的是代码候选 `5d17496756`。

## 2. 04 权威运行

我在 04 上逐项读取并重算了日志：

| 项 | 内容 |
| --- | --- |
| 日志 | `/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T162807Z.log`，SHA256 `25f3295d…92665c1a`，与 handoff 和 sidecar 一致 |
| 节点 | 起止的 hostname 都是 `gw-dms-test-04.lan` |
| 时间 | `16:28:07Z`–`16:28:47Z` |
| HEAD 和树 | 起止都是 `5d17496756`；`frontend/` 树起止都是 `a0f8ce750b` |
| 工具链 | config digest `sha256:a0d7b2b4…a1017`；7 个 RootFS DiffID 与固定值一致；04 上 `docker image inspect` 的 DiffID 列表也一致 |
| 缓存 | 默认路径 `/home/dev/gdds-fe-cache/frontend/npm-cache`；来源归档 `npm-cacache.tar.gz`，SHA256 `0d861824…089f4`（我在 04 上重算一致），来源提交 `a2fb4a027a`。没有使用节点上自行打包的副本 |
| lock source | `package_lock_resolved_count=305` |
| 网络 | `docker_network=none` |
| 步骤 | 离线安装 280 个包；typecheck、lint、build 通过；24 个单测文件 107 项通过；生产检查通过（含模块清单）；e2e 15 passed |
| 截图 | `screenshot_dir=/home/dev/gdds-fe-evidence/fe2b/5d174967-04` |
| 结果 | `exit_code=0` |

- **外层日志：**
  - `runner-wrapper-fe2b-exit-04-5d174967.log`（`be36d79e…df783a`）、`preflight-fe2b-exit-04-5d174967.log`（`bb7a114e…be406`）重算一致；
  - preflight 记录运行前没有占用标记，worktree clean，截图目录不存在。
- **只运行了一次：** 04 的 `fe2b/` 下只有这一份 runner 日志，wrapper 记录 `run_count=1`，没有 DC68 重做。
- **DC68 记录：** 取证期间的三处操作错误都发生在 runner 之前或在文档编辑中，没有副作用，按 DC68 处理正确：
  - bundle 参数；
  - `git bundle verify` 的执行目录（`39555f3b…1c1` 重算一致）；
  - handoff 脚本的锚点。
- **源码传输：**
  - bundle `fe2b-exit-5d174967.bundle`，SHA256 `46ebd6a7…f78b`，与 handoff 一致；
  - 传输记录 `worktree-transfer-…log`（`2744bbf6…cb`）重算一致。
- **运行后的状态：**
  - worktree `/home/dev/gdds-fe-fe2b-5d174967-04` 是 detached HEAD `5d17496756`，clean，`legacy` 链接指向主仓库；
  - 占用标记不存在；
  - 04 的 main 是 `718809ba9a`。reflog 显示 main 最后一次移动在 `16:26:06Z`（设计会话同步），早于 preflight 和这次运行。

## 3. 截图

- **清单：**
  - 04 上的清单 `screenshot-sha256-5d174967-04.txt`，SHA256 `bea5e1b4…f9960d`，与 handoff 一致；
  - 50 项与证据目录中重算的 SHA256 逐项一致。
- **与我在 05 上为复审拍的截图比较：** 47 张逐字节相同，不同的 3 张如下：
  - `manual-recovery-required-1280/1920` 只是“已等待”的秒数不同（04 上为 26908 秒），这是 FE2c 带入项 N2（§6.4）；
  - `history-compare-result-drawer-1280` 内容相同，只是像素级渲染差异。
- **草图对照：** 结论与复审第 1 轮 §1、§4 相同，没有新的偏差。

**handoff 勘误（不影响结论）：**

- §6 的逐张表仍然是 05 截图的 SHA256，其中 3 张与 04 的截图不同：
  - `manual-recovery-required-1280/1920`；
  - `workspace-error-no-connected-1280`。
- 04 截图以清单文件 `bea5e1b4…` 为准，表格应注明是 05 的截图，或换成 04 的值。
- §8 仍写着“请 owner 决定”。owner 已在 §9 Q15 中决定（抽屉摘要带入 FE2c，接受 M10），以 kickoff 为准。

## 4. FE2b 退出条件

| 条件 | 状态 |
| --- | --- |
| FE2b 范围（§2 FE2b 一行、§6.1–§6.3 中属于 FE2b 的部分） | 已完成（审核 B1–B9，复审第 1 轮 PASS） |
| §6.3 带入项 N1、N2、R2、R5、R7、S1、S2 | 已完成，相关项都经变异探针验证 |
| §7.5 模拟响应 | 满足 |
| fixture 由后端生产代码产出，可逐字节复现（§7.1） | 满足。226 个文件，我在 `bf4942e0a8` 上独立复现，此后生成输入未变 |
| 两项偏差、N2–N4 | owner 已决定（§9 Q15、§6.4）：抽屉摘要与 N2–N4 带入 FE2c，接受 M10 |
| 截图交 owner 确认（§7.3） | **待 owner 确认** |
| 04 阶段退出取证（§7.4） | 满足（本报告） |

**请 owner 查看的截图**在 04 的 `/home/dev/gdds-fe-evidence/fe2b/5d174967-04/`，每项有 1280 和 1920 两张：

| 组 | 文件 |
| --- | --- |
| 草图 S1 工作台 | `s1-workbench` |
| 草图 S2 比较托盘 | `s2-compare-tray`、`history-compare-running` |
| 历史比较结果抽屉 | `history-compare-result-drawer` |
| 草图 S3 的 Preview、History 顶栏 | `s3-header-upload`、`s3-header-history` |
| 正常业务场景 | `s3-workbench-normal`、`s4-grid-normal-main`、`s4-grid-normal-hover`、`s4-grid-normal-debug` |
| 无草图页面 | `history-compare-connection-interrupted`、`manual-recovery-required`、`workspace-error-no-connected`、`navigation-fallback`、`formula-preview`、`formula-history` |

## 5. 建议

1. **退出：** owner 确认截图后，由设计会话：
   - 把附注 tag `fe-fe2b-exit` 打在 `31f4310ff8`（handoff 提交；代码候选在它的祖先链上，`frontend/` 树与被测代码相同）；
   - 合入 `main`，只带入 `frontend/` 与 `docs/frontend-vnext/fe2b-handoff.md`；
   - §3 的勘误可以在合入时由设计会话在 kickoff §2 的退出记录中注明，不需要新的 handoff 提交。
2. **FE2c：** 审核范围为 `fe-fe2b-exit..<FE2c 候选>`，按 §6.4 核对抽屉摘要与 N2–N4。
3. **合入后可以清理：**
   - **审核会话：**
     - 开发主机上的 `/home/dev/gdds-fe-review-fe2b-bf4942e0`；
     - 05 上的 `/home/dev/gdds-fe-review-fe2b-bf4942e0-05`、`/home/dev/gdds-fe-rereview1-fe2b-7682297b-05`；
     - 两端的 `/home/dev/gdds-test-tmp/src-review-fe2b-bf4942e0.bundle`、`src-rereview1-fe2b-7682297b.bundle`。
   - **实施会话：**
     - handoff §9 列出的 05 worktree、04 worktree `/home/dev/gdds-fe-fe2b-5d174967-04`；
     - 临时 ref `refs/codex/fe2b-exit-evidence-7682297b`；
     - 各 bundle 与 fixture 生成输出。

   以下保留，供 FE2c 使用：
   - 证据目录 `/home/dev/gdds-fe-logs/fe2b/`、`/home/dev/gdds-fe-evidence/fe2b/`；
   - 各节点的工具链镜像与 npm 缓存；
   - 后端依赖镜像 `gateway-backend-deps:lock-d054366c02fa`。

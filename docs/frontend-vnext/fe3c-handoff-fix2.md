# FE3c handoff fix2（B7 路由竞态定向修复）

本文件是 `docs/frontend-vnext/fe3c-handoff-fix1.md`（提交 `031dc3d754e754feb22bba793324f3d53bd80825`）的补丁说明，原 handoff 不改。
停止核对为本地 main `docs/frontend-vnext/reviews/fe3c-evidence-stop-1.md`（`f9fa8cd8f8`，未推送）。
复审依据为复审第 1 轮 `docs/frontend-vnext/reviews/fe3c-rereview-1.md` §6（取证提示词）。

- 基座：`031dc3d754e754feb22bba793324f3d53bd80825`（fix1 handoff）
- 代码基座：`cbb14f578cd22f37355db78a62ba9264f71477d3`（本轮未改产品代码）
- 本轮修复：`e8864ce1da2dcd6d6536c421607abb383ec955d9`
- 修复 frontend tree：`46e425f84eb28936563c8751295a8829e33f3ad6`
- 修复 vnext tree：`6368c9c40cf08a97eecf2a0c457a6c16ce448080`（与 `cbb14f578c` 相同，未改 `vnext/`）
- 旧 frontend tree（`cbb14f578c`）：`f626a8f0b3ab4ebd2a3e1d7a3eb15e1803c48908`
- 未合入 main、未 rebase、未推送。

提交序列（`031dc3d754..e8864ce1da`）：

| 提交 | 内容 |
| --- | --- |
| `e8864ce1da` | 只改 `frontend/e2e/archive-validation.spec.ts`：预检闸门与 `wait` 清理 |

## 1. 改动说明与 diff 范围

只改一个文件：`frontend/e2e/archive-validation.spec.ts`（21 增、10 删）。

- 删除 `ArchiveScenario.previewDelayMs`，新增 `ArchiveScenario.holdPreview?: boolean`。
- `installArchiveScenario` 在 `holdPreview` 为真时建闸门：`previewGate` 与 `releasePreview`；预检路由处理函数在 `previewGate` 打开前等待，不再 `setTimeout` 睡眠；返回 `{ apiRequests, apiResponses, releasePreview }`。
- B7 第一段用 `holdPreview: true` 安装场景，截完“正在预检”后 `releasePreview()`，等对话框显示“预检状态”，再 `page.unrouteAll({ behavior: "wait" })`，然后进入下一段。
- 本文件全部 5 处 `unrouteAll` 改为 `unrouteAll({ behavior: "wait" })`：V7 1 处、B7 4 处。
- `workspace-shell.spec.ts` 的 11 处不带参数的 `unrouteAll` 本轮不动，列为 FE4 带入项 N9。
- 不改其他用例断言，不改产品代码，不改 `frontend/e2e-real/`，不改 `frontend/scripts/`。

`git diff --stat`（`031dc3d754..e8864ce1da`）：

```text
frontend/e2e/archive-validation.spec.ts | 31 +++++++++++++++++++++----------
1 file changed, 21 insertions(+), 10 deletions(-)
```

## 2. 07 运行记录

节点 `gw-dms-07.lan`（别名 `ct109-gw-dms-07`），worktree `/home/dev/gdds-fe3c-fix2-wt`（detached，`e8864ce1da2dcd6d6536c421607abb383ec955d9`，起止 clean）。
工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`，config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，
npm 缓存 `/home/dev/gdds-fe-cache/frontend/npm-cache`，归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，
归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，`package_lock_resolved_count=305`，`docker_network=none`。
两次全量 `tracked_frontend_archive_sha256=5cb149ece784ad3d71df1d7c846afb7c8ca47f31e0c1d35f135f855002abe628`。

### 2.1 全量 r1（`GATEWAY_FE_TEST_WORKERS=2`）

- 外层日志：`/home/dev/gdds-fe-logs/fe3c-fix2-07-r1/outer-20261110T014927Z.log`，SHA256 `9253d9df12de1832b85a9ea2a36fd0d375dadd66ea581985629128abb2b89a71`
- 入口日志：`/home/dev/gdds-fe-logs/fe3c-fix2-07-r1/frontend-tests-20261110T014950Z.log`，SHA256 `d8014fff7524aa9777f3f9f8e248ff560f2f435293626c72987ebd2f66a0e9cf`
- 截图目录：`/home/dev/gdds-fe-logs/fe3c-fix2-07-r1/screenshots`（1280、1920 各 45 个）
- hostname：起止 `gw-dms-07.lan`
- 起止时间：`2026-11-10T01:49:27Z` 至 `2026-11-10T01:52:02Z`（入口 `2026-11-10T01:49:50Z` 起）
- 起止 HEAD：`e8864ce1da2dcd6d6536c421607abb383ec955d9` 至 `e8864ce1da2dcd6d6536c421607abb383ec955d9`
- frontend tree：起止 `46e425f84eb28936563c8751295a8829e33f3ad6`
- vnext tree：起止 `6368c9c40cf08a97eecf2a0c457a6c16ce448080`
- 起止 status：均空
- 结果：`86 passed`，`exit_code=0`；B7 `B7 确认归档禁用原因截图 (3.4s)` 通过；`fe3c-confirm-disabled-*` 五个名称在 1280、1920 下齐全（`blocked`、`loading`、`unchecked`、`unknown`、`unprocessed`）

### 2.2 全量 r2（Playwright 默认 workers）

- 外层日志：`/home/dev/gdds-fe-logs/fe3c-fix2-07-r2/outer-20261110T015214Z.log`，SHA256 `8d84a7eb8ca5630c254f7f843c980c6a29f7b3f67cde437b5ceb17282ea74a22`
- 入口日志：`/home/dev/gdds-fe-logs/fe3c-fix2-07-r2/frontend-tests-20261110T015237Z.log`，SHA256 `facac6c5225327046e30010abc08ae4f6d69a157946571572a75d01647f2691d`
- 截图目录：`/home/dev/gdds-fe-logs/fe3c-fix2-07-r2/screenshots`（1280、1920 各 45 个）
- hostname：起止 `gw-dms-07.lan`
- 起止时间：`2026-11-10T01:52:14Z` 至 `2026-11-10T01:53:44Z`（入口 `2026-11-10T01:52:37Z` 起）
- 起止 HEAD：`e8864ce1da2dcd6d6536c421607abb383ec955d9` 至 `e8864ce1da2dcd6d6536c421607abb383ec955d9`
- frontend tree：起止 `46e425f84eb28936563c8751295a8829e33f3ad6`
- vnext tree：起止 `6368c9c40cf08a97eecf2a0c457a6c16ce448080`
- 起止 status：均空；`e2e_workers=playwright-default`
- 结果：`86 passed`，`exit_code=0`；B7 `B7 确认归档禁用原因截图 (13.8s)` 通过；`fe3c-confirm-disabled-*` 五个名称在 1280、1920 下齐全

### 2.3 B7 压力（fix2，`--repeat-each=30 --workers=8`）

- 外层日志：`/home/dev/gdds-fe-logs/fe3c-fix2-07-b7-stress/outer-20261110T015414Z.log`，SHA256 `02d1ed35b050143c5cd981a97d20ae99648688c30f8c5556ee487e07148b82b7`
- hostname：起止 `gw-dms-07.lan`
- 起止时间：`2026-11-10T01:54:14Z` 至 `2026-11-10T01:54:36Z`
- 起止 HEAD：`e8864ce1da2dcd6d6536c421607abb383ec955d9` 至 `e8864ce1da2dcd6d6536c421607abb383ec955d9`
- frontend tree：起止 `46e425f84eb28936563c8751295a8829e33f3ad6`
- 起止 status：均空
- 结果：`30 passed`，`exit_code=0`

### 2.4 复现尝试（`cbb14f578c`，同样 `--repeat-each=30 --workers=8`）

- worktree `/home/dev/gdds-fe3c-fix1-wt`（detached，`cbb14f578cd22f37355db78a62ba9264f71477d3`，起止 clean）
- 外层日志：`/home/dev/gdds-fe-logs/fe3c-fix2-07-b7-repro-cbb/outer-20261110T015442Z.log`，SHA256 `bf013a44618540243c7d084a46b7ac843d8b9a6708ced8b95b1051408c72af70`
- hostname：起止 `gw-dms-07.lan`
- 起止时间：`2026-11-10T01:54:42Z` 至 `2026-11-10T01:55:03Z`
- 起止 HEAD：`cbb14f578cd22f37355db78a62ba9264f71477d3` 至 `cbb14f578cd22f37355db78a62ba9264f71477d3`
- frontend tree：起止 `f626a8f0b3ab4ebd2a3e1d7a3eb15e1803c48908`
- 起止 status：均空
- 结果：`30 passed`，`exit_code=0`，未复现原失败；原失败只在 04 的 86 worker 高负载下出现，07 的 2 worker 与 8 worker 下均不出现，不强求复现。

## 3. 停止核对 §2 原因说明

B7 失败是用例自身的路由竞态，与被测页面无关：

1. 第一段用 `previewDelayMs: 4000` 安装场景后截“正在预检”，此时预检处理函数正在 `setTimeout` 中等待。
2. 截图后 `page.unrouteAll()` 不带参数，行为是 `default`：不等正在运行的处理函数，处理函数之后抛出的异常照常抛出。
3. 第二、三段各自重装路由并 `page.goto("/")`，原预检请求随导航结束。
4. 约 4 秒后第一段遗留处理函数醒来，对已结束的请求调用 `route.fulfill`，得到 `Route is already handled!`。
5. 该异常让用例失败，表现为第三段 `openArchiveDialog` 的 `page.goto`（`:743`）报 `Test ended`。

失败栈 `:148` 是预检路由在等待后调用 `json()` 的位置，不是候选路由。失败与否取决于处理函数醒来落在哪个导航之后，所以和负载有关：07 两个 worker 时不出现，04 的 86 个 worker 时出现。
页面第一、二段截图已正常生成。本文件 `:473` 与 `workspace-shell.spec.ts` 的 11 处不带参数的 `unrouteAll` 写法同样不等处理函数，其中带延迟的三处（`timeoutFirstCompare`、`historyBundleDelayMs`、`slowPreview`）有相同竞态，已列为 FE4 带入项 N9。

## 4. 停止核对 §3 第 5 项：第一次 wrapper 失败说明

- 18:06:06 那次 wrapper 把 `LOG_DIR` 取成了 `$2`（即命令的第一个词 `env`），`env/` 目录不存在。
- bash 重定向失败时不执行命令，所以入口命令没有运行，也没有留下日志文件；报告里“外层日志落到 `env/`”不准确。
- 04 全盘搜索 `outer-*20261109T1806*` 只找到 18:06:27 那次的日志；截图目录 `shots/1280` 创建于 18:07:12Z，晚于重做开始时间，与“首次未运行”一致。
- 本 handoff 如实写明：首次运行无日志文件，无 SHA 可记；证据以 18:06:27 起的重做运行为准。
- 下一轮 wrapper 在写日志前检查参数，并确认日志目录存在（本轮 07 外层与 B7 wrapper 已先做：检查 worktree/logdir/shotdir 为绝对路径、截图目录在 worktree 外、日志目录存在后才写）。

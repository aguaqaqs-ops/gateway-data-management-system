# FE3c fix2 定向核对

结论：**通过，可以开始 04/05 取证**。fix2 按[停止核对](fe3c-evidence-stop-1.md) §3 第 1 项实现。07 上的复现与探针确认：原失败来自 B7 遗留的预检处理函数，fix2 消除了这个竞态。取证按停止核对 §4 第 4 项，在 handoff 提交 `e22e39ba15` 上进行。

| 项 | 值 |
| --- | --- |
| 范围 | `fe-vnext` `031dc3d754..e22e39ba15` |
| fix2 测试修复 | `e8864ce1da2dcd6d6536c421607abb383ec955d9`，父提交 `031dc3d754` |
| fix2 handoff | `e22e39ba1528c7a0339c9c800d87fb3f3f95190a`，新增 `docs/frontend-vnext/fe3c-handoff-fix2.md` |
| `HEAD:frontend` | `46e425f84eb28936563c8751295a8829e33f3ad6`（原为 `f626a8f0b3`） |
| `HEAD:vnext` | `6368c9c40cf08a97eecf2a0c457a6c16ce448080`（未变） |

## 1. diff 核对

`031dc3d754..e22e39ba15` 只改两个文件：`frontend/e2e/archive-validation.spec.ts`（+21/−10）和新增的 fix2 handoff。

- `previewDelayMs` 已删除，改为 `holdPreview` 闸门。`installArchiveScenario` 返回 `releasePreview`。预检处理函数先等闸门，再计数并响应。
- B7 第一段截“正在预检”后，依次 `releasePreview()`、等“预检状态”出现、调用 `unrouteAll({ behavior: "wait" })`。
  - “预检状态”这一节只在 `!loading && plan && candidates` 时渲染（`ArchiveMainlineDialog.tsx:419-421`），所以它可见就说明预检响应已经处理完。
  - 即使不靠这一点，`wait` 也会等在途处理函数结束。
- 本文件 5 处 `unrouteAll`（V7 1 处，B7 4 处）都带 `{ behavior: "wait" }`。
- 其他用例的断言、产品代码、`e2e-real/` 与脚本都没有改。`workspace-shell.spec.ts` 未动，对应 FE4 带入项 N9。

## 2. 实施会话 07 记录的核对

- **SHA256 重算。** 在 07 上现场重算以下 6 条日志，均与 handoff 一致：
  - r1 外层 `9253d9df12de…`、入口 `d8014fff7524…`；
  - r2 外层 `8d84a7eb8ca5…`、入口 `facac6c52253…`；
  - 压力 `02d1ed35b050…`；
  - 复现尝试 `bf013a446185…`。
- **wrapper 记录。** r1、r2 都记录了 hostname，起止 HEAD 与 `frontend/` 树，起止 status（两侧都为空），以及 exit code 0。r1 为 `Running 86 tests using 2 workers`，r2 为 `using 86 workers`，都是 86 passed。两次截图都是每个宽度 45 张，`fe3c-confirm-disabled-*` 五个名称齐全。
- **复现尝试为何没有复现。** 复现尝试在 8 个 worker 下运行 B7。旧 B7 在这个负载下只用 2.9–3.5 秒，早于 4 秒的预检延迟，遗留处理函数醒来时用例已经结束，所以没有复现。这与原因分析一致，见第 3 节。
- **十六进制核对。** 用脚本把 handoff 中每个十六进制值与来源逐个对照，来源包括 07 现场 `sha256sum`、日志字段和 git 对象：
  - 41 处、19 个不同值都能唯一回源；
  - 没有长度不是 7–12、40、64 的值。

  handoff 自报“21 个唯一值”，与本次统计口径不同，不影响结论。

## 3. 审核会话的独立运行与探针（07）

- 07 上没有占用标记。源码用 bundle 传到 07：bundle SHA256 `e7ba166533128d0782e22933a3d9ab5a506f2f3edc41f6dead11c54cc14f7b16`，fetch 到 `refs/review/fe3c-f2c/{candidate,handoff}` 后即删除。
- 运行目录：
  - fix2 用新的 detached worktree `/home/dev/gdds-fe3c-fix2check-run`（`e22e39ba15`，含 `legacy` 符号链接）；
  - 旧代码沿用复审第 1 轮的 `/home/dev/gdds-fe3c-rereview1-run`（`cbb14f578c`）。
- 两个 worktree 运行前后都是 clean。日志在 `/home/dev/gdds-fe-logs/fe3c-fix2-check/`。

| 运行 | 起止 UTC | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 旧代码 `cbb14f578c` 全量，默认 worker（86），带截图 | 02:07:23–02:08:53 | exit 1。B7 失败 `route.fulfill: Route is already handled!`，其余 85 passed，**复现了 04 的原失败** | `eb971be692cda2321e0c86af661518d1118e2473d2a8a2926d13658273caf5a3` |
| fix2 `e22e39ba15` 全量，默认 worker（86），带截图 | 02:08:53–02:10:17 | exit 0，86 passed。每个宽度 45 张截图，`fe3c-confirm-disabled-*` 五个名称齐全。截图清单 SHA256 `b6eec8573a0e8f7557b160651885ad741bd684fff77c3d033e8c9a9bf37f19aa`（190 行） | `3b38bdfbe841c0786462778e4c4a7c5169ae3908841dfb243519c0058752af1d` |

探针都是节点上一次性的已提交 worktree，只运行 B7，2 个 worker。运行后 worktree 与 probe ref 都已删除。

| 探针 | 改动 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| pa（`f32101862f`，基于 `cbb14f578c`） | B7 结尾加 `waitForTimeout(6000)`，让遗留处理函数在用例结束前醒来 | 失败 | 失败：`Route is already handled!`，必然复现 | `de9a238499d4db538e847f75b13d13f43d34b8028447d6ea9794dcf09b385f6b` |
| pb（`8e026b4ee1`，基于 `e8864ce1da`） | 同上，对照 | 通过 | 1 passed | `4fe33364e6f56d476658d8b5d27333b97d447eb0e5f4f7e531c83c2b050ff2f3` |
| pc（`18df7d80b3`，基于 `e8864ce1da`） | 删去 `releasePreview()` 和等“预检状态”两行，闸门未开就 `unrouteAll({ behavior: "wait" })` | 卡住 | 30 秒超时。闸门之后没有别的步骤会阻塞，说明 `wait` 确实在等在途处理函数 | `6ce529e055e6b58b80218af06096a8d7cdb35a93f9a61e8083c114b3b3d144c2` |

**对停止核对 §2 的细化。** 两次失败运行（旧代码全量、pa）的日志中，失败前都有一行 vite 代理错误：`/v1/archive-plan-preview` 连接 `127.0.0.1:8000` 被拒；三次通过的运行没有这一行。这说明处理函数被移除后，被挡住的预检请求已经交给网络，之后遗留处理函数再 `fulfill`，就遇到“已处理”。停止核对第 3、4 步写的是“请求随导航结束”，应以这里的观察为准。修复方式不受影响。

## 4. 非阻塞

- handoff §3 把 `workspace-shell.spec.ts` 中三处带延迟的 `unrouteAll` 写成“有相同竞态”。停止核对写的是“可能”，尚未证实。这一点保持为 N9 的待查内容，不需要更正提交。
- 07 的 `/home/dev` 下留有实施会话的传输 bundle `fe3c-fix1.bundle`、`fe3c-fix2-e8864.bundle`，应由实施会话删除。同目录的其他 bundle 不属于 FE3c，不动。
- 实施会话在 07 用自己的克隆 `/home/dev/gdds-fe3c-fix1-src` 调试，可以接受。证据仍以 04/05 的 bundle 传输为准。

## 5. 下一步

实施会话按停止核对 §4 第 4 项，在 `e22e39ba15` 上取证：

- 04 三项，`run-tests.sh` 设 `GATEWAY_FE_TEST_WORKERS=2`；
- 05 t1 重跑；
- 用新的 worktree 和证据目录；
- 证据 handoff 中加“前次运行”一节；
- wrapper 在写日志前检查参数。

完成后由审核会话写 `fe3c-evidence-check-1.md`。

保留到 FE3 exit 清理：

- 07 的 `/home/dev/gdds-fe3c-fix2check-run`、`refs/review/fe3c-f2c/{candidate,handoff}`、日志 `/home/dev/gdds-fe-logs/fe3c-fix2-check/`、截图 `/home/dev/gdds-fe-shots/fe3c-fix2check-{e22e39ba,old-cbb14f57}`；
- 开发主机的 `refs/review/fe3c-f2c/{candidate,handoff}`。

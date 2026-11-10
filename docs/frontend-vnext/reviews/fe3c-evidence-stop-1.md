# FE3c 证据运行停止核对第 1 次

结论：**测试竞态，定向修复测试后重新取证**。B7 失败是用例自身的路由竞态，不是产品缺陷。实施会话按 DC68 停止是正确的。修复只改 `frontend/e2e/archive-validation.spec.ts`。修复后在新的被测提交上重跑 04 的三项和 05 t1。本次 05 t1 只作参考记录，不沿用为证据。

| 项 | 值 |
| --- | --- |
| 被测提交 | `fe-vnext` `031dc3d754e754feb22bba793324f3d53bd80825`（fix1 handoff） |
| 代码 | `cbb14f578cd22f37355db78a62ba9264f71477d3` |
| `HEAD:frontend` | `f626a8f0b3ab4ebd2a3e1d7a3eb15e1803c48908` |
| 依据 | [复审第 1 轮](fe3c-rereview-1.md) §6（取证提示词） |

## 1. 现场核对

- **SHA256 重算。** 下面的值都在节点上用 `sha256sum` 现场重算，与实施会话报告一致：

  | 文件 | SHA256 |
  | --- | --- |
  | 04 外层日志 `/home/dev/gdds-fe-logs/fe3c-evidence-04/outer-run-tests-20261109T180627Z.log` | `1049fa85aeb54df362719ad391f60244793338ff836895ebad6657c5c26066f3` |
  | 04 入口日志 `frontend-tests-20261109T180649Z.log` | `e5e39c55f36e3d9c7ecf3bacf1dc81e98dde925abaf0d79828d9f73a46427f15` |
  | 05 外层日志 `/home/dev/gdds-fe-logs/fe3c-evidence-05/outer-t1-20261109T180756Z.log` | `378aa3d6a6db40f9156145505231105fdc47d0ce6c588ba3e059e3c27500f6cf` |
  | 05 入口日志 `real-backend-e2e-t1-fe3c-evidence-05-031dc3d75-20261109T180757Z-3036095.log` | `a60fafc31d40d714d831d4e1a5736ab0be09b192b5754ab2f68dd20622d25b7d` |
  | 05 case log `evidence/journey-cases.log` | `7a79568123c100af7eb2fef77707edc9942530dcf950d66b3bb421b68cc9440e` |

- **wrapper 记录。** 04 与 05 的外层日志都记录了以下字段：hostname，起止时间，起止 HEAD、`frontend/` 树与 `vnext/` 树，起止 `git status --porcelain --untracked-files=all`（两侧都为空），以及入口命令的 exit code。04 起始时的占用标记是本会话自己的，用途为非计时。两台节点上的证据 worktree 现在仍在 `031dc3d754`，状态 clean。
- **04 运行结果。** 运行时 `e2e_workers=playwright-default`：04 有 32 核，Playwright 用 86 个 worker 运行 86 个用例。结果 85 通过，1 失败。
- **05 t1 结果。** 以下字段与报告一致：
  - 两份清单 `cdb598cd…0163`、`fa2450fa…a96a`，各 `files=19`；
  - `table_count=125`，`composite_changed=0`；
  - M1 两次的 `renderer_increment_bytes` 为 22581248（MODIFIED_ONLY）与 13078528（FULL，只报告）；
  - `openapi_compare=match`，`cleanup_status=ok`，`exit_code=0`；
  - RS config digest `sha256:82eaa1057d9cf71f9c0cb63bdd03236e4bdc6125e4cc1a5b6b3446709591b76c`。

## 2. B7 失败原因

失败栈中的 `:148` 是**预检**路由在 `previewDelayMs` 等待后调用 `json()` 的位置。实施会话报告写成了“候选路由”，这里更正。

B7 的步骤和结果：

1. 第一段用 `previewDelayMs: 4000` 安装场景，然后截“正在预检”。此时预检请求的处理函数正在 `setTimeout` 中等待。
2. 截图后调用 `page.unrouteAll()`。不带参数时行为是 `default`：不等待正在运行的处理函数，处理函数之后抛出的异常也照常抛出。
3. 第二、三段各自重新安装路由并 `page.goto("/")`，原预检请求随导航结束。
4. 约 4 秒后，第一段遗留的处理函数醒来，对这个已结束的请求调用 `route.fulfill`，得到 `Route is already handled!`。
5. 这个异常让用例失败，表现为第三段 `openArchiveDialog` 的 `page.goto`（`:743`）报 `Test ended`。

失败与否取决于处理函数醒来的时刻落在哪一段导航之后，所以和负载有关：07 上两个 worker 时没有出现，04 上 86 个 worker 时出现。这是用例自身的竞态，与被测页面无关；页面在第一、二段的截图都已正常生成（`fe3c-confirm-disabled-loading`、`fe3c-confirm-disabled-blocked`）。

同一文件 `:473` 和 `workspace-shell.spec.ts` 中还有 11 处 `unrouteAll()` 不带参数。这些位置目前都通过了，但写法同样不等待正在运行的处理函数。

## 3. 决定

1. **修复（fix2，只改测试）。** 改动只限 `frontend/e2e/archive-validation.spec.ts`，并作为 `031dc3d754` 之上的新提交：
   - `installArchiveScenario` 不再用固定的 `previewDelayMs` 睡眠，改为由测试控制的闸门。场景返回一个释放函数，预检处理函数等闸门打开后才响应。
   - B7 截完“正在预检”后先释放闸门，等对话框显示“预检状态”，再调用 `page.unrouteAll({ behavior: "wait" })`，然后进入下一段。
   - 本文件所有 `unrouteAll` 都改为 `{ behavior: "wait" }`。
   - `workspace-shell.spec.ts` 已在 FE3b 取证中通过，本轮不改，列为 FE4 带入项 N9。
   - 不改其他用例的断言，不顺带处理 M1–M4。
2. **04 的 worker 数。** 04 取证设 `GATEWAY_FE_TEST_WORKERS=2`，与 FE3b 04 证据（`a300b16485` §3.1）和 07 的设置一致，并写进 handoff。修复本身不依赖 worker 数，由第 4 节的 07 压力运行证明。
3. **05 t1 不沿用。** 修复会改变 `frontend/` 树。FE3 exit tag 要绑定同一个被测提交，前端证据目前也没有沿用机制，重跑 t1 约 4 分钟。所以 t1 在新提交上重跑一次。本次 t1 已核对 SHA 和字段，写进新的证据 handoff 的“前次运行”一节作参考，不作证据。
4. **DC68 计数。** 本次 run-tests 失败发生在被测对象运行之后，停止是正确的。新被测提交的取证重新计数，同 FE2b Q14 的先例。
5. **第一次 wrapper 失败。** 18:06:06 那次 wrapper 把 `LOG_DIR` 取成了 `$2`，即命令的第一个词 `env`，`env/` 目录不存在。bash 的重定向失败时不执行命令，所以入口命令没有运行，也**没有留下日志文件**；报告里“外层日志落到 `env/`”不准确。04 全盘搜索 `outer-*20261109T1806*` 只找到 18:06:27 那次的日志。截图目录 `shots/1280` 创建于 18:07:12Z，晚于重做的开始时间，与“首次未运行”一致。新 handoff 要如实写明“无日志文件”，并附终端输出。下一轮 wrapper 在写日志前检查参数，并确认日志目录存在。

## 4. 下一步（给实施会话的提示词）

> 你是 FE3c 实施会话。取证停止的核对结论在本地 main 的 `docs/frontend-vnext/reviews/fe3c-evidence-stop-1.md`，用 `git show main:<路径>` 读取，不切换开发主机任何 worktree 的分支。
>
> **1. 修复（只改测试）。** 在 `fe-vnext` 的 `031dc3d754` 之上按本文 §3 第 1 项提交，只改 `frontend/e2e/archive-validation.spec.ts`：
>   - 预检延迟改为由测试控制的闸门；
>   - B7 释放闸门并等到“预检状态”后再 `unrouteAll({ behavior: "wait" })`；
>   - 本文件所有 `unrouteAll` 都带 `{ behavior: "wait" }`。
>
>   不改其他断言、产品代码、`e2e-real/` 或脚本。
>
> **2. 07 调试验证。** 在 07 的 clean detached worktree 中：
>   - 运行 `frontend/scripts/run-tests.sh --e2e --screenshots <目录>` 两次，一次 `GATEWAY_FE_TEST_WORKERS=2`，一次不设（Playwright 默认）。两次都要 B7 通过，`fe3c-confirm-disabled-*` 五个名称在 1280、1920 下齐全。
>   - 在工具链容器中单独运行 B7：`--repeat-each=30`，worker 数不少于 8，全部通过。
>   - 能在 `cbb14f578c` 上用同样的单独运行复现原失败时，一并记录；复现不了就写明，不强求。
>   - 每次运行记录 hostname、起止时间、起止 HEAD、起止 status、exit code 和日志 SHA256。
>
> **3. handoff fix2。** 新增 `docs/frontend-vnext/fe3c-handoff-fix2.md`，作为单独的 docs-only 提交，内容包括：
>   - 改动说明与 diff 范围；
>   - 07 的运行记录；
>   - 本文 §2 的原因说明；
>   - 本文 §3 第 5 项要求的第一次 wrapper 失败说明。
>
>   提交前用脚本核对文中每个十六进制值，并报告长度不是 7–12、40、64 的值。完成后交审核会话做定向核对。**核对通过之前不开始 04/05 取证。**
>
> **4. 核对通过后取证。** 按复审第 1 轮 §6 的提示词，在 fix2 handoff 提交上重新取证，并做以下变更：
>   - 04 的 `run-tests.sh` 设 `GATEWAY_FE_TEST_WORKERS=2`；
>   - 用新的 worktree 和新的证据目录，不覆盖 `031dc3d754` 那轮的日志与截图；
>   - 05 t1 也在新提交上重跑；
>   - 证据 handoff 加一节“前次运行（`031dc3d754`，已停止）”：列出本文 §1 的日志 SHA256 和 05 t1 的结果，注明只作参考；
>   - wrapper 在写日志前检查参数与日志目录。
>
> 不合入 main、不 rebase、不推送。保留 `031dc3d754` 那轮的 04/05 worktree、日志与截图，等 FE3 exit 清理时再处理。

## 5. 非阻塞项更新

在复审第 1 轮的基础上新增一项：

- **N9.** `workspace-shell.spec.ts` 中 11 处 `unrouteAll()` 不带参数。其中 `timeoutFirstCompare`、`historyBundleDelayMs`、`slowPreview` 带有延迟，可能出现与 B7 相同的竞态。列为 FE4 带入项，在 FE4 中统一改为 `{ behavior: "wait" }`，或者改用闸门。

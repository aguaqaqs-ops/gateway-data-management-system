# FE3b 复审第 3 轮 N5 定向复核

- **审核对象：** 分支 `fe-vnext`，范围 `88237dbc3b..a3b72d4461`。
  - 代码候选 `dac69890a8`，`frontend/` 树 `54b5a333c6`；
  - handoff 提交 `a3b72d4461`（只新增 `docs/frontend-vnext/fe3b-handoff-fix4.md`）。
- **依据：** [复审第 3 轮报告](fe3b-rereview-3.md)（`ae3117eb89`）§5 N5；fix4 handoff。
- **日期：** 2026-11-09。
- **结论：通过。** N5 已补齐：工作台页提示的“重试”现在有用例保护。产品代码没有改动，04 取证改在 `dac69890a8` 上运行（替代第 3 轮报告 §6 中的 `1e5c43ee65`）。

## 1. 路径核对

| 检查 | 结果 |
| --- | --- |
| `git rev-parse dac69890a8:vnext`、`a3b72d4461:vnext` | 都是 `56720104af34a1eb677336f57bdbc07444a56615` |
| `git diff --stat 88237dbc3b a3b72d4461` | 只有 `frontend/e2e/workspace-shell.spec.ts`（+103）与 `docs/frontend-vnext/fe3b-handoff-fix4.md` |
| `git log --merges 88237dbc3b..a3b72d4461` | 无合入 |
| 提交序列 | `926af9f983`、`dac69890a8`、`a3b72d4461`，与 handoff 一致 |

## 2. 用例核对

两条新用例都在工作台页（`/?page=workspace&operationId=submit-op-1&operationKind=operation`）上运行：

- **“工作台续做提示重试时按已知 attempt 重读并保留原提示”**：对应 n3/W9①。操作结束时两个指针被清空、attempt 为 `ABORTED`。提示框显示“提交未完成…”和原始代码 `IMPORT_REJECTED`；选目录后，卡片和工具栏的“上传”都可用。点提示框内的“重试”后，先等 attempt 读取次数增加，再断言提示、原始代码和“上传”仍在。
- **“工作台续做提示重试时读不到提交结果仍保留刷新提示”**：对应 W9④ 前半，attempt 读不到时保留“无法读取提交结果，请刷新后重试”。

两条用例的定位都限定在 `.workspace-notice[role="alert"]` 内，不会点到比较托盘或历史抽屉里的“重试”。第二条在重试后断言的提示文字与重试前相同，靠 attempt 读取计数区分新旧状态，这与第 3 轮 N6 指出的 W9④ 写法一致，不影响结论。

## 3. 独立运行与探针（05，`gw-dms-test-05`）

- 运行前五个节点都没有占用标记。我以 `fe3b-rereview-n5` 在 05 上取得标记（03:14:39Z 起），运行结束后释放。
- 源码经 git bundle（`88237dbc3b..a3b72d4461`，SHA256 `104db945…a58a`）传入，在 detached worktree `/home/dev/gdds-fe-n5check-fe3b` 上运行。运行前后都 clean，起止 HEAD 都是 `dac69890a8`。
- 日志目录 `/home/dev/gdds-fe-logs/fe3b/rereview-n5/`。

| 运行 | 结果 | 日志 SHA256 |
| --- | --- | --- |
| `run-tests.sh --e2e`，`GATEWAY_FE_TEST_WORKERS=2`，npm 缓存两变量指向 `/home/dev/gdds-fe-cache/fe0/`，03:15:01–03:16:52Z | exit 0：单测 32 个文件 175 项，Playwright 63 项（含两条新用例） | 入口日志 `ed564830…743d`；外层 `d05dda22…138d` |
| 探针 G1w：工作台页提示“重试”改回 `load()`（提交 `3c77682493`） | **符合**：只有两条新用例失败，61 passed | `7e4f3a82…c49e` |
| 探针 G1c：预览页提示“重试”改回 `refreshUploadMode()`（提交 `55194d5e53`） | **符合**：只有 n3/W9①、W9③b、W9④ 失败，两条新用例通过，60 passed | `024c083b…417c` |

探针 worktree、`refs/review/fe3b-n5/probe-*`、05 上的传输 bundle 与探针脚本目录都已删除；diff 存于 `probes/probe-*.diff`。

## 4. handoff 核对

- fix4 中的 14 个 64 位 SHA 与 05 上的文件一致，包括：三次运行日志、两个探针日志、两个传输 bundle、5 个内层 `frontend-tests` 日志，以及工具链 digest 和 npm 缓存归档。
- 首轮失败（`926af9f983`，挂载读被 hold 的操作挡住）已保留日志。修订后在 `dac69890a8` 上连续两次完整运行都通过，按 DC68 处理得当。
- 真实 journeys、`validate-upload-package.sh` 和截图都没有重跑，理由成立：本轮只改 mock e2e 用例。
- 小处：
  - 日志目录是 `/home/dev/gdds-fe-logs/fe3b-fix4-n5/`，与前几轮的 `fe3b/<轮次>/` 布局不同；
  - 05 上还有一个更早留下的 worktree `/home/dev/gdds-fe-fix4-05`（HEAD `fa507ee77c`），fix4 没提到。

  这两处都在 FE3b 退出清理时处理。

## 5. 下一步

1. 04 取证在 `dac69890a8` 上进行：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`run-real-backend-e2e.sh --suite journeys --subphase fe3b` 各运行一次。
2. 截图交 owner 确认（N3、N4）。N2、N6 仍是非阻塞项。取证后做证据核对，再给出 FE3b 退出建议。
3. 保留供对照，FE3b 退出后清理：
   - 05 的 `/home/dev/gdds-fe-n5check-fe3b` 与 `refs/review/fe3b-n5/{candidate,handoff}`；
   - 开发主机的 `refs/review/fe3b-n5/{candidate,handoff}`；
   - 05 的 `/home/dev/gdds-fe-logs/fe3b/rereview-n5/`。

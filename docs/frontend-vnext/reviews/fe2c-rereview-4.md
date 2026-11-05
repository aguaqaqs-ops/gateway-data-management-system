# FE2c 复审报告（第 4 轮）

- **复审对象：** 开发主机分支 `fe-vnext`。
  - 代码候选 `e3835718eb6879a7461c176820c5576f87c48b81`，`frontend/` 树 `960ab1f6a1`；
  - handoff 提交 `220325da3770fc94ce610a73f983cd26871e4a65`（相对代码候选只改 handoff，`frontend/` 树相同）。
- **范围：** `01a232c40b..220325da37`，共 2 个代码提交、8 个 `frontend/` 文件（88+/35-），加上 handoff。`vnext/` 没有改动。
- **依据：** [复审第 3 轮](fe2c-rereview-3.md) §3–§5；AGENTS“前端测试（FD7）”。
- **日期：** 2026-11-04。
- **结论：通过（PASS），可以去 04 取证。**
  - R6、R7 修复正确；我在已提交的一次性 worktree 上复做了两个回归探针，去掉修复后断言都失败（§2.3）。
  - n1、n3–n7 已处理；n2 实际也有 e2e 覆盖，只是 handoff 写成了“部分”（§3）。
  - 剩下的都是 handoff 文字和流程上的小问题，在 04 取证的 handoff 中改正即可，不需要再改代码。

## 1. 核对

| 项 | 核对 | 结论 |
| --- | --- | --- |
| R6 | `Dialog` 增加 `alert` 区，位于可滚动的 `.dialog__body` 与底部按钮区之间，不随内容滚动。归档失败（含开始归档失败）、提交未完成、提交失败、需要管理员处理都放进这一区。e2e 在 1920 与 1280 下对归档冲突的错误码与“刷新预检”、提交未完成的错误码、需要管理员处理断言 `toBeInViewport()`；审核“刷新审核信息”也加了同样的断言。截图 `archive-audit-conflict-*` 能看到错误码、复制与“刷新预检” | **通过** |
| R7 | `.dialog` 设 `white-space: normal`，所有对话框不再继承顶栏样式；`.confirm-impact` 允许换行。e2e 在 1280 下断言通过、退回、撤回三个对话框的影响说明不溢出。截图 `review-withdraw-dialog-*` 完整显示“此操作不可撤销” | **通过** |
| n1 | 刷新失败时进入失败阶段，显示 `REFRESH_FAILED`；新增 e2e | **通过** |
| n2 | 新增 `onDownloadStart`，开始下载时阶段切到“下载”；`FE2c 上传失败后重试不重复上传` 的断言改为“预览已生成，但下载比较结果失败，请重试”，截图 `upload-failure-retry-*` 显示该文案 | **通过**（handoff 记为“部分”，见 §3） |
| n3 | 续做时 `ABORTED`、缺少提交、读取失败、操作失败都显示提示；续做期间“提交”按钮禁用并说明原因。失败分支没有 e2e，handoff 已如实说明 | **通过**（接受，无专门 e2e） |
| n4 | 第 3 轮 handoff 的说明不再单独补 | 接受 |
| n5 | 注释已改准确 | **通过** |
| n6 | 预检失败按错误显示错误码与复制；403 时“确认归档”的禁用原因为“当前身份没有归档权限” | **通过** |
| n7 | 补拍 `upload-running-modified-only-1280` | **通过** |

## 2. 证据核对与我在 05 上的运行

### 2.1 实施会话的证据

- bundle `/home/dev/gdds-test-tmp/fe2c-fix4-e3835718.bundle`，SHA256 与报告一致（`c2bb3142…4221f2`）。
- `fix-4/` 下两个 runner 日志、三个探针日志的 SHA256 都与 handoff §3 一致。
- 最后一次 runner（`15:41:51Z`–`15:42:44Z`）：起止 HEAD `e3835718eb`，exit 0，130 个单测、32 个 e2e。
- 截图 94 张，按 handoff 的公式（`sha256sum *.png | sort -k2 | sha256sum`）聚合 SHA256 一致（`eed53692…27e5f7`）。这一轮的聚合公式与前几轮（`find … | sort -z | xargs -0 sha256sum | sha256sum`）不同；04 取证时请写明所用公式。
- 上传包校验本轮没有运行。我核对过 `9518278fef..e3835718eb` 没有改动 `frontend/scripts`、`upload-package.ts`、`features/bundle` 与 `vnext/`，符合第 3 轮 §5 第 3 条的条件。

### 2.2 我的运行

源码经 bundle 传到 05（`/home/dev/gdds-test-tmp/src-rereview4-fe2c-220325da.bundle`，SHA256 `23717c7f35e8fc109fc4580a5251f1e8861d418a907cbabace309217b4aef592`，ref `fe-vnext`，只取 `FETCH_HEAD`），worktree `/home/dev/gdds-fe-rereview4-fe2c-220325da-05`（detached `220325da37`）。开发主机的只读 worktree 为 `/home/dev/gdds-fe-rereview4-fe2c-220325da`。

日志在 05 的 `/home/dev/gdds-fe-logs/fe2c/rereview-4/`，驱动日志为 `rereview-05.log`，SHA256 `2d180fec0df65151e2919b3518a392275c71bdc899e47481dc2c59ac401401de`（`15:51:56Z`–`15:55:41Z`）。运行期间 05 没有占用标记。

- **runner**（`--e2e --screenshots /home/dev/gdds-fe-evidence/fe2c/rereview4-220325da-05`）：日志 `frontend-tests-20261104T155219Z.log`，SHA256 `4d8bb0d3c8da90a9d6b9539e569eb470ac70b21a80bc4694a49ee950b3e217be`；exit 0，27 个单测文件 130 项、生产检查、32 个 e2e 全部通过；起止 HEAD `220325da37`，`frontend/` 树 `960ab1f6a1`；运行前后 worktree clean。
- **截图：** 94 张。
  - 聚合 SHA256：前几轮的公式 `b67f2bd066b132eb849e7f166747e36b31da5831b10732a753c737174cf10c80`；handoff 的公式 `0ffa2394ee3af6587e8897143b5a31765d333cf9f2472614b57b243547a913da`。
  - 文件名与实施会话一致，85 张逐字节相同。不同的 9 张是执行中、抽屉与几个对话框，属于前几轮也有的渲染差异。

### 2.3 回归探针

两个探针各在以 `220325da37` 为基础的一次性 worktree 中修改，以 `review-probe` 身份提交后运行完整 runner（`--e2e`），结束后删除 worktree。修改脚本在 05 的 `/home/dev/gdds-test-tmp/fe2c-rereview4-edit.py`。

| 探针 | 修改 | 结果 |
| --- | --- | --- |
| R6 | `Dialog` 的 `alert` 区放回 `.dialog__body` 末尾（探针提交 `64365d89fc`，日志 `probes/frontend-tests-20261104T155334Z.log` `01f1320d…7f59`） | exit 1：`FE2c 归档 403、审计冲突与阻断项` 失败，`viewport ratio 0`。提交对话框的断言仍通过，因为提交对话框内容较短，没有滚动 |
| R7 | 删除 `.dialog` 与 `.confirm-impact` 的换行设置（探针提交 `71105ccdf9`，日志 `probes/frontend-tests-20261104T155449Z.log` `943b66a9…b2e2b2`） | exit 1：退回、撤回两条 e2e 在影响说明溢出断言处失败 |

实施会话的探针结果与此一致。但 handoff §3 把探针记为 `ec503f39`，日志里没有 hostname、HEAD 与提交记录，是在未提交的改动上直接运行 Playwright；前几轮要求探针改动先提交再运行。探针不作为证据，本轮由我在已提交的 worktree 上复做，不再要求补做。

## 3. handoff 需要改正的地方（在 04 取证的 handoff 中一并改）

1. **n2 的状态：** §2 表中写“部分（下载阶段文案无专门 e2e）”，§6 写“现有重试用例在 Preview 进行中失败，断言的是通用前端文案”。实际上 `ec503f39` 已把该用例的断言改为下载失败文案，截图也是。请改为“完成”，并从 §6 删除。
2. **R6 的描述：** §2 写“审核刷新……移入 `Dialog` 底部固定区”，但 `ReviewActions` 没有改动，审核对话框的错误仍在正文中。审核对话框内容短，提示在可视区域内，已有 `toBeInViewport()` 断言，功能没有问题，只需把描述改准确。
3. **探针记录：** §3、§4 注明探针是在未提交的改动上运行的 focused Playwright，不是 runner。
4. **截图聚合公式：** 写明所用公式。

## 4. 次要问题（不阻塞，可留到后续阶段）

- **n8：** 截图 `submit-manual-recovery-*`：“操作 ID `submit-op-1`复制 ID系统仍在查询状态”中，ID、链接与后文之间没有空格，链接按钮像嵌在句子中间。这一行也没有 `form-error` 那样的提示样式，和同一区域的其他提示不一致。

## 5. 04 取证

1. 在 04 的 clean、已提交 detached worktree 上运行：
   - runner `--e2e --screenshots <worktree 外的新目录>` 一次；
   - 上传包校验脚本一次（`--output <空目录> --log-dir <日志目录>`）。
   - npm 缓存使用 04 的默认预填路径 `/home/dev/gdds-fe-cache/frontend/`，归档 SHA256 应为 `0d861824…089f4`。
2. 取证对象为代码候选 `e3835718eb`，或本 handoff 提交 `220325da37`（两者 `frontend/` 树相同）。§3 的改正写进新的 handoff 提交（只改文档）。
3. 新 handoff 记录 04 的 hostname、起止时间、起止 HEAD、exit code、日志 SHA256、工具链与依赖镜像身份（config digest 与全部 DiffID）、npm 缓存来源，以及截图目录与聚合 SHA256。
4. 之后由我做证据核对；通过后在最终 handoff 提交上打 `fe-fe2c-exit`。

## 6. 本轮在节点上留下的内容

- **开发主机：** 只读 worktree `/home/dev/gdds-fe-rereview4-fe2c-220325da`；bundle `/home/dev/gdds-test-tmp/src-rereview4-fe2c-220325da.bundle`。
- **05：**
  - worktree `/home/dev/gdds-fe-rereview4-fe2c-220325da-05`；
  - bundle `/home/dev/gdds-test-tmp/src-rereview4-fe2c-220325da.bundle`；
  - 驱动与探针脚本 `/home/dev/gdds-test-tmp/fe2c-rereview4.sh`、`fe2c-rereview4-edit.py`；
  - 日志与探针结果 `/home/dev/gdds-fe-logs/fe2c/rereview-4/`；
  - 截图 `/home/dev/gdds-fe-evidence/fe2c/rereview4-220325da-05/`。

  探针 worktree 已删除。FE2c 退出合入后，与第 1–3 轮的内容一起清理。

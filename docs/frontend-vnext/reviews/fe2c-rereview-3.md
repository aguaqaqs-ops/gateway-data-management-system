# FE2c 复审报告（第 3 轮）

- **复审对象：** 开发主机分支 `fe-vnext`。
  - 代码候选 `9518278fef1ca43f42bdf0e76461ba95c21658e2`，`frontend/` 树 `88f51b1471`；
  - handoff 提交 `01a232c40be247bb9b22d69c23d3f054bf75c590`（相对代码候选只改 handoff，`frontend/` 树相同）。
- **范围：** `e42d40e526..01a232c40b`。
  - 其中 `98bfb9522a` 合入 main（只有文档：复审第 2 轮报告与 Q18）；
  - FE2c 的改动为 4 个提交、11 个 `frontend/` 文件，加上 handoff。`vnext/` 没有改动。
- **依据：** [复审第 2 轮](fe2c-rereview-2.md) §3–§5；[FE2 kickoff](../fe2-kickoff.md) §6.2、§7.1、§9 Q18；AGENTS“前端测试（FD7）”“镜像身份”。
- **日期：** 2026-11-04。
- **结论：定向修复，范围很小。**
  - R1–R5 全部按要求完成，m1–m6 已处理；我在 05 上的完整运行与上传包校验都通过（§2）。
  - 看截图时发现两处“用户看不到关键内容”的问题，与 R4 同类，探针已证实（§3）：
    - R6：归档对话框的错误提示出现在可滚动区域底部，点“确认归档”后可视区域内没有任何变化；
    - R7：审核对话框继承了顶栏的 `white-space: nowrap`，退回、撤回的影响说明被截断，撤回的“此操作不可撤销”看不到。R4 的根因也是这一条。
  - 这两处在第 2 轮的候选中已经存在，是我上一轮漏看的。
  - 修复只涉及样式、滚动和几条断言。第 4 轮只核对 R6、R7 的改动与截图，通过后去 04 取证。

## 1. R1–R5、m1–m6 核对

| 项 | 核对 | 结论 |
| --- | --- | --- |
| R1 | 按 Q18 甲删除了空基线判断、两段说明、对应 e2e 与 `emptyBaseline` 路由桩；`src`、`e2e` 中没有残留。第 ① 步显示“可选”，可以操作 | **通过** |
| R2 | 确定的 4xx（408、429 除外）后丢弃整份进度；版本冲突与 `PREVIEW_BINDING_CONFLICT` 只给“刷新”，刷新时重新读取工作区与 History 头。重试时 `runPreviewJourney` 重新取工作区版本，基线版本取自刷新后的 `head`。新 e2e 点击“刷新”后第二次上传带版本 14、新 key 并成功；实施会话的探针（不丢弃进度）使该用例失败 | **通过**，次要问题见 n1 |
| R3 | 脚本与 `generate-backend-bundle-fixtures.sh` 的入口约束一致：worktree clean、两个镜像已加载、输出目录为空、日志与 `.sha256` 写在 worktree 外、记录各输入的 SHA256、按镜像 `inputs.json` 核对 `uv.lock`/`.python-version`（不一致 exit 2）、`pyproject.toml`/`Cargo.lock` 只记录、身份由 `docker image save` 取得。日志中的 config digest 与 runner、FE1 handoff 的记录相同（工具链 `sha256:a0d7b2b4…a1017`，依赖镜像 `sha256:b5b54224…e4b92a`）。两个停止探针结果正确 | **通过** |
| R4 | 审核、提交、归档的错误提示改为三行（说明、错误码、操作），1280 下有“刷新审核信息”在对话框内的断言；截图 `review-version-conflict-*` 完整 | **通过**；同类问题见 R6、R7 |
| R5 | 退回以审核人发起并核对 `Bearer dev-token-reviewer`；归档主线以归档确认人发起，确认、异常处理、开始归档的请求都核对了 `Bearer dev-token-archive-confirmer`；截图右上角身份正确 | **通过** |
| m1 | 回调存入 ref，effect 只依赖 `operationId` 与刷新计数 | **通过** |
| m2 | 固定了页面时钟；失败标题取前端文案；上传卡负责的操作不再另显示操作卡片 | **通过**，见 n2 |
| m3 | 随 R1 删除 | **通过** |
| m4 | 提交受理后记下操作与 attempt，刷新后在比较页显示操作卡片，成功后进入提交结果；e2e 已加 | **通过**，见 n3 |
| m5 | 不再把文字检查列为 N6 的证据 | **通过** |
| m6 | 加了场景注释 | **通过**，注释措辞见 n5 |
| N8 | 空基线项按 Q18 撤回，handoff §6 记为偏差 | 与 Q18 一致 |

## 2. 证据核对与我在 05 上的运行

### 2.1 实施会话的证据

- bundle `/home/dev/gdds-test-tmp/fe2c-fix3-9518278fef.bundle`，SHA256 与 handoff 一致（`9b0dc161…4f38e4`）。
- `fix-3/` 下 5 个 runner 日志与校验脚本日志的 SHA256 都与 handoff §3 一致；最后一次运行（`12:01:07Z`）起止 HEAD `9518278fef`，exit 0，130 个单测、31 个 e2e。
- 4 个探针日志的 SHA256 与 handoff §4 一致，失败点都是目标断言：
  - R2 探针：第二次上传仍用旧 key；
  - R4 探针：按钮下边缘 964 > 对话框下边缘 900.5；
  - R3 两项：分别停在 `dependency-input-preflight` 与 `preconditions`，exit 2。
- 截图 93 张，聚合 SHA256 与 handoff §5 一致（`4286296a…bd0e25`）。
- handoff §3 第 2 次运行（`11:56:24Z`，exit 0）是 `run_e2e=0`，只跑了单测阶段，handoff 没有注明（n4）。

### 2.2 我的运行

源码经 bundle 传到 05（`/home/dev/gdds-test-tmp/src-rereview3-fe2c-01a232c4.bundle`，SHA256 `a7855351d037b6e426e117d3406c6e0eb3fe6f6e12759f57b486c77532d66207`，ref `fe-vnext`，只取 `FETCH_HEAD`），worktree `/home/dev/gdds-fe-rereview3-fe2c-01a232c4-05`（detached `01a232c40b`）。开发主机的只读 worktree 为 `/home/dev/gdds-fe-rereview3-fe2c-01a232c4`。

日志在 05 的 `/home/dev/gdds-fe-logs/fe2c/rereview-3/`。驱动日志 `rereview-05.log`，SHA256 `9fda23f28da4eaa0f42c35bc0cd37a00c3b6beac5e749dea1f1ac8a9af55f0d7`，`14:43:49Z`–`14:45:51Z`。运行期间 05 没有占用标记。

- **runner**（`--e2e --screenshots /home/dev/gdds-fe-evidence/fe2c/rereview3-01a232c4-05`）：
  - 日志 `frontend-tests-20261104T144413Z.log`，SHA256 `57f2fb57febf47f18067c4ad0b94245015096b2c2ad34b7340abb819afc53bf3`；
  - `14:44:13Z`–`14:45:05Z`，`gw-dms-test-05.lan`，起止 HEAD `01a232c40b`，`frontend/` 树 `88f51b1471`，exit 0；
  - 27 个单测文件 130 项、生产检查、31 个 e2e 全部通过；运行前后 worktree clean。
- **截图：** 93 张，聚合 SHA256 `75a5d4a47f3f38d0e8a9bc96d6bbfd5dd8b22f1453b1fb102e1ab9c011b7a589`。文件名与实施会话一致，86 张逐字节相同。不同的 7 张是抽屉、S2 托盘、上传执行中与几个对话框，前几轮也有同类渲染差异。
- **上传包校验**（`--output /home/dev/gdds-test-tmp/fe2c-rereview3-upload-validation --log-dir <上述目录>`）：
  - exit 0，4 个包结果符合预期；
  - 日志 `upload-validator-01a232c40b-20261104T144505Z-1095518.log`，SHA256 `fde25a81f54786c1fcf814b92cd9f8ceadc3592677224ecee49c2e54e92541e5`；
  - 运行后 worktree clean。

### 2.3 探针

两个探针都在以 `01a232c40b` 为基础的一次性 worktree 中修改 e2e，以 `review-probe` 身份提交后运行 runner（`--e2e`），结束后删除 worktree。脚本在 05 的 `/home/dev/gdds-test-tmp/fe2c-rereview3-probe*.sh`。

| 探针 | 内容 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 归档冲突提示是否可见 | 在 `FE2c 归档 403、审计冲突与阻断项` 出现 `ARCHIVE_AUDIT_VERSION_CONFLICT` 后，断言错误码（1920×1080）和“刷新预检”（1280×900）`toBeInViewport()` | 两条都失败（exit 1）：提示在 DOM 中可见，但不在可视区域 | 驱动 `probe-05.log` `9090c1d4…641dc51`；runner `frontend-tests-20261104T144837Z.log` `2871bdf6…8f332af` |
| 审核对话框文字是否换行 | 在退回、撤回对话框中，1280×900 下断言 `.confirm-impact` 的 `scrollWidth <= clientWidth` | 两条都失败（exit 1） | 驱动 `probe2-05.log` `228f1c02…bd5`；runner `frontend-tests-20261104T145136Z.log` `239073ad…184a5` |

## 3. 需要修复

**R6. 归档对话框的错误提示不在可视区域内**（`ArchiveMainlineDialog.tsx:190` 起的 `failure` 块）

- **现状：**
  - 错误提示渲染在对话框可滚动区域的最底部，位于“确认后的影响”之后；
  - 对话框带有确认项与异常处理时，内容比可视高度长。点“确认归档”失败后，可视区域内没有变化，用户看不到错误码，也看不到“刷新预检”；
  - 截图 `archive-audit-conflict-1280/1920` 名为冲突状态，画面里却只有填好的确认表单。e2e 用 `toBeVisible()` 断言，它不检查元素是否在可视区域内，所以没有发现；
  - 开始归档（`POST /v1/archives`）失败也走这个块，情况相同。
- **修复：**
  - 失败时把提示滚动到可视区域并移动焦点（`scrollIntoView` + `focus`，提示设 `tabIndex={-1}`）；或者把提示放到对话框底部按钮区的上方，不随内容滚动；
  - e2e 在两种宽度下对错误码与“刷新预检”断言 `toBeInViewport()`；
  - 提交对话框在需要身份确认时同样较长（1280 下需要滚动），请一并检查失败提示的位置，并在 `submit-aborted` 或身份确认场景加同样的断言；
  - 重拍 `archive-audit-conflict-*`，截图中应能看到错误码与“刷新预检”。

**R7. 审核对话框的文字不换行，影响说明被截断**（`ComparisonPage.tsx:475–477`；`styles.css:140` `.compare-status`）

- **现状：**
  - `ReviewActions` 渲染在 `.compare-status` 内，三个审核对话框是它的子元素，没有通过 portal 移出，因此继承了 `white-space: nowrap`；
  - 截图 `review-reject-dialog-*`：影响说明在“退回理由会保留在审”处被对话框裁掉；
  - 截图 `review-withdraw-dialog-*`：“此操作不可撤销”被裁掉。这是撤回前唯一的不可逆提示；
  - 第 2 轮 R4 中“刷新审核信息”超出对话框，根因也是这一条。本轮把错误提示拆成三行，只绕开了这个问题。理由较长的错误文字仍会被截断。
- **修复：**
  - 对话框根元素设 `white-space: normal`（例如 `.dialog`），或把对话框通过 portal 渲染到 `body`。两种做法都能让所有对话框不再继承顶栏样式；
  - e2e 在 1280 下断言退回、撤回、通过三个对话框的 `.confirm-impact` 满足 `scrollWidth <= clientWidth`，或断言“此操作不可撤销”`toBeInViewport()`；
  - 重拍 `review-reject-dialog-*`、`review-withdraw-dialog-*`、`review-version-conflict-*`。

## 4. 次要问题（不阻塞）

- **n1：** `refreshAfterConflict` 先把阶段设为 `idle` 再刷新，刷新失败时设置的 `REFRESH_FAILED` 错误不会显示，因为错误面板只在 `phase === "failed"` 时渲染。用户点“刷新”后如果网络失败，界面没有任何提示。
- **n2：** `errorMessage` 中“预览已生成，但下载比较结果失败”只在 `phase === "downloading"` 时生效，而阶段只在收到下载进度后才切到 `downloading`。下载请求直接失败时阶段仍是 `previewing`，显示的是通用的“服务暂时不可用”（截图 `upload-failure-retry-*`）。文案取自前端，符合 C6，可以保留；若要区分，阶段切换应在开始下载时进行。
- **n3：** 提交刷新后的续做：
  - 操作成功、attempt 为 `ABORTED`（没有 `submission_id`），或读取 attempt 失败时，代码只清除标记并返回，界面停在“已完成”的操作卡片，没有“提交未完成”与错误码；
  - 续做期间比较页的“提交”按钮仍可点击。
  - 建议续做失败时显示与提交对话框相同的提示，续做期间禁用“提交”。
- **n4：** handoff §3 第 2 次运行只跑了单测阶段（`run_e2e=0`），请在表中注明。
- **n5：** m6 的注释写“异常场景固定以 submission-1 为异常目标提交”，但非阻断分支的异常目标是 `candidateId`，`approvedSubmission` 时为 `fe2a-history-ref-2`（截图 `archive-audit-conflict-*`）。只有阻断分支沿用 `ARCHIVE_PLAN_NEEDS_CONFIRMATION` 中的 `submission-1`。请把注释改准确。
- **n6：** 截图 `archive-permission-denied-*`：
  - 预检返回 403 后，“确认归档”下的禁用原因仍是“正在预检”；
  - 这条错误没有“复制错误代码”，与其他错误提示不一致。
- **n7：** `upload-running-modified-only` 只有 1920 一张，缺 1280。第 2 轮 N9 我也漏看了。

## 5. 复审第 4 轮的范围与要求

1. 修复 R6、R7。n1–n7 能一起修就修，不修的在 handoff 中说明。
2. 测试：
   - R6：两种宽度下归档冲突的错误码与“刷新预检”`toBeInViewport()`；提交对话框的同类断言；
   - R7：1280 下三个审核对话框的影响说明不溢出；
   - 探针：去掉 R6、R7 的修复后，上述断言应失败（结果写进 handoff）。
3. 在 05 的已提交 detached worktree 上完整运行 runner（`--e2e --screenshots`）一次。上传包校验脚本的输入没有变化时，本轮可以不跑；04 取证时照常运行。
4. 重拍 `archive-audit-conflict-*`、`review-reject-dialog-*`、`review-withdraw-dialog-*`、`review-version-conflict-*`，以及改动涉及的其他截图。
5. 第 4 轮范围为 `01a232c40b..<新 handoff 提交>`，只核对 R6、R7 及改动到的部分；通过后在 04 取证一次，包括 runner 与上传包校验脚本。

## 6. 本轮在节点上留下的内容

- **开发主机：**
  - 只读 worktree `/home/dev/gdds-fe-rereview3-fe2c-01a232c4`；
  - bundle `/home/dev/gdds-test-tmp/src-rereview3-fe2c-01a232c4.bundle`。
- **05：**
  - worktree `/home/dev/gdds-fe-rereview3-fe2c-01a232c4-05`；
  - bundle `/home/dev/gdds-test-tmp/src-rereview3-fe2c-01a232c4.bundle`；
  - 上传包输出 `/home/dev/gdds-test-tmp/fe2c-rereview3-upload-validation/`；
  - 探针脚本 `/home/dev/gdds-test-tmp/fe2c-rereview3-probe*.sh`、`fe2c-rereview3-probe2-edit.py`；
  - 日志与探针结果 `/home/dev/gdds-fe-logs/fe2c/rereview-3/`；
  - 截图 `/home/dev/gdds-fe-evidence/fe2c/rereview3-01a232c4-05/`。

  探针 worktree 已删除。FE2c 退出合入后，与第 1、2 轮的内容一起清理。

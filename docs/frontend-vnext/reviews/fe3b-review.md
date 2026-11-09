# FE3b 审核报告

- **审核对象：** 分支 `fe-vnext`。
  - 代码候选 `5a0cdbad9c662658be3822ad96940f7ca7221283`，`frontend/` 树 `8764289b6b`；
  - handoff 提交 `afd7711e4b`（只新增 `docs/frontend-vnext/fe3b-handoff.md`，`frontend/` 树相同）。
- **范围：** `fe-fe3a-exit..afd7711e4b`（`fe-fe3a-exit` = `0e7caf66f4`）。合并提交 `db466112e0` 带入的 main `748de5034d` 中，只有 `55d56efb6e`（`frontend/scripts/run-tests.sh`）在前端审核范围内。
- **依据：** [FE3 kickoff](../fe3-kickoff.md)（main `885f5c4b64`）§2.3、§3.2、§4.7、§5、§6、§9、§13.4；FE2 kickoff §7.5；前端 kickoff §7.1、FD4；AGENTS“前端测试（FD7）”。
- **日期：** 2026-11-08。
- **结论：定向修复。** 不需要大范围重写（§6）。
  - 已做到：路径核对通过；快照与运行时、后端原件逐字节一致；tar/PAX 接收修复与同字节互通实现干净、符合 §5.5；kickoff 规定的 4 个探针全部按预期失败（摘要探针需加跳一条单测才到达 e2e）；
    真实 backend 旅程（18 个独立 scope）覆盖扎实，R10 四项都在真实 backend 上；05、07 上我的独立运行都通过（§2）。
  - 需要修复：上传步骤卡的“上传并生成预览”没有接入占用禁用（B1）；§6.1 的“先重新读取一次工作区”没有实现（B2）；
    提交续做在操作结束后用的是页面加载时的旧状态，禁用原因与提示不一致、`abort_code` 丢失，模拟数据用不可达状态掩盖了这一点（B3）；
    工作台与 Preview 页的占用判定是两套不同的规则（B4）；bundle 路由的错误码没有文案与用例（B5）；上传包后端校验脚本在当前 main 上已不能运行（B6）；
    模拟数据可达性断言、若干必测断言缺失，handoff 有多处与实际不符（B7–B9）。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| `git rev-parse afd7711e4b:vnext` 与 `748de5034d:vnext` | 都是 `56720104af34a1eb677336f57bdbc07444a56615` |
| `git diff --name-only 748de5034d afd7711e4b` | 只含 `frontend/`（44 个文件）与 `docs/frontend-vnext/fe3b-handoff.md` |
| kickoff 确认提交 `885f5c4b64` 是否在 main 上 | 是（FE3b 按约定不合入，路径核对以 `748de5034d` 为准） |
| `55d56efb6e` | 只改 `run-tests.sh`，加 `GATEWAY_FE_TEST_WORKERS` 的正整数校验与传参；07 上我的运行用它设为 2，正常 |

| 内容 | 主要文件 |
| --- | --- |
| 快照、类型与清理 | `openapi.json`、`generated/openapi.d.ts`、`client.ts`、`workspace.ts`、`ComparisonPage.tsx`、`mock-data.ts`、`journeys.ts`、`ArchiveMainlineDialog.tsx`、`check-production-build.mjs` |
| tar/OPFS | `posix-tar.ts`、`local-bundle.ts`、`interop-fixture.test.ts`、`e2e/bundle-interop.spec.ts`、fixture 目录 `be-d-0ba45e5ef8/` |
| 撤回、占用、续做 | `upload-header.ts`（新）、`ComparisonPage.tsx`、`WorkbenchPage.tsx`、`SubmitDialog.tsx`、`OperationStatusPanel.tsx`、`ReviewActions.tsx`、`e2e/upload-mode.spec.ts`（新）、`e2e/workspace-shell.spec.ts` |
| 终局处置显示 | `workspace.ts`、`WorkbenchPage.tsx`、`ReviewActions.tsx`、`ComparisonPage.tsx` |
| 真实旅程 | `run-real-backend-e2e.sh`、`e2e-real/journeys.spec.ts`（新）、`e2e-real/lib/*`、`e2e-real/smoke.spec.ts`、`playwright.real.config.ts` |
| N1 | `e2e/tsconfig.json`、`e2e-real/tsconfig.json`、根 `tsconfig.json` |

## 2. 证据、独立运行与探针

### 2.1 handoff 中的证据

- fixture 与 `SHA256SUMS` 已重新核对（§3.2）。
- 07、05 的日志只抽查了最终候选两份（mock 全量 `30ce43fc…4031`、journeys `c143a13d…0aca`），与 handoff 一致；其余逐轮记录未逐一核对，不影响结论。
- 上传包校验：见 B6。

### 2.2 我的独立运行

源码以 git bundle（SHA256 `e38204a5…be5f`）传入两节点共享仓库的 `refs/review/fe3b/*`，在 detached worktree `/home/dev/gdds-fe-review-fe3b-<名称>` 上运行，运行前后都 clean，起止 HEAD 相同。日志目录两节点都是 `/home/dev/gdds-fe-logs/fe3b/review/`。

| 节点 | 运行 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 07 | `run-tests.sh --e2e --screenshots`（`afd7711e4b`，`GATEWAY_FE_TEST_WORKERS=2`），12:19:13–12:21:25Z | exit 0；32 个单测文件 161 项、47 个 Playwright 通过；截图 134 张，目录 `/home/dev/gdds-fe-shots/fe3b-review-afd7711e4b` | `de972979…5999`（`candidate/frontend-tests-20261108T121932Z.log`） |
| 05 | `--suite journeys --subphase fe3b --session fe3b-review`（`afd7711e4b`），12:19:13–12:24:23Z | exit 0；18 passed；`openapi_compare=match`；`cleanup_status=ok`；日志中无 token；结束后无占用标记、无容器 | `6207bbd3…3a50` |

### 2.3 探针（一次性提交，只在节点上）

| 探针 | 提交 | 节点 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- |
| A：删去撤回的 403 分支（同时跳过对应单测，使 e2e 能运行） | `c171893afe` | 07 | W3 失败 | 符合：只有 W3 失败（46 passed、1 failed） | `a5e2ed3b…55a0` |
| B：PAX 改回整体解码后按字符切片 | `1b85bed619` | 07 | 互通单测失败 | 符合：`interop-fixture.test.ts` 4 项失败（同字节安装、两层解码、成员层拒绝、切分层拒绝） | `6aab218c…8f87` |
| C：摘要不符仍提交安装（跳过一条摘要单测） | `826747ca6f` | 07 | 负例 e2e 失败 | 被另一条单测（“drops a bad local copy…”）先拦下，e2e 未运行。单测层有效 | `a3b48151…bbb4` |
| C2：在 C 上再跳过该单测 | `7bd39da7e0` | 07 | 负例 e2e 失败 | 符合：只有“parquet member byte is corrupted”失败 | `836c0b30…343d` |
| E：撤回改发工作区版本（`r7-withdraw` 中 review 版本为 0，工作区版本在上传、预览、提交后远大于 0） | `fa4c95cd15` | 05 | 真实 e2e 失败 | 符合：只有 `r7-withdraw` 失败（停在 Preview 页，未撤回），17 passed，清理正常 | `89ccc56e…fd7` |
| D：我写的演示用例（不改产品代码） | `834ceb50a8` | 07 | 见下 | 见下 | `8049c059…49f7` |

演示用例 D（预期在候选上失败，用来证实 §4 的缺陷）：

| 用例 | 结果 | 对应 |
| --- | --- | --- |
| a：待审核时步骤卡“上传并生成预览”应禁用 | 失败：按钮可用 | B1 |
| b：工作区读取过时后应重读并恢复 | **通过**，但原因是开发服务器的 StrictMode 双执行，见 B2 | B2 |
| c：续做中操作失败、工作区重读失败时，按钮原因不应仍是“提交正在执行” | 失败：“提交正在执行，完成后才能撤回”仍在 | B3 |
| d：可达序列下 ABORTED 应显示 `abort_code` | 失败：不显示 `IMPORT_REJECTED` | B3 |

探针与演示的 worktree、bundle 与 ref 在报告提交后清理（§7）。

## 3. 逐项核对（§13.4 重点）

### 3.1 快照与清理

| 项 | 结果 |
| --- | --- |
| 快照 | `frontend/openapi.json` SHA256 `e26d9e14…574a`；我在 05 的 journeys 运行中 `openapi_compare=match` |
| 退回修改 | `client.ts` 映射、`workspace.ts` 分支、`ComparisonPage.tsx` 的“需修改”都已删除；`REJECTED` 统一“已退回”，前端源码与用例中不再出现“已拒绝” |
| 201/202 | 变通已删除 |
| `archive_disposition` | 无残留、无双读 |
| action 映射 | `anomalyAction` 对 5 个 `subject_kind` 穷举，`default` 走 `never`，新增取值时类型检查失败 |
| 取值表 | `subject_kind` 6 值、`action` 7 值、`issue_code` 7 个业务码、blockers 加 `ARCHIVE_PENDING_REVIEW`，与后端一致 |
| 生产构建检查 | 模式已扩充；但模拟接口并没有新增身份（`DevIdentityControl.tsx` 仍是 4 个），扩充的 `upload-only`、`no-preview` 没有对应 token，无害 |
| 新错误码 | 见 B5 |
| 模拟数据可达性 | 见 B3、B7 |

### 3.2 tar（§5.5）

- fixture 9 个文件与开发主机 `/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/` 逐个 `cmp` 相同；`SHA256SUMS` 为 `662afdfc…10d9`，`sha256sum -c` 全部通过；`bundle.tar` 24,576 字节、`b08a310c…32a2`。
- `splitPaxRecords` 在字节上切分，长度含前缀，越界、缺换行、缺 `=` 都拒绝，切出后严格 UTF-8 解码；`parseMemberPaxHeader` 只接受 `path`/`size`，重复、空值、其他 key 都拒绝。两层分离清楚。
- `size`：只含 ASCII 数字、安全整数；覆盖 header size；与 closure `size_bytes`、剩余 `Content-Length` 比对在写 OPFS 之前。
- 预算：PAX payload 按 header 声明值在读取前检查；路径按 UTF-8 字节，PAX 路径在解码前检查，ustar name/prefix 拼出后同样检查。`PAX_LIMIT` 已删除。
- 新增两条防护：PAX 头后紧跟结束块、连续两个 PAX 头都拒绝。合理。
- 失败时 `transaction.abort()`；e2e 负例断言安装目录不存在、界面显示下载失败。未检查本次临时目录是否删净（handoff 写“无残留内容”），非阻塞。
- 这一部分的实现质量好，不需要改。

### 3.3 §6 撤回、占用、续做

| 检查 | 结果 |
| --- | --- |
| 不按 actor、指针推断可撤回 | 符合：只有 review 查询成功且 `PENDING` 才可用 |
| 撤回携带 `review_version` | 符合；探针 E 在真实 backend 上证实（§2.3） |
| 冲突后不自动重发 | 符合；模拟 W5 与真实 `r7-stale` 都断言只发 1 次 |
| 工作区被占用时“提交”“上传”禁用 | Preview 顶栏“提交”与工作台工具栏“上传”符合；**上传步骤卡不符合（B1）** |
| §6.1 各行文案 | 文案字符串与表一致；“先重新读取一次工作区”的三行没有实现（B2） |
| 续做失败按 §6.2 | 页面加载时读取失败的分支符合；**操作在页面上结束之后的分支不符合（B3）** |
| URL 中操作的类型按 `job_kind` | **没有实现**：产品代码不读 `job_kind`。提交续做改为“URL 的 operationId 等于指针 attempt 的 operation_id”，Preview 续做仍靠 `gateway-preview-operation` 标记。效果上大体可用，但与 §6.2 不同，handoff §4.1 写“`job_kind` 来自 GET /v1/operations/{id}”与代码不符（B8） |
| 删除 `sessionStorage` 提交标记 | 写、读、清全部删除；n3 两个用例改为指针驱动，但其中 ABORTED 用例的数据不可达（B3） |

### 3.4 §6.4 终局处置

- 组态树状态位、色调、处置优先于标记、“归档主线”禁用原因、`workspace.test.ts` 映射单测都符合。
- 与 §6.4 的差异（B9 一并修）：
  - 审核模式顶栏：处置标签已加，但“归档时选中了其他提交”“由 {closed_by} 于 {closed_at} 关闭”只放在标签的 `title` 里，表中要求的是“下方一行”，理由可展开；
  - 详情面板：关闭理由总是折叠在“展开理由”里，§6.4 要求全文显示、超过 3 行才折叠；另多了一行“终局状态”，与“审核状态”“终局处置”重复；
  - 有理由关闭的树节点状态位没有悬停提示“有理由关闭，详情见右侧面板”；
  - 关闭时间用 `toLocaleString("zh-CN")` 的完整格式（截图 `fe3b-d3-manual-close` 为“2026/11/6 08:00:00”），与组态树的“MM/DD HH:mm”不同；§6.4 要求与组态树相同的本地格式。

### 3.5 真实旅程（§4.7）

- 18 个 scope 各自独立仓库与身份；本人撤回用 `submitter`（含 `withdraw_own_submission`、无审核权限），仅上传用 `submitter-upload-only`，没有用审核人或全权限身份。
- R1–R7、R9（两节点）、R10 四项、R11 两类冲突都在真实 backend 上覆盖；R5 用 `route.fetch()` + `abort` 验证同一 key 回放 202、审核 200；R2 FULL 恰好两个比较对。
- 冒烟已删除下载失败判据，改为进入差异浏览后断言无未捕获错误。
- 小问题：`r7-upload-only` 中的注释说审核模式的 403 只显示通用标题，与 `ComparisonPage` 实际传入的“当前身份没有该操作的权限”及 `r10-noperm` 的断言矛盾；用例里抛错文本说脚本只给仅上传身份 `upload_submit_workspace`，也已过时。随修复删改。

## 4. 需要修复（阻塞）

### B1 上传步骤卡绕过占用禁用

- kickoff §6.1、§11 Q9：“工作台的‘上传’（工具栏与上传步骤卡）任一指针非空时同样禁用”。
- `WorkbenchPage.tsx` 只把占用原因并入工具栏动作（`effectiveActions`）；`UploadStepCard.tsx:331` 的“上传并生成预览”只看 `busy`，没有占用输入。待审核或已通过时，提交人在步骤卡上仍可直接上传，后果正是 §6.1 所说的 409 `WORKSPACE_OCCUPANCY_CONFLICT` 或归档后丢失上传内容。
- 演示用例 `review-demo a`（§2.3）证实：工具栏“上传”禁用时，步骤卡按钮仍可用。
- W8（模拟与真实）只断言工具栏按钮，所以没有发现。handoff §4.1“workbench 的上传（工具栏与步骤卡）同样禁用”与实际不符。
- **修复：** 步骤卡接受同一占用原因并禁用按钮（目录选择可保留）；W8 的模拟与真实用例都断言步骤卡按钮。

### B2 §6.1“先重新读取一次工作区”没有实现

- §6.1 表中 `submission_disposition` 非空、`REJECTED`、`WITHDRAWN` 三行，以及上传表的“工作区读取过时”行，都要求先重读一次工作区，指针已清空时恢复可用，仍过时才显示终局原因；§6.3 W10 的断言包括“重读后指针为空则恢复可用”。
- `upload-header.ts` 计算了 `reread: true`，但没有任何调用方读取它（全仓只在单测中出现）；页面直接显示“该提交已归档”等原因。
- 页面加载时只有一处读取工作区（`ComparisonPage.tsx:257` 的 effect），之后不会因 `reread` 再读。
- 演示用例 `review-demo b`（第一次读取过时、之后已清空）在 07 上**通过了**，原因是模拟 e2e 跑在 Vite 开发服务器上（`playwright.config.ts:13`），`React.StrictMode` 在开发模式下把该 effect 执行两次，碰巧产生第二次读取（用例断言读取次数 > 1 成立）。生产构建只执行一次，恢复不会发生。
  这也提醒：依赖“加载时读取次数”的模拟用例在开发服务器上会被 StrictMode 掩盖，修复后的 W10 用例应断言是页面按 `reread` 主动重读（例如第一次与第二次之间有可观察的状态，或在生产构建的 preview 下运行该用例）。
- 模拟 W10 只覆盖“重读仍过时”的一支。
- **修复：** 页面在得到 `reread` 时重读一次工作区（只一次，不循环），再按新状态派生；W10 补“重读后恢复”的一支。

### B3 提交续做结束后的状态不一致，模拟数据掩盖缺陷

`ComparisonPage.finishSubmitResume` 与 `WorkbenchPage.resumeSubmitFromOperation` 在操作到终态后重读工作区与 attempt，但：

1. **禁用原因与提示不一致：** 不更新页面里的 `operation`，也不在失败时设置 `workspaceProblem`/`attemptProblem`。操作结束后若工作区或 attempt 读取失败，提示显示“无法确认提交状态”，按钮仍按页面加载时的 `RUNNING` 显示“提交正在执行，完成后才能撤回/继续”。这正是 FE3a B7 与 Q14 要消除的“提示与禁用原因并存且矛盾”。演示用例 `review-demo c` 证实。
   同理，操作结束而 attempt 仍未结束时，提示是“需要管理员处理”，按钮仍是“提交正在执行”。
2. **`abort_code` 丢失：** 正常的 ABORTED 会清空两个指针，代码走到最后一支，取的是页面加载时缓存的 `attempt?.abort_code`（那时 attempt 还是 `PREPARED`，没有码）。§6.2 要求显示“提交未完成”与原始码。演示用例 `review-demo d`（加载时 `PREPARED`、结束后 `ABORTED` + `IMPORT_REJECTED`）证实不显示码。
   工作台一支直接写 `code: null`。
3. **模拟数据不可达：** n3 的“FE3a 提交续做时 ABORTED 后提交恢复可用”让 attempt 路由从一开始就返回 `ABORTED` + `IMPORT_REJECTED`，同时工作区指针非空、操作在运行，这是后端不会出现的组合（FE2 kickoff §7.5“只模拟后端可达的状态”）。用例正因为这一点读到了码而通过。
4. **虚构的 operation 状态：** `ae5705df56` 把 `ABORTED` 当作 operation 终态加进 `journeys.ts:69`、`OperationStatusPanel.tsx:44`、`upload-header.ts:72`。后端 `OperationStatus` 只有 `QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED/SUPERSEDED/MANUAL_RECOVERY_REQUIRED`（`operations/contracts.py:100`），`ABORTED` 是 attempt 的状态。`upload-header.ts` 的 `TERMINAL` 反而漏了 `CANCELLED`、`SUPERSEDED`：这两种终态加 attempt 未结束时会显示“提交正在执行”而不是“需要管理员处理”。后续用例已改用 `FAILED`，但产品代码中的虚构值没有删。

- **修复：** 操作到终态后，用已知的 attempt ID 重读 attempt（取 `abort_code`），同时更新页面的 operation/attempt/workspace 与各自的读取错误，让禁用原因只从同一份状态派生；删除 `ABORTED` 操作状态，`TERMINAL` 按后端枚举；n3 的 ABORTED 用例改为可达序列（加载时 `PREPARED`，结束后 `ABORTED` 且指针清空）；W6、W9 补下述断言。

### B4 工作台与 Preview 页的占用判定是两套规则

- `upload-header.ts` 的 `deriveUploadModeGates` 只被 `ComparisonPage` 使用；`WorkbenchPage.tsx:466-484` 另写了一份 `uploadOccupancy`，规则不同：
  - 只看 attempt 状态，不读 operation：`MANUAL_RECOVERY_REQUIRED`、或操作已终态而 attempt 为 `PREPARED` 时显示“提交正在执行”，§6.1 要求“提交结果待确认，需要管理员处理”；
  - 加载中显示“正在读取…”，而 Preview 页在首次读取工作区之前显示“无法确认提交状态”并给出“重试读取”（`input.workspace` 为 null 即判为读不到；`attemptLoading`/`operationLoading` 传入了但模块没有使用）。
- 单测覆盖的是模块，工作台的行为没有单测。
- **修复：** 两页共用一个读取工作区/attempt/operation/review 并派生 gates 的 hook（见 §6），工作台删除自己的规则；模块区分“加载中”与“读不到”。

### B5 bundle 路由与 review 查询的新错误码没有文案和用例

- §5.3“bundle 错误码”：两个 bundle 路由在 OpenAPI 中列出的错误码（Preview bundle 503 `BUNDLE_INTEGRITY_FAILURE`；History bundle 404 `ARTIFACT_UNAVAILABLE`、503 `BUNDLE_INTEGRITY_FAILURE`）要有前端文案并加入取值核对；“新权限与错误”要求错误码单测覆盖 review 查询的 403/404 等。
- 现状：两个码在 `src/`、`e2e/` 中都不存在；`bundleLoadErrorCode` 把服务器返回的任何错误都映射成 `BUNDLE_LOAD_FAILED`，服务器的原始码不显示（C6 要求可见、可复制）。`client.test.ts`、`mock-data.test.ts` 没有为新码增加用例。handoff §2.2 没有提到这一项。
- **修复：** 按 §5.3 补文案、取值表与单测；`ApiError` 的服务器码原样带到错误状态。

### B6 上传包后端校验脚本在当前 main 上不能运行

- `validate-upload-package.sh` 用依赖基础镜像的 `/build/backend/.venv` 加源码 `PYTHONPATH` 运行后端校验。合入 `748de5034d` 后后端导入 `gateway_compute`（Rust 扩展），依赖基础镜像里没有，脚本在 05 以 `ModuleNotFoundError` 失败（handoff §8.3）。
- 实施方在 05 手工构建了包装镜像 `fe3b-upload-validator:latest` 才跑通。这个镜像不在仓库里，04 无法按 clean worktree 的权威入口复现；kickoff §3.2 把这项校验列为 FE3b 在 04 上的退出条件。
- 这是前端脚本随后端变化需要跟进的缺陷，不是 owner 认可一次手工步骤就能解决的：每次取证都要重复。
- **修复：** 脚本自己得到含本地包与扩展的后端环境（例如用当前 HEAD 的 backend 镜像，在本机 `GATEWAY_DOCKER_BUILD_NETWORK=none` 构建，venv 路径 `/app/backend/.venv`），并在日志中记录该镜像的 config digest 与全部 DiffID；依赖输入核对照旧。若实施方认为应改由后端提供镜像，**交设计会话**决定。

### B7 模拟数据的可达性断言缺失

- §5.3 要求在模拟数据单测中断言处置组合（只在 `APPROVED` 的 `SUBMISSION` 上；`ARCHIVED_BASELINE` ⇒ `ARCHIVE` + `result_id` + 无 `closure` + 有对应的 `ARCHIVED_SUBMISSION` 基线；两种关闭的组合；无 `ARCHIVED_BASELINE + MANUAL_CLOSE`；Review 与 History 一致；已处置的提交不是 `active_submission_id`），并把 D5 列为唯一允许的例外。
- 现状：`mock-data.test.ts` 只加了“`eligibility_note` 只在 `APPROVED`”一条。处置数据都写在 `upload-mode.spec.ts` 里，不经任何断言，其中：
  - `d4` 是 `ARCHIVED_BASELINE` 但没有 `promoted_baseline_node_id`；
  - `d-arch` 与 `d4` 都是 `ARCHIVED_BASELINE`，且来自同一个 `archive-result-1`：一次归档只会产生一个归档基线；
  - `d5`（D5 防御性数据）没有标注。
- handoff §2.4 把这些规则写成“模拟数据规则”，但没有单测保证。
- **修复：** 处置场景数据放进 `mock-data.ts`（或可被单测读取的模块），按 §5.3 逐条断言，D5 单列例外；改正 `d4` 等不可达数据。

### B8 必测断言缺失

| 场景 | kickoff 要求 | 现状 |
| --- | --- | --- |
| W6 | 撤回、提交、上传禁用；刷新后找回操作卡片；操作终态而 attempt 未结束时显示“需要管理员处理” | 只断言 `RUNNING` 时的禁用，后两项没有 |
| W9 | ①②③三支，点“重试”后恢复读取 | 只在页面加载时读取失败，断言“重试读取”按钮可见，没有点击；操作结束后的分支没有（B3） |
| W10 | 重读后恢复、重读仍过时两支 | 只有后者（B2） |
| D1 | 审核模式顶栏两个标签与禁用原因 | 没有打开审核模式，审核顶栏的处置显示没有任何用例 |
| D2 | 详情与顶栏写“归档时选中了其他提交” | 只断言详情 |
| D3 | 关闭人、时间、理由完整；多行折叠与展开；父基线仍是 head 时归档主线禁用 | 只断言“关闭人”“关闭理由”标签与 actor，时间、折叠展开、主线禁用都没有 |
| `job_kind` | §6.2 按 `job_kind` 判断 URL 中操作类型 | 未实现（§3.3），按 §6.2 实现并加用例；或在 handoff 写明偏差交设计会话 |

### B9 handoff 与实际不符

随修复改正（不要求改已提交的 handoff 提交，新 handoff 写正确即可）：

- §4.1：步骤卡已禁用（B1）、`job_kind` 来自 operation（B8）；
- §5 表：D1“审核标签”、D3“多行原因折叠展开”有用例（B8）；
- §2.4：“处置只出现在…”等规则有单测保证（B7）；
- §7 N1：“strict 在 mock 重的 spec 中关闭”，实际是 `e2e/` 与 `e2e-real/` 两个工程整体 `strict: false`，且 `e2e/tsconfig.json` 再次编译 `../src/**/*.ts`。建议只在确有需要的文件上放宽，或在 handoff 如实写明；
- §9 第 4 项引用的“§4.6”在 handoff 中不存在；
- §3.3 的 §6.4 处置显示差异（§3.4 所列）应在修复后的 handoff 中逐条说明。

## 5. 非阻塞

- **N1** RS 镜像的完整 DiffID 未记录（handoff §9 第 2 项）：04 取证运行时由日志补齐即可；建议脚本在构建 RS 镜像后把 DiffID 写入日志，不依赖人工。
- **N2** `ArchiveMainlineDialog` 对预检 403 用“当前身份没有预检归档方案的权限”，与 R10 统一文案不同；候选查询（R10 ④）已用统一文案，可保留，handoff 注明。
- **N3** 首次读取工作区之前，Preview 页撤回与提交短暂显示“无法确认提交状态”与“重试读取”（B4 一并修）。
- **N4** 截图 `fe3b-w8-upload-disabled`：工作区有待审核提交、“上传”已禁用，工作区节点的状态位仍是“可提交”。kickoff 没有规定被占用时工作区节点的状态位，这里只提出，**交 owner 看图时确认**是否改为与占用一致的说明（例如“待审核占用”）。
- **N5** 07 上我的截图与实施方最终运行的 134 张中 116 张逐字节相同，其余 18 张（如 `fe3b-w6-*`、`fe3b-withdraw-unknown`）的差异属于悬停、计时等动态内容，抽查无布局差异。

## 6. 代码实现质量与是否需要重写

**结论：不需要大范围重写。** 问题集中在“上传模式状态”的编排一处，其余部分质量良好。

| 部分 | 评价 |
| --- | --- |
| tar/PAX（`posix-tar.ts`） | 好。改动聚焦，两层解析职责清楚，预算与 size 检查都在分配、写入之前，注释准确；单测与 e2e 用后端原件，探针证明有效 |
| 契约同步（快照、类型、取值表、action 映射） | 好。穷举映射用 `never` 守住新增取值；直接改字段，没有兼容层 |
| `upload-header.ts` | 思路对：纯函数、按 §6.1 顺序、有单测。缺点是只接了一半：`reread` 与两个 loading 字段无人使用，工作台另写一套（B2、B4） |
| `ComparisonPage.tsx`、`WorkbenchPage.tsx` | 主要问题所在。FE3b 在 `ComparisonPage` 新增 14 个 `useState`（33 → 47），工作区、attempt、operation、review 的读取与续做、撤回逻辑都写在页面里，彼此独立更新，导致 B3 的旧状态问题；两页各自实现占用判定（B4）。另外两页各有 40、18 行超过 300 字符（最长约 2,000 字符）的 JSX，这是既有风格，FE3b 加重了它，审阅困难 |
| 模拟 e2e | 覆盖面够，但断言偏浅（B8），且有不可达数据掩盖缺陷（B3、B7） |
| 真实旅程（`journeys.spec.ts`、脚本） | 好。每 scope 独立、身份权限精确、断言直接核对后端状态与请求次数；本阶段最有价值的部分 |

**建议的重构范围（随 B2–B4 一起做，属定向修复）：**

- 抽出一个 `useUploadModeState`（名称自定）hook：负责读取工作区 → review / attempt → operation、续做结束后的重读、一次性重读（B2）、各自的读取状态，输出 `deriveUploadModeGates` 的结果；`ComparisonPage` 与 `WorkbenchPage` 都只消费它。
- `deriveUploadModeGates` 区分“加载中”与“读不到”，增加工作台需要的上传步骤卡输出（B1）。
- 页面中与本阶段相关的超长 JSX 行（Preview 顶栏、详情面板）顺手拆成小组件即可，不要求整体改写既有页面。

预计改动集中在 `upload-header.ts`、新 hook、两页面的相关段落、`UploadStepCard.tsx` 与对应用例，规模与 FE3b 已有的 §6 改动相当或更小。

## 7. 下一步

1. 实施会话按 B1–B9 修复，提交新的代码候选与 handoff。
2. 复审第 1 轮范围 `afd7711e4b..<新 handoff>`：核对修复；在 07 重跑 `run-tests.sh --e2e --screenshots`（演示用例 a–d 的场景应由正式用例覆盖并通过），在 05 重跑 `--suite journeys` 与上传包校验（B6 修复后的脚本）。
3. 复审通过后，04 取证（kickoff §9 FE3b 行）：在 clean detached worktree 上运行
   - `run-tests.sh --e2e --screenshots`（含 §5.5 互通用例）；
   - `validate-upload-package.sh`（修复后的脚本，日志含后端环境镜像身份）；
   - `run-real-backend-e2e.sh --suite journeys --subphase fe3b`（日志含 RS 完整 DiffID）。
4. 审核会话的遗留：探针 worktree、`refs/review/fe3b/probe-*` 与传输用 bundle 已删除；保留开发主机 `/home/dev/gdds-fe-review-fe3b-afd7711e` 与 05、07 的 `/home/dev/gdds-fe-review-fe3b-candidate`（复审对照用）、两节点 `/home/dev/gdds-fe-logs/fe3b/review/` 日志与 07 截图，FE3b 退出后清理。
5. 证据核对后由 owner 确认 §6、§6.4 截图，再决定 FE3b 退出（FE3 在 FE3c 结束时退出）。§5.5 的修复提交、同文件 SHA256 与 04 证据由 owner 回传后端。

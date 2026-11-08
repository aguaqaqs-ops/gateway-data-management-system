# FE3b 复审第 1 轮

- **审核对象：** 分支 `fe-vnext`，范围 `afd7711e4b..4e0d074179`。
  - 代码候选 `403e2faefc8603cec43f376a60a22a02c3360057`，`frontend/` 树 `4d5a835614`；
  - handoff 提交 `4e0d074179`（只新增 `docs/frontend-vnext/fe3b-handoff-fix1.md`，`frontend/` 树相同）。
- **依据：** [FE3b 审核报告](fe3b-review.md)（`704509b6b3`）§3–§6；[FE3 kickoff](../fe3-kickoff.md)（main `885f5c4b64`）§4.7、§5.3、§5.5、§6.1–§6.4、§9、§10、§13.4；FE2 kickoff §7.5；新 handoff。
- **日期：** 2026-11-08。
- **结论：定向修复。** 不需要重写。
  - 已做到：
    - 路径核对通过；
    - B1、B5、B6 完整修复，B2 的“重读后恢复”不依赖 StrictMode；
    - 共用 hook 让两页的占用规则来自同一处，页面明显变简单；
    - 我在 07、05 的三项独立运行都通过；
    - 规定的 5 个探针中 4 个按预期失败。
  - 需要修复（§4）：
    - F1：续做提示与按钮禁用原因仍会并存且矛盾。探针“撤掉续做后的状态更新”没有任何用例失败；
    - F2：attempt 已结束但指针未清时，“提交”“上传”被解锁；
    - F3：review 查询 404 也触发了一次性重读；
    - F4：模拟数据的可达性断言只覆盖新场景数组，D1–D5 的树数据仍不可达，D5 形态的数据出现在共用 fixture 中；
    - F5：审核模式顶栏没有截图，D3 顶栏没有用例，W6 的“刷新后找回”没有走指针路径；
    - F6：handoff 有几处与实际不符。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| `git rev-parse 403e2faefc:vnext`、`4e0d074179:vnext` | 都是 `56720104af34a1eb677336f57bdbc07444a56615` |
| `git diff --name-only 748de5034d 403e2faefc` | 只含 `frontend/` 与 `docs/frontend-vnext/` |
| `git diff --name-only 403e2faefc 4e0d074179` | 只有 `docs/frontend-vnext/fe3b-handoff-fix1.md` |
| `git log --merges afd7711e4b..4e0d074179` | 无合入 |
| 提交序列 | `087281ce65`、`df3e8c5abd`、`069a8f65a5`、`fa507ee77c`、`403e2faefc`、`4e0d074179`，与 handoff §5 一致 |

本轮改动（`afd7711e4b..403e2faefc`，19 个文件，+1396/−274）：

| 内容 | 主要文件 |
| --- | --- |
| 新 hook | `use-upload-mode.ts`（新） |
| gates 与单测 | `upload-header.ts`、`upload-header.test.ts` |
| 两个页面 | `ComparisonPage.tsx`、`WorkbenchPage.tsx` |
| 步骤卡 | `UploadStepCard.tsx` |
| 处置显示 | `disposition-display.tsx`（新） |
| bundle 文案 | `local-bundle.ts` |
| 模拟数据与单测 | `mock-data.ts`、`mock-data.test.ts` |
| 模拟 e2e | `upload-mode.spec.ts`、`workspace-shell.spec.ts` |
| 真实旅程 | `journeys.spec.ts`、`e2e-real/lib/ui.ts` |
| 脚本 | `run-real-backend-e2e.sh`、`validate-upload-package.sh` |
| 删除 operation `ABORTED` | `OperationStatusPanel.tsx`、`journeys.ts` |

## 2. 独立运行与探针

源码以 git bundle（SHA256 `db9b81f25b47cae9…`，`afd7711e4b..4e0d074179`）传入两节点的 `refs/review/fe3b-rr1/candidate`，在 detached worktree `/home/dev/gdds-fe-rereview1-fe3b` 上运行。运行前后都 clean，起止 HEAD 都是 `4e0d074179`。日志目录两节点都是 `/home/dev/gdds-fe-logs/fe3b/rereview-1/`。两节点运行前都没有占用标记，结束后无标记、无残留容器。

### 2.1 独立运行

| 节点 | 运行 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 07（`gw-dms-07`） | `run-tests.sh --e2e --screenshots`，`GATEWAY_FE_TEST_WORKERS=2`，14:38:55–14:41:14Z | exit 0：单测 32 个文件 171 项，Playwright 55 项；截图 138 张，目录 `/home/dev/gdds-fe-shots/fe3b-rereview1-4e0d0741`；工具链 config digest `sha256:a0d7b2b4…a1017`，npm 缓存归档 `0d861824…0089f4` | `d058702d4e9d0848bf18146f4f34f77eab1921ecbd3eef3f99c79ce81bb286cc` |
| 05（`gw-dms-test-05`） | `run-real-backend-e2e.sh --suite journeys --subphase fe3b --session fe3b-rereview-1`，14:43:26–14:48:44Z | exit 0：18 passed；`openapi_compare=match`；`cleanup_status=ok`；日志中没有 token；RS config digest `sha256:25b080df…5d97`，`rs_image_rootfs_diff_ids` 完整记录（N1 已修） | `48c4af8fdfe6f96f6868b37237f1e1bb95f4c3cffa396ac8349e12a9c9665f32` |
| 05 | `validate-upload-package.sh`（修复后），14:54:50–14:55:47Z | exit 0（见下） | `2275e1c497600c1fa2b20234bc4fef4792829eced3b4a243dd08672876445691` |

上传包校验（05）的结果：

- `required_inputs_match=true`；`RESULT packages=4 failures=0`；`missing-dbcfg` 被 `UPLOAD_CLOSURE_INVALID` 拒绝。
- 4 个包的 SHA256 与 handoff §8.3 相同。
- 校验镜像由脚本自行构建，config digest `sha256:99f72527…a00c58fca4` 与实施方的运行相同，可复现。全部 DiffID 已记录，运行后 tag 已删除。

05 第一次启动 journeys 时，我把 npm 缓存路径设错了：05 的缓存在 `/home/dev/gdds-fe-cache/fe0/`，脚本默认是 `frontend/`。脚本在预检阶段以 exit 2 退出，没有接触被测对象，清理正常；日志 `journeys-wrapper-attempt1-npm-cache-path.log`。改正两个缓存变量后重新运行，结果见上表。归档 SHA 与 07 相同。

### 2.2 探针（已提交的一次性 worktree，只在节点上）

| 探针 | 提交 | 节点 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- |
| P1：步骤卡不接收占用原因 | `9825585b14` | 07 | W8 失败 | **符合**：只有 W8 失败（步骤卡按钮可用），54 passed | `e1bb2804…ef0d` |
| P2：去掉一次性重读 | `03311b9625` | 07 | W10“重读后恢复”失败 | **符合**：只有该用例失败（上传保持禁用），54 passed | `3b3e0640…82ed` |
| P3：续做后不更新 hook 的 attempt/operation 状态（`readAttemptChain` 改为不写状态的直接读取） | `de698aa383` | 07 | W9 或 ABORTED 用例失败 | **不符合：55 项全部通过**，见 F1 | `6f73896d…6aa6be` |
| P4：bundle 服务器码改回一律 `BUNDLE_LOAD_FAILED`（保留原有的 `SCOPE_FORBIDDEN` 特判） | `a374c83512` | 07 | 对应用例失败 | **符合**：只有“bundle 接口失败显示可重试错误页”失败 | `a19b452d…bd21` |
| E：撤回改发工作区 `optimistic_version` | `f73b7b4a45` | 05 | `r7-withdraw` 失败 | **符合**：只有 `r7-withdraw` 失败（停在 Preview 页），17 passed，清理正常 | `3a0483c4…4e6c` |
| B7a：在 `DISPOSITION_SCENARIO_NODES` 加一条 `ARCHIVED_BASELINE` + `MANUAL_CLOSE` | `fc0e380522` | 07 | 单测失败 | **符合**：`keeps every disposition scenario…` 失败 | `e4324f23…a98c` |

P1–P4、E 都没有被前面的单测阶段拦下，不需要跳过单测重跑。

我另写了两组演示提交（只加用例，不改产品代码），用来证实 §4 的问题：

| 演示 | 提交 | 断言 | 结果 | 对应 |
| --- | --- | --- | --- | --- |
| a：W9②、W9③点“重试”后，“无法确认提交状态”不应仍在 | `e3a98dad2b` | `toHaveCount(0)` | **两条都失败**：按钮原因已是“提交结果待确认，需要管理员处理”，提示仍是“无法确认提交状态” | F1 |
| c1、c2：工作台与 Preview 页的 URL 中没有操作 ID，只有 attempt 指针 | 同上 | 写入 URL 并显示操作卡片 | 通过（产品行为正确，只缺正式用例） | F5 |
| d403、d404：review 查询 403/404 后的工作区读取次数应为 1 | 同上 | `workspaceReads == 1` | 403 通过（1 次）；**404 失败（2 次）** | F3 |
| b：工作区只有 attempt 指针、attempt 为 `FINALIZED`，“上传”“提交”应禁用 | `029522eeed` | `enabled == false` | **失败**：两者都可用 | F2 |
| e：在共用 fixture `HISTORY_PAGE_TWO` 的 `fe2a-history-ref-old` 上加 `ARCHIVED_BASELINE` + `MANUAL_CLOSE` | 同上 | 可达性单测应失败 | **`mock-data.test.ts` 11 项全部通过**。只有 `workspace.test.ts` 的两条显示断言因显示变化失败，与可达性无关 | F4 |

演示 a 日志 `7ed6482c…0666`，演示 b/e 日志 `917fe261…044d`。

各探针的 diff 存于 `probes/probe-*.diff`（07）与 `probe-e.diff`（05）。探针 worktree、`refs/review/fe3b-rr1/probe-*` 与传输用 bundle 已删除。

## 3. 逐项核对

### B1 步骤卡占用禁用：符合

- `UploadStepCard` 接收 `occupancyReason`，只禁用“上传并生成预览”，目录选择不受影响。原因与工具栏同源（`gates.upload`）。
- 模拟 W8 断言了步骤卡按钮、原因与目录选择。真实 `r4-submit`、`r7-withdraw`（W8 段与撤回后恢复）、`r7-approved` 断言了步骤卡。P1 证实了覆盖。

### B2 一次性重读：恢复一支符合；触发范围多了 404（F3）

| 检查 | 结果 |
| --- | --- |
| 只读一次、不循环 | 符合。`rereadKey` 固定过时内容，`rereadConsumed` 保证同一内容只重读一次 |
| 重读后指针清空即恢复，仍过时才显示终局原因 | 符合（W10 两支） |
| “重读后恢复”不依赖 StrictMode | 符合。hook 对挂载读取做了在途去重，用例断言恰好 2 次读取；P2 去掉重读后该用例失败。如果 2 次读取来自 StrictMode 双执行，P2 会通过 |
| 只在 §6.1 的四种情形触发 | **不符合**：`submissionGate` 对撤回 404 也返回 `reread: true`。这是 FE3b 初版遗留的标志，以前没有调用方，现在被 hook 消费；演示 d404 证实多读一次（F3） |
| 覆盖 | W10 恢复一支只在工作台验证重读，handoff 说的“Preview 页也覆盖”不成立：用例后半段打开 Preview 时工作区已经是干净的（F6）。hook 共用，功能上不缺 |

### B3 续做后状态一致：部分符合（F1）

| 检查 | 结果 |
| --- | --- |
| 续做结束后用已知 attempt ID 重读，`abort_code` 来自重读结果 | 符合（`attemptIdRef` 跨越指针清空，n3/W9①断言 `IMPORT_REJECTED`） |
| 禁用原因与提示同源 | **不符合**。提示（`resumeMessage`/`submitResumeMessage`）仍是页面里的独立状态，只在续做结束时写一次。“重试”只刷新 hook，不重新派生提示，于是出现“提示：无法确认提交状态”与“按钮：提交结果待确认，需要管理员处理”并存（演示 a）。另外，指针已清空而 attempt 读不到时，页面提示“无法确认提交状态”，按钮却可用；§6.2 第 2 步对这种情况要求保留“无法读取提交结果，请刷新后重试” |
| 用例能否发现 | **不能**。P3 去掉续做后的 hook 状态更新，55 项全过：W9②③用 `getByText("无法确认提交状态").first()`，提示里的同一句话就能满足，没有断言按钮自己的禁用原因 |
| 产品代码中没有 operation `ABORTED`，终态与后端一致 | 符合。`TERMINAL` 为 `SUCCEEDED/FAILED/CANCELLED/SUPERSEDED`，`MANUAL_RECOVERY_REQUIRED` 单独处理；`OperationStatusPanel`、`pollOperation` 已删除 `ABORTED`；模拟取值表与 `operations/contracts.py:100` 的 7 个值一致 |
| n3 的 ABORTED 数据可达 | 符合：加载时 `PREPARED` + `RUNNING`，结束后 `ABORTED` + `IMPORT_REJECTED`，两个指针清空 |
| 演示 c、d 成为正式用例 | 符合：c → W9③，d → n3/W9① |

### B4 两页共用 hook：符合，但有一处规则缺陷（F2）

- **共用：** 两页只消费 `useUploadModeState` 与 `deriveUploadModeGates`。工作台的 `uploadOccupancy`、`activeReview`、`attemptState` 等已删除，页面中没有残留的占用文案（全仓 grep）。
- **加载与读不到：** 模块区分了“加载中”与“读不到”。“attempt 已知、操作读取中”保持“提交正在执行”，单测覆盖。
- **单测：** 覆盖了 `MANUAL_RECOVERY_REQUIRED`、`CANCELLED`、`SUPERSEDED` 加 attempt 未结束。
- **缺陷（F2）：** 新增的 `ATTEMPT_CLOSED → "none"` 让“只有 attempt 指针、attempt 已 `FINALIZED`/`ABORTED`”的快照直接解锁“上传”“提交”（演示 b）。这个快照只在读取竞争中出现（读工作区之后、读 attempt 之前提交完成或被恢复流程收尾），出现时说明工作区读取过时。§6.2 明确“不在指针未清时解锁”，应按过时处理：重读一次，期间保持禁用。
  - 对应单测“judges by the submission pointer when the attempt is already closed”用的是两个指针同时非空的工作区，不可达（§5.3“两者至多一个非空”），所以没有发现这一点。
- **重构质量：**
  - 好的方面：
    - 读取、续做重读、一次性重读集中在 hook；
    - `ComparisonPage` 删去 11 个 `useState`，工作台删去 4 个及一套规则；
    - Preview 顶栏动作与详情面板拆成 `PreviewHeaderActions`、`DispositionDetails`，审阅明显容易；
    - 失败的重读保留最后一份快照、只记录问题，避免页面闪成错误页，这个取舍合理。
  - 不足：
    - 续做提示仍留在两个页面里，没有从 hook 的同一份快照派生，这正是 F1 的来源。建议由 hook 输出续做结果（或提示），页面只渲染；
    - 两页各自实现“指针写入 URL”（一个经 runtime、一个用 `replaceState`），可以接受；
    - `resumeAfterOperation(finishedOperationId)` 的参数未使用（`void finishedOperationId`），可删除。

### B5 bundle 与 review 错误码：符合

- OpenAPI 中两个 bundle 路由列出的码都有文案：401 `AUTHENTICATION_REQUIRED`、403 `SCOPE_FORBIDDEN`、404 `RESOURCE_NOT_FOUND`/`ARTIFACT_UNAVAILABLE`、503 `SERVICE_NOT_READY`/`BUNDLE_INTEGRITY_FAILURE`。单测解析快照逐码断言有文案，且 §5.3 的码有模拟场景。
- 服务器码原样显示：Preview 进 `ErrorState` 的 code（可复制）；History 抽屉在消息中带 `code：`。P4 证实有用例覆盖。
- review 查询 403/404、review-events `ARCHIVE_CLOSED` 已加入模拟错误响应并有单测。

### B6 上传包校验脚本：符合

- 脚本在 clean worktree 上自建校验镜像：`--network=none`，依赖基础镜像经 `--print-input` 核对 tag，venv 为 `/app/backend/.venv`。tag 已存在时拒绝复用，结束后删除。
- 日志含依赖镜像与校验镜像的 config digest 与全部 DiffID；依赖输入核对保留，输入表新增 `vnext/backend/Dockerfile`。
- 05 上已没有 `fe3b-upload-validator:latest`、`fe3b-upload-backend:latest`（`docker images` 核对）。
- 实施方没有交设计会话，自行修复，合理。

### B7 模拟数据可达性：部分符合（F4）

- **已做到：** 处置场景数据已移入 `mock-data.ts`，单测逐条断言 §5.3 的组合；`d4` 有了 `promoted_baseline_node_id`，与 `d-arch` 不再共享归档结果；B7a 证实单测能拦住场景数组中的不可达组合。
- **断言范围只覆盖新场景数组：**
  - `HISTORY_PAGE_ONE/TWO`、`TEST_HISTORY_CURSOR_*` 等共用 fixture 不在处置断言范围内，演示 e 证实；
  - “d5 是唯一例外”只对场景数组成立。共用 fixture 中还有两条 D5 形态的数据（`APPROVED` + `NOT_CANDIDATE_BASE_ADVANCED`、无处置）：
    - `HISTORY_PAGE_TWO` 的 `fe2a-history-ref-old`（注释标为 D5 防御性）；
    - `TEST_HISTORY_CURSOR_SECOND` 的 `submission-1`（未标注）。
  - §5.3 要求这类数据“单独放在 D5 用例使用的数据中”。`fe2a-history-ref-old` 实际出现在所有 W 场景的截图里（如 `fe3b-w8-upload-disabled` 的“提交 1 · 已通过 · 基线已更新”）。
- **D1–D5 的树数据仍不可达：**
  - `d-arch` 与 `d4` 的父基线都是 `fe2a-history-ref-1`，却都是 `ARCHIVED_BASELINE`。第一次归档后 head 前移、其余已通过的同级提交被关闭，同一父基线不会产生第二次归档；
  - `d4` 提升的 `baseline-arch-2` 的父基线是 `baseline-arch`，与 `d4` 自己的父基线不同；
  - 两个归档基线存在，head 却仍是 `fe2a-history-ref-1`。截图 `fe3b-d1-archived` 到 `fe3b-d5-flag` 中，“归档基线 1”标“当前基线”，其下依次是“归档基线 3”“归档基线 2”。这批截图要交 owner 看图，数据会误导判断。

### B8 必测断言：部分符合（F5）

| 场景 | 结果 |
| --- | --- |
| W6 | 禁用（Preview 与工作台）、终态加 attempt 未结束显示“需要管理员处理”都有用例。“刷新后找回操作卡片”的用例在 URL 中已带 `operationId=submit-op-1`，没有走 §6.2“URL 中没有该操作时经 attempt 取 `operation_id` 并写入 URL”的路径。演示 c1/c2 证明产品行为正确，只缺正式用例 |
| W9 | ①②③与点击“重试”都有；但断言不足以发现提示与原因并存（F1、P3） |
| W10 | 两支都有（B2） |
| D1、D2 | 已打开审核模式，断言两个标签、三个按钮的禁用原因与“归档时选中了其他提交” |
| D3 | 关闭时间（悬停 UTC、正文 `MM/DD HH:mm`）、4 行理由折叠与展开、父基线是 head 时“归档主线”禁用都有。审核模式顶栏的有理由关闭行（`ReviewDispositionLine` 的“由 {closed_by} 于 {closed_at} 关闭”与理由展开）**没有用例** |
| 截图 | D1/D2 的审核模式用例没有截图，D3 审核顶栏没有用例。§9 要求的“§6.4 D1–D5：组态树、详情面板与审核模式顶栏”缺审核模式顶栏 |
| `job_kind` | 按 §6.2 实现：URL 中的提交操作与指针不一致时以指针为准，Preview 操作不动，两页都实现，有用例 |

§6.4 显示修正与截图核对（07 本次截图）：

- 详情面板删除了重复的“终局状态”；
- 关闭时间为组态树同款格式（`11/06 08:00`）；
- 多行理由折叠，展开后保留换行；
- 有理由关闭的状态位有悬停提示（用例断言 `title`）。

### B9 handoff 与代码一致：部分符合（F6）

- **已改正：** 审核报告 B9 所列各条——步骤卡、`job_kind`、D1/D3 用例、§2.4 规则有单测、N1 `strict: false` 如实写明、不再引用不存在的章节。
- **新的不符：** 见 F6。

## 4. 需要修复（阻塞）

### F1 续做提示与禁用原因仍可并存且矛盾（B3）

- **现象：**
  - 演示 a：W9②③点“重试”后，按钮原因变为“提交结果待确认，需要管理员处理”，页面顶部的提示仍是“无法确认提交状态”。FE3a B7、Q14 与 §6.2 要求“提示与禁用原因始终一致”。
  - 指针已清空、attempt 读不到时（`resumeAfterOperation` 返回 `unknown`），提示“无法确认提交状态”，按钮却可用。§6.2 第 2 步对此要求保留“无法读取提交结果，请刷新后重试”。
- **测试缺口：** P3 去掉续做后的 hook 状态更新，W9 与 n3 全部通过。原因是 W9②③的断言 `getByText("无法确认提交状态").first()` 由提示本身满足。
- **修复：**
  - 续做提示由 hook 按 §6.2 第 1–3 步从同一份快照派生（或在“重试”后重新派生），不再是页面里只写一次的独立状态；
  - W9②③分别断言“提交”按钮的禁用原因与提示文本，点“重试”后断言旧提示消失；
  - 补“指针已清空、attempt 读不到”一支。

### F2 attempt 已结束而指针未清时解锁（B4，§6.2）

- **现象：** 工作区只有 `active_submit_attempt_id`，attempt 读到 `FINALIZED` 或 `ABORTED` 时，`attemptPhase` 返回 `none`，“上传”“提交”可用（演示 b）。这个快照说明工作区读取过时，实际可能已有待审核的提交。§6.2 规定“不在指针未清时解锁”。
- **修复：**
  - 把它当作过时快照，纳入一次性重读（与 W10 同一机制），重读前后仍为该组合时保持禁用。原因用“无法确认提交状态”加“重试”，或由设计会话另定文案；
  - 改正单测“judges by the submission pointer when the attempt is already closed”，不再用两个指针同时非空的工作区，补本条的单测。

### F3 404 也触发一次性重读（B2，§6.1）

- **现象：** 撤回 gate 对 review 查询 404 返回 `reread: true`，hook 因此自动重读一次（演示 d404：2 次读取，403 为 1 次）。§6.1 中 404 一行是“未找到该提交，请刷新后重试（另附‘刷新’）”，由用户触发，不在自动重读的四种情形内；“刷新”入口目前也没有显示。
- **修复：** 删除 404 的 `reread`；按 §6.1 给出“刷新”入口（重新执行读取序列）；用例断言 404 时读取次数不增加、“刷新”可用。

### F4 模拟数据可达性仍有缺口（B7，§5.3）

- **断言范围：**
  - 处置与例外断言扩展到全部模拟 History 数据（`HISTORY_PAGE_ONE/TWO`、`TEST_HISTORY_CURSOR_*`、场景数组），按 ref 显式列出允许的 D5 例外；
  - 演示 e 那样的改动应使单测失败。
- **D5 形态数据：**
  - `fe2a-history-ref-old` 移出共用的 `HISTORY_PAGE_TWO`（W 场景截图不再出现它），或按 §5.3 改为 D4 形态；
  - `TEST_HISTORY_CURSOR_SECOND` 的 `submission-1` 改为可达形态（例如去掉标记），或标为 D5 并列入例外。
- **D1–D5 的树数据改为可达序列：**
  - `d-arch` 从 `ref-1` 归档成 `baseline-arch`，`d-closed` 为同一次归档关闭的同级提交；
  - `d4` 的父基线为 `baseline-arch`，归档成 `baseline-arch-2`，其父基线与 `d4` 的父基线一致；
  - head 为最新的归档基线；
  - 需要“父基线仍是 head”的 `d-manual` 挂在 head 下；
  - `d4` 因父基线不是 head 带标记（D4）。
- **补断言：**
  - 提升基线的父基线等于提交的父基线；
  - 同一父基线最多一个 `ARCHIVED_BASELINE`；
  - head 是基线链的末端。
- 改完后重拍 D1–D5 截图。

### F5 必测与截图缺口（B8，§9）

- D1–D3 的审核模式顶栏补截图（1280/1920）。D3 补审核模式用例：断言“由 {closed_by} 于 {时间} 关闭”与理由展开，并截图。
- W6 的“刷新后找回操作卡片”改为 URL 中不带 `operationId`：断言 URL 被写入指针 attempt 的 `operation_id`，操作卡片出现。工作台与 Preview 各一条，可直接采用演示 c1/c2。

### F6 handoff 不符（B9）

新 handoff 改正即可：

- §2 B2“W10 … workspace 表与 Preview 页都覆盖”：Preview 页没有走重读（§3 B2）；
- §2 B6 写校验镜像 tag 为 `fe-<HEAD12>`，代码取 10 位（日志为 `fe-403e2faefc`）；
- §6 探针表的表头重复了一次；
- §2 B8 W6“刷新后找回操作卡片”：用例没有走指针路径（F5）；
- W9②的用例标题“工作区与 attempt 都读不到”与内容（只有 attempt 读不到）不符，标题或数据二选一改正。

## 5. 非阻塞

- **N1：** 页面首次渲染、hook 尚未开始读取的一帧里，`workspaceLoading` 为 false，Preview 顶栏会短暂显示“无法确认提交状态”与“重试读取”（审核报告 N3 的残余）。把初值设为 `enabled` 即可消除。
- **N2：** `ClosureReason` 只按换行数判断“超过 3 行”。折叠后正文全部隐藏，只剩“展开理由”；很长的单行理由不会折叠。交 owner 看图时一并确认是否需要“显示前 3 行 + 展开”。
- **N3：** 截图 `fe3b-withdraw-unknown` 拍摄时差异结果仍在下载（骨架屏），顶栏“重试读取”与“提交”挤在一起。建议等 bundle 就绪后再拍。
- **N4：** 部分 W 场景的 History 与工作区指针不一致。例如 `fe3b-w6-recovery` 中树上有“提交 2 · 待审核”，工作区却是 attempt 指针，后端不会同时出现。修 F4 时顺带对齐，不单列。
- **N5：** “提交结果待确认，需要管理员处理”的提示把操作 ID 标为“错误代码：submit-op-1”（FE3a 起如此）。§6.2 写的是“含操作 ID”，建议改标“操作 ID”并可复制。
- **N6：** 审核报告 N4（被占用时工作区节点仍标“可提交”）仍待 owner 看图确认，本轮未改，符合约定。

## 6. 下一步

1. 实施会话按 F1–F6 修复，提交新的代码候选与 handoff。复审第 2 轮范围 `4e0d074179..<新 handoff>`，重点：
   - P3 同类探针应使 W9 失败；
   - 演示 a、b、d404、e 的场景成为正式用例并通过；
   - 07 重跑 `run-tests.sh --e2e --screenshots`；
   - 05 重跑 journeys（F1–F3 改动 hook，需要确认真实旅程不受影响）。
2. 复审通过后的 04 取证（kickoff §9 FE3b 行）不变。三项在 04 的 clean、已提交 detached worktree 上各运行一次：
   - `run-tests.sh --e2e --screenshots`（含 §5.5 的互通用例）；
   - 修复后的 `validate-upload-package.sh`；
   - `run-real-backend-e2e.sh --suite journeys --subphase fe3b`（日志含 RS 完整 DiffID）。
3. §6、§6.4 截图（含审核报告 N4 的工作区节点“可提交”问题、本报告 N2）交 owner 确认；取证后做证据核对，再给出 FE3b 退出建议（FE3 在 FE3c 结束时退出）。
4. 本轮遗留：
   - 已删除：探针 worktree、`refs/review/fe3b-rr1/probe-*`、传输用 bundle；
   - 保留供复审对照，FE3b 退出后清理：
     - 两节点的 `/home/dev/gdds-fe-rereview1-fe3b` 与 `refs/review/fe3b-rr1/candidate`；
     - 05 的 `/home/dev/gdds-test-tmp/fe3b-rr1-upload-out`；
     - 两节点的 `/home/dev/gdds-fe-logs/fe3b/rereview-1/`；
     - 07 的截图目录 `/home/dev/gdds-fe-shots/fe3b-rereview1-4e0d0741`；
   - 第 1 轮保留项不变：开发主机 `/home/dev/gdds-fe-review-fe3b-afd7711e`，05/07 的 `/home/dev/gdds-fe-review-fe3b-candidate`。

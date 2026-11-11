# FE4a handoff：带入项、Q21、令牌、取证工具与新后端回归（调试）

- **实施会话：** FE4a 实施会话（新会话，沿用 FE4a 提示词，不沿用 FE3 实施会话上下文）。
- **日期：** 2026-11-10（时间均为 UTC）。
- **依据：** FE4 kickoff（main `a4c4d60827`）§3.3–§3.8、§5.2、§6、§7、§8、§10、§12；FE3 kickoff §3.2、§4.6、§4.7、§6.4、§8、§16；FE2 kickoff §5.5；后端 Q21 答复（`p6-fe3-q21-answer`）；`fe4a-prompt-preflight.md`。
- **结论：** C1–C11 按 kickoff §3.4“处理”列完成（C4 的“逐字节相同”未达成，见 §5）、Q21 按 §3.5 完成、令牌按 §3.6 完成、取证工具按 §3.8 提交在 `frontend/scripts/`、入口加 J1/J2 调试选择（§7.2）、t1 参考截图按 §3.3 加入。J1、J2 调试通过（C7 之后接受都经界面；异常集合与 FE3 kickoff §4.6 一致），t1 调试运行一次通过。模拟接口全量在最终候选上连续两次通过（H、I）。不接入 BE-b，不合入 main，不推送。

## 1. 起点、快进与路径核对

- `fe-vnext` 在 `/home/dev/gdds-fe` 从 `e22e39ba1528c7a0339c9c800d87fb3f3f95190a` 用 `git merge --ff-only` 快进到主线 `16ffe728290e1179d9450ea160a0e6ca49473ec6`（`16ffe72829`）。无合并提交，不 rebase，未合入其后的 main（P7 S1a 文档在 `16ffe72829` 之后，FE4a 期间不合入，kickoff §6.1）。
- `<main>` 为 `16ffe72829`。候选的 `vnext/` 树为 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`，与 `git rev-parse 16ffe72829:vnext` 相等；`p6-exit` 目标 `b0fc25e881` 的 `vnext/` 与之相同（`fe4a-prompt-preflight.md` §2）。
- 路径核对（kickoff §5.2）：`git diff --name-only 16ffe72829 <候选>` 只含 `frontend/` 与 `docs/frontend-vnext/` 下的路径（`vnext/` 无改动；`AGENTS.md`、`frontend/` 以外的顶层文件无改动）。
- 代码候选：`674c24fbb21f6ddbc6cfcade2d5112635d8280eb`（`fe-vnext`，未推送），§5 的两次全量 H/I 在此提交上运行；`frontend/` 树为 `154a5a4af52192caf9b8d038e68285ce3185fca5`（FE3c 退出时为 `46e425f84eb28936563c8751295a8829e33f3ad6`）。本 handoff 与其配套的 `check-handoff-hex.py` `--allow` 选项作为其后的 docs/tools-only 提交加入；证据运行在最终 HEAD 的 clean detached worktree 上执行。
- `--print-input`：在 05 的 clean 检出（HEAD `16ffe72829`）中运行 `vnext/scripts/build-backend-dependency-base.sh --print-input`（审核会话 2026-11-10 现场实测，`fe4a-prompt-preflight.md` §3），输入摘要为 `578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`，即 `gateway-backend-deps:lock-578e079b762e`。RS 依赖镜像为 `gateway-p2r1-repository:lock-6dc9659f0aee`（`repository_service/uv.lock` SHA256 `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`）。
- OpenAPI 快照：未刷新。J1/J2 与 t1 每次真实运行都在浏览器用例之前把运行时 `/openapi.json` 按 FE3 kickoff §5.1 规范化后与已提交快照逐字节比较，均为 `openapi_compare=match`（规范化后 SHA256 `4c2ddca7d64ec77029528f5a6f03f73b17185784091530c7086fa67d484d620a`）；没有出现 kickoff §6.3 的停止条件。

## 2. 改动位置与用例（C1–C11、Q21、令牌、取证工具、入口、截图）

### 2.1 C1 续做提示不残留（FE3b N2）

- `frontend/src/features/workbench/use-upload-mode.ts`：新增 `resumeAttemptId`/`resumeSubmissionId`（记录续做结果所属快照）与 `clearResumeNotice()`（`setResumeSeq(0)` 并清指针）；`resumeNotice` 在工作区指针已离开续做结果时返回 `null`。
- `frontend/src/pages/ComparisonPage.tsx`：打开提交对话框时调用 `clearResumeNotice()`；`frontend/src/pages/WorkbenchPage.tsx`：上传开始（`onUploadStateChange(true)`）时调用 `clearResumeNotice()`。
- 用例：`e2e/workspace-shell.spec.ts` 新增 `C1 续做后开始新的提交时红色提示框清除`（续做 ABORTED → 打开提交对话框 → 提示框消失，对话框出现）。

### 2.2 C2 重试经在途合并（FE3b N6）

- 新增 `frontend/src/features/workbench/inflight.ts`（`InflightGate`：并发触发共用一次运行，失败共担、settled 后释放）与 `frontend/src/features/workbench/inflight.test.ts`（两个单测：快速连点只执行一次、失败共担后释放）。
- `use-upload-mode.ts` 的 `retryResume` 先串行等待在途 `refresh()`（`inflight.current`），再经 `retryGate` 合并，实现“快速连点只产生一次读取序列”。
- W9④（`workspace-shell.spec.ts`）：第二段重试增加 attempt 读取次数断言（重试前后内容可区分）；第一段的 workspace/attempt 双计数保留。
- G3 放宽收敛到单页切片：`frontend/src/features/dev/mock-data.test.ts` 的 `checkDispositionCombinationRules` 新增 `allowOffArrayHead` 参数；4 个单页切片为 `true`，两个合并视图、场景集与 D5 为 `false`。

### 2.3 C3 顶栏禁用原因分开显示（FE3b N7）

- `frontend/src/design-system/components.tsx` 的 `Button`：`aria-describedby` 改为调用方传入值与禁用原因 ID 的合并（原来有禁用原因时丢弃调用方传入），各自对应自己的按钮。
- `frontend/src/pages/ComparisonPage.tsx` 的 `PreviewHeaderActions`：撤回与提交两个原因之间加 `compare-actions__divider` 分隔线（仅两个原因同时存在时渲染）；`frontend/src/styles.css` 增加 `.compare-actions__divider` 样式（1px 垂直线，两侧各 4px 间距）。
- 用例：`e2e/upload-mode.spec.ts` 的 W6 用例断言两个 `.disabled-reason` 分开渲染（`toHaveCount(2)`）、`aria-describedby` 互不相同、分隔线可见。（初版另加 `gap: 8px`，逐字节比对发现会整体移动 preview 顶栏，已 revert；最终只保留分隔线，`navigation-fallback-1280.png` 与 FE3c 逐字节相同。）

### 2.4 C4 截图固定时钟（FE3b N8）

- `e2e/upload-mode.spec.ts` 与 `e2e/workspace-shell.spec.ts` 的 `freezePageClock` 统一为 `await page.clock.setFixedTime(new Date("2026-11-03T09:00:09Z"))`（固定 `Date`，定时器照常运行；固定时刻为 mock 操作开始 `2026-11-03T09:00:01Z` 之后 8 秒）。含等待时长的用例断言“已等待 8 秒”固定值：`upload-mode.spec.ts` 的 W6 三个用例与 `workspace-shell.spec.ts` 的 `History 比较仍在运行…`、`FE2c 执行中刷新后恢复页面锁定…`。
- 所有截图调用加 `animations: "disabled"`；`frontend/playwright.config.ts` 的 mock 配置加 `launchOptions: { args: ["--force-color-profile=srgb"] }`（`playwright.real.config.ts` 不变）。
- `e2e/upload-mode.spec.ts` 的 screenshot helper 新增 `settleAfterResize(page)`：视口切换后等待 canvas 后备尺寸与 `.grid-frame` 宽度一致、`data-rendered="true"`，再等两次 rAF 后截图（修复 1920 截图偶发空网格，见 §5）。
- 同一提交连续两次全量的逐字节比对结论见 §5：固定时钟与稳定内容已达成；“逐字节相同”未达成，原因是浏览器每次启动的亚像素光栅差异，已用对照实验定位。

### 2.5 C5 409 后重读 review 与 History（FE3c N2）

- `frontend/src/features/workbench/ReviewActions.tsx`：`ReviewActionsProps` 新增可选 `onReviewSettled`；成功刷新后与 409（`BASELINE_VERSION_CONFLICT` 通过过期、`ARCHIVE_CLOSED`）刷新后各调用一次。
- `frontend/src/pages/ComparisonPage.tsx`：传入 `onReviewSettled={() => void reloadReviewContext()}`；`reloadReviewContext` 在 REVIEW 模式下同时重读 `getReviewFacts` 与 `listHistory`（只更新 facts，不碰 bundle/错误态；基线变化由下一次锚点读取接管，注释说明这是有意的）。
- 模拟数据：`workspace-shell.spec.ts` 的 fixture 在 `reviewConflict === "ARCHIVE_CLOSED"` 的 409 送达后，后续 Review GET 携带 `MANUAL_CLOSE` 处置（`closed_by: reviewer`、`closed_at: 2026-11-03T10:00:00Z`、理由“不再需要该提交”）。
- 用例：V11 断言过期通过 409 后 History GET 增加；V12 断言重读后按 §6.4 显示（“由 reviewer 于…”、展开“查看关闭理由”看到理由、审核通过禁用）。

### 2.6 C6 来源摘要悬停与理由折叠（FE3c N3，含 FE3b N2 长单行理由）

- `frontend/src/features/workbench/ArchiveMainlineDialog.tsx`：
  - 卡片标题加 `title="issue_code=… · subject_digest=…"`；详情段加 `title`（全文摘要 + 全部 edge 的完整 `canonical_state_digest`）；受影响提交加原文 `title`（`anomalyHoverTitle`）。
  - 新增 `ReasonText` 组件与 `.archive-reason--clamped`（3 行 clamp + “展开/收起”）；只有长度超过 120 字符的理由走折叠路径，短理由保持与 FE3c 逐字相同的 JSX（逐字节验证见 §5），单行长理由同样折叠。
- 用例：V1 追加悬停断言（全文 digest、`issue_code`、`subject_digest` 的 `title`）；新增 `C6 长理由折叠为三行并可展开`（151 字理由 → 出现“展开”、clamp 类存在 → 点击 → “收起”且 clamp 消失）；`archive-validation-data.ts` 新增 `vPreviewAllKindsMissingAccepted(reason)` 以提供接受后重读的第二个 preview。

### 2.7 C7 真实旅程经界面接受（FE3c N4）

- `frontend/e2e-real/journeys.spec.ts` 新增 `acceptAnomaliesViaUi(page, submissionLabel, reason, cardText?)`：打开归档对话框，循环接受可见卡片（每次接受前等加载态消失且预检区可见；接受成功以接受对话框关闭为准，失败保留对话框内联错误并 loud 失败）。
- J1 第 8、10、11、13 步与 J2 第 1、7、8 步的 `acceptAnomalies`/`acceptAllAnomalies` API 调用改为经界面；J1 第 14 步三节点历史比较改由审核人会话执行（`reviewerSession`）。J1 第 7 步的退回、第 9 步的两 context 撤销流程保持 API（不在 C7 范围）。
- 过程修正：初版用“等待已接受出现”作完成信号，遇到整组折叠导致计数为零提前返回（J1 step 10 现场定位）；已改为对话框关闭信号 + 每次计数前 settle。

### 2.8 C8 冲突提示与集合变化提示分开显示（FE3c N5/M1）

- `frontend/src/features/workbench/ArchiveMainlineDialog.tsx`：新增 `conflictNotice` 状态与独立横幅（`.form-warning`，在 `collectionNotice` 之后渲染）；409 处理改为 `setConflictNotice(notice)` + `pendingNotice.current = notice`；`load()` 在集合变化时固定显示通用文案，每次成功加载必清 `pendingNotice`，普通加载清掉陈旧冲突提示，409 后的加载保留冲突提示使两条同时出现；对话框打开时两处都清。
- 用例（`e2e/archive-validation.spec.ts`）：`C8 关闭 409 后集合变化时两条提示都出现`；`C8 集合未变时后续加载不显示旧的冲突提示`。

### 2.9 C9 关闭对话框（FE3c M2）

- `ArchiveMainlineDialog.tsx`：关闭正文改为 `"关闭" + displayName + "（不归档）。"`（修复“关闭提交提交 2（不归档）”重复）；成功后“确认关闭”按钮改标签为“已关闭”并带 `disabledReason="已关闭"`（仍禁用防重发，重放由幂等 key 保障）。
- 用例：V9 打开即断言正文匹配 `/关闭提交 \d+（不归档）。/` 且无“关闭提交提交”；V9 200 回放断言成功后按钮为“已关闭”且禁用、`确认关闭` 计数为 0。

### 2.10 C10 详情映射单测（FE3c M3）

- `frontend/src/features/view-model/archive-dialog.test.ts` 新增 `covers the four §16.3 detail mappings missing from C10`：`INITIAL_SOURCE_UNEXPLAINED`、`GENERATION_TIME_LAST_NOT_MAX`、`TIME_ABNORMAL_INITIAL`、“② 早于 ①”（`MODIFIED_BEFORE_INITIAL`）四条逐字断言。

### 2.11 C11 `unrouteAll`（FE3c N9）

- `frontend/e2e/workspace-shell.spec.ts` 的 11 处裸 `unrouteAll()` 全部改为 `{ behavior: "wait" }`。
- 原三处固定延时改为测试可控 gate：新增 `deferred()` 与 `slowPreview?: Promise<void>`、`timeoutFirstCompare?: Promise<void>` 选项；`加载中显示骨架…`、`History 比较超时重试…`、`查看差异超时后的重试复用同一幂等意图` 三个用例分别 hold/release gate；已无调用点的 `historyBundleDelayMs` 删除。

### 2.12 Q21 诊断码文案（kickoff §3.5）

- `frontend/src/features/view-model/diagnostics.ts`：删除 `ROW_IDENTITY_UNSUPPORTED`、`ORDER_KEY_UNSUPPORTED`、`COMPARISON_MODE_NOT_DETAILED`、`BLANK_PROVENANCE_INVALID`（各删 `SURFACE_COPY` 与 `SURFACE_DIAGNOSTIC_CODES` 两处）；新增有序表组 `ORDERED_PROVENANCE_MISSING`、`ORDERED_PROVENANCE_INVALID`（文案“有序表缺少空行来源信息，或该信息无效”）与内部组 `METADATA_ROUTE_REQUIRES_NATIVE_ROWS`、`METADATA_ROLE_REQUIRES_NATIVE_ROWS`（文案“比较时发生内部错误”）；保留 `BLANK_PROVENANCE_MISSING`、`CANONICAL_BLANK_PROVENANCE_INVALID`、`ORDER_KEY_INVALID`、`COMPARISON_RULESET_DIGEST_MISSING`；匹配顺序不变。
- `frontend/src/features/view-model/diagnostics.test.ts`：新增 4 码文案断言 + 删除的 4 码不在码表中的断言。

### 2.13 `--color-warning-soft`（kickoff §3.6）

- `frontend/src/styles.css`：`.form-warning` 的 `background` 改为 `var(--color-surface-muted)`。三处使用方（`SubmitDialog.tsx` 两处、`UploadStepCard.tsx` 一处）不动；外观不变，不新增黄色令牌。

### 2.14 取证工具（kickoff §3.8，`frontend/scripts/`）

- `run-evidence-wrapper.sh`：写日志前检查参数个数/会话名格式、worktree 与日志目录为绝对路径、日志目录已存在、截图目录在 worktree 外，任一不满足即退出、不运行入口；按入口区分占用（`run-tests.sh`、`validate-upload-package.sh` 由 wrapper 原子 `mkdir` 取得标记并只删自己的；`run-real-backend-e2e.sh` 由入口自行取得，wrapper 只确认标记不存在）；记录 hostname、起止 UTC、起止 HEAD、`HEAD:frontend`、`HEAD:vnext`、起止 `git status`、占用标记内容；`set -o pipefail` 取入口 exit code；写 `.sha256` 旁注；按入口从日志逐行取结果字段，取不到时写明原因（不写 `MISSING`）。
- `check-handoff-hex.py`（`python3 -I`，仅标准库）：读取 handoff，找出全部十六进制值并逐个回源——`--git-objects` 用 `git cat-file -e` 核对 7–12/40 位值；`--sha-file`（sha256sum 格式，可多个）核对 64 位值并输出命中路径；`--source-dir` 对“路径 + SHA”同行做配对核对；`--allow` 声明已知的非 Git 对象 token（如镜像 tag 的 12 位后缀）并单独报告；截断形（`…`）只列出不验；报告未命中与长度异常（非 7–12、40、64）；exit 0/1。
- 两个工具均经正反验证（§9）：wrapper 的参数检查在开发主机验证（错误即退、入口未运行）；hex 脚本在开发主机用正反 fixture 验证（错一位即报未命中）。

### 2.15 入口 J1/J2 调试选择（kickoff §7.2）

- `frontend/scripts/run-real-backend-e2e.sh`：`--subphase` 接受 `fe4a`；新增 `FE4A_SCOPE_SLUGS=(j1-archive-mainline j2-manual-close)`，复用 `FE3B_SCOPE_SLUGS` 的白名单过滤；`--suite journeys` 的用法更新为 `fe3b|fe3c|fe4a`；`--suite t1` 不变。证据运行不带该选择，跑完整集。
- 调试点：为避免未播种 scope 的 18 个用例失败（`scopeBySlug` 缺 scope 即抛），playwright 调用加了按 subphase 的 `--grep`（`fe4a` 时 `--grep=j1-archive-mainline|j2-manual-close`，日志记录 `playwright_grep=`）。

### 2.16 t1 参考截图（kickoff §3.3，不依赖 BE-b 的 7 个页面）

- `frontend/e2e-real/t1.spec.ts` 新增 `saveEvidenceBothWidths`（1280 与 1920 各拍一张，命名 `<名>-1280`、`<名>-1920`），插入点全部在 M1 测量窗口之外、不新增旅程步骤、不改变 §8.3 判据：
  - `fe4-t1-workbench`（第 1 步上传前）、`fe4-t1-preview-v1`（第 1 步 M1 取值之后，已有 `t1-v1-diff` 保留）、`fe4-t1-preview-v2-baseline_to_initial` / `fe4-t1-preview-v2-initial_to_modified`（第 4 步按 `pair_id` 取用，点 tab 切换）、`fe4-t1-review`（第 5 步，reviewer 只读访问）、`fe4-t1-history-3node`（第 6 步抽屉完成后，已有 `t1-history-three-nodes` 保留）、`fe4-t1-archive`（第 3 步预检状态可见后、确认归档前）。
- 不加依赖 BE-b 的页面。

### 2.17 新增或修改的用例清单

- 单测：`inflight.test.ts`（新增 2 项）；`diagnostics.test.ts`（+4 新增码 +4 删除码）；`mock-data.test.ts`（G3 收窄，数据驱动）；`archive-dialog.test.ts`（+1 个 `it` 覆盖 C10 四项）。
- 模拟 e2e：`workspace-shell.spec.ts`（C1 新 1 项；W9④ +attempt 计数；V11/V12 History 重读断言；C5 mock 处置；C11 11 处改参与 3 个 gate 用例）；`upload-mode.spec.ts`（C3 分隔/aria 断言；C4 冻结与固定文本断言；screenshot helper 视口等待）；`archive-validation.spec.ts`（V1 悬停断言；C6 折叠新 1 项；C8 新 2 项；C9 正文 + 成功态断言）。
- 真实 e2e（只改 J1/J2 接受路径与 J1 step 14 执行身份）：`acceptAnomaliesViaUi` 新增；J1 8/10/11/13、J2 1/7/8 改走界面；`e2e-real/t1.spec.ts` 新增 7 个参考截图点（双宽度）。
- 附带修复（超出 C1–C11 的范围，需审核确认）：`frontend/src/features/bundle/local-bundle.ts` 的 `removeEntry` 对 OPFS 删除的短暂 DOMException 做 4 次短重试（20/40/60/80 ms）；原因：全量运行中 bundle 截断重试用例约 2/5 次以 `NoModificationAllowedError` 失败（run A、E），隔离运行 30/30 通过，属中止写入后的短暂锁；修复后 run F、G、H、I 均通过。

## 3. J1、J2：预检异常集合与耗时（`49c1de43be`，`--subphase fe4a` 调试运行）

调试运行（§7.2）：05 节点，`run-real-backend-e2e.sh --suite journeys --subphase fe4a --session fe4a-impl`，wrapper 见证；通过轮为 `07:52:49Z→07:55:18Z`（J1 74 秒：`07:52:49Z→07:54:03Z`；J2 75 秒：`07:54:03Z→07:55:18Z`；取自日志，只报告）。运行 HEAD 为 `07a55a1db6`（`16ffe72829` 之上第 4 个 WIP 提交；最终候选在其后又改了 C11 gate、C4 截图等待、OPFS 重试与测试代码，见 §6）。J1、J2 每次预检的异常集合由用例内 `expectAnomalySets` 按 FE3 kickoff §4.6 的比较口径核对，不符即报“phase: anomaly set differs from the kickoff table (stop for design review)”；下表为通过轮的实际值（`sub-*` 为当次提交 ID，码与 side 与 §4.6 一致）：

| 旅程 | 步骤 | 异常集合（`kind|code|side|受影响提交`） |
| --- | --- | --- |
| J1 | step 2 | `GENERATION_TIME_MISSING`（MODIFIED，A）1 项 |
| J1 | step 4 | FULL：`baseline_to_initial.changed=0`、`initial_to_modified.changed=5` |
| J1 | step 7 | `GENERATION_TIME_MISSING`（INITIAL，B）、`GENERATION_TIME_MISSING`（MODIFIED，B）、`BASELINE_TIME_UNAVAILABLE`（BASELINE，[B]）；B 来源 `EXPLAINED` |
| J1 | step 11 | `GENERATION_TIME_MISSING`（MODIFIED，C2）、`BASELINE_TIME_UNAVAILABLE`（BASELINE，[C2]） |
| J1 | step 13 | 上两项 + `PROJECT_IDENTITY_EXCEPTION`（D） |
| J2 | step 1 | `GENERATION_TIME_MISSING`（MODIFIED，A）1 项 |
| J2 | step 3 | `GENERATION_TIME_MISSING` ×5（B ①、B ②、C ②、E ①、E ②）、`BASELINE_TIME_UNAVAILABLE`（[B,C,E]）、`APPROVED_SIBLING_EXCLUDED` ×2（C、E） |
| J2 | step 5 | `INITIAL_SOURCE_UNEXPLAINED`（INITIAL，[E]）、其余 missing ×4、`BASELINE_TIME_UNAVAILABLE`（[B,E]）、`APPROVED_SIBLING_EXCLUDED`（E）；全部 `UNRESOLVED` |
| J2 | step 8 | `GENERATION_TIME_MISSING`（MODIFIED，C2）、`BASELINE_TIME_UNAVAILABLE`（BASELINE，[C2]） |

与 §4.6 表逐项相符（B 的 FULL 基线对 changed=0；C2 的两项；E 的来源解释与关闭后未解释；D 的身份确认；J2 step 4 的关闭 201 后回放 200、同 key 同 body、`expected_review_version` 取同次候选版本、全程无 Review GET；J2 step 6 的指针清空与处置显示；J1 step 14 的三节点历史比较浏览）。未出现上表以外的编码，不符即停的条件未触发。变长主因是 C7 的界面接受（每个接受一次对话框往返）。journey-cases.log 未保留（用例把 evidenceDir 默认写到 worktree 内，运行后清理）；后续证据运行将带 `--evidence-dir` 到 worktree 外。

## 4. t1 调试运行一次（§8.3 逐条核对，不做计时，不用 t2–t4）

调试运行（§7.2 只允许一次，本次通过，不再运行）：05 节点，`run-real-backend-e2e.sh --suite t1 --input-root /home/dev/gateway-real-dumps/source-dirs --session fe4a-impl`，wrapper 见证；`07:55:41Z→07:59:57Z`，exit 0；运行 HEAD `07a55a1db6`、`vnext` 树 `49c1de43be`。

- 输入核对（入口在 Compose 启动前执行，不符即停）：`t1-v1`、`t1-v2` 各 19 个文件（11 条目录项），`sha256sum -c` 通过；清单与 FE3a 一致（`SHA256SUMS-t1-v1.txt`：`cdb598cdd30198ee94e56469c0c289be1ad1e1e8524e5da13b9d00249eed0163`；`SHA256SUMS-t1-v2.txt`：`fa2450fac17f5011fee31eb0b163a7355846932c973dedf86bfe10532c32a96a`）；预期值从被测树 `vnext/backend/benchmarks/real_dump_journey.py` 的模块级常量读取，v1/v2 `preview_table_count` 均为 124，v2 changed 为 4。
- v1 Preview（MODIFIED_ONLY）：`table_count = changed = 124 + 1`（+1 为派生表 `composite_signal_point`），`degraded = failed = 0`。
- v2 Preview（FULL）：恰好两个比较对，按 `pair_id` 取用：`baseline_to_initial` 的 `changed = degraded = failed = 0`，`table_count` 记录实际值 125；`initial_to_modified` 的 `table_count = 124 + 1`，`degraded = failed = 0`，`changed = 4 + composite_changed`，实测 `composite_changed = 0`。
- 每次下载经 tar 成员与摘要校验；无未捕获的页面错误（`expectNoPageErrors` 通过）。
- 出现过的诊断码：step 3 的 anomalies 为 `[]`（与 §3.3 一致）；surface 诊断文案均命中 §3.5 文案表，§3.5 以外的编码未出现。
- M1（只报告，与 FE3a t1 v1 的 24.86 MiB 并列；FULL 只报告、不可比较）：第 1 步 MODIFIED_ONLY `renderer_increment_bytes=20 058 112`（19.13 MiB，比值 0.77，未超 2 倍）；第 4 步 FULL `renderer_increment_bytes=-1 835 008`（同一浏览器实例，增量偏低，只报告、不作基线，符合 Q23）。
- 参考截图（只留节点，SHA256 如下；不作验收）：

| 文件 | SHA256 |
| --- | --- |
| fe4-t1-workbench-1280.png | d689c2ac89b1ecb354cfa7e2f67af4f98bb6e052e97f89a060b728b5de395d3d |
| fe4-t1-workbench-1920.png | adfcd4af8e6fc6ea830a926ead8e0dc063ffa1537a17725e1957b4a1ff346e9d |
| fe4-t1-preview-v1-1280.png | c3fac1ac75ee0f271451fb230eca97739f3a237b133b4a0e4176487fd4d383e5 |
| fe4-t1-preview-v1-1920.png | 60f70b283873f172ecf5fec887811c65f3b9ff00158b040336b485d1ec508547 |
| fe4-t1-preview-v2-baseline_to_initial-1280.png | b53556c4751b1a5524af73cd1d80be978190dce660b87205579c321c3835ee53 |
| fe4-t1-preview-v2-baseline_to_initial-1920.png | 375b2ddd7d05c4bf9966b682012fa8c4131fef62d4e511bac11372c298ff3222 |
| fe4-t1-preview-v2-initial_to_modified-1280.png | 25c3c441b6340435c46b8b48cb82d25f6db5b377d5b6752832dac46f16b1707f |
| fe4-t1-preview-v2-initial_to_modified-1920.png | 111f9dcf5d65bb4c221129c32b3a77e765902a0fe8984e239c9a561a0c520b05 |
| fe4-t1-review-1280.png | e25caf53cd41e3e622bbe2a4a6bcfdf87716bced36891ed13b1cd7fc2ec90d3e |
| fe4-t1-review-1920.png | 0f1c1e51ccc0adbb8a6021f5ad98b2bc5693ae3d7ac868b85a613797c327c11e |
| fe4-t1-history-3node-1280.png | a1763a0313ee506623eb8e2bba93189b95b7d4abef39c89d1e507056fddf0808 |
| fe4-t1-history-3node-1920.png | 08421992d4a9f46ab4638cfbb9528863c0412f4ee6972e541ab2515482867902 |
| fe4-t1-archive-1280.png | 3b1b3c0fa483cdaca089414713b624d3f73ace25a1962dcda12dd06cad865520 |
| fe4-t1-archive-1920.png | 305fd66a4b1c5742cd629cfefdfc391a17c1e8572d0818d47965abf44b8ae9f6 |

- 打包流程筛查（kickoff §7.4）：`git diff --stat 16ffe72829 <候选> -- frontend/src/features/workbench/upload-package.ts frontend/src/features/workbench/UploadStepCard.tsx` 为空 → 未改变，不触发 t4 重测。
- 已知偏差（§10 未决事项，不追加 t1 运行）：t1 参考截图在 `07a55a1db6` 上拍摄，当时 `compare-actions` 仍带 8px 间隙（C3 初版）；最终候选已 revert 为无间隙（分隔线保留）。受影响的只是 3 张 preview 页截图的按钮间距，行为、测量与判据不受影响；正式重拍在 FE4b（BE-b 树上）进行。

## 5. C4 证明与残留差异（07，同一提交连续两次全量）

- 最终候选上的两次全量：run H（`11:01:23Z→11:02:54Z`）与 run I（`11:03:00Z→11:04:30Z`），均 `90 passed`、exit 0，各 190 张 PNG。逐字节比较：13 张不同，均为 1–73 px 的亚像素光栅/AA 与动画帧差异，无页面内容差异（此前 run F/G 在 8164fe6d 上的 3 张 1920 空网格竞态已由 `settleAfterResize` 修复，H/I 不再出现）：
  - `1280/fe3b-d1-review-topbar` 2 px、`1280/fe3b-w10-stale-preview` 2 px、`1280/fe3b-w6-attempt-running` 2 px、`1280/fe3b-w6-withdraw-busy` 14 px、`1280/fe3c-confirm-disabled-loading` 10 px；
  - `archive-blocked-1280` 4 px、`upload-locked-1280` 5 px、`s2-compare-tray-1920` 4 px；
  - `review-permission-denied-1280` 73 px、`review-permission-denied-1920` 1 px、`review-reject-dialog-1920` 1 px；
  - `submit-identity-confirmation-1920` 11 px、`submit-summary-workspace-1280` 33 px。
- 根因对照实验（07，同一工具链镜像，聚焦 `W6 Preview` 与同页截图）：`--disable-gpu`、`--disable-partial-raster`、`--num-raster-threads=1`、`--disable-skia-runtime-opts`、`--disable-lcd-text`、`--force-color-profile=srgb` 及组合各跑两次，均不能使两次启动逐字节相同；`--deterministic-mode` 会让 `page.screenshot` 等待字体超时（30 s），不可用。最小静态页面（单个带 1px 边框与圆角的 div，`--force-color-profile=srgb`）连续 6 次启动的 SHA256 全部为 `4389c199d2c8cdd8cd64ac30891bd9c7cd3cd5f4387aaac4a4eaec5cfacd8255`——静态圆角边框本身是确定的。
- 应用侧差异集中在：比较页操作卡（高 71.5 px 的分数高度）圆角处的 1-LSB 混合，以及表格列宽为分数宽度时 1px 边框接缝像素在“边框色/背景色”之间的翻转（如 (178,180,183) 与 (235,237,241)，坐标 347/916、y=291/383）。同一浏览器实例内相隔 300 ms 的两张截图逐字节相同（`612c593efdc21028c9c90ea604b95dc7b28be751497a6ef9f7515a9ae1e6bce1`），说明差异来自浏览器启动级的光栅路径，而不是页面时钟或动画。
- 结论：固定时钟、`animations: "disabled"`、稳定缩放与视口等待已全部落地；同一提交两次全量仍存在上表 13 张的亚像素差异，**不能声称逐字节相同**。这是 Chromium 在分数布局上的光栅行为，页面侧无法在不改变生产外观的前提下消除。残留清单、像素计数、flag matrix 与最小页面对照均在此记录，交审核会话与 owner 判定；未触发 §8 的其他停止条件。

## 6. 运行记录

| 运行 | 节点（hostname） | 起–止 UTC | HEAD 起/止 | frontend 树 | vnext 树 | exit | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A 全量模拟 | 07（gw-dms-07.lan） | 10:36:43–10:38:11 | 2ee0e9f614 | a4bbc16b90 | 49c1de43be | 1（1 failed） | a87a8ede090d98f4fd11bee500fc5d856fafad152529e7ade92ec0c14c10dc19 |
| B 全量模拟 | 07 | 10:38:38–10:40:08 | 2ee0e9f614 | a4bbc16b90 | 49c1de43be | 0 | fffef064b95cc7d324b9e727629c1c5a0e5ec3f0025fabd63a4ea00917a6331c |
| C 全量模拟 | 07 | 10:40:17–10:41:44 | 2ee0e9f614 | a4bbc16b90 | 49c1de43be | 0 | 3df46bbd4f10ee7b356d5cefc800f801f5275b014ba377db9ed6e12076c2138a |
| D 全量模拟 | 07 | 10:46:29–10:47:59 | 8af927f3f6 | bb76fd2a59 | 49c1de43be | 0 | 3f85f610ba0aa2b67bd82dff56c326270dc2028a7c77109f32eb0e1908053f3c |
| E 全量模拟 | 07 | 10:48:06–10:49:33 | 8af927f3f6 | bb76fd2a59 | 49c1de43be | 1（OPFS 截断重试） | 47ae38466aba7fd4ba07626cc7745764d5e8e300af961c93c306cd4fd0f2c619 |
| F 全量模拟 | 07 | 10:53:54–10:55:24 | 8164fe6d88 | 8cbba38878 | 49c1de43be | 0 | 6d525f5fd0c8e05509ca8ff308eae67ef3cb81fdf16b439f32c3c6e3a334073f |
| G 全量模拟 | 07 | 10:55:29–10:56:56 | 8164fe6d88 | 8cbba38878 | 49c1de43be | 0 | c3a96fb2bd6d1aab5c952faa1f6b63ee532db72c6b93cc18a81343d71ab78019 |
| H 全量模拟 | 07 | 11:01:23–11:02:54 | 674c24fbb2 | 154a5a4af5 | 49c1de43be | 0 | e867dd0b8e028d9a70d44722bbc23f7895919dbda77a9334995657c15e31364d |
| I 全量模拟 | 07 | 11:03:00–11:04:30 | 674c24fbb2 | 154a5a4af5 | 49c1de43be | 0 | f29f00981b74b8df5b03524658e4b2316d771e6dedda0b87e4f7a54ba0aa2fd3 |
| J1/J2 调试 | 05（gw-dms-test-05.lan） | 07:51:29–07:55:23（套件 07:52:49–07:55:18） | 07a55a1db6 | 7c059ec3f0 | 49c1de43be | 0 | f792d0d42b17ed4e10bca7269b5afafe9c2fd89240f8a720b221b560238d75a5 |
| t1 调试 | 05 | 07:55:41–07:59:57 | 07a55a1db6 | 7c059ec3f0 | 49c1de43be | 0 | 557bc3a1618022fc460dfe26c573c06fa4f2cee059a3625b2734eafd2f8562be |

- H、I 的 07 记录：hostname `gw-dms-07.lan`，工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`（config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，7 个 RootFS DiffID：`bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`、`1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`、`c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`、`89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`、`ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`、`16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`、`d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`）；npm 缓存 `/home/dev/gdds-fe-cache/frontend/npm-cache`，来源归档 `npm-cacache.tar.gz` SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`（来源提交 preflight 记录为 `a2fb4a027a`，运行日志记录为 unknown）；`GATEWAY_FE_TEST_WORKERS=2`；entry 为 `run-tests.sh --e2e --screenshots <dir>`，每轮含 typecheck、lint、35 个单测文件/210 项、build、check:production-build、playwright 90 项。
- 05 的真实数据运行：工具链同上（config digest 与 7 DiffID 相同）；`dependency_base_image=gateway-backend-deps:lock-578e079b762e`，`dependency_input_sha256=578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`，image ID `sha256:2d13e70aa3101dba0bd4f07695ce4886c844b930787b56fafad0bda2c9a0dfbd`（19 层）；`rs_dependency_base_image=gateway-p2r1-repository:lock-6dc9659f0aee`（label `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`），构建的 RS 镜像 tag `gateway-repository-service:fe-07a55a1db6b9`；docker `29.9.1`、compose `5.6.0`；占用标记 worktree `/home/dev/gdds-fe4a-wip`；J1/J2 入口 wrapper 日志 SHA256 `c000f7e50a3998abafa0dd3644fed79bae67972ebcb986a31b126b97cc3e6621`，t1 入口 wrapper 日志 SHA256 `c97092a2fc2f7fa8d908fbe82c60bd9482d76b341e2d07477540f7d2f404ea93`。

## 7. 模拟接口截图清单（07，run H/I）

- run H 的清单：`/home/dev/gdds-fe-shots/fe4a-c4-h/shots.sha256`（190 个 PNG：根目录 100 个 `name-1280.png`/`name-1920.png`，1280/ 与 1920/ 各 45 个），清单 SHA256 `308ab357a767cf25ee756a53b2106086426bb025e1159b277a3934276f290ec6`。
- 交 owner 看图的文件（kickoff §7.3，有变化的页面；run H 值）：
  - C3 预览页顶栏两个禁用原因：`1280/fe3b-w6-withdraw-busy.png` `967288318d9538298b0f516d11d40a059af674786f2f208325f71e6b06fca4a1`，`1920/fe3b-w6-withdraw-busy.png` `e853273cfbd542ce44b3955293b1c6b6b4235cc8dcee52f30010a1a78696766f`；`1280/fe3b-w6-preview-resumed-card.png` 与 `1280/fe3b-w6-withdraw-busy.png` 同值，`1920/fe3b-w6-preview-resumed-card.png` 与 `1920/fe3b-w6-withdraw-busy.png` 同值；`1280/fe3b-w6-attempt-running.png` `d52d2324f207785251c356ac05b37fa2c447e212382f508de142b4e4547f3a02`，`1920/fe3b-w6-attempt-running.png` `10c8c834c3ea1db4a305b1b510faaaf13dd4200ba7299bff2b674ccbf8939db0`。三组均含分隔线（C3），其中 resumed-card 与 attempt-running 另含冻结的“已等待 8 秒”（C4）。
  - C9 关闭对话框与关闭结果：`1280/fe3c-close-dialog.png` `29d26e0734f028ca24a35bbd32c10f62972d7e04bbcbcfaf8495a423c2d2137c`，`1920/fe3c-close-dialog.png` `658cfd63c7b4fdfdd2f688e0abd3be2557827b536de9c2449ccd983bfc002f66`；`1280/fe3c-close-result.png` `f9d0e7b39c95a97e5326e9307554f529eee6d7e29f14ed13840f7ce5e1100201`，`1920/fe3c-close-result.png` `edc50d4460b0f123ae54f9afa7d5e5a59e5b6db490ea89c347738fb1881b1ea5`。
  - C6 来源摘要与长理由折叠：无新增截图；由 V1 的 `title` 断言与 C6 折叠用例覆盖。
  - C8 冲突提示与集合变化提示同时出现：无新增截图；两用例只断言文本。
  - C4 固定等待时长：`history-compare-running-1920.png` `a4cd97f445cfb1e13fc863b8017fe52fe19d7367ee753a4b1ba65a05113b8cdd`、`1280/fe3b-w6-resumed-card.png` `3fef3e46ef3890e153699ca60e04e87064fcf0acece72b145de17c3c4d18bbe2`。
  - V12 处置显示（C5）：`1280/fe3c-review-closed.png` `5fcbb5359f177abdbb0c921dbcebe2b0de6685956c27a16d3c32750e271e3456`，`1920/fe3c-review-closed.png` `6791164fbaa0edb6537d528b5ca1b0cd52dfb1e691fab40366021637a719b097`。
- run I 与 run H 只有 §5 的 13 张不同，其余逐字节相同；交审查看图时以 run H（或证据运行）为准。

## 8. 出现过的诊断码

- 模拟接口与真实旅程中出现的业务编码全部在 §3.5 文案表（surface）与 FE3 kickoff §16.3（归档）范围内：`ORDERED_PROVENANCE_*`、`METADATA_*` 未在真实数据中触发；`INITIAL_SOURCE_UNEXPLAINED`（J2 step 5）、`PROJECT_IDENTITY_EXCEPTION`（J1 step 13，D）、`APPROVED_SIBLING_EXCLUDED`、`GENERATION_TIME_*`、`TIME_ABNORMAL_*`（模拟）、`BASELINE_TIME_UNAVAILABLE` 均按文案表显示，未出现通用文案回退（`formatSurfaceDiagnostic` 的类名/通用分支只覆盖测试桩的 `FUTURE_CODE`）。
- §3.5 文案表以外的编码：无（`DUPLICATE_EFFECTIVE_KEY:<表名>` 等沿用旧文案，未改）。

## 9. 已完成、未测与未决

**已完成**

- C1–C11 按 §3.4 完成（C4 见 §5 的残留说明）；Q21 四个删除码/四个新增码与单测；`--color-warning-soft` 删除并保持灰底；取证 wrapper 与 hex 回源脚本；入口的 FE4a 子阶段与 J1/J2 选择；t1 七个参考页面双宽度截图；J1/J2 调试通过（异常集合逐项核对）；t1 调试一次通过；模拟接口全量在最终候选上连续两次通过（H、I）。

**未测（只由模拟接口覆盖的项及原因）**

- C2 的“快速连点合并”只有 `inflight.test.ts` 两个单测与 W9④ 的顺序读取计数覆盖；没有浏览器级连点用例（在 mock 中连点触发的是同一 in-flight promise，单测已直接证明；浏览器级只增加时间敏感性）。
- C5 的 History 重读只断言 GET 发生；`reloadReviewContext` 有意丢弃 `listHistory` 返回值（基线变化由下一次锚点读取接管），没有可断言的界面变化。V12 仅覆盖处置显示。
- C6 悬停全文与 C8 双提示、C9 关闭对话框只在 mock 用例中断言，t1/J1/J2 不含对应页面状态。
- OPFS 删除重试只在全量运行的截断重试用例上观察到原失败（run A/E），隔离 30/30 通过；修复后 F/G/H/I 未再出现，但没有专门的故障注入单测。
- 未跑 t2–t4、未跑第二次 t1 调试、未做计时；BE-b 依赖页面（导航、列名、行定位、侧栏分组等）不在 FE4a 范围，t1 正式重拍在 FE4b。

**未决**

- C4“同一提交连续两次运行逐字节相同”未达成（§5）；是否接受“固定时钟 + 动画冻结 + 视口等待 + 残留亚像素差异记录”由审核/owner 判定。
- J1/J2/t1 的调试运行在 `07a55a1db6`，最终候选在其后只改了测试等待、C11 gate、截图 helper 与 OPFS 重试（`local-bundle.ts`）；没有按“每个候选都重跑真实旅程”追加运行（kickoff §7.2 只允许一次 t1 调试）。证据运行将在最终候选的 clean detached worktree 上重跑 J1/J2、t1 全量。
- `local-bundle.ts` 的 OPFS 删除重试是超出 C1–C11 的附带修复（无它时全量约 2/5 次失败）；是否保留由审核确认。
- t1 参考截图摄于 `07a55a1db6`（C3 初版 8px 间隙），最终候选已 revert；只影响 3 张 preview 截图的按钮间距，正式重拍在 FE4b。

## 10. 十六进制回源

- 命令：`python3 -I frontend/scripts/check-handoff-hex.py --handoff docs/frontend-vnext/fe4a-handoff.md --git-objects --repo /home/dev/gdds-fe --sha-file /home/dev/fe4a-work/handoff-sha256.txt --allow 578e079b762e --allow 6dc9659f0aee`。
- 结果：`OK: 82 distinct full token(s), 0 truncated form(s)`。所有 7–12/40 位值解析为 git 对象（`578e079b762e`、`6dc9659f0aee` 为镜像 tag 后缀，用 `--allow` 声明）；所有 64 位值在 `/home/dev/fe4a-work/handoff-sha256.txt` 中命中；未出现长度异常。M1 的两个数值以千位分隔书写（`20 058 112`、`-1 835 008`），避免被当作十六进制 token。

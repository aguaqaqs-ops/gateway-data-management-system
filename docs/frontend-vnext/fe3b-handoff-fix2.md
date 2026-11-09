# FE3b 交接：复审第 1 轮定向修复（F1–F6）第 2 轮

复审报告 `docs/frontend-vnext/reviews/fe3b-rereview-1.md`（main `18e76dbbf0`）§4 的定向修复。
范围：只修 F1–F6，N1/N3/N5 顺手修；N2、N6 不改，留待 owner 看图确认；不做 FE3c。
本文件为单独的文档提交，不改动代码。

## 0. 摘要

- 分支 `fe-vnext`，范围 `4e0d074179..`（本文件提交）。
- 代码候选 **`8e6b8dd6f2`**（`frontend/` 树 `80e2344d`）；`vnext/` 树
  `56720104af`，与 `4e0d074179:vnext` 相同。相对 `4e0d074179` 的差异只含
  `frontend/` 下的 10 个文件（§5）。
- 07 `run-tests.sh --e2e --screenshots`（`GATEWAY_FE_TEST_WORKERS=2`）：exit 0，
  单测 32 文件 175 项、Playwright 60 项全过；截图 25 组 × 1280/1920。
- 05 `--suite journeys --subphase fe3b`：18/18，exit 0，`openapi_compare=match`，
  `cleanup_status=ok`。F1–F3 改了 hook，不影响真实旅程（§8.2）。
- `validate-upload-package.sh` 未重跑：脚本与输入均无变化（本轮差异只有
  `frontend/` 源码与用例，不碰 Dockerfile、依赖锁、基础镜像、entrypoint、
  Compose 与校验脚本本身），见 §8.3。
- 新回归探针 Q1–Q5 各使对应用例失败（§6），探针提交只在节点上，复审后已
  删除 worktree，保留提交 SHA 与日志 SHA 供复核。
- P1、P2、P4、E 的预期不变（仍应失败）；P3（去掉续做后状态更新）在新候选上
  应变为仅 W9 类失败（Q1 即其同类探针，见 §6）。

## 1. 合并与路径核对

| 项 | 结果 |
| --- | --- |
| 代码候选 | `8e6b8dd6f2`（§5 共 5 个提交） |
| `HEAD:frontend` | `80e2344d` |
| `HEAD:vnext` | `56720104af`（与 `4e0d074179:vnext` 相同） |
| `git diff --name-only 4e0d074179 HEAD`（除本文件） | 仅 `frontend/` 下的 10 个路径 |
| 未合入 main、未推送、未改写已有提交 | 是；探针提交只在 07 节点仓库的 detached worktree，`fe-vnext` 上只有 §5 的 5 个提交加本文件 |
| `legacy/` | 未入 Git；节点 worktree 以 `ln -s` 引用（`docs/...` 除外） |

## 2. F1–F6 逐条处理

### F1 续做提示与禁用原因同源（B3，§6.2）

- `useUploadModeState` 新增 `resumeNotice`（`use-upload-mode.ts`），按 §6.2
  第 1–3 步从**同一份快照**派生，与 `gates` 同源：
  - attempt 为 `ABORTED`：`提交未完成，请检查上传与 Preview 后重试` + 原始码；
  - 两个指针都为空、但 attempt 读不到：`无法读取提交结果，请刷新后重试`，
    按钮可用；
  - attempt 指针非空且读得到：提示与 §6.1 表一致（走 `gates.submit.reason`，
    例如 `提交结果待确认，需要管理员处理` + 操作 ID）；
  - attempt 或工作区读不到：`无法确认提交状态` + 重试。
- `ComparisonPage`、`WorkbenchPage` 删除各自的 `resumeMessage` /
  `submitResumeMessage` 状态，只渲染 hook 的 `resumeNotice`；
  `finishSubmitResume` / `resumeSubmitFromOperation` 只处理导航与操作卡片
  挂载，不再写提示。重试按钮沿用原入口（`refreshUploadMode` / `load()`），
  即从 §6.2 第 1 步重新开始并重新得出提示。
- 用例（`workspace-shell.spec.ts`）：W9②③分别断言“提交”按钮**自己的**
  禁用原因（`.compare-actions` 内该按钮的 `disabledReason`，不再用
  `getByText(...).first()`）与提示文本；点“重试”后断言旧提示消失
  （复审 §2.2 演示 a 转正）；新增 W9④（指针已清空、attempt 读不到一支）。
- 探针关系：Q1（同 P3）现在使 n3/W9①–④全部失败；以前 P3 在旧断言下
  55 项全过。

### F2 attempt 已结束而指针未清（B4，§6.2）

- `upload-header.ts`：工作区只有 `active_submit_attempt_id`、attempt 读到
  `FINALIZED`/`ABORTED` 时，`attemptPhase` 返回新增的 `stale`（不再返回
  `none` 解锁），门禁为 `无法确认提交状态` + 重试，并纳入一次性重读
  （`reread: true`）。重读后仍是该组合时保持该原因（新文案未定，沿用已有
  文案，未停下——理由：§6.2 已有“无法确认提交状态”覆盖此意，且按钮保持
  禁用满足“不在指针未清时解锁”）。
- 后端不改：读路径仍是单快照直出，过时指针由占用冲突 /
  `FinalizeRecoveryRequired` 表达（F2 研究结论），前端按过时快照重读。
- 改正单测 `judges by ... when the attempt is already closed`：改用单指针
  工作区（仅 `active_submission_id` + 陈旧 ABORTED attempt），双指针工作区
  违反 kickoff §5.3 与 control DB `CHECK`，不可达；补仅 attempt 指针 +
  `FINALIZED` / `ABORTED` 各一支。
- 新增 e2e（工作台）：第一次读到过时 attempt 指针 + `FINALIZED`，第二次读到
  `active_submission_id`（`PENDING`）；断言工作区读取恰好 2 次、“上传”全程
  不可用、最终原因为“已有待审核的提交，撤回后才能重新上传”。
  为留在工作台不断言漂移，夹具的操作保持轮询（`RUNNING`）：终态操作会
  触发已有的续做导航（到审核页），那是既有行为，不是本条要断言的。
- 附带产品修复（调试中发现的竞态）：重读效果可能撞上仍在途的挂载读取
  （attempt/operation 尾部未落），被去重吞掉导致重读丢失。现改为串行：
  有在途读取时等它落定后再重读一次（`de48668864`；W10 与 F2 共用该机制，
  各自仍恰好 2 次读取）。

### F3 404（B2，§6.1）

- 删除撤回 gate 中 404 的 `reread`，改为 `retry: true`；自动重读只保留
  §6.1 的四种情形。404 的“重试读取”按钮（即 §6.1 的“刷新”入口，
  `withdrawRetry` 已有接线）重新执行读取序列。
- 用例：单测补 404（一支：有 `retry`、无 `reread`）；`upload-mode.spec.ts`
  新增 F3 e2e：review 查询 404 时工作区只读 1 次、“刷新”可见；点“刷新”
  后读第 2 次（演示 d404 转正）。

### F4 模拟数据可达（B7，§5.3）

- D1–D5 改为可达链（`mock-data.ts`）：`d-arch` 从 `ref-1` 归档成
  `baseline-arch`，`d-closed` 为同一次归档（`archive-result-1`）关闭的同级
  提交（父基线同为 `ref-1`）；`d4` 的父基线为 `baseline-arch`，归档成
  `baseline-arch-2`（`archive-result-2`，其父基线与 `d4` 的父基线一致）；
  head 为 `baseline-arch-2`（新增 `DISPOSITION_HEAD`）；`d-manual` 挂在 head
  下（父基线仍是 head、无标记）；`d-arch`/`d-closed` 按推导规则带标记
  （`APPROVED` + 父基线不是 head；处置优先显示，D4 同理）。
  `d5` 移出 `DISPOSITION_SCENARIO_NODES`，只以 `DISPOSITION_D5_NODE` 供 D5
  用例使用，并标注“DC89 不可达，防御性”。
- `HISTORY_PAGE_TWO` 的 `fe2a-history-ref-old` 改为 D4 形态（`APPROVED` + 标记
  + `ARCHIVED` 处置，提升 `ref-1`；其父 `ref-0` 即 `ref-1` 的父，链不断），
  不再是共用数据中的 D5 形态。`TEST_HISTORY_CURSOR_SECOND` 的
  `submission-1` 保持 D5 形态但列入显式例外（Cursor 分页显示测试不断言
  处置，保持 intake 不变比改父基线影响小）。
- 可达性单测（`mock-data.test.ts`）覆盖全部模拟 History 数据
  （`HISTORY_PAGE_ONE/TWO`、合并页、`TEST_HISTORY_CURSOR_FIRST/SECOND`、
  合并 Cursor 页、处置场景集、D5 用例集）与三条归档链断言：
  - 标记非空当且仅当 `APPROVED` 且父基线不是 head（`projection.py:216`）；
    无标记的反向（`APPROVED` + 父非 head 必有标记）同步断言；
  - 父基线不是 head 的 `APPROVED` 提交必须有处置，只有显式 D5
    `ref_id` 例外（各数据集分别列出；注入式 Q4 探针使之失败）；
  - §5.3 处置组合规则（沿用 B7 单测并保留）；
  - 提升基线的父基线等于提交的父基线；同一父基线最多一个
    `ARCHIVED_BASELINE`；同一归档结果的 `CLOSED_NOT_ARCHIVED` + `ARCHIVE`
    同级提交与被归档提交父基线相同；归档基线成链且 head 为链末端；
  - 已处置提交不是任何工作区 fixture 的 `active_submission_id`。
- 受影响期望按新数据更新（未删除/放宽断言）：`workspace.test.ts` 的 stale
  行状态 `已通过`→`已归档`、归档主线原因按处置优先改为 `该提交已归档`
  （kickoff §6.4 修订 2 要求）；`submit-summary`、`client` 的 Cursor 断言
  不变。
- D1–D5 e2e 改用 `DISPOSITION_HEAD` + D5 节点；行选择改按提交标签
  （`提交 2..6`）而非 DOM 位置（重定父后顺序变化）。

### F5 必测与截图（B8，§9）

- D1/D2 审核模式用例加截图（`fe3b-d1/d2-review-topbar`，各 1280/1920，
  helper 本来就双宽度拍）。
- 新增 D3 审核模式用例：断言 `由 owner-9 于 {本地时间} 关闭`（悬停 title
  为 UTC 原值）与“查看关闭理由”展开，并截图。
- W6 的“刷新后找回操作卡片”改为 URL 中不带 `operationId`：断言 URL 被写入
  指针所指 attempt 的 `operation_id` 并出现操作卡片；工作台与 Preview 各
  一条（直接采用演示 c1/c2 的路径）。
- F4 改动后 D1–D5 截图与受影响 W 场景截图随全量重拍；`fe3b-withdraw-unknown`
  改为等 bundle 就绪（`waitForPreview`）后再拍（N3）。
- W9 三支与新 W9④、F2、F3、D3 均在此轮截图覆盖之外按常规 e2e 运行（无专属
  截图要求）；W9②③标题修正见 §4。

### F6 handoff（B9）

- 本文件即新 handoff（`docs/frontend-vnext/fe3b-handoff-fix2.md`），单独提交，
  不改已提交的 `fe3b-handoff-fix1.md`。复审 §4 F6 所列五处不符改正如下
  （§4 逐条）。

## 3. 非阻塞项（N1、N3、N5 修了；N2、N6 未动；N4 顺带）

- N1：`workspaceLoading` 初值改为 `true`（`use-upload-mode.ts`），首帧显示
  “正在读取提交状态”，不再闪“无法确认提交状态”。禁用的 hook 不渲染
  gates，无影响。
- N3：`fe3b-withdraw-unknown` 等 bundle 就绪后再拍（§2 F5），顶栏不再与
  提交挤在骨架屏上。
- N5：续做提示的码标改为 `操作ID`（恢复类）/`原始代码`（ABORTED 类）并可
  复制（两页Resume提示区）；其余错误码位置（撤回失败、对话框等）仍标
  “错误代码”，那是真正的错误码，不在此改。
- N2：未改。单行长理由仍不折叠，待 owner 看图确认。
- N6：未改。审核报告 N4（工作区节点“可提交”）仍待 owner 看图确认。
- N4：顺带 D1–D5 父基线与 head 对齐后，W6 等场景的 History 与工作区指针
  已一致（工作台 W6 用默认 History + attempt 指针，attempt 尚未入 History，
  与后端语义一致：未终局前无 History 节点）。

## 4. 复审 F6 五处不符对照改正

| 复审条目 | fix1 原文 | 本轮改正 |
| --- | --- | --- |
| §2 B2 W10 覆盖 | “Workspace 表与 Preview 页都覆盖” | 仅 Workspace 表：Preview 页后半段打开时工作区已经干净、无重读（hook 共用，功能上不缺）。用例 `W10 陈旧指针重读后恢复可用` 只在工作台验证重读计数 |
| §2 B6 校验镜像 tag | `fe-<HEAD12>` | 代码取 10 位：本次 05 日志 `rs_image_tag=gateway-repository-service:fe-8e6b8dd6f20b`（`8e6b8dd6f20b`，10 位十六进制） |
| §6 探针表 | 表头重复一次（fix1:199/201） | 本文件 §6 表头单行 |
| §2 B8 W6 | “刷新后找回操作卡片”有用例 | 旧用例 URL 中自带 `operationId`，没走指针路径；本轮改为无 `operationId` 进入并断言 URL 写入，两页各一条（§2 F5） |
| W9②标题 | “工作区与 attempt 都读不到” | 内容只有 attempt 读不到：标题改为“操作结束后 attempt 读不到时禁用并可重试恢复”（工作区读不到是 W9③） |

## 5. 提交序列（`4e0d074179` 之后）

| 提交 | 内容 |
| --- | --- |
| `ce7796fa78` | F1–F6 代码与用例主体（含 F1 hook 提示、F2 过时重读、F3 404、F4 可达数据、F5 用例截图、N1/N3/N5） |
| `5fe7e69ee8` | `mock-data.test.ts` 节点类型加宽（`tsc -b` 门禁：按 fixture 页推断的字面量联合装不下跨页合并数组，改用 `HistoryNodeResponse`） |
| `9aaeeded89` | e2e 与夹具对齐：W9④指针清空时序（照 n3）、D1–D5 按提交标签选行、F2 操作保持轮询以留在工作台 |
| `de48668864` | 产品竞态修复：一次性重读串行在在途读取之后（重读撞上挂载读取的 attempt/operation 尾部时曾被去重吞掉，F2 e2e 证实） |
| `8e6b8dd6f2` | W9④夹具：加载时用开放 attempt（`PREPARED`；fixture 默认 `FINALIZED` 会使加载快照直接过时，测不到续做路径） |
| （本文件） | 新建本文档 |

DC68 记录：`tsc -b` 字面量类型失败修一轮（加宽+复验）；3 个新 e2e 失败修三轮——
W9④ 加载时序 + D1–D5 标签选择 + F2 操作轮询（一轮）、F2 重读被吞的产品竞态
（一轮，`de48668864`）、W9④ 缺 `PREPARED`（一轮）。每轮都是先停后修再对受
影响步骤复验；无无修改重试。

## 6. 回归验证（一次性探针提交，只放在节点上）

探针 worktree 均已删除；下表为提交 SHA 与日志 SHA（07，
`/home/dev/gdds-fe-logs/fe3b/fix2/probes/<qx>/run.log`）。
Q1–Q5 的失败点与 §2 的新用例一一对应；某个探针被前面的单测阶段拦下时，
探针内跳过拦它的单测再跑 e2e（Q2、Q3 均如此）。

| 探针 | 节点提交（一词 `probe` 作者，节点专用） | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| Q1：续做结束后不更新 hook 状态（`readAttemptChain` 改为不写状态的直接读取，同复审 P3） | `3fbc15e8` | n3/W9①–④失败 | 4 个 W9 全失败（n3 卡片不挂载，②③④提示不出） | `01a5368b39bee7f193909e25815266eec9a6d819efd9aef979eb0faa57ac0d0` |
| Q2：恢复“attempt 已结束即解锁” | `3179416b` | F2 的单测 + e2e 失败 | 单测 `treats a closed attempt ... as stale` 失败（1/21），F2 e2e 失败 | `37315982bf15ba98518ea467de4ee533214bf9d75b14dbb6e6ffaf9daaf916e8` |
| Q3：恢复 404 的 reread | `0e1b2783` | F3 用例失败 | 单测 404 一支失败（1/21），F3 e2e 失败（读 2 次且无刷新入口） | `4aa9ce44db1bfd43efcce45e270b274d4b26c0835e62636c66e8060731ac8ed` |
| Q4：往共用 History fixture 注入父基线非 head、无标记的 APPROVED 节点 | `efd9be3c` | 可达性单测失败 | `mock-data.test.ts` 1/13 失败（注记完备性分支） | `72536e84451bc30a3bf3bf39f0223a149c1dcf4c5d3452280c8fa7259e1de35f` |
| Q5：去掉“按指针写入 URL” | `e14ac7e5` | 新的 W6 用例失败 | 工作台与 Preview 的指针路径各失败 1 支 | `27cb2a3044d4f9fd4cf822957fab5a9dea036617ae880bf9e172b90c22517d31` |

另：Q4 的注入同时验证了演示 e（往 `HISTORY_PAGE_TWO` 加不可达记录）会使
可达性单测失败——本轮可达性覆盖全部共用 fixture，不再是场景数组独享。

## 7. B1/B5/撤回保护与旧探针说明

- B1（步骤卡占用禁用，`UploadStepCard` 只禁“上传并生成预览”）、B2（一次性
  重读，`rereadKey` + `rereadConsumed` + 在途串行）、B5（bundle/服务器码透传
  与文案）、撤回携带 `review_version`（`ReviewActions` + `confirmWithdraw`
  双页）均未削弱：本轮 diff 不碰这些路径（`git diff` 见 §1）。
- P1、P2、P4、E 在新候选上的预期与复审第 1 轮相同（各使对应用例失败），
  复审第 2 轮可照常重跑；P3（去掉续做后状态更新）在旧断言下 55 项全过，
  在本轮 W9②③④ + n3 加强断言下应变为仅 W9 类失败（Q1 已证）。

## 8. 证据与运行记录

### 8.1 07（`gw-dms-07`）mock 全量（最终候选 `8e6b8dd6f2`）

- 入口：`frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-shots/fe3b-fix2-8e6b8dd6`，`GATEWAY_FE_TEST_WORKERS=2`；
  clean detached worktree `/home/dev/gdds-fe-fix2-8e6b8dd6`（legacy 软链），运行期间未写 worktree。
- 起止 HEAD 都是 `8e6b8dd6f2`；`frontend/` 树 `80e2344d`，`vnext/` 树 `56720104af`。
- 结果：exit 0。`tsc -b`、`eslint`、`test:unit`（32 文件 175 项）、生产构建 +
  `check-production-build`、`test:e2e`（60 项）全过。
- 工具链镜像 tag `mcr.microsoft.com/playwright:v1.64.1-noble`，config digest
  `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，
  全部 RootFS DiffID 见日志头；npm 缓存归档 `0d861824…0089f4`（305 个
  `resolved`，registry 归一）。
- 截图 25 组 × 1280/1920（含新增 `fe3b-d1/d2/d3-review-topbar`、
  `fe3b-w6-preview-resumed-card`），目录上述 `--screenshots` 参数。
- 日志：`/home/dev/gdds-fe-logs/fe3b/fix2/07-run-tests.log`，
  SHA256 `7e36418a8e1d5bd56d6b4beaa337ac0f4fd3ddd7751fcb84409ad16f5d437`
  （起 2026-11-08T16:42:27Z，止 16:44:24Z，`hostname=gw-dms-07`）。

### 8.2 05（`gw-dms-test-05`）真实 journeys（最终候选 `8e6b8dd6f2`）

- 入口：`frontend/scripts/run-real-backend-e2e.sh --suite journeys --subphase fe3b --session fe3b-impl-fix2 --log-dir /home/dev/gdds-fe-logs/fe3b/fix2 --evidence-dir /home/dev/gdds-fe-shots/fe3b-fix2-8e6b8dd6-real`
  （脚本自行取得/释放 DC70 占用，外层未取）；
  npm 缓存显式设置 `GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache`、
  `GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE=/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`；
  clean detached worktree `/home/dev/gdds-fe-fix2-8e6b8dd6`（legacy 软链）。
- 起止 HEAD 都是 `8e6b8dd6f2`；起 2026-11-08T16:44:33Z，止 16:50:09Z。
- 结果：exit 0，18/18 passed（r1–r11 全绿），`openapi_compare=match`，
  `cleanup_status=ok`，日志无 token。
- RS 镜像 tag `gateway-repository-service:fe-8e6b8dd6f20b`（10 位，见 §4），
  config digest `sha256:cbb2b6d15939076c5f38e488576e666c14571189583ebf86e80e58f28c2a900e`，
  全部 RootFS DiffID 见日志；工具链镜像身份同 07。
- 日志：`/home/dev/gdds-fe-logs/fe3b/fix2/real-backend-e2e-journeys-fe3b-impl-fix2-8e6b8dd6f-20261108T164433Z-1754.log`，
  SHA256 `c90f2440c4cac690f3562e1dd45af81008c0bdc854f6579dc3720ba035a00461`。

### 8.3 `validate-upload-package.sh` 未重跑的理由

脚本与全部输入均无变化：本轮 5 个提交只改 `frontend/` 源码、单测与模拟
e2e，不碰 Dockerfile、依赖锁、基础镜像、entrypoint、Compose、环境变量接线
与校验脚本本身；`vnext/` 树不变（§1）。按任务约定不重跑。

### 8.4 调试与取证分工（DC30）

- 调试：07 focused（W9/F2/D1-D5/D3/F3/W10/W6 子集，`9aaeeded89`→`de48668864`→`8e6b8dd6f2`
  三轮收敛）、05 journeys、Q1–Q5 探针，日志与 worktree 见上。
- 取证：08.1–8.2 即最终候选上的完整权威运行各一次；04 取证与 04
  `validate-upload-package.sh`（如需）待复审通过后按 kickoff §9 执行。

## 9. 保留与清理

- 保留供复审第 2 轮对照（FE3b 退出后清理）：07/05 的
  `/home/dev/gdds-fe-fix2-8e6b8dd6`（detached HEAD `8e6b8dd6f2`，clean）与
  `refs/review/fe3b-fix2/candidate`；两节点的 `/home/dev/gdds-fe-logs/fe3b/fix2/`
 （含探针 `probes/q1..q5` 日志与 trace）、07 的截图目录、
  05 的 evidence 目录；传输用 bundle（`/tmp/fe3b-fix2-*.bundle` 开发主机、
  `/home/dev/gdds-fe-logs/*.bundle` 两节点）。
- 已删除：07 的 `gdds-fe-fix2-ce7796fa/5fe7e69e/9aaeeded/de486688` 中间
  worktree、Q1–Q5 探针 worktree 与其 `refs/probe/*`（从未进 `fe-vnext`）。
- 第 1 轮保留项不变（开发主机 `gdds-fe-review-fe3b-afd7711e`、05/07 的
  review worktree 与 `refs/review/fe3b-rr1/*`）。

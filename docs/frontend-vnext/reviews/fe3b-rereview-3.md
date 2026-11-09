# FE3b 复审第 3 轮

- **审核对象：** 分支 `fe-vnext`，范围 `4ff1c11396..88237dbc3b`。
  - 代码候选 `1e5c43ee65`，`frontend/` 树 `0ed4a3885a`；
  - handoff 提交 `88237dbc3b`（只新增 `docs/frontend-vnext/fe3b-handoff-fix3.md`，`frontend/` 树相同）。
- **依据：** [复审第 2 轮报告](fe3b-rereview-2.md)（`cb2b8b6f9b`）§4–§6；[FE3 kickoff](../fe3-kickoff.md)（main `885f5c4b64`）§5.3、§6.1、§6.2、§9；新 handoff。
- **日期：** 2026-11-09。
- **结论：通过。** G1–G4 都已修复，没有新的阻塞项，可以进入 04 取证（§6）。
  - G1：续做提示的“重试”改走 hook 的同一入口 `retryResume`，两个指针都为空时仍按已知 attempt ID 重读，符合 §6.2 第 2 步。探针证实预览页的接线有用例保护；工作台页的接线没有用例覆盖，列为非阻塞 N5；
  - G2：404 的入口文字为“刷新”，其他行保持“重试读取”，两个方向都有用例保护；
  - G3：§5.3 组合规则对 8 个模拟 History 数据集逐个执行。Q4b 与我新加的两个数据变体都使单测失败；
  - G4：fix3 handoff 改正了四处错误，20 个 64 位 SHA 与节点文件一致；
  - N1（D1–D3 顶栏截图等 bundle 就绪再拍）已修；N2 未改，继续列为非阻塞；
  - 我在 05 的独立运行（mock 全量与真实 journeys）都通过；第 2 轮的回归探针 P1–P4、R1、Q2–Q4、E 仍按预期失败。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| `git rev-parse 1e5c43ee65:vnext`、`88237dbc3b:vnext` | 都是 `56720104af34a1eb677336f57bdbc07444a56615` |
| `git diff --name-only 748de5034d 88237dbc3b` | 只含 `frontend/` 与 `docs/frontend-vnext/` |
| `git diff --name-only 4ff1c11396 88237dbc3b` | `frontend/` 下 8 个文件，加 `docs/frontend-vnext/fe3b-handoff-fix3.md` |
| `git log --merges 4ff1c11396..88237dbc3b` | 无合入 |
| 提交序列 | `85e9b34f53`、`4e0c1285e9`、`1e5c43ee65`、`88237dbc3b`，与 handoff §5 一致 |

本轮改动（`4ff1c11396..1e5c43ee65`，8 个文件，+244/−64）：

| 内容 | 文件 |
| --- | --- |
| hook：`retryResume`（与续做共用 §6.2 序列） | `use-upload-mode.ts` |
| gates：`retryLabel`（404 为“刷新”） | `upload-header.ts`、`upload-header.test.ts` |
| 两页的提示“重试”改用 `retryResume`；预览页撤回入口透传标签 | `ComparisonPage.tsx`、`WorkbenchPage.tsx` |
| §5.3 组合规则覆盖全部数据集 | `mock-data.test.ts` |
| 模拟 e2e：r2a、W9③b、W9④ 改写、F3 改写、N1 | `workspace-shell.spec.ts`、`upload-mode.spec.ts` |

## 2. 独立运行与探针

我在开发主机建了 `refs/review/fe3b-rr3/candidate`（`1e5c43ee65`）与 `refs/review/fe3b-rr3/handoff`（`88237dbc3b`），以 git bundle 传入 05。bundle 内容为 `8e6b8dd6f2..88237dbc3b`，SHA256 `1aa6192e…91e6`。在 detached worktree `/home/dev/gdds-fe-rereview3-fe3b` 上运行，运行前后都 clean，起止 HEAD 都是 `1e5c43ee65`。日志目录 `/home/dev/gdds-fe-logs/fe3b/rereview-3/`。

节点选择与占用：

- 运行前：04 有 S4 的计时测量标记（`s4-e … sample=warm`），04/06/07 同宿主；ct108 有 S3 的 W3 运行标记。为不干扰计时，本轮全部放在独立宿主的 05 上顺序运行。
- 05 运行前没有占用标记。mock 全量与 15 个模拟探针在我以 `fe3b-rereview-3` 取得的标记下完成（01:24:50Z 起），结束后释放；两次 journeys 由脚本自行取得、释放标记，没有残留容器。
- 收尾时 05 出现了他人的标记（`s4-e-dc98-minimal-t4-r0`，02:38:14Z 起），晚于我的运行结束（02:05:37Z）。我没有动它。

### 2.1 独立运行

| 节点 | 运行 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 05（`gw-dms-test-05`） | `run-tests.sh --e2e --screenshots`，`GATEWAY_FE_TEST_WORKERS=2`，npm 缓存两变量指向 `/home/dev/gdds-fe-cache/fe0/`，01:24:50–01:27:10Z | exit 0：单测 32 个文件 175 项，Playwright 61 项；截图 146 张（`fe3b-*` 25 组 × 2 宽度），目录 `/home/dev/gdds-fe-shots/fe3b-rereview3-1e5c43ee`，清单 `shots.sha256` 的 SHA256 为 `699bf1fd…b407`；工具链 config digest `sha256:a0d7b2b4…a1017` | 入口日志 `a63fa0f4…3a05`；外层 `307feaa9…7fcb` |
| 05（`gw-dms-test-05`） | `run-real-backend-e2e.sh --suite journeys --subphase fe3b --session fe3b-rereview-3`，01:53:14–01:58:28Z | exit 0：18 passed；`openapi_compare=match`；`cleanup_status=ok`；日志无 token；RS tag `gateway-repository-service:fe-1e5c43ee656f`，config digest `sha256:f2ba8cfc…af09`（与 handoff §8.2 相同） | 入口日志 `049c9f6f…1a76`；外层 `1fcebe41…bcf3` |

### 2.2 探针（已提交的一次性 worktree，只在 05 上）

| 探针 | 提交 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| G1c：预览页提示“重试”改回 `refreshUploadMode()` | `34a37ff665` | W9 类失败 | **符合**：n3/W9①、W9③b、W9④ 失败，58 passed | `976e3064…4a9b` |
| G1w：工作台页提示“重试”改回 `load()` | `3dcf9c9a07` | 记录覆盖情况 | **全部通过**（175 单测、61 e2e）：工作台页的接线没有用例覆盖，见 N5 | `36cc58f0…9435` |
| G2：404 改回“重试读取”（单测跳过） | `4a74f28199` | F3 e2e 失败 | **符合**：只有 F3 失败 | `23deff27…4647` |
| G2b：非 404 的 review 读取失败行误标“刷新” | `a2cd918de9` | 单测失败 | **符合**：`offers a manual refresh…` 失败 | `20a0f2ad…ff96` |
| Q4b：共用 `fe2a-history-ref-old` 改为 `ARCHIVED_BASELINE` + `MANUAL_CLOSE` | `afb0d28688` | 单测失败 | **符合**：组合规则在 `HISTORY_PAGE_TWO fe2a-history-ref-old archive source` 处失败 | `e0827063…4001` |
| Q4c：共用 `fe2a-history-ref-old` 的提升基线指向不存在的节点 | `440f39b104` | 单测失败 | **符合**：组合规则（单页与合并页）与链断言都失败 | `3feb03e8…0386` |
| Q4d：Cursor 页 `submission-1` 加 `MANUAL_CLOSE` 而无 `closure` | `52c1bf24e6` | 单测失败 | **符合**：组合规则在 `TEST_HISTORY_CURSOR_SECOND submission-1 closure` 处失败（可达性断言也失败） | `d2dcdbee…564e` |
| P1：步骤卡不接收占用原因 | `769b4a786f` | W8 失败 | **符合**：只有 W8 失败 | `6b510782…6544` |
| P2：去掉一次性重读（直接与串行两处） | `8ebf484101` | W10 失败 | **符合**：W10 与 F2 失败 | `d94af67b…66b2` |
| P3：续做读取 attempt 时不更新 hook 状态 | `bc937c4d2f` | W9 类失败 | **符合**：n3/W9①、W9②、W9③b、W9④ 失败 | `2167f1aa…115b` |
| P4：bundle 服务器码改回固定码 | `dcdf596c01` | 对应用例失败 | **符合**：只有“bundle 接口失败显示可重试错误页”失败 | `5819c63e…1c01` |
| R1：撤掉重读的在途串行 | `5bf08e476b` | F2 失败 | **符合**：只有 F2 失败 | `c934e4bb…077f` |
| Q2：过时 attempt 改回解锁（单测跳过） | `1d3889d3d0` | F2 e2e 失败 | **符合**：只有 F2 失败 | `2c35559f…971e` |
| Q3：404 恢复重读（单测跳过） | `843b55755e` | F3 e2e 失败 | **符合**：只有 F3 失败 | `27ed55fa…0547` |
| Q4：共用 `HISTORY_PAGE_TWO` 注入 D5 形态节点 | `b9827a0bb8` | 可达性单测失败 | **符合**：可达性单测失败（另有两条显示断言随数据变化失败） | `f091ccf9…b1b3` |
| E：撤回改发工作区 `optimistic_version` | `20b84d9361` | `r7-withdraw` 失败 | **符合**：只有 `r7-withdraw` 失败，17 passed，`cleanup_status=ok` | 外层 `2107c777…82ab`；入口 `1455e494…49ec` |

G2、Q2、Q3 在探针提交内用 `it.skip` 跳过各自拦截的那一条单测，再跑 e2e（与 handoff §6 做法相同）；其余探针都没有被前面的阶段拦下。各探针的 diff 存于 05 的 `probes/probe-*.diff` 与 `probe-e.diff`。探针 worktree、`refs/review/fe3b-rr3/probe-*`、节点上的传输 bundle 与探针脚本目录都已删除。

## 3. 逐项核对

### G1 续做提示的“重试”：符合

- `retryResume` 就是此前 `resumeAfterOperation` 的序列，`resumeAfterOperation` 现在只是委托给它：
  1. 读工作区，读不到则 `workspaceProblem`，提示“无法确认提交状态”，gates 禁用并带重试，不自动循环；
  2. `active_submission_id` 非空：读 review，两页按续做的 `submitted` 处理导航到 REVIEW；
  3. 否则取 `active_submit_attempt_id ?? attemptIdRef.current`：两个指针都为空时仍按已知 ID 重读 attempt 与操作。`ABORTED` 显示“提交未完成…”与原始代码，读不到显示“无法读取提交结果，请刷新后重试”。指针为空时 `attemptPhase` 为 `none`，“提交”“上传”保持可用；
  4. 没有已知 ID：`empty`，提示“提交未完成…”。
- 两页的提示“重试”都改用 `retryResume`，`refresh()`/`load()` 只留给挂载、模式切换与撤回冲突。
- 用例：r2a 已并入 n3/W9①；W9④ 拆成“仍读不到”和“可读且 `ABORTED`”两段；新增 W9③b（工作区恢复、指针为空、按已知 ID 读取 `attempt-1`）。三支都断言 attempt 读取次数增加。G1c 与 P3 使这三支失败。
- 工作台页的提示“重试”没有用例（G1w 全部通过），见 N5。工作台页 `retryResumeNotice` 的代码与预览页相同，仅多一次 History 重载，代码阅读无误。

### G2 404 的“刷新”入口：符合

`Gate.retryLabel` 只在 review 404 行取“刷新”，工作区读不到、attempt 读不到、`stale`、review 其他读取失败都取“重试读取”；`PreviewHeaderActions` 透传标签，点击行为仍是重新执行读取序列。单测同时断言 404 与 500 两行；F3 e2e 断言“刷新”可见、“重试读取”为 0 个、点击后工作区读取 1→2。G2、G2b、Q3 三个方向的探针都失败。

### G3 §5.3 组合规则覆盖全部模拟 History 数据：符合

`checkDispositionCombinationRules` 对共用两页、合并共用页、两个 Cursor 页、合并 Cursor 页、场景集、D5 用例集各执行一遍，规则与 §5.3 一致，已有的 Review/History 一致性断言与链断言没有放宽。单页切片允许提升基线等于 head 而不在数组里（共用第 2 页就是这种情况）；合并页中 head 在数组里，仍按 `ARCHIVED_SUBMISSION` 检查。Q4b、Q4c、Q4d 都失败，Q4c 同时被合并页的“提升基线存在”断言拦下。

### G4 handoff：符合

- 第 2 轮 §3 F6 列出的四处都已改正：RS tag 12 位、校验镜像 10 位；Q1、Q3、07 run-tests 三个 SHA；演示 e 的说法；D3 截图的说法。
- 我对照节点文件核对了 fix3 中全部 20 个 64 位 SHA：07 的 fix3 运行日志、首轮失败日志、6 个探针日志、3 个 fix2 日志，05 的两份 journeys 日志，以及内层 `frontend-tests` 日志（在 07 的 `/home/dev/gdds-fe-logs/frontend/` 下），都一致。文中唯一的 61 位串是表里照录的 fix2 原文错值。
- 小处（不影响结论，退出清理时一并处理）：
  - §8.1 没写内层 `frontend-tests` 日志的路径；
  - 07 上还有 `07-run-tests-retry1.log`（`4e0c1285e9` 上的中间运行，exit 0），handoff 没提；它是修订后的复验，不是无修改重试；
  - §9 说中间 worktree 已删，但 07 上 `refs/tmp/fe3b-fix3-85e9b`、`refs/tmp/fe3b-fix3-4e0c12` 仍在；另有更早一轮留下的 worktree `/home/dev/gdds-fe-fix3-069a8f65`（HEAD `069a8f65`，11-08 建）；
  - §8.2 的起始时间写作“01:07:56Z 左右”，日志头有准确值。

### N1 截图：符合

`fe3b-d1/d2/d3-review-topbar` 现在拍的是 bundle 加载完的页面。D3 在 1280 宽度下面包屑挤压，展开的关闭理由把顶栏撑高，属于已交 owner 看图的 N3/N4 一类，不是新问题。

## 4. 需要修复（阻塞）

无。

## 5. 非阻塞

- **N2（沿用）：** `resumeNotice` 在页面生命周期内不归零，再次提交后的“提交正在执行…”仍会显示在红色提示框里。本轮未改，handoff §3 已如实说明。
- **N3、N4（沿用）：** `fe3b-withdraw-unknown` 中按钮间距；长关闭理由不折叠（D3 截图可见）；被占用时工作区节点仍标“可提交”。交 owner 看图确认。
- **N5（新）：** 工作台页的提示“重试”没有用例覆盖，探针 G1w 把它改回 `load()` 后全部通过。G1 的原始缺陷正是页面接线，建议补一条工作台页用例（ABORTED 后点“重试”，提示与原始代码仍在、attempt 读取次数增加），可在 FE3c 或退出前的小修中完成，由 owner 决定。
- **N6（新，小）：**
  - `retryResume` 不经过 `refresh()` 的在途合并，快速连点“重试”会并行两次读取序列，结果以后完成者为准，不影响正确性；
  - W9④ 第一次重试后断言的提示文字与重试前相同，这一句本身不能区分新旧状态，靠随后的 attempt 读取计数把关；
  - G3 的“提升基线等于 head 可不在数组里”的放宽也作用于合并数据集，可只对单页切片放宽。

## 6. 下一步

1. 04 取证（kickoff §9 FE3b 行）：在最终候选 `1e5c43ee65` 上运行 `run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`run-real-backend-e2e.sh --suite journeys --subphase fe3b` 各一次。04 当前有 S4 的计时测量标记，须等标记释放后再开始。
2. §6、§6.4 截图交 owner 确认（含 N3、N4），N5 由 owner 决定是否在退出前补。取证后做证据核对，再给出 FE3b 退出建议。
3. 本轮遗留：
   - 已删除：探针 worktree、`refs/review/fe3b-rr3/probe-*`、05 上的传输 bundle 与探针脚本目录、开发主机上的 bundle；
   - 保留供对照，FE3b 退出后清理：
     - 05 的 `/home/dev/gdds-fe-rereview3-fe3b` 与 `refs/review/fe3b-rr3/{candidate,handoff}`；
     - 开发主机的 `refs/review/fe3b-rr3/{candidate,handoff}`；
     - 05 的 `/home/dev/gdds-fe-logs/fe3b/rereview-3/` 与截图目录 `/home/dev/gdds-fe-shots/fe3b-rereview3-1e5c43ee`；
   - 第 1、2 轮保留项不变。

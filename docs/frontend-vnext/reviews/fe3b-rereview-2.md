# FE3b 复审第 2 轮

- **审核对象：** 分支 `fe-vnext`，范围 `4e0d074179..4ff1c11396`。
  - 代码候选 `8e6b8dd6f2`，`frontend/` 树 `80e2344daf`；
  - handoff 提交 `4ff1c11396`（只新增 `docs/frontend-vnext/fe3b-handoff-fix2.md`，`frontend/` 树相同）。
- **依据：** [复审第 1 轮报告](fe3b-rereview-1.md)（`18e76dbbf0`）§4–§6；[FE3 kickoff](../fe3-kickoff.md)（main `885f5c4b64`）§5.3、§6.1、§6.2、§9；FE2 kickoff §7.5；新 handoff。
- **日期：** 2026-11-08。
- **结论：定向修复。** 范围比上一轮小，不需要重写。
  - 已做到：
    - 路径核对通过；
    - F2、F5 完整修复，F3 只差 404 的“刷新”入口；
    - F1 的提示改由 hook 从同一份快照派生，W9 断言改为按钮自身原因；P3 同类探针现在使 n3/W9①②④ 失败；
    - F4 的 D1–D5 改成可达链，D5 形态移出共用 fixture，注记与处置的存在性断言覆盖全部模拟 History 数据；
    - 在途读取与重读的竞态修复有用例保护（探针 R1）；
    - 我在 07、05 的独立运行都通过；第 1 轮的 P1–P4、E 与新加的 Q2–Q4 都按预期失败。
  - 需要修复（§4）：
    - G1：续做提示点“重试”后，指针为空时不再保留原提示（丢失原始代码，或在没读 attempt 的情况下改写为“提交未完成”）。§6.2 第 2 步要求保留原提示，新用例 W9④ 断言的恰好是相反行为；
    - G2：review 404 仍只有通用的“重试读取”，§6.1 要求附“刷新”；
    - G3：§5.3 处置组合规则仍只检查场景数组。第 1 轮演示 e 原样注入共用 fixture 后，单测全部通过；
    - G4：handoff 有几处与实际不符（三个日志 SHA、镜像 tag 位数、演示 e 的覆盖说法、D3 截图说法）。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| `git rev-parse 8e6b8dd6f2:vnext`、`4ff1c11396:vnext` | 都是 `56720104af34a1eb677336f57bdbc07444a56615` |
| `git diff --name-only 748de5034d 4ff1c11396` | 只含 `frontend/` 与 `docs/frontend-vnext/` |
| `git diff --name-only 4e0d074179 4ff1c11396` | `frontend/` 下 10 个文件，加 `docs/frontend-vnext/fe3b-handoff-fix2.md` |
| `git log --merges 4e0d074179..4ff1c11396` | 无合入 |
| 提交序列 | `ce7796fa78`、`5fe7e69ee8`、`9aaeeded89`、`de48668864`、`8e6b8dd6f2`、`4ff1c11396`，与 handoff §5 一致 |

本轮改动（`4e0d074179..8e6b8dd6f2`，10 个文件，+469/−57）：

| 内容 | 文件 |
| --- | --- |
| hook：续做提示、N1 初值、重读串行 | `use-upload-mode.ts` |
| gates：`stale` 阶段、404 去掉重读 | `upload-header.ts`、`upload-header.test.ts` |
| 两页改用 hook 的提示 | `ComparisonPage.tsx`、`WorkbenchPage.tsx` |
| 可达链数据与断言 | `mock-data.ts`、`mock-data.test.ts`、`workspace.test.ts` |
| 模拟 e2e | `upload-mode.spec.ts`、`workspace-shell.spec.ts` |

`validate-upload-package.sh` 本轮没有重跑。区间没有改动 `frontend/scripts/`、Dockerfile、依赖锁或 `vnext/`，同意 handoff §8.3 的理由。

## 2. 独立运行与探针

我在开发主机建了 `refs/review/fe3b-rr2/candidate`（`4ff1c11396`），以 git bundle 传入两节点。bundle 内容为 `4e0d074179..4ff1c11396`，SHA256 `b8accca1…0c144`。在 detached worktree `/home/dev/gdds-fe-rereview2-fe3b` 上运行，运行前后都 clean，起止 HEAD 都是 `4ff1c11396`。日志目录两节点都是 `/home/dev/gdds-fe-logs/fe3b/rereview-2/`。

占用情况：

- 07：运行前没有占用标记。我以 `fe3b-rereview-2` 取得标记，独立运行与全部探针都在同一标记下完成，结束后已释放。
- 05：运行前没有占用标记。两次 journeys 都由脚本自行取得、释放标记（会话 `fe3b-rereview-2`），没有残留容器。
- 05 收尾时出现了他人的标记（`p6-s4-e-05-6786-source-prep`，23:38:23Z 起），晚于我的运行结束。我没有动它。

### 2.1 独立运行

| 节点 | 运行 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 07（`gw-dms-07`） | `run-tests.sh --e2e --screenshots`，`GATEWAY_FE_TEST_WORKERS=2`，23:16:18–23:18:38Z | exit 0：单测 32 个文件 175 项，Playwright 60 项；截图 146 张（`fe3b-*` 25 组 × 2 宽度），目录 `/home/dev/gdds-fe-shots/fe3b-rereview2-4ff1c113`，清单 `shots.sha256` 的 SHA256 为 `20f5ed5a…9fb1`；工具链 config digest `sha256:a0d7b2b4…a1017` | 入口日志 `fc31f73a…214e`；外层 `06e0ccf8…c1a0` |
| 05（`gw-dms-test-05`） | `run-real-backend-e2e.sh --suite journeys --subphase fe3b --session fe3b-rereview-2`，23:16:32–23:21:57Z；npm 缓存两变量指向 `/home/dev/gdds-fe-cache/fe0/` | exit 0：18 passed；`openapi_compare=match`；`cleanup_status=ok`；RS tag `gateway-repository-service:fe-4ff1c1139662`，config digest `sha256:68f54131…05fc` | 入口日志 `2ca90078…10f9`；外层 `33d9874d…b845` |

### 2.2 探针（已提交的一次性 worktree，只在节点上）

| 探针 | 提交 | 节点 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- |
| P1：步骤卡不接收占用原因 | `0d14649948` | 07 | W8 失败 | **符合**：只有 W8 失败 | `74c847b5…8946` |
| P2：去掉一次性重读（直接与串行两处） | `1f73fbe5c2` | 07 | W10 失败 | **符合**：W10 与 F2 两条失败 | `f6947540…d79c` |
| P3：续做后不更新 hook 状态（同第 1 轮 P3） | `d5672ce088` | 07 | W9 类失败 | **符合**：n3/W9①、W9②、W9④ 失败。W9③是工作区读不到的分支，不经过被改的读取，不失败是正确的 | `3c00c0f4…bd07` |
| P4：bundle 服务器码改回固定码 | `7b938630b0` | 07 | 对应用例失败 | **符合**：只有“bundle 接口失败显示可重试错误页”失败 | `a5c8e12c…61a2` |
| E：撤回改发工作区 `optimistic_version` | `4db4894b9c` | 05 | `r7-withdraw` 失败 | **符合**：只有 `r7-withdraw` 失败，17 passed，清理正常 | 外层 `f69c1862…4ebea`；入口 `71eee943…352c` |
| R1：撤掉重读的在途串行（`de48668864`） | `50fd647fdb` | 07 | F2 或 W10 失败 | **符合**：F2 用例失败。竞态修复有用例保护 | `af4daee1…30a6` |
| Q2：过时 attempt 改回解锁（单测跳过） | `9afed3fbc5` | 07 | F2 e2e 失败 | **符合**：F2 用例失败 | `c0f907e3…f4f1` |
| Q3：404 恢复重读（单测跳过） | `00e6204694` | 07 | F3 e2e 失败 | **符合**：F3 用例失败 | `3c22a43c…ab13` |
| Q4：共用 `HISTORY_PAGE_TWO` 注入 D5 形态节点 | `7e7e63d4ea` | 07 | 可达性单测失败 | **符合**：`keeps every simulated History dataset reachable` 失败（另有两条显示断言随数据变化失败） | `28d4984c…f8ca` |
| Q4b：第 1 轮演示 e 原样注入：共用 `fe2a-history-ref-old` 改为 `ARCHIVED_BASELINE` + `MANUAL_CLOSE` | `d6e731c99b` | 07 | 单测失败 | **不符合：175 项全部通过**，见 G3 | `ee0e2a63…f2f0f` |
| 演示 r2a：n3/W9① 末尾点“重试”，断言提示与 `IMPORT_REJECTED` 仍在 | `3fa737f353` | 07 | 产品正确时通过 | **失败**：提示仍是“提交未完成…”，`IMPORT_REJECTED` 消失，见 G1 | `6a2c0909…24eb` |

P1、P3、P4、R1、Q4、Q4b、演示 r2a 都没有被前面的单测阶段拦下。Q2、Q3 在探针提交内用 `it.skip` 跳过各自拦截的那一条单测，再跑 e2e（handoff §6 用的是同一做法）。各探针的 diff 存于 07 的 `probes/probe-*.diff` 与 05 的 `probe-e.diff`。探针 worktree、`refs/review/fe3b-rr2/probe-*`、节点上的传输 bundle 与探针脚本目录都已删除。

## 3. 逐项核对

### F1 续做提示与禁用原因：部分符合（G1）

- **符合：**
  - 两页删掉了本地提示状态，`resumeNotice` 与 `gates` 来自 hook 的同一份快照；
  - W9②③改为分别断言 `.compare-actions` 内“提交”按钮自己的原因与 `role=alert` 的提示，并断言点“重试”后旧提示消失（第 1 轮演示 a 已转为正式用例）；
  - 新增 W9④（指针已清空、attempt 读不到）；P3 现在使 W9 类用例失败；
  - N5 已改：码标为“操作ID”或“原始代码”，并可复制。
- **不符合：** 点“重试”只调用不带续做语义的 `refresh()`。两个指针都为空时，`refresh()` 会清掉已读到的 attempt（`clearAttemptChain`），提示随即落到 `resumeNotice` 的最后一支，得到“提交未完成…”且没有代码（`use-upload-mode.ts` 的 `resumeNotice`）。后果有三：
  - ABORTED 后点“重试”，原始代码丢失（演示 r2a）；
  - W9④点“重试”后，提示从“无法读取提交结果，请刷新后重试”变成“提交未完成，请检查上传与 Preview 后重试”，而这期间没有读取 attempt。W9④的最后三行断言的正是这一变化（`workspace-shell.spec.ts` W9④）；
  - W9③（工作区读不到）点“重试”后，若指针已空，也会不读 attempt 就显示“提交未完成”（代码阅读）。

  §6.2 第 2 步写明：两个指针都为空时，“提交”“上传”可用，**保留原提示**（“提交未完成…”或“无法读取提交结果，请刷新后重试”）。“重试”应从第 1 步重新执行这一序列，而不是只重读工作区。handoff §2 F1 写“重试从 §6.2 第 1 步重新开始并重新得出提示”，与实际行为不符。

### F2 attempt 已结束而指针未清：符合

- 新增 `stale` 阶段：禁用，原因“无法确认提交状态”，带 `retry` 与 `reread`，纳入一次性重读；
- 单测改为单指针工作区，补齐 `FINALIZED`/`ABORTED` 两支；工作台 e2e 断言两次读取、上传全程禁用、最终原因为待审核；
- Q2 使 F2 e2e 失败。重读撞上在途读取时会被去重吞掉，这个竞态的修复（`de48668864`）由 R1 证实有用例保护；
- 小问题（非阻塞，见 N2）：`ABORTED` + 指针未清的过时快照，在重读完成前提示显示“提交未完成…”，按钮原因是“无法确认提交状态”。这只是一次重读的瞬间，重读后两者一致。

### F3 404：部分符合（G2）

- 符合：404 不再自动重读（单测与 e2e 都断言读取 1 次，Q3 使 e2e 失败），点入口后重读 1 次。
- 不符合：§6.1 的表把 404 一行写作“未找到该提交，请刷新后重试（另附‘刷新’）”，与其他几行的“另附‘重试’”有意区分。实现仍用通用的“重试读取”按钮，用例断言的也是“重试读取”（`upload-mode.spec.ts` F3）。

### F4 模拟数据可达：部分符合（G3）

- **符合：**
  - D1–D5 改成可达链：`ref-1 → baseline-arch → baseline-arch-2(head)`，`d-closed` 与 `d-arch` 同父、同一归档结果；`d4` 挂在 `baseline-arch` 下；`d-manual` 挂在 head 下；
  - D5 只留在 `DISPOSITION_D5_NODE`，并标为 DC89 防御性数据；
  - `fe2a-history-ref-old` 改为 D4 形态，与 `ref-1`（`ARCHIVED_SUBMISSION`，父 `ref-0`）成链；`submission-1` 作为显式 D5 例外列出；
  - 新断言覆盖全部模拟 History 数据：注记当且仅当 `APPROVED` 且父基线不是 head；父基线非 head 的 `APPROVED` 必须有处置（例外按 ref 列出）；归档链、提升基线父基线、同父唯一 `ARCHIVED_BASELINE`、同结果关闭同级同父；
  - Q4 使单测失败；D1 截图中树结构与链一致；
  - `workspace.test.ts` 两处期望随数据改变，这不是放宽。“该提交所基于的基线已不是当前基线”仍由 `workspace.test.ts:145` 与 `upload-mode.spec.ts:393`（D5）覆盖。
- **不符合：** §5.3 的处置组合规则仍只在 `keeps every disposition scenario…` 中检查场景数组。这些规则包括：`ARCHIVED_BASELINE` 要求来源 `ARCHIVE`、有 `result_id`、无 `closure`、提升基线为 `ARCHIVED_SUBMISSION`；`MANUAL_CLOSE` 要求有 `closure`、无 `result_id`；Review 与 History 一致。新的链断言只检查提升基线存在且父基线相同，不检查来源与字段组合。Q4b 把第 1 轮演示 e 原样注入共用 fixture，175 项单测全部通过。第 1 轮 F4 要求“演示 e 那样的改动应使单测失败”，handoff §6 称 Q4“同时验证了演示 e”，但 Q4 注入的是 D5 形态，不是演示 e。

### F5 必测与截图：符合

- D1、D2 审核模式顶栏已截图；D3 有审核模式用例（关闭人、本地时间及 UTC 悬停原值、理由展开、三按钮禁用）并截图；
- W6 的工作台与 Preview 各有一条，URL 不带 `operationId`，断言 URL 被写入指针 attempt 的操作 ID 并出现操作卡片；
- `fe3b-withdraw-unknown` 改为等 bundle 就绪后再拍（N3 已改，截图核对通过）；
- 小问题（非阻塞，见 N1）：新增的 `fe3b-d1/d2/d3-review-topbar` 三张是在比较结果还在下载时拍的（骨架屏与“下载并校验比较结果”）。顶栏内容正确，但与 N3 同类。

### F6 handoff：部分符合（G4）

第 1 轮列的五处中，W10 覆盖、探针表头、W6、W9②标题四处已改。另有以下不符：

- §4 第 2 行把“校验镜像 tag”这一条换成了 RS 镜像，写“代码取 10 位”，却引用 `fe-8e6b8dd6f20b`（12 位）。实际情况：
  - RS tag 取 12 位（`run-real-backend-e2e.sh:452`）；
  - 校验镜像 `gateway-backend-validate:fe-<HEAD 10 位>`（`validate-upload-package.sh:191`）。
- 三个日志 SHA256 与节点上的文件不符，均有缺字或错字：

  | 项 | handoff | 节点实际 |
  | --- | --- | --- |
  | Q1 | `01a5368b39bee7f1…` | `01a5368bb39bee7f193909e25815266eec9a6d819efd9aef979eb0faa57ac0d0` |
  | Q3 | `4aa9ce44db1bfd43efcce45…` | `4aa9ce44db1bfd43ecfcce45e270b274d4b26c0835e62636c66e8060731ac8ed` |
  | 07 run-tests | `7e36418a8e1d5bd56d6b4beaa337ac0f4fd3ddd7751fcb84409ad16f5d437`（61 位） | `7e36418a8e1d5bd56d6b4beaa337ac0f4de3ddd7751fcb99784409ad16f5d437` |
- §6 末尾“Q4 的注入同时验证了演示 e”：不成立（G3）。
- §2 F5 末段称“W9 三支与新 W9④、F2、F3、D3 均在此轮截图覆盖之外”，与同节“D3 … 并截图”及实际截图 `fe3b-d3-review-topbar` 矛盾。

## 4. 需要修复（阻塞）

### G1 续做提示的“重试”不保留原提示（F1，§6.2）

- **现象：**
  - 演示 r2a：ABORTED 提示点“重试”后，`IMPORT_REJECTED` 消失；
  - W9④点“重试”后，在没有读取 attempt 的情况下，“无法读取提交结果，请刷新后重试”变成“提交未完成…”；用例断言的就是这一变化；
  - W9③同理（代码阅读）。
- **修复：** 续做提示上的“重试”重新执行 §6.2 的序列，而不是只调用 `refresh()`，或采用等价实现。序列为：先读工作区；
  - `active_submission_id` 非空：按 §6.1 的表，或按 FE2c 已有的提交结果处理；
  - `active_submit_attempt_id` 非空：按 §6.1 的表；
  - 两个指针都为空：用已知的 attempt ID 重读 attempt，`ABORTED` 保留“提交未完成…”与原始代码，读不到保留“无法读取提交结果，请刷新后重试”；
  - 工作区读不到：“无法确认提交状态”加“重试”。

  两页的“重试”使用同一入口。
- **用例：**
  - 演示 r2a 转为正式用例；
  - W9④改为：“重试”时 attempt 仍读不到，则保留原提示；attempt 可读且为 `ABORTED`，则显示“提交未完成…”与原始代码；
  - W9③补“重试后指针为空”一支，断言读取了 attempt。
- **探针：** 把提示的“重试”改回只调用 `refresh()`，上述用例必须失败。

### G2 404 的“刷新”入口（F3 余项，§6.1）

- **修复：** 404 一行的入口显示为“刷新”（行为仍是重新执行读取序列），其他行保持“重试读取”。
- **用例：** F3 e2e 断言“刷新”可见、“重试读取”不出现，点击后读取次数加 1。

### G3 §5.3 组合规则覆盖全部模拟 History 数据（F4 余项）

- **修复：** 把 `keeps every disposition scenario…` 中的处置组合规则改为对 `keeps every simulated History dataset reachable` 列出的每个数据集都执行。规则包括：
  - 处置只在 `APPROVED` 上；
  - `ARCHIVED_BASELINE` 的来源、`result_id`、无 `closure`，以及提升基线为 `ARCHIVED_SUBMISSION`；
  - `ARCHIVE` 关闭有 `result_id`、无 `closure`；
  - `MANUAL_CLOSE` 有 `closure`、无 `result_id`；
  - 同一归档结果至多一个 `ARCHIVED_BASELINE`。

  已有的 Review/History 一致性断言保持不变。
- **探针：** 演示 e（Q4b）必须使单测失败。

### G4 handoff（F6 余项）

在新 handoff 中改正 §3 F6 所列四处：镜像 tag 位数、三个 SHA、演示 e 的说法、D3 截图的说法。SHA 建议直接从 `sha256sum` 输出复制，不手抄。

## 5. 非阻塞

- **N1：** `fe3b-d1/d2/d3-review-topbar` 三张截图拍在骨架屏上，建议等 bundle 就绪再拍（同第 1 轮 N3 的做法）。可随 G1–G3 一起改。
- **N2：** `resumeNotice` 的计数在页面生命周期内不归零。续做之后的任何快照都会显示在红色 `role=alert` 提示框里，包括正常状态，例如再次提交后的“提交正在执行，完成后才能继续”（代码阅读，未构造用例）。建议在开始新的提交或上传时清除提示，或只在快照仍属于续做结果时显示。`ABORTED` + 指针未清的过时快照在重读前的短暂不一致（§3 F2）也会随之消失。
- **N3：** `fe3b-withdraw-unknown` 中，“重试读取”与“提交”按钮在 1280 宽度下间距很小，交 owner 看图时一并确认。
- **N4：** 第 1 轮 N2（长单行关闭理由不折叠）与 N6（被占用时工作区节点仍标“可提交”）仍待 owner 看图确认，本轮未改，符合约定。

## 6. 下一步

1. 实施会话按 G1–G4 修复（N1、N2 可同批），提交新的代码候选与 handoff。复审第 3 轮范围 `4ff1c11396..<新 handoff>`，重点：
   - G1 的探针（“重试”只调用 `refresh()`）使 W9 类用例失败；演示 r2a、Q4b 转为正式用例并通过；
   - 重跑 P1–P4、R1、Q2、Q3 与 E，确认保护仍在；
   - 07 重跑 `run-tests.sh --e2e --screenshots`；05 重跑 journeys。
2. 复审通过后的 04 取证（kickoff §9 FE3b 行）不变：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`run-real-backend-e2e.sh --suite journeys --subphase fe3b` 各运行一次。
3. §6、§6.4 截图交 owner 确认（含 N3、N4）。取证后做证据核对，再给出 FE3b 退出建议。
4. 本轮遗留：
   - 已删除：探针 worktree、`refs/review/fe3b-rr2/probe-*`、节点上的传输 bundle 与探针脚本目录；
   - 保留供复审对照，FE3b 退出后清理：
     - 两节点的 `/home/dev/gdds-fe-rereview2-fe3b` 与 `refs/review/fe3b-rr2/candidate`；
     - 开发主机的 `refs/review/fe3b-rr2/candidate`；
     - 两节点的 `/home/dev/gdds-fe-logs/fe3b/rereview-2/`；
     - 07 的截图目录 `/home/dev/gdds-fe-shots/fe3b-rereview2-4ff1c113`；
   - 第 1 轮保留项不变（`/home/dev/gdds-fe-rereview1-fe3b`、`refs/review/fe3b-rr1/candidate` 等）。

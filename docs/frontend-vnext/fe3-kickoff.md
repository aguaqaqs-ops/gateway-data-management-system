# FE3 kickoff：对接真实 backend

- **状态：** 已确认（owner，2026-11-05，§11 Q1–Q9；FE3a 审核后补充 Q10–Q12）；FE3a 可以开始，FE3b 的前置条件见 §3.2。
  - 初稿 `5c360bfb1b` 经 [kickoff 审核](reviews/fe3-kickoff-review.md)（`920f068da4`），结论为定向修订；
    修订 1 `de9cd5cb6f` 处理 B1–B4 与采纳的非阻塞意见（逐条见 §15）；
    [定向复审第 1 轮](reviews/fe3-kickoff-rereview-1.md)（`e91d9db6eb`）通过。
  - 确认记录 `3d3373e7fa` 改正复审 §3 的 R1–R4，并按复审 §4 登记基线已前移的已通过提交永久占用工作区的后端缺口（§2.1、§6.1、§12）。
  - 2026-11-05 按 [FE3a 审核](reviews/fe3a-review.md)（`a0b9604ddd`）中交设计会话的事项修订：
    - §4.6 补记真实 e2e 上传输入的方案（§11 Q10）；
    - §7 M7 规定组态树的基线显示序号（§11 Q11）；
    - §8.4 记录 M1 的结论（§11 Q12）。
    - 逐项处理见 §15.1。
- **日期：** 2026-11-05。
- **起点：** `fe-fe2c-exit`（tag 对象 `86901e038d` → `749f219d5f`，测试提交 `220325da37`，`frontend/` 树 `960ab1f6a1`），
  main 合入提交 `0430e0e738`；`fe-vnext` 在 `749f219d5f`。本文以 main `2c79d0947f` 为准核对。
- **依据：** [前端 kickoff](frontend-kickoff.md)（§3.3、§4.2–§4.4、§5、§6、§7、§7.1）、
  [FE2 kickoff](fe2-kickoff.md)（§6.5、§7、§9 Q16–Q19、§10）、FE2c 各轮审核报告（`reviews/fe2c-*.md`）、
  后端 [DC73](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc73-后端会话分为设计与审核两个角色)、
  [DC75](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc75-be-a工作区占用指针与本人撤回权限)、
  [BE-a 设计补充](../backend-vnext/refactoring/formal/plans/p6-be-a-design.md)（`f20f08bea9`，审核 `fcbfb4c1a0`）、
  [BE-a / BE-d 任务提示词草案](../backend-vnext/refactoring/formal/plans/p6-be-a-d-kickoff.md)、AGENTS（“专用测试节点”“前端测试（FD7）”“Docker / Compose 验证”）、
  testing-conventions“前端测试（FD7）”。
- **会话分工：** 与前端 kickoff §10 相同。本文由前端设计会话维护。BE-a、BE-d 归后端设计会话 `p6-backend-design`（DC73），
  前端设计会话不写后端提示词，只核对接口是否满足 FE3 的需要（§2.3），并经 owner 协调排期。

## 1. 目标

- 前端对接 Compose 中的真实 backend，跑通全部业务旅程（前端 kickoff §7 FE3 一行）。
- 刷新 OpenAPI 快照，并在 e2e 中与运行中的 `/openapi.json` 比对（前端 kickoff §4.2）。
- 接回上传模式顶栏的撤回（前端 kickoff §7.1，DC75）。
- 用 t1 真实数据从浏览器走完一次完整旅程。
- 完成 FE2 带入项（FE2 kickoff §6.5：M1、M7、n3、n8）。

不在范围：BE-b 的分组、列展示与行定位（FE4）；首批空基线（FE2 kickoff Q18，仍为缺口）；正式 SSO 与部署形态（Phase 8/9）；外部驱动通道与深色主题。

## 2. 当前事实（main `2c79d0947f`，2026-11-05 核对）

### 2.1 后端依赖

| 项 | 状态 | 对 FE3 的影响 |
| --- | --- | --- |
| S2a | 证据复核 2 通过（[报告](../backend-vnext/refactoring/formal/plans/p6-s2a-evidence-check-2.md)，候选 `3b3d9c97bc`）；exit 排在基准 exit 之后（DC70）。main 上没有 `p6-s2a-exit` | BE-a、BE-d 都排在 S2a 合入 main 之后 |
| 基准测量 | 进行中。[后端交接](../backend-vnext/refactoring/formal/plans/p6-backend-session-handoff.md) §2.1 列出的剩余项：W4 输入重新生成与验收、W4 各场景、H2 三节点、H3、表哈希对照、DC63/V5b 分段、正式 JSON、04 最终 runner，之后是基准终审。W4 修正已通过定向复核（[报告](../backend-vnext/refactoring/formal/plans/p6-baseline-stop-check-w4-duplicate-key.md)），实施方估计 W4 部分剩余 14–30 小时。设计会话核对时，ct108 的占用标记为 `p6-baseline-measure`，用途 `corrected-keyless-w4-generation-and-acceptance`，自 2026-11-04T23:10:53Z（审核会话未访问 ct108） | 决定 S2a 合入时间 |
| BE-a | 设计补充 `f20f08bea9`；kickoff 审核通过（`fcbfb4c1a0`，归属订正 `680f9a60f0`）；owner 实施确认待记录；提示词草案未发出 | 接回撤回（§6）、OpenAPI 状态码与指针字段（§5） |
| BE-d | 任务草案在 `p6-be-a-d-kickoff.md` §3；kickoff 审核未安排；提示词未发出 | 当前 `/bundle` 只返回 manifest JSON，所有需要下载 bundle 的旅程都要等 BE-d |

**预计时间（设计会话估计，不是后端承诺）：** 基准剩余项与终审约 1–2 天，随后办理基准 exit 与 S2a exit。
BE-a、BE-d 各含实施、审核、04 runner、容器门禁与 05 t1，后端草案建议先 BE-a 后 BE-d，各约 2–3 天；
BE-d 还需先完成 kickoff 审核。按此估计，两者合入 main 约在 S2a 合入后一周内，即 11 月 10–14 日前后。排期以后端设计会话为准。

**协调建议（经 owner 转后端设计会话）：**

- BE-d 的 kickoff 审核是纯文档工作，建议现在安排，与基准测量并行；BE-a 的实施确认也可以现在给出。这样 S2a 合入后两项都可以立即开始。
- 对 FE3 而言，BE-d 解锁的旅程比 BE-a 多（差异浏览、提交、审核、历史比较都要下载 bundle），BE-a 只解锁 §6 与快照中的状态码和字段。
  若后端认为两项可以并行或调换顺序，FE3 会更早进入真实旅程调试；不并行也不影响本文的安排。
- **请在 BE-d kickoff 审核中确认 tar 成员与 closure 的对应关系（审核报告 D1，见 §2.3 最后一行）。**
- **请在 BE-a 实施前决定：基线已前移后才通过的提交会永久占用工作区（定向复审 §4，见 §12）。**
  - 归档候选只包括基于当前 head 的已通过提交（`application/archive/snapshot.py`），开始归档时只释放和关闭这些候选（`start.py`）。
  - BE-a 删除 `RETURN_FOR_REVISION` 后，`APPROVED` 没有任何转移；审核时也不检查基线是否已前移。
  - 于是：A、B 基于同一基线都在待审核 → A 通过并归档，基线前移 → 审核人再通过 B。B 的工作区不能撤回、不会被任何归档释放，再次提交返回 `SUBMIT_OCCUPANCY_CONFLICT`，被永久占用。
  - 处理方式由后端定，例如：归档时一并关闭基于旧基线的待审核或已通过提交；通过时拒绝基线已前移的提交；允许对这类提交做关闭。前端不需要新字段，但 §6.1 的最终文案取决于处理方式。

### 2.2 节点、镜像与数据

| 项 | 05 | 04 | 说明 |
| --- | --- | --- | --- |
| 前端工具链 `mcr.microsoft.com/playwright:v1.64.1-noble` | 有 | 有 | 身份见 `frontend/scripts/run-tests.sh` |
| npm 缓存 | `/home/dev/gdds-fe-cache/fe0/npm-cache`，归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz` | `/home/dev/gdds-fe-cache/frontend/npm-cache`，归档 `npm-cacache.tar.gz` | 两节点归档的 SHA256 相同（`0d861824…0089f4`），来源提交 `a2fb4a027a`。`run-tests.sh` 的默认路径是 04 的路径；在 05 上运行要设置 `GATEWAY_FRONTEND_NPM_CACHE` 与 `GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE`；两节点都设置 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a`，否则日志中的来源提交记为 `unknown`。新脚本使用同样的变量 |
| backend 依赖镜像（当前 main vnext 树 `2791d3ff3d` 需要 `gateway-backend-deps:lock-c668cef8e47e`，由 `build-backend-dependency-base.sh --print-input` 得出） | **缺** | 有 | 05 上只有 `lock-d054366c02fa`（fixture 生成用）。05 调试真实 e2e 前要按 §4.3 传入 |
| RS 依赖镜像 `gateway-p2r1-repository:lock-6dc9659f0aee` | 有 | 有 | RS 镜像本身按当前 HEAD 构建（§4.3） |
| `gateway-repository-service:local` | 有（revision `80ce756619`） | 有（S2a 候选 `3b3d9c97bc`） | 由后端会话使用，前端不重新 tag（§4.3） |
| 真实数据包 `/home/dev/gateway-real-dumps/packages/rd-t{1..4}-*.tar.gz` | 有 | 有 | 规范化的源包，只含 `/sql/dbcfg.sql` 与 `/comps/logic/logics.xml`，没有 `.pmc` |
| 组态目录原件 | **无** | **无** | 只在开发主机 `/home/dev/gateway-real-dumps/{small_cut,small,medium,large}` |

**组态目录与数据档的对应（按 `sql/dbcfg.sql` 与 `comps/logic/logics.xml` 的 SHA256 核对；8 个目录的两个成员都与对应源包一致）：**

| 档 | 目录（开发主机） | 文件数 | 目录大小 |
| --- | --- | --- | --- |
| t1 v1 / v2 | `small_cut/small_cut-1`、`small_cut-2` | 19 / 19 | 6,853,875 / 6,854,427 字节 |
| t2 v1 / v2 | `small/small-1`、`small-2` | 229 / 230 | 约 66 / 64 MB |
| t3 v1 / v2 | `medium/medium-1`、`medium-2` | 223 / 226 | 约 237 / 238 MB |
| t4 v1 / v2 | `large/large-1`、`large-2` | 528 / 528 | 约 317 MB |

- 前端上传要求所选目录根下恰好一个 `.pmc` 且有 `sql/dbcfg.sql`（`upload-package.ts`，沿用 legacy 的规则）。
  节点上的源包不满足，不能直接用于浏览器上传；组态目录原件满足。t1 旅程的输入需要把目录原件传到 05（§8.1、§11 Q2）。
- 审核会话的补充核对（不阻塞）：
  - t1 两个目录各有 3 个非 ASCII 文件名与 3 个空文件；
  - `large-1` 有 498 个非 ASCII 文件名，另有 2 个路径超过 100 字节（最长 103 字节），按 `tarHeader` 的规则可以拆分；
  - 后端 `normalize_package_path` 不拒绝这些路径。

### 2.3 BE-a、BE-d 与 FE3 需要的接口核对

依据 BE-a 设计补充 §2–§4 与任务草案 §3。结论：**满足 FE3 的需要，不需要新增后端字段或接口**，前提是最后一行由 BE-d 确认。

| FE3 需要 | 后端设计 | 结论 |
| --- | --- | --- |
| 定位上传模式下当前提交（Q16） | `WorkspaceResponse.active_submission_id`，required nullable，新建 201 与已存在 200 两条路径都返回 | 满足 |
| 刷新后找回进行中的提交尝试 | `active_submit_attempt_id`，经已有 `GET .../submit-attempts/{id}` 取 `operation_id`；提交执行、等待恢复或结果未知时保留，确认 `ABORTED` 后才清空（BE-a 设计补充 §2） | 满足；前端按 §6.2 处理，不按 operation 终态推断指针已清空 |
| 本人读取审核状态（含终态） | `withdraw_own_submission` 可读本人提交的 `GET .../review`，所有状态 | 满足 |
| 撤回请求的预期版本 | `expected_review_version` 取 `review_version`，不用工作区版本 | 满足 |
| “无权限”的判定 | 两个审核权限都没有时 GET 与 POST 返回 403；他人、跨 scope 与不存在统一 404 | 满足；前端不按 actor 推断（§6.1） |
| 撤回后可重新上传 | 指针、当前上传与 Preview 清空 | 满足 |
| 两个创建接口的状态码 | `POST /v1/workspaces` 201/200，`POST /v1/history-compares` 202/200 写进 OpenAPI | 满足；FE3b 去掉 FE2 的类型变通（§5.3） |
| 整包 tar | 成员 `manifest.json`、`artifact-closure.json`、按 closure 顺序的产物；`Content-Length`、`ETag`；头前预检的错误码写进 Contract 与 OpenAPI | **有前提，需 BE-d 确认（审核报告 D1）**。前端 `posix-tar.ts` 要求：第 1、2 个成员是 `manifest.json` 与 `artifact-closure.json`；之后的成员与 closure 条目逐个对应、顺序相同，`logical_path` 不重复。BE-d 草案 §3 还在考虑同一 `source_ref` 对应多个 `logical_path` 时去重。如果后端要按内容去重，必须由 closure 本身表达共享，不能出现多个 closure 条目对应同一个 tar 成员。在 BE-d kickoff 审核中确认；结论与此不同时，前端解析的改动在 FE3b 中做，交设计会话安排 |

实施中若合入后的接口与本表不符，按 §10 停止。

## 3. 阶段安排

### 3.1 甲、乙两个方案

- **甲：** 整个 FE3 等 BE-a、BE-d 合入 main 后开始。
  - 好处：一个阶段、一次审核与取证；运行框架直接按最终接口做。
  - 代价：前端空等约一周或更久（§2.1）。M1 是否需要改流式打包要到 t1 旅程才知道，届时才改，FE3 的后半程变长。
- **乙（owner 2026-11-05 原则同意，§11 Q1）：** 拆成两个子阶段。
  - **FE3a（现在开始）：** 不依赖新接口的部分。包括 M7、n3、n8（模拟接口）；真实 backend e2e 的运行框架，在当前 backend 上跑冒烟；
    真实 e2e 用的上传输入；生成类型与快照的一致性检查；M1 的打包内存测量（只需组态目录，不需要 backend）。
  - **FE3b（BE-a、BE-d 合入后）：** 刷新快照、§6 撤回、全部真实旅程、t1 旅程。若 FE3a 的 M1 结论为“需要流式”，流式打包也在 FE3b 做。
  - 理由：
    - 运行框架（Compose、占用标记、镜像、身份、数据准备、清理、日志）与新接口无关，工作量也最大，可以先在当前 backend 上做实、先审核；
    - FE3b 开始时只需加场景，审核也集中在业务旅程；
    - M1 提前测量，需要改流式时不占 FE3b 的关键路径。
  - 代价：多一次审核与 04 取证。FE3a 冒烟时 backend 仍是 BE-a 之前的形态，FE3b 中会话文件的权限要补 `withdraw_own_submission`，属于预期的小改动。

### 3.2 乙的子阶段

| 子阶段 | 内容 | 前置条件 | 退出 tag | 审核范围 | 退出条件 |
| --- | --- | --- | --- | --- | --- |
| FE3a 运行框架与带入项 | §7 的 M7、n3、n8；§4 运行框架与当前 backend 上的冒烟（§4.7）；§4.6 上传输入；§5.4 生成类型一致性；M1 的打包测量（§8.4，需要 §8.1 的目录） | 本文经 owner 确认 | `fe-fe3a-exit` | `fe-fe2c-exit..<FE3a 候选>` | 审核通过；04 上：模拟接口全量 runner（含截图）、上传包后端校验、真实 backend 冒烟各一次通过；**M1 测量完成**，结果写入 handoff，并经审核会话与 owner 判断（§8.4，§11 Q8） |
| FE3b 真实旅程 | `fe-vnext` 合入含 BE-a、BE-d 的 main；§5 快照刷新与类型、模拟数据同步；§6 撤回；§4.7 全部真实旅程；§8 t1 旅程；M1 在旅程中复测；M1 需要时改流式 | S2a、BE-a、BE-d 都已合入 main；§12 的“基线已前移的已通过提交”已由后端定下处理方式，§6.1 的文案已据此定稿；owner 确认发出 FE3b 提示词 | `fe-fe3b-exit` | `fe-fe3a-exit..<FE3b 候选>` | 审核通过；04 上：模拟接口全量 runner（含截图）、上传包校验、真实 backend 全部旅程各一次通过；05 上 t1 旅程的证据运行通过（§9）；§6 截图经 owner 确认 |

- FE3b 结束即 FE3 结束，FE4 以 `fe-fe3b-exit` 为起点。
- **M1 与 FE3a 退出（owner 2026-11-05，§11 Q8）：** M1 测完才能退出 FE3a。若目录传输迟迟不能完成，由 owner 另行决定是否把 M1 移到 FE3b。
- 两个子阶段都在 `fe-vnext` 上进行。开始时先把当时的 main 合入 `fe-vnext`（只用合并，不 rebase）。
- **路径核对（两个子阶段都做）：** 设 `<main>` 为最后一次合入 `fe-vnext` 的 main 提交：
  - `git rev-parse <候选>:vnext` 与 `git rev-parse <main>:vnext` 相等；
  - `git diff --name-only <main> <候选>` 只含 `frontend/` 与 `docs/frontend-vnext/` 下的路径。
- 审核范围中来自 main 的提交（文档与 `vnext/`）不在前端审核范围内；`vnext/` 由后端审核负责。

**FE3b 的提前调试：** BE-a、BE-d 先后合入时，实施会话可以在先合入的一项上开始在 05 调试相关旅程，例如 BE-d 合入后先调差异浏览。
FE3b 的候选与审核仍在两项都合入后进行，不为单项另设 tag。

### 3.3 FE3a 在当前 backend 上无法验证的内容

当前 backend（vnext 树 `2791d3ff3d`）上，`GET .../preview-results/{id}/bundle` 与 `GET /v1/history-compares/{id}/bundle` 只返回 manifest JSON。前端 bundle 下载按 tar 解析，因此：

- **要等 BE-d：**
  - Preview 差异浏览，以及由此进入的提交：`SubmitDialog` 只在 Preview 页渲染，“提交”在没有 bundle 时禁用（`ComparisonPage.tsx`）；
  - 审核模式（History bundle）中的通过、退回、撤回；
  - 归档主线：入口只在组态树的提交节点上（`WorkbenchPage.tsx`、`view-model/workspace.ts`），FE3a 期间树中没有提交节点，归档候选为空的界面也走不到；
  - 历史比较的结果浏览与抽屉计数（需要至少两个节点）；
  - bundle 截断后重新下载；t1 旅程。
- **要等 BE-a：** §6 全部内容；快照中的 201/202、指针字段与 `RETURN_FOR_REVISION` 的删除；本人撤回身份。
- **FE3a 可以验证：**
  - 运行框架本身；
  - 运行时 OpenAPI 与当前快照比对（预期一致，§5.2）；
  - 工作区 CreateOrGet；组态树读取 History（只有 `INITIAL`）；
  - 浏览器打包的上传被真实 backend 接受；
  - Preview 操作轮询到 `SUCCEEDED`，并读到 Preview 结果（判据见下）；
  - 无权限身份上传返回 403 的显示。工作区按 actor 隔离，无权限身份的工作区没有上传，当前 backend 上只有上传的 403 可以验证；
  - “能上传、没有 Preview 权限”的身份发起 Preview 返回 403 的显示（§4.6）；
  - 请求侧约束（`Idempotency-Key` 等）由真实 backend 检查。

**冒烟的判据：**

- 用 `page.waitForResponse` 等方式由程序断言：`GET .../preview-results/{id}` 返回 200，其 `preview_result_id` 与工作区的 `current_preview_result_id` 一致；
- Preview 成功后前端会立即下载 bundle（`UploadStepCard` 中的 `runPreviewJourney`），在当前 backend 上必然失败。这一步不作断言（这是即将删除的临时行为），但页面上不能出现未捕获错误。

## 4. 真实 backend e2e 的运行框架

### 4.1 入口

- 新增提交在 `frontend/scripts/` 下的独立脚本，例如 `run-real-backend-e2e.sh`，**不作为 `run-tests.sh` 的选项**（§11 Q4）。理由：
  - 前提条件不同：占用标记、Compose、backend 镜像与 vnext 树；
  - `run-tests.sh` 不依赖后端镜像（AGENTS FD7），这一点不变；
  - 与 FE2c 的上传包后端校验脚本（FE2 kickoff §7.1）做法一致。
- 套件参数：`--suite smoke`（FE3a）、`--suite journeys`（FE3b 全部旅程）、`--suite t1 --input-root <目录>`（§8）。
  另有 `--log-dir <绝对路径>`、`--evidence-dir <绝对路径>`（失败时的 trace、截图与参考截图），都必须在 worktree 外。
  npm 缓存路径与 `run-tests.sh` 使用同样的环境变量（§2.2）。
- Playwright 使用单独的配置与目录，例如 `playwright.real.config.ts` 与 `e2e-real/`；`run-tests.sh` 的 `playwright test` 不收集这些用例。
- 不修改 `vnext/`。只读使用 `vnext/deploy/compose.yaml`、`vnext/scripts/build-backend-dependency-base.sh --print-input`、
  `vnext/scripts/build-repository-service-image.sh`。需要改它们才能运行时，停下交设计会话（§10）。
- AGENTS 与 testing-conventions 的 FD7 一节还没有写这个脚本。FE3a handoff 写出建议条文（入口、节点、占用、证据），由 owner 转治理会话（同 DC72 第 2 项的做法）。

### 4.2 节点、占用与单飞

- 调试在 05，取证在 04（testing-conventions“前端测试”节点表）。t1 在 05（DC36，§8）。
- 脚本开始时按 DC70 补充用 `mkdir /home/dev/gdds-node-busy.d` 原子获取整机占用，写入会话名、用途、开始时间（UTC）、hostname、worktree 与 HEAD。
  - 会话名按角色与子阶段写，例如 `fe3a-impl`、`fe3a-review`、`fe3b-impl`；
  - 目录已存在即退出（非 0），等待对方释放，不抢占；长时间未释放时报告 owner（DC70 补充）；
  - 占用标记的用途为计时测量时，前端在该节点上的任何运行都等待（前端 kickoff §6）。
- 获取后另以非阻塞方式（`flock -n`）持有后端 Compose 门禁使用的 `/tmp/gateway-compose-gate.lock`（`compose_gate_harness.py`），失败即退出，与占用标记的处理一致。
- 运行前的残留检查（AGENTS 整机单飞）：
  - 没有容器发布 8000 端口（`docker ps --filter publish=8000`）；
  - `/proc` 中没有 dolt 进程；
  - 没有本脚本命名前缀的 Compose 项目、卷、网络与工具链容器残留（§4.5）。

  任一不满足即退出，不清理他人的资源。
- 退出时（含失败与可捕获的中断）先清理（§4.8），确认没有本次的容器、卷、网络与进程后，释放 flock，最后删除占用标记。
  清理核对失败时保留占用标记，把用途改写为 `cleanup-failed` 并以非 0 退出，交 owner 处理。

### 4.3 镜像

- **backend/worker：** 按 AGENTS“backend/worker（自 `p6-backend-image-exit` 起）”，在节点本机离线构建：
  - `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`；
  - `GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=<tag>`，`<tag>` 由 `vnext/scripts/build-backend-dependency-base.sh --print-input` 对当前 HEAD 算出，
    该镜像必须已在本机且 `gateway.backend.dependency-input-sha256` label 与输入一致，否则停止（缓存缺失），不在测试节点上构建依赖镜像；
  - `GATEWAY_DOCKER_BUILD_NETWORK=none`；
  - 保留 Compose build，不设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。
- **依赖镜像的来源：**
  - FE3a 需要 `lock-c668cef8e47e`，04 已有，05 缺。按 AGENTS 的 backend/worker 规则补到 05：
    1. 在 CT201（开发主机）的 clean worktree 运行 `vnext/scripts/build-backend-dependency-base.sh --save <归档>`。标签已存在时脚本会复用并核对 label；
    2. 经获准的局域网传到 05，`docker load`；
    3. handoff 记录来源提交、完整输入摘要、tag、config digest、全部 RootFS DiffID、归档 SHA256、构建与传输的起止时间。
  - FE3b 使用合入 S2a、BE-a、BE-d 后 main 所需的依赖镜像。S2a 合入后，依赖输入可能变为 `p6-s2a` 的输入，tag 可能就是两节点都已有的 `lock-d054366c02fa`。
    无论哪种情况，都按 `--print-input` 的结果与 label 核对，缺失即停止并报告。
- **Repository Service：**
  - 构建前由程序核对 `gateway-p2r1-repository:lock-<repository_service/uv.lock 的 SHA256 前 12 位>` 在本机存在，且 `gateway.p2r1.uv-lock-sha256` label 一致；
    不一致即停止。否则 `build-repository-service-image.sh` 会自动改用缓存 URL 构建；
  - 用 `vnext/scripts/build-repository-service-image.sh` 按当前 HEAD 构建，`GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE` 设为上述 tag，`GATEWAY_DOCKER_BUILD_NETWORK=none`；
    构建失败（包括需要访问网络）即停止，视为缓存缺失；
  - `GATEWAY_REPOSITORY_SERVICE_IMAGE` 设为本次运行专用的 tag（例如 `gateway-repository-service:fe-<HEAD12>`），不覆盖后端会话使用的 `gateway-repository-service:local`；
  - 所有 `docker compose up` 都带 `--no-build`（同 `compose_gate_harness.py`）：compose 中 RS 同时有 `image:` 与 `build:`，tag 不存在时会按 compose 的参数联网构建；
  - 运行结束时删除本次 tag，保留构建层缓存。
- **身份记录（每次运行）：**
  - 依赖镜像：tag、`dependency-input-sha256` label、本机 image ID、`docker image inspect` 的 `RootFS.Layers`；
  - RS：tag、本机 image ID，以及 build-input、source-tree、revision label；
  - backend/worker：本机 image ID；
  - Docker 与 Compose 的版本。

  config digest 与全部 DiffID 只在跨节点传输时比较一次，写进 handoff；每次运行不对依赖镜像做 `docker save`（约 4.7 GB）。
  `backend/Dockerfile` 在预置依赖模式下已核对 tag、输入摘要与五个输入文件。
- **前端工具链：** 与 `run-tests.sh` 相同的固定镜像与身份核对、npm 离线缓存。

### 4.4 Compose 栈

1. 项目名 `gdds-fe-<子阶段>-<HEAD12>-<UTC 时间戳>`，全部小写（Compose 项目名只能用小写字母、数字、`-` 与 `_`；时间戳写成 `20261105t101500z` 这样的格式）。
   命令为 `docker compose -f vnext/deploy/compose.yaml -p <项目名>`。
2. secret 与配置写在 worktree 外的本次运行目录（容器可读的权限）：Repository bearer、internal bearer、session 文件、部署映射。
   token 每次随机生成，不提交，不进入构建产物，也不写进脚本日志。Playwright trace 中含有本次的临时 token（§4.9）。
3. `build backend worker` → `up -d --no-build repository-service` → 等 RS ready → 播种全部 scope 的仓库（§4.6） → 写好全部映射 →
   `up -d --no-build backend worker` → 等 `/readyz` 与 worker 就绪。backend 启动后才读取映射，因此映射要在此之前写好。
4. 运行时 OpenAPI 比对（§5.2）通过后才运行浏览器用例。

### 4.5 工具链容器与 backend 的网络

- 工具链容器加入本次 Compose 项目的默认网络（`--network <项目名>_default`），`GATEWAY_FRONTEND_BACKEND_ORIGIN=http://backend:8000`。
  浏览器只访问容器内的前端服务器，由它代理 `/v1`、`/readyz`、`/openapi.json` 到 backend（`vite.config.ts` 的代理不分模式，preview 沿用；与生产同源反向代理的形态一致）。
- 工具链容器使用固定的名称（`<项目名>-toolchain`）与 label `com.docker.compose.project=<项目名>`。它不属于 Compose 项目，中断时如果仍连在网络上，`compose down` 删不掉网络。
  因此清理时先停止并删除它（§4.8），运行前残留检查与清理后核对也包括它。
- 不用 host 网络：不在宿主机上新增端口；8000 由 Compose 发布，仍按 §4.2 占用。
- `npm ci --offline` 照常离线；日志记录所用网络名与 `docker network inspect` 的 ID。
- **被测构建（§11 Q5）：** 真实 e2e 测生产构建（`npm run build` 后 `vite preview`），不测开发构建：
  - 生产构建是用户实际拿到的产物；
  - 生产构建中没有身份选择（FE2 kickoff §6.2）。`currentGatewaySession()` 在每次请求时读取 `window.__gatewaySession`，
    由 Playwright 在页面脚本运行前注入（`addInitScript`）；token 来自 §4.4 生成的身份文件，以只读方式挂进容器；
  - 生产构建没有身份切换。**每个身份用一个 browser context**，各自注入；需要两个身份同时在线的场景（例如 §6.3 W5）开两个 context；
  - OPFS 按 context 隔离，“再次打开同一 Preview 不重新下载”要在同一个 context 中验证；
  - 开发构建的模拟身份切换（`DevIdentityControl`）与模拟接口只用于模拟接口 e2e，不改动。

### 4.6 测试身份与初始数据

**身份：** 会话文件按 backend 已支持的格式生成（`sessions[]`：`token`、`actor_id`、`gateway_device_external_key`、`business_project_id`、`permissions`；
同 `real_dump_journey.py` 的 `_write_compose_secrets`；前端 kickoff §4.3）。每个 scope 一组，权限是精确字符串，没有继承（`vnext/deploy/README.md`）。

- 每个身份有不同的 `actor_id`：工作区按 actor 隔离，本人撤回按 `Submission.created_by` 判定。
- 组态树读 History，审核模式的历史比较与轮询也要读 History，因此各身份都带 `workspace_read` 与 `read_project_history`。

| 身份 | 权限（在上述两项之外） | 用途 |
| --- | --- | --- |
| 提交人（本人撤回） | `upload_submit_workspace`、`preview_workspace`、`withdraw_own_submission`（BE-a 之后） | 上传、Preview、提交、上传模式撤回（§6） |
| 提交人（仅上传） | `upload_submit_workspace`、`preview_workspace` | §6“无权限”场景 |
| 提交人（无 Preview 权限） | `upload_submit_workspace` | Preview 403（R10） |
| 审核人 | `review_submission` | 审核模式的通过、退回、撤回 |
| 归档确认人 | `archive_submission` | 归档主线 |
| 无权限身份 | 无 | 上传、审核查询、归档候选的 403（R10） |

- FE3a 中“本人撤回”身份不带 `withdraw_own_submission`（当前 backend 没有该权限）；FE3b 补上。
- 验证本人撤回时不用审核人或全权限身份代替（前端 kickoff §4.3）。
- 身份文件同时给出 `business_project_id`、`gateway_device_external_key`，由用例按身份注入；脚本日志只记录身份名与权限，不记录 token。

**初始数据：**

- **仓库与映射：** 做法同后端 Compose 门禁（`compose_gate_harness.seed_repository_and_mapping`）：在 RS 容器内 `POST /v1/repositories`，
  核对 `INITIAL` 提交为空，再把 `repository_id`、`initial_commit_id` 写入部署映射（`baseline_head_version = 0`）。backend 启动时据此创建 `INITIAL` 基线。
  多个 scope 时：
  - 每个 scope 播种用不同的 RS `Idempotency-Key`。harness 固定使用 `compose-seed-repo`，照抄会回放同一个仓库；
  - 每个 scope 的 `business_baseline_node_id` 互不相同；
  - 全部映射在 backend 启动前写好。
- **scope 隔离：** 每个互相独立的旅程用自己的 scope（一条映射、一个仓库、一组身份），失败不连带其他旅程。用例单 worker 串行（`workers: 1`，不重试）。
- **共用上传输入（FE3a）：** 把 bundle fixture 生成器（`frontend/scripts/generate-backend-bundle-fixture.py`）中的输入移到提交的文件
  `frontend/src/test/fixtures/source/upload-inputs/`：
  - SQL 常量移到 `.sql` 文件；`_composite_logic()` 生成的 `logics.xml` 也移到文件；由程序生成的 `_workbench_telemetry_sql()` 留在生成器中；
  - 文件内容与原字符串逐字节相同（含结尾换行）。移动后重新生成全部 fixture，与已提交的逐字节相同，跨实现摘要测试照常通过。此后这些文件继续保持逐字节不变。
- **真实 e2e 的上传输入（owner 2026-11-05，§11 Q10）：**
  - **与模拟 fixture 分开的理由：** 共用的 `sql-baseline.sql`、`sql-initial.sql`、`sql-modified.sql` 都含没有 `gid` 列的有序表 `b1_n1_iec104_yc_list`。
    这是有意的设计，用来产生模拟 fixture 中的有序表诊断；真实 Preview 对它返回 `KEY_MISSING`（FE3a 调试，`0712368347`）。
    改共用文件会改变全部已提交的 bundle fixture 与诊断场景，所以真实 e2e 另备输入，模拟 fixture 不动。
  - **来源规则：** 从共用文件派生，只补真实 backend 接受所需的最少列，不改数据本身：
    - 派生文件放在 `frontend/e2e-real/fixtures/upload-inputs/`，与共用文件同名：`sql-baseline.sql`、`sql-initial.sql`、`sql-modified.sql`；
    - 三份文件都只改 `b1_n1_iec104_yc_list` 的两行：表定义加 `gid INT NULL` 作为第一列（`(gid INT NULL, no INT NOT NULL, value VARCHAR(32) NULL)`），
      `INSERT` 的那一行补 `gid = 1`（`VALUES (1, 1, '无稳定 gid')`），其余逐字节相同。FE3a 已有的 `real-sql.sql` 就是派生后的 `sql-modified.sql`，改名后移入该目录；
    - 不需要改的文件（`sql-replacement-current.sql`、`logics-1.xml`、`logics-2.xml`、`logics-3.xml`）由运行脚本直接从共用目录读取，不复制。删除 `real-logics.xml`（与 `logics-3.xml` 相同）；
    - 单测（进入 `run-tests.sh`）核对：两行替换文本在共用文件中各出现一次；对共用文件做这两行替换后，得到的结果与派生文件逐字节相同；
    - 以后若要再补列（例如别的 key 列），按同一规则扩展替换表与单测；无法只靠补列让 backend 接受时，停下交设计会话。
  - **`logics.xml` 配对：** 与生成器相同：`sql-baseline` ↔ `logics-1`，`sql-initial` ↔ `logics-2`，`sql-modified` ↔ `logics-3`，`sql-replacement-current` ↔ `logics-3`。
  - **上传目录：** 每个上传目录包括：根目录一个占位 `.pmc`、`sql/dbcfg.sql`、`comps/logic/logics.xml`。目录写在 worktree 外的本次运行目录；FULL 的 ① 与 ② 各用一个目录。
- **四类上传（下表“派生”指上面的派生文件，“共用”指共用目录中的文件）：**

  | 输入 | 用途 | ② 本次归档组态 | ① 原始组态备份（只 FULL） | 相对当时基线的规范变化 |
  | --- | --- | --- | --- | --- |
  | A | 第一次 MODIFIED_ONLY（基于空 `INITIAL`） | 派生 `sql-baseline` + `logics-1` | — | 全部表都是新增 |
  | B | 归档 A 后的 FULL | 派生 `sql-initial` + `logics-2` | 与 A 相同 | 相对 A：`device` 改一行、删一行、增一行；`keyless_demo` 内容；`schema_demo` 结构与值；`b1_n1_iec104_syx_list` 移动与空行；`logics.xml` |
  | C | 归档 B 后再一次 MODIFIED_ONLY | 派生 `sql-modified` + `logics-3` | — | 相对 B：`device` 改一行；`keyless_demo`；删除表 `retired_table`、新增表 `added_table`；`schema_demo` 加列与值；`logics.xml`（`b1_n1_iec104_syx_list` 不变） |
  | D | `DIFFERENT_PROJECT`（R4 的身份确认） | 共用 `sql-replacement-current` + `logics-3` | — | `version_manager` 为 `project-b`，而 A、B、C 都是 `project-a`；表集合也不同 |

  - **上传顺序：** 每个 scope 内，每次提交都必须相对当时的基线有规范变化，否则提交返回 409 `NO_CANONICAL_CHANGE`。实施会话按上表写出每个 scope 的上传序列，并在 handoff 列出：
    - A → B → C 依次归档时，每一步的规范变化见上表；
    - 被退回或撤回后重新上传，可以用同一输入：规范变化是相对基线计算的，不是相对上一次上传；
    - 已归档某输入后，再上传同一输入会得到 `NO_CANONICAL_CHANGE`，序列中不要这样排；
    - D 必须在至少归档过 A、B、C 之一的 scope 上进行。在空 `INITIAL` 上，基线一侧没有 `version_manager`，产生不了 `DIFFERENT_PROJECT`。
  - 至少覆盖：A（第一次 MODIFIED_ONLY）；B（归档后的 FULL，① + ②）；C（内容与上一次不同的再一次 MODIFIED_ONLY）；D（`DIFFERENT_PROJECT`）。
- **FE3a 的核对（真实 backend，05 调试，04 随冒烟取证）：**
  - **组成：** 并入 `--suite smoke`。每次上传用一个独立 scope，都基于空 `INITIAL`，共 5 个：
    - A、B 的 ②（派生 `sql-initial` + `logics-2`）、C、D 各做一次 MODIFIED_ONLY；
    - B 做一次 FULL（① = A，② = B 的 ②）。
    - 其中一个可以与冒烟已有的提交人 scope 合并。
  - **判据（每个 scope）：**
    - 上传 201；Preview 轮询到 `SUCCEEDED`；`GET .../preview-results/{id}` 返回 200；
    - 测试侧用该身份经代理读取 bundle 端点。当前 backend 上它返回 bundle manifest JSON（§3.3），断言 `failed_pairs` 为空；
    - 每个比较对的 `summary.failed_table_count = 0`，② 一侧所在比较对的 `summary.changed_table_count ≥ 1`。降级的表允许出现，例如 `keyless_demo` 的整行比较；
    - 运行时 JSON 的字段名与此不符时，停下交设计会话，不自行另选判据。
  - **只记录、不断言：** D 的 `identity_pairs[].status`（空 `INITIAL` 上预期不是 `DIFFERENT_PROJECT`）；FULL 两个比较对各自的 `changed_table_count`。
  - **FULL 在空 `INITIAL` 上不能走到 `SUCCEEDED` 时：**
    - 后端不拒绝在 `INITIAL` 上做 FULL（FE2 kickoff §9 Q18），所以这属于意外，保留日志与 trace，停下交设计会话；
    - 设计会话判断为预期行为时，B 的 FULL 留到 FE3b 归档 A 之后首次验证，FE3a 不因此阻塞退出。B 的 ② 已由 MODIFIED_ONLY 核对过 import；
    - 设计会话判断为后端缺陷时，按 §10 转后端设计会话。
  - **FE3a 证实不了、留给 FE3b 的（都需要归档）：**
    - B 的 FULL 中，基线 → ① 比较对 `changed_table_count = 0`（① 与已归档的 A 相同；不为 0 时停下交设计会话），① → ② 比较对 ≥ 1；
    - C 相对 B 有变化；D 的身份对为 `DIFFERENT_PROJECT`；
    - A、B、C、D 的提交都不返回 `NO_CANONICAL_CHANGE`。
  - BE-d 合入后，bundle 端点改为 tar。FE3b 按 BE-d 的格式读取同一组 summary。
- 真实 e2e 以外，模拟接口 e2e 与 fixture 生成器只用共用目录；派生文件不进入 fixture 生成器。
- 真实数据只在 t1 套件中使用（§8）。

### 4.7 场景

**FE3a 冒烟（`--suite smoke`）：** §3.3“FE3a 可以验证”所列各项，判据同 §3.3。

**FE3b 全部旅程（`--suite journeys`）：**

| # | 旅程 | 要点 |
| --- | --- | --- |
| R1 | 工作区与组态树 | CreateOrGet 第一次 201、刷新后 200；树中 `INITIAL` 基线；提交与归档后树节点与状态按 FE2 kickoff §4.1 |
| R2 | 上传与 Preview | 浏览器打包、上传、Preview 轮询、下载 tar（`Content-Length`、`ETag`、逐成员摘要）、进入差异浏览；MODIFIED_ONLY 与 FULL 各一次；在同一 context 中再次打开同一 Preview 不重新下载 |
| R3 | bundle 截断重下 | 路由拦截截断一次真实 tar 响应，前端丢弃本地副本、重新下载后可浏览 |
| R4 | 提交 | 从 Preview 顶栏提交到 `PENDING`；`DIFFERENT_PROJECT` 输入（§4.6）覆盖身份确认 |
| R5 | 幂等重试 | 提交或审核之一：用 `route.fetch()` 把请求送到 backend 后对浏览器 `abort`，前端用同一 key 重试，界面显示成功。回放状态码按 route：提交 202，审核 200。上传是含 Blob 的 multipart，不用于本项 |
| R6 | 审核 | 审核人在审核模式（History bundle）退回（必填理由），工作区指针清空；重新上传、提交后通过；审核顶栏撤回回归 |
| R7 | 上传模式撤回 | §6.3 全部场景 |
| R8 | 归档主线 | 候选 → 首次预检“待确认” → 确认 → 异常处理（若有） → 开始归档 → head 前移，树显示归档基线 |
| R9 | 历史比较 | 两节点与三节点；结果抽屉计数（FE2 kickoff §6.4 D1）；打开 History 差异浏览 |
| R10 | 权限拒绝 | 真实 backend 上覆盖四项，都显示“当前身份没有该操作的权限”与错误码：① 无权限身份上传 403；② 无 Preview 权限的提交人发起 Preview 403；③ 无权限身份打开审核模式时 review 查询 403（发生在页面加载时，不在按钮上）；④ 无权限身份进入归档主线时候选查询 403。提交与上传使用同一个权限（`upload_submit_workspace`），工作区又按 actor 隔离，提交 403 在真实 backend 上产生不了，只由模拟接口覆盖，handoff 说明 |
| R11 | 版本冲突 | 审核版本冲突：另一身份先行动作后，界面提示并刷新，不自动重发；工作区版本冲突一例 |

- Preview、提交等操作在小输入上很快完成，“仍在运行”、刷新后继续轮询与 `MANUAL_RECOVERY_REQUIRED` 继续由模拟接口覆盖，真实 e2e 不强求。
- 浏览器控制台出现未捕获错误即判失败。
- 失败时保存 trace、截图与该次的 Compose 日志；成功时为 R2、R6、R7、R9 的关键页面各存一张参考截图（不作验收，FE4 用 t1 数据重拍）。

### 4.8 清理

1. 停止并删除本次的工具链容器（§4.5）。
2. `docker compose ... logs --no-color --timestamps` 写入日志目录。
3. 执行 `down -v --remove-orphans --rmi local`。backend/worker 没有 `image:` 键，`--rmi local` 只删除本项目的 `<项目名>-backend`、`<项目名>-worker`；RS 有自定义 `image:`，不会被删。
4. 按 `com.docker.compose.project=<项目名>` label 删除残留的卷与网络（同 `compose_gate_harness._teardown_compose_project_resources`）；删除本次 RS tag 与 secret 目录。
5. 核对：没有该项目的容器（含工具链容器）、卷与网络；8000 端口空闲；`/proc` 中没有 dolt 进程。之后才按 §4.2 释放。

不删除共享镜像（依赖镜像、工具链、`gateway-repository-service:local`、client e2e 镜像），不运行 `docker rmi` 或 prune 清理他人资源。
节点上后端 Compose 门禁遗留的 `*-backend:latest`、`*-worker:latest` 镜像不属于前端，不要清理。

### 4.9 日志

日志写在 worktree 外的 `--log-dir`，运行结束后写 SHA256 旁注文件。字段：

- 开头与结尾：hostname、UTC 时间、`git rev-parse HEAD`、`HEAD:frontend` 与 `HEAD:vnext` 树、worktree 是否 clean；结尾记录 exit code；
- 占用标记的获取、释放时间与内容，flock 的获取、释放时间；残留检查结果；
- 工具链镜像身份、npm 缓存归档 SHA256 与来源提交；§4.3 的镜像身份；Compose 项目名、网络 ID 与工具链容器名；
- 运行时 `/openapi.json` 的 SHA256 与比对结果；
- 身份名与权限（不含 token）；播种的仓库 ID 与 `INITIAL` 提交 ID；
- 每个用例的名称、起止时间与结果；
- 清理核对结果；
- t1 套件另记：输入目录的文件数、字节数与逐文件 SHA256 的聚合值；§8.4 的 M1 指标；各步骤耗时与 bundle 的 `Content-Length`、实收字节、`ETag`（只报告）。

以下文件只留在节点上，不写进仓库与 handoff 正文，handoff 只记路径与 SHA256：

- Playwright trace：网络记录中含本次的临时 token（栈清理后失效），也可能含输入数据；
- Compose 日志；
- t1 套件的参考截图：含真实业务值。

## 5. OpenAPI

### 5.1 快照刷新（FE3b）

- 在已合入 BE-a、BE-d 的 `fe-vnext` 上，用 §4 的脚本起栈，取运行中的 `/openapi.json`，规范化后写入 `frontend/openapi.json`。
- **规范化（两处都用）：** 在宿主机用 `python3 -I` 执行 `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"`。
  不用 Node：快照中有 `9007199254740991.0`、`0.0` 这样的浮点写法，`JSON.stringify` 会写成整数，逐字节比较必然失败。
  脚本先核对当前快照按该规则重排后逐字节不变，否则停下，说明规则不对。审核会话已核对当前快照满足。
- 用 `npm run generate:api-types` 重新生成 `src/features/api/generated/openapi.d.ts`；快照与生成类型在同一个提交中更新，提交说明写明来源 main 提交与 vnext 树。
- 刷新快照的运行可以在 05 调试；最终以 04 证据中的运行时比对为准（§5.2）。

### 5.2 与运行中 `/openapi.json` 的比对

- 每次真实 e2e 运行在浏览器用例之前比对。运行时的 `/openapi.json` 在工具链容器内经 preview 服务器的代理读取，顺带证明代理可用；
  两侧都按 §5.1 规范化后逐字节比较。
- 不一致时脚本以非 0 退出，不运行浏览器用例，日志目录保存两份规范化 JSON 与 diff。处理：
  - 差异来自已合入 main、前端尚未刷新的后端改动：按 §5.1 刷新，从头运行；
  - 差异与 §2.3、§6 或 BE-a 设计不符，或出现前端没有预期的 schema 变化：停下交设计会话（§10）。
- FE3a 在当前 backend 上比对，预期一致（快照自 `a2fb4a027a` 起，后端 HTTP 层没有改动）；不一致即停止。

### 5.3 刷新后的同步（FE3b）

按 FE2 kickoff §7.5 的规则同步，规则本身不变：

- **删除 `RETURN_FOR_REVISION`：** 删除 FE2 kickoff §4.1 末段的 `RETURNED_FOR_REVISION` → “已退回”映射及 `client.test.ts` 中的对应用例（AGENTS：删除被替代的实现）；
  `review_status`、事件动作的取值以新生成类型为准。
- **201/202：** `POST /v1/workspaces` 新建 201、已存在 200；`POST /v1/history-compares` 第一次 202、回放 200。
  模拟响应改用各状态码自己的生成类型，删除 FE2 kickoff §7.5“幂等回放”中“响应体用 200 的类型约束”的变通。
- **指针字段：** 全部 `WorkspaceResponse` 模拟数据补 `active_submit_attempt_id`、`active_submission_id`，两者至多一个非空，与场景的生命周期一致
  （BE-a 设计补充 §2 的表；场景注明依据），包括“operation 已到终态、attempt 未结束、指针保留”的场景（§6.2）。
- **新权限与错误：** 错误码单测解析新快照，覆盖 BE-a 新增或变化的状态码与 code（例如 review 查询的 403、404）。
- **模拟身份：** 模拟接口新增“本人撤回”等身份时，同步扩充 `check-production-build.mjs` 的模拟 token 禁用模式（目前为 `dev-token-(?:submitter|reviewer|archive-confirmer|no-permission)`）。
- **bundle 错误码：** BE-d 在 OpenAPI 中列出的 bundle 错误码各有前端文案，加入 FE2 kickoff §7.5 的取值核对；没有列出的不模拟。
- **fixture 的 tar：** FE1–FE2 的 bundle fixture 由前端按前端 kickoff §4.4 的格式在本地拼装 tar。BE-d 若在生产代码中提供可以直接调用、不经 HTTP 的 tar 封装函数，
  生成器改用它；没有时保留现有拼装，由 R2、R3 覆盖，handoff 说明。

### 5.4 生成类型的一致性（FE3a）

增加一项检查：由 `frontend/openapi.json` 重新生成类型到临时目录，与已提交的 `openapi.d.ts` 逐字节相同，否则失败。放进 `run-tests.sh` 的单测阶段或作为单测。

## 6. 接回上传模式顶栏撤回（前端 kickoff §7.1）

### 6.1 状态与文案

数据来源与请求规则见前端 kickoff §7.1：指针非空时调用 `GET /v1/submissions/{id}/review`，撤回携带 `review_version`。
前端不按 actor 推断权限，也不把指针非空当作可撤回：GET review 成功，说明调用方持有两个审核权限之一，再加上 `PENDING`，才可撤回（BE-a 设计补充 §3）。

撤回按钮在上传模式顶栏始终显示（草图 `header-upload`），不可用时禁用并给出原因（F4，§11 Q7）。危险按钮样式、二次确认（X4）、幂等 key 与审核顶栏的撤回相同。
已有的审核顶栏文案（`ReviewActions.tsx` 的 `STATUS_REASON`）沿用，新增的按下表：

| 条件（按顺序判断） | 按钮 | 禁用原因 / 提示 |
| --- | --- | --- |
| `active_submit_attempt_id` 非空，提交操作为 `QUEUED` 或 `RUNNING` | 禁用 | 提交正在执行，完成后才能撤回 |
| `active_submit_attempt_id` 非空，提交操作为 `MANUAL_RECOVERY_REQUIRED`，或已到终态但 attempt 未结束（§6.2） | 禁用 | 提交结果待确认，需要管理员处理 |
| 两个指针都为空 | 禁用 | 当前没有待审核的提交 |
| 正在查询审核状态 | 禁用 | 正在读取审核状态 |
| 查询返回 403 | 禁用 | 当前身份没有撤回权限 |
| 查询返回 404 | 禁用 | 未找到该提交，请刷新后重试（另附“刷新”） |
| 查询失败（临时错误超过重试上限、5xx） | 禁用 | 无法读取审核状态（另附“重试”） |
| `status = PENDING` | 可用 | — |
| `status = APPROVED`，History 中该提交节点带 `NOT_CANDIDATE_BASE_ADVANCED` | 禁用 | 暂定：该提交所基于的基线已更新，不能归档，需要管理员处理。最终文案按后端的处理方式定稿（§12） |
| `status = APPROVED` | 禁用 | 该提交已通过审核，不能撤回 |
| `status = REJECTED` 或 `WITHDRAWN` | — | 撤回或退回后指针会清空（BE-a §2），只有工作区读取过时才会出现。先重新读取一次工作区，再按新状态显示；重新读取后仍是该状态时，显示“该提交已退回”或“该提交已撤回” |

- 403、404 与查询失败都按 C6 在悬停提示中附错误码，可复制。
- **撤回对话框：** 标题“撤回提交”，影响说明与确认勾选沿用审核顶栏的撤回对话框。
- **撤回失败（对话框底部提示区，FE2c R6）：**
  - 409 `REVIEW_VERSION_CONFLICT`、`REVIEW_TRANSITION_CONFLICT`、`WORKSPACE_OCCUPANCY_CONFLICT`：提示“审核状态已变化，已重新读取”。
    同时重新查询工作区与 review，按新状态更新按钮，不自动重发；
  - 403：“当前身份没有撤回权限”；404：“未找到该提交，请刷新后重试”；
  - 其他错误（包括 `IDEMPOTENCY_CONFLICT`）：通用文案“撤回未完成”加错误码（C6）。
- **撤回成功：** 重新读取工作区。指针、当前上传与 Preview 都为空时，离开 Preview 页回到工作台的上传步骤卡，提示“已撤回，可以重新上传”。
- 文案按 FE2 kickoff §4 的原则：只说原因，原始码放悬停提示与 Debug。

**工作区被占用时的“提交”与“上传”：**

- **Preview 顶栏的“提交”：** 任一指针非空时禁用，原因与下表相同。目前只在没有 bundle 或续做期间禁用；指针非空时后端会返回 409 `SUBMIT_OCCUPANCY_CONFLICT`。
- **工作台的“上传”（工具栏与上传步骤卡，§11 Q9）：** 任一指针非空时同样禁用。后端不拦截这时的上传，但上传后：
  - 待审核时，撤回、通过、退回都会因为占用绑定不符返回 409 `WORKSPACE_OCCUPANCY_CONFLICT`：`review_transaction.py` 经 `assert_review_workspace_bindings`（`application/submission/review.py`）核对 generation、当前上传、当前 Preview 与占用。提交人不能撤回，审核人也不能审核；
  - 已通过时，开始归档会清空该工作区的当前上传与 Preview（`application/archive/start.py` 的 `_release_workspaces_for_archive`），刚上传的内容会丢失。

  这是界面决定，不需要后端新增字段。

| 工作区状态 | “提交”与“上传”的禁用原因 |
| --- | --- |
| `active_submit_attempt_id` 非空，提交操作为 `QUEUED` 或 `RUNNING` | 提交正在执行，完成后才能继续 |
| `active_submit_attempt_id` 非空，提交操作为 `MANUAL_RECOVERY_REQUIRED`，或已到终态但 attempt 未结束 | 提交结果待确认，需要管理员处理 |
| `active_submission_id` 非空，`PENDING` | 已有待审核的提交，撤回后才能重新上传 |
| `active_submission_id` 非空，`APPROVED`，History 节点带 `NOT_CANDIDATE_BASE_ADVANCED` | 暂定：该提交所基于的基线已更新，不能归档，需要管理员处理（最终文案见 §12） |
| `active_submission_id` 非空，`APPROVED` | 该提交已通过审核，开始归档后才能重新上传 |
| `active_submission_id` 非空，审核状态读不到（403、查询失败） | 已有提交在处理中，完成后才能重新上传 |

### 6.2 刷新恢复与 `active_submit_attempt_id`

- URL 中的 `operation_id`（FE2 kickoff N2）保持不变，仍是操作卡片与轮询的依据。
- **URL 中操作的类型：** 删除 `sessionStorage` 标记后，以 `GET /v1/operations/{id}` 返回的 `job_kind` 为准
  （`backend-vnext/submit` 或 `backend-vnext/preview`，FE2 kickoff §7.5 取值表）。上传与提交写入 URL 时都用 `operationKind=operation`，不靠参数区分。
- **页面加载或刷新时：** 读取工作区。
  - `active_submit_attempt_id` 非空，URL 中没有该 attempt 的提交操作时，经 `GET .../submit-attempts/{id}` 取 `operation_id`，写入 URL，显示操作卡片并继续轮询；
  - URL 中的操作是提交（按 `job_kind`），但与指针所指 attempt 的 `operation_id` 不同时，以服务器（指针）为准，替换 URL 中的值；
  - 续做卡片显示在刷新时所在的页面：与 FE2c 的续做位置相同，Preview 页在顶栏之上（`ComparisonPage` 的 `comparison-resume` 排在 `compare-header` 之前），工作台在组态树标题下方（`WorkbenchPage` 的 `OperationStatusPanel`）。
- **提交操作到达终态后：** 重新读取工作区与 attempt（`GET .../submit-attempts/{id}`）：
  - attempt 为 `FINALIZED`：指针转为 `active_submission_id`，按 FE2c 已有的提交结果处理；
  - attempt 为 `ABORTED`：两个指针都为空，显示“提交未完成”与原始码（FE2 kickoff §7.5）；
  - operation 已到终态，但 attempt 仍为 `PREPARED` 或 `EFFECT_PENDING`、指针仍非空：显示 FE2c 已有的“需要管理员处理”提示（含操作 ID），不自动重试。
    BE-a 设计补充 §2 规定，执行、等待恢复或结果未知时指针保留，不能按 operation 的终态推断已释放。
- **FE2c 的 `sessionStorage` 提交标记（§11 Q6）：** `gateway-submit-operation`（`SubmitDialog.tsx`、`ComparisonPage.tsx`）只能在同一标签页内找回提交，
  指针可以跨标签页与设备。FE3b 删除该标记，由指针与 `job_kind` 取代（AGENTS：删除被替代的实现）；n3 的失败分支 e2e（§7）随之改为基于指针，覆盖不减。
  上传的 `gateway-preview-operation` 标记不受影响。

### 6.3 必测场景

模拟接口 e2e 与真实 backend e2e（R7）都覆盖，本人撤回用“提交人（本人撤回）”身份，无权限用“提交人（仅上传）”身份：

| # | 场景 | 断言 |
| --- | --- | --- |
| W1 | 本人撤回 | `PENDING` 时按钮可用；确认后撤回成功，回到上传步骤卡 |
| W2 | 撤回后重新上传 | 工作区两个指针、`current_upload_revision_id`、`current_preview_result_id` 都为空；重新上传、Preview、提交成功，指针指向新提交 |
| W3 | 无权限 | 仅上传身份提交后，review 查询 403，按钮禁用且原因为“当前身份没有撤回权限” |
| W4 | 已通过 | 审核人通过后，提交人刷新：`active_submission_id` 仍非空，撤回禁用且原因为“该提交已通过审核，不能撤回”；“上传”禁用且原因为“该提交已通过审核，开始归档后才能重新上传” |
| W5 | 冲突刷新 | 撤回对话框打开后，审核人先撤回或退回（真实 e2e，两个 context 同时在线）或模拟 `REVIEW_VERSION_CONFLICT`（模拟接口）；界面重新读取后按新状态显示，不自动重发 |
| W6 | 提交执行中与结果待确认 | `active_submit_attempt_id` 非空时撤回、“提交”与“上传”都禁用；刷新后按 §6.2 找回操作卡片；operation 终态而 attempt 未结束时显示“需要管理员处理”。只用模拟接口覆盖（真实 backend 上提交很快完成），handoff 说明 |
| W7 | 回归 | 审核人在审核顶栏撤回，行为与 FE2c 相同 |
| W8 | 待审核时不能上传 | `PENDING` 时工作台“上传”禁用，原因为“已有待审核的提交，撤回后才能重新上传”；撤回后恢复可用 |

模拟数据按 BE-a 设计补充 §2 的生命周期表构造指针，按 FE2 kickoff §7.5 的“后端可达状态”规则核对跨响应关系，场景注明依据。
REJECTED、WITHDRAWN 两行按“读取工作区之后被退回或撤回”的竞争构造。
“已通过、基线已前移”（§6.1 暂定的一行）的场景与断言，在后端定下处理方式后补入本表（§12），按后端实际行为构造，并在真实 e2e 中能走到时一并覆盖。

## 7. FE2 带入项（FE2 kickoff §6.5）

| ID | 子阶段 | 内容与完成标准 |
| --- | --- | --- |
| M7 | FE3a | 提交对话框的摘要不显示原始 ID：History 节点用组态树中的显示名（由前端从 History 推导，例如“当前基线（归档基线 2）”“提交 2”）；Preview 结果显示“本次预览”。拿不到显示名时才显示 ID。原始 ID 放悬停提示与 Debug（C6）。单测覆盖有、无显示名两种情况；重拍提交对话框截图（`submit-*` 中显示摘要的各张）。**基线序号（§11 Q11）：** 组态树与摘要共用同一个标签函数（`view-model/workspace.ts` 中的规则移出，`submit-summary.ts` 不再复制）。`ARCHIVED_SUBMISSION` 基线在树上也显示为“归档基线 n”：n 按 `created_at` 升序从 1 编号，同时刻时按 `ref_id`，与“提交 n”的编号方式相同；`INITIAL` 仍为“初始基线”，不编号。“当前基线”仍是状态标签，摘要写成“当前基线（归档基线 n）”或“当前基线（初始基线）”。单测覆盖多个归档基线的编号；组态树截图随之变化，审核对照草图（草图本来就带序号） |
| n3 | FE3a | e2e（模拟接口）覆盖续做时 `ABORTED` 与读取失败的提示，以及续做期间“提交”按钮禁用并显示原因。FE3b 删除 `sessionStorage` 标记后，这些用例改为基于指针，覆盖不减 |
| n8 | FE3a | “需要管理员处理”一行：ID、“复制 ID”与正文分开排版，使用同一区域其他提示的提示样式；重拍 `submit-manual-recovery-1280/1920` |
| M1 | FE3a 测量；FE3b 复测，需要时改流式 | 见 §8.4 |

## 8. t1 真实数据旅程（FE3b）

### 8.1 输入

- 需要组态目录原件（§2.2）：t1 v1、v2 即开发主机的 `small_cut/small_cut-1`、`small_cut-2`。节点上的源包没有 `.pmc`，浏览器上传会在校验阶段拒绝；
  不用源包加占位 `.pmc` 代替：那样不是用户的真实目录，M1 的测量也没有意义。
- **传输（owner 2026-11-05 原则同意，§11 Q2）：** 由 FE3a 实施会话在本文经 owner 确认后执行：
  - 经获准的局域网把上述两个目录传到 05 的 `/home/dev/gateway-real-dumps/source-dirs/t1-v1`、`t1-v2`；
  - M1 另需 t4 v1 的 `large/large-1`（约 317 MB，528 个文件），传到 `source-dirs/t4-v1`。FULL 测量把它同时用作 ① 和 ②，不需要 `large-2`；
  - 传输后生成逐文件 SHA256 清单及其聚合值，清单文件留在节点上，其 SHA256 写入 handoff；
  - 核对 `sql/dbcfg.sql`、`comps/logic/logics.xml` 与同档源包成员的 SHA256 一致；
  - 工具链容器以 root 运行，`chmod` 防不住写入，因此一律以只读 bind mount（`:ro`）挂进容器。
- 传输完成前，t1 旅程与 M1 测量都不能开始。

### 8.2 节点与步骤

- 节点 05（DC36：t1–t3 在 05），按 §4.2 获取占用；与后端在 05 上的 t1 等运行互斥。
- `--suite t1 --input-root /home/dev/gateway-real-dumps/source-dirs`，一个独立 scope。步骤按后端 t1（`real_dump_journey.py`）的主线顺序，
  省略 repeat-v1（同一输入重复上传）；历史比较改用三节点。两者并不逐步对应：
  1. 提交人：工作区 → 选择 t1 v1 目录 → MODIFIED_ONLY 上传（基于空的 `INITIAL`） → Preview → 下载并浏览（全部为新增表） → 提交；
  2. 审核人：审核模式下载 History bundle → 通过；
  3. 归档确认人：归档主线 → head 前移到 v1；
  4. 提交人：选择 t1 v2 目录 → MODIFIED_ONLY 上传 → Preview → 下载并浏览差异 → 提交；
  5. 审核人：通过；
  6. 审核人：历史比较三节点（`INITIAL`、归档 v1、v2 提交） → 打开结果浏览。
- FULL 上传、退回、撤回等已由 §4.7 覆盖，t1 不重复。

### 8.3 通过标准

全部由程序判定，读取下载到的 bundle manifest 中 `pairs[].summary` 的四个汇总数：`table_count`、`changed_table_count`、`degraded_table_count`、`failed_table_count`。

- **预期值的来源：** 从被测候选同一 vnext 树的 `vnext/backend/benchmarks/real_dump_journey.py` 读取，不手抄。
  在宿主机用 `python3 -I` 的 `ast.literal_eval` 读取模块级常量 `S2B_DATASET_BASELINE` 与 `S1B_V2_PREVIEW_CHANGED_COUNTS`；读不到即停止。
  前端上传的是整个目录（19 个文件），后端忽略 Contract 以外的成员；后端 t1 上传的是规范化源包。两者的 `dbcfg.sql` 与 `logics.xml` 逐字节相同（§2.2），因此预期值可以直接沿用。
- **v1 Preview：**
  - `table_count = changed_table_count = S2B_DATASET_BASELINE["rd-t1-a-v1"]["preview_table_count"] + 1`。+1 是派生表 `composite_signal_point`，按 `main` 当前值为 124 + 1 = 125；
  - `degraded_table_count = failed_table_count = 0`。
  - 依据：`_assert_s1b_preview_summary`。
- **v2 Preview：**
  - `table_count` 等于 `S2B_DATASET_BASELINE["rd-t1-a-v2"]["preview_table_count"] + 1`；`degraded_table_count = failed_table_count = 0`；
  - `changed_table_count = S1B_V2_PREVIEW_CHANGED_COUNTS["rd-t1-a-v2"] + composite_changed`。前一项按 `main` 当前值为 4；
    `composite_changed` 为 1 或 0，前端按同一 bundle 中 `composite_signal_point` 的状态是否属于 `UNCHANGED`、`BUSINESS_EQUIVALENT` 取值。
    这样只能独立核对派生表以外变化的表数（4）；后端 t1 的 `composite_changed` 来自离线投影，与 Preview 无关；
  - 派生表本身是否变化，只在有对照时独立核对：同一 vnext 树上有后端 t1 运行（BE-d 的 05 t1）结果时，核对两者的 `composite_changed` 相同；取不到时 handoff 记录实际值，并注明没有对照。
- 每一步在浏览器中完成，没有未捕获错误；每次下载都通过 tar 成员与摘要校验。
- 有诊断时，界面显示对应文案而不是通用文案（FE2 kickoff §5.5），handoff 列出出现过的编码。
- 各步骤耗时、bundle 体积与下载耗时只报告，不设门槛。05 不是计时参考节点，这些数字不作为性能证据（DC36）。
- 关键页面（工作台、v2 Preview 差异浏览、审核模式、历史比较结果）在 1280 与 1920 下各存参考截图，只留在节点上，SHA256 写入 handoff；不作验收，FE4 重拍（前端 kickoff §6）。

### 8.4 M1：打包峰值内存

- **测量内容：** 目录字节数与文件数、压缩后包大小、打包耗时，以及打包期间 Chromium 各进程的内存峰值。
- **场景：**
  - MODIFIED_ONLY：只打 ② 一个包；
  - FULL：先打 ①，再打 ②（`UploadStepCard`）。打 ② 时 ① 的压缩包还在内存中；`buildTar` 先存一份文件内容，再拼一份整包。FULL 是更可能超标的场景。
  - t1 v1 测 MODIFIED_ONLY；t4 v1 测 MODIFIED_ONLY 与 FULL（① 和 ② 都用 `large-1`）。
- **测量方法：**
  - **新浏览器：** 每次测量启动一个新的浏览器实例；
  - **进程：** 经浏览器级 CDP 会话（`browser.newBrowserCDPSession()`）调用 `SystemInfo.getProcessInfo` 取各进程 PID。这是实验性接口，拿不到时，从浏览器主进程向下遍历 `/proc` 中的子进程，
    按命令行中的 `--type=` 区分。Playwright 默认关闭 Chromium 沙箱，得到的 PID 就是工具链容器内 `/proc` 中的 PID；
  - **记录全部进程：** renderer、browser 主进程、utility/network、GPU。`new File([bytes])` 的数据交给浏览器主进程的 Blob 存储，上传时由网络服务进程读取。主指标是 renderer；
  - **峰值清零：** 页面加载本身会抬高峰值。在“确认上传”之前，对每个进程向 `/proc/<pid>/clear_refs` 写入 `5`，把 `VmHWM` 清零，并记录此时的 `VmRSS` 作为基线；
    上传请求发出后（打包已完成）读取 `VmHWM`。峰值增量 = `VmHWM` − 基线；
  - `setInputFiles` 选择目录时，本地启动的浏览器只拿到文件路径，选择目录不会复制文件内容；读取发生在 `file.arrayBuffer()`；
  - `performance.memory`（`--enable-precise-memory-info`）只作参考，它不含 `ArrayBuffer` 的外部内存；
  - **包大小：** 路由拦截通常拿不到含 Blob 的 multipart 请求体，因此从 multipart 中 `manifest` 部分的 `size_bytes` 读取（前端在 `client.ts` 中按 `File.size` 填写）。实施时先验证可行；
  - **打包耗时：** 用上传步骤卡已有的阶段计时（`begin("packaging")` 到下一阶段开始）。“确认上传”到上传请求发出之间还含 CreateOrGet 与 `sha256`，不作打包耗时；
  - 每个目录、每个场景测 3 次，报告中位数与最大值。
- **FE3a：** 在 05 上用模拟接口测量（开发构建，路由拦截上传请求，不需要 backend 与占用标记）。测量用独立的 Playwright 配置与提交的脚本，结果写入 handoff。
- **FE3b：** 在 t1 旅程中用生产构建对 t1 v1、v2 再测一次，与 FE3a 对照。
- **判断（§11 Q3）：** 由审核会话与 owner 看数据决定。默认标准对 MODIFIED_ONLY 与 FULL 都适用：
  - t4 v1 的 renderer 峰值增量不超过 1 GiB；
  - 按目录大小线性外推到前端上限 1 GB 时不超过 3 GiB。

  任一不满足即在 FE3b 改为流式打包（逐文件读取、边打包边压缩，不在内存中攒整包），FE2 kickoff §7.1 的后端校验继续接受产物，改后重测。
- **FE3a 的结论（owner 2026-11-05，§11 Q12）：**
  - **判定：** 只看 renderer。t4 v1 renderer 峰值增量最大 676.3 MiB（审核复测 668.2 MiB），线性外推到 1 GB 约 2.08 GiB，两项都满足。
    FE3b 不改流式，除非 FE3b 复测时 renderer 不满足上面的标准。
  - **浏览器主进程：** 作为报告项，不参与判定。FE3a 实测：MODIFIED 时增加约 200 MiB，FULL 时约 420 MiB，约为每读一遍目录 0.65 倍目录大小。两进程合计外推到 1 GB 约 3.4 GiB。
  - **理由：**
    - renderer 是持有 `ArrayBuffer`、内存不足时崩溃的进程；
    - 64 位桌面版 Chromium 的浏览器主进程 Blob 存储在内存中最多 2 GiB，超过后写入磁盘（`storage/browser/blob/blob_memory_controller.cc`）；
    - 主进程的增量远大于压缩包（约 20 MB），更可能来自读取文件，改流式打包未必能降低它，因此不宜用它决定是否改流式；
    - 用户机器内存按 16 GB 及以上估计（owner），合计约 3.4 GiB 的峰值可以接受。
  - **FE3b 复测补充：** 打包期间约每 100 ms 采样一次各进程 `/proc/<pid>/status` 的 `RssAnon`、`RssFile`、`RssShmem`，报告各项最大值，以确认主进程的增量是否属于可回收的文件页；
    只报告、不作判定。`VmHWM` 增量的方法不变。

## 9. 证据

| 子阶段 | 节点 | 内容 | 计时 |
| --- | --- | --- | --- |
| FE3a | 04 | `run-tests.sh --e2e --screenshots <目录>`（全量模拟接口，含截图）；上传包后端校验脚本；`run-real-backend-e2e.sh --suite smoke`。各一次，在 clean、已提交的 detached worktree 上 | 否 |
| FE3a | 05 | M1 打包测量（§8.4） | 否（只报告） |
| FE3b | 04 | 同 FE3a 的前两项；`--suite journeys` 一次（含运行时 OpenAPI 比对） | 否 |
| FE3b | 05 | `--suite t1` 证据运行一次（含 M1 复测与参考截图） | 否（只报告） |

- 调试与取证分开（DC30）：
  - 05 调试只跑 focused 与出问题的那一段；
  - 04 证据只在审核通过后运行一次；
  - FE3b 的 t1：实施会话 handoff 前在 05 上的运行属于调试。证据在审核通过后，于最终候选的 clean、已提交 worktree 上运行一次，与 04 取证同一时点；
  - FE3a 的 M1 是测量，不是门禁：在送审候选上测量，handoff 记录所用提交，供审核复核；审核要求的修复如果改动打包代码（`upload-package.ts`、`UploadStepCard.tsx`），在新候选上重测。
- 04、05 的运行日志、截图与 trace 都在 worktree 外的证据目录，记录 SHA256；handoff 记录工具链与依赖镜像身份、npm 缓存来源、运行节点。
- **需要重拍并交 owner 看图确认的截图：**
  - FE3a：M7 的提交对话框各张；n8 的 `submit-manual-recovery-1280/1920`；
  - FE3b：§6 的各状态，即上传模式顶栏的撤回可用，以及 §6.1 表中的每种禁用状态各一张；
    上传模式撤回对话框、撤回冲突提示、撤回成功后的上传步骤卡；W8 中工作台上传的禁用状态；快照刷新后显示有变化的截图。
- 真实 backend 与 t1 的参考截图只作参考；FE4 用真实 backend 与 t1 数据重拍关键页面（前端 kickoff §6，节点见 §12）。

## 10. 实施会话的停止条件

除 AGENTS、前端 kickoff 与 FE2 kickoff §10 已有的规则外：

- 合入后的接口与 §2.3、§6 或 BE-a 设计补充不符，或运行时 OpenAPI 出现前端没有预期的变化（§5.2）；
- 真实 e2e 发现后端缺陷，或后端不接受 §4.6 的输入：保留日志与 trace，交设计会话与后端设计会话处理；不在前端绕过，不改 `vnext/`；
- 需要后端新增字段或接口；
- 依赖镜像、RS 依赖镜像、工具链镜像或 npm 缓存缺失，身份或 label 不符，或构建需要访问网络；
- 运行需要修改 `vnext/` 下的 Compose、脚本或配置；
- t1 或 M1 的输入未传输或核对不符（§8.1），或 §8.3 的预期值读不到；
- 清理核对失败（§4.2）。

脚本自身的错误按 DC68 重做一次；被测对象运行后的失败不按 DC68 重做。

## 11. owner 决定（2026-11-05）

Q1–Q9 均由 owner 于 2026-11-05 确认，按下表的建议执行。Q1–Q7 经 kickoff 审核（`920f068da4`）逐条判断成立；Q9 经定向复审（`e91d9db6eb`）核对成立。

| # | 事项 | 决定 |
| --- | --- | --- |
| Q1 | 阶段安排（§3） | 乙：FE3a 现在开始，FE3b 在 S2a、BE-a、BE-d 合入后开始；tag、范围与退出条件按 §3.2 |
| Q2 | t1 输入（§8.1）：节点上没有组态目录原件 | 把 `small_cut-1`、`small_cut-2`（各 19 个文件、约 6.9 MB）与 `large-1`（528 个文件、约 317 MB，只用于 M1）经局域网传到 05 的 `source-dirs/`，只读挂载，并记录 SHA256 清单。不用源包加占位 `.pmc` 代替 |
| Q3 | M1 的测量与判断（§8.4） | FE3a 用 t1 与 t4 目录测打包内存（t4 测 MODIFIED_ONLY 与 FULL），FE3b 在 t1 旅程中复测；默认标准按 §8.4，对两种模式都适用，不满足即在 FE3b 改流式 |
| Q4 | 真实 e2e 的入口（§4.1） | 单独提交的脚本，不并入 `run-tests.sh` |
| Q5 | 真实 e2e 的被测构建与身份注入（§4.5） | 测生产构建；身份由 Playwright 按 context 注入 `window.__gatewaySession`，token 每次随机生成，不进入构建产物 |
| Q6 | FE2c 的 `sessionStorage` 提交标记（§6.2） | 由 `active_submit_attempt_id` 与 `job_kind` 取代并删除；URL 中的 `operation_id` 保留 |
| Q7 | 上传模式顶栏撤回的显示（§6.1） | 始终显示，不可用时禁用并给原因（与 F4 一致）；文案按 §6.1 |
| Q8 | 目录传输晚于 FE3a 其余工作时，FE3a 能否先退出（审核报告 O1） | **已决定（owner 2026-11-05）：** M1 测完才能退出 FE3a；传输迟迟不能完成时，由 owner 另行决定是否把 M1 移到 FE3b（§3.2） |
| Q9 | 工作区被占用时是否禁用上传（审核报告 D2，§6.1） | 任一指针非空时禁用“上传”与“提交”，原因按 §6.1 的表。否则待审核时上传会使撤回与审核都返回 409，已通过时上传的内容会在开始归档时被清空 |

Q10–Q12 来自 FE3a 审核（`a0b9604ddd`），由 owner 于 2026-11-05 确认（§15.1）。

| # | 事项 | 决定 |
| --- | --- | --- |
| Q10 | 真实 e2e 的上传输入（审核报告 §6、B10）：共用 SQL 含没有 `gid` 列的 `b1_n1_iec104_yc_list`，真实 Preview 返回 `KEY_MISSING` | FE3a 调试中（2026-11-05，`0712368347` 之后），实施会话按 §10 停下，owner 直接答复实施方：新增真实 e2e 专用的合法输入，模拟 fixture 不动。当时没有书面记录，本次补记。来源规则、四类上传与 FE3a 的核对按 §4.6 |
| Q11 | 组态树的基线是否显示序号（审核报告 N2） | 甲：树也显示“归档基线 n”，与摘要共用同一个标签函数，在 FE3a 做（§7 M7） |
| Q12 | M1 的判定是否只看 renderer（审核报告 §5） | 只看 renderer，FE3a 满足，FE3b 不改流式；浏览器主进程只报告，FE3b 复测时补记 `RssAnon`、`RssFile`、`RssShmem`。用户机器内存按 16 GB 及以上估计（§8.4） |

## 12. 开放项

| 项 | 说明 | 何时 |
| --- | --- | --- |
| 基线已前移后才通过的提交永久占用工作区（定向复审 §4） | 见 §2.1 协调建议。经 owner 转后端设计会话，在 BE-a 实施前决定处理方式；前端据此定稿 §6.1 中暂定的一行，并按后端行为补模拟场景与真实 e2e。前端不在界面上绕过（例如不提供前端自造的“关闭”） | BE-a 实施前；FE3b 前置条件 |
| tar 成员与 closure 的对应（审核报告 D1） | 见 §2.3 最后一行，经 owner 转后端设计会话，在 BE-d kickoff 审核中确认 | BE-d kickoff 审核 |
| FE4 真实数据重拍的节点 | 前端 kickoff §6 写“FE4 在 04 上用真实 backend 与 t1 数据重拍”，但 DC36 规定 t1–t3 在 05。建议 FE4 kickoff 时改为：t1 数据的重拍在 05，04 只跑合成输入的真实 backend e2e；如需在 04 使用 t1 数据，由 owner 作例外决定 | FE4 kickoff |
| 首批空基线（FE2 kickoff Q18） | 仍为缺口，不在 FE3。FE3 的输入都从空的 `INITIAL` 开始，界面不禁用第 ① 步 | 后端提供该事实后 |
| P6 计时与整包下载（DC74 草案） | t1 旅程的下载耗时与体积只报告；DC74 确认后，按其结论更新前端 kickoff §9 | DC74 确认后 |
| AGENTS 与 testing-conventions 的真实 e2e 条文 | FE3a handoff 写出建议条文，由 owner 转治理会话（§4.1） | FE3a 退出时 |

## 13. 实施与审核提示词

以下提示词在各自的前置条件满足、并经 owner 确认后由设计会话发出（或由 owner 转发）。发出时填写方括号中的值。

### 13.1 FE3a 实施（前置：本文经 owner 确认，§11 全部决定已记录）

> 你是 FE3a 前端实施会话。先读 AGENTS、[前端 kickoff](frontend-kickoff.md)（§4、§6、§7）、[FE2 kickoff](fe2-kickoff.md)（§6.5、§7、§10）、本文（main `[确认提交]`）全文、[本文的 kickoff 审核](reviews/fe3-kickoff-review.md)，以及 FE2c 复审第 4 轮与证据核对第 1 次。
>
> - **起点与分支：** `fe-vnext`（`fe-fe2c-exit` = `749f219d5f`）。先把 main `[确认提交]` 合入 `fe-vnext`（只合并，不 rebase），在开发主机 worktree `/home/dev/gdds-fe` 开发；源码经 git bundle 传到节点，在 clean、已提交的 detached worktree 中运行。
> - **先做两项准备：**
>   - 按本文 §8.1 把 t1 v1、v2 与 t4 v1 的组态目录原件传到 05，生成 SHA256 清单并核对；
>   - 按本文 §4.3 把 `gateway-backend-deps:lock-c668cef8e47e` 补到 05：在开发主机 clean worktree 用 `build-backend-dependency-base.sh --save`，传输后核对身份。
>
>   两项都在 handoff 中记录。
> - **范围（本文 §3.2 FE3a 一行）：**
>   1. §7 的 M7、n3、n8；
>   2. §4 的真实 backend e2e 运行框架与 `--suite smoke`（判据见 §3.3）；
>   3. §4.6 的上传输入（SQL 与 `logics.xml` 移到共用文件，fixture 逐字节不变；写出每个 scope 的上传序列），调试开始时先在 05 上让真实 backend 走一遍这些输入；
>   4. §5.4 生成类型一致性检查；
>   5. §8.4 的 M1 打包测量（t1 v1 MODIFIED_ONLY；t4 v1 MODIFIED_ONLY 与 FULL）。M1 测完才能退出 FE3a（§11 Q8）。
> - **不做：** 不改 `vnext/`；不刷新 OpenAPI 快照（FE3b）；不做 §6。
> - **节点：**
>   - 调试在 05。在 05 上运行时，npm 缓存路径按 §2.2 设置；
>   - 真实 e2e 按 §4.2 获取占用标记（会话名 `fe3a-impl`）与 `flock -n`，并完成清理核对；
>   - 某节点占用标记的用途为计时测量时，在该节点上的任何运行都等待。
> - **停止条件：** 本文 §10。脚本自身错误按 DC68 重做一次。
> - **交付：** 05 上完整运行 `run-tests.sh --e2e --screenshots` 与 `--suite smoke` 各一次通过后，提交代码候选与 handoff（`docs/frontend-vnext/fe3a-handoff.md`）。handoff 包括：
>   - 改动清单与完成标准的逐条对应；
>   - 运行框架的使用说明；
>   - 各次运行的节点、日志路径与 SHA256、镜像与缓存身份；
>   - 依赖镜像与组态目录的传输记录；
>   - 每个 scope 的上传序列；
>   - M1 数据（所用提交、各场景 3 次的结果、中位数与最大值，以及按 §8.4 标准的判断）；
>   - 截图清单；
>   - 给 AGENTS 与 testing-conventions 的建议条文（§4.1）；
>   - 偏差与未决事项。
>
>   不在 04 上运行，04 取证在审核通过后进行。

### 13.2 FE3a 审核（前置：FE3a handoff 已提交）

> 你是 FE3a 审核会话（不与实施会话为同一会话）。审核 `fe-fe2c-exit..[FE3a handoff 提交]`，其中来自 main 的提交不在前端审核范围内；先按本文 §3.2 的“路径核对”检查候选。依据：本文（main `[确认提交]`）§3.2、§3.3、§4、§5.4、§7、§8.1、§8.4、§10，FE2 kickoff §7，AGENTS“前端测试（FD7）”。
>
> 重点：
> 1. **运行框架：** 符合 §4，包括：
>    - 不修改 `vnext/`；构建设置符合 AGENTS；RS 依赖镜像核对、禁网与 `--no-build`；不覆盖共享 tag；
>    - 占用（会话名）与 `flock -n` 的获取、释放顺序；失败与中断时的清理，工具链容器先删；清理核对失败时保留标记；
>    - token 不进入构建产物与脚本日志，trace 只留在节点上；
>    - 多 scope 播种的 key 与节点 ID 互不相同；日志字段齐全。
>
>    在 05 上用已提交的一次性 worktree 做探针（会话名 `fe3a-review`）：
>    - 让占用目录预先存在：脚本应退出，且不触碰他人资源；
>    - 运行中途中断：应完成清理，无残留（含工具链容器与网络）；
>    - 改动快照一处：运行时比对应失败，且不运行浏览器用例。
> 2. **冒烟：** 覆盖 §3.3“FE3a 可以验证”的各项，判据由程序断言；不为 bundle 下载失败写断言。
> 3. **上传输入：** fixture 逐字节不变（重新生成并比较）；真实 backend 接受全部输入；上传序列中每次提交都有规范变化。
> 4. **带入项：** M7、n3、n8 的完成标准。截图对照草图与 FE2 kickoff §7.3 的原则。
> 5. **M1：** 测量方法符合 §8.4（新浏览器、`clear_refs` 清零、全部进程、包大小与打包耗时的取法、3 次）；数据可复核；按 §11 Q3 的标准给出建议。
> 6. **传输记录：** 组态目录与依赖镜像的传输与核对记录完整。
> 7. **独立运行：** 在 05 上独立运行一次 `run-tests.sh --e2e --screenshots` 与 `--suite smoke`。
>
> 报告写入 `docs/frontend-vnext/reviews/fe3a-review.md`，结论为通过、定向修复或停止；需要设计决定的事项标注“交设计会话”。通过后指明 04 取证项（本文 §9 FE3a 行），取证后做证据核对。

### 13.3 FE3b 实施（前置：S2a、BE-a、BE-d 都已合入 main，§12 基线前移问题已由后端定下处理方式，FE3a 已退出，owner 确认发出）

> 你是 FE3b 前端实施会话。先读 AGENTS、前端 kickoff（§4.3、§4.4、§7.1）、FE2 kickoff §7.5、本文（main `[确认提交]`）全文、FE3a 的 handoff 与审核报告，以及后端 BE-a 设计补充（`f20f08bea9`）、BE-a 合入提交 `[BE-a 合入提交]` 与 BE-d 合入提交 `[BE-d 合入提交]` 的 handoff。
>
> - **起点：** `fe-fe3a-exit`。把 main `[合入 BE-a、BE-d 后的 main 提交]` 合入 `fe-vnext`；之后按本文 §3.2 做路径核对。
> - **范围（本文 §3.2 FE3b 一行）：**
>   1. §5 快照刷新与同步；
>   2. §6 上传模式撤回，含工作区被占用时禁用“提交”与“上传”、§6.2 的刷新恢复与 `job_kind`、删除 `sessionStorage` 提交标记；
>   3. `--suite journeys` 的 R1–R11（§4.7），身份按 §4.6 补 `withdraw_own_submission`；
>   4. §8 t1 旅程；
>   5. M1 复测（§8.4，含 `RssAnon`、`RssFile`、`RssShmem` 采样）；只有 renderer 不满足标准时才改流式打包（§11 Q12）。
>   6. 真实旅程的上传按 §4.6 的 A–D，写出每个 scope 的上传序列，并证实 §4.6 中“留给 FE3b”的各项。
> - **先核对接口：** 运行时 OpenAPI 与 §2.3、§6 的预期一致，tar 成员与 closure 的对应符合 BE-d 的结论；不一致按 §10 停止，交设计会话。
> - **节点：**
>   - 真实 e2e 调试与 t1 都在 05，均按 §4.2 获取占用（会话名 `fe3b-impl`）；
>   - 依赖镜像按 §4.3 用 `--print-input` 与 label 核对，缺失即停止并报告；
>   - 某节点占用标记的用途为计时测量时，在该节点上的任何运行都等待。
> - **停止条件：** 本文 §10。真实 e2e 发现的后端缺陷交设计会话与后端设计会话，不在前端绕过。
> - **交付：** 05 上 `run-tests.sh --e2e --screenshots`、`--suite journeys`、`--suite t1` 各一次通过（均为调试运行）后，提交代码候选与 handoff（`docs/frontend-vnext/fe3b-handoff.md`）。handoff 包括：
>   - 快照来源（main 提交与 vnext 树）；
>   - §6.3 W1–W8 与测试的对应；
>   - R1–R11 的结果，以及只由模拟接口覆盖的项及原因；
>   - t1 通过标准的逐条核对（§8.3），以及与后端 t1 的对照或其缺失说明；
>   - M1 数据与结论；
>   - 截图清单与偏差；
>   - 各次运行的节点、日志 SHA256 与镜像、缓存身份。
>
>   04 取证与 05 的 t1 证据运行在审核通过后进行（§9）。

### 13.4 FE3b 审核（前置：FE3b handoff 已提交）

> 你是 FE3b 审核会话。审核 `fe-fe3a-exit..[FE3b handoff 提交]`：来自 main 的提交与 `vnext/` 不在前端审核范围；先按本文 §3.2 的“路径核对”检查候选。依据：本文（main `[确认提交]`）§2.3、§4.7、§5、§6、§8、§9、§10，前端 kickoff §7.1，FE2 kickoff §7.5，BE-a 设计补充 §2–§4。
>
> 重点：
> 1. **快照：** 与运行时逐字节一致（Python 规范化）；`RETURNED_FOR_REVISION` 映射已删除；201/202 不再使用变通；模拟数据的指针符合 BE-a 生命周期表（含 operation 终态而 attempt 未结束的场景）；
>    错误码单测覆盖新状态码；生产构建检查覆盖新增的模拟 token。
> 2. **§6：**
>    - 文案与 §6.1 一致；
>    - 前端没有按 actor 或指针推断可撤回；没有按 operation 终态推断指针已清空；撤回使用 `review_version`；冲突后不自动重发；
>    - 工作区被占用时“提交”“上传”禁用；URL 中操作的类型按 `job_kind` 判断；删除 `sessionStorage` 标记后，n3 的覆盖不减少。
> 3. **测试与探针：** §6.3 W1–W8 都有对应用例（W6 只在模拟接口）；本人撤回没有用审核人或全权限身份。在 05 上用已提交的一次性 worktree 做探针（会话名 `fe3b-review`）：
>    - 把撤回的预期版本改为工作区版本：真实 e2e 应失败（先确认场景中两个版本的取值不同）；
>    - 去掉 403 分支：W3 应失败。
> 4. **旅程：** R1–R11 符合 §4.7，R10 的四项在真实 backend 上覆盖。t1 按 §8.3 核对：预期值从同一 vnext 树读取，四个汇总数由程序判定。复核 M1 数据与结论。
> 5. **运行：** 在 05 上独立运行一次 `--suite journeys`。t1 不要求审核会话重跑，只核对日志与参考截图的 SHA256。
>
> 报告写入 `docs/frontend-vnext/reviews/fe3b-review.md`。通过后指明 04 取证项与 05 的 t1 证据运行（本文 §9 FE3b 行），取证后做证据核对，并给出 FE3 退出建议。

## 14. 不在 FE3 范围

- BE-b 的分组、列展示、Preview 改前公式与行定位产物（FE4）。
- 首批空基线（FE2 kickoff Q18）。
- Preview 顶栏的上传快捷入口、历史比较结果抽屉布局、1280 下提交对话框滚动：已接受为 FE2 的偏差（FE2 kickoff Q19），FE3 不再处理。
- 正式 SSO、部署形态、外部驱动通道、深色主题。

## 15. kickoff 审核与定向复审意见的处理（`920f068da4`、`e91d9db6eb`）

| 意见 | 处理 | 位置 |
| --- | --- | --- |
| B1 t1 表数与对照 | 改为从同一 vnext 树读取预期值，核对四个汇总数 | §8.3 |
| B2 冒烟走不到的两项与判据 | 删去归档候选界面（移入“要等 BE-d”）；403 限于上传与 Preview；写明 Preview 结果的判据 | §3.3 |
| B3 R10、R5 | R10 改为四项，新增无 Preview 权限的身份，提交 403 只由模拟接口覆盖；R5 回放状态码按 route | §4.6、§4.7 |
| B4 提交失败后的指针 | 按 attempt 状态处理，增加“结果待确认”；URL 中操作的类型按 `job_kind`；写明续做卡片位置；模拟场景补充 | §6.1、§6.2、§5.3 |
| N1 05 的 npm 缓存 | 改正路径，新脚本使用同样的变量 | §2.2、§4.1 |
| N2 tar 前提 | 写明前端的前提，交 BE-d 确认（D1） | §2.1、§2.3、§12 |
| N3 RS 构建 | 核对 RS 依赖镜像、禁网、全部 `up --no-build` | §4.3、§4.4 |
| N4 依赖镜像传输 | 按 AGENTS 的 `--save` 流程；FE3b 按 `--print-input` 核对 | §4.3 |
| N5 身份记录的比例化 | 每次运行记录 label、image ID 与层；config digest 与 DiffID 在传输时比较 | §4.3 |
| N6 项目名小写 | 写明 | §4.4 |
| N7 工具链容器 | 固定名称与 label，清理时先删，残留检查包括它 | §4.2、§4.5、§4.8 |
| N8 每个身份一个 context | 写明，含 OPFS 隔离 | §4.5 |
| N9 trace 中的 token、t1 截图 | 改正说法，t1 截图只留在节点上 | §4.4、§4.9、§8.3 |
| N10 OpenAPI 经代理读取 | 写明 | §5.2 |
| N11 身份文件、`actor_id`、多 scope 播种 | 写明 | §4.6 |
| N12 上传输入 | `logics.xml` 移到文件；上传序列；replacement 输入；05 上先走一遍 | §4.6 |
| N13 Python 规范化 | 写明，固定 `ensure_ascii=True` | §5.1 |
| N14 生产构建检查、占用时禁用提交 | ① 补入 §5.3；② 补入 §6.1；上传是否禁用按 D2 处理（§11 Q9） | §5.3、§6.1 |
| N15 REJECTED/WITHDRAWN 两行 | 先重新读取工作区，再按新状态显示；模拟场景按竞争构造 | §6.1、§6.3 |
| N16 W5 两个 context、探针前提 | 写入 W5 与 13.4 | §6.3、§13.4 |
| N17 t1 步骤与后端的关系 | 改为“按主线顺序，省略 repeat-v1，历史比较用三节点” | §8.2 |
| N18 传输执行者与只读挂载 | 写明由 FE3a 实施会话执行，只读 bind mount | §8.1 |
| N19 M1 方法 | 补 FULL、全部进程、`clear_refs`、包大小与打包耗时的取法 | §8.4 |
| N20 t1 证据的时点 | 写明调试与证据的区别 | §9 |
| N21 / O1 | owner 决定：M1 测完才能退出 FE3a | §3.2、§11 Q8 |
| N22 路径核对 | 改为树相等加路径白名单，两个子阶段都做 | §3.2 |
| N23 占用用词与会话名 | 改正，规定会话名 | §4.2 |
| N24 AGENTS 条文 | FE3a handoff 写出建议条文 | §4.1、§12 |
| N25 `flock -n` | 写明 | §4.2 |
| D2 占用时禁用上传 | 设计会话建议禁用，owner 2026-11-05 确认 | §6.1、§11 Q9 |
| 复审 R1 M1 的测量时点 | 在送审候选上测量；打包代码改动后重测 | §9 |
| 复审 R2 Preview 页续做卡片的位置 | 改为“顶栏之上” | §6.2 |
| 复审 R3 `composite_changed` 的来源 | 写明前端与后端 t1 的来源不同，派生表只在有对照时核对 | §8.3 |
| 复审 R4 `MANUAL_RECOVERY_REQUIRED` 的归类 | 并入“提交结果待确认”，两张表都分开写 | §6.1 |
| 复审 §2.2 占用绑定适用于通过与退回 | 补入 | §6.1 |
| 复审 §4 基线已前移的已通过提交 | 交后端设计会话；§6.1 增加暂定的一行；列为 FE3b 前置条件 | §2.1、§3.2、§6.1、§12 |
| 复审 N1 补充 | 写明 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT` | §2.2 |

### 15.1 FE3a 审核中交设计会话事项的处理（`a0b9604ddd`）

| 意见 | 处理 | 位置 |
| --- | --- | --- |
| §6、B10 真实 e2e 的上传输入 | 补记 owner 当时的决定；写明分开的理由、派生规则与目录、`logics.xml` 配对、A–D 四类上传及其规范变化、FE3a 的核对与判据、FULL 在空 `INITIAL` 上失败时的处理、留给 FE3b 的项 | §4.6、§11 Q10 |
| N2 基线序号 | 甲：树也显示“归档基线 n”，与摘要共用同一个标签函数，在 FE3a 做 | §7 M7、§11 Q11 |
| §5 M1 的判定 | 只看 renderer；浏览器主进程只报告，FE3b 补记 RSS 拆分 | §8.4、§11 Q12、§13.3 |
| B7 续做读取失败后“提交”是否保持禁用 | 实施方按审核意见恢复 FE2c 行为时不需要设计会话处理；如果实施方认为应保持禁用而停下，设计会话按 §6.1 的文案原则定文案 | 待实施方提出 |
| N6 AGENTS 建议条文 | 不在设计会话范围，由 owner 转治理会话 | — |

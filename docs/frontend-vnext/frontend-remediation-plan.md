# 前端专项整顿执行计划

- **状态：** Owner 已确认（2026-11-12）：§11.1 七项均按本文建议。2026-11-13 按计划评审意见与 Owner 同日的决定修订：并入 T4、T5、T6，加入整顿后后端上的一次 journeys（§9.1），补 T3 的检查清单、收窄 kickoff §4.2 的措辞（§11.2）。T4 的 t1 验证按甲执行（Owner 2026-11-13，§11.2 第 3 项）。按计划复审补上 T5 漏列的两个服务级 token（§11.2 第 7 项）。2026-11-17 按中期合入后的重新评估、修订核对意见与 Owner 2026-11-16、2026-11-17 决定修订（§11.3）：实施路线改为以 `main` 的新起点 **B′**（附注 tag `gw08-midterm-exit`）为基础切新分支 `fe-remediation` 重做，不合并 `fe-vnext`（`583a72c5da` 只读保留作取用来源）；在打 tag 前于 B′ 候选上重取测试计数与截图基线并跑一次真实 backend `journeys` 完整集对照运行（§2、§9 第 0a 步、§9.1）；按中期合入后的新结构重排 `ComparisonPage` 与 `WorkbenchPage` 的拆分和 state 分组（§6、§7，保持 B′ 的 effect 顺序，仅保留原有两处换序）及 G1 推导（§8.1，G1 按甲执行并预先声明 `schema-keyless` 的 4 张 mock 截图顶栏差异），把第一轮预审教训写成规则（§3），并补齐未重核项（R9、O2、O4、T2、T4、T6）及 O1/T1/T3/T5 的核对结论（§8.4、§11.3）。恢复计划已定稿，整体复盘会话已核对（2026-11-17），待 B′ 核收，未实施、未测试。2026-11-18 按第 9 步独立审核与第 10 步证据核对后的 Owner 决定修订截图例外与 T4 判据（§11.4）：G1 预声明截图由 4 张扩为 6 张，R9 的一行 CSS 及 10 张截图列为例外，T4 判据 ② 按 B′ 新顶栏改写，第 10 步三张 04 图的光栅化抖动与两组 pregate 的网格交点差异按噪声处理。
- **会话分工：** 前端设计会话写本计划、答复设计问题并给出 F7 判断；实施与审核各由独立会话负责（[前端 kickoff](frontend-kickoff.md) §10）。
- **依据：** `/home/dev/gdds-stage-exchange/whole-project-review/` 下的 `remediation-input-frontend.md`（下称“输入”）、`project-review-2026-11.md`（§11、§12、§20）、`remediation-plan-review-frontend.md`（2026-11-13）、`remediation-plan-rereview-frontend.md`（2026-11-13）、`remediation-pause-2026-11-14.md`、`remediation-reassessment-2026-11-16.md`（§1、§2、§3.5、§6、§8，下称“复评”）与 `remediation-plan-revision-check-frontend.md`（2026-11-17）；[FE4 kickoff](fe4-kickoff.md) §20；[现行界面视觉确认](ui-optimization-direction.md) §9、§9.1；AGENTS“前端测试（FD7）”。
- **代码事实基线：** 正式实施起点为 **B′**（附注 tag `gw08-midterm-exit`）。本次修订在打 tag 前的 `main`（`frontend/` 树 `6b8fb33532a5a9daff36ea3f3a6e4b5be06e7fff`，与复评基线 `6da40cc7e0:frontend` 相同）上做只读静态核对；暂停前 H（`eb6530b36e`）/ B（`ef69cb41fb`，`frontend/` 树 `b4806ba6a5`）的数字作为历史记录保留。本文按函数名引用代码，不引用行号：H4 之后行号全部改变。
- **阶段材料：** 开发主机 `/home/dev/gdds-stage-exchange/fe-remediation/`（`log.md`、`prompts/`、`handoffs/`、`reviews/`、`evidence/`、`reference/reassessment-argon-20261117.md`）。`evidence/` 中暂停前的旧证据只作参考，本轮证据统一放入 `/home/dev/gdds-stage-exchange/fe-remediation/evidence/post-midterm/`，与暂停前的旧证据分开；本轮证据与独立审核在 `B′..新候选 C` 上整套重做。入库的只有本计划、kickoff 的修改与退出时的一页总结。

## 1. 范围

| 代号 | 内容 | 输入 | 审核 |
| --- | --- | --- | --- |
| H4 | 引入 Prettier，一次全量格式化，入口加格式检查 | §2 | 实施者与门禁 |
| H1 | 三层导入规则，移动 `ConnectionStatusIndicator` | §3 | 实施者与门禁 |
| H2 | `ComparisonPage.tsx` 中已独立的子组件与纯函数移到单独文件 | §4 | 实施者与门禁 |
| H3 | 三个组件体的 state 按关注点抽成 hook | §5 | 整轮末尾独立审核，重点 |
| G1 | 比较对的标签与标题从 `inputs[].role` 推导 | §6 | 实施者与门禁，末尾审核一并看 |
| G2 | 刷新 OpenAPI 快照 | §7 | 等 Owner 转交后端 SHA |
| O1、O2、O4、R9、T1、T2 | FE4b 遗留中不改行为的项（其中 O2、O4 经重核已在中期提交 `34d16d6bd9`、`3e05f0aae9` 中完成，见 §8.4） | §8 | 实施者与门禁，末尾审核一并看 |
| T3 | 真实 backend 入口复用日志目录时失败（FE4 合并后验证交来，即同批的 E1，输入之后才出现） | — | 实施者与门禁，末尾审核一并看 |
| T4、T5、T6 | 只改测试工具：t1 稳定门使 1280 正式截图取景偏移（T4）；凭据检索的 token 格式与执行时点，做成只读脚本（T5）；`check-handoff-hex.py` 核对截断形式（T6）。来源是 FE4 合并后验证审核（交换目录 `fe4b/reviews/fe4-post-merge-eb6530b36e.md` §2.3、§2.4、§3、§6）的 E2、E3、E4，记在 `fe4b/followups/fe4-behavior-small-task.md` 末节；Owner 2026-11-13 决定并入本轮 | — | 实施者与门禁，末尾审核一并看 |

另有两次真实 backend `journeys` 完整集运行：① 打 tag 前在 **B′** 候选上跑一次作为归因对照基线（§2、§9 第 0a 步，Owner 2026-11-16 确认，失败用例逐个记录，不要求全部通过才开始整顿）；② 在包含后端整顿退出提交 Sx 的后端上至少跑一次（§9.1，Owner 2026-11-13，不阻塞前端退出，在后端 S3 实施前完成）。它们不是代码改动项。

本轮不做：S2b 的设备路由头；会改行为的 FE4b 遗留（小任务，见 §8.3 与交换目录 `fe4b/followups/fe4-behavior-small-task.md`）；`presentation.ts` 中 `logical_path.includes("/blank/")`（等后端给出显式引用）；Prettier 以外的新依赖与状态管理库；顺手改交互、文案或样式（R9 的一行 CSS 是 Owner 授权的例外，§11.4）。任何一项必须改行为时停下，交设计会话与 Owner。

## 2. 开始条件与基线

- **开始条件（Owner 2026-11-16、2026-11-17，复评 §1、§2）：**
  1. **B′ 候选与后端门禁：** `gate-cost-reduction-phase-a` 与前后端两份定稿计划均已合入 `main`，当时的 `main` 头作为 **B′** 候选。在该候选上由后端或 Owner 指定的会话执行并确认 `04` 后端阶段门禁通过；前端只核收其门禁结果，不代替后端确认门禁。
  2. **打 tag 前的前端基线与 `journeys` 对照（§9 第 0a 步）：** 在打 tag 之前，由前端实施会话在 **B′** 候选的 clean、已提交 worktree 上依次取：`07` 的 mock 全量与截图（**B′@07**）、`04` 的 mock 全量与截图加上传包校验（**B′@04**），以及 `04` 上真实 backend 的 `journeys` 完整集对照运行（`run-evidence-wrapper.sh` 调 `run-real-backend-e2e.sh --suite journeys --subphase fe4b`，单独 `--log-dir`）。
  3. **失败处理与重取规则：** 后端门禁或前端 mock 全量若失败，算中期遗留，先在 `main` 上修复再开始整顿；修复后**在修复后的新头上重取全部基线**（含 `07` mock 全量与截图、`04` mock 全量与截图及上传包校验、`04` `journeys` 完整集对照），不混用旧提交的结果。`journeys` 的业务失败逐个记录（用例名、观察到的错误码与状态码、退出码与日志），不阻塞开始整顿；若运行没有进入 suite，记“未完成对照”，修正后重开一次，不把它当作完成了完整集。
  4. **打 tag 与转交（§9 第 0b 步）：** 上述门禁与基线运行完成后，由 Owner 指定的会话在最终候选头上打附注 tag `gw08-midterm-exit`，该提交记为 **B′**。由 Owner 转交后，前端实施会话核对 tag，从 **B′** 切出新分支 `fe-remediation`，并重核本文引用的函数与数量（若有出入写进 handoff，不算偏差）。
  5. **不改行为基准：** 整顿的“不改行为”（接口、错误码与状态码、文档字节、digest、golden、截图）一律相对 **B′** 判断（预声明例外为 §8.1 G1 中 `schema-keyless` 的 6 张 mock 截图顶栏一行差异，以及 Owner 授权的 R9 一行 CSS 带来的 10 张截图变化，见 §11.4）。草图与布局对照以 [`ui-optimization-direction.md`](ui-optimization-direction.md) §9、§9.1 已获 Owner 接受的现行布局为准，这些与旧草图的差异不算偏差。
- **测试数量基线：** 全部在 **B′** 上由第 0a 步实跑产生（中期最后一次记录是 vitest 610 项、Playwright e2e 153 项，仅作参考；暂停前 H 上为 vitest 46 个文件 481 项、Playwright 118 项、PNG 252 张，`smoke` 9 项、`journeys` 21 项）。本轮新增的单测（H1 `layering-rules.test.ts`、O1 `table-assembly.test.ts`、G1 `view-copy.test.ts`）只增加计数；既有用例一个不删、不改断言。
- **截图基线：** 第 0a 步在 `07` 上跑 **B′** 的 mock 全量带截图得到 **B′@07**，在 `04` 上跑 **B′** 的 mock 全量带截图得到 **B′@04**（暂停前 §20.5 的 04 截图属中期界面改动前的旧图，不再作本轮退出基线）。
- **真实 backend `journeys` 对照基线与基线记录规则（Owner 2026-11-16、2026-11-17）：** 第 0a 步在 `04` 上执行的 **B′** `journeys` 完整集用来给整顿后后端 Sx 上的那次 `journeys`（§9.1）作归因对照。**基线运行的凭据处理：** 第 0a 步 **B′** 上的 `journeys` 跑在还没有 T1 脱敏的入口上，失败用例保留的 trace 里会有 token，做不到“计数为 0”；基线运行按 kickoff §6 的手工方法逐成员检索 zip 并如实记录结果，原件受控保留，交接材料里不放凭据，不把 T1 的改动提前混进 **B′**。“计数为 0”只要求本轮把入口改完之后的运行（§8.4 T5、§9 第 7 步与第 10 步）。
- **打 tag 前的 `main`（`frontend/` 树 `6b8fb33532`）上的现状数字**（供结果评审对照，口径：`frontend/src` 不含 `features/api/generated/` 与 `test/fixtures/`，核对明细见阶段区 `reference/reassessment-argon-20261117.md`）：
  - **108 个文件，20,328 行**（暂停前 H：99 个文件 17,285 行）；超过 160 字符的行 **751**（H：630），超过 400 字符的 **46**（H：43），最长 **1,819 字符**（`ComparisonPage.tsx`；H：2,048）。
  - **三个目标文件与组件体：**
    - `ComparisonPage.tsx`：全文件 **1,572 行**（H：1,048 行；全文件 `useState` 出现 41 次、`useEffect` 20 次，含 import 行及 `ScrollStrip`、`InfoPopover`、`CopyDebugValue`、`GridTable` 四个子组件）；`ComparisonPage` 组件体 **812 行**（H：579 行），`useState` **34**（H：30）、`useRef` **9**（H：9）、`useEffect` **13**（H：9）。
    - `WorkbenchPage.tsx`：全文件 **717 行**（H：647 行；全文件 `useState` 出现 32 次，含 import 行）；`WorkbenchPage` 组件体 **613 行**（H：557 行），`useState` **31**（H：32）、`useRef` **2**（H：3）、`useEffect` **6**（H：7）。
    - `ArchiveMainlineDialog.tsx`：全文件 **590 行**（中期未动）；`ArchiveMainlineDialog` 组件体 **516 行**，`useState` **30**、`useRef` **3**、`useEffect` **1**（与 H 相同）。
  - `pair_id` 子串匹配：**4 处**（`viewLabel` 2、`viewTitle` 2）。
  - OpenAPI 快照（`frontend/openapi.json`）：**41 条路径**（其中公开 `/v1` 33 条、`/healthz` 与 `/readyz` 2 条，内部 `/internal/v1` 6 条），schema 组件 **107 个**（H：39 条路径、102 个组件）。

### 2.1 暂停前核收记录与单 agent 实施模式（Owner 2026-11-13、2026-11-16）

暂停前（2026-11-13）核收点 `main` `74a0f326bfdaf402c8cb372246d761ab6461d6c0` / 暂停点 `ef69cb41fbfbc248e5e87c25357e8e004c75333f`（`frontend` 树 `b4806ba6a5`，`vnext` 树 `6080ecec82`）及 `fe-vnext` 上的旧运行记录保留在交换日志中作为历史，正式恢复实施以 **B′**（`gw08-midterm-exit`）为准。

前端实施保持单 agent 模式：完成编码、必要调试、handoff、收到审核意见后的修复及已批准取证，不派生协调者/实施者/测试者/验收核对团队，不套用后端模型与分包规则。§10 的整轮独立审核保持，由 Owner 另行安排新会话并转交材料和意见；实施者不自审、不自行启动审核 agent。模型由 Owner 选择。前端设计问题、取证放行、退出/合入仍按本计划由 Owner 决定或指定会话处理。

## 3. 分支、取用、预审教训规则、节点与缓存

- **分支（复评 §1 第 3 条、§6.3 第 1 条）：** 从 **B′**（`gw08-midterm-exit`）切出**新分支 `fe-remediation`** 实施，**不合并 `fe-vnext`**。`fe-vnext`（头 `583a72c5daf56c269d512b8b5b7a0c128ffc29de`）与工作区 `/home/dev/gdds-fe` 只读保留到前端整顿退出，作为取用提交的来源，退出后再按工作区回收规则清理。本轮证据统一放在阶段区 `/home/dev/gdds-stage-exchange/fe-remediation/evidence/post-midterm/` 下，与暂停前的旧证据分开。本轮独立审核对象为 `B′..候选提交 C`。
- **提交：** 每一项单独提交，H3 每个组件一个提交；H4 拆为三个提交（工具提交、`FormulaCard` 标题改成 `{" · "}` 的手工提交、格式化提交），其中格式化提交只含 `prettier --write .` 的输出（§4）。提交说明写代号（例如 `H3:`），不写审核轮次编号。每个直接取用或局部取用 `fe-vnext` 的提交，必须在 handoff 中写明来源提交 SHA。
- **`fe-vnext`（`ef69cb41fb..583a72c5da`）21 个提交的取用与重做（复评 §6.1、§6.3 第 2 条）：**

| `fe-vnext` 提交 | 内容 | 文件 / 中期重叠 | 本轮处理方式 |
| --- | --- | --- | --- |
| `c5d5482193` | H4 Prettier 工具与配置 | 6 / 0 | **直接取用** |
| `34aa5d15f7`（及 `4c29b0832a`、`35592ccb75`） | H4 全量格式化与 `FormulaCard` 标题节点 | 123 / 46 | **不搬格式化提交**；在 B′ 取用 `c5d5482193` 工具提交后，先把 `FormulaCard` 标题改成 `{" · "}` 的手工改动（来自 `35592ccb75`，不用行内 `prettier-ignore`）单独一个提交，再重跑 `prettier --write .` 到第二遍无变化作为纯 Prettier 输出的格式化提交 |
| `65bcaefa21` | H1 分层规则与 `ConnectionStatusIndicator` 迁移 | 7 / 2 | **规则与单测取用**（`eslint.config.js`、`ConnectionStatusIndicator.test.ts`、`layering-rules.test.ts`）；迁移 `ConnectionStatusIndicator.tsx` 时保留中期新增的 `compact` 属性（+3/−1）；两页面文件的导入修正重做 |
| `eb1a3f16fe` | H3 `ArchiveMainlineDialog` 抽 hook | 6 / 0 | **直接取用**（该文件 `main` 上未动，590 行） |
| `f979b07dd0`、`7f5461c704`（及 `cc90d2e5bf`、`6c2608c397`、`6ffce18697`） | H2 `ComparisonPage` 拆文件与 H3 抽 hook | 13 / 1、11 / 1 | **在 B′ 新结构上重做**（§6、§7.2），旧提交只作参考，并直接吸收 `openWithdraw`、`visibleRows` 初值与 `loadTable` 依赖数组修正 |
| `7971c7c4fe` | H3 `WorkbenchPage` 抽 hook | 9 / 1 | **在 B′ 新结构上重做**（§7.2），旧提交只作参考 |
| `47a7003f9b`、`a4c575a7db` | O1 表格装配（含预审 F1 三段式修正） | 8 / 5 | **在 B′ 上重做**（§8.4 O1），采用 `a4c575a7db` 的 `checkTableRowLocations` / `decodeTableEncodings` / `assembleTableRows` 三段拆分保持 B′ 语句顺序；O2、O4 已在中期完成 |
| `d9de8824e9` | G1 标签与标题从输入角色推导 | 6 / 1 | **在 B′ 上重做**（§8.1），吸收中期 `REVIEW` 模式的提交绑定 Preview 结果语义与新增调用点 |
| `bef2a49160` | R9、T4 截图稳定门不改变滚动位置 | 3 / 2 | **思路与 `guard.ts` 取用**，`upload-mode.spec.ts` 与 `t1.spec.ts` 的改动在 B′ 上手工重放 |
| `017dfc90d1`、`50f3f1a89e`、`f41608b3d4`、`687e62636b`、`583a72c5da` | T1、T3、T5、T6 真实入口与证据检查（含预审 F5、F6、F7 修正） | 3 / 1 等 | **独立脚本直接取用**（T6 `check-handoff-hex.py`、T5 `scan-credentials.py` 最终版 `50f3f1a89e`、T1 `redact-entry-tokens.py` 最终版 `583a72c5da`；与复评 §6.1“思路取用”不同：因为 `check-handoff-hex.py` 中期未动，另两个是独立新文件）；`run-real-backend-e2e.sh` 的 T1/T3 改动（含 `687e62636b` 的 11 项固定名清单）在 B′ 上手工重放 |

- **第一轮预审的教训（写为硬规则，复评 §6.3 第 3 条）：**
  1. **抽函数或抽 hook 时严格保持同步段的语句顺序。** 相邻两个 `await` 之间（或无 `await` 的整段）以及跨 `await` 的 `setState`、ref 读写、同步校验/解码调用的先后顺序不得改变；禁止把可能抛错的 `validateRowLocations` 或 `decodeSnapshotEncodings` 移到 `setState` 之后（防止校验失败时已写入新表部分 state 而与旧表 `rows` 混杂）。
  2. **不使用行内 `prettier-ignore`。** 源码与 JSX 中一律禁止写 `prettier-ignore` 或 `{/* prettier-ignore */}`；`FormulaCard` 标题用 `{" · "}` 保持与 B′ 相同的三个 JSX 子节点（§4）。
  3. **逐步比较截图，出现不能归为噪声的变化即停（例外只有 §8.1 G1 的 6 张图与 §11.4 的 R9 10 张图）。** 每一步在 `07` 跑 mock 全量后都必须与 **B′@07** 做 `compare-screenshots.py` 比较，并在 handoff 中记录五类计数（相同、噪声、内容变化、尺寸差异、缺失）。预声明例外是 §8.1 G1 提交起，`e2e/workspace-shell.spec.ts` 中用 `PREVIEW` 打开 `schema-keyless` 的两个用例所截的 6 张整页图（`f-original-structure-nonempty`、`f-filtered-scope-count`、`f-search-nonempty-count` 的 1920 与 1280；原预声明 4 张，第 9 步审核发现第三组与第二组同属一个用例，Owner 2026-11-18 扩为 6 张，§11.4），它们与 **B′** 基线的差异限于顶栏这一行（面包屑文字从“当前基线 → 本次归档组态”变为“比较视图 1”，同一行里排在它后面的元素可随之移位），顶栏以下的区域相同或只有噪声；另有 Owner 2026-11-17 授权的 R9 一行 CSS 带来的 10 张图（§11.4）；除此之外，任何一张图出现不能归为噪声的内容或尺寸变化时**立即停下**，交设计会话与 Owner，不得自行打补丁绕过。
  4. **初值、依赖数组与非 DOM ref 内联处理原样守恒。** `useState` 初值逐字保持 B′ 原样（如 `visibleRows` 初值 `{ start: 1, end: 1 }`）；`useEffect`/`useCallback`/`useMemo` 依赖数组保持 B′ 原样（如 `loadTable` 不添加稳定 setter `setError`）；JSX 中直接写非 DOM ref 的内联回调（如撤回按钮写 `withdrawKey.current`）必须改为拥有者 hook 的具名函数（`openWithdraw`）。
- **节点：** 按 AGENTS DC91 节点池与原子占用规则。日常 mock 全量在 `ct109-gw-dms-07`（`GATEWAY_FE_TEST_WORKERS=2`）；T1、T3、T4、T5、T6 的真实 backend 与脚本调试在 `ct108-gw-dms-05`；B′ 的 `journeys` 对照运行与退出证据在 `ct108-gw-dms-04`，`t1` 证据在 `05`（§9）。不在开发主机运行类型检查、lint、单元测试、构建或 e2e。
- **格式化在哪里做：** `prettier --write` 是改写源码的开发操作，与 `npm run generate:api-types` 相同，在 CT201 的开发 worktree 中执行；格式检查作为测试的一部分，只在测试节点由入口执行。
- **npm 缓存（DC67，复评 §6.2）：** `main` 上前端依赖与 `frontend/package-lock.json`（SHA256 `811fa3dfbf22233738906335b35ec3e2abf0846f510a157cb69ff18db71f0f7c`）自暂停点起未变。取用 `c5d5482193` 工具提交后，先核对 `frontend/package-lock.json` 与 `fe-vnext` 的 `c5d5482193` 逐字节相同（SHA256 `3cd77751f9c5399ef17a1ad0b4606989b77aec1cc46bcde483711b40cae7e7c6`）；一致时，`04`、`05`、`07` 上已有的 `/home/dev/gdds-fe-cache/fe-remediation/npm-cache` 及同目录归档 `npm-cacache.tar.gz`（SHA256 `332deeb8d7a0a750f8f9cc56dfae146249c31baae81df52d4e557c2f5cfda0eb`）可继续使用，无需重新从 CT201 打包传输。工具提交之后的运行显式设置 `GATEWAY_FRONTEND_NPM_CACHE`、`GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE` 与 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT`；第 0a 步 **B′** 的 lockfile 未变，照旧使用节点默认缓存（`04`、`07` 的默认缓存 `/home/dev/gdds-fe-cache/frontend/` 已恢复为 FE4b 归档 `0d861824…`，`05` 无默认路径，与整顿前一致）。**严禁在整顿合入 `main` 之前修改或替换节点默认缓存目录**；默认缓存在退出合入 `main` 之后才更新（§9）。缓存缺失或摘要不符即停止，补齐后从头运行。
- **通道规则并行修改：** 通道规则并行修改只改规则内容、不改前端界面，若合入 `main` 时带动前端夹具更新，处理与回归区分方式见 §9.2。

## 4. H4：Prettier

- **版本：** `prettier` 精确钉 `3.9.10`（直接取用 `fe-vnext` 的 `c5d5482193`）。Prettier 没有依赖，lockfile 只增加一个包，`resolved` 为官方 `https://registry.npmjs.org/prettier/-/prettier-3.9.10.tgz`，`package-lock.json` SHA256 为 `3cd77751f9c5399ef17a1ad0b4606989b77aec1cc46bcde483711b40cae7e7c6`。
- **配置：** `frontend/.prettierrc.json` 只写 `printWidth: 100`，其余用默认值（双引号、分号、`trailingComma: "all"`、LF），与现有代码习惯一致，行宽与后端 ruff 的 `line-length = 100` 相同。定了不再调。
- **忽略：** `frontend/.prettierignore` 列出 `src/features/api/generated/`、`src/test/fixtures/`、`e2e-real/fixtures/`、`openapi.json`、`package-lock.json`，以及 `dist/`、`coverage/`、`playwright-report/`、`test-results/`。生成的类型由 `generated-types.test.ts` 逐字节核对，快照与 lockfile 由各自的工具生成，夹具有 SHA256 核对。**不使用行内 `prettier-ignore`**（§3 预审教训规则 2）。
- **`FormulaCard` 标题文本节点守恒（来自 `35592ccb75`）：** Prettier 将单行 `<strong>{a} · {b}</strong>` 折行时会拆成 `·{" "}` 四个子节点，改变末尾数字亚像素光栅化相位并导致 6 张公式截图出现 50 像素差异。将 `FormulaCard` 标题改为 `<strong>{formula.currentDeviceName ?? formula.beforeDeviceName ?? "未知装置"}{" · "}{formula.pointLabel}</strong>` 的手工改动**单独作为一个提交**，放在工具提交之后、格式化提交之前，保持与 B′ 完全相同的三个 JSX 子节点 `[a, " · ", b]`，既不用行内 `prettier-ignore`，也使随后的格式化提交保持纯 `prettier --write .` 输出且 6 张公式截图零内容变化。
- **脚本与入口：** `package.json` 加 `format`（`prettier --write .`）与 `format:check`（`prettier --check .`）。`run-tests.sh` 在 `npm ci --offline` 之后、`typecheck` 之前执行 `npm run format:check`：有未格式化文件时逐个列出并以非零退出，入口随之失败。README 补一段用法。
- **三个提交：** ① 工具提交（直接取用 `c5d5482193`）：依赖、lockfile、两个配置文件、脚本、入口与 README；② `FormulaCard` 标题手工提交：只含将 `FormulaCard` 标题改为 `{" · "}` 的手工改动；③ 格式化提交：只含在 ② 的树上于 `frontend/` 执行 `prettier --write .` 的输出（Prettier 3.9.10 对少数长行文件需跑两遍才收敛，故重复执行 `prettier --write .` 到第二遍无变化）。可重放的门禁：在格式化提交的父提交（②）上重复执行 `prettier --write .` 到第二遍无变化，得到的树与格式化提交（③）相同；③ 之后 `format:check` 通过；`07` 截图与 **B′@07** 比较只有相同与噪声（6 张公式截图内容变化为 0）。

## 5. H1：分层门禁

**规则。** 在 `eslint.config.js` 用 ESLint 自带的 `no-restricted-imports` 的 `patterns`（`regex`），按目录写三条（取用 `65bcaefa21`）。消息写明层次与 kickoff §4.2。

| 文件 | 不得导入 |
| --- | --- |
| `src/design-system/**` | 任一路径段为 `features` 或 `pages` |
| `src/features/{api,bundle,session,view-model}/**` | `design-system`、`pages`、`workbench`、`dev` 路径段 |
| 同上目录中的 `*.test.{ts,tsx}` | `design-system`、`pages`、`workbench`（允许 `dev`，见下） |
| `src/features/workbench/**` | `pages` |

- **测试文件的范围与重核结果（§11.1 第 1 项、复评 §6.2）：** 规则同样作用于测试文件，只允许 A 层测试导入 `features/dev`（共享测试数据，5 个文件：`client.test.ts`、`journeys.test.ts`、`polling.test.ts`、`scope-session.test.ts`、`workspace.test.ts`）。在打 tag 前的 `main`（`frontend/` 树 `6b8fb33532`）上静态重核确认：中期新增的 `HistoryCompareTasks.tsx`、`history-compare-errors.ts`（及 `.test.ts`）、`manual08.tsx`、`scope-copy.ts`、`secondary-scope-fixture.test.ts`、`ReviewActions.test.tsx`、`fixture-provenance.test.ts` 全部符合上述三层规则；全仓违规仍只有生产代码 `src/design-system/ConnectionStatusIndicator.tsx` 1 处与测试文件 `src/features/api/connection-status.test.ts` 1 处。
- **移动：** `src/design-system/ConnectionStatusIndicator.tsx` → `src/features/workbench/ConnectionStatusIndicator.tsx`（`git mv`，**保留中期在该文件上新增的 `compact` 属性改动**，组件内导入改为 `../api/connection-status`），在 B′ 的 `ComparisonPage.tsx` 与 `WorkbenchPage.tsx` 上重做导入路径修改；`connection-status.test.ts` 中渲染组件的用例原样移到 `src/features/workbench/ConnectionStatusIndicator.test.ts`（取用 `65bcaefa21`），另两个用例留下。用例数不变，单测文件数加 1。
- **证明规则生效：** 取用 `65bcaefa21` 的 `src/test/layering-rules.test.ts`（`// @vitest-environment node`，13 个参数化用例），用 ESLint 的 Node API `lintText` 对每条规则各给违规样例（必须报 `no-restricted-imports`）和合法样例（不报）。
- **文档：** kickoff §4.2 已写入目录与层的对应关系。
- **不处理：** A 层内部方向不整齐的导入（`bundle` → `view-model`、`api` → `bundle`），以及 §11.1 第 2 项中 Owner 决定本轮不动、记为遗留的两个 UI 组件（`SessionComponents.tsx`、`table-state.tsx`）。

## 6. H2：机械拆 `ComparisonPage.tsx`

在 B′ 上重做（旧提交 `f979b07dd0` 只作参考）。新目录 `src/pages/comparison/`（C 层，页面专用；`ComparisonPage.tsx` 留在原处，`App.tsx` 不改）。只移动代码、加 `export` 与 `import`，不改名、不改逻辑、不合并函数。

相对暂停前 H，打 tag 前的 `main`（`frontend/` 树 `6b8fb33532`）上 `ComparisonPage.tsx`（1,572 行）在中期删除了 `tabCount`、`tabChangeKind`、`tabRiskLevel`、`columnWidth` 四个旧函数，新增了提交结果错误码判断、通知与装置定义变化文案、局部风险与范围文案、canvas 文本测量与列宽拟合、列宽持久化，以及 `PublicNoticesPanel`、`ScrollStrip`、`InfoPopover`、`ChangeMark`、`ScopeChangeBadge` 五个独立子组件（其中 `ScrollStrip` 与 `InfoPopover` 各自带有内部 `useState`/`useRef`/`useEffect`）。全部顶层函数、常量、类型与子组件按职责移入下表文件：

| 文件 | 移入的内容 |
| --- | --- |
| `view-copy.ts` | `reviewStatusLabel`、`viewLabel`、`viewTitle`、`noticeReasonText`、`noticeLines`、`definitionChangeText`、`localRiskText`、`itemBadgeKind`、`itemStatusTooltip`、`riskLevelText`、`scopeChangeText`、`tabTitle`、`rowLabel`、`formatSchemaSummary` |
| `view-helpers.ts` | `bundleErrorState`、`serverResultReleaseCode`、`bundlePathForState`、`viewRiskLevel`、`pairDiagnosticDetails`、`riskTokens`、`HOVER_FIELD_LIMIT`、`orderedMovedCount`、`hasDeletedAppearance`、`recordValues`、`createTextMeasure`、`sampleRows`、`COLUMN_PADDING`、`COLUMN_MIN`、`COLUMN_AUTO_MAX`、`COLUMN_FIT_MAX`、`fitWidth`、`matchesGroup`、`matchesItem`，类型 `PairSummary`、`PairPresentation`、`SizedGridColumn`、`NavItem`、`NavTab`、`TextMeasure` |
| `sidebar-settings.ts` | `Settings`（含 `deletionLayout`）、`SETTINGS_KEY`、`SIDEBAR_MIN`、`SIDEBAR_MAX`、`DEFAULT_SETTINGS`、`clampSidebar`、`readSettings`、`ColumnWidths`、`COLUMN_WIDTHS_KEY`、`readColumnWidths` |
| `GridTable.tsx` | `GridTable` |
| `ChangeNavigator.tsx` | `ChangeNavigator` |
| `NavigationDiagnosticNote.tsx` | `NavigationDiagnosticNote` |
| `PublicNoticesPanel.tsx` | 中期新增的侧栏与页签条/信息行独立子组件：`PublicNoticesPanel`、`ScrollStrip`、`InfoPopover`、`ChangeMark`、`ScopeChangeBadge`（也可按组件拆为同名小文件，在 handoff 写明） |
| `DebugInfoBar.tsx` | `DebugInfoBar`、`CopyDebugValue`、`RiskReasonDetail` |
| `ReplacementBrowser.tsx` | `ReplacementBrowser`、`ReplacementSide` |
| `FormulaCard.tsx` | `FormulaCard`、`FormulaAlignedPair`、`FormulaLineList` |
| `PreviewHeaderActions.tsx` | `PreviewHeaderActions` |

完成后 `ComparisonPage.tsx` 只剩 `ComparisonPage` 与导入（子组件的 `useState`/`useRef`/`useEffect` 随子组件一并迁出）。若 `e2e/tsconfig.json`、`e2e-real/tsconfig.json` 因拆出文件需要收窄 `exclude`（参考 `f979b07dd0`），或跨文件导出时需要把原本依赖上下文推断的类型（如 `FormulaDisplay`、`ChangeLocation[]`、`Settings`）写成显式类型标注，均在 handoff 中逐一列出（预审 F8.2 教训）。审核用 `git diff -M --color-moved=dimmed-zebra` 核对整块移动。

## 7. H3：三个组件的 state 抽成 hook

### 7.1 规则

1. **完成标准：** 三个组件体（`ComparisonPage`、`WorkbenchPage`、`ArchiveMainlineDialog`）不再调用 `useState`、`useReducer`、`useEffect`、`useLayoutEffect`。组件体只剩：按 §7.2 的顺序调用 hook；三个共享 hook（第 3 条）；组合几个 hook 的事件处理（如 `WorkbenchPage` 的 `runAction`）与摆放所需的派生，按 B′ 上的写法保留 `useMemo`/`useCallback`；挂 DOM ref。每个 hook 的职责能用一句话说清（§7.2）。
2. **只移动，不改语义（含预审 F1、F4 教训）：**
   - state 的初值随 state **逐字原样**进入 hook（例如 `useTableData` 中 `visibleRows` 初值保持 `{ start: 1, end: 1 }`，不得改成 `{ start: 0, end: 0 }`），包括读 URL、存储与会话的惰性初值。依赖另一个 state 初值的成对 state 放在同一个 hook（`compareStartError` 与 `compareIntent`；`uploadLocked`、`resumePending` 与 `resumePreviewOperation`）。这些初值只读不写，挂载时先后调整不改变取值。
   - effect、`useCallback`、`useMemo` 的依赖数组**原样保留**，现有数组中有意省略的依赖不“补全”，也不把因拆 hook 作为参数传入的稳定 `setState` setter（如 `loadTable` 中的 `setError`）加入依赖数组；不新增也不去掉 `useCallback`/`useMemo`，以免改变传给子组件的函数身份。
   - 不合并、不删除 state；看到冗余（如 `ComparisonPage` 中由 runtime 订阅同步的 `search`、`onlyInteresting`、`debug` 三个镜像 state）记进 handoff，留给以后。
   - 回调中语句的先后按“同步段”核对（相邻两个 `await` 之间，或没有 `await` 的整段）。段内对**不同** state 的 `setState` 可以因分组而换序：应用用 React 18.3.1 的 `createRoot`，代码中没有 `flushSync`，同一段内的更新一起批处理，渲染结果相同。对同一个 state 的多次设置、ref 的读写、`await`、函数调用（父组件回调、`runtime.execute`、`load()`、`validateRowLocations`、`decodeSnapshotEncodings` 这类会同步执行或抛错的调用），它们彼此之间以及与 `setState` 之间的先后保持原样（§3 预审教训规则 1）。§7.3 的重置序列按同一标准核对。
3. **数据流不变：**
   - `useBoundGatewayApi`（内部是 `useState`）、`useGatewaySessionState`、`useUploadModeState`（内部有自己的 state 与 effect）由组件各调用一次，结果作为参数传给需要的 hook。hook 内不得再调用它们，否则会出现第二份状态或第二个绑定实例。
   - 自定义 hook 之间不互相调用。一个 hook 用到另一个 hook 的值或函数时，由组件作为参数传入，所以被用到的 hook 必须先调用；§7.2 的顺序由此而来。
   - 一个 hook 要改另一个 hook 拥有的 state 或 ref 时，由拥有者提供具名函数，函数体是原处连续语句的原样搬入（例如归档对话框三处冲突路径共有的“写待定提示、显示冲突提示、刷新”），或者直接传 setter。不新增 context 或全局 store。
4. **effect 顺序：** 按 §7.2 的顺序调用后，effect 的相对顺序只有 §7.3 列出的两处与 B′ 不同。其他任何调整都在 handoff 逐条写明为什么安全，标准是被跨过的 effect 在同步部分没有共同读写的 state、ref 或 URL。
5. **ref（含预审 F3 教训）：** 非 DOM 的 ref（`ComparisonPage` 的 `withdrawKey`、`loadingKey`、`loadedRequest`；`WorkbenchPage` 的 `resumePending`；`ArchiveMainlineDialog` 的 `previousDigest`、`pendingNotice`、`progress`；注：`WorkbenchPage` 原 `uploadRef` 已在中期删除）随所属 state 进入同一个 hook。JSX 中直接写这些 ref 的内联处理（`ComparisonPage` 顶栏撤回按钮写 `withdrawKey.current = crypto.randomUUID()`，`WorkbenchPage` 中 `OperationStatusPanel` 与 `UploadStepCard` 的回调写 `resumePending.current`）必须改为拥有者 hook 的具名函数（如 `usePreviewWithdraw` 的 `openWithdraw`，不再向组件返回 `withdrawKey`），函数体原样。被 hook 使用的 DOM ref（`selectedNavRef`、`workspaceRef`、`pageRef`、`headerRef`）由该 hook 创建并返回，组件负责挂载；只在 JSX 中使用的（`searchInputRef`、`reviewNoticeRef`、`searchRef`）留在组件体。
6. **放置：** `ComparisonPage` 的 hook 放 `src/pages/comparison/`，`WorkbenchPage` 的 hook（及抽出的页内纯辅助函数 `workbench-helpers.ts`）放 `src/pages/workbench/`，`ArchiveMainlineDialog` 的放 `src/features/workbench/archive-mainline/`；文件名 `use-*.ts`。这些目录都受 H1 规则约束。
7. **测试：** 不改既有测试；不为 hook 补单测（覆盖靠既有 mock e2e 与截图）；mock 全量数量不变，每一步截图与 **B′@07** 比较只有相同与噪声。

### 7.2 分组与调用顺序（按中期合入后的新结构重排）

下表按组件内的调用顺序排列；“参数”列只写来自其他 hook 或组件的值，`gatewayApi` 省略。

**`ComparisonPage`（打 tag 前的 `main` `6b8fb33532` 组件体共 34 个 `useState`、9 个 `useRef`、13 个 `useEffect`）**

| # | hook | 管什么（含中期新增项） | 参数 |
| --- | --- | --- | --- |
| — | `useBoundGatewayApi`、`useGatewaySessionState`（组件调用） | 位置同 B′，在最前 | — |
| 1 | `useBrowseRuntime` | 浏览命令 `runtime`、`browse` 与 `search`、`onlyInteresting`、`debug` 三个镜像 state（4 个 `useState`、0 个 `useRef`），runtime 订阅与 `popstate`（1 个 `useEffect`） | — |
| — | `useUploadModeState`（组件调用） | 共享的上传模式读取 | `enabled` 取 `browse.mode`，在 1 之后 |
| 2 | `usePreviewSubmitResume` | Preview 上传模式：`submitOpen`、续接卡片 `resumeOperationId`（2 个 `useState`、0 个 `useRef`），`refreshUploadMode`、`finishSubmitResume`、`retryResumeNotice` 及 2 个 `useEffect` | 上传模式、`runtime`、`browse.mode` |
| 3 | `usePreviewWithdraw` | 顶栏撤回：`withdrawOpen`、`withdrawBusy`、`withdrawUnderstood`、`withdrawError`（4 个 `useState`）与幂等键 `withdrawKey`（1 个 `useRef`、0 个 `useEffect`），`openWithdraw`（含原 JSX 内联 4 条语句）、`confirmWithdraw` | 上传模式、`refreshUploadMode` |
| 4 | `useCompareHeaderHeight` | R15 顶栏高度变量：`pageRef`、`headerRef`（0 个 `useState`、2 个 `useRef`）与 `ResizeObserver`（1 个 `useEffect`） | 会话状态 |
| 5 | `useViewSettings` | 侧栏与列宽设置：`settings`（含侧栏宽度、折叠、折叠分组与 `deletionLayout`）、`columnWidths`（2 个 `useState`；中期已删 `overflow`），`workspaceRef`（1 个 `useRef`），`SETTINGS_KEY` 与 `COLUMN_WIDTHS_KEY` 两个 `localStorage` 持久化（2 个 `useEffect`），`fitSidebarWidth`、`updateSidebarWidth` | — |
| 6 | `useReviewFacts` | 审核上下文读取：`reviewFacts`、中期新增的 `reviewResultChecking` 与 `reviewResultErrorCode`（3 个 `useState`、0 个 `useRef`、0 个 `useEffect`），以及并行读取 `getReviewFacts` 与 `getSubmissionResult` 的 `readReviewContext` | `runtime` |
| 7 | `useComparisonBundle` | bundle 下载、历史比较等待与审核结果重验：`fetchBundle`、`bundle`、`pairs`、`loading`、`error`、`historyCompareStatus`、`historyCompareWaited`（7 个 `useState`），`loadingKey`、`loadedRequest`（2 个 `useRef`，现含 `bundle`），`loadBundle`（1 个 `useEffect`）及重验 `loadedRequest.current.bundle` 的 `reloadReviewContext` | `runtime`、`browse`、会话状态、`readReviewContext`、`setReviewResultChecking`、`setReviewResultErrorCode` |
| 8 | `useComparisonNavigation` | 导航与范围选择：中期新增的 `showEmptyTabs`（1 个 `useState`），`selectedNavRef`（1 个 `useRef`），分组、可见分组/项/页签（`shownTabs`、`shownItems`、`visibleGroups`、`navigationEntries`、`emptyTabCount`、`toggleEmptyTabs`）、当前选择（含整表视图 `wholeTable`、页签条 `selectedItem`/`stripTabs`/`itemEmptyTabCount`/`stripVisible`），只留选择同步与侧栏滚动到当前节点 2 个 `useEffect`，`chooseTab`/`choosePair`/`openWholeTable`/`openItem` | `pairs`、`browse`、`runtime` |
| 9 | `useTableExpansion` | 折叠运行段展开状态：`expandedRuns`（1 个 `useState`、0 个 `useRef`）与切换节点/页签/表时重置 `expandedRuns`（1 个 `useEffect`，排在未归属回退之前） | 当前选择（`selectedNodeKey`、`browse.tabKey`、`selectedTab?.table`） |
| 10 | `useUnassignedBrowse` | 未归属行谓词、浏览与回退：`filterTabsForTable`、`unassignedPredicates`、`canBrowseUnassigned`、`activeUnassigned`、`browseUnassigned` 及未归属 URL 状态回退（0 个 `useState`、0 个 `useRef`、1 个 `useEffect`） | `presentation`、`surfaceTable`、`browse`、`runtime`、`openWholeTable` |
| 11 | `useTableData` | 当前表数据与范围派生：`rows`、`beforeRows`、`currentRows`、`scopedRows`（中期替代 `records`）、`annotations`、`tableLoading`、`visibleRows`（7 个 `useState`，`visibleRows` 初值保持 `{ start: 1, end: 1 }`；0 个 `useRef`），`loadTable`（1 个 `useEffect`），基于 `scopedRows` 的 `locations`、`rowRiskCounts`、`currentIndex`、`selectedScopeKind`、`riskReasonDetails`、`unassignedView`，以及按当前表派生的 `widthTable`、`storedWidths`、`changeColumnWidth`、`resetColumnWidths` | `bundle`、当前选择与 `presentation`/`surfaceTable`/`replacement`、`browse`、`expandedRuns`、`filterTabsForTable`、`activeUnassigned`、`settings.deletionLayout`、`columnWidths`、`setColumnWidths`、`setError`（不入 `loadTable` 依赖数组） |
| 12 | `useTabStripScroll` | 页签条激活项滚动：将 `.overflow-tabs button.is-active` 滚动到可视区（0 个 `useState`、0 个 `useRef`、1 个 `useEffect`，排在 `useTableData` 之后） | 当前选择（`selectedNodeKey`、`browse.tabKey`） |
| 13 | `useFormulaPanel` | 公式抽屉：`formulaOpen`、`formulas`、中期新增的 `formulaFocus`（3 个 `useState`、0 个 `useRef`、0 个 `useEffect`）与 `openFormula` | `bundle`、`presentation`、`browse.mode` |

组件体保留：`searchInputRef`、`reviewNoticeRef`（2 个只在 JSX 中挂载的 DOM `useRef`），面包屑与返回工作台 `returnToWorkbench`，以及 JSX 渲染。（合计：hook 内 `4+2+4+0+2+3+7+1+1+0+7+0+3 = 34` 个 `useState`、`0+0+1+2+1+0+2+1+0+0+0+0+0 = 7` 个 `useRef` + 组件体 2 个 `useRef` = 9 个 `useRef`、`1+2+0+1+2+0+1+2+1+1+1+1+0 = 13` 个 `useEffect`。）

**`WorkbenchPage`（打 tag 前的 `main` `6b8fb33532` 组件体共 31 个 `useState`、2 个 `useRef`、6 个 `useEffect`）**

中期在 `WorkbenchPage.tsx`（717 行）中删除了 `columnWidths`（组态树固定三列）及 `uploadRef`、`pendingUploadAction`、`uploadReady`、`uploadBlockedReason` 与 `pendingUploadAction` 的 `useEffect`（工具栏上传快捷入口移除）；新增了历史比较重跑标记 `compareNeedsRerun`、抽屉折叠 `historyDrawerCollapsed`、原地改 URL 后的触发器 `[, setUrlRevision]`（3 个 `useState`），以及 `closeHistoryDrawer`、`openSubmissionResult`、`openCompareOperation`、`jumpToCompare`、`activePreviewOperationId`、`resumeActivePreview`。页内纯辅助函数（`shortTime`、`timeTitle`、`refKey`、`historyRef`、`pageUrl`、`isTemporaryError`、`messageFrom`、`statusClass`、`showOperationForCompare`、`historyBundleErrorMessage`、`fullTime`）移入 `src/pages/workbench/workbench-helpers.ts`。

| # | hook | 管什么（含中期调整） | 参数 |
| --- | --- | --- | --- |
| — | `useBoundGatewayApi`、`useGatewaySessionState`、`useUploadModeState`（组件调用） | 位置同 B′，在最前 | — |
| 1 | `useSubmitResume` | 提交续接卡片的操作 ID：`resumeSubmitOperationId`（1 个 `useState`），上传模式 attempt 带出操作 ID 时设置的 1 个 `useEffect` | 上传模式 |
| 2 | `useWorkbenchData` | 工作区与 History 加载：`history`、`loadError`、`loading`（3 个 `useState`），`load`、`reloadHistory`、`reloadHead`，加载与会话变化监听（1 个 `useEffect`）；没有进行中的提交时清除续接 ID | 上传模式、`setResumeSubmitOperationId` |
| 3 | `useWorkbenchPanels` | 选中节点与页面面板：`selectedKey`、`detailExpanded`（初值 `window.innerWidth > 1100`）、撤回提示 `notice`、归档对话框目标 `archiveSubmissionId`（4 个 `useState`） | — |
| 4 | `useHistoryCompareRun` | 进行中与已完成的历史比较：`compareState`、`compareError`、`compareNeedsRerun`、`compareConnectionLost`、`refreshCompare`、`historyDrawerCollapsed`、`[, setUrlRevision]`、`compareElapsed`、`bundleStatus`、`downloadRevision`、`historyBundle`、`pairSummaries`、`pairSummaryError`（13 个 `useState`），轮询/下载与比较对摘要 2 个 `useEffect`，URL 派生的 `operationId`/`operationKind`/`historyCompareOperationId`/`compareReplayed`/`showHistoryDrawer`/`showOperationStatus` 与 `closeHistoryDrawer` | — |
| 5 | `useCompareTray` | 比较托盘：`compareRefs`、`compareIntent`、`compareStartError`（`HistoryCompareFailure \| null`）、`comparePending`（4 个 `useState`），`comparisonLocked`，`setCompareSelection`、`toggleCompare`、`sendHistoryCompare`、`startOrRetryCompare(request, fresh)`、`openCompareOperation`、`jumpToCompare` | `selectedKey`、比较运行状态（`historyCompareOperationId`、`compareState`、`bundleStatus`） |
| 6 | `useHistoryTree` | 历史树：`filter`、`currentBaselineOnly`、`sort`（`"label" \| "time"`）、`collapsedNodes`（4 个 `useState`），`rows`、`rowByKey`、`nodeLabel`、`selected`、`comparedKeys`、`visibleRows`，`selectedKey` 默认选中与 URL `workbenchNode` 同步（2 个 `useEffect`），`sortBy`、`toggleCollapse` | 工作区、`history`、`compareRefs`、`selectedKey`、`setSelectedKey` |
| 7 | `useUploadGate` | 上传锁定与 Preview 续接：`resumePreviewOperation`、`uploadLocked`（2 个 `useState`），`resumePending`（1 个 `useRef`），`resumePreviewFromOperation`、`activePreviewOperationId`、`resumeActivePreview`，以及原 JSX 中读写 `resumePending`/`setUploadLocked` 的两个具名函数（中期已无 `uploadRef` 与 `useEffect`） | 上传模式（`workspace`、`clearResumeNotice`）、`operationId`、`compareRefs`、`selectedKey` |

组件体保留：`searchRef`（1 个只在 JSX 中挂载的 DOM `useRef`）、`resumeSubmitFromOperation`、`retryResumeNotice`、`openPreview`、`openReview`、`openSubmissionResult`、`activeSubmissionRow`、`actionLabel`、`runAction`、`actions`、`occupancyReason` 与 `DispositionDetails`。（合计：hook 内 `1+3+4+13+4+4+2 = 31` 个 `useState`、1 个 `useRef` + 组件体 1 个 `useRef` = 2 个 `useRef`、`1+1+0+2+0+2+0 = 6` 个 `useEffect`。）

**`ArchiveMainlineDialog`（30 个 `useState`、3 个 `useRef`、1 个 `useEffect`，直接取用 `eb1a3f16fe`）**

| # | hook | 管什么 | 参数 |
| --- | --- | --- | --- |
| 1 | `useArchivePlan` | 一次归档的计划与执行：候选、计划、选中摘要、加载中与错误、集合变化与冲突提示、确认勾选、进行中、失败、结果、进度；`load`、`refresh`、打开时的重置、`start`；供动作使用的 `reportConflict`、`clearPlanAndLoad` | `open`、`submissionId` |
| 2–4 | `useReasonedAction` ×3 | 一个需要理由的动作：目标、理由、幂等键、进行中、错误，`open(target)`；接受、撤销、关闭各一个实例 | — |
| 5 | `useAnomalyResolution` | 接受与撤销的提交（原 `submitResolution`） | 两个动作实例、计划、`reportConflict`、`refresh` |
| 6 | `useCloseSubmission` | 关闭：已知晓、打开时的快照、结果、送达失败后的重试体，`openClose`、`submitClose`、`retryClose` | 关闭动作实例、计划、`reportConflict`、`clearPlanAndLoad`、`refresh` |

### 7.3 审核要点（交 §10 的独立审核）

- **effect 顺序。**
  - **B′ 上 `ComparisonPage`（共 13 个 `useEffect`，外加 `useUploadModeState` 内部）：** 上传模式 hook 内部 → 续接操作 ID → PREVIEW 时刷新上传模式 → R15 顶栏高度 → runtime 订阅 → `SETTINGS_KEY` 持久化 → `COLUMN_WIDTHS_KEY` 持久化 → `loadBundle` → 选择同步 → 侧栏滚动到当前节点 → 重置 `expandedRuns` → 未归属 URL 状态回退 → `loadTable` → 页签条滚动到当前激活页签。
  - **B′ 上 `WorkbenchPage`（共 6 个 `useEffect`，外加 `useUploadModeState` 内部）：** 上传模式 hook 内部 → 续接操作 ID → 加载与会话监听 → 选中键默认选择 → URL `workbenchNode` 同步 → 历史比较轮询与下载 → 比较对摘要。
  - **B′ 上 `ArchiveMainlineDialog`：** 只有打开时重置并加载 1 个 `useEffect`。
  - **按 §7.2 调用后的相对顺序变化只有两处**（`ComparisonPage` 其余 effect 借 `#8`–`#12` 拆分保持“选择同步 → 侧栏滚动 → 重置 `expandedRuns` → 未归属回退 → `loadTable` → 页签条滚动”的 B′ 顺序不变）：
    1. `ComparisonPage` 的 runtime 订阅移到最前（`useUploadModeState` 的参数取自 `browse`）。它的同步部分只登记监听，不读写 state；被跨过的 effect 都不在同步部分调用 `runtime.execute` 或触发 `popstate`；依赖 `[runtime]` 挂载后不变。
    2. `WorkbenchPage` 的历史比较轮询与比较对摘要（`#4`）移到选中键与 URL 同步（`#6`）之前（托盘 `#5` 要读比较运行状态）。两者的同步部分只设比较运行自己的 state、启动计时与异步读取，不读写选中键、详情展开，也不写 URL。
- **重置序列。** 归档对话框的三种重置序列逐项不变：`load` 内（进度、加载中、错误、失败）、`refresh`（进度、结果，再 `load`）、打开时的 effect（计划、候选、结果、失败、两个提示、待定提示、确认勾选、上次摘要、进度，再 `load`）；冲突时 `pendingNotice` 与 `conflictNotice` 的先后不变。
- **跨 hook 的具名函数**（`reportConflict`、`clearPlanAndLoad`、`openWithdraw`，以及 §7.1 第 5 条由内联处理改成的函数）逐个与原处语句对照。
- **捕获的值。** 异步回调捕获的值不变，例如 `resumePreviewFromOperation` 捕获 `compareRefs` 与 `selectedKey`；`useCallback([])` 的 `load` 继续捕获首次渲染的 `gatewayApi`。

## 8. G1、G2 与 FE4b 遗留（含复评 §6.2 未重核项核对结果）

### 8.1 G1：比较对的标签与标题

- **类型：** `posix-tar.ts` 的 `BundleManifest.inputs` 由 `unknown[]` 改为 `{ input_index: number; role: string; display_name: string; display_metadata: Record<string, string>; snapshot_digest: string | null }[]`。`PairSummary` 另取 `before_input_index`、`current_input_index`，载入 bundle 时解析出两侧角色 `beforeRole`、`currentRole` 放进 `PairPresentation`；任一侧找不到时角色为 `null`。
- **推导（含中期 `REVIEW` 模式提交绑定 Preview 结果的更新）：** 中期提交 `53bb1e32dc`、`704a90888b` 将 `REVIEW` 模式改为直接读取提交绑定的不可变 Preview bundle（FULL 两对与 Preview 共用标签与标题，MODIFIED_ONLY 单对 `baseline → modified` 标签为 `基线 → 修改`、标题为 `提交绑定比较：基线 → 修改`）。因此 `PREVIEW` 与 `REVIEW` 均按（前一侧角色 `beforeRole`，后一侧角色 `currentRole`）推导，`HISTORY` 模式不变（按模式与下标，不读 `inputs[].role`，历史比较里那是节点 ref）：

  | 模式 | 前一侧 `beforeRole` | 后一侧 `currentRole` | 标签 `viewLabel` | 标题 `viewTitle` |
  | --- | --- | --- | --- | --- |
  | `HISTORY` | 任意 | 任意 | `节点 (index + 1) → 节点 (index + 2)` | `节点 (index + 1) → 节点 (index + 2)` |
  | `PREVIEW` 或 `REVIEW` | `baseline` | `initial` | 原始组态视图 | 已归档数据 → 原始组态备份 |
  | `PREVIEW` 或 `REVIEW` | `initial` | `modified` | 本次组态视图 | 原始组态备份 → 本次归档组态 |
  | `PREVIEW` | `baseline` | `modified` | 当前基线 → 本次归档组态 | 当前基线 → 本次归档组态 |
  | `REVIEW` | `baseline` | `modified` | 基线 → 修改 | 提交绑定比较：基线 → 修改 |
  | `PREVIEW` 或 `REVIEW` | 其他或 `null` | | `比较视图 (index + 1)` | `比较对 <pair_id>` |

  删除 `pair_id` 子串匹配与 `total === 1` 特判，`total` 参数随之删除（同步更新 `ComparisonPage.tsx` 中面包屑、顶栏视图切换、更多菜单审核摘要共 3 处 `viewLabel` 调用与 1 处 `viewTitle` 调用）。
- **夹具核实与预先声明的 6 张截图变化（Owner 2026-11-17 决定按甲执行，2026-11-18 由 4 张扩为 6 张，§11.4）：**
  - Preview 与提交绑定结果只在 bundle 为 READY 时成功，真实后端已发布的 Preview/Submission bundle 总是完整的一对或两对：完整上传（FULL）是 `("baseline", "initial")` 与 `("initial", "modified")`，只上传修改后（MODIFIED_ONLY）是 `("baseline", "modified")`（其 `pair_id` 虽叫 `initial_to_modified`，但 `inputs` 角色正是 `0: baseline`、`1: modified`）。
  - 除 `schema-keyless` 外，mock e2e 以 `PREVIEW` 或 `REVIEW` 打开的夹具，单对的都是 `("baseline", "modified")`，双对的是 `("baseline", "initial")` 与 `("initial", "modified")`；`schema-keyless` 是历史形状的夹具（只有一对 `left_to_right`，两侧角色是 `fixture-history-ref-0`、`fixture-history-ref-1`，不在推导表里），真实后端不会给 Preview 产出这种 bundle，它落到回退行。推导表不变，不为它加特判。
  - **允许的截图差异：** `e2e/workspace-shell.spec.ts` 里有两个中期新增的用例用 `PREVIEW` 模式打开夹具 `schema-keyless`，共截 6 张整页图：`f-original-structure-nonempty`、`f-filtered-scope-count` 与 `f-search-nonempty-count`（后者与 `f-filtered-scope-count` 同属一个用例，在同一页面上搜索后再截），各 1920、1280 两张。按推导表，面包屑从“当前基线 → 本次归档组态”变成“比较视图 1”。G1 提交起，这 6 张图与 **B′** 基线（**B′@07**、**B′@04**）的差异限于顶栏这一行（面包屑文字变短，同一行里排在它后面的元素可以随之移位），顶栏以下的区域相同或只有噪声。其他任何截图的内容变化仍然即停。
- **测试：** `src/pages/comparison/view-copy.test.ts` 用一张参数表覆盖上表各行（含 `PREVIEW`、`REVIEW` FULL/MODIFIED_ONLY、`HISTORY` 及未知/空角色回退），其中必须有一行“`PREVIEW`、单对、角色不在表内”（如 `("fixture-history-ref-0", "fixture-history-ref-1")`），期望值是通用文案（标签 `比较视图 1`、标题 `比较对 <pair_id>`）。既有断言不改。门禁：`frontend/src` 中没有对 `pair_id` 的子串匹配。

### 8.2 G2：OpenAPI 快照

等 Owner 转交后端“`/internal/v1` 移出公开 schema”的提交 SHA，且该提交已在 `main`。转交的应是后端本轮公开 schema 不再变化的提交 Sb（Owner 2026-11-13 已确认后端 G2 可以修改公开 OpenAPI：在打 tag 前的 `main` 41 条路径、107 个 schema 组件基数上，移出的只有 `/internal/v1` 的 6 条路径与只被它们引用的 schema 组件，保留 35 条非内部路径）。收到后从运行中的 backend 取 `/openapi.json`、保持 canonical 排序写回 `frontend/openapi.json`，用锁定的 `openapi-typescript` 重新生成类型，两者同一个提交，说明写明来源 `main` 提交与 `vnext/` 树。验证：真实 backend `smoke` 的 `openapi_compare=match`、快照中没有 `/internal/` 路径、mock 全量与类型检查通过。不得默认接受新增统计端点或其他未交接差异。若 Sb 含 P1 公开 DTO 字段删除，须同时收到 Owner 逐字段批准与后端消费者清单，逐项核差异；影响前端消费者或需要改变行为即停该项交 Owner。届时整轮已退出的，作为退出后的单独提交按同样验证进入 `main`；后端迟迟未完成的，记为遗留，不阻塞退出。

### 8.3 F7 汇总口径的判断（输入 §8.3）

**结论：暂停前已判为不等价并转入小任务（`fe4b/followups/fe4-behavior-small-task.md` 第 6 项）；中期提交 `34d16d6bd9`（二次装置变化与风险范围 P3）已升级 business-navigation v4/v6 并实现 `tabScope`、`table_notices` 与 `device_definition_changes`，本轮整顿保持“不改行为”，不再变动。**

### 8.4 其余遗留与复评 §6.2 未重核项核对结果

复评 §6.2 列出的未重核项（R9、O2、O4、T2、T4、T6）及 O1、T1、T3、T5 已在打 tag 前的 `main`（`frontend/` 树 `6b8fb33532`）上逐一静态核对（详见阶段区 `reference/reassessment-argon-20261117.md`）：

| # | 项 | 打 tag 前的 `main`（`frontend/` 树 `6b8fb33532`）重核事实与本轮做法 | 完成标准 |
| --- | --- | --- | --- |
| O1 | `loadTable` 的接线没有用例保护 | **重做（吸收预审 F1 修正，参考 `a4c575a7db`）。** `loadTable` 在中期增加了 `unassigned`、`needsBlankProvenance`、`currentCanonicalBlanks`、`deletionLayout` 与 `setScopedRows`。在 H3 之后，严格按 B′ 的同步段顺序在 `features/view-model/table-assembly.ts` 拆出三个纯函数（I/O 与 `setState` 留在 `useTableData`）：① `checkTableRowLocations`（在第一次 `await` 之后、读 parquet 元数据 `await` 之前计算 `publishesFilterTabs`、`exactTable` 并调用 `validateRowLocations`）；② `decodeTableEncodings`（在元数据 `await` 之后、`setBeforeRows`/`setCurrentRows`/`setAnnotations` 三个 `setState` 之前解码 `beforeEncodings`、`currentEncodings` 与 `currentCanonicalBlanks`）；③ `assembleTableRows`（在三个 `setState` 之后调用 `buildBrowseRows`，返回 `{ rows, scoped }` 供 `setRows`、`setScopedRows`）。用现有夹具 bundle 加单测 `table-assembly.test.ts` | `loadTable` 中 `await`、校验、解码与 `setState` 的先后顺序与 B′ 完全一致；复审探针 R10d（两侧编码换成空 Map）与 R11f（`exactTable` 写死 `false`）在 07 临时提交上各自使至少一个新用例失败，探针 SHA 记入 handoff、不入候选 |
| O2 | `table_scope` 提升的死代码 | **已重核：中期已完成。** 中期提交 `34d16d6bd9` 已从 `model.ts` 删除 `DerivedTable.tableScope` 字段、初值与 `deriveBundleView` 的提升循环，并从 `ComparisonPage.tsx` 删除 `?? table.tableScope`。本轮在 B′ 上只做静态确认，无需再改代码 | `model.ts` 与 `ComparisonPage.tsx` 中无 `DerivedTable.tableScope` 死代码；`NavigationTableNotice.table_scope` 是有消费者的有效事实，不删 |
| O4 | 过时注释 | **已重核：中期已完成。** 中期提交 `3e05f0aae9` 重排比较页单行顶栏时，已移除 `styles.css` 中 `.compare-status` 上方过时的 N5 `flex-wrap` 注释（现 N5 注释位于 `.disabled-reason` 上方且与实现一致）。本轮在 B′ 上只做静态确认，无需再改代码 | `styles.css` 中无过时 N5 注释 |
| O5 | handoff 的尝试记录 | 已写入 kickoff §6 | 已写 |
| R9 | W6 忙态截图不稳定 | **已重核：问题仍在，手工重放 `bef2a49160`。** `e2e/upload-mode.spec.ts` 仍在 `settleAfterResize` 之前调用 `waitForStableHeader` 且使用 `header.screenshot()`。将 `waitForStableHeader` 移到 `settleAfterResize` 之后，改用不改变滚动位置的视口可见区域裁剪截图（`page.screenshot({ clip })`）连续两次逐字节相同，并核对门前门后 `window.scrollY` 不变；`e2e/guard.ts` 导出 `Locator` | 07 连续两次 mock 全量、04 对 07 各一次 `compare-screenshots.py --stable`，都只有相同与噪声 |
| T1 | 真实旅程 trace 带 `authorization` | **已重核：取用 `f41608b3d4`、`583a72c5da` 独立脚本并手工接入 B′ 入口（吸收预审 F6 修正）。** 新增只读标准库脚本 `frontend/scripts/redact-entry-tokens.py`（`python3 -I` 运行）；`run-real-backend-e2e.sh` 在 Playwright 结束后、复制 `$LOG_DIR/artifacts` 到证据目录后，在 `set +e` 下调用该脚本，把生成的全部 token（含两个服务级 token，见 T5）与 `gdds-handoff=` 载荷在明文及 zip 成员中逐个替换为固定占位，输出经 `log` 写进入口日志并写一行 `trace_redaction=ok\|failed`，同时记入 `suite-summary.txt`。照常计算 `SUITE_EXIT` 与写出测试摘要（不覆盖或丢弃测试本身的结果）；若文件改写失败（`token_redaction_file_error`）或脱敏后残留计数不为 0，记 `trace_redaction=failed` 并在入口末尾以非零退出 | 在 05 上用一个只为制造失败的临时提交（不入候选，SHA 记入 handoff）跑一次真实 backend `smoke`，保留的 trace 逐成员解压后，入口生成的 token（§8.4 T5 的模式）与“`Bearer ` 后接 token 字符”均为 0，源码模板 `Bearer ${` 单列；补充验证：在 05 的 clean 已提交 worktree 上用树外运行时生成的合成样本确认正常替换 exit 0、只读文件报 `token_redaction_file_error` 且 exit 1（用后销毁样本） |
| T2 | 凭据检索必须解压 zip | **已重核：规则已在 kickoff §6 就位**，由 T1 与 T5 落实 | 规则已写；由 T1、T5 强制执行 |
| T3 | 真实 backend 入口复用日志目录时失败（E1） | **已重核：手工重放 `687e62636b`（吸收预审 F7 修正）。** `run-real-backend-e2e.sh` 中期新增了 `--suite cfgtest`（+82/−11）；重核全部 `$LOG_DIR` 与容器 `/results` 写出点（`run-real-backend-e2e.sh`、`playwright.real.config.ts`、`e2e-real/*.ts`、`e2e-real/lib/*.ts`），固定名输出共 **11 项**：`groups-control`、`processing-groups.log`、`openapi-runtime.json`、`openapi-runtime.normalized.json`、`openapi-snapshot.normalized.json`、`openapi.diff`、`results.json`、`suite-summary.txt`、`input-scope-results.json`、`artifacts`（Playwright `outputDir`）、`evidence`（`t1` 截图目录 `resultsDir()/evidence`）。入口在取得节点占用之前检查 `--log-dir` 是否已存在上述任一项，有则逐个列出并以 2 退出。handoff 写出完整清单与查找命令 | 05 上分别向带旧 `groups-control/` 和带旧 `artifacts/` 的目录运行一次，均在取得占用之前以 2 退出并写明原因；T1 的 `smoke` 用新目录正常通过；04/05 每次真实运行使用单独的日志目录 |
| T4 | t1 稳定门使 1280 正式截图取景偏移（E2） | **已重核：问题仍在，手工重放 `bef2a49160`。** `e2e-real/t1.spec.ts` 中期只改了 `openSidebarTab` 与 `assertTabsReachable`，`waitForGridShotReady` 仍用 `grids.first().screenshot()` 且未记录滚动位置。改为按网格在视口内的可见区域做 `page.screenshot({ clip })` 比较，不改变页面滚动位置，并在 `shot-gate` 日志行加记 `scroll_before=<n> scroll_after=<n>` | 05 上的两次 `t1` 运行（§9“t1”一段）都满足（FE4 的样本数为“`shot-gate` 26 行、11 张有 pregate、9 张原受影响”；B′ 上按 `t1.spec.ts` 的截图调用点清单重数并逐项对应，不少验截图；中期改过顶栏和页签条，原判据不适用时先交 Owner，不自行改判据，也不加跑 `t1`）：① 每个 `shot-gate` 行全部 `rendered=ok`，`stable` 为数字，无 `timeout`、`unstable`、`error`，`scroll_before` 与 `scroll_after` 相同；② 按 `t1-frame-scan.py` 方法测顶部均匀行数：有 pregate 诊断图的正式 1280 图与各自的 pregate 逐字节相同，若不同，只允许 `compare-screenshots.py` 判为噪声、差异只在 Canvas 网格线交点，且 `scroll_before` 与 `scroll_after` 相同；没有 pregate 的 `device-tabs`、`forward-channel` 的顶部均匀行数不大于 5（B′ 新顶栏的内边距），并目检顶栏与表格页签条完整可见；原受影响的对应正式 1280 图目检表格页签条可见；③ `t1` 判据行与 B′ 一致。B′ 上的样本数为 `shot-gate` 24 行、pregate 10 组、PNG 38 张（两处 `fe4-t1-nav-diagnostics` 按诊断数有条件出现）。② 与样本数为 Owner 2026-11-18 按 B′ 新顶栏修订（§11.4） |
| T5 | 凭据检索的模式与时点（E3） | **已重核：直接取用 `50f3f1a89e` 的 `frontend/scripts/scan-credentials.py`（吸收预审 F5 修正）。** 重核 `run-real-backend-e2e.sh` 全部 token 生成点：① 服务级 `RS_BEARER`（`<前缀>-rs-<32位hex>`）与 ② `INTERNAL_BEARER`（`<前缀>-internal-<32位hex>`，`journeys` 前缀为 `fe3b`，`smoke`/`t1`/`cfgtest` 前缀为 `fe3a`）；③ `smoke` 角色与输入 scope（`fe3a-<身份段>-<32位hex>`）；④ `journeys`、`t1` 与中期新增 `cfgtest` 的“场景-角色”（`fe3b-<slug>-<role>-<32位hex>`）。单一正则 `fe3[ab]-[a-z0-9-]+?-[0-9a-f]{32}(?![0-9a-f])` 完整覆盖全部四类。脚本只用标准库、`python3 -I` 运行，递归扫描明文与 zip 成员；每次运行前先自检，生成三种形状（`fe3a-submitter-…`、`fe3b-r2-preview-submitter-…`、`fe3b-rs-…`）在明文与 zip 成员中各一份（共 6 份），**逐份单独核对**每份样本的 `entry`、`bearer`、`dir-token`、`gdds-handoff`（及明文 `template`）均命中才算 `self-check=ok`，否则以 2 退出 | 05 上验证：① 正常脚本自检通过（6 份样本逐份 `result=ok`）；② 树外复制脚本将模式改为漏掉 `fe3b-rs-` 的写法，自检失败并以 2 退出（输出留存 `evidence/post-midterm/`，用后删变异脚本）。入口改完之后的第 7 步与第 10 步全部真实运行（含重跑与失败尝试）结束后对其日志与证据目录执行，计数均为 0 |
| T6 | `check-handoff-hex.py` 不核截断形式（E4） | **已重核：文件未动，直接取用 `017dfc90d1` 对 `frontend/scripts/check-handoff-hex.py` 的修改。** 每个 `<hex>…<hex>` 截断形式的前缀与后缀必须各不少于 4 位十六进制，且唯一匹配一个已知完整值（来自 `--sha-file`、`--evidence-file`、`--source-dir` 或 `--git-objects`）；过短、无匹配或匹配多个时逐行列出并以 1 退出 | 在 05 的 clean 已提交 worktree 上对树外样本 handoff（含正确截断、前缀错、后缀取自值中间、2+2 过短）运行以 1 退出并逐行指出错误；对本轮实施 handoff 运行以 0 通过 |

**T1 的设计。** token 进入 trace 的途径不止请求头：`addInitScript` 与 `page.evaluate` 的参数、Node 侧 `APIRequestContext` 请求都会被记录（FE4b 的 trace 中 16 个 token，14 个在请求头、2 个在动作记录）。只关掉网络记录不够。由真实 backend 入口在 Playwright 结束后处理保留下来的 trace：入口自己生成全部 token（含两个服务级 token，§8.4 T5 的四类），逐个 zip 成员把每个 token 值与 `gdds-handoff=` 的载荷换成固定占位，再逐成员检索并把计数写进日志（`trace_redaction=ok|failed` 与各项计数）；处理失败或检索不为 0 时入口以非零退出并写明原因，不覆盖测试本身的结果。其余排障内容（动作、截图、DOM 快照、网络时序）保留。完成标准以“在 05 上用一个只为制造失败的临时提交（不入候选，SHA 记入 handoff）跑一次真实 backend `smoke`，保留的 trace 逐成员解压后，入口生成的 token 与‘`Bearer ` 后接 token 字符’均为 0，源码模板 `Bearer ${` 单列”为准，两项合成样本验证（正常替换 exit 0、只读文件 exit 1）作为补充保留。

## 9. 顺序、验证与退出

| 步 | 内容 | 验证（`07` mock 全量带截图，每次均与 **B′@07** 比较并记录五类计数，除非另注） |
| --- | --- | --- |
| 0a | 在 **B′** 候选（打 tag 之前）上，由前端实施会话取 `07` 的 mock 全量与截图（**B′@07**）、`04` 的 mock 全量与截图加上传包校验（**B′@04**）、`04` 的真实 backend `journeys` 完整集对照（`--suite journeys --subphase fe4b`，单独 `--log-dir`） | mock 全量失败算中期遗留，先修，在修复后的头上重取全部基线，不混用旧提交的结果；`journeys` 的失败逐个记录，不阻塞；运行没有进入 suite 的，记“未完成对照”，修正后重开一次。基线 `journeys` 按 §2 基线记录规则手工检索 zip 并如实记录 |
| 0b | `gw08-midterm-exit` tag 由 Owner 指定的会话打出并由 Owner 转交后，核对 tag，从 **B′** 切新分支 `fe-remediation`，重核本文引用的函数与数量 | 确认 **B′** tag 与 0a 基线提交一致；函数与数量核对结果记入 handoff |
| 1 | H4 工具提交（取用 `c5d5482193`）；核对 lockfile SHA256（`3cd77751…`）并复用 `07`、`05`、`04` 已有的 `fe-remediation/npm-cache`（归档 `332deeb8…`）；`FormulaCard` 标题改成 `{" · "}` 的手工提交；只含 `prettier --write .` 输出的格式化提交 | 在格式化提交的父提交上重复执行 `prettier --write .` 到第二遍无变化，得到的树与格式化提交相同；入口全过（含 `format:check`）；与 **B′@07** 截图比较只有相同与噪声（6 张公式截图内容变化为 0） |
| 2 | H1（取用 `65bcaefa21` 规则与单测，迁 `ConnectionStatusIndicator.tsx` 含中期 `compact` 属性，重做两页面导入） | 入口全过（含 `layering-rules.test.ts` 13 项单测）；与 **B′@07** 截图比较只有相同与噪声 |
| 3 | H2（在 B′ 上机械拆分 `ComparisonPage.tsx`，§6） | 同上；`git diff -M --color-moved=dimmed-zebra` 自查 |
| 4 | H3，三个提交（`ArchiveMainlineDialog` 取用 `eb1a3f16fe`；`WorkbenchPage` 与 `ComparisonPage` 在 B′ 上按 §7.2 重做） | 每个提交后各跑一次 `07` mock 全量；计数不变；每次与 **B′@07** 截图比较只有相同与噪声 |
| 5 | O1（三段纯函数与单测；确认 O2、O4 已在中期完成） | 同上（单测计数增加）；O1 的 R10d、R11f 两个探针在 `07` 临时提交上各自使至少一个新用例失败 |
| 6 | R9、T4 的稳定门（手工重放 `bef2a49160`） | `07` 连续两次 mock 全量 `--stable`，且与 **B′@07** 比较只有相同与噪声；T4 的 `t1` 验证在第 7 步 |
| 7 | T1、T3、T4、T5、T6（取用 `redact-entry-tokens.py`、`scan-credentials.py`、`check-handoff-hex.py`，手工重放 `run-real-backend-e2e.sh` 的 T1/T3 接线） | `05`：T1 用一个只为制造失败的临时提交（不入候选，SHA 记入 handoff）跑一次真实 backend `smoke`，保留的 trace 逐成员解压后入口 token 与“`Bearer ` 后接 token 字符”均为 0、源码模板 `Bearer ${` 单列，另加树外合成样本验证（正常替换 exit 0、只读文件 exit 1）；T3 对带旧 `groups-control/` 与 `artifacts/` 的目录在占用前以 2 退出，且 T1 的 `smoke` 用新目录正常通过；T4 的 `t1` 调试运行一次（满足 §8.4 T4 标准）；T6 在 clean 已提交 worktree 上对树外错误截断样本以 1 退出；T5 正常自检通过、漏 `fe3b-rs-` 变异自检以 2 退出，且在以上全部运行（含失败尝试）结束后检索这些运行的日志与证据目录，计数为 0 |
| 8 | G1（在 B′ 上重做 `viewLabel`/`viewTitle` 角色推导与 `view-copy.test.ts`，§8.1） | `07` mock 全量通过（单测计数增加，含“`PREVIEW`、单对、角色不在表内”参数行）；与 **B′@07** 截图比较：除预声明的 `schema-keyless` 两个用例 6 张图（`f-original-structure-nonempty`、`f-filtered-scope-count`、`f-search-nonempty-count` 的 1920 与 1280）差异限于顶栏这一行、顶栏以下相同或只有噪声外，其余截图只有相同与噪声，其他任何截图的内容变化即停；`frontend/src` 中 `pair_id` 子串匹配为 0 |
| 9 | 候选 C、handoff、独立审核（§10，审核范围 `B′..C`）；有修复按审核结论定向复审 | 审核通过并获 Owner 确认后进入第 10 步（不抢跑 04/05 退出证据） |
| 10 | `04` 证据：在 C 的 clean detached worktree 经 `run-evidence-wrapper.sh` 依次跑 mock 全量带截图、上传包校验、真实 `smoke`、`journeys` 完整集（`smoke` 不传 `--subphase`，`journeys` 用 `--subphase fe4b`，两个真实 suite 各用单独的 `--log-dir`）。同时在 `05` 上对 C 跑 `t1`（`--suite t1 --subphase fe4b`，单独 `--log-dir`）。全部运行（含重跑与运行前失败的尝试）结束后，用 `scan-credentials.py` 检索每一次运行的日志与证据目录 | 全部通过（基线上已有的失败不构成第 10 步或 S3 的豁免）；mock 计数等于 B′ 加本轮新增，`smoke`、`journeys` 用例数与 B′ 相同；`04` 截图对 **B′@04** 除 §8.1 G1 预声明的 6 张图差异限于顶栏一行（顶栏以下相同或只有噪声）与 §11.4 的 R9 10 张图（卡片 71.5px→72px 及其下方 0.5px 下移）外，其余截图只有相同与噪声，`04` 对 `07` `--stable`（§11.4 E1 的三张按噪声处理）；四个上传包与 **B′** 的 `04` 输出逐字节相同；OpenAPI 比对通过；`t1` 满足 §8.4 T4 标准；凭据检索自检通过、对本步全部运行的目录计数为 0；handoff 回源（含截断形式，T6）通过 |
| 11 | G2（收到后端 Sb SHA 后，可在 9 之前或退出之后） | §8.2 |
| 12 | 整顿后的后端 Sx 上跑一次 `journeys`（§9.1，与第 0a 步 B′ 的 `journeys` 对照结果逐用例对比归因） | §9.1 |

- **t4 筛查（FE4 kickoff §7.4 的做法）：** `upload-package.ts` 中期未改动，`UploadStepCard.tsx` 在 `B′..C` 中只有 H4 格式化提交的改动（其他各项都不改这两个文件，H3 只动 `WorkbenchPage` 一侧，`UploadStepCard` 的接口不变）。审核会话确认这两个文件在 `B′..C` 中只有格式化提交的改动且该提交可重放（§4）；满足时打包流程没有改变，不触发 t4 重测。上传包校验的四个包与 **B′** 逐字节相同是直接证据。
- **t1（T4；Owner 2026-11-13 按 DC33 确认甲，§11.2 第 3 项）：** 本轮不改真实数据的处理、`t1` 的旅程步骤与判据；但 T4 改了 `t1.spec.ts` 的截图稳定门，故在 `05` 上跑两次 `t1`：第 7 步用含 T4 的提交跑一次 `t1`（调试，不作证据），按 §8.4 T4 的标准核对；第 10 步在审核通过后于 `05` 上对 C 跑一次 `t1` 作为证据，与 `04` 并行，参数为 `--suite t1 --subphase fe4b`（输入 `/home/dev/gateway-real-dumps/source-dirs/` 的 `t1-v1`、`t1-v2`）。`04` 的退出证据不加 `t1`。本轮真实数据 `t1` 只有这两次；需要更多运行时先交设计会话与 Owner。
- **失败处理：** 证据或逐步截图比较（除 §8.1 G1 预声明的 6 张图顶栏一行差异与 §11.4 的 R9 10 张图外）失败即停，交设计会话与 Owner。被测对象运行前的命令、环境与缓存问题按 AGENTS 的构建故障快速修复处理，每次尝试（包括运行前失败）都记进 handoff。
- **退出：** 审核结论为可以退出且 Owner 确认后，设计会话（或 Owner 指定的会话）打附注 tag `fe-remediation-exit`，以 `--no-ff` 合入 `main`；合入前与当时的 `main` 头试合并，`frontend/` 有冲突时停下。**合入 `main` 之后**（严禁提前），在 `04`、`05`、`07` 上把新缓存解包到默认目录 `/home/dev/gdds-fe-cache/frontend/npm-cache`（`05` 没有该目录时新建），默认归档换成新归档（`332deeb8…`）、旧归档改名保留，记录前后 SHA256；`fe0` 目录不动。随后告知 Owner，由 Owner 转告后端与其他前端会话：此后 `main` 上的前端入口用默认目录的新缓存，预检改为核对新归档的 SHA256。退出后，`fe-vnext` 分支与 `/home/dev/gdds-fe` 工作区的只读保留期结束，可按工作区回收规则归档并清理。不推送。§9.1 的那次 `journeys` 不阻塞打 tag。
- **一页总结：** 实施会话在退出前写 `docs/frontend-vnext/frontend-remediation-summary.md`，含 §12 的门禁说明（遵循 AGENTS“阶段总结写给人看”，机器记录用引用指向阶段交接区 `evidence/post-midterm/`）；在“未测限制”里写明 `cfgtest` 没有在改动后的入口上运行（Owner 2026-11-17 决定不加验证）。

### 9.1 整顿后的后端上跑一次 `journeys`（Owner 2026-11-13、2026-11-16）

- **决定：** 前端 `journeys` 完整集至少有一次跑在包含后端整顿退出提交（下称 Sx）的后端上，由前端会话在 `04` 执行（`project-review-2026-11.md` §20.2）。第 0a 步在 **B′** 候选上跑的 `journeys` 完整集作为本次运行的归因对照基线（复评 §2 第 4 条、§6.3 第 6 条）。
- **触发：** Sx 由 Owner 转交并记入 `log.md`。收到之前不猜测后端进度。
- **方式 1：** 第 10 步运行时 C 的 `vnext/` 已包含 Sx（`git merge-base --is-ancestor Sx C` 成立，例如做 G2 时合入的 `main` 已含它）。这时第 10 步的 `journeys` 就算数，不另跑；在 `log.md` 记一句并写明核对命令的结果。
- **方式 2：** 否则在两端都合入 `main`、且 G2 的快照提交也已进入 `main` 之后补跑一次：取当时的 `main` 头 M2（核对 Sx 与 G2 快照提交都是 M2 的祖先），在 `04` 上 M2 的 clean detached worktree 中经 `run-evidence-wrapper.sh` 跑 `journeys` 完整集，参数与第 10 步相同（`--subphase fe4b`），用单独的 `--log-dir`；npm 缓存用“退出”一段更新后的默认目录。快照必须与该后端一致，否则入口会停在 OpenAPI 比对，所以排在 G2 之后。运行结束后用 `scan-credentials.py` 检索其日志与证据目录。
- **时限：** 不阻塞 `fe-remediation-exit`；在后端 S3 实施开始之前完成（`project-review-2026-11.md` §20.2）。
- **记录：** 结果记入 `log.md`（M2 或 C、Sx、节点、hostname、起止 UTC、起止 HEAD、exit code、用例数、日志 SHA256、凭据检索结果），证据放交换目录 `evidence/post-midterm/`，并用一句话告知 Owner。
- **对照：** 以第 0a 步 **B′** 完整 `journeys` 的用例名、结果、错误码与状态码逐项对比 C 或 M2，分清原有失败、新失败、已修复与无法归因；若规则、夹具或用例集另变须标明，不能仅凭总数相同认定等价。
- **失败：** 失败即停，不改断言、不放宽判据。把逐用例差异表、原始失败用例与观察到的错误码、状态码交 Owner 判断归属。**基线上已有的失败不阻塞开始整顿，但不构成第 10 步或 S3 的豁免**，整顿后失败或未知不满足 S3 放行；修复后重做受影响验证，不能用基线失败关闭 finding。被测对象运行前的命令、环境与缓存问题仍按 AGENTS 的构建故障快速修复与 DC68 处理并记录每次尝试。

### 9.2 通道规则并行修改（复评 §1 第 2 条、§6.3 第 7 条、§8）

通道规则并行修改只改规则内容，不改前端界面，前端整顿不需要为它让路。规则内容、版本与 golden 作为独立提交进 `main`，与整顿提交分开，经 Owner 通知两端。

若规则改动合入 `main` 时带动了前端测试夹具，收到 Owner 通知后记录规则提交与受影响用例，在**包含该规则改动的提交**上重取截图基线，再继续后续比较；规则提交与整顿提交分开，分别判断行为差异，不把规则变化混进重构提交。为分清整顿回归与规则带动的变化，保留“规则提交应用到未整顿前端”的对照，或等价的逐提交前后对照，不把重构后的新图直接升为基线；不重打 `gw08-midterm-exit`，只记录新规则版本对应的截图对照。来源冲突或业务差异无法归因时停受影响比较交 Owner。

### 跨端交接（Owner 2026-11-13 开工补充）

前后端由不能直接通信的不同 agent 执行。只写本端阶段区并向 Owner 给出可直接转发的文字；不调用消息工具联系另一端、不写另一端 log/prompts、不把共享文件出现或 Git 分支前进当作对方已收到通知。接收方在本端 log 记录 Owner 原文、来源提交及处理结果，再由 Owner 回传。没有收到依赖输入时只暂停相关步骤，其余工作继续。

| 交接 | 发出时点与必填内容 | 接收方动作与回执 |
| --- | --- | --- |
| BE-SCHEMA-NOTICE | 后端 G2 进入 `main` 时立即发：完整提交、`main` HEAD、`vnext` tree、允许的差异、公开 schema 尚可能变化与否、OpenAPI mismatch 窗口 | 前端记录；未取得最终 schema 前，继续固定 **B′** 的独立整改和 mock，不盲目合入后端新树或绕过 OpenAPI 检查 |
| BE-SCHEMA-FINAL | 后端确认 schema 不再变化时发 Sb、`main` HEAD、`vnext` tree、schema 原件路径/摘要和逐项差异；若有 P1 公开 DTO 删除，附 Owner 逐字段决定和消费者核对结论 | 前端核 Sb 在 `main`，按 G2 同步快照与类型；差异必须全部匹配交接清单。若影响实际前端消费者或需改行为，停相关项交 Owner，不能借生成类型更新隐式修改行为 |
| BE-EXIT | 后端 exit 后发 Sx（tag 指向提交）、tag、`main` HEAD、`vnext` tree、总结/证据索引，明确 Sb 是否仍有效 | 前端核 Sx 祖先关系，安排 §9.1 的 `04` 完整 `journeys`；已有合格运行则回执引用，不重复运行 |
| FE-SCHEMA-ACK / FE-JOURNEYS | 前端发快照提交、合入 `main` 的提交、消费的 Sb/Sx、运行候选/节点/原件、结果（含相对 B′ 对照运行的逐用例归因）与未完成项；新 npm 缓存来源提交/归档摘要/节点路径单列 | Owner 转后端登记。S3 实施前必须核收包含 Sx 的完整 `journeys` 通过结果；失败或未知不算满足 |
| FAILURE / REVISED | 任一端失败或改变已交接的 schema/候选，发旧/新 SHA、失效范围、失败用例、观察到的错误码/状态码和原件；不放凭据 | Owner 决定归属并转发；修复后原审核定向复审、重做受影响验证，再回执。旧回执保留但明确失效 |

Sb 与 Sx 是两个不同用途的提交，不能互相代替。FE `04` 证据及 BE `04` stage gate 共享节点，按现场有效占用排队，不抢占；只有实际冲突才经 Owner 协调。前端保持独立 worktree/分支，后端在 `main` 推进；前端准备合入时经 Owner 转交候选、写入范围和 `main` 接入时点，不让两个会话同时修改同一 worktree。

## 10. 独立审核

整轮末尾一次，由 Owner 转交给独立的新会话，审核 **`B′..C`**，重点 H3，其余各项一并看。`fe-remediation/evidence/` 中的暂停前旧证据只作参考，不替代本轮在 C 上的证据与独审。单 agent 实施不取消独立审核，也不让实施者自行组建审核团队。

- **角色：** Owner 安排独立审核会话，模型由 Owner 选择，不套用后端角色/模型分配；报告写明范围、风险与实际模型。该会话一并核对 §9 第 10 步的证据，不强制另设验收核对角色；审核结果和修复意见均经 Owner 转交实施者。
- **H3：** 每个 hook 的职责与 §7.2 一致；`git diff --color-moved` 下非移动改动逐条有理由；§7.1 的各条规则（含初值、依赖数组、同步段语句顺序、非 DOM ref 具名函数）与 §7.3 的 effect 顺序、重置序列、具名函数与捕获值逐项核对；在 `07` 上对每个组件挑一两处风险最高的接线做探针（例如撤掉某个重置或调换两个 hook 的调用顺序），看 mock e2e 是否失败；不失败的记为覆盖缺口，写进报告，不阻塞。
- **H4、H1、H2：** 在格式化提交的父提交上重复执行 `prettier --write .` 到第二遍无变化，得到的树与格式化提交相同，源码中无行内 `prettier-ignore`；三条规则与规则单测；H2 移动是否整块、handoff 是否完整列出非移动改动（`tsconfig.json` 与显式类型标注）；t4 筛查（§9）：两个打包文件在 `B′..C` 中只有格式化提交的改动。
- **G1：** 推导表（含 `PREVIEW`、`REVIEW` FULL/MODIFIED_ONLY、`HISTORY`）、等价性论证与单测（参数表含“`PREVIEW`、单对、角色不在表内”一行）；源码中不再有 `pair_id` 子串匹配与 `total === 1` 特判；审核会话逐张核对预声明的 `schema-keyless` 6 张图（`f-original-structure-nonempty`、`f-filtered-scope-count`、`f-search-nonempty-count` 的 1920 与 1280，§11.4），确认与 **B′** 基线的差异只在顶栏一行（面包屑从“当前基线 → 本次归档组态”变为“比较视图 1”及同行后续元素移位），顶栏以下相同或只有噪声。
- **O1、O2、O4、R9、T1、T3：** 按 §8.4 的完成标准复核：`loadTable` 三段纯函数保持 B′ 的同步段语句顺序；确认 O2、O4 在 B′ 上已无残留（且保留有效的 `NavigationTableNotice.table_scope`）；T1 的临时失败真实 `smoke` 保留 trace 检索在审核会话自己的解压结果上重做（入口生成的 token 与“`Bearer ` 后接 token 字符”均为 0，源码模板 `Bearer ${` 单列），并复核两项合成样本补充验证（正常替换 exit 0、只读文件 exit 1）、入口 `set +e` 与 `trace_redaction=ok` 日志；T3 的 11 项固定名清单（含 `input-scope-results.json`、`artifacts`、`evidence`）与入口实际输出对照，并确认 T1 的 `smoke` 用新目录正常通过。
- **T4：** 稳定门不再改变滚动位置，R9 与 T4 的判定方式一致；对第 7 步 `t1` 按 B′ 的 `t1.spec.ts` 截图调用点清单重数并逐项核对 `shot-gate` 行（含 `scroll_before`/`scroll_after`）与截图（不少验截图；“26 行、11 张有 pregate、9 张原受影响”为 FE4 样本数，B′ 上为 24 行、10 组 pregate、38 张 PNG，§11.4），审核会话自己用 `t1-frame-scan` 的方法重测顶部均匀行数，并目检对应受影响的正式 1280 图表格页签条可见（中期改过顶栏和页签条，原判据不适用时先交 Owner，不自行改判据，也不加跑 `t1`）。
- **T5：** 脚本只用标准库、只输出计数、先自检（逐份核对 3 种形状 × 明文/zip 共 6 份样本全部命中）；入口 token 是一条模式，覆盖全部四类（两个服务级 token、`smoke` 的角色与输入 scope、`journeys`/`t1`/`cfgtest` 的“场景-角色”）；T1 的替换范围含两个服务级 token；审核会话在节点上自己运行它，自检通过后检索第 7 步的日志与证据目录。
- **T6：** 审核会话另做一份含错误截断的样本 handoff，脚本以 1 退出并指出行号；对实施 handoff 运行通过。
- **截图：** 核对实施 handoff 中每一步 `07` 全量对 **B′@07** 的五类计数（G1 之前各步内容变化为 0；G1 起除预声明的 6 张图差异限于顶栏一行外，其余截图只有相同与噪声；R9 修复起另有 §11.4 的 10 张图）；审核会话在 `07` 跑一次 C 的 mock 全量，与 **B′@07** 比较（除这 6 张图差异只在顶栏一行、顶栏以下相同或只有噪声，以及 R9 的 10 张图外，其余截图只有相同与噪声）。
- **结论：** 可以退出、定向修复或停下交 Owner。报告放交换目录 `reviews/`。
- **证据核对（第 10 步之后）：** 按第 10 步的判据逐项核对（含 `04` 截图对 **B′@04** 中预声明的 6 张 G1 图与 10 张 R9 图逐张核对）；`05` `t1` 按 T4 的标准；凭据检索在全部运行（含重跑）结束之后执行、覆盖第 10 步每一次运行的目录，审核会话自己再运行一次 `scan-credentials.py`；handoff 回源含截断形式；写明 §9.1 是方式 1 还是留待方式 2；Sx 尚未转交时写“待定”。

## 11. 与输入的出入与 Owner 决定

### 11.1 2026-11-12（已决定）

**Owner 决定：** 七项均按本节建议。第 1 项选甲；第 2 项本轮不动，记为遗留；第 3、5、6、7 项按本文执行；第 4 项 F7 转入小任务第 6 项。

1. **H1 规则对测试文件的范围（建议甲）。** 甲：规则作用于测试文件，A 层测试可以导入 `features/dev`，渲染组件的用例随组件移走（§5）。乙：规则只作用于生产代码。甲多一个测试文件，保证测试也不跨层用 UI。
2. **A 层目录里还有两个 UI 组件（建议本轮不动）。** `features/session/SessionComponents.tsx`（`SessionGate`、`DeviceBar`）与 `features/view-model/table-state.tsx` 中的 `SurfaceChangeBadge`、`TableFailureNotice` 按 kickoff §4.2 属于 C 层，三条导入规则查不出来。移动不改行为，但 `table-state.tsx` 还要把纯函数与组件拆开，超出输入范围。建议记为遗留，下次改到这两个文件时移到 C 层；Owner 希望本轮做的，归入 H1。
3. **H3 分组的调整**（§7.2 末段）：拆开审核事实与撤回；补导航选择与 R15；归档执行并入计划 hook，关闭动作在共用 hook 之外单独成 hook；`WorkbenchPage` 的选中键归面板 hook、提交续接 ID 单独成 hook。另外两条规则比输入细：“`setState` 先后原样”改为按同步段核对（§7.1 第 2 条）；按依赖排定调用顺序后有两处 effect 顺序与 H 不同，已逐条说明为什么安全（§7.3）。属于输入授权的定稿范围，列出供核对。
4. **F7 判为不等价**（§8.3），按输入转入小任务第 6 项，本轮不改。
5. **T1 的完成标准：** “`Bearer `为 0”细化为“`Bearer ` 后接 token 字符为 0，源码模板 `Bearer ${` 单列”，与 FE4b 的核对口径一致。
6. **退出证据加上传包校验**（§9 第 10 步）：输入只列了 mock 全量、`smoke`、`journeys`。格式化改到 `upload-package.ts`，而前端各阶段（含 §20.5）的 04 证据都含这一项；四个包与 §20.5 逐字节相同即证明打包输出未变，t4 不触发。
7. **新增 T3，修法与 handoff 的建议不同。** FE4 合并后验证的 handoff 建议 `mkdir -p` 或清理后复用，并补“同一 `--log-dir` 先后跑 `smoke` 与 `journeys`”的回归。本计划改为拒绝复用、每次运行用单独目录（理由见 §8.4），回归检查相应改为拒绝检查，不需要为此多跑一次完整 `journeys`。

### 11.2 2026-11-13（计划评审之后）

计划评审意见（主 checkout 根目录 `remediation-plan-review-frontend.md`）与 Owner 同日的决定（`project-review-2026-11.md` §20.2）。

1. **Owner 决定：E2、E3、E4 并入本轮**，代号 T4、T5、T6（§1、§8.4、§9、§10）。同批的 E1 就是 T3，以 T3 的修法为准；E1 建议的 `mkdir -p` 与同目录回归不采用。三项都只改测试工具。T5 采用审核报告的建议，做成仓库内的只读脚本 `frontend/scripts/scan-credentials.py`，并加自检，使每次检索都先证明有检出能力。
2. **Owner 决定：整顿后的后端上跑一次 `journeys`**（§9.1）。
3. **Owner 决定（2026-11-13）：T4 的 t1 验证按甲执行**（DC33）。甲：05 上调试一次（第 7 步）加 C 上的证据一次（第 10 步，与 04 并行），04 不加 t1。未采用乙（只在第 10 步对 C 跑一次）。理由与耗时见 §9“t1”一段。
4. **评审补充，采纳：** T3 的检查清单点名 `input-scope-results.json` 与入口的其他固定名输出（§8.4 T3）。
5. **评审补充，采纳：** kickoff §4.2 的页面 state 规则收窄到 `ComparisonPage`、`WorkbenchPage`、`ArchiveMainlineDialog` 三个组件，与 §7.1 第 1 条的完成标准一致，并保留输入原话“新功能的 state 进入对应的 hook 或新 hook”。原措辞把三个组件的完成标准变成了对所有页面组件的禁令，又没有门禁支撑。
6. **补记与输入的出入：** H1 加了一个用 ESLint Node API 的规则单测（§5），证明三条规则确实生效；输入没有这一项。它不加依赖。
7. **计划复审修正（主 checkout 根目录 `remediation-plan-rereview-frontend.md` §1）：** T5 原先只列了两种 token 格式，漏了入口每个 suite 都生成的 Repository Service bearer 与 backend internal bearer（`fe3b-rs-…`、`fe3b-internal-…` 只有一段，不符合 journeys 的“场景-角色”格式，分别写模式会漏检，而自检也只含那两种格式）。改为：一条模式覆盖四类 token；自检加 `fe3b-rs-` 形样本，明文与 zip 成员各一份；T1 按值替换时含这两个 token（§8.4 T1、T5，§10）。源头是计划评审 §1.3 漏写。复审结论：改完不再评一轮。

### 11.3 2026-11-16 / 2026-11-17（中期合入后重新评估、修订核对与 Owner 决定）

依据 `/home/dev/gdds-stage-exchange/whole-project-review/` 下的 `remediation-reassessment-2026-11-16.md` 与 `remediation-plan-revision-check-frontend.md`：

1. **Owner 决定（2026-11-16）：以 `main` 的新起点 B′（附注 tag `gw08-midterm-exit`）为基础切新分支 `fe-remediation` 重做，不合并 `fe-vnext`。** `fe-vnext`（`583a72c5da`）只读保留到前端整顿退出，按 §3 表取用仍适用的提交；`ComparisonPage`、`WorkbenchPage` 的拆分与抽 hook 在 B′ 的新结构上重做（§6、§7.2），其中 `ComparisonPage` 将“重置 `expandedRuns`”、“未归属回退”、“页签条激活项滚动”分别独立成 hook，保持 B′ 的 effect 顺序，全轮仍只有 §7.3 列出的两处 effect 换序；测试计数基线、截图基线、证据（放入 `evidence/post-midterm/`）与独立审核（`B′..C`）整套重做（§2、§9、§10）。
2. **Owner 决定（2026-11-16）：在打 tag 前的 B′ 候选上加跑一次真实 backend 的 `journeys` 完整集作对照**（§2、§9 第 0a 步、§9.1），失败用例逐个记录，不阻塞开始整顿，用于给整顿后后端 Sx 上的那次 `journeys` 作逐用例归因对照；基线运行按 kickoff §6 的手工方法逐成员检索 zip 并如实记录结果，基线上已有的失败不构成第 10 步或 S3 的豁免。
3. **第一轮预审（F1–F9）的教训写入计划规则：** 保持同步段语句顺序（O1 拆为三段纯函数 `checkTableRowLocations`、`decodeTableEncodings`、`assembleTableRows`）；禁用行内 `prettier-ignore`（`FormulaCard` 标题 `{" · "}` 单独一个手工提交，放在工具提交之后、格式化提交之前，格式化提交只含 `prettier --write .` 的输出）；每次 `07` 全量必与 **B′@07** 比较截图并记五类计数，除第 5 项预声明的 4 张图外出现非噪声变化即停；保持初值与依赖数组原样、内联写非 DOM ref 改为具名函数 `openWithdraw`；T1 保持临时失败真实 `smoke` 保留 trace 解压检索的原判据并保留两项合成样本验证作补充；T3 补齐 `artifacts`、`evidence` 共 11 项固定名输出；T5 自检逐份核对 6 份样本；严禁在合入 `main` 前替换节点默认 npm 缓存（§3、§4、§7.1、§8.4、§9）。
4. **打 tag 前的 `main`（`frontend/` 树 `6b8fb33532`）静态重核结论：**
   - **O2、O4 已在中期完成：** `O2`（`DerivedTable.tableScope` 提升死代码）已由 `34d16d6bd9` 删除（`NavigationTableNotice.table_scope` 是有消费者的有效事实，不删）；`O4`（`styles.css` 中 `.compare-status` 上方过时 N5 注释）已由 `3e05f0aae9` 移除。本轮在 B′ 上确认即可，不再重复改代码（§8.4）。
   - **R9、T2、T4、T6 核对结论：** `R9`（`upload-mode.spec.ts`）、`T4`（`t1.spec.ts` `waitForGridShotReady`）、`T6`（`check-handoff-hex.py`）问题仍在，`T2` 规则已在 kickoff §6 就位，均按 §3 与 §8.4 取用或手工重放；T4 中“`shot-gate` 26 行、11 张有 pregate、9 张原受影响”标为 FE4 样本数，B′ 上按 `t1.spec.ts` 的截图调用点清单重数并逐项对应。
   - **G1 适配中期审核结果复用：** 中期提交 `53bb1e32dc`、`704a90888b` 使 `REVIEW` 模式读取提交绑定的不可变 Preview bundle，FULL 两对与 Preview 共用标签/标题，MODIFIED_ONLY 单对（`baseline → modified`）标签为“基线 → 修改”、标题为“提交绑定比较：基线 → 修改”；§8.1 推导表据此更新，一并消去 `pair_id` 子串匹配与 `total === 1`。
5. **Owner 决定（2026-11-17）：**
   - **计划定稿：** 以 argon 候选为底稿并入 iris 的六处设计（基线运行凭据手工检索与记录规则、保持 B′ effect 顺序的 hook 拆法、第 0a/0b 两步与修复后在新头重取全部基线、§9.2 通道规则带动夹具时的对照与回归区分、T4 在 B′ 上按截图调用点重数、§9.1 逐用例归因对照与基线失败不构成豁免），写回 `frontend-remediation-plan.md` 并删除两份候选文件。
   - **G1 按甲执行：** 接受 `e2e/workspace-shell.spec.ts` 中用 `PREVIEW` 模式打开历史形状夹具 `schema-keyless` 的两个用例所截的 4 张整页图（`f-original-structure-nonempty`、`f-filtered-scope-count` 的 1920 与 1280）面包屑文字从“当前基线 → 本次归档组态”变为“比较视图 1”；自 G1 提交起，这 4 张图与 **B′** 基线的允许差异限于顶栏这一行（面包屑文字变短，同行排在它后面的元素可随之移位），顶栏以下的区域相同或只有噪声，由审核会话逐张核对，其他任何截图的内容变化仍然即停（§3、§8.1、§9、§10）。
   - **不为 `cfgtest` 加验证：** `cfgtest` 与 `t1` 走同一段入口分支，T3 的目录检查在取得占用之前、T1 的脱敏在 Playwright 之后，均与 suite 无关；在退出一页总结的“未测限制”里写明 `cfgtest` 没有在改动后的入口上运行（§9）。

### 11.4 2026-11-18（第 9 步独立审核与第 10 步证据核对之后的 Owner 决定）

依据交换目录 `reviews/fe-remediation-post-midterm-fda178f502.md`（第 9 步审核 F1–F3）与 `reviews/fe-remediation-post-midterm-evidence-fda178f502.md`（第 10 步证据核对 E1–E3），Owner 2026-11-18 均按审核建议确认，并授权审核会话直接修订本计划的相应措辞（记录见 `log.md`）。候选 C 代码不变。

1. **F1：G1 截图例外由 4 张扩为 6 张。** 增加 `f-search-nonempty-count` 的 1920 与 1280；它与 `f-filtered-scope-count` 同属一个用例，变化性质相同。允许差异仍限于顶栏一行，顶栏以下相同或只有噪声（§3、§8.1、§9、§10）。
2. **F2：R9 的一行产品 CSS 及 10 张截图列为例外。** Owner 2026-11-17T09:43–09:45Z 授权在 `frontend/src/styles.css` 的 `.operation-status-card__heading strong` 加 `line-height: 20px;`（提交 `cba228cc11`），修复 B′ 原生的半像素抖动。受影响的 10 张图为 `fe3b-w6-attempt-running`、`fe3b-w6-preview-resumed-card`、`fe3b-w6-resumed-card`、`fe3b-w6-withdraw-busy`、`manual-recovery-required` 各 1920 与 1280；允许差异为卡片高度 71.5px→72px 及其下方整体 0.5px 下移。这是本轮唯一的产品样式改动，退出一页总结的“与设计的偏差”写明这一行 CSS 与授权时间。
3. **F3：T4 判据 ② 按 B′ 新顶栏改写**（§8.4 T4）：没有 pregate 的 `device-tabs`、`forward-channel` 顶部均匀行数为顶栏内边距 5，不再要求为 0；样本数为 `shot-gate` 24 行、pregate 10 组、PNG 38 张。
4. **E1：第 10 步 04 mock 的三张 1920 图按噪声处理。** `s3-workbench-upload-1920`、`s4-grid-main-1920`、`s4-grid-hover-1920` 各差 112 像素（111 个通道差 1、1 个通道差 2，最大连通块 10），全部在面板圆角与边线上，与同次运行已判噪声的图同坐标；这三张在 B′@04、B′@07 与 C@07 逐字节相同，属该次运行的光栅化抖动。不改 `compare-screenshots.py` 阈值，不重跑；以后再出现同类情形仍须停下交 Owner。
5. **E2：T4 判据 ② 的 pregate 比较允许网格交点噪声。** 第 10 步 `fe4-t1-nav-groups-1280`、`fe4-t1-review-1280` 与 pregate 各差 57 像素，恰为 3 条 Canvas 列线与 19 条行线的交点，取景与滚动不变。判据改为“逐字节相同；若不同，只允许判为噪声、差异只在 Canvas 网格线交点，且 `scroll_before` 与 `scroll_after` 相同”。不加跑 `t1`。
6. **E3：`fe4-t1-columns` 落在空页签，本轮接受。** 第 7、10 步选中 0→0 行的 `b1_n2_iec104_dyk_list`（FE4 选中的是有数据的 `b1_n2_iec104_syx_list`）。`pickColumnsTab` 在 `B′..C` 只有格式化改动，选表变化来自中期合入，不是本轮引入。列为下一前端阶段的后续：选表优先有数据行的表，并在该阶段的 `t1` 中验证。

## 12. 交规则会话的门禁说明（整顿结束时，由 Owner 转交）

| 门禁 | 运行 | 失败时 | 豁免 |
| --- | --- | --- | --- |
| 前端格式检查 | `frontend/scripts/run-tests.sh` 在 `npm ci` 之后执行 `npm run format:check`（`prettier --check .`，Prettier 3.9.10，配置 `frontend/.prettierrc.json`） | 逐个列出未格式化的文件，以非零退出，入口失败。修正：在 CT201 的开发 worktree 重复执行 `prettier --write .`（或 `npm run format`）到第二遍无变化、确认 `npm run format:check` 通过后提交 | 只有 `frontend/.prettierignore` 列出的生成类型、测试夹具、OpenAPI 快照与 lockfile；不用行内 `prettier-ignore` |
| 前端分层规则 | 同一入口的 `npm run lint`，规则在 `frontend/eslint.config.js` 的 `no-restricted-imports`，由规则单测 `src/test/layering-rules.test.ts` 证明生效 | ESLint 报 `no-restricted-imports` 并给出层次说明，lint 以非零退出，入口失败 | 无；A 层测试导入 `features/dev` 属于规则范围（§5） |

实际名称与命令以实施后的一页总结为准；这里是设计。

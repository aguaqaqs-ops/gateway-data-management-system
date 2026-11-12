# 前端专项整顿执行计划

- **状态：** 草案，待 Owner 确认 §11 的事项（2026-11-12）。
- **会话分工：** 前端设计会话写本计划、答复设计问题并给出 F7 判断；实施与审核各由独立会话负责（[前端 kickoff](frontend-kickoff.md) §10）。
- **依据：** 主 checkout 根目录的未提交文件 `remediation-input-frontend.md`（下称“输入”）与 `project-review-2026-11.md` §11、§12；[FE4 kickoff](fe4-kickoff.md) §20；AGENTS“前端测试（FD7）”。
- **代码事实基线：** main `eb6530b36e`（FE4 合并后的 H，`H:frontend` `b4806ba6a5`）。本文按函数名引用代码，不引用行号：H4 之后行号全部改变。
- **阶段材料：** 开发主机 `/home/dev/gdds-stage-exchange/fe-remediation/`（`log.md`、`prompts/`、`handoffs/`、`reviews/`、`evidence/`）。入库的只有本计划、kickoff 的修改与退出时的一页总结。

## 1. 范围

| 代号 | 内容 | 输入 | 审核 |
| --- | --- | --- | --- |
| H4 | 引入 Prettier，一次全量格式化，入口加格式检查 | §2 | 实施者与门禁 |
| H1 | 三层导入规则，移动 `ConnectionStatusIndicator` | §3 | 实施者与门禁 |
| H2 | `ComparisonPage.tsx` 中已独立的子组件与纯函数移到单独文件 | §4 | 实施者与门禁 |
| H3 | 三个组件体的 state 按关注点抽成 hook | §5 | 整轮末尾独立审核，重点 |
| G1 | 比较对的标签与标题从 `inputs[].role` 推导 | §6 | 实施者与门禁，末尾审核一并看 |
| G2 | 刷新 OpenAPI 快照 | §7 | 等 Owner 转交后端 SHA |
| O1、O2、O4、R9、T1、T2 | FE4b 遗留中不改行为的项 | §8 | 实施者与门禁，末尾审核一并看 |
| T3 | 真实 backend 入口复用日志目录时失败（FE4 合并后验证交来，输入之后才出现） | — | 实施者与门禁，末尾审核一并看 |

本轮不做：S2b 的设备路由头；会改行为的 FE4b 遗留（小任务，见 §8.3 与交换目录 `fe4b/followups/fe4-behavior-small-task.md`）；`presentation.ts` 中 `logical_path.includes("/blank/")`（等后端给出显式引用）；Prettier 以外的新依赖与状态管理库；顺手改交互、文案或样式。任何一项必须改行为时停下，交设计会话与 Owner。

## 2. 开始条件与基线

- **开始条件：** FE4 kickoff §20.5 合并后验证通过、§20.4 第 6 步收尾完成，本计划经 Owner 确认并合入 main。实施从当时的 main 头开始，记为 B。B 的 `frontend/` 树与 H 不同时（§20.5 失败后有修复），先重新核对本文引用的函数与数量，有出入写进 handoff，不算偏差。
- **测试数量基线：** §20.5 的 04 mock 全量（H 上：vitest 46 个文件 481 项、Playwright 118 项、PNG 252 张；`smoke` 9 项、`journeys` 21 项，见交换目录 `fe4b/handoffs/fe4-post-merge-eb6530b36e-handoff.md`，以审核会话核对后的数字为准）。本轮新增的测试只增加计数；既有用例一个不删、不改断言。
- **截图基线：** 07 上 B 的 mock 全量截图（B@07，实施会话的第一次运行）。04 的退出比较用 §20.5 的 04 mock 截图；B 与 H 的 `frontend/` 树不同时，先在 04 跑一次 B 作基线（调试，不作证据）。
- **H 上的现状数字**（供结果评审对照，口径：`frontend/src` 不含生成类型与测试夹具）：99 个文件 17,285 行；超过 160 字符的行 630，超过 400 字符的 43，最长 2,048 字符（`ComparisonPage.tsx`）。组件体：`ComparisonPage` 579 行，`useState` 30、`useRef` 9、`useEffect` 9；`WorkbenchPage` 557 行，32、3、7；`ArchiveMainlineDialog` 516 行，30、3、1。`pair_id` 子串匹配 4 处（`viewLabel` 2、`viewTitle` 2）。OpenAPI 快照 39 条路径，其中 `/internal/` 6 条。

## 3. 分支、节点与缓存

- **分支：** 实施在 `fe-vnext`（worktree `/home/dev/gdds-fe`，现为 `dddccd359c`，是 H 的祖先）。开始时确认 clean、无人使用，快进到 B。审核对象为 `B..候选提交`。
- **提交：** 每一项单独提交，H3 每个组件一个提交；格式化提交只含 Prettier 的输出。提交说明写代号（例如 `H3:`），不写审核轮次编号。
- **节点：** 按 AGENTS DC91 节点池与原子占用规则。日常 mock 全量在 `ct109-gw-dms-07`（`GATEWAY_FE_TEST_WORKERS=2`）；T1、T3 的真实 backend 调试在 `ct108-gw-dms-05`；退出证据在 `ct108-gw-dms-04`。不在开发主机运行类型检查、lint、单元测试、构建或 e2e。
- **格式化在哪里做：** `prettier --write` 是改写源码的开发操作，与 `npm run generate:api-types` 相同，在 CT201 的开发 worktree 中执行；格式检查作为测试的一部分，只在测试节点由入口执行。
- **npm 缓存（DC67）：** H4 的工具提交改了 `package-lock.json`，之后凡是执行 `npm ci --offline` 的入口（`run-tests.sh`、`run-real-backend-e2e.sh`、`run-packaging-measure.sh`）都需要含 Prettier 的缓存；`validate-upload-package.sh` 不装依赖，不受影响。做法同 FE0（`fe0-handoff.md`）：在 CT201 用该提交的 `frontend/`（`git archive` 导出到 worktree 外）执行 `npm ci --cache <新目录> --no-audit --no-fund`，得到只对应新 lockfile 的完整缓存；打包、计算 SHA256，经局域网传到 07、05、04，解包到 `/home/dev/gdds-fe-cache/fe-remediation/npm-cache`，归档放在同目录。工具提交之后的运行都显式设置 `GATEWAY_FRONTEND_NPM_CACHE`、`GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE` 与 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT`（工具提交）；第 0 步 B 的 lockfile 未变，照旧用节点现有缓存。现有缓存在本轮内不动：04、07 用入口默认目录 `/home/dev/gdds-fe-cache/frontend/`，05 用显式变量指向 `/home/dev/gdds-fe-cache/fe0/npm-cache`，其他会话的预检按 FE4b 的归档 SHA256（`0d861824…`）核对。它们在退出时更新（§9）。缓存缺失即停止，补齐后从头运行。

## 4. H4：Prettier

- **版本：** `prettier` 精确钉 `3.9.10`（2026-10-10 发布；3.10.0、3.10.1 分别在 11-11、11-12 发布，太新）。Prettier 没有依赖，lockfile 只增加一个包。lockfile 的 `resolved` 必须是 `https://registry.npmjs.org/prettier/-/prettier-3.9.10.tgz`：CT201 的 npm 默认取局域网 registry，装完后把新条目的主机改回官方地址，保留路径与 integrity（FE0 B1 的做法），并与 `npm view prettier@3.9.10 dist.integrity` 核对。
- **配置：** `frontend/.prettierrc.json` 只写 `printWidth: 100`，其余用默认值（双引号、分号、`trailingComma: "all"`、LF），与现有代码习惯一致，行宽与后端 ruff 的 `line-length = 100` 相同。定了不再调。
- **忽略：** `frontend/.prettierignore` 列出 `src/features/api/generated/`、`src/test/fixtures/`、`e2e-real/fixtures/`、`openapi.json`、`package-lock.json`，以及 `dist/`、`coverage/`、`playwright-report/`、`test-results/`。生成的类型由 `generated-types.test.ts` 逐字节核对，快照与 lockfile 由各自的工具生成，夹具有 SHA256 核对。不使用行内 `prettier-ignore`。
- **脚本与入口：** `package.json` 加 `format`（`prettier --write .`）与 `format:check`（`prettier --check .`）。`run-tests.sh` 在 `npm ci --offline` 之后、`typecheck` 之前执行 `npm run format:check`：有未格式化文件时逐个列出并以非零退出，入口随之失败。README 补一段用法。
- **两个提交：** ① 工具提交：依赖、lockfile、两个配置文件、脚本、入口与 README；② 格式化提交：只含在 ① 的树上于 `frontend/` 执行 `prettier --write .` 的输出。门禁：在 ① 上重放格式化得到的树与 ② 相同；② 之后 `format:check` 通过。
- **预期规模**（设计会话在 H 的副本上试算，供核对）：格式化改动 123 个文件，`frontend/` 总行数约从 2.86 万增到 4.69 万；格式化后超过 160 字符的行剩 16 行（`src` 中 9 行），都是 Prettier 不拆的长字符串，没有超过 400 字符的行。CSS 中十六进制颜色转小写、`font-family` 引号与换行变化，渲染不变，由截图比较确认。

## 5. H1：分层门禁

**规则。** 在 `eslint.config.js` 用 ESLint 自带的 `no-restricted-imports` 的 `patterns`（`regex`），按目录写三条。消息写明层次与 kickoff §4.2。

| 文件 | 不得导入 |
| --- | --- |
| `src/design-system/**` | 任一路径段为 `features` 或 `pages` |
| `src/features/{api,bundle,session,view-model}/**` | `design-system`、`pages`、`workbench`、`dev` 路径段 |
| 同上目录中的 `*.test.{ts,tsx}` | `design-system`、`pages`、`workbench`（允许 `dev`，见下） |
| `src/features/workbench/**` | `pages` |

- **测试文件的范围（与输入的出入，§11 第 1 项）：** 输入说“现有违规只有一处”，按生产代码计是对的；连测试文件算，还有 6 处：A 层的 5 个测试导入 `features/dev` 的模拟数据与模拟接口（`client`、`scope-session`、`polling`、`journeys`、`workspace` 的测试），`features/api/connection-status.test.ts` 渲染了 `ConnectionStatusIndicator`。设计：规则同样作用于测试文件，只允许 A 层测试导入 `features/dev`（那是共享的测试数据，不是 UI）；把那个渲染组件的用例随组件移走。这是规则范围的定义，不是逐处豁免。
- **移动：** `src/design-system/ConnectionStatusIndicator.tsx` → `src/features/workbench/ConnectionStatusIndicator.tsx`（`git mv`，组件内导入改为 `../api/connection-status`），两个页面的导入随之修改；`connection-status.test.ts` 中渲染组件的用例原样移到 `src/features/workbench/ConnectionStatusIndicator.test.ts`，另两个用例留下。用例数不变，单测文件数加 1。
- **证明规则生效：** 加一个参数化单测（`// @vitest-environment node`），用 ESLint 的 Node API `lintText` 对每条规则各给一个违规样例（必须报 `no-restricted-imports`）和一个合法样例（不报）。门禁配置写错（例如 glob 不匹配）时它会失败，否则规则可能一直“静默通过”。
- **文档：** kickoff §4.2 已写入目录与层的对应关系（本计划的同一提交）。
- **不处理：** A 层内部方向不整齐的导入（`bundle` → `view-model`、`api` → `bundle`）。另见 §11 第 2 项：两个放在 A 层目录里的 UI 组件。

## 6. H2：机械拆 `ComparisonPage.tsx`

新目录 `src/pages/comparison/`（C 层，页面专用；`ComparisonPage.tsx` 留在原处，`App.tsx` 不改）。只移动代码、加 `export` 与 `import`，不改名、不改逻辑、不合并函数。

| 文件 | 移入的内容 |
| --- | --- |
| `view-copy.ts` | `reviewStatusLabel`、`viewLabel`、`viewTitle`、`riskLevelText`、`tabTitle`、`itemBadgeKind`、`itemStatusTooltip`、`rowLabel`、`formatSchemaSummary` |
| `view-helpers.ts` | `bundleErrorState`、`bundlePathForState`、`viewRiskLevel`、`pairDiagnosticDetails`、`tabCount`、`tabChangeKind`、`tabRiskLevel`、`riskTokens`、`recordValues`、`columnWidth`、`matchesGroup`、`matchesItem`，类型 `PairSummary`、`PairPresentation`、`SizedGridColumn` |
| `sidebar-settings.ts` | `Settings`、`SETTINGS_KEY`、`DEFAULT_SETTINGS`、`readSettings` |
| `GridTable.tsx` | `GridTable` |
| `ChangeNavigator.tsx` | `ChangeNavigator` |
| `NavigationDiagnosticNote.tsx` | `NavigationDiagnosticNote` |
| `DebugInfoBar.tsx` | `DebugInfoBar`、`CopyDebugValue`、`RiskReasonDetail` |
| `ReplacementBrowser.tsx` | `ReplacementBrowser`、`ReplacementSide` |
| `FormulaCard.tsx` | `FormulaCard`、`FormulaAlignedPair`、`FormulaLineList` |
| `PreviewHeaderActions.tsx` | `PreviewHeaderActions` |

完成后 `ComparisonPage.tsx` 只剩 `ComparisonPage` 与导入。审核用 `git diff -M --color-moved=dimmed-zebra` 看出是整块移动；非移动的改动只能是导出与导入行。

## 7. H3：三个组件的 state 抽成 hook

### 7.1 规则

1. **完成标准：** 三个组件体不再调用 `useState`、`useReducer`、`useEffect`、`useLayoutEffect`。组件体只剩：按 §7.2 的顺序调用 hook；三个共享 hook（第 3 条）；组合几个 hook 的事件处理（如 `WorkbenchPage` 的 `runAction`）与摆放所需的派生，按 H 上的写法保留 `useMemo`/`useCallback`；挂 DOM ref。每个 hook 的职责能用一句话说清（§7.2）。
2. **只移动，不改语义：**
   - state 的初值随 state 原样进入 hook，包括读 URL、存储与会话的惰性初值。依赖另一个 state 初值的成对 state 放在同一个 hook（`compareStartError` 与 `compareIntent`，`uploadLocked`、`resumePending` 与 `resumePreviewOperation`）。这些初值只读不写，挂载时先后调整不改变取值。
   - effect、`useCallback`、`useMemo` 的依赖数组原样，现有数组中有意省略的依赖不“补全”；不新增也不去掉 `useCallback`/`useMemo`，因为这会改变传给子组件的函数身份。
   - 不合并、不删除 state；看到冗余（如 `ComparisonPage` 中由 runtime 订阅同步的 `search`、`onlyInteresting`、`debug` 三个镜像 state）记进 handoff，留给以后。
   - 回调中语句的先后按“同步段”核对（相邻两个 `await` 之间，或没有 `await` 的整段）。段内对**不同** state 的 `setState` 可以因分组而换序：应用用 React 18.3.1 的 `createRoot`，代码中没有 `flushSync`，同一段内的更新一起批处理，渲染结果相同。对同一个 state 的多次设置、ref 的读写、`await`、函数调用（父组件回调、`runtime.execute`、`load()` 这类会同步执行一段代码的调用），它们彼此之间以及与 `setState` 之间的先后保持原样。§7.3 的重置序列按同一标准核对。
3. **数据流不变：**
   - `useBoundGatewayApi`（内部是 `useState`）、`useGatewaySessionState`、`useUploadModeState`（内部有自己的 state 与 effect）由组件各调用一次，结果作为参数传给需要的 hook。hook 内不得再调用它们，否则会出现第二份状态或第二个绑定实例。
   - 自定义 hook 之间不互相调用。一个 hook 用到另一个 hook 的值或函数时，由组件作为参数传入，所以被用到的 hook 必须先调用；§7.2 的顺序由此而来。
   - 一个 hook 要改另一个 hook 拥有的 state 或 ref 时，由拥有者提供具名函数，函数体是原处连续语句的原样搬入（例如归档对话框三处冲突路径共有的“写待定提示、显示冲突提示、刷新”），或者直接传 setter。不新增 context 或全局 store。
4. **effect 顺序：** 按 §7.2 的顺序调用后，effect 的相对顺序只有 §7.3 列出的两处与 H 不同。其他任何调整都在 handoff 逐条写明为什么安全，标准是被跨过的 effect 在同步部分没有共同读写的 state、ref 或 URL。
5. **ref：** 非 DOM 的 ref（`withdrawKey`、`loadingKey`、`loadedRequest`、`resumePending`、`previousDigest`、`pendingNotice`、`progress`）随所属 state 进入同一个 hook。JSX 中直接写这些 ref 的内联处理（`ComparisonPage` 的撤回按钮，`WorkbenchPage` 中 `OperationStatusPanel` 与 `UploadStepCard` 的回调）改为拥有者 hook 的具名函数，函数体原样。被 hook 使用的 DOM ref（`selectedNavRef`、`workspaceRef`、`pageRef`、`headerRef`、`uploadRef`）由该 hook 创建并返回，组件负责挂载；只在 JSX 中使用的（`searchInputRef`、`reviewNoticeRef`、`searchRef`）留在组件体。
6. **放置：** `ComparisonPage` 的 hook 放 `src/pages/comparison/`，`WorkbenchPage` 的放 `src/pages/workbench/`，`ArchiveMainlineDialog` 的放 `src/features/workbench/archive-mainline/`；文件名 `use-*.ts`。这些目录都受 H1 规则约束。
7. **测试：** 不改既有测试；不为 hook 补单测（覆盖靠既有 mock e2e 与截图）；mock 全量数量不变，截图与 B@07 相同或只有噪声。

### 7.2 分组与调用顺序

输入的分组是起点。下表按组件内的调用顺序排列；“参数”列只写来自其他 hook 或组件的值，`gatewayApi` 省略。

**`ComparisonPage`**

| # | hook | 管什么 | 参数 |
| --- | --- | --- | --- |
| — | `useBoundGatewayApi`、`useGatewaySessionState`（组件调用） | 位置同 H，在最前 | — |
| 1 | `useBrowseRuntime` | 浏览命令 runtime、`browse` 与三个镜像 state、runtime 订阅与 `popstate` | — |
| — | `useUploadModeState`（组件调用） | 共享的上传模式读取 | `enabled` 取 `browse.mode`，所以在 1 之后 |
| 2 | `usePreviewSubmitResume` | Preview 上传模式：提交对话框开关、续接卡片的操作 ID、`refreshUploadMode`、续接回调 | 上传模式、runtime、`browse.mode` |
| 3 | `usePreviewWithdraw` | 顶栏撤回：对话框、进行中、已知晓、错误、幂等键，`openWithdraw`、`confirmWithdraw` | 上传模式、`refreshUploadMode` |
| 4 | `useCompareHeaderHeight` | R15 顶栏高度变量（`pageRef`、`headerRef`） | 会话状态 |
| 5 | `useViewSettings` | 侧栏宽度与折叠（含持久化）、页签溢出弹层、`workspaceRef` | — |
| 6 | `useReviewFacts` | 审核事实与 `reloadReviewContext` | runtime |
| 7 | `useComparisonBundle` | bundle 下载与历史比较等待：`fetchBundle`、`bundle`、`pairs`、`loading`、`error`、两个历史比较状态、两个去重 ref | runtime、`browse`、会话状态、`setReviewFacts` |
| 8 | `useComparisonNavigation` | 分组、导航条目、当前选择（含整表视图）、页签溢出列表、选择同步与滚动（`selectedNavRef`），`chooseTab`/`choosePair`/`openWholeTable` | `pairs`、`browse`、runtime、`setOverflow` |
| 9 | `useTableData` | 当前表：行、两侧行、记录、标注、展开、加载中、可见行、`loadTable`，以及定位、风险计数与原因 | bundle、当前选择、`browse`、`setError`（表读取失败写同一个错误） |
| 10 | `useFormulaPanel` | 公式面板开关、公式数据与 `openFormula` | bundle、当前选择、`browse.mode` |

**`WorkbenchPage`**

| # | hook | 管什么 | 参数 |
| --- | --- | --- | --- |
| — | `useUploadModeState` 等（组件调用） | 位置同 H，在最前 | — |
| 1 | `useSubmitResume` | 提交续接卡片的操作 ID：上传模式的 attempt 带出操作 ID 时设置 | 上传模式 |
| 2 | `useWorkbenchData` | 工作区与 History 加载、`reloadHistory`、`reloadHead`、会话变化时重载；没有进行中的提交时清除续接 ID | 上传模式、`setResumeSubmitOperationId` |
| 3 | `useWorkbenchPanels` | 选中节点与页面面板：选中键、详情展开、撤回提示、归档对话框的目标 | — |
| 4 | `useHistoryCompareRun` | 进行中的历史比较：轮询、断线、计时、bundle 下载与两种重试、比较对摘要 | URL 中的历史比较操作 ID |
| 5 | `useCompareTray` | 比较托盘：已选节点、幂等意图、发起中、发起错误、`comparisonLocked`，加入/移出与发起/重试 | 选中键、比较运行状态 |
| 6 | `useHistoryTree` | 历史树：行、可见行、筛选、只看当前基线、折叠、排序、列宽，选中键与 URL 同步 | 工作区、History、已选节点、选中键与 `setSelectedKey` |
| 7 | `useUploadGate` | 上传门控与 Preview 续接：待执行的上传动作、锁定、就绪、阻止原因、`uploadRef`、`resumePending`，`resumePreviewFromOperation` 与原 JSX 中的两个续接回调 | 上传模式、已选节点、选中键、选中行、行、`setSelectedKey`、`setDetailExpanded` |

组件体保留：`resumeSubmitFromOperation`、`retryResumeNotice`（同时用到续接 ID、History 重载、已选节点与选中键，是组合）、`runAction`、`openPreview`、`openReview` 与 `actions` 等派生。

**`ArchiveMainlineDialog`**

| # | hook | 管什么 | 参数 |
| --- | --- | --- | --- |
| 1 | `useArchivePlan` | 一次归档的计划与执行：候选、计划、选中摘要、加载中与错误、集合变化与冲突提示、确认勾选、进行中、失败、结果、进度；`load`、`refresh`、打开时的重置、`start`；供动作使用的 `reportConflict`、`clearPlanAndLoad` | `open`、`submissionId` |
| 2–4 | `useReasonedAction` ×3 | 一个需要理由的动作：目标、理由、幂等键、进行中、错误，`open(target)`；接受、撤销、关闭各一个实例 | — |
| 5 | `useAnomalyResolution` | 接受与撤销的提交（原 `submitResolution`） | 两个动作实例、计划、`reportConflict`、`refresh` |
| 6 | `useCloseSubmission` | 关闭：已知晓、打开时的快照、结果、送达失败后的重试体，`openClose`、`submitClose`、`retryClose` | 关闭动作实例、计划、`reportConflict`、`clearPlanAndLoad`、`refresh` |

与输入的不同：

- 输入把审核事实与撤回放在一组：前者属于审核模式，后者属于 Preview 上传模式，分开。导航选择与 R15 输入没有列出，补上，否则组件体里仍有 effect。
- 归档执行并入 `useArchivePlan`。输入只列了“候选与计划加载”和三个动作共用的 hook；`load`、`refresh` 与打开时的重置都同时清理计划和执行两边的 state（进度、失败、结果、确认勾选），分开就得把这些 setter 交叉传递，`start` 又要读计划，两个 hook 互相依赖。关闭动作在共用 hook 之外还有四项 state 和自己的提交、重试，单独成 hook。
- `WorkbenchPage` 的选中键归 `useWorkbenchPanels`：托盘发起比较要读选中键，历史树的行又要读托盘的已选节点，选中键的拥有者必须排在两者之前。提交续接的 ID 单独成 hook 并最先调用，因为 `useWorkbenchData` 的加载会清除它；两个续接回调还要用 History 重载与托盘的值，留在组件体。

### 7.3 审核要点（交 §10 的独立审核）

- **effect 顺序。** H 上 `ComparisonPage`：上传模式 hook 内部 → 续接操作 ID → PREVIEW 时刷新上传模式 → R15 顶栏高度 → runtime 订阅 → 设置持久化 → `loadBundle` → 选择同步 → 滚动到当前节点 → `loadTable`。`WorkbenchPage`：上传模式 hook 内部 → 续接操作 ID → 加载与会话监听 → 选中键 → URL 同步 → 历史比较轮询 → 待执行上传动作 → 比较对摘要。`ArchiveMainlineDialog`：只有打开时重置并加载一个。按 §7.2 调用后只有两处变化：
  1. `ComparisonPage` 的 runtime 订阅移到最前（`useUploadModeState` 的参数取自 `browse`）。它的同步部分只登记监听，不读写 state；被跨过的四个 effect 都不在同步部分调用 `runtime.execute` 或触发 `popstate`（PREVIEW 刷新在第一个 `await` 之后才执行命令）；依赖 `[runtime]` 挂载后不变。
  2. `WorkbenchPage` 的历史比较轮询与比较对摘要移到选中键之前（托盘要读比较运行状态）。两者的同步部分只设比较运行自己的 state、启动计时与异步读取，不读写选中键、详情展开与待执行动作，也不写 URL。
- **重置序列。** 归档对话框的三种重置序列逐项不变：`load` 内（进度、加载中、错误、失败）、`refresh`（进度、结果，再 `load`）、打开时的 effect（计划、候选、结果、失败、两个提示、待定提示、确认勾选、上次摘要、进度，再 `load`）；冲突时 `pendingNotice` 与 `conflictNotice` 的先后不变。
- **跨 hook 的具名函数**（`reportConflict`、`clearPlanAndLoad`、`openWithdraw`，以及 §7.1 第 5 条由内联处理改成的函数）逐个与原处语句对照。
- **捕获的值。** 异步回调捕获的值不变，例如 `resumePreviewFromOperation` 捕获 `compareRefs` 与 `selectedKey`；`useCallback([])` 的 `load` 继续捕获首次渲染的 `gatewayApi`。

## 8. G1、G2 与 FE4b 遗留

### 8.1 G1：比较对的标签与标题

- **类型：** `posix-tar.ts` 的 `BundleManifest.inputs` 由 `unknown[]` 改为 `{ input_index: number; role: string; display_name: string; display_metadata: Record<string, string>; snapshot_digest: string | null }[]`。比较对另取 `before_input_index`、`current_input_index`，载入 bundle 时解析出两侧角色放进 `PairPresentation`；任一侧找不到时角色为 null。
- **推导：** Preview 模式按（前一侧角色，后一侧角色）：

  | 前一侧 | 后一侧 | 标签 | 标题 |
  | --- | --- | --- | --- |
  | `baseline` | `initial` | 原始组态视图 | 已归档数据 → 原始组态备份 |
  | `initial` | `modified` | 本次组态视图 | 原始组态备份 → 本次归档组态 |
  | `baseline` | `modified` | 当前基线 → 本次归档组态 | 当前基线 → 本次归档组态 |
  | 其他或 null | | 比较视图 N | 比较对 `<pair_id>` |

  审核与历史模式不变（按模式与下标），不读 `inputs[].role`（历史比较里那是节点 ref）。删除 `pair_id` 子串匹配与 `total === 1` 特判，`total` 参数随之删除。
- **为什么不改行为：** Preview 只在 bundle 为 READY 时成功（`preview_jobs.py` 在 bundle assembly 非 READY 时让 Preview 失败；历史比较同理），所以已发布的 Preview bundle 总是完整的一对或两对：完整上传是（baseline, initial）与（initial, modified），只上传修改后是（baseline, modified）。mock e2e 用 Preview 模式打开的夹具（`fe2a/preview-*`、`fe2b/preview-workbench-normal`、`scenarios/*`）角色与之相同；`scenarios/schema-keyless` 是历史形状，只在单测中使用；`backend-interop` 的 v3 夹具在渲染前被拒绝。只有角色不在上表的畸形 bundle 会从“当前基线 → 本次归档组态”变成通用文案，这正是去掉猜测的目的。
- **测试：** `src/pages/comparison/view-copy.test.ts` 用一张参数表覆盖上表四行与审核、历史两种模式。既有断言（`workspace-shell.spec.ts` 的两个视图页签、`journeys.spec.ts` 的“当前基线 → 本次归档组态”、t1 的两个页签名）不改。门禁：`frontend/src` 中没有对 `pair_id` 的子串匹配。

### 8.2 G2：OpenAPI 快照

等 Owner 转交后端“`/internal/v1` 移出公开 schema”的提交 SHA，且该提交已在 main。把 main 合入 `fe-vnext` 后，按 S2b `116e831701`、`223e073cb4` 的做法从运行中的 backend 取 `/openapi.json`、保持 canonical 排序写回 `frontend/openapi.json`，用锁定的 `openapi-typescript` 重新生成类型，两者同一个提交，说明写明来源 main 提交与 `vnext/` 树。验证：真实 backend smoke 的 `openapi_compare=match`、快照中没有 `/internal/` 路径、mock 全量与类型检查通过。新增的统计端点出现在快照里，前端不调用。届时整轮已退出的，作为退出后的单独提交按同样验证进入 main；后端迟迟未完成的，记为遗留，不阻塞退出。

### 8.3 F7 汇总口径的判断（输入 §8.3）

**结论：不等价，转入小任务（`fe4b/followups/fe4-behavior-small-task.md` 第 6 项），本轮不改。**

Business Navigation Contract“局部事实与表级事实”与 FE4 kickoff F7 要求：`EXACT` 筛选页签用局部事实，`table_scope` 作为独立的表级标记参与页签、项、组汇总与“只看变化/风险”；`TABLE_FALLBACK` 用整表 surface/RiskReport 参与汇总与筛选，并提示按整表。H 上的实现（`model.ts` 的 `deriveGroups`，`ComparisonPage` 的 `tabChangeKind`、`tabRiskLevel` 与侧栏筛选）：

1. **项、组与筛选漏掉表级事实。** 项的 `changeKinds`/`riskLevels` 对筛选页签只取局部事实，不读 `table_scope`。例：某表只有 schema 变化，装置页签局部 `UNCHANGED`、`table_scope.change=true`——项与组没有变化标记，“只看变化/风险”把它隐藏。
2. **`TABLE_FALLBACK` 页签不参与项与组的汇总。** 局部事实为 null 时项得不到任何变化或风险，“只看变化/风险”会隐藏这些装置项（`DEVICE_TAB_FACTS_UNAVAILABLE` 只指向组，救不回项）；Contract 要求此时用整表事实参与。
3. **`EXACT` 页签的徽标用了整表事实。** `tabChangeKind` 先取 surface 整表 `changeKind`，`tabRiskLevel` 在局部风险为 null 时取整表 RiskReport 风险：同表其他装置有行变化时，本装置页签也显示“已修改”或风险。这是 Contract 只给 `TABLE_FALLBACK` 的整表提示行为。

另：O2 描述的“页签/项/组都用 surface 表级值”不完全准确，项用的是局部事实；上面三点已按代码核对。改正会改变侧栏徽标、筛选结果与截图，所以转小任务，由 Owner 看图。

### 8.4 其余遗留

| # | 项 | 做法 | 完成标准 |
| --- | --- | --- | --- |
| O1 | `loadTable` 的接线没有用例保护 | H3 之后，把 `useTableData` 中“两侧行、记录、标注、locator、两侧 metadata 编码与 `exactTable` → 行”的纯组装抽到 `features/view-model` 的一个函数（I/O 留在 hook），用现有夹具 bundle 加单测 | 复审探针 R10d（两侧编码换成空 Map）与 R11f（`exactTable` 写死 `false`）各自使至少一个新用例失败；探针在调试节点的临时提交上做，不入候选 |
| O2 | `table_scope` 提升的死代码 | 删除 `deriveBundleView` 中只从整表页签提升 `table_scope` 的循环、`DerivedTable.tableScope` 字段与初值，以及表头标记中随之恒为 null 的 `?? table.tableScope` 回退 | 单测与截图不变 |
| O4 | 过时注释 | 改写 `styles.css` 中 `.compare-status` 上方 N5 注释，与删除 `flex-wrap` 后的实际一致 | 只改注释 |
| O5 | handoff 的尝试记录 | 写进 kickoff §6（本计划的同一提交） | 已写 |
| R9 | W6 忙态截图不稳定 | 先查根因；查不明时把 `upload-mode.spec.ts` 的稳定门移到 `settleAfterResize` 之后，改为按状态特征判定（例如顶栏各元素的位置在连续 3 帧内不变）。只改测试工具 | 07 连续两次 mock 全量、04 对 07 各一次 `compare-screenshots.py --stable`，都只有相同与噪声 |
| T1 | 真实旅程 trace 带 `authorization` | 见下 | 见下 |
| T2 | 凭据检索必须解压 zip | 规则写进 kickoff §6（本计划的同一提交）；T1 的入口检索按此实现；`run-evidence-wrapper.sh` 没有自带检索，不改 | 规则已写；§20.5 起已按此执行 |
| T3 | 真实 backend 入口复用日志目录时失败（FE4 合并后验证 handoff §4：`smoke` 与 `journeys` 共用 `--log-dir`，`mkdir groups-control` 报 `File exists`，在被测对象运行前退出） | 入口在取得占用之前检查 `--log-dir` 中是否已有上一次运行的固定名输出（实施会话列全，至少 `results.json`、`suite-summary.txt`、`groups-control/`、`processing-groups.log`、`openapi-runtime.json`），有则逐个列出并以 2 退出，提示每次运行用单独的空目录。不改成 `mkdir -p`：残留的 `groups-ready.json` 会被等待循环立刻读到，拿到上一次运行的地址；共用目录还会覆盖上一次的 `results.json` 等结果。只改测试工具；kickoff §6 写明每次真实运行用单独的日志目录（本计划的同一提交） | 05 上向带旧 `groups-control/` 的目录运行一次，在取得占用之前以 2 退出并写明原因；T1 的 smoke 用新目录正常通过；04 证据每次真实运行用单独的日志目录 |

**T1 的设计。** token 进入 trace 的途径不止请求头：`addInitScript` 与 `page.evaluate` 的参数、Node 侧 `APIRequestContext` 请求都会被记录（FE4b 的 trace 中 16 个 token，14 个在请求头、2 个在动作记录）。只关掉网络记录不够。建议由真实 backend 入口在 Playwright 结束后处理保留下来的 trace：入口自己生成全部 token，逐个 zip 成员把每个 token 值与 `gdds-handoff=` 的载荷换成固定占位，再逐成员检索并把计数写进日志（`trace_redaction=ok|failed` 与各项计数）；处理失败或检索不为 0 时入口以非零退出并写明原因，不覆盖测试本身的结果。其余排障内容（动作、截图、DOM 快照、网络时序）保留。实施会话可以选别的做法，但必须满足同一完成标准：在 05 上用一个只为制造失败的临时提交（不入候选，SHA 记入 handoff）跑一次真实 backend smoke，保留的 trace 逐成员解压后，入口生成的 token 前缀与“`Bearer ` 后接 token 字符”均为 0；源码模板 `Bearer ${` 单独计数，不算凭据（与 FE4b 证据核对的口径相同）。

## 9. 顺序、验证与退出

| 步 | 内容 | 验证（07 mock 全量带截图，与 B@07 比较，除非另注） |
| --- | --- | --- |
| 0 | `fe-vnext` 快进到 B；07 跑 B 的 mock 全量带截图 | 计数与 §20.5 相同；得到 B@07 |
| 1 | H4 工具提交；预填充缓存到 07、05、04；格式化提交 | 重放一致；入口全过；截图相同或噪声 |
| 2 | H1 | 入口全过（含规则单测）；截图同上 |
| 3 | H2 | 同上；`color-moved` 自查 |
| 4 | H3，三个提交 | 每个提交后各跑一次；计数不变；截图同上 |
| 5 | O1、O2、O4 | 同上；O1 的两个探针 |
| 6 | R9 | 07 连续两次 `--stable` |
| 7 | T1、T3 | 05：临时失败提交的真实 smoke 与 trace 检索；T3 的拒绝检查 |
| 8 | G1 | 同上 |
| 9 | 候选 C、handoff、独立审核（§10）；有修复按审核结论定向复审 | — |
| 10 | 04 证据：在 C 的 clean detached worktree 经 `run-evidence-wrapper.sh` 依次跑 mock 全量带截图、上传包校验、真实 `smoke`、`journeys` 完整集。参数与 §20.5 相同：`smoke` 不传 `--subphase`，`journeys` 用 `--subphase fe4b`；两个真实 suite 各用单独的 `--log-dir`（T3） | 全部通过；mock 计数等于 §20.5 加本轮新增，`smoke`、`journeys` 用例数与 §20.5 相同；04 截图对 §20.5 的 04 截图只有相同与噪声；04 对 07 `--stable`；四个上传包与 §20.5 的 04 输出逐字节相同；OpenAPI 比对通过；日志、证据目录与 trace 逐成员检索为 0 |
| 11 | G2（收到 SHA 后，可在 9 之前或退出之后） | §8.2 |

- **t4 筛查（FE4 kickoff §7.4 的做法）：** 格式化会改到 `upload-package.ts`（试算 10 行）与 `UploadStepCard.tsx`（685 行），所以 `B..C` 对这两个文件的筛查必然非空。其他各项都不改这两个文件（H3 只动 `WorkbenchPage` 一侧，`UploadStepCard` 的接口不变）。审核会话确认这两个文件在 `B..C` 中只有格式化提交的改动、该提交可重放（§4）；满足时打包流程没有改变，不触发 t4 重测。上传包校验的四个包与 §20.5 逐字节相同是直接证据：包内 tar 头是确定性的（mtime 0 等）。B 的 `upload-package.ts` 与 H 不同时，改为只要求校验通过，并在 handoff 写明。
- **不跑 t1：** 本轮不改真实数据的处理、判据与 t1 用例；G1 的三种 Preview 标签由 `journeys` 的 `r2-preview`（面包屑“当前基线 → 本次归档组态”）与 `r2-full`（两个视图页签名）在真实 backend 上覆盖。
- **失败处理：** 证据失败即停，交设计会话与 Owner。被测对象运行前的命令、环境与缓存问题按 AGENTS 的构建故障快速修复处理，每次尝试（包括运行前失败）都记进 handoff。
- **退出：** 审核结论为可以退出且 Owner 确认后，设计会话（或 Owner 指定的会话）打附注 tag `fe-remediation-exit`，以 `--no-ff` 合入 main；合入前与当时的 main 头试合并，`frontend/` 有冲突时停下。合入后，在 04、05、07 上把新缓存解包到默认目录 `/home/dev/gdds-fe-cache/frontend/npm-cache`（解包只增加条目，旧提交仍可用；05 没有该目录时新建），默认归档换成新归档、旧归档改名保留，记录前后 SHA256；`fe0` 目录不动，只适用于整顿合入之前的提交。随后告知 Owner，由 Owner 转告后端与其他前端会话：此后 main 上的前端入口用默认目录的新缓存，预检改为核对新归档的 SHA256。不推送。
- **一页总结：** 实施会话在退出前写 `docs/frontend-vnext/frontend-remediation-summary.md`，含 §12 的门禁说明。

## 10. 独立审核

整轮末尾一次，新会话，审核 `B..C`，重点 H3，其余各项一并看。

- **H3：** 每个 hook 的职责与 §7.2 一致；`git diff --color-moved` 下非移动改动逐条有理由；§7.1 的各条规则与 §7.3 的 effect 顺序、重置序列、具名函数与捕获值逐项核对；在 07 上对每个组件挑一两处风险最高的接线做探针（例如撤掉某个重置或调换两个 hook 的调用顺序），看 mock e2e 是否失败；不失败的记为覆盖缺口，写进报告，不阻塞。
- **H4、H1、H2：** 格式化提交可重放；三条规则与规则单测；移动是否整块；t4 筛查（§9）：两个打包文件在 `B..C` 中只有格式化提交的改动。
- **G1：** 推导表、等价性论证与单测；源码中不再有 `pair_id` 子串匹配。
- **O1、O2、R9、T1、T3：** 按 §8.4 的完成标准复核，T1 的检索在审核会话自己的解压结果上重做。
- **截图：** 审核会话在 07 跑一次 C 的 mock 全量，与 B@07 比较。
- **结论：** 可以退出、定向修复或停下交 Owner。报告放交换目录 `reviews/`。

## 11. 与输入的出入，交 Owner 决定

1. **H1 规则对测试文件的范围（建议甲）。** 甲：规则作用于测试文件，A 层测试可以导入 `features/dev`，渲染组件的用例随组件移走（§5）。乙：规则只作用于生产代码。甲多一个测试文件，保证测试也不跨层用 UI。
2. **A 层目录里还有两个 UI 组件（建议本轮不动）。** `features/session/SessionComponents.tsx`（`SessionGate`、`DeviceBar`）与 `features/view-model/table-state.tsx` 中的 `SurfaceChangeBadge`、`TableFailureNotice` 按 kickoff §4.2 属于 C 层，三条导入规则查不出来。移动不改行为，但 `table-state.tsx` 还要把纯函数与组件拆开，超出输入范围。建议记为遗留，下次改到这两个文件时移到 C 层；Owner 希望本轮做的，归入 H1。
3. **H3 分组的调整**（§7.2 末段）：拆开审核事实与撤回；补导航选择与 R15；归档执行并入计划 hook，关闭动作在共用 hook 之外单独成 hook；`WorkbenchPage` 的选中键归面板 hook、提交续接 ID 单独成 hook。另外两条规则比输入细：“`setState` 先后原样”改为按同步段核对（§7.1 第 2 条）；按依赖排定调用顺序后有两处 effect 顺序与 H 不同，已逐条说明为什么安全（§7.3）。属于输入授权的定稿范围，列出供核对。
4. **F7 判为不等价**（§8.3），按输入转入小任务第 6 项，本轮不改。
5. **T1 的完成标准：** “`Bearer `为 0”细化为“`Bearer ` 后接 token 字符为 0，源码模板 `Bearer ${` 单列”，与 FE4b 的核对口径一致。
6. **退出证据加上传包校验**（§9 第 10 步）：输入只列了 mock 全量、`smoke`、`journeys`。格式化改到 `upload-package.ts`，而前端各阶段（含 §20.5）的 04 证据都含这一项；四个包与 §20.5 逐字节相同即证明打包输出未变，t4 不触发。
7. **新增 T3，修法与 handoff 的建议不同。** FE4 合并后验证的 handoff 建议 `mkdir -p` 或清理后复用，并补“同一 `--log-dir` 先后跑 `smoke` 与 `journeys`”的回归。本计划改为拒绝复用、每次运行用单独目录（理由见 §8.4），回归检查相应改为拒绝检查，不需要为此多跑一次完整 `journeys`。

## 12. 交规则会话的门禁说明（整顿结束时，由 Owner 转交）

| 门禁 | 运行 | 失败时 | 豁免 |
| --- | --- | --- | --- |
| 前端格式检查 | `frontend/scripts/run-tests.sh` 在 `npm ci` 之后执行 `npm run format:check`（`prettier --check .`，Prettier 3.9.10，配置 `frontend/.prettierrc.json`） | 逐个列出未格式化的文件，以非零退出，入口失败。修正：在 CT201 的开发 worktree 执行 `npm run format` 后提交 | 只有 `frontend/.prettierignore` 列出的生成类型、测试夹具、OpenAPI 快照与 lockfile；不用行内 `prettier-ignore` |
| 前端分层规则 | 同一入口的 `npm run lint`，规则在 `frontend/eslint.config.js` 的 `no-restricted-imports`，由规则单测证明生效 | ESLint 报 `no-restricted-imports` 并给出层次说明，lint 以非零退出，入口失败 | 无；A 层测试导入 `features/dev` 属于规则范围（§5） |

实际名称与命令以实施后的一页总结为准；这里是设计。

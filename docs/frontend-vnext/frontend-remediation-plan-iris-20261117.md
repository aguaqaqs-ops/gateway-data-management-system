# 前端专项整顿执行计划（iris-20261117 修订候选）

- **状态：** 2026-11-17 完成中期复评后的设计修订，待整体复盘会话按复评 §9 核对；不启动实施。本文是带独立标识的完整修订候选，不覆盖[原计划](frontend-remediation-plan.md)，也不表示其他并行计划已经采用本文。Owner 选定后，实施提示词须明确采用的文档和提交。
- **依据：** `/home/dev/gdds-stage-exchange/whole-project-review/` 下的 `remediation-reassessment-2026-11-16.md`（下称“复评”）§1、§2、§3.5、§6、§8；同目录 `remediation-input-frontend.md`（下称“输入”）、`project-review-2026-11.md` §11、§12、§20、两轮前端计划评审意见；[FE4 kickoff](fe4-kickoff.md) §20；AGENTS 与 [testing-conventions](../backend-vnext/testing-conventions.md) 的 FD7。
- **核对基线：** main `b771631276`，仅静态核对。其 `frontend/` 与复评基线 `6da40cc7e0` 无差异。门禁整改已在 main，但本次未见 `gw08-midterm-exit` tag，也未收到 Owner 转交的 B′ 与验收结果；不把当前 HEAD 冒充 B′。本文的现状数字在真正 B′ 上须复核。
- **冻结基准：** 两端共同的 B′，即附注 tag `gw08-midterm-exit` 所指提交；接口、错误码/状态码、文档字节、digest、golden、界面和截图均相对 B′ 判断。R1/R2 例外仅按已批准范围及跨端交接处理，不扩展到其他行为。
- **会话分工：** 本会话只修订前端计划。前端一个实施 agent 完成编码与调试；整轮独审由 Owner 另开新会话，不套后端角色/模型规则，不自行派生团队。
- **阶段材料：** `/home/dev/gdds-stage-exchange/fe-remediation/`；共享 `log.md` 只追加。新材料使用 `iris-20261117` 标识，例如 `evidence/iris-20261117/`、`handoffs/*-iris-20261117.md`。旧证据和历史过程文档只读保留，不能充作本轮通过证据。入库为计划、必要设计文档及退出时的一页总结；本次不改 kickoff、AGENTS、testing-conventions 或产品代码。

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
| T3 | 真实 backend 入口复用日志目录时失败（FE4 合并后验证交来，即同批的 E1，输入之后才出现） | — | 实施者与门禁，末尾审核一并看 |
| T4、T5、T6 | 只改测试工具：t1 稳定门使 1280 正式截图取景偏移（T4）；凭据检索的 token 格式与执行时点，做成只读脚本（T5）；`check-handoff-hex.py` 核对截断形式（T6）。来源是 FE4 合并后验证审核（交换目录 `fe4b/reviews/fe4-post-merge-eb6530b36e.md` §2.3、§2.4、§3、§6）的 E2、E3、E4，记在 `fe4b/followups/fe4-behavior-small-task.md` 末节；Owner 2026-11-13 决定并入本轮 | — | 实施者与门禁，末尾审核一并看 |

另有一次跨端运行：前端 `journeys` 完整集至少有一次跑在包含后端整顿退出提交的后端上（§9.1，Owner 2026-11-13）。它不是改动项，不阻塞退出。

本轮不做：S2b 的设备路由头；会改行为的 FE4b 遗留（小任务，见 §8.3 与交换目录 `fe4b/followups/fe4-behavior-small-task.md`）；`presentation.ts` 中 `logical_path.includes("/blank/")`（等后端给出显式引用）；Prettier 以外的新依赖与状态管理库；顺手改交互、文案或样式。任何一项必须改行为时停下，交设计会话与 Owner。

## 2. 开始条件与基线

1. **新起点准备：** 门禁整改在 04 验收并合入 main。Owner 指定新起点候选，前端实施会话在该候选取以下基线，不能自行把当日 main 命名为 B′。
2. **后端门禁：** 在新起点执行 `scripts/run-stage-gate.py <full-sha> --purpose stage`，不指定包，由脚本判断实跑/沿用。快进合入且整改自身的 04 六包验收绑定到同一个提交时可直接引用，不重复跑。本前端计划只核收其结果，不另起一套后端门禁。
3. **前端 mock：** 前端实施会话在 clean、已提交 worktree 通过 `frontend/scripts/run-tests.sh` 跑 mock 全量并出 1280/1920 截图，记录单测文件/用例、e2e、PNG 的实际数量和用例清单。07 上的 B′@07 是逐步调试和独审对照；04 退出对照也须有同一 B′ 的 mock 截图（可在第 10 步前补取 B′@04）。复评所称“一次前端全量”可由这两次中已合格的一次满足，不另开第三次启动验收。04 与 07 的同节点对照保留原计划要求。
4. **新增真实对照：** 在同一候选的 04 clean detached worktree 经 `run-evidence-wrapper.sh` 调 `run-real-backend-e2e.sh --suite journeys --subphase fe4b --session <唯一会话名> --log-dir <独立目录>`，完整集、不筛用例，方法与 §9.1 一致。记录每个失败用例、错误码/状态码、原始退出码与日志；失败不要求修完才开始整顿，也不能写为通过。若运行根本未进入 suite，记“未完成对照”，按适用规则修正后重开一次，不把它当完成了完整集。
5. **确认 B′：** 门禁或 mock 全量失败属于中期遗留，先修复并在新头完成受影响核验；以修复后的同一头重新取上述前端基线与 journeys 对照，不能混用旧提交结果。核收后由负责新起点的会话打附注 tag `gw08-midterm-exit`，Owner 转交完整 SHA、tag 与结果索引，两端共用。前端不越权代替后端确认门禁。
6. **正式实施前提：** 本修订经复评 §9 的一致性核对、Owner 选定版本，且 B′/tag 和上述结果已核收。设计修订、只读源码重核不受缺少 B′ 阻塞；本次不跑任何基线。

**基线记录规则。** 原 H=`eb6530b36e`、暂停点 `ef69cb41fb`、旧 B@07、旧 481/118/252 及修复后的 505/118 等计数仅作历史。中期 610 单测、153 e2e 也仅是复评提供的参考，不能写成 B′ 实测。新增测试单列，既有业务断言不删不放宽；T1/T3–T6 等已授权工具修改与临时失败探针按各项标准处理。基线 journeys 在 T1/T5 实施前按 kickoff §6 的既有手工方法逐成员检索 zip，记录检索能力与结果；旧入口泄漏如实记录，原件受控保留，转交材料不含凭据，不把旧 T1 成果提前混入 B′。

**视觉基准。** B′ 截图结合 [UI 优化方向 §9、§9.1](ui-optimization-direction.md#9-现行界面视觉确认owner2026-11-16) 的已接受布局：工作台三列、手动折叠详情、比较页与二次装置布局、满额托盘、超时原请求重试、任务行和蓝框焦点。它们与旧草图的差异不再报偏差。该文件仍列为未确认的低风险色条差异继续保留，不借整顿改色。整顿截图出现不能归为噪声的内容变化即停；不更新截图来掩盖变化。

**当前静态数量（非 B′ 验收）：** `ComparisonPage.tsx` 1572 行，文件内 `useState`/`useEffect` 字符出现 41/20 次（含导入及子组件）；真正页面组件内调用 34/13 次。`WorkbenchPage.tsx` 717 行，文件内 `useState` 出现 32 次，页面调用 31 次、effect 6 次。`ArchiveMainlineDialog.tsx` 590 行，组件内 state 30、effect 1。不要把全文出现数当页面 state 数。`pair_id` 子串判断仍四处；OpenAPI 41 条路径，其中内部 6 条、公开 35 条。B′ 到位核差异并更新阶段记录，不沿用旧组件分组假设。

### 2.1 历史核收与当前实施模式

2026-11-13 的 FE4 核收与 `74a0f326bf` 开工记录保留在原计划 §2.1 和阶段日志中；它们不能满足本轮的新起点要求。前端仍只用一个实施 agent，完成编码、必要调试、交接、审核修复及已授权取证；整轮独审由 Owner 另行安排。不重新请求已授权的普通可逆实现和调试。设计/验收范围、来源冲突和不可逆操作才交 Owner；缺少跨端输入只暂停依赖步骤。

## 3. 分支、节点与缓存

- **分支：** 从 B′ 开新的短期实施分支，例如 `fe-remediation-iris-20261117`，使用独立 worktree。`fe-vnext` 固定 `583a72c5da` 及 `/home/dev/gdds-fe` 只读保留到整顿退出，不快进、不继续追加、不整体合并。审核范围 B′..新候选 C。本次计划提交直接落 main，仅包含本候选文档。
- **提交：** 每项单独提交，H3 每个组件一提交；格式化提交只含新树上的格式化输出。取用、手工重放、重做各项在 handoff 记来源 SHA、新提交及实际取用范围；不用旧提交的测试结果替代新树验证。
- **节点：** 07 为日常 mock 对照（`GATEWAY_FE_TEST_WORKERS=2`），05 为 T1/T3/T4 调试及 t1，04 为启动 journeys 对照和退出证据。这是本轮对照安排，不是节点池固定职责。可在合格空闲池内节点调度，但截图保留同节点基线，计时统计组保持同节点同配置。现场核空闲后原子占用；真实入口自行占用，外层不重复取；其他运行按 FD7 占用。开发主机不运行 lint、类型检查、构建、测试或截图取证。
- **源码生成：** `prettier --write` 与 API 类型生成是在 CT201 改写源码的开发操作；格式检查、生成类型一致性验证只在节点入口执行。
- **缓存复用：** 当前 main 的依赖和锁自暂停点未变。取用 `c5d5482193` 后，先将 `package-lock.json` 与 `fe-vnext` 对应锁逐字节/完整摘要核对；一致时可用 04、05、07 现有 `fe-remediation/npm-cache` 及 `332deeb8…` 归档。完整摘要、来源提交、来源节点、预填充时间从旧原件回源，并在实际节点重新核存在性及归档身份；本文短摘要只用于识别，不作验收值。未现场核对，不声称可用。工具之后所有装依赖入口显式设置 `GATEWAY_FRONTEND_NPM_CACHE`、`GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE`、`GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT`，如实记录缓存原来源而非伪称重新生成。
- **缓存补齐：** 锁不一致、归档不符或缺失先停受影响运行，定位原因；不能默改依赖。确需重建时在 CT201 按已授权锁导出 `frontend/`、取完整 npm 缓存并经 LAN 预填充目标节点，保持 canonical registry identity；节点离线 `npm ci --offline`，不经转发代理。`run-tests.sh`、真实入口、打包测量入口均需同一锁的缓存；包校验入口不装依赖。
- **基线缓存：** B′ 没有 H4 工具时沿用 FE4b 缓存归档 `0d861824…`。复评已确认 04/07 默认恢复，05 没有默认路径；05 必须显式指定经核实的旧缓存（旧计划为 `fe0/npm-cache`）。不假设跨节点缓存共享，不在退出前替换默认缓存。

### 3.1 旧 21 个提交的处理

| 来源 | 处理 |
| --- | --- |
| `c5d5482193` | 取用 Prettier 工具与配置；先核 B′ 上六个文件是否又变，避免覆盖新增入口接线 |
| `34aa5d15f7` | 不搬全量格式化；工具落到 B′ 后重跑格式化并作独立提交 |
| `65bcaefa21` | 取用三层规则和规则测试；页面导入修正重做，移动连接状态组件时保留中期改动 |
| `eb1a3f16fe` | `ArchiveMainlineDialog` 中期未改，可在新格式化之后取用；先核文件与依赖接口，按本轮重验 |
| `f979b07dd0`、`7f5461c704`、`7971c7c4fe` | 两页拆文件/抽 hook 在 B′ 新结构上重做，只参考旧提交；见 §6、§7 |
| `47a7003f9b`、`d9de8824e9` | O1、G1 重做；不恢复已经被中期删除的 O2，不覆盖现行 scope、空点、提交结果行为 |
| `bef2a49160`、`017dfc90d1` | 稳定门、真实入口和证据检查的思路取用，改动逐段手工重放，T1/T3/T5 重新扫描全部生成点与固定输出 |
| `4c29b0832a`、`35592ccb75` | 随 H4/H2 保持公式标题文本节点和空白；禁用行内 `prettier-ignore`，不原样覆写当前 JSX |
| `a4c575a7db` | 随 O1 保持校验、解码、组装与 setter 的同步段顺序，分阶段抽函数 |
| `cc90d2e5bf`、`6c2608c397`、`6ffce18697` | 随 H3 落实具名撤回动作、初值与依赖数组原样、无遗留未用导入；对照 B′，不恢复旧初值 |
| `50f3f1a89e` | 随 T5 验证每种凭据样本各自被检出，不能只看合计非零 |
| `f41608b3d4`、`583a72c5da` | 随 T1 取用独立脱敏脚本、保留 suite 原结果、正确 argv 接线与失败处理 |
| `687e62636b` | 随 T3 拒绝带 `artifacts/`、`evidence/` 的旧日志目录；完整清单仍以当前入口为准 |

每项取用前核依赖，不整批 cherry-pick；冲突时按新树手工重放，不以旧文件整份覆盖解决。

## 4. H4：Prettier

- **版本：** `prettier` 沿用已批准的精确版本 `3.9.10`，取用工具提交，不重新选版本。该工具提交的 lockfile 只增加一个包。lockfile 的 `resolved` 必须是 `https://registry.npmjs.org/prettier/-/prettier-3.9.10.tgz`：CT201 的 npm 默认取局域网 registry，装完后把新条目的主机改回官方地址，保留路径与 integrity（FE0 B1 的做法），并与 `npm view prettier@3.9.10 dist.integrity` 核对。
- **配置：** `frontend/.prettierrc.json` 只写 `printWidth: 100`，其余用默认值（双引号、分号、`trailingComma: "all"`、LF），与现有代码习惯一致，行宽与后端 ruff 的 `line-length = 100` 相同。定了不再调。
- **忽略：** `frontend/.prettierignore` 列出 `src/features/api/generated/`、`src/test/fixtures/`、`e2e-real/fixtures/`、`openapi.json`、`package-lock.json`，以及 `dist/`、`coverage/`、`playwright-report/`、`test-results/`。生成的类型由 `generated-types.test.ts` 逐字节核对，快照与 lockfile 由各自的工具生成，夹具有 SHA256 核对。不使用行内 `prettier-ignore`。
- **脚本与入口：** `package.json` 加 `format`（`prettier --write .`）与 `format:check`（`prettier --check .`）。`run-tests.sh` 在 `npm ci --offline` 之后、`typecheck` 之前执行 `npm run format:check`：有未格式化文件时逐个列出并以非零退出，入口随之失败。README 补一段用法。
- **两个提交：** ① 工具提交：依赖、lockfile、两个配置文件、脚本、入口与 README；② 格式化提交：只含在 ① 的树上于 `frontend/` 执行 `prettier --write .` 的输出。门禁：在 ① 上重放格式化得到的树与 ② 相同；② 之后 `format:check` 通过。
- **历史规模**（暂停前在 H 的副本上试算，不是 B′ 预期值；B′ 实际改动数在实施时重数）：格式化改动 123 个文件，`frontend/` 总行数约从 2.86 万增到 4.69 万；格式化后超过 160 字符的行剩 16 行（`src` 中 9 行），都是 Prettier 不拆的长字符串，没有超过 400 字符的行。CSS 中十六进制颜色转小写、`font-family` 引号与换行变化，渲染不变，由截图比较确认。

## 5. H1：分层门禁

**规则。** 在 `eslint.config.js` 用 ESLint 自带的 `no-restricted-imports` 的 `patterns`（`regex`），按目录写三条。消息写明层次与 kickoff §4.2。

| 文件 | 不得导入 |
| --- | --- |
| `src/design-system/**` | 任一路径段为 `features` 或 `pages` |
| `src/features/{api,bundle,session,view-model}/**` | `design-system`、`pages`、`workbench`、`dev` 路径段 |
| 同上目录中的 `*.test.{ts,tsx}` | `design-system`、`pages`、`workbench`（允许 `dev`，见下） |
| `src/features/workbench/**` | `pages` |

- **中期新增文件：** `HistoryCompareTasks.tsx`、`history-compare-errors.ts` 属 workbench（C）；`manual08.tsx` 是 dev 装配入口；`scope-copy.ts` 属 view-model（A）。按现行三层规则重核其全部导入及中期改动，不能仅核旧两个页面。组件移动带上中期 `ConnectionStatusIndicator` 的改动。
- **测试文件的范围（与输入的出入，§11.1 第 1 项，以下数量是 H 的历史数，B′ 重数）：** 输入说“现有违规只有一处”，按生产代码计是对的；连测试文件算，还有 6 处：A 层的 5 个测试导入 `features/dev` 的模拟数据与模拟接口（`client`、`scope-session`、`polling`、`journeys`、`workspace` 的测试），`features/api/connection-status.test.ts` 渲染了 `ConnectionStatusIndicator`。设计：规则同样作用于测试文件，只允许 A 层测试导入 `features/dev`（那是共享的测试数据，不是 UI）；把那个渲染组件的用例随组件移走。这是规则范围的定义，不是逐处豁免。
- **移动：** `src/design-system/ConnectionStatusIndicator.tsx` → `src/features/workbench/ConnectionStatusIndicator.tsx`（`git mv`，组件内导入改为 `../api/connection-status`），两个页面的导入随之修改；`connection-status.test.ts` 中渲染组件的用例原样移到 `src/features/workbench/ConnectionStatusIndicator.test.ts`，另两个用例留下。用例数不变，单测文件数加 1。
- **证明规则生效：** 加一个参数化单测（`// @vitest-environment node`），用 ESLint 的 Node API `lintText` 对每条规则各给一个违规样例（必须报 `no-restricted-imports`）和一个合法样例（不报）。门禁配置写错（例如 glob 不匹配）时它会失败，否则规则可能一直“静默通过”。
- **文档：** kickoff §4.2 已写入目录与层的对应关系（原计划提交已写入，本次不重复修改）。
- **规则单测是与输入的出入**（§11.2 第 6 项）：输入没有这一项，它不加依赖。
- **不处理：** A 层内部方向不整齐的导入（`bundle` → `view-model`、`api` → `bundle`）。另见 §11.1 第 2 项：两个放在 A 层目录里的 UI 组件，Owner 决定本轮不动、记为遗留。

## 6. H2：在新树机械拆 `ComparisonPage.tsx`

新目录 `src/pages/comparison/`（C 层）；入口文件、`App.tsx` 不改位置。只移动、导出、导入，不改名、不合并逻辑。旧 `f979b07dd0` 只供参考。下表按当前 main 定稿，B′ 的增量须逐项补进交接。

| 文件 | 移入内容 |
| --- | --- |
| `view-copy.ts` | `reviewStatusLabel`、`viewLabel`、`viewTitle`、`riskLevelText`、`noticeReasonText`、`noticeLines`、`definitionChangeText`、`localRiskText`、`scopeChangeText`、`tabTitle`、`itemBadgeKind`、`itemStatusTooltip`、`rowLabel`、`formatSchemaSummary` |
| `view-helpers.ts` | `bundleErrorState`、`serverResultReleaseCode`、`bundlePathForState`、`viewRiskLevel`、`pairDiagnosticDetails`、`riskTokens`、`orderedMovedCount`、`hasDeletedAppearance`、`recordValues`、`matchesGroup`、`matchesItem`；`PairSummary`、`PairPresentation`、`NavItem`、`NavTab` |
| `sidebar-settings.ts` | `Settings`、`SETTINGS_KEY`、`DEFAULT_SETTINGS`、`SIDEBAR_MIN/MAX`、`clampSidebar`、`readSettings` |
| `column-widths.ts` | `ColumnWidths`、`COLUMN_WIDTHS_KEY`、`readColumnWidths`、`TextMeasure`、`createTextMeasure`、`sampleRows`、`fitWidth`、`COLUMN_PADDING/MIN/AUTO_MAX/FIT_MAX`、`SizedGridColumn` |
| `ScopeChangeBadge.tsx` | `ChangeMark`、`ScopeChangeBadge`，保留中性标记与各 scope 的现行判断 |
| `ScrollStrip.tsx`、`InfoPopover.tsx` | 同名子组件，内部 hook 整块搬走，不扩大 H3 到这些组件 |
| `PublicNoticesPanel.tsx` | 同名组件，保留公共提示与装置定义变化 |
| `GridTable.tsx` | `GridTable`、`HOVER_FIELD_LIMIT`；包含现有 hover/ref、绘制及 `useLayoutEffect`，不另改表格实现 |
| `ChangeNavigator.tsx`、`NavigationDiagnosticNote.tsx` | 同名组件，带未归属行入口 |
| `DebugInfoBar.tsx` | `DebugInfoBar`、`CopyDebugValue`、`RiskReasonDetail` |
| `ReplacementBrowser.tsx` | `ReplacementBrowser`、`ReplacementSide` |
| `FormulaCard.tsx` | `FormulaCard`、`FormulaAlignedPair`、`FormulaLineList`，精确保留可见文本节点和空白 |
| `PreviewHeaderActions.tsx` | 同名组件 |

旧表中的 `columnWidth`、`tabCount`、`tabChangeKind`、`tabRiskLevel` 已不在当前文件，不创建空壳或恢复旧路径。完成后入口只剩 `ComparisonPage` 与导入；以 `git diff -M --color-moved=dimmed-zebra` 对照移动，非移动改动限导入/导出。样式和业务文案不调整。

## 7. H3：三个组件的 state 抽成 hook

### 7.1 规则

1. **完成标准：** 三个组件体不再调用 `useState`、`useReducer`、`useEffect`、`useLayoutEffect`。组件体只剩：按 §7.2 的顺序调用 hook；三个共享 hook（第 3 条）；组合几个 hook 的事件处理（如 `WorkbenchPage` 的 `runAction`）与摆放所需的派生，按 B′ 上的写法保留 `useMemo`/`useCallback`；挂 DOM ref。每个 hook 的职责能用一句话说清（§7.2）。
2. **只移动，不改语义：**
   - state 的初值随 state 原样进入 hook，包括读 URL、存储与会话的惰性初值。依赖另一个 state 初值的成对 state 放在同一个 hook（`compareStartError` 与 `compareIntent`，`uploadLocked`、`resumePending` 与 `resumePreviewOperation`）。这些初值只读不写，挂载时先后调整不改变取值。
   - effect、`useCallback`、`useMemo` 的依赖数组原样，现有数组中有意省略的依赖不“补全”；不新增也不去掉 `useCallback`/`useMemo`，因为这会改变传给子组件的函数身份。
   - 不合并、不删除 state；看到冗余（如 `ComparisonPage` 中由 runtime 订阅同步的 `search`、`onlyInteresting`、`debug` 三个镜像 state）记进 handoff，留给以后。
   - 回调中语句的先后按“同步段”核对（相邻两个 `await` 之间，或没有 `await` 的整段）。同步段内**全部语句保持原顺序**，包括不同 state 的 setter、ref 读写、校验/解码、存储、URL、`runtime.execute`、父回调与函数调用；不以 React 批处理为由换序。抽取边界切在原连续语句间；不能用一个大组装函数把原本后置的异常提前到 setter 前。§7.3 与 O1 按同一标准核对。
3. **数据流不变：**
   - `useBoundGatewayApi`（内部是 `useState`）、`useGatewaySessionState`、`useUploadModeState`（内部有自己的 state 与 effect）由组件各调用一次，结果作为参数传给需要的 hook。hook 内不得再调用它们，否则会出现第二份状态或第二个绑定实例。
   - 自定义 hook 之间不互相调用。一个 hook 用到另一个 hook 的值或函数时，由组件作为参数传入，所以被用到的 hook 必须先调用；§7.2 的顺序由此而来。
   - 一个 hook 要改另一个 hook 拥有的 state 或 ref 时，由拥有者提供具名函数，函数体是原处连续语句的原样搬入（例如归档对话框三处冲突路径共有的“写待定提示、显示冲突提示、刷新”），或者直接传 setter。不新增 context 或全局 store。
4. **effect 顺序：** 以 B′ 当前 effect 序列为准，§7.3 给出本次核对序列与允许分析的两处重排。逐项记录新旧顺序、同步读写及 cleanup；不能照搬 H 上的安全结论。出现共同读写或无法证明等价时调整边界以保序，仍有问题才停相关拆分交设计会话。
5. **ref：** 非 DOM 的 ref（`withdrawKey`、`loadingKey`、`loadedRequest`、`resumePending`、`previousDigest`、`pendingNotice`、`progress`）随所属 state 进入同一个 hook。JSX 中直接写这些 ref 的内联处理（`ComparisonPage` 的撤回按钮，`WorkbenchPage` 中 `OperationStatusPanel` 与 `UploadStepCard` 的回调）改为拥有者 hook 的具名函数，函数体原样。被 hook 使用的 DOM ref（`selectedNavRef`、`workspaceRef`、`pageRef`、`headerRef`）由该 hook 创建并返回，组件负责挂载；只在 JSX 中使用的（`searchInputRef`、`reviewNoticeRef`、`searchRef`）留在组件体。
6. **放置：** `ComparisonPage` 的 hook 放 `src/pages/comparison/`，`WorkbenchPage` 的放 `src/pages/workbench/`，`ArchiveMainlineDialog` 的放 `src/features/workbench/archive-mainline/`；文件名 `use-*.ts`。这些目录都受 H1 规则约束。
7. **测试：** 不改既有测试；不为 hook 补单测（覆盖靠既有 mock e2e 与截图）；mock 全量数量不变，截图与 B′@07 相同或只有噪声。

### 7.2 分组与调用顺序

下表按新页面数据依赖排列；`gatewayApi`/会话由组件各调用一次后传入，hook 不互相调用。每项覆盖当前 state，而不是旧提交中的名字。

**`ComparisonPage`**

| # | hook | 拥有的状态、动作及输入 |
| --- | --- | --- |
| — | `useBoundGatewayApi`、`useGatewaySessionState` | 组件调用，保持现有实例 |
| 1 | `useBrowseRuntime` | runtime、`browse/search/onlyInteresting/debug`，订阅与 popstate；不删镜像 state |
| — | `useUploadModeState` | 组件调用，enabled 仍依 `browse.mode` |
| 2 | `usePreviewSubmitResume` | `submitOpen/resumeOperationId`、刷新与两个续接回调；输入上传模式、runtime、browse |
| 3 | `usePreviewWithdraw` | `withdrawOpen/Busy/Understood/Error`、`withdrawKey`、具名打开和确认；输入上传模式与刷新 |
| 4 | `useCompareHeaderHeight` | `pageRef/headerRef`、现有 R15 effect；输入会话状态 |
| 5 | `useViewSettings` | `settings/columnWidths`、两项 localStorage 持久化、`workspaceRef`、侧栏拖动/自适应；列宽的 `storedWidths` memo、`changeColumnWidth` callback 与 reset 在组件拿到当前表后保持原写法，setter 由此 hook 输出 |
| 6 | `useComparisonResult` | `fetchBundle/bundle/pairs/loading/error/historyCompareStatus/historyCompareWaited/reviewFacts/reviewResultChecking/reviewResultErrorCode`、`loadingKey/loadedRequest`；原 `readReviewContext/loadBundle/reloadReviewContext` 放一起。输入 runtime、browse、会话；输出表加载所需 `setError`。不把复核与 bundle 拆成相互依赖的两个 hook |
| 7 | `useComparisonNavigation` | `showEmptyTabs`、groups/当前 pair/整表与设备选择、`selectedNavRef`、选择同步/节点滚动、选择与 `openWholeTable/openItem` 动作；输入 pairs、browse、runtime。包含表/页签派生，不恢复旧 overflow state |
| 8 | `useTableExpansion` | `expandedRuns` 与切换节点/页签/表时清空的 effect；输入选择。该 effect 留在未归属回退之前，state/setter 供表加载和展开按钮使用 |
| 9 | `useUnassignedBrowse` | filterTabs、未归属 predicates、可浏览判断、activeUnassigned、URL 无法兑现时回退 effect、`browseUnassigned`；输入 presentation、browse、runtime、`openWholeTable`，不新增 state |
| 10 | `useTableData` | `rows/beforeRows/currentRows/scopedRows/annotations/tableLoading/visibleRows`、`loadTable` effect、定位/风险计数与原因及未归属视图；输入 bundle、选择、browse、settings、expandedRuns、filterTabs/activeUnassigned、setError。保留空点 provenance、降级、缺侧和 locator 校验 |
| 11 | `useTabStripScroll` | 原 `.overflow-tabs button.is-active` 滚动 effect，输入 selectedNodeKey/tabKey；刻意放在表加载之后，不并进第 7 项而提前 effect |
| 12 | `useFormulaPanel` | `formulaOpen/formulas/formulaFocus`、`openFormula`；输入 bundle、presentation、browse.mode，保留公式与 locator/缺侧处理 |

只用于 JSX 的 `searchInputRef/reviewNoticeRef` 留组件。`stripTabs` 等无副作用派生可留组件，既有 memo/callback 不删不加。所有 34 项页面 state 均有 owner，移动后的子组件内部 state 不计入 H3 完成条件。

**`WorkbenchPage`**

| # | hook | 拥有的状态、动作及输入 |
| --- | --- | --- |
| — | 共享三个 hook | API、会话、上传模式由组件按原顺序调用 |
| 1 | `useSubmitResume` | `resumeSubmitOperationId`、attempt 带出 ID 的 effect；输入上传模式 |
| 2 | `useWorkbenchData` | `history/loadError/loading`、load/reloadHistory/reloadHead、会话监听；输入上传模式与续接 setter |
| 3 | `useWorkbenchPanels` | `selectedKey/detailExpanded/notice/archiveSubmissionId`；现行宽度惰性初值保留 |
| 4 | `useHistoryCompareRun` | `compareState/compareError/compareNeedsRerun/compareConnectionLost/refreshCompare/compareElapsed/bundleStatus/downloadRevision/historyBundle/pairSummaries/pairSummaryError`、`historyDrawerCollapsed/urlRevision`；URL 派生 operationId/kind/replayed、轮询/下载/摘要、关闭抽屉。关闭时先删 URL 参数、replaceState，再重置折叠和 revision，顺序原样 |
| 5 | `useCompareTray` | `compareRefs/compareIntent/compareStartError/comparePending`，选择、发送、同 key 重试/新 key 重跑、comparisonLocked；输入选中键与第 4 项的运行状态 |
| 6 | `useHistoryTree` | `filter/currentBaselineOnly/sort/collapsedNodes`，rows/可见行、选择同步与 URL effect；输入 workspace、history、compareRefs、selectedKey/setSelectedKey。当前已经没有树列宽 state，不恢复旧实现 |
| 7 | `useUploadGate` | `resumePreviewOperation/uploadLocked/resumePending`、resumePreviewFromOperation、原 JSX 的失败/上传状态回调；输入上传模式、compareRefs、selectedKey。当前无 pendingAction/uploadReady/uploadRef，不从旧 hook 带回 |

组件保留跨组组合：`resumeSubmitFromOperation/retryResumeNotice/runAction/openPreview/openReview/openSubmissionResult/openCompareOperation/jumpToCompare/resumeActivePreview`、activePreview 提示、actions 与任务列表接线。`HistoryCompareTasks` 自带的列表/轮询 state 留在原组件，不复制进页面 hook。31 项页面 state 覆盖全部，具名回调与捕获值原样。

**`ArchiveMainlineDialog`**

| # | hook | 管什么 | 参数 |
| --- | --- | --- | --- |
| 1 | `useArchivePlan` | 一次归档的计划与执行：候选、计划、选中摘要、加载中与错误、集合变化与冲突提示、确认勾选、进行中、失败、结果、进度；`load`、`refresh`、打开时的重置、`start`；供动作使用的 `reportConflict`、`clearPlanAndLoad` | `open`、`submissionId` |
| 2–4 | `useReasonedAction` ×3 | 一个需要理由的动作：目标、理由、幂等键、进行中、错误，`open(target)`；接受、撤销、关闭各一个实例 | — |
| 5 | `useAnomalyResolution` | 接受与撤销的提交（原 `submitResolution`） | 两个动作实例、计划、`reportConflict`、`refresh` |
| 6 | `useCloseSubmission` | 关闭：已知晓、打开时的快照、结果、送达失败后的重试体，`openClose`、`submitClose`、`retryClose` | 关闭动作实例、计划、`reportConflict`、`clearPlanAndLoad`、`refresh` |


归档对话框文件中期未变，沿用上述分组并按 §3.1 取用。复评后关键差异：比较页审核事实与结果复核/缓存共同属于“提交结果读取”，放一个 hook 以免循环；展开重置与 strip 滚动分别安置以保 effect 顺序；工作台新抽屉状态随历史比较运行，已删除的旧上传与列宽状态不恢复。

### 7.3 审核要点（交 §10 独审）

- **当前 effect 序列：** 比较页：共享上传 hook → 续接 ID → Preview 刷新 → R15 → runtime 订阅 → settings 持久化 → columnWidths 持久化 → loadBundle → 选择同步 → 节点滚动 → expandedRuns 清空 → unassigned 回退 → loadTable → strip 滚动。工作台：共享上传 hook → 续接 ID → load/会话监听 → 选中键 → URL 同步 → 历史比较轮询 → 比较摘要。归档只有打开重置/加载一项。B′ 若变须重列。
- **两处重排须重新证明：** runtime 订阅提到上传 hook 前；工作台轮询/摘要提到选中键与 URL 同步前。当前 runtime subscribe 仅登记，重排跨过的同步段没有 runtime 命令；轮询/摘要同步段只碰本组状态、不写选中键或 URL。实施须追到 B′ 的被调函数、cleanup、异步入口复核；不能将异步段也视为可随意重排。其余 effect 用 §7.2 边界保序。
- **同步段原样：** 所有 setter、ref、存储、校验、await 和调用按 B′ 顺序。尤其 `loadTable` 的 validate → metadata I/O → decode → setter → build → setter，不合成会提前抛错的大函数；`visibleRows` 初值、原依赖数组逐项对照。
- **审核结果语义：** facts 与 submission result 并发读取、服务端 unavailable/integrity 错误才提供放行依据、加载/复核中撤销结果可用性、缓存与 default_pair、readonly 模式均不变；本地下载错误不能误变成服务端授权依据。
- **其他关键接线：** 未归属 URL 回退、空点 provenance、展开重置、列宽持久化、任务抽屉 URL 删除与 revision、history 同请求/新请求重试、进行中 Preview 接回；归档原三种重置序列及 conflict/pendingNotice 顺序不变。
- **具名函数与捕获：** 跨 hook 每个动作与原连续语句对照；原 `useCallback([])` 捕获首次 API、Preview 续接捕获 compareRefs/selectedKey 等维持原样；公式标题不得靠 ignore 保持空白，按可见文本节点核对。

## 8. G1、G2 与 FE4b 遗留

### 8.1 G1：比较对的标签与标题

- **类型与落点：** `posix-tar.ts` 的 manifest inputs 从 `unknown[]` 改为 `{ input_index: number; role: string; display_name: string; display_metadata: Record<string, string>; snapshot_digest: string | null }[]`；pair 取 `before_input_index/current_input_index`，在新 `useComparisonResult` 装配 `PairPresentation` 时按 index 解析两侧 role，缺失为 null。不假设数组下标等于 input_index。沿用当前文档读取/校验边界，不借整顿改变合法 bundle 集合。
- **Preview 推导表：**

  | before role | current role | 标签 | 标题 |
  | --- | --- | --- | --- |
  | baseline | initial | 原始组态视图 | 已归档数据 → 原始组态备份 |
  | initial | modified | 本次组态视图 | 原始组态备份 → 本次归档组态 |
  | baseline | modified | 当前基线 → 本次归档组态 | 当前基线 → 本次归档组态 |
  | 其他或 null | — | 比较视图 N | 比较对 `<pair_id>` |

- **中期 REVIEW 分支必须保留：** 当前 `viewLabel/viewTitle` 在 REVIEW 且 total=1 时分别返回“基线 → 修改”与“提交绑定比较：基线 → 修改”。这属于 B′ 行为，不能照旧 `d9de8824e9` 删除全部 total 参数。HISTORY 继续按模式/下标，不用 role（值为节点 ref）。REVIEW 多对沿用提交绑定 Preview 的现有展示：与 Preview 相同的角色对映射，保留单对专用分支；若 B′ 的合法 REVIEW bundle 与这张表不等价，停 G1 交设计会话，不能改文案来适配。
- **等价性与验证：** Preview READY 完整上传为 baseline→initial 与 initial→modified，只改后上传为 baseline→modified；到 B′ 在 producer、Contract 与实际所有 Preview/REVIEW 夹具重新核实，不复用暂停前夹具清单。合法数据标签/标题不变，未知角色仅按原批准的通用回退处理。参数表覆盖三种角色、缺失/未知、HISTORY、REVIEW 单对与多对；用与角色无关的 pair_id 证明去掉字符串猜测。既有 mock、journeys、t1 的页签/面包屑断言原样。最终源码不存在 pair_id 子串推断。

### 8.2 G2：OpenAPI 快照

等 Owner 转交后端“`/internal/v1` 移出公开 schema”的提交 SHA，且该提交已在 main。转交的应是后端本轮公开 schema 不再变化的提交，不一定就是 G2 那一个提交，以 Owner 转交的为准（Owner 2026-11-13 已确认后端 G2 可以修改公开 OpenAPI：移出的只有 `/internal/v1` 路径与只被它们引用的 schema 组件）。把含 Sb 的 main 合入新实施分支后（先核通道规则夹具变化，按 §9.2 重取基线），按 S2b `116e831701`、`223e073cb4` 的做法从运行中的 backend 取 `/openapi.json`、保持 canonical 排序写回 `frontend/openapi.json`，用锁定的 `openapi-typescript` 重新生成类型，两者同一个提交，说明写明来源 main 提交与 `vnext/` 树。验证：真实 backend smoke 的 `openapi_compare=match`、快照中没有 `/internal/` 路径、mock 全量与类型检查通过。不得默认接受新增统计端点或其他未交接差异。若 Sb 含 P1 公开 DTO 字段删除，须同时收到 Owner 逐字段批准与后端消费者清单，逐项核差异；影响前端消费者或需要改变行为即停该项交 Owner。届时整轮已退出的，作为退出后的单独提交按同样验证进入 main；后端迟迟未完成的，记为遗留，不阻塞退出。

### 8.3 F7 汇总口径：保留历史决定，不恢复旧问题

原计划在 H 上判“不等价、转后续功能小任务”，本轮不借机改业务语义。中期 `34d16d6bd9` 已引入 navigation scope 投影、`tabScope`、公共提示及装置定义变化，旧 `tabChangeKind/tabRiskLevel` 和 O2 的提升逻辑已不存在。旧三条分析保留在原计划 §8.3 作为历史，不能当作 B′ 尚未修复的缺陷，也不在本轮重跑一次 F7 业务改造。冻结 B′ 的现行 scope 与筛选；对新的业务疑问记录源码依据交 Owner，不静默扩大整顿范围。

### 8.4 其余遗留

| # | 项 | 做法 | 完成标准 |
| --- | --- | --- | --- |
| O1 | `loadTable` 的接线没有用例保护 | H3 之后，在 `useTableData` 中按现行校验、metadata 解码、行组装三个连续阶段抽纯函数到 `features/view-model`（I/O 与 setter 留在原位置），覆盖两侧编码、exactTable、缺侧、未归属与 currentCanonicalBlanks 的现有接线。不得把原校验或 build 异常提前/推后跨过 setter；参考旧修复 `a4c575a7db`，用 B′ 夹具加单测 | 复审探针 R10d（两侧编码换成空 Map）与 R11f（`exactTable` 写死 `false`）各自使至少一个新用例失败；探针在调试节点的临时提交上做，不入候选 |
| O2 | `table_scope` 提升的死代码 | 中期 `34d16d6bd9` 已删除该循环、`DerivedTable.tableScope`/初值及页面回退；本轮在 B′ 重核并记已由中期完成，不重复删代码。新 `NavigationTableNotice.table_scope` 是有消费者的有效事实，不能一并删除 | 单测与截图不变 |
| O4 | 过时注释 | 中期 `3e05f0aae9` 已删除过时的 status cluster wraps 注释；现存 N5 是 disabled-reason 换行说明，与 CSS 一致。B′ 核收，无需重做 | 源码/历史核对，零额外产品改动 |
| O5 | handoff 的尝试记录 | 写进 kickoff §6（原计划提交已写入，本次不重复修改） | 已写 |
| R9 | W6 忙态截图不稳定 | 先查根因；查不明时把 `upload-mode.spec.ts` 的稳定门移到 `settleAfterResize` 之后。与 T4 是同一类问题（稳定门用元素截图），判定方式与 T4 一致：不改变滚动位置的区域截图连续两次逐字节相同；仍不稳定时再加状态特征（例如顶栏各元素的位置在连续 3 帧内不变），handoff 写明。两处各自实现或共用一个 helper 由实施会话定。只改测试工具 | 07 连续两次 mock 全量、04 对 07 各一次 `compare-screenshots.py --stable`，都只有相同与噪声 |
| T1 | 真实旅程 trace 带 `authorization` | 见下 | 见下 |
| T2 | 凭据检索必须解压 zip | 规则写进 kickoff §6（原计划提交已写入，本次不重复修改）；T1 的入口检索按此实现；`run-evidence-wrapper.sh` 没有自带检索，不改。token 格式与检索时点由 T5 补 | 规则已写；§20.5 起已按此执行 |
| T3 | 真实 backend 入口复用日志目录时失败（FE4 合并后验证 handoff §4：`smoke` 与 `journeys` 共用 `--log-dir`，`mkdir groups-control` 报 `File exists`，在被测对象运行前退出；即审核报告 §6 的 E1） | 入口在取得占用之前检查 `--log-dir` 中是否已有上一次运行的固定名输出，有则逐个列出并以 2 退出，提示每次运行用单独的空目录。清单至少包括：`artifacts/`、`evidence/`、`groups-control/`、`processing-groups.log`、`openapi-runtime.json`、`openapi-runtime.normalized.json`、`openapi-snapshot.normalized.json`、`openapi.diff`、`results.json`、`suite-summary.txt`、`input-scope-results.json`（入口按“文件存在才读”把它写进日志，残留的会被当成本次结果）；容器经 `/results` 挂载写出的其他固定名文件由实施会话补全，handoff 列出完整清单与查找方法。不改成 `mkdir -p`：残留的 `groups-ready.json` 会被等待循环立刻读到，拿到上一次运行的地址；共用目录还会覆盖上一次的 `results.json` 等结果。E1 建议的 `mkdir -p` 加“同目录先 smoke 后 journeys”回归不采用（Owner 2026-11-12、2026-11-13）。只改测试工具；kickoff §6 写明每次真实运行用单独的日志目录（原计划提交已写入，本次不重复修改） | 05 上向带旧 `groups-control/` 的目录运行一次，在取得占用之前以 2 退出并写明原因；T1 的 smoke 用新目录正常通过；04 证据每次真实运行用单独的日志目录 |
| T4 | t1 稳定门使 1280 正式截图取景偏移（E2；审核报告 §3 O1）。`t1.spec.ts` 的 `waitForGridShotReady` 用 `grids.first().screenshot()` 连续截元素图，Playwright 截元素图前把网格滚入视口；1280×800 下网格底边约 853 像素，页面被滚动，随后的整页截图里吸顶顶栏画在滚动后的位置，顶部出现 33–53 像素空带，表格页签条被顶栏盖住。合并后验证的 13 张正式 1280 图中 9 张如此，1920 图与诊断图没有 | 稳定门不改变页面滚动位置：改用不滚动的区域截图比较（例如按网格在视口内的可见部分做 `page.screenshot({ clip })`），或在门前记录、门后恢复滚动位置并核对。`shot-gate` 行加记门前与门后的滚动位置，其余字段与判定含义不变。R9 用同一种判定方式（上一行）。只改测试工具，不改 t1 的旅程步骤、判据与 M1 | 05 两次 t1 都满足：① B′ 当前截图清单的每个 `shot-gate` 均 rendered=ok、stable 为数字，无 timeout/unstable/error，门前后滚动相同；② 用既有 `t1-frame-scan.py` 方法核正式 1280 图与各自 pregate 顶部均匀行一致，无 pregate 的 device-tabs/forward-channel 为 0，目检页签条可见；③ 通过 B′ 冻结的 t1 业务断言、诊断与 M1，OpenAPI 匹配。旧 26 行/11 张/9 张为 FE4 样本数，B′ 按调用点清单重数并逐项映射，不少验截图；若中期布局使原判据无法适用，先交 Owner，不自行改判据或额外跑 t1 |
| T5 | 凭据检索的模式与时点（E3；审核报告 §2.3）。入口每次运行生成四类 token（`run-real-backend-e2e.sh`，本次在 `b771631276` 上重新核过全部生成点；实施前对 B′ 再扫）：① Repository Service 的 bearer `<前缀>-rs-<32 位十六进制>` 与 ② backend 的 internal bearer `<前缀>-internal-<32 位十六进制>`（`RS_BEARER`、`INTERNAL_BEARER`，每个 suite 都生成；前缀 journeys 是 `fe3b`，smoke 与 t1 是 `fe3a`），是一次运行里权限最高的两个凭据；③ smoke 的角色与输入 scope：`fe3a-<身份段>-<32 位十六进制>`（身份段如 `submitter`、`input-b-mod`，可含连字符）；④ journeys 与 t1 的“场景-角色”：`fe3b-<场景>-<角色>-<32 位十六进制>`（t1 走同一生成路径，Python `secrets.token_hex(16)` 分支，形如 `fe3b-t1-<角色>-…`）。①② 在前缀与十六进制串之间只有一段，按 ③④ 分别写模式会漏掉 journeys 运行里的这两个。合并后验证 handoff 用的 `fe3[ab]-[0-9a-f]{32}` 一个也匹配不到，“计数为 0”没有检出能力；检索又在 journeys 重跑之前执行，漏了重跑的日志目录。T1 只覆盖一次运行内部的 trace，T2 没写格式与时点，事后对日志与证据目录的检索两者都没有覆盖 | 新增只读脚本 `frontend/scripts/scan-credentials.py`：只用标准库，`python3 -I` 运行，不加依赖。参数是若干目录；递归读全部文件，zip（含 Playwright trace）逐成员解压；分别计数 `Bearer ` 后接 token 字符、`dir-token`、`gdds-handoff=`、入口 token，源码模板 `Bearer ${` 单列。入口 token 用一条模式覆盖上述四类，不按格式分别写：`fe3a-` 或 `fe3b-`，接一段或多段小写字母、数字和连字符，再接 `-` 与 32 位十六进制，其后不再跟十六进制字符，即 `fe3[ab]-[a-z0-9-]+?-[0-9a-f]{32}(?![0-9a-f])`（与审核会话的 `node-scan.py` 相同）。只输出计数与命中文件的路径，不输出匹配值；输出头记 hostname、起止 UTC 与各目录。每次先自检：在临时目录生成三种形状的随机假 token（smoke 的 `fe3a-<身份段>-…`、journeys 的 `fe3b-<场景>-<角色>-…`、服务级的 `fe3b-rs-…`），每种在明文文件与 zip 成员中各放一份，每份样本都被命中、各项计数都不为 0 才继续，否则以非零退出；自检结果写进输出。实际计数任一不为 0 时以非零退出。仓库中不放含 token 形状的样本文件。kickoff §6 的规则同步（原计划提交已写入，本次不重复修改）；实施与审核提示词改为调用它；T1 的入口检索可以复用它的匹配规则；T1 的入口按值替换时，两个服务级 token 也在替换与检索的范围内 | 自检在 05 上通过（含 `fe3b-rs-` 形样本的明文与 zip 成员）；第 7 步全部真实运行（含失败尝试）结束后对其日志与证据目录执行，计数为 0；§9 第 10 步全部运行（含重跑）结束后对每一次运行的日志与证据目录执行，计数为 0 |
| T6 | `check-handoff-hex.py` 不核截断形式（E4；审核报告 §2.4）。`<十六进制>…<十六进制>` 只打印 `truncated (not verified)`（文件头说明也这样写）；合并后验证 handoff 的 30 种截断形式中 15 种与真实值不符（有的前缀就错，有的后缀取自值的中间），退出码仍为 0 | 每个截断形式的前缀与后缀必须唯一匹配一个已知完整值：`--sha-file`、`--evidence-file`、`--source-dir` 得到的 SHA256，或 `--git-objects` 下的 git 对象。匹配不到或匹配到多个时逐个列出行号与形式，以 1 退出。前缀或后缀不足 4 位的无法唯一核对，同样失败。文件头说明与汇总行同步改写。只改测试工具 | 一份样本 handoff（含正确截断各一处，以及前缀错、后缀取自值中间的错误截断各一处）：脚本以 1 退出并逐行指出两处错误；对本轮实施 handoff 运行通过。样本放交换目录 `evidence/`，不入库。修改脚本的样本功能验证在 05 的 clean 已提交 worktree 执行，测试样本与输出在树外；开发主机只对已有证据做只读回源，不运行样本测试 |

### 8.5 复评未重核六项的本次结论（静态核对）

| 项 | 当前依据 | 本轮处理 |
| --- | --- | --- |
| R9 | `upload-mode.spec.ts` 的 screenshot 仍先 waitForStableHeader 再 settleAfterResize；helper 仍用 header 元素截图 | 问题机制仍在，按 R9 重放；本次没跑图，不声称复现/修好 |
| O2 | `model.ts` 的 DerivedTable/tableProjection/deriveBundleView 与页面回退均已改，删除来源 `34d16d6bd9` | 标记中期完成，B′ 重核；不删有消费者的 notice/table_scope |
| O4 | `styles.css` 旧注释在 `3e05f0aae9` 删除，现 N5 指 disabled-reason | 标记中期完成，B′ 重核 |
| T2 | kickoff §6 已要求全部运行后检索、逐 zip 成员解压；wrapper 没有内建扫描 | 规则已具备，T1/T5 落实，基线按手工口径 |
| T4 | `e2e-real/t1.spec.ts:waitForGridShotReady` 仍用 grids.first().screenshot | 修法保留；中期改了用例内容，须按 B′ 清单和已接受布局核收，旧数量不作当前结果 |
| T6 | `check-handoff-hex.py` 仍将 TRUNC_RE 命中收集后跳过完整值核对，说明写“printed and not verified” | 仍需取用截断核对改动并在专用节点验证样本，不复用旧通过结果 |

另已重扫当前真实入口的 `openssl rand -hex 16` 与 `secrets.token_hex(16)` 生成点：两个服务级 bearer、smoke 角色/输入 scope、journeys/t1 场景角色均仍落在 T5 四类模式。T1 按值覆盖全部生成 token，T5 按模式证明检出能力；后续 B′ 若新增生成点须同步纳入。这里只读源码，无凭据值进入记录。

**T1 的设计。** token 进入 trace 的途径不止请求头：`addInitScript` 与 `page.evaluate` 的参数、Node 侧 `APIRequestContext` 请求都会被记录（FE4b 的 trace 中 16 个 token，14 个在请求头、2 个在动作记录）。只关掉网络记录不够。建议由真实 backend 入口在 Playwright 结束后处理保留下来的 trace：入口自己生成全部 token（含两个服务级 token，§8.4 T5 的四类），逐个 zip 成员把每个 token 值与 `gdds-handoff=` 的载荷换成固定占位，再逐成员检索并把计数写进日志（`trace_redaction=ok|failed` 与各项计数）；处理失败或检索不为 0 时入口以非零退出并写明原因，不覆盖测试本身的结果。其余排障内容（动作、截图、DOM 快照、网络时序）保留。实施会话可以选别的做法，但必须满足同一完成标准：在 05 上用一个只为制造失败的临时提交（不入候选，SHA 记入 handoff）跑一次真实 backend smoke，保留的 trace 逐成员解压后，入口生成的 token（§8.4 T5 的模式）与“`Bearer ` 后接 token 字符”均为 0；源码模板 `Bearer ${` 单独计数，不算凭据（与 FE4b 证据核对的口径相同）。

## 9. 顺序、验证与退出

所有 mock 全量均带截图；07 对 B′@07，04 对 B′@04。旧 `fe-remediation/evidence/` 内容仅作方法参考。新证据放独立标识子目录；全部原始失败和重跑记录保留。

| 步 | 内容 | 验证/条件 |
| --- | --- | --- |
| 0a | Owner 指定新起点候选，核收后端 stage 门禁；取 07 mock 基线和 04 完整 journeys 对照 | §2；mock/门禁失败先修，journeys 业务失败逐项记录但不阻塞开始 |
| 0b | 核收 B′/`gw08-midterm-exit`；从 B′ 开新分支、重核源码清单 | 本计划经一致性核对；旧分支不改；B′ 的测试与截图计数入 log |
| 1 | 取用 H4 工具、核缓存、在新树全量格式化 | 格式化重放一致；入口全过；截图相同或噪声；公式文本节点不变 |
| 2 | H1 取规则并重做移动/导入 | 全量入口含规则单测；中期新增文件过三层规则 |
| 3 | H2 在新树拆 comparison 子组件/函数 | 全量入口与截图；color-moved 自查 |
| 4 | H3 三个组件各一提交（Archive 取用，两页重做） | 每提交一次 mock 全量；原用例不减；同步段、依赖、effect 顺序核对 |
| 5 | O1 重做；O2/O4 只核收 B′ 状态 | mock 全量；O1 两个探针各能击穿新用例，临时提交不入候选 |
| 6 | R9/T4 稳定门手工重放 | 07 连续两次 mock 与 `--stable` 比较；T4 t1 留第 7 步 |
| 7 | T1/T3/T4/T5/T6 手工重放 | 05：T1 临时失败 smoke 与 trace；T3 占用前拒绝；T4 一次 t1 调试；T6 样本；全部结束后 T5 自检、覆盖全部尝试扫描。正常 smoke 用独立目录运行，临时故障结果不冒称正常通过 |
| 8 | G1 在新结果读取/文案模块重做 | 参数表、mock 全量、截图及无 pair_id 子串检查；REVIEW 单对专用文案不变 |
| 9 | 新候选 C、handoff、整轮独审 | 范围 B′..C；包含所有取用、手工重放与中期新增模块接线；定向修复由原审核复审 |
| 10 | C 的退出证据全部重做 | 04 clean detached 经 wrapper 依次 mock 全量、上传包校验、真实 smoke（不传 subphase）、完整 journeys（subphase fe4b），各唯一 session/log-dir；05 对同 C 跑 t1（subphase fe4b）。所有尝试结束再扫描日志/证据及 zip 成员；独审核收 |
| 11 | G2 收到最终 Sb 后进行，可早于 9 或晚于退出 | 按 §8.2；生成快照及类型，核实际消费者，相关验证绑定新候选 |
| 12 | 包含后端退出 Sx 的完整 journeys | §9.1，与第 0a 步基线逐用例对照，S3 前核收通过 |

**第 10 步判据。** 所有必需入口通过；mock 为 B′ 的原用例加本轮新增，既有用例断言不变；真实 suite 按 B′ 用例清单逐项核对，不沿用旧 9/21 数字。mock 只有相同或噪声，04 对 07 `--stable`；OpenAPI match；T4 t1 满足 §8.4；T5 自检逐类通过、所有检索计数 0；T6 回源含截断形式通过。基线 journeys 已有失败可用于归因，不构成第 10 步或 S3 的豁免，若仍失败依 §9.1 交 Owner。04 的 B′ mock 未取过时先补取，不拿 FE4 截图代替。

- **上传包/t4：** 筛查 B′..C 的 `upload-package.ts`、`UploadStepCard.tsx`，确认只有可重放的格式化，不拿 H..B′ 的中期变化归罪本轮。四个包用 B′ 同输入、同工具链的确定性输出作逐字节对照；如暂无 B′ 包，按原包校验入口在 04 的 B′ 已提交树产生对照，不额外跑 t4。若筛查发现非格式化的打包流程变更，停相关项核是否越界；不得自行免掉所需验证或扩大真实测量。
- **t1：** 沿用 Owner 2026-11-13 选定的甲：05 含 T4 提交调试一次，第 10 步同 C 取证一次；输入仍为 `/home/dev/gateway-real-dumps/source-dirs/` 的 t1-v1/t1-v2，不增加 B′ t1 全旅程。B′ 的源码断言、截图清单、已接受布局用于核对中期变化，旧 FE4 t1 证据只是故障说明。涉及旧验收判据不适用时先交 Owner。与 04 可并行，若实际资源干扰则协调；长测前读执行入口与长时间执行规则。额外 t1 不自动授权。
- **失败处理：** 内容截图变化、产品错误或证据失败即停受影响运行和依赖验收，交设计会话/Owner；无依赖工作可继续。命令/路径/已批准缓存等确认的构建条件错误按现行快速修复规定处理，工具/取证问题按 DC68；每次新尝试留原件，不覆盖失败。不因发生在 build 就把产品问题当环境错误。
- **退出：** 独审及证据核收、Owner 确认后，由设计/指定会话打附注 `fe-remediation-exit`，新分支以 `--no-ff` 合入 main；先试合并，冲突停下协调，frontend 夹具有变化按 §9.2。不得推送。G2 与 §9.1 可按原决定晚于前端 tag，但 §9.1 必须在 S3 前完成并通过。
- **缓存收尾：** 退出合入后按原授权更新 04/05/07 默认 `frontend/npm-cache` 和归档，核现场占用与消费者；只增加条目，保留旧归档、记录前后身份，fe0 不动。Owner 转交新默认缓存的完整摘要、来源提交和实际节点路径；不提前改默认、不清别人资源。
- **一页总结：** `frontend-remediation-summary-iris-20261117.md` 写做了什么、与设计偏差、遗留、验证结论/未测限制并引用新证据目录；不抄机器记录。含 §12 门禁说明，经 Owner 交规则会话修改 AGENTS/testing-conventions。`fe-vnext` 保留至退出，清理不自动包含在本次计划修订内。

### 9.1 整顿后的后端上跑一次 `journeys`（Owner 2026-11-13）

- **决定：** 前端 `journeys` 完整集至少有一次跑在包含后端整顿退出提交（下称 Sx）的后端上，由前端会话在 04 执行（`project-review-2026-11.md` §20.2）。依据：第 10 步在未接入 Sb/Sx 时仍跑在分支起点 B′ 的后端上，而后端整顿会把授权与错误码映射从 `http` 搬到 `application`。
- **触发：** Sx 由 Owner 转交并记入 `log.md`。收到之前不猜测后端进度。
- **方式 1：** 第 10 步运行时 C 的 `vnext/` 已包含 Sx（`git merge-base --is-ancestor Sx C` 成立，例如做 G2 时合入的 main 已含它）。这时第 10 步的 `journeys` 就算数，不另跑；在 `log.md` 记一句并写明核对命令的结果。
- **方式 2：** 否则在两端都合入 main、且 G2 的快照提交也已进入 main 之后补跑一次：取当时的 main 头 M2（核对 Sx 与 G2 快照提交都是 M2 的祖先），在 04 上 M2 的 clean detached worktree 中经 `run-evidence-wrapper.sh` 跑 `journeys` 完整集，参数与第 10 步相同（`--subphase fe4b`），用单独的 `--log-dir`；npm 缓存用“退出”一段更新后的默认目录。快照必须与该后端一致，否则入口会停在 OpenAPI 比对，所以排在 G2 之后。运行结束后用 `scan-credentials.py` 检索其日志与证据目录。
- **时限：** 不阻塞 `fe-remediation-exit`；在后端 S3 实施开始之前完成（`project-review-2026-11.md` §20.2）。
- **记录：** 结果记入 `log.md`（M2 或 C、Sx、节点、hostname、起止 UTC、起止 HEAD、exit code、用例数、日志 SHA256、凭据检索结果），证据放交换目录 `evidence/iris-20261117/`，并用一句话告知 Owner。
- **对照：** 以第 0a 步 B′ 完整 journeys 的用例名、结果、错误码/状态码逐项对比 C 或 M2，分清原有失败、新失败、已修复与无法归因；若规则/夹具/用例集另变须标明，不能仅凭总数相同认定等价。
- **失败：** 失败即停，不改断言、不放宽判据。把差异表、原始失败用例与错误码/状态码交 Owner 判断归属。基线失败不阻塞开始整顿，但整顿后失败或未知不满足 S3 放行；修复后重做受影响验证，不能用基线失败关闭 finding。被测对象运行前的命令、环境与缓存问题仍按 AGENTS 的构建故障快速修复与 DC68 处理并记录每次尝试。

### 9.2 通道规则并行修改

通道规则只改内容，不为其预留前端 UI 改造。本轮不改后端 `capabilities/table_rules/`、`business_navigation/`、`risk_evaluation/`，也不改其他后端源码。规则内容/版本/golden 单独提交，经 Owner 通知两端；不直接联系后端 agent。

若规则合入带动前端夹具，接收 Owner 通知后记录规则提交与受影响用例。在**包含该规则改动的提交**上重取截图基线，再继续比较；规则提交与整顿提交分开，分别判断行为差异，不把规则变化混进重构提交。为识别整顿回归，保留该规则提交应用到未整顿 B′ 前端的对照树，或等价的逐提交前后对照；不能仅把重构后的新图直接升为基线。不重打 `gw08-midterm-exit`，只记录新规则版本对应的截图对照。来源冲突或业务差异无法归因时停受影响比较交 Owner。

### 跨端交接（Owner 2026-11-13 开工补充）

前后端由不能直接通信的不同 agent 执行。只写本端阶段区并向 Owner 给出可直接转发的文字；不调用消息工具联系另一端、不写另一端 log/prompts、不把共享文件出现或 Git 分支前进当作对方已收到通知。接收方在本端 log 记录 Owner 原文、来源提交及处理结果，再由 Owner 回传。没有收到依赖输入时只暂停相关步骤，其余工作继续。

| 交接 | 发出时点与必填内容 | 接收方动作与回执 |
| --- | --- | --- |
| BE-SCHEMA-NOTICE | 后端 G2 进入 main 时立即发：完整提交、main HEAD、vnext tree、允许的差异、公开 schema 尚可能变化与否、OpenAPI mismatch 窗口 | 前端记录；未取得最终 schema 前，继续固定 B′ 的独立整改和 mock，不盲目合入后端新树或绕过 OpenAPI 检查 |
| BE-SCHEMA-FINAL | 后端确认 schema 不再变化时发 Sb、main HEAD、vnext tree、schema 原件路径/摘要和逐项差异；若有 P1 公开 DTO 删除，附 Owner 逐字段决定和消费者核对结论 | 前端核 Sb 在 main，按 G2 同步快照与类型；差异必须全部匹配交接清单。若影响实际前端消费者或需改行为，停相关项交 Owner，不能借生成类型更新隐式修改行为 |
| BE-EXIT | 后端 exit 后发 Sx（tag 指向提交）、tag、main HEAD、vnext tree、总结/证据索引，明确 Sb 是否仍有效 | 前端核 Sx 祖先关系，安排 §9.1 的 04 完整 journeys；已有合格运行则回执引用，不重复运行 |
| FE-SCHEMA-ACK / FE-JOURNEYS | 前端发快照提交、合入 main 的提交、消费的 Sb/Sx、运行候选/节点/原件、结果与未完成项；新 npm 缓存来源提交/归档摘要/节点路径单列 | Owner 转后端登记。S3 实施前必须核收包含 Sx 的完整 journeys 通过结果；失败或未知不算满足 |
| FAILURE / REVISED | 任一端失败或改变已交接的 schema/候选，发旧/新 SHA、失效范围、失败用例、观察到的错误码/状态码和原件；不放凭据 | Owner 决定归属并转发；修复后原审核定向复审、重做受影响验证，再回执。旧回执保留但明确失效 |

Sb 与 Sx 是两个不同用途的提交，不能互相代替。FE 04 证据及 BE 04 stage gate 共享节点，按现场有效占用排队，不抢占；只有实际冲突才经 Owner 协调。前端保持独立 worktree/分支，后端在 main 推进；前端准备合入时经 Owner 转交候选、写入范围和 main 接入时点，不让两个会话同时修改同一 worktree。

## 10. 独立审核

整轮末尾一次，由 Owner 转交给独立的新会话，审核 `B′..C`，重点 H3，其余各项一并看。单 agent 实施不取消独立审核，也不让实施者自行组建审核团队。

- **角色：** Owner 安排独立审核会话，模型由 Owner 选择，不套用后端角色/模型分配；报告写明范围、风险与实际模型。该会话一并核对 §9 第 10 步的证据，不强制另设验收核对角色；审核结果和修复意见均经 Owner 转交实施者。

- **审核现场：** 代码审核使用只读 clean detached worktree；探针由实施者在专用节点另建临时已提交树执行，审核会话指定风险点并核结果，不修改审核树或正在测试的树。
- **H3：** 每个 hook 的职责与 §7.2 一致；`git diff --color-moved` 下非移动改动逐条有理由；§7.1 的各条规则与 §7.3 的 effect 顺序、重置序列、具名函数与捕获值逐项核对；由实施者在 07 对每个组件挑一两处审核指定的高风险接线做探针（例如撤掉某个重置或调换两个 hook 的调用顺序），看 mock e2e 是否失败；不失败的记为覆盖缺口，写进报告，不阻塞。
- **H4、H1、H2：** 格式化提交可重放；三条规则与规则单测；移动是否整块；t4 筛查（§9）：两个打包文件在 `B′..C` 中只有格式化提交的改动。
- **G1：** 推导表、等价性论证与单测；源码中不再有 `pair_id` 子串匹配。
- **O1、O2、O4、R9、T1、T3：** 按 §8.4 的完成标准复核，T1 的检索在审核会话自己的解压结果上重做。T3 的清单含 `input-scope-results.json`，并与入口实际的固定名输出对照。
- **T4：** 稳定门不再改变滚动位置，R9 与 T4 的判定方式一致；对第 7 步 t1 的 `shot-gate` 行与截图，审核会话自己用 `t1-frame-scan` 的方法重测顶部均匀行数，并目检按 B′ 映射后的受影响截图。
- **T5：** 脚本只用标准库、只输出计数、先自检；入口 token 是一条模式，四类（两个服务级 token、smoke 的角色与输入 scope、journeys 与 t1 的“场景-角色”，含可带连字符的身份段）都能命中，自检样本含 `fe3b-rs-` 形的明文与 zip 成员；T1 的替换范围含两个服务级 token；审核会话在节点上自己运行它，自检通过后检索第 7 步的日志与证据目录。
- **T6：** 审核会话另做一份含错误截断的样本 handoff，脚本以 1 退出并指出行号；对实施 handoff 运行通过。
- **截图：** 审核会话在 07 跑一次 C 的 mock 全量，与 B′@07 比较。
- **结论：** 可以退出、定向修复或停下交 Owner。报告放交换目录 `reviews/`，文件名加本轮标识。
- **证据核对（第 10 步之后）：** 按第 10 步的判据逐项核对；05 t1 按 T4 的标准；凭据检索在全部运行（含重跑）结束之后执行、覆盖每一次运行的目录，审核会话自己再运行一次 `scan-credentials.py`；handoff 回源含截断形式；写明 §9.1 是方式 1（核对 Sx 是 C 的祖先、`journeys` 用例清单与 B′ 核收清单对应）还是留待方式 2；Sx 尚未转交时写“待定”。

## 11. 与输入的出入与 Owner 决定

以下 §11.1/§11.2 保留暂停前决策记录，H、旧 B、旧数量及旧分组不是本轮现状；实施以本文 §2–§10 的 B′ 修订为准。历史中允许同步段不同 setter 换序的解释已由 §7.1 的全部语句保序取代；O2/O4 与 F7 的中期状态见 §8，不重复执行旧动作。

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

计划评审意见（`/home/dev/gdds-stage-exchange/whole-project-review/remediation-plan-review-frontend.md`）与 Owner 同日的决定（`project-review-2026-11.md` §20.2）。

1. **Owner 决定：E2、E3、E4 并入本轮**，代号 T4、T5、T6（§1、§8.4、§9、§10）。同批的 E1 就是 T3，以 T3 的修法为准；E1 建议的 `mkdir -p` 与同目录回归不采用。三项都只改测试工具。T5 采用审核报告的建议，做成仓库内的只读脚本 `frontend/scripts/scan-credentials.py`，并加自检，使每次检索都先证明有检出能力。
2. **Owner 决定：整顿后的后端上跑一次 `journeys`**（§9.1）。
3. **Owner 决定（2026-11-13）：T4 的 t1 验证按甲执行**（DC33）。甲：05 上调试一次（第 7 步）加 C 上的证据一次（第 10 步，与 04 并行），04 不加 t1。未采用乙（只在第 10 步对 C 跑一次）。理由与耗时见 §9“t1”一段。
4. **评审补充，采纳：** T3 的检查清单点名 `input-scope-results.json` 与入口的其他固定名输出（§8.4 T3）。
5. **评审补充，采纳：** kickoff §4.2 的页面 state 规则收窄到 `ComparisonPage`、`WorkbenchPage`、`ArchiveMainlineDialog` 三个组件，与 §7.1 第 1 条的完成标准一致，并保留输入原话“新功能的 state 进入对应的 hook 或新 hook”。原措辞把三个组件的完成标准变成了对所有页面组件的禁令，又没有门禁支撑。
6. **补记与输入的出入：** H1 加了一个用 ESLint Node API 的规则单测（§5），证明三条规则确实生效；输入没有这一项。它不加依赖。
7. **计划复审修正（`/home/dev/gdds-stage-exchange/whole-project-review/remediation-plan-rereview-frontend.md` §1）：** T5 原先只列了两种 token 格式，漏了入口每个 suite 都生成的 Repository Service bearer 与 backend internal bearer（`fe3b-rs-…`、`fe3b-internal-…` 只有一段，不符合 journeys 的“场景-角色”格式，分别写模式会漏检，而自检也只含那两种格式）。改为：一条模式覆盖四类 token；自检加 `fe3b-rs-` 形样本，明文与 zip 成员各一份；T1 按值替换时含这两个 token（§8.4 T1、T5，§10）。源头是计划评审 §1.3 漏写。复审结论：改完不再评一轮。

### 11.3 2026-11-17 复评落实与待核收

复评 §6.3 七项分别落实：新分支与旧来源保留（§3）、21 提交取用/重做（§3.1）、同步段保序/无行内 ignore/截图变化即停（§4、§7、§9）、全部基线重取（§2）、证据与 B′..C 独审重做（§9–§10）、B′ journeys 对照（§2、§9.1）、通道夹具重取截图（§9.2）。§6.2 未重核的六项已在 §8.5 给出源码依据；O2/O4 的目标已由中期实现，不为它们增加无用改动。

待核收的是 B′/tag 与真实运行结果、整体复盘会话的一致性意见和 Owner 选定计划版本；本次没有新产品范围或新依赖请求。当前静态核对不宣称测试、截图、节点缓存或最终验收通过。

## 12. 交规则会话的门禁说明（整顿结束时，由 Owner 转交）

| 门禁 | 运行 | 失败时 | 豁免 |
| --- | --- | --- | --- |
| 前端格式检查 | `frontend/scripts/run-tests.sh` 在 `npm ci` 之后执行 `npm run format:check`（`prettier --check .`，Prettier 3.9.10，配置 `frontend/.prettierrc.json`） | 逐个列出未格式化的文件，以非零退出，入口失败。修正：在 CT201 的开发 worktree 执行 `npm run format` 后提交 | 只有 `frontend/.prettierignore` 列出的生成类型、测试夹具、OpenAPI 快照与 lockfile；不用行内 `prettier-ignore` |
| 前端分层规则 | 同一入口的 `npm run lint`，规则在 `frontend/eslint.config.js` 的 `no-restricted-imports`，由规则单测证明生效 | ESLint 报 `no-restricted-imports` 并给出层次说明，lint 以非零退出，入口失败 | 无；A 层测试导入 `features/dev` 属于规则范围（§5） |

实际名称与命令以实施后的一页总结为准；这里是设计。

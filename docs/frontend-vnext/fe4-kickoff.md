# FE4 kickoff：前端收口与业务导航接入

- **状态：** 修订 1，2026-11-10。初稿（`e0082180e0`）经[审核](reviews/fe4-kickoff-review.md)（`6536502a11`，定向修订）后，按审核意见与 owner 2026-11-10 的决定修订（§13、§14）。修订 2（同日）：owner 按建议确认其余问题，并补充决定 BE-b 第二步在 S1a 结束后由后端开始（§10、§13.3）。§10 的问题已全部由 owner 决定。修订 3（同日）：定向复核（[复核报告](reviews/fe4-kickoff-rereview-1.md)，通过）的 R1–R4 与后端记录更正（§13.4）。修订 4（同日）：FE4a 审核（`541febf566`，定向修复）交设计会话的 D1（C4 截图稳定性）、D2（审核模式顶栏在 1280 下横向溢出）与看图范围，owner 2026-11-10 按设计会话的建议确认（§10 Q14–Q16，处理见 §15）。修订 5（2026-11-11）：按 BE-b 第二步候选 `b61cc37d5f` 与前端窄复核同步 §3.1 与 §5.3，owner 同意 B9 退役（§10 Q17、§13.6）。修订 6（2026-11-11）：FE4a 证据运行（被测提交 `59c5b8cfca`）在 04-c 真实旅程完整集停止（[证据核对第 1 轮](reviews/fe4a-evidence-check-1.md)，`fe4a-review` 分支 `14f8daa7f8`，尚未合入 main）：候选的真实旅程 helper 没有随 C12 第 3 条同步。设计会话决定以 fix4（只改测试代码）修复，并安排调试、复审与证据重跑；owner 2026-11-11 确认 fix4 的一次完整集调试与证据重跑的解释（§10 Q18、Q19）；更正 §15.4 的错误说法（处理见 §16）。修订 7（2026-11-11）：fix4 第一个候选 `d12e3b8f70` 的 05 完整集调试有 3 个 scope 失败，原因是 §16.2 写定的 helper 规则不适用于工作台工具栏的原生按钮（设计会话的错误）；改写 §16.2 的 helper 规则，owner 2026-11-11 授权再跑一次完整集调试（§10 Q20，处理见 §17）。**FE4a 当前：** 等待 fix4 修正候选。
- **日期：** 2026-11-10（时间均为 UTC）。
- **起点：** `fe-fe3c-exit`（tag 对象 `43e66d3eb7` → `06b454b0ef`；被测提交 `e22e39ba15`；`frontend/` 树 `46e425f84e`）。main 合入提交 `475022300c`，退出记录 `16ffe72829`。
  `fe-vnext` 仍在 `e22e39ba15`，比 tag 少一个 docs 提交（`06b454b0ef`，只新增 `fe3c-evidence-04.md`）。
- **依据：**
  - [前端 kickoff](frontend-kickoff.md)：§3.3、§4.5、§4.6、§5 BE-b、§6、§7 FE4 行、§9、§10；
  - [BE-b 设计草案](be-b-navigation-and-presentation-draft.md)（第一步，全文）；
  - [FE3 kickoff](fe3-kickoff.md)：§2.3 末段、§3.2 的 FE3b、FE3c 退出记录、§4.6、§4.7、§8、§9、§10、§11 Q21、§12、§14、§15.5 第 9 项；
  - FE3c：[审核](reviews/fe3c-review.md)（N2–N5）、[复审第 1 轮](reviews/fe3c-rereview-1.md)（M1–M3）、[证据停止核对](reviews/fe3c-evidence-stop-1.md)（N9）、[证据核对](reviews/fe3c-evidence-check-1.md)；
  - FE3b：[复审第 1 轮](reviews/fe3b-rereview-1.md)（N2，并入 C6）、[复审第 2 轮](reviews/fe3b-rereview-2.md)（N2）、[复审第 3 轮](reviews/fe3b-rereview-3.md)（N2、N6）、[证据核对](reviews/fe3b-evidence-check-1.md)（N7、N8）；
  - [FE2 kickoff](fe2-kickoff.md) §5.3（行定位的浏览器自校验）、§5.4、§5.5（诊断文案表）；
  - 后端对 FE3 Q21 的答复：[`p6-fe3-q21-answer.md`](../backend-vnext/refactoring/formal/plans/p6-fe3-q21-answer.md)（提交 `d3450675bf`；2026-11-10 由审核会话以 `--no-ff` 合入本地 main，合并提交 `d10f6d55a8`，未推送；§10 Q10）；
  - [FE4 kickoff 审核](reviews/fe4-kickoff-review.md)（`6536502a11`）与 owner 2026-11-10 的决定（§10）；
  - [UI 优化方向](ui-optimization-direction.md)（§3、W3、W5、X6、§7.3、§7.4）与 `sketches/`；
  - AGENTS（main 版本）：“角色与子 agent”（`b93bed6bda`）、“专用测试节点”（DC91 五节点池）、“前端测试（FD7）”、“Docker / Compose 验证”；
  - [Owner 决议](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md) DC91、DC97、DC98。
- **P7 文档的用法：** P7 S0 决议、总体设计、执行计划与 S1a 设计已提交在本地 main（2026-11-10 合入 `p7-s1a-a`，合并提交 `00ca325c2e`，未推送）。S0 决议写明 S0 已收口，owner 已授权 S1a A–G 编码至本地退出；P7 文档没有提到 BE-b。本文只引用其中的事实，以及 owner 2026-11-10 对 BE-b 与 S1a 先后的决定（§4、§10 Q5），不据此推导 BE-b 的设计内容。
- **会话分工：** 本文由前端设计会话维护。按 AGENTS“角色与子 agent”，FE4 的实施与审核都由**新会话**承担：
  - FE3 的实施、审核会话已退出活动分工，不接 FE4；
  - FE4a 与 FE4b（§5）是两个明确划分的子阶段，各自新建实施与独立审核会话；FE4a 的会话不接 FE4b；
  - 同一子阶段内的 finding 由该子阶段原审核会话连续复审，直到该子阶段退出；
  - 新会话不继承旧会话的对话上下文，交接材料见 §12；
  - 后端 BE-b 的设计、实施与审核按后端流程另行指定（§4），前端设计会话不写后端提示词。

## 1. 结论摘要

1. **拆成两段（§5，§10 Q1，owner 已决定）：** FE4a 不依赖 BE-b，可以马上开始：FE3 带入项、Q21 文案、视觉令牌、取证工具，并在 P6 退出的 backend 树上重跑真实旅程与 t1。FE4b 接入 BE-b，等 BE-b 交付后开始，正式的真实数据重拍放在 FE4b。
2. **FE4a 的合入点（§6.1，§10 Q2，owner 已决定）：** `fe-vnext` 快进到 main `16ffe72829`，FE4a 期间不再合入 main，被测后端固定为 `vnext/` 树 `49c1de43be`（与 `p6-exit` 的目标 `b0fc25e881` 相同）。`16ffe72829` 已在远端，FE4a 开始前不需要推送。本地 main 之后合入的 P7 S1a 文档不进入 FE4a。
3. **后端变化（§6.2）：** 设计会话核对了 `fd9e383d76..16ffe72829` 的 `vnext/` 差异，审核会话补了导入闭包核对。`http/`、bundle 与 surface 组装、golden、部署和依赖输入都没有改，诊断码只是代码搬移；History 比较的 assemble 步骤多了终态失败，但前端只显示其 message。FE4a 预期不需要刷新 OpenAPI 快照。
4. **BE-b 与 P7 的先后（§4，§10 Q5，owner 已决定）：** FE4a 与 P7 S1a 并行。S1a 本地退出并合入 main 之后，由后端开始 BE-b 第二步设计，再实施；前端设计会话参与审核，核对面向前端的部分；FE4b 在 BE-b 之后（§10 Q4、Q5）。
5. **真实数据范围（§3.3、§7.2，§10 Q11，owner 已决定）：** FE4a 的 journeys 调试只跑 J1、J2，证据跑完整集一次；t1 证据一次，另允许一次调试运行（因 t1 套件加入参考截图）。两段都只报告 t1 MODIFIED_ONLY 的内存增量，不做计时，不用 t2–t4；打包流程没改就不跑 t4。修订 6：FE4a 证据停止后，fix4 另允许在 05 上跑一次完整集调试，证据在 fix4 候选上四项重跑（§10 Q18、Q19，§16）。
6. **前端 kickoff §3.3 的三个开放缺口（§3.7）：**
   - 历史初始备份节点、首批空基线：FE4 都不做，各自依赖一项尚未立项的后端工作；
   - `diagnostics_summary` 的自由文本：已于 2026-11-03 并入 BE-b §4.10，随 FE4b 接入。

## 2. 当前事实（2026-11-10 核对）

### 2.1 前端

| 项 | 值 |
| --- | --- |
| `fe-fe3c-exit` | tag 对象 `43e66d3eb7` → `06b454b0ef`；被测提交 `e22e39ba15`；`frontend/` 树 `46e425f84e` |
| `fe-vnext` | `e22e39ba15`，是 `06b454b0ef` 的父提交，也是 main 的祖先，可以直接快进 |
| main 的 `frontend/` | `16ffe72829:frontend` = `46e425f84e`。main 在 tag 合入后没有 `frontend/` 改动 |
| `frontend/openapi.json` | SHA256 `4c2ddca7d64ec77029528f5a6f03f73b17185784091530c7086fa67d484d620a`，等于 FE3c 原件（`vnext/` 树 `6368c9c40c`，SHA256 `ce58f20a209883983d270e6f9d758044a22ce35e15e11eee137d1595f92ac079`）按 FE3 kickoff §5.1 规范化后的结果 |
| 工具链、npm 缓存 | `mcr.microsoft.com/playwright:v1.64.1-noble`，config `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；npm 缓存归档 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a`（FE3c 证据核对 §4 在 04、05 上重算） |

占位与浏览器计算在代码中的位置（`fe-fe3c-exit`）：

- **占位导航：** `features/view-model/model.ts::fallbackNavigation`（`contract_version` 为 `frontend-placeholder/business-navigation/v1`）；手写的占位产物在 `src/test/fixtures/source/business-navigation*.json`、`navigation-diagnostics.json`，以及各后端 fixture 下的 `projections/business-navigation.json` 与 `fe2a/preview-modified-only/…/projections/business-navigation/diagnostics.json`。
- **浏览器中的行标识计算：** `features/view-model/table-rows.ts::snapshotRowIdentity` 及其规范编码（`canonicalTemporal`、`frame` 等），即 FE2 kickoff §5.3 的自校验匹配。
- **读取导航产物：** `features/bundle/presentation.ts` 已按 `projection_kind = BUSINESS_NAVIGATION` 读取导航产物与 `diagnostics_ref`；导航诊断文案在 `features/view-model/diagnostics.ts::NAVIGATION_COPY`（BE-b §4.7 的 10 个编码）。
- **Preview 公式抽屉：** `pages/ComparisonPage.tsx` 中有“改前公式在 BE-b 实现后提供”的说明。

### 2.2 后端与 main

| 项 | 值 |
| --- | --- |
| FE4a 合入点 | `16ffe72829`（FE3c 退出记录）；`vnext/` 树 `49c1de43be`。修订时远端跟踪 ref `gateway-data-management-system/main` 也指向这个提交 |
| 本地 main（修订时） | `27ea352487`（2026-11-10 05:10 UTC），`vnext/` 树仍为 `49c1de43be`，未推送。`16ffe72829` 之后的主线提交依次为：`00ca325c2e`（合入 P7 S1a-A 文档，2026-11-10）、`6536502a11`（本文审核报告）、`6a8fff14f3`（合入 P6/P7 文档清理）及其三个收尾提交、`d10f6d55a8`（合入 Q21 答复）、`27ea352487`（后端记录 S1a 前端交接与 BE-b 先后）。这些提交只改 `docs/backend-vnext/` 与 `docs/frontend-vnext/reviews/`；`AGENTS.md`、`frontend/`、`vnext/` 都没有改 |
| `p6-exit` | 本地附注 tag，对象 `e4791d4e8d` → `b0fc25e881`；tag 本身未推送，但 `b0fc25e881` 是 `16ffe72829` 的祖先，已在远端。`b0fc25e881:vnext` = `49c1de43be`。tag 说明写明“Frontend, P7, independent SDK and production release are not signed off” |
| FE3c 期间的 `vnext/` | `6368c9c40c`（main `fd9e383d76`） |
| `fd9e383d76..16ffe72829` 的 `vnext/` | 72 个文件：S5 的计算缓存（comparison、risk、snapshot export、control DB），S6 的 History 元数据与校验，以及测试与 benchmarks。逐类核对见 §6.2 |
| 依赖镜像 | `--print-input` 的五个输入文件（`backend/pyproject.toml`、`backend/uv.lock`、`backend/.python-version`、`rust/Cargo.lock`、`rust/rust-toolchain.toml`）与 `vnext/scripts`、两个 backend Dockerfile 在该区间都未改。预期仍得 `gateway-backend-deps:lock-578e079b762e`。输入还包括节点本机基础镜像的身份，因此以审核会话发出提示词时在所选节点上的实测为准 |
| RS 依赖镜像 | `repository_service/uv.lock` 未改，仍为 `gateway-p2r1-repository:lock-6dc9659f0aee` |

### 2.3 BE-b

- 第一步（数据结构与业务规则，含 §4.7–§4.10）已由 owner 确认（2026-11-02、2026-11-03）。
- 第二步（实现层设计：在哪一步计算、缓存、计时预算、golden 组织、History 侧注释的持久化）按草案应在“P6 S5 接近完成时”定稿，**尚未写**。P6 已在本地退出，这个时点已过。
- 后端没有实现。按 FD8，实现排在 P6 退出之后、Phase 8 之前。
- P7：S0 已收口，owner 已授权 S1a A–G 编码至本地退出（本地 main 上的 S0 决议）。S1a 的目标补充写入了 9 份 Contract，其中与前端有关的是：`artifact_id` 改为新格式；bundle 改为多 root 交付；被改写的 JSON 成员含新的 ref，其 raw SHA 与大小改变，可经 surface 与 closure 的完整性传递改变 surface/bundle 摘要（`comparison-bundle.md` 末节“P7-S1a 目标补充”、`p7-s1a-a-entry-and-contract.md` §4）。P7 的设计与计划文档没有提到 BE-b；BE-b 的先后由后端在 [S1a 前端交接与 BE-b 第二步设计启动](../backend-vnext/refactoring/formal/plans/p7-s1a-frontend-beb-handoff.md)（`27ea352487`）中按 owner 2026-11-10 的指示记录。
- **owner 2026-11-10 决定（§10 Q4、Q5）：** S1a 本地退出并合入 main 之后，由后端开始 BE-b 第二步设计，以 S1a 的实际实现与退出交接为基础，然后实施；前端设计会话参与审核，核对面向前端的部分。这取代修订 1 记录的“第二步现在可以开始”。后端分工与排期按后端流程处理，本文只记录前端的依赖（§4）。

### 2.4 Q21

后端答复（`d3450675bf`，2026-11-09；已合入本地 main `d10f6d55a8`，用 `git show main:docs/backend-vnext/refactoring/formal/plans/p6-fe3-q21-answer.md` 读取）核对了 `56720104af` 到 `6368c9c40c` 两棵树的差异，结论：

- `ROW_IDENTITY_UNSUPPORTED`、`ORDER_KEY_UNSUPPORTED`、`COMPARISON_MODE_NOT_DETAILED` 已经没有产生点；`BLANK_PROVENANCE_INVALID` 也没有主动产生点；
- `ORDERED_PROVENANCE_MISSING`、`ORDERED_PROVENANCE_INVALID`、`METADATA_ROUTE_REQUIRES_NATIVE_ROWS`、`METADATA_ROLE_REQUIRES_NATIVE_ROWS` 若触发，会成为表级 `DEGRADED` 诊断，写入 surface 的 `tables[].diagnostics.diagnostics_summary`（有序表另写入 `ordered_extension.diagnostics`），不会导致 operation 失败；
- `BLANK_PROVENANCE_MISSING`、`CANONICAL_BLANK_PROVENANCE_INVALID` 仍有产生点；
- 未捕获的意外异常改为向 operation 层传播，不再保证作为表诊断出现。

答复不覆盖 `6368c9c40c..49c1de43be`，这一段由本文 §6.2 补核。

### 2.5 节点、镜像与数据

- **节点池（DC91，AGENTS main）：** 五个节点都是 32 vCPU / 64 GiB，没有固定用途。任一空闲、且本次工具链、缓存与输入都已就绪的节点都可以使用。
  - 所有前端运行（含静态检查与模拟接口 e2e）都按原子 `mkdir /home/dev/gdds-node-busy.d` 取得占用，记录会话名、用途与开始 UTC，收尾后释放；
  - `run-real-backend-e2e.sh` 自行取得占用，外层不重复获取（否则 exit 3）；
  - 浏览器 worker 设 `GATEWAY_FE_TEST_WORKERS=2`；
  - 已知物理拓扑不变：04/06/07 同宿主，04、05、CT108 分属不同宿主。
- **按 FE3c 记录已就绪的节点：**
  - 04、05：工具链、npm 缓存、`lock-578e079b762e`、`lock-6dc9659f0aee`；
  - 07：工具链与 npm 缓存；
  - t1 组态目录 `source-dirs/t1-v1`、`t1-v2` 与 M1 用的 `t4-v1` 只在 05 上（FE3 kickoff §8.1）。

  其他节点要先按 DC67 预填充并核对身份，否则不能使用。审核会话发出提示词前现场核对。
- FE3 kickoff §12“FE4 真实数据重拍的节点”一项由 DC91 关闭：t1 可以在任一合格节点上运行，前提是该节点上的 t1 目录按清单逐文件核对通过（§7）。

## 3. 范围清单

每项写明处理、依据与所属子阶段。“FE4a”“FE4b”见 §5。

### 3.1 BE-b 接入（FE4b）

“BE-b §x”指第一步草案；“第二步 §x”指 [BE-b 第二步设计](../backend-vnext/refactoring/formal/plans/be-b-second-step-design.md)（候选 `b61cc37d5f`）；FE-BEB-xx 指前端设计会话对第二步的定向核对与窄复核的 finding（报告位置与 SHA256 见 §13.6）。

| # | 项 | 处理 | 依据 |
| --- | --- | --- | --- |
| B1 | 业务分组与筛选 | **结构：**<br>• 每个比较对恰好一份导航产物；缺失或多于一份按 B9 拒绝。<br>• 普通模式读 `groups`，固定五组，按后端给出的顺序通用渲染，`items` 可为空（空组可隐藏）；未知 `group_key` 按通用分组显示。<br>• `DATASET_REPLACEMENT` 读 `replacement_sides.before/current`，此时 `groups=[]`。两侧是独立的键空间：浏览状态、URL、整表视图键都带 `side`。<br>• 按 `group_key`、`item_key` 寻址（命令层、URL、筛选）。<br>**筛选：**<br>• `row_filter` 为 `null`（整表）或 `{before, current}` 双侧集合谓词（`{column, values}`）。对象内某侧为 null，表示该侧没有匹配身份，不表示整表。<br>• 按侧在本地执行；一对行中任一半命中即显示整对。<br>• 整数按 BigInt 值比较，字符串只和字符串比较，缺失与 NULL 不匹配。<br>**事实与标记：**<br>• 普通模式的筛选页签用 `facts`：`basis=EXACT` 用局部 `change_kind`/`risk_level`；`TABLE_FALLBACK` 用整表变化与风险，并提示“此页签按整表提示”。<br>• `table_scope` 是同表一致的表级标记，参与页签、项、组汇总和“只看变化/风险”筛选，不涂到各行。<br>• 整表页签和 `SECONDARY_DEVICES` 中 `item_kind=TABLE` 的整表项，从 surface 与 `RiskReport` 读取。<br>• replacement 的筛选页签 `facts=null`，只显示本侧计数。<br>**解码校验：**<br>• 有导航时不再把未出现在页签中的表补进“其他表”。<br>• 同表整表页签最多一个；整表页签与筛选页签互斥；同表的筛选页签同属一组。 | BE-b §4.2、§4.3、§4.6；第二步 §4.1–§4.3；前端 kickoff §4.5；FE-BEB-01、03、06、09 |
| B2 | 列展示与列序 | 普通比较的 `columns` 是两侧列名并集：<br>• 按 `present_in`（`BEFORE`/`CURRENT`/`BOTH`）在缺列一侧显示“该侧无此列”，与 NULL 区分；<br>• `display_order` 决定列序（并集内从 0 连续），`pinned` 决定固定列。<br>replacement 各侧用本侧 `replacement_summary.<side>.columns`。<br>列宽与对齐仍由前端计算；不提供隐藏 | BE-b §4.1；第二步 §4.3、§4.4；§6 Q4；FE-BEB-02 |
| B3 | 中文显示名 | 表名与列名取 `SurfaceTable.display_name`、`SurfaceColumn.display_name`；replacement 的表头、浏览标题、“查看整表”和带 side 的诊断表名取 `replacement_summary.<side>.display_name`；Debug 模式另显示标识符 | BE-b §4.1；第二步 §4.3；UI 优化方向 C6 |
| B4 | 行定位产物 | **定位：** 读 `row_locator_ref` 的五列 Parquet：`row_identity`、`before_row_index`、`current_row_index`、`before_filter_context_json`、`current_filter_context_json`。<br>**取身份值：**<br>• bundle 有该侧快照时按 index 读行，此时该侧 context 必须为 null；<br>• bundle 缺该侧快照时，从 context（JCS 小对象）取身份值，`{}` 与 `{"<列>":null}` 不匹配；<br>• 没有记录的行，两侧身份值相同（FE-BEB-12）；<br>• 快照中身份值的类型与谓词类型不一致时，作为 bundle 解码错误（FE-BEB-13）。<br>**显示：** keyless 删除行缺少的旧值显示“改前值不可得”，与 NULL 区分。<br>**删除：** `snapshotRowIdentity`、全部规范编码、`validateLocations` 和“本表的变更行无法定位”的匹配路径。<br>**回退：** ref 为 null 时按表级展示（BE-b §4.8 的既定回退），不在浏览器中补算身份 | BE-b §4.8；第二步 §4.2、§5.2；FE2 kickoff §5.3 末条；FE-BEB-08、12、13 |
| B5 | 视图 ID | 前端按 `pair_id` 区分视图，修复前后都不受影响；FE4b 核对代码中没有依赖 History `-p<i>` 形式的逻辑。模拟数据改用第二步 §7 的取值（`baseline_to_initial`、`initial_to_modified`、`left_to_right`、`left_to_middle`、`middle_to_right`），每个 pair 用自己的 `view_id` | BE-b §4.9；第二步 §7 |
| B6 | 诊断编码 | **导航诊断（BE-b §4.7 加第二步 §4.2 的两个新码）：**<br>• 就地提示，分组头汇总个数；<br>• `DEVICE_ROWS_UNASSIGNED` 提供“查看整表”（这是额外入口，不是导航页签），`changed_row_count` 为 null 时显示“变化行数未知”，replacement 下不显示变化行数；<br>• `DEVICE_TAB_FACTS_UNAVAILABLE` 每表一条，target 的 item、tab 为 null，带三个 reason 的文案；<br>• `DEVICE_FILTER_VALUE_UNSUPPORTED` 每个受影响侧一条，指向该表整表项，带三个 reason 的文案。<br>**surface 诊断：**<br>• 按后端 B4 交付的完整稳定编码表（新码→旧原文→emit 位置）更新文案表；<br>• 删除被取代的原文键、`DUPLICATE_EFFECTIVE_KEY:` 前缀切分、`*Error/*Exception` 正则，以及 `max_risk_tables_per_pair exceeded`、`max_risk_pair_wall_time_seconds exceeded` 两个键（这两条是 pair 失败，不进 READY surface）。<br>未知编码统一用通用文案，原值放 Debug | BE-b §4.7、§4.10；第二步 §4.2、§4.4；FE-BEB-05、06 |
| B7 | Preview 改前公式与装置名 | 双侧浏览表（`device`、`composite_signal_point`）在改前侧逻辑存在时必有 `before_table_ref`：表未变时别名 current，有变时单独导出；新增表的 before 为 null。<br>改前公式与改前侧装置名统一读 before ref，Preview 与 History 一样显示改前、改后对照。<br>删除“改前公式在 BE-b 实现后提供”以及用 current 回填 before 的路径 | BE-b §4.4；第二步 §5.1；前端 kickoff §8；FE-BEB-07 |
| B8 | 移除占位数据 | 删除手写的占位导航与诊断 fixture，以及前端生成器对后端私有符号的导入。后端 fixture 改由后端入口生成，前端 wrapper 只用 subprocess 调用并搬运输出（§5.3）。上传输入改由后端持有，前端模拟数据所用副本按后端清单逐文件核对 SHA256 | 前端 kickoff §4.5；第二步 §8；FE-BEB-10 |
| B9 | 回退退役 | BE-b 之后每个 READY surface 恰好一份导航（第二步 §4.1），“没有导航产物”已不可达。因此：<br>• 删除 `fallbackNavigation` 与 `preview-no-navigation` fixture；<br>• 缺导航或导航多于一份时，按该比较对的 bundle 解码错误处理，与其他 Contract 违例相同；<br>• 原 B9 中“没有注释用标识符”“没有 `display_order` 按 DDL 顺序”两个分支同样不可达，因为 `display_name` 和 `display_order` 为 required，一并删除。<br>原 B9 是前端 kickoff §4.5 确认的正式行为；owner 2026-11-11 同意退役（§10 Q17）。后端须按 FE-BEB-11 删去第二步 §4.1“无导航产物时 B9 回退仍可用”一句 | 前端 kickoff §4.5 第一条；第二步 §4.1；FE-BEB-11 |

Contract 版本：
- 导航仍为 `backend-vnext/business-navigation/v1`，但形状已改，旧占位产物用的也是同一版本串。因此解码器按形状严格校验，拒绝 `row_filter.value` 等旧字段，不按版本串分支。
- Comparison Surface v4、Comparison Bundle v4、CanonicalizationManifest 3.4.0 按各自 selector 精确匹配，不双读旧版本。

FE4b 的 fixture、程序判据与截图分工已按第二步写定（§5.3）；合入点、OpenAPI 与截图名等待 BE-b 交付后写定。

### 3.2 侧栏层级（§4.6，FE4b）

前端 kickoff §4.6 留下的问题：导航层级“视图 → 分组 → 节点 → 页签”能否精简。按 BE-b 第一步的结构判断：

- 多页签的项是业务需要：转发通道有 9 类转发表加“定值”，装置有 11 类测点表，规约通道有两张规约表。不能把“项”和“页签”压成一层：装置数 × 11 会把侧栏撑得很长。
- 只有一个页签的项很多：全局参数的各整表项、“其他表”中的每张表、装置总表、网口配置表。为这些项显示页签栏没有信息量。
- 大多数比较只有一个视图：MODIFIED_ONLY 的 Preview、两节点的 History。

**决定（owner 2026-11-10，§10 Q6）：** 层级的定义不变，渲染时按需折叠：

- 只有一个视图时不显示视图分段控件；
- 只有一个页签的项点击后直接打开该表，不显示页签栏，表名显示在信息行；
- 空组不显示，这是 BE-b §4.2 允许的；
- 有两个及以上页签的项保留页签栏，规则同 S3 草图。

侧栏搜索同时匹配项名、页签名、表的显示名与标识符。在 FE4b 实现：占位数据没有页签，规则只有在 BE-b 数据上才能验证。

### 3.3 真实数据重拍（前端 kickoff §6）

真实数据范围由 owner 2026-11-10 按 DC33、DC98 决定（§10 Q11），运行次数见 §7.2。

- **FE4a：参考截图。** 在 P6 退出的 backend 树上跑 t1 旅程（FE3 kickoff §8 的步骤与判据），并在 `e2e-real/t1.spec.ts` 中加入**不依赖 BE-b** 的关键页面截图。这些截图只作参考，不作验收：留在节点上，SHA256 写入 handoff。
  - 页面与截图名（`<名>` 后加 `-1280`、`-1920`，两种宽度都拍）：
    - `fe4-t1-workbench`：工作台，组态树与详情面板（第 1 步上传前）；
    - `fe4-t1-preview-v1`：Preview v1 差异浏览（全部新增，第 1 步）；
    - `fe4-t1-preview-v2-baseline_to_initial`、`fe4-t1-preview-v2-initial_to_modified`：Preview v2 FULL 的两个比较对（第 4 步，按 `pair_id` 取用，同 FE3 kickoff §8.3）；
    - `fe4-t1-review`：审核模式，固定在第 5 步（审核 v2 FULL，含两个比较对）；
    - `fe4-t1-history-3node`：历史比较三节点的结果（第 6 步）；
    - `fe4-t1-archive`：归档主线的业务核验概况（第 3 步；t1 v1 预期没有业务核验异常）。
  - 截图放在 M1 的测量窗口之外：第 1 步的 renderer 增量先取值，再拍 `fe4-t1-preview-v1`，切换宽度不进入 M1 读数。
  - 截图不增加旅程步骤，也不改变 FE3 kickoff §8.3 的判据。
  - FE4a 的退出条件不含依赖 BE-b 的页面。
- **FE4b：正式重拍。** 在 BE-b 交付后的 backend 上，用 t1 数据在 1280 与 1920 下重拍，交 owner 看图确认。t1 证据运行一次，同时产生正式重拍截图。范围：
  - 沿用上面 FE4a 的页面与截图名，作为 FE4b 的正式截图；
  - 加上依赖 BE-b 的页面，页面与截图名在本文第 2 步（§5.3）定稿并在 FE4b 实现：侧栏各分组展开、装置页签（按身份过滤）、中文列名与业务列序及固定列、行定位后的修改行连线与风险底色、导航诊断（若 t1 数据产生）。

  t1 的 `composite_changed` 为 0，Preview 改前、改后公式对照由模拟接口截图覆盖。
- **两段共同的范围：** 只报告 t1 第 1 步 MODIFIED_ONLY 的 renderer 增量；不做计时，不用 t2–t4；打包流程没改就不跑 t4（§7.4）。t4 上的导航正确性由 BE-b 的后端验证负责，前端不重复。
- **节点：** 按 DC91 选合格空闲节点，见 §2.5、§7.1。

### 3.4 FE3 带入项（FE4a）

| # | 来源 | 内容 | 处理 |
| --- | --- | --- | --- |
| C1 | FE3b N2（复审第 2、3 轮） | `resumeNotice` 在页面生命周期内不归零，再次提交后的“提交正在执行…”仍显示在红色提示框里 | 开始新的提交或上传时清除；或只在快照仍属于续做结果时显示。加一条模拟用例：续做后再次提交，提示框不再出现 |
| C2 | FE3b N6（复审第 3 轮） | `retryResume` 不经过 `refresh()` 的在途合并；W9④ 第一次重试后的断言不能区分新旧状态；G3 的放宽也作用于合并数据集 | `retryResume` 经过在途合并，快速连点只产生一次读取序列（用例断言 attempt 读取次数）；W9④ 的断言改为能区分重试前后的内容；G3 的放宽只作用于单页切片 |
| C3 | FE3b N7（证据核对） | 预览页顶栏中撤回与提交的禁用原因并排、没有分隔，读起来像一句话 | 两个原因分开显示，各自对应自己的按钮（`aria-describedby`），中间有明确分隔。补拍 `fe3b-w6-*` 三张 |
| C4 | FE3b N8（证据核对） | 截图中的等待时长按墙钟计算，每次运行的截图都不同 | 截图用例固定时钟（Playwright `page.clock`），等待时长显示固定值；截图冻结动画，视口切换后等待布局稳定。同一提交连续两次模拟接口全量运行，用 §3.8 的截图比较脚本以稳定性模式比较，每张截图都判为“相同”或“噪声”，没有“内容变化”、尺寸不同或缺失（判定规则与运行方式见 §7.3；修订 4 取代原来的“逐字节相同”，§10 Q14） |
| C5 | FE3c 审核 N2 | 过期通过后只重读 review，没有重读 History；V12 重读后的模拟数据仍没有处置 | 409 `BASELINE_VERSION_CONFLICT` 与 `ARCHIVE_CLOSED` 之后，同时重读 review 与 History；V12 重读后的模拟数据带处置，并断言按 FE3 kickoff §6.4 显示 |
| C6 | FE3c 审核 N3（含 FE3b 复审第 1 轮 N2） | 来源详情的摘要前 12 位没有悬停全文；理由超过 3 行不折叠，很长的单行理由也不折叠；原始码没有放进悬停提示 | 摘要悬停显示全文；理由按渲染行数折叠（超过 3 行时显示前 3 行加“展开”），单行长理由同样适用；`issue_code`、`subject_digest` 等原始值放进悬停提示（C6） |
| C7 | FE3c 审核 N4 | J1 第 8、10、11、13 步与 J2 第 1、7、8 步的接受用 API 助手完成；J1 第 14 步由提交人做历史比较 | 都改为经界面接受；J1 第 14 步改由审核人执行。真实旅程会变长，按调试运行的实测报告耗时 |
| C8 | FE3c 审核 N5、复审第 1 轮 M1 | `collectionNotice`、`pendingNotice` 在同一对话框会话中不清除；关闭返回 409 后，冲突提示替代了集合变化提示（FE3 kickoff §16.4） | 冲突提示与集合变化提示分两处显示，每次加载后清除待用提示；补两条模拟用例：关闭 409 后集合变化，两条提示都出现；集合未变时后续加载不显示旧的冲突提示 |
| C9 | 复审第 1 轮 M2 | 关闭对话框正文“关闭提交提交 2（不归档）”显示名重复；“确认关闭”成功后仍可点击 | 正文直接用显示名（例如“关闭提交 2（不归档）”）；成功后“确认关闭”不再可用，只保留关闭对话框的按钮。owner 看图时没有另作决定，按带入项处理 |
| C10 | 复审第 1 轮 M3 | 详情映射的单测没有覆盖 `INITIAL_SOURCE_UNEXPLAINED`、`GENERATION_TIME_LAST_NOT_MAX`、`TIME_ABNORMAL_INITIAL` 与“② 早于 ①” | 在 view-model 单测中补齐，按 FE3 kickoff §16.3 的文字逐条断言 |
| C11 | 停止核对 N9 | `workspace-shell.spec.ts` 中 11 处 `unrouteAll()` 不带参数，其中 `timeoutFirstCompare`、`historyBundleDelayMs`、`slowPreview` 三处有延迟 | 全部改为 `{ behavior: "wait" }`；带延迟的三处改用测试控制的闸门（同 FE3c fix2 的做法）。不改其他断言 |
| C12 | FE4a 审核 D2（修订 4 新增，§10 Q15） | 审核模式顶栏在 1280 下横向溢出：V12（`ARCHIVE_CLOSED`）页面宽 1340 px，V11（过期通过，`BASELINE_VERSION_CONFLICT`）宽 1509 px，FE3c 起就存在，真实 backend 上同样可达；面包屑被挤到宽度 0，模式标签“审核”折成两行。V12 重读后的模拟数据审核状态仍为“待审核”，不是后端可达的形状 | 规则见 §15.2：① 审核操作的错误提示移出按钮所在的行；② 处置说明独占顶栏一行；③ 审核操作组中相同的禁用原因只显示一次；④ 模拟接口截图前断言没有横向滚动；⑤ V12 重读后的审核状态为“已通过”。预览页顶栏不改（随 N5 在 FE4b 处理）。D1–D3、V11、V12 的顶栏截图交 owner 重新看图（§7.3） |

FE3c 证据核对的 E1、E2 都是 wrapper 的显示问题，由 §3.8 的取证工具处理；E3 已在 FE3 退出清理中删除。

### 3.5 Q21：诊断码文案（FE4a）

按后端答复（§2.4）与本文 §6.2 的补核，修改 `features/view-model/diagnostics.ts` 的 `SURFACE_COPY` 与 `SURFACE_DIAGNOSTIC_CODES`，并同步单测：

| 编码 | 处理 | 文案 |
| --- | --- | --- |
| `ROW_IDENTITY_UNSUPPORTED`、`ORDER_KEY_UNSUPPORTED`、`COMPARISON_MODE_NOT_DETAILED` | 删除 | — |
| `BLANK_PROVENANCE_INVALID` | 删除（答复 §4：没有主动产生点，只在保留原文的名单中出现） | — |
| `ORDERED_PROVENANCE_MISSING`、`ORDERED_PROVENANCE_INVALID` | 新增，放在有序表组 | 有序表缺少空行来源信息，或该信息无效 |
| `METADATA_ROUTE_REQUIRES_NATIVE_ROWS`、`METADATA_ROLE_REQUIRES_NATIVE_ROWS` | 新增，放在内部组 | 比较时发生内部错误 |
| `BLANK_PROVENANCE_MISSING`、`CANONICAL_BLANK_PROVENANCE_INVALID` | 保留 | 不变 |
| `ORDER_KEY_INVALID` | 保留；新的位置上界检查也归入此码 | 不变 |
| `COMPARISON_RULESET_DIGEST_MISSING` | 保留：答复没有列入删除，§6.2 也没有发现变化 | 不变 |

- 文案沿用 FE2 kickoff §5.5 的原则：只说原因，后果由表状态文字表达。“无法可靠比较”由 `DEGRADED` 状态表达，不写进文案。
- 匹配顺序不变：完整编码、冒号前缀、异常类名、通用文案。答复 §4 说明 native 普通错误仍映射为 `ValueError` 等类名，因此类名规则保留。
- 本节取代 FE2 kickoff §5.5 文案表中对应的行，FE2 kickoff 不另改。
- 风险引擎的英文短句与 `DUPLICATE_EFFECTIVE_KEY:<表名>` 不在本节，随 BE-b §4.10 在 FE4b 处理。
- FE3 kickoff §11 Q21 与 §12 的状态由本分支的另一个提交更新（§13）。

### 3.6 `--color-warning-soft`（FE4a）

现状：`styles.css` 中 `.form-warning` 引用了未定义的 `--color-warning-soft`，回退到 `--color-surface-muted`（灰底）。使用处有三个：`SubmitDialog.tsx` 的“需要管理员处理”与“Preview 结果已基于旧基线”，`UploadStepCard.tsx` 的 `MANUAL_RECOVERY_REQUIRED`。FE3a 复审 N8 时 owner 已看图接受灰底。

**决定（owner 2026-11-10，§10 Q7）：** 删除这个未定义的引用，直接使用 `--color-surface-muted`，外观不变，不新增黄色令牌。依据：

- owner 已接受灰底；
- UI 优化方向 §7.4 有意不用黄色，避免与风险色混淆、夸大问题；
- 提示类样式应当并入现有语义（A2：“徽章与提示色并入第 3 节语义色”），不另起一套；
- 只删一个未定义的变量，截图不变，不需要 owner 重新看图。

### 3.7 前端 kickoff §3.3 仍开放的缺口

| 缺口 | 处理 | 依赖 |
| --- | --- | --- |
| 历史初始备份节点（随归档提交上传的原始组态备份，可查看差异、加入比较） | **FE4 不做**（owner 2026-11-10，§10 Q8）。owner 在 FE2 kickoff Q4 决定 FE2 不做，是否需要由 owner 另定。需要时作为后端任务单独立项，再开一个前端阶段接回 | 后端：先确认 FULL 上传的 ① 是否作为可寻址的历史节点保存；History 投影增加该类节点；`POST /v1/history-compares` 接受该类节点。前端不能推断 |
| 首批空基线时禁用上传第 ① 步 | **FE4 不做**（owner 2026-11-10，§10 Q9），保持 FE2 kickoff Q18 的决定：界面不禁用 | 后端：在 History 中提供“基线为空”的事实（`INITIAL` 可以由部署映射带内容）。建议作为独立的小后端任务，不并入 BE-b：它与导航和展示无关，并入会扩大 BE-b 的审核面 |
| surface `diagnostics_summary` 中的自由文本 | **随 FE4b 接入**：owner 2026-11-03 已把它并入 BE-b（草案 §4.10、§6 Q10）。前端 kickoff §9 写的“不属于 BE-b”已过时，由本分支的另一个提交更正 | BE-b §4.10 |

### 3.8 取证工具（FE4a）

FE3 中出现过两类取证错误：FE3b 的 04 证据 handoff（`a300b16485`）有 5 个 SHA 抄错；FE3c 的 wrapper 把 `LOG_DIR` 取成了 `$2`，入口命令没有运行。另外 FE3c 证据核对的 E2 中，wrapper 的两个结果字段显示为 `MISSING`。FE3 的 wrapper 都是临时写在节点上的，没有经过审核。

FE4a 在 `frontend/scripts/` 下提交三个工具，由审核会话审核，FE4a 与 FE4b 的取证都使用它们（第三个截图比较脚本由修订 4 增加，§10 Q14，在 FE4a 的修复轮中实现）：

- **证据 wrapper：**
  - 写日志前检查参数：参数个数；worktree、日志、截图目录都是绝对路径，日志目录已存在，截图目录在 worktree 外。任一不满足即以非 0 退出，不运行入口；
  - 占用标记 `/home/dev/gdds-node-busy.d`，按入口区分：
    - `run-tests.sh`、`validate-upload-package.sh`：由 wrapper 原子 `mkdir` 取得标记，写入会话名、用途与开始 UTC；收尾后只删除本次自己取得的标记；
    - `run-real-backend-e2e.sh`：入口自行取得标记，wrapper 不获取；启动前标记必须不存在，否则入口会 exit 3；
    - 标记已存在时：属于他人的有效标记，等待或退出，不删除、不抢占；用途为计时测量时一律等待；本会话残留的标记（会话名相同、没有对应进程）先按收尾规则确认后再删除，不自动删除；
  - 记录 hostname、起止 UTC、起止 HEAD 与 `HEAD:frontend`、`HEAD:vnext`、起止 `git status --porcelain --untracked-files=all`、开始与结束时的占用标记内容；
  - 用 `set -o pipefail` 取入口自身的 exit code；
  - 写日志的 `.sha256` 旁注文件；
  - 从入口日志按整行取结果字段，取不到时写明原因，不写 `MISSING`。
- **十六进制回源脚本：** 读取 handoff，找出全部十六进制值，逐个与来源对照：节点上现场重算的文件 SHA256、取回的日志与清单原文、git 对象。输出每个值的来源；报告未命中的值与长度不是 7–12、40、64 的值；“路径 + SHA”成对出现时核对配对关系。用 `python3 -I` 运行，只用标准库，不依赖 Node。运行位置：
  - 文件 SHA256 的现场重算必须在该测试节点的宿主机上运行（节点宿主机没有 Node.js，有 python3）；
  - 与 git 对象、取回的日志和清单原文的只读对照可以在开发主机上运行。
- **截图比较脚本（修订 4）：** `frontend/scripts/compare-screenshots.py`，`python3 -I` 运行，只用标准库（`zlib`、`struct`），不依赖 Node 与浏览器，在测试节点宿主机上运行。
  - **输入：** 两个截图目录，按相对路径配对同名 PNG。只接受 Playwright 产生的 8 位、非隔行 RGB/RGBA PNG；其他格式或解码失败以 exit 2 报错，不归入任何类别。
  - **逐文件判定：**
    - 字节相同 →“相同”；
    - 宽或高不同 →“尺寸不同”；只在一侧存在 →“缺失”；
    - 否则逐像素比较全部通道，任一通道值不同的像素为“不同像素”。不同像素不超过 100 个，**且**按 8 邻接计算的最大连通块不超过 16 个像素 →“噪声”；否则 →“内容变化”。
  - **两个上限是脚本中的常量**，不提供命令行或环境变量覆盖。依据见 §15.1：同一前端内容的运行间噪声每张最多 73 个像素、最大连通块 10 个像素；改变一个数字（11 px 字号）就有 41 个像素，但连成一块。只限总数（审核报告的建议）会把一个数字的变化判为噪声，正是 C4 要防的情况。改上限须修订本文并附测量数据。
  - **输出：** 每个不是“相同”的文件一行（相对路径、类别、不同像素数、最大连通块、最大通道差、差异范围），按路径排序；末尾按类别计数。输出可重复：同一输入两次运行结果逐字节相同。
  - **两种模式：**
    - 稳定性模式（`--stable`）：用于同一提交的两次运行。全部文件都是“相同”或“噪声”时 exit 0，否则 exit 1；
    - 比较模式（默认）：用于不同提交之间（§7.3 的 FE3c 到 FE4a）。完成比较即 exit 0，类别只作报告。
  - **自检（`--self-test`）：** 在内存中构造 PNG，覆盖：字节相同；1 个孤立不同像素（噪声）；16 像素连通块（噪声）与 17 像素连通块（内容变化）；101 个分散的不同像素（内容变化）；尺寸不同；缺失；解码器对 5 种 PNG 行过滤类型的处理；非 8 位或隔行输入报错。
  - **节点复验（07，写入 handoff）：** 对审核会话留下的目录（`/home/dev/gdds-fe-shots/` 下的 `fe4a-c4-h`、`fe4a-c4-i`、`fe4a-review/full1`、`fe4a-review/probe-srgb`）以稳定性模式比较 H/I、H/R、R/S，三对都应 exit 0；以比较模式比较 `fe4a-review/fe3c-04-copy` 与 `fe4a-review/full1`，结果应为 30 张内容变化、2 张尺寸不同、7 张噪声，与审核报告 §2.3 的分类一致。设计会话的测量（§15.1）可作对照，不作为脚本的验收依据。

这三个工具只是辅助，不改变证据规则：运行仍由入口脚本完成，审核会话仍独立回源与看图。

### 3.9 不在 FE4 范围

- 历史初始备份节点与首批空基线（§3.7）。
- P6 计时是否包含整包下载（前端 kickoff §9、FE3 kickoff §12 的 DC74 行）：**已关闭（owner 2026-11-10，§10 Q13）**。P6 门槛不含 bundle 下载；t1 与 journeys 的下载耗时和体积继续只报告；Phase 8 如需包含下载的端到端时间再立项。DC74 文档由后端修改，本文不改；后端已在 [S1a 前端交接与 BE-b 第二步设计启动](../backend-vnext/refactoring/formal/plans/p7-s1a-frontend-beb-handoff.md) 中记录“DC74 未生效，随 P6 退出关闭”。
- Phase 7 可能增加的排队状态与统计展示：随 P7 的接口另开前端阶段，不在 FE4。
- 正式 SSO、部署形态、外部驱动通道、深色主题。
- Preview 顶栏的上传快捷入口、历史比较结果抽屉布局、1280 下提交对话框滚动：已接受为 FE2 的偏差（FE2 kickoff Q19）。
- 浏览器中重新解析 SQL、计算来源图或生成时间；FE4b 之后也不在浏览器中计算行标识。
- 在 Preview 中为 `composite_signal_point`、`device` 以外的表补齐改前侧（BE-b §4.8 写明不在范围）。

## 4. BE-b 的前置与排期

| 事项 | 现状 | 决定 | 来源 |
| --- | --- | --- | --- |
| 第二步设计的作者 | 前端 kickoff §10 把“BE-b 设计”列为前端设计会话的职责，§10 末行又写 BE-b 的实施与审核按后端流程另行指定。第一步已由前端设计会话写完 | 第二步由后端设计会话执行：内容是计算位置、缓存（S5 的计算缓存）、计时、golden、Repository/History 侧的注释持久化、Rust 与 Python 解析器的注释捕获，都在后端实现层。前端设计会话参与审核，核对面向前端的部分：Contract 形状与第一步一致、fixture 与 golden 覆盖第一步的规则、§4 第 7 项的变化说明，并答复业务规则问题 | owner 2026-11-10（§10 Q4） |
| 第二步的时间与基础 | 草案定的时点（“S5 接近完成”）已过 | S1a 本地退出并合入 main 之后由后端开始，以 S1a 的实际实现与退出交接为基础。取代修订 1 的“现在可以开始，以 S1a 的目标 Contract 为基础” | owner 2026-11-10（§10 Q5） |
| 实施与审核会话、排期 | 无 | 按后端流程处理，本文只记录前端的依赖。前端的要求只有一条：实施与审核不由前端会话承担 | 后端流程 |
| 与 P7 的先后 | P7 S0 已收口，S1a 编码已获授权；S1a 改 `artifact_id` 格式、bundle 交付与 surface/bundle 摘要（§2.3） | FE4a 与 S1a 并行；S1a 本地退出并合入 main 之后依次是 BE-b 第二步设计、BE-b 实施；FE4b 在 BE-b 退出之后 | owner 2026-11-10（§10 Q5） |
| 范围 | 草案 §4.1–§4.10 与 §5 的约束 | 不拆。FE4b 需要全部内容；行定位、视图 ID 与稳定编码都会改变摘要，分开做会多改几次 golden | 后端设计会话在第二步中确认 |

FE4b 接入的后端树会同时带有 S1a 与 BE-b 的改动。S1a 改变 `artifact_id` 格式与 bundle 交付，前端的 bundle 解析、互通 fixture 与生成器都可能受影响，而这些变化在 OpenAPI 中看不出来。因此下面的交付清单要求把两者的变化分开说明。后端已把 S1a 一侧写成 S1a 退出的交接要求（[S1a 前端交接与 BE-b 第二步设计启动](../backend-vnext/refactoring/formal/plans/p7-s1a-frontend-beb-handoff.md)，以及 `p7-s1a-execution-plan.md` 的 owner 补充）：以实际候选与证据说明规范化 OpenAPI、bundle tar 成员的 `logical_path` 集合与 manifest 字段集合不变，并逐项列出改变的 ID 与摘要取值及其传递影响。FE4b 第 2 步以该交接与 BE-b 的交付一起核对第 7 项。

**与后端记录一致：** 后端已按 owner 2026-11-10 的更正更新记录（`e2eaab4db9`：`p7-s1a-execution-plan.md` 与 [S1a 前端交接与 BE-b 第二步设计启动](../backend-vnext/refactoring/formal/plans/p7-s1a-frontend-beb-handoff.md) 均改为“BE-b 第二步设计在 S1a 本地 exit 并合入 main 之后由后端开始，随后实施”），与本文一致。

**FE4b 需要 BE-b 交付的内容（写进 BE-b 第二步的交付清单）：**

1. Contract：Business Navigation v1（含诊断产物）；Comparison Surface 修订（`projection_kind`、`SurfaceColumn.pinned`、`display_order`、`row_locator_ref`、视图 ID 规则）；Comparison Bundle 修订（Preview 双侧浏览表的闭包规则）；草案 §7 所列过时文档的替换。
2. golden：导航、导航诊断、行定位、surface 与 bundle。
3. 一个能在后端镜像中生成前端 fixture 的入口（现有 `frontend/scripts/generate-backend-bundle-fixture(s)` 调用的后端能力随之产出真实导航），或者明确的调用方式。
4. 合入 main 的提交、`vnext/` 树与退出 tag；依赖镜像 tag 与身份（依赖输入有变化时，按 AGENTS 在 CT201 构建并预填充）。
5. 该树的生产 OpenAPI 原件。
6. §4.10 稳定编码的完整列表，标明取代了哪些旧条目。
7. 相对 `6368c9c40c`（FE3c 的被测树）的变化说明，**S1a 与 BE-b 的变化分开列**：
   - OpenAPI 规范化后的差异（按 FE3 kickoff §5.1 规范化；没有差异时写明）；
   - bundle tar 成员的 `logical_path` 集合的变化；
   - manifest 字段集合的变化；
   - ArtifactRef（`artifact_id` 格式等）与 surface 的变化；
   - 重新生成的互通 fixture：`frontend/src/test/fixtures/source/backend/` 下由后端生成的 bundle fixture，含摘要互通用的 `pairs/initial_to_modified_fixture_for_backend_digest_cross_implementation`，以及生成它们的上传输入与命令。

## 5. 阶段安排

### 5.1 是否拆段

**拆（owner 2026-11-10，§10 Q1）。** 理由：

- 按 owner 2026-11-10 的决定，BE-b 第二步设计与实施都排在 P7 S1a 本地退出并合入 main 之后，FE4b 还要再等 BE-b，可能需要数周；带入项、Q21 与令牌现在就能做，等待只会让上下文变旧；
- FE4a 在 P6 退出的 backend 树上重跑真实旅程与 t1，前端与新后端的组合尽早得到验证；之后 FE4b 的问题只剩 BE-b 本身；
- 两段改的地方基本不重叠：FE4a 改归档对话框、续做提示、诊断文案与测试；FE4b 改导航、表格列、行定位与 fixture；
- 代价：多一次审核与一次取证。按 DC98，取证只跑受影响的项（§7.2）。

### 5.2 子阶段

| 子阶段 | 内容 | 前置条件 | 退出 tag | 审核范围 | 退出条件 |
| --- | --- | --- | --- | --- | --- |
| FE4a 带入项与新后端回归 | `fe-vnext` 快进到 main `16ffe72829`（§6.1）；§3.4 C1–C12；§3.5 Q21；§3.6 令牌；§3.8 取证工具；在 `t1.spec.ts` 中加入不依赖 BE-b 的参考截图（§3.3）；在 `vnext/` 树 `49c1de43be` 上跑真实 e2e 与 t1（次数按 §7.2） | 本文经定向复核；审核会话按 §11.1 标题重核分支与 tag、现场核对节点、镜像与 `--print-input` 后发出提示词 | `fe-fe4a-exit` | `fe-fe3c-exit..<FE4a 候选>` | 审核通过；证据（§7.2 FE4a 证据行）各一次通过；C4 的三次稳定性比较（§7.3）都通过；§7.3 看图清单中的截图经 owner 确认。不含依赖 BE-b 的页面 |
| FE4b BE-b 接入与正式重拍 | §3.1 B1–B9；§3.2 侧栏；§3.3 正式重拍（含依赖 BE-b 的页面）；按 BE-b 交付合入 main、刷新 OpenAPI 与 fixture；FE4 退出 | `fe-fe4a-exit`；P7 S1a 本地退出并合入 main 之后，BE-b 完成第二步设计与实施、退出并合入 main，§4 的交付齐全；本文第 2 步（FE4b 设计）经审核与 owner 确认 | `fe-fe4b-exit`（即 FE4 退出） | `fe-fe4a-exit..<FE4b 候选>` | 审核通过；证据（§7.2 FE4b 行）各一次通过；正式重拍与 FE4b 截图经 owner 确认 |

- 两段都在 `fe-vnext` 上进行，合入 main 只用快进或合并，不 rebase，不改写已被引用的提交。
- **路径核对（每段都做）：** 设 `<main>` 为最后一次进入 `fe-vnext` 的 main 提交：
  - `git rev-parse <候选>:vnext` 与 `git rev-parse <main>:vnext` 相等；
  - `git diff --name-only <main> <候选>` 只含 `frontend/` 与 `docs/frontend-vnext/` 下的路径。
- 审核范围中来自 main 的文档与 `vnext/` 不属于前端审核，由后端审核负责。main 上直接提交的 `frontend/` 改动属于前端审核范围（目前没有）。
- FE4a 期间不合入 main（owner 2026-11-10 已决定，§10 Q2）。P7 S1a 在 main 上改 `vnext/` 不影响 FE4a，被测后端固定为 `16ffe72829`；需要偏离时停下交 owner，实施与审核会话都不自行合入。
- FE4b 的合入点、依赖镜像与比对原件在第 2 步写定。

### 5.3 FE4b 的第 2 步

BE-b 第二步与 Contract 固定后，前端设计会话修订本文。修订 5 按第二步候选 `b61cc37d5f` 与前端窄复核（`GO_WITH_NONBLOCKING`，§13.6）先写定下列各项；后端 B0 落 Contract 或 B4 交付时如有出入，以正式 Contract 为准重新同步。

**fixture 的重新生成（第二步 §8，FE-BEB-10、11）：**

- **生成入口：** 后端入口 `vnext/scripts/generate-presentation-fixtures.py --input-root <绝对路径> --output-root <外部空目录>`。在专用测试节点的 clean、已提交 worktree 中，以后端 uv 环境调用（完整命令见第二步 §8）。
- **wrapper：** 前端 `generate-backend-bundle-fixture(s)` 改为只用 subprocess 调这个入口，并把 `<output>/backend/` 整体替换到 `frontend/src/test/fixtures/source/backend/`，不再导入后端私有符号。
- **上传输入：** 由后端持有，位于 `vnext/fixtures/presentation-inputs/` 与 `manifest.json`，从 FE4a 核对基线 `59c5b8cfca` 的 `frontend/src/test/fixtures/source/upload-inputs/` 原字节复制。前端模拟数据所用副本逐文件按清单 SHA256 核对。
- **目录清单：** 输出须覆盖下列目录，缺项即失败：
  - `fe2a/{preview-full,preview-modified-only,preview-replacement,history-three-nodes}`、`fe2b/preview-workbench-normal`；
  - `pairs/…`，以及 `source/backend/` 顶层的 `manifest.json`、`artifact-closure.json`（`build-golden-bundle-fixture.mjs` 读取）；
  - 第二步 §8 列出的新增场景。
  - `fe2a/preview-no-navigation` 退役，不生成（B9）。
- **删除：**
  - `src/test/fixtures/source/business-navigation.json`、`business-navigation-workbench.json`、`navigation-diagnostics.json`；
  - 各 fixture 下手写的 `projections/business-navigation*`；
  - `fallbackNavigation` 及其测试。
- **确定性：** 同一输入在同一版本重复生成，结果逐字节相同。fixture 用的 ID 固定方式由后端记录，前端不改写生成产物。

**模拟数据规则：** 只构造后端可达的组合，规则同 FE2 kickoff §7.5。解码器按下列不变量严格校验，模拟数据不得违反：
- `replacement_sides != null` ⇔ `comparison_mode == DATASET_REPLACEMENT` ⇔ `groups == []`；
- 每个 surface 恰好一个 `BUSINESS_NAVIGATION` projection；
- B1 的三条唯一性；
- 某表筛选页签全为 `TABLE_FALLBACK` ⇔ 该表有 `DEVICE_TAB_FACTS_UNAVAILABLE`；
- `table_ref` 为 null ⇔ 对应 `table_content_bindings` 为 null；
- surface 中 ArtifactRef 的 `raw_sha256`/`size_bytes` 等于同一 `artifact_id` 的 closure 条目；
- 有快照侧的 locator context 为 null。

浏览器不重算 `surface_digest`，surface 摘要由后端 golden 负责（第二步 §6，FE-BEB-04）。

**程序判据（t1，在两种宽度的截图运行中同时断言；FE-BEB-03）：**

1. **导航形状：** 每个比较对恰好一份导航；普通模式固定五组；B1 的三条唯一性成立。
2. **不可见的表：** 不出现在任何页签中的 surface 表，都满足：
   - bundle 中有绑定的各侧 `table_content_bindings.row_count` 为 0；
   - surface `change_kind` ∈ {`UNCHANGED`, `BUSINESS_EQUIVALENT`}；
   - `RiskReport` 中该表无风险。
   不再要求“每张表都出现在可见页签中”。
3. **按侧覆盖（不藏行）：** 对每张有筛选页签的共享表，只核 bundle 有该侧快照、且该表筛选页签为 `EXACT` 的一侧。该侧全部已发布谓词覆盖的行集合（取并集，不能把各页签计数相加）的大小，加上同侧 `DEVICE_ROWS_UNASSIGNED.row_count`，等于该侧行数。缺快照侧由后端 Contract 测试负责。
4. **行定位：** 有 `row_locator_ref` 的表全部定位：
   - 每条行级记录在有快照侧的 index 处命中恰好一行；
   - 缺快照侧的 context 合规；
   - 没有出现表级回退。
   回退的表数与 `TABLE_FALLBACK` 页签数只报告。

**截图分工：** 截图名在本文第 2 步定稿时列出。
- **t1 真实数据，1280 与 1920：** 导航分组与页签、表级标记、中文列名与固定列、行定位后的变更行；
- **后端确定性 fixture 加模拟接口 e2e，同样两种宽度：**
  - Preview 改前公式与改前侧装置名（t1 的 `composite_changed=0`，只能在这里覆盖）；
  - gid 变化与重复地址；
  - 本侧孤儿与“查看整表”；
  - `TABLE_FALLBACK` 与 `table_scope`；
  - 只在改前侧存在的列；
  - keyless 删除行的“改前值不可得”；
  - replacement 分侧；
  - `DEVICE_FILTER_VALUE_UNSUPPORTED` 整表项；
  - 仅注释 Preview，以及提交得到 `NO_CANONICAL_CHANGE` 时的说明：“注释变化未单独保存，将随下一次业务变化一起保存”。
- 前端不重复 t4 的后端导航验证。

**合入点：** BE-b 退出并合入后的 main，同时带有 S1a 与 BE-b。路径核对同 §5.2。具体提交、`vnext/` 树、依赖镜像，在 BE-b 交付后写定。

**仍待 BE-b 交付后写定：**
- 合入提交与依赖镜像；
- OpenAPI 刷新与比对原件；
- 按 §4 第 7 项的变化说明（S1a 与 BE-b 分栏），确认 bundle 解析、互通 fixture 与生成器要改的地方；
- 依赖 BE-b 的页面截图名与 owner 看图项（§3.3）；
- FE4b 的实施与审核提示词；
- 核对后端已按 FE-BEB-11–13 修订第二步与 Contract。

FE4b 的设计期间若发现 BE-b 的 Contract 与第一步或第二步不一致，交 owner 转后端，前端不自行假设。

## 6. 合入点与后端变化

### 6.1 FE4a：快进到 main `16ffe72829`

- `fe-vnext` 当前 `e22e39ba15` 是 `16ffe72829` 的祖先，直接快进，没有合并提交：
  - 包含 `fe-fe3c-exit` 的目标 `06b454b0ef`（FE3c 证据 handoff）与 main 合入提交 `475022300c`；
  - `vnext/` 树变为 `49c1de43be`，与 `p6-exit` 的目标 `b0fc25e881` 相同。
- **为什么是这个提交（owner 2026-11-10 已决定，§10 Q2）：**
  - 它是 FE3 退出记录，`vnext/` 等于 P6 退出验证过的树，且不带 P7 文档，路径核对更简单；
  - 用 tag `p6-exit` 的目标 `b0fc25e881` 不行：它不含 FE3c 的合入，快进不到；
  - 新建分支没有好处：前端 kickoff §7 的流程以 `fe-vnext` 为唯一长期分支，快进不改写任何提交。
- **不合入之后的 main：** 本地 main 之后已合入 P7 S1a 的设计与 Contract 目标补充（§2.2），S1a 编码已获授权，随时可能带入 `vnext/` 改动。FE4a 与 S1a 并行，期间不合入 main。
- **推送（owner 2026-11-10 已决定，§10 Q12）：** `16ffe72829` 已在远端，且包含 `b0fc25e881`，FE4a 的被测提交与 `vnext/` 树不依赖任何未推送的对象，FE4a 开始前不需要推送。`p6-exit` 这个 tag 本身未推送，不影响 FE4a。
- **审核会话发提示词前重核（§11.1）：** `fe-vnext` 仍为 `e22e39ba15`；`p6-exit` 仍指向 `b0fc25e881`，其 `vnext/` 为 `49c1de43be`；记录 main 当前的头与 `vnext/` 树。合入点不随 main 改变。
- **审核范围的说明：** `fe-fe3c-exit..<FE4a 候选>` 会包含 S5、S6 的全部后端提交，按 §5.2 不属于前端审核；`16ffe72829:frontend` 与 tag 相同，范围内的前端改动全部来自 FE4a。

### 6.2 `6368c9c40c..49c1de43be` 对前端的影响

方法同 FE3 kickoff §15.5 第 9 项：按前端能看到的几类，读 `git diff fd9e383d76 16ffe72829 -- vnext` 逐类核对。设计会话只读源码，没有运行产品。

| 类别 | 核对 | 结论 |
| --- | --- | --- |
| OpenAPI、HTTP DTO、错误码 | `backend/src/gateway_backend/http/` 下没有任何改动（含 `schemas/`、`errors.py` 与路由）；`application/workspace/`（上传上限）、`settings.py`、`app.py`、`deploy/` 未改。**导入闭包（审核会话补核）：** `http/routes/` 与 `http/schemas/` 导入的非 `http` 模块都不在改动集合中；整个 `http/` 导入的非 `http` 模块中只有 `application/history/compare_jobs.py` 与 `application/submission/ports.py` 改了，前者被 `http/orchestration/history_compare.py` 使用的三个符号逐字不变，后者只给 Protocol 加了一个方法，不是 schema | 无变化。预期运行时 `/openapi.json` 规范化后与现有快照逐字节相同 |
| bundle、manifest、closure、tar | `capabilities/bundle_assembly/`、`capabilities/surface_assembly/`、`domain/`、`vnext/fixtures/`（含全部 golden）未改；`artifacts/` 只改了 `computation_cache.py`（新增）、`snapshot_table_export_cache.py` 两个缓存文件 | 无变化。S5 的计算缓存只是复用已有结果，不改变产物字节 |
| surface 与比较、风险的取值 | `capabilities/comparison/` 6 个文件（3 个新增）、`risk_evaluation/` 4 个（2 个新增）、`snapshot_materialization/` 5 个；Rust 的 `comparison/mod.rs`、`lib.rs`、`records.rs`、`records/{builders,cache,facts}.rs` 与 `gateway-compute-python/src/comparison_records.rs`：都是缓存编解码、任务身份、持久化与快照导出缓存。diff 中出现的大写编码都是已有取值（记录族、变化类型、有序事件等），以及从旧位置原样搬移的 `ORDERED_PROVENANCE_MISSING`、`ORDERED_PROVENANCE_INVALID`。新增的 `ValueError("row_diff_detail_policy is invalid")` 是缓存任务的内部校验，即使写入诊断，也只会以异常类名出现，归入“内部错误” | 无新的诊断码。§3.5 的文案表适用于 `49c1de43be` |
| operation 与 checkpoint | `application/` 下 `history/compare_jobs.py`、`preview_jobs.py`、`pair_pipeline.py`、`canonical_metadata/table_access.py`、`submission/{finalize_transaction,ports}.py`，`bootstrap/operation_worker.py`，`infrastructure/control_db/` 6 个（1 个新增）、`infrastructure/repository_read/` 2 个：缓存接线、精确提交的校验与按需读取。`CHECKPOINT_JOB_STATE_MISMATCH` 在 `6368c9c40c` 中已有，是内部恢复码，不经 HTTP DTO 返回给前端。**History 比较的 assemble 步骤**改为按需读取行，新增两类终态失败：`HistoryCompareInputError`（`CommitCanonicalMetadataError` 的码或 `HISTORY_COMMIT_UNAVAILABLE`）与不可重试的 `RepositoryProviderError`（以其 `code.value` 作为诊断码）。因此 `HistoryCompareResultResponse.diagnostic.code` 在 assemble 阶段的可达取值扩大了 | 无渲染影响：前端只显示 `diagnostic.message`，不按码映射；模拟数据可达表只列 `HISTORY_RULESET_VERSION_MISMATCH`，仍是可达取值的子集。真实旅程中若出现，按本节末条在 handoff 中列出 |
| `repository_client` | `repository_client/src/` 5 个文件（`arrow_stream`、`client`、`deadline`、`errors`、`retry`）：请求改为受调用方期限约束 | 不经 HTTP DTO 暴露给前端；对前端的影响只能由真实旅程验证，这是 FE4a 在新树上重跑的理由之一 |
| 依赖与镜像 | 五个依赖输入文件、`repository_service/uv.lock`、两个 backend Dockerfile、`vnext/scripts` 都未改 | 依赖镜像预期仍为 `lock-578e079b762e`，RS 为 `lock-6dc9659f0aee`；以现场 `--print-input` 为准 |

另有 24 个测试文件（按路径计；审核报告把 `tests/test_control_db_schema.py` 计入 control DB，记为 7 与 23，总数同为 72）与 `benchmarks/` 的 4 个文件（2 个新增），不影响前端。`repository_service/`、`vnext/scripts/` 与两个 backend Dockerfile 都没有改。

- `real_dump_journey.py` 在 `benchmarks/` 下有改动（S6 的 t4 W1/W2 范围）。t1 的预期值仍按 FE3 kickoff §8.3，在运行时从被测树读取模块级常量 `S2B_DATASET_BASELINE` 与 `S1B_V2_PREVIEW_CHANGED_COUNTS`；读不到即停止。设计会话已用 `git grep` 确认两者在 `16ffe72829:vnext/backend/benchmarks/real_dump_journey.py` 中仍是模块级常量（第 192、234 行）；审核会话发提示词前再用只读 `git grep` 重核一次（§11.1）。
- FE4a 真实旅程中若出现上表没有预期的诊断码，在 handoff 中列出编码与出现位置，不作为停止条件（同 FE3 kickoff §2.3 末段）。

### 6.3 OpenAPI 快照与比对原件

- **FE4a 不刷新快照。** 依据 §6.2 第 1 行。
- **比对原件（owner 2026-11-10，§10 Q3）：** FE4a 不要求后端为 `49c1de43be` 交付新的生产 OpenAPI 原件。每次真实运行照常在浏览器用例之前，把运行时 `/openapi.json` 与已提交的快照按 FE3 kickoff §5.1 规范化后逐字节比较；不一致即停止，不在 FE4a 中刷新，交设计会话，由 owner 转后端交付该树的原件后再定。理由：
  - FE3 要求原件，是因为要用它刷新快照，原件是快照的独立来源；FE4a 不刷新，快照的来源仍是 `6368c9c40c` 的原件；
  - `http/` 一行未改；
  - 运行时比对本身能发现任何 schema 变化。
- **FE4b：** BE-b 交付的树的原件与变化说明由 BE-b 的后端交付方提供（§4 第 5、7 项），按 FE3 kickoff §5.1、§5.2 刷新与比对。

### 6.4 合入 main

- **FE4a 退出：** 附注 tag `fe-fe4a-exit` 指向 FE4a 证据 handoff。先把审核报告合入本地 main，再以 `--no-ff` 合入 tag。main 届时可能已有 P7 的文档或代码；FE4a 只改 `frontend/` 与 `docs/frontend-vnext/`，预期没有冲突，由审核会话先试合并。
- **FE4a 的推送（owner 2026-11-10 已决定，§10 Q12）：** 退出时推送 tag `fe-fe4a-exit`。main 是否推送随后端的推送节奏由 owner 决定；届时 main 会带上 P7 的内容。
- **FE4b 退出（FE4 退出）：** 同样流程，tag `fe-fe4b-exit`；推送在第 2 步写定。
- tag 与合入由设计会话在 owner 确认后执行；推送只按 owner 的决定或授权执行。

## 7. 测试与证据

### 7.1 节点

- **规则：** 按 DC91 与 AGENTS main 的五节点池，选合格空闲节点，不在开发主机上运行。“合格”指本次工具链、npm 缓存、依赖镜像、RS 依赖镜像与所需输入都已在该节点上，并按身份核对一致。
- **建议：** 沿用 FE3c 已就绪的节点，减少预填充。这只是建议，不是固定用途：
  - 模拟接口各项的调试：07（或 04、05）；
  - 真实 backend 与 t1 的调试：05；
  - 证据：模拟接口全量、上传包校验与真实旅程在 04，t1 在 05。
- 改用其他池内节点时，先按 DC67 预填充，handoff 记录来源、摘要与预填充时间。t1 目录要整目录传输，并按 FE3a 清单逐文件核对。
- **占用：** 所有运行都取原子占用标记；会话名按角色与子阶段写，例如 `fe4a-impl`、`fe4a-review`。真实 backend 入口自行获取标记，外层不重复获取。用途为计时测量的标记存在时，该节点上的任何前端运行都要等待。
- 同一节点整机单飞。不同节点可以并行，例如 04 上的模拟接口全量与 05 上的 t1。

### 7.2 证据项

真实数据的次数由 owner 2026-11-10 按 DC33、DC98 决定（§10 Q11）。

| 子阶段 | 内容 | 性质 |
| --- | --- | --- |
| FE4a 调试（实施会话） | 受影响的单测与模拟接口用例（focused）；送审前跑一次模拟接口全量 `run-tests.sh --e2e --screenshots`（`GATEWAY_FE_TEST_WORKERS=2`），产生交 owner 看图的截图（修订 4：修复轮在最终修复候选上同一节点连续跑两次，作为 §7.3 的第 ① 次稳定性比较）；`run-real-backend-e2e.sh --suite journeys` 只跑 C7 改到的 J1、J2（`j1-archive-mainline`、`j2-manual-close` 两个 scope），按需；`--suite t1` **一次**（因在 `t1.spec.ts` 中加入参考截图，§3.3）。`validate-upload-package.sh` 不在调试中跑：FE4a 不改上传包与校验 | 调试；通过后送审 |
| FE4a 审核（审核会话） | 模拟接口全量 `run-tests.sh --e2e --screenshots` 一次与探针（§11.2）；**不独立跑真实旅程与 t1**，改为核对实施会话的调试日志 | 审核 |
| FE4a fix4 调试与复审（修订 6，§16） | 实施会话：07 上 `run-tests.sh`（不带 `--e2e`）一次；05 上 `--suite journeys --subphase fe3c` 完整集调试**一次**；不跑模拟接口全量与 t1。审核会话：helper 区分力探针（模拟接口）、07 上模拟接口全量一次并与复审第 3 轮 `full1` 做稳定性比较、核对 05 调试日志；不独立跑真实旅程与 t1 | 调试与审核（owner 2026-11-11，§10 Q18） |
| FE4a 证据 | 审核通过后，在最终候选的 clean、已提交 detached worktree 上各运行一次：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`--suite journeys`（完整集 20 个 scope）、`--suite t1`。审核会话随后核对证据日志。修订 6：`59c5b8cfca` 上的证据运行停止，四项在 fix4 候选上各重跑一次（§16.5，§10 Q19） | 证据；耗时只报告 |
| FE4b | t1 证据运行一次，同时产生正式重拍截图（§3.3）；调试按需，在第 2 步写定。`journeys` 与 `t1` 加入导航、列与行定位的程序判据（第 2 步） | 第 2 步写定 |

- 调试与取证分开（DC30）：调试只跑 focused 与受影响的真实数据段；证据只在审核通过后运行。
- **只跑 J1、J2 需要改入口：** `run-real-backend-e2e.sh` 现在只能用 `--subphase fe3b`（18 个 scope）或 `fe3c`（完整集 20 个）选择范围，不能只选 J1、J2。FE4a 在入口中加一个只运行这两个 scope 的调试选择，并让入口接受 FE4a 的子阶段名；具体形式由实施会话定，审核会话审核。证据运行不带该选择，跑完整集。
- FE4a 证据仍跑四项各一次：前端没有沿用机制，`frontend/` 树变了，模拟接口全量必须重跑；backend 树也变了，`journeys`、`t1` 与上传包校验要在新树上各跑一次。
- **两段共同：** 只报告 t1 第 1 步 MODIFIED_ONLY 的 renderer 增量；不做计时，不用 t2–t4；打包流程没改就不跑 t4（§7.4）。不另加重复采样或性能测量（DC98）。
- **t1 调试只有一次：** 需要第二次 t1 调试运行时（例如第一次失败，或之后又改了 `t1.spec.ts`），停下交设计会话，由 owner 决定，不自行追加。失败属于 DC68 的工具或取证错误时，按下条处理。在新候选上重跑的 t1 证据不计为调试运行（修订 6，§16.5）。
- **失败与重做：** 按 AGENTS（main）“专用测试节点”的 DC68，原文如下：

  > **DC68 工具/取证错误（Owner 2026-11-08 修订）：**首次失败后，同一具体故障允许最多三轮自行修复、适用独审与受影响步骤复验；不因被测对象已经运行就立即交 owner。每轮先停止该次执行、保留原始失败及日志/SHA、确认收尾，再固定修订稿复验；三轮仍未解决、原因/副作用不明或超出既有授权时交 owner。不得无修改自动重试、改预期掩盖结果或跳过身份/缓存前提；产品 finding 按阶段已有修复与停止规则办理。只读后处理/预检、代码传输准备的不计次数澄清继续适用。

  细则见 testing-conventions 的 DC68 现行规则。产品问题按本文 §8 与审核流程处理，不按 DC68 重做。

### 7.3 截图

修订 4 改写本节（§10 Q14、Q16）。截图之间的比较一律用 §3.8 的截图比较脚本，不再按逐字节相同判定“有无变化”：逐字节不同而判为“噪声”的文件不算变化，只报告计数。

- **模拟接口：** `run-tests.sh --screenshots` 的全量截图照常生成（1280、1920）。C4 之后，等待时长固定。
- **C4 稳定性比较（稳定性模式，三次都要通过）：**
  1. **实施会话（修复轮）：** 在最终修复候选上、同一节点连续两次模拟接口全量（`GATEWAY_FE_TEST_WORKERS=2`，经 wrapper），两次的截图相互比较；
  2. **审核会话（复审）：** 复审时独立运行的模拟接口全量，与实施会话在同一提交、同一节点上的第 ① 次运行比较；
  3. **证据：** 04 证据运行的截图与复审通过的候选在 07 上的截图比较（两者 `frontend/` 树必须相同）。审核报告 §2.3 中 04 的 FE3c 证据截图与 07 的运行之间，未改动页面的差异与同节点噪声同量级，跨节点比较可行；不通过时按 §8 停止。

  每次比较的两个截图目录、清单 SHA256、脚本输出与 exit code 写入对应的 handoff 或审核报告。判为“噪声”的文件只报告计数与最大值，不逐个解释。
- **FE3c 到 FE4a 的变化清单（比较模式）：** 把 FE3c 证据截图（04 `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/`，清单 SHA256 `63a0e6006952152e7cd59db22ada9b34e4774f4f99676c22041b31f9ea1129f2`）与最终修复候选的模拟接口全量截图比较。实施会话在 fix handoff 中列出全部“内容变化”“尺寸不同”与“缺失”的文件并按原因分组（可直接引用审核报告 §2.3 的分类）；审核会话复审时用同一脚本复核，确认每个文件都有对应的改动或由 C4 引起。
- **FE4a 交 owner 看图的范围：**
  - 上一条清单中的**全部文件**，按原因分组。按审核报告 §2.3，至少包括：C3 的 `fe3b-w6-*` 与另外 10 张（`fe3b-w10-stale-preview`、`fe3b-w4-approved-withdraw`、`fe3b-withdraw-forbidden`、`fe3b-withdraw-unknown`、`bundle-error`、`loading-skeleton`）；C4 固定时长与截图 helper 引起的文件（其中 `1920/fe3b-withdraw-enabled`、`1920/fe3c-many-first` 是 FE3c 拍到了中间状态，FE4a 为正常状态）；C9 的 `fe3c-close-dialog`、`fe3c-close-result`；C5 的 `fe3c-review-closed`。C12 改动后，D1–D3 的 `fe3b-d*-review-topbar`、V11 的 `fe3c-review-expired` 与其他出现相同禁用原因的审核顶栏也会进入清单；
  - FE3c 没有对应截图的新状态（1280、1920）：C6 归档卡片的长理由折叠与展开、详情面板长关闭理由折叠（审核报告 F2）；C8 冲突提示与集合变化提示同时出现（F5）；
  - C8 的冲突提示由 FE3c 的红色 `.form-error` 改为灰色 `.form-warning`，设计会话同意（§15.3），随上面的 C8 截图由 owner 确认；
  - C4 之后显示固定等待时长的截图，抽一张确认文字；
  - owner 看复审通过的候选在 07 上的截图（handoff 记录路径与 SHA256）；证据运行的截图由第 ③ 次稳定性比较与之绑定，不另看。
- **真实 backend 与 t1：** FE4a 的 t1 参考截图（§3.3 的页面与截图名）只留在节点上，SHA256 写入 handoff，不作验收，审核会话只核对 SHA256 与文件名是否齐全；FE4b 的 t1 正式重拍交 owner 看图（§3.3）。
- **对照依据：** 审核会话对照 `sketches/` 与 UI 优化方向核对布局、层级、语义色、按钮层级、禁用原因与焦点样式，不做像素级比对。
- **FE4b：** 模拟接口截图的比较沿用同一脚本、同一上限与同样的三次稳定性比较；FE4a 到 FE4b 的变化清单以 FE4a 证据截图为比较原件，具体在第 2 步写定。真实 backend 的 t1 截图不用该脚本判定（数据与时间不固定），按 §3.3 看图。

### 7.4 t1 与 M1

- **t1：** FE4a、FE4b 都跑（次数按 §7.2）：backend 树（FE4a 为 `49c1de43be`，FE4b 为 BE-b 的树）与前端都有变化。步骤、判据与输入核对按 FE3 kickoff §8.1–§8.3：两份清单逐文件核对，预期值从被测树读取，FULL 的两个比较对按 `pair_id` 取用，`baseline_to_initial.table_count` 记录实际值。
- **M1（FE3 kickoff §8.4；owner 2026-11-10 决定的范围，§10 Q11）：**
  - 两段都只报告 t1 第 1 步 MODIFIED_ONLY 的 renderer 增量，与 FE3a t1 v1 的 24.86 MiB 并列；超过 2 倍时在 handoff 中标出，交设计会话；
  - 第 4 步 FULL 不再报告（FE3 的“只报告、不可比较”一项取消）；
  - 不做计时，不用 t2–t4。
- **t4 重测只在打包流程改变时触发：** 在有 `t4-v1` 目录的节点上用新浏览器重测 t4 v1 的 MODIFIED_ONLY 与 FULL，各 3 次，按 FE3 kickoff §8.4 的标准判定。FE4a 与 FE4b 都不计划改打包流程。判断分两步：
  1. **筛查：** 审核会话运行 `git diff --stat <范围起点>..<候选> -- frontend/src/features/workbench/upload-package.ts frontend/src/features/workbench/UploadStepCard.tsx`。为空则不触发；
  2. **判断：** 非空时，审核会话读 diff，判断打包流程是否改变：`upload-package.ts` 中的 `collectLocalDirectory`、`buildTar`、`buildSourcePackage`，或 `UploadStepCard.tsx` 中打包阶段的代码（从 `begin("packaging")` 到下一阶段开始）。只有这些改变时才触发 t4 重测。例如 C1 若在上传开始处清除续做提示而改到 `UploadStepCard.tsx`，不触发。
- **打包代码的位置：** 在 `features/workbench/upload-package.ts` 与调用它的 `features/workbench/UploadStepCard.tsx`。FE3 kickoff §8.4 与 §11 Q23 理由 ② 写的 `features/upload/` 在仓库中不存在。按实际路径复核：`fe-fe3b-exit..fe-fe3c-exit` 中两个文件都没有改动，Q23 理由 ② 的结论成立，FE4 不需要补测；`fe-fe3a-exit..fe-fe3b-exit` 中只有 `087281ce65` 改了 `UploadStepCard.tsx`，内容是给按钮加禁用原因，不涉及打包流程。

### 7.5 日志与回源

- 日志、截图与 trace 写在 worktree 外的证据目录。
- **wrapper：** 证据运行一律经 §3.8 的 wrapper 启动，不在终端里临时拼命令。FE4a 的工具提交并通过审核之前，调试运行可以用临时 wrapper，但也要先检查参数。
- **handoff：**
  - 记录每次运行的节点、hostname、起止 UTC、起止 HEAD、`frontend/` 与 `vnext/` 树、exit code、日志 SHA256；
  - 记录工具链、npm 缓存、依赖镜像与 RS 镜像的身份；
  - 提交前用 §3.8 的回源脚本逐个核对文中的十六进制值，并在 handoff 末尾附核对结果：命中数、未命中值及原因、长度不是 7–12、40、64 的值。
- trace、Compose 日志与 t1 截图只留在节点上，handoff 只记路径与 SHA256（FE3 kickoff §4.9）。

## 8. 停止条件

除 AGENTS、前端 kickoff、FE2 kickoff §10 与 FE3 kickoff §10 中仍适用的规则外：

**FE4a：**

- 快进失败；候选的 `vnext/` 树不是 `49c1de43be`；路径核对出现 `frontend/`、`docs/frontend-vnext/` 以外的路径；
- `--print-input` 与提示词中审核会话填写的 tag 不符；依赖镜像、RS 依赖镜像、工具链或 npm 缓存缺失，或身份不符；构建需要访问网络；
- 运行时 `/openapi.json` 与快照规范化后不同（§6.3 甲）；
- 真实旅程发现后端缺陷，或 J1、J2 某次预检的异常集合与 FE3 kickoff §4.6 的表不符：保留日志与 trace，交设计会话；判断为后端问题时由 owner 转后端，不在前端绕过，不改 `vnext/`；
- t1 输入核对不符，或 §8.3 的预期值读不到、实测不符；
- 需要第二次 t1 调试运行（§7.2），或需要在调试中跑 J1、J2 以外的真实旅程（修订 6、修订 7 授权的 fix4 完整集调试除外，§16.3、§17.3）；
- fix4 的完整集调试有 scope 失败，或需要超出 §17.3 授权的完整集调试：保留日志、trace 与截图，交设计会话（§16.3、§17.3）；
- fix4 复审中 07 模拟接口全量与复审第 3 轮 `full1` 的稳定性比较不通过（§16.4）；
- 打包流程按 §7.4 判断为改变，但 t4 重测不能在同一阶段完成；
- 需要后端新增字段或接口，或需要修改 `vnext/` 下的 Compose、脚本或配置；
- C1–C12 的修改需要改变 FE3 kickoff 已定的业务规则（例如 §16 的接受、撤销、关闭规则）：停下交设计会话；
- C4 的稳定性比较（§7.3）不通过，且原因不是被测提交的缺陷（例如差异看上去是渲染噪声、只是超出上限）：保留两次运行的截图与比较输出，停下交设计会话，不改上限、不重跑到通过为止；
- 证据运行的截图与复审通过的候选截图（§7.3 第 ③ 次比较）不稳定：停下交设计会话；
- 清理核对失败。

**本次停止（修订 6）：** 2026-11-11，`59c5b8cfca` 的证据运行中 04-c 有 4 个 scope 失败，原因是候选内真实旅程 helper 没有随 C12 第 3 条同步，不是后端缺陷，也不在 DC68 重做范围（被测对象已运行）。实施会话按本节停止并保留全部产物，处理正确。设计会话的处理见 §16：fix4 只改测试代码，05 上完整集调试一次，审核会话定向复审，证据四项在 fix4 候选上重跑。

**fix4 调试停止（修订 7）：** 2026-11-11，fix4 第一个候选 `d12e3b8f70` 的 05 完整集调试中 3 个 scope 失败，原因是 §16.2 的 helper 规则要求所有按钮都有 `aria-describedby`，工作台工具栏的原生按钮没有。这是设计会话的错误，不是产品缺陷。实施会话按 §16.3 停止并保留产物，处理正确。处理见 §17。

**FE4b：** 在第 2 步写定。原则已经确定：

- BE-b 的 Contract 或产物与第一步不一致，不自行适配，交 owner 转后端；
- 需要在浏览器中重新计算行标识、按表名推断分组或列序时，停下交设计会话。

## 9. 风险

- **FE4 的退出排在 S1a 与 BE-b 之后：** 按 owner 2026-11-10 的决定，BE-b 第二步设计与实施都等 S1a 本地退出并合入 main，FE4b 再等 BE-b。任何一环推迟，FE4 都无法退出。FE4a 退出后，前端停在一个已取证的状态。owner 可以在 FE4a 退出时决定是否先把 FE4a 的结果作为 Phase 8 shadow 的前端候选；这不改变 FD8。
- **S1a 改变前端看不到的产物形态：** `artifact_id` 格式、bundle 交付与摘要的变化不出现在 OpenAPI 中（§2.3）。由 §4 第 7 项的变化说明与重新生成的互通 fixture 覆盖；说明缺失时 FE4b 不开始。
- **P7 改动 `vnext/` 后 FE4a 想跟进：** 按 §5.2，FE4a 期间不合入 main。
- **C7 让真实旅程变长：** 每次接受都走界面。用调试运行的实测评估；明显变长时报告，不删减步骤。

## 10. owner 决定

本文的问题已全部由 owner 决定（日期见各修订）：

- 修订 1：在审核会话中决定 Q2、Q5、Q10–Q13（审核报告 D1–D5）；
- 修订 2：按建议确认 Q1、Q3、Q4、Q6–Q9，并补充决定 BE-b 第二步在 S1a 结束后由后端开始（改写 Q5）；
- 修订 4：FE4a 审核交设计会话的 D1、D2 与看图范围，按设计会话的建议确认 Q14–Q16（§15）；
- 修订 5：2026-11-11 同意 B9 退役（Q17，§13.6）；
- 修订 6：FE4a 证据停止后，2026-11-11 约 02:28 UTC 在设计会话中按设计会话的建议确认 Q18、Q19（§16）；
- 修订 7：fix4 调试停止后，2026-11-11 约 03:02 UTC 在设计会话中按设计会话的建议确认 Q20（§17）。

| # | 事项 | owner 2026-11-10 的决定 | 本文落点 |
| --- | --- | --- | --- |
| Q1 | FE4 是否拆段 | 拆成 FE4a 与 FE4b，tag `fe-fe4a-exit`、`fe-fe4b-exit`；内容、前置与退出条件按 §5.2 | §5 |
| Q2 | FE4a 的合入点 | `fe-vnext` 快进到 main `16ffe72829`；FE4a 期间不合入 main，被测后端固定在 `16ffe72829`（`vnext/` 树 `49c1de43be`） | §5.2、§6.1 |
| Q3 | FE4a 是否需要新的生产 OpenAPI 原件 | 不需要。运行时 `/openapi.json` 与快照规范化后比对，不一致即停止，再由 owner 转后端交付原件 | §6.3 |
| Q4 | BE-b 第二步由谁写 | 由后端设计会话写；前端设计会话参与审核，核对面向前端的部分（Contract 形状与第一步一致、fixture 与 golden 覆盖第一步的规则、§4 第 7 项的变化说明），并答复业务规则问题。前端 kickoff §10 中“BE-b 设计”一项改为“BE-b 第一步与面向前端的核对” | §4 |
| Q5 | BE-b 与 P7 的先后（审核 D1；修订 2 改写） | FE4a 与 P7 S1a 并行。S1a 本地退出并合入 main 之后，由后端开始 BE-b 第二步设计，以 S1a 的实际实现与退出交接为基础；然后 BE-b 实施；FE4b 在 BE-b 退出并合入 main 之后。取代修订 1 记录的“第二步现在可以开始，以 S1a 的目标 Contract 为基础”。§4 的交付清单不变（含第 7 项：OpenAPI 规范化差异、bundle tar 成员 `logical_path` 集合与 manifest 字段集合相对 `6368c9c40c` 的变化说明，S1a 与 BE-b 分开列；ArtifactRef 与 surface 的变化说明；重新生成的互通 fixture）。后端的分工与排期按后端流程处理，本文只记录对前端的依赖 | §2.3、§4、§5、§9 |
| Q6 | 侧栏层级 | 层级定义不变，渲染时按需折叠：单视图不显示分段控件，单页签的项不显示页签栏，空组隐藏，多页签保留。FE4b 实现 | §3.2 |
| Q7 | `--color-warning-soft` | 删除未定义的引用，直接使用 `--color-surface-muted`，外观不变，不新增令牌，不需要重新看图 | §3.6 |
| Q8 | 历史初始备份节点 | FE4 不做；需要时作为后端任务立项，再开前端阶段 | §3.7 |
| Q9 | 首批空基线 | FE4 不做，维持 FE2 kickoff Q18；需要时作为独立的小后端任务，不并入 BE-b | §3.7 |
| Q10 | Q21 答复分支 `p6-fe3-q21-answer`（`d3450675bf`）（D4） | 已完成：审核会话以 `--no-ff` 合入本地 main，合并提交 `d10f6d55a8`，未推送。提示词用 `git show main:docs/backend-vnext/refactoring/formal/plans/p6-fe3-q21-answer.md` 读取 | 头部、§2.4、§11.1 |
| Q11 | 真实数据范围（D2，DC33、DC98） | FE4a：journeys 调试只跑 C7 改到的 J1、J2，证据跑完整集一次；t1 证据跑一次，只有改了 `t1.spec.ts` 时才允许一次调试运行（FE4a 加入参考截图，预计使用这一次）。审核会话不独立跑真实旅程，改为核对证据日志，加上模拟接口全量和探针。<br>FE4b：t1 证据跑一次，同时产生正式重拍截图；调试按需。<br>两段：只报告 t1 的 MODIFIED_ONLY 增量；打包流程没改就不跑 t4；不做计时，不用 t2–t4。t4 上的导航正确性由 BE-b 后端验证，前端不重复 | §3.3、§7.2、§7.4、§11 |
| Q12 | 证据与推送（D3） | `16ffe72829` 已在远端（包含 `b0fc25e881`），FE4a 开始前不需要推送。FE4a 退出时推送 tag `fe-fe4a-exit`；main 是否推送随后端推送节奏由 owner 决定（届时 main 会带上 P7 的内容） | §6.1、§6.4 |
| Q13 | DC74 与“P6 计时”（D5） | 不带入 FE4。前端 kickoff §9 那一行改为“已关闭（owner 2026-11-10）……”；FE3 kickoff §12 的 DC74 行只在末尾追加“已随 P6 退出关闭，见前端 kickoff §9”。DC74 文档由后端修改，本文不改 | §3.9、§13.2 |
| Q14 | C4 的“同一提交连续两次运行逐字节相同”是否改为容差判定（FE4a 审核 D1） | 改为容差判定：同尺寸，不同像素 ≤ 100，**且**最大 8 邻接连通块 ≤ 16 像素为“噪声”，否则为“内容变化”。上限写成截图比较脚本的常量（§3.8），脚本由 FE4a 实施会话在修复轮中实现、审核会话复审；§7.3 的 FE3c 到 FE4a 比较改用同一脚本；FE4b 沿用。不采用：只限总数 ≤ 100（测得一个数字的变化只有 41 个像素，会被判为噪声）；维持逐字节相同（当前 Chromium 下无法达成） | §3.4 C4、§3.8、§5.2、§7.2、§7.3、§8、§15.1 |
| Q15 | V12 在 1280 下横向溢出（FE4a 审核 D2） | 甲：在 FE4a 中修复，作为带入项 C12，范围扩大到同样溢出的 V11。审核操作组中相同的禁用原因只显示一次，改变 owner 在 FE3b D1–D3 看图时接受的“三个按钮各显示一次”，D1–D3、V11、V12 的顶栏截图交 owner 重新看图。预览页顶栏不改，N5 仍在 FE4b。不采用：保留每个按钮各自的原因、让操作区换行（V11、V12 的顶栏变成两行以上）；乙，作为偏差带入 FE4b（FE4b 要等 S1a 与 BE-b，真实 backend 上的溢出会保留数周） | §3.4 C12、§7.3、§15.2 |
| Q16 | FE4a 的看图范围 | 以比较脚本对 FE3c 证据截图判为“内容变化”或“尺寸不同”的全部文件为准，按原因分组，C3 另外改动的 10 张、C5 的 2 张随之并入；另加没有 FE3c 对应截图的新状态（C6、C8）。C8 冲突提示改用灰色 `.form-warning`，设计会话同意，随 C8 截图由 owner 确认 | §7.3、§15.3 |
| Q17 | B9 回退是否保留（2026-11-11） | 同意退役：BE-b 之后每个 READY surface 恰好一份导航，删除 `fallbackNavigation` 与 `preview-no-navigation`，缺导航或多份导航按 bundle 解码错误处理 | §3.1 B9、§5.3、§13.6 |
| Q18 | FE4a fix4 的真实旅程调试范围（2026-11-11，修订 6） | 在 05 上用 `--suite journeys --subphase fe3c` 跑一次完整集调试（20 个 scope，约 6 分钟），不给入口加新的选择项；任一 scope 失败即停，交设计会话，不自行再跑。对 fix4 取代 Q11 的“journeys 调试只跑 J1、J2”。不采用：甲，只跑 J1、J2（失败的 r7-reviewer-withdraw、r11-review-conflict 不在其中，首次在证据中执行，证据可能再次失败）；乙，给入口加这 4 个 scope 的选择项（要改工具并审核） | §1、§7.2、§8、§16.3 |
| Q19 | 证据在新候选上重跑（2026-11-11，修订 6） | 在 fix4 候选上四项各重跑一次，不为 04-b、05-t1 开沿用例外。Q11 的“证据跑一次”指在最终候选上各一次：在新候选上重跑 t1 属于证据，不计为第二次 t1 调试运行；`59c5b8cfca` 上通过的三项只作记录。不采用：沿用 `59c5b8cfca` 的 04-b、05-t1（与 §7.2“前端没有沿用机制”冲突，需要新例外，节省约 15 分钟） | §7.2、§16.5 |
| Q20 | fix4 修正候选的调试（2026-11-11，修订 7） | fix4 第一个候选的完整集调试因设计会话写错的 helper 规则失败后，授权在修正候选上用 `--subphase fe3c` 再跑一次完整集调试（约 6 分钟）；再失败即停，交设计会话。不采用：不再调试、直接取证（`stepUploadAction` 等调用在新 helper 下从未在真实 backend 上运行，证据失败要再花一轮约 30 分钟） | §8、§17.3 |

**后续仍需 owner 或后端处理的事项：**

- 已完成：后端交接记录 `p7-s1a-frontend-beb-handoff.md` 中第二步的开始时间已按 Q5 修订 2 更正（`e2eaab4db9`，§4）；
- BE-b 的排期与后端会话安排（后端流程）；
- t1 第二次调试运行（§7.2）；
- FE4a 退出时 main 的推送；FE4b 退出时的 tag、合入与推送。

## 11. 提示词草稿

发出时间由审核会话按前置条件决定，发出前填写方括号中的值。FE4a 与 FE4b 的实施、审核都由**新会话**承担，不由 FE3 的会话或另一子阶段的会话承担（AGENTS“角色与子 agent”）。§10 的 owner 决定已经写进下面的提示词。

### 11.1 FE4a 实施

**前置条件：**

1. 本文经审核会话定向复核（§10 已全部由 owner 决定）；复核通过后，由设计会话把 `fe4-kickoff` 以 `--no-ff` 合入本地 main（不推送），提示词中的 `[kickoff 确认提交]` 与 `[确认提交]` 填入合入后的提交号；
2. 审核会话发出前重核并记录：
   - `fe-vnext` 仍为 `e22e39ba15`；
   - `p6-exit` 仍指向 `b0fc25e881`，其 `vnext/` 为 `49c1de43be`；
   - main 当前的头与其 `vnext/` 树（只记录，FE4a 的合入点不随之改变）；
   - `S2B_DATASET_BASELINE`、`S1B_V2_PREVIEW_CHANGED_COUNTS` 在 `16ffe72829:vnext/backend/benchmarks/real_dump_journey.py` 中仍是模块级常量（只读 `git grep`）；
3. 审核会话在所选节点上现场核对工具链、npm 缓存、依赖镜像、RS 依赖镜像与 t1 目录，并运行 `--print-input`。

> 你是 FE4a 前端实施会话，是新会话，不沿用 FE3 实施会话的上下文。本阶段处理 FE3 的带入项、Q21 文案、视觉令牌与取证工具，并在 P6 退出的 backend 树上跑真实旅程与 t1。不接入 BE-b。FE4a 与后端 P7 S1a 并行，期间不合入 main。
>
> **先读（一律用 `git show main:<路径>`，不切换开发主机上任何共享 worktree 的分支）：**
> - AGENTS：“角色与子 agent”“专用测试节点”（DC91 五节点池、占用与 DC68）、“前端测试（FD7）”、“Docker / Compose 验证”；testing-conventions“前端测试”“真实 backend e2e”；
> - FE4 kickoff（main `[kickoff 确认提交]`）全文，重点 §3.3–§3.8、§5.2、§6、§7、§8、§10、§12；
> - FE3 kickoff §3.2（FE3b、FE3c 退出记录）、§4.6、§4.7、§6.4、§8、§16；FE2 kickoff §5.5；
> - 带入项的原文：`reviews/fe3b-rereview-1.md`、`fe3b-rereview-2.md`、`fe3b-rereview-3.md`、`fe3b-evidence-check-1.md`、`fe3c-review.md`、`fe3c-rereview-1.md`、`fe3c-evidence-stop-1.md`、`fe3c-evidence-check-1.md`；
> - FE3c 的 handoff：`fe3c-handoff.md`（§5.5 只由模拟接口覆盖的项、§10 偏差）、`fe3c-handoff-fix1.md`、`fe3c-handoff-fix2.md`、`fe3c-evidence-04.md`；
> - 后端 Q21 答复：`git show main:docs/backend-vnext/refactoring/formal/plans/p6-fe3-q21-answer.md`。
>
> **起点与分支：** 在独立 worktree `/home/dev/gdds-fe` 的 `fe-vnext`（当前 `e22e39ba15`）上，快进到 `16ffe728290e1179d9450ea160a0e6ca49473ec6`（`git merge --ff-only`），不 rebase，不合入其后的 main（kickoff §6.1，owner 2026-11-10 已决定）。这个提交已在远端，开始前不需要推送。按 kickoff §5.2 做路径核对：`<main>` 为 `16ffe72829`，候选的 `vnext/` 树必须是 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`。`--print-input` 必须得到 `[审核会话现场核对后填写，预期 gateway-backend-deps:lock-578e079b762e]`，RS 依赖镜像为 `[预期 gateway-p2r1-repository:lock-6dc9659f0aee]`，否则停止。不刷新 OpenAPI 快照：运行时 `/openapi.json` 与快照规范化后必须逐字节相同，否则停止（kickoff §6.3）。
>
> **范围：**
> 1. 带入项 C1–C11（kickoff §3.4），每项按“处理”一列完成，并补对应的用例；
> 2. Q21 文案（§3.5）：删除 4 个码，新增 4 个码，单测同步；
> 3. `--color-warning-soft`（§3.6，owner 已决定：删除未定义的引用，保持灰底，截图不变）；
> 4. 取证工具（§3.8）：证据 wrapper 与十六进制回源脚本，提交在 `frontend/scripts/`；
> 5. `run-real-backend-e2e.sh` 加一个只运行 `j1-archive-mainline`、`j2-manual-close` 两个 scope 的调试选择，并接受 FE4a 的子阶段名（§7.2）；
> 6. 在 `e2e-real/t1.spec.ts` 中加入 kickoff §3.3 列出的参考截图（不依赖 BE-b 的 7 个页面名，各拍 1280 与 1920），放在 M1 测量窗口之外；不加依赖 BE-b 的页面；
> 7. 在新 backend 树上：J1、J2 通过（C7 之后的接受都经界面），J1、J2 每次预检的异常集合仍按 FE3 kickoff §4.6 的表核对，不符即停；t1 调试运行一次通过。
>
> **不做：** 不改 `vnext/`；不接入 BE-b，不改导航、列展示与行定位；不改打包流程（需要改时先停下，kickoff §7.4）；不改 FE3 kickoff 已定的业务规则；不跑 J1、J2 以外的真实旅程调试，不跑第二次 t1 调试，不用 t2–t4，不做计时（kickoff §7.2，owner 2026-11-10 已决定）。
>
> **节点与占用：** 按 AGENTS 的五节点池选合格空闲节点（kickoff §7.1，建议 07 模拟接口、05 真实 backend 与 t1），会话名 `fe4a-impl`。所有运行都原子取得占用标记，真实 backend 入口自行获取，外层不重复获取（kickoff §3.8）。`GATEWAY_FE_TEST_WORKERS=2`。t1 目录运行前按清单逐文件核对，只读挂载。
>
> **日志与回源（FE3 中出现过的两类错误，必须遵守）：**
> - 证据日志一律由脚本 wrapper 生成。wrapper 写日志前先检查参数个数、绝对路径、日志目录已存在、截图目录在 worktree 外，任一不满足即退出、不运行入口。FE3c 曾把 `LOG_DIR` 取成 `$2`，导致入口没有运行；
> - handoff 中的每个十六进制值都用脚本逐个回源（节点现场重算的 SHA256 在该节点宿主机上算；取回的日志原文与 git 对象可在开发主机上对照），并报告长度不是 7–12、40、64 的值。FE3b 的证据 handoff 曾有 5 个 SHA 抄错。不手抄 SHA。
>
> **停止条件：** kickoff §8 FE4a。失败与重做按 kickoff §7.2 引用的 DC68 原文；需要第二次 t1 调试运行时停下交设计会话。
>
> **交付：** kickoff §7.2 FE4a 调试行的运行通过后，提交代码候选与 handoff `docs/frontend-vnext/fe4a-handoff.md`，内容包括：
> - 快进后的 HEAD、`vnext/` 树、路径核对结果、`--print-input` 与运行时 OpenAPI 比对结果；
> - C1–C11、Q21、令牌、取证工具、入口的 J1/J2 选择各项的改动位置与对应用例；新增或修改的用例清单；
> - J1、J2 逐次预检的异常集合；C7 之后 J1、J2 的耗时（取自日志，只报告）；
> - t1：§8.3 逐条核对；第 1 步 MODIFIED_ONLY 的 renderer 增量与 FE3a 24.86 MiB 并列；参考截图的文件名与 SHA256；打包流程是否改变（kickoff §7.4 筛查结果）；
> - 出现过的诊断码，以及 §3.5 文案表以外的编码；
> - 模拟接口截图清单，标出 kickoff §7.3 中交 owner 看图的文件；
> - 每次运行的节点、hostname、起止 UTC、起止 HEAD、树、exit code、日志 SHA256；工具链、npm 缓存、依赖镜像与 RS 镜像的身份；
> - 十六进制回源的结果；
> - 已完成、未测（只由模拟接口覆盖的项及原因）与未决事项，分三节写。
>
> 不合入 main，不推送。审核通过后，按审核会话的指示在最终候选的 clean、已提交 detached worktree 上各运行一次证据项（kickoff §7.2 FE4a 证据行：模拟接口全量、上传包校验、`journeys` 完整集、`t1`），提交证据 handoff，交审核会话核对。

### 11.2 FE4a 审核（前置：FE4a handoff 已提交）

> 你是 FE4a 审核会话，是新会话，不与 FE4a 实施会话为同一会话，也不沿用 FE3 审核会话的上下文。审核 `fe-fe3c-exit..[FE4a handoff 提交]`；来自 main 的文档与 `vnext/` 不在前端审核范围。先按 kickoff §5.2 做路径核对（`<main>` 为 `16ffe72829`，`vnext/` 树 `49c1de43be`）。依据：FE4 kickoff（main `[确认提交]`）§3–§8、§10；FE3 kickoff §4.6、§6.4、§8、§16；带入项原文所在的审核报告；后端 Q21 答复（`git show main:docs/backend-vnext/refactoring/formal/plans/p6-fe3-q21-answer.md`）。
>
> 重点：
> 1. **带入项：** C1–C12 逐项对照“处理”一列，确认用例有区分力：把修复回退后对应用例应失败。
> 2. **Q21：** 文案表与 kickoff §3.5 一致；删除的 4 个码不再出现在文案表与码表中；单测覆盖新增的 4 个码与匹配顺序。
> 3. **令牌：** `--color-warning-soft` 的引用已删除，`.form-warning` 直接用 `--color-surface-muted`；相关截图与 FE3c 相比为“相同”或“噪声”（§7.3）。
> 4. **取证工具与入口：** wrapper 的参数检查、按入口区分的占用标记处理与记录字段完整（kickoff §3.8）；回源脚本能发现抄错与长度异常；`run-real-backend-e2e.sh` 的 J1/J2 调试选择只影响所选 scope，不带该选择时仍是完整集。
> 5. **真实旅程与 t1（核对日志，不重跑）：** J1、J2 在新 backend 树上的异常集合与 FE3 kickoff §4.6 一致；C7 之后的接受都经界面；t1 按 §8.3 由程序判定；第 1 步 MODIFIED_ONLY 增量与 FE3a 并列；参考截图齐全（kickoff §3.3 的 7 个页面名 × 2 种宽度），且不在 M1 测量窗口内；按 kickoff §7.4 两步判断打包流程是否改变。
> 6. **截图（修订 4 改写）：** 用 §3.8 的截图比较脚本：与 FE3c 证据截图比较，“内容变化”“尺寸不同”与“缺失”的文件都有对应的改动或由 C4 引起，并全部列入 §7.3 的看图清单；C4 的稳定性比较按 §7.3 第 ①、② 次进行，证据运行后核对第 ③ 次。
> 7. **探针（已提交的一次性 worktree，只在节点上）：**
>    - 恢复 C8 之前的单一提示变量：C8 的两条用例应失败；
>    - 恢复 C2 之前不经在途合并的重试：attempt 读取次数的断言应失败；
>    - 把 C11 的一处闸门改回固定延迟加不带参数的 `unrouteAll()`：在不少于 8 个 worker、`--repeat-each` 不少于 20 的单独运行中观察是否复现，结果如实记录，不强求复现；
>    - 让 wrapper 的日志目录参数取错位置：wrapper 应在运行入口前退出；
>    - 在一份 handoff 副本中改错一个 SHA 的一位：回源脚本应报告未命中。
> 8. **运行（owner 2026-11-10 已决定）：** 独立运行一次模拟接口全量 `run-tests.sh --e2e --screenshots` 与上面的探针（会话名 `fe4a-review`）。**不独立跑真实旅程与 t1**：J1、J2 与 t1 只核对实施会话的调试日志、日志 SHA256 与参考截图的 SHA256；证据运行之后再核对证据日志。
> 9. **回源：** 用脚本把 handoff 中的十六进制值逐个回源，报告长度不是 7–12、40、64 的值。
> 10. **DOM 结构与真实旅程定位器（修订 6 增加，FE4a 余下各轮与 FE4b 都适用）：** 候选改动 DOM 结构或 class 时（包括元素之间的兄弟、父子关系与 `aria-describedby` 的指向），用 `grep -rn` 按改动的 class 名与结构关键词（如 `following-sibling`、`xpath=`、被改动的 class）核对 `frontend/e2e-real/` 中依赖该结构的定位器。报告写明命令、命中，以及真实旅程是否受影响、受影响的 scope；受影响而未同步修改的列为阻塞 finding，并写明需要的调试范围（按 §7.2，超出范围时交设计会话）。不以“真实旅程按角色和文字定位”代替核对。改动或新增共享 helper 时（修订 7），还要按 helper 的全部调用处核对被断言元素的实际结构（例如是否有 `aria-describedby`、`title`、`id`），不只核对定位器文本。
>
> 报告写入 `docs/frontend-vnext/reviews/fe4a-review.md`，结论为通过、定向修复或停止；需要设计决定的事项标注“交设计会话”。通过后指明证据项（kickoff §7.2 FE4a 证据行），由实施会话运行；取证后核对证据日志，给出 FE4a 退出建议（含推送 tag `fe-fe4a-exit`，kickoff §6.4），并列出带入 FE4b 的项。

### 11.3 FE4b 实施与审核

在本文第 2 步（§5.3）中写定。框架与 FE4a 相同：新建实施与审核会话；先读 BE-b 的 Contract、交接、golden 与 §4 第 7 项的变化说明；合入 BE-b 退出后的 main（届时含 P7 S1a）；刷新 OpenAPI 与 fixture；按 §3.1、§3.2 实施；t1 证据运行一次，同时产生正式重拍截图，交 owner 看图。§11.2 第 10 项（DOM 结构与真实旅程定位器）同样适用，写进 FE4b 的审核清单。

## 12. 交接材料

新会话从下列文档读取“已完成、未测、未决”，不依赖旧会话的上下文：

| 类别 | FE4a 读取 | FE4b 另读 |
| --- | --- | --- |
| 已完成 | FE3 kickoff §3.2 的 FE3a、FE3b、FE3c 退出记录；`fe3c-evidence-04.md`、`fe3b-evidence-04.md`；`fe3c-handoff.md` 及 fix1、fix2 | `fe4a-handoff.md` 与 FE4a 退出记录；BE-b 的退出交接 |
| 未测 | `fe3c-handoff.md` §5.5（只由模拟接口覆盖的项）；FE3 kickoff §4.6 末段（时间倒退等只由模拟接口覆盖）、§4.7（提交 403、仍在运行与 `MANUAL_RECOVERY_REQUIRED` 只由模拟接口覆盖）、§15.3 与 §16.7（过期 `APPROVE` 409 只由模拟接口覆盖）；§8.4（t1 FULL 不可比较，FE4 起不再报告；t4 自 FE3a 后未重测） | `fe4a-handoff.md` 的“未测”一节 |
| 未决 | 本文 §3.4–§3.7、§10；FE3 kickoff §12 中仍开放的项 | 本文第 2 步；BE-b 第二步与交接中留给前端的事项 |

## 13. 同分支中对其他文档的修改

### 13.1 初稿（`79ccde87d6`）

本分支另一个提交只改以下几节，不改其他内容：

- **前端 kickoff：**
  - §7 FE4 一行：写明拆段与范围见本文（待 owner 确认），退出条件改为按本文 §5.2；
  - §9：“侧栏导航层级是否精简”改为见本文 §3.2、Q6；“`diagnostics_summary` 中的自由文本”改为“已并入 BE-b（草案 §4.10，owner 2026-11-03），随 FE4b 接入”。
- **FE3 kickoff：**
  - §11 Q21：状态改为“后端已答复（`d3450675bf`），前端处理见 FE4 kickoff §3.5”；
  - §12：“比较诊断码的变化”“FE4 真实数据重拍的节点”“`--color-warning-soft`”三行改为指向本文 §3.5、§2.5、§3.6。

### 13.2 修订 1（2026-11-10）

**本文修改的节：** 头部（状态、依据、P7 文档的用法）；§1；§2.1（占位 fixture）；§2.2（合入点、本地 main、`p6-exit`）；§2.3；§2.4；§3.3；§3.8；§3.9；§4；§5.1；§5.2；§5.3；§6.1；§6.2；§6.4；§7.2；§7.3；§7.4；§8；§9；§10（拆为 10.1 已决定、10.2 待决定）；§11；§12；§13；新增 §14。§3.2、§3.6、§3.7、§6.3 只把“§10 Qn”改为“§10.2 Qn”（§6.3 另把 FE4b 的交付引用改为 §4 第 5、7 项）。§2.5、§3.1、§3.4、§3.5、§7.1、§7.5 未改。

**修订期间 main 的变化：** 修订开始时本地 main 为 `d10f6d55a8`；修订期间后端提交了 `27ea352487`（只改 `docs/backend-vnext/` 下两个文件，`vnext/` 仍为 `49c1de43be`）。修订 1 的第三个提交据此更新 §2.2 的 main 头，并在 §2.3、§3.9、§4 引用该交接记录；其内容与 owner 2026-11-10 的决定一致，没有改变本文的结论。

**其他文档（本分支另一个提交，只改以下几行）：**

- **前端 kickoff §9：**
  - “P6 计时是否包含整包传输”一行：处理列改为“已关闭（owner 2026-11-10）：P6 门槛不含 bundle 下载；t1 与 journeys 的下载耗时和体积继续只报告；Phase 8 如需包含下载的端到端时间再立项”，阶段列改为“已关闭”；
  - “`diagnostics_summary` 中的自由文本”一行：补引前端 kickoff §5 BE-b 行与 FE2 kickoff §5.5（审核报告第 4 节第 1 点的可选建议）。
- **FE3 kickoff：**
  - §11 Q21 状态列：补“答复已合入本地 main（`d10f6d55a8`）”与“拆段待 owner 确认（FE4 kickoff Q1）”；
  - §12“比较诊断码的变化”“`--color-warning-soft`”两行的阶段列：补“拆段待 owner 确认（FE4 kickoff Q1）”；
  - §12“P6 计时与整包下载（DC74 草案）”一行：只在末尾追加“已随 P6 退出关闭，见前端 kickoff §9”，不改原文。

### 13.3 修订 2（2026-11-10）

owner 按建议确认 Q1、Q3、Q4、Q6–Q9，并补充决定：BE-b 第二步在 S1a 本地退出并合入 main 之后由后端开始，前端设计会话参与审核核对。

**本文修改的节：** 头部（状态）；§1 第 1、4 条；§2.3；§3.2、§3.6、§3.7（“建议”改为决定，删除不采用的方案）；§4（表头与三行、交付清单标题，新增与后端记录的出入）；§5.1；§5.2（两行前置条件）；§6.3（删除乙）；§7.3（删除 Q7 选乙的一项）；§9 第 1 条；§10（改为单一的决定表，删除建议说明与“不采用的方案及其代价”）；§11.1（前置条件第 1 项、范围第 3 项）；§11.2（第 3 项）；§13.3；§14 N5 行。其余各节中的“§10.1 Qn”统一改为“§10 Qn”。

**其他文档（本分支另一个提交，只改以下几行）：**

- **前端 kickoff：**
  - §7 FE4 一行：“2026-11-10 草案，待 owner 确认”改为“owner 2026-11-10 已确认”；
  - §9“侧栏导航层级是否精简”：改为 owner 已决定；
  - §10 设计会话的职责：“BE-b 设计”改为“BE-b 第一步与面向前端的核对”（Q4）。
- **FE3 kickoff：**
  - §11 Q21 状态列与 §12 两行：“拆段待 owner 确认”改为“拆段已由 owner 确认”；
  - §12 `--color-warning-soft` 一行：末尾追加 owner 的决定。
- **BE-b 设计草案：**
  - §5 首句“第二步在 P6 S5 接近完成时定稿”：原文保留，末尾追加 owner 2026-11-10 的新时点。

### 13.4 修订 3（2026-11-10）

依据[定向复核报告](reviews/fe4-kickoff-rereview-1.md)（`be3dc218f8`，通过）的 R1–R4，以及 owner 对 D-R1 的确认（以修订 2 为准）和后端的记录更正（`e2eaab4db9`）。

**本文修改的节：**

- 头部：状态加修订 3；
- §3.3（R3）：`fe4-t1-review` 固定在第 5 步；
- §4：“与后端记录的出入”改为“与后端记录一致”，引用 `e2eaab4db9`；
- §7.2（R1）：删除残留的空表头；
- §10：“后续仍需 owner 或后端处理的事项”第一条改为已完成；
- §11.1（R2）：前置条件第 1 项加“复核通过后由设计会话以 `--no-ff` 把 `fe4-kickoff` 合入本地 main，提示词填入合入后的提交号”；
- §13.4；
- §14（R4）：B1 行第 ③ 点后注明“修订 2 已改，见 §10 Q5”。

§2.2 的“本地 main（修订时）”仍记修订 1 时的 `27ea352487`，不随本次更新：发提示词前由审核会话按 §11.1 重核并记录 main 当时的头。其他文档本次不改。

### 13.5 修订 4（2026-11-10）

依据 [FE4a 审核报告](reviews/fe4a-review.md)（短分支 `fe4a-review`，提交 `541febf566`，尚未合入 main）§2.3、§3.1、§6 交设计会话的 D1、D2 与看图范围，以及 owner 2026-11-10 对设计会话建议的确认（§10 Q14–Q16）。修订分支从本地 main `cad463d3ec` 拉出。

**本文修改的节：** 头部（状态）；§3.4（C4 行“处理”列改写，新增 C12 行）；§3.8（新增截图比较脚本，“两个工具”改为三个）；§5.2（FE4a 行的内容与退出条件）；§7.2（FE4a 调试行补修复轮的两次全量）；§7.3（改写，增加 FE4b 一条）；§8（FE4a 增加两条停止条件，C1–C11 改为 C1–C12）；§10（说明与 Q14–Q16）；§11.2（第 1、3、6 项）；§13.5；新增 §15。

§11.1 的实施提示词已经发出，不改；修订 4 对实施会话的要求由审核会话随修复轮转达（§15.4）。其他文档本次不改。

**审核报告之外由设计会话核对出的事实：** V11 的 `fe3c-review-expired-1280` 同样横向溢出（1509 px，FE3c 证据截图中已如此，两次审核都没有列出）；V12 重读后的模拟数据审核状态仍为 PENDING（§15.2）。两项都并入 C12。

### 13.6 修订 5（2026-11-11）

**依据：**
- BE-b 第二步设计与执行计划，候选 `b61cc37d5f`（本地 main，未推送；`vnext/` 树 `bd452d67dc`，无产品源码变化），各文件 SHA256：
  - `be-b-second-step-design.md`：`706998b6cc141bf34c288083db2d8eee08caacc3784cba6df1c8d31748454703`
  - `be-b-execution-plan.md`：`69c2dabbed7bd5ac5a8725fb1df67a58dbf5c6933faf5050d3951fbe70d1ac8d`
  - 第一步草案：`370d5a53b8f73a6b98bde276cd1e05cdf798b6026ec5df0c2119ec68c2d7b28a`
- 前端设计会话的两份报告（在仓库外的交接目录 `/home/dev/gdds-stage-exchange/be-b/reviews/`，不入库）：
  - 对 `f0be08d9ed` 的定向核对：`frontend-targeted-review-f0be08d9ed.md`，结论 `CHANGES_REQUIRED`，SHA256 `b1187f8254dc8a6c210dfe4a099faf72893313a64b524d3d12402eeab969cfff`；
  - 对 `b61cc37d5f` 的窄复核：`frontend-targeted-rereview-b61cc37d5f.md`，结论 `GO_WITH_NONBLOCKING`，SHA256 `45fff18109b2594ca494b060379e869b893c246e3ee79769da23e9914cdb8845`。FE-BEB-01–10 关闭；新增非阻塞 FE-BEB-11–13，由后端在 B0/B4 补文字。
- owner 2026-11-11 采纳原报告全部建议，包括空 `sg_cfg` 有变化或风险时保留（FE-BEB-01(b) 甲），并要求同步本文 §3.1 与 §5.3。
- 修订分支 `fe4-kickoff-rev5` 从本地 main `b61cc37d5f` 拉出。

**本文修改的节：** 头部（状态）；§3.1（B1–B9 全部按第二步改写，补 Contract 版本判定）；§10（Q17）；§5.3（写定 fixture、模拟数据不变量、程序判据、截图分工与合入点，列出仍待 BE-b 交付的项）；§13.6。

**owner 确认项：** B9 由“保留回退”改为退役。原 B9 是前端 kickoff §4.5 确认的正式行为，但第二步规定每个 READY surface 恰好一份导航，该状态已不可达，不影响任何业务结果。owner 2026-11-11 同意退役（§10 Q17）。

**未改：**
- §2.3 与 §4 的事实记录（第二步已写、交付清单的 S1a/BE-b 分栏）留到 BE-b 交付核对时一并更新；
- 第一步草案与后端文档不由本文修改；
- 其他文档本次不改。

### 13.7 修订 6（2026-11-11）

依据 FE4a [证据核对第 1 轮](reviews/fe4a-evidence-check-1.md)（`fe4a-review` 分支 `14f8daa7f8`，尚未合入 main）与 owner 2026-11-11 的确认（§10 Q18、Q19）。修订分支 `fe4-kickoff-rev6` 从本地 main `b329d1d2de` 拉出。处理与本文修改的节见 §16。其他文档本次不改。

### 13.8 修订 7（2026-11-11）

依据 fix4 实施会话的停止报告（候选 `d12e3b8f706c99c66d0de2e1763f145f95862c92`，05 日志目录 `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-05/`）与 owner 2026-11-11 的确认（§10 Q20）。修订分支 `fe4-kickoff-rev7` 从本地 main `1645609805` 拉出。处理与本文修改的节见 §17。其他文档本次不改。

## 14. 审核意见与 owner 决定的处理（修订 1）

依据[审核报告](reviews/fe4-kickoff-review.md)第 11 节与 owner 2026-11-10 的决定（§10）。owner 的决定优先于审核报告第 12 节提示词中的写法。

| 编号 | 处理 | 位置 |
| --- | --- | --- |
| B1 | **已改。** ① §2.2 记录修订时本地 main 为 `d10f6d55a8`、`vnext/` 仍为 `49c1de43be`（不照抄审核时的 `00ca325c2e`），列出 `16ffe72829` 之后的主线提交，FE4a 仍固定用 `16ffe72829` 并换上新理由；② 头部与 §2.3 改写 P7 事实：S0 已收口、S1a 编码已获授权、P7 文档未提及 BE-b，不据此推导 BE-b 设计；③ Q5 按 owner 决定改写为已决定项（BE-b 第二步以 S1a 目标 Contract 为基础、实施在 S1a 本地退出合入 main 之后），不再保留“P7 计划未提交”的前提（修订 2 已改，见 §10 Q5）；④ §4 交付清单增加第 7 项，在 owner 要求的 OpenAPI 差异、`logical_path` 集合、manifest 字段集合之外，保留 ArtifactRef 与 surface 的变化说明与互通 fixture；⑤ §11.1 前置条件增加发提示词前重核 `fe-vnext`、`p6-exit` 与 main | 头部、§1、§2.2、§2.3、§4、§6.1、§9、§10 Q5、§11.1 |
| B2 | **已改。** FE4a 只在 `t1.spec.ts` 中加入不依赖 BE-b 的 7 个页面的参考截图，列出截图名规则与 1280/1920；依赖 BE-b 的页面在第 2 步定稿并在 FE4b 实现；FE4a 退出条件不含 BE-b 页面；另规定截图放在 M1 测量窗口之外 | §3.3、§5.2、§5.3、§7.3、§11.1 范围第 6 项 |
| N1 | **已改。** §6.2 补全分类（`snapshot_materialization/`、`repository_read/`、`canonical_metadata`、`pair_pipeline`、`bootstrap/operation_worker.py`、`repository_client/src/`、完整的 Rust 文件），第 1 行补导入闭包核对。按路径计 control DB 为 6 个、测试 24 个，与审核报告的 7、23 计法不同，总数同为 72，已注明 | §6.2 |
| N2 | **已改。** §6.2 operation 行写明 History 比较 assemble 步骤新增的两类终态失败与 `diagnostic.code` 可达取值扩大，结论为无渲染影响 | §6.2 |
| N3 | **已改。** 直接引用 AGENTS（main）DC68 原文 | §7.2 |
| N4 | **已改。** t4 触发改为“`git diff --stat` 筛查 + 审核会话判断打包流程是否改变”，列出函数与打包阶段范围；补 Q23 理由 ② 按实际路径的复核结论与 FE3b 的 `087281ce65` | §7.4 |
| N5 | **已改（修订 1）。** 当时待决定的 Q1、Q3、Q4、Q6–Q9 都增加了“不采用的方案及其代价”一列。修订 2 中这些问题已由 owner 决定，§10 只保留决定，建议说明与该列一并删除 | §10 |
| N6 | **按 owner 决定改写。** FE4a 调试的真实旅程只跑 J1、J2，t1 只允许一次调试运行；审核会话不独立跑真实旅程；完整集与 t1 证据各一次。为只跑 J1、J2，FE4a 需要给入口加调试选择（入口现在只能按子阶段选范围） | §3.3、§7.2、§8、§11 |
| N7 | **按 owner 决定处理。** DC74 与 P6 计时已关闭，不带入 FE4；前端 kickoff §9 与 FE3 kickoff §12 按 owner 给出的文字修改，不改历史记录 | §3.9、§10 Q13、§13.2 |
| N8 | **已改。** 头部依据补 `fe3b-rereview-1.md`；§2.1 补 `projections/business-navigation/diagnostics.json`；§6.2 的 Rust 文件改为实际列表；§12 把“过期 `APPROVE` 409”的出处改为 FE3 kickoff §15.3、§16.7 | 头部、§2.1、§6.2、§12 |
| N9 | **已改。** FE3 kickoff §11 Q21 状态列与 §12 两行注明“拆段待 owner 确认（FE4 kickoff Q1）” | FE3 kickoff（§13.2） |
| N10 | **已改。** wrapper 的占用标记按入口区分（`run-tests.sh`、`validate-upload-package.sh` 由 wrapper 获取；`run-real-backend-e2e.sh` 由入口获取，wrapper 只确认标记不存在），区分本人与他人标记；回源脚本写明节点现场重算在测试节点宿主机运行，只读对照可在开发主机运行 | §3.8、§11.1 |
| N11 | **已改。** §6.2 写明两个常量名，设计会话已用 `git grep` 确认其在 `16ffe72829` 中仍存在（第 192、234 行）；§11.1 前置条件要求审核会话发提示词前再重核 | §6.2、§11.1 |
| D1 | owner 2026-11-10 已决定 | §10 Q5 |
| D2 | owner 2026-11-10 已决定 | §10 Q11 |
| D3 | owner 2026-11-10 已决定 | §10 Q12 |
| D4 | owner 2026-11-10 已决定，已完成 | §10 Q10 |
| D5 | owner 2026-11-10 已决定 | §10 Q13 |

## 15. FE4a 审核交设计会话事项的处理（修订 4）

依据 FE4a 审核报告（`541febf566`）§6 的 D1、D2 与 §2.3、§4 F5 的看图范围。owner 2026-11-10 按设计会话的建议确认（§10 Q14–Q16）。

### 15.1 D1：C4 的截图稳定性

**测量（设计会话，07 `gw-dms-07.lan`，2026-11-10，只读）：** 脚本与输出在 07 `/home/dev/gdds-fe-logs/fe-design-d1/`，`SHA256SUMS` 记录全部文件；比较脚本 `pngstat.py` SHA256 `12364129eb6af4db4035696c65e74f06a4f94ed9844e7cf964e2a06fd189993c`。它只用于本次测量，不是 §3.8 要交付的脚本。

| 比较 | 逐字节不同 | 每张不同像素最大值 | 每张最大连通块最大值 | 输出 SHA256 |
| --- | --- | --- | --- | --- |
| H 与 I（实施会话） | 13 | 73 | 10 | `ee0e438587c623bc104f14bc3de440d0556e6bd1332fc3a3501641f469d4c348` |
| H 与 R（审核会话） | 24 | 21 | 8 | `5e0dc7e1847376895594a8fadeb43cd79f5ed202617159ce043cb32bd2d84e45` |
| R 与 S（审核会话，只差 srgb 参数） | 17 | 56 | 10 | `9a6f9d70ea2755d1237844d750b10a635e33c1c1b4283fd76bfb234fc1b7cdf0` |
| FE3c 证据（04）与 R（07）：未改动页面 | 7 | 21 | 6 | `e058dd5b9eea1855120e181bb76db86749e796825a6d6b3b9d9f371fabf7405e` |
| 同上：有改动的页面中最小的两张（`history-compare-connection-interrupted`、`upload-running-modified-only`） | — | 216、734 | 216、211 | 同上 |
| 一个数字的变化：“执行中 · 已等待 N 秒”，N = 0–9 两两比较，11 px 与 12 px 各 45 对 | 90 | 最小 41 | 最小 41 | `570a71fa6a62bd3424b84e1ae61fed5834ecbb1e5731c0444ee860ebec37c4bc` |

最后一行在工具链镜像 `mcr.microsoft.com/playwright:v1.64.1-noble` 中用 `chrome-headless-shell` 渲染（`--network none`），字体栈取 `--font-family-ui`，颜色 `--color-text-muted`，与模拟接口截图在同一镜像中、用同样的字体。各次运行中不同像素的最大通道差可以达到 58（表格边框接缝），所以通道差不能用来区分噪声与内容。

**结论：**

- 噪声是分散的单点或小块：总数最多 73，连成一块最多 10 个像素；跨节点（04 与 07）没有变大；
- 内容变化连成一块：改一个数字就有 41 个像素的连通块，有改动的页面最小也有 211；
- 审核报告建议的“不同像素 ≤ 100”单独使用时，一个数字的变化（41）会判为噪声，正是 C4 要防的“等待时长每次不同”。所以采用两个上限同时满足：总数 ≤ 100（噪声最大值 73 的约 1.4 倍，挡住大面积分散的变化），最大连通块 ≤ 16（噪声最大值 10 的 1.6 倍，不到一个数字变化 41 的一半）；
- 逐字节相同在当前 Chromium 下做不到（实施会话的参数对照实验，fe4a-handoff §5），继续要求只会让 C4 无法完成。

**限制：**

- 两个上限按 07 与固定的工具链镜像测得。工具链镜像变化时重新测量，按测量结果修订本文后才能改上限；
- 比一个数字更小的变化（例如单个标点、零散的 1 像素改动）可能判为噪声。脚本只用来区分同一提交两次运行的不确定性，并生成交 owner 看图的清单；改动的意图由代码审核负责，脚本不代替看图与审核。

### 15.2 D2：审核模式顶栏在 1280 下横向溢出（C12）

**事实（`fe-vnext` `7a6520620b`）：**

- 审核报告 R 运行的 190 张截图中，宽度超过视口的只有两张，都是 1280：`fe3c-review-closed-1280`（V12，1340 px）与 `fe3c-review-expired-1280`（V11，1509 px）；FE3c 证据截图中 V11 已是 1509 px。真实 backend 上做同样的操作都会出现；
- 三个原因都在审核模式顶栏：
  1. `ReviewActions.tsx:144-148`：错误提示框渲染在 `.review-actions` 中，与三个按钮同一行；`.review-actions` 是不换行的 `inline-flex`（`styles.css:578`），位于不换行的 `.compare-status` 中；
  2. 每个按钮各自显示禁用原因：V12 中三个按钮都写“该提交已关闭（未归档）”，比 D1 状态的“该提交已归档”更长；V11 中“审核通过”下的长原因超出视口右边缘；
  3. `ComparisonPage.tsx:618`：`ReviewDispositionLine` 是 `.compare-header__top` 四列网格（`styles.css:130`）中的第五个子元素，自动换到下一行的第一列，把第一列（“返回工作台”）撑宽，可伸缩的面包屑列被挤到宽度 0；
- `workspace-shell.spec.ts:161-177`：C5 加入处置后，V12 重读的 Review 审核状态仍是 PENDING，截图显示“审核：待审核”加“已关闭（未归档）”。按 FE3 kickoff §6.4 的表，关闭只发生在已通过的提交上，这不是后端可达的形状（FE2 kickoff §7.5）。审核报告把 C5 记为符合，没有发现这一点。

**规则（C12）：**

1. **错误提示：** `ReviewActions` 的错误提示（含错误代码、复制错误代码、“刷新审核信息”）不放在按钮所在的行，改为顶栏主行下方单独一行，占满顶栏宽度；保留 `role="alert"`。错误出现与消失时，按钮的位置和顶栏主行的高度不变；
2. **处置说明：** `ReviewDispositionLine` 独占顶栏的一整行（FE3 kickoff §6.4“下方一行”），不参与各列宽度的计算：“返回工作台”按钮与无处置时同宽，面包屑可见。处置说明紧接顶栏主行，错误提示在它下面，处置说明的位置不随错误出现而移动；
3. **相同的禁用原因只显示一次：** 审核操作组（撤回、退回、审核通过）中两个及以上按钮禁用且原因文字相同时，原因在操作组下方只显示一次，这些按钮的 `aria-describedby` 都指向它；原因不同时，各自显示在对应按钮下，与 C3 的规则一致。原因可以换行，右边缘不超出视口。确认对话框中的按钮不在此列；
4. **程序判据：** 模拟接口用例的截图 helper 在每次截图前断言 `document.documentElement.scrollWidth <= window.innerWidth`，适用于全部截图与两种宽度。V11、V12 另断言 1280 下面包屑可见且宽度大于 0；
5. **V12 的数据：** 重读后的 Review 审核状态为“已通过”（版本号相应前进），V12 断言顶栏显示“审核：已通过”与“已关闭（未归档）”，三个按钮禁用，原因只显示一次。

**不在 C12 内：** 预览页顶栏（`PreviewHeaderActions`，C3 的分隔线）不改，审核报告 N5（1280 下提交的禁用原因被截断）仍随 FE4b 的顶栏调整处理；不改任何文案与业务规则。

**对截图与看图的影响：** 第 3 条改变 owner 在 FE3b D1–D3 看图时接受过的“三个按钮各显示一次原因”。D1–D3 的 `fe3b-d*-review-topbar`、V11 的 `fe3c-review-expired`、V12 的 `fe3c-review-closed`，以及比较脚本找出的其他审核顶栏变化，都列入 §7.3 的看图清单，由 owner 重新看图。owner 已于 2026-11-10 确认这个方向（§10 Q15）。

**复审建议的探针：** 把错误提示放回按钮行（只回退第 1 条），第 4 条的断言应在 V11 或 V12 失败；把 V12 的重读状态改回 PENDING，第 5 条的断言应失败。

### 15.3 看图范围与 C8 的提示颜色

- **看图范围：** 以比较脚本的结果为准（§7.3），不再维护固定的文件清单。审核报告 §2.3 中 C3 另外改动的 10 张、C5 的 2 张因此并入；C12 改动的顶栏同样并入。
- **C8 冲突提示改为灰色 `.form-warning`：** 设计会话同意。冲突提示“归档候选或核验结果已变化，已重新预检”（FE3 kickoff §16.4）说明的是状态已变化、系统已经重新预检，与 `SubmitDialog.tsx` 中“Preview 结果已基于旧基线”同属一类，后者用的也是 `.form-warning`。集合变化提示“候选集合已变化，之前的接受不再适用，请重新核对”要求用户重新接受，保持红色 `.form-error`。两条提示同时出现时颜色不同，区分的是“已自动处理”与“需要你处理”。由 owner 随 C8 截图确认；owner 不接受时改回红色，不影响其他项。

### 15.4 对 FE4a 修复轮与复审的影响

- **转达：** 审核会话把本节转给实施会话，并入当前修复轮（建议编号 F10：§3.8 截图比较脚本与 C4 的第 ① 次稳定性比较；F11：C12），fix1 handoff 一并交付，由审核会话复审第 1 轮。审核报告 F1–F9 不变；F5 的看图清单按 §7.3 改写后的规则生成。
- **修复轮的运行：** 审核报告 §8 第 2 项的“模拟接口全量一次”改为在最终修复候选上同一节点连续两次（§7.2、§7.3 第 ① 次）。**（修订 6 更正）** 原文“C12 只改模拟接口可覆盖的顶栏，不改 `journeys.spec.ts` 与 `t1.spec.ts`，不增加真实旅程或 t1 调试运行”不成立。C12 第 3 条改变了审核操作组中按钮与禁用原因的 DOM 关系，而 `e2e-real/lib/ui.ts` 的 `expectDisabledWithReason` 要求原因是按钮的下一个兄弟元素，`journeys.spec.ts` 中审核操作组的 5 处调用（4 个 scope）因此在证据中失败。正确的要求是：改动 DOM 结构或 class 时，同步核对并修改 `frontend/e2e-real/` 中依赖该结构的定位器，并按 §7.2 安排受影响 scope 的调试。设计会话写这条规则时没有用 grep 核对这一依赖，是设计会话的遗漏；复审第 1–3 轮照此执行。今后设计会话写改动 DOM 的规则时同样先核对，审核按 §11.2 第 10 项核对。处理见 §16。
- **复审：** 核对脚本的自检与节点复验（§3.8）、第 ② 次稳定性比较、C12 的五条规则与 §15.2 的探针、按 §7.3 生成的看图清单。
- **证据：** 证据项不变（§7.2 FE4a 证据行）；证据运行后，审核会话核对第 ③ 次稳定性比较（§7.3）。
- **带入 FE4b：** D2 不再带入；比较脚本与上限由 FE4b 沿用（§7.3 FE4b 一条）；N5 照旧带入。

## 16. FE4a 证据停止的处理（修订 6）

依据：

- [证据核对第 1 轮](reviews/fe4a-evidence-check-1.md)（`fe4a-review` 分支 `14f8daa7f8`）§3–§6；
- [复审第 3 轮](reviews/fe4a-rereview-3.md)（同分支 `35c60972ff`）§5 N20、§7；
- 被测提交 `59c5b8cfca0ae6d07a64a6a4e1645f724fa2ad1f`（`frontend/` 树 `802bdfb1a42b5319b483f3c4324d2b609a1b57b0`，`vnext/` 树 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`）中的 `frontend/e2e-real/lib/ui.ts:132-135`、`frontend/src/features/workbench/ReviewActions.tsx:164-171`、`frontend/src/design-system/components.tsx:12-24`；
- owner 2026-11-11 约 02:28 UTC 的确认（§10 Q18、Q19）。

### 16.1 事实与归类

- **结果：** 04-a 模拟接口全量、04-b 上传包校验、05-t1 通过。04-c 的 20 个 scope 中 16 个通过，失败 4 个：`r7-reviewer-withdraw`、`r11-review-conflict`、`j1-archive-mainline`、`j2-manual-close`；`openapi_compare=match`，`cleanup_status=ok`。
- **原因：** 四处都失败在 `expectDisabledWithReason`，它要求原因是按钮的下一个兄弟元素 `span.disabled-reason`。fix2 `d9fc3b3d56` 按 C12 第 3 条，把审核操作组中相同的原因改为在组下方显示一次的 `span.review-actions__reason`，各按钮的 `aria-describedby` 指向它，但没有改 `e2e-real/`。四个失败页面的快照都是三个按钮禁用、原因文字与期望一致且只显示一次。产品行为符合 C12，失败是候选内真实旅程 helper 没有同步。
- **归类：** 不是后端缺陷；失败发生在被测对象运行之后，不在 DC68 的重做范围。实施会话停止并保留全部产物，处理正确。
- **遗漏：** §15.4 原文（已更正）；复审第 1–3 轮照此执行，没有检查 `e2e-real/` 中依赖按钮与原因 DOM 关系的定位器。
- **设计会话的补充核对（开发主机只读，`59c5b8cfca`）：** `e2e-real/` 中其他与 fix2 改动相关的定位器与候选结构一致：对话框内的 `[role="alert"].form-error`（`journeys.spec.ts:916`、`1150`、`1202`、`1210`、`1256`，错误在对话框打开时仍渲染在对话框内）、`.review-disposition-line`（`1901`、`1930`）、`.review-actions` 容器（`ui.ts:125`、`t1.spec.ts:399`）。受影响的只有 `expectDisabledWithReason` 用在审核操作组的 5 处调用（`journeys.spec.ts:958`、`959`、`1214`、`1546`、`1931`）；其余 9 处对象是上传、提交、撤回提交等按钮，所在 scope 都通过。
- **没有在真实 backend 上执行过的部分：**
  - J1 第 4 步以后与 J2 第 8 步，包括这些步骤中各次预检的异常集合核对；
  - `r7-reviewer-withdraw` 中提交人一侧的核对（指针清除、树状态“已撤回”、可以重新上传）与两侧 `assertClean`；
  - `r11-review-conflict` 的证据截图与两侧 `assertClean`；
  - fix2 的应用代码改动：归档对话框重读后改用重读结果（C8）、错误提示移出按钮行、处置说明独占一行。

  最后一次真实旅程调试是 05 上的 J1/J2（`501fd7469c`），早于 fix2。
- **耗时参考：** 04-c 完整集的套件部分用时约 5.5 分钟（01:51:57–01:57:18）。

### 16.2 修复：fix4（只改测试代码）

> **修订 7：** 本节第 1 项的“两种结构都成立”是错的，遗漏了工作台工具栏的原生按钮，按第 1 项写的 helper 在 05 调试中失败。第 1 项以 §17.2 为准，其余各项不变。

1. **`expectDisabledWithReason(button, reason)` 改为与结构无关（已由 §17.2 取代）：**
   - `toBeDisabled()`；
   - `toHaveAccessibleDescription(reason)`；
   - 按按钮 `aria-describedby` 中的 id 取得所指元素，其中文字等于 `reason` 的元素可见。理由：被 `aria-describedby` 直接引用的隐藏元素仍计入可访问描述，只断言描述时原因被隐藏也能通过。

   两种结构都成立：按钮自带原因时 `aria-describedby` 指向同一 `button-wrap` 内的 `span.disabled-reason`（`components.tsx:15-24`）；共享原因时指向 `.review-actions__reason`。
2. **审核操作组另加一条断言**（名称由实施会话定，例如 `expectReviewReasonShownOnce(page, reason)`）：`.review-actions .review-actions__reason` 计数为 1、文字等于 `reason` 且可见；`.review-actions .disabled-reason` 计数为 0。对应 C12 第 3 条。`journeys.spec.ts` 中审核操作组的每个禁用状态各调用一次，现为 `r7-reviewer-withdraw`、`r11-review-conflict`、`j1-archive-mainline`、`j2-manual-close` 四处。
3. **范围：** 只改 `frontend/e2e-real/lib/ui.ts`、`frontend/e2e-real/journeys.spec.ts` 与 fix4 handoff。不改 `frontend/src/`、`frontend/e2e/`（模拟接口用例）、`t1.spec.ts`、`frontend/scripts/` 下的入口与工具（含 `run-real-backend-e2e.sh`）。需要改其他路径时停下交设计会话。
4. **提交位置：** 在 `fe-vnext`（现为 `59c5b8cfca`）之后，沿用 fix3 的短分支做法；不 rebase，不改写已被引用的提交。复审通过后 `fe-vnext` 快进到 fix4 候选，再开始证据。
5. **fix4 handoff 写明：**
   - diff 范围（`59c5b8cfca..<fix4 候选>`）；
   - 按 §11.2 第 10 项做的 grep 核对：命令与命中；
   - 05 调试日志与 07 运行日志的路径与 SHA256（按 §16.7 取得）；
   - §16.1 列出的未执行部分在调试日志中的落点（scope、步骤、日志行），包括 J1、J2 各次预检的异常集合与 FE3 kickoff §4.6 的表一致。

### 16.3 调试（owner 2026-11-11 确认，§10 Q18）

- **07：** `run-tests.sh`（不带 `--e2e`）一次：类型检查（含 `e2e-real/`）、lint、单测与构建通过。实施会话不跑模拟接口全量：fix4 不改产品代码与模拟接口用例，由复审的一次全量覆盖（§16.4 第 3 项）。
- **05：** 在 fix4 候选的 clean、已提交 worktree 上，经 wrapper 运行 `run-real-backend-e2e.sh --suite journeys --subphase fe3c` **一次**（完整集 20 个 scope，约 6 分钟），会话名 `fe4a-impl`，使用新的日志目录（§16.6）。
  - 不另跑 `--subphase fe4a` 的 J1/J2 调试，不给入口加新的选择项；
  - 不跑 t1：`t1.spec.ts` 未改，§7.2 的一次 t1 调试已经用过。
- **失败处理：** 任一 scope 失败，保留日志、trace 与截图，停下交设计会话，不自行再跑第二次完整集调试。被测对象运行之前的命令、参数或工具错误按 §7.2 的 DC68 处理。
- **不采用：**
  - 甲，只跑 J1、J2：`r7-reviewer-withdraw`、`r11-review-conflict` 要到证据中才首次执行，证据可能再次失败；
  - 乙，给入口加这 4 个 scope 的选择项：要改工具并审核，只省约 4 分钟。

### 16.4 审核：定向复审 fix4

由 FE4a 原审核会话做复审第 4 轮（同一子阶段的 finding 由原审核会话连续复审）。不独立运行真实旅程与 t1。

1. **路径核对与 diff 范围：** 按 §5.2；diff 只含 §16.2 第 3 项的路径。
2. **helper 的区分力探针：** 在已提交的一次性 worktree 中用模拟接口执行，不跑真实 backend。建议做法：临时用例从 `e2e-real/lib/ui.ts` 导入两个 helper，对 V12 或 D1–D3 的模拟审核顶栏断言，另取一个按钮自带原因的禁用按钮作对照；具体由审核会话定。
   - 不改产品代码：两条断言都通过，对照按钮的原因断言也通过；
   - 把 C12 第 3 条回退为各按钮各自显示原因：“只显示一次”的断言失败，原因断言仍通过；
   - 删掉共享原因元素，保留 `aria-describedby`：原因断言失败；
   - 保留共享原因元素但使其不可见：原因断言失败。
3. **07 模拟接口全量一次：** `run-tests.sh --e2e --screenshots`（`GATEWAY_FE_TEST_WORKERS=2`，经 wrapper，会话名 `fe4a-review`）。截图与复审第 3 轮的 `full1`（`59c5b8cfca`）用截图比较脚本的 `--stable` 模式比较，应 exit 0。
   - 两者的 `frontend/` 树不同，但 fix4 不改产品代码与模拟接口用例，截图内容应相同；
   - 这次比较代替 fix4 的第 ①、② 次稳定性比较（§7.3），同时说明 owner 按 `59c5b8cfca` 看过的看图清单仍然适用，不重新看图；
   - 不通过时停下交设计会话（§8）。
4. **核对 05 调试日志：** 20 个 scope 全部通过；`openapi_compare=match`、`cleanup_status=ok`；起止 HEAD 为 fix4 候选、起止 clean；§16.2 第 5 项列出的落点都能在日志中找到。
5. **§11.2 第 10 项**的 grep 核对。
6. **回源** fix4 handoff（§16.7）。

### 16.5 证据（owner 2026-11-11 确认，§10 Q19）

- **四项重跑：** 复审通过后，在 fix4 候选的 clean、已提交 detached worktree 上各运行一次，合计约 30 分钟：
  - 04：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`--suite journeys`（完整集，不带 J1/J2 选择）；
  - 05：`--suite t1`，使用新的 `--log-dir` 与 `--evidence-dir`（复审第 3 轮 §7 第 2 项）。
- **不沿用：** 前端没有沿用机制（§7.2），不为 04-b、05-t1 开沿用例外。`59c5b8cfca` 上通过的三项只作记录，不作 FE4a 证据。
- **次数的解释：** Q11 的“证据跑一次”指在最终候选上各一次。在新候选上重跑 t1 属于证据，不计为第二次 t1 调试运行（§7.2、§8）；journeys 完整集同理。
- **第 ③ 次稳定性比较（§7.3）：** 在新证据之后做，比较 04 证据截图与 §16.4 第 3 项审核会话在 07 上的 fix4 截图，按新的 `frontend/` 树绑定（两者树号必须相同）。
- **审核会话核对证据日志时另补两项：** 证据核对第 1 轮 §2 留下的 05-t1 §8.3 逐条核对与 M1 增量。
- 证据再次失败时按 §8 停止，不在本节授权内追加运行。

### 16.6 证据目录与 `fe-vnext`

- **保留到 FE4a 退出，任何会话不删改：**
  - 04、05 的 `/home/dev/gdds-fe4a-evidence-59c5b8cf` worktree 与 `refs/fe4a-evidence/59c5b8cfca`；
  - `/home/dev/gdds-fe-logs/fe4a-evidence-04/`、`/home/dev/gdds-fe-logs/fe4a-evidence-05/`（含 4 个失败 scope 的 trace 与截图）；
  - `/home/dev/gdds-fe-evidence-04/fe4a-59c5b8cf/`、`/home/dev/gdds-fe-evidence-05/fe4a-59c5b8cf/`；
  - 开发主机 `fe-vnext` 到 `59c5b8cfca` 的快进。
- **新证据用新名字，带 fix4 候选的提交号**（`<短号>` 为 8 位）：
  - worktree `/home/dev/gdds-fe4a-evidence-<短号>`，ref `refs/fe4a-evidence/<10 位提交号>`；
  - 日志 `/home/dev/gdds-fe-logs/fe4a-evidence-<短号>-04/`、`/home/dev/gdds-fe-logs/fe4a-evidence-<短号>-05/`；
  - 截图 `/home/dev/gdds-fe-evidence-04/fe4a-<短号>/`、`/home/dev/gdds-fe-evidence-05/fe4a-<短号>/`；
  - 启动前确认这些路径都不存在。
- 05 的 fix4 调试与 07 的运行同样使用带短号的新目录，不写入任何证据目录。

### 16.7 handoff 中的哈希

- **确认 N20 的做法：** fix4 handoff 与新证据 handoff 中的哈希都从机器生成的清单取得（`.sha256` 旁注、节点现场重算的清单），不手抄；提交前用 §3.8 的回源脚本核对，并在 handoff 末尾附结果。
- **配对受检：** fix4 不改回源脚本（脚本的修正随 FE4b，N20），因此 handoff 改用脚本支持的“路径与 SHA256”写法，使配对关系受检；来源清单中的标签项改为由命令写出、可复算的证据文件，经 `--evidence-file` 提供；不用 `--allow`。
- **回复中不抄哈希：** 实施会话在回复中只给 handoff 提交号与清单路径。59c5b8cfca 证据的停止回复中 7 个 SHA256 有 2 个抄错（日志文件本身与 `.sha256` 旁注一致）。
- 审核会话把本节写进 fix4 与证据的提示词。

### 16.8 本次修改的节

头部（状态）；§1 第 5 项；§7.2（新增 fix4 行，证据行与“t1 调试只有一次”一条补注）；§8 FE4a（调整一条、新增两条、新增“本次停止”）；§10（说明、Q18、Q19）；§11.2（新增第 10 项）；§11.3（补一句）；§13.7；§15.4（更正“修复轮的运行”一条）；新增 §16。其他文档本次不改。

## 17. fix4 调试停止的处理（修订 7）

依据：

- fix4 实施会话的停止报告：候选 X 为 `d12e3b8f706c99c66d0de2e1763f145f95862c92`（分支 `fe4a-fix4`），diff `59c5b8cfca..d12e3b8f70` 只含 `frontend/e2e-real/lib/ui.ts` 与 `frontend/e2e-real/journeys.spec.ts`；
- 05 日志目录 `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-05/`，07 日志目录 `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-07/`；
- 设计会话在开发主机 `/home/dev/gdds-fe4a-fix4`（HEAD 为 X）上只读核对：`frontend/e2e-real/lib/ui.ts:105-112`、`:132-160`，`frontend/src/pages/WorkbenchPage.tsx:528-532`，`frontend/src/features/workbench/UploadStepCard.tsx:333`；
- owner 2026-11-11 约 03:02 UTC 的确认（§10 Q20）。

### 17.1 事实与归类

- **结果：** 07 的 `run-tests.sh`（不带 `--e2e`）通过。05 完整集调试 20 个 scope 中 17 个通过，3 个失败（`r4-submit`、`r7-withdraw`、`r7-approved`），没有 flaky；`openapi_compare=match`，`cleanup_status=ok`，起止 HEAD 为 X、起止 clean。§16 的 4 个目标 scope 全部通过。
- **失败位置：** 三处都停在工作台工具栏“上传”按钮的 `expectDisabledWithReason`，`ui.ts:137` 的“`aria-describedby` 至少指向一个元素”，期望大于 0，实际为 0。它前面的 `toHaveAccessibleDescription(reason)` 已经通过：这些按钮的可访问描述来自 `title`。
- **`e2e-real/` 中禁用原因的三种结构：**

  | 按钮 | 代码位置 | 可访问描述来源 | 可见原因 | 调用处（X 的 `journeys.spec.ts` 行号） |
  | --- | --- | --- | --- | --- |
  | `Button` 组件自带原因 | `design-system/components.tsx:12-24` | `aria-describedby` → 同一 `button-wrap` 内的 `span.disabled-reason` | 同左 | `stepUploadAction`：595、750、866；`compareAction`：815、870、871 |
  | 审核操作组共享原因 | `ReviewActions.tsx:164-171` | `aria-describedby` → `.review-actions__reason` | 同左 | `reviewAction`：959、960、1216、1549、1935 |
  | 工作台工具栏原生按钮 | `pages/WorkbenchPage.tsx:528-532` | `title` | 后面的兄弟元素 `span.disabled-reason`（没有 `id`） | `workshopAction`：590、746、861 |

- **归类：** 设计会话的错误。§16.2 第 1 项断言“两种结构都成立”，只看了前两种；§16.1 已经列出这些调用所在的 scope，却没有核对它们的按钮结构。不是产品缺陷：原生按钮的 `title` 给出了可访问描述，可见原因也在。fix4 仍然只改测试代码。不属于 DC68。
- **调试性质：** X 的运行是调试，不是证据；其中通过的 scope 不代替 §17.3 的运行。

### 17.2 helper 规则（取代 §16.2 第 1 项）

`expectDisabledWithReason(button, reason)` 依次断言：

1. `toBeDisabled()`；
2. `toHaveAccessibleDescription(reason)`：三种结构都成立；
3. **原因可见**，按按钮有没有 `aria-describedby` 分两支，命中的那一支必须通过：
   - **有：** 按 id 取得所指元素，其中文字等于 `reason` 的元素可见（与 X 的实现相同）；
   - **没有：** 按钮后面的兄弟元素中有 `span.disabled-reason`，文字等于 `reason` 且可见（即 `59c5b8cfca` 原 helper 的定位器）。

   两支之间不互相回退：有 `aria-describedby` 而所指元素不符时直接失败，不再去找兄弟元素。

其余不变：

- `expectReviewReasonShownOnce` 与 `journeys.spec.ts` 的调用处不变；
- 只改 `frontend/e2e-real/lib/ui.ts`，范围同 §16.2 第 3 项；
- 新提交接在 X 之后（分支 `fe4a-fix4`），不改写 X；
- 产品代码不改。工具栏原生按钮由 `title` 提供描述，不列为 finding；FE4b 调整工作台工具栏时可以顺带统一为 `Button` 组件，不作要求。

### 17.3 调试（owner 2026-11-11 确认，§10 Q20）

- **07：** 在修正候选上运行 `run-tests.sh`（不带 `--e2e`）一次。
- **05：** 在修正候选的 clean、已提交 worktree 上，经 wrapper 运行 `run-real-backend-e2e.sh --suite journeys --subphase fe3c` **一次**，会话名 `fe4a-impl`，使用带修正候选短号的新目录。不跑 t1。
- 这是 fix4 最后一次获授权的完整集调试。任一 scope 失败即停，保留产物，交设计会话。

### 17.4 复审（补充 §16.4）

- **范围：** `59c5b8cfca..<修正候选>`，含 X 与修正提交，仍只有两个文件；另单独看 `X..<修正候选>`。
- **探针补充工具栏原生按钮：** 在 §16.4 第 2 项四种情形之外，对模拟接口中一个禁用的工作台工具栏按钮：
  - 不改产品代码：原因断言通过；
  - 删掉后面的 `span.disabled-reason`：原因断言失败；
  - 删掉按钮的 `title`：原因断言失败。

  `Button` 组件自带原因的对照（§16.4 第 2 项）保留。
- §16.4 的其余各项不变：07 模拟接口全量一次并与 `full1` 做 `--stable` 比较；核对 05 调试日志；§11.2 第 10 项（含修订 7 补充的 helper 调用处结构核对）；回源。

### 17.5 handoff 与目录

- **fix4 handoff** 覆盖 X 与修正候选：
  - X 的运行作为调试停止记录，写明路径、结果与失败产物；
  - §16.2 第 5 项的落点取自修正候选的运行。
- **保留到 FE4a 退出：**
  - 05、07 的 `/home/dev/gdds-fe4a-fix4-d12e3b8f` worktree 与 `refs/fe4a-fix4/d12e3b8f70`；
  - `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-05/`、`/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-07/`（含 3 个失败 scope 的 trace 与截图）；
  - §16.6 列出的 `59c5b8cfca` 证据产物。
- 修正候选的 worktree、ref 与日志目录用带它的短号的新名字。
- §16.5–§16.7 不变。证据在修正候选（fix4 最终候选）上运行。

### 17.6 本次修改的节

头部（状态）；§8 FE4a（调整两条、新增“fix4 调试停止”）；§10（说明、Q20）；§11.2 第 10 项（补一句）；§13.8；§16.2（开头加修订 7 说明，第 1 项标为已取代）；新增 §17。其他文档本次不改。

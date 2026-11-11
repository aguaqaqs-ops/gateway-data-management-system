# FE4 kickoff：前端收口与业务导航接入

- **状态：** 修订 1，2026-11-10。初稿（`e0082180e0`）经[审核](reviews/fe4-kickoff-review.md)（`6536502a11`，定向修订）后，按审核意见与 owner 2026-11-10 的决定修订（§13、§14）。修订 2（同日）：owner 按建议确认其余问题，并补充决定 BE-b 第二步在 S1a 结束后由后端开始（§10、§13.3）。§10 的问题已全部由 owner 决定。修订 3（同日）：定向复核（[复核报告](reviews/fe4-kickoff-rereview-1.md)，通过）的 R1–R4 与后端记录更正（§13.4）。修订 4（同日）：FE4a 审核（`541febf566`，定向修复）交设计会话的 D1（C4 截图稳定性）、D2（审核模式顶栏在 1280 下横向溢出）与看图范围，owner 2026-11-10 按设计会话的建议确认（§10 Q14–Q16，处理见 §15）。修订 5（2026-11-11）：按 BE-b 第二步候选 `b61cc37d5f` 与前端窄复核同步 §3.1 与 §5.3，owner 同意 B9 退役（§10 Q17、§13.6）。修订 6（2026-11-11）：FE4a 证据运行（被测提交 `59c5b8cfca`）在 04-c 真实旅程完整集停止（[证据核对第 1 轮](reviews/fe4a-evidence-check-1.md)，`fe4a-review` 分支 `14f8daa7f8`，尚未合入 main）：候选的真实旅程 helper 没有随 C12 第 3 条同步。设计会话决定以 fix4（只改测试代码）修复，并安排调试、复审与证据重跑；owner 2026-11-11 确认 fix4 的一次完整集调试与证据重跑的解释（§10 Q18、Q19）；更正 §15.4 的错误说法（处理见 §16）。修订 7（2026-11-11）：fix4 第一个候选 `d12e3b8f70` 的 05 完整集调试有 3 个 scope 失败，原因是 §16.2 写定的 helper 规则不适用于工作台工具栏的原生按钮（设计会话的错误）；改写 §16.2 的 helper 规则，owner 2026-11-11 授权再跑一次完整集调试（§10 Q20，处理见 §17）。**FE4a 已退出（2026-11-11，§5.2 表后的退出记录）：** owner 2026-11-11 05:51 UTC 确认看图与遗留项，附注 tag `fe-fe4a-exit` → `c2199b82f7`，以 `--no-ff` 合入本地 main（`1d1de9d2a4`），tag 已推送，main 未推送。修订 8（2026-11-11）：P7 S1a（`p7-s1a-exit` → `42780a1230`）与 BE-b（`be-b-exit` → `3e5f24583d`）都已本地退出并合入 main。设计会话只读复核 BE-b 的正式交付（§18），据此写定 FE4b 的合入点、依赖镜像、OpenAPI、改动范围、带入项、截图、测试与证据和停止条件（§5.3、§6.5–§6.7、§7、§8、§11.3），新增 owner 问题 Q22–Q25（§10）。修订 8 fix1（同日）：按独立审核（`fe4-kickoff-rev8-review` 分支 `f87b4d07e1`，定向修订，R8-1–R8-7）修订，新增 Q26 与 §19（新流程下 FE4b 的角色与材料）；无记录行复用身份的前端判据交后端答复（§18.2 第 2 项），只阻塞 F5 的该分支（§13.10）。**Owner 补充（2026-11-11，Q26 已决定）：**前端暂不需要固定长程任务的角色分工，无需参考后端角色分配规则。已删除 FE4b 对后端固定角色、工作包与模型家族安排的引用。修订 8 fix2（同日）：按复核意见收紧 F5 的阻塞范围、写明定位截图时机、写全 `fe-handoff` 的三种集成情形（§13.11）。**FE4 当前：** fix2 待审核会话定向复核，之后请 owner 确认 Q22–Q25；确认后合入 main，再写 FE4b 正式提示词。
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
  - AGENTS（main 版本）：“专用测试节点”（DC91 五节点池）、“前端测试（FD7）”、“Docker / Compose 验证”；
  - [Owner 决议](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md) DC91、DC97、DC98。
- **P7 文档的用法：** P7 S0 决议、总体设计、执行计划与 S1a 设计已提交在本地 main（2026-11-10 合入 `p7-s1a-a`，合并提交 `00ca325c2e`，未推送）。S0 决议写明 S0 已收口，owner 已授权 S1a A–G 编码至本地退出；P7 文档没有提到 BE-b。本文只引用其中的事实，以及 owner 2026-11-10 对 BE-b 与 S1a 先后的决定（§4、§10 Q5），不据此推导 BE-b 的设计内容。
- **会话分工（owner 2026-11-11）：**前端暂不需要固定长程任务的角色分工，无需参考后端角色分配规则。本文由前端设计会话维护；交接材料见 §12。FE4a 已完成的角色与记录保留为历史。

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
- **修订 8 更新（2026-11-11）：** 本节前三条记录的是修订 1 时的状态，保留原文。现状：
  - S1a 本地退出：附注 tag `p7-s1a-exit` → `42780a1230`，已在 main 中；
  - BE-b 第二步设计候选 `b61cc37d5f` 经前端定向核对（`f0be08d9ed`，`CHANGES_REQUIRED`）与窄复核（`GO_WITH_NONBLOCKING`，FE-BEB-01–10 关闭，11–13 由后端在 B0/B4 补文字），见 §13.6；
  - BE-b 实施 B0–B5 完成并本地退出：附注 tag `be-b-exit`（对象 `517ce8d4a3`）→ H `3e5f24583d`，即修订时的本地 main 头；产品验证 V `37fe3a87d2`；`vnext/` 树 `2faac9fc1d`；全范围独审最终 GO。本地退出不表示已推送或部署，远端 main 仍为 `16ffe72829`；
  - 交付文档 [BE-b → FE4b 交付](../backend-vnext/refactoring/formal/plans/be-b-frontend-delivery.md) §1–§7 对应 §4 第 1–7 项。设计会话的复核结果见 §18。

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
| B4 | 行定位产物 | **定位：** 读 `row_locator_ref` 的五列 Parquet：`row_identity`、`before_row_index`、`current_row_index`、`before_filter_context_json`、`current_filter_context_json`。<br>**取身份值：**<br>• bundle 有该侧快照时按 index 读行，此时该侧 context 必须为 null；<br>• bundle 缺该侧快照时，从 context（JCS 小对象）取身份值，`{}` 与 `{"<列>":null}` 不匹配；<br>• 缺快照侧的无记录行（修订 8 按正式 Contract 收紧，§18.2 第 2 项）：只在 Business Navigation“无记录行与完整性”的四个条件全部成立时（前端以哪些公开字段判定，待后端答复，§18.2 第 2 项），用有快照侧的身份值执行缺快照侧的谓词（FE-BEB-12）；任一条件不成立时不复用，只按可得侧、已有记录与 context 浏览，并提示“改前对应不可确定”；<br>• 快照中身份值的类型与谓词类型不一致时，作为 bundle 解码错误（FE-BEB-13）。<br>**显示：** keyless 删除行缺少的旧值显示“改前值不可得”，与 NULL 区分。<br>**删除：** `snapshotRowIdentity`、全部规范编码、`validateLocations` 和“本表的变更行无法定位”的匹配路径。<br>**回退：** ref 为 null 时按表级展示（BE-b §4.8 的既定回退），不在浏览器中补算身份 | BE-b §4.8；第二步 §4.2、§5.2；FE2 kickoff §5.3 末条；FE-BEB-08、12、13 |
| B5 | 视图 ID | 前端按 `pair_id` 区分视图，修复前后都不受影响；FE4b 核对代码中没有依赖 History `-p<i>` 形式的逻辑。模拟数据改用第二步 §7 的取值（`baseline_to_initial`、`initial_to_modified`、`left_to_right`、`left_to_middle`、`middle_to_right`），每个 pair 用自己的 `view_id` | BE-b §4.9；第二步 §7 |
| B6 | 诊断编码 | **导航诊断（BE-b §4.7 加第二步 §4.2 的两个新码）：**<br>• 就地提示，分组头汇总个数；<br>• `DEVICE_ROWS_UNASSIGNED` 提供“查看整表”（这是额外入口，不是导航页签），`changed_row_count` 为 null 时显示“变化行数未知”，replacement 下不显示变化行数；<br>• `DEVICE_TAB_FACTS_UNAVAILABLE` 每表一条，target 的 item、tab 为 null，带三个 reason 的文案；<br>• `DEVICE_FILTER_VALUE_UNSUPPORTED` 每个受影响侧一条，指向该表整表项，带三个 reason 的文案。<br>**surface 诊断：**<br>• 按后端交付的完整稳定编码表（[`presentation-diagnostic-codes.md`](../backend-vnext/contracts/presentation-diagnostic-codes.md) 与同源的 `diagnostic-codes.json`）更新文案表，增删与文案见 §18.4（修订 8）；<br>• 删除被取代的原文键、`DUPLICATE_EFFECTIVE_KEY:` 前缀切分、`*Error/*Exception` 正则，以及 `max_risk_tables_per_pair exceeded`、`max_risk_pair_wall_time_seconds exceeded` 两个键（这两条是 pair 失败，不进 READY surface）。<br>未知编码统一用通用文案，原值放 Debug | BE-b §4.7、§4.10；第二步 §4.2、§4.4；FE-BEB-05、06 |
| B7 | Preview 改前公式与装置名 | 双侧浏览表（`device`、`composite_signal_point`）在改前侧逻辑存在时必有 `before_table_ref`：表未变时别名 current，有变时单独导出；新增表的 before 为 null。<br>改前公式与改前侧装置名统一读 before ref，Preview 与 History 一样显示改前、改后对照。<br>删除“改前公式在 BE-b 实现后提供”以及用 current 回填 before 的路径 | BE-b §4.4；第二步 §5.1；前端 kickoff §8；FE-BEB-07 |
| B8 | 移除占位数据 | 删除手写的占位导航与诊断 fixture，以及前端生成器对后端私有符号的导入。后端 fixture 改由后端入口生成，前端 wrapper 只用 subprocess 调用并搬运输出（§5.3）。上传输入改由后端持有，前端模拟数据所用副本按后端清单逐文件核对 SHA256 | 前端 kickoff §4.5；第二步 §8；FE-BEB-10 |
| B9 | 回退退役 | BE-b 之后每个 READY surface 恰好一份导航（第二步 §4.1），“没有导航产物”已不可达。因此：<br>• 删除 `fallbackNavigation` 与 `preview-no-navigation` fixture；<br>• 缺导航或导航多于一份时，按该比较对的 bundle 解码错误处理，与其他 Contract 违例相同；<br>• 原 B9 中“没有注释用标识符”“没有 `display_order` 按 DDL 顺序”两个分支同样不可达，因为 `display_name` 和 `display_order` 为 required，一并删除。<br>原 B9 是前端 kickoff §4.5 确认的正式行为；owner 2026-11-11 同意退役（§10 Q17）。后端须按 FE-BEB-11 删去第二步 §4.1“无导航产物时 B9 回退仍可用”一句 | 前端 kickoff §4.5 第一条；第二步 §4.1；FE-BEB-11 |

Contract 版本：
- 导航仍为 `backend-vnext/business-navigation/v1`，但形状已改，旧占位产物用的也是同一版本串。因此解码器按形状严格校验，拒绝 `row_filter.value` 等旧字段，不按版本串分支。
- Comparison Surface v4、Comparison Bundle v4、CanonicalizationManifest 3.4.0 按各自 selector 精确匹配，不双读旧版本。bundle 的 selector 在安装 tar 时校验 manifest 与 closure 的环节检查，v3 包不进入 OPFS（修订 8，§18.3 第 1 项）。

FE4b 的 fixture、程序判据与截图分工已按第二步写定（§5.3）。修订 8 按 BE-b 正式交付写定其余各项：B1–B9 的 Contract 落点与验收用例见 §5.3 的“前端改动范围”，合入点、镜像与 OpenAPI 见 §6.5–§6.7，截图名见 §7.3。B1–B9 与正式 Contract 的出入及处理见 §18.2。

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
  - 加上依赖 BE-b 的页面（修订 8：页面、截图名与选取规则见 §7.3 FE4b），在 FE4b 实现：侧栏各分组展开、装置页签（按身份过滤）、中文列名与业务列序及固定列、行定位后的修改行连线与风险底色、导航诊断（若 t1 数据产生）。

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
| FE4a 带入项与新后端回归（已退出） | `fe-vnext` 快进到 main `16ffe72829`（§6.1）；§3.4 C1–C12；§3.5 Q21；§3.6 令牌；§3.8 取证工具；在 `t1.spec.ts` 中加入不依赖 BE-b 的参考截图（§3.3）；在 `vnext/` 树 `49c1de43be` 上跑真实 e2e 与 t1（次数按 §7.2） | 本文经定向复核；审核会话按 §11.1 标题重核分支与 tag、现场核对节点、镜像与 `--print-input` 后发出提示词 | `fe-fe4a-exit` | `fe-fe3c-exit..<FE4a 候选>` | 审核通过；证据（§7.2 FE4a 证据行）各一次通过；C4 的三次稳定性比较（§7.3）都通过；§7.3 看图清单中的截图经 owner 确认。不含依赖 BE-b 的页面 |
| FE4b BE-b 接入与正式重拍 | §3.1 B1–B9；§3.2 侧栏；§3.3 正式重拍（含依赖 BE-b 的页面）；按 BE-b 交付合入 main、重新生成 fixture（OpenAPI 不刷新，修订 8 §6.3）；FE4 退出 | `fe-fe4a-exit`；P7 S1a 本地退出并合入 main 之后，BE-b 完成第二步设计与实施、退出并合入 main，§4 的交付齐全；本文第 2 步（FE4b 设计）经审核与 owner 确认 | `fe-fe4b-exit`（即 FE4 退出） | `fe-fe4a-exit..<FE4b 候选>` | 审核通过；证据（§7.2 FE4b 行）各一次通过；正式重拍与 FE4b 截图经 owner 确认 |

- 两段都在 `fe-vnext` 上进行，合入 main 只用快进或合并，不 rebase，不改写已被引用的提交。
- **路径核对（每段都做）：** 设 `<main>` 为最后一次进入 `fe-vnext` 的 main 提交：
  - `git rev-parse <候选>:vnext` 与 `git rev-parse <main>:vnext` 相等；
  - `git diff --name-only <main> <候选>` 只含 `frontend/` 与 `docs/frontend-vnext/` 下的路径（FE4b 合入 `fe-handoff` 时的受限例外见 §6.5）。
- 审核范围中来自 main 的文档与 `vnext/` 不属于前端审核，由后端审核负责。main 上直接提交的 `frontend/` 改动属于前端审核范围：FE4a 期间 main 上出现了两个（`7b16061b2e`、`b79fd4c72f`），纳入 FE4b，见下方 FE4a 退出记录。
- FE4a 期间不合入 main（owner 2026-11-10 已决定，§10 Q2）。P7 S1a 在 main 上改 `vnext/` 不影响 FE4a，被测后端固定为 `16ffe72829`；需要偏离时停下交 owner，实施与审核会话都不自行合入。
- FE4b 的合入点、依赖镜像与比对原件在第 2 步写定（修订 8：§6.5–§6.7）。

**FE4a 已退出（2026-11-11）：**

- **tag 与范围：**
  - 附注 tag `fe-fe4a-exit`（tag 对象 `b98dd9c1c0`）指向证据 handoff `c2199b82f7`（`fe-vnext` 头），审核范围 `fe-fe3c-exit..c2199b82f7`；
  - 证据运行的提交 H 是 fix4 handoff `16f4306306`（修正候选 `26236839f7`），tag 目标与它只差 `docs/frontend-vnext/fe4a-evidence.md`；
  - `frontend/` 树 `d8e9a2e717`；`vnext/` 树 `49c1de43be`，与合入点 main `16ffe72829` 相同（§6.1），路径核对通过。
- **合入 main（§6.4）：** 合入前 main 为 `37fe3a87d2`（main worktree clean，没有进行中的合并或变基）。
  - `4c566a11a9`：`--no-ff` 合入 `fe4a-review` 分支（7 份审核报告，头 `f95a66c800`）；
  - `1d1de9d2a4`：`--no-ff` 合入 tag `fe-fe4a-exit`，`frontend/scripts/run-real-backend-e2e.sh` 自动合并，没有冲突；
  - 合入后 `HEAD:vnext` 等于合入前 main 的 `vnext/` 树 `2faac9fc1d`；相对合入前 main 只改 `frontend/`（27 个文件）与 `docs/frontend-vnext/`（13 个文件）；
  - 合入后 main 的 `frontend/` 树为 `5658a45f21`，与审核会话在 main `8fb7245911` 上的试合并结果相同。它是 FE4a 的改动加上 main 上的两个后端提交（见下），**还没有在任何节点上运行过**。
- **owner 确认（2026-11-11 05:51 UTC，在设计会话中）：**
  - **看图：** 07 `/home/dev/gdds-fe-shots/fe4a-rereview4/full1`（复审第 4 轮在最终 `frontend/` 树上的全量截图，与复审第 3 轮没有内容变化；证据截图经第 ③ 次比较与它绑定），范围按 §7.3，分组按 fix2 handoff §6.4 的 50 个文件：确认；
  - **规则 4 的唯一豁免** `fe3b-w4-approved-withdraw`（1280、1920 下顶栏都溢出 12 px，禁用原因被截断）：接受，随 FE4b 的 N5 修复并删除豁免；
  - **C8：** 灰色冲突提示（`.form-warning`）与红色集合变化提示同屏（`fe4a-c8-both-notices`，§15.3）：接受；
  - **N11**（关闭成功后输入仍可编辑）：接受现状；
  - **N15**（“收起”在正文下一行，缩进 4 px）：接受现状；
  - **main 推送（§10 Q12）：** 本次只推送 tag，不推送 main；
  - **后端改 `frontend/`：** 今后后端改 `frontend/` 前，先告知前端设计会话（见下“main 上的 `frontend/` 提交”）。
- **证据运行**（04、05 各在 clean detached worktree `/home/dev/gdds-fe4a-evidence-16f43063` 上，被测提交 H，各一次，没有 DC68 重做）：

  | 节点 | 运行 | 结果 | wrapper 日志 | SHA256 |
  | --- | --- | --- | --- | --- |
  | 04 | 04-a 模拟接口全量 runner（含截图，`GATEWAY_FE_TEST_WORKERS=2`） | exit 0；单测 35 个文件 214 项，e2e 96 通过；198 张截图 | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/fe4a-evidence-04-run-tests-20261111T043941Z.log` | `088da58cc4fd0834c20d2e4f3b8acfe4a12ae85028a78ff8ad1d9e4c95a1f2f5` |
  | 04 | 04-b 上传包的后端校验 | exit 0；4 个包，`failures=0` | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/fe4a-evidence-04-validate-upload-package-20261111T044322Z.log` | `b1d4932eab7697969cf0e54811492c200f3ac254a9b3f6bc9f120a7d081094f1` |
  | 04 | 04-c 真实 backend `--suite journeys`（完整集） | exit 0；20/20，`openapi_compare=match`，`cleanup_status=ok` | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/fe4a-evidence-04-run-real-backend-e2e-20261111T044548Z.log` | `94da0b0f3b9430aed5cc86b10639a650be5f05ffb28ec08b2ff907edc2339ce2` |
  | 05 | 05-t1 真实数据 `--suite t1` | exit 0；1 通过，`table_count=125`，`composite_changed=0`，两份 t1 清单各 19 个文件核对通过 | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/fe4a-evidence-05-run-real-backend-e2e-20261111T044048Z.log` | `3a450ca0b666f3549f0b0d729201d98d89653c655d0f789c35bd79b4d42d954e` |

- **核对结果**（[证据核对第 2 轮](reviews/fe4a-evidence-check-2.md) §2、§3）：
  - J1、J2 共 8 次预检的异常集合与 FE3 kickoff §4.6 一致，`business_issues` 都等于 `anomalies` 去掉 ASE 与 PIE；
  - t1 符合 FE3 kickoff §8.3：v1 Preview 125、125、0、0；v2 FULL 恰好两对；`initial_to_modified` 为 125 张表、变化 4；`composite_changed=0`，同一 `vnext/` 树上没有后端 t1 结果，没有对照；14 张参考截图齐全（不作验收）；
  - M1：t1 第 1 步 MODIFIED_ONLY 的 renderer 增量 19,300,352 字节（18.41 MiB），为 FE3a 24.86 MiB 的 0.74 倍；第 4 步 FULL 只报告；
  - C4 三次稳定性比较都通过：第 ①、② 次由复审第 4 轮复审第 3 轮 `full1` 对本轮 `full1` 的 `--stable` 比较代替（§16.4 第 3 项）；第 ③ 次为 04 证据截图对 07 `/home/dev/gdds-fe-shots/fe4a-rereview4/full1`，exit 0，内容变化 0，噪声 19 张（每张最多 56 个像素、连通块 10）；
  - 打包流程筛查（§7.4）为空，没有跑 t4。
- **截图：** 198 张（1280、1920），在 04 的 `/home/dev/gdds-fe-evidence-04/fe4a-16f43063/shots/`；清单 `/home/dev/gdds-fe-evidence-04/fe4a-16f43063/shots/shot-files.txt` SHA256 `3db69cef9dc15ac8adeece2d52ce061f108ac4b754db384ebbaa4a77f233aa35`。它是 FE4b 的比较原件（§7.3）。
- **停止与修复经过：**
  - 第一次证据（被测提交 `59c5b8cfca`，fix3 handoff）在 04-c 完整集停止：真实旅程 helper 没有随 C12 第 3 条同步（证据核对第 1 轮；修订 6，§16）；
  - fix4 第一个候选 X `d12e3b8f70` 的 05 完整集调试有 3 个 scope 失败：§16.2 写定的 helper 规则不适用于工作台工具栏的原生按钮，属设计会话的错误（修订 7，§17）；
  - 修正候选 Y `26236839f7` 的 05 完整集调试 20 个 scope 全部通过，复审第 4 轮通过，证据在其 handoff H 上四项重跑通过。
- **依据：** [审核](reviews/fe4a-review.md)：定向修复；[复审第 1 轮](reviews/fe4a-rereview-1.md)、[第 2 轮](reviews/fe4a-rereview-2.md)：定向修复；[复审第 3 轮](reviews/fe4a-rereview-3.md)：通过；[证据核对第 1 轮](reviews/fe4a-evidence-check-1.md)：停止，转 fix4；[复审第 4 轮](reviews/fe4a-rereview-4.md)：通过；[证据核对第 2 轮](reviews/fe4a-evidence-check-2.md)：通过。handoff：`fe4a-handoff.md`、`fe4a-handoff-fix1.md`–`fe4a-handoff-fix4.md`、`fe4a-evidence.md`。
- **main 上的 `frontend/` 提交（设计会话决定，采纳审核会话试合并后的建议）：**
  - **事实：** main 在 `16ffe72829` 之后有两个后端提交改了 `frontend/scripts/run-real-backend-e2e.sh`：`7b16061b2e`（P7 S1a F：入口改用 `vnext/scripts/tests/runtime_config_fixture.py` 生成运行时根目录与 Compose override `compose_runtime`）与 `b79fd4c72f`（清理时调用 fixture 的 `--cleanup`，失败时保留现场并 exit 非 0，新增 `main_exit_code`）。按本节，它们属于前端审核范围；
  - **不阻塞 FE4a 退出：** 两者不在 FE4a 的被测树上（被测后端固定在 `16ffe72829`，§10 Q2），tag 目标与证据不受影响，合并没有冲突；
  - **纳入 FE4b：** FE4b 第 2 步设计时把这两个提交列为前端审核对象，FE4b 的调试覆盖新入口；FE4b 审核范围 `fe-fe4a-exit..<FE4b 候选>` 经由 main 包含它们；
  - **owner 决定（2026-11-11）：** 今后后端改 `frontend/` 前先告知前端设计会话。已按 owner 要求写入 AGENTS“前端测试（FD7）”一节。
- **带入 FE4b 的项**（证据核对第 2 轮 §6）：
  - N5：预览页顶栏禁用原因溢出；修复后删除规则 4 的豁免 `fe3b-w4-approved-withdraw`；
  - N19：比较脚本自检对 Paeth 预测函数没有区分力；
  - N20 与 N25：回源脚本的配对范围（`` `路径`，SHA256 `值` `` 与表格单元格内的路径不配对；标签项改为可复算的证据文件；报告“有路径却未配对”的文件哈希）；
  - N26：证据提示词写明设置 `GATEWAY_FE_LOG_DIR`；
  - N27：wrapper 的 `exit_code` 字段（04-b 记 `wrapper_field_missing`）与 `busy_end` 的记录时机（在释放后记录，或改名为 `busy_before_release`）；
  - N24：C12 第 1 条（对话框关闭后的审核错误提示移到 `.compare-header__notice`）在真实旅程中没有覆盖，只由模拟接口 V12 覆盖；FE4b 如果构造过期通过或 `ARCHIVE_CLOSED` 场景，可以补上；
  - §17.2 的可选项：工作台工具栏的原生按钮统一改为 `Button` 组件；
  - 复审第 2 轮 N14（截图 helper 的溢出断言只在开截图时执行）、N17（`ReviewActions` 错误提示的清除时机与 `errorNoticeHost` 无回退）；
  - 审核清单补充（证据核对第 1 轮 §4）：DOM 结构改动时 grep `e2e-real/` 中的定位器，并核对共享 helper 全部调用处的结构（§11.2 第 10 项，FE4b 同样适用）；
  - 上一条中 main 上的两个 `frontend/` 提交。
- **不带入：** N21–N23（handoff 文字与计数小误），值已由审核会话现场核对，不出勘误。
- **保留到 FE4 退出：**
  - 04：`/home/dev/gdds-fe-evidence-04/fe4a-16f43063/`（FE4b 的比较原件）、`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/`；
  - 05：`/home/dev/gdds-fe-evidence-05/fe4a-16f43063/`、`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/`（含 t1 参考截图）；
  - 07：`/home/dev/gdds-fe-shots/fe4a-rereview4/`（owner 看图的对象与证据截图副本）、`/home/dev/gdds-fe-logs/fe4a-rereview4/`；
  - 开发主机：`/home/dev/gdds-fe4a-handoff/`（证据回源用的清单副本）。
- **FE4b 起点：** `fe-fe4a-exit`（tag 对象 `b98dd9c1c0` → `c2199b82f7`，`frontend/` 树 `d8e9a2e717`），main 合入提交 `1d1de9d2a4`。

### 5.3 FE4b 的第 2 步

BE-b 第二步与 Contract 固定后，前端设计会话修订本文。修订 5 按第二步候选 `b61cc37d5f` 与前端窄复核（`GO_WITH_NONBLOCKING`，§13.6）先写定下列各项；后端 B0 落 Contract 或 B4 交付时如有出入，以正式 Contract 为准重新同步。

**fixture 的重新生成（第二步 §8，FE-BEB-10、11）：**

- **生成入口：** 后端入口 `vnext/scripts/generate-presentation-fixtures.py --input-root <绝对路径> --output-root <外部空目录>`。在专用测试节点的 clean、已提交 worktree 中，以后端 uv 环境调用。修订 8 按交付 §3 写定：
  - 命令以交付 §3 的原文为准：`UV_OFFLINE=1 CARGO_NET_OFFLINE=true` 下先用 `uv-consume.sh` 同步 `vnext/backend`，再用该环境的 `.venv/bin/python` 调入口；输入根为 worktree 内的 `vnext/fixtures/presentation-inputs`，输出根在 worktree 外（例如 `/home/dev/gdds-test-tmp/fe4b-fixtures-<提交>-a`）；
  - 同步时按 AGENTS“跑测试”一节使用 `--reinstall-package gateway-compute-python` 与 `GATEWAY_RUST_BUILD_INPUT=<HEAD:vnext/rust 的 tree id>`，随后用 `check-rust-extension-build-input.sh` 核对已安装扩展，不一致即停止；
  - **节点：** 需要后端 uv 缓存、Rust 工具链与 Cargo registry，用 05（或已预填充的 06）；07 没有后端环境与依赖镜像，不在 07 生成；
  - 入口要求 clean、已提交的 worktree，并自行检查提交来源；生成在节点上的 detached worktree 中进行，输出取回开发主机后再替换到实施 worktree。
- **wrapper：** 前端 `generate-backend-bundle-fixture(s)` 改为只用 subprocess 调这个入口，并把 `<output>/backend/` 整体替换到 `frontend/src/test/fixtures/source/backend/`，不再导入后端私有符号。修订 8 补充：
  - wrapper 在调用前检查参数（绝对路径、输出目录不存在或为空、worktree clean），在调用后按输入清单的 `required_output_directories` 与 `required_root_outputs` 核对输出，缺项即非 0 退出；
  - 记录生成所在的提交、`HEAD:vnext` 树、节点 hostname，以及输出目录全部文件的 SHA256 清单；
  - 同一提交连续生成两次，两份输出逐文件比较相同后才替换；替换后 `source/backend/` 与输出的 `backend/` 逐字节相同，不编辑生成产物。输出根下 `backend/` 之外的索引文件含生成提交，跨提交比较时不要求它相同；
- **上传输入：** 由后端持有，位于 `vnext/fixtures/presentation-inputs/` 与 `manifest.json`，从 FE4a 核对基线 `59c5b8cfca` 的 `frontend/src/test/fixtures/source/upload-inputs/` 原字节复制。前端模拟数据所用副本逐文件按清单 SHA256 核对。修订 8 补充：
  - 由前端单测读取后端清单 `vnext/fixtures/presentation-inputs/manifest.json`，对 8 个原件逐个核对 SHA256，取代 `upload-inputs.test.ts` 中手写的 `SOURCE_SHA256` 常量；
  - **输入通路（修订 8 审核 R8-2）：** `run-tests.sh` 现在只归档 `HEAD:frontend`，容器里没有 `vnext/`。FE4b 把 runner 的归档改为同一 HEAD 的 `frontend` 加两个文件 `vnext/fixtures/presentation-inputs/manifest.json`、`vnext/fixtures/presentation-inputs/diagnostic-codes.json`，容器内解包后两文件位于前端根目录的 `../vnext/fixtures/presentation-inputs/`，单测按这个相对路径读取，只读；runner 日志记录两文件的 SHA256。不复制整个 `vnext/`，也不在前端保存副本。F8 的编码集合单测走同一通路；
  - 后端另增的 `sql-{baseline,initial,modified}-canonical.sql` 只用于 fixture 生成，不复制到前端；
  - 真实旅程的派生输入 `e2e-real/fixtures/upload-inputs/`（FE3a Q10，`gid INT NULL`）与后端的 canonical 派生件不同，两者都是合法输入；FE4b 不改它，真实旅程的输入不变（§18.2 第 6 项）。
- **目录清单：** 输出须覆盖下列目录，缺项即失败：
  - `fe2a/{preview-full,preview-modified-only,preview-replacement,history-three-nodes}`、`fe2b/preview-workbench-normal`；
  - `pairs/…`，以及 `source/backend/` 顶层的 `manifest.json`、`artifact-closure.json`（`build-golden-bundle-fixture.mjs` 读取）；
  - 第二步 §8 列出的新增场景。修订 8：交付的输入清单列出 11 个，位于 `backend/scenarios/` 下：`identity-changes`、`duplicates-orphans`、`text-identities`、`integer-boundary`、`schema-keyless`、`table-addition`、`comment-only`、`formula-unchanged-device`、`identity-unrecorded-exact`、`excluded-identity`、`missing-identity-column`；
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

修订 8 补充模拟 HTTP 数据（`features/dev/mock-data.ts` 等）的两条：
- HTTP 响应中的 ArtifactRef（`SourceArtifactResponse`、`PreviewArtifactRefResponse` 等）一律用 `a1:<location>:<64 位小写十六进制>` 形式：S1a 之后后端在这两个响应模型上校验该格式（§6.6），旧的 `fixture-…` 等写法已不可达；
- History 比较结果中的 `pair_id` 与对应 bundle 一致，用稳定 pair 名（`left_to_right`、`left_to_middle`、`middle_to_right`），删除 `fe2a-history-fixture-p0/p1`。

浏览器不重算 `surface_digest`，surface 摘要由后端 golden 负责（第二步 §6，FE-BEB-04）。

**程序判据（t1，在两种宽度的截图运行中同时断言；FE-BEB-03）：**

1. **导航形状：** 每个比较对恰好一份导航；普通模式固定五组；B1 的三条唯一性成立。
2. **不可见的表：** 不出现在任何页签中的 surface 表，都满足：
   - bundle 中有绑定的各侧 `table_content_bindings.row_count` 为 0；
   - surface `change_kind` ∈ {`UNCHANGED`, `BUSINESS_EQUIVALENT`}；
   - `RiskReport` 中该表无风险。
   不再要求“每张表都出现在可见页签中”。
3. **按侧覆盖（不藏行）：** 对每张有筛选页签的共享表，只核 bundle 有该侧快照、且该表筛选页签为 `EXACT` 的一侧。该侧全部已发布谓词覆盖的行集合（取并集，不能把各页签计数相加）的大小，加上同侧 `DEVICE_ROWS_UNASSIGNED.row_count`，等于该侧行数。缺快照侧由后端 Contract 测试负责。
4. **行定位：** 有 `row_locator_ref` 的表全部定位（修订 8 按审核 R8-3 改写）。只针对已发布的 STANDARD 普通行记录（`ROW_ADDED`、`ROW_DELETED`、`ROW_MODIFIED`），ordered、blank 与 schema 记录按原语义，不进入本条：
   - **逻辑存在侧：** `ROW_ADDED` 只有 current，`ROW_DELETED` 只有 before，`ROW_MODIFIED` 两侧都有；
   - **逻辑存在且 bundle 有该侧快照：** index 合法，命中该侧快照中恰好一行，该侧 context 为 null；
   - **逻辑存在而缺该侧快照：** index 为 null；该表发布了筛选页签时 context 必须非 null 且为合规的 JCS 对象，否则为 null；
   - **逻辑不存在侧：** index 与 context 都为 null；
   - locator 中的身份集合与已发布 STANDARD 普通行记录的身份集合相等，没有重复；
   - 该表已发布的 STANDARD 普通行记录非零而 `row_locator_ref` 为 null，判为不符（只有真实零记录的表才允许 null）；
   - 没有出现表级回退。
   回退的表数与 `TABLE_FALLBACK` 页签数只报告。

修订 8 补充判据的实现与范围：
- **实现位置：** `e2e-real/lib/` 下的独立 helper，读取浏览器下载并安装的同一份 bundle（或旅程中经 API 取回的 tar）。可以复用产品的 tar 与 Parquet 解码库，但不调用 view-model 中的筛选、定位与汇总函数，避免用被测代码证明自己；
- **t1：** 对 v1 Preview、v2 FULL 的两个比较对与 History 比较的每个 surface 断言 1–4。判据只依赖数据，与截图宽度无关，每个 surface 断言一次即可；
- **journeys：** 同一 helper 对旅程中下载的每个 bundle 断言 1–4；
- **报告：** 每个 surface 的导航页签数、`TABLE_FALLBACK` 页签数、表级回退表数、有 locator 的表数与定位行数，写入 handoff。BE-b 在同一 V 上的 t1 实测（交付真实链 handoff）为：v1 没有普通行定位；v2 FULL 1 张表 6 行；History 2、3 节点各 1 张表 6 行。FE4b 的 v1 Preview 与 v2 FULL 使用相同的 t1 目录与 `vnext/` 树，定位表数与行数预期相同；不同时在 handoff 中标出并交设计会话判断，不自行解释。History 的节点构成与 BE-b 的链不一定相同，只并列报告。

**截图分工：** 截图名见 §7.3 FE4b（修订 8）。
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

**合入点：** BE-b 退出并合入后的 main，同时带有 S1a 与 BE-b。路径核对同 §5.2。修订 8 写定：见 §6.5（含与设备目录 `fe-handoff` 的先后，§10 Q22）。

**修订 8 写定的其余各项（原“仍待 BE-b 交付后写定”）：**

| 原待定项 | 落点 |
| --- | --- |
| 合入提交与依赖镜像 | §6.5、§6.7 |
| OpenAPI 刷新与比对原件 | §6.3 FE4b 一条：不刷新 |
| 按 §4 第 7 项的变化说明确认要改的地方 | §6.6 与下面的“前端改动范围” |
| 依赖 BE-b 的页面截图名与 owner 看图项 | §7.3 FE4b |
| FE4b 的实施与审核提示词 | §11.3 草稿要点；正式提示词在审核与 owner 确认之后写 |
| 核对后端已按 FE-BEB-11–13 修订第二步与 Contract | §18.1：三项都已落到正式 Contract |

**前端改动范围（修订 8，按交付 §7 的 S1a 与 BE-b 分栏）：**

“S1a”“BE-b”一列标明该项来自哪一侧的变化。验收用例中的场景名指 §5.3 目录清单中的生成目录。所有反例都由生成的 fixture 变异得到（改一个字段），不手写整份产物；同构反例按 AGENTS“测试性能红线”收敛为共享参数表。

| # | 改动 | 来源 | 依据（正式 Contract） | 主要位置 | 验收用例 |
| --- | --- | --- | --- | --- | --- |
| F1 | **bundle 解析：** manifest 与 closure 的 `bundle_contract_version` 精确等于 `backend-vnext/comparison-bundle/v4`；closure kind 增加 `ROW_LOCATOR`，与 `PROJECTION`、`DIAGNOSTICS` 和表 ref 一样核对 raw SHA 与大小；`artifact_id` 按不透明字符串与 closure 条目逐字匹配，不解析 `a1:` 的 location，不按前缀推断类别；多 root 只影响后端存放位置，前端看到的仍是 bundle 内的 `logical_path` | S1a（a1、多 root）；BE-b（v4、ROW_LOCATOR） | Comparison Bundle“当前版本 v4”“P7-S1a 生效补充”；Comparison Surface“Refs” | `features/bundle/posix-tar.ts`、`presentation.ts` | 17 个生成目录全部能安装与解码；v3 包被拒（BE-d 向量，§18.3 第 1 项）；`ROW_LOCATOR` 条目的 SHA 改一位被拒；surface 中某个 ref 的 `raw_sha256` 或 `size_bytes` 与 closure 条目不同被拒 |
| F2 | **surface v4：** selector 精确匹配；`columns` 为两侧并集，`present_in`、`pinned`、`display_order` 必填，`display_order` 是 0 起的排列；`table_content_bindings` 三项与对应 table ref 同为 null 或同非 null；`row_locator_ref`；replacement 各侧 `display_name` 与列；恰好一个 `BUSINESS_NAVIGATION` projection，`risk_summary_ref` 为 null；不重算 `surface_digest` | BE-b | Comparison Surface“当前版本 v4”“SurfaceTable”“语义摘要与 raw 完整性” | `features/view-model/model.ts` | 缺导航、两份导航、`display_order` 不连续、binding 与 ref 不同为 null，各一个反例，都按该比较对的 bundle 解码错误处理 |
| F3 | **导航解码的严格不变量：** 本节“模拟数据规则”的七条与 B1 的三条唯一性；谓词 `values` 非空、同类、去重并按规定排序，两侧不同时为 null；未知 `group_key` 按通用分组显示 | BE-b | Business Navigation“载荷与唯一性”“双侧筛选与标量” | `model.ts` | 每条不变量一个反例（共享参数表）；`preview-replacement` 与普通场景各自满足互斥关系 |
| F4 | **筛选与标量：** 按侧执行；整数按同侧 `gateway.sta.enc.v1` metadata 确定类型，规范十进制文本转 BigInt 并核 safe 范围；字符串原值比较；身份值类别与谓词不一致即解码错误；NULL 与缺列不匹配 | BE-b | Business Navigation“双侧筛选与标量”（FE-BEB-13） | `features/view-model/table-rows.ts` | `integer-boundary`、`text-identities`、`excluded-identity`；单测：负零、前导零、空白、小数、指数、超范围、字符串“7”对整数谓词 |
| F5 | **行定位：** 读五列 locator，按程序判据 4 的矩阵区分记录种类与逻辑存在侧；有快照的逻辑存在侧按 index 读行且 context 必须为 null；缺快照侧解析 context（`{}` 与 `{"列":null}` 不匹配）；无记录行是否复用身份待后端答复后写定（§18.2 第 2 项），答复前该分支不实现；ref 为 null 时表级展示；删除 `snapshotRowIdentity`、规范编码、`validateLocations` 与“本表的变更行无法定位”路径 | BE-b | Row Location 全文；Business Navigation“无记录行与完整性” | `table-rows.ts`、`pages/ComparisonPage.tsx` | 复用分支待答复后补用例，预期正向落在 `duplicates-orphans` 缺 before 快照的共享表（`device_cfg`、`device_st`，`EXACT`），反向落在 `identity-changes`（抑制增删、`TABLE_FALLBACK`）；`identity-unrecorded-exact` 的共享表有 before 别名，只能验证 gid 与地址变化的归属，不能证明复用分支执行过；`preview-modified-only` 的 `keyless_demo`（删除行“改前值不可得”）；`schema-keyless`（keyless 多副本）；单测：有快照侧 context 非 null、index 越界、重复 identity |
| F6 | **双侧列：** 按 `present_in` 在缺列一侧显示“该侧无此列”，与 NULL 区分；列序按 `display_order`；固定列按 `pinned`；中文名按 `display_name`，Debug 另显示标识符 | BE-b | Table Presentation；Comparison Surface“当前版本 v4”第 2、3 条 | 表格组件、`ComparisonPage.tsx` | `schema-keyless` 的 `device_st.before_only`；`comment-only` 的中文名 |
| F7 | **局部事实与表级标记：** `EXACT` 与 `TABLE_FALLBACK`（“此页签按整表提示”）；`table_scope` 参与页签、项、组汇总与“只看变化/风险”，不涂到各行；`SECONDARY_DEVICES` 中 `item_kind=TABLE` 的整表项 | BE-b | Business Navigation“局部事实与表级事实” | `model.ts`、侧栏 | `identity-changes`、`table-addition`、`schema-keyless` |
| F8 | **诊断文案：** 12 个导航码与两个 reason 族；surface 码表按 §18.4 增删；删除前缀切分、类名正则与英文短句键；未知编码用通用文案，原值放 Debug | BE-b | Presentation 稳定编码 | `features/view-model/diagnostics.ts` | 单测读取 `diagnostic-codes.json`：导航码集合与各码 params 键集合、`surface_summary_codes` 集合分别与文案表全等；`duplicates-orphans`、`excluded-identity`、`missing-identity-column` 的就地提示 |
| F9 | **双侧浏览表：** 改前公式与改前侧装置名读 `before_table_ref`；删除“改前公式在 BE-b 实现后提供”与用 current 回填 before 的路径 | BE-b | Comparison Bundle“当前版本 v4”第 2 条；Composite Signal Device | `formula-view.ts`、`ComparisonPage.tsx` | `formula-unchanged-device`（`device` 的 before 别名 current，`composite_signal_point` 有变化） |
| F10 | **replacement 分侧：** 读 `replacement_sides`；浏览状态、URL 与整表视图键带 `side`；分侧标题取本侧 `display_name` | BE-b | Business Navigation“Replacement” | `commands.ts`、侧栏 | `preview-replacement` |
| F11 | **fixture 与删除：** 本节“fixture 的重新生成”；删除手写导航、诊断 fixture、`fallbackNavigation`、`preview-no-navigation` 及其用例；模拟 HTTP 数据用 a1 ID 与稳定 pair 名 | S1a（a1）；BE-b | 交付 §2、§3 | `frontend/scripts/`、`src/test/fixtures/`、`features/dev/mock-data.ts` | 两次生成逐字节相同；审核会话独立再生成一次，与提交的 `source/backend/` 相同（§11.3）；`grep` 不再出现 `fallbackNavigation`、`preview-no-navigation`、`fe2a-history-fixture-p` |
| F12 | **侧栏（§3.2）：** 单视图不显示分段控件；单页签的项直接打开表，表名在信息行；空组隐藏；搜索匹配项名、页签名、表的显示名与标识符 | BE-b | §3.2；Business Navigation“载荷与唯一性” | 侧栏组件 | `preview-modified-only`（单视图）；`preview-full`（两视图）；`duplicates-orphans`（3 个页签）；搜索单测 |
| F13 | **仅注释与 `NO_CANONICAL_CHANGE`：** 仅注释的 Preview 照常显示（表都是 UNCHANGED，中文名随注释变化）；提交返回 `NO_CANONICAL_CHANGE` 时的文案改为“本次组态与基线一致，没有可提交的变更。注释等展示信息的变化不单独保存，将随下一次业务变化一起保存。”（前端无法判断是否只改了注释，所以对该码统一显示） | BE-b | 交付 §3；Table Presentation | `features/workbench/SubmitDialog.tsx` | `comment-only` 与返回 `NO_CANONICAL_CHANGE` 的模拟提交 |

F1–F13 都不改 OpenAPI 快照与生成的类型（§6.3）。范围外的事项见 §3.9；带入项见 §18.5。

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
- **FE4b：** BE-b 交付的树的原件与变化说明由 BE-b 的后端交付方提供（§4 第 5、7 项），按 FE3 kickoff §5.1、§5.2 比对（修订 8 写定不刷新，见下条）。
- **FE4b 写定（修订 8）：不刷新快照，也不重新生成类型。**
  - **比对原件：** 交付 §5 的生产原件 `/home/dev/gdds-stage-exchange/be-b/b5-real-37fe3a87d2/t1/production-openapi.json`（06，同一 V 的生产 Compose 响应原字节，79082 字节，SHA256 `ce58f20a209883983d270e6f9d758044a22ce35e15e11eee137d1595f92ac079`）。t4 的原件与 FE3c 原件（`/home/dev/gdds-reviews/artifacts/p6-openapi-6368c9c40c/production-openapi.json`）原字节与它相同。
  - **设计会话复核（2026-11-11）：** 在开发主机重算三份原件的 SHA256 均为上值；按 FE3 kickoff §5.1 规范化后为 146666 字节，SHA256 `4c2ddca7d64ec77029528f5a6f03f73b17185784091530c7086fa67d484d620a`，与 `fe-fe4a-exit:frontend/openapi.json` 和 main 的快照逐字节相同。后端机器索引 `/home/dev/gdds-stage-exchange/be-b/b5-frontend-openapi-audit.json`（SHA256 `6bfd316bf044b108aecc8257bd63ace62fc1366d2e62fee71a0d498cff0fc991`）记录的四个 diff 都为空。
  - **为什么 OpenAPI 不变而 HTTP 行为有变化：** S1a 在两个响应模型上加了 `artifact_id` 校验器，在写请求上加了 503 `SERVICE_NOT_READY` 的两种 `details.reason`（§6.6）。前者是 pydantic 校验器，后者是错误详情的取值，都不进入 schema。
  - **运行时比对照旧：** 每次真实运行在浏览器用例之前，把运行时 `/openapi.json` 与快照规范化后逐字节比较，不一致即停止（§8 FE4b）。

### 6.4 合入 main

- **FE4a 退出：** 附注 tag `fe-fe4a-exit` 指向 FE4a 证据 handoff。先把审核报告合入本地 main，再以 `--no-ff` 合入 tag。main 届时可能已有 P7 的文档或代码；FE4a 只改 `frontend/` 与 `docs/frontend-vnext/`，预期没有冲突，由审核会话先试合并。
- **FE4a 的推送（owner 2026-11-10 已决定，§10 Q12）：** 退出时推送 tag `fe-fe4a-exit`。main 是否推送随后端的推送节奏由 owner 决定；届时 main 会带上 P7 的内容。
- **FE4b 退出（FE4 退出）：** 按 §19 的材料约定：退出只入库一页总结，tag `fe-fe4b-exit` 指向 `fe-vnext` 上的总结提交，再以 `--no-ff` 合入 main。修订 8 的建议（§10 Q25，待 owner 确认）：退出时推送 tag `fe-fe4b-exit`；它指向的提交包含 S1a 与 BE-b 的全部提交，推送 tag 会把这些对象一并推到远端，但不移动远端 main。main 是否推送由 owner 按后端节奏另定。
- tag 与合入由设计会话在 owner 确认后执行；推送只按 owner 的决定或授权执行。

### 6.5 FE4b 的合入点（修订 8）

- **起点：** `fe-vnext` 为 `c2199b82f7`（`fe-fe4a-exit` 的目标），是 main 的祖先。
- **合入点：** 快进到 `be-b-exit` 的目标 `3e5f24583dee3d3c44705e4ef34557890557568b`（`git merge --ff-only`），不 rebase，不改写已被引用的提交。设计会话已核对：`c2199b82f7` 是它的祖先，可以快进；它的 `vnext/` 树为 `2faac9fc1da9a6fd15eddef894f5c6e1652fba95`，与 BE-b 产品验证 V `37fe3a87d2` 相同。
- **与设备目录 `fe-handoff` 的先后（§10 Q22，按审核 R8-1 后的事实改写，待 owner 确认；分析见 §18.7）。** 按建议甲（FE4b 作为集成线）：
  - FE4b 从 `3e5f24583d` 开始，不等 `fe-handoff`；`fe-handoff` 经其自身审核（代码、单测、模拟 e2e 与截图）通过后，在 FE4b 最终候选之前以 `--no-ff` 把审核通过的提交合入 `fe-vnext`，只此一次，冲突由实施者解决并写入 handoff；
  - 合入的 `fe-handoff` 提交须满足：`git diff --name-only 3e5f24583d <该提交>` 只含 `frontend/` 与 `docs/` 下的路径，`vnext/` 树仍为 `2faac9fc1d`。不满足即停下交设计会话；
  - 三种情形（合入前的 `journeys` 调试不覆盖 `fe-handoff`）：

    | 情形 | FE4b 的真实旅程 | `fe-handoff` 的真实回归 | `fe-handoff-exit` 与进入 main | 目录任务 `dir-v1` 阶段 2 的放行 |
    | --- | --- | --- | --- | --- |
    | 1 在 FE4b 第一次 `journeys` 调试之前合入 | 第一次调试即覆盖两者 | 由 FE4b 的 `journeys` 调试与证据覆盖（证据的被测提交即 FE4b 最终候选） | 执行 FE4 退出的会话在 owner 确认 FE4 退出时，把 `fe-handoff-exit` 打在被合入的 `fe-handoff` 审核通过提交上，tag 说明引用 FE4b 证据与最终候选；随 FE4b 的退出合入 main，并通知 `dir-v1` | FE4 已退出 |
    | 2 在第一次 `journeys` 调试之后、最终候选之前合入 | 合入后须再跑一次完整集调试，计为 §7.2 的第二次（第二次已用掉时交 owner）；t1 不加调试，由 t1 证据覆盖 | 同上 | 同上 | FE4 已退出 |
    | 3 最终候选之前未合入 | FE4b 不带它继续，不相互等待 | FE4 退出后，`fe-handoff` 合入当时的 main，按其 kickoff 自行完成真实回归 | 按其原 kickoff，由其审核会话合入 main、打 tag | FE4 已退出，且 `fe-handoff` 已验证并进入 main |

  - 情形 1、2 改变了 owner 已确认的 `fe-handoff` kickoff（真实回归的位置、合入 main 的时点与 tag 的执行者），随 Q22 交 owner 确认，并在该任务的提示词中同步；不能让该任务继续按旧的退出指令执行；
- **路径核对（§5.2）：** 设 `<main>` 为最后一次进入 `fe-vnext` 的 main 提交：
  - `git rev-parse <候选>:vnext` 等于 `2faac9fc1da9a6fd15eddef894f5c6e1652fba95`；
  - `git diff --name-only <main> <候选>` 只含 `frontend/` 与 `docs/frontend-vnext/` 下的路径；合入了 `fe-handoff` 时，另允许它自身改动的路径（其 kickoff §2：`docs/device-directory/` 下的 handoff 与 `docs/frontend-vnext/frontend-kickoff.md`），这是 FE4b 路径核对的唯一例外。
- **不合入之后的 main：** FE4b 期间不合入 main 的后续提交（`fe-handoff` 按上条经它自己的提交进入）。main 再改 `vnext/` 时，是否跟进由 owner 决定，实施与审核会话都不自行合入。
- **推送：** `3e5f24583d` 尚未推送（远端 main 仍为 `16ffe72829`）。FE4b 的开发、调试与取证都在本地与测试节点之间经局域网传递代码，不需要推送；FE4b 退出时的推送见 §6.4 与 §10 Q25。
- **审核范围：** `fe-fe4a-exit..<FE4b 候选>`。其中来自 main 的 S1a、BE-b、设备目录与 AGENTS 文档，以及全部 `vnext/` 改动，不属于前端审核。属于前端审核的 `frontend/` 改动：
  - FE4b 自身的提交；
  - main 上的两个后端提交 `7b16061b2e`、`b79fd4c72f`（§18.6）；
  - 若合入了 `fe-handoff`：它已由自身的审核会话审过，FE4b 审核只核合并冲突的解决，以及 FE4b 的改动是否破坏它的行为（会话启动、顶栏设备位置、真实旅程的会话注入）。
- **起点的 `frontend/` 树：** `3e5f24583d:frontend` 为 `5658a45f21`，即 FE4a 退出合入后的树（FE4a 的 `d8e9a2e717` 加上两个后端提交），**还没有在任何节点上运行过**（§12）。FE4b 第一次真实 backend 调试就是它的首次运行。

### 6.6 S1a 与 BE-b 对前端的变化（修订 8）

依据交付 §7 与同输入机器索引 `/home/dev/gdds-stage-exchange/be-b/b5-frontend-delta/index.json`（SHA256 `94a78f6459f9aa455c4b9f1a747705c52a407633bc4ac5fbc2016fc3656248ae`，设计会话已重算），加上设计会话对 `16ffe72829..3e5f24583d` 中 `vnext/backend/src/gateway_backend/http/` 的只读核对。

| 面 | S1a | BE-b | 前端处理 |
| --- | --- | --- | --- |
| OpenAPI | 规范化后不变 | 规范化后不变 | §6.3：不刷新 |
| HTTP 行为（不进 schema） | `PreviewArtifactRefResponse`、`SourceArtifactResponse` 的 `artifact_id` 按 a1 格式校验；7 个写路由在临时存储不可用时返回 503 `SERVICE_NOT_READY`（`details.reason=root_unavailable`），上传在存储容量不足时同样返回 503（`capacity_rejected`）；History bundle 的 checkpoint ID 不合法时报完整性错误 | 无 | `SERVICE_NOT_READY` 已有通用文案（FE3 起），不新增分支；模拟数据用 a1 ID（F11） |
| bundle tar 成员 | t1 v1 同输入样本 354→354，11 增 11 删（ID 改写引起的路径变化） | 354→356，13 增 11 删：新增导航与导航诊断 2 个成员，其余为路径变化；History 稳定 pair 名取代 `operation-pN` | 前端按 closure 条目定位，不依赖具体路径（F1） |
| manifest 与 closure 字段集合 | 顶层 11、递归 62、closure 递归 34，不变 | 同左，不变；selector v3→v4，closure kind 增加 `ROW_LOCATOR` | F1 |
| ArtifactRef 与摘要 | 四个字段不变；`artifact_id` 改为 `a1:<location>:<64hex>`，混合 root；被改写 JSON 的 raw SHA 变化，经完整性传递改变 surface 与 bundle 摘要 | 沿用 a1；surface v4 的语义摘要以内容 binding 取代表文件 raw SHA，排除 locator ref | 前端不重算 surface 摘要，只核 ref 与 closure 一致（F1、F2） |
| surface | selector 与字段不变 | v4：递归字段 118→148（新增 30）；列并集与三个展示字段；`table_content_bindings`、`row_locator_ref`；恰好一个导航；稳定 pair 与 view ID、稳定编码 | F2–F10 |
| fixture | 无 | 后端持有输入与生成器，五类 golden | F11 |
| 依赖与镜像 | `repository_service/uv.lock` 与 Dockerfile 改动（`3b1a707cb6`），RS 依赖镜像变为 `lock-b47d6de3cbce` | 未改依赖输入 | §6.7 |
| 真实旅程入口 | `7b16061b2e`、`b79fd4c72f` 改 `run-real-backend-e2e.sh` | 无 | §18.6 |

`tar_stream.py` 自 BE-d 互通向量的后端候选 `0ba45e5ef8` 以来没有改动，tar 帧格式不变；向量中的 manifest 是 v3，处理见 §18.3 第 1 项。

### 6.7 依赖镜像与节点（修订 8）

| 镜像 | tag | OCI config digest | DiffID |
| --- | --- | --- | --- |
| backend 依赖 | `gateway-backend-deps:lock-578e079b762e`（与 FE4a 相同） | `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939` | 19 个 |
| RS 依赖 | `gateway-p2r1-repository:lock-b47d6de3cbce`（FE4a 为 `lock-6dc9659f0aee`） | `sha256:567e7bf95a9a226efb7e557260d494b63c1f3c865de53eb6860c181703db9c13` | 19 个 |

- **身份来源：** 交付 §4 的完整索引 `/home/dev/gdds-stage-exchange/be-b/b5-real-37fe3a87d2/image-identities-v2/identities.json`（SHA256 `923de66a5a9ebb3ef1d49768e6aa9467a4699afad3f1474ce9ce24343dedbacf`），逐条列出全部有序 DiffID。比较一律用 config digest 与全部 DiffID，不比较 `docker inspect` ID。
- **设计会话的只读核对（2026-11-11）：** 在 04（`gw-dms-test-04`）与 05（`gw-dms-test-05`）上把 `docker save` 的输出流式读入 `python3 -I`（不落盘），两个镜像的 config digest 与 19 个有序 DiffID 都与索引一致。07（`gw-dms-07`）没有这两个镜像；07 只跑静态检查与模拟接口，用不到。三台都有工具链镜像；npm 缓存归档 SHA256 均为 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`（04、07 在 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`；05 在 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，解开于 `/home/dev/gdds-fe-cache/fe0/npm-cache`，FE4a 的 05-t1 即用它）。05 有 t1 目录 `/home/dev/gateway-real-dumps/source-dirs/{t1-v1,t1-v2}` 与清单。核对时三台都没有占用标记。
- **每次运行前现场核对：** 实施与审核会话在所选节点上重新核对上表两个镜像（方法同上）、工具链镜像与 npm 缓存，并运行 `--print-input`，必须得到 `gateway-backend-deps:lock-578e079b762e`；传给真实 backend 入口的 RS 依赖镜像必须是 `lock-b47d6de3cbce`。缺失或不符即停止，按 DC67 从 CT201 经局域网预填充并在 handoff 记录来源、摘要与时间，不使用转发代理。
- **fixture 生成节点：** 生成需要后端 uv 缓存、Rust 工具链与 Cargo registry（§5.3），用 05；改用 06 时先核对这些缓存。
- 其他池内节点首次使用前，按 DC67 预填充并核对身份（§7.1）。

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
| FE4b | t1 证据运行一次，同时产生正式重拍截图（§3.3）；调试与判据见下面三行（修订 8） | 见下面三行 |
| FE4b 调试（实施会话；修订 8，次数待 owner 确认，§10 Q23） | **fixture 生成：** 05 上同一提交连续两次，逐文件相同后才替换（§5.3）。它不运行真实数据，不计入下面的次数；合入点变化（§6.5）后须重新生成一次，同样连续两次。<br>**模拟接口：** focused 用例按需；送审前在最终候选上、同一节点连续两次全量 `run-tests.sh --e2e --screenshots`（`GATEWAY_FE_TEST_WORKERS=2`），作为 §7.3 第 ① 次稳定性比较。<br>**`--suite journeys`：** 完整集，**最多两次**。第一次在 bundle 解析、导航、表格与行定位都改完之后；第二次只在以下任一情形：第一次失败并修复之后；`fe-handoff` 在第一次之后才合入（§6.5 情形 2）。两种情形都出现时，仍最多两次，超出交 owner。入口须接受 FE4b 的子阶段名（建议 `fe4b`），选择范围等同 `fe3c` 的完整集；FE4a 加的 J1/J2 调试选择不用。<br>**`--suite t1`：最多两次。** 第一次验证程序判据（§5.3）与截图的选取（§7.3）；第二次只在第一次失败，或之后又改了 `t1.spec.ts` 或判据 helper 时。<br>`validate-upload-package.sh` 不在调试中跑：FE4b 不改上传包与校验。<br>超过上述次数时停下交设计会话，由 owner 决定 | 调试；通过后送审 |
| FE4b 审核（独审，§19；修订 8） | 阶段末全范围独审：模拟接口全量一次（第 ② 次稳定性比较）与探针（§11.3）；fixture 核对：在 05 上用实施会话的 wrapper 独立生成一次 fixture，与候选中的 `source/backend/` 逐文件比较；**不独立跑真实旅程与 t1**，核对实施会话的调试日志、判据输出与截图 SHA256 | 审核 |
| FE4b 证据（修订 8） | 审核通过后，在最终候选的 clean、已提交 detached worktree 上各运行一次：04 上 `run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`--suite journeys`（完整集 20 个 scope）；05（或另一个按清单核对过 t1 目录的节点）上 `--suite t1`，同时产生正式重拍截图、程序判据输出与 M1。证据停止后在新候选上重跑时，四项都重跑（同 §10 Q19），不计为调试次数 | 证据；耗时只报告 |

- 调试与取证分开（DC30）：调试只跑 focused 与受影响的真实数据段；证据只在审核通过后运行。
- **只跑 J1、J2 需要改入口：** `run-real-backend-e2e.sh` 现在只能用 `--subphase fe3b`（18 个 scope）或 `fe3c`（完整集 20 个）选择范围，不能只选 J1、J2。FE4a 在入口中加一个只运行这两个 scope 的调试选择，并让入口接受 FE4a 的子阶段名；具体形式由实施会话定，审核会话审核。证据运行不带该选择，跑完整集。
- FE4a 证据仍跑四项各一次：前端没有沿用机制，`frontend/` 树变了，模拟接口全量必须重跑；backend 树也变了，`journeys`、`t1` 与上传包校验要在新树上各跑一次。
- **FE4b 证据同样四项各一次（修订 8）：** 理由同上；另外 FE4b 改了 bundle 解析，每个下载 bundle 的旅程都受影响，所以 `journeys` 跑完整集而不是只跑受影响的 scope。
- **FE4b 的 t1 调试为什么给两次（修订 8，§10 Q23）：** FE4a 的 t1 调试只加了截图；FE4b 要在 t1 中新增四条程序判据、6 个依赖 BE-b 的截图页面，并且是新前端对新后端（S1a、BE-b）的第一次真实数据运行，第一次就暴露问题的可能性较大。FE4a 的 05-t1 证据从启动到收尾约 4 分 13 秒（wrapper 日志 04:40:48–04:45:01 UTC）；FE4b 加入截图与判据后会略长。只用 t1，不涉及 t2–t4。
- **两段共同：** 只报告 t1 第 1 步 MODIFIED_ONLY 的 renderer 增量；不做计时，不用 t2–t4；打包流程没改就不跑 t4（§7.4）。不另加重复采样或性能测量（DC98）。
- **FE4a 的 t1 调试只有一次（FE4b 的次数见上表与 §10 Q23）：** 需要第二次 t1 调试运行时（例如第一次失败，或之后又改了 `t1.spec.ts`），停下交设计会话，由 owner 决定，不自行追加。失败属于 DC68 的工具或取证错误时，按下条处理。在新候选上重跑的 t1 证据不计为调试运行（修订 6，§16.5）。
- **失败与重做：** 按 AGENTS（main）“专用测试节点”的 DC68，原文如下：

  > **DC68 工具/取证错误（Owner 2026-11-08 修订）：**首次失败后，同一具体故障允许最多三轮自行修复、适用独审与受影响步骤复验；不因被测对象已经运行就立即交 owner。每轮先停止该次执行、保留原始失败及日志/SHA、确认收尾，再固定修订稿复验；三轮仍未解决、原因/副作用不明或超出既有授权时交 owner。不得无修改自动重试、改预期掩盖结果或跳过身份/缓存前提；产品 finding 按阶段已有修复与停止规则办理。只读后处理/预检、代码传输准备的不计次数澄清继续适用。

  细则见 testing-conventions 的 DC68 现行规则。已确认的构建或环境故障（非产品逻辑）优先按 AGENTS“构建故障快速修复（Owner 2026-11-10）”处理，不占用上面的调试次数；其他取证错误按 DC68；产品问题按本文 §8 与审核流程处理，不按 DC68 重做。

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
- **FE4b：** 模拟接口截图的比较沿用同一脚本、同一上限与同样的三次稳定性比较；FE4a 到 FE4b 的变化清单以 FE4a 证据截图为比较原件：04 `/home/dev/gdds-fe-evidence-04/fe4a-16f43063/shots`（清单 `shot-files.txt`，SHA256 `3db69cef9dc15ac8adeece2d52ce061f108ac4b754db384ebbaa4a77f233aa35`）；07 上有按该清单逐文件核对过的副本 `/home/dev/gdds-fe-shots/fe4a-rereview4/evidence-04-copy`。其余见下面的“FE4b（修订 8 写定）”。真实 backend 的 t1 截图不用该脚本判定（数据与时间不固定），按 §3.3 看图。设计会话 2026-11-11 核对：04 原件 198 张、清单 SHA256 与上值相同；07 副本 198 张。

**FE4b（修订 8 写定）：**

- **稳定性比较：** 三次，规则同 C4：① 实施会话在最终候选、同一节点连续两次全量；② 审核会话独立全量与 ① 比较；③ 04 证据截图与复审通过的候选在 07 上的截图比较（`frontend/` 树必须相同）。
- **FE4a 到 FE4b 的变化清单（比较模式）：** 以上面的 FE4a 证据截图为比较原件，与最终候选的全量截图比较。实施会话在 handoff 中列出全部“内容变化”“尺寸不同”与“缺失”的文件并按原因分组，审核会话用同一脚本复核。预期的原因：
  - **fixture 重新生成：** 生成 fixture 的输入换成后端的 canonical 派生件（`yc_list` 的值文本不同）、ID 与 pair 名改变，差异浏览页的截图内容会变；
  - **导航与侧栏（§3.2，F12）、列（F6）、行定位（F5）、诊断（F8）、改前公式（F9）**；
  - **N5：** `fe3b-w4-approved-withdraw` 与同一顶栏的其他截图（§18.5）；
  - **退役（缺失）：** `navigation-fallback`（B9）；`tab-overflow` 依赖占位导航的页签，生成的 fixture 中单项最多 3 个页签（§18.2 第 7 项），若没有 fixture 能在 1280 或 1920 下触发页签溢出，该截图退役，理由写入 handoff；溢出逻辑由组件单测覆盖，t1 的 `fe4-t1-device-tabs`、`fe4-t1-forward-channel` 只在实际溢出时算作补充覆盖；
  - **合入 `fe-handoff` 时（§6.5）：** 只由 `fe-handoff` 引起的文件（包括它新增的截图），比较原件改为 `fe-handoff` 自身的 04 证据截图，结果应为“相同”或“噪声”；FE4b 改到的，按 FE4b 的原因列出。
- **新增的模拟接口截图（1280、1920 各一张，共 19 个名字、38 个文件；合入 `fe-handoff` 时另加最后一行，共 20 个名字、40 个文件）：** 场景名指 §5.3 的生成目录。

  | 截图名 | 场景 | 画面 |
  | --- | --- | --- |
  | `fe4b-nav-two-views` | `fe2a/preview-full` | 两个视图的分段控件；侧栏只显示非空的组 |
  | `fe4b-nav-single-view` | `fe2a/preview-modified-only` | 单视图，不显示分段控件 |
  | `fe4b-device-tabs` | `duplicates-orphans` 的 `device:composite`（3 个页签；普通装置 `device:addr:49` 只有 2 个） | 多页签的项与页签栏 |
  | `fe4b-single-tab-item` | `fe2a/preview-full` | “其他表”中单页签的项：不显示页签栏，表名在信息行 |
  | `fe4b-sidebar-search` | `fe2a/preview-full` | 侧栏搜索命中页签名或表的显示名（查询词写入 handoff） |
  | `fe4b-columns-pinned` | 实施会话选一个 `display_name` 与列名不同、且有固定列的表，写入 handoff | 中文列名、业务列序与固定列 |
  | `fe4b-before-only-column` | `schema-keyless` 的 `device_st` | 改后侧“该侧无此列” |
  | `fe4b-keyless-before-unavailable` | `fe2a/preview-modified-only` 的 `keyless_demo` | 删除行“改前值不可得” |
  | `fe4b-located-rows` | `fe2a/preview-full` 的 `initial_to_modified`：有 `row_locator_ref` 且含修改记录的表（实施会话选定，写入 handoff） | 定位后的修改行对；该表有行级风险时显示风险底色 |
  | `fe4b-formula-before` | `formula-unchanged-device` | Preview 公式抽屉的改前、改后对照与改前侧装置名 |
  | `fe4b-gid-change` | `identity-unrecorded-exact` | gid 变化后，装置页签按改前 gid 与改后 gid 分别命中的行 |
  | `fe4b-duplicates` | `duplicates-orphans` | `DEVICE_ADDRESS_DUPLICATE`、`DEVICE_GID_DUPLICATE` 就地提示与分组头计数 |
  | `fe4b-orphans-view-table` | `duplicates-orphans` | `DEVICE_ROWS_UNASSIGNED` 提示，“查看整表”打开后的整表视图 |
  | `fe4b-table-fallback` | `identity-changes` | `TABLE_FALLBACK` 页签的“此页签按整表提示”与 `DEVICE_TAB_FACTS_UNAVAILABLE` |
  | `fe4b-table-scope` | `table-addition` | 表级标记在页签、项与组上。该场景的 `device_st` 为零行，不能证明“不涂到各行”，这一点由 `identity-changes` 的非空表加组件断言覆盖（F7） |
  | `fe4b-filter-unsupported` | `excluded-identity` | `device_st` 的整表项与两侧各一条 `DEVICE_FILTER_VALUE_UNSUPPORTED` |
  | `fe4b-count-unknown` | `missing-identity-column` | `DEVICE_TAB_COUNT_UNKNOWN` 提示 |
  | `fe4b-comment-only` | `comment-only` | 仅注释变化的 Preview：表都无变化，中文名来自注释 |
  | `fe4b-no-canonical-change` | `comment-only` 加返回 `NO_CANONICAL_CHANGE` 的模拟提交 | F13 的提交提示文案 |
  | `fe4b-preview-topbar-device` | 只在合入 `fe-handoff` 时：Preview 模式的已通过提交（同 `fe3b-w4-approved-withdraw`），用 `fe-handoff` 的跳转会话 | N5 修复后，带设备位置与禁用原因的顶栏不溢出（§18.7） |

  replacement 分侧与 History 三节点已有截图（`dataset-replacement-browse`、`s3-header-history`、`formula-history` 等），随变化清单进入看图，不另起新名。
- **t1 正式重拍（真实数据，1280、1920）：** 沿用 §3.3 FE4a 的 7 个名字，加上下面 6 个（`fe4-t1-forward-channel`、`fe4-t1-nav-diagnostics` 视数据而定），共 11–13 个名字、22–26 个文件。选取规则固定，选中的 `group_key`、`item_key`、`tab_key`、`table_id` 写入 handoff：

  | 截图名 | 时机与选取 |
  | --- | --- |
  | `fe4-t1-nav-groups` | 第 4 步 v2 FULL 的 `initial_to_modified`：侧栏展开全部非空的组（转发通道、规约通道、全局参数三组只在真实数据中出现） |
  | `fe4-t1-device-tabs` | 第 1 步 v1 Preview（在 M1 取值之后）：`SECONDARY_DEVICES` 中页签最多的项（并列取后端顺序第一个），打开其第一个有行的页签。审核核对：v1 的装置项最多 12 个页签，而 v2 FULL 只有 3 个 |
  | `fe4-t1-forward-channel` | 第 1 步 v1 Preview（在 M1 取值之后）：`FORWARD_CHANNELS` 中页签最多的项（并列取第一个；v1 最多 10 个页签）；没有该组则不拍，在 handoff 中写明 |
  | `fe4-t1-columns` | 第 4 步 v2 FULL 的 `initial_to_modified`：按导航顺序第一张既有 `display_name` 与列名不同的列、又有固定列的表 |
  | `fe4-t1-located-rows` | 第 4 步 v2 FULL 的 `initial_to_modified`：有 `row_locator_ref` 的表（BE-b 同输入实测 1 张，`b1_n2_iec104_syx_list`；v1 与 `baseline_to_initial` 都没有 locator），打开后滚到第一条定位的记录 |
  | `fe4-t1-nav-diagnostics` | 任一比较对有导航诊断时，第一个有诊断的比较对中按后端顺序的第一条就地提示；都没有时不拍，handoff 记录各比较对的诊断数为 0 |

  截图仍在 M1 测量窗口之外（§3.3），不增加旅程步骤。`fe4-t1-device-tabs`、`fe4-t1-forward-channel` 在某个宽度下页签溢出时，同时断言溢出控件可用、经它能到达最后一个页签；不溢出时如实记录该宽度未溢出，不算覆盖页签溢出（由组件单测覆盖）。
- **FE4b 交 owner 看图的范围：**
  1. 上面变化清单中的全部文件，按原因分组；
  2. 新增的 38 个（合入 `fe-handoff` 时 40 个）模拟接口截图文件；
  3. t1 正式重拍的全部文件（22–26 个）；
  4. N5 修复后的 `fe3b-w4-approved-withdraw`（1280、1920），截图 helper 中规则 4 的豁免已删除；
  5. F13 的提交提示文案（`fe4b-no-canonical-change`）。

  模拟接口截图：owner 看复审通过的候选在 07 上的截图，证据运行的截图由第 ③ 次稳定性比较与之绑定，不另看。t1 截图：正式重拍以 t1 **证据运行**的截图为准（§3.3），审核会话核对文件名齐全与 SHA256 后交 owner 看；t1 截图的数据与时间不固定，不能用比较脚本绑定，调试运行的 t1 截图只作参考。

### 7.4 t1 与 M1

- **t1：** FE4a、FE4b 都跑（次数按 §7.2）：backend 树（FE4a 为 `49c1de43be`，FE4b 为 BE-b 的树）与前端都有变化。步骤、判据与输入核对按 FE3 kickoff §8.1–§8.3：两份清单逐文件核对，预期值从被测树读取，FULL 的两个比较对按 `pair_id` 取用，`baseline_to_initial.table_count` 记录实际值。
- **M1（FE3 kickoff §8.4；owner 2026-11-10 决定的范围，§10 Q11）：**
  - 两段都只报告 t1 第 1 步 MODIFIED_ONLY 的 renderer 增量，与 FE3a t1 v1 的 24.86 MiB 并列；超过 2 倍时在 handoff 中标出，交设计会话。FE4b 另与 FE4a 证据的 18.41 MiB 并列（修订 8）；
  - 第 4 步 FULL 不再报告（FE3 的“只报告、不可比较”一项取消）；
  - 不做计时，不用 t2–t4。
- **t4 重测只在打包流程改变时触发：** 在有 `t4-v1` 目录的节点上用新浏览器重测 t4 v1 的 MODIFIED_ONLY 与 FULL，各 3 次，按 FE3 kickoff §8.4 的标准判定。FE4a 与 FE4b 都不计划改打包流程。判断分两步：
  1. **筛查：** 审核会话运行 `git diff --stat <范围起点>..<候选> -- frontend/src/features/workbench/upload-package.ts frontend/src/features/workbench/UploadStepCard.tsx`。为空则不触发；
  2. **判断：** 非空时，审核会话读 diff，判断打包流程是否改变：`upload-package.ts` 中的 `collectLocalDirectory`、`buildTar`、`buildSourcePackage`，或 `UploadStepCard.tsx` 中打包阶段的代码（从 `begin("packaging")` 到下一阶段开始）。只有这些改变时才触发 t4 重测。例如 C1 若在上传开始处清除续做提示而改到 `UploadStepCard.tsx`，不触发。
- **打包代码的位置：** 在 `features/workbench/upload-package.ts` 与调用它的 `features/workbench/UploadStepCard.tsx`。FE3 kickoff §8.4 与 §11 Q23 理由 ② 写的 `features/upload/` 在仓库中不存在。按实际路径复核：`fe-fe3b-exit..fe-fe3c-exit` 中两个文件都没有改动，Q23 理由 ② 的结论成立，FE4 不需要补测；`fe-fe3a-exit..fe-fe3b-exit` 中只有 `087281ce65` 改了 `UploadStepCard.tsx`，内容是给按钮加禁用原因，不涉及打包流程。
- **FE4b 的 t4 判断（修订 8）：** 筛查范围为 `fe-fe4a-exit..<FE4b 候选>`，合入了 `fe-handoff` 时它的改动也在其中（它的“尚无数据”提示可能改到工作台，但不应改打包代码）。设计会话核对：`fe-fe4a-exit..3e5f24583d` 中这两个文件没有改动。FE4b 的范围（F1–F13）不含打包流程，预期筛查为空、不跑 t4。BE-b 的 t4 导航正确性由后端负责，前端不重复（§3.3）。

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

**FE4b：** 原则（修订 5 时已定）：

- BE-b 的 Contract 或产物与第一步不一致，不自行适配，交 owner 转后端；
- 需要在浏览器中重新计算行标识、按表名推断分组或列序时，停下交设计会话。

修订 8 写全如下。

*合入点与输入：*
- 快进失败；进入 `fe-vnext` 的 main 提交不满足 §6.5 的条件；候选的 `vnext/` 树不是 `2faac9fc1d`；路径核对出现 §6.5 允许范围以外的路径；
- 合入 `fe-handoff` 的提交不满足 §6.5 的条件；合入 `fe-handoff` 时的冲突需要改变它的会话启动或凭据处理（这两部分归 `fe-handoff` 的实施会话，见其 kickoff §6）；
- `--print-input` 不是 `lock-578e079b762e`；两个依赖镜像、工具链或 npm 缓存缺失或身份不符（§6.7）；构建需要访问网络；
- 运行时 `/openapi.json` 与快照规范化后不同（§6.3）；
- fixture 生成：入口失败、输出缺少清单要求的目录、两次生成不完全相同，或上传输入副本与后端清单的 SHA256 不符（§5.3）。不改输入、不编辑生成产物、不放宽清单，保留两份输出交设计会话；
- 生成的 fixture 或真实 bundle 违反 §5.3 的解码不变量（即后端产物与 Contract 不符）：保留产物，交设计会话，由 owner 转后端；不在前端放宽解码。

*Contract 与设计：*
- 实现需要 Contract 没有提供的字段，或 Contract 有两种读法而 fixture 不能区分：停下交设计会话，不自行假设；
- 无记录行复用身份的分支（§18.2 第 2 项）：后端答复并经设计会话同步本文之前，该分支不实现、不送审；其他不依赖它的内容照常实施、审核与送审。FE4b 的最终全范围审核与退出之前，须已完成答复、设计同步与该分支的实现及审核；做不到时交设计会话，由 owner 决定；
- 需要在浏览器中重新计算行标识、按表名推断分组或列序（原则）；
- 改动需要改变 FE3 kickoff 已定的业务规则，或 §3.2 的侧栏规则。

*真实数据与调试次数：*
- `journeys` 或 `t1` 的调试超出 §7.2 的次数；
- 真实旅程发现后端缺陷，或 J1、J2 某次预检的异常集合与 FE3 kickoff §4.6 不符：保留日志与 trace 交设计会话，判断为后端问题时由 owner 转后端，不在前端绕过，不改 `vnext/`；
- t1 输入核对不符，FE3 kickoff §8.3 的预期值读不到或实测不符，或 §5.3 的程序判据 1–4 任一不成立；
- 新入口（`7b16061b2e`、`b79fd4c72f`）的运行时 fixture 创建或清理失败（`cleanup_runtime=failed`，入口保留现场）：保留现场与日志交设计会话，不手工删除保留的目录；
- 打包流程按 §7.4 判断为改变，但 t4 重测不能在同一阶段完成。

*截图：*
- 稳定性比较三次中任一不通过，且原因不是被测提交的缺陷：保留两次运行的截图与比较输出交设计会话，不改上限、不重跑到通过为止；
- 新增截图在 1280 或 1920 下横向溢出（规则 4 不再有豁免）；
- t1 截图的选取规则（§7.3）找不到对象，且该截图不是写明视数据而定的两个：交设计会话。

*其他：*
- 需要修改 `vnext/` 下的任何文件，或需要后端新增字段或接口；
- 清理核对失败。

## 9. 风险

- **FE4 的退出排在 S1a 与 BE-b 之后：** 按 owner 2026-11-10 的决定，BE-b 第二步设计与实施都等 S1a 本地退出并合入 main，FE4b 再等 BE-b。任何一环推迟，FE4 都无法退出。FE4a 退出后，前端停在一个已取证的状态。owner 可以在 FE4a 退出时决定是否先把 FE4a 的结果作为 Phase 8 shadow 的前端候选；这不改变 FD8。
- **S1a 改变前端看不到的产物形态：** `artifact_id` 格式、bundle 交付与摘要的变化不出现在 OpenAPI 中（§2.3）。由 §4 第 7 项的变化说明与重新生成的互通 fixture 覆盖；说明缺失时 FE4b 不开始。
- **P7 改动 `vnext/` 后 FE4a 想跟进：** 按 §5.2，FE4a 期间不合入 main。
- **C7 让真实旅程变长：** 每次接受都走界面。用调试运行的实测评估；明显变长时报告，不删减步骤。

## 10. owner 决定

修订 7 及以前的问题已全部由 owner 决定（日期见各修订）；修订 8 新增的 Q22–Q25 待 owner 确认，Q26 已由 owner 决定，见本节末的“修订 8 待决定”：

- 修订 1：在审核会话中决定 Q2、Q5、Q10–Q13（审核报告 D1–D5）；
- 修订 2：按建议确认 Q1、Q3、Q4、Q6–Q9，并补充决定 BE-b 第二步在 S1a 结束后由后端开始（改写 Q5）；
- 修订 4：FE4a 审核交设计会话的 D1、D2 与看图范围，按设计会话的建议确认 Q14–Q16（§15）；
- 修订 5：2026-11-11 同意 B9 退役（Q17，§13.6）；
- 修订 6：FE4a 证据停止后，2026-11-11 约 02:28 UTC 在设计会话中按设计会话的建议确认 Q18、Q19（§16）；
- 修订 7：fix4 调试停止后，2026-11-11 约 03:02 UTC 在设计会话中按设计会话的建议确认 Q20（§17）；
- FE4a 退出：2026-11-11 05:51 UTC 在设计会话中确认 §7.3 看图、豁免、C8、N11、N15，决定本次不推送 main，并要求后端今后改 `frontend/` 前先告知前端设计会话（§5.2 表后的 FE4a 退出记录）。

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
- FE4a 的 t1 第二次调试运行（§7.2，历史，未发生）；
- 已完成：FE4a 退出时推送 tag `fe-fe4a-exit`；owner 2026-11-11 决定本次不推送 main，main 的推送随后端节奏另定；
- 已完成：后端今后改 `frontend/` 前先告知前端设计会话（owner 2026-11-11），已写入 AGENTS“前端测试（FD7）”一节；
- FE4b 退出时的 tag、合入与推送（修订 8：建议见 Q25）；
- 修订 8：§18.2 列出的交后端事项，由 owner 转后端：第 2 项无记录行复用身份的消费者判据（问题原文 `/home/dev/gdds-stage-exchange/fe4b/questions/be-b-unrecorded-identity-consumer-rule.md`，阻塞 F5 的该分支）；第 3 项交付文档与 Contract 的状态行未随退出更新（不阻塞）。

**修订 8 待决定（2026-11-11，设计会话建议，待独立审核后交 owner）：**

| # | 事项 | 设计会话建议 | 不采用的方案及代价 | 落点 |
| --- | --- | --- | --- | --- |
| Q22 | FE4b 与设备目录 `fe-handoff` 的先后与合并方式（按审核 R8-1 后的事实改写） | **甲：FE4b 作为集成线。** 事实：当前 main 的前端（FE4a 树 `5658a45f21`）仍按 `{column,value}` 读导航，后端已是 BE-b，main 上前后端不匹配，`fe-handoff` 在 main 上做的真实回归不能证明它与 BE-b 后端的适配，目录试运行也要等前端适配 BE-b。做法：两者并行；`fe-handoff` 照常完成单测、模拟 e2e、截图与自身审核，真实回归改由 FE4b 的 `journeys` 调试与证据覆盖；审核通过的 `fe-handoff` 提交在 FE4b 最终候选前合入 `fe-vnext` 一次，随 FE4 退出进入 main；`fe-handoff` 来不及时 FE4b 不等它。三种情形下的真实回归、`fe-handoff-exit` 的绑定与执行者、`dir-v1` 阶段 2 的放行条件见 §6.5 的表（来不及合入时放行条件为“FE4 已退出且 `fe-handoff` 已验证并进入 main”）。这改变了 owner 已确认的 `fe-handoff` kickoff（真实回归位置、合入 main 与 `dir-v1` 的时点），需 owner 决定 | **乙：`fe-handoff` 先独立退出，真实回归在旧后端树上做：** 需拼接前端与旧 `vnext/` 树，组合未经验证，不推荐。**丙：FE4b 先退出，`fe-handoff` 之后基于 main 做：** 简单，但目录试运行串行等两者，`fe-handoff` 加设备位置时还要再处理一次顶栏。无论选哪种，FE4 退出前不要从 main 部署试运行 | §6.5、§7.3、§8、§18.7 |
| Q23 | FE4b 的真实数据次数（DC33、DC98） | 调试：`journeys` 完整集最多两次、`t1` 最多两次；审核不独立跑真实数据；证据：`journeys` 完整集、`t1` 各一次（证据停止后在新候选上重跑不计为调试）；只用 t1，不用 t2–t4；打包流程没改就不跑 t4；M1 只报告第 1 步 MODIFIED_ONLY。理由：FE4b 改 bundle 解析与差异浏览页，每个下载 bundle 的旅程都受影响，只跑部分 scope 不够；t1 新增四条程序判据与 6 个截图页面，第一次就暴露问题的可能性较大。每次 t1 约 4–5 分钟 | **各只给一次调试（同 FE4a）：** 第一次失败后要再走一次 owner 确认，按 FE4a 修订 6、7 的经验，每次停顿都要等确认。**不给 journeys 调试、直接取证：** 证据失败要在新候选上四项重跑（Q19），代价更大 | §7.2 |
| Q24 | FE4a 带入项的纳入与推迟 | 纳入：N5、N14、N17、N19、N20 与 N25、N26、N27、审核清单补充、两个后端提交的审核；N24 只写入“未测”说明，不安排到不了该状态的 r11 断言。推迟：§17.2 的可选项（工作台工具栏原生按钮统一改为 `Button` 组件），理由是与 BE-b 无关，且会改动大量工作台截图、扩大看图范围；记入 FE4 退出的遗留，由以后的前端阶段处理。逐项理由见 §18.5 | **全部纳入：** 工作台截图大面积变化，与 FE4b 的差异浏览页变化混在一起，看图与审核都更难 | §18.5 |
| Q25 | FE4 退出时的推送 | 推送 tag `fe-fe4b-exit`；main 是否推送由 owner 按后端节奏另定（同 Q12）。推送 tag 会把它指向的提交及其祖先（含 S1a、BE-b 的提交）一并推到远端，但不移动远端 main | **同时推送 main：** main 带有 S1a、BE-b 与 P7 文档，其推送应随后端的安排，不由前端退出决定 | §6.4 |
| Q26（已决定） | 前端角色安排（owner 2026-11-11） | 前端暂不需要固定长程任务的角色分工，无需参考后端角色分配规则。 | 原固定角色、逐包新上下文与不同模型家族要求取消 | §19、AGENTS |

## 11. 提示词草稿

发出前填写方括号中的值。§11.1、§11.2 保留 FE4a 的历史提示词；FE4b 的角色安排按 Q26 与 §19。

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

修订 5 时的原文（修订 8 起以下面的草稿要点与 §19 为准，其中“刷新 OpenAPI”已改为不刷新，角色安排以 Q26 的 owner 决定为准）：新建实施与审核会话；先读 BE-b 的 Contract、交接、golden 与 §4 第 7 项的变化说明；合入 BE-b 退出后的 main（届时含 P7 S1a）；重新生成 fixture；按 §3.1、§3.2 实施；t1 证据运行一次，同时产生正式重拍截图，交 owner 看图。§11.2 第 10 项（DOM 结构与真实旅程定位器）同样适用，写进 FE4b 的审核清单。

**修订 8 的草稿要点（正式提示词在本修订经独立审核、owner 确认 Q22–Q25（Q26 已决定）并合入 main 之后写）：**

*发出前置条件：*
1. 修订 8 经独立审核，owner 确认 Q22–Q25；设计会话以 `--no-ff` 合入本地 main，提示词填入合入后的提交号；
2. 发出前重核并记录：`fe-vnext` 仍为 `c2199b82f7`；`be-b-exit` 仍指向 `3e5f24583d`，其 `vnext/` 为 `2faac9fc1d`；main 当前的头与 `vnext/` 树；`fe-handoff` 是否已合入 main 及合入提交（决定 §6.5 的哪种情形）；`S2B_DATASET_BASELINE`、`S1B_V2_PREVIEW_CHANGED_COUNTS` 在 `3e5f24583d:vnext/backend/benchmarks/real_dump_journey.py` 中仍是模块级常量（设计会话 2026-11-11 用 `git grep` 核对在第 192、234 行）；
3. 在所选节点上现场核对 §6.7 的两个依赖镜像、工具链、npm 缓存与 t1 目录，并运行 `--print-input`。

*实施提示词要点：*
- 先读：AGENTS（main）“专用测试节点”“前端测试（FD7）”（含后端改 `frontend/` 先告知的规则）；本文（main `[确认提交]`）§3.1、§3.2、§5.3、§6.5–§6.7、§7、§8 FE4b、§10 Q22–Q26、§18、§19；交付文档与 BE-b 总结；七份正式 Contract（§18.1 表）；golden 的 README；FE4a 的 handoff、退出记录与带入项原文所在的审核报告；合入了 `fe-handoff` 时另读它的 kickoff 与 handoff；
- 起点按 §6.5，路径核对、`--print-input`、RS 依赖镜像 tag 与运行时 OpenAPI 比对不符即停止；
- 范围：§5.3 的 F1–F13、§3.2 侧栏、§18.5 纳入的带入项、`t1.spec.ts` 的正式重拍截图与程序判据、`journeys` 的程序判据、入口接受 `fe4b` 子阶段名；
- 不做：不改 `vnext/`；不在浏览器中重算行标识；不依赖“未变表在 Preview 中也有 before 别名”这一实测现象（Contract 只承诺 `device` 与 `composite_signal_point`，§18.2 第 4 项）；不编辑生成的 fixture；不改打包流程；真实数据次数不超过 §7.2；
- 节点与占用：生成 fixture 在 05；静态检查与模拟接口优先 07；真实 backend 与 t1 在 05；都按原子占用标记，真实 backend 入口自行获取；
- 日志与回源：证据与调试运行经 §3.8 的 wrapper，设置 `GATEWAY_FE_LOG_DIR`（N26）；handoff 中的十六进制值用回源脚本核对；
- 交付 handoff，放 `/home/dev/gdds-stage-exchange/fe4b/handoffs/`（§19），内容包括：合入点与路径核对；F1–F13 与带入项逐项的改动位置与用例；fixture 两次生成的记录（提交、`vnext/` 树、节点、两份输出的 SHA256 清单与比较结果）；程序判据输出；t1 的 FE3 kickoff §8.3 逐条核对与 M1；截图清单、变化清单分组与第 ① 次稳定性比较；真实旅程中出现的诊断码；每次运行的节点、hostname、起止 UTC、起止 HEAD、树、exit code、日志 SHA256 与镜像、缓存身份；回源结果；已完成、未测（含 §18.2 第 7 项列出的只由单测或 t1 覆盖的编码与情形）、未决三节。

*审核提示词要点：*
- 审核 `fe-fe4a-exit..[FE4b 候选]`，范围说明按 §6.5；先做路径核对；
- **F1–F13 的区分力：** 逐项把修复回退或放宽后对应用例应失败，至少包括：去掉 v4 selector 的精确匹配（v3 向量应被拒的用例失败）；不核 `ROW_LOCATOR` 条目的 SHA；允许有快照侧 context 非 null；无记录行不按后端答复后写定的判据就复用身份（`identity-changes` 的用例应失败）；整数文本接受前导零；文案表少一个 `diagnostic-codes.json` 中的码（集合全等单测失败）；
- **fixture：** 在 05 上用实施会话的 wrapper 独立生成一次，与候选中的 `source/backend/` 逐文件比较；核对删除项已无引用；
- **§11.2 第 10 项**（DOM 结构改动时 grep `e2e-real/` 中的定位器，并核对共享 helper 全部调用处的结构）；
- **两个后端提交（§18.6）：** 审查入口改动，并在实施会话的 `journeys` 调试日志中核对 `cleanup_runtime`、`cleanup_status=ok`、`main_exit_code` 与 `exit_code` 两行，以及 wrapper 得到的是 `exit_code` 字段而不是 `main_exit_code`（N27）；
- **合入了 `fe-handoff` 时：** 只核冲突的解决与 FE4b 对其行为的影响（会话注入在真实旅程调试中仍有效；它的单测与模拟用例仍通过）；
- **截图：** 第 ② 次稳定性比较；用比较脚本复核变化清单的分组；新增的 38 个（合入 `fe-handoff` 时 40 个）文件齐全；t1 截图的选取符合 §7.3 的规则；规则 4 不再有豁免；
- **t4 筛查**（§7.4）；**回源**（§3.8）；
- **运行：** 模拟接口全量一次与探针；不独立跑真实旅程与 t1，核对实施会话的调试日志；
- 报告写入 `/home/dev/gdds-stage-exchange/fe4b/reviews/<被审提交>.md`（§19），标明审核范围与风险；通过后指明证据项（§7.2 FE4b 证据行），取证后核对证据日志，给出 FE4 退出建议（含 Q25 的推送）。

## 12. 交接材料

新会话从下列文档读取“已完成、未测、未决”，不依赖旧会话的上下文：

| 类别 | FE4a 读取 | FE4b 另读 |
| --- | --- | --- |
| 已完成 | FE3 kickoff §3.2 的 FE3a、FE3b、FE3c 退出记录；`fe3c-evidence-04.md`、`fe3b-evidence-04.md`；`fe3c-handoff.md` 及 fix1、fix2 | FE4a 的 handoff：`fe4a-handoff.md` 及 fix1–fix4（`fe4a-handoff-fix1.md`–`fe4a-handoff-fix4.md`）；`fe4a-evidence.md`；FE4a 退出记录（§5.2 表后）与 FE4a 审核报告（`reviews/fe4a-review.md`、`fe4a-rereview-1.md`–`fe4a-rereview-4.md`、`fe4a-evidence-check-1.md`、`fe4a-evidence-check-2.md`）；BE-b 的退出交接 |
| 未测 | `fe3c-handoff.md` §5.5（只由模拟接口覆盖的项）；FE3 kickoff §4.6 末段（时间倒退等只由模拟接口覆盖）、§4.7（提交 403、仍在运行与 `MANUAL_RECOVERY_REQUIRED` 只由模拟接口覆盖）、§15.3 与 §16.7（过期 `APPROVE` 409 只由模拟接口覆盖）；§8.4（t1 FULL 不可比较，FE4 起不再报告；t4 自 FE3a 后未重测） | `fe4a-handoff.md` 的“未测”一节；N24（C12 第 1 条在真实旅程中未覆盖，只由模拟接口 V12 覆盖）；05-t1 的 `composite_changed=0` 没有后端对照；合入后 main 的 `frontend/` 树 `5658a45f21`（含 `7b16061b2e`、`b79fd4c72f`）没有在任何节点上运行过 |
| 未决 | 本文 §3.4–§3.7、§10；FE3 kickoff §12 中仍开放的项 | 本文第 2 步；BE-b 第二步与交接中留给前端的事项 |
| FE4b 另读（修订 8） | — | BE-b 交付 [`be-b-frontend-delivery.md`](../backend-vnext/refactoring/formal/plans/be-b-frontend-delivery.md) 与 [`be-b-summary.md`](../backend-vnext/refactoring/formal/plans/be-b-summary.md)（状态行写于打 tag 之前，以 tag `be-b-exit` 的消息与阶段日志 `/home/dev/gdds-stage-exchange/be-b/log.md` 的“B5 最终核收”为准）；§18.1 的七份正式 Contract；`vnext/fixtures/golden/presentation/be-b/v1/README.md`；本文 §18 |

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

### 13.9 修订 8（2026-11-11）

依据 BE-b 的正式交付（`be-b-exit` → `3e5f24583d`）与设计会话的只读复核（§18）。修订分支 `fe4-kickoff-rev8` 从本地 main `3e5f24583d`（即 `be-b-exit` 的目标）拉出，在独立 worktree 中修改，不在 main 共享 worktree 中工作。本轮不写代码、不运行测试，节点上只做只读核对（镜像身份、缓存与截图原件）。

**本文修改的节：** 头部（状态）；§2.3（追加修订 8 的现状）；§3.1（B4 无记录行一条、B6 surface 诊断一条、Contract 版本一条、表后说明）；§5.2（一句指向 §6.5）；§5.3（fixture 生成的节点与命令、wrapper、上传输入、新增场景目录；模拟 HTTP 数据两条；程序判据的实现与范围；截图分工、合入点改为指向；“仍待”改为落点表；新增“前端改动范围”F1–F13）；§6.3（FE4b 写定）；§6.4（FE4b 推送建议）；新增 §6.5–§6.7；§7.2（FE4b 调试、审核、证据三行与两条说明）；§7.3（FE4b 写定）；§7.4（M1 并列值、FE4b 的 t4 判断）；§8 FE4b（写全）；§10（说明、后续事项、“修订 8 待决定”Q22–Q25）；§11.3（草稿要点）；§12（FE4b 另读一行）；§13.9；新增 §18。

**其他文档：** 本次不改。交付文档、Contract 与 golden README 中状态行未随退出更新等问题，按 §18.2 交 owner 转后端，不由本文修改。

### 13.10 修订 8 fix1（2026-11-11）

依据独立审核报告 `docs/frontend-vnext/reviews/fe4-kickoff-rev8-review.md`（分支 `fe4-kickoff-rev8-review`，提交 `f87b4d07e1`，结论定向修订）。各 finding 的处理：

| finding | 处理 | 修改的节 |
| --- | --- | --- |
| R8-1 无记录行复用判据 | 同意。初稿的五项检查作废；设计会话读后端实现，发现复用条件看上去恰等于筛选页签 `basis=EXACT`，与 Contract 写法不一致，一并写入问题交 owner 转后端；答复前 F5 的该分支不实现、不送审，其他工作不受影响 | §3.1 B4、§5.3 F5、§8、§10 后续事项、§18.1、§18.2 第 2 项、§19 |
| R8-2 清单进不了 runner 容器 | 同意。runner 改为同一 HEAD 归档 `frontend` 加两个后端清单文件，单测按相对路径只读读取 | §5.3 上传输入 |
| R8-3 定位判据漏逻辑存在侧 | 同意。改写为按记录种类与逻辑存在侧的矩阵，补“非零记录而 locator 为 null 判为不符” | §5.3 判据 4、F5 |
| R8-4 t1 截图不能覆盖页签溢出 | 同意，设计会话从交付的 t1 tar 复核：v1 转发通道与装置项最多 10、12 个页签，v2 FULL 只有 1、3 个。两张截图改在 v1 选取，实际溢出时才算覆盖并断言可达末页签 | §7.3 |
| R8-5 N27 修法没对准原因 | 同意。改为让入口把结束字段也打到标准输出；验收覆盖两个入口 | §18.5、§11.3、§18.6 |
| R8-6 FE4b 仍沿用 FE4a 的角色安排 | 同意。新增 §19：持续协调者、工作包与风险等级、独审模型家族、交换目录与一页总结；新增 Q26 | §6.4、§11.3、§19、§10 Q26 |
| R8-7 冲突的旧句 | 同意，逐条清理 | §3.3、§5.2、§7.2、§7.3、§8、§11.3 |
| Q22 意见 | 同意其事实：main 上前后端不匹配，`fe-handoff` 在 main 上的真实回归不是有效证据。Q22 改为“FE4b 作为集成线”，并写明这改变了 `fe-handoff` 已确认的 kickoff，需 owner 决定 | §6.5、§8、§10 Q22、§18.7 |
| Q24 意见（N24） | 同意，N24 改为记录未测 | §18.5 |
| 报告 §3 的细节 | `fe4b-device-tabs` 指明 `device:composite`；`fe4b-table-scope` 注明零行场景不能证明“不涂到各行”；F5 正反用例的落点；BE-d 互通用例的改法；生成输出比较只比 `backend/` | §5.3、§7.3、§18.3 |

**Owner 后续决定（2026-11-11，Q26）：**前端暂不需要固定长程任务的角色分工，无需参考后端角色分配规则。上述 R8-6 的固定角色与模型分配方案已撤销，§19 与正式提示词草稿已同步。

本次材料按 §19 放阶段交换目录 `/home/dev/gdds-stage-exchange/fe4b/`（问题文件与阶段日志）。其他文档本次不改。

### 13.11 修订 8 fix2（2026-11-11）

依据定向复核 `/home/dev/gdds-stage-exchange/fe4b/reviews/89215cd873.md`（结论定向修订，剩余 F1–F3）与 owner 的角色决定（Q26，`7b91e4ad82`，在分支 `fe4b-role-rule-owner` 提交；本分支已快进到该提交后再修订）。

| 项 | 处理 | 修改的节 |
| --- | --- | --- |
| F1 F5 的阻塞范围 | 只阻塞无记录行复用分支；其他内容照常实施、审核与送审；最终全范围审核与退出之前须完成答复、同步与该分支 | §8 |
| F2 定位截图时机 | `fe4-t1-columns`、`fe4-t1-located-rows` 明确取第 4 步 v2 FULL 的 `initial_to_modified`，不再用“同上” | §7.3 |
| F3 `fe-handoff` 集成条件 | §6.5 改为三种情形的条件表：合入前的 `journeys` 不覆盖它；晚合入计为第二次 `journeys` 调试；`fe-handoff-exit` 的绑定与执行者；`dir-v1` 放行条件；路径例外集中写在 §6.5 一处，§5.2 与 §8 引用它 | §5.2、§6.5、§7.2、§8、§10 Q22、§18.7 |
| 文字收尾 | §6.3 去掉“刷新”；§10 后续事项的 t1 第二次调试标为 FE4a 历史；§7.2 补现行构建故障快速修复优先；§11.3 写明 Q26 已决定；Q24 中 N24 改为只写未测 | §6.3、§7.2、§10、§11.3 |
| 后端问题原文 | 补列 `comparison_succeeded` 为 false 的分支（复核的小补充） | 交换目录 `questions/` |

其他文档本次不改。

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

## 18. BE-b 交付的复核（修订 8）

设计会话 2026-11-11 只读复核：在开发主机上用 git 读取 main `3e5f24583d` 中的文档、golden 与输入，读取交换目录 `/home/dev/gdds-stage-exchange/be-b/` 中的原件并重算 SHA256；在 04、05、07 上只读核对镜像、缓存与截图原件（§6.7、§7.3）。没有运行测试，也没有改动任何节点上的内容。

### 18.1 交付项与 FE-BEB 的关闭

| §4 交付项 | 交付位置 | 复核结果 |
| --- | --- | --- |
| 1 Contract | 交付 §1 | 七份都在 main 中：[`business-navigation.md`](../backend-vnext/contracts/business-navigation.md)、[`comparison-surface.md`](../backend-vnext/contracts/comparison-surface.md)、[`comparison-bundle.md`](../backend-vnext/contracts/comparison-bundle.md)、[`row-location.md`](../backend-vnext/contracts/row-location.md)、[`table-presentation.md`](../backend-vnext/contracts/table-presentation.md)、[`presentation-diagnostic-codes.md`](../backend-vnext/contracts/presentation-diagnostic-codes.md)、[`composite-signal-device.md`](../backend-vnext/capabilities/composite-signal-device.md) |
| 2 golden | 交付 §2 | `vnext/fixtures/golden/presentation/be-b/v1/` 下五类（navigation、navigation-diagnostics、row-location、surface、bundle）各 17 个文件，与 17 个场景一一对应。golden 的 `manifest.json` 记录的生成提交 `f663fba2f5` 是 main 的祖先，`input_manifest_sha256` 是生成时的输入清单；之后 `2aa5b9d964` 改了 `diagnostic-codes.json` 并更新了输入清单（main 上输入清单原字节 SHA256 为 `debbe82838064b06ec90ddf31744269fd7d424c5b1d93b2cabe6f0ee1c6ebb04`）。阶段日志记录 B5 修复后 17 个场景的 golden 一致。不影响前端：FE4b 以自己在合入点上生成的输出为准 |
| 3 生成入口 | 交付 §3 | `vnext/scripts/generate-presentation-fixtures.py` 在 main 中；输入清单 `vnext/fixtures/presentation-inputs/manifest.json` 列出 17 个必需目录、两个必需根文件、退役目录 `backend/fe2a/preview-no-navigation`，以及三个被拒的原件（`sql-{baseline,initial,modified}.sql`，`b1_n1_iec104_yc_list` 缺 gid，`KEY_MISSING`）及其派生件。8 个原件的路径与 SHA256 来自 `59c5b8cfca` |
| 4 提交、树与镜像 | 交付 §4；tag 消息；阶段日志“B5 最终核收” | `be-b-exit`（对象 `517ce8d4a3`）→ `3e5f24583d`；V `37fe3a87d2`；`vnext/` 树 `2faac9fc1d`；镜像见 §6.7，04、05 实测一致 |
| 5 OpenAPI 原件 | 交付 §5 | 见 §6.3：三份原件原字节相同，规范化后等于前端快照 |
| 6 稳定编码 | 交付 §6 | Contract 与 `diagnostic-codes.json` 同源：设计会话用脚本比对，导航 12 个码及各自 params 键集合一致，`surface_summary_codes` 与 Contract surface 部分出现的编码集合一致。与前端现状的差异见 §18.4 |
| 7 变化说明 | 交付 §7 | 机器索引 `index.json` 的 SHA256 与交付一致；S1a 与 BE-b 分栏，见 §6.6 |

**FE-BEB-01–13 在正式 Contract 中的落点：**

| finding | 落点 | 结论 |
| --- | --- | --- |
| 01 表级事实与空表 | Business Navigation“载荷与唯一性”末两段、“局部事实与表级事实” | 关闭：`table_scope` 只从实际 typed 风险归约；空 `sg_cfg` 有变化或风险时保留 |
| 02 改前独有列 | Comparison Surface v4 第 2 条；Table Presentation | 关闭：列并集与 `present_in` |
| 03 唯一性与省略 | Business Navigation“载荷与唯一性” | 关闭：三条唯一性、省略条件、按侧覆盖等式 |
| 04 surface 摘要 | Comparison Surface“语义摘要与 raw 完整性” | 关闭：前端不重算 |
| 05 稳定编码 | Presentation 稳定编码 | 关闭 |
| 06 事实不可用诊断 | Business Navigation“局部事实与表级事实” | 关闭：每表一条，`side=null`，三个 reason 按序择首 |
| 07 改前浏览表 | Comparison Bundle v4 第 2 条；Composite Signal Device | 关闭 |
| 08 定位与 context | Row Location；Comparison Bundle v4 第 3–5 条 | 关闭 |
| 09 replacement 与单导航 | Business Navigation“Replacement” | 关闭 |
| 10 输入与生成器归属 | 交付 §3 | 关闭 |
| 11 B9 退役 | Business Navigation“载荷与唯一性”第 2 段：退役 B9、`fallbackNavigation`、`preview-no-navigation` 与猜列序分支；输入清单把 `preview-no-navigation` 列为退役 | 关闭 |
| 12 无记录行身份 | Business Navigation“无记录行与完整性”：四个条件全部成立才复用；不成立时 `TABLE_FALLBACK` | 后端文字已补齐；前端从公开字段判定的规则尚未写定，已交后端（§18.2 第 2 项），F5 的该分支等答复 |
| 13 身份标量类型与 side | Business Navigation“双侧筛选与标量”：类型表、整数文本规则、同侧 metadata；`IDENTITY_EXCLUDED` 按受影响存在侧逐侧一条，物理缺列不归入 | 关闭 |

**§5.3 截图场景的覆盖：** §5.3 列出的 9 类模拟接口截图场景都有对应的生成目录（映射见 §7.3 的新增截图表）：改前公式与装置名 `formula-unchanged-device`；gid 变化 `identity-unrecorded-exact`、`identity-changes`；重复地址与孤儿 `duplicates-orphans`；`TABLE_FALLBACK` `identity-changes`；`table_scope` `table-addition`、`schema-keyless`；改前独有列 `schema-keyless`；keyless 删除行 `fe2a/preview-modified-only` 的 `keyless_demo`（locator 中有两侧 index 都为 null 的删除记录）；replacement `fe2a/preview-replacement`；`DEVICE_FILTER_VALUE_UNSUPPORTED` `excluded-identity`、`text-identities`、`integer-boundary`；仅注释 `comment-only`（实际调用提交事务，得到 `NO_CANONICAL_CHANGE`）。

### 18.2 出入与处理

| # | 出入 | 处理 |
| --- | --- | --- |
| 1 | §3.5（FE4a Q21）按后端答复删除了 `BLANK_PROVENANCE_INVALID`（“没有主动产生点”）；正式稳定编码表把它列为 native 保留错误码，可以进入 surface summary | 以正式 Contract 为准：FE4b 恢复该码，文案同有序表 gid 组（§18.4）。Q21 答复说的是当时的产生点，与 Contract 列出完整错误空间不矛盾，不交后端 |
| 2 | 本文 B4 原写“没有记录的行，两侧身份值相同”，缺少 Contract 的四个前提（后端在 B0 日志中也指出了这一点）。Contract 又写“`null` ref、`facts.basis=EXACT`、`replay_guarantee=EXACT` 单独都不是证明”，第二步设计 §4.2 要求前端“仅按这些明确条件消费”，但没有写出从公开字段到条件的映射。修订 8 初稿在此给出的五项检查经独立审核（R8-1）指出不完整：漏了风险归属完整性（记录完整而因 `RISK_ATTRIBUTION_UNAVAILABLE` 进入 fallback 的情形），且公开 surface 把 `SCHEMA_CHANGED` 与 `SCHEMA_ONLY_CHANGED` 都显示为 `SCHEMA_ONLY`，前端区分不出后端只对后者禁止复用。设计会话随后读后端实现：对发布了筛选页签、两逻辑侧都存在的表，`may_reuse_unrecorded_identity` 看上去恰等于该表筛选页签 `basis=EXACT`，与 Contract 的写法不一致 | **交 owner 转后端，作为 F5 复用分支的前置（阻塞该分支，不阻塞其他工作）。** 问题原文：`/home/dev/gdds-stage-exchange/fe4b/questions/be-b-unrecorded-identity-consumer-rule.md`，请后端确认复用是否保证等价于 `basis=EXACT`、“两逻辑侧都存在”取哪个公开字段，或给出准确映射；并确认已发布 STANDARD 普通行记录非零时 `row_locator_ref` 必须非 null。答复写入 Contract 后，设计会话同步 B4、F5 与本行，再由审核会话定向复核。在此之前：F5 中该分支不实现、不送审；前端不得自拟判据；B4 的“只在四个条件全部成立时复用”保留为方向，不作为实施规则。初稿的五项检查作废 |
| 3 | 交付文档与总结的状态行、§4 仍写“最终 H 与退出 tag 待核收”；`business-navigation.md` 头部仍写“集中验收…尚待完成”；golden README 仍写“剩余 B5 身份/OpenAPI/门禁绑定见交付” | 都写于打 tag 之前。FE4b 以 tag 消息与阶段日志“B5 最终核收”为准（§12）。交 owner 转后端更新，不阻塞 |
| 4 | golden 显示 Preview 中未变化的表也带 `before_table_ref`（与 current 同一 artifact，例如 `fe2a/preview-modified-only` 的 `b1_n1_iec104_yc_list`、`device_st`、`version_manager`）；Contract 只承诺 `device` 与 `composite_signal_point` | 前端按 ref 是否存在通用处理，不依赖这一现象，写进实施提示词的“不做”（§11.3）。不交后端 |
| 5 | BE-d 互通向量 `backend-interop/be-d-0ba45e5ef8/` 的 manifest 是 v3；交付没有重新生成它（§4 第 7 项也只列了 `source/backend/`，是本文清单的遗漏） | 设计决定，见 §18.3 第 1 项 |
| 6 | 后端为三个被拒原件另做的 `sql-*-canonical.sql`（`gid INT NOT NULL`，值“稳定 gid”）与前端真实旅程用的派生件（FE3a Q10，`gid INT NULL`，值不变）不同 | 两套各管各的：前者只用于 fixture 生成，后者只用于真实旅程，FE4b 都不改。FE3a 派生件在 P6 退出的树上通过了 FE4a 的完整集证据，在 BE-b 的树上由 FE4b 第一次 `journeys` 调试验证；若被后端拒绝（例如 `KEY_MISSING`），按 §8 停下交设计会话，不自行改输入 |
| 7 | 生成的 fixture 没有覆盖：导航码 `PROTOCOL_EXE_MISSING`、`PROTOCOL_TABLE_NOT_FOUND`、`APP_TABLE_CFG_MISSING`、`APP_TABLE_CFG_DUPLICATE`、`APP_TABLE_NOT_FOUND`；reason `RISK_ATTRIBUTION_UNAVAILABLE`、`TABLE_DEGRADED`；带诊断的 replacement；`FORWARD_CHANNELS`、`COMMUNICATION_PROTOCOLS`、`GLOBAL_PARAMETERS` 三组；单项最多 3 个页签 | 文案由单测覆盖（构造诊断对象，不构造整份产物）；三组与多页签由 t1 真实数据覆盖（`fe4-t1-nav-groups`、`fe4-t1-forward-channel`、`fe4-t1-device-tabs`）。写入 FE4b handoff 的“未测”。产生这些情形的规则由后端 golden 负责，不请求后端补场景 |

### 18.3 设计决定（不需要 owner 决定）

1. **BE-d 互通向量：** `tar_stream.py` 自后端候选 `0ba45e5ef8` 以来没有改动，tar 帧格式不变。FE4b 在安装 tar 时精确校验 bundle selector（F1），v3 包不进入 OPFS。处理：
   - 向量原样保留（字节与 `SHA256SUMS` 不变）；
   - 其中的 PAX 记录、size 头与 `size-vectors.json` 等仍作 tar 帧格式的正向用例；
   - `bundle.tar` 改作反例：安装时因 selector 为 v3 被拒，且不写入 OPFS；
   - 生产 encoder 产出的完整 v4 包的安装，由真实旅程与 t1（经生产下载路径）覆盖；模拟接口的完整安装用例改用由生成 fixture 构建的 v4 golden 包。`e2e/bundle-interop.spec.ts` 的三种模式各自仍须证明原来的结论，具体改法由实施会话定、审核会话核对。
   - 同步 `interop-fixture.test.ts` 中原有的完整安装用例；截断与损坏两种反例改为基于有效的 v4 包，证明失败发生在对应的边界，而不是都提前失败在 v3 selector 上；原有的逐成员大小与 SHA、失败后不留已安装目录等断言保留；
   - 不请求后端重新生成该向量。
2. **records 中的 `DUPLICATE_EFFECTIVE_KEY:<表名>`：** Contract 规定 comparison facts 与 records 仍保留带表名的形式。前端只在 surface summary 上使用诊断文案（`diagnostics.ts` 的三个函数只由 `ComparisonPage.tsx` 对 surface summary 调用），所以删除前缀切分不影响 records。
3. **`tab-overflow` 截图：** 见 §7.3，没有 fixture 能触发时退役。
4. **程序判据独立实现：** 见 §5.3。
5. **`NO_CANONICAL_CHANGE` 文案：** 见 F13。

### 18.4 诊断文案（F8）

**surface 诊断：**

| 变化 | 编码 | 文案 |
| --- | --- | --- |
| 删除 | `ORDERED_POLICY_MISSING`（不在正式编码表中） | — |
| 删除 | 英文短句键 `risk table budget exceeded`、`risk diagnostics truncated`、`annotation artifact budget exceeded`、`max_annotations_per_pair exceeded`、`max_risk_tables_per_pair exceeded`、`max_risk_pair_wall_time_seconds exceeded` | — |
| 新增 | `COMPARISON_INTERNAL_ERROR` | 比较时发生内部错误 |
| 新增 | `RISK_TABLE_BUDGET_EXCEEDED`、`RISK_DIAGNOSTICS_TRUNCATED`、`RISK_ANNOTATION_ARTIFACT_BUDGET_EXCEEDED` | 风险标注不完整（超出上限），请打开整表核对（沿用被取代短句的文案） |
| 新增 | `RISK_ANNOTATION_LIMIT_EXCEEDED` | 风险标注数量超出上限，部分行没有标注（同上） |
| 恢复 | `BLANK_PROVENANCE_INVALID` | 有序表的 gid 或空行标记无效 |
| 不变 | 其余各码 | 文案不变 |

- 匹配只按完整编码；不再按冒号前缀切分，不再用 `*Error/*Exception` 类名正则；未知编码显示通用文案“比较过程有提示”，原值放 Debug。
- `SURFACE_DIAGNOSTIC_CODES`（降级原因的优先级）按上表同步：新码 `COMPARISON_INTERNAL_ERROR` 放在内部错误组，四个风险码放在原短句的位置。
- §3.5 作为 FE4a 的记录保留；FE4b 起以正式编码表为准。

**两个新的导航码**（文案原则同 FE2 kickoff §5.5：只说原因，后果由状态表达）：

| 编码 | 文案模板 | reason 文案 |
| --- | --- | --- |
| `DEVICE_TAB_FACTS_UNAVAILABLE` | {table}的装置页签无法确定逐行的变化与风险（{reason}），页签按整表提示 | `RECORDS_UNAVAILABLE`：变更记录不完整；`RISK_ATTRIBUTION_UNAVAILABLE`：风险无法归属到行；`TABLE_DEGRADED`：该表比较已降级 |
| `DEVICE_FILTER_VALUE_UNSUPPORTED` | {side}{table}的 {identity_column} 无法用于按装置筛选（{reason}），已改为整表显示 | `INTEGER_OUT_OF_RANGE`：数值超出可精确处理的范围；`UNSUPPORTED_TYPE`：列类型不支持筛选；`IDENTITY_EXCLUDED`：该列未参与比较 |

- `DEVICE_ROWS_UNASSIGNED` 的 `changed_row_count` 为 null 时，括号内改为“其中变化行数未知”；replacement 下不显示变化行数（B6）。
- reason 是封闭集合，出现集合外的取值时显示“原因未提供”，原值放 Debug，不作为解码错误。
- 单测读取 `diagnostic-codes.json`，断言导航码集合与各码 params 键集合、`surface_summary_codes` 集合分别与文案表全等（F8）。

### 18.5 FE4a 带入项的处理（§10 Q24）

| 项 | 处理 | 理由与做法 |
| --- | --- | --- |
| N5 预览页顶栏溢出 | 纳入 | Preview 模式差异浏览页的顶栏（撤回、提交的禁用原因）在 1280、1920 下都溢出 12 px。修复后删除 `e2e/upload-mode.spec.ts` 中对 `fe3b-w4-approved-withdraw` 的豁免，交 owner 看图。与 `fe-handoff` 设备位置的配合按 §18.7“N5 的验收” |
| N14 溢出断言只在开截图时执行 | 纳入 | 把截图 helper 中的横向溢出断言移到“未设置截图目录即返回”之前，不拍截图的运行也检查；只改测试代码 |
| N17 `ReviewActions` 错误提示的清除与回退 | 纳入 | FE4b 调整顶栏时一并处理：其他路径重读 Review 后清除旧的冲突提示；`errorNoticeHost` 为空时有回退位置。补模拟用例 |
| N19 比较脚本自检对 Paeth 没有区分力 | 纳入 | 自检的编码器与解码器不再共用同一个 `paeth()`（例如用独立写法或固定的已知向量）；把 `paeth()` 改为恒返回“左”的变异应使自检失败 |
| N20、N25 回源脚本的配对范围 | 纳入 | 支持 `` `路径`，SHA256 `值` `` 与表格单元格内的路径；标签项改为可复算的证据文件；报告“有路径却未配对”的文件哈希。FE4b 的 handoff 要用它回源 |
| N24 C12 第 1 条在真实旅程中未覆盖 | 记为未测（按审核意见改写） | 现有 `r11-review-conflict` 是 `REVIEW_VERSION_CONFLICT`，刷新后先清除错误再关闭对话框，到不了过期通过或 `ARCHIVE_CLOSED` 的关闭后顶栏提示。不加真实旅程步骤，仍只由模拟接口 V12 覆盖，写入 handoff 的“未测” |
| N26 证据提示词设置 `GATEWAY_FE_LOG_DIR` | 纳入 | 写进 FE4b 的实施与证据提示词（§11.3） |
| N27 wrapper 的 `exit_code` 与 `busy_end` | 纳入（修订 8 按审核 R8-5 改写） | 字段缺失的原因不是匹配写法：wrapper 的 `report_field()` 已按 `^exit_code=` 整行匹配，但只扫描它捕获的入口输出段，而 `validate-upload-package.sh` 的 `finish()` 把结束字段只追加到自己的日志，标准输出只打印 `log_file` 与摘要。修法：上传校验入口在 `finish()` 中把结束字段（含 `exit_code`）同时打到标准输出；真实 backend 入口同样核对，必要时同法处理。wrapper 的执行结果仍以入口进程退出码为准，字段缺失不能改判成功。`busy_end` 在释放标记之后记录，或改名为 `busy_before_release`。验收：上传校验与真实 backend 两个入口经 wrapper 各得到最终 `exit_code` 字段，且不会取到 `main_exit_code` |
| §17.2 可选项：工作台工具栏原生按钮改为 `Button` | **推迟** | 与 BE-b 无关，会改动大量工作台截图、扩大看图范围；记入 FE4 退出的遗留，由以后的前端阶段处理 |
| 审核清单补充（DOM 结构改动时 grep `e2e-real/` 定位器，核对共享 helper 的全部调用处） | 纳入 | 写进 FE4b 审核提示词（§11.3） |
| 两个后端 `frontend/` 提交 | 纳入 | 见 §18.6 |
| N21–N23 | 不带入 | 同 FE4a 退出记录 |

### 18.6 main 上的两个后端 `frontend/` 提交

- **内容：**
  - `7b16061b2e`（P7 S1a F）：入口在 `TMPDIR` 下建运行时根目录，用 `python3 -I vnext/scripts/tests/runtime_config_fixture.py <根> --owner <Compose 项目名>` 生成运行时配置与 Compose override `compose-runtime.json`，所有 `docker compose` 调用改经 `compose_runtime()` 带上 override；收尾时以 `--cleanup` 清理，失败运行加 `--retain` 保留现场，清理失败记 `cleanup_runtime=failed retained=<路径>`；
  - `b79fd4c72f`：收尾记录 `main_exit_code`；主流程成功但清理失败时，`exit_code` 改为 1。
- **设计会话的只读阅读：** 入口有 `set -Eeuo pipefail` 与 `trap cleanup EXIT`，生成运行时配置失败会直接退出并进入收尾，收尾对已建的根目录做清理，逻辑成立；没有发现阻塞问题。审核时重点看：
  1. wrapper 取得 `exit_code` 字段的通路（N27，§18.5）；
  2. 失败保留的运行时根目录中是否含凭据（注释说凭据在另行删除的 `RUN_ROOT` 中）；
  3. 前端入口依赖后端测试目录下的 `runtime_config_fixture.py`。AGENTS 只要求后端改 `frontend/` 前先告知，改这个 helper 同样会影响前端入口。**交 owner 考虑（不阻塞）：** 是否把它也列入“先告知前端设计会话”的范围。
- **由谁审、何时审：** 在 FE4b 审核中审，不现在另做窄审。理由：它们不在 FE4a 的被测树上，`5658a45f21` 还没有在任何节点上运行；单独窄审也需要一次真实运行才能验证，而 FE4b 的第一次 `journeys` 调试正好是它们的首次运行。
- **第一次调试中的验证：** 实施会话在 handoff 中摘录入口日志的 `compose_project`、运行时配置生成的输出、`cleanup_status`、`main_exit_code` 与 `exit_code`，并确认运行后运行时根目录已删除（成功时）；出现 `cleanup_runtime=failed` 即按 §8 停止，不手工删除保留的目录。

### 18.7 与设备目录 `fe-handoff` 的先后（§10 Q22）

**事实（2026-11-11 核对）：**
- `fe-handoff` 的实施 kickoff（[`kickoff-fe-handoff.md`](../device-directory/kickoff-fe-handoff.md)）已由 owner 确认：从 main 新建短分支，只改 `frontend/` 与少量文档，审核通过后由其审核会话合入 main 并打 `fe-handoff-exit`；之后目录任务 `dir-v1` 才进入阶段 2。开发主机上还没有 `fe-handoff` 分支或 worktree。
- 它改会话启动（新模块与 `main.tsx`、`App.tsx`）、`DevIdentityControl`、`authenticated-fetch.ts` 的注释、工作台 `workspace-topbar` 与差异浏览页 `compare-header`（显示“地区一 / 地区二 / 项目名（站号）”与“返回目录”）、无会话与会话失效页面、工作台“尚无数据”。它要求不破坏 `e2e-real/lib/ui.ts` 用 `addInitScript` 注入的会话；测试注入的会话没有 `display`，不显示设备位置，现有布局不变。
- FE4b 改差异浏览页的侧栏、表格与 `compare-header`（N5、N17），以及 `e2e-real`。两者在 `compare-header` 与 `ComparisonPage.tsx` 上重叠；N5 修的正是 `fe-handoff` 要加设备位置的那个顶栏，它现在已经在两种宽度下溢出 12 px。
- **main 上前后端不匹配（审核 Q22 意见，设计会话复核）：** main 的 `frontend/` 仍是 FE4a 树 `5658a45f21`，`model.ts` 按 `row_filter: {column, value}` 读导航；main 的后端已是 BE-b，发布 `{before, current}`。`journeys.spec.ts` 中有 9 处进入差异浏览页。`fe-handoff` 按其 kickoff 在 main 上跑的真实回归即使通过，也不能说明新 Contract 已适配；从 main 部署的试运行同样会遇到导航不可用，直到 FE4 退出。

**建议甲（§10 Q22，修订 8 按审核改写）：** FE4b 作为集成线，做法与理由见 §6.5 与 Q22。下面几条影响按此理解：`fe-handoff` 的截图比较原件为它自身的 04 证据截图（正式提示词写明提交、目录与 SHA256）；它的真实回归在 §6.5 情形 1、2 下由 FE4b 的 `journeys` 调试与证据覆盖，情形 3 下由它自己在 FE4 退出后完成。

**对 FE4b 的影响：**
- **截图基线：** FE4a 到 FE4b 的变化清单中，只由 `fe-handoff` 引起的文件改用 `fe-handoff` 的 04 证据截图作比较原件，应为“相同”或“噪声”；FE4b 改到的按 FE4b 的原因列出（§7.3）。`fe-handoff` 新增的截图不进入 FE4b 的看图范围，除非 FE4b 改变了它们。
- **N5 的验收：** 带设备位置的顶栏只出现在跳转会话中。`fe-handoff` 在 FE4b 的顶栏工作之前合入时，FE4b 修 N5 一并排布设备位置，除现有的 `fe3b-w4-approved-withdraw` 外另拍 `fe4b-preview-topbar-device`（§7.3），两种宽度下都不溢出；合入较晚时，FE4b 先单独修 N5，合入后再拍该图并复核不溢出；来不及合入时，顶栏不溢出由 `fe-handoff` 按其 kickoff 自行保证。
- **真实旅程的会话注入：** 测试注入的会话（`window.__gatewaySession` 已预先设置）按 `fe-handoff` 的优先级 2 保持不变，不读写 `sessionStorage`。合入 `fe-handoff` 之后的第一次 `journeys` 调试（§6.5 情形 1 为第一次，情形 2 为第二次）验证它的会话启动与整页跳转后预置会话的注入仍有效；失败时按 §8 停止，判断属于哪一方。这只证明预置会话的路径，地址片段与 `sessionStorage` 的行为仍由它的单测与模拟 e2e 负责。
- **审核：** FE4b 审核只核合并冲突的解决与 FE4b 对 `fe-handoff` 行为的影响（§6.5）。会话启动与凭据处理的修正归 `fe-handoff` 的实施会话（其 kickoff §6）。

## 19. FE4b 的角色与材料

**Owner 决定（2026-11-11，Q26）：**前端暂不需要固定长程任务的角色分工，无需参考后端角色分配规则。

前端继续使用自己的权威入口（`frontend/scripts/run-tests.sh`）与真实 backend 入口。

**材料位置：**

- 阶段交换目录 `/home/dev/gdds-stage-exchange/fe4b/`（开发主机，不在 Git checkout 下）：
  - `log.md`：追加式阶段日志：UTC、提交、做了什么、未测与未决、下一步；
  - `prompts/`：任务提示词；
  - `handoffs/`：handoff；
  - `reviews/<sha>.md`：审核意见与追加的复审结论，标明审核范围与风险；
  - `questions/`：交后端的问题，例如 `be-b-unrecorded-identity-consumer-rule.md`（§18.2 第 2 项）；
  - `evidence/`：从节点按原字节复制的日志、清单与比较输出，保留来源 hostname 与路径。截图、trace、Compose 日志仍只留在节点上，只记路径与 SHA256。
- **入库：** 本文（设计）；后端答复由后端写入 Contract；退出时一页总结，按规格 §4 的模板。前端总结建议放 `docs/frontend-vnext/fe4b-summary.md`。FE4a 那样的 handoff 与审核报告不再入库。
- **tag 与合入：** `fe-fe4b-exit` 指向 `fe-vnext` 上的一页总结提交；以 `--no-ff` 合入 main；推送按 §10 Q25。路径核对规则不变（§6.5）。

**交 owner 的事项：** 按 AGENTS，只有产品范围、验收范围（含 §7.3 的看图）、来源冲突与不可逆操作交 owner；节点选择与已授权范围内可逆的实现细节按 AGENTS 办理。调试次数超出 §7.2 属于验收范围，交 owner。

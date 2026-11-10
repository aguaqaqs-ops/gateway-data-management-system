# FE4 kickoff：前端收口与业务导航接入

- **状态：** 初稿，2026-11-10。待审核会话核对，owner 确认 §10 的问题后生效。FE4 尚未开始。
- **日期：** 2026-11-10（时间均为 UTC）。
- **起点：** `fe-fe3c-exit`（tag 对象 `43e66d3eb7` → `06b454b0ef`；被测提交 `e22e39ba15`；`frontend/` 树 `46e425f84e`）。main 合入提交 `475022300c`，退出记录 `16ffe72829`。
  `fe-vnext` 仍在 `e22e39ba15`，比 tag 少一个 docs 提交（`06b454b0ef`，只新增 `fe3c-evidence-04.md`）。
- **依据：**
  - [前端 kickoff](frontend-kickoff.md)：§3.3、§4.5、§4.6、§5 BE-b、§6、§7 FE4 行、§9、§10；
  - [BE-b 设计草案](be-b-navigation-and-presentation-draft.md)（第一步，全文）；
  - [FE3 kickoff](fe3-kickoff.md)：§2.3 末段、§3.2 的 FE3b、FE3c 退出记录、§4.6、§4.7、§8、§9、§10、§11 Q21、§12、§14、§15.5 第 9 项；
  - FE3c：[审核](reviews/fe3c-review.md)（N2–N5）、[复审第 1 轮](reviews/fe3c-rereview-1.md)（M1–M3）、[证据停止核对](reviews/fe3c-evidence-stop-1.md)（N9）、[证据核对](reviews/fe3c-evidence-check-1.md)；
  - FE3b：[复审第 2 轮](reviews/fe3b-rereview-2.md)（N2）、[复审第 3 轮](reviews/fe3b-rereview-3.md)（N2、N6）、[证据核对](reviews/fe3b-evidence-check-1.md)（N7、N8）；
  - [FE2 kickoff](fe2-kickoff.md) §5.3（行定位的浏览器自校验）、§5.4、§5.5（诊断文案表）；
  - 后端对 FE3 Q21 的答复：分支 `p6-fe3-q21-answer`，提交 `d3450675bf`，`docs/backend-vnext/refactoring/formal/plans/p6-fe3-q21-answer.md`（未合入 main，未推送，§10 Q10）；
  - [UI 优化方向](ui-optimization-direction.md)（§3、W3、W5、X6、§7.3、§7.4）与 `sketches/`；
  - AGENTS（main 版本）：“角色与子 agent”（`b93bed6bda`）、“专用测试节点”（DC91 五节点池）、“前端测试（FD7）”、“Docker / Compose 验证”；
  - [Owner 决议](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md) DC91、DC97、DC98。
- **不作依据：** 开发主机上未提交的 P7 设计与执行计划草稿。BE-b 与 P7 的衔接以 owner 或后端设计会话的答复为准（§4、§10）。
- **会话分工：** 本文由前端设计会话维护。按 AGENTS“角色与子 agent”，FE4 的实施与审核都由**新会话**承担：
  - FE3 的实施、审核会话已退出活动分工，不接 FE4；
  - FE4a 与 FE4b（§5）是两个明确划分的子阶段，各自新建实施与独立审核会话；FE4a 的会话不接 FE4b；
  - 同一子阶段内的 finding 由该子阶段原审核会话连续复审，直到该子阶段退出；
  - 新会话不继承旧会话的对话上下文，交接材料见 §12；
  - 后端 BE-b 的设计、实施与审核按后端流程另行指定（§4），前端设计会话不写后端提示词。

## 1. 结论摘要

1. **拆成两段（§5，§10 Q1）：** FE4a 不依赖 BE-b，可以马上开始：FE3 带入项、Q21 文案、视觉令牌、取证工具，并在 P6 退出的 backend 树上重跑真实旅程与 t1。FE4b 接入 BE-b，等 BE-b 交付后开始，正式的真实数据重拍放在 FE4b。
2. **FE4a 的合入点（§6，§10 Q2）：** `fe-vnext` 快进到 main `16ffe72829`。这个提交包含 `fe-fe3c-exit` 的目标，`vnext/` 树为 `49c1de43be`，与本地 tag `p6-exit` 的目标 `b0fc25e881` 相同。不合入其后可能含 P7 代码的 main。
3. **后端变化（§6.2）：** 设计会话核对了 `fd9e383d76..16ffe72829` 的 `vnext/` 差异。`http/`、bundle 与 surface 组装、golden、部署和依赖输入都没有改，新的诊断码只是代码搬移。FE4a 预期不需要刷新 OpenAPI 快照。
4. **BE-b 是 FE4b 的唯一前置，目前没有排期（§4）：** 第二步设计（实现层）未写，后端未实现，P7 草稿未提及 BE-b。由谁写第二步、何时写、实施与审核由哪个会话负责、与 P7 如何衔接，都需要 owner 决定（§10 Q4、Q5）。
5. **前端 kickoff §3.3 的三个开放缺口（§3.7）：**
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

- **占位导航：** `features/view-model/model.ts::fallbackNavigation`（`contract_version` 为 `frontend-placeholder/business-navigation/v1`）；手写的占位产物在 `src/test/fixtures/source/business-navigation*.json`、`navigation-diagnostics.json`，以及各后端 fixture 下的 `projections/business-navigation.json`。
- **浏览器中的行标识计算：** `features/view-model/table-rows.ts::snapshotRowIdentity` 及其规范编码（`canonicalTemporal`、`frame` 等），即 FE2 kickoff §5.3 的自校验匹配。
- **读取导航产物：** `features/bundle/presentation.ts` 已按 `projection_kind = BUSINESS_NAVIGATION` 读取导航产物与 `diagnostics_ref`；导航诊断文案在 `features/view-model/diagnostics.ts::NAVIGATION_COPY`（BE-b §4.7 的 10 个编码）。
- **Preview 公式抽屉：** `pages/ComparisonPage.tsx` 中有“改前公式在 BE-b 实现后提供”的说明。

### 2.2 后端与 main

| 项 | 值 |
| --- | --- |
| main | `16ffe72829`（FE3c 退出记录）；`vnext/` 树 `49c1de43be` |
| `p6-exit` | 本地附注 tag，对象 `e4791d4e8d` → `b0fc25e881`，未推送；`b0fc25e881:vnext` = `49c1de43be`，与 main 相同。tag 说明写明“Frontend, P7, independent SDK and production release are not signed off” |
| FE3c 期间的 `vnext/` | `6368c9c40c`（main `fd9e383d76`） |
| `fd9e383d76..16ffe72829` 的 `vnext/` | 72 个文件：S5 的计算缓存（comparison、risk、snapshot export、control DB），S6 的 History 元数据与校验，以及测试与 benchmarks。逐类核对见 §6.2 |
| 依赖镜像 | `--print-input` 的五个输入文件（`backend/pyproject.toml`、`backend/uv.lock`、`backend/.python-version`、`rust/Cargo.lock`、`rust/rust-toolchain.toml`）与 `vnext/scripts`、两个 backend Dockerfile 在该区间都未改。预期仍得 `gateway-backend-deps:lock-578e079b762e`。输入还包括节点本机基础镜像的身份，因此以审核会话发出提示词时在所选节点上的实测为准 |
| RS 依赖镜像 | `repository_service/uv.lock` 未改，仍为 `gateway-p2r1-repository:lock-6dc9659f0aee` |

### 2.3 BE-b

- 第一步（数据结构与业务规则，含 §4.7–§4.10）已由 owner 确认（2026-11-02、2026-11-03）。
- 第二步（实现层设计：在哪一步计算、缓存、计时预算、golden 组织、History 侧注释的持久化）按草案应在“P6 S5 接近完成时”定稿，**尚未写**。P6 已在本地退出，这个时点已过。
- 后端没有实现。按 FD8，实现排在 P6 退出之后、Phase 8 之前。
- 开发主机上未提交的 P7 草稿没有提到 BE-b。本文不以这些草稿为依据（§4）。

### 2.4 Q21

后端答复（`d3450675bf`，2026-11-09）核对了 `56720104af` 到 `6368c9c40c` 两棵树的差异，结论：

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

| # | 项 | 处理 | 依据 |
| --- | --- | --- | --- |
| B1 | 业务分组 | 按导航产物的 `groups` 通用渲染，分组名与顺序取自后端，不写死槽位；未知 `group_key` 按通用分组显示；按 `group_key`、`item_key` 寻址（命令层、URL、筛选）；`row_filter` 只在本地执行；按身份过滤的页签用 `facts`，整表页签从 surface 与 `RiskReport` 读取 | BE-b §4.2、§4.3、§4.6；前端 kickoff §4.5 |
| B2 | 列展示与列序 | `SurfaceColumn.display_order` 决定列序，`pinned` 决定固定列；列宽与对齐仍由前端计算；不提供隐藏 | BE-b §4.1；§6 Q4 |
| B3 | 中文显示名 | 表名与列名取 `SurfaceTable.display_name`、`SurfaceColumn.display_name`；Debug 模式另显示标识符 | BE-b §4.1；UI 优化方向 C6 |
| B4 | 行定位产物 | 改用 `row_locator_ref`；删除 `snapshotRowIdentity` 与全部规范编码、自校验和“本表的变更行无法定位”的匹配路径；ref 为 null 时按表级展示（BE-b §4.8 的既定回退） | BE-b §4.8；FE2 kickoff §5.3 末条 |
| B5 | 视图 ID | 前端按 `pair_id` 区分视图，修复前后都不受影响；FE4b 核对代码中没有依赖 History `-p<i>` 形式的逻辑，模拟数据改用修复后的取值 | BE-b §4.9 |
| B6 | 诊断编码 | 导航诊断按 BE-b §4.7 就地提示，分组头汇总个数，`DEVICE_ROWS_UNASSIGNED` 提供“查看整表”；surface 诊断按 §4.10 的稳定编码更新文案表，删除被取代的自由文本条目 | BE-b §4.7、§4.10 |
| B7 | Preview 改前公式 | 双侧浏览表补齐基线侧后，Preview 与 History 一样显示改前、改后对照，删除“改前公式在 BE-b 实现后提供” | BE-b §4.4；前端 kickoff §8 |
| B8 | 移除占位数据 | 删除手写的占位导航与诊断 fixture；后端 fixture 用 BE-b 的生成器重新生成（同一批上传输入，逐字节不变） | 前端 kickoff §4.5 |
| B9 | 保留回退 | 某个比较对没有导航产物时仍是“全部表一个组、节点即表、无页签”；没有注释时用标识符；没有 `display_order` 时按 DDL 顺序。这是正式行为，不是兼容层 | 前端 kickoff §4.5 第一条 |

FE4b 的细节（fixture 的生成方式、Contract 版本号的判定、按导航的程序判据、截图清单）在 BE-b 第二步与 Contract 固定后，由本文第 2 步写定（§5.3）。

### 3.2 侧栏层级（§4.6，FE4b）

前端 kickoff §4.6 留下的问题：导航层级“视图 → 分组 → 节点 → 页签”能否精简。按 BE-b 第一步的结构判断：

- 多页签的项是业务需要：转发通道有 9 类转发表加“定值”，装置有 11 类测点表，规约通道有两张规约表。不能把“项”和“页签”压成一层：装置数 × 11 会把侧栏撑得很长。
- 只有一个页签的项很多：全局参数的各整表项、“其他表”中的每张表、装置总表、网口配置表。为这些项显示页签栏没有信息量。
- 大多数比较只有一个视图：MODIFIED_ONLY 的 Preview、两节点的 History。

**建议（§10 Q6，甲）：** 层级的定义不变，渲染时按需折叠：

- 只有一个视图时不显示视图分段控件；
- 只有一个页签的项点击后直接打开该表，不显示页签栏，表名显示在信息行；
- 空组不显示，这是 BE-b §4.2 允许的；
- 有两个及以上页签的项保留页签栏，规则同 S3 草图。

侧栏搜索同时匹配项名、页签名、表的显示名与标识符。在 FE4b 实现：占位数据没有页签，规则只有在 BE-b 数据上才能验证。

### 3.3 真实数据重拍（前端 kickoff §6）

- **FE4a：** 在 P6 退出的 backend 树上重跑 t1 旅程（FE3 kickoff §8 的步骤与判据），产生参考截图，只留在节点上，SHA256 写入 handoff，不作验收。同时把关键页面的截图清单固定在 t1 套件中，FE4b 用同一套用例重拍。
- **FE4b：** 正式重拍。在 BE-b 交付后的 backend 上，用 t1 数据在 1280 与 1920 下重拍关键页面，交 owner 看图确认。暂定页面如下，第 2 步定稿：
  - 工作台：组态树与详情面板；
  - Preview 差异浏览：v1（全部新增）与 v2 FULL 的两个视图；
  - 侧栏各分组展开：转发通道、二次装置（含复合信号虚装置）、通讯规约、全局参数、其他表；
  - 装置页签（按身份过滤）；
  - 表格的中文列名、业务列序与固定列；
  - 行定位后的修改行连线与风险底色；
  - 导航诊断（若 t1 数据产生）；
  - 审核模式；
  - 历史比较三节点的结果；
  - 归档主线（t1 v1 预期没有业务核验异常，截核验概况）。

  t1 的 `composite_changed` 为 0，Preview 改前、改后公式对照由模拟接口截图覆盖。
- **节点：** 按 DC91 选合格空闲节点，见 §2.5、§7.1。

### 3.4 FE3 带入项（FE4a）

| # | 来源 | 内容 | 处理 |
| --- | --- | --- | --- |
| C1 | FE3b N2（复审第 2、3 轮） | `resumeNotice` 在页面生命周期内不归零，再次提交后的“提交正在执行…”仍显示在红色提示框里 | 开始新的提交或上传时清除；或只在快照仍属于续做结果时显示。加一条模拟用例：续做后再次提交，提示框不再出现 |
| C2 | FE3b N6（复审第 3 轮） | `retryResume` 不经过 `refresh()` 的在途合并；W9④ 第一次重试后的断言不能区分新旧状态；G3 的放宽也作用于合并数据集 | `retryResume` 经过在途合并，快速连点只产生一次读取序列（用例断言 attempt 读取次数）；W9④ 的断言改为能区分重试前后的内容；G3 的放宽只作用于单页切片 |
| C3 | FE3b N7（证据核对） | 预览页顶栏中撤回与提交的禁用原因并排、没有分隔，读起来像一句话 | 两个原因分开显示，各自对应自己的按钮（`aria-describedby`），中间有明确分隔。补拍 `fe3b-w6-*` 三张 |
| C4 | FE3b N8（证据核对） | 截图中的等待时长按墙钟计算，每次运行的截图都不同 | 截图用例固定时钟（Playwright `page.clock`），等待时长显示固定值；同一提交连续两次运行，这些截图逐字节相同（由审核会话抽查） |
| C5 | FE3c 审核 N2 | 过期通过后只重读 review，没有重读 History；V12 重读后的模拟数据仍没有处置 | 409 `BASELINE_VERSION_CONFLICT` 与 `ARCHIVE_CLOSED` 之后，同时重读 review 与 History；V12 重读后的模拟数据带处置，并断言按 FE3 kickoff §6.4 显示 |
| C6 | FE3c 审核 N3（含 FE3b 复审第 1 轮 N2） | 来源详情的摘要前 12 位没有悬停全文；理由超过 3 行不折叠，很长的单行理由也不折叠；原始码没有放进悬停提示 | 摘要悬停显示全文；理由按渲染行数折叠（超过 3 行时显示前 3 行加“展开”），单行长理由同样适用；`issue_code`、`subject_digest` 等原始值放进悬停提示（C6） |
| C7 | FE3c 审核 N4 | J1 第 8、10、11、13 步与 J2 第 1、7、8 步的接受用 API 助手完成；J1 第 14 步由提交人做历史比较 | 都改为经界面接受；J1 第 14 步改由审核人执行。真实旅程会变长，按调试运行的实测报告耗时 |
| C8 | FE3c 审核 N5、复审第 1 轮 M1 | `collectionNotice`、`pendingNotice` 在同一对话框会话中不清除；关闭返回 409 后，冲突提示替代了集合变化提示（FE3 kickoff §16.4） | 冲突提示与集合变化提示分两处显示，每次加载后清除待用提示；补两条模拟用例：关闭 409 后集合变化，两条提示都出现；集合未变时后续加载不显示旧的冲突提示 |
| C9 | 复审第 1 轮 M2 | 关闭对话框正文“关闭提交提交 2（不归档）”显示名重复；“确认关闭”成功后仍可点击 | 正文直接用显示名（例如“关闭提交 2（不归档）”）；成功后“确认关闭”不再可用，只保留关闭对话框的按钮。owner 看图时没有另作决定，按带入项处理 |
| C10 | 复审第 1 轮 M3 | 详情映射的单测没有覆盖 `INITIAL_SOURCE_UNEXPLAINED`、`GENERATION_TIME_LAST_NOT_MAX`、`TIME_ABNORMAL_INITIAL` 与“② 早于 ①” | 在 view-model 单测中补齐，按 FE3 kickoff §16.3 的文字逐条断言 |
| C11 | 停止核对 N9 | `workspace-shell.spec.ts` 中 11 处 `unrouteAll()` 不带参数，其中 `timeoutFirstCompare`、`historyBundleDelayMs`、`slowPreview` 三处有延迟 | 全部改为 `{ behavior: "wait" }`；带延迟的三处改用测试控制的闸门（同 FE3c fix2 的做法）。不改其他断言 |

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

**建议（§10 Q7，甲）：** 删除这个未定义的引用，直接使用 `--color-surface-muted`，外观不变，不新增黄色令牌。理由：

- owner 已接受灰底；
- UI 优化方向 §7.4 有意不用黄色，避免与风险色混淆、夸大问题；
- 提示类样式应当并入现有语义（A2：“徽章与提示色并入第 3 节语义色”），不另起一套；
- 只删一个未定义的变量，截图不变，不需要 owner 重新看图。

乙：定义一个淡黄色的 `--color-warning-soft`，需要设计会话补语义色画板并交 owner 看图，相关截图全部重拍。

### 3.7 前端 kickoff §3.3 仍开放的缺口

| 缺口 | 处理 | 依赖 |
| --- | --- | --- |
| 历史初始备份节点（随归档提交上传的原始组态备份，可查看差异、加入比较） | **FE4 不做**（§10 Q8）。owner 在 FE2 kickoff Q4 决定 FE2 不做，是否需要由 owner 另定。需要时作为后端任务单独立项，再开一个前端阶段接回 | 后端：先确认 FULL 上传的 ① 是否作为可寻址的历史节点保存；History 投影增加该类节点；`POST /v1/history-compares` 接受该类节点。前端不能推断 |
| 首批空基线时禁用上传第 ① 步 | **FE4 不做**（§10 Q9），保持 FE2 kickoff Q18 的决定：界面不禁用 | 后端：在 History 中提供“基线为空”的事实（`INITIAL` 可以由部署映射带内容）。建议作为独立的小后端任务，不并入 BE-b：它与导航和展示无关，并入会扩大 BE-b 的审核面 |
| surface `diagnostics_summary` 中的自由文本 | **随 FE4b 接入**：owner 2026-11-03 已把它并入 BE-b（草案 §4.10、§6 Q10）。前端 kickoff §9 写的“不属于 BE-b”已过时，由本分支的另一个提交更正 | BE-b §4.10 |

### 3.8 取证工具（FE4a）

FE3 中出现过两类取证错误：FE3b 的 04 证据 handoff（`a300b16485`）有 5 个 SHA 抄错；FE3c 的 wrapper 把 `LOG_DIR` 取成了 `$2`，入口命令没有运行。另外 FE3c 证据核对的 E2 中，wrapper 的两个结果字段显示为 `MISSING`。FE3 的 wrapper 都是临时写在节点上的，没有经过审核。

FE4a 在 `frontend/scripts/` 下提交两个工具，由审核会话审核，FE4a 与 FE4b 的取证都使用它们：

- **证据 wrapper：**
  - 写日志前检查参数：参数个数；worktree、日志、截图目录都是绝对路径，日志目录已存在，截图目录在 worktree 外；没有他人的有效占用标记（用途为计时测量时等待）。任一不满足即以非 0 退出，不运行入口；
  - 记录 hostname、起止 UTC、起止 HEAD 与 `HEAD:frontend`、`HEAD:vnext`、起止 `git status --porcelain --untracked-files=all`、开始与结束时的占用标记；
  - 用 `set -o pipefail` 取入口自身的 exit code；
  - 写日志的 `.sha256` 旁注文件；
  - 从入口日志按整行取结果字段，取不到时写明原因，不写 `MISSING`；
  - 不替真实 backend 入口获取占用标记。
- **十六进制回源脚本：** 读取 handoff，找出全部十六进制值，逐个与来源对照：节点上现场重算的文件 SHA256、取回的日志与清单原文、git 对象。输出每个值的来源；报告未命中的值与长度不是 7–12、40、64 的值；“路径 + SHA”成对出现时核对配对关系。在宿主机用 `python3 -I` 运行，不依赖 Node。

这两个工具只是辅助，不改变证据规则：运行仍由入口脚本完成，审核会话仍独立回源。

### 3.9 不在 FE4 范围

- 历史初始备份节点与首批空基线（§3.7）。
- Phase 7 可能增加的排队状态与统计展示：随 P7 的接口另开前端阶段，不在 FE4。
- 正式 SSO、部署形态、外部驱动通道、深色主题。
- Preview 顶栏的上传快捷入口、历史比较结果抽屉布局、1280 下提交对话框滚动：已接受为 FE2 的偏差（FE2 kickoff Q19）。
- 浏览器中重新解析 SQL、计算来源图或生成时间；FE4b 之后也不在浏览器中计算行标识。
- 在 Preview 中为 `composite_signal_point`、`device` 以外的表补齐改前侧（BE-b §4.8 写明不在范围）。

## 4. BE-b 的前置与排期

| 事项 | 现状 | 建议 | 谁决定 |
| --- | --- | --- | --- |
| 第二步设计的作者 | 前端 kickoff §10 把“BE-b 设计”列为前端设计会话的职责，§10 末行又写 BE-b 的实施与审核按后端流程另行指定。第一步已由前端设计会话写完 | 第二步由后端设计会话执行：内容是计算位置、缓存（S5 的计算缓存）、计时、golden、Repository/History 侧的注释持久化、Rust 与 Python 解析器的注释捕获，都在后端实现层。前端设计会话核对面向前端的部分：Contract 形状与第一步一致、fixture 与 golden 覆盖第一步的规则，并答复业务规则问题 | owner（Q4） |
| 第二步的时间 | 草案定的时点（“S5 接近完成”）已过 | 现在开始，不等 P7 | owner（Q4） |
| 实施与审核会话 | 无 | 按 AGENTS“角色与子 agent”新建后端实施与独立审核角色，不由前端会话承担 | owner 或后端协调者（Q5） |
| 与 P7 的衔接 | P7 草稿未提及 BE-b，不作依据 | BE-b 会改变 surface、bundle 摘要与 golden，并在 Preview/History 路径上增加计算。建议作为 main 上的独立后端任务，在 P7 中改动 Preview/History 组装或产物的阶段之前，至少先固定 BE-b 的 Contract 与 golden；具体先后由后端设计会话评估、owner 决定 | owner（Q5） |
| 范围 | 草案 §4.1–§4.10 与 §5 的约束 | 不拆。FE4b 需要全部内容；行定位、视图 ID 与稳定编码都会改变摘要，分开做会多改几次 golden | 后端设计会话在第二步中确认 |

**FE4b 需要 BE-b 交付的内容（建议写进 BE-b 第二步的交付清单）：**

1. Contract：Business Navigation v1（含诊断产物）；Comparison Surface 修订（`projection_kind`、`SurfaceColumn.pinned`、`display_order`、`row_locator_ref`、视图 ID 规则）；Comparison Bundle 修订（Preview 双侧浏览表的闭包规则）；草案 §7 所列过时文档的替换。
2. golden：导航、导航诊断、行定位、surface 与 bundle。
3. 一个能在后端镜像中生成前端 fixture 的入口（现有 `frontend/scripts/generate-backend-bundle-fixture(s)` 调用的后端能力随之产出真实导航），或者明确的调用方式。
4. 合入 main 的提交、`vnext/` 树与退出 tag；依赖镜像 tag 与身份（依赖输入有变化时，按 AGENTS 在 CT201 构建并预填充）。
5. 该树的生产 OpenAPI 原件，以及与 `6368c9c40c` 原件规范化后的差异说明（HTTP 没有改动时写明无差异）。
6. §4.10 稳定编码的完整列表，标明取代了哪些旧条目。

## 5. 阶段安排

### 5.1 是否拆段

**建议拆（§10 Q1）。** 理由：

- BE-b 的第二步、实施、审核都还没开始，排期取决于 owner 对 P7 的安排，可能需要数周；带入项、Q21 与令牌现在就能做，等待只会让上下文变旧；
- FE4a 在 P6 退出的 backend 树上重跑真实旅程与 t1，前端与新后端的组合尽早得到验证；之后 FE4b 的问题只剩 BE-b 本身；
- 两段改的地方基本不重叠：FE4a 改归档对话框、续做提示、诊断文案与测试；FE4b 改导航、表格列、行定位与 fixture；
- 代价：多一次审核与一次取证。按 DC98，取证只跑受影响的项（§7.2）。

不拆的代价：FE4 整体等 BE-b，带入项拖到 BE-b 之后，且与 BE-b 的接入混在同一次审核中。

### 5.2 子阶段

| 子阶段 | 内容 | 前置条件 | 退出 tag | 审核范围 | 退出条件 |
| --- | --- | --- | --- | --- | --- |
| FE4a 带入项与新后端回归 | `fe-vnext` 快进到 main `16ffe72829`（§6.1）；§3.4 C1–C11；§3.5 Q21；§3.6 令牌；§3.8 取证工具；在 `vnext/` 树 `49c1de43be` 上跑真实 e2e 完整集与 t1；固定 FE4b 重拍用的截图清单（§3.3） | 本文经审核会话核对与 owner 确认（Q1、Q2、Q3、Q7）；审核会话现场核对节点、镜像与 `--print-input` 后发出提示词 | `fe-fe4a-exit` | `fe-fe3c-exit..<FE4a 候选>` | 审核通过；证据（§7.2 FE4a 行）各一次通过；C3、C4、C9 及有变化页面的截图经 owner 确认 |
| FE4b BE-b 接入与正式重拍 | §3.1 B1–B9；§3.2 侧栏；§3.3 正式重拍；按 BE-b 交付合入 main、刷新 OpenAPI 与 fixture；FE4 退出 | `fe-fe4a-exit`；BE-b 退出并合入 main，§4 的交付齐全；本文第 2 步（FE4b 设计）经审核与 owner 确认 | `fe-fe4b-exit`（即 FE4 退出） | `fe-fe4a-exit..<FE4b 候选>` | 审核通过；证据（§7.2 FE4b 行）各一次通过；正式重拍与 FE4b 截图经 owner 确认 |

- 两段都在 `fe-vnext` 上进行，合入 main 只用快进或合并，不 rebase，不改写已被引用的提交。
- **路径核对（每段都做）：** 设 `<main>` 为最后一次进入 `fe-vnext` 的 main 提交：
  - `git rev-parse <候选>:vnext` 与 `git rev-parse <main>:vnext` 相等；
  - `git diff --name-only <main> <候选>` 只含 `frontend/` 与 `docs/frontend-vnext/` 下的路径。
- 审核范围中来自 main 的文档与 `vnext/` 不属于前端审核，由后端审核负责。main 上直接提交的 `frontend/` 改动属于前端审核范围（目前没有）。
- FE4a 期间不再合入 main。后端若在 main 上改 `vnext/`，不影响 FE4a；只有 FE4a 确实需要时，才由审核会话重核依赖镜像与比对原件后决定是否重新合入，实施会话不自行合入。
- FE4b 的合入点、依赖镜像与比对原件在第 2 步写定。

### 5.3 FE4b 的第 2 步

BE-b 第二步与 Contract 固定后，前端设计会话修订本文，写定：

- 合入点与路径核对；OpenAPI 刷新与比对原件；
- fixture 的重新生成：生成器、上传输入、哪些手写占位 fixture 删除；
- 导航、列与行定位的模拟数据规则：只构造后端可达的组合，规则同 FE2 kickoff §7.5；
- 程序判据：t1 上每张 surface 表恰好被认领一次（按身份过滤的共享表可在多个装置下出现）；有 `row_locator_ref` 的表全部定位，没有出现表级回退；回退的表数只报告；
- 截图清单与 owner 看图项；
- FE4b 的实施与审核提示词。

FE4b 的设计期间若发现 BE-b 的 Contract 与第一步不一致，交 owner 转后端，前端不自行假设。

## 6. 合入点与后端变化

### 6.1 FE4a：快进到 main `16ffe72829`

- `fe-vnext` 当前 `e22e39ba15` 是 `16ffe72829` 的祖先，直接快进，没有合并提交：
  - 包含 `fe-fe3c-exit` 的目标 `06b454b0ef`（FE3c 证据 handoff）与 main 合入提交 `475022300c`；
  - `vnext/` 树变为 `49c1de43be`，与 `p6-exit` 的目标 `b0fc25e881` 相同。
- **为什么是这个提交：**
  - 它是 FE3 退出记录，`vnext/` 等于 P6 退出验证过的树；
  - 用 tag `p6-exit` 的目标 `b0fc25e881` 不行：它不含 FE3c 的合入，快进不到；
  - 新建分支没有好处：前端 kickoff §7 的流程以 `fe-vnext` 为唯一长期分支，快进不改写任何提交。
- **不合入之后的 main：** 之后的 main 可能含 P7 代码，且尚未验证。
- **`p6-exit` 尚未推送：** FE4a 的证据只绑定本地树 `49c1de43be`。若推送前 P6 的退出提交发生变化，由审核会话重新核对，再决定是否重新合入（§10 Q2）。
- **审核范围的说明：** `fe-fe3c-exit..<FE4a 候选>` 会包含 S5、S6 的全部后端提交，按 §5.2 不属于前端审核；`16ffe72829:frontend` 与 tag 相同，范围内的前端改动全部来自 FE4a。

### 6.2 `6368c9c40c..49c1de43be` 对前端的影响

方法同 FE3 kickoff §15.5 第 9 项：按前端能看到的几类，读 `git diff fd9e383d76 16ffe72829 -- vnext` 逐类核对。设计会话只读源码，没有运行产品。

| 类别 | 核对 | 结论 |
| --- | --- | --- |
| OpenAPI、HTTP DTO、错误码 | `backend/src/gateway_backend/http/` 下没有任何改动（含 `schemas/`、`errors.py` 与路由）；`application/workspace/`（上传上限）、`settings.py`、`deploy/` 未改 | 无变化。预期运行时 `/openapi.json` 规范化后与现有快照逐字节相同 |
| bundle、manifest、closure、tar | `capabilities/bundle_assembly/`、`capabilities/surface_assembly/`、`domain/`、`vnext/fixtures/`（含全部 golden）未改；`artifacts/` 只改了 `computation_cache.py`、`snapshot_table_export_cache.py` 两个缓存文件 | 无变化。S5 的计算缓存只是复用已有结果，不改变产物字节 |
| surface 与比较、风险的取值 | `capabilities/comparison/` 改了 6 个文件、`risk_evaluation/` 改了 4 个，Rust `records/` 改了 3 个：都是缓存编解码、任务身份与持久化。diff 中出现的大写编码都是已有取值（记录族、变化类型、有序事件等），以及从旧位置原样搬移的 `ORDERED_PROVENANCE_MISSING`、`ORDERED_PROVENANCE_INVALID`。新增的 `ValueError("row_diff_detail_policy is invalid")` 是缓存任务的内部校验，即使写入诊断，也只会以异常类名出现，归入“内部错误” | 无新的诊断码。§3.5 的文案表适用于 `49c1de43be` |
| operation 与 checkpoint | `application/` 下的 History、Preview、Submit 与 checkpoint 改动集中在缓存接线与精确提交的校验；`CHECKPOINT_JOB_STATE_MISMATCH` 在 `6368c9c40c` 中已有，是内部恢复码，不经 HTTP DTO 返回给前端 | 无前端可见变化 |
| 依赖与镜像 | 五个依赖输入文件、`repository_service/uv.lock`、两个 backend Dockerfile、`vnext/scripts` 都未改 | 依赖镜像预期仍为 `lock-578e079b762e`，RS 为 `lock-6dc9659f0aee`；以现场 `--print-input` 为准 |

- `real_dump_journey.py` 在 `benchmarks/` 下有改动（S6 的 t4 W1/W2 范围）。t1 的预期值仍按 FE3 kickoff §8.3，在运行时从被测树读取模块级常量；读不到即停止。
- FE4a 真实旅程中若出现上表没有预期的诊断码，在 handoff 中列出编码与出现位置，不作为停止条件（同 FE3 kickoff §2.3 末段）。

### 6.3 OpenAPI 快照与比对原件

- **FE4a 不刷新快照。** 依据 §6.2 第 1 行。
- **比对原件（§10 Q3，甲）：** FE4a 不要求后端为 `49c1de43be` 交付新的生产 OpenAPI 原件。每次真实运行照常在浏览器用例之前，把运行时 `/openapi.json` 与已提交的快照按 FE3 kickoff §5.1 规范化后逐字节比较；不一致即停止，不在 FE4a 中刷新，交设计会话，由 owner 转后端交付该树的原件后再定。理由：
  - FE3 要求原件，是因为要用它刷新快照，原件是快照的独立来源；FE4a 不刷新，快照的来源仍是 `6368c9c40c` 的原件；
  - `http/` 一行未改；
  - 运行时比对本身能发现任何 schema 变化。
- 乙：发出 FE4a 提示词前，由后端为 `49c1de43be` 交付原件，取件方法同 FE3 kickoff §5.2，交付方为后端设计会话指定的会话。代价是多一次后端起栈，结论预期与甲相同。
- **FE4b：** BE-b 交付的树的原件由 BE-b 的后端交付方提供（§4 第 5 项），按 FE3 kickoff §5.1、§5.2 刷新与比对。

### 6.4 合入 main

- **FE4a 退出：** 附注 tag `fe-fe4a-exit` 指向 FE4a 证据 handoff。先把审核报告合入 main，再以 `--no-ff` 合入 tag。main 届时可能已有 P7 的文档或代码；FE4a 只改 `frontend/` 与 `docs/frontend-vnext/`，预期没有冲突，由审核会话先试合并。
- **FE4b 退出（FE4 退出）：** 同样流程，tag `fe-fe4b-exit`。
- tag、合入与推送由设计会话在 owner 确认后执行；推送需要 owner 授权。

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

| 子阶段 | 内容 | 性质 |
| --- | --- | --- |
| FE4a 调试 | `run-tests.sh --e2e --screenshots`（`GATEWAY_FE_TEST_WORKERS=2`）；`run-real-backend-e2e.sh --suite journeys`（完整集，含 C7 改动后的 J1、J2）；`--suite t1`；`validate-upload-package.sh` | 调试，各至少一次通过后送审 |
| FE4a 证据 | 审核通过后，在最终候选的 clean、已提交 detached worktree 上各运行一次：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`--suite journeys`、`--suite t1` | 证据；耗时只报告 |
| FE4b 调试与证据 | 同 FE4a 四项；`journeys` 与 `t1` 加入导航、列与行定位的程序判据（第 2 步）；t1 产生正式重拍截图 | 第 2 步写定 |

- 调试与取证分开（DC30）：调试只跑 focused 与出问题的那一段；证据只在审核通过后运行。
- FE4a 证据仍跑四项。前端没有沿用机制，`frontend/` 树变了，模拟接口全量必须重跑；backend 树也变了，`journeys`、`t1` 与上传包校验也要在新树上重跑。按 DC98，不另加重复采样或性能测量。
- **失败与重做（AGENTS main，DC68 的 2026-11-08 修订）：** 工具或取证步骤失败时：
  - 先停止该次执行，保留原始日志与 SHA256；
  - 同一具体故障最多三轮自行修复与复验；
  - 三轮仍未解决、原因或副作用不明，或超出授权时，交 owner。

  不得无修改重试，不改预期去掩盖结果。产品问题按审核流程处理，不按 DC68 重做。

### 7.3 截图

- **模拟接口：** `run-tests.sh --screenshots` 的全量截图照常生成（1280、1920）。C4 之后，等待时长固定。
- **FE4a 交 owner 看图的范围（只看有变化的页面）：**
  - C3 预览页顶栏的两个禁用原因（`fe3b-w6-withdraw-busy`、`fe3b-w6-preview-resumed-card`、`fe3b-w6-attempt-running`）；
  - C9 关闭对话框与关闭成功后的结果（`fe3c-close-dialog`、`fe3c-close-result`）；
  - C6 来源摘要与长理由的折叠；
  - C8 冲突提示与集合变化提示同时出现的状态；
  - C4 之后显示固定等待时长的截图，抽一张确认文字；
  - Q7 选乙时，全部用到 `.form-warning` 的截图。
- **审核会话对比：** 把 FE4a 全量截图与 FE3c 证据截图（04 `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/`，清单 SHA256 `63a0e6006952152e7cd59db22ada9b34e4774f4f99676c22041b31f9ea1129f2`）按文件名比较，列出逐字节不同的文件，确认都在上面的范围或由 C4 引起。
- **真实 backend 与 t1：** FE4a 的参考截图只留在节点上，SHA256 写入 handoff，不作验收；FE4b 的 t1 重拍交 owner 看图（§3.3）。
- **对照依据：** 审核会话对照 `sketches/` 与 UI 优化方向核对布局、层级、语义色、按钮层级、禁用原因与焦点样式，不做像素级比对。

### 7.4 t1 与 M1

- **t1：** FE4a、FE4b 都重跑：backend 树（FE4a 为 `49c1de43be`，FE4b 为 BE-b 的树）与前端都有变化。步骤、判据与输入核对按 FE3 kickoff §8.1–§8.3：两份清单逐文件核对，预期值从被测树读取，FULL 的两个比较对按 `pair_id` 取用，`baseline_to_initial.table_count` 记录实际值。
- **M1（FE3 kickoff §8.4，Q12、Q20、Q23）：**
  - t1 第 1 步 MODIFIED_ONLY 的 renderer 增量只作回归对照：与 FE3a t1 v1 的 24.86 MiB 对照，超过 2 倍时报告并交设计会话；
  - 第 4 步 FULL 与第 1 步在同一浏览器实例中，只报告，并注明不可比较；
  - **打包代码有改动时**，在有 `t4-v1` 目录的节点上用新浏览器重测 t4 v1 的 MODIFIED_ONLY 与 FULL，各 3 次，按 §8.4 的标准判定。FE4a 与 FE4b 都不计划改打包代码；
  - **打包代码的范围：** `features/workbench/upload-package.ts`（打包、压缩与 `buildTar`）与 `features/workbench/UploadStepCard.tsx` 的打包流程。FE3 kickoff §8.4 写的 `features/upload/` 在仓库中不存在，以这两个文件为准；
  - 审核会话用 `git diff --stat <范围起点>..<候选> -- frontend/src/features/workbench/upload-package.ts frontend/src/features/workbench/UploadStepCard.tsx` 核对是否触发。

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
- 需要改动打包代码，但 t4 重测（§7.4）不能在同一阶段完成；
- 需要后端新增字段或接口，或需要修改 `vnext/` 下的 Compose、脚本或配置；
- C1–C11 的修改需要改变 FE3 kickoff 已定的业务规则（例如 §16 的接受、撤销、关闭规则）：停下交设计会话；
- 清理核对失败。

**FE4b：** 在第 2 步写定。原则已经确定：

- BE-b 的 Contract 或产物与第一步不一致，不自行适配，交 owner 转后端；
- 需要在浏览器中重新计算行标识、按表名推断分组或列序时，停下交设计会话。

## 9. 风险

- **BE-b 长期未排期：** FE4 无法退出。FE4a 退出后，前端停在一个已取证的状态。owner 可以在 FE4a 退出时决定是否先把 FE4a 的结果作为 Phase 8 shadow 的前端候选；这不改变 FD8。
- **P7 改动 `vnext/` 后 FE4a 想跟进：** 按 §5.2，FE4a 期间不合入。
- **C7 让真实旅程变长：** 每次接受都走界面。用调试运行的实测评估；明显变长时报告，不删减步骤。

## 10. owner 问题

| # | 事项 | 建议与理由 |
| --- | --- | --- |
| Q1 | FE4 是否拆段（§5） | **拆成 FE4a 与 FE4b**，tag `fe-fe4a-exit`、`fe-fe4b-exit`，内容、前置与退出条件按 §5.2。理由见 §5.1：BE-b 没有排期；带入项与 Q21 现在可做；FE4a 尽早在 P6 退出的 backend 上验证；两段改动基本不重叠。代价是多一次审核与取证 |
| Q2 | FE4a 的合入点（§6.1） | **`fe-vnext` 快进到 main `16ffe72829`**（`vnext/` 树 `49c1de43be`，等于 `p6-exit` 的树），FE4a 期间不再合入 main。理由：它是 P6 退出验证过的树；快进不产生合并提交，也不改写提交；`p6-exit` 的目标本身不含 FE3c 的合入，无法快进。注意：`p6-exit` 是本地 tag，FE4a 的证据绑定本地树；若推送前 P6 的退出提交发生变化，由审核会话重新核对 |
| Q3 | FE4a 是否需要新的生产 OpenAPI 原件（§6.3） | **甲：不需要。** 运行时比对与快照一致即可，不一致即停止，再请后端交付原件。理由：FE4a 不刷新快照，`http/` 未改，运行时比对能发现任何变化。乙：先请后端交付 `49c1de43be` 的原件，多一次后端起栈 |
| Q4 | BE-b 第二步由谁写、何时写（§4） | **由后端设计会话写，现在开始；前端设计会话核对面向前端的部分。** 理由：第二步全是后端实现层的内容（计算位置、S5 缓存、计时、golden、History 侧注释持久化、解析器）；第一步已固定前端需要的数据结构。前端 kickoff §10 中“BE-b 设计”一项随之改为“BE-b 第一步与面向前端的核对” |
| Q5 | BE-b 的实施与审核会话，以及与 P7 的先后（§4） | **新建后端实施与独立审核角色；作为 main 上的独立后端任务，在 P7 改动 Preview/History 组装或产物的阶段之前，至少先固定 BE-b 的 Contract 与 golden。** 理由：BE-b 改变 surface、bundle 摘要与 golden，与 P7 同时改同一路径会互相使对方的 golden 与基准失效。P7 的计划尚未提交，具体先后由后端设计会话评估后由 owner 决定 |
| Q6 | 侧栏层级是否精简（§3.2） | **甲：层级定义不变，渲染时按需折叠**：单视图不显示分段控件，单页签的项不显示页签栏，空组隐藏，多页签保留。FE4b 实现。理由：多页签是业务需要，不能压层；单页签项的页签栏没有信息量。乙：维持现状，所有项都显示页签栏 |
| Q7 | `--color-warning-soft`（§3.6） | **甲：删除未定义的引用，用现有灰色令牌，外观不变。** 理由：owner 已接受灰底；UI 方向有意不用黄色；不需要重新看图。乙：新增淡黄色令牌，补语义色画板并重新看图 |
| Q8 | 历史初始备份节点（§3.7） | **FE4 不做；是否需要由 owner 另定，需要时作为后端任务立项，再开前端阶段。** 理由：后端还没有这类节点，前端无法推断；FE2 kickoff Q4 已决定 FE2 不做 |
| Q9 | 首批空基线（§3.7） | **FE4 不做，维持 FE2 kickoff Q18；需要时作为独立小后端任务，不并入 BE-b。** 理由：后端不拒绝在 `INITIAL` 上做 FULL，禁用第 ① 步只是界面提示；并入 BE-b 会扩大其审核面 |
| Q10 | Q21 答复分支（`p6-fe3-q21-answer`，`d3450675bf`） | **发出 FE4a 提示词前合入 main**（只新增一个后端文档，与 main 无冲突），是否推送由 owner 定。理由：FE4a 提示词与 §3.5 引用它，实施与审核会话统一用 `git show main:<路径>` 读取；在此之前只能引用提交号。合入由 owner 或后端会话执行，前端设计会话不合入后端文档 |

**不能由设计会话决定的事项：** Q2 中使用尚未推送的本地 P6 退出树；Q4、Q5 的后端会话分工与排期；Q8、Q9 的业务需要与优先级；Q10 的合入与推送；FE4a、FE4b 退出时的 tag、合入 main 与推送。

## 11. 提示词草稿

发出时间由审核会话按前置条件决定，发出前填写方括号中的值。FE4a 与 FE4b 的实施、审核都由**新会话**承担，不由 FE3 的会话或另一子阶段的会话承担（AGENTS“角色与子 agent”）。

### 11.1 FE4a 实施（前置：本文经审核核对与 owner 确认，含 Q1、Q2、Q3、Q7；Q10 已合入或明确只引用提交号；审核会话现场核对节点、镜像与 `--print-input`）

> 你是 FE4a 前端实施会话，是新会话，不沿用 FE3 实施会话的上下文。本阶段处理 FE3 的带入项、Q21 文案、视觉令牌与取证工具，并在 P6 退出的 backend 树上重跑真实旅程与 t1。不接入 BE-b。
>
> **先读（一律用 `git show main:<路径>`，不切换开发主机上任何共享 worktree 的分支）：**
> - AGENTS：“角色与子 agent”“专用测试节点”（DC91 五节点池与占用）、“前端测试（FD7）”、“Docker / Compose 验证”；testing-conventions“前端测试”“真实 backend e2e”；
> - FE4 kickoff（main `[kickoff 确认提交]`）全文，重点 §3.4–§3.8、§5.2、§6、§7、§8、§12；
> - FE3 kickoff §3.2（FE3b、FE3c 退出记录）、§4.6、§4.7、§6.4、§8、§16；FE2 kickoff §5.5；
> - 带入项的原文：`reviews/fe3b-rereview-2.md`、`fe3b-rereview-3.md`、`fe3b-evidence-check-1.md`、`fe3c-review.md`、`fe3c-rereview-1.md`、`fe3c-evidence-stop-1.md`、`fe3c-evidence-check-1.md`；
> - FE3c 的 handoff：`fe3c-handoff.md`（§5.5 只由模拟接口覆盖的项、§10 偏差）、`fe3c-handoff-fix1.md`、`fe3c-handoff-fix2.md`、`fe3c-evidence-04.md`；
> - 后端 Q21 答复：`[main 上的路径，或 git show d3450675bf:docs/backend-vnext/refactoring/formal/plans/p6-fe3-q21-answer.md]`。
>
> **起点与分支：** 在独立 worktree `/home/dev/gdds-fe` 的 `fe-vnext`（当前 `e22e39ba15`）上，快进到 main `16ffe728290e1179d9450ea160a0e6ca49473ec6`（`git merge --ff-only`），不 rebase，不合入其后的 main（kickoff §6.1）。按 kickoff §5.2 做路径核对：`<main>` 为 `16ffe72829`，候选的 `vnext/` 树必须是 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`。`--print-input` 必须得到 `[审核会话现场核对后填写，预期 gateway-backend-deps:lock-578e079b762e]`，RS 依赖镜像为 `[预期 gateway-p2r1-repository:lock-6dc9659f0aee]`，否则停止。不刷新 OpenAPI 快照：运行时 `/openapi.json` 与快照规范化后必须逐字节相同，否则停止（kickoff §6.3）。
>
> **范围：**
> 1. 带入项 C1–C11（kickoff §3.4），每项按“处理”一列完成，并补对应的用例；
> 2. Q21 文案（§3.5）：删除 4 个码，新增 4 个码，单测同步；
> 3. `--color-warning-soft`（§3.6，按 owner 对 Q7 的决定：`[甲 / 乙]`）；
> 4. 取证工具（§3.8）：证据 wrapper 与十六进制回源脚本，提交在 `frontend/scripts/`；
> 5. 真实旅程 `--suite journeys` 完整集与 `--suite t1` 在新 backend 树上通过；J1、J2 每次预检的异常集合仍按 FE3 kickoff §4.6 的表核对，不符即停；
> 6. t1 套件固定 FE4b 正式重拍用的关键页面截图清单（§3.3），本阶段只作参考截图。
>
> **不做：** 不改 `vnext/`；不接入 BE-b，不改导航、列展示与行定位；不改打包代码（需要改时先停下，kickoff §7.4）；不改 FE3 kickoff 已定的业务规则。
>
> **节点与占用：** 按 AGENTS 的五节点池选合格空闲节点（kickoff §7.1，建议 07 模拟接口、05 真实 backend 与 t1），会话名 `fe4a-impl`。所有运行都原子取得占用标记，真实 backend 入口自行获取，外层不重复获取。`GATEWAY_FE_TEST_WORKERS=2`。t1 目录运行前按清单逐文件核对，只读挂载。
>
> **日志与回源（FE3 中出现过的两类错误，必须遵守）：**
> - 证据日志一律由脚本 wrapper 生成。wrapper 写日志前先检查参数个数、绝对路径、日志目录已存在、截图目录在 worktree 外，任一不满足即退出、不运行入口。FE3c 曾把 `LOG_DIR` 取成 `$2`，导致入口没有运行；
> - handoff 中的每个十六进制值都用脚本逐个回源（节点现场重算的 SHA256、取回的日志原文、git 对象），并报告长度不是 7–12、40、64 的值。FE3b 的证据 handoff 曾有 5 个 SHA 抄错。不手抄 SHA。
>
> **停止条件：** kickoff §8 FE4a。失败与重做按 AGENTS main 的 DC68（2026-11-08 修订）。
>
> **交付：** 调试运行（kickoff §7.2 FE4a 调试行）各至少一次通过后，提交代码候选与 handoff `docs/frontend-vnext/fe4a-handoff.md`，内容包括：
> - 快进后的 HEAD、`vnext/` 树、路径核对结果、`--print-input` 与运行时 OpenAPI 比对结果；
> - C1–C11、Q21、令牌、取证工具各项的改动位置与对应用例；新增或修改的用例清单；
> - J1、J2 逐次预检的异常集合；C7 之后真实旅程的耗时（只报告）；
> - t1：§8.3 逐条核对，M1 两次数值与 FE3a 的对照；打包代码是否改动（kickoff §7.4 的 `git diff --stat` 结果）；
> - 出现过的诊断码，以及 §3.5 文案表以外的编码；
> - 截图清单，标出 kickoff §7.3 中交 owner 看图的文件；
> - 每次运行的节点、hostname、起止 UTC、起止 HEAD、树、exit code、日志 SHA256；工具链、npm 缓存、依赖镜像与 RS 镜像的身份；
> - 十六进制回源的结果；
> - 已完成、未测（只由模拟接口覆盖的项及原因）与未决事项，分三节写。
>
> 不合入 main，不推送。审核通过后的取证由审核会话指明：在最终候选的 clean、已提交 detached worktree 上，模拟接口全量、上传包校验、`journeys`、`t1` 各运行一次。

### 11.2 FE4a 审核（前置：FE4a handoff 已提交）

> 你是 FE4a 审核会话，是新会话，不与 FE4a 实施会话为同一会话，也不沿用 FE3 审核会话的上下文。审核 `fe-fe3c-exit..[FE4a handoff 提交]`；来自 main 的文档与 `vnext/` 不在前端审核范围。先按 kickoff §5.2 做路径核对（`<main>` 为 `16ffe72829`，`vnext/` 树 `49c1de43be`）。依据：FE4 kickoff（main `[确认提交]`）§3–§8；FE3 kickoff §4.6、§6.4、§8、§16；带入项原文所在的审核报告；后端 Q21 答复。
>
> 重点：
> 1. **带入项：** C1–C11 逐项对照“处理”一列，确认用例有区分力：把修复回退后对应用例应失败。
> 2. **Q21：** 文案表与 kickoff §3.5 一致；删除的 4 个码不再出现在文案表与码表中；单测覆盖新增的 4 个码与匹配顺序。
> 3. **令牌：** 按 owner 对 Q7 的决定。
> 4. **取证工具：** wrapper 的参数检查与记录字段完整；回源脚本能发现抄错与长度异常。
> 5. **真实旅程与 t1：** J1、J2 在新 backend 树上的异常集合与 FE3 kickoff §4.6 一致；C7 之后的接受都经界面；t1 按 §8.3 由程序判定；M1 按 Q20、Q23 对照；核对打包代码是否改动。
> 6. **截图：** 与 FE3c 证据截图按文件名比较，逐字节不同的文件都在 kickoff §7.3 的范围内或由 C4 引起；C4 之后同一提交两次运行的截图逐字节相同（抽查）。
> 7. **探针（已提交的一次性 worktree，只在节点上）：**
>    - 恢复 C8 之前的单一提示变量：C8 的两条用例应失败；
>    - 恢复 C2 之前不经在途合并的重试：attempt 读取次数的断言应失败；
>    - 把 C11 的一处闸门改回固定延迟加不带参数的 `unrouteAll()`：在不少于 8 个 worker、`--repeat-each` 不少于 20 的单独运行中观察是否复现，结果如实记录，不强求复现；
>    - 让 wrapper 的日志目录参数取错位置：wrapper 应在运行入口前退出；
>    - 在一份 handoff 副本中改错一个 SHA 的一位：回源脚本应报告未命中。
> 8. **运行：** 独立运行一次 `run-tests.sh --e2e --screenshots` 与一次 `--suite journeys`（会话名 `fe4a-review`）；t1 不要求重跑，只核对日志与参考截图的 SHA256。
> 9. **回源：** 用脚本把 handoff 中的十六进制值逐个回源，报告长度不是 7–12、40、64 的值。
>
> 报告写入 `docs/frontend-vnext/reviews/fe4a-review.md`，结论为通过、定向修复或停止；需要设计决定的事项标注“交设计会话”。通过后指明证据项（kickoff §7.2 FE4a 证据行），取证后做证据核对，给出 FE4a 退出建议，并列出带入 FE4b 的项。

### 11.3 FE4b 实施与审核

在本文第 2 步（§5.3）中写定。框架与 FE4a 相同：新建实施与审核会话；先读 BE-b 的 Contract、交接与 golden；合入 BE-b 退出后的 main；刷新 OpenAPI 与 fixture；按 §3.1、§3.2 实施；t1 正式重拍交 owner 看图。

## 12. 交接材料

新会话从下列文档读取“已完成、未测、未决”，不依赖旧会话的上下文：

| 类别 | FE4a 读取 | FE4b 另读 |
| --- | --- | --- |
| 已完成 | FE3 kickoff §3.2 的 FE3a、FE3b、FE3c 退出记录；`fe3c-evidence-04.md`、`fe3b-evidence-04.md`；`fe3c-handoff.md` 及 fix1、fix2 | `fe4a-handoff.md` 与 FE4a 退出记录；BE-b 的退出交接 |
| 未测 | `fe3c-handoff.md` §5.5（只由模拟接口覆盖的项）；FE3 kickoff §4.6 末段（时间倒退等只由模拟接口覆盖）、§4.7（过期 `APPROVE` 409、提交 403、仍在运行与 `MANUAL_RECOVERY_REQUIRED` 只由模拟接口覆盖）；§8.4（t1 FULL 不可比较；t4 自 FE3a 后未重测） | `fe4a-handoff.md` 的“未测”一节 |
| 未决 | 本文 §3.4–§3.7、§10；FE3 kickoff §12 中仍开放的项 | 本文第 2 步；BE-b 第二步与交接中留给前端的事项 |

## 13. 同分支中对其他文档的修改

本分支另一个提交只改以下几节，不改其他内容：

- **前端 kickoff：**
  - §7 FE4 一行：写明拆段与范围见本文（待 owner 确认），退出条件改为按本文 §5.2；
  - §9：“侧栏导航层级是否精简”改为见本文 §3.2、Q6；“`diagnostics_summary` 中的自由文本”改为“已并入 BE-b（草案 §4.10，owner 2026-11-03），随 FE4b 接入”。
- **FE3 kickoff：**
  - §11 Q21：状态改为“后端已答复（`d3450675bf`），前端处理见 FE4 kickoff §3.5”；
  - §12：“比较诊断码的变化”“FE4 真实数据重拍的节点”“`--color-warning-soft`”三行改为指向本文 §3.5、§2.5、§3.6。

# 前端重构 kickoff

- **状态：** 已确认（owner，2026-11-02）；FE0 可以开始。
- **日期：** 2026-11-02。
- **修订：** 2026-11-04 按后端 [DC75](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc75-be-a工作区占用指针与本人撤回权限)（方向经 owner 确认，后端设计 main `f20f08bea9`）更新 §3.3、§4.3、§5 BE-a 与 §7 FE3；BE-a 尚未实施。
- **会话分工：** 本设计会话负责 kickoff、决定记录与设计问题答复；实施与审核各由独立会话负责（§10）。
- **范围：** 新建前端工程，对接 vnext 后端；`legacy/frontend/` 只作行为与问题来源。
- **依据：**
  [UI 优化方向](ui-optimization-direction.md)（视觉与交互的 authority，S1–S4 草图已确认）、
  [Frontend Surface Simplification](../backend-vnext/frontend-surface-simplification.md)（用户可见能力覆盖矩阵）、
  [Comparison Bundle](../backend-vnext/contracts/comparison-bundle.md)、
  [Comparison Surface](../backend-vnext/contracts/comparison-surface.md)、
  [Business Lifecycle and State](../backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md)、
  [P6 讨论稿 §9 D5 的 owner 决定](../backend-vnext/refactoring/formal/plans/p6-planning-discussion.md)（整包传输，2026-10-24）、
  AGENTS.md。

## 1. 目标与非目标

目标：

- 新前端直接消费 vnext HTTP API 与 Comparison Bundle，覆盖全部正式业务旅程：上传与 Preview、提交、审核/撤回、归档、历史比较。
- 落实 [UI 优化方向](ui-optimization-direction.md) 已确认的视觉与交互约定。
- 在 Phase 8 切换前就位，作为 shadow 与正式切换的用户入口。

非目标：

- 不为 legacy 前端或 legacy bundle 形状建设兼容层（AGENTS“项目前提”）。
- 不在本 kickoff 内设计正式 SSO：测试阶段使用模拟会话，正式凭据在投产前单独设计和测试（FD2）。
- 不改变后端业务语义。需要后端改动的项列在 §5，按后端流程单独立项。

## 2. owner 决定（2026-11-02）

以下决定均由 owner 于 2026-11-02 确认，本表是其权威记录。

| ID | 决定 | 要点 |
| --- | --- | --- |
| FD1 | 新建前端工程，legacy 只作参考 | legacy 中不属于客观业务要求的设计可以讨论改进；不在 legacy 代码上渐进改造 |
| FD2 | 测试期会话用模拟 control plane | 测试 control plane 写 backend 已支持的 session 文件（token → IdentityContext）；正式 SSO 投产前单独设计与测试。约束见 §4.3 |
| FD3 | 数据整包传输，浏览只依赖前端本地 | 重申 2026-10-24 的 owner 决定：bundle 一次下载、按摘要校验、写入本地；浏览期间不向后端按需取数，不新增按 artifact 读取的接口。允许的优化只在前端本地进行（§4.4） |
| FD4 | 审核“退回”= `REJECT`；删除 `RETURN_FOR_REVISION` | 业务不需要撤销已通过的审核。后端删除该动作、状态与事件，见 §5 BE-a |
| FD5 | 差异浏览侧栏采用方案 A | 整个侧栏一个滚动区，组标题吸顶；展开或收起只影响本组；当前节点自动滚到可见；配合侧栏搜索与“只看变化/风险”过滤。取代 legacy 中展开组平分高度、各自滚动的做法 |
| FD6 | 业务分组与列展示由后端决定 | 已确认是迁移遗漏（§3.3），由后端补回（§5 BE-b）；前端在补回前使用占位（§4.5） |
| FD7 | 前端测试规则 | 见 §6 |
| FD8 | BE-b 的排期 | 现在立项设计，P6 退出后实现，Phase 8 之前完成；不作为例外放进 P6。理由见 §5 |

## 3. 后端现状核对（2026-11-02，main `b7d6e45406`）

### 3.1 HTTP API

vnext 已交付全部业务旅程的路由（`vnext/backend/src/gateway_backend/http/routes/`），`/openapi.json` 可用，路由集合由 `test_http_openapi.py` 冻结。P6 中对 HTTP 与 bundle 可见的变化（上传超时 408 `UPLOAD_STREAM_TIMEOUT`、整表浏览、bundle 含全部表）已在 S1b 落地；S2a–S6 为性能工作，comparison/risk/surface/bundle golden 在 S1b 后冻结。Phase 7 可能为 operation 增加对用户可见的排队状态，属于增量字段。

| 业务 | legacy 前端调用 | vnext |
| --- | --- | --- |
| 会话 | `/api/session`、`/api/sso/consume` | 无会话接口；`Authorization: Bearer`，由 session 文件解析为 IdentityContext（一个会话对应一个 actor、网关设备与业务项目） |
| 工作区与组态树 | `/api/workspaces/current`、`/api/workspace-tree` | `POST /v1/workspaces`（CreateOrGet）；`GET /v1/history`（节点列表与 head）；树由两者组合 |
| 上传与 Preview | `/api/workspaces/{id}/uploads` | `POST .../upload-revisions` → `POST .../preview-operations`（202 + `operation_id`）→ `GET /v1/operations/{id}` 轮询 → `GET .../preview-results/{id}`、`.../bundle` |
| 提交 | `/api/submissions` | `POST .../submit-attempts`（含 `identity_confirmations`）、`GET .../submit-attempts/{id}`、`GET .../submissions/{id}` |
| 审核与撤回 | `/api/submissions/{id}/review-actions`（`START_REVIEW`/`APPROVE`/`REJECT`/`WITHDRAW`） | `POST /v1/submissions/{id}/review-events`（`APPROVE`/`REJECT`/`WITHDRAW`，BE-a 之后）、`GET .../review` |
| 归档 | `/api/baseline-batches/*` | `archive-candidates`、`archive-plan-preview`、`archive-confirmations`、`archive-anomaly-resolutions`、`archive-audit-events`、`archives` |
| 历史比较 | `/api/history-comparisons` | `POST /v1/history-compares`（2–3 节点）、`GET .../{operation_id}`、`.../bundle` |

客户端通则：除 CreateOrGetWorkspace 外，写操作都携带调用方生成的幂等 key 与预期版本号；同 key 不同内容返回冲突。错误码以 OpenAPI 与各 route 的 `responses` 为准。

### 3.2 Bundle

vnext bundle 是精简的表索引（`ComparisonSurface`）加 artifact 闭包：表状态与计数、records/risk/diagnostics 引用、Preview 上传侧全部表与删除表基线侧的 Parquet、History 每个节点的全部表（相同内容按内容地址共享）。legacy 的 `preview_index`、`sidebar_trees`、`alignment_report` 等形状不再存在。侧栏、筛选、徽章与只看风险等由前端从 surface 与 risk 推导（覆盖矩阵“前端派生”项）；风险只来自 `RiskReport` 与 annotation，不从记录推断。

### 3.3 缺口

| 缺口 | legacy 位置 | vnext 现状 | 处理 |
| --- | --- | --- | --- |
| 业务分组（转发通道、二次装置列表、通讯规约列表、全局参数、转发通道分组信息、未解析表）、组内节点、二次装置页签 | `legacy/backend_vnext/capabilities/business_projection/`、`flows/business_projection.py`（约 2,000 行；需读 `net_cfg`、`app_cfg` 等表的行数据、身份计数与风险汇总） | P5 收口时作为“无使用方的占位”删除（ADR 0018 第 7 项、P5 arch closure design §10）；当时前端尚未接入 | BE-b |
| 列展示（显示名、顺序、宽度、隐藏、固定、键列） | `legacy/backend_vnext/capabilities/table_presentation/`（约 2,600 行，多为按表名正则的列宽规则） | 代码未迁移；`contracts/table-presentation.md`、`capabilities/table-presentation.md`、`capabilities/business-projection.md` 仍为现行文档，与代码不一致 | BE-b |
| 复合信号公式查看 | legacy formulas artifact | vnext 有 `composite_signal_point` 派生表（含 `formula_ast_json`），bundle 是否完整携带待核对 | FE0 核对 |
| 历史初始备份节点（随归档提交上传的原始组态备份，可查看差异、加入比较） | `FormalWorkspaceTree.tsx`、`formalWorkspaceState.ts` | History 只有基线、提交与规则迁移节点；History 比较只接受基线节点与提交 | owner 2026-11-02（FE2 kickoff Q4 甲）：FE2 不实现；是否需要由 owner 另定，需要时作为后端任务单独立项 |
| 上传模式顶栏的“撤回”（草图 `header-upload`） | legacy 工作区顶栏 | `WorkspaceResponse` 只有 `current_upload_revision_id`、`current_preview_result_id`，没有指向当前提交的字段，工作台无法确定可撤回的提交；审核顶栏的撤回按 `submission_id` 进行，不受影响 | owner 2026-11-04（FE2 kickoff Q16 甲）：FE2 只在审核顶栏提供撤回；是否在 `WorkspaceResponse` 加入当前提交，由 BE-a 或后续后端任务决定，加入后由前端接回。后续（owner 2026-11-04 确认方向，[DC75](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc75-be-a工作区占用指针与本人撤回权限)）：占用指针与本人撤回权限并入 BE-a（§5），FE3 接回（§7.1）；BE-a 实施前此缺口仍然存在，FE2 继续按 Q16 甲 |
| 首批空基线时禁用上传第 ① 步（UI 优化方向 §7.2） | legacy 上传步骤卡 | History 没有“基线为空”的事实；`INITIAL` 基线的提交来自部署映射（`infrastructure/control_db/sqlite_mapping.py`），可以有内容，后端不拒绝在其上做 FULL 上传 | FE2 不禁用（FE2 kickoff §9 Q18，owner 2026-11-04）；后端在 History 中提供该事实后再接入 |

## 4. 工程与架构

### 4.1 位置与依赖

- 工程放在仓库根目录 `frontend/`。不放进 `vnext/`：backend 与 repository_service 的测试闭包和镜像身份以整个 `vnext/` 为 Docker context（`test_input_closure.py` 的 `docker:context:vnext`），前端提交若进入其中，会使后端包沿用与 carried 判定失效。
- 沿用 React、TypeScript、Vite、glide-data-grid（C7）、hyparquet；图标用 lucide 并本地打包（C7）。依赖精确钉版本，提交 `package-lock.json`，安装用 `npm ci`。
- `node_modules/`、构建产物加入 `.gitignore`。
- 正式部署形态（静态文件与 backend 同源反向代理）属于 Phase 8/9，本 kickoff 不定；开发与 e2e 使用 Vite dev/preview server 代理到 backend。

### 4.2 分层

| 层 | 内容 | 依赖 | 测试 |
| --- | --- | --- | --- |
| A 功能层（无 UI） | 认证 fetch 封装；由 OpenAPI 生成的类型与客户端；operation 轮询、幂等 key 与版本处理；bundle 下载、校验、本地存储与 Parquet 解析；视图模型推导（导航、筛选、变更定位、风险）；UI 命令层与 URL 状态（[UI 优化方向 §5.1](ui-optimization-direction.md#51-ui-命令层c3)） | OpenAPI 快照、`vnext/fixtures/golden/{bundle,surface,risk}` | 单元测试 |
| B 设计系统 | token（色、字号、间距、圆角、阴影）、四档按钮、应用内对话框、焦点样式、表格主题、风险与差异语义色（UI 优化方向 §3、§7.4） | 仅已确认草图 | 单元测试 + 组件预览 |
| C 页面 | 正式工作台、差异浏览、审核、归档、历史比较、数据集替换浏览与确认 | A + B | 浏览器 e2e |

A 与 B 可以并行；C 才对接真实后端。

OpenAPI 快照：在仓库中提交 `frontend/` 下的 `openapi.json` 快照并由它生成类型；快照与当前 backend 是否一致，在 FE3 的 e2e 中用运行中的 `/openapi.json` 比对。不在 `vnext/` 中新增导出脚本。

### 4.3 会话（FD2）

- 所有请求经同一个认证 fetch 封装。bundle 下载也用 fetch（流式写入本地），不用 `<a href>`，以便正式 SSO 采用 header 或 cookie 时只改一处。
- 测试 control plane 写入多个身份：提交人、审核人、归档确认人，以及缺少相应权限的身份，覆盖审核、归档与权限拒绝路径。
  BE-a 之后（DC75），FE3 另设只持 `withdraw_own_submission` 的提交人身份，与持 `review_submission` 的审核人分开；验证本人撤回时不用审核人或全权限身份代替。
- 一个会话对应一个网关设备与业务项目。legacy README 中的“设备选择/SSO 入口”不作为前端页面，切换设备即切换会话。
- token 不写入构建产物；开发与 e2e 通过 dev server 代理或仅开发环境出现的身份选择注入。

### 4.4 Bundle 本地化（FD3）

**传输格式（owner 2026-11-02；后端由 BE-d 实现）：**

- `GET .../preview-results/{id}/bundle` 与 `GET /v1/history-compares/{operation_id}/bundle` 返回一个流式、不压缩的 POSIX tar（`application/x-tar`，长路径用 pax 扩展头）。
- 成员顺序：bundle manifest、bundle closure，然后按 closure 条目顺序放每个产物，路径为条目的 `logical_path`（bundle 内相对路径）。按内容寻址共享的文件只出现一次。不加其他元数据成员。
- 不压缩：Parquet 自带压缩。
- 后端在发送响应头前确认 closure 中全部产物可读，缺失时返回稳定错误码，不发送残缺包；响应带 `Content-Length`（由各产物大小算出）与 `ETag`（bundle 摘要）。
- 发送过程中出错时中断连接；前端以 tar 截断或摘要不符判定失败，丢弃本地副本后重新下载。
- 整包一次请求、下载完成后才开始浏览；不提供按 artifact 读取的接口。

**前端处理：**

- 流式下载并写入 OPFS，按 `Content-Length` 显示进度，不在内存中攒整包；逐个成员按 closure 中的摘要校验。
- 先读索引并渲染导航；每张表在打开时才从本地解析 Parquet（本地懒加载，不访问后端）。
- 按 bundle 摘要缓存在本地，同一 Preview/History 再次打开不重新下载；淘汰策略按本地容量，读写失败时退回重新下载。
- 后端数据有 TTL，本地副本是浏览依据；浏览期间后端清理不影响已下载内容。

### 4.5 分组与列展示占位（FD6）

- 占位期间：全部表放在一个组，节点即表，无页签；列名用原始列名，宽度由前端按内容自动计算。该回退保留为正式行为：后端未给出某表的分组或展示设置时同样适用。
- BE-b 的数据结构见 [BE-b 设计草案](be-b-navigation-and-presentation-draft.md) §4（第一步已确认）；前端的占位 fixture 按它构造，补回后只替换数据来源。
- 前端按产物中的 `groups` 列表通用渲染分组，不写死分组槽位或分组名；未知 `group_key` 按通用分组显示（草案 §4.6）。

### 4.6 侧栏（FD5）

在 UI 优化方向 W3、W5 的基础上：单一滚动区、组标题吸顶、各组独立展开、当前节点自动可见、搜索与只看变化/风险过滤；记忆宽度与展开状态（X6）。导航层级（视图 → 分组 → 节点 → 页签）是否还能精简，待 BE-b 的分组设计定稿后讨论。

## 5. 依赖的后端任务

各项按后端流程（kickoff、focused 测试、审核、门禁）单独执行，不在前端工程中实施。

| ID | 内容 | 影响面 | 时机 |
| --- | --- | --- | --- |
| BE-a | 删除 `RETURN_FOR_REVISION`：domain 动作、`RETURNED_FOR_REVISION` 状态与事件、HTTP literal、history 状态 literal、control DB schema 约束（直接改基线，本地 DB 删除重建，DC6）、测试与 Contract（Business Lifecycle、P5-5C 设计中的状态机表）。当前约 18 个文件引用。另外（owner 2026-11-03，FE2 kickoff §9 Q13）：`POST /v1/history-compares` 第一次返回 202、回放 200，OpenAPI 只声明了 200，补齐 202 并把 200 标为幂等回放；`POST /v1/workspaces` 新建返回 201、已存在返回 200，OpenAPI 同样只声明了 200，一并补齐；同步 OpenAPI 测试；前端快照在 FE3 刷新。另外（owner 2026-11-04 确认方向，[DC75](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc75-be-a工作区占用指针与本人撤回权限)，[BE-a 设计补充](../backend-vnext/refactoring/formal/plans/p6-be-a-design.md)，后端设计 main `f20f08bea9`；后端 kickoff 审核通过 `fcbfb4c1a0`，待 owner 实施确认；以下尚未实现）：① `WorkspaceResponse` 增加 required nullable 的 `active_submit_attempt_id`、`active_submission_id`，投影当前提交占用，至多一个非空，新建（201）与已存在（200）两条路径都返回；指针只表示当前占用，不表示可撤回，通过后仍保留到归档开始；② 新增权限 `withdraw_own_submission`：可读本人提交的 review facts（`GET .../review`，含终态），可对本人 `PENDING` 提交执行合法的 `WITHDRAW`；不含通过、退回与项目 History；他人、跨 scope 与不存在统一 404，无任一审核权限 403；③ `review_submission` 保留审核人现有能力，两者同时持有取并集；④ 撤回的 `expected_review_version` 取 `GET .../review` 返回的 `review_version`，不使用 `Workspace.optimistic_version`（APPROVE 不改变工作区版本）；⑤ 撤回或退回后指针、当前上传与 Preview 清空，工作区可重新上传 | HTTP DTO、control DB schema、审核授权语义（新权限）；无镜像边界外的部署变化 | 不阻塞 FE0–FE2；S2a 合入 main 之后作为小任务进行，避免与 P6 分支冲突（owner 已确认） |
| BE-b | 补回业务分组与列展示：capability、bundle/surface 中的产物形态、Contract 与 golden；注释来源；Preview bundle 为 `composite_signal_point`、`device` 补齐基线侧整表（owner 2026-11-02）；行定位产物、视图 ID 修复与诊断稳定编码（owner 2026-11-03，FE2a 审核 D1–D3，BE-b 草案 §4.8–§4.10）。范围与数据结构见 [BE-b 设计草案](be-b-navigation-and-presentation-draft.md) | bundle 结构与摘要；Preview/History 计时路径增加计算 | FD8：现在立项设计并先给出数据结构草案；实现排在 P6 退出之后、Phase 8 之前。理由：P6 对照基准已在 S1b 后重建、bundle golden 已冻结，P6 中加入会改变 bundle 摘要并影响 W1–W4、H1–H3 的计时 |
| BE-c | 在 P6 测量中记录 t4 与 2× t4 的 bundle 体积（只报告） | 无 | 随 P6 测量；用于评估 1 Mbps（DC49）下的下载时长 |
| BE-d | 闭合 bundle 传输（owner 2026-11-02）：`/bundle` 现在只返回 manifest JSON（`LocalArtifactBundleReader` 按 manifest ID 读单个 artifact），closure 引用的产物不在响应中，与 FD3 冲突。改为 §4.4 的流式 tar；Comparison Bundle Contract 补“传输格式”一节并同步 OpenAPI；路由测试验证 tar 成员与 closure 一致；`benchmarks/real_dump_journey.py` 改为解析 tar 中的 manifest，并记录下载耗时与体积（只报告） | HTTP 响应格式与 OpenAPI；不涉及 Dockerfile 与镜像 | S2a 合入 main 之后、FE3 之前（与 BE-a 同类）；FE1、FE2 用本地按该格式拼装的 tar fixture 开发 |

## 6. 测试与证据（FD7）

AGENTS 的“专用测试节点”规则同样适用于前端：不在开发主机上运行测试。

- **调试（owner 2026-11-06 新增节点）：** 类型检查、lint、单元测试、构建、截图和 mock e2e 优先在 `ct109-gw-dms-07`（8 vCPU / 16 GiB / 200 GiB thin）运行。它们不涉及 Dolt 与 Compose，不需要本机 Dolt 占用标记。07 与 04 同物理宿主，Owner 已确认资源宽裕，日常开发自主并行，不为共享宿主向原基准线申请窗口或常规互斥。07 设置 `GATEWAY_FE_TEST_WORKERS=2` 限制浏览器并发。
- **浏览器 e2e：** 对接真实 backend 时需要起 Compose 栈（共享 8000 端口），按 DC70 补充的节点占用标记（`mkdir /home/dev/gdds-node-busy.d`，写入会话名、用途与开始时间）获取整机占用，在 05 调试；模拟接口的 e2e 不需要占用标记。
- **与计时测量的关系（owner 2026-11-02；2026-11-06 补充）：** Phase 6 正式计时只在 ct108 上独占进行，前端不使用 ct108。原 04、05、ct108 互不共享硬件；新 06/07 与 04 同宿主，不与 ct108 同宿主。共享宿主不自动要求互斥；实际出现资源干扰时协调。某节点占用标记写明用于计时测量时，前端在该节点上的任何运行仍等待释放。
- **证据：** 阶段退出时在 `ct108-gw-dms-04` 的 clean、已提交 worktree 上完整运行一次前端测试与 e2e；日志记录 hostname、起止时间与 HEAD、exit code。
- **工具链镜像（owner 2026-11-02）：** 测试节点没有 Node.js。前端测试统一在一个固定版本的工具链镜像中运行（例如 Playwright 官方镜像，内含 Node.js、浏览器与系统库），在 CT201 取得，经 `docker save`/`docker load` 传到实际使用的 07、05 与 04；跨节点身份比较 config digest 与全部 RootFS DiffID（同 DC67），不比较 `docker inspect` ID。不在测试节点宿主机上安装 Node.js。镜像版本变化时按同一流程重新取得与传输。
- **依赖与缓存（参照 DC67）：** 在 CT201 用 `package-lock.json` 取得 npm 依赖缓存，经获准的局域网预填充到实际使用的节点，挂载进工具链容器，在容器中 `npm ci --offline`；缓存缺失即停止，补齐后从头运行。handoff 记录来源提交、工具链镜像 tag 与身份、npm 缓存摘要与预填充时间。
- **入口：** FE0 提供 `frontend/scripts/run-tests.sh` 作为前端权威入口；是否并入 `vnext/scripts/run-tests.sh` 的包选择（例如新增 `frontend` 包名）在 FE0 评估。并入会修改 runner 与闭包脚本，影响后端闭包，倾向保持独立。
- **截图验收（owner 2026-11-02）：** FE2 起，由 Playwright 在 1280 与 1920 两种宽度下，对 UI 优化方向 §7 草图清单中的每个页面与状态截图（模拟接口，固定示例数据），截图与运行日志存于 worktree 外的证据目录并记录 SHA256。审核会话逐张对照草图核对布局、层级、语义色、按钮层级、禁用原因与焦点样式；不做像素级比对（示例数据不同）。与草图不符处要么修正，要么作为偏差列入 handoff 交 owner 确认。FE4 在 04 上用真实 backend 与 t1 数据重拍一次关键页面作为证据。
- 规则写入 AGENTS 与 testing-conventions，由治理会话在 FE0 首次运行测试前完成。

## 7. 阶段

前端位于 `vnext/` 之外，不影响后端闭包。主工作区由多个会话共用，因此实施会话在独立 worktree `/home/dev/gdds-fe` 的短期分支 `fe-vnext` 上开发（AGENTS 允许的并行短期分支）；每个阶段审核通过并经 owner 确认后，由设计会话打附注 tag（`fe-<阶段>-exit`）并合入 `main`。审核对象为 `<上一 tag>..<候选提交>`；FE0 的起点为分支创建时的 `main` 提交。

| 阶段 | 内容 | 依赖 | 退出条件 |
| --- | --- | --- | --- |
| FE0 骨架 | 工程初始化、工具链镜像与 npm 缓存预填充、测试入口与节点规则落地、OpenAPI 快照与类型生成、§3.3 复合信号核对、legacy 能力清单（§8）逐项确认 | kickoff 确认 | 05 上入口可运行；清单无“未判定”项 |
| FE1 A/B 并行 | A：认证封装、API 客户端、轮询与幂等、bundle 本地化与解析、视图模型推导、命令层；B：token、组件、表格主题、对话框 | FE0 | A 用 golden bundle 与模拟接口覆盖全部旅程的数据流；B 覆盖 UI 优化方向 P1、P2 条目 |
| FE2 页面 | 正式工作台（树、上下文工具栏、上传步骤卡、比较托盘、结果抽屉）、差异浏览（两行顶栏、侧栏 A、tab、表格、变更定位）、审核与撤回、归档、历史比较、数据集替换浏览与确认。分为 FE2a 差异浏览、FE2b 工作台、路由与历史比较、FE2c 写操作旅程，各自审核、取证与打 tag（[FE2 kickoff](fe2-kickoff.md) §2，owner 2026-11-02、2026-11-03） | FE1 | 用模拟接口完成全部旅程；UI 优化方向 P3、P4 条目落地；截图验收通过（§6） |
| FE3 对接 | 对接 Compose 中的真实 backend；刷新 OpenAPI 快照并做一致性比对；接回上传模式顶栏撤回（§7.1）；真实数据 t1 完整旅程；FE2 带入项（[FE2 kickoff](fe2-kickoff.md) §6.5，owner 2026-11-05） | FE2、BE-a、BE-d | e2e 全部旅程通过（含 §7.1 场景）；t1 旅程通过 |
| FE4 收口 | 接入 BE-b 的分组与列展示与行定位产物，移除占位数据与浏览器中的行标识计算（保留回退行为）；04 上取证 | BE-b | 04 证据；owner 退出审核 |

FE0–FE2 不依赖后端剩余工作；FE4 依赖 BE-b，按 FD8 排在 P6 退出之后。

### 7.1 FE3：接回上传模式顶栏撤回（[DC75](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc75-be-a工作区占用指针与本人撤回权限)）

依据后端设计 main `f20f08bea9` 的 [BE-a 设计补充](../backend-vnext/refactoring/formal/plans/p6-be-a-design.md) §2–§4。BE-a 尚未实施：FE3 开始前核对 BE-a 已合入 main，以合入后的 OpenAPI 为准；与本节不符时停下交设计会话，不按本节自行假设接口。FE2 不实现本节内容。

- **数据来源：** 工作区的 `active_submission_id` 非空时，调用 `GET /v1/submissions/{id}/review` 取 `status` 与 `review_version`。指针只表示当前占用，撤回是否可用以 review 查询结果和服务器响应为准；前端不按 actor 推断权限，也不把指针非空当作可撤回。
- **撤回请求：** `expected_review_version` 取上一步的 `review_version`；不使用 `Workspace.optimistic_version`。沿用审核顶栏撤回的幂等 key、二次确认（X4）与危险按钮样式。
- **必测场景：** 模拟接口与真实 backend e2e 都覆盖下列场景，本人撤回用 §4.3 的仅本人权限身份：
  - 无权限：只有上传权限的身份，review 查询返回 403，不提供撤回；
  - 已通过：`APPROVED` 时指针仍非空（保留到归档开始），不可撤回；
  - 冲突刷新：审核版本冲突时重新查询 review 与工作区后再判断，不自动重发写请求；
  - 撤回后重新上传：指针、当前上传与 Preview 为空，回到上传步骤，重新上传、Preview 与提交；
  - 回归：审核人在审核顶栏的撤回保持原行为。
- **刷新恢复：** `active_submit_attempt_id` 可辅助刷新后找回进行中的提交尝试（经已有的 attempt 查询取得 `operation_id`），不替代 FE2c 的 `operation_id` 写入 URL 方案。
- **文案与状态：** 无权限、已通过等禁用原因的文案在 FE3 kickoff 定稿。
- **提示词：** FE3 的实施与审核提示词由设计会话在 FE3 kickoff 时给出，引用后端设计 `f20f08bea9` 与 BE-a 实施的合入提交。

## 8. legacy 能力清单

FE0 逐项核对 vnext 来源并标注 KEEP / SIMPLIFY / REMOVE；“简化”须说明保留的业务事实。

| legacy 能力 | legacy 位置 | vnext 来源 | 初判 |
| --- | --- | --- | --- |
| 正式工作台组态树与节点详情 | `FormalWorkspaceTree.tsx`、`formalWorkspaceState.ts` | `/v1/workspaces`、`/v1/history` | KEEP，按 S1 重做 |
| 上传：目录选择、浏览器端打包、校验 | `workspaceUpload.ts`、`workbenchUploadPackage.ts` | `upload-revisions`；打包格式以 Source Package Contract 为准 | KEEP，打包规则待核对 |
| Preview 进度与任务锁定 | `StrictTaskModal.tsx` | `preview-operations`、`/v1/operations/{id}` | KEEP，按 T1/S2 重做 |
| 表列表、表级状态、行级差异 | `PreviewGridPanel.tsx`、`previewTableData.ts`、`grid/` | surface + records Parquet | KEEP |
| 整表新增/删除浏览与表级风险 | — | S1b `TABLE_BROWSE` | 新增 |
| ordered 表差异 | `orderedDiffV3.ts` | ordered records | KEEP，展示规则待核对 |
| 风险浏览与提示 | `formalRiskUiModel.ts`、`previewRiskSummary.ts` | `RiskReport`、annotation | KEEP，按 W7、S4 重做 |
| 业务分组、节点、页签 | `workbenchModel.ts`、`localWorkbenchBundle.ts` | 缺（BE-b） | 占位 |
| 列展示 | `grid/columns.ts` | 缺（BE-b） | 占位 |
| 复合信号表与公式查看 | `CompositeSignalGridPanel.tsx`、`CompositeFormulaViewer.tsx` | 各侧的 `composite_signal_point`（含 `formula_ast_json`）与 `device` 整表；Preview 的基线侧由 BE-b 补齐 | KEEP（owner 2026-11-02）：History 与 Preview 都提供改前、改后对照。BE-b 实现前，Preview 中公式有变化的测点只显示上传侧公式并标“公式已改”。数据来源与名称映射见 [BE-b 设计草案](be-b-navigation-and-presentation-draft.md) §4.4 |
| 数据集替换双侧浏览与确认 | `replacement-preview/`、`projectIdentityNotice.ts` | `DATASET_REPLACEMENT`、`identity_pairs`、`identity_confirmations` | KEEP |
| 提交 | `workspaceApi.ts` | `submit-attempts` | KEEP |
| 审核通过、退回、撤回 | `workspaceApi.ts` | `review-events`；审核浏览用 History 比较 bundle | KEEP；`START_REVIEW` 取消。审核人读不到提交人的 Preview（工作区范围含所有人，`assert_exact_scope`），审核模式加载 History 比较（基线节点 → 待审提交）的 bundle |
| 归档主线（预检、异常处理、确认） | `ArchiveMainlineReviewPanel.tsx`、`archiveMainlineReviewModel.ts` | `archive-*` | KEEP，按新接口重排，A1 去除原生确认 |
| 历史比较（2/3 节点、比较对切换） | `historyComparisonPolling.ts` | `history-compares` + bundle | KEEP，按 F5/F6 重做 |
| diagnostics 与 KEYLESS_FALLBACK 提示 | `localWorkbenchBundle.ts` | surface diagnostics | KEEP |
| 上传性能基准 Playwright 工具 | `tools/upload_benchmark_playwright_runner.mjs` | — | REMOVE；P6 测量使用后端工具 |

## 9. 开放项

| 项 | 需要的决定 | 阶段 |
| --- | --- | --- |
| FD7 规则写入 AGENTS 与 testing-conventions | 治理会话执行 | FE0 首次运行测试前 |
| UI 草图中的占位文案（节点状态、Diff Kind、Change Group） | 已关闭：按 vnext 实际枚举定稿，见 [FE2 kickoff §4](fe2-kickoff.md#4-界面文案定稿回填前端-kickoff-9-第-2-项)（owner 2026-11-02）；Change Group 列删除 | — |
| 侧栏导航层级是否精简 | BE-b 分组设计后讨论 | BE-b 设计 |
| 导航诊断的结构与编码（FE1 审核 D1） | 已答复：[BE-b 草案 §4.7](be-b-navigation-and-presentation-draft.md#47-导航诊断设计会话-2026-11-02答复-fe1-审核-d1)。诊断放在 `SurfaceProjectionRef.diagnostics_ref` 指向的独立产物中，不带 message，前端按 code 映射中文文案。FE2 按此修改 `model.ts` 的过渡处理并补测试；新增编码 `DEVICE_ROWS_UNASSIGNED` 已由 owner 确认（2026-11-02） | FE2 |
| surface `diagnostics_summary` 中的自由文本 | 少数条目是自由文本而不是编码（如风险引擎的 `max_annotations_per_pair exceeded`、比较失败的异常文本）。收敛为编码是后端清理项，不属于 BE-b，时机由 owner 安排；在此之前前端显示通用文案，原文放进 Debug | 后端，不阻塞 |
| 正式部署形态与正式 SSO | Phase 8/9 前单独设计 | — |
| P6 计时是否包含整包传输 | P6 的“用户可见时间”只计到结果可读，不含 bundle 打包与下载；是否把下载耗时作为只报告项，由 P6 设计会话或 owner 决定（与 BE-c 一并考虑） | P6 |

## 10. 会话分工

| 会话 | 职责 | 不做 |
| --- | --- | --- |
| 设计会话（本会话） | kickoff 与本文维护；FD 决定记录；答复实施中的设计问题；BE-b 设计 | 不写产品代码，不审核实施结果 |
| 实施会话 | 按 §7 各阶段实施，提交候选与 handoff；设计问题与停止条件交设计会话或 owner | 不自行改变 FD 决定与 UI 优化方向的已确认条目 |
| 审核会话 | 各阶段代码审核与证据复核，按 `<上一 tag>..<候选提交>` 审核 | 不与实施会话为同一会话 |

后端任务 BE-a、BE-b 的实施与审核按后端阶段流程另行指定会话。

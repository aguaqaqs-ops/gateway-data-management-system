# FE2 kickoff：页面

- **状态：** 已确认（owner，2026-11-02，§9 Q1–Q5 均按建议）；FE2a 可以开始。
  2026-11-03 按 FE2a 审核的设计问题修订 §4.2、§4.3、§5.1、§5.3、§5.5、§5.6（owner 确认，§9 Q6–Q9）。
  2026-11-03 FE2a 退出（§2），新增 §6.3 FE2a 带入项（§9 Q10、Q11）。
  2026-11-03 新增 §7.5 模拟接口响应规则；FE2b 拆分为 FE2b、FE2c（§2，§9 Q12）；更正 §4.1 工作区的来源。
- **FE2b：** 可以开始。起点为 `fe-fe2a-exit`（main 合入提交 `a7c6160447`），审核范围为 `fe-fe2a-exit..<候选>`。
- **日期：** 2026-11-02。
- **起点：** `fe-fe1-exit`（`a42139222f`），main 合入提交 `abbe6e8777`。
- **依据：** [前端 kickoff](frontend-kickoff.md)（FD1–FD8、§4、§6、§7）、
  [UI 优化方向](ui-optimization-direction.md)（S1–S4 草图与 P3、P4 条目）、
  [BE-b 设计草案](be-b-navigation-and-presentation-draft.md)（§4.2–§4.7）、
  [FE1 证据核对](reviews/fe1-evidence-check-1.md) §6、AGENTS“前端测试（FD7）”。
- **会话分工：** 与前端 kickoff §10 相同。本文由设计会话维护；实施会话按本文实施，遇到本文未覆盖的设计问题时停下交设计会话。

## 1. 目标

用模拟接口完成全部业务旅程的页面，落实 UI 优化方向 P3、P4 条目，并按截图通过验收（前端 kickoff §7 FE2 一行）。
真实 backend 对接、OpenAPI 运行时比对与 t1 真实数据属于 FE3，不在本阶段。

## 2. 阶段划分（owner 2026-11-02 确认，Q1）

FE2 的页面量约为 FE1 的三倍。FE1 一轮审核加两轮复审，范围只有功能层与设计系统。
因此拆成两个子阶段，各自走完整的审核、04 取证和 tag，审核范围保持可控：

| 子阶段 | 内容 | 带入项 | 草图 | 退出 tag |
| --- | --- | --- | --- | --- |
| FE2a 差异浏览 | 差异浏览工作台（三种模式共用）：两行顶栏、侧栏 A、tab、表格（S4 全部呈现规则）、变更定位与分布条、仅看差异折叠行、表级状态（新增/删除整表、结构变化、降级、比较失败）、ordered 与 blank 记录、数据集替换双侧浏览、复合信号公式查看、导航与 surface 诊断、Debug 模式、加载骨架与错误页（T2、T3）；URL 状态 | R4、N4、N6、行分隔色、导航诊断改为 `diagnostics_ref`、ViewKind 删除、视图按比较对区分（§5.6） | S3、S4 | `fe-fe2a-exit` |
| FE2b 工作台与写操作 | 正式工作台：组态树、上下文工具栏、详情面板、上传步骤卡与页面锁定、比较托盘、历史比较结果抽屉；上传与 Preview 进度（T1）、提交（含身份确认）、审核通过/退回/撤回、归档主线（A1、A2）；页面之间的路由 | N1、N2 | S1、S2，以及 S3 的三种顶栏 | `fe-fe2b-exit` |

顺序为先 FE2a 后 FE2b。理由：差异浏览是数据最复杂、草图最细的部分，FE1 带入的大多数事项也在这里；
FE2b 的写操作依赖 N1、N2，可以在 FE2a 审核期间准备。两个子阶段都在 `fe-vnext` 上进行，审核范围分别为
`fe-fe1-exit..<FE2a 候选>`、`fe-fe2a-exit..<FE2b 候选>`。

**FE2a 已退出（2026-11-03）：**

- 附注 tag `fe-fe2a-exit`（tag 对象 `e83f00409b`）指向 handoff 提交 `e301cc0f88`；
  被测代码为 `a80a2e93af`，两者 `frontend/` 树相同，都是 `f1c238248a`。
- 合入 main 的合并提交为 `a7c6160447`，只带入 `frontend/` 与 `docs/frontend-vnext/fe2a-handoff.md`。
- 依据：[审核](reviews/fe2a-review.md)、[复审第 1 轮](reviews/fe2a-rereview-1.md)、
  [复审第 2 轮](reviews/fe2a-rereview-2.md)（PASS）、[证据核对第 1 轮](reviews/fe2a-evidence-check-1.md)（PASS）。
- owner 决定（§9 Q10）：FE2a 不再修复。无草图页面的截图（公式抽屉、数据集替换双侧浏览、加载骨架、错误页、导航回退；
  04 证据目录 `/home/dev/gdds-fe-evidence/fe2a/a80a2e93af-04/`）按现状接受；R7 与正常业务场景的截图带入 FE2b（§6.3）。
- FE2b 以 `fe-fe2a-exit` 为起点。

**FE2b 拆分（owner 2026-11-03 确认，§9 Q12）：**
原 FE2b 包括 §6.1 全部页面与写操作，加 §6.3 的带入项，体量大于 FE2a；FE2a 一轮审核加两轮复审才通过。
因此拆成两段，各自走完整的审核、04 取证与 tag。上方表中“FE2b 工作台与写操作”一行由下表取代：

| 子阶段 | 内容 | 截图 | 退出 tag | 审核范围 |
| --- | --- | --- | --- | --- |
| FE2b 工作台、路由与历史比较 | §6.3 全部带入项（N1、N2、R2、R5、R7、S1、S2）；模拟会话与身份选择、模拟接口层（§6.2 第 3 条、§7.5）；正式工作台（组态树、详情面板、上下文工具栏，F1、F2、F4、F7–F9）；比较托盘与历史比较结果抽屉（`history-compares` 发起、轮询、打开 History 差异浏览）；页面路由，取代 FE2a 的 URL 脚手架：三种模式的入口都在本段，Preview 打开工作区当前的 Preview 结果，审核模式从待审提交发起“基线节点 → 该提交”的 History 比较并读取 `GET /v1/submissions/{submission_id}/review`（只读，前端 kickoff §8 审核一行） | 草图 S1；草图 S2 的比较托盘部分；S3 的 Preview、History 两种顶栏；§6.3 S1 正常业务截图；无草图页面中的“仍在运行”与侧栏回退 | `fe-fe2b-exit` | `fe-fe2a-exit..<FE2b 候选>` |
| FE2c 写操作旅程 | 上传步骤卡、浏览器端打包与校验、页面锁定与进度（S2、F3、T1）；Preview 发起；提交（含身份确认）；审核通过、退回、撤回（审核模式顶栏中的操作）；归档主线（A1、A2）；全部写操作的权限拒绝与版本冲突（§6.2）；需要管理员处理 | 草图 S2 的上传步骤卡部分；S3 的审核顶栏；无草图页面中的数据集替换确认、归档对话框各步骤、退回与撤回对话框、需要管理员处理 | `fe-fe2c-exit` | `fe-fe2b-exit..<FE2c 候选>` |

- **切分依据：** 第一段只有一个异步写操作（历史比较），不改变业务状态，用它先把 N1、N2、模拟会话与模拟接口层做实；
  第二段的写操作都复用这些基础，审核集中在业务规则与错误路径。
- **工具栏：** FE2b 中上下文工具栏按 F2、F4 显示全部操作及其启用条件与禁用原因（纯视图模型，有单测）；
  写操作的点击流程在 FE2c 接入。FE2b 审核不把未接入的点击算作缺陷，e2e 也不点击这些按钮。
- **截图确认：** 草图 S1 的工作台在 FE2b 交 owner 确认；FE2c 只重拍工具栏的写操作状态有变化的截图。
- **§6、§7 中的“FE2b”：** 指原 FE2b 的范围，按上表分属 FE2b、FE2c；§6.3 带入项都在 FE2b 完成，§7.5 对两段都适用。

## 3. FE1 带入项

| ID | 内容 | 子阶段 | 完成标准 |
| --- | --- | --- | --- |
| N1 | 幂等 key 按用户意图复用：用户确认一次操作时生成 key，同一意图的重试（含网络中断后的重试按钮）复用该 key；旅程函数按步骤接收 key，不在 client 内部生成 | FE2b | 单测：重试复用同一 key，新的意图用新 key；e2e：模拟第一次请求超时、重试，模拟接口按 key 回放第一次结果 |
| N2 | 轮询：超时只表示“仍在运行”，不判为失败；界面显示已等待时长，可继续等待或离开页面（后端操作继续）。临时错误（网络错误、5xx、429）按有上限的退避重试，超过上限后显示“连接中断”并提供重试，不判定操作失败。`operation_id` 写入 URL，刷新后继续轮询 | FE2b | 单测覆盖超时、临时错误重试与上限、终态（含 `SUPERSEDED`、`MANUAL_RECOVERY_REQUIRED`）；e2e 覆盖“仍在运行”与刷新后继续 |
| N4 | 已缓存的表不在每次读取时重算整个文件的摘要：写入时校验一次；之后在每个浏览会话中首次读取某表时校验一次，结果在会话内记住；读取或解析失败时清除该 bundle 缓存并重新下载 | FE2a | 单测：同一会话第二次打开同一表不再计算摘要；摘要不符时触发重新下载 |
| N6 | 应用代码的 tsconfig 不含 Node 类型；测试与脚本用单独的 tsconfig | FE2a | 应用代码中使用 `Buffer` 时 typecheck 失败（可用一次性探针验证，结果写进 handoff） |
| R4 | 本地搜索跳过二进制值（`ArrayBuffer`/`ArrayBufferView`），只匹配展示文本，不匹配值结构中的 `kind` 等结构字段 | FE2a | 单测：搜索“12”不命中只在行标识字节中含 12 的行；搜索“string”不命中全部记录 |
| — | token 补行分隔色 `#EEF1F4`（S4） | FE2a | 截图验收 |
| D1 | 导航诊断按 BE-b §4.7：从 `SurfaceProjectionRef.diagnostics_ref` 读取单独产物，去掉 `business-navigation.json` 中的内联 `diagnostics` 与 `model.ts` 的 `diagnosticText`；按 code 映射中文文案 | FE2a | 单测：v1 全部 code 都有文案，文案占位符与 params 一致；未知 code 显示“导航提示（{code}）”；`diagnostics_ref` 为 null 时没有诊断 |

## 4. 界面文案定稿（回填前端 kickoff §9 第 2 项）

前端 kickoff §9 要求 FE2 之前按 vnext 实际枚举确定草图中的占位文案。本节由 owner 于 2026-11-02 确认（Q2、Q3），是 FE2 的权威文案；
UI 优化方向 §7 草图中对应的占位文案以本节为准，草图不重画。原始枚举值一律放进悬停提示或 Debug（C6）。

### 4.1 组态树节点

节点类型用图标与形状表示（F7），状态用圆点加文字。类型和状态来自 `GET /v1/history` 的节点字段与 `head`，以及 `POST /v1/workspaces`（CreateOrGet，
请求参数为会话对应的 `business_project_id` 与 `gateway_device_external_key`，前端 kickoff §4.3）返回的工作区。vnext 没有列出工作区的接口。

| 来源 | 类型文字 | 状态文字 |
| --- | --- | --- |
| 工作区（`WorkspaceResponse`） | 工作区 | 没有上传：“未上传”；有上传但没有 Preview 结果：“已上传”；有 Preview 结果：“可提交”；有进行中的操作：进度指示（F7）。`WorkspaceResponse` 不含进行中的操作，进度指示只针对本会话发起、`operation_id` 记录在 URL 中的操作（N2） |
| `BASELINE_NODE` + `INITIAL` | 初始基线 | 是 `head` 时加“当前基线” |
| `BASELINE_NODE` + `ARCHIVED_SUBMISSION` | 归档基线 | 是 `head` 时加“当前基线” |
| `SUBMISSION` | 提交 | `review_status`：`PENDING` 待审核、`APPROVED` 已通过、`REJECTED` 已退回、`WITHDRAWN` 已撤回。有 `archive_disposition` 时以它为准：`ARCHIVED_BASELINE` 已归档、`CLOSED_NOT_ARCHIVED` 未归档关闭 |
| `SYSTEM_MIGRATION` | 规则迁移 | 无 |

附加标记（不占状态位，放在节点行尾的小标签与悬停提示中）：

- `eligibility_note = NOT_CANDIDATE_BASE_ADVANCED`：“基线已更新”，悬停提示“该提交所基于的基线已不是当前基线，不能归档”；
- `identity_exception = true`：“项目身份例外”。

`RETURNED_FOR_REVISION` 在 BE-a 之前仍可能出现在快照类型中，按 FE1 的处理映射为“已退回”，不出现单独入口。

### 4.2 差异浏览：视图与比较对

视图按 bundle 的比较对 ID（`pair_id`）区分，不按 surface 的 `view_id`，也不写死枚举（§5.6，Q8）：

| 比较对 | 文字 |
| --- | --- |
| Preview `baseline_to_initial` | 原始组态视图（已归档数据 → 原始组态备份） |
| Preview `initial_to_modified` | 本次组态视图（原始组态备份 → 本次归档组态）；只上传本次归档组态时为“当前基线 → 本次归档组态” |
| History 比较对 | 按比较对在 bundle 中的顺序显示“节点 1 → 节点 2”，序号与比较托盘一致；三节点时为两个相邻比较对（F6）。不依赖 `pair_id` 的具体取值 |

后端现状（FE2a 审核 D3）：生产 Preview 给两个比较对都传 `view_id=initial_to_modified`，History 的比较对 ID 为 `<operation_id>-p<i>`，
都与 Comparison Surface Contract（同一 bundle 内 `view_id` 唯一；History 用 `left_to_right` 等）不符。这是后端缺陷，随 BE-b 修复（BE-b 草案 §4.9）；
前端按上表处理，修复前后都能正确显示。

括号里的说明放在分段控件的悬停提示中，控件上只显示前半部分。

### 4.3 表级状态（导航徽章与当前表信息行）

| `SurfaceChangeKind` | 文字 | 导航徽章 |
| --- | --- | --- |
| `UNCHANGED` | 未变化 | 无 |
| `BUSINESS_EQUIVALENT` | 业务等价 | 无；悬停提示说明“内容写法不同，业务含义相同” |
| `ADDED` | 新增表 | 新增 |
| `DELETED` | 删除表 | 删除（条目文字加删除线） |
| `UPDATED` | 有修改 | 更新 |
| `SCHEMA_CHANGED` | 结构变化 | 更新；信息行说明新增或删除的列 |
| `DEGRADED` | 降级比较 | 更新；信息行显示降级原因（来自诊断，按 §5.5 文案表的顺序取第一条；没有可识别的原因时显示“降级原因未提供”） |
| `FAILED` | 比较失败 | 失败（中性图标加文字）；表格区域显示错误说明，不显示数据 |
| `REPLACED` | 数据集替换 | 替换；进入双侧浏览 |

有风险时导航徽章只显示风险等级（W3，S3 取舍），完整的状态加风险等级在信息行与悬停提示中显示。

### 4.4 行级记录（S4 的 Diff Kind、Row Role、Change Group）

User 模式下以符号、连线和文字表示（S4），不显示原始编码：

| 记录类型 | 文字 | 呈现 |
| --- | --- | --- |
| `ROW_ADDED`、`ORDERED_ROW_ADDED` | 新增 | `+` |
| `ROW_DELETED`、`ORDERED_ROW_DELETED` | 删除 | `−`，删除线 |
| `ROW_MODIFIED`、`ORDERED_ROW_MODIFIED` | 修改 | 成对两行加连线（W9） |
| `ORDERED_ROW_MOVED` | 移动 | 移动图标，悬停提示“第 a 行 → 第 b 行”（取 `before_position`、`current_position`） |
| `BLANK_DELETE_INTERVAL`、`BLANK_INSERT_INTERVAL` | 删除空行区间、插入空行区间 | 一行摘要“第 a–b 行：删除（插入）n 个空行” |
| `SCHEMA_CHANGE`、`TABLE_DEGRADED`、`ORDERED_TABLE_DEGRADED` | — | 表级，不进入行，在信息行显示 |

Debug 模式的元数据列：

- **Diff Kind：** 显示原始 `record_kind`；
- **Row Role：** 改为“前/后”，只对修改记录的成对两行显示，由前端从记录推导；
- **Change Group：** vnext 没有对应事实，删除该列；ordered 记录改为显示 `semantic_kind` 与前后位置。

### 4.5 风险等级与操作状态

- **风险等级：** `HIGH` 高、`MEDIUM_HIGH` 中高、`MEDIUM_LOW` 中低、`LOW` 低、`UNKNOWN` 未知（与 FE1 token 一致）。
- **操作状态**（`OperationStatus`）：
  - `QUEUED` 排队中、`RUNNING` 执行中、`SUCCEEDED` 已完成、`FAILED` 失败、`CANCELLED` 已取消；
  - `SUPERSEDED` 显示“已被新的操作取代”；
  - `MANUAL_RECOVERY_REQUIRED` 显示“需要管理员处理”，同时显示操作 ID（可复制），不提供重试。

## 5. FE2a：差异浏览

### 5.1 范围

- 一个工作台承载三种模式（W10）：上传（Preview bundle）、审核（History bundle，基线节点 → 待审提交，沿用 FE1 的 B2 修复）、历史比较（History bundle，2–3 节点）。
  模式由入口决定，差异浏览页不提供模式页签（草图中没有，Q9）：FE2a 由 URL 参数进入（测试脚手架），FE2b 由工作台进入。
  FE2a 只做浏览：顶栏模式操作区留出位置，写操作按钮由 FE2b 接入；S3 三种顶栏的截图在 FE2b 验收；FE2a 的 S3 整页截图中模式操作区为空，属于已知差异，不算偏差。
- 两行顶栏（W2、S3）、侧栏方案 A（FD5、W3、W5）、tab 与溢出（W6）、变更定位与分布条（W4）、表格呈现（S4、W9）、仅看差异（W2）、可读化（W7）、复制（W8）、焦点样式（X5）。
- 数据集替换（`REPLACED`、`REPLACEMENT_SIDE_BY_SIDE`）：左右两侧各自浏览整表，显示 `identity_pairs` 的结论，不拼成普通差异。确认操作属于 FE2b。
- 复合信号公式查看：见 §5.4。
- 加载骨架（T2）与错误页（T3）：bundle 下载与校验的进度、失败与重试。

### 5.2 侧栏（FD5）

- 整个侧栏一个滚动区；组标题吸顶；展开、收起只影响本组；当前节点自动滚到可见。
- 搜索匹配组名、节点名与页签名；“只看变化/风险”过滤与搜索可叠加。
- 宽度与各组展开状态按 X6 记在本地（`localStorage`，读写失败时用默认值）。
- 折叠后保留窄栏，含展开、搜索与当前位置三个入口（W5）。
- 分组来自业务导航产物（BE-b §4.2）；没有该产物时按前端 kickoff §4.5 回退为单一组。两种情形都要有截图。

### 5.3 表格

- 继续使用 glide-data-grid。风险整行底色与左侧 4px 色条、修改行连线、改动单元格加深底色、旧值弱化等按 S4 与 7.4 的取舍实现。
- 修改行的两行因排序、筛选或搜索不再相邻时，不画连线，退回显示符号（S4 取舍）。
- 仅看差异：只显示有变化或有风险的行，连续的未变更行折叠为一行“… n 行未变更”，可展开，`#` 列保留原始行号。
- 风险只来自 `RiskReport` 与 annotation（前端 kickoff §3.2）；未变更但有风险的行在仅看差异下也显示。
- 列名与宽度：BE-b 之前用原始列名，宽度按内容计算（前端 kickoff §4.5）。
- **行定位（Q6，FE2a 审核 D1；2026-11-03 按审核澄清补充）：** 普通表的行级记录与风险标注只带后端算出的行标识摘要，快照 Parquet 中没有对应字段；
  摘要的算法与快照值的规范化都是后端内部实现，没有 Contract。BE-b 在 bundle 中提供行定位产物（BE-b 草案 §4.8），FE4 接入。在此之前：
  - **快照所在侧：** 只有 bundle 中有快照的一侧参与定位。Preview 中有变化的表只闭合上传侧（BE-b §4.4），改前侧没有快照；History 两侧都有。
  - **自校验：** 前端可以在浏览器中为快照行计算行标识，但结果必须自校验，且只约束有快照的一侧：
    - 新增记录在改后侧、删除记录在改前侧、修改记录在每个有快照的一侧，各自恰好匹配一行；
    - 没有对应记录的 `ROW` 标注（落在未变更行上，v1 不产出），在改后侧恰好匹配一行；改后侧没有快照时在改前侧匹配；
    - 同一侧的一行最多对应一条记录；同一侧不得有两行算出相同的标识。
  - **退回：** 任一条件不满足时，整张表不显示行级样式，退回表级风险与状态，信息行提示“本表的变更行无法定位，已显示表级结果”
    （Comparison Surface Contract：缺少行标识或位置时展示表级风险，不得伪造行级样式）。浏览器算错只会导致对不上并退回，不会标错行，
    因此这段计算不写进 Contract，也不要求跨实现向量；暂不支持的类型（如 SET、BIT）直接退回。
  - **风险标注：** 有对应记录的标注按后端写入的行标识与记录逐字节对应，不按 `target_type` 区分记录类型：v1 对新增、删除、修改记录的标注都是 `ROW`，
    带 `row_identity`；`ROW_PAIR` 是 Contract 预留的形状，出现时按 `before_row_identity`、`current_row_identity` 同样逐字节对应。前端不为这些标注重算。
  - **没有快照一侧的行**（Preview 的删除行与修改行的“前”行）由记录中的值组成：
    - 删除行：取记录的 `before_values`（参与比较的全部列）；
    - 修改行的“前”行：比较键列取“后”行的值（键相同），改动列取 `before_values`；
    - 其他单元格留空，悬停提示“改前值不在本 bundle 中”。不用“后”行的值填充：surface 不发布哪些列被比较规则忽略，填充可能显示错误的旧值。
  - **行的位置与 `#` 列：** 表格按改后侧的行序排列，删除行统一放在表末（与现状一致）：
    - 有改前侧快照时，删除行按改前侧行序排列，`#` 显示改前侧行号；
    - 没有改前侧快照时，删除行按记录顺序排列，`#` 留空，悬停提示“改前行号不在本 bundle 中”；修改行的“前”行 `#` 同样留空。
  - 有序表的记录带序号列的值（`before_position`、`current_position`），按序号定位，不受本项影响。
  - **测试：** 一个唯一的 owner 用例，断言五个后端 fixture 中每条行级记录在每个有快照的一侧恰好定位一行，Preview 的删除行与“前”行按上一条组成；
    另有一个用例，改动一条记录的行标识后该表退回表级；没有记录的 `ROW` 标注由 §7.1 的渲染测试覆盖（匹配成功一例、匹配失败退回一例）。
  - FE4 改用行定位产物，删除浏览器中的计算。

### 5.4 复合信号公式查看

- 对 `composite_signal_point` 表，公式列的单元格提供“查看公式”入口，在右侧抽屉中显示由 `formula_ast_json` 渲染的公式；装置名称按 BE-b §4.4 从同侧 `device` 表映射。
- History 与审核模式：两侧公式并列，改动部分标出。
- Preview：BE-b 实现前只有上传侧，公式有变化的测点标“公式已改”，抽屉中只显示上传侧，并说明“改前公式在 BE-b 实现后提供”（前端 kickoff §8）。
- 本项没有草图，按 §7.3 的“无草图页面”处理。

### 5.5 诊断

- **导航诊断：** 按 BE-b §4.7 显示在目标节点上（组、节点、页签或表），提示样式，不使用风险色。
- **表诊断（Q7）：** 当前表的 `SurfaceTable.diagnostics.diagnostics_summary` 只显示在该表的信息行，不显示在其他表上。
- **比较对诊断（Q7）：** 视图的 `diagnostics_summary` 是各表诊断的合并（去掉了表名），另加比较对自己的诊断。前端只显示其中不属于任何表的条目
  （视图汇总减去本视图全部表诊断的并集），放在顶栏下方的提示条中，有内容时才出现；视图页签的悬停提示写“n 张表有比较提示”。
- **文案原则：** 诊断文案只说原因；后果由 §4.3 的表状态文字表达（例如“降级比较”）。原始编码只在 Debug 中显示。
- **匹配顺序：** 先按完整编码匹配；再按冒号前的部分匹配（如 `DUPLICATE_EFFECTIVE_KEY:<表名>`）；形如 Python 异常类名（以 `Error`、`Exception` 结尾）的归入“内部错误”；
  仍无文案的显示“比较过程有提示”。
- **文案表：** 下表是 v1 可能写入 surface 诊断的全部编码，整理自 main `d1fad3e4a6` 的 `capabilities/comparison/`（`standard.py`、`row_encoding.py`、`ordered.py`、`replacement.py`）、
  `capabilities/risk_evaluation/_engine.py` 与 `capabilities/surface_assembly/_assembly.py`。行的顺序即 `DEGRADED` 信息行取原因的优先级。
  风险引擎的英文短句与异常类名以后改为稳定编码（BE-b 草案 §4.10），届时同步本表。

| 组 | 编码 | 文案 |
| --- | --- | --- |
| 键 | `DEGRADE_NO_COMPARE_KEY` | 本表没有可用的比较键 |
| 键 | `EFFECTIVE_KEY_CHANGED` | 两侧的比较键不同 |
| 键 | `DUPLICATE_EFFECTIVE_KEY`（前缀） | 比较键有重复值 |
| 键 | `EFFECTIVE_KEY_IGNORED` | 比较键中有列被比较规则忽略 |
| 键 | `SOURCE_PRIMARY_KEY_CHANGED` | 两侧的源表主键定义不同 |
| 有序表 | `ORDERED_REQUIRED_COLUMN_MISSING` | 有序表缺少排序或行标识所需的列 |
| 有序表 | `ROW_IDENTITY_MISSING` | 有序表缺少行标识列 |
| 有序表 | `ROW_IDENTITY_DUPLICATE` | 有序表的行标识有重复值 |
| 有序表 | `ORDER_KEY_UNSUPPORTED`、`ROW_IDENTITY_UNSUPPORTED` | 有序表的排序键或行标识配置暂不支持 |
| 有序表 | `ORDER_KEY_MISSING`、`ORDER_KEY_INVALID`、`ORDER_KEY_DUPLICATE`、`ORDERED_INTEGER_INVALID` | 有序表的序号缺失、无效或重复 |
| 有序表 | `SOURCE_GID_INVALID`、`SOURCE_RESERVED_PSEUDO_GID`、`CANONICAL_GID_INVALID`、`BLANK_PROVENANCE_MISSING`、`BLANK_PROVENANCE_INVALID`、`CANONICAL_BLANK_PROVENANCE_INVALID` | 有序表的 gid 或空行标记无效 |
| 有序表 | `ORDERED_DIFF_UNSUPPORTED` | 该有序表无法生成可靠差异，建议打开整表核对 |
| 列与结构 | `BEFORE_ONLY_COLUMNS` | 部分列只在改前侧存在，未参与行比较 |
| 列与结构 | `CURRENT_ONLY_COLUMNS` | 部分列只在改后侧存在，未参与行比较 |
| 列与结构 | `INCOMPATIBLE_SELECTED_COLUMNS` | 部分共有列两侧类型不兼容 |
| 列与结构 | `NO_SELECTED_COLUMNS` | 两侧没有可比较的共有列 |
| 列与结构 | `BUSINESS_SCHEMA_CHANGED` | 表结构有业务变化 |
| 列与结构 | `KEYLESS_FALLBACK` | 没有可用主键，已按整行内容比较（只识别新增与删除） |
| 数据 | `SET_VALUE_INVALID`、`SCALAR_VALUE_INVALID`、`SCALAR_TYPE_MISMATCH`、`SCALAR_TYPE_UNKNOWN`、`CANONICAL_COLUMN_COLLISION`、`ROW_SHAPE_MISMATCH` | 本表数据无法按列类型解析 |
| 内部 | `TABLE_READER_UNAVAILABLE`、`TABLE_DESCRIPTOR_MISSING`、`TABLE_TASK_INVALID`、`TABLE_TASK_HAS_NO_SIDE`、`TABLE_POLICY_MISSING`、`ORDERED_POLICY_MISSING`、异常类名 | 比较时发生内部错误 |
| 风险 | `risk table budget exceeded`、`risk diagnostics truncated`、`annotation artifact budget exceeded` | 风险标注不完整（超出上限），请打开整表核对 |
| 比较对 | `PROJECT_IDENTITY_UNVERIFIABLE` | 项目身份无法验证，提交前需要人工确认 |
| 比较对 | `DATASET_REPLACEMENT` | 识别为不同数据集，已切换为双侧浏览 |
| 比较对 | `max_annotations_per_pair exceeded` | 风险标注数量超出上限，部分行没有标注 |
| 比较对 | `max_risk_tables_per_pair exceeded`、`max_risk_pair_wall_time_seconds exceeded` | 风险评估超出上限，未完成 |
| 比较对 | `COMPARISON_MODE_NOT_DETAILED`、`COMPARISON_RULESET_DIGEST_MISSING` | 比较未能完成（内部错误） |

- **测试：** 以本表为后端可能产出的编码集合：每个编码都有非通用文案；五个后端 fixture 中出现的全部诊断都得到非通用文案；
  `device` 等无诊断的表不显示比较对诊断；匹配顺序各有一个用例。导航诊断与表诊断两份文案表放在同一模块。

### 5.6 视图 ID 与 URL 状态

- FE1 的 `ViewKind`（`INITIAL_TO_MODIFIED`、`BASELINE_TO_SUBMISSION`、`BEFORE_TO_CURRENT`）不是后端的视图 ID，已删除。视图按 bundle 的 `pair_id` 区分（§4.2、Q8）；URL 记录 `pair_id`，不在当前 bundle 内时回到 bundle 的默认视图。
  后端 `view_id` 目前不唯一（D3），前端不用它区分视图；fixture 跟随生产作业的实际取值，包括两个 Preview 比较对相同的 `view_id`，并有一个用例覆盖这种形状。
- 命令层（UI 优化方向 §5.1）执行后的浏览状态写入 URL：bundle 摘要、视图、节点、页签、变更序号、仅看差异、Debug、搜索。刷新或分享链接后回到同一画面（本地已有 bundle 时不重新下载）。
- “agent 操作中”指示与外部驱动通道仍不实现（§5.1 第 5 项）。

## 6. FE2b：工作台与写操作

### 6.1 范围

- 正式工作台（S1）：只呈现 vnext 已有的节点类型（§4.1）；F2、F5 中“历史初始备份”的操作不实现（Q4）。组态树为主区域（四列、搜索、列排序与调宽，F8），详情面板 400px 可折叠，视口 ≤1440px 默认折叠（F1）；上下文工具栏按节点类型显示操作（F2）；禁用操作都给出原因（F4）；状态字段用简短标签，长原因折叠（F9）。
- 上传步骤卡（S2、F3）：目录选择、浏览器端打包（Source Package Contract：必需 `/sql/dbcfg.sql`，可选 `/comps/logic/logics.xml`）、逐步校验与错误列表（X2）；上传与 Preview 期间页面遮罩锁定，进度时间线在步骤卡中（T1）。
- 比较托盘（S2、F5）与历史比较结果抽屉（S1、F6）。
- 提交：`submit-attempts`；identity 结论需要确认时（`DIFFERENT_PROJECT`、`UNVERIFIABLE`、数据集替换），先在对话框中逐项确认，再携带 `identity_confirmations` 提交。
- 审核：通过（主按钮）、退回（危险按钮，必填理由，X3）、撤回（危险按钮，二次确认，X4）。审核前先下载 History bundle，在审核模式的差异浏览中执行（W1、S3 审核顶栏）。
- 归档主线：`archive-candidates` → `archive-plan-preview` → 异常处理（`archive-anomaly-resolutions`）→ 确认（`archive-confirmations`）→ `archives`。最终确认在对话框内完成，展示“确认后的影响”摘要（A1），不使用 `window.confirm`。
- 页面路由：工作台 ↔ 差异浏览（含返回工作台），URL 可直接打开任一页面与节点。

### 6.2 权限与错误

- 前端在调用前不知道当前身份的权限（vnext 没有会话查询接口），因此按钮按业务状态启用；后端返回权限拒绝时就地显示“当前身份没有该操作的权限”，并显示错误码（T3、C6）。
- 版本冲突（预期版本不符）时提示“数据已被更新”，并提供刷新；不自动重放写操作。
- 模拟会话：开发与 e2e 通过开发环境的身份选择注入 token（前端 kickoff §4.3），覆盖提交人、审核人、归档确认人与无权限身份。生产构建中不出现身份选择，也不出现模拟接口代码（§7.2 检查）。

### 6.3 FE2a 带入项（owner 2026-11-03）

| ID | 内容 | 完成标准 | 来源 |
| --- | --- | --- | --- |
| N1、N2 | FE1 留下的幂等 key 复用、轮询超时与临时错误（§3），在接入按钮和进度界面之前完成 | §3 中的完成标准 | FE1、§3 |
| R2 | `ComparisonPage` 的 token 目前固定为 `null`，改为模拟会话的 token；URL 中的 `request`、`previewRequest`、`reviewRequest`、`historyRequest` 是 FE2a 的测试脚手架，由 FE2b 的页面路由替换；`check-production-build.mjs` 的禁止模式与 FE2b 实际的模拟接口、身份选择模块名对应 | 单测或 e2e：请求携带所选身份的 token；URL 不再接受上述参数；对生产构建做一次探针（把模拟接口模块引入应用入口），检查失败，结果写进 handoff | [审核](reviews/fe2a-review.md) R2 |
| R5 | 顶栏连接状态目前固定显示“已连接”，错误页上也一样。改为按最近一次接口请求的结果显示：请求成功显示“已连接”，临时错误超过重试上限时显示“连接中断”（与 N2 一致）；还没有请求时不显示。bundle 下载失败不改变连接状态，错误页只显示错误本身 | 单测覆盖三种状态；错误页截图上不出现“已连接” | [复审第 1 轮](reviews/fe2a-rereview-1.md) R5 |
| R7 | 公式抽屉中，单子节点的一元运算符（如 `-`）显示成了分组“｜（- 分组）”。按 Composite Signal Device §Frontend，一元运算符直接作为前缀；只对两个及以上子节点、运算符与上层不同的表达式分组 | 恢复第 1 轮的前缀断言；`formula-preview`、`formula-history` 重拍 | [复审第 2 轮](reviews/fe2a-rereview-2.md) R7 |
| S1 | 正常业务场景的截图。现有 fixture 每张表只有 1–4 行，S3、S4 的主截图都是从导航诊断“查看整表”进入的整表视图，侧栏都带诊断提示，没有覆盖接近草图的正常浏览 | 见下文 | 审核会话与 owner，2026-11-03 |
| S2 | 行级高风险与低风险的展示：v1 风险规则不在行上产出高风险，也不产出低风险，按 §7.1 的真实 bundle 截图中不会出现 | 按甲（§9 Q11）：不另拍截图，不加演示入口；`s4-semantic-tokens` 截图在 FE2b 全套截图中照常重拍 | 同上 |

**S1 的做法：**

- 生成器用后端生产代码补一个接近 S3 草图的 Preview 场景：一个转发通道的遥测表，几十到上百行，修改、新增、删除分散在表中；
  导航正常，没有导航诊断与表诊断。这一条落实 §7.1“表名、列名与数据尽量接近草图示例”。
- 从这个场景以普通页签浏览重拍 S3 工作台，以及 S4 的主表、悬停、Debug。
- 现有的异常与边界截图保留，单独成组，文件名不变。
- 该场景同样进入跨实现摘要测试；风险等级只含 v1 在该输入下产出的等级（§7.1 风险覆盖）。

**S2 的取舍（owner 2026-11-03 选甲）：**

- **甲（已选）：** 维持 §7.1 的做法，五个等级只在设计系统页的语义色截图（`s4-semantic-tokens`）上验收。
  这张截图已经按行的形态展示五个等级（整行底色、左侧色条、变更文字与改动格的加深色），能看出各等级在表格行中的效果；
  渲染映射由 §7.1 的渲染测试覆盖。
  理由：v1 不会在行上产出高或低，v1 用户看不到这两种行；为此做一张演示截图，需要在开发构建中加一个只供截图用的渲染入口
  （bundle 带摘要校验，不能在 e2e 中改写风险产物），验收的却是用户看不到的画面。
- **乙（未选，记录备查）：** 增加一张演示截图 `demo-s4-row-risk-levels`：数据取自渲染测试中改过等级的标注对象，不进入 bundle，页面上显示“演示数据”标记。
  需要一个只在开发构建中存在的渲染入口，并纳入生产构建检查的禁止模式。

**截图确认：** 带入项 S1 的截图在 FE2b 截图验收时，与草图 S1、草图 S2 的比较托盘部分、草图 S3 的 Preview 与 History 顶栏一起交 owner 看图确认（§7.3）；
草图 S2 的上传步骤卡部分与 S3 的审核顶栏在 FE2c 确认（§2）。
本节的 S1、S2 是带入项编号，与草图编号无关。

## 7. 测试、fixture 与证据

### 7.1 fixture

沿用 FE1 B1 的原则：bundle fixture 一律由 `frontend/scripts/generate-backend-bundle-fixture.py` 调用后端生产代码产出，可逐字节复现；不手写 bundle。
FE2a 开始时扩展生成器，产出以下 bundle（每个都进入跨实现摘要测试）：

| fixture | 来源 | 覆盖 |
| --- | --- | --- |
| Preview FULL | `run_preview_pair_pipeline`，两个视图 | 三类行记录；新增表、删除表、结构变化；keyless 回退；ordered 表（含移动）与 blank 区间；v1 风险规则可产出的全部等级（见下文“风险覆盖”）；`composite_signal_point` 公式变化 |
| Preview MODIFIED_ONLY | 同上，一个视图 | 只有本次归档组态时的视图文字 |
| Preview 数据集替换 | 同上，替换模式 | `REPLACED`、双侧浏览、`identity_pairs` |
| History 三节点 | `run_history_pair_pipeline` 加 `MULTI_PAIR` 组装 | 两个比较对；审核模式（两节点）复用其中一对 |

- 业务导航产物与导航诊断产物仍由前端按 BE-b §4.2、§4.7 构造（后端尚无该能力），通过生成器注入 `SurfaceProjectionRef`，并进入 closure 与摘要。BE-b 实现后换成后端产出（FE4）。
- 表名、列名与数据尽量接近草图中的示例（如 `device`、转发通道表），便于截图对照。
- 某类 fixture 用后端生产代码无法在不启动 Dolt/Compose 的前提下产出时，停下交设计会话，不改用手写。

**风险覆盖（设计会话 2026-11-02，答复 FE2a 实施停止）：** 生产入口固定使用 `V1_RISK_RULE_SPECS`。
v1 不产出 `LOW`；行级风险只落在有变化的行上（新增、删除为中低，修改为中高）；
表级与比较对级可产出高（项目身份不符、比较失败）、中高、中低、未知。
未变更行上的风险、行级的高与未知、`LOW`，是 Contract 允许、v1 规则不产出的情形。

- **bundle fixture：** 覆盖 v1 在该输入下能产出的等级，不为凑齐等级而注入或改写风险产物。
  各 fixture 实际产出的等级列表写进 handoff。
- **其余情形：** 由渲染层的单元或组件测试覆盖，前端仍须完整支持 Contract 中的五个等级与任意目标行。
  测试输入取自后端 fixture 解析出的标注对象：复制后只改等级或目标行标识，不手写对象结构。
  这些对象只用于测试渲染映射，不写入 bundle，也不进入摘要测试。
- **截图：**
  - 五个等级的颜色由设计系统页的语义色截图验收，对应 S4 `semantic-tokens`；
  - S4 `grid-main` 的截图只含 v1 产出的等级，与草图相比缺少的等级属于已知差异，不算偏差。
- **同类情形：** §7.1 中其他情形如果同样属于 v1 生产代码不会产出的，按同一原则处理，在 handoff 中列明，不需要停下。
  若能产出、只是必须启动 Dolt/Compose，仍按上一条停下。

### 7.2 测试

- 单测：§3 各项的完成标准；§4 文案表的完整性（每个已知枚举都有文案）；视图模型新增的推导（折叠行、连线配对、变更分布、侧栏过滤）。
- e2e（模拟接口，Playwright 路由拦截提供 API 响应与 bundle tar）：
  - FE2a：三种模式的浏览、侧栏与搜索、仅看差异、变更定位、公式查看、数据集替换浏览、下载截断后重新下载、刷新后按 URL 恢复；
  - FE2b：全部写操作旅程，含权限拒绝、版本冲突、轮询超时与刷新后继续、幂等重试。
- 生产构建检查：构建产物中不含模拟接口模块与身份选择（例如对 `dist/` 做字符串检查），由 runner 执行。
- runner 仍是 `frontend/scripts/run-tests.sh`；新增截图输出参数，截图写到 worktree 外的证据目录。

### 7.3 截图验收（前端 kickoff §6）

- 每张草图对应的页面与状态在 1280 与 1920 两种宽度下各截一张，使用 §7.1 的固定 fixture；文件名与草图对应，例如 `s3-workbench-upload-1920.png`。
- **无草图页面：** 公式查看、数据集替换浏览与确认、归档对话框各步骤、退回与撤回对话框、加载骨架、错误页、“仍在运行”、需要管理员处理、侧栏无导航产物时的回退。审核会话按 UI 优化方向的原则（token、语义色、按钮层级、禁用原因、焦点）核对；handoff 单列清单，交 owner 看图确认。
- 审核会话逐张对照，不做像素比对；与草图不符处修正，或作为偏差写入 handoff 交 owner 确认（AGENTS FD7）。
- 截图与运行日志放在证据目录，记录 SHA256；04 取证时重拍一次全套。

### 7.4 节点与证据

与 FE1 相同：调试在 05，阶段退出在 04 的 clean detached worktree 上完整运行一次权威入口（含 e2e 与截图）；
工具链镜像与 npm 缓存沿用现有预填充，依赖不变时不重新传输。依赖若有变化（例如新增 Playwright 以外的测试依赖），按 DC67 在 CT201 取得并预填充，handoff 记录来源与摘要。

### 7.5 模拟接口响应（FE2b 起，设计会话 2026-11-03）

FE2b 的 e2e 与组件测试依赖模拟的工作区、History、操作状态、上传、Preview、提交、审核、归档等 HTTP 响应。
FE1 审核 B4 与 FE2a 审核 B1 的问题都是前端自造了后端不会产出的取值，本节规定这些响应怎样构造。
bundle 仍按 §7.1 由生成器产出，本节只管 JSON 响应。

- **一处定义：** 模拟响应集中在一个只供测试与开发构建使用的模块中，e2e 的路由拦截和组件测试都从这里取；
  按场景组织（例如“提交需要身份确认”），每个场景列出依次返回的响应。生产构建检查（§7.2、§6.3 R2）禁止该模块。
- **编译期约束：** 每个成功响应体用 `frontend/src/features/api/generated/openapi.d.ts` 中该 route、方法与状态码对应的类型约束
  （`satisfies`，对象字面量多出的字段编译失败）；状态码只能是 OpenAPI 为该 route 列出的状态码。请求体同样按生成类型检查。
  生成类型来自 `frontend/openapi.json`，该快照在 `a2fb4a027a` 之后后端 HTTP 层没有改动；与运行中 backend 的比对属于 FE3。
- **错误响应体：** OpenAPI 中错误状态只有描述，没有响应体 schema。前端用一个类型对应后端 `ErrorResponse`
  （`vnext/backend/src/gateway_backend/http/schemas/errors.py`：`code`、`message`、可选 `details`，不允许其他字段）。
  `code` 只能取 `frontend/openapi.json` 中该 route、该状态码的描述里列出的值（如 `submit-attempts` 的 409 列出 9 个）。
  由一个单测解析 `openapi.json` 的描述，逐个核对全部模拟错误的（route、状态码、code），不用手工清单。
  权限拒绝是 403 `SCOPE_FORBIDDEN`；版本冲突按 route 分别为 `WORKSPACE_VERSION_CONFLICT`、`BASELINE_VERSION_CONFLICT`、
  `REVIEW_VERSION_CONFLICT`、`ARCHIVE_AUDIT_VERSION_CONFLICT`。
- **OpenAPI 中只是字符串的字段：** 以下字段在 OpenAPI 中是 `string`，取值以后端源码为准。前端维护一张取值表，每项注明源码位置，
  模拟响应与界面文案映射都从这张表取；单测核对模拟响应中这些字段的值都在表内：

  | 字段 | 取值 | 后端来源 |
  | --- | --- | --- |
  | `OperationResponse.status` | `QUEUED`、`RUNNING`、`SUCCEEDED`、`FAILED`、`CANCELLED`、`SUPERSEDED`、`MANUAL_RECOVERY_REQUIRED` | `operations/contracts.py` `OperationStatus` |
  | `OperationResponse.job_kind` | `backend-vnext/preview`、`backend-vnext/submit`、`backend-vnext/history-compare` | `application/preview_jobs.py`、`application/submission/job_payload.py`、`application/history/contracts.py` |
  | `WorkspaceResponse.state` | `OPEN`、`CLOSED` | `domain/workspace/models.py` `WorkspaceState` |
  | `UploadRevisionResponse.input_completeness` | `FULL`、`MODIFIED_ONLY` | 同上 `InputCompleteness` |

  OpenAPI 中有枚举的字段（如 `review_status`、`SubmitAttemptResponse.state`、`HistoryCompareResultResponse.status`）由生成类型约束，
  不进这张表。其他只是字符串、界面又要按值区分的字段，先在源码中找到枚举并加入这张表；找不到就停下交设计会话。
- **不用的值：** `RETURN_FOR_REVISION` 动作与 `RETURNED_FOR_REVISION` 状态由 BE-a 删除（前端 kickoff §5），模拟响应不使用，界面不提供入口（§4.2 的映射保留）。
- **状态序列：** 轮询与多步场景中依次返回的状态，按后端的状态转移取：操作状态见 `operations/state.py`，审核见
  `domain/submission/review.py` 的 `_ALLOWED_TRANSITIONS`，提交尝试为 `PREPARED → EFFECT_PENDING → FINALIZED` 或 `ABORTED`。
  每个场景注明所依据的转移。轮询终态的覆盖：`GET /v1/operations/{operation_id}` 覆盖 `SUCCEEDED`、`FAILED`、`CANCELLED`、
  `SUPERSEDED`、`MANUAL_RECOVERY_REQUIRED`；`GET /v1/history-compares/{operation_id}` 的 `status` 只有五个值，没有后两个。
- **幂等回放（N1）：** 同一 key 的重试返回第一次的响应体。状态码按后端 route：`review-events`、`archive-anomaly-resolutions`、
  `archive-confirmations`、`archives` 第一次 201、回放 200；上传始终 201；Preview 与提交始终 202；`POST /v1/history-compares` 第一次 202、回放 200
  （`http/routes/history.py`）。最后一项与 OpenAPI 不符：快照只声明了 200，模拟按后端行为返回 202，响应体用 200 的类型约束，
  客户端两者都接受；OpenAPI 的声明由 BE-a 补齐（§9 Q13）。同一 key、不同请求内容返回 409 `IDEMPOTENCY_CONFLICT`。
- **标识前后一致：** 场景内各响应引用的 ID 相互一致（例如工作区的 `current_preview_result_id` 等于 Preview 结果的 ID，
  该结果的 bundle 是 §7.1 的某个 fixture）。ID 是不透明字符串，前端不解析其格式。
- **注明来源：** 每个场景注明 route、方法、状态码、schema 名，以及上述取值所依据的源码位置；handoff 列出全部场景。
- **覆盖：** 每个写操作至少覆盖成功、403 权限拒绝、对应的版本冲突与幂等冲突；N1 的超时后重试回放、N2 的“仍在运行”、
  临时错误重试与上限、刷新后继续，以及上述轮询终态。

**为什么不由后端产出响应样例：** bundle 必须由后端生成，因为它的内部产物不在 OpenAPI 中；JSON 响应的形状 OpenAPI 已经完整描述，
可以在编译期约束。剩下的风险是只是字符串的字段、错误码与状态序列，由上面的取值表、错误码单测与源码注明覆盖。
由后端路由测试产出样例，需要为上传、Preview、提交、归档准备 Repository Service 与 Dolt，或者大量替身，替身数据仍是手造的；
后端的真实行为由 FE3 的真实 backend e2e 验证。因此 FE2b 不由后端产出响应样例。

## 8. 不在 FE2 范围

- 真实 backend 对接、OpenAPI 运行时比对、t1 真实数据（FE3）；BE-a 刷新快照后去掉 `RETURNED_FOR_REVISION` 的映射（FE3）。
- BE-b 的分组与列展示正式数据、Preview 改前公式、行定位产物（FE4）。
- 外部驱动通道与 agent 操作指示（UI 优化方向 §5.1 第 5 项）。
- 深色主题（C5）。

## 9. owner 决定（2026-11-02、2026-11-03）

Q1–Q5（2026-11-02）与 Q6–Q9（2026-11-03）均按建议确认；Q10、Q11 为 owner 2026-11-03 的 FE2a 退出决定；Q12、Q13 于 2026-11-03 按建议确认。

| # | 事项 | 决定 |
| --- | --- | --- |
| Q1 | 是否拆分为 FE2a、FE2b（§2） | 拆分，先 FE2a（§2） |
| Q2 | §4 的界面文案是否作为权威文案；UI 优化方向 §7 中的占位文案以此为准，不重画草图 | 同意；前端 kickoff §9 第 2 项关闭 |
| Q3 | Debug 模式删除 Change Group 列，ordered 记录改显示 `semantic_kind` 与位置（§4.4） | 同意；vnext 没有对应事实 |
| Q4 | **“历史初始备份”节点：** legacy 的组态树在归档基线下有“历史初始备份”节点（随归档提交上传的原始组态备份），可以查看差异、加入比较（F2、F5）。vnext 的 History 只有基线、提交与规则迁移三类节点，History 比较的输入也只接受基线节点与提交，没有对应的节点与比较入口 | 甲（见下） |
| Q5 | 无草图页面按 §7.3 由审核会话按原则核对、owner 看截图确认，不先补草图 | 同意 |
| Q6 | 行定位（FE2a 审核 D1，2026-11-03） | 长期由后端提供行定位产物，并入 BE-b（草案 §4.8），FE4 接入；之前用 §5.3 的自校验浏览器匹配，对不上整表退回表级。不把行摘要算法写进 Contract |
| Q7 | 诊断的显示位置与文案（FE2a 审核 D2，2026-11-03） | 按 §5.5：表诊断只在该表，比较对诊断放顶栏下方提示条；文案只说原因；文案表按 §5.5 |
| Q8 | 视图 ID（FE2a 审核 D3，2026-11-03） | 后端缺陷，随 BE-b 修复（草案 §4.9）；前端按 `pair_id` 区分视图（§4.2、§5.6） |
| Q9 | 差异浏览页的模式页签（FE2a 审核 B8，2026-11-03） | 删除；模式由入口决定（§5.1），R1 随之消失 |
| Q10 | FE2a 退出（证据核对第 1 轮 §6，2026-11-03） | FE2a 不再修复；无草图页面的截图按现状接受；R7 与正常业务场景截图带入 FE2b（§2、§6.3） |
| Q11 | 行级高风险与低风险的截图（§6.3 S2） | 甲：五个等级只在设计系统页的语义色截图上验收，不做演示截图 |
| Q12 | FE2b 是否拆分（§2） | 拆成 FE2b（工作台、路由与历史比较）、FE2c（写操作旅程），tag 与审核范围见 §2 |
| Q13 | `POST /v1/history-compares` 的 OpenAPI 只声明 200，后端第一次返回 202（§7.5） | 并入 BE-a（同为 S2a 合入后、FE3 之前的 HTTP DTO 小改动）：补齐 202，并把 200 标为幂等回放 |

**Q4 说明：** 这是 vnext 后端的能力差异，前端无法单独补齐。owner 选择甲；乙作为备选记录在此。

- **甲（已选）：** FE2 只呈现 vnext 已有的节点，F2、F5 中“历史初始备份”的操作暂不实现，在前端 kickoff §3.3 登记为缺口。是否需要在 History 中保留原始组态备份，由 owner 另行决定；若需要，作为后端任务（类似 BE-b）单独立项。
  理由：原始组态备份在 Preview 中已经通过“原始组态视图”浏览，归档后再次查看的需求是否存在，需要业务确认。
- **乙：** 先把该能力定为后端任务，FE2b 留出节点类型与操作入口，后端补齐后接入。

## 10. 实施会话的停止条件

除 AGENTS 与前端 kickoff 已有的规则外：

- fixture 无法由后端生产代码产出（§7.1）；
- 草图与后端事实冲突，且本文没有给出取舍；
- 需要后端新增字段或接口（FD3：不新增按 artifact 读取的接口）；
- 截图与草图有不能修正的偏差，需要 owner 判断。

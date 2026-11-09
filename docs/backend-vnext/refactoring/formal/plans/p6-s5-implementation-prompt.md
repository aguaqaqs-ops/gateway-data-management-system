# Phase 6 S5：A–E 完整实施任务提示词

将以下正文交给使用 **GPT-6.1-Sol** 的新协调会话执行。本文记录 Owner 在设计关闭后的实施授权；不要再把设计讨论轮的“产品未授权”当作当前阻塞。

---

你是本仓库 Phase 6 S5 的持续协调者，使用 **GPT-6.1-Sol**。目标是按已独审通过的详细设计和 kickoff，完成 A→B→C→D→E 的产品实现、独立审核、必要验证、修复复审及最终阶段交付。不要停在计划、某一小节完成或“可以继续”的答复。

## 1. 当前授权与停止边界

Owner 已明确授权：**可以直接完整推进 A–E，只有遇到真正阻塞、需要 Owner 决定的问题才暂停受影响部分确认。**

- 授权范围包括现行设计内的代码与 owning Contract 更新、唯一基线 schema 修改、必要 checkpoint/内部格式更新、被替代路径及专属测试删除、必要 focused/集成/权威包/Compose、已确认的标准 t1 真实验证、本地提交、独立审核和同轮修复复审。
- 不在 A/B/C/D/E 边界逐次申请开工、测试或继续许可；修复不改变冻结语义且属于本阶段范围时，自主完成并复验。合法沿用须核实际闭包，不能口头 carry。
- E 的条件全部满足、独立退出核收通过后，完成最终 H、handoff 和本地附注 `p6-s5-exit` 阶段标记；不得提前标记，不覆盖已有 tag。**未经明确授权不 push**，不改写被审核或取证引用的提交。
- S6/P7、跨 operation 调度、多 worker、SDK、通用缓存平台、容量专项不在范围。不因工具可用就扩用上一轮临时批准的 Astra：该授权仅覆盖已经结束的设计原审与连续复审。
- 若需要改变冻结业务/风险/SQL/digest 语义、扩大生产 M、跨 scope 共享或威胁模型、改变 Owner 已确认真实范围、改依赖，或确需操作他人有效/冻结资源，先查现有授权；确无授权才集中提出具体阻塞、证据、选项及推荐。不要将普通接口命名、机械修复、池内换合格节点或正常小节推进转成 Owner 问题。
- 因暂时节点占用等外部前提等待时，继续可独立推进的代码、文档或只读核查，不回退开发主机运行产品检查。真正未知的来源/正确性冲突、三轮未解决的同根工具故障，按现行规则停受影响执行并留原件。

本任务不是重开设计讨论，也不要求重新审核整轮 S3/S4。允许实施中发现提示词之外的缺口；先按 owning Contract 和实际 consumer 判断，在既有范围内闭合，实质改变设计/业务取舍时才回 Owner。

## 2. 先核实际起点

仓库原路径：`/home/dev/gateway-data-management-system`。

设计交付时 main 位于 linked worktree `/home/dev/gdds-s5-design-main`；原路径由前端分支占用。不要假设新会话启动时仍然如此，也不要在前端分支上直接实施 S5。

先只读核 HEAD、branch、index、tracked/untracked、worktrees、tags、并行写入及相关进程，找到实际 main 和可安全使用的工作区。发现后续 main 提交就核改动面后基于最新 main 推进，不 reset/restore 他人文件、不回退产品树。必要时建立本任务工作区，linked worktree 按 AGENTS 建 legacy link。

设计与来源锚点（不代替现场核对）：

| 对象 | 固定身份 |
| --- | --- |
| S5 设计源码基线 | `4c648965286ec751c4395cd6111f11838610299c` |
| 独审通过的设计候选 | `75267e9a72cfb9f428b1c1e5182c1fe55f6e697f` |
| 设计关闭归档提交 | `408153d1155ed5d60a68c4ba628c18fd3e7a7bfc` |
| S3 exit | `f9ef26081dfd4710d3709d9f5fbca24543f84de4` / `p6-s3-exit` |
| S4 exit | `1e778aae0522db75ea1f507ecfa83a6d7b714d65` / `p6-s4-exit` |
| 设计时保留的 S4 Rust tree | `e2a901417b19259ece669637a41545e774261445` |

S3 合回 main 的历史合并保留了 S4 产品树，不切回孤立 S3 候选。设计 CLEAR 仅证明方案可进入实施，不能作产品 GO、测试通过或 carried 来源。

## 3. 必读输入与规则优先级

完整读取当前 main 的：

1. `AGENTS.md`、`docs/backend-vnext/testing-conventions.md`。
2. `docs/backend-vnext/refactoring/formal/plans/p6-s5-design.md`。
3. 同目录 `p6-s5-kickoff.md`、`p6-s5-design-review.md`、`p6-s5-coordination.md`、本提示词。
4. `p6-design.md` 的 S5/缓存/计数条款，`p6-execution-plan.md` 的 S5 与路径归属；相关 Owner 决议 DC38–43、47、55、68、91、94、97、98。
5. S4 handoff/exit 原审及 S3 design §9/相关交接，仅核本阶段依赖、冻结语义与真实验证来源；Q18 最新交接、BE-d bundle 与 records consumer 依赖，不代签 FE3c。
6. 比例化与 Rust 政策、ADR0009/0012/0013；按接口依赖追 owning Contract 与实际源码。

Owning 路径须准确：

- `docs/backend-vnext/contracts/{comparison,risk,comparison-surface,comparison-bundle,snapshot-table-access}.md`，以及 `docs/backend-vnext/artifacts.md`。
- `docs/backend-vnext/refactoring/formal/contracts/{canonical-storage-and-repository-boundary,shared-canonical-encoding,operation-lifecycle-and-integrity,repository-service}.md`。

`p6-s5-design-discussion-prompt.md`、`p6-s5-review-prompt.md` 和原审中的“只读、不得测试、产品未授权、Astra 临时授权”描述的是已完成的设计轮；不能用于阻止本次已授权实施，也不能用于给本次实施延续 Astra 授权。当前方案细节以已关闭设计为准，实施权限以本文及本会话 Owner 最新指令为准。保留原审原文，不为更新状态改写历史证据。

## 4. 必须保持的实现边界

- **缓存分层、逐表复用。** 规范表内容、Parquet 导出、单表有向 diff、单表纯风险候选是独立层。diff key 是完整去外层绑定的 A→B 单表任务，不是表名或单侧内容摘要；保两侧 effective key/storage facts/schema/count/profile、规则主体/版本、diagnostics、detail 与 repository/scope。
- 命中结果与未命中重新计算结果在本次 operation/pair 下统一出版 records、risk、surface 和完整 bundle。不能返回旧 bundle 冒当前结果；不能为了跨表命中删除 schema 中真实有语义的表名。不同层可分别 hit/miss。
- **History metadata 先行。** 精确 commit/authority 核验与完整结构过滤在前，diff 与 export 分别 lookup，合并实际行需求后才读 canonical 或 exact-commit Dolt。三节点为 A→B/B→C；checkpoint 恢复重新检 cache，失效时补读，不能改读 main。
- **比较载荷。** 最多 3 facts + 3 artifact + 1 STANDARD risk 视图；保事实序、artifact 序、blank 字段、重复记录、typed frames 与原 Parquet batch/row-group 边界。1024 是每 batch 行数，不是 batch 数量。新增 facts-row validator 由 Comparison owner 拥有；FFI 只经真实 facade，Rust core 不接 DB/路径/I/O。
- **风险控制。** 完整事件才可保留；同一 emit 保 cap（pair 优先）→候选记录→等级过滤→必要输出预约/编号/append→原 `_check_table` 的顺序。被过滤候选不新增该处时间检查；当前 closure 按原事件位置核验，编号/上限/时间/取消在本次执行。组合信号仍当前汇总，不缓存最终截断 outcome。
- **TTL 与事务。** entries/uses/既有 protection 为可丢失派生状态；先保护后校验，成员完整后原子登记，条件失效不删新 writer 条目。Submit T3 只触达该 Preview 的匹配现存条目；不推进 BaselineHead、不增加跨服务原子事务或恢复 journal。
- **DC94 恢复分界。** T1 即 PREPARED，但不代表已有导入包。T1 后至 prepare checkpoint 前缺冻结输入稳定失败；checkpoint 持久化后复用绑定包/raw SHA/effect key，缺包不重建、不换 key。已提交副本才可从精确 commit 回填。
- **资源与重试。** N1/单 active、worker32GiB/reserve8GiB/显式M24；cache hit 的 mapping/FFI/Vec capacity/输出/导出也计 M，optional 保留先释放。RS≤min(N,8)，N1 实读并发1。client 单请求最多3次502/503尝试，接当前取消/截止，不叠外层HTTP重试；durable recovery 归原 Lifecycle。
- **计数真实。** diff 健康命中才可零比较/单侧摘要；零 Dolt 还要求完整导出/composite 的行需求由健康缓存满足。metadata/cache/restore/records校验/digest重绑分别计。FULL Preview 未计算的 baseline→modified 首次允许计算，不提前多算来凑零。
- 项目无兼容/迁移要求：直接改目标 Contract/内部格式/唯一基线 schema，删除替代路径。内部格式需要的新 golden 与冻结业务 golden 分清；不能用 actual 反填或修改业务预期掩盖差异。

## 5. 按 A–E 实施，不逐节等待批准

严格按 `p6-s5-kickoff.md` 的路径、输入输出和唯一验证 owner 推进：

| 小节 | 交付重点 |
| --- | --- |
| A | 完整任务投影/key、neutral codec/有预算统一 reader/handle、风险事件与 owning Contract；先完成内存 round-trip 和独立小向量 |
| B | 唯一基线 schema、SQLite cache/uses、TTL/protection、lookup-and-pin、完整登记、条件失效及有限失败处理 |
| C | Preview/History 接线、metadata-only 描述、按需 ensure_rows、独立导出 lookup、当前结果出版与 checkpoint 恢复 |
| D | T3 精确触达、RS 通用控制接线、同 M 生命周期、旧路径/mock/probe 删除 |
| E | 固定最终产品 V、必要权威/Compose、一次已确认 t1 定向清单、实际/沿用/未验证矩阵、独立退出核收与最终 H |

每节实施→固定 clean 已提交候选→独审→必要验证→有修改的修复复审/受影响复验→交接。可先做必要 focused 调试；不要先跑全量门禁再依赖审核发现基本接口问题。相同 finding 由同轮原审核者连续复审；每节都明确哪些产品/Contract/测试已变，哪些未运行或延期。代码提交的五包 ruff/mypy 与 Rust 要求按 AGENTS 执行，不能把设计轮的纯文档豁免用于代码。

A–D 的结果可为 E 提供真实合格来源，但 E 必须按最终实际闭包/镜像判定，不能预先承诺固定只跑三包。旧 Comparison pair-level/JSONL 条款等设计已定位的冲突，在其 owning 小节直接改成目标形态，不留并行双实现。

## 6. 验证范围已确认

- A–D 只跑必要 focused/marker/受影响集成；每个不变量一个权威 owner。key/codec/类型等纯逻辑不得引入真实 Dolt fixture，重复 payload 用共享参数表。
- 最终 V 集中完成必要权威包和适用 Compose；同候选同入口已完成的旅程不再单独重跑。闭包变化必实跑，carried 仍同来源节点、同 worktree、环境/镜像与 Hypothesis 规则。项目最终/发布门禁必须六包，不将阶段比例化解释为取消该要求。
- DC33 真实范围已经确认：**标准 t1 v1/v2，优先复用身份可核的合法已提交状态，仅必要 History 冷查、一个新 operation 的复查，以及真实 records 读取和完整 bundle/tar 核验。** 不再问是否同意此范围。
- FULL 例外、三节点、损坏回填、恢复、风险控制与预算取消主要由小型 Contract/focused 证明；不做 fresh t1–t4、2×t4、1暖3测或每种 cache 状态一遍完整旅程。
- 复查要用新 idempotency key/new operation，不能把原受理 replay 当缓存命中。冷态仅在本人隔离派生命名空间构造，不删冻结/共享资料。
- 独立 expected 来自手算/既有 golden/固定旧源受控捕获；SET 的内部与 wire profile 按 owning 逻辑语义对齐。不以新实现 self round-trip 代替正确性。
- 如存量状态不适配新唯一 schema，按 kickoff §5 先报告实际缺失，仅补标准 t1 必需的合法前置，不迁移旧库或扩成所有真实旅程；涉及他人资源/超范围才确认。
- 性能只观察，无数值退出门槛；仍报告实际资源/时间、业务断言、失败和未知。S4 M40 成功不证明 M24，不自动扩预算。

## 7. 节点、执行者与独立审核

五节点按当前 AGENTS/DC91/DC97 为统一空闲池；现场核合格后原子取得 `/home/dev/gdds-node-busy.d`，所有运行与有写清理均遵守占用，04/06/07 同宿主。不搬迁 carried 来源，不抢他人标记；自管占用入口不要外层重复加锁。测试、编译、lint、构建、取证均不在开发主机执行。

使用持续协调者、实施者、独立审核者与唯一测试/等待者；允许按本任务分工创建子 agent，先核实际并发槽，最多4个活跃角色（含协调者），不得递归扩队。实施与独审默认沿用协调者 GPT-6.1-Sol 模型；关键身份/风险/FFI/预算/事务审核使用适当高推理强度。测试执行/长测等待沿用 kickoff 的 Luna max；简单机械任务错峰，Luna 不自行设计关键语义。审核者不同时承担其审核范围的实现，新的实现审核角色不能用原设计 CLEAR 代签。

**按小节新建角色（Owner 2026-11-09补充）：**协调者持续保留，A/B/C/D/E各节使用新建的实施、独审和测试/等待子agent，不以follow-up复用上一节角色。先完成当前节finding连续复审、执行收尾与固定交接，再让旧角色退出活动分工；下一节角色从固定候选、owning Contract、handoff和必要原件接手，不继承旧角色对话或临时权限。此规则在本次补充时已进行中的B收口后，从C起执行；不改写A/B历史角色与审核原文。阶段切换无需再次申请许可，活跃角色含协调者仍不超过4。

独审在固定 clean detached worktree，报告写外部并逐字归档，同一小节内的修复由该节原审连续复审；验证时被测 worktree 不写入/提交。复用单份 `p6-s5-coordination.md` 记录本轮状态/决定，并使用最少必要小节 handoff、执行稿及退出报告，不建立新治理框架。

唯一测试者负责执行、保留日志和等待异常/完成；协调者不重复轮询、分钟级转述或跨会话预约，发现实际冲突才协调。长测不会因用户未回复普通状态消息而停止；用户新输入纳入当前任务。

执行前 SSH BatchMode 可达、clean 已提交候选、现场 Dolt/Compose/8000 与缓存前提齐全。离线/LAN、root PATH、Rust selector 四工具、TMPDIR、强制重装 native/build-input、network=none dependency-base、uv-consume 参数、镜像身份与日志全部按 AGENTS/testing conventions。不得用旧 `.so`、裸 uv 绕 wrapper、转发代理证据或漏缓存强跑。

首失败停止该次执行及后续验收，保原 numeric exit/log/SHA并收尾。DC68 同一工具故障最多三轮有修订、适用独审和受影响复验，不无修改自动重试、不换目录/节点重计次数，不改 expected 掩盖产品 finding。产品问题按所属 Contract 和授权修复；不可判定或需要改变边界时交 Owner。

## 8. 完成条件与最终交付

完成必须同时满足：

1. A–D 实现与 owning Contract/删除矩阵一致，原设计三项 finding 的语义没有回归，各节独审及后续 finding 关闭。
2. 最终 V/H 的必要产品检查、权威包/Compose及标准 t1 证据通过或满足真实 carry；没有以未运行/未知/失败冒通过。
3. 完整记录实际节点、起止 HEAD/UTC、入口 exit、日志及制品 SHA、缓存/镜像来源、N/M、资源释放与逐包运行/沿用；审核可追溯原件。
4. 最终 handoff/exit 原审写清代码 GO、证据 GO、未测项及其范围依据；只有 exit 条件满足后标记本地 `p6-s5-exit`，不 push。
5. 向 Owner 报告最终 H/tag、设计与实现关键差异、审核关闭情况、验证矩阵与真实结果、剩余限制；没有实质阻塞时不要以“下一步是否继续E”结束。

现在先核现场并读取必读输入，简要报告实际基线与实施顺序，然后直接从 A 开始，持续完成 A–E。

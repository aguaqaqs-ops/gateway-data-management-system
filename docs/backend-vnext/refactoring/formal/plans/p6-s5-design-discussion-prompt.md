# Phase 6 S5：设计缺口讨论与详细实施计划提示词

将以下正文发送给新会话，或直接要求其完整读取本文件后执行。

---

你是 `/home/dev/gateway-data-management-system` 的 Phase 6 S5 设计协调者，使用 **GPT-6-Sol xhigh**。

本轮目标：以已经正式退出的 S3/S4 和当前 main 实现为起点，核实 History 与跨操作缓存的实际缺口，完成技术细节讨论、完整设计、分节实施与验证计划，并对固定设计候选做独立审核。不要只给原则或把关键问题留到实施时再决定。

## 一、授权与阶段边界

1. **本轮授权设计、讨论、计划和相关文档，不授权 S5 产品实施。** 可以只读追源码/日志及核现场，整理或修订设计、kickoff、独审提示词及必要的 Contract/决议草案；未经确认的 Owner 选项明确标为待决，不写成已获授权。不得启动产品测试、编译、lint、镜像构建、真实旅程或容量原型，不创建 S5 exit tag，不推送。
2. S3/S4 均已正式 exit；其完成只解除 S5 的阶段前置，不等于本轮实施授权。不要重新审核整轮 S3/S4，也不要重跑其证据来准备 S5 设计。S6/P7 不在本轮范围。
3. 先读取实际 `AGENTS.md`、`docs/backend-vnext/testing-conventions.md` 及适用 skill。使用 design-readiness 时只做轻量准备度判断：先查已有材料；仅对会实质改变核心方案、且仓库与会话没有答案的问题向 Owner 集中提问，最多5个；普通命名、机械实现及已有决议不反复请示。没有阻塞问题就按明确假设继续。
4. 明确设计冲突、业务取舍与普通实现选择的区别。真正需要改变冻结语义时，给出源码/Contract依据、影响、具体选项和推荐；独立工作继续。不要把所有未知转成 Owner 问题，也不能把实质冲突自行定为普通优化。

## 二、先核当前事实

工作目录：`/home/dev/gateway-data-management-system`。

先只读核 HEAD、branch、index、tracked/untracked、worktrees、tags、并行修改及相关进程；必要时只读核节点有效占用。不能假定上个会话结束后的仓库/节点仍空闲；不 reset/restore 他人文件，不删除引用证据或保护资源。

以下为核查锚点，不代替实际 Git/交接核对：

| 阶段 | 固定产品V | 正式退出H / 本地附注tag |
| --- | --- | --- |
| S3 | `4b0a2eec725bffb0cf2e753df5f3e5d90e26c3fb` | `f9ef26081dfd4710d3709d9f5fbca24543f84de4` / `p6-s3-exit` |
| S4 | `6786b28a3506feab3d8eac7d1288c8b22525bb8f` | `1e778aae0522db75ea1f507ecfa83a6d7b714d65` / `p6-s4-exit` |

- S3历史通过已审合并 `87f4ae305c48cd06dfd3033f41c5a8b50ac3ebfc` 回到main，merge tree与第一父相同，保留S4产品树。**S5基线是核实后的当前main，不切回S3孤立候选覆盖S4实现。** 两个tag/H是各自证据与范围，不能混作同一个运行源。
- S4当前Rust tree为 `e2a901417b19259ece669637a41545e774261445`；实际权威来源为c9e四包、V6786的backend/RS两包，最终H在04原同WT实际ALL_CARRY。源WT/env/images与原件保留，后续沿用仍按实际闭包判断。
- 默认仍为N1、worker32GiB/reserve8GiB/M24；S4另以N1、48/8/M40验证了DC98真实t4。原S3 M24大负载失败、S4 M24未测及撤回统计项保持原义。不要以M40成功或低RSS宣称M24通过，不自动改生产默认。S5拟用资源档在kickoff明确，并核现有授权的适用范围。
- Q18/前端按最新独立handoff核消费者和接口状态；不继承旧“未验证”结论，也不由后端退出推导FE3c或全部前端已验收。

## 三、必读材料与源码入口

先读以下直接输入，相关内容按真实依赖追读，不遍历全部历史：

- `docs/backend-vnext/refactoring/formal/plans/p6-design.md`：§1.5、§4.1–4.2、§8–§9、§11、§14–§16；`p6-execution-plan.md` 的S5、路径归属与后续边界。
- `p6-s0-owner-decisions.md`：DC38–DC43、DC47、相关存储/恢复决议，以及DC91、DC97、DC98现行补充。旧数值门槛、固定节点用途、全旅程/合成1暖3测安排须按最新决议解释。
- `p6-s3-candidate-handoff.md`、`p6-s3-exit-review.md`、`p6-s3-design.md` §9及最新累计原审；重点是operation内去重、风险候选控制步骤与真实records消费者移交。
- `p6-s4-handoff.md`、`p6-s4-exit-review.md`；需要接口细节时追S4 A–D交接。S2b规范表存储/Arrow/预算的实际边界追 `p6-s2b-kickoff.md`、`p6-s2b-arrow-mapping-design.md`、`p6-s2b-e-handoff.md` 及相关小节原审。
- `p5-5e-history-compare-design.md`、`p5-5e-history-compare-execution-plan.md`：仅作为当前History语义来源，核现在代码，不恢复旧实现。
- `p6-be-q18-handoff.md`、最新Q18原审；按History真实消费者需要追前端与BE-d完整bundle契约，不接管其产品路径。
- 政策：`formal/policies/proportional-assurance-and-risk-based-verification-policy.md`、`rust-safety-and-performance-policy.md`，以及ADR0009/0012的可信内部组件与cleanup边界。

除已写完整路径外，上述p6/p5文档均位于 `docs/backend-vnext/refactoring/formal/plans/`，政策位于 `docs/backend-vnext/refactoring/formal/policies/`。Owning文档另有两组路径，**不能误写成全部位于formal/contracts**：

- `docs/backend-vnext/contracts/{comparison,risk,comparison-surface,comparison-bundle}.md`，以及 `docs/backend-vnext/artifacts.md`。
- `docs/backend-vnext/refactoring/formal/contracts/{canonical-storage-and-repository-boundary,shared-canonical-encoding,operation-lifecycle-and-integrity,repository-service}.md`。
- 追这些文档实际引用的History/HTTP、protection/cleanup、checkpoint、规范表与导出缓存条款；ADR0013用于区分内部规范存储与Repository wire类型。

源码优先从以下当前入口画出真实调用图（后列路径相对 `vnext/backend/src/gateway_backend/`）：

- `application/history/{compare,compare_jobs,compare_bindings,contracts,ports,queries}.py`，`application/pair_pipeline.py`、canonical metadata绑定及当前History受理/恢复/发布流程。
- `capabilities/comparison/{production,native,artifacts,pair_planning}.py`，当前risk、surface、bundle实现及真实records读取校验入口；先用rg定位准确risk模块，不猜目录。
- `capabilities/snapshot_materialization/`、`capabilities/table_access/kernel.py`、`infrastructure/repository_read/{parent_catalog,http_arrow}.py`。
- `application/submission/{finalize,finalize_transaction}.py`、artifact release、control DB事务/protection；`artifacts/snapshot_table_export_cache.py` 与现有SQLite导出缓存owner。
- `vnext/rust/` 的公共facade、共享池、Arrow、context/预算/取消接口；当前History、Preview、Submit、缓存和cleanup的测试及架构import guard。

先登记“已实现/部分实现/未实现/待核”，列出对应源码位置。operation内session去重、规范表副本、表导出缓存、pair产物与S5跨operation diff/risk缓存必须分清，不能因已有名为cache的结构就判断S5已实现。

## 四、设计讨论必须关闭的问题

逐项给出“当前事实 → 缺口/冲突 → 推荐及必要替代方案 → owning接口/Contract → 失败语义 → 最小验证owner”。本轮是补齐设计，不要求所有问题都产生新机制。

1. **History完整数据流与不变量。** 两/三节点解析成哪些有方向的pair，如何冻结repository/scope、精确commit、ruleset和节点绑定？逐表结构过滤仍用表摘要、schema、storage view、projection version的完整条件；ordered未变化facts取本pair当前侧或合法缓存，保gid/no、伪gid、keyless重复行、schema演进、共有列、degraded语义和composite分支。明确旧流程的替换、保留与删除边界。
2. **完整任务身份与命中条件。** 从实际完整、去绑定后的单表任务派生key，覆盖规则主体/版本、两侧有效比较键与存储事实、schema/count、算法/记录格式、风险options/diagnostics及artifact scope等真实输入，避免手工列几项导致漏依赖。分清哪些表名/schema摘要允许共享、哪些事实上不同而必须miss；不得为了命中去掉真实语义或跨scope复用。
3. **缓存值和重新绑定。** 决定比较facts/records、纯风险候选的具体payload、reader/handle接口与格式owner；哪些值不含operation/pair/table/display/标注编号，哪些引用必须在当前operation重绑？命中后records/closure、风险、surface/bundle的身份与digest如何等价于未命中路径？不能将S3内存map、native handle或已经套pair上限的最终risk outcome直接持久化。
4. **风险缓存的纯函数边界。** 原S3候选序列包含当前`CheckRecordsClosure`等控制步骤；命中仍对当前closure执行必要检查、当前上限/等级过滤/编号/时间检查。只完整成功序列可复用，不缓存截断、超时、取消或前次验证成功结论；不把时间预算变成可缓存事实。设计可持久表达的最小结果与重放接口，或有证据提出需要Owner决定的收敛，不暗删DC43要求。
5. **形成、登记、TTL与删除。** Preview/History何时形成条目，哪些现有artifact/protection owner可复用，谁续引用、TTL从何时起算、如何处理读者与cleanup并发？数据字节可重算，不能升级成不可丢失事实或新增持久journal。缓存保留不得挤占必要计算；缺失、损坏、过期或写入失败的安全miss/有限回填与真实错误分别定义。新control DB字段直接改基线，不造兼容层或迁移框架。
6. **Submit finalize与权威边界。** 澄清旧设计“移动head同事务登记引用”究竟指哪个head、哪笔control DB事务。Repository技术main/CAS与control DB不是一个跨服务数据库事务；沿用现有effect/checkpoint/finalize恢复屏障，Submit不提前推进业务BaselineHead，T1仍PREPARED。具体列成功、回放、重试、失败时引用归属/释放点；不重做S4 publisher、冻结包或durable状态机。
7. **查找顺序与回填正确性。** 结构过滤、diff/risk缓存、规范表副本、exact-commit Dolt兜底、表导出缓存分别在哪层消费？验证什么、何时回填、谁关闭stream/mmap？区分可丢失派生缓存、权威commit绑定和未提交T1冻结，不能把坏权威绑定当普通miss吞掉。内部IPC与Repository Arrow wire物理表示不同，独立预期先按owning逻辑语义对齐，不重复S4 SET跨profile误比较。
8. **资源与并发。** 画出读表/比较/命中重绑/Parquet/风险/汇总/导出的同时驻留及最后消费者；同operation M实际涵盖Arrow/FFI复制、Vec capacity、索引、输出与导出bytes，hit/miss/取消/异常均释放。不把mmap视为零预算，不恢复Python逐行热路径。复用显式KernelExecutionContext和共享池；RS读取≤min(N,有效RS容量)，503有界退避继承取消/截止，N1不自动变8并发。跨operation调度/多worker归P7。
9. **接口、消费者与旧路径删除。** 列现有HTTP/History结果、records API、完整bundle/tar、readback/恢复和独立计算消费者；校验必须覆盖真实读取路径，不能把raw/ref检查冒完整records语义校验，也不要求每次下载新增全份解码。能力模块保持DAG，不形成comparison/risk→workflow依赖或直接越权FFI边；保真实library facade，不新增无consumer SDK/服务。替换算法时同步删除专属mock/probe，不保永久双实现。
10. **计数断言及FULL例外。** H1/H3零Dolt读、零比较、零单侧摘要只在pair已计算、规则相同、缓存健康的条件下成立；FULL Preview未算的baseline→modified允许首次重算，不为它提前多算pair。明确定义metadata读取、缓存/IPC读取、records验证、比较kernel/单侧facts与派发计数，核现行Contract是否有歧义；不能隐藏实际调用凑零。损坏/缺失回填、H2冷读、三节点正确性由最合适层级证明。

缓存本身通常是派生/可重算对象；涉及权威绑定、跨scope、保护引用和事务时保相应强约束。默认采用现有artifact/control DB/cleanup能力与最小机制；没有具体威胁、consumer或可复现故障，不增sidecar、独立UID/helper、通用缓存平台、spool、持久evidence状态机或恶意同euid换名证明。

## 五、验证成本与当前Owner原则

- **业务正确性优先，DC97/DC98生效。** 旧H1/H2/H3时间目标可保留作参考/观察，不把数值达标作为退出门槛；旧2×t4、三节点完整旅程、1暖3测及每段profile不是自动执行清单。不能把S3/S4取消项机械转给S5/S6/P7。
- 先用既有golden/Contract与必要小向量证明命中/未命中等价、key变化miss、完整条件、风险上限、scope隔离、损坏回填、引用/恢复与取消/预算。H1/FULL例外/H2/H3/三节点是需覆盖的行为，不等于分别新跑整条真实旅程。每个不变量只设一个权威测试owner。
- 为S5推荐最小代表真实输入与必要真实路径，并说明为何需要、可否复用合法已存状态、预计成本及哪些业务断言只由focused覆盖。不要先承诺fresh t1–t4全旅程，或为每个cache状态重新Preview→Submit→审核→Archive→History。独立expected来自手算/既有golden/固定旧源受控捕获，不以新实现反填。
- 提出“运行/合格沿用/未验证”矩阵：A–D仅必要focused/受影响集成，最后候选集中必要权威/Compose；闭包变化包仍按规则实跑，合格沿用必须同来源节点/同WT/环境与镜像规则，不因节省时间口头carry。最终项目/发布完整六包要求不被取消；S5阶段门禁按现行闭包与实际影响制定。
- 现有五节点均32C/64GiB、无功能分工，任一实时空闲且准备合格者可用；04/06/07同宿主。专用节点、原子占用、离线缓存/LAN、root PATH、强制native重装/build input等按实际AGENTS执行，不搬他人来源、不占用节点做纯讨论。
- 后续长测试交唯一Luna等待异常/完成，常规监视可小时级，协调者不重复轮询或逐次跨会话预约；实际冲突才协调。执行稿复用现有入口，静核真实CLI边界（uv-consume会拒绝业务参数名`--project`）及root SSH环境，避免重建庞大取证工具。工具失败按DC68留原件、有修订后复验，不改预期掩盖产品问题。
- 特定名称特征的大表组并行优化，当前只参考已有几份真实数据，不生成放大合成数据；真实大规模接入后按实际规模/热点分布再决定专项，不固化样本表名，也不自动成为S5验收项目。小型正确性边界向量仍保留。

## 六、分工、交付与完成条件

沿用持续协调者＋设计者＋独立审核者：均新建角色，不继承上轮结束的子agent。协调/设计用Sol xhigh；缓存身份、风险语义、FFI/预算/事务原审可用Sol max，同轮修复由原审连续复审。先核工具实际并发上限；至多四个活跃槽（含协调者），工具限制更低时按实际错峰，不递归扩队。本轮没有测试执行授权，不因预配Luna角色就跑测试；后续实施时唯一测试/监视者Luna max，简单机械任务错峰处理。关键语义与资源/事务方案不交Luna自行设计。

完成以下文档，已有同义文件先核后更新，不制造重复入口：

1. `p6-s5-design.md`：已核实现清单与缺口/决策表、接口/缓存键值、数据流与资源/引用生命周期、事务/恢复/回填边界、Contract归属、行为与digest保值/允许变化清单、消费者/删除矩阵、非目标。
2. `p6-s5-kickoff.md`：有依赖的小节划分（可用A–E但不强凑），每节输入/输出/路径归属/产品与测试owner、固定候选→独审→修复复审→核收时序、最小验证与成本、集中最终来源绑定、明确exit条件及仍待Owner确认的范围。实现顺序具体到可独立交付，不提前给实施授权。
3. `p6-s5-review-prompt.md`：独审范围、完整只读输入、核心正确性/预算/事务/缓存纯函数问题、冻结候选与预期来源、比例化约束及必须停止交Owner的实质冲突。
4. `p6-s5-design-review.md`：新独审者对固定clean detached设计候选的原文结论与finding；同轮修复连续复审到关闭，不能用实施者自查代签。必要时用单份`p6-s5-coordination.md`记录事实/决策/未决项，不新增治理框架。

允许本地必要文档提交，直接main、精确路径提交，不改写已引用提交；独审在clean detached WT，测试/构建仍不运行。最后交付固定设计候选、原审报告及关闭情况、少量真实待决问题和推荐、实施节奏与验证成本。**设计CLEAR不等于产品GO；本轮结束后等待Owner另行授权实施S5。**

现在先核实际起点并阅读上述直接输入，给出有源码依据的S5现状/缺口与推荐讨论顺序，然后推进完整设计、详细计划和独立设计审核；不要重新询问是否可以开始这轮设计。

# Phase 6 S6：设计讨论、缺口补齐与详细实施计划提示词

在新对话中要求完整读取并执行本文件。正文的授权止于设计、讨论、计划和设计独审。

---

你是本项目 **Phase 6 S6 的持续设计协调者**。请从当前 main 与已正式退出的 S1–S5 实现出发，核实 S6 收尾的真实需求，发现设计冲突、业务缺口与实现缺陷，与我讨论需要业务判断的具体场景，落成可独立审核、可直接交给实施会话使用的详细文档。

不要只转述旧 S6 清单，不把关键方案留给实施者决定，也不要为了表格完整扩张验证范围。下列问题是核查起点，并非限制你发现其他实际缺口。

## 一、授权与完成边界

1. 本轮授权读取源码、Contract、Git、现有日志与证据，开展设计讨论，编写设计、kickoff、协调记录、设计审核材料和必要的 Contract/决议草案；相关文档可以直接本地提交到 main。不在普通文档步骤或小节边界重复申请许可。
2. **不授权产品实施、原型试跑、测试、语法检查、lint、编译、镜像构建、真实旅程、容量/性能测量或资源清理。** 需要这些动作才能消除的未知，写清最小验证方案、成本和前置条件，留待授权实施时执行。设计本身不能签出产品或实测 GO。
3. 不创建 S6/Phase 6 exit tag，不推送。上一轮 Astra 临时授权不延续；不从历史提示词继承模型或节点权限。S5 exit 只解除 S6 设计的阶段前置，不是 S6 实施或 Phase 6 总退出授权。
4. 先读实际 `AGENTS.md`、`docs/backend-vnext/testing-conventions.md` 及适用 skill。采用 design-readiness 时，准备度检查最多集中提出 5 个会实质改变核心方案的缺失问题；已知决议、可逆实现选择不重复问。这不是后续必要业务讨论的总问题数上限，也不要求凑满问题。
5. 有实质业务取舍或冻结语义冲突时，给出证据、具体场景、可选方案、推荐和代价，再由我决定；其他独立工作继续。待决不能因等待时间经过而视为批准。没有实质阻塞就说明假设并推进。

## 二、先核实际 main、阶段前置与并行状态

实际 main 工作区的已知位置是 **`/home/dev/gdds-s5-design-main`**。`/home/dev/gateway-data-management-system` 在提示词编写时为前端工作区，不要在那里切分支或覆盖文件。先核实际 branch、HEAD、index、tracked/untracked、worktree 列表、tag 和相关并行修改，之后再选择正确的 main 工作区；路径与下列 SHA 都是核查锚点，不替代现场事实。

| 对象 | 已确认锚点 |
| --- | --- |
| S5 最后产品 V2 | `2d8b29d332ceb467ba77bb4826fb0925653ebb4e` |
| S5 正式退出 H | `e80f6ddbac88b47b6c41d8d2faa21e39c24dbd53` |
| S5 本地附注 tag | `p6-s5-exit`；tag 对象 `5d169e6db68c2469d3ce010b469dc4b3034dd196`，指向上述 H |
| V2/H 的 vnext tree | `fb92c4757f4f9d9174ce6ab8c17187fdabafacdf` |
| V2/H 的 Rust tree | `c0213e18a9645c5cfbd39f310f532273a03a10cb` |
| S4 产品 / exit H | `6786b28a3506feab3d8eac7d1288c8b22525bb8f` / `1e778aae0522db75ea1f507ecfa83a6d7b714d65`，tag `p6-s4-exit` |
| S3 产品 / exit H | `4b0a2eec725bffb0cf2e753df5f3e5d90e26c3fb` / `f9ef26081dfd4710d3709d9f5fbca24543f84de4`，tag `p6-s3-exit` |

- S6 基线是核实后的当前 main，允许包含随后正常提交的文档或产品改动；逐项判断其影响。不要切回孤立的旧阶段候选覆盖已合入实现，不 reset/restore 他人文件，不改写已引用提交或 tag。
- S5 exact-H 独审原件：`/home/dev/gdds-s5-logs/archives/p6-s5-exit-e80f6ddbac88/e-exit-review.md`，SHA256=`2e92a3239016b5a523e2a6a3e364f02f8f3fc4cb214d9dd371af3011fe71f860`。
- 同目录 `receipt.json` 的 SHA256=`c73cced09622747470e0ef194798ad56a95ae53ef8bf175740029e75ee3f7974`；它记录实际 tag、H 绑定、资源释放和证据限制。结合库内 S5 handoff/审核归档核对，不把较早的“待退出”历史行当作当前状态。
- 保留成功、失败及未知原件，保留 carried 来源 worktree/env/images、真实输入与冻结基准；不为设计重跑旧证据或清理现场。源原件暂不可读时先查已有归档和引用链，不能直接补造结论或启动重跑。
- S5 H 保留并行 FE3c 文档，不代表后端为 FE3c 签验收。Q18、BE-a/BE-d、前端按各自最新交接判断，不继承已过时的“未完成”状态，也不越界代签。

## 三、材料读取顺序

以下未写目录的 `p6-*.md` 均在 `docs/backend-vnext/refactoring/formal/plans/`。先读直接输入，之后沿真实依赖追读，不遍历全部历史取代分析。

1. `AGENTS.md`、`docs/backend-vnext/testing-conventions.md`；比例化政策 `docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md` 与 `rust-safety-and-performance-policy.md`；相关 ADR 0009、0010、0012、0013。
2. `p6-design.md`，重点为 S6 §12、验收 §16、资源与 Rust/Python 边界及相关阶段约定；`p6-execution-plan.md` 的 S6、路径归属、最终门禁与退出条款。
3. `p6-s0-owner-decisions.md` 的最新有效决议，特别是 DC33、DC35、DC38–43、DC47–48、DC55、DC68、DC74、DC78、DC83–84、DC87、DC91、DC94、DC97–98；核是否已有更新。分清原始决定、后来补充和未获批准的提案，不能仅凭编号较新就自行推断取消所有旧义务。
4. `p6-s5-design.md`、`p6-s5-kickoff.md`、`p6-s5-coordination.md`、`p6-s5-handoff.md`、`p6-s5-e-review.md` 与上述最终退出原件。需要定位具体机制时再追 A–D handoff/原审，不重审整轮 S5。
5. `p6-s3-candidate-handoff.md`、`p6-s3-exit-review.md`、`p6-s3-e-scope-supplement.md`、`p6-s3-performance-report.md`；`p6-s4-handoff.md`、`p6-s4-exit-review.md`、`p6-s4-business-validation-scope.md`；`p6-s2b-e-handoff.md` 中 W1/W2、容量与资源交接的最终状态。不要只读其中早期暂停记录。
6. Owning Contract：`docs/backend-vnext/contracts/` 下的 `comparison.md`、`risk.md`、`comparison-surface.md`、`comparison-bundle.md`、`snapshot-table-access.md`，以及 `docs/backend-vnext/artifacts.md`；`docs/backend-vnext/refactoring/formal/contracts/` 下的 `canonical-storage-and-repository-boundary.md`、`shared-canonical-encoding.md`、`operation-lifecycle-and-integrity.md`、`repository-service.md`、`performance-measurement-and-baseline.md`。按实际改动追相关 HTTP、存储变更及恢复 Contract。
7. 对照当前 `vnext/backend`、`vnext/rust`、Repository Service/client、runner、闭包与容器脚本的真实 consumer。Q18、BE-d、前端只追与 S6 缺口有关的实际接口和交接。旧基准的来源不清时再查其原始交接，不能用新实现自己的结果当独立 expected。

文档冲突要定位到条款、当前代码和实际证据；把“设计未落地”“代码缺陷”“历史事实”“已经变更的计划”分别说清。

## 四、必须带入的事实与结论边界

### 4.1 S5 已通过的范围

- V2 在 06 clean 来源 worktree 实跑六包权威 runner 与同次适用 Compose，原 exit 0；最终 H 在同节点、同来源 worktree 实际逐包比较全部可沿用、镜像身份绑定，并在本人资源实际释放后获独立 EXIT_GO。不能用这次阶段 carried 直接替代 S6 项目最终全量门禁。
- Owner 确认的真实范围是标准 **t1 v1/v2 最小合法前置、必要 History 冷查/复查、真实 records 与完整 bundle 消费**；实际含两次 History 操作和四个完整 tar GET。未跑 fresh t1–t4、合成 2×t4 或一暖三测；不把这些写成遗漏后机械补齐。
- 固定旧实现独立 expected 核收 12 条记录（STANDARD 6 / ORDERED 6）、6 条 MEDIUM_LOW 风险 annotation 和 composite 语义。两处 XML 原字节变化已按真实逻辑核对，不能仅据文件大小变化判定业务漂移。
- warm 的 comparison kernel、ordered 单侧计算、RS rows HTTP 均为 0；仍有 cache restore、records 验证、digest 重绑、metadata/catalog 读取与导出命中。不能宣称“所有 native、校验或网络工作为零”。
- 冷 44.148s、暖 34.118s 仅为两次操作观察，不构成中位数、正式提速或容量承诺。cold cgroup peak 为 UNKNOWN；warm 峰值不能代填 cold。
- 原 RS 权威日志有 1 skip，原 `-q` 未给出具体身份/原因；不能据源码推断写成确切原因或 PASS。RS admission 诊断不可观察、可选物理 RiskReport 专有字段未直接导出等限制继续保留，不能因此抹去已观察的真实 records/annotation 证据。

### 4.2 身份、恢复与资源口径

- source/checkpoint/HTTP Surface 与最终 BundlePair/tar Surface 是不同身份层：最终嵌套 ref JSON 的重写会改变 raw SHA/size，按 owning Contract 重算最终 Surface digest。应分别验证每层绑定和冷暖稳定，不能强求跨层 digest 相等，也不能通过忽略实际内容/目标/annotation 标识来放松核验。
- operation worker 日志中 `operation_id=-` 可表示无业务 operation 的 ready/drain/exit 生命周期事件；不能据此虚构另一次业务操作。日志 INFO 是否齐全也不自动成为业务 Contract。
- 默认仍是 **N1、单 active、32 GiB worker envelope、8 GiB reserve、显式 M24 GiB（25769803776 bytes）**。M 是计算准入预约预算，不能等同于 RSS 或 cgroup peak。S5 cold/warm reservation HWM 分别为 25438132736 / 25438127616 bytes，二者不是同一个数。
- S3 默认档 fresh t1–t4 功能证据、增预算 M40 的派生负载测量、S4 M40 的 t4 证据、S5 M24 的 t1 证据分别绑定其产品/输入/配置。S3 原 M24 大负载失败、S4 M24 未测或其他 UNKNOWN 不因后续小输入成功而关闭；不把 M40 改成默认，也不据低 RSS 推断预约容量通过。
- S5 冻结的事务/CAS、prepare checkpoint、T1/PREPARED、cache pin/失效、恢复重验证和风险控制步骤以当前 Contract/实现为准。仅在发现具体跨阶段缺陷时追查，不能为收尾泛化成新的恢复或缓存平台。

## 五、先解决 S6 范围与决议冲突

### 5.1 逐项处置旧义务

当前 `p6-design.md §12` 与执行计划仍含加速曲线定 N、§16.3 全场景、2×t4 全负载一暖三测、t1–t4 全旅程、存储报告、V8 门禁剖析等旧安排；执行计划同时已有 DC98 收敛补充。**不得直接照旧矩阵开测，也不得自行把全部旧义务删去。**

先形成紧凑的义务处置表，每项记录：原条款/Owner 决议、最新有效范围、已有实际来源及适用产品/输入/N/M、尚缺的业务证明、建议处置、所需 Owner 决定及重新启动条件。处置可为已完成、合格复用、最小新增验证、明确取消、待决；未知不是通过。

特别核清：

1. **W1/W2：**DC83/DC84 明确有“最迟 S6”复核/取证义务；DC97 只取消数值达标作为退出门槛，DC98 又要求按业务目的和成本收敛。已有来源能证明什么、仍需何种有效端到端测量、是否改变次数或口径，必须给出明确方案并讨论，不能长期 pending，也不能擅自豁免或恢复整套旧测量。
2. **S3/S4 取消项：**S3 已确认取消的 18 个未启动项、W4 UNKNOWN 和 S4 撤回的大队列/合成压力不自动迁移到 S6。不能把“Phase 6 收尾”解释为追补全部历史统计；真实已发现故障仍按其最终处置证据判断。
3. **DC74 / BE-c：**t4/2×t4 完整 bundle 体积仍是待决提案。核有无后续确认；没有就讨论真实 consumer 和需要的报告，不把草案当既定验收。
4. **定 N 与专项优化：**旧 1/2/4/8/16/32 曲线不自动生效。现有 N1 是否满足当前业务、是否确有必须在 S6 决定的线程配置问题，依据实际工作负载和已授权目标讨论。具名大表的合成放大/并行调优已被 DC98 排除为当前自动任务；P7 多 worker、跨 operation 调度与生产总容量不顺带纳入。
5. **最终门禁：**S6 的 Phase 6/项目最终收口仍保留当前候选上的六包完整权威 runner 和适用容器门禁、来源与独审核收。不能用比例化或阶段 carried 将这项删去；与性能专项、真实数据最小范围分别决策。

DC98 不降低冻结语义、真实表结果、事务/CAS、幂等、恢复、取消、资源边界及来源要求；同样不要求为了每段 timing 构建新机制。讨论后同步修订现行 S6 条文，保留原始历史事实和原审，不让两套矛盾要求继续并存。

### 5.2 业务场景与具体设计缺口

从当前用户路径和实际 consumer 建立“已完成 / 部分完成 / 缺失 / 未知”清单，明确 owning Contract、代码入口和现有证明。重点检查跨阶段拼接处，而不是重新证明每个已退出阶段：

- Preview、Submit、审批、Archive、BaselineHead、History 与完整 records/bundle 消费之间，是否还有实际状态、权限、来源或冻结产物绑定缺口；业务基线推进与技术提交/CAS 是否被错误混同。
- 冷读、warm、恢复、导出复用及完整包下载是否仍给出相同业务语义；首个未计算 pair 合法重算、derived cache miss 与真正权威状态损坏是否区别正确。
- Rust core、Python facade、Arrow/records reader、risk 控制流、Repository 访问与 operation context 的现有职责是否闭合；仅在真实缺陷需要时改变接口或流程。
- 资源拒绝、取消、截止、租约丢失与正常退出是否会留下明确的业务损失；优先使用现有机制和既有测试 owner，不建立假设性的恢复层。
- 当前对外承诺、Phase 6 完成定义与 P7/前端/未来规模优化是否有实质空隙。未来愿望或观测不足不自动变成本阶段产品需求。

涉及选择时，用“谁在什么状态做什么动作、当前与预期结果、失败损失、现有约束、选项与代价”的具体场景和我讨论。不先铺一整套抽象问卷，也不只问“是否同意方案”。

## 六、清理、验证与最终收口的设计要求

### 6.1 删除有替代者的实现，保留真实职责

按 DC78 核旧 Python 热点算法、临时差分入口、重复 fixtures/测试及无 consumer 的中间层是否已删除；为每个拟删对象指出实际替代者和引用情况。当前 Python orchestration、risk 业务控制、适配/读取/发布、必要 Contract/golden/恢复测试不因语言或“旧”标签被删除。

本项目没有部署兼容或历史数据迁移要求：需要改 Contract/schema 时直接设计目标形态，不加双读/双写、别名、回填或生产 fallback。阶段冻结语义仍受约束；发现真实错误先说明冲突和影响，不能改 golden/expected 掩盖。`legacy/` 只作参考来源。

遵守比例化政策：权威/不可逆事实保持强 Contract、事务/CAS/幂等与关键 crash 证明；可恢复 durable、derived/temporary 和内部细节按各自风险设计最小机制。新增 journal、sidecar、helper、隔离身份、tombstone 或 evidence 平台须有当前实际威胁/损失/consumer/可复现故障及 owning 决策，不能用收尾审计本身作为理由。

### 6.2 按实际变化确定最小验证

- 每项新增/修复行为指定唯一的主要测试 owner、真实 consumer 和预期，区分已有证据、focused/Contract、必要真实片段和最终门禁；不按层复制同一矩阵。小型合成正确性向量可用，不等于获准合成放大或压力测量。
- 正确性 oracle 应来自已冻结业务向量、固定旧实现、人工可核结果或 owning Contract，不能只做新实现自我 round-trip。核源码变更、真实表/records/risk、SQL/golden、typed bytes 与绑定，按实际影响收敛。
- H1/H2/H3、FULL/三节点、损坏与恢复等保留当前语义及既有 owners；不因旧矩阵里有名字就全跑真实旅程，也不能把未跑的真实场景写成已实跑。零比较、零单侧、零行读各有前提，与 metadata、恢复、验证及重绑分别记。
- 计时与资源分开：原始起止/轮询观察、正式 samples/median/range、预约 HWM、RSS、cgroup 生命周期峰值不能互相代替。沿用必须说明当前 consumer、来源与适用性；不将旧版本统计回填为新版本实测。
- 存储与门禁时长报告优先复用现有合格日志和事实。只在有实际决策用途时提出最小补测，不默认细粒度 profiling、重新运行 V8 或全负载容量普查；容量估算与实测分列。

### 6.3 节点、失败处置与最终候选

实施计划必须写入现行执行规则，不能沿用旧提示词的固定节点分工：

- 五节点 `ct108-gw-dms-04`、`ct108-gw-dms-05`、`ct108-gw-dms`、`ct107-gw-dms-06`、`ct109-gw-dms-07` 均为 32 vCPU/64 GiB 的统一空闲池；04/06/07 同物理宿主，不是五套独立硬件。合格空闲节点可直接按实际状态原子取得本人标记，无常规跨会话预约；只对实际冲突或涉及他人资源的操作协调。
- 所有产品测试、静态检查、编译与容器验证只能在专用 CT 的 clean、已提交 worktree 执行，不在开发主机。保持 offline、LAN 缓存、locked 依赖、Rust build-input、镜像 config digest/全部 DiffID 和同来源 carried 等现行前提；节点内测试并发与产品 N/M 分开。
- 不扩张到节点全局 prune、按年龄删文件或移动他人资源；保护输入、冻结基准、原始失败、有效来源 worktree/env/images 与未决现场。必要本任务清理也须有明确所有权和保留边界。
- 失败先保留 numeric exit、日志/SHA 和实际触及范围，停止并按适用规则处理。DC68 对同一具体工具/取证故障允许最多三轮有修订、独审和受影响步骤复验；不无修改重试、不靠换节点/目录重置次数，三轮未解决或原因/副作用不明交 Owner。只读后处理等例外按当前条款，不为补一个后处理字段重跑整段业务旅程。
- 普通阶段的按包 carried、阶段镜像等价与**项目最终/发布门禁**分别设计。最终门禁须六包实跑，最终 production gate 在最终 HEAD 本机重建并完整运行适用容器门禁；同一次 runner 已覆盖的 Compose 不另跑一次。不用 S5 合格来源替代这项义务。
- 先设计最终候选冻结、独审、实测、必要修复/复审及退出记录顺序。避免“写入自身 SHA/刚完成的结果→产生新 H→再绑定”的循环；可预先冻结 tracked 文档结构，以外置不可变回执绑定字面最终 SHA。不能为解决文档自引用绕过最终门禁的 HEAD 要求，也不能在被测 worktree 写文件或提交。

## 七、讨论与角色组织

持续协调者负责把事实、假设、已确认决定与待决项分开，发现缺口后追到足以决策的具体程度。每轮优先讨论少量会改变业务行为、核心方案、成本或退出范围的问题，附证据与推荐；不要反复询问已经确认的 M24、节点池、取消项或普通文件命名。

本轮设计独审使用**新建的 S6 设计审核子 agent**，不复用 S5/E 角色。独审在 clean、只读 detached worktree 上审核固定设计候选及指定区间，按仓库要求接 `legacy`；不运行产品测试、不做产品实现。设计者不代签独审，原始 finding 和同一审核者连续复审应保留。

未来实施的角色说明和 kickoff 明文写入：

- 协调者持续；进入每个新阶段或已明确划分的实施小节，**新建该节实施、独立审核、唯一测试/等待子 agent**，不向旧阶段角色换任务复用。
- 同节原 finding 由该节原审连续复审至关闭，未收尾的执行不因换节转移或中断；交接含固定候选、Contract、已完成、未测、未决与原始证据位置。
- 创建前检查实际并发槽，最多 4 个活跃角色含协调者；不递归扩队。未来实施/测试角色等到该节获授权并实际需要时创建，本轮不预占。
- 已结束 agent 要继续本节工作时使用真正触发执行的任务分派，不能只发消息后假定其正在运行。测试者唯一执行并等待异常/封口，协调者不重复高频巡检，不新建监控平台。
- 不继承历史临时 Astra 权限；按新会话明确授权与实际可用模型组织。模型选择不改变独审独立性、验证范围或授权边界。

## 八、文档交付与设计完成条件

以仓库现有格式为准，至少形成下列可直接用于实施的材料；不为清单本身新建治理系统：

1. **`p6-s6-design.md`**：实际基线与范围、义务处置表、业务场景与不变量、冲突/缺口及决定、具体接口/数据/错误与恢复方案、资源配置、清理对象、明确不在本轮的事项与重新开启条件。关键路径说明输入、步骤、成功与失败后的状态；没有产品改动的部分明确写“无需实现”及依据。
2. **`p6-s6-kickoff.md`**：依据实际依赖划分小节，不机械照搬 A–E；逐节列文件/模块、输入与输出、实施/独审/测试职责、最小验证及来源复用、必要成本与节点前提、finding 修复/复审和停止条件、最终候选冻结与 Phase 6 退出顺序。真实数据/性能范围列清待我确认的具体选择，不把设计 GO 当执行许可。
3. **`p6-s6-coordination.md`**：简洁维护当前候选、已确认决定及依据、假设、待决、风险、下一步和交接入口；将按阶段新建角色规则写入角色说明。历史事实保留，不靠不断堆叠相互矛盾的“当前状态”推进。
4. **`p6-s6-design-review.md`**：新独审对固定候选的原始结论、finding、修订与连续复审。核业务边界、Contract 一致性、遗漏、最小验证、成本、角色与收口流程；发现缺陷就修文档并复审。设计审核通过只表示可以请求实施确认，不能替代 CODE/EVIDENCE/EXIT_GO。重大待决未解时不得强行给整体 GO。
5. 将我已确认的 S6 范围和方案同步到 `p6-design.md`、`p6-execution-plan.md` 及必要 owning 文档/决议；未确认项保留提案身份。最终文档不能同时保留“默认跑旧全矩阵”与“按 DC98 收敛”两套执行要求。

交付前确认：真实缺口有明确处置；已取消、未测、未知和历史失败没有变成 PASS；未把延期义务悄悄取消或把取消项搬到 S6；必要的核心业务与验证范围决定已讨论落实；实施者无需重新猜业务语义、预算、接口或最终门禁顺序。

现在先核实际仓库与 S5 退出事实，报告是否具备 **S6 设计讨论**条件及最优先的少量具体缺口，然后进入讨论、补齐设计和独审。持续推进已授权的设计工作；完成后交付文档与待实施确认事项，**不要自行启动产品实施或推送**。

# Preview 全阶段优化决策调查计划

2026-11-14。Owner 授权以已完成第一部分规则修复的 gw08-dual-env 为基准，合入诊断总结；在新会话由持续协调者组织 Terra high 并行调查、Astra high 集中分析，必要时由新 Terra high 做针对性补证。本次准备会话只合入文档、准备调查材料，不启动调查代理或测试。

## 1. 固定基准及首要变化

- 产品基准：`7469fbcb4afccf31bfc212f7609ca6ab2f2d45e5`，gw08-dual-env，包含第一部分业务规则修复。354 focused、五包静态通过的既有证据见[业务修复记录](/home/dev/gdds-stage-exchange/gw08-business-rules/stage-log.json)和同目录gate；全量runner、容器门禁及真实旅程仍按该记录为deferred，不把focused当阶段放行。
- 调查起点：`3b1dee0c565e7a327da87b655b45a3e4b476d142`，相对产品基准仅新增[历史诊断总结](preview-cross-stage-diagnostic-summary.md)。该提交由`f8bf194682082c0ba2c0c8bd2552e0ad671b6027` cherry-pick而来。后续本计划的文档提交不改变产品基准。
- 首轮bundle优化已在该祖先链：`c2670718fd`成员复用、`ff3355ea4e`内容匹配alias修正、`d06b8ce4a0`去插桩；bundle实现相对`c2bea74bb1548097a6d0aa074927f4f130b55d77`未改变。没有将临时观测提交合入产品，没有合并整条分支到main。
- 旧测量基于c2bea74：阶段诊断`0b0c1aec6ac3f60a0c69c941c611347be95f261b`、cache诊断`daa100a6da839f1858ec6e0e069943c954fa29d3`、跨阶段诊断`d23393b768c0afda0a5c693721f1a8c10940d539`。它们均不是修复后基准的性能样本。
- **必须重评risk候选：**新pair pipeline按完整before表集合传入empty_baseline；新risk engine为空baseline返回无annotations outcome，发布阶段对无annotations执行observer后跳过annotation artifact发布。旧第一pair的312对annotation与约22秒risk不能当作新版本仍有该工作量，更不能算作可优化收益。TABLE_ADDED等级、disabled app导航、risk model/ruleset、options/cache/checkpoint版本也已改变。空风险归属与comparison诊断仍需保留，不推断整个risk或presentation成本为零。

Owner仍在进行后续正确性修复。协调者启动时核一次增量；默认固定以上基准，不跟随移动HEAD、不并入进行中的修复。新完成修复若影响候选，单列适用性，协调者与Owner确认是否切换基准；无关包继续。不能用旧golden/真实产物的风险字段相等作为修复后验收预期，也不能为通过而扩大比较器忽略项。

## 2. 决策范围与授权

目标是覆盖Preview全链路的优化决策，不是每阶段重新profiling。每阶段最终有“继续设计/保持现状/当前证据不适用/待具体补证”的结论，选择一个优先局部方案，或明确停止。不以阶段耗时最大、报告最细或源码存在循环作为优先依据。

本阶段可做：固定源码只读分析、证据后处理；新隔离上下文的必要focused和受控局部成本核查，由协调者依据Astra明确问题单组织，使用专用节点、固定源码及现有合格输入/缓存。新增harness/临时观测必须隔离、明确diff并完成适用校验，不改变业务语义。

本阶段不做：产品优化实现、公共Contract变更、删除校验、扩资源、增加缓存机制、启用并行、部署或推送。**新增真实Preview额度为0**；前轮FULL已耗尽，新增MO/FULL或真实旅程须Owner单独确认输入、模式、次数和目的。局部补证授权不能扩成端到端基准、预热重复矩阵或系统调用级全栈profiling。若未授权真实运行而结论需要它，交付确切缺口，不声称已经验证。

现有N1、M24、32GiB worker envelope、8GiB reserve、单active及CPU配置保持。有界并行只作候选分析；规则、行数、计算成本和内存/所有权共同决定可行性，不据2 CPU自动启用N2，不恢复已暂缓双pair计划。

## 3. 角色与依赖

协调者使用Terra high，持续负责基准、授权、共享资源、证据适用性、阶段日志与汇总。允许直接子代理，禁止递归扩队。当前工具最多4个活动槽（含协调者），实际可用槽为准；同一时刻最多3名子代理。调查并行不等于测试节点可以并行跑多个任务。

所有分包用新上下文`fork_turns=none`，明确传入正式计划、COMMON.md、分包提示、固定SHA与工作区、输出路径及必要来源。调查/补证模型`gpt-6.1-terra`、reasoning_effort=`high`；集中分析`gpt-6-astra`、reasoning_effort=`high`。工具不支持指定模型或无可用槽时如实报告，不冒充模型或绕过角色；已完成独立材料可继续整理。

| 包 | 范围、输出和依赖 |
| --- | --- |
| P0 公共发布链路 | ArtifactStore端口/生产adapter/自定义adapter、put/read完整性、事务/保护/错误与取消语义。输出唯一公共保证表；不把LocalStore实现自动推广为port承诺。供P1–P4引用。 |
| P1 risk | 先核规则修复导致的路径变化，再核仍存在的annotation发布/验证及observer屏障。旧22秒候选可以被否决；不得为保持旧结论寻找替代理由。依赖P0公共语义。 |
| P2 materialize/canonical/export | staging/parse/business/projection/baseline粗覆盖，重点canonical与export的转换、lookup、manifest、登记、alias，区分实际冗余和必要逐表工作。依赖P0。 |
| P3 compare/presentation/cache | comparison planning/session/records、identity、presentation扫描与发布、comparison/risk cache分别出结论；规则修复对风险归属/导航/缓存影响单列。依赖P0，不强求共同方案。 |
| P4 bundle及其余链路 | 核首轮bundle优化仍在且适用；输入恢复、closure/READY、checkpoint/保护、publish及端到端轮询差额。重点确认已有优化不回退，其余阶段无充分理由不深入。依赖P0。 |
| A Astra集中分析 | 所有包与基准适用性表完成后，新上下文读取关键源码和原件，覆盖全部阶段。提出优先项、停止项、假说及最小补证需求；不是产品正式独审。 |
| T Terra补证（按需） | A每项未决问题由协调者确认授权与最小范围后，新上下文执行；不修改产品。结果回同一Astra复核，不重建另一套判断。 |

启动P0、P1、P2；完成后释放活动槽运行P3/P4。后两包也可在槽允许时提前，只读调查可并行，P0结论到达后统一收敛。共享接口疑点由P0统一处理；分包不得各写不同假设。已完成代理不驻场轮询。审核材料写入交接区，代理不改同一文件。源码调查在协调者建立的固定clean只读detached工作区进行；测试另用clean已提交测试树，不在被测树写入。

## 4. 证据与统一交付

交接根：`/home/dev/gdds-stage-exchange/gw08-preview-optimization-investigation/`，提示词在prompts/。必读历史证据：

- [阶段报告](/home/dev/gdds-stage-exchange/gw08-preview-materialize-assemble-diagnostic/REPORT.md)及同目录EVIDENCE-INDEX、TIMING-BOUNDARIES、ASTRA-ANALYSIS；后者文件名不证明模型身份。
- [cache报告](/home/dev/gdds-stage-exchange/gw08-preview-cache-commit-diagnostic/REPORT.md)及其索引。
- [跨阶段报告](/home/dev/gdds-stage-exchange/gw08-preview-cross-stage-diagnostic/REPORT.md)、[原件索引](/home/dev/gdds-stage-exchange/gw08-preview-cross-stage-diagnostic/EVIDENCE-INDEX.md)、[risk设计核查](/home/dev/gdds-stage-exchange/gw08-preview-cross-stage-diagnostic/RISK-PUBLICATION-DESIGN-CHECK.md)。
- [首轮bundle总结](preview-optimization-exit-summary.md)及其交接区的原件/审核；旧跨阶段和materialize计划只作历史范围，不继承受理额度。

每包统一格式：结论→固定源码和证据→当前必要/可减少工作→保持现状及最小候选比较→适用性和未知→补证分岔/停止条件。至少列出：现行路径、旧测量绑定SHA/模式/输入、适用/失效/未知理由、实际可减少操作、MO/FULL覆盖、错误和保护屏障、风险/改动面、最小验证与收益未知。需要变更owning Contract时只指出，不在调查中实施。

新基准适用性优先于历史排序。区分直接测量、算术余量、源码推导、假设；不将不同样本子项拼成同次账。旧312 annotation、239KB、FULL195.723秒只用于解释旧版本。表行数不足以预测成本；top10不代表完整分布，受污染risk条目排除，partial利用率不作资源瓶颈证据。已有CPU/内存cgroup限额证据不能补写前轮缺失，也不证明利用率完整。

只计算有依据的工作量和条件性上界，不给未经验证的稳定节省承诺。每个阶段至少有一行处置；不为凑全覆盖重复原已完成的诊断。基础root/symlink、exact-ref、事务/CAS、跨scope、预算与取消不能忽略；遵守ADR0012单信任域，不构造额外恶意同euid威胁。

## 5. 集中分析及补证

协调者先整理BASELINE-APPLICABILITY.md、全部包输出和CANDIDATE-MATRIX.md，不替原始失败作成功摘要；随后Astra完整分析，独立核关键源码/引用，拒绝不适用的旧样本结论。按当前可减少工作、覆盖、风险、复杂度排序，允许“现有数据无法排序”。

若需补证，每项必须写：要决定什么、为何既有证据不能回答、最小输入/边界/次数、不同结果如何改变继续/停止、固定条件、原件保护、停止条件。优先已有日志/产物只读核查，再局部focused/成本核查；不把局部harness时间线性外推完整Preview收益。新规则改变业务预期时用现行Contract/golden证明，不强制与旧风险产物相等。

协调者据上述问题单派新Terra high，锁定具体命令/源码/节点/输出，遵守[测试规范](testing-conventions.md)的占用、缓存和执行入口。禁止在开发主机运行测试/编译/lint/取证。记录执行唯一责任人；短focused由执行者收尾，长测按现行规则把进程、日志及资源责任明确移交持续协调者，不能双方同时负责或创建监视agent。不重测仅为统计好看；环境修复遵循现行规则、有具体修正可重跑失败步骤，产品失败回正常finding，不将失败runner续接为成功。

补证集中完成后交原Astra复核相关结论。无新的决定性问题不递归扩调查；若仍需越权真实测量或修改业务，交付未决问题供Owner决定。不能用预设“必须找到优化”推动无限循环。

## 6. 收敛与停止

协调者核收REPORT.md、CANDIDATE-MATRIX.md、ASTRA-ANALYSIS.md、BASELINE-APPLICABILITY.md、EVIDENCE-INDEX.md及追加式STAGE-LOG.md；测试如有，单独索引原始成功/失败及未知。最终一页总结按正式流程入库，工作包/提示词/运行材料留交接区。

停止于：推荐一个有明确方案边界和最小验证要求的候选；或指出具体缺口并停止受限工作；或建议停止优化投入。未选方向不自动移交后续阶段。本次不实施、不合并产品、不部署、不推送，不以Astra调查结论宣称正式独审/阶段验收通过。保留仍有消费者的工作区与原件；只收尾本人资源，不清其他会话工作区。

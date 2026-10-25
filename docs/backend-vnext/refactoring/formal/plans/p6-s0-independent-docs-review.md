# Phase 6 S0 独立文档审核

- 结论：**定向修订**
- 日期：2026-10-25（UTC）
- 审核对象：main @ `fc109806bb714bf004fa4ffd7b043941e834fa4e`，本地、未推送；`p6-design.md` r1、`p6-execution-plan.md` r1、`p6-s0-owner-decisions.md` DC37–DC54、`implementation-stages.md` §2、§9、§10。
- 审核形态：S0 文档快照审核，不是实现阶段退出审核；无本轮门禁提交 V。开发机在 `/home/dev/gdds-p6-s0-review` detached worktree 阅读，被审文件未修改。
- 依据：[P5 执行计划 §8.8](p5-arch-closure-execution-plan.md)、[AGENTS](../../../../../AGENTS.md)、P5 DC35/DC36、P6 DC37–DC54、讨论稿 r29、V5/V5b/V6/V7/V8/V1 报告，以及设计开头引用的 Contract、ADR 与比例化/Rust 策略。决议优先于讨论稿和原型建议。
- 下文源码前缀：B=`vnext/backend/src/gateway_backend/`，SK=`vnext/shared_kernel/src/gateway_shared_kernel/`，RS=`vnext/repository_service/src/gateway_repository_service/`；位置均以被审提交为准。

## 1. 结论摘要

总体方向与 Phase 6/7 边界成立，先改语义、再替换数据路径的阶段划分可保留，不需整体返工。发现 **8 项阻塞、2 项非阻塞建议**；阻塞主要是摘要冻结要求自相矛盾、内容缓存身份不完整、冻结产物恢复边界、零日期跨服务语义，以及计数和测量验收未闭合。原型支持 Rust 解析、ordered 比较与有限并发读取的方向，但没有证明 W2/W4 的端到端目标；报告明确保留这些证据边界。

当前不能据此打 S0 exit tag 或授权 S1a 实施。由作者修订、owner 处理涉及决议本身的冲突后定向复审；本报告不修改决议、不代替实现授权。

## 2. Findings

### P6-S0-F1：S1a 的 ordered 摘要变更与 bundle digest 冻结不可同时满足

- 类型：**已证实缺陷**；是否阻塞：**是**。
- 位置：`p6-design.md:127`、`:131`、`:160`、`:276`；`p6-execution-plan.md:56`、`:103`；DC39 第 3、5 项及 DC50 第 1 项。
- 依据：B`capabilities/comparison/ordered.py:746` 的 `_ordered_digest` 包含表名、policy version 和 ordered logical rows，不是 `raw_content_digest`。B`capabilities/comparison/row_encoding.py:633` 将两侧 ordered digest 纳入 facts；B`capabilities/comparison/standard.py` 的 `_build_facts` 再将 facts core 纳入 comparison digest；B`capabilities/bundle_assembly/_digest.py:65` 将 comparison digest 纳入 bundle digest。surface 也保留这些 ordered 字段。Ordered Diff「Digest」明确 v2 final digest 含表名且排除 ignored columns。
- 触发场景与影响：任何带 ordered 表的既有结果，把两侧逻辑摘要改成全规范表摘要并去掉表名，即使行值不变，comparison/surface/bundle digest 也会变化。因此 S1a “只有 manifest 及其传播值改变、bundle digest 不变”的验收不能通过；随后 S1b 再改 comparison/risk/surface/bundle，会使“每类 golden 只改一次”失去可执行含义。
- 最小修正方向：请 owner 明确 DC39 第 3 与第 5 项的取舍，作者据此统一摘要传播和冻结清单。把 Ordered Diff 的逻辑摘要定义修订列入 owning Contract 清单，不能只修伪 gid 范围。明确 golden 的分组/更新时间；S3 的分歧点应在基准冻结前定稿，或明确只补充已冻结的解释、不改语义。不要用兼容摘要掩盖矛盾。
- 关闭标准：设计、决议和计划使用同一份“允许变化/必须保值”的摘要表；明确 ordered → facts → surface/bundle 的传播；每组 golden 有唯一更新节点；S1a 验收可满足且 S1b 后的基准不再被未授权语义变更推翻。

### P6-S0-F2：把内容摘要当作完整表身份，会误命中导出缓存并漏判 schema 变化

- 类型：**已证实缺陷**；是否阻塞：**是**。
- 位置：`p6-design.md:184`、`:291`；DC41 第 2 项；对照设计 §4.2、§8.2。
- 依据：B`capabilities/snapshot_materialization/_digest.py:105` 的 `raw_content_digest_of` 只合并 row hashes；零行时没有 schema 输入。Snapshot Table Access「Snapshot Table Artifact Cache」现有 `row_layout_digest` 明确组合 raw content 与 export schema，并限制 repository scope。规范状态身份本来就另外包含 business schema digest（ADR 0019 第 5 项）。
- 触发场景与影响：两个空表分别有不同列或类型，内容摘要相同；按“表摘要 + writer 版本”缓存 Parquet 会复用错误 schema。History 按 §11 的“表摘要相同 → 未变化”也会把空表减列/改类型判成 UNCHANGED，漏掉 DC40 要保留的 schema 风险；非空表仅改变可空性等 schema 元数据也有同类问题。
- 最小修正方向：区分“行内容摘要”与“导出/比较输入身份”。导出键至少覆盖规范 export schema、内容和 writer/映射语义，并说明 repository scope、规范行序与闭包绑定；可复用现有 row-layout 身份，不另建证明机制。History 应复用 §4.2 的完整等价条件，而非仅比 raw hash。DC41 的短键措辞需由 owner 澄清。
- 关闭标准：文档可明确推导出“内容相同但 schema 不同不得误命中/误判”；安排空表不同 schema、同内容可空性变化和同 schema 同内容复用的一个权威测试 owner；表名去重不丢失当前表/节点的绑定。

### P6-S0-F3：未提交的 T1 冻结规范表不能一律由 Dolt 回填

- 类型：**已证实缺陷**；是否阻塞：**是**。
- 位置：`p6-design.md:117`、`:252`、`:254`、`:257`；DC42 第 2、5 项及其比例化说明。
- 依据：Canonical Storage §5 要求 Submit 从 exact Preview-bound SnapshotTableArtifact 开始，不重新解析 SQL；ADR 0019 第 6 项要求 T1 后只使用冻结产物、不依赖运行期 ruleset。当前 B`infrastructure/repository_write/import_publication.py` 从冻结闭包读 MODIFIED 数据，而该目标内容在导入前尚不存在于任何 Dolt commit。
- 触发场景与影响：T1 已接受、prepare 尚未构建导入包，上传侧变化表的 IPC 缺失或损坏。Dolt 只有旧 parent，无法重建新内容；无条件“从 Dolt 读取并重写、只影响性能”没有可用来源。若误用 parent 回填会污染提交；即使正确拒绝，也已经影响 operation 成功而不只是性能。
- 最小修正方向：保留一个内容存储，但分清角色：已提交表的派生副本可由精确 commit 回填；T1 冻结的未提交产物按现有保护和稳定失败规则处理。明确 T1 前可从 SourcePackage 重算、T1 后不得静默换输入，以及 PREPARED 后复用已冻结导入包的边界。补明 DC45 的 parent 行按 parent manifest 校验、expected-parent CAS；不增加条件 DML、sidecar 或新的恢复状态机。
- 关闭标准：设计列出缺失/损坏在 T1 前、T1 后 prepare 前、PREPARED 后、已提交缓存四种状态的来源与终态；无法回填时稳定失败且不移动 main；现有事务/CAS/冻结恢复测试明确承接这些语义屏障。

### P6-S0-F4：接受零日期的提案漏掉 Repository Arrow 边界和 Shared Kernel 实现面

- 类型：**已证实缺陷**；是否阻塞：**是**。
- 位置：`p6-design.md:205`–`:214`、`:225`、`:247`、`:312`；`p6-execution-plan.md:132`。
- 依据：Shared Canonical Encoding §2/标量规则将 zero/incomplete date 限为 owner 允许的 anomaly 或 hard failure；SK`scalar.py:639` 拒绝 year/month/day 为零，`:667`、`:679` 的日期规范化调用它。Repository Service Contract §10 固定 DATE=`date32`、DATETIME=`timestamp[us]`；RS`arrow_mapping.py:472`、`:484` 通过 `date.fromisoformat` / `datetime.fromisoformat` 转换，不能表示零日期。此外 FLOAT 两次舍入的真实实现位于 SK`scalar.py:431`，不在计划所列 backend parser 路径内。
- 触发场景与影响：解析器接受 `0000-00-00` 后，现行物化/编码仍拒绝；即使只修上传侧，提交后清空表缓存的 History/Dolt 回读仍不能按现行 Arrow Contract 返回该值。因此“Repository Service 无 Contract 变化”不能与该提案同时直接接受；t1–t4 没有这类值，零差异不能证明它可往返。
- 最小修正方向：owner 选择继续稳定拒绝、使用既有 anomaly 语义，或完整支持；若支持，先定义规范标量/存储类型/SQL 渲染/RS Arrow/客户端解码的闭环，并列出相应 owner、版本和 golden。将 shared_kernel 源码、测试及共享编码 golden 纳入 S1b 路径预算；不得只加 Utf8 类别绕过 typed scalar 约束。
- 关闭标准：S1b 的零日期目标形态及完整往返路径已定稿，RS 是否修约不再自相矛盾；FLOAT 修复由真实 owner 承担；对新增接受的值安排合成往返验证，且语义/golden 在重建基准前冻结。

### P6-S0-F5：结构性计数与 SQL 字节验收的口径互相冲突

- 类型：**已证实缺陷**；是否阻塞：**是**。
- 位置：`p6-design.md:138`、`:148`、`:283`–`:286`、`:356`–`:359`；`p6-execution-plan.md:53`、`:111`；DC45 第 2、7 项。
- 依据：现有 B`capabilities/mutation_planning/_repository_replay_renderer.py:154`–`:210` 已将 INSERT 批成一条语句（最多 256 行），因此 SQL statement 数不等于逻辑变化行数。Storage Mutation §4 又区分同 key UPDATE 一次、key 变化 DELETE+INSERT 两次。设计允许 S4 定稿阈值和调整 batching，却要求 replay.sql 与 S1a 逐字节一致。
- 触发场景与影响：同一表新增两行，当前 renderer 可产生一条 INSERT，即违反“语句数=变化行数”；S4 改阈值导致 patch/rebuild 路由变化或改 batch 边界，也会改变 SQL bytes 而业务结果正确。比较次数还会被 S3 单次去重、S5 缓存命中减少；新表没有可读取的 before，删除表与新增表也不能都混入同一个未定义的“变化表数”。按现文本既可能误拒绝正确优化，也可能用计数解释掩盖多读。
- 最小修正方向：请 owner 澄清 DC45 的计数语义，区分逻辑变更行/物理 mutation/SQL statement、请求表数/实际读取表数/去重后 kernel 调用数。给出新增、删除、修改、未变集合的定义和公式。确定 S4 是冻结路由与 batch 后逐字节回归，还是先完成获批的语义/渲染修订再冻结，不能同时开放阈值又要求原始 SQL 不变。
- 关闭标准：用“两行批量 INSERT、key 变化、仅新增表、仅删表、两个同内容任务、缓存命中”即可无歧义手算验收计数；指定观测点，区分业务 logical dispatch 与实际 kernel/RS 调用；S1a/S4 的字节验收及 golden 生命周期一致。

### P6-S0-F6：W2/W4 仍缺少把已知固定成本与 Python consumer 纳入的端到端预算

- 类型：**待验证假设**；是否阻塞：**是**（阻塞无条件接受当前可行性说明，不要求在 S0 提前完成性能实现）。
- 位置：`p6-design.md:151`–`:158`、`:273`–`:277`、§16、§17；`p6-execution-plan.md:96`、`:104`；DC53、DC54。
- 依据：DC53 自身估算 W2 计算部分约 30–35 s，已贴近/超过 30 s，另有 step 间隔与约 175 s 残差；V5/V5b 没有证明这些全部可消除。V1 测的是 changed ordered kernel，排除了 IPC 和输出编码。W4 两侧都存在，DC41 不会移除其逐行 records。当前 B`capabilities/risk_evaluation/_facts.py:31`、`:101` 保留 `tuple[ComparisonRecord, ...]`，`_engine.py:277`、`:326` 逐条消费；比较产出 Arrow 后，风险仍需明确消费接口。B`capabilities/comparison/artifacts.py:279`、`:483` 存在读取校验与发布后校验两条路径，删除一条不等于消除全部 Python 解码。
- 触发场景与影响：S1a 只完成“解释来源”但没有确定消除/缩短方案，S2b 把 W2 写成“测量”而非目标可达性的检查点，就可一路推进到 S6 才发现固定成本超预算。S3 若为现有风险输入重建所有 Python records，或每次打开 closure 又全量 `to_pylist`，DC54 的收益估算会漏计对象重建和校验；反之仅传小 facts 会失去逐行/ordered 风险依据。
- 最小修正方向：补一张粗粒度预算表，区分实测、外推与待归因；列出受理、上传数据路径、基线读取、比较、records 发布/读取校验、Python 风险、bundle、step 间隔。S1a handoff 给出残差 owner 和处理节点；S2b 若 W2 的剩余成本已不能在 30 s 内闭合，按 DC53 提交 owner 决策。明确 Arrow records 到 Python 风险的有界接口及预算，S3 用 W4 实测判断是否按 DC47 重开风险热点范围。
- 关闭标准：设计能说明 W2 除“查清原因”外还依赖哪些削减及何时判停；W4 每段不存在未计入的必经逐行 Python 转换/回读；不把原型吞吐冒充生产端到端结果，也不因预算不足自动放宽数值或搬迁全部风险规则。

### P6-S0-F7：验收矩阵遗漏 FULL/三节点场景，并把 H1 缓存例外写成无条件零计算

- 类型：**已证实缺陷**；是否阻塞：**是**。
- 位置：`p6-design.md:40`–`:48`、§11、§16；`p6-execution-plan.md` S5/S6。
- 依据：DC35 第 2、3、8 项及 DC53 第 1 项要求 READY/完成双指标、W3/W4 各一次 FULL 补测、范围报告；DC38 第 1 项要求三节点 H2 条件下补测一次（只报告、10 min 硬上限），第 4 项明确 FULL Preview 后首次 History 不命中 diff/risk、允许重算。
- 触发场景与影响：照计划只跑 W1–W4、H1–H3 名称清单可以漏掉双侧双 pair 与三节点旅程，却声称最终验收完整；FULL Submit 后 H1 按无条件“比较次数=0”验收则会拒绝 owner 已接受的行为。TTL 内但文件已缺失/损坏也应走回填，不能与健康命中场景混为同一零读断言。
- 最小修正方向：在 runbook/验收矩阵明确模式、节点数量、缓存健康及 TTL 条件、READY/terminal 时点、样本和范围、FULL 例外、100% 行变化压力档只报告的范围。H1 的零比较限定为已计算该 pair、规则相同、健康缓存命中；缺失/损坏作为正确性 fallback 场景。S6 明列最终完整 runner/容器门禁，避免只引用指标表；S2a 前置明确包含“重建基准完成”，而不只写 S1b exit。
- 关闭标准：逐项映射 DC35/DC38/DC53，每个必测场景都有阶段、可判定结果和门槛/只报告标记；FULL H1 与普通 H1 不再冲突；无需猜测“全部负载”包含哪些变体。

### P6-S0-F8：缓存和生产 mutation 的 Contract 修订清单未覆盖现行明确限制

- 类型：**已证实缺陷**；是否阻塞：**是**。
- 位置：`p6-design.md` §4.5、§8.4、§9、§11、§14；`p6-execution-plan.md` S3/S5 及 §3。
- 依据：Comparison「Cache」明确第一版为 pair-level、不得做 table-level facts cache；DC43 明确改为纯函数单表比较和“未套用 pair 上限”的风险缓存，并要求写入 Comparison/Risk。设计只列缓存实现和概括性 owner，S3/S5 没有对应修约落点。Snapshot Table Access 还规定 Parquet artifact、row-layout/schema/scope 和可信等级，不能仅在 S1b 将它列为“解析语义说明”。ADR 0014 与 Storage Mutation 现行文本包含条件 DML/affected-row/readback 要求，而 DC45 第 6 项规定生产 Repository 路径以 expected-parent CAS、parent manifest 校验和受信 Repository 为前提，不另加条件 DML/提交后读回。
- 触发场景与影响：按当前列表只改 Canonical Storage 存储格式、Comparison schema 演进和阈值，S3/S5 将实现 Contract 明文禁止的 table-level cache；实现者也可能沿通用外部 ChangeSet 要求给生产 replay 增加已被决议排除的机制，或遗漏 parent 输入验证。缓存若把 pair 截断结果当单表结果复用，会在不同 pair 下漏报风险。
- 最小修正方向：补“现行条款 → 目标条款 → owner → 阶段 → golden/测试”清单：Comparison/Risk 的纯函数输入/结果、pair 限额后绑定、scope、命中后 operation closure；Snapshot Table Access 的新旧 artifact/cache 边界；ADR 0014/Storage Mutation 中生产 Dolt 路径与保留的通用外部目标要求。完整输入摘要应包含规则和版本，不能把表名删除后剩余的任意旧请求对象直接当作已证明的纯函数键。
- 关闭标准：读者能从清单定位上述现行限制的修订节点；S3/S5 无需临时改 Contract 才能实现；风险规则变化和 pair 上限变化的缓存行为明确；保留 CAS/事务和跨 scope 边界，不引入新 evidence/helper 机制。

### P6-S0-F9：测试归属与资源失败边界需要细化，但不应扩成测试矩阵

- 类型：**非阻塞建议**；是否阻塞：**否**。
- 位置：`p6-design.md` §8.3、§11、§15；`implementation-stages.md:684`。
- 依据：比例化策略 §6.2 的一个不变量一个权威 owner；DC35/DC47 的 N/M、取消与 deadline；Rust policy §3 不允许把 native abort/allocator termination 伪装成普通诊断。
- 触发场景与影响：§15 把 Submit 跳过、阈值和 parent 绑定一行同时交给 planning、prepare、Compose，实施时容易三层重复矩阵；规范表保护转移、finalize 同事务绑定、503 重试终止、native crash 接管没有明确承接点。
- 最小修正方向：拆分该行的不变量，分别标明唯一断言 owner 和其他层 smoke；引用已有 runtime/CAS/cleanup 测试，不新建平行框架。RS 读取并发明确受 N 与 RS 容量共同限制，重试继承取消/deadline；M 估算包含常驻输入、结果及并行临时内存，不能仅按活动表的平均列宽解释峰值；所有长 kernel 复用取消和失败边界。
- 关闭标准：实施 kickoff 前给出少量具名测试 owner；区分“预算拒绝可诊断”与“native crash 由 runtime 恢复”，不要求穷举 syscall 窗口。

### P6-S0-F10：若干代码事实与交叉引用需校正

- 类型：**非阻塞建议**；是否阻塞：**否**。
- 位置：`p6-design.md:11`、`:86`、`:91`、`:155`、`:254`、`:274`；`p6-s0-owner-decisions.md` DC54 第 3 项；执行计划 §3。
- 依据：B`infrastructure/repository_write/import_publication.py:389` 在 storage_projection 外传递 `ordering_digest`；没有发现该字段在外部参与业务分支，但“只在内部”字面不实。RS`settings.py:72` 的 8 是可配置默认值。V5 step 表中重传第一处间隔为 1.007 s，并非每个 Preview 两处都 7–10 s。DC42 详情没有第 9 项；当前 P6 设计也没有 §4.6。讨论稿头部保留 r28 状态，同时追加了 r29 说明，版本标记需统一。
- 触发场景与影响：删除字段时漏掉 frozen import 传递点；实现者找不到闭包权威定义或误解 503 容量；归因从错误的固定间隔假设出发。
- 最小修正方向：改为“无独立外部语义 consumer，但存在跨模块传递”；明确 RS 默认/有效容量；保留 V5 各负载间隔实际差异；把“设计 §4.6”链接到真正的 P5 收口设计；DC42 回读引用改为实际条目；更新讨论稿版本。S2a 路径预算补列 `check-rust-extension-build-input.sh`、依赖/架构检查与 import_rules 对新 adapter 的一致性核对（已声明验收，不要求一定改每个文件）。
- 关闭标准：引用可定位且数字不再被概括为普遍事实；删除清单可覆盖实际引用者，新扩展的 build-input 检查与 runner 排除同步核对。

## 3. 验收核对

### 3.1 S0 与决议落实

| 验收项（执行计划 §2 S0 及审核重点） | 结果 | 证据 |
| --- | --- | --- |
| 独立、只读审核指定快照 | 已完成 | detached @ `fc109806bb`；四份被审文档未修改；报告单独提交 |
| DC37、implementation-stages §2/§9/§10 | 基本一致 | Phase 6 单 operation，Phase 7 K/公平调度/共享瓶颈；退出删除生产 flag；没有恢复 accepted-baseline 状态机 |
| DC38、DC53 目标数值 | 数值一致，验收未闭合 | F6/F7；H2 仍草案，不能把 V7 热读宣称为冷读通过 |
| DC39、DC40、DC41 | 需修订 | F1/F2；只增列、ENUM/SET 扩展、减列风险和整表浏览方向落实；需处理摘要及完整表身份 |
| DC42、DC43 | 需修订 | F3/F8；复用保护表/TTL/原子写合理，冻结新数据不能泛化为 Dolt cache |
| DC44、DC46、DC47、DC54 | 有可信技术方向，边界待补 | V6/V1；F4/F6/F8/F9；Rust core 不写文件、Arrow 粗粒度传输、单 worker 共享池合理 |
| DC45 | 需修订验收和安全前提的落点 | F3/F5/F8；保留通用 planner，生产不复用 frontend diff 的方向正确 |
| DC48、DC51、DC52 | 基本落实 | runner 六包、强制重装/build-input；S2a 删除旧扩展和排除、镜像切换、架构基线；保留门禁 worktree；重新剖析门禁不构成当前 blocker |
| DC49 | 方向合理 | 空闲 60 s + 最大压缩包/1 Mbps 总上限、同步受理下沉；上传传输不计 operation 指标，准入名额归 P7 |
| DC50 阶段顺序/基准/每类 golden 一次 | 主顺序正确，局部约束冲突 | F1/F5/F7；S1a→S1b→基准→S2a→S2b→S3→S4→S5→S6 保留 |
| Contract/ADR/DTO/checkpoint/schema 清单 | 不完整 | F1/F4/F8；control DB 直接改基线、不加迁移符合 AGENTS；HTTP 错误码/展示变化、prepare parent 绑定已列 |
| 比例化保障与基础边界 | 未发现无依据的新治理机制；需补冻结边界 | F3/F8/F9；不要求 broker、持久 evidence、恶意同 euid 防护或提交后全量回读 |
| kickoff 小修、keyless 自然键评估 | 仍为后续前置 | 本轮不执行产品修复、不代 owner 进行业务决策 |
| S0 接受与实现授权 | 未满足 | 8 项阻塞须定向修订、复审和 owner 接受 |

### 3.2 设计 §2.2 的十条代码事实亲自核对

| # | 源码证据 | 判断与限定 |
| --- | --- | --- |
| 1 Submit 全量重写 | B`capabilities/mutation_planning/import_replay.py:86`–`:120` 构造空 before + REBUILD_ALWAYS；B`capabilities/storage_projection/import_replay.py:58`、`:103` 对全部 import tables DROP/CREATE | 已确认，针对实际进入 Submit prepare 的操作；原样无变化在受理处阻断不产生 Repository operation |
| 2 Preview 全量基线 | B`application/preview_jobs.py:1178`–`:1214`；B`capabilities/snapshot_materialization/repository_ref.py:180` 起获取 catalog、遍历 selected_names | 已确认，没有按变化表传入选择集；INITIAL 仍须为空 catalog |
| 3 ordered 不提前退出 | B`capabilities/comparison/standard.py:185` 起先 dispatch ordered，再走普通表 early-exit | 已确认其 ordered 行比较路径；BROWSE_ONLY/SNAPSHOT_ONLY 有前置分支，不宜表述为所有角色无例外 |
| 4 摘要 | B`capabilities/storage_projection/_digest.py:50`、`:91`、`:99`；`project.py` 的 keyed/ordered/keyless 投影；B`capabilities/snapshot_materialization/_digest.py:98`、`:105`、`:179`；全源码搜索 `ordering_digest` | manifest 的普通内容计算具有顺序依赖（keyless 已排序，不是所有表都依赖源顺序）；raw content 是无序 row-hash 摘要；fast-row 进入 snapshot；ordering 的外部传递见 F10 |
| 5 标准 bundle | B`application/pair_pipeline.py:291` 在 DATASET_REPLACEMENT 才提供 table_artifacts | 已确认，标准模式传空元组 |
| 6 Python records | B`capabilities/comparison/artifacts.py:435`、`:483`、`:518`、`:618` | 已确认逐条字典/JCS、from_pylist、写后读回/to_pylist；读取侧另有完整校验 |
| 7 上传时限/受理 | B`application/workspace/upload_limits.py:11`；B`http/orchestration/multipart_stream.py:232`；`multipart_upload.py:40`–`:68`、`:177`；B`http/routes/upload_revisions.py:81` | 已确认 60 s 总 deadline、超时转 UploadLimitExceeded/413；async 受理直接调用同步 helper/accept_upload，无线程下沉 |
| 8 parser 缺陷 | B`capabilities/table_access/_sql_values.py:114`、`:245`、`:345`；`sql.py:30`–`:60`；SK`scalar.py:431`–`:461` | 静态确认 to_bytes/ASCII decode/深层 json 异常未被对应 catch 包住；FLOAT 先 float 后 pack；未在本轮重跑反例，V6 动态结果是来源报告证据 |
| 9 RS 许可池 | RS`settings.py:72`；RS`versioned_read/http_service.py:105`–`:125` | 默认 8，try_acquire 失败立即 503；defunct 的观察只来自 V7，本轮未复现，根因不明 |
| 10 Rust 状态 | Rust core `lib.rs` 导出 table_access/comparison 原型；旧 adapter 只导出 canonical-row-hash；全 B 搜索其调用；`run-tests.sh:63`、`:245` 及 build-input 脚本 | 未见原型生产接线或旧 hash 能力的外部生产 caller；runner 已纳入 rust、排除两个旧 adapter crate 的 cargo test、重装扩展并核对构建输入；uv 缓存行为的动态证明引用 DC48，不冒充本轮实测 |

### 3.3 目标可行性与开放项意见

| 项目 | 审核意见 |
| --- | --- |
| W1 | 合并上传路径 + 整表新增表级浏览/风险可去掉 V5b 的大量逐行成本，方向可信；新增全表 Parquet 导出成本须计入，原型不能直接证明 ≤180 s |
| W2 | 风险最高。即便过滤做到零基线读取/比较，上传解析投影、bundle、受理及 step 成本仍存在；依 F6 设置 S1a 归因、S2b 预算检查，不接受直接宣布 ≤30 s 可达 |
| W3 | V1 显示 changed ordered 比较可显著缩短，但与 2× 生产路径并非同口径；需完整数据路径/固定成本闭合，FULL 另测 |
| W4 | Rust records 必要且合理；DC41 对“两侧都存在”的大量变化记录无减免。Python 风险与读取校验是剩余 consumer，依 F6 定接口和预算；100% 压力档不能当作 10% 门槛样本 |
| S1–S4 | 表级跳过、1% 路由和渲染直通有可信路径。V7 mixed 约 4.45 s 为模型，不是完整混合 Submit；需实测产品 renderer，且 0.1323%/100% 两端样本不足以确认精确交叉点。提交完成必须包含 main 前移 |
| H1/H3 | 健康的表/导出/diff/risk 缓存提供路径，但必须补 FULL 例外、规则与 scope 键、pair 限额重绑定；H3 还需要全量 bundle 命中成本预算 |
| H2 | 保留 ≤300 s 草案合理。V7 的一个热 t4 commit、8 并发约 26.7 s 只作参考，不替代两个历史节点 2× t4 的派生缓存全 miss 旅程；三节点补测不可漏 |
| 删除 ordering_digest | 原则同意：没有独立外部语义用途。删除全部字段传递与校验；不得与 comparison ordered logical digest 混为一个保值改动（F1/F10） |
| 保留 fast_row_digest | 同意 S1a 保留；反对把 S2b 删除当普通优化。它进入 snapshot 身份，若确要删除须重开 owner/Contract/基准决定，不能破坏 DC50 的冻结承诺 |
| 上传超时错误码 | `UPLOAD_STREAM_TIMEOUT` / 408 作为提案合理；两种 timeout 可共享码并附有界原因。413 留给大小/资源限制；继续保留解压预算、断连释放和线程池操作的完成/取消边界 |
| parser 六项语义提案 | BIT 十进制、_binary、转义保留、类型注释、拒绝 JSON 非有限数可按既定 S1b owner 流程定稿，不能以“Rust 与旧实现不同”为由在 S2a 临时改参照；零日期须先关闭 F4。另两类修复（异常边界与 FLOAT）有直接源码依据。深 JSON 不应写成“与 V6 原型一样返回诊断”：V6 报告说原型迭代接受，需明确选择有界拒绝还是接受；JSON 孤立代理策略一并定稿 |
| Arrow 映射 v1 | 原生整数/浮点/BIT、DECIMAL 文本总体合理；需写清 NULL、字段 metadata、SET 文本与成员序列互转、零日期形态、>2 GiB offsets 的统一规则。它是 backend 内部映射，不可冒充现行 RS wire mapping；无 first-party unsafe 例外 |
| 删除 records 写后回读 | 同意消除发布后重复全量解码；保留实际读取的 raw/content/schema 校验和普通 I/O 失败处理。需区分各回读点并避免为 Python 风险重建相同成本，不要求新增 evidence 状态机 |
| 上传原始表 consumer 核对 | 必要；不能仅删除 Parquet writer。核对 materialize/assemble checkpoint、FULL 双侧、composite、bundle、T1、恢复的读取者；未完成前不得进入 S2b 切换 |
| 磁盘与 N/M | S2b 前完成容量估算合理；应含 head、active Preview/Attempt、TTL 旧表、导出副本和临时高水位，不能只按两份 IPC 相加；N 暂定可用 V6 的 4，但按完整路径重测，M 含常驻和输出，不引入容量淘汰系统 |
| keyless 自然键 | 保持业务评估前置；若改变语义，在 S1a/S1b 与基准之前定稿，不在 S3 用性能理由补键 |

## 4. 实际执行的检查

| 检查 | 命令/方法 | 结果 |
| --- | --- | --- |
| 主 checkout 与被审提交 | `git status --short`、`git rev-parse HEAD` | 初始 main clean，HEAD 为 `fc109806bb714bf004fa4ffd7b043941e834fa4e` |
| 独立 worktree | `git worktree add --detach /home/dev/gdds-p6-s0-review fc109806bb` | 成功；开发机只读文档/源码，不运行产品、pytest 或测量 |
| 文档/Contract/源码核对 | `rg`、`rg --files`、`sed -n`、`nl -ba`；沿调用和摘要传播链阅读 | 十条事实复核见 §3.2；未仅按前置报告复制结论；无修改被审文件 |
| 调试节点 preflight | `ssh -o BatchMode=yes ct108-gw-dms-05 'echo OK'`；hostname、HEAD/status、`pgrep -af` 与 `docker ps` | 连接正常；hostname=`gw-dms-test-05`；无测试/编译/Dolt/测量任务，无运行容器；进程输出只有本次检查 shell |
| 只读快照同步 | 本地 `git bundle create`，scp，05 上 fetch bundle 并 `git worktree add --detach /home/dev/gdds-p6-s0-review fc109806bb`，添加 legacy 链接 | 不经 GitHub、不移动节点 main；05 的检查工作区也是相同 clean 提交 |
| 五包提交前静态检查 | 在 05 各包执行 `../scripts/uv-consume.sh -C . run ruff check .` 与 `../scripts/uv-consume.sh -C . run mypy` | 全部通过；mypy 文件数 shared_kernel=34、repository_contracts=15、repository_client=26、backend=486、repository_service=200；无锁文件漂移 |
| 静态检查 provenance | 节点日志 `/home/dev/gdds-p6-s0-review-static.log` | 2026-10-25T23:30:59Z–23:31:52Z；起止 HEAD 均 `fc109806bb714bf004fa4ffd7b043941e834fa4e`；exit=0；结束 tracked worktree clean。TMPDIR=`/home/dev/gdds-test-tmp`，LC_ALL=`C.UTF-8`，umask=022，root SSH |
| 测试/门禁/测量 | 未执行 pytest、权威 runner、Compose、真实数据旅程或性能测量 | 此为文档审核；静态检查不是本轮正确性或性能门禁 |

## 5. 验证限制与剩余前置

- 本轮依据源码证明控制流、数据身份和 Contract 冲突，未动态重现所有错误分支。V1/V5/V5b/V6/V7/V8 数字按其报告中的输入、冷热、阶段与局限引用；没有登录参考节点重读私有真实数据日志，也不声称重新验证了这些测量。没有真实数据进入 Git。
- 镜像记录：当前被审 HEAD=`fc109806bb714bf004fa4ffd7b043941e834fa4e`；本轮不触发重建（仅新增审核报告，无代码、依赖或容器边界变化）；最后验证的 image revision/source-tree **本轮未核验，不作 carried 声明**。下一实施阶段按 AGENTS/DC50 在其最终候选上建立门禁证据，不能引用本报告作为当前 HEAD 的容器通过结果。
- 未运行 Rust fmt/clippy/test：本轮无 Rust 改动；05 上 uv 为静态检查安装依赖时构建了既有扩展，这不构成新扩展的差分/构建输入验收。S2a 必须对新 adapter 同步完成构建输入检查、pytest 解释器测试、旧 crate 排除删除、镜像和 import_rules 基线核对。
- 开放项仍须 owner 确认。特别是 F1/F2/F5 揭示决议短句之间或与完整 Contract 的冲突，作者不能仅改设计而把原决议保留成另一个相反验收口径；F4 不能仅以“t1–t4 不含该值”关闭。
- 进入实施前：关闭 F1–F8、完成定向复审、给出 keyless 自然键评估与实现授权。S2b 前完成原始表 consumer 和磁盘核对；其后依据完整路径实测确认 W2/W4 和 H2，不提前承诺达标，不默默放宽目标。
- 本轮没有遇到 auto-mode 分类器拒绝，没有改写命令规避拒绝。报告提交到 main 后删除本轮开发机及 05 的审核 worktree；05 的静态检查日志保留在 worktree 外。不推送，不改写被审提交。

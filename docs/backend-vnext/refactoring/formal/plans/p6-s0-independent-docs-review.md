# Phase 6 S0 独立文档审核

- 结论：**通过**（第 3 次复审：P6-S0-F5、F13 按原关闭标准关闭；未发现新 finding。F1、F6、F11、F12 等既有关闭项不重审。）
- 最近复审：2026-10-26（UTC），main @ `40d4ea78995441297895fd411044d6f2b6924c57`，本地、未推送；设计与计划 r4。详见 §8。
- 第 2 次复审：2026-10-26（UTC），main @ `0adc2459739e910b3c595ed3c1ea16bb43b3b507`。以下 §1–§7 保留此前审核历史，不代表最新关闭状态。
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

## 6. 复审记录

### 6.1 第 1 次复审：对象与结论

- 结论：**定向修订**。原 F1–F10 中 **7 项关闭、3 项部分关闭**；新增 **P6-S0-F11、P6-S0-F12**，均阻塞。仍未关闭的阻塞编号共 **5 个：F1、F5、F6、F11、F12**；其中 F11/F12 是 F1 新方案的具体缺口，并非五个相互独立的根因。不能据此接受 S0 或授权 S1a。
- 日期：2026-10-26（UTC）。审核对象为 main @ `01c41e78bbcc4158e71d2a56fda2b8d726e2e172`，本地、未推送；设计 r2（含附录 A）、执行计划 r2、决议记录 DC55 及 DC39/DC41/DC42/DC45/DC50 修订。对照首次审核对象 `fc109806bb714bf004fa4ffd7b043941e834fa4e` 与本报告 §2 的关闭标准。
- 依据：P5 执行计划 §8.8；AGENTS；P5 DC35/DC36；P6 决议（DC55 优先于被修订旧条目）；设计引用的 owning Contract/ADR；V5/V5b/V6/V1 报告。以下行号均为本次被审提交，B/SK/RS 前缀同报告开头。
- 此为文档复审，没有实现门禁提交 V。使用 `/home/dev/gdds-p6-s0-review` detached worktree 阅读；被审文档和源码未修改。源码与 AGENTS 在两次被审提交之间无差异，但本轮仍亲自核对下列调用链，不以首次报告代替源码证据。
- 本节为便于阅读，源码路径中 `comparison/`、`mutation_planning/` 等 capability 名称均相对于 B`capabilities/`；同段省略目录的文件沿用该段模块目录。

### 6.2 原 findings 逐项关闭判定

| 原 finding | 关闭情况 | 按原关闭标准核对的依据 |
| --- | --- | --- |
| P6-S0-F1 | **部分关闭，仍阻塞** | DC55 第 1 项（决议 `:294`）保留 ordered 逻辑摘要定义；设计 `:138` 的传播表、`:184` 的 golden 生命周期与计划 `:49`–`:57` 一致，消除了 r1 用 raw digest 替换 logical digest 的直接冲突。投影阶段确有完整比较规则来源，见 §6.3。但新方案的策略命中条件和生成未变化 facts 所需字段不完整（F11/F12），尚不能满足原标准中的“S1a 保值验收可满足”。 |
| P6-S0-F2 | **关闭** | DC55 第 2 项；设计 §4.2（`:155`）、§5.2（`:210`）、§11（`:328`）统一完整表身份，导出键使用 row-layout/schema/repository scope/writer，并保留具名绑定；§15 将 schema 判定交 Preview 结构过滤测试、导出误命中交 bundle 组装测试，History 只 smoke。空表不含 schema 的源码事实仍见 B`capabilities/snapshot_materialization/_digest.py:105`。这是设计闭合，未宣称实现已验证；ordered 策略问题单列 F11。 |
| P6-S0-F3 | **关闭** | DC55 第 3 项与设计 `:281`–`:293` 明列 T1 前、T1 后 prepare 前、PREPARED、已提交副本四种恢复状态；未提交冻结内容无替代来源时稳定失败、不移动 main。设计 `:165` 保留 parent manifest 校验与 CAS，`:280`/`:391` 保留 finalize 同事务保护转移；§14/§15 给出 Contract 与恢复测试 owner。未引入新的恢复状态机。 |
| P6-S0-F4 | **关闭** | DC55 第 4 项、设计 `:227`–`:241` 明确零日期维持拒绝，FLOAT 由 Shared Kernel 修复；计划 `:69`、`:71`、`:135` 纳入真实实现及 golden。源码 SK`scalar.py:431`、`:639` 与 RS`arrow_mapping.py:472`/`:484` 的边界没有被绕开。新增接受值安排合成往返，S1b 定稿后才换 Rust；因此不再需要为零日期修订 RS wire mapping。 |
| P6-S0-F5 | **部分关闭，仍阻塞** | DC55 第 5 项、设计 `:168`/`:321`/`:437` 已取消 SQL statement 数断言，并在 S1a 冻结阈值与 batching，S4 只回归或走 owner 例外。§16.2 新增集合、观测点和六个例子，但重建/删除的“逻辑数”与所指规划器摘要不符，读取公式又混用逻辑需求和实际 cache miss；不能无歧义手算，详见 §6.4。 |
| P6-S0-F6 | **部分关闭，仍阻塞** | §4.4（`:171`–`:178`）增加归因、削减方案、owner 和停止条件；§9（`:311`–`:312`）明确 Arrow 风险接口、删除发布后回读；§16.1 与计划 `:99` 加入 S2b W2 检查点，方向正确。但预算表不是可加总的端到端账，读取 content 校验没有计算归属，“不能闭合”也缺可执行判据，详见 §6.5。不要求 S0 提前证明优化后的性能。 |
| P6-S0-F7 | **关闭** | 设计 §16.3（`:450`–`:468`）补 W3/W4 FULL、100% 压力只报告、H1-FULL、健康命中/损坏回填、H2 两节点/三节点和 Submit 时点；§16.4 明确冷热条件，样本与范围沿用 DC35。计划 `:83`、`:89` 明确先重建基准，`:121`、`:127` 覆盖 History 变体与最终六包/容器门禁。H1 的无条件零计算矛盾已解；读取数量错误仍归 F5，不重复记为 F7。 |
| P6-S0-F8 | **关闭** | 设计 §14（`:355`–`:373`）已列现行条款→目标→owner→阶段→golden/测试，含 Comparison table-level cache、Risk 未套 pair 上限结果、Snapshot Table Access IPC 边界、ADR 0014/Storage Mutation 的生产 Dolt 例外；§9/§11 缓存输入含规则主体、版本、scope，pair 限额和表名后绑定，命中重建当前 operation closure。计划 S3/S5 同步安排修约；基础 CAS/事务未弱化。新 ordered 元数据缺口需在此清单补充，归 F11/F12。 |
| P6-S0-F9 | **关闭（原为非阻塞建议）** | 设计 §15（`:377`–`:395`）将跳过、阈值、prepare、finalize、读取恢复、503、native crash 分开指定 owner；`:298`–`:300` 将 M 扩至常驻输入/输出/scratch，并区分预算拒绝与 runtime 接管。规则复用现有测试体系，无需加重复矩阵。后续 kickoff 落实具名用例即可。 |
| P6-S0-F10 | **关闭（原为非阻塞建议）** | 设计 `:83`、`:90`–`:97` 校正 step 范围、ordered 适用路径、ordering_digest 外部传递、RS 默认容量；`:290` 指向 P5 收口设计 §4.6，DC54 第 3 项改引 DC42 第 5 项；讨论稿头部 r29。计划 `:91`/`:136` 补新扩展 build-input、runner 排除与 import_rules 核对。原列举的删除遗漏和无效引用已修正；新的预算证据分类错误归 F6。 |

### 6.3 F1 的源码专项核对：规则在投影时可得，但不等于 pair 策略已确定

**比较规则视图可得，不构成“投影拿不到规则”的 blocker。** B`application/preview_jobs.py:1071` 取得完整 `TableRulesetSnapshot`；`:1250` 上传侧物化接收该 snapshot，`:1319` 将其传给 `project_canonical_table_set`。B`capabilities/storage_projection/contracts.py:157` 的 `ProjectionRequest` 也持有完整 ruleset。B`capabilities/table_rules/resolver.py:64` 的 `comparison_rule_set` 与 `:70` 的 `resolve_comparison_rule_view` 能在有表名、主键列时解析比较角色、排除列、ordered identity/position 和规则摘要。因此可复用 table_rules 的 owning 接口安排预计算，不需要为此新建规则来源或历史规则兼容层。

但现行完整 `OrderedTablePolicy` 不是单侧 ruleset view 本身：B`capabilities/comparison/pair_planning.py:125`–`:140` 还把**两侧共有列**填入 `value_columns`，`:169`–`:182` 对双侧取交集；`comparison/contracts.py:358` 起计算的 policy digest 覆盖这些字段。只掌握投影时的一侧 schema，不能无条件承诺预计算值适用于以后所有 pair；即使两侧存储策略标签相等，也须与本次受理冻结的有效比较策略核对。应修正复用条件及 fallback 范围，不能通过修改 ordered 定义或放宽 S1a comparison/bundle golden 来掩盖差异（F11）。

### 6.4 F5 剩余缺口与关闭要求

- **重建“写入行数”不是所指的 planner summary。** 设计 `:432` 将 patch 净变化数与 rebuild 写入行数混成一个计数，并指向“规划器摘要”；`:446` 删除表写作 0 行。当前 B`capabilities/mutation_planning/_planner.py:155`–`:159` 对新增/删除表记 `before_count + after_count`，`:170`–`:175` 对投影变化另有全表计数，普通阈值 fallback 在 `:202`–`:215` 仍保留净变化数。例：相同 schema 的 100 行表修改 6 行，按现行 5% 或拟定 1% 都重建，summary 是 6，新表写入 100 行；B`_changeset.py:80` 则构造 100 DELETE + 100 INSERT。删除一个 10 行表的 summary 是 10，生产 replay 的 DROP 可以是 1 条、INSERT 可以是 0，但不能把 0 当作该 summary。Storage Mutation §4（`storage-mutation-and-change-set.md:58`）也没有定义“DROP 后逻辑变更归零”的规则。
- **两行 INSERT 例子缺路由前提。** 设计 `:443`/`:444` 的 patch 示例只有在 schema/key/资格不变、落在冻结阈值内且未跨 renderer batch 字节上限时才成立；小表两行变化可能走 rebuild。当前 renderer `B…/mutation_planning/_repository_replay_renderer.py:176`–`:209` 同时按表/列身份、字节上限与 256 行切 batch。补出例如 1,000 行合格 keyed 表和小行值，即可保留这两个示例，不必新增 SQL statement 验收。
- **读取“等式”没有区分需求与命中。** 设计 `:428` 对 X/D 给出等式，`:448` 又允许 H3 全命中读取 0；`:435` 将“TTL 外或缓存缺失”直接等同于读取旧节点 X/D。diff/risk 条目缺失但规范表副本健康时，可重算而 Dolt 读取 0；当前 head 的规范表及导出副本缺失时也可能读当前 commit；整表 bundle 的缺失副本可涉及 U。两张同内容表还可能只有一次物理读取。§11/§8.2 本身允许这些状态，不能用旧节点集合等式覆盖所有 miss。
- **最小修正与关闭标准：** 保留 DC55 已定的 SQL 字节冻结；将净变化/规划器摘要、重建写入行数、物理 mutation 分列，明确使用哪一个作为验收，若引入新计数明确其观测点，不能声称它就是旧字段。对读取分别写出阶段/用途的逻辑表需求和按 `(commit, table/content identity)` 去重、缓存命中后实际读取；H1 缺失场景应按实际缺失的层与两侧来源计算。六个原例子补齐资格和缓存前提，再用上述重建、删表、仅 diff cache miss 验算无矛盾即可；无需扩成跨层组合测试矩阵。

### 6.5 F6 剩余缺口与关闭要求

| §16.1 项目 | 复审判断 |
| --- | --- |
| SQL 约 0.5 s | V6 `:114`/`:126` 的 N=4 为 **2× t4 已实测 0.481 s**，数值引用合理；不是表头 `:401` 所称“t4 实测再放大一倍”。它仍只是解析原型，不是生产 IPC/投影全路径。 |
| 1,248 次写入、10–15 s | V5b A（`:40`）为旧路径 624 次 `ArtifactStore.put` 合计 6.994 s，线性加倍约 13.988 s，作为粗估有来源；但这应标为**旧路径线性外推**，并说明目标 IPC 文件/manifest 数量与 W2 内容命中时是否仍写。旧 Parquet/ArtifactStore 的平均调用成本不是新 IPC 路径实测；V5b 明示 put 是嵌套子计数，不能与含它的阶段再次相加。 |
| W2 计算合计 30–35 s | 表内具数字的受理、解析、投影和写入小计约 **13.5–21.5 s**，bundle 只写“缓存命中”而无耗时，其余计算为 0；不能据此复算 30–35 s。step 2–20 s 与残差另列，正文又说另加，读者无法确定总计边界、重叠项和剩余缺口。不能把“缓存命中”当作免费或把残差当作一定消失。 |
| S2b W2 检查点 | 阶段和停止责任已补对，但“剩余成本已不能在 30 s 内闭合”没有可记录的判定式。W2 已跳过比较，S3 的 changed-kernel 加速不能泛化成 W2 的未来收益。应在 S2b handoff 以完整受理至 READY wall 为锚，列仍会发生的成本与有依据、具名的剩余削减上界；没有归属的残差不能作为可削减额度。总量不能闭合或仍未知时交 owner，不是只在证明物理下限后才停。 |
| W4 记录读取/风险 | §9 已禁止重建完整 `ComparisonRecord` 元组，也正确删除发布后回读；但同时保留实际读取的 raw/content/schema 校验。B`comparison/artifacts.py:279`、`:547`–`:578`、`:618` 当前仍全量解码并重算 JCS content digest。风险只取所需列无法替代对**全部记录内容**的校验；把读取改成分 batch 也只改变峰值，未消除扫描/编码时间。§16.1 没有这段的归属/预算，`:419` 因而还不能断言“不存在未计入的转换或回读”。约 5 s Python 风险应明确为待验证假设，并说明是否包含该校验。 |

**最小修正与关闭标准：** 用不重叠的粗粒度账替代当前合计，逐行标明“目标工作量×来源吞吐”的假设、实际 wall/CPU/嵌套关系与阶段；允许保留未知值，但未知值必须触发既定检查点。给出 S2b W2 可直接填实测数的判定式和允许继续/交 owner 的条件。给 W4 保留的读取 content 校验指定执行接口、计算 owner 和所属预算段，例如复用 Rust Arrow/JCS 能力重算而保持 Python 风险规则不搬迁；若保留 Python 处理则计入其成本。仍由 S3 W4 实测验证与触发 DC47 重开，不要求 S0 新跑性能测试，不放宽指标，也不增设读取证据机制。

### 6.6 新增 findings

#### P6-S0-F11：预计算 ordered 摘要只比较两侧历史策略，漏掉当前 pair 的有效策略

- 类型：**已证实缺陷**；是否阻塞：**是**。
- 位置：DC55 第 1 项（`p6-s0-owner-decisions.md:294`）；`p6-design.md:132`、`:155`–`:158`、`:362`；`p6-execution-plan.md:50`。
- 依据：ADR 0019 Decision 6（`:53`–`:54`）规定 Preview/History 按受理时冻结的运行期 ruleset 比较，commit 元数据只提供存储身份/provenance。B`comparison/pair_planning.py:125`–`:140` 的完整 ordered policy 还依赖 pair 共有列；B`comparison/ordered.py:746`/`:770` 的摘要实际使用 policy version 与 value columns。投影规则来源可得的正面证据见 §6.3。
- 触发场景与影响：两个历史 commit 都在 R1 下生成 manifest，随后只调整 comparison 排除列为 R2，存储视图/schema/内容不变；两侧存储的策略摘要仍相等，按新条文会直接取 R1 摘要，而当前重算应使用 R2，输出 facts/digest 不一致。不同 schema 的 pair 还必须用共有列策略，不能仅凭单侧规则摘要复用全列逻辑值。§4.2 的 U 条件不含这类有效性判断，却无条件承诺不读不比，连策略不同时的回退也与它冲突。
- 最小修正方向：由 owner 澄清 DC55 的“相同”包含**各侧缓存计算身份与本次有效 pair 策略相同**，其身份覆盖实际使用的列投影和规则语义；不能改用 commit 历史规则做 History。区分“存储内容未变”与“足以不读行生成本次比较结果”，按当前策略不匹配/元数据不足安排最小回退，并同步读取计数、Contract 清单和缓存命中条件。
- 关闭标准：文档可无歧义推导规则不变同 schema 命中、两侧历史规则相同但当前规则变化、两侧 schema/共有列不同三种结果；明确哪些允许不读行、哪些重算。沿用 §15 的 ordered 权威测试 owner，要求预计算路径与现算 facts/digest 相同；不新增历史规则兼容层或重复测试 owner。

#### P6-S0-F12：manifest 新字段不足以保值生成未变化 ordered 表的 blank facts

- 类型：**已证实缺陷**；是否阻塞：**是**。
- 位置：`p6-design.md:132`、`:145`–`:147`、`:156`、`:346`/`:357`；DC55 第 1 项；执行计划 S1a 保值验收。
- 依据：B`comparison/ordered.py:527`、`:599` 即使未变化也输出 `BlankExtension`；`:729`–`:743` 的两侧 occupancy digest 根据稳定锚点间空白数量计算。B`comparison/row_encoding.py:667`–`:687` 将其纳入 facts digest。当前 `storage_projection/contracts.py:233`–`:248` 的 manifest 只有伪 gid 总数等，没有该分布摘要；r2 新增的仅是 ordered logical digest 与策略摘要，二者的哈希值不能反推出 occupancy digest。
- 触发场景与影响：两侧为同一张含空白行的 ordered 表，且规则/schema/存储全部相同。原算法虽无 changed records，仍生成内容相关的非空 occupancy digest。r2 要求只凭 manifest 构造 UNCHANGED facts，不读基线行；缺少所需字段时只能漏填/用常量而改变 comparison/surface/bundle digest，或重新读取行而违反声明的零读验收。这个问题在当前规则完全相同时仍存在，与 F11 独立。
- 最小修正方向：列出从 manifest 合成完整 UNCHANGED ordered/blank facts 的最小字段和计算来源；例如在已有投影扫描中一并保存所需 occupancy 摘要及有效性身份，或使用明确已验证且适配当前策略的完整 facts 来源。同步 Canonical Storage/Ordered Diff 的字段、manifest/checkpoint 传播及 S1a golden；不能把 occupancy 字段删掉或改成常量来维持“零读”。
- 关闭标准：给出含头部/内部/尾部空白的未变化 ordered 输入在新旧路径的 facts 字段对应，证明 logical digest、occupancy digest、policy 和其余非行数据都能从所列来源获得且保持原值；健康命中无需读行，元数据不适配有明确回退。由同一个 ordered 比较测试 owner 承接保值断言，不新建保障层。

### 6.7 验收核对与比例化意见

| 验收项 | 结果 | 证据/限制 |
| --- | --- | --- |
| 原 F1–F10 按关闭标准复审 | 完成 | §6.2；没有把附录 A 自称“已处置”当成关闭证据 |
| DC55 落实与新矛盾 | 需定向修订 | 第 2–4 项闭合；第 1 项需 F11/F12；第 5 项字节冻结成立，但设计计数仍需 F5 |
| 规则在物化/投影时是否可得 | 可得 | §6.3 源码；所缺是有效 pair 身份与完整 facts 元数据，而非 ruleset 传递 |
| W2/W4 可行性与判停 | 仍有技术路径，尚未闭合 | F6；没有把粗估标成达标证据；S1a 归因与 S2b/S3 检查点应保留 |
| 阶段顺序、golden、flag 与旧扩展 | 本轮未发现新的实质冲突 | 计划 S1a→S1b→基准→S2a→S2b→S3→S4→S5→S6；S2a 镜像/build-input/import_rules，S6 删除生产 flag；S4 golden 调整限 owner 例外 |
| Contract/DTO/checkpoint/schema | 原 F8 关闭；ordered 增补待完成 | 新字段不能遗漏 §13/§14 的载荷与测试落点；不要求兼容迁移或旧数据回填 |
| 基础边界与测试归属 | 保留 | caller 输入、资源上限、T1、parent 校验、CAS 与 finalize 事务仍强验证；F11/F12 是既有输出语义保值要求，不扩大信任域 |
| 文档收尾 | 非阻塞提醒 | 决议待定表 `:309` 仍称“S4 定稿”，`:337` 仍称 r1；计划 S0 `:38` 仍写 DC37–DC54。DC55/计划正文已明确优先口径，建议随下一轮对齐这些导航文字，不据此重开已关闭项 |
| S0 exit/实现授权 | 未满足 | 5 个未关闭编号按上述范围修订、定向复审后由 owner 接受；本报告不代替授权 |

### 6.8 本次实际执行的检查

| 检查 | 命令/方法 | 结果 |
| --- | --- | --- |
| 主 checkout 与指定快照 | `git status --short`、`git rev-parse HEAD`；`git worktree add --detach /home/dev/gdds-p6-s0-review 01c41e78bb` | 起始 main clean，HEAD 等于本次目标；开发机只读审核，无测试/测量 |
| 差异与来源 | `git diff fc109806bb 01c41e78bb`；`rg`、`sed -n`、`nl -ba` | 阅读 r2/决议修订与原关闭标准；`git diff ... -- vnext AGENTS.md` 为空；亲自复核规则入口、pair policy、ordered/blank 摘要、mutation planner/renderer、records 校验；数字外推手算，未执行产品代码 |
| 05 节点 preflight | `ssh -o BatchMode=yes ct108-gw-dms-05 'echo OK'`；hostname、`pgrep -af`、`docker ps`、节点 HEAD/status | 可连接，`gw-dms-test-05`；检查时无其他测试/编译/Dolt/测量任务或运行容器，节点 checkout clean |
| 05 独立已提交 worktree | bundle/scp/fetch；`git worktree add --detach /home/dev/gdds-p6-s0-rereview1 01c41e78bb`；legacy 符号链接 | 不移动节点 main；同一 clean 被审提交；`TMPDIR=/home/dev/gdds-test-tmp`，`CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/p6-s0-rereview1-cargo-target` 在 worktree 外 |
| 五包提交前静态检查 | 05 各包 `../scripts/uv-consume.sh -C . run ruff check .` 与 `../scripts/uv-consume.sh -C . run mypy` | 全部通过；mypy 文件数 shared_kernel=34、repository_contracts=15、repository_client=26、backend=486、repository_service=200；没有锁文件漂移 |
| 静态检查 provenance | `/home/dev/gdds-p6-s0-rereview1-static.log`（05） | 2026-10-26T00:00:06Z–00:01:05Z；起止 HEAD 均 `01c41e78bbcc4158e71d2a56fda2b8d726e2e172`；exit=0；结束 tracked worktree clean；root SSH、LC_ALL=C.UTF-8、umask=022 |
| 产品测试/门禁/测量 | 未执行 | 未运行 pytest、权威 runner、Compose、真实数据旅程或性能测量；没有在开发机跑测试 |

### 6.9 验证限制与交付边界

- 本轮证明的是文档与源码/Contract 的一致性。F11/F12 的输入是根据源码推导的反例，未运行动态用例；静态检查不证明优化已实现或 W2/W4 达标。预算仅重读公开入库报告并复核算术，没有访问真实数据内容，也没有真实数据进入 Git。
- 当前被审 HEAD 为 `01c41e78bbcc4158e71d2a56fda2b8d726e2e172`；本次仅追加审核报告，不触发镜像重建。最后验证的 image revision/source-tree **本轮未核验，不作 carried 声明**；下一实施阶段按 AGENTS 在其候选上建立门禁证据。静态检查环境安装构建了既有 Rust 扩展，不是 Rust gate 或新 adapter 验收。
- 本次只提交此报告，§1–§5 保留首次审核历史；不会修改设计、计划、决议或实现来替作者关闭问题。提交后清理开发机审核 worktree 与 05 的本次检查 worktree；05 日志保留在 worktree 外。不推送，不改写被审提交。
- 未遇到 auto-mode 分类器拒绝，也未改写命令规避拒绝。

## 7. 第 2 次复审记录

### 7.1 对象与结论

- 结论：**定向修订**。本轮五个待关闭编号中，**F1、F6、F11、F12 关闭，F5 部分关闭**；F5 仅剩 History 需求与实际读取公式的遗漏，仍阻塞。新增 **P6-S0-F13，非阻塞**，是 ordered 摘要 Rust 化阶段的文字未同步。未关闭项共 2 个，其中阻塞 1 个；修订范围已明显收敛，仍需关闭 F5 后由 owner 接受 S0、授权实施。
- 日期：2026-10-26（UTC）。审核对象：main @ `0adc2459739e910b3c595ed3c1ea16bb43b3b507`，本地、未推送；设计 r3、计划 r3、DC55 第 1 项再次修订。对照对象为 `01c41e78bb`，关闭标准为本报告 §6.2–§6.6；沿用 P5 执行计划 §8.8 模板。
- 审核在 `/home/dev/gdds-p6-s0-review` detached worktree 只读进行；没有实现门禁 V，没有修改被审文档或源码。两次对象之间 `vnext/` 与 AGENTS 无差异，本轮仍重读相关调用链。以下设计/计划/决议行号均对应 r3；B/SK/RS 前缀同开头，简称 `comparison/` 等指 B 下 `capabilities/` 中的模块。

### 7.2 逐项关闭判定

| 原 finding | 关闭情况 | 依据 |
| --- | --- | --- |
| P6-S0-F1 | **关闭** | DC55 第 1 项（决议 `:294`）、设计 `:132`、`:145`–`:147`、`:155`、`:362` 与计划 `:50` 改用当前侧规范行计算，取消 manifest 的 ordered 新字段；摘要保值表和 §4.6 golden 生命周期保持一致。对于满足 U 的表，有只读一侧而保留既有双侧结果的路径，详见 §7.3；不再依赖不可逆哈希反推 blank facts。 |
| P6-S0-F5 | **部分关闭，仍阻塞** | 设计 `:450`–`:474` 已分开 patch 净变化、rebuild 写入、DROP 和只报告的 planner summary；新增阈值/批量前提，上一轮两个反例均成立。读取已分逻辑与实际，但 `:439` 的 History 行比较需求只列旧节点 X∪D，漏掉当前节点 X；其“上述需求”无法覆盖仅当前规范表缺失、导出缓存命中的状态。见 §7.4，仍未满足“按层与两侧来源无歧义计算”的关闭标准。 |
| P6-S0-F6 | **关闭（设计可执行性，不是性能达标）** | §16.1（`:401`–`:427`）修正证据类别、可复算小计、未知项检查点与 S2b 判定式；§9（`:310`–`:312`）明确风险消费内存 Arrow、存储读取校验由 Rust 承担并进入 History/bundle 成本。W4 的 Python 风险 5 s 明标假设；未知成本不再冒充已消除。小计和判定式验算见 §7.5；F13 的阶段残句不改变该可行性检查的用途。 |
| P6-S0-F11 | **关闭** | 设计 `:132` 明确“本次受理冻结的有效 pair 策略（含两侧共有列）”；历史 R1 标签相同不再构成复用依据。当前规则变化时按 R2 重算，schema 不同走 X 普通比较；§15 `:382` 指定相应权威测试。`pair_planning.py:45`–`:71`、`:125`–`:140` 的双侧描述符和运行期规则均可在不读 before 行时使用。 |
| P6-S0-F12 | **关闭** | 设计 `:132`、`:155`、`:328`、附录 `:539` 明确 occupancy 及其余 facts 由当前侧行现算或取健康 diff/risk 缓存；不再仅凭 manifest 两个哈希生成全部 facts。现有规范行带 blank provenance，单侧 gap 计算具有所需锚点/计数；头部、内部、尾部空白已进入同一 ordered 测试 owner（`:382`）。源码等价推导与调用限制见 §7.3。 |

### 7.3 ordered 专项：行来源、有效策略与单侧计算的输入

**当前侧不是固定的 MODIFIED，也不能假设 materialize 与 assemble 共享内存。** r3 的“内存中的上传侧”应理解为本次 pair 当前侧的规范行来源；实际现行实现有 checkpoint/artifact reader，目标 S2b 有 IPC reader。以下每条路径都有来源，未发现必须读取未变 before 行才能计算摘要的依赖。

| 路径/状态 | 当前侧与可用来源 | 源码/设计依据 |
| --- | --- | --- |
| MODIFIED_ONLY Preview | baseline→MODIFIED，当前侧为上传后投影的 MODIFIED | B`application/preview_jobs.py:1618`–`:1625`；投影 reader 与规范 blank metadata 见 `storage_projection/project.py:483`–`:504` |
| FULL Preview | baseline→INITIAL、INITIAL→MODIFIED；两次当前侧分别是上传的 INITIAL、MODIFIED | `preview_jobs.py:1598`–`:1607`；不能都拿 MODIFIED 代替当前侧。INITIAL baseline 没有 U 表，走新增路径 |
| Preview assemble/重启恢复 | 从 materialize checkpoint 打开当前侧 artifact 的 reader，不依赖上一步 Python 对象存活 | `preview_jobs.py:2463`–`:2529`；S2b 原始表 consumer 核对仍是设计 `:272` 的切换前置，缺失产物按既定恢复/失败规则处理，不用另一份输入代替 |
| 两节点 History | pair 的 current commit；S1a 现有 artifact/RS，S2b 起规范表存储/精确 commit Dolt 兜底 | B`application/history/compare_jobs.py:715`–`:793`、`:838`–`:844`；设计 §8.2、§11。S1a 尚无整表导出优化，也不能据此取消单侧摘要的独立读取需求 |
| 三节点 History | 两个相邻 pair 的 current 分别为第 2、第 3 节点，按各自 pair 的规则/描述符计算 | `history/compare_jobs.py:807`–`:811`；不能用最终 head 的一份行替代所有 pair |
| History 导出命中、diff/risk 未命中 | 仍需读当前 U 中 ordered 表；不能以 bundle 无需读表为由跳过摘要 | 设计 `:439` 已把“单侧摘要需要当前节点行”列为独立需求，补足 `:155` “本来要为打包读取”的简写；旧节点行无需为此读取 |
| History diff/risk 健康命中 | 直接用完整有效任务键命中的 facts；无须单侧重算 | 设计 `:313`、`:327`–`:330`、`:448`/`:461`；规则变化不命中旧条目。损坏/缺失回退仍由现有读取与恢复边界处理 |

策略构造不需要 before 的行，但需要 **before/current 两侧描述符与存储事实**。`comparison/pair_planning.py:37`–`:61` 以本次 request 的规则解析两侧 view，再将双侧 descriptor 交 `_comparison_policy`；`:125`–`:140` 的 `value_columns` 来自两侧共有列，`:169`–`:182` 对双侧取交集。U 已要求 schema 相同，故共有列与当前侧同一列集一致；仍应沿用这个双侧构造，不能因为只读一侧就把 before descriptor 设成 `None`。History 的 `_assert_runtime_ruleset`（`:753`–`:762`）检查受理冻结的 digest，Preview assemble 显式传 `rule_set`（`:1645`）；R1→R2 因而使用当前 R2，而非历史 manifest 的规则。

blank 所需 provenance 也可得：上传投影 `storage_projection/project.py:496`–`:504` 和 Repository 物化 `snapshot_materialization/repository_ref.py:450`–`:461` 都生成 `CANONICAL_PSEUDO_GID`；`snapshot_materialization/artifact.py:305`–`:325` 在打开 artifact 时还原 metadata，History checkpoint 同样调用 `open_snapshot_table_artifact`（`:1220`）。单侧扫描必须使用这份**规范行与规范 provenance**，不能拿原始 SQL 行按 pseudo-gid 规则解释，也不能丢掉 metadata 后直接哈希 Arrow 裸列。

**逐字节等价的静态推导：** 对 U 中通过现行 ordered 校验的表，`ordered.py:270`–`:340` 按本次 `schema.selected`、required key、规范 blank provenance 编码并按 position 排序；两侧内容/schema/存储相同，所以得到同一 `_OrderedRow` 序列。`_ordered_digest`（`:746`）的 table name、policy version、stable/position/blank/content 均相同，一次计算可作为两侧值。`_occupancy_digest(_blank_gaps(rows, None))`（`:729`–`:743`）只依赖这一侧按 position 排列的真实锚点与空白数量，同样可直接复用两侧；它不是把两侧共同 backbone 当成单侧输入。

对于头部/内部/尾部空白，设序列为 `blank, A, blank, B, blank`，单侧 gap 分别是 `(None,A):1`、`(A,B):1`、`(B,None):1`；两侧相同则每个 gap 的差为 0，records 为空，occupancy 两侧取同一规范 JSON 摘要。空表给空 gap 列表，全空白表给 `(None,None):n`，也不需要 LIS。一般 U 的真实行 position 严格递增，旧算法 `:500`–`:508` 的 backbone 是所有真实 key，故 moved/position changed 和所有增删改计数均为 0；ordered/blank status、replay guarantee、schema facts、policy digest 等仍按既有结构填充，不能只填两个摘要。

**不要把现有 `_compare_single_side` 当作这项优化。** `ordered.py:159`–`:185` 表达的是 ADDED/DELETED：另一侧 rows 为空、descriptor 为 `None`，会生成增删记录和不同的 blank 摘要；`_single_side_schema_changes`（`:253`）也不是双侧 schema facts。新分支应复用双侧策略/校验与单侧编码/摘要 helper，或等价地构造“两侧相同”的 facts，保留 `_ordered_schema_diagnostics`、row 读取异常的既有 degraded 语义，不能仅因 manifest 相等就把失效输入强制标成 UNCHANGED。r3 没有要求调用该新增/删除入口，故这属于实施约束，不作为新 blocker。上述是源码推导，实际新旧结果逐字节断言仍由 §15 指定的 ordered 测试在实现阶段完成。

### 7.4 F5：手算结果、剩余反例与最小关闭方向

| §16.2 示例 | 手算/源码核对结果 |
| --- | --- |
| 1,000 行合格 keyed 表新增两行 | X=1；基线需求 1，未复用时实际读 1；行派发/kernel 各 1；净 INSERT=2，比例 `2/1002 < 1%`，可 patch。相同列身份且字节未超限时可一条批量 INSERT，但 SQL 条数不作断言，正确 |
| 同一表一行键变化 | X=1，DELETE+INSERT=2，`2/1000=0.2%`，可 patch；读/派发计数同上，正确 |
| 100 行表改 6 行 | `6/100=6%`，超过拟定 1%，也超过现行 5%；rebuild 写入 100，planner `changed_row_count=6` 只报告，正确。旧 `_changeset.py:80` 的 200 个 DELETE/INSERT 对象不再被冒充该写入数 |
| 新增表 n 行 | A=1，基线读 0，行派发/kernel 0，表级处理 1；rebuild 写入 n，正确 |
| 删除表 10 行 | D=1，表级处理 1，DROP 1、写入 0；planner summary 10，正确。示例实际读 1 是没有可复用基线数据/导出的情形，导出命中时须按上方“实际读取≤逻辑需求”处理 |
| 两张同内容表相同变化 | 逻辑派发 2；在完整任务键也相同的前提下 kernel 1，读取按完整内容身份可为 1 或 2；Submit 各自计数，正确。仅 raw hash 相同但 schema/规则不同不能套用去重例子 |
| 只缺 diff/risk，两侧规范表健康 | X=1，重算需要两侧行，但两侧都从存储读取，Dolt=0、kernel=1，正确 |
| H3 健康命中 | Dolt/kernel/单侧摘要均 0，正确；这是逻辑派发之后的命中分支，不与派发数冲突 |

依据为 B`mutation_planning/_planner.py:150`–`:215`、`_patch_eligible:253` 起，`_repository_replay_renderer.py:176`–`:209` 的行数/字节/列身份切批，以及 Storage Mutation §4。上述数字均为人工代入，不是新跑产品测试。上一轮的“重建 summary≠写入行数”和“删表 summary≠0”已经修正，不再要求作者重做这部分。

**仍未关闭的 F5 仅限下述读取公式：** 设计 `:439` 将 History 的行比较需求写成“旧节点 X∪D”，随后用各层需求中的存储 miss 数算 Dolt 次数，却没有当前节点 X 的行需求。取一个两侧都存在且内容变化的非 ordered 表 t：diff/risk 未命中；旧节点规范表健康；当前节点规范表缺失；两侧导出缓存均健康。按该行列出的需求，旧节点存储命中、bundle 不读表、又没有 U ordered 单侧摘要需求，推得 Dolt=0；但 `pair_planning.py:68`–`:69` 与双侧比较需要 current rows，按 §8.2 的规范表存储→Dolt 回退应读取当前 commit 的 t，实际为 1。若实现打算将导出 Parquet 作为另一比较输入来源，则必须明列其可信输入转换与计数，不能由“导出命中”暗中推定当前规范行已存在。

- 类型仍为**已证实缺陷，阻塞**；位置收敛为 `p6-design.md:439` 与执行计划 S5 的 §16.2 验收引用；影响是低报当前侧读取或给正确回退错误的计数上限，不是新的数据安全机制要求。
- 最小修正：在 diff/risk 未命中且需要行比较的 pair 中，分别列 old-X 与 current-X；D 的表级处理/导出需求独立列出，A/所有节点的 bundle 需求照现规则。合并去重后再按完整内容身份和缓存层计算实际读取，不能只列旧节点。健康 diff/risk 命中应消除两侧比较行需求，而不自动消除独立 bundle 需求。
- 关闭标准：保留已正确的八个例子，补上述“仅当前规范表 miss、导出命中”的 1 次 Dolt 回退结果，以及其两侧都健康时的 0 次结果；正文公式与示例一致即可。无需新建计数框架或扩大测试矩阵。

### 7.5 F6：预算小计与 W2 判定式复算

按表头明确排除 e、i、j、k，a–h 的已知项相加如下（单位 s）：

| 负载 | 逐项相加 | 精确区间 | 文档约数 |
| --- | --- | --- | --- |
| W1 | 1 + 0.5 + (2–5) + 14 | 17.5–20.5 | 18–21，一致 |
| W2 | 1 + 0.5 + (2–5) | 3.5–6.5 | 4–7，一致 |
| W3 | 1 + 0.5 + (2–5) + 2 + 1 + 2 + 1 | 9.5–12.5 | 10–13，一致 |
| W4 | 1 + 0.5 + (2–5) + 14 + (1–5) + (5–10) + 5 | 28.5–40.5 | 29–41，一致 |

V6 的 0.481 s 正确标为 2× t4 原型实测；写入约 14 s 正确标为旧路径外推（`624×2×6.994/624=13.988`）。W2 写入 0 是内容全部命中且不重写的明确假设，W3 约 2 s、物化 2–5 s、Rust 单侧摘要 <1 s 均不能当成生产实测。g 的 V1 来源不含 IPC/输出编码，S3 取证必须以 g 所声明的完整“比较与逐行记录”边界测量；i 的 bundle 成本含真实读 closure 时的 Rust 校验。i/k 中提到的 assemble 固定开销归因后只能落入一个最终成本项，不能重复相加。r3 把这些未知/外推绑定到阶段检查，足以关闭 S0 预算建模缺口，不表示已有端到端可达证明。

判定式 `W2_S2b − Σ有证据、有阶段的剩余削减上界 ≤ 30 s` 是**可行性筛查**而非达标验收：例如实测 40 s、唯一不重叠且有证据的削减上界为 12 s，则乐观剩余 28 s，可继续验证；上界只有 8 s，则 32 s，停止交 owner；存在任何未归因项时即使算术为 28 s 也停止。未归因项的可削减额度为 0，不能靠未知收益填洞。多个削减不能重复覆盖同一 wall 段，实际削减未达预期时仍需重新核对可达性，最终 ≤30 s 由 S6 测量判定。

W2 没有变化表行比较，不能借 S3 的 changed-kernel 吞吐抵扣；它有 e 项的未变 ordered 单侧扫描，S3 若确实缩短该项，可用**该项自身证据**申报削减。§9 已为新算记录的 Python 风险和缓存/bundle 读 closure 的 Rust 校验分别明确执行路径，W4 约 5 s 风险仍是待验证假设，超出预算继续按 DC47 处理，不自动搬迁全部规则。因而本轮关闭 F6，不要求在 S0 运行尚不存在的优化实现。

### 7.6 新增 P6-S0-F13：S2b 路径仍残留与 S3 安排相冲突的 ordered 摘要计算

- 类型：**非阻塞建议**；是否阻塞：**否**。
- 位置：`p6-design.md:269`（§8.1），对照 `:132`、`:155`、`:409` 与 DC55 第 1 项。
- 依据：r3 已取消投影时为 manifest 预计算 ordered 字段；§4.2 明确单侧摘要 S1a 用 Python、S3 起用 Rust，预算 e 也是 S1a/S3 检查。§8.1 仍称 S2b 上传合并路径依次完成“表摘要、ordered 逻辑摘要与 fast_row_digest”，未说明此处如何获得本次完整 pair 策略或是否代替 S3 的计算。
- 触发场景与影响：实现者照 S2b 清单预计算一次，assemble 又按当前 pair 重算，产生无 consumer 的重复扫描；或误将单侧策略的值当作 pair 结果，并高估 W2 在 S2b 已获得的削减。更具体的新 §4.1/§4.2 已给出正确方向，因此本轮不把这条残留文字单独列为阻塞，也不重开已关闭 F11。
- 最小修正方向：同步 §8.1，删除无 consumer 的 ordered 预计算措辞；若有意把单侧摘要提前到 S2b，则明确完整 pair 输入、唯一计算位置并同步 e 项阶段，不能两处各算一次。
- 关闭标准：设计和计划对 ordered 单侧摘要的 Python→Rust 节点、输入与预算归属只有一种解释；不要求新增机制、Contract 版本或测试 owner。

### 7.7 验收核对与已关闭项影响范围

| 验收项 | 结果 | 依据/限制 |
| --- | --- | --- |
| 五项逐一按原关闭标准复核 | 完成 | §7.2；F5 仅保留一个明确反例，不重复否定已修正部分 |
| Preview/FULL/History/恢复的 ordered 输入 | 设计路径可满足 | §7.3；保留双侧元数据，只减少 before 行读取，不使用 ADDED/DELETED 单侧入口 |
| 计数手算与上一轮反例 | Submit 与已列示例通过；History 公式仍遗漏 | §7.4 |
| 已知项小计与 W2 检查点 | 通过设计审核 | §7.5；不是生产性能通过或最终门槛豁免 |
| F2–F4、F7–F10 | 维持关闭 | 本轮仅复核受影响的缓存输入、blank metadata/恢复、§13/§14 ordered 字段撤回、§15 owner 与导航文字；完整表身份、零日期、FULL/三节点矩阵、CAS/保护、旧扩展与 runner 规则未被 r3 推翻 |
| 比例化与阶段依赖 | 无新增过度保障机制 | 单侧扫描使用当前规则和既有输入校验；沿用 ordered 权威测试 owner，不加摘要持久字段、历史规则兼容层或独立恢复机制；阶段文字问题见 F13 |
| S0 接受 | 尚未满足 | F5 关闭后定向复核并由 owner 接受；F13 可同轮文字对齐 |

### 7.8 本次实际执行的检查

| 检查 | 命令/方法 | 结果 |
| --- | --- | --- |
| 主 checkout 与 detached 快照 | `git status --short`、`git rev-parse HEAD`；`git worktree add --detach /home/dev/gdds-p6-s0-review 0adc245973` | 初始 main clean；HEAD 为目标完整 SHA；开发机仅阅读、手算与写审核报告 |
| 差异/源码/模板 | `git diff 01c41e78bb 0adc245973`、`rg`、`nl -ba`、`sed -n` | 三份 r3 修订与上一轮关闭标准逐项比对；`vnext/`、AGENTS 差异为空；重读 pair planning、ordered/blank、Preview/History checkpoint、投影 provenance、planner/renderer 与 P5 §8.8 |
| 05 preflight | `ssh -o BatchMode=yes ct108-gw-dms-05 'echo OK'`；hostname、`pgrep -af`、`docker ps`、HEAD/status/worktree list | `gw-dms-test-05`；无其他测试/编译/Dolt/测量任务和运行容器，节点主 checkout clean |
| 节点快照同步 | `git bundle create - main` 经 SSH 写入节点日志目录，fetch 后建 `/home/dev/gdds-p6-s0-rereview2` detached worktree 并建 legacy 链接 | 节点 worktree 同为目标提交；未移动节点 main；无本地临时 bundle |
| 五包提交前静态检查 | 05 每包执行 `../scripts/uv-consume.sh -C . run ruff check .` 与 `../scripts/uv-consume.sh -C . run mypy` | 全部通过；mypy 文件数 shared_kernel=34、repository_contracts=15、repository_client=26、backend=486、repository_service=200；无锁文件漂移；不是产品测试或性能取证 |
| 产品测试/门禁/测量 | 未执行 | 未运行 pytest、权威 runner、Compose 或真实数据旅程；本轮无需动态测量；未在开发机运行测试 |

静态检查日志：05 的 `/home/dev/gdds-p6-s0-rereview2-logs/static.log`；2026-10-26T04:49:43Z–04:50:42Z，起止 HEAD 均为 `0adc2459739e910b3c595ed3c1ea16bb43b3b507`，exit=0，结束 tracked worktree clean。root SSH、LC_ALL=C.UTF-8、umask=022、TMPDIR=`/home/dev/gdds-test-tmp`；CARGO_TARGET_DIR=`/home/dev/gdds-p6-s0-rereview2-logs/cargo-target` 位于 worktree 外。

### 7.9 验证限制与交付边界

- 单侧摘要的逐字节等价是根据现行编码、排序、策略与 blank 函数推导；没有声称新 helper 已实现或测试通过。有效输入之外的诊断/degraded 语义仍受 S1a 保值约定约束。实现阶段须以既有完整 facts/golden 比较证明，不能仅比较两个摘要。
- 未读取或提交真实数据；预算只核对入库报告与人工算术，不把原型吞吐当作端到端结果。未知成本、S2b W2 判定和 S3 W4 实测仍是实施检查点。
- 当前被审 HEAD=`0adc2459739e910b3c595ed3c1ea16bb43b3b507`。报告为纯文档变更，不触发镜像重建；最后验证的 image revision/source-tree 本轮未核验，不作 carried 声明。五包静态检查不是 runner/容器门禁；环境安装构建既有扩展也不是 Rust gate。
- 只提交本报告，保留 §1–§6 历史；不修改被审文档，不推送。交付时删除开发机和 05 的本次 detached worktree；节点日志及其中的临时 bundle/构建缓存保留在 `/home/dev/gdds-p6-s0-rereview2-logs/`，不需要单独删除。此前复审遗留的临时文件不属于本次清理范围。
- 本轮未遇到 auto-mode 分类器拒绝，未尝试绕过此前拒绝的删除操作。

## 8. 第 3 次复审记录

### 8.1 对象与结论

- 结论：**通过**。P6-S0-F5 与 P6-S0-F13 均按 §7.4、§7.6 原关闭标准关闭；本轮未发现需续编为 P6-S0-F14 的新问题。设计文档复核通过，可交 owner 接受 S0；接受与 S1a 实现授权仍由 owner 作出。
- 日期：2026-10-26（UTC）。审核对象：main @ `40d4ea78995441297895fd411044d6f2b6924c57`，本地、未推送；`p6-design.md` r4、`p6-execution-plan.md` r4。只定向复核上一轮未关闭的 F5 与 F13；对照对象为 `0adc2459739e910b3c595ed3c1ea16bb43b3b507`。
- 审核在 `/home/dev/gateway-data-management-system-p6-s0-rereview3` detached worktree 中只读进行；只修改本报告，未改被审文档或源码。未运行测试或代码静态检查；`git diff --check` 仅检查本报告补丁的空白格式。

### 8.2 Findings

无新增 finding。

### 8.3 验收核对

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| P6-S0-F5：History 当前侧读取遗漏反例 | **关闭** | 设计 §16.2（`:441`、`:475`–`:476`）现按 pair 分层；diff/risk miss 的 `X={t}` 需要 old-X 与 current-X。旧侧规范副本健康、当前侧缺失、两侧导出缓存健康时，打包层不读表，行比较层仅当前侧存储 miss，按精确 commit 回退 Dolt 1 次。两侧规范副本都健康时，比较所需两侧均由存储满足，Dolt 为 0。导出命中不再掩盖当前侧行比较需求，两个指定场景与正文公式一致。 |
| P6-S0-F5：原有八个例子 | **未被改坏** | §16.2 的六个 Preview/Submit 例子仍分别给出：新增两行 `X=1`、基线读取 1、净 INSERT 2；键变化 DELETE+INSERT 2；100 行改 6 行时重建写 100、summary 6 仅报告；新增表无基线读取、写 n 行；删除表由 bundle 读取旧侧、DROP 且写 0 行；同内容双表逻辑派发 2、完整任务键相同才将 kernel 去重为 1。原有 History 两例也成立：两侧存储健康时 Dolt 0；H3 健康命中时 Dolt/kernel/单侧摘要均为 0。原“两节点副本健康”行现明确标为非 ordered 的 `X={t}` 且两侧健康，属于澄清；新增的当前侧缺失行使示例总数为九。 |
| P6-S0-F13：ordered 摘要的阶段、输入与预算 | **关闭** | §8.1（`:271`）删除上传路径对 ordered/occupancy 摘要的预计算，只在 assemble 按 pair 计算；§4.2（`:155`–`:157`）明确每 pair 一次、S1a 用 Python、S3 起用 Rust，成本归 e 项。与 §16.1（`:411`）S1a/S3 的检查点一致，满足 §7.6 关闭标准。 |
| §4.2 新增来源和实施约束 | **与 §7.3 一致，无新矛盾** | 当前侧来源按 MODIFIED_ONLY、FULL 两个相邻 pair、History 各 pair 的 current commit 区分；checkpoint artifact reader 与 S2b 起 IPC reader、History 精确 commit Dolt 兜底，和 §7.3 的输入路径一致。仍按两侧描述符构造策略、使用规范行及 blank provenance、填充既有 facts 并保留 degraded 语义，也明确禁止复用 `_compare_single_side`；没有重开 F1/F11/F12。 |
| 其他已关闭项 | **未重审** | r4 只检查其对 ordered 单侧计算的影响；上述 §4.2 约束维持 §7.3 已核实的方案，没有改变已关闭项的结论。 |

### 8.4 本次实际执行的检查

| 检查 | 命令/方法 | 结果 |
| --- | --- | --- |
| 目标快照与变更范围 | `git status --short --branch`、`git rev-parse HEAD`、`git diff --stat 0adc2459739e910b3c595ed3c1ea16bb43b3b507 40d4ea78995441297895fd411044d6f2b6924c57 -- docs/backend-vnext/refactoring/formal/plans/p6-design.md docs/backend-vnext/refactoring/formal/plans/p6-execution-plan.md docs/backend-vnext/refactoring/formal/plans/p6-s0-independent-docs-review.md` | review worktree 为目标完整 SHA；r4 差异限于三份指定文档；本次最终改动仅审核报告。 |
| 公式、例子与关闭标准 | `nl -ba`、`sed -n` 阅读 §7.4、§7.6、设计 §4.2、§8.1、§16.1–§16.2、执行计划 S0 与 P5 §8.8；人工手算 | 两个 History 对照分别为 1 次与 0 次 Dolt 读取；原八例逐项核对；未运行测试或代码静态检查。 |
| 报告补丁格式 | `git diff --check` | 仅检查审核报告补丁的空白格式；无代码或测试检查。 |

### 8.5 验证限制与剩余前置

本轮是定向文档复核，不验证实现、性能或测试结果；没有据此声称实现门禁通过。owner 接受 S0 并授权 S1a 后，S1a kickoff 前仍须完成业务评估（重要 keyless 表是否有自然键）与计划列出的 kickoff 小修：`uv-consume.sh` EXIT trap、SQLite `-wal`/`-shm` 残留、讨论稿文档整理，以及由 RS owner 排查 defunct `dolt` 进程并决定是否并入。报告不替 owner 作出这些决定。

### 8.6 复审记录

| 原 finding | 关闭情况 | 依据 |
| --- | --- | --- |
| P6-S0-F5 | **关闭** | §16.2 逐 pair 列出 old-X/current-X、D、未变 ordered 单侧摘要和整表打包的独立需求，再按存储 miss 计算 Dolt 读取；当前侧单独 miss 的新反例为 1，两侧健康对照为 0，原八例保持成立，满足 §7.4 关闭标准。 |
| P6-S0-F13 | **关闭** | §8.1、§4.2 与 §16.1 对 ordered 摘要的唯一计算位置、输入、Python→Rust 阶段和 e 项预算归属一致，满足 §7.6 关闭标准。 |

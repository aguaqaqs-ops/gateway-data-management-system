# Phase 6 S0 Owner 决议记录

- 状态：**已决议**（repository owner，2026-10-24 至 2026-10-25）。本记录是 Phase 6 设计与执行计划的输入。它不直接修改 Contract 版本或 ADR 状态，相应修订在各阶段按“落点”进行；本记录也不构成实现授权。
- 决议人：repository owner
- 记录人：Phase 6 S0 讨论的审核方。依据讨论稿各项分析与 owner 的逐项答复整理。
- 依据：
  - [Phase 6 规划讨论稿](p6-planning-discussion.md) r21（提交 `206f4816c2`），以下简称“讨论稿”；
  - [P5 S0 Owner 决议记录](p5-arch-closure-s0-owner-decisions.md) 中与 Phase 6 相关的 DC35（目标设定方法）与 DC36（测试节点三台分工）。本记录的编号接续为 DC37–DC55。
- 补充：2026-10-25 owner 决议 G6b 维持 C 并增加门禁 worktree 的保留规则（DC51），以及现有 Rust 扩展视为过时、直接以新设计测试（DC52），见 §2 末尾；DC48、DC50 相应修订。
- 补充：2026-10-25 owner 决议 W1–W4 目标数值定稿与达标条件（DC53），以及逐行记录的生成与序列化进入 Rust（DC54），见 §2 末尾。
- 补充：2026-10-26 独立文档审核后 owner 修订决议为 DC55；S0 文档（详细设计与执行计划 r4）经首次审核与三次复审通过（[S0 独立文档审核](p6-s0-independent-docs-review.md)），由 owner 接受；实现授权范围见执行计划 §2 S0。

```yaml
record_kind: p6_s0_owner_decisions
decided_by: repository_owner
decided_at: [2026-10-24, 2026-10-25]
discussion_draft: p6-planning-discussion.md r21 @ 206f4816c2
decisions: DC37-DC55
prior_phase6_decisions: [DC35, DC36]   # 记录在 p5-arch-closure-s0-owner-decisions.md
adr_status_changed: no
implementation_authorized: no
```

## 1. 决议总览

| 编号 | 主题 | 讨论稿 | 讨论稿事项 |
| --- | --- | --- | --- |
| DC37 | Phase 6 与 Phase 7 的边界；implementation-stages §9/§10 改写；feature flag 只在接入期间保留 | §4 | A4 |
| DC38 | Submit 与 History 的目标；Submit 后首次 History 的命中路径；上传传输不计入 | §3.2、§3.8 | A2 |
| DC39 | 表摘要保值统一；Preview 只读、只比变化表（含 ordered） | §9 D1、D7 | B1、B5 第 1 项 |
| DC40 | 只增列的 schema 变化按共有字段判定 | §9 D9 | B8 |
| DC41 | bundle 补齐整表数据；整表新增或删除改为整表浏览加表级计数风险 | §9 D5、D7、§12 | B9、B5 第 2 项 |
| DC42 | 规范表存储：按内容寻址、两类引用、同步写入、不压缩 | §9 D2、D3 | B2 |
| DC43 | 计算去重与跨操作缓存；“分组分裂”拆出单独立项 | §9 D5 | B3、B4 |
| DC44 | 比较改为 Rust 列式实现 | §9 D7 | B5 第 3、4 项 |
| DC45 | Submit 只写变化；同内容表写入优化不做 | §9 D8、D10 | B6、B7 |
| DC46 | SQL 解析器主线与上传侧数据路径合并 | §6 | C1、C2 |
| DC47 | Rust 范围、并发与技术栈 | §5 | C3–C7 |
| DC48 | Rust 测试进入权威门禁；门禁时长先剖析 | §11 V8、§12、§13 D5/D6 | D5、D6 |
| DC49 | 慢速外网上传的接收限制 | §3.2、§12 | — |
| DC50 | Phase 6 阶段结构与前置验证任务 | §8.1、§11 | D3 |
| DC51 | G6b 维持 C；门禁 worktree 保留到阶段 exit 合入之后 | §12 | — |
| DC52 | 现有 Rust 扩展视为过时，直接以新设计测试 | §9 D1、§12 | — |
| DC53 | W1–W4 目标数值定稿与达标条件 | §3.3 | A1 |
| DC54 | 逐行记录的生成与序列化进入 Rust（S3） | §5.4 | — |
| DC55 | 独立文档审核后的决议修订（F1–F5） | — | — |
| DC56 | keyless 表的自然键与处理角色（DC50 业务评估） | — | — |
| DC57 | 行级修改按批渲染（S1a 阈值停止后的处理） | — | — |
| DC58 | 快照身份不含逐行快速摘要；删除 `fast_row_digest` | — | — |
| DC59 | S1a 归因的验收粒度 | — | — |
| DC60 | S1a 初审修订：语句字节规则与重跑范围 | — | — |
| DC61 | worker 在 step 完成后立即唤醒；镜像构建脚本的锁快照清理 | — | — |

## 2. 决议详情

### DC37 Phase 6 与 Phase 7 的边界

- **来源**：讨论稿 §4、§13 A4。implementation-stages §9 的目标、推荐顺序、进入与退出条件与已定方向不符：生产链路目前是纯 Python，唯一的 Rust consumer 不可达，Phase 6 是 Rust 首次进入生产链路；accepted baseline 状态机已被 Performance Measurement 3.0.0 废除。
- **决议**：
  1. **Phase 6 管单个 operation 的延迟**，以 DC35、DC38 的目标与结构性计数断言为退出条件。手段包括 operation 内部的表级与数据级并行、operation 内并发读取 Dolt（受单任务上限 N 约束），以及自身目标需要的缓存。缓存机制只用内容寻址、现有保护表、TTL、ADR 0012 的协作清理与读取时校验。
  2. **Phase 7 管多个 operation 的吞吐与资源**：槽位上限 K、公平调度、排队状态、多项目扩展测量、多 worker（重新设计启动租约判定）、跨 operation 的 RS 资源队列与单 repository writer、其他共享瓶颈、按容量淘汰与多项目缓存治理、统一并发预算与背压。按容量淘汰只在 Measurement Contract §6 的存储测量显示需要时才做。
  3. **Phase 6 含一个 Contract 阶段**（DC50 的 S1a、S1b）。其中的业务语义修正不是性能工作；按 Measurement Contract §5，前后结果不作为性能收益比较。
  4. **feature flag**：各 Rust 路径接入期间保留，可退回 Python 参照实现；Phase 6 退出时删除生产开关，Python 降为测试用参照（差分测试与小数据 oracle），生产不保留双路径。
  5. **阶段改名**：Phase 6 为“单任务性能与 Rust 接入”，Phase 7 为“多项目并发与容量”。
- **修订**：implementation-stages §9 中“Phase 3 首批 Rust provider 已通过真实纵切验证”“Slice 5B 已产生 accepted vNext baseline”两条进入条件，以及“Rust provider 可通过 feature flag 回退”的退出条件，由本决议取代。
- **落点**：implementation-stages §2、§9、§10，按讨论稿 §4.2 的改写要点修改，随本记录同期提交。

### DC38 Submit 与 History 的目标

- **来源**：讨论稿 §3.8、§13 A2。S5（t4）：History 893 s，其中比较 39 s，大头是两个节点各自从 Dolt 全量读取并在 Python 中物化；Submit 566 s，同一份 replay SQL 直接导入 Dolt 约 24 s。
- **决议**：
  1. **History 分三种负载，门槛为用户可见时间（2× t4）**：
     - H1 相邻首查（上一 commit 与 head，规则集未变，Submit 后首次查询）≤ 60 s；
     - H2 冷查询（派生缓存全部未命中）≤ 5 min，草案，S5 用两节点 2× t4 冷读验收定稿（V7 参考：一个已热的 t4 commit 8 并发读完约 26.7 s，[V7 报告](p6-v7-dolt-report.md)）；
     - H3 重复查询（TTL 内）≤ 15 s；
     - 三节点在 H2 条件下补测一次，只报告，受 10 min 硬上限。
     - 计数断言：TTL 内的 H1 与 H3，Dolt 读取次数与比较次数均为 0；TTL 外的 H1，Dolt 读取次数等于旧节点的变化表数。
  2. **Submit 的门槛为完成时间**（从受理到 Submission 提交成功、main 已前移）：S1 首次 Submit 与 S4 几乎全变 ≤ 5 min，S3 少量变化 ≤ 2 min，所有 Submit ≤ 10 min。结构性门槛为 DC45 的计数断言；原样重传不产生 Repository operation。
  3. **Submit 后首次 History 的命中路径**：表缓存（DC42）、diff/risk 缓存（DC43）与导出缓存（DC41）都在 Preview 与 Submit 的链路上形成。旧 head 的变化表在 head 前移后按 TTL 保留，TTL 从最后一次引用起算；diff/risk 条目由 Submit finalize 在移动 head 的同一事务中登记引用。
  4. **FULL 模式的 Preview** 没有直接计算“基线 → 修改”，其后首次 History 的 diff/risk 缓存不命中、对变化表重算。**接受**，不在 Preview 中多算一个 pair。
  5. **上传传输不计入** DC35 的两个时间指标：“受理”在整个上传包接收完毕之后。旅程另行记录上传耗时，只报告。
  6. **测量安排**：在 DC35 的合成 2× t4 旅程上接着跑，统计规则同 DC35；清空派生缓存模拟冷启动。
- **落点**：Phase 6 设计、测量 runbook；讨论稿 §3.8。

### DC39 表摘要保值统一与结构性过滤

- **来源**：讨论稿 §9 D1 审核分析（r4）、§9 D7。每张表现有四种摘要；`raw_content_digest` 已与行顺序无关，Dolt 读回能重算出同一个值；manifest `content_digest` 依赖源顺序，不能用于“只读变化表”；哈希本身不是瓶颈。ordered 表在比较中从不提前退出，重传、v2 与 History 中约 40 s 基本是这部分。
- **决议**：
  1. 以现有 `raw_content_digest`（SHA-256）作为唯一的表摘要；manifest 的内容摘要统一为同一个值，storage projection version 从 2 升到 3。
  2. 去掉重复计算；`CommitCanonicalMetadataPort` 返回每表摘要，作为 DC35 结构性门槛“未变化的表不读基线、不做比较”的前提。
  3. Preview 用基线 commit 的每表摘要过滤，只读、只比变化表；未变化的 ordered 表同样不读、不比，`before/current_ordered_digest` 改为取自表摘要或 manifest 并去掉表名。**（DC55 第 1 项修订：ordered 逻辑摘要与 occupancy 摘要定义不变；未变化的 ordered 表用当前侧的行按本次有效 pair 策略计算，不读基线侧，manifest 不新增字段。）**
  4. 不采用 BLAKE3。只有在 Rust 化之后哈希实测占比明显时才重新考虑，且只用于新的、带算法标签的摘要类型。
  5. 规范状态摘要、snapshot 与 bundle digest、HTTP DTO 与真实数据的规范状态摘要基准都不变；变化的是 manifest digest（随之体现在 PreviewResult、Submission 记录与 checkpoint 中）。
- **设计阶段待定**：ordered 表的统一口径（现 manifest 摘要不含结构列，`raw_content_digest` 含全部规范列与伪 gid）；是否保留 `ordering_digest`；是否删除 `fast_row_digest`（删除会改变 snapshot digest）。（`fast_row_digest`：由 DC58 决定删除，快照身份改为只用不读行即可得到的表级事实。）
- **落点**：Canonical Storage §4（内容摘要定义与 projection version）、ADR 0019 的 commit 元数据端口、相关 golden（storage-projection、mutation）；DC50 的 S1a。

### DC40 只增列的 schema 变化按共有字段判定

- **来源**：讨论稿 §9 D9。业务数据中数十张表同时只增列；testdata1（data1 → data2）中 32 张表只增列、2 张 ENUM 标签扩展、没有减列或主键变化。
- **决议**：
  1. 只增列不算 diff、没有风险：每张表按两个版本的共有字段判定变化与风险，不降级。
  2. ENUM 标签扩展（只增加标签、已有标签全部保留，插入位置不限）与 SET 成员扩展算兼容，同样不算 diff；删除或改名标签仍按不兼容处理。
  3. 只减列保持现行（`SCHEMA_CHANGED`，`MEDIUM_HIGH`）。
  4. 后端与入库照常处理并可登记 schema 变化；Submission 与 History 结果不列出新增列；全部变化都是只增列时，Preview 不提示“提交仍会生成版本”。
  5. 比较能力为两侧都存在的表计算 schema 演进分类（`NONE`、`COLUMNS_ADDED`、`COLUMNS_REMOVED`、`INCOMPATIBLE`），作为比较 facts 的稳定字段保留，为以后的触发事件（例如告警）预留；现在不建事件总线、通知状态机或订阅配置。
  6. 表摘要不增加每列摘要字段。
  7. ~~testdata1 登记为真实数据档 W5~~（2026-10-25 取消，owner 确认）：testdata1 的 data1、data2 与 t3 的 v1、v2 数据包逐字节相同（2026-10-25 核对），S5 的真实数据旅程已覆盖。t3 即 schema 演进样本，不另行登记；本记录与讨论稿中其余提到 testdata1 之处均指 t3。
- **已知后果**：只增列改变规范状态，`NO_CANONICAL_CHANGE` 不成立，提交后仍生成版本，须写入 Contract；新增列的值在本期不受风险检查。
- **落点**：Comparison、Risk、Surface Contract 与相应 golden；DC50 的 S1b。

### DC41 bundle 补齐整表数据；整表新增或删除改为整表浏览

- **来源**：讨论稿 §12（标准模式 bundle 不含整表数据）、§9 D5、§9 D7。代码核对：`application/pair_pipeline.py` 只在 DATASET_REPLACEMENT 模式下向 surface 传入表 ref，标准模式的 Preview 与 History bundle 不含整表 Parquet，与 owner 的“数据全量打包发送客户端、客户端不依赖服务端”原则及 comparison-bundle 契约不一致。整表新增时逐行产出 `ROW_ADDED` 记录与逐行风险标注，t4 首次上传约 25 万条，比较 148 s 与风险 27 s 主要在这里。
- **决议**：
  1. Preview 的 bundle 包含全部表（含未变化的表）；History 每个节点都包含全部表。整表优先从表缓存读取，未命中读 Dolt 并按 TTL 回填。客户端不向服务端按需取数。
  2. bundle 中的表文件仍用 Parquet；导出结果按“表摘要 + Parquet writer 版本”缓存，按 TTL 管理。**（DC55 第 2 项修订：导出缓存键为 row-layout 身份加 writer 版本。）**
  3. 整表新增或删除：表状态仍为 `ADDED_TABLE` / `DELETED_TABLE`；不产出逐行记录；风险改为一条表级标注，证据中带行数；surface 用整表浏览（新增表浏览 `current_table_ref`，删除表浏览 `before_table_ref`）。前端的表浏览须能在表级展示风险。两侧都存在的表不受影响。
  4. 第 3 项依赖第 1 项，二者在同一阶段落地。
- **落点**：comparison-bundle 契约（跨 operation 的 snapshot Parquet cache 改为按表摘要命中）、Comparison、Risk、Surface Contract 与 golden；DC50 的 S1b。

### DC42 规范表存储

- **来源**：讨论稿 §9 D2、D3 及其审核分析（r7）。现有表文件为 zstd Parquet 加 JCS manifest、ID 随机、写后立即读回；读取把整个文件读成 bytes，与 mmap 零拷贝不兼容；“projected snapshot 写入 153 s”主要花在 Python 编码、压缩与回读。
- **决议**：
  1. 一个按内容寻址的存储，两类引用，直接用现有保护表（`artifact_protection_intents`）实现，不新增状态机：临时引用即现有的 Preview owner；正式引用新增一种 owner 类型，**只绑定项目当前的 BaselineHead**，head 前移时在同一 control DB 事务里移到新 head。更早 commit 的表由 Dolt 兜底读取、按 TTL 回填，不挂正式引用。
  2. 规范表文件在 Preview 中**同步写入**；T1 照旧冻结 MODIFIED 侧的规范表集合闭包与 manifest，Submit prepare 照旧读冻结产物，ADR 0019 与设计 §4.6 的结构不变，闭包条目改为指向按内容寻址的文件。
  3. 文件**不压缩**，用 Arrow IPC，mmap 读取。
  4. 内容地址由 storage projection version、business schema digest、行数、表摘要（DC39）与 Arrow 映射版本组成，不含表名；文件内的行按规范顺序存放。
  5. 读取时在 mmap 上校验 raw SHA-256，不符按缺失处理，从 Dolt 读取并重写；写入用临时文件加原子 rename，删除写后回读。**（DC55 第 3 项修订：只适用于已提交表的派生副本；T1 冻结的未提交产物缺失时稳定失败。）**
  6. 复用已有文件时，TTL 从最后一次引用起算；先登记保护，再确认文件存在。
  7. 格式切换随 DC46 的上传侧数据路径一起做。
  8. 若实际使用中“查询较早 commit”的 History 很常见，重新评估“正式引用只保留 head”。
- **设计阶段待定**：磁盘需求估算（每个项目的 head 体积加 Preview TTL 副本）与参考节点磁盘容量；超出预算时再评估 LZ4；上传侧原始表在 checkpoint 恢复之外是否还有使用方（没有则不再持久化，见 DC46）。
- **比例化保障**：没有新增独立状态机、证据机制或 helper；丢失或损坏由读取校验加 Dolt 兜底处理，只影响性能。
- **落点**：Canonical Storage §5 的格式与生命周期、设计 §4.6 的闭包条目格式；DC50 的 S2b。

### DC43 计算去重与跨操作缓存

- **来源**：讨论稿 §9 D5。按原始 SQL 统计，同内容表组的去重在单次操作内可省约 10–20% 的比较量；t4 与 testdata1 中同内容表组的分裂与合并都是 0。
- **决议**：
  1. 只有纯函数可以缓存：单表比较结果与“未套用 pair 上限之前”的单表风险标注，是“去掉表名与显示名之后的整个单表任务输入”的纯函数；表名、显示名、标注编号、pair 上限与组合信号表在汇总步骤绑定。写入 Comparison 与 Risk Contract。
  2. 缓存键取上述任务输入的摘要，含不含表名的规则主体 digest、两侧有效键与存储规则、schema digest、行数、算法与记录格式版本、artifact scope；不手工列字段。
  3. 单次操作内去重随 DC44 实施；跨操作缓存（History 的 diff/risk 缓存）实现排在 DC44 之后，以 DC38 的 History 目标验收；diff/risk 条目按 TTL 保留，不沿 commit 链长期保留。
  4. 权威测试：同一输入，开启与关闭去重，facts 与 records 的摘要相同。
  5. “分组分裂”风险信号与 ruleset 中“预期相同的表族”声明**拆出单独立项，不进 Phase 6**。重开条件：业务方提出需求，或出现因分组分裂漏报风险的实际案例。
- **落点**：Comparison、Risk Contract；DC50 的 S3、S5。

### DC44 比较改为 Rust 列式实现

- **来源**：讨论稿 §9 D7。
- **决议**：
  1. 用 Rust 加 arrow-rs，不引入 Polars。
  2. 先做 standard 与 keyless；ordered 待前置验证 V1 的结论。**V1 结论（owner 2026-10-25 确认）：ordered 在 S3 与 standard、keyless 一起进入 Rust，** 共用规范编码、共有列投影、行身份、记录排序、资源上限与 facts 管线，ordered 专属的 LIS 主干、绝对 `no` 位置与空白区间规则留在 ordered 模块内（[V1 报告](p6-v1-ordered-prototype-report.md)）。
  3. Python 实现作为参照实现，按 §6.3 的差分分层验证；分歧点（浮点 -0.0、NULL、字符串按字节排序、记录输出顺序、ordered 并列规则）先写进 Contract。
  4. 列式实现须同时满足 DC40 的语义。
- **落点**：Comparison Contract；DC50 的 S3。

### DC45 Submit 只写变化

- **来源**：讨论稿 §9 D8、D10。现有 Submit 每次重写全部表：prepare 用 `REBUILD_ALWAYS` 规划但传入的“变化前”为空，schema SQL 为每张表生成 `DROP` + `CREATE`，与 Storage Mutation Contract §2“每个变化表生成完整重建”不符；plan child 231 s 主要花在逐行构造变化集对象与没有消费方的摘要上。RS 在从 expected parent 建立的私有 ref 上执行 `replay.sql`，并用整个 catalog 与包 manifest 做 STRUCTURAL 校验，已支持只写变化。真实数据中变化表的行级变化比例两极分布。
- **决议**：
  1. **表级跳过**：prepare 拿 T1 冻结的上传侧 manifest 与 expected parent 的 manifest 逐表比较，内容摘要、schema 摘要、键与存储视图都相同的表不进入 `replay.sql`；删除的表照旧 `DROP`；parent 为 INITIAL、缺少 metadata 或投影版本不同时全部按变化处理；包 manifest 仍列出全部表。
  2. **按阈值行级修改或整表重建**：生产 policy 从 `REBUILD_ALWAYS` 改为 `ADAPTIVE_PATCH`；有序表（GID_NO_V1）纳入行级修改，以 `gid` 为存储键、`no` 作为普通列更新；keyless 表（DC29）与 schema 变化的表（含 DC40 的只增列）仍整表重建。阈值（owner 2026-10-25 按 V7 修订）：**1,000 行 / 1%**；V7 实测逐行修改约 9 ms / 条语句、整表重建约 0.11 ms / 行，交叉点约为表行数的 1.2%，原草案 5% 比重建慢约 4 倍。S1a 用实际渲染器（INSERT 与 DELETE 可成批）与 RS 回放路径复测，S4 定稿（[V7 报告](p6-v7-dolt-report.md)）。行级 diff 所需的基线优先从规范表存储读取，Dolt 兜底；存储 diff 与比较共用列式内核。**（DC55 第 5 项修订：阈值与批量规则在 S1a 冻结，S4 调整须作为例外交 owner。）**
  3. **不复用 Preview 的比较结果**：Preview 的结果按前端语义生成（共有列、比较排除列、风险预算截断），不能替代存储变更。
  4. **渲染直通**：变化表直接从冻结的规范 Arrow 表渲染 SQL，导入路径不再构造逐行变化集对象、不计算没有消费方的摘要；表级决定仍归规划器。
  5. **保留通用规划器与 ChangeSet Contract**，作为 ADR 0014 外部目标的 Contract owner。外部分区库（按表类型汇总所有项目的数据，用于加速查询）只作预留，不排优先级。
  6. **正确性前提**：expected parent CAS、从存储读出的基线按 parent manifest 摘要校验、ADR 0009 的受信 Repository。按比例化保障政策，不另加条件 DML 或提交后回读校验。
  7. **计数断言**：`replay.sql` 涉及的表数等于变化表数；行级语句数等于行级修改表的变化行数。**（DC55 第 5 项修订：只断言逻辑数量，公式见设计 §16.2。）**
  8. **同内容表在 Dolt 中的写入优化（B6）不做**（V7：混合写入估算约 4.5 s，Dolt 写入只占 t4 Submit 的 0.8–2.8%，重开条件不成立）：估算最多省约 4–5 s，且要修订跨 Backend 与 Repository Service 边界的包格式。重开条件：本决议完成后 Submit 仍达不到 DC38 的目标，且实测 Dolt 写入占比明显。
- **落点**：Storage Mutation Contract §2/§3、ADR 0014（生产默认 policy）、Canonical Storage §6.1（`replay.sql` 是相对 expected parent 的确定性 replay）、T1 冻结的 `builder_mutation_policy`、prepare checkpoint 增加 parent manifest 摘要绑定、包 golden；RepositoryImportArtifact 包格式与 Repository Service Contract 不变。表级跳过与阈值方案在 DC50 的 S1a；渲染直通与列式存储 diff 在 S4。

### DC46 SQL 解析器主线与上传侧数据路径合并

- **来源**：讨论稿 §6。现有解析 0.54 MiB/s；t4 v1 Preview 上传侧四段（解析 140 s、物化 212 s、投影与摘要 219 s、snapshot 写入 153 s，合计 724 s）都是逐行 Python；只换解析器、再把 Arrow 转回 Python 行（36.5 MiB/s），收益会被抵消。
- **决议**：
  1. SQL 解析器作为 Phase 6 的主线并提前（DC37 修订 implementation-stages 中“最后单独评估 SQL parser”的排序）。
  2. **数据路径合并、Contract 不合并**：每张表在 Rust 中依次完成解析（table_access）、业务列与检查（snapshot_materialization）、规范投影（storage_projection）与表摘要，数据始终是 Arrow；三个 capability 仍各自拥有语义与诊断，模块依赖不变。composite signal 留在 Python，先在 Arrow 上按特殊设备过滤，只把命中的行转成 Python。
  3. 上传侧原始表不再写 Parquet，物化步骤崩溃后从 SourcePackage 重算；设计中逐一核实没有其他使用方。
  4. 差分验证：解析结果逐值对照为主判据，下游摘要对照为端到端判据；类型化值完全相等；错误路径要求诊断码、表与语句位置相同，**错误消息文本不要求相同**；语料五层，第 ④ 层为 t1–t4 与 testdata1。1 个线程与 N 个线程、不同分块大小的输出逐字节相同。
  5. V6 原型的验收：第 ① 层语料子集与 t4 第 ④ 层差异为 0；并行确定；2× t4 约 160 MB 的 SQL 在固定 N 下解析 ≤ 10 s，单线程吞吐只报告。达不到时先重新评估方案。
     **结果（2026-10-25，[V6 报告](p6-v6-parser-prototype-report.md)）：** 通过。语料 118 例与 t1–t4 两版 8 份真实数据（3,389 万个值）差异为 0；1–32 线程、1 B–1 MiB 块输出逐字节相同；ct108 上 2× t4 单线程 1.25 s、32 线程 0.28 s；解析器单独的暂定 N 为 4（并行效率 0.65）。
  6. Arrow 列映射在设计阶段定稿：表摘要按规范标量编码计算，与 Arrow 物理类型无关；映射单独加版本号。
  7. 不做覆盖引导 fuzz（cargo-fuzz 需要 nightly，Rust safety policy §2 禁止）；用 stable 上的 proptest 做 Rust 侧属性测试，加上 Hypothesis 差分。
- **落点**：讨论稿 §6；DC50 的 S2a、S2b。

### DC47 Rust 范围、并发与技术栈

- **来源**：讨论稿 §5、§9 D6。
- **决议**：
  1. **模块拆解**（讨论稿 §5.4）：解析、物化检查、规范投影与表摘要为一条 Arrow 数据路径；比较按 DC44；Submit 存储 diff 与 SQL 渲染与比较共用列式内核；风险 facts 不进 Rust（V5 显示占比明显时重开）；History 读取与 bundle 导出不新建 kernel。（DC54 补充：比较 kernel 同时产出逐行记录的 Arrow 列与 `content_digest`，Python 只写 Parquet。）
  2. **Rust core 不写文件**（Rust safety policy §4）：core 只产出 Arrow 结果或在内存中编码的 IPC 字节，由 Python 的 ArtifactStore 落盘；读取由 pyarrow mmap 后经 Arrow C Stream 交给 Rust。
  3. **crate 结构**：一个 core crate 加一个 PyO3 adapter；core 内按 capability 分模块，由 `gateway-architecture-check` 约束依赖方向；`gateway-compute-worker` 按需，不建。
  4. **并发分层**：按表并行（L2）是唯一主机制，随各 kernel 一起做；FULL 模式的双侧物化与双 pair 并入 L2；基线读取与解析重叠（L1c）、表内分块（L3）按实测条件再做；operation 之间并行属 Phase 7。每个 kernel 必测 1 个线程与 N 个线程的输出逐字节相同。
  5. **并发上限**：每个 worker 进程一个固定 N 的 Rayon 池，启动时建好、所有 kernel 共用；N 按 DC35 的加速曲线取值，设计阶段先用 V6 给暂定值。按预估内存准入，同时运行的任务总和不超过 M；单表超过 M 时以资源预算诊断稳定失败。Rust 长调用释放 GIL（沿用 `py.detach`）并定期检查取消与截止时间。pyarrow 的 CPU 与 I/O 线程池在 worker 启动时按 N 设定。测试环境默认 N=1，只有一致性测试显式比较 1 与 N。（V1 参考：t4 变化 ordered 表的 Rust 进程峰值从 1 线程的约 191 MiB 增至 16 线程的约 1.2 GB，32 线程比 16 线程慢；M 的准入估算与 N 的取值应计入这一点。）
  6. **对 RS 的并发读取**（owner 2026-10-25 按 V7 补充）：RS 的逐表读取许可池容量为 8，超出时以 503 立即拒绝、不排队。operation 内对 RS 的并发读取不超过 RS 的容量，由客户端信号量控制；503 作为背压，退避后重试，不作为失败。多个 operation 共享该许可池，跨 operation 的分配归 Phase 7。
  7. **调度配置**：部署配置只开放 N 与 M，可修改、有范围校验、写进测量记录；小表阈值、LPT 成本系数、L3 分块大小为代码常量，随实现版本校准。调度信息不放进 ruleset，不参与任何摘要。
  8. **技术栈**：新增 rayon、memchr、arrow-ipc（=59.1.0，不开压缩 feature）、arrow-row、arrow-ord、arrow-select（=59.1.0）、proptest（只作 dev-dependency）。不引入 Polars、BLAKE3、自定义内存分配器、criterion。Python 侧不加依赖。
- **落点**：讨论稿 §5、§9 D6；Phase 6 设计。

### DC48 Rust 测试进入权威门禁；门禁时长先剖析

- **来源**：讨论稿 §12、§13 D5/D6；[节点核对报告](p6-node-init-report.md) §4–§7。权威 runner 不运行任何 cargo 命令；backend 以路径依赖引用 maturin 构建的扩展，uv 默认只在 `pyproject.toml` 等变化时重建，只改 Rust 源码时 Python 测试可能运行旧的扩展（推断，待验证）；`cargo test` 失败的一例源于 adapter 测试嵌入 Python 解释器并写死 venv 路径。全量门禁约 39 分钟，主要在 backend 与 repository_service 的串行批次。
- **决议**：
  1. Rust 测试进入权威门禁，作为 Phase 6 开工的前置任务，在 V1、V6 之前完成（按 DC52 修订：现有扩展不再迁移，以下各项按新设计从一开始建立）：
     - 新扩展需要 Python 解释器的测试用 pytest 测已安装的扩展，不在 Rust 中嵌入解释器；现有 `adapter_errors.rs` 等随旧扩展删除，不迁移，也不再验证旧扩展是否过时；
     - 权威 runner 增加第六个包 `rust`（`cargo fmt --check`、`cargo clippy --workspace --locked -- -D warnings`、`cargo test --workspace --locked`，离线，`CARGO_TARGET_DIR` 在 worktree 外），闭包 manifest 相应增加；
     - 保证 Python 测试使用当前扩展（`tool.uv.cache-keys` 或强制重装），门禁增加一条构建输入一致性检查；新扩展同样以 maturin 路径依赖装入 backend 环境，uv 不重建的问题依然存在。
  2. runner、AGENTS 与 testing-conventions 的修改由负责 DC36 的会话实施。
  3. 门禁时长不阻塞 Phase 6。先做 V8 剖析（2026-10-25 完成，[V8 报告](p6-v8-gate-profile.md)；owner 决定测试基础设施阶段暂不插入，S2b 之后重新剖析）；只采用不削弱门禁证据的改法，预计缩短约 40% 以上时才作为测试基础设施阶段插入。backend 与 repository_service 跨节点分开运行涉及 AGENTS 的规则，归负责 DC36 的会话。
- **落点**：run-tests.sh、test_input_closure.py、AGENTS.md、testing-conventions（DC36 会话）；讨论稿 §11 V8。
- **实施（2026-10-25）**：第 1 项已完成，实施提交 `4526084da1`，handoff 见 [p6-dc48-handoff.md](p6-dc48-handoff.md)，轻量审核通过，见 [p6-dc48-review.md](p6-dc48-review.md)。选用强制重装（`--reinstall-package`）；构建输入以 `vnext/rust` 的 Git tree id 嵌入扩展并在 runner 中检查。节点 05 的反例实测确认：只改 Rust 源码时 `uv sync` 不重建扩展。owner 同日确认 `cargo test` 在 S2a 之前同时排除 `gateway-compute-python-impl`（其测试同样嵌入 Python 解释器）。

### DC49 慢速外网上传的接收限制

- **来源**：讨论稿 §3.2、§12。上传带宽从局域网千兆到外网不足 3 Mbps 不等。代码核对：上传接收已流式化、async，Preview operation 在受理之后才创建，worker 不空等网络；但整次上传有固定 60 s 总时限（`FIXED_UPLOAD_STREAM_TIMEOUT_SECONDS`，超时返回 413），1 Mbps 下 t4 包已很勉强；受理在事件循环上同步解压校验整个包；准入闸门在整个上传期间占用名额。
- **决议**：
  1. 改为空闲超时（连续 60 s 没有收到数据）加总上限；**最低支持带宽 1 Mbps**，总上限按“最大压缩包 ÷ 1 Mbps”推出（256 MiB 约 36 分钟）；超时使用独立的错误码，不再返回 413。
  2. 范围：256 MiB 是 Preview 上传（第一阶段，SQL 与 XML 核心数据）压缩包的上限，不是 Submit 的限制。Backend 到 RS 的导入包另有服务端内部上限。各项上传上限会随业务变化调整，总时长上限随之按 1 Mbps 重新推算；这些上限现为代码常量，调整需随版本修改。
  3. 受理中的同步工作移到线程池，在 Phase 6 中修复。
  4. 准入名额的占用交给 Phase 7。
  5. 不做“边收边解析”。
- **落点**：HTTP Contract（新错误码）、`application/workspace/upload_limits.py`、`http/orchestration/`；DC50 的 S1b。

### DC50 Phase 6 阶段结构与前置验证任务

- **来源**：讨论稿 §8.1、§11、§13 D3。
- **决议**：
  1. **排序原则**：先改 Contract、再改性能，Contract 阶段之后重建一次对照基准，之后的纯性能阶段结果须与基准逐字节一致；每类 golden 只改一次；按依赖排序。
  2. **S0（开工前）**：本记录与 implementation-stages 改写；kickoff 小修（`uv-consume.sh` 的 EXIT trap、SQLite 旁路文件残留、三项文档整理）；DC48 第 1 项；前置验证 V1、V5、V6、V7（V8 并行，不阻塞）；重要 keyless 表是否定义自然键的业务评估，在 S1b kickoff 之前给出（owner 2026-10-26 修订：原为 S1a 之前；补键改变规范键与比较结果，属于 S1b 冻结的比较类 golden，故截止点改为 S1b kickoff 之前，S1a 不等待）；Phase 6 设计、执行计划与独立文档审核。
  3. **实施阶段**：
     - **S1a 摘要与存储 Contract**：DC39；DC45 的表级跳过与 `ADAPTIVE_PATCH`（用现有规划器）；阶段结束、重建对照基准时对完整 worker step 做归因（DC53 第 2 项）。
     - **S1b 业务语义 Contract**：DC40、DC41、DC49 第 1、3 项；生成合成 2× t4 并写入测量 runbook；参照实现的输入边界缺陷（V6 报告“需要澄清的语义”第 3、9 项：BIT 负数、超宽 BIT、非 ASCII 的 `b'..'` 与深层嵌套 JSON 抛出未捕获的异常）的修复，以及 FLOAT 两次舍入（第 1 项）与其余语义问题（第 2、4–8 项）的定稿（owner 2026-10-25 决定在 S1b 完成；S2a 不同时改语义和换实现）。**（DC55 第 4 项修订：零日期维持拒绝；FLOAT 修复在 Shared Kernel。）**
     - **重建对照基准**：用 Python 实现，在 `ct108-gw-dms` 上测 t1–t4、testdata1 与合成 2× t4。
     - **S2a 解析器**：完整的 Rust 解析器与五层差分，放在 feature flag 之后，不切生产；同时删除现有 Rust 扩展（DC52）。
     - **S2b 上传侧数据路径与表存储**：DC46 第 2、3 项；DC42；DC47 第 5 项；切换生产。
     - **S3 比较**：DC44；DC43 的单次操作内去重；DC54 的逐行记录由 Rust 生成。
     - **S4 Submit**：DC45 的渲染直通与列式存储 diff；按 V7 定稿阈值。
     - **S5 History 与跨操作缓存**：DC43 的跨操作缓存；History 按表拼接；Dolt 按表并发读取。
     - **S6 收尾**：加速曲线定 N；删除生产 feature flag；2× t4 全部负载取证（W1–W4、H1–H3、S1–S4、计数断言）；存储报告（Measurement Contract §6）；Phase 6 退出。
     - 测试基础设施阶段按 DC48 第 3 项可选插入。
  4. **真实数据（DC33：kickoff 写明，退出时 owner 确认）**：S1a、S1b 为 t1–t4 与 testdata1 完整旅程；S2a 只做解析结果逐值差分；S2b 至 S5 为 t1–t4 与 testdata1 端到端摘要与基准一致，并测本阶段相关负载；S6 为 2× t4 全部负载（1 次预热加 3 次测量）与 t1–t4 完整旅程。t1–t3 与 testdata1 在 `ct108-gw-dms-05`，t4 与测量在 `ct108-gw-dms`。
     - **补充（owner，2026-10-25）：** 允许在 `ct108-gw-dms-05` 上使用 t4，用于正确性对照（例如 V6 的逐值差分）。05 上自克隆起就有 t4 的两个数据包（`/home/dev/gateway-real-dumps/packages/`），DC36 生效记录写的是“05 保留 t1–t3”，与实际不符，以此为准。性能测量与 t4 的完整旅程取证仍在 `ct108-gw-dms`。
  5. **门禁**：沿用 AGENTS、DC30、DC33、DC34、DC36、G12、G13；每个阶段的最终提交运行一次权威 runner（含 `rust` 包）；改动 Rust 或镜像时重建 backend 镜像并跑容器门禁；阶段边界打 `p6-sN-exit` 附注 tag。
  6. **前置验证任务**：
     - V1 ordered 比较的小规模 Rust 验证，决定 ordered 是否进 Rust（2026-10-25 完成并以 merge commit `102c857f7e` 合入 main，见 [V1 报告](p6-v1-ordered-prototype-report.md)）；
     - V5 operation 级耗时归因，先用 step 时间戳，不足时用 py-spy（2026-10-25 完成，见 [V5 报告](p6-v5-attribution-report.md)）；
     - V5b 分段补测（owner 2026-10-25 补充）：不加产品插桩，只扩展测量工具，补测基线 commit 全量物化、完整 bundle 组装、Submit prepare 的 build input 解析与 checkpoint 序列化四段；S1 之后重建对照基准时沿用；
     - V6 SQL 解析器原型，按 DC46 第 5 项验收（2026-10-25 完成并以 merge commit `863330e757` 合入 main，见 [V6 报告](p6-v6-parser-prototype-report.md)）；
     - V7 Dolt 回放（整表重建与行级修改的耗时，核对两条路径的表哈希相同）与 Dolt 读取吞吐、并发读取加速比，用于 DC45 阈值与 DC38 H2 门槛定稿（2026-10-25 完成，见 [V7 报告](p6-v7-dolt-report.md)）；
     - V8 门禁耗时剖析（DC48）。
     - V3（Dolt 同内容表写入）与 V4（同内容表组统计）不再是前置任务，随 DC45 第 8 项或 DC43 第 5 项重开时再做。
- **落点**：Phase 6 设计与执行计划；讨论稿 §8.1、§11。

### DC51 G6b 维持 C；门禁 worktree 保留到阶段 exit 合入之后

- **来源**：讨论稿 §12；[治理修订计划](p5-arch-closure-post-s1-governance-plan.md) G6b；[P5 exit review](p5-exit-review.md) §6/§7。同一提交在两个 worktree 中构建出的 backend/worker 镜像 ID 不同（权限位与未跟踪的残留目录进入镜像），carried 只能在原门禁 worktree 中判定。owner 2026-10-11 选 C；P5 exit 时因 G10 清理按计划删除了门禁 worktree 而 fresh 全量，终审判断未触发重新评估条件。
- **决议**（repository owner，2026-10-25）：
  1. **维持 C，不重新评估。** 理由：
     - 原 A 方案（为 backend 镜像加身份 label，替代比较 image ID）已不对题：DC34 之后 carried 比较的是闭包 manifest，剩下的问题是 manifest 本身依赖 worktree（本地权限位与 Docker context 中的非 Git 内容）；
     - Phase 6 几乎每个阶段都改 backend 或 Rust，backend 闭包每次都变，按规则必须实际运行，backend 的 carried 很少用到；DC36 已把门禁与 carried 固定在门禁节点的同一 worktree；
     - 上次触发由流程造成，可以用流程避免（第 2 项）。
  2. **流程规则：** 阶段的门禁 worktree 保留到该阶段 exit 合入之后再清理。
  3. **重新评估：** 条件不变（独立审核需要在门禁 worktree 之外复核 carried，或再次因此多跑一次完整门禁）。真要做时，目标改为“与 worktree 无关的闭包 manifest”（接近原 B 方案：用 `COPY --chmod` 等消除权限位依赖，context 只取已跟踪文件），由负责 DC36 的会话负责。
- **落点**：第 2 项写入 Phase 6 执行计划；如需写入 AGENTS 或 testing-conventions，由负责 DC36 的会话实施。

### DC52 现有 Rust 扩展视为过时，直接以新设计测试

- **来源**：owner 2026-10-25。现有扩展（`gateway-compute-python` 与 `canonical_row_hash`）在生产中不可达（P5 exit review §6.1）；讨论稿 §9 D1 曾建议复用其 Rust `canonical_row_hash` 内核，让 Rust 先进入生产链路。
- **决议**（repository owner，2026-10-25）：
  1. 现有 Rust 扩展视为过时，不迁移、不复用；测试直接面向新设计。
  2. **DC39 的表摘要统一（S1a）用 Python 实现**，不复用旧的 Rust 内核；Rust 从 S2a 开始进入。
  3. **DC48 简化：** `cargo test` 在 S2a 之前排除 `gateway-compute-python` 与 `gateway-compute-python-impl`（后者由 owner 2026-10-25 确认）。 旧扩展的测试（含嵌入解释器的 `adapter_errors.rs`）随旧扩展删除，不迁移成 pytest，也不再验证旧扩展是否过时；新扩展从一开始按 DC48 的方式建立测试与构建一致性检查。V1、V6 的原型直接建在新代码上。
  4. **删除时机为 S2a：** 删除 `capabilities/canonical_row_hash`、`gateway-compute-core` 中的旧 pipeline、PyO3 adapter 的旧入口、`canonical-row-hash` golden、Canonical Row Hash Compute Boundary Contract、`native_kernel_component.sh`，以及引用它们的测试与架构基线条目。backend Dockerfile 的 maturin 构建步骤保留，改为构建新 crate；在 S2a 新旧替换，镜像始终能构建，也不出现 Rust 完全不在生产链路的空窗期。
- **落点**：DC48、DC50 已相应修订；S2a 的执行计划。

### DC53 W1–W4 目标数值定稿与达标条件

- **来源**：DC35 第 4 项约定 W1–W4 草案数值在 V5、V6 完成后定稿。V5、V5b、V6、V7、V1 已完成（讨论稿 §2.3、§11）。按已定方案估算（2× t4、N=4）：计算部分 W1 约 35–45 s、W2 约 30–35 s、W3 约 40–50 s、W4 约 45 s 加记录与风险；另有两项固定开销——每个 Preview 两处 step 间隔合计约 18 s（V5；worker 空闲轮询为 1 s，不能解释），以及 V5b 未归因的 worker step 残差约 175 s（基线物化约 75 s、assemble 固定约 100 s）。逐行记录的生成与序列化在 Python 中约 1.3 ms/条（V5b）。
- **决议**（repository owner，2026-10-25）：
  1. **定稿数值（2× t4，用户可见时间）：** W1 ≤ 3 min、W2 ≤ 30 s、W3 ≤ 60 s、W4 ≤ 3 min，维持 DC35 草案；完成时间 ≤ 10 min 硬上限、FULL 模式在 W3 与 W4 各补测一次、统计方法均不变。S2b 之后有实测再考虑收紧 W1、W3；调整须经 owner 确认。
  2. **W2 的前置条件：** S1a 结束、重建对照基准时，对完整 worker step 做归因，查清 step 间隔与约 175 s 残差的来源；测量工具仍无法归因时，由 owner 决定是否增加产品插桩。W2 能否达标取决于这两项能否消除，若 S2b 证明其中一项是物理下限，再由 owner 决定是否调整。
  3. **W4 合成规则：** 在已有基线上，全部表都有变化，每表约 10% 的行变化（插入、删除、修改混合，ordered 表包含位移）；另设一档“每表 100% 行变化”的压力测试，只报告、不设门槛。规则写入测量 runbook。
- **修订**：DC35 第 4 项的“草案”由本决议定稿；第 7 项的 W4“扰动全部表”由第 3 项细化。
- **落点**：测量 runbook；DC50 的 S1a（第 2 项）与 S1b（合成 2× t4 与 W4 规则）；讨论稿 §3.3。

### DC54 逐行记录的生成与序列化进入 Rust（S3）

- **来源**：V5b：v1 Preview 的 250,471 条逐行记录，records closure 生成约 318 s、写后全量回读约 95 s，约 1.3 ms/条，全部在 Python 中（`capabilities/comparison/artifacts.py`：逐条构造 dict 并做规范 JSON 编码，用 `from_pylist` 转回 Arrow 写 Parquet，写后整份解码回 Python 行重算摘要）。DC41 去掉了整表新增或删除时的逐行记录，但两侧都存在的表仍逐行产出；按 DC53 的 W4 规则约 5 万条，100% 行变化时约 50 万条（约 11 分钟）。DC44、DC47 的 Rust 范围只覆盖比较本身。
- **决议**（repository owner，2026-10-25）：
  1. Rust 比较 kernel 直接按记录族的 schema 产出 Arrow 记录列，并用与现行实现相同的 JCS 规范编码计算 `content_digest`，与 Python 逐字节相同。
  2. Python 只用 pyarrow 把 Arrow batch 直接写成 Parquet，不经过逐行 dict；manifest 与 closure 的形态不变。
  3. 写后回读校验改由 Rust 对读回的 Arrow 重算摘要，或按 DC42 第 5 项（删除写后回读）的思路删除，在 Phase 6 设计中二选一。
  4. 记录的逻辑内容、`content_digest` 与 manifest 不变，Comparison 与 bundle 的 Contract 不改；现有 golden 作为逐字节回归基准。若设计中发现必须改动记录产物格式，按 Contract 变更另行提交 owner。
  5. 风险标注仍留在 Python（DC47 第 1 项）。
- **落点**：DC47 第 1 项的模块拆解、DC50 的 S3；讨论稿 §5.4。

### DC55 独立文档审核后的决议修订（F1–F5）

- **来源**：[S0 独立文档审核](p6-s0-independent-docs-review.md)（结论：定向修订；8 项阻塞）。其中 F1–F5 揭示决议条文之间或与完整 Contract 之间的冲突，须由 owner 修订决议本身。
- **决议**（repository owner，2026-10-26，接受审核方与作者的建议）：
  1. **未变化 ordered 表的 facts（F1，修订 DC39 第 3 项；2026-10-26 按第 1 次复审 F11、F12 再修订）：** Ordered Diff 定义的 ordered 逻辑摘要与空白区间的 occupancy 摘要**定义不变**。对满足“未变化”完整条件的 ordered 表，两侧内容相同，比较 facts 用**当前侧的行**、按**本次受理冻结的有效 pair 策略**（含两侧共有列）计算，两侧取同一值；不读基线侧，也不运行完整比较算法。Preview 的当前侧即内存中的上传侧；History 的当前节点表本来就要为整表打包读取（DC41），健康缓存命中时直接用 diff/risk 缓存。**manifest 不新增 ordered 字段**（取消第 1 次修订中“写入 manifest”的做法）。comparison、surface 与 bundle digest 在 S1a 保持不变（DC39 第 5 项成立）。
  2. **完整表身份（F2，修订 DC41 第 2 项）：** 导出缓存键改为现有 row-layout 身份（行内容 + 导出 schema + repository scope）加 Parquet writer 版本，不只用表摘要。Preview 与 History 判定“未变化”统一使用完整条件：表摘要、schema digest、存储视图与投影版本都相同。
  3. **冻结产物的恢复边界（F3，修订 DC42 第 5 项）：** “读取校验失败即从 Dolt 读取并重写”只适用于已提交表的派生副本（从对应的精确 commit 回填）。T1 冻结、尚未提交的规范表：T1 之前可从 SourcePackage 重算（重跑 Preview）；T1 之后、prepare 之前缺失或损坏时稳定失败、不移动 main（与现行 artifact 行为相同）；PREPARED 之后复用已冻结的导入包。
  4. **零日期（F4，修订 DC50 中 S1b 的语义定稿范围）：** Phase 6 维持现行的稳定拒绝，不接受零日期与零日期时间；真实数据出现时另行立项（届时须同时修订 Shared Canonical Encoding、Repository Service 的 Arrow 映射与客户端解码）。FLOAT 两次舍入的修复由 Shared Kernel 的标量规范化承担（`shared_kernel/scalar.py`），S1b 路径预算包含 shared_kernel 及其编码 golden。
  5. **计数口径与字节冻结（F5，修订 DC45 第 2、7 项）：** 计数断言只针对逻辑数量，不针对 SQL 语句数：规划器的逻辑变更数按 Storage Mutation §4 计（同键 UPDATE 计 1 次，键变化计 DELETE + INSERT 2 次）；表按“变化、新增、删除、未变”四类给出公式（设计 §16.2）；去重或缓存命中后的实际 kernel 调用数单独记录，只要求不超过逻辑派发数。行级修改阈值与 INSERT 批量规则在 S1a 实测后冻结；S4 对同一输入做 `replay.sql` 逐字节回归；若 S4 实测必须调整阈值，作为明确例外交 owner 决定，并在 S4 更新包 golden。
- **落点**：DC39、DC41、DC42、DC45 及 DC50 S1b 的对应条目已注明“DC55 修订”；[详细设计](p6-design.md) 与 [执行计划](p6-execution-plan.md) r2。

### DC56 keyless 表的自然键与处理角色（DC50 业务评估）

- **来源**：[keyless 候选键普查](p6-keyless-candidate-census.md)（t1–t4 的 v1、v2 共 8 份数据，35 张 keyless 表，只含计数与列名）与[规则讨论稿](p6-keyless-candidate-rules-review.md)；S0 讨论会话审核意见。普查没有发现 DC29 清单以外的新表。
- **决议**（repository owner，2026-10-26）：
  1. **逐表显式键（11 张表）：** `comm_user_data` 用 `data_key`；`forwardtbl_lst_*` 系列（cs、dz、qt、yc、yk、ym、yt、yx 共 8 张）用 `tbname`；`mms_rp_cdc_index` 用 `idx`；`out_time_cfg` 用 `(board, link_no)`。这些表由 keyless 改为 keyed，比较给出字段级变化，Submit 可走行级修改。显式键是严格规则：之后数据中键列出现重复或 NULL 时，该表投影稳定失败，不回退 keyless。`out_time_cfg` 与 4 个 `forwardtbl_lst_*` 系列在现有数据中均为空表，键按业务语义指定，不是数据验证的结果。`forwardtbl_lst_*` 的选择器形式（8 个精确名或系列正则）在 S1b kickoff 确认。
  2. **18 张含 `(no, page_no)` 的表按 BROWSE_ONLY 处理，存储保持 keyless：** `cnt_manage_cfg`、`dev104_cfg`、`iec101_cfg`、`iec104_cfg`、`iec104gw_cfg`、`iec61850c_cfg`、`jdxx_cfg`、`nbridge_cfg`、`nr103d_cfg`、`nr103ht_cfg`、`sc_cfg`、`scada_cfg`、`sg_manage_cfg`、`sntp_cfg`、`vqc_cfg`、`wave_cfg`、`wf_cfg` 新加入 BROWSE_ONLY 名单，`project` 已在名单中。不为 BROWSE_ONLY 增加存储键，不拆分存储键与比较键，Contract 不变。owner 接受业务后果：这些表变化时不再产生逐行记录与风险，只有表级变化事实（DC16）与整表浏览。
  3. **列存在兜底暂不实施：** 按列集合自动选键、校验失败回退 keyless 及额外处理调用，Phase 6 不实施，也不预留接口。DC29 的 keyless 兜底继续处理新表；需要键的新表按规则激活补显式规则。**重开条件：** 出现新的 keyless 表，且业务上需要字段级比较。
  4. **`forwardtable_*` 保持现状并做一次专项调查：** 6 张 `forwardtable_*` 继续命中 SNAPSHOT_ONLY、keyless 存储、不做比较；不引入 `KEYLESS_ORDERED`。由实施者做一次专项调查（只输出计数与列状态分类，不输出单元格值），确认：完全相同的重复行是否都是空点行；非空点行的 `gid` 是否唯一；源数据中的行顺序是否与 `gid` 顺序一致。结论由 owner 确认；若发现重复行不全是空点行，或行顺序有业务含义且无法由 `gid` 恢复，作为 Phase 6 之外的单独立项。
- **第 4 项调查结论**（[`forwardtable_*` 空点行调查](p6-forwardtable-blank-rows.md)；repository owner，2026-10-26）：
  1. **数据结果：** 22 个有重复的表/数据组合中，完全相同的重复行都属于同一列状态模式（`gid`、`devaddr`、`fun`、`inf`、`icseq` 为 0，`fcda` 为空串，`desc` 非空），共 6,177 行，没有单独出现的同模式行；除去这些行后 `gid` 唯一且无 NULL；源顺序中 `gid` 在 30 个组合里有 27 个出现下降（共 10,242 处），空点行 6,176 行夹在正常点之间、1 行在表尾。
  2. **owner 确认：** 该模式是业务上的空点行；行位置有业务含义，源顺序不能由 `gid` 恢复。但 `forwardtable_*` 是实际转发表（ordered 表）的模板，当前没有业务用途，只保存作参考；必要时可用同源的对应 ordered 表恢复顺序（owner 的业务判断，本次调查未比对 ordered 表）。
  3. **处置：** 维持 SNAPSHOT_ONLY、keyless 存储、不做比较；owner 接受这些表的存储与导出不保留源行顺序。不引入 `KEYLESS_ORDERED`，不另行立项。**重开条件：** 模板开始被实际使用（例如用于生成转发表，或导出交付设备），需要保留行顺序时，另行立项设计保序存储，并届时验证能否由对应 ordered 表恢复顺序。
- **落点**：S1b 实施第 1、2 项的规则改动（`capabilities/table_rules/` 名单与规则；规则集版本提升），storage-projection 组中的规则集与 manifest golden 随之在 S1b 更新一次（[详细设计](p6-design.md) §4.6 的例外行）；第 4 项的调查不改规则，不阻塞 S1b。

### DC57 行级修改按批渲染（S1a 阈值停止后的处理）

- **来源**：[S1a handoff](p6-s1a-handoff.md)（S1a 按设计 §17 第 4 项停止）。t4 v2 的 1% 有序表样本 `b1_n11_iec104_syx_list`（98/9,828 行）：行级修改三轮中位 1.458 秒，整表重建 1.239 秒，修改慢约 17.7%。整表重建约 40 条语句（一条整表 DELETE 加按批 INSERT），行级修改每行一条语句（92 条 UPDATE 加 1 条 INSERT），每条约 15 毫秒，主要是单条语句的固定开销；这张表的盈亏点约 83 行（0.85%）。t4 v2 整体回放中，行级修改 3.2 秒、整表重建 27.4 秒，两者的 Dolt 表哈希与当前结果全部相同（312/312）。
- **决议**（repository owner，2026-10-26，选择 B）：
  1. **行级修改按批渲染：** 渲染器把同一表的逐行 UPDATE 与 DELETE 合并为按批语句，INSERT 沿用每条最多 256 行、4 MiB 的规则；UPDATE 与 DELETE 的批量上限在 S1a 实测后与 INSERT 规则一同冻结。规划器的逻辑变更与 §16.2 的逻辑计数口径不变，只改变渲染出的语句形式与条数。
  2. **语句形式由预检选定：** 在固定的 Dolt 版本上先用合成表预检候选形式（例如按批 `DELETE … WHERE 键 IN (…)` 加按批 INSERT，或按批 upsert），覆盖单列键、复合键与有序表（GID_NO_V1）；选定形式须满足：语法可执行、查找走主键而不是全表扫描、结果的 Dolt 表哈希与逐行形式相同、Dolt 中同键行显示为修改。预检不满足时停止，交 owner。
  3. **正确性前提不变：** 仍为 expected-parent CAS、parent 行按 parent manifest 校验与受信 Repository（DC45 第 6 项、ADR 0014 修订）；不新增条件 DML 或 affected-row 检查。若选定 upsert 形式，“目标行不存在时插入”由上述前提排除，与现行逐行 UPDATE 不检查影响行数的处理一致。
  4. **阈值保持 1,000 行 / 1%：** 按批渲染后在同一样本上复测。仍慢于重建时退回 A：按实测盈亏点降低比例阈值，作为本决议的例外交 owner 确认。
  5. **阶段归属：** 语句合批从 S4 的“渲染直通”提前到 S1a；mutation 组 golden 随之在 S1a 更新（属于 S1a 组）。S4 的渲染直通对同一输入逐字节回归 S1a 的按批产物。
- **落点**：[详细设计](p6-design.md) §4.3、§17；[执行计划](p6-execution-plan.md) §2 S1a 第 3 项。

### DC58 快照身份不含逐行快速摘要；删除 `fast_row_digest`

- **来源**：[S1a handoff](p6-s1a-handoff.md)（S1a 第二次停止）。04 门禁中 History Compose 测试发现 comparison digest 不保值。原因是设计层面的冲突：仓库侧快照的 snapshot digest 对每张表都包含 `fast_row_digest`，它只能读出整表的行才算得出来；而 §4.2 要求 Preview 基线与 History 旧侧不读未变化表的行。实现以提交元数据中记录的 snapshot digest（Submit 时按上传侧计算，物化阶段不同）代替，导致摘要不同，并使同一身份有两种算法。规范状态摘要本来不含 `fast_row_digest`，代码注明它只用于诊断；snapshot digest 的其余每表输入都可以从目录与 manifest 得到。
- **决议**（repository owner，2026-10-27，选择 B；修订 DC39 中“是否删除 `fast_row_digest`”的结论）：
  1. **快照身份：** snapshot digest 的每表输入只用不读行即可得到的表级事实：表名、比较 schema 摘要、业务 schema 摘要、比较键、行数与表摘要。仓库侧未变化的表由目录与 commit manifest 生成表描述，不读行，须与读行得到的描述逐字段相同。Preview 基线、History 两侧与上传侧用同一算法；删除以提交元数据摘要代替计算的做法。
  2. **删除 `fast_row_digest`：** 计算、表描述字段、checkpoint 序列化、manifest 与 Contract 条文一并删除。原始状态摘要去掉它后，若与规范状态摘要重复且没有独立使用方，一并删除；有独立使用方时保留并列明。
  3. **摘要值一次性改变：** snapshot digest、原始状态摘要，以及包含它们的 comparison、surface、bundle digest 在 S1a 改变一次，是设计 §4.1 保值清单与 §4.6 golden 生命周期的例外；snapshot-materialization golden 与上述组中的摘要值在 S1a 更新。规范状态摘要、ordered 逻辑摘要、occupancy 摘要与 HTTP DTO 形状保值。没有兼容要求，不保留旧摘要算法或双算。
  4. **核对方式：** 摘要值改变的产物，屏蔽三类字段：摘要与哈希字段；由摘要派生的内容寻址标识（`artifact_id` 等引用）；运行实例字段（operation、workspace、pair 等 ID，时间与耗时，随机生成的 artifact ID，以及包含这些值的路径）。屏蔽后与改动前逐字节相同，并顺着引用逐个加载被引用的产物（records closure 与各记录族、风险、surface、bundle 成员、导出表），按逻辑角色（表名、记录族、产物种类）对齐，用同一口径比较内容，覆盖 HTTP DTO。范围分两类：内容应保值的产物（比较记录与 facts、风险、surface、bundle、snapshot-materialization 内容、HTTP DTO 及其 golden）按上述口径核对，golden fixture 与真实数据（t1）都须相同；§4.1 列为变化的组（mutation、storage-projection、导入包）不要求相同，但每处差异须对应到 §4.1、§4.3 或 DC57 列出的变更，对应不上即停止；另证明仓库侧不读行的表描述与读行描述逐字段相同、规范状态摘要不变。
  5. **证据范围：** 设计与 Contract 直接写目标形态，被取代的机制与其测试一并删除（AGENTS 项目前提）。S1a 全部验收在最终候选上重新运行，不沿用此前候选的阈值、表哈希与旅程结果。
- **落点**：[详细设计](p6-design.md) §4.1、§4.6、§14、§17；[执行计划](p6-execution-plan.md) §2 S1a；DC39 对应条目注明由本决议取代。

### DC59 S1a 归因的验收粒度

- **来源**：[S1a handoff](p6-s1a-handoff.md)。诊断分支的结构化计时（不进入候选）把 v1、v2 assemble 与 Submit prepare 的耗时分解到子阶段：v1 assemble 723.0 s = checkpoint 读取 45.1 s + pair pipeline 625.5 s + bundle 51.4 s + 收尾 1.0 s；与 V5b 相比约 178.9 s 的差额来自 checkpoint 读取（V5b 不含）、pair pipeline +124.7 s（记录生成 +78.6 s、compare +38.3 s、风险 +7.7 s）与 bundle +8.1 s。v2 约 71 s 的差额主要是 checkpoint 读取 58.7 s。同一代码在 worker 中比 V5b 慢的原因（产物存储位置为 Compose volume 对比宿主机 scratch，或运行环境），现有测量不能确定。
- **决议**（repository owner，2026-10-27）：
  1. 设计 §4.4 的归因到阶段级即可：各子阶段耗时及与独立测量对应段的差额，每项给出处理方案、阶段与 owner。
  2. worker 与 V5b 在同一代码上的耗时差，作为性能诊断项登记：checkpoint 读取与产物写入归 S1b（产物/checkpoint），记录生成与 compare 归 S3（比较），在对应阶段的 kickoff 中列入。
  3. DC58 第 4 项的核对方式按设计 §4.1 的表述执行（屏蔽摘要、派生标识与运行实例字段，并顺着引用比较产物内容）。
  4. DC58 核对中 mutation 与 storage-projection 组的 16 处 golden 差异（阈值 `max_patch_change_ratio`、按批渲染的 `expected.sql`、`storage_projection_version` 与 `contract_version`）均对应已批准的 S1a 变更，不触发停止；核对范围按设计 §4.1 分为“内容保值”与“列为变化的组”两类。
- **落点**：[详细设计](p6-design.md) §4.1、§4.4。

### DC60 S1a 初审修订：语句字节规则与重跑范围

- **来源**：[S1a 独立阶段审核](p6-s1a-independent-review.md)（结论：定向修订；F1 未变化 ordered 表仍运行完整比较与 LIS，F2 INSERT 可生成超过 4 MiB 的语句，F3 DC58 核对的屏蔽过宽且未覆盖 snapshot-materialization 内容）。4 MiB 是渲染器自定的分批上限，不是 Repository Service 或 Dolt 的硬限制（RS 读取单行上限为 64 MiB）；S1a 之前大行的 INSERT 与逐行 UPDATE 都能单独成句执行，S1a 的按批 UPDATE/DELETE 在单行超限时失败，属于退化。
- **决议**（repository owner，2026-10-27）：
  1. **语句字节规则：** INSERT、UPDATE、DELETE 统一：每条最多 256 行；多行批次按完整 UTF-8 语句（含 `;\n`）不超过 4 MiB，加入下一行会超限时先结束当前批次；单行本身超过 4 MiB 时单独成一条语句，不失败。前提是先在 05 用合成数据证明 5–8 MiB 的单行 INSERT 与 CASE UPDATE 经 RS 实际回放路径执行成功、表哈希与逐行形式相同；不成立时停止，由 owner 改为稳定失败。规则写入 Storage Mutation Contract。
  2. **重跑范围：** 修复 F1–F3 后的新候选重跑 S1a 验收（04 权威 runner 与镜像重建、t1–t4 旅程、阈值复测与 t4 v2 表哈希、DC58 核对）；worker step 归因不重跑，沿用 DC59 已接受的阶段级分解，F1/F2 对耗时的影响以新候选 t4 旅程的耗时为准。
  3. F1、F3 按审核建议修复：未变化 ordered 表直接构造两侧相同的 facts，摘要各算一次，不运行完整比较与 LIS；DC58 核对改用显式屏蔽字段清单，并补比较 snapshot-materialization 内容与规范表等产物。
- **落点**：[详细设计](p6-design.md) §4.3；[执行计划](p6-execution-plan.md) §2 S1a“证据范围”。

### DC61 worker 在 step 完成后立即唤醒；镜像构建脚本的锁快照清理

- **来源**：[S1a handoff](p6-s1a-handoff.md) 的 step 间隔归因（DC59）。`WorkerRuntime._run_claim` 在非 drain 状态下等待注入的 `wait`（即停止信号 `stop_requested.wait`），超时为距下一次 heartbeat 的时间；executor 结束时设置的完成事件在这条路径上无人等待，supervisor 要到下一次 heartbeat（默认 10 s）才发现 step 已结束。drain 状态下等待的是完成事件，没有这个问题。实测每个 step 边界 2.6–9.95 s，t4 一次完整旅程合计约 1 分钟，小档占比更高；这就是 DC53 中 W2 前置条件所指的 step 间隔。另在 S1a exit 清理时发现：`build-repository-service-image.sh` 创建锁快照后没有 EXIT trap，约 10 处提前退出都会留下快照文件；其错误路径测试未隔离 TMPDIR，每次权威 runner 在节点的 TMPDIR 留下若干文件（04 累计 147 个，已清理）。与 kickoff 修复的 `uv-consume.sh` 属同一类问题。
- **决议**（repository owner，2026-10-28）：
  1. **立即唤醒：** executor 结束（成功或抛出异常）时立即唤醒 supervisor，随即校验结果并领取下一个 step。runtime 持有一个唤醒事件，executor 结束与停止信号都将其置位；非 drain 等待改为等待该事件，超时仍为距下一次 heartbeat 或 drain 截止的时间；醒来后照常检查完成、drain 意图与 heartbeat 时间。不改成短间隔轮询。
  2. **不变项：** heartbeat 间隔 10 s、lease 时长与续约、drain 与 drain 超时语义、每个 worker 同时最多一个 executor 均不变；Operation Lifecycle Contract 的 lease/heartbeat 条款不改，不新增 golden。
  3. **测试：** `test_operation_worker_scheduler.py` 补行为测试，使用注入的时钟与事件，不依赖真实耗时（必须用真实时间时标 `serial`）：短 executor 完成后 supervisor 在 heartbeat 到期前返回且不发 heartbeat；执行中收到停止信号仍按现有规则进入 drain；长 executor 照常按周期发 heartbeat。
  4. **验收：** 由 control DB 的 step 时间戳计算 S1b 每档真实数据旅程（t1–t4）的 step 间隔（前一 step 完成到下一 step 开始）；不再出现接近 heartbeat 周期的等待，超过 1 s 的间隔在 handoff 中逐项说明。旅程耗时与 S1a 的对比只作记录，不另做归因。
  5. **锁快照清理：** `build-repository-service-image.sh` 用 EXIT trap 删除锁快照，覆盖全部退出路径；其测试把 TMPDIR 设为测试临时目录，并断言错误路径不留文件。该脚本属于镜像构建脚本，按 AGENTS 是强制重建项，S1b 最终候选照常重建并运行容器门禁。
  6. **阶段：** 两项均在 S1b 实施（owner 2026-10-28）。
- **落点**：[详细设计](p6-design.md) §4.4、§5.7、§16 的 j 行；[执行计划](p6-execution-plan.md) §2 S1b 第 7、8 项与 §3 路径预算。

## 3. 设计阶段待定项

| 项 | 所属决议 | 何时定 |
| --- | --- | --- |
| ordered 表摘要的统一口径；是否保留 `ordering_digest`；是否删除 `fast_row_digest` | DC39、DC58 | 已定：统一为表摘要，删除 `ordering_digest`（设计 §4.1）；删除 `fast_row_digest`（DC58） |
| W1–W4 目标数值定稿 | DC35 | 已定稿（DC53） |
| 记录写后回读：Rust 重算摘要或删除 | DC54 | Phase 6 设计 |
| H2 门槛定稿 | DC38 | S5 冷读验收（V7 已提供参考） |
| 行级修改的阈值定稿 | DC45、DC57 | S1a 按批渲染后复测并冻结（含 UPDATE、DELETE 批量上限；不达标时按 DC57 第 4 项交 owner）；S4 只做回归，须调整时作为例外交 owner（DC55 第 5 项） |
| Arrow 列映射 | DC46 | Phase 6 设计，结合 V1、V6 |
| 规范表存储的磁盘需求估算与参考节点磁盘容量；上传侧原始表是否还有其他使用方 | DC42、DC46 | Phase 6 设计 |
| ordered 比较是否进 Rust | DC44 | 已定（V1）：S3 进入 Rust |
| `ordered-diff.md` 中伪 gid 起点（20 亿）与 Canonical Storage G8（40 亿–4,294,967,295）的冲突 | DC39、DC44 | S1a 修订 Contract 时明确以 G8 为准（实现已按 G8） |
| N 的暂定值与定稿 | DC47 | V6 给出解析器单独的暂定值 4；整条路径的 N 在 S2b 后暂定，S6 定稿 |
| 合成 2× t4 的生成规则 | DC35、DC50 | S1b，写入测量 runbook |
| 重要 keyless 表是否定义自然键 | DC50 | 已定（DC56，2026-10-26）：11 张表补显式键，17 张表加入 BROWSE_ONLY，规则改动在 S1b；`forwardtable_*` 保持 SNAPSHOT_ONLY；空点行调查已完成，不另行立项（DC56 第 4 项结论） |

以下仍由 owner 另行决定，不属于本记录：GitHub 远程默认分支改为 `main`；Repository Service 容器中累积 defunct `dolt` 进程的排查（讨论稿 §12，交 RS 的 owner）。G6b 已由 DC51 决定维持 C。

## 4. 需同步修订的文档

| 文档 | 内容 | 时机 |
| --- | --- | --- |
| implementation-stages §2、§9、§10 | 按 DC37 与讨论稿 §4.2 改写，阶段改名 | 随本记录 |
| Phase 6 规划讨论稿 | 状态改为“已整理为 DC37–DC50”，§13 B1 改为已决议 | 随本记录 |
| Canonical Storage §4、§5、§6.1；ADR 0019 的 commit 元数据端口 | DC39、DC42、DC45 | 所在实施阶段 |
| Storage Mutation Contract §2/§3；ADR 0014 | DC45 | S1a |
| Comparison、Risk、Surface Contract；comparison-bundle 契约 | DC40、DC41、DC43、DC44 | S1b、S3、S5 |
| HTTP Contract（上传超时错误码） | DC49 | S1b |
| run-tests.sh、test_input_closure.py、AGENTS.md、testing-conventions | DC48；DC51 第 2 项（如需写入） | S0，由负责 DC36 的会话实施；交接说明见 [p6-dc48-rust-test-gate-handoff.md](p6-dc48-rust-test-gate-handoff.md) |
| Canonical Row Hash Compute Boundary Contract（删除）；backend Dockerfile 的 maturin 构建目标 | DC52 | S2a |

## 5. 后续步骤

1. 按 §4 第 1、2 行修订 implementation-stages 与讨论稿。
2. S0 前置项：kickoff 小修；DC48 第 1 项（DC36 会话）；V1、V5、V6、V7，V8 并行；keyless 自然键的业务评估。
3. 前置验证完成后，编写 Phase 6 设计与执行计划，进行独立文档审核。（2026-10-26：前置验证已全部完成；[详细设计](p6-design.md) 与 [执行计划](p6-execution-plan.md) 已起草，经独立文档审核与复审修订，见两份文档的状态行。）
4. 审核通过后进入 S1a。

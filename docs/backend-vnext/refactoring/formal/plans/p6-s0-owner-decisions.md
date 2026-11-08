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
| DC62 | S1b kickoff 确认：选择器形式、解析器语义、上传超时错误码、诊断项、真实数据范围与授权 | — | — |
| DC63 | S1b exit：N1-1 测量限制的处置与真实数据范围确认 | — | — |
| DC64 | 审核先行、证据后补；真实数据按受影响步骤重跑；结果一致的口径 | — | — |
| DC65 | Submit 等待 Repository 导入：健康等待不消耗恢复会话；人工恢复命令后的续行（S1c，修订 2026-10-30） | — | — |
| DC66 | 缩短测量与取证耗时：基准单次测量、预检查复用、失败从 checkpoint 续跑、S1c 证据收窄、工具修正常设授权（修订 2026-10-31：S1c ct108 改为 2× t4 完整旅程） | — | — |
| DC67 | 测试节点依赖获取：取证运行只用预填充缓存，代理仅限 05 调试构建 | — | — |
| DC68 | 工具/取证操作失误：首次失败后同一具体故障最多三轮自行修复复验（2026-11-08修订）；既有只读与代码传输准备不计次数澄清继续适用 | — | — |
| DC69 | S1c 并入 mutation planner 变更集排序缺陷的修复；ct108 改为 2× t4 三节点完整旅程 | — | — |
| DC70 | S2a 开发与重建对照基准的正式测量并行；S2a exit 在基准 exit 之后（补充 2026-10-31：节点占用标记） | — | — |
| DC71 | S1c exit：真实数据范围确认；DC70 的 S2a 起点澄清；startup 阻断遗留的登记 | — | — |
| DC72 | S2a kickoff 确认：O2 非有限 JSON 数值拒绝、旧实现删除范围、test-only 差分入口（生产 flag 移到 S2b）、parser 表内分块、adapter 命名、线程池分步 | — | — |
| DC73 | 后端会话分为设计与审核两个角色 | — | — |
| DC74（草案） | BE-c 体积报告放在 S6；整包下载单列只报告，不改 P6 门槛 | — | — |
| DC75 | BE-a 扩项：Workspace 占用指针与本人撤回权限；方向已确认，kickoff 审核通过、待实施确认 | — | — |
| DC76 | S2b 输入约定与映射准备：UTC 导出、来源/类型不变，纳入少数约 100 MB SQL；映射细则待审核 | — | — |
| DC77 | 容量设计输入：首版 1,000、长期 10,000 个独立设备仓库；年均每仓库 6–12 版；补充单项目 5 版/日假设压力与 500 仓库同日上传场景 | — | — |
| DC78 | Rust 替换验证后删除旧 Python 算法；无生产回退/双路径；语言按业务取舍，core 可复用，测试转为契约与固定向量 | — | — |
| DC79 | 基准输入工具预检、分段复用与多路生成；后续必要重开不默认单路全量 | — | — |
| DC80 | 基准停止后的主动诊断与最小修复；READY 闭包容量问题及限定的跨修正续跑 | — | — |
| DC81 | 开发与全量基准解耦，S2a exit 不再等待基准；性能目标可结合实测与物理限制讨论 | — | — |
| DC82 | 新增 06 后端与 07 前端开发测试节点；04/06/07 共享宿主，正式测量及权威门禁归属不变 | — | — |
| DC83 | S2b 功能退出与 W2 性能复核分开；30 秒目标保留，最迟 S6 收口 | — | — |
| DC84 | S2b 容量与 M 分步收口；CT108 无窗口时 W1 诊断最迟 S6 | — | — |
| DC85 | S2b kickoff 批准，启动 A 节纯内存映射/IPC codec | — | — |
| DC86 | 授权按既定 kickoff 逐节推进 B–E，每节新建既定实施/审核二角色；额外角色先交 Owner 确认 | — | — |
| DC87 | S2b 单 worker：完整 t3 校准后已选 32 GiB envelope、8 GiB reserve、显式 M=24 GiB，N=1/单 active；06 fresh t1–t3、04 最终门禁、t4 按独审沿用 | — | — |
| DC88 | 正常 drain 的 effect 前 PURE_RECOMPUTE 阶段可安全重排队，不消耗失败恢复次数；保留原 checkpoint/保护 | — | — |

## 2. 决议详情

### DC37 Phase 6 与 Phase 7 的边界

- **来源**：讨论稿 §4、§13 A4。implementation-stages §9 的目标、推荐顺序、进入与退出条件与已定方向不符：生产链路目前是纯 Python，唯一的 Rust consumer 不可达，Phase 6 是 Rust 首次进入生产链路；accepted baseline 状态机已被 Performance Measurement 3.0.0 废除。
- **决议**：
  1. **Phase 6 管单个 operation 的延迟**，以 DC35、DC38 的目标与结构性计数断言为退出条件。手段包括 operation 内部的表级与数据级并行、operation 内并发读取 Dolt（受单任务上限 N 约束），以及自身目标需要的缓存。缓存机制只用内容寻址、现有保护表、TTL、ADR 0012 的协作清理与读取时校验。
  2. **Phase 7 管多个 operation 的吞吐与资源**：槽位上限 K、公平调度、排队状态、多项目扩展测量、多 worker（重新设计启动租约判定）、跨 operation 的 RS 资源队列与单 repository writer、其他共享瓶颈、按容量淘汰与多项目缓存治理、统一并发预算与背压。按容量淘汰只在 Measurement Contract §6 的存储测量显示需要时才做。
  3. **Phase 6 含一个 Contract 阶段**（DC50 的 S1a、S1b）。其中的业务语义修正不是性能工作；按 Measurement Contract §5，前后结果不作为性能收益比较。
  4. **Rust 替换（2026-11-04 由 DC78 修订）**：不建设 Python 生产回退或双路径开关；替换期可临时差分验证，Rust 完成生产接入与验证后，在对应阶段删除被替代 Python 算法及重复测试，不长期保留完整旧实现作为测试参照。
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
  3. Python 实现在替换期作为临时参照，按 §6.3 的差分分层验证；分歧点（浮点 -0.0、NULL、字符串按字节排序、记录输出顺序、ordered 并列规则）先写进 Contract。DC78 修订后续生命周期：接入验证后删除被替代算法，Contract 与独立固定向量继续拥有语义。
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
     - **S6 收尾**：加速曲线定 N；按 DC78 核对各阶段被替代算法及临时差分设施已清理，不新建生产回退开关；2× t4 全部负载取证（W1–W4、H1–H3、S1–S4、计数断言）；存储报告（Measurement Contract §6）；Phase 6 退出。
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
  1. **逐表显式键（11 张表）：** `comm_user_data` 用 `data_key`；`forwardtbl_lst_*` 系列（cs、dz、qt、yc、yk、ym、yt、yx 共 8 张）用 `tbname`；`mms_rp_cdc_index` 用 `idx`；`out_time_cfg` 用 `(board, link_no)`。这些表由 keyless 改为 keyed，比较给出字段级变化，Submit 可走行级修改。显式键是严格规则：之后数据中键列出现重复或 NULL 时，该表投影稳定失败，不回退 keyless。`out_time_cfg` 与 4 个 `forwardtbl_lst_*` 系列在现有数据中均为空表，键按业务语义指定，不是数据验证的结果。`forwardtbl_lst_*` 的选择器形式在 S1b kickoff 定为 8 个精确名（DC62 第 1 项）。
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

### DC62 S1b kickoff 确认

- **来源**：S1b kickoff 确认项（DC56 第 1 项的选择器形式；设计 §5.4、§5.5 的 P 项；DC59 第 2 项；DC33 真实数据范围；执行计划 §2 S0 的分阶段授权）。解析器各项的证据见 [V6 报告](p6-v6-parser-prototype-report.md)“需要澄清的语义”；真实数据 t1–t4 中均无受影响的值。
- **决议**（repository owner，2026-10-28）：
  1. **`forwardtbl_lst_*` 选择器：** 8 个精确表名（`forwardtbl_lst_cs`、`_dz`、`_qt`、`_yc`、`_yk`、`_ym`、`_yt`、`_yx`），与其他显式键表同为 `STANDARD_EXACT`，不用系列正则。理由：显式键是严格规则，正则会让将来新出现、缺 `tbname` 列的同前缀表直接投影失败；精确名之外的表照常走默认规则。与 `forwardtable_*` 的 SNAPSHOT_ONLY 正则不重叠。
  2. **参照解析器语义（设计 §5.5）：**
     - a. BIT 列的十进制数字字面量按 MySQL 以十进制解释（`10` 得 `0x0a`）；超出声明宽度为 `SQL_VALUE_ILLEGAL`。
     - b. `_binary` 前缀：接受，后接字符串或十六进制字面量，按二进制值解析；只用于二进制类列（BINARY、VARBINARY、BLOB 系列），用于其他列为 `SQL_VALUE_ILLEGAL`；其他字符集前缀（如 `_utf8mb4`）仍为 `MALFORMED_SQL`。
     - c. 字符串中的 `\%`、`\_` 按 MySQL 保留反斜杠（各为两个字符）。
     - d. 列类型中夹的注释忽略，与 MySQL 一致。
     - e. JSON 中的 `NaN`、`Infinity` 拒绝，`SQL_VALUE_ILLEGAL`（表级）。
     - f. JSON 中的孤立代理（如 `"\ud800"`）拒绝，`SQL_VALUE_ILLEGAL`（表级）。
     - g. JSON 嵌套深度上限 100（与 MySQL JSON 最大深度相同），超过为 `SQL_VALUE_ILLEGAL`，检查不得递归；实施者以只出计数的方式确认 t1–t4 中 JSON 的最大深度远低于上限。
     - 已定项不变：BIT 负数、超宽 BIT、非 ASCII `b'..'` 改为确定诊断；FLOAT 直接舍入；零日期维持拒绝（DC55 第 4 项）。新增接受的写法用合成用例验证往返。
  3. **上传超时错误码（设计 §5.4）：** 两种超时共用 `UPLOAD_STREAM_TIMEOUT`，HTTP 408；原因字段取值只有 `IDLE`（连续 60 s 未收到数据）与 `TOTAL`（超过总上限）；413 只用于大小与资源限制。
  4. **DC59 第 2 项在 S1b 的处理：** 不设性能门槛。§5.2 改造 bundle 路径（补齐整表与导出缓存）后，handoff 记录 t4 的 checkpoint 读取与 bundle 段耗时，与 S1a 对比并说明差距是否消除；未消除部分转 S2b（规范表存储接管数据来源）。不在产品中加计时插桩，耗时由现有旅程输出与 step 时间戳计算。
  5. **真实数据范围（DC33）：** t1–t4 完整旅程（t1–t3 在 05，t4 在 ct108；t3 覆盖只增列）。另核对：t1–t4 的 step 间隔（DC61）；补键 11 张表的比较结果（重点为有数据的 4 张 `forwardtbl_lst_*`、`comm_user_data`、`mms_rp_cdc_index`）；新增 BROWSE_ONLY 的 17 张表的处理结果；重复导出命中导出缓存。
  6. **实施授权：** 授权 S1b，范围为设计 §5.1–§5.8 及对应的 Contract 与 golden 修订（含 DC56 规则改动、DC61）。
- **落点**：[详细设计](p6-design.md) §5.2、§5.4、§5.5、§17 开放项表；[执行计划](p6-execution-plan.md) §2 S1b；DC56 第 1 项注明选择器形式。

### DC63 S1b exit：N1-1 处置与真实数据范围确认

- **来源**：[S1b 终审](p6-s1b-final-review.md) §4。DC62 第 4 项要求 handoff 记录 t4 的 checkpoint 读取与 bundle 段耗时并与 S1a 对比，但限定只用现有旅程输出与 step 时间戳、不在产品中加计时插桩；S1a 的子段数值来自不进入候选的诊断分支（DC59），而 S1b 把 Parquet 导出移入 `materialize_inputs`，step 级数值无法与 S1a 的子段一一对应（审核 N1-1）。
- **决议**（repository owner，2026-10-29）：
  1. **N1-1：** 接受测量限制。S1b handoff 的 step 级记录视为满足 DC62 第 4 项在给定手段下可达的范围：t4 History API 312.889 s（S1a）→ 361.051 s（`materialize_inputs` 216.440 s、assemble 142.544 s），增加部分对应两节点各 312 张表整表导出与绑定的新 Contract 成本。checkpoint 读取与 bundle 子段的拆分转交“重建对照基准”，在 ct108 独占测量中以不进入候选的诊断计时完成；仍未消除的差距按 DC62 第 4 项转 S2b kickoff。S1b 不再为此修改产品代码。
  2. **真实数据范围（DC33）：** 确认 DC62 第 5 项的范围为 S1b 的真实数据证据：代码候选 `020deda2fd` 上的 t1–t4 完整旅程（t1–t3 在 05，t4 在 ct108），以及 step 间隔、补键 11 张表、BROWSE_ONLY 17 张表与重复导出命中缓存的核对（handoff 与终审 §3.2）。
  3. **不阻塞遗留项（终审 §4.3）：** 登记，不在本决议中定处置：O1（`bootstrap/operation_worker.py` 信号处理在主线程调用 `Event.set` 的窄自锁窗口，S1b 前已存在）列入 worker runtime 后续维护；O2（JSON `1e400` 经 `json.loads` 得到 inf，绕过 DC62 第 2 项 e 的非有限值拒绝）作为语义确认项列入 S2a kickoff。
- **落点**：[执行计划](p6-execution-plan.md) §2 S1b 状态与“重建对照基准”内容；[S1b handoff](p6-s1b-handoff.md) 状态。

### DC64 审核先行、证据后补；真实数据按受影响步骤重跑

- **来源**：S1b 在 5 个候选（80ce、705b、914、afb、020deda2）上各跑了一次完整 t1–t4 旅程，每轮墙钟约 1.6 小时（t1–t3 在 05、t4 在 ct108 并行）；04 上跑了 8 次权威 runner。其中 914、afb、020deda2 三轮发生在审核 finding（F1–F5）之后，而 F1–F5 都能用 focused 测试或合成复现发现，并不需要完整证据才能暴露。按 DC30 第一部分第 2 项与执行计划 §8.4，每次修订形成新 V 都要重跑完整 runner 与真实数据；F5 只改了 History 的物化路径，也重跑了全部旅程。DC33 已按包沿用 runner 结果，真实数据仍以整档为单位。
- **决议**（repository owner，2026-10-29）：
  1. **审核先行、证据后补**（修订 DC30 第一部分第 2 项的时点）：
     - a. 实施者调试收敛后交**代码候选**：focused 测试与五包静态检查、05 门禁前预检（[P5 执行计划 §8.9](p5-arch-closure-execution-plan.md)）、本阶段改动直接触及的那段真实数据（调试性质，不作证据），以及 handoff 的代码部分（改动清单、Contract 与 golden diff、测试归属、kickoff 范围内的计数断言）。此时不跑完整权威 runner 与完整真实数据。
     - b. 独立审核与复审只针对代码候选：读代码、复跑 focused、合成复现。finding 修订后的复审同样不要求完整证据。
     - c. 审核结论为**代码通过**后，在最终候选上运行一次完整权威 runner（按包沿用照常），真实数据按 kickoff 范围运行一次（DC33），容器门禁按 AGENTS 判定。
     - d. **证据复核**由同一审核会话完成：核对证据日志与验收项，不重审代码。证据暴露缺陷时，修订后按第 2 项重跑受影响范围，再做只针对该修订的短复审。
     - e. 例外：阶段验收本身就是真实数据或测量结论的（S2a 解析结果差分、S2b 的 W2 检查点、重建对照基准、S6 取证），相应的数据运行可在代码审核之前进行并作为审核输入；修订后的重跑仍按第 2 项处理。kickoff 列明的设计输入类普查与测量不受本项限制。
  2. **真实数据按受影响步骤重跑**（修订 DC30 第一部分第 2 项“在同一 V 上完整运行真实数据一次”）：
     - a. **来源运行**：某一档在候选 V 上的一次完整运行 R。要求 clean、已提交 worktree，日志记录 hostname、起止时间、起止 HEAD 与 exit 0，各步骤核对通过，并保存各步骤的状态。R 结束后其卷与状态不再写入（只读核对除外）；续跑在卷副本上进行，原卷保留到阶段 exit 合入之后（同 DC51）。
     - b. **适用条件**：V..H 的产品改动可以证明只影响部分旅程步骤。实施者在 handoff 中列出“改动文件 → 经过的 operation/step → 首个受影响步骤 k”的映射，由审核者核对。在 H 上构建镜像，在 R 的卷副本上从步骤 k 续跑 k 及之后的全部步骤；k 之前各步骤的证据取自 R。
     - c. **不适用**（须在 H 上完整重跑该档）：V..H 改动了持久格式或身份（Contract、checkpoint 或 manifest 载荷、digest、golden、control DB 或 Repository Service schema、artifact 格式）；改动了镜像边界（Dockerfile、Compose、依赖锁、entrypoint、环境变量接线）；改动了所有步骤共用的基础设施（worker runtime、operation 生命周期、artifact store、Repository Service）；或无法给出可核对的步骤映射。
     - d. **记录**：handoff 按档列出每个步骤证据的来源候选与日志。链式沿用直接引用最初实际运行该步骤的候选，不引用沿用结果（同 DC33 第一部分）。
     - e. **计时**：带门槛或作为基准对照的数值（设计 §16.3 负载、重建对照基准的对照项），若其测量路径受 V..H 影响，必须在 H 上实测；不受影响才可沿用，并写明依据。
     - f. **范围**：阶段 exit 可按本项绑定证据；S6 最终取证、Phase 6 退出与发布门禁须在最终 HEAD 上完整运行，与 AGENTS“镜像身份等价”的例外一致。
     - g. **工具**：`real_dump_journey.py` 在取证模式下保存步骤状态，并支持以新镜像在保留卷的副本上从指定步骤续跑。这属于 benchmarks 改动，按 DC30 第一部分第 3 项处理；该能力就绪之前，本项不适用。
  3. **不变项**：DC30 的调试与取证分开、DC33 的按包沿用与 kickoff 定范围、DC36 节点分工、AGENTS 的镜像身份等价与停止规则均不变。本决议不放宽任何验收项，只改变证据运行的时点与重跑范围。
  4. **补充：结果一致的口径**（repository owner，2026-10-29；细化 DC50 第 1 项的“逐字节一致”）：
     - 来源：重建对照基准阶段在 05 上做续跑验证时，来源运行与续跑的 History bundle 指纹不同。逐字段核对后，两份 History Surface 只有 `surface_id` 与 `view_id` 不同，两者都由 History operation ID 派生；其余内容（全部表、记录、风险、Parquet 绑定与行数）相同（05 `/home/dev/gdds-p6-logs/baseline/owner-h1-closure-attribution.log`）。
     - a. 产物内嵌运行实例标识时，“结果一致”指把这些标识替换为规范化占位（例如按序编号的 pair key）后逐字节相同。运行实例标识包括 operation、pair、surface/view、submission 与 artifact 的 ID，以及由它们派生的路径。
     - b. 屏蔽只限运行实例标识。业务内容与业务摘要字段不屏蔽；二进制产物（records rows、risk annotations、Parquet）、Dolt 表哈希与 canonical state 原样比较。
     - c. 屏蔽清单在对照工具中显式列出，工具输出实际被规范化的字段路径（不含值）。清单的任何增减都须在 handoff 中写明来源与理由。
     - d. 出现新的、无法从产物结构确定是运行实例标识的差异字段时，按不一致处理并停止，交 owner 判定。
- **落点**：[执行计划](p6-execution-plan.md) §8.2、§8.4；第 4 项落在重建对照基准的对照工具、runbook 与 handoff。AGENTS.md「主线开发与阶段边界」与 testing-conventions 由负责这两份文件的会话同步；主 checkout 中这两份文件另有未提交的修改，本次不改。

### DC65 Submit 等待 Repository 导入：健康等待不消耗恢复会话

- **来源**：重建对照基准在 ct108 上做 2× t4 warmup 时，v1 Submit 的 `await_import_result` 共进行 3 次 60 s 轮询（18:37:45、18:38:46、18:39:48，2026-10-29 UTC），Repository Service 每次都返回运行中；18:40:48 按 R5 转为 `MANUAL_RECOVERY_REQUIRED`。Repository Service 导入随后成功，用时约 3–5 min（诊断目录 ct108 `/home/dev/gdds-p6-logs/baseline/scenarios/compose/s4-stall-20261029T184249318055Z`）。
  - 规则出处：P4 R5 设计 §6（每个 step 最多 3 个恢复会话，单个会话内轮询 ≤ 60 s）；P5-5B 设计 §13.1（Submit 的 `SUBMIT_IMPORT_POLL_DEADLINE_SECONDS = 60.0`，每次轮询超时结束一个恢复会话，第三次进入人工恢复）。代码为 `operations/recovery.py` 的 `MAX_RECOVERY_SESSIONS = 3`、`RECONCILE_SESSION_BUDGET_SECONDS = 60.0`。
  - 余量此前已偏小：P5 退出审核记录 t4 的导入为 79/83 s，分别用了 2/3 个会话。
  - 问题实质：Repository Service 健康地返回“运行中”时，单次轮询到期被计为一次恢复会话，于是总等待上限固定在约 3 min，与导入规模无关。这一上限也短于 Repository Service 自身的导入上限（`import_timeout_seconds` 默认 3600 s）。在 Phase 6 目标规模下，Submit 无法自动完成，§16.3 的 S1/S3/S4 门槛（完成，main 前移）无法达到。
  - 与 Contract 不一致：[External Effect and Recovery Contract](../contracts/external-effect-and-recovery.md) §4 规定 timeout 不等于 Repository operation 失败，`MANUAL_RECOVERY_REQUIRED` 表示 commit/ref/artifact 证据矛盾。而当前规则会在没有任何证据矛盾、Repository Service 仍健康运行时进入人工恢复。
- **临时做法**（已下发，不依赖本决议）：重建对照基准不改产品，在 Repository Service 已成功时用现有的 `RESUME_RECONCILE` 人工恢复命令完成 Submit。S1/S3/S4 的完成时间只作报告，结果指纹照常记录。
- **方案**：
  - **A. 只放大数值。** 提高 Submit 等待的单次轮询上限，或提高会话上限，使总等待覆盖目标规模。
    - 改动：常量，以及 P4 R5 §6 与 P5-5B §13.1 的数值。
    - 优点：改动最小。
    - 缺点：会话数同时也是崩溃与结果未知时的重试次数，提高它等于允许更多次失败重试；拉长单次轮询会让 drain 与停机等得更久；仍是固定值，规模再大时会再次触发，而且与 Repository Service 自身的上限不对齐。
  - **B. 区分健康等待与恢复会话**（推荐）。
    - 规则：Repository Service 明确返回 QUEUED/RUNNING（HTTP 成功、operation 身份与请求指纹匹配）时，单次 60 s 轮询到期不计入恢复会话；写入 checkpoint，经现有 safe handoff 让出 lease，之后重新领取继续对账。
    - 只有以下情况计入 3 个恢复会话：崩溃或 lease 丢失、传输错误或结果未知、身份或指纹不符。
    - 总等待上界与 Repository Service 自身的导入上限对齐（导入上限加服务启动时间，backend 侧为有名常量）；超过即进入人工恢复。单次轮询仍为 60 s，drain 与停机响应不变。
    - 改动：`recovery.py` / `submit_jobs.py` 的计数规则，P4 R5 §6 与 P5-5B §13.1 的条款（涉及 Operation Lifecycle Contract 时一并修订）。权威测试覆盖四点：健康等待不消耗会话；超出上界转人工恢复；崩溃与结果未知仍计数；drain 在单次轮询内响应。实施时须核对 safe handoff 之后的重新领取不增加 `attempt_count`。
    - 优点：与规模无关；符合 R5 “恢复预算只计失败”的原意；不新增机制。
    - 缺点：触及恢复核心路径，属于强验证区域，需要独立审核。
  - **C. Submit 不在 worker 内等待。** 改为 Repository Service 完成回调，或单独的异步对账。
    - 缺点：新增 IPC/回调机制，按比例化保障政策须先修订 Contract/ADR。不推荐。
  - **D. 不改产品。** 把人工恢复当作大规模 Submit 的常规路径。
    - 只适合作为基准阶段的临时做法；达不到 S1/S3/S4 门槛，不推荐作为长期方案。
- **阶段安排（与方案独立选择）**：
  - **甲（推荐）**：重建对照基准完成后、S2b kickoff 之前，作为独立小修阶段完成，流程按 DC64（审核先行、证据后补）。改动面（operations、submission）与 S2a（解析器）不重叠，可以和 S2a 用各自的短期分支并行。
  - **乙**：并入 S2b。
  - **丙**：并入 S4（Submit）。S2b 的 W2 实测需要先提交 2× t4 基线，选乙或丙时，S2b 至 S3 都要继续使用人工恢复的临时做法。
- **对基准的影响**：方案 A 与 B 只改变等待与计数，不改变提交内容，预期 Submit 结果指纹不变。修订阶段按 DC64 第 4 项用基准对照工具核对 S1/S3 的结果一致；S1/S3/S4 的完成时间在 S4 与 S6 取证时实测。若改变诊断码或 checkpoint 载荷，按 AGENTS 直接改到目标形态，并同步 golden 与测试。
- **决议**（repository owner，2026-10-29）：采用**方案 B**与**阶段安排甲**。
  1. 新增阶段 **S1c — Submit 等待预算修订**：前置为重建对照基准已完成；可与 S2a 用各自的短期分支并行；S2b 的前置增加 S1c exit。阶段边界 tag 为 `p6-s1c-exit`，流程按 DC64（审核先行、证据后补）。
  2. 实现范围只限方案 B：健康等待不计入恢复会话；总等待上界与 Repository Service 导入上限对齐；崩溃、lease 丢失、传输错误或结果未知、身份或指纹不符仍计入 3 个恢复会话；单次轮询仍为 60 s。不新增 IPC、回调、状态机或 durable 字段；如必须新增 checkpoint 字段，先交 owner。
  3. 同步修订：P4 R5 设计 §6、P5-5B 设计 §13.1；External Effect and Recovery Contract 只核对一致性，不改语义；涉及 Operation Lifecycle Contract 的条款一并修订。
  4. 基准：重建对照基准维持 p6-s1b-exit 的产品与人工恢复临时做法，不因 S1c 重测。S1c 用基准对照工具核对 Submit 结果与基准一致（DC64 第 4 项）。
- **落点**：[执行计划](p6-execution-plan.md) §1、§2（S1c、S2b 前置）。
- **修订**（repository owner，2026-10-30；替代上文决议第 1 项的前置与第 4 项）：
  - 来源：按临时做法修正测量工具后，ct108 的 2× t4 warmup（`p6b2xwarmr5fix1030b`，工具提交 `fc9ba62412`，产品 p6-s1b-exit）在 v1 Submit 上走完了人工恢复流程：09:54:24 转 `MANUAL_RECOVERY_REQUIRED`；09:54:40 Repository Service 返回 SUCCEEDED；同一秒 `RESUME_RECONCILE` 被接受（APPLY）。此后 Submit 一直没有完成，09:56:41 被监视器判为 worker 静默。证据见 ct108 `/home/dev/gdds-p6-logs/baseline/compose/r5-recovery-p6b2xwarmr5fix1030b-v1-560a8a0e/` 与 `/home/dev/gdds-p6-logs/baseline/s4-stall-20261030T095641241998Z/`。
  - 归因（产品缺陷，owner 核对代码与 control DB）：
    - `RESUME_RECONCILE` 与 `RETRY_FROM_CHECKPOINT` 只把 step 与 operation 置为 RUNNING，并以 `operator-recovery` 身份持有 30 s lease（`operations/recovery.py` `build_operator_recovery_candidates`）。
    - 运行中的 worker 只领取 PENDING/RETRY_WAIT 的 step（`sqlite_operations.py` `list_claim_candidates`）。lease 过期的 RUNNING step 只在 worker 启动时处理。启动时 `attempt_count` 已为 3，于是判定会话用尽，step 被打回 `MANUAL_RECOVERY_REQUIRED`，该次启动报阻断。
    - 结果是：人工恢复命令被接受后，step 在运行期无人执行，重启后又回到人工恢复。现有测试（`test_operation_takeover.py` 的 `test_manual_recovery_retains_occupancy_and_excludes_claim`）把“命令后不可领取”断言为正确行为。P4 R5 设计 §7 与 P5-5B 设计都没有规定命令之后由谁继续执行。
    - 因此临时做法在 p6-s1b-exit 上不可行，2× t4 的基准无法越过 v1 Submit。正式测量尚未完成任何一组三次，改变基准所依据的产品版本，损失只有等待时间。
  - 修订内容：
    1. **顺序**：S1c 移到重建对照基准的正式测量之前，前置改为 S1b exit。重建对照基准的工具开发与 05 上的验证可以继续；正式测量（ct108 与 04 最终 runner）以 S1c exit 为前置。
    2. **范围增加**（在方案 B 之外）：人工恢复命令之后的续行。
       - `RESUME_RECONCILE` 与 `RETRY_FROM_CHECKPOINT` 被接受后，运行中的 worker 无需重启即领取并执行该 step。
       - 每条命令授予且只授予一次恢复会话：该会话再次计数失败时回到 `MANUAL_RECOVERY_REQUIRED`；健康等待按方案 B 不计数。
       - 命令之后 worker 重启，不得把该 step 判为会话用尽。
       - 只使用现有状态与字段，不新增状态、durable 字段或机制；须新增时先交 owner。
       - 同步修订 P4 R5 设计中的 operator 命令条款，以及 P5-5B 设计中 operator recovery 的条款。
       - 替换上述测试中“命令后不可领取”的断言。
    3. **基准**：重建对照基准的全部正式测量改在 p6-s1c-exit 的产品上进行，替代原第 4 项。此前在 p6-s1b-exit 上的 warmup 与 05 工具验证只作诊断。
    4. **S1c 的 Submit 结果核对**：基准此时尚未建立，改为与 `p6b2xwarmr5fix1030b` 保留卷对照。该卷中 Repository Service 已在 p6-s1b-exit 上导入成功 2× t4 v1，核对 Dolt 表哈希与 canonical state（DC64 第 4 项口径）。保留卷与 v1-submit checkpoint 在 S1c exit 前不得清理。（S1c 结果的产生方式见 DC66 修订：由 ct108 的 2× t4 完整旅程产生，不再从 v1-submit checkpoint 续跑；对照口径不变。）
  - 落点：[执行计划](p6-execution-plan.md) §1、§2（重建对照基准、S1c）。
- **澄清**（repository owner，2026-10-30；来自 [S1c 独立审核](p6-s1c-independent-review.md) F3）：决议第 2 项“身份或指纹不符……仍计入 3 个恢复会话”的原意是“这类观测不算健康等待”，不是把证据矛盾改为可重试。
  - 身份或指纹不符（本地 checkpoint 与 payload 不符、Repository 返回的 operation identity 与 checkpoint 不符）维持基线行为：立即进入 `MANUAL_RECOVERY_REQUIRED`，使用能区分原因的诊断码，不使用 `r5.reconcile_timeout`。依据：External Effect and Recovery Contract §4，人工恢复表示证据矛盾。
  - 计入 3 个恢复会话的只有：崩溃或 lease 丢失、传输错误、结果未知（没有拿到成功的观测）。
  - P4 R5 设计 §6 失败矩阵与 S1c handoff 的调用方盘点按此修订。

### DC66 缩短测量与取证耗时

- **来源**：
  - 重建对照基准在 ct108 上三次 2× t4 warmup（2026-10-29、10-30）的实测：
    - 每次调用先做离线 composite 比较，用时 1222 s；输入不变，结果每次相同。
    - v1 Preview 三次分别为 1707、1715、1735 s，相差不到 2%。
    - v1 Submit 的 prepare_import 约 21 min，导入约 3–5 min。
    - 按此推算，一次 2× t4 完整旅程约 3.5–4 h；按设计 §16.3“1 次预热加 3 次测量”，仅 2× t4 就需 15 h 左右，基准阶段的 ct108 合计约 25–30 h。
  - 失败恢复：两次失败（R5 会话用尽、人工恢复后无人续行）都要从头重跑，每次失败损失约 75 min 运行时间，另加等待 owner 决定的时间。DC64 第 2 项 a 要求来源运行 exit 0，失败运行的 checkpoint 不能用来续跑。
  - 这一阶段测量的是 Phase 6 改造前的产品，慢路径（Preview、prepare_import）正是 S2b–S4 的改造对象；后续阶段在 2× t4 上的运行会随之缩短。
- **决议**（repository owner，2026-10-30）：
  1. **基准单次测量**（只适用于重建对照基准，修订设计 §16.3 末段在本阶段的执行方式）：
     - 每个负载在 ct108 上测量 1 次，不做整轮预热；正式测量前在 ct108 跑一次 t1 旅程作为环境预热。记录写明“单次测量，无范围”。
     - 补测：某项结果与已有参考证据（同一路径的 warmup、S1a/S1b 的同档记录）偏离超过 10%，或实施者发现干扰（节点上有其他负载、采样缺失）时，补测 1 次；两次偏离超过 5% 时测第 3 次，取中位数并报告范围。
     - 门槛判定不在本阶段进行；S4、S5 的门槛取证与 S6 最终取证仍按设计 §16.3 执行（1 次预热加 3 次测量）。
  2. **预检查复用**：
     - 离线 composite 比较按“输入文件 SHA256 + 比较代码的源码摘要”只做一次，结果连同两个摘要记录在 Git 外的证据目录。
     - 之后的调用核对两个摘要一致即复用；任一不同则重做。
     - 复用记录写入每次运行的日志与 handoff。
  3. **失败后从 checkpoint 续跑**（修订 DC64 第 2 项 a 中“来源运行 exit 0”的要求）：
     - 正式运行在每个计时步骤之前保存 checkpoint（卷副本与状态）。
     - 来源运行之后失败的，其 checkpoint 仍可作续跑起点，条件为：
       - 该 checkpoint 之前的各步骤核对全部通过；
       - 状态文件已记录到该 checkpoint；
       - 失败发生在该 checkpoint 对应的步骤或之后；
       - 续跑使用同一产品提交的镜像（测量工具的修正除外）。
     - 失败运行也必须写完状态文件（结束时间、exit code、失败步骤），否则其 checkpoint 不可用。
     - 续跑结果与 checkpoint 之前的结果合并为一次完整测量，handoff 列明每个步骤的来源运行。
     - DC64 第 2 项 c 的整档重跑条件不变，本项第 4 点的例外除外。
  4. **S1c 证据收窄**（修订 DC65 修订第 4 项的执行方式与 S1c kickoff 的真实数据范围）：
     - 去掉 ct108 的 t4 完整旅程；04 权威 runner 的 Compose 旅程覆盖 Submit 的一般路径。
     - 2× t4 的 Submit 核对从 `p6b2xwarmr5fix1030b` 的 v1-submit checkpoint 副本续跑：
       - 来源运行是 p6-s1b-exit，续跑使用 S1c 最终候选的镜像；
       - 这是 DC64 第 2 项 c 的例外，前提是 S1c 没有改变 control DB schema、checkpoint 载荷与 Repository Service（DC65 已禁止新增 durable 或 checkpoint 字段）；
       - 前提不成立时改为整档运行。
       - 1030b 的状态文件没有写完结束时间与 exit code，这是第 3 项要求修正的已知工具缺口。对这一次运行，三项事实取自其运行日志 ct108 `/home/dev/gdds-p6-logs/baseline/p6b2xwarmr5fix1030b.log`（SHA256 `737b8005fd130ce2e934f63f0d7b4a8b88a179e6cc48c29f8fae86a9aafca27f`）：exit_code=1、ended_utc=2026-10-30T09:56:47Z、失败步骤 v1-submit。handoff 引用该日志，视为满足第 3 项；原状态文件不改写。
     - 05 的 t1 冒烟保留。
  5. **测量工具修正的常设授权**：
     - 授权范围：`vnext/backend/benchmarks/` 及其测试、runbook 与基准 handoff 内的工具缺陷，实施者可直接修正，不等 owner。
     - 程序：
       - 在 05 跑 focused 测试，五包静态检查通过；
       - 修正提交与理由在 handoff 中逐项记录；
       - 修正影响已完成测量的计时路径时，按第 3 项重测受影响步骤。
     - 以下情况仍须停下交 owner：
       - 产品缺陷，或需要改动产品代码、golden、Contract、输入数据；
       - 结果不一致；
       - 测量值异常且补测后仍无法解释；
       - 节点不可用。
- **不变项**：调试与取证分开（DC30）、审核先行与证据后补（DC64 第 1 项）、结果一致的口径（DC64 第 4 项）、节点分工（DC36）、AGENTS 的停止规则。
- **落点**：[执行计划](p6-execution-plan.md) §2（重建对照基准、S1c）；测量工具与基准 runbook。
- **修订**（repository owner，2026-10-31；第 4 项中 S1c 在 ct108 的核对方式）：
  - 来源：第 3 项“从失败运行的 checkpoint 续跑”尚未实现，基准会话估计还需约一个工作日实现与验证。第 4 项原定从 1030b 的 v1-submit checkpoint 续跑 2× t4 Submit，依赖这项能力，S1c exit 因此要等待。04 权威 runner 与 05 t1 已通过（[S1c 取证复核 2](p6-s1c-evidence-check-2.md)）。1030b 的 checkpoint 位于 v1 Submit 开始之前，从它续跑的 Submit 与完整旅程中的 v1 Submit 走同一条代码路径。
  1. **S1c 的 ct108 核对改为一次 2× t4 完整旅程**，替代从 1030b checkpoint 续跑 Submit：
     - 产品为 S1c 最终候选 V。backend/worker 使用 DC67 补充第 2 项的预构建镜像，按 DC67 澄清以 config digest 与全部 DiffID 核对。
     - 测量工具为已在 05 验证的 `p6-baseline` 提交。取证合并提交只在节点上生成，相对 V 只改 `vnext/backend/benchmarks/`、相应测试与 docs，handoff 记录双亲与 `diff --stat`；不合入、不推送。
     - 保留该次运行的卷。旅程结束并停止容器后，以只读方式把 v1 Submit 后 Repository Service 的 Dolt 表哈希与 canonical state 和 `p6b2xwarmr5fix1030b` 保留卷对照（DC65 修订第 4 项，DC64 第 4 项口径）。不得以 root 写入任一 Dolt 仓库。
     - 验收：2× t4 v1 Submit 无人工干预完成；全旅程各步骤核对通过，exit 0；对照一致。对照不一致时停止，交 owner。
     - 该次运行只作为 S1c 证据，不作为基准测量。
  2. 第 4 项中“去掉 ct108 的 t4 完整旅程”、DC64 第 2 项 c 的例外，以及 1030b 状态文件从日志取值的安排，不再用于 S1c。1030b 保留卷与 v1-submit checkpoint 作为对照来源，继续保留到 S1c exit 合入之后。
  3. 第 3 项不变：续跑能力继续实现，作为正式测量的前提，不再是 S1c exit 的前提。
  4. 不变：05 t1 冒烟与 04 权威 runner（均已完成）、第 5 项常设授权、DC67 的取证不经代理。
- **澄清**（repository owner，2026-11-02；W4 输入重新生成与无效的补测参考）：
  - 来源：基准 W4/S4/H1 场景在首个 operation 之前停止。W4 生成器改写 ordered 表时不保持 `no` 连续，两份 W4 输入中全部 54 张非空 ordered 表不满足产品的 ordered 投影；锁定的补测参考中，W4、W4-STRESS 取的是 S1b 生成器的运行时间，S4 取的是 S1c 的 v3 回退 Submit。见 [W4 停止复核](p6-baseline-stop-check-w4.md)。
  1. **W4 输入重新生成**：第 5 项“改动输入数据须交 owner”在此处由本澄清授权。
     - 生成器按第 5 项修正，输出的每张 ordered 表满足产品 ordered 投影（`no` 为 1..N、不重复），每表变化量仍约为设定比例；生成后运行与旅程相同的 census，任何数据集或表不是 COMPLETE 即失败。
     - W4 10% 与 100% 写入新的输入目录，不覆盖已完成场景的输入 `input/1ed24d38f0`；2× v1/v2 不变。
     - 验收由程序给出：census 全部 COMPLETE、重复生成 SHA256 一致、按表的插入/删除/修改/位移计数、由新输入生成期望输入清单。满足后实施者直接继续，记入 handoff，不另设 owner 检查点；终审复核。
  2. **补测参考**：W4、W4-STRESS、S4 改为“无参考，只记录”，替代 DC68 澄清第 4 项中这三项“不变”的表述。W4 的验收在终审按设计 §16.1/§16.3 的业务目标判定，不经由第 1 项的 10% 补测。
  3. journey 的 census 检查移到 Compose 启动之前，与期望输入清单检查一起执行；不满足即退出，按 DC68 属于未触及被测对象的错误。
  4. 不依赖 W4 输入的剩余场景可以先继续；重新生成在 ct108 两个场景之间进行，不与测量重叠。
  5. 不变：第 1 项的单次测量与补测规则（其余场景）、第 3 项续跑、第 5 项常设授权与其余停止条件、DC67 取证不经代理、DC68 及其澄清的其余内容。

### DC67 测试节点依赖获取：预填充为主，代理仅限调试

- **来源**：S1c 代码候选在 05 构建 Compose 镜像时，经开发节点 `heavy-dev-01` 上的受限转发代理（只放行 CT05 客户端与 PyPI 文件、GitHub release 主机）取依赖，并临时替换后恢复了 `rust:1.97.0-bookworm`（[S1c handoff](p6-s1c-handoff.md)，[S1c 独立审核](p6-s1c-independent-review.md) §5）。首次经代理构建因下载失败/超时没有成功。AGENTS 允许测试 CT 经局域网取用获准的依赖、镜像与制品缓存，但“不表示获准任意公网访问”；转发代理实质上是限定范围的公网访问，规则此前没有写明是否允许。
- **决议**（repository owner，2026-10-30）：
  1. **默认预填充**：
     - 依赖、锁文件或基础镜像变化时，先在开发节点（CT201）取得所需制品（uv 缓存/wheel、Cargo crates、Docker 基础镜像与构建层），经获准的局域网方式传到实际使用的节点，再在节点上离线构建与测试。
     - 预填充的来源、内容摘要与时间记入当期 handoff，不记录凭据。
  2. **取证运行不经代理**：04 权威 runner、carried、ct108 的测量与各节点的真实数据取证，不得经转发代理取依赖。缓存缺失时停止该次运行，先补预填充，再从头运行。
  3. **调试例外**：05 上的调试构建可以临时使用受限转发代理。条件：
     - 只放行所需主机；
     - 不传递凭据；
     - 用完即停；
     - handoff 记录放行的主机范围、起止时间与用途。
     调试结果不作为证据。
  4. **阶段安排**：
     - S2a、S2b 等预计新增依赖的阶段，在 kickoff 中列出一次预填充步骤（新增的 crates、wheel 与镜像，以及目标节点）。
     - 不改依赖的阶段（如 S1c）沿用节点已有缓存。
  5. **不变项**：AGENTS 的测试节点与网络约束、DC36 节点分工、`uv-consume.sh` 的锁定与 lock source 约束、Cargo `--offline`。
- **落点**：本记录；AGENTS.md 与 testing-conventions 的网络与缓存一节由负责这两份文件的会话同步（主 checkout 中这两份文件另有未提交的修改，本次不改）。
- **补充**（repository owner，2026-10-30；来自 S1c 取证首次运行）：
  - 来源：S1c 在 04 的六包 runner（V=`3008d578cf`，2026-10-30 14:44:31–14:44:38 UTC，日志 04 `/home/dev/gdds-p6-logs/s1c/04-runner-3008d578cf.log`，SHA256 `b45ccd74…`）同步 backend 环境时 exit 1：解析 build-system 依赖 `maturin==1.14.1` 时连接 PyPI 失败。
  - 核对结果一（owner 在 04 临时 worktree 中验证）：04 的 uv 本地缓存已有 maturin，失败原因是非离线模式下 uv 刷新索引；设置 `UV_OFFLINE=1` 与 `CARGO_NET_OFFLINE=true` 后，backend 环境与 Rust 扩展离线构建成功（04 `/home/dev/gdds-p6-logs/s1c/owner-04-offline-sync-probe.log`）。
  - 核对结果二：backend Dockerfile 在安装 Python、依赖与 Rust crates 之前复制 `rust`、`shared_kernel`、`repository_client`、`repository_contracts`。这些目录或 backend 锁文件一旦变化，其后的层都要联网重建，测试节点无法离线完成。Repository Service 与 client e2e 镜像有预置依赖模式，所需 dependency-base 镜像已在节点上。
  1. **runner 环境**：测试节点上的权威 runner 与环境同步设置 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，写入日志开头与 handoff。
  2. **backend/worker 镜像预构建**：上述依赖层输入变化时，
     - 在开发节点（CT201）从候选提交的 clean worktree 构建 backend/worker 镜像，只构建，不运行测试或 Compose；
     - 经 `docker save`/`docker load` 通过局域网传到需要的节点；
     - runner 以 `GATEWAY_COMPOSE_GATE_PREBUILT=1` 运行；
     - handoff 记录构建提交、image ID、传输文件 SHA256、构建日志与起止时间。
     这属于本决议第 1 项的预填充。
  3. **Repository Service 与 client e2e 镜像**：在节点上以预置依赖模式离线构建；dependency-base 镜像缺失时按第 1 项预填充。
  4. **就绪预检**：权威 runner 之前先在节点核对镜像与缓存就绪（不运行测试）；缺失即停止，不进入 runner。
  5. **遗留**：调整 backend Dockerfile，使依赖层只取决于锁文件，测试节点即可离线自建镜像。建议在 S2a 之前作为独立小改完成（S2a 会改 `rust`），由 owner 另行安排；完成前按第 2 项执行。已安排（2026-10-30）：见[执行计划](p6-execution-plan.md) §2“backend 镜像依赖层调整”，S2a 前置。
  6. **第 2、5 项的落实**（repository owner，2026-10-31；backend 镜像依赖层调整 exit，tag `p6-backend-image-exit`，证据见[证据复核 2](p6-backend-image-deps-evidence-check-2.md)）：自此替代第 2 项的整镜像预构建：
     - backend 锁文件（`pyproject.toml`、`uv.lock`、`.python-version`）、`rust/Cargo.lock`、`rust/rust-toolchain.toml` 或 Rust 基础镜像变化时，在开发节点（CT201）从 clean worktree 运行 `vnext/scripts/build-backend-dependency-base.sh --save <归档>`，只构建 dependency-base `gateway-backend-deps:lock-<12>`；经局域网传到需要的节点后 `docker load`，按本决议澄清以 config digest 与全部 DiffID 核对身份。
     - 节点上的权威 runner 与旅程设置 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=<tag>`、`GATEWAY_DOCKER_BUILD_NETWORK=none`，backend/worker 在节点本机离线构建，不再设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。
     - 只改源码（含 `rust`、`shared_kernel`、`repository_client`、`repository_contracts`）时不需要新的 dependency-base。
     - 例外：`p6-backend-image-exit` 之前的产品提交（S1c 候选 V、`p6-s1c-exit`）沿用旧 Dockerfile，仍按第 2 项使用开发节点预构建的整镜像。
     - 当前 dependency-base：`gateway-backend-deps:lock-c668cef8e47e`（输入摘要 `c668cef8…`，config digest `sha256:a8d9d1ac…`），已在 04 加载；05、ct108 需要时按上述方式传输。
- **澄清**（repository owner，2026-10-30；来自 S1c 04 镜像就绪预检停止，[S1c 取证复核 1](p6-s1c-evidence-check-1.md)）：
  - 来源：开发节点构建的 backend/worker 镜像经 `docker save`/`docker load` 传到 04 后，04 的 `docker image inspect` ID 与开发节点不同，实施者按取证提示词中的“ID 一致”要求停止。核对结果：两端 config digest 相同（`sha256:b1f3c7b6…`），15 个 RootFS DiffID 逐项相同。ID 不同的原因是两端 image store 不同：开发节点为 classic store，inspect ID 即 config digest；测试节点为 containerd store，inspect ID 是本机生成的 manifest digest。
  1. **跨节点镜像身份**：经 `docker save`/`docker load` 或其他方式在节点间传输的镜像，以“config digest + 全部 RootFS DiffID 逐项相同”判定身份，不比较 inspect ID。
     - 取值：classic store 上 config digest 即 inspect ID；containerd store 上在本机 `docker save` 后读取归档 `manifest.json` 的 `Config`。DiffID 取自 `docker image inspect` 的 `.RootFS.Layers`。
     - handoff 记录两端的 config digest、DiffID 列表与比较结果；两端 inspect ID 照记，仅供参考。
  2. **适用范围**：本决议第 2 项的 backend/worker 预构建镜像（04、05、ct108），backend 镜像依赖层调整中的 dependency-base 传输，以及其后所有跨节点镜像预填充。
  3. **不变项**：同一节点内的闭包 manifest 与 carried 判定继续使用本机 image ID（同一 worktree、同一 image store），与 AGENTS“镜像身份等价”和 DC34 一致。
  4. **S1c 本次结果**：04 已加载的 `s1c-v-3008-backend:latest`、`s1c-v-3008-worker:latest` 按第 1 项与开发节点构建结果一致，04 就绪预检视为通过，不重做。

### DC68 取证中的操作失误：修正后重做一次

**现行执行以本节末“2026-11-08：最多三轮自主修复”补充为准。** 以下2026-10-31原始决定及澄清保留为历史，不再把“一次重做”和“被测对象已运行即上报”当作当前工具故障限制。

- **来源**：2026-10-30 至 10-31，S1c、重建对照基准与 backend 镜像依赖层调整的取证先后因实施者自身的操作或工具错误停止四次：
  - 构建命令的 context 指向 worktree 根目录（依赖层调整第 3 步）；
  - rustc 版本预检位置错误（基准工具验证，源于审核提示词）；
  - 测量工具的 mypy 错误（基准工具验证）；
  - 采集脚本在 `set -u` 下的变量错误（依赖层调整第 4 步）。
  这些失败都发生在被测对象运行之前，或者是 DC66 第 5 项范围内的工具缺陷，对候选与已有证据没有影响。提示词统一要求“任一步非 0 即停”，每次都要经 owner 往返一轮才能继续。
- **决议**（repository owner，2026-10-31）：
  1. **可修正后重做一次的失败**，须同时满足：
     - 原因是实施者自己的命令、脚本或参数错误，或 DC66 第 5 项范围内的测量工具缺陷；
     - 失败时被测对象尚未运行：没有启动容器，没有运行产品代码或测试，没有写入卷、Dolt 仓库或 control DB；
     - 没有需要撤销的副作用。
  2. **程序**：
     - 失败尝试的日志与 SHA256 保留，不覆盖；
     - 修正命令或脚本后，从该步骤开头重做；
     - handoff 逐项记录失败原因、修正内容与重做结果。
     - 工具代码的修正按 DC66 第 5 项另起提交，并完成 05 focused 测试与五包静态检查。
  3. **仍须停止交 owner**：
     - 同一步骤的重做再次失败；
     - 被测对象运行之后的任何失败，包括测试、runner、旅程、镜像构建结果与对照；
     - 缓存缺失、身份不符、结果不一致；
     - 原因无法判定属于第 1 项；
     - 需要改动产品代码、golden、Contract、锁文件或输入数据。
  4. **适用范围**：各阶段的取证与预检步骤（04 runner 及其前置、真实数据旅程、ct108 测量、镜像构建与传输核对）。不改变 AGENTS 的 runner 停止规则：runner 已开始运行测试后 exit 非 0，仍先停下处理。
- **不变项**：DC30 调试与取证分开；DC64 审核先行与重跑范围；DC66 第 5 项常设授权；DC67 取证不经代理与停止条件；AGENTS 的节点约束。
- **落点**：本记录。此后的取证提示词把停止条件写成“DC68 第 1 项的失败修正后重做一次，其余停止”。
- **澄清（repository owner，2026-10-31）：只读后处理与只读预检不计次数。**
  - 来源：重建对照基准接手后，ct108 上的停止有四次来自实施者临时编写的只读核对片段（镜像身份抄录、两次输入核对脚本、t1 结果解析），被测对象本身均正常。
  1. 对已保存证据的只读解析、计算与哈希比较（含在卷副本上的只读对照），以及启动前的只读预检，脚本或命令出错时可以修正后重跑，不受第 1 项“重做一次”的限制。每次失败的输出与 SHA256 照常保留，并记入 handoff。
  2. 界限：
     - 失败原因是证据本身缺字段或内容不符，而不是脚本错误时，照常停止交 owner；
     - 会启动或触及被测对象的步骤（容器、产品代码、测试、写卷、Dolt 仓库或 control DB）仍按第 1–3 项执行。
  3. 判定、比对与核对优先使用提交过并经测试的工具或指定脚本，结论取程序输出，不手工抄录或心算。
  4. **在重建对照基准中的应用：**
     - 10% 偏差判定按 DC66 第 5 项做成 benchmarks 中提交过的工具：读取 journey 的 state/run JSON，按参考表计算相对偏差并输出结论；参考值由程序从参考证据中提取，存为提交过的机读参考文件。工具在 05 做 focused 测试与五包静态检查（获取节点占用标记，与 S2a 错开），只改 benchmarks 与对应测试。已完成的 t1 正式运行用该工具对已保存证据补做判定，不重跑。
     - 补测参考必须来自同一节点（ct108）。t1 以本次 ct108 预热运行为参考（预热仍不计入正式结果）；t2、t3 在 ct108 上没有同口径参考，05 的 S1b 数值只记录、不触发补测；其余 ct108 上的参考（t4、W4、S1/S3/S4、H2-三节点、S1a 子段、V5b）不变。（W4、W4-STRESS、S4 已由 DC66 澄清第 2 项改为只记录。）
- **澄清（repository owner，2026-11-02）：代码传输准备不计次数。**
  - 来源：基准会话把工具提交送往 05 验证前，开发节点上的 `git bundle create` 两次命令错误（裸 commit hash 作 ref 得到空 bundle；`--all` 参数位置错误）。实施者按第 1 项“修正后重做一次”停止，测量、输入与证据均未触及。
  1. 代码传输准备与只读预检同等对待：在开发节点或测试节点上打包、传输、拉取或检出提交（`git bundle`、`scp`、`git fetch`/`pull`、`git bundle verify` 与摘要校验），命令出错时修正后重做，不受第 1 项“重做一次”的限制。失败输出与 SHA256 照常保留并记入 handoff。
  2. 界限：不得对正在运行测试、测量或生成的 worktree 检出、拉取或写入；节点 worktree 的提交切换须在使用它的进程结束之后，或改用新的 worktree。传输后的提交身份（HEAD、bundle 内容）仍由程序核对，不符即停止交 owner。

- **修订（repository owner，2026-11-08）：最多三轮自主修复。**
  - 来源：S3 D 的小Compose执行稿仅运行Submit，后续Ordered/History未启动但整体exit0。Owner已明确恢复缺失Ordered-only后，进一步授权：“可以同时修改这条限制，后续授权允许3次自行修复尝试，而不是一次即停”。
  1. 本条工具/操作/取证故障在首次失败后，同一具体根因允许最多三轮自行定位、修复、适用独审和受影响步骤复验；首次失败不计轮次。第三轮仍未解决才交Owner，不以换候选/目录/节点/角色重置同根计数。既有只读后处理/预检与代码传输准备不计次数授权继续。
  2. 被测对象已经运行不再单独触发Owner恢复要求；每轮先停止该次执行与后续验收、保留原始exit/失败日志及SHA、确认安全收尾，固定修订稿并完成适用独审后再执行。只有工具stdout而无独立原日志时如实限定来源，不能补造原件或把旧失败改成成功。
  3. 三轮不是无修改自动重试，不改权威runner为自动重试。每轮在handoff记录具体根因、修复及复验次数/实际结果；只补受影响步骤，保留合格的未受影响证据。无需增建持久计数或evidence状态机。
  4. 真实产品失败仍按所属阶段已有修复授权/停止规则处理；不能伪装工具故障、修改预期或放宽断言。原因或副作用无法确认、资源无法安全收尾、需要变更冻结语义/Contract/golden/输入或超出现有授权时，停止受影响部分交Owner。
  5. 缓存/HEAD/镜像/输入身份和结果正确性继续严格核验，不符不继续当次验收。可修复错误工具/命令选择并复核，可按DC67已有授权准备正确缓存；真实来源/正确性冲突未解决时交Owner，不接受错误身份、不绕过离线/节点限制。
  6. 本补充替代本节原决定中“仅未触及被测对象”“重做一次”“对象运行后的任何失败即交Owner”的工具故障限制；其他阶段范围、冻结决定、节点与记录规则不变。历史停止与缺失记录不追认为通过。同步落点：AGENTS.md、testing-conventions.md。

### DC69 S1c 并入变更集排序缺陷的修复

- **来源**：
  - ct108 的 2× t4 三节点旅程（取证合并提交 `47832ee94d`）中，v1、v2 Submit 均无人工干预完成，1030b 对照一致。
  - v3 Submit 以 v2 为基线重新上传 v1 的包，失败在 `prepare_import`，诊断为 `OPERATION.PURE_RECOMPUTE_FAILED`（见 [S1c 取证复核 4](p6-s1c-evidence-check-4.md)）。
  - 诊断与审核（[v3 诊断审核](p6-s1c-v3-diagnosis-review.md)）确认了根因：`_changeset.py` 的 `_patch_mutations` 按主键顺序交错输出 DELETE 与 UPDATE，而 `validate_change_set_ordering` 要求同表内按 DELETE → UPDATE → INSERT 分阶段。
  - 任何 PATCH_DML 表，只要某个 UPDATE 的主键小于某个 DELETE 的主键就会触发。该缺陷自 P3-R7（`e09ff32cc3`）起存在，不是 S1c 引入的。
  - 失败发生在纯计算阶段，没有数据损坏，表现为 Submit 稳定失败。
  - 三节点场景原不在 S1c 的约定取证范围内（DC66 修订），是复核 3 的 checkpoint 清单把它带进了运行。
- **决议**（repository owner，2026-10-31，采纳方案甲）：
  1. **范围**：修复并入 S1c，作为 `p6-s1c-impl` 上的追加提交，形成新的代码候选 V'，内容为：
     - `_patch_mutations` 先分别收集 DELETE、UPDATE、INSERT，各组内保持主键顺序，再按 DELETE → UPDATE → INSERT 输出；
     - 补一个按业务行为命名的权威测试，相关 golden 与 digest 直接更新到新形态；
     - `recovery.py` 的 PURE_RECOMPUTE 兜底分支用日志记录异常堆栈，只写 worker 日志，不进入 diagnostic 与 API。
     修复由审核会话做针对性复审。
  2. **取证**（替代 DC66 修订中 S1c 的 ct108 项）：
     - V' 早于 `p6-backend-image-exit`，backend/worker 仍按 DC67 补充第 2 项在开发节点整镜像预构建；
     - 04：V' 上的六包权威 runner；
     - 05：t1；
     - ct108：一次 2× t4 三节点完整旅程（冷 History，五个 checkpoint，保留卷），exit 0。
     - 之后只读对照两项：v1 Submit commit 与 1030b 保留卷的表哈希与 canonical state；v3 commit 与同次运行 v1 commit 的表哈希，后者应全部一致。
  3. **基准起点不变**：重建对照基准仍以 `p6-s1c-exit` 为起点，DC65 修订不变。H2-三节点场景随之可以测量。
  4. **保留**：`s1c-v-3008-rerun-fb534_*`、`s1c-v-3008-rerun-20e634_*`、1030b 卷，以及各次运行的日志，保留到 S1c exit 合入之后。
  5. **停止条件**：
     - DC68 第 1 项的失败修正后重做一次；
     - 测量工具缺陷按 DC66 第 5 项修正；
     - 产品失败、缓存缺失、身份不符，或任一对照不一致时停止，交 owner。
- **不变项**：DC30；DC64；DC65 的 Submit 恢复设计；DC66 第 5 项；DC67 取证不经代理；DC68。
- **落点**：本记录；执行计划 S1c 的真实数据项。

### DC70 S2a 开发与基准正式测量并行

- **来源**：
  - 执行计划把重建对照基准与 S2a 排成串行。基准的正式测量要在 ct108 上独占运行设计 §16.3 的全部场景，预计 1–2 天。
  - S2a 的开发主要使用开发节点与 05。它的真实数据只做 05 上的逐值差分（DC50 补充），验收不依赖基准数值。
  - 基准测量的对象是 `p6-s1c-exit` 这个固定提交，S2a 的改动不影响它。
- **决议**（repository owner，2026-10-31）：
  1. **开始时点**：S1c exit 合入 main 后，S2a 的 kickoff、设计核对、编码、focused 测试与审核即可开始，与基准正式测量并行。
     - S2a 在短期分支 `p6-s2a` 上开发，基于 `p6-s1c-exit`，exit 时合入 main。（2026-10-31 澄清见 DC71 第 2 项：基于把 `p6-s1c-exit` 合入 main 的 merge commit。）
     - kickoff 提示词随 S1c exit 一并给出。
  2. **节点**：
     - ct108 在基准测量期间由基准独占，S2a 不使用；
     - 04 上基准的最终 runner 优先，S2a 的权威 runner 只在 04 空闲时运行；
     - 05 由 S2a 使用。基准的预热 t1 或工具验证需要 05 时，两边协调，不并用。
     - 每台节点仍整机单飞（AGENTS）。
  3. **取证与 exit**：
     - S2a 的权威 runner 与 05 真实数据差分可以在基准完成前进行；
     - 原约定 S2a 的 exit（tag、合入 main）在基准 exit 之后办理；2026-11-05 已由 DC81 解除这一顺序依赖。
  4. **基准发现产品缺陷时**：按 DC69 的方式由 owner 决定修复放在哪里。修复落到 main 或 S1c 系列提交后，`p6-s2a` 先合入修复；修复所影响的 S2a 证据重新运行，未受影响的按包沿用。
  5. **审核**：两条线分开审核。基准由新开的审核对话负责；S2a 的审核会话在 kickoff 时指定。
- **不变项**：基准只改测量工具、不改产品代码与 golden（执行计划“重建对照基准”的授权）；DC30；DC66–DC68；S2a 的范围与验收（设计 §7）。
- **落点**：本记录；执行计划 §1 与 S2a 的前置。
- **补充（repository owner，2026-10-31）：节点占用标记。** 基准与 S2a 的会话共用测试节点，彼此不能直接通信，整机单飞（AGENTS）按以下约定执行：
  1. 在任一测试节点（04、05、ct108）运行会触及 Dolt、Compose、pytest 或 cargo 的命令前，用 `mkdir /home/dev/gdds-node-busy.d` 原子获取占用。`mkdir` 失败表示节点已被占用：等待，不抢占；长时间未释放时报告 owner。
  2. 获取后在该目录写入 owner 文件，内容为会话名、用途与开始时间（UTC）。会话名按角色区分，例如 `p6-baseline-measure`、`p6-s2a-impl`。
  3. 运行及其清理完成、确认无本次容器与进程后，删除该目录。
  4. 只读检查（`ls`、`sha256sum`、`git status`、`docker image inspect` 等）不需要占用；审核会话的只读核对不需要占用。
  5. 会话异常结束留下的占用目录，由 owner 确认节点上没有相关容器与进程后决定删除，其他会话不自行删除。
  6. 本约定不替代 AGENTS 的整机单飞与运行前残留检查。是否写入 AGENTS，由维护该文件的治理会话决定。

### DC71 S1c exit：真实数据范围确认、DC70 起点澄清与遗留登记

- **来源**：[S1c 终审](p6-s1c-final-review.md) §4。
- **决议**（repository owner，2026-10-31，按终审建议）：
  1. **真实数据范围（DC33）：** 确认 DC66 修订与 DC69 第 2 项的范围为 S1c 的真实数据证据：05 t1；ct108 一次 2× t4 三节点完整旅程（冷 History、五个 checkpoint、保留卷，取证合并提交 `b96fe8e4cc`）；v1 Submit 对 1030b 保留卷、v3 对同次 v1 的只读对照（均 631/631 一致）。见 [取证复核 5](p6-s1c-evidence-check-5.md)。
  2. **DC70 起点澄清：** `p6-s1c-exit` 打在 S1c 分支的最终 HEAD `9f288ad504` 上，早于 `p6-backend-image-exit`，不含 backend 镜像依赖层改动。`p6-s2a` 改为基于把 `p6-s1c-exit` 合入 main 的 merge commit `49d0846d86`，它同时包含两者。重建对照基准仍测量 `p6-s1c-exit` 这个提交本身。DC70 其余内容不变。
  3. **遗留登记：** 非 operator 会话中，会话已用尽、lease 过期的 RUNNING step 在 startup 转人工恢复并阻断该次启动（`BLOCK_STARTUP_FATAL`），与 P4 R5 §8“人工恢复记录不阻断 readiness”的表述有出入。这是 S1c 之前的基线行为。列入 worker runtime 后续维护（与 DC63 第 3 项的 O1 同一归属），不阻塞 exit，不并入基准或 S2a。
- **落点**：本记录；DC70 第 1 项；[执行计划](p6-execution-plan.md) S1c 状态与 S2a 前置。

### DC72 S2a kickoff 确认

- **来源**：[S2a kickoff](p6-s2a-kickoff.md)（`p6-s2a` 提交 `30de9c1cae`）与 [kickoff 审核](p6-s2a-kickoff-review.md)。
- **决议**（repository owner，2026-10-31，按审核建议）：
  1. **O2：** JSON 数值解码后非有限（包括 `1e400` 这类溢出为 inf 的值）按表级 `SQL_VALUE_ILLEGAL` 拒绝。这是 DC62 第 2 项 e 的一致性修正，不是新语义。先在 Python 参照实现中单独提交修正（复用现有 reject 参数表），再由 Rust 实现对齐；第 ④ 层差分记录真实数据中这类值的出现次数。
  2. **旧实现删除范围：** 按 kickoff §3 确认（DC52）。AGENTS.md 与 testing-conventions.md 由治理会话维护，S2a 在 handoff 中写出建议条文；执行计划路径清单的修改在 handoff 中提出，exit 时更新。设计 §2.2 的事实描述、被删除的 Contract 与 ADR 链接由 S2a 修改。
  3. **差分入口与接入（设计 §7 澄清，后续由 DC78 修订）：** S2a 只在测试支持层提供双实现入口，生产 `parse_sql()` 与 worker 路由继续走 Python，不引入部署 flag，不做 shadow 执行。S2b 随上传侧数据路径合并（DC46）直接接入 Rust，验证后删除被替代 Python 路径；不再引入原拟的生产 feature flag。S2a 已引用证据及范围不追溯更改。
  4. **parser 表内分块（DC47 第 4 项的 L3）：** 保留 V6 已实现并验证的 INSERT 元组分块，作为 SQL parser 专属的 L3。条件：只用同一个共享池，不嵌套建池；row-budget 偏移、同表多处错误的诊断顺序在不同分块大小下必须相同，纳入第 ③ 层与 Rust 确定性测试；不在其他 kernel 扩大 L3。
  5. **adapter 命名：** 新的单一 adapter 沿用 distribution 与 crate 名 `gateway-compute-python`；删除 `gateway-compute-python-impl`。Python 模块对外为全新的 parser 接口，不保留任何旧 API 符号。
  6. **线程池分步（DC47 第 5、7 项）：** S2a 在 adapter 中实现进程内共享的有界池（一次创建、固定 N、所有调用复用，N 由调用方传入；测试默认 N=1，一致性测试比较 1 与 N）。worker 启动时的接线与部署配置 N、M 在 S2b 完成；相应的 owner 测试分别在 S2a（adapter 层池复用）与 S2b（worker 启动接线）。
  7. **其余按 kickoff 确认：** 真实数据范围只做第 ④ 层逐值差分，t1–t4 的 v1/v2 与 testdata1 均在 05，testdata1 按输入 digest 与 t3 去重（DC33、DC50 第 4 项及补充）；审核由原 S1c 审核会话负责；节点按 DC70 及其补充；exit 在基准 exit 之后。
- **落点**：本记录；设计 §7、§8.3、§8.4；执行计划 S2a、S2b 内容。

### DC73 后端会话分为设计与审核两个角色

- **来源**：
  - 到 2026-11-03，后端由同一个审核会话兼做两类工作：一是审核与停止复核；二是 DC 记录、设计与执行计划修订、kickoff 确认。两条线（重建对照基准、S2a）并行后，单一会话的工作量与上下文都过大。
  - 同一会话既提出验收条件又审核执行结果，缺少独立核对。例如 [W4 KEY_EMPTY 停止复核](p6-baseline-stop-check-w4-key-empty.md) §3：审核方建议的验收范围不足，直到产品运行才暴露。
  - 前端已按设计、实施、审核分设会话（[前端 kickoff](../../../../frontend-vnext/frontend-kickoff.md) §10），运行正常。
- **决议**（repository owner，2026-11-04）：
  1. **两个常设会话：**后端后续工作由新开的设计会话（`p6-backend-design`）与审核会话（`p6-backend-review`）分担。原审核会话交接后退出。交接内容见 [后端会话交接](p6-backend-session-handoff.md)。
  2. **设计会话：**
     - 负责：DC 的起草、编号与记录（下一个编号 DC74）；详细设计与执行计划的修订；各阶段 kickoff 与实施提示词；kickoff 确认记录；答复实施中的设计问题；后端任务 BE-a、BE-d 的安排；从后端可行性角度核对 BE-b 草案（BE-b 设计仍由前端设计会话负责）。
     - 不做：不写产品代码；不审核实施结果；不判定证据。
  3. **审核会话：**
     - 负责：kickoff 审核、代码审核与复审、证据复核；停止复核，包括 DC66 第 5 项范围内工具修正的处置建议；阶段终审与 exit 办理（tag、合入、清理，推送须经授权）；exit 时执行计划阶段状态行的更新；审核 worktree 与节点遗留的清理。
     - 不做：不写产品代码；不起草或修改 DC、设计与执行计划正文。
  4. **交接面：**
     - 审核结论若需要新决议、修订设计或计划、扩大授权，报告中写明建议并标注“交设计会话”，由 owner 转交。
     - 设计会话起草的 kickoff、设计修订与验收条件，交审核会话做 kickoff 审核后再由 owner 确认。
     - 两会话不直接通信，经 owner 转交提示词；引用对方文档时注明提交号。
  5. **仓库与推送：**
     - 两会话都在主工作区的 `main` 上提交。提交前看 `git status`，只按显式路径提交本角色的文件，不暂存其他会话的改动。
     - 推送须 owner 的消息中含“推送”。推送前列出远端之后的全部本地提交（包括其他会话的），在回复中说明。
     - 推送后由执行推送的会话用 bundle 同步三台节点。节点的占用标记用途为计时测量时跳过该节点，记为待同步。
  6. **不变：**
     - AGENTS.md 与 testing-conventions 仍由治理会话维护。
     - 前端各会话、基准测量会话 `p6-baseline-measure` 与 S2a 实施会话照旧。
     - DC70 第 5 项中的基准审核与 S2a 审核由审核会话承接，包括基准终审。
     - DC66 第 5 项的常设工具修正授权、DC68 与停止规则不变。
- **落点**：本记录；执行计划 §8.2；[后端会话交接](p6-backend-session-handoff.md)。

### DC74（草案）BE-c 的落点与整包传输计时

- **状态**：2026-11-04，p6-backend-design 起草；待 kickoff 审核后交 owner 确认。不是已生效决议。DC75 已用于本人撤回与工作区占用投影，DC76/DC77 用于 S2b 输入与容量约定；DC78 用于 Rust 单实现与清理约定，DC79 用于基准输入工具并行完善，DC80 用于停止后的主动处置及 READY 闭包容量修正，DC81 用于开发与全量基准解耦，DC82 用于新增开发测试节点，DC83 用于 S2b 功能退出与 W2 性能复核分开，DC84 用于 S2b 容量分步收口与 W1 诊断时点，DC85 用于 S2b kickoff 确认及 A 节实施授权，DC86 用于 B–E 逐节推进及既定二角色授权，DC87 用于单 worker 资源配置，DC88 用于纯重算正常 drain 交接，下一个可分配编号为 DC89。
- **来源**：`ebb0047383300a3754a4be6a6a78f72286600c83` 的[后端交接 §2.3](p6-backend-session-handoff.md)、[前端 kickoff §4.4/§5/§9](../../../../frontend-vnext/frontend-kickoff.md)、本记录 DC38/DC41/DC53/DC64/DC66；设计 §16.1 的 i 段已计入 READY 前 bundle 组装与导出成本。
- **需 owner 定的两项及建议**：
  1. **BE-c 放在基准还是 S6？建议 S6。** 基准产品固定为 `p6-s1c-exit`，当前 GET `/bundle` 只返回 manifest JSON；基准体积不能冒称 BE-d 后完整 tar 的线传字节。完整报告随 S6 已有 t4、2× t4 旅程采集，不为体积另跑一轮完整旅程。BE-d 实施后即可随已授权运行先记实际字节供 FE3 参考；如 owner 要提前从保留闭包估算，也须标“闭包逻辑大小/理论 tar 大小”，不作网络实测，不扩充当前基准必跑场景。
  2. **整包下载是否计入 P6 门槛？建议不改既定门槛，新增只报告项。** W/H 仍按受理到 READY、完成时间按原定义，Submit 仍受理到 main 前移。READY 前已发生的表导出、manifest/closure 组装全部保留计时；GET `/bundle` 时的预检、tar 封装与发送进入独立的 download 时间。前端 kickoff §9 的“不含 bundle 打包”须澄清为“不含下载请求中的传输封装”，不能从 worker 路径扣掉既有工作。
- **建议采集口径**：
  - 对 t4 与 2× t4，每个已有 Preview/History 场景记录模式、节点数、bundle digest、实际收到的 tar 字节数、Content-Length、GET 发起到完整读取结束的单调时钟耗时、完整性核验状态和软硬件/网络条件；覆盖 MODIFIED_ONLY、FULL、DATASET_REPLACEMENT 的已有场景及两/三节点 History，不另造超出阶段授权的计时场景。没有该模式样本时明列缺项及后续归属，不写已覆盖。
  - 成员覆盖与校验通过才计为成功下载。Content-Length 与实收字节由程序比较；不能只读取 manifest 后停止计时。缺字段、下载失败或校验失败不写成 0 字节/0 秒成功样本。
  - 1 Mbps 的理想下载下限由程序算 `8 * tar_bytes / 1_000_000` 秒（十进制 Mbps），只报告；不含协议开销与浏览器解析，不作为 1 Mbps 实测。
  - 若另报“受理到本地可浏览”，须有客户端校验/解析结束的独立锚，不能简单把不同运行的 READY 与 GET 时间相加冒充实测。该客户端指标不在本次后端任务新增硬门槛。
- **安排与落点（草案）**：BE-d 按[任务草案](p6-be-a-d-kickoff.md)修改旅程工具；设计 §12/§16.4 与执行计划 S6 标记待决事项。owner 确认后，由 owner 转前端设计会话更新其 §9，后端设计会话不编辑前端文档。基准当前授权、DC66 单次测量例外、S6 统计方法均不改变。
- **确认记录**：审核提交待填；owner 未确认。

### DC75 BE-a：工作区占用指针与本人撤回权限

- **来源**：`55e6c0083c` 的前端 FE2 kickoff Q16 与 frontend-kickoff §3.3；后端设计会话以 main `d0a8143d804e158e16b0712cc5f2aa007066f9cb` 核对源码及 P5-5C §4.3/§5。owner 在 2026-11-04 同意“新增本人撤回能力、保留审核人权限，与 Workspace 指针一起扩入 BE-a”，并要求补充订正及各方提示词。
- **决定（方向已确认，kickoff 审核通过，待 owner 实施确认）**：
  1. WorkspaceResponse 增加必需但可为 null 的 `active_submit_attempt_id`、`active_submission_id`，投影当前占用，至多一个非空；不表示最近提交或可撤回状态。与 Workspace/optimistic_version 同一事务快照读取，无新持久字段。新建/已有工作区响应均覆盖。
  2. 新增 exact permission `withdraw_own_submission`：scope 内 `context.actor_id == Submission.created_by` 的本人提交可读 review facts；只有 PENDING、未关闭且版本/占用条件成立时可执行新 WITHDRAW。不隐含授予 APPROVE/REJECT 或项目 History 权限。session 显式发放，不由上传权限或本人身份自动授予。
  3. `review_submission` 保持跨 actor 的现有能力；双权限取并集，不给 reviewer 加本人限制。新增权限必须接入 GET、POST 与 replay，不只改 route 或前端按钮。
  4. 权限在对象读取前按动作检查；仅本人权限的请求在读取目标绑定后检查本人关系，不存在、非本人及跨 scope 统一 404。返回审核事实之前完成授权。当前授权、幂等完整性、review CAS、归档屏障、精确占用与原子释放均保持；成功后的合法 replay 不重新要求 PENDING/占用存在。
  5. 不改 actor-independent 的幂等 namespace/fingerprint；合法跨 actor 回放只返回原事件 actor。任何路径不得通过幂等键泄露他人事实或回放无权执行的动作。
  6. 占用受理/finalize/abort/审核释放/归档释放时按现有事务递增工作区版本；APPROVE 不改变工作区版本。撤回仍使用独立 `expected_review_version`。撤回后清空当前输入与 Preview，可重新上传；历史提交与 Repository commit 保留。
  7. 并入 BE-a，S2a exit 合入 main 后、FE3 前；原删除 RETURN_FOR_REVISION 及两创建接口 OpenAPI 订正继续执行。权限修订本身不新增 schema；原 BE-a 的旧状态删除仍直接改基线。BE-d/BE-b 和当前 P6 基准范围不变。
- **详细设计与验收**：[BE-a 设计补充](p6-be-a-design.md)、[kickoff §2](p6-be-a-d-kickoff.md)。实施时同步 owning Contract、P5-5C 及 Workspace HTTP 文档正文、OpenAPI、示例 session 配置和测试；前端快照由 FE3 更新。本文不声明产品已实现。
- **确认记录**：owner 方向确认 2026-11-04；kickoff 细则审核通过、无阻塞项（[报告](p6-be-a-kickoff-review.md) @ `fcbfb4c1a0`，候选 `f20f08bea919`）；非阻塞建议已采纳：replay 权限与披露归公开 HTTP 测试，事务测试归完整性/CAS/原子释放。owner 实施确认待记录，S2a 合入提交待填。DC74 不因本次同意而变为已确认。

### DC76 S2b 输入约定与映射准备

- **来源**：2026-11-04，owner 在设计会话 `01a1a628-e59a-7981-aad5-6bf31e919d38` 确认：“保证按 UTC 导出设计”；来源与类型先按现有数据，约 70 MB 大样本之外已有约 100 MB SQL，属于极少数；随后授权按需落成映射方案并继续讨论下一部分。
- **已确认的设计输入**：输入按 UTC 导出；来源、类型及冻结业务规则不变；约 100 MB 作为容量场景，不能据少见而忽略，也不设置新的 100 MB 上限。不改变现有 parser 各项预算或当前基准输入/测量口径。
- **方案落点**：[S2b Arrow 映射 v1](p6-s2b-arrow-mapping-design.md)、设计 §8.1 与 S2b kickoff。细则以独立内部映射表达，业务摘要与 Repository wire 保持原 Contract；后续补容量/N/M 与 flag。真实约 100 MB 文件当前不是必需交付，现有样本分布不足时再协调。
- **授权与状态**：允许设计准备和文档修订；映射技术细则尚待独立审核，S2b kickoff 未确认、未发实施提示词。本文不判定产品支持容量，不要求重做 S2a 已通过证据，不授权推送。

### DC77 仓库规模与提交频率的容量设计输入

- **来源**：2026-11-04，owner 在设计会话 `01a1a628-e59a-7981-aad5-6bf31e919d38` 确认首版预计 1,000 个独立设备数据仓库、长期 10,000 个；单仓库极端短期一周约 5 版，按年平均每 1–2 个月一次提交。
- **设计输入**：常态按每仓库每年 6–12 次提交推算；短期每周 5 次只用于突发情景，不按 52 周外推为年均。首版全体年提交约 6,000–12,000 次，长期约 60,000–120,000 次；不据平均频率断言提交均匀或不存在集中维护。
- **落点**：[S2b kickoff §3.1/§5.1](p6-s2b-kickoff.md)。分别估算当前 head 常驻、历史 durable 增长和临时/TTL 高水位；不把 100 MB 少数样本当作所有仓库的平均值。历史 SourcePackage/Dolt 保留边界不变，不新增自动清理历史的授权。
- **范围**：N/M 仍按 DC47 的单 worker/operation 内计算路径定；仓库数用于磁盘外推，不直接变成线程数、内存倍数或多 worker 数。多项目并发/吞吐和生产总容量验证仍归 Phase 7（DC37）；S2b 完成单位成本与参考节点预算，不因此新增 1,000/10,000 仓库正式门禁。
- **峰值补充（owner，2026-11-04）**：初始阶段可能在维护窗口批量上传。单项目一天 5 版是尚未实际发生的假设极端压力场景；跨仓库按 500 个仓库同一天上传作为极端集中到达场景。两者分别建模，不默认相乘成必须验收的 2,500 版/日；500 仓库同日到达不等于 500 个计算任务同时执行，也没有自动确定当日完成或排队时限。年均 6–12 版仍不变。
- **扩展方向（owner 已确认，具体选型待 Phase 7）**：利用仓库独立性，在 Phase 7 评估按项目/仓库归属分配执行与存储资源、有限槽位排队和横向增加服务分区；同仓库写入与 CAS/幂等保持原约束。现有单 executor、启动租约判定、RS root 所有权和共享 control DB/artifact 边界须先评估，不能直接把增加副本当作已具备的跨机扩展能力。S2b 不提前引入分片、分布式调度或共享存储改造。
- **方案确认（owner，2026-11-04）**：同意上述容量分层、两个独立突发场景、单位成本测量后外推，以及 Phase 7 评估横向扩展的设计方向，授权落成方案并继续下一部分。此确认不指定机器数量、磁盘规格、N/M 数值或任务完成时限；这些仍按测量和后续设计确定。
- **处理窗口与优先级补充（owner，2026-11-04）**：功能上允许集中上传后台处理到次日；生产部署按多个 worker 考虑，不以单 worker 作为最终部署目标，具体数量待测。500 个上传通常分散在当天，不会集中在单次处理的数分钟窗口；不据此假定均匀到达。日常交互优先；必要时可评估集中突发压力测试，不因此新增当前基准或 S2b 的 500 路正式门禁。
- **Phase 7 设计落点**：区分 worker 进程数、同时执行槽位 K 与单任务线程 N/内存预算 M；跨仓库有限并行，同仓库 writer/CAS/幂等保持。候选调度在任务领取边界优先日常工作，同时给批量任务有界等待或保底份额，避免持续交互使批量永久饥饿；不抢占正在进行的事务、Dolt 写入或不可逆提交。验证启动租约、共享资源和排队/执行截止时间、上传产物保护期，才能宣称支持跨日批量处理；不把 Phase 6 单任务延迟门槛改成一天。
- **未决输入**：日内到达分布的量化、次日具体完成时点/队列等待目标、worker 数量、实际大小与变更量分布、单位物理存储和运行峰值仍需核对；不将这些未知量默认为零或均匀分布。单任务准备可继续，部署容量/峰值吞吐尚未通过验证。本文确认业务规模输入与调度方向，不替代 kickoff 审核或实施授权。

### DC78 无兼容负担下的 Rust 替换、模块边界与测试生命周期

- **来源与状态**：owner 于 2026-11-04 在设计会话 `01a1a628-e59a-7981-aad5-6bf31e919d38` 明确：项目没有历史包袱或兼容要求；Rust 重构并验证后可完全删除被替代 Python 实现，不作为回退。此方向已确认；技术落点纳入相应 kickoff 审核，非新的实施开工或推送授权。
- **替换规则**：取代 DC37 第 4 项、DC44 第 3 项的永久参照解释、DC50 的 S6 开关安排及 DC72 第 3 项的未来生产 flag 安排。不增加 Python/Rust 部署开关、自动/人工算法回退或为选择引擎新增的 operation 持久字段。开发期间可以临时差分；完成实际调用链接入与验证后，在该阶段删除旧算法、仅服务旧算法的依赖/mock/重复测试及临时双实现入口。不把完整旧算法改名为 oracle 后长期维护。
- **阶段衔接**：当前 S2a 是 test-only parser；生产仍用的 Python parser 尚未被完整替换，S2b 承接接入、验证及清理。比较与 Submit 等模块在各自替换阶段执行相同规则；S6 只做剩余项核对，不统一延期清理。冻结基准、既有 S2a 证据、停止规则和 exit 次序不变；历史提交保留原证据，不为删除旧算法改写已引用提交。
- **测试规则**：删除的是旧实现及重复执行，不是它承担的业务断言。先把语义预期收敛到经核实的语言中立 fixtures/golden、Contract 边界与性质测试，再移交到 Rust 权威 owner；关键预期不能由当前 Rust 输出无审查地自生成。Python 侧保留实际编排/适配/错误传播/端到端恢复测试；取消、预算、租约、事务/CAS、冻结产物与跨 scope 边界照常验证。测试脚本使用 Python 不等于保留 Python 热点算法；其他仍有独立生产消费者的 Python 能力不得误删。
- **语言取舍**：Python 当前适合轻载编排和快速业务验证，但不是永久语言边界。新功能可先用 Python 验证，也可按真实需要直接用 Rust；编排若出现经测量的瓶颈，也可单独设计 Rust 替换。没有本次全量重写编排或移动业务状态所有权的授权。
- **可复用边界**：Rust core 保持稳定输入/输出、错误、取消/截止和资源预算接口，独立于 PyO3 与调用方。未来 Python、CLI 或 AI 工具/MCP 可通过适配层复用同一 core；本轮不新建 MCP server、网络计算服务或通用插件框架。AI 发起业务操作仍经过服务的认证授权、scope、幂等和事务边界，不直接获得数据库/文件系统写入口。未来 Rust 编排可置于相应应用层，不因此让纯计算 core 承担 I/O 或业务 workflow。
- **收益口径**：预期减少双实现差分、重复算法用例与旧依赖维护，并让使用热点的新路径测试加速；不能承诺整个 runner 按 kernel 倍数缩短。Compose/Dolt、进程恢复、I/O、等待及 Rust 编译成本另计；按已有 V8 方法在替换后重新剖析，不因预期收益削减关键覆盖。
- **文档同步与后续授权**：owner 随后于同日同意并授权按需修改设计文档、提交和推送。本次据此定向同步 ADR 0001、ADR 0010 和 Rust policy 的 reference 生命周期、无回退与语言取舍文字；不改 Safe Rust、失败边界、core 依赖方向或测试治理。相关 owning Contract 的实际消费者与覆盖移交仍由各替换阶段核对；新决议优先于冲突旧文字。不因本次文档推送授权改变阶段开工、审核、取证或 exit 条件。

### DC79 基准输入准备工具的并行完善

- **来源与授权**：2026-11-05，owner 在设计会话了解 W4 生成返工成本、缺少独立低成本预检及分段复用后，授权“并行完善这一部分”。允许在独立 worktree/短期分支开发工具并在 05 定向验证，不修改或打断 CT108 正在运行的生成。
- **设计范围**：[工具 kickoff](p6-baseline-input-preparation-kickoff.md)：实际表形态的有界小样本预检；显式分开生成与验收；按相关输入、规则、实现身份和实际文件摘要复用不受影响产物，失败后仍使用新输出根。既有完整 Preview/投影、census、计数、重复 SQL/package SHA 及最终 manifest 不削减；未完成产物不能标为 READY。
- **角色与启用**：设计维护范围和计划；独立实施任务拥有工具与 focused 测试，原基准实施者继续当前运行；原审核者判断工具及证据。候选通过定向审核后协调合入及后续调用，不自动切换运行中任务，不为展示新工具重新生成已通过输入或重测无影响场景。
- **边界**：不改产品、golden、依赖、测量口径、停止规则、节点分工或 S2a exit 顺序；不是 S2b 开工授权。不建设通用恢复状态机，不宣称小样本预检证明全量正确或性能收益。
- **交付（2026-11-05）**：工具代码 `249c09d082`、handoff `9deb891532` 的[代码和定向证据审核通过](p6-baseline-input-preparation-evidence-check-1.md)（`d2ec2cdd5e`），交基准实施者协调合入及后续需要时采用。包含可选 W4 两路生成（默认单路），没有大输入加速或峰值证明；历史无分段来源记录的旧根不自动获得复用能力，当前生成不切换，不为展示工具重生成。本文转记审核结论，不另判实施证据。

- **后续重开与多路接线（owner，2026-11-05）**：若当前单路过程再次失败且确需重开，不再默认单路完整重跑；先按原停止规则处置，获准继续后复用有效产物，确需生成时采用经审核、资源允许的多路方案，不自动降回单路。当前流程不中断。授权空闲 05 并行完善正式四路接线与有界验证，具体范围见 kickoff §5.5：pair 和 W4 分阶段、各首次/独立重复四任务、完整报告与验收保留。正式计时仍按冻结口径与同机单飞执行，不把输入生成并行扩大为多个计时场景混跑；本轮不重做已有 full4 大诊断、不自动导入历史诊断产物。

- **四路交付（2026-11-05）**：代码 `3d6b1ae59b`、handoff `a5e8809f08` 经[复审](p6-input-four-worker-code-rereview-1.md)通过（`aa0e09854b`），支持 pair/W4 分阶段的 1/2/4 路，交原基准实施者协调合入。当前运行不切换；大输入实际采用须另核资源/截止边界，旧有界样本仍绑定 `6f78b8fc50`，不据此宣称全流程加速或新输入 READY。

- **S2b E 后的使用边界（2026-11-06，设计协调记录）**：原基准设计会话核 DC79、剩余 handoff 与实际入口，确认深依赖旧 Python scanner 的历史生成/测量工具没有必须在当前 main 执行的消费者。后续必要生成使用已审 `p6-baseline`/固定 Git 历史（含四路接线 `4007619abd`），优先复用既有输入；旧 V5b/DC63/S1a 测量如需仍在对应冻结源码执行，局部诊断固定 `1f9731dfc3`。E 按已批准的唯一 Rust 路径与[具体删除范围](p6-s2b-e-kickoff.md#1-消费者收口与删除)退役 main 旧工具及孤立依赖，由 E 独立审核具体删除和覆盖移交；不为历史工具重建旧 parser、重做 S1 或提前建设 S6 框架。本记录不改 DC79 原授权、不改运行中任务，不删除或改写冻结 refs/worktree、输入、镜像、卷、产物和证据，也不删除 E 的当前正确性旅程入口及有效依赖。

### DC80 基准停止后的主动处置与 READY 闭包容量修正

- **来源与授权（owner，2026-11-05）**：W4/S4/H1 在 `v2-preview` 失败后，owner 先要求“进行问题排查，看能否直接续跑”，在确定为 READY 闭包 4096 引用限制后进一步要求“继续，并且后续遇到暂停你需要主动尝试排查和解决而不是等待 owner”。设计据此组织诊断、最小修复、审核和恢复；不是把失败运行判为成功或取消运行期停止条件。
- **后续停止的处理**：先停止受影响运行、保留证据，然后主动查明原因；实施者在明确范围内做必要的最小工具或产品修复，审核者核对修正和恢复条件，设计负责影响面与计划。不得因“已停止”就让已可推进的诊断/修复等待下一次 owner 催办。涉及业务语义取舍、扩大阶段范围、破坏性数据操作或无法证明证据可沿用的情况，带具体方案和影响报告 owner；未获相应授权前不越过该边界。
- **04 环境修正接续（owner，2026-11-05）**：owner 再次明确要求“让实施者正式开始恢复测量，不要浪费时间”。当时实际阻塞为 04 backend runner 在新 worktree 缺少 `repository_service/.venv`，七项测试辅助调用失败。保留该次 exit 1 及日志，不把失败归为通过；立即按原节点占用与离线规则补齐同一 clean worktree 的必要环境，核五锁、缓存及镜像身份后重跑既定 backend 门禁。此项是本次明确的修正接续授权，不要求再等 owner，不扩大为任意失败可原样重试。审核者并行核验归因及恢复条件；门禁和目标身份通过后，原实施者直接启动已批准的 checkpoint 副本恢复，不再增加 owner 或设计确认环节。不得用周期性空闲节点检查代替已有明确下一步的修复执行。
- **本次问题与范围**：原 `p6-s1c-exit` 产品在 `ReadyClosureDocument.build` 因 output refs 超过 4096 失败，不是超时或输入身份不符。仅修正满足当前批准规模所需的有限容量边界，保留完整输出集合、排序、JCS/digest、schema、checkpoint/closure 载荷、版本和完整性检查；不截断引用、不减少 W4 数据、不关闭资源限制。具体数值以实际引用计数与既有场景上界核对为依据，经独立审核后固定，见[容量修正 kickoff](p6-ready-closure-capacity-kickoff.md)。设计不替代停止证据复核。
- **限定的恢复例外**：若固定 V→H 的产品差异只为上述容量检查，审核证实此前成功步骤未触发旧上限且结果字节/语义不变，允许在本次基准中使用已验证的 H 镜像，从 `p6bw4s4h120261105a` 的 `v2-preview` 前 checkpoint 的新项目/新卷副本恢复该步及全部后续步骤。此项明确例外于 DC66 第 3 项同一产品镜像、冻结 `p6-s1c-exit` 产品及 DC64 第 2 项 c 共享设施变更的默认整档要求；不扩展为任意产品修正均可续跑。输入、原证据、快照、原卷及失败末态不修改，失败末态不作为恢复源。
- **证明与启用**：实际引用数/类别、容量预算、精确代码差异、旧成功步骤不受影响映射、05 focused/五包静态、代码审核、04 受影响包/容器门禁及 H 镜像身份齐备后，由审核者确认恢复条件，原实施者按授权执行；不再另设重复 owner 确认。恢复工具同时校验来源产品/镜像与目标 H 产品/镜像的精确关系，不增加通用忽略身份开关。新场景及正式 record 标明真实产品版本与步骤来源，不把 V′ 与 H 写成同一镜像。
- **不变边界**：正式计时仍在 CT108 独占，节点占用与离线缓存要求不变；无新输入生成需要时不重生成。已通过且证明不受影响的场景保留，受影响路径须在 H 实测；无法满足本次限定例外时，继续给出最小替代方案而非原样盲重试。S2a exit 仍等基准 exit，修正同步纳入后续产品线；不推送、不改写已引用提交。

### DC81 开发与全量基准解耦，定向验证优先

- **来源与授权（owner，2026-11-05）**：owner 明确同意解除 S2a exit 对“基准整体 exit”的依赖；先推进开发，不过早纠结性能优化，完整测量后续作为参考，允许小范围定向返工；开发过程中的测试/测量尽可能限定范围，减少长时间全量运行。原设计会话继续独立跟踪基准，owner 将新开会话讨论后续开发安排。
- **S2a 收尾**：不再等待基准整体 exit，可立即核对候选、已通过证据、当前主线与后续修复的影响，由适格独立审核者办理合格退出。此前 S2a 候选 `3b3d9c97bc`、handoff `c3c95282bf`、证据复核 `7c5cc2a49efb` 为交接起点，须核最新状态，不预先判定当前 HEAD 可沿用。未受影响证据按现有闭包规则沿用，受影响部分定向验证，不默认重跑全部。此项优先于 DC70、DC72、DC78–DC80 中仍写“基准 exit 后”的旧顺序文字。
- **后续开发**：新会话推进 S2a 收尾与 S2b 设计/kickoff 收口，不重新实施已退出的 S1a/S1b。缺少全量性能数值不再作为所有开发工作的统一前置；DC63/V5b 未测分段登记为待补，不填零、不宣称已优化。映射、消费者、冻结/恢复语义及必要资源预算仍须明确。此次没有把 S2b 准备稿自动判为审核通过；具体实施范围及 kickoff 在新会话讨论、核对后推进。
- **性能与验收**：允许根据后续完整测量做小范围定向返工；优先实现已定功能与 Contract，不因假设性能收益扩大改造。业务正确性、取消/截止、租约、事务/CAS、冻结产物与资源边界仍须验证。当前 W4 Submit 租约失效是未完成的产品路径，不降格为普通性能参数。既有 W2 可达性/阶段性能退出条款的时点如需调整，由新会话给出明确方案供 owner 决定，本条不默默取消它们。
- **性能指标补充（owner，2026-11-06）**：owner 在原基准设计会话 `01a1a628-e59a-7981-aad5-6bf31e919d38` 明确：“如果部分测试/测量被性能指标拦截，可以与我讨论性能指标合理性，当前的性能指标并非硬性门槛，也会有物理限制。”新开发设计会话已通过 `read_thread` 核对原话。既有数值作为当前目标与评估依据保留；纯性能未达目标时，报告实测、物理约束、调整方案及影响，交 owner 决定，不自动判为通过，也不作为不可讨论的永久开发或 exit 阻塞。W2 的具体测量时点和数值调整仍须明确收口，未知项保持待补。此补充不放宽业务正确性、取消/截止、租约、事务/CAS、冻结产物或资源上限；客户端超时导致业务失败须作为运行故障处理，不能仅改称性能偏差，也不据此自行修改 timeout、重试或冻结测量口径。
- **验证比例**：开发迭代使用受影响范围的 focused、Contract/差分及必要容器检查，复用已验证输入、缓存、checkpoint 与合格证据；不为每次修改、文档整理或工具交接重复全量旅程。阶段最终候选仍完成实际改动所要求的权威/容器门禁，按包沿用保持原规则；S5 最终门禁、S6 及发布要求未被豁免。已批准的全量基准由原线独立跟踪，不意味着新代码的必要门禁可以用旧产品基准替代。
- **并行隔离与责任**：原设计 `01a1a628-e59a-7981-aad5-6bf31e919d38` 与原实施者继续基准、停止诊断和定时巡检。新开发线不重复启动该工作，不修改冻结测量 worktree、输入、镜像 tag、卷或证据；共享修复有明确提交/影响映射后再协调集成，不改写已引用提交。05/04/CT108 节点分工、有效占用、离线缓存及正式计时独占继续有效；开发并行不等于同节点并行测量。
- **执行边界**：本条确认流程调整，不代替实施证据审核，不直接授权推送或不可逆操作。新会话无需再次询问是否允许解除 S2a 的基准 exit 依赖，但须确认实际阶段、角色与当前证据。原基准巡检及 DC80 主动处置继续，不因新会话讨论而暂停。

### DC82 新增后端与前端开发测试节点

- **来源与授权（owner，2026-11-06）**：owner 已新增 CT107 `gw-dms-06`（16 vCPU，cpuset 64–79，32 GiB，300 GiB thin，`192.168.233.207`）和 CT109 `gw-dms-07`（8 vCPU，cpuset 80–87，16 GiB，200 GiB thin，`192.168.233.208`），明确要求本设计会话验证、更新项目测试节点说明并判断并行开发条件。该指令授权本轮定向更新 AGENTS、testing-conventions 及前端 kickoff 的节点条文，不改变其他治理文件归属。
- **用途**：06 使用 SSH 别名 `ct107-gw-dms-06`，承担后端 Rust 编译、focused、Contract/差分及小规模 Compose；07 使用 `ct109-gw-dms-07`，承担前端检查、lint、单测、构建、截图与 mock e2e。05 保留基准/共享故障调试、真实数据及前端真实 backend e2e；04 保留权威门禁与 carried；CT108 保留正式测量与 t4。此次不迁移真实数据全旅程，不赋予新节点正式测量或阶段退出证据节点身份。
- **物理边界及自主并行（owner 同轮补充）**：06/07 与相对空闲的 04 共享物理宿主，不与 CT108 共享宿主。Owner 随后在原设计会话明确，06/07 与当前测量独立性强、04/06/07 宿主资源宽裕，不必为两个新增节点资源问题与原总协调通信；本会话通过 `read_thread` 核对原话。06/07 日常开发测试自主并行，无需申请窗口或例行汇报占用；共享宿主不自动转成整宿主排他，也不为新节点常规运行占用 04。各节点自身有效占用、服务/端口及同节点计时独占保留，只有真实干扰、跨节点操作或明确冲突时针对性协调。cpuset 分离不证明完全无竞争，新节点结果不作性能基准。
- **全部 CT 常规协调简化（owner，2026-11-07）**：Owner 明确“如遇到空闲直接置标志位直接使用”，不再反复通信请示。需要占用的任务按现场状态核空闲后原子取得标志并使用、完成收尾后释放，不以跨会话申请/窗口确认或例行起止通知为前置；只有实际占用冲突或涉及他人资源才协调。尊重有效标志和既有节点用途，前端非独占任务仍沿既有例外。已同步 AGENTS 与 testing-conventions。
- **验证范围**：使用 clean、已提交 detached worktree；先修正克隆环境的 root Cargo PATH、Dolt 离线配置及重复 Docker engine ID，保留备份及镜像清单；按 DC67 从 CT201 经 LAN 预填实际缺少的依赖镜像/npm 缓存并核身份。06 做 Rust/扩展/Contract 定向验证与小规模 Compose，07 使用既有前端入口验证静态检查、单元、构建、mock e2e 与截图。不为节点启用重复六包权威 runner或真实数据完整旅程；实际结果与来源记录在 [06/07 核对报告](p6-node-06-07-readiness.md)。
- **预算与不变项**：06 初始 pytest workers/Cargo jobs 建议各为 4，07 使用 `GATEWAY_FE_TEST_WORKERS=2` 限制浏览器并发，与产品 N/M 分开。节点继续禁止公网直连，05 的受限调试代理例外不自动扩展。thin pool 的实际容量由宿主管理员监测；克隆带入的旧证据、worktree、镜像与卷不自动获得沿用资格，初始化不擅自删除。源码通过 LAN bundle 传输，日志在 worktree 外；同节点同 worktree carried、独立审核、停止规则与离线身份约束不变。
- **阶段授权边界**：节点验证通过表示可以在相应用途内并行开展已授权工作，不代替 S2a 的整合/退出审核，也不等于 S2b kickoff 或全部产品实施获准。W2 时点、映射/消费者/覆盖移交及必要资源预算继续按 DC81 收口；不推送、不改写已引用提交。


### DC83 S2b 功能退出与 W2 性能复核分开

- **来源与授权（owner，2026-11-06）**：新开发协调会话提出两种时点安排，owner 明确选择“功能退出与性能复核分开，最迟 S6 收口”。允许在 S3/S4 期间依据后续测量做小范围定向返工，不将本条解释为全部 S2b 产品实施授权。
- **功能退出**：S2b 最终候选仍验证业务正确性、唯一 Rust 路径与旧实现清理、取消/截止、租约、事务/CAS、冻结产物四种恢复状态、必要容量/资源边界及相应权威/容器门禁。结构性计数断言仍需成立。不能用旧产品基准代替当前候选证据。
- **性能复核**：W2 的 30 秒目标、受理到 READY 口径和既有完整路径统计方法保留。CT108 可用时补测，最迟纳入 S6 收口；不再把 W2 完整测量或可达性公式通过作为 S2b 功能 exit 的先决条件。未测、未归因或未达标如实登记，不填零、不记 PASS；公式结果用于性能复核与是否需要 owner 调整目标的讨论，不自动阻断无关功能开发。
- **交付与追踪**：S2b handoff 列出未完成测量、真实来源/产品版本、负责角色、最晚节点及潜在返工影响。若只测后续产品，结果必须绑定实际版本，不能回填为 S2b 历史候选已测；S6 需有有效端到端测量与明确结论，不能以一直 pending 代替收口。阈值、统计方法或执行预算仍须明确决议才能改变。
- **不变边界**：本条只调整 W2 性能复核时点，不自动豁免其他场景的必要验证。超时造成业务失败、租约失效、错误结果、冻结产物缺失及越过资源上限继续按实际故障处置；原 W4 Submit 问题不因本条关闭。正式测量仍由 CT108 独占，不改原基准冻结资源，不重复启动原基准。


### DC84 S2b 容量与配置分步收口、W1 诊断窗口

- **来源与授权（owner，2026-11-06）**：owner 分别选择“采用分步收口”以及“允许无窗口时延期至最迟 S6”。这是容量/验收安排确认，不是整体 kickoff 已审核通过，也不是全部 S2b 产品开工授权。
- **容量前置分步关闭**：kickoff 先依据现有输入、可复核的已有 buffer/字节观测与保守估算，明确实测、推导和未知项；第一步范围限于映射、固定向量与纯 kernel。新规范 IPC writer 完成后立即校准真实 IPC 体积；进入 worker 接线前定 M 并核对 FULL 场景的驻留/临时峰值，注明已实现 kernel 与测量边界；接线后的实际 worker 资源行为仍在最终功能候选复核。不得把尚不存在的新 writer 的字节数或整链 RSS 写成实测，不为取数建设第二套 Python IPC。
- **预算不放宽**：M 仍是包含完整驻留输入、输出、IPC 缓冲及每线程临时预约的计算准入预算，不是 RSS 严格封顶。各实现小步须有适用的有界输入/资源拒绝；阶段性估算不能代替 worker 接线前的 M 定稿与最终边界验证。单位成本与 1,000/10,000 仓库的参数化估算分开；生产总容量、多个 worker 和排队承诺仍归 Phase 7。若测得容量超出预算或无法安全接线，停止受影响的小步并带事实讨论，不填未知为通过。
- **W1 时点**：保留 S2b 起做 W1 诊断测量、S6 正式取证的原安排；如果 CT108 到 S2b 功能退出时仍无可用窗口，允许 W1 诊断延期，最迟 S6 收口。记录待测版本、负责角色与原因；后续结果绑定实际产品版本，不能回填为旧候选已测。
- **其他验收**：W3 按原设计从 S3 起测、S6 取证；W2 沿用 DC83。上述安排不改变既有目标或统计口径，不取消 S2b 的正确性、恢复、资源边界、结构计数及必要权威/容器门禁。租约失效或超时造成实际业务失败仍按故障处置，原 W4 问题不因此关闭；CT108 正式测量继续独占，原基准冻结资源不变。


### DC85 S2b kickoff 确认与 A 节实施授权

- **来源（owner，2026-11-06）**：明确“批准这份kickoff并且启动A节”。批准已审 kickoff 候选 `1a4adaae05`（独立报告 `8b4be7434b`）及 A 节实施；无需重复请求该范围授权。
- **A 范围**：唯一 Rust 纯内存规范 Arrow mapping/IPC codec、内存读取校验、独立固定向量及 N/chunk/列序确定性；输入为已物化/投影且按 owning 规则排好行的数据与规范声明。按[任务单](p6-s2b-a-kickoff.md)完成局部有界预算、取消/有限截止和必要依赖/容器验证。
- **阶段边界**：B 业务 kernel、C store/mmap/refs/recovery、D worker/config 与 E 生产切换/旧实现删除不因本次授权自动开工。生产 M/FULL 校准依旧按 DC84；不提前修改生产路由或建立双路径开关，不新增第二 Python IPC。
- **执行与审核**：每小节新实施者 Luna/max 与独立审核者 Astra/high；设计/审核可以修改已协调归属的文档，代码原则上由实施者修改后独立复审。A 在 06 做定向验证；生产依赖变化按实际影响完成本节候选容器检查，不逐提交重跑全量。最终 S2b 的 04 门禁与 t1–t4 正确性不豁免。
- **协作**：原基准与 W4 故障继续独立；共享修复按精确提交/路径协调，不碰冻结资源。未经另行明确授权不推送、不改写引用提交；A 完成后先交付再安排下一节。
- **A 交付记录（2026-11-06）**：产品候选 `db7767ffbb`、[实施交接](p6-s2b-a-handoff.md) `b625d775e0`、[独立审核](p6-s2b-a-review.md) `83b927207a`，结论 A GO、无未关闭 Finding。06 定向及必要容器证据已核对；本节两角色结束，后续小节另建角色。此记录不增加 B–E 授权、不标记 S2b exit，也不将未知性能/生产容量视为通过。


### DC86 S2b B–E 逐节推进与角色授权

- **来源（owner，2026-11-06）**：在 A 独立交付后，Owner 同意“本会话持续统筹、B–E 分节自动推进、每节重建实施者和独立审核者”，并明确授权直接推进 B–E 及每节两个新角色；如需额外角色/子 agent，先暂停汇报原因并约定模型与思考强度。
- **授权范围**：按已批准 [kickoff §5.4](p6-s2b-kickoff.md#54-分阶段实施和验证-owner) 顺序推进 B 业务 kernel、C store/ref/recovery、D worker/callers、E 单路径删除。每节先给出明确范围，在前节完成实施、必要验证、独立审核和固定交接后启动下一节；不重复要求 Owner 逐节开主会话或确认相同授权。本轮从 B 开始，A 固定交付保留。
- **既定角色**：S2b 每节新建实施者 GPT-6.1-Sol / high；当前 B 独立审核者 GPT-6-Astra / high，C–E 改为 GPT-6.1-Sol / xhigh 或 max（初始安排及后续 Owner 调整见本条末尾记录）；结束后不复用到下一节。设计/审核可改已协调归属的文档，产品/测试修复由实施者执行，审核复核。明确小问题允许双方直接闭环。不得自行增加第三角色、额外会话或让子 agent 再派生；确需增加时暂停该依赖工作，向 Owner 说明原因、任务边界、拟用模型/思考强度，获确认后创建。
- **停止与恢复**：语义、验收或架构边界需要改变、容量前提不成立、同一问题多轮不收敛、必要节点/证据无法取得时，停止受影响步骤，保留事实并报告具体方案。明确范围内的小问题继续按 DC80 主动诊断、最小修正和独立审核，不把暂停变成无限等待，也不盲目重复失败命令。额外角色授权不能从“小问题可解决”推导。
- **前置与门禁不变**：DC84 的 C 后 FULL/IPC 容量校准和 D 前 M/envelope/reserve 收口仍必须完成；未知值不视为通过。最终 S2b 退出单独办理，04 权威/容器、t1–t4 正确性及事务/CAS、租约、取消/截止、冻结边界均不豁免。W1/W2 时点按 DC83/DC84，原基准线独立；不推送、不改写引用提交、不改原线冻结资源。
- **执行改进**：依赖方向/架构守卫在首批依赖改动时检查；固定 clean 候选后再准备最终镜像。多行远程操作优先外置脚本，日志明确命令来源、起止 HEAD/节点、exit 与外部 SHA；验证仍按影响面收敛，不每轮重复全量 runner、旅程或输入生成。

DC86 收尾记录（owner，2026-11-07）：最终验收与H绑定独审GO后，Owner 明确选择“现在办理本地 S2b 退出”，授权本轮独立审核者在报告 `9220f3cdecba7df3e50fec00d77d1dd9efb0f678` 上创建本地附注 `p6-s2b-exit`。已执行并核 annotated 类型/完整目标/注释，tag object `6076acbd552045c7c1846ce4c8191ebd4605e35f`；V=`a6876d5600`、H=`3580e6649f` 不变。A–E已交付、S2b功能退出；未推送，未授权或启动S3。原成功及失败证据、gate WT保留；W1/W2正式测量和原基准线继续按既定范围独立收口。

DC86 执行补充（owner，2026-11-06）：B 因重复源码同步准备错误及节点占用前置遗漏暂停后，Owner 同意重建本节两角色尝试：**仅 B 实施者改为 GPT-6.1-Sol/high，B 独立审核者仍为 GPT-6-Astra/high**。后续各节实施者默认仍为 **GPT-6-Luna/max**，不得把本次例外扩展到 C–E。若仍反复出错，继续暂停汇报；额外角色仍须先说明原因与模型/强度并获确认。此前缺失原子占用的日志只供诊断，不追认为合格证据。恢复须重新满足节点占用、clean 候选和离线环境前置；本次不改变功能范围或门禁。

DC86 后续模型调整（owner，2026-11-06）：主协调核对 A/B 反复错误记录后，Owner 进一步同意“如果确实比较多允许 S2b 的后续步骤实施者改用 6.1sol”。据已确认的执行问题，**S2b C–E 实施者改为 GPT-6.1-Sol/high**，独立审核者仍 GPT-6-Astra/high、每节重建两角色；此项取代上一补充对 C–E 保留 Luna/max 的安排，仅限 S2b，不自动扩展其他阶段。B 当前 Sol/high 组合继续工作，未增加第三角色；反复失败仍暂停汇报。

DC86 审核模型后续调整（owner，2026-11-06）：Owner 提出后续审核者改为 GPT-6.1-Sol，按需选择 xhigh/max，并要求协调者在合适节点直接调整。执行节点选为 **C kickoff 创建新角色时**：当前 B 的 Astra/high 审核者完成本节，C–E 审核者使用 **GPT-6.1-Sol，默认 xhigh**；每节创建前依据事务/CAS、租约、冻结恢复和证据冲突复杂度决定是否使用 max，并记录选择。实施者仍 Sol/high。接口可在创建时指定模型/强度，无运行中协作 agent 热切换入口；若需中途额外重建，仍先报告并获确认。每节二角色、独立上下文/只读审核工作区及真实证据要求不变，不以同模型或更高强度替代独立审核。

### DC87 S2b 单 worker 的显式资源配置

- **当前生效配置与最终验收（owner，2026-11-07，完整 t3 校准后确认）**：Owner 明确“确认上述配置与验收范围，可以开始最终验收”。采用 **32 GiB 容器上限 / 8 GiB 工程预留 / 显式 M=24 GiB**，N=1、单 active operation；分别为 34,359,738,368 / 8,589,934,592 / 25,769,803,776 bytes，M24 也是本档可配上限，缺失/非法/越界仍拒绝。此项替代此前 24/8/M16；40/8/M32 为未选备选，临时 64/16/M48 与日志不合 main。
- **当前选择依据**：a10 fresh 完整 t3 宽裕校准经 `cde10c5acd` 独审通过，最高预约 19.907343 GiB，M24 留 4.092657 GiB；按真实调用时序投影，最紧 native inspect 仍有 15.622567 GiB 预算，parser/business/encode 至少 23.6686 GiB。同 worker cgroup 峰 4.438370 GiB 仅属于该临时校准，不能称最终 32/M24 已实测，不能把预算上限当实际消耗；最终候选实际验证仍须完成。
- **DC33 本轮已确认范围**：扩容后的 **06 执行最终候选 fresh 完整 t1–t3 功能/容量旅程**；**04 同候选六包权威 runner 与其中 Compose** 可跨节点并行。06 此次获准真实旅程不使其成为权威 runner/carried 或正式性能节点。t1/t2 补实际承载，未采用仅 t3 的范围备选；t4 依 82 完整来源和独审新增费用上界沿用：M24 满足 M≥18,678,133,632 B 的保守条件，保留原物理峰的 24/M16 来源标记，不冒新档物理实测。复用未影响的 A–D 语义证据，保留必要静态/定向、实际当前容器及最终 H 同04同WT闭包绑定；同轮 Compose 不另重跑，不生成新输入、不逐档试预算。实际失败按 DC80 留证、诊断/明确修正与独审，S2b exit 另办理，无推送授权。

- **此前 M16 选择（历史，已由本节当前 M24 配置替代）**：Owner 选择 **A：24 GiB 容器上限 / 8 GiB 工程预留 / 显式 M=16 GiB**，N=1、单 active operation。分别为 25,769,803,776 / 8,589,934,592 / 17,179,869,184 bytes；M16 同时为本档可配上限，M 必须显式填写，缺失/非法/越界拒绝。此选择替代下列 2026-11-06 的 12/4/8 配置；旧选择与失败证据保留为历史，不把临时 64/16/48 合入最终 main。
- **选择依据与限制**：宽裕档 v1/v2 前缀最大预约 12.173 GiB，修复 FD 后的独立 History 最大预约 10.448 GiB；M16 对已观测峰值留 3.827 GiB、约 31% 余量。旧 worker 前缀 cgroup peak 6.519 GiB，独立 History 为另一 worker 的局部数据，两者不拼为完整峰值；charged 不含全部 native temporary，故这是经实测支持、仍须最终候选验证的配置，不保证所有输入 quota 同时满额、2×t4 或正式性能达标。8 GiB 是工程 reserve，不是已测固定开销。
- **直接推进范围**：将最终配置与必要 owner 断言落 main，保留最小 FD 修复，移除临时观测候选差异；按影响面 focused/static 后集中取得最终 04 六包实际门禁及所需当前容器证据、05 t1–t3 与 CT108 同 worker 完整 t4。已有相同 runner 中 Compose 不单独重复，A–D 未受影响语义证据按现规则复用；不逐档试跑，不为既定准备/focused 反复申请运行许可。新实质阻塞仍按 DC80 诊断、明确修正及独立审核；S2b exit 另办理，无推送授权。

- **来源与确认（owner，2026-11-06）**：C 的真实 kernel/IPC/store 双侧校准及 XML/AST/composite 补充测量后，Owner 选择 **A：单 worker 容器内存上限 12 GiB、预留 4 GiB、显式 M=8 GiB**；B 的 24 GiB 方案仅保留为未选备选。N=1、单 active operation，不由本决议放开多 operation 或多 worker 并发。
- **配置语义**：12 GiB = 12,884,901,888 bytes；reserve 4 GiB = 4,294,967,296 bytes；M 8 GiB = 8,589,934,592 bytes，当前 A 档上限也是 8 GiB。M 是单 operation 活跃资源预约，8 GiB 为部署中显式填写的初始值，不是代码隐式默认；缺失、非法或超出 envelope−reserve 时拒绝启动。部署声明与实际容器限制须一致，不以 06 的 32 GiB 代替生产预算。无需为此新建通用 cgroup 探测或 allocator 追踪框架。
- **证据边界**：[C 容量报告](p6-s2b-c-capacity-calibration.md) 的固定输入实测与分进程峰值估算支持配置选择，不是实际 production worker 峰值、严格上界或 capacity PASS；reserve 也是工程预留，不是已测得的固定非 operation 上限。既有各项输入 quota 不保证全部最大值同时可接受，仍按 M 在增长前拒绝。
- **D 必验**：真实 worker 的 FULL 两侧同时存活资源、借用/共享 backing、mmap、转换/排序、IPC/adapter copy 与 staging 的合并预约和峰值；M 缺失/非法/超限启动拒绝、增长前资源拒绝，以及真实 cancel/drain/lease_lost/可选 deadline 与 EOF/publish 屏障。不得把局部 kernel 各自低于 M 等同总量合格，不将 OOM 作为正常资源拒绝路径。
- **推进边界**：关闭 D 接线前尚缺的生产 envelope/reserve/M 选择；C 独立 GO 后按 DC86 既有授权创建 D 实施与审核角色继续，不再请求重复配置确认。若实际 worker 校准不支持此档，保留证据、诊断最小修正，必要时列方案交 Owner，不静默增加 M、容器限额或降低输入/正确性验收。W1/W2、最终门禁及原基准独立跟踪不变，不授权推送。


- **E 校准推进调整（owner，2026-11-07）**：E 修正 metadata-only 单侧比较误计费后，t4 Preview 通过，首次 Submit 在真实行镜像/索引/回放准入被 M8 拒绝。冻结输入只读核算的已知预约约 12.071 GiB，不是完整 used 或实测内存峰值。Owner 要求“先增大预算，然后按测量结果决定”，避免逐档试探。设计协调据 CT108 实读 96 GiB，选择**隔离临时校准档：worker 硬限 64 GiB、reserve 16 GiB、显式 M48 GiB，N1/单 active 不变**；约 32 GiB 留给其他服务/OS 是节点余量，不是这些服务的硬预约。本数值是协调者落实测量安排的临时选择，不代表 Owner 已将最终生产档改成 64/16/48。
- **校准范围**：基于固定 E 产品建立任务专有已提交候选/工作区；仅资源常数、Compose/CLI/driver 对应值及必要定向断言，以及读取现有 `high_water_bytes`/`stage_admissions` 的最小临时日志。记录每 execution scope/step 的预约高水位，按 operation 汇总；stage temporary limit 是可用上限，不作为实耗。实际 cgroup peak 保留同一 fresh worker 整生命周期累计口径，不虚构各 operation 独立峰值。临时观测不进入最终 main，不新增 observer/采样框架，不改 GC、租约、预算系数或输入。
- **一次测量后定档**：独立审核及必要 focused/static 后，在 CT108 新项目 fresh t4 完成一次校准；不为临时档重复六包权威，不把临时配置/观测当最终验收。仍保有限预算与硬限；真实故障或再次预算拒绝就停并保现场，不继续逐档增加。测后依据实际预约/内存峰值、余量及未覆盖范围向 Owner 提出最终配置；最终档确定后再集中取得其必要权威/容器与真实数据证据。本条 A 档作为此前已确认最终配置的历史事实保留，在新最终决定前不默默改 main 默认，不以此豁免 S2b 功能/资源边界。

- **E History 诊断接续（owner，2026-11-07）**：宽裕档校准的 v1/v2 前缀成功、末尾 History control DB 打开失败。FD 复现脚本连续两次准备错误按 DC68 停止后，Owner 明确批准“允许按已审第三稿续做，明确问题修复后定向验证”。具体第三稿 SHA `4b982cb016eb3ff4903f42e6cdda489cf4e9136751019d26fc7c81523bf8df65` 已静态独立核过 factory/kernel scope 生命周期；先运行该诊断，证实根因后最小修复/复审，再在独立冷拷副本仅续 History。原失败日志与卷保留，不重复整旅程，不把局部成功拼成原校准 PASS，最终配置仍另定。此项为本次具体接续授权，不改变其他失败停止规则。

- **E 最终验证后的容量补测（协调执行记录，2026-11-07）**：24/8/M16 候选 `82c4251b6c` 的六包/容器与完整 t1/t2/t4 通过，t3 v2 Preview 在真实双侧比较准入被拒绝。只读部分预约下界已达 16.867 GiB，另以 `464289138a` 补齐 non-record 新增列分支的漏预约（不改业务/系数，定向已独审）。协调者依据 Owner 已有“先增大预算，然后按测量结果决定，而不是多次尝试”授权，将同一隔离 64/16/M48、N1 策略补到未覆盖的 t3 剩余路径；候选 `a10dec894e` 已核与 main 业务等价。此为原授权的执行安排，不声称新的 Owner 批复；不把“先 Owner 再测量”的额外等待作为前置，也不把它当作最终生产档自动批准。保原失败；原拟冷副本续v2 Preview，但05被原线有效占用后，协调者改为CT108一次fresh完整t3宽裕校准，使用既有输入、只增加已成功前缀约8分钟成本，取得完整同worker峰值，不复制05或重复其他档/runner。最终生产配置与必要真实数据范围在测后依据具体结果交 Owner 确定，当前 main 仍为 24/8/M16。方案见 [E 任务](p6-s2b-e-kickoff.md)。

### DC88 纯重算阶段的正常 drain 交接

- **来源与确认（owner，2026-11-06）**：D 实际接线发现，在尚未写出本次新 checkpoint 时以普通 retryable failure 表达 drain 会消耗 R5 的三个失败恢复会话，连续正常停机可能导致业务永久失败。现有 safe-handoff 又要求本 session 最新已提交 checkpoint，不能伪造。Owner 明确选择 A：窄幅扩展现有 Runtime/LeaseSession，正常停机安全重排队，不耗失败次数。
- **范围与前置**：仅适用于已注册为 `PURE_RECOMPUTE`、当前未产生外部副作用的执行阶段；应用/registry owner 判定阶段能力，不从某次 kernel 调用猜整个 step 的 effect 边界。必须有真实 `ExecutionControl.drain_requested` 与 fresh 有效租约。取消优先处理为原业务取消；失租/过期/陈旧 CAS 禁止继续写。Submit prepare 的实际注册为 PURE_RECOMPUTE，可在本地冻结读取/转换阶段按这些前置使用；外部 import/等待/Finalize 不因本条变成可重算。
- **最小转换**：沿现有 LeaseSession mutation lock、fresh control DB transaction 与 CAS，使用已有 `RUNNING → RETRY_WAIT`，设置立即可重领、清 worker/token/lease，保留既有 checkpoint（可以为空）、prior outputs 与 Preview/Attempt 等业务保护。不要求为未完成计算制造新 checkpoint，不发布部分结果；未挂接临时产物仍用原 cleanup 规则。
- **计数与分类**：以独立的正常 drain 诊断区分于故障和 Repository healthy wait，下一次 claim 保持当前 attempt_count，不增加也不重置；operator recovery session 授权语义须保留，不能靠清诊断取得额外自动恢复。重领后的真实失败、crash、失租仍按原 R5 额度和规则处理。不复用 `healthy_external_operation_wait` 冒称远端健康，不改变 `MAX_RECOVERY_SESSIONS` 或外部 effect 后的原 reconcile/冻结规则。
- **验收与边界**：D 更新 owning lifecycle/recovery 文档，实施者实现、独立审核复核。定向验证 fresh lease/cancel/CAS 与失败回滚、原 checkpoint/保护不变、重领计数及 operator 分支，再做一条真实 worker drain→重领继续的集成验证。无新 schema/status、持久预约或并行租约状态机，不追加内部时序全排列；现有 180 秒 drain timeout、无自动强杀、节点/离线/最终容器门禁不变。此条不证明实现已经通过，不接管原基准，也不授权推送。

### DC89 BE-a/BE-d 重启设计与归档待审核门禁

- **来源与确认（Owner，2026-11-07）**：S2b功能退出后核查FE3依赖，BE-a只有旧kickoff审核、BE-d仍为草案，均未完成产品交付。Owner授权先联合补充设计；不把此前S2b B–E开工/角色授权延续为本轮全部实施授权。
- **BE-a新增方向已确认**：同exact业务scope、当前baseline下有未关闭PENDING提交，阻塞归档；草稿不阻塞，active SubmitAttempt原规则保留。PENDING必须先通过、退回或撤回，不提供人工忽略按钮。新的APPROVE须在写事务检查当前baseline；过期拒绝，WITHDRAW/REJECT保留出口，合法成功幂等回放不按新动作重新判定。归档仍唯一选中、其余approved sibling按原确认关闭，不合并内容。
- **BE-d成员规则已确认**：最终closure每entry按顺序对应一个普通tar文件；manifest.json、artifact-closure.json在前。共享由assembler在最终closure中表达，下载层不按source_ref/hash另去重，不用hardlink/symlink省掉路径；若两个合法entry有不同logical_path，则两者都发送。
- **状态边界**：S2a/S2b前置已满足，不等原基准整体exit；旧BE-a审核`fcbfb4c1a0`仅覆盖原稿，新增范围需独审。原冻结测量线不接管、不改写、不重启；不推送、不重写引用提交、不启动S3。
- **落点**：[BE-a §9](p6-be-a-design.md#9-待审核阻塞归档与基线前移2026-11-07dc89)、[BE-d设计](p6-be-d-design.md)、[联合kickoff](p6-be-a-d-kickoff.md)。本决议记录业务方向，不声明新接口或门禁已实现。

### DC90 归档时间倒退与来源解释的业务补充

- **来源与确认（Owner，2026-11-07）**：Owner指出旧实现有时间倒退、initial来源不明（可能漏上传）检查，核查确认当前vnext没有等价门禁，且缺口早于S2。Owner同意随BE-a/BE-d补充设计；不重做S1–S2b，也不把旧阶段证据当本能力通过。
- **来源匹配已确认**：当前baseline X下A:X→Y、B:Y→Z合法，A:X→Y、B:X→Z同样合法；initial可以匹配已解释的initial或modified，不强制线性链。A/B共同未知initial Q仍需处理，不能相互匹配自证来源；共用根因列出受影响提交。范围限当前baseline及同baseline未关闭已通过提交；旧归档历史不自动放行。
- **人工接受已确认**：时间倒退、来源不明、必要生成时间缺失允许archive_submission权限持有人逐项填写原因后接受，绑定具体输入和影响集合。原始异常不改成自然PASS；损坏、越权、事务/CAS冲突不豁免。复用现有Archive审计，不增加无消费者平台。
- **时间口径已确认**：采用UTC；无时区按UTC，有offset归一UTC。从version_manager.saved_time取源序最后一个可解析值，不能替换为最大值。若最后有效值不是最大有效值，该差异自身作为数据问题诊断。原始顺序提取必须在Rust规范排序前完成，不能从排序后的存储猜最后值。
- **闭环缺口及Owner后续确认**：新业务核验可能在APPROVED后阻塞，删除RETURN_FOR_REVISION后若操作者不接受异常将没有正常释放出口。Owner选择新增“有理由关闭、不归档”：保留APPROVED历史、关闭该提交并释放工作区以重提，不伪装成撤回，不推进基线。独立权限/审计/事务与History消费设计见业务设计§10；本条确认方向。具体设计随后在候选`16472197b4`经报告`a5d87540e6`独审GO，未启动实施。
- **待审技术细化**：既有canonical内容身份的复用、源时间语法及质量诊断、Checkpoint/Preview/Attempt/Submission/基线的持久绑定、来源图与有界诊断、具体audit/HTTP形态及容量、统一终局处置事实与关闭的权限/回放；详见[归档业务核验设计](p6-archive-business-validation-design.md)。上述不是原产品现状；实现前同步owning Contract/版本/golden并独审。
- **阶段边界**：设计先收口，新增能力独立列验收；已完成阶段与tag保持历史含义。后续若改Rust/元数据接口只按真实影响定向验证，不恢复被替代Python、不默认重跑全量基准。原测量版本和本轮新语义分别标识。
- **2026-11-07独审后技术细化（设计者制定，候选`16472197b4`经报告`a5d87540e6`复审GO；非新增Owner业务决议）**：按`e92afaa53f`的B1/B2，将字段提取语法固定为`gateway-vnext/configuration-generated-time/v1`（完整日期/秒、T或单空格、最多6位fraction、Z/±HH:MM、UTC边界与ASCII trim），不扩展Shared Kernel scalar；200候选的异常数保守上界8N+1，选择确认1、异常引用1601，紧凑Start最坏转义预算197,265bytes小于256KiB。详见业务设计§4.1/§7.1。N1按BE-d§2.1交前端owner修UTF-8 PAX字节计数，并需同tar互通才能报FE3依赖解除；未运行产品测试或启动前端实施。

### S3 最终真实数据范围与本轮06用途（DC33，Owner 2026-11-08）

- Owner已确认S3最终产品fresh t1–t4完整功能范围：v1及重复Preview为MODIFIED_ONLY、v2为FULL，覆盖Submit、真实读取/approve与History，保持N1、worker 32 GiB/reserve 8 GiB/显式M24 GiB；比较、记录与风险均被替换，t4不沿用S2b旧算法结果。正式退出、tag与push仍另办。
- 05在FE3b连续轮次中有效占用，S3准备准入正确拒绝且没有启动测试。协调者先固定06替代稿并由E原审在`3ec25a2f76` §31静态CLEAR；Owner随后明确回复“授权06完整t1–t3”。据此仅将本轮S3最终fresh t1–t3节点从05改为06，完整范围、模式、输入与资源档不变。04权威runner/carried和CT108 fresh t4及W3/W4性能职责不变，不把06功能旅程当正式性能依据。
- 此为本轮明确用途授权，不继承S2b一次性例外，不改变06常设职责或冻结N/M；保有效占用/离线/clean来源与首失败留证规则，按实际干扰协调共享宿主而非自动互斥。当前候选或后续修订仍须适用独审、门禁和逐包/镜像绑定；授权与脚本CLEAR不代表产品、真实数据或性能已通过。执行与原始失败见[S3协调 §24](p6-s3-coordination.md#24-固定v集中取证与06专项用途)。

### DC91 五节点统一配置、按空闲调度与一轮清理（Owner，2026-11-08）

- Owner确认五测试节点均改为32C/64GiB，后续前后端和并行任务不再固定节点，只要空闲并遵循有效标记即可使用。取消旧固定用途及轻量前端无标记例外；池内换点无需再次申请专项用途。
- 工具链、离线缓存、clean固定worktree、镜像身份、同源carried、同组测量同节点同配置仍按原规则；规格一致不证明缓存齐全、物理隔离或旧样本等价。生产N1/32-8/M24不因guest配置改变而改变。
- 同时授权一轮删除无法复用的历史测试文件；执行前明确路径/归属/无消费者，保留引用证据、当前carried来源、冻结原基准、真实输入和未决故障状态，不全局prune、不动他人有效资源。具体规则见AGENTS和[交接计划](p6-s3-s4-parallel-plan.md)。

### DC92 S4提前实施的顺序例外与S3条件性诊断（Owner，2026-11-08）

- Owner计划S4设计完成后同步提前实施，授权更新阶段顺序例外；S3预约归因与临时增预算测试可逻辑并行。Owner随后明确：**S4设计/实施在新对话，本对话仅作合理性判断与决策**，不在本轮启动S4工作。
- S4仍须先补齐详细设计、kickoff与独立审核；提前实施不以S3 exit为开工前置，但不签S3通过、不放行S5、不改冻结SQL/golden/阈值/批量规则或恢复边界。具体开工在新对话按设计与授权推进，不将本条当作已完成设计审核。
- 临时增预算诊断方向已认可，具体M/envelope、worker生命周期和验收口径尚待固定；不得自动修改生产N/M或把另条件结果计为原M24同worker容量/正式性能PASS。原W3基线Submit失败及首次拒绝点未知保留，S3仍BLOCKED_CAPACITY。
- 三线文件归属、候选隔离与证据归因见[交接计划](p6-s3-s4-parallel-plan.md)；本轮提供[S4新对话设计提示词](p6-s4-design-discussion-prompt.md)，不提前实施S4或扩入S5。

### DC93 Q18独立优先交付与S3补测衔接（Owner，2026-11-08）

- Owner明确Q18可随S3补测一起验证、可先完成。它是独立归档接口补缺，不归入S4算法，不改变review权限/CAS或以硬编码版本绕过缺口。
- 目标为归档候选读响应提供同事务权威review_version，供archive-only关闭请求填写expected_review_version；固定Contract/OpenAPI、实现、独审和适用节点/容器证据齐备后才交前端解除前置。生成时间问题保留现代码检查与已修订的异常预期，不混为Q18产品修复。
- 本轮已形成产品候选a1ca3bad93；节点证据未运行，不能把实现提交或执行稿静态CLEAR写成通过。实际状态见[Q18 handoff](p6-be-q18-handoff.md)与原审核者报告。

### DC94 S4设计澄清与DC33验收范围（Owner，2026-11-08）

- 本轮Owner要求补齐S4全部设计缺口、落成可实施的完整方案和执行计划；只做设计，未授权产品实施或测试。
- 存储键独立判定：Submit按稳定、唯一的canonical storage key及完整persisted列判断patch；与前端effective compare key不同本身不迫使rebuild。同步修正Storage Mutation §4旧歧义，保持DC45/ADR0014与现行生产SQL；不改变1,000行/1%、256行/4MiB或200MiB规则。
- 恢复口径：T1即创建PREPARED Attempt，按prepare checkpoint是否已持久化区分构包/复用；非INITIAL缺失或损坏parent manifest继续拒绝。同步修正Canonical Storage §5/§6.1旧文字，不改状态机、checkpoint或产品行为。
- Owner确认S4 DC33范围：原N1/32GiB envelope−8GiB reserve/M24下fresh t1–t4完整Preview→Submit→审核→Archive→History；冻结2×t4首次/少量变化/几乎全变Submit各正式组1预热+3测量，保原样重传零Repository operation断言，100%压力单列报告。模式、输入、计数和统计细化见[S4 kickoff §6](p6-s4-kickoff.md#6-owner已确认的dc33范围与统计)。确认范围不授权本轮执行。
- [S4设计](p6-s4-design.md)/[kickoff](p6-s4-kickoff.md)/[独审提示词](p6-s4-review-prompt.md)为本轮交付；须独立设计审核，再核实施授权。S3仍BLOCKED_CAPACITY，Q18节点证据仍独立，S5前置不变。临时大预算的具体参数仍归S3另案，不由本条批准。

### DC95 S3补测worker资源上调授权（Owner，2026-11-08）

- Owner在授权继续完成Q18与S3剩余工作/退出候选后，明确允许“在容器现有资源范围内增大worker资源（最大32C/64G）”。本条补充DC92的临时增预算方向，允许协调者在上限内提出并固定实际worker envelope/reserve/M及CPU配额，不需要为每个职责内参数选择重复申请；不增加节点或接管他人资源。
- guest为64GiB，实际配置仍须计入Repository Service/backend/OS余量并符合M≤envelope−reserve；kernel N与测试workers、容器CPU分别设置。当前生产默认N1/32−8/M24未因授权本身变更，支持更大显式配置所需的最小settings/容器/工具调整须固定并独审，不以只改环境变量宣称生效。
- 原M24的W3基线Submit失败、首次拒绝点未知和未运行项保留。新资源档的完整旅程、统计、容器与真实结果按实际条件取证，不记为旧M24同条件容量通过或同条件性能提升。若作为后续S3候选的资源条件，明确写入交接并交独审核收；正式阶段手续、tag/push仍另办。
- S4由另对话负责，本条不授权本会话实施S4算法。触及冻结语义/golden/恢复边界等设计冲突仍暂停受影响部分讨论；日志监控与固定稿执行优先由唯一Luna测试者承担。

## 3. 设计阶段待定项

| 项 | 所属决议 | 何时定 |
| --- | --- | --- |
| ordered 表摘要的统一口径；是否保留 `ordering_digest`；是否删除 `fast_row_digest` | DC39、DC58 | 已定：统一为表摘要，删除 `ordering_digest`（设计 §4.1）；删除 `fast_row_digest`（DC58） |
| W1–W4 目标数值定稿 | DC35 | 已定稿（DC53） |
| 记录写后回读：Rust 重算摘要或删除 | DC54 | Phase 6 设计 |
| H2 门槛定稿 | DC38 | S5 冷读验收（V7 已提供参考） |
| 行级修改的阈值定稿 | DC45、DC57 | S1a 按批渲染后复测并冻结（含 UPDATE、DELETE 批量上限；不达标时按 DC57 第 4 项交 owner）；S4 只做回归，须调整时作为例外交 owner（DC55 第 5 项） |
| Arrow 列映射 | DC46、DC76 | 固定候选 `1a4adaae05` 技术审核完成；UTC/输入范围已确认，整体 kickoff 与首节 A 已由 DC85 确认 |
| 规范表存储的磁盘需求估算与参考节点磁盘容量；上传侧原始表是否还有其他使用方 | DC42、DC46、DC84 | 使用方及有界容量输入已核清；实际 IPC/FULL、M 与容量边界按 DC84 指定的实现节点关闭 |
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

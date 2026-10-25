# Phase 6 规划讨论稿：按业务阶段的性能优化

- 状态：**讨论稿 r14，尚未形成正式决议**。本文整理 owner 与审核方的讨论结论，不改变任何现行 Contract、ADR 或计划；§13 的事项经 owner 决议后，才进入正式的 Phase 6 设计与执行计划。§13 中标为“owner 方向”的条目是 owner 已给出的方向，细节仍待讨论；标为“已决议”的条目以 S0 owner 决议记录为准。
- 日期：r1 2026-10-17；r2 2026-10-24（P5 exit 后更新：S5 实测数据、Rust 目标与并发分层、SQL 解析器主线与差分验证、开启前问题清单）；r3 2026-10-24（A1 目标设定已决议为 DC35，§3 改写为决议内容）；r4 2026-10-24（DC36 生效，更新 §13 D2；新增 §13 D5 Rust 测试入口、D6 单次门禁时长；§9 D1 增加审核分析，§13 B1 倾向改为“保值统一”；新增 §9 D9 与 §13 B8：只增列的 schema 变化）；r5 2026-10-24（D9/B8 记录 owner 方向、testdata1 计数、schema 演进分类与触发事件预留、ENUM 值域扩展）；r6 2026-10-24（owner 决定 ENUM 标签扩展算兼容、Preview 不提示）；r7 2026-10-24（SET 同理、只减列保持现行；§9 D2/D3 增加审核分析，B2 记录 owner 方向：同步写入、正式引用只保留 head、先不压缩）；r8 2026-10-24（§9 D5 增加第 ③ 层审核分析与 History 缓存分析，B3 记录 owner 方向：拆分、跨操作缓存暂缓）；r9 2026-10-24（diff/risk 按 TTL 保留；History 整表打包、优先读表缓存，撤回按需读取；§12 登记标准模式 bundle 不含整表，新增 §13 B9）；r10 2026-10-24（B9 范围：Preview 与 History 每个节点都含全部表，bundle 用 Parquet 加导出缓存；跨操作缓存实现排在 D7 之后，以 A2 验收）；r11 2026-10-24（§9 D7 增加审核分析，B5 记录 owner 方向：Rust 加 arrow-rs、standard/keyless 先行、ordered 不读不比归入 B1 阶段、整表新增/删除改为整表浏览）；r12 2026-10-24（B4 拆出单独立项、B6 不做，均按重开条件登记；V3、V4 不再是前置任务）；r13 2026-10-25（新增 §9 D10，B7 记录 owner 决定：表级跳过未变化表、变化表按阈值行级修改或整表重建、渲染直通；新增 V7；§14 预留外部分区库）；r14 2026-10-25（新增 §3.8，A2 记录 owner 决定：History 分 H1/H2/H3 三种负载、Submit 按完成时间设宽松上限；补充 Submit 后首次 History 的命中路径；V7 增加 Dolt 读取实测）。
- 范围：P5 收口之后的性能工作，即 [implementation-stages](implementation-stages.md) §9 Phase 6 与 §10 Phase 7。
- 关联：
  - [S0 owner 决议](p5-arch-closure-s0-owner-decisions.md) §13（DC30）、§14（DC31）、§15（DC32）；
  - [P5 收口设计](p5-arch-closure-design.md) §4.6、§5.3、§13；[S5 handoff](p5-arch-closure-s5-handoff.md) §8–§11；[P5 exit review](p5-exit-review.md) §6；
  - [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)、[ADR 0004](../adr/0004-raw-source-artifact-and-canonical-dolt-storage.md)、[ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)、[ADR 0019](../adr/0019-commit-canonical-metadata-authority.md)；
  - [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)、[Performance Measurement](../contracts/performance-measurement-and-baseline.md)、[Rust safety and performance policy](../policies/rust-safety-and-performance-policy.md)、[Proportional assurance policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)。

## 0. 开启判断（2026-10-24）

**可以启动 Phase 6 S0（决议、设计、执行计划），还不能开始实现。**

已具备：

- P5 整体 exit 通过（tag `p5-exit`），main 与 P5 tag 已推送；
- 已接受的业务容量目标（DC30：约 2× t4，Preview 10 分钟内）；
- 正确性已通过的生产路径实测显示差距（S5：t4 v1 Preview 1,685 s，线性外推 2× 规模约 3,370 s，是目标的 5.6 倍），满足 Performance Measurement §5 的优化进入条件；
- 正确性对照完整：全量测试、golden、真实数据 t1–t4；Rust/PyO3 构建已接入 backend 镜像（`vnext/backend/Dockerfile` 用 maturin 构建 `gateway-compute-python`）。

尚不具备：

1. 没有 Phase 6 设计与执行计划；本稿 r1 的事项均未决议。
2. [implementation-stages](implementation-stages.md) §9 的进入条件有两条需要改写：
   - “Slice 5B 产生 accepted vNext baseline”：该 baseline 状态机已被 Performance Measurement 3.0.0 废除；
   - “Phase 3 首批 Rust provider 已通过真实纵切验证”：目前唯一的 Rust consumer `canonical_row_hash` 不可达（P5 exit review §6.1），生产链路是纯 Python。Phase 6 是 Rust 首次进入生产链路。
3. 前置验证 V1、V3、V4 未做（§11）。
4. operation 级耗时归因不完整（§2.3）。

## 1. 背景与问题

DC31 规定：P5 只验证正确性，性能整体留给 Phase 6，Phase 6 可以按需重新设计、重写实现，约束是公共 Contract 与业务语义。DC30 给出的业务容量目标是“约 2× t4 的项目，Preview 10 分钟内完成”，DC31 把它定为 Phase 6 的退出目标。

讨论中确认了这个目标的两个问题：

1. **它比可达到的水平宽松得多。** owner 提供的信息：旧实现的 t4 Preview 约 60 s 返回前端，并且 Preview 阶段完全不访问 Dolt。S5 的基本操作吞吐（§2.2）也说明，主要开销在 Python 逐行处理，而不在 I/O、哈希或 Dolt 读取。
2. **固定门槛对各阶段不公平。** 有的阶段很快达标就退出，其实还有很大的优化空间；有的阶段受物理限制（例如 Dolt 写入），无论怎样优化都达不到。

因此目标按 DC35 的结构确定（§3）：业务目标与结构性条件为门槛，各阶段下界用于排序与判断何时停止优化；方法按业务阶段逐段设计（§8）。

## 2. 现状数据

### 2.1 operation 耗时（t4，operation terminal 墙钟秒）

| 阶段 | v1 Preview | 重传 v1 Preview | v2 Preview | v1 Submit | v2 Submit | History |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S3 | 2,656 | 2,335 | 2,339 | 801 | 811 | 1,375 |
| S5 | 1,685 | 1,464 | 1,478 | 566 | 574 | 893 |

来源：[S5 handoff](p5-arch-closure-s5-handoff.md) §9、§11。S2b 的同类记录（v1 Preview 2,567 s）只有 step 墙钟，口径不同，仅作历史参考。各档 S5 数值（墙钟秒）：

| 档 | 规范表/行 | v1 Preview | 重传 Preview | v2 Preview（变化表） | v1 Submit | History |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| t1 | 125 / 3,733 | 52 | 62 | 66（4） | 40 | 62 |
| t2 | 209 / 73,693 | 493 | 412 | 458（57） | 195 | 343 |
| t3 | 192 / 122,452 | 842 | 903 | 1,017（54） | 348 | 626 |
| t4 | 312 / 246,794 | 1,685 | 1,464 | 1,478（26） | 566 | 893 |

观察：

- **成本不随变化量增长。** 0 张表变化的重传、少量表变化的 v2，耗时都与全量 Preview 相当；t3 的重传与 v2 甚至高于 v1。
- **真实数据旅程只用 MODIFIED_ONLY。** `benchmarks/real_dump_journey.py` 的 Preview 请求为 `MODIFIED_ONLY`，每次只有一个上传侧、一个比较 pair（baseline→modified）。FULL 模式的双侧物化与双 pair 没有真实数据测量。

### 2.2 capability 分段与基本操作吞吐（t4，S5 DC32）

capability 分段（wall / 线程 CPU 秒；各段属于不同测量边界，**不能相加**替代 operation 墙钟）：

| 段 | wall | CPU |
| --- | ---: | ---: |
| SQL 解析 | 140.5 | 140.5 |
| business materialization | 211.5 | 211.5 |
| 规范投影与表摘要 | 219.0 | 218.9 |
| projected snapshot 写入 | 153.3 | 153.1 |
| v1 Preview pair 比较 | 148.4 | 148.3 |
| 风险评估 | 27.4 | 27.4 |
| RS 逐表 Arrow 读取（312 次） | 51.8 | RS 0.4 |
| Submit v1：snapshot build | 69.1 | — |
| Submit v1：plan child / replay child | 230.8 / 7.1 | — |

基本操作吞吐（同一台 ct108）：

| 操作 | 实测 |
| --- | --- |
| 包解压 | 5.6 MB → 80.3 MB，415 MiB/s |
| 现有 SQL 解析 | 79.4 MB，**0.54 MiB/s** |
| Arrow → Python | 36.5 MiB/s |
| Arrow IPC | 写 2,625 MiB/s；mmap 读 1,340 MiB/s |
| 哈希 | SHA-256 约 1,730 MiB/s；BLAKE3 约 5,200–5,600 MiB/s |
| 同一份 replay SQL 直接导入 Dolt | import 24.3 s，commit 0.13 s |

逐表分布：耗时高度集中在少数大表。按表跨所有 stage 聚合，最高为 `device_st` 762 s（50 次调用，最大 54,150 行），`device_mx` 213 s，`device_co` 74 s；单个 table-stage 最大为 `device_st` 的 artifact 写入 49 s。

### 2.3 现状结构与归因缺口

- **backend 计算路径没有任何并行。** 只有 worker runtime 的执行线程；Preview 的上传侧物化（`preview_jobs.py` 中按 side 的循环）、两个 pair（`_PAIR_BASELINE_TO_INITIAL`、`_PAIR_INITIAL_TO_MODIFIED`）、pair 内的比较→风险→surface 都是串行。worker 墙钟约等于 worker CPU；测试节点有 128 vCPU。
- **数据在 Python 中逐行、逐单元格处理。** SQL 解析器（`capabilities/table_access/`，约 2,600 行手写字节游标）为每个单元格构造 Python 字面量对象；物化、投影、比较也是逐行 Python。
- **归因缺口：** 上表各段分开测量，粗略合计约 900 s，只有 v1 Preview operation 1,685 s 的一半左右；剩余部分（步骤之间的 artifact 写入与读回、checkpoint、序列化，或测量边界本身的差异）没有归因。Step 记录带 `started_at` / `completed_at`，可以不加插桩先得到 step 级拆分（§11 V5）。
- **Submit 与下界的差距：** 同一份 replay SQL 直接导入 Dolt 约 24 s，现有 Submit 566 s；大头在 snapshot build 与 mutation planning（plan child 231 s），不在 Dolt 写入。现有 Submit 每次重写全部表，与变化量无关（§9 D10）。

真实数据的结构统计（G2 普查）：完全相同的重复行为 0；按规则键重复的行共 40,748 行，都是同键不同内容，已按 G8 用伪 gid 处理。

## 3. 目标的设定方法（已决议：DC35，2026-10-24）

决议全文见 [S0 owner 决议](p5-arch-closure-s0-owner-decisions.md) §18（DC35）。要点：

### 3.1 退出门槛的结构

| 层 | 内容 | 性质 |
| --- | --- | --- |
| 业务目标 | 目标规模、参考环境下各工作负载的绝对时间（§3.3） | **退出门槛** |
| 结构性条件 | 成本随变化量增长：未变化的表不读基线、不做比较；尽量用确定性计数断言证明（例如基线读取次数等于变化表数） | **退出门槛** |
| 分段下界分析 | 每段写出“语义最少工作 × 实测基本吞吐”，或原型提供的可达证据，与实测对比 | **报告，不设门槛**；用于排序和判断何时停止优化，相差约 5 倍以上须写明原因 |

r1 的“每个阶段达到下界的约定倍数以内”不再作为门槛：解析、比较等计算为主的阶段没有物理下界，其“下界”取决于实现本身；逐段设门槛的测量成本也与比例化保障政策不符。

### 3.2 两个时间指标

- **用户可见时间：** 从受理到 Preview 结果可读（READY）。
- **完成时间：** 包括 READY 之后的全部后台工作，例如 D3 的规范表文件写入。

两者都测量；门槛以用户可见时间为主，完成时间设硬上限。旧实现把 comparison cache 的补全放在返回之后的 `ASYNC_COMPARISON_CORE_CACHE_COMPLETION` 步骤里（`legacy/backend_vnext/flows/upload_preview.py`），它的“60 s 返回”很可能是用户可见时间。

### 3.3 工作负载与目标数值（草案）

| 负载 | 场景 | 用户可见时间（2× t4） |
| --- | --- | --- |
| W1 首次上传 | 空基线 | ≤ 3 min |
| W2 原样重传 | 0 张表变化 | ≤ 30 s |
| W3 少量变化 | 约 10% 的表变化，类似 v2 | ≤ 60 s |
| W4 最坏情况 | 已有完整基线，几乎所有表变化 | ≤ 3 min |
| 所有负载 | 完成时间 | ≤ 10 min（保留 DC30 原值作为硬上限） |

FULL 模式（双侧、双 pair）在 W3、W4 中各补测一次。数值在 V5、V6 完成后定稿，调整须经 owner 确认。

按 S5 的吞吐粗估：t4 的解压、哈希、Arrow IPC 读写合计在秒级；解析器达到每秒数十 MiB 时，2× t4 约 160 MB 的 SQL 解析只需数秒；现有全量基线读取 52 s（t4）是 W4 中最大的已知项，由规范表存储（D2、D3）降低。

### 3.4 参考环境与单任务资源上限

- 参考环境为 `ct108-gw-dms`（128 vCPU、96 GiB），不加容器配额；测量期间独占，不与全量门禁或其他测量并行。
- 程序自身设单任务（单个 operation）资源上限：固定并发数 N 与内存预算 M，部署配置，默认固定，不随 CPU 数自动放大（§5.5）。
- N 取加速曲线的拐点：各主要阶段完成后以 1、2、4、8、16、32 个线程测量，取并行效率约 60–70% 以上的最大值；单线程结果另行报告。目标数值在该 N 下判定。
- 每次取证记录墙钟、CPU 秒、峰值并行核数、峰值内存与临时磁盘高水位。墙钟决定用户等待，资源占用决定一台机器能同时处理几个项目。

### 3.5 项目级并发（交给 Phase 7）

以单任务资源上限为单位，多个独立项目按数量线性扩展是设计目标，由 Phase 7 的多项目扩展测量验证，不预设成立。容量规划：一台机器能同时处理的项目数 ≈ 机器资源 ÷ 单任务上限；排队时的用户等待 = 排队时间 + 单任务处理时间。Phase 7 的内容见 §4。

### 3.6 规模口径、验证数据集与统计

- 规模统一用源 SQL 字节数、规范行数、表数、最大单表行数四项描述（DC30 的“约 87 万行”是源 SQL 行数，S5 外推用的是规范行数）。
- 退出判定使用合成的 2× t4：复制 t4 的表并改名，同时扰动内容，避免去重收益虚高；W4 在已有基线上扰动全部表。按 t1–t4 拟合的规模函数只作交叉核对。合成规则写入测量 runbook，Git 中只出现表名与计数。
- 每个负载预热 1 次、测量 3 次，取中位数并报告范围；W1、W4 冷启动，W2、W3 允许命中上一次 Preview 的临时条目并写明；失败运行不计入；门槛只在取证运行中判定，普通 CI 不设计时阈值。

### 3.7 结构性目标

**成本应当随变化量增长，而不是随基线大小增长。** 内容不变的重传，成本应当接近“只解析和投影上传”；History 缓存命中时成本应当接近零。已作为退出门槛（§3.1）。

### 3.8 Submit 与 History 的目标（A2，owner 决定，r14，2026-10-25）

**现状（t4，S5 真实旅程）：**

- **History 893 s：** 旅程测的是 v1、v2 两个相邻节点、一个 pair。比较只占 39 s，大头是两个节点各自从 Dolt 全量读取，再在 Python 中物化（worker CPU 768 s）。RS 逐表读一个 t4 commit 约 52 s（312 次查询，RS 自身 CPU 0.4 s），基本是 Dolt 的耗时。D4 已确定 Dolt 中存的是投影后的规范表，读出后不需要重新投影。
- **Submit 566 s：** 准备阶段 374 s，RS 导入 79 s，另有约 100 s 未归因（V5）。原样重传的 Submit 判为无变化，只要 0.007 s。
- **还没计入的成本：** B9 补齐整表打包后，Preview 与 History 都多出整表 Parquet 导出，目标须把这部分计入。

**History：按缓存命中分三种负载，门槛为用户可见时间（2× t4）。**

| 负载 | 场景 | 门槛 | 路径与计数断言 |
| --- | --- | --- | --- |
| H1 相邻首查 | 上一 commit 与 head 两节点，规则集未变，Submit 后首次查询 | ≤ 60 s | 命中路径见下方；TTL 内 Dolt 读取次数与比较次数均为 0，TTL 外 Dolt 读取次数等于旧节点的变化表数 |
| H2 冷查询 | 两节点，派生缓存全部未命中（规则集激活后首查，或 TTL 过期） | ≤ 5 min（草案，V7 后定稿） | 两个节点的表都读 Dolt，变化表全部比较 |
| H3 重复查询 | TTL 内同一查询 | ≤ 15 s | Dolt 读取次数与比较次数均为 0，bundle 用导出缓存拼装 |
| 三节点 | H2 条件下补测一次 | 只报告 | 受 10 min 硬上限 |

- **H2 是最大的未知项：** 按现在每表约 0.17 s 的读取速度，2× t4 两节点冷读 Dolt 约 200 s，已超出 3 min；能降多少取决于 Dolt 能否并发读取，由 V7 实测。
- **与 B2 的关系：** 实际使用中若“查询较早 commit”（H2）很常见，按 B2 已登记的条件，重新评估“正式引用只保留 head”。

**Submit：门槛为完成时间（从受理到 Submission 提交成功、main 已前移；用户可见时间是受理，已是毫秒级）。**

| 负载 | 门槛（2× t4） | 依据 |
| --- | --- | --- |
| S1 首次 Submit（W1 之后） | ≤ 5 min | 全表新增，Dolt 导入下界约 50 s；靠 D10 的渲染直通 |
| S3 少量变化（W3 之后） | ≤ 2 min | D10 后 Dolt 写入约 4 s，其余主要是 RS 的固定开销 |
| S4 几乎全变（W4 之后） | ≤ 5 min | 与 S1 相近 |
| 所有 Submit | ≤ 10 min | DC30 硬上限 |

结构性门槛：
- D10 的计数断言：`replay.sql` 涉及的表数等于变化表数，行级语句数等于行级修改表的变化行数；
- S2（原样重传）不产生 Repository operation。

**测量安排：**
- **旅程：** 在 DC35 的合成 2× t4 旅程上接着跑，不另建数据。顺序为：W1 Preview 与 Submit（S1）→ W3 Preview 与 Submit（S3）→ H1 → H3 → 清空派生缓存后跑 H2 → W4 Submit（S4）→ 三节点 History。
- **清缓存的合法性：** 缓存是派生数据，清空不影响业务事实。
- **统计规则：** 与 DC35 相同。

**Submit 后首次 History 的命中路径（r14 补充）。** H1 的两个节点是父 commit P 与新 head H。三类缓存都在 Preview 与 Submit 的链路上形成，History 不需要额外准备：

| 缓存 | 何时形成 | H1 中是否命中 |
| --- | --- | --- |
| 表缓存（B2） | H 的表：Preview 同步写入上传侧规范表，Submit finalize 把正式引用移到新 head。P 的表：未变化的表与 H 共用同一文件；变化的表在 head 前移时释放正式引用，按 TTL 保留（TTL 从最后一次引用起算，D2/D3 设计要点 7） | TTL 内两侧全部命中，不读 Dolt；TTL 过期后只有 P 的变化表读 Dolt 并回填 |
| diff/risk 缓存（B3） | Preview 计算“基线 head → 上传”时形成；Submit finalize 在移动 head 的同一事务中给这些条目登记引用、重新起算 TTL，不做计算（§9 D5 第 ③ 层） | 键与 History 的“P → H”相同，全部命中 |
| 导出缓存（B9） | Preview 的 bundle 导出上传侧全部表；P 的表在上一次 Preview 中作为上传侧导出过 | H 侧命中；P 的变化表在 TTL 内命中，否则重新导出 |

TTL 内的 H1 因此不读 Dolt、不做比较，只做 pair 级 surface 汇总与 bundle 拼装；60 s 的门槛覆盖 TTL 外的兜底路径。不命中的情况：

- **FULL 模式的 Preview：** Preview 的两个 pair 是“基线 → 初始”与“初始 → 修改”，没有直接计算“基线 → 修改”，而 Submit 提交的是修改侧。H1 的 diff/risk 缓存因此不命中，要对变化表重算；表缓存与导出缓存仍命中。**owner 决定（2026-10-25）：** 接受（D7 之后只算变化表，代价小），不在 Preview 中多算一个 pair。
- **规则集在 Preview 与 History 之间激活：** 键全部变化，按 H2 处理，这是正确行为。
- **Preview 与 Submit 的间隔超过 TTL：** diff/risk 条目可能已被清理，finalize 无条目可登记，首次 History 对变化表重算。

## 4. Phase 6 与 Phase 7 的边界（建议）

| 阶段 | 原定内容 | 建议调整 |
| --- | --- | --- |
| Phase 6 | 扩大 Rust 覆盖、优化计算与数据路径 | **单个 operation 的延迟**，以 §3 的阶段目标为退出条件。手段不限，包括 operation 内部的表级与数据级并行（从 Phase 7 前移，§5），以及同一项目内按内容摘要的确定性复用 |
| Phase 7 | 并行、缓存、并发预算、背压 | **多个 operation 的吞吐与资源（项目级并发，DC35 第 6 项）**：同时执行的槽位上限 K（K × 单任务上限 ≤ 机器资源）、项目之间的公平调度、对用户可见的排队状态、多项目扩展测量（1、2、4、K 个独立项目）；多 worker（需要重新设计启动时的租约判定，S2b 复审 R1-O2）；共享瓶颈（Repository Service 与 Dolt、control DB、磁盘与内存带宽）；跨 operation 的通用缓存治理（淘汰、晋升、权威性校验）；统一并发预算、背压 |

把 operation 内并行前移的理由：worker 是单核，并行是数量级提升的直接手段之一。Phase 6 只须保证单任务资源可控、可度量，单任务失败（例如内存不足）不影响其他任务。implementation-stages §9 的进入条件同时改写（§0 第 2 项）。

## 5. Rust 的目标与优化分层

### 5.1 目标

owner 方向（2026-10-24）：使用 Rust 的**首要目标是突破 Python 的并发瓶颈**（GIL 使 CPU 密集的 Python 代码无法在线程间并行），但不是唯一目标；Rust 的其他效率优势同样计入。

Rust 带来的收益分两类，两者相乘：

| 类别 | 内容 | 现状数据中的体现 |
| --- | --- | --- |
| 并发 | 不受 GIL 限制的线程级并行（Rayon），共享内存、零拷贝 | worker 单核满载，96 核主机空闲 |
| 单核效率 | 不为每个单元格构造 Python 对象；紧凑的列式内存布局；字节级扫描（memchr/SIMD）；无解释器开销 | SQL 解析 0.54 MiB/s，对比解压 415 MiB/s、BLAKE3 约 5 GiB/s；Arrow→Python 36.5 MiB/s |

就现有数据看，单核效率很可能是更大的一项（例如解析器），并发在其上再乘一个系数。并发的上限受两点约束，需要在设计中正面处理：

- **最大的单元决定关键路径。** 表级并行的墙钟下界是最大一张表的耗时（t4 中 `device_st` 明显偏大）；只做表级并行，收益会被大表截断，需要表内数据级并行（§5.2 L3）或先降低单表成本。
- **串行部分（Amdahl）。** checkpoint、artifact 发布、汇总排序等仍是串行；并行前要先知道它们的占比（§11 V5）。

### 5.2 并发分层（参考选项，不代表优先级）

owner 提出的几类并发作为参考选项列入；是否值得做、先后顺序，以 V5/V6/V1 的实测与成本模型决定。

| 层 | 内容 | 适用范围与收益上限 | 前提与注意 | 初步评估 |
| --- | --- | --- | --- | --- |
| L0 operation 间 | 多个 operation 同时执行 | 吞吐，不改善单个 operation 延迟 | 多 worker 需先重开启动租约判定（S2b R1-O2）、统一并发预算 | 留在 Phase 7 |
| L1a 双侧物化 | FULL 模式下 INITIAL 与 MODIFIED 两个上传包的解析、物化、投影并行 | 只在 FULL 模式；上限约 2× | 两侧完全独立；诊断汇总已按 side 合并（EXIT-F1） | 值得补充，成本低；但对 MODIFIED_ONLY 无收益 |
| L1b 双 pair 比较 | FULL 模式下 baseline→initial 与 initial→modified 两个 pair 并行 | 只在 FULL 模式；上限约 2×，受较慢的 pair 限制 | 物化完成后两个 pair 互相独立；bundle 汇总按固定顺序 | 值得补充，成本低；同上 |
| L1c 流水线重叠 | 基线读取（RS I/O）与上传侧解析（CPU）重叠；异步写入移出关键路径（D3） | 基线读取现为 52 s，可隐藏在解析之后 | 不改变结果；取消与失败需要统一收敛 | 值得补充 |
| L2 表级 | 解析、物化、投影与摘要、比较、风险 facts 按表并行 | 收益随核数增长，受最大表限制 | 结果按规范表顺序合并，并行与串行摘要相同；调度见 D6 | **主线**，适用于所有模式 |
| L3 表内数据级 | 大表按行块并行：分块解析扩展 INSERT、分块编码与哈希、并行排序与归并连接 | 突破“最大表决定关键路径” | 摘要须与分块方式无关（D1 的顺序无关定义已满足）；分块边界扫描须识别引号与转义 | 对大表必要；Rust/Rayon 天然适合 |
| L4 单核效率 | 列式数据、零拷贝、字节级扫描、去掉逐单元格对象 | 往往是数量级 | 与 L2/L3 叠加 | 与并发同等重要（§5.1） |

### 5.3 并发以外的优化点

| 优化点 | 内容 | 与现状数据的关系 |
| --- | --- | --- |
| 按变化量计算（结构性） | 用表摘要与基线 manifest 比对，只对变化表做基线读取与比较 | 重传与低变化 v2 耗时接近全量（§2.1） |
| 减少物化次数与格式转换 | 现链路：SQL → 单元格对象 → business snapshot → 投影 → artifact 写入 → 读回比较；改为一次产出规范 Arrow 表并沿用到比较 | materialization 212 s、snapshot 写入 153 s |
| 比较结果复用（History） | 以“前表摘要、后表摘要、规则主体 digest”为键缓存（D5 第 ③ 层） | History 893 s，重复查询应接近零 |
| Submit 只写变化 | 已定（D10）：表级跳过未变化表；变化表按阈值行级修改或整表重建；从冻结的规范表直接渲染 SQL。复用 Preview 冻结的规范表与 manifest，不复用 Preview 的比较结果 | Submit 566 s，对比 Dolt 直接导入 24 s |
| 降低 RS 读取成本 | 基线优先从规范表存储读取（D2/D3），Dolt 兜底 | RS 读取 52 s |

### 5.4 模块拆解（待讨论的初步划分）

原则沿用 implementation-stages §9 与 ADR 0001：Rust 承担数据密集计算，接口为 Arrow 进、Arrow 出的粗粒度调用；Python 保留 domain、application、Operation Runtime、ruleset 选择与业务 policy；不按 Python 文件逐一翻译。

| 模块 | 候选的 Rust 范围 | Python 保留 | 备注 |
| --- | --- | --- | --- |
| SQL 与 XML 解析（`table_access`） | 流式扫描、语句与值解析、按表与按块并行、直接产出列式数据 | 请求与预算的组装、诊断的映射 | 主线并提前（§6） |
| business materialization（`snapshot_materialization`） | 与解析合并为“解析即列式物化” | 业务快照的组装规则 | 范围是否与解析一并做，待决议（§13 C2） |
| 规范投影与表摘要（`storage_projection`） | 列式投影、排序检查、BLAKE3 摘要 | 规则解析、诊断与上限 | 依赖 D1 |
| 比较（`comparison`） | standard 哈希连接、keyless 多重集合、ordered 序列算法 | 比较模式选择、结果 Contract | 以 V1 决定 ordered 是否进 Rust |
| 风险 facts（`risk_evaluation`） | 大规模 facts 提取 | 规则定义与决策 | 现 27 s，优先级低 |
| mutation planning（Submit） | 存储 diff（与比较共用列式内核）、replay SQL 渲染 | 表级决定（跳过、重建、行级）、CAS 与发布语义 | 见 D10 |
| 调度 | Rayon 工作池、LPT 派发 | 调度配置与并发上限 | 见 D6 与 §5.5 |

### 5.5 并发上限：固定配置的收益与风险

owner 倾向：并发上限用固定配置，仍可讨论。

| | 内容 |
| --- | --- |
| 收益 | 测量可重复、结果可比；与同机门禁和其他服务共存时不抢占；容器内 `os.cpu_count()` 返回分配给容器的全部 vCPU（ct108 为 128），不反映程序应占用的份额，自动探测容易超额订阅；峰值内存可预估（并发数 × 单表峰值） |
| 风险 | 换到更大的机器不会自动用满；嵌套并行（Python 多进程内再开 Rayon、Polars 自带线程池）会叠加超额订阅；大表与小表混合时固定数量可能偏保守 |
| 建议 | 每个 worker 一个显式并发上限（部署配置，默认固定值，不随 CPU 数自动放大）；所有原生线程池（Rayon 全局池、Polars 等）由同一配置统一设定，禁止库自行探测；同时给出单个 operation 的内存预算；Phase 7 的全局并发预算再统一收敛 |

## 6. SQL 解析器：主线并提前

### 6.1 方向

owner 方向（2026-10-24）：**SQL 解析器作为 Phase 6 的主线并提前做。**

理由：解析为 0.54 MiB/s，是基本操作中最慢的一项；解析与物化合计约 350 s，是 t4 Preview 中最大的开销之一；它在每次 Preview 与 Submit 重投影中都必须全量执行，不能靠按变化量计算省掉。这与 implementation-stages §9“最后单独评估 SQL streaming parser”的排序冲突，需要同步修订。

解析器同时决定真实数据的格式保真（G2 的教训），因此差分验证是它的核心交付物，而不是附属测试。

### 6.2 目标设计（待讨论）

- **两阶段：** 先用字节级扫描（memchr/SIMD）找出语句边界与表边界，识别引号、转义和注释；再按表并行解析（L2），对超大扩展 INSERT 按值元组边界分块并行（L3）。
- **直接产出列式数据：** 按 DDL 声明类型（`sql_declared_types.py`）产出 Arrow 列，不经逐单元格 Python 对象。
- **语义与现有解析器逐项对齐：** 转义序列、字符集与多字节字符、`_binary` 与十六进制/位字面量、NULL、负零与指数浮点、大精度 DECIMAL、零日期、条件注释 `/*!40101 ... */`、`LOCK TABLES` 等样板语句、CRLF。
- **预算与诊断：** 现有 `ParserRuntime` 的上限与 `TableAccessError` 诊断（错误码、表与语句位置）属于行为的一部分，必须保留。
- **Python 解析器保留为参照实现**（ADR 0001），通过 feature flag 可退回；Phase 6 退出后降为小数据 oracle。
- **Rust 安全：** 不使用 `unsafe`（如需使用，按 Rust safety policy 单独评审）；panic 在 FFI 边界转为确定的失败；解析器单独做 coverage-guided fuzz（cargo-fuzz），只验证不崩溃、不超预算。

### 6.3 差分验证建议

**对照点分两层：**

1. **解析输出逐值对照（主判据）。** 定义“解析结果规范形”：每张表的描述（表名、列、声明类型、主键）、行数，以及按列的类型化值（类型标记加字节表示）与行顺序。参照实现的输出经一个仅用于测试的转换器变成同一规范形，与 Rust 输出逐列比较；不一致时报告第一个差异的表、列、行号与两侧值的类型标记（真实数据只输出位置与类型，不输出值）。
2. **下游摘要对照（端到端）。** 同一输入经两种解析器后，business snapshot digest、规范表摘要、manifest digest 必须相同。

**判定标准：** 类型化值完全相等，没有容差。错误路径要求诊断码相同、表与语句位置相同；错误消息文本是否要求相同，待决议（建议不要求）。

**语料分五层：**

| 层 | 内容 | 运行位置 |
| --- | --- | --- |
| ① 现有测试改为双实现参数化 | 现有解析器单元测试与 golden 对两种实现各跑一遍；每个现有用例自动成为差分用例 | 普通 CI |
| ② 语法感知的随机生成 | Hypothesis 按 mysqldump 结构生成语句与边界字面量（§6.2 所列各类），比较两实现的输出与错误 | 普通 CI（有限样本）+ 定期加大样本 |
| ③ 负例与预算 | 截断语句、引号不配对、超长值、超出预算的输入；两实现须以相同诊断失败 | 普通 CI |
| ④ 真实数据 t1–t4（v1、v2） | 在 ct108 全量解析，逐表逐列对照与下游摘要对照；只输出计数、表名与摘要（DC22、真实数据不入 Git） | 每次取证运行一次（DC30） |
| ⑤ 普查覆盖的格式类别 | G2 普查统计到的格式类别各取合成样本，确保真实数据里出现过的形态都有用例 | 普通 CI |

**并行确定性：** Rust 解析器分别以 1 个线程和 N 个线程运行，输出必须逐字节相同；分块大小取不同值，输出也必须相同。

**性能断言：** 不在 CI 中设时间阈值（Performance Measurement §7）；吞吐在取证运行中记录。

### 6.4 解析器主线的阶段建议

1. **V6 原型：** 只实现扫描与 INSERT 值解析，在 t4 上测单线程与多线程吞吐，并跑语料 ①④ 的子集，确认可行性与下界。
2. **完整实现：** 补齐 DDL、样板语句、预算与诊断；五层语料全部通过。
3. **接入：** 解析器输出直接进入列式物化；Python 路径保留在 feature flag 之后。
4. **取证：** 真实数据 t1–t4 端到端摘要一致，记录吞吐与 Preview 墙钟变化。

## 7. 主线：规范表是唯一流转的数据形态

```text
上传 → 流式解析 → 一次投影 → 规范 Arrow 表 → 表摘要（BLAKE3，与行顺序无关）
     → 规范表存储（Arrow IPC，按摘要寻址；Preview 只挂临时引用）
Preview：上传侧摘要与基线 manifest 比对 → 只对变化表从存储 mmap 读取
         （缺失时由 Dolt 兜底并回填）→ 按调度分组做列式比较
Submit：未变化表跳过，变化表按阈值行级修改或整表重建，写入 Dolt（权威）；commit 成功后，相关表加正式引用
History：manifest 过滤 + 比较结果缓存 + 规范表存储
```

Dolt 始终是权威来源，规范表存储和各类缓存都是派生数据：缺失或损坏只影响性能，不改变业务事实。

## 8. 分阶段的方法

| # | 阶段 | 语义最少工作 | 主要方法 | 下界的来源 |
| --- | --- | --- | --- | --- |
| ① | 上传与 staging | 接收、限额检查、解包 | 流式解包，不重复落盘 | I/O 吞吐（解压 415 MiB/s） |
| ② | 解析与物化 | 全量解析 SQL 与 `logics.xml` | 新解析器（§6）：扫描后按表与按块并行，直接产出列式数据 | 新解析器的实测吞吐（V6） |
| ③ | 规范投影与表摘要 | 全量（上传侧） | 列式投影；BLAKE3 表摘要（D1）；按表并行（D6） | 哈希与排序的实测吞吐 |
| ④ | 基线解析 | 只取变化表 | 用基线 commit 的 manifest 中的表摘要过滤；变化表优先从规范表存储读取（D2、D3），缺失时由 Dolt 兜底；与 ② 重叠执行（L1c） | 与变化表的数量成正比 |
| ⑤ | 比较、风险与 surface | 只处理变化表 | 列式比较（D7）；计算去重（D5）；按调度分组并行（D6）；FULL 模式双 pair 并行（L1b） | 与变化行数成正比 |
| ⑥ | 发布 Preview | 写入用户需要的结果 | 只同步写入小的权威事实，大文件异步写入（D3） | 小 |
| ⑦ | Submit 受理 | 比对摘要 | 现状已经很便宜 | 毫秒级 |
| ⑧ | Submit 准备与回放 | 只写变化 | 表级跳过、按阈值行级修改、渲染直通（D10）；keyless 表按 DC29 整表重写；同内容表组的写入优化不做（D8） | **受 Dolt 写入限制**：同样数据直接导入 Dolt 实测 24 s |
| ⑨ | History 比较 | 只处理变化表 | manifest 过滤 + 比较结果缓存 + 规范表存储 | 缓存命中时接近零 |

第 ⑧ 步最可能受物理限制，因为 Dolt 的写入和提交不受我们控制。它单独定目标，不和 Preview 共用一个门槛。按 owner 的判断，Submit 是用户可以离开的异步过程，对耗时不敏感；但 S5 显示现有 Submit 的大头不在 Dolt 写入（§2.3）。

## 9. 设计决定（讨论结论，待决议）

### D1 只保留一个表摘要，它就是权威摘要

- 不设快速哈希和权威哈希两层。摘要只有一个，同时用作 manifest 内容摘要、`NO_CANONICAL_CHANGE` 的输入，以及规范表存储的内容地址。
- **哈希函数用 BLAKE3：** 它是密码学哈希，单核可达 GB/s 级（S5 实测约 5 GiB/s）。摘要同时是缓存的内容地址，一旦碰撞，会读到错误的缓存、静默得出错误结果，所以不采用非密码学哈希。
- **编码改为列式二进制，不再逐行做 JCS 编码。** 现在慢主要慢在编码和逐行处理，而不是哈希函数本身。
- **与行顺序无关：** 按规范键排序后计算，但先检查是否已经有序，有序就不排。常见情况下 dump 顺序就是主键顺序，检查是 O(n)。keyless 表按行摘要排序，计算多重集合摘要，保留重复行（DC29）。顺序无关也使表内分块并行（L3）不影响摘要。
- **不按源顺序计算的理由：**
  - 省下的时间很少；
  - Dolt 按主键顺序返回数据，摘要与顺序无关，才能从 Dolt 读回后重算出同一个摘要，用来回填或校验缓存；
  - 摘要在 Preview 时算出，PreviewResult 的规范状态摘要、`NO_CANONICAL_CHANGE` 与陈旧判定的语义（设计 §5.3、ADR 0019）都不用变。
- **Contract 影响：** 修订 Canonical Storage 中内容摘要与行编码的定义，storage projection version 提升，golden 重建。按 DC6，直接改到目标形态。
- **顺序（r2 补充）：** Performance Measurement §5 要求优化前后业务摘要不变，而 D1 本身改变摘要。建议把 D1 作为 Phase 6 中单独的 Contract 变更阶段，完成后重新测一次作为后续优化的对照基准（§13 B1）。

#### D1 审核分析（r4，2026-10-24）

**现状：每张表实际有四个摘要，定义与 consumer 各不相同。**

| 摘要 | 位置 | 定义 | consumer |
| --- | --- | --- | --- |
| manifest `content_digest` | `storage_projection/_digest.py`、`project.py` | SHA-256；keyed 表按读取顺序（即源顺序）逐单元格计算；keyless 先排序；ordered 按 gid 排序且不含结构列，另有 `ordering_digest` | manifest digest → Submission 记录、import 包绑定、PreviewResult、checkpoint 校验、Submit 重投影核对（`import_publication.py`）、mutation planning |
| `raw_content_digest` | `snapshot_materialization/_digest.py` | 每行一个 domain-separated SHA-256（列名排序后编码），再按多重集合排序合并；**已经与行顺序无关** | 规范状态摘要（DC13、ADR 0019），即 `NO_CANONICAL_CHANGE` 与陈旧判定；比较提前退出（`comparison/row_encoding.py`）；snapshot digest → 比较请求与 bundle digest；HTTP `canonical_business_digest`；Dolt 读回时重算（`repository_ref.py`） |
| `fast_row_digest` | 同上 | 另一种逐行 SHA-256 | 只作诊断，但计入 snapshot digest 与 raw state digest |
| Rust `canonical_row_hash` | `capabilities/canonical_row_hash` | 在 Arrow 上计算 Shared Kernel 行哈希，有 vector 一致性测试 | 生产中不可达（P5 exit review §6.1） |

另外两点：

- **重复计算。** 投影时每个保留单元格要编码 3–4 次：内容摘要一遍；ordered 表再算一遍自校验，keyless 表的多重集合摘要也算两遍；之后 reopen reader，再算 `row_content_hash` 与 `fast_row_hash`。重算的是同一份内存数据，并不证明什么。
- **哈希本身不是瓶颈。** 按 t4 源 SQL 79 MB 估算，SHA-256（约 1.7 GiB/s）每遍不到 0.1 s。“规范投影与表摘要 219 s”几乎全部花在 Python 逐单元格编码和多次遍历上（待 V5 确认）。换成 BLAKE3 省下的不到 1 秒。
- **现有 manifest 摘要不能用于“只读变化表”。** keyed 表的 manifest `content_digest` 依赖源顺序，与 Dolt 读回顺序不同，读回后无法重算出同一个值；`CommitCanonicalMetadataPort` 目前也只返回存储身份，不返回每表摘要。

**按 r2 原方案（BLAKE3、列式编码、按键排序）的影响面：**

- **Shared Kernel 的线上类型：** `DigestRef` 只接受 `sha256:` 前缀。改用 BLAKE3 要么改这个类型，进而影响 HTTP DTO、源码中的 6 处正则校验和 `real_dump_journey`；要么给摘要贴错算法标签，后者不可接受。
- **Contract：**
  - Shared Canonical Encoding：ROW、RAW_CONTENT 两类摘要和 digest vectors；
  - Snapshot Materialization：`DIGEST_CONTRACT_VERSION`、snapshot digest；
  - Canonical Storage §4：推翻“producer 不得自行排序”，storage projection version 从 2 升到 3；
  - ADR 0019/DC13：规范状态摘要的组成项变了；
  - Canonical Row Hash Compute Boundary：要重写或删除；
  - Comparison 与 bundle：snapshot digest 变化会传到 bundle、PreviewResult 和 surface；
  - Performance Measurement §5。
- **对照基准：**
  - 17 个 golden 目录（mutation 7、snapshot-materialization 5、storage-projection 3、canonical-row-hash 1、schema 1）；
  - shared-kernel digest vectors 和 Rust vector conformance；
  - 写死摘要的测试；
  - checkpoint 载荷：按 DC6 不做兼容，删除本地 control DB；
  - **P5 记录的 t1–t4 真实数据摘要全部失效**，要重新跑一次建立基准。
- **键依赖：** 按键排序后再哈希，摘要就依赖键的定义。DC29 下的 keyless↔keyed 切换，即使行完全相同，摘要也会变。多重集合方案没有这个问题。

**与解析器主线及 C2 的关系：**

- 解析器差分的主判据（§6.3 第 1 层）是解析输出逐值对照，与摘要定义无关。下游摘要对照（第 2 层）是相对比较，两边用同一套下游代码，用哪种摘要都成立；但摘要定义不能在主线进行中途改变。
- 只有摘要值不变，真实数据 t1–t4 才能直接和 P5 的已知值比，成为最强的绝对 oracle。
- `parser_version` 进入 snapshot digest。Rust 解析器必须沿用同一个值，把它定义为语义版本，而不是实现标识。
- 如果解析器与物化合并（C2），Rust 路径要自己算 `raw_content_digest` 与 snapshot digest，摘要定义必须在 C2 实现之前定稿。r2 的 §13 D3 顺序“解析器主线 → D1 摘要阶段”与此冲突：会先用 Rust 实现旧编码，再丢掉重写。

**审核方建议：B1 改为“保值统一”。**

1. 以现有 `raw_content_digest` 作为唯一的表摘要。它已与行顺序无关，Dolt 读回也能重算出同一个值。
2. manifest 的 `content_digest` 改为同一个值，storage projection version 升到 3。ordered 表的统一口径（现 manifest 摘要不含结构列，`raw_content_digest` 包含全部规范列，含伪 gid）与 `ordering_digest` 是否保留，在设计中定。
3. 去掉重复计算；`fast_row_digest` 是否一并删除，单独决定（删除会改变 snapshot digest）。
4. `CommitCanonicalMetadataPort` 返回每表摘要。这是“只读变化表”这一结构性门槛（DC35 第 1 项）的前提。
5. 实现复用现有的 Rust `canonical_row_hash` 内核，让 Rust 先以一个小而好验证的步骤进入生产链路。

这样，规范状态摘要、snapshot 与 bundle digest、HTTP DTO 和真实数据的规范状态摘要基准都不变；变化的只有 manifest digest（随之体现在 PreviewResult、Submission 记录与 checkpoint 中的值），golden 只改 storage-projection 与 mutation 两组；Performance Measurement §5 的“业务摘要不变”自然满足。

- **BLAKE3：** 降为备选，只在 Rust 化之后哈希实测占该段比例明显时再考虑，并且只用于新的、带算法标签的内容摘要类型。
- **阶段位置：** 单独成一个小的 Contract 阶段，放在 S0 与 V5 之后、解析器主线之前；D9（只增列的 schema 变化）若同期决议，并入同一阶段，对照基准只重建一次。
- **若 owner 仍选 r2 原方案：** B1 要排在 V6 与解析器完整实现之后、“接入”与 C2 之前；Python 参照实现也要实现新编码；还要单独为 t1–t4 重建一次基准。

### D2 规范表文件用不压缩的 Arrow IPC，内存映射读取

- 每张规范表一个 Arrow IPC 文件，以 D1 的摘要命名；先写临时文件，再原子 rename。
- **零拷贝读取：** Python 用 `pyarrow.memory_map` 加 `pyarrow.ipc.open_file`，或 Polars 的 `read_ipc(memory_map=True)`；Rust 用 arrow-rs 的 IPC reader 配合 mmap 构造 `Buffer`。
- **零拷贝的条件：**
  - 不使用缓冲区压缩；
  - 文件的 schema 就是规范 schema，Canonical Storage 的类型词表与 Arrow 类型有固定映射；
  - **比较程序直接处理 Arrow 数组。** 如果仍然转成 Python 对象，格式上的收益会全部抵消，所以 D2 以 D7 为前提。
- 旧实现用 Parquet（`shared/snapshot-tables/{side}/{digest}.parquet`），读取时需要解码；本决定在这一点上改进。
- RS 本身就用 Arrow IPC 流传输，Dolt 兜底读取的结果可以直接写成缓存文件。

### D3 规范表存储：一个按内容寻址的存储，两类引用；Preview 只同步写入小事实

- **只有一个存储，条目带两类引用：**
  - **临时引用：** 来自某个 Preview，有 TTL；被新的 Preview 取代时撤销；
  - **正式引用：** 来自某个 Repository commit，在 Submit 的 Repository commit 成功、finalize 时加上，不在受理时加。
- **晋升只是加一条正式引用，** 不复制、不移动文件。没有任何引用的条目，由协作式清理回收（ADR 0012）。重新上传只撤销旧 Preview 的引用，删除由后台完成，不放在上传路径上。
- **用户改一点再重传时，** 没变的表摘要相同，临时条目可以直接命中。
- **（r7 已取代：改为同步写入，见下方 D2/D3 审核分析）Preview 同步只写小的权威事实：** 每表摘要、两侧的规范状态摘要、manifest，以及展示需要的 surface 和变化表的记录。规范表文件在返回之后异步写入，并且有上限（例如固定 1～2 个线程）。旧实现用 `max_cache_workers=2` 的线程池做同样的事。
- **（r7 已取代：T1 冻结对象不变，prepare 读冻结产物）Submit 的 prepare：** 优先使用已经写好、并且摘要校验通过的文件；如果文件还没写完（很快就提交了），或者已经被清理（间隔很久才提交），就从 SourcePackage 重新投影，再用 PreviewResult 中的摘要校验。这样，Preview 与 Submit 不连续的情况也能正确处理，异步写入失败只影响性能。
- **Preview 读基线时由 Dolt 兜底得到的表，** 是已经提交的内容，可以直接挂正式引用。
- **Contract 影响：** 修订 ADR 0019 与设计 §4.6 中“PreviewResult 持久化规范表集合闭包 artifact”的条款，以及 T1 冻结的对象：从“闭包 artifact”改为“摘要 + SourcePackage”。
- **比例化保障（r2 补充）：** 这是新增的持久化派生状态。按 Proportional assurance policy，需写明它对应的业务需求（容量目标）、丢失或损坏只影响性能的证明方式，以及不新增独立的状态机或证据机制。

#### D2/D3 审核分析与 owner 决定（r7，2026-10-24）

**owner 决定（2026-10-24）：** 规范表文件在 Preview 中**同步写入**；正式引用**只保留当前 BaselineHead**；文件**先不压缩**。D3 中“规范表文件在返回之后异步写入”与“Submit prepare 在文件缺失时重新投影、T1 冻结对象改为摘要加 SourcePackage”两条，由本节取代。

**现状（代码核对）：**

- **表文件：** 每张表写成 zstd 压缩的 Parquet 加一个 JCS manifest，ID 随机生成（`sta-rows-…`），写完立即读回校验一遍（`snapshot_materialization/artifact.py`）。上传侧写两份完整副本：业务物化时一份原始表，规范投影后一份规范表。
- **读取：** `LocalArtifactStore.locate` 把整个文件读成 bytes，再做一次 SHA-256 校验，与 mmap 零拷贝不兼容。
- **保护：** `artifact_protection_intents` 以“artifact、owner 类型、owner ID”为主键，一个文件可以有多个 owner。现有 owner 类型包括 current-preview、preview-operation、submit-attempt、canonicalization-manifest 等 10 种；T1 时把保护转给 Attempt。没有任何保护的文件，超过 24 小时（`DEFAULT_UNPINNED_TTL`）由协作式清理回收（ADR 0012）。
- **耗时：** S5 的“projected snapshot 写入 153 s”。按 IPC 写入 2.6 GiB/s 换算，t4 的数据量写盘不到 1 秒，所以这 153 s 主要花在 Python 编码、zstd 压缩与写后回读上，不在 I/O。

**设计要点：**

1. **两类引用直接用现有保护表实现，不新增状态机。**
   - 临时引用就是现有的 preview owner，T1 转移规则不变。
   - 正式引用新增一种 owner 类型，**绑定到项目当前的 BaselineHead**。head 前进时（Submit finalize），在同一个 control DB 事务里把引用移到新 head；内容没变的表摘要相同，文件不动。
   - 更早 commit 的表，History 需要时由 Dolt 兜底读取，按 TTL 回填，不挂正式引用。
   - 这样磁盘占用有上界：每个项目一份 head，加上 Preview 的 TTL 副本。按 commit 挂正式引用，会随提交历史无限增长。
2. **同步写入。** 直接从 Arrow 写 IPC、去掉写后回读之后，写入预计只要秒级。T1 照旧冻结 MODIFIED 侧的规范表集合闭包与 manifest，Submit prepare 照旧读冻结产物，不重新投影；ADR 0019 与设计 §4.6 的结构不变，只是闭包条目改为指向按内容寻址的 IPC 文件。异步写入降为备选：只有实测写入在关键路径上占比明显时才启用，启用时须重新评估 T1 冻结对象。
3. **内容地址的组成：** storage projection version、business schema digest、行数、表摘要（B1）、Arrow 映射版本；不含表名，D5 的去重才能命中。
4. **文件内的行按规范顺序存放：** keyed 表按键排序，ordered 表按 gid 排序，keyless 表按行哈希排序。同一地址的文件字节因此一致，写入是幂等的；Dolt 按主键顺序返回，读回后可直接写成同一个文件。
5. **读取时校验，不通过就回退到 Dolt。** “缺失或损坏只影响性能”成立的前提是损坏能被发现，否则损坏的缓存会直接进入比较结果。保留文件的 raw SHA-256，在 mmap 上计算（t4 规模零点几秒，不拷贝数据）；不符时按缺失处理，从 Dolt 读取并重写。
6. **不压缩（owner 决定）：** 不压缩的 IPC 才能零拷贝。设计中给出磁盘需求估算（每个项目的 head 体积加 Preview TTL 副本），并查明参考节点的磁盘容量；超出预算时再评估 LZ4。
7. **清理的两处配合（ADR 0012 范围内）：**
   - 复用已有文件时，TTL 从最后一次引用开始计时，不从发布时间算；否则旧文件一释放保护就立即可删。
   - 复用文件时先登记保护，再确认文件存在，避免与清理任务竞争。
8. **上传侧原始表可能不再需要持久化。** 比较只用规范表，原始表可以从 SourcePackage 重算。checkpoint 恢复之外是否还有使用方，待设计时核实；如果没有，少写一整份。
9. **写后回读校验删除。** 写入路径用临时文件加原子 rename，读取时有第 5 条的校验，写后立即回读不再提供额外证明。

**依赖与顺序：**

- 地址使用 B1 的表摘要，B1 先完成。
- mmap 零拷贝的收益以 D7 为前提：比较若仍转成 Python 对象（36.5 MiB/s），格式收益会被抵消。格式切换（Parquet → IPC + mmap）与 D7 一起做，或在 C2 时由解析器直接产出 Arrow 并写 IPC。
- “只读变化表”的结构性门槛靠 B1 的 commit 每表摘要实现，不依赖 B2；B2 降低的是变化表的读取成本（现全量读基线 52 s），对 W4 最有用。

**比例化保障：** 本设计没有新增独立状态机、证据机制或 helper，只多一种 owner 类型和一条 head 转移规则；丢失或损坏由读取校验加 Dolt 兜底处理，只影响性能。对应的业务需求是 DC35 的容量目标。

### D4 Dolt 中存放投影后的规范表（现行设计，确认）

- ADR 0004 与 Canonical Storage §1–§2 已经规定：Dolt commit 保存规范业务状态，不保证还原原始 SQL schema、物理列或 DDL；`DROP_FROM_STORAGE` 的列在写入前删除；键按规则确定；原始数据只保存在 SourcePackageArtifact 中。
- 读取 Dolt 时不再做投影。剩下的开销在 RS 的查询与序列化，以及 backend 的 Arrow → Python 转换；D2、D3、D7 正是要绕开这两段。
- ruleset 改变存储规则以后，Dolt 中的已有数据仍按旧规则存放，比较按运行期规则对齐（DC10、Canonical Storage §7）。这一点不变。

### D5 计算去重：分三层，用不含表名的规则主体 digest

- **三层：**

  | 层 | 内容 | 性质 |
  | --- | --- | --- |
  | ① 表身份事实 | 每个快照、每张表的摘要，存在 manifest 中 | 权威事实 |
  | ② 业务分组事实 | 由 ① 按明确的分组规则推导：哪些表内容相同；业务上如有“预期应该相同”的表族，再加 ruleset 中的声明 | 业务语义，单独定义、单独测试 |
  | ③ 计算去重 | 以“前表摘要、后表摘要、规则主体 digest”为键的缓存，每个键只算一次，结果分发到每张逻辑表，并填入各自的表名 | 纯粹的性能优化，对业务语义透明 |

- **分发结果的例子：** A1、A2、A3 在两侧的内容都相同，规则也相同。比较只算一次，结果中除表名以外的内容只取决于“前内容、后内容、规则”，复制三份并分别填入表名，就等于各自比较了一次。
- **去重键不能用现有的 digest。** 现在的 `comparison_rule_digest`（`table_rules/resolver.py`）包含 `canonical_table`，每张表都不同，按它作键不会命中。去重键改用一个**不含表名的规则主体 digest**，现有 digest 继续用于原来的用途。
- **约束（写入比较与风险能力的 Contract）：**
  - 只有纯函数可以按第 ③ 层的键缓存，也就是单表比较结果和单表风险 facts，它们只取决于“前内容、后内容、规则主体”；
  - 凡是依赖表名、分组成员或其他表的输出，一律在去重之后的汇总步骤计算，不进入缓存；
  - 用测试守护：同一份输入，开启和关闭去重，facts 与 records 的摘要必须相同。
- **分组变化作为风险信号：** 在第 ② 层检测。比较前后两个快照按摘要划分出的分组（例如 {A1, A2, A3} 中 A2 分出来），产出“分组分裂”事实，交给风险规则判定等级。这一步只用 manifest 中的摘要，不读行数据；History 也能用每个 commit 的 manifest 追溯分组的演变。
- **r2 补充：** “分组分裂”是新的业务风险事实，不是性能工作。建议从 Phase 6 拆出单独立项，Phase 6 只做对业务语义透明的第 ③ 层（§13 B4）。
- **owner 决定（r12，2026-10-24）：拆出单独立项，不进 Phase 6。** 依据（一次性脚本按原始 SQL 统计，只记录计数）：

  | 数据 | v1 中的同内容组 | 两版都没变 | 整组一起变 | 组分裂 | v2 中由合并形成的组 |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | t4 v1→v2 | 10 | 8 | 2 | 0 | 0 |
  | testdata1 | 9 | 8 | 1 | 0 | 0 |

  同内容的表在两份数据中都是要么一起不变、要么一起变，没有出现分裂或合并；该信号目前没有使用方，也没有发生过的案例。以后要做也便宜：只需比较两个 commit 的 manifest 中的表摘要（B1 落地后即具备），可按 D9 的触发事件预留方式接入。第 ② 层中“ruleset 声明预期相同的表族”同样搁置。**重开条件：** 业务方提出需求，或出现因分组分裂漏报风险的实际案例。
- **与旧实现的区别：** 旧实现按 `canonical_artifact_ref` 把同内容的表分组，在 Dolt 中只存一张物理表、其余逻辑表映射到它（`legacy/backend_vnext/capabilities/snapshot_materialization/canonical_storage.py`）。映射跨提交演变，因此需要分岔逻辑。本设计中，分组只是第 ② 层按需推导出的事实，不存在需要拆分的持久映射。

#### D5 第 ③ 层审核分析与 owner 决定（r8，2026-10-24）

**owner 决定（2026-10-24）：** B3 拆为两部分。**单次操作内去重**随 D7 实施；**跨操作缓存**暂缓。跨操作缓存与 History 缓存设计的关系见本节末尾，待 owner 确认。

**收益估算。** 一次性脚本按原始 SQL 计算，未经规范投影，只记录计数，数字是近似值。

| | 同内容表组 | 涉及表数（最大组） | 变化表 | 变化表中前后内容都相同的组 | 去重可省的比较行数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| t4 v1→v2 | 10 | 50（12） | 38 张，约 26.3 万行 | 2 组，12 张表 | 约 5.3 万行，约 20% |
| testdata1 | 9 | 34（5） | 58 张，约 24.8 万行 | 1 组，5 张表 | 约 2.1 万行，约 9% |

B1 的结构性过滤先跳过内容不变的表，去重只对“内容变化、且多张表变成相同内容”有收益：单次操作内约 10–20% 的比较量。

**代码核对：哪些输出依赖表名或其他表。**

- **比较：** 单表比较只依赖本表任务的输入，各项上限按表计算（`max_records_per_table` 等），满足纯函数要求；行身份摘要不含表名。比较记录的每一行带表名，facts 中的 descriptor 带表名与显示名，分发时改写。
- **风险：** v1 是固定规则集，没有按表名选择的规则；但 `annotation_id` 含表名，组合信号表按表名特判（`COMPOSITE_SIGNAL_POINT_TABLE`），每个 pair 的标注总数上限（`max_annotations_per_pair`）按表的顺序累加，一张表的风险输出因此依赖排在它前面的表。只能缓存“未套用 pair 上限之前的单表标注”；pair 上限与组合信号表在汇总步骤处理。

**缓存键要补全。** “前表摘要、后表摘要、规则主体 digest”不够。结果还依赖两侧的有效键与存储规则（`storage_facts_before/current`）、keyless 策略与有键/keyless 切换许可、两侧的 business schema digest 与行数、比较算法与记录格式版本、artifact scope。键不手工列字段，而是取“去掉表名与显示名之后的整个单表比较任务输入”的摘要，新增字段自动进入键。

**B3 的 Contract 内容：** 在 Comparison 与 Risk Contract 中写明，单表比较结果与未套用 pair 上限的单表风险标注，是“去掉表名的任务输入”的纯函数；表名、显示名、标注编号、pair 上限与组合信号表在汇总步骤绑定。

**单次操作内去重的实施：** 随 D7 一起做，D7 本来就要重新定义单表比较接口。分发时改写记录里的表名，记录数受单表上限约束，成本有界，比较记录格式不改。

**测试：** 一个权威测试负责：同一输入，开启与关闭去重，facts 与 records 的摘要相同；另用 Hypothesis 随机把表复制成多个名字。

**History 缓存设计与跨操作缓存的关系（审核方分析，待 owner 确认）。**

owner 提出的设计：在对应数据 Submit 或首次 History cache miss 时形成表缓存、diff 缓存与 risk 缓存；History 查询大部分从这三类缓存中获取和拼接，避免 Dolt 的耗时操作。

- **与跨操作缓存是同一路径。** diff 缓存与 risk 缓存就是第 ③ 层的跨操作缓存，键相同（去掉表名的单表任务输入摘要）；表缓存就是 B2 的规范表存储。“暂缓跨操作缓存”因此也暂缓了这条 History 快速路径。
- **设计合理，代码条件已具备。** History 现在对每个节点从 Dolt 全量物化，再运行与 Preview 相同的 pair 流水线（`application/pair_pipeline.py`），规则集为运行期规则集，artifact scope 来自同一套规则。只要规则集未变，Preview 中“基线 head → 上传”这一 pair 的单表结果，键就与 History 中“父 commit → 新 commit”的单表结果相同。
- **“拼接”按表进行。** 对 History 的每个 pair、每张表：
  1. 两侧表摘要相同（来自 B1 的 commit 每表摘要），直接判为未变化，不读数据；
  2. 不同则查 diff/risk 缓存，命中直接取用；
  3. 未命中时读表缓存，再未命中才读 Dolt，计算后写回。
  
  pair 级的 surface 与 bundle 由单表结果在汇总步骤组装。
- **第 1 步省掉的是比较，不是读取。** History 的 2–3 个节点可以不相邻，现在每个节点都全量读 Dolt；有了 B1 的每表摘要，未变化的表不再比较。但 History 结果需要打包整表数据（见下方 owner 决定），整表读取仍然需要，由表缓存承担。
- **缓存在哪里形成：**
  - diff/risk 条目在计算时形成，计算可以发生在 Preview 或 History 中；
  - Submit finalize 不做计算，只给该 Submit 对应 Preview 的条目加引用，让“父 commit → 新 commit”的结果保留下来（相当于旧实现的“Submit finalize 晋升”，内容寻址后只是加引用）；
  - History miss 计算后按 TTL 写回。
- **命中的边界：**
  - 规则集激活后键全部变化，首次 History 需重算，这是正确行为；
  - 不相邻节点中，一张表在区间内变化不止一次时，前后摘要对是新的，需要两侧表数据；B2 只为 head 保留表文件，更早 commit 的表首次走 Dolt、按 TTL 回填；
  - Preview 与 History 的 artifact scope 不同时，键不同，不能共用。
- **owner 决定（2026-10-24）：**
  - diff/risk 条目**按 TTL 保留**，不沿 commit 链长期保留；
  - History 结果**需要引用整表数据**，优先从表缓存读取。数据全量打包发送给客户端，客户端不再依赖服务端；上一版中“浏览时按需读取”会让客户端向服务端按需取数，违背这一原则，**撤回**。
- **整表打包对 History 设计的影响：**
  - 整表数据在服务端组装结果时读取：先读表缓存，未命中读 Dolt，读到后按 TTL 回填，再全部打进 bundle。
  - diff/risk 缓存命中省掉的是比较与风险计算，不省整表读取。B1 的每表摘要省掉的也只是未变化表的比较。
  - 能否“大部分避免 Dolt”，取决于各节点的表是否在表缓存中：当前 head 有正式引用，重复查询在 TTL 内命中；更早 commit 的表首次查询走 Dolt。若查询较早 commit 的 History 很常见，需重新评估 B2 中“正式引用只保留 head”。
  - 三节点 History 中，相邻节点内容相同的表按内容地址共享（bundle 契约已有 `shared/snapshot-tables/`），打包体积约为一份全量加上变化表。
  - bundle 中表文件的格式与服务端存储格式不同：bundle 契约规定为 Parquet，B2 的服务端存储为不压缩的 Arrow IPC。**owner 决定（2026-10-24）：bundle 仍用 Parquet，导出结果按“表摘要 + Parquet writer 版本”缓存，按 TTL 管理**（`contracts/comparison-bundle.md` 已规定跨 operation 的 snapshot Parquet cache 只能按 layout digest 与 writer 版本精确命中，改为按表摘要命中）。原样重传（W2）与重复 History 直接命中导出缓存。
- **跨操作缓存的定位（owner 决定，2026-10-24）：** 由“暂缓”改为“设计在 Phase 6 设计中定稿，实现排在 D7 之后，以 A2 的 History 目标验收”。D7 的单表接口直接按可缓存的形态产出。

### D6 表级计算调度：按特征建模，配置独立于 ruleset

- **策略：**
  - 低于阈值的小表，在进程内串行成批处理；
  - 重表进入一个有上限的工作池，按预估成本从大到小派发（LPT），并发数用固定配置，不按 CPU 数量自动放大（§5.5）；
  - 超大表进入表内分块并行（L3）；
  - 结果按规范表顺序合并，保证并行与串行得到相同的摘要。
- **成本模型：** 输入是比较角色（ORDERED 的权重远高于 STANDARD）、实际行数、列宽、是否产出行级记录，例如 `成本 ≈ 角色权重 × 行数 + 列宽项`。**不维护重表名单。** 系数由 S5 的逐表实测校准；新实现完成后，相对成本会变（例如 ordered 改用 Rust 以后），要重新校准。
- **调度信息不放进 ruleset：** ruleset digest 参与比较语义（DC10、DC24），把性能信息写进去，调一次参数就会让已有 Preview 判为陈旧、缓存失效。能从现有规则推导的特征（例如 ORDERED 角色）直接推导；需要额外标注的内容放在独立的性能配置中，不参与任何 digest。
- **并行机制：** 首选在 Rust 中用 Rayon，不受 GIL 限制。在 Python 中用多进程时，D2 的内存映射文件让进程之间只传路径、不传数据。Python 3.14 的 free-threaded 构建可以作为备选，前提是依赖支持（当前运行时为 Python 3.14.6 标准构建）。
- Phase 7 引入全局并发预算后，单个 operation 的工作池要服从这个预算。

### D7 比较改为列式实现，Python 实现降为参照实现

| 比较类型 | 实现方式 | 可行性 |
| --- | --- | --- |
| standard（按键对齐） | 按键列做哈希连接，比较行摘要列，分出新增、删除、修改；只对修改行逐列比较。用 Polars 或 Rust | 天然适合列式 |
| ordered（IEC104：位置列、稳定键、空白行、移动、区间、G8b 骨架） | 带规则的序列算法，难以向量化；在 Rust 中直接在 Arrow 数组上写循环 | 可行，前提是规则写成精确规格 |
| keyless（多重集合差异） | 先按行摘要排序，再做多重集合合并 | 简单 |

- **一致性保证：**
  - 现有 Python 实现作为参照实现（ADR 0001）。implementation-stages §9 已有的退出条件继续适用：facts、records、排序与 digest 一致，并且可以用 feature flag 退回参照实现；
  - 差分测试沿用 §6.3 的分层：现有 golden 双实现参数化；Hypothesis 生成的随机表对；真实数据 t1–t4 逐表比对 facts 与 records 的摘要；
  - 先把容易产生分歧的地方写进 Contract：浮点数（-0.0 的归一已有）、NULL 语义、字符串按字节排序而不按 locale、记录的输出顺序、ordered 的并列规则（G8b-F2 保留的规则）。
- 仓库中已有 Rust 与 PyO3 的基础：`vnext/rust/gateway-compute-python`。
- 列式化是否作为 Phase 6 的主线，由 V1 的结论决定。

#### D7 审核分析与 owner 决定（r11，2026-10-24）

**S5 数据（t4，比较与风险段，wall 秒）：**

| 场景 | 比较 | 风险 | 说明 |
| --- | ---: | ---: | --- |
| v1 首次上传（空基线） | 148.4 | 27.4 | 全部是新增表 |
| 原样重传（0 张表变化） | 40.6 | 0.0 | 本应接近 0 |
| v2（26 张表变化） | 39.2 | 0.0 | |
| History | 38.6 | 0.0 | |

**代码核对中的两个发现：**

1. **ordered 表从不提前退出。** standard 表在内容摘要相同时直接判为未变化；`comparison/standard.py` 的 `_compare_task` 在提前退出判断之前就把 ordered 表交给 `compare_ordered_task`，后者总是读两侧全量数据并跑完整算法。重传、v2 与 History 中约 40 s 基本是这部分。另外，未变化 ordered 表的 facts 中有 `before/current_ordered_digest`，它们由比较侧从行数据算出且含表名；要做到不读数据就判定未变化，这两个摘要须改为取自 B1 的表摘要或 manifest，并去掉表名（同时满足 B3 的纯函数要求）。
2. **整表新增时逐行产出完整记录。** 新增表的每一行都生成一条带全部值的 `ROW_ADDED` 记录，风险再按行发 `MEDIUM_LOW` 标注（t4 首次上传约 25 万条，原因全部相同；单表与 pair 的标注上限为 200 万与 400 万，不会触发降级）。v1 的比较 148 s 与风险 27 s 主要是这一项。B9 补齐整表打包后，这些记录与 bundle 中的整表数据完全重复。

**owner 决定（2026-10-24）：**

1. 未变化 ordered 表“不读、不比”放进 B1/B8/B9 的 Contract 阶段，作为 B1 结构性门槛的一部分，不等 D7。
2. 整表新增或删除时，逐行记录与整表浏览两种方式 owner 都可接受，**采用审核方建议：整表浏览加表级计数风险**（理由与条件见下）。
3. D7 用 Rust 加 arrow-rs，不引入 Polars。
4. D7 先做 standard 与 keyless；ordered 待 V1 结论。

**整表新增/删除的处理（审核方建议，owner 采纳）：**

- **理由：**
  - 逐行记录与 bundle 中的整表数据重复，首次上传的下载体积因此约翻倍；
  - 逐行 `ROW_ADDED` 标注对整张新表没有区分度：每一行的原因相同、等级相同；
  - W1 的比较与风险时间（t4 约 175 s）基本消失；
  - `UPDATE_ONLY` 范围已经对新增、删除行不产出记录，是现成先例。
- **做法：**
  - 表状态仍为 `ADDED_TABLE` / `DELETED_TABLE`；
  - 不产出逐行记录；
  - 风险改为一条表级标注，证据中带行数（现有 `TABLE_ADDED` / `TABLE_DELETED` 规则加计数）；
  - surface 用 `TABLE_BROWSE`：新增表浏览 `current_table_ref`，删除表浏览 `before_table_ref`（现映射为 `RECORDS_ONLY`/`SUMMARY_ONLY`，需修订）。
- **条件：**
  - 依赖 B9 的整表打包，二者须在同一个 Contract 阶段落地，否则新增表在前端完全不可见；
  - 前端的表浏览须能在表级展示风险。
- **代价：** 新增表不再有逐行风险定位。以后若需要对新增表的特定行告警，按 D9 的触发事件预留方式接入。
- **范围：** 只针对整表新增或删除；两侧都存在的表不受影响。

**D7 的范围：**

- **standard keyed 表：** 按键做哈希连接，比较行摘要，只对修改行逐列比较。S5 中大于 1 万行的 standard 表是逐表耗时最大的一组。
- **keyless 表：** 行摘要排序后做多重集合合并。
- **ordered 表：** Python 版 845 行（含 G8b 骨架与并列规则），须先把规则写成精确规格。V1 在变化的 ordered 表上做 Rust 原型与差分测试，再决定是否迁移；V1 期间 ordered 表保留 Python，只处理变化表。
- **技术栈：** Rust 加 arrow-rs（workspace 已钉 arrow 59.1、parquet、pyo3-arrow），不引入 Polars：Polars 自带线程池，与 C6 的统一固定并发上限冲突，Python 侧也会出现两套列式引擎（C5）。记录由 Rust 直接写成 Parquet，不经 Python 对象。
- **接口：** 粗粒度调用，一张表的任务进，facts 加 records 出（ADR 0001）；输入不含表名（B3），同一接口直接支持单次操作内去重与以后的跨操作缓存。
- **一致性：** 沿用 §6.3 的差分分层，Python 实现作为参照，可用 feature flag 退回。分歧点先写进 Contract：浮点 -0.0、NULL、字符串按字节排序、记录输出顺序、ordered 并列规则。退出条件沿用 implementation-stages §9：facts、records、排序与 digest 一致。
- **收益：** 不预估倍数，以 V1 与 D7 原型实测为准。

**顺序：** B1/B8/B9 Contract 阶段（含 ordered 不读不比、整表新增/删除改为整表浏览）→ V1 → D7（standard、keyless；ordered 视 V1）。B2 的格式切换与 B3 的单次操作内去重随 D7 落地。

### D8 Dolt 中同内容表的重复写入

块共享解决了空间问题，这一点旧实现已经测过；但每张表的行数据仍要逐行写入、建树，写入耗时无法靠块共享消除。候选做法如下，按推测收益从高到低排列，都要实测（V3）：

1. **表级复制：** Dolt 的表数据是指向内容的哈希引用，`dolt table cp` 这类操作有可能只复制引用。如果 RS 内部能用上，同组的 k 张表只需真正写入一次。
2. **服务端 `INSERT INTO b SELECT * FROM a`：** 省去传输与 SQL 解析，建树成本还在。
3. **最后手段：** 在 RS 内部做存储层去重，把旧实现的映射收在 RS 里，作为 RS 的实现细节，不进入 backend 的业务模型。

- **Contract 影响：** 第 1、2 种都需要 import 包能表达“表 B 的内容与表 A 相同”，要修订 RepositoryImportArtifact 的包格式（Repository 一侧）。
- **优先级可以靠后：** 重复写入只发生在同组表一起变化时，以及首次提交时；而且 Submit 对耗时不敏感，S5 也显示 Submit 的大头不在 Dolt 写入。先用 V4 的统计算出最坏情况，再决定是否投入。
- **owner 决定（r12，2026-10-24）：不做。** 上限估算：t4 全量直接导入 Dolt 约 24 s，同内容表的重复行约占原始行数的 17%（34.5 万行中约 5.8 万）；首次 Submit 去重最多省约 4 s，之后的 Submit 只写变化表，“整组一起变”的重复行约 5.3 万，最多省约 5 s。S5 中 v1 Submit 566 s 的大头在 snapshot build 与 mutation planning（231 s），属于 B7。前两种做法都要修订 RepositoryImportArtifact 的包格式，跨 Backend 与 Repository Service 边界，还要过 Repository Contract、镜像与容器门禁，代价与收益不相称。**重开条件：** B7 完成后 Submit 仍达不到 A2 的目标，且实测 Dolt 写入在其中占比明显。

### D9 只增列的 schema 变化：按共有字段判定（r4 新增，r5 更新）

**发现与需求（owner，2026-10-24）：** 业务数据测试中，某些情况下数十张表同时出现 schema 变化，基本是新数据相比归档数据增加列（列只增不减）。

**owner 决定（2026-10-24）：**

1. 从前端角度，“只增列”**不算 diff，也没有风险**：每张表只按两个版本的共有字段判定变化与风险，不降级。
2. 后端与实际入库可以登记 schema 变化；**不需要**在 Submission 或 History 结果中显式列出新增列。
3. “只增列”以及超出当前计划的“只减列”，后续可能增加触发事件的逻辑（例如推送告警），暂时不需要动作，但最好有预留设计。
4. ENUM 标签扩展（只增加标签、已有标签全部保留）算兼容，与只增列同样不算 diff。
5. 全部变化都是只增列时，Preview 不需要提示“提交仍会生成版本”。
6. SET 成员扩展按 ENUM 同一规则处理；只减列保持现行处理（`SCHEMA_CHANGED`，`MEDIUM_HIGH`）。

**新的业务测试数据 testdata1（data1 → data2，owner 提供，2026-10-24）。** 只记录计数，真实数据不入 Git（DC22）。

| 项 | 计数 |
| --- | --- |
| 规模 | 单个 `sql/dbcfg.sql`，约 49 MB（CRLF 行尾），约 26.8 万行；含 `comps/logic/logics.xml`；与 t4 同一量级 |
| 表数 | 199 → 200（新增 1 张，1 行） |
| 列集合不变 | 167 张：137 张内容不变（7,128 行），30 张内容变化（124,671 行） |
| 只增列 | **32 张**（11 张增 1 列，21 张增 2 列），新列都追加在末尾 |
| 其中共有字段不变 | 29 张，共 26,783 行 |
| 其中共有字段变化 | 3 张，共 96,383 行：一张删除 9,000 行并伴随首列（疑为 ID）重新编号，一张删除 4,500 行，一张增加 1 行 |
| ENUM 值域扩展 | **2 张**：同一个 ENUM 列的标签由 10 个增至 13 个，新标签插在中间，已有标签都保留 |
| 删列、改主键 | 0 |

统计用一次性脚本完成（自写的引号感知元组切分，不是产品解析器），只作讨论依据，正式数字以后续取证为准。

**现状（代码核对）：**

- **比较核心已经只比较共有列。** `comparison/row_encoding.py` 的 `_schema_view` 取两侧列名交集作为比较列，行级新增、删除、修改都按共有列产出，另加一条 `SCHEMA_CHANGE` 记录（`CURRENT_ONLY_COLUMNS`）。ordered 表同样比较共有列，只有必需列缺失、类型不兼容或没有共有列时才降级。
- **“降级”来自表状态与下游映射。** 只要有新增列，表状态就是 `SCHEMA_CHANGED`，覆盖 `MODIFIED`/`UNCHANGED`：
  - 风险：`SCHEMA_CHANGED` 默认规则对每张表发出 `MEDIUM_HIGH` 的表级风险，风险范围从 `STANDARD_ROWS` 变为 `TABLE`；
  - surface：处理模式为 `SCHEMA_ONLY`，展示策略为 `RECORDS_ONLY`（没有 records 时为 `DEGRADED_NOTICE`），而不是普通更新表的 `CURRENT_WITH_RECORDS`；
  - 性能：business schema digest 不同，比较的提前退出不成立，这类表都要全量读基线并比较。
- **ENUM 值域扩展同样被当作 schema 变化。** 列签名比较的是 `scalar_type` 全文（`_column_signature`），标签列表变了，该列就判为不兼容（`INCOMPATIBLE_SELECTED_COLUMNS`），表状态为 `SCHEMA_CHANGED`；若该列是有效键，表会降级。规范编码按标签文本而不按序号编码 ENUM 单元格，所以已有值在两侧可以直接比较。
- **入库：** 投影 schema 变化时 mutation planning 整表重写（`_table_projection_unchanged`）。每个 commit 的 manifest 已记录保留列与 schema digest，schema 变化可以由相邻 commit 的 manifest 推导，这就是“登记”。

**建议设计：**

- **一个分类，单一 owner。** 比较能力为每张两侧都存在的表计算一个 schema 演进分类，作为比较 facts 的一部分。现有的 `ComparisonSchemaChanges`（`current_only_columns`、`before_only_columns`）已有列清单，只需补分类：

  | 分类 | 条件 | 本期处理 |
  | --- | --- | --- |
  | `NONE` | 列集合相同；签名相同，或只差 ENUM/SET 值域扩展 | 不变；值域扩展不算 diff |
  | `COLUMNS_ADDED` | 前侧列是后侧列的真子集；共有列签名相同（或只差 ENUM 值域扩展，见下）；有效键不变 | **不算 diff、无风险**：表状态按共有列的结果取 `MODIFIED` 或 `UNCHANGED`；不产出 `SCHEMA_CHANGE` 记录，不发 `SCHEMA_CHANGED` 风险；surface 按普通更新或未变化展示 |
  | `COLUMNS_REMOVED` | 后侧列是前侧列的真子集，其余同上 | **保持现行**（`SCHEMA_CHANGED`，`MEDIUM_HIGH`；owner 决定）。只减列会在入库时删除该列的已存数据；分类仍单独计算，供以后的触发事件使用 |
  | `INCOMPATIBLE` | 其余情况：同时增删、共有列改类型或可空性、有效键变化 | 保持现行 |

- **ENUM 值域扩展（owner 决定，2026-10-24）：** “只增加 ENUM 标签、已有标签全部保留”视为兼容的签名变化，与只增列同样不算 diff；标签的插入位置不影响判定。删除或改名标签仍按不兼容处理。SET 成员扩展按同一规则处理（owner 决定）。
- **预留触发事件：** 分类与列清单作为比较 facts 的稳定字段保留，随 Preview 的比较产物持久化，入库侧另有 manifest 可推导。以后要做告警时，作为这一 fact 的新 consumer 接入（一条风险规则，或独立的通知 consumer），不改比较本身。按比例化保障政策，现在不建事件总线、通知状态机或订阅配置，因为目前没有 consumer。
- **只增列，Preview 无 diff，Submit 仍产生新版本。** 只增列改变规范状态（新列的值要入库），因此 `NO_CANONICAL_CHANGE` 不成立。这与 G8 中 ordered 空白行字段的已接受先例相同，须写入 Contract。全部变化都是只增列时，前端看到“无变化”，提交后仍生成版本；owner 决定 Preview 不提示。
- **新增列的值在本期不受任何风险检查。** 这是 owner 决定的直接结果：新列出现异常值，不会在 Preview 中被发现，直到以后接入触发事件。
- **性质与阶段：** 这是业务语义变更（Comparison、Risk、Surface Contract 与相应 golden），不是性能工作；但它和 B1 一样改变对照基准，建议并入同一个 Contract 阶段，基准只重建一次。D7 的列式比较实现须同时满足这一语义。

**表摘要是否需要增加字段（结论：不加）：**

- **正确性上不需要。** 比较本来就按共有列计算。表摘要只回答“规范内容是否有任何变化”，只增列确实是变化；读取并比较这类表，不违反 DC35 的结构性门槛（未变化的表不读基线）。
- **可选的性能字段是每列摘要**：在 manifest 中为每张表记录按规范键顺序逐列计算的摘要，keyed 表在键列摘要与行数相同、共有列的列摘要都相同时，可以不读基线。限制如下：
  - 它要求规范行顺序（按键排序），与 B1“保值统一”的多重集合摘要是两套定义；
  - keyless 表不适用，因为列摘要无法还原行的组合；ordered 表要按 gid 顺序另行定义。
- **testdata1 的数据说明收益有限。** 可以省掉的只有 29 张共有字段不变的只增列表，共 26,783 行，约占 data2 的 10%；内容变化的 34 张表（30 张列集合不变、3 张只增列、1 张新表）共约 22 万行，无论如何都要比较。
- **建议：** 不加。读基线由 D2 的 mmap 承担、比较列式化（D7）之后，这部分成本已经很小。

**测试数据：**

- **作为 Contract 回归用例：** 按 D9 的分类各写合成用例（只增列且共有字段不变或变化、只减列、ENUM 值域扩展、同时增删），进入普通 CI。
- **作为真实数据档：** 把 testdata1 按现有真实数据档的方式打包登记（`datasets.json`，别名不含项目名），作为 DC35 W1–W4 之外的 schema 演进负载（W5），同时用于 D9 的端到端验证。
- **节点：** owner 已允许拷贝到其他测试节点。按 DC36，调试放在 `ct108-gw-dms-05`，取证放在 `ct108-gw-dms`，需要时再拷贝，同一档的完整旅程在同一节点内完成。

### D10 Submit 只写变化：表级跳过、按阈值行级修改、渲染直通（r13 新增）

**现状（代码核对，2026-10-25）：**

- **每次 Submit 都重写全部表。** prepare 用 `REBUILD_ALWAYS` 规划，但传入的“变化前”状态为空（`capabilities/mutation_planning/import_replay.py`），规划器把每张表都当作新表；schema SQL 为每张表生成 `DROP TABLE` + `CREATE TABLE`（`capabilities/storage_projection/import_replay.py`），DML 插入全部行。t4 v2 只有 26 张表变化，prepare 外层仍为 369 s，与 v1 的 374 s 相当。
- **与 Contract 不符。** Storage Mutation Contract §2 把 `REBUILD_ALWAYS` 定义为“每个变化表生成完整重建”，现在的实现是所有表都重建。
- **plan child 231 s 的去向。** 主要是逐行构造变化集对象（`ChangeSetMutation`、`MutationKeyedRow`）、两次排序校验、对整个变化集做 canonical JSON 摘要。导入路径不发布变化集（`artifact_store=None`），渲染器也不检查这些摘要，变化集摘要与逐行摘要都没有消费方。真正渲染 SQL 的 replay child 只有 7 s；snapshot build 69 s 是把冻结的 Parquet 表读成 Python 行。
- **RS 已支持只写变化。** RS 从 expected parent 建立私有 ref，在上面执行 `replay.sql`，再用整个 catalog 与包 manifest 做 STRUCTURAL 校验（表集合、行数、主键、列）。只要 manifest 仍列出全部表，`replay.sql` 只处理变化部分也能通过，RS 的 Contract 与代码都不用改。
- **归因缺口。** 真实旅程中 Submit 的 worker CPU（479 s）比 prepare 外层（374 s）多约 100 s，归属未明，由 V5 拆分。

**真实数据：变化比例两极分布。** 一次性脚本按原始 SQL 计算，只记计数，已去掉不入库的 skipped 表；本地 medium 与 testdata1 是同一份文件，独立样本只有两个。

| | 变化表 | 按主键变化 ≤ 5% 的表 | 这些表的行数 / 实际变化行 | 其余变化表 |
| --- | ---: | ---: | ---: | --- |
| t4 v1→v2 | 30 | 12 | 63,936 / 156 | 16 张约 100% 变化（键整体更换），2 张 keyless |
| testdata1 | 55 | 8 | 32,020 / 380 | 14 张约 100% 变化，32 张只增列，1 张 keyless |

- 阈值放在 5% 到 50% 之间的任何位置，分出来的表都完全相同，结果对阈值不敏感。
- t4 的 12 张小变化表全是有序表（11 张 iec104、1 张 forwardtable）。不纳入有序表，阈值方案在 t4 上没有收益。

写入 Dolt 的数据量（按约 24 s 导入 25 万行粗估，t4 v2 的 Dolt 写入从约 8 s 降到约 2 s，2× t4 时翻倍）：

| | 全部重写（现状） | 只重建变化表 | 再加阈值 |
| --- | ---: | ---: | --- |
| t4 v2 | 约 16.3 万行 | 约 8.2 万行 | 约 1.8 万行重建 + 156 条行级语句 |
| testdata1 | 约 11.8 万行 | 约 11.5 万行 | 约 8.3 万行重建 + 380 条行级语句 |

**owner 决定（r13，2026-10-25）：**

1. **表级跳过（B7a）。** prepare 拿 T1 冻结的上传侧 manifest，与 expected parent 的 manifest（经 CommitCanonicalMetadataPort 解析）逐表比较。内容摘要（D1）、schema 摘要、键与存储视图都相同的表，不进入 `replay.sql`；删除的表照旧 `DROP`。parent 为 INITIAL、缺少 metadata 或投影版本不同时，全部表按变化处理。包 manifest 仍列出全部表。
2. **变化表按阈值行级修改或整表重建。**
   - **policy：** 生产 policy 从 `REBUILD_ALWAYS` 改为 `ADAPTIVE_PATCH`。变化表满足 Contract §3 的条件时用 DELETE / UPDATE / INSERT，否则整表重建。
   - **有序表：** 纳入行级修改（GID_NO_V1）。以 `gid` 为存储键，位置 `no` 作为普通列更新。中间插入一行会让后面所有行的 `no` 变化，空 gid 行的伪 gid 也按 `no` 顺序连续分配，这些都表现为大量 UPDATE，会自然超过阈值、退回整表重建，正确性不受影响。
   - **仍整表重建：** keyless 表（DC29），以及 schema 变化的表（含 D9 的只增列）。“ALTER 加列 + 行级修改”通常等于更新每一行，现在不做。
   - **阈值：** 先沿用 Contract §3 的 1,000 行 / 5%，V7 实测后定稿。
   - **基线来源：** 行级 diff 需要的基线，优先从规范表存储读取（D2、D3；parent 即正式引用的 BaselineHead），Dolt 兜底。
   - **比较内核：** 存储 diff 按存储键比较全部保留列，与 D7 共用列式比较内核，只是参数不同。
3. **不复用 Preview 的比较结果。** Preview 的比较结果按前端语义生成：按 D9 只比较两版共有的列，有比较时排除的列，还有风险预算截断。存储需要完整的保留列，两者不能互相替代。Submit 复用的是 Preview 冻结的规范表与 manifest。
4. **渲染直通（B7b）。** 变化表直接从冻结的规范 Arrow 表渲染 SQL，整表重建与行级修改都如此。导入路径不再构造逐行变化集对象，也不再计算没有消费方的摘要。表级决定（跳过、重建、行级、删除确认）仍归规划器。snapshot build 随 B2 的 Arrow IPC 存储解决，之后按 §5.4 进入 Rust。W1 与 W4 没有可跳过的表，只能靠这一部分提速。
5. **保留通用规划器与 ChangeSet Contract。** 它们是 ADR 0014 外部目标的 Contract owner。`external_target_sync` 目前没有生产调用方，Phase 6 不删除。外部分区库的预留见 §14。

**正确性前提。** 表级跳过与行级修改都假定 parent 在 Dolt 中的内容与 parent manifest 一致：整表重建会覆盖不一致，跳过与行级修改不会。保证来自：
- expected parent CAS；
- 从存储读出的基线按 parent manifest 的摘要校验；
- ADR 0009 的受信 Repository（Dolt 只经由 Submit 写入）。

按比例化保障政策，不另加条件 DML 或提交后回读校验。

**Contract 影响。**
- Storage Mutation Contract §2/§3：生产 policy 改为 `ADAPTIVE_PATCH`，有序表纳入行级修改资格；
- ADR 0014：生产默认 policy；
- Canonical Storage §6.1：`replay.sql` 改为相对 expected parent 的确定性 replay，未变化表不出现；
- T1 冻结的 `builder_mutation_policy`；
- prepare checkpoint 增加 parent manifest 摘要的绑定；
- 包 golden。

RepositoryImportArtifact 的包格式与 Repository Service Contract 不变。

**验证。**
- **差分验证：** Dolt 按内容寻址，新旧两条路径在 t4 v2 上应得到相同的表哈希。这一点未实测，作为差分验证项。
- **计数断言（满足 A3）：** `replay.sql` 涉及的表数等于变化表数；行级语句数等于行级修改表的变化行数。

**阶段位置。**
- **Contract 阶段：** 表级跳过、阈值方案的 Contract 修订，以及基于现有规划器的实现，放进 B1/B8/B9 的 Contract 阶段，包 golden 只改一次。
- **阶段 ⑧：** 渲染直通与列式存储 diff 依赖 B2 与 D7 的列式内核。

## 10. 旧实现：可以参考的与需要重新设计的

旧实现位于本地参考目录 `legacy/backend_vnext/`，只用作行为参考（AGENTS.md「项目前提」）。

| 旧实现 | 处理 |
| --- | --- |
| Preview 不访问 Dolt，基线从归档时保存的快照行 artifact 恢复（`snapshot_rows_archive`） | 借鉴思路；新设计中基线来自规范表存储，Dolt 兜底（D2、D3） |
| 快照表按内容寻址存储（`shared/snapshot-tables/`，Parquet） | 借鉴；格式改为 Arrow IPC（D2） |
| 投影表缓存（`cache/projection_table.py`） | 不再需要：Dolt 与存储中保存的都是规范表（D4） |
| comparison core cache，三种来源：Preview 完成、Submit finalize 晋升、History 计算 | 借鉴；按内容寻址后，晋升步骤不再需要，摘要对相同即自动命中（D5） |
| 把缓存补全移出返回路径，用小线程池执行 | 借鉴（D3） |
| 同内容表在 Dolt 中只存一张物理表，并维护跨提交的映射与分岔逻辑 | 不沿用；改为三层分离（D5），写入优化另行实测（D8） |
| 用 Polars 和 Parquet 做列式处理 | 借鉴列式思路（D7） |
| 归档快照作为基线的事实来源 | 重新设计：vNext 的权威是 Repository commit 加 manifest（ADR 0019），缓存以不可变摘要为键，定位为派生数据 |
| Dolt native diff | 不沿用：vNext 按列名与有效键对齐，不用 native diff（设计 §4.5） |
| 缓存条目用 pickle 存储 | 不沿用：改为 Arrow IPC 与 JCS |
| hidden summary | 已按 DC9 删除 |
| 缓存键不含运行期规则的语义 | 补上：键包含规则主体 digest（DC10） |

## 11. 前置验证任务

在正式的 Phase 6 设计之前完成，用来确定方案和排序：

- **V1 ordered 比较的小规模验证（未做）。** 用 Rust 在 Arrow 数组上实现一个 IEC104 ordered 系列的比较，在 t4 的同类表上与 Python 参照实现做差分测试，并测加速比。输出：一致性结论、加速比、规格中需要澄清的地方。它决定 D7 能否作为主线。
- **V2 S5 测量的扩展（已完成）。** 2026-10-17 决议并入 S5（DC32），结果见 [S5 handoff](p5-arch-closure-s5-handoff.md) §8–§11 与本稿 §2。旧实现同口径对照未能执行，条件允许时再测，不阻塞。
- **V3 Dolt 写入实测（r12：随 B6 搁置，不再是 Phase 6 前置任务；B6 重开时再做）：**
  - N 张同内容表的写入耗时，分别用逐表写入、表级复制、服务端 `INSERT ... SELECT`；
  - 同样数据直接导入 Dolt 的耗时已由 S5 给出（24 s），作为第 ⑧ 步的下界。
- **V4 同内容表组的统计（r12：不再是 Phase 6 前置任务。D5 与 D8 需要的计数已由一次性统计回答，见 §9 D5 第 ② 层与 D8；正式统计在 B4 或 B6 重开时再做）：** 在普查中增加只输出计数的统计：每份数据中同内容表组的数量、组的大小、组内行数，以及 v1→v2 的分组分裂与合并。用来估算 D5 的去重收益和 D8 的最坏情况。前提：先修普查工具的 G8a-F1（未扫描却报告 ordered_projection COMPLETE）。
- **V5 operation 级耗时归因（按需补充，r2 新增）：** 先不加插桩，从 control DB 的 step `started_at` / `completed_at` 得到 t4 Preview、Submit、History 的 step 级拆分；如仍不足以解释 §2.3 的缺口，再在 t4 Preview 运行期间用 py-spy 从主机侧采样一次（DC31 已允许，不改产品代码）。需要产品插桩时另行授权。
- **V6 SQL 解析器原型（r2 新增，主线的第一步）：** 见 §6.4 第 1 项。输出：单线程与多线程吞吐、与参照实现在现有测试和 t4 上的一致性、需要澄清的语义。
- **V7 Dolt 回放：整表重建与行级修改（r13 新增）：**
  - **做法：** 在调试节点上，用 t4 v2 与 testdata1 的变化表，分别生成整表重建与行级修改的 `replay.sql`（一次性脚本即可）。在同一 parent 上回放并计时，同时核对两条路径的表哈希相同。
  - **读取（r14 增加）：** 测 Dolt 逐表读取的吞吐，以及并发读取的加速比。
  - **输出：** D10 的阈值定稿；Dolt 写入在 Submit 中的占比，供 A2 与 B6 的重开条件使用；§3.8 H2 门槛定稿。

## 12. 开启前需处理的遗留项

| 项 | 内容 | 建议 |
| --- | --- | --- |
| G8a-F1 普查工具误报 | `benchmarks/real_dump_census.py` 在诊断模式下未扫描也报告 ordered_projection COMPLETE | V4 已不是前置任务；B4 或 B6 重开、需要正式统计时修复 |
| `uv-consume.sh` 锁快照残留 | 没有 EXIT trap，中途退出时 `mktemp` 文件留在 TMPDIR | Phase 6 kickoff 前小修 |
| SQLite 旁路文件残留 | 有测试留下 `repository-import-*.sqlite3` 的 `-shm` / `-wal` | 同上 |
| 三项文档整理 | snapshot-materialization 文档的 ADR 0019 取代提示；收口设计 DC28–DC34 索引与 DC26 表述；旧 5B/G11 deferred register 整理 | kickoff 前或首次修改相关文档时 |
| G6b 是否重新评估 | P5 exit review 认为已触及重新评估条件；终审判断未触发，维持 C | owner 决定 |
| 重要 keyless 表是否定义自然键 | 业务评估（DC29 后续，部署前） | 结论可能影响 D1、D7 对 keyless 的处理，建议在 D1 定稿前给出 |
| 标准模式 bundle 不含整表数据 | 代码核对（2026-10-24）：`application/pair_pipeline.py` 只在 DATASET_REPLACEMENT 模式下向 surface 传入表 ref，标准模式传空，Preview 与 History 的 bundle 因此只含 records、risk 与摘要，不含整表 Parquet；HTTP 下载按存储的 bundle 原样输出。这与 owner 的“数据全量打包发送客户端”原则及 `docs/backend-vnext/contracts/comparison-bundle.md`（Preview 为每张表发布 `current_table_ref`；History 发布可浏览的 snapshot rows）不一致，P5 文档中没有对应的决议或延期登记；测试只覆盖 replacement 模式与 bundle 组装单元。真实数据旅程只核对摘要，未发现该问题 | 业务缺口，不是性能工作；单独立项（§13 B9），owner 已给出范围与格式；在 B1/B8 的 Contract 阶段中修复 |
| GitHub 默认分支 | 远程默认分支仍为 `phase1/gate-ownership-repair` | owner 在 GitHub 设置中改为 `main` |

## 13. 待 owner 决议的事项

状态说明：**待决议**＝尚无结论；**owner 方向**＝owner 已给出方向，细节待讨论；**已决议**＝已有正式决议。

### A. 目标与范围

| # | 事项 | 状态 | 审核方初步倾向 |
| --- | --- | --- | --- |
| A1 | 目标的设定方法（§3） | **已决议（DC35，2026-10-24）** | 业务目标与结构性条件为门槛、下界分析只作报告；W1–W4 与草案数值（V5、V6 后定稿）；ct108 不设配额、按单任务资源上限 N/M 测量；项目级并发交给 Phase 7；合成 2× t4；1 + 3 次取中位数 |
| A2 | Submit 与 History 是否设目标（S5：Submit 566 s，对比 Dolt 直接导入 24 s；History 893 s） | **已决定（owner，2026-10-25）**：History 分 H1 相邻首查 ≤ 60 s、H2 冷查询 ≤ 5 min（V7 后定稿）、H3 重复查询 ≤ 15 s，H1（TTL 内）与 H3 以计数断言为门槛；Submit 按完成时间设门槛：S1/S4 ≤ 5 min、S3 ≤ 2 min，加 D10 的计数断言 | 见 §3.8。FULL 模式 Preview 之后的首次 History，diff/risk 缓存不命中，owner 决定接受 |
| A3 | “成本随变化量增长”是否作为硬性退出条件（§3.7） | **已决议（DC35 第 1 项）** | 是，尽量用确定性计数断言证明 |
| A4 | Phase 6 与 Phase 7 的边界（§4），同时改写 implementation-stages §9 的进入条件（§0 第 2 项） | 待决议 | 按 §4 调整 |

### B. 需要修订 Contract 的设计决定

| # | 事项 | 状态 | 审核方初步倾向 |
| --- | --- | --- | --- |
| B1 | D1 表摘要（BLAKE3、列式编码、与行顺序无关），以及它作为单独 Contract 变更阶段、完成后重建对照基准 | 待决议 | r4 改为“保值统一”（§9 D1 审核分析）：以现有 `raw_content_digest` 为唯一表摘要，manifest 内容摘要统一到它，去掉重复计算，commit 元数据返回每表摘要，复用 Rust `canonical_row_hash`；BLAKE3 降为备选。单独成一个小 Contract 阶段，在 S0/V5 之后、解析器主线之前，与 B8 同阶段 |
| B2 | D2 与 D3 规范表存储：格式、两类引用、写入时机；比例化保障说明 | **owner 方向（2026-10-24）**：同步写入；正式引用只保留当前 BaselineHead；先不压缩 | 见 §9 D2/D3 审核分析：用现有保护表实现两类引用，不新增状态机；T1 冻结对象与 ADR 0019 结构不变，修订 Canonical Storage §5 的格式与生命周期及设计 §4.6 的闭包条目格式；读取时校验 raw SHA-256，不符回退 Dolt；格式切换与 D7 或 C2 同期。待设计细化：磁盘需求估算、上传侧原始表是否仍需持久化 |
| B3 | D5 第 ③ 层计算去重与规则主体 digest；“只有纯函数可以缓存”写入比较与风险 Contract | **owner 方向（2026-10-24）**：拆分；单次操作内去重随 D7 实施；跨操作缓存（即 History 的 diff/risk 缓存）设计在 Phase 6 设计中定稿，实现排在 D7 之后，以 A2 的 History 目标验收；diff/risk 条目按 TTL 保留 | 见 §9 D5 第 ③ 层审核分析：缓存键取去掉表名的整个单表任务输入摘要；风险只缓存未套用 pair 上限的单表标注；History 结果整表打包，优先读表缓存 |
| B4 | D5 第 ② 层“分组分裂”风险信号是否在 Phase 6 范围内 | **已决定（owner，2026-10-24）**：拆出单独立项，不进 Phase 6 | t4 与 testdata1 中组分裂、合并均为 0；重开条件：业务方提出需求，或出现因分组分裂漏报风险的实际案例（§9 D5） |
| B5 | D7 比较列式化（以 V1 为前提）；差分测试与一致性条款作为强制要求；分歧点先写入 Contract | **owner 方向（2026-10-24）**：Rust 加 arrow-rs，不引入 Polars；先做 standard 与 keyless，ordered 待 V1；未变化 ordered 表不读不比放进 B1/B8/B9 Contract 阶段；整表新增/删除改为整表浏览加表级计数风险 | 见 §9 D7 审核分析。整表新增/删除的处理依赖 B9，须同阶段落地；前端表浏览须能展示表级风险 |
| B6 | D8 同内容表写入优化（依 V3、V4 决定；可能修订 RepositoryImportArtifact） | **已决定（owner，2026-10-24）**：不做；V3、V4 不再是前置任务 | 估算最多省约 4–5 s；重开条件：B7 完成后 Submit 仍达不到 A2 的目标，且 Dolt 写入占比明显（§9 D8） |
| B7 | Submit 复用 Preview 产物（§5.3），涉及 T1 冻结对象与 ADR 0019 | **已决定（owner，2026-10-25）**：表级跳过未变化表；变化表按阈值行级修改或整表重建（生产 policy 改为 `ADAPTIVE_PATCH`，有序表纳入，阈值先沿用 1,000 行 / 5%，V7 后定稿）；渲染直通；不复用 Preview 的比较结果；保留通用规划器与 ChangeSet Contract | 见 §9 D10。现有 Submit 每次重写全部表；修订 Storage Mutation §2/§3、ADR 0014、Canonical Storage §6.1、prepare checkpoint 与包 golden，RS Contract 不变。Contract 修订与基于现有规划器的实现放进 B1/B8/B9 Contract 阶段；渲染直通与列式存储 diff 放在阶段 ⑧ |
| B8 | D9 只增列的 schema 变化：按共有字段判定，不降级；入库照常并登记 schema 变化 | **owner 方向（2026-10-24）**：只增列与 ENUM/SET 值域扩展不算 diff、无风险；只减列保持现行；不在 Submission/History 中列出新增列；Preview 不提示“提交仍会生成版本”；为只增列与只减列预留触发事件（如告警），暂不实现 | 业务语义变更，修订 Comparison、Risk、Surface Contract，与 B1 同一 Contract 阶段。方向已全部给出，细节进入 Contract 修订。表摘要不增加字段（testdata1：每列摘要最多省约 10% 的行） |
| B9 | 标准模式 bundle 补齐整表数据（§12）：Preview 与 History 按“全量打包、客户端不依赖服务端”的原则发布整表 snapshot rows；整表优先从表缓存读取 | **owner 方向（2026-10-24）**：Preview 包含全部表（含未变化的表）；History 每个节点都包含全部表；bundle 表文件用 Parquet，导出结果按“表摘要 + writer 版本”缓存、按 TTL 管理 | 业务缺口，不是性能工作；与 B1/B8 同一 Contract 阶段。Preview 打包当前侧（上传）全部表，只有被删除的表需要基线侧数据；History 每个节点的全部表优先读表缓存，未命中读 Dolt 并按 TTL 回填 |

### C. 技术路线

| # | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| C1 | SQL 解析器作为主线并提前（§6） | **owner 方向（2026-10-24）** | 待定细节：差分验证的判定标准（错误消息是否要求一致）、语料范围、V6 原型的验收 |
| C2 | 解析器主线是否连同 business materialization 一并改为“解析即列式物化” | 待决议 | 物化 212 s 也是逐行 Python；合并可省去中间对象 |
| C3 | Rust 的目标：首要是突破并发瓶颈，同时计入单核效率（§5.1） | **owner 方向（2026-10-24）** | 待定：模块拆解（§5.4）与各层并发的取舍（§5.2） |
| C4 | 并发分层的取舍与顺序：L1a 双侧物化、L1b 双 pair、L1c 流水线重叠、L2 表级、L3 表内数据级（§5.2） | 待决议 | 建议 L2 为主线；L1a/L1b 只惠及 FULL 模式，成本低可顺带；L3 用于大表；顺序以 V5/V6 实测决定 |
| C5 | 技术栈 | **owner 方向（2026-10-24）：允许按需增加** | 待定：每项新依赖（Polars、arrow-rs、rayon 等）随所在阶段说明理由；避免 Python 侧同时引入两套列式引擎 |
| C6 | 并发上限（§5.5） | **owner 倾向：固定配置**，可讨论 | 建议每 worker 显式上限、原生线程池统一设定、配套单 operation 内存预算 |
| C7 | 调度配置独立于 ruleset（D6） | 待决议 | 接受 |

### D. 测量与流程

| # | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| D1 | 耗时归因（V5） | **owner 方向（2026-10-24）：按需补充** | 先用 step 时间戳，不足时 py-spy |
| D2 | Phase 6 测量 runbook | **部分决议（DC35）**：预热 1 次、测量 3 次取中位数；冷/热启动按负载区分；测量期间独占参考节点；规模口径与合成数据集 | 测试节点三台分工已决议并生效（DC36，2026-10-24）；待定：合成规则细节 |
| D3 | Phase 6 阶段结构 | 待决议 | S0 决议 → V1/V5/V6/V7 → 设计与执行计划 + 独立文档审核 → B1/B7/B8/B9 Contract 阶段（r13：加入 B7 的表级跳过与阈值方案；r4 调整：原为解析器主线之后的 D1 摘要阶段，见 §9 D1 审核分析）→ 解析器主线 → 按业务阶段分段实施；DC30/DC33/DC34 与 G12/G13 的门禁规则沿用 |
| D4 | V2 是否并入 S5 | **已决议（2026-10-17，DC32）** | 并入 S5，已完成 |
| D5 | Rust 测试的正式入口与门禁覆盖（建议并入 C1/C3 讨论） | 待决议 | 权威 runner 现在不跑 `cargo test`。调试节点上直接执行 `cargo test --workspace --locked` 失败 1 例（`gateway-compute-python` 的 `adapter_errors`，`No module named 'pyarrow.lib'`）：`vnext/rust/gateway-compute-python/tests/common/mod.rs` 写死了 `backend/.venv/lib/python3.14/site-packages`，未激活 venv 时 PyO3 嵌入的是系统 Python 3.13。设置 `VIRTUAL_ENV=<backend .venv>` 与 `LD_LIBRARY_PATH=<uv cpython-3.14.6 lib>` 后 exit 0。Rust 解析器主线开始前须定下调用方式（例如固定 PyO3 解释器，或提供脚本入口），并把 Rust 测试纳入权威门禁。数据见 [节点核对报告](p6-node-init-report.md) §5、§7 |
| D6 | 单次门禁时长（建议并入 D3 讨论，作为 P6 的测试基础设施事项） | 待决议 | 64 核新节点与 128 核 ct108 跑完整 runner 的时间相同（约 39 分钟）。耗时主要在 backend 串行批次（39 个用例约 1,590 s，大部分是 Compose 旅程）与 repository_service 串行批次（约 593 s）。加节点解决的是不同类运行之间的排队；要缩短单次门禁，须缩短串行批次。与 G11b-O3（并发优化，当时未授权）相关。数据见 [节点核对报告](p6-node-init-report.md) §4–§6 |

## 14. 不在本稿范围

- 正式的 Phase 6 设计、路径预算与执行计划：本稿决议之后再写。
- 多 worker、全局并发预算与背压（Phase 7）。
- Phase 8 shadow 切换与 Phase 9 生产加固。
- “分组分裂”等新的业务风险事实（已拆出单独立项，§13 B4）。
- 外部分区库（owner 初步设想，r13 预留，不排优先级）：未来可能用一个外部库，按表类型以分区大表汇总所有项目的数据，用于加速查询，避免轮询各项目的 Dolt。现有设计已留出位置，Phase 6 不做额外工作：
  - ChangeSet 是 ADR 0014 定义的目标无关变化集；
  - 规划按目标分别进行，输入里带 `threshold_policy` 与 `renderer_capability`，外部库可以用自己的阈值，或始终用行级修改；
  - 外部库相对自己上次同步状态的增量，由 `external_target_sync` 的 ledger 管理。

  D10 因此保留通用规划器与 ChangeSet Contract。
- Dolt 中同内容表的写入优化（不做，按重开条件登记，§13 B6）。

# Phase 6 规划讨论稿：按业务阶段的性能优化

- 状态：**讨论稿 r2，尚未形成正式决议**。本文整理 owner 与审核方的讨论结论，不改变任何现行 Contract、ADR 或计划；§13 的事项经 owner 决议后，才进入正式的 Phase 6 设计与执行计划。§13 中标为“owner 方向”的条目是 owner 已给出的方向，细节仍待讨论。
- 日期：r1 2026-10-17；r2 2026-10-24（P5 exit 后更新：S5 实测数据、Rust 目标与并发分层、SQL 解析器主线与差分验证、开启前问题清单）。
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

因此本稿主张：先测出各阶段的下界，再确定目标（§3），并按业务阶段逐段设计方法（§8）。

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

- **backend 计算路径没有任何并行。** 只有 worker runtime 的执行线程；Preview 的上传侧物化（`preview_jobs.py` 中按 side 的循环）、两个 pair（`_PAIR_BASELINE_TO_INITIAL`、`_PAIR_INITIAL_TO_MODIFIED`）、pair 内的比较→风险→surface 都是串行。worker 墙钟约等于 worker CPU，主机有 96 核。
- **数据在 Python 中逐行、逐单元格处理。** SQL 解析器（`capabilities/table_access/`，约 2,600 行手写字节游标）为每个单元格构造 Python 字面量对象；物化、投影、比较也是逐行 Python。
- **归因缺口：** 上表各段分开测量，粗略合计约 900 s，只有 v1 Preview operation 1,685 s 的一半左右；剩余部分（步骤之间的 artifact 写入与读回、checkpoint、序列化，或测量边界本身的差异）没有归因。Step 记录带 `started_at` / `completed_at`，可以不加插桩先得到 step 级拆分（§11 V5）。
- **Submit 与下界的差距：** 同一份 replay SQL 直接导入 Dolt 约 24 s，现有 Submit 566 s；大头在 snapshot build 与 mutation planning（plan child 231 s），不在 Dolt 写入。

真实数据的结构统计（G2 普查）：完全相同的重复行为 0；按规则键重复的行共 40,748 行，都是同键不同内容，已按 G8 用伪 gid 处理。

## 3. 目标的设定方法

### 3.1 每个阶段写四项

1. **语义上必须做的最少工作。** 例如：Preview 必须解析全部上传内容，但只需要比较有变化的表。
2. **物理下界。** 在本机实测基本操作的吞吐，据此推算这一阶段的最短时间。S5 已给出第一批数字（§2.2）；SQL 解析的下界取决于新解析器的实测（§11 V6）。
3. **旧实现的实测值。** 作为某个量级可以做到的证明。必须与 vNext 按同一口径测量（见 §3.2）；S5 未能运行旧实现，条件允许时再测，不阻塞。
4. **目标写成规模函数。** 形如 `T ≈ a × 上传字节 + b × 变化行数 + c`，而不是一个固定秒数。

退出条件：每个阶段达到下界的约定倍数以内，或者剩余差距有明确的物理原因并记录在案。业务需求可以保留，例如“2× t4 的 Preview 能交互式使用”，但具体数值在下界分析之后再定。

按 S5 的吞吐粗估（待 V5、V6 核实）：t4 的解压、哈希、Arrow IPC 读写合计在秒级；即使 SQL 解析达到每秒数十至上百 MiB，也只需数秒。Preview 的下界很可能在数十秒量级，主要由 RS 读取（现为 52 s）与比较计算决定。因此 10 分钟是宽松目标。

### 3.2 两个时间指标

- **用户可见时间：** 从受理到结果可以读取。
- **完成时间：** 包括返回之后的全部后台工作，例如缓存写入。

旧实现把 comparison cache 的补全放在返回之后的 `ASYNC_COMPARISON_CORE_CACHE_COMPLETION` 步骤里（`legacy/backend_vnext/flows/upload_preview.py`）。所以它的“60 s 返回”很可能是用户可见时间，而 vNext 现在测的是一直算到 operation 终态的时间。两者要分开比较。

### 3.3 结构性目标

**成本应当随变化量增长，而不是随基线大小增长。** 这是比任何常数级优化都更重要的一项目标：

- 内容不变的重传：成本应当接近“只解析和投影上传”；
- History：缓存命中时成本应当接近零。

建议把它写成 Phase 6 的硬性退出条件（§13 A3）。

## 4. Phase 6 与 Phase 7 的边界（建议）

| 阶段 | 原定内容 | 建议调整 |
| --- | --- | --- |
| Phase 6 | 扩大 Rust 覆盖、优化计算与数据路径 | **单个 operation 的延迟**，以 §3 的阶段目标为退出条件。手段不限，包括 operation 内部的表级与数据级并行（从 Phase 7 前移，§5），以及同一项目内按内容摘要的确定性复用 |
| Phase 7 | 并行、缓存、并发预算、背压 | **多个 operation 的吞吐与资源**：多 worker（需要重新设计启动时的租约判定，S2b 复审 R1-O2）、跨 operation 的通用缓存治理（淘汰、晋升、权威性校验）、统一并发预算、背压 |

把 operation 内并行前移的理由：worker 是单核，并行是数量级提升的直接手段之一。implementation-stages §9 的进入条件同时改写（§0 第 2 项）。

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
| Submit 复用 Preview 的产物 | Submit 的 snapshot build 与 mutation planning 能否复用 Preview 已冻结的规范表与变化集（以摘要校验）；涉及 T1 冻结对象与 ADR 0019，需单独讨论 | Submit 566 s，对比 Dolt 直接导入 24 s |
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
| mutation planning（Submit） | 变化集计算、replay SQL 渲染 | CAS 与发布语义 | 先确定能否复用 Preview 产物（§5.3） |
| 调度 | Rayon 工作池、LPT 派发 | 调度配置与并发上限 | 见 D6 与 §5.5 |

### 5.5 并发上限：固定配置的收益与风险

owner 倾向：并发上限用固定配置，仍可讨论。

| | 内容 |
| --- | --- |
| 收益 | 测量可重复、结果可比；与同机门禁和其他服务共存时不抢占；容器 CPU 配额下 `os.cpu_count()` 返回宿主核数（ct108 为 96），自动探测容易超额订阅；峰值内存可预估（并发数 × 单表峰值） |
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
Submit：只把变化表写入 Dolt（权威）；commit 成功后，相关表加正式引用
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
| ⑧ | Submit 准备与回放 | 只写变化表 | 复用 Preview 产物（§5.3，待讨论）；增量回放、批量写入；keyless 表按 DC29 整表重写；同内容表组的写入优化（D8） | **受 Dolt 写入限制**：同样数据直接导入 Dolt 实测 24 s |
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
- **Preview 同步只写小的权威事实：** 每表摘要、两侧的规范状态摘要、manifest，以及展示需要的 surface 和变化表的记录。规范表文件在返回之后异步写入，并且有上限（例如固定 1～2 个线程）。旧实现用 `max_cache_workers=2` 的线程池做同样的事。
- **Submit 的 prepare：** 优先使用已经写好、并且摘要校验通过的文件；如果文件还没写完（很快就提交了），或者已经被清理（间隔很久才提交），就从 SourcePackage 重新投影，再用 PreviewResult 中的摘要校验。这样，Preview 与 Submit 不连续的情况也能正确处理，异步写入失败只影响性能。
- **Preview 读基线时由 Dolt 兜底得到的表，** 是已经提交的内容，可以直接挂正式引用。
- **Contract 影响：** 修订 ADR 0019 与设计 §4.6 中“PreviewResult 持久化规范表集合闭包 artifact”的条款，以及 T1 冻结的对象：从“闭包 artifact”改为“摘要 + SourcePackage”。
- **比例化保障（r2 补充）：** 这是新增的持久化派生状态。按 Proportional assurance policy，需写明它对应的业务需求（容量目标）、丢失或损坏只影响性能的证明方式，以及不新增独立的状态机或证据机制。

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
- **与旧实现的区别：** 旧实现按 `canonical_artifact_ref` 把同内容的表分组，在 Dolt 中只存一张物理表、其余逻辑表映射到它（`legacy/backend_vnext/capabilities/snapshot_materialization/canonical_storage.py`）。映射跨提交演变，因此需要分岔逻辑。本设计中，分组只是第 ② 层按需推导出的事实，不存在需要拆分的持久映射。

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

### D8 Dolt 中同内容表的重复写入

块共享解决了空间问题，这一点旧实现已经测过；但每张表的行数据仍要逐行写入、建树，写入耗时无法靠块共享消除。候选做法如下，按推测收益从高到低排列，都要实测（V3）：

1. **表级复制：** Dolt 的表数据是指向内容的哈希引用，`dolt table cp` 这类操作有可能只复制引用。如果 RS 内部能用上，同组的 k 张表只需真正写入一次。
2. **服务端 `INSERT INTO b SELECT * FROM a`：** 省去传输与 SQL 解析，建树成本还在。
3. **最后手段：** 在 RS 内部做存储层去重，把旧实现的映射收在 RS 里，作为 RS 的实现细节，不进入 backend 的业务模型。

- **Contract 影响：** 第 1、2 种都需要 import 包能表达“表 B 的内容与表 A 相同”，要修订 RepositoryImportArtifact 的包格式（Repository 一侧）。
- **优先级可以靠后：** 重复写入只发生在同组表一起变化时，以及首次提交时；而且 Submit 对耗时不敏感，S5 也显示 Submit 的大头不在 Dolt 写入。先用 V4 的统计算出最坏情况，再决定是否投入。

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
- **V3 Dolt 写入实测（未做）：**
  - N 张同内容表的写入耗时，分别用逐表写入、表级复制、服务端 `INSERT ... SELECT`；
  - 同样数据直接导入 Dolt 的耗时已由 S5 给出（24 s），作为第 ⑧ 步的下界。
- **V4 同内容表组的统计（未做）：** 在普查中增加只输出计数的统计：每份数据中同内容表组的数量、组的大小、组内行数，以及 v1→v2 的分组分裂与合并。用来估算 D5 的去重收益和 D8 的最坏情况。前提：先修普查工具的 G8a-F1（未扫描却报告 ordered_projection COMPLETE）。
- **V5 operation 级耗时归因（按需补充，r2 新增）：** 先不加插桩，从 control DB 的 step `started_at` / `completed_at` 得到 t4 Preview、Submit、History 的 step 级拆分；如仍不足以解释 §2.3 的缺口，再在 t4 Preview 运行期间用 py-spy 从主机侧采样一次（DC31 已允许，不改产品代码）。需要产品插桩时另行授权。
- **V6 SQL 解析器原型（r2 新增，主线的第一步）：** 见 §6.4 第 1 项。输出：单线程与多线程吞吐、与参照实现在现有测试和 t4 上的一致性、需要澄清的语义。

## 12. 开启前需处理的遗留项

| 项 | 内容 | 建议 |
| --- | --- | --- |
| G8a-F1 普查工具误报 | `benchmarks/real_dump_census.py` 在诊断模式下未扫描也报告 ordered_projection COMPLETE | V4 前修复 |
| `uv-consume.sh` 锁快照残留 | 没有 EXIT trap，中途退出时 `mktemp` 文件留在 TMPDIR | Phase 6 kickoff 前小修 |
| SQLite 旁路文件残留 | 有测试留下 `repository-import-*.sqlite3` 的 `-shm` / `-wal` | 同上 |
| 三项文档整理 | snapshot-materialization 文档的 ADR 0019 取代提示；收口设计 DC28–DC34 索引与 DC26 表述；旧 5B/G11 deferred register 整理 | kickoff 前或首次修改相关文档时 |
| G6b 是否重新评估 | P5 exit review 认为已触及重新评估条件；终审判断未触发，维持 C | owner 决定 |
| 重要 keyless 表是否定义自然键 | 业务评估（DC29 后续，部署前） | 结论可能影响 D1、D7 对 keyless 的处理，建议在 D1 定稿前给出 |
| GitHub 默认分支 | 远程默认分支仍为 `phase1/gate-ownership-repair` | owner 在 GitHub 设置中改为 `main` |

## 13. 待 owner 决议的事项

状态说明：**待决议**＝尚无结论；**owner 方向**＝owner 已给出方向，细节待讨论；**已决议**＝已有正式决议。

### A. 目标与范围

| # | 事项 | 状态 | 审核方初步倾向 |
| --- | --- | --- | --- |
| A1 | 目标的设定方法（§3）：用“下界 + 规模函数”取代固定 10 分钟；目标按“交互可用”还是 10 分钟；用户可见时间与完成时间是否分开设目标。需要修订 DC30/DC31 | 待决议 | 采用下界方法；Preview 按用户可见时间设交互级目标，完成时间另设上限 |
| A2 | Submit 与 History 是否设目标（S5：Submit 566 s，对比 Dolt 直接导入 24 s；History 893 s） | 待决议 | History 设目标；Submit 设宽松上限 |
| A3 | “成本随变化量增长”是否作为硬性退出条件（§3.3） | 待决议 | 是 |
| A4 | Phase 6 与 Phase 7 的边界（§4），同时改写 implementation-stages §9 的进入条件（§0 第 2 项） | 待决议 | 按 §4 调整 |

### B. 需要修订 Contract 的设计决定

| # | 事项 | 状态 | 审核方初步倾向 |
| --- | --- | --- | --- |
| B1 | D1 表摘要（BLAKE3、列式编码、与行顺序无关），以及它作为单独 Contract 变更阶段、完成后重建对照基准 | 待决议 | 单独成段，在性能优化之前 |
| B2 | D2 与 D3 规范表存储：格式、两类引用、Preview 只同步写入小事实；修订 ADR 0019 与设计 §4.6，调整 T1 冻结对象；比例化保障说明 | 待决议 | 接受方向，引用生命周期与清理在设计中细化 |
| B3 | D5 第 ③ 层计算去重与规则主体 digest；“只有纯函数可以缓存”写入比较与风险 Contract | 待决议 | 接受 |
| B4 | D5 第 ② 层“分组分裂”风险信号是否在 Phase 6 范围内 | 待决议 | 拆出单独立项 |
| B5 | D7 比较列式化（以 V1 为前提）；差分测试与一致性条款作为强制要求；分歧点先写入 Contract | 待决议 | 接受，ordered 视 V1 结论 |
| B6 | D8 同内容表写入优化（依 V3、V4 决定；可能修订 RepositoryImportArtifact） | 待决议 | 靠后 |
| B7 | Submit 复用 Preview 产物（§5.3），涉及 T1 冻结对象与 ADR 0019 | 待决议 | 在 B2 的设计中一并评估 |

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
| D2 | Phase 6 测量 runbook：预热、样本数、冷/热启动、是否独占 ct108（门禁与测量共用一台机器） | 待决议 | 按 Performance Measurement §3、§4 在设计中写明 |
| D3 | Phase 6 阶段结构 | 待决议 | S0 决议 → V1/V5/V6（V3/V4 视 B6）→ 设计与执行计划 + 独立文档审核 → 解析器主线 → D1 摘要阶段 → 按业务阶段分段实施；DC30/DC33/DC34 与 G12/G13 的门禁规则沿用 |
| D4 | V2 是否并入 S5 | **已决议（2026-10-17，DC32）** | 并入 S5，已完成 |

## 14. 不在本稿范围

- 正式的 Phase 6 设计、路径预算与执行计划：本稿决议之后再写。
- 多 worker、全局并发预算与背压（Phase 7）。
- Phase 8 shadow 切换与 Phase 9 生产加固。
- “分组分裂”等新的业务风险事实（建议单独立项，§13 B4）。

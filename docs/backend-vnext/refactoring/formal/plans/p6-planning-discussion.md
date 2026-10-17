# Phase 6 规划讨论稿：按业务阶段的性能优化

- 状态：**讨论稿，尚未决议**。本文整理 owner 与审核方 2026-10-17 的讨论结论，不改变任何现行 Contract、ADR 或计划；§10 的事项经 owner 决议后，才进入正式的 Phase 6 设计与执行计划。
- 日期：2026-10-17。
- 范围：P5 收口之后的性能工作，即 [implementation-stages](implementation-stages.md) §9 Phase 6 与 §10 Phase 7。
- 关联：
  - [S0 owner 决议](p5-arch-closure-s0-owner-decisions.md) §13（DC30）、§14（DC31）；
  - [P5 收口设计](p5-arch-closure-design.md) §4.6、§5.3、§13；
  - [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)、[ADR 0004](../adr/0004-raw-source-artifact-and-canonical-dolt-storage.md)、[ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)、[ADR 0019](../adr/0019-commit-canonical-metadata-authority.md)；
  - [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)、[Performance Measurement](../contracts/performance-measurement-and-baseline.md)；
  - 现状数据：[S2b handoff](p5-arch-closure-s2b-handoff.md) §8.5–§8.6。

## 1. 背景与问题

DC31 规定：P5 只验证正确性，性能整体留给 Phase 6，Phase 6 可以按需重新设计、重写实现，约束是公共 Contract 与业务语义。DC30 给出的业务容量目标是“约 2× t4 的项目，Preview 10 分钟内完成”，DC31 把它定为 Phase 6 的退出目标。

讨论中确认了这个目标的两个问题：

1. **它比旧实现可达到的水平宽松得多。** owner 提供的信息：旧实现的 t4 Preview 约 60 s 返回前端，并且 Preview 阶段完全不访问 Dolt。vNext 当前的 t4 v1 Preview 为 2,567 s。10 分钟的目标比旧实现慢 10 倍。
2. **固定门槛对各阶段不公平。** 有的阶段很快达标就退出，其实还有很大的优化空间；有的阶段受物理限制（例如 Dolt 写入），无论怎样优化都达不到。

因此本稿主张：先测出各阶段的下界，再确定目标（§3），并按业务阶段逐段设计方法（§6）。

## 2. 现状数据

S2b 取证运行（t4，墙钟与各容器 cgroup CPU，单位秒）：

| 步骤 | 墙钟 | worker CPU | RS CPU | 说明 |
| --- | ---: | ---: | ---: | --- |
| v1 Preview | 2,567 | 2,556 | 65 | 对 INITIAL，全部表都是新增 |
| 重传 v1 Preview | 2,244 | 2,174 | 173 | 0 张表有变化 |
| v2 Preview | 2,244 | — | 172 | 311 张表中 26 张有变化；worker 的 `cpu.stat` 被重置 |
| v1 Submit | 805 | 743 | 205 | |
| v2 Submit | 815 | 748 | 226 | 只有 26 张表有变化 |
| History | 1,352 | 1,234 | 275 | |
| Repository 读取（脚本核对） | 53 | 0 | 198 | |

由此得到的观察（标“推断”的还需要 S5 的分段测量确认）：

- **worker 基本是单核在算。** 墙钟约等于 worker CPU，主机有 96 核。
- **成本不随变化量增长。** 0 张表变化的重传、26 张表变化的 v2，耗时都和全量 Preview 相当；v2 Submit 也和 v1 Submit 相当。
- **数据在 Python 里逐行处理。** 从 RS 读回数据时逐列 `to_pylist()`（`infrastructure/repository_read/http_arrow.py`）；投影（`storage_projection/project.py`）与比较（`comparison/standard.py`、`ordered.py`）都是逐行的 Python 代码。
- **推断：** History 不解析 SQL，worker CPU 仍有约 1,200 s，所以“读取快照 + 摘要 + 比较”这一段本身就很重；Preview 比 History 多出的部分主要是上传侧的解析与物化。

真实数据的结构统计（G2 普查）：完全相同的重复行为 0；按规则键重复的行共 40,748 行，都是同键不同内容，已按 G8 用伪 gid 处理。

## 3. 目标的设定方法

### 3.1 每个阶段写四项

1. **语义上必须做的最少工作。** 例如：Preview 必须解析全部上传内容，但只需要比较有变化的表。
2. **物理下界。** 在本机实测基本操作的吞吐（解压、SQL 解析、Arrow 转换、哈希、Arrow IPC 读写、RS 读取、Dolt 导入），据此推算这一阶段的最短时间。
3. **旧实现的实测值。** 作为某个量级可以做到的证明。必须与 vNext 按同一口径测量（见 §3.2）。
4. **目标写成规模函数。** 形如 `T ≈ a × 上传字节 + b × 变化行数 + c`，而不是一个固定秒数。

退出条件：每个阶段达到下界的约定倍数以内，或者剩余差距有明确的物理原因并记录在案。业务需求可以保留，例如“2× t4 的 Preview 能交互式使用”，但具体数值在下界分析之后再定。

### 3.2 两个时间指标

- **用户可见时间：** 从受理到结果可以读取。
- **完成时间：** 包括返回之后的全部后台工作，例如缓存写入。

旧实现把 comparison cache 的补全放在返回之后的 `ASYNC_COMPARISON_CORE_CACHE_COMPLETION` 步骤里（`legacy/backend_vnext/flows/upload_preview.py`）。所以它的“60 s 返回”很可能是用户可见时间，而 vNext 的 2,567 s 是一直算到 operation 终态的时间。两者要分开比较。

### 3.3 结构性目标

**成本应当随变化量增长，而不是随基线大小增长。** 这是比任何常数级优化都更重要的一项目标：
- 内容不变的重传：成本应当接近“只解析和投影上传”；
- History：缓存命中时成本应当接近零。

## 4. Phase 6 与 Phase 7 的边界（建议）

| 阶段 | 原定内容 | 建议调整 |
| --- | --- | --- |
| Phase 6 | 扩大 Rust 覆盖、优化计算与数据路径 | **单个 operation 的延迟**，以 §3 的阶段目标为退出条件。手段不限，包括 operation 内部按表并行（从 Phase 7 前移），以及同一项目内按内容摘要的确定性复用 |
| Phase 7 | 并行、缓存、并发预算、背压 | **多个 operation 的吞吐与资源**：多 worker（需要重新设计启动时的租约判定，S2b 复审 R1-O2）、跨 operation 的通用缓存治理（淘汰、晋升、权威性校验）、统一并发预算、背压 |

把按表并行前移的理由是：worker 是单核，按表并行是达成数量级提升最直接的手段。

## 5. 主线：规范表是唯一流转的数据形态

```text
上传 → 流式解析 → 一次投影 → 规范 Arrow 表 → 表摘要（BLAKE3，与行顺序无关）
     → 规范表存储（Arrow IPC，按摘要寻址；Preview 只挂临时引用）
Preview：上传侧摘要与基线 manifest 比对 → 只对变化表从存储 mmap 读取
         （缺失时由 Dolt 兜底并回填）→ 按调度分组做列式比较
Submit：只把变化表写入 Dolt（权威）；commit 成功后，相关表加正式引用
History：manifest 过滤 + 比较结果缓存 + 规范表存储
```

Dolt 始终是权威来源，规范表存储和各类缓存都是派生数据：缺失或损坏只影响性能，不改变业务事实。

## 6. 分阶段的方法

| # | 阶段 | 语义最少工作 | 主要方法 | 下界的来源 |
| --- | --- | --- | --- | --- |
| ① | 上传与 staging | 接收、限额检查、解包 | 流式解包，不重复落盘 | I/O 吞吐 |
| ② | 解析与物化 | 全量解析 SQL 与 `logics.xml` | 流式解析；mysqldump 按表分段，先按表边界切开再并行解析；直接产出列式数据，不经过逐行的 Python 对象 | 解压加解析的实测吞吐 |
| ③ | 规范投影与表摘要 | 全量（上传侧） | 列式投影；BLAKE3 表摘要（D1）；按表并行（D6） | 哈希与排序的实测吞吐 |
| ④ | 基线解析 | 只取变化表 | 用基线 commit 的 manifest 中的表摘要过滤；变化表优先从规范表存储读取（D2、D3），缺失时由 Dolt 兜底 | 与变化表的数量成正比 |
| ⑤ | 比较、风险与 surface | 只处理变化表 | 列式比较（D7）；计算去重（D5）；按调度分组并行（D6） | 与变化行数成正比 |
| ⑥ | 发布 Preview | 写入用户需要的结果 | 只同步写入小的权威事实，大文件异步写入（D3） | 小 |
| ⑦ | Submit 受理 | 比对摘要 | 现状已经很便宜 | 毫秒级 |
| ⑧ | Submit 准备与回放 | 只写变化表 | 增量回放、批量写入；keyless 表按 DC29 整表重写；同内容表组的写入优化（D8） | **受 Dolt 写入限制**：以同样数据直接导入 Dolt 的实测时间为下界 |
| ⑨ | History 比较 | 只处理变化表 | manifest 过滤 + 比较结果缓存 + 规范表存储 | 缓存命中时接近零 |

第 ⑧ 步最可能受物理限制，因为 Dolt 的写入和提交不受我们控制。它单独定目标，不和 Preview 共用一个门槛。按 owner 的判断，Submit 是用户可以离开的异步过程，对耗时不敏感。

## 7. 设计决定（讨论结论，待决议）

### D1 只保留一个表摘要，它就是权威摘要

- 不设快速哈希和权威哈希两层。摘要只有一个，同时用作 manifest 内容摘要、`NO_CANONICAL_CHANGE` 的输入，以及规范表存储的内容地址。
- **哈希函数用 BLAKE3：** 它是密码学哈希，单核可达 GB/s 级。摘要同时是缓存的内容地址，一旦碰撞，会读到错误的缓存、静默得出错误结果，所以不采用非密码学哈希。
- **编码改为列式二进制，不再逐行做 JCS 编码。** 现在慢主要慢在编码和逐行处理，而不是哈希函数本身。
- **与行顺序无关：** 按规范键排序后计算，但先检查是否已经有序，有序就不排。常见情况下 dump 顺序就是主键顺序，检查是 O(n)。keyless 表按行摘要排序，计算多重集合摘要，保留重复行（DC29）。
- **不按源顺序计算的理由：**
  - 省下的时间很少；
  - Dolt 按主键顺序返回数据，摘要与顺序无关，才能从 Dolt 读回后重算出同一个摘要，用来回填或校验缓存；
  - 摘要在 Preview 时算出，PreviewResult 的规范状态摘要、`NO_CANONICAL_CHANGE` 与陈旧判定的语义（设计 §5.3、ADR 0019）都不用变。
- **Contract 影响：** 修订 Canonical Storage 中内容摘要与行编码的定义。按 DC6，直接改到目标形态。

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
- **与旧实现的区别：** 旧实现按 `canonical_artifact_ref` 把同内容的表分组，在 Dolt 中只存一张物理表、其余逻辑表映射到它（`legacy/backend_vnext/capabilities/snapshot_materialization/canonical_storage.py`）。映射跨提交演变，因此需要分岔逻辑。本设计中，分组只是第 ② 层按需推导出的事实，不存在需要拆分的持久映射。

### D6 表级计算调度：按特征建模，配置独立于 ruleset

- **策略：**
  - 低于阈值的小表，在进程内串行成批处理；
  - 重表进入一个有上限的工作池，按预估成本从大到小派发（LPT），并发数用固定配置，不按 CPU 数量自动放大；
  - 结果按规范表顺序合并，保证并行与串行得到相同的摘要。
- **成本模型：** 输入是比较角色（ORDERED 的权重远高于 STANDARD）、实际行数、列宽、是否产出行级记录，例如 `成本 ≈ 角色权重 × 行数 + 列宽项`。**不维护重表名单。** 系数由 S5 的逐表实测校准（V2）；新实现完成后，相对成本会变（例如 ordered 改用 Rust 以后），要重新校准。旧实现的逐表统计已经不存在，不作为输入。
- **调度信息不放进 ruleset：** ruleset digest 参与比较语义（DC10、DC24），把性能信息写进去，调一次参数就会让已有 Preview 判为陈旧、缓存失效。能从现有规则推导的特征（例如 ORDERED 角色）直接推导；需要额外标注的内容放在独立的性能配置中，不参与任何 digest。
- **并行机制：** 首选在 Rust 中用 Rayon，不受 GIL 限制。在 Python 中用多进程时，D2 的内存映射文件让进程之间只传路径、不传数据。Python 3.14 的 free-threaded 构建可以作为备选，前提是依赖支持。
- Phase 7 引入全局并发预算后，单个 operation 的工作池要服从这个预算。

### D7 比较改为列式实现，Python 实现降为参照实现

| 比较类型 | 实现方式 | 可行性 |
| --- | --- | --- |
| standard（按键对齐） | 按键列做哈希连接，比较行摘要列，分出新增、删除、修改；只对修改行逐列比较。用 Polars 或 Rust | 天然适合列式 |
| ordered（IEC104：位置列、稳定键、空白行、移动、区间、G8b 骨架） | 带规则的序列算法，难以向量化；在 Rust 中直接在 Arrow 数组上写循环 | 可行，前提是规则写成精确规格 |
| keyless（多重集合差异） | 先按行摘要排序，再做多重集合合并 | 简单 |

- **一致性保证：**
  - 现有 Python 实现作为参照实现（ADR 0001）。implementation-stages §9 已有的退出条件继续适用：facts、records、排序与 digest 一致，并且可以用 feature flag 退回参照实现；
  - 差分测试的三层输入：现有 golden；用 Hypothesis 生成的随机表对；真实数据 t1–t4 逐表比对 facts 与 records 的摘要，再加上 DC31 的公开对照基准；
  - 先把容易产生分歧的地方写进 Contract：浮点数（-0.0 的归一已有）、NULL 语义、字符串按字节排序而不按 locale、记录的输出顺序、ordered 的并列规则（G8b-F2 保留的规则）。
- 仓库中已有 Rust 与 PyO3 的基础：`vnext/rust/gateway-compute-python`。
- 列式化是否作为 Phase 6 的主线，由 V1 的结论决定。

### D8 Dolt 中同内容表的重复写入

块共享解决了空间问题，这一点旧实现已经测过；但每张表的行数据仍要逐行写入、建树，写入耗时无法靠块共享消除。候选做法如下，按推测收益从高到低排列，都要实测（V3）：

1. **表级复制：** Dolt 的表数据是指向内容的哈希引用，`dolt table cp` 这类操作有可能只复制引用。如果 RS 内部能用上，同组的 k 张表只需真正写入一次。
2. **服务端 `INSERT INTO b SELECT * FROM a`：** 省去传输与 SQL 解析，建树成本还在。
3. **最后手段：** 在 RS 内部做存储层去重，把旧实现的映射收在 RS 里，作为 RS 的实现细节，不进入 backend 的业务模型。

- **Contract 影响：** 第 1、2 种都需要 import 包能表达“表 B 的内容与表 A 相同”，要修订 RepositoryImportArtifact 的包格式（Repository 一侧）。
- **优先级可以靠后：** 重复写入只发生在同组表一起变化时，以及首次提交时；而且 Submit 对耗时不敏感。先用 V4 的统计算出最坏情况，再决定是否投入。

## 8. 旧实现：可以参考的与需要重新设计的

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

## 9. 前置验证任务

这四项在正式的 Phase 6 设计之前完成，用来确定方案和排序：

- **V1 ordered 比较的小规模验证。** 用 Rust 在 Arrow 数组上实现一个 IEC104 ordered 系列的比较，在 t4 的同类表上与 Python 参照实现做差分测试，并测加速比。输出：一致性结论、加速比、规格中需要澄清的地方。它决定 D7 能否作为主线。
- **V2 S5 测量的扩展**（需要修订 S5 的范围，见 §10 第 7 项）：
  - 逐表、逐步骤的墙钟与线程 CPU，并区分变化表与不变表；
  - 基本操作的吞吐基准：解压、SQL 解析、Arrow 转换、BLAKE3、Arrow IPC 读写、RS 读取、Dolt 原生导入；
  - 用户可见时间与完成时间分开记录；如果条件允许，按同一口径测一次旧实现的 t4 Preview。
  - 输出只含表名与数字。
- **V3 Dolt 写入实测：**
  - N 张同内容表的写入耗时，分别用逐表写入、表级复制、服务端 `INSERT ... SELECT`；
  - 同样数据直接导入 Dolt 的耗时，作为第 ⑧ 步的下界。
- **V4 同内容表组的统计：** 在普查中增加只输出计数的统计：每份数据中同内容表组的数量、组的大小、组内行数，以及 v1→v2 的分组分裂与合并。用来估算 D5 的去重收益和 D8 的最坏情况。

## 10. 待 owner 决议的事项

1. **目标的设定方法（§3）：** 用“下界 + 规模函数”取代固定门槛；需要修订 DC30/DC31 中的容量目标条款。
2. **Phase 6 与 Phase 7 的边界（§4）：** 需要修订 implementation-stages §9、§10。
3. **D1 表摘要：** BLAKE3、列式编码、与行顺序无关；修订 Canonical Storage。
4. **D2 与 D3：** 规范表存储的格式、两类引用；Preview 只同步写入小事实，大文件异步写入；修订 ADR 0019 与设计 §4.6，调整 T1 冻结的对象。
5. **D5：** 三层分离与规则主体 digest；“只有纯函数可以缓存”写入比较与风险能力的 Contract；分组变化作为第 ② 层的业务事实。
6. **D6：** 调度配置独立于 ruleset。
7. **V2 是否并入 S5：** 设计 §13 原定只测一条链路，V2 要求按阶段分段并测基本操作吞吐，需要修订 S5 的范围。
8. **D7：** 比较列式化以 V1 为前提；差分测试与一致性条款作为 Phase 6 的强制要求。
9. **D8：** 根据 V3、V4 的结果决定是否投入；如果投入，涉及 RepositoryImportArtifact 包格式的修订。
10. **Submit 与 History 是否设目标：** 现有容量目标只规定了 Preview。

## 11. 不在本稿范围

- 正式的 Phase 6 设计、路径预算与执行计划：本稿决议之后再写。
- P5 的剩余阶段（S3–S5）：按现行计划进行，不受本稿影响。S5 的范围是否调整，见 §10 第 7 项。
- 多 worker、全局并发预算与背压（Phase 7）。
- Phase 8 shadow 切换与 Phase 9 生产加固。

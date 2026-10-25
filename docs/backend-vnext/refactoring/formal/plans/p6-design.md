# Phase 6 详细设计：单任务性能与 Rust 接入

状态：**DRAFT r1 — 待独立文档审核；实现未授权**

日期：2026-10-26（r1）

Owner：Backend vNext Architecture（Phase 6 牵头）；各项语义归属见 §14

入口：[S0 Owner 决议记录](p6-s0-owner-decisions.md)（DC37–DC54）→ 本文 → [执行计划](p6-execution-plan.md)

依据：[Phase 6 规划讨论稿](p6-planning-discussion.md) r28（分析过程与数据）；前置验证报告
[V5](p6-v5-attribution-report.md)、[V5b](p6-v5b-segment-report.md)、[V6](p6-v6-parser-prototype-report.md)、
[V7](p6-v7-dolt-report.md)、[V8](p6-v8-gate-profile.md)、[V1](p6-v1-ordered-prototype-report.md)；
[implementation-stages](implementation-stages.md) §9、§10（已按 DC37 改写）；P5 的 DC35（目标设定方法）与 DC36（测试节点分工）见
[P5 S0 Owner 决议记录](p5-arch-closure-s0-owner-decisions.md) §18、§19。

上游 Contract 与 ADR：
[Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)、
[Storage Mutation](../contracts/storage-mutation-and-change-set.md)、
[Shared Canonical Encoding](../contracts/shared-canonical-encoding.md)、
[Performance Measurement](../contracts/performance-measurement-and-baseline.md)、
[Repository Service](../contracts/repository-service.md)、
[Comparison](../../../contracts/comparison.md)、[Ordered Diff](../../../contracts/ordered-diff.md)、
[Risk](../../../contracts/risk.md)、[Comparison Surface](../../../contracts/comparison-surface.md)、
[Comparison Bundle](../../../contracts/comparison-bundle.md)；
ADR [0001](../adr/0001-python-rust-hybrid-compute-strategy.md)、[0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)、
[0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)、[0014](../adr/0014-adaptive-patch-and-target-neutral-change-set.md)、
[0019](../adr/0019-commit-canonical-metadata-authority.md)；
[Rust safety and performance policy](../policies/rust-safety-and-performance-policy.md)、
[Proportional assurance policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)。

标记：**E** = 已实现或已实测的事实（源码 @ `e6e3460d9c`）；**D** = 已决议（DCxx）；**P** = 本设计提案，须经审核与 owner 确认。

## 1. 目标、决定与非目标

### 1.1 目标（D）

- **单个 operation 的延迟**达到已决议的门槛（DC35、DC38、DC53），参考环境 `ct108-gw-dms`，规模 2× t4，单任务资源上限 N、M 下判定：

  | 负载 | 门槛 |
  | --- | --- |
  | W1 首次上传（空基线） | ≤ 3 min |
  | W2 原样重传（0 张表变化） | ≤ 30 s |
  | W3 少量变化（约 10% 的表） | ≤ 60 s |
  | W4 几乎全变（全部表、每表约 10% 行变化） | ≤ 3 min |
  | H1 / H2 / H3（History 相邻首查 / 冷查询 / 重复查询） | ≤ 60 s / ≤ 5 min（S5 定稿） / ≤ 15 s |
  | S1、S4 / S3（Submit 首次与几乎全变 / 少量变化，完成时间） | ≤ 5 min / ≤ 2 min |
  | 所有 operation 的完成时间 | ≤ 10 min |

- **结构性条件：** 成本随变化量增长，用确定性计数断言证明（§16.2）。
- **Rust 首次进入生产链路**（DC37）：上传侧解析、物化检查、投影与摘要，比较（含 ordered）与逐行记录，Submit 的存储 diff 与 SQL 渲染。
- **业务缺口修正**（Contract 阶段，不计入性能收益）：只增列的 schema 变化（DC40）、bundle 补齐整表（DC41）、慢速上传（DC49）、参照解析器的输入边界缺陷（DC50）。

### 1.2 决定索引（D）

DC37 边界与 feature flag；DC38 Submit 与 History 目标；DC39 表摘要保值统一与结构性过滤；DC40 只增列；DC41 bundle 整表与整表浏览；DC42 规范表存储；
DC43 计算去重与跨操作缓存；DC44 比较列式化（ordered 一并进入 Rust）；DC45 Submit 只写变化；DC46 解析器主线与数据路径合并；DC47 Rust 范围、并发与技术栈；
DC48 Rust 测试入门禁（已实施）；DC49 慢速上传；DC50 阶段结构；DC51 门禁 worktree 保留；DC52 旧扩展过时；DC53 W1–W4 定稿；DC54 逐行记录进入 Rust。

### 1.3 非目标（D）

- 多个 operation 的并发、排队、多 worker、跨 operation 的 RS 资源分配、按容量淘汰（Phase 7，DC37）。
- “分组分裂”风险信号（DC43 第 5 项）；Dolt 同内容表写入优化（DC45 第 8 项）；外部分区库（DC45 第 5 项，只预留）。
- 产品插桩：除非 S1a 的归因（§4.4）仍无法解释残差并由 owner 另行决定。
- 测试基础设施阶段：S2b 之后按 V8 方法重新剖析再决定（DC48 第 3 项）。
- 跨节点拆分门禁、AGENTS 与 testing-conventions 的规则变化（归负责 DC36 的会话）。

## 2. 当前事实（E）

### 2.1 耗时结构（t4，S5 与 V5/V5b）

| operation | 现在 | 主要构成 |
| --- | ---: | --- |
| v1 Preview | 1,675 s | `materialize_inputs` 931 s（解析 140、业务物化 209、投影与摘要 217、规范 artifact 写入 163）；`assemble_preview` 724 s（逐行 records closure 生成 318、回读 95、比较 149、风险 37） |
| 重传 / v2 Preview | 约 1,450 s | 上传侧同上；**基线 commit 全量物化约 293 s**；`assemble_preview` 约 140 s（比较约 40 s，主要是 ordered 表从不提前退出） |
| v1 / v2 Submit | 约 570 s | `prepare_import` 477 s（全量逐行变化集构造 231 s、冻结规范表读取与解码 66 s 等）；RS 导入约 70 s |
| History | 884 s | `materialize_inputs` 731 s（两个 commit 全量物化）；`assemble_comparison` 144 s |
| 每个 operation 的 step 间隔 | 9–26 s | worker 空闲轮询为 1 s，不能解释（V5） |
| 未归因的 worker step 残差 | 约 210 s | 基线物化约 75 s、assemble 固定约 100 s、Submit prepare 约 36 s（V5b） |

### 2.2 代码事实

1. **Submit 每次重写全部表**：`capabilities/mutation_planning/import_replay.py` 以 `REBUILD_ALWAYS`、空的“变化前”规划，schema SQL 为每张表 `DROP` + `CREATE`（`storage_projection/import_replay.py`），与 Storage Mutation §2 不符。RS 在从 expected parent 建立的私有 ref 上回放并做 STRUCTURAL 校验，已支持只写变化（DC45）。
2. **Preview 全量物化基线 commit**：`application/preview_jobs.py` 的 `_materialize_baseline` 经 `materialize_repository_ref` 读出并物化全部表。
3. **ordered 表从不提前退出**：`comparison/standard.py` 在提前退出判断之前把 ordered 表交给 `compare_ordered_task`。
4. **manifest 内容摘要依赖源顺序**，不能在 Dolt 读回后重算；`raw_content_digest` 已与行顺序无关（DC39）。`ordering_digest` 只在 storage_projection 内部用于自校验与写入 manifest，无外部使用方；`fast_row_digest` 计入 snapshot digest。
5. **标准模式 bundle 不含整表数据**：`application/pair_pipeline.py` 只在 DATASET_REPLACEMENT 模式下传入表 ref（DC41）。
6. **逐行记录在 Python 中逐条构造**：`comparison/artifacts.py` 每条记录构造 dict、做 JCS 编码、`from_pylist` 写 Parquet、写后整份解码重算摘要（DC54）。
7. **上传**：固定 60 s 总时限（`application/workspace/upload_limits.py`，超时返回 413）；受理在事件循环上同步解压校验（`http/orchestration/multipart_upload.py`）（DC49）。
8. **参照解析器的输入边界缺陷**：BIT 负数、超宽 BIT、非 ASCII 的 `b'..'`、深层嵌套 JSON 抛出未捕获的异常越过 `parse_sql`；FLOAT 两次舍入（V6）。
9. **RS 逐表读取许可池容量 8**，超出以 503 立即拒绝（`versioned_read/http_service.py`）；读取期间累积 defunct `dolt` 进程（V7，未确认根因）。
10. **Rust**：V6（`gateway-compute-core/src/table_access/`）与 V1（`src/comparison/ordered.rs`）原型已合入，未接入生产；旧扩展 `gateway-compute-python` 与 `canonical_row_hash` 生产中不可达（DC52）。权威 runner 已含 `rust` 包并强制重装扩展（DC48）。

### 2.3 原型实测（E）

| 原型 | 一致性 | 性能（ct108） |
| --- | --- | --- |
| V6 解析器 | 语料 118 例、t1–t4 两版 3,389 万个值，差异 0；1–32 线程逐字节相同 | 2× t4 单线程 1.25 s（约 121 MiB/s），N=4 时 0.48 s；峰值内存为输入 3.8–5.0 倍 |
| V1 ordered 比较 | t1–t4 的 58 张变化表、11,698 条记录、合成 30 例与随机 96 例，差异 0 | t4 变化 ordered 表单线程 2.64 s（参照 32.6 s）；10 万行近乎全量重排近似线性 |
| V7 Dolt | 三种回放的 312 张表哈希一致 | 逐行修改约 9 ms/条语句、整表重建约 0.11 ms/行；RS 8 并发读一个 t4 commit 约 27 s |

## 3. 目标结构

```text
上传（流式接收，空闲超时）→ 受理（线程池）
  → Rust：扫描与解析 → 业务列与检查 → 规范投影 → 表摘要（SHA-256 现值）
    → Arrow / IPC 字节 →（Python）ArtifactStore 写入规范表存储（按内容寻址）
  → manifest（每表摘要）
Preview：与基线 commit manifest 逐表比对 → 只对变化表从存储 mmap 读基线（Dolt 兜底）
       → Rust 比较（standard / keyless / ordered）+ 逐行记录 Arrow 与 content_digest
       → 风险（Python）→ surface → bundle（全部表 Parquet，导出缓存）
Submit：T1 冻结 → prepare：与 parent manifest 比对 → 跳过 / 行级修改 / 整表重建
       → Rust 直接从冻结规范表渲染 replay.sql → RS 导入（包格式不变）
History：按表拼接：摘要相同即未变化 → diff/risk 缓存 → 表缓存 → Dolt（并发 ≤ RS 容量）
```

Dolt 始终是权威来源；规范表存储、diff/risk 缓存与导出缓存都是派生数据，缺失或损坏只影响性能（DC42、DC43）。

模块与语言分工按 DC47 第 1 项与讨论稿 §5.4：数据密集计算在 `gateway-compute-core`（按 capability 分模块）中，经 PyO3 adapter 以 Arrow 进、Arrow 出的粗粒度调用接入；Python 保留 domain、application、Operation Runtime、规则解析、风险规则与业务 policy；Rust core 不读写文件。

## 4. S1a：摘要与存储 Contract

### 4.1 表摘要保值统一（DC39）

- **定义（D）：** 每表唯一的表摘要 = 现有 `raw_content_digest`（每行 domain-separated SHA-256，列按名称排序编码，按多重集合合并），与行顺序无关，Dolt 读回能重算出同一个值。
- **manifest（D）：** `CanonicalizationManifestTable` 的内容摘要字段改为该值；`STORAGE_PROJECTION_VERSION` 从 `"2"` 升到 `"3"`（`capabilities/table_rules/contracts.py`）。投影版本不同的 parent 一律按“全部变化”处理；不做兼容，本地 control DB 与 Dolt 测试数据重建（AGENTS 项目前提）。
- **ordered 的统一口径（P）：** 表摘要覆盖全部规范列（含 `no` 与伪 gid），顺序变化即内容变化。`ordering_digest` 删除：它只在 storage_projection 内部使用（§2.2 第 4 项），统一摘要已覆盖顺序。比较 facts 中的 `before/current_ordered_digest` 属于 ordered-diff 契约的逻辑摘要，改为由表摘要或 manifest 提供并去掉表名（DC39 第 3 项）。
- **`fast_row_digest`（P）：** S1a 保留，snapshot digest 因此不变（DC39 第 5 项）；S2b 由 Rust 一并计算，是否删除留到 S2b 设计复核。
- **去掉重复计算（D）：** 投影时同一份数据不再编码 3–4 次；摘要只算一遍。
- **commit 元数据（D）：** `CommitCanonicalMetadataPort` 返回的 manifest 即带每表摘要，作为结构性过滤的输入（ADR 0019 的端口形态不变，语义说明补充）。
- **不变量：** 规范状态摘要、snapshot 与 bundle digest、HTTP DTO、真实数据的规范状态摘要基准都不变；变化的是 manifest digest 及其在 PreviewResult、Submission 记录与 checkpoint 中的值。

### 4.2 Preview 与 History 的结构性过滤（DC39）

- Preview 读取基线 commit 的 manifest，逐表比对：表摘要、schema digest、存储视图与投影版本都相同，判为未变化，**不读基线行、不做比较**（含 ordered）。facts 由 manifest 生成（行数、`UNCHANGED`），ordered 的逻辑摘要取自表摘要。
- 只对变化表与删除表读取基线：S1a 中经 RS 逐表读取（规范表存储在 S2b 才有）；并发不超过 RS 容量（DC47 第 6 项，S1a 可先顺序读取）。
- History 的两个节点同样按 manifest 过滤；未变化的表不比较。整表数据的读取随 DC41 的打包需要进行（§5.2）。
- **计数断言：** 基线读取的表数 = 变化表数 + 删除表数；比较调用次数 = 变化表数。

### 4.3 Submit 只写变化：表级跳过与阈值行级修改（DC45 的 S1a 部分）

- **表级跳过：** prepare 取 T1 冻结的上传侧 manifest 与 expected parent 的 manifest 逐表比较；相同的表不进入 `replay.sql`；删除的表照旧 `DROP`；parent 为 INITIAL、缺少 metadata 或投影版本不同时全部按变化处理；包 manifest 仍列出全部表（RS STRUCTURAL 校验整个 catalog）。
- **行级修改：** 生产 policy 改为 `ADAPTIVE_PATCH`；资格按 Storage Mutation §3 修订：keyed 表与有序表（GID_NO_V1，以 `gid` 为存储键、`no` 为普通列）可行级修改；keyless 表与 schema 变化的表整表重建；阈值 **1,000 行 / 1%**（DC45 第 2 项）。
- **基线行：** 变化表的 parent 行经 RS 读取（S1a）；S2b 起优先读规范表存储。
- **实现：** S1a 用现有 Python 规划器与渲染器（`capabilities/mutation_planning/`）；导入路径不再构造与变化无关的表的变化集。逐行变化集对象与无消费方摘要的去除、渲染直通在 S4。
- **checkpoint 与 T1：** T1 冻结的 `builder_mutation_policy` 改为 `ADAPTIVE_PATCH`；prepare checkpoint 增加 parent manifest digest 的绑定，恢复时核对。
- **阈值复测：** S1a 用实际渲染器与 RS 回放路径，对 t4 v2 的变化表实测逐行与重建的耗时，确认 1% 不比重建慢；S4 定稿。
- **计数断言：** `replay.sql` 涉及的表数 = 变化表数；行级语句数 = 行级修改表的变化行数。
- **验证：** 新旧路径在 t4 v2 上得到的 Dolt 表哈希相同（V7 已在一次性回放中证明，S1a 用产品路径复核一次）。

### 4.4 worker step 归因（DC53 第 2 项）

S1a 退出前，在 ct108 上对 S1a 候选 HEAD 运行 t4 完整旅程（同 V5 的方法），并用 V5b 的测量工具补测，回答：

1. 每个 Preview 两处 step 间隔（各 7–10 s）的来源：step 发布、checkpoint、租约、领取路径中的哪一段；
2. 基线物化约 75 s、assemble 约 100 s、Submit prepare 约 36 s 残差的来源。

结论写入 S1a handoff。仍无法归因时停止，由 owner 决定是否增加产品插桩（§17）。

### 4.5 S1a 的 Contract 修订

| 文档 | 修订 |
| --- | --- |
| Canonical Storage §4 | 内容摘要定义改为与行顺序无关的统一表摘要；删除“producer 不得自行排序”的约束中与摘要冲突的部分；删除 `ordering_digest`；投影版本 3 |
| Canonical Storage §6.1 | `replay.sql` 为相对 expected parent 的确定性 replay，未变化表不出现 |
| Storage Mutation §2/§3；ADR 0014 | 生产默认 `ADAPTIVE_PATCH`；有序表资格；阈值 1,000 行 / 1% |
| ADR 0019 | commit 元数据的 manifest 每表摘要作为结构性过滤的输入（说明补充，端口不变） |
| Ordered Diff | 伪 gid 范围以 Canonical Storage G8（4,000,000,000–4,294,967,295）为准 |
| golden | storage-projection、mutation 两组；包 golden |

## 5. S1b：业务语义 Contract

### 5.1 只增列的 schema 变化（DC40）

- 比较为两侧都存在的表计算 schema 演进分类 `NONE | COLUMNS_ADDED | COLUMNS_REMOVED | INCOMPATIBLE`，作为 facts 的稳定字段（`ComparisonSchemaChanges` 增加分类）。
- `COLUMNS_ADDED`（含 ENUM 只增标签、SET 只增成员，标签位置不限）：按共有列判定变化与风险，表状态不因新增列变为 `SCHEMA_CHANGED`，不降级；不产生 `SCHEMA_CHANGE` 风险；Submission 与 History 结果不列出新增列。
- `COLUMNS_REMOVED`：保持现行（`SCHEMA_CHANGED`，`MEDIUM_HIGH`）。
- 只增列改变规范状态，`NO_CANONICAL_CHANGE` 不成立，提交仍生成版本；Preview 不提示。写入 Comparison Contract。
- 触发事件只预留（分类作为 facts 字段），不建事件机制。

### 5.2 bundle 补齐整表数据（DC41）

- Preview 的 bundle 包含上传侧全部表与删除表的基线侧数据；History 每个节点包含全部表；同内容的表按内容地址共享（`shared/snapshot-tables/`）。
- 表文件为 Parquet；**导出缓存**以“表摘要 + Parquet writer 版本”为键，条目经现有保护表登记引用、按 TTL 管理（ADR 0012）；未命中时从规范表读取并导出、回填。
- S1b 中规范表来自现有 snapshot artifact 与 Dolt 读取；S2b 起来自规范表存储。
- 设计须避免整表反复读取与校验（V5b 中 assemble 有约 100 s 未归因的固定开销，§4.4 归因）。
- 修订 Comparison Bundle 契约：跨 operation 的 snapshot Parquet cache 改为按表摘要命中。

### 5.3 整表新增或删除改为整表浏览（DC41 第 3 项）

- 表状态仍为 `ADDED_TABLE` / `DELETED_TABLE`；不产出逐行记录；风险为一条表级标注，证据带行数（`TABLE_ADDED` / `TABLE_DELETED` 规则加计数）。
- surface 映射为整表浏览：新增表浏览 `current_table_ref`，删除表浏览 `before_table_ref`；前端表浏览须能显示表级风险。
- 依赖 §5.2，同一阶段落地。

### 5.4 慢速上传（DC49）

- 上传改为**空闲超时**（连续 60 s 没有收到数据）加**总上限**（最大压缩包 ÷ 1 Mbps，256 MiB 约 36 min），常量仍在 `application/workspace/upload_limits.py`，总上限由最大包推出。
- 超时使用独立的错误码（P：`UPLOAD_STREAM_TIMEOUT`，HTTP 408），不再返回 413；修订 P5-5A 上传设计中的错误码表。
- 受理中的同步工作（解压校验、artifact 写入、control DB 事务）移到线程池（`anyio.to_thread` 或等价），不阻塞事件循环。

### 5.5 参照解析器的缺陷与语义定稿（DC50 S1b）

| 项 | 处理（P，S1b kickoff 时由 owner 逐项确认） |
| --- | --- |
| BIT 负数、超宽 BIT、非 ASCII `b'..'`、深层嵌套 JSON 的未捕获异常 | 修复为确定的诊断（`SQL_VALUE_ILLEGAL` 或 `MALFORMED_SQL`，与 V6 原型一致），补 golden |
| FLOAT 两次舍入 | 按 Shared Canonical Encoding 直接舍入到 binary32 |
| BIT 列的十进制数字字面量 | 按 MySQL 以十进制解释 |
| `_binary` 前缀 | 接受，按二进制值解析 |
| 零日期、零日期时间 | 接受，保留规范文本；规范形与 Arrow 映射增加对应类别 |
| `\%`、`\_` 转义 | 按 MySQL 保留反斜杠 |
| 列类型中夹注释 | 忽略注释 |
| JSON 接受 `NaN` / `Infinity` | 拒绝（与 MySQL 一致） |

语义改动在 S1b 定稿，S2a 不同时改语义和换实现（讨论稿 §6.3）。真实数据 t1–t4 中均无受影响的值。

### 5.6 测量负载

- 合成 2× t4：复制 t4 的表并加后缀、扰动内容，避免同内容去重收益虚高（DC35 第 7 项）。
- W4：在已有基线上全部表变化，每表约 10% 行变化（插入、删除、修改混合，ordered 表含位移）；压力档每表 100% 行变化，只报告（DC53 第 3 项）。
- 规则写入测量 runbook（`vnext/backend/benchmarks/` 下的生成工具，Git 中只出现表名与计数）。
- t3 即原 testdata1，作为 schema 演进样本（DC40 第 7 项）。

### 5.7 S1b 的 Contract 修订

Comparison（schema 演进分类、只增列、整表新增/删除、`NO_CANONICAL_CHANGE` 说明）、Risk（表级计数风险、只增列无风险）、Comparison Surface（整表浏览映射）、Comparison Bundle（整表打包、导出缓存）、P5-5A 上传设计（错误码与时限）、Snapshot Table Access 与 Shared Canonical Encoding 的解析语义说明（§5.5）；相应 golden。

## 6. 重建对照基准

S1b 合入后，用 Python 实现在 `ct108-gw-dms` 上独占测量 t1–t4（含 t3 即 testdata1）与合成 2× t4 的 W1–W4、H1–H3、S1–S4，1 次预热加 3 次测量取中位数，记录墙钟、CPU、峰值并行核数、峰值内存、临时磁盘高水位与计数断言。之后各阶段只核对结果与该基准一致，不再重建（DC50）。

## 7. S2a：SQL 解析器

- **范围：** 在 V6 原型（`gateway-compute-core/src/table_access/`）基础上补齐：完整诊断（消息文本、同一张表多处错误、行预算按元组计数的偏移）、第 ③ 层负例与预算语料、第 ② 层 Hypothesis 差分、现有解析器测试改为双实现参数化（讨论稿 §6.3）；`Utf8`/`Binary` 超过 2 GiB 时改用 large 变体或分批输出。
- **PyO3 adapter（新）：** 长调用 `py.detach`；取消标志与截止时间接到 `ParserRuntime`；输出经 Arrow C Stream 交给 Python；panic 在 core 入口与 adapter 两层转为诊断。线程池改为 worker 级共享（DC47 第 5 项），不再用解析器专用池。
- **接入：** 放在 feature flag 之后，只用于差分，不切生产。
- **旧扩展删除（DC52）：** 删除 `capabilities/canonical_row_hash`、core 中的旧 pipeline、旧 adapter 入口、`canonical-row-hash` golden、Canonical Row Hash Compute Boundary Contract、`native_kernel_component.sh` 及引用它们的测试与架构基线条目；`rust` 包去掉对旧 crate 的 `cargo test` 排除；backend Dockerfile 的 maturin 构建改为新 adapter。
- **验收：** 五层语料全部通过，t1–t4 逐值差异 0，并行确定。

## 8. S2b：上传侧数据路径与规范表存储

### 8.1 数据路径合并（DC46）

- 解析 → 业务列与检查（伪 gid 范围、重复有效键、keyless 降级）→ 规范投影（保留列、规范键、ordered 的 gid/no 校验与伪 gid）→ 表摘要（含 `raw_content_digest`、`fast_row_digest`）在 Rust 中依次完成，数据始终是 Arrow；三个 capability 各自拥有语义与诊断，模块依赖不变。
- composite signal 留在 Python：在 Arrow 上先按特殊设备过滤 `device` 与 5 张特殊点表，只把命中行转成 Python。
- Rust 输出规范表的 IPC 字节，由 Python ArtifactStore 写入（Rust safety policy §4）。
- 上传侧原始表不再写 Parquet：设计核对项——逐一确认原始表在 checkpoint 恢复之外没有使用方；物化 step 崩溃后从 SourcePackage 重算。
- **Arrow 列映射 v1（P，依 V6 建议）：** 整数 `Int64`/`UInt64`、布尔 `Boolean`、浮点 `Float32`/`Float64`（-0 归一）、二进制 `Binary`、BIT `FixedSizeBinary(⌈n/8⌉)`，DECIMAL、日期时间、ENUM、SET、JSON、字符串用 `Utf8` 规范文本；映射单独加版本号并进入规范表存储的内容地址；表摘要按规范标量编码计算，与 Arrow 物理类型无关。

### 8.2 规范表存储（DC42）

- **内容地址：** storage projection version、business schema digest、行数、表摘要、Arrow 映射版本；不含表名。文件内按规范顺序存放（keyed 按键、ordered 按 gid、keyless 按行哈希）。
- **格式：** 不压缩的 Arrow IPC，mmap 读取；读取时校验 raw SHA-256，不符按缺失处理，从 Dolt 读取并重写；写入用临时文件加原子 rename，删除写后回读。
- **引用（现有保护表 `artifact_protection_intents`）：** 临时引用即 Preview owner（T1 转移规则不变）；新增 owner 类型“项目当前 BaselineHead”，Submit finalize 在移动 head 的同一事务中把引用移到新 head；释放后按 TTL 保留，TTL 从最后一次引用起算；复用时先登记保护再确认文件存在。
- **同步写入：** Preview 中同步写入；T1 照旧冻结 MODIFIED 侧闭包与 manifest，闭包条目指向内容寻址的文件（ADR 0019、设计 §4.6 结构不变）。
- **基线读取：** Preview、Submit 与 History 优先从存储 mmap 读取，未命中由 Dolt 兜底并回填。
- **磁盘估算（设计核对项）：** 每个项目的 head 体积加 Preview TTL 副本；参考节点磁盘容量；超出预算时评估 LZ4。
- **比例化保障：** 不新增状态机、证据机制或 helper；丢失或损坏只影响性能。

### 8.3 并发与资源（DC47）

- 每个 worker 进程一个固定 N 的 Rayon 池，启动时建好，所有 kernel 共用；pyarrow 的 CPU 与 I/O 线程池按 N 设定；测试默认 N=1。
- 按“预估行数 × 列宽”准入，运行中任务的预估总和 ≤ M；单表超过 M 时以资源预算诊断稳定失败。V6、V1 实测内存随线程数增长（V1：16 线程约 1.2 GB），M 的估算须计入。
- 部署配置只开放 N 与 M（有范围校验、写进测量记录）；其余为代码常量。N 在 S2b 后按整条路径的加速曲线暂定，S6 定稿。

### 8.4 切换与 Contract 修订

- feature flag 切换上传侧到 Rust 路径；Python 路径保留至 S6（DC37 第 4 项）。
- 修订 Canonical Storage §5（格式与生命周期：BaselineHead 正式引用与 TTL 副本取代“第一版不长期保存 full-row archive”的表述）、设计 §4.6 闭包条目格式。
- 验收：t1–t4 端到端摘要与 §6 的基准一致；内容地址与读取校验的权威测试。

## 9. S3：比较与逐行记录

- **共用内核（DC44、V1）：** standard、keyless 与 ordered 在 `gateway-compute-core/src/comparison/` 中共用规范编码、共有列投影（DC40 的语义）、行身份、记录排序、资源上限与 facts 管线；ordered 专属的 LIS 主干、绝对 `no` 位置与空白区间规则留在 ordered 模块。
- **逐行记录（DC54）：** kernel 按记录族 schema 产出 Arrow 记录列，并用相同 JCS 编码计算 `content_digest`；Python 用 pyarrow 由 Arrow batch 写 Parquet；写后回读改为 Rust 重算摘要或删除（P：删除，理由同 DC42 第 9 项——读取侧已有校验）。记录产物与 Contract 不变，现有 golden 作为逐字节回归基准；如必须改动格式，按 Contract 变更另行提交 owner。
- **单次操作内去重（DC43）：** 缓存键为“去掉表名与显示名之后的单表任务输入”的摘要；表名、显示名、标注编号、pair 上限与组合信号表在汇总步骤绑定；权威测试：开启与关闭去重，facts 与 records 摘要相同。
- **分歧点先写进 Contract：** 浮点 -0.0、NULL、字符串按字节排序、记录输出顺序、ordered 并列规则（DC44 第 3 项）。
- **风险仍在 Python**（DC47 第 1 项）。
- **接入：** feature flag 之后；差分覆盖第 ① 层语料、随机差分与 t1–t4。

## 10. S4：Submit

- **渲染直通（DC45 第 4 项）：** 变化表直接从冻结规范表（S2b 起为 IPC，mmap）渲染 SQL；导入路径不再构造逐行变化集对象、不计算无消费方的摘要；表级决定仍归规划器。
- **存储 diff：** 与 S3 共用比较内核，按存储键比较全部保留列；行级修改的 DELETE 与 INSERT 尽量成批。
- **阈值定稿：** 用最终渲染器与 RS 回放路径实测，定稿 DC45 的阈值。
- **通用规划器与 ChangeSet Contract 保留**，作为 ADR 0014 外部目标的 owner（DC45 第 5 项）。
- **验收：** `replay.sql` 与 S1a 的产物逐字节一致（同输入）；计数断言；S1–S4 完成时间。

## 11. S5：History 与跨操作缓存

- **diff/risk 缓存（DC43）：** 条目以单表任务输入摘要为键，作为 artifact 存放并经保护表登记引用；在计算时形成（Preview 或 History），按 TTL 保留；Submit finalize 在移动 head 的同一事务中给该 Submit 对应 Preview 的条目登记引用。
- **History 按表拼接（DC38）：** 两侧表摘要相同 → 未变化；否则查 diff/risk 缓存 → 读表缓存 → Dolt 兜底并回填；pair 级 surface 与 bundle 由单表结果汇总。
- **Dolt 并发读取（DC47 第 6 项）：** operation 内对 RS 的并发读取 ≤ RS 容量（客户端信号量），503 作为背压退避重试，不作为失败。
- **计数断言：** TTL 内 H1 与 H3 的 Dolt 读取次数与比较次数为 0；TTL 外 H1 的 Dolt 读取次数等于旧节点的变化表数。
- **H2 定稿：** 两节点 2× t4 冷读验收。

## 12. S6：收尾

- 加速曲线定 N（DC35 第 5 项：1、2、4、8、16、32 线程，取并行效率约 60–70% 以上的最大值）。
- 删除生产 feature flag，Python 实现降为测试用参照（差分测试与小数据 oracle）。
- 2× t4 全部负载取证与计数断言；存储报告（Performance Measurement §6）。
- 结合 V8 方法重新剖析门禁时长（DC48 第 3 项）；Phase 6 退出。

## 13. 持久化、HTTP 与部署影响

| 面 | 影响 | 阶段 |
| --- | --- | --- |
| control DB | 保护表新增 owner 类型（BaselineHead 正式引用；diff/risk 与导出缓存条目）；schema 基线直接修改，本地 DB 删除重建（DC6） | S1b、S2b、S5 |
| checkpoint 载荷 | prepare checkpoint 绑定 parent manifest digest；Preview 与 History checkpoint 引用内容寻址文件 | S1a、S2b |
| HTTP | 上传超时的新错误码；Preview/History 结果中整表浏览的 surface；bundle 含整表 | S1b |
| 部署配置 | N、M（可修改、有范围校验） | S2b |
| 镜像 | backend Dockerfile：新 adapter 的 maturin 构建、Rust 依赖；强制重建项 | S2a 起 |
| Repository Service | 无 Contract 变化；defunct 进程问题交 RS owner（可并入 kickoff 小修或 S1a，修复可能涉及 Dockerfile/Compose） | — |

## 14. 语义 owner 与需修订的文档

| 语义 | owner | 文档 |
| --- | --- | --- |
| 表摘要、manifest、replay.sql、规范表存储生命周期 | Canonical Storage / Storage Projection | Canonical Storage §4、§5、§6.1 |
| 行级修改与阈值 | Storage Mutation | Storage Mutation §2/§3、ADR 0014 |
| schema 演进分类、比较分歧点、逐行记录 | Comparison | Comparison、Ordered Diff |
| 风险 | Risk | Risk |
| surface 与 bundle | Surface / Bundle | Comparison Surface、Comparison Bundle |
| 解析语义 | Table Access / Shared Canonical Encoding | Snapshot Table Access、Shared Canonical Encoding |
| 上传时限与错误码 | Workspace HTTP | P5-5A 上传设计 |
| commit 元数据 | ADR 0019 | ADR 0019 |
| Rust 边界 | Rust policy | 不修订（本设计不需要 unsafe、nightly、手写 SIMD、自定义分配器） |

## 15. 测试归属

每个不变量一个权威测试 owner（比例化保障政策）：

| 不变量 | 权威测试（拟） |
| --- | --- |
| 表摘要与行顺序无关、Dolt 读回可重算 | storage_projection 摘要测试 |
| 未变化表不读基线、不比较（含 ordered） | Preview 结构过滤的计数断言测试 |
| Submit 跳过未变化表、阈值路由、parent 绑定 | mutation planning 与 prepare 测试；Compose Submit 旅程 |
| 只增列按共有列判定 | comparison schema 演进测试 |
| bundle 含全部表、导出缓存按摘要命中 | bundle 组装测试 |
| 上传空闲超时与总上限、错误码 | 上传 streaming 测试（serial） |
| Rust 与 Python 逐值 / 逐字节一致 | 各 kernel 的差分测试（含 t1–t4 取证） |
| 1 与 N 线程输出相同 | 各 kernel 的确定性测试 |
| 去重开关不改结果 | comparison 去重测试 |
| 规范表存储读取校验与 Dolt 兜底 | 存储读取测试 |
| 缓存条目只缓存纯函数结果 | diff/risk 缓存测试 |

## 16. 性能测量

### 16.1 runbook

测量在 `ct108-gw-dms` 独占；日志开头记录 hostname、起止时间与 HEAD；1 次预热加 3 次测量取中位数；W1、W4 冷启动（存储中只有已提交基线的条目），W2、W3 允许命中上一次 Preview 的临时条目并写明；清空派生缓存模拟 H2；合成负载规则见 §5.6。

### 16.2 计数断言

| 断言 | 负载 |
| --- | --- |
| 基线读取表数 = 变化表数 + 删除表数；比较调用次数 = 变化表数 | W2（均为 0）、W3 |
| `replay.sql` 涉及表数 = 变化表数；行级语句数 = 行级修改表的变化行数 | S2（无 Repository operation）、S3 |
| TTL 内 Dolt 读取次数与比较次数 = 0 | H1、H3 |
| TTL 外 Dolt 读取次数 = 旧节点变化表数 | H1 |

## 17. 停止条件与开放项

停止条件（遇到即停止并报告 owner）：

1. S1a 的归因（§4.4）无法解释 step 间隔或约 175 s 残差的来源；
2. 任一 Rust kernel 与参照实现出现无法归入“参照实现不符合 Contract”的差异；
3. 阈值复测显示 1% 仍比整表重建慢；
4. 规范表存储的磁盘估算超出参考节点容量；
5. 逐行记录必须改变产物格式（DC54 第 4 项）；
6. 某阶段的门槛在设计手段用尽后仍不能达到。

开放项（本设计提案，待审核与 owner 确认）：

| 项 | 本设计提案 | 节 |
| --- | --- | --- |
| ordered 表摘要口径、`ordering_digest`、`fast_row_digest` | 覆盖全部规范列；删除 `ordering_digest`；`fast_row_digest` 保留到 S2b 复核 | §4.1 |
| 上传超时错误码 | `UPLOAD_STREAM_TIMEOUT`，HTTP 408 | §5.4 |
| 参照解析器的语义问题 | §5.5 表中各项 | §5.5 |
| Arrow 列映射 v1 | §8.1 | §8.1 |
| 记录写后回读 | 删除 | §9 |
| 上传侧原始表是否还有使用方、磁盘估算 | 设计核对项，S2b kickoff 前完成 | §8.1、§8.2 |
| 重要 keyless 表的自然键 | 业务评估，S1a 之前给出（DC50） | — |

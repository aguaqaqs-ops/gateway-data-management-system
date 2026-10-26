# Phase 6 详细设计：单任务性能与 Rust 接入

状态：**ACCEPTED — S0 文档（r4）经独立文档审核（首次审核与三次复审，第 3 次复审结论：通过）由 repository owner 于 2026-10-26 接受；实现授权范围见执行计划 §2 S0**

日期：2026-10-26（r4）；r1–r3 为 2026-10-26

Owner：Backend vNext Architecture（Phase 6 牵头）；各项语义归属见 §14

入口：[S0 Owner 决议记录](p6-s0-owner-decisions.md)（DC37–DC55）→ 本文 → [执行计划](p6-execution-plan.md)

审核：[S0 独立文档审核](p6-s0-independent-docs-review.md)：首次审核（r1，定向修订，8 项阻塞、2 项非阻塞）；第 1 次复审（r2，定向修订：F1、F5、F6 部分关闭，新增 F11、F12）；第 2 次复审（r3，定向修订：F1、F6、F11、F12 关闭，F5 部分关闭，新增非阻塞 F13）。处置见附录 A。

依据：[Phase 6 规划讨论稿](p6-planning-discussion.md)（分析过程与数据）；前置验证报告
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
[Comparison Bundle](../../../contracts/comparison-bundle.md)、[Snapshot Table Access](../../../contracts/snapshot-table-access.md)；
ADR [0001](../adr/0001-python-rust-hybrid-compute-strategy.md)、[0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)、
[0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)、[0014](../adr/0014-adaptive-patch-and-target-neutral-change-set.md)、
[0019](../adr/0019-commit-canonical-metadata-authority.md)；
[Rust safety and performance policy](../policies/rust-safety-and-performance-policy.md)、
[Proportional assurance policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)；
[P5 收口设计](p5-arch-closure-design.md) §4.6（Preview 闭包与 T1 冻结对象）。

标记：**E** = 已实现或已实测的事实（源码 @ `fc109806bb`，经独立审核复核）；**D** = 已决议（DCxx）；**P** = 本设计提案，须经审核与 owner 确认。

## 1. 目标、决定与非目标

### 1.1 目标（D）

- **单个 operation 的延迟**达到已决议的门槛（DC35、DC38、DC53），参考环境 `ct108-gw-dms`，规模 2× t4，单任务资源上限 N、M 下判定。完整验收矩阵（模式、节点数、缓存条件、READY 与完成两个时点、门槛或只报告）见 §16.3。

  | 负载 | 门槛（用户可见时间） |
  | --- | --- |
  | W1 首次上传（空基线） | ≤ 3 min |
  | W2 原样重传（0 张表变化） | ≤ 30 s |
  | W3 少量变化（约 10% 的表） | ≤ 60 s |
  | W4 几乎全变（全部表、每表约 10% 行变化） | ≤ 3 min |
  | H1 / H2 / H3（History 相邻首查 / 冷查询 / 重复查询） | ≤ 60 s / ≤ 5 min（S5 定稿） / ≤ 15 s |
  | S1、S4 / S3（Submit 首次与几乎全变 / 少量变化，完成时间：受理到 main 前移） | ≤ 5 min / ≤ 2 min |
  | 所有 operation 的完成时间 | ≤ 10 min |

- **结构性条件：** 成本随变化量增长，用确定性计数断言证明（§16.2）。
- **Rust 首次进入生产链路**（DC37）：上传侧解析、物化检查、投影与摘要；比较（含 ordered）与逐行记录；Submit 的存储 diff 与 SQL 渲染。
- **业务缺口修正**（Contract 阶段，不计入性能收益）：只增列（DC40）、bundle 补齐整表（DC41）、慢速上传（DC49）、参照解析器的输入边界缺陷（DC50）。

### 1.2 决定索引（D）

DC37 边界与 feature flag；DC38 Submit 与 History 目标；DC39 表摘要保值统一与结构性过滤；DC40 只增列；DC41 bundle 整表与整表浏览；DC42 规范表存储；
DC43 计算去重与跨操作缓存；DC44 比较列式化（ordered 一并进入 Rust）；DC45 Submit 只写变化；DC46 解析器主线与数据路径合并；DC47 Rust 范围、并发与技术栈；
DC48 Rust 测试入门禁（已实施）；DC49 慢速上传；DC50 阶段结构；DC51 门禁 worktree 保留；DC52 旧扩展过时；DC53 W1–W4 定稿；DC54 逐行记录进入 Rust；
**DC55 审核后的决议修订**（未变化 ordered 表用当前侧按本次有效 pair 策略计算 facts、完整表身份、冻结产物恢复边界、零日期维持拒绝、计数口径与字节冻结）。

### 1.3 非目标（D）

- 多个 operation 的并发、排队、多 worker、跨 operation 的 RS 资源分配、按容量淘汰（Phase 7，DC37）。
- “分组分裂”风险信号（DC43 第 5 项）；Dolt 同内容表写入优化（DC45 第 8 项）；外部分区库（DC45 第 5 项，只预留）。
- 零日期与零日期时间的支持（DC55 第 4 项）。
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
| step 间隔 | 每个 operation 合计 9–26 s | 单处 1.0–9.8 s，不是每处都长（例如重传 Preview 的第一处 1.0 s）；worker 空闲轮询为 1 s，不能解释（V5） |
| 未归因的 worker step 残差 | 约 210 s | 基线物化约 75 s、assemble 固定约 100 s、Submit prepare 约 36 s（V5b） |

### 2.2 代码事实（经独立审核复核）

1. **Submit 每次重写全部表**：`capabilities/mutation_planning/import_replay.py` 以 `REBUILD_ALWAYS`、空的“变化前”规划，schema SQL 为每张 import 表 `DROP` + `CREATE`（`storage_projection/import_replay.py`），与 Storage Mutation §2 不符。原样重传在受理处判为 `NO_CANONICAL_CHANGE`，不产生 Repository operation。RS 在从 expected parent 建立的私有 ref 上回放并做 STRUCTURAL 校验，已支持只写变化（DC45）。
2. **Preview 全量物化基线 commit**：`application/preview_jobs.py` 的 `_materialize_baseline` 经 `materialize_repository_ref` 读出全部表，没有按变化表选择。
3. **ordered 表的行比较路径从不提前退出**：`comparison/standard.py` 在普通表的提前退出判断之前把 ordered 表交给 `compare_ordered_task`（BROWSE_ONLY、SNAPSHOT_ONLY 有前置分支）。
4. **摘要**：manifest 内容摘要的计算依赖读取顺序（keyless 表先排序，ordered 表按 gid 排序）；`raw_content_digest` 是与行顺序无关的 row-hash 摘要，**但只覆盖行内容，零行时不含 schema 输入**；`fast_row_digest` 计入 snapshot digest。`ordering_digest` 没有独立的外部语义使用方，但除 storage_projection 外还经 `infrastructure/repository_write/import_publication.py` 传递。ordered 比较 facts 中的 `before/current_ordered_digest` 是 Ordered Diff 定义的逻辑摘要（含表名与策略版本、排除 ignored columns，`comparison/ordered.py` 的 `_ordered_digest`），计入 comparison digest，进而计入 surface 与 bundle digest。
5. **标准模式 bundle 不含整表数据**：`application/pair_pipeline.py` 只在 DATASET_REPLACEMENT 模式下传入 table artifacts（DC41）。
6. **逐行记录在 Python 中逐条构造**：`comparison/artifacts.py` 每条记录构造 dict、做 JCS 编码、`from_pylist` 写 Parquet、发布后整份解码重算摘要；读取侧另有完整校验（DC54）。风险引擎以 `tuple[ComparisonRecord, ...]` 逐条消费记录（`risk_evaluation/_facts.py`、`_engine.py`）。
7. **上传**：固定 60 s 总时限（`application/workspace/upload_limits.py`，超时转为 `UploadLimitExceeded`，返回 413）；async 路由直接调用同步的受理 helper，在事件循环上解压校验（`http/orchestration/multipart_upload.py`）（DC49）。
8. **参照解析器的输入边界缺陷**：BIT 负数、超宽 BIT、非 ASCII 的 `b'..'`、深层嵌套 JSON 抛出未捕获的异常越过 `parse_sql`（`capabilities/table_access/_sql_values.py`）；FLOAT 两次舍入的实现位于 Shared Kernel 的 `scalar.py`。零日期由 Shared Kernel 的日期规范化拒绝，RS 的 Arrow 映射固定 DATE=`date32`、DATETIME=`timestamp[us]`，也不能表示零日期。
9. **RS 逐表读取许可池**：容量为可配置项，默认 8（`repository_service/settings.py`），超出以 503 立即拒绝（`versioned_read/http_service.py`）；读取期间累积 defunct `dolt` 进程（V7 观察，未复现，根因未明）。
10. **Rust**：V6（`gateway-compute-core/src/table_access/`）与 V1（`src/comparison/ordered.rs`）原型已合入，未接入生产；旧扩展 `gateway-compute-python` 与 `canonical_row_hash` 生产中不可达（DC52）。权威 runner 已含 `rust` 包，排除两个旧 adapter crate 的 `cargo test`，强制重装扩展并核对构建输入（DC48）。

### 2.3 原型实测（E）

| 原型 | 一致性 | 性能（ct108） | 证据边界 |
| --- | --- | --- | --- |
| V6 解析器 | 语料 118 例、t1–t4 两版 3,389 万个值，差异 0；1–32 线程逐字节相同 | 2× t4 单线程 1.25 s（约 121 MiB/s），N=4 时 0.48 s；峰值内存为输入 3.8–5.0 倍 | 只到解析输出，不含物化、投影、PyO3 交接 |
| V1 ordered 比较 | t1–t4 的 58 张变化表、11,698 条记录、合成 30 例与随机 96 例，差异 0 | t4 变化 ordered 表单线程 2.64 s（参照 32.6 s）；10 万行近乎全量重排近似线性 | 不含 IPC 读取与输出编码 |
| V7 Dolt | 三种回放的 312 张表哈希一致 | 逐行修改约 9 ms/条语句、整表重建约 0.11 ms/行；RS 8 并发读一个已热 t4 commit 约 27 s | 混合写入 4.45 s 是模型估算；读取是热读，不是 H2 冷读 |

## 3. 目标结构

```text
上传（流式接收，空闲超时）→ 受理（线程池）
  → Rust：扫描与解析 → 业务列与检查 → 规范投影 → 表摘要
    → Arrow / IPC 字节 →（Python）ArtifactStore 写入规范表存储（按内容寻址）
  → manifest（每表：表摘要、schema digest、存储视图）
Preview：与基线 commit manifest 按完整条件逐表比对 → 只对变化表与删除表读基线
         （已提交表从存储 mmap 读，Dolt 兜底）→ Rust 比较 + 逐行记录 Arrow 与 content_digest
         → 风险（Python，按 Arrow 分批消费）→ surface → bundle（全部表 Parquet，导出缓存）
Submit：T1 冻结 → prepare：与 parent manifest 比对 → 跳过 / 行级修改 / 整表重建
         → Rust 直接从冻结规范表渲染 replay.sql → RS 导入（包格式不变）
History：按表拼接：完整条件相同即未变化 → diff/risk 缓存 → 表缓存 → Dolt（并发 ≤ min(N, RS 容量)）
```

Dolt 始终是已提交数据的权威来源；规范表存储中已提交表的副本、diff/risk 缓存与导出缓存都是派生数据，缺失或损坏只影响性能。T1 冻结、尚未提交的规范表不是派生数据，其恢复边界见 §8.2（DC55 第 3 项）。

模块与语言分工按 DC47 第 1 项与讨论稿 §5.4：数据密集计算在 `gateway-compute-core`（按 capability 分模块）中，经 PyO3 adapter 以 Arrow 进、Arrow 出的粗粒度调用接入；Python 保留 domain、application、Operation Runtime、规则解析、风险规则与业务 policy；Rust core 不读写文件。

## 4. S1a：摘要与存储 Contract

### 4.1 表摘要保值统一（DC39、DC55 第 1 项）

- **表摘要（D）：** 每表唯一的表摘要 = 现有 `raw_content_digest`，与行顺序无关，Dolt 读回能重算出同一个值。它只代表行内容；凡需要表身份的地方都与 schema digest 等一起使用（§4.2、§5.2）。
- **manifest（D）：** `CanonicalizationManifestTable` 的内容摘要字段改为表摘要；`STORAGE_PROJECTION_VERSION` 从 `"2"` 升到 `"3"`（`capabilities/table_rules/contracts.py`）。投影版本不同的 parent 一律按“全部变化”处理；不做兼容，本地 control DB 与 Dolt 测试数据重建（AGENTS 项目前提）。
- **未变化 ordered 表的 facts（D，DC55 第 1 项）：** Ordered Diff 定义的 ordered 逻辑摘要与空白区间 occupancy 摘要定义不变。满足“未变化”完整条件（§4.2）的 ordered 表，两侧内容相同，facts 用当前侧的行、按本次受理冻结的有效 pair 策略（含两侧共有列）计算，两侧取同一值；不读基线侧，不运行完整比较算法（LIS、记录生成）。manifest 不新增 ordered 字段。
- **`ordering_digest`（P）：** 删除，包括 storage_projection 内部的计算与自校验，以及 `import_publication.py` 中的传递；统一表摘要覆盖全部规范列（含 `no` 与伪 gid），顺序变化即内容变化。它与 ordered 逻辑摘要是两回事，不合并。
- **`fast_row_digest`（P）：** 保留。它进入 snapshot 身份；若以后要删除，须重开 owner 决定与 Contract，并重建基准，不作为普通优化（审核意见）。
- **去掉重复计算（D）：** 投影时同一份数据不再编码 3–4 次。
- **commit 元数据（D）：** `CommitCanonicalMetadataPort` 返回的 manifest 带每表表摘要、schema digest 与存储视图，作为结构性过滤的输入（ADR 0019 的端口形态不变，语义说明补充）。

**摘要变化与保值清单（S1a）：**

| 摘要或产物 | S1a | 说明 |
| --- | --- | --- |
| 表摘要（`raw_content_digest`） | 保值 | 定义不变 |
| manifest 每表内容摘要 | **变化** | 改为表摘要的值 |
| `ordering_digest` | **删除** | |
| manifest digest | **变化** | 随以上字段变化；体现在 PreviewResult、Submission 记录与 checkpoint 中 |
| ordered 逻辑摘要、occupancy 摘要、comparison / surface / bundle digest | 保值 | 未变化 ordered 表的单侧计算与现算逐字节相同；S1b 才因 DC40、DC41 变化 |
| snapshot digest、规范状态摘要、`fast_row_digest`、HTTP DTO | 保值 | |
| 导入包与 `replay.sql` | **变化** | 只写变化（§4.3） |

**golden 生命周期：** 见 §4.6。

### 4.2 Preview 与 History 的结构性过滤（DC39、DC55 第 2 项）

- **未变化的完整条件（D）：** 两侧都存在，且表摘要、schema digest、存储视图与投影版本都相同。仅表摘要相同不够（零行表不同 schema、只改可空性等）。
- 满足完整条件的表：不读基线行、不做行比较；facts 的行数与 `UNCHANGED` 来自 manifest。ordered 表另按 §4.1 用当前侧的规范行计算逻辑摘要与 occupancy 摘要，计算发生在 assemble 中、按每个 pair 一次（S1a 用 Python，S3 起用 Rust），健康缓存命中时直接用 diff/risk 缓存（§11）。成本计入 §16.1 的 e 项。
- **当前侧的规范行来源：** 是本 pair 的当前侧，不固定为 MODIFIED：MODIFIED_ONLY Preview 为上传的 MODIFIED；FULL Preview 的两个 pair 分别为上传的 INITIAL 与 MODIFIED；History 为各 pair 的 current commit（三节点时分别为第 2、第 3 节点）。读取经 materialize checkpoint 的 artifact reader（S2b 起为规范表存储的 IPC reader），不依赖上一步 Python 对象存活；History 经存储，缺失时从精确 commit 经 Dolt 兜底（§8.2）。
- **单侧计算的实施约束（第 2 次复审 §7.3）：** 有效 pair 策略仍按现行方式由两侧描述符与存储事实构造（`comparison/pair_planning.py`），不能因只读一侧而把基线侧描述符设为空；行编码与 blank provenance 使用规范行及其规范 metadata（`CANONICAL_PSEUDO_GID`），不按原始 SQL 重新解释；ordered/blank status、replay guarantee、schema facts、policy digest 等 facts 字段按既有结构填充；现有 schema 诊断与行读取异常的 degraded 语义保留，不能仅因 manifest 相等就强制标为 `UNCHANGED`；**不得复用 `_compare_single_side`**——它表达的是整表新增或删除，会产生增删记录与不同的 blank 摘要。
- 变化表与删除表读取基线：S1a 中经 RS 逐表读取（规范表存储在 S2b 才有），并发 ≤ min(N, RS 有效容量)（DC47 第 6 项；S1a 可先顺序读取）；新增表没有基线可读。
- History 的两个节点使用同一套完整条件；整表数据的读取随 DC41 的打包进行（§5.2）。
- 计数断言见 §16.2。

### 4.3 Submit 只写变化：表级跳过与阈值行级修改（DC45、DC55 第 5 项）

- **表级跳过：** prepare 取 T1 冻结的上传侧 manifest 与 expected parent 的 manifest，按 §4.2 的完整条件逐表比较；未变化的表不进入 `replay.sql`；删除的表照旧 `DROP`；parent 为 INITIAL、缺少 metadata 或投影版本不同时全部按变化处理；包 manifest 仍列出全部表（RS STRUCTURAL 校验整个 catalog）。
- **行级修改：** 生产 policy 改为 `ADAPTIVE_PATCH`；资格按 Storage Mutation §3 修订：keyed 表与有序表（GID_NO_V1，以 `gid` 为存储键、`no` 为普通列）可行级修改；keyless 表与 schema 变化的表整表重建；阈值 1,000 行 / 1%。
- **parent 行：** 变化表的 parent 行经 RS 读取（S1a），读取结果按 parent manifest 的表摘要校验，不一致时稳定失败；S2b 起优先读规范表存储中该 commit 的副本。正确性前提为 expected-parent CAS、parent 行按 manifest 校验与受信 Repository（DC45 第 6 项）；生产 Dolt 路径不加条件 DML、affected-row 检查或提交后读回（§14 的 ADR 0014 修订）。
- **实现：** S1a 用现有 Python 规划器与渲染器（`capabilities/mutation_planning/`）；导入路径不再为未变化的表构造变化集。逐行变化集对象与无消费方摘要的去除、渲染直通在 S4。
- **checkpoint 与 T1：** T1 冻结的 `builder_mutation_policy` 改为 `ADAPTIVE_PATCH`；prepare checkpoint 增加 parent manifest digest 的绑定，恢复时核对。
- **阈值与批量规则冻结（D，DC55 第 5 项）：** S1a 用实际渲染器与 RS 回放路径，对 t4 v2 的变化表实测逐行与重建的耗时，确认 1% 不比重建慢；阈值与 INSERT 批量规则（现为每条最多 256 行）在 S1a 冻结。S4 只做逐字节回归；若必须调整阈值，作为例外交 owner，并在 S4 更新包 golden。
- **验证：** 新旧路径在 t4 v2 上得到的 Dolt 表哈希相同（V7 已在一次性回放中证明，S1a 用产品路径复核）。

### 4.4 worker step 归因与残差处理（DC53 第 2 项）

S1a 退出前，在 ct108 上对 S1a 候选 HEAD 运行 t4 完整旅程（同 V5 的方法），并用 V5b 的测量工具补测，回答：

1. 各处 step 间隔（单处 1.0–9.8 s）来自 step 发布、checkpoint、租约、领取路径中的哪一段；
2. 基线物化约 75 s、assemble 约 100 s、Submit prepare 约 36 s 残差的来源。

handoff 对每项给出：来源、处理方案、处理阶段与 owner。仍无法归因时停止，由 owner 决定是否增加产品插桩（§17）。W2 的可达性在 S2b 检查（§16.1）。

### 4.5 S1a 的 Contract 修订

见 §14 的修订清单（标注 S1a 的行）。

### 4.6 golden 生命周期

| golden 组 | 唯一更新节点 | 之后 |
| --- | --- | --- |
| storage-projection、mutation、导入包 | S1a | 冻结；S4 只回归，调整须 owner 例外（DC55 第 5 项） |
| storage-projection 中的规则集文档与 manifest（例外） | S1b | DC56 的补键与 BROWSE_ONLY 名单改变规则集（版本提升）与受影响表的规范键，在 S1b 更新一次后冻结；mutation 与导入包 golden 只在其输入含受影响表时随之更新 |
| comparison、risk、surface、bundle | S1b | 冻结；S3 的分歧点只把现行行为写进 Contract，不改语义；若必须改语义，作为例外交 owner 并在重建基准前完成 |
| table-access（参照解析器修复与语义） | S1b | 冻结；S2a 的 Rust 实现以其为基准 |
| shared-kernel 编码向量（FLOAT 直接舍入） | S1b | 冻结 |
| snapshot-materialization | 不变 | 保值 |
| canonical-row-hash | S2a 删除 | — |

重建对照基准（§6）在 S1b 之后进行，此后各 golden 作为逐字节回归基准。

## 5. S1b：业务语义 Contract

### 5.1 只增列的 schema 变化（DC40）

- 比较为两侧都存在的表计算 schema 演进分类 `NONE | COLUMNS_ADDED | COLUMNS_REMOVED | INCOMPATIBLE`，作为 facts 的稳定字段（`ComparisonSchemaChanges` 增加分类）。
- `COLUMNS_ADDED`（含 ENUM 只增标签、SET 只增成员，标签位置不限）：按共有列判定变化与风险，表状态不因新增列变为 `SCHEMA_CHANGED`，不降级；不产生 `SCHEMA_CHANGE` 风险；Submission 与 History 结果不列出新增列。
- `COLUMNS_REMOVED`：保持现行（`SCHEMA_CHANGED`，`MEDIUM_HIGH`）。
- 只增列改变规范状态，`NO_CANONICAL_CHANGE` 不成立，提交仍生成版本；Preview 不提示。写入 Comparison Contract。
- 触发事件只预留（分类作为 facts 字段），不建事件机制。

### 5.2 bundle 补齐整表数据（DC41、DC55 第 2 项）

- Preview 的 bundle 包含上传侧全部表与删除表的基线侧数据；History 每个节点包含全部表；同内容的表按内容地址共享（`shared/snapshot-tables/`），每个节点或当前侧对表名的绑定保留在 bundle 清单中，不因共享丢失。
- 表文件为 Parquet。**导出缓存**以现有 row-layout 身份（行内容 + 导出 schema + repository scope，Snapshot Table Access 的 `row_layout_digest`）加 Parquet writer 版本为键，条目经现有保护表登记引用、按 TTL 管理（ADR 0012）；未命中时从规范表读取并导出、回填。
- S1b 中规范表来自现有 snapshot artifact 与 Dolt 读取；S2b 起来自规范表存储。
- 避免整表反复读取与校验；assemble 约 100 s 的固定开销按 §4.4 归因后在此处理。
- 修订 Comparison Bundle 契约（整表打包、导出缓存按 row-layout 身份命中）。

### 5.3 整表新增或删除改为整表浏览（DC41 第 3 项）

- 表状态仍为 `ADDED_TABLE` / `DELETED_TABLE`；不产出逐行记录；风险为一条表级标注，证据带行数（`TABLE_ADDED` / `TABLE_DELETED` 规则加计数）。
- surface 映射为整表浏览：新增表浏览 `current_table_ref`，删除表浏览 `before_table_ref`；前端表浏览须能显示表级风险。
- 依赖 §5.2，同一阶段落地。

### 5.4 慢速上传（DC49）

- 上传改为**空闲超时**（连续 60 s 没有收到数据）加**总上限**（最大压缩包 ÷ 1 Mbps，256 MiB 约 36 min）；常量仍在 `application/workspace/upload_limits.py`，总上限由最大包推出。
- 两种超时共用一个错误码（P：`UPLOAD_STREAM_TIMEOUT`，HTTP 408），附有界的原因字段；413 只用于大小与资源限制。修订 P5-5A 上传设计中的错误码表。
- 受理中的同步工作（解压校验、artifact 写入、control DB 事务）移到线程池；保留解压预算、断连释放，以及线程池中操作的完成与取消边界。

### 5.5 参照解析器的缺陷与语义定稿（DC50 S1b、DC55 第 4 项）

| 项 | 处理 |
| --- | --- |
| BIT 负数、超宽 BIT、非 ASCII `b'..'` 的未捕获异常 | 修复为确定的诊断（D），补 golden |
| 深层嵌套 JSON 的未捕获异常 | 修复为确定的结果（D）；P：设嵌套上限并以 `SQL_VALUE_ILLEGAL` 有界拒绝（V6 原型现为迭代接受，S2a 按定稿调整）；JSON 孤立代理的策略一并定稿 |
| FLOAT 两次舍入 | 按 Shared Canonical Encoding 直接舍入到 binary32，修复位于 Shared Kernel `scalar.py`（D，DC55 第 4 项） |
| 零日期、零日期时间 | **维持拒绝**（D，DC55 第 4 项） |
| BIT 列的十进制数字字面量 | P：按 MySQL 以十进制解释 |
| `_binary` 前缀 | P：接受，按二进制值解析 |
| `\%`、`\_` 转义 | P：按 MySQL 保留反斜杠 |
| 列类型中夹注释 | P：忽略注释 |
| JSON 接受 `NaN` / `Infinity` | P：拒绝（与 MySQL 一致） |

P 项在 S1b kickoff 时由 owner 逐项确认。语义改动在 S1b 定稿并冻结 golden（§4.6），S2a 不同时改语义和换实现。真实数据 t1–t4 中均无受影响的值，新增接受的值用合成用例验证往返。

### 5.6 测量负载

- 合成 2× t4：复制 t4 的表并加后缀、扰动内容，避免同内容去重收益虚高（DC35 第 7 项）。
- W4：在已有基线上全部表变化，每表约 10% 行变化（插入、删除、修改混合，ordered 表含位移）；压力档每表 100% 行变化，只报告（DC53 第 3 项）。
- 规则写入测量 runbook（`vnext/backend/benchmarks/` 下的生成工具，Git 中只出现表名与计数）。
- t3 即原 testdata1，作为 schema 演进样本（DC40 第 7 项）。

### 5.7 S1b 的 Contract 修订

见 §14 的修订清单（标注 S1b 的行）。

## 6. 重建对照基准

S1b 合入后，用 Python 实现在 `ct108-gw-dms` 独占测量 §16.3 验收矩阵中的全部场景（t1–t4 与合成 2× t4），记录墙钟、CPU、峰值并行核数、峰值内存、临时磁盘高水位与计数断言。之后各阶段只核对结果与该基准一致，不再重建（DC50）。

## 7. S2a：SQL 解析器

- **范围：** 在 V6 原型（`gateway-compute-core/src/table_access/`）基础上补齐：完整诊断（消息文本、同一张表多处错误、行预算按元组计数的偏移）、第 ③ 层负例与预算语料、第 ② 层 Hypothesis 差分、现有解析器测试改为双实现参数化（讨论稿 §6.3）；`Utf8`/`Binary` 超过 2 GiB 时改用 large 变体或分批输出；按 §5.5 的定稿调整（例如深层 JSON 有界拒绝）。
- **PyO3 adapter（新）：** 长调用 `py.detach`；取消标志与截止时间接到 `ParserRuntime`；输出经 Arrow C Stream 交给 Python；panic 在 core 入口与 adapter 两层转为诊断；native abort 或被内存不足终止不伪装成诊断，由 Operation Runtime 的既有租约接管处理（Rust policy §3）。线程池改为 worker 级共享（DC47 第 5 项）。
- **接入：** feature flag 之后，只用于差分，不切生产。
- **旧扩展删除（DC52）：** 删除 `capabilities/canonical_row_hash`、core 中的旧 pipeline、旧 adapter 入口、`canonical-row-hash` golden、Canonical Row Hash Compute Boundary Contract、`native_kernel_component.sh` 及引用它们的测试与架构基线条目；`rust` 包去掉对两个旧 crate 的 `cargo test` 排除；backend Dockerfile 的 maturin 构建改为新 adapter；新扩展的 `__build_input__` 与 `check-rust-extension-build-input.sh`、依赖与架构检查、`import_rules` 基线同步核对。
- **验收：** 五层语料全部通过，t1–t4 逐值差异 0，并行确定。

## 8. S2b：上传侧数据路径与规范表存储

### 8.1 数据路径合并（DC46）

- 解析 → 业务列与检查（伪 gid 范围、重复有效键、keyless 降级）→ 规范投影（保留列、规范键、ordered 的 gid/no 校验与伪 gid）→ 表摘要与 `fast_row_digest` 在 Rust 中依次完成，数据始终是 Arrow；三个 capability 各自拥有语义与诊断，模块依赖不变。上传路径不预计算 ordered 逻辑摘要与 occupancy 摘要：它们依赖本次 pair 策略，只在 assemble 中按 pair 计算一次（§4.2，S3 起由 Rust 计算）。
- composite signal 留在 Python：在 Arrow 上先按特殊设备过滤 `device` 与 5 张特殊点表，只把命中行转成 Python。
- Rust 输出规范表的 IPC 字节，由 Python ArtifactStore 写入（Rust safety policy §4）。
- **上传侧原始表不再写 Parquet（设计核对项，S2b kickoff 前完成）：** 逐一核对 materialize 与 assemble 的 checkpoint、FULL 双侧、composite、bundle、T1 与恢复路径中的读取者；未完成前不进入 S2b 切换。
- **Arrow 列映射 v1（P，backend 内部映射，不改 RS wire 映射）：** 整数 `Int64`/`UInt64`、布尔 `Boolean`、浮点 `Float32`/`Float64`（-0 归一）、二进制 `Binary`、BIT `FixedSizeBinary(⌈n/8⌉)`；DECIMAL、日期时间、ENUM、JSON、字符串用 `Utf8` 规范文本；SET 用按声明顺序以 `,` 连接的文本，与成员序列的互转规则写入映射；所有列可空性按规范 schema，NULL 用 Arrow validity；字段 metadata 记录声明类型与映射版本；超过 2 GiB offsets 时使用 large 变体。映射单独加版本号并进入规范表存储的内容地址；表摘要按规范标量编码计算，与 Arrow 物理类型无关。

### 8.2 规范表存储（DC42、DC55 第 3 项）

- **内容地址：** storage projection version、business schema digest、行数、表摘要、Arrow 映射版本；不含表名。文件内按规范顺序存放（keyed 按键、ordered 按 gid、keyless 按行哈希）。
- **格式：** 不压缩的 Arrow IPC，mmap 读取；读取时校验 raw SHA-256；写入用临时文件加原子 rename，删除写后回读。
- **引用（现有保护表 `artifact_protection_intents`）：** 临时引用即 Preview owner（T1 转移给 Attempt 的规则不变）；新增 owner 类型“项目当前 BaselineHead”，Submit finalize 在移动 head 的同一 control DB 事务中把引用移到新 head；释放后按 TTL 保留，TTL 从最后一次引用起算；复用时先登记保护再确认文件存在。
- **缺失或损坏时的来源与终态（DC55 第 3 项）：**

  | 状态 | 来源 | 终态 |
  | --- | --- | --- |
  | T1 之前（Preview 的上传侧表） | 从 SourcePackage 重算（重跑 Preview） | 用户重新 Preview；不影响已提交数据 |
  | T1 之后、prepare 构建导入包之前（冻结、未提交） | 无替代来源；不得用 parent 或运行期 ruleset 重建 | 稳定失败，不移动 main（与现行冻结 artifact 行为相同） |
  | PREPARED 之后 | 复用已冻结的导入包（`BackendArtifactRef` 与 raw SHA） | 按现行 Submit 恢复规则 |
  | 已提交表的派生副本（BaselineHead 正式引用与 TTL 副本） | 从对应的精确 commit 经 Dolt 读回、按表摘要校验后重写 | 只影响性能 |

- **同步写入：** Preview 中同步写入；T1 照旧冻结 MODIFIED 侧闭包与 manifest，闭包条目指向内容寻址的文件（ADR 0019 与 P5 收口设计 §4.6 的结构不变）。
- **基线读取：** Preview、Submit 与 History 读取已提交表时优先从存储 mmap 读取，未命中或校验失败由 Dolt 兜底并回填。
- **磁盘估算（设计核对项，S2b kickoff 前完成）：** 每个项目的 head、活跃 Preview 与 Attempt 的冻结表、TTL 内的旧表、导出缓存副本与临时高水位；与参考节点磁盘容量对照；超出预算时评估 LZ4，不引入按容量淘汰（Phase 7）。
- **比例化保障：** 不新增状态机、证据机制或 helper；已提交表副本的丢失或损坏只影响性能；冻结产物沿用现有保护与稳定失败规则。

### 8.3 并发与资源（DC47）

- 每个 worker 进程一个固定 N 的 Rayon 池，启动时建好，所有 kernel 共用；pyarrow 的 CPU 与 I/O 线程池按 N 设定；测试默认 N=1。
- **内存预算 M：** 准入估算包含常驻输入（上传侧与已读取的基线表）、输出（Arrow 结果、记录、IPC 缓冲）与每线程的临时内存，不能只按活动表的平均列宽；运行中任务的预估总和 ≤ M；单表超过 M 时以资源预算诊断稳定失败。V6、V1 实测内存随线程数增长（V1：16 线程约 1.2 GB）。
- **RS 读取：** operation 内并发 ≤ min(N, RS 有效容量)（容量为 RS 配置，默认 8）；503 作为背压退避重试，重试次数有界并继承 operation 的取消与截止时间。
- 所有长 kernel 复用同一套取消与失败边界；预算拒绝返回可诊断的失败，native crash 由 Operation Runtime 恢复。
- 部署配置只开放 N 与 M（有范围校验、写进测量记录）；其余为代码常量。N 在 S2b 后按整条路径的加速曲线暂定（V6 的解析器单独为 4），S6 定稿。

### 8.4 切换

- feature flag 切换上传侧到 Rust 路径；Python 路径保留至 S6（DC37 第 4 项）。
- 验收：t1–t4 端到端摘要与 §6 的基准一致；存储读取校验与 Dolt 兜底、冻结产物四种状态的权威测试；W2 可达性检查（§16.1）。

## 9. S3：比较与逐行记录

- **共用内核（DC44、V1）：** standard、keyless 与 ordered 在 `gateway-compute-core/src/comparison/` 中共用规范编码、共有列投影（DC40 的语义）、行身份、记录排序、资源上限与 facts 管线；ordered 专属的 LIS 主干、绝对 `no` 位置与空白区间规则留在 ordered 模块。
- **逐行记录（DC54）：** kernel 按记录族 schema 产出 Arrow 记录列，并用相同 JCS 编码计算 `content_digest`；Python 用 pyarrow 由 Arrow batch 写 Parquet。发布后的整份回读解码删除；实际读取时的 raw、content 与 schema 校验及普通 I/O 失败处理保留。记录产物与 Contract 不变，现有 golden 作为逐字节回归基准；如必须改动格式，按 Contract 变更另行提交 owner。
- **风险的消费接口：** 风险仍在 Python（DC47 第 1 项）。在 Preview 与 History 的计算路径中，风险直接消费 kernel 在内存中产出的 Arrow 记录，按表、按 batch 有界地读取，只转换风险规则需要的列，不先重建完整的 `ComparisonRecord` 元组；这条路径不从 Parquet 读回，因此没有读取校验成本。约 5 s（W4）的风险段是待 S3 验证的假设；超出 §16.1 预算时，按 DC47 第 1 项的重开条件评估风险热点进入 Rust。
- **记录的读取校验：** 只发生在从存储读取 closure 时（History 命中 diff/risk 缓存、bundle 组装）：raw、content 与 schema 校验由 Rust 对读出的 Arrow 重算 JCS `content_digest`，计入 H1、H3 与 bundle 的预算（§16.1）。
- **单次操作内去重（DC43）：** 缓存键为“去掉表名与显示名之后的单表任务输入”的摘要，包含比较与风险规则主体及其版本、两侧有效键与存储规则、schema digest、行数、算法与记录格式版本、artifact scope；表名、显示名、标注编号、pair 上限与组合信号表在汇总步骤绑定。权威测试：开启与关闭去重，facts 与 records 摘要相同。
- **分歧点：** 浮点 -0.0、NULL、字符串按字节排序、记录输出顺序、ordered 并列规则，按现行行为写进 Contract，不改语义（§4.6）。
- **接入：** feature flag 之后；差分覆盖第 ① 层语料、随机差分与 t1–t4。

## 10. S4：Submit

- **渲染直通（DC45 第 4 项）：** 变化表直接从冻结规范表（S2b 起为 IPC，mmap）渲染 SQL；导入路径不再构造逐行变化集对象、不计算无消费方的摘要；表级决定仍归规划器。
- **存储 diff：** 与 S3 共用比较内核，按存储键比较全部保留列。
- **阈值与批量规则：** 沿用 S1a 冻结值；S4 用最终渲染器与 RS 回放路径复测确认。须调整时作为例外交 owner（DC55 第 5 项）。
- **通用规划器与 ChangeSet Contract 保留**，作为 ADR 0014 外部目标的 owner（DC45 第 5 项）。
- **验收：** 同一输入的 `replay.sql` 与 S1a 逐字节一致；§16.2 的 Submit 计数；S1–S4 完成时间。

## 11. S5：History 与跨操作缓存

- **diff/risk 缓存（DC43）：** 只缓存纯函数结果——单表比较结果与未套用 pair 上限的单表风险标注；键同 §9 的单次去重键（含规则主体与版本、scope）；pair 上限、组合信号表与表名在汇总步骤绑定，命中后的结果与当前 operation 的 closure 重新绑定。条目作为 artifact 存放并经保护表登记引用；在计算时形成（Preview 或 History），按 TTL 保留；Submit finalize 在移动 head 的同一事务中给该 Submit 对应 Preview 的条目登记引用。
- **History 按表拼接（DC38）：** 两侧满足 §4.2 的完整条件 → 未变化（ordered 表的 facts 按 §4.1 用当前节点的行计算，或取自 diff/risk 缓存）；否则查 diff/risk 缓存 → 读表缓存 → Dolt 兜底并回填；pair 级 surface 与 bundle 由单表结果汇总。
- **Dolt 并发读取：** 同 §8.3。
- **计数与例外：** 见 §16.2 与 §16.3（H1 的零比较只在“该 pair 已计算、规则相同、缓存健康”时成立；FULL 模式 Preview 之后的首次 History 允许重算，DC38 第 4 项；缓存文件缺失或损坏时走回填，作为正确性场景单独验收）。
- **H2 定稿：** 两节点 2× t4 派生缓存全 miss 旅程验收；三节点补测一次，只报告。

## 12. S6：收尾

- 加速曲线定 N（DC35 第 5 项：1、2、4、8、16、32 线程，取并行效率约 60–70% 以上的最大值）。
- 删除生产 feature flag，Python 实现降为测试用参照（差分测试与小数据 oracle）。
- 按 §16.3 验收矩阵完成全部场景的取证与计数断言；存储报告（Performance Measurement §6）。
- 最终提交上运行完整权威 runner 与容器门禁，运行真实数据 t1–t4 一次。
- 结合 V8 方法重新剖析门禁时长（DC48 第 3 项）；Phase 6 退出审核。

## 13. 持久化、HTTP 与部署影响

| 面 | 影响 | 阶段 |
| --- | --- | --- |
| control DB | 保护表新增 owner 类型（BaselineHead 正式引用；导出缓存；diff/risk 缓存）；schema 基线直接修改，本地 DB 删除重建（DC6） | S1b、S2b、S5 |
| manifest | 每表内容摘要改值、删除 `ordering_digest`；不新增 ordered 字段 | S1a |
| checkpoint 载荷 | prepare checkpoint 绑定 parent manifest digest；Preview 与 History checkpoint 引用内容寻址文件 | S1a、S2b |
| HTTP | 上传超时的新错误码；Preview/History 结果中整表浏览的 surface；bundle 含整表 | S1b |
| 部署配置 | N、M（可修改、有范围校验） | S2b |
| 镜像 | backend Dockerfile：新 adapter 的 maturin 构建、Rust 依赖；强制重建项 | S2a 起 |
| Repository Service | 无 Contract 变化（零日期维持拒绝）；defunct 进程问题交 RS owner（可并入 kickoff 小修或 S1a，修复可能涉及 Dockerfile/Compose） | — |

## 14. Contract 修订清单

| 文档与现行条款 | 目标条款 | owner | 阶段 | golden / 测试 |
| --- | --- | --- | --- | --- |
| Canonical Storage §4：内容摘要按逐单元格规则、producer 不得自行排序；含 `ordering_digest` | 每表内容摘要为与行顺序无关的统一表摘要；删除 `ordering_digest`；投影版本 3 | Canonical Storage / Storage Projection | S1a | storage-projection |
| Canonical Storage §5：第一版不长期保存 full-row archive | 规范表存储的角色与生命周期：BaselineHead 正式引用、TTL 副本、冻结产物四种状态（§8.2） | Canonical Storage | S2b | 存储与恢复测试 |
| Canonical Storage §6.1：`replay.sql` 是 snapshot replay | 相对 expected parent 的确定性 replay，未变化表不出现 | Canonical Storage | S1a | 导入包 |
| Storage Mutation §2/§3：生产默认 `REBUILD_ALWAYS`；有序表不可 patch；阈值 5% | 生产默认 `ADAPTIVE_PATCH`；有序表可 patch；阈值 1,000 行 / 1%；§4 计数口径不变 | Storage Mutation | S1a | mutation |
| ADR 0014 与 Storage Mutation 中的条件 DML、affected-row、readback 要求 | 生产 Dolt 路径以 expected-parent CAS、parent 行按 manifest 校验与受信 Repository 为前提，不适用这些要求；外部目标保留 | Storage Mutation / ADR 0014 | S1a | — |
| Ordered Diff：逻辑摘要与 occupancy 摘要按比较计算；伪 gid 起点 20 亿 | 定义不变；对两侧内容相同的表，可用当前侧的行按本次有效 pair 策略计算并作为两侧的值；伪 gid 范围以 Canonical Storage G8 为准 | Comparison | S1a | ordered 测试 |
| ADR 0019 | manifest 每表字段作为结构性过滤输入；T1 冻结产物的恢复边界（§8.2） | ADR 0019 | S1a、S2b | — |
| Comparison：schema 变化即 `SCHEMA_CHANGED`；整表新增/删除逐行记录 | schema 演进分类与只增列；整表新增/删除不产逐行记录；`NO_CANONICAL_CHANGE` 说明 | Comparison | S1b | comparison |
| Comparison「Cache」：第一版只做 pair 级缓存，不做 table 级 facts 缓存 | 单表纯函数结果可按完整任务输入键缓存；pair 上限与表名在汇总绑定 | Comparison | S3（单次去重）、S5（跨操作） | 去重与缓存测试 |
| Comparison：分歧点 | 按现行行为写明 -0.0、NULL、字节排序、记录顺序、ordered 并列 | Comparison | S3 | 回归 |
| Risk：逐行新增风险；无缓存 | 表级计数风险；只增列无风险；未套用 pair 上限的单表标注可缓存，键含规则与版本 | Risk | S1b、S3/S5 | risk |
| Comparison Surface | 整表浏览映射 | Surface | S1b | surface |
| Comparison Bundle：标准模式无整表；snapshot Parquet cache 按 layout digest | 全部表打包；导出缓存按 row-layout 身份加 writer 版本命中 | Bundle | S1b | bundle |
| Snapshot Table Access：Parquet artifact、row-layout、scope 与可信等级 | 解析语义（§5.5）；规范表存储的 IPC 内容寻址文件与既有 artifact/cache 的边界 | Table Access | S1b、S2b | table-access |
| Shared Canonical Encoding | 不改条文；FLOAT 实现按条文修正；零日期维持拒绝 | Shared Kernel | S1b | shared-kernel 编码向量 |
| P5-5A 上传设计：60 s 总时限、413 | 空闲超时与总上限；`UPLOAD_STREAM_TIMEOUT` | Workspace HTTP | S1b | 上传 streaming 测试 |
| Canonical Row Hash Compute Boundary | 删除 | — | S2a | 删除 canonical-row-hash golden |

## 15. 测试归属

每个不变量一个权威测试 owner；其他层只做 smoke，引用既有 runtime、CAS 与 cleanup 测试，不新建平行框架（比例化保障政策）：

| 不变量 | 权威 owner（拟） | smoke |
| --- | --- | --- |
| 表摘要与行顺序无关、Dolt 读回可重算 | storage_projection 摘要测试 | — |
| 未变化 ordered 表的单侧计算与现算一致（含头部、内部、尾部空白；规则变化；schema 不同不判未变化） | ordered 比较测试 | — |
| 完整条件判定未变化（零行不同 schema、只改可空性不得误判） | Preview 结构过滤测试 | History 旅程 |
| Submit 跳过未变化表 | mutation planning 单元测试 | Compose Submit 旅程 |
| 阈值路由 | mutation planning 单元测试 | — |
| prepare 绑定 parent manifest、parent 行校验 | prepare checkpoint 测试 | — |
| 只增列按共有列判定 | comparison schema 演进测试 | — |
| bundle 含全部表、导出缓存不误命中 | bundle 组装测试 | — |
| 上传空闲超时与总上限、错误码 | 上传 streaming 测试（serial） | — |
| 规范表存储读取校验与 Dolt 兜底；冻结产物缺失稳定失败 | 存储读取测试；Submit 恢复测试 | — |
| 保护转移（BaselineHead 正式引用随 finalize 同事务移动） | finalize 事务测试 | — |
| RS 503 退避有界、继承取消与截止时间 | repository read 客户端测试 | — |
| native crash 由 runtime 接管 | 既有 worker 恢复测试 | — |
| Rust 与 Python 逐值 / 逐字节一致；1 与 N 线程相同 | 各 kernel 的差分与确定性测试 | 真实数据取证 |
| 去重开关不改结果；缓存只缓存纯函数结果 | comparison 去重与缓存测试 | — |

## 16. 性能测量与验收

### 16.1 端到端预算与 W2 检查点（2× t4，N=4）

下表是**不重叠**的分项账：每一项只计一次，不与包含它的阶段重复相加。“工作量”按 2× t4（约 624 张规范表、约 49 万行、约 159 MB SQL）计；“依据”标明是实测（原型或旧路径在 t4 / 2× t4 上的数）、外推（工作量 × 假设吞吐）还是未知。未知项必须在所列检查点给出实测值。

| 段 | 工作量 × 吞吐假设 | W1 | W2 | W3 | W4 | 依据 | 检查点 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| a 受理（解压、校验、写入 SourcePackage） | 160 MB × 415 MiB/s 解压，另加写入 | ~1 s | ~1 s | ~1 s | ~1 s | 外推（S5 解压吞吐） | S1b |
| b SQL 解析 | V6：2× t4 在 N=4 时 0.481 s | 0.5 s | 0.5 s | 0.5 s | 0.5 s | 实测（V6 原型，2× t4） | S2b |
| c 物化检查、投影、摘要 | 约 49 万行；按 V6 单行成本的 2–5 倍 | ~2–5 s | 同 | 同 | 同 | 外推 | S2b |
| d 规范表写入 | 约 1,248 次写入 × 约 11 ms（旧 Parquet 路径每次 `put` 的平均成本） | ~14 s | 0（内容命中，不重写） | ~2 s | ~14 s | 外推（V5b 旧路径线性加倍；新 IPC 路径须实测） | S2b |
| e 未变化 ordered 表的单侧摘要 | 未变化 ordered 表的行数 × 编码与哈希吞吐 | 0 | 未知（Python）；Rust 后 <1 s | 同 | 0 | 未知 | S1a（Python）、S3（Rust） |
| f 基线读取（变化表与删除表） | \|X\|+\|D\| 张表，存储 mmap 命中 | 0 | 0 | ~1 s | ~1–5 s | 外推 | S2b |
| g 行比较与逐行记录 | 变化行数 × V1 单行成本（约 22 µs/行，单线程） | 0 | 0 | ~2 s | ~5–10 s | 外推（V1，不含 IPC 与输出编码） | S3 |
| h 风险（Python，消费内存中的 Arrow 记录） | W4 约 5 万条 × 约 0.1 ms/条 | 0 | 0 | ~1 s | ~5 s | 外推（V5b 现行约 0.11 ms/条），假设 | S3 |
| i bundle 组装与导出 | W1、W3、W4 导出整表 Parquet；W2 导出缓存命中，只组装清单 | 未知 | 未知 | 未知 | 未知 | 未知（含 §4.4 的 assemble 固定开销） | S1b、S2b |
| j step 间隔 | 每个 Preview 两处，单处 1.0–9.8 s | 2–20 s | 2–20 s | 2–20 s | 2–20 s | 实测（V5） | S1a 归因 |
| k 未归因残差 | 基线物化约 75 s、assemble 约 100 s | 未知 | 未知 | 未知 | 未知 | 待归因（V5b） | S1a 归因 |
| **已知项小计（a–h，不含 e、i、j、k）** | | ~18–21 s | ~4–7 s | ~10–13 s | ~29–41 s | | |

- **W2 检查点（S2b，可判定）：** 以 S2b 实测的 W2（受理到 READY，§16.3 的统计方法）为锚，列出仍在路径上的各项实测成本，以及每项有依据、有具名阶段的剩余削减上界：

  ```text
  W2_S2b − Σ 剩余削减上界（每项须有证据与阶段，未归因残差计 0）≤ 30 s  → 继续
  否则，或 W2_S2b 中仍有未归因项                                          → 停止，交 owner（DC53 第 2 项）
  ```

  W2 不做行比较，S3 对比较的加速不能计入 W2 的削减。
- **W4：** 计算路径中不存在未计入的逐行 Python 转换或回读：记录由 Rust 产出（S3），风险消费内存中的 Arrow 记录，Parquet 只写不读；读取校验只在 History 与 bundle 读取 closure 时由 Rust 进行。S3 用 W4 实测核对 g、h；风险段超出预算时按 DC47 第 1 项评估。
- 原型吞吐不冒充生产端到端结果；预算用于排序与判停，不作为达标证据。

### 16.2 计数断言（DC55 第 5 项）

**表集合：** 对每张表按两侧比较：未变 U（两侧都存在且满足 §4.2 完整条件）、变化 X（两侧都存在但不满足）、新增 A（只在当前侧）、删除 D（只在基线侧）。

**读取：区分逻辑需求与实际读取。**

| 断言 | 内容 | 观测点 |
| --- | --- | --- |
| Preview 基线的逻辑需求 | 需要基线侧行的表 = X ∪ D | 管线的需求记录 |
| Preview 基线的实际读取 | 按 (commit, 内容身份) 去重后的实际读取数 ≤ \|X\|+\|D\|；其中 Dolt 读取数 = 存储未命中或校验失败的表数。**W2：需求为 0，实际读取为 0** | 存储与 RS 读取计数 |
| History（每个 pair） | 需求按层分别记录，跨层按 (commit, 内容身份) 合并去重后再计算实际读取：<br>• **行比较**（diff/risk 未命中的 X 表）：需要旧节点与当前节点两侧的行，即 old-X 与 current-X；<br>• **表级处理**：D 表需要旧节点的行用于整表浏览与导出；<br>• **单侧摘要**（diff/risk 未命中的未变 ordered 表）：需要当前节点的行；<br>• **整表打包**：两个节点全部表的导出，命中导出缓存则不读表。<br>diff/risk 健康命中消除该表的行比较与单侧摘要需求，但不消除整表打包需求。实际 Dolt 读取数 = 合并后的需求中存储副本缺失或校验失败的 (commit, 表) 数 | 存储、RS 与缓存计数 |

**比较：**

| 断言 | 内容 |
| --- | --- |
| 行比较的逻辑派发 | = \|X\| |
| 表级处理 | = \|A\| + \|D\|（整表浏览与表级风险） |
| 实际 kernel 调用 | ≤ \|X\|（单次去重、diff/risk 缓存命中后更少） |
| 未变 ordered 表的单侧摘要计算 | = 未变 ordered 表中未命中 diff/risk 缓存的表数 |

**Submit：** 不断言 SQL 语句数（INSERT 现为批量，按表与列身份、每条最多 256 行和字节上限切分）。

| 断言 | 内容 | 观测点 |
| --- | --- | --- |
| 表级决定 | 进入 `replay.sql` 的表 = X ∪ A ∪ D；X 中每表的决定为行级修改或整表重建（按 S1a 冻结的阈值），A 为整表重建，D 为 `DROP` | 规划器的表级决定 |
| 行级修改表 | 逻辑变更数 = 独立计算的净 diff：同键 UPDATE 计 1，键变化计 DELETE + INSERT 2，新增行 INSERT 1，删除行 DELETE 1（Storage Mutation §4） | 规划器的变更列表 |
| 整表重建表 | 写入行数 = 变化后的行数 | 渲染统计 |
| 删除表 | `DROP` 1 次，写入 0 行 | 渲染统计 |
| 规划器的 `changed_row_count` | 保持现行定义（行级修改表为净变化，新增/删除表为 before + after，投影变化表为全表计数），只作报告，不作为验收 | 规划器摘要 |
| 原样重传（S2） | 不产生 Repository operation | 受理结果 |

**History 的零计算条件：** H1（该 pair 已在 Preview 或 History 中计算、规则相同、缓存健康）与 H3：Dolt 读取数 = 0，kernel 调用数 = 0，单侧摘要计算数 = 0。

**手算示例**（其余表均未变；行级修改示例的前提：表为合格的 keyed 表，约 1,000 行，schema、键与存储视图不变，变化在冻结阈值内，单批不超字节上限）：

| 场景 | 集合 | Preview 基线实际读取 | 行比较 / 表级 | kernel | 表级决定 | 逻辑变更或写入 |
| --- | --- | ---: | --- | ---: | --- | --- |
| keyed 表 t 新增两行 | X={t} | 1 | 1 / 0 | 1 | 行级修改 | INSERT×2（SQL 可为 1 条，不断言） |
| keyed 表 t 一行的键变化 | X={t} | 1 | 1 / 0 | 1 | 行级修改 | DELETE + INSERT = 2 |
| 100 行 keyed 表 t 修改 6 行（6% 超过 1% 阈值） | X={t} | 1 | 1 / 0 | 1 | 整表重建 | 写入 100 行；`changed_row_count`=6，只报告 |
| 只有新增表 t（n 行） | A={t} | 0 | 0 / 1 | 0 | 整表重建 | 写入 n 行 |
| 只有删除表 t（10 行） | D={t} | 1（bundle 需要基线侧数据） | 0 / 1 | 0 | `DROP` | 写入 0 行；`changed_row_count`=10，只报告 |
| 两张同内容表 t1、t2 发生相同变化 | X={t1,t2} | ≤ 2（同内容身份可共享一次读取） | 2 / 0 | 1（去重后） | 各自按表 | 各自按表 |
| History：diff/risk 缓存缺失，但两节点规范表副本健康 | X={t}（非 ordered） | Dolt 0（两侧都从存储读） | 1 / 0 | 1 | — | — |
| History：diff/risk 缓存缺失；旧节点规范表健康，当前节点 t 的规范表缺失；两侧导出缓存均健康 | X={t}（非 ordered） | Dolt 1（当前 commit 的 t，按 §8.2 回填） | 1 / 0 | 1 | — | — |
| History：H3 重复查询，缓存健康 | — | Dolt 0 | 派发照常记录 | 0 | — | — |

### 16.3 验收矩阵

| 场景 | 模式与条件 | 时点 | 判定 | 阶段 |
| --- | --- | --- | --- | --- |
| W1 | MODIFIED_ONLY，冷启动 | READY（门槛）、完成（≤ 10 min） | 门槛 | S2b 起测，S6 取证 |
| W2 | MODIFIED_ONLY，允许命中上一次 Preview 的临时条目并写明 | 同上 | 门槛 | S2b 检查点，S6 取证 |
| W3 | MODIFIED_ONLY；另 FULL 一次 | 同上 | 门槛 | S3 起测，S6 取证 |
| W4 | MODIFIED_ONLY，冷启动；另 FULL 一次 | 同上 | 门槛 | S3 起测，S6 取证 |
| W4 压力档 | 每表 100% 行变化 | 同上 | 只报告 | S3、S6 |
| H1 | 普通 Preview 之后，缓存健康，规则相同 | READY | 门槛 + 计数（零读零比） | S5 |
| H1-FULL | FULL Preview 之后的首次 History | READY | 门槛；允许重算变化表 | S5 |
| H1-回填 | TTL 内但缓存文件缺失或损坏 | READY | 结果正确、回填成功（正确性场景） | S5 |
| H2 | 两节点，派生缓存全 miss | READY | 门槛（S5 定稿） | S5 |
| H2-三节点 | 三节点，派生缓存全 miss | 完成 | 只报告；≤ 10 min | S5、S6 |
| H3 | TTL 内重复查询 | READY | 门槛 + 计数 | S5 |
| S1 / S3 / S4 | W1 / W3 / W4 之后的 Submit | 完成（main 前移） | 门槛 + 计数 | S4、S6 |
| S2 | 原样重传之后的 Submit | 受理 | 不产生 Repository operation | S1a 起 |

每个负载 1 次预热加 3 次测量取中位数并报告范围；失败运行不计入；门槛只在取证运行中判定（DC35 第 8 项）。

### 16.4 runbook

测量在 `ct108-gw-dms` 独占；日志开头记录 hostname、起止时间与 HEAD；W1、W4 冷启动（存储中只有已提交基线的条目），W2、W3 允许命中上一次 Preview 的临时条目并写明；清空派生缓存模拟 H2；合成负载规则见 §5.6。

## 17. 停止条件与开放项

停止条件（遇到即停止并报告 owner）：

1. S1a 的归因（§4.4）无法解释 step 间隔或约 175 s 残差的来源；
2. S2b 的 W2 检查点判定为停止（§16.1 的判定式）；
3. 任一 Rust kernel 与参照实现出现无法归入“参照实现不符合 Contract”的差异；
4. 阈值复测显示 1% 仍比整表重建慢，或 S4 实测要求调整 S1a 冻结的阈值或批量规则；
5. 规范表存储的磁盘估算超出参考节点容量；
6. 逐行记录必须改变产物格式（DC54 第 4 项）；
7. 某阶段的门槛在设计手段用尽后仍不能达到。

开放项（本设计提案，待复审与 owner 确认）：

| 项 | 本设计提案 | 节 |
| --- | --- | --- |
| `ordering_digest`、`fast_row_digest` | 删除前者（含跨模块传递）；保留后者，删除须重开决定 | §4.1 |
| 上传超时错误码 | `UPLOAD_STREAM_TIMEOUT`，HTTP 408，两种超时共用并附原因 | §5.4 |
| 参照解析器的 P 项语义 | §5.5 表中各项；深层 JSON 有界拒绝 | §5.5 |
| Arrow 列映射 v1 | §8.1 | §8.1 |
| 上传侧原始表的使用方、磁盘估算 | 设计核对项，S2b kickoff 前完成 | §8.1、§8.2 |
| 重要 keyless 表的自然键 | 已定（DC56）：11 张表补显式键，17 张表加入 BROWSE_ONLY，存储保持 keyless；规则改动在 S1b，与比较类 golden 一起冻结；`forwardtable_*` 保持 SNAPSHOT_ONLY，空点行调查已完成，不另行立项（DC56 第 4 项结论） | §4.6 |

## 附录 A：S0 独立文档审核 findings 处置

| finding | 类型 | 处置 | 位置 |
| --- | --- | --- | --- |
| F1 ordered 摘要变更与 bundle digest 冻结冲突 | 阻塞 | （r2 处置，其中“写入 manifest”的做法已由下方第 1 次复审 F1 行取代）owner 修订 DC39 第 3 项（DC55 第 1 项）：逻辑摘要定义不变，投影时计算并连同策略摘要写入 manifest；新增摘要变化与保值清单与 golden 生命周期；Ordered Diff 修订列入清单；S3 分歧点只写现行行为 | §4.1、§4.6、§9、§14 |
| F2 内容摘要当作完整表身份 | 阻塞 | owner 修订 DC41 第 2 项（DC55 第 2 项）：导出缓存键为 row-layout 身份加 writer 版本；未变化统一用完整条件；表名绑定保留；权威测试列入 §15 | §4.2、§5.2、§11、§15 |
| F3 冻结产物不能由 Dolt 回填 | 阻塞 | owner 修订 DC42 第 5 项（DC55 第 3 项）：四种状态的来源与终态；parent 行按 manifest 校验与 CAS | §3、§4.3、§8.2、§15 |
| F4 零日期跨服务语义 | 阻塞 | owner 决定维持拒绝（DC55 第 4 项）；FLOAT 修复归 Shared Kernel，列入 S1b 路径预算与 golden | §5.5、§13、§14；执行计划 §3 |
| F5 计数与字节验收冲突 | 阻塞 | owner 修订 DC45 第 2、7 项（DC55 第 5 项）：逻辑计数公式与观测点；阈值与批量规则在 S1a 冻结，S4 例外交 owner | §4.3、§10、§16.2 |
| F6 W2/W4 端到端预算 | 阻塞 | 增加端到端预算表（实测、外推、待归因）；S1a 归因给出处理节点；S2b 设 W2 可达性检查点；风险按 Arrow 分批消费；删除发布后回读但保留读取校验 | §4.4、§9、§16.1、§17 |
| F7 验收矩阵遗漏 | 阻塞 | 新增验收矩阵：FULL、三节点、READY 与完成、H1 条件与 FULL 例外、缓存缺失回填；S6 明列完整门禁；执行计划中 S2a 前置包含重建基准 | §11、§12、§16.3；执行计划 §2 |
| F8 Contract 修订清单不完整 | 阻塞 | 新增“现行条款 → 目标条款 → owner → 阶段 → golden/测试”清单，覆盖 Comparison Cache、Risk、Snapshot Table Access、ADR 0014 与 Storage Mutation 的生产路径条款；缓存键含规则与版本 | §9、§11、§14 |
| F9 测试归属与资源边界 | 非阻塞 | 拆分测试 owner；RS 并发 ≤ min(N, RS 容量)，重试继承取消与截止时间；M 估算口径；native crash 与预算拒绝区分 | §7、§8.3、§15 |
| F10 事实与引用校正 | 非阻塞 | `ordering_digest` 的跨模块传递；RS 容量为可配置默认值；V5 间隔的实际差异；P5 收口设计 §4.6 链接；DC42 回读条目引用改为第 5 项；讨论稿版本标记；S2a 路径预算补列 build-input 检查与 `import_rules` | §2.1、§2.2、§7、§8.2；执行计划 §3 |
| 第 1 次复审 F1（部分关闭） | 阻塞 | owner 再修订 DC55 第 1 项：取消 manifest 新字段；未变化 ordered 表用当前侧的行按本次有效 pair 策略计算逻辑摘要与 occupancy 摘要，两侧取同一值，不读基线侧；保值清单与 Contract 清单相应修改 | §4.1、§4.2、§11、§14 |
| 第 1 次复审 F11（预计算摘要漏掉当前 pair 的有效策略） | 阻塞 | 同上：始终使用本次受理冻结的有效 pair 策略（含共有列）计算，规则变化或 schema 不同不会复用历史值；schema 不同时不满足“未变化”完整条件，走行比较 | §4.1、§4.2、§15 |
| 第 1 次复审 F12（manifest 字段不足以生成 blank facts） | 阻塞 | 同上：occupancy 摘要与其余 facts 字段都由当前侧的行现算，不依赖 manifest；权威测试覆盖头部、内部、尾部空白 | §4.1、§15 |
| 第 1 次复审 F5（部分关闭） | 阻塞 | Submit 分列表级决定、行级修改的逻辑变更数、整表重建的写入行数与删除表；`changed_row_count` 保持现行定义只作报告；读取区分逻辑需求与实际读取，按层与缓存状态计算；手算示例补路由与缓存前提，增加整表重建与只缺 diff/risk 缓存的例子 | §16.2 |
| 第 1 次复审 F6（部分关闭） | 阻塞 | 预算改为不重叠分项账，逐项写工作量 × 吞吐假设与依据，未知项绑定检查点；S2b W2 检查点给出判定式，未归因残差不计入可削减额度；风险消费内存中的 Arrow 记录，读取校验只在从存储读 closure 时由 Rust 进行并计入 H1/H3 与 bundle 预算；风险约 5 s 标为待验证假设 | §9、§16.1 |
| 第 1 次复审的导航文字提醒 | 非阻塞 | 决议记录待定表、后续步骤与执行计划 S0 的版本与编号已对齐 | 决议记录 §3、§5；执行计划 §2 |
| 第 2 次复审 F5（部分关闭） | 阻塞 | History 的读取需求改为按 pair 分层列出：行比较需要 old-X 与 current-X 两侧，D 表的表级处理与导出、未变 ordered 的单侧摘要、整表打包各自独立；跨层按 (commit, 内容身份) 合并去重后计算实际 Dolt 读取；diff/risk 命中只消除行比较与单侧摘要需求。补“当前节点规范表缺失、导出命中”读 Dolt 1 次与“两侧健康”0 次两例 | §16.2 |
| 第 2 次复审 F13（非阻塞） | 非阻塞 | S2b 上传路径删除 ordered 逻辑摘要的预计算；单侧摘要只在 assemble 中按 pair 计算一次，S1a 用 Python、S3 起用 Rust，预算 e 项的阶段一致 | §4.2、§8.1 |
| 第 2 次复审 §7.3 的实施约束（非 finding） | — | 写入 §4.2：当前侧规范行来源按 pair 与模式区分、经 checkpoint 或存储 reader 读取；有效策略仍由两侧描述符构造；使用规范 provenance；facts 按既有结构填充并保留 degraded 语义；不得复用 `_compare_single_side` | §4.2 |

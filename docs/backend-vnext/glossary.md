# 后端 vNext 术语表

本文是 gateway 后端 vNext 的第一版术语草案，用于人和 AI 共同对齐语义。它不是最终代码 contract；后续如果某个术语进入接口、数据库 schema 或模块名，应在对应设计文档中进一步固化。

## 使用约定

- 文档说明优先使用中文术语，括号或代码样式中保留英文候选名。
- PascalCase 名称通常表示候选业务对象、值对象或 contract，例如 `SnapshotTableReader`。
- snake_case 名称通常表示候选字段、能力名或 cache 层名，例如 `sql_source_digest`、`snapshot_materialization`。
- enum / status 值保留英文大写，例如 `ACCEPTED`、`READY`、`FAILED_FINAL`。
- 如果英文词已经是项目内部稳定表达，例如 upload、submit、preview、cache、bundle、digest，可以在中文句子中直接使用。
- 对于非程序标识符，优先使用统一中文译法，避免同一概念出现多个中文名。

## 常见翻译约定

| 英文 | 推荐中文 | 说明 |
| --- | --- | --- |
| artifact | 产物 / artifact | 泛指系统持久化或交付的文件对象时可用“产物”；作为类别或字段名时可保留 artifact。 |
| artifact closure | 产物闭包 | 指某个 operation/bundle 对外可读所需的一组完整 artifacts。 |
| operation artifact closure | operation 产物闭包 | READY 前必须闭合，不能依赖未来 cache 回填。 |
| business truth | 业务事实 | 不译成“业务真相”。指受状态机和审计保护、不可用 cache 替代的事实。 |
| durable | 持久 / 已可靠保存 | 强调可恢复、可校验，不等同于业务事实。 |
| staged durable | 已暂存持久态 | L1 等级，通常用于 source package、binding、operation record。 |
| immutable | 不可变 | 常用于 repository commit/ref、snapshot/ref、归档 candidate。 |
| mutable | 可变 | 常用于 workspace branch、临时 ref。 |
| finalize | 固化 | submit 后台入库、创建不可变 ref、推进业务状态的动作。 |
| acceptance | 接收校验 | submit 同步阶段，只表示请求被可靠接收并通过初步校验。 |
| accepted | 已接收 | 不表示 repository commit 成功，也不表示进入审核状态。 |
| rejected | 已拒绝 / 拒绝 | 同步校验失败或业务状态拒绝。 |
| ready | 就绪 / READY | 作为状态值时保留 `READY`。 |
| surface | 展示结构 | 指前端可消费的展示层数据，不等同于 UI 页面。 |
| bundle | 包 / bundle | 指可下载或可离线加载的文件包。 |
| provider | 执行路线 / provider | 指 capability 内部的执行策略，不是外部服务提供方。 |
| provider planning | provider 规划 | 基于输入来源、summary、table rules 选择执行路线。 |
| provider decision | 执行路线决策 / `ProviderDecision` | 通常是表级或表组级决策。 |
| fallback | 回退 | 主路线不适用时使用的通用路线。 |
| materialize | 物化 | 把 source/ref 转成可读取、可比较、可持久化的结构。 |
| materialization | 物化 | 名词形式。 |
| readback | 读回 | 从 repository、artifact 或 cache 读回可比较数据。 |
| export | 导出 | 从 repository/Dolt 导出表或数据。 |
| pin | pin / 固定 | 保证 cache entry 或 artifact 在一段时间内不被 cleanup 删除。 |
| release | release / 释放 | 解除生命周期保护。 |
| cache hit | cache 命中 | 可复用已有 cache entry。 |
| cache miss | cache 未命中 | 必须回退到重算或其他 provider。 |
| cache warmup | cache 预热 | 异步生成或补充 cache，不应作为业务成功条件。 |
| cleanup | 清理 | 删除临时目录、过期 artifacts 或未 pinned cache。 |
| diagnostics | 诊断信息 | 供排查和性能分析使用，不是业务状态。 |
| trace | trace / 跟踪记录 | 记录 phase、duration、cache result、provider 等执行细节。 |
| audit | 审计 | 记录 actor、时间、原因、状态变化等业务可追溯事实。 |

## 分层术语

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| Flow | 业务流程 | 描述业务对象、用户动作、权限、状态机和生命周期。 |
| Operation | 执行编排 / operation | 把一次业务动作拆成可执行步骤，负责重试、取消、并发、失败和诊断。 |
| Capability | 能力 | 可复用技术能力，拥有稳定输入输出，不绑定 upload、submit 或 history compare。 |
| Provider | 执行路线 / provider | Capability 内部选择的具体执行策略。 |
| Contract | 契约 / contract | 对外 API、跨模块输入输出、artifact 格式或 cache key 规则。 |
| DIRECT_RESPONSE_CALLER | 直接反馈调用者 | 效率优先的直接反馈路径，不执行重负载 repository import。 |
| READ_ONLY_CALLER | 只读调用者 | 只读流程调用者，不执行 repository import，只读取 validated cache 或 repository facts。 |
| WARMUP_CALLER | 预热调用者 | 异步预热或 shadow benchmark 调用者，只能产生 candidate/provisional 结果。 |
| FINALIZE_WRITE_CALLER | 正式写入调用者 | 正式写入路径调用者，必须持有 writer lease 并做 readback validation。 |

基本关系：

```text
业务流程 Flow
  -> 创建 Operation
  -> Operation 调用 Capability
  -> Capability 内部选择 Provider
```

## 业务对象

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| Workspace | 工作区 | 用户围绕某个 gateway/baseline 准备、预览和提交配置变更的业务空间。 |
| Submission | 提交记录 / submission | 用户把某个 preview 提交后形成的业务记录，后续进入审核、归档或撤回。 |
| SourcePackage | 源包 / 输入包 | 用户上传或系统接收的原始多目录多文件配置包。它是输入容器事实，不负责解析 SQL 或生成 SnapshotTable。 |
| SourceDocumentRef | 源文档引用 | 指向 SourcePackage 内某个可解析文档的内部引用，例如 `/sql/dbcfg.sql`。 |
| SqlDumpSource | SQL dump 来源 | SQL materialization 的输入对象；当前业务默认由 `/sql/dbcfg.sql` 的 SourceDocumentRef 派生，也可由兼容 SQL 文件或测试输入构造。 |
| SQL_FILE | 裸 SQL 输入 | 测试或 benchmark 使用的单 SQL 文件输入，显式映射为 `/sql/dbcfg.sql`。 |
| SQL_GZ | gzip SQL 输入 | 测试或 benchmark 使用的单 `.sql.gz` 输入，解压后映射为 `/sql/dbcfg.sql`。 |
| PreviewInputBinding | Preview 输入绑定 | upload preview 阶段冻结的输入绑定，用于证明 submit full package 可复现 preview-relevant input。 |
| SubmitSourcePackage | Submit 完整源包 | submit 阶段上传并持久化的完整数据目录，是 finalize 的 L1 输入。 |
| Snapshot | 快照 | 从 SourcePackage、repository commit/ref 或其他可信来源得到的一次可比较配置状态。 |
| SnapshotSummary | 快照摘要 | Snapshot 的轻量摘要；PROVISIONAL 形态用于 upload/preview，FINAL 形态会落到 repository commit/ref 内的隐藏系统表，包含表集合、digest、版本上下文和 provider 规划所需事实。 |
| Hidden summary table | 隐藏摘要表 | repository commit/ref 内的隐藏系统表，承载 FINAL SnapshotSummary 的 compare-ready facts；history compare / archive 只读读取。 |
| Comparison | 比较结果 / comparison | 两个 ComparisonInput 之间的一次有向比较结果。 |
| RiskEvaluation | 风险评估 | 基于 ComparisonFacts 计算出的风险等级、原因和 annotation。 |
| ComparisonSurface | 比较展示结构 | 前端查看比较结果所需的展示层结构，不携带 upload/submit 私有 binding。 |
| WorkbenchBundle | Workbench 包 | 可被 Diff Workbench 离线/只读加载的文件包，是 UI adapter，不等同于业务事实。 |
| ArchiveSelection | 归档选择 | 归档或推进 mainline 时选定的 candidate 事实。 |
| Repository | Repository / 仓库 | 承载 Dolt commit/ref/mainline 等持久状态的后端存储上下文。 |
| RepositoryRegistry | Repository 注册表 | repository-local 技术元数据持久化层，保存 artifact/cache/scan/debug-hold 等 repository-local facts；v1 以 per-repository SQLite 承载。 |
| RepositoryTableAccessProvider | Repository 表访问 provider | repository_server 暴露给 snapshot materialization 的入口，用于 `open_ref()`。 |
| RepositoryRefSession | Repository ref session | repository server 打开某个 immutable ref 后形成的表 catalog + lazy table access 会话。 |
| RepositoryTableCatalog | Repository 表目录 | repository ref 下的表清单、schema facts、row count 和可选 table root/hash metadata。 |
| RepositoryTableReader | Repository 表读取器 | repository server 提供的通用表 row stream，不直接等同 SnapshotTableReader。 |
| RepositoryTableExportArtifact | Repository 表导出产物 | repository_server 可选导出的 repository-local 表文件，需经 snapshot materialization 校验后才能成为 SnapshotTableArtifact。 |
| RepositoryServerTableCache | Repository server 表 cache | repository server 内部跨 session 技术 cache，用于 catalog、describe/count、export artifact 等 repository-local 结果。 |
| ScalarEncoding | Scalar encoding / 标量编码 | 将 SQL/repository/readback 中的标量值归一化为稳定 digest 输入的规则。第一版位于 snapshot materialization。 |
| RepositoryImportPlan | Repository 导入计划 | 将 Snapshot/SourcePackage 导入 repository/Dolt 的计划，包含目标 ref、表清单、provider 和校验策略。 |
| RepositoryImportResult | Repository 导入结果 | Repository import capability 的输出，包含 commit/ref、provider、校验结果和诊断。 |
| Artifact | 产物 / artifact | 系统持久化或交付的文件/对象，包括 source、derived、bundle、cache 等类别。 |
| CacheEntry | Cache 记录 | 可重算内容的缓存记录，不是业务事实。 |

## 流程术语

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| Create Workspace | 创建 Workspace | 创建或读取当前用户工作区。 |
| Prepare Snapshot Input | 准备 Snapshot 输入 | 上传 SQL package 或选择 repository source，生成可比较 Snapshot。 |
| Stage Initial Snapshot | 暂存 Initial Snapshot | 分阶段上传 initial package，并在 workspace 中记录 before-role Snapshot。 |
| Build Preview From Modified Snapshot | 基于 Modified Snapshot 构建 Preview | before Snapshot 已存在时上传 modified package 并构建 preview。 |
| Build Preview From Initial And Modified | 基于 Initial 与 Modified 构建 Preview | 同一次业务动作上传 initial 和 modified，并完成比较。 |
| Build Baseline To Initial Diagnostics | 构建 Baseline 到 Initial 的诊断比较 | baseline/mainline 与 initial Snapshot 做诊断比较，不改写主 preview。 |
| Submit Acceptance | Submit 接收校验 | submit 同步阶段，校验完整包、binding、generation 和权限。 |
| Submit Finalize | Submit 后台固化 | submit 异步阶段，导入 repository/Dolt 并创建 immutable snapshot/ref。 |
| Review | 审核 | approve、reject、withdraw 等 submission 状态转移。 |
| Archive / Promote Mainline | 归档 / 推进 Mainline | 将已审核/选定 candidate 推进为新的 mainline 业务事实。 |
| History Compare | 历史比较 | 对 2/3 个历史节点生成只读 comparison surface / workbench bundle。 |

## 比较术语

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| ComparisonInput | 比较输入 | Directed comparison 的一侧输入，带 before/current 角色、来源类型、summary 和 table access。 |
| Directed comparison | 有向比较 | `before -> current` 的比较。方向会影响 add/delete、risk 和展示语义。 |
| before | before / 比较前 | Directed comparison 的左侧或基准侧角色。 |
| current | current / 比较后 | Directed comparison 的右侧或当前侧角色。 |
| Input Pair | 输入 pair / 输入对 | before/current 两侧输入组合，用于 pair 级 provider 默认规划。 |
| ComparisonPlan | Comparison 计划 | 基于输入来源、summary、ruleset 和 cache 状态生成的 provider 规划。 |
| ComparisonFacts | 比较事实 | comparison compute 输出的标准化事实集合，供 risk、surface、diagnostics 消费。 |
| ComparisonTableFact | 表级比较事实 | 单表 status、schema change、row count、records ref 和 diagnostics。 |
| ComparisonRecords | 比较记录 | diff compute 之后的行级/表级记录，不是输入表格式。 |
| ComparisonRecord | 比较记录行 | 单条 row/schema/table degraded 差异记录。 |
| ComparisonRecordsArtifactManifest | 比较记录产物清单 | 单表 records artifact 的格式、行数和 content digest，不包含 comparison digest。 |
| ComparisonRecordsClosure | 比较记录闭包 | 绑定 ComparisonFacts 与 records artifacts 的 manifest，用于 operation READY、cache restore 和 bundle assembly。 |
| ComparisonCoreCache | 比较核心缓存 | 缓存 directed comparison 的 neutral facts core 与 records closure，不缓存 risk/surface。 |
| NativeDiffCanonicalizer | Dolt native diff 归一化器 | 将 Dolt raw diff 映射为 vNext ProjectionSchema、ComparisonRecord、ComparisonTableFact 和 canonical digest 的 provider 内部模块。 |
| OrderedDiff | 有序表 diff | 针对 position、move、interval、blank slot 等有序语义的 comparison extension。 |
| OrderedTablePolicy | 有序表策略 | Flow 选择并冻结到 table ruleset 的有序表规则，包含 order key、row identity、blank policy 和 move policy。 |
| OrderedRecord | 有序差异记录 | `ORDERED_TABLE_COMPARE` 输出的 row/position/interval 级差异记录。 |
| OrderedInterval | 有序区间 | 有序表中连续新增、删除或变化的 position 区间。 |
| PseudoBlank | 伪 blank 行 | ordered table 中缺失/空 stable key 的空位行，沿用旧实现以 pseudo key 表达。 |
| OrderedTableProcessingMode | 有序表处理模式 | ordered diff 对 tail segment、local patch、shift repaired、complex reorder、degraded 的分类。 |
| ArtifactClosure | 产物闭包 | 将结果对象引用的 artifacts 闭合为当前 operation/bundle 可读取、可校验 refs 的通用支撑能力。 |
| ComparisonSurface | 比较展示结构 | 面向前端或 workbench 的展示层结构。 |
| SurfaceTable | 展示表条目 | ComparisonSurface 内的单表展示条目，包含 table status、display strategy、records/risk refs 和 diagnostics。 |
| ComparisonBundle | 比较 bundle | 一个或多个 ComparisonSurface 及其 artifacts 的闭合交付单元。 |
| BundlePair | Bundle pair | ComparisonBundle 中的一段 directed comparison surface，例如 `left_to_right`。 |
| FlowEnvelope | 流程 envelope | Flow 在 bundle core 外包裹的业务 metadata，例如权限、TTL、operation/download 信息。 |
| WorkbenchBundleAdapter | Workbench bundle adapter | 为 Workbench 只读加载生成的 UI adapter，不替代 ComparisonBundle。 |
| RiskEvaluationInput | 风险评估输入 | `ComparisonFacts`、可选 records access、`RiskRulesetSnapshot`、版本和 options 的组合。 |
| RiskRulesetSnapshot | 风险规则集快照 | Flow 选择并传入 risk capability 的版本化规则集，包含 ruleset digest。 |
| RiskFacts | 风险事实 | risk capability 从 ComparisonFacts 派生出的表级风险输入。 |
| RiskEvaluation | 风险评估 | 基于 ComparisonFacts 的风险结论和原因。 |
| RiskReport | 风险报告 | 风险评估的可展示或可下载形式。 |
| RiskTarget | 风险目标 | 风险 annotation 指向的 comparison、table、row、row pair 或后续 ordered interval。 |
| RiskAnnotation | 风险标注 | 单个风险结论及其 target、等级、原因和诊断，可内联或写入 artifact。 |
| RiskAnnotationArtifact | 风险标注产物 | 大量 row-level risk annotations 的物理承载，需进入 operation artifact closure。 |
| Annotation | 标注 | 风险、差异或业务规则在展示层上的说明。 |

## Provider 与输入组合

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| SQL -> SQL | SQL 到 SQL | 两侧都来自 SQL/package，优先使用解析结果直接比较。 |
| Dolt -> SQL | Dolt 到 SQL | before 通常来自 repository，current 通常来自上传包。 |
| Dolt -> Dolt | Dolt 到 Dolt | 两侧都来自 repository commit/ref，优先考虑 Dolt native 或 projection compare。 |
| Snapshot -> Snapshot | Snapshot 到 Snapshot | 两侧都已抽象为 Snapshot，适合 cache hit 或 operation 内复用。 |
| DOLT_NATIVE | Dolt 原生路线 | 两侧可由 repository/Dolt 直接比较时使用；第一版必须经 NativeDiffCanonicalizer 输出标准 ComparisonFacts。 |
| SQL_DUMP_REPLAY | SQL dump replay 路线 | 将原始 SQL 或规范化 SQL fragment 交给 Dolt 执行，常作为 repository import correctness baseline。 |
| SINGLE_TABLE_CLI_IMPORT | 单表 CLI import 路线 | 使用 Dolt CLI 对单张表导入，用于对照、fallback 或小规模导入。 |
| MULTI_TABLE_CLI_IMPORT | 多表 CLI import 路线 | 使用 Dolt CLI 对多张表批量导入，是 bulk import 候选路线。 |
| DOLT_TABLE_IMPORT | Dolt table import 路线 | 使用面向 Dolt 的 table import 输入导入整表数据，是 bulk import 候选路线。 |
| LOAD_DATA | LOAD DATA 路线 | 使用 CSV/TSV staging 文件进行批量导入，是 bulk import 候选路线。 |
| PARQUET_IMPORT | Parquet import 路线 | 使用 Parquet staging 文件和显式 schema 导入整表数据，是列式 staging 候选路线。 |
| DOLT_SERVER_BULK_LOAD | Dolt server bulk load 路线 | 临时启动 Dolt sql-server 并通过客户端批量写入的实验路线。 |
| SERVER_SESSION_BULK_LOAD | Server session bulk load 路线 | 在一段时间内复用 warm Dolt server session 进行批量导入的实验路线。 |
| PARSED_DIRECT | 解析结果直接比较路线 | 两侧 SQL/package 已解析且可直接比较时使用。 |
| SNAPSHOT_TABLE_COMPARE | Snapshot table 比较路线 | 两侧统一成可读取 snapshot table 后比较，是通用回退路线。 |
| ORDERED_TABLE_COMPARE | 有序表比较路线 | 对有序表处理 position、move、blank interval 等业务差异的 comparison provider。 |
| ORDERED_SEMANTIC | 有序语义比较路线 | 旧称 / 泛称；正式 provider 名称优先使用 `ORDERED_TABLE_COMPARE`。 |
| SUMMARY_EARLY_EXIT | Summary 提前退出路线 | 基于 summary/digest 判断无需行级 diff。 |

## 表格模型术语

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| SnapshotTableDescriptor | Snapshot 表描述 | 表级元数据和比较所需事实，例如 table name、columns、row count、schema digest、content digest。 |
| SnapshotTableReader | Snapshot 表读取器 | 行数据读取协议，可来自 SQL parser、Dolt readback、Parquet artifact、cache 命中或测试内存表。 |
| SnapshotTable | Snapshot 表 | `SnapshotTableDescriptor + SnapshotTableReader` 的逻辑组合，是 capability 边界上的核心表模型。 |
| SnapshotTableSet | Snapshot 表集合 | 一个 Snapshot 内的多张 SnapshotTable。 |
| SnapshotTableArtifact | Snapshot 表产物 | SnapshotTable 的物理承载格式，例如 manifest + parquet rows。 |
| ProjectionTable | Projection 表 | raw SnapshotTable 应用 table rules 后形成的 compare-ready 逻辑表。 |
| ProjectionSchema | Projection schema | ProjectionTable 的列集合、ignored columns、effective compare key 和 schema digest。 |
| ProjectionTableArtifact | Projection 表产物 | 由 SnapshotTable + table rules 派生的 compare-ready table artifact，属于 comparison-derived artifact。 |
| OrderedProjection | 有序投影 | 有序表在 ProjectionSchema 基础上按 order key 和 ordered policy 形成的 ordered compare input。 |
| RepositoryImportArtifact | Repository 导入产物 | 面向 Dolt import provider 的 staging 输入，例如 CSV、TSV、Parquet 或 SQL fragment；不是业务事实。 |
| ParserInternalTable | Parser 内部表 | SQL parser 内部短生命周期结构，不跨 capability 边界。 |
| ParsedTable | 旧称 / 不推荐 | vNext 不建议作为 capability contract；如需内部结构，用 ParserInternalTable。 |
| Parquet table | Parquet 表文件 | SnapshotTableArtifact 的一种可能物理承载。 |
| Manifest | Manifest / 清单 | 描述 artifact 内容、schema、refs、digest、版本等元数据的文件。 |
| Table ruleset | 表规则集 | 决定 compare key、ignored columns、有序表规则等的版本化规则集合；实现上通常是从 `backend_vnext.capabilities.table_rules` 共享真源派生出来的 comparison 侧冻结视图。 |
| Compare schema | 比较 schema | 从原始 DDL 抽取出的业务比较 schema facts，例如 canonical 字段集合和 compare key。 |
| Degraded table | 降级表 | 因 identifier 冲突、不兼容类型变化或 DDL 不支持解析等原因不能走普通 row-level semantic diff 的表。 |

## Artifact 与持久化等级

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| L0 Ephemeral | L0 临时态 | 仅内存或 operation 临时目录中的执行产物，可丢失。 |
| L1 Staged Durable | L1 已暂存持久态 | 已可靠保存的输入或执行记录，可用于恢复、校验或重新计算。 |
| L2 Business Truth | L2 业务事实 | 必须通过业务状态机和审计保护的事实。 |
| L3 Recomputable Cache | L3 可重算 Cache | 可删除、可重算的优化产物。 |
| Source artifact | Source 产物 | 原始输入文件或 submit 完整包等输入事实。 |
| Derived artifact | 派生产物 | 由 source/ref 计算得到的产物，例如 table artifact、comparison records。 |
| Bundle artifact | Bundle 产物 | 可下载或可供 workbench 加载的包。 |
| Cache artifact | Cache 产物 | 作为 L3 cache 保存的可重算产物。 |
| Operation artifact | Operation 产物 | 某次 operation 对外 READY 所需的产物。 |
| Operation artifact closure | Operation 产物闭包 | operation READY 前必须存在且可解析的一组完整产物引用。 |
| Repository import artifact | Repository 导入产物 | 面向 repository/Dolt 导入的 staging artifact，可由 SourcePackage、SnapshotTableReader 或 SnapshotTableArtifact 重建。 |
| Artifact ref | Artifact 引用 | 指向 artifact 的内部引用，不应直接等同 host path。 |
| Storage ref | Storage 引用 | 存储层内部引用，通常不暴露给前端。 |
| Host path | 主机路径 | 本机文件路径，不得作为 API contract 或前端可见值。 |

## Cache 术语

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| Cache | Cache / 缓存 | 可重算的优化层，不是业务事实。 |
| Cache key | Cache key | 由输入事实、能力版本和输出 contract 组成，不绑定 operation id 或 host path。 |
| Cache key digest | Cache key digest | 对 cache key payload 的摘要，用于诊断和 registry 索引。 |
| Cache hit | Cache 命中 | 找到可复用 cache entry。 |
| Cache miss | Cache 未命中 | 没有找到可复用 entry，应回退到重算或其他路线。 |
| Cache stale | Cache 过期 / stale | 找到 entry 但版本、contract 或有效性不满足。 |
| Cache disabled | Cache 禁用 | 本次 operation 或环境配置不使用 cache。 |
| Cache registry | Cache registry / cache 注册表 | 管理 cache key、entry、pin、release 和诊断的能力。 |
| Source snapshot cache | Source snapshot cache | 复用同一 source 内容和 parser 上下文的解析/物化输出。 |
| Snapshot table artifact cache | Snapshot table artifact cache | 复用 immutable table row artifact materialization。 |
| Projection table cache | Projection table cache | 复用经过 table rules、compare key、ignored columns 等加工后的 compare-ready projection table。 |
| Comparison core cache | Comparison core cache | 复用 directed comparison core 输出，不包含 surface / bundle。 |
| Comparison surface cache | Comparison surface cache | 复用 thin surface assembly 输出。 |
| Flow assembly cache | 流程组装 cache | 缓存某个 flow/request 形状的最终组装结果，例如 bundle tar。 |
| Pin | Pin / 固定 | 临时保护 cache entry 或 artifact closure 不被 cleanup。 |
| Release | Release / 释放 | 解除 pin 或生命周期保护。 |
| TTL | TTL / 存活时间 | cache、download 或 operation artifact 的有效期。 |
| Cleanup policy | 清理策略 | 删除过期、未 pinned 或可重算产物的策略。 |
| PROVISIONAL | provisional cache / 候选 cache | upload/precommit warmup 产生的候选 cache，尚未经过 commit/readback 权威流程确认。 |
| CONTENT_VERIFIED | 内容已校验 cache | artifact/descriptor/digest 已校验，但尚未绑定 repository commit validation。 |
| COMMIT_VALIDATED | commit 已校验 cache | 已经 commit/finalize 或 repository readback 校验，可被 history compare 等只读流程采用。 |

## ID / Digest / Ref 术语

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| Business ID | 业务 ID | 一等业务对象身份，例如 `workspace_id`、`submission_id`、`operation_id`。 |
| Content digest | 内容 digest | 内容完整性校验，例如 `source_package_digest`、`sql_source_digest`、`snapshot_digest`、`comparison_digest`。 |
| Ref | 引用 / ref | 指向 repository、artifact 或 storage 对象的内部引用。 |
| Repository ref | Repository ref | repository/Dolt 中的 commit、tag、branch 或其他 ref。 |
| Snapshot digest | Snapshot digest | Snapshot 内容或业务等价内容的摘要。 |
| Raw state digest | Raw state digest | Snapshot 或 table 的 raw row state 摘要，用于发现规范化行内容变化。 |
| Business state digest | Business state digest | 应用 table rules 后的业务等价状态摘要，可用于 summary early exit。 |
| Source DDL digest / raw DDL digest | Source DDL digest / raw DDL digest | 原始 `CREATE TABLE` 或规范化 DDL facts 的摘要，用于审计、诊断和 Dolt import source identity，不进入业务 snapshot digest。 |
| Compare schema digest | Compare schema digest | 基于 canonical 字段集合和 compare key 的业务 schema 摘要。 |
| Projection schema digest | Projection schema digest | Projection table 的 schema 摘要，完整 contract 在 `contracts/comparison.md` 中定义。 |
| Projection logical digest | Projection logical digest | Projection table 的逻辑内容摘要，完整 contract 在 `contracts/comparison.md` 中定义。 |
| Comparison digest | Comparison digest | Directed comparison 输入、规则和结果 contract 的摘要。 |
| Bundle digest | Bundle digest | 可下载 bundle 内容或 artifact closure 的摘要。 |
| Upload generation | Upload generation | workspace 内用于区分多次 upload 的单调版本。 |
| Contract version | Contract 版本 | 输出格式或语义契约版本。 |
| Parser version | Parser 版本 | SQL/package parser 的版本。 |
| Table ruleset version | 表规则集版本 | 表比较规则的版本。 |

## 状态术语

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| WorkspaceStatus | Workspace 状态 | 表达 workspace 的业务生命周期，不表达执行进度。 |
| SubmissionStatus | Submission 状态 | 表达 submission 审核和业务生命周期。 |
| ComparisonStatus | Comparison 状态 | 表达只读 comparison request 是否 ready 或 expired。 |
| OperationStatus | Operation 状态 | 表达执行编排状态，例如 queued、running、failed。 |
| OperationStepStatus | Operation step 状态 | 表达某个步骤的执行状态。 |
| SubmitOperationStatus | Submit operation 状态 | Submit 专用 operation 状态，例如 `ACCEPTED`、`FINALIZING`。 |
| ACCEPTED | 已接收 | submit full package 已持久化并通过同步接收校验。 |
| FINALIZING | 固化中 | submit 后台正在导入 repository、创建 ref 或推进业务状态。 |
| SUCCEEDED | 成功 | operation 执行成功。 |
| FAILED_RETRYABLE | 可重试失败 | 临时 repository/IO 等失败，可以重试。 |
| FAILED_FINAL | 最终失败 | digest mismatch、权限失败、不可解析 ref 等不可重试失败。 |
| CANCELLED | 已取消 | operation 被用户、系统或 supersede 机制取消。 |
| SUPERSEDED | 已被新版本取代 | 常用于旧 upload generation 或旧 operation。 |
| PENDING_REVIEW | 待审核 | submission 在 submit finalize 成功后进入的正式业务状态。 |

## 诊断与并发术语

| 术语 | 推荐中文 | 说明 |
| --- | --- | --- |
| Operation runtime | Operation runtime / 执行运行时 | 调度 accepted operation，处理 step、retry、cancel、status。 |
| Operation record | Operation 记录 | 一次业务动作的持久化执行记录。 |
| Operation step | Operation step / 执行步骤 | Operation 内部的可诊断、可重试步骤。 |
| Trace | Trace / 跟踪记录 | 记录 phase、duration、cache result、provider 等执行信息。 |
| Diagnostics | 诊断信息 | 供排查和性能分析使用，不应作为业务状态。 |
| Audit | 审计 | 业务状态变化的可追溯记录。 |
| Lease | Lease / 租约 | 控制并发执行或 repository writer 的短期占用。 |
| Writer lease | 写入租约 | repository 写操作的并发保护机制。 |
| Generation gate | Generation gate / generation 门禁 | 防止旧 upload generation 覆盖新 generation 的保护。 |
| Retryable failure | 可重试失败 | 临时失败，可由 operation runtime 重试。 |
| Final failure | 最终失败 | 不应自动重试，需要用户重新提交或修正输入。 |

## 易混淆术语

| 术语 A | 术语 B | 区别 |
| --- | --- | --- |
| Business truth | Cache | 业务事实受状态机和审计保护；cache 可删除、可重算。 |
| SourcePackage | Snapshot | SourcePackage 是原始输入；Snapshot 是可比较配置状态。 |
| SnapshotTable | SnapshotTableArtifact | SnapshotTable 是逻辑表模型；SnapshotTableArtifact 是物理承载。 |
| ParserInternalTable | SnapshotTable | ParserInternalTable 是 parser 内部短生命周期结构；SnapshotTable 才跨 capability 边界。 |
| ComparisonFacts | ComparisonSurface | ComparisonFacts 是标准化比较事实；ComparisonSurface 是前端展示结构。 |
| ComparisonSurface | WorkbenchBundle | Surface 是结构化展示数据；Bundle 是可下载/可离线加载的包。 |
| Submit Acceptance | Submit Finalize | Acceptance 是同步接收校验；Finalize 是异步固化和入库。 |
| OperationStatus | Business status | OperationStatus 表达执行进度；业务状态表达业务事实。 |
| Cache hit | READY | Cache 命中不等于 operation READY；READY 需要 operation artifact closure 完整。 |
| Artifact ref | Host path | Artifact ref 是内部稳定引用；host path 是本机路径，不应暴露。 |

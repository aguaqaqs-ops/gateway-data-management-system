# Snapshot Table Access Contract

<a id="be-b-展示边界目标b0-固定b1-激活"></a>

## BE-b 展示边界（B1 已激活）

Table Access owner 的 `SourceTableDescriptor`、`SourceColumnDescriptor` 增加 nullable comment；display_name 保持原 DDL 标识符。只捕获已支持 CREATE TABLE 的表/列 COMMENT 字符串，沿用转义/字符集/字段与 statement/source/operation 预算；空白注释归 null，多 COMMENT 最后一个生效，NUL/非法字符串按现有 malformed 拒绝。不扩 ALTER 或 allowlist，不将 SQL 行/块注释误作展示注释。

raw table-set materialization 的进程内结果独立携带 `PresentationMetadata={tables:[{table_name,comment,columns:[{name,comment}]}]}`，canonical projection 按保留表/列变换。表 canonical name UTF-8 序，列 DDL 序，覆盖最终 canonical 全部表列，缺注释显式 null；derived 无源字段为 null。不得把 comment 写进 canonical descriptor wrapper、IPC/Parquet metadata、逐表 cache identity 或 table-set closure 的第二份载荷。持久化唯一 owner 是 CanonicalizationManifest.presentation，详见 [Canonical Storage](../refactoring/formal/contracts/canonical-storage-and-repository-boundary.md#be-b-presentation-目标b0-固定b1-激活)。

Rust parser/native adapter 同轮传递 comment，测试专用独立 oracle 覆盖 COMMENT 子集，不恢复 Python 生产 parser。请求/scalar/materialization 算法形状不变的 selector 保持原值；实际受影响的 durable payload 按[消费者矩阵](../refactoring/formal/plans/be-b-second-step-design.md#71-b0-contractselector-与消费者矩阵)同步更改 producer/decoder，旧载荷拒绝。

本文定义 `SnapshotTableSet`、`SnapshotTableReader`、`SnapshotTableArtifact` 和 raw table artifact cache 的边界。它们是 Snapshot 行数据访问层，不是 repository/Dolt 写入层。

## SnapshotTable

```text
SnapshotTable:
  descriptor: SnapshotTableDescriptor
  reader: SnapshotTableReader
  source_ref optional
  diagnostics optional
```

规则：

- `SnapshotTable` 是 capability 边界上的 L0 逻辑对象。
- Descriptor 表达表事实；reader 提供 row stream。
- `SnapshotTable` 不表达业务流程状态，也不等同于 cache entry。

## SnapshotTableSet

```text
SnapshotTableSet:
  snapshot_id
  snapshot_digest
  table_ruleset_version
  tables:
    table_name -> SnapshotTable
  resolution_plan
  diagnostics
```

规则：

- 默认是 L0 逻辑对象。
- 支持 lazy resolution。
- 同一 set 可以混合 SQL parser、repository export/readback、table artifact、cache artifact 等 reader 来源。
- 必须与 `SnapshotSummary` 的 table facts 一致。
- `SnapshotTableSet` 不直接作为业务事实持久化。

## SnapshotTableReader

Reader 同时提供 full-row streaming 与精确单列值计数。后者用于只需要完整性摘要、但不需要行内容的消费方。

```text
SnapshotTableReader:
  descriptor() -> SnapshotTableDescriptor
  iter_rows() -> RowIterator
  count_column_values(column_name) -> SnapshotColumnValueCounts
  close()
```

`SnapshotColumnValueCounts` 包含 canonical `column_name`、原始 scalar `value -> row count`、`total_row_count` 和内部读取策略。计数必须覆盖所有行并包含 `NULL`；业务层自行决定是否忽略或转换某类值。

约束：

- row 使用规范化 scalar encoding。
- reader 输出按 descriptor canonical columns 映射的完整 row。
- reader 应能在需要时校验 `raw_content_digest`，但这可以放在显式 validation/readback 阶段，不要求 reader init 阶段完成。
- `reader init` 应尽量保持轻量，只负责 descriptor、row stream 句柄和预览所需元数据准备，不应把 canonical digest 校验耦合进对象构造。
- reader 可以持有 deferred row source，并在第一次 `iter_rows()`、`rows` 访问或 digest 校验时才 materialize rows；这类 lazy reader 依然必须对外表现为稳定的 full-row streaming。
- reader 不暴露 host path、Dolt internal path 或 cache key。
- reader 不拼接 SQL literal。
- reader 不管理 Dolt branch、server、commit 或 ref。
- 第一版要求调用方能够重新打开 reader；不强制同一个 reader 支持 rewind。
- 单列计数不得为了生成 cache key 触发完整 content digest 计算；只有 descriptor 已携带不可变 content/raw SQL/fast-row digest 时才允许持久缓存。
- SQL reader 只解析目标 INSERT literal，Parquet reader只投影目标列，repository reader将聚合下推到 provider，内存 reader只访问目标列。优化路径不可用时调用方可以回退 full-row streaming，但不得把失败解释为空表。

### Row Path First

- `SnapshotTableReader` 是 repository-backed row access 的第一选择，调用方应优先消费 row stream，再决定是否做 snapshot、diff 或 artifact 打包。
- repository source provider 不需要把 row access 先转成文件再回读；只要能稳定输出 canonical rows，就满足第一版 contract。
- `SnapshotTableArtifact` 或其它物理化产物可以由上层在需要时再派生，不要求 repository server 在第一版把导出格式矩阵纳入主职责。

未来可选扩展：

```text
PredicatePushdownReader
```

通用多列 projection 和 predicate pushdown 仍不是当前 contract；精确单列计数是已落地的受限统计能力，不扩展为任意查询接口。

## SnapshotTableArtifact

`SnapshotTableArtifact` 是 `SnapshotTableDescriptor + rows` 的公共物理承载 wrapper；format 表达实际用途，不表达可切换的生产引擎。

建议 manifest：

```text
SnapshotTableArtifactManifest:
  artifact_contract_version
  snapshot_digest
  table_name
  descriptor
  row_file_refs
  row_format
  compression
  repository_id  # canonical 必填；raw 明确为 null
  row_materialization_profile
  artifact_content_digest
  created_at
  diagnostics optional
```

通用 raw table artifact 的物理格式：

```text
manifest + Parquet rows
```

规则：

- artifact manifest 必须能还原 `SnapshotTableDescriptor + SnapshotTableReader`。
- `artifact_content_digest` 校验物理文件，不替代 `raw_content_digest`。
- artifact 可作为 cache artifact；调用方对外声明 READY 前需要的 artifact 必须进入调用方自己的 artifact closure。
- raw `parquet/zstd` 载荷是原始 table materialization，不因共用 wrapper 获得 ignored columns、effective key 修正后的 projection 语义。内部 canonical `arrow-ipc/none` 则必须来自 Storage Projection 后的结果，并由 Canonical Storage 拥有内容身份及恢复边界。

### S2b 内部规范表边界

Storage projection 后的内部规范表使用唯一 canonical IPC v1，owner 为 [Canonical Storage §5](../refactoring/formal/contracts/canonical-storage-and-repository-boundary.md#5-artifact-lifecycle)；不同于这里的 raw Parquet artifact、面向客户端的 Parquet/export cache，也不同于下文 comparison-derived projection table。SQL parser 原始行不新增落盘。内部 reader 通过有界 `CanonicalTableStore` handle 读取，按外层 descriptor 对齐规范列名并保留导出 row layout；不以 raw Parquet `row_layout_digest` 替代规范内容身份，不保留内部格式生产回退。引用/TTL、T1/PREPARED 冻结和精确 commit 回填以该 owning Contract 为准，S2b C–E 分节实现与迁移。

D 复用现有 artifact wrapper/manifest，避免给每个 SnapshotTable consumer 增设平行 union。目标 manifest 严格区分 `row_format=parquet, compression=zstd` 与 `row_format=arrow-ipc, compression=none`；`repository_id` 字段必须显式存在，raw 为 null，canonical 为有效 repository scope，并与 caller 已绑定的 repository 比较，再验证 C 的内容身份。`row_materialization_profile` 仍描述既有逻辑标量语义，不能因改物理格式改变业务 schema/content digest。reader 按声明格式打开对应真实用途，canonical 只用 C handle；缺损/错误不尝试另一格式或重新选择来源。同步更改 DTO、checkpoint/closure/冻结 reader 与 golden，不接受缺字段的旧 manifest、别名或格式猜测。

客户端 table/bundle/export 仍提供真实 Parquet。内部 canonical IPC 必须经已有导出/cache owner 按外层 DDL/列序有界地转为 Parquet，纳入当前 operation 预算和发布保护，再进入客户端 closure；禁止将 IPC ref 直接标成 `.parquet`。raw Parquet 与内部 IPC 的共存来自不同实际用途，不是生产 fallback。

## 与 Repository Import 的边界

`SnapshotTableReader` 需要提供足够的导入输入事实：

- canonical table name。
- raw CREATE TABLE / DDL facts。
- canonical columns 和 scalar encoding。
- row stream。
- row count、compare schema digest、raw content digest。
- primary key / compare key hints。

但 `SnapshotTableReader` 不负责：

- 选择 Dolt import provider。
- 拼接 SQL import statements。
- 生成 CSV/TSV/Parquet staging artifact。
- 启动或关闭 Dolt server。
- 管理 writer lease、commit、branch 或 ref。

这些职责属于 `repository_import` capability。`RepositoryImportArtifact` 可以由 `SnapshotTableReader` streaming 生成，也可以从 `SnapshotTableArtifact` 转换得到。

## Snapshot Table Artifact Cache

`snapshot_table_artifact_cache` 只缓存 raw table materialization。

Key scope：

```text
repository_id
row_layout_digest
scalar_encoding_version
snapshot_table_artifact_contract_version
export_format
sort_or_row_order_contract
```

规则：

- 支持同 `repository_id` 内跨 commit/ref 复用。
- 不支持跨 project/repository_id 复用。
- Cache key 不包含 flow ID、operation ID、preview ID、workspace ID、table name 或 host path。
- `row_layout_digest` 由 canonical raw content digest、完整源列编码 schema 与 ordered row metadata 组合而成；table name 不进入 digest。源列类型、ENUM/SET 标签、nullability 或 Parquet 字段布局变化会改变 layout。Repository scope 与 Parquet writer contract version 是 export cache 的独立键字段。
- `PROVISIONAL` candidate 只能作为候选加速输入，不能作为业务事实。
- 调用方允许读取 `PROVISIONAL` candidate 时，必须重新校验 source binding、descriptor 和 digest，并具备 fallback recompute 路径。
- Repository/readback 或等价权威校验通过后，cache entry 才能 promote 为 `COMMIT_VALIDATED`。
- `READ_COMMIT_VALIDATED_ONLY` lookup policy 只读取 `COMMIT_VALIDATED` 或 repository readback 产生的 cache。

S1b 的 Parquet export cache 是独立的可重建 IO cache：精确键为 repository scope、`row_layout_digest` 与
`parquet_writer_contract_version`。layout digest 覆盖完整源列编码 schema 和 ordered row metadata；layout 或 writer 版本不同不得命中。
命中行文件经 `artifact_protection_intents` 登记并按 TTL 延长/释放保护，过期清理由有界 prune 完成；
cache miss、损坏引用或 Parquet 校验失败时回退到规范表读取与导出。Cache ref 不进入 surface 或 bundle，
对外产物仍需闭合为当前 operation 或 bundle 的相对引用。

S5 的 History 先调用 `describe_repository_ref`，以精确 commit 的完整 catalog 和 owning
canonical manifest 核验 repository、表集合、schema、count、raw identity、storage view 和
ordered provenance。返回完整 `SnapshotTableSet`，未读表保留 descriptor 且 `reader=None`；
不打开 canonical 文件或 Dolt 行。任一未选中表的权威绑定错误也必须先失败。

diff 与 export 分别 lookup。`lookup_snapshot_table_parquet` 仅使用上述已验证 metadata，
以 canonical source 编码 schema 构造同一 layout key；先取得 root read borrow 与 TTL 保护，
再在 DB 事务外验证实际文件的 ref/hash、Parquet footer、字段类型、编码 schema、行数与
repository/layout 绑定。缓存内存预约不足作为 miss；取消、截止和未知 DB 错误继续传播。
损坏条目以 `discard_if_same(key, ref)` 条件删除，不能清掉后写者替换的健康 ref。

合并 miss 和 composite 的实际行需求后，`ensure_committed_tables` 仅补读缺少的 readers，
保持完整表集合、顺序、digest 和已打开 reader；使用同一 repository owner、完整 binding 和
精确 commit，不回退 main。返回 reader 拥有 canonical handle，关闭 reader/batch reader 后
才释放 mapping。元数据、cache 解码、行与输出统一使用当前 operation 的同一 M。

## SQL Reference Parser Semantics

参照解析器拒绝 BIT 负数、超宽值与非 ASCII `b'..'`，并以确定诊断报告；BIT 数字字面量按十进制解释。
`_binary` 后接字符串或十六进制字面量，只能写入 BINARY、VARBINARY、BLOB 系列列；`\%` 与
`\_` 保留反斜杠。列类型中的 SQL 注释被忽略。JSON 拒绝 `NaN`、`Infinity`、孤立代理与超过
100 层嵌套的值，深度检查以迭代方式完成。零日期与零日期时间保持拒绝。


### S2b 生产 parser 的 operation 预算

D 将 Rust parser 接入生产时，除了既有 source/statement/row/field/diagnostic 配额，还须传入当前 operation 剩余的局部 `max_live_bytes`。该局部预算约束 parser 拥有的元数据、jobs/plans/chunks、列 builder、合并与 Arrow/adapter 转移的同时存活分配；借用 SQL 输入由 operation 持有并计一次，不重复算 parser 自有内存。局部调用完成后，实际 retained Arrow backing 继续计入 operation 预约，不能只在返回后检查已完成的大分配。

采用分配前 checked 的确定性源序预预约，复用已有 scanner 的有界元组统计；估计需覆盖元数据/ordinals、capacity 增长、merge 旧新重叠和转移临时量。不要用并行任务抢占共享计数器决定错误位置，也不建设全局 allocator 框架。新 `max_live_bytes` 不足按既有 `RESOURCE_LIMIT_EXCEEDED` 返回文档级诊断（budget=`max_live_bytes`、byte offset=`0`），不返回可成功发布的部分结果；这是本次新增整体额度的定位规则，不改既有配额的定位与成功输入语义。

具体保守项由实现及独立审核说明，并以有界资源拒绝、宽表/短坏 tuple、N 确定性和真实 worker 校准验证；配置与容量结论按 [D 任务](../refactoring/formal/plans/p6-s2b-d-kickoff.md) 及 DC87。不因补该资源边界重做已通过且不受影响的 S2a 全量逐值差分。

## Projection Table Boundary

Projection table 是 comparison-derived artifact，不属于 `SnapshotTableArtifact`。

```text
SnapshotTableArtifact
  raw snapshot table materialization
  面向 summary、bundle、repository import、comparison fallback

ProjectionTableArtifact
  comparison-derived table materialization
  面向 comparison_compute / provider planning / native projection diff
```

规则：

- Projection artifact 由 `SnapshotTableArtifact + table_ruleset` 或 `SnapshotTableReader + table_ruleset` 派生。
- ignored columns、effective primary key、schema intersection 和 projection row identity 由 `contracts/comparison.md` 定义。
- `projection_table_cache` 不并入 `snapshot_table_artifact_cache`。
- 第一阶段只能预留 boundary，不要求实现 projection cache。

## 验收标准

- `SnapshotTableReader` 能 streaming 大表，不要求一次性读入内存。
- Reader digest 校验失败时，该表 resolution 或 validation 明确失败。
- `SnapshotTableSet` 与 `SnapshotSummary` 的 descriptor/digest 一致。
- 可重建 L3 cache 缺失时，按绑定来源重建 table access；T1 后冻结文件不适用通用重建规则，已提交规范副本只按精确 commit 回填，见 Canonical Storage §5。
- Cache hit 后仍校验 descriptor、digest 和 artifact manifest。
- `SnapshotTableReader` contract 测试不依赖 Dolt 写入。
- Repository import benchmark 应调用正式 table access / artifact builder，不长期维护独立 row/digest 实现。

## Configuration generated time native metadata（V1）

SQL parser返回独立小型configuration_generated_time metadata，不改变既有parse canonical encoding或scalar grammar。事实在INSERT成功typed转换时、规范排序前累计；source ordinal从1跨INSERT/chunk连续，NULL/empty/invalid占位，selected为最后有效值，max并列保留首次。文本复用原SQL literal解码（含TEXT合法hex），不由宿主自动转换非字符串逻辑类型。业务规则、UTC语法与缺失分类的唯一语义见[业务设计§4.1](../refactoring/formal/plans/p6-archive-business-validation-design.md#41-提取位置与顺序)。

native只传递规则身份、selected/max、三类计数、两序号、status及last_not_max，不搬整列到Python、不重读SQL；取消/截止/预算错误仍按原parser整体失败。domain在application边界严格校验和绑定，缺metadata不是业务missing，不可发布READY。Rust唯一向量owner为gateway-compute-core/tests/configuration_generated_time.rs；adapter仅保留接线smoke。

<a id="p7-s1a-目标补充位置与-handle待实现"></a>

## P7-S1a 生效补充：位置与 handle（已生效）

状态：S1a 位置与 handle 接线已实现并经 G 核收，证据与适用边界见 [S1a 总结](../refactoring/formal/plans/p7-s1a-summary.md)；[A 入口](../refactoring/formal/plans/p7-s1a-a-entry-and-contract.md)保留当时仅固定目标的历史事实。[Canonical Storage 协议](../refactoring/formal/contracts/canonical-storage-and-repository-boundary.md#p7-s1a-目标补充多-root-身份与发布待实现)的统一位置身份与发布约束生效。

canonical IPC 与 canonical wrapper 显式归 canonical；raw Parquet wrapper/rows 与 client export 显式归 export。二者共用 wrapper 不允许按 `_opaque_id("sta-manifest")`、media type 或扩展名猜位置。完整 canonical key 和 export cache key 保持原 scope/版本/行布局，换物理挂载不能变 key。reader、get_ref 与 mmap 一律通过位置 codec/resolver，handle 持有对应 root borrow 到所有 Arrow/native consumer 关闭。

client Parquet writer 使用本角色显式 scratch，最终从普通服务生成文件有界 copy/hash 到 export staging，不整文件 read_bytes 后复制，不依赖跨盘 replace。HTTP Arrow spool 同样使用 scratch；关闭/异常/取消删除本次临时文件，scratch 不是恢复权威。共享 IPC 多用途不复制/搬盘，格式转换产生真实 export 对象。强保护冻结缺失与 optional export cache miss 仍按原 owning 恢复规则区分。

manifest 中 row_file_refs 采用新 ID，因此 wrapper JSON bytes/raw SHA按实际载荷重算；artifact_content_digest_of只取row media/size/raw SHA及descriptor/profile，不取row artifact_id，固定这些输入时必须保持。业务 descriptor/schema/table/state 与 row_layout_digest 不新增位置输入。同一新版本同盘/分盘应相等，不承诺 wrapper 与旧 ID golden 相等。

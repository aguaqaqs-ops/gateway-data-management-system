# P3-R5 Comparison Discussion Summary

状态：临时讨论摘要；不是 R5 执行计划，不授权 R5 实现

日期：2026-08-20

用途：保留 P3-R5 Comparison 的已确认语义、推荐决策和未决架构问题，避免在详细
执行计划和 S0 freeze 之前丢失上下文。字段级 contract、numeric budget、fixture
matrix 和 implementation path 仍须在正式 R5 plan 中冻结。

## 1. R4 entry context

- R4 handoff `p3_r4_exit: pass`、`p3_r5_ready: yes`。
- R4 validated code SHA：`4effb6eefa16d246e75213212f884b2546e6d6ef`。
- 当前 R4 handoff 证据修正尚未提交；`r5_entry_sha` / `handoff_documentation_sha`
  待该文档修正提交后回填。
- 当前 sealed HEAD 的 R4 focused suite：268 passed；ruff/mypy passed。
- 当前 sealed HEAD 的全量 unit 复跑在既有 `tests/test_app.py::test_healthz_uses_injected_settings`
  处 60 秒超时；原 S8 的 609-pass 保留为历史 gate 证据，不冒充本次新复跑。

## 2. Confirmed R5 boundary

- R5 只消费 immutable before/current `SnapshotTableArtifact` / public reader closure。
- R4 `CanonicalizationManifest` 只作为 opaque storage identity/binding；R5 不 import
  R4 private modules，不从 canonical storage 反推 comparison columns。
- R5 不接 HTTP、Workspace、Submit、Repository/Dolt、Operation Runtime、Risk/Surface/Bundle
  production integration。
- `FULL` / `MODIFIED_ONLY` 是输入完整性语义；`DETAILED` / `DATASET_REPLACEMENT` 是
  comparison execution mode；`ALL_CHANGES` / `UPDATE_ONLY` 是 table artifact scope。
- `MODIFIED_ONLY` 保留为用户语义，但必须先通过 pinned baseline reconstruction 形成
  完整 before/current snapshot pair。当前不引入 sparse delta input contract。
- `DETAILED` 允许 schema/key/ordered alignment 和 row/field records。
- `DATASET_REPLACEMENT` 表示不同 project identity，不做普通 row alignment，输出
  replacement facts/closure，并驱动显式 submit confirmation。
- `ComparisonFacts` 保存不可变 comparison mode 与 project-identity assessment digest；
  下游不得重新猜测 mode。
- 权威 comparison record 仍是 `ROW_MODIFIED`；前端字段展示使用派生 `FieldChange`
  视图，包含 `table_name`、`row_identity`、`column_name`、before/current value 和
  `change_kind=UPDATE`。
- key 变化不得伪装为普通 field update；keyless 只有在 deterministic multiset matching
  成功时才生成 field changes。

## 3. Confirmed classification baseline

Overall status：`UNCHANGED`、`BUSINESS_EQUIVALENT`、`CHANGED`、`DEGRADED`、`FAILED`，
优先级为 `FAILED > DEGRADED > CHANGED > BUSINESS_EQUIVALENT > UNCHANGED`。

Table status：`UNCHANGED`、`BUSINESS_EQUIVALENT`、`ADDED_TABLE`、`DELETED_TABLE`、
`MODIFIED`、`SCHEMA_ONLY_CHANGED`、`SCHEMA_CHANGED`、`REPLACED`、`DEGRADED`。

Record kind：`ROW_ADDED`、`ROW_DELETED`、`ROW_MODIFIED`、`SCHEMA_CHANGE`、
`TABLE_DEGRADED`。`UPDATE_ONLY` 抑制 INSERT/DELETE，但保留 suppressed counts 和
`ROW_MODIFIED`/FieldChange。

## 4. Confirmed alignment baseline

- effective key：explicit comparison key > DDL primary key > explicit keyless policy；
  不使用隐式 positional fallback。
- keyless comparison 使用 comparison-only canonical row multiset/occurrence identity，
  不创建持久 surrogate key。
- ordered comparison 使用 stable key 做匹配、`no` 做顺序事实；ordered movement 由
  ordered extension 表达，不退化为普通 positional comparison。
- selected comparison column、type、nullability 或 key 变化默认 `SCHEMA_CHANGED`；
  `REPLACED` 只由显式 `DATASET_REPLACEMENT` 产生。
- records closure 有界、可流式写入 artifact；`ComparisonFacts` 只有在 closure 完整
  后才可发布。R5 S0 仍须冻结具体 record/diagnostic/resource limits 和 benchmark。

## 5. Confirmed identity and continuation decisions

以下决策已确认：

1. `ProjectIdentityAssessment` 由独立 capability 拥有，R5 只消费 immutable assessment。
2. `version-manager-overlap/v1` 继续作为身份算法；明确交集才是 `SAME_PROJECT`，明确无交集
   才是 `DIFFERENT_PROJECT`，无法可靠比较则是 `UNVERIFIABLE`，不使用隐藏启发式。
3. `UNVERIFIABLE` 在确认前严格 fail-closed：只发布 assessment/diagnostic gate，不执行
   comparison、risk、surface、business projection，不发布 READY 或 `ComparisonFacts`。
4. 前端确认 action 为 `ALLOW_DETAILED_ON_UNVERIFIABLE`；确认只授权按 `DETAILED` 继续，
   不能授权 `DATASET_REPLACEMENT`。
5. 服务端受信 orchestrator 必须重新校验 workspace、upload generation、snapshot digests、
   assessment set digest、actor policy 和 policy version 后才调用 R5。
6. gate assessment、确认和 continuation 状态持久化并幂等；FULL 多 pair 使用一个
   `assessment_set_digest`，任一 pair `UNVERIFIABLE` 则整体等待一次确认。
7. 确认后的 preview 保留 `project_identity_status = UNVERIFIABLE`、
   `comparison_mode = DETAILED`，overall status 为 `DEGRADED`，表级状态仍使用正常 diff
   status，并保留 `PROJECT_IDENTITY_UNVERIFIABLE` diagnostics。
8. submit 不复用 replacement action；使用独立的
   `ACCEPT_UNVERIFIABLE_DETAILED_RESULT`，绑定最新 preview/bundle/assessment digests，
   并在 submit 时重新检查当前 policy。preview 确认记录 actor、时间和 policy version；
   submit 另行记录不可逆操作理由。
9. 普通用户获得的是可撤销的 server-side policy allowance，不获得 trusted caller 身份。
   policy 撤回不静默改写已生成 preview，但可阻止新的 continuation 或 submit。
10. `DATASET_REPLACEMENT` 固定输出 before/current dataset facts、replacement reason、
    assessment digest，且 `records_ref = none`。
11. `FieldChange` 是 `ROW_MODIFIED` 的派生视图，暂不建立第二个 public artifact contract。
12. Preview 小规模结果提供 typed before/current values；大规模结果通过 bounded records
    artifact 引用，禁止无界 inline payload。

## 6. Confirmed storage/business identity boundary

R4 canonical storage 中的 pseudo gid 会持久化为正式表的 physical primary key，但现有 R4
contract 明确称其为 physical identity，不是展示或业务 stable gid。其按 canonical `no`
顺序确定分配，保证同一 source snapshot 重算/retry 一致，不保证跨 snapshot 在 blank 插入、
删除或 position shift 后保持同一业务实体身份。

已确认继续采用双身份模型：`StorageRowKey` 可为持久 pseudo gid；
`ComparisonEntityIdentity` 对 blank row 使用 interval + blank occupancy/occurrence 的
comparison-only 语义，不用 pseudo gid 或其他属性 payload 做跨 snapshot 配对。blank row
除 `gid/no` 外的属性可以变化，但当前 comparison 忽略这些变化，不将其视为非法或业务 diff。
若 R5 只能读取 canonical rows，
public reader 必须同时提供 source-blank marker / ordered blank metadata；不能从 pseudo gid
范围反推 blank 语义。不引入跨 snapshot durable blank lineage，也不修订 ADR 0004 将 pseudo
gid 提升为业务 stable key。

来源校验补充：`SOURCE_SQL` 输入中的 `4_000_000_000..4_294_967_295` 是 reserved-range
source gid，必须拒绝；只有受信 `CANONICAL_DOLT` reader 返回的同范围值才是合法 physical
key。来源类型由受信 materialization/reader capability 绑定，不能由普通 caller 任意声明。

## 7. Confirmed ordered comparison decisions

1. 同一 stable row 的内容变化和位置变化可分别输出 `CONTENT_UPDATE`/`ORDERED_ROW_MODIFIED`
   与 `MOVE`/`ORDERED_ROW_MOVED` 两条 records；同一 `row_identity` 下不合并语义，
   `position_changed_count` 对该行只计一次。
2. `ORDERED_POSITION_CHANGED` 保留给绝对 position/no 变化但相对顺序未变化的事实；相对
   顺序改变使用 `ORDERED_ROW_MOVED`，不重复输出 position record。
3. `no` 同时保留原始 before/current position 值和 stable-key 相对顺序事实；整体重编号不
   伪装成 move，但必须保留 position-change evidence。`no` 不参与 content `FieldChange`。
4. 没有 stable key 时不推断 move；只能输出可靠 interval/insert/delete，无法唯一表达时
   输出 `ORDERED_TABLE_DEGRADED`，不退回普通 positional comparison。
5. 有序 diff 不使用隐式“最像”匹配；可精确重放为 `EXACT`，局部可解释但有歧义为 `PARTIAL`，
   无法可靠表达为 `UNSUPPORTED`/`DEGRADED`。
6. Blank row 只由 source blank marker 或 `PSEUDO_BLANK` provenance 识别；除 `gid/no` 外的
   属性允许变化但属于 comparison-ignored payload，不做 blank validity 校验，不进入 blank
   signature、comparison digest、`ROW_MODIFIED` 或 blank insert/delete 判定。
7. Blank comparison 只比较 real-row backbone interval 内的 occupancy/count；同一 interval
   内 blank 数量不变即不产生 blank record，数量变化才产生
   `BLANK_INSERT_INTERVAL` / `BLANK_DELETE_INTERVAL`。blank 不产生 move 或普通 row identity。
8. Blank 的结构位置变化可以独立产生 records：旧 interval/position 没有对应 blank 时输出
   `BLANK_DELETE_INTERVAL`，新 interval/position 出现额外 blank 时输出
   `BLANK_INSERT_INTERVAL`；两者不建立 move 配对。若只是同一 interval 内的 `no` 重编号且
   occupancy 未变，则不产生 blank record。
9. Blank records 的 replay guarantee 针对 comparison ordered projection/occupancy 语义，
   不承诺重放被 comparison 忽略的 blank payload 属性；`storage_row_key` 仅用于物理回指。
10. Blank records 按 interval 聚合，不按 pseudo row 逐条生成；记录 before/current occupancy、
    position/interval 范围、数量和 occupancy digest，不携带被忽略的 blank payload values。
11. 对外 records closure 统一使用 Parquet；JSON 仅用于 manifest/facts/diagnostics，JSONL
    只能作为内部临时 spool，不进入 public artifact contract。
12. 普通 records 的 typed values 由列 schema 解释，显式保留 `null`，不转成字符串；identity
    和 digest 继续使用 canonical scalar encoding。`COUNTS_ONLY`、`CHANGED_COLUMNS`、
    `FULL_BEFORE_AFTER_VALUES` 分别控制 records detail。
13. Records artifact 保持 immutable canonical 全量文件；分页属于 reader API，opaque page
   token 绑定 manifest digest、table、sort policy 和最后 canonical sort key，不按行号分页。

## 10. Confirmed execution assurance decisions

1. Comparison execution 使用 pair/table/runtime 的分层 bounded budgets；上游输入预算继续由
   R2/R3 owner 继承，R5 不复制 parser budget。HASH 超内存时 `AUTO` 可切换 SQLite；
   SQLite/spill/records/per-table budget 超限时当前表 `DEGRADED`，丢弃 partial artifact，
   其他表继续。
2. 用户取消或 deadline 到期不发布 `ComparisonFacts`/records closure；reader/key/schema
   问题可形成完整表级 `DEGRADED`；records writer、manifest、digest、closure 校验失败为
   pair-level `FAILED`，不发布 READY。
3. `ComparisonFacts` 只有在每张 planned table 都有终态、所有引用 artifact 已校验闭合、
   transient reader/writer/spool 已关闭且 digest 完成后才能发布。
4. benchmark 记录 workload、cold/cache、内部模式、耗时、CPU、RSS、spill、artifact bytes、
   records count 和 cancellation latency 等指标；暂不定义固定性能阈值、通过门槛或以
   benchmark 结果自动授权实现 gate。安全预算和完整性 contract 仍是硬边界。
5. correctness fixture 要求 HASH/SQLite 产生相同 canonical facts、records manifest digest
   和 counts；临时布局、chunk、provider diagnostics 不进入语义 digest。

## 8. Confirmed schema alignment decisions

1. 字段顺序、display name 和 canonical name 大小写变化不算 schema change。
2. 仅 ignored column 变化为 `SCHEMA_ONLY_CHANGED`；非 ignored、非 key 字段增删为
   `SCHEMA_CHANGED`，仍可比较两侧兼容字段。
3. selected comparison column 的 type/nullability 变化为 `SCHEMA_CHANGED`；该字段不产生
   普通 `FieldChange`。默认只允许 exact canonical scalar type，不做隐式 widening/coercion。
4. effective key 增删、类型变化或来源变化以 `SCHEMA_CHANGED` 为主状态，附带
   `ROW_ALIGNMENT_UNAVAILABLE` diagnostic；不使用备用 key，不生成 row alignment records。
5. effective key 未变且仍存在兼容 selected columns 时，schema change 可继续有限 row diff；
   before-only/current-only 字段本身不制造 `ROW_MODIFIED`，另行输出 `SCHEMA_CHANGE`。
6. 所有字段被忽略时输出 schema-only facts；ruleset 无效或 projection schema 无法构造时才
   输出 `DEGRADED`。

## 11. Newly confirmed initial/pair/cache decisions

以下问题已经冻结，正式设计基线见
[P3-R5 Comparison Design Baseline](p3-r5-comparison-design.md)。

1. `INITIAL_SNAPSHOT` 使用 `view_kind=INITIAL_SNAPSHOT`、
   `comparison_applicability=NOT_APPLICABLE`、`before=none`、`current=initial snapshot`，
   不生成 comparison facts/records；current-side business projection 可用。
2. snapshot/materialization/projection 失败不能发布数据结果；static risk provider 失败时不
   发布部分 annotation，保留 `STATIC_RISK_UNAVAILABLE`，数据 preview 可用但 aggregate/bundle
   为 `DEGRADED`。
3. FULL 中 `baseline_to_initial` 为 optional、`initial_to_modified` 为 primary；baseline
   缺失/恢复失败最多使整体 `DEGRADED`，primary pair 继续，primary 失败才使整体 `FAILED`。
4. history compare/archive replay 由受信 flow context 设置
   `identity_applicability=NOT_APPLICABLE`，不自动运行 identity assessment，不生成 replacement；
   普通 caller 不能伪造该值。
5. cache 分为 neutral comparison core、comparison risk、static risk 三层；restore 后必须
   重建 final envelope、risk aggregation、operation-local closure 和 bundle digest，cache hit
   不授予 continuation/submit 权限。
6. identity envelope 分别表达 `requires_continuation_confirmation` 与
   `requires_submit_confirmation`；`UNVERIFIABLE` continuation 和 replacement submit 不共用
   confirmation bit。

## 12. Confirmed future risk extension boundary

未来 static risk 与 diff risk 采用“计算能力独立、结果统一聚合”的结构：

```text
comparison_risk  -> comparison risk artifacts
static_risk      -> static snapshot risk artifacts
risk_aggregation -> unified RiskReport / RiskReportSet
surface/bundle   -> aggregated risk contract
```

1. `comparison_risk` 继续消费 `ComparisonFacts`/comparison records；`static_risk` 消费
   immutable `SnapshotTableArtifact` / public reader closure，不依赖 comparison。
2. 两者共享 `RiskSource`、`RiskAnnotation`、`RiskReason`、`RiskTarget`、artifact closure 和
   aggregation contract，但不合并为一个带大量 optional input 的 provider DTO。
3. digest/cache 分层为 `comparison_risk_digest`、`static_risk_digest` 和
   `risk_report_set_digest`；static risk 不改变 `ComparisonFacts`，diff risk 不改变 static
   risk artifact。
4. `INITIAL_SNAPSHOT` 可以只有 static risk 而没有 comparison facts；各 provider 可独立失败，
   聚合结果保留来源和 diagnostics。R5 只预留 contract seam，不实现 static risk rules。

## 13. Formal design and execution plan

正式设计基线：[P3-R5 Comparison Design Baseline](p3-r5-comparison-design.md)。

正式执行计划：[P3-R5 Comparison Execution Plan](p3-r5-comparison-execution-plan.md)；S0 记录：
[P3-R5-S0 Entry and Budget Freeze](p3-r5-s0-entry-and-budget-freeze.md)。执行计划新增 S1
language-neutral batch boundary/provider port，阶段总数为 S0-S8；每一步的同对话/新对话策略已
写入 execution plan §2。

S0 freeze 必须把本文规则落成 owner、contract、fixtures、budgets、failure matrix、review focus
和 reopen conditions，并额外冻结 `NOT_APPLICABLE`、baseline initialization、batch reader owner
和 Python/Rust provider port boundary。

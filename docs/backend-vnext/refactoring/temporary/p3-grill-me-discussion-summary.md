# Phase 3 Grill-Me Discussion Summary

状态：Temporary / non-normative / discussion checkpoint

日期：2026-08-18

用途：保存 Phase 3 正式设计讨论中的已确认决策、暂定假设和未决问题，防止
上下文压缩后把讨论建议误读为正式 contract。本文不拥有 wire、字段、状态机或
implementation authority；正式语义仍以现行 formal contract、ADR 和后续经批准的
P3 design plan 为准。

当前阶段：

```yaml
phase_2_complete: yes
p3_context_ready: yes
p3_design_started: yes
p3_design_status: accepted
p3_implementation_authorized: no
```

## 1. 讨论边界

- 首个真实 consumer 是 `BuildUploadPreview`。
- `FULL` 与 `MODIFIED_ONLY` 共用 capability 主链。
- `INITIALIZE_BASELINE` 延后到 Workspace/Application flow，建议 Phase 5。
- P3 只实现 capability contracts/providers，不接 HTTP/application。
- P4 提供 durable Operation Runtime。
- Phase 5A 接入 Workspace、HTTP、PreviewResult 和 artifact retention。
- 生产 Preview 统一使用异步 Operation，不根据数据大小切换同步/异步 wire 语义。

主链：

```text
table_access/parser
  -> snapshot_materialization
  -> SnapshotTableArtifact
  -> storage/comparison projection
  -> comparison
  -> risk
  -> surface
  -> bundle
```

## 2. 已确认的输入、容量和格式

### SourcePackage

- capability 正式保留：`DIRECTORY`、`ZIP`、`TAR_GZ`、`SQL_FILE`、`SQL_GZ`。
- 首版 HTTP 只承诺 `TAR_GZ`，兼容前端 `directory-tar-gzip`。
- `SQL_FILE` / `SQL_GZ` 仅用于测试和 benchmark。
- `DIRECTORY` / `ZIP` 仅用于内部 staging/test helper。
- zstd 仅作为内部 fixture/staging transport，不新增正式 `TAR_ZST` package kind，
  也不把 zstd 伪装成 `TAR_GZ`。
- compressed ingress 上限：`256 MiB`。
- expanded SourcePackage admission 上限：暂定独立 `1 GiB`，由 benchmark 再收口。

### RepositoryImportArtifact

- compressed upload：`256 MiB`。
- `manifest.json`：`16 MiB`。
- `replay.sql`：`200 MiB`。
- replay SQL 超过 `200 MiB` 直接拒绝，不拆分、不 fallback。
- total expanded payload/stream 收紧到约 `256 MiB`。
- 超限必须在 Repository effect 前发现。
- Submit 在 T1 前执行 admission。
- Preview 可以成功，但记录派生 `SUBMIT_CAPACITY_BLOCKED`；不上传、不创建
  Repository operation、不进入 `EFFECT_PENDING`。
- 首版 RepositoryImportArtifact 继续固定为 `manifest.json + replay.sql`，当前
  `replay.sql` 是受信 Storage Projection 生成的 deterministic replay。

## 3. 已确认的失败、降级和规则语义

- 合法但不关注的 SQL 语句：ignored + diagnostics。
- 解析、列/行宽度、identifier collision、非法 scalar/ENUM/SET、重复有效 key：
  hard failure。
- 未知或暂不支持的 SQL type：
  - Preview：表级 `DEGRADED`，保留 descriptor/row count/diagnostics，不生成可信
    row records；
  - Submit/storage projection：effect 前拒绝；
  - 不使用正式 `STRINGIFY` fallback。
- 无有效 compare key：
  - Preview：`DEGRADED`，不生成 row-level diff records；
  - Submit/storage：fail closed；
  - 只有显式 keyless/multiset ruleset 才能解除限制。
- 不把部分 rows 当作空表或成功结果。
- Composite XML 缺失等价于合法空公式集，使用固定 EMPTY source/digest，不阻塞
  Preview；这里的 EMPTY 指解析结果为空，不是阻塞或等待。
- XML 存在但格式错误、重复公式名或业务不变量失败：阻塞 Preview。
- SQL parser 与 XML parser 保持独立。

## 4. Snapshot、Comparison、Risk 和 Bundle

- Preview 不等待 FINAL，也不等待 cache warmup；只要 Preview 自身 artifact closure
  完整即可 `READY`。
- Preview `READY` 可以是 `materialization_stage=PROVISIONAL`。
- `FINAL` 只在 Submit finalize 后成为 repository/history 权威事实。
- 全量 rows 使用 Parquet/raw table artifacts；JSON 只保存 summary、surface、bundle
  metadata、artifact refs。
- Bundle refs 必须真实闭合，不能用 placeholder metadata 替代实际 rows/records。
- Snapshot table artifact 在 current Preview/active SubmitAttempt 期间 pin；Attempt
  终态后释放，full-row archive 不长期重复保存。
- Dataset replacement 保留旧业务语义：`FULL` 中 baseline-to-initial 与
  initial-to-modified 独立判定；`DIFFERENT_PROJECT` 使用双侧 snapshot bundle、
  显式确认，不进入普通 row comparison。
- Table ruleset 初版继续 hardcoded registry，但 capability 依赖 immutable
  `TableRulesetSnapshot` provider 接口。
- Risk ruleset 初版继续 hardcoded registry，入口捕获 immutable
  `RiskRulesetSnapshot`，记录 `risk_ruleset_id/version/digest/contract_version`。
- Risk ruleset 是声明式数据，不允许 Python/plugin/任意代码；未知 rule 或非法
  params 在 activation/validation 阶段拒绝。
- RiskEngine 是实际 risk 计算器，不是配置读取器。它消费 `ComparisonFacts` 和
  ruleset，生成 RiskEvaluation、RiskReport 和 annotations。

## 5. SQL type 和 Composite ownership

- P3 建立 capability-owned logical SQL type contract。
- 首版类型矩阵：signed/unsigned integer、BOOLEAN、DECIMAL、FLOAT/DOUBLE、
  DATE/TIME/DATETIME/TIMESTAMP、CHAR/VARCHAR/TEXT、BINARY/VARBINARY/BLOB、BIT、
  JSON、ENUM/SET。
- JSON 是逻辑 JSON；artifact 可采用 UTF-8/string 物理表示，但必须遵守 canonical
  JSON/digest contract。
- Spatial/GIS 首版 unsupported。
- ENUM/SET 复用 ADR 0013 和 canonical storage semantics。
- SQL parser 不 import `repository_service`；Repository Service type grammar 只
  作为参考/conformance oracle。
- Composite signal point 和公式 artifacts 进入 Snapshot identity 和 bundle closure。

## 6. Python/Rust 混合架构（已修正）

Rust 的主要价值是解除 Python 多 pair 并行时的 GIL、Python object materialization、
进程复制和资源抢占限制；不是单纯追求语言本身的 numeric speed。

### Python control plane

- HTTP/API、application/domain、Workspace/Submission/Archive。
- Operation Runtime、durable step、retry、takeover 和状态更新。
- provider/ruleset selection 和频繁变化的业务 policy。
- 小型 metadata、surface、response assembly。

### Rust data plane candidates

- scalar/type normalization 和 canonical digest。
- SQL streaming parser，前提是并发 profile 确认它是主要热点。
- storage/comparison projection、standard hash diff、records。
- Arrow/Parquet materialization。
- large-scale risk facts extraction，以及 profile 证明稳定后可扩展到 risk decision
  kernels。
- XML parser 也是 Rust candidate，但必须与 SQL parser 独立 profile；不因语言统一
  强行转换成 Arrow 或强行 Rust 化。

### Provider boundary

- P3 先定义语言无关 contract，并用 Python reference 恢复旧语义和提供 golden/
  differential oracle。
- 已证明为稳定数据面热点的 capability 可直接使用 Rust production provider，
  不要求先建设同等规模的 Python production implementation。
- 首阶段优先 PyO3 + Arrow 进程内粗粒度调用；不逐 row/scalar FFI，不把 Rust 内存
  对象放入 Operation state，不在 P3 引入 compute network service。
- Rust provider 不自动 fallback 到 Python。Python provider 只能通过显式
  `REFERENCE/DIAGNOSTIC` profile 选择。
- Python/Rust/Polars/Repository 使用统一的全局 concurrency budget，禁止嵌套线程
  超卖；pair、source materialization、Rust threads、I/O slots 都由 execution policy
  显式控制。
- 同一 source 只解析、只物化一次，多 pair 共享 SnapshotTableArtifact。

## 7. 跨语言和失败合同

- SQL parser 输出 table descriptors、diagnostics 和 deferred row stream/Arrow batches，
  不生成大规模 Python AST/tuple/dict。
- XML parser 输出 compact formula AST/diagnostics/source digest，保持独立 capability。
- Rust 使用 bounded Arrow batches/channels；取消在安全 checkpoint/batch boundary
  生效。
- 未完成 Snapshot 不得发布为 PROVISIONAL/FINAL；临时 artifact 不得进入 cache hit
  或公开 closure。
- OOM、panic、timeout、cancel、native failure 映射为稳定 capability errors，
  Operation 可按同一 provider 重试或接管。
- provider implementation name、语言和线程数只记录 diagnostics/measurement，不
  进入 semantic digest；只有当前语义发生变化才需要改变当前初版常量。

## 8. 未发布阶段的版本策略

- 当前项目尚未对外发布，所有 capability/parser/model 统一保持初版语义。
- 不建立旧版本兼容读取、双 digest、迁移 alias 或历史兼容矩阵。
- 现有 version fields 可以保留为固定初始常量，用于同一运行期校验和缓存隔离，
  但不提前建设正式版本治理。
- 初版语义变化直接更新当前 fixtures、实现和 cache；正式上线后再引入正式版本管理。

## 9. 已确认的迁移兼容原则

- owning contract/ADR 和用户已确认决策高于 legacy 行为；legacy 仅作为 reference
  oracle。
- 用户可见且仍属有效业务语义的 legacy 行为保留并纳入 golden。
- 明确 bug、未定义行为或安全风险不复制，改为 hard failure/diagnostic。
- 不在每个生产请求中长期 dual-run Python/Rust；使用离线 golden/differential、
  benchmark 和有限 shadow run，production 选择一个明确 provider。

## 10. 新增但尚未收敛的增量 replay 能力

用户提出：当前 standard comparison 主要服务前端行级差异；Repository replay 对变化表
默认整表重建。未来希望在单表变化小于阈值时，使用 `UPDATE/INSERT/DELETE`，超过阈值仍
整表重建，并支持开关切换，以便加速后续提交和向外部系统（例如 PostgreSQL）同步。

当前判断：可行，但不是 standard comparison 的简单输出格式开关，预计是中等偏大的
新增 capability。

建议新增：

```text
before canonical storage snapshot
  + current canonical storage projection
  -> StorageMutationPlan
  -> REBUILD_TABLE / PATCH_DML per table
  -> Dolt replay renderer
  -> optional external dialect renderer
```

### 暂定建议（尚未成为正式决策）

- 当前默认保持 `REBUILD_ALWAYS`。
- 后续增加 `ADAPTIVE_PATCH`：符合 eligibility 且小于阈值时使用 DML，否则重建。
- 不直接复用前端 ComparisonRecords；需要 storage-level change set，包含完整
  persisted-column values 和 canonical physical key。
- 只允许稳定 keyed `STANDARD_DIFF` 表；schema/key/storage projection 变化、keyless、
  ordered、degraded、unsupported、derived table 等默认整表重建。
- 建议阈值同时考虑 changed row count、change ratio 和 estimated patch SQL bytes。
- hidden summary table 作为小型 derived fact 独立重建；composite/其他 derived table
  首版也建议整表重建。
- Dolt 的 `replay.sql` 可以包含 DML，Repository Service public contract 预计无需
  改动；最终 manifest 仍描述最终 schema/row count。
- 不建议把 Dolt/MySQL 风格 `replay.sql` 直接发送给 PostgreSQL；应由通用
  `StorageMutationPlan` 分别渲染 Dolt 和 PostgreSQL dialect。
- 外部同步需要 base snapshot/commit precondition、target drift detection、transaction
  boundary、idempotency/change-set digest 和 full resync 策略。

### 本轮已确认的 ADAPTIVE_PATCH 决策

- `composite_signal_point` 等表在 source materialization 完成后均视为普通 canonical
  table；relay 阶段不因其派生来源而默认整表重建。它们与普通表使用相同的
  `PATCH_DML`/`REBUILD_TABLE` eligibility、key、projection、digest、plan 和事务边界。
- `changed_row_count` 与 `change_ratio` 是首版唯一的 patch 选择阈值，且必须同时满足：
  - `changed_row_count <= 1,000`
  - `change_ratio <= 5%`
- 删除 `estimated patch bytes` eligibility 条件。既有 artifact admission 仍然有效：最终
  `replay.sql > 200 MiB` 时直接拒绝，不拆分、不 fallback；这属于 artifact 容量门禁，
  不是 patch 选择阈值。
- 同一行更新多个字段只计一次 `UPDATE`；字段数量不放大 `changed_row_count` 或
  `change_ratio`。canonical key 变化表达为 `DELETE + INSERT`，计为两个物理 mutation。
  同一 key 的中间变化先归并为最终 before/after；最终无变化为 `NOOP`。
- mutation identity 使用 canonical storage key，而不是仅用于前端 comparison 的
  `effective compare key`。二者不一致的表首版不允许 `PATCH_DML`，自动使用
  `REBUILD_TABLE`。
- `StorageMutationPlan` 允许同一 plan 中混合 `PATCH_DML`、`REBUILD_TABLE` 和 `NOOP`；
  表内顺序固定为 `DELETE -> UPDATE -> INSERT`，各阶段按 canonical key 排序。
- 中间 `ChangeSetArtifact` 完全结构化，不保存 Dolt/PostgreSQL SQL 文本。mutation 至少
  包含 table、operation、canonical storage key、before-row digest 和 after-image；
  `manifest.json` 保存 source/base/target identity、projection/ruleset/policy digest、
  counts、change-set digest 和 encoding 信息。
- `UPDATE` 使用完整 persisted after-image，而非仅 changed columns；key 不作为 SET 字段。
  generated/server-default/无法直接写入的字段会使该表不满足首版 patch eligibility。
- renderer capability 必须参与 plan identity 和 planner 选择。renderer 不支持某种值或
  操作时，effect 前返回稳定的 `TARGET_CAPABILITY_UNSUPPORTED`；不得静默 stringify、
  偷改 plan，或在 executor 内部隐式切换 mutation policy。
- Dolt renderer 生成 deterministic `replay.sql`；外部 renderer 生成 target-specific
  parameterized command stream；二者共享同一 `ChangeSetArtifact` 和 mutation digest，
  不直接复用彼此的 SQL 文本。
- `ChangeSetArtifact` 在 Preview/Submit reuse、Dolt replay、可选 external ChangeSet、
  readback/audit 完成前保持 pinned；缺失、损坏或 digest 不匹配时 Submit 只能走已确认的
  source materialization fallback。

### 尚待讨论

- PATCH eligibility 是否允许 foreign-key/trigger/cascade 依赖，及其顺序合同。
- 阈值是否固定为行数 + 比例 + SQL bytes 三重门槛，具体默认值如何 benchmark。
- UPDATE 的 optimistic guard、affected-row 检查和 patch 应用后的 content digest 校验。
- `StorageMutationPlan` 是否在 P3 只收口 contract/fixtures，还是连同 Dolt renderer
  一起实现。
- 外部 PostgreSQL/change-set capability 的正式阶段和 target contract。
- patch retry、private ref replay 和外部 target exactly-once 的完整验证矩阵。

### 已确认的派生表与 Submit 复用原则

- 派生逻辑只在 source materialization 阶段执行；Preview 和 Submit fallback 都可能
  执行该阶段，但物化完成后 `composite_signal_point` 等表按普通 canonical table
  处理。
- Submit finalize 正式采用 `reuse-first`：优先复用 exact Preview-bound
  `SnapshotTableArtifact` 和 provisional mutation/replay candidate，完成 binding、
  descriptor、digest、ruleset、storage projection 和 base commit 校验后 finalize。
- 从 durable `SubmitSourcePackage` 重新 source materialize 仅作为 artifact 缺失、损坏、
  profile 不足、binding/digest 不匹配、恢复或显式重算时的 fallback。
- Preview 可以按 retention/materialization profile 不保留完整 current rows；但必须明确
  区分 `FULL_ROW_ARTIFACT` 与 `SUMMARY/LIGHTWEIGHT_READER`，不能把轻量 artifact 当作
  可直接用于 Submit 的完整 artifact。Submit 接受时若完整 artifact 不存在，则走
  durable source fallback。
- 基础表与 `composite_signal_point` 等同一 canonical snapshot 中发生的变更，应进入同一
  `StorageMutationPlan`，在 Dolt 中同一 private ref/commit，在支持事务的外部目标中同一
  transaction 提交；不支持原子提交的外部目标不得宣称完整同步成功。
- provisional mutation candidate 只有在以下内容全部匹配后才能 promotion：source/binding
  identity、base repository commit/ref、current snapshot/storage manifest、table ruleset
  and storage projection、threshold policy、change-set digest、artifact closure/content
  digests 和 target renderer policy。仅 `fast_row_digest` 匹配不足以 promotion。

### 已确认的 ruleset repository 边界

- `TableRulesetSnapshot` 可以作为 protected hidden metadata table 随正式 canonical
  commit 原子保存，用于 storage semantics/provenance；它不进入 ordinary table listing、
  comparison、risk、bundle、`StorageMutationPlan` 或 external sync。
- ruleset snapshot 不是 live configuration source。未来热加载仍走
  `validate -> activate -> immutable snapshot`；已运行 operation 继续使用捕获时的 snapshot。
- `table_ruleset_digest` 与 `storage_projection_digest` 应进入 Snapshot/storage identity；
  不只依赖 ruleset version。
- Risk ruleset 首版继续保存在 RiskEvaluation、risk annotation artifacts 和 operation/audit
  metadata 中，不强制写入业务 repository commit；未来可选 protected snapshot，但不自动
  改变 history compare policy。
- History compare 首版统一使用程序当前默认 ruleset，不读取历史 ruleset 做额外判定，
  不增加 ruleset mismatch 分支。历史 ruleset snapshot 如存在，仅作为 provenance/readback
  metadata。
- 不为了 ruleset 变化单独创建空业务 commit；规则快照在下一次正式 canonical commit
  中随业务事实原子更新。

### Ruleset activation 与安全生命周期补充

- 首版 ruleset 变更采用 `validate -> pending_restart -> graceful drain -> safe restart ->
  activate`，不实现在线 watcher。安全重启和安全关停共用同一 lifecycle contract；首版
  graceful drain timeout 为 `180s` 的 deployment/runtime 默认值，不属于 capability
  contract，超时进入 `DRAINING_TIMEOUT`，不自动强杀。
- `DRAINING` 默认拒绝新的 Preview、Submit、history compare 及会创建 artifact/cache/
  external ChangeSet 的请求；允许 health/readiness、metrics、admin readback 和已有
  operation 状态查询。已有 operation 继续执行并由 durable runtime 接管。
- 新 ruleset 不重写已有 repository commit，不自动创建空 commit；已捕获旧 snapshot 的
  operation 继续使用旧规则。
- activation validator 预留影响分类：`ADDITIVE`、`BEHAVIORAL`、`STORAGE_BREAKING`。
  改变 canonical key、字段集合、类型或 storage projection 的 `STORAGE_BREAKING` 规则
  必须标记 `MIGRATION_REQUIRED`，走显式 migration/rebuild operation，不能直接 activation。
- additive ruleset 可面向未来 source materialization 生效；rollback 只影响未来 operation，
  不回滚已有 repository commit。
- ruleset 更新未来可建模为 durable administrative operation；首版只预留状态/provider
  边界，不实现 watcher、在线热加载或完整 migration executor。

### Ruleset migration 边界

- `STORAGE_BREAKING` 变更不进入 Phase 3，也不能随 ruleset activation 自动执行。candidate
  可以完成 validation/classification，但必须停在 `MIGRATION_REQUIRED`；在 migration 完成
  前保持旧 active ruleset，不能让不同表混用新旧 storage projection。
- 影响分类至少包括：`ADDITIVE`、`COMPARISON_BEHAVIORAL`、`RISK_ONLY`、
  `STORAGE_BREAKING`。改变 canonical key、字段集合、类型、null 语义或 storage projection
  的变更属于最后一类。
- migration 从 FINAL canonical repository state 读取数据，按新 ruleset 重新生成受影响表
  的 canonical snapshot/storage projection，通过完整 rebuild 创建新的 Dolt commit；不
  改写旧 commit、不自动创建空 commit。受影响 external target 另行要求 full resync。
- 新增此前不存在的异常表可以作为 `ADDITIVE` 规则面向未来 source 生效；已有表从无有效
  key/不支持变成新的 canonical storage 语义时属于 `STORAGE_BREAKING`。

### 业务重新上传与 Repository integrity incident

- 重新上传只用于恢复 provisional/未产生权威 repository effect 的流程。Preview artifact、
  provisional cache、未提交 mutation plan 丢失或损坏时可以丢弃并重新上传；Submit 在
  Repository effect 前可从 durable source fallback，source 也不可用时创建新的 attempt。
- 重新上传统一创建新的 Preview/Submit attempt，不复用旧 attempt id；通过
  `recovery_of`、source upload、previous failure code、base commit 和 ruleset snapshot
  记录关联关系。
- Dolt commit 已完成后，重新上传不得替代、覆盖或回滚原 commit；external target 失败
  必须针对原 canonical commit 做 resync，不能用新上传数据掩盖 target drift 或 readback
  mismatch。
- Repository/content readback mismatch、CAS ambiguity 或其他权威事实问题必须产生
  durable `RepositoryIntegrityIncident`（或等价 control metadata），至少记录 repository/
  operation/commit/ref、expected/observed digest、affected tables、failure class、
  recommended action、首次/最近发现时间、acknowledgement 和 resolution reference。
- incident 通过 operation/user-visible stable code、结构化持久日志、metrics/alert 和
  admin readback 多渠道暴露；不只依赖日志文本。integrity incident 不进入普通 artifact
  cleanup，至少保留到显式 acknowledge、resolution 记录和 operator archive。
- Repository health 首版区分 `HEALTHY`、`DEGRADED`、`REUPLOAD_REQUIRED`、
  `FULL_RESYNC_REQUIRED`、`BLOCKED`。incident 保存身份、digest、状态和诊断引用，不保存
  大规模业务 row payload、secret 或可被普通 cleanup 自动删除的内容。

## 11. 当前明确不应推断的事项

- 不得把本摘要当作 P3 implementation authorization。
- 不得把 `ADAPTIVE_PATCH`、PostgreSQL renderer 或阈值默认值当成已接受 contract。
- 不得把 zstd、Python fallback、自动 ruleset watcher、正式版本迁移、独立 compute
  service 视为首版已承诺能力。
- 不得因为 ComparisonRecords 已有 before/current values，就假设它足以生成 storage
  mutation；storage projection 和 comparison projection 必须保持 ownership 分离。

## 12. 主要参考

- [P3 Active Context Index](../formal/plans/p3-active-context-index.md)
- [Implementation Stages](../formal/plans/implementation-stages.md)
- [Canonical Storage and Repository Boundary](../formal/contracts/canonical-storage-and-repository-boundary.md)
- [Snapshot Contract](../../contracts/snapshot.md)
- [Comparison Contract](../../contracts/comparison.md)
- [Risk Contract](../../contracts/risk.md)
- [Comparison Bundle Contract](../../contracts/comparison-bundle.md)
- [ADR 0001: Python/Rust Hybrid Compute Strategy](../formal/adr/0001-python-rust-hybrid-compute-strategy.md)
- [ADR 0013: ENUM/SET V1 Import Semantics](../formal/adr/0013-enum-set-v1-import-semantics.md)

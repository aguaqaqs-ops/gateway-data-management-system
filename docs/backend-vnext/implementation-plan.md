# Implementation Plan

本文定义 backend vNext 的模块级执行计划。它面向实际编码顺序和每一步的完成标准；长期边界仍以 `implementation-boundary.md`、`modules.md`、`contracts/` 和 `capabilities/` 下的设计为准。

## 总原则

1. 按依赖关系推进，不按业务 flow 先后推进。
2. 先实现基础模型，再实现可独立测试的 capability，最后串联 operations / flows。
3. 每个 capability 编码前先收口 stable entrypoint API。
4. Capability 必须 flow-neutral；upload、submit、history compare 等业务语义只在 flow / operation 层表达。
5. Benchmark、功能测试和后续业务 flow 都应调用正式模块，不长期维护一套独立实现。
6. 新包不 import 旧业务模块；旧实现只作为语义参考、fixture 对照和性能问题样本。

## RepositoryServer 的位置

`repository_server` 本地模块应提前实现，但不需要早于所有 capability。

建议边界：

- `core`、`artifacts`、SQL-only `snapshot_materialization` 不依赖 repository_server，应先行。
- repository-backed 能力开始前必须先有 repository_server 本地模块，包括 `RepositoryRegistry`、`repository_ref_materialization`、Dolt readback/export、Dolt native provider 和 repository table cache。
- `repository_import` 的 SQL artifact 构建可以不依赖 repository_server，但正式 readback validation、catalog/export 复用和后续 provider benchmark 应尽量走 repository_server 的本地 API。
- 本轮 repository_server / repository_service 只把 `dolt-test/dolt-import-provider-functional-test-result-2026-06-20.md` 中已通过的 provider 当作支持基线；`backend_vnext/capabilities/repository_import/` 的实现和回归测试是可直接参考的正式代码来源。未进入该基线的 Dolt 行为先按 fallback / diagnostic 处理，不作为本轮 contract 扩展目标。

这样可以避免两种问题：

- 为了纯 SQL 解析提前引入 Dolt/repository 依赖，增加实现复杂度。
- 后续 repository-backed capability 各自直接封装 Dolt CLI/server，形成重复逻辑和不一致 cache 行为。

## 模块级执行顺序

### 0. Implementation Preflight

目标：

- 确认代码落点为 `gateway-data-management-system/backend/backend_vnext/`。
- 确认测试目录为 `gateway-data-management-system/backend/tests/backend_vnext/`。
- 确认后端命令使用 `gateway-data-management-system/backend/.venv/`。

注意事项：

- 不复制旧业务模块到新包。
- 不在第一步引入 flow、operation 或 API 层。
- 如需复用旧实现中的代码，先回到设计文档讨论并记录 exit plan。

参考文档：

- `implementation-boundary.md`
- `modules.md`

### 1. Core Foundation

目标模块：

```text
backend_vnext/core/
```

优先实现：

- `Result` / `Error` / `Diagnostics`
- canonical serialization
- stable digest helper
- contract/version constants
- 基础错误分类和 phase 标识

完成标准：

- digest 和 canonical serialization 有单元测试。
- diagnostics 不包含 host-only identity、临时路径或敏感 payload。
- core 不依赖 artifacts、repository_server、capabilities、operations 或 flows。

参考文档：

- `identity-and-digests.md`
- `implementation-boundary.md`
- `modules.md`

### 2. Artifact Foundation

目标模块：

```text
backend_vnext/artifacts/
```

优先实现：

- `ArtifactRef`
- `ArtifactManifest`
- local artifact store
- records artifact JSONL writer/reader
- artifact closure manifest
- operation-local ref restore 的基础能力

完成标准：

- manifest digest 稳定。
- artifact identity 不依赖 host path。
- records artifact 和 closure 可被 comparison、risk、surface、bundle 复用。
- 第一版只实现本地存储，不实现远端存储、TTL、eviction 或完整 cache registry。

参考文档：

- `artifacts.md`
- `contracts/comparison.md`
- `contracts/risk.md`
- `contracts/comparison-bundle.md`

### 3. Snapshot Materialization SQL Path

目标模块：

```text
backend_vnext/capabilities/snapshot_materialization/
```

优先实现 stable entrypoint：

- `stage_source_package`
- `resolve_required_sql_document`
- `resolve_sql_dump_source`
- `parse_sql_dump_source`
- `materialize_sql_dump_source`
- `resolve_snapshot_table_set`

完成标准：

- SourcePackage 容器解析与 SQL dump parser 解耦。
- 当前业务约定只要求唯一 `/sql/dbcfg.sql`。
- SQL parser 可直接消费 `SqlDumpSource`，支持测试/benchmark 的裸 SQL 或 `.sql.gz` compat input。
- 输出 `Snapshot`、`SnapshotSummary`、`SnapshotTableDescriptor`、`SnapshotTableReader` 和 raw DDL digest。
- 本阶段先收口 row-stream-first、provisional/final summary 和轻量 reader init；不要把 CSV/TSV/Parquet 作为默认同步产物，相关 staging/export 先按需开启，后续在第 9/10 步串联 `diff compute`、`risk` 和 `bundle` 时再统一复盘是否需要前移。
- schema policy、字段大小写 canonical、字段交集比较、极端 schema 冲突降级均有最小测试覆盖。

参考文档：

- `contracts/source-package.md`
- `contracts/snapshot.md`
- `contracts/snapshot-table-access.md`
- `capabilities/snapshot-materialization.md`
- `testing-fixtures.md`

### 4. RepositoryServer Local Module

目标模块：

```text
backend_vnext/repository_server/
```

优先实现 technical capability：

- `registry`
- `dolt_backend`
- `ref_session`
- `catalog`
- `table_reader`
- `table_export`
- `table_cache`

完成标准：

- 本地 Python API 按未来网络 API / Unix socket 边界设计。
- 不暴露 Workspace、Submission、History request 等业务模型。
- 不产出 Snapshot、Comparison、RiskReport 或 Bundle。
- repository-local registry v1 先落最小 SQLite schema，承载 repository-local metadata / cache / scan index，不做 TTL、pin、eviction 或 export cleanup 策略。
- `open_ref()` read-only、pinned-to-commit、支持 timeout、语义幂等。
- catalog / reader 第一版能支撑 repository ref materialization 和 readback validation。
- `repository_server_table_cache` 第一版只做 repository-local 技术 cache，后补 TTL、pin、eviction 和 export cleanup。

参考文档：

- `capabilities/repository-ref-materialization.md`
- `modules.md`
- `artifacts.md`
- `dolt-test/dolt-import-provider-functional-test-result-2026-06-20.md`
- `dolt-test/dolt-native-diff-functional-test-result-2026-06-21.md`

### 5. Repository Ref Materialization

目标模块：

```text
backend_vnext/capabilities/snapshot_materialization/repository_ref.py
```

优先实现：

- `materialize_repository_ref`
- repository table access 到 `Snapshot` / `SnapshotSummary` / `SnapshotTableSet` 的归一化
- repository scalar encoding 复用

完成标准：

- 同一 repository ref 生成 SnapshotSummary 时最多加载一次 catalog。
- comparison 不直接 list repository tables，只消费 SnapshotSummary 和 SnapshotTableSet。
- Snapshot materialization 负责业务对象归一化，repository_server 只负责 repository-local table access。
- 本阶段产出的 `scalar_encoding`、模型字段和 digest helper 仅作为共享基础件，不构成第 7 步 comparison 内部实现的硬约束；后续若需调整 planner / projection / provider 的内部结构，只要继续满足模块间约定与公开 contract 即可。

参考文档：

- `capabilities/repository-ref-materialization.md`
- `capabilities/snapshot-materialization.md`
- `contracts/snapshot.md`
- `contracts/snapshot-table-access.md`

### 6. Repository Import Capability

目标模块：

```text
backend_vnext/capabilities/repository_import/
```

优先实现：

- import artifact builder（支持单次 build 内按 `row_layout_digest` 复用 row files）
- provider runner
- writer lease / server lifecycle 的本地抽象
- readback validation
- benchmark 已验证 primitives 的正式化

补充边界：

- 正式 capability 先行，benchmark runner 作为基于正式 capability 的 orchestration / diagnostics 层，不反向定义 capability contract。
- `writer_lease_context`、`idempotency_key` 和 `base_ref_or_commit` 属于正式 repository-level 输入；benchmark 只负责传递或在测试场景下提供显式模拟值，不在 runner 内硬编码业务语义。
- `profile` 只属于 benchmark contract，用于选择 provider / validation / server reuse 组合，不进入 `repository_import` capability contract。
- `requested_tables` 只保留单一来源，优先在 dataset resolution 或 plan 构造阶段一次性确定，artifact builder 不再二次决定表子集。
- server lifecycle 的细粒度计时可以保留在 benchmark result / diagnostics 中，但正式 capability result 只保留稳定字段。
- 首版只接受已确认的 `RepositoryImportImportMode` / `RepositoryImportSchemaMode` 组合，其他组合必须明确报 unsupported diagnostic，而不是静默降级。

完成标准：

- benchmark 中可复用的 SQL/Dolt primitives 被吸收到正式模块。
- benchmark runner 反向调用正式 capability。
- provider 成功不等于 import 成功，必须有 readback validation 或明确的 degraded validation status。
- validation 命名使用 `VERIFY_SCHEMA_ROW_COUNT_SUMMARY` / correctness smoke 等已确认语义，`DISABLED` 不参与 correctness 结论。

参考文档：

- `capabilities/repository-import.md`
- `repository-import-benchmark-runbook.md`
- `_tmp/repository-import-benchmark-implementation-plan.md`
- `dolt-test/dolt-import-provider-functional-test-result-2026-06-20.md`

### 7. Comparison Compute

目标模块：

```text
backend_vnext/capabilities/comparison/
```

优先实现：

- `ComparisonInput`
- `TableRulesetSnapshot`
- hardcoded ruleset registry
- comparison planner
- projection
- `SUMMARY_EARLY_EXIT`
- 普通表 `HASH_STREAM_COMPARE`
- records artifact 输出
- comparison core cache handoff 接口

本阶段明确不实现：

- `ORDERED_TABLE_COMPARE` / ordered diff / ordered risk semantic restoration
- `PROJECTION_TABLE_COMPARE`
- `ProjectionTableArtifact` 的独立持久化与 `projection_table_cache`
- `DOLT_NATIVE`
- risk / surface / bundle 组装
- `runtime_policy` 驱动的 projected payload 估算和 `HASH_STREAM_COMPARE` / `SQLITE_SPOOL_COMPARE` mode selection，留到 projection 正式实现后再补

完成标准：

- Capability 只消费 SnapshotSummary / SnapshotTableSet / SnapshotTableReader。
- Flow 负责选择 TableRuleset，capability 只应用传入的 frozen snapshot。
- TableRuleset registry 第一版 hardcoded，但输出可序列化、可 digest，保留未来配置文件 loader。
- comparison core cache 第一版先只定义 handoff 接口和 canonical value 形状，不强制实现 cache registry、promotion 或 eviction。
- projection 只要求逻辑层和流式中间层可用，不要求独立 artifact/cache。
- `runtime_policy` 先只保留 opaque seam，不做 mode selection；等 projection 正式实现后再补 projected payload 估算和 SQLite spill 路径。
- 默认优先 `HASH_STREAM_COMPARE`；只有在 projected payload 明显超预算或调用方显式要求落盘时才切到 `SQLITE_SPOOL_COMPARE`，这里是实现级性能策略，不是 contract 语义。
- `FULL_ROW_DIGEST_SET_DIFF` 作为 ruleset / fallback 语义保留，但本阶段默认不启用。
- 若 table 被 ruleset 标记为 ordered role 但 provider 未接入，必须显式降级为 `DEGRADED`，并保留 ordered diagnostics，不得伪装为普通表 diff。
- 第 5 步形成的共享基础件可被第 7 步重构或替换内部组织方式，只要保持 `contracts/comparison.md` 与模块间输入输出约定一致即可；第 5 步不会反向锁死第 7 步的实现细节。

参考文档：

- `contracts/comparison.md`
- `capabilities/comparison-compute.md`
- `artifacts.md`
- `_tmp/cache-framework.md`

### 8. Risk Evaluation

目标模块：

```text
backend_vnext/capabilities/risk_evaluation/
```

优先实现：

- `RiskRulesetSnapshot`
- hardcoded risk registry
- risk facts extraction
- structural / standard row / degraded risk
- ordered unsupported review-required placeholder
- risk annotation artifact

完成标准：

- Capability 不计算 diff，不读取 SourcePackage / RepositoryRef / repository_server。
- Flow 负责选择 RiskRuleset，capability 只应用传入的 frozen snapshot。
- RiskRuleset registry 第一版 hardcoded，但输出可序列化、可 digest，保留未来配置文件 loader。
- 本轮只收口 risk capability 本体与 annotation artifact 落盘，不提前实现 operation artifact closure、surface assembly 或 bundle assembly。

参考文档：

- `contracts/risk.md`
- `capabilities/risk-evaluation.md`
- `contracts/ordered-diff.md`

### 9. Surface And Bundle Assembly

目标模块：

```text
backend_vnext/capabilities/surface_assembly/
backend_vnext/capabilities/bundle_assembly/
```

优先实现：

- thin `ComparisonSurface`
- surface ref validation / rewrite
- surface digest
- `ComparisonBundle`
- bundle artifact closure
- bundle-relative ref rewrite

完成标准：

- Surface / bundle 不计算 diff，不计算 risk，不读取 repository。
- Bundle assembly 第一版只实现 ComparisonBundle core，不引入兼容层。
- ordered table 第一版可保留 extension，不强行实现完整展示。
- 第一阶段优先把 bundle assembly core 在 `backend_vnext/capabilities/bundle_assembly/` 独立实现，旧 preview/workbench 保持 legacy 独立实现，迁移期间不要互相转发。

参考文档：

- `contracts/comparison-surface.md`
- `contracts/comparison-bundle.md`
- `capabilities/surface-assembly.md`
- `capabilities/bundle-assembly.md`
- `frontend-surface-simplification.md`

### 10. Operations And Flows

目标模块：

```text
backend_vnext/operations/
backend_vnext/flows/
```

优先实现：

- operation persistence
- step diagnostics
- retry / cancel
- artifact closure before READY
- upload preview flow
- submit acceptance / commit finalize flow
- history compare flow

完成标准：

- Flow 只编排业务状态和 capability 调用。
- Operation 负责异步、重试、失败诊断和 artifact readiness。
- heavy Dolt import / finalize 任务放入异步流程，不阻塞 upload/history compare 的快速反馈路径。
- commit finalize 是正式 Dolt 数据和正式 cache promotion 的权威点。
- read-only sidecar adapter materialization 只在需要旧前端手测或适配验收时进入第 10 步；如果当前阶段不做旧前端手测，可以先只落 adapter contract 与 seam，把真实 materialize 延后到第 11 步相关能力稳定之后再补。

建议定稿：

- operation persistence 用“1 个 operation 主表 + 1 个 step 明细表”的最小结构即可。主表只保留执行状态、caller type、retry 关系、失败摘要和 READY 所需 closure digest；业务事实不进 operation 表。
- step 名称保持 flow-neutral，优先用稳定枚举表达执行阶段，不直接写 legacy UI 名称。第一版可以先覆盖 `LOAD_INPUT`、`MATERIALIZE_SNAPSHOT`、`COMPUTE_COMPARISON`、`COMPUTE_RISK`、`ASSEMBLE_SURFACE`、`ASSEMBLE_BUNDLE`、`MATERIALIZE_READ_ONLY_ADAPTERS`、`PUBLISH_RESULT`、`CLEANUP`。
- `retry` 只允许显式标记为 `retryable` 的失败，不允许跳过 digest / binding validation。
- `cancel` 只做 best-effort 停止，不回滚已固化业务事实；被 supersede 的 warmup 允许自然过期。
- `READY` 只由“所需 artifact closure 完整且可解析”决定，不由 cache warmup 成败决定。
- 先把 read-only adapter policy / seam 定义清楚，真实 sidecar materialize 可以在需要旧前端手测时进入第 10 步，否则延后到第 11 步。
- submit acceptance 的 workspace 入口先收敛到 `backend_vnext/workspaces/` 薄层：只负责 `PREVIEW_READY` gate、preview binding 比对、`active_submit_operation_id` 乐观写入和失败回滚，不把 repository import 细节塞进 flow。
- submit finalize 的 workspace 归位也应走同一薄层：在 repository import 成功后把 workspace 推进到 `SUBMITTED`，并写入 `submitted_submission_id`，不要把业务状态推进直接塞进 finalize flow。
- `submission_id` 应在 submit acceptance 阶段分配，并作为后续 finalize 的稳定业务 ID 复用。
- 旧实现只建议复用语义样例、fixture、失败场景和旧 mapping 表；不要直接复用旧 runtime adapter 或旧 UI payload builder。ordered diff、projection table、history compare native diff 仍按第 11 步处理。

参考文档：

- `flows.md`
- `operations.md`
- `artifacts.md`
- `capabilities/repository-import.md`

### 10.1 Legacy Sidecar Compatibility

目标模块：

- read-only adapter contract / seam，收口在 `flows` 与 `operations` 的正式接口内，不再单独保留旧兼容模块。

职责边界：

- `flows` 决定某个请求是否需要 read-only sidecar adapter，以及需要哪一组适配文件。
- `operations` 在 READY 前把旧 diff / risk / diagnostics sidecar 从 comparison / risk 的原始 artifact 对象 materialize 出来。
- 兼容输出只服务只读路径，不引入 upload、submit、review 或 withdraw 语义。
- `ComparisonBundle` 只提供可重写 refs 和闭合事实，不作为 sidecar 字节的逆推来源。
- 如果所需原始 artifact 字节不可用，operation 应记录诊断并失败，不要伪造兼容文件。
- 如果第 10 步不以旧前端手测作为验收条件，read-only sidecar adapter 可以先只保留 contract 和调用 seam，不要求在本阶段完成真实字节 materialize；完整适配实现可在第 11 步 ordered / projection / native diff 稳定后再补。

第一版优先覆盖：

- Upload Preview 的旧前端只读兼容路径。
- History Compare 的旧 Workbench 只读兼容路径。
- 兼容文件的具体格式和路径固定后，再逐步收敛到稳定 contract。

### 10.2 Implementation Ready

本轮围绕第 10 步已经收口的决策如下：

- 第 10 步可直接进入代码实现，优先落 `operations` / `flows` 骨架和最小 runtime，而不是继续扩展新的设计分支。
- 并行策略第一版保持串行为默认，只对双份业务数据上传或两个 pair 比较启用固定双槽 fan-out / fan-in。
- 单份业务数据保持完全串行，不引入通用 DAG 调度器。
- read-only sidecar adapter 先保留 contract 和 seam；是否真实 materialize 由是否需要旧前端手测决定，不作为第 10 步的硬前置。
- 旧实现只用于语义样例、fixture、失败场景和 legacy mapping，不直接复用旧 runtime adapter 或旧 UI payload builder。
- submit acceptance 负责创建 `OperationKind.SUBMIT_FINALIZE` queued operation，finalize worker 只按 `operation_id` 接管既有 operation，不在 finalize 阶段重新创建。
- ordered diff、projection table 和 history compare native diff 仍然延后到第 11 步。

### 11. Advanced Providers, Cache And Benchmarks

目标模块：

```text
backend_vnext/capabilities/comparison/providers/
backend_vnext/capabilities/comparison/ordered/
backend_vnext/cache/
backend_vnext/benchmarks/
```

本节收口结论（v1）：

- Ordered table compare 需要单独建模，但只做 thin split：`ordered` policy、`ordered` records、`ordered` extension 和 ordered provider 独立存在；共享 comparison core、digest、surface/risk 基础契约，不把 ordered 语义塞回 generic snapshot compare。
- Ordered P1 会吸收一部分 projection normalization 作为前置处理；这部分只保留单一实现，不在 ordered provider 内重复建模为第二套归一化逻辑。
- DOLT_NATIVE eligibility / fallback 冻结为两层：
  - pair 级 eligibility 面向所有 `Dolt -> Dolt` comparison pair；当前最先落地和验证的 consumer 是 `history compare`，但它不是唯一 consumer。
  - pair 级 eligibility 先判断 repository-backed、同仓库、immutable commit、Dolt capability、table list 对齐。
  - table 级 fallback 处理 ordered table、projection/effective key 重复、key change、rename 未决、schema policy 不一致、canonicalizer 失败等情况。
  - 先固定稳定的 fallback reason enum，再实现 provider。
- cache formalization 先收口到三个命名空间：
  - `comparison_core_cache` 只缓存 canonical `ComparisonFacts + ComparisonRecordsClosure`。
  - `projection_table_cache` 只缓存 compare-ready projection artifact；命中规则采用 raw artifact identity + projection contract/ruleset exact match，不做“raw 变了但 projection 没变”的内容级推断。
  - `repository_server_table_cache` 只负责 repository-local export/catalog artifact。
- `comparison_core_cache` / `risk_evaluation_cache` / `comparison_surface_cache` / `flow_assembly_cache` 的 payload schema 由各自模块决定，但都必须遵守统一的 artifact envelope、版本化 schema、digest 和 closure 规则。
- `projection_table_cache` 第一版若持久化 row-level table artifact，优先沿用 `manifest + Parquet rows`；`repository_server_table_cache` 第一版只缓存小型技术事实和 metadata，row-level export artifact cache 不进入本轮主线。
- projection cache 只保留最简单的 exact-match 命中和异步持久化，不做更复杂的 semantic equivalence 设计。
- repository_server cache cleanup 第一版只做 `clear()` + `cleanup_expired()`；仅清理可重算 IO cache，TTL 先定 180 天，catalog 只保留手动清理。
- benchmark 采用三层口径：
  - correctness matrix：先验证 canonical facts / records contract / fallback diagnostics。
  - performance matrix：再测 provider / cache / forced hash / forced SQLite / native / fallback 组合。
  - dataset matrix：按 small / medium / large 和 ordered-specific fixture 覆盖不同数据形态。
- benchmark 主路径以 flow 为唯一入口；出现问题时允许把同一输入按 operation -> capability 逐层下钻做定位，但下钻结果只作为诊断 profile，不作为新的主实现。
- benchmark 第一轮建议先跑不启用 read-only adapter 的 baseline，再跑启用 adapter 的同一旅程；如果旧实现仍可用，可再补 parity 对比，但不要把额外适配层开销混入主性能结论。

完成标准：

- Dolt native provider 输出必须归一化为 `ComparisonFacts + ComparisonRecordsClosure`。
- projection/ignored columns 默认走 vNext comparison core；Dolt native projection 只作为可选优化。
- ordered diff 保留旧 IEC104 list family、gid/no、pseudo blank、tail/middle/move 风险语义。
- projection table cache 仅采用 raw identity 精确命中，不引入内容级等价推断。
- repository_server cache cleanup 的 v1 只需要简单、可解释、可手动触发。
- provider benchmark 调用正式 capability，不复制 provider 逻辑。

参考文档：

- `capabilities/dolt-native-provider.md`
- `capabilities/ordered-diff-compute.md`
- `contracts/ordered-diff.md`
- `contracts/ordered-diff.md`
- `adr/0003-dolt-native-provider-selection.md`
- `dolt-test/dolt-native-diff-functional-test-result-2026-06-21.md`

建议实现顺序：

1. 先冻结接口和诊断字段：ordered policy、native provider decision / fallback reason、cache key / version、benchmark result schema。
2. 先落 cache formalization 和 cleanup：`comparison_core_cache`、`projection_table_cache`、`repository_server_table_cache` 的最小 registry / clear / cleanup 路径。
3. 先做 ordered provider 第一切片：IEC104 family、gid/no、pseudo blank、semantic_kind、table_processing_mode、tail/middle/move 风险恢复。
4. 再做 DOLT_NATIVE provider：pair 级 eligibility、table 级 fallback、canonicalizer、diagnostics。
5. 最后补 benchmark harness：先 correctness，再 performance，最后 dataset / crossover 比较；主路径先跑不启用 read-only adapter 的 baseline，再跑启用 adapter 的同一旅程；benchmark 骨架可以并行起，但收口以 capability 稳定后为准。

当前判断：

- 当前已经具备收口到 Step 11 第一版设计并开始实现的条件。
- 可以开始的部分包括：ordered v1 slice、DOLT_NATIVE scaffold、comparison cache formalization、repository_server 简化 cleanup、benchmark 骨架。
- 不建议等待全部 benchmark 数据再开工，因为 benchmark 本身依赖这些 capability 先落地。
- 还不算最终完全收口的点主要是：P2 planner 是否需要按业务数据启用、benchmark 阈值和 crossover 口径。
- ruleset loader 的 simple v1 约定已纳入当前实现计划；后续仅在需要切换配置文件格式或支持更复杂加载方式时再讨论。
- `DOLT_NATIVE` fallback reason 已在当前设计中冻结，若后续没有新冲突，可从 open items 中移除。

## 每个 Capability 的固定落地步骤

1. 写清 stable entrypoint API：输入、输出、版本、digest、diagnostics。
2. 写最小 fixture：happy path、degraded path、错误 path。
3. 实现纯模型和 canonical digest。
4. 实现本地 artifact layout 或声明不产出 artifact。
5. 实现 capability 主流程。
6. 增加 contract test 和 integration smoke。
7. 更新 benchmark / flow 调用方，移除重复实现。

## 实现过程中需要继续明确的内容

- `Result` / `Error` / `Diagnostics` 的字段级 schema。
- local artifact store 的目录布局、临时文件命名和 cleanup 约定。
- operation persistence 的状态表、step id、retry policy 和 READY artifact closure。
- TableRuleset / RiskRuleset 从 hardcoded registry 切换为配置文件时的 loader contract；`ruleset loader` 的 simple v1 约定已纳入当前实现计划，当前不作为 Phase 0 阻塞项。
- comparison core cache 的正式 registry / validation / promotion / eviction 细节。
- ordered P2 planner 是否需要按业务数据启用，以及复杂 reorder / shift repair 的降级命名。
- hash / SQLite mode 的阈值和 benchmark 切换规则见 `adr/0002-comparison-hash-sqlite-mode-selection.md`，必要时再根据 benchmark 结果收紧或放宽。

这些问题不阻塞基础模块和 SQL-first capability 实现；进入对应阶段前必须补充设计或 ADR。

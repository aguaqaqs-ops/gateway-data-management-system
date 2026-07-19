# 后端 vNext

本文档区用于重新设计 gateway 后端 vNext。

vNext 设计不以兼容旧后端、迁移旧数据或保留现有内部契约为前提。旧系统只作为问题样本和业务语义来源，不作为模块、状态机、ID/hash 或 artifact 结构的强制约束。

## 目录约定

- `dolt-test/`：Dolt 功能测试结果归档。
- `glossary.md`：术语表。稳定后用于人和 AI 共同对齐语义。
- `flows.md`：业务流程、业务对象和状态机。
- `capabilities/`：可复用能力及其输入输出契约。
- `operations.md`：执行编排、异步/并发 runtime、步骤状态和诊断。
- `identity-and-digests.md`：业务 ID、内容 digest、内部 ref、下载标识的边界。
- `artifacts.md`：source artifact、derived artifact、cache artifact、bundle artifact 的分类。
- `implementation-boundary.md`：vNext 代码落点、隔离新包、旧模块依赖禁用和实施边界。
- `implementation-plan.md`：模块级执行顺序、RepositoryServer 前置位置、每阶段完成标准和实现注意事项。
- `modules.md`：目标代码模块边界。
- `contracts/comparison-bundle.md`：正式新前后端契约、operation polling、bundle/data package 边界和 upload preview bundle closure。
- `frontend-surface-simplification.md`：前后端共同简化 surface/bundle 的策略、正式 projection/read-model 和 artifact 边界。
- `contracts/ordered-diff.md`：ordered diff 正式语义、records、ordered extension、digest 和风险挂载边界。
- `contracts/`：新一版对外或跨模块 contract。
- `adr/`：关键架构决策记录。
- `notes/`：实现笔记、benchmark readiness、决策备忘录和阶段性结论。

## 当前已收口设计

- `flows.md`：upload preview、submit acceptance/finalize、history compare、archive/promote 等业务流程如何调用能力。
- `operations.md`：异步 operation、precommit warmup、finalize、history compare、retry/cancel 和 step diagnostics。
- `identity-and-digests.md`：业务 ID、内容 digest、内部 ref、cache key digest 的边界。
- `artifacts.md`：artifact 分类、L0/L1/L2/L3 持久化等级和 operation artifact closure。
- `implementation-boundary.md`：新架构实现落在 `backend/backend_vnext/`，不依赖旧业务模块。
- `implementation-plan.md`：先 core/artifacts/SQL snapshot，再 repository_server，随后 repository-backed capabilities、comparison/risk/surface/bundle 和 flows。
- `modules.md`：`backend_vnext` 第一阶段目标模块、依赖方向和 benchmark 最小拆分。
- `contracts/comparison-bundle.md`：目标 formal API 不复刻旧 DTO，按操作流程契约和 bundle/数据包契约拆分，并记录正式 upload preview bundle 与 data-surface closure 边界。
- `frontend-surface-simplification.md`：surface/bundle thin core、前端派生、Workbench adapter 和旧功能覆盖策略。
- `contracts/source-package-and-snapshot.md`：SourcePackage 到 Snapshot 的总览和拆分入口。
- `contracts/source-package.md`：SourcePackage 容器、SourceDocumentRef、SqlDumpSource 和 source digest 边界。
- `contracts/snapshot.md`：Snapshot、SnapshotSummary、SnapshotTableDescriptor 和 schema policy。
- `contracts/snapshot-table-access.md`：SnapshotTableSet、SnapshotTableReader、SnapshotTableArtifact 和 table artifact cache 边界。
- `contracts/comparison.md`：ComparisonInput、ProjectionTable、ComparisonFacts、ComparisonRecords 和 comparison core cache 边界。
- `contracts/ordered-diff.md`：有序表 diff 的 ordered facts、records、interval/move、digest 和降级边界。
- `contracts/risk.md`：RiskEvaluationInput、RiskRulesetSnapshot、RiskFacts、RiskEvaluation、RiskReport 和 annotation artifact 边界。
- `contracts/comparison-surface.md`：ComparisonSurface 的展示 contract、artifact refs、digest、ordered table 预留和验收标准。
- `contracts/table-presentation.md`：raw descriptor 到完整 preview 列展示元数据的独立契约和 digest 边界。
- `contracts/comparison-bundle.md`：ComparisonBundle、FlowEnvelope、business projection refs、bundle artifact closure 和后续 Dolt native/ordered 计划。
- `contracts/ordered-diff.md`：IEC104 ordered family、gid/no、pseudo blank、table processing mode 和 ordered risk reason code 的正式目标。
- `adr/0002-comparison-hash-sqlite-mode-selection.md`：comparison compute 的 hash / SQLite 内部模式选择、benchmark 切换准则和诊断口径。
- `capabilities/snapshot-materialization.md`：source staging、snapshot materialization、summary、table set resolution。
- `notes/snapshot-materialization-implementation-notes.md`：Snapshot Materialization 当前实现形状、兼容入口和稳定 entrypoint 说明。
- `notes/snapshot-materialization-benchmark-readiness.md`：Snapshot Materialization benchmark 数据 readiness 和 parallelism 决策备忘录。
- `notes/snapshot-materialization-decision-memo.md`：Snapshot Materialization 的 base table / fingerprint、hash 分层和历史映射收口 memo。
- `notes/registry-v1-schema-memo.md`：repository-local SQLite registry v1 的 schema 收口、单表 entry 模型和读写边界。
- `capabilities/repository-ref-materialization.md`：repository ref 到 Snapshot/Summary/TableSet 的实现边界、RepositoryRefSession、scalar encoding 和 repository table cache 关系。
- `capabilities/repository-import.md`：Dolt/repository API 边界、import provider modes、writer lease、cache handoff 和导入后校验。
- `capabilities/comparison-compute.md`：comparison compute 的实现拆分、provider 路线、projection、records artifact、cache 接入点和验收标准。
- `capabilities/business-projection.md`：业务 projection、secondary-device 身份索引、per-device/per-tab changes/risk 聚合和性能约束。
- `capabilities/project-identity-and-dataset-replacement.md`：formal upload 的逐 pair 项目身份判定、跨项目 replacement 安全预览、提交/归档二次确认和审计边界。
- `capabilities/dolt-native-provider.md`：Dolt native provider 的功能测试结论、eligibility、canonicalization、cache 边界和 benchmark 前置条件。
- `capabilities/ordered-diff-compute.md`：`ORDERED_TABLE_COMPARE` provider 的第一版实现边界、算法取舍、records artifact 和验收标准。
- `capabilities/risk-evaluation.md`：risk evaluation 的 capability 边界、第一版规则、annotation artifact、cache 预留和 ordered table 后续完善计划。
- `capabilities/surface-assembly.md`：surface assembly 的 flow-neutral 能力边界、旧实现参考边界、ref validation 和 future cache。
- `capabilities/table-presentation.md`：独立展示 ruleset、resolver、snapshot column comment 和 preview delivery 接入边界。
- `capabilities/bundle-assembly.md`：bundle assembly 的 artifact closure、ref rewrite、Workbench adapter 和多 pair 组装边界。
- `testing-fixtures.md`：vNext fixture 分层、测试隔离和 benchmark dataset 约定。
- `repository-import-benchmark-runbook.md`：repository import benchmark 的实际运行方法、外部业务数据目录约定和产物验收。
- `adr/0001-snapshot-table-and-dolt-import-boundary.md`：SnapshotTableReader 与 Dolt import 分离的架构决策。
- `adr/0003-dolt-native-provider-selection.md`：DOLT_NATIVE provider selection、history compare cache miss 边界和 comparison-side repository-backed context。

## 当前合同与执行记录

- `contracts/comparison-bundle.md`：正式 bundle/data package contract 与 upload preview bundle closure 的主锚点。
- `notes/formal-contract-migration-execution-plan.md`：正式 contract 演进和手动反馈的历史执行记录，不作为当前兼容要求。
- `notes/comparison-bundle-migration-execution-plan.md`：comparison/bundle data-surface cleanup 的历史验收记录，不作为当前兼容要求。
- `notes/comparison-bundle-oracle-audit.md`：旧 Workbench / risk / ordered 实现中的业务语义 oracle、mapping 表和手工 case。
- `notes/comparison-bundle-formal-contract-scheme.md`：正式 bundle/surface/projection/risk/Parquet records 的 contract 收口方案。
- `dolt-test/dolt-import-provider-functional-test-result-2026-06-20.md`：Dolt import provider 功能测试结果。
- `dolt-test/dolt-native-diff-functional-test-result-2026-06-21.md`：Dolt native diff 功能测试结果。

## 工作原则

1. 先梳理流程，再反推能力。
2. 业务流程表达业务模型和状态机。
3. 执行编排负责调用能力、记录步骤、处理重试和失败。
4. 能力层只暴露稳定输入输出，不绑定 upload、submit 或 history compare 场景。
5. Cache 不是业务事实；source package、snapshot、comparison、bundle 等事实对象必须有清晰归属。
6. 新设计优先减少 ID/hash/status 数量，避免一个字段同时承担业务身份、内容校验、缓存 key 和存储路径。
7. Capability 可以暴露多个稳定 entrypoint；可复用的 resolver、parser、projector、validator、canonicalizer 不应无必要地隐藏在单一 flow-facing 入口背后。

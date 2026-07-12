# ADR 0001: SnapshotTable 与 Dolt Import 边界

## 状态

Accepted

## 背景

vNext 需要同时支持直接反馈、只读比较、异步 warmup 和正式写入等不同调用者。旧实现中 SQL parse、Dolt readback/export、projection、diff、bundle 和 repository write 容易耦合，导致同步路径过重、cache 边界不清、性能诊断困难。

特别是 Dolt import 属于重负载写入能力，不应污染 `SnapshotTableReader` 这个通用表读取协议。

## 决策

1. `SnapshotTableReader` 是读协议，只提供 full-row streaming、descriptor 和 digest 校验。
2. `SnapshotTableReader` 不拼接 SQL，不管理 Dolt branch/server/commit/ref。
3. Dolt import 作为独立 `repository_import` / `dolt_snapshot_import` capability。
4. `SnapshotTableArtifact` 与 `RepositoryImportArtifact` 分离。
5. Direct-response caller 和 read-only caller 不执行 Dolt import。
6. Dolt import 放入异步 operation，例如 warmup caller 或 finalize/write caller。
7. 同 `repository_id` 内允许 table artifact cache 跨 commit/ref 复用；不同 project/repository_id 绝对隔离。
8. Schema 比较基于 compare schema facts；原始 `CREATE TABLE` 保留用于审计、诊断和 Dolt import。
9. 极端 schema 情况采用表级降级，不做复杂等价推理。

## 后果

正向：

- Snapshot/Table contract 能被 compare、summary、bundle、cache 和 import 共用。
- 直接反馈和只读流程保持轻量，不被 Dolt 写入拖慢。
- repository import provider 可以独立做 SQL replay、table import、LOAD DATA、临时 server bulk load 的 benchmark。
- cache scope 更清晰，避免跨项目错误复用。

代价：

- repository import 需要单独设计 provider selection、writer lease、import artifact 和 readback validation。
- 某些可优化路径需要通过异步 warmup 或 shadow benchmark 渐进启用。

## 验证

- Reader contract 测试不依赖 Dolt 写入。
- Repository import provider 写入后必须 readback digest 校验。
- Direct-response/read-only flow 测试不得触发 repository import。
- 同 repository 内跨 commit/ref 的 table artifact cache 可命中；跨 repository_id 不命中。

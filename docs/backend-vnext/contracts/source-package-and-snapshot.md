# SourcePackage 与 Snapshot 总览

本文保留 `SourcePackage -> Snapshot -> SnapshotSummary -> SnapshotTableSet` 的整体链路。对象细节拆分到以下正式 contract：

- `source-package.md`：`SourcePackage` 容器、`SourceDocumentRef`、`SqlDumpSource` 和 source digest 边界。
- `snapshot.md`：`Snapshot`、`SnapshotSummary`、`SnapshotTableDescriptor`、schema policy 和 snapshot digest。
- `snapshot-table-access.md`：`SnapshotTableSet`、`SnapshotTableReader`、`SnapshotTableArtifact` 和 table artifact cache 边界。

## 对象链路

```text
SourcePackage
  -> SourceDocumentRef("/sql/dbcfg.sql")
  -> SqlDumpSource
  -> Snapshot
  -> SnapshotSummary
  -> SnapshotTableSet
  -> ComparisonInput

SubmitSourcePackage
  -> SourceDocumentRef("/sql/dbcfg.sql")
  -> SqlDumpSource
  -> Snapshot
  -> SnapshotSummary
  -> SnapshotTableSet
  -> RepositoryImportPlan
  -> immutable repository ref
```

关键规则：

- `SourcePackage` 是多目录多文件压缩包容器，不包含解析后的表。
- 当前业务 SourcePackage 默认只解析唯一的 `/sql/dbcfg.sql`；通用 SQL dump materialization 可以直接消费 `SqlDumpSource`。
- SQL 解析属于 `SqlDumpSource` / snapshot materialization capability，不属于 `SourcePackage` 容器职责。
- `Snapshot` 是可比较状态身份，不包含全量 rows。
- `SnapshotSummary` 是轻量摘要；PROVISIONAL 形态不提供 row reader，FINAL 形态会被持久化到 repository commit/ref 内的隐藏系统表并由只读流程读取。
- `SnapshotTableSet` 是 L0 逻辑视图，不直接作为业务事实持久化。
- `SnapshotTableReader` 是读协议，不是 Dolt 写入器。

## 持久化与 Cache

- `SourcePackage` / `SubmitSourcePackage` 是 L1 staged durable。
- immutable repository commit/ref 是 L2 business truth。
- `SnapshotTableArtifact`、`source_snapshot_cache` 和 `snapshot_table_artifact_cache` 是 L3 recomputable cache 或 operation artifact。
- 预热类调用只能产生 `PROVISIONAL` cache candidate。
- Repository/readback 或等价权威校验通过后，cache entry 才能 promote 为 `COMMIT_VALIDATED`。

## Capability 解耦原则

- Contract 描述输入、输出和内容身份，不描述业务流程状态机。
- Capability 不根据 upload、submit、history compare 等流程名分支。
- Flow/operation 层负责把业务语义映射成 `cache_policy`、`cache_lookup_policy`、`validation_status_policy` 和 `artifact_policy`。
- 当流程状态、权限或 UI 反馈方式变化时，不应修改 capability contract；只有输入、输出、artifact、cache 或 validation 需求变化时才修改。
- 外部测试、benchmark 和新功能可以直接调用 capability；只要提供相同输入和版本上下文，就应得到相同内容结果。

## Benchmark 依赖方向

Benchmark 可以继续作为能力验证和性能观察入口，但不应长期维护独立的 SQL parse、digest、artifact 生成逻辑。

目标依赖方向：

```text
benchmarks.repository_import
  -> capabilities.snapshot_materialization
  -> contracts/source-package.md
  -> contracts/snapshot.md
  -> contracts/snapshot-table-access.md
```

正式实现应吸收 benchmark 中已验证的能力；之后 benchmark 反过来调用正式 capability，只保留 dataset、matrix、timing 和 report 逻辑。

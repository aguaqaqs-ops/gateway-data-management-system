# Storage Mutation and Change Set Contract

状态：正式设计基线（Accepted）

阶段：Phase 3 contract；P5 Submit/external integration

Contract ID：`gateway-vnext.storage-mutation-and-change-set`

Owner：Canonical Storage / Mutation Planner

## 1. Scope

本 contract 定义 canonical storage snapshot 之间的 mutation plan，以及供 Dolt 和其他
target renderer 消费的 target-neutral `ChangeSetArtifact`。它不定义前端 row comparison
records，也不把 SQL 方言写入中间 artifact。

```text
before canonical storage snapshot
  + current canonical storage projection
  -> StorageMutationPlan
  -> REBUILD_TABLE | PATCH_DML | NOOP per table
  -> target renderer
```

## 2. Policy

支持两种 policy：

- `REBUILD_ALWAYS`：每个变化表生成完整重建 mutation；
- `ADAPTIVE_PATCH`：planner 对每张表独立判断 patch eligibility，允许 mixed plan。

生产 `RepositoryImportArtifact` 路径冻结使用 `ADAPTIVE_PATCH`，planner 对每张变化表独立判断，
允许 mixed plan。通用 planner 仍保留 `REBUILD_ALWAYS` 供明确选择该策略的非生产调用方使用；它不是
Submit 的生产默认值。

## 3. Patch eligibility

首版仅允许同时满足以下条件的表使用 `PATCH_DML`：

- canonical storage key 稳定、唯一、可直接定位行；
- schema、key、storage projection 没有变化；
- table 不是 keyless、degraded 或 unsupported table；`GID_NO_V1` ordered table 可 patch，
  以 `gid` 为稳定 canonical storage key，`no` 作为普通 persisted column；
- 没有 foreign key、trigger、cascade、generated/server-default 或其他未建模外部副作用；
- target renderer 支持该表所有 logical types 与其目标所需的 apply semantics；外部目标保留
  条件 DML、affected-row 检查、事务与 readback 要求，生产 Dolt 路径按 §6 的 expected-parent CAS
  边界执行；
- `changed_row_count <= 1,000`；
- `change_ratio <= 1%`。

`change_ratio` 定义为：

```text
changed_row_count / max(before_row_count, after_row_count, 1)
```

阈值 policy 冻结为 `1,000` 行和 `1%`。INSERT replay 每条 SQL 最多包含 `256` 行；
S1a 在 t4 v2 的真实变化表上验证逐行路径与整表重建耗时并冻结这两个值。
没有 estimated patch bytes eligibility 条件。最终 renderer 产生的 `replay.sql` 仍受
`200 MiB` artifact admission 限制；超过限制直接拒绝，不拆分、不 fallback。

派生表在 materialization 后按普通 canonical table 判断，不因来源而默认 rebuild。

## 4. Counting and net diff

- 多字段更新同一行计一次 `UPDATE`；字段数量不放大计数。
- `DELETE`、`INSERT` 各计一次 physical mutation。
- canonical key 变化表达为 `DELETE + INSERT`，计两次 physical mutation。
- 同一 key 的中间变化先归并为最终 before/after；最终无变化为 `NOOP`。
- `StorageMutationPlan` 使用 canonical storage key，而非仅用于前端 comparison 的
  `effective compare key`。二者不一致的表首版自动 rebuild。

## 5. ChangeSetArtifact

artifact 为结构化数据，不保存 Dolt、PostgreSQL 或其他 SQL 文本。每个 mutation 至少包含：

```text
table_id
operation: INSERT | UPDATE | DELETE
canonical_storage_key
before_row_digest: optional
after_image: optional full persisted row
```

`UPDATE` 使用完整 persisted after-image，不只保存 changed columns；key 不作为 SET
字段。generated/server-default/无法直接写入字段使该表不满足 patch eligibility。

`manifest.json` 至少保存：

```text
source_identity
base_repository_commit/ref
target_identity
storage_projection_digest
table_ruleset_digest
threshold_policy
per_table operation/count summary
change_set_digest
artifact schema/encoding
```

logical scalar、NULL、DECIMAL、datetime、JSON、binary 等值遵守 shared canonical encoding；
renderer 负责 target-specific physical encoding，不得静默 stringify unsupported values。

## 6. Determinism and apply semantics

表按 canonical table identity 排序；表内操作按固定阶段排序：

```text
DELETE -> UPDATE -> INSERT
```

每个阶段按 canonical key 排序。所有 digest 使用 canonical encoding，不受输入顺序、
线程调度或 provider language 影响。

外部目标的 `UPDATE/DELETE` 带 canonical key 和 before-image guard，并要求 affected-row 数
精确匹配；`INSERT` 遇到已存在 key 为冲突。生产 Dolt renderer 在 Repository Service 私有 ref
上按 expected parent 构造确定性 replay，变化表 parent rows 先按 parent manifest 的行数与
`raw_content_digest` 校验；不生成 conditional DML，不做 affected-row 检查或提交后 readback。
其正确性依赖受信 Repository、expected-parent CAS 与上述 parent 行校验。各目标的 drift 与
capability failure 按其既定 full-resync/error contract 处理，不自动 merge。

## 7. Renderer boundary and lifecycle

Dolt renderer 生成 deterministic `replay.sql`。外部 renderer 生成 target-specific
parameterized command stream。renderer capability 必须参与 plan identity；effect 前
发现不支持时返回稳定的 `TARGET_CAPABILITY_UNSUPPORTED`，不得偷偷改变 plan。

artifact 在 Preview/Submit reuse、Dolt replay、可选 external ChangeSet、readback/audit
完成前保持 pinned。缺失、损坏或 digest 不匹配时，Submit 可从 durable source fallback
或要求新的 upload attempt。

## 8. Verification

必须覆盖 no-op、multi-column update、key change、mixed plan、threshold boundary、
before-image conflict、input reorder、unsupported type、replay size admission、
renderer failure、retry、crash 和 readback mismatch。前端 comparison records 不能直接
作为 mutation source。

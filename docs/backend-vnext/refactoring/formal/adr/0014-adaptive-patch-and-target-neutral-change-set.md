# ADR 0014: Adaptive Patch and Target-Neutral Change Set

状态：Accepted

日期：2026-08-18

决策 owner：Backend vNext Canonical Storage and External Sync

关联阶段：Phase 3、Phase 5B、Phase 6/7 validation

## Context

前端 comparison records 不能直接作为 repository mutation source。旧路径对任何变化表
整表重建，未来需要在小幅变化时生成 `UPDATE/INSERT/DELETE`，同时为 Dolt 和潜在外部
数据库提供不同 renderer。将 SQL 方言、comparison projection 和 storage mutation 混在
一起会使幂等、drift、digest 和跨 target 验证不可控。

## Decision

建立 target-neutral `StorageMutationPlan` 和 `ChangeSetArtifact`：

```text
canonical before/after storage projection
  -> per-table REBUILD_TABLE | PATCH_DML | NOOP
  -> Dolt renderer or external target renderer
```

首版 policy 为 `REBUILD_ALWAYS`；`ADAPTIVE_PATCH` 全局开启只启用 planner。patch eligibility
要求 canonical storage key、稳定 projection、无未建模 FK/trigger/cascade/generated side
effect、目标能力支持，并同时满足 `changed_row_count <= 1000`、`change_ratio <= 5%`。
不使用 estimated bytes eligibility；最终 `replay.sql > 200 MiB` 仍直接拒绝。

中间 artifact 只保存结构化 mutation、before digest 和完整 after-image，不保存 SQL。Dolt
使用 deterministic replay SQL，外部 target 使用自己的 parameterized command stream。
所有 mutation 使用 key guard、精确 affected-row 检查、change-set digest 和 readback。

## Alternatives

- 直接复用 frontend `ComparisonRecords`：拒绝，projection/identity/physical value ownership
  不同。
- 把 PostgreSQL SQL 直接发送给 Dolt 或反向复用：拒绝，方言、事务和 type semantics 不同。
- 只按 changed column 数量决定 patch：拒绝，不能表达 row work、key change 和 drift。
- 失败后自动在 patch/rebuild 间隐式切换：拒绝，改变 plan identity 并破坏可审计性。
- 为外部 target 引入 2PC：拒绝，Dolt 是权威，异步 target resync 更可恢复。

## Consequences

需要额外的 planner、artifact schema、renderer capability declaration、reference executor
和 fault matrix。收益是 Dolt、未来 PostgreSQL 和其他 target 可以共享 canonical mutation
语义，且 mixed patch/rebuild/no-op 在单一 commit/transaction 中保持一致。

## Required Verification

- multi-column update、key change、no-op、mixed plan 和 threshold boundary；
- input reorder、before-image guard、duplicate digest、target drift 和 readback mismatch；
- `replay.sql` capacity rejection；
- Dolt golden renderer 与 target-neutral reference executor 分离验证；
- crash、unknown outcome、retry 和 full-resync recovery。

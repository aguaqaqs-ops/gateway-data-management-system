# ADR 0017: SQL Spelling → DeclaredType Unification

状态：Accepted

日期：2026-09-25

决策 owner：Backend vNext History Compare / Storage Projection

关联阶段：P5-5E-S3 remediation round 2

## Context

S3 compose ordered compare 在 production DDL（`gid int unsigned`）下出现整表 `DEGRADED` 与
`SCALAR_TYPE_MISMATCH`：materialize 路径将 `INT UNSIGNED` 错误映射为 `SIGNED_INTEGER`，而
compare 路径保留 `UNSIGNED_INTEGER`。F1 集成测试 `move_only` / `keyed_ignored_column` 暴露同一
缺陷。独立问题：prepare 投影失败后 submit attempt 仍停留在 `PREPARED` 且占用 workspace/repository
occupancy，导致同 workspace 再提交返回 `409 SUBMIT_OCCUPANCY_CONFLICT`。

原 P5-5E 执行计划禁止改动 `capabilities/**`；上述缺陷需要受控预算扩展。

## Decision

### 1. 共享 SQL spelling → DeclaredType 映射

新增权威模块 `capabilities/snapshot_materialization/sql_declared_types.py`，经
`snapshot_materialization.contracts` 重导出供 compare/storage_projection 消费，导出
`declared_type_for_sql_spelling`。`snapshot_materialization/scalar_encoding.py` 与
`comparison/standard.py` 均委托该模块，禁止双实现漂移。

Canonical 决策（与 `table_access/_sql_types.py`、`canonicalization_cells.py` 一致）：

| SQL spelling | DeclaredType |
| --- | --- |
| `INT UNSIGNED` / `BIGINT UNSIGNED` / `TINYINT UNSIGNED` 等 | `UNSIGNED_INTEGER`（bits 按宽度表） |
| `INT` / `BIGINT` 等无 `UNSIGNED` 后缀 | `SIGNED_INTEGER` |
| `VARCHAR(n)` 及字符族 | `STRING` |
| 其他已支持标量族 | 与现有 compare/materialize 语义一致 |

不变量：同一 SQL spelling 在 materialize 与 compare 路径必须产生相同 `DeclaredType`。ordered
`gid` 保持 catalog `INT UNSIGNED`；digest/oracle 一致性检查性质不变（管线重跑，非独立参考实现）。

**参数解析 fail-closed（remediation round 3）**：mapper 对 `DECIMAL`/`BIT` 等带参族不得泄漏
`IndexError`/`ValueError`。畸形或不可解析参数统一抛 `SqlDeclaredTypeMappingError`；compare 路径
捕获后转为 `StandardComparisonError("SCALAR_TYPE_UNKNOWN")`；storage projection 对 mapper 可解析但
词表未支持的族（如 `DECIMAL(10)`、`BIGINT UNSIGNED`）返回 `UNSUPPORTED_TABLE` 诊断，不得未处理异常。
`DECIMAL` 单 precision 参数（如 `DECIMAL(10)`）语义为 `precision=10, scale=0`（与 materialize 历史
语义及 repository `normalize_sql_type` 一致）。

**`try_declared_type_for_sql_spelling` 返回 None 的三路径语义（有意差异）**：

| 消费路径 | None / 映射失败后的行为 |
| --- | --- |
| storage projection | mapper 可解析但词表外 → `UNSUPPORTED_TABLE`（fail-closed） |
| materialize (`_declared_type_for`) | 畸形拼写 → unknown `STRING`（`unknown=True` 软降级） |
| compare (`_declared_type`) | `SqlDeclaredTypeMappingError` → `StandardComparisonError` → 表 `DEGRADED` |

守卫 owner：`tests/test_sql_declared_type_mapping.py`、`tests/test_storage_projection_integrity.py`。

### 2. Storage projection BIGINT 修正

`storage_projection/project.py` 将 `BIGINT` 映射为 64-bit `SIGNED_INTEGER`，不得降为 32-bit `INT`。

### 3. Prepare 失败占用释放

prepare 投影公布失败时，在同一 control 事务内将 attempt `PREPARED → ABORTED`，释放
workspace/repository occupancy 与 checkpoint protection，再标记 operation/step `FAILED`。不复用
要求 `EFFECT_PENDING` 的 operator `abort_submit_in_control_transaction` 路径。

### 4. S3 预算扩展（引用 [p5-5e-history-compare-execution-plan.md:171](../plans/p5-5e-history-compare-execution-plan.md) 原禁止项；执行计划互指本 ADR）

本轮授权改动：

- `capabilities/snapshot_materialization/contracts.py`（显式重导出 mapper 公开面）
- `capabilities/snapshot_materialization/scalar_encoding.py`（映射对齐）
- `capabilities/comparison/standard.py`（映射对齐，无行为扩展）
- `capabilities/snapshot_materialization/sql_declared_types.py`（新增共享 mapper）
- `capabilities/storage_projection/project.py`（BIGINT bits 修正）
- `application/submit_jobs.py` + `application/submission/abort_transaction.py`（PREPARED 释放）
- `application/submission/errors.py`（`SubmitImportPublicationError` 清洁切出，T5）
- `repository_import_artifact.py`（projection 失败 diagnostic 格式化）

## Test owners

| 行为 | Owner |
| --- | --- |
| 跨模块映射守卫 | `tests/test_sql_declared_type_mapping.py` |
| F1 ordered 语义 | `tests/test_history_compare_jobs.py` |
| Compose ordered 语义 | `tests/test_ordered_compare_compose.py` |
| Prepare 占用释放 | `tests/test_submit_job_prepare.py` + bisect compose B′ 扩展 |

## Rollback

守卫测试或 F1/compose 语义断言失败 → revert mapper + projection bits 改动。occupancy 释放可独立
revert 若仅 T4 回归。

## Required Verification

- `pytest -m unit` 0 failed / 0 skipped（含 F1 `move_only` / `keyed_ignored_column`）
- compose 串行：`test_ordered_compare_compose.py`、`test_ordered_submit_bisect_compose.py`、
  `test_history_compose_e2e.py`
- B′ 后同 workspace 再 submit 非 409，occupancy 已释放

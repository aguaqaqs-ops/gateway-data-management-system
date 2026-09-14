# P5-5B-S2 Control DB Schema, Repositories and T1/T3 UoW Handoff

状态：**S2 implementation complete — focused gate passed**

日期：2026-09-14

Owner：P5-5B Delivery

## Scope delivered

- Workspace schema **v3**（5 张 submit 表 + 双 occupancy projection）
- `SQLiteSubmissionRepository`（读写端口 + T1/T3/Abort 写方法）
- `ControlDbUnitOfWork.submission` 与 `list_artifact_protection_for_owner`
- T1 `accept_submit_transaction`、T3 `finalize_submit_transaction`、stable `abort_submit_transaction`
- 权威单元测试（migration / repository / transaction matrix）

## Deferred（S2 边界外）

- HTTP routes / OpenAPI（S4）
- Import builder / artifact package bytes（S3）
- 真实 Repository Client upload/import、worker handler（S5）
- `sqlite_protection.py`、contract packages、lockfile 变更

## Schema v3 migration

| 表 | 关键约束 |
| --- | --- |
| `submit_attempt_records` | PK `submit_attempt_id`；四态 CHECK；`optimistic_version`；FK workspace + operation |
| `submit_idempotency_records` | PK `(workspace_id, idempotency_key)`；UNIQUE `submit_attempt_id` |
| `submission_records` | PK `submission_id`；UNIQUE `submit_attempt_id` |
| `workspace_submit_occupancy_records` | PK `workspace_id`；XOR：attempt/submission 恰一非空 |
| `repository_submit_occupancy_records` | PK `repository_id`；UNIQUE `workspace_id` + `submit_attempt_id` |

- `WORKSPACE_SCHEMA_VERSION = 3`
- `_apply_workspace_v3` 前执行 `PRAGMA integrity_check` / `foreign_key_check` fail-closed 审计
- v2 历史库 reopen → v3；newer ledger 版本 → `UnsupportedSchemaVersion`
- synthetic failure rollback 探针保留

**Test owner**：[`test_submit_control_db_migrations.py`](vnext/backend/tests/test_submit_control_db_migrations.py)（§4 唯一 owner）

## Transaction matrix

| 场景 | 入口 | 断言要点 |
| --- | --- | --- |
| T1 persist | `accept_submit_transaction` | Attempt PREPARED + idempotency + Operation/Step + occupancy + protection 转移 |
| T1 all-or-nothing | monkeypatch 中途写失败 | 无 attempt/idempotency/operation/occupancy 残留 |
| T1 replay | 同 key 第二次 | same `submit_attempt_id`，`replay=True` |
| T1 idempotency conflict | same key + different fingerprint | `IdempotencyConflict` |
| Concurrent occupancy | 两 workspace 争同一 `repository_id` | unique 决定 winner；loser `SubmitOccupancyConflict` |
| T3 exactly-one | `finalize_submit_transaction` | submission 唯一；replay 不 second insert |
| T3 occupancy switch | finalize 后 | `active_submission_id` 设置；repository occupancy 删除 |
| Stable abort | `abort_submit_transaction` | ABORTED + occupancy 释放 + 无 submission |
| CAS 防线 | workspace/attempt version 过期 | 冲突，无部分提交 |

**Test owner**：[`test_submit_transactions.py`](vnext/backend/tests/test_submit_transactions.py)（§4 唯一 owner：T1/T3/abort/并发）

## 并发线性化

- Idempotency：`submit_idempotency_records` UNIQUE `(workspace_id, idempotency_key)` + UNIQUE `submit_attempt_id`
- Repository occupancy：`repository_submit_occupancy_records` UNIQUE `repository_id`
- Attempt / workspace：`optimistic_version` CAS（`cas_update_attempt` / `save_workspace`）
- Operation runtime：先 terminalize active step，再 terminalize operation（P4 状态机约束）

## Focused gate（2026-09-14）

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py \
  tests/test_submit_transactions.py \
  tests/test_sqlite_workspace_repository.py \
  tests/test_workspace_control_db_migrations.py
# 27 passed

uv run ruff check src/gateway_backend/infrastructure/control_db \
  src/gateway_backend/application/submission \
  tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py tests/test_submit_transactions.py
# clean

uv run mypy
# clean
```

## Test owner 治理（S2）

| 文件 | 角色 |
| --- | --- |
| [`test_submit_control_db_migrations.py`](vnext/backend/tests/test_submit_control_db_migrations.py) | v3 DDL/FK/index、rollback、reopen、newer-version fail-closed |
| [`test_sqlite_submit_repository.py`](vnext/backend/tests/test_sqlite_submit_repository.py) | row mapping、occupancy/CAS/idempotency roundtrip |
| [`test_submit_transactions.py`](vnext/backend/tests/test_submit_transactions.py) | T1/T3/abort 单 SQLite 事务矩阵与并发 winner |
| [`test_workspace_control_db_migrations.py`](vnext/backend/tests/test_workspace_control_db_migrations.py) | v3 bootstrap 不破坏既有 workspace migration 回归 |
| [`test_sqlite_workspace_repository.py`](vnext/backend/tests/test_sqlite_workspace_repository.py) | v3 bootstrap 不破坏 upload/workspace CAS |

## S1 纯逻辑复用

- `validate_accept_submit`（T1 事务内外）
- `finalize_submit`（T3 闭包 + replay 校验）
- `validate_abort_proof`（stable abort 事务外）
- `transition_attempt_state`：finalize/abort 通过 `**changes` 原子设置终态字段（避免中间态 invariant 违反）

## 下一跳（S3+）

1. Import builder / artifact package bytes
2. Worker handler + 真实 Repository effect（S5）
3. HTTP routes / OpenAPI（S4）

# P5-5B-S2 Control DB Schema, Repositories and T1/T3 UoW Handoff

状态：**S2 round-2 remediation complete — independent re-review required**

日期：2026-09-15

Owner：P5-5B Delivery

## Authority gate snapshot

```yaml
p4_r6_exit: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
p5b_real_repository_effect_authorized: yes
unresolved_contract_drift: pending_D1_design_owner_errata
first_authorized_step: P5-5B-S1
implementation_authority_unchanged: true
```

## Traceability

```yaml
stage: P5-5B-S2-control-db-t1-t3
parent_head: c561ffe97bb968b9bb9852fa0bdd4492b9b94c28
candidate_head: pending_round2_review_follow_up_commit
input_authority:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-independent-review-findings.md
scope_paths:
  - vnext/backend/src/gateway_backend/infrastructure/control_db/**
  - vnext/backend/src/gateway_backend/application/submission/**
  - vnext/backend/src/gateway_backend/domain/submission/**
  - vnext/backend/tests/test_submit_control_db_migrations.py
  - vnext/backend/tests/test_sqlite_submit_repository.py
  - vnext/backend/tests/test_submit_transactions.py
  - vnext/backend/tests/test_sqlite_workspace_repository.py
  - vnext/backend/tests/test_workspace_control_db_migrations.py
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-*.md
changed_paths:
  - vnext/backend/src/gateway_backend/domain/submission/__init__.py
  - vnext/backend/src/gateway_backend/domain/submission/errors.py
  - vnext/backend/src/gateway_backend/domain/submission/models.py
  - vnext/backend/src/gateway_backend/application/submission/__init__.py
  - vnext/backend/src/gateway_backend/application/submission/abort_transaction.py
  - vnext/backend/src/gateway_backend/application/submission/accept.py
  - vnext/backend/src/gateway_backend/application/submission/accept_transaction.py
  - vnext/backend/src/gateway_backend/application/submission/contracts.py
  - vnext/backend/src/gateway_backend/application/submission/errors.py
  - vnext/backend/src/gateway_backend/application/submission/finalize_transaction.py
  - vnext/backend/src/gateway_backend/application/submission/ports.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py
  - vnext/backend/tests/test_architecture.py
  - vnext/backend/tests/test_sqlite_submit_repository.py
  - vnext/backend/tests/test_submit_control_db_migrations.py
  - vnext/backend/tests/test_submit_domain.py
  - vnext/backend/tests/test_submit_transactions.py
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s1-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-remediation-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-round2-remediation-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-round2-remediation-brief.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-independent-review-findings.md
plan_alignment_s1_paths:
  note: S2-F3 architecture-guard alignment only; not a silent S1 scope expansion
  - vnext/backend/tests/test_architecture.py
  - vnext/backend/src/gateway_backend/application/submission/contracts.py
  - vnext/backend/src/gateway_backend/application/submission/errors.py
  - vnext/backend/src/gateway_backend/domain/submission/models.py
  - vnext/backend/src/gateway_backend/domain/submission/errors.py
  - vnext/backend/tests/test_submit_domain.py
invariants_delivered:
  - Workspace schema v3 Attempt/Submission/idempotency/two occupancy relations
  - T1 preflight control-DB reads inside read-only SQLite txn; baseline/main ports outside any SQLite txn
  - T3/abort lease + caller-observed version fencing (token identity + expected optimistic versions)
  - Occupancy release is owner-qualified CAS
  - T3 replay requires matching Attempt/Submission/Workspace/Operation/await-step closure
  - Abort after P4 terminalize is idempotent and does not rewrite terminal steps
  - Business abort accepts EFFECT_PENDING only (PREPARED rejected at state gate)
  - Submit job registry requires all three steps before Accept writes
unique_test_owners:
  - tests/test_submit_control_db_migrations.py
  - tests/test_sqlite_submit_repository.py
  - tests/test_submit_transactions.py
  - tests/test_architecture.py  # S2-F3 allowlist alignment only
focused_commands_and_results:
  - cd vnext/backend && uv run pytest -q -m unit tests/test_architecture.py tests/test_submit_domain.py tests/test_submit_application.py tests/test_submit_idempotency.py tests/test_submit_control_db_migrations.py tests/test_sqlite_submit_repository.py tests/test_submit_transactions.py tests/test_sqlite_workspace_repository.py tests/test_workspace_control_db_migrations.py => 156 passed
  - cd vnext/backend && uv run pytest -q -m unit => 1880 passed / 0 failed
  - cd vnext/backend && uv run ruff check . && uv run mypy => pass (332 files)
five_package_static: deferred
authoritative_runner: deferred
container_rebuild_required: no
container_reason: S2 is control DB/application/domain submission only; no image, Compose, entrypoint, UID/GID, volume, or production ENV change
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
uv_lock_in_diff: no
uv_lock_sha256: 21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea
findings:
  - S2-F1..F13 addressed in p5-5b-s2-remediation-handoff.md
  - S2-F14..F18 addressed in p5-5b-s2-round2-remediation-handoff.md
deferred:
  - HTTP routes / OpenAPI (S4)
  - Import builder / artifact package bytes (S3)
  - Real Repository Client upload/import and worker handlers (S5)
  - Independent S1/S2 closure countersign
reopen_required: []
implementation_authority_unchanged: true
next_step: independent_review_of_S2_round2_review_follow_up
process_track_open:
  - candidate_head SHA binding after review follow-up commit
  - S1 independent countersign
```

## Transaction matrix

| 场景 | 实际行为 | 断言要点 |
| --- | --- | --- |
| T1 persist | `accept_submit_transaction` | Attempt PREPARED + idempotency + Operation/Step + occupancy + protection 转移 |
| T1 all-or-nothing | monkeypatch 中途写失败 | 无 attempt / idempotency / Operation+Step / occupancy / submit-attempt protection；workspace version 不变 |
| T1 replay | 同 key 第二次 | `replay=True`；不调用 baseline digest / main resolve |
| T1 I/O boundary | recording ports | digest/main 各 1 次且 writer transaction 未打开 |
| T1 NO_CANONICAL_CHANGE | baseline digest 等于 preview canonical | `main_resolve.calls == 0`；全程无写锁；零写入 |
| T1 registry | 仅 prepare 注册 | Accept 拒绝且零写入 |
| T1 workspace version | T1 前 bump version | `WorkspaceVersionConflict` + 零写入 |
| T1 occupancy serialization | 两 workspace 顺序争同一 `repository_id` | SQLite 单写者串行化；loser `SubmitOccupancyConflict`（不是线程并发） |
| T3 exactly-one | finalize + replay | submission 唯一；完整 closure 才 ACK |
| T3 incomplete replay | 逐组件破坏 occupancy / await Step / Operation | `FINALIZE_RECOVERY_REQUIRED`，不得 ACK |
| T3/abort lease | takeover 后旧 identity | `StaleWrite`；当前 holder 成功 |
| T3/abort version | caller 旧 step/attempt version（token 可不变） | `StaleWrite` / `SubmitAttemptVersionConflict`；零终态写 |
| Stable abort | EFFECT_PENDING + RUNNING await | ABORTED + occupancy 释放 + 无 submission；`validate_abort_proof` 在写事务外 |
| Abort after P4 terminalize | await 已 FAILED | business abort 成功；二次 replay=True |
| PREPARED business abort | T1 后 PREPARED | 状态门拒绝；occupancy 保留 |
| Occupancy owner CAS | mismatched attempt id | `SubmitOccupancyConflict` + 行不变 |

**Test owner**：[`test_submit_transactions.py`](../../../../../vnext/backend/tests/test_submit_transactions.py)

## S1 纯逻辑复用

- `validate_accept_submit`（S1 内存路径；仍按原顺序在 `NoCanonicalChange` / closure 之后才 `main_resolve`）
- `load_new_accept_preflight_facts` + `evaluate_new_accept_preflight`（T1 §6.1 steps 3-5；baseline I/O 在 SQLite 读事务外）
- `validate_accept_submit_with_frozen`（T1 写锁内，不再调用任何 I/O port）
- `validate_abort_proof`（stable abort **写事务外**）
- `finalize_submit`（Attempt↔Submission binding；T3 replay 另验 occupancy/Operation/Step closure）

## 下一跳

独立评审按 [p5-5b-s2-independent-review-findings.md](p5-5b-s2-independent-review-findings.md) §4 复核。S3 不以本卷 delivery 自证为 entry。

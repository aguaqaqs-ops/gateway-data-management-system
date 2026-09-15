# P5-5B-S2 Round-2 Finding-Scoped Remediation Handoff

状态：**round-2 remediation complete — S2 closure pass**

日期：2026-09-15

Owner：P5-5B Delivery（实现侧；不签署独立 closure）

Finding 输入：[p5-5b-s2-round2-remediation-brief.md](p5-5b-s2-round2-remediation-brief.md)

评审对象 parent HEAD：`c561ffe97bb968b9bb9852fa0bdd4492b9b94c28`

## Authority gate snapshot

```yaml
p4_r6_exit: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
p5b_real_repository_effect_authorized: yes
unresolved_contract_drift: none
first_authorized_step: P5-5B-S1
implementation_authority_unchanged: true
```

## Implementation traceability

```yaml
stage: P5-5B-S2-round2-remediation
parent_head: c561ffe97bb968b9bb9852fa0bdd4492b9b94c28
round2_initial_commit: bebf2fad64430c5da05333f863f56e08e959414f
candidate_head: 2da4d71f3c8090cfac08390cfe5f3fb79fd305f4
independent_review: docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-final-independent-review.md
uv_lock_sha256: 21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea
uv_lock_in_diff: no
container_rebuild_required: yes
container_reason: final candidate `2da4d71f` includes uv-lock guard wiring on native/build/run-tests entrypoints
last_verified_image_revision: gateway-repository-service:local sha256:b44a67a7fe6260293ce80ad5e94ee3ba8d65a6c9d16494255c9585807a837a44
container_gate_for_current_head: pass
```

## Finding → fix → owner → retest

| Finding | 修复摘要 | Test owner | Retest |
| --- | --- | --- | --- |
| **S2-F14** | `FinalizeSubmitTransactionRequest` 必填 `expected_*_version`；`AbortSubmitTransactionRequest` 可选同名字段；新鲜 finalize/abort CAS 使用 caller 观察 version | `test_submit_transactions.py` | stale step+取消、stale attempt、abort stale step → 拒绝零终态写；lease takeover 回归绿 |
| **S2-F15** | `load_new_accept_preflight_facts` + `evaluate_new_accept_preflight`；`NO_CANONICAL_CHANGE` 在写锁前裁决；`main_resolve` 仅在 no-op 排除后 | `test_submit_transactions.py` | `main_resolve.calls==0` + 全程无写锁 + 零写入；happy path I/O boundary 回归绿 |
| **S2-F16** | abort 状态门收窄 EFFECT_PENDING-only；删合成 PREPARED abort 测试；handoff matrix 删 PREPARED abort 行 | `test_submit_transactions.py` | PREPARED → 状态门拒绝；EFFECT_PENDING abort 矩阵回归绿 |
| **S2-F17** | 选项 B：单写者下事务内 `save_workspace` CAS 失败不可达论证；可达路径由 `test_t1_rejects_stale_workspace_version_without_writes` 覆盖 | docs | 不新增注入测试 |
| **S2-F18** | `candidate_head`/`changed_paths` 更新；本卷落盘；S1 countersign 证据准备（不自签） | docs | binding + changed_paths + 本卷 |

## Design clarifications（上报，非实现侧闭合）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| **D-1** | implementation delivered — independent review required | T1 同连接 projection freshness 已交付；见 [D-1 执行计划](p5-5b-s2-d1-projection-freshness-execution-plan.md) 与 [D-1 handoff](p5-5b-s2-d1-projection-freshness-handoff.md)；`unresolved_contract_drift: none` |
| **D-2** | reported | QUEUED/prepare-PENDING 取消无 occupancy 释放口；S2 未实现任何释放行为 |

## Round-2 复审 follow-up（bebf2fad 之后）

| 项 | 修复摘要 | Test owner | Retest |
| --- | --- | --- | --- |
| **P1** | baseline I/O 移出 SQLite 读事务：`load_new_accept_preflight_facts` 仅 control-DB 读；`baseline_digest` 在读事务关闭后调用 | `test_submit_transactions.py` | `digest.writer_open_during_calls==(False,)` |
| **P2** | `WriterLockTracker` 增 `writer_entries`/`factory_calls`；no-op 断言从未请求 `read_only=False` | `test_submit_transactions.py` | `writer_entries==0` + `factory_calls==(True,)` |
| **F18** | `p5-5b-s2-handoff.md` authority/changed_paths 与 round-2 handoff 对齐 | docs | `unresolved_contract_drift` 一致；brief 列入 changed_paths |

## Round-2 复审 follow-up 第二轮（b87efe8a 之后）

| 项 | 修复摘要 | Test owner | Retest |
| --- | --- | --- | --- |
| **P2-1** | 纯本地 preflight（version/binding/stale/occupancy/closure）置于 `baseline_digest` 之前；`NO_CANONICAL_CHANGE` 仍在其后 | `test_submit_transactions.py` | stale version + 不可用 baseline → `WorkspaceVersionConflict` 且 `baseline_calls==0` |
| **P2-2** | `WriterLockTracker.active_uow_entries` + port `uow_active_during_calls`；证明外部 port 调用时零活跃 UoW（含 read-only） | `test_submit_transactions.py` | no-op/happy path `uow_active_during_calls==(False,)` |

## Round-2 复审 follow-up 第三轮（de7ad788 之后）

| 项 | 修复摘要 | Test owner | Retest |
| --- | --- | --- | --- |
| **P2-3** | occupancy/closure 移回 `NO_CANONICAL_CHANGE` 之后；新增 `assert_accept_preflight_post_noop_guards`；§6.1 顺序 = binding/stale → baseline → NO_CANONICAL_CHANGE → occupancy/closure → main_resolve | `test_submit_transactions.py` | no-op + repository occupancy / 空 closure digest → `NoCanonicalChange`（非 occupancy/closure 冲突）且 `baseline_calls==1` |

初版 Round-2 交付 commit：`bebf2fad64430c5da05333f863f56e08e959414f`（parent `c561ffe9`）。复审 follow-up 第一轮：`b87efe8a115bb5ca91a495968620037d65567ac1`。第二轮：`de7ad788fa25c127e43fe5031ba49e34736fcdcb`。第三轮 review tip 见本卷 `candidate_head`。

## S2-F17 闭合记录（选项 B）

BEGIN IMMEDIATE 单写者下，T1 写事务持有期间 workspace 行不可被其他写者推进，故事务内 `save_workspace` CAS 失败路径不可达；仅 monkeypatch 可触达，属防御性覆盖。round-1 F11 所指可达契约（caller 观察 workspace version 失配、零写入）由 `test_t1_rejects_stale_workspace_version_without_writes` 覆盖。

## S1 countersign 证据（F18.2 — 待独立评审签署）

实现侧记录、不自签 `p5-5b-s1-handoff.md` closure。

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_submit_domain.py \
  tests/test_submit_application.py \
  tests/test_submit_idempotency.py \
  tests/test_architecture.py
# 102 passed (round-1 记录交叉引用)

uv run pytest -q -m unit \
  tests/test_architecture.py \
  tests/test_submit_domain.py \
  tests/test_submit_application.py \
  tests/test_submit_idempotency.py \
  tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py \
  tests/test_submit_transactions.py \
  tests/test_sqlite_workspace_repository.py \
  tests/test_workspace_control_db_migrations.py
# 158 passed (round-2 亲跑，含 P2-3 no-op 优先级回归)

uv run pytest -q -m unit
# 1882 passed / 0 failed

uv run ruff check . && uv run mypy
# ruff clean; mypy Success (332 source files)
```

## Verification record（review tip `f9414aa4`）

```bash
cd /home/dev/gateway-data-management-system
git diff -- vnext/backend/uv.lock | wc -l
# 0

cd vnext/backend
uv run pytest -q -m unit \
  tests/test_architecture.py \
  tests/test_submit_domain.py \
  tests/test_submit_application.py \
  tests/test_submit_idempotency.py \
  tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py \
  tests/test_submit_transactions.py \
  tests/test_sqlite_workspace_repository.py \
  tests/test_workspace_control_db_migrations.py
# 158 passed

uv run pytest -q -m unit
# 1882 passed / 115 deselected / 0 failed

uv run ruff check . && uv run mypy
# ruff clean; mypy Success (332 source files)
```

锁 diff 为空声明：`git diff -- vnext/backend/uv.lock` 在验证后确认为 0 行（`uv run` 后 `git checkout -- vnext/backend/uv.lock` 恢复）。

## Final verification record (`2da4d71f`)

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run --offline pytest -q -m unit
# 1894 passed, 115 deselected, 0 failed

./vnext/scripts/run-tests.sh
# pass（serial 批次首次因并行 unit 遗留 dolt 子进程失败 2 项；清理后同 SHA 重跑全绿）

git diff -- vnext/*/uv.lock | wc -l
# 0
```

Focused/static/identity：见 [p5-5b-s2-final-independent-review.md](p5-5b-s2-final-independent-review.md)（`verified_at: 2da4d71f`）。

## Next step

S2 closure pass；见 [p5-5b-s2-final-independent-review.md](p5-5b-s2-final-independent-review.md)。下一授权步骤：**P5-5B-S3** entry。

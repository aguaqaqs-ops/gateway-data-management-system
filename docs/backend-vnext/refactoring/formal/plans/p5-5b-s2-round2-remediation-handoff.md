# P5-5B-S2 Round-2 Finding-Scoped Remediation Handoff

状态：**round-2 remediation complete — independent re-review required**

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
unresolved_contract_drift: pending_D1_design_owner_errata
first_authorized_step: P5-5B-S1
implementation_authority_unchanged: true
```

## Implementation traceability

```yaml
stage: P5-5B-S2-round2-remediation
parent_head: c561ffe97bb968b9bb9852fa0bdd4492b9b94c28
round2_initial_commit: bebf2fad64430c5da05333f863f56e08e959414f
candidate_head: b87efe8a115bb5ca91a495968620037d65567ac1
uv_lock_sha256: 21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea
uv_lock_in_diff: no
container_rebuild_required: no
container_reason: round-2 remediation is control DB/application submission only; no Dockerfile, Compose, entrypoint, image, UID/GID, volume, or runtime ENV change
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
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
| **D-1** | pending design owner errata | §6.1/§6.3 mapping/BaselineHead 互斥；S2 pass 门禁项；候选勘误见 brief §8.2 |
| **D-2** | reported | QUEUED/prepare-PENDING 取消无 occupancy 释放口；S2 未实现任何释放行为 |

## Round-2 复审 follow-up（bebf2fad 之后）

| 项 | 修复摘要 | Test owner | Retest |
| --- | --- | --- | --- |
| **P1** | baseline I/O 移出 SQLite 读事务：`load_new_accept_preflight_facts` 仅 control-DB 读；`baseline_digest` 在读事务关闭后调用 | `test_submit_transactions.py` | `digest.writer_open_during_calls==(False,)` |
| **P2** | `WriterLockTracker` 增 `writer_entries`/`factory_calls`；no-op 断言从未请求 `read_only=False` | `test_submit_transactions.py` | `writer_entries==0` + `factory_calls==(True,)` |
| **F18** | `p5-5b-s2-handoff.md` authority/changed_paths 与 round-2 handoff 对齐 | docs | `unresolved_contract_drift` 一致；brief 列入 changed_paths |

初版 Round-2 交付 commit：`bebf2fad`（parent `c561ffe9`）。复审 follow-up 形成 review tip commit 后更新 `candidate_head`。

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
# 156 passed (round-2 亲跑)

uv run pytest -q -m unit
# 1880 passed / 0 failed

uv run ruff check . && uv run mypy
# ruff clean; mypy Success (332 source files)
```

## Verification record

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
# 156 passed

uv run pytest -q -m unit
# 1880 passed / 115 deselected / 0 failed

uv run ruff check . && uv run mypy
# ruff clean; mypy Success (332 source files)
```

锁 diff 为空声明：`git diff -- vnext/backend/uv.lock` 在验证后确认为 0 行。

## Next step

独立评审按 brief §6 + §7 + 本卷「复审 follow-up」复核：代码轨 F14–F18 + P1/P2 + gate 全绿；设计轨 D-1 勘误落地；过程轨 `candidate_head` 绑定 review follow-up 全 SHA + S1 countersign 落盘（实现侧不自签）。

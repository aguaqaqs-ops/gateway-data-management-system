# P5-5B-S2 Finding-Scoped Remediation Handoff

状态：**round-1 closure complete — independent re-review required**

日期：2026-09-14

Owner：P5-5B Delivery（实现侧；不签署独立 closure）

Finding 输入：[p5-5b-s2-independent-review-findings.md](p5-5b-s2-independent-review-findings.md)

评审对象 parent HEAD：`3d39fdcf884ff71899664154f4ef9c6e19fa6147`

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
stage: P5-5B-S2-remediation
parent_head: 3d39fdcf884ff71899664154f4ef9c6e19fa6147
candidate_head: uncommitted_working_tree_on_c561ffe9
uv_lock_sha256: 21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea
uv_lock_in_diff: no
container_rebuild_required: no
container_reason: S2 remediation is control DB/application/domain submission only; no Dockerfile, Compose, entrypoint, image, UID/GID, volume, or runtime ENV change
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
```

## S1 focused gate re-run（S2-F1）

本卷记录 S1 focused 复跑，不伪造独立评审 PASS。独立 closure 仍由不同 conversation 签署。

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_submit_domain.py \
  tests/test_submit_application.py \
  tests/test_submit_idempotency.py \
  tests/test_architecture.py
# 102 passed

uv run ruff check . && uv run mypy
# ruff clean; mypy Success (332 source files)
```

S1 `next_step` 更新为本卷已记录 focused 复跑，待独立复核签署。

## S2-F3 plan 对齐（S1 属路径最小例外）

S2 已授模块边界 `application/submission/**` + `control_db/**` 的固有结果：基础设施不能依赖 application VO/异常。本轮最小守护对齐触碰：

- `vnext/backend/src/gateway_backend/domain/submission/{models,errors,__init__}.py`
- `vnext/backend/src/gateway_backend/application/submission/{contracts,errors}.py`（domain 再导出）
- `vnext/backend/tests/test_architecture.py`（control_db allowlist 增加 `domain.submission`）
- `vnext/backend/tests/test_submit_domain.py`（occupancy VO 改从 domain 导入）

application 禁止 import infrastructure 的规则未改。

## Finding → fix → owner → retest

| Finding | 修复摘要 | Test owner | Retest |
| --- | --- | --- | --- |
| **S2-F1** | 本卷记录 S1 focused 102 passed；S1 handoff `next_step` 改为待独立签署 | docs | S1 focused 复跑 |
| **S2-F2** | `git checkout -- vnext/backend/uv.lock`；`uv run` 会按机器 index 再污染，交付 diff 必须为空。canonical sha256 `21c8da4f…` | docs | `git diff -- vnext/backend/uv.lock` 为空 |
| **S2-F3** | occupancy/acceptance VO 与 CAS 异常迁 domain；orchestrator 改注 `SubmitControlTransaction`；control_db 只 import domain.submission | `test_architecture.py` | 全包 unit 0 failed |
| **S2-F4** | T1：read_only replay → 事务外 digest/main resolve → 短写锁只用 frozen facts。Abort：read_only 取 attempt → 事务外 `validate_abort_proof` → 短写锁 | `test_submit_transactions.py` | port 回调时 writer txn 未打开；replay 不调 Repository 端口 |
| **S2-F5** | T3/abort request 携带调用方 `worker_id`/`lease_token`；`WritePrecondition` 不再抄行上 token | `test_submit_transactions.py` | takeover 后旧 identity → `StaleWrite`；当前 holder 成功 |
| **S2-F6** | 终态 step/operation 跳过 CAS；无 active step 不再回退到 FAILED await | `test_submit_transactions.py` | P4 已 FAILED await 后 abort 成功 + replay；半收口 operation 仍 RUNNING 可收口 |
| **S2-F7** | occupancy DELETE owner-qualified + rowcount CAS | `test_sqlite_submit_repository.py`, `test_submit_transactions.py` | mismatched owner 不可删；行不变 |
| **S2-F8** | T3 replay `_assert_finalized_closure`；半破坏 → `FINALIZE_RECOVERY_REQUIRED` | `test_submit_transactions.py` | occupancy / await Step / Operation 逐组件 fail closed |
| **S2-F9** | registry 校验 prepare/submit/await 三步 | `test_submit_transactions.py` | 仅 prepare → Accept 拒绝且零写入 |
| **S2-F10** | 损坏 v2 FK → v3 拒绝、ledger 停 v2 | `test_submit_control_db_migrations.py` | `test_corrupted_workspace_v2_foreign_keys_reject_v3_upgrade` |
| **S2-F11** | T1 rollback 全 participant；workspace 版本过期回滚；PREPARED abort 项以 S2-F16 收窄替代闭合 | `test_submit_transactions.py` | 见 round-2 矩阵 |
| **S2-F12** | JSON decoder exact keys + exact primitive types | `test_sqlite_submit_repository.py` | `MALFORMED_JSON_SHAPES` |
| **S2-F13** | 重写 `p5-5b-s2-handoff.md` | docs | 本文件 + S2 handoff |

## Lockfile 环境现象（S2-F2）

`uv run pytest` / `uv run ruff` 在本开发机上会把 `vnext/backend/uv.lock` 改写成 LAN mirror（`http://192.168.233.184:3141/root/pypi/simple`），丢 `size`/`upload-time`。这是机器级 index 隔离未覆盖 `uv run` 写锁的环境问题，不是交付内容。每轮验证后必须 `git checkout -- vnext/backend/uv.lock`。权威测试入口应使用 `uv run --locked` 并隔离 index。

## Verification record

```bash
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
# 152 passed

uv run pytest -q -m unit
# 1876 passed / 115 deselected / 0 failed

uv run ruff check . && uv run mypy
# ruff clean; mypy Success (332 source files)
```

## Next step

Independent reviewer 按 findings §4 gate + 9 组新测试 + 逐 finding 证据复核，输出 S2 closure 签署或下一轮 findings。S3 entry 以本卷全部 finding 闭合 + S1 独立 closure 签署为准。

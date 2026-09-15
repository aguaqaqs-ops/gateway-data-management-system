# P5-5B-S2 D-1 Projection Freshness Handoff

状态：**implementation delivered — independent review required**

日期：2026-09-15

Owner：P5-5B Delivery（实现侧；不签署独立 closure）

输入：[D-1 Execution Plan](p5-5b-s2-d1-projection-freshness-execution-plan.md)、
[Round-2 Remediation Handoff](p5-5b-s2-round2-remediation-handoff.md)

文档基线 parent：`c0d607bc49b245dacc49f8c210cd069e12d39b43`

代码候选：工作区未提交（实现侧交付；独立评审绑定 review tip 全 SHA）

## Authority gate snapshot

```yaml
decision_direction: same_uow_projection_freshness
user_direction_confirmation: confirmed_in_conversation_2026_09_15
design_owner: Backend vNext Architecture
design_owner_signature_or_decision_reference: d1_t1_implementation_plan_2026_09_15
owning_design_commit: pending_at_review_tip
allowed_paths_amendment_commit: pending_at_review_tip
implementation_authorization_reference: d1_t1_implementation_plan_2026_09_15
independent_design_review: pending
unresolved_contract_drift: none
```

## 交付摘要

| 项 | 状态 |
| --- | --- |
| Owning design §6.1/§6.3/§13.1 勘误落盘 | done |
| Brief §4 撤回旧依据、§8.2 superseded | done |
| S2 allowed paths 追加 `sqlite_mapping.py` | done |
| `SubmitControlTransaction.resolve_provisioned_scope` | done |
| T1 replay 前同连接 fresh mapping 授权 | done |
| T1 新 key 完整 Head node/commit/version equality | done |
| 移除 read-only UoW 提前 replay 返回 | done |
| 参数表测试（新 key 漂移 + winner/replay） | done |
| 独立 closure / S2 pass | **not signed**（实现侧不自签） |

## changed_paths（D-1 卷）

- `vnext/backend/src/gateway_backend/application/submission/accept.py`
- `vnext/backend/src/gateway_backend/application/submission/accept_transaction.py`
- `vnext/backend/src/gateway_backend/application/submission/ports.py`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/database.py`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_mapping.py`
- `vnext/backend/tests/test_submit_transactions.py`
- `docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-round2-remediation-brief.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-handoff.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-d1-projection-freshness-execution-plan.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-d1-projection-freshness-handoff.md`

## 容器决策

```yaml
container_rebuild_required: no
container_reason: T1 projection freshness 为 control DB/application Python 逻辑；无 image/Dockerfile/Compose 变更
last_verified_image_revision: not_applicable
container_gate_for_current_head: deferred
deferred_to: 阶段最终候选/S3 ready；建议先完成 uv.lock 工程计划
```

## Verification record（D-1 实现侧亲跑）

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
# 165 passed

uv run pytest -q -m unit tests/test_submit_transactions.py
# 35 passed（含 7 项 D-1 新增）

uv run ruff check src/gateway_backend/application/submission \
  src/gateway_backend/infrastructure/control_db tests/test_submit_transactions.py
# clean

uv run mypy
# Success (333 source files)
```

D-1 变更未触达 `vnext/backend/uv.lock`（工作区其他轨可能有独立 lock 改动，不在本卷证明范围）。

## Next step

独立评审按执行计划 §5 + 本卷验证记录复核；通过后方可关闭 D-1 并评估 S2 pass（实现侧不自签）。

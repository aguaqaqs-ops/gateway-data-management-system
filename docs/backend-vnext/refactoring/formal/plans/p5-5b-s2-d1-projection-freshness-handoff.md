# P5-5B-S2 D-1 Projection Freshness Handoff

状态：**D-1 closed — independent review pass**

日期：2026-09-15

Owner：P5-5B Delivery（实现侧；不签署独立 closure）

输入：[D-1 Execution Plan](p5-5b-s2-d1-projection-freshness-execution-plan.md)、
[Round-2 Remediation Handoff](p5-5b-s2-round2-remediation-handoff.md)

文档基线 parent：`c0d607bc49b245dacc49f8c210cd069e12d39b43`

代码候选：`2da4d71f3c8090cfac08390cfe5f3fb79fd305f4`

## Authority gate snapshot

```yaml
decision_direction: same_uow_projection_freshness
user_direction_confirmation: confirmed_in_conversation_2026_09_15
design_owner: Backend vNext Architecture
design_owner_signature_or_decision_reference: d1_t1_implementation_plan_2026_09_15
owning_design_commit: 2da4d71f3c8090cfac08390cfe5f3fb79fd305f4
allowed_paths_amendment_commit: 2da4d71f3c8090cfac08390cfe5f3fb79fd305f4
implementation_authorization_reference: d1_t1_implementation_plan_2026_09_15
independent_design_review: pass
independent_review: docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-final-independent-review.md
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
| 独立 closure / S2 pass | **pass**（见 final independent review） |

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
container_gate_for_current_head: pass
deferred_to: none（工程轨见 uv-lock handoff §7 @ 2da4d71f）
```

## Verification record（D-1 实现侧亲跑）

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run --offline pytest -q -m unit \
  tests/test_architecture.py tests/test_submit_domain.py tests/test_submit_application.py \
  tests/test_submit_idempotency.py tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py tests/test_submit_transactions.py \
  tests/test_sqlite_workspace_repository.py tests/test_workspace_control_db_migrations.py
# 165 passed @ 2da4d71f

./vnext/scripts/uv-consume.sh -C vnext/backend run --offline pytest -q -m unit tests/test_submit_transactions.py
# pass（含 D-1 并发 winner / Head 漂移 replay）@ 2da4d71f

./vnext/scripts/uv-consume.sh -C vnext/backend run --offline pytest -q -m unit
# 1894 passed / 0 failed @ 2da4d71f
```

D-1 变更未触达 `vnext/backend/uv.lock`（`git diff -- vnext/backend/uv.lock` 为空 @ closure）。

## Next step

D-1 closed；S2 closure pass。见 [p5-5b-s2-final-independent-review.md](p5-5b-s2-final-independent-review.md)。

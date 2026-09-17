# P5-5B-S5 Independent Review (Retroactive)

状态：**PASS — S5 stage closed; S6 entry authorized at time of delivery**

日期：2026-09-17

Owner：Independent reviewer（read-only; retroactive sign-off）

## 1. Review target and decision

```yaml
stage: P5-5B-S5-submit-jobdefinition-repository-effect-recovery
implementation_candidate: c9a6d032e049a9dbc61a0aaa9969aa56d274cfda
review_note: exact S5 tip is c9a6d032 (round-5 remediation); reviewed at lineage HEAD 37fa7c21
parent_head: 0c97fc276b641ea59bbbdbc99cde7ff0d772aa46
s5_commit_range: 8996a2b5..c9a6d032
decision: pass
findings_open: []
s6_entry: authorized_retroactively
s7_prerequisite: contributes_to_s1_s6_all_pass
```

评审对象：S5 scope（[`p5-5b-s5-handoff.md`](p5-5b-s5-handoff.md) changed paths）@ commit `c9a6d032`；验证在 lineage HEAD `37fa7c21` 重跑 focused gate（S6 未改 S5 production 语义）。

## 2. Authority audit

| Gate | Result |
| --- | --- |
| `p4_r6_exit` | pass（S4 final review lineage） |
| `p5_5b_design` | accepted |
| `p5_5b_implementation_authorized` | yes |
| `p5b_real_repository_effect_authorized` | yes |
| `s4_independent_review` | pass |
| P4 core untouched | pass — 无 `operations/**`、`application/recovery.py`、Repository packages 变更 |
| `unresolved_contract_drift` | none |

## 3. S0-F1~F3 closure（S5 layer）

| Finding | Design authority | S5 evidence |
| --- | --- | --- |
| S0-F1 PRE_REQUEST 不得作 abort proof | design §10.3 | `test_prepared_attempt_operator_abort_retains_occupancy`；`test_submit_import_prepared_without_prepare_checkpoint_stays_manual_recovery`；`ALLOWED_ABORT_CODES` 三码守卫 |
| S0-F1 unknown-outcome 保留 occupancy | design §10.3 / §11 | `test_submit_recovery_without_checkpoint_retains_occupancy`；`test_await_import_result_timeout_marks_manual_recovery`；`test_submit_recovery_maps_timeout_to_manual_recovery` |
| S0-F2 internal recovery HTTP | design §9 | S4 owner `test_operator_recovery_http.py`（S5 未改 wire；F6 typed errors 在 S5 orchestration） |
| S0-F3 prepare=RETRY / external=RESUME | design §10 | `build_submit_recovery_port`；`test_operator_recovery_mapping.py`；HTTP capability 负例在 S4 owner |

## 4. §4 unique owner verification

| Owner file | Collected @ HEAD | Gate |
| --- | ---: | --- |
| `test_submit_job_payload.py` | 23 | pass |
| `test_submit_job_prepare.py` | 3 | pass |
| `test_submit_finalize.py` | 1 | pass |
| `test_submit_job_effect.py` | 16 int + serial subset | pass |
| `test_submit_recovery.py` | 9 | pass |
| `test_submit_worker.py` | 8 | pass |
| `test_operator_recovery_mapping.py` | 3 | pass |
| `test_architecture.py`（S5 submit 子集） | 43/45 | 2 项 S6 边界扩展见 §5 |

## 5. Focused gate results（@ HEAD `37fa7c21`, `uv-consume.sh`）

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_submit_job_payload.py tests/test_submit_job_prepare.py \
  tests/test_submit_finalize.py tests/test_operator_recovery_mapping.py \
  tests/test_architecture.py \
  -k "not test_worker_bootstrap_owns_concrete_process_composition and not test_repository_client_is_confined"
# 71 passed

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and not serial' \
  tests/test_submit_job_effect.py tests/test_submit_recovery.py tests/test_submit_worker.py
# 26 passed, 7 deselected

../scripts/uv-consume.sh -C . run pytest -q -m serial \
  tests/test_submit_recovery.py tests/test_submit_worker.py tests/test_submit_job_effect.py
# 7 passed, 26 deselected

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_submit_http.py tests/test_operator_recovery_http.py
# 39 passed

../scripts/uv-consume.sh -C . run ruff check \
  src/gateway_backend/application/submit_jobs.py \
  src/gateway_backend/application/submission/errors.py \
  src/gateway_backend/application/submission/operator_recovery_mapping.py \
  src/gateway_backend/infrastructure/repository_write \
  tests/test_submit_job_payload.py tests/test_submit_job_prepare.py \
  tests/test_submit_job_effect.py tests/test_submit_recovery.py \
  tests/test_submit_worker.py tests/test_operator_recovery_mapping.py
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: 377 source files
```

**S6 lineage note**：@ HEAD，`test_architecture.py` 中
`test_worker_bootstrap_owns_concrete_process_composition` 与
`test_repository_client_is_confined_to_repository_read_and_write` 因 S6 引入
`http/runtime.py` repository client 与 worker→runtime 接线而失败；属 S6 deployment 边界扩展，
**不是 S5 功能缺陷**。S5 交付时（`c9a6d032`）handoff 报告 73 passed 仍有效。

## 6. Design §8–§11 spot checks

- 三步 static topology + closed payload/checkpoint decoders：**pass**（payload/prepare/effect owners）
- exact upload/import wire + operation identity：**pass**（recording + live paths）
- matching T3 vs Repository SUCCEEDED 分层：**pass**（effect + finalize + transactions）
- stable abort 三码 + operator abort adapter：**pass**（recovery + live evidence port）
- response-loss upload replay：**pass**（`test_submit_import_upload_response_loss_replays_via_recovery`）
- T3 evidence replay without re-poll：**pass**（`test_await_import_replays_t3_from_persisted_evidence_without_poll`）
- **Deferred to S7**：design §11 `T3 commit后worker response loss` 无 dedicated nodeid（S7 矩阵项）

## 7. Deferred / non-blocking

- Repository restart submit journey：design §11 要求 worker poll-only；无 backend restart integration（S7 评估）
- Production deployment wiring：explicitly deferred to S6（handoff §Deferred）
- Container rebuild：no（S5 scope）

## 8. Conclusion

S5 功能交付与 §4 owner 证据 **pass**。五轮 remediation（F1–F4、A/B、B1–M5）均已闭合。
追溯签署不修改 implementation authority；`s6_entry` 追溯为 authorized。

```yaml
next_step: S6 independent review completion (round 6 @ 37fa7c21)
s7_entry: blocked_pending_s6_pass
```

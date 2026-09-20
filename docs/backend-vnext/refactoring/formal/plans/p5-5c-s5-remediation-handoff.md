# P5-5C-S5 Finding-Scoped Remediation Handoff

状态：**pass — P1/P2 closed @ independent review remediation**

日期：2026-09-20 (UTC+8)

Owner：P5-5C Delivery

## Authority gate snapshot

```yaml
p5_5b_slice_exit: pass
p5_5c_design: accepted
p5_5c_implementation_authorized: yes
source_or_test_change_authorized: true
unresolved_contract_drift: none
repository_effect_authorized: false
production_deployment_authorized: false
```

## Traceability

```yaml
stage: P5-5C-S5-remediation
parent_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5c-s5-handoff.md
implementation_candidate_head: 66bdca8812
remediation_implementation_head: 04317788c2
finding_remediation: P1, P2
independent_review: pending_publication
next_step: independent_acceptance_authority_for_p5_5c_slice_exit
```

`implementation_candidate_head` 保留首次 S5 compose e2e 交付 `66bdca8812`；
`remediation_implementation_head` 绑定 P1/P2 gate harness 修复提交 `04317788c2`。

## Findings closed

| ID | Severity | Summary | Closure |
| --- | --- | --- | --- |
| P1 | P1 | `test_backend_container_ready_and_stops_cleanly_with_repository_service` skipped when `compose build repository-service` failed | Shared harness uses `build-repository-service-image.sh` + `up --no-build`; nodeid **pass**; conjunction **0 skipped** |
| P2 | P2 | Handoff `deploy-backend`/`deploy-worker` IDs did not match conjunction runtime images | Fixed `GATEWAY_COMPOSE_GATE_PROJECT_NAME` + `GATEWAY_COMPOSE_GATE_PREBUILT=1`; prebuild `gateway-p5-5c-s5-gate` images consumed by all conjunction tests |

## Changed paths

- `vnext/backend/tests/support/compose_gate_harness.py` (new)
- `vnext/backend/tests/test_submit_compose_e2e.py`
- `vnext/backend/tests/test_review_compose_e2e.py`
- `vnext/backend/tests/test_backend_http_container_gate.py`
- `docs/backend-vnext/refactoring/formal/plans/p5-5c-s5-handoff.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5c-s5-remediation-handoff.md`

## Conjunction gate（@ `04317788c2`，PREBUILT project `gateway-p5-5c-s5-gate`）

```bash
export GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5c-s5-gate
export GATEWAY_COMPOSE_GATE_PREBUILT=1
export GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local

cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py \
  tests/test_backend_http_container_gate.py
# 5 passed, 0 skipped
```

| nodeid | Result |
| --- | --- |
| `test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey` | **pass** |
| `test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart` | **pass** |
| `test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` | **pass** |
| `test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint` | **pass** |
| `test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service` | **pass** |

## Independent countersign

```yaml
review: pending
next_step: independent_acceptance_authority_for_p5_5c_slice_exit
```

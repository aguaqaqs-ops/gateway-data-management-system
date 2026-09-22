# P5-5D-S3 Public API, Production Composition and Deployment Inputs Handoff

状态：**S3 pass — delivery complete（不签 slice exit）**

日期：2026-09-22

Owner：Backend Archive HTTP / Deployment

## Authority gate snapshot

```yaml
p5_5d_s1_stage_exit: pass
p5_5d_s2_stage_exit: pass
p5_5d_design: accepted
p5_5d_implementation_authorized: yes
source_or_test_change_authorized: true
unresolved_contract_drift: none
repository_effect_authorized: false
production_deployment_authorized: false
p5_5d_s3_stage_exit: pass
p5_5d_slice_exit: not_evaluated
```

## Traceability

```yaml
stage: P5-5D-S3-public-api-production-composition-and-deployment-inputs
parent_plan: docs/backend-vnext/refactoring/formal/plans/p5-5d-archive-execution-plan.md
implementation_candidate_head: a6720238d6cc7e9f1bccc029ba774f413429ec52
evidence_delivery: delivered_by_commit_introducing_this_handoff
workspace_schema_version: 5
uv_lock_in_diff: no
candidate_binding: independent_review_uses_git_head_at_review_time
next_step: P5-5D-S4
```

## Scope delivered

### New HTTP layer

- `vnext/backend/src/gateway_backend/http/schemas/archive.py` — Design §8.1 DTOs, `extra=forbid`, delegates to Application contracts
- `vnext/backend/src/gateway_backend/http/orchestration/archive.py` — seven operations, idempotency/body-size enforcement
- `vnext/backend/src/gateway_backend/http/routes/archives.py` — seven Archive routes

### Modified HTTP / wiring

- `vnext/backend/src/gateway_backend/http/wiring.py` — `include_router(archives_router)`; `PRODUCTION_OPENAPI_PATHS` +7
- `vnext/backend/src/gateway_backend/http/errors.py` — `ArchiveApplicationError` stable_code → 409/404 before Submit fallback

### Minimal Application / Infra extension (audit-events list)

- `vnext/backend/src/gateway_backend/application/archive/queries.py` — `list_archive_audit_events`
- `vnext/backend/src/gateway_backend/domain/archive/ports.py` — `list_confirmation_events` / `list_resolution_events`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_archive.py` — scoped SQL with `after_sequence` + `LIMIT`

### Deployment inputs

- `vnext/deploy/config/session.json` — explicit `archive_submission` in example session
- `vnext/deploy/README.md` — permissions, initial seed, maintenance upgrade, secret file paths

### Tests

- `vnext/backend/tests/test_archive_http.py` — contract owner (27 passed)
- `vnext/backend/tests/test_archive_compose_e2e.py` — compose journey (1 passed)
- Updated: `test_http_openapi.py`, `test_http_auth_matrix.py`, `test_production_wiring.py`
- O-1 fix: `test_production_wiring.py` authoritative baseline head alignment (18 passed)
- `test_submit_compose_e2e.py` — `journey_key_prefix` parameter for idempotency isolation

### Routes registered (production OpenAPI)

| Method | Path |
| --- | --- |
| GET | `/v1/archive-candidates` |
| POST | `/v1/archive-plan-preview` |
| POST | `/v1/archive-confirmations` |
| POST | `/v1/archive-anomaly-resolutions` |
| GET | `/v1/archive-audit-events` |
| POST | `/v1/archives` |
| GET | `/v1/archives/{archive_result_id}` |

Worker job registry: **no** Archive job added.

## Invariants delivered

- All seven Design §8 routes on production factory via `register_workspace_http`
- `archive_submission` permission independent of review/submit; example session grants explicitly, not auto-all
- Write routes (`confirmations`, `anomaly-resolutions`, `archives`) wrapped in `acquire_new_work`; Preview/candidates/audit-events/result reads do not
- `ArchiveApplicationError` maps to 409/404 per Design §8.2; `ArchiveIntegrityFailure` → 503; `ArchiveAuditVersionConflict` includes expected/actual details
- Preview is read-only (no durable archive table growth on repeat calls)
- Archive Start produces zero Repository effect (main commit unchanged in HTTP and compose tests)
- HTTP responses do not leak `repository_id`, internal paths, or raw SQL
- Dual-sibling candidate-set semantics, disposition, and Head CAS proven in `test_archive_http.py` (application fixture journey)

## Compose journey scope note

`test_archive_compose_e2e.py` exercises a **single approved submission** Archive journey with zero Repository effect, Head bump, and backend/worker restart persistence. A second full HTTP Submit on the same device/project workspace is blocked by `SUBMIT_OCCUPANCY_CONFLICT` after the first finalized submission; dual-sibling Archive semantics remain owned by `test_archive_http.py` with seeded approved siblings. Compose proves production wiring, permissions, admission, and restart durability on a real initial-empty provisioning path.

## Unique test owners

- `tests/test_archive_http.py` — UTF-8 boundary shared param table, permissions, replay, admission, Preview no-write, dual-sibling HTTP journey
- `tests/test_archive_compose_e2e.py` — three-container stack, real provisioning, Archive confirm/start, main unchanged, restart Head persistence
- `tests/test_http_openapi.py` — frozen OpenAPI path set including seven Archive paths
- `tests/test_http_auth_matrix.py` — archive mutation without permission → 403
- `tests/test_production_wiring.py` — `test_production_runtime_exposes_archive_routes`; O-1 baseline head fix

## Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q \
  tests/test_archive_http.py tests/test_http_auth_matrix.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py
# => 107 passed, 1 warning, ~6s

../scripts/uv-consume.sh -C . run ruff check .
# => All checks passed

../scripts/uv-consume.sh -C . run mypy
# => Success: no issues found in 421 source files
```

五包 static（backend / repository_service / repository_client / repository_contracts / shared_kernel）ruff + mypy 全通过；无 `uv.lock` 变更。

## Container / image gate

```yaml
container_rebuild_required: yes
container_reason: S3 touches production HTTP routes, wiring, errors, deployment session example
compose_project_name: gateway-p5-5d-s3-gate
prebuilt_used: no
```

### Fresh build

```bash
# repository-service: pre-existing local image (build script skipped when tag present)
docker compose -f vnext/deploy/compose.yaml build backend worker
# exit 0; images tagged gateway-p5-5d-s3-gate-backend / gateway-p5-5d-s3-gate-worker
```

### Image IDs (immutable)

| Service | Image ref | ID |
| --- | --- | --- |
| repository-service | `gateway-repository-service:local` | `sha256:70c25d76bb1abd9a24e73558c91d66e99980cee49d3f55a5e2ea50b936eb7487` |
| backend | `gateway-p5-5d-s3-gate-backend` | `sha256:a05b5de49b677f5ce8fcf601f634ed63b1599968d2f637f0f7f21de96eb9d216` |
| worker | `gateway-p5-5d-s3-gate-worker` | `sha256:313302c977a80c7139c9bd4d7115211fb81a6ec59122b950c1505c38cd4f3f12` |

Containers torn down after each test (`compose down -v`); running container IDs not retained. Image IDs above bound the verified candidate.

### Conjunction (6 passed, 0 skipped, ~277s)

```bash
cd vnext/backend
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5d-s3-gate \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
```

| nodeid | result |
| --- | --- |
| `tests/test_archive_compose_e2e.py::test_compose_archive_single_submission_journey_restart_and_head_persistence` | pass |
| `tests/test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey` | pass |
| `tests/test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart` | pass |
| `tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` | pass |
| `tests/test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint` | pass |
| `tests/test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service` | pass |

## Provenance record (§6.3)

| 证据 | 值 |
| --- | --- |
| Git HEAD | `a6720238d6cc7e9f1bccc029ba774f413429ec52` |
| uv.lock SHA (backend) | `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
| uv.lock SHA (repository_service) | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| uv.lock SHA (repository_client) | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| uv.lock SHA (repository_contracts) | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| uv.lock SHA (shared_kernel) | `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
| compose.yaml SHA-256 | `f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0` |

## Forbidden imports

None. HTTP layer imports Application archive modules and existing HTTP dependencies only.

## Independent countersign

```yaml
review: pending
next_step: P5-5D-S4
slice_exit: not_signed_by_delivery
```

Delivery does not sign `p5_5d_slice_exit` or `production_deployment_authorized`.

# P5-5B-S6 Remediation Round 1 Handoff

状态：**S6 remediation round 1 complete — candidate 待复审**

日期：2026-09-17

Owner：P5-5B Delivery

## Review closure

```yaml
review: p5-5b-s6-independent-review.md
parent_candidate: ff9ea77cfe0dcf1b7f807fec2374c7b3bb8c170a
remediation_round: 1
findings_addressed:
  S6-R1: closed — del removed; HttpBaselineCanonicalDigestPort calls preview_jobs owner; real port tests
  S6-R2: closed — design §6.1 frozen; port extended; compute_baseline_canonical_bundle_digest isomorphic to preview
  S6-R3: closed — runtime duplicate closure/pipeline removed; surface_artifact_closure exported from preview_jobs
  S6-R4: closed — /readyz 503 HTTP assertion; registry decoder identity check; workspace registry cross-check test
  S6-R5: closed — compose e2e fallback explicitly skips with image id reason
  S6-R6: closed — backend stop_grace_period: 180s in compose.yaml
  S6-R7: closed — tautological assertions removed; production NO_CANONICAL_CHANGE uses real port
  S6-R8: closed — recovery capability lookup unified; FailClosedSession/Scope removed; settings __all__ cleanup
container_rebuild_required: yes
container_reason: S6 remediation touched compose stop_grace_period and deployment/runtime wiring
container_gate_for_current_head: deferred
```

## Key changes

| Finding | Fix |
|---------|-----|
| R1 | `HttpBaselineCanonicalDigestPort` delegates to `compute_baseline_canonical_bundle_digest`; no `del` on frozen `BaselineHead` |
| R2 | Design §6.1 defines base digest semantics; `BaselineCanonicalDigestPort` takes `input_completeness` + `ruleset_version`; preview-isomorphic bundle assembly |
| R3 | `surface_artifact_closure` + `compute_baseline_canonical_bundle_digest` exported from `preview_jobs.py`; ~300 lines removed from `runtime.py` |
| R4 | `assert_submit_registry_decoders`; lifespan shutdown `/readyz` 503 test; full registry identity test |
| R5 | Compose e2e skips on repository build fallback with explicit reason |
| R6 | `backend.stop_grace_period: 180s` |
| R7/R8 | Production wiring tests call real port; shared `build_submit_recovery_capability_mapping` |

附加修复：`prepare_backend_runtime().unit_of_work_factory` 现接受 `read_only=`，与 submit acceptance 契约一致。

## Focused gate

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_backend_settings.py \
  tests/test_backend_readiness.py \
  tests/test_http_admission_shutdown.py \
  tests/test_production_wiring.py
# 32 passed

../scripts/uv-consume.sh -C . run pytest -q -m serial \
  tests/test_submit_worker_process.py
# 3 passed

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_compose_e2e.py
# 1 skipped (repository-service conjunction build unavailable; fallback image in use)

../scripts/uv-consume.sh -C . run ruff check .
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: no issues found in 371 source files
```

## New owner test nodeids

- `test_http_baseline_canonical_digest_port_returns_digest`
- `test_http_baseline_canonical_digest_port_maps_failures_to_503`
- `test_accept_submit_rejects_no_canonical_change_with_production_port`
- `test_surface_artifact_closure_owner_includes_ordered_and_projection_paths`
- `test_production_lifespan_shutdown_marks_not_ready` (extended: `/readyz` 503 after lifespan)

## Deferred

- S8 authoritative runner、五包 static conjunction、current-HEAD image digest
- Compose e2e full conjunction pass（本环境 repository-service build 失败时显式 skip）
- S7 independent functional acceptance

## next_step

```yaml
next_step: S6 independent review round 2
s7_entry: blocked pending S6 pass
```

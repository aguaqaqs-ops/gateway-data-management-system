# P5-5B-S6 Remediation Round 2 Handoff

状态：**S6 remediation round 2 complete — superseded by round 3（见 p5-5b-s6-remediation-round3-handoff.md）**

日期：2026-09-17

Owner：P5-5B Delivery

## Review closure

```yaml
review: p5-5b-s6-independent-review-2.md
parent_candidate: 1bbc125d99f7b4dd24fe97d0ff39b0cec10a1a25
remediation_round: 2
findings_addressed:
  S6-RR1: closed — bundle_assembly cross-pair shared promotion; FULL port digest + preview↔port equality
  S6-RR2: closed — surface_artifact_closure behavior test; architecture boundary on runtime.py
  S6-RR3: closed — WorkspaceHttpDependencies uses SubmitControlUnitOfWorkFactory; casts removed
  S6-RR4: closed — ruleset_version fail-closed against RULESET_VERSION; preview payload aligned
  S6-RR5: closed — port maps only PreviewJobError/ValueError to 503; programming errors propagate
  S6-RR6: closed — production composition 202 accept path with real runtime
container_rebuild_required: no
container_reason: round 2 touched bundle capability and HTTP orchestration types only; no compose/Dockerfile change
container_gate_for_current_head: deferred
```

## Key changes

| Finding | Fix |
|---------|-----|
| RR1 | `_collect_bindings` promotes duplicate `source_ref` across pairs to `shared/…` for all kinds; design §6.1 updated |
| RR2 | `test_surface_artifact_closure_maps_ordered_and_projection_refs`; `test_http_runtime_does_not_duplicate_surface_artifact_closure` |
| RR3 | `SubmitControlUnitOfWorkFactory` on `WorkspaceHttpDependencies` / submit / preview / multipart orchestration |
| RR4 | `compute_baseline_canonical_bundle_digest` requires `ruleset_version == RULESET_VERSION`; `build_preview_job_payload` emits `RULESET_VERSION` |
| RR5 | `HttpBaselineCanonicalDigestPort` single except; `test_http_baseline_canonical_digest_port_does_not_mask_programming_errors` |
| RR6 | `test_accept_submit_returns_202_with_production_runtime` |

## Focused gate

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_backend_settings.py \
  tests/test_backend_readiness.py \
  tests/test_http_admission_shutdown.py \
  tests/test_production_wiring.py \
  tests/test_bundle_assembly.py
# 50 passed

../scripts/uv-consume.sh -C . run pytest -q -m 'unit and integration' \
  tests/test_preview_job_assemble.py::test_full_canonical_noop_bundle_digest_matches_baseline_port
# 1 passed

../scripts/uv-consume.sh -C . run pytest -q -m serial \
  tests/test_submit_worker_process.py
# 3 passed

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_compose_e2e.py
# deferred — not re-run this round (repository-service conjunction build unavailable)

../scripts/uv-consume.sh -C . run ruff check .
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: no issues found in 371 source files
```

## New owner test nodeids

- `test_multi_pair_identical_artifact_refs_are_shared`
- `test_http_baseline_canonical_digest_port_returns_digest_for_full`
- `test_full_canonical_noop_bundle_digest_matches_baseline_port`
- `test_accept_submit_rejects_no_canonical_change_for_full_with_production_port`
- `test_surface_artifact_closure_maps_ordered_and_projection_refs`
- `test_http_baseline_canonical_digest_port_does_not_mask_programming_errors`
- `test_accept_submit_returns_202_with_production_runtime`
- `test_http_runtime_does_not_duplicate_surface_artifact_closure`

## Deferred

- S8 authoritative runner、五包 static conjunction、current-HEAD image digest
- Compose e2e conjunction（沿用 round 1 skip 策略）
- S7 independent functional acceptance

## next_step

```yaml
next_step: S6 independent review round 3
s7_entry: blocked pending S6 pass
```

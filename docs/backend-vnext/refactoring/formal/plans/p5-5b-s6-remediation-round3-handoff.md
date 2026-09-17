# P5-5B-S6 Remediation Round 3 Handoff

状态：**S6 remediation round 3 complete — candidate 待 round 4 复审**

日期：2026-09-17

Owner：P5-5B Delivery

## Review closure

```yaml
review: p5-5b-s6-independent-review-3.md
parent_candidate: c55726cac6e4f41d3b5808ccd48815df10a9557d
remediation_round: 3
findings_addressed:
  S6-RR9: closed — digest port maps repository/transport failures to 503 DEPENDENCY_UNAVAILABLE;
    unsupported ruleset to 503 SERVICE_NOT_READY; programming errors propagate
  S6-RR10: closed — design §6.1 documents preview/submit ruleset_version vocabularies and upgrade rule
  S6-RR11: closed — comparison-bundle.md and bundle-assembly.md updated for cross-pair shared-ref rules
container_rebuild_required: no
container_reason: round 3 touched HTTP exception mapping and documentation only
container_gate_for_current_head: deferred
```

## Key changes

| Finding | Fix |
|---------|-----|
| RR9 | `_api_error_for_baseline_digest_failure` in `runtime.py`; repository client + httpx errors → 503 DEPENDENCY_UNAVAILABLE |
| RR9 | ruleset mismatch → 503 SERVICE_NOT_READY with distinct message |
| RR9 | Tests: ConnectError, ReadTimeout, legal wire error body; ruleset split from dependency failures |
| RR10 | design §6.1: preview `RULESET_VERSION` vs submit `"v1"`; upgrade requires re-preview |
| RR11 | `comparison-bundle.md` + `bundle-assembly.md` shared-ref promotion rules; optional `by_path` cleanup |

## Focused gate

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_backend_settings.py \
  tests/test_backend_readiness.py \
  tests/test_http_admission_shutdown.py \
  tests/test_production_wiring.py \
  tests/test_bundle_assembly.py
# 53 passed

../scripts/uv-consume.sh -C . run pytest -q -m serial \
  tests/test_submit_worker_process.py
# 3 passed

../scripts/uv-consume.sh -C . run ruff check .
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: no issues found in 371 source files
```

## Compose conjunction attempt

```bash
cd vnext/deploy
docker compose build backend worker repository-service
# repository-service FAILED: dolt-linux-amd64.tar.gz sha256 mismatch (environment/network)

../scripts/uv-consume.sh -C ../backend run pytest -q -m 'integration and serial' \
  tests/test_submit_compose_e2e.py
# 1 skipped (repository-service conjunction build unavailable; fallback image in use)
```

## New owner test nodeids

- `test_http_baseline_canonical_digest_port_maps_unsupported_ruleset_to_service_not_ready`
- `test_http_baseline_canonical_digest_port_maps_repository_connect_failure_to_503`
- `test_http_baseline_canonical_digest_port_maps_repository_timeout_to_503`
- `test_http_baseline_canonical_digest_port_maps_repository_wire_error_to_503`

## Deferred

- S8 authoritative runner、五包 static conjunction、current-HEAD image digest
- Compose e2e full conjunction pass（repository-service build 仍因 dolt checksum 失败）

## next_step

```yaml
next_step: S6 independent review round 4
s7_entry: blocked pending S6 pass
```

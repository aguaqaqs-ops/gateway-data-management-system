# P5-5B-S1 Submission Domain and Application Handoff

状态：**S1 closure signed — independent countersign complete**

日期：2026-09-14

Owner：P5-5B Delivery

## Authority gate snapshot

```yaml
p4_r6_exit: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
p5b_real_repository_effect_authorized: yes
unresolved_contract_drift: none
first_authorized_step: P5-5B-S1
```

## Traceability

```yaml
stage: P5-5B-S1-submission-domain-application
parent_head: 6b8e7fc5468389c5f2907d8d3a9a5f52566e5ef6
candidate_head: 1360d0e0bdc32b98c576f495bbae205ac9bbe512
remediation_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5b-s1-remediation-handoff.md
uv_lock_in_diff: no
```

```yaml
stage: P5-5B-S1-submission-domain-application
input_authority:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s0-remediation-independent-review.md
scope_paths:
  - vnext/backend/src/gateway_backend/domain/submission/**
  - vnext/backend/src/gateway_backend/application/submission/**
  - vnext/backend/tests/test_submit_domain.py
  - vnext/backend/tests/test_submit_application.py
  - vnext/backend/tests/test_submit_idempotency.py
  - vnext/backend/tests/test_architecture.py
changed_paths:
  - vnext/backend/src/gateway_backend/domain/submission/__init__.py
  - vnext/backend/src/gateway_backend/domain/submission/errors.py
  - vnext/backend/src/gateway_backend/domain/submission/models.py
  - vnext/backend/src/gateway_backend/domain/submission/policies.py
  - vnext/backend/src/gateway_backend/domain/submission/ports.py
  - vnext/backend/src/gateway_backend/application/submission/__init__.py
  - vnext/backend/src/gateway_backend/application/submission/abort.py
  - vnext/backend/src/gateway_backend/application/submission/accept.py
  - vnext/backend/src/gateway_backend/application/submission/contracts.py
  - vnext/backend/src/gateway_backend/application/submission/errors.py
  - vnext/backend/src/gateway_backend/application/submission/finalize.py
  - vnext/backend/src/gateway_backend/application/submission/ports.py
  - vnext/backend/tests/test_submit_domain.py
  - vnext/backend/tests/test_submit_application.py
  - vnext/backend/tests/test_submit_idempotency.py
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s1-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s1-remediation-handoff.md
invariants_delivered:
  - SubmitAttempt / Submission immutable domain records with four-state guards
  - Field co-presence and Submission unique Attempt binding at domain boundary
  - Server-computed accept request fingerprint with source/snapshot/closure digest fields and replay helpers
  - Same-key replay skips Workspace OPEN gate while preserving scope re-authorization
  - Repository upload/import effect-key derivation from submit_attempt_id
  - Accept pre-transaction validation order with idempotency replay and NO_CANONICAL_CHANGE
  - Replay path does not resolve Repository main
  - Pure matching/replay closure smoke in test_submit_application.py（authoritative unit owner: test_submit_finalize.py / S5）
  - Abort proof shape + matching identity guard（transaction/recovery proof deferred to S2/S5）
  - Workspace occupancy XOR and row-existence occupancy guard
unique_test_owners:
  - tests/test_submit_domain.py
  - tests/test_submit_application.py  # S1 contract smoke; not finalize unit owner
  - tests/test_submit_idempotency.py    # Accept fingerprint/replay authoritative unit owner
  - tests/test_architecture.py
finalize_unit_owner_deferred:
  - tests/test_submit_finalize.py       # execution plan §4 authoritative unit owner (S5)
recovery_integration_owner_deferred:
  - tests/test_submit_recovery.py       # execution plan §4 Repository/recovery integration owner
focused_commands_and_results:
  - cd vnext/backend && uv run pytest -q -m unit tests/test_submit_domain.py tests/test_submit_application.py tests/test_submit_idempotency.py tests/test_architecture.py => 102 passed (S2 remediation re-run 2026-09-14)
  - cd vnext/backend && uv run ruff check . && uv run mypy => pass (332 source files)
five_package_static: deferred
authoritative_runner: deferred
container_rebuild_required: deferred
container_reason: S1 is pure domain/application memory contracts only; container gate not claimed for current working tree
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
findings:
  - S1-F1..F9 addressed in p5-5b-s1-remediation-handoff.md (round-1 + round-2 + round-3)
  - S2-F1 S1 focused re-run recorded in p5-5b-s2-remediation-handoff.md
deferred:
  - T1 SQLite atomicity and occupancy persistence (S2)
  - HTTP / Repository wire / JobDefinition effect (S4/S5)
  - Import builder and nominal artifact conversion boundary (S3)
  - End-to-end finalize replay unit coverage (S5 / test_submit_finalize.py)
  - Repository/recovery integration (test_submit_recovery.py per execution plan)
reopen_required: []
implementation_authority_unchanged: true
next_step: P5-5B-S3 entry (S2 closure pass)
independent_countersign:
  review: docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-final-independent-review.md
  candidate_head: 2da4d71f3c8090cfac08390cfe5f3fb79fd305f4
  s1_focused_rerun: 102 passed (four-file); nine-file 165 passed; full unit 1894 passed (cross-ref S2 final)
```

## Notes

- S1 uses in-memory fakes only; no SQLite, HTTP, Repository client, or real Dolt/process I/O.
- `canonical_business_digest` maps to `PreviewResult.digests.bundle_digest` for Accept validation.
- `BackendArtifactRef` and `RepositoryArtifactRef` are separate nominal domain types; conversion to `gateway_backend.artifacts` is deferred to S3.
- S1 does **not** claim T1 transaction atomicity, T3 SQLite UoW, or real Repository effect.
- Initial S1 review findings S1-F1..F7 are remediated per `p5-5b-s1-remediation-handoff.md`; `vnext/backend/uv.lock` is not part of the delivery diff.

# P4-R4-S6 Independent Review

状态：**PASS AFTER S5 REMEDIATION — S7 required and not authorized**

日期：2026-08-25

Reviewer：Independent R4 reviewer

上游：[P4-R4-S5 Handoff](p4-r4-s5-handoff.md)、[P4-R4-S5 Remediation Appendix](p4-r4-s5-remediation-appendix.md)

```yaml
step_id: P4-R4-S6
context: mandatory_new_conversation
input_handoff_sha: e80ab19e617d8288b629e23019278681300c265edcb5672a5d54e8e037e803e6
input_validated_code_sha: 9ea535e138a7e498aeade69042bfbbff559fcfc0
validated_code_sha: not_validated
validated_source_tree: sha256:497656adb314efddc47abe5771f13848c352fb835104f4abb94da98cebf64a82
candidate_worktree: uncommitted_r4_source_test_changes
result: pass
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s6-independent-review.md
commands_and_results:
  - "backend unit focused: 143 passed"
  - "backend integration and not serial focused: 36 passed"
  - "backend serial focused: 8 passed"
  - "backend ruff/mypy: pass"
  - "shared_kernel, repository_contracts, repository_client, repository_service ruff/mypy: pass"
  - "git diff --check: pass"
focused_tests: pass
backend_unit: pass
integration: pass
serial: pass
five_package_static: pass
container_rebuild_required: yes
container_reason: S2b changed worker bootstrap/composition; S7 must rebuild current HEAD
last_verified_image_revision: none_for_r4_candidate
container_gate: deferred
benchmark: not_applicable_no_performance_claim
findings:
  - id: P4-R4-S6-F1
    severity: P1
    status: closed
    owner: application.synthetic_jobs / ArtifactStore boundary
  - id: P4-R4-S6-F2
    severity: P2
    status: closed
    owner: bootstrap.operation_worker claim/version gate
deferred_items:
  - S7 current-HEAD image build and container smoke
reopen_conditions:
  - any fix requiring R1/R2 schema, status, CAS or error-taxonomy changes
  - any fix requiring R5 retry/takeover/reconcile policy or real Repository effect
  - any fix requiring a second registry, executor, IPC, cleanup/evidence state machine or new principal
next_step: P4-R4-S7
next_step_authorized: no
```

## 1. Review basis

The reviewer read the complete R4 entry brief and detailed plan, S1a-S3c handoffs, S4 focused
review, S5 appendix and handoff, R1/R2/R3 handoffs and artifact contracts, all R4 application
source and tests, changed bootstrap/worker source and tests, and the complete current worktree
diff. The review did not rely on handoff PASS summaries alone. No production or test file was
changed during S6.

## 2. Bounded probe results

| Probe | Result |
| --- | --- |
| Unknown key/version already queued | Pass; startup preflight leaves QUEUED/PENDING and no lease. |
| Registry and decoder immutability | Pass; lookup maps are `mappingproxy` and mutation raises `TypeError`. |
| Decoder/checkpoint I/O separation | Pass; decoders receive an injected artifact port and no DB UoW; focused/static gates pass. |
| Canonical checkpoint/closure, duplicate keys, closure mismatch | Pass; S5 regressions fail closed. |
| Missing/corrupt checkpoint and stale CAS | Pass; no READY/ref publication in the existing recovery and integration owners. |
| Missing external request artifact after checkpoint | Pass after S5; see F1 closure. |
| Duplicate pure-compute/stub delivery and idempotency identity | Pass for the covered reload/duplicate matrix. |
| Cancel before request / after request | Pass; covered outcomes retain the R5 handoff boundary. |
| Process termination, non-zero failure and log redaction | Pass; selected serial/process owner and static gates pass. |

## 3. Findings and S5 closure

### P4-R4-S6-F1 — P1: missing request artifact is recreated and can produce false READY

`_request_state_from_job_state()` validates the derived request identity, then calls
`put_with_built_ref()` before `store.locate()` at
`vnext/backend/src/gateway_backend/application/synthetic_jobs.py:473-480`. If the request
artifact referenced by the durable checkpoint has been deleted, this writes a new copy and the
subsequent locate succeeds. A confirmed recovery then writes the response/closure and publishes
`SUCCEEDED` with a READY closure even though a durable artifact required by the checkpoint was
missing.

The independent probe deleted the request artifact after `_publish_stub_checkpoint_only()` and
ran the confirmed executor. Observed result:

```text
ack PUBLISHED
statuses SUCCEEDED SUCCEEDED ready ArtifactRef(...)
request_restored True
```

This violated the S6 barrier that missing bytes and digest failures must not produce READY, and
changed durable artifact state during recovery. S5 now constructs the exact ref and only calls
`store.locate()`, mapping verification failure to `CHECKPOINT_REF_UNREADABLE`. The six-case
`STUB_REQUEST_ARTIFACT_FAULTS` x confirmed/unknown/accepted regression passes. A fresh probe
observed `CheckpointDecodeError CHECKPOINT_REF_UNREADABLE`, `restored=False`,
`RUNNING/RUNNING`, and no READY closure. Closed; no cleanup broker, evidence state machine, or R5
policy was introduced.

### P4-R4-S6-F2 — P2: job-contract version gate has a claim-time TOCTOU window

`_R4WorkerStartup.claim_one()` performs its extra version validation in one write transaction at
`vnext/backend/src/gateway_backend/bootstrap/operation_worker.py:256-270`, then calls
`super().claim_one()`, which opens a second transaction and claims the next candidate. A queued
operation can be inserted after the first transaction commits and before the second transaction
starts. The second path resolves only the `JobStepKey`, so an unsupported `job_contract_version`
can receive a RUNNING step and lease before the payload wrapper fails.

The bounded race probe used an empty queue, inserted a registered key with version
`backend-vnext/import-package/v9` between the two transactions, and observed:

```text
startup READY
claimed True ... version backend-vnext/import-package/v9
persisted RUNNING RUNNING
```

This contradicted the required “unknown key/version first candidate does not generate RUNNING/lease”
barrier. S5 now performs candidate lookup, version validation, executor resolution, and
`OperationLifecycleActions.claim_one` in the same write transaction. The deterministic
`test_unsupported_job_contract_version_rejected_at_claim_without_running_lease` regression passes;
the operation and step remain `QUEUED/PENDING` without worker or lease identity. Closed; no R3
protocol widening or second registry was introduced.

## 4. Re-review decision

All S6 findings are closed after the authorized S5 remediation. The reviewer re-read the changed
source/tests and complete diff, reran the bounded probes, and reran the focused unit/integration/
serial gates plus all five package static checks. No source or test file was changed during this
re-review. Current code remains an uncommitted candidate, so `validated_code_sha` is intentionally
not sealed and the S7 current-HEAD image/container gate remains required.

## 5. Disposition and handoff

S6 is `pass_after_s5_remediation`. S7 is the only next step and remains unauthorized until its
current-HEAD candidate commit, complete module gates, image rebuild, and container smoke are sealed.
This document does not authorize R5, P5, production effect validation, or any container claim for
the current uncommitted candidate.

# P4-R5-S6 Independent Review

状态：**PASS AFTER FINDING-SCOPED REMEDIATION AND R3 REOPEN — S7 required and not authorized**

日期：2026-08-27

Reviewer：independent sealed-evidence reviewer

上游：[P4-R5-S4 Focused Review](p4-r5-s4-focused-review.md)、
[P4-R5-S3c Handoff](p4-r5-s3c-handoff.md)、
[P4-R5-R3 Recovery-Release Reopen](p4-r5-r3-recovery-release-reopen.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)

```yaml
step_id: P4-R5-S6
context: mandatory_new_conversation
input_review_sha: 9beea4572b5896f2e7268b1c38aa20e54c4ea1a3
reviewed_head: 9beea4572b5896f2e7268b1c38aa20e54c4ea1
candidate_code_sha: pending_explicit_commit_authorization
candidate_worktree: documented_dirty_candidate
validated_source_tree: sha256:2fcb0e05217590b09a552e545a196847d76e50c260fa2229dca6335da1e02e4d
source_tree_method: sorted_per_file_sha256_records_for_vnext/backend/src_and_tests_python_files
result: pass
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s6-independent-review.md
focused_tests: pass_154_plus_f1_integration_1
backend_unit: sealed_s5_1615_passed
integration: pass_1_f1_regression_and_sealed_s5_36
serial: deferred_to_s7
five_package_static: pass
container_rebuild_required: yes
container_reason: worker/runtime recovery composition is in scope; S7 must rebuild current HEAD after findings close
last_verified_image_revision: none_for_current_candidate
container_gate: deferred_to_S7
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - explicit commit authorization and clean candidate before S7
  - current-HEAD image/container gate owned by S7
reopen_conditions:
  - any fix requiring R1/R2 schema, status, CAS or error-taxonomy change
  - any real Repository effect, new principal/IPC, second registry or generic evidence state machine
handoff_document: p4-r5-s6-independent-review.md
next_step: P4-R5-S7
next_step_authorized: no
```

## 1. Independent decision

S6 passes after independent verification of the F1/F2 behavioral fixes, F3 static fix and the
accepted bounded R3 recovery-release reopen. The accepted public surface matches the implementation:
live-lease recovery release remains serialized by `LeaseSession` through `OperationLifecycleActions`,
without promoting `RecoveryPort`, changing R1/R2 schema/CAS, or adding an application runtime import.
The candidate remains an uncommitted dirty worktree and therefore has no sealed code commit. S7 is
required and not authorized by this record.

## 2. Finding Closure

### F1 — closed: external-effect RecoveryPort claim-path composition

The new `_RecoveryAwareWorkerRegistry` wraps the resolved `JobStepKey` executor, routes checkpointed
`EXTERNAL_EFFECT` claims to the recovery port, and releases the live lease through
`publish_recovery_release()`. The independent worker takeover regression passed and retained
`submit_count == 1` while polling the original identity to `SUCCEEDED`.

### F2 — closed: three-session reconcile budget

`transition_for_outcome()` now checks `recovery_sessions_exhausted(attempt_count)` before the 60-second
reconcile check. The new `reconcile_pending_session_exhausted` matrix row passed and produces manual
recovery without scheduling another retry.

## 3. F3/F4 Closure

### F3 — closed as a static issue: LeaseSession recovery-release protocol is mypy-compatible

Owner: Operation Runtime worker contract

The worker protocol now declares the same bounded `RecoveryTransitionIntent` parameter as the
concrete session at
[worker.py:208](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/operations/worker.py:208),
matching [lease_session.py:271](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/operations/lease_session.py:271).
The type-only import avoids a runtime `worker`/`recovery` cycle. `finalize_handler_recovery()` calls
the protocol method directly, and the `get_type_hints` contract probe locks the parameter and return
types. Independent backend strict mypy reports zero errors.

No R1/R2 schema, status, CAS or error-taxonomy change was introduced.

### F4 — closed: bounded R3 LeaseSession protocol reopen accepted

Owner: R3 Operation Worker contract / Architecture acceptance

The accepted S1a contract defines `RecoveryPort` as an in-process composition port, not an R3 public
protocol, and lists the need for R3 public protocol widening as a reopen condition
([p4-r5-s1a-handoff.md:52-55](/root/gateway-data-management-system/docs/backend-vnext/refactoring/formal/plans/p4-r5-s1a-handoff.md:52)).
[P4-R5-R3 Recovery-Release Reopen](p4-r5-r3-recovery-release-reopen.md) now explicitly exercises and
accepts that condition for the single bounded `publish_recovery_release()` primitive. The acceptance
freezes existing `RUNNING` release transitions, live-lease/version fencing, fresh transaction and
`OperationLifecycleActions` ownership. It rejects additional protocol methods, `RecoveryPort`
promotion, application runtime imports and R1/R2 changes. The S1a and R3-S1b lineage records point to
the accepted reopen. The implemented surface stays within those bounds.

## 4. Evidence and scope

Sealed evidence reread:

```text
source/test tree hash -> 2fcb0e05217590b09a552e545a196847d76e50c260fa2229dca6335da1e02e4d
git diff --check -> pass
F1 worker takeover regression -> 1 passed; original identity and submit_count == 1
F2 reconcile_pending_session_exhausted -> 1 passed; MANUAL_RECOVERY
contract/architecture/recovery focused -> 154 passed, 11 deselected
backend ruff/mypy -> pass; mypy 235 source files
shared_kernel/repository_contracts/repository_client/repository_service ruff/mypy -> pass
```

The recorded S1a-S3c gates and S4 focused counts remain historical regression evidence. F1-F4 are
closed by S5 remediation, the R3/architecture reopen and the independent checks above. S6 made no
source/test changes. No Dolt, Repository effect, benchmark, image, or container result is claimed.

## 5. Boundary

S7 is the only next named step and is not authorized by this record. Its entry still requires an
explicitly authorized commit/clean candidate, and its gate must rebuild the current HEAD backend image,
run the required container smoke and record exact source/image provenance. No P4-R6 or P5B work is
authorized.

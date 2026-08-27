# P4-R5-R3 Recovery-Release Contract Reopen

状态：**ACCEPTED — bounded R3 LeaseSession recovery-release mutation re-authorized**

日期：2026-08-27

Owner：R3 Operation Worker Runtime + Backend vNext Architecture Acceptance

上游：[P4-R5-S6 Independent Review](p4-r5-s6-independent-review.md)、
[P4-R5-S1a Handoff](p4-r5-s1a-handoff.md)、
[P4/R3-S1b Handoff](p4-r3-s1b-handoff.md)、
[P4-R5-S0 Independent Entry Acceptance](p4-r5-s0-entry-acceptance.md)

```yaml
disposition_kind: p4_r5_r3_recovery_release_reopen
step_id: P4-R5-R3-REOPEN
input_review: p4-r5-s6-independent-review.md
triggered_reopen_condition: R3 public protocol widening (P4-R5-S1a reopen_conditions)
finding_addressed: F4 R3 LeaseSession public protocol widened without owning-contract reopen
result: accepted
scope: docs_only_disposition
production_tests_modified: false
public_boundary_reopen: LeaseSession_publish_recovery_release_bounded_recovery_release_only
schema_or_status_changed: false
cas_semantics_changed: false
recovery_port_promoted_to_r3_protocol: false
application_runtime_dependency_introduced: false
next_step: P4-R5-S6
next_step_authorized: no
```

## 1. Disposition decision

S6 F4 records that S5 F3 remediation added `publish_recovery_release()` to the R3
`operations.worker.LeaseSession` protocol and made the concrete R3 lease session depend at runtime on
the R5 `RecoveryTransitionIntent` type, without documenting an owning-contract reopen. This
disposition explicitly reopens and re-accepts that boundary under a **bounded** recovery-release
scope.

**Path selected:** explicit R3/architecture contract reopen. The method remains on the R3
`LeaseSession` protocol and concrete implementation. No second adapter, no promotion of
`RecoveryPort` to an R3 public protocol, and no duplication of lease mutation outside
`LeaseSession`.

## 2. Accepted public surface

The only intentional R3 protocol widening is:

```text
LeaseSession.publish_recovery_release(
  intent: RecoveryTransitionIntent,
  *,
  diagnostic: OperationDiagnostic,
) -> ExecutorAcknowledgment
```

Implementation anchors:

- Protocol: [`worker.py:211-217`](../../../../vnext/backend/src/gateway_backend/operations/worker.py)
- Concrete: [`lease_session.py:271-276`](../../../../vnext/backend/src/gateway_backend/operations/lease_session.py)
- Composition caller: [`recovery.py:647-679`](../../../../vnext/backend/src/gateway_backend/operations/recovery.py) `finalize_handler_recovery`

## 3. Bounded acceptance matrix

| Dimension | Accepted | Explicitly rejected |
| --- | --- | --- |
| New surface | `publish_recovery_release` on R3 `LeaseSession` | Promoting `RecoveryPort` to R3 public protocol |
| Responsibility | Live-lease durable transition, lease clearing, optimistic-version / live-lease CAS fencing, per-session lock, fresh-transaction publication serialization | Copying lease mutation into bootstrap adapter or a second registry |
| Allowed transitions | `RUNNING -> RETRY_WAIT`; `RUNNING ->` existing terminal/manual targets (`FAILED`, `MANUAL_RECOVERY_REQUIRED`, and other already-authorized final terminals) | New statuses, new CAS semantics, schema/migration |
| Dependency direction | `RecoveryTransitionIntent` is an R5 read-only plan in `operations.recovery`; `worker.py` references it under `TYPE_CHECKING` only; `lease_session.py` references the R5 intent at runtime within `gateway_backend.operations` | R3 runtime import of `gateway_backend.application` or application recovery implementation |
| Invariants | Mutations continue through `OperationLifecycleActions` and `validate_step_transition`; existing lease token and optimistic-version guards remain authoritative | R1/R2 contract extension, principal, IPC, Repository effect, persisted recovery field |

`RecoveryPort` remains an in-process composition port as frozen in S0/S1a. Handler recovery
composition may call `publish_recovery_release` on the `lease_session` instance passed into
`RecoveryPort.recover`, but `RecoveryPort` itself is **not** added to the R3 worker protocol
surface.

## 4. Provenance

| Source | Role |
| --- | --- |
| [P4-R5-S1a Handoff](p4-r5-s1a-handoff.md) `reopen_conditions` | Named R3 public protocol widening as a stop/reopen trigger |
| [P4-R5-S6 Independent Review](p4-r5-s6-independent-review.md) F4 | Independent finding that S5 closed F3 without reopen provenance |
| [P4-R5-S0 Entry Acceptance](p4-r5-s0-entry-acceptance.md) | R3 owns lease/session/publication serialization; R5 owns recovery policy |
| [P4/R3-S1b Handoff](p4-r3-s1b-handoff.md) | Original LeaseSession mutation model; recovery-release is a controlled post-S1b extension |

This reopen does not retroactively change the sealed S1b or S1a implementation scope at their
validation time. It records lineage and re-authorizes the additional mutation primitive required
for R5 claim-path recovery release.

## 5. Reopen triggers

Stop and reopen the owning R3/architecture contract before any further work if any of the following
become necessary:

- additional R3 `LeaseSession` protocol methods beyond the bounded recovery-release primitive;
- promoting `RecoveryPort`, handler recovery callbacks, or R5 policy types to R3 public protocols;
- R3 runtime dependency on `gateway_backend.application` recovery implementation;
- R1/R2 schema, status, CAS, or shared error-taxonomy change to support recovery release;
- second registry, persisted recovery field, principal, IPC, sidecar, or Repository effect.

## 6. Verification applicability

This disposition is docs-only. No Dockerfile, dependency, Compose, entrypoint, deployment, or
container boundary is changed; container rebuild remains deferred to S7 per the S5 handoff.

The existing candidate tree already implements the accepted surface. Closure of F4 requires the S5
handoff to record this reopen and sealed evidence to remain green. Independent S6 re-review is
still required and is not authorized by this document.

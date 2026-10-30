# P4-R5 Retry, Takeover and Effect Recovery Design

状态：**ACCEPTED — S7 module gate complete; P4-R6-S0 discussion only**

日期：2026-08-26

Owner：Operation Runtime + Application Recovery owner

上游：[P4/R4 JobDefinition and Checkpoint Handoff](p4-r4-jobdefinition-checkpoint-handoff.md)、
[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)

默认入口：[P4 Active Context Index](p4-active-context-index.md)

本文固化 P4-R5 设计讨论中已确认的 retry、expired-lease takeover、external-effect
reconcile 和 operator recovery 边界。它不取代 R1/R2/R3/R4 contract，也不授权 Python、
tests、Repository effect 或 P5 implementation。

## 1. Entry identity and authorization boundary

```yaml
design_kind: p4_r5_retry_takeover_effect_recovery
input_validated_code_sha: d1d929dcee3b0620b649a248079d846dfbe7aba1
input_documentation_head: 895deeee80507e351ca7d97dc0e9e306712e8d72
validated_source_tree: sha256:76bbf7eef1ac26eb814d5ad5be6a86fec06a6850c42ac7a445b0b2fe93270de6
source_tree_changed_since_r4: no
p4_r4_exit: pass
p4_r5_entry_discussion: converged
p4_r5_s0_acceptance: not_run
p4_r5_implementation_authorized: no
p5b_real_repository_effect_authorized: no
schema_or_status_change_authorized: no
```

The R4 code candidate remains the validated source tip. The current HEAD after R4 is a
documentation-only descendant; any source, test, build-input or deployment change invalidates
this identity and requires a new provenance check.

## 2. Objective and users

R5 provides the smallest recovery policy that lets a worker safely continue a durable Step after
crash, lease expiry, duplicate delivery or an uncertain external outcome. Direct consumers are:

- R3 worker/runtime, which owns claim, lease, heartbeat, session and CAS publication;
- application JobDefinition owner, which owns checkpoint interpretation and effect-aware handler
  behavior;
- P5B, which later binds the real Repository client/effect journey;
- a future protected operator path, wired by P5 rather than by R5.

R5 does not explain Workspace, Submission, Archive, business finalize, Repository commit/ref
authority or global readiness.

## 3. Owner split and dependency direction

```text
R5 policy
  owns: retry classification, attempt/backoff budget, expired-lease disposition,
        takeover decision, reconcile scheduling and manual-recovery authorization boundary

R3 runtime
  owns: worker identity, lease/session fencing, scheduler claim, heartbeat, drain and CAS write

R4/application
  owns: immutable JobDefinition recovery capability, checkpoint decoding, request identity,
        handler recovery path and typed application recovery outcome

Repository Service / P5B
  owns: real Repository operation, request fingerprint, commit/ref evidence and production effect
```

R5 consumes the existing `(job_kind, step_name)` registry. It may extend the immutable
`JobDefinition` descriptor with a non-persisted `recovery_capability`, but it must not create a
second registry or make Operations import application implementations.

## 4. Recovery contract

The following are proposed in-process contracts; none are persisted as new R1/R2 fields:

```text
RecoveryCapability:
  PURE_RECOMPUTE | EXTERNAL_EFFECT | NON_RETRYABLE

RecoveryDecision:
  NO_ACTION | MOVE_TO_RETRY_WAIT | CLAIM_FOR_RECONCILE |
  MARK_MANUAL_RECOVERY | BLOCK_STARTUP_RETRYABLE | BLOCK_STARTUP_FATAL

RecoveryOutcome:
  PUBLISHED | RETRYABLE_FAILURE | PERMANENT_FAILURE |
  RECONCILE_PENDING | MANUAL_RECOVERY | CANCELLED
```

The recovery hook is a bounded, read-only decision function over fresh Operation/Step records.
The runtime applies its decision in a separate write UoW using the existing transition guard,
write precondition and SQLite CAS. It must not perform artifact, network, handler or sleep work
inside a read transaction.

The existing handler remains the recovery executor. R5 does not parse application payload or
checkpoint bytes. An external-effect handler must inspect its checkpoint and:

- reuse the original idempotency key before request acceptance;
- poll only the original operation identity after request acceptance;
- count a confirmed identity or request-fingerprint mismatch as a reconcile failure; do not
  treat it as a healthy wait;
- never generate a new key during takeover or reconcile.

## 5. State and transition policy

```text
safe retry:
  RUNNING -> RETRY_WAIT -> RUNNING

external unknown:
  RUNNING -> RETRY_WAIT (reconcile session) -> SUCCEEDED | FAILED | MANUAL_RECOVERY_REQUIRED

unreadable checkpoint/artifact:
  RUNNING/RETRY_WAIT -> MANUAL_RECOVERY_REQUIRED

confirmed Repository identity/fingerprint disagreement:
  RUNNING -> RETRY_WAIT (counted reconcile) -> MANUAL_RECOVERY_REQUIRED when exhausted
```

Operation remains `RUNNING` while its active Step is `RETRY_WAIT`; R1 has no operation-level
`RETRY_WAIT`. A Step entering `RUNNING` gets a new worker/token and increments `attempt_count`.
The original `started_at` remains unchanged. An expired worker cannot replace a live token with a
direct `RUNNING -> RUNNING` mutation.

Step retry is independent per step. A succeeded Step is immutable and is never rolled back or
re-executed. Successor publication remains R4's static single-successor/terminal policy.

## 6. Failure matrix and budgets

| Situation | Default disposition |
|---|---|
| deterministic pure compute failure with a valid checkpoint | retry until three sessions, then `FAILED` |
| external request not accepted | retry with the same idempotency key |
| request accepted or outcome unknown | reconcile only; never blind replay |
| Repository identity or request-fingerprint mismatch | count as reconcile failure; never healthy wait |
| 3 个恢复会话用尽 | `MANUAL_RECOVERY_REQUIRED`, occupancy retained |
| checkpoint/artifact unreadable | immediate manual recovery; do not recreate bytes |
| explicit application permanent failure | `FAILED` |
| unclassified executor failure | manual recovery, fail closed |
| cancel before irreversible effect | `CANCELLED` |
| cancel after request/effect boundary | continue reconcile; no synthetic `CANCELLED` |

Defaults are three counted recovery sessions per Step, backoff `1s -> 2s -> 4s` capped at `10s`,
bounded jitter with injectable clock/wait/jitter sources, and a 60-second maximum poll duration
within one active reconcile session. A lease loss/crash, transport error, unknown result, or
identity/request-fingerprint disagreement consumes a session. A Submit `await_import_result` poll
that successfully reads the matching Repository operation and sees `QUEUED` or `RUNNING` records
that health observation in the existing Step diagnostic and reuses the existing checkpoint when
handing off its lease; it does not consume a session, and reclaim preserves `attempt_count`. Its
total wait is bounded by `started_at` plus
Repository Service `import_timeout_seconds + server_start_timeout_seconds` (currently 3630 seconds).
Exceeding that bound enters `MANUAL_RECOVERY_REQUIRED` with `r5.wait_upper_bound_exceeded`.
This count-free requeue is selected only by Submit after the matching healthy observation; other
safe-handoff callers retain their existing behavior. Polls without a successful health observation
retain the normal three-session rule. Submit does not persist `reconcile_started_at`.

## 7. Identity, diagnostics and operator recovery

The original request identity is immutable and must be checked against a fingerprint containing:

```text
repository_id, artifact_ref/size/digest, target_ref, expected_commit,
verification_policy, unknown_type_policy, idempotency_key
```

R5 uses namespaced bounded diagnostics only:

```text
r5.lease_expired
r5.retry_scheduled
r5.reconcile_started
r5.reconcile_timeout
r5.manual_recovery_required
r5.recovery_authorized
r5.operator_recovery_session
r5.healthy_wait_handoff
r5.healthy_wait_handoff_operator
r5.wait_upper_bound_exceeded
```

No shared error registry or new stable R3 event enum is introduced. The internal recovery port
accepts only `RESUME_RECONCILE`, `RETRY_FROM_CHECKPOINT` and `ABORT_CONFIRMED_FAILURE`, each with
operation/step identity, expected optimistic version and operator reason. P5 owns HTTP and
authorization wiring; R5 adds no principal.

`RESUME_RECONCILE` and `RETRY_FROM_CHECKPOINT` move a manual Step to the existing claimable
`RETRY_WAIT` state, move its Operation to `RUNNING`, clear lease ownership, and set immediate
eligibility. The next worker claim consumes exactly one session. The existing diagnostic field
carries the authorization through that claim and any confirmed healthy-wait handoff; a counted
failure in that authorized session returns the pair to `MANUAL_RECOVERY_REQUIRED`. A restart before
claim leaves the due `RETRY_WAIT` claimable and does not spend a session. If the claimed session's
lease expires, startup marks it manual and remains ready.

## 8. Lifecycle, startup and deployment

Startup performs a bounded classification pass before readiness. It may move expired safe-retry
records to `RETRY_WAIT`, schedule external reconcile, or mark irrecoverable records manual. It
does not perform unbounded Repository polling before `READY`; manual records do not block readiness.
After an operator resume/retry accepted but before the next claim, the Step is already due
`RETRY_WAIT`, so startup leaves it claimable and does not apply the exhausted-session rule. If that
authorized session was claimed and its lease later expires, startup marks it manual but remains
`READY`.

Drain stops new claims, lets the current executor heartbeat/checkpoint or safely hand off, and
does not convert drain into cancellation. A bounded Submit Repository poll returns its last
successful `QUEUED`/`RUNNING` observation at the 60-second poll deadline, allowing drain or
SIGTERM to finish through that poll's safe handoff. The deployment remains single-host,
single-worker, SQLite/WAL. R5's final worker/runtime candidate requires a current-HEAD backend
image rebuild and container smoke; a stub result is never production Repository validation.

## 9. Reopen conditions and exclusions

Reopen R1/R2 if implementation needs a new persisted field, status, transition, schema, migration,
CAS or error taxonomy. Reopen R3 if it needs direct token swap, a second fencing service, changed
drain/signal semantics or multiple executors. Reopen R4 if recovery requires a second registry,
generic checkpoint/evidence format or changes READY/checkpoint authority. Reopen P5B for real
Repository effect, T1/T3, HTTP/global readiness, or business occupancy semantics.

R5 does not add HA, arbitrary DAG, dynamic plugins, cleanup/GC, generic external-effect journals,
sidecars, new IPC or a new security boundary.

## 10. Design acceptance criteria

- no new idempotency key is generated after request acceptance;
- expired takeover is fenced by optimistic version, worker identity and lease token;
- pure compute resumes from checkpoint and respects the three-session budget;
- external unknown outcome only reuses the original operation identity;
- unreadable checkpoint/artifact cannot produce READY or a fabricated terminal result;
- manual recovery retains occupancy and requires explicit authorization;
- duplicate delivery, stale writer, crash, cancel, drain and successor cases have one authoritative
  contract-level test owner;
- R5 tests and static gates are separated from P5B real Repository effect evidence.


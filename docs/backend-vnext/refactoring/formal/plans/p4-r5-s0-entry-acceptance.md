# P4-R5-S0 Independent Entry Acceptance

状态：**PASS — DESIGN AND EXECUTION PLAN ACCEPTED; S1a AUTHORIZED ONLY**

日期：2026-08-26

Owner：Backend vNext Architecture Acceptance（independent acceptance context）

上游：[P4/R4 JobDefinition and Checkpoint Handoff](p4-r4-jobdefinition-checkpoint-handoff.md)、
[P4-R5-S0 Entry Brief](p4-r5-s0-entry-brief.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)

## 1. Acceptance identity

```yaml
acceptance_kind: p4_r5_s0
step_id: P4-R5-S0
input_handoff_sha: 895deeee80507e351ca7d97dc0e9e306712e8d72
input_validated_code_sha: d1d929dcee3b0620b649a248079d846dfbe7aba1
reviewed_base_sha: 653b127598aca5d0ed73374723e45a2ccaad43d2
reviewed_candidate_document_set_sha256: 1c00f80e1f3b33ffdcf45aef049775678aaad068e3347d8772286831623afcd2
candidate_acceptance_record_excluded_from_hash: true
candidate_worktree: documentation_only_candidate_on_clean_r5_sealed_tip
source_code_changed: false
tests_changed: false
dependencies_changed: false
deployment_changed: false
r4_validated_code_sha: d1d929dcee3b0620b649a248079d846dfbe7aba1
r4_validated_source_tree: sha256:76bbf7eef1ac26eb814d5ad5be6a86fec06a6850c42ac7a445b0b2fe93270de6
r4_image_valid_only_for_source_sha: d1d929dcee3b0620b649a248079d846dfbe7aba1
r5_documentation_seal: be1b70c
r5_normative_document_set_hash: 1c00f80e1f3b33ffdcf45aef049775678aaad068e3347d8772286831623afcd2
p4_r4_exit: pass
p4_r5_design: accepted
p4_r5_execution_plan: accepted
p4_r5_s0: accepted
p4_r5_s1a_authorized: yes
p4_r5_implementation_authorized: s1a_only
p5b_real_repository_effect_authorized: no
p5_implementation_authorized: no
schema_or_status_change_authorized: no
```

The R4 handoff remains the code authority: `d1d929d` is an ancestor of the reviewed base and the
committed source/test diff from that tip is empty. The inherited R4 source-tree identity and image
provenance therefore remain valid as R4 evidence; this S0 acceptance introduces no source, test,
dependency, deployment or image claim. The R5 normative document seal is the docs-only commit
`be1b70c`; the fixed two-file semantic hash was recomputed as `1c00f80e...2286831623afcd2`.
The acceptance record, Active Context and formal README are status/retrieval wiring and are not
included in that semantic hash.

## 2. Independent acceptance decisions

### 2.1 Owner and dependency direction — PASS

R1 continues to own Operation/Step records, statuses, transitions and immutable identity. R2 owns
the existing SQLite transaction, CAS and persisted row shape. R3 owns scheduler claim, lease/session,
heartbeat, drain and publication serialization. R4/application owns immutable JobDefinition recovery
capability, checkpoint decoding and handler recovery. R5 owns retry classification, budgets, expired
lease disposition, takeover/reconcile policy and the internal authorization boundary. P5B/Repository
later owns the real effect, request fingerprint and commit/ref evidence; P5 owns business T1/T3,
HTTP/global readiness and the operator route. No owner is widened by S0.

### 2.2 Existing state and recovery boundary — PASS

The proposed recovery decisions fit existing `StepRecord.retry_not_before`, attempt/lease fields,
`repository_operation_id`, checkpoint reference and transition/CAS guards. Operation remains `RUNNING`
while a Step is `RETRY_WAIT`; takeover is guarded and never a direct `RUNNING -> RUNNING` token swap.
No new persisted field, status, schema, migration, CAS contract, shared error taxonomy, registry,
principal, IPC, sidecar or generic evidence journal is required. Blind replay and new idempotency keys
after request acceptance remain forbidden; unreadable checkpoint/request artifacts are not recreated.

### 2.3 S1a contract shape — PASS

S1a must freeze this non-persisted, in-process shape before S1b/S2 work:

```text
RecoveryCapability:
  PURE_RECOMPUTE | EXTERNAL_EFFECT | NON_RETRYABLE

RecoveryDecision:
  disposition: NO_ACTION | MOVE_TO_RETRY_WAIT | CLAIM_FOR_RECONCILE |
               MARK_MANUAL_RECOVERY | BLOCK_STARTUP_RETRYABLE | BLOCK_STARTUP_FATAL
  diagnostic_code: bounded namespaced ASCII code
  retry_not_before: UTC datetime | null
  reason: bounded diagnostic message

RecoveryOutcome:
  disposition: PUBLISHED | RETRYABLE_FAILURE | PERMANENT_FAILURE |
               RECONCILE_PENDING | MANUAL_RECOVERY | CANCELLED
  diagnostic_code: bounded namespaced ASCII code | null
  reason: bounded diagnostic message | null

RecoveryPort.recover(
  operation: OperationRecord,
  step: StepRecord,
  control: ExecutionControl,
  lease_session: LeaseSession,
) -> RecoveryOutcome
```

`RecoveryPort` is a composition port, not an HTTP API, persisted registry or R3 public protocol.
Decisions are bounded/read-only and carry no payload, artifact bytes, SQL, network client or callable.
R5 maps the single application outcome to existing R1/R2 transitions and does not accept an arbitrary
handler-provided durable record.

### 2.4 Steps, markers and review isolation — PASS

| Step | Context / owner | Scope and gate |
| --- | --- | --- |
| S0 | mandatory new conversation / Architecture acceptance | docs-only provenance, owner/reopen and link review; no Python gate |
| S1a | new conversation / R5 + Application | recovery capability/decision/outcome and reconcile port; focused unit, backend unit subset, ruff/mypy |
| S1b | new conversation / R5 | retry/failure matrix, budgets, diagnostics and operator command contract; pure unit/static |
| S2a | new conversation / R5 + R3 | expired lease classification, retry scheduling and CAS takeover; integration + serial + focused unit |
| S2b | new conversation / R5 + Application | original identity reconcile adapter and deterministic stub; non-serial integration + focused unit |
| S2c | new conversation / R5 | internal authorized recovery commands and CAS; focused unit + SQLite integration |
| S3a | new conversation / Application | pure-compute retry/takeover consumer; unit/integration and serial process cases |
| S3b | new conversation / Application + R5 | external-effect unknown/reconcile/cancel consumer; unit/integration and serial cases as applicable |
| S3c | new conversation / R5 | single cross-boundary crash/duplicate/budget/manual matrix; shared parameter tables |
| S4 | mandatory new conversation / independent focused reviewer | complete diff and owner-boundary review |
| S5 | conditional new conversation / finding owner | finding-scoped remediation only |
| S6 | mandatory new conversation / independent reviewer | sealed evidence reread; no implementation |
| S7 | new conversation / R5 owner | current-HEAD gates, image provenance, worker smoke and handoff |

Marker policy is explicit: pure policy/contract/fake-clock tests are `unit`; on-disk or stub
reconciliation is `integration`; fixed timeout, crash, signal or restart boundaries are `serial`.
R5 does not run Dolt or Repository Service integration. Five-package `ruff`/`mypy` is a S7 gate,
not an S0 gate, and same-shape faults use shared parameter tables with one contract-level owner.

### 2.5 Container applicability and review gates — PASS

S0 is documentation-only: `container_rebuild_required: no`, `container_gate: not_applicable_for_s0`,
and no Python, Dolt, Repository or benchmark command is required. R4's image remains provenance
for unchanged `d1d929d`; it is not current-HEAD R5 evidence. R5 source/runtime work may defer
intermediate builds, but S7 must rebuild the current HEAD backend image and run the synthetic worker
container smoke. Dockerfile, dependency, entrypoint, Compose, health/readiness, process harness,
mount, UID/GID or other container-only changes trigger an earlier rebuild.

## 3. Stop and reopen conditions

Stop the named step and reopen the owning contract for any of the following: R1/R2 schema, status,
CAS, migration or error-taxonomy change; direct `RUNNING -> RUNNING` token replacement; blind replay
or a new key after request acceptance; real Repository/Dolt effect; a new principal, IPC, sidecar,
second registry or generic evidence/cleanup state machine; a marker unable to represent a new
timing/process boundary; or a requirement that changes R4 checkpoint/READY authority, R3 fencing/
drain semantics, or P5B/P5 business/effect ownership. Findings are recorded by contract behavior,
not round or finding number.

## 4. Verification and applicability

```text
git status --short --branch
  -> clean before this acceptance edit; branch HEAD=653b127
git merge-base --is-ancestor d1d929dcee3b0620b649a248079d846dfbe7aba1 HEAD
  -> pass
git diff --name-only d1d929dcee3b0620b649a248079d846dfbe7aba1..HEAD -- vnext/backend/src vnext/backend/tests
  -> empty
git diff --name-only -- vnext/backend/src vnext/backend/tests
  -> empty
sha256sum docs/backend-vnext/refactoring/formal/plans/p4-r5-retry-takeover-effect-recovery-design.md docs/backend-vnext/refactoring/formal/plans/p4-r5-retry-takeover-effect-recovery-execution-plan.md | sha256sum
  -> 1c00f80e1f3b33ffdcf45aef049775678aaad068e3347d8772286831623afcd2
git merge-base --is-ancestor be1b70c HEAD
  -> pass; sealed R5 docs commit is an ancestor
git diff --check
  -> pass before this acceptance edit
```

```yaml
container_rebuild_required: no
container_reason: docs_only_p4_r5_s0_acceptance
last_verified_image_revision: sha256:443216f4a7e098abf3cd85a908e571d1236ed0a656913b96598d8bee4488ed5b
container_gate: not_applicable_for_s0
python_tests: not_run_by_s0_plan
five_package_static: not_run_by_s0_plan
benchmark: not_applicable_no_performance_claim
findings: []
reopen_conditions: []
```

## 5. Decision and next boundary

`p4_r5_s0: accepted` confirms that the R5 design, detailed execution plan, owner split, S1a shape,
step cards, markers, review isolation, container applicability and stop/reopen conditions are
internally consistent. `p4_r5_s1a_authorized: yes` is recorded only as the next-step authorization;
this conversation did not begin S1a and changed no source or tests.

The next action is a separate new conversation for P4-R5-S1a, limited to the plan card's allowed
application contract paths and handoff. S1b, S2a and all P5B/Repository work remain unauthorized
until their preceding handoffs and gates pass.

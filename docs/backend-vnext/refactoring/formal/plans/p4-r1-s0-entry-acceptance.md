# P4/R1-S0 Independent Entry Acceptance

状态：**PASS**（独立 entry acceptance；仅授权 R1-S1a）

日期：2026-08-23

Owner：Backend vNext Architecture Acceptance（independent acceptance context）

上游：[P4 Entry Acceptance Candidate](p4-entry-acceptance.md)、[P4-R1-S0 Entry Brief](p4-r1-s0-entry-brief.md)、[P4-R1 Runtime Contract and State Detailed Execution Plan](p4-r1-runtime-contract-state-execution-plan.md)

```yaml
acceptance_kind: p4_r1_s0
reviewed_candidate_sha: a2da77f2332f876a575fdef2605eea13ed3293fb
reviewed_candidate_document_set_sha256: efd7ae90840a3653858261667c7056302b84b48a671b7b19629c2e7bb802b264
candidate_worktree: clean
p4_entry_acceptance: pass
p4_r1_s0: accepted
r1_s1a_authorized: yes
accepted_contract_source: p4-r1-runtime-contract-state-execution-plan.md@a2da77f2332f876a575fdef2605eea13ed3293fb#2
accepted_status_semantics: detailed plan §2.5 matrix and attention-state rules
accepted_public_surface: detailed plan §2.2 staged exports and signatures
accepted_document_keys: detailed plan §2.4 exact closed Operation/Step key sets
accepted_budgets: detailed plan §2.6 conservative bounded defaults
open_findings: []
deferred_items:
  - R1 implementation remains limited to the staged S1a-S2b/S3a-S3b steps; no P4-wide implementation authorization.
  - SQLite/WAL schema, CAS transaction implementation, worker lifecycle, JobDefinition registry and Repository effect remain owned by R2-R5/P5 steps.
  - Lease/retry/retention numeric parameters not required by S1a remain deferred to their owning R2/R5/P5 entry decisions.
next_step: P4-R1-S1a
next_step_authorized: yes
```

## 1. Independent decisions

Both gates were reviewed separately. `p4_entry_acceptance: pass` confirms that Phase 4 has a
sealed, internally consistent design and execution boundary. `p4_r1_s0: accepted` confirms the
Operations contract/state package can enter S1a without first changing an owning contract or ADR.
The acceptance candidate remains the sealed source snapshot; this record supplies the independent
decision and current reviewed-tree provenance.

## 2. Accepted R1 snapshot

### Public surface and placement

- The sole physical package is `vnext/backend/src/gateway_backend/operations/`; no
  `backend_vnext` Python package or compatibility alias is permitted.
- S1a exports only `OPERATION_RUNTIME_CONTRACT_VERSION`, `OperationStatus`, `StepStatus`, and
  frozen/slotted `JobStepKey` through an explicit `__all__`. `operation_kind` is absent from fields,
  aliases, exports and registry identity.
- The staged publication order is accepted: S1a identity, S1b records/parsers, and S2b
  preconditions/dispositions/guards. R1 does not define handlers, SQLite records, worker results or
  Repository DTOs.

### Status and transition semantics

- Operation values are `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `SUPERSEDED`, and
  `MANUAL_RECOVERY_REQUIRED`; Step values are `PENDING`, `RUNNING`, `RETRY_WAIT`, `SUCCEEDED`,
  `FAILED`, `CANCELLED`, and `MANUAL_RECOVERY_REQUIRED`, with exact uppercase persisted spelling.
- `SUCCEEDED | FAILED | CANCELLED | SUPERSEDED` are final terminal states. `MANUAL_RECOVERY_REQUIRED`
  is an attention state: it is not automatically claimable and does not release business occupancy.
  Only authorized recovery may produce an accepted `RUNNING` or permitted final state.
- The matrix and cross-field rules in the detailed plan are accepted, including lease identity only
  on RUNNING Steps, diagnostics on failure/attention states, completion timestamps on final states,
  monotonic optimistic versions, immutable identity/envelope fields, append-only artifact refs, and
  exact same-record terminal idempotency.

### Persisted documents and budgets

- Operation and Step documents are closed objects with the exact key sets in detailed plan §2.4;
  parsers reject unknown keys, discriminator/version/type mismatches, malformed nested refs and
  non-canonical timestamps. `job_payload` and `job_payload_ref` are mutually exclusive with exactly
  one non-null; inline payloads are bounded JSON objects and canonical bytes are the record form.
- `BusinessReference`, diagnostics and ArtifactRef items retain their owner-defined shapes. Runtime
  treats payload and reference values as opaque and never stores callables, paths, PIDs or
  provider-private objects.
- Accepted conservative limits are those in §2.6: bounded opaque IDs (1..255 UTF-8 bytes), registry
  names (1..128 ASCII), bounded diagnostic code/message, 64 KiB inline payload, depth 32,
  aggregate JSON members/elements 4096, 16 KiB strings, at most 64 business/artifact refs, and
  non-negative I-JSON-safe counters.

## 3. Boundary and architecture checks

| Check | Result | Evidence |
| --- | --- | --- |
| Candidate revision and document-set identity | pass | Reviewed `a2da77f`; recomputed document-set digest equals sealed `efd7ae...` |
| Worktree and whitespace | pass | Clean worktree; `git diff --check` passes |
| Physical package and dependency direction | pass | Existing `gateway_backend` root; architecture checker forbids app/settings/infrastructure/capability-private/Repository imports |
| Contract ownership | pass | Operation Lifecycle, External Effect and Recovery, and Contract Taxonomy assign Operation/Step semantics to Operations and retain Repository effect authority in Repository Service |
| R1 scope | pass | No SQLite, worker, HTTP, P5 business entity, Repository wire or deployment changes are authorized |
| Applicable steps and handoffs | pass | S0, S1a, S1b, S2a, S2b, S3a, S3b, S4 and S7 required; S5/S6 conditional exactly as brief/plan state |
| Static/tests/container applicability | not_applicable | Documentation-only acceptance; no source/test/runtime boundary changed, so focused tests, five-package static checks, container rebuild and benchmark are not rerun here |

## 4. Deferred and reopen conditions

The deferred register in the P4 design and detailed plan remains authoritative. Reopen before S1a
or during R1 if the implementation needs a second package root, a new security/deployment
principal, business payload interpretation, a generic evidence taxonomy, Repository wire/CAS
ownership, a SQLite/worker dependency, or any state/field that cannot satisfy the accepted closed
document and recovery barriers. Such a change requires the owning contract/ADR decision; it cannot
be introduced by an implementation step.

`p4_implementation_authorized: r1_s1a_only` is intentionally narrower than P4 implementation
authorization. No R1 step beyond S1a is authorized until its preceding handoff is `pass` and names
the next step.

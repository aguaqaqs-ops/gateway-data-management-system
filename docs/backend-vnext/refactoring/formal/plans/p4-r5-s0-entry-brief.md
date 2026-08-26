# P4-R5-S0 Entry Brief: Retry, Takeover and Effect Recovery

状态：**READY FOR P4-R5-S0 DOCUMENT REVIEW — IMPLEMENTATION NOT AUTHORIZED**

日期：2026-08-26

Owner：Operation Runtime + Application Recovery owner

上游：[P4/R4 JobDefinition and Checkpoint Handoff](p4-r4-jobdefinition-checkpoint-handoff.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4 Durable Operation Runtime Execution Plan](p4-durable-operation-runtime-execution-plan.md)

默认入口：[P4 Active Context Index](p4-active-context-index.md)

## 1. Entry identity

```yaml
step_id: P4-R5-S0
input_handoff_sha: 895deeee80507e351ca7d97dc0e9e306712e8d72
input_validated_code_sha: d1d929dcee3b0620b649a248079d846dfbe7aba1
validated_source_tree: sha256:76bbf7eef1ac26eb814d5ad5be6a86fec06a6850c42ac7a445b0b2fe93270de6
candidate_documentation_sha: pending_r5_docs_only_seal_commit
candidate_worktree_at_gate: pending_clean_committed_docs_candidate
candidate_document_set_hash: pending_s0_recompute_excluding_acceptance_record
p4_r4_exit: pass
p4_r5_design_discussion: converged
p4_r5_s0_acceptance: not_run
p4_r5_implementation_authorized: no
p5b_real_repository_effect_authorized: no
schema_or_status_change_authorized: no
```

The input code candidate is R4's validated `d1d929d`; `895deee` is the last committed
documentation-only descendant before this R5 document set. Before S0 acceptance, the R5 design,
brief, execution plan, Active Context and formal README changes must be sealed in a docs-only commit.
S0 then recomputes the candidate documentation hash with the acceptance record excluded, records the
seal SHA, and verifies a clean committed worktree. No source/test/build-input drift is authorized.

## 2. Objective and accepted scope

S0 freezes the R5 owner split, recovery contract, state matrix, identity rules, budgets, operator
port, test truthfulness and execution-step boundary. R5 is a generic runtime recovery module; it
does not become a Repository Service client owner or a business finalize owner.

Accepted defaults:

- three recovery sessions per Step;
- `1s/2s/4s`, capped at `10s`, bounded injectable jitter;
- 60-second reconcile session;
- Step-level retry with Operation remaining `RUNNING`;
- no blind replay or new key after external request acceptance;
- no checkpoint/artifact recreation after an unreadable reference;
- internal recovery port only; P5 supplies HTTP/authorization later;
- no new schema, state, CAS, registry, principal, IPC or evidence state machine.

## 3. Owner split

```text
R5: recovery decision, retry/takeover/reconcile policy and authorization boundary
R3: scheduler, claim, lease/session, heartbeat, drain, CAS and publication serialization
R4/application: JobDefinition recovery capability, checkpoint decoding and handler recovery path
P5B/Repository: real effect, operation identity, request fingerprint and commit/ref evidence
P5: business T1/T3, HTTP/global readiness and operator route
```

## 4. S0 required checks

1. Read the R4 handoff, R1/R2/R3 handoffs, R4 design and this design document.
2. Verify that all R5 decisions fit existing `StepRecord.retry_not_before`, attempt/lease fields,
   `repository_operation_id`, checkpoint ref and existing transition/CAS guards.
3. Verify that R5 does not need a persisted field/status/schema/error-taxonomy extension.
4. Verify no second JobDefinition/recovery registry, new principal, IPC, sidecar or generic journal
   is required.
5. Freeze the detailed step split, allowed paths, markers, review contexts and container trigger.
6. Record current HEAD, validated code SHA, source tree identity and the fact that R4's image is
   valid only for the unchanged R4 source tree.
7. Seal the R5 document set in a docs-only commit and recompute `candidate_document_set_hash` with
   the S0 acceptance record excluded; a dirty worktree is not an accepted S0 candidate.

## 5. Exit and authorization

S0 acceptance may set `p4_r5_s0: accepted` and authorize S1a only after an independent acceptance
record verifies this brief, the design and the detailed execution plan. This entry brief alone does
not authorize Python/tests or P5B work.

Any finding requiring R1/R2/R3/R4 owner changes is a reopen, not an S1 implementation task.

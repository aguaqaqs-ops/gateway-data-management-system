# P4-R6-S0 Independent Entry Finding Disposition

状态：**REOPEN RESOLVED — remediation validated; independent S0 rereview accepted**

日期：2026-09-13

Owner：Backend vNext Architecture Acceptance + Operation Runtime Integration

上游：[P4-R6-S0 Entry Brief](p4-r6-s0-entry-brief.md)、
[P4-R6/R1 Registry-Name Contract Reopen](p4-r6-r1-registry-name-contract-reopen.md)、
[P4/R5 Retry, Takeover and Effect Recovery Handoff](p4-r5-retry-takeover-effect-recovery-handoff.md)

```yaml
step_id: P4-R6-S0-FINDING-DISPOSITION
reviewed_candidate_head: 7e8cea7b3454a8cfdd7c2ba880becee5c427a0de
reviewed_worktree: four_untracked_user_owned_P5_5B_documents_only
decision: reopen_resolved
scope: docs_only_finding_disposition
production_test_deployment_modified: false
findings:
  - id: P4-R6-S0-F1
    severity: P2
    owner: P4_R1_Operation_persisted_admission_contract
    disposition: accepted_bounded_contract_reopen
    closure: pass
  - id: P4-R6-S0-F2
    severity: P2
    owner: P4_worker_test_classification
    disposition: add_serial_to_fixed_timeout_worker_test
    closure: pass
p4_r6_s0_acceptance: accepted
p4_r6_implementation_authorized: no
p4_r6_exit: not_declared
p5b_implementation_authorized: no
next_step: issue_P4-R6-S1-S7_gate_execution_task
next_step_authorized: no
new_explicit_authorization_required: yes
```

## 1. Findings-first disposition

| Finding | Evidence | Disposition | Closure requirement |
| --- | --- | --- | --- |
| P4-R6-S0-F1: post-R5 registry-name acceptance changed | `operations/contracts.py` accepts `/`; R1 sealed pattern did not; P5 Preview uses `backend-vnext/preview` | Reopen R1 and accept `/` as an opaque namespace character; no path semantics, schema, migration, status/CAS or version change | Add direct positive/negative owner tests and revalidate dependent R2–R5 assumptions |
| P4-R6-S0-F2: fixed timeout owner lacks `serial` | `test_registered_key_reaches_ready_with_empty_queue` uses `Event.wait(timeout=5)` and `Thread.join(timeout=5)` under module-level `integration` only | Tests-only marker remediation | Add `@pytest.mark.serial`; run affected integration and serial owners |

F1 and F2 are now closed at the candidate-validation layer by the tests-only remediation and the
repeated independent review. The resulting acceptance is recorded in
[P4-R6-S0 Independent Entry Acceptance](p4-r6-s0-independent-entry-acceptance.md); it does not
authorize R6 implementation.

## 2. Delta disposition retained

The rest of the independent review remains valid:

- R1–R5 handoffs are reachable and all five validated code commits are candidate ancestors.
- The R5 digest reproduces as
  `sha256:2fcb0e05217590b09a552e545a196847d76e50c260fa2229dca6335da1e02e4d`;
  the old `911fe38d...` value is not provenance.
- `0fa2b897..d7cb5b9c` changes gate infrastructure, not backend P4 runtime source/tests.
- The current Preview composition, workspace schema component, settings, dependencies and Compose
  wiring are compatible P5 consumer/composition integration subject to P4 regression and fresh
  container provenance. They do not put Workspace/HTTP/PreviewResult or a real Repository Submit
  effect into R6.
- P5-5A `authoritative_runner=partial_pass_5a_scope`; its five repository-service parallel failures
  and eight Compose failures are not P4-R6 pass evidence.
- All eight Compose nodeids in the entry brief exist and are marked `integration + serial`.

## 3. R6 step and gate boundary after remediation

The repeated S0 acceptance passed. S1 is merged into S2/S3 because the synthetic, Repository-stub,
crash and admin-readback harnesses already exist. S2–S4, S6 and S7 remain required; S5 is
finding-conditional. The authoritative runner must execute without Compose ignores, and the final
candidate must rebuild backend/worker images and record exact source/image provenance.

No S1–S7 step is authorized by this disposition or the acceptance. The immediate next step is a
separately authorized P4-R6 S1–S7 gate-execution task using the frozen commands and provenance plan.

## 4. Verification applicability

This docs-only disposition runs no Python, static, Dolt, process, Docker, Compose or final gate.
Container evidence remains historical or prerequisite-only, and the required execution point remains
the final R6 candidate before S7. Markdown/link/fence/whitespace and Git identity checks are the only
applicable checks for this step.

# P4-R6-S0 Entry Brief: Acceptance and Integration Gate

状态：**DISCUSSION CONVERGED — INDEPENDENT ENTRY ACCEPTANCE REQUIRED; R6 IMPLEMENTATION NOT AUTHORIZED**

日期：2026-09-05

Owner：Backend vNext Architecture Acceptance + Operation Runtime Integration

上游：[P4/R5 Retry, Takeover and Effect Recovery Handoff](p4-r5-retry-takeover-effect-recovery-handoff.md)、
[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)、
[P4 Durable Operation Runtime Execution Plan](p4-durable-operation-runtime-execution-plan.md)、
[Implementation Stages §7 Phase 4](implementation-stages.md#7-phase-4durable-operation-runtime)

默认入口：[P4 Active Context Index](p4-active-context-index.md)

## 1. Entry identity and decision

```yaml
step_id: P4-R6-S0
entry_kind: p4_final_acceptance_and_integration_gate
discussion_head: d7cb5b9c2c55e8f8b0814520e9d95c7df0ad00a5
input_r5_validated_code_sha: 0fa2b897a75436b4319d4490bc97c54ced494783
input_r5_handoff_documentation_sha: 91e96c2262529d80504fa5cdc50fdd111f2fe323
input_r5_validated_source_tree: sha256:2fcb0e05217590b09a552e545a196847d76e50c260fa2229dca6335da1e02e4d
p4_r5_exit: pass
p4_r5_runtime_or_contract_drift_after_gate: false
current_head_cross_repository_gate_input_drift: true
current_head_container_gate: stale
r6_scope: p4_final_acceptance_integration_container_and_provenance
workspace_http_global_readiness_in_scope: false
real_repository_dolt_effect_in_scope: false
p4_r6_s0_discussion: converged
p4_r6_s0_acceptance: pending_independent_review
p4_r6_implementation_authorized: no
p5b_real_repository_effect_authorized: no
p5_implementation_authorized: no
next_step: P4-R6-S0-independent-entry-acceptance
next_step_authorized: yes
```

The prerequisites to enter R6-S0 discussion are met. R1-R5 have module handoffs, R5 is closed at
candidate `0fa2b897`, and the R5 Python source/test tree remains byte-identical at the discussion
HEAD. The R5 S7 post-seal correction makes its declared tree identity reproducible without changing
the tested code or image identity.

This brief does not accept S0 and does not authorize R6 source, test, image, deployment or P5 work.
An independent entry acceptance must verify this scope, the current-HEAD delta inventory, the exact
gate plan and the provenance rules before any later R6 step is authorized.

## 2. Scope and owner boundary

R6 is the final P4 acceptance and integration gate. It owns aggregation and current-HEAD validation
of the runtime delivered by R1-R5:

- synthetic pure-compute and external-effect-stub worker composition;
- process crash, lease takeover, duplicate delivery, cancellation, drain/restart, checkpoint
  corruption and unknown-outcome behavior;
- focused, unit, integration and serial test ownership and result aggregation;
- five-package ruff/mypy evidence;
- applicable backend image, process smoke and affected Compose/container gates;
- exact tested tip, source-tree/image provenance, deferred register and P5 entry prerequisites;
- independent review and P4 exit decision.

R6 does not own Workspace, HTTP routes, PreviewResult, Submit/Finalize, business occupancy/T1/T3,
production Repository/Dolt effects, global readiness, HA, an external durable DB or deployment of a
P5 journey. Those remain P5/P5B or future deployment scope. R6 may verify that P4's worker lifecycle
and existing readiness contracts compose correctly, but it must not create those deferred product
surfaces to make the gate pass.

## 3. Current-HEAD delta and provenance disposition

The discussion input was clean HEAD `d7cb5b9c` at the start of this docs-only audit. Compared with
the R5 validated code `0fa2b897`:

```text
vnext/backend + vnext/shared_kernel + vnext/rust build inputs -> no diff
vnext/backend/src + vnext/backend/tests Python files          -> no diff
authoritative test runner / Compose harness / test Dockerfile -> changed
R5 reproducible Python source/test tree digest                -> 2fcb0e05...1e02e4d
R5 historical image                                          -> a2db693e...c6b3d95
current-HEAD container gate                                   -> stale
```

The later changes are test execution and container-harness work, not an R5 semantic change, so they
do not reopen S6 or the R5 contract. They do invalidate any statement that the R5 ancestor image is
the current-HEAD gate. R6 must inventory the exact affected images and Compose nodeids during S0,
then rebuild and run them on its final candidate in accordance with the repository testing policy.

## 4. Proposed R6 step and review boundary

The P4 execution plan remains authoritative. S0 acceptance must confirm the following bounded split
before authorizing work:

| Step | Purpose | Authorization boundary |
| --- | --- | --- |
| S0 | Freeze current HEAD, delta inventory, test ownership, container applicability and provenance | Docs/inspection only; independent acceptance required |
| S1 | Assemble or confirm the existing synthetic worker, crash, Repository stub and admin-readback harnesses | No production Repository effect or business route |
| S2 | Run focused/unit/integration/serial gates and five-package static checks; add only demonstrated regression coverage | No new mechanism without a reproduced gap |
| S3 | Run the P4 fault matrix across crash, takeover, duplicate, cancel, drain/restart and corruption boundaries | Contract behavior, not internal-step probes |
| S4 | Independent review of owners, CAS/transaction boundaries, recovery, test ownership and deferred register | Findings first; no implementation in review context |
| S5 | Finding-scoped remediation and retest when required | Reopen owning R1-R5 contract for semantic changes |
| S6 | Rebuild current-HEAD images and run applicable worker/container/Compose gates | Exact image/source provenance required |
| S7 | Issue the P4 final handoff and entry decision for the next phase | No implicit P5 authorization |

S0 acceptance may merge or mark S1 not applicable if all required harnesses already exist and are
owned by R3-R5. It must not add work merely to populate every nominal step.

## 5. Entry acceptance checklist

Independent S0 acceptance must verify:

1. Every R1-R5 handoff is reachable and its validated code SHA is an ancestor of the candidate.
2. The corrected R5 source-tree digest is reproducible and the original incorrect digest is not
   used as current provenance.
3. No post-R5 diff changes Operation/Step contracts, schema, CAS, worker behavior, JobDefinition or
   recovery semantics; otherwise reopen the owning module before R6.
4. Each P4 exit invariant has one authoritative test owner, with timing/process tests correctly
   classified as serial and Dolt-dependent tests correctly classified as integration.
5. The exact current-HEAD image, Compose and process gates are listed, including gates triggered by
   the post-R5 runner, harness and test-client Dockerfile changes.
6. R6 contains no Workspace/HTTP/global-readiness or real Repository-effect implementation.
7. The candidate and evidence record distinguish historical R5 image evidence from current-HEAD R6
   results and name the required final execution point.

The exact candidate gate inventory proposed for acceptance is:

```text
Host and package gate:
  ./vnext/scripts/run-tests.sh
  cd vnext/<each of backend, shared_kernel, repository_contracts,
    repository_client, repository_service> && uv run ruff check . && uv run mypy

P4 recovery/fault evidence owners:
  vnext/backend/tests/test_operation_recovery_policy.py
  vnext/backend/tests/test_operation_takeover.py
  vnext/backend/tests/test_operation_effect_reconcile.py
  vnext/backend/tests/test_operation_job_recovery.py
  vnext/backend/tests/test_operation_job_synthetic.py
  vnext/backend/tests/test_operation_worker_integration.py
  vnext/backend/tests/test_operation_worker_process.py
  vnext/backend/tests/test_operation_recovery_process.py
  vnext/backend/tests/test_job_definition_contracts.py
  vnext/backend/tests/test_job_definition_registry.py
  vnext/backend/tests/test_architecture.py

Backend container gate:
  rebuild vnext/backend/Dockerfile from the final vnext build context
  run python -m gateway_backend.bootstrap.operation_worker in the image
  verify worker_ready, SIGTERM drain_started/worker_exited, exit 0, DB reopen and log redaction

Post-R5 affected Compose nodeids:
  tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
  tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
  tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
  tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle
  tests/test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up
  tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up
  tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up
  tests/test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up
```

The authoritative runner must be invoked without Compose ignores for the final candidate. The
focused P4 files may be run earlier by marker and risk scope; timing/process owners remain serial.

## 6. Container and verification disposition

```yaml
current_head: d7cb5b9c2c55e8f8b0814520e9d95c7df0ad00a5
container_rebuild_required: yes
container_reason: post-R5 container harness and test-client Dockerfile changed; R6 is the P4 final gate
last_verified_backend_image_revision: 0fa2b897a75436b4319d4490bc97c54ced494783
last_verified_backend_image_id: sha256:a2db693e2e9f56747532134d819067cf850f1606b34f845460aebb872c6b3d95
container_gate_for_current_head: stale
required_execution_point: P4-R6 final candidate before S7 exit
python_tests_for_this_docs_only_discussion: not_run
five_package_static_for_this_docs_only_discussion: not_run
benchmark: not_applicable_no_performance_claim
```

No test or container result is claimed by this docs-only discussion. The independent S0 acceptance
may use inspection and provenance checks; implementation and execution gates begin only after their
own authorization.

## 7. Discussion outcome and next boundary

R5 is closed. The project has enough consistent contract, code and historical gate evidence to enter
P4-R6-S0 independent entry acceptance. It does not yet have authority to begin R6 implementation or
to claim that current HEAD passed container/Compose validation. Acceptance must either approve the
bounded gate above or record a concrete owner/provenance finding; it may not expand R6 into P5 work.

# P4-R6-S0 Independent Entry Acceptance

状态：**PASS — R6 ENTRY ACCEPTED; S1–S7 EXECUTION NOT YET AUTHORIZED**

日期：2026-09-13

Owner：Backend vNext Architecture Acceptance + Operation Runtime Integration

上游：[P4-R6-S0 Entry Brief](p4-r6-s0-entry-brief.md)、
[P4-R6-S0 Finding Disposition](p4-r6-s0-finding-disposition.md)、
[P4-R6/R1 Registry-Name Contract Reopen](p4-r6-r1-registry-name-contract-reopen.md)、
[P4/R5 Retry, Takeover and Effect Recovery Handoff](p4-r5-retry-takeover-effect-recovery-handoff.md)

## 1. Acceptance identity and decision

```yaml
acceptance_kind: p4_r6_s0_independent_entry_acceptance
step_id: P4-R6-S0
reviewed_candidate_head: 7e8cea7b3454a8cfdd7c2ba880becee5c427a0de
reviewed_worktree: p4_docs_plus_two_finding_scoped_backend_test_files
reviewed_worktree_committed: false
r6_discussion_head: d7cb5b9c2c55e8f8b0814520e9d95c7df0ad00a5
r5_validated_code_sha: 0fa2b897a75436b4319d4490bc97c54ced494783
r5_corrected_source_tree: sha256:2fcb0e05217590b09a552e545a196847d76e50c260fa2229dca6335da1e02e4d
reviewed_worktree_python_source_test_tree: sha256:5f49d396981f1b75f43b092c71979c3f56ea8742e639db717316a5992028f941
reviewed_worktree_python_file_count: 308
decision: pass
findings: []
closed_findings:
  - P4-R6-S0-F1
  - P4-R6-S0-F2
p4_r6_s0_acceptance: accepted
p4_r6_implementation_authorized: no
p4_r6_exit: not_declared
p5b_real_repository_effect_authorized: no
p5_5b_implementation_authorized: no
next_step: issue_P4-R6-S1-S7_gate_execution_task
next_step_authorized: no
new_explicit_authorization_required: yes
```

The reviewed candidate is the exact Git `HEAD` above plus these P4 formal-document changes:

- `docs/backend-vnext/refactoring/formal/README.md`;
- `docs/backend-vnext/refactoring/formal/contracts/operation-lifecycle-and-integrity.md`;
- `docs/backend-vnext/refactoring/formal/plans/p4-active-context-index.md`;
- `docs/backend-vnext/refactoring/formal/plans/p4-r1-runtime-contract-state-execution-plan.md`;
- `docs/backend-vnext/refactoring/formal/plans/p4-r6-r1-registry-name-contract-reopen.md`;
- `docs/backend-vnext/refactoring/formal/plans/p4-r6-s0-finding-disposition.md`;
- this acceptance record.

The only finding-scoped `vnext/**` changes are:

- `vnext/backend/tests/test_operation_contracts.py`;
- `vnext/backend/tests/test_operation_worker_integration.py`.

All five `uv.lock` files are byte-identical to `HEAD`. The following four untracked P5-5B documents
are user-owned parallel work, were not read as P4 authority, were not modified, and are excluded
from the P4-R6 finding-scoped diff:

- `p5-5b-s0-independent-docs-review.md`;
- `p5-5b-s0-remediation-independent-review.md`;
- `p5-5b-submit-finalize-design.md`;
- `p5-5b-submit-finalize-execution-plan.md`.

All four are under `docs/backend-vnext/refactoring/formal/plans/`. This acceptance record itself is
an uncommitted documentation output; no commit is created or implied.

## 2. Prerequisites and corrected R5 provenance

| Module | Reachable handoff | Validated code | Candidate ancestor |
| --- | --- | --- | --- |
| R1 | [Runtime Contract and State](p4-r1-runtime-contract-state-handoff.md) | `e2703407a1c80d31f6888ce86c0ab9b125464ad5` | yes |
| R2 | [Durable Store and Atomic Transition](p4-r2-durable-store-atomic-transition-handoff.md) | `31235dc820472a5ca2c99138fdf150090cfe122d` | yes |
| R3 | [Worker Lifecycle](p4-r3-worker-lifecycle-handoff.md) | `acb3efca06a02aadaa5ce6d1e2a815e85d36e6af` | yes |
| R4 | [JobDefinition and Checkpoint](p4-r4-jobdefinition-checkpoint-handoff.md) | `d1d929dcee3b0620b649a248079d846dfbe7aba1` | yes |
| R5 | [Retry, Takeover and Effect Recovery](p4-r5-retry-takeover-effect-recovery-handoff.md) | `0fa2b897a75436b4319d4490bc97c54ced494783` | yes |

The discussion commit `d7cb5b9c2c55e8f8b0814520e9d95c7df0ad00a5` is also an ancestor of the
candidate. Recomputing sorted per-file SHA-256 records for tracked Python files under
`vnext/backend/src` and `vnext/backend/tests` from `0fa2b897` produces
`2fcb0e05217590b09a552e545a196847d76e50c260fa2229dca6335da1e02e4d`. The obsolete
`911fe38d...` digest is not accepted provenance and must not reappear in R6 evidence.

## 3. Current-HEAD delta classification

| Delta | Classification | R6 disposition |
| --- | --- | --- |
| `0fa2b897..d7cb5b9c`: authoritative locked runner, serial grouping, tmpfs handling, Compose lifecycle harness and repository-client test Dockerfile | Compatible gate/harness maintenance; no P4 runtime semantic change | Revalidate with the current runner and the eight affected Compose owners; final image evidence must be fresh |
| `operations/contracts.py`: registry grammar adds `/` | Bounded R1 persisted-admission amendment, accepted by the explicit reopen; `/` remains opaque and backslash remains invalid | F1 closed by direct constructor/parser/round-trip owners; no R2–R5 reopen |
| `bootstrap/operation_worker.py`: Preview JobDefinitions, recovery port, bounded artifact store, Repository read provider and production settings composition | Compatible P5 consumer/composition integration over existing P4 ports | P4 lifecycle/recovery regression and current-HEAD worker image smoke required; no real Repository Submit effect enters R6 |
| `settings.py`, `tests/support/runtime_settings.py`, and P4 owner fixture call sites | Compatible P5 production-settings expansion and test-fixture adaptation | Re-run P4 focused, lifecycle, process and crash owners on current HEAD |
| P4 owner test adjustments for Preview composition, redaction, architecture and settings | Regression adaptation; no second contract owner | Retain the existing unique owners and marker split below |
| `backend/Dockerfile`, Compose wiring/config and backend/worker runtime inputs | Image/deployment boundary changed after R5 | Rebuild backend and worker from the final R6 candidate and record source/image provenance in S6 |
| Workspace, HTTP, PreviewResult, upload and Repository-read P5-5A implementation | Compatible parallel P5 consumer, outside R6 ownership | Do not extend, redesign or claim as a P4 deliverable |
| Finding-scoped worktree tests | Tests-only closure for F1/F2 | No immediate image rebuild; final R6 candidate rebuild remains mandatory |

The R2 store persists and compares registry names as exact text; R3 registry/worker paths use exact
`JobStepKey` lookup; R4 checkpoints serialize and compare opaque strings; R5 passes the strings to
capability lookup without path interpretation. No schema, migration, status, CAS, JobDefinition
meaning or recovery authority drift remains, so R1–R5 do not require another reopen.

## 4. Applicable and merged R6 steps

| Step | Accepted disposition |
| --- | --- |
| S0 | complete by this independent acceptance; no R6 exit claim |
| S1 | merge into S2/S3: synthetic worker, Repository stub, crash and admin-readback harnesses already exist; confirm them rather than add duplicate mechanisms |
| S2 | required: current-HEAD focused/unit/integration/serial gates and five-package ruff/mypy |
| S3 | required: process/crash/takeover/duplicate/cancel/drain/restart/corruption matrix |
| S4 | required independent findings-first review of owners, CAS/transaction, recovery and deferred scope |
| S5 | conditional; only demonstrated S4 findings may authorize finding-scoped remediation |
| S6 | required current-HEAD backend/worker rebuild, process smoke, affected Compose gates and provenance |
| S7 | required final P4 handoff and `p4_r6_exit` decision; it does not authorize P5-5B implementation |

This split is accepted, but no S1–S7 execution begins from this document. A new explicit task must
authorize the implementer to execute the gates.

## 5. Unique test-owner and marker matrix

Ownership is per invariant. Supporting assertions in another file do not create a second owner.

| P4 exit invariant | Unique authoritative owner | Required marker |
| --- | --- | --- |
| Operation/Step shape, statuses, bounded values and registry-name grammar | `test_operation_contracts.py`; transition matrix in `test_operation_state.py` | `unit` |
| SQLite row mapping, schema integrity and atomic/CAS persistence | `test_sqlite_operation_store.py`; real-file/reopen/process boundaries in `test_sqlite_operation_store_integration.py` | `unit`; file-backed `integration`; contention/process termination also `serial` |
| JobDefinition descriptor and immutable registry lookup | `test_job_definition_contracts.py`, `test_job_definition_registry.py` | `unit` |
| Retry classification, bounded budgets and recovery decision mapping | `test_operation_recovery_policy.py` | `unit` |
| Lease expiry, retry budget, takeover, stale writer and operator CAS | `test_operation_takeover.py`; real startup process takeover in `test_operation_recovery_process.py` | `integration`; concurrent/fixed-time/process cases `serial` |
| Pure-compute checkpoint, READY closure and deterministic output | `test_operation_job_synthetic.py` | `unit`; real artifact reopen case `integration` |
| Cross-boundary crash, response loss, duplicate delivery and corrupt/missing checkpoint | `test_operation_job_recovery.py` shared matrices | `integration`; no real process timing is claimed by simulated crash rows |
| External-effect identity, reconcile timeout and no-blind-replay policy | `test_operation_effect_reconcile.py`; checkpoint consumer outcomes in `test_operation_job_recovery.py` | pure policy `unit`; file/stub recovery `integration` |
| File-backed worker readiness, WAL reopen, heartbeat/cancel and publication | `test_operation_worker_integration.py` | `integration`; every fixed `Event.wait`, `Thread.join` or concurrency budget owner `serial` |
| Real worker process startup, SIGTERM drain, crash barrier and redaction | `test_operation_worker_process.py` | module-level `integration + serial` |
| Real recovery process startup takeover | `test_operation_recovery_process.py` | module-level `integration + serial` |
| Runtime/application/import dependency boundaries | `test_architecture.py` | `unit` through backend collection policy |
| Current image worker lifecycle and DB reopen | S6 backend/worker container smoke | container gate; not a pytest marker substitute |
| Post-R5 Compose lifecycle and network gates | the eight nodeids in section 6 | `integration + serial`, `-n 0` |

No P4 owner requires Dolt. Any real Dolt/network test remains `integration`; fixed timing, subprocess,
signal, crash and drain/restart evidence remains `serial` and must not enter the parallel batch.

## 6. Frozen pending execution commands

The following are pending R6 evidence, not results of S0.

### 6.1 Authoritative and static gates

```bash
./vnext/scripts/run-tests.sh

for package in backend shared_kernel repository_contracts repository_client repository_service; do
  (
    cd "vnext/${package}"
    env -u UV_DEFAULT_INDEX -u UV_INDEX_URL -u UV_INSECURE_HOST \
      -u PIP_INDEX_URL -u PIP_TRUSTED_HOST \
      uv run --locked ruff check .
    env -u UV_DEFAULT_INDEX -u UV_INDEX_URL -u UV_INSECURE_HOST \
      -u PIP_INDEX_URL -u PIP_TRUSTED_HOST \
      uv run --locked mypy
  )
done
```

The authoritative runner is invoked without `--ignore` or environment-provided ignores.

### 6.2 Focused recovery/fault owners

```bash
cd vnext/backend

P4_OWNER_FILES=(
  tests/test_operation_recovery_policy.py
  tests/test_operation_takeover.py
  tests/test_operation_effect_reconcile.py
  tests/test_operation_job_recovery.py
  tests/test_operation_job_synthetic.py
  tests/test_operation_worker_integration.py
  tests/test_operation_worker_process.py
  tests/test_operation_recovery_process.py
  tests/test_job_definition_contracts.py
  tests/test_job_definition_registry.py
  tests/test_architecture.py
)

env -u UV_DEFAULT_INDEX -u UV_INDEX_URL -u UV_INSECURE_HOST \
  -u PIP_INDEX_URL -u PIP_TRUSTED_HOST \
  uv run --locked pytest -q -m unit "${P4_OWNER_FILES[@]}"
env -u UV_DEFAULT_INDEX -u UV_INDEX_URL -u UV_INSECURE_HOST \
  -u PIP_INDEX_URL -u PIP_TRUSTED_HOST \
  uv run --locked pytest -q -m 'integration and not serial' "${P4_OWNER_FILES[@]}"
env -u UV_DEFAULT_INDEX -u UV_INDEX_URL -u UV_INSECURE_HOST \
  -u PIP_INDEX_URL -u PIP_TRUSTED_HOST \
  uv run --locked pytest -q -m serial "${P4_OWNER_FILES[@]}"
```

The worker process/crash/drain/restart matrix is the serial slice of
`test_operation_worker_process.py`, `test_operation_recovery_process.py`,
`test_operation_worker_integration.py`, `test_operation_takeover.py` and
`test_operation_job_recovery.py`; the command above is its authoritative focused invocation.

### 6.3 Current-HEAD images and Compose owners

```bash
cd vnext/deploy
docker compose build backend worker
docker compose up -d repository-service backend worker
docker compose stop -t 180 worker
docker compose logs --no-color backend worker repository-service
docker compose down
```

The smoke must observe `worker_ready`, SIGTERM `drain_started` then `worker_exited`, exit zero,
control-DB reopen and absence of host paths, bearer tokens, payload bodies and SQL text in logs.
Build and smoke must use the final R6 candidate, not the S0 worktree or a cached historical image.

```bash
cd vnext/repository_service
env -u UV_DEFAULT_INDEX -u UV_INDEX_URL -u UV_INSECURE_HOST \
  -u PIP_INDEX_URL -u PIP_TRUSTED_HOST \
  uv run --locked pytest -q -n 0 \
    tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay \
    tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network \
    tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host \
    tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle \
    tests/test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up \
    tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up \
    tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up \
    tests/test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up
```

All eight nodeids were collected during S0 under `integration and serial`; collection is not an
execution pass.

## 7. Image and source provenance requirements

S6/S7 must record the final candidate commit and clean/declared worktree, the exact build context,
the sorted source-tree digest and file count, `backend/uv.lock` digest, backend Dockerfile identity,
Compose digest, backend and worker image IDs/tags, build timestamp and commands. It must verify the
Python source inside each image against the final candidate and bind every smoke/Compose result to
those image IDs. If repository-service is rebuilt or consumed by the eight Compose owners, its image
ID, candidate/build-input revision, source-tree and lock digest must be recorded as well.

R5 image `sha256:a2db693e...c6b3d95` and P5-5A backend/static/container smoke are historical or
prerequisite evidence only. P5-5A records `authoritative_runner=partial_pass_5a_scope`; its five
repository-service parallel failures and eight Compose failures are not P4-R6 pass evidence. Later
P5-5A image results likewise do not replace the mandatory final-R6 rebuild and provenance binding.

```yaml
container_rebuild_required_for_s0_remediation: no
container_reason_for_s0_remediation: tests_only
container_rebuild_required_for_final_r6_candidate: yes
container_reason_for_final_r6_candidate: p4_exit_plus_post_r5_worker_docker_compose_and_harness_delta
current_candidate_container_gate: pending
historical_image_results_are_current_candidate_pass: false
```

## 8. S0 verification, findings and deferred boundary

Independent S0 rereview executed only proportionate focused checks:

```text
backend contract + architecture unit owners -> 274 passed
worker integration and not serial           -> 8 passed, 3 deselected
worker serial                               -> 3 passed, 8 deselected
registered readiness integration+serial     -> 1 node collected
eight Compose integration+serial nodeids    -> 8 nodes collected; not executed
two changed test files ruff                 -> pass
five-package ruff + mypy                    -> pass; backend mypy 308 files
git diff --check                            -> pass before acceptance edits
```

S0 did not run the authoritative full runner, Dolt, Docker build, container smoke or Compose tests,
and does not claim any of them passed. F1 is closed by the bounded R1 amendment plus positive and
negative owner tests; F2 is closed by the combined `integration + serial` marker. No finding remains.

Workspace/HTTP/PreviewResult, production Repository Submit/Finalize effect, occupancy/T1/T3,
P5-5B implementation, global readiness, HA and external durable DB remain deferred and outside R6.
Reopen R1–R5 only if later work changes Operation/Step/JobDefinition fields or versions, schema/
migration/status/CAS semantics, checkpoint/READY ownership, worker fencing/drain behavior, recovery
authority, or introduces path meaning for registry names. A gate failure without contract drift is
an R6 S5 remediation finding, not an automatic architecture reopen.

## 9. Final decision and next boundary

`p4_r6_s0_acceptance: accepted`. The existing R6 scope, merged S1 disposition, S2–S7 gates, unique
test ownership, marker policy, container applicability and provenance plan are accepted for the
current candidate. This is entry acceptance only: `p4_r6_implementation_authorized: no` and
`p4_r6_exit` is not declared.

The next step is to issue a separate, explicit P4-R6 S1–S7 gate-execution task to the implementer.
Because S1 is merged into S2/S3, that task should begin by confirming existing harnesses and running
S2/S3 evidence, then proceed through independent S4, conditional S5, mandatory S6 and final S7.
New explicit authorization is required before that task begins.

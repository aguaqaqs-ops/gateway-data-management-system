# P4/R3-S5 Remediation Handoff

状态：**PASS — seven S4 findings remediated; focused rereview required before S6**

日期：2026-08-24

Owner：Backend Bootstrap + Operation Worker Runtime

上游：[P4/R3-S4 Focused Review](p4-r3-s4-focused-review.md)、
[P4/R3-S5 Remediation Appendix](p4-r3-s5-remediation-appendix.md)

```yaml
handoff_kind: p4_r3_s5
step_id: P4-R3-S5
input_handoff_sha: 6d9bbcd520ca628076e85ac0d85bd9602d9f4519ab2463314c7aa41fe7678599
input_review_sha: 3ee9e985dc8bd6b2d44f6eae1fda45bc8d948807223352e4195e9b40172d0319
input_validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
reviewed_head: edb15144ac5eae54e970c28f12f58e5e45b075a9
candidate_code_sha: pending_explicit_commit_authorization
candidate_worktree: uncommitted_s5_remediation_candidate
validated_source_tree: sha256:35992e625422607d5dca560b428599cd92149402544864e1815a192be7fa4d9a
source_tree_method: sorted_per_file_sha256_records_for_vnext/backend/src_and_tests_python_files
result: pass
container_rebuild_required: yes
container_reason: S3b entrypoint/settings/process boundary remains in the candidate
last_verified_image_revision: none_for_s5_candidate
container_gate: deferred_to_s7_final_candidate
candidate_commit: not_created
```

## 1. Finding dispositions

| Finding | Result | Remediation and evidence |
| --- | --- | --- |
| P4-R3-S4-F1 | **closed for S5** | `WorkerRuntime` anchors claim budget before `claim_one` and renewal budget immediately before `LeaseSession.heartbeat()`. The remaining monotonic budget is used for busy retry and is not replenished by transaction/observer latency. `test_heartbeat_budget_includes_claim_and_observer_elapsed_time` passes and fences at the remaining budget. |
| P4-R3-S4-F2 | **closed for S5** | `LeaseSession` rejects a checkpoint candidate whose `lease_expires_at` differs from the transaction-fresh current Step, before the R2 action. `test_checkpoint_builder_cannot_replace_the_session_lease_expiry` proves rollback and lease retention. |
| P4-R3-S4-F3 | **closed for S5** | The runtime latches `pending_drain` immediately after observing active drain and waits on executor completion while retaining heartbeat supervision. `test_active_drain_latches_executor_wait_without_polling_spin` passes with a bounded completion wait and no polling-spin path. |
| P4-R3-S4-F4 | **closed for S5** | Runtime drain timeout is worker-fatal, including the completion-at-deadline boundary; it emits no `worker_exited` and cannot enter clean exit. Bootstrap maps the failure to status 1. `test_runtime_timeout_is_worker_fatal_without_worker_exit` and `test_bootstrap_maps_runtime_timeout_to_nonzero_without_clean_exit` pass. |
| P4-R3-S4-F5 | **closed for S5** | `_StartupObserver` buffers READY and `_StartupBudget` performs the post-gate deadline check before publishing it. A slow gate yields exactly one bounded startup-timeout failure and no claim. `test_startup_budget_rejects_a_slow_gate_without_publishing_ready` passes. |
| P4-R3-S4-F6 | **closed for S5** | `gateway_backend.bootstrap` initialization is side-effect free; the process owner now asserts that the real module entrypoint output contains neither `RuntimeWarning` nor `runpy`. The four process tests pass. |
| P4-R3-S4-F7 | **closed for S5** | This handoff records the actual S1a–S3b content hashes, current rerun counts, current source/test tree identity, and the still-pending candidate code SHA. Historical handoffs were not rewritten. |

The S5 delta is limited to the finding-scoped paths authorized by the appendix:

```text
production:
  vnext/backend/src/gateway_backend/bootstrap/__init__.py
  vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
  vnext/backend/src/gateway_backend/operations/lease_session.py
  vnext/backend/src/gateway_backend/operations/worker_runtime.py
tests:
  vnext/backend/tests/test_operation_lease_session.py
  vnext/backend/tests/test_operation_worker_lifecycle.py
  vnext/backend/tests/test_operation_worker_process.py
  vnext/backend/tests/test_operation_worker_scheduler.py
documentation:
  docs/backend-vnext/refactoring/formal/plans/p4-r3-s5-remediation-appendix.md
  docs/backend-vnext/refactoring/formal/plans/p4-r3-s5-handoff.md
```

No R1 state, R2 schema/store/CAS/error semantics, lease profile, second executor, force-kill/detach,
durable worker evidence, IPC, packaging, Dockerfile, Compose or container workaround was added.

## 2. Verification

All commands below were run against the current uncommitted candidate:

```text
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_operation_worker_contracts.py \
  tests/test_operation_lease_session.py \
  tests/test_operation_worker_startup.py \
  tests/test_operation_worker_scheduler.py \
  tests/test_operation_worker_lifecycle.py \
  tests/test_architecture.py
  -> 100 passed

uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_worker_integration.py \
  tests/test_operation_worker_process.py
  -> 1 passed, 6 deselected

uv run pytest -q -m serial \
  tests/test_operation_worker_integration.py \
  tests/test_operation_worker_process.py
  -> 6 passed, 1 deselected

uv run pytest -m unit
  -> 1393 passed, 31 deselected, 1 pre-existing Starlette deprecation warning

uv run pytest -m serial
  -> 8 passed, 1416 deselected, 1 pre-existing Starlette deprecation warning

uv run ruff check . && uv run mypy
  -> backend pass; mypy 217 source files
cd vnext/shared_kernel && uv run ruff check . && uv run mypy
  -> pass; mypy 34 source files
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
  -> pass; mypy 15 source files
cd vnext/repository_client && uv run ruff check . && uv run mypy
  -> pass; mypy 26 source files
cd vnext/repository_service && uv run ruff check . && uv run mypy
  -> pass; mypy 195 source files

git diff --check
  -> pass
```

The repository-prescribed `pytest -m serial -n 0` spelling was also attempted, but this environment's
backend virtualenv has no xdist plugin and pytest rejected `-n`. The same serial marker was therefore
run in the available single-process pytest environment; no serial test was skipped.

The current source/test identity was recomputed from sorted SHA-256 records of every Python file under
`vnext/backend/src` and `vnext/backend/tests`:

```text
35992e625422607d5dca560b428599cd92149402544864e1815a192be7fa4d9a
```

## 3. Corrected lineage

These are the content SHA-256 values of the existing historical handoffs at S5 entry. They are copied
without rewriting the historical documents:

```yaml
S1a_handoff_sha: 51d92420519f200c244df169e21a3780de8e08fcbecf17a365e3f25586817925
S1b_handoff_sha: 2db23e601cb091684bd5ee60b672ee543fc61b11f452d6b3c93e3ac2f24d0699
S2a_handoff_sha: 2e9b4d4cf11d06b59294e238863efc3f95ac5f77b448b2e4d5fcb5c7aea6a2d8
S2b_handoff_sha: ab75132a93b6aaae2796f8b0cb76a48f934f4a00838ba01f21c7ef14a84591b9
S3a_handoff_sha: 5036dd4f1fb71b19a3531c340b2d93aab096296c1977af958e30413c7a4e9823
S3b_handoff_sha: 6d9bbcd520ca628076e85ac0d85bd9602d9f4519ab2463314c7aa41fe7678599
S4_review_sha: 3ee9e985dc8bd6b2d44f6eae1fda45bc8d948807223352e4195e9b40172d0319
candidate_code_sha: pending_explicit_commit_authorization
```

The corrected current evidence is 100 focused unit passes, 1393 backend unit passes with 31
deselected, 1 non-serial integration pass, and 6 worker-focused serial passes. The broader serial
marker run is 8 passed with 1416 deselected. The one Starlette warning is pre-existing and unrelated
to the worker changes.

## 4. Boundary and next step

S5 is complete for remediation. The next authorized workflow step is an independent S4 focused
rereview of this remediation. S6 remains blocked pending that rereview; S7 remains blocked pending
S6 and must rebuild the current final candidate image before any production/container claim. No image
was built in S5, so no image revision or container result is asserted here.

This handoff does not authorize a commit, S6 implementation changes, R4/R5 work, P5 work, or an
early container gate.

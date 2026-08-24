# P4/R3-S5 Remediation Appendix

状态：**S5 remediation authorized by explicit user request; finding-scoped changes only**

日期：2026-08-24

Input review：[P4/R3-S4 Focused Review](p4-r3-s4-focused-review.md)

本 appendix 是 S5 的 production/test authorization boundary。每项修复只允许使用下表列出的
S1a–S3b 已有职责子集；不得借修复引入 R4/R5 policy、R2 schema/store/error 语义、durable
worker evidence、IPC、第二 executor、packaging、Dockerfile、Compose 或 container workaround。

## 1. Finding-scoped remediation table

| Finding | Severity / owner | Allowed production paths | Allowed test paths | Production change | Regression / closure rule | Reopen trigger | Container impact |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F1 lease budget anchor | P2 / `operations.worker_runtime` | `vnext/backend/src/gateway_backend/operations/worker_runtime.py` | `vnext/backend/tests/test_operation_worker_scheduler.py` | Anchor each claim/renewal budget no later than the durable lease-establishing operation; account for claim/session/observer elapsed monotonic time; never replenish budget from post-operation latency. | Fake-clock regression advances time during claim/session/observer and heartbeat busy retry; retry is bounded by remaining durable lease budget and fences before expiry. | Need a second durable clock, configurable/flexible lease profile, or R2 lease/CAS changes. | No immediate build; existing S7 entrypoint boundary still requires final current-HEAD rebuild. |
| F2 checkpoint lease ownership | P2 / `operations.lease_session` | `vnext/backend/src/gateway_backend/operations/lease_session.py` | `vnext/backend/tests/test_operation_lease_session.py` | Checkpoint publication preserves the fixed R3 lease expiry rule and rejects arbitrary future extension before the R2 action. | Existing heartbeat/checkpoint freshness tests plus arbitrary long-expiry rejection and valid fixed-budget checkpoint publication. | Need a new persisted field, R2 action, or configurable lease duration. | Same S7 deferred container trigger; no image change in S5. |
| F3 active-drain wait | P2 / `operations.worker_runtime` | `vnext/backend/src/gateway_backend/operations/worker_runtime.py` | `vnext/backend/tests/test_operation_worker_scheduler.py` | Latch local pending-drain immediately after first observation and use completion/deadline waits while heartbeat supervision continues; no repeated already-set drain polling. | Fake clock/executor regression requests drain immediately after thread start and proves bounded wait calls, no new claim and continued heartbeat path. | Need force escalation, thread kill/detach, or a second executor. | Same S7 deferred container trigger; no image change in S5. |
| F4 timeout exit mapping | P2 / lifecycle + bootstrap | `vnext/backend/src/gateway_backend/operations/worker_runtime.py`; `vnext/backend/src/gateway_backend/bootstrap/operation_worker.py` | `vnext/backend/tests/test_operation_worker_lifecycle.py`; `vnext/backend/tests/test_operation_worker_process.py` | Surface `DRAINING_TIMEOUT` as worker-fatal/non-zero without emitting `worker_exited`; retain no-kill/no-detach/heartbeat behavior. Bootstrap maps the bounded runtime failure to exit 1. | Runtime/controller fake-time regression and bootstrap mapping regression prove timeout cannot return cleanly or exit 0. | Need persisted lifecycle, force kill, IPC/global readiness, or changed timeout semantics. | Container rebuild remains deferred to S7; final smoke must verify non-zero timeout mapping if exercised. |
| F5 startup budget postcondition | P2 / bootstrap composition | `vnext/backend/src/gateway_backend/bootstrap/operation_worker.py` | `vnext/backend/tests/test_operation_worker_lifecycle.py` | Buffer the delegate's READY event and publish it only after the complete gate attempt is confirmed inside the 60-second monotonic budget; slow gate becomes one bounded startup failure. | Fake-clock slow-gate regression proves no READY after deadline, exactly one timeout failure, and no claim. | Need scan truncation/sampling, new durable readiness state, or changed deployment objective. | Same S7 deferred container trigger; no diagnostic build in S5. |
| F6 module runpy warning | P3 / bootstrap module CLI | `vnext/backend/src/gateway_backend/bootstrap/__init__.py` | `vnext/backend/tests/test_operation_worker_process.py` | Make package initialization side-effect free so the module target is not pre-imported before `python -m`. | Authoritative subprocess test asserts ready/drain output contains no `RuntimeWarning` or runpy duplicate-load warning. | Need console script, packaging, Dockerfile or second distribution. | S7 still owns current-HEAD image rebuild; S5 does not build an image. |
| F7 lineage/evidence consistency | P3 / S5 documentation | None | None | Corrected lineage and current command counts are recorded in the S5 handoff without rewriting historical S1b/S3a/S3b claims. | S5 handoff records actual handoff content hashes, pending uncommitted code SHA, current source/test hash, and rerun counts; no stale count is used as current evidence. | Any claim of an unauthorized candidate commit, mismatched source/test identity, or undocumented in-scope drift. | Container remains `required: yes`, `deferred: S7`; no image evidence is invented. |

## 2. Fixed evidence commands

Each production/test finding must run its own regression plus the affected focused owner. Before
closing S5, run:

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_operation_worker_contracts.py \
  tests/test_operation_lease_session.py \
  tests/test_operation_worker_startup.py \
  tests/test_operation_worker_scheduler.py \
  tests/test_operation_worker_lifecycle.py \
  tests/test_architecture.py
uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_worker_integration.py \
  tests/test_operation_worker_process.py
uv run pytest -q -m serial \
  tests/test_operation_worker_integration.py \
  tests/test_operation_worker_process.py
uv run pytest -q -m unit
uv run ruff check .
uv run mypy
```

Also rerun `ruff check . && mypy` in `shared_kernel`, `repository_contracts`, `repository_client`
and `repository_service`, then `git diff --check`. S5 does not run S6 probes, S7 image/container
gates, Dolt, Repository Service integration or a benchmark.

## 3. Corrected lineage baseline for S5 handoff

These are content SHA-256 values of the existing handoff documents at S5 entry; they identify the
actual lineage without changing historical records:

```yaml
S1a_handoff_sha: 51d92420519f200c244df169e21a3780de8e08fcbecf17a365e3f25586817925
S1b_handoff_sha: 2db23e601cb091684bd5ee60b672ee543fc61b11f452d6b3c93e3ac2f24d0699
S2a_handoff_sha: 2e9b4d4cf11d06b59294e238863efc3f95ac5f77b448b2e4d5fcb5c7aea6a2d8
S2b_handoff_sha: ab75132a93b6aaae2796f8b0cb76a48f934f4a00838ba01f21c7ef14a84591b9
S3a_handoff_sha: 5036dd4f1fb71b19a3531c340b2d93aab096296c1977af958e30413c7a4e9823
S3b_handoff_sha: 6d9bbcd520ca628076e85ac0d85bd9602d9f4519ab2463314c7aa41fe7678599
candidate_code_sha: pending_explicit_commit_authorization
```

Historical S1b/S3a/S3b documents remain unchanged as historical evidence. The corrected S5 handoff
must use current rerun counts and the post-remediation source/test tree identity.

## 4. S5 exit

S5 closes only when all seven findings have a regression result and disposition, the affected focused
tests plus backend static gates pass, the S5 handoff records current provenance, and no reopen trigger
is hit. The next step is S4 focused rereview of the remediation; S6 and S7 remain unauthorized.

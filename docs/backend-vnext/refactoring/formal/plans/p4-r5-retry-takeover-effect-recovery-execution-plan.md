# P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan

状态：**PASS — S7 module gate complete; P4-R6-S0 discussion only**

日期：2026-08-26

Owner：Operation Runtime + Application Recovery owner

入口：[P4-R5-S0 Entry Brief](p4-r5-s0-entry-brief.md)

设计基线：[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)

默认入口：[P4 Active Context Index](p4-active-context-index.md)

## 1. Execution protocol

每个 named step 必须从磁盘重新读取 R4 handoff、R5 design、R5 S0 brief、本 plan 和 Git 状态；
不得从聊天记忆推断授权。一个对话只完成一个 named step 的 implementation、validation、
diff review 和 handoff。S0、focused review、independent review 和 S7 使用新对话隔离设计偏置。

任何 source/test/build-input drift、跨 owner finding、R1/R2 schema/CAS/status/error taxonomy
需求、真实 Repository effect 或新的安全主体都必须停止并 reopen owning contract。

## 2. Shared handoff schema

```yaml
step_id:
context: same_conversation | new_conversation | mandatory_new_conversation
input_handoff_sha:
input_validated_code_sha:
validated_code_sha:
validated_source_tree:
candidate_worktree:
result: pass | rework_required | not_applicable
changed_paths: []
commands_and_results: []
focused_tests:
backend_unit:
integration:
serial:
five_package_static:
container_rebuild_required: yes | no
container_reason:
last_verified_image_revision:
container_gate: passed | deferred | stale | not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items: []
reopen_conditions: []
handoff_document:
short_prompt:
allowed_paths: []
forbidden_paths: []
expected_gate:
authorization_evidence:
candidate_worktree_at_gate: clean_committed | documented_dirty_candidate
next_step:
next_step_authorized: yes | no
```

## 3. Conversation and step split

| Step | Context | Objective | Primary owner |
|---|---|---|---|
| S0 | mandatory_new_conversation | Entry acceptance, owner/reopen freeze, provenance | Architecture acceptance |
| S1a | new_conversation | Recovery capability, decision/outcome and reconcile port contracts | R5 + Application |
| S1b | new_conversation | Retry/failure matrix, budgets, diagnostics and operator command contract | R5 |
| S2a | new_conversation | Expired lease classification, retry scheduling and CAS takeover | R5 + R3 |
| S2b | new_conversation | Original identity reconcile adapter and stub recovery path | R5 + Application |
| S2c | new_conversation | Internal operator recovery port and authorized CAS actions | R5 |
| S3a | new_conversation | Pure-compute retry/takeover consumer | Application |
| S3b | new_conversation | External-effect unknown/reconcile/cancel consumer | Application + R5 |
| S3c | new_conversation | Cross-boundary crash, duplicate, budget and manual matrix | R5 |
| S4 | mandatory_new_conversation | Focused review of complete R5 diff | Independent focused reviewer |
| S5 | new_conversation, conditional | Finding-scoped remediation and regression | Finding owner |
| S6 | mandatory_new_conversation | Independent review from sealed evidence | Independent reviewer |
| S7 | new_conversation | Current-HEAD module gate, image provenance and handoff | R5 owner |

S1a/S1b are separate because public in-process contracts and policy budgets have different owners.
S2a/S2b/S2c are separate because CAS takeover, effect reconciliation and authorized recovery have
distinct failure boundaries. S3a/S3b isolate pure recompute from external-effect assumptions; S3c
owns the cross-consumer matrix. S5 is created only if S4 or S6 records a finding.

### 3.1 Step execution cards

Each card is self-contained enough for a new conversation. The short prompt is an execution
instruction, not an implementation authorization beyond the named step.

#### S0 — Entry acceptance

```text
handoff_document: p4-r5-s0-entry-acceptance.md
allowed_paths: docs/backend-vnext/refactoring/formal/plans/p4-r5-s0-entry-acceptance.md,
  p4-active-context-index.md, formal/README.md, p4-r5-s0-entry-brief.md,
  p4-r5-retry-takeover-effect-recovery-design.md,
  p4-r5-retry-takeover-effect-recovery-execution-plan.md
forbidden_paths: all source, tests, dependencies, schema, deployment and Repository paths
expected_gate: docs-only provenance, link and owner/reopen review; no Python gate
candidate_worktree_at_gate: clean_committed after a docs-only seal commit
```

Short prompt:

```text
在新对话执行 P4-R5-S0 independent entry acceptance。读取 Active Context、R4 handoff、R5
design、S0 brief、本 execution plan 和 Git 状态；核对 docs-only seal SHA、R1/R2/R3/R4/P5B
owner、S1a contract shape、step cards、markers、container applicability 和 stop/reopen 条件；
只修改 S0 acceptance/索引文档，不改 source/tests，不开始 S1a；只有 independent acceptance
通过后才记录 p4_r5_s1a_authorized: yes。
```

#### S1a — Recovery contracts

```text
handoff_document: p4-r5-s1a-handoff.md
allowed_paths: application/job_definitions.py, application/recovery.py,
  tests/test_job_definition_contracts.py, tests/test_operation_recovery_policy.py,
  tests/test_architecture.py, p4-r5-s1a-handoff.md
forbidden_paths: operations runtime/store/bootstrap, migrations, Repository/P5 paths
expected_gate: focused unit + backend unit subset + ruff/mypy; no integration/serial
```

Short prompt:

```text
执行 P4-R5-S1a，按 S0 sealed handoff 冻结 RecoveryCapability、RecoveryDecision、RecoveryOutcome
和 reconcile port，并把 capability 作为现有 immutable JobDefinition 的非持久化字段；完成
contract/export/dependency-direction unit gates、diff review 和 p4-r5-s1a-handoff.md；不开始 S1b。
```

#### S1b — Policy and budgets

```text
handoff_document: p4-r5-s1b-handoff.md
allowed_paths: operations/recovery.py, tests/test_operation_recovery_policy.py,
  tests/test_operation_contracts.py, tests/test_operation_state.py, p4-r5-s1b-handoff.md
forbidden_paths: migrations, worker scheduler, application handlers, Repository/P5 paths
expected_gate: pure unit policy matrix, fake clock/wait/jitter, ruff/mypy; no real artifact/DB/process
```

Short prompt:

```text
执行 P4-R5-S1b，按 S1a handoff 冻结 retry/manual/reconcile/cancel/startup matrix、三 session
budget、1/2/4s backoff、10s cap、60s reconcile budget、diagnostics 和 RecoveryDecision 到
transition mapping；只跑纯 unit/static，生成 p4-r5-s1b-handoff.md，不开始 S2a。
```

#### S2a — Takeover and scheduling

```text
handoff_document: p4-r5-s2a-handoff.md
allowed_paths: operations/recovery.py, operations/worker_startup.py,
  operations/worker_runtime.py, tests/test_operation_takeover.py,
  tests/test_operation_recovery_process.py, p4-r5-s2a-handoff.md
forbidden_paths: migrations/schema, R2 port widening, application checkpoint format, Repository/P5 paths
expected_gate: backend integration + serial takeover/process tests, focused unit, ruff/mypy
```

Short prompt:

```text
执行 P4-R5-S2a，按 S1a/S1b handoff 将 expired RUNNING 分类接入现有 R3 startup/scheduler 和
R2 CAS；只允许 guarded RUNNING->RETRY_WAIT->RUNNING、保留 started_at、fence old token；完成
integration/serial takeover gates、diff review 和 p4-r5-s2a-handoff.md；若现有 store port 不足
立即 reopen R2，不改 port，不开始 S2b。
```

#### S2b — Effect identity reconcile

```text
handoff_document: p4-r5-s2b-handoff.md
allowed_paths: application/recovery.py, application/synthetic_jobs.py,
  tests/test_operation_effect_reconcile.py, tests/test_operation_job_recovery.py,
  p4-r5-s2b-handoff.md
forbidden_paths: Repository client wire, real Repository/Dolt, migrations, P5 business paths
expected_gate: backend integration (non-serial) + focused unit; stub-only, ruff/mypy
```

Short prompt:

```text
执行 P4-R5-S2b，按已冻结 port 实现原 idempotency key、request fingerprint 和
repository_operation_id 的 checkpoint-aware reconcile；accepted/confirmed 只 poll 原 identity，
不生成新 key；完成 stub integration/focused gates 和 p4-r5-s2b-handoff.md，不开始 S2c。
```

#### S2c — Authorized recovery port

```text
handoff_document: p4-r5-s2c-handoff.md
allowed_paths: operations/recovery.py, tests/test_operation_recovery_policy.py,
  tests/test_operation_takeover.py, p4-r5-s2c-handoff.md
forbidden_paths: HTTP/admin/auth principal, migrations, force-terminal escape hatch, P5 paths
expected_gate: focused unit + SQLite integration for CAS authorization, ruff/mypy
```

Short prompt:

```text
执行 P4-R5-S2c，按 contract 实现内部 RESUME_RECONCILE、RETRY_FROM_CHECKPOINT、
ABORT_CONFIRMED_FAILURE command port；要求 expected version、bounded reason 和 authorized CAS；
完成 stale/unauthorized/idempotent/occupancy tests 与 p4-r5-s2c-handoff.md，不开始 S3a。
```

#### S3a — Pure-compute consumer

```text
handoff_document: p4-r5-s3a-handoff.md
allowed_paths: application/synthetic_jobs.py, tests/test_operation_job_recovery.py,
  tests/test_operation_recovery_process.py, p4-r5-s3a-handoff.md
forbidden_paths: external-effect stub, Repository/P5 paths, R1/R2/R3 contracts
expected_gate: backend unit + integration + serial process tests as applicable, ruff/mypy
```

Short prompt:

```text
执行 P4-R5-S3a，使用 pure-compute synthetic job 验证 checkpoint recompute、三 session exhaustion、
lease takeover、duplicate、cancel-before-effect 和 successor non-duplication；按 marker 跑 gates，
生成 p4-r5-s3a-handoff.md，不开始 S3b。
```

#### S3b — External-effect stub consumer

```text
handoff_document: p4-r5-s3b-handoff.md
allowed_paths: application/synthetic_jobs.py, tests/test_operation_effect_reconcile.py,
  tests/test_operation_job_recovery.py, p4-r5-s3b-handoff.md
forbidden_paths: Repository client/service, P5 T1/T3, new effect journal or artifact recreation
expected_gate: backend integration + serial process/reconcile tests as applicable, ruff/mypy
```

Short prompt:

```text
执行 P4-R5-S3b，使用 deterministic external-effect stub 验证 request checkpoint、accepted/confirmed/
unknown、原 identity poll、60s budget、cancel-after-request 和 manual；断言 no new key/no false READY/
no occupancy release/no artifact recreation，生成 p4-r5-s3b-handoff.md，不开始 S3c。
```

#### S3c — Cross-boundary fault matrix

```text
handoff_document: p4-r5-s3c-handoff.md
allowed_paths: tests/test_operation_job_recovery.py, tests/test_operation_takeover.py,
  tests/test_operation_recovery_process.py, p4-r5-s3c-handoff.md
forbidden_paths: production source unless finding-scoped, Repository/P5 paths, duplicate invariant owners
expected_gate: complete backend focused/unit/integration/serial matrix, ruff/mypy
```

Short prompt:

```text
执行 P4-R5-S3c，按 S3a/S3b handoff 收敛唯一 cross-boundary matrix：crash、response loss、lease expiry、
duplicate、stale writer、corrupt checkpoint、retry exhaustion、reconcile timeout 和 operator action；
使用参数表避免同构复制，生成 p4-r5-s3c-handoff.md，不开始 S4。
```

#### S4/S5/S6/S7 — Review and gate cards

```text
S4 handoff: p4-r5-s4-focused-review.md;
  allowed: docs/backend-vnext/refactoring/formal/plans/p4-r5-s4-focused-review.md only;
  gate: reviewer reads complete R5 source/test/diff; prompt: only review, no production edits.
S5 handoff: p4-r5-s5-handoff.md + finding appendix;
  allowed: exactly the finding appendix paths plus the two S5 docs; gate: regression/owner closure;
  prompt: only if S4/S6 finding exists.
S6 handoff: p4-r5-s6-independent-review.md;
  allowed: docs/backend-vnext/refactoring/formal/plans/p4-r5-s6-independent-review.md only;
  gate: sealed evidence reread and independent disposition; prompt: no implementation.
S7 handoff: p4-r5-retry-takeover-effect-recovery-handoff.md;
  allowed: that handoff, p4-active-context-index.md, formal/README.md, R5 plan/brief/design status
  fields only; gate: current-HEAD source/test/static/image/container provenance; final module gate only.
```

Short prompts:

```text
在新对话执行 P4-R5-S4 focused review。读取完整 R5 source/test/diff 和全部 handoffs；只记录
finding、owner、severity、regression、closure/reopen，不改 production，不开始 S5/S6。

有 finding 时执行 P4-R5-S5，仅按 finding appendix 的 allowed paths 修复并复测；无 finding 不创建
production step，记录 not_applicable_no_findings。

在新对话执行 P4-R5-S6 independent review。只依据 sealed source/test/diff/evidence；不继承实现
假设，不改 source/test，不开始 S7。

执行 P4-R5-S7 current-HEAD module gate。重跑适用 gates，重建 backend image，执行 container smoke，
核对 provenance 并生成 R5 handoff；不开始 P4-R6 或 P5B。
```

## 4. Frozen allowed and forbidden surfaces

Candidate paths, subject to S0 authorization:

```text
vnext/backend/src/gateway_backend/application/job_definitions.py   # recovery capability only
vnext/backend/src/gateway_backend/application/recovery.py           # application recovery outcome/port
vnext/backend/src/gateway_backend/application/synthetic_jobs.py    # checkpoint-aware recovery paths
vnext/backend/src/gateway_backend/operations/recovery.py           # pure R5 policy/decision
vnext/backend/src/gateway_backend/operations/worker_startup.py     # recovery decision integration
vnext/backend/src/gateway_backend/operations/worker_runtime.py     # bounded retry/takeover scheduling
vnext/backend/src/gateway_backend/bootstrap/operation_worker.py    # composition only
vnext/backend/tests/test_operation_recovery_policy.py
vnext/backend/tests/test_operation_takeover.py
vnext/backend/tests/test_operation_effect_reconcile.py
vnext/backend/tests/test_operation_recovery_process.py
vnext/backend/tests/test_operation_job_recovery.py                 # only R5 matrix additions
vnext/backend/tests/test_architecture.py
```

The following are forbidden without reopen:

```text
R1/R2 contracts, migrations, schema, CAS or error taxonomy
R2 infrastructure/control_db migrations.py and persisted row shape
Repository Service/client HTTP wire or real Repository/Dolt effect
P5 business routes, T1/T3, global readiness, Compose or admin HTTP
second registry, generic journal/evidence state machine, cleanup broker, IPC or new principal
```

If an existing R2 store port cannot express expired-lease classification using its current
transition/CAS contract, stop and reopen R2; do not widen the port silently.

## 5. Step contracts and gates

### S0 — Independent entry acceptance

Docs-only. Verify R4 provenance, accepted R5 design, existing fields/guards, owner split, no schema
need, step split, markers, review contexts and container applicability. Exit:
`p4_r5_s0: accepted`, `p4_r5_s1a_authorized: yes`.

### S1a — Recovery contracts and immutable capability

Define the non-persisted `RecoveryCapability`, bounded `RecoveryDecision`, `RecoveryOutcome` and
reconcile port. Extend the existing immutable JobDefinition only; no second registry or persisted
field. Unit tests cover exact exports, enum closure, immutability, bounded identities and dependency
direction. Review focus: R3 protocol widening, application import direction and generic error leakage.

S1a handoff must freeze this exact recommended shape before S1b/S2 work begins:

```text
RecoveryCapability: PURE_RECOMPUTE | EXTERNAL_EFFECT | NON_RETRYABLE

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

`RecoveryPort` is an in-process composition port, not a persisted registry, HTTP API or R3 public
protocol. `RecoveryDecision` is read-only and cannot carry artifact bytes, payload objects, SQL,
network clients or callables. `retry_not_before` is required only for `MOVE_TO_RETRY_WAIT` and must
be within the bounded policy horizon. `RecoveryOutcome` is the only application-to-R5 result; R5
maps it to existing R1/R2 transitions and never accepts a handler-provided arbitrary candidate record.

The mapping is normative for S2/S3:

| Decision/outcome | Durable mapping |
|---|---|
| `MOVE_TO_RETRY_WAIT` | guarded `RUNNING -> RETRY_WAIT` with `retry_not_before` |
| `CLAIM_FOR_RECONCILE` | first schedule `RETRY_WAIT`; never direct token replacement |
| `RECONCILE_PENDING` | `RUNNING -> RETRY_WAIT` while budget remains |
| `RETRYABLE_FAILURE` | `RUNNING -> RETRY_WAIT` while three-session budget remains |
| `PERMANENT_FAILURE` | Step `FAILED`, then Operation `FAILED` |
| `MANUAL_RECOVERY` | Step/Operation `MANUAL_RECOVERY_REQUIRED`, occupancy retained |
| `CANCELLED` | only before irreversible effect boundary |
| `NON_RETRYABLE` capability | explicit permanent failure unless checkpoint/effect evidence is ambiguous, then manual |

### S1b — Policy matrix and budgets

Implement pure policy over fresh records: safe retry, external reconcile, manual, cancel and startup
classification. Freeze three sessions, `1/2/4` backoff capped at `10s`, 60-second reconcile session,
injected clock/wait/jitter and namespaced diagnostics. Unit tests use parameter tables and no artifact,
SQLite, Dolt or process fixtures. Review focus: unknown outcome replay, occupancy release and budget
accounting.

### S2a — Takeover and retry scheduling

Integrate recovery decisions with existing R3 startup/scheduler and R2 transition/CAS ports. Expired
`RUNNING` becomes `RETRY_WAIT` only through guarded CAS; next claim establishes a new lease and
increments attempt count. Preserve `started_at`; reject stale worker writes. Integration tests cover
lease expiry, StoreBusy deadline, duplicate claim and old-token fencing. No migration or direct token
swap is allowed.

### S2b — Effect identity and reconcile adapter

Bind the original idempotency key, request fingerprint and `repository_operation_id` to the existing
application handler/reconcile port. Confirmed requests poll only the original identity; pre-request
retry reuses the original key; mismatch becomes manual. Use deterministic stub only. Integration tests
cover accepted, confirmed, unknown, timeout and fingerprint mismatch without Repository/Dolt.

### S2c — Authorized recovery port

Implement only internal `RESUME_RECONCILE`, `RETRY_FROM_CHECKPOINT` and
`ABORT_CONFIRMED_FAILURE` commands with expected optimistic version and bounded reason. Apply
authorized transitions through existing CAS; no HTTP, auth principal or force-terminal escape hatch.
Unit/integration tests cover stale command, unauthorized manual transition, idempotent replay and
occupancy retention.

### S3a — Pure-compute consumer

Exercise checkpoint-based recompute, three-session retry exhaustion, duplicate delivery, lease
takeover, cancel-before-effect and successor non-duplication. Tests remain backend unit/integration;
process crash and fixed waits are `serial`.

### S3b — External-effect stub consumer

Exercise request checkpoint, accepted/confirmed/unknown outcomes, original identity polling,
poll-budget exhaustion, cancel-after-request and manual recovery. Assert no new key, no false READY,
no occupancy release and no request artifact recreation.

### S3c — Cross-boundary fault matrix

Own the single matrix for crash before/after checkpoint, before/after request, response loss,
lease expiry, duplicate delivery, stale writer, corrupt checkpoint, retry exhaustion, reconcile
timeout and operator action. Same-shape faults use shared parameter tables. No second production
probe is created for an invariant already owned by S3a or S3b.

### S4/S5/S6/S7 — Review and module gate

S4 reviews the complete source/test diff and all owner boundaries. S5 is conditional and finding-scoped.
S6 independently rereads source/test/diff and sealed evidence. S7 reruns focused/backend unit/
integration/serial gates, five-package ruff/mypy, `git diff --check`, SHA ancestry and current-HEAD
backend image/container smoke because worker/runtime composition is touched. S7 handoff must record
the exact source tree/image identity, deferred P5B gates and `next_entry: P4-R6-S0`.

## 6. Shared verification commands

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_operation_recovery_policy.py \
  tests/test_operation_takeover.py \
  tests/test_operation_effect_reconcile.py \
  tests/test_job_definition_contracts.py \
  tests/test_job_definition_registry.py \
  tests/test_architecture.py
uv run pytest -q -m unit
uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_effect_reconcile.py \
  tests/test_operation_job_recovery.py
uv run pytest -q -m serial \
  tests/test_operation_takeover.py \
  tests/test_operation_recovery_process.py
uv run ruff check .
uv run mypy
```

The other four Python packages each run `uv run ruff check . && uv run mypy`. R5 does not run Dolt
or Repository Service integration. Any test using fixed timeout, process crash, signal or restart
must be marked `serial`; pure policy/decoder/fake-clock tests must not create a real repository.

## 7. Stop, review and container rules

Stop immediately for any R1/R2 schema/status/CAS/error-taxonomy change, direct `RUNNING -> RUNNING`
token replacement, blind replay/new key, real Repository effect, new principal/IPC, generic evidence
state machine, or marker that cannot represent a new timing/process boundary. Findings must be
recorded by contract behavior, not round/finding number names.

R5 source/runtime changes normally defer intermediate image builds, but S7 must rebuild the current
HEAD image and run the synthetic worker container smoke. Any Dockerfile, entrypoint, Compose,
health/readiness, process harness or container-only runtime change triggers an earlier rebuild.

### 7.1 S7 exact container gate

Run from the repository root against the sealed source tip. Replace only the tag and the exact
temporary directory; do not use a prior R4 image as current-HEAD evidence:

```bash
r5_control_dir="$(mktemp -d)"
trap 'docker rm -f "$r5_container_id" >/dev/null 2>&1 || true; rm -rf "$r5_control_dir"' EXIT
docker build --network host \
  -f vnext/backend/Dockerfile \
  -t p4-r5-<validated-code-sha> \
  vnext

r5_container_id="$(docker run -d \
  -e GATEWAY_BACKEND_OPERATION_WORKER_CONTROL_DB_PATH=/var/lib/gateway/control/control.sqlite3 \
  -v "$r5_control_dir:/var/lib/gateway/control" \
  p4-r5-<validated-code-sha> \
  python -m gateway_backend.bootstrap.operation_worker)"

for r5_attempt in $(seq 1 30); do
  if docker logs "$r5_container_id" 2>&1 | rg -q 'worker_ready'; then
    break
  fi
  if ! docker inspect -f '{{.State.Running}}' "$r5_container_id" 2>/dev/null | rg -q '^true$'; then
    docker logs "$r5_container_id"
    exit 1
  fi
  sleep 1
done
docker logs "$r5_container_id"
# Observe worker_ready, then run the bounded synthetic fixture through the existing backend
# process/integration harness against the same image and mounted control directory.
docker kill --signal TERM "$r5_container_id"
docker wait "$r5_container_id"
docker logs "$r5_container_id"
docker image inspect p4-r5-<validated-code-sha> --format '{{.Id}}'
```

The gate record must include: `worker_ready`, bounded pure-compute/stub recovery evidence,
`drain_started`, no-new-claim during drain, clean/non-zero exit as specified by the fault case,
WAL/schema/ref readback, absence of path/token/payload/SQL in logs, image ID/digest, source SHA,
source-tree SHA and cleanup of the exact temporary directory. If no existing harness can execute
the synthetic fixture inside the image without adding an unplanned container harness path, stop
and record a planning finding before S7.

## 8. Exit criteria

R5 exits only when the complete fault matrix passes, no blind replay/new identity path exists,
manual recovery is authorized and fenced, R1/R2/R3/R4 owners have no open finding, focused/unit/
integration/serial/static gates pass, and current-HEAD image provenance is sealed. R5 handoff then
points to `P4-R6-S0`; it does not authorize P5B real Repository effect or P5 deployment work.

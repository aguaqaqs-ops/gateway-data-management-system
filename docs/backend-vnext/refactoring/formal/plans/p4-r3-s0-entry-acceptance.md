# P4/R3-S0 Independent Entry Acceptance

状态：**PASS — DESIGN AND EXECUTION PLAN ACCEPTED; S1a IMPLEMENTATION NOT AUTHORIZED**

日期：2026-08-24

Owner：Backend vNext Architecture Acceptance（independent acceptance context）

上游：[P4/R2 Durable Store and Atomic Transition Handoff](p4-r2-durable-store-atomic-transition-handoff.md)、
[P4-R3-S0 Entry Brief](p4-r3-s0-entry-brief.md)、
[P4-R3 Worker and Process Lifecycle Detailed Execution Plan](p4-r3-worker-lifecycle-execution-plan.md)

```yaml
acceptance_kind: p4_r3_s0
step_id: P4-R3-S0
input_handoff_sha: e9adbb03603e04bca5981c363fa01ac11576fbe7
input_validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
reviewed_base_sha: e9adbb03603e04bca5981c363fa01ac11576fbe7
reviewed_candidate_document_set_sha256: 1f5a82384023b44353636f63323c5e6bbb4abf623fa072d37fb16e980e75c920
candidate_acceptance_record_excluded_from_hash: true
candidate_worktree: documentation_only_candidate_on_clean_reviewed_base
source_code_changed: false
tests_changed: false
dependencies_changed: false
deployment_changed: false
p4_r2_exit: pass
p4_r3_s0: accepted
p4_r3_design: accepted
p4_r3_execution_plan: accepted
p4_r3_s1a_authorized: no
p4_r3_implementation_authorized: no
accepted_entrypoint: python_-m_gateway_backend.bootstrap.operation_worker
accepted_deployment: single_host_single_worker_shared_reliable_local_sqlite_wal
accepted_concurrency: one_non_daemon_executor_max_in_flight_1
accepted_transaction_boundary: fresh_uow_per_mutation_single_process_local_lease_session
accepted_lifecycle_split: r3_worker_local_p5_deployment_http_global_quiescence
accepted_drain_profile: 180s_no_automatic_kill_or_second_signal_force
open_findings: []
deferred_items:
  - R4 JobDefinition registry, payload, checkpoint closure and successor/final policy
  - R5 retry, expired RUNNING disposition, takeover and effect-aware reconciliation
  - P5 business T1/T3, backend HTTP/global readiness and final Compose wiring
  - multi-worker coordination, HA, external DB, retention and formal capacity baseline
next_step: P4-R3-S1a
next_step_authorized: no
next_input_sha: pending_s0_documentation_commit
```

## 1. Candidate identity

本次independent acceptance从已封存R2 handoff `e9adbb0`开始，只审查R3-S0 brief、
detailed execution plan、owner-reference clarification和default-context/status接线。
`31235dc` 仍是当前HEAD的ancestor；从该validated code tip到reviewed base的
`vnext/backend/src` 和 `vnext/backend/tests` 差异为空，当前worktree也没有source、
tests、dependency或deployment变更。

候选摘要按以下固定顺序计算，明确排除本acceptance record以避免自引用：

```bash
sha256sum \
  docs/backend-vnext/refactoring/formal/contracts/operation-lifecycle-and-integrity.md \
  docs/backend-vnext/refactoring/formal/contracts/external-effect-and-recovery.md \
  docs/backend-vnext/refactoring/formal/adr/0016-graceful-lifecycle-and-integrity-recovery.md \
  docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md \
  docs/backend-vnext/refactoring/formal/plans/p4-durable-operation-runtime-design.md \
  docs/backend-vnext/refactoring/formal/plans/p4-durable-operation-runtime-execution-plan.md \
  docs/backend-vnext/refactoring/formal/plans/p4-r2-durable-store-atomic-transition-handoff.md \
  docs/backend-vnext/refactoring/formal/plans/p4-r3-s0-entry-brief.md \
  docs/backend-vnext/refactoring/formal/plans/p4-r3-worker-lifecycle-execution-plan.md \
  | sha256sum
```

复算结果为`1f5a8238...e75c920`。P4 Active Context和formal README只负责检索/
状态接线，不拥有本文接受的runtime、lifecycle或deployment语义，因此不进入
candidate semantic document set。

## 2. Independent acceptance decisions

### 2.1 Owner and import direction — PASS

`gateway_backend.operations` 只拥有SQLite-neutral worker mechanism、scheduler、
`LeaseSession`、`ExecutionControl`和worker-local lifecycle，且已有architecture gate禁止其
import settings、infrastructure、capabilities、FastAPI/uvicorn和Repository packages。
`gateway_backend.bootstrap` 只作settings、signal、concrete control-DB与process-exit的
composition root。R4保持JobDefinition/payload/successor owner，R5保持retry/takeover/
effect-reconcile owner，P5保持business、HTTP/global readiness和deployment owner。

Operation lifecycle Contract与ADR 0016已仅增加owner reference：R3拥有worker进程内
signal/lifecycle，P5拥有deployment/container signal、HTTP readiness/admission和全局
quiescence汇总。没有改变状态、`180s`、`DRAINING_TIMEOUT`或force语义。

### 2.2 LeaseSession and publication freshness — PASS

`LeaseSession` 是每个active lease的进程内单写通道，不是durable closure、
JobDefinition或recovery entry。它序列化heartbeat/checkpoint/terminal publication，且
每次在fresh write UoW内重读record并复用R1 guard、R2 action与SQL CAS。candidate
builder只能对transaction-fresh record执行有界纯内存构造；handler、network、
artifact/Repository I/O、sleep或长计算均不得在lock/DB transaction内运行。

### 2.3 Registry preflight and R2 reuse — PASS

R2已公开`list_claim_candidates(limit=1)`、`ClaimCandidate.job_step_key`和
`OperationLifecycleActions.claim_one`。R3可在同一write UoW/`BEGIN IMMEDIATE`中执行
candidate lookup -> bounded in-memory resolve -> `claim_one` -> exact identity assertion；
`claim_one`的第二次读发生在同一transaction snapshot/lock内。missing handler可在
任何mutation前fatal block，不需要改R2 schema、store port、error taxonomy或CAS。

### 2.4 Startup topology and readiness boundary — PASS

startup顺序固定为migration -> complete active integrity scan -> complete topology/registry
validation -> recovery hook -> repeat both complete validations -> scheduler。R2 status-scoped
operation pages、operation-scoped step pages和active integrity cursor足以验证每个非终局
Operation恰有一个一致active Step。`MANUAL_RECOVERY_REQUIRED`只告警且不claim；
empty DB/empty registry可idle；runnable unknown key、corruption、higher schema和R5尚未能
解释的expired `RUNNING`全部fail closed。worker-local `READY_TO_CLAIM`不冒充
backend HTTP/global readiness。

### 2.5 Heartbeat, cancellation, lease loss and drain — PASS

heartbeat只延长原worker/token lease并通过同一session发布；`StoreBusy`只在当前
lease剩余预算内重试，definitive stale/expired立即设置单调`lease_lost`。cancel
来自durable record并在effect/checkpoint边界合作传播；drain只停止新claim，
不cancel Operation。safe handoff只能在checkpoint commit后确认；180秒超时不
kill/detach executor、不停heartbeat、不伪造terminal/retry/manual state。因此R3没有
吸收R4的业务publication policy或R5的recovery decision。

### 2.6 Module entrypoint and current image — PASS

当前Dockerfile以`uv sync --no-install-project`构建并设置
`PYTHONPATH=/app/backend/src`，所以`python -m gateway_backend.bootstrap.operation_worker`
是与现有image一致的权威入口。R3不修改`pyproject.toml`、lock、Dockerfile、
default uvicorn `CMD`或已有stale console script。S3b因引入真实process entrypoint而
记录container gate deferred，S7必须对最终当前HEAD重建image并运行worker smoke。

### 2.7 Deployment and reopen boundary — PASS

V1的可执行假设是single host、single operation-worker process、reliable local
SQLite/WAL volume、同一Service euid/trust domain和deployment-wide `max_in_flight=1`。
方案不预建membership、leader、global permit、IPC、sidecar或新principal。同机多worker
需重开R3/P5 scheduler/deployment/readiness并增加contention/capacity gate；全局额度需
重开coordination owner；multi-host/NFS/external DB需重开R2 storage/deployment ADR。
每个触发条件都对应明确owner和验证点。

### 2.8 Step split, tests and reviews — PASS

S1a只冻结ports/control，S1b独立证明fresh-transaction publication，S2a在无thread情况
下证明startup/topology/claim，S2b再引入scheduler/executor/heartbeat，S3a建立
signal-independent lifecycle，S3b最后组合settings/SQLite/process。S4、S6是强制新对话
review；S5仅在finding存在时实施，避免空production step；S7拥有当前
HEAD image gate。unit/integration/serial marker、five-package static gate和docs/container
provenance均有明确owner，没有空验收步骤。

## 3. Acceptance checklist

| Gate | Result | Evidence / condition |
| --- | --- | --- |
| R2 handoff identity | PASS | input `e9adbb0`; validated code `31235dc` remains ancestor |
| R2 source/test drift | PASS | committed and worktree diffs under backend source/tests are empty |
| Operations/bootstrap/R4/R5/P5 owner | PASS | one-way imports and policy/composition owners are explicit |
| LeaseSession builder boundary | PASS | process-local callback; bounded in-memory construction only inside transaction |
| Registry preflight reuse | PASS | existing candidate/action ports suffice in one write UoW; no schema/API extension |
| Startup/double-scan/topology | PASS | full pages, exact active-Step topology, MANUAL/empty/fatal boundaries frozen |
| Heartbeat/cancel/lease-loss/drain | PASS | session serialization and fail-closed policy split are explicit |
| Module entrypoint/image fit | PASS | `python -m` works with source-on-`PYTHONPATH` image layout |
| Single-worker/reopen boundary | PASS | local-volume assumptions and three evolution levels have owners/gates |
| Step/test/review/container split | PASS | S1a–S7 each owns a distinct result; S5 is explicitly conditional |
| Contract/ADR clarification | PASS | owner reference only; no state, 180s or force semantic change |
| Container/dependency applicability | N/A | S0 is documentation-only; current-HEAD image gate remains required at R3-S7 |
| Open findings | PASS | none |
| S1a implementation authorization | NO | requires committed S0 identity and explicit new user authorization |

## 4. Verification and applicability

S0按plan只运行document/provenance gates，未运行Python tests、ruff/mypy或container gate：

```text
git merge-base --is-ancestor 31235dc820472a5ca2c99138fdf150090cfe122d HEAD
  -> pass
git diff --name-only 31235dc820472a5ca2c99138fdf150090cfe122d..HEAD -- vnext/backend/src vnext/backend/tests
  -> empty
git diff --name-only -- vnext/backend/src vnext/backend/tests
  -> empty
candidate semantic document set sha256
  -> 1f5a82384023b44353636f63323c5e6bbb4abf623fa072d37fb16e980e75c920
relative Markdown link target validation for all S0 changed documents
  -> pass; zero missing local targets
git diff --check, including each untracked S0 document
  -> pass
```

```yaml
container_rebuild_required: no
container_reason: documentation_only_owner_reference_and_acceptance_status_changes
last_verified_image_revision: none_for_phase_4_candidate
container_gate: not_applicable_for_s0
required_execution_point: P4-R3-S7_final_current_HEAD
benchmark: not_applicable_no_performance_claim
python_tests: not_run_by_s0_plan
five_package_static: not_run_by_s0_plan
```

## 5. Decision and next prerequisites

`p4_r3_s0: accepted`表示R3 worker/process lifecycle设计与逐step execution plan已收敛，
可作为后续实施authority。它不表示worker、settings、tests或entrypoint已实现，
`p4_r3_s1a_authorized: no` 和 `p4_r3_implementation_authorized: no` 保持不变。

开始S1a前必须：

1. 将本S0 documentation candidate作为docs-only revision封存，S1a handoff记录实际input SHA；
2. 获得明确的`P4-R3-S1a` implementation authorization；
3. 在新对话重新核对worktree、input ancestry与R2 source/test tree identity；
4. 只执行detailed plan §8允许的worker port/export/architecture paths，不提前引入
   SQLite、thread、settings或bootstrap。

若封存前candidate摘要、accepted owner/transaction/lifecycle/deployment边界发生变化，
必须重新复算并re-review，不得沿用本PASS。

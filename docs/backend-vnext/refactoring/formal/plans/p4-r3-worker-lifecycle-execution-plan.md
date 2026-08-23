# P4-R3 Worker and Process Lifecycle Detailed Execution Plan

状态：**S0 ACCEPTED — S1a IMPLEMENTATION NOT AUTHORIZED**

日期：2026-08-24

Owner：Operation Worker Runtime + Backend Bootstrap

设计输入：[P4-R3-S0 Entry Brief](p4-r3-s0-entry-brief.md)

上游封存：[P4/R2 Durable Store and Atomic Transition Handoff](p4-r2-durable-store-atomic-transition-handoff.md)

默认入口：[P4 Active Context Index](p4-active-context-index.md)

## 1. Purpose and authorization boundary

本文按当前代码的真实依赖、事务、线程和容器边界拆分R3，使后续可用短提示
词只执行一个named step。实现步骤不是对通用S模板的机械填充：

- S1a固化R4/R5将消费的SQLite-neutral worker port；
- S1b单独建立single-writer `LeaseSession`；
- S2a实现不需线程的startup/topology/atomic claim；
- S2b再引入executor thread、scheduler和heartbeat；
- S3a在scheduler稳定后加signal-independent drain/lifecycle；
- S3b最后接settings、concrete UoW、module CLI和真实process evidence；
- S4–S7是本仓库必需的review、remediation、independent review和module gate。

```yaml
module: P4-R3
input_handoff_sha: e9adbb03603e04bca5981c363fa01ac11576fbe7
input_validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
input_design_document: p4-r3-s0-entry-brief.md
input_design_document_sha: pending_s0_documentation_commit
p4_r2_exit: pass
p4_r3_s0_acceptance: accepted
p4_r3_implementation_authorized: no
first_implementation_step: P4-R3-S1a
first_implementation_step_authorized: no
```

本计划已通过 [P4-R3-S0 Independent Entry Acceptance](p4-r3-s0-entry-acceptance.md)。
本文不授权Python、tests、settings或container变更；S1a仍需单独授权。

## 2. Actual code inventory and consequences

### 2.1 Reused production seams

R3直接复用：

```text
gateway_backend.operations.contracts
  OperationRecord / StepRecord / JobStepKey / status enums

gateway_backend.operations.state
  WritePrecondition / transition guards / stale-write validation

gateway_backend.operations.store
  OperationStore / OperationUnitOfWork / ClaimCandidate / integrity scan
  RecordNotFound / StaleWrite / LeaseExpired / StoreBusy / corruption errors

gateway_backend.operations.persistence
  OperationLifecycleActions.claim_one
  mutate_live_step / cancel_intent
  complete_with_successor / complete_operation

gateway_backend.infrastructure.control_db
  initialize_control_db / ControlDbUnitOfWork
```

`ControlDbUnitOfWork` 每次enter新建connection，write使用`BEGIN IMMEDIATE`，事务时钟只
采样一次，adapter rollback-only会阻止意外commit。R3不重写这些机制。

### 2.2 Constraints discovered from current code

- `test_architecture.py` 已禁止Operations import settings、infrastructure、capabilities、
  FastAPI/uvicorn或Repository packages；R3只能扩展，不得放宽；
- R2 UoW只暴露transaction-scoped store；R3必须注入UoW factory，不把concrete UoW
  import到Operations；
- R2 `claim_one` 会重读第一candidate；R3 registry preflight与`claim_one`必须在同一
  write UoW内；
- heartbeat是same-status versioned mutation；executor不能直接使用claim snapshot发布；
- R2 active scan证明row/owner，但partial unique index只证明“最多一个”active Step；
  R3 startup还必须证明每个非终局Operation“恰有一个”active Step；
- 当前`settings.py`只有`BackendSettings.artifact_root`，`app.py`只有`/healthz`；R3不改
  它们的现有语义；
- Dockerfile使用`uv sync --no-install-project`并靠`PYTHONPATH`运行source；`project.scripts`
  不会安装到image；
- 现有`gateway-backend = gateway_backend:main`也无对应`main`；R3不借机整改整个
  packaging boundary。

因此R3 V1权威进程入口冻结为：

```text
python -m gateway_backend.bootstrap.operation_worker
```

S3b不修改`pyproject.toml`、`uv.lock`或Dockerfile安装方式。若后续确需
`gateway-operation-worker`命令，单独重开packaging/Dockerfile，并同时处理现有stale
`gateway-backend` script。

## 3. Frozen boundary

In scope：worker/executor/registry/recovery/observer ports、`ExecutionControl`、`LeaseSession`、
double startup gate、atomic claim、single executor、heartbeat、cancel propagation、drain、worker settings、
module CLI、file/process/container evidence。

Out of scope：R4 JobDefinition/payload/successor policy；R5 retry/takeover/effect reconcile；P5 T1/T3、
HTTP/global readiness/Compose；R1/R2 schema/state/error changes；multiple workers、global permits、HA；
metrics SDK、durable evidence、IPC；async/thread pool/process pool/fan-out/thread kill。

## 4. Protocol for short follow-up prompts

后续提示词可只写：

```text
执行 P4-R3-S2a，严格按 detailed execution plan 完成本 step 与 handoff，
不开始下一 step。
```

执行者必须自动：

1. 读Active Context、R3-S0 brief、本plan、上一handoff和Git状态；
2. 核对input/validated SHA ancestry和source/test tree identity；
3. 保留unrelated用户变更，拒绝未记录in-scope drift；
4. 只修allowed paths，命中stop/reopen时立即停止；
5. 运行focused、适用regression/static/container gates并review diff；
6. 记录HEAD、container/benchmark applicability和findings；
7. code step使用“candidate code commit + docs-only handoff commit”两段seal；
8. handoff只指向下一step，不自动开始/授权下一step。

若短提示没有明确授权commit，执行者应先完成代码、验证和diff review，然后
报告commit待授权；不得从本plan推导当前commit权限。

## 5. Conversation strategy

一个named step的implementation、validation、diff review和handoff应在同一对话完成；不同step
默认新开对话，以handoff取代隐式记忆。

| Step | Recommendation | Reason |
| --- | --- | --- |
| S0 | **必须新对话** | independent acceptance不继承设计讨论偏置 |
| S1a | **新对话** | public port/export约束后续全部实现 |
| S1b | **新对话** | 事务freshness/atomic publication高风险 |
| S2a | **新对话** | startup/topology/claim是独立consistency seam |
| S2b | **新对话** | 首次引入thread/heartbeat |
| S3a | **新对话** | signal/drain需从lifecycle contract重建上下文 |
| S3b | **新对话** | 跨越Operations到bootstrap/settings/process |
| S4 | **必须新对话** | reviewer与实现对话隔离 |
| S5 | **默认新对话** | 依S4 finding record实施；纯docs follow-up可留S4 |
| S6 | **必须新对话** | independent review不继承实现/S4假设 |
| S7 | **新对话** | final gate只依sealed handoffs和HEAD evidence |

不建议同一超长对话连续做S1a–S3b。如不得不继续当前对话，每步仍必须从
磁盘重读context/handoff，不依赖聊天记忆。

## 6. Shared handoff and gates

每个handoff/review至少记录：

```yaml
step_id:
input_handoff_sha:
input_validated_code_sha:
validated_code_sha:
validated_source_tree:
result: pass | rework_required
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
benchmark:
findings: []
deferred_items: []
reopen_conditions: []
next_step:
next_step_authorized: yes | no
```

Focused files：

```text
tests/test_operation_worker_contracts.py
tests/test_operation_lease_session.py
tests/test_operation_worker_startup.py
tests/test_operation_worker_scheduler.py
tests/test_operation_worker_lifecycle.py
tests/test_operation_worker_integration.py
tests/test_operation_worker_process.py
tests/test_architecture.py
```

Shared final commands（步骤内按实际文件收窄）：

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

五包static还包括`shared_kernel`、`repository_contracts`、`repository_client`、
`repository_service`各自`uv run ruff check . && uv run mypy`。R3不需Dolt或network。

`Event.wait(timeout=...)`、`thread.join(timeout=...)`、真实signal/subprocess标`serial`；on-disk
SQLite/subprocess标`integration`；纯fake clock/wait/state标`unit`。

## 7. S0 — Independent entry acceptance

```yaml
step_id: P4-R3-S0
change_kind: docs_only
context: mandatory_new_conversation
```

Entry：R2 S7 PASS；`31235dc` 仍是HEAD ancestor；R2 source/test tree无漂移；本brief/plan
已是可审查docs candidate。

Allowed paths：

```text
docs/backend-vnext/refactoring/formal/plans/p4-r3-s0-entry-brief.md
docs/backend-vnext/refactoring/formal/plans/p4-r3-worker-lifecycle-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p4-r3-s0-entry-acceptance.md
docs/backend-vnext/refactoring/formal/plans/p4-active-context-index.md
docs/backend-vnext/refactoring/formal/contracts/operation-lifecycle-and-integrity.md
docs/backend-vnext/refactoring/formal/adr/0016-graceful-lifecycle-and-integrity-recovery.md
docs/backend-vnext/refactoring/formal/README.md
```

ADR/Contract只允许纯owner-reference clarification。只允许明确“R3拥有process-local
signal/lifecycle，P5拥有deployment/HTTP/global readiness/quiescence”；不改状态、180s或
force semantics。

Required review：

1. Operations/bootstrap/R4/R5/P5 owner与import方向；
2. LeaseSession builder不是durable closure且不在DB事务运行handler/I/O；
3. registry preflight可复用R2 port，无schema/API扩展；
4. startup topology/double scan/MANUAL/empty registry边界；
5. heartbeat/cancel/lease-loss/drain不吸收R4/R5 policy；
6. `python -m`入口与当前image的`--no-install-project`一致；
7. single-worker/local-volume/multi-worker reopen可执行；
8. step split、tests、reviews和container gate无空步骤。

Exit：输出`p4-r3-s0-entry-acceptance.md`，明确
`p4_r3_s0: accepted | rework_required`、`p4_r3_s1a_authorized: no`。只运行docs link/provenance/
`git diff --check`，不运行Python/container gates。

## 8. S1a — Worker contracts and execution control

```yaml
step_id: P4-R3-S1a
context: new_conversation
```

Why separate：这一步冻结R4/R5的消费面，不需SQLite、thread、settings或bootstrap。

Allowed：

```text
vnext/backend/src/gateway_backend/operations/worker.py
vnext/backend/src/gateway_backend/operations/__init__.py
vnext/backend/tests/test_operation_worker_contracts.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r3-s1a-handoff.md
```

Implementation：

1. frozen/slots lifecycle、startup disposition、executor acknowledgment和bounded event values；
2. `ExecutionControl`只暴露单调drain/cancel/lease-lost边界，不暴露内部thread primitive；
3. structural protocols：immutable registry/resolver、claimed executor、recovery hook、observer、
   read/write UoW factory；
4. executor只接R1 records、control和LeaseSession protocol，不接SQLite/Repository/business context；
5. controlled `__all__`；不公开private lock/event/helper或generic `WorkerError`；
6. 不创建`NotImplementedError`、production fake registry或无consumer framework。

Tests：exact exports/signatures/protocols；frozen/bounded/redacted values；control monotonicity；reuse
`JobStepKey`；architecture import gate。不创建SQLite/thread/subprocess。

Commands：

```bash
cd vnext/backend
uv run pytest -q -m unit tests/test_operation_worker_contracts.py tests/test_architecture.py
uv run ruff check . && uv run mypy
```

Review：R4/R5 policy leakage、public type过多、mutable registry、thread leakage、新error taxonomy、
import方向。Container N/A；仅handoff到S1b。

## 9. S1b — LeaseSession and atomic publication

```yaml
step_id: P4-R3-S1b
context: new_conversation
```

Why separate：它是核心consistency seam，必须在scheduler前独立证明publication freshness。

Allowed：

```text
vnext/backend/src/gateway_backend/operations/lease_session.py
vnext/backend/src/gateway_backend/operations/worker.py
vnext/backend/src/gateway_backend/operations/__init__.py
vnext/backend/tests/test_operation_lease_session.py
vnext/backend/tests/test_operation_worker_contracts.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r3-s1b-handoff.md
```

Implementation：

1. session固定worker/token/operation/step/UoW factory/control/observer；
2. 每次mutation使用fresh write UoW，重读Operation/Step，验identity、RUNNING、worker/token、
   live lease并传播cancel；
3. closed publication shapes只映射：same-status checkpoint；terminal Step + PENDING successor；
   terminal/manual Step + terminal/manual Operation；
4. builder只用fresh records/transaction_now做有界纯内存构造，不做I/O/wait/handler；
5. 只调R2 `mutate_live_step`/`complete_with_successor`/`complete_operation`；
6. heartbeat method只延长同一worker/token lease并version+1；
7. stale/expired设lease-lost并禁止后续publication；
8. safe handoff必须绑定到session已commit的checkpoint generation。

Tests：fresh UoW/clock；heartbeat后checkpoint观察新version；external cancel；stale/expired/
identity mismatch；builder/second-leg rollback；reject terminal-only Step；safe-handoff commit barrier。使用
fake UoW/store，不穷举thread timing。

Focused：

```bash
cd vnext/backend
uv run pytest -q -m unit tests/test_operation_worker_contracts.py \
  tests/test_operation_lease_session.py tests/test_architecture.py
uv run ruff check . && uv run mypy
```

Review：持锁期间handler/I/O、old-snapshot rebase、绕过R2 actions、cancel reset、token log。
Container N/A；仅handoff到S2a。

## 10. S2a — Startup, topology and atomic claim

```yaml
step_id: P4-R3-S2a
context: new_conversation
```

Allowed paths：

```text
vnext/backend/src/gateway_backend/operations/worker_startup.py
vnext/backend/src/gateway_backend/operations/worker.py
vnext/backend/src/gateway_backend/operations/__init__.py
vnext/backend/tests/test_operation_worker_startup.py
vnext/backend/tests/test_operation_worker_contracts.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r3-s2a-handoff.md
```

Implementation：

1. 循环R2 active integrity cursor直到完整扫描；
2. 通过status/step keyset pages枚举非终局Operation，验证恰一active Step、owner、
   runnable registry coverage；MANUAL只告警不claim；
3. 顺序固定为integrity -> topology/registry -> recovery -> 再次完整验证；
4. recovery只READY/RETRYABLE_BLOCK/FATAL_BLOCK，fatal不调scheduler；
5. atomic claim在一个write UoW内完成candidate(limit=1) -> in-memory resolve -> `claim_one`
   -> exact identity assertion -> commit；
6. boot worker ID和per-claim token使用可注入factory，production为typed-prefix UUID4；
7. 不启thread/signal/settings/concrete DB。

Tests：multi-page/double scan；QUEUED/RUNNING/MANUAL topology；zero/multiple/mismatch active Step；
missing key无mutation；preflight/claim identity；empty DB/registry；recovery后新corruption/key；可中断
retry。不复制R2 corruption shape matrix。

Focused：

```bash
cd vnext/backend
uv run pytest -q -m unit tests/test_operation_worker_contracts.py \
  tests/test_operation_worker_startup.py tests/test_architecture.py
uv run ruff check . && uv run mypy
```

Review：分页完整、recovery后重验、MANUAL错claim、transaction内resolver I/O、unknown-key
prefix。Container N/A；仅handoff到S2b。

## 11. S2b — Scheduler, executor and heartbeat

```yaml
step_id: P4-R3-S2b
context: new_conversation
```

Allowed paths：

```text
vnext/backend/src/gateway_backend/operations/worker_runtime.py
vnext/backend/src/gateway_backend/operations/worker.py
vnext/backend/src/gateway_backend/operations/lease_session.py
vnext/backend/src/gateway_backend/operations/__init__.py
vnext/backend/tests/test_operation_worker_scheduler.py
vnext/backend/tests/test_operation_lease_session.py
vnext/backend/tests/test_operation_worker_startup.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r3-s2b-handoff.md
```

Implementation：

1. main thread负责claim/poll/heartbeat orchestration；
2. 一次claim创建一session/control/non-daemon executor thread，永不存在第二executor；
3. executor return只能是经session证明的terminal/successor publication或drain safe handoff；
   无证明normal return是worker-fatal；
4. main thread以monotonic deadline做10s heartbeat；
5. heartbeat StoreBusy只在lease剩余预算内retry，截止后转lease-lost；
6. heartbeat/publication传播cancel；
7. executor异常不发FAILED/RETRY，停heartbeat/新claim并worker-fatal；
8. idle poll 1s，busy backoff 1–10s+jitter，wait可被stop中断；
9. 不安装OS signal或bootstrap/settings。

Tests：empty queue no busy loop；one claim/one executor；no overlap；heartbeat/publication serialization；
concurrent cancel；busy deadline；stale/expired fence；executor/unproven return/observer failure。本步使用
deterministic runner/barrier；权威真thread/process serial owner留给S3b。

Focused：

```bash
cd vnext/backend
uv run pytest -q -m unit tests/test_operation_lease_session.py \
  tests/test_operation_worker_startup.py tests/test_operation_worker_scheduler.py \
  tests/test_architecture.py
uv run ruff check . && uv run mypy
```

Review：thread硬上限、DB跨线程、interruptible waits、busy越过lease、伪造终局。Container
N/A；仅handoff到S3a。

## 12. S3a — Drain and process-local lifecycle

```yaml
step_id: P4-R3-S3a
context: new_conversation
```

Allowed paths：

```text
vnext/backend/src/gateway_backend/operations/worker_lifecycle.py
vnext/backend/src/gateway_backend/operations/worker_runtime.py
vnext/backend/src/gateway_backend/operations/worker.py
vnext/backend/src/gateway_backend/operations/__init__.py
vnext/backend/tests/test_operation_worker_lifecycle.py
vnext/backend/tests/test_operation_worker_scheduler.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r3-s3a-handoff.md
```

Implementation：

1. 只允许`STARTING -> READY_TO_CLAIM -> DRAINING -> QUIESCED -> STOPPING -> EXITED`
   及`DRAINING -> DRAINING_TIMEOUT`；
2. signal-independent API只接单调drain intent；OS handler留S3b；
3. drain停止新claim、传给executor、继续heartbeat；
4. publication或经session证明checkpoint handoff后才QUIESCED；
5. checkpoint-only保持RUNNING，停heartbeat并clean exit，不写RETRY/MANUAL；
6. 180s fake-monotonic deadline后DRAINING_TIMEOUT，不kill/detach/停heartbeat；
7. repeated drain幂等，不force；drain不写cancel；
8. worker-local QUIESCED不声称global activity为零。

Tests：idle drain；active executor + heartbeat；safe-handoff commit barrier；terminal/drain race；
fake 180s timeout/no-force；repeated intent；drain-not-cancel。全部使用deterministic runner/clock；
权威真thread/signal/process owner留S3b。

Focused：

```bash
cd vnext/backend
uv run pytest -q -m unit tests/test_operation_worker_scheduler.py \
  tests/test_operation_worker_lifecycle.py tests/test_architecture.py
uv run ruff check . && uv run mypy
```

Review：drain/cancel混淆、timeout停heartbeat、daemon/detach、second-signal force、persisted/global
lifecycle leakage。Container N/A；仅handoff到S3b。

## 13. S3b — Settings, bootstrap, module CLI and process evidence

```yaml
step_id: P4-R3-S3b
context: new_conversation
```

Allowed：

```text
vnext/backend/src/gateway_backend/bootstrap/__init__.py
vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
vnext/backend/src/gateway_backend/settings.py
vnext/backend/tests/test_operation_worker_process.py
vnext/backend/tests/test_operation_worker_integration.py
vnext/backend/tests/test_operation_worker_lifecycle.py
vnext/backend/tests/test_architecture.py
vnext/backend/README.md
docs/backend-vnext/refactoring/formal/plans/p4-r3-s3b-handoff.md
```

Forbidden：`pyproject.toml`、`uv.lock`、Dockerfile、Compose、`app.py`。

Implementation：

1. 新增独立`OperationWorkerSettings`，env prefix为
   `GATEWAY_BACKEND_OPERATION_WORKER_`，不改`BackendSettings`现有field/default/env；
2. 要求absolute control DB file path，冻结30/10s lease/heartbeat、1s poll、1–10s backoff、
   60s startup、180s drain和fixed concurrency/claim；
3. bootstrap只创建server-owned DB parent，然后`initialize_control_db`；
4. 组合concrete UoW factory、empty immutable registry、fail-closed recovery、observer、UUID；
5. main thread安装SIGTERM/SIGINT，handler只设event；无SIGHUP/second-signal force；
6. 提供`python -m gateway_backend.bootstrap.operation_worker`，不修console scripts；
7. empty DB可ready/idle；runnable record在claim前fatal，不留RUNNING；
8. 只保证0 clean/non-zero failure，原因由event code；
9. 不建HTTP/socket/pidfile/ready file，不改app/Compose。

Tests：

- settings env/absolute path/budgets和BackendSettings回归；
- bootstrap parent、empty composition、log redaction、bootstrap architecture imports；
- local SQLite/WAL bootstrap/double scan/reopen；
- heartbeat + concurrent cancel file readback；
- subprocess ready -> SIGTERM -> drain/no-new-claim/exit 0；
- process termination保留RUNNING/checkpoint且lease过期，不证明takeover；
- corruption/higher-schema/missing-handler非零且无path/token leak；
- subprocess按批复用harness，不为每个shape重复spawn。

Commands：shared focused unit、`integration and not serial`、serial、backend ruff/mypy。

Container：此步触及process entrypoint/settings/startup/shutdown，记录
`container_rebuild_required: yes`、`container_gate: deferred`、
`required_execution_point: P4-R3-S7 final candidate`。可做diagnostic build，但不替代S7当前HEAD
gate。仅handoff到S4。

## 14. S4 — Focused review

```yaml
step_id: P4-R3-S4
context: mandatory_new_conversation
change_kind: review_docs_only
```

Reviewer必须读全部R3 production source、权威tests、S1a–S3b handoffs和actual diff，不只读
handoff。必审：

Allowed change：只新增/更新
`docs/backend-vnext/refactoring/formal/plans/p4-r3-s4-focused-review.md`。Reviewer不就地修改
production/tests；需probe时使用临时命令或记录后交S5/S6。

1. owner/import/public surface；
2. atomic registry preflight + claim是否mutation-free on failure；
3. integrity/topology/registry/recovery/double-scan是否完整；
4. LeaseSession fresh UoW/record、closed shapes、no terminal-only Step；
5. heartbeat busy/stale/expired/token fencing；
6. one non-daemon executor、no DB cross-thread、bounded interruptible waits；
7. cancel-before-effect、drain-not-cancel、timeout-no-force；
8. executor/observer/builder/invariant failure不伪造终局或继续claim；
9. module CLI在当前image可运行且无packaging/app/Compose leakage；
10. tests的unit/integration/serial owner、无重复private-interleaving matrix；
11. redaction和无durable evidence/IPC扩张；
12. single-worker/local-volume/container deferral/capacity claim边界。

P1/P2、contract ambiguity、stale-writer gap、unknown-key prefix、unsafe drain或无界thread必须
`rework_required`。跨R1/R2/R4/R5/P5/deployment/security的finding必须reopen，不在S5静默修。
输出`p4-r3-s4-focused-review.md`和finding/disposition table。

## 15. S5 — Conditional remediation

S4无finding时记录`not_applicable_no_findings`，不创建空production/test step。有in-boundary
finding时，先在remediation appendix写：finding/severity/owner/allowed paths/production change/
regression/commands/closure/reopen/container impact，然后才修。

S5的docs paths固定为
`p4-r3-s5-remediation-appendix.md`与`p4-r3-s5-handoff.md`；production/test allowed paths必须是
appendix逐finding列出的S1a–S3b已授权边界子集，不得用“R3全部”作宽泛范围。

每项修复运行finding regression、受影响focused files、backend ruff/mypy和S4 focused rereview。
entrypoint/settings/process harness的container触发仍合并到S7最终一次build。产生S5 handoff，
不自动进S6。

## 16. S6 — Independent review

```yaml
step_id: P4-R3-S6
applicability: required
context: mandatory_new_conversation
```

Independent reviewer只依sealed docs、source/tests和Git evidence。必做八个bounded probes：

Allowed changes：

```text
docs/backend-vnext/refactoring/formal/plans/p4-r3-s6-independent-review.md
vnext/backend/tests/test_operation_worker_integration.py   # only if a reusable probe is required
vnext/backend/tests/test_operation_worker_process.py       # only if a reusable probe is required
```

任何production defect必须记录finding并回S5，不在S6修production。

1. unknown-key first candidate不留RUNNING；
2. 多次heartbeat后checkpoint/terminal不用claim version；
3. 独立connection cancel在effect boundary前可观察且不可清除；
4. busy-to-expiry或stale writer后publication/新claim被fence；
5. checkpoint commit前/后process termination的代表性barrier；
6. fake timeout后不停heartbeat/detach/kill；
7. recovery造成新unknown successor/corruption被第二次gate拒绝；
8. failure logs无token/path/payload/SQL且exit非0。

不穷举SQL/thread schedules。S6不就地修production；发现defect输出finding并回S5。
输出`p4-r3-s6-independent-review.md`。P1/P2/ambiguity/fence/shutdown/container-trigger findings全部
closed/reopen后才进S7。

## 17. S7 — Module gate, current-HEAD image and handoff

Entry：S4 pass，适用S5 closed，S6 pass；final source/test committed；validated candidate是HEAD
ancestor；无未记录in-scope changes。

Allowed changes：S7默认只修改
`p4-r3-worker-lifecycle-handoff.md`、`p4-active-context-index.md`、formal `README.md`与本plan/
brief中的状态、SHA、命令结果或owner-reference。如gate发现source/test defect，停止S7并
回S5，不在module-gate对话即兴修production。

Required gates：

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_operation_contracts.py tests/test_operation_state.py \
  tests/test_operation_store.py tests/test_control_db_migrations.py \
  tests/test_sqlite_operation_store.py \
  tests/test_operation_worker_contracts.py tests/test_operation_lease_session.py \
  tests/test_operation_worker_startup.py tests/test_operation_worker_scheduler.py \
  tests/test_operation_worker_lifecycle.py tests/test_architecture.py
uv run pytest -q -m unit
uv run pytest -q -m 'integration and not serial' \
  tests/test_sqlite_operation_store_integration.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
uv run pytest -q -m serial \
  tests/test_sqlite_operation_store_integration.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
uv run ruff check .
uv run mypy
```

再运行其余四包ruff/mypy、`git diff --check`、SHA ancestry和source/test tree identity。R3不
运行Dolt/Repository integration。

Current-HEAD container gate：

```text
docker build -f vnext/backend/Dockerfile -t <r3-candidate-tag> vnext
docker run ... \
  -e GATEWAY_BACKEND_OPERATION_WORKER_CONTROL_DB_PATH=/var/lib/gateway/control/control.sqlite3 \
  <r3-candidate-tag> \
  python -m gateway_backend.bootstrap.operation_worker
```

用`mktemp -d`创建精确host DB目录并挂载到明确container parent；观察`worker_ready`；
发SIGTERM；断言idle drain/`worker_exited`/exit 0；reopen DB验证schema/WAL；检查log无
path/token；记录Git SHA、tree hash、image ID/digest、commands和cleanup。只清理本gate精确
创建的container/tag/temp path。

container gate后修改source/settings/entrypoint/Dockerfile/process harness会使image失效，必须重建。
docs-only handoff descendant必须同时记录documentation HEAD和image source SHA/tree identity。

输出`p4-r3-worker-lifecycle-handoff.md`，包含validated SHAs、applicable/skipped steps、public
symbols、module entrypoint、settings、startup/claim/session/heartbeat/lifecycle matrices、reviews、gates、
image provenance、single-worker/local-SQLite/empty-registry limits、deferred/reopen和`next_entry: P4-R4-S0`。

R3 handoff只允许R4-S0 discussion，不授权R4/R5/P5实现或真实Repository effect。

## 18. Global stop/reopen rules

任何step命中以下情况立即停止：

- 需改R1 record/status/transition/precondition或R2 schema/migration/errors/CAS；
- 需direct RUNNING lease swap或terminal Step-only publication；
- registry preflight与claim无法同一write UoW完成；
- Operations需import settings/infrastructure/application/capabilities/Repository；
- DB transaction内需handler/network/artifact/长计算；
- R3需选retry/manual/takeover、解释job payload/effect；
- 需多executor、dynamic registry、hot reload、fan-out或thread kill；
- 需HTTP/global readiness、T1/T3、outbox、Compose或Repository integration；
- 需durable worker membership/permit、leader、IPC、broker、sidecar或新principal；
- 部署不再single-host/single-worker/local reliable SQLite；
- representative R4 handler占用GIL使heartbeat无法满足30/10s budget；
- active-set startup scan实测超出deployment recovery objective；
- 需改Dockerfile/project-install mode来安装console script；
- 出现现有unit/integration/serial/container分类无法表达的新高风险边界。

处理顺序：evidence -> finding -> owning Contract/ADR decision -> 更新brief/plan ->
finding-scoped implementation -> focused/independent rereview。

## 19. Recommended short prompts

S0：

```text
在新对话执行 P4-R3-S0 independent entry acceptance。按R3 detailed plan审查
实际代码接缝、设计和步骤；只修docs acceptance，不改source/tests，不授权S1a。
```

Code step：

```text
执行 P4-R3-S1a，按R3 detailed execution plan完成本step的实现、focused gates、
diff review和handoff，不开始S1b。
```

S4/S6/S7：

```text
在新对话执行 P4-R3-S4 focused review，从sealed handoffs和Git状态独立审查，
只输出finding disposition，不就地修production。

在新对话执行 P4-R3-S6 independent review，按plan运行bounded counterexamples，
不继承实现/S4假设，不就地修production。

在新对话执行 P4-R3-S7 module gate，重跑final gates、重建当前HEAD image、
运行worker container smoke并生成handoff，不开始R4。
```

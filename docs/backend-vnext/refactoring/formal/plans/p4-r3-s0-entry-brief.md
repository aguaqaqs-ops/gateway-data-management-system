# P4-R3-S0 Entry Brief: Worker and Process Lifecycle

状态：**S7 MODULE GATE PASS — P4-R4-S0 DISCUSSION ONLY**

日期：2026-08-24

Owner：Operation Worker Runtime（scheduler、lease session、process-local lifecycle）与
Backend Bootstrap（worker settings、CLI composition）

上游：[P4/R2 Durable Store and Atomic Transition Handoff](p4-r2-durable-store-atomic-transition-handoff.md)、
[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)、
[P4 Durable Operation Runtime Execution Plan](p4-durable-operation-runtime-execution-plan.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[ADR 0016](../adr/0016-graceful-lifecycle-and-integrity-recovery.md)、
[Proportional Assurance and Risk-Based Verification Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)

默认入口：[P4 Active Context Index](p4-active-context-index.md)

逐step执行authority：
[P4-R3 Worker and Process Lifecycle Detailed Execution Plan](p4-r3-worker-lifecycle-execution-plan.md)

## 1. Entry identity and authorization boundary

```yaml
step_id: P4-R3-S0
input_handoff_sha: e9adbb03603e04bca5981c363fa01ac11576fbe7
input_validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
p4_r2_exit: pass
p4_r3_entry_discussion_authorized: yes
p4_r3_s0_design: accepted
p4_r3_s0_acceptance: accepted
p4_r3_s1a_authorized: no
p4_r3_implementation_authorized: no_further_r3_work
validated_code_sha: acb3efca06a02aadaa5ce6d1e2a815e85d36e6af
module_gate: pass
next_step: P4-R4-S0 discussion
next_step_authorized: no
```

R2 S7已封存Operations v1的SQLite/WAL store、migration、claim、lease、CAS、active
integrity scan与cross-table transaction seam。当前HEAD是验证代码SHA的documentation-only
后代，R2 source/test tree无漂移，且S4/S5/S6无open finding。

本文固化已由 [P4-R3-S0 Independent Entry Acceptance](p4-r3-s0-entry-acceptance.md)
接受的R3-S0需求与设计。该acceptance本身不是implementation authorization；入口时点的
S1a限制已由后续显式授权、S1a–S7 evidence和本 handoff 封存。当前R3不再开放新的
source/test/settings/container变更；后续只允许P4-R4-S0 entry discussion。

## 2. Objective, users and scenarios

R3为后续R4 JobDefinition和R5 recovery policy提供最小、可运行的durable worker机制：

- 从R2 store顺序claim一个runnable Step；
- 在handler执行期间续租，并对stale/expired worker fail closed；
- 串行化heartbeat、checkpoint和terminal/successor publication，不让它们互相制造
  optimistic-version race；
- 在SIGTERM/SIGINT后停止新claim，允许当前handler完成或在durable checkpoint后安全交接；
- 在startup开放worker-local readiness前完成migration、integrity、registry与recovery gates；
- 通过独立CLI作为同一backend image中的worker角色运行。

直接使用者是P4-R4/R5的registry、executor与recovery-policy owner，以及P5的deployment/
application composition owner。R3不直接面向HTTP用户，不解释Workspace、Submission、Archive
或Repository effect。

## 3. Scope and ownership split

```text
gateway_backend.operations
  owns: worker mechanism ports, scheduler, LeaseSession, ExecutionControl,
        process-local lifecycle and stable worker event codes
  depends on: R1 record/state contracts and R2 SQLite-neutral store/UoW ports
  must not import: infrastructure, settings, application, capabilities,
                   Repository client/service packages

gateway_backend.bootstrap
  owns: OperationWorkerSettings, CLI entrypoint, signal installation,
        concrete control-DB composition and process exit
  may import: operations public ports and control_db infrastructure

future R4
  owns: immutable JobDefinition/executor registry, job payload interpretation,
        checkpoint/READY closure and successor/final candidate policy

future R5
  owns: retry/backoff decision, expired RUNNING disposition, takeover,
        unknown external-effect reconciliation and manual-recovery policy

future P5
  owns: business T1/T3, create-time registry validation, backend HTTP admission,
        global readiness/quiescence aggregation and final Compose wiring
```

R3的signal/readiness只指worker进程内机制；ADR 0016中P5的signal/readiness/container
responsibility指deployment orchestration、backend HTTP对外语义和全局生命周期汇总。S0
acceptance应在ADR/contract owner引用中明确这一拆分，不新增第二套lifecycle语义。

## 4. Frozen deployment and trust boundary

- V1是单主机、单operation-worker进程/replica，整个部署`max_in_flight=1`；
- backend进程不内嵌worker；worker与backend之后通过server-owned本地volume上的同一
  SQLite/WAL control DB协作；
- worker与backend位于同一Service euid/受控信任域；`worker_id`不是认证主体；
- 不新增HTTP端口、Unix socket、pidfile、ready文件、worker-registration table、leader
  election、broker、sidecar或独立UID/helper；
- 使用同一backend image的独立CLI角色，不建立第二distribution或worker-only image；
- R3不修改image默认backend/uvicorn `CMD`，也不完成最终Compose或backend
  `/readyz`接线。

## 5. Candidate physical surface

精确Python signatures由S1冻结；detailed execution plan按当前代码接缝冻结候选落点为：

```text
vnext/backend/src/gateway_backend/operations/worker.py
vnext/backend/src/gateway_backend/operations/lease_session.py
vnext/backend/src/gateway_backend/operations/worker_startup.py
vnext/backend/src/gateway_backend/operations/worker_runtime.py
vnext/backend/src/gateway_backend/operations/worker_lifecycle.py
vnext/backend/src/gateway_backend/bootstrap/__init__.py
vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
vnext/backend/src/gateway_backend/settings.py
vnext/backend/src/gateway_backend/operations/__init__.py
vnext/backend/tests/test_operation_worker_contracts.py
vnext/backend/tests/test_operation_lease_session.py
vnext/backend/tests/test_operation_worker_startup.py
vnext/backend/tests/test_operation_worker_scheduler.py
vnext/backend/tests/test_operation_worker_lifecycle.py
vnext/backend/tests/test_operation_worker_integration.py
vnext/backend/tests/test_operation_worker_process.py
vnext/backend/tests/test_architecture.py
```

文件合并/拆分若需改变上述职责边界，必须先更新detailed plan而不在code step
即兴扩展。Operations不得import `bootstrap`、`settings`或`infrastructure`。根据当前Dockerfile
使用`uv sync --no-install-project`并仅通过`PYTHONPATH`运行source的实际，R3冻结
模块入口为：

```text
python -m gateway_backend.bootstrap.operation_worker
```

R3使用独立`OperationWorkerSettings`，不把worker-only参数混入当前
`BackendSettings`或改变现有`/healthz`响应。
不在R3修改project-install mode或新增image中不会安装的console script；后续对
可执行命令名的真实需求将触发packaging/Dockerfile reopen。

## 6. Worker-local lifecycle

R3的进程内状态是运行时协调信号，不进入R1 persisted document或R2 schema：

```text
STARTING -> READY_TO_CLAIM -> DRAINING -> QUIESCED -> STOPPING -> EXITED
                              |
                              +----------> DRAINING_TIMEOUT
```

- `READY_TO_CLAIM`只表示worker自身startup gates已通过且scheduler可claim；
- 它不等于backend HTTP readiness、业务admission或全局`QUIESCED`；
- SIGTERM和SIGINT都只设置drain intent；signal handler不执行DB I/O、join或业务逻辑；
- 重复signal不自动升级为强杀；R3不支持SIGHUP动态重载settings/registry；
- 进入`DRAINING`后立即停止新claim，但当前lease在executor仍运行时继续heartbeat；
- 180秒内executor正常完成，或在durable checkpoint commit后确认safe handoff，
  worker才能进入`QUIESCED`；
- 超时进入`DRAINING_TIMEOUT`，不自动kill executor、停heartbeat或伪造terminal状态；
- 不合作的handler会阻止正常退出，只能由管理员显式强制终止。

R3不声称它能确认Preview、Submit/finalize、Repository effect、external sync等
全局活动为零；该aggregation仍属P5。

## 7. Startup and readiness gate

worker只能按以下顺序进入`READY_TO_CLAIM`：

```text
validate settings and server-owned path
  -> initialize/migrate control DB
  -> complete active integrity scan
  -> enumerate active records and validate registry coverage
  -> invoke recovery hook
  -> repeat complete active integrity and registry validation
  -> start scheduler
```

规则：

- active scan使用R2 bounded keyset pages，但在readiness前必须扫完，不得抽样；
- 第二次验证用于发现recovery hook造成的状态、successor或registry-coverage变化；
- 枚举阶段还必须验证每个非终局Operation恰有一个与其一致的active Step；
  R2 partial unique index只证明“最多一个”，无active Step的`QUEUED`/`RUNNING`不得静默ready；
- `PENDING | RETRY_WAIT | RUNNING`的active Step必须能由immutable registry解析；
- 合法`MANUAL_RECOVERY_REQUIRED`只告警并保持不可claim，不阻止其他Operation；
- empty DB允许empty registry进入idle scheduler；
- 完整扫描可输出bounded progress log，但不建立durable scan evidence；
- R3不自动修复、quarantine、删除或从宽读取损坏record。

recovery hook的候选结果只有：

```text
READY             scheduler may start
RETRYABLE_BLOCK   bounded startup retry/backoff
FATAL_BLOCK       stable event plus non-zero process exit
```

高版本schema、active corruption、缺失runnable handler或无法安全解释的expired
`RUNNING`属于fatal block。R3不提供“忽略后ready”结果。R3阶段的empty recovery
hook在存在需要R5决策的record时必须fail closed；R5之后注入真实policy。

## 8. Registry and atomic claim discipline

- registry/resolver在worker进程生命周期内immutable；更新handler必须重启worker；
- resolver是纯内存、有界lookup，不进行network、filesystem、artifact或Repository I/O；
- 每次claim在同一`BEGIN IMMEDIATE` UoW中先读取第一个R2 `ClaimCandidate`，
  校验其`JobStepKey`可解析，再执行R2 `claim_one`；
- 因为candidate lookup与claim在同一write transaction中，其间不存在新writer插入
  更早unknown candidate的窗口；
- registry缺失时事务无mutation并fatal block，不得先把Step写成`RUNNING`；
- 每次worker process boot生成fresh typed-prefix UUID4 `worker_id`，每次claim生成新
  `lease_token`；不使用
  hostname、PID、path或用户输入作identity；
- R4/P5仍需在Operation create path验证registry；R3的claim前校验是独立的持久化
  安全屏障，不以调用方正确性代替。

## 9. Execution model and ports

V1使用stdlib同步线程模型，不引入async scheduler或线程池：

```text
main thread
  signal handling + scheduler + monotonic waits + heartbeat

one bounded non-daemon executor thread
  one claimed Step + injected executor
```

- 同时最多一个executor thread；不内部fan-out；
- SQLite connection/cursor/UoW不跨线程；每个事务使用独立connection；
- scheduler、poll、retry和drain deadline使用monotonic clock；持久化lease/timestamp仍
  使用R2每事务一次采样的aware UTC wall clock；
- wait/backoff必须能被signal、drain或lease-loss event立即中断；
- executor只通过`ExecutionControl`和`LeaseSession`协作，不获得store或concrete UoW；
- exact protocol/class names和signatures留给S1，不在S0创建无consumer的generic worker framework。

`ExecutionControl`至少提供单调的process-local signals：

```text
drain_requested
cancel_requested
lease_lost
```

`lease_lost`是最强屏障；一旦设置，该executor不得再发布checkpoint、successor或
terminal outcome。executor必须在发起不可逆effect前和每个安全checkpoint边界检查
control；R3不强制中断Python线程。

## 10. LeaseSession and live-mutation serialization

每个active lease只有一个process-local `LeaseSession`，它是heartbeat、checkpoint和
terminal/successor publication的唯一写入通道：

```text
acquire per-lease mutation lock
  -> open fresh write UoW
  -> reload current Operation/Step in transaction
  -> validate worker identity, lease token, live lease and cancel intent
  -> invoke bounded in-memory candidate builder
  -> call the matching existing R2 atomic action
  -> R1 guard + write precondition + SQL CAS
  -> commit or roll back
```

原则：

- handler不得保存claim时的optimistic version后直接写store；
- heartbeat对Step的version更新不能使同一session的checkpoint/terminal意外stale；
- candidate builder只可使用事务内fresh records与`transaction_now`构造已选定candidate；
- builder不得进行I/O、sleep、lock wait、handler execution或任何长计算；
- builder是短命进程内callback，不是durable closure、JobDefinition或恢复入口；
- builder异常使当前UoW回滚；R1/R2仍是记录合法性、状态关系、CAS和atomic
  composition的唯一owner；
- R4/R5可选择step-only checkpoint、terminal + successor或terminal Step + Operation
  publication，R3不选择业务结果。

safe-handoff acknowledgment只能在对应checkpoint经`LeaseSession`提交后发出。
checkpoint-only交接不伪造新状态；Step保持`RUNNING`，worker退出后lease自然过期，
再由R5决定`RETRY_WAIT`或`MANUAL_RECOVERY_REQUIRED`。

## 11. Heartbeat, cancellation and failure behavior

### 11.1 Heartbeat

- heartbeat每次通过`LeaseSession`重读fresh Step，延长同一worker/token lease并递增
  optimistic version；
- `StoreBusy`只在当前lease剩余时间内有界重试，不用固定次数越过expiry；
- definitive `StaleWrite` / `LeaseExpired`立即设置`lease_lost`，禁止新claim和后续
  publication；
- lease loss后等待executor合作退出，随后worker非零退出；不在R3原地换租或
  选择recovery状态。

### 11.2 Cancellation

- claim后、executor前必须重读cancel intent；已取消的Step仍交给对应executor，但
  `ExecutionControl.cancel_requested` 预先置位；
- executor不得启动新external effect，只能按R4/R5 policy发布安全取消、checkpoint
  或manual recovery；
- 运行中cancel由每次heartbeat/mutation对fresh record的读取单调传递；
- drain不cancel业务Operation，也不把process shutdown写为`cancel_requested`。

### 11.3 Executor and invariant failures

- 未分类executor异常不发布`FAILED`、`RETRY_WAIT`或新diagnostic record；
- executor结束heartbeat，保留durable `RUNNING`事实，记录bounded event并非零退出；
- R5之后可以用明确typed policy把特定failure转为retry/recovery，不放宽R3的
  fail-closed默认；
- `CorruptPersistedRecord`、`UnsupportedSchemaVersion`、registry invariant或无法完成的
  recovery gate都denote worker-fatal startup/runtime failure，不跳过当前record继续claim。

## 12. Settings and fixed budgets

```yaml
control_db_path: required absolute server-owned path
lease_duration_seconds: 30        # R2 owner; not configurable in R3
heartbeat_interval_seconds: 10    # positive and <= lease / 3
idle_claim_poll_seconds: 1
transient_backoff_initial_seconds: 1
transient_backoff_max_seconds: 10
startup_retry_budget_seconds: 60
graceful_drain_timeout_seconds: 180
max_in_flight: 1                  # fixed; not configurable
claim_limit: 1                    # R2 owner; not configurable
```

- bootstrap可创建server-owned DB parent目录；R2 connection/store仍要求parent已存在且不读
  environment；
- heartbeat、poll、startup与drain参数的精确配置表面与上限由S1冻结；
- transient retry使用exponential backoff与bounded jitter，所有clock/wait/jitter source可注入测试；
- startup预算60秒耗尽后非零退出；不在未ready进程内无期重试；
- clean idle drain、正常完成或durable safe handoff退出0；executor/lease/invariant失败
  退出非0；当前不建立更细的public exit-code taxonomy。

## 13. Observability and data minimization

R3冻结最小稳定worker event codes：

```text
startup_failed
worker_ready
claim_succeeded
claim_busy
heartbeat_succeeded
heartbeat_busy
lease_lost
executor_failed
drain_started
safe_handoff
drain_timed_out
worker_exited
```

事件可包含operation ID、step ID、worker ID、attempt、稳定error category和bounded duration；
禁止包含lease token、job payload、artifact/checkpoint bytes、absolute DB path、SQL或secret。

R3使用stdlib logging并允许注入轻量observer以便确定性测试。没有当前consumer
前不增加metrics SDK、audit table、durable worker evidence或自定义IPC。最终log encoder和
metrics exporter是P5/observability composition细节。

## 14. Consistency and state relationships

R3必须保持以下屏障：

1. 一个worker进程同时最多一个active lease/executor；
2. 一个active lease同时最多一个R3 mutation transaction；
3. claim前registry validation与R2 claim在同一write transaction内；
4. heartbeat、checkpoint和terminal publication总是基于transaction-fresh record；
5. lease token不可由heartbeat替换；stale/expired worker永远不能发布新durable fact；
6. cancel/drain/lease-loss signals单调，不在进程内清除；
7. safe handoff一定发生在checkpoint commit之后；
8. process-local readiness不写入Operation/Step或被当作业务终局；
9. startup recovery的状态选择与external-effect解释不属R3；
10. 任何持锁/DB transaction内禁止handler、network、artifact或Repository I/O。

## 15. Compatibility, migration and staged usability

- R3不修改R1 persisted contract、R2 schema `operations/v1`、migration或store error taxonomy；
- 不导入legacy worker状态，不提供`operation_kind`兼容层；
- R3 production CLI在R4前组合immutable empty registry：empty DB可idle，任何runnable
  record均fail closed；
- synthetic executor只存在tests/harness，不通过production flag暴露；
- R3 handoff只能声称“worker mechanism runnable”，不能声称production jobs、retry、takeover或
  external effects可执行；
- R4之后用registry-backed resolver/executor替换empty composition；R5之后注入recovery
  policy；P5再接global readiness与Compose。

## 16. Multi-worker evolution and controlled reopen

| Future requirement | Reopen/refactor boundary |
| --- | --- |
| 同机多worker进程，每进程并发1 | 优先复用R1/R2 fencing/CAS；修改R3 scheduler、P5 deployment/readiness，并增加SQLite contention/capacity gate |
| 严格部署级全局并发额度、rolling drain或worker membership | 重开R3/P5 coordination owner；只在真实需求证明后评估R2 permit/registration durable state |
| 多主机、HA、NFS或外部DB | 重开R2 storage/deployment ADR、migration和transaction adapter；不将SQLite/WAL直接放到network filesystem |

任何层级都不得改变R1状态语义或放宽lease fencing。默认先把worker count当作
deployment-fixed capacity，不预先建设leader election、membership或global slot table。每个层级
分别验证duplicate claim、heartbeat、drain和takeover，不把同机多进程自动升级为HA。

## 17. Test and verification strategy

### 17.1 Deterministic unit owners

- startup gate顺序、双重scan和registry/recovery result matrix；
- claim-time registry validation与mutation-free missing-handler failure；
- scheduler idle poll、backoff、jitter和signal-interruptible wait；
- `LeaseSession` serialization、fresh-version publication、cancel propagation和builder rollback；
- heartbeat与checkpoint/terminal竞争、StoreBusy deadline和definitive lease loss；
- lifecycle、clean drain、safe-handoff-after-commit和timeout-no-auto-kill；
- event redaction、exit result和architecture import boundary。

单元测试注入UTC/monotonic clock、wait、jitter、UoW factory和observer；不使用真实长
`sleep`、SQLite file或无界thread pool。

### 17.2 File/process integration owners

- real temporary local SQLite/WAL file、独立connections和restart可见性；
- worker与concurrent cancel writer之间的version/intent传递；
- 真实SIGTERM、process crash、lease自然过期和checkpoint-before-exit可见性；
- crash后不证明takeover；R3只证明旧worker不能迟到写、durable record保留且R5 hook
  可观测。

on-disk/shared-WAL/process tests标`integration`；固定时间或真实process signal/crash tests标
`serial`并串行运行。不使用Dolt或真实Repository Service。

### 17.3 Container gate

R3引入真实worker entrypoint，因此R3-S7必须重建当前HEAD backend image，并：

- 用显式command运行`python -m gateway_backend.bootstrap.operation_worker`；
- 挂载临时server-owned本地control DB目录；
- 证明empty DB bootstrap、`READY_TO_CLAIM`、SIGTERM drain和clean exit；
- 记录image revision、source-tree identity和container applicability；
- 不声称backend HTTP/global readiness、R4 job execution或R5 takeover通过。

P4-R6在R4/R5完成后必须再次重建最终HEAD并运行完整container/Compose gate；R3
的旧镜像证据不代表后续HEAD已验证。

## 18. Candidate staged plan

精确step拆分由S0 acceptance后的detailed execution plan冻结；当前建议：

| Step | Applicability | Candidate output |
| --- | --- | --- |
| S0 | required | accepted owner/scope/budgets/reopen brief and independent entry acceptance |
| S1a | required | SQLite-neutral executor/control/lifecycle/recovery/observer ports |
| S1b | required | LeaseSession and fresh-transaction atomic publication seam |
| S2a | required | startup integrity/topology/registry gates and atomic claim |
| S2b | required | single executor scheduler, heartbeat, cancellation and bounded waits |
| S3a | required | drain, timeout and process-local lifecycle |
| S3b | required | worker settings, concrete bootstrap, module CLI and file/process evidence |
| S4 | required | focused owner/concurrency/lifecycle review |
| S5 | conditional | finding-scoped remediation only |
| S6 | required | independent stale-worker, signal/drain and process-boundary review |
| S7 | required | module gate, rebuilt image evidence and R4 entry handoff |

S6建议required，因为R3首次将持久化lease/CAS与cross-thread执行、process signal和
checkpoint handoff组合成一个runnable boundary。评审证明Contract barrier，不穷举Python/
SQLite所有调度。

## 19. Non-goals and excluded alternatives

- 不实现JobDefinition payload、successor/final policy、READY closure或production handler；
- 不实现retry/backoff decision、expired RUNNING takeover、unknown-effect reconcile或Repository stub；
- 不实现business outbox/T1/T3、HTTP operation route、global readiness或最终Compose；
- 不把drain当作cancel，不把worker退出当作Operation terminal；
- 不强杀thread，不在timeout后停租或伪造safe handoff；
- 不向handler暴露SQLite、store、UoW、lease token或任意SQL；
- 不使用async scheduler、无界thread pool、process pool、broker或动态fan-out；
- 不为未来多worker预建membership、global permit、leader lease或第二durable state machine；
- 不支持NFS上的SQLite、multi-host、HA、external DB或formal throughput claim。

已排除的主要路径及原因：

| Alternative | Reason excluded in R3 V1 |
| --- | --- |
| handler直接写store | heartbeat/cancel会使旧version失效，无法保证单写与candidate freshness |
| heartbeat和executor各自管理latest record | 建立两个进程内写owner，放大stale publication竞争 |
| R3直接处理expired RUNNING | 提前越过R5 retry/effect-aware policy，可能blind replay |
| durable worker registry/leader | 单进程当前无consumer，扩大持久化和恢复证明面 |
| worker HTTP/readiness side channel | 全局readiness由P5组合，R3不需新IPC或对外端口 |
| timeout后自动kill | 违反graceful lifecycle，可丢checkpoint并扩大unknown outcome |

## 20. Risks, assumptions and deferred items

### 20.1 Confirmed assumptions

以下不是未确认推测，而是R3 V1已确认的部署前提：

- 单主机、可靠本地SQLite/WAL volume；
- 同一受控euid/信任域；
- 整个部署一个operation worker进程；
- handler合作检查cancel/drain/lease-loss，且candidate builder为有界纯内存操作；
- R4/R5/P5在后续模块提供当前明确留白的policy与composition。

### 20.2 Risks with explicit triggers

| Risk | Current treatment | Reopen/validation trigger |
| --- | --- | --- |
| SQLite writer contention | one worker, short `BEGIN IMMEDIATE`, bounded busy/backoff | first real journey misses latency/capacity budget or needs multiple workers |
| handler monopolizes interpreter/GIL and starves heartbeat | one executor thread; R4 must test representative handlers | representative Python/native handler blocks main scheduler beyond heartbeat margin |
| complete startup scan delays readiness | bounded pages and progress events; no sampling | measured active-set startup time violates deployment recovery objective |
| handler ignores cooperative stop | no unsafe thread kill; drain timeout remains visible | a real handler cannot provide bounded checkpoint/stop cooperation |
| no cross-process worker-ready channel | P5 owns global readiness composition | P5 consumer cannot safely compose readiness without an additional standard platform seam |
| empty R3 registry limits staged CLI | fail closed and synthetic test-only executor | production job execution is requested before R4 handoff |

### 20.3 Deferred details

- exact Python type names/signatures、module file split和public export list；
- exact jitter distribution、log encoder和metrics exporter；
- R4 JobDefinition registry、payload/checkpoint/READY semantics与two synthetic jobs；
- R5 retry/takeover/effect reconciliation matrix；
- P5 business create/finalize、HTTP/global readiness、Compose volume和worker replica wiring；
- terminal retention/GC/backup与formal capacity baseline。

## 21. S0 acceptance and module exit criteria

R3-S0 independent acceptance前必须确认：

1. R2 validated source/test identity与当前HEAD仍无漂移；
2. process-local lifecycle与P5 global readiness/signal/deployment owner拆分已在owning
   ADR/contract reference中无歧义；
3. executor/registry/recovery ports不提前吸收R4/R5 policy；
4. `LeaseSession`只组合R1/R2已有guard/CAS/atomic action，不建立新持久化语义owner；
5. claim-time registry validation、heartbeat/publication serialization和lease-loss fencing可在不改R2
   schema/port的前提下实现；
6. signal、drain、safe handoff、timeout和exit semantics与ADR 0016一致；
7. test markers、five-package static gates、container rebuild applicability和image provenance已冻结；
8. detailed execution plan冻结allowed paths、S-step split、review owner和每步单独授权；
9. independent acceptance结果明确`p4_r3_s0: accepted | rework_required`；
10. 即使S0 accepted，S1a implementation仍需单独授权。

R3模块S7只能在以下行为被证明后exit：

- worker可以从empty DB完成双重startup gate并进入idle scheduler；
- known runnable key的claim与registry validation原子，unknown key不留`RUNNING`前缀；
- heartbeat、checkpoint和terminal/successor publication在同一lease session中不互相stale；
- cancel、drain、StoreBusy、lease loss和executor failure全部有界且fail closed；
- safe handoff必须后于durable checkpoint，timeout不自动强杀；
- focused/unit/integration/serial、five-package ruff/mypy、`git diff --check`通过；
- 当前HEAD image重建与`python -m gateway_backend.bootstrap.operation_worker`
  worker process container gate通过；
- handoff精确记录R4/R5/P5 deferred boundary、single-worker limit、image revision和reopen
  conditions。

## 22. Stop and reopen conditions

出现以下任一情况必须停止对应implementation step，先提交evidence/finding并重开
owning Contract/ADR：

- 需要改变R1 record/status/transition/write-precondition semantics；
- 需要修改R2 schema/version/error taxonomy或放宽SQL CAS；
- 无法在同一write transaction内完成registry preflight与exact candidate claim；
- 需要direct `RUNNING -> RUNNING` worker/token replacement或R3自行选择retry/manual状态；
- 需要handler直接store/UoW访问或在DB transaction中执行外部I/O；
- 需要多个active executors、DAG/fan-out、动态registry或hot reload；
- 需要production Repository effect、business T1/T3、outbox或global readiness语义；
- 需要durable worker membership、leader、permit、IPC、broker、sidecar或新安全主体；
- 部署不再是单机单worker，或SQLite volume不是可靠本地filesystem；
- representative handler无法在heartbeat/drain预算内合作，需要process isolation或新执行模型；
- 需要自动强杀、持久化lifecycle evidence、repair/quarantine或无限startup retry。

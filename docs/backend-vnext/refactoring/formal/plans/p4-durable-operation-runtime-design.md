# P4 Durable Operation Runtime Design Baseline

状态：**Accepted for P4 entry acceptance and staged implementation planning**

日期：2026-08-23

Owner：Backend vNext Operation Runtime

上游：[P4 Active Context Index](p4-active-context-index.md)、[P3 Final Closure and P4/P5 Entry Handoff](p3-final-closure-handoff.md)

本文将已收敛的 P4 entry/design decisions 固化为总体设计基线。它组合已有
normative contracts，不取代 [Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md) 或
[Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)。精确 wire、字段和错误矩阵由对应 owner 在 P4-R1 冻结。

逻辑架构名称为 `backend_vnext`；当前 distribution 的物理 Python package root 为
`gateway_backend`。两者不是两个并行实现。P4 允许整理已提交代码的目录结构，但不为
兼容旧内部 import 保留第二套 Runtime。

## 1. 目标与边界

P4 建立供 Phase 5 业务纵切使用的最小 Durable Operation Runtime：

- operation/step 状态可持久化、可查询、可恢复；
- worker crash、lease expiry 和重复投递不会产生重复业务 effect；
- checkpoint、artifact ref 和 repository operation identity 足以支持接管；
- JobDefinition 通过稳定注册继续执行，不依赖请求进程内 closure；
- drain、startup recovery 和 readiness 遵守既有 lifecycle contract。

P4 不实现：

- Workspace、HTTP、PreviewResult、Submit/Finalize、Review 或 Archive 业务流程；
- production external-target adapter、multi-target durable schema 或 PostgreSQL adapter；
- Repository marker/ref/CAS/reconciliation authority；
- 任意 DAG、动态脚本工作流、跨服务分布式事务或新的 broker/sidecar/security principal；
- capability 内部按表并行；只有需要独立恢复和业务可见进度的工作才可成为 operation step。

## 2. 已确认架构决策

| 主题 | 决策 |
|---|---|
| 物理包落点 | `vnext/backend/src/gateway_backend/operations/`；`backend_vnext` 只作逻辑架构名称 |
| 部署形态 | 模块化单体部署单元；独立 worker entrypoint；同一受控信任域 |
| Durable Store | backend application control DB 的 SQLite/WAL；operation、step、outbox 与业务表共享事务数据库 |
| 并发 | 首版顺序 step、有界并发，默认 `max_in_flight=1`；固定 fan-out/fan-in 只预留 |
| claim/takeover | optimistic version + worker identity + lease token；过期 worker 的写入被 CAS 拒绝 |
| 注册 key | `(job_kind, step_name) -> JobDefinition handler`；不再并存 `operation_kind` |
| contract version | `backend-vnext/operation-runtime/v1`；job-specific payload 另有 `job_contract_version` |
| payload | `job_kind`、`job_contract_version`、版本化 payload 或 payload ref；runtime 不解释业务语义 |
| 大型结果 | 只保存 immutable artifact/checkpoint ref、digest 和 closure ref，不保存 Python object graph |
| 外部 effect | request 前后均复用原 idempotency/operation identity；unknown outcome 只查询和 reconcile |
| 取消 | cooperative cancellation；外部请求已发送后不伪造远程取消、不生成新 key |
| cleanup | P4 不自动删除 terminal operation；保留/GC 等待真实 consumer 和容量数据 |

### 2.1 P4-R4-S0 JobDefinition and Checkpoint discussion closure

本节记录 2026-08-25 完成的 R4-S0 架构讨论。它冻结总体设计边界，但不创建或授权
R4 implementation；精确字段、wire shape、测试 fixture 和 step 拆分仍由独立 R4 entry
brief 与 execution plan 负责。

- **Registry owner and lifecycle**：`JobDefinition` 由 application owner 定义并在进程启动
  时组装为 immutable registry。registry 是纯内存、有界 lookup；不使用 durable registry、
  远程发现或 hot reload。identity 固定为 `(job_kind, step_name)`，
  `job_contract_version` 独立匹配。runnable record 遇到未知 key 或版本时 fail closed。
- **Handler boundary**：R4 通过 R3 已冻结的 `ClaimedExecutor`/`LeaseSession` adapter 执行；
  handler 只能接收 transaction-fresh Operation/Step、`ExecutionControl`、session 和注入的
  artifact port。payload decoder、artifact I/O 和 handler 计算不得在 DB transaction 内运行，
  也不得依赖请求进程 closure、动态脚本或 Python object graph。
- **Payload and checkpoint versions**：job payload、checkpoint 和 READY closure 各自使用
  明确的 owner/version 轴。只接受 registry 已声明的 decoder；未知版本不做隐式迁移、宽松
  读取或自动重写，active runnable record 直接 fail closed。
- **Artifact port and identity**：R4 复用现有 `ArtifactStorePort` 与 `ArtifactRef`。`put`/
  `locate` 必须保持 exact ref、size 和 raw digest 校验；artifact identity 不携带 host path。
  R4 不新增 delete、quarantine、sidecar、generic manifest 或 artifact cleanup authority。
- **Checkpoint authority**：运行中的恢复游标以 `StepRecord.checkpoint_ref` 为权威，
  `prior_output_refs` 保持 immutable。`OperationRecord.checkpoint_ref` 仅作为 operation-level
  或 terminal publication 的汇总字段；普通 R4 checkpoint 不引入 operation same-status
  mutation，也不改变 R1/R2 schema、status 或 CAS contract。
- **READY closure**：R4 定义最小、版本化的 JCS closure document，记录有序 artifact refs、
  size/digest、closure version 和对应 job contract version。只有在所有 refs 可读取且完整性
  校验通过后，才能在 terminal publication 中一次性设置 `ready_closure_ref`；缺失、损坏或
  版本未知时 fail closed，不伪造 READY。
- **Successor and final policy**：R4 只支持静态、显式的单 successor 组合或正常 terminal
  publication，不引入任意 DAG、动态 fan-out 或隐式 successor。retry、takeover、expired
  lease、unknown external outcome 和 manual recovery 仍由 R5 拥有。
- **External-effect stub**：R4 只使用 test-only deterministic stub。stub 接受稳定的
  idempotency key/request ref 并返回稳定 operation identity，可模拟 accepted、unknown 和
  confirmed；R4 只持久化 request/checkpoint/identity，不执行真实 Repository/Dolt effect，
  也不作 reconcile 或 retry 决策。
- **Cancellation**：纯计算或 external stub 尚未提交请求时，cooperative cancel 可发布
  `CANCELLED`；请求已提交或结果未知时不得伪造取消终局，必须保留原 identity/checkpoint
  交给 R5 处理。
- **Artifact write versus CAS**：先写 immutable artifact，再提交 durable CAS。stale CAS
  造成的未引用 artifact 属于可恢复的 temporary/derived 状态，允许通过确定性 identity 和
  幂等 `put` 限制重复；R4 不建立不可逆 cleanup 或 durable evidence 状态机。

任何需要修改 R1 record/status/transition、R2 schema/store/CAS/error taxonomy、增加新的
principal/IPC、改变 single-worker/local SQLite 边界或引入真实 Repository effect 的需求，
必须 reopen 对应 owner，不得在 R4 implementation 中静默扩展。

### 2.2 P4-R5 retry, takeover and effect recovery discussion closure

R5 的设计讨论已于 2026-08-26 收敛；详细 contract、failure matrix、预算、operator port 和
执行边界见 [P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)。
本节只记录与总体 P4 基线的兼容性结论：

- R5 使用现有 immutable `(job_kind, step_name)` registry，可在 `JobDefinition` descriptor
  上增加非持久化 `recovery_capability`，不创建第二 registry，也不把 recovery policy 写入
  Operation/Step persisted document；
- recovery hook 是只读、无 I/O 的 decision function；R3 runtime 在独立 write UoW 中通过
  现有 transition/CAS 应用 `RecoveryDecision`，不改变 R1/R2 status、schema 或 fencing；
- Step retry 走 `RUNNING -> RETRY_WAIT -> RUNNING`，Operation 在 active Step `RETRY_WAIT`
  时保持 `RUNNING`；`attempt_count` 统计 recovery session，不统计 session 内 poll 次数；
- 外部 request acceptance 后只复用原 idempotency key、request fingerprint 和
  `repository_operation_id`；unknown outcome 只能 reconcile，无法判断时进入
  `MANUAL_RECOVERY_REQUIRED` 并保留 occupancy；
- R5 复用 application handler 解释 checkpoint，不解析业务 payload，不连接真实 Repository；
  P5B 仍拥有真实 Repository/Dolt effect、commit/ref evidence 和 T1/T3；
- operator 只有内部 `RESUME_RECONCILE`、`RETRY_FROM_CHECKPOINT` 和
  `ABORT_CONFIRMED_FAILURE`，P5 后续接线 HTTP/授权；R5 不新增 principal、IPC 或稳定 R3
  event enum；
- 默认每 Step 三个 recovery session、`1s/2s/4s` backoff（上限 `10s`）、60 秒 reconcile
  session、有界 jitter 和可注入 clock/wait/jitter；
- R5 不改变 single-host/single-worker/SQLite/WAL、静态 successor、READY closure 或 cleanup
  边界。任何需要 R1/R2/R3/R4/P5B owner 语义变化的候选必须 reopen。

## 3. 逻辑架构

```text
application use case / JobDefinition owner
        |  create operation + outbox in one DB transaction
        v
Operation Runtime port
        |
        +--> SQLite/WAL Operation Store
        |      operation / step / lease / checkpoint metadata
        |
        +--> JobDefinition Registry
        |      stable job_kind + step_name -> handler
        |
        +--> Worker entrypoint
               claim -> load checkpoint -> execute -> CAS publish
                         |                         |
                         v                         v
                    ArtifactStore             Repository Client port
                         |                         |
                         +--> immutable refs       +--> Repository Service
                                                      (operation/ref/CAS owner)
```

允许的依赖方向：`application -> operation port -> runtime/store`；JobDefinition 由
application 注册，runtime 只负责执行机制；Repository adapter 只暴露网络 contract，
不泄漏 Dolt path、CLI、PID 或 server session。

P4/P5 的物理目录演进为：

```text
gateway_backend/
  capabilities/       # P3 capability owners
  operations/         # P4 runtime owner
  artifacts/          # artifact contracts/ports
  infrastructure/     # adapters
  application/        # P5 use cases and JobDefinitions
  domain/             # P5 domain modules
  interfaces/         # HTTP/worker interfaces
  bootstrap/           # startup and composition root
```

现有 `app.py`、settings 和接口代码可在 R3/P5 按 owner 迁入 `bootstrap/`、`interfaces/`
和 `application/`；迁移保持功能语义不变，不在 R1 提前引入业务路由或 worker wiring。

## 4. 状态与事务语义

### 4.1 Operation 与 Step

首版建议的通用状态集合为：

```text
Operation: QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED | SUPERSEDED | MANUAL_RECOVERY_REQUIRED
Step:      PENDING -> RUNNING -> RETRY_WAIT | SUCCEEDED | FAILED | CANCELLED | MANUAL_RECOVERY_REQUIRED
```

`READY` 是 step output 的 closure/readability 条件，不是通用 Operation terminal status。
Operation terminal status 不等于业务终局；Submit/Archive 的 T3 finalize 仍由业务 owner 负责。

通用 Operation envelope 至少绑定：

```text
operation_id, job_kind, job_contract_version,
job_payload or job_payload_ref,
business IDs, artifact refs/digests,
repository_operation_id (when present), checkpoint_ref,
ready_closure_ref, optimistic_version, created/updated timestamps
```

Step record 额外保存 step name、attempt count、lease token/expiry、last error code、
checkpoint ref 和 prior output refs。具体业务 payload/schema 不进入 Operations owner 的通用语义。

R4 恢复时先解析 active Step 的 checkpoint 和 prior outputs；Operation-level checkpoint 不替代
active Step checkpoint，也不作为普通 heartbeat/checkpoint 的第二写入目标。

### 4.2 T1/T2/T3

P4 提供执行机制，未来 P5 application 定义业务事务：

```text
T1 business DB transaction:
   validate -> persist business binding + Operation + outbox atomically

T2 durable worker:
   checkpoint immutable request/artifact -> submit/poll Repository operation

T3 business DB transaction:
   require matching SUCCEEDED or allowed stable failure -> finalize business facts
```

请求已发送而结果未知时，worker 不创建新 idempotency key；接管 worker 先以原
`repository_operation_id` 查询，再按 Repository contract 处理 evidence。

### 4.3 Lease 与 stale worker

claim、heartbeat、checkpoint 和 terminal publish 都必须带 `optimistic_version` 与
`lease_token`。lease 过期只允许新 worker 通过 CAS 接管；旧 worker 的迟到写入必须失败并
记录诊断。P4 不建设独立 fencing 服务。

## 5. Lifecycle、drain 与恢复

遵守既有生命周期：

```text
SERVING -> DRAINING -> QUIESCED -> CHECKPOINTED -> STOPPING -> EXITED
```

进入 `DRAINING` 后拒绝新的会创建 operation/artifact/effect 的请求，已有 operation 可
继续执行或 checkpoint 后接管。startup readiness 前执行：

```text
load durable state -> reconcile unknown outcomes/artifacts
  -> validate registry/ruleset -> restore workers -> health check
  -> readiness=true
```

默认 graceful drain timeout 仍为 deployment contract 的 `180s`；数值型 lease、heartbeat、
retry/backoff 和 poll interval 在详细设计中冻结，并必须满足测试时间预算。

取消只在安全 checkpoint 边界生效。外部 effect 已发送时，取消不能释放业务占用，必须先
完成原 operation 的 reconcile 或转入 `MANUAL_RECOVERY_REQUIRED`。

## 6. 故障与验收不变量

- 纯 compute step 可从 checkpoint 幂等重算；外部 effect step 不得 blind replay。
- 同一 operation/step 的 duplicate delivery 最终只产生一个 terminal publication。
- repository operation 已接受但 worker crash 时，接管 worker 复用原 identity 查询。
- `MANUAL_RECOVERY_REQUIRED`、integrity incident 和未解决外部事实不进入普通 cleanup。
- READY 前所需 artifact 必须存在且可读；READY 后的后台优化不得改变正式结果。
- Runtime 不依赖具体 Workspace、Submission、Archive 或 capability 内部模型。
- 未知 job/payload/checkpoint/closure version 不得进入 runnable 或 READY 状态。
- READY closure 只允许一次性设置；terminal publication 前必须完成所有引用 artifact 的完整性校验。
- 请求已提交或 outcome 未知时不得用新的 idempotency key 或 `CANCELLED` 终局掩盖原事实。

P4 必须覆盖纯计算 synthetic job、external-effect stub job、process crash、lease takeover、
duplicate delivery、cancel、drain/restart、checkpoint corruption 和 unknown outcome。
真实 Repository/Dolt effect 与 P5B 一起做 integration；worker entrypoint/lifecycle 触碰
container boundary 后，P4 final candidate 必须重建当前 HEAD 镜像并运行容器门禁。

## 7. 风险与延后事项

| 项目 | 当前处理 |
|---|---|
| SQLite lock contention / 容量 | P4 使用有界并发和诊断；真实容量 baseline 延后到 P5 journey |
| lease/retry 数值 | 详细设计阶段按故障测试预算冻结 |
| terminal operation retention/GC | P4 不自动删除；由后续运维 policy 和真实 consumer 决定 |
| 多实例 HA / 外部 DB | 非 P4 V1 目标；出现真实部署需求后重开架构决策 |
| production Repository/Dolt integration | P5B owner；P4 使用 contract stub |
| 任意 DAG / 动态 fan-out | 保留接口，不进入首版实现 |
| R4 未引用 artifact 与 closure GC | R4 只保证 bounded/idempotent 写入；cleanup/retention 等待真实 consumer 和容量数据 |
| R4 checkpoint/READY closure wire | 本节冻结 owner 和一致性边界；精确 document shape 由 R4-S0 execution plan 冻结 |

## 8. Entry acceptance

实现授权前必须接受：[P4 Durable Operation Runtime Execution Plan](p4-durable-operation-runtime-execution-plan.md) 中的六个 module charter、schema/migration plan、fault matrix、测试命令、review owner、deferred register 和当前 HEAD provenance。通过 entry acceptance 后，才可将 `p4_implementation_authorized` 改为 `yes`。

P4-R4-S0 的总体架构讨论、entry brief、detailed execution plan 和 independent acceptance
已完成并分别封存于正式 plans。它们复用本节决策，已补齐 step split、review rounds、conversation
strategy、test markers、container trigger、fault matrix 方向和 provenance；当前仍未授权
R4 implementation。

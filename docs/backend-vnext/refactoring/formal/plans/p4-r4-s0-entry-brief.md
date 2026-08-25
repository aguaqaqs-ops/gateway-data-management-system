# P4-R4-S0 Entry Brief: JobDefinition and Checkpoint

状态：**DESIGN AND EXECUTION PLAN ACCEPTED — R4 IMPLEMENTATION NOT AUTHORIZED**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

上游：[P4/R3 Worker Lifecycle Handoff](p4-r3-worker-lifecycle-handoff.md)、
[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)、
[P4 Durable Operation Runtime Execution Plan](p4-durable-operation-runtime-execution-plan.md)、
[Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)

默认入口：[P4 Active Context Index](p4-active-context-index.md)

逐 step authority：
[P4-R4 JobDefinition and Checkpoint Detailed Execution Plan](p4-r4-jobdefinition-checkpoint-execution-plan.md)

## 1. Entry identity and authorization boundary

```yaml
step_id: P4-R4-S0
input_handoff_sha: 9ea535e138a7e498aeade69042bfbbff559fcfc0
input_validated_code_sha: acb3efca06a02aadaa5ce6d1e2a815e85d36e6af
p4_r3_exit: pass
p4_r4_s0_design: accepted
p4_r4_execution_plan: accepted
p4_r4_s0_acceptance: accepted
p4_r4_implementation_authorized: no
accepted_registry: application_owned_immutable_process_local
accepted_registry_key: '(job_kind, step_name)'
accepted_payload_policy: explicit_job_contract_version_strict_decoder_no_implicit_migration
accepted_checkpoint_authority: active_step_checkpoint_ref
accepted_artifact_port: existing_ArtifactStorePort_and_ArtifactRef
accepted_successor_policy: static_explicit_single_successor_or_terminal
accepted_external_effect: deterministic_test_only_stub_no_real_repository_effect
next_step: P4-R4-S1a
next_step_authorized: no
next_input_sha: pending_r4_s0_documentation_commit
```

R3 handoff只授权本 R4-S0 的 entry discussion。本文、execution plan 和 acceptance record
冻结设计与验证边界，但不授权 Python、tests、bootstrap、artifact store、container 或真实
Repository effect 变更。每个 code step 仍需要新的明确 authorization。

## 2. Objective and users

R4 让 R3 worker 能仅凭 durable Operation/Step、版本化 payload、prior outputs 和 immutable
artifact refs 恢复执行。直接使用者是 application JobDefinition owner、R3 executor adapter
和后续 R5 recovery owner；R4 不面向 HTTP 用户，不解释 Workspace、Submission、Archive 或
Repository 业务语义。

交付目标：

- application-owned immutable JobDefinition registry；
- strict payload/checkpoint/READY-closure decoders；
- 复用既有 `ArtifactStorePort`/`ArtifactRef` 的 checkpoint 和 closure refs；
- 一个幂等纯计算 synthetic job；
- 一个 deterministic external-effect stub synthetic job；
- payload reload、checkpoint round-trip、artifact integrity、READY gating、duplicate delivery
  和 cancellation 的可重复测试证据。

## 3. Scope and ownership split

```text
R4 application/job-definition owner
  owns: JobDefinition descriptor, payload decoder, checkpoint/closure document,
        handler policy, normal successor/final candidate and synthetic jobs

R4 operation adapter
  owns: immutable registry lookup and mapping to R3 ClaimedExecutor
  depends on: R1 Operation/Step records, R3 ExecutionControl/LeaseSession,
              existing ArtifactStorePort

R3
  owns: claim, lease, heartbeat, publication serialization, drain and process-local lifecycle

R5
  owns: retry, takeover, expired RUNNING disposition, unknown external outcome,
       reconcile and MANUAL_RECOVERY_REQUIRED policy

P5/application journey
  owns: T1/T3, business admission, HTTP/global readiness and real Repository integration
```

R4不得让 `gateway_backend.operations` import application implementation。application 通过
composition root向 R3既有 `WorkerRegistry` port提供 adapter；R3 public protocol不因 R4
静默增加第二套 registry 或新的 error taxonomy。

## 4. Frozen R4 decisions

### 4.1 Registry and handler

- registry 在进程启动时组装，进程生命周期内 immutable；不使用 durable registry、远程发现或
  hot reload；
- identity 固定为 `(job_kind, step_name)`，`job_contract_version` 独立匹配；unknown runnable
  key/version 在 claim 前 fail closed 且不产生 durable mutation；
- handler 由 R3 `ClaimedExecutor`/`LeaseSession` adapter 调用，输入限于 transaction-fresh
  records、`ExecutionControl`、session 和 injected artifact port；
- handler、decoder、artifact I/O 和长计算不得在 DB transaction 内运行，不捕获请求进程
  closure，不保存 Python object graph。

### 4.2 Payload, checkpoint and artifacts

- payload、checkpoint、READY closure 各有明确 owner/version 轴；只接受 registry 已声明的
  decoder，不做隐式迁移、宽松读取或自动重写；
- 复用现有 `ArtifactStorePort.put/locate` 和 `ArtifactRef`，保持 exact ref、size、raw
  digest 和 path-neutral identity；R4 不增加 delete/quarantine/generic-manifest authority；
- active execution 的恢复游标是 `StepRecord.checkpoint_ref`；`prior_output_refs` immutable；
  `OperationRecord.checkpoint_ref` 只作 operation-level/terminal 汇总，不成为普通 checkpoint
  的第二写入目标；
- R4-owned READY closure 是最小版本化 JCS document，包含有序 refs、size/digest、closure
  version 和 job contract version。所有 refs 可读且完整性校验通过后，才可在 terminal
  publication 中一次性设置 `ready_closure_ref`；
- artifact 先写入再 CAS。stale CAS 造成的未引用 artifact 视为 bounded temporary/derived
  state，由确定性 identity 和幂等 put 限制重复；R4 不建立 cleanup/evidence 状态机。

### 4.3 Successor, cancellation and external stub

- R4 只允许静态、显式的单 successor 或 normal terminal publication；不引入任意 DAG、动态
  fan-out 或隐式 successor；
- 纯计算或 stub 尚未提交 request 时可以 cooperative `CANCELLED`；request 已提交或 outcome
  未知时不伪造取消终局，保留原 identity/checkpoint 交给 R5；
- external-effect stub 是 test-only deterministic port，接受 stable idempotency key/request
  ref，返回 stable operation identity，可模拟 accepted/unknown/confirmed；R4 不执行真实
  Repository/Dolt effect，不决定 retry/reconcile/takeover。

## 5. Candidate physical surface

候选代码路径（S1a 可在不改变 owner 的前提下合并文件）：

```text
vnext/backend/src/gateway_backend/application/__init__.py
vnext/backend/src/gateway_backend/application/job_definitions.py
vnext/backend/src/gateway_backend/application/synthetic_jobs.py
vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
vnext/backend/src/gateway_backend/operations/worker.py       # adapter only if required
vnext/backend/src/gateway_backend/artifacts/                  # no new generic port

vnext/backend/tests/test_job_definition_contracts.py
vnext/backend/tests/test_job_definition_registry.py
vnext/backend/tests/test_job_payload_decoding.py
vnext/backend/tests/test_operation_checkpoint_contracts.py
vnext/backend/tests/test_operation_job_synthetic.py
vnext/backend/tests/test_operation_job_recovery.py
vnext/backend/tests/test_operation_worker_process.py
vnext/backend/tests/test_architecture.py
```

不得修改 R1/R2 record、status、schema、migration、CAS/error taxonomy、Repository Service、
P5 business routes、Compose、dependency lock 或引入新的 principal/IPC。若候选路径证明会
违反这些边界，立即回到 S0/reopen owner，不在 code step 即兴扩展。

## 6. Test classification and evidence

- 纯 descriptor、decoder、JCS、registry、state candidate 和 fake artifact tests 标 `unit`；
- 真实 `LocalArtifactStore`、on-disk checkpoint/closure、reopen 和 process harness 标 `integration`；
- 固定 timeout、thread/process crash、signal 或 drain/restart 标 `serial`；
- 不创建 Dolt，不将 stub 结果表述为 production Repository validation；
- 同构 malformed payload/ref/closure faults 使用模块级参数表，不复制测试函数；
- 每个不变量只有一个权威测试 owner，S4/S6 只复用或补充必要的 contract-level probe。

## 7. Stop and reopen conditions

立即停止并记录 finding/reopen：

- 需要改 R1 record/status/transition、R2 schema/store/CAS/error taxonomy；
- 需要普通 checkpoint 更新 Operation same-status、direct RUNNING lease swap 或 terminal Step-only publication；
- 需要 dynamic registry/hot reload、任意 DAG、多 executor、IPC、sidecar 或新 principal；
- 需要在 DB transaction 内执行 handler、artifact I/O、network 或长计算；
- 需要 retry/takeover/manual-recovery/reconcile policy 或真实 Repository effect；
- artifact cleanup/evidence 需求超出 bounded temporary handling；
- 现有 unit/integration/serial/container marker 无法表达新增高风险边界。

## 8. Entry acceptance exit

R4-S0 acceptance 只证明设计、执行计划、owner、step split、review rounds、测试分类和
provenance 已足够进入 S1a authorization discussion。它不改变
`p4_implementation_authorized`，也不授权 R4/R5/P5 implementation。


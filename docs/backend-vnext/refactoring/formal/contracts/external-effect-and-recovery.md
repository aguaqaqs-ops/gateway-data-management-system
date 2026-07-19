# External Effect and Recovery Contract

状态：正式设计（Accepted）

阶段：Phase 0 结论；Phase 2、Phase 4、Slice 5B/5D 实现

Contract ID：`gateway-vnext.external-effect-and-recovery`

Owner：Submit/Archive Application（业务 execution）；Operations（通用执行）；Repository Service（effect evidence）

Semantic version：`1.0.0`

## 1. 目的与 owner 分界

本文固定跨 Repository Service 写 effect 的事务、证据、失败和恢复规则。所有权按语义分离：

| 语义 | 唯一 owner |
| --- | --- |
| SubmitAttempt/ArchiveExecution、命令验收、业务 finalize | 对应 Application/Domain |
| Operation/Step、claim/lease/retry/checkpoint | Operations |
| Repository operation journal、commit/ref/effect evidence | Repository Service |
| FailureDescriptor 公共维度 | Shared Kernel |
| stable code、phase、details schema | 对应 use case owner |

Operation terminal status 不等于业务终局；FailureDescriptor 也不替代 Repository evidence。

## 2. Execution 四态

SubmitAttempt 与 ArchiveExecution 分别拥有相同形状但不同业务语义的状态：

```text
PREPARED -> EFFECT_PENDING -> FINALIZED
PREPARED -----------------> ABORTED
EFFECT_PENDING -----------> ABORTED
```

只有下列证据允许终止：业务 finalize 成功进入 `FINALIZED`；或者 Repository authority 提供 explicit `NOT_APPLIED` evidence、原请求不再运行且不会被应用，进入 `ABORTED`。`UNKNOWN`、`APPLIED`、worker failure、lease expiry 和 Operation `FAILED_FINAL` 均不允许释放业务占用或 serialization key。

## 3. T1/T2/T3 边界

```text
T1 Accept/Start (business DB transaction)
  validate immutable bindings, idempotency and occupancy
  persist PREPARED execution + Operation + outbox atomically
  acquire business/repository serialization occupancy

T2 External effect (durable worker + Repository Service)
  persist immutable request/artifact checkpoint
  cross request-acceptance boundary once
  journal PREPARED/APPLIED/VERIFIED evidence
  reconcile uncertain outcomes

T3 Finalize (business DB transaction)
  require matching VERIFIED evidence
  create Submission or ArchiveResult/BaselineNode
  transition execution and business refs atomically
  persist integration outbox record atomically
```

Outbox delivery 发生在 T1/T3 commit 之后；业务状态与待投递 outbox record 必须同事务。正式故障点名称为 `after_business_finalize_before_outbox_delivery`。

## 4. Repository journal 与 full evidence

每个外部请求具有 immutable idempotency key、request digest 和（适用时）RepositoryImportArtifact digest。Repository journal 至少区分：

- `PREPARED`：请求被接受并获得确定 operation identity。
- `APPLIED`：commit/ref effect 已形成，记录 before/after commit 等 effect evidence。
- `VERIFIED`：operation-kind-specific verification 完成。Submit import 必须 full scan committed ref 并匹配 SnapshotManifest；Archive ref CAS 必须匹配 request digest、before/after commit 与当前 ref evidence，目标 commit 沿用 Submit 时已完成的内容验证，不重复全表扫描。

Reconciler 的 effect classification 只允许：

| Classification | 含义 | 允许动作 |
| --- | --- | --- |
| `NOT_APPLIED` | 权威证明无 effect 且旧请求不再运行 | 使用原 key 重放，或 ABORT |
| `UNKNOWN` | 证据不足或仍可能应用 | 保持 EFFECT_PENDING，继续查询/人工修复 |
| `APPLIED` | effect 已发生，尚未 VERIFIED/finalized | readback、验证和 finalize；禁止重发 |

业务侧先查本地 Finalize 结果，再查 Repository journal/operation/commit/ref 证据。不得仅凭超时、连接中断、worker lease、HTTP code 或客户端异常推断 `NOT_APPLIED`。

## 5. Evidence-first recovery

当请求可能已被 Repository 接受时，禁止 blind replay，禁止生成新 idempotency key，禁止重建另一份“逻辑等价”的 import artifact。恢复必须复用原 execution、operation、request digest、artifact ref 和 Repository key。

`RUNNING`/lease expired step 的接管规则：

1. 加载 durable checkpoint 与 Repository operation identity。
2. 查询 Repository journal/effect evidence。
3. `VERIFIED/APPLIED` 时从相应 checkpoint 向前完成验证或 T3。
4. `UNKNOWN` 时继续 reconcile，不调用写 API。
5. 仅有 explicit `NOT_APPLIED` evidence 时，才允许以原 key 重发原 bytes。

任何 handler 不能把“重做整个 step”作为默认恢复策略。Readback mismatch 保留 effect evidence 和占用，不创建业务成功结果，也不伪装为可安全重试。

## 6. FailureDescriptor

Shared Kernel 只定义下列公共、可序列化维度：

```text
FailureDescriptor
  code
  category
  phase
  recovery
  effect
  message
  details
  diagnostic_refs optional

category: INVALID_REQUEST | FORBIDDEN | NOT_FOUND | STATE_CONFLICT |
          DEPENDENCY_FAILURE | INTEGRITY_FAILURE | INTERNAL_FAILURE
recovery: RETRY_COMMAND | RETRY_SAME_OPERATION | RECONCILE_SAME_OPERATION |
          NEW_USER_INPUT | OPERATOR_INTERVENTION | NO_RETRY
effect: NOT_APPLIED | UNKNOWN | APPLIED | NONE
```

Use case owner 必须定义 stable `code`、`phase` 和 typed `details` schema；Shared Kernel 不拥有统一业务 ErrorCode registry。`retryable` 若对外出现，只是由 `recovery` 派生的兼容字段，不是权威事实。Business Outcome、Command rejection、Execution failure 和 external-effect uncertainty 必须分离。

最低必需 code 包括：Submit 的 stale/binding/idempotency/`NO_CANONICAL_CHANGE`、Repository outcome unknown、import rejection、readback integrity 和 finalize recovery；Review 的 stale/transition/reason；Archive 的 stale plan/selection/readiness、Repository outcome unknown、main ref drift 和 finalize recovery。完整枚举由对应 application contract 维护。

## 7. Fault 与 recovery conformance

稳定注入点为：

```text
before_repository_effect
after_repository_request_sent
after_repository_effect_confirmed
before_readback_verified
after_readback_verified
before_business_finalize
after_business_finalize_before_outbox_delivery
```

每个 recovery scenario 同时断言失败后 checkpoint 与恢复后终局，包括 execution/operation 状态、业务事实有无、Repository journal/ref/commit、Workspace/serialization occupancy、下一恢复动作和最终 event/artifact。注入通道只能在 test profile 启用；生产 request schema 不暴露 fault control。

## 8. 版本与 wire 规则

Module public：是。Persisted：必须。Wire：business persistence + Repository wire JSON/gRPC + artifact refs。

改变四态含义、effect classification、T1/T2/T3 原子边界或 replay 合法性属于 breaking change。新增 use-case code 由其 owner 版本化，不要求提升 Shared Kernel primitive version，除非公共维度改变。

## 9. 验收标准

- T1/T3 的业务事实、Operation/outbox 原子性有 transaction tests。
- 每个 request acceptance 后故障都从 journal/evidence 恢复，无 blind replay。
- Repository restart、worker takeover、重复投递和 Finalize crash 最终只产生一个业务结果。
- `UNKNOWN/APPLIED` 不释放占用；只有 VERIFIED finalize 或 explicit `NOT_APPLIED` abort 释放。
- Python/Repository 对 request digest、operation identity 和 evidence status 的解释一致。
- 故障场景使用正式 `...before_outbox_delivery` 名称。

## 10. 关联文档

- [Business Lifecycle and State](business-lifecycle-and-state.md)
- [Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
- [Fixture Oracle and Conformance](fixture-oracle-and-conformance.md)
- [ADR 0003](../adr/0003-external-effect-reconciliation.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)

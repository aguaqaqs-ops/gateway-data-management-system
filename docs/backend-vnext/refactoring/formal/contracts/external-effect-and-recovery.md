# External Effect and Recovery Contract

状态：正式设计（Accepted）

阶段：Phase 0 结论；Phase 2、Phase 4、Slice 5B 实现

Contract ID：`gateway-vnext.external-effect-and-recovery`

Owner：Submit Application（业务 execution）；Operations（通用执行）；Repository Service（effect evidence）

Semantic version：`4.0.0`

2026-08-02收口：Repository Service effect遵循ADR 0009和Repository Service
Contract的caller-selected verification、stable failure code与minimal recovery。旧
`PREPARED/APPLIED/VERIFIED` Repository journal、`FailureDescriptor`和generic
effect taxonomy不再约束当前实现；Phase 0–1错误表达由owner-owned simple error持有。

2026-09-06 amendment：当前没有integration-event consumer，T1/T3不创建outbox，删除
dispatcher与`after_business_finalize_before_outbox_delivery`故障点。Archive直接把既有
Submission commit提升为业务Baseline，不产生Repository写effect，因此不属于本文。

## 1. 目的与 owner 分界

本文固定跨 Repository Service 写 effect 的事务、证据、失败和恢复规则。所有权按语义分离：

| 语义 | 唯一 owner |
| --- | --- |
| SubmitAttempt、命令验收、业务 finalize | Submission Application/Domain |
| Operation/Step、claim/lease/retry/checkpoint | Operations |
| Repository operation、commit marker、commit/ref result | Repository Service |
| 业务Operation错误表达 | Operations/use case owner |
| stable code、message、optional details | 对应 use case owner |

Operation terminal status不等于业务终局；simple error也不替代Repository
operation/commit/ref result。

## 2. Execution 四态

SubmitAttempt拥有以下状态：

```text
PREPARED -> EFFECT_PENDING -> FINALIZED
PREPARED -----------------> ABORTED
EFFECT_PENDING -----------> ABORTED
```

只有下列结果允许终止：业务 finalize 成功进入`FINALIZED`；或者Repository operation
以`IMPORT_REJECTED`、`EXPECTED_COMMIT_MISMATCH`或
`VERIFICATION_FAILED_NOT_PUBLISHED`终止，且result与原operation identity匹配，进入
`ABORTED`。连接中断、poll timeout、worker failure、lease expiry和
`MANUAL_RECOVERY_REQUIRED`均不允许释放业务占用或serialization key。

## 3. T1/T2/T3 边界

```text
T1 AcceptSubmit (business DB transaction)
  validate immutable bindings, idempotency and occupancy
  persist PREPARED SubmitAttempt + Operation atomically
  acquire Workspace/repository serialization occupancy

T2 External effect (durable worker + Repository Service)
  persist immutable request/artifact checkpoint
  submit idempotent Versioned import once
  poll repository-scoped operation
  service reconciles matching commit marker or reports manual recovery

T3 Finalize (business DB transaction)
  require matching SUCCEEDED result, requested==completed verification,
          type policy and business-owned package/digest facts
  create exactly one Submission
  transition SubmitAttempt, Workspace and Operation atomically
```

V1没有已确认integration-event consumer，不创建outbox table、record或dispatcher。未来出现
真实consumer时必须先定义event owner、delivery contract、retention与replay边界，再以独立
contract/ADR加入；不得预建空outbox。

## 4. Repository operation result

每个import具有immutable idempotency key和Repository内部request fingerprint。
Repository Operation只公开`QUEUED | RUNNING | SUCCEEDED | FAILED`。

- SUCCEEDED返回matching CommitId和target ref；
- FAILED返回Repository-owned stable code；普通未发布失败只限`IMPORT_REJECTED`、
  `EXPECTED_COMMIT_MISMATCH`或`VERIFICATION_FAILED_NOT_PUBLISHED`；
- `MANUAL_RECOVERY_REQUIRED`表示commit/ref/artifact证据矛盾，需要operator且不得释放
  business occupancy；
- timeout、连接中断或worker failure不等于Repository operation失败；
- 业务侧先检查本地Finalize结果，再以原operation identity查询Repository。

## 5. Evidence-first recovery

当请求可能已被Repository接受时，业务worker禁止blind replay或生成新
idempotency key；必须复用原operation identity查询。Repository Service启动恢复：

1. main已发布matching operation commit时补齐SUCCEEDED；
2. private ref有唯一candidate且main仍为expected时继续verification/CAS（continue路径
   无条件以`STRUCTURAL`复核candidate作为证据补强；`completed_verification_policy`仍等于
   requested policy，见[Repository Service Contract](repository-service.md) §11规则3）；
3. 完全未找到matching commit且artifact完整时使用原artifact/key自动重试一次；
4. 多commit、ref矛盾、artifact缺失或无法判断时FAILED /
   MANUAL_RECOVERY_REQUIRED。

业务worker只消费该终态；不自行推断commit是否存在。

## 6. Error boundary

Shared Kernel不拥有generic FailureDescriptor、category/recovery/effect taxonomy或
统一业务ErrorCode registry。每个use case拥有最小错误：

```text
code
message
details optional
```

HTTP status或Operation/Repository状态表达请求与执行结果。External-effect uncertainty
由持久业务execution状态、Repository operation identity和commit/ref result表达，
不复制进每个error object。

Submit owner必须定义stable`code`和所需typed`details`。最低必需code包括：
Submit的stale/binding/idempotency/`NO_CANONICAL_CHANGE`、Repository outcome
unknown、import rejection和finalize recovery。Review与Archive没有Repository写effect，
其owner-specific错误由Business Lifecycle contract和各自use case拥有。

## 7. Fault and recovery tests

稳定注入点为：

```text
before_repository_effect
after_repository_request_sent
after_repository_effect_confirmed
before_repository_verification
after_repository_verification
before_business_finalize
after_business_finalize_commit_before_worker_ack
```

每个重要failure test同时断言失败后checkpoint与恢复后终局，包括
execution/operation状态、业务事实有无、Repository operation/ref/commit、
Workspace/serialization occupancy、下一恢复动作和最终业务事实/artifact。测试使用
owner-specific helper或integration test，不要求generic scenario runner、fault
registry或RunEvidence。注入通道只能在test profile启用；production request schema
不暴露fault control。

## 8. 版本与 wire 规则

Module public：是。Persisted：必须。Wire：business persistence + Repository HTTP/JSON
control DTO + Arrow IPC row stream + artifact refs。

改变四态含义、T1/T2/T3原子边界或replay合法性属于breaking change。新增
use-case code由其owner版本化，不要求提升Shared Kernel version。

## 9. 验收标准

- T1/T3 的业务事实与Operation原子性有transaction tests；schema中没有未被真实consumer
  需要的outbox。
- 每个 request acceptance 后故障都从 journal/evidence 恢复，无 blind replay。
- Repository restart、worker takeover、重复投递和 Finalize crash 最终只产生一个业务结果。
- Unknown outcome不允许blind replay。Business occupancy只有在matching SUCCEEDED
  result完成finalize，或matching普通未发布stable failure完成abort后释放；
  MANUAL_RECOVERY_REQUIRED继续占用直到operator恢复并产生允许的终局。
- Python/Repository对request fingerprint、operation identity和result的解释一致。
- T3 commit后worker丢失响应的场景使用正式
  `after_business_finalize_commit_before_worker_ack`名称。

## 10. 关联文档

- [Business Lifecycle and State](business-lifecycle-and-state.md)
- [Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
- [Fixture Oracle and Conformance](fixture-oracle-and-conformance.md)
- [ADR 0003](../adr/0003-external-effect-reconciliation.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
- [Repository Service](repository-service.md)
- [ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)

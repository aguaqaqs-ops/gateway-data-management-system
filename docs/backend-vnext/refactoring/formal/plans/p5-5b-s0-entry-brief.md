# P5-5B-S0 Entry Brief: Submit Acceptance and Finalize

状态：**ENTRY BASELINE ACCEPTED — DETAILED DESIGN READY; IMPLEMENTATION BLOCKED BY P4-R6**

日期：2026-09-13

Owner：Submit Application + HTTP Interface + Submit JobDefinition

上游：[P5 Business Vertical Slices Design Baseline](p5-business-vertical-slices-design.md)、
[P5-5A S6 Handoff](p5-5a-s6-handoff.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)、
[Repository Service Contract](../contracts/repository-service.md)、
[Storage Mutation and Change Set](../contracts/storage-mutation-and-change-set.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[P4/R4 JobDefinition and Checkpoint Handoff](p4-r4-jobdefinition-checkpoint-handoff.md)、
[P4/R5 Retry, Takeover and Effect Recovery Handoff](p4-r5-retry-takeover-effect-recovery-handoff.md)

## 1. Entry identity and decision

```yaml
step_id: P5-5B-S0
entry_kind: submit_acceptance_finalize_vertical_slice
discussion_base_sha: c8ff3606a59901e32f92dda98aa045a936c361df
p5_5a_slice_exit: pass
p4_r6_exit: pending
p5_design_baseline: accepted
p5_5b_s0_entry_brief: accepted
p5_5b_design_s0_authorized: yes
p5_5b_implementation_authorized: no
p5b_real_repository_effect_authorized: no
source_or_test_change_authorized: false
next_step: P5-5B-S0-detailed-design-and-execution-plan
next_step_authorized: yes
```

S0 的目的，是在实现前冻结 5B 的 application/domain/HTTP/Operation 边界、T1/T2/T3 原子语义、
Repository effect/reconciliation、takeover 边界、最小持久事实、JobDefinition、失败语义和验证矩阵。
本 brief 不授权修改 `vnext/**`。P4-R6 最终 exit 和明确的 5B implementation authorization 仍是
任何 source、test、migration、route、Repository write effect 或 deployment 改动的硬前置。

## 2. Objective and user journey

5B 在 5A 已 land 的 Upload/Preview 之上，交付首个跨 Repository 写 effect 的正式纵切：

```text
resolve identity and provisioned scope
  -> load OPEN Workspace with current UploadRevision and PreviewResult
  -> reject derived-stale Preview or NO_CANONICAL_CHANGE before Attempt
  -> AcceptSubmit (T1): persist SubmitAttempt + Operation
  -> poll Operation
  -> build/reuse RepositoryImportArtifact and SubmitImport (T2)
  -> poll/checkpoint repository-scoped operation
  -> evidence-first reconcile on unknown outcome
  -> Finalize Submission + release Attempt occupancy (T3)
  -> read immutable Submission facts
```

前端可以把 Preview 与 Submit 串成一次交互，但 Backend 保留独立 command、独立幂等 fingerprint、
独立失败边界和 T1/T2/T3 事务屏障。Preview 成功不承诺 Submit 成功；Repository 成功前不存在
Submission；Submit 失败不使 UploadRevision 或 PreviewResult 失效。

## 3. In scope and non-goals

### 3.1 In scope

- AcceptSubmit command、T1 业务验收与 Workspace/repository serialization occupancy；
- SubmitAttempt 四态、`NO_CANONICAL_CHANGE`、Preview binding 与 derived-stale 拒绝；
- T1 pin responsibility 从 current Preview 原子转给 Attempt；
- Submit JobDefinition、immutable request/artifact checkpoint、Repository import poll/reconcile；
- 固定 Repository policy（caller 不可选）与 evidence-first recovery；
- T3 Finalize：exactly one Submission、Workspace 占用切换、Operation terminal publication；
- worker takeover、duplicate delivery、crash/restart 与 Repository Service restart 恢复；
- SubmitAttempt/Submission/Operation read DTO、re-authorization 与必要 HTTP/OpenAPI DTO；
- focused、unit、integration、serial、static 和适用 current-HEAD container gates。

### 3.2 Out of scope

- Review、Archive、History Compare、Workspace create/upload/preview 语义变更；
- outbox table、dispatcher、integration-event consumer；
- caller-selectable Repository target ref、verification policy、unknown type policy 或 mutation policy；
- Baseline/Repository provisioning、Archive ref mutation、History tree projection；
- blind replay、新 idempotency key 或 worker 自行推断 commit/ref 存在；
- legacy HTTP/persistence compatibility；
- generic refcount GC、arbitrary workflow DAG、per-table durable Step 或 HA/multi-worker membership；
- broker、external DB 和 new security principal。

## 4. Owner and dependency boundary

```text
HTTP Interface
  -> Submit Application use cases
       -> Workspace/Submit Domain + business repository ports
       -> Storage Projection / RepositoryImportArtifact builder ports
       -> Operation Runtime port
       -> ArtifactStore / Repository Client read+write ports

infrastructure
  -> SQLite UoW and repositories
  -> local ArtifactStore adapter
  -> Repository Client import/effect adapter
```

Domain 不依赖 FastAPI、sqlite3、Operation record、ArtifactStore path、Repository DTO 或
capability implementation。Application 只 import capability public contracts 与 formal Repository
wire DTO。Operations 只解释 versioned job payload/checkpoint envelope，不解释 Workspace 业务
状态；Submit handler 通过 application port 加载 T1 冻结 binding。

## 5. Provisioned scope and authorization

每个命令先从当前 session 取得：

```text
actor_id
gateway_device_external_key
business_project_id
permissions
```

control-plane adapter 必须把 device/project 解析到唯一 active Repository，并返回当前
BaselineHead/BaselineNode。mapping 缺失、disabled gateway、多 active project 或 Baseline 缺失均在
AcceptSubmit 前 fail closed。

AcceptSubmit 必须 exact 匹配 owner actor、device 和 project，并要求 submit 权限（exact permission
字符串由 S0 HTTP contract 冻结）。SubmitAttempt、Submission、Operation 和必要 artifact read 每次
读取都重新检查当前 session、mapping scope 与 permission；T1 接受时授权不成为永久读票据。
session expiry 不取消已接受 Submit，disabled gateway 也不取消已 accepted 且可恢复的 external
effect，但都阻止新 command 和未授权读取。

Worker 不持续重新授权；它只执行已接受、冻结且可恢复的 job。结果读取不能依赖接受时权限。

## 6. Minimal business records

本节冻结语义字段，不冻结 SQLite 列名或 HTTP 拼写。

```text
SubmitAttempt
  submit_attempt_id
  workspace_id + generation
  preview_result_id + upload_revision_id
  repository_id
  business_baseline_node_id
  business_baseline_commit_id
  repository_expected_commit_id   # T1 冻结的技术 main，不得与 business baseline 混用
  canonical_business_digest
  source_artifacts + snapshot table artifact refs
  repository_import_artifact_ref optional
  repository_operation_id optional
  repository_operation_evidence optional
  requested_verification_policy: STRUCTURAL   # maps to SubmitVersionedImport wire
  requested_unknown_type_policy: REJECT       # maps to SubmitVersionedImport wire
  requested_target_ref: main                # maps to SubmitVersionedImport wire
  builder_mutation_policy: REBUILD_ALWAYS   # Storage Mutation / RepositoryImportArtifact builder; not Repository wire
  idempotency_key + request_fingerprint   # durable checkpoint/request identity; HTTP via Idempotency-Key header
  operation_id
  state: PREPARED | EFFECT_PENDING | FINALIZED | ABORTED
  submission_id optional
  created_by / created_at / finalized_at / aborted_at optional

Submission
  submission_id
  submit_attempt_id unique
  workspace_id + generation
  preview_result_id
  repository_id
  business_baseline_node_id + business_baseline_commit_id
  repository_commit_id            # SUCCEEDED import 的 matching CommitId
  canonical_business_digest
  source/package/digest facts owned by Submit owner
  created_at
```

Workspace 继续承载 `active_submit_attempt_id` 与 `active_submission_id` 占用指针；Attempt
`FINALIZED` 原子切换到 Submission 占用，`ABORTED` 释放 Attempt 占用。Operation terminal status、
effect unknown 或已 applied 但未 finalize 都不能单独释放占用。

T1 checkpoint 与 durable request identity 可以保存 `idempotency_key` 及完整
request fingerprint，用于 T2 reconcile 与 evidence-first recovery；这与 Repository HTTP
传输边界分离。

Repository HTTP 调用遵守 [Repository Service Contract](../contracts/repository-service.md)
§6 wire 与 §10 SubmitVersionedImport：

- `POST /v1/repositories/{repository_id}/versioned/imports`；path 中的 `{repository_id}`
  必须与 T1 冻结 scope 一致；
- `Idempotency-Key` header 传输 immutable idempotency key；**不在** JSON body 中重复；
- closed JSON body **必须**包含正式 `SubmitVersionedImportRequest` DTO 的全部字段：
  `repository_id`、`artifact_ref`、`target_ref`、`expected_commit_id`、
  `verification_policy`、`unknown_type_policy`；`body.repository_id` **必须**等于 path
  `{repository_id}`；不得扩展 Repository request/result DTO。

`builder_mutation_policy: REBUILD_ALWAYS` 属于
[Storage Mutation and Change Set](../contracts/storage-mutation-and-change-set.md) /
`RepositoryImportArtifact` builder，不出现在 import HTTP request/result body。

## 7. Commands and idempotency

5B 公开以下逻辑 use case；exact URL、header 与 JSON 字段在 S0 HTTP contract 中冻结：

```text
AcceptSubmit
GetOperation
GetSubmitAttempt
GetSubmission
```

`AcceptSubmit` 要求 Workspace expected version、exact current PreviewResult（非 derived-stale）、
expected BaselineHead node/version、idempotency key 和当前支持的 submit options。fingerprint 至少覆盖
Workspace/scope、expected version、preview/upload/generation binding、baseline node/commit、
canonical digest、frozen SubmitVersionedImport wire policy 与 `builder_mutation_policy`。same key/same fingerprint 返回原 SubmitAttempt；
same key/different fingerprint 为 409。

若 Preview-bound canonical business digest 等于当前 business base，在创建 Attempt 前返回
`NO_CANONICAL_CHANGE`：不得创建 Operation、Repository request、Submission 或 BaselineNode。

## 8. T1 AcceptSubmit frozen boundary

T1 在单一 control DB 短事务内重新检查：

- exact Workspace scope、OPEN state、无 active SubmitAttempt 占用冲突；
- current UploadRevision、generation、current PreviewResult 且 `derived_stale=false`；
- current provisioned Repository 与 BaselineHead node/version；
- preview/source/snapshot artifact refs 存在、可读且 closure 完整；
- idempotency fingerprint 无冲突；
- 静态 JobDefinition/decoder/handler 版本已注册。

成功后原子：

- 创建 `PREPARED` SubmitAttempt 与 Operation（及首个 PENDING Step）；
- 把 SnapshotTableArtifact pin responsibility 从 current Preview 转给 Attempt；
- 设置 Workspace `active_submit_attempt_id` 并 acquire repository/BaselineHead serialization occupancy；
- **不**创建 outbox、Submission、Repository request 或 BaselineNode。

T1 checkpoint 必须同时冻结 `business_baseline_commit_id` 与 `repository_expected_commit_id`。
任何 T1 失败、CAS 失败或 pin transfer 失败均不得留下部分 Attempt 或部分 pin 状态。

## 9. T2 external effect frozen boundary

T2 由 durable worker + Repository Service 执行，遵守 P4-R5 takeover/lease 规则：

```text
job_kind: backend-vnext/submit
job_contract_version: backend-vnext/submit/v1

prepare_import
  -> submit_import
  -> await_import_result
```

`prepare_import`：

- 从 immutable Preview-bound SnapshotTableArtifact 构建或复用 `RepositoryImportArtifact`；
- 使用 T1 冻结 `builder_mutation_policy: REBUILD_ALWAYS` 驱动 Storage Mutation planner（见
  [Storage Mutation and Change Set](../contracts/storage-mutation-and-change-set.md) §2）；
- 每个 Attempt 只构建一次并持久 checkpoint；unknown outcome 后禁止重建 package 或分配新 key；
- 上传 BackendArtifactRef 与 raw SHA，再复用 Repository 返回的独立 RepositoryArtifactRef；
- 两个 ref 字段同形但 ID scope 与 nominal type 不同，不得共享 class 或相互复制 artifact ID。

`submit_import`：

- 调用正式 [SubmitVersionedImport](../contracts/repository-service.md) contract；不得扩展
  Repository request/result DTO；
- HTTP：`POST /v1/repositories/{repository_id}/versioned/imports`；path `{repository_id}` 与 T1
  checkpoint scope 一致；
- `Idempotency-Key` header 携带 T1 冻结的 immutable idempotency key；durable
  checkpoint/request identity 保存同一 key 供 reconcile，但 key **不在** JSON body 中；
- closed JSON body **必须**包含正式 `SubmitVersionedImportRequest` 全部字段：
  `repository_id`、`artifact_ref`、`target_ref=main`、`expected_commit_id`、
  `verification_policy=STRUCTURAL`、`unknown_type_policy=REJECT`；`body.repository_id`
  **必须**等于 path `{repository_id}`；
- `REBUILD_ALWAYS` 不在 import HTTP request/result 中出现；它只约束 `prepare_import` 的
  artifact 构建（`builder_mutation_policy`）；
- 以 immutable idempotency key 提交 idempotent Versioned import 一次；
- 持久 immutable request/artifact checkpoint 后 crossing effect boundary 进入 `EFFECT_PENDING`。

`await_import_result`：

- poll repository-scoped operation；
- Repository Service 负责 matching commit marker、verification/CAS 与 evidence-first reconcile；
- 业务 worker **禁止** blind replay、生成新 idempotency key 或自行推断 commit/ref 是否存在；
- timeout、连接中断、worker failure、lease expiry 不等于 Repository operation 失败；
- `MANUAL_RECOVERY_REQUIRED` 不得释放 business occupancy。

## 10. T3 Finalize frozen boundary

T3 在单一 control DB 短事务内，仅当 matching Repository operation 为 `SUCCEEDED` 且：

- `requested_verification_policy == completed_verification_policy`；
- artifact ID、CanonicalizationManifest digest、expected parent、target ref 和 unknown type policy
  均与 T1 checkpoint 一致；
- business-owned package/digest facts 通过 Submit owner validation；

才允许：

- 创建 exactly one Submission；
- 把 SubmitAttempt 转为 `FINALIZED`；
- 把 Workspace 占用从 Attempt 原子切换到 Submission；
- terminal publish Operation=`SUCCEEDED`；
- 释放 Attempt 对 SnapshotTableArtifact 的 pin（Submission 长期 authority 由 SourcePackageArtifact、
  CanonicalizationManifest 与 canonical Dolt history 提供）。

Finalize 重放先返回既有 matching Submission，不产生第二个结果。Repository verification 不替代
business-owned digest/binding validation。

普通未发布 stable failure（`IMPORT_REJECTED`、`EXPECTED_COMMIT_MISMATCH`、
`VERIFICATION_FAILED_NOT_PUBLISHED`）且 result 与原 operation identity 匹配时，Attempt 进入
`ABORTED` 并释放占用；不得创建半完成 Submission。

## 11. Takeover, recovery and admin boundary

5B 外部 effect 只能复用原 request/artifact/idempotency/Repository operation identity 进行
reconcile。Repository Service 启动恢复顺序见
[External Effect and Recovery](../contracts/external-effect-and-recovery.md) §5；业务 worker 只
消费终态。

Takeover 与 duplicate delivery 遵守 P4-R5 既有 lease/claim/checkpoint 规则：

- worker crash、lease loss、Repository Service restart 不得产生 duplicate submission/ref/commit；
- 迟到 worker 不得通过 Attempt/Workspace CAS 发布第二个 Submission；
- T3 commit 后 worker 丢失响应的场景使用正式
  `after_business_finalize_commit_before_worker_ack` 注入点。

部署内部 admin HTTP 复用现有 internal bearer，仅允许：

```text
RESUME_RECONCILE
RETRY_FROM_CHECKPOINT
ABORT_CONFIRMED_FAILURE
```

请求必须带 Operation/Step expected versions 和 reason；不允许任意 record 编辑、force-success、
force 移动 Repository ref 或 blind replay。

## 12. Failure, stale and occupancy semantics

- derived-stale Preview 必须拒绝 AcceptSubmit；不自动重算 Preview。
- 新 Upload generation 或 BaselineHead drift 不 retroactively 修改 immutable PreviewResult，只影响
  后续 Submit 验收。
- `NO_CANONICAL_CHANGE` 在 Attempt 前返回；不构建 RepositoryImportArtifact、不提升 source retention、
  不调用 Repository。
- required import/materialization/verification failure 不创建 Submission，也不回滚已接受 Upload/
  Preview。
- connection 中断、poll timeout、worker failure、lease expiry 和 `MANUAL_RECOVERY_REQUIRED` 均不
  允许释放 Workspace/repository serialization occupancy，直到 matching 允许终局。
- AcceptSubmit 与 StartArchive 在同一 Repository/BaselineHead scope 内通过 control DB 事务串行验收
  （Archive 属 5D；5B 只保留 occupancy 互斥语义，不实现 Archive）。

## 13. HTTP and error boundary

HTTP DTO 与 domain record 分离，拒绝 unknown fields 和 scope/body 冲突。AcceptSubmit 使用 202，
idempotency/version/binding conflict 使用 409，认证 401、授权 403、缺失 404、validation 422、
derived-stale/`NO_CANONICAL_CHANGE` 使用 owner-defined 4xx、dependency/readiness 503。具体 route
和 stable code 表由 S0 HTTP contract 拥有。

最低错误族必须覆盖：scope/mapping/baseline missing、Workspace version/current preview stale、
derived-stale preview、idempotency conflict、`NO_CANONICAL_CHANGE`、Preview binding mismatch、
Attempt occupancy conflict、Repository outcome unknown、import rejection、verification mismatch、
finalize recovery、superseded、artifact unavailable 和 service not ready。错误使用 owner-owned
`code/message/details?`，不引入 generic FailureDescriptor。

Operation、SubmitAttempt、Submission response 不得暴露 host path、SQLite key、Repository bearer、
private ref、lease token 或内部 artifact directory。

## 14. Readiness and deployment applicability

Backend 启动必须在开放 HTTP 前完成 settings、control DB migration/integrity、artifact root、
registry 和 Repository Client 连通性检查。worker 独立启动、恢复遗留 Submit Operation 并发布
worker health。Repository Service 必须 healthy，因为 5B 首次引入真实 Repository write effect；
暂时没有 worker 时 Backend 可以保持进程健康但 deployment 不得宣称完整 Submit journey ready。

shutdown 先关闭会创建 SubmitAttempt/Operation 的新 HTTP admission，再让 worker 按 P4 规则
drain/checkpoint。结果读取可以在 admission 关闭后继续，直到 HTTP 进程退出。

5B 会触碰 HTTP、settings/readiness、worker registry、SQLite migration、artifact volume 接线与
Repository write path，因而最终 implementation 候选必须重建 Backend/worker 镜像并运行
current-HEAD container/Compose gate。中间纯 domain/application 改动按比例化策略运行 focused gate。

## 15. Verification matrix

| Barrier | Required evidence |
| --- | --- |
| T1 acceptance | generation/preview/baseline binding、derived-stale 拒绝、`NO_CANONICAL_CHANGE`、occupancy acquire、pin transfer |
| Idempotency/CAS | same/same replay、same/different 409、expected version conflict、并发 AcceptSubmit |
| T2 effect | immutable checkpoint、fixed Repository policy、idempotent import、poll/reconcile、no blind replay |
| T3 finalize | matching SUCCEEDED + policy/digest closure、exactly one Submission、Finalize 重放 |
| Takeover/recovery | worker crash、lease loss、duplicate delivery、Repository restart、late writer fence |
| Failure/occupancy | unknown outcome 不释放占用、ABORTED 仅 matching stable failure、MANUAL_RECOVERY_REQUIRED |
| Artifacts | RepositoryImportArtifact 一次构建、Backend/Repository ref 边界、Attempt 终态 pin 释放 |
| Authorization | accepted work 可完成；每次 Attempt/Submission read 重新授权；disabled gateway 拒绝新工作 |
| Runtime | backend/worker readiness、shutdown order、DB reopen、registry mismatch fail closed |

稳定 fault 注入点见 External Effect and Recovery §7。测试命名按业务行为，不按轮次/finding 编号；
fixed timeout、process、signal 和 crash 测试标 `serial`；真实 Repository/Dolt effect 标
`integration`。最终执行使用仓库权威 runner、五包 ruff/mypy 和适用 current-HEAD image gate。

## 16. S0 deliverables and exit

S0 详细设计必须产出：

1. SubmitAttempt/Submission domain 与 application public contract；
2. HTTP route/DTO/error/permission 表；
3. SQLite schema/migration 和 T1/T3 transaction/CAS 矩阵；
4. RepositoryImportArtifact builder、ArtifactStore pin transfer 与 checkpoint 规则；
5. Submit job payload、decoder、handler、checkpoint 和 import result closure 版本；
6. Repository Client import/effect adapter 与 evidence-first reconcile 映射；
7. settings/readiness/bootstrap/worker composition 与 container applicability；
8. staged implementation plan、allowed paths、test owners、review 和 handoff 格式。

S0 exit 只允许把 `p5_5b_design` 标记为 accepted。任何 implementation authorization 必须另行记录，
并要求 P4-R6 exit=pass、当前 candidate 无未处理 contract drift、明确的 first implementation step、
`p5b_real_repository_effect_authorized: yes` 和适用验证命令。

## 17. Stop and reopen conditions

- AcceptSubmit 需要 caller-selectable Repository policy 或动态 target ref；
- T1/T2/T3 原子边界、四态含义或 replay 合法性无法由现有 contract 表达；
- evidence-first recovery 需要 blind replay、新 idempotency key 或 worker 推断 commit/ref；
- Preview-bound digest 与 base 相同但仍需创建 Attempt/Repository request；
- SQLite 不能原子提交 T1 pin transfer + Attempt + Operation，或 T3 Submission + occupancy 切换；
- 需要 outbox、integration-event consumer、broker、external DB、multi-worker HA 或跨库事务；
- Submit 需要动态 DAG、多个同时 active Step 或持久 per-table workflow；
- P4-R6 发现会改变 5B 依赖的 Operation/Step/worker/checkpoint/Repository effect 契约。

当前下一动作是完成 S0 详细设计和 execution plan；在 P4-R6 最终 exit 前不得开始实现。

## 18. P5-5B-S0 docs-only handoff record

```yaml
stage: P5-5B-S0-docs-only-handoff
candidate_head: c8ff3606a59901e32f92dda98aa045a936c361df
conversation_context: same
scope_paths: [docs/**]
changed_paths:
  - docs/backend-vnext/README.md
  - docs/backend-vnext/refactoring/formal/README.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s0-entry-brief.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-s0-entry-brief.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-baseline-acceptance.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-upload-preview-design.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-upload-preview-execution-plan.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-remediation-review.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-s6-handoff.md
source_or_test_change_authorized: false
p5_5a_slice_exit: pass
p5_5b_s0_entry_brief: accepted
p5_5b_design_s0_authorized: yes
p5_5b_implementation_authorized: no
decision: pass
next_step: P5-5B-S0-detailed-design-and-execution-plan
next_step_authorized: yes
```

## 19. P5-5B-S0 authority consistency record

```yaml
stage: P5-5B-S0-authority-consistency
candidate_head: c8ff3606a59901e32f92dda98aa045a936c361df
scope_paths: [docs/**]
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p5-business-vertical-slices-design.md
  - docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md
  - docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s0-entry-brief.md
  - docs/backend-vnext/refactoring/formal/README.md
source_or_test_change_authorized: false
decision: pass
```

## 20. P5-5B-S0 Repository wire closure record

```yaml
stage: P5-5B-S0-repository-wire-closure
candidate_head: c8ff3606a59901e32f92dda98aa045a936c361df
scope_paths: [docs/**]
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s0-entry-brief.md
  - docs/backend-vnext/refactoring/formal/README.md
finding_closed: SubmitVersionedImport_required_body_repository_id_and_path_scope_match
source_or_test_change_authorized: false
decision: pass
```

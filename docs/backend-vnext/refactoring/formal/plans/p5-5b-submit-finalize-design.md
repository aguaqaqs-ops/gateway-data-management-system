# P5-5B Submit Acceptance and Finalize Detailed Design

状态：**CANDIDATE / DRAFT — independent docs review required; implementation not authorized**

日期：2026-09-13

设计基线 HEAD：`7e8cea7b3454a8cfdd7c2ba880becee5c427a0de`

Owner：Submission Application、Submission Domain、HTTP Interface、Submit JobDefinition

上游：[P5 Business Vertical Slices Design Baseline](p5-business-vertical-slices-design.md)、
[P5-5B-S0 Entry Brief](p5-5b-s0-entry-brief.md)、
[P5-5A S6 Handoff](p5-5a-s6-handoff.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)、
[Storage Mutation and Change Set](../contracts/storage-mutation-and-change-set.md)、
[Repository Service](../contracts/repository-service.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[P4/R4 JobDefinition and Checkpoint Handoff](p4-r4-jobdefinition-checkpoint-handoff.md)、
[P4/R5 Retry, Takeover and Effect Recovery Handoff](p4-r5-retry-takeover-effect-recovery-handoff.md)、
[Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)

配套执行计划：[P5-5B Submit/Finalize Execution Plan](p5-5b-submit-finalize-execution-plan.md)

Finding输入：[P5-5B-S0 Independent Docs Review](p5-5b-s0-independent-docs-review.md)

本文只组合并映射 owning contracts，不复制或取代其规范正文。字段表、HTTP shape、job-specific
payload/checkpoint 和事务参与者是 5B consumer 设计；Operation 状态/lease、Repository wire、
canonical artifact、mutation policy 的语义继续由上游 owner 唯一拥有。若本文与 owning contract
冲突，以 owning contract 为准并停止设计进入 reopen，不能用兼容代码维持两套含义。

## 1. Authority and authorization boundary

```yaml
design_kind: p5_5b_submit_acceptance_finalize_detailed_design
design_base_sha: 7e8cea7b3454a8cfdd7c2ba880becee5c427a0de
p5_5a_slice_exit: pass
p5_5b_s0_entry_brief: accepted
p5_5b_design_s0_authorized: yes
p4_r6_exit: pending
p5_5b_design: candidate_draft
p5_5b_implementation_authorized: no
p5b_real_repository_effect_authorized: no
source_or_test_change_authorized: false
scope_paths: [docs/**]
next_step: independent_docs_review
```

本轮不授权 source、test、migration、dependency、HTTP route、settings、Docker、Compose 或
deployment 改动，不运行 Python、Dolt 或 Docker 测试，不提交。实现必须同时满足：
`p4_r6_exit=pass`、独立 docs review 接受本 candidate、明确
`p5_5b_implementation_authorized=yes`、`p5b_real_repository_effect_authorized=yes`。

## 2. Requirements and risk baseline

### 2.1 Goal, users and journey

范围内用户是持有当前 session、exact actor/device/project scope 和
`upload_submit_workspace` 权限的 Workspace owner。其目标是把 current、非 stale 的
Preview 作为一次 durable Submit 接受，在 Repository `main` 上产生一个 CAS-protected commit，
并最终获得恰好一个 immutable Submission。UI 只需轮询既有 Operation 和读取 Attempt/Submission；
worker/operator 使用冻结 identity 恢复，不成为终端用户 authority。

组合流程固定为：HTTP acceptance（T1）→ durable Repository effect（T2）→ business finalize
（T3）。Preview 成功不等于 Submit 成功；Repository 成功前不存在 Submission；Submit 失败不
回滚 UploadRevision 或 PreviewResult。

### 2.2 Scope, exclusions and accepted assumptions

范围内：Submit records、HTTP、control DB transaction、artifact builder、三步 JobDefinition、
Repository client composition、reconcile、read authorization、readiness/shutdown 和最终 container
applicability。

范围外：Review/Archive/History、provisioning、legacy compatibility、dynamic target/policy、outbox、
broker、external DB、HA/multi-worker membership、新 principal/UID/helper、Repository Service wire
扩展、generic GC/evidence framework。single host、single worker、本地 SQLite/WAL、Backend HTTP 与
worker 同镜像不同进程、Repository Service 独立内网进程及现有 internal bearer 均为已接受假设。

没有新增未确认架构假设。资源上限和 capacity tuning 沿用既有 bounded settings；确切生产容量仍
deferred，不改变数据、事务或 wire 设计。

### 2.3 Risk classification and assurance

| Object | Class | Consequence and assurance |
| --- | --- | --- |
| Repository commit/`main`、Submission、Workspace ownership | A | 错误发布或跨 scope 写；必须 permission、CAS、idempotency、T1/T3 transaction、response-loss/restart 证明 |
| SubmitAttempt、Operation/Step、occupancy、effect checkpoint | B | 恢复错误或业务永久阻塞；必须 owner、四态、lease/takeover、bounded operator recovery |
| RepositoryImportArtifact bytes、temporary upload、derived snapshot cache | C | 可重建或可重传；bounded、protected while active、best-effort cleanup，不建立新状态机 |
| mapper/decoder/private helper | D | 普通 unit/type tests，不复制 owner 状态机 |

外部 session、HTTP body/header、artifact bytes、Repository scope/path 是不可信边界；同 euid Backend
模块与 worker 是协作信任域。最高风险为 A。验收集中在 commit/main、exactly-one Submission、
scope、occupancy 和 evidence-first recovery，不穷举私有 syscall/interleaving。

## 3. Owner map and dependency direction

| Concern | Unique semantic owner | 5B responsibility |
| --- | --- | --- |
| SubmitAttempt command acceptance/finalize coordination | Submission Application | T1/T3、idempotency、occupancy、cross-owner UoW |
| SubmitAttempt state and Submission invariants | Submission Domain | record construction、four-state transition、exactly-one binding |
| Workspace scope/generation/current pointers | Workspace Domain | expose existing repository port and CAS; no duplicate submit state owner |
| Operation/Step/lease/checkpoint envelope | Operation Runtime/P4 | 5B supplies job payload, job-state decoder and handlers only |
| canonical content/manifest/import package | Storage Projection | 5B invokes public capability and stores its refs/digests |
| `REBUILD_ALWAYS` planning | Mutation Planner | 5B fixes policy input; does not reinterpret policy |
| Repository HTTP/result/recovery evidence | Repository Service | 5B maps exact public DTO through Repository Client |
| terminal-user wire/auth/errors | 5B HTTP Interface | route, closed DTO, permission and stable business code |
| Backend artifact protection | ArtifactStore owner | 5B transfers/clears owner intent in T1/T3 |

依赖方向保持：HTTP → Submission Application → Domain/ports；infrastructure 实现 SQLite UoW、
ArtifactStore、Repository Client ports。Domain 不依赖 FastAPI、sqlite3、Operation records、paths、
Repository DTO 或 capability implementation。Operations 不解释 Workspace/Submission 状态；handler
通过 application port transaction-fresh 加载 Attempt。

## 4. Business records and occupancy projection

本节冻结 5B logical fields 和关系；Repository、Operation、artifact document 内部 shape 不由本文
重定义。所有 ID/timestamp/version 使用现有 bounded/canonical rules。

### 4.1 SubmitAttempt

唯一 owner：Submission Application（acceptance/finalize）+ Submission Domain（record/state）。

```text
SubmitAttempt
  submit_attempt_id
  workspace_id
  workspace_generation
  upload_revision_id
  preview_result_id
  repository_id
  business_baseline_node_id
  business_baseline_commit_id
  baseline_head_version
  repository_expected_commit_id
  canonical_business_digest
  source_artifact_refs[]
  snapshot_table_artifact_refs[]
  preview_ready_closure_ref
  canonicalization_manifest_ref?
  canonicalization_manifest_digest?
  repository_import_artifact_ref?: BackendArtifactRef
  repository_artifact_ref?: RepositoryArtifactRef
  repository_operation_id?
  repository_operation_evidence?
  requested_target_ref: main
  requested_verification_policy: STRUCTURAL
  requested_unknown_type_policy: REJECT
  builder_mutation_policy: REBUILD_ALWAYS
  accept_idempotency_key
  accept_request_fingerprint
  repository_upload_idempotency_key
  repository_import_idempotency_key
  operation_id
  state: PREPARED | EFFECT_PENDING | FINALIZED | ABORTED
  submission_id?
  optimistic_version
  created_by
  created_at
  effect_pending_at?
  finalized_at?
  aborted_at?
  abort_code?
```

字段分组不允许部分成立：Repository import artifact ref 出现时 manifest ref/digest 必须出现；
RepositoryArtifactRef 出现前 BackendArtifactRef 必须已 checkpoint；Repository operation identity
出现时 exact closed import request/fingerprint 必须已 checkpoint；`submission_id` 只在 FINALIZED；
`abort_code` 只在 ABORTED。四态转换和允许终局引用
[External Effect and Recovery §2–§4](../contracts/external-effect-and-recovery.md)；本文不增加状态或边。

`repository_upload_idempotency_key` 与 `repository_import_idempotency_key` 在 T1 生成并冻结，分别以
`p5b-upload-v1:` / `p5b-import-v1:` 加 lowercase SHA-256(`submit_attempt_id` UTF-8 bytes)；它们不是
caller 的 Accept key，避免同一 Repository 内不同 Workspace 恰好复用 caller key。两者长度受
Repository `IdempotencyKey` 限制，并分别用于 upload/import mutation kind。任何恢复都复用其原值。

### 4.2 Submission

唯一 owner：Submission Domain；Submission Application 只在 T3 组合创建。

```text
Submission
  submission_id
  submit_attempt_id unique
  workspace_id
  workspace_generation
  upload_revision_id
  preview_result_id
  repository_id
  based_on_baseline_node_id
  business_baseline_commit_id
  repository_commit_id
  canonical_business_digest
  source_artifact_refs[]
  canonicalization_manifest_ref
  canonicalization_manifest_digest
  repository_import_artifact_raw_sha256
  repository_artifact_id
  requested_verification_policy
  completed_verification_policy
  requested_unknown_type_policy
  target_ref
  created_by
  created_at
```

`submit_attempt_id` 数据库唯一；一条 Attempt 最多且最终恰好对应一条 Submission。Submission
冻结 T1/T3 matching facts，不保存可从 Review/Archive 派生的状态。Repository import package bytes
不是长期 authority；其 raw SHA/Repository artifact ID 是 matching fact，长期 authority 仍由
SourcePackageArtifact、CanonicalizationManifest 和 canonical Dolt history 共同提供。

### 4.3 Workspace and repository-scope occupancy

Workspace Domain 的 logical view 继续包含：

```text
active_submit_attempt_id?
active_submission_id?
```

二者互斥。实现采用同一 control DB 的 1:1 `workspace_submit_occupancy_records` projection，row 缺失
表示 unoccupied；row 存在时恰有一个 `active_submit_attempt_id` 或 `active_submission_id`。这不是
新业务 aggregate，也没有独立 status/version；Workspace `optimistic_version` 是其 CAS version。

Submission Application 另拥有 `repository_submit_occupancy_records`：

```text
repository_id primary key
workspace_id unique
submit_attempt_id unique
business_baseline_node_id
baseline_head_version
acquired_at
```

row existence 表示某 Attempt 持有 Repository/BaselineHead submit serialization。T1 同时建立
Workspace Attempt pointer 与 Repository row；T3 FINALIZED 删除 Repository row并把 Workspace
pointer从 Attempt原子切到Submission；ABORTED删除两类Attempt occupancy。EFFECT_PENDING、
unknown outcome、lease loss、Operation terminal/attention 或 Repository已应用但未T3 均不得释放。

Active Submission 的 Workspace pointer 持续到 5C/5D owner 产生允许的业务终局；5B 不定义其释放
规则。Upload、AcceptSubmit 和未来 StartArchive 必须把这两个 occupancy projection 纳入各自
transaction-fresh acceptance；5B 不实现 StartArchive。

## 5. HTTP v1 contract

### 5.1 Routes and permission

| Method and route | Use case / success | Required current-session permission |
| --- | --- | --- |
| `POST /v1/workspaces/{workspace_id}/submit-attempts` | AcceptSubmit；首次及 same/same replay 均 `202` | `upload_submit_workspace` + exact owner/device/project scope |
| `GET /v1/workspaces/{workspace_id}/submit-attempts/{submit_attempt_id}` | GetSubmitAttempt；`200` | `workspace_read` + current exact scope |
| `GET /v1/workspaces/{workspace_id}/submissions/{submission_id}` | GetSubmission；`200` | `workspace_read` + current exact scope |
| `GET /v1/operations/{operation_id}` | 复用 GetOperation；`200` | `workspace_read` + submit business-ref current exact scope |

AcceptSubmit 的 caller idempotency key 只来自必需 `Idempotency-Key` header（1..255 UTF-8 opaque
characters）；body、query 或 cookie 不接受第二份 key。Authorization/actor/repository identity 只来自
当前 session 与 mapping，不允许 body/header 覆盖。

### 5.2 Closed DTOs

所有 JSON object `extra=forbid`。Path `workspace_id` 不在 body 重复。

```text
AcceptSubmitRequest
  expected_workspace_version: non-negative integer
  preview_result_id: bounded non-empty string
  upload_revision_id: bounded non-empty string
  generation: non-negative integer
  expected_baseline_node_id: bounded non-empty string
  expected_baseline_head_version: non-negative integer
  options: {}  # closed empty v1 object

SubmitAcceptedResponse
  submit_attempt_id
  operation_id
  workspace_id
  preview_result_id
  generation
  state: PREPARED | EFFECT_PENDING | FINALIZED | ABORTED

SubmitAttemptResponse
  submit_attempt_id
  workspace_id
  upload_revision_id
  preview_result_id
  generation
  operation_id
  state
  submission_id?
  business_baseline_node_id
  business_baseline_commit_id
  canonical_business_digest
  created_at
  effect_pending_at?
  finalized_at?
  aborted_at?
  abort_code?

SubmissionResponse
  submission_id
  submit_attempt_id
  workspace_id
  upload_revision_id
  preview_result_id
  generation
  repository_id
  based_on_baseline_node_id
  business_baseline_commit_id
  repository_commit_id
  canonical_business_digest
  canonicalization_manifest_digest
  created_by
  created_at
```

Responses do not expose host path、SQLite key/blob、Repository bearer、private ref、lease token、
checkpoint internals or artifact directory. RepositoryId/CommitId are business-visible opaque values;
RepositoryArtifactId remains internal matching evidence and is not in terminal-user DTO。

### 5.3 Stable HTTP errors

Envelope 复用 closed `code/message/details?`。`details` 只放 bounded identifiers/current version，
不得回显 secret/path/raw payload。

| HTTP | Stable code | Boundary |
| --- | --- | --- |
| `401` | `AUTHENTICATION_REQUIRED` | 当前 session 缺失、失效或过期 |
| `403` | `SCOPE_FORBIDDEN` | 已允许披露对象但 permission/exact owner scope 不足 |
| `404` | `RESOURCE_NOT_FOUND` | Workspace/Preview/Attempt/Submission/Operation/mapping/baseline 缺失或按 policy 隐藏 |
| `409` | `IDEMPOTENCY_CONFLICT` | same Workspace/key but different effective fingerprint |
| `409` | `WORKSPACE_VERSION_CONFLICT` | expected Workspace version 过期 |
| `409` | `PREVIEW_BINDING_CONFLICT` | revision/generation/current-preview binding 不匹配 |
| `409` | `PREVIEW_DERIVED_STALE` | current Baseline 与 immutable Preview binding 不同 |
| `409` | `BASELINE_VERSION_CONFLICT` | expected node/head version 与 fresh Head 不同 |
| `409` | `SUBMIT_OCCUPANCY_CONFLICT` | Workspace active Attempt/Submission 或 Repository scope 已占用 |
| `409` | `NO_CANONICAL_CHANGE` | Preview canonical digest 与 current business base 相同；零写入 |
| `422` | `REQUEST_VALIDATION_FAILED` | header/closed DTO/type/range/options 校验失败 |
| `429` | `ADMISSION_LIMIT_REACHED` | Backend new-work gate 拒绝 |
| `503` | `ARTIFACT_UNAVAILABLE` | required immutable artifact/closure 不可读或 binding 不完整 |
| `503` | `DEPENDENCY_UNAVAILABLE` | mapping/Repository resolve 暂时失败 |
| `503` | `SERVICE_NOT_READY` | admission closed、registry/schema/readiness 未闭合 |

Repository import terminal code 和 Operation attention/diagnostic 属异步 read 结果，不伪装成
AcceptSubmit HTTP 失败。`SUPERSEDED` 只复用既有 Operation status（例如 upstream Preview）；它不
增加第五种 Attempt state。

### 5.4 Internal operator recovery HTTP

本endpoint只操作`job_kind=backend-vnext/submit`，是P5对P4既有in-process
`AuthorizedOperatorRecovery`的最小HTTP接线，不建立新command、principal、permission registry或
recovery protocol：

```text
POST /internal/v1/operations/{operation_id}/steps/{step_id}/recovery
Authorization: Bearer <existing deployment internal bearer>
Content-Type: application/json
```

Inbound认证复用Backend已从只读secret file加载、用于可信内网service通信的同一个global internal
bearer；不使用终端用户session，不接受body token，也没有per-Repository ACL。Route只在deployment
internal network开放。缺失、空或错误bearer统一401，比较与日志遵守现有secret redaction；这不是
新security principal。

Request/response均为closed DTO：

```text
OperatorRecoveryRequest
  operation_id
  step_id
  command: RESUME_RECONCILE | RETRY_FROM_CHECKPOINT | ABORT_CONFIRMED_FAILURE
  expected_operation_optimistic_version: non-negative I-JSON safe integer
  expected_step_optimistic_version: non-negative I-JSON safe integer
  reason: bounded non-empty string

OperatorRecoveryResponse
  operation_id
  step_id
  command
  disposition: APPLY | IDEMPOTENT
```

Body `operation_id`/`step_id`必须分别等于path值；Step必须属于Operation，Operation必须通过business
ref绑定一个SubmitAttempt，registry中的`(job_kind, step_name)`必须与stored Step一致。HTTP adapter
先执行这些closure checks，再把exact fields映射到P4 `OperatorRecoveryRequest`；不得绕过
`authorize_operator_command`或直接写Operation/Step。

Success与replay：guarded CAS apply返回`200/APPLY`。`ABORT_CONFIRMED_FAILURE`已经把P4 records和
business Attempt收口后，caller以重新读取的current expected versions重放，返回
`200/IDEMPOTENT`；不增加admin idempotency ledger。`RESUME_RECONCILE`或
`RETRY_FROM_CHECKPOINT`成功后已离开MANUAL source，旧请求或重复请求返回409，不把第二次执行伪装
成replay。

| HTTP | Stable code | Boundary |
| --- | --- | --- |
| `401` | `AUTHENTICATION_REQUIRED` | internal bearer缺失或不匹配 |
| `404` | `RECOVERY_TARGET_NOT_FOUND` | Operation/Step/SubmitAttempt不存在 |
| `409` | `RECOVERY_IDENTITY_CONFLICT` | path/body不等、Step不属于Operation或非Submit job |
| `409` | `OPERATION_VERSION_CONFLICT` | Operation expected optimistic version过期 |
| `409` | `STEP_VERSION_CONFLICT` | Step expected optimistic version过期 |
| `409` | `RECOVERY_STATE_CONFLICT` | P4 source status不允许command或non-abort terminal replay |
| `409` | `RECOVERY_CAPABILITY_CONFLICT` | command与sealed P4 capability guard不匹配 |
| `409` | `ABORT_PROOF_NOT_SATISFIED` | 缺少matching Repository普通未发布stable failure |
| `422` | `REQUEST_VALIDATION_FAILED` | closed DTO、enum、version range或reason预算失败 |
| `503` | `SERVICE_NOT_READY` | registry/control DB/admin recovery composition未ready |
| `503` | `DEPENDENCY_UNAVAILABLE` | abort proof所需Repository evidence暂不可验证 |

Error/details和response不得暴露internal bearer、lease token、checkpoint、request/package bytes、host
path或private ref。HTTP/auth/capability rejection的唯一test owner由execution plan §4冻结；command
到business terminal/occupancy的integration owner仍是Submit recovery tests。

## 6. AcceptSubmit ordering, idempotency and T1

### 6.1 Pre-transaction ordering

禁止在 SQLite transaction 内执行 session file、artifact 或 Repository network I/O。顺序固定：

1. 解析 closed body、path 和 `Idempotency-Key`，通过 new-work admission。
2. 从当前 session取得IdentityContext并检查`upload_submit_workspace`。
3. 读取 Workspace、immutable referenced Preview/Upload 与现有 submit idempotency row；先做 exact
   scope re-authorization。若 key 已存在，使用既有 Attempt 冻结的 server facts重建 effective
   fingerprint：same/same直接返回当前 Attempt response，same/different返回409；replay不重新
   resolve `main`，也不受后来 Workspace/Head version变化影响。
4. 对新 key解析唯一 active mapping/BaselineHead，检查 caller body binding、derived-stale、
   canonical digest与current business base。`NO_CANONICAL_CHANGE`在此返回且不写 idempotency row。
   **Current business-base canonical digest** 定义为：对 `baseline_head.business_baseline_commit_id`
   materialize 后，按 bound `UploadRevision.input_completeness` 与 `PreviewResult.ruleset_version`，
   使用与 preview assemble **相同**的 bundle profile/inputs/pairs 拓扑重跑 comparison+bundle
   assembly；comparison 各侧均使用 baseline 快照（identity/no-change 路径）。比较两侧均为
   `bundle_digest` 字符串；相等 ⇒ `409 NO_CANONICAL_CHANGE`。`BaselineCanonicalDigestPort` 必须接收
   `input_completeness` 与 `ruleset_version` 以保证与 preview canonical digest 同构；bound
   `PreviewResult.ruleset_version` 必须等于本进程实现的 table-rules `RULESET_VERSION`（当前
   `"v2"`，由 `build_preview_job_payload` 发出），否则 fail-closed 并返回 `503
   SERVICE_NOT_READY`（非 `DEPENDENCY_UNAVAILABLE`）。注：submit job payload 的
   `ruleset_version` 是独立契约字段（当前 `"v1"`），与 preview 同名不同义；升级后 bound preview
   `ruleset_version != RULESET_VERSION` 的 workspace 须重新 preview 后方可 accept。
   MULTI_PAIR bundle 组装时，跨 pair 出现相同 `source_ref` 的比较/risk/projection 等产物提升为
   `shared/…`（与 snapshot table 共享规则同构），因此 FULL identity/no-change 路径与 preview 均可
   成功组装。`NO_CANONICAL_CHANGE` 主要覆盖 source 不同但 canonical business content 相同的 no-op
   场景（如 `DROP_FROM_STORAGE`）。
5. 在 Preview pin仍有效时 verify required source/snapshot/READY closure exact可读。
6. 通过 Repository Client执行`ResolveVersionedRef(repository_id, main)`；失败返回503且不进入T1。
7. 打开T1 `BEGIN IMMEDIATE`短事务，按§6.3重新读并裁决所有可变business facts。步骤6返回的
   CommitId仅成为`repository_expected_commit_id`；T1后Repository main drift由T2 mandatory CAS
   稳定拒绝，不通过长事务或跨库锁消除。

新 key 的 preflight 与 T1 使用同一 control DB projection 解释 active mapping/BaselineHead。
Server-owned provisioning JSON 是该 projection 的输入；运行时变更以 projection 更新事务提交
为生效点。文件改写本身不承诺即时生效。T1 同连接的 SQLite 读取不属于本节禁止的外部 I/O。

### 6.2 Effective request fingerprint

`accept_request_fingerprint` 使用 JCS object + domain separator
`gateway-vnext:accept-submit-request:v1\0` + SHA-256。输入至少包括：path Workspace、当前
actor/device/project/Repository、body全部字段、immutable Preview/Upload/generation、Baseline
node/commit/head version、canonical business digest、source/snapshot/closure digests、resolved
Repository expected commit、四项固定 policy、Submit job contract version 和 closed options。

Same-key replay用既有Attempt中的server-owned部分与incoming caller-owned部分比较，不拿当前main/
Head覆盖原值。新的key即使body相同也是新动作，但 occupancy/current-binding rules仍会裁决。

### 6.3 T1 in-transaction validation order

1. 再查 `(workspace_id, accept_idempotency_key)`。若已存在，返回 replay 前必须用当前 T1 UoW
   的同一 SQLite 连接，按 caller device/project exact key 读取当前 mapping，并结合
   Workspace/Attempt 的 scope 检查 mapping 存在且 enabled、exact scope 与当前 Repository
   visibility。禁用或换仓不能沿用 preflight 的 resolved_repository_id 通过授权。授权通过后，
   再以既有 Attempt 冻结的 server facts 重建 effective fingerprint，same/same 返回 replay，
   same/different 返回既有 conflict。当前 Head 的 node/commit/version 不覆盖 Attempt 的冻结值，
   也不触发新 key 的 Head CAS；当前授权与冻结 fingerprint 必须分开处理。不为该分支重新调用
   baseline digest/main resolve，亦不再写入新 Attempt。处理被并发 winner 插入的 same/same 或
   conflict。
2. 使用当前 T1 UoW 的同一 SQLite 连接，按 caller 的 device/project exact key
   transaction-fresh 读取 provisioned active mapping/BaselineHead，以及 Workspace、
   UploadRevision、PreviewResult。不得调用会新开连接/UoW 或读取 session/mapping 文件的 adapter。
3. 对新 key，当前 mapping 必须存在、enabled，且其 Repository 与 frozen scope/Workspace 一致；
   校验 exact frozen scope/Repository、Workspace OPEN、expected optimistic version、current
   upload/preview pointers、generation 与 caller binding。当前 BaselineHead 必须满足 caller
   expected node/version，并与 preflight Head 及 immutable Preview 的 baseline binding 三字段
   完整一致：business_baseline_node_id、business_baseline_commit_id、baseline_head_version。
   Caller body 不新增 expected commit 字段；commit 由 server-owned Head/Preview facts 比较。
   Preview 必须非 derived-stale；仅在完整 equality 通过后，使用绑定该 Head 的 preflight
   canonical digest 执行 `NO_CANONICAL_CHANGE` guard。包括 commit-only 在内的 Head 漂移均先
   拒绝，不混用 fresh Head 与旧 digest，不在事务内重新获取 canonical digest，也不能仅复用
   现有 node/version guards 代替完整比较。Same-key replay 仍按既有冻结 fingerprint/Attempt
   facts 比较，不施加新 key 的当前 Head CAS；当前 session/exact scope/Repository 可见性重新
   授权仍适用，不能借 replay 绕过 mapping 禁用。
4. 校验 Workspace 没有 Attempt/Submission occupancy，Repository occupancy row 不存在；unique
   constraints是并发线性化点。
5. 校验artifact protection intents仍由current Preview持有，所有refs/digests等于preflight结果。
6. 校验Submit三步JobDefinition/decoder/handler/version registry snapshot ready。
7. 写入全部T1 facts；任一constraint/CAS失败回滚整个前缀。

### 6.4 T1 single-transaction matrix

| Participant | Atomic success mutation | Failure/replay rule |
| --- | --- | --- |
| SubmitAttempt | insert PREPARED with frozen bindings/policies/three keys/version 0 | no partial row；same/same returns winner |
| Submit idempotency | insert `(workspace_id, accept_key) -> fingerprint/attempt_id` | unique conflict reroutes to replay comparison |
| Operation/Step | insert QUEUED Operation + first `prepare_import` PENDING Step and immutable job payload | no Attempt without Operation/Step |
| Workspace | increment optimistic version | expected version CAS |
| Workspace occupancy | insert active Attempt pointer | unique workspace and xor constraint |
| Repository occupancy | insert repository/baseline owner Attempt | RepositoryId primary key/Attempt unique |
| Artifact protection | add Attempt intents then remove current Preview intents for exact snapshot refs | set equality/digest check；no unprotected window |

T1不创建Submission、RepositoryArtifactRef、Repository request/operation、BaselineNode、outbox或
integration event。SQLite schema采用现有component ledger的additive Workspace schema v3；若实现
开始时current schema不再是v2，先重新审计migration，不沿用版本号猜测。

## 7. RepositoryImportArtifact builder and nominal refs

Builder是5B application adapter，消费 Preview-bound SnapshotTableArtifact 和现有 Storage
Projection/Mutation Planner public contracts；它不重新解析SQL、不把comparison records当mutation
source。固定输入`builder_mutation_policy=REBUILD_ALWAYS`，变化表产生owner定义的full rebuild，
不启用`ADAPTIVE_PATCH`。全局canonical no-op已在Attempt前拒绝。

每个Attempt只允许一个durably published package identity。`prepare_import`可在checkpoint发布前从
pinned inputs重算；crash留下的未引用bytes是C类orphan。checkpoint一旦存在，retry/takeover只能
read-back并复用同一BackendArtifactRef/raw SHA，不能重建、覆盖或选择另一个package。

发布顺序：build deterministic replay + CanonicalizationManifest → durable保存完整manifest并校验
digest → build正式v1 tar+zstd package → ArtifactStore put/read-back → 一个CAS checkpoint同时记录
manifest ref/digest、BackendArtifactRef和raw SHA。Package shape/media type只引用
[Canonical Storage §6.1](../contracts/canonical-storage-and-repository-boundary.md)；本文不复制。

```text
BackendArtifactRef        Backend ArtifactStore scope；可定位本地immutable bytes
RepositoryArtifactRef     RepositoryId scope；Repository upload response分配的新ArtifactId
```

两者字段相似但必须是不同nominal class/port type；禁止继承、type alias、直接复制artifact_id或把
Backend locator序列化进Repository DTO。唯一conversion boundary是UploadArtifact：stream Backend
bytes + exact media/size/raw SHA，接收新的RepositoryArtifactRef，再核对response三项metadata后
checkpoint。BackendArtifactRef不能出现在SubmitVersionedImport body。

## 8. Submit JobDefinition and versioned documents

### 8.1 Fixed topology and registry

```text
job_kind: backend-vnext/submit
job_contract_version: backend-vnext/submit/v1

prepare_import -> submit_import -> await_import_result
```

| Step | decoder identity | handler identity | publication | recovery capability |
| --- | --- | --- | --- | --- |
| `prepare_import` | `backend-vnext/submit/prepare-import/decoder/v1` | `backend-vnext/submit/prepare-import/handler/v1` | `SINGLE_SUCCESSOR` | `PURE_RECOMPUTE` before durable checkpoint, then reuse |
| `submit_import` | `backend-vnext/submit/submit-import/decoder/v1` | `backend-vnext/submit/submit-import/handler/v1` | `SINGLE_SUCCESSOR` | `EXTERNAL_EFFECT` |
| `await_import_result` | `backend-vnext/submit/await-import-result/decoder/v1` | `backend-vnext/submit/await-import-result/handler/v1` | `TERMINAL` | `EXTERNAL_EFFECT` reconcile/readback |

Registry必须同时包含Preview与Submit definitions、全部decoder/handler exact identity。unknown pair、
duplicate identity、unsupported version、HTTP acceptance registry与worker registry不一致均在startup/
claim fail closed。没有dynamic DAG、per-table Step或第二registry。

### 8.2 Closed Submit payload

Operation Runtime envelope/version/budget沿用P4。5B inline payload是closed object；超过64 KiB使用
既有`job_payload_ref`，不提高runtime limit：

```text
document_type: submit_job_payload
contract_version: backend-vnext/submit/v1
submit_attempt_id
workspace_id
generation
upload_revision_id
preview_result_id
repository_id
business_baseline_node_id
business_baseline_commit_id
baseline_head_version
repository_expected_commit_id
canonical_business_digest
source_artifact_refs[]
preview_ready_closure_ref
snapshot_table_set_digest
ruleset_version
storage_projection_version
canonicalization_manifest_contract_version
repository_import_package_version: 1
accept_request_fingerprint
repository_upload_idempotency_key
repository_import_idempotency_key
repository_policy:
  target_ref: main
  verification_policy: STRUCTURAL
  unknown_type_policy: REJECT
builder_mutation_policy: REBUILD_ALWAYS
options: {}
```

Decoder要求exact key set、T1 Attempt equality、ref uniqueness、policy constants与version support；
各表SnapshotTableArtifact refs由Attempt和`preview_ready_closure_ref`加载，并以
`snapshot_table_set_digest`闭合，不复制进受64-ref预算约束的Operation payload。Payload不是第二个
business owner，Attempt是transaction-fresh source of truth。

### 8.3 Job-specific checkpoint schemas

每份job state都装入P4 `StepCheckpointEnvelope`，使用JCS、exact key set、predecessor binding和现有
artifact ref预算：

| Step | schema version | Closed job-state fields |
| --- | --- | --- |
| prepare | `backend-vnext/submit/prepare-import-checkpoint/v1` | attempt_id、manifest_ref/digest、backend_import_artifact_ref、package raw size/SHA、builder policy、input closure digest |
| submit | `backend-vnext/submit/submit-import-checkpoint/v1` | prepare checkpoint ref、RepositoryArtifactRef、upload key、closed import request bytes ref/digest、request fingerprint、import key、`request_sent`、repository_operation_id? |
| await | `backend-vnext/submit/await-import-result-checkpoint/v1` | submit checkpoint ref、repository_operation_id、last observed Repository status、matching terminal result/evidence ref?、reconcile_started_at? |

`request_sent=true`与non-null Repository operation ID在同一checkpoint CAS出现；此前
`request_sent=false`只表示operation identity尚未durable捕获，不证明网络没有收到请求。Terminal
Repository result原文以bounded closed evidence document/ref保存，T3从该document解码，不从log或
diagnostic字符串推断。

## 9. T2 Repository wire and effect crossing

### 9.1 Exact upload/import mapping

Repository upload先使用`repository_upload_idempotency_key`、Backend bytes、media type、size和raw
SHA。response loss只允许exact same-key/same-bytes replay并接受原RepositoryArtifactRef。

正式import调用固定为：

```http
POST /v1/repositories/{repository_id}/versioned/imports
Idempotency-Key: <T1 frozen repository_import_idempotency_key>
Content-Type: application/json
```

Closed JSON body恰为正式`SubmitVersionedImportRequest`：

```text
repository_id
artifact_ref
target_ref: main
expected_commit_id
verification_policy: STRUCTURAL
unknown_type_policy: REJECT
```

`body.repository_id == path repository_id == T1 repository_id`是调用前和Repository route的双重
validation。`Idempotency-Key`只在header；`builder_mutation_policy=REBUILD_ALWAYS`只属于Builder，
二者都不进入JSON body。不得扩展request/result DTO。

### 9.2 Crossing and recovery identity

1. `prepare_import` checkpoint已durable且readable。
2. `submit_import`以原upload key取得/恢复RepositoryArtifactRef并checkpoint。
3. 组装并closed-validate exact import body；持久body ref/digest、fingerprint、import key；同一control
   transaction把Attempt PREPARED→EFFECT_PENDING。此时business occupancy保持。
4. lease/cancel检查通过后发送import。202返回的RepositoryOperationId与`request_sent=true`一起CAS
   checkpoint；然后才发布`await_import_result` successor。
5. 若请求发送后response loss且ID未durable，只允许以exact same body/header/key进行identity-preserving
   transport replay来取回Service原OperationId；这不是新业务Attempt。ID一旦durable，所有路径只
   `GET /v1/repositories/{repository_id}/operations/{operation_id}` poll/reconcile。

业务worker禁止新key、新package、不同request fingerprint、直接查Dolt、猜marker/commit/ref或在
Repository超时后自行重放effect。Repository startup按owning contract以marker/private ref/main/
artifact evidence恢复；Backend只消费Repository-scoped Operation终态。

## 10. T3 finalize and stable abort

### 10.1 Matching-result closure

`await_import_result`只有在Repository Operation path scope、ID和T1 checkpoint一致时消费结果。
SUCCEEDED result还必须逐项匹配：Repository artifact ID、canonicalization manifest digest、expected
commit/parent、literal `main`、requested/completed `STRUCTURAL`、unknown type `REJECT`。Submission
owner另核对canonical business digest、source binding、package raw SHA、manifest ref/digest和
Preview/Attempt identity；Repository structural verification不替代这些facts。

### 10.2 T3 single transaction

| Participant | Finalize mutation | CAS/invariant |
| --- | --- | --- |
| Submission | insert exactly one immutable row | unique submit_attempt_id；matching closure |
| SubmitAttempt | EFFECT_PENDING→FINALIZED，set submission/time/version | operation/result identity and expected version |
| Workspace | increment version；Attempt pointer→Submission pointer | current active Attempt must match |
| Repository occupancy | delete owner row | owner Attempt、repository、baseline exact match |
| Artifact protection | clear Attempt snapshot/package pins；promote SourcePackage + manifest durable intent | exact owner/ref set；no authority gap |
| Operation/await Step | terminal SUCCEEDED + completion/closure | current lease token、Step/Operation expected versions |

Finalize replay先按unique attempt读取既有Submission。若Submission、Attempt、Workspace和Operation已
形成matching T3 closure，返回既有结果并ack；不得生成第二个Submission或重新release。由于全部
参与者同一SQLite UoW，任何非完整前缀是integrity/recovery finding，不以补写新Submission掩盖。

### 10.3 Abort

自动ABORT只接受原Repository operation identity的普通未发布stable FAILED：
`IMPORT_REJECTED`、`EXPECTED_COMMIT_MISMATCH`、
`VERIFICATION_FAILED_NOT_PUBLISHED`。一个事务完成Attempt→ABORTED、abort code/time、Workspace
Attempt pointer删除、Repository occupancy删除、Attempt pin清除和Operation/Step FAILED；不创建
Submission。

Pre-request deterministic failure、artifact丢失、`request_sent=false`、P4 `PRE_REQUEST`分类或矛盾
evidence都不是`NOT_PUBLISHED`证明，也不扩充ABORT集合；它们保留occupancy并进入retry或
`MANUAL_RECOVERY_REQUIRED`。Response loss/RepositoryOperationId尚未捕获时必须以原body/header/key
取回matching operation identity并reconcile，不能abort。

`ABORT_CONFIRMED_FAILURE`只有在已持久的RepositoryOperationId及其matching FAILED result属于上述
三个普通未发布stable code时，才允许释放business occupancy。Operator apply先通过P4既有guarded
CAS把Operation/Step收口；5B随后以matching evidence执行幂等business abort transaction。两者之间
crash只会留下FAILED Operation + 仍被占用的Attempt，startup/replay继续后半段，绝不提前释放。
该command不能force-success、移动main或编辑record。

## 11. Failure, crash and takeover matrix

| Scenario | Required behavior |
| --- | --- |
| crash before prepare checkpoint | 从pinned T1 input重算；未引用bytes按TTL清理 |
| crash after prepare checkpoint | 复用同一BackendArtifactRef/raw SHA，不重建 |
| upload response loss | same upload key/bytes replay，取得原RepositoryArtifactRef |
| import response loss before operation ID checkpoint | same closed body/header/import key identity replay；不得新key/package |
| worker crash/lease expiry after operation ID | takeover只poll原Repository operation；Attempt保持EFFECT_PENDING |
| duplicate delivery | JobDefinition/Step CAS和Attempt version fence；最多一个effect identity和Submission |
| late writer after lease loss | Repository request可由Service幂等；business checkpoint/T3 CAS拒绝旧lease publication |
| Repository restart | Service先按owning startup recovery收口；worker只poll终态 |
| poll/reconcile timeout | 不是Repository failure；bounded retry后Operation attention，occupancy保留 |
| `MANUAL_RECOVERY_REQUIRED` | Attempt保持EFFECT_PENDING；artifact/Workspace/Repository occupancy保护；operator处理 |
| matching ordinary not-published failure | stable abort transaction；可用新Accept key开始未来新Attempt |
| valid SUCCEEDED but T3 transient DB failure | 原evidence重试T3，不重复Repository effect |
| T3 commit后worker response loss | `after_business_finalize_commit_before_worker_ack`；replay返回既有Submission |
| state/result/ref矛盾 | fail closed为`SUBMIT_RESULT_BINDING_MISMATCH`/`FINALIZE_RECOVERY_REQUIRED`，不释放占用 |

异步stable business diagnostics至少为：`REPOSITORY_OUTCOME_UNKNOWN`、
`SUBMIT_RESULT_BINDING_MISMATCH`、`FINALIZE_RECOVERY_REQUIRED`、`ARTIFACT_UNAVAILABLE`；Repository
四个public import code保持原样。Operation `MANUAL_RECOVERY_REQUIRED`是attention state，不等于
Attempt ABORTED。

Operator command/capability映射固定为sealed P4 matrix：

| Submit Step | Recovery capability | Allowed resume command | Required behavior |
| --- | --- | --- | --- |
| `prepare_import` | `PURE_RECOMPUTE` | `RETRY_FROM_CHECKPOINT` | 从既有input/checkpoint继续；若package identity已发布只复用 |
| `submit_import` | `EXTERNAL_EFFECT` | `RESUME_RECONCILE` | 原upload/import keys、body、package和Repository identity |
| `await_import_result` | `EXTERNAL_EFFECT` | `RESUME_RECONCILE` | 只poll/reconcile原RepositoryOperationId并继续T3 |

`RETRY_FROM_CHECKPOINT`用于两个external Step或`RESUME_RECONCILE`用于`prepare_import`均fail closed为
`RECOVERY_CAPABILITY_CONFLICT`；不得修改P4 guard。`ABORT_CONFIRMED_FAILURE`在P4对任意capability可用，
但5B额外施加§10.3 matching Repository stable-failure business proof guard。全部command要求Operation/
Step expected versions和bounded reason，并写既有recovery audit；没有arbitrary edit/force success/
blind replay。

## 12. Current-session re-authorization

每次读取Operation、Attempt、Submission都重新：解析current session/expiry → 检查
`workspace_read` → 读取business ref及其冻结actor/device/project/repository → 解析当前mapping →
校验exact device/project和Repository visibility。对象不存在或policy隐藏返回404；对象可披露但
permission不足返回403。不得把接受时permissions、Repository bearer或Operation business_refs当
长期读票据。

Operation read必须先解析其submit Attempt business ref再执行相同检查；不能仅凭OperationId读取。
必要artifact/bundle/commit content read在真正打开stream前再次执行同一授权。session失效或gateway
disabled不取消已接受worker effect，但阻止新Accept和所有未授权read。

## 13. Runtime, readiness, shutdown and containers

### 13.1 Settings and composition

复用现有Backend/worker settings owner：absolute control DB/artifact root、Repository base URL、
secret-file bearer、bounded request timeout、session/mapping file。5B新增的语义配置只允许是bounded
Repository poll/reconcile/admission参数；P4的60s reconcile session、lease/backoff/drain contract不
由5B改变。target/policy/mutation mode不是setting，固定在job contract。

Backend与worker必须从同一composition factory获得Submit definitions/decoders/handler identity；
HTTP T1使用同一immutable registry snapshot做preflight。Repository client不得记录bearer、body、
source SQL、path或checkpoint payload。

HTTP/worker bootstrap 的 provisioning 输入按既有 seed 事务写入运行时 projection；文件更新
不意味着自动 hot reload。每次已授权 seed 提交是一次 provisioning 应用。本文不新增 reload
writer、不改变 seed/upsert 生命周期；若要禁止旧 seed 覆盖、支持热更新或多 writer generation，
应另行修订对应 provisioning owner contract，不由 D-1 隐式实现。

### 13.2 Readiness and shutdown

Backend开放new-work前检查：settings、control DB migration/integrity、artifact root、Preview+Submit
registry、Repository client `/readyz` connectivity。Worker先load/reconcile durable Submit Operation、
校验registry/checkpoint decoder并发布worker-ready。Manual-recovery Attempt可使相关scope blocked但不
伪造全局成功；deployment只有Backend、worker、Repository Service三者healthy/ready才宣称完整
Submit journey ready。

Shutdown顺序：HTTP readiness=false →关闭会创建Upload/Preview/Submit的新admission →允许既有
read → worker停止claim新Step并drain/checkpoint → quiescence后退出。effect已cross时不能因shutdown
cancel；超时遵守Operation Lifecycle `DRAINING_TIMEOUT`，不由5B自动强杀。

### 13.3 Container applicability

未来实现会触碰route、migration、worker production registry、Repository write client、settings/
readiness、artifact volume和Compose journey，因此最终candidate必须在current HEAD重建Backend、
worker、Repository Service镜像，记录source-tree/image provenance，并运行三者conjunction、真实
upload/import/restart/response-loss smoke。祖先5A/P4镜像仅为historical evidence，不能代表5B HEAD。

## 14. Deferred, exclusions and reopen

Deferred：Review/Archive/History DTO与Workspace Submission释放；production capacity数字和poll
tuning；legacy persistence/Dolt cutover；外部event consumer；HA/multi-worker/external DB；public
Repository repair/backup；temporary package TTL调优。它们不阻塞当前单host V1 design。

明确排除：outbox、generic FailureDescriptor/evidence journal、dynamic DAG、per-table durable Step、
new UID/helper/service、custom IPC、sidecar/quarantine/tombstone、blind replay、caller-selectable
Repository policy、Backend挂载Repository volume或运行Dolt。

出现以下任一项必须停止并reopen owning contract/ADR，不能作为finding-scoped实现修复：

- T1/T2/T3边界、四态含义或稳定abort集合需要改变；
- Repository path/body/header、required fields、policy或result需要改变；
- P4 lease/claim/checkpoint envelope/status/recovery protocol不能承载本设计；
- artifact长期authority或Backend/Repository nominal ref边界需要改变；
- 需要outbox、跨库transaction、second writer、broker、HA、external DB或新security principal；
- `REBUILD_ALWAYS`不能生成该Submit的正式package，或需要dynamic target/policy；
- SQLite不能原子提交T1 pin+Attempt+Operation+occupancy或T3 Submission+occupancy+Operation；
- P4-R6结论改变任何上述依赖，或实现开始时authority/current schema已漂移。

## 15. Candidate acceptance checklist

- owner/field/state/occupancy mapping完整且没有第二semantic owner；
- HTTP route、closed DTO、permission、status/stable error表冻结；
- T1 order、main resolve、idempotency、CAS、pin transfer和single transaction闭合；
- builder、REBUILD_ALWAYS、Backend/Repository ref nominal boundary闭合；
- SubmitVersionedImport exact path/body/header与Repository contract一致；
- job topology、payload/decoder/checkpoint versions和recovery capability闭合；
- T2 crossing/poll/reconcile/no-blind-replay与T3 exactly-one/replay/abort闭合；
- crash/takeover/restart/response-loss/manual recovery/operator路径可测；
- every-read re-authorization和runtime/container applicability闭合；
- deferred/reopen/forbidden mechanisms明确；
- 独立docs reviewer确认无contract drift后，candidate才可标记design accepted；仍不自动授权实现。

## 16. S0 finding-scoped remediation record

```yaml
input_review: p5-5b-s0-independent-docs-review.md
input_decision: changes_required
findings_addressed:
  S0-F1: PRE_REQUEST_removed_as_abort_proof
  S0-F2: internal_operator_recovery_http_frozen
  S0-F3: sealed_p4_capability_matrix_applied_per_step
owning_contract_reopen: not_required
candidate_status: candidate_draft_pending_new_independent_review
implementation_authority_changed: false
```

S0-F1选择保持现有owning contract；没有新增pre-effect abort authority。S0-F2的endpoint仅接线既有
P4 port和existing internal bearer。S0-F3不修改P4 capability guard。下一步仍是新的独立context复审，
不是implementation。

## 后续维护约束（2026-09-19）

本 Slice 已交付部分的后续维护与跨 Slice 复用遵守 [P5 架构纠偏与阶段收口](p5-business-vertical-slices-design.md#p5-architecture-guardrails)。
该补充约束后续增量，不追溯改写本文件历史 gate、实现授权或已通过的 slice exit。
既有 port/wire、私有模块调用、编排职责与依赖环问题按总体设计 §2A 的 owner/时机收口；
后续消费者不得复制这些例外。当前请求/结果、digest、checkpoint 与幂等恢复语义继续由
原 owning contract 定义，不能以边界整理为由静默改变。

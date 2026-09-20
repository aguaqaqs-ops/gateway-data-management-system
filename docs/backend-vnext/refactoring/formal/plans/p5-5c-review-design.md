# P5-5C Review Detailed Design

状态：**DESIGN ACCEPTED — IMPLEMENTATION AUTHORIZED (P5-5C-S1)**

日期：2026-09-19

Owner：Submission Domain + Review Application + HTTP Interface

入口授权：[P5-5C-S0 Entry Brief](p5-5c-s0-entry-brief.md)

上游：[P5-5B-S8 Independent Slice Exit Acceptance](p5-5b-s8-independent-acceptance.md)、
[P5 Business Vertical Slices Design Baseline](p5-business-vertical-slices-design.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[ADR 0002](../adr/0002-minimal-persisted-business-state.md)、
[Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)

执行计划：[P5-5C Review Execution Plan](p5-5c-review-execution-plan.md)

## 1. Decision summary

```yaml
design_kind: p5_5c_review
design_authority: accepted
authority_base_sha: a7ed4090bd1e182a77aff074ac9573692cfce9d6
implementation_head: 0e9c131b6c90bd7f32c8cac886896740bbb99215
implementation_candidate_head: 82f353de7687607370a76cfb40d42717214f3ba7
p5_5b_slice_exit: pass
p5_5c_design: accepted
p5_5c_design_status: accepted
p5_5c_implementation_authorized: yes
first_authorized_step: P5-5C-S1
repository_effect: forbidden
operation_runtime: not_used
worker: not_used
transaction_model: one_local_sqlite_write_transaction
review_permission: review_submission
```

P5-5C 将 Review 实现为 Submission Domain 拥有的 immutable events + current projection。所有 command
都是同步、短、单 SQLite 事务；成功响应表示权威业务事实已经提交。Review 不创建单独 aggregate
workflow、不调用 Repository、不创建 Operation，也不将 Archive 或 History projection 持久化进
Review。

## 2. Owner and dependency boundary

```text
HTTP route / closed DTO / current-session auth
  -> Review Application command/query
       -> Submission Domain transition policy
       -> Review repository port
       -> Workspace repository port
       -> provisioned scope read port
  -> one ControlDbUnitOfWork

SQLite adapters
  -> immutable event + current projection + idempotency
  -> existing Submission + Workspace + occupancy records
```

Owner rules：

- Submission Domain owns ReviewStatus、ReviewEvent、ReviewProjection 和 transition policy；
- Review Application owns authorization、command acceptance、idempotency fingerprint 和跨
  Review/Workspace 的短事务；
- Workspace Domain retains Workspace state/pointer/version semantics；
- Archive Application later derives CandidateProjection and atomically consumes occupancy；
- History Application later reads Review facts to derive HistoryTreeProjection；
- HTTP owns wire spelling only；SQLite adapter owns schema/row mapping only。

Domain 不依赖 FastAPI、Pydantic、sqlite3、Operation、Repository Client、artifact store 或 Archive
model。HTTP handler 不直接执行 SQL 或推进 domain state。

### 2.1 P5 增量架构约束

本 Slice 遵守 [P5 架构纠偏与阶段收口](p5-business-vertical-slices-design.md#p5-architecture-guardrails)。Review 继续是 Application 协调的本地短事务；
不为 Review 新建 capability、worker job 或 Rust provider。Domain 只保留 Review 事实与转换规则；
HTTP DTO、application command/result 和 SQLite record 由各自 owner 映射。

组合 `WorkspaceControlUnitOfWorkFactory` 仅在接线处表达同一个事务实现可服务多个用例；
Review 内部依赖所需的最小 port，不因共享 UoW 获得调用 Submit job/Repository wire 的职责。
S2 的 finalize seed 在既有本地事务内复用 Review owner 的最小入口，seed/helper 不反向依赖
`submit_jobs`，Review transaction 也不导入 Preview/Submit 编排模块或 capability 私有实现。
修改 finalize seam 不要求立即清理全部 Submit 历史问题，但不得增加相同反向依赖。
Review 新增的 ref/record 映射留在 Application/adapter，不让 Artifacts 反向依赖 Review/Submission。
公共 contract 可包含纯 codec/validator，执行和 I/O 留在用例或 adapter；不新增包根胶水。

5D/5E 通过稳定 Review facts/read port 消费审核状态，不直接复用 SQLite record 或改写 Review
entity。当前已接受的字段、状态机、权限、事务与幂等语义保持不变。

## 3. Domain model

### 3.1 Status and event kind

```text
ReviewStatus
  PENDING
  APPROVED
  REJECTED
  RETURNED_FOR_REVISION
  WITHDRAWN

ReviewEventKind
  SUBMISSION_FINALIZED
  APPROVED
  REJECTED
  RETURNED_FOR_REVISION
  WITHDRAWN
```

`SUBMISSION_FINALIZED` 只由 Submission finalize/backfill 产生，不能由 HTTP caller 请求。它将
projection 初始化为 `PENDING`，sequence `0`，optimistic version `0`。其他 event 每次只推进一次
projection；不允许 status 与 latest event 的 `to_status` 分叉。

### 3.2 Immutable ReviewEvent

语义字段：

```text
ReviewEvent
  submission_id
  sequence                    # per Submission, starts at 0
  event_kind
  from_status optional        # seed only is null
  to_status
  reason optional
  actor_id
  occurred_at                 # one transaction UTC sample
```

`reason` 是 bounded plain text audit context，不是 permission、workflow instruction 或 external
notification payload。它的 wire/domain/persistence contract 统一冻结为：

- `null` 表示未提供；非 `null` 值按收到的 Unicode scalar sequence 原样保存，不 trim、不做
  NFC/NFKC 或大小写转换；校验、fingerprint、event response 使用同一原值；
- UTF-8 编码长度 `1..4096` bytes（与现有 bounded diagnostic size 一致）；拒绝 U+0000–U+001F、
  U+007F–U+009F、surrogate U+D800–U+DFFF 和 Unicode noncharacter；
- `REJECT` / `RETURN_FOR_REVISION` 的 reason 还必须至少包含一个非 Unicode whitespace scalar；
  `APPROVE` / `WITHDRAW` 可为 `null`，但一旦提供同样不得是 empty/whitespace-only；
- 错误与日志不得回显完整 reason。

### 3.3 Current ReviewProjection

```text
ReviewProjection
  submission_id
  status
  optimistic_version
  latest_sequence
  updated_by
  updated_at
```

`ReviewEvent` 是 Review 状态变化的 A 类权威事实；Projection 是可由完整 event stream 重建的
recoverable durable current view，不与 event 并列成为第二份权威事实。每次 mutation、GET、Finalize
replay 都必须验证：

```text
projection.optimistic_version == projection.latest_sequence == max(event.sequence)
projection.status == latest_event.to_status
projection.updated_by == latest_event.actor_id
projection.updated_at == latest_event.occurred_at
event.sequence == 0..max(event.sequence)  # 从 0 开始，无缺口、无重复
```

任一不变量不成立均抛出 typed `ReviewIntegrityFailure` 并 fail closed；请求路径不得自动修补、追加 event
或把损坏伪装成 404。Projection 可由 event stream 重建，但 5C 不增加 operator HTTP endpoint；恢复须由
后续明确授权的 operator procedure 在单独事务中完成。Projection 不复制
Submission/Workspace/Repository/Archive 字段，不保存 candidate、archive eligibility 或 History label。

### 3.4 Idempotency record

```text
ReviewIdempotencyRecord
  business_project_id
  submission_id
  idempotency_key
  request_fingerprint
  event_sequence
```

Idempotency namespace 冻结为 actor-independent project-wide namespace：primary key 是
`(business_project_id, idempotency_key)`，不是 `(submission_id, key)` 或 `(actor_id, key)`。因此同一
project 内跨 actor 使用 same key/same fingerprint 可 replay 原 event；same key/different fingerprint
（包括改为另一 Submission）返回 conflict。不同 project 可独立复用同一 key。新 key 永远按当前
state/version 重新验收，不能把语义相同的非法重复动作当作 replay。该选择与 project/device reviewer
permission 一致；actor 不是 fingerprint 字段，replay response 中的 event actor 仍是首次提交者。
读取 record 时必须验证其 project 与 owning Workspace 一致、`(submission_id, event_sequence)` exact
解析到 user ReviewEvent，且该 event 可按 v1 contract 重建相同 fingerprint；dangling、cross-project、
cross-submission 或 fingerprint/event mismatch 均是 `ReviewIntegrityFailure`，不是 replay/conflict/404。

## 4. State machine

### 4.1 Transition matrix

| Current | Command | Next | Workspace effect | Decision |
| --- | --- | --- | --- | --- |
| `PENDING` | `APPROVE` | `APPROVED` | 要求并保持 exact Submission occupancy | allowed |
| `PENDING` | `REJECT` | `REJECTED` | clear pointers + release occupancy | allowed |
| `PENDING` | `RETURN_FOR_REVISION` | `RETURNED_FOR_REVISION` | clear pointers + release occupancy | allowed |
| `PENDING` | `WITHDRAW` | `WITHDRAWN` | clear pointers + release occupancy | allowed |
| `APPROVED` | `RETURN_FOR_REVISION` | `RETURNED_FOR_REVISION` | exact occupancy 仍存在时 clear/release | allowed |
| `APPROVED` | `APPROVE/REJECT/WITHDRAW` | — | none | conflict |
| terminal | any new key | — | none | conflict |

`REJECT` 和 `RETURN_FOR_REVISION` 必须携带 non-empty reason；`APPROVE` 与 `WITHDRAW` 可省略，若提供
仍受相同 bounds。状态转换错误稳定返回 `REVIEW_TRANSITION_CONFLICT`。

### 4.2 Archive race barrier

5D 不存在长时间 `ArchiveExecution`；StartArchive 成功在一个本地 transaction 内消费 selected 与
sibling occupancy。Review return transaction 要求：

```text
workspace_submit_occupancy.active_submission_id == submission_id
```

Review 与 Archive 均使用 control DB `BEGIN IMMEDIATE`。因此：

- return 先提交：projection 不再 APPROVED、occupancy 已释放，StartArchive 不能选择它；
- Archive 先提交：occupancy 已释放，return exact precondition 失败；
- 不需要 archive lock、in-progress state、outbox、tombstone 或 Repository ref probe。

`PENDING -> APPROVED` 也必须在写 event 前证明 exact occupancy 存在；没有该屏障不得产生可供 5D
选择的 `APPROVED` fact。

### 4.3 Request and replay ordering

POST、GET 和 replay 共用以下外层授权顺序：

1. 验证 current session；缺失、失效或过期返回 `401 AUTHENTICATION_REQUIRED`；
2. 仅检查 session 中是否含 exact `review_submission` permission，且必须发生在任何 Submission、
   Workspace、Review event/projection/idempotency object read 之前；缺失统一返回 `403 SCOPE_FORBIDDEN`；
3. 解析 current device/project provisioned mapping；missing/disabled 返回 `404 RESOURCE_NOT_FOUND`，
   provider operational failure 返回 `503 DEPENDENCY_UNAVAILABLE`；
4. 在 resolved project/device/repository scope 中读取对象；Submission/Review absent、cross
   device/project/repository 或 mapping drift 统一返回 `404 RESOURCE_NOT_FOUND`；
5. Review closure 损坏返回 `503 SERVICE_NOT_READY`，不得降格为 404。

permission check 只读取认证后的 session claims，不以 object existence 为前提，因此 unknown id、跨 scope
id 与 same-key replay 均不会绕过 permission-before-object-read。

完成上述门禁后，每个 mutation transaction 按以下顺序处理：

1. 在 write transaction 内重新加载 resolved scope 对应的 Submission/Workspace 和完整 Review closure；
2. 查 `(business_project_id, idempotency_key)`；
3. existing + same fingerprint：从原 event 重建原始 `ReviewAppliedResponse`，不读取最新 projection
   冒充原结果，也不重写 facts；
4. existing + different fingerprint：`IDEMPOTENCY_CONFLICT`；
5. 无 existing：校验 expected review version、transition、reason 与 occupancy；
6. append event、CAS projection、写 idempotency；
7. 若为 release action，同事务更新 Workspace 与删除 occupancy；
8. commit 后返回。

Replay 仍执行上述 current-session authentication、permission-before-object-read、mapping 和 scope 检查；
旧授权不是永久票据。GET 执行同一外层顺序，并在返回前验证 event/projection closure。

## 5. Scope and authorization

### 5.1 Permission

exact permission：

```text
review_submission
```

它适用于四条 mutation 和 Review facts read。Review 是 project/device 级职责，允许 reviewer 审核
不同 owner actor 的 Workspace；不要求 `context.actor_id == workspace.owner_actor_id`。

### 5.2 Scope closure

Application 必须同时校验：

```text
context.gateway_device_external_key == workspace.gateway_device_external_key
context.business_project_id == workspace.business_project_id
resolved_scope.repository_id == workspace.repository_id
submission.workspace_id == workspace.workspace_id
submission.repository_id == workspace.repository_id
```

具体且唯一的 HTTP disclosure policy 是：permission 缺失在任何 object read 前返回 403；object absent、
跨 device/project/repository、mapping missing/disabled/drift 返回 404；control DB 或 scope provider
运行故障返回 503。该策略适用于 POST、GET 和 replay。日志只记录 safe request correlation，不记录
token、reason、artifact path 或 source payload。

### 5.3 Withdraw semantics

`WITHDRAW` 使用相同 project/device reviewer permission，不引入 owner-only special case。若未来产品
要求 submitter self-withdraw 或 reviewer/submitter 分权，必须在 permission contract、HTTP tests 与
transition policy 中显式 reopen；不得只在 route 增加 actor comparison。

## 6. Application commands and queries

### 6.1 Command

```text
ApplyReviewCommand (inbound; HTTP caller fields only)
  context
  submission_id
  expected_review_version
  action: APPROVE | REJECT | RETURN_FOR_REVISION | WITHDRAW
  reason optional
  idempotency_key

ApplyReviewResult (transaction commit output)
  event
  projection
  request_fingerprint
  replay
```

`replay` 为 `true` 时表示 same-key/same-fingerprint 重放，HTTP 返回 `200 OK`；fresh commit 为
`false`，HTTP 返回 `201 Created`。Replay 结果从 bound event 重建，不代表当前 projection。

Inbound `ApplyReviewCommand` 不含 `request_fingerprint`。Application 在 scope closure 后生成
fingerprint，并写入 `ApplyReviewResult` / idempotency record；HTTP
caller 永不提供 fingerprint。Fingerprint 使用既有 canonical JSON/digest
utility，contract 冻结为 `gateway-vnext.review-apply-fingerprint.v1`。输入是以下 closed object，不得增加、
删除、重命名字段，也不得加入 actor 或运行时值：

```json
{
  "action": "APPROVE",
  "business_project_id": "project-1",
  "contract_version": "gateway-vnext.review-apply-fingerprint.v1",
  "expected_review_version": 0,
  "gateway_device_external_key": "device-1",
  "reason": null,
  "repository_id": "repository-1",
  "submission_id": "submission-1",
  "workspace_id": "workspace-1"
}
```

字段值取 scope closure 验证后的 frozen Submission/Workspace/resolved mapping identity；`reason` 使用
§3.2 校验后未经任何转换的原值或 JSON `null`。对该 object 使用 Shared Kernel RFC 8785 JCS
`canonicalize_json_value` 生成 UTF-8 bytes，再计算 SHA-256；输出固定为
`sha256:` + 64 个 lowercase hex 字符。它不包含 actor id、bearer token、display name、server path、
current time 或随机 event id。v1 object、JCS 或 digest/output format 任一变化都必须 bump contract version，
且在迁移旧 idempotency records 前不得上线。

上述 exact 示例的 golden 输出固定为：

```text
sha256:f97a6da6f2c568efdbbecdf64b6687593f5dc10b708cca81e602ba1a4e77b909
```

`Idempotency-Key` 是原样存储和比较的 ASCII opaque value：长度 `1..255` characters，只允许
U+0021–U+007E；不 trim、不做 Unicode normalization，因而 whitespace、DEL/C0/C1 control、non-ASCII
与 empty value 都以 422 拒绝。其 namespace 按 §3.4 固定。

### 6.2 Read query

```text
GetReviewFacts
  context
  submission_id

ReviewFacts
  projection
  events ordered by sequence ascending
```

当前状态图最多产生三个 events：seed、approve、return。GET 可以一次返回 closed list，不引入 cursor。
若将来允许反复 reopen/reapprove 或 comment stream，必须重新评估 bound 和 pagination。

### 6.3 Ports
最小 ports：

```text
ReviewReadPort
  get_projection(submission_id)
  list_events(submission_id)
  find_idempotency(business_project_id, key)

ReviewWritePort
  insert_seed(event, projection)
  append_event(event)
  cas_projection(projection, expected_version)
  insert_idempotency(record)

SubmissionReadPort
WorkspaceRepository
ScopeResolutionPort
ReviewControlUnitOfWorkFactory
```

为复用现有 HTTP dependency bundle 而不引入 unchecked cast，application ports 同时定义组合
`WorkspaceControlTransaction` 与 `WorkspaceControlUnitOfWorkFactory`：前者结构化继承既有
`SubmitControlTransaction` 和新增 `ReviewControlTransaction`，后者返回该组合 transaction。现有
`WorkspaceHttpDependencies.unit_of_work_factory` 只把静态类型改为该组合 factory；production 仍传入
同一个 `ControlDbUnitOfWork` callable，不增加字段、adapter 或 runtime wiring。组合 factory 必须可作为
既有 Submit factory 使用，也可作为 `ReviewControlUnitOfWorkFactory` 使用。

5D/5E 只依赖 stable application/domain read contracts，不 import SQLite row、HTTP response 或 private
helper。

## 7. SQLite schema and migration

### 7.1 Schema component

5C 将现有 `workspace` control schema 从 version 3 升级到 version 4；不创建新的数据库文件或 schema
ledger。新增表：

```text
review_event_records
review_projection_records
review_idempotency_records
```

约束至少覆盖：

- all ids/key/status/kind/reason bounds and types；reason byte bound 使用
  `length(CAST(reason AS BLOB))`，不得误用 SQLite character count；
- `(submission_id, sequence)` primary key；
- one projection per Submission；
- `(business_project_id, idempotency_key)` primary key；
- idempotency `(submission_id, event_sequence)` composite foreign-key 到 event；
- projection/event/idempotency 均 foreign-key 到 immutable Submission；
- status/kind closed enum；
- non-negative version/sequence；
- latest projection sequence 对应存在 event；
- immutable events 没有 update/delete repository method。

SQLite 不能独立表达的 `from -> to` matrix、连续 sequence 和完整 projection/event equality 由 Domain
policy、repository closure validator 与 transaction test 共同强制，不复制成 trigger。append 只能插入
`projection.latest_sequence + 1`，seed 只能是 sequence/version `0`；每次 read/mutation/finalize replay
都执行 §3.3 closure validator。

### 7.2 Existing-data backfill

v3 -> v4 migration 在同一 migration transaction 内为每个 existing `submission_records` 插入：

```text
sequence = 0
event_kind = SUBMISSION_FINALIZED
from_status = null
to_status = PENDING
actor_id = submission.created_by
occurred_at = submission.created_at
projection.status = PENDING
projection.optimistic_version = 0
projection.latest_sequence = 0
projection.updated_by = submission.created_by
projection.updated_at = submission.created_at
```

Backfill 不生成 user idempotency record，不修改 Submission、Workspace pointer、occupancy 或 artifact。
Migration 前后执行 integrity/foreign-key checks；schema already v4 时 no-op；newer schema fail closed。

### 7.3 Future finalize closure

5C implementation 必须把 `insert_review_seed` 加入现有 T3 transaction：只有新插入 Submission 时才
插入 seed；Finalize replay 读取并验证 existing projection/event closure，不生成第二条 seed。若
Submission 已存在但 seed/projection 缺失或冲突，进入明确 recovery/integrity failure，不返回伪成功。

该 failure 的唯一 typed application error 定义在现有异常模块
`gateway_backend.application.submission.errors.ReviewIntegrityFailure`（stable code
`REVIEW_INTEGRITY_FAILURE`）；HTTP 统一映射 `503 SERVICE_NOT_READY`。它覆盖 seed/projection 缺失、
projection/event 分叉、event sequence 缺口，以及 idempotency 指向不存在或不匹配 event。该错误只给
bounded generic message，不暴露损坏 row 内容。

这是 5C 对 Submission finalize closure 的扩展，不改变 Repository result validation、Attempt state、
Operation terminal、artifact protection 或 repository occupancy release。

## 8. Atomic Workspace release

release action 的 transaction preconditions：

- Submission 存在且属于 resolved scope；
- Review projection/version 与 command 一致；
- transition allowed；
- Workspace state 是 `OPEN`；
- `workspace.generation == submission.workspace_generation`；
- `workspace.current_upload_revision_id == submission.upload_revision_id`；
- `workspace.current_preview_result_id == submission.preview_result_id`；
- `workspace_submit_occupancy.active_submission_id == submission.submission_id`；
- Workspace 与 Submission frozen workspace/repository identity 一致。

以上 preconditions 必须全部在 append `ReviewEvent` 前验证。任一不匹配都返回
`WORKSPACE_OCCUPANCY_CONFLICT`，并证明 event、projection、idempotency、Workspace pointers/version 和
occupancy 全部不变。`PENDING -> APPROVED` 不清 pointer，但同样要求 Workspace 为 `OPEN`、frozen
workspace/generation/repository identity 一致且 exact occupancy 存在。

成功后：

```text
workspace.current_upload_revision_id = null
workspace.current_preview_result_id = null
workspace.optimistic_version += 1
workspace.updated_at = transaction_now
delete exact workspace_submit_occupancy row
```

Workspace generation 不变；下一 Upload 使用既有逻辑推进 generation。Review 不删除 historical
UploadRevision/PreviewResult，不释放长期 source/canonicalization protection，不修改 Submission record。

任一 statement/CAS/integrity failure 回滚全部 event/projection/idempotency/workspace changes。不存在
“Review 已成功但 Workspace 未释放”或相反的合法状态。

## 9. HTTP contract

### 9.1 Apply review event

```text
POST /v1/submissions/{submission_id}/review-events
Authorization: Bearer <session>
Idempotency-Key: <bounded opaque key>
Content-Type: application/json
```

Closed request：

```json
{
  "expected_review_version": 0,
  "action": "APPROVE",
  "reason": null
}
```

`action` only：`APPROVE | REJECT | RETURN_FOR_REVISION | WITHDRAW`。Unknown fields、wrong types、
out-of-range integers，以及不满足 §3.2/§6.1 exact character contract 的 keys/reasons 以 closed-schema
422 拒绝。Path Submission id 不在 body 重复。

Success：

- first commit：`201 Created`；
- same-key/same-fingerprint replay：`200 OK`；
- body 为与该 key 的 event sequence 绑定的 `ReviewAppliedResponse`。

```text
ReviewAppliedResponse
  submission_id
  status                 # bound event.to_status
  review_version         # bound event sequence/version
  event: ReviewEventResponse
```

若原 `APPROVE` 之后已有合法 return，重放 approve key 仍返回原 `APPROVED/version 1` 结果；caller 通过
GET 获取最新 projection。这样满足 same-key replay 返回原结果，而不持久化重复 response blob。

### 9.2 Get review facts

```text
GET /v1/submissions/{submission_id}/review
Authorization: Bearer <session>
```

Closed response：

```text
ReviewFactsResponse
  submission_id
  status
  review_version
  updated_by
  updated_at
  events[]

ReviewEventResponse
  sequence
  event_kind
  from_status optional
  to_status
  reason optional
  actor_id
  occurred_at
```

不返回 repository internal ref、artifact refs、server path、session/token 或 SQLite identifiers。

### 9.3 Stable error mapping

| Status | Code | Meaning |
| --- | --- | --- |
| 401 | `AUTHENTICATION_REQUIRED` | session missing/expired/invalid |
| 403 | `SCOPE_FORBIDDEN` | `review_submission` permission missing；permission-before-object-read |
| 404 | `RESOURCE_NOT_FOUND` | object absent/cross-scope，或 mapping missing/disabled/drift |
| 409 | `IDEMPOTENCY_CONFLICT` | same key, different fingerprint |
| 409 | `REVIEW_VERSION_CONFLICT` | expected version stale |
| 409 | `REVIEW_TRANSITION_CONFLICT` | action invalid for current status |
| 409 | `WORKSPACE_OCCUPANCY_CONFLICT` | exact active Submission no longer owns Workspace |
| 422 | `REQUEST_VALIDATION_FAILED` | closed DTO/bounds/reason invalid |
| 429 | `ADMISSION_LIMIT_REACHED` | new mutation admission closed/full |
| 503 | `DEPENDENCY_UNAVAILABLE` | scope provider operational failure |
| 503 | `SERVICE_NOT_READY` | control DB unavailable、schema/readiness 未闭合或 `ReviewIntegrityFailure` |

POST 使用现有 new-work admission gate；GET 在 shutdown drain 中仍可按当前 read policy服务。Exception
mapping 不包含 raw reason、token、SQL 或 private path。

## 10. History and Archive handoff

### 10.1 5D Archive

5C 交付 `ReviewReadPort`/projection status 和 exact occupancy semantics。5D CandidateProjection 仅选择：

```text
ReviewStatus == APPROVED
submission.based_on_baseline_node_id == current BaselineHead node
no ArchiveResult disposition
```

5D 不反向修改 Review status。StartArchive 释放 occupancy 后，5C approved-return guard自然关闭。

### 10.2 5E History

5C 的 `ReviewFacts` 是 5E HistoryTreeProjection 的输入。5C GET 只提供单 Submission 的 Review facts；
它不建设 project history listing、cursor、commit resolve、comparison Operation 或 bundle。所有
Submission commit，包括 rejected/returned/withdrawn，继续保留并可由未来授权 History 读取。

## 11. Deployment and runtime boundary

- Backend HTTP 与现有 SQLite/WAL control DB 内完成；
- 不注册 JobDefinition、worker handler 或 recovery command；
- 不调用 Repository Client，不要求 Dolt；
- 不改 backend/worker process topology、UID/GID、volume、socket、health/readiness contract；
- production session fixture/config 在 implementation 时加入 `review_submission`；
- source/schema/route change 会触发最终 current-HEAD backend/worker image rebuild 和 container gate；
- Repository Service build input若未变，仍按权威 runner/provenance规则验证 current candidate identity。

## 12. Verification ownership

| Invariant | Unique test owner |
| --- | --- |
| status/event model and transition matrix | `tests/test_review_domain.py` |
| v3->v4 schema, backfill, constraints, row mapping | `tests/test_review_persistence.py` |
| idempotency/version/atomic Workspace release/Archive race barrier | `tests/test_review_transactions.py` |
| future T3 seed + Finalize replay closure | existing `tests/test_submit_transactions.py` |
| route/closed DTO/status/error/current-session scope | `tests/test_review_http.py` |
| architecture dependency and no Repository/Operation imports | existing `tests/test_architecture.py` |
| deployed Submit->Review smoke and OpenAPI exposure | `tests/test_review_compose_e2e.py` |

Tests prove semantic barriers, not every SQL statement ordering. Review tests must not create a real Dolt
repository or spawn Repository Service for pure transition/persistence/HTTP logic. Time-sensitive thread/process
tests are unnecessary unless implementation introduces a real timing dependency; ordinary SQLite concurrency is
tested deterministically with transactions/preconditions.

Review permission matrix 的唯一 owner 是 `tests/test_review_http.py`，包含 POST、GET、replay 的
permission-before-object-read、跨 actor same-key replay 和 403/404/503 taxonomy。既有
`tests/test_http_auth_matrix.py` 不承担 5C Review coverage，避免重复 ownership。

## 13. Reopen conditions

Stop implementation and reopen owning design/contract if any of the following becomes required：

- reviewer assignment、multi-party quorum、approval chain、comment workflow 或 start-review state；
- approve/reject/return/withdraw 需要异步 external effect；
- Review must modify/delete Repository commit/ref or business History；
- submitter self-withdraw requires a distinct owner-only authorization model；
- Review event stream becomes unbounded and needs paging/retention；
- external audit/event consumer requires delivery guarantee/outbox；
- Archive introduces a durable in-progress state instead of one local transaction；
- multi-host writer、external DB、HA or new trust principal。

## 14. Acceptance conditions

Design acceptance requires independent docs review to confirm：

- alignment with Business Lifecycle status/owner/short transaction；
- no `START_REVIEW`, Repository effect, Operation, outbox or duplicated Archive/History state；
- transition and occupancy matrix closes approved-return vs Archive race；
- migration/backfill and future Finalize seed preserve one projection/event stream per Submission；
- permission/scope/idempotency/error contracts are closed and testable；
- execution stages/allowed paths/test owners are proportional and non-overlapping；
- pre-S1 design acceptance gate is satisfied; S1+ implementation authority is recorded separately in the execution plan and does not imply P5-5D/P5-5E authorization。

```yaml
p5_5c_design_candidate: accepted
p5_5c_design_accepted: yes
p5_5c_implementation_authorized: yes
first_authorized_step: P5-5C-S1
```

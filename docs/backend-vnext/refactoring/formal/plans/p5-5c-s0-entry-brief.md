# P5-5C-S0 Entry Brief: Review

状态：**DESIGN ACCEPTED — IMPLEMENTATION AUTHORIZED (P5-5C-S1)**

日期：2026-09-19

Owner：Submission Domain + Review Application + HTTP Interface

授权来源：repository owner 在当前会话明确授予 P5-5C-S0 docs-only entry/design authority。

上游：[P5-5B-S8 Independent Slice Exit Acceptance](p5-5b-s8-independent-acceptance.md)、
[P5 Business Vertical Slices Design Baseline](p5-business-vertical-slices-design.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)、
[Implementation Stages](implementation-stages.md)、
[Proportional Assurance and Risk-Based Verification Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)

## 1. Entry identity and authority

```yaml
step_id: P5-5C-S0
entry_kind: review_vertical_slice
authorization_source: explicit_repository_owner_authorization_in_current_conversation
authorization_base_sha: a7ed4090bd1e182a77aff074ac9573692cfce9d6
p5_5b_slice_exit: pass
p5_design_baseline: accepted
p5_5c_s0_entry_authorized: yes
p5_5c_design_s0_authorized: yes
p5_5c_design: accepted
p5_5c_design_status: accepted
p5_5c_implementation_authorized: yes
source_or_test_change_authorized: true
unresolved_contract_drift: none
first_authorized_step: P5-5C-S1
implementation_head: 0e9c131b6c90bd7f32c8cac886896740bbb99215
migration_or_route_change_authorized: false
repository_effect_authorized: false
production_deployment_authorized: false
review_scope: implementation_s1
next_step: P5-5C-S1
next_step_authorized: yes
```

本 S0 授权当时只允许冻结 P5-5C 的领域状态机、持久事实、短事务、HTTP contract、权限、幂等、
Workspace release、5D/5E handoff 和实施/验证分解；属于 docs-only entry 边界，不授权当时的
`vnext/**` 实现改动。后续 repository owner 在 `0e9c131b` 明确授权 P5-5C-S1 implementation，
允许修改 S1 path budget 内的 `vnext/backend` 与对应测试；仍不授权依赖锁、数据库 migration、
route、OpenAPI、镜像、Compose 或生产部署，也不授权任何 Repository read/write effect。

## 2. Entry decision

P5-5C 已满足设计入口：5B 在 gate-tested implementation `460d6f5b` 上通过独立 slice exit；当前
authority base `a7ed4090` 相对接受记录没有 `vnext/**` 实现漂移；Review 的 owner、状态集合、
Workspace release、History inclusion、Repository 禁写和短事务边界均已由 owning contract 冻结。

本轮没有需要 reopen Contract/ADR 的问题。exact route、closed DTO、permission 字符串、事件字段、
idempotency fingerprint、错误映射和 stage/test owner 属于本 S0 详细设计范围。

## 3. Objective and user journey

5C 在已成功 Finalize 的 immutable Submission 上交付同步 Review：

```text
authenticate current session
  -> require project/device reviewer permission before object read
  -> resolve provisioned project/device scope
  -> load immutable Submission + owning Workspace
  -> load current ReviewProjection and project-wide idempotency record
  -> validate expected review version and transition
  -> append one immutable ReviewEvent
  -> update ReviewProjection
  -> when reject/return/withdraw: clear Workspace current input/preview and release occupancy
  -> commit one local SQLite transaction
  -> return current review facts
```

Review 不创建 Operation，不进入 worker，不调用 Repository Service，不移动或删除 ref，也不改变
Submission 的 immutable commit/source/binding facts。响应成功即表示本地权威 Review 事务已提交。

## 4. In scope and non-goals

### 4.1 In scope

- `PENDING | APPROVED | REJECTED | RETURNED_FOR_REVISION | WITHDRAWN` projection；
- immutable ReviewEvent、当前 ReviewProjection 与幂等记录；
- `APPROVE | REJECT | RETURN_FOR_REVISION | WITHDRAW` 同步 command；
- project/device scope 的 current-session authorization；
- optimistic version、caller idempotency key、same-key replay/conflict；
- reject/return/withdraw 的 Workspace pointer clear 与 submission occupancy release；
- approve 后保持 occupancy，允许 5D 从 approved facts 派生 CandidateProjection；
- Review facts read response，以及供 5E History projection 消费的稳定 read port；
- schema migration/backfill 和未来 Submission finalize 的 PENDING seed；
- focused tests、static、权威 runner 与最终 current-HEAD container gate 的实施计划。

### 4.2 Out of scope

- `START_REVIEW`、review-in-progress、assignment、queue、SLA、comment thread 或多签审批；
- Archive Candidate/Plan/Result、BaselineHead advance、`CLOSED_NOT_ARCHIVED`；
- 完整 HistoryTreeProjection、History Compare operation/bundle/cursor；
- Repository read/write、commit/ref create/move/delete/cleanup；
- Operation/JobDefinition/worker、outbox、event dispatcher 或外部通知；
- legacy wire/persistence migration、production cutover、HA、外部 DB 或新安全主体；
- artifact retention、source facts、Submission 内容或 5B T1/T2/T3 语义变更。

## 5. Frozen state-machine boundary

初始 Review projection 在 Submission finalize 时与 Submission 同事务创建：

```text
Submission finalized -> PENDING

PENDING  -> APPROVED
PENDING  -> REJECTED
PENDING  -> RETURNED_FOR_REVISION
PENDING  -> WITHDRAWN
APPROVED -> RETURNED_FOR_REVISION  # 仅在 Workspace 仍由该 Submission 占用时
```

`REJECTED | RETURNED_FOR_REVISION | WITHDRAWN` 为 5C 终态。`APPROVED` 不是 Archive 完成；它只让
5D 能派生 candidate。重复 command 只有 same idempotency key/same fingerprint 才 replay；使用新 key
重复相同动作仍按当前状态机拒绝，不追加无意义事件。

5D StartArchive 是单个本地事务，并在成功时释放 selected/sibling Workspace occupancy。因此
`APPROVED -> RETURNED_FOR_REVISION` 只需在同一 SQLite write transaction 中 CAS 当前 Review version
并要求 `active_submission_id == submission_id`；Archive 和 return 由 `BEGIN IMMEDIATE` 串行，先提交
Archive 后 return 必然失败，先提交 return 后该 Submission 不再是 candidate。5C 不预建 Archive 状态。

## 6. Authorization and scope

P5-5C 冻结一个 permission：

```text
review_submission
```

四条 mutation 与 Review facts read 均要求该 permission。它是 project/device permission，不要求
caller actor 等于 Workspace owner，允许授权 reviewer 跨 actor Workspace 审核。每次请求都必须：

1. 从当前 session 取得 actor/device/project/permissions；
2. 在任何 object read 前检查 `review_submission` permission；缺失为 403；
3. 解析当前 provisioned device/project mapping；
4. 校验 Submission、Workspace 与 mapping 的 frozen device/project/Repository identity；
5. object absent/cross-scope 或 mapping missing/disabled/drift 为 404；provider/DB 运行故障为 503。

知道 `submission_id` 或 Repository CommitId 不构成读取或 mutation authority。disabled/unmapped scope、
session expiry、Repository mapping drift 和 permission 缺失均 fail closed。Review 不使用 deployment
internal bearer，也不新增 principal。

## 7. Persistence and transaction boundary

5C 持久化三类最小事实：

- immutable `ReviewEvent`：按 Submission 单调 sequence 保存发生过的状态变化；
- recoverable durable `ReviewProjection`：保存 current status、optimistic version 和 latest sequence，可从
  immutable event stream 重建；
- `ReviewIdempotencyRecord`：保存 project-wide
  `(business_project_id, key) -> submission_id + fingerprint + event sequence`。

初始 `SUBMISSION_FINALIZED -> PENDING` event 与 projection 属于 Submission finalize closure。Schema
升级必须为已存在的 `submission_records` 幂等 backfill 初始 event/projection；未来 finalize 必须在插入
Submission 的同一事务内写 seed。该集成由 5C owner 交付，不 reopen 5B Repository effect 或 T1/T2。

reject/return/withdraw 的一个 transaction 原子完成：

- append ReviewEvent；
- CAS ReviewProjection；
- 写 idempotency record；
- 校验 Workspace 为 OPEN，generation、current upload/current preview pointer exact 匹配 Submission，且
  occupancy exact 指向该 Submission；
- 清空 current upload/current preview pointer；
- 删除 submission occupancy；
- 推进 Workspace optimistic version 和 `updated_at`。

Review release 不改变 Workspace generation；下一次 Upload 按既有规则创建新 generation。它不删除
UploadRevision、PreviewResult、Submission、source artifact 或 Repository commit，也不触发 cleanup。

## 8. HTTP and idempotency envelope

详细设计冻结两条 project-scoped route：

```text
POST /v1/submissions/{submission_id}/review-events
GET  /v1/submissions/{submission_id}/review
```

POST 使用 project-wide、actor-independent `Idempotency-Key` header；key 固定为 `1..255` 个
U+0021–U+007E ASCII characters，原样存储比较且不 trim。Closed body 包含
`expected_review_version`、`action` 和 optional `reason`。Reason 原样保存/参与 fingerprint，不 trim 或做
Unicode normalization，UTF-8 编码长度 `1..4096` bytes，并拒绝 C0/C1 control、surrogate 与
noncharacter；reject/return 要求 non-whitespace reason。Fingerprint contract version、closed object、
RFC 8785 JCS、SHA-256 和 `sha256:<lowercase hex>` 输出由详细设计完整冻结。

POST 返回与本 idempotency key 绑定的 immutable event result；replay 即使发生在后续合法 transition
之后也重建原始 event 的 status/version，不伪装成最新状态。GET 返回 current projection 和按 sequence
排序的 bounded events。当前状态机每个 Submission 最多三个 event（initial、approve、return），
不建设分页。5E 使用 application read port，不通过 HTTP 自调用。

## 9. Risk and proportional assurance register

```yaml
authoritative_facts:
  - immutable ReviewEvent
  - Workspace occupancy and current pointers
recoverable_durable_state:
  - current ReviewProjection rebuilt from immutable ReviewEvent stream
  - ReviewIdempotencyRecord binding a project-wide retry key to an authoritative event
derived_or_temporary_state:
  - response DTO
  - future CandidateProjection and HistoryTreeProjection
external_trust_boundaries:
  - current user session
  - HTTP path/header/body
accepted_deployment_assumptions:
  - single host
  - one SQLite/WAL control DB
  - no external event consumer
highest_risk_class: A
required_semantic_barriers:
  - current scope and permission
  - transaction plus optimistic CAS
  - idempotent replay/conflict
  - event/projection/idempotency integrity closure with typed fail-closed error
  - exact occupancy release
  - no Repository effect
explicitly_out_of_scope:
  - workflow runtime
  - external audit pipeline
  - multi-party review
  - HA or external DB
```

强验证集中在 Review/Workspace 权威事实的事务与权限边界。由于没有外部 effect、worker、artifact
或恢复状态，本 Slice 不建立 Operation、receipt、outbox、crash state machine 或 sidecar。

## 10. Design outputs and allowed docs paths

本 S0 输出：

- [P5-5C Review Detailed Design](p5-5c-review-design.md)；
- [P5-5C Review Execution Plan](p5-5c-review-execution-plan.md)；
- 本 Entry Brief；
- active authority/index 文档的 docs-only 状态更新。

Allowed docs paths：

```text
docs/backend-vnext/refactoring/formal/plans/p5-5c-*.md
docs/backend-vnext/refactoring/formal/plans/p5-business-vertical-slices-design.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md
docs/backend-vnext/refactoring/formal/README.md
docs/backend-vnext/README.md
```

## 11. S0 exit and next authority

S0 docs-only entry 已完成；design 与 execution plan 已由 independent docs review 接受。repository
owner 在 `0e9c131b` 授权 `p5_5c_implementation_authorized: yes` 与 `first_authorized_step: P5-5C-S1`。
当前 next action 为 S1 independent countersign；通过后进入 S2，仍不自动授权 P5-5D/P5-5E 或 production
deployment。

```yaml
p5_5c_s0_entry: authorized
p5_5c_design_candidate: accepted
p5_5c_design_accepted: yes
p5_5c_implementation_authorized: yes
first_authorized_step: P5-5C-S1
next_step: P5-5C-S1-handoff
```

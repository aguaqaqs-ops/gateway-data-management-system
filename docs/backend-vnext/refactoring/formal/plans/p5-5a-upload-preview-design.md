# P5-5A 上传/预览详细设计

状态：**CLOSED — design accepted; historical input for 5B; 5A slice exit pass**

日期：2026-09-08

Owner：Workspace Application、HTTP Interface、Preview JobDefinition

上游：[P5 Business Vertical Slices Design Baseline](p5-business-vertical-slices-design.md)、
[P5-5A Baseline Acceptance](p5-5a-baseline-acceptance.md)、
[P5-5A-S0 Entry Brief](p5-5a-s0-entry-brief.md)、
[Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)、
[Repository Service](../contracts/repository-service.md)、
[ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)

本文件冻结5A的可观察语义、HTTP v1逻辑wire和模块边界；不授权修改`vnext/**` source、test、
migration、settings、Docker、Compose或deployment。SQLite物理列名/index、资源上限与TTL数值、
provider调优和production capacity baseline仍在deferred register。激活route生成的FastAPI
OpenAPI是最终wire authority；实现若无法生成本文件冻结的shape，必须回到S0 review，不能静默
改名或增加兼容alias。

## 1. 范围和不变量

5A 是模块化单体中的 Upload/Preview 纵切：HTTP backend 与 worker 使用同一镜像、不同进程，
single host、single worker、本地 SQLite/WAL control DB；Repository Service 是独立内网服务。
外部 control plane 负责 device/project mapping 和 provisioning。只有 provisioning 已创建
Repository、initial empty commit 和 explicit-empty `BaselineNode/Head` 后才能开始。Upload/Preview
不创建 Repository、初始化 Baseline 或执行 Repository write effect。

| 不变量 | 唯一 owner |
| --- | --- |
| Workspace scope、generation、OPEN 唯一性 | Workspace Domain |
| UploadRevision role closure、publication | Workspace Application |
| Preview binding、stale/latest-generation-wins、result publication | Preview Application |
| Operation/Step 状态、lease、checkpoint、CAS | [Operation Lifecycle](../contracts/operation-lifecycle-and-integrity.md) / [P4 R4 handoff](p4-r4-jobdefinition-checkpoint-handoff.md) |
| Snapshot、Comparison、Risk、Surface、Bundle 语义 | P3 capability owner与现有public contracts；本文件只定义5A组合 |
| Artifact envelope、bytes、pin、protected path | [Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md) / [ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md) |
| Repository exact-commit read wire | [Repository Service](../contracts/repository-service.md) / [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md) |
| Submit external effect；5A不得创建effect | [External Effect and Recovery](../contracts/external-effect-and-recovery.md) |

其他计划或 DTO 不得建立第二个 owner。

## 2. Domain/application contract

### 2.1 IdentityContext 和 scope

每个 command/read 都接收：

```text
actor_id
gateway_device_external_key
business_project_id
permissions
```

Application 在 transaction-fresh read 中解析当前 session、active mapping、Repository identity
和 BaselineHead。mapping 缺失、gateway disabled、一个 device 多个 active project 或 BaselineHead
缺失时，创建 revision/Operation 前 fail closed。历史 record 固化创建时的 actor/device/project/
Repository identity；后续 mapping 不重写历史。

Workspace 在 `state=OPEN` 时按
`(owner_actor_id, gateway_device_external_key, business_project_id)` 唯一。Domain state 只有
`OPEN | CLOSED`；`EMPTY`、`INPUT_READY`、`PREVIEW_READY` 是派生 label。generation 和
optimistic_version 单调递增并用于 CAS。

### 2.2 Workspace、UploadRevision、PreviewResult

Workspace 最小字段：

```text
workspace_id, owner_actor_id, gateway_device_external_key, business_project_id, repository_id
state: OPEN | CLOSED
generation, current_upload_revision_id?, current_preview_result_id?
active_submit_attempt_id?, active_submission_id?   # 5B 保留；5A 不写
optimistic_version, created_at, updated_at, closed_at?
```

`CreateOrGetWorkspace` 对 exact scope 幂等；已有 OPEN Workspace 返回原对象，否则创建无
input/Operation 的新对象。跨 scope 访问拒绝（`403` 或不披露时 `404`）。

UploadRevision 是 immutable input selection：

```text
upload_revision_id, workspace_id, generation
input_completeness: FULL | MODIFIED_ONLY
source_artifacts: { INITIAL?: BackendArtifactRef, MODIFIED: BackendArtifactRef }
size_bytes / raw_sha256 / media_type / provenance binding
idempotency_key + request_fingerprint, created_by / created_at
```

`FULL` 恰有 INITIAL+MODIFIED；`MODIFIED_ONLY` 恰有 MODIFIED；没有
`INITIALIZE_BASELINE`。Upload 只做 bounded streaming、size/hash、archive/path/link/root safety、
required files 和 role closure；不做 SQL parsing、Snapshot、comparison、risk、bundle、Repository
write 或 Operation creation。

PreviewResult 是成功 publication 对 exact frozen inputs 的 immutable 绑定：

```text
preview_result_id, workspace_id, upload_revision_id, generation, repository_id
business_baseline_node_id, business_baseline_commit_id, baseline_head_version
ruleset_version, contract_version, provider_versions
source/input/snapshot/comparison/risk/surface/bundle digests
bundle_artifact_ref, ready_closure_ref, operation_id, created_at
```

结果不原地更新；读取时若 current BaselineHead 不同则派生 `derived_stale=true`，不改结果。
stale 结果禁止 Submit，不自动重算。

### 2.3 Command 分离和幂等

逻辑 command 为 `CreateOrGetWorkspace`、`AcceptUpload`、`StartPreview`、`GetOperation`、
`GetPreviewResult`、`ReadPreviewBundle`。Upload 和 Preview 使用不同 key、fingerprint、
重试和失败边界。same key+same fingerprint 返回原 record；same key+different fingerprint 为
`409`；AcceptUpload和StartPreview必须带expected Workspace/Head version。

`CreateOrGetWorkspace`是mutation通则的唯一例外：caller既不提供`Idempotency-Key`，也不提供
不存在对象的expected version。当前session解析出的exact actor/device/project scope是幂等identity；
数据库OPEN partial-unique约束是并发线性化点。唯一赢家创建并返回`201`，其他并发事务在unique
conflict后重读同一OPEN Workspace并返回`200`；不得以application先读后写代替该约束。

`AcceptUpload` 原子发布 role artifacts、创建 revision、递增 generation、设置 current input、
清除 current preview，并把旧 queued Preview 标记 `SUPERSEDED`、旧 running Preview 设置
单调 cooperative-cancel request。CAS 失败不得留下可见 partial revision。

`StartPreview` 在创建 Operation/首个 PENDING Step 前重验 scope、OPEN、current revision/
generation、frozen BaselineHead、artifact 可读性、幂等和已注册 JobDefinition/decoder；成功
返回 `202 + operation_id`。

## 3. HTTP contract

### 3.1 Route、transport和permission

Backend业务HTTP统一使用`/v1/`，不复用legacy `/api/*`。本节的permission字符串属于5A HTTP
Interface registry，不进入domain record或Repository wire：

| Method and route | Use case / success | Required permission |
| --- | --- | --- |
| `POST /v1/workspaces` | CreateOrGetWorkspace；创建`201`，重放/已有`200` | `workspace_read` + exact actor/device/project scope |
| `POST /v1/workspaces/{workspace_id}/upload-revisions` | AcceptUpload；`multipart/form-data`，成功`201` | `upload_submit_workspace` + exact owner scope |
| `POST /v1/workspaces/{workspace_id}/preview-operations` | StartPreview；成功`202` | `preview_workspace` + exact owner scope |
| `GET /v1/operations/{operation_id}` | GetOperation；`200` | `workspace_read` + current exact scope |
| `GET /v1/workspaces/{workspace_id}/preview-results/{preview_result_id}` | GetPreviewResult；`200` | `workspace_read` + current exact scope |
| `GET /v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle` | ReadPreviewBundle；`200` stream | `workspace_read` + current exact scope |

认证身份只来自当前session。actor、permission或Repository identity不得由body/header覆盖。
Workspace path identity与当前mapping不一致时，按信息披露policy稳定返回`404`；已确认对象存在但
permission不足时返回`403`。每次read重新授权，不使用创建时权限快照。

### 3.2 Closed DTO shape

所有JSON object拒绝unknown fields。`Idempotency-Key`是AcceptUpload和StartPreview必需header；
CreateOrGetWorkspace不接受该header作为业务幂等输入，也没有expected-version字段，其并发语义由
exact OPEN scope数据库唯一约束保证。语义DTO冻结如下，Pydantic/OpenAPI可拆成多个
实现model，但不能把domain/persistence/Operation record直接当HTTP DTO：

```text
CreateWorkspaceRequest:
  gateway_device_external_key
  business_project_id

WorkspaceResponse:
  workspace_id, gateway_device_external_key, business_project_id
  state, generation, current_upload_revision_id?, current_preview_result_id?
  optimistic_version, created_at, updated_at

UploadManifestPart:
  expected_workspace_version
  input_completeness: FULL | MODIFIED_ONLY
  artifacts:
    INITIAL?: {part_name, media_type, size_bytes, raw_sha256}
    MODIFIED: {part_name, media_type, size_bytes, raw_sha256}

UploadRevisionResponse:
  upload_revision_id, workspace_id, generation, input_completeness
  source_artifacts, optimistic_version, created_at

StartPreviewRequest:
  expected_workspace_version
  upload_revision_id, generation
  expected_baseline_node_id, expected_baseline_head_version
  options: {}  # v1 closed object; additive option requires contract review

OperationAcceptedResponse:
  operation_id, workspace_id, upload_revision_id, generation
  status: QUEUED

OperationResponse:
  operation_id, job_kind, status, optimistic_version
  created_at, started_at?, completed_at?, diagnostic?

PreviewResultResponse:
  preview_result_id, workspace_id, upload_revision_id, generation, operation_id
  business_baseline_node_id, business_baseline_commit_id
  derived_stale, bundle_digest, created_at
```

Multipart文件part名必须与manifest的`part_name`形成一一映射；重复、未声明、缺失或额外part均
`422`。Bundle response只暴露closure内的相对logical name和bytes，不暴露BackendArtifactRef的
locator、host path或Repository private ref。

### 3.3 Stable error family

错误envelope为closed `{"code": string, "message": string, "details"?: object}`；details必须
bounded且脱敏。每个具体use case拥有自己的code，以下family不得被通用FailureDescriptor取代：

| HTTP | Stable code family | Meaning |
| --- | --- | --- |
| `401` | `AUTHENTICATION_REQUIRED` | session缺失或失效 |
| `403` | `SCOPE_FORBIDDEN` | 已允许披露的对象上permission/scope拒绝 |
| `404` | `RESOURCE_NOT_FOUND` | 对象缺失或按policy隐藏 |
| `409` | `IDEMPOTENCY_CONFLICT`, `WORKSPACE_VERSION_CONFLICT`, `PREVIEW_BINDING_CONFLICT` | same-key/different-fingerprint、stale CAS或frozen binding冲突 |
| `413` | `UPLOAD_LIMIT_EXCEEDED` | compressed/expanded/entry/resource预算超限 |
| `415` | `UPLOAD_MEDIA_UNSUPPORTED` | media或archive格式不支持 |
| `422` | `REQUEST_VALIDATION_FAILED`, `UPLOAD_CLOSURE_INVALID` | closed DTO、path/link/file/role或语义校验失败 |
| `429` | `ADMISSION_LIMIT_REACHED` | bounded admission/backpressure拒绝 |
| `503` | `SERVICE_NOT_READY`, `DEPENDENCY_UNAVAILABLE` | registry、ArtifactStore、control DB或Repository read依赖不可用 |

## 4. SQLite persistence 和 transaction/CAS

物理table/index名称deferred；migration必须提供以下逻辑relations和数据库级约束，不能只靠
application先读后写：

- Workspace：exact scope + state的OPEN唯一约束、单调generation/optimistic version；
- UploadRevision：`upload_revision_id`唯一、`(workspace_id, generation)`唯一、immutable role map；
- Upload idempotency：`(workspace_id, idempotency_key)`唯一并保存request fingerprint与result id；
- Preview acceptance/idempotency：key、fingerprint、frozen binding与Operation id一一对应；
- PreviewResult：`preview_result_id`和`operation_id`唯一，immutable binding/closure，current pointer
  只经Workspace CAS切换；
- 既有Operation/Step、BaselineHead relation由其owner管理；5A migration只增加组合事务所需FK/index，
  不复制owner record或状态。

升级时发现多个OPEN exact scope、dangling current pointer或重复generation必须fail closed并要求
显式migration repair；不得选择任一行继续启动。语义矩阵如下：

| 事务 | 原子事实 | CAS/冲突 |
| --- | --- | --- |
| Workspace create/get | OPEN Workspace 或 no-op | exact-scope unique；重放返回已有 |
| Upload publication | UploadRevision、generation、current input、清除 preview、旧 Preview supersede/cancel | expected Workspace version；过期不创建 |
| Preview acceptance | Operation、首个 PENDING Step、frozen binding、artifact protection | expected Workspace + BaselineHead |
| Terminal failure | terminal Operation/Step、bounded diagnostics | lease/version；迟到 worker 拒绝 |
| Preview publish | PreviewResult、ready closure、current pointer、terminal Operation | 重新读 generation/revision/Head/lease |
| Read | 不写业务事实 | 每次重新检查 session/scope/permission |

Capability/artifact I/O 不在 SQLite transaction 内。artifact 先写入、close、read-back 校验，
再在短事务发布 ref。CAS 失败产生的 derived bytes 只能进入 TTL 候选，不回滚已接受 revision。

## 5. ArtifactStore contract

复用既有 store pattern：bounded `put`、exact-ref `locate/read`、显式 pin intent、retention
classification。bytes 写入 server-owned staging directory，不接受 caller pathname、URL、file
descriptor、symlink 或 host path；size/raw SHA 校验后用同 filesystem atomic rename 发布，partial
file 永不可见。

| 类别 | 保护 | 保留 |
| --- | --- | --- |
| UploadRevision 的 SourcePackageArtifact | immutable；成功 Submission 后长期保留 | metadata durable；bytes 按 policy |
| current Preview 的 snapshot/table/bundle facts | protected pin | superseded 且无 active Attempt 后才可清理 |
| active Operation/checkpoint/ready closure | protected | terminal recovery/readability 完成后 |
| superseded/failed/never-submitted 大 derived bytes | 资格确认后不保护 | conservative fixed TTL、best effort |

Cleanup 拒绝 protected/active/manual-recovery 引用，失败只记录 bounded diagnostics 并重试。
5A 不增加 generic refcount、tombstone、quarantine、broker 或 GC state machine；Preview 到
SubmitAttempt 的 pin transfer 属于 5B。

Application-side port只冻结行为，不暴露Path：

```text
put_stream(kind, bounded_stream, declared_size, declared_raw_sha256, media_type)
  -> BackendArtifactRef
read_exact(ref) -> bounded byte stream
verify_readable(ref, expected_size, expected_raw_sha256) -> verified | failure
set_protection(refs, owner_kind, owner_id, intent) -> applied | idempotent
classify_cleanup(ref, now) -> protected | eligible_after(timestamp) | manual_review
delete_eligible(ref, expected_classification) -> deleted | absent | retryable_failure
```

`set_protection`与business publication在同一control DB Unit of Work中记录intent；filesystem I/O
仍在事务外。Port不允许caller pathname、URL、fd、symlink policy开关或任意delete target。

## 6. Preview job contract

唯一持久 topology：

```text
job_kind: backend-vnext/preview
job_contract_version: backend-vnext/preview/v1
materialize_inputs -> assemble_preview -> publish_preview
```

Payload 只含 stable IDs、generation、frozen baseline node/commit/head version、artifact refs/
digests、ruleset/contract/provider versions、options、idempotency identity；不含 host path、callable、
bearer、SQLite connection 或大对象。Decoder 拒绝 unknown version/field、缺失 identity 和超预算。

`backend-vnext/preview/v1` payload是closed object：

```text
workspace_id, upload_revision_id, generation, repository_id
business_baseline_node_id, business_baseline_commit_id, baseline_head_version
input_completeness
source_artifacts: {INITIAL?: BackendArtifactRef, MODIFIED: BackendArtifactRef}
source_digests, input_digest
ruleset_version, capability_contract_versions, provider_versions
ready_closure_contract_version
idempotency_identity
options: {}
```

JobDefinition registry恰有上述三步；handler/checkpoint schema分别版本化，但不另建业务状态。
Decoder沿用Operation runtime的64 KiB inline payload、depth/aggregate/string/ref预算；超预算payload
必须先成为ArtifactRef，不能提高通用runtime上限。

`materialize_inputs`对两种mode都先通过Repository exact-commit read物化frozen business Baseline。
FULL再物化uploaded INITIAL与MODIFIED，形成Baseline/INITIAL/MODIFIED三侧；MODIFIED_ONLY物化
uploaded MODIFIED，并把同一个Baseline snapshot ref绑定为before/effective INITIAL，不复制第二份
snapshot。校验required tables/default pairs/key/schema后，checkpoint必须闭合各侧Snapshot/Summary/
Table refs、source/ref digests和side role；任一required侧缺失或不可读使Step失败。

`assemble_preview` 调用既有 Snapshot、Comparison、Risk、Surface、Bundle public capability，
写入并回读 immutable output 后记录 versioned READY closure。FULL closure必须包含三侧输入和
`baseline_to_initial`、`initial_to_modified`两组directed pair；MODIFIED_ONLY closure必须包含
Baseline/effective INITIAL、MODIFIED和`initial_to_modified`。XML、ordered-table、risk enhancement
可用 bounded typed diagnostics 降级；required source/table/default-pair/directed-pair/bundle
closure 失败则整个 Preview 失败，不增加 `READY_WITH_WARNINGS`。

`publish_preview` transaction-fresh 重读 Workspace、BaselineHead 和 Operation，校验 generation/
revision、frozen Head、lease/version。发布前 drift -> Operation `SUPERSEDED` 且无 PreviewResult；
无 drift -> 原子创建一个 PreviewResult、设置 current pointer、Operation `SUCCEEDED`。迟到/
重复 writer 不得覆盖；matching replay 返回既有结果。

## 7. FULL/MODIFIED_ONLY capability 映射

| Mode | Frozen business Baseline | INITIAL side | MODIFIED side | Comparison pairs | 默认 view |
| --- | --- | --- | --- | --- | --- |
| FULL | exact-commit reconstructed Baseline Snapshot | uploaded INITIAL Snapshot | uploaded MODIFIED Snapshot | `baseline_to_initial`、`initial_to_modified` | `initial_to_modified` |
| MODIFIED_ONLY | exact-commit reconstructed Baseline Snapshot | 与Baseline使用同一Snapshot ref的effective INITIAL | uploaded MODIFIED Snapshot | `initial_to_modified` | `initial_to_modified` |

Risk、Surface、Bundle 继续使用既有 capability contract。table fan-out、cache hit、decoder 细节
只能成为 bounded diagnostics/checkpoint，不能成为 durable Step；optional degradation 不改变
业务事实或 UploadRevision 有效性。

## 8. Runtime/readiness/shutdown

Backend `/readyz` 在 settings、SQLite migration/integrity、server-owned artifact root 和
JobDefinition registry/decoder 检查完成前为 false。Worker 启动加载 durable Operation，按 P4
runtime reconcile artifact/checkpoint 后报告 health。Repository Service 是 exact Baseline read
依赖；backend 可在无 worker 时进程健康，但 deployment 只有 backend、worker、Repository 全部
healthy 才能宣称完整 5A readiness。

Shutdown 先关闭 Workspace/Upload/Preview creation admission；已有 result read、metrics、admin
readback 在 worker drain/checkpoint 时继续可用。Session expiry/gateway disable 不取消已接受的
pure computation，只阻止新 command 和未授权 read；worker 不持续重新授权 caller。

S5必须提供以下semantic settings；环境变量名和数值在实现时按deployment convention冻结：

| Setting group | Startup/readiness requirement |
| --- | --- |
| control DB | absolute server-owned path、migration target、WAL/integrity检查 |
| artifact root | absolute server-owned root、same-filesystem atomic rename、free-space admission |
| upload budgets | compressed/expanded bytes、entry count、path length、stream timeout |
| operation admission | queue/in-flight上限、registry/decoder完整性 |
| cleanup | fixed conservative TTL、sweep batch、retry backoff |
| Repository read | base URL、secret-file bearer、timeout；日志禁止输出token |

这些设置缺失或互相矛盾时fail startup/readiness；不得运行中猜测默认root、自动创建Repository或
降级到Dolt CLI。

## 9. 验收、deferred 与 reopen

验收必须证明：command/identity 分离；FULL/MODIFIED_ONLY 映射正确；Workspace/UploadRevision/
PreviewResult immutable/CAS；required/optional、READY、supersede/cancel/stale 语义可观察；每次
read 重新授权；artifact protection 在既有 trust model 内；不引入 Repository write、Baseline
initialization、outbox/dispatcher、broker、HA、external DB 或新 principal。

Deferred：SQLite column/index物理拼写与query tuning、resource cap/TTL具体数值、provider tuning、
History cursor/page、Review/Archive DTO、legacy cutover、external consumer、HA/external DB、
production capacity baseline。5A v1 route、DTO字段、permission字符串和stable error family已在§3
冻结，不再属于deferred。

必须 reopen owning contract 的条件：多 active project；Upload 创建 Repository/Baseline、解析
SQL或合并 Preview identity；无法 exact reconstruction；需要 dynamic DAG/per-table Step/broker；
出现真实 consumer、second writer、new principal；store 无法保护 current Preview/active Attempt；
或 P4-R6 改变 Operation/Step/checkpoint/readiness/lease/CAS。

本文件从属于 Business Lifecycle、External Effect、Operation Lifecycle、Canonical Storage、
Repository Service contracts。`p4_r6_exit` 仍 **pending**；`p5_5a_slice_exit` **pass**（见
[P5-5A S6 Handoff](p5-5a-s6-handoff.md)）；`container_gate` **pass**（current-HEAD 重建 + smoke +
conjunction，见 handoff §3.4）。

## 10. S0 authority audit and historical boundary

只读核对结论：Business Lifecycle拥有Workspace/UploadRevision/PreviewResult业务事实；Operation
Lifecycle与P4 R4拥有通用状态、lease、CAS、checkpoint envelope；Repository Service只提供
Repository-scoped exact-commit catalog/row read，不理解Baseline或Preview；External Effect不适用于
5A pure compute；ADR 0012允许同一信任域内的cooperative cleanup，但继续要求server-owned root、
path/symlink边界和protected retention。本文没有建立第二owner或扩大service/principal边界。

`docs/backend-vnext/contracts/**`、`capabilities/**`、`flows.md`、`operations.md`及同级P3设计只作为
non-authoritative historical oracle，用于发现capability行为和fixture。其同步Preview、
`BuildUploadPreview`、`INITIALIZE_BASELINE`、`START_REVIEW`、Archive/Repository ref写入等旧表述
不得覆盖本文件；历史原文保留，不做语义洗写。当前authority中的这些词只能出现在明确删除、
禁止、historical fence或reopen说明中。

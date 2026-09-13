# P5-5A-S0 Entry Brief: Upload and Preview

状态：**CLOSED — HISTORICAL INPUT; 5A slice exit pass; superseded by P5-5B-S0**

日期：2026-09-06

Owner：Workspace Application + HTTP Interface + Preview JobDefinition

上游：[P5 Business Vertical Slices Design Baseline](p5-business-vertical-slices-design.md)、
[P5-5A Baseline Acceptance](p5-5a-baseline-acceptance.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[P4/R5 Retry, Takeover and Effect Recovery Handoff](p4-r5-retry-takeover-effect-recovery-handoff.md)

## 1. Entry identity and decision

```yaml
step_id: P5-5A-S0
entry_kind: upload_preview_vertical_slice
discussion_base_sha: d7cb5b9c2c55e8f8b0814520e9d95c7df0ad00a5
p4_r5_exit: pass
p4_r6_exit: pending
p5_design_baseline: accepted
p5_5a_baseline_acceptance: pass
p5_5a_detailed_design_ready: yes
p5_5a_implementation_authorized: no
p5_5a_slice_exit: pass
p5b_repository_write_in_scope: false
source_or_test_change_authorized: false
superseded_by: P5-5B-S0
```

S0的目的，是在实现前冻结5A的application/domain/HTTP/Operation边界、最小持久事实、
JobDefinition、失败语义和验证矩阵。本brief不授权修改`vnext/**`；P4-R6最终exit和明确的5A
implementation authorization仍是任何source、test、migration、route或deployment改动的硬前置。

## 2. Objective and user journey

5A交付可供新前端直接使用的首个正式纵切：

```text
resolve identity and provisioned scope
  -> create or get OPEN Workspace
  -> upload immutable source package selection
  -> accept asynchronous Preview
  -> poll Operation
  -> read immutable PreviewResult
  -> load complete preview bundle
```

前端可以把Upload与Preview串成一次交互，但Backend保留两个command、两个幂等fingerprint、两个
失败边界。Upload成功不承诺Preview成功；Preview失败不使UploadRevision失效。

## 3. In scope and non-goals

### 3.1 In scope

- Workspace create/get、scope mapping、OPEN uniqueness与optimistic version；
- SourcePackageArtifact streaming admission、content reuse与UploadRevision publication；
- FULL/MODIFIED_ONLY input binding；
- Preview command、Operation acceptance、三步JobDefinition和worker composition；
- baseline/source materialization、comparison/risk/surface/bundle capability orchestration；
- PreviewResult/current pointer publication、artifact pin/TTL和download/read authorization；
- Backend/worker settings、readiness、shutdown admission与必要HTTP/OpenAPI DTO；
- focused、unit、integration、serial、static和适用container gates。

### 3.2 Out of scope

- Baseline或Repository provisioning；
- SubmitAttempt、Repository import、Submission、Review、Archive和History Compare；
- Repository ref mutation、Dolt binary/volume access或real external effect；
- legacy HTTP/persistence compatibility；
- generic outbox、generic refcount GC、arbitrary workflow DAG或per-table durable Step；
- HA、多worker membership、broker、external DB和new security principal。

## 4. Owner and dependency boundary

```text
HTTP Interface
  -> Workspace/Preview Application use cases
       -> Workspace Domain + business repository ports
       -> capability public contracts
       -> Operation Runtime port
       -> ArtifactStore / Repository read ports

infrastructure
  -> SQLite UoW and repositories
  -> local ArtifactStore adapter
  -> Repository Client exact-commit read adapter
```

Domain不依赖FastAPI、sqlite3、Operation record、ArtifactStore path、Repository DTO或capability
implementation。Application只import capability public contracts。Operations只解释versioned job
payload/checkpoint envelope，不解释Workspace业务状态；Preview handler通过application port加载绑定。

## 5. Provisioned scope and authorization

每个命令先从当前session取得：

```text
actor_id
gateway_device_external_key
business_project_id
permissions
```

control-plane adapter必须把device/project解析到唯一active Repository，并返回当前
BaselineHead/BaselineNode。mapping缺失、disabled gateway、多active project或Baseline缺失均在
创建UploadRevision/Operation前fail closed。5A不调用CreateRepository。

Workspace upload必须exact匹配owner actor、device和project，并要求
`upload_submit_workspace`。Preview沿用相同exact scope。Workspace、Operation、PreviewResult和
bundle每次读取都重新检查当前session、mapping scope与permission；接受时授权不成为永久读票据。
session expiry不取消已接受Preview，disabled gateway也不取消已接受pure compute，但都阻止新
command和未授权读取。

## 6. Minimal business records

本节冻结语义字段，不冻结SQLite列名或HTTP拼写。

```text
Workspace
  workspace_id
  owner_actor_id
  gateway_device_external_key
  business_project_id
  repository_id
  state: OPEN | CLOSED
  generation
  current_upload_revision_id optional
  current_preview_result_id optional
  active_submit_attempt_id optional
  active_submission_id optional
  optimistic_version
  created_at / updated_at / closed_at optional

UploadRevision
  upload_revision_id
  workspace_id
  generation
  input_completeness: FULL | MODIFIED_ONLY
  source_artifacts by INITIAL | MODIFIED role
  source size/raw digest/provenance binding
  idempotency_key + request_fingerprint
  created_by / created_at

PreviewResult
  preview_result_id
  workspace_id + upload_revision_id + generation
  repository_id
  business_baseline_node_id + business_baseline_commit_id + Head version
  frozen ruleset/contract/provider versions
  source/input/snapshot/comparison/risk/surface/bundle digests
  bundle artifact ref + ready closure ref
  operation_id
  created_at
```

Workspace read-model labels可以派生`EMPTY | INPUT_READY | PREVIEW_READY`等展示状态，但这些不是
持久domain状态。Preview stale也按当前Head派生，不回写PreviewResult。

## 7. Commands and idempotency

5A公开以下逻辑use case；exact URL、header与JSON字段在S0 HTTP contract中冻结：

```text
CreateOrGetWorkspace
AcceptUpload
StartPreview
GetOperation
GetPreviewResult
ReadPreviewBundle
```

`CreateOrGetWorkspace`是mutation通则的唯一例外：不要求caller-generated idempotency key或
expected Workspace version。当前session解析出的exact actor/device/project scope是幂等identity；
数据库OPEN唯一约束裁决并发创建。唯一赢家创建并返回`201`，其余事务在unique conflict后重读
同一OPEN Workspace并返回`200`，不得产生第二个Workspace。

`AcceptUpload`要求Workspace expected version、idempotency key、mode和role map。fingerprint至少覆盖
Workspace/scope、expected version、mode、每个role的media type/size/raw digest及稳定admission
options。same key/same fingerprint返回原UploadRevision；same key/different fingerprint为409。
same bytes/new key创建新revision/generation，但ArtifactStore可以复用内容。

`StartPreview`要求Workspace expected version、exact upload revision/generation、expected
BaselineHead node/version、idempotency key和当前支持的preview options。fingerprint覆盖所有冻结
输入和版本。重放返回原operation_id；冲突返回409。

## 8. Upload admission and publication

Upload按bounded stream处理，不把请求整体载入内存。每个role至少验证：

- media type与压缩格式allowlist；
- compressed/uncompressed size、entry count、path length与总资源上限；
- incremental raw SHA和caller声明的size/digest；
- exactly required regular files、无duplicate/absolute/traversal path；
- 无symlink/hardlink/device/FIFO/extended filesystem metadata；
- server-owned artifact root、temporary staging和atomic publication；
- FULL恰有INITIAL/MODIFIED，MODIFIED_ONLY恰有MODIFIED。

所有role完成admission后，单一control DB事务创建UploadRevision、递增Workspace generation、设置
current input并清除current preview pointer。任何role失败、artifact publication失败或Workspace
CAS失败均不得留下部分revision。已发布但CAS失败的无引用bytes可由固定TTL cleanup处理。

Upload事务还把旧generation QUEUED Preview标记为`SUPERSEDED`，并对旧RUNNING Preview设置单调
cancel request；迟到worker仍由publish CAS阻断。Upload不创建自己的Operation。

## 9. Preview acceptance and frozen input

StartPreview在短事务内重新检查：

- exact Workspace scope、OPEN state和permission；
- current UploadRevision、generation和expected Workspace version；
- current provisioned Repository和BaselineHead node/version；
- input role closure、source artifacts存在且可读；
- idempotency fingerprint无冲突；
-静态JobDefinition/decoder/handler版本已注册。

成功后原子创建Operation和首个PENDING Step并返回`202 + operation_id`。Preview payload只保存稳定
业务ID、generation、frozen identity/version和artifact refs/digests；不保存host path、capability
object、callable或完整大payload。

## 10. JobDefinition and checkpoints

```text
job_kind: backend-vnext/preview
job_contract_version: backend-vnext/preview/v1

materialize_inputs
  -> assemble_preview
  -> publish_preview
```

`materialize_inputs`：

- 从immutable source artifact读取并解析SQL/source；
- 两种mode都按frozen Baseline CommitId执行Repository exact-commit reconstruction；
- FULL materialize Baseline、uploaded INITIAL和uploaded MODIFIED三侧；
- MODIFIED_ONLY materialize Baseline与uploaded MODIFIED，并将Baseline snapshot ref直接绑定为
  effective INITIAL，不复制第二份snapshot；
- 解析、required table/default pair、key/schema和hard resource failure使Step失败；
- 发布带side role/digest的Snapshot/Summary/Table artifacts；checkpoint对FULL闭合三侧，对
  MODIFIED_ONLY闭合Baseline/effective INITIAL与MODIFIED。

`assemble_preview`：

- FULL从三侧checkpoint构建`baseline_to_initial`和`initial_to_modified`两个directed pair，
  默认view为后者；
- MODIFIED_ONLY把baseline reconstruction绑定为effective INITIAL，并构建
  `initial_to_modified`主pair；
- 运行comparison、risk、surface和bundle public capabilities；
- required pair/table/bundle closure失败使Operation失败；
- owner声明的optional XML/ordered/risk enhancement可输出bounded diagnostics；
- 写完并回读全部immutable artifacts后设置READY closure checkpoint；FULL closure必须覆盖三侧
  input refs与两个pair，MODIFIED_ONLY必须覆盖Baseline/effective INITIAL、MODIFIED与主pair。

`publish_preview`：

- 重载transaction-fresh Workspace和BaselineHead；
- 校验generation/current revision、frozen baseline node/version和Operation lease/version；
- drift时发布Operation=`SUPERSEDED`，不创建PreviewResult；
- 无drift时原子创建一个PreviewResult、设置Workspace current pointer并terminal publish
  Operation=`SUCCEEDED`；
- 重放先返回既有matching PreviewResult，不产生第二个结果。

每个Step只有owner-defined最小checkpoint。capability/table级并行、cache hit和内部阶段只进入
bounded diagnostics，不成为Operation topology。

## 11. Cancellation, failure and stale semantics

- 新generation对QUEUED旧Preview直接supersede；RUNNING旧Preview只请求cooperative cancel。
- worker在reader batch、capability call和artifact publication前后检查ExecutionControl。
- 已被supersede的旧generation即使忽略/晚看到cancel，也无法通过Workspace generation CAS。
- 普通用户cancel只在安全checkpoint生效；terminal publication保持R1-R5既有CAS/lease规则。
- required failure不创建PreviewResult，也不回滚已接受UploadRevision。
- optional degradation可创建READY PreviewResult，但diagnostics必须bounded、typed且进入bundle closure。
- 发布后Baseline变化只使读取投影`derived_stale=true`；不修改Operation或PreviewResult，不自动重算。

## 12. Artifact lifecycle

UploadRevision metadata长期存在。current UploadRevision、current Preview和active SubmitAttempt需要的
source/snapshot/bundle artifacts被保护。5A只实现consumer所需的显式pin intent和保守固定TTL：

- current Preview full-row facts保持pin；
- 新current Preview发布后，旧且未被Submit接受的facts转为可清理cache material；
- superseded/failed/never-submitted大bytes在TTL后best-effort cleanup；
- active Operation、current Preview、active SubmitAttempt或manual recovery引用不得清理；
- cleanup failure只记录诊断并重试，不改写Preview/Operation事实；
- 不建立generic reference counting、tombstone、quarantine或GC状态机。

Submit在5B负责把source retention和SnapshotTableArtifact pin从Preview转移给Attempt；5A不得提前
模拟该事务。

## 13. HTTP and error boundary

HTTP DTO与domain record分离，拒绝unknown fields和scope/body冲突。同步command使用201/200，
Preview acceptance使用202，idempotency/version/binding conflict使用409，认证401、授权403、缺失
404、validation 422、size 413、media 415、admission 429、dependency/readiness 503。具体route和
stable code表由S0 HTTP contract拥有。

最低错误族必须覆盖：scope/mapping/baseline missing、Workspace version/current revision stale、
idempotency conflict、upload size/archive/path/role closure、Preview binding、required materialization/
pair/bundle closure、superseded、artifact unavailable和service not ready。错误使用owner-owned
`code/message/details?`，不引入generic FailureDescriptor。

Operation、PreviewResult和bundle response不得暴露host path、SQLite key、Repository bearer、
private ref、lease token或内部artifact directory。

## 14. Readiness and deployment applicability

Backend启动必须在开放HTTP前完成settings、control DB migration/integrity、artifact root和registry
检查。worker独立启动、恢复遗留Preview并发布worker health。Repository Service必须healthy，因为
MODIFIED_ONLY和FULL的baseline诊断都可能需要exact-commit read；暂时没有worker时Backend可以
保持进程健康但deployment不得宣称完整业务ready。

shutdown先关闭会创建Workspace/UploadRevision/Operation的新HTTP admission，再让worker按P4
规则drain/checkpoint。结果读取可以在admission关闭后继续，直到HTTP进程退出。

5A会触碰HTTP、settings/readiness、worker registry、SQLite migration和artifact volume接线，因而
最终候选必须重建Backend镜像并运行当前HEAD container/Compose gate。中间纯domain/capability
改动按比例化策略运行focused gate。

## 15. Verification matrix

| Barrier | Required evidence |
| --- | --- |
| Workspace/scope | OPEN uniqueness、cross-actor/device/project拒绝、mapping/baseline缺失 |
| Idempotency/CAS | same/same replay、same/different 409、expected version conflict、并发Upload |
| Upload safety | streaming size/hash、bomb/resource cap、path/link/root escape、role/file closure |
| Input modes | 两种mode均exact Baseline reconstruction；FULL三侧/双pair/default view；MODIFIED_ONLY复用Baseline为effective INITIAL；无initialize路径 |
| Operation | 三步registry/payload/checkpoint、restart/takeover、cancel/supersede、迟到writer fence |
| Correctness | existing snapshot/comparison/risk/surface/bundle golden及required failure closure |
| Drift | publication前Head/generation drift无结果；publication后derived stale且结果不变 |
| Artifacts | atomic publish、pin transfer seam、TTL eligibility、protected cleanup拒绝 |
| Authorization | accepted work可完成；每次result/bundle read重新授权；disabled gateway拒绝新工作 |
| Runtime | backend/worker readiness、shutdown order、DB reopen、registry mismatch fail closed |

测试命名按业务行为，不按轮次/finding编号；纯解析/校验不得引入Dolt fixture。fixed timeout、process、
signal和crash测试标`serial`；真实Repository/Dolt read标`integration`。最终执行使用仓库权威runner、
五包ruff/mypy和适用current-HEAD image gate。

## 16. S0 deliverables and exit

S0详细设计必须产出：

1. Workspace/UploadRevision/PreviewResult domain与application public contract；
2. HTTP route/DTO/error/permission表；
3. SQLite schema/migration和transaction/CAS矩阵；
4. ArtifactStore source upload/pin/TTL port及server-owned path规则；
5. Preview job payload、decoder、handler、checkpoint和READY closure版本；
6. capability composition和FULL/MODIFIED_ONLY bundle映射；
7. settings/readiness/bootstrap/worker composition与container applicability；
8. staged implementation plan、allowed paths、test owners、review和handoff格式。

S0 exit只允许把`p5_5a_design`标记为accepted。任何implementation authorization必须另行记录，
并要求P4-R6 exit=pass、当前candidate无未处理contract drift、明确的first implementation step和
适用验证命令。

## 17. Stop and reopen conditions

- device需要同时映射多个active business project；
- Upload必须解析SQL、创建Baseline、调用Repository写接口或合并Preview identity；
- 任一mode无法从frozen exact Baseline commit构建完整Baseline侧；
- Preview需要动态DAG、多个同时active Step或持久per-table workflow；
- required/optional failure边界无法由现有capability result与bundle closure表达；
- SQLite不能原子提交Workspace/Operation/Preview publication所需事实；
- 需要新service/principal、外部DB、broker、multi-worker HA或跨库事务；
- P4-R6发现会改变5A依赖的Operation/Step/worker/checkpoint契约。

当前下一动作是完成S0详细设计和execution plan；在P4-R6最终exit前不得开始实现。

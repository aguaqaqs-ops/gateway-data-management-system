# P5-5A 上传/预览执行计划

状态：**S0 独立 docs review 通过；设计已接受；当前仅有 docs-only 授权**

日期：2026-09-08

Owner：P5-5A Slice Lead（Workspace/Preview）

设计依据：[P5-5A Upload/Preview Detailed Design](p5-5a-upload-preview-design.md)

本计划是可执行顺序、审核和交接合同，不授权 source、test、migration、dependency、Docker、
Compose、settings 或 deployment 修改。只有 `p4_r6_exit: pass` 且明确记录
`p5_5a_implementation_authorized: yes` 后，才可进入 S1。后续可以仅用本文件各阶段的短提示词
推进，因为每一步都规定了上下文边界、允许路径、前置事实、动作顺序、测试 owner、退出证据和
独立审核点。

## 1. 入口门禁和固定边界

| 检查项 | 必须满足 |
| --- | --- |
| 当前 discussion head | `d7cb5b9c2c55e8f8b0814520e9d95c7df0ad00a5` |
| P4-R1 至 R5 | module gate 均为 `pass` |
| P4-R6 | exit `pending`；实现未授权 |
| P5 总体设计 | accepted |
| P5-5A baseline acceptance | pass |
| 5A-S0 entry brief | ready；S0 design accepted；独立review `pass_after_docs_only_remediation` |
| 当前阶段变更 | 仅 `docs/**`；禁止 `vnext/**` |

固定边界：single-host/single-worker SQLite/WAL；backend/worker 同镜像不同进程；独立
Repository Service；provisioned Baseline；Upload/Preview 独立 identity；固定三步
Preview JobDefinition；复用现有 capability public contracts；无真实 consumer 时不建
outbox/dispatcher。

## 2. 对话和上下文策略

### 2.1 S0 设计阶段

S0 与本轮 context hygiene 保持在同一对话，便于同时看到 authority 修订、旧文档处置和新增
设计。S0 结束后应开一个新的独立审核对话，避免实现讨论污染设计验收；审核对话只读
`docs/**` 和指定 contracts，不修改源码。

### 2.2 S1-S2 领域与持久化

S1 与 S2 建议使用同一实现对话：两者共享 Workspace/UploadRevision 语义和 transaction/CAS
矩阵，连续上下文能减少重复解释。若 S1 引入未预期的跨领域状态或 S2 需要改变语义 owner，
立即暂停并新开独立设计审核对话；修复后可回到实现对话继续，不把修复/复审另列为交付步骤。

### 2.3 S3 HTTP

S3 建议新开对话。HTTP DTO、权限和状态码容易把 DTO 细节反向写入 domain；新对话只载入本
计划、设计 §3、相关 contract 和 S1/S2 handoff 摘要。审核完成后，若仅是字段/测试修复可在
同一 S3 对话完成；若改变授权模型必须独立审核。

### 2.4 S4 JobDefinition 与 capability 组合

S4 建议新开对话，并只带入 P4 Operation/JobDefinition contract、设计 §6-7、S1-S3 handoff。
这样可避免把 HTTP 讨论带入 worker topology。固定 timeout、process、signal、crash 测试的
分类由独立审核确认；发现需要动态 DAG、per-table durable Step 或新 registry 时停止并 reopen。

### 2.5 S5 runtime/container

S5 必须新开对话。它涉及 settings、readiness、shutdown、Docker/Compose 和 image provenance，
与纯 domain 讨论隔离。只有在明确触碰 runtime boundary 后才申请 container gate；审核和修复
可以在该对话内完成，但最终镜像/源码树 provenance 必须由独立 reviewer 复核。

### 2.6 S6 最终验收

S6 新开独立验收对话，不沿用实现对话上下文。只读取各阶段 handoff、当前 HEAD、测试输出和
provenance；review 采用 findings-first。发现语义问题时 reopen owning contract，修复和复审
不作为新的 S-step，但必须在 S6 记录中闭合。

## 3. 阶段执行说明和短提示词

每一步都应先把“当前 HEAD、允许路径、上一阶段 handoff、授权值”贴入对话，然后使用下面
的短提示词。短提示词不能扩大 allowed paths；任何超出范围的动作先停下并提出 reopen。

### S0：冻结详细设计和检索边界（当前阶段）

前置：P5 三件套 accepted/ready；P4-R6 pending；工作区已有用户修改必须保留。

允许路径：`docs/backend-vnext/README.md`、`docs/backend-vnext/refactoring/formal/README.md`、
`architecture/architecture-and-refactoring-plan.md`、`contracts/{contract-taxonomy-and-ownership,
business-lifecycle-and-state,operation-lifecycle-and-integrity,external-effect-and-recovery,
canonical-storage-and-repository-boundary,repository-service}.md`、ADR 0012、P4 R4/R5 handoff、
P5 authority plans、P3 historical interpretation fence，以及本计划和设计文档。除现行authority
修正、默认入口与historical fence外不改写历史handoff。禁止source/test/migration/dependency/image。

操作顺序：读取指定 contracts -> 扫描旧术语和默认入口 -> 只修订现行 authority -> 给 legacy
增加 non-authoritative/historical 说明 -> 编写设计与本计划 -> 做 link/fence/diff/hash 检查。

测试/证据 owner：Architecture Acceptance；只运行 Markdown/link/path、术语、围栏和
`git diff --check` 检查，不运行 Python/Dolt/Docker。

独立审核：S0 完成后必须新开独立 docs review，确认无 positive old semantics、无第二 owner、
无架构扩展。若 findings 只涉及措辞，在本对话修复后由 reviewer 重扫；若改变 contract 语义，
reopen 对应 contract。

短提示词：

```text
按 P5-5A-S0 设计和执行计划执行 S0：只读并核对指定 formal contracts，
检查默认入口和旧术语，维护 legacy historical oracle，完善两份 5A 文档。
仅修改 docs/**，不得改 vnext/**。完成后给出链接、围栏、术语扫描、git diff --check、
当前 HEAD 和文档集 hash。
```

退出记录：记录 changed paths、authority 决定、历史文档保留清单、扫描命令/结果、当前
`p4_r6_exit` 和 `p5_5a_implementation_authorized`。

### S1：Workspace/Upload/Preview domain 与 application ports（需实现授权）

前置：S0 独立审核通过；P4-R6 exit 和 5A implementation authorization 均为 yes。

允许路径：`vnext/backend/src/gateway_backend/domain/**`、`application/**` 中 5A owner
范围及对应 focused unit tests。不得改 HTTP、migration、worker wiring 或 Repository write。

操作顺序：先实现 IdentityContext/scope 和 OPEN uniqueness；再实现 UploadRevision role closure、
idempotency fingerprint、generation CAS；最后实现 Preview frozen binding、derived stale 和
latest-generation-wins。domain 不依赖 FastAPI、sqlite、Operation record、ArtifactStore path 或
Repository DTO。

测试 owner：Workspace Domain（scope/generation）；Upload Application（role closure）；Preview
Application（binding/stale）。纯 parsing/validation 使用内存 fixture，禁止 Dolt fixture 或
`dolt init`。

阶段 gate：affected package focused/unit、ruff、mypy；检查 dependency direction 和 one-owner
matrix。固定 timeout/process 测试若出现，标记 `serial`。

建议对话：S1 可与 S2 同一实现对话；完成 S1 后保留短 handoff 摘要，不复制全部讨论。

短提示词：

```text
执行 P5-5A S1。只改允许的 domain/application 路径和行为测试。
实现 exact IdentityContext scope、OPEN Workspace uniqueness、UploadRevision role closure/
idempotency/generation CAS、Preview frozen binding 与 derived_stale。
不得加入 HTTP、migration、worker 或 Repository write。跑 affected unit、ruff、mypy，
按 handoff 模板报告 changed paths、owner、结果和未决问题。
```

退出记录：S1 handoff、测试结果、source-tree 摘要、deferred 是否触碰、是否需要 reopen。

### S2：SQLite transaction/CAS 与 ArtifactStore（需实现授权）

前置：S1 handoff 通过；语义矩阵未改变。

允许路径：5A-owned migration/repository、SQLite UoW、ArtifactStore adapter 和对应 tests。不得
建立 generic StateStore、refcount GC、tombstone、quarantine 或 outbox table。

操作顺序：按设计 transaction/CAS 矩阵落库；实现 bounded streaming、atomic publication、
read-back digest、pin intent、protected path refusal；验证 rollback、stale writer、duplicate
idempotency、TTL eligibility。artifact/capability I/O 不在 SQLite transaction 内。

测试 owner：Workspace persistence（CAS/rollback/idempotency）；ArtifactStore（stream、archive/
path/link/root、pin、TTL）。真实 Repository exact-commit read 才标 `integration`；纯解析/
校验保持 `unit` 且不创建 Dolt。

阶段 gate：focused unit/integration、migration review、ruff/mypy。只有触碰 image/runtime boundary
才触发 container gate。

建议对话：与 S1 保持同一实现对话；若 schema 需要新增未定义业务事实，暂停并新开独立
contract review。修复与复审在原阶段记录中闭合。

短提示词：

```text
执行 P5-5A S2。沿设计 §4 transaction/CAS 矩阵实现 5A-owned persistence 和 ArtifactStore。
只改允许路径；不得引入 generic StateStore、GC/tombstone/quarantine/outbox。
覆盖 atomic upload publish、digest read-back、pin/protected path、rollback、stale CAS、
same-key replay。纯解析/校验不要 Dolt。运行分类正确的 focused tests、ruff、mypy，
必要时做 migration review 并输出 handoff。
```

退出记录：migration/CAS 审核、artifact safety 证据、test owner 结果、是否触发 container gate。

### S3：HTTP DTO、状态码和授权（需实现授权）

前置：S1/S2 handoff 通过；domain/persistence contract 不变。

允许路径：5A HTTP interface、OpenAPI/DTO schemas 和 interface tests。DTO、domain record、
Operation payload、capability object 必须分离。

操作顺序：实现设计§3已冻结的route/DTO/status family，再接current-session/scope/permission检查，
最后覆盖idempotency/version/binding errors。验证`202 + operation_id`、`401/403/404/409/413/
415/422/429/503`、disabled gateway 拒绝新工作、session expiry 不取消 accepted compute、
每次 Operation/result/bundle read 重新授权。不得暴露 host path、bearer、lease token 或 SQLite
key。

测试 owner：HTTP Interface；application owner 提供 binding fixtures。运行 focused HTTP unit/
contract、ruff、mypy。

建议对话：必须新开 S3 对话；只带设计 §3 和 S1/S2 handoff 摘要。仅字段/测试修复可在同一
对话复审；改变 permission 或 scope 模型则独立审核并 reopen。

短提示词：

```text
执行 P5-5A S3。只改 5A HTTP/DTO/OpenAPI 和接口测试路径。
保持 DTO、domain、Operation payload、capability object 分离；实现设计 §3 已冻结的 route、DTO、
permission、状态码、exact scope、current-session re-authorization 和 202 operation response。
不得静默改名、增加 legacy alias 或把其余 deferred 细节提前冻结。跑 focused HTTP tests、
ruff、mypy，报告授权边界和错误矩阵。
```

退出记录：HTTP contract 摘要、错误/权限测试、deferred register、独立审核结论。

### S4：Preview JobDefinition、decoder、handler（需实现授权）

前置：S3 handoff 通过；P4 Operation Runtime contract 未改变。

允许路径：JobDefinition registry、versioned payload decoder、`materialize_inputs`、
`assemble_preview`、`publish_preview` handlers 和行为 tests。不得增加 dynamic DAG、per-table
durable Step 或第二 registry。

操作顺序：先实现closed payload/budget；再让两种mode都从frozen Baseline exact commit重建
Baseline snapshot并实现materialize/checkpoint；再组合existing Snapshot/Comparison/Risk/Surface/
Bundle；最后实现READY closure、publication CAS、supersede/cancel/late-writer fence。FULL闭合
Baseline/INITIAL/MODIFIED三侧并产生两个directed pair；MODIFIED_ONLY复用Baseline snapshot ref为
effective INITIAL并产生主pair。

测试 owner：JobDefinition owner（payload/两种mode的Baseline read/三侧或两侧checkpoint/READY）；capability owners（golden correctness）；
Preview Application（closure/publication）。fixed timeout/process/signal/crash 标 `serial`；
FULL和MODIFIED_ONLY的真实Repository exact-commit read均标`integration`。

建议对话：新开 S4 对话，只带 P4 runtime contract、设计 §6-7、S1-S3 handoff。若需要改变
Operation/Step/CAS 语义，停止实现并 reopen P4 owner。

短提示词：

```text
执行 P5-5A S4。只改 preview JobDefinition/decoder/handlers 和行为测试。
固定 topology 为 materialize_inputs -> assemble_preview -> publish_preview；
复用 P4 lease/checkpoint/CAS；两种mode都读取frozen Baseline exact commit；覆盖FULL三侧双pair、
MODIFIED_ONLY的Baseline/effective INITIAL ref复用、required/optional closure、READY、
supersede/cancel/stale publication。不得加入 dynamic DAG、per-table durable Step 或新 registry。
按 unit/integration/serial 分类运行测试、ruff、mypy，并输出 checkpoint/closure handoff。
```

退出记录：payload/decoder 版本、capability mapping、failure/stale 证据、测试分类和 reviewer 结论。

### S5：bootstrap、readiness、shutdown、container（需实现授权）

前置：S4 handoff 通过；只有实际触碰 runtime/image boundary 才继续本阶段。

允许路径：backend/worker bootstrap、settings/readiness、Docker/Compose harness（仅受影响范围）
及测试。启动必须校验 settings、DB integrity、artifact root、registry；worker recovery 完成后
才报告 health；HTTP admission 先关闭再 drain。

操作顺序：先完成 backend/worker readiness 接线；再验证 DB reopen、registry mismatch fail closed、
Repository dependency；最后验证 shutdown order、signal、protected artifact 和容器日志脱敏。
记录是否必须重建 current-HEAD image、source-tree hash 和 image digest。

测试 owner：Bootstrap/deployment owner；fixed lifecycle/process/signal 测试标 `serial`，
container gate 只在 boundary 变化时运行。

建议对话：必须新开 S5 对话。实现、独立审核、修复和复审可在该对话闭合，但 provenance 必须
由另一位 reviewer 复核；历史 P4 image 不能当 current-HEAD 证据。

短提示词：

```text
执行 P5-5A S5。只处理 5A 影响到的 bootstrap/settings/readiness/shutdown/container 边界。
验证 settings、SQLite integrity、artifact root、JobDefinition registry、worker recovery、
HTTP admission/drain、DB reopen 和日志脱敏。若触碰 image/Compose，按策略重建并记录
current HEAD、source-tree hash、image digest；否则明确 container gate deferred。输出独立审核
所需的 provenance。
```

退出记录：readiness/shutdown 证据、container applicability、镜像/source provenance、残余风险。

### S6：Slice acceptance 和 handoff（需实现授权）

前置：S1-S5 handoff 均通过或明确标记 not applicable；所有 reopen 已闭合。

允许路径：测试结果、handoff/acceptance docs 和必要的 finding-scoped 修复路径。最终候选才可
运行完整权威 runner；中间阶段不跑全量。

操作顺序：运行 5A focused/unit/integration/serial、五包 ruff/mypy 和受影响 container/Compose
gate；核对完整 journey、owner matrix、transaction/CAS、authorization、artifact protection、
capability mapping、readiness、deferred register；独立 reviewer 采用 findings-first；修复和
复审在 S6 记录闭合，不新增伪步骤。

测试 owner：各行为唯一 owner；Architecture Acceptance 汇总。最终执行使用
`./vnext/scripts/run-tests.sh`，但本轮 docs-only 不执行。

建议对话：新开独立验收对话，不沿用实现上下文。只载入 handoff、当前 HEAD、测试/静态输出和
provenance。任何语义变化 reopen owning contract。

短提示词：

```text
执行 P5-5A S6 acceptance。只依据各阶段 handoff 和当前 candidate 证据做 findings-first review。
核对 owner 唯一性、CAS/授权、FULL/MODIFIED_ONLY、READY/stale/supersede、artifact protection、
readiness、deferred/reopen 和 image/source provenance。列出 pass、finding、修复复审结果、
残余 gap、当前 HEAD 和 authorization；不要把验收写成实现授权。
```

退出记录：acceptance decision、findings/修复/复审、test matrix、source-tree/image provenance、
deferred/reopen register、下一阶段授权值。

## 4. 测试 owner 矩阵

| 行为 | 唯一 test owner | 分类 |
| --- | --- | --- |
| Workspace exact scope/OPEN uniqueness/generation | Workspace Domain | unit |
| Upload stream、archive/path/link/root、role closure | Upload Application + ArtifactStore | unit |
| Upload persistence/idempotency/CAS | Workspace persistence | unit/integration（SQLite only） |
| Baseline exact reconstruction | Repository read adapter + Preview Application | integration |
| FULL/MODIFIED_ONLY pair 和 bundle closure | Capability owners + Preview Application | unit/integration |
| Job payload/decoder/checkpoint/READY closure | JobDefinition owner | unit |
| Supersede/cancel/late writer/stale result | Preview Application | timing-sensitive 时 serial |
| Operation lease/takeover/retry | P4 Operation Runtime | serial/process |
| Current-session read authorization | HTTP Interface | unit/contract |
| Startup/readiness/shutdown/container | Bootstrap/deployment owner | serial/container |

测试按业务行为命名，不按 round/finding 编号；一个不变量不得因多层观察而重复设 owner。

## 5. Review 与 handoff 格式

每个阶段都记录：

```yaml
stage: S<n>
candidate_head: <git sha>
conversation_context: same | new | independent_review
scope_paths: [<allowed paths>]
changed_paths: [<actual paths>]
contract_owners: [<owner -> invariant>]
tests: {unit: <result>, integration: <result>, serial: <result>, static: <result>}
container: {required: <yes/no>, image_revision: <sha-or-null>, status: <pass/stale/not-run>}
review: {independent: <yes/no>, findings: [], remediation_retest: <pass/not-needed>}
deferred_touched: []
reopen_required: false
decision: pass | hold | reopen
```

最终 handoff 还要记录 source-tree hash、exact image digest、current HEAD、acceptance criteria、
残余 test gaps、deferred register 和 authorization 值。历史 P4 image 必须标为 historical，
不得宣称 current-HEAD gate。

## 6. Acceptance、reopen 和 deferred

Acceptance 必须满足设计文档 §9：Upload/Preview 分离；FULL/MODIFIED_ONLY 映射正确；
immutable PreviewResult 和 stale/latest-generation-wins 正确；当前授权在每次 read 生效；
ArtifactStore protected lifecycle 成立；readiness/shutdown 有证据；没有 forbidden mechanism
expansion。

Reopen 条件：P4-R6 改变 Operation/Step/JobDefinition/checkpoint/lease/CAS/readiness；mapping
允许多个 active project；Upload 创建 Repository/Baseline、解析 SQL或合并 identity；
MODIFIED_ONLY 无法 exact reconstruction；required/optional closure 无法表达；出现真实
consumer、broker、HA、external DB、second writer 或 new principal。

Deferred保持设计文档清单：SQLite names/indexes与query tuning、TTL/capacity数值、provider
tuning、History pagination、后续Slice DTO、legacy cutover、external consumer、HA/external DB。
5A route/DTO/permission/error family已由设计§3冻结。Deferred选择只能细化实现，不能改变
domain、consistency、authorization或Repository边界。

## 7. 当前状态

```yaml
current_head: d7cb5b9c2c55e8f8b0814520e9d95c7df0ad00a5
p4_r6_exit: pending
p5_5a_implementation_authorized: no
docs_only_changes_authorized: yes
source_test_dependency_migration_deployment_changes_authorized: no
container_gate: stale_from_prior_p4_context
```

本计划从属于 formal contracts 和 5A detailed design；不改写 P4/P3 historical handoff。授权后
下一动作是 S1，不是隐式开始实现。

## 8. S0 docs-only execution record

```yaml
stage: P5-5A-S0
candidate_head: d7cb5b9c2c55e8f8b0814520e9d95c7df0ad00a5
conversation_context: same
scope_paths: [docs/**]
changed_paths:
  - docs/backend-vnext/README.md
  - docs/backend-vnext/refactoring/formal/README.md
  - docs/backend-vnext/refactoring/formal/adr/0002-minimal-persisted-business-state.md
  - docs/backend-vnext/refactoring/formal/adr/0003-external-effect-reconciliation.md
  - docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md
  - docs/backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md
  - docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md
  - docs/backend-vnext/refactoring/formal/contracts/external-effect-and-recovery.md
  - docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
  - docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
  - docs/backend-vnext/refactoring/formal/plans/p4-active-context-index.md
  - docs/backend-vnext/refactoring/formal/plans/p4-durable-operation-runtime-design.md
  - docs/backend-vnext/refactoring/formal/plans/p4-durable-operation-runtime-execution-plan.md
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-retry-takeover-effect-recovery-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p4-r6-s0-entry-brief.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-baseline-acceptance.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-s0-entry-brief.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-upload-preview-design.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-upload-preview-execution-plan.md
  - docs/backend-vnext/refactoring/formal/plans/p5-business-vertical-slices-design.md
contract_audit: pass_read_only_no_reopen
default_entry: pass_p5_entry_triad_then_5a_design_and_execution_plan
legacy_historical_oracle: preserved_with_central_fence_and_p3_interpretation_fence
positive_old_semantics_in_current_authority: none
local_markdown_links: pass
markdown_fences: pass
git_diff_check: pass
non_document_change: none
python_dolt_static_container_tests: not_run_docs_only
candidate_document_set_sha256: abebdf8d099dfcc2ed0af236b185e4791e487c56c30e8ebec00397f746bc578c
document_set_hash_method: sorted_changed_docs_per_file_sha256_records_with_this_field_removed
p4_r6_exit: pending
p5_5a_implementation_authorized: no
independent_review: pass_after_docs_only_remediation
review_findings:
  - create_or_get_workspace_idempotency_and_version_exception_missing
  - full_baseline_materialization_and_three_side_closure_missing
remediation: applied_docs_only
remediation_retest: pass
decision: pass_design_accepted_implementation_blocked
```

Authority决定：Workspace/UploadRevision/PreviewResult继续由Business Lifecycle列出的domain/
application owner拥有；5A只拥有application composition与HTTP interface。Operation runtime、
Repository wire、capability和artifact envelope不被复制。5A是pure compute，不引入Repository
write、outbox/dispatcher、新service/principal、dynamic DAG或per-table durable Step。

历史保留清单为`docs/backend-vnext/{contracts/**,capabilities/**,flows.md,operations.md,
artifacts.md,identity-and-digests.md,implementation-boundary.md,modules.md}`及P3过程材料。它们保持
可达、可用于行为/fixture追溯，但不是P5入口；本轮不重写其历史正文。

文档集hash覆盖当前`git status --short`列出的全部changed/untracked `docs/**`文件。按path的
`LC_ALL=C`顺序，为每个文件计算SHA-256；仅从本文件输入流删除
`candidate_document_set_sha256:`字段，再对`<file-sha><two-spaces><path><newline>`记录流计算最终
SHA-256。该归一化避免hash字段自引用，且不忽略其他内容。

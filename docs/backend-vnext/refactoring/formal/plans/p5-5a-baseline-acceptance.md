# P5-5A Baseline Acceptance

状态：**PASS — DESIGN INPUTS CONVERGED; 5A slice exit pass（见 [P5-5A S6 Handoff](p5-5a-s6-handoff.md)）；historical input for 5B**

日期：2026-09-06

Owner：Backend vNext Architecture Acceptance

上游：[P5 Business Vertical Slices Design Baseline](p5-business-vertical-slices-design.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[P4-R6-S0 Entry Brief](p4-r6-s0-entry-brief.md)

入口：[P5-5A-S0 Entry Brief](p5-5a-s0-entry-brief.md)

## 1. Acceptance identity

```yaml
acceptance_kind: p5_5a_design_baseline
discussion_base_sha: d7cb5b9c2c55e8f8b0814520e9d95c7df0ad00a5
candidate_document_set_sha256: 627ab89acf4376991e7412bfbd76e5d0f0f7d7c8c84516cfd1cc21771da7d6f7
candidate_acceptance_record_excluded_from_hash: true
candidate_worktree: pre_existing_p4_document_changes_plus_p5_docs_only_candidate
source_code_changed: false
tests_changed: false
dependencies_changed: false
deployment_changed: false
p4_r1_through_r5: pass
p4_r6_exit: pending
p4_current_head_container_gate: stale
p5_design_baseline: accepted
p5_5a_baseline: pass
p5_5a_entry_brief: accepted
p5_5a_implementation_authorized: no
p5b_real_repository_effect_authorized: no
```

本验收只判断5A是否有足够且一致的设计输入，并确认可以进入S0详细设计。它不把用户批准的
docs工作解释为source implementation授权，也不覆盖P4-R6最终gate。候选开始前工作区已有P4
provenance/index文档修改和未跟踪P4-R6 brief；这些内容被保留，不作为5A实现证据。

候选文档集按以下固定顺序计算，排除本验收记录以避免自引用：

```bash
sha256sum \
  docs/backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md \
  docs/backend-vnext/refactoring/formal/contracts/external-effect-and-recovery.md \
  docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md \
  docs/backend-vnext/refactoring/formal/adr/0002-minimal-persisted-business-state.md \
  docs/backend-vnext/refactoring/formal/adr/0003-external-effect-reconciliation.md \
  docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md \
  docs/backend-vnext/refactoring/formal/plans/p4-durable-operation-runtime-design.md \
  docs/backend-vnext/refactoring/formal/plans/implementation-stages.md \
  docs/backend-vnext/refactoring/formal/plans/p5-business-vertical-slices-design.md \
  docs/backend-vnext/refactoring/formal/plans/p5-5a-s0-entry-brief.md \
  | sha256sum
```

## 2. Acceptance findings

### 2.1 Phase and authorization — PASS

P4 R1-R5已有module handoff；P4-R6是尚未完成的最终acceptance/integration gate，current-HEAD
container evidence仍stale。5A可以进行docs/interface/schema planning，但任何source、test、
migration、HTTP route、settings或deployment实现必须等待P4-R6 exit和明确授权。基线没有把设计
ready写成implementation ready。

### 2.2 Owner and architecture — PASS

Workspace/UploadRevision由Workspace Domain拥有；PreviewResult和command transaction由Workspace/
Preview Application拥有；Operation Runtime只执行稳定JobDefinition；capability owner继续拥有
snapshot/comparison/risk/surface/bundle语义；Repository Service只提供exact-commit read，不取得
Workspace、Preview或授权所有权。依赖方向无反转，也不需要新service或principal。

### 2.3 Scope and provisioning — PASS

IdentityContext、OPEN Workspace唯一键、一个device一个active project、control-plane mapping、
Repository/explicit-empty Baseline provisioning和历史identity freeze均已明确。5A在Baseline缺失时
fail closed，不承担CreateRepository或baseline initialization。

### 2.4 Upload boundary — PASS

Upload和Preview已拆为独立identity。Upload只做bounded stream、size/hash、archive/path/link、
required file与role closure admission，然后发布immutable UploadRevision；不解析SQL、不创建
Snapshot/Operation、不比较。same bytes/new key与artifact content reuse的边界明确。

### 2.5 Mode and capability composition — PASS

`FULL`绑定INITIAL+MODIFIED并产生`baseline_to_initial`与`initial_to_modified`；
`MODIFIED_ONLY`只上传MODIFIED，before侧来自frozen business Baseline exact-commit reconstruction。
用户可见`INITIALIZE_BASELINE`已删除。该映射可由现有Snapshot、Comparison、Risk、Surface和
Bundle public capabilities表达，不需要改变capability owner或持久per-table workflow。

### 2.6 Operation and publication — PASS

Preview固定三步`materialize_inputs -> assemble_preview -> publish_preview`，可使用现有P4
JobDefinition/checkpoint/READY closure、lease、retry、takeover、cancel与CAS机制。generation和
BaselineHead publication gate、latest-generation-wins、QUEUED supersede、RUNNING cooperative
cancel及迟到writer fencing均有单一owner。

### 2.7 Failure and result semantics — PASS

required source/table/default pair/bundle closure失败使Preview失败；optional XML/ordered/risk增强
可以产生bounded diagnostics，但不增加`READY_WITH_WARNINGS`。发布前drift无PreviewResult，
发布后drift只派生stale并由Submit拒绝；系统不自动重算。UploadRevision不因Preview失败回滚。

### 2.8 Authorization and retention — PASS

command acceptance使用当前session/scope/permission；accepted pure compute不因session expiry或
gateway disable被取消；每次Operation/result/bundle read重新授权。current Preview与active
Attempt artifacts受保护，成功Submission source长期保留，其余大bytes使用固定TTL；不需要generic
refcount/GC状态机。

### 2.9 Cross-slice consistency corrections — PASS

Repository技术`main`与业务BaselineHead已分离。Review不移动/清理ref；Archive直接引用既有
Submission commit并使用本地Head CAS，不再有ArchiveExecution/Repository effect。无真实event
consumer，因此outbox及其故障点已从P5 authority删除。这些修订不改变Repository Service V1 wire。

### 2.10 Verification and deployment applicability — PASS

S0已经列出domain/HTTP/schema/artifact/job/bootstrap设计交付物和行为级验证矩阵。5A实现预计触碰
HTTP、SQLite migration、worker registry、settings/readiness和artifact volume，因此最终candidate
必须重建current-HEAD image并运行container/Compose gate；本次docs-only acceptance无需运行
Python、Dolt、static或container测试。

## 3. Deferred details

以下内容不会改变5A核心架构，交由S0冻结：exact HTTP route/DTO字段、permission字符串、stable
error code表、SQLite列/index、固定TTL数值、resource cap默认值和staged implementation allowed
paths。History cursor、Review/Archive DTO、legacy cutover和capacity结果分别属于后续Slice或独立
gate，不阻塞5A详细设计。

## 4. Reopen conditions

- P4-R6改变Operation/Step、JobDefinition、checkpoint、worker或readiness contract；
- device需要同时映射多个active business project；
- 5A必须创建Baseline、执行Repository写入或合并Upload/Preview identity；
- MODIFIED_ONLY不能从exact Baseline commit完整重建before侧；
- 需要动态DAG、多个active Step、broker、外部DB、multi-worker HA或新principal；
- required/optional failure和READY closure无法由现有capability contract表达；
- current Preview/active Attempt的artifact保护无法在既有ArtifactStore trust model内实现。

## 5. Verification record

```yaml
review_kind: docs_and_contract_consistency
document_set_hash_recomputed: pass
local_markdown_links: pass
conflict_term_scan: pass_no_unresolved_current_authority_conflict
git_diff_check: pass
non_document_source_diff: empty
python_tests: not_run_docs_only
static_checks: not_run_docs_only
repository_dolt_tests: not_applicable
container_rebuild_required: no
container_reason: docs_only_design_and_acceptance
current_head_container_claim: none
benchmark: not_applicable_no_performance_claim
findings: []
```

验收使用权威文档、现有public capability/Operation contracts和当前Git状态做只读核对。
`git diff --check`、本地Markdown link/path检查、冲突词扫描、非文档source diff检查和候选文档
集hash复算均已通过；Ruby不可用后使用系统Perl完成等价的只读link检查，不影响结果。

## 6. Decision and next boundary

5A设计输入完整且无剩余架构级歧义，`p5_5a_baseline: pass`。允许按
[P5-5A-S0 Entry Brief](p5-5a-s0-entry-brief.md)继续HTTP/schema/application/job详细设计和execution
plan；P4-R6 exit前以及未取得明确授权时，`p5_5a_implementation_authorized`保持`no`。

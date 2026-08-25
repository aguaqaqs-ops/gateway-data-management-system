# P4-R4-S0 Independent Entry Acceptance

状态：**PASS — DESIGN AND EXECUTION PLAN ACCEPTED; S1a IMPLEMENTATION NOT AUTHORIZED**

日期：2026-08-25

Owner：Backend vNext Architecture Acceptance（independent acceptance context）

上游：[P4/R3 Worker Lifecycle Handoff](p4-r3-worker-lifecycle-handoff.md)、
[P4-R4-S0 Entry Brief](p4-r4-s0-entry-brief.md)、
[P4-R4 JobDefinition and Checkpoint Detailed Execution Plan](p4-r4-jobdefinition-checkpoint-execution-plan.md)、
[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)

## 1. Acceptance identity

```yaml
acceptance_kind: p4_r4_s0
step_id: P4-R4-S0
input_handoff_sha: 9ea535e138a7e498aeade69042bfbbff559fcfc0
input_validated_code_sha: acb3efca06a02aadaa5ce6d1e2a815e85d36e6af
reviewed_base_sha: 9ea535e138a7e498aeade69042bfbbff559fcfc0
reviewed_candidate_document_set_sha256: ebaf1e5bf27bee36d59706f1e9ab681583b1a9594ea2c4cb40aed8ba49768ac8
candidate_acceptance_record_excluded_from_hash: true
candidate_worktree: documentation_only_uncommitted_candidate_on_r3_handoff_tip
source_code_changed: false
tests_changed: false
dependencies_changed: false
deployment_changed: false
p4_r3_exit: pass
p4_r4_s0: accepted
p4_r4_design: accepted
p4_r4_execution_plan: accepted
p4_r4_s1a_authorized: no
p4_r4_implementation_authorized: no
accepted_registry: application_owned_immutable_process_local
accepted_registry_key: '(job_kind, step_name)'
accepted_payload_policy: strict_explicit_version_no_implicit_migration
accepted_checkpoint_authority: active_step_checkpoint_ref
accepted_artifact_port: existing_ArtifactStorePort_and_ArtifactRef
accepted_ready_policy: versioned_jcs_closure_set_once_after_ref_verification
accepted_successor_policy: static_explicit_single_successor_or_terminal
accepted_stub_policy: deterministic_test_only_no_real_repository_effect
focused_review_required: yes
conditional_remediation_step: yes
independent_review_required: yes
open_findings: []
next_step: P4-R4-S1a authorization discussion
next_step_authorized: no
next_input_sha: pending_r4_s0_documentation_commit
```

`pending_r4_s0_documentation_commit` 是本 docs-only candidate 尚未
封存时的 provenance 字段；candidate semantic hash 会在本记录排除自身后复算，文档封存提交
后必须回填 documentation SHA。它们不代表设计或实现 finding。

候选 semantic document set 按以下固定顺序计算；本 acceptance record、Active Context index
和 formal README 只负责状态/检索接线，明确排除以避免自引用或把索引当作设计语义 owner：

```bash
sha256sum \
  docs/backend-vnext/refactoring/formal/contracts/operation-lifecycle-and-integrity.md \
  docs/backend-vnext/refactoring/formal/contracts/external-effect-and-recovery.md \
  docs/backend-vnext/refactoring/formal/adr/0016-graceful-lifecycle-and-integrity-recovery.md \
  docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md \
  docs/backend-vnext/refactoring/formal/plans/p4-durable-operation-runtime-design.md \
  docs/backend-vnext/refactoring/formal/plans/p4-durable-operation-runtime-execution-plan.md \
  docs/backend-vnext/refactoring/formal/plans/p4-r3-worker-lifecycle-handoff.md \
  docs/backend-vnext/refactoring/formal/plans/p4-r4-s0-entry-brief.md \
  docs/backend-vnext/refactoring/formal/plans/p4-r4-jobdefinition-checkpoint-execution-plan.md \
  | sha256sum
```

复算结果为 `ebaf1e5b...49768ac8`。封存 docs-only commit 后，必须在不改变上述文件集合
语义的前提下回填提交 SHA；若集合或边界发生变化则重新进行 S0 acceptance。

## 2. Independent acceptance decisions

### 2.1 R3 boundary and owner split — PASS

R3 handoff 的 single-host/single-worker/local SQLite/WAL、R3 worker-local lifecycle、R3
`ClaimedExecutor`/`LeaseSession`、R5 recovery owner 和 P5 global/business owner 保持不变。
R4 只增加 application-owned JobDefinition/registry/decoder/synthetic consumer，不让
Operations import application implementation，也不改变 R1/R2 persisted semantics。

### 2.2 Registry and handler boundary — PASS

registry 在 boot 时 immutable、纯内存、有界 lookup；key 为 `(job_kind, step_name)`，payload
version 独立匹配；unknown runnable key/version 在 claim 前 fail closed 且无 durable mutation。
handler 通过 R3 executor/session adapter 接收 fresh records、control、session 和 artifact port；
无 dynamic closure、hot reload、network/filesystem discovery 或 transaction 内长计算。

### 2.3 Payload/checkpoint/artifact semantics — PASS

payload、checkpoint 和 READY closure 使用独立 owner/version 轴，decoder 只接受显式注册版本，
不做 implicit migration。R4 复用 `ArtifactStorePort`/`ArtifactRef` 的 exact size/raw digest
验证和 path-neutral identity；active Step checkpoint 是恢复权威，Operation checkpoint 不是普通
checkpoint 的第二写入目标。artifact-before-CAS、bounded orphan、no cleanup/evidence state
machine 边界已明确。

### 2.4 READY, successor and cancellation — PASS

R4-owned versioned JCS READY closure 在所有 refs 完整性验证后只设置一次。R4 只允许静态显式
single successor 或 terminal publication，不引入任意 DAG。effect boundary 前 cooperative
cancel 可发布 `CANCELLED`；request 已发送或 outcome unknown 时保留原 identity/checkpoint，
不伪造取消终局并交由 R5。

### 2.5 External-effect stub and test truthfulness — PASS

stub 是 deterministic test-only port，保持原 idempotency key/request ref 和稳定 operation ID，
可表达 accepted/unknown/confirmed；不连接 Repository/Dolt、不生成真实 effect、不作 retry/reconcile/
takeover 决策。测试只能宣称 R4 contract/stub evidence，不能宣称 production integration。

### 2.6 Step split and conversation isolation — PASS

S1a registry contract、S1b decoder、S2a checkpoint/closure、S2b composition、S3a pure compute、
S3b effect stub、S3c fault matrix 分属独立 context package；S4 focused review、条件式 S5、
独立 S6 和 current-HEAD S7 均保留。S0/S4/S6/S7 强制新对话，code step 默认新对话；短提示词
可以只引用 named step，不要求用户在提示词中重复执行内容。

### 2.7 Test and container applicability — PASS

纯 parser/registry/fake store 为 unit；on-disk artifact/reopen 为 integration；固定 timeout、
crash、signal、process 为 serial。S2b 触碰 worker bootstrap，因此 S7 需要 current-HEAD image
重建和 synthetic worker container smoke；R4 不运行 Dolt/Repository integration。

## 3. Acceptance checklist

| Gate | Result | Evidence / condition |
|---|---|---|
| R3 handoff identity | PASS | input `9ea535e`; validated code `acb3efc` remains ancestor |
| R3 source/test boundary | PASS | current candidate is documentation-only relative to R3 source/test tip |
| JobDefinition owner | PASS | application-owned; no Operations/application reverse import |
| Registry lifecycle | PASS | immutable process-local registry; no durable lookup/hot reload |
| Payload/version policy | PASS | explicit version decoder; unknown version fail closed; no implicit migration |
| Artifact boundary | PASS | existing `ArtifactStorePort`/`ArtifactRef`; path-neutral exact digest validation |
| Checkpoint authority | PASS | active Step checkpoint is authoritative; no ordinary Operation same-status mutation |
| READY closure | PASS | versioned JCS refs/digests; set once after complete verification |
| Successor/final policy | PASS | static single successor or terminal; no DAG/fan-out |
| Cancel/effect boundary | PASS | before request may cancel; after request preserves identity for R5 |
| External stub truthfulness | PASS | deterministic test-only stub; no real Repository effect |
| Orphan artifact handling | PASS | bounded/idempotent temporary handling; no cleanup/evidence state machine |
| Step split | PASS | S1a-S3c plus S4/S5/S6/S7 have distinct owners and outputs |
| Conversation strategy | PASS | mandatory new conversations recorded for S0/S4/S6/S7 |
| Test marker strategy | PASS | unit/integration/serial owner and no Dolt misuse defined |
| Container applicability | PASS | S2b trigger recorded; final current-HEAD rebuild owned by S7 |
| Open architecture findings | PASS | none |
| S1a implementation authorization | NO | requires separate explicit authorization after S0 seal |

## 4. Deferred register

- R4 exact Python signatures, JCS key order and synthetic payload fixture values：S1a-S3a；
- retry/backoff, expired RUNNING disposition, takeover and unknown effect reconcile：R5；
- business T1/T3, HTTP/global readiness, Compose and real Repository/Dolt integration：P5/P5B；
- terminal retention/GC/backup、orphan artifact retention和正式容量 baseline：后续真实 consumer；
- multi-worker/HA/external DB、dynamic DAG/fan-out、durable worker membership：architecture reopen。

## 5. Reopen conditions

任何下列需求都必须 reopen R4 owner 或上游 contract：

- 修改 R1 record/status/transition、R2 schema/store/CAS/error taxonomy；
- 引入 dynamic registry/hot reload、任意 DAG、多 executor、IPC、sidecar、新 principal；
- 将 handler、decoder、artifact/network I/O 或长计算放入 DB transaction；
- 在 request sent/unknown outcome 后生成新 idempotency key 或伪造 `CANCELLED`；
- 把 stub、synthetic process 或旧 image 证据表述为 production Repository validation；
- 为 orphan artifact 建立 cleanup/quarantine/evidence 状态机；
- 新增无法由现有 unit/integration/serial/container markers 表达的高风险边界。

## 6. Verification and applicability

本 acceptance 是 docs-only；不运行 Python、Dolt、Repository、artifact process 或 container gate。
只执行 provenance、source/test drift、文档目标和 whitespace checks：

```text
git merge-base --is-ancestor 9ea535e138a7e498aeade69042bfbbff559fcfc0 HEAD
  -> pass (HEAD=9ea535e138a7e498aeade69042bfbbff559fcfc0)
git diff --name-only 9ea535e138a7e498aeade69042bfbbff559fcfc0..HEAD -- vnext/backend/src vnext/backend/tests
  -> empty
git diff --name-only -- vnext/backend/src vnext/backend/tests
  -> empty
find vnext/backend/src vnext/backend/tests -type f -name '*.py' -print0 | sort -z | xargs -0 sha256sum | sha256sum
  -> 26994ad239969afb95556c03d9f03590837a98ac3148f3a9d70d835241370146
R4 local document target existence check
  -> pass
git diff --check plus new-document trailing-whitespace check
  -> pass
candidate semantic document set SHA256 (fixed command above)
  -> ebaf1e5bf27bee36d59706f1e9ab681583b1a9594ea2c4cb40aed8ba49768ac8
```

```yaml
container_rebuild_required: no
container_reason: docs_only_r4_s0_entry_acceptance
last_verified_image_revision: sha256:f461fc3ec5347e3779edbdc0c041ba15af9b2cc79c007e525f7844d3815abaaf
container_gate: not_applicable_for_s0
python_tests: not_run_by_s0_plan
five_package_static: not_run_by_s0_plan
benchmark: not_applicable_no_performance_claim
```

R3 image revision只作为上游 provenance，不覆盖任何 R4 source；R4 S7 必须按当前 HEAD 重新
运行适用 gates 和 container smoke。

## 7. Decision

`p4_r4_s0: accepted` 表示 R4 JobDefinition/Checkpoint 设计与详细 execution plan 已收敛，
可以开始 S1a authorization discussion。它不表示 R4 source/tests/bootstrap 已实现，也不
授权 R4/R5/P5 implementation 或真实 Repository effect。下一步必须是单独授权后的：

```text
在新对话执行 P4-R4-S1a，按 detailed execution plan 完成 registry contract 与 focused gates，
不开始 S1b。
```

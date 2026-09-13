# P5-5B-S0 Independent Docs Review

状态：**CHANGES REQUIRED — design not accepted; implementation remains unauthorized**

日期：2026-09-13

Owner：Independent Architecture Review

评审对象：[P5-5B Submit/Finalize Detailed Design](p5-5b-submit-finalize-design.md)、
[P5-5B Submit/Finalize Execution Plan](p5-5b-submit-finalize-execution-plan.md)

权威输入：[P5-5B-S0 Entry Brief](p5-5b-s0-entry-brief.md)、
[P5 Business Vertical Slices Design Baseline](p5-business-vertical-slices-design.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[Repository Service](../contracts/repository-service.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[P4/R5 Retry, Takeover and Effect Recovery Handoff](p4-r5-retry-takeover-effect-recovery-handoff.md)、
[P4-R5-S2c Handoff](p4-r5-s2c-handoff.md)、
[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)、
[Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)

```yaml
stage: P5-5B-S0-independent-docs-review
candidate_head: 7e8cea7b3454a8cfdd7c2ba880becee5c427a0de
candidate_worktree: two_untracked_docs_on_clean_candidate_head
conversation_context: independent_docs_review
reviewed_documents:
  - path: docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md
    sha256: 07a527acb65e98221fb78be6a13698da21fcb9e6a09a2d0bc9ddd153ee19be8f
  - path: docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md
    sha256: 862edd7573a10039273af61aa9000af02512b20af8b51bbf1e50622bc0da242a
review_scope: docs_only
source_or_test_change_authorized: false
p4_r6_exit: pending
p5_5b_design: changes_required
p5_5b_implementation_authorized: no
p5b_real_repository_effect_authorized: no
decision: changes_required
findings: [S0-F1, S0-F2, S0-F3]
next_step: finding_scoped_docs_remediation_then_new_independent_review
next_step_authorized: docs_only_within_s0_allowed_paths
```

## 1. Decision

两份 candidate 已覆盖 Submit 的主要 owner map、T1/T2/T3、四态、Repository
`SubmitVersionedImport` path/body/header、artifact nominal boundary、current-session read
authorization、部署适用性与分阶段 test owner。Repository wire 未发现扩展，P4-R6 仍正确保持为
pending，两项 implementation authority 也保持为 `no`。

但当前 candidate 不能标记 `p5_5b_design: accepted`。以下三个 finding 会分别改变 Attempt 是否可
释放、operator command 是否可由现有 P4 runtime 执行，以及 manual-recovery HTTP 是否具有可实现且
可验证的安全边界。它们不是措辞建议，必须先做 finding-scoped docs remediation，再由新的独立
conversation/context 复核。

## 2. Findings

### S0-F1 — P1: `PRE_REQUEST` 不能作为 `ABORTED` 的充分证明

**Authority：** [External Effect and Recovery §2](../contracts/external-effect-and-recovery.md) 只允许
matching Repository Operation 以 `IMPORT_REJECTED`、`EXPECTED_COMMIT_MISMATCH` 或
`VERIFICATION_FAILED_NOT_PUBLISHED` 终止后把 Attempt 转为 `ABORTED`；同 contract §5 要求请求可能
已被接受时只按原 operation identity reconcile。[Business Lifecycle and State §3](../contracts/business-lifecycle-and-state.md)
同样把 `ABORTED` 定义为 Repository stable outcome 已证明未发布。

**Candidate conflict：** detailed design §8.3 明确说明 `request_sent=false` 只代表 operation identity
尚未 durable 捕获，**不能证明网络没有收到请求**；但 §10.3/§11 又允许
`ABORT_CONFIRMED_FAILURE` 以 durable `PRE_REQUEST/NOT_PUBLISHED` evidence 执行同一 abort
transaction。把 `PRE_REQUEST` 与 `NOT_PUBLISHED` 并列为可释放证据，会允许在 response loss 后把
可能已被 Repository 接受的 Attempt 标成 `ABORTED`，随后新 Attempt 可推进同一业务 scope。

**Business consequence / risk：** Class A。可能在原 import 最终发布的同时释放 Workspace/repository
occupancy并接受第二次 Submit，破坏 exactly-one business result、serialization 和 evidence-first
recovery。

**Required remediation：** 二选一：

1. 保持现有 owning contract，删除 `PRE_REQUEST` 作为 abort 证明；明确
   `ABORT_CONFIRMED_FAILURE` 只有在 matching Repository stable failure，或由 owning contract 已
   接受的等价 `NOT_PUBLISHED` 事实存在时才可释放。response loss/identity 未捕获必须复用原 key/body
   取回原 operation identity，不能 abort；或
2. 若确需让无 Repository Operation 的 deterministic pre-request failure 进入 `ABORTED`，先 reopen
   External Effect/Business Lifecycle owner，冻结新的终止 authority 与 proof shape，再更新 5B。

**Allowed remediation paths：** 两份 5B candidate；若选择方案 2，则必须先取得 owning contract reopen
authority，本 S0 review 不授权修改 contract。

**Unique test owner after remediation：** `test_submit_transactions.py` 负责允许的 abort transaction；
`test_submit_recovery.py` 负责 response-loss/unknown-outcome 不释放 occupancy 的反例。

### S0-F2 — P1: internal recovery HTTP contract 未冻结

**Authority：** [P5 Business Vertical Slices Design §10](p5-business-vertical-slices-design.md) 与
[P5-5B-S0 Entry Brief §11](p5-5b-s0-entry-brief.md) 要求部署内部 admin HTTP 复用既有 internal bearer，
只暴露三条 operator command，并携带 Operation/Step expected versions 与 bounded reason。P4-R5-S2c
只交付了 in-process command/CAS port，明确把 HTTP 与 authorization wiring 留给 P5。

**Candidate gap：** detailed design §5 的 HTTP contract 只冻结终端用户的 Accept/Get 四条 route；
§11 只列 command 名和抽象约束，没有 admin route、closed request/response DTO、bearer 失败语义、
Operation/Step path/body identity matching、success/replay/conflict status 或 stable error mapping。
Execution plan S4 也没有把 admin command HTTP 列为 deliverable，§4 没有独立的 admin auth/closed-wire
test owner；当前 `operator commands and MANUAL occupancy retention` integration owner 只覆盖 runtime
语义，不能替代 HTTP/auth owner。

**Business consequence / risk：** Class A/B。manual-recovery Attempt 可能没有可操作的生产入口，或实现
阶段自行发明 route/auth/error，造成未授权恢复、跨 Operation/Step 操作或永久占用。S0 宣称已交付
HTTP route/DTO/error/permission 表与 admin boundary，因此不能延后到实现时决定。

**Required remediation：** 在 detailed design 冻结一个最小 internal recovery endpoint：exact method/
route、bearer authority、closed request/response、path/body identity closure、expected-version CAS、
command capability guard、status/error/redaction 和 idempotent replay。Execution plan 必须为其指定 S4/S5
owner、allowed production/test paths、focused gate 与唯一 HTTP/auth test owner；runtime business effect
仍由 `test_submit_recovery.py` 拥有，不复制。

**Allowed remediation paths：** 两份 5B candidate。

**Unique test owner after remediation：** 新增或明确一个 admin recovery HTTP/auth owner file；
`test_submit_recovery.py` 只保留 command 到 business terminal/occupancy 的 integration owner。

### S0-F3 — P1: operator command capability guard 与 sealed P4 runtime 不一致

**Authority：** [P4-R5-S2c Handoff §1](p4-r5-s2c-handoff.md) 冻结：
`RESUME_RECONCILE` 只允许 `EXTERNAL_EFFECT`，`RETRY_FROM_CHECKPOINT` 只允许
`PURE_RECOMPUTE`，`ABORT_CONFIRMED_FAILURE` 才是任意 capability 的受控终止命令。当前 runtime
`authorize_operator_command` 也按该矩阵 fail closed。

**Candidate conflict：** detailed design §11 把 `RETRY_FROM_CHECKPOINT` 描述为在原
request/package/key identity 下继续，没有限定它只能作用于 `prepare_import` 的
`PURE_RECOMPUTE` Step；而 §8.1 已把 `submit_import`、`await_import_result` 定义为
`EXTERNAL_EFFECT`。这会让 S4/S5 implementation 面临两种互斥解释：按文档对 external step 发
`RETRY_FROM_CHECKPOINT` 会被 P4 拒绝；放宽 P4 guard 又违反 execution plan 对 `operations/**` 与
`application/recovery.py` 的禁止修改边界。

**Business consequence / risk：** Class B，并保护 Class A effect。错误映射会使恢复命令稳定失败；若
为使其工作而绕过 capability guard，则可能把 unknown external outcome 当作 pure retry，违反
no-blind-replay。

**Required remediation：** 在 design 的 admin/recovery matrix 逐 Step 冻结：
`prepare_import(PURE_RECOMPUTE) -> RETRY_FROM_CHECKPOINT`；
`submit_import/await_import_result(EXTERNAL_EFFECT) -> RESUME_RECONCILE`；
`ABORT_CONFIRMED_FAILURE` 仍受 S0-F1 的 business proof guard。Execution plan 与 test owner matrix
必须显式验证错误 command/capability 组合 fail closed，不修改 P4 guard。

**Allowed remediation paths：** 两份 5B candidate。

**Unique test owner after remediation：** admin recovery HTTP owner验证 wire/capability rejection；
`test_submit_recovery.py` 验证 external step 只 reconcile 原 identity。

## 3. Reviewed boundaries without findings

| Boundary | Result |
| --- | --- |
| Owner/dependency direction | pass；Submission、Workspace、Operation、Storage Projection、Repository owner 未重复 |
| T1/T2/T3 and four-state skeleton | pass except S0-F1 |
| Repository upload/import/ref/get-operation mapping | pass；body/path RepositoryId、header-only key、fixed policy 与 public DTO 一致 |
| Artifact authority and nominal refs | pass；Backend/Repository refs 分离，manifest/source/Dolt 长期 authority 未转移 |
| Job topology/checkpoint/version budgets | pass except S0-F3；固定三步、closed document、64 KiB/ref budgets 已保留 |
| Read authorization/redaction | pass；每次 current-session re-authorization，未暴露 path/token/private refs |
| Deployment/trust boundary | pass；single-host/single-worker、无新 UID/helper/broker，final current-HEAD image gate 未被豁免 |
| Authorization gate | pass；P4-R6 pending，implementation/effect authority 仍为 no |
| Test owner matrix | pass except S0-F2/S0-F3 的 admin wire/guard owner 缺口 |

## 4. Verification record

```yaml
authority_and_contract_read: pass
repository_wire_comparison: pass
p4_operator_capability_comparison: fail_findings_S0-F2_S0-F3
business_abort_authority_comparison: fail_finding_S0-F1
local_markdown_links: pass
markdown_fences: pass
candidate_diff_whitespace: pass
non_document_source_diff: empty
python_tests: not_run_docs_only
static_checks: not_run_docs_only
repository_dolt_tests: not_applicable_docs_only
container_rebuild_required: no
container_reason: docs_only_independent_review
current_head_container_claim: none
```

检查基于 HEAD `7e8cea7b3454a8cfdd7c2ba880becee5c427a0de` 加两份未跟踪 candidate 的 exact
bytes。两份 candidate 的 local Markdown links、fence parity 与 whitespace check 通过；除三份
P5-5B docs 外没有 source/test/dependency/deployment 改动。本 review 没有运行 Python、Dolt、static
或 container gate，也不引用历史 image 作为当前 candidate 证据。

## 5. Next boundary

当前只允许在 S0 allowed paths 内做 S0-F1～F3 的 docs remediation。Remediation 必须同时更新 detailed
design 与 execution plan，避免 design/plan 分叉；完成后由新的独立 conversation/context 重新核对
exact document hashes、三项 closure、Repository wire 和 authorization gate。

本记录不授权 source、test、migration、dependency、HTTP route、settings、Docker、Compose、
deployment 或 git commit；`p5_5b_implementation_authorized` 与
`p5b_real_repository_effect_authorized` 均保持 `no`。

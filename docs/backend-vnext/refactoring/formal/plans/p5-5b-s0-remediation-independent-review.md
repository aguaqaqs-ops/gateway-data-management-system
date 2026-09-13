# P5-5B-S0 Remediation Independent Docs Review

状态：**PASS — design accepted; implementation remains unauthorized**

日期：2026-09-13

Owner：Independent Architecture Review

评审对象：[P5-5B Submit/Finalize Detailed Design](p5-5b-submit-finalize-design.md)、
[P5-5B Submit/Finalize Execution Plan](p5-5b-submit-finalize-execution-plan.md)

Finding 输入：[P5-5B-S0 Independent Docs Review](p5-5b-s0-independent-docs-review.md)

权威输入：[P5-5B-S0 Entry Brief](p5-5b-s0-entry-brief.md)、
[P5 Business Vertical Slices Design Baseline](p5-business-vertical-slices-design.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[Repository Service](../contracts/repository-service.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[P4-R5-S2c Handoff](p4-r5-s2c-handoff.md)、
[Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)

```yaml
stage: P5-5B-S0-remediation-independent-docs-review
candidate_head: 7e8cea7b3454a8cfdd7c2ba880becee5c427a0de
conversation_context: new_independent_docs_review
reviewed_documents:
  - path: docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md
    sha256: cea677c677aca91fd27f96522fb1e403af01e3869778c2789183d3d70df2ee9a
  - path: docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md
    sha256: e91db136ef675afc6d99ee82ff383fe71f318c774808447141c5eff8360ae2b3
review_scope: docs_only
source_or_test_change_authorized: false
p4_r6_exit: pending
p5_5b_design: accepted
p5_5b_implementation_authorized: no
p5b_real_repository_effect_authorized: no
decision: pass
findings_closed: [S0-F1, S0-F2, S0-F3]
new_findings: []
next_step: wait_for_p4_r6_exit_and_explicit_implementation_authority
```

## 1. Decision

对上述 exact bytes 的 finding-scoped remediation 复审通过。S0-F1 至 S0-F3 已闭合，未发现新的
Contract、Repository wire、P4 recovery capability、test-owner 或 deployment/trust-boundary
finding。P5-5B detailed design 可记录为 `accepted`。

本结论只接受设计，不授权实现。P4-R6 exit 仍为 `pending`；在 execution plan 的完整 entry gate
明确记录为 pass/yes 前，`vnext/**`、测试、migration、HTTP route、settings、image、Compose 和真实
Repository effect 均不得开始。

## 2. Finding closure

### S0-F1 — closed

Detailed design §10.3 已删除 `PRE_REQUEST` 作为 abort proof。只有已持久
RepositoryOperationId 的 matching Repository FAILED result，且 stable code 是
`IMPORT_REJECTED`、`EXPECTED_COMMIT_MISMATCH` 或
`VERIFICATION_FAILED_NOT_PUBLISHED`，才能执行 business abort 并释放 occupancy。

`request_sent=false`、未捕获 operation identity、pre-request deterministic failure、artifact 丢失、
response loss 或矛盾 evidence 均保留 occupancy，并通过原 body/header/key 取回 identity 或进入
manual recovery。P4 records 先变为 FAILED、business abort 尚未提交时发生的 crash 也不会提前释放；
terminal replay 继续幂等收口后半段。

Unique owners 保持分离：`test_submit_transactions.py` 证明 matching stable abort transaction；
`test_submit_recovery.py` 证明 unknown outcome 不释放及中间 crash/replay。

### S0-F2 — closed

Detailed design §5.4 已冻结唯一 Submit-only internal recovery endpoint：

```text
POST /internal/v1/operations/{operation_id}/steps/{step_id}/recovery
```

它复用 existing deployment internal bearer，request/response 均为 closed DTO，并冻结 path/body
identity、Step ownership、Submit job identity、Operation/Step expected-version CAS、capability guard、
success/replay/conflict status、stable error mapping 和 redaction。它不建立新 principal、permission
registry、idempotency ledger 或 recovery protocol。

Execution plan S4 已列出 route/schema/orchestration/auth/error/wiring production paths、
`test_operator_recovery_http.py`、focused unit gate 和 OpenAPI closure；S5 负责真实 command-to-business
effect 与 Repository evidence。HTTP/auth assertions 与 business recovery assertions 没有重复 owner。

### S0-F3 — closed

Detailed design §11 和 execution plan S5 与 sealed P4 matrix 一致：

| Submit Step | Capability | Allowed resume command |
| --- | --- | --- |
| `prepare_import` | `PURE_RECOMPUTE` | `RETRY_FROM_CHECKPOINT` |
| `submit_import` | `EXTERNAL_EFFECT` | `RESUME_RECONCILE` |
| `await_import_result` | `EXTERNAL_EFFECT` | `RESUME_RECONCILE` |

错误 command/capability 组合稳定返回 `RECOVERY_CAPABILITY_CONFLICT`，P4 core files 和
`application/recovery.py` 仍禁止修改。`ABORT_CONFIRMED_FAILURE` 虽由 P4 对任意 capability 支持，
但 5B 额外执行 S0-F1 的 matching Repository stable-failure business proof guard。

## 3. Re-reviewed boundaries

| Boundary | Result |
| --- | --- |
| Owner/dependency direction | pass；Submission、Workspace、Operation、Storage Projection、Repository owner 未重复 |
| T1/T2/T3 and four-state skeleton | pass；abort authority 与 owning contracts 一致 |
| Repository wire | pass；upload/import/get-operation/resolve-ref 无扩展，import path/body/header 与 public DTO 一致 |
| Artifact authority and nominal refs | pass；Backend/Repository refs 分离，长期 authority 未转移 |
| Job topology/checkpoints | pass；固定三步、closed versioned documents、P4 budgets 不变 |
| P4 recovery | pass；逐 Step capability、expected-version CAS、terminal abort replay 均未绕过 sealed guard |
| Internal recovery HTTP | pass；route/auth/DTO/identity/status/error/redaction/replay 与分阶段 owner 完整 |
| Read authorization/redaction | pass；current-session re-authorization 与 internal secret redaction 分离 |
| Deployment/trust boundary | pass；single-host/single-worker，无新 UID/helper/broker/principal |
| Test owner matrix | pass；HTTP adapter、business transaction/recovery 与 P4 core owner 分离 |
| Authorization gate | pass；P4-R6 pending，implementation/effect authority 均保持 `no` |

## 4. Verification record

```yaml
authority_and_contract_read: pass
finding_closure_S0_F1: pass
finding_closure_S0_F2: pass
finding_closure_S0_F3: pass
repository_wire_comparison: pass
p4_operator_capability_comparison: pass
local_markdown_links: pass
markdown_fences: pass
candidate_diff_whitespace: pass
tracked_source_or_test_diff: empty
python_tests: not_run_docs_only
static_checks: not_run_docs_only
repository_dolt_tests: not_applicable_docs_only
container_rebuild_required: no
container_reason: docs_only_independent_review
current_head_container_claim: none
```

检查基于 HEAD `7e8cea7b3454a8cfdd7c2ba880becee5c427a0de` 加未跟踪 P5-5B docs 的 exact
bytes。Markdown local links、fence parity、`git diff --check` 和两份 candidate 的 no-index
whitespace 检查通过。本 review 未运行 Python、Dolt、static 或 container gate，也不以历史 image
作为当前 candidate 证据。

## 5. Next boundary

本 review 关闭 S0 docs findings 并接受 design，但不能推出 P4-R6 exit 或 P5-5B implementation
authority。开始 S1 前仍须在同一 current HEAD 明确记录：

```yaml
p4_r6_exit: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
p5b_real_repository_effect_authorized: yes
unresolved_contract_drift: none
first_authorized_step: P5-5B-S1
```

缺任一项时只允许 docs/authority 工作；本记录不授权 source、test、migration、dependency、HTTP、
settings、Docker、Compose、deployment、git commit 或真实 Repository effect。

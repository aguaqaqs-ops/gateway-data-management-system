# P5-5B-S8 Independent Slice Exit Acceptance

状态：**PASS — `p5_5b_slice_exit: pass`**

日期：2026-09-18

Owner：Backend vNext Architecture Acceptance（independent acceptance context）

上游：[P5-5B Submit/Finalize Execution Plan](p5-5b-submit-finalize-execution-plan.md)、
[P5-5B-S7 Independent Review 8](p5-5b-s7-independent-review-8.md)、
[P5-5B-S8 Handoff](p5-5b-s8-handoff.md)、
[P5-5B-S8 Independent Review 1](p5-5b-s8-independent-review-1.md)

```yaml
acceptance_kind: p5_5b_s8_slice_exit
conversation_context: independent_acceptance
acceptance_authority: explicit_repository_owner_authorization
acceptance_target_tip: 1bff2970bc7ff22179aa644426b5b1a9aca0a18e
gate_tested_head: 460d6f5b1efdb24199534778bd5cc9d4a8131d13
container_gate_head: 87c497634e4f6417de7fbb46b42086fd61af9031
implementation_seal: e5c43c0c9f71de3cd2e602504ec9034f16add8af
s7_f2_remediation_seal: 4d1dc010deff17249bb2aa54b7563e7a86959096
test_hygiene_fix_seal: 460d6f5b1efdb24199534778bd5cc9d4a8131d13
evidence_content_seal: ed202d846f609fb60a047c0e01422b13d535c7d0
decision: pass
findings_open: []
reopen_required: []
docs_only: true
scope_paths:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s8-independent-acceptance.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md
  - docs/backend-vnext/refactoring/formal/plans/p5-business-vertical-slices-design.md
  - docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
  - docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md
  - docs/backend-vnext/refactoring/formal/README.md
  - docs/backend-vnext/README.md
p5_5b_slice_exit: pass
p5_5c_authorized: no
production_deployment_authorized: no
next_step: separate_p5_5c_entry_authorization
```

## 1. Acceptance decision

**PASS.** P5-5B 的 S1–S7 stage/review lineage、S7-F2 finding-scoped remediation、S8-F1
static-gate remediation、五包 static、无 ignore 权威 runner、三镜像 conjunction、真实
Accept→upload→preview→submit→poll→T3→read journey，以及 provenance 记录均已闭合。

本 acceptance 只声明 P5-5B slice exit。它不授权 P5-5C implementation、production deployment、
新的 Repository effect、contract/wire/trust boundary 变更或 deferred 项的顺手实现。

## 2. Independent evidence audit

| Barrier | Evidence | Decision |
| --- | --- | --- |
| S7 functional acceptance | review-7 pass；S7-F2 由 review-8 独立复核 | pass |
| Open findings | S7-F2、S8-F1 closed；`findings_open: []` | pass |
| Five-package static | review-1 记录 @ `460d6f5b` 全部 pass | pass |
| Authoritative runner | `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh` @ `460d6f5b` exit 0 | pass |
| Container conjunction | fresh images + smoke @ `87c49763` | pass |
| Container evidence inheritance | `87c49763..460d6f5b` 仅修改 `tests/test_live_session.py`；Backend Dockerfile 只复制 `backend/src` | pass |
| Current implementation identity | `460d6f5b..1bff2970` 无 `vnext/**` 变化 | pass |
| Provenance | content seal `ed202d84` 可达，且为 publication tip `1bff2970` 的 parent | pass |

本轮独立复核重新计算并确认：

```yaml
vnext_source_tree_sha256: sha256:700d77136bae43c356e0270404ad83dda1a5a8438ead3398826bb5e99160c359
vnext_tracked_file_count: 860
compose_yaml_sha256: f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0
backend_uv_lock_sha256: 21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea
repository_service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
```

未重复执行已在同一 implementation tree 上通过的全量测试或容器 journey；本轮执行的是
Git lineage、changed-path、content-seal、source digest、Compose/lock digest 与文档一致性复核。

## 3. Deferred disposition

S7-O1、S7-O3、S7-O4、occupancy assertion gap、test harness shutdown caller、private process access
和 Repository restart owner 范围维持 S8 handoff 的非阻塞 disposition。它们不改变已接受的
contract barrier，也不构成 P5-5B exit blocker；后续若出现真实 consumer、故障或 contract
变化，按 proportional-assurance policy 单独 reopen。

## 4. Authorization boundary

```yaml
p5_5b_slice_exit: pass
p5_5b_hold: released
p5_5b_implementation_authorized: no
p5_5c_authorized: no
production_deployment_authorized: no
new_repository_effect_authorized: no
next_step_authorized: no
```

P5-5C 的 entry/design/implementation 必须取得新的明确授权；不得从本记录推导。

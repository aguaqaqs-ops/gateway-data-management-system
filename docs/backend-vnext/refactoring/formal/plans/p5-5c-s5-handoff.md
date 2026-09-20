# P5-5C-S5 Final Current-HEAD Gate and Slice Handoff

当前结论：**`p5_5c_slice_exit: pass`**，见 [Independent Acceptance](p5-5c-s5-independent-acceptance.md)。下文 Delivery 状态是验收前快照。

状态：**pass — slice exit 建议 `p5_5c_slice_exit=pass_recommended`（P1/P2 closed @ [remediation handoff](p5-5c-s5-remediation-handoff.md)；不自行授权 P5-5D / production）**

日期：2026-09-20 (UTC+8)

Owner：P5-5C Delivery

上游：[P5-5C Review Execution Plan §8](p5-5c-review-execution-plan.md)、
[P5-5C-S4 Handoff](p5-5c-s4-handoff.md)、
[P5-5C-S5 Remediation Handoff](p5-5c-s5-remediation-handoff.md)

```yaml
stage: P5-5C-S5-independent-functional-acceptance-and-current-head-gate
candidate_head: 04317788c259b172e3b8580cfe42bac8d16735f0
gate_tested_head: 04317788c259b172e3b8580cfe42bac8d16735f0
s5_implementation_candidate_head: 66bdca8812
s5_remediation_implementation_head: 04317788c2
s4_implementation_candidate_head: 83dc907cb5
s4_remediation_implementation_head: 161b805ad8
s4_sealed_doc_tree_head: 4eac2464f0
remediation_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5c-s5-remediation-handoff.md
clean_status: yes
container_rebuild_required: yes
container_reason: S4 route/production wiring/session config + S5 compose e2e; fresh prebuilt gate project @ candidate
container_gate_for_current_head: passed
five_package_static: pass
authoritative_runner: pass
review_findings_open: []
findings_closed: [P1, P2]
p5_5c_slice_exit: pass_recommended
p5_5d_authorized: no
production_deployment_authorized: no
compose_gate_project: gateway-p5-5c-s5-gate
timezone: Asia/Shanghai
```

## S5 deliverables

| Path | Change |
| --- | --- |
| `vnext/backend/tests/test_review_compose_e2e.py` | deployed Submit→Review APPROVE→GET facts journey |
| `vnext/backend/tests/support/compose_gate_harness.py` | shared compose gate harness（P1/P2 remediation） |
| `docs/backend-vnext/refactoring/formal/plans/p5-5c-s5-remediation-handoff.md` | P1/P2 closure evidence |

reject/return/withdraw release 由 `tests/test_review_transactions.py` 证明；compose journey 不复制四态矩阵。

## Phase 1 — Accumulated focused unit gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_domain.py tests/test_review_persistence.py \
  tests/test_review_transactions.py tests/test_review_http.py \
  tests/test_submit_transactions.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_architecture.py
# 278 passed (@ 04317788c2 remediation re-verify)
```

## Phase 2 — Five-package static

```bash
for pkg in shared_kernel repository_contracts repository_client backend repository_service; do
  (cd vnext/$pkg && ../scripts/uv-consume.sh -C . run ruff check . && \
    ../scripts/uv-consume.sh -C . run mypy)
done
# all pass @ 04317788c2
```

| Package | mypy source files |
| --- | --- |
| shared_kernel | 34 |
| repository_contracts | 15 |
| repository_client | 26 |
| backend | 391 |
| repository_service | 198 |

## Phase 3 — Authoritative runner

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

| Package | Result |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend | 2366 passed |
| repository_service (parallel) | 1678 passed, 1 skipped |
| repository_service (serial) | 205 passed |

**Exit code:** 0

## Phase 4 — Container gate and provenance

### Pre-build identity

| Item | Value |
| --- | --- |
| Gate tested SHA | `04317788c259b172e3b8580cfe42bac8d16735f0` |
| Gate worktree porcelain | **empty** |
| `vnext/**` source-tree digest | `sha256:9b7f863c4d24596fdddb3bbd82a4e5b25a85fcf1af26dd8af2124dbb06c885d9` (874 files) |
| `source_tree_method` | `sorted_per_file_sha256_records_for_git_ls_files_vnext` |
| `deploy/compose.yaml` | `sha256:f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0` |
| `shared_kernel/uv.lock` | `sha256:7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
| `repository_contracts/uv.lock` | `sha256:b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| `repository_client/uv.lock` | `sha256:6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| `backend/uv.lock` | `sha256:21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
| `repository_service/uv.lock` | `sha256:6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |

### Image pre-build（conjunction evidence）

```bash
./vnext/scripts/build-repository-service-image.sh

cd vnext/deploy
export GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5c-s5-gate
export COMPOSE_PROJECT_NAME=gateway-p5-5c-s5-gate
export GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local
docker compose build --no-cache backend worker
```

| Image | ID / labels | Role |
| --- | --- | --- |
| `gateway-repository-service:local` | `sha256:d731197ec2e425defcaf582cc9cd2c516f9e43176f62bd4b0990336680e42b30`；`org.opencontainers.image.revision=04317788c2`；`build-input-revision=4d1dc010` | script build；conjunction 三服务共用 |
| `gateway-p5-5c-s5-gate-backend:latest` | `sha256:ee3e8b0983efdb84cbd56a25d090d050b4d527deca87f5f572dfc25ac0736b5b` | **conjunction 实跑 backend**（PREBUILT 消费） |
| `gateway-p5-5c-s5-gate-worker:latest` | `sha256:f0ef349faea1f19d417e2db6dc447864971c111326e1f3992432127f9f15d261` | **conjunction 实跑 worker**（PREBUILT 消费） |

`deploy-backend:latest` / `deploy-worker:latest`（默认 compose project）**不是** conjunction journey 证据；仅作 non-conjunction reference。

### Conjunction smoke（PREBUILT，**0 skipped**）

```bash
export GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5c-s5-gate
export GATEWAY_COMPOSE_GATE_PREBUILT=1
export GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local

cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py \
  tests/test_backend_http_container_gate.py
# 5 passed, 0 skipped
```

| nodeid | Owner | Result |
| --- | --- | --- |
| `test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey` | Review journey | **pass** |
| `test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart` | restart smoke | **pass** |
| `test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` | Submit journey | **pass** |
| `test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint` | CMD gate | **pass** |
| `test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service` | readiness/clean-stop (**P1 owner**) | **pass** |

## §2A disposition

5C 未扩大 [P5 Business Vertical Slices Design §2A](p5-business-vertical-slices-design.md#p5-architecture-guardrails) 的已知跨 Slice 问题；尚存的架构收口项继续引用 P5 阶段收口，**不**宣称所有历史架构问题已解决。

## Forbidden imports

None introduced in S5 remediation.

## Next step

```yaml
p5_5c_slice_exit: pass_recommended
next_step: independent_acceptance_authority_for_p5_5c_slice_exit
p5_5d_authorized: no
production_deployment_authorized: no
```

最终由 separate independent acceptance context 决定 `p5_5c_slice_exit`。Delivery/handoff 不自签 exit。

## Independent acceptance publication

[S5 Independent Slice Exit Acceptance](p5-5c-s5-independent-acceptance.md) 已独立声明
`p5_5c_slice_exit: pass`，P1/P2 closed、open findings 为空。上文 Delivery 建议与 pending
快照保留为历史交接记录，当前状态以独立 acceptance 为准；不授权 5D implementation 或 production。

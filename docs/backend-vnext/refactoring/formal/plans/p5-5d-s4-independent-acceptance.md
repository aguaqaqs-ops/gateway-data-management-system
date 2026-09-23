# P5-5D-S4 Independent Slice Exit Acceptance Record

> **SUPERSEDED（2026-09-23）**：本文绑定的候选 `05e0399fe9` 上 `five_package_static: pass` 复核
> 不可复现，本记录的 `p5_5d_slice_exit: pass` 不再是当前权威。现行权威记录：
> [p5-5d-s4r2-independent-acceptance.md](p5-5d-s4r2-independent-acceptance.md)（绑定 `af833695ef`）。
> 以下原文仅作历史保留，不改写。

状态：**PASS — `p5_5d_slice_exit: pass`**

日期：2026-09-23

Owner：Backend vNext Architecture Acceptance（independent acceptance context）

上游：[Execution Plan §4 S4 / §7](p5-5d-archive-execution-plan.md)、
[S4 Handoff](p5-5d-s4-handoff.md)、
[S3 Stage Exit Acceptance](p5-5d-s3-stage-exit-acceptance.md)。

```yaml
acceptance_kind: p5_5d_slice_exit
acceptance_authority: explicit_user_authorization_after_s4_gates
accepted_candidate_head: 05e0399fe950c115e4a24764dce4f6d2d49cb4bb
gate_tested_head: 05e0399fe950c115e4a24764dce4f6d2d49cb4bb
archive_implementation_binding: d61d37be97821f303e9083abe739618cebd96b46
decision: pass
findings_closed: [S4-submit-integration-baseline-fix]
review_findings_open: []
p5_5d_s1_stage_exit: pass
p5_5d_s2_stage_exit: pass
p5_5d_s3_stage_exit: pass
p5_5d_slice_exit: pass
p5_5d_implementation_status: completed
p5_5e_implementation_authorized: no
production_deployment_authorized: no
new_repository_effect_authorized: no
```

## Acceptance and evidence

独立验收确认 S4 最终候选 `05e0399fe9` 已通过五包 static、权威 runner、fresh-build conjunction
（6 nodeids，0 skipped）及 §6.3 provenance 绑定。S4 相对 S3 的唯一源码差异为 Submit 集成测试
fixture 与 authoritative BaselineHead 对齐（scoped node id），属 tests owner 修复，不扩展生产机制。
用户授权进入 S3 stage exit 与 S4 验收流程后，本记录签署 `p5_5d_slice_exit: pass`。

### Static

五包 ruff + mypy 全通过（421 / 198 / 26 / 15 / 34 files）。

### Authoritative runner

`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh` → **exit 0**

| Package | Result |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend | 2519 passed |
| repository_service (parallel) | 1678 passed, 1 skipped |
| repository_service (serial) | 205 passed |

### Fresh-build conjunction

Project `gateway-p5-5d-final-gate`；`GATEWAY_COMPOSE_GATE_PREBUILT=0`。

**6 passed, 0 skipped，348.43s，exit 0**

```text
test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect
test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey
test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart
test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey
test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint
test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service
```

### Provenance

| 证据 | 值 |
| --- | --- |
| Source-tree digest (905 files) | `5f94c79aeca82d2b558d1a0942520c86349dc5e2eedb825efa941a794387d9bc` |
| Backend `src` py digest | `b37e8b3ec48fad1144505a6756e79ae33f71cfeb8c3356f4f2a4c85e235f6285` |
| repository-service image | `sha256:beb50fed3d1ecca65c2f67450dea69969898e604a38e3e818f72370ce2521c8d` |
| backend image | `sha256:2e73f82418d354cbf935ac4536a6f10f11ac51895020b7cfb8c7226dab23b3bc` |
| worker image | `sha256:b52585330d7a79db272d10d04dafdea50e2feda2b7520f71ca81062cb3648e54` |

运行中 container/image 绑定见 [S4 handoff](p5-5d-s4-handoff.md) 与
`vnext/backend/tests/support/.last_compose_gate_provenance.json`。

## Container decision

- Current HEAD at acceptance：`05e0399fe950c115e4a24764dce4f6d2d49cb4bb`；工作区干净。
- Container rebuild required：**yes**（S4 最终候选 fresh-build conjunction）。
- Container gate for accepted candidate：**passed**；无 deferred conjunction nodeid。
- v5 schema **仍未发布**；本 exit 不授权 production deployment 或 Repository effect。

5D slice exit 不等于 5E implementation、P5 整体架构收口或 production deployment 授权。

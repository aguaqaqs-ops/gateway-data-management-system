# P5-5D-S3 Stage Exit Acceptance

状态：**PASS — `p5_5d_s3_stage_exit: pass`**

日期：2026-09-23

Owner：Backend vNext Architecture Acceptance（independent acceptance context）

上游：[Execution Plan §4 S3](p5-5d-archive-execution-plan.md)、
[S3 Handoff](p5-5d-s3-handoff.md)、
[S3 Round-4 Independent Closure Review](p5-5d-s3-round4-independent-closure.md)。

```yaml
acceptance_kind: p5_5d_s3_stage_exit
acceptance_authority: explicit_user_authorization_after_independent_review
accepted_candidate_head: 918a75a4987c3739c7a70ca8acc680aaeaf436e7
implementation_binding: d61d37be97821f303e9083abe739618cebd96b46
evidence_basis: p5-5d-s3-round4-independent-closure.md
decision: pass
findings_closed: [P1-1, P1-2, P1-3, P1-4, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6, P2-7, P2-8, P2-9, R-1, R-2, R-3, R-4, round-4-F1]
review_findings_open: []
p5_5d_s3_stage_exit: pass
p5_5d_slice_exit: not_evaluated
production_deployment_authorized: no
new_repository_effect_authorized: no
next_step: P5-5D-S4
```

## Acceptance and evidence

独立复审确认 S3 re-review remediation（R-1 断连死循环、provenance、Plan §4 残留、七响应泄漏扫描、
非 string 边界、Start 跨 actor 重放）及 round-4 修复（P2-1 RecursionError→422、P2-2 main ref 屏障、
F1 compose gate dolt 用户隔离）均已关闭，未发现新的阻断 finding。用户随后明确授权将
`p5_5d_s3_stage_exit: pass` 落入文档。

- **E1** focused gate（六文件）：**137 passed, 1 warning，7.46s**
- **E3** 五包 ruff + mypy：**全部通过**（421 / 198 / 26 / 15 / 34 files）
- **E2** fresh-build conjunction：**6 passed, 0 skipped，346.44s，exit 0**
- Source-tree digest（905 文件，`path\tsha256` recipe）：
  `c21785c370568befd0c24517c190c003bde7b0ef1efcfc4fb6f97b68c0e24c15`
- Backend `src` py digest（local == running image）：
  `b37e8b3ec48fad1144505a6756e79ae33f71cfeb8c3356f4f2a4c85e235f6285`
- 五锁与 compose.yaml SHA 均与 [S3 handoff](p5-5d-s3-handoff.md) 一致

E2 六个 nodeid（相对 `vnext/backend/tests/`）：

```text
test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect
test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey
test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart
test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey
test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint
test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service
```

## Build / running provenance（S3 复审绑定）

Project `gateway-s3-independent-918a75a`；`GATEWAY_COMPOSE_GATE_PREBUILT=0`。

| Service | Container ID | Immutable image ID |
| --- | --- | --- |
| repository-service | `a5f026430a4d5e5e4104686a3d5d75e66cdac881c833bed9619457fb710f5f30` | `sha256:6dfc8ad602835ae54d6504bb459bc77eecd697561873f1a20bd3383cf6125a4a` |
| backend | `845b3294cfc4c773e95eaafbb9da0f4f489a92b4a784109655fbc51b8e20f9e9` | `sha256:2391594c8056e340197e185dabaa18253a2d11af6b057b4892002ef3f4f9279a` |
| worker | `2ed431fb1d736026d62a666b9cea986df6ab092a383aa881ef421e51d799636e` | `sha256:dc9b49cea82e2b2c6328e1c9ea004d8043848157321db36e961ec2f06b45fb10` |

## Container decision

- Current HEAD at acceptance：`918a75a4987c3739c7a70ca8acc680aaeaf436e7`；`vnext/**` 干净。
- Container rebuild required this acceptance：**yes**（middleware / harness 变更）；已在 round-4 复审完成。
- Last verified image revision：实现绑定 `d61d37be97821f303e9083abe739618cebd96b46`；source-tree/IDs 见上。
- S4 仍须对最终候选执行 fresh-build 全量 conjunction 与权威 runner；**不得**沿用本阶段镜像续签 slice exit。

本记录不声明 `p5_5d_slice_exit: pass`，不授权 production deployment 或 5E implementation。

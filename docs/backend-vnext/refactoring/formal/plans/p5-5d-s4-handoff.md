# P5-5D-S4 Final Candidate Gate and Slice Handoff

状态：**delivery complete — `delivery_recommendation: pass_recommended`（不签 slice exit）**

日期：2026-09-23

Owner：P5-5D Delivery

上游：[Archive Execution Plan §4 S4 / §6 / §7](p5-5d-archive-execution-plan.md)、
[S3 Stage Exit Acceptance](p5-5d-s3-stage-exit-acceptance.md)。

```yaml
stage: P5-5D-S4-final-fresh-candidate-conjunction-and-independent-exit
candidate_head: 05e0399fe950c115e4a24764dce4f6d2d49cb4bb
gate_tested_head: 05e0399fe950c115e4a24764dce4f6d2d49cb4bb
s3_stage_exit_acceptance: dcdb22e679
archive_implementation_binding: d61d37be97821f303e9083abe739618cebd96b46
clean_status: yes
container_rebuild_required: yes
container_reason: S4 final candidate fresh-build conjunction @ 05e0399fe9
container_gate_for_current_head: passed
five_package_static: pass
authoritative_runner: pass
compose_gate_project: gateway-p5-5d-final-gate
prebuilt_used: no
p5_5d_s1_stage_exit: pass
p5_5d_s2_stage_exit: pass
p5_5d_s3_stage_exit: pass
p5_5d_slice_exit: not_evaluated
p5_5e_implementation_authorized: no
production_deployment_authorized: no
new_repository_effect_authorized: no
delivery_recommendation: pass_recommended
```

## S4 candidate delta

相对 S3 stage exit 文档提交 `dcdb22e679`，最终候选新增一次测试修复提交
`05e0399fe9`：Submit 集成测试读取 DB authoritative BaselineHead（scoped node id），
消除全量 runner 中 24 项 backend integration 失败与 8 项 repository_service compose
dirty-worktree 级联失败。变更限于 `vnext/backend/tests/**` 既有 owner fixture，无生产机制扩展。

## §7 evidence summary

1. **阶段 HEAD / 独立 review**：S1/S2/S3 stage exit 均已 pass；S3 round-4 独立复审与
   stage-exit acceptance 见链接文档；S4 在本候选 fresh-build 全量 gate。
2. **Design 差异**：Archive Design §8 七路由、permission、DTO byte 规则、双 actor compose journey、
   零 Repository effect 观察窗口均已交付；未实现项仍仅为 Design §11 细化与 slowloris 等已记录 defer。
3. **事务 / 并发证明**：引用 S2 handoff（单事务 Start、replay、三竞争、Review closure）与 S3 compose
   双 actor journey + main ref 屏障。
4. **Migration / initial-empty**：S1 v5 Baseline DDL + initial-empty focused gate；S3 真实 provisioning journey。
5. **Gate 结果**：见下文 Phase 1–4；0 skipped conjunction nodeid。
6. **P5 §2A 未扩散**：无新增 broker/outbox/worker job/Repository write adapter/private import 泄漏。
7. **Delivery**：`pass_recommended`；slice exit 待 [independent acceptance](p5-5d-s4-independent-acceptance.md)。

## Phase 1 — Five-package static

```bash
for pkg in backend repository_service repository_client repository_contracts shared_kernel; do
  (cd vnext/$pkg && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done
```

全部通过；mypy 文件数 421 / 198 / 26 / 15 / 34。

## Phase 2 — Authoritative runner

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

| Package | Result |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend | 2519 passed, 1 warning |
| repository_service (parallel) | 1678 passed, 1 skipped |
| repository_service (serial) | 205 passed |

**Exit code:** 0（五锁 SHA 前后一致）。

## Phase 3 — Fresh build

```bash
./vnext/scripts/build-repository-service-image.sh   # exit 0
docker compose -f vnext/deploy/compose.yaml build backend worker
```

| Service | Immutable image ID |
| --- | --- |
| repository-service | `sha256:beb50fed3d1ecca65c2f67450dea69969898e604a38e3e818f72370ce2521c8d` |
| backend | `sha256:2e73f82418d354cbf935ac4536a6f10f11ac51895020b7cfb8c7226dab23b3bc` |
| worker | `sha256:b52585330d7a79db272d10d04dafdea50e2feda2b7520f71ca81062cb3648e54` |

## Phase 4 — Conjunction（0 skipped）

```bash
cd vnext/backend
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5d-final-gate \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
GATEWAY_COMPOSE_GATE_PREBUILT=0 \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
```

**6 passed, 0 skipped，348.43s，exit 0**

| nodeid | result |
| --- | --- |
| `test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect` | passed |
| `test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey` | passed |
| `test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart` | passed |
| `test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` | passed |
| `test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint` | passed |
| `test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service` | passed |

## Provenance record (§6.3)

| 证据 | 值 |
| --- | --- |
| Git HEAD | `05e0399fe950c115e4a24764dce4f6d2d49cb4bb` |
| Worktree | clean |
| Source-tree file count | 905 |
| Source-tree digest (`path\tsha256` recipe) | `5f94c79aeca82d2b558d1a0942520c86349dc5e2eedb825efa941a794387d9bc` |
| Backend `src` py digest | `b37e8b3ec48fad1144505a6756e79ae33f71cfeb8c3356f4f2a4c85e235f6285` |
| uv.lock SHA (backend) | `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
| uv.lock SHA (repository_service) | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| uv.lock SHA (repository_client) | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| uv.lock SHA (repository_contracts) | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| uv.lock SHA (shared_kernel) | `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
| compose.yaml SHA-256 | `f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0` |
| Running container provenance | `vnext/backend/tests/support/.last_compose_gate_provenance.json` |
| `org.opencontainers.image.revision` (backend/worker) | 空（py digest 对等补偿） |

Running containers（project `gateway-p5-5d-final-gate`）：

| Service | Container ID | Immutable image ID |
| --- | --- | --- |
| repository-service | `366706ba3c42` | `sha256:beb50fed3d1ecca65c2f67450dea69969898e604a38e3e818f72370ce2521c8d` |
| backend | `1c51de285bfc` | `sha256:2e73f82418d354cbf935ac4536a6f10f11ac51895020b7cfb8c7226dab23b3bc` |
| worker | `48c2ffff2089` | `sha256:b52585330d7a79db272d10d04dafdea50e2feda2b7520f71ca81062cb3648e54` |

## Independent countersign

```yaml
delivery_recommendation: pass_recommended
review: pending
p5_5d_slice_exit: not_evaluated
slice_exit: not_signed_by_delivery
```

Delivery 不代签 `p5_5d_slice_exit` 或 `production_deployment_authorized`。

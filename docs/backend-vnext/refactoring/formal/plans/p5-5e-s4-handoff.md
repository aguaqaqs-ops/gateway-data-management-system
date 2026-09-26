# P5-5E-S4 Final Fresh Candidate Conjunction and Slice Handoff

状态：**S4 pass — `delivery_recommendation: pass_recommended`（slice exit 见独立验收记录）**

日期：2026-09-26

Owner：P5-5E Delivery

上游：[Execution Plan §S4](p5-5e-history-compare-execution-plan.md)、
[S3 Stage Exit Acceptance](p5-5e-s3-stage-exit-acceptance.md)。

```yaml
stage: P5-5E-S4-final-fresh-candidate-conjunction-and-independent-exit
candidate_head: 217236980350d523101936af5464fbbd9ad66f88
gate_tested_head: 217236980350d523101936af5464fbbd9ad66f88
s3_stage_exit_acceptance: docs/backend-vnext/refactoring/formal/plans/p5-5e-s3-stage-exit-acceptance.md
s3_gate_tested_head: db9ac0a808c6494ed081fd00bf60fb6962867a46
clean_status: yes_at_t1_t2_t3_t4
container_rebuild_required: yes
container_reason: S4 unconditional fresh-build conjunction @ gate_tested_head
container_gate_for_current_head: passed
five_package_static: pass
authoritative_runner: pass
compose_gate_project: gateway-p5-5e-s4-gate
prebuilt_used: no
p5_5e_s1_stage_exit: pass
p5_5e_s2_stage_exit: pass
p5_5e_s3_stage_exit: pass
p5_5e_slice_exit: not_evaluated
production_deployment_authorized: no
new_repository_effect_authorized: no
delivery_recommendation: pass_recommended
acceptance_record: docs/backend-vnext/refactoring/formal/plans/p5-5e-s4-independent-acceptance.md
compose_gate_provenance: docs/backend-vnext/refactoring/formal/plans/p5-5e-s4-compose-gate-provenance.json
```

## S3 → S4 candidate delta

相对 S3 `gate_tested_head` `db9ac0a` 的增量限于执行计划 §S4 **架构门禁预算例外**与 S3 exit 文档：

| 区域 | 说明 |
| --- | --- |
| `T/test_architecture.py`、`T/architecture_baseline.py`、`T/support/import_rules.py` | 2026-09-25 架构评审基线（非 5E 行为变更） |
| `T/support/compose_gate_harness.py` | port 8000 检查移至 flock 之后（测试 harness） |
| docs | S3 stage exit、provenance、execution plan §S4 预算记录 |

无 `B/**` 生产逻辑、五包 lock、Dockerfile/compose 边界变更。

## Phase 1 — Five-package static (T1)

```bash
for p in shared_kernel repository_contracts repository_client repository_service backend; do
  (cd vnext/$p && ../scripts/uv-consume.sh -C . run ruff check . \
    && ../scripts/uv-consume.sh -C . run mypy --no-incremental) || exit 1
done
```

| Package | ruff | mypy |
| --- | --- | --- |
| shared_kernel | exit 0 | 34 files |
| repository_contracts | exit 0 | 15 files |
| repository_client | exit 0 | 26 files |
| repository_service | exit 0 | 198 files |
| backend | exit 0 | 459 files |

## Phase 2 — Authoritative runner (T2)

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

| Package | Result |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend | 2702 passed, 1 Starlette deprecation warning |
| repository_service (parallel) | 1678 passed, **1 skipped** |
| repository_service (serial) | 205 passed |

**runner exit code: 0。** 五锁 SHA 前后一致；worktree clean。

`repository_service` parallel 的 1 skipped 与 P5-5D S4R2 先例同型（非 backend/compose owner）；S4 compose 并合与 backend 全量为 **0 skipped**。

## Phase 3 — Fresh build (T3)

```bash
./vnext/scripts/build-repository-service-image.sh
docker compose -f vnext/deploy/compose.yaml build backend worker
```

| Service | Immutable image ID | Notes |
| --- | --- | --- |
| repository-service | `sha256:09a6710d894974d54da78103e95aad5dc420a536b47c0921f55ecd49c2ba9738` | `org.opencontainers.image.revision=217236980350d523101936af5464fbbd9ad66f88` |
| backend (gate running) | `sha256:5d872a0086226376bac21fccd90c0a5115e6d9e52aa863d5c43e6fc779cc693f` | conjunction stack |
| worker (gate running) | `sha256:dcc615760f0da6990825525bd3f8a5f67dcdd6fbe050b9dca328e642bf778014` | conjunction stack |

Backend `src` py 聚合 digest（本地与 gate running 镜像内一致）：

`0fa5063d2b241ba9e208aa79ac526e2e2b5060856b01e4d2552cd06b322a689f`

## Phase 4 — Conjunction (T4)

**9 passed, 0 skipped, 0 xfailed**；1070.00s；exit 0。

```bash
cd vnext/backend
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5e-s4-gate \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
GATEWAY_COMPOSE_GATE_PREBUILT=0 \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v --durations=0 \
  tests/test_archive_compose_e2e.py \
  tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py \
  tests/test_backend_http_container_gate.py \
  tests/test_history_compose_e2e.py \
  tests/test_ordered_compare_compose.py \
  tests/test_ordered_submit_bisect_compose.py
```

| nodeid | elapsed | result |
| --- | ---: | --- |
| `tests/test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect` | 140.31s | passed |
| `tests/test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey` | 78.21s | passed |
| `tests/test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart` | 25.41s | passed |
| `tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` | 74.66s | passed |
| `tests/test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint` | 1.63s | passed |
| `tests/test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service` | 15.61s | passed |
| `tests/test_history_compose_e2e.py::test_compose_history_compare_journey_zero_write_restart` | 289.31s | passed |
| `tests/test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey` | 170.78s | passed |
| `tests/test_ordered_submit_bisect_compose.py::test_ordered_submit_bisect_control_cases` | 271.01s | passed |

## §6.3 provenance record

| 证据 | 值 |
| --- | --- |
| Candidate / gate-tested Git HEAD | `217236980350d523101936af5464fbbd9ad66f88` |
| `source_tree_sha` | `3baa8beb0b1278a51473e91a456859d3b65ec25f` |
| `vnext/deploy/compose.yaml` | `f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0` |
| 五锁 SHA | 见 [p5-5e-s4-compose-gate-provenance.json](p5-5e-s4-compose-gate-provenance.json) |
| Running provenance (authoritative) | 同上 JSON `running_images_by_gate.s4_conjunction` |

## 执行计划 §7 最终 exit 证据（author 声明）

1. **设计 §10 停止条件**：未触发（无 capability 词表扩展、无 caller commit、无业务写、无 job_payload 超预算等）。
2. **5D 对齐**：`p5_5d_slice_exit: pass` @ `af833695`；零表腿在本轮 `test_compose_history_compare_journey_zero_write_restart` 重断言（INITIAL 空 commit + compare 旅程）；5D 历史零表 compose 证据仍见 [p5-5d-s4r2-independent-acceptance.md](p5-5d-s4r2-independent-acceptance.md)。
3. **零写三项**：`test_history_compose_e2e` 内 `HISTORY_ZERO_WRITE_TABLES` row-set、`list_repository_commit_ids`、`r4-manifest-` 前缀集合 compare 前后相等（测试内断言通过）。
4. **容器并合**：9/9 passed，0 skipped；image ID 见 provenance JSON。
5. **设计 §8 owner 映射**：见下表（与 S3 handoff 一致，S4 全量 runner 覆盖）。
6. **deferred**：无 slice-exit 阻塞项。post-exit 评估：prepare handler 非 `SubmitImportPublicationError` 确定性失败占用释放（[S3 handoff 已知边界](p5-5e-s3-handoff.md)）。
7. **镜像 provenance 链路**：S1/S2/S3 各阶段 JSON + 本 S4 记录为最终 fresh 权威。

### 设计 §8 ↔ 测试文件（摘要）

| Owner 文件 | 不变量域 |
| --- | --- |
| `test_history_projection.py` | History 投影 |
| `test_history_http.py` | HTTP 读/compare 路由 |
| `test_history_compare_transactions.py` | accept/replay/事务 |
| `test_history_compare_jobs.py` | job/checkpoint/policy |
| `test_history_compare_integrity.py` | 类 (c) integrity |
| `test_history_compose_e2e.py` | 正式 compose 旅程 + 零写 |
| `test_ordered_compare_compose.py` / `test_ordered_submit_bisect_compose.py` | ordered policy / submit 对照 |
| `test_architecture.py` | import 边界 |

## 范围声明

- 本 handoff **不** 授权 production deployment 或新 Repository effect。
- `p5_5e_slice_exit` 由 [p5-5e-s4-independent-acceptance.md](p5-5e-s4-independent-acceptance.md) / [p5-5e-slice-exit-final.md](p5-5e-slice-exit-final.md) 签署；**5E slice exit ≠ P5 整体架构/性能收口**。

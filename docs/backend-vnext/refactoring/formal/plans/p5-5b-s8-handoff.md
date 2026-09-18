# P5-5B-S8 Final Current-HEAD Gate and Slice Handoff

状态：**pending_closure — S8-F1 mypy 硬失败待闭合（见 [p5-5b-s8-f1-remediation-handoff.md](p5-5b-s8-f1-remediation-handoff.md)）**

日期：2026-09-18 (UTC+8)

Owner：P5-5B Delivery

上游：[P5-5B Submit Finalize Execution Plan §6–§8](p5-5b-submit-finalize-execution-plan.md)、
[P5-5B-S7 Remediation Handoff](p5-5b-s7-remediation-handoff.md)、
[P5-5B-S7 Independent Review 7](p5-5b-s7-independent-review-7.md)、
[P5-5B-S7 Independent Review 8](p5-5b-s7-independent-review-8.md)

```yaml
stage: P5-5B-S8-final-current-head-gate
candidate_head: 87c497634e4f6417de7fbb46b42086fd61af9031
gate_tested_head: 87c497634e4f6417de7fbb46b42086fd61af9031
implementation_seal: e5c43c0c9f71de3cd2e602504ec9034f16add8af
test_evidence_seal: d3661fe0eda4a3463afed879c6a5bbec72f79404
s7_f2_remediation_seal: 4d1dc010deff17249bb2aa54b7563e7a86959096
test_hygiene_seal: 87c497634e4f6417de7fbb46b42086fd61af9031
records_head: f4aab01863c8d644b94dd9808c1104851795945f
clean_status: yes
container_rebuild_required: yes
container_gate_for_current_head: passed
five_package_static: pending_closure
authoritative_runner: pending_closure
findings_closed: [S7-F2]
findings_open: [S8-F1]
deferred: [S7-O1, S7-O3, S7-O4, occupancy-assertion-gap, shutdown-no-caller, private-process-access]
reopen_required: []
implementation_authority_unchanged: false
p5_5b_slice_exit: pending_closure
timezone: Asia/Shanghai
```

## Seal 分层说明

| Seal | SHA | 含义 |
| --- | --- | --- |
| `implementation_seal` | `e5c43c0c` | Round 4 owner evidence 生产源码边界（S7 review-7 前） |
| `test_evidence_seal` | `d3661fe0` | R4-F1 recovery owner lease 窗口健壮性（test-only） |
| `s7_f2_remediation_seal` | `4d1dc010` | S7-F2 compose journey + 真实 preview→submit 路径下 snapshot table binding 最小生产修订 |
| `test_hygiene_seal` | `87c49763` | `test_live_session.py` repository ready probe 隔离（权威 runner 门禁） |
| `candidate_head` | `87c49763` | 全部 gate 实测代码对象（与 `gate_tested_head` 一致） |
| `gate_tested_head` | `87c49763` | 镜像构建与 conjunction 实测对象 |
| `s7_f2_closure_review` | 见 review-8 `records_head` | S7-F2 remediation 独立复核（`4d1dc010` closure @ review-8） |
| `records_head` | 见 YAML 顶栏 | 本文档发布 revision；`git rev-parse HEAD` 必须等于此 SHA；gate 代码仍以 `candidate_head` 为准 |

`implementation_authority_unchanged: false`：`4d1dc010` 在 S7-F2 remediation 中扩展了 allowed paths 外的最小生产修订（`submit_jobs.py`、`submit_acceptance.py`、`contracts.py`），以修复真实 preview artifact 集合无法被 prepare-import 打开的问题；其余 Submit finalize 语义与 Round 4 seal 一致。

## S7-F2 remediation summary

**Authority**：[p5-5b-s7-independent-review-4.md](p5-5b-s7-independent-review-4.md) §4.3（reclassification）；
**Closure**：[p5-5b-s7-independent-review-8.md](p5-5b-s7-independent-review-8.md)（`4d1dc010` remediation 独立复核）

**Changed paths**：

| Path | Change |
| --- | --- |
| `vnext/backend/tests/test_submit_compose_e2e.py` | 三容器 Accept→upload→preview→submit→poll→T3→read journey；无 repository fallback skip |
| `vnext/deploy/compose.yaml` | `worker.restart: unless-stopped` |
| `vnext/backend/src/.../submit_acceptance.py` | preflight 仅将可打开的 snapshot table manifest 记入 `snapshot_table_artifact_refs` |
| `vnext/backend/src/.../submit_jobs.py` | `_snapshot_bindings_from_operation` 过滤/去重 snapshot manifest |
| `vnext/backend/src/.../contracts.py` | `is_submit_snapshot_table_binding_candidate` |
| `vnext/backend/tests/test_live_session.py` | autouse skip repository ready probe（test-only） |

**Owner 分工**（conjunction）：

| 证明项 | Owner |
| --- | --- |
| healthz/readyz + worker_ready + 脱敏 + backend restart | `test_submit_compose_e2e.py` |
| Accept→upload→import→poll→T3→read | `test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` |
| backend image CMD | `test_backend_http_container_gate.py` |
| backend+repository clean stop | `test_backend_http_container_gate.py` |
| T3 crash barrier | `test_submit_recovery.py` |
| Repository hard-kill restart | `test_submit_recovery.py` |
| T3 response-loss | `test_submit_recovery.py` |

## Phase 1 — Focused accumulated Submit suite

```bash
cd vnext/backend
ACCUMULATED=(tests/test_submit_domain.py tests/test_submit_idempotency.py \
  tests/test_submit_application.py tests/test_submit_transactions.py \
  tests/test_submit_control_db_migrations.py tests/test_sqlite_submit_repository.py \
  tests/test_submit_import_builder.py tests/test_repository_import_artifact_package.py \
  tests/test_submit_artifact_protection.py tests/test_artifact_boundary.py \
  tests/test_submit_http.py tests/test_submit_read_http.py tests/test_operation_http.py \
  tests/test_operator_recovery_http.py tests/test_http_openapi.py \
  tests/test_submit_job_payload.py tests/test_submit_job_prepare.py \
  tests/test_submit_finalize.py tests/test_production_wiring.py \
  tests/test_backend_readiness.py tests/test_http_admission_shutdown.py \
  tests/test_architecture.py)
../scripts/uv-consume.sh -C . run pytest -q -m unit "${ACCUMULATED[@]}"
# 319 passed

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and not serial' \
  tests/test_submit_job_effect.py tests/test_submit_recovery.py tests/test_submit_worker.py
# 26 passed, 11 deselected

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_recovery.py tests/test_submit_worker.py \
  tests/test_submit_worker_process.py tests/test_http_admission_shutdown_process.py \
  tests/test_backend_http_container_gate.py tests/test_submit_compose_e2e.py
# 15 passed, 1 skipped, 14 deselected
```

## Phase 2 — Five-package static

```bash
for pkg in backend shared_kernel repository_contracts repository_client repository_service; do
  (cd vnext/$pkg && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done
# all pass; lockfile guard pass (uv-consume wrapper)
```

## Phase 3 — Authoritative runner

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

| Package | Result |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend | 2184 passed, 1 skipped |
| repository_service (parallel) | 1678 passed, 1 skipped |
| repository_service (serial) | 205 passed |

**Exit code:** 0

## Phase 4 — Container gate and provenance

### Pre-build identity

| Item | Value |
| --- | --- |
| Gate tested SHA | `87c497634e4f6417de7fbb46b42086fd61af9031` |
| Handoff / records SHA | 见 YAML `records_head` |
| Gate worktree porcelain | **empty** |
| `vnext/**` source-tree digest | `sha256:15e496bbdf7d408587755265c9f61cdc4d370e5c9fdb7a5d09f276d1a871c64e` (860 files) |
| `deploy/compose.yaml` | `sha256:f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0` |
| `backend/uv.lock` | `sha256:21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
| `repository_service/uv.lock` | `sha256:6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |

### Image build

```bash
./vnext/scripts/build-repository-service-image.sh
cd vnext/deploy && docker compose build --no-cache backend worker
```

| Image | ID | Fresh rebuild |
| --- | --- | --- |
| `deploy-backend:latest` | `sha256:6309926b558c270bb47a13b42a37971c88b5cddba11d5c48dd07420a54ab4450` | yes (`--no-cache`) |
| `deploy-worker:latest` | `sha256:3ce442466a9925b1601bedb8f031b4c43c597eddbb2408f6f9922af40a7bb227` | yes (`--no-cache`) |
| `gateway-repository-service:local` | `sha256:a725a242e07b1185ed3a1eb8c1e3edd43d550811ee994df405ac6a56b0a5b1e6` | yes (`build-repository-service-image.sh` @ candidate HEAD) |

**Note:** 裸 `docker compose build repository-service` 在本环境因 `dolt-linux-amd64.tar.gz` checksum mismatch 失败；与 S6 历史风险一致。Conjunction 使用 `build-repository-service-image.sh`（`USE_PRELOADED_DEPENDENCIES=1`）成功构建 current-HEAD 镜像。

### Conjunction smoke (@ candidate HEAD)

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
# 3 passed, 1 skipped

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_recovery.py \
  -k 'after_terminal_commit_before_worker_ack or repository_restart'
# 2 passed, 11 deselected
```

## Deferred register（非阻塞）

| 项 | 处置 |
| --- | --- |
| S7-O1 PRE_REQUEST cross-owner | acceptable |
| S7-O3 `defer_operation_terminal` 无 production caller | deferred |
| S7-O4 `abort_submit_in_control_transaction` 未进 `__all__` | deferred |
| 崩溃 owner 未补 occupancy 断言 | deferred |
| `RepositoryServiceClient.shutdown()` 无调用方 | deferred |
| `service1._process` 私有访问 + finally 断言 | deferred |
| Repository restart owner 范围 | 仅 hard-kill 后持久性 + Backend 消费；graceful shutdown / startup recovery 属其他 owner |

## Hygiene

```bash
git diff --check          # pass
HEAD=$(git rev-parse HEAD)
for f in docs/backend-vnext/refactoring/formal/plans/p5-5b-s7-independent-review-8.md \
         docs/backend-vnext/refactoring/formal/plans/p5-5b-s8-handoff.md \
         docs/backend-vnext/refactoring/formal/plans/p5-5b-s7-acceptance.md; do
  sed -i "s/^records_head: .*/records_head: $HEAD/" "$f"
done
RH=$(grep -m1 '^records_head:' docs/backend-vnext/refactoring/formal/plans/p5-5b-s8-handoff.md | awk '{print $2}')
test "$HEAD" = "$RH"      # publication tip：records_head 必须等于当前 HEAD
git add docs/backend-vnext/refactoring/formal/plans/p5-5b-s7-independent-review-8.md \
        docs/backend-vnext/refactoring/formal/plans/p5-5b-s8-handoff.md \
        docs/backend-vnext/refactoring/formal/plans/p5-5b-s7-acceptance.md
git commit --amend --no-edit
git status --short        # empty
```

注：`test` 在 `git commit --amend` **之前**执行；amend 将 `records_head` 落盘为 amend 前
`HEAD`（content seal）。gate 代码仍以 `candidate_head: 87c49763` 为准。

## Next step

```yaml
p5_5b_slice_exit: pending_closure
next_step: independent_acceptance_authority_for_slice_exit_declaration
p5_5c_authorized: no
production_deployment_authorized: no
```

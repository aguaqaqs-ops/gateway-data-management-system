# P5-5D-S4R2 Final Candidate Gate and Slice Handoff

状态：**S4R2 pass — slice exit authorized @ [p5-5d-s4r2-independent-acceptance.md](p5-5d-s4r2-independent-acceptance.md)；`delivery_recommendation: pass_recommended`（delivery 不签 slice exit）**

日期：2026-09-23

Owner：P5-5D Delivery

上游：[Archive Execution Plan §4 S4 / §6 / §7](p5-5d-archive-execution-plan.md)、
[S3 Stage Exit Acceptance](p5-5d-s3-stage-exit-acceptance.md)。本记录由
[S4R2 superseding acceptance record](p5-5d-s4r2-independent-acceptance.md) 绑定；旧的
[S4 acceptance record](p5-5d-s4-independent-acceptance.md) 保留为历史记录，但不再是当前证据。

```yaml
stage: P5-5D-S4R2-final-fresh-candidate-conjunction-and-independent-exit
candidate_head: af833695ef1c16b1ea0744d1b6eff6b5ada9924c
gate_tested_head: af833695ef1c16b1ea0744d1b6eff6b5ada9924c
tests_remediation_commit: af833695ef1c16b1ea0744d1b6eff6b5ada9924c
s3_stage_exit_acceptance: dcdb22e679
archive_implementation_binding: d61d37be97821f303e9083abe739618cebd96b46
supersedes_candidate: 05e0399fe950c115e4a24764dce4f6d2d49cb4bb
clean_status: yes_at_t3_t4_t5
container_rebuild_required: yes
container_reason: S4R2 final candidate fresh-build conjunction and current-HEAD provenance
container_gate_for_current_head: passed
five_package_static: pass
authoritative_runner: pass
compose_gate_project: gateway-p5-5d-s4r2-gate
prebuilt_used: no
p5_5d_s1_stage_exit: pass
p5_5d_s2_stage_exit: pass
p5_5d_s3_stage_exit: pass
p5_5d_slice_exit: pass
p5_5e_implementation_authorized: no
production_deployment_authorized: no
new_repository_effect_authorized: no
delivery_recommendation: pass_recommended
acceptance_record: docs/backend-vnext/refactoring/formal/plans/p5-5d-s4r2-independent-acceptance.md
```

## S4R2 supersession and candidate delta

候选 `05e0399fe950c115e4a24764dce4f6d2d49cb4bb` 的旧 handoff/acceptance 声称
`five_package_static: pass`，但该声明不可复现，已由本记录和 S4R2 acceptance record 显式
supersede。旧候选的 backend static 复核为 exit 1、3 个 F401：

```text
tests/support/http_shutdown_harness.py:19 — initialize_control_db unused
tests/test_submit_job_prepare.py:49 — BASELINE_HEAD unused
tests/test_submit_recovery.py:90 — BASELINE_HEAD unused
```

三处 import-only 删除已在单独提交 `af833695ef1c16b1ea0744d1b6eff6b5ada9924c` 完成；
没有恢复旧调用/断言，没有改生产代码、依赖、部署或测试分类。相对旧候选，新的 gate-tested
candidate 是 `af833695ef1c16b1ea0744d1b6eff6b5ada9924c`。

## F3 path disclosure

`05e0399fe9` 实际修改了以下 7 个既有测试文件。表中“预算”按 Execution Plan §3
S1–S3 的明确测试路径行判定，不把 `tests/**` 当作通配授权。

| `05e0399fe9` 文件 | 用途 | §3 S1–S3 预算 | 处理理由 |
| --- | --- | --- | --- |
| `vnext/backend/tests/support/baseline_fixtures.py` | 从 control DB 读取 scoped authoritative BaselineHead，供测试 seed 使用 | S2 明列 | 对齐 S1 DB authority 的测试材料 |
| `vnext/backend/tests/support/http_shutdown_harness.py` | 生产 HTTP submit/shutdown harness 使用指定 repository 的 DB Head | 超出 | tests-only；同源 `ProvisionedBaselineHeadRead`；未削弱断言 |
| `vnext/backend/tests/support/http_workspace_harness.py` | scoped submit workspace/preview/上传记录使用 DB Head，而不是全局常量 | 超出 | tests-only；对齐 S1 authority；未改变 production path 或断言 |
| `vnext/backend/tests/test_http_admission_shutdown_process.py` | SIGTERM/admission 测试把 seeded authoritative Head 传入请求 | 超出 | tests-only；与生产 `http/runtime.py` 使用同一 Head reader；断言保持 |
| `vnext/backend/tests/test_submit_job_prepare.py` | prepared submit accept path 使用当前 repository 的 Head | 超出 | tests-only；同源 `ProvisionedBaselineHeadRead`；未削弱断言 |
| `vnext/backend/tests/test_submit_recovery.py` | recovery/abort 场景使用 DB authoritative Head | 超出 | tests-only；对齐 S1 authority；未削弱断言 |
| `vnext/backend/tests/test_submit_transactions.py` | submit seed 写入 scoped Head/version facts 并使用 DB reader | S1/S2 明列 | 既有 owner 路径内的最小 authority 对齐 |

本轮 S4R2 新增的 3 个**文件变更**（不是新增测试路径；均为上述 7 个路径中的 import
清理）如下：

| S4R2 文件 | 本轮用途 | 结果 |
| --- | --- | --- |
| `vnext/backend/tests/support/http_shutdown_harness.py` | 删除已无调用点的 `initialize_control_db` import | 仅 1 行删除 |
| `vnext/backend/tests/test_submit_job_prepare.py` | 删除已无引用的 `BASELINE_HEAD` import | 仅 1 行删除 |
| `vnext/backend/tests/test_submit_recovery.py` | 删除已无引用的 `BASELINE_HEAD` import | 仅 1 行删除 |

5 个超出 §3 行的文件只承载测试 fixture/调用输入的 authority 对齐：它们通过
`gateway_backend.infrastructure.control_db.sqlite_mapping.ProvisionedBaselineHeadRead` 读取
control DB，而不是引入新的 reader；该 reader 与 production `http/runtime.py` 的 authority
路径同源。没有新增测试、没有放宽或删除断言、没有扩大生产预算。该说明不是对历史 S1 owner
签署的替代。

## R2 — S1 record-gap waiver

仓库历史中没有 `p5-5d-s1-*` handoff/review 文档；`S1 stage exit: pass` 是在
`6c99810779` 相关记录中顺带写入的，现有材料没有可独立核对的 S1 candidate HEAD、focused
gate 原始结果、initial-empty owner sign-off 和 v5 Baseline owner sign-off。本轮不伪造这些
历史签署，S4R2 acceptance record 明确记录该缺口并请求独立 acceptance/用户决定是否接受下列
范围化豁免：

1. S3 focused gate 覆盖 production wiring/readiness/architecture 以及 Archive HTTP owner
   的 authority 接缝；
2. 本轮 T4 权威 runner 对 backend 全部 2519 项、以及 T5 真实三进程 conjunction，重新覆盖
   S1 Baseline authority、initial-empty consumer 和 v5 schema 未发布边界所能到达的行为面；
3. 因此本轮只豁免“缺少独立 S1 文档/owner 签署记录”，不把豁免表述为历史签署已存在，也不
   自动改变 `p5_5d_s1_stage_exit: pass` 的既有阶段状态。

## Phase 1 — Five-package static (T3)

命令：

```bash
for pkg in backend repository_service repository_client repository_contracts shared_kernel; do
  (cd vnext/$pkg && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done
```

每包 raw output、exit code 和 mypy 文件数：

```text
=== backend: ruff check . ===
All checks passed!
backend ruff exit=0
=== backend: mypy ===
Success: no issues found in 421 source files
backend mypy exit=0

=== repository_service: ruff check . ===
All checks passed!
repository_service ruff exit=0
=== repository_service: mypy ===
Success: no issues found in 198 source files
repository_service mypy exit=0

=== repository_client: ruff check . ===
All checks passed!
repository_client ruff exit=0
=== repository_client: mypy ===
Success: no issues found in 26 source files
repository_client mypy exit=0

=== repository_contracts: ruff check . ===
All checks passed!
repository_contracts ruff exit=0
=== repository_contracts: mypy ===
Success: no issues found in 15 source files
repository_contracts mypy exit=0

=== shared_kernel: ruff check . ===
All checks passed!
shared_kernel ruff exit=0
=== shared_kernel: mypy ===
Success: no issues found in 34 source files
shared_kernel mypy exit=0
```

五包 ruff/mypy 均 exit 0；无 F401。

## Phase 2 — Authoritative runner (T4)

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

| Package | Raw result | Duration / notes |
| --- | --- | --- |
| shared_kernel | 242 passed | 0.66s |
| repository_contracts | 152 passed | 0.17s |
| repository_client | 154 passed | 1.70s |
| backend | 2519 passed | 485.89s；1 Starlette deprecation warning |
| repository_service (parallel) | 1678 passed, 1 skipped | 15.75s |
| repository_service (serial) | 205 passed, 1679 deselected | 349.69s |

**runner exit code: 0。**T3/T4 运行期间 identity helper 均 exit 0，工作区 clean；五锁 SHA
前后完全一致。serial 没有 `ProvenanceError: worktree is dirty`。

## Phase 3 — Fresh build (T5)

```bash
./vnext/scripts/build-repository-service-image.sh
docker compose -f vnext/deploy/compose.yaml build backend worker
```

两条命令均 exit 0。repository-service 构建实际绑定：

| Service | Immutable image ID | Revision / build identity |
| --- | --- | --- |
| repository-service | `sha256:3ced4f022e0fcff1a4b0ae5c071c018c8fdf826fb820e83b916772435ecde84d` | `org.opencontainers.image.revision=af833695ef1c16b1ea0744d1b6eff6b5ada9924c`；build input `4d1dc010deff17249bb2aa54b7563e7a86959096` |
| backend | `sha256:e7a7c10f3f798059cd6fa92448352e298dc1660d2b0cfa5f2416d5ad8aa30df7` | backend build export manifest `sha256:f2b1cdf06bc59ec7660fd246828e0ae3263c69448243ee88d897219b9f48a32f` |
| worker | `sha256:73680e40265b5b109ecdc987d2f0607b8ab29218ab85fb3bfc1098c6edb49cc6` | worker build export manifest `sha256:ff59c02718151096bb8b97861724baf8cd8551cb0c7537a6b953316fcc5198b3` |

backend/worker 的 BuildKit 层命中，且其 image Created 时间早于 S4R2 commit；因此没有把 tag
存在当作 fresh-build 证明，额外在两个实际镜像内执行：

```bash
cd /app/backend/src
find . -name '*.py' -type f | LC_ALL=C sort | while read -r p; do
  printf '%s\t%s\n' "$p" "$(sha256sum "$p" | cut -d' ' -f1)"
done | sha256sum
```

结果 backend 与 worker 都为
`b37e8b3ec48fad1144505a6756e79ae33f71cfeb8c3356f4f2a4c85e235f6285`，等于本地
`vnext/backend/src`；repository-service OCI revision 则直接等于新候选 SHA。

## Phase 4 — Conjunction (T5, final report run)

首次按要求的命令已 exit 0；为取得逐项耗时，同一候选/同一 project 又运行了同一命令并加上
`--durations=0 --junitxml=/tmp/gateway-p5-5d-s4r2-conjunction.xml`。两次均 **6 passed,
0 skipped**。最终报告 run：338.14s，exit 0。

```bash
cd vnext/backend
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5d-s4r2-gate \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
GATEWAY_COMPOSE_GATE_PREBUILT=0 \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
```

| nodeid | elapsed | result |
| --- | ---: | --- |
| `tests/test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect` | 141.166s | passed |
| `tests/test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey` | 77.883s | passed |
| `tests/test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart` | 26.438s | passed |
| `tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` | 74.513s | passed |
| `tests/test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint` | 1.458s | passed |
| `tests/test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service` | 15.250s | passed |

## §6.3 provenance record

统一 source-tree recipe：

```bash
git ls-files 'vnext/**' | LC_ALL=C sort | while read -r p; do
  printf '%s\t%s\n' "$p" "$(sha256sum "$p" | cut -d' ' -f1)"
done | sha256sum
```

| 证据 | 值 |
| --- | --- |
| Candidate / gate-tested Git HEAD | `af833695ef1c16b1ea0744d1b6eff6b5ada9924c` |
| Worktree at T3/T4/T5 | clean；identity helper exit 0 |
| Source-tree file count | 905 |
| Source-tree digest | `ba627192eb47da1f1bf1b71ee32c982e7cb55c739f5a30f86c43cd6d4a830ba5` |
| Backend `src` py digest | `b37e8b3ec48fad1144505a6756e79ae33f71cfeb8c3356f4f2a4c85e235f6285` |
| backend `uv.lock` | `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
| repository_service `uv.lock` | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| repository_client `uv.lock` | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| repository_contracts `uv.lock` | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| shared_kernel `uv.lock` | `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
| `vnext/deploy/compose.yaml` | `f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0` |
| Build identity helper | `build_input_revision=4d1dc010deff17249bb2aa54b7563e7a86959096`; package source label `sha256:62a38a0881926ba0afd15fb22db292c15be19318649562033f4b9c3f91d642cf` |
| Running provenance (authoritative) | [p5-5d-s4r2-compose-gate-provenance.json](p5-5d-s4r2-compose-gate-provenance.json) |
| Local last-run overlay (gitignored, non-authoritative) | `vnext/backend/tests/support/.last_compose_gate_provenance.json` |

最终报告 run 的实际运行容器：

| Service | Container ID | `.Image` immutable ID |
| --- | --- | --- |
| repository-service | `df856f8a770d` | `sha256:3ced4f022e0fcff1a4b0ae5c071c018c8fdf826fb820e83b916772435ecde84d` |
| backend | `300fbd493f27` | `sha256:e7a7c10f3f798059cd6fa92448352e298dc1660d2b0cfa5f2416d5ad8aa30df7` |
| worker | `a2b9fa9107b0` | `sha256:73680e40265b5b109ecdc987d2f0607b8ab29218ab85fb3bfc1098c6edb49cc6` |

## Container decision record

```text
Current HEAD: af833695ef1c16b1ea0744d1b6eff6b5ada9924c (code candidate; docs-only record follows)
Container rebuild required: yes
Reason: S4R2 final candidate and current-HEAD fresh-build/conjunction boundary
Last verified image revision: af833695ef1c16b1ea0744d1b6eff6b5ada9924c (repository-service OCI label)
Last verified source-tree/image IDs: ba627192…30ba; repository 3ced4f…de84d; backend e7a7c10…30df7; worker 73680e4…49cc6
Current gate: passed for gate-tested candidate; p5_5d_slice_exit signed @ p5-5d-s4r2-independent-acceptance.md (2026-09-23)
Deferred nodeids: none
Required execution point: none for 5D slice exit; production deployment or Repository effect remain unauthorized
```

5D Archive 仍为零 Repository effect；v5 schema 未发布；本轮没有 deployment、生产发布或新的
Repository effect。5E 未进入实现范围；其未跟踪 review 文档已原样纳入本轮 docs-only 提交。

## Independent countersign

```yaml
delivery_recommendation: pass_recommended
review: delivery_gate_evidence_complete
acceptance_record: docs/backend-vnext/refactoring/formal/plans/p5-5d-s4r2-independent-acceptance.md
p5_5d_slice_exit: pass
slice_exit_acceptance: docs/backend-vnext/refactoring/formal/plans/p5-5d-s4r2-independent-acceptance.md
slice_exit: not_signed_by_delivery
production_deployment_authorized: no
new_repository_effect_authorized: no
```

Delivery 不代签 `p5_5d_slice_exit`、`production_deployment_authorized` 或
`new_repository_effect_authorized`；slice-exit 签名已由独立 acceptance context 在复审通过后于
2026-09-23 落盘（见 S4R2 acceptance record），delivery 自身未签署。

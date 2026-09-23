# P5-5D-S4R2 Superseding Independent Slice Exit Acceptance Record

状态：**PASS — `p5_5d_slice_exit: pass`（independent acceptance context 复审签署，2026-09-23）**

日期：2026-09-23

本记录是 S4R2 的 superseding evidence/acceptance record，由 delivery 产生证据，不能替代
独立 acceptance authority。旧的 [P5-5D-S4 Independent Slice Exit Acceptance](p5-5d-s4-independent-acceptance.md)
不改写；它绑定的候选 `05e0399fe950c115e4a24764dce4f6d2d49cb4bb` 上的
`five_package_static: pass` 已复核为**不可复现并明确 supersede**。新证据只绑定
`af833695ef1c16b1ea0744d1b6eff6b5ada9924c`。

上游：[S4R2 Handoff](p5-5d-s4-handoff.md)、[Execution Plan §1 / §4 S4 / §6.3](p5-5d-archive-execution-plan.md)、
[S3 Stage Exit Acceptance](p5-5d-s3-stage-exit-acceptance.md)。

```yaml
record_kind: superseding_p5_5d_slice_exit_acceptance_evidence
supersedes: docs/backend-vnext/refactoring/formal/plans/p5-5d-s4-independent-acceptance.md
superseded_candidate_head: 05e0399fe950c115e4a24764dce4f6d2d49cb4bb
superseded_claim: five_package_static_pass_not_reproducible
acceptance_kind: p5_5d_slice_exit
acceptance_authority: independent_acceptance_context_or_explicit_user_authorization
candidate_head: af833695ef1c16b1ea0744d1b6eff6b5ada9924c
gate_tested_head: af833695ef1c16b1ea0744d1b6eff6b5ada9924c
tests_remediation_commit: af833695ef1c16b1ea0744d1b6eff6b5ada9924c
archive_implementation_binding: d61d37be97821f303e9083abe739618cebd96b46
decision: pass
findings_closed: [S4-submit-integration-baseline-fix-and-static-recheck]
review_findings_open: []
p5_5d_s1_stage_exit: pass
p5_5d_s2_stage_exit: pass
p5_5d_s3_stage_exit: pass
p5_5d_slice_exit: pass
r2_s1_record_gap: waiver_accepted_by_independent_acceptance
p5_5e_implementation_authorized: no
production_deployment_authorized: no
new_repository_effect_authorized: no
delivery_signature: absent
```

## Superseded static declaration

在旧候选 `05e0399fe9` 上，backend 受控命令
`../scripts/uv-consume.sh -C . run ruff check .` exit 1，恰有三项 F401：

```text
tests/support/http_shutdown_harness.py:19 — initialize_control_db unused
tests/test_submit_job_prepare.py:49 — BASELINE_HEAD unused
tests/test_submit_recovery.py:90 — BASELINE_HEAD unused
```

因此旧 acceptance 中的 `five_package_static: pass` 不能作为 S4 证据。S4R2 只在三处测试
文件删除未使用 import 后重新冻结，未恢复调用、未恢复常量用法、未改 production code。

## T3 — Five-package static

完整 raw output、每包 exit code 和 mypy 文件数见 [S4R2 Handoff §Phase 1](p5-5d-s4-handoff.md)。
结果为：

| Package | ruff raw result / exit | mypy raw result / exit |
| --- | --- | --- |
| backend | `All checks passed!` / 0 | `Success: no issues found in 421 source files` / 0 |
| repository_service | `All checks passed!` / 0 | `Success: no issues found in 198 source files` / 0 |
| repository_client | `All checks passed!` / 0 | `Success: no issues found in 26 source files` / 0 |
| repository_contracts | `All checks passed!` / 0 | `Success: no issues found in 15 source files` / 0 |
| shared_kernel | `All checks passed!` / 0 | `Success: no issues found in 34 source files` / 0 |

## T4 — Authoritative runner

`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh` exit **0**，且 clean worktree：

| Package | Result |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend | 2519 passed，1 warning |
| repository_service parallel | 1678 passed，1 skipped |
| repository_service serial | 205 passed，1679 deselected |

五锁 SHA 与 `compose.yaml` SHA 前后一致；没有 `ProvenanceError: worktree is dirty`。

## T5 — Fresh build and conjunction

两条 build 命令均 exit 0：

```bash
./vnext/scripts/build-repository-service-image.sh
docker compose -f vnext/deploy/compose.yaml build backend worker
```

repository-service 的 `org.opencontainers.image.revision` 是新候选完整 SHA；backend/worker
构建命中缓存且 Created 早于候选提交，故已完成镜像内 source digest 对等证明，三镜像不是以 tag
存在作为唯一证据。详细 build/export manifest、镜像内 digest 和最终运行容器见
[S4R2 Handoff Phase 3 / §6.3](p5-5d-s4-handoff.md)。

Conjunction 使用 project `gateway-p5-5d-s4r2-gate`、`GATEWAY_COMPOSE_GATE_PREBUILT=0`，
两次均 **6 passed / 0 skipped / exit 0**。最终报告 run 为 338.14s，逐项耗时：

| nodeid | elapsed | result |
| --- | ---: | --- |
| `test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect` | 141.166s | passed |
| `test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey` | 77.883s | passed |
| `test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart` | 26.438s | passed |
| `test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` | 74.513s | passed |
| `test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint` | 1.458s | passed |
| `test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service` | 15.250s | passed |

## Binding and provenance

| 证据 | 值 |
| --- | --- |
| Candidate / gate-tested HEAD | `af833695ef1c16b1ea0744d1b6eff6b5ada9924c` |
| Worktree during T3/T4/T5 | clean；identity helper exit 0 |
| Source-tree | 905 files；`ba627192eb47da1f1bf1b71ee32c982e7cb55c739f5a30f86c43cd6d4a830ba5` |
| Backend `src` py digest | `b37e8b3ec48fad1144505a6756e79ae33f71cfeb8c3356f4f2a4c85e235f6285` |
| Five lock SHA / compose SHA | 与 handoff §6.3 列值一致，未漂移 |
| repository-service image | `sha256:3ced4f022e0fcff1a4b0ae5c071c018c8fdf826fb820e83b916772435ecde84d`；OCI revision = candidate |
| backend image | `sha256:e7a7c10f3f798059cd6fa92448352e298dc1660d2b0cfa5f2416d5ad8aa30df7` |
| worker image | `sha256:73680e40265b5b109ecdc987d2f0607b8ab29218ab85fb3bfc1098c6edb49cc6` |
| Running provenance (authoritative) | [p5-5d-s4r2-compose-gate-provenance.json](p5-5d-s4r2-compose-gate-provenance.json) |
| Local last-run overlay (gitignored, non-authoritative) | `vnext/backend/tests/support/.last_compose_gate_provenance.json` |
| Final container IDs | repository-service `df856f8a770d`; backend `300fbd493f27`; worker `a2b9fa9107b0` |
| Backend/worker content proof | Each image digest equals local `b37e8b3e…6285` |

## R2 — S1 documentation-gap waiver

历史中没有 `p5-5d-s1-*` handoff/review 文档；S1 的 candidate HEAD、focused gate 原始记录、
initial-empty owner sign-off 和 v5 Baseline owner sign-off 未能从现有记录独立核对。本记录不把
`6c99810779` 的顺带 `S1 stage exit: pass` 改写成这些缺失签署。

本轮提出的有限豁免覆盖理由是：S3 focused gate 已覆盖 production wiring/readiness/architecture
的 authority 接缝；T4 backend 全量 runner 重新执行 S1 consumer；T5 conjunction 重新执行真实
provisioning、三进程 restart 和 v5 未发布边界。豁免对象仅为历史文档/owner-sign-off 缺口，
不扩大源码预算、不把历史 sign-off 补写成已存在。是否接受该豁免，仍需独立 acceptance context
或用户明确决定。

## Container decision record

```text
Current HEAD: af833695ef1c16b1ea0744d1b6eff6b5ada9924c (gate-tested code candidate)
Container rebuild required: yes
Reason: S4R2 final candidate fresh-build conjunction and current-HEAD provenance
Last verified image revision: af833695ef1c16b1ea0744d1b6eff6b5ada9924c
Last verified source-tree/image IDs: ba627192…30ba; 3ced4f…de84d; e7a7c10…30df7; 73680e4…49cc6
Current gate: passed for gate-tested candidate; p5_5d_slice_exit signed (independent acceptance context, 2026-09-23)
Deferred nodeids: none
Required execution point: none for 5D slice exit; production deployment or Repository effect remain unauthorized
```

## Independent re-review evidence（independent acceptance context，2026-09-23）

- T3 独立复跑：五包 ruff + mypy 全部 exit 0（backend ruff `All checks passed!`，mypy 421 files）。
- Source-tree digest 按 §6.3 recipe 复算 4 次、5 种变体均得
  `ba627192eb47da1f1bf1b71ee32c982e7cb55c739f5a30f86c43cd6d4a830ba5`（905 文件）；backend src
  digest / 五锁 / compose SHA 全部匹配。
- 镜像绑定：三个 image ID 存在且 tag 映射正确；repository-service OCI revision = 候选 SHA；
  backend/worker 与上一轮镜像的 Config 唯一差异为 `com.docker.compose.project` label，两镜像内
  src digest 均等于本地 `b37e8b3e…6285`；权威 provenance 见
  [p5-5d-s4r2-compose-gate-provenance.json](p5-5d-s4r2-compose-gate-provenance.json)（gitignored
  `.last_compose_gate_provenance.json` 仅为本地 last-run，可能已被无关运行覆盖）；conjunction
  junitxml 6/6 PASS、0 skipped，逐项耗时与记录吻合。
- T4 独立复跑（独占窗口、全量输出）：**exit 0** —— 242 / 152 / 154 / **2519** / 1678+1 skipped /
  serial **205**，与交付记录逐项一致。首次复跑因第三方并发 runner 污染（共享宿主 8000 与 dolt
  PID 空间，serial 4 项 dolt-PID 断言失败）清场后复跑全绿；该污染与候选无关。
- 据此接受 R2 范围化豁免（仅历史 S1 文档/签署缺口，行为面已由 T4/T5 覆盖）与 F3 路径披露，
  无未关闭 finding。

## Acceptance boundary and signature

Archive 仍为零 Repository effect；v5 schema 仍未发布；本记录不授权 5E implementation、production
deployment 或 `new_repository_effect_authorized`。delivery 不能签署本记录中的 slice exit；本记录
的 slice exit 由独立 acceptance context 在复审通过后签署。

```yaml
acceptance_signature:
  status: signed
  signer: independent_acceptance_context
  signed_date: 2026-09-23
  basis: independent_re_review_static_runner_provenance_reproduced
p5_5d_slice_exit: pass
production_deployment_authorized: no
new_repository_effect_authorized: no
```

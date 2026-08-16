# P2-R6-S7 — Independent Lifecycle Re-review

状态：`pass`（F-001/F-002 已关闭；允许进入 S7-11，不授予 S7 exit）

日期：2026-08-16

本记录是 S7-10 blocker repair 后的独立只读 rereview。审核对象为
[p2-r6-s7-step-10-blocker-repair.md](p2-r6-s7-step-10-blocker-repair.md)、修复提交
`af36c325403d2173b5e4dc5b2ca69fa40d8b7812`、四个 exact Compose nodeid 的 gate 输出以及
当前 docs-only descendant `5f474ce2ccf15f11ea07f263edf3fb04c771d410`。审核未修改
production、test、Compose 或 Docker 输入，未启动 S7-11。

权威执行计划：[P2-R6-S7 Compose Lifecycle Execution Plan](../formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md) §12
此前审核：[p2-r6-s7-step-10-lifecycle-review.md](p2-r6-s7-step-10-lifecycle-review.md)
修复证据：[p2-r6-s7-step-10-blocker-repair.md](p2-r6-s7-step-10-blocker-repair.md)

## Review identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_head: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
container_validated_code_sha: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
container_validated_code_is_ancestor: yes
docs_only_descendant_after_container_gate: yes
review_worktree_clean_at_start: yes
production_code_changed_by_review: no
compose_or_docker_input_changed_by_review: no
phase_2_complete: no
```

The service image is `gateway-repository-service:af36c325403d` with ID
`sha256:57f5622c134a734dd2c8ab34bc7971e4af5f5b088d09812316213accf77e64af`. The ephemeral client
image is `gateway-repository-client-e2e:local` with ID
`sha256:051b4bfe982c0c8d4a8b41cfbcebcc3f22a7f5eb78ead8ec3bf1f5abb2a815db`. Both labels bind
candidate `af36c325403d2173b5e4dc5b2ca69fa40d8b7812`; service and client lock identities are
`6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` and
`6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` respectively.

## Verification performed

- Exact S7 nodeid collection: `4 tests collected`.
- `tests/test_compose_lifecycle_harness.py`: `85 passed` under `-m unit`.
- Touched harness ruff: passed.
- `repository_service` mypy: passed (`195 source files`).
- `git diff --check`: passed.
- No new Docker gate was run during this read-only rereview; all gate results below are the
  independently recorded repair evidence.

## Same-candidate nodeid review

| nodeid | result | elapsed | project(s) | candidate/image identity |
| --- | --- | ---: | --- | --- |
| `tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay` | `PASSED` | 27.84s | `gateway-p2r6-s7-import-bd51c9b234aa` | `af36c325` / `sha256:57f5622c…` |
| `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network` | `PASSED` | 27.05s | `gateway-p2r6-s7-inside-036493ec7ae6` | `af36c325` / `sha256:57f5622c…`; client `sha256:051b4bfe…` |
| `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host` | `PASSED` | 22.57s | `gateway-p2r6-s7-gatehost-cb4de7e5929a` | `af36c325` / `sha256:57f5622c…`; host runner bound to `af36c325` + client lock |
| `tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle` | `PASSED` | 71.57s | `gateway-p2r6-s7-lifecycle-5dee395367b0`, `gateway-p2r6-s7-restored-8689c1b304e7` | `af36c325` / `sha256:57f5622c…`; host runner bound to `af36c325` + client lock |

`all_nodeids_current_candidate: yes`. Each nodeid ran independently with its own project,
volume and token. The inside-network endpoint was the Compose DNS name; the gate-host endpoint was
the discovered Linux bridge IPv4. The repair evidence reports no published host port and no
remaining S7 containers, networks or volumes after each run.

## F-001 re-review — candidate binding

**Closed.** All four exact nodeids report candidate
`af36c325403d2173b5e4dc5b2ca69fa40d8b7812` and the same Service image ID. The client image labels
and gate-host runner identity bind to the same candidate and locked client project. The later
`5f474ce` commit is docs-only and therefore does not invalidate the container evidence.

## F-002 re-review — residual inventory evidence

**Closed.** Every project teardown emits both `teardown_scan` and `residual_inventory`. Import,
inside-network and gate-host each report zero `container_dolt`, `query_temps`, containers, networks,
volumes, hold containers, Dolt delta, check-temp homes, client PIDs, host threads and work-root
directories. The restored lifecycle reports the same zero counts independently for both source and
restored projects. `leftover_after_gate: none` is recorded after each nodeid.

The repair commit also adds focused unit coverage for the formatting and cleanup print path; the
review verification observed `85 passed` for the harness unit module.

## Lifecycle and boundary questions

| invariant | result | basis |
| --- | --- | --- |
| force-recreate restart uses the same volume | pass | lifecycle gate reports restart summary identical to fresh and uses the existing force-recreate helper |
| hold/copy/check/start ordering | pass | lifecycle evidence reports ready hold, whole-root copy, passed check before restored startup |
| public c0/c1/c2 oracle and mutation isolation | pass | consumer summaries show distinct c0/c1/c2 with `main=c2`; restored facts equal snapshot facts and mutation is absent |
| inside-network and gate-host topology | pass | DNS and bridge endpoints differ; no host port is published |
| provenance and lock identity | pass | candidate, source digest, image IDs and both lock identities agree |
| S7/S10 boundary | pass | `S7_exit: no`, `phase_2_complete: no`, S7-11 and S8/S9/S10 remain deferred |

## Verdict

```yaml
review_status: pass
reviewed_head: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
reviewed_container_code_sha: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
finding_count: 0
blocker_count: 0
f001_candidate_binding: closed
f002_residual_inventory: closed
all_four_nodeids_current_candidate: yes
zero_process_thread_query_temp_residual: yes
zero_container_network_volume_residual: yes
independent_lifecycle_review: pass
allow_final_s7_gate: yes
S7_exit: no
S8_ready: no
production_retest_required: yes
phase_2_complete: no
next: S7-11 final S7 candidate/container gate and handoff
```


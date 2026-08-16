# P2-R6-S7 — Independent Lifecycle Review

状态：`fail`（独立审核发现阻塞项；不授予 S7-11 final gate）

日期：2026-08-16

本记录是 S7-10 的独立只读审核。审核对象为 S7-2/S7-3 harness 与 nodeid 实现、S7-5
provisional image、S7-6/S7-7 directed gates、S7-8/S7-9 restored lifecycle 以及对应
evidence。审核没有修改 production、test、Compose 或 Docker 输入；新增本文件只记录审核
结论。旧 image 结果没有被升级为当前 candidate 的验证。

权威设计：[P2-R6-S7 Compose Lifecycle Design](../formal/plans/p2-r6-s7-compose-lifecycle-design.md)
权威执行计划：[P2-R6-S7 Compose Lifecycle Execution Plan](../formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md) §12
S7-5 image：[p2-r6-s7-step-5-provisional-image.md](p2-r6-s7-step-5-provisional-image.md)
S7-6 gate：[p2-r6-s7-step-6-import-restart-replay.md](p2-r6-s7-step-6-import-restart-replay.md)
S7-7 gate：[p2-r6-s7-step-7-pinned-read.md](p2-r6-s7-step-7-pinned-read.md)
S7-9 gate：[p2-r6-s7-step-9-restored-lifecycle.md](p2-r6-s7-step-9-restored-lifecycle.md)

## Review identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_head: a396a926e9a99306efd2c60be4da64623ead1f05
reviewed_commit_range: 10f84a19..a396a926e9a99306efd2c60be4da64623ead1f05
review_worktree_clean_at_start: yes
production_code_changed_by_review: no
compose_or_docker_input_changed_by_review: no
public_contract_changed: no
phase_2_complete: no
```

The current HEAD is the S7-9 evidence documentation commit. The lifecycle implementation is
`da1460613bc330c4878785de74decff0a7d97d26`; the earlier directed gates remain on
`eeadbdd38ab468667b2b9ebbdfffae39ddc62771`.

## Verification performed

- Exact S7 nodeid collection: `4 tests collected`.
- Harness/read focused unit tests: `118 passed`.
- `git diff --check`: passed.
- No new Docker gate was run during this read-only review.

## Nodeid result and provenance table

| nodeid | recorded result | candidate / service image | client identity | review result |
| --- | --- | --- | --- | --- |
| `tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay` | pass | `eeadbdd38ab468667b2b9ebbdfffae39ddc62771` / `sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606` | same S7-5 client image | recorded |
| `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network` | pass | `eeadbdd38ab468667b2b9ebbdfffae39ddc62771` / `sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606` | `sha256:5b06a495979442437e11261d2506919e656d1fcbb65a56c56970e045d80de41e` | recorded |
| `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host` | pass | `eeadbdd38ab468667b2b9ebbdfffae39ddc62771` / `sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606` | `host-runner:candidate=eeadbdd38ab468667b2b9ebbdfffae39ddc62771;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` | recorded |
| `tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle` | pass | `da1460613bc330c4878785de74decff0a7d97d26` / `sha256:c34d2e99587981e4b9925359f7db338a261f2446fead477b0784e1fcd4f97f9e` | `host-runner:candidate=da1460613bc330c4878785de74decff0a7d97d26;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` | recorded |

The service lock identity is `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`;
the client lock identity is `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954`.
The image labels and source-tree digests agree within each recorded gate, but the four nodeids do
not share one candidate.

## Review questions

| invariant | result | basis |
| --- | --- | --- |
| restart is force-recreate on the same volume | pass | `recreate_started_service` uses `up -d --no-build --force-recreate`; lifecycle evidence says restart facts equal fresh |
| restored target is independently empty | pass | source and restored projects allocate distinct volumes; empty assertion precedes copy |
| hold before whole-root copy; check before restored startup | pass | lifecycle implementation orders ready hold, copy, controlled hold exit, restore, check, then Service startup |
| c0/c1/c2 and mutation facts are public/reproducible | pass | the locked `versioned_fixture_consumer` supplies all summaries; restored mutation ref returns 404 |
| inside-network and gate-host paths differ and are host-port-free | pass | DNS service endpoint and discovered bridge IPv4 endpoint differ; rendered config/evidence report no published port |
| image/client/source/lock provenance is bound | pass within each gate | immutable image IDs, candidate labels, source digest and lock identities are recorded |
| S7/S10 deferred scope and Phase 2 boundary are explicit | pass | evidence keeps `S7_exit: no`, `phase_2_complete: no`, and S8/S9/S10 deferred |
| process/thread/Dolt/query-temp/container/network/volume residuals are zero per nodeid | **blocker** | lifecycle evidence only records no project containers/networks/volumes; the required per-node process/thread/Dolt/query-temp inventory is absent |
| all four nodeids ran on the same provisional candidate | **blocker** | three directed nodeids ran on `eeadbdd`/`b8615ac…`; lifecycle ran on `da146061`/`c34d2e…` |

## Findings

### F-001 — Four nodeids are split across provisional candidates (blocker)

S7-10 explicitly requires one provisional candidate for all four exact nodeids. S7-6/S7-7
evidence is bound to `eeadbdd38ab468667b2b9ebbdfffae39ddc62771` and service image
`sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606`, while S7-9 is bound to
`da1460613bc330c4878785de74decff0a7d97d26` and service image
`sha256:c34d2e99587981e4b9925359f7db338a261f2446fead477b0784e1fcd4f97f9e`. The S7-9 record
correctly says `all_nodeids_current_candidate: no`; that is a gate prerequisite failure, not a
partial aggregate pass.

Remediation is to rerun the three directed nodeids on the candidate selected for the final S7
boundary, preserving their independent project/resource inventories. Do not reuse the old image
as current-candidate evidence.

### F-002 — Lifecycle evidence does not expose the required residual inventory (blocker)

The lifecycle record reports zero project containers, networks and volumes, but does not provide
the required per-node results for host processes/threads, container Dolt children, query-temp roots,
and snapshot-check temporary homes. The harness contains baseline assertions for these resources,
but S7's evidence contract requires the result inventory itself; code inspection cannot substitute
for a per-node gate record. The lifecycle gate must be rerun or its captured evidence completed with
the exact zero counts and baseline comparison for source and restored projects.

## Residual risk and boundary

The recorded lifecycle behavior is otherwise consistent with S4 whole-root semantics: the source
Service is stopped before `hold`, the target is proved empty, `check` succeeds while the restored
Service is stopped, and the post-snapshot mutation is absent after restore. These facts do not close
the two findings above. This review does not authorize a production retest, S7 exit, S8 readiness,
or any Phase 2 completion claim.

## Verdict

```yaml
review_status: fail
reviewed_head: a396a926e9a99306efd2c60be4da64623ead1f05
finding_count: 2
blocker_count: 2
all_four_nodeids_same_provisional_candidate: no
public_oracle: pass
restore_ordering: pass
network_boundary: pass
provenance_within_each_gate: pass
cleanup_evidence: incomplete
allow_final_s7_gate: no
production_code_changed_by_review: no
container_rebuild_required: yes
container_rebuild_reason: rerun all four exact nodeids on one final S7 candidate
phase_2_complete: no
next: return to S7-6/S7-7 evidence ownership and S7-11 candidate gate after remediation
```


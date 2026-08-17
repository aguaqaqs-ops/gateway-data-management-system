# P2-R6-S9 Independent Candidate Seal Review — Rerun

状态：`pass`

日期：2026-08-17

本记录是新的 S9-5 独立只读复审。前一份失败审核
[p2-r6-s9-candidate-seal-review.md](p2-r6-s9-candidate-seal-review.md) 保留原样，
其 finding 不被覆盖。复审对象是 S9-3 reporting-only 证据重跑、新 S9-4 packet、candidate
identity、provisional image labels、五组 old-reference raw 文件、S8 carried evidence 和
S10 deferred scope。复审没有修改 candidate、source/test/build input、Docker/Compose、image
或 handoff。

权威步骤：[P2-R6-S9 Final Candidate Seal Execution Plan](../formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md) §7

失败审核：[p2-r6-s9-candidate-seal-review.md](p2-r6-s9-candidate-seal-review.md)

S9-3：[p2-r6-s9-step-3-no-ignore-regression.md](p2-r6-s9-step-3-no-ignore-regression.md)

S9-4：[p2-r6-s9-step-4-candidate-seal-packet.md](p2-r6-s9-step-4-candidate-seal-packet.md)

## Review identity

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 71da506171d01bbccdf2c54137949cdd0bff234e
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s8_handoff_head: 71da506171d01bbccdf2c54137949cdd0bff234e
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
review_kind: independent_read_only_seal_review_rerun
prior_failed_review_blob_sha: 97b3856d0c2f309ec538ebef50e503b3a6481dcc
reviewed_s9_3_blob_sha: 784e6cf82defe8e7c7d641b51670bac9feb2cace
reviewed_s9_4_blob_sha: 0546ad3716809ff5fb65f7f7357df2caebfb65c8
authoritative_log_sha256: 65fa698473e997ec1a97a9f3fbc342465542c1e7cd47fcd881be0607e5506a7f
superseded_quiet_log_sha256: 93e5224df5de211ff8e81cef665ee39072759dac52689c35602539bf93bd5ede
preserved_fail_1_log_sha256: 80d7691e777f9b5ebe6b02da6026edf6cdae895017106f9f8e5cc7938c7aba7d
candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_worktree_clean_at_review: yes
production_code_changed_by_review: no
test_or_build_input_changed_by_review: no
image_built_or_changed_by_review: no
handoff_changed_by_review: no
phase_2_complete: no
```

`documentation_head_sha`/`s8_handoff_head` remains documentation-only. The candidate checkout
still reports `HEAD=2ef884278b4998dde1e5fe224532c89b7a0cd73a` and empty porcelain. The identity
helper remains:

```text
build_input_revision=3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256=sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256=6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
```

The candidate-bound provisional image remains Service
`sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6` and client
`sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b`; remote labels match
the candidate, build-input, source-tree and lock identities. These remain S9 provisional images,
not S10 production provenance.

## Closure of prior findings

### Prior P1 — Individual Docker nodeid pass evidence

**Closed.** S9-3 now records the reporting-only command
`./vnext/scripts/run-tests.sh -vv -s`. The script's fixed package/serial selection is unchanged;
`-vv -s` only exposes pytest nodeids and harness stdout. The authoritative log contains one
`PASSED` for each required nodeid, rather than relying on aggregate arithmetic:

| nodeid | authoritative log evidence |
| --- | --- |
| `test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay` | lines 3983–3986 |
| `test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network` | lines 4146–4153 |
| `test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host` | lines 4154–4161 |
| `test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle` | lines 4162–4178 |
| `test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up` | lines 3962–3964 |
| `test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up` | lines 3965–3967 |
| `test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up` | lines 3968–3970 |
| `test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up` | lines 3971–3973 |

The quiet log is explicitly superseded and retained; the fail-1 log is preserved.

### Prior P1 — Per-node resource inventory

**Closed.** The same authoritative log has nine `residual_inventory` rows: one for each of the
eight required nodeids, plus the second project owned by the restored-lifecycle nodeid. Each row
reports `containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0
host_threads=0 work_root_dirs=0`; each is preceded by its `teardown_scan`. S9-4 reproduces the
nine project identities and zero fields at lines 140–160 and separately records aggregate
`gateway-p2r6` zero state at lines 162–180.

### Prior P2 — Repair ledger consistency

**Closed.** S9-3 and S9-4 now agree on the preserved first failure, the environment-only `:local`
retag/unset repair, `source_or_build_input_repairs: none`, and `repairs: environment-only`. No
source, test, dependency, build-input or container-boundary change occurred.

## Gate review

**Pass.** The new S9-3 log reports the required six suite rows: `242/242`, `152/152`, `154/154`,
`35/35`, repository-service parallel `1639 collected / 1638 passed / 1 expected cgroup skip`,
and serial `205/205`; service total is `1844`, exit code is `0`, and no other skip or failure is
reported. The exact no-ignore source selection is unchanged; `-vv -s` is reporting-only
passthrough and adds no marker, keyword, file exclusion, retry, xfail or skip.

S9-4's five raw searches remain present and classified with no unclassified current old semantic.
The packet identity, lock hashes, image IDs, clean-source result, zero residual result, S8 carried
scope and S10 deferred scope are internally consistent. It does not claim `candidate_seal`,
`S9_exit` or `S10_ready`.

## Verdict

```yaml
review_status: pass
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
finding_count: 0
blocker_count: 0
prior_review_status: fail
prior_finding_count: 3
prior_findings_closed: yes
candidate_bound_provenance: pass
no_ignore_source_regression: pass
all_eight_docker_nodeids: pass
per_node_cleanup_inventory: pass
old_reference_classification: pass
candidate_clean: pass
allow_s9_seal: yes
S9_exit: no
S10_ready: no
production_retest_required: yes
phase_2_complete: no
next: S9-6 external candidate seal and S9 handoff
```

This review authorizes entry to S9-6 only. It does not itself record the external candidate seal,
S9 exit, S10 readiness or Phase 2 completion.

# P2-R6-S9 Independent Candidate Seal Review

状态：`fail`

日期：2026-08-17

本记录是 S9-5 的独立只读审核。审核对象是 S9-0、S9-2、S9-3、S9-4 的实际记录、原始
no-ignore 日志、五组 old-reference raw 文件、S8 handoff 与 S10 deferred scope。审核没有
修改 candidate、source/test/build input、Docker/Compose、image 或 handoff；没有用新的运行
结果替代 S9-3 的缺失证据。失败记录必须保留，修复后按执行计划开启新的 S9-5 审核。

权威步骤：[P2-R6-S9 Final Candidate Seal Execution Plan](../formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md) §7

设计审核：[p2-r6-s9-design-review.md](p2-r6-s9-design-review.md)

S9-0：[p2-r6-s9-step-0-entry-preflight.md](p2-r6-s9-step-0-entry-preflight.md)

S9-2：[p2-r6-s9-step-2-provisional-image.md](p2-r6-s9-step-2-provisional-image.md)

S9-3：[p2-r6-s9-step-3-no-ignore-regression.md](p2-r6-s9-step-3-no-ignore-regression.md)

S9-4：[p2-r6-s9-step-4-candidate-seal-packet.md](p2-r6-s9-step-4-candidate-seal-packet.md)

## Review identity

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 71da506171d01bbccdf2c54137949cdd0bff234e
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s8_handoff_head: 71da506171d01bbccdf2c54137949cdd0bff234e
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
reviewed_sha_kind: candidate_plus_external_documentation_records
reviewed_s9_0_blob_sha: d78c1360088860ea4220950d354e5286ad6331a3
reviewed_s9_2_blob_sha: 81f9d4cfe82461abb9d92a10ad7433c338a9d296
reviewed_s9_3_blob_sha: 1abeec381418129e1de0150930378b92896cc062
reviewed_s9_4_blob_sha: 84839fcc643f3431f75781f8d758c10b57b2556d
review_worktree_clean_at_start: no
review_worktree_dirty_scope: docs-only S9 records and formal documentation
candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_worktree_clean_at_review: yes
production_code_changed_by_review: no
test_or_build_input_changed_by_review: no
image_built_or_changed_by_review: no
handoff_changed_by_review: no
phase_2_complete: no
```

`documentation_head_sha`/`s8_handoff_head` is documentation-only. It is not the candidate and is
not used as an image or runtime identity. The candidate checkout was independently checked with:

```text
git rev-parse HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
git status --porcelain: empty
candidate identity: build_input_revision=3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
candidate identity: source_tree_sha256=sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
```

The remote image identities were also read without mutation and match S9-2/S9-4:

```text
Service: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
  revision=2ef884278b4998dde1e5fe224532c89b7a0cd73a
  build-input=3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
  source-tree=sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
  lock=6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
Client: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
  revision=2ef884278b4998dde1e5fe224532c89b7a0cd73a
  lock=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
```

## Review results

### 1. Candidate authority and scope

**Pass.** S9-0, S9-2, S9-3 and S9-4 consistently use literal candidate
`2ef884278b4998dde1e5fe224532c89b7a0cd73a`. `71da5061` is explicitly documentation-only, and
`5f474ce2` is retained only as S7 ancestor evidence. The candidate checkout is clean and the
review did not change it. S10 final production image/provenance, four production Compose nodeids,
W1/W2 and Candidate A v8 remain deferred.

### 2. Entry, builder and provisional image provenance

**Pass.** S9-0 records the S7 remote builder/gate-host, retained cache, bridge and secret-file
prerequisites. S9-2 records the remote checkout, Compose boundary, baseline and cleanup. The
independent identity and remote `docker image inspect` checks above match candidate, build-input,
source-tree and lock hashes. The provisional images are not represented as S10 production images.

### 3. Old-reference and clean-source packet

**Pass.** S9-4 preserves all five raw search files and classifies current, negative, unrelated and
historical hits without deleting historical material. Candidate identity recomputation matches
S9-2/S9-3, `git diff --check` passes, candidate porcelain is empty, and the packet keeps S8 carried
evidence and S10 deferred ownership explicit. The remote residual probe found no owned
`gateway-p2r6` containers/networks/volumes or query-temp artifacts at review time.

## Findings

### P1 — Eight required Docker nodeids are not individually reported as passed

The frozen S9-3 requirement is that all eight required Docker nodeids be collected **and
individually reported as passed by the exact** `./vnext/scripts/run-tests.sh` command (execution
plan §5, lines 179–187 and 192–207). The authoritative log
`p2-r6-s9-step-3-run-tests.log` uses quiet pytest output: it contains only the serial aggregate
`205 passed, 1639 deselected`, with no required Docker nodeid or per-node pass line. S9-3 lines
99–107 are a separate `--collect-only` listing and prove collection only. S9-3 lines 110–117
explicitly replace the missing per-node report with an inference from the aggregate count and
`exit_code=0`; that inference does not satisfy the frozen evidence requirement. No other S9 raw
log contains the eight nodeids with a passed result.

This routes to **S9-3**. Preserve the current failed review and rerun the exact no-ignore gate on
the unchanged candidate-bound image, capturing authoritative per-node pass evidence for all eight
nodeids. Do not close this finding with collect-only output, aggregate arithmetic or a host-only
substitution.

### P1 — Required per-node resource inventory is absent

Execution plan §5 requires a per-node Docker project/network/volume and process/thread/Dolt/
query-temp/work-root inventory. S9-3 lines 152–165 provide only one aggregate post-run block
(`gateway-p2r6 containers=0 networks=0 volumes=0`, aggregate PIDs/temp homes and image IDs).
The record explicitly states at lines 110–111 that the quiet log has no per-node
`compose_project=`/`teardown_scan` output. S9-2 has a single preflight project, not the eight
Docker nodeids, and S9-4 repeats only the aggregate zero inventory. Therefore the packet cannot
prove that every required Docker node cleaned its owned resources independently, even though the
aggregate is zero.

This routes to **S9-3**. Rerun the required gate (source/image unchanged) and record each required
nodeid's project/network/volume plus process/thread/Dolt/query-temp/work-root inventory and final
zero state. Preserve the current packet and this failed review; do not infer per-node cleanup from
the aggregate.

### P2 — Repair ledger and exit field are internally inconsistent

S9-3 lines 131–149 records a first failed authoritative attempt and an environment-only repair
(retagging the candidate image to `gateway-repository-service:local` and unsetting
`GATEWAY_REPOSITORY_SERVICE_IMAGE`) before the passing rerun. The same record's exit block at
lines 191–199 says `repairs: none`. The plan requires the first-failure/repair ledger to be
explicit and says the clean-candidate expectation is `none`; it must not simultaneously describe a
repair and claim no repairs. This is a provenance/evidence ambiguity, not a source defect, but it
prevents an internally consistent seal packet.

This routes to **S9-3** (or S9-4 if only the packet wording is corrected). Preserve the failed
first-run log, state explicitly that the rerun was environment-only with no source/test/build-input
repair, and make the ledger and exit fields agree before a fresh S9-5 review.

## Verdict

```yaml
review_status: fail
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
finding_count: 3
severity:
  p1_stage_blocker: 2
  p2_evidence_consistency: 1
blocker_count: 3
allow_s9_seal: no
return_step: S9-3
required_rerun: exact ./vnext/scripts/run-tests.sh on unchanged candidate-bound image
candidate_bound_provenance: pass
old_reference_classification: pass
candidate_clean: pass
zero_aggregate_residual: pass
independent_seal_review: repeat_after_route
S9_exit: no
S10_ready: no
production_retest_required: yes
phase_2_complete: no
```

S9-5 does not authorize S9-6, candidate seal, S10 readiness or Phase 2 completion. After the
owning S9-3 evidence is rerun and the packet is reconstructed with no candidate-affecting change,
start a new S9-5 conversation and require `finding_count: 0` and `allow_s9_seal: yes`.

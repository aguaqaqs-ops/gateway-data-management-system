# P2-R6-S10 Independent Final Production-Gate Review

状态：`pass`（`finding_count: 0`；仅授权 S10-11 external seal）

日期：2026-08-17

本记录执行权威计划 §12 的新会话只读复核。复核未修复或重写任何证据，未重跑 gate，未
retag/rebuild image，未读取 W1/W2 原始 package，未写 S10-11 seal。S10-0/S10-1、adapter
review、S10-6 attempt-1、S10-7 attempt-1..4 等失败或 superseded 记录均作为不可变历史保留。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §12

## Reviewed identity

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:p2-r6-final
service_image_local_tag: gateway-repository-service:local
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
adapter_sha256: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
installed_launcher_sha256: 2782a83f4465f1d9505a5347e1cc418ebd64f8fe73e2e9964d5235945da54a88
gate_host: issac@10.10.60.4
docker_daemon_id: dc91db82-3d49-41a4-a63c-f23dda721890
compose_version: 5.4.0
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
candidate_worktree_clean: yes
local_remote_identity_match: yes
phase_2_complete: no
```

Independent live checks confirmed local and remote detached checkouts at the literal candidate with
empty porcelain. Remote Docker inspection confirmed the final Service image and `:local` resolve to
the same ID; Service labels carry candidate, build-input, source-tree and Service lock, while Client
labels carry candidate and Client lock. The rendered `p2-r2` Compose boundary has no
`repository-service` host ports, Docker socket, host-root mount or resident client, and the live
project inventory is zero.

## Evidence hash review

The S10-9 machine packet is
`/root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/artifacts/s10-9/inventory.json` with SHA-256
`2a3f355a24207beff87090e16474ec9550e79237a352399baa73d734302a90ad`.
Its `hash_crosscheck` reports `23` compared objects and `0` mismatches. I independently ran the
following checks from the correct roots:

```text
sha256sum -c artifacts/s10-9/SHA256SUMS: all OK
sha256sum -c artifacts/s10-9/audit-tree-SHA256SUMS: all OK
sha256sum -c artifacts/s10-9/docs-SHA256SUMS: all OK
```

Key authoritative objects and hashes:

| object | SHA-256 |
| --- | --- |
| reviewed adapter | `af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150` |
| S10-5 no-ignore log | `59ae8de26c5a8e1b68d1af0a0308c5c721cc825b9d236dc4b98cd0c92983f2c7` |
| S10-6 attempt-2 W1 JSON | `365712104a784579be1d439c438a23eaf610fbb06bdba818a1dab42a2944a573` |
| S10-6 attempt-2 W2 JSON | `0f18233493b397d1da49eb923591ab47c2873ca23c0a4d1516eaa34882c7a017` |
| S10-7 attempt-5 W0 JSONL | `0720b5a1eec0fe5d9670d7757120490655436a125b2ebf1962b89b07796bdeab` |
| S10-8 attempt-1 v8 JSONL | `9dcdd1b458ec96a7391dc5cb96619155c02edaa6e17d5cd763abf42bf1d0a256` |
| S10-9 residual scan | `bd5c2962736c3acd3e4945dd9a85ffa1eb3e4a8657f73a8a9eb8333cf3a3e504` |

The same-daemon Service archive metadata records `332429824` bytes and SHA-256
`f2416c49c0e6b712fdf59fb2db7ba5bd62c81cdeefe67b83155b852cf6ed2245`; the archive was removed only
after packet hash verification.

## Review results

### Entry, authority and isolation

**Pass.** S10-0 attempt-2 is `S10_entry_ready: yes`; the failed attempt-1 and failed S10-1 review
remain preserved. The design rereview is pass with zero findings. Documentation SHA is separated
from the source candidate, and all candidate-affecting changes remain routed through S8/S9.

### Final artifacts and provenance

**Pass.** S10-4 rebuilt the final Service image from the clean candidate, bound `:local` to the same
immutable ID, requalified the candidate-bound Client image, recorded host-runner identity and hashed
the same-daemon archive. No cross-daemon load or provisional-image substitution is claimed.

### Exact no-ignore and Compose gate

**Pass.** The retained command is exactly `./vnext/scripts/run-tests.sh -vv -s`, with no ignore,
retry or duplicate targeted Compose run. Counts are `242/242`, `152/152`, `154/154`, `35/35`,
Repository Service `1639 collected / 1638 passed / 1 expected delegated-target cgroup skip`, and
serial `205/205` (total `1844`). The eight required Docker nodeids are individually `PASSED`; all
reported per-project inventories are zero. The only skip is the documented target-container cgroup
capability skip.

### Adapter and W1/W2 production repeat

**Pass.** The independently reviewed adapter is the exact current SHA, uses public HTTP against the
final container over the bridge, binds image/candidate/package/manifest identities, requests
`FULL_SCAN`/`REJECT`, verifies public readback and unknown/lossy counts, and fails closed on cleanup
or resource errors. AST parsing and static checks found no `shell=True` or `sh -c`; no production
internal module is imported. S10-6 attempt-2 W1 and W2 are both `SUCCEEDED`/`container_pass=pass`,
with exact package/manifest hashes, `unknown=0`, `lossy=0`, W2 replay `201681690` bytes in the
180-199 MiB band and below the 200 MiB cap, and final containers/networks/volumes all zero. The
attempt-1 named-volume failure and its review route remain preserved; this is not retry-as-pass.

### W0 and v8 formal coverage

**Pass.** S10-7 attempt-5 is explicitly diagnostic-only (`formal_decision=false`) and is not used
as formal evidence. S10-8 attempt-1 uses the final image and installed launcher with `66/66` unique
records (`30` normal, `36` scaling, `11` warm-ups, `55` measured), zero execution/correctness/sample
failures, complete provenance/cgroup/storage evidence, Candidate A selected, Candidate B
`reserved_not_evaluated`, and `formal_status=go`. The scale-ratio warning is correctly advisory and
does not change the hard-gate result.

### Attempts, packet and residuals

**Pass.** The S10-9 attempt ledger preserves every failed or superseded record. Hash manifests and
raw artifact trees verify without mismatch. The post-scan reports no S10-owned archive, package,
staging path, Compose container/network/volume, Dolt process, runner unit, active slice, work root or
pytest scratch. Historical volumes, retained cache, final image tags and the empty environment cgroup
mount are explicitly classified as pre-existing/retained rather than silently deleted.

## Findings and verdict

```yaml
finding_count: 0
blocker_count: 0
high_count: 0
medium_count: 0
low_count: 0
failed_attempts_preserved: yes
hash_crosscheck: pass
zero_owned_residual: yes
review_status: pass
allow_s10_seal: yes
candidate_or_image_changed_by_review: no
production_retest_required: yes
S10_exit: no
S11_ready: no
phase_2_complete: no
next: S10-11 external S10 seal and S11 handoff in a new conversation
```

This review authorizes the external seal step only. It does not itself set `S10_exit`, change
`production_retest_required`, publish a release, or claim Phase 2 completion. S10-11 must recheck
the exact identities and this review hash before writing the external seal.

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no for this read-only review
Reason: final image was rebuilt at S10-4 and all mandatory container gates S10-5 through S10-8 ran on the unchanged identity; this review changed no image/deployment input
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: passed on sealed candidate identity
Deferred: S10-11 docs-only seal/handoff; it must not change container identity
```

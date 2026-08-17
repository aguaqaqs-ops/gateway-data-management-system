# P2-R6-S10 Exact-Candidate Production Gate Execution Plan

状态：Ready for independent design review

日期：2026-08-17

关联设计：[P2-R6-S10 Exact-Candidate Production Gate Design](p2-r6-s10-exact-candidate-production-gate-design.md)

上游 handoff：[P2-R6-S9 final handoff](../../temporary/p2-r6-s9-final-handoff.md)

总计划：[P2-R6 Operational Closure Execution Plan](p2-r6-operational-closure-execution-plan.md)

本文把 S10 拆成 bounded sessions，并明确 implementation context、独立审核、失败回路、
预计耗时和数据移动。审核步骤只读；finding 返回 owning implementation step 修复，保留失败
审核并重新审核，直到 finding 为零。本文不授权修改 sealed candidate，也不把 task prompt
当作 allowed paths、identity、command 或 acceptance 的替代品。

## 0. Frozen entry and global rules

```yaml
stage: P2-R6-S10
branch: phase1/gate-ownership-repair
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s9_handoff_record_commit_sha: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
container_validated_code_sha: deferred
S9_exit: pass
S10_ready: yes
remote_builder_gate_host: issac@10.10.60.4
same_daemon_build_and_gate: yes
exact_no_ignore_command: ./vnext/scripts/run-tests.sh -vv -s
production_retest_required: yes
phase_2_complete: no
```

### 0.1 Session policy

- **New conversation:** S10-0 entry/preflight, S10-1 independent design review, S10-2 audit
  adapter implementation, S10-3 independent adapter review, S10-4 final image/container boundary,
  S10-7 target-launcher boundary, S10-10 independent final review and S10-11 external seal.
- **Same conversation:** S10-4 may continue through S10-5 only while candidate, final Service/Client
  IDs, tags and build inputs remain unchanged. S10-5 may continue into S10-6 with the same identities
  and reviewed adapter. S10-7 W0 smoke may continue into S10-8 formal only when launcher, image,
  checkout, cache condition, cgroup/storage preflight and output root remain unchanged. S10-9 packet
  may continue from S10-8 when no identity or evidence source changed.
- **Review isolation:** S10-1, S10-3 and S10-10 run in new read-only conversations. Reviewers record
  findings and return them; they never edit design, adapter, candidate, image, evidence or handoff.
- **Candidate immutability:** no source, test, dependency, Dockerfile, Compose, lock or build-input
  edit. Such a change returns to S8 owner, then repeats S9 and all S10 steps with a new seal.
- **External evidence:** all adapter bytes, logs, image archive metadata, W1/W2 records and v8
  artifacts live outside the candidate and documentation worktrees under a unique audit root.
- **No substitution:** no old/provisional image, broad skip/exclusion, retry-as-pass, accepted flake,
  stale artifact, host-runtime W1/W2 substitute or changed v8 parameter closes a gate.
- **Attempt immutability:** preserve every failed log/review/formal path. A rerun uses a new attempt
  or run ID and an explicit failure/repair ledger.

### 0.2 Duration and transfer labels

Labels are planning aids, not time budgets:

- **short:** usually under 15 minutes;
- **long:** may take 15-60 minutes or depends materially on remote cache/I/O;
- **very long:** expected to exceed one hour;
- **large transfer:** full image archive or comparable multi-GiB payload across a network;
- **moderate transfer:** tens of MiB or less, but still requires digest verification.

Current topology has no full-image remote transfer because build and gate share one daemon. S10-4
still creates a potentially multi-GiB archive and is high local disk I/O. If a distinct daemon is
introduced, stop and review the plan before performing the now-large remote image transfer.

## 1. Step map

| step | name | session policy | review/implementation | duration | remote/data profile | next / finding route |
| --- | --- | --- | --- | --- | --- | --- |
| S10-0 | Entry reconciliation and external preflight | new conversation | read-only/preflight | short | remote probes only | S10-1; missing prerequisite stops |
| S10-1 | Independent design and plan review | new conversation | independent review | short | none | S10-2; finding returns design/plan and repeats review |
| S10-2 | Production-image W1/W2 audit adapter | new conversation | external audit implementation | long/variable | no package transfer yet | S10-3; adapter defect returns here |
| S10-3 | Independent audit adapter review | new conversation | independent review | short/medium | none | S10-4; finding returns S10-2 until zero |
| S10-4 | Final Service/Client artifacts and provenance | new conversation; container boundary | implementation/gate | long/variable | high local I/O; full image archive; no current remote image transfer | S10-5; image failure returns here |
| S10-5 | Exact no-ignore full and Compose gate | same as S10-4 if identities unchanged | test/gate | medium/long | low network | S10-6; source defect returns S8/S9 |
| S10-6 | W1 medium and W2 production repeat | same as S10-5 if identities/adapter unchanged | external data gate | long | moderate package transfer; large remote expansion/I/O | S10-7; adapter finding returns S10-2/S10-3 |
| S10-7 | Candidate A W0 target smoke | new conversation; target boundary | diagnostic gate | medium | small output | S10-8; target preflight failure stays here |
| S10-8 | Candidate A v8 formal `--runs 5` | same as S10-7 if preflight unchanged | formal gate | very long | small network; heavy remote compute/volume I/O | S10-9; preserve failed run, route owner |
| S10-9 | Final packet and zero-residual audit | continue if all identities unchanged | evidence/read-only | short/medium | hashes/metadata only | S10-10; evidence gap returns owner |
| S10-10 | Independent final production-gate review | new conversation | independent review | medium | read-only artifact access | S10-11; finding returns owning step and repeats review |
| S10-11 | External S10 seal and S11 handoff | new conversation | external gate record | short | metadata only | S11; missing field is no-go |

## 2. S10-0 - Entry reconciliation and external preflight

**Session:** New conversation. Read-only; no adapter, image, package transfer or gate execution.

**Read first:** repository `AGENTS.md`, S10 design and this plan, S9 final handoff and seal review,
operational plan §§7-8, v8 authority, Stage I/K W1/W2 evidence, target launcher README and Testing
Conventions.

**Checks:**

1. Record documentation branch/HEAD/status and separately resolve candidate `2ef88427`. Create or
   select a fresh clean detached remote checkout; do not use documentation HEAD as source.
2. Recompute candidate, build-input revision, source-tree digest and both lock hashes. Confirm they
   equal S9 seal fields and that candidate/source/build-input worktrees are clean.
3. Revalidate SSH, Docker, Compose, retained cache HTTP 200, bridge/gate-host endpoint, secret-file
   handling, disk space, interactive release-operator sudo, installed target launcher and protected
   audit output directory. `sudo -n` is not required; the operator path must be real and available.
4. Verify approved local W1 `medium` and W2 package size/SHA, descriptor identity and permission to
   transfer to a protected remote staging directory. Do not transfer yet.
5. Inventory exact test counts/eight Docker nodeids, expected delegated-target cgroup skip, final
   tag names, Docker baseline and owned process/thread/Dolt/query-temp/work-root resources.
6. Allocate a unique audit root/run prefix without overwriting historical or failed evidence.

**Evidence:** `p2-r6-s10-step-0-entry-preflight.md` outside the candidate, including literal remote
commands/results, prerequisite owners, baseline inventory and unresolved items.

**Exit:** `S10_entry_ready: yes` only when every prerequisite is current. A missing operator,
launcher, output permission, cache, disk, package or identity is `no-go`; do not build first and hope
the later gate can compensate.

**Prompt:** `只读复核 S10 sealed candidate、远端 builder/gate-host、W1/W2、launcher、sudo、audit root 和零残留前置。`

## 3. S10-1 - Independent design and execution-plan review

**Session:** New conversation after S10-0 pass. Read-only; reviewer does not fix documentation.

**Review questions:**

- Is literal `2ef88427` the only candidate and are documentation SHAs separated?
- Does the plan prohibit candidate writes and route any source/build-input change through S8/S9?
- Are Service, Client, host runner, same-daemon archive and tag identities complete?
- Is no-ignore selection exact, with one allowed skip and no duplicate targeted Compose run?
- Does the external adapter prove the final container through public HTTP without host-port exposure?
- Are W1/W2 hard/advisory boundaries and package identities exact?
- Are W0/formal commands, 66-record hard gates and immutable attempt paths unchanged?
- Are session grouping, long steps, remote data movement, cleanup and review loops explicit?

**Output:** `p2-r6-s10-design-review.md` with reviewed design/plan blob or commit SHAs, findings,
`review_status: pass|fail` and `allow_s10_implementation: yes|no`.

**Finding loop:** preserve a failed review, repair only the design/plan in its owning conversation,
repeat S10-0 if authority/identity/prerequisites changed, then open a new S10-1 review. Continue until
`finding_count: 0`.

**Prompt:** `只读审核 S10 exact-candidate、final artifact、W1/W2 adapter、v8、session 和 failure routing 设计。`

## 4. S10-2 - Production-image W1/W2 audit adapter

**Session:** New conversation after S10-1 pass. Implementation is limited to the external audit
root. Do not modify candidate, repository tests/scripts, Compose or images.

**Why this step exists:** the committed `run_r6_s6_evidence.py` starts an in-process host runtime.
It is valid carried S6 evidence but cannot prove the S10 final container. S10 needs a reviewed
external adapter rather than changing the sealed candidate or mislabelling host evidence.

**Tasks:**

1. Create the audit adapter under the unique external audit root. Retain its exact bytes and SHA-256.
2. Reuse candidate-owned public contracts/HTTP client, manifest and Arrow parsing where practical.
   Do not import production internals to bypass HTTP behavior.
3. Require inputs for base endpoint, token file, package path, expected package/manifest identity,
   expected running Service image ID, dataset ID and output path. Never place token values in argv,
   logs or output.
4. Implement public HTTP create, upload, `FULL_SCAN`/`REJECT` submit/poll, result digest, main
   resolution, catalog with documented manifest fallback, table row stream and unknown/lossy checks.
5. Verify the container/Compose project uses the final immutable image and no host port. Record
   Docker/volume/process/resource baselines and final cleanup through existing bounded harness APIs
   or literal reviewed Docker commands.
6. Output only sanitized result data: identity, settings, timings, resource peaks, public counts,
   status and cleanup. Do not output raw rows, SQL, package bytes, bearer token or host source path.
7. Dry-validate argument parsing, redaction and fail-closed identity checks without consuming the
   approved W1/W2 packages or claiming a container PASS.

**Evidence:** adapter source, SHA-256, command contract, safe sample output/redaction checks and
`p2-r6-s10-step-2-audit-adapter.md`.

**Exit:** adapter is ready for independent review; no W1/W2 production claim and no candidate/image
change. An adapter implementation finding returns here.

**Prompt:** `在 external audit root 实现 final-container W1/W2 public HTTP adapter，保留 source hash、redaction 和 fail-closed identity evidence。`

## 5. S10-3 - Independent audit adapter review

**Session:** New read-only conversation. Do not modify adapter or execute approved W1/W2 packages.

**Review questions:**

- Does the adapter address only the final container through the approved bridge and avoid host ports?
- Does it bind running Service image ID, package SHA, manifest digest and candidate identity?
- Does it request exactly `FULL_SCAN` and `REJECT`, poll terminal state and verify public facts/read?
- Are unknown/lossy, W2 band/cap, disk/headroom, resource and cleanup evidence present?
- Are secrets, raw rows, replay SQL, package bytes and host paths absent from safe output?
- Can an error or missing field only fail closed, with no retry or host-runtime fallback?

**Output:** `p2-r6-s10-audit-adapter-review.md` with adapter SHA, findings,
`review_status: pass|fail` and `allow_w1_w2_execution: yes|no`.

**Finding loop:** a finding returns to S10-2. Preserve the failed review, update the adapter in its
implementation conversation, then start a new S10-3 review. Any byte change invalidates the prior
adapter review. Continue until zero findings.

**Prompt:** `只读审核 external W1/W2 adapter 的 final-image identity、public HTTP、redaction、resource 和 cleanup 边界。`

## 6. S10-4 - Final Service/Client artifacts and provenance

**Session:** New conversation after S10-3 pass. Container/build boundary. This step may be long and
creates a full image archive with potentially multi-GiB local disk I/O.

**Tasks:**

1. From the clean detached candidate, rerun canonical identity and lock hashes immediately before
   build. Fail on any mismatch or dirty path.
2. Build `gateway-repository-service:p2-r6-final` with retained dependencies and exact identity env.
   Verify candidate, build-input, source-tree, Service lock and pinned-version labels plus image ID.
3. Bind `gateway-repository-service:local` to the same immutable ID and prove both tags resolve
   identically. Leave the global Service image override unset for S10-5.
4. Force-build or requalify `gateway-repository-client-e2e:local`; record candidate label, Client
   lock SHA and immutable image ID. Record the gate-host Python runner identity.
5. Create a temporary Service `docker save` archive, record command, exact image references, size
   and SHA-256. Since the gate uses the same daemon, do not perform a false same-daemon load.
6. Render Compose and confirm no host port, resident client service, host-root mount or unscoped
   Docker resource. Capture a fresh resource baseline.

**Large-transfer note:** current path performs no full-image network transfer. If S10-0/S10-4 finds
that build and gate daemons differ, stop before copying the image. A full archive is a large remote
transfer and requires the S10 design/plan to be reviewed for save/load path, free space, checksum
and remote/local ID equivalence.

**Evidence:** `p2-r6-s10-step-4-final-artifacts.md`, image/client inspect, helper output, archive
size/SHA, Compose config and baseline inventory.

**Exit:** final immutable identities pass and the candidate remains clean. An image/client/archive/
provenance failure returns here. An image ID change invalidates S10-5 onward.

**Prompt:** `从 2ef88427 clean checkout 构建 final Service/Client artifacts，记录 labels、IDs、same-daemon archive hash 和 baseline。`

## 7. S10-5 - Exact no-ignore full and Compose gate

**Session:** Continue S10-4 in the same conversation only while candidate, build inputs, Service/
Client IDs, tags and baseline remain unchanged. This is a medium/long-running remote gate.

**Authoritative command:**

```bash
./vnext/scripts/run-tests.sh -vv -s
```

**Required evidence:**

- six package/pass rows and counts exactly matching the sealed S9 inventory;
- no marker/file/keyword exclusion, ignore, xfail, retry or accepted flake;
- only the delegated-target cgroup smoke skip;
- all eight Docker-starting nodeids individually `PASSED` in the authoritative log;
- the four S10 Compose nodeids bind the final Service/Client identities and each report zero owned
  resource inventory; do not run a duplicate targeted four-node command;
- final tags still resolve to the S10-4 immutable IDs and candidate checkout remains clean;
- failure/repair ledger, even when `none`.

**Evidence:** immutable raw log plus `p2-r6-s10-step-5-no-ignore-compose.md`.

**Exit:** exit `0`, exact counts, one classified skip, all Docker nodeids pass, zero residual and
unchanged identity. A source/test defect returns to S8 owner then S9; an environment failure is
preserved and may rerun this step only after concrete diagnosis while image identity is unchanged.

**Prompt:** `在 final image identity 上执行 exact no-ignore gate，逐条记录八个 Docker nodeid、四条 Compose、counts 和零残留。`

## 8. S10-6 - W1 medium and W2 production repeat

**Session:** Continue S10-5 only while candidate, final image IDs, reviewed adapter SHA, topology and
baseline remain unchanged. This is long-running and transfers about 10.4 MiB compressed packages;
W2 expands to about 192 MiB and produces substantial remote disk/process I/O.

**Tasks:**

1. Create a protected remote staging directory through the approved operator path. Transfer only
   W1 `medium`, W2 and sanitized descriptor; compare local/remote sizes and SHA-256 before use.
2. Start isolated final-image Compose projects with scoped names/networks/volumes and secret files.
   Verify the running container image ID before each dataset.
3. Execute the reviewed adapter for W1 medium and W2. Record exact command, adapter SHA, image ID,
   public results, timings, resources and cleanup.
4. Enforce all hard gates from the design. Record S6 comparisons as advisory without inventing a
   time/RSS percentage threshold.
5. Remove transferred packages, expanded/work roots, secrets and owned Compose resources. Preserve
   sanitized results, adapter bytes/hash and failure attempts under the audit root.

**Evidence:** `p2-r6-s10-step-6-w1-w2-production-repeat.md`, sanitized machine results, transfer
hashes and per-dataset zero-residual inventory.

**Exit:** both datasets pass on the final image and all temporary data/resources are removed. An
adapter defect returns to S10-2 then S10-3 and repeats this step. A production defect returns to the
S8/S9 loop. A transfer/permission failure preserves evidence and reruns S10-6 only when identities
and reviewed adapter are unchanged.

**Prompt:** `用 reviewed adapter 在 final container 上重跑 W1 medium/W2，记录 digest、FULL_SCAN/read、资源与清理。`

## 9. S10-7 - Candidate A W0 target smoke

**Session:** New conversation after S10-6 pass. Target-launcher boundary. May continue to S10-8 only
with unchanged checkout, image, launcher, cgroup/storage preflight and audit root.

**Tasks:**

1. Revalidate clean final checkout, final tag/image labels, retained-cache condition, installed
   launcher, interactive sudo, fresh output path and target baselines.
2. Execute the canonical Candidate A W0 diagnostic smoke entry point through the target launcher.
3. Verify final image provenance, delegated cgroup, exact/effective 8 GiB safety ceiling, named
   volume/storage layout, batch contract, cleanup and zero residual.
4. Record `diagnostic_only=true`, `formal_decision=false`; never treat smoke as S10-8 evidence.

**Evidence:** raw smoke artifacts and `p2-r6-s10-step-7-w0-smoke.md`.

**Exit:** smoke pass with unchanged identity and clean baseline. A target capability failure stays
in S10-7; source/image change follows the earlier owner route.

**Prompt:** `在 final image 上执行 Candidate A W0 target smoke，验证 provenance、cgroup、storage、batch 和 cleanup。`

## 10. S10-8 - Candidate A v8 formal

**Session:** Continue S10-7 in the same conversation only when its environment remains unchanged.
This is the longest step; historical reference is approximately 2 hours 20 minutes. Do not treat
that reference as a timeout or performance acceptance threshold.

**Canonical command:** use the exact command in the S10 design and operational plan with a unique
new output path, `--v8-formal` and `--runs 5`. Do not add diagnostic, workload, candidate, row/byte
or retry arguments.

**Required evidence:**

- raw JSONL, machine summary and report with hashes;
- `66/66` unique records, `30` normal, `36` scaling, `11` warm-ups and `55` measured;
- zero execution, correctness, batch, lifecycle, provenance, storage, cgroup and cleanup failures;
- Candidate A selected, Candidate B `reserved_not_evaluated`, `formal_status=go`;
- resource advisory recorded without changing hard-gate meaning;
- final project/volume/process/cgroup and output-path ownership inventory.

**Failure rule:** once any record is written, preserve the whole attempt. A diagnosed environment-
only rerun requires a fresh run ID/path. A source/image/hard-gate defect follows its owning earlier
route; no partial 66-record result or successful subset can close S10.

**Evidence:** immutable v8 artifact directory plus `p2-r6-s10-step-8-v8-formal.md`.

**Prompt:** `用 canonical launcher 在 final image 上执行唯一 66-record Candidate A v8 formal --runs 5，保留完整 artifacts。`

## 11. S10-9 - Final packet and zero-residual audit

**Session:** Continue S10-8 only if no identity/evidence source changed. Open a new implementation
conversation if the packet must be reconstructed after a repair.

**Checks:**

1. Recompute candidate/build-input/source-tree/locks and compare with final Service/Client/runner,
   archive metadata, no-ignore, W1/W2 and v8 evidence.
2. Hash every authoritative log, adapter, sanitized W1/W2 record and v8 artifact. Classify failed
   and superseded attempts without deleting them.
3. Confirm exact test counts, individual Docker/Compose evidence, one allowed skip, W1/W2 hard
   gates and v8 coverage/formal status.
4. Confirm no transferred package, image archive, secret, expanded data, Compose object, process,
   thread, Dolt child, query temp, work root, target unit/cgroup or unowned output remains.
5. Record Docker/Compose policy for current HEAD: candidate final image rebuilt and mandatory
   container gate run; later S11 docs-only commit does not change container identity.

**Evidence:** `p2-r6-s10-step-9-final-packet.md` plus machine-readable artifact/hash inventory.

**Exit:** packet complete, consistent and zero-residual. Evidence-only gaps return S10-9; factual
gate gaps return their owning step.

**Prompt:** `汇总 S10 final identity、counts、W1/W2、v8、attempt ledger、artifact hashes 和 zero-residual packet。`

## 12. S10-10 - Independent final production-gate review

**Session:** New read-only conversation. Do not repair evidence, rerun commands, retag images or
write the external seal.

**Review scope:** S10-0 through S10-9 records and raw artifacts, including failed/superseded
attempts. Review literal candidate, final artifact identity, adapter review, no-ignore counts,
individual nodeids, W1/W2 hard/advisory classification, W0/formal coverage and final residuals.

**Output:** `p2-r6-s10-final-gate-review.md` with reviewed artifact hashes, findings,
`review_status: pass|fail` and `allow_s10_seal: yes|no`.

**Finding routing:**

| finding | owner | required rerun before new review |
| --- | --- | --- |
| entry/prerequisite/authority | S10-0/S10-1 | affected preflight/design review |
| adapter behavior/redaction | S10-2/S10-3 | adapter review and S10-6 |
| Service/Client/provenance/archive | S10-4 | S10-4 through S10-9 |
| no-ignore/count/Compose | S10-5 or S8/S9 | exact gate and downstream affected steps |
| W1/W2/transfer/resource/cleanup | S10-6 or S8/S9 | W1/W2 and downstream affected steps |
| target smoke | S10-7 | smoke and formal when target facts changed |
| v8 formal | S10-8 or source/image owner | fresh formal attempt and packet |
| packet/hash/residual | S10-9 or factual owner | packet and affected gate |

Preserve every failed review. The reviewer never fixes a finding. After the owner repairs and reruns
the required scope, start a new S10-10 review. Repeat until `finding_count: 0` and
`allow_s10_seal: yes`.

**Prompt:** `只读审核 S10 final artifacts、no-ignore/Compose、W1/W2、v8、attempts、hashes 和 zero-residual packet。`

## 13. S10-11 - External S10 seal and S11 handoff

**Session:** New conversation after S10-10 pass. External/documentation evidence only; no gate
rerun, candidate write, image rebuild/retag or adapter change.

**Verify:** exact reviewed packet and hashes, unchanged candidate/final identities, zero open
finding, no residual and explicit S11-only Phase 2 completion scope.

**External seal:**

```yaml
stage: P2-R6-S10
stage_status: pass
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
final_service_image_provenance: pass
final_client_and_host_runner_identity: pass
same_daemon_archive_evidence: pass
no_ignore_full_gate: pass
four_compose_nodeids: pass
w1_medium_production_repeat: pass
w2_production_repeat: pass
candidate_a_w0_smoke: pass
candidate_a_v8_formal: pass
v8_records: 66
v8_formal_status: go
zero_owned_residual: yes
independent_final_review: pass
production_retest_required: no
S10_exit: pass
S11_ready: yes
phase_2_complete: no
```

**Exit:** S10 is complete only with the exact seal above. S11 owns documentation/provenance handoff,
SHA lineage, limitations and the final `phase_2_complete` decision. Documentation cannot convert a
missing/failed S10 field into pass.

**Prompt:** `在 independent final review 通过后记录 S10 external seal、container validated SHA 和 S11-ready handoff。`

## 14. Plan verdict

```yaml
plan_status: ready_for_independent_design_review
steps: 12
implementation_or_gate_steps: 7
independent_review_steps: 3
entry_or_handoff_steps: 2
same_session_groups:
  - S10-4_to_S10-6_when_candidate_images_adapter_unchanged
  - S10-7_to_S10-9_when_target_and_identity_unchanged
long_steps:
  - S10-2 audit adapter implementation
  - S10-4 final image build/archive
  - S10-5 no-ignore full gate
  - S10-6 W1/W2 production repeat
very_long_steps:
  - S10-8 Candidate A v8 formal
large_data_steps:
  - S10-4 full image archive high local I/O; large remote transfer only if topology changes
  - S10-6 moderate compressed package transfer and large remote expansion
review_findings_return_to_implementation_until_zero: yes
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
production_retest_required: yes
phase_2_complete: no
next: S10-0 entry reconciliation
```

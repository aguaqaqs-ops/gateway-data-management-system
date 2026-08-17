# P2-R6-S10 Exact-Candidate Production Gate Design

状态：Design baseline frozen by discussion; independent design review required

日期：2026-08-17

适用范围：`P2-R6-S10` sealed candidate final Service/Client artifact identity、production-image
no-ignore/Compose gate、representative W1/W2 repeat、Candidate A v8 formal production retest、
独立 final gate review 和 S11-ready external seal。本文不重新拥有 public Contract、S8 source
repair、S9 candidate seal、P2-R1 v8 methodology 或 S11 Phase 2 documentation handoff。

## 1. Authority and entry

权威顺序：

1. Repository Service Contract and referenced contract owners;
2. P2 Versioned Repository Implementation Design;
3. [P2-R1 v8 Authority and Implementation Brief](p2-r1-v8-authority-and-implementation-brief.md);
4. [P2-R6 Operational Closure Execution Plan](p2-r6-operational-closure-execution-plan.md)
   §§7-8 and S9 handoff;
5. [P2-R6-S9 final handoff](../../temporary/p2-r6-s9-final-handoff.md);
6. R6-EXT-W1 Stage I/K evidence and sanitized descriptor;
7. Testing Conventions and repository `AGENTS.md`.

S10 consumes exactly the S9 external seal:

```yaml
branch: phase1/gate-ownership-repair
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s9_handoff_record_commit_sha: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
container_validated_code_sha: deferred
candidate_seal: pass
S9_exit: pass
S10_ready: yes
production_retest_required: yes
phase_2_complete: no
```

`21c99ef3` and later design/evidence commits are documentation-only descendants. They must never be
used as the S10 source candidate. Every source, test, dependency, Dockerfile, Compose or effective
build-input change invalidates the sealed candidate and routes to the owning S8 step, followed by a
complete S9 reseal before S10 restarts.

## 2. Goal and non-goals

### 2.1 Goal

Build and validate the literal sealed candidate in the production-equivalent remote environment.
S10 must produce one internally consistent evidence chain containing:

- a fresh clean detached checkout and current external-prerequisite record;
- final Service image plus candidate-bound Client image and host-runner identities;
- Service candidate/build-input/source-tree/lock labels and immutable image ID;
- an auditable same-daemon image archive digest, without claiming a false cross-host transfer;
- the exact no-ignore full gate with individual Docker nodeid and cleanup evidence;
- representative W1 `medium` and synthetic W2 against the final container image;
- Candidate A W0 diagnostic smoke and the canonical 66-record v8 formal `--runs 5`;
- a final packet, independent review with zero findings and an external S10 seal consumed by S11.

### 2.2 Explicit non-goals

- no candidate, production, test, dependency, Dockerfile, Compose or build-input edit;
- no S9 provisional Service/Client image or ancestor image as final evidence;
- no Candidate B formal run, changed v8 parameters or resource-warning promotion to an invented SLO;
- no repeat of all five W1 fixtures or the S6 1/4/8 concurrency matrix;
- no second targeted execution of the four Compose nodeids already proven by the no-ignore command;
- no registry publication, Git release tag, production traffic activation or Phase 2 completion claim;
- no retry, accepted flake, marker/file exclusion, xfail, broad skip or overwritten failed artifact.

## 3. Confirmed execution decisions

### 3.1 Remote topology and operator boundary

The designated S7/S9 host `10.10.60.4` remains both retained-cache builder and production-equivalent
gate host. The release operator supplies interactive `sudo` for the installed target launcher and
protected audit directory. Local WSL Docker and its unavailable cache are not substitutes.

W1/W2 packages are owner-declared desensitized. Only the approved `medium/package.tar.zst`,
`w2/package.tar.zst`, sanitized descriptor and expected digests may be transferred to a protected
remote staging directory. Record size and SHA-256 before and after transfer; remove packages and
expanded/work roots after the gate. Raw rows, replay SQL and secrets are not written to repository
evidence.

### 3.2 Final Service, Client and host-runner identity

The Service image is built once from the clean candidate with the canonical build script and
retained cache, then tagged both:

```text
gateway-repository-service:p2-r6-final
gateway-repository-service:local
```

Both tags must resolve to the same immutable image ID. The no-ignore gate leaves
`GATEWAY_REPOSITORY_SERVICE_IMAGE` unset so the build-harness unit tests retain their default-tag
contract. The final image records candidate SHA, build-input revision, effective source-tree digest,
Service lock SHA and pinned runtime versions.

The Client image is rebuilt or requalified from the same candidate and records its immutable ID,
candidate label and Client lock SHA. It is a candidate-bound gate artifact, not a separately
published production product. Gate-host Python execution records a host-runner identity containing
the candidate and Client lock SHA.

Because builder and gate use the same Docker daemon, S10 does not perform a meaningless same-daemon
`docker load`. It creates a temporary `docker save` archive, records archive size/SHA-256 and image
inspect output, then deletes the archive after packet assembly. Evidence records
`same_daemon_build_and_gate=yes` and `cross_host_transfer=not_applicable`. If a later preflight finds
distinct daemons, the image archive becomes a large remote transfer and requires design-plan review
before using auditable save/load.

### 3.3 Exact no-ignore and Compose gate

The authoritative command is:

```bash
./vnext/scripts/run-tests.sh -vv -s
```

`-vv -s` changes reporting only. It exposes individual nodeids and teardown inventories without
changing the script's package, marker or serial selection. The sealed candidate must reproduce the
S9 inventory: fast packages `242/242`, `152/152`, `154/154`, `35/35`; Repository Service parallel
`1639 collected / 1638 passed / 1 expected delegated-target cgroup skip`; serial `205/205`; total
Repository Service collection `1844`.

The same command must report the four production Compose nodeids individually as passed. They are
not run a second time. The four negative Compose probes also remain required through the no-ignore
gate. Only the delegated-target cgroup smoke may skip; S10 W0/formal target execution closes that
environment capability directly.

### 3.4 Production-image W1/W2 repeat

S10 repeats only:

- representative W1 `medium`, package `2081228` bytes, SHA-256
  `3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e`;
- synthetic W2, package `8301271` bytes, SHA-256
  `6cac7852d1174c126c182e82010b0ff9d4043e51826b8043103360c8e49f6d10`, whose replay SQL is
  `201681690` bytes (`192.337 MiB`).

Both use the final Service container over the existing no-host-port gate-host bridge and execute
public HTTP create, upload, `FULL_SCAN`/`REJECT` import, operation poll, main resolution, catalog or
manifest-selected table read and Arrow schema inspection. Required hard gates are exact package and
manifest identity, `SUCCEEDED`, completed `FULL_SCAN`, public facts, `unknown=0`, `lossy=0`, W2 in
the 180-199 MiB band and below the 200 MiB cap, disk admission/headroom, and zero timeout/OOM/
process/query-temp/work-root/container residual.

Elapsed time, RSS, Docker memory and durable-root peaks are recorded and compared to S6 as advisory
observations. They become hard failures only when an existing limit, admission boundary, timeout,
OOM or cleanup invariant fails.

The existing `vnext/scripts/run_r6_s6_evidence.py` starts an in-process host `ServiceRuntime`; it
cannot by itself prove the final container image. S10 therefore prepares an audit-only adapter under
the external audit root. The adapter may reuse committed candidate HTTP client/manifest/Arrow
helpers, but must connect to the final container, verify the running image ID, avoid host port
publication, redact secrets/rows and record its own SHA-256. It is independently reviewed before
W1/W2 execution. Adapter changes after review require that review and all adapter-owned W1/W2
evidence to repeat; they do not change the candidate or image when no candidate file changes.

### 3.5 Candidate A smoke and v8 formal

Before the long formal run, execute one Candidate A W0 diagnostic smoke through the installed target
launcher. It verifies interactive sudo, launcher, cgroup delegation, exact 8 GiB ceiling, image
provenance, named-volume storage and a fresh audit output path. It is diagnostic-only and never
selects a provider.

The formal command remains canonical and unmodified:

```bash
sudo env \
  GATEWAY_P2R1_REPO_ROOT=<clean-final-source-checkout> \
  GATEWAY_P2R1_IMAGE=gateway-repository-service:p2-r6-final \
  GATEWAY_P2R1_CACHE_CONDITION=retained-dependency-cache \
  /usr/local/libexec/gateway-p2r1-target-launcher.sh \
  --output /var/lib/gateway/repository/audit-rerun/<unique-r6-run>/p2-r1.jsonl \
  --v8-formal \
  --runs 5
```

Acceptance is `66/66` unique records, `30` normal, `36` scaling, `11` warm-ups, zero execution/
correctness/hard-gate failures, verified resource/cgroup/storage evidence and `formal_status=go`.
Resource advisory may be `within_reference` or `above_reference`. A formal attempt that writes any
record is immutable evidence: preserve it, and use a new run ID/path for an allowed environment-only
rerun.

### 3.6 Evidence and stage state

Raw commands, logs, adapter source/hash, image archive hash, W1/W2 results and v8 raw/summary/report
remain under the external audit root. The candidate checkout and documentation worktree remain
separate. Transferred packages, expanded data, image archive and ephemeral Docker resources are
removed; formal raw evidence remains through S11 review and then follows the existing release
evidence retention policy.

S10 success changes the stage-level `production_retest_required` to `no`. The v8 artifact's
historical P2-R1 field may remain `true` and is not rewritten. S10 records `phase_2_complete: no`;
only S11 may publish the documentation/provenance handoff with Phase 2 completion.

## 4. Identity and evidence model

| fact | authority | S10 rule |
| --- | --- | --- |
| source candidate | S9 seal/Git | literal `2ef88427`; immutable |
| documentation SHA | Git docs branch | separate; never an image input |
| build-input revision/source digest | canonical helper | recompute and compare at every boundary |
| final Service image | Docker | two tags, one immutable ID, full labels |
| candidate-bound Client image | Docker | candidate and Client lock labels |
| host runner | clean checkout/lock | candidate + Client lock identity |
| image archive | external audit | temporary bytes; retained size/SHA only |
| W1/W2 adapter | external audit | retained source and SHA; independent review owner |
| W1/W2 packages | external owner | exact approved package digests; removed remotely after use |
| v8 artifacts | target launcher | immutable fresh run path; raw/summary/report hashes |

## 5. Review and failure routing

- Design and final reviews are read-only and occur in new conversations. Reviewers do not repair
  documents, adapter, image, test evidence or handoff state.
- A design finding returns to the design/plan owner. Preserve the failed review and repeat entry
  reconciliation when authority, scope or identity changes.
- An audit-adapter finding returns to the external adapter implementation step. Repeat adapter
  review until zero findings; repeat W1/W2 if reviewed adapter bytes change.
- An image/client/provenance finding returns to final image construction and invalidates every later
  S10 gate.
- A source/test/build-input defect returns to its S8 owner and requires S9 reseal plus complete S10.
- A diagnosed package-transfer, permission, launcher or other environment failure preserves failed
  evidence and reruns only the affected step and unexecuted downstream steps while identities remain
  unchanged. A test failure cannot be relabelled as an environment flake.
- A v8 retry never overwrites or appends to a failed run path.

## 6. Duration and data-movement profile

Durations below are planning observations, not acceptance budgets.

| activity | expected profile | remote/network data |
| --- | --- | --- |
| final Service/Client build | long/variable, bounded by 30-minute build timeout | retained-cache traffic; no full-image network transfer on current same daemon |
| image archive | high local disk I/O; potentially long | full image may be multi-GiB; large remote transfer only if topology changes |
| no-ignore full gate | medium/long; S9 reference about 6-7 minutes | low, aside from local Docker layers already present |
| W1 medium + W2 | long; imports/reads may take tens of minutes | about 10.4 MiB compressed package transfer; W2 expands to about 192 MiB remotely |
| W0 smoke | medium | small audit output |
| v8 formal | very long; historical reference about 2 hours 20 minutes | small control/output traffic; substantial remote compute and volume I/O |

## 7. Acceptance matrix

| invariant | required evidence | owner |
| --- | --- | --- |
| exact entry | candidate, clean checkout, S9 seal, current external prerequisites | S10-0 |
| design closure | independent design/plan review, zero findings | S10-1 |
| audit adapter | public-HTTP/container boundary, redaction, identity and adapter SHA | S10-2/S10-3 |
| final artifacts | Service/Client/host identities and same-daemon archive evidence | S10-4 |
| full regression | exact counts, only allowed skip, eight Docker nodeids and zero residual | S10-5 |
| W1/W2 | exact packages, hard gates, advisory resources, final image and cleanup | S10-6 |
| target preflight | Candidate A W0 diagnostic smoke and cgroup/storage/provenance | S10-7 |
| v8 formal | 66-record hard-gate `go`, fresh path and artifact hashes | S10-8 |
| final packet | all identities, counts, attempts, hashes and zero residual consistent | S10-9 |
| independent review | zero findings, failure ledger and deferred S11 scope checked | S10-10 |
| external seal | exact S10 state and S11-ready handoff | S10-11 |

## 8. S10 external seal schema

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

## 9. Risk and proportional assurance

- Strong proof remains on immutable source/image identity, public facts, import commit effects,
  cgroup/storage provenance, hard gates and cross-scope cleanup.
- Timing and resource deltas remain advisory unless they cross an existing safety or admission
  boundary. S10 does not invent a new production SLO.
- Same-host builder/gate and same-euid controlled processes remain one trust domain. No new service,
  helper UID, broker, IPC, capability or persistent state machine is introduced.
- The audit adapter exists only because the sealed candidate's S6 driver is host-runtime-only. It
  owns no production behavior and is retained/reviewed as evidence code rather than added to the
  production image.

## 10. Design verdict

```yaml
design_status: ready_for_independent_review
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
source_or_build_input_change_allowed: no
remote_builder_gate_host: 10.10.60.4
same_daemon_build_and_gate: yes
external_audit_adapter_required: yes
independent_design_review_required: yes
independent_adapter_review_required: yes
independent_final_review_required: yes
production_retest_required: yes
phase_2_complete: no
next: P2-R6-S10 execution plan
```

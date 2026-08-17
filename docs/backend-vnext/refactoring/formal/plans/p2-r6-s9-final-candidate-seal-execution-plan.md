# P2-R6-S9 Final Candidate Seal Execution Plan

状态：Ready for independent design review

日期：2026-08-17

关联设计：[P2-R6-S9 Final Candidate Seal Design](p2-r6-s9-final-candidate-seal-design.md)

上游 handoff：[P2-R6-S8 final handoff](../../temporary/p2-r6-s8-final-handoff.md)

总计划：[P2-R6 Operational Closure Execution Plan](p2-r6-operational-closure-execution-plan.md)

本文把 S9 拆成 bounded sessions。每个 implementation step 在同一对话中保留局部上下文、
命令、证据和失败修复；设计审核、容器边界、独立 seal review 和 handoff 使用新对话。任务
prompt 只启动已经冻结的步骤，不替代本文的 allowed paths、evidence owner、failure routing
或 candidate immutability 规则。

## 0. Frozen entry and global rules

```yaml
stage: P2-R6-S9
branch: phase1/gate-ownership-repair
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s8_handoff_head: 71da506171d01bbccdf2c54137949cdd0bff234e
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s8_exit: pass
s9_ready: yes
production_retest_required: yes
phase_2_complete: no
remote_builder_gate_host: same S7 retained-cache configuration
exact_no_ignore_command: ./vnext/scripts/run-tests.sh
```

`validated_code_sha` is the only permitted S9 source candidate. `s8_handoff_head` is documentation
only and must never be used as `CANDIDATE_SHA`. Before any gate, obtain literal values with
`git rev-parse` and stop on branch, ancestry, source or worktree mismatch.

### 0.1 Session policy

- **New conversation:** S9-0 entry/preflight, S9-1 independent design review, S9-2 provisional
  image/container boundary, S9-5 independent seal review and S9-6 final seal/handoff.
- **Same conversation:** S9-2 image preflight may continue through S9-3 no-ignore regression while
  the candidate-bound image and source checkout remain unchanged. S9-4 packet assembly may continue
  from S9-3 only when no source/build-input change occurred.
- **Read-only review:** S9-1 and S9-5 inspect actual design, diffs, commands, counts, labels and
  evidence. Reviewers do not repair code, tests, deployment, candidate or handoff text.
- **Source immutability:** after S9-0 selects the clean checkout, no source/test/dependency/
  Dockerfile/Compose/build-input edit is allowed. Any such change invalidates all S9 evidence,
  routes to the S8 owning step, and starts S9 again from the new clean SHA.
- **Evidence location:** write step records, raw searches and command logs outside the detached
  candidate checkout, using a separate documentation worktree or external audit location. No S9
  evidence file may make the candidate worktree dirty.
- **No substitution:** no broad ignore, marker exclusion, `-k`, xfail, skip, retry, accepted flake,
  stale image or host-only replacement may close a gate.
- **Container policy:** the eight Docker-starting nodeids require candidate-bound provisional
  Service/client images. Final production image and S10 runtime gates remain deferred.
- **Review failure loop:** preserve the failed review record; route the finding, rerun the required
  owner gate, open a new conversation and repeat the affected review until zero findings.

## 1. Step map

| step | name | session policy | kind | output | next / failure route |
| --- | --- | --- | --- | --- | --- |
| S9-0 | Entry reconciliation and environment preflight | new conversation | read-only/preflight | entry + prerequisite record | S9-1; mismatch/no-go stops |
| S9-1 | Independent S9 design review | new conversation | read-only | design review | S9-2 or design correction |
| S9-2 | Candidate checkout and provisional image | new conversation; container boundary | implementation/preflight | image/client identity + baseline | S9-3; image/provenance failure returns here |
| S9-3 | Exact no-ignore source regression | same as S9-2 if image/source unchanged | test/gate | command, counts, Docker nodeids, inventory | S9-4; source failure returns S8 owner |
| S9-4 | Hygiene and seal packet | continue only with unchanged source | read-only/evidence | old refs, digest, counts, clean packet | S9-5; evidence gap returns S9-4 or S8 |
| S9-5 | Independent candidate seal review | new conversation | read-only | review record, zero findings | S9-6 or routed repair loop |
| S9-6 | External candidate seal and S9 handoff | new conversation | docs/external gate record | literal seal + S10-ready record | S10; missing field is no-go |

The plan deliberately puts independent seal review before the irreversible external seal record.
The source SHA is already fixed by S8; S9-6 authorizes its consumption by S10 only after the packet
and review pass.

## 2. S9-0 - Entry reconciliation and environment preflight

**Session:** New conversation. Read-only; no source/test/deployment edits and no candidate image build.

**Read first:** `AGENTS.md`, this plan §§0–2, S9 design §§1–7, S8 final handoff, S7 final handoff,
Testing Conventions, operational plan §§8–12 and the S7 builder/gate-host records.

**Checks:**

1. Record branch, literal `HEAD`, `git status --short`, and ancestry for `2ef88427`, `1bfa1d7f`
   and `5f474ce2`. Confirm the source candidate is a clean detached checkout target and the current
   handoff HEAD is docs-only.
2. Verify Docker daemon, Docker Compose, remote builder, retained dependency/artifact cache,
   gate-host bridge and secret-file prerequisites using the same S7 configuration. Do not silently
   switch to a different image host or cache.
3. Verify all eight Docker nodeids and the one expected delegated-target cgroup skip are present;
   no Docker nodeid may be environment-skipped.
4. Compute, without changing the candidate, the expected identity fields and both lock hashes:

   ```bash
   python3 vnext/repository_service/tests/support/build_context_digest.py identity
   sha256sum vnext/repository_service/uv.lock vnext/repository_client/uv.lock
   ```

**Evidence:** `p2-r6-s9-step-0-entry-preflight.md`, with literal identity, host/cache prerequisites,
nodeid inventory, expected skip classification and unresolved external prerequisites.

**Exit:** `S9_entry_ready: yes` only when all identity and environment prerequisites are available.
If Docker/cache/builder/bridge/secret prerequisites are unavailable, record `no-go` and stop; do
not run source regression against an old or unlabelled image.

**Prompt:** `复核 S9 candidate SHA、clean checkout、remote builder/gate-host 和八个 Docker nodeid 前置。`

## 3. S9-1 - Independent S9 design review

**Session:** New conversation after S9-0 pass. Read-only; no implementation or image changes.

**Review questions:**

- Does S9 use exactly `2ef88427`, while keeping `71da5061` documentation-only?
- Is the no-ignore command authoritative and free of broad exclusion or retry substitution?
- Are all eight Docker nodeids required, with only the delegated cgroup smoke skip allowed?
- Does every Docker test receive candidate-bound provisional Service/client identity evidence?
- Are S9 provisional images clearly separated from S10 final production image/provenance?
- Are source immutability, external evidence, failure routing and independent seal review explicit?
- Are S8 carried evidence and S10 W1/W2/Compose/v8 ownership preserved?

**Output:** `p2-r6-s9-design-review.md` containing reviewed design/execution SHA, findings,
`review_status: pass|fail` and `allow_s9_implementation: yes|no`.

**Exit:** zero design blockers. A finding returns to the S9 design/plan and S9-0 is repeated if
entry scope or authority changes. The reviewer does not patch the issue.

**Prompt:** `只读审核 S9 candidate seal 设计、image provenance、no-ignore gate 和回退边界。`

## 4. S9-2 - Candidate checkout and provisional image

**Session:** New conversation after S9-1 pass; container boundary. Continue into S9-3 only if the
checkout, image identities and build inputs remain unchanged.

**Allowed scope:** clean detached worktree provisioning, retained-cache Service/client image build,
image inspection, Compose configuration and baseline resource inventory. No source or build-input
edits.

**Tasks:**

1. Create/use a detached clean checkout at `2ef884278b4998dde1e5fe224532c89b7a0cd73a` on the
   remote builder/gate-host configuration used by S7. Record local/remote helper identity and
   worktree status.
2. Run the canonical identity helper and bind `candidate_sha`, `build_input_revision`,
   `source_tree_sha256` and lock hashes to the checkout.
3. Build or resolve the Service image with retained cache and the client image/host runner. Verify
   immutable IDs and labels match the candidate and effective inputs. A stale `5f474ce2` image is
   ancestor evidence only and cannot satisfy this step.
4. Render Compose config and verify no host port, resident client service, host-root mount or
   unscoped Docker resource is introduced. Capture process/thread/Dolt/query-temp/work-root and
   project/network/volume baselines.

**Evidence:** `p2-r6-s9-step-2-provisional-image.md`, including commands, image IDs/labels, source
identity, client identity, Compose boundary and baseline inventories.

**Exit:** candidate-bound provisional identity and preflight pass; no residual. Any image/build/
container failure is a no-go and returns to this step. A build-input or deployment change stops S9
and routes to the owning S5/S7/S8 scope before a new image.

**Prompt:** `在 2ef88427 clean checkout 上构建/核对 candidate-bound provisional Service/client image，记录 provenance 和 baseline。`

## 5. S9-3 - Exact no-ignore source regression

**Session:** Continue S9-2 only while source, build inputs, image identities and checkout remain
unchanged. No source edits or handoff edits.

**Authoritative command:**

```bash
./vnext/scripts/run-tests.sh
```

Do not add `-m`, `-k`, `--ignore`, `--ignore-glob`, xfail, skip, retry or accepted-flake
substitution. The exact command must run with the candidate-bound image environment and the same
remote Docker/cache boundary established in S9-2.

**Required evidence:**

- each package command, version, collected, passed, skipped, failed and duration;
- repository-service parallel and serial counts whose sum is the no-ignore service total;
- all eight Docker nodeids collected and individually reported as passed by the exact command;
- only the delegated-target cgroup smoke skip, if the environment variable is absent;
- first-failure and repair ledger (expected `none` for a clean candidate);
- per-node Docker project/network/volume, process/thread/Dolt/query-temp/work-root inventory;
- final clean source/build-input status after the command.

**Acceptance:** exit code `0`, no unexpected skip/failure, all required nodeids pass, all owned
resources return to zero, and the candidate identity remains unchanged.

The eight Docker-starting nodeids required by this gate are exactly:

```text
tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle
tests/test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up
tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up
tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up
tests/test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up
```

Each must be collected and reported as passed by the exact command above. The four
Compose/lifecycle nodeids are also rerun in S10; the four negative probes remain part of the
S9 no-ignore source gate and are not silently replaced by the S10 production image gate.

**Failure route:** a production/test/build-input failure is not repaired in S9. Preserve the failed
output, route to the S8 owning step, rerun its focused/static/full gates, create a new clean source
SHA and restart S9-0. A pure evidence/count discrepancy returns to S9-3/S9-4 without changing the
candidate only when source and image identities are unchanged.

**Evidence:** `p2-r6-s9-step-3-no-ignore-regression.md`.

**Prompt:** `从 2ef88427 candidate-bound image 执行无 ignore 源码全量回归，记录八个 Docker nodeid、counts 和零残留。`

## 6. S9-4 - Hygiene and candidate seal packet

**Session:** Continue S9-3 only if no source/build-input change occurred. Open a new conversation
after any repair or when packet assembly must be independently reconstructed.

**Checks:**

1. Rerun all five exact old-reference searches from operational plan §9 across the repository;
   save raw outputs and classify current authority, negative prohibition, unrelated terminology and
   historical/superseded material. Preserve historical docs.
2. Recompute candidate/source-tree/build-input identity and lock hashes from the clean checkout;
   compare them to S9-2 image labels and S9-3 runtime evidence.
3. Run `git diff --check`, inspect source/build-input paths, and verify no source/test/deployment
   changes or untracked candidate files remain in the detached checkout.
4. Confirm final process/thread/Dolt/query-temp/work-root and Docker object inventory is zero.
5. Assemble the external seal packet without modifying the candidate. It must include the literal
   candidate SHA, all counts, old-reference artifact paths, image/client identities, digests, lock
   hashes, skip classification, cleanup inventory and deferred S10 scope.

**Evidence:** `p2-r6-s9-step-4-candidate-seal-packet.md` plus five raw search files.

**Exit:** packet is complete and internally consistent; candidate remains clean and unmodified.
Any current old-reference hit, identity mismatch, missing count or residual is no-go and returns to
this step or S8 as owning scope.

**Prompt:** `完成 S9 old-reference、provenance、clean-source 和 zero-residual seal packet，不修改 candidate。`

## 7. S9-5 - Independent candidate seal review

**Session:** New conversation. Read-only; no candidate, source, build input, image or handoff edits.

**Review the actual S9 range/evidence:**

- S9-0 identity and builder/gate-host preflight;
- S9-2 provisional image/client labels and immutable IDs;
- S9-3 literal no-ignore command, all package counts, eight Docker nodeids and cleanup inventory;
- S9-4 old-reference raw/classification files, identity recomputation and clean-source packet;
- S8 carried evidence, S10 deferred scope and candidate/documentation SHA separation.

**Output:** `p2-r6-s9-candidate-seal-review.md` with reviewed SHA/range, finding count, severity,
concrete command/path evidence, `review_status: pass|fail` and `allow_s9_seal: yes|no`.

**Finding routing:**

| finding type | return step | required rerun before review |
| --- | --- | --- |
| entry/authority/prerequisite | S9-0 or S9-1 | affected preflight/review and new evidence |
| image/client/provenance/container boundary | S9-2 | candidate-bound image, labels, Compose config and inventory |
| source regression/count/nodeid | S9-3 or S8 owner | exact no-ignore command and affected focused gate |
| old-reference/hygiene/clean-source packet | S9-4 | five searches, identity recomputation, diff and leak audit |
| candidate immutability/seal scope | S9-0/S9-4 | entry and packet reconstruction; new review |

The reviewer never fixes a finding. After repair, preserve the failed review, rerun the owning
route, and start a fresh S9-5 review. Repeat until `finding_count: 0` and `allow_s9_seal: yes`.

**Prompt:** `只读审核 S9 no-ignore counts、八个 Docker nodeid、provenance、clean packet 和 candidate seal 边界。`

## 8. S9-6 - External candidate seal and S9 handoff

**Session:** New conversation after S9-5 pass. Documentation/external evidence only; no candidate
source, test, build input, deployment or image rebuild.

**Verify:**

- S9-5 reviewed the exact packet and allowed the seal;
- candidate SHA is still literal `2ef884278b4998dde1e5fe224532c89b7a0cd73a`;
- source/build-input checkout remains clean and unchanged;
- all required counts, nodeids, image labels, old-reference artifacts and zero-residual evidence
  are present;
- S10 final image/provenance/Compose/W1/W2/v8 scope remains explicit.

**External seal schema:**

```yaml
stage: P2-R6-S9
stage_status: pass
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
no_ignore_source_regression: pass
all_eight_docker_nodeids: pass
candidate_bound_provisional_images: pass
old_reference_classification: pass
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
independent_seal_review: pass
candidate_seal: pass
S9_exit: pass
S10_ready: yes
production_retest_required: yes
phase_2_complete: no
deferred_scope:
  - S10 final production image/provenance/container gate
  - S10 four Compose nodeids on the sealed candidate
  - S10 W1/W2 repeat and Candidate A v8 formal --runs 5
```

**Exit:** the exact external seal is recorded and handed to S10. Any missing field or changed
source/build input is `no-go`; documentation cannot turn a failed/missing gate into a seal.

**Prompt:** `在独立 seal review 通过后，记录 literal CANDIDATE_SHA 和 S10-ready external handoff。`

## 9. S9 completion decision

S9 is complete only when S9-0 through S9-6 have current records, S9-5 has zero findings,
S9-6 records `candidate_seal: pass` and `S10_ready: yes`, and the sealed candidate remains the
literal `2ef88427`. S10 then owns the final production image, no-ignore final gate, Compose,
W1/W2, v8 and final residual/provenance evidence.

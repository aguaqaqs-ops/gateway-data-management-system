# P2-R6-S9 Final Candidate Seal Design

状态：Design baseline frozen by discussion; independent design review required

日期：2026-08-17

适用范围：`P2-R6-S9` exact source candidate sealing, no-ignore source regression,
candidate-bound provisional image provenance and independent seal review. 本文不重新拥有
Repository Service public Contract、S8 source fixes、S10 final production image、S10 Compose/
W1/W2/v8 gates 或 Phase 2 exit。

## 1. Authority and entry

权威顺序：

1. Repository Service Contract and referenced contract owners;
2. P2 Versioned Repository Implementation Design;
3. [P2-R6 Operational Closure Execution Plan](p2-r6-operational-closure-execution-plan.md)
   §§8–12;
4. [P2-R6-S8 final handoff](../../temporary/p2-r6-s8-final-handoff.md);
5. [P2-R6-S7 final handoff](../../temporary/p2-r6-s7-final-handoff.md) for ancestor container
   evidence;
6. Testing Conventions and repository `AGENTS.md`.

S9 starts from the literal clean source SHA recorded by S8:

```yaml
branch: phase1/gate-ownership-repair
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s8_handoff_head: 71da506171d01bbccdf2c54137949cdd0bff234e
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s8_exit: pass
s9_ready: yes
production_retest_required: yes
phase_2_complete: no
```

`71da5061` is a documentation-only handoff descendant and is not the candidate source. The S9
source gate uses a clean detached checkout at `2ef88427`; any source, test, dependency, build-input
or deployment change creates a new candidate and returns to its owning earlier stage.

## 2. Goal and non-goals

### 2.1 Goal

Freeze one exact source candidate and prove it through the authoritative no-ignore source gate,
including the eight Docker-starting nodeids previously excluded by S8. S9 must produce:

- an entry/preflight record for the literal candidate and remote builder/gate-host prerequisites;
- candidate-bound service and client provisional image identity evidence for the Docker tests;
- exact package/nodeid counts for `./vnext/scripts/run-tests.sh` with no `--ignore`;
- five old-reference searches and a final source/build-input/provenance packet;
- an independent read-only seal review with zero open findings;
- an external candidate seal record consumed by S10.

### 2.2 Explicit non-goals

- no production/test/source/build-input repair inside S9;
- no amend, rebase, squash, candidate self-reference or source edit after the clean candidate is
  selected;
- no use of the ancestor `5f474ce2` image as current-candidate validation;
- no final production image/provenance transfer or Phase 2 completion claim;
- no final W1/W2 repeat, Candidate A v8 `--runs 5`, or S10 production gate;
- no accepted skip, retry, xfail, broad marker exclusion or old-image substitution.

## 3. Confirmed decisions

### 3.1 Exact source gate

S9 runs this command from the clean `2ef88427` checkout, without any marker or file exclusion:

```bash
./vnext/scripts/run-tests.sh
```

The command must record every package's command, collected, passed, skipped, failed and duration
counts. All eight nodeids in the three Docker-starting files must be collected and pass. The only
allowed environment skip is the pre-existing delegated-target cgroup smoke test when
`GATEWAY_P2R1_TARGET_CONTAINER != "1"`; that nodeid is not an S9 required Docker nodeid.

### 3.2 Candidate-bound provisional images

The Docker tests call `ensure_repository_service_image()` and, where required,
`ensure_client_image()`. These helpers compute identity from the current clean checkout and build
or reuse only when labels match it. S9 therefore uses the same retained-cache remote
builder/gate-host configuration used by S7 and records, for every provisional image:

- immutable image ID;
- candidate SHA `2ef88427`;
- build-input revision and effective source-tree digest for the Service image;
- Service and client lock hashes;
- client candidate/lock labels or host-runner identity;
- Compose project/network/volume and final zero-residual inventory.

These are candidate-bound S9 gate artifacts, not the S10 final production image. S10 rebuilds and
transfers the exact sealed candidate independently.

### 3.3 Immutability and evidence ownership

The candidate is sealed only after no-ignore regression, provenance packet assembly and independent
review pass. The seal record is external to the candidate or a docs-only audit artifact created
after the candidate SHA is fixed; it never changes `validated_code_sha`. A source/build-input change
after selection invalidates the seal and routes back to S8. A documentation/evidence correction does
not change the candidate but requires the affected S9 review to repeat.

All S9 records, raw search outputs and command logs are written in a separate documentation
worktree or external audit location. They must never appear as tracked or untracked files inside the
detached candidate checkout, because candidate identity computation requires a clean worktree.

### 3.4 Review and failure boundaries

S9 design review and independent seal review are read-only. A review finding is preserved and routed
to its owning S9 step; source/test/build failures route to the S8 owning step and restart S9 from a
new clean SHA. No review or handoff step repairs implementation or changes acceptance semantics.

## 4. Identity and provenance model

| fact | owner | S9 treatment |
| --- | --- | --- |
| literal source candidate | Git | fixed `2ef88427`; no self-reference |
| effective build-input revision | build-context helper | recompute on clean candidate; record exact SHA |
| effective source-tree digest | build-context helper | recompute on clean candidate; record exact digest |
| Service lock hash | `repository_service/uv.lock` | record and compare to image label |
| client lock hash | `repository_client/uv.lock` | record and compare to client label/runner |
| provisional Service image | Docker/builder | candidate-bound identity only; S10 rebuilds final |
| provisional client image | Docker/builder | candidate/lock-bound identity only |
| final production image | S10 | deferred; never inferred from S9 provisional image |
| source regression result | S9 exact command | no-ignore counts and skip classification |

The candidate identity, source-tree digest, build-input revision, lock hashes and image IDs must be
captured in one evidence packet so that a later S10 gate cannot silently mix identities.

## 5. Acceptance matrix

| invariant | required evidence | owner |
| --- | --- | --- |
| exact entry | branch, clean detached checkout, literal `2ef88427`, S8/S7 ancestry | S9-0 |
| environment readiness | Docker/Compose, retained cache, remote builder/gate-host and secret prerequisites | S9-0 |
| design closure | independent design review has zero blockers | S9-1 |
| provisional image identity | Service/client IDs and labels match `2ef88427` and effective inputs | S9-2 |
| no-ignore regression | exact command, all package counts, all 8 Docker nodeids pass | S9-3 |
| old-reference closure | five exact searches rerun and classified; historical docs preserved | S9-4 |
| clean source | no source/build-input change after regression; `git diff --check` pass | S9-4 |
| seal review | independent review has zero findings and checks packet/identity/counts | S9-5 |
| candidate seal | external record fixes `CANDIDATE_SHA=2ef88427` and S10 input | S9-6 |

S9 exit requires:

```yaml
stage: P2-R6-S9
stage_status: pass
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
no_ignore_source_regression: pass
all_eight_docker_nodeids: pass
candidate_bound_provisional_images: pass
old_reference_classification: pass
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

## 6. Risk and proportional assurance

- S9 proves candidate identity and source behavior; it does not repeat S6 capacity or claim final
  production behavior.
- Provisional images are required only because the exact no-ignore command includes Docker tests.
  Their labels and immutable IDs are evidence, while S10 remains the final image owner.
- A stale image, missing label, unclassified skip, residual resource, or mixed source/build-input
  identity is a no-go, not a warning.
- No new public state, helper service, UID, IPC, recovery state machine or threat model is added.

## 7. Design verdict

```yaml
design_status: ready_for_independent_review
scope: exact candidate seal, no-ignore source regression, provisional image identity and seal review
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
remote_builder_gate_host: same S7 retained-cache configuration
provisional_image_in_s9: yes
final_production_image_in_s9: no
independent_design_review_required: yes
independent_seal_review_required: yes
phase_2_complete: no
next: P2-R6-S9 execution plan
```

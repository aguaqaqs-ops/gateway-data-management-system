# P2-R6-S8 Full Regression and Candidate Preparation Design

状态：Design baseline frozen by discussion; independent design review required before implementation

日期：2026-08-16

适用范围：`P2-R6-S8` source regression, test classification, operational residue audit and
candidate preparation. 本文不重新拥有 Repository Service public Contract、S3 production
semantics、S7 Compose lifecycle semantics、S9 exact candidate seal 或 S10 final production gate。

## 1. Authority and entry

权威顺序：

1. [Repository Service Contract](../contracts/repository-service.md) and its referenced
   contract owners;
2. [P2 Versioned Repository Implementation Design](p2-versioned-repository-implementation-design.md);
3. [P2-R6 Operational Closure Execution Plan](p2-r6-operational-closure-execution-plan.md) §§7-10;
4. [P2-R6-S3 staged execution guide](../../temporary/phase-2/p2-r6-s3-staged-execution-guide.md)
   for the closed R5 cleanup dispositions;
5. [P2-R6-S6 capacity evidence](../../temporary/p2-r6-ext-w1-stage-i-s6-capacity.md), W2 and
   concurrency evidence for carried capacity facts;
6. [P2-R6-S7 final handoff](../../temporary/p2-r6-s7-final-handoff.md) for the completed deferred
   Compose inventory;
7. [Testing Conventions](../../../testing-conventions.md) and repository `AGENTS.md`.

S8 starts from the clean current HEAD recorded by S8-0. The current tree is a docs-only descendant
of S7's container-validated candidate `5f474ce2`; that documentation delta does not invalidate
S7's `container_validated_code_sha`. S8 must nevertheless re-check the literal HEAD, branch and
worktree rather than inheriting a prior session's state.

The S8 entry decision is already recorded as `S7_exit: pass`, `S8_ready: yes`,
`production_retest_required: yes` and `phase_2_complete: no`. S8 does not convert any of those
boundary flags into a Phase 2 completion claim.

## 2. Goal and non-goals

### 2.1 Goal

Produce a clean, source-level green tree with no open S8 implementation or review finding, while
preserving the previously closed Contract and lifecycle evidence. S8 must provide:

- an exact entry and carried-evidence inventory;
- correct unit/integration/serial classification, including a parked-Dolt unit gate;
- five-package `ruff` and `mypy` results;
- focused regression of the worker cancellation/convergence and resource cleanup boundary;
- the authoritative source regression command with only the three exact Docker-test ignores;
- five-group old-reference classification and saved exact consumer searches before dead-symbol
  deletion;
- a bounded leak audit with zero owned process/thread/query-temp/work-root residual at gate exit;
- an independent read-only review and an S8 handoff that makes S9 the next owner.

### 2.2 Explicit non-goals

- no new public route, DTO, Contract, persisted business state or operational feature;
- no reopening of S3's R5-CLEANUP-01/02/03/04/05/06 implementation dispositions unless a new,
  reproducible S8 failure proves the existing evidence invalid;
- no full W1/W2 capacity rerun; S6 capacity, W2 and concurrency records remain carried evidence;
- no S7 four-nodeid rerun unless an S8 change touches a relevant Compose/container boundary;
- no final no-ignore candidate seal, final production image, W1/W2 final repeat or v8 formal run;
- no accepted-ignore, broad marker exclusion, skip substitution or harmless-flake waiver;
- no repair in a review or handoff step. Findings return to their owning implementation step.

## 3. Confirmed decisions

### 3.1 Closure inventory and ownership

S8 owns only the following current closure inventory:

| item | S8 treatment | authority |
| --- | --- | --- |
| S7 four Compose nodeids and S7 findings | carry as passed evidence; do not reopen without a new affected change | S7 final handoff |
| R5-CLEANUP-01/02/03/04/05/06 implementation dispositions | carry S3 disposition; verify affected source/tests where S8 changes them | S3 guide and R6 plan |
| parked-Dolt unit classification | required S8 gate; any Dolt-dependent unit is a failure | `AGENTS.md` and Testing Conventions |
| five-package ruff/mypy | required S8 gate for `shared_kernel`, `repository_contracts`, `repository_service`, `repository_client`, `backend` | `AGENTS.md` |
| transient bridge-worker convergence | required focused serial/integration evidence; zero final residual | S8 worker policy below |
| old-reference searches | rerun all five groups across the repository and classify current, negative and historical hits | R6 plan §9 |
| exact dead-symbol consumer search | save search output before deleting any confirmed dead helper/parameter/branch | R6 plan §7 and S3 guide |
| leak audit | process/thread/Dolt child/query-temp/work-root inventory for S8-owned runs | proportional assurance policy |

Historical review records are not current findings by themselves. A historical hit becomes an S8
finding only when it is a current production/test/build reference, contradicts an active authority,
or is a reproducible failure in the S8 gate.

### 3.2 Worker warning and residual policy

The message `versioned read arrow bridge worker did not exit in time` is a diagnostic signal, not an
automatic failure. The S8 focused gate must prove bounded convergence after cancellation or shutdown:

- the bridge registry is empty;
- owned Dolt child processes are reaped;
- query temporary files are absent;
- S8-owned host threads and test work roots return to their baseline;
- the convergence duration and all non-zero intermediate counts are recorded.

The warning is a failure if the bounded convergence deadline expires, any owned residual remains, or
the result cannot distinguish a transient diagnostic from a real survivor. A warning-free run is not
required if the above contract is met and the evidence is complete.

The existing owner nodeid is:

```text
tests/test_versioned_read_http_integration.py::test_http_disconnect_cancels_worker_and_cleans_query_files
```

Supporting cancellation and shutdown tests may be run in the same focused batch, but the owner above
must remain the named S8 worker-convergence gate. Fixed time budgets and subprocess/thread lifecycle
make these tests `serial` and they run with `-n 0`.

### 3.3 Full regression boundary

S8 uses the exact source regression command with the three actual Docker-test files excluded:

```bash
./vnext/scripts/run-tests.sh \
  --ignore=tests/test_import_compose_e2e.py \
  --ignore=tests/test_versioned_read_compose_e2e.py \
  --ignore=tests/test_compose_lifecycle_negative_probes.py
```

No broad marker exclusion is allowed. Static Dockerfile/Compose tests, build-harness unit tests,
real Dolt integration and all non-Docker package tests remain in the command. S9 owns the same command
without `--ignore` immediately before exact candidate sealing.

### 3.4 Capacity and container boundary

S8 does not repeat the S6 W1/W2 capacity matrices. It may run a focused worker/leak regression using
the existing local/integration harness. If a source change touches Dockerfile, dependency closure,
Compose, entrypoint, environment wiring, health/readiness, client image or container harness, the
affected current candidate must be rebuilt and its affected directed gate rerun. Otherwise a pure
Python/test/docs change may defer container rebuild to S9/S10; the old S7 image remains ancestor
evidence only.

### 3.5 Context and review boundaries

- One implementation step keeps its local code, focused tests and step evidence in one conversation.
- A design review, independent implementation review, candidate preparation and handoff each start
  in a new conversation.
- Reviewers are read-only. A finding routes back to the owning implementation step, whose affected
  tests and evidence must be rerun before review repeats.
- S8 handoff is documentation-only and records the source SHA separately from any later container
  validation SHA.

## 4. Acceptance matrix

| invariant | required evidence | result owner |
| --- | --- | --- |
| entry identity | branch, literal HEAD, clean worktree, S7 ancestor and carried handoff flags | S8-0 |
| no unit/Dolt misclassification | parked-Dolt `-m unit` passes and binary is restored even on failure | S8-2 |
| static quality | five-package ruff/mypy and `git diff --check` pass | S8-2/S8-5 |
| worker convergence | owner nodeid passes, warning policy is satisfied, zero final residual | S8-3 |
| source regression | exact command/count report passes with only three exact Docker ignores | S8-4 |
| old-reference closure | five groups searched and manually classified; historical docs preserved | S8-5 |
| dead-symbol safety | exact consumers saved before deletion and affected tests pass | S8-3/S8-5 |
| review closure | independent review has zero open blocker or implementation finding | S8-6 |
| clean source exit | final S8 HEAD is clean and no source/build input changed after review | S8-7 |

S8 exit requires every row to pass, no skipped required test, no unresolved finding, and a handoff
that declares:

```yaml
stage: P2-R6-S8
stage_status: pass | no-go
entry_sha: <literal S8 entry SHA>
validated_code_sha: <exact clean S8 source SHA>
container_validated_code_sha: <same SHA | deferred>
parked_dolt_unit: pass | fail
five_package_static: pass | fail
worker_convergence: pass | fail
source_regression_with_exact_docker_ignores: pass | fail
old_reference_classification: pass | fail
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes | no
independent_review: pass | fail
S8_exit: pass | no-go
S9_ready: yes | no
production_retest_required: yes
phase_2_complete: no
deferred_scope:
  - S9 exact candidate seal and no-ignore source gate
  - S10 final production image/provenance/container gate
  - S10 W1/W2 repeat and Candidate A v8 formal --runs 5
```

`container_validated_code_sha: deferred` is correct when S8 changes only Python/tests/docs and no
current-stage container gate is triggered. It must never be reported as current-container PASS.

## 5. Failure and reopen rules

- A first test, classification or static failure returns to the owning implementation scope; the
  failed command and evidence are retained.
- A worker timeout, unreaped child, surviving thread, query temp or work root is an S8 no-go until the
  focused owner gate passes with bounded cleanup.
- A skipped test, broad ignore, missing count, unclassified current old-reference hit or review gap
  is an evidence failure, not a warning.
- A Docker/container-boundary change invalidates affected prior image evidence and requires a rebuild
  before its directed gate is called PASS.
- A public Contract, persisted state, restore semantic or topology change stops S8 and requires the
  owning design/ADR review before implementation continues.
- S8 does not repair findings in S8-6 or S8-7; it routes them back to S8-2, S8-3, S8-4 or S8-5 and
  repeats the independent review.

## 6. Design verdict

```yaml
design_status: ready_for_independent_review
scope: source regression, classification, residue audit and candidate preparation
public_contract_changed: no
capacity_rerun_in_s8: no
exact_docker_ignores: 3
worker_warning_policy: bounded_convergence_zero_residual
independent_review_required: yes
phase_2_complete: no
next: P2-R6-S8 execution plan
```

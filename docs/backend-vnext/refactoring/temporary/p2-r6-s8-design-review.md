# P2-R6-S8 - Independent Design Review

状态：`pass`

日期：2026-08-16

本记录是 S8-1 的独立只读设计审核。审核对象为冻结的 S8 full regression/candidate
preparation design、execution plan，以及 S8-0 entry reconciliation、S7 final handoff、
S3 cleanup dispositions、S6 capacity evidence、Testing Conventions 和 R6 operational
closure plan 的相关边界。审核没有修改 production、test、Docker、Compose 或 handoff
输入，也没有运行 pytest、Dolt、Docker、Compose、builder 或 capacity gate。

权威设计：[P2-R6-S8 Full Regression and Candidate Preparation Design](../formal/plans/p2-r6-s8-full-regression-design.md)

权威执行计划：[P2-R6-S8 Full Regression and Candidate Preparation Execution Plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md)

入口记录：[P2-R6-S8 Step 0 - Entry Reconciliation](p2-r6-s8-step-0-entry-reconciliation.md)

上游 handoff：[P2-R6-S7 Final Handoff](p2-r6-s7-final-handoff.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_design_sha: 77a43ebea9d8c97bac3e3c6987307e71413a7e4b
reviewed_plan_sha: 77a43ebea9d8c97bac3e3c6987307e71413a7e4b
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2cc15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
s8_entry_is_ancestor: yes
review_worktree_clean_at_start: yes
post_s7_delta: formal_and_temporary_docs_only
production_code_changed_by_review: no
test_or_deployment_input_changed_by_review: no
public_contract_changed: no
phase_2_complete: no
```

`reviewed_design_sha` and `reviewed_plan_sha` are the literal clean HEAD before this review
record is added. `s8_entry_sha` is the clean S8-0 source/reference entry recorded in the
execution plan; the review was performed on its docs-only descendant. The S7 image and
Compose results remain ancestor evidence for `5f474ce2`, not current-HEAD container PASS.

Read-only identity checks at review start:

```text
git rev-parse HEAD: 77a43ebea9d8c97bac3e3c6987307e71413a7e4b
git branch --show-current: phase1/gate-ownership-repair
git merge-base --is-ancestor 5f474ce2 HEAD: yes
git merge-base --is-ancestor 1bfa1d7f HEAD: yes
git diff --check: pass
```

The three source-regression Docker exclusions are present at the reviewed tree:

```text
tests/test_import_compose_e2e.py
tests/test_versioned_read_compose_e2e.py
tests/test_compose_lifecycle_negative_probes.py
```

Each target is a Docker/Compose-starting repository-service test file. No additional ignore,
marker exclusion, `-k`, skip, retry or accepted-flake substitution is authorized.

## Required questions

### 1. Scope and contract boundary

**Pass.** S8 is limited to source regression, marker classification, static quality, operational
residue audit, old-reference/dead-symbol hygiene and candidate preparation. The design explicitly
prohibits a new public route, DTO, persisted business state, Contract change, S3 semantic change,
S7 topology/lifecycle change, S9 candidate seal or S10 production gate. A public Contract,
persisted-state, restore-semantic or topology change stops S8 and routes to its owning design/ADR.

### 2. Carried S3/S6/S7 evidence

**Pass.** S3 R5-CLEANUP-01/02/03/04/05/06 dispositions are carried as closed evidence and are
reopened only by a new reproducible S8 failure. S6 W1/W2/capacity/concurrency evidence is carried;
the design forbids a full capacity rerun in S8. S7's four Compose nodeids, independent reviews and
zero-residual inventories remain passed ancestor evidence, with a rerun only if S8 touches a
container boundary. The plan keeps `production_retest_required: yes` and `phase_2_complete: no`.

### 3. Worker warning and cleanup acceptance

**Pass.** The warning `versioned read arrow bridge worker did not exit in time` is correctly treated
as a diagnostic rather than a warning-count gate. The owner and supporting nodeids are identified,
fixed-time/subprocess/thread tests are required to run as `integration`/`serial` with `-n 0`, and
acceptance requires bounded convergence plus zero final bridge, Dolt child, query-temp, host-thread
and work-root residual. A warning becomes no-go when the deadline expires, a residual remains or
the evidence cannot distinguish a transient diagnostic from a survivor. This preserves business
results while making cleanup evidence authoritative.

### 4. Source regression and Docker boundary

**Pass.** S8 owns the authoritative source command with exactly the three Docker-test ignores;
the full no-ignore command and immutable candidate seal remain S9-owned. The execution plan
forbids broad exclusions and requires exact collected/passed/skipped/failed/duration counts for
every package. Pure Python/test/docs changes may defer the image, while Dockerfile, dependency,
Compose, entrypoint, environment, health/readiness, client-image or container-harness changes
invalidate ancestor image evidence and require the affected current-candidate directed gate.
The current docs-only tree is therefore `deferred`, never current-container `passed`.

### 5. Capacity and phase ownership

**Pass.** S8's worker/leak regression is intentionally narrower than S6 W1/W2 matrices. W1/W2
full repeats, final production image/provenance, the four final Compose nodeids and Candidate A v8
formal `--runs 5` remain explicit S10 scope. S9 owns no-ignore source regression and immutable
candidate sealing. This prevents S8 from silently converting ancestor evidence into current
candidate evidence or claiming Phase 2 completion.

### 6. Classification, hygiene and review routing

**Pass.** The plan requires a parked-Dolt `-m unit` gate with unconditional binary restoration,
five-package `ruff`/`mypy`, strict marker collection and no Dolt initialization for pure unit
classification. It requires all five repository-wide old-reference searches to be rerun and
manually classified without deleting historical material. Exact `rg` consumer output must be
saved before every new dead-symbol deletion. Every review finding has an owning return step and
required rerun; reviewers are read-only and cannot repair or hide findings. Missing tests, skipped
required tests, broad ignores, unclassified current references and residual resources are evidence
failures/no-go conditions.

### 7. Handoff identity and acceptance schema

**Pass.** The S8 acceptance matrix and handoff schema distinguish `entry_sha`, clean
`validated_code_sha`, `container_validated_code_sha` (`deferred` when appropriate), S9 readiness,
production retest and `phase_2_complete`. S8 cannot declare exit or S9 readiness without every
closure row, exact counts, zero residual inventory, zero open review findings and a clean source
tree. The design retains explicit S9/S10 deferred scope rather than folding it into S8.

## Findings

No blocker findings.

## Non-findings and implementation conditions

- The three ignored files are Docker/Compose tests, not a general Docker test glob. S8 execution
  must preserve the literal command and S9 must rerun without any ignore.
- A warning-free worker run is not required, but convergence timing, intermediate inventories and
  final zero residual must be recorded. A missing inventory is an evidence failure even when tests
  pass.
- The parked-Dolt unit gate and all fixed-time lifecycle checks must retain the repository's
  declared `unit`/`integration`/`serial` markers; classification is part of the acceptance result,
  not an after-the-fact annotation.
- The S7 image digest and Compose reports must continue to be labeled as `5f474ce2` ancestor
  evidence. Any S8 container-boundary change supersedes that evidence and requires a current
  rebuild before a directed gate can be called pass.

## Verdict

```yaml
review_status: pass
finding_count: 0
blocker_count: 0
allow_s8_implementation: yes
public_contract_changed: no
persisted_state_changed: no
topology_changed: no
worker_warning_policy: bounded_convergence_zero_residual
exact_docker_ignores: 3
capacity_rerun_in_s8: no
container_rebuild_required_at_review: no
container_gate_for_current_head: deferred
last_verified_container_code_sha: 5f474ce2cc15f11ea07f263edf3fb04c771d410
production_code_changed_by_review: no
phase_2_complete: no
next: S8-2 - classification and static gates
```

独立设计审核通过，允许进入 S8-2。后续实现必须保留本记录列出的 bounded-convergence、
exact-ignore、marker、count、provenance 和 finding-routing 条件；本记录不授权 S8 exit、
S9 candidate seal、S10 production/container gate 或 Phase 2 completion claim。

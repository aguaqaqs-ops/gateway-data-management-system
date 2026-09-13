# P4-R6-S4 Independent Findings-First Review

状态：**PASS_AFTER_PROVENANCE_CLOSURE — F1 closed; authoritative gates pass on sealed candidate**

日期：2026-09-13

Reviewer：independent gate review (Bugbot code review + gate evidence assembly)

上游：[P4-R6-S0 Independent Entry Acceptance](p4-r6-s0-independent-entry-acceptance.md)、
[P4-R6-S1 Harness Confirmation](p4-r6-s1-harness-confirmation.md)、
[P4-R6-S6 Container and Provenance Evidence](p4-r6-s6-container-provenance-evidence.md)

```yaml
step_id: P4-R6-S4
reviewed_candidate_head: 7fbddc731d304be719fb980d6c538a6b9cf6910f
reviewed_worktree_committed: true
reviewed_worktree_python_source_test_tree: sha256:5f49d396981f1b75f43b092c71979c3f56ea8742e639db717316a5992028f941
reviewed_worktree_python_file_count: 308
decision: pass_after_provenance_closure
findings:
  - id: P4-R6-S4-F1
    severity: P1
    owner: P4_compose_provenance_gate
    summary: require_clean_worktree blocks eight Compose owners on uncommitted P4-R6 candidate
    status: closed
p4_r6_s4: pass_after_provenance_closure
p4_r6_s5: not_applicable_provenance_precondition
container_gate: pass
reopen_R1_R5: no
next_step: p4_r6_s7_final_handoff
new_explicit_authorization_required: yes
```

## 1. Scope reviewed

| Area | Result |
| --- | --- |
| Finding-scoped test diff (`test_operation_contracts.py`, `test_operation_worker_integration.py`) | Bugbot rereview: **no bugs**; registry slash positive/negative owners and serial marker match S0 acceptance |
| R1–R5 contract / schema / CAS drift in test diff | **none** |
| Preview composition expansion into R6 | **none** in test diff |
| Authoritative `./vnext/scripts/run-tests.sh` on clean gate worktree | **4288 passed, 0 failed** |
| Five-package ruff/mypy | **pass**; lockfiles unchanged |
| S6 backend/worker rebuild + smoke | **pass** (worker ExitCode=0, source digest match) |
| Eight Compose owner nodeids | **8/8 pass** |

## 2. Finding closure

### P4-R6-S4-F1 — Compose provenance gate requires clean worktree

**Original failure (historical):** uncommitted P4-R6 candidate worktree caused
`ProvenanceError: worktree is dirty` in `ensure_repository_service_image()` → eight Compose
owner failures. Recorded as `container_gate: fail_dirty_worktree`.

**Closure action:** sealed candidate commit `7fbddc731d304be719fb980d6c538a6b9cf6910f` +
detached clean gate worktree with empty porcelain. Authoritative runner and explicit eight
nodeids **re-passed** with actual Compose e2e execution.

**Status:** **closed**. No production or test remediation beyond S0-accepted finding-scoped
tests and formal docs.

### 2.1 Partial S6 evidence (historical only)

Pre-closure backend/worker build/smoke and missing-secret attempts remain **partial historical
evidence** only. They do not bind to the sealed candidate and cannot override F1 while open.
Post-closure evidence is authoritative in [p4-r6-s6-container-provenance-evidence.md](p4-r6-s6-container-provenance-evidence.md).

## 3. Fault matrix disposition (S3 binding)

All matrix rows remain covered by unique owners listed in S0 acceptance §5. Clean-worktree
authoritative runner provides **pass** evidence for integration/serial/Compose owners. No
duplicate owner or marker downgrade observed.

## 4. Decision

```text
decision: pass_after_provenance_closure
reason: sealed candidate + clean worktree; authoritative runner and Compose 8/8 pass
code_review: pass (Bugbot rereview, finding-scoped tests)
reopen_R1_R5: no
p4_r6_s5: not_applicable_provenance_precondition (no authorized production remediation in closure)
```

S5 is **not applicable** (closure was provenance-only; no new findings requiring remediation).

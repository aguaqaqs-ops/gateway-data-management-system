# P4-R6-S4 Independent Findings-First Review

状态：**CHANGES_REQUIRED — test remediation accepted; authoritative Compose gate blocked by dirty worktree**

日期：2026-09-13

Reviewer：independent gate review (Bugbot code review + gate evidence assembly)

上游：[P4-R6-S0 Independent Entry Acceptance](p4-r6-s0-independent-entry-acceptance.md)、
[P4-R6-S1 Harness Confirmation](p4-r6-s1-harness-confirmation.md)

```yaml
step_id: P4-R6-S4
reviewed_candidate_head: 7e8cea7b3454a8cfdd7c2ba880becee5c427a0de
reviewed_worktree_committed: false
reviewed_worktree_python_source_test_tree: sha256:5f49d396981f1b75f43b092c71979c3f56ea8742e639db717316a5992028f941
reviewed_worktree_python_file_count: 308
decision: changes_required
findings:
  - id: P4-R6-S4-F1
    severity: P1
    owner: P4_compose_provenance_gate
    summary: require_clean_worktree blocks eight Compose owners on uncommitted P4-R6 candidate
p4_r6_s5: not_applicable_provenance_precondition
container_gate: fail_dirty_worktree
next_step: seal_candidate_commit_and_clean_worktree_rerun
new_explicit_authorization_required: yes
```

## 1. Scope reviewed

| Area | Result |
| --- | --- |
| Finding-scoped test diff (`test_operation_contracts.py`, `test_operation_worker_integration.py`) | Bugbot: **no bugs**; registry slash positive/negative owners and serial marker match S0 acceptance |
| R1–R5 contract / schema / CAS drift in test diff | **none** |
| Preview composition expansion into R6 | **none** in test diff |
| P4 owner focused gates (unit / integration-not-serial / serial) | **286 passed**, 0 failed |
| Five-package ruff/mypy | **pass**; lockfiles unchanged |
| Authoritative `./vnext/scripts/run-tests.sh` (no ignore) | **exit 1** — see F1 |
| S6 backend/worker rebuild + Compose owners | partial historical evidence only; see §2.1 |

## 2. Finding

### P4-R6-S4-F1 — Compose provenance gate requires clean worktree

**Evidence:** `./vnext/scripts/run-tests.sh` completed shared_kernel through repository_service
parallel with **0 failures**, then repository_service serial reported **8 failed** on the eight
Compose owner nodeids. Root cause:

```text
support.build_context_digest.ProvenanceError: worktree is dirty
```

`compute_image_identity()` → `require_clean_worktree()` rejects any `git status --porcelain`
output. The P4-R6 candidate worktree intentionally contains:

- modified P4 formal docs and two backend test files;
- untracked P4-R6 and P5-5B formal docs.

This is **not** a runtime contract defect and **not** a P5-5A “non-blocker” exemption. Under
P4-R6 policy the eight Compose owners must be re-judged on the current gate; they **failed** for
provenance infrastructure reasons, not because production code regressed.

**Minimal fix (choose one, requires new authorization):**

1. Commit the P4-R6 candidate (docs + two tests) to a sealed tip and rerun authoritative runner
   Compose slice and S6 eight nodeids on a clean worktree; or
2. Explicit gate waiver / alternate provenance binding documented in owning Contract — **not**
   authorized in this task.

### 2.1 Partial S6 evidence (historical only)

A separate S6 attempt rebuilt `backend`/`worker` and observed `worker_ready` → `drain_started` →
`worker_exited` after supplying dev secret environment variables. That smoke run is **partial
historical evidence** only. It does **not** override the eight Compose owner failures above, does
not bind to a sealed candidate commit, and cannot satisfy `container_gate: pass` while F1 remains
open.

## 3. Fault matrix disposition (S3 binding)

All matrix rows are covered by unique owners listed in S0 acceptance §5. Focused P4 owner serial
slice and full backend package run provide **pass** evidence for integration/serial owners. No
duplicate owner or marker downgrade was observed. Detailed row binding for the first gate round is
retained in the interim S7 record; closure evidence will supersede it after provenance rerun.

## 4. Decision

```text
decision: changes_required
reason: authoritative runner Compose slice failed (8/8) on dirty-worktree provenance guard
code_review: pass (Bugbot, finding-scoped tests only)
reopen_R1_R5: no
```

S5 is **not applicable** (no authorized remediation in this task). S6 container evidence is
recorded separately but **cannot** override F1 for `p4_r6_exit`.

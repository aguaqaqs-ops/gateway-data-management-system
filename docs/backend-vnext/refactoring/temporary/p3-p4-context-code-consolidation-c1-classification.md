# P3→P4 Context and Code Consolidation — C1 Classification

状态：`complete`（`c1_continue_plan: yes`；`unresolved_escalations: 0`）

日期：2026-08-23

本记录确认每个文档 path 的 owner、consumer、保留义务与 C2/C3/C4 动作。没有修改 `vnext/**`、没有删除文件、没有创建 pre-tag（提交后创建）。

权威计划：[P3→P4 Context and Code Consolidation Execution Plan](p3-p4-context-and-code-consolidation-execution-plan.md) §7 C1
上游 C0：[p3-p4-context-code-consolidation-c0-inventory.md](p3-p4-context-code-consolidation-c0-inventory.md)
机器可读表：[p3-p4-context-code-consolidation-c1-classification.json](p3-p4-context-code-consolidation-c1-classification.json)
Manifest draft：[p3-p4-cleanup-manifest.yaml](../formal/plans/p3-p4-cleanup-manifest.yaml)

## Continue / stop

```yaml
c1_status: complete
c1_continue_plan: yes
unresolved_escalations: 0
baseline_sha: 31409c8e0c37d8c12a323269ddeefebdb9927955
pre_cleanup_tag: docs/p3-p4-cleanup-pre-20260823
```

## Confirmed counts

| Manifest bucket | 数量 |
| --- | ---: |
| `active` | 23 |
| `normative` | 33 |
| `evidence_pointer` | 2 |
| `retain_in_place` | 10 |
| `archive_from_default` | 25 |
| `deferred` | 7 |

## P4 default reads

- `docs/backend-vnext/refactoring/formal/plans/p4-active-context-index.md` (c2_create) — P4 default entry
- `docs/backend-vnext/refactoring/formal/plans/p3-final-closure-handoff.md` (active) — P3 exit and P4 entry boundary
- `docs/backend-vnext/refactoring/formal/plans/p3-final-closure-f5-independent-acceptance.md` (active) — P3 F5 independent acceptance
- `docs/backend-vnext/refactoring/formal/plans/implementation-stages.md` (active) — Phase map; P4 section
- `docs/backend-vnext/refactoring/formal/contracts/operation-lifecycle-and-integrity.md` (active) — Operation lifecycle owner
- `docs/backend-vnext/refactoring/formal/contracts/external-effect-and-recovery.md` (active) — External effect owner
- `docs/backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md` (active) — Business lifecycle owner
- `docs/backend-vnext/refactoring/formal/contracts/repository-service.md` (active) — Repository service owner
- `docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md` (active) — P3 capability design authority
- `docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md` (active) — Proportional assurance policy
- `AGENTS.md` (optional) — Contributor constraints
- `docs/backend-vnext/testing-conventions.md` (optional) — Testing conventions

## Must retain source pointer

- `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md` ← `vnext/repository_service/tests/test_p2_r1_audit_corrective.py`, `docs/backend-vnext/refactoring/formal/contracts/repository-service.md`
- `docs/backend-vnext/refactoring/formal/plans/p2-r5-commit-pinned-read-execution-plan.md` ← `vnext/repository_service/README.md`
- `docs/backend-vnext/refactoring/temporary/p2-r9-s2-step-e-container-gate.md` ← `vnext/deploy/p2r1-cache/README.md`

## Code bundles (C4 decides)

- `KEEP_EVIDENCE_TOOL`: 1 path(s); default `KEEP`
- `KEEP_P3_REFERENCE`: 1 path(s); default `KEEP`
- `MOVE_REMOVE_CANDIDATE`: 2 path(s); default `DEFER`
- `MOVE_CANDIDATE`: 4 path(s); default `DEFER`
- `RETIRE_DECISION_REQUIRED`: 3 path(s); default `DEFER`
- `KEEP_UNTIL_PROFILE_RETIRED`: 1 path(s); default `KEEP`
- `FOLLOW_HARNESS_DECISION`: 1 path(s); default `DEFER`

## Findings

### `adr-0013-process-links`

- path: `docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md`
- fact: ADR links to P3-R2 S0 and execution plan as table_access pointers.
- action: C2 rewrite links to owning contracts/handoff; not an archive blocker.

### `p3-active-context-process-matrix`

- path: `docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md`
- fact: Default P3 index still lists many process docs slated for archive.
- action: C2 create P4 index; C3 archive process docs and retire P3 index.

### `formal-readme-process-list`

- path: `docs/backend-vnext/refactoring/formal/README.md`
- fact: Formal README still lists R5/R6/R7 S0 and execution plans.
- action: C2 shrink default index to active handoffs/contracts only.

### `final-closure-plan-links`

- path: `docs/backend-vnext/refactoring/formal/plans/p3-final-closure-execution-plan.md`
- fact: Active handoff/F5/design still link to final closure execution plan.
- action: C2 rewrite to handoff/F5/manifest recovery pointer before C3 archive.

### `repository-probe-harness`

- path: `vnext/repository_service/src/gateway_repository_service/target_gate.py`
- fact: Compose repository-probe profile still invokes target_gate.
- action: C4 must decide harness retirement as one bundle with profile/README/tests.


## Verified pre-cleanup tag (C1 exit)

```text
pre_cleanup_tag: docs/p3-p4-cleanup-pre-20260823
pre_cleanup_commit: 4faf10fd905c3cc582ff5a11626b940cc609289e
pre_cleanup_tag_object: 1027ef5e6f766ebc5a064f761cc5e48a22d8646b
```

## C1 exit

```yaml
c1_exit: pass
unresolved_escalations: 0
```

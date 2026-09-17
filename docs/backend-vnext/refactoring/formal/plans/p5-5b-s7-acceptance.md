# P5-5B-S7 Independent Functional Acceptance

状态：**PASS — S7 complete; S8 entry authorized**

日期：2026-09-18

Owner：P5-5B Delivery + Independent reviewer closure

## Exit summary

```yaml
stage: P5-5B-S7-independent-functional-acceptance
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
baseline_commit: 4cda6b9c
remediation_commit: pending
s5_independent_review: pass
s6_independent_review_round: 6
s6_independent_review: pass
s7_independent_review: changes_required → pass (review-3)
decision: pass
findings_open: []
findings_reclassified: [S7-F2]
accumulated_submit_unit: pass_319
accumulated_submit_integration: pass_27
backend_static: pass
five_package_static: deferred
authoritative_runner: deferred
container_conjunction_gate: deferred
s8_entry: eligible
implementation_authority_unchanged: true
p5_5b_slice_exit: not_declared
```

## Stage lineage

| Stage | Review | Result |
| --- | --- | --- |
| S5 | [p5-5b-s5-independent-review.md](p5-5b-s5-independent-review.md) | pass (retroactive) |
| S6 | [p5-5b-s6-independent-review-5.md](p5-5b-s6-independent-review-5.md) | pass |
| S7 review | [p5-5b-s7-independent-review.md](p5-5b-s7-independent-review.md) | changes_required |
| S7 remediation r1 | [p5-5b-s7-remediation-handoff.md](p5-5b-s7-remediation-handoff.md) (draft) | rejected @ review-2 |
| S7 closure | [p5-5b-s7-independent-review-3.md](p5-5b-s7-independent-review-3.md) | pass |

## Deliverables

- Cross-stage functional matrix reviewed against design §6/§8–§11/§13
- Accumulated Submit unit selection frozen（§4 27 files, 319 tests @ remediation round 2）
- Finding-scoped remediation：T3 finalize LeaseSession bridge、architecture 精确屏障、operator capability HTTP
- S7-F2 reclassified to S8（完整 compose journey；无效 smoke 已删除）
- **Not in S7 scope**：五包 static、权威 runner、三镜像 conjunction/full journey smoke（S8）

## S8 prerequisites recorded

1. Remediation commit sealed on branch
2. Run `./vnext/scripts/run-tests.sh` without ignore
3. Five-package ruff/mypy
4. Rebuild current-HEAD backend/worker/repository-service images
5. Container gate：Accept→upload→import→poll→T3→read + restart recovery

```yaml
next_step: P5-5B-S8 final current-HEAD gate and slice handoff
```

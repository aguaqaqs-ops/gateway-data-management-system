# P5-5B-S7 Independent Functional Acceptance

状态：**changes_required — F8 record sealing remediated; pending review-6 mechanical verification**

日期：2026-09-18

Owner：P5-5B Delivery + Independent reviewer closure

## Exit summary

```yaml
stage: P5-5B-S7-independent-functional-acceptance
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
baseline_commit: 4cda6b9c
remediation_round_2: 30193dd5d3b34ec82da382cd7d85650cd98a3bb7
remediation_round_3: 7c511c4b8b59842b67d24083abf274ba620b2e7e
implementation_seal: 7c511c4b8b59842b67d24083abf274ba620b2e7e
records_head: b80a283f689ed6e957f932a72bc283aeacbef5be
s5_independent_review: pass
s6_independent_review: pass (p5-5b-s6-independent-review-5.md)
s7_independent_review: changes_required → remediation round 3 @ review-4
decision: changes_required
findings_closed: [S7-F1, S7-F4, S7-F6, S7-F7]
findings_reclassified: [S7-F2]
findings_remediated_pending_review: [S7-F8]
findings_open: []
accumulated_submit_unit: pass_319
accumulated_submit_integration: pass_26
backend_static: pass
five_package_static: deferred
authoritative_runner: deferred
container_conjunction_gate: deferred
s8_entry: blocked
implementation_authority_unchanged: true
p5_5b_slice_exit: not_declared
```

> `b48ca592` 曾 pin 不可解析的 amend 孤本 `5de2e0b7…`；authoritative implementation seal 为可达的 `7c511c4b`。

## Stage lineage

| Stage | Review | Result |
| --- | --- | --- |
| S5 | [p5-5b-s5-independent-review.md](p5-5b-s5-independent-review.md) | pass (retroactive) |
| S6 | [p5-5b-s6-independent-review-5.md](p5-5b-s6-independent-review-5.md) | pass |
| S7 review | [p5-5b-s7-independent-review.md](p5-5b-s7-independent-review.md) | changes_required |
| S7 remediation r1 | [p5-5b-s7-remediation-handoff.md](p5-5b-s7-remediation-handoff.md) (draft) | rejected @ review-2 |
| S7 remediation r2 | `30193dd5` | rejected @ review-4 (S7-F7/F8) |
| S7 review-4 | [p5-5b-s7-independent-review-4.md](p5-5b-s7-independent-review-4.md) | changes_required |
| S7 remediation r3 | `7c511c4b` | F7 closed @ review-5 |
| S7 review-5 | [p5-5b-s7-independent-review-5.md](p5-5b-s7-independent-review-5.md) | changes_required (F8 open) |
| S7 F8 closeout | pending | pending review-6 |
| S7 closure | [p5-5b-s7-independent-review-3.md](p5-5b-s7-independent-review-3.md) | **superseded** |

## Deliverables

- Cross-stage functional matrix reviewed against design §6/§8–§11/§13
- Accumulated Submit unit selection frozen（§4 22 unit files, 319 tests）
- Round 2：T3 finalize LeaseSession bridge、architecture 精确屏障、operator capability HTTP
- Round 3：stable abort LeaseSession bridge（S7-F7）+ closure record provenance（S7-F8）
- S7-F2 reclassified to S8（完整 compose journey；无效 smoke 已删除）
- **Not in S7 scope**：五包 static、权威 runner、三镜像 conjunction/full journey smoke（S8）

## S8 prerequisites recorded

1. Review-6 mechanical F8 sealing verification pass
2. Run `./vnext/scripts/run-tests.sh` without ignore
3. Five-package ruff/mypy
4. Rebuild current-HEAD backend/worker/repository-service images
5. Container gate：Accept→upload→import→poll→T3→read + restart recovery

```yaml
next_step: P5-5B-S7 review-6 mechanical F8 sealing verification
s8_entry: blocked
```

# P5-5B-S7 Independent Functional Acceptance

状态：**pass — S7 closure @ review-7 + S7-F2 @ review-8；S8 gate pass @ [p5-5b-s8-handoff.md](p5-5b-s8-handoff.md)（S8-F1 @ review-1）**

日期：2026-09-17 (UTC+8)

Owner：P5-5B Delivery + Independent reviewer closure

## Exit summary

```yaml
stage: P5-5B-S7-independent-functional-acceptance
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
baseline_commit: 4cda6b9c
remediation_round_2: 30193dd5d3b34ec82da382cd7d85650cd98a3bb7
remediation_round_3: 7c511c4b8b59842b67d24083abf274ba620b2e7e
remediation_round_4: e5c43c0c9f71de3cd2e602504ec9034f16add8af
remediation_round_4_fix: d3661fe0eda4a3463afed879c6a5bbec72f79404
implementation_seal: e5c43c0c9f71de3cd2e602504ec9034f16add8af
records_head: pending_hygiene_seal
s5_independent_review: pass
s6_independent_review: pass (p5-5b-s6-independent-review-5.md)
s7_independent_review: pass (p5-5b-s7-independent-review-7.md)
s7_f2_closure_review: pass (p5-5b-s7-independent-review-8.md)
decision: pass
findings_closed: [S7-F1, S7-F2, S7-F4, S7-F6, S7-F7, S7-F8, S7-O2-owner-T3-crash-barrier, S7-O2-owner-repository-restart-journey, R4-F1]
findings_reclassified: []
findings_open: []
accumulated_submit_unit: pass_319
accumulated_submit_integration: pass_26
backend_static: pass
five_package_static: pass
authoritative_runner: pass
container_conjunction_gate: pass
s8_entry: eligible
s8_gate: pass
s8_f1_closure_review: pass (p5-5b-s8-independent-review-1.md)
implementation_authority_unchanged: false
p5_5b_slice_exit: pass_recommended
timezone: Asia/Shanghai
```

> `b48ca592` 曾 pin 不可解析的 amend 孤本 `5de2e0b7…`；Round 3 code seal 为 `7c511c4b`；Round 4 owner evidence seal 为 `e5c43c0c`；`d3661fe0` 为 R4-F1 test-only lease 健壮性修订（§490/491 owner 语义与 `decision: pass` 不变）。

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
| S7 F8 closeout | `b80a283f` | superseded @ review-6 |
| S7 review-6 | [p5-5b-s7-independent-review-6.md](p5-5b-s7-independent-review-6.md) | **superseded** (premature) |
| S7 remediation r4 | `e5c43c0c` | owner evidence @ review-7 |
| S7 remediation r4 fix | `d3661fe0` | R4-F1 lease window（test-only） |
| S7 closure | [p5-5b-s7-independent-review-7.md](p5-5b-s7-independent-review-7.md) | **pass** |
| S7-F2 closure | [p5-5b-s7-independent-review-8.md](p5-5b-s7-independent-review-8.md) | **pass** @ `4d1dc010` |
| S8-F1 closure | [p5-5b-s8-independent-review-1.md](p5-5b-s8-independent-review-1.md) | **pass** @ `460d6f5b` |
| S7 review-3 | [p5-5b-s7-independent-review-3.md](p5-5b-s7-independent-review-3.md) | **superseded** |

## Deliverables

- Cross-stage functional matrix reviewed against design §6/§8–§11/§13
- Accumulated Submit unit selection frozen（§4 22 unit files, 319 tests）
- Round 2：T3 finalize LeaseSession bridge、architecture 精确屏障、operator capability HTTP
- Round 3：stable abort LeaseSession bridge（S7-F7）+ closure record provenance（S7-F8）
- Round 4：execution-plan §490–491 owner tests（T3 crash barrier + Repository restart consumer journey）
- S7-F2 closed @ review-8（`4d1dc010` remediation；gate evidence @ [p5-5b-s8-handoff.md](p5-5b-s8-handoff.md)）
- S8 gate：五包 static、权威 runner、三镜像 conjunction 均已 pass

```yaml
next_step: independent_acceptance_authority_for_p5_5b_slice_exit
s8_gate: pass
p5_5b_slice_exit: pass_recommended
```

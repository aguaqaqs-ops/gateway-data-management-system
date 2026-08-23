# P3→P4 Context and Code Consolidation — C0 Freeze and Inventory

状态：`complete`（`c0_continue_plan: yes`；preliminary classification only）

日期：2026-08-23

本记录冻结 cleanup baseline 与 docs/code inventory。没有修改 `vnext/**` 源码、Dockerfile、Compose、lockfile 或 candidate checkout，没有创建 git tag，没有重跑测试或重建 image。初步分类供 C1 确认，不是最终 authority。

权威计划：[P3→P4 Context and Code Consolidation Execution Plan](p3-p4-context-and-code-consolidation-execution-plan.md) §6 C0
机器可读清单：[p3-p4-context-code-consolidation-c0-inventory.json](p3-p4-context-code-consolidation-c0-inventory.json)

## Freeze identity

```yaml
branch: phase1/gate-ownership-repair
baseline_sha: 31409c8e0c37d8c12a323269ddeefebdb9927955
baseline_subject: 'docs(p3-p4-cleanup): establish cleanup entry baseline and normative refs'
freeze_head_does_not_include_c0_artifacts: true
freeze_head_sha: this_c0_freeze_head
freeze_head_resolution: git rev-parse HEAD when inventory is at HEAD
freeze_head_subject: 'docs(p3-p4-cleanup): freeze C0 inventory and proposed archive tags'
tested_candidate_sha: 13ce18b8b2d689bc7a4087e0072d485891740c0c
f3_validated_source_sha: a28d88a85793017716029638155687ca17e4b5ed
f4_validated_source_sha: a28d88a85793017716029638155687ca17e4b5ed
handoff_record_sha: b0ac984507056fb10c17c07243330b20a315c2c8
p3_exit: pass
p4_ready: yes
p4_implementation_authorized: no_until_p4_entry_acceptance
vnext_delta_vs_baseline: []
proposed_pre_cleanup_tag: docs/p3-p4-cleanup-pre-20260823
proposed_final_tag: docs/p3-p4-cleanup-final-20260823
pre_cleanup_tag_exists: false
pre_cleanup_tag_create_gate: C1
```


## Verified freeze head (C0 exit)

```text
freeze_head_sha: 78144e55f2ea94bb8c83a2e4abb190ab0362dd50
freeze_head_subject: 'docs(p3-p4-cleanup): freeze C0 inventory and proposed archive tags'
```

C0 开始时 worktree 在 baseline commit 上为 clean。本 inventory 产物在 baseline 之后生成。

## Stop conditions

| 条件 | 结果 |
| --- | --- |
| source/build/deployment delta vs baseline | no |
| 提议的 pre-cleanup tag 已存在 | no |
| 继续本计划 | **yes** |

## Coverage

- documentation/code inventory rows: **752**
- doc rows: **136**
- code rows: **531**
- code disposition candidates: **7**

## Preliminary classification counts

| 分类 | 数量 |
| --- | --- |
| `ACTIVE_INTERFACE` | 19 |
| `ARCHIVE_FROM_DEFAULT` | 22 |
| `DEFERRED` | 163 |
| `EVIDENCE_POINTER` | 2 |
| `NORMATIVE` | 37 |
| `RETAIN_IN_PLACE` | 509 |

## Code disposition candidates (§3.3, C4 decides)

| initial_disposition | 数量 |
| --- | --- |
| `FOLLOW_HARNESS_DECISION` | 1 |
| `KEEP_EVIDENCE_TOOL` | 1 |
| `KEEP_P3_REFERENCE_DELIVERABLE` | 1 |
| `KEEP_UNTIL_PROFILE_RETIRED` | 1 |
| `MOVE_CANDIDATE` | 4 |
| `MOVE_REMOVE_CANDIDATE` | 2 |
| `RETIRE_DECISION_REQUIRED` | 3 |

## C1 watchlist

1. formal/README.md still lists many P3 step/review docs; C2 shrinks default retrieval.
2. p3-active-context-index.md remains P3 default entry; C2 adds P4 index.
3. p3-grill-me-discussion-summary.md is an archive candidate.
4. P3 R1-R6 *-s0-*, *-s6-*, *-s7-*, and round execution plans are archive candidates.
5. Code candidates in code_disposition_counts require C4 consumer audit.
6. repository-probe profile binds target_gate.py; do not retire harness before C4 decision.

## Unresolved escalations

无。R7 handoff 引用已在 baseline commit 中恢复。

## C0 exit

```yaml
c0_exit: pass
baseline_sha: 31409c8e0c37d8c12a323269ddeefebdb9927955
freeze_head_sha: this_c0_freeze_head
unresolved_escalations: 0
```

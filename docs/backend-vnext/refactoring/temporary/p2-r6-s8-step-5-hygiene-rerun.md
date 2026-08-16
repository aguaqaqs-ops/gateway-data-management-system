# P2-R6-S8 Step 5 — Hygiene Rerun

状态：`pass`

日期：2026-08-17

本记录是 S8-6 P1 修复后的 old-reference 分类、dead-symbol 边界和 leak audit。
原 [p2-r6-s8-step-5-hygiene-and-candidate-preparation.md](p2-r6-s8-step-5-hygiene-and-candidate-preparation.md)
与 [p2-r6-s8-step-5-old-reference-raw/](p2-r6-s8-step-5-old-reference-raw/) 保留。
本轮原始命中：[p2-r6-s8-step-5-old-reference-raw-rerun/](p2-r6-s8-step-5-old-reference-raw-rerun/)。

分类修复 SHA：`3e4bd1fca0e52a0497bbc5a7bf69071a744fd952`

## Five old-reference searches

仓库根执行 checklist §9 五条精确命令，未加 `--hidden` / 额外 `--glob`。

| group | raw file | hits | unclassified current production/test/CI/runbook old semantic |
| --- | --- | ---: | --- |
| 1 verification level | [g1-verification-level.txt](p2-r6-s8-step-5-old-reference-raw-rerun/g1-verification-level.txt) | 60 | none |
| 2 effect-state | [g2-effect-state.txt](p2-r6-s8-step-5-old-reference-raw-rerun/g2-effect-state.txt) | 112 | none |
| 3 CAS/store | [g3-cas-store.txt](p2-r6-s8-step-5-old-reference-raw-rerun/g3-cas-store.txt) | 264 | none |
| 4 path/version | [g4-path-version.txt](p2-r6-s8-step-5-old-reference-raw-rerun/g4-path-version.txt) | 301 | none |
| 5 wire/readback | [g5-wire-readback.txt](p2-r6-s8-step-5-old-reference-raw-rerun/g5-wire-readback.txt) | 12 | none |

相对原 S8-5（27 / 53 / 126 / 143 / 5），增量全部是：

- 原 raw 文件对自身命中的拷贝（self-hit）
- S8-5 证据文档引用的 `rg` 命令与分类摘录
- `rg` 输出排序差异

没有新的 `vnext/` production 旧语义。current / negative / unrelated /
historical 口径与原 S8-5 相同。historical 文档未删。`test_snapshot_admin.py`
的 marker 改动不匹配这五组模式。

## Dead-symbol consumer search

```yaml
s8_deletions_considered: none
consumer_search_before_delete: not_applicable
r5_cleanup_06: carried_closed
s3_disposition_reopened: no
```

仅重命名测试别名 `_UNIT_*` → `_NON_DOLT_*`，不是删除 production helper。

## Leak audit

S8-4 rerun 结束后：`dolt_pids=0`，`query-*.sql=0`，`snapshot-check-dolt=0`。
keepdir `pytest-3` / `pytest-4` / `pytest-5`（及 `pytest-current` 链接）无
`query-*.sql`；记录后删除。空 `/tmp/pytest-of-root` 留下。

```text
residual_inventory gate=s8-5-hygiene-rerun
  dolt_pids=0 query_temps=0 check_temp_homes=0
  s8_owned_work_root_dirs=0
```

```yaml
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
git_diff_check: pass
broad_marker_exclusion: no
exact_docker_ignores: 3
stale_source_claim: no
missing_nodeid_count: no
undocumented_current_old_reference: no
```

## Implementation review packet (refresh)

| item | location / SHA |
| --- | --- |
| failed S8-6 | [p2-r6-s8-implementation-review.md](p2-r6-s8-implementation-review.md) `review_status: fail`；preserve |
| P1 repair | `3e4bd1fc` + [step-2 classification repair](p2-r6-s8-step-2-classification-repair.md) |
| parked-Dolt | 1448 passed, 1 skipped, 1449 collected |
| source regression | [step-4 rerun](p2-r6-s8-step-4-source-full-regression-rerun.md)；1836 service items |
| old-reference | this record + `p2-r6-s8-step-5-old-reference-raw-rerun/` |
| S8-3 worker | unchanged；not rerun |
| container | deferred；ancestor `5f474ce2` |

## Docker / Compose decision

```text
Current HEAD: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
Container rebuild required: no
Reason: test marker classification and documentation only
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S9 no-ignore ./vnext/scripts/run-tests.sh and exact candidate seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

## Exit

```yaml
old_reference_classification: pass
dead_symbol_consumer_search: pass
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
implementation_review_packet: complete
S8_exit: no
S9_ready: no
allow_s8_handoff: no
production_retest_required: yes
phase_2_complete: no
next: S8-6 independent implementation review in a new conversation
```

下一步必须**新开对话**只读审核修复后的 range（含 `3e4bd1fc` 与本证据）。
本记录不授权 S8-7 handoff。

# P2-R6-S8 Step 5 — Hygiene and Candidate Preparation

状态：`pass`

日期：2026-08-16

本记录是 S8-5 的 old-reference 分类、dead-symbol consumer 边界、leak audit 和
clean-source review packet。S8-4 全量回归之后没有源码改动，因此本步续在 S8-4
对话。没有删除 historical 文档，没有提出 S8 删除，没有重跑 W1/W2、无 ignore
全量或 Compose。

权威计划：[P2-R6-S8 Full Regression and Candidate Preparation Execution Plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md) §7
权威设计：[P2-R6-S8 Full Regression and Candidate Preparation Design](../formal/plans/p2-r6-s8-full-regression-design.md)
搜索原文：[P2 Versioned Repository Execution Checklist](../formal/plans/p2-versioned-repository-execution-checklist.md) §9
分类口径：[P2-R6 Operational Closure Execution Plan](../formal/plans/p2-r6-operational-closure-execution-plan.md) §9
S8-4：[P2-R6-S8 Step 4 — Source Full Regression](p2-r6-s8-step-4-source-full-regression.md)

原始命中保存在 [p2-r6-s8-step-5-old-reference-raw/](p2-r6-s8-step-5-old-reference-raw/)，
不把 historical 文档删空。

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
implementation_start_sha: 8e42bdd647512dfdc851b255973cf47c3f7cdd5a
s8_4_evidence_sha: 8e42bdd647512dfdc851b255973cf47c3f7cdd5a
s8_4_regression_sha: a27fe00453a910d6bdb2d0369b7923125d5d9278
s8_3_evidence_sha: a27fe00453a910d6bdb2d0369b7923125d5d9278
classification_repair_sha: 601206e4f9bd4c3d20c9b9e8b0b076127d0b4f4f
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
source_change_after_s8_4_regression: no
post_regression_delta: docs-only S8-4 evidence
production_code_changed: no
test_code_changed_in_s8_5: no
docker_or_compose_changed: no
public_contract_changed: no
capacity_rerun: no
phase_2_complete: no
```

S8-5 开始时 `git status --short` 为空。`/usr/local/bin/dolt` 可执行，
`/usr/local/bin/dolt.parked` 不存在。相对 S8-4 运行 SHA `a27fe004` 的已提交
delta 只有 S8-4 证据文件。S8 对 `vnext/` 的唯一改动仍是 S8-2 的
`tests/test_snapshot_admin.py` serial marker。

## Five old-reference searches

在仓库根执行 checklist §9 的五条精确命令。`rg` 遵守 gitignore，未加
`--hidden` / `-uu` / 额外 `--glob`。

```bash
rg -n "NONE \\| STRUCTURAL \\| FULL|completed_verification_level|SnapshotManifest" .
rg -n "PREPARED/APPLIED/VERIFIED|UNKNOWN/APPLIED|FailureDescriptor|FAILED_FINAL" .
rg -n "LAST_WRITE_WINS|CHECK_EXPECTED|table.?CAS|schema.?CAS|StoreKind|CurrentTableStore" .
rg -n "repository_path|run_dir|multipart|LATEST_AT_START|/v2/|compatibility adapter" .
rg -n "Repository wire JSON/gRPC|before_readback_verified|after_readback_verified" .
```

| group | raw file | hits | unclassified current production/test/CI/runbook old semantic |
| --- | --- | ---: | --- |
| 1 verification level | [g1-verification-level.txt](p2-r6-s8-step-5-old-reference-raw/g1-verification-level.txt) | 27 | none |
| 2 effect-state | [g2-effect-state.txt](p2-r6-s8-step-5-old-reference-raw/g2-effect-state.txt) | 53 | none |
| 3 CAS/store | [g3-cas-store.txt](p2-r6-s8-step-5-old-reference-raw/g3-cas-store.txt) | 126 | none |
| 4 path/version | [g4-path-version.txt](p2-r6-s8-step-5-old-reference-raw/g4-path-version.txt) | 143 | none |
| 5 wire/readback | [g5-wire-readback.txt](p2-r6-s8-step-5-old-reference-raw/g5-wire-readback.txt) | 5 | none |

`vnext/` production 源码没有 `StoreKind`、`FailureDescriptor`、`SnapshotManifest`、
`completed_verification_level`、`LATEST_AT_START` 命中。`/v2/` 只出现在负向测试。

### Group 1 — verification level

Current authority 使用 `FULL_SCAN`：ADR 0009、canonical-storage contract、
P2 implementation design、R4 import design。Checklist §9 命令是 self-hit。

ADR 0008 的 `NONE | STRUCTURAL | FULL`（无 `_SCAN`）以及 phase-0
`SnapshotManifest`、phase-2 decision ledger / README / consumer-adequacy 中的旧
`FULL` 术语是 superseded historical。未删除这些文档。

无 `vnext/` 代码命中。没有把旧 `FULL` 当生产 verification level。

### Group 2 — effect-state

Current formal 命中是删除/禁止旧模型：ADR 0009、repository-service contract、
external-effect contract、taxonomy、R4 design/plan、implementation-stages。
Checklist 与若干计划中的同类 `rg` 是 self-hit。

`docs/backend-vnext/operations.md` 与 `glossary.md` 的 `FAILED_FINAL` 属于其他
application capability 术语，不是 Repository Service journal。

phase-0 baseline 与 phase-2 decision ledger 中的 `FailureDescriptor` /
`PREPARED/APPLIED/VERIFIED` / `UNKNOWN/APPLIED` 是 historical。无生产代码激活
这些状态机。

### Group 3 — CAS/store

Current formal 命中均为 non-goal、reopen 或 future Current 说明：repository-service
contract §16、ADR 0009 Future CurrentTableStore、architecture plan、P2 design、
service README「public ref/table/schema CAS」。没有激活的 `StoreKind`、
table/schema CAS 或 generic store。

phase-2 decision ledger / consolidated review 中的 CurrentTableStore /
CHECK_EXPECTED / LAST_WRITE_WINS 是 superseded 设计材料，保留为历史。

### Group 4 — path/version

Production / 内部测试命中均为 private 变量、测试 helper 或明确拒绝：

- `runtime.py` 的 `repository_path`：private layout 变量，不进 public DTO
- `published_repository_path(...)`：测试 harness
- `artifacts.py` `_reject_multipart_content_type` 与 upload 测试：拒绝 multipart
- `test_http_shell.py` / `test_p2_r2_compose_integration.py`：断言无 `/v2/` route
- `target_gate.py` 与 `p2r1-target-launcher.sh` 的 `run_dir`：P2-R1 运行时私有目录

ADR 0009 / repository-service contract 把 `/v2/` 写成未来 breaking 版本策略，
并把 `LATEST_AT_START` / multipart 列为禁止项，不是现存 public path。

`operations.md`、`flows.md`、`artifacts.md`、`capabilities/repository-import.md`
与 benchmark runbook 的 `repository_path` / `run_dir` 是 backend application /
benchmark 术语。`notes/` 与 frontend compatibility adapter 命中与 Repository
Service public wire 无关。phase-2 的 `LATEST_AT_START` 设计是 historical。

### Group 5 — wire/readback

除 checklist 命令 self-hit 外，只命中 phase-0
`before_readback_verified` / `after_readback_verified`。当前 Repository wire
没有旧 JSON/gRPC 或 before/after readback 状态。

## Dead-symbol consumer search

```yaml
s8_deletions_considered: none
consumer_search_before_delete: not_applicable
r5_cleanup_06: carried_closed
s3_disposition_reopened: no
```

S8-5 只拥有 *新的* S8 删除。本步没有确认、也没有删除 dead helper / parameter /
branch。因此没有可保存的 deletion-time `rg`。S3 R5-CLEANUP-06 保持 carried
closed，不重开。

## Leak audit

S8-4 权威命令结束后、本步开始时的 host inventory。`list_host_thread_idents()`
是进程内 pytest 探针；权威命令进程已退出，host 侧按 Dolt PID、query-temp、
snapshot-check home 和 pytest work-root 审计。

审计时 keepdir：

| path | mtime | class |
| --- | --- | --- |
| `/tmp/pytest-of-root/pytest-188` | 23:28:49 | S8-4 parallel xdist keepdir（`popen-gw*`）；`query-*.sql=0`；无活 Dolt |
| `/tmp/pytest-of-root/pytest-189` | 23:32:44 | S8-4 serial keepdir；`query-*.sql=0`；无活 Dolt |
| `/tmp/pytest-of-root/pytest-190` | 23:33:13 | 空；S8-4 后 skip 确认 |
| `/tmp/pytest-of-root/pytest-current` | symlink → pytest-190 | pytest 默认 current 链接 |

keepdir 内有 `replay.sql` 等 fixture/import SQL 和已停止的 `.dolt` 目录，**没有**
`query-*.sql` worker temp。按 S8-3 口径，keep-last tmp 不是活进程残留；记录后删除
四个 S8-owned 项。空的 `/tmp/pytest-of-root` 用户目录留下，不是 session work-root。

最终：

```text
residual_inventory gate=s8-5-hygiene
  dolt_pids=0 query_temps=0 check_temp_homes=0
  s8_owned_work_root_dirs=0 host_pytest_process=0
```

```yaml
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
```

## Hygiene checks

```yaml
broad_marker_exclusion: no
exact_docker_ignores: 3
stale_source_claim: no
missing_nodeid_count: no
undocumented_current_old_reference: no
git_diff_check: pass
changed_paths_in_s8_allowed_scope: yes
```

S8 对 `vnext/` 的唯一 source 改动是 S8-2 `test_snapshot_admin.py` 模块级
`serial` marker。其余 S8 提交为 docs。没有 Dockerfile / Compose / lock /
entrypoint 改动。S8-4 记录了六段 collected/passed/skipped/failed/duration。

## Implementation review packet

供 S8-6 只读审核，不在本步做 pass/fail 判定。

| item | location / SHA |
| --- | --- |
| entry | [p2-r6-s8-step-0-entry-reconciliation.md](p2-r6-s8-step-0-entry-reconciliation.md) `1bfa1d7f` |
| design review | [p2-r6-s8-design-review.md](p2-r6-s8-design-review.md) `97f0f454`；`allow_s8_implementation: yes` |
| classification / static | [p2-r6-s8-step-2-classification-and-static.md](p2-r6-s8-step-2-classification-and-static.md)；repair `601206e4` |
| worker convergence | [p2-r6-s8-step-3-worker-convergence.md](p2-r6-s8-step-3-worker-convergence.md) `a27fe004` |
| source regression | [p2-r6-s8-step-4-source-full-regression.md](p2-r6-s8-step-4-source-full-regression.md)；run SHA `a27fe004`；`repairs: none` |
| old-reference raw + class | this record and `p2-r6-s8-step-5-old-reference-raw/` |
| dead-symbol consumers | none；no S8 deletion |
| S8 commits `1bfa1d7f..HEAD` | `77a43ebe` `97f0f454` `601206e4` `be2d1a03` `a27fe004` `8e42bdd6` plus this docs commit |
| S3/S7/S6 | carried closed；本步未重开 |
| W1/W2 / S9 / S10 | 未扩张进 S8 |

## Docker / Compose decision

```text
Current HEAD: 8e42bdd647512dfdc851b255973cf47c3f7cdd5a
Container rebuild required: no
Reason: hygiene searches, leak audit and documentation only; no Dockerfile, dependency closure, Compose, entrypoint, health/readiness, client image or container harness change
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S9 no-ignore ./vnext/scripts/run-tests.sh and exact candidate seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

S7 image 与四条 Compose PASS 仍是祖先 `5f474ce2` 证据。本证据 docs commit 是
文档后代，不改变 container identity。

## Exit

```yaml
old_reference_classification: pass
dead_symbol_consumer_search: pass
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
git_diff_check: pass
implementation_review_packet: complete
source_tree_clean_except_this_evidence: yes
container_gate_for_current_head: deferred
source_regression_with_exact_docker_ignores: pass
parked_dolt_unit: pass
five_package_static: pass
worker_convergence: pass
S8_exit: no
S9_ready: no
production_retest_required: yes
phase_2_complete: no
next: S8-6 independent implementation review in a new conversation
```

下一步必须**新开对话**做只读 S8-6。审核人检查实际 diff、命令、counts、分类和
残留，不修改 production/test/handoff 来掩盖 finding。本记录不授权 S8 exit、
S9 candidate seal 或 Phase 2 completion。

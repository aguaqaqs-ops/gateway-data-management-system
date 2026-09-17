# P5-5B-S7 Independent Review 6 — F8 Record Sealing Mechanical Verification

> **SUPERSEDED by [p5-5b-s7-independent-review-7.md](p5-5b-s7-independent-review-7.md)** — premature pass before execution-plan §490–491 owner evidence (`e5c43c0c`).

状态：**SUPERSEDED — 见 review-7**

日期：2026-09-17

Owner：Independent reviewer（read-only；本文件是唯一写入）

## 1. Decision

```yaml
stage: P5-5B-S7-f8-record-sealing-closure
review_target: e7e429c45edd1577212ae18af9e6990b5af159da          # HEAD @ review time
implementation_seal: 7c511c4b8b59842b67d24083abf274ba620b2e7e     # 可达，code/test 内容 = HEAD
records_head: b80a283f689ed6e957f932a72bc283aeacbef5be            # 可达，HEAD 祖先
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
decision: pass
findings_closed: [S7-F1, S7-F4, S7-F6, S7-F7, S7-F8]
findings_reclassified: [S7-F2]
findings_open: []
s7_closure: pass
s8_entry: eligible
s8_entry_preconditions: §4 required record actions（acceptance 收口更新 + clean status + S8 provenance pin）
observations_non_blocking: [S7-O1, S7-O2, S7-O3, S7-O4]
p5_5b_slice_exit: not_declared
```

复核范围：纯文档 closeout（`afdfb30b` / `b80a283f` / `e7e429c4`），无代码/测试改动；因此本轮的
mechanical 检查 + 对 seal 内容一致性的再确认即为充分证据（比例化保障）。

## 2. Mechanical verification

| # | 检查项 | 结果 |
| --- | --- | --- |
| 1 | `remediation_round_3` / `implementation_seal` = 可达 revision | **pass** — `7c511c4b`：`git cat-file -t` = commit，`--is-ancestor HEAD` = yes |
| 2 | `records_head` = 可达 revision | **pass** — `b80a283f`：HEAD 祖先 |
| 3 | 代码/测试相对 seal 无漂移 | **pass** — `git diff --stat 7c511c4b..HEAD -- vnext/` 为空（seal 后的提交全部只动 docs） |
| 4 | 不可解析 amend 孤本不再被当作 pin | **pass** — `5de2e0b7`/`b60402dc` 仅出现在“孤本已废弃”注记（acceptance:38、handoff:30）与 review-5 的缺陷描述中，无 pin 引用 |
| 5 | 计数与当轮实测一致 | **pass** — handoff retest 注记：`2 passed, 9 deselected` / `7 passed, 28 deselected` / `1 passed, 15 deselected` / `319 passed` / `26 passed, 9 deselected`，全部与 §3 实测一致 |
| 6 | touched paths 按 finding 分列 | **pass** — handoff round-3 表 + prior-round 表与实际 diff 一致 |
| 7 | review-5 记录未被改写 | **pass** — `afdfb30b` 仅新增 181 行，`decision: changes_required` / `findings_open: [S7-F8]` 原样保留 |
| 8 | review-3 保持 SUPERSEDED、S6 引用正确 | **pass** |
| 9 | closeout 提交仅文档 | **pass** — `afdfb30b`（review-5）、`b80a283f`（acceptance+handoff）、`e7e429c4`（2 行 `records_head`）均无 `vnext/**` 改动 |
| 10 | `git diff --check` | **pass**（clean） |
| 11 | `git status --short` 干净 | **未满足（1 行）** — 见 §4：`M p5-5b-s7-acceptance.md`（lineage 表 `S7 F8 closeout \| pending` → `b80a283f` 的 1 行修正未提交） |

## 3. Gates re-run @ HEAD `e7e429c4`

| Gate | 命令 | 结果 |
| --- | --- | --- |
| WorkerRuntime serial | `… -m 'integration and serial' tests/test_submit_recovery.py -k 'worker_runtime and (finalize or stable_abort)'` | **2 passed, 9 deselected** |
| abort unit | `… -m unit tests/test_submit_transactions.py -k abort` | **7 passed, 28 deselected** |
| accumulated unit（§4 22 unit files） | `… -m unit <22 files>` | **319 passed** |
| backend ruff / mypy | `… run ruff check .` / `… run mypy` | **All checks passed / 377 source files OK** |

S7-F7 的判别力与探针证据见 review-5 §2.3/§2.4（seal 内容与 HEAD 一致，结论继续成立）。

## 4. Required record actions before S8（交付方，S7 allowed paths）

1. 将工作区未提交的 1 行修正（acceptance lineage `S7 F8 closeout` → `b80a283f`）**提交**；提交后
   `git status --short` 必须为空、`git diff --check` 通过。
2. 更新 `p5-5b-s7-acceptance.md` 为 S7 收口态（字段值必须与下一致）：

```yaml
decision: pass
findings_closed: [S7-F1, S7-F4, S7-F6, S7-F7, S7-F8]
findings_reclassified: [S7-F2]          # 保持 reclassified_deferred_to_s8，不得记 closed
# 移除 findings_remediated_pending_review / findings_open
s7_independent_review: pass (p5-5b-s7-independent-review-6.md)
s8_entry: eligible
five_package_static: deferred
authoritative_runner: deferred
container_conjunction_gate: deferred
p5_5b_slice_exit: not_declared
```

3. 将本文件（`p5-5b-s7-independent-review-6.md`）原样提交；lineage 增加 review-6 + closure 行。
4. `records_head` 必须指向可达 revision（不得再指向 amend 孤本）；任何 pin 的 SHA 必须能从分支解析。
5. S8 handoff 必须 pin S7 acceptance 收口 revision 与 `implementation_seal: 7c511c4b`，并按 plan §6.3/§6.4
   跑无 ignore 权威 runner + 五包 static + 三镜像 container journey；S7-F2 在 §6.4 通过前不得记 closed。

若 §2 的字段值与 (2) 不一致，交付方不得自行判定收口，应回到本 reviewer。

## 5. Residual observations（不阻塞）

- **S7-O1 / S7-O2（carry）**：PRE_REQUEST cross-owner acceptable；Repository restart submit journey 仍为
  reopen candidate（worker poll-only 设计不变）。
- **S7-O3（carry）**：`FinalizeSubmitTransactionRequest.defer_operation_terminal` 默认分支在生产无 caller
  （仅 unit 覆盖）；后续无关 remediation 不得顺带重构。
- **S7-O4（carry）**：`abort_submit_in_control_transaction` 未进入 `application/submission/__init__.py`
  的 `__all__`；当前调用方均在包内，可接受。

## 6. Boundary confirmations

- 本 review 未改代码/既有文档；唯一写入为本文件。
- S7 未声明 `p5_5b_slice_exit`；本记录不授权 5C、production release 或任何新 Repository effect。
- review-2/review-3 的错误 closure 与 review-4/review-5 的 findings 均保留原文 + superseded 标记，
  可追溯。

## 7. Next step

```yaml
next_step: P5-5B-S8 final current-HEAD gate and slice handoff
s7_findings_all_closed: true
s8_entry: eligible_after_required_record_actions
```

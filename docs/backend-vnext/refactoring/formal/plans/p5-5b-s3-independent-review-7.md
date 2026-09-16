# P5-5B-S3 Independent Review 7 — Traceability Confirmation

日期：2026-09-16

结论：**implementation pass / documentation changes required**。`01e888fc` 关闭了 J3 的 SHA、
focused command 和 static evidence 子项，但主 handoff 仍有最终树可直接证伪的旧声明，S3 暂不签署
stage pass。

评审对象：code candidate `d093caf919d36631e99e832b7227fe5a4ec5ac9f`；docs correction
`01e888fc85a2bed9f563b7bc8cd7945b3b4bc57c`。评审开始时工作区 clean。Reviewer 仅新增本文，
未重跑已在 Review 6 通过的代码测试。

## Confirmed closure

- `01e888fc` 仅修改/新增 4 份 S3 docs，没有 production、tests、lockfile 或 dependency 变更。
- 主 handoff 与 round-2 handoff 均绑定完整 code candidate SHA `d093caf9…`；round-1/round-2
  remediation 分别绑定 `33c14a92` / `2881e747`。
- Focused 命令现列出完整 10 files；此前独立执行的对应结果为 131 passed。
- Backend full unit 1916 passed、五包 static 的 Review 6 provenance 已准确记录。
- Round-1 handoff 已明确标为 superseded，并指向权威 round-2 handoff。
- 四份修改文档的 local links/fences、`git diff --check` 均通过。

## Finding

### S3-J4 / P2 process — 主 handoff 仍混用 baseline 与 final invariants/path claims

Exact doc：`docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-handoff.md`。

1. `remediation_changed_paths_33c14a92_to_d093caf9` 只覆盖 round-2/3 区间，没有任何字段记录
   `8618b21a..33c14a92` 的 round-1 changed paths。实际该遗漏区间包含：
   - `capabilities/storage_projection/project.py`；
   - `tests/test_submit_artifact_protection.py`；
   - round-1 capability/publication changes 和 remediation handoff。
   因此当前“baseline vs remediation changed paths”并未覆盖 baseline 到 final candidate 的完整差异。

2. `Explicit non-deliverables` 仍声明 `No capabilities/** ... changes`，但最终 remediation 明确修改
   `storage_projection/**`、`mutation_planning/**` 并新增 public APIs。该句只有在标为 historical
   baseline claim 时才成立。

3. `invariants_delivered` 仍声明 S3 提供 preview→attempt transfer 和 terminal promote/clear helpers；
   Pin transfer/release evidence matrix 仍列四个当前不存在的测试。R7 已明确删除这些与 S2 重复的
   helpers，当前 `test_submit_artifact_protection.py` 只有
   `test_pin_prepare_import_artifacts_extends_attempt_protection`。最终 handoff 应说明 transfer/terminal
   行为由 S2 既有 transaction owner 负责，S3 只交付 prepare manifest/package pin helper，S5 wiring
   仍 deferred。

Business consequence：handoff 的 SHA 与数字虽已正确，但 scope/invariant/test-owner 仍不能从最终树
复核；reviewer 会被引导去查不存在的 tests，并得到与 final diff 相反的 capability 结论。

Required closure（docs-only）：

- 用一个完整 `8618b21a..d093caf9` remediation path list，或分别增加
  `8618b21a..33c14a92` 与 `33c14a92..d093caf9` 两段且确保并集完整；
- 将 baseline non-deliverables 明确标为 historical，并增加 final remediation scope/authority 说明；
- 删除已移除的 helper/test claims，以当前唯一 S3 protection owner test 重写 invariant/evidence；
- 保持已正确的 SHA、10-file command、131/1916 和 five-package provenance 不变。

Allowed paths：`p5-5b-s3-handoff.md`，必要时同步 round-2 handoff；不得改 production/tests。
修正后只需 local links/fences、`git diff --check` 与 clean committed traceability，无需重跑测试。

## Decision record

```yaml
stage: P5-5B-S3-independent-review-7
code_candidate: d093caf919d36631e99e832b7227fe5a4ec5ac9f
docs_candidate: 01e888fc85a2bed9f563b7bc8cd7945b3b4bc57c
implementation_verdict: pass
overall_verdict: changes_required
open_findings: [S3-J4]
closed_findings: [S3-J1, S3-J2, S3-J3-partial]
tests_rerun: false
test_reason: docs-only correction; Review 6 exact candidate evidence retained
authoritative_runner: not_run
container_gate_for_current_head: not_claimed
next_step: docs-only final-handoff scope/invariant correction, then traceability-only confirmation
```

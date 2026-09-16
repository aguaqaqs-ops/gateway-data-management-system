# P5-5B-S3 Independent Review 6

日期：2026-09-16

结论：**implementation pass / documentation changes required**。J1/J2 已关闭，未发现新的代码
finding；S3 在 handoff 绑定当前候选并修正验证记录前暂不签署最终 pass。

评审对象：`d093caf919d36631e99e832b7227fe5a4ec5ac9f`，父整改提交
`2881e747`。评审开始时工作区 clean。Reviewer 仅新增本文。

## J1/J2 closure

| Finding | Result | Evidence |
| --- | --- | --- |
| S3-J1 repository base identity | closed | Consumer 将 `DigestRef(build_input.repository_base_digest)` 传给 public `render_import_mutation_dml`；owner 用它构造 `MutationRepositoryBase`，source identity 仍来自 manifest。捕获 planner request 的负分离测试通过。 |
| S3-J2 public capability boundary | closed | Consumer 只从 `mutation_planning` public package 导入 DML composition；无 `mutation_planning._*` 或 `storage_projection._*` import。Owner test 只调用 public API；architecture allowlist 未改且 tests 通过。 |

Renderer 的 target-neutral public composition 位于 Mutation Planning owner；具体 renderer 实现改名为
owner 内部 `_repository_replay_renderer.py`。仓库内不存在 `_dolt_renderer` 残留 import。Manifest
semantic reuse 使用 public `open_canonicalization_manifest` 返回且已验证的 `manifest_digest`，没有再次
跨入 Storage Projection 私有 digest 模块。

## Finding

### S3-J3 / P2 process — Handoff 未绑定已提交候选，验证命令与结果不一致

- Authority：Execution plan §7 要求每阶段 handoff 记录 exact candidate/changed paths/commands/results；
  同节规定 independent review 先核 authority 与 changed paths。
- Exact docs：`p5-5b-s3-handoff.md`、`p5-5b-s3-remediation-round2-handoff.md`。
- 当前不一致：
  1. 主 handoff 仍写 `candidate_head: pending remediation commit`，并保留 baseline 的 37 tests、
     337 mypy files、旧 `_dolt_renderer` notes 和不完整 changed paths。
  2. Round-2 handoff 仍写 `remediation_commit: pending`，尽管 `2881e747` 与 `d093caf9` 均已提交。
  3. Round-2 记录的 focused 命令仅列 8 个文件，独立执行结果是 **95 passed**；记录却写
     **131 passed** 并声称包含 integrity/renderer。补列
     `tests/test_storage_projection_integrity.py` 与 `tests/test_dolt_renderer.py` 后才是
     **131 passed**。
  4. `five_package_static` 仍写 `backend-only`。本次独立复审已补跑五包并全部通过，可据此如实
     更新为 independent-review evidence，或由 delivery 自行重跑并记录。
- Business consequence：review 无法从交付 handoff 将最终实现、changed paths 和 exact evidence
  唯一绑定到 `d093caf9`；当前文档同时描述 baseline、round-2 未提交树和最终提交。
- Required closure：把最终 candidate/remediation SHA 写为完整 SHA；补全最终 changed paths；修正
  focused 命令或结果；将旧 baseline evidence 明确标为 historical；更新 Notes/public surface 和
  five-package evidence provenance。仅需 docs 修改，不需重跑已通过的代码测试。
- Allowed paths：两份 S3 handoff docs；必要时 remediation handoff docs。不得借此改 production/tests。
- Closure check：Markdown links/fences、`git diff --check`、clean committed candidate traceability。

## Verification

```bash
# Handoff 原样列出的 8-file selection
./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit \
  tests/test_architecture.py tests/test_submit_import_builder.py \
  tests/test_mutation_planning_import_replay.py tests/test_storage_projection_import_replay.py \
  tests/test_submit_artifact_protection.py tests/test_repository_import_artifact_package.py \
  tests/test_artifact_boundary.py tests/test_canonical_lock_identity.py
# 95 passed in 1.92s

# 实际 131-test battery（在上面增加以下两个 owner files）
# tests/test_storage_projection_integrity.py tests/test_dolt_renderer.py
# 131 passed in 2.01s

./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit
# 1916 passed, 115 deselected, 1 warning in 68.92s
```

五包均通过受控 `ruff check .` 与 `mypy`：Backend 341、Shared Kernel 34、Repository Contracts 15、
Repository Client 26、Repository Service 198 source files。Canonical lock 无 diff；
`git diff 33c14a92..d093caf9 --check` 通过。

未跑 integration、authoritative runner 或 Docker；S3 当前改动是 Python/tests/docs，未触碰 lock、
image 或 deployment boundary。本 review 不宣称容器门禁。

```yaml
stage: P5-5B-S3-independent-review-6
candidate_head: d093caf919d36631e99e832b7227fe5a4ec5ac9f
parent_remediation: 2881e747
implementation_verdict: pass
overall_verdict: changes_required
open_findings: [S3-J3]
closed_findings: [S3-J1, S3-J2]
focused_unit: pass_131
backend_unit: pass_1916
five_package_static: pass_independent_review
architecture: pass
canonical_lock_identity: pass
authoritative_runner: not_run
container_gate_for_current_head: not_claimed
next_step: docs-only handoff correction, then light traceability confirmation
```

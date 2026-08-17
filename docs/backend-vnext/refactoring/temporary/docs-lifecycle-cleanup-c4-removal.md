# Documentation Lifecycle Cleanup — C4 Removal

状态：`complete`（默认树已去掉 archive 检索噪声；final tag 仍待 C6）

日期：2026-08-17

本记录不是 `validated_code_sha`、`CANDIDATE_SHA` 或 image revision。未修改
`vnext/**`，未改变 contract/ADR 公开语义，未 amend/rebase/复用 tag。

权威计划：[Documentation Lifecycle Cleanup Execution Plan](all-documentation-lifecycle-cleanup-execution-plan.md) §5 C4
Manifest：[P2–P3 Cleanup Manifest](../formal/plans/p2-p3-cleanup-manifest.yaml)
P3 入口：[P3 Active Context Index](../formal/plans/p3-active-context-index.md)
P2 接口：[P2 External Interface Handoff](../formal/plans/p2-external-interface-handoff.md)
归档介质：Git annotated tag `docs/p2-p3-cleanup-pre-20260817`

```yaml
c4_status: complete
c4_continue_plan: yes
pre_cleanup_tag: docs/p2-p3-cleanup-pre-20260817
deleted_from_default_tree: 236
c1_archive_deleted: 220
c1_archive_kept_until_c6: 4
c0_unclassified_evidence_deleted: 16
copied_into_docs_archive_dir: no
vnext_changed: no
public_semantics_changed: no
amend_or_rebase: no
final_cleanup_tag_created: no
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
```

## 删除范围

C1 `archive` 共 224 条。本阶段从默认树删除 220 条；下列 4 条留到 C6。C5 另将 C0
未分类的 16 个 raw `.jsonl`/`.log` 证据登记到 manifest，因此 manifest archive 总数为 240：

- `docs/backend-vnext/refactoring/temporary/README.md`
- `docs/backend-vnext/refactoring/temporary/all-documentation-lifecycle-cleanup-execution-plan.md`
- `docs/backend-vnext/refactoring/temporary/docs-lifecycle-cleanup-c0-inventory.md`
- `docs/backend-vnext/refactoring/temporary/docs-lifecycle-cleanup-c0-inventory.json`

C0 只枚举 Markdown/README/YAML/JSON，因此另有 16 个已跟踪证据文件不在 C1 表内，
但属于同一批过程噪声，已一并移出默认树（均可从 pre-cleanup tag 恢复）：

- 3 个 `p2-r6-s9-step-3-run-tests*.log`
- 13 个 P2-R1 diagnostics/v8/smoke `.jsonl`

未把任何历史文件复制进另一套 `docs/` archive 目录。

## 必须保留且仍在默认树

- `retain_active` / `retain_oracle` / `retain_in_place` / `leave_in_vnext`
- `must_retain_source_pointer` 三件：
  - `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md`
    （pytest methodology 字符串未改）
  - `docs/backend-vnext/refactoring/formal/plans/p2-r5-commit-pinned-read-execution-plan.md`
  - `docs/backend-vnext/refactoring/temporary/p2-r9-s2-step-e-container-gate.md`
- C1/C3 过程记录（C6 前）

## 存活链接改写

存活 formal/oracle 文档不再把已删除路径当作可点击依赖。需要历史证据时改为：

- [P2 External Interface Handoff](../formal/plans/p2-external-interface-handoff.md)
- [cleanup manifest](../formal/plans/p2-p3-cleanup-manifest.yaml)
- tag `docs/p2-p3-cleanup-pre-20260817` + 原路径

恢复示例：

```bash
git checkout docs/p2-p3-cleanup-pre-20260817 -- \
  docs/backend-vnext/refactoring/temporary/p2-r6-s11-final-handoff.md
```

工作区删除尚未提交。C5 做链接与 allowlist 核验；cleanup commit 与
`docs/p2-p3-cleanup-final-20260817` 在 C6。

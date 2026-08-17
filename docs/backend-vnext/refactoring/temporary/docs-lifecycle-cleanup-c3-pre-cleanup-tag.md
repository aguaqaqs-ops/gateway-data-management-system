# Documentation Lifecycle Cleanup — C3 Pre-cleanup Tag

状态：`complete`（`pre_cleanup_tag_created: yes`；final tag 仍待 C4）

日期：2026-08-17

本记录在不可变 tag 创建之后登记字面量 SHA。它不是 `validated_code_sha`、
`CANDIDATE_SHA` 或 image revision。被 tag 的提交自身仍使用占位符
`this_pre_cleanup_commit`，不自引用。未 amend、rebase 或复用已存在 tag。

权威计划：[Documentation Lifecycle Cleanup Execution Plan](all-documentation-lifecycle-cleanup-execution-plan.md) §5 C3
Manifest：[P2–P3 Cleanup Manifest](../formal/plans/p2-p3-cleanup-manifest.yaml)
P2 handoff：[P2 External Interface Handoff](../formal/plans/p2-external-interface-handoff.md)

```yaml
c3_status: complete
c3_continue_plan: yes
pre_cleanup_tag: docs/p2-p3-cleanup-pre-20260817
pre_cleanup_tag_object: 93e7a492d81ae9272aaf5835277cf1a30cc3c2bd
pre_cleanup_commit: 7f2e2ddfd5567775bcc39c3a2e15801897feb845
tag_type: annotated
final_cleanup_tag: docs/p2-p3-cleanup-final-20260817
final_cleanup_tag_created: no
cleanup_commit: null
retain_owner: Backend vNext Architecture
archive_medium: git_annotated_tag_and_history
archive_paths_in_tag: 224
archive_paths_missing_in_tag: 0
public_semantics_changed: no
vnext_changed: no
amend_or_rebase: no
reuse_existing_tag: no
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
```

恢复示例：

```bash
git checkout docs/p2-p3-cleanup-pre-20260817 -- \
  docs/backend-vnext/refactoring/temporary/p2-r6-s11-final-handoff.md
```

C4 才删除默认检索树中的 archive 路径。本记录随后的 docs-only 提交不是 image input。

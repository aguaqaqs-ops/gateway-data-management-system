# Documentation Lifecycle Cleanup — C3 Pre-cleanup Tag

状态：`tagging`（`pre_cleanup_tag_sha: this_pre_cleanup_commit`）

日期：2026-08-17

本记录与 pre-cleanup 提交一起进入被 tag 的树。按仓库自引用约定，本提交不写入
自己的最终 SHA。字面量 tag/commit SHA 在 tag 创建后的外部记录中登记。

权威计划：[Documentation Lifecycle Cleanup Execution Plan](all-documentation-lifecycle-cleanup-execution-plan.md) §5 C3
Manifest：[P2–P3 Cleanup Manifest](../formal/plans/p2-p3-cleanup-manifest.yaml)

```yaml
c3_status: tagging
pre_cleanup_tag: docs/p2-p3-cleanup-pre-20260817
pre_cleanup_tag_sha: this_pre_cleanup_commit
final_cleanup_tag: docs/p2-p3-cleanup-final-20260817
final_cleanup_tag_created: no
cleanup_commit: null
retain_owner: Backend vNext Architecture
archive_medium: git_annotated_tag_and_history
public_semantics_changed: no
vnext_changed: no
amend_or_rebase: no
reuse_existing_tag: no
```

本 tag 覆盖 C0 inventory、C1 classification、C2 P3 index / P2 handoff / manifest
以及索引改链。它不是 `validated_code_sha`、`CANDIDATE_SHA` 或 image revision。
C4 删除前可用 `git checkout docs/p2-p3-cleanup-pre-20260817 -- <path>` 恢复
manifest 中的 `archive` 路径。

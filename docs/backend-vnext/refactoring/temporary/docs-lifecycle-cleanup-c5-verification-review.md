# Documentation Lifecycle Cleanup — C5 Verification and Independent Review

状态：`pass`（C5 findings repaired；C6 final cleanup handoff authorized）

日期：2026-08-17

审核范围：C4 staged removal worktree、pre-cleanup tag、C0/C1/C3/C4 records、P3 active
context、P2 external interface handoff 和 cleanup manifest。

权威计划：[Documentation Lifecycle and Active-Context Cleanup Execution Plan](all-documentation-lifecycle-cleanup-execution-plan.md) §5 C5
C4 记录：[docs-lifecycle-cleanup-c4-removal.md](docs-lifecycle-cleanup-c4-removal.md)
Manifest：[P2–P3 Cleanup Manifest](../formal/plans/p2-p3-cleanup-manifest.yaml)
Pre-cleanup tag：`docs/p2-p3-cleanup-pre-20260817`

## 1. Review identity

```yaml
review_head: 9088ed9c
pre_cleanup_tag: docs/p2-p3-cleanup-pre-20260817
pre_cleanup_commit: 7f2e2ddfd5567775bcc39c3a2e15801897feb845
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_or_image_changed: no
cleanup_commit: not_created
final_cleanup_tag: not_created
repair_reviewed_at: 2026-08-17
manifest_archive_entries: 240
manifest_hashed_entries: 320
```

C4 删除仍未提交；当前 worktree 同时包含 236 个 staged 删除和 active-document
修改。该审核不提交、恢复或修复 C4 内容。

## 2. Checks that passed

```yaml
manifest_yaml_parse: pass
manifest_hash_and_size_crosscheck: pass
pre_cleanup_tag_exists_and_is_annotated: pass
deleted_paths: 236
deleted_paths_present_in_pre_cleanup_tag: 236
deleted_paths_missing_from_pre_cleanup_tag: 0
deleted_evidence_manifest_entries: 16
git_diff_check_staged: pass
git_diff_check_unstaged: pass
source_build_deployment_delta: no
vnext_delta: empty
scoped_markdown_links: pass
pytest_dolt_compose_rerun: not_run_by_plan
```

Manifest parsing used an ephemeral PyYAML tool environment; no project dependency or lockfile
was changed. Archive restoration was checked with `git cat-file` against the annotated tag.

## 3. Findings and repairs

### F-C5-001 — Manifest hashes do not match the pre-cleanup tag

严重性：**blocker；已修复并复核通过**

Initial C5 computed 304 hashed path entries. Recomputing each entry from the exact
`docs/p2-p3-cleanup-pre-20260817` tree found three mismatches:

| Path | Manifest SHA | SHA in pre-cleanup tag |
| --- | --- | --- |
| `docs/backend-vnext/refactoring/formal/plans/p2-external-interface-handoff.md` | `ba08791eee390ad3e314fd024a361ae24db9ec645ab194da997cd2f92d5435d3` | `6cfbd2c2c62b6a341d428db657b3670d374923c86882cf42fbb99b2b968cc313` |
| `docs/backend-vnext/refactoring/temporary/README.md` | `f977f2349d265e53e65812db02cbc1308170e614d01f12e8f8acdd0596ca0b17` | `9a5549fa1c9bde4e53eb58c755a37f5704a42c03a4f797492b28c802540ba735` |
| `docs/backend-vnext/refactoring/temporary/all-documentation-lifecycle-cleanup-execution-plan.md` | `0ee7c0947249aaec39398dd2dfe565c2acf2adaa646b7cfbab2f374ed3683989` | `7bce009c1b0bceb1f22e7090968974b4f6ddf7521424e89a3f58d51d782a75dd` |

修复：三项 SHA 和字节数已按不可变 pre-cleanup tag 重新计算并写回 manifest。复核 320
个带 SHA 的条目，hash 与 size 全部和 tag 内容一致；tag 对象和提交未修改、未替换。

### F-C5-002 — Sixteen deleted evidence files have no per-path manifest entries

严重性：**blocker；已修复并复核通过**

C4 records `c0_unclassified_evidence_deleted: 16` for 13 `.jsonl` files and 3 S9 test logs.
In the initial C5 review those files were recoverable from the tag but absent from the manifest
`paths.archive` table, with only the aggregate count recorded.

修复：16 个文件已逐项加入 `paths.archive`，每项都有 `class`、`role`、pre-tag `sha256`
和字节数。manifest archive 总数由 224 校正为 240；236 个实际删除路径仍全部可从 tag
恢复。

### F-C5-003 — Three current cleanup records contain broken Markdown links

严重性：**high；已修复并复核通过**

修复：C0/C1 的上游链接改为 retained P2 External Interface Handoff，C0 的 ADR 0012
链接改为正确的 `../formal/adr/` 相对路径。对 `docs/backend-vnext/**/*.md` 的 362 个
本地 Markdown 链接复核结果为 `broken_links: 0`；方法文本中的 `[text](url)` 仍按语法
示例排除，不计为链接。

### F-C5-004 — Package README retains stale P2 status (advisory before C6)

严重性：**medium；已决策并接受**

`vnext/repository_service/README.md:3-7` 仍是 P2-R5 的历史状态，包含
`production_retest_required=yes` 和 `phase_2_complete=no`。本轮不修改该 package README：
它保留了测试/consumer 需要的 source pointer，且 P3 index 已将其状态行明确列入默认排除，
P2 External Interface Handoff 是完成状态 authority。C6 final handoff 必须保留这一永久
排除声明，直接阅读该 README 时不得将其解释为 Phase 2 completion authority。

## 4. C5 verdict

```yaml
finding_count: 4
blocker_count: 0
high_count: 0
medium_count: 0
manifest_hash_and_size_crosscheck: pass
deleted_path_recovery: pass
markdown_links: pass
source_boundary: pass
review_status: pass
allow_c6: yes
next: C6 final cleanup commit, immutable final tag, and final handoff review
```

No pytest, Dolt, W1/W2, v8 formal or container gate was rerun because the reviewed changes are
documentation-only and C5 explicitly excludes those gates. Any source/build/deployment change
while repairing these findings exits the cleanup plan and requires a new candidate/gate.

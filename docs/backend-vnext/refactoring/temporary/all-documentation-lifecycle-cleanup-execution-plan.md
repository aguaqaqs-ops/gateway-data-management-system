# Documentation Lifecycle and Active-Context Cleanup Execution Plan

状态：C5 pass / C6 authorized

日期：2026-08-17

Owner：Backend vNext Architecture（authority、阶段边界和最终 handoff）

适用范围：仓库现有设计、执行、接口、运维和交付文档；重点覆盖
`docs/**`、root/package README 和与文档直接关联的索引文件。

本文只规定文档分类、归档、删除、检索边界和验收顺序，不建立新的业务 contract、容器
wire 语义或实现方案。正式语义仍由现有 contracts、ADR、architecture 和 implementation
stages 拥有。完成后本文应删除，Git history 和最终 cleanup manifest 作为执行记录。

## 1. Objective

在 P3 完整设计开始前，把仓库从“所有历史过程材料都处于默认检索路径”整理为：

1. 小而明确的 active context，供 P3 设计和后续实现默认读取；
2. 一套不重复定义语义的 normative interface/operations 文档；
3. 可由不可变 Git tag、Git history、manifest 和外部 audit root 恢复的 P0-P2 历史证据；
4. 无悬空链接、无相互矛盾状态、无把失败尝试误当成当前规则的检索边界。

清理不等于重写历史，也不等于删除仍被 P3 消费的接口、限制、错误语义、恢复边界或
reopen condition。

## 2. Assumptions and non-goals

### 2.1 Assumptions

- Git history 和一个不可变 cleanup tag 被接受为过程文档的主要归档介质。
- 外部 audit root 中的 raw logs、packages、tokens 和完整证据不拷回当前文档树。
- P3 默认把 Repository Service 当作独立容器服务，通过 `gateway-repository-client`
  和正式 Repository Service Contract 调用。
- P2/P1 已完成结论不因本轮文档清理重新验证；任何语义变化必须另开 owning contract/ADR
  变更，而不是借清理提交顺手修改。

### 2.2 Non-goals

- 不修改 `vnext/**` production code、tests、Dockerfile、Compose、entrypoint、lockfile、
  image input 或 candidate checkout。
- 不删除正式 contract、ADR、容量/安全/部署约束，除非先明确新的 semantic owner 和
  replacement。
- 不用“文档已归档”替代仍需执行的测试、container gate 或 release gate。
- 不把 archive 目录复制成另一套可被误读为 authority 的规范。

## 3. Authority model

清理前每个文档必须归入且只能归入一个主分类：

| 分类 | 含义 | 默认动作 |
| --- | --- | --- |
| `NORMATIVE` | 仍定义 contract、ADR、架构边界、阶段出口或部署约束 | 保留，列入 active index |
| `ACTIVE_INTERFACE` | P3/后续实现直接需要的 API、client、运行、容量和兼容性说明 | 保留或压缩为单一入口 |
| `EVIDENCE` | 已完成 gate、provenance、测试包、hash 和审计记录 | 归档；只保留最终索引和摘要 |
| `HISTORICAL` | 讨论、被否决方案、重复 review、失败/替代 attempt | 从默认树移除，Git history/tag 保留 |
| `REDUNDANT` | 与 authority 重复、过期状态、生成物或无 consumer 文档 | 删除前确认无引用 |
| `ESCALATE` | authority 不明、存在外部 consumer、未决问题或保留义务不明 | 停止处理并登记 owner/决策 |

`temporary/` 不拥有正式语义。已完成的临时执行记录不应继续作为 P3 默认上下文；
formal 文档也不得复制一整套历史过程来替代归档。

## 4. Active P3 context target

清理完成后，P3 默认入口只允许从以下类型的文档开始：

- P3 context index 和当前 P3 design plan；
- `Repository Service Contract` 及其直接引用的 canonical storage、effect/recovery、
  shared encoding contract；
- Repository Client API/README 和 executable contract/e2e test entry points；
- Service 的健康、认证、部署、容量、版本兼容和错误映射说明；
- 一个精简的 P2 external interface handoff，记录 sealed candidate/image、支持面、
  限制、non-goals、reopen triggers 和 archive manifest 引用。

接口摘要只能链接到 normative owner，不得重新复制字段表、状态机或错误矩阵。若 generated
OpenAPI 是激活 wire authority，应固定其生成来源和版本/hash，不能手写第二份 schema。

## 5. Staged execution

### C0 - Freeze and inventory（read-only）

记录当前 branch/HEAD/worktree、candidate/image identity 和不可变 pre-cleanup tag。
使用 `git ls-files` 枚举 Markdown、README、RST、文档 YAML/JSON 及文档索引；记录路径、
大小、最近提交、incoming links、outgoing links、状态字段和初步分类。

任何 source/build/deployment delta 都停止本计划并回到 owning stage。

C0 产物（2026-08-17）：

- [C0 freeze and inventory](docs-lifecycle-cleanup-c0-inventory.md)
- [C0 machine-readable inventory](docs-lifecycle-cleanup-c0-inventory.json)

```yaml
c0_status: complete
c0_continue_plan: yes
freeze_head: 1420eaddaffb506d6c209862b9daeb510b7fc230
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
proposed_pre_cleanup_tag: docs/p2-p3-cleanup-pre-20260817
pre_cleanup_tag_created: no
inventory_rows: 300
```

### C1 - Authority and consumer classification

逐项确认：

1. 是否存在正式 owner；
2. 是否被 active 文档、代码、测试、CI、runbook 或外部链接引用；
3. 是否包含仍需保留的限制、reopen condition、失败尝试或审计 hash；
4. 是否与当前 P2 final handoff、formal README 和 package README 状态一致。

重点检查 README 中残留的旧 P2 状态、formal 文档指向 temporary execution records 的链接，
以及仍未 formalize 的 decision ledger 条款。

C1 产物（2026-08-17）：

- [C1 authority and consumer classification](docs-lifecycle-cleanup-c1-classification.md)
- [C1 machine-readable classification](docs-lifecycle-cleanup-c1-classification.json)

```yaml
c1_status: complete
c1_continue_plan: yes
unresolved_escalations: 0
confirmed_normative: 26
confirmed_active_interface: 43
confirmed_evidence: 63
confirmed_historical: 169
c4_must_retain_source_pointers: 3
```

### C2 - Active context and handoff assembly

生成 P3 active context index、P2 interface handoff 和 machine-readable cleanup manifest。
必要时补充 Repository Client README；只抽取稳定接口和运行边界，不在摘要中重述过程证据。

任何需要改变 public semantics 的发现都登记为 `ESCALATE`，不得在 C2 直接修订。

C2 产物（2026-08-17）：

- [P3 Active Context Index](../formal/plans/p3-active-context-index.md)
- [P2 External Interface Handoff](../formal/plans/p2-external-interface-handoff.md)
- [P2–P3 Cleanup Manifest](../formal/plans/p2-p3-cleanup-manifest.yaml)

```yaml
c2_status: complete
c2_continue_plan: yes
unresolved_escalations: 0
public_semantics_changed: no
p3_design_plan: absent_not_invented
client_readme_in_vnext: not_created
```

### C3 - Archive and immutable tagging

在删除或移动前创建不可变 tag，例如：

```text
docs/p2-p3-cleanup-pre-20260817
```

最终 cleanup commit 再创建一个不可变 tag，例如：

```text
docs/p2-p3-cleanup-final-20260817
```

manifest 必须记录两个 tag、cleanup commit、被归档路径集合、每个归档文件的 hash、
外部 audit root 和保留责任人。不得 amend、rebase 或复用已存在 tag。

C3 产物（2026-08-17）：

- 不可变 annotated tag：`docs/p2-p3-cleanup-pre-20260817`
- [C3 pre-cleanup tag record](docs-lifecycle-cleanup-c3-pre-cleanup-tag.md)

```yaml
c3_status: complete
pre_cleanup_tag: docs/p2-p3-cleanup-pre-20260817
pre_cleanup_tag_object: 93e7a492d81ae9272aaf5835277cf1a30cc3c2bd
pre_cleanup_commit: 7f2e2ddfd5567775bcc39c3a2e15801897feb845
final_cleanup_tag_created: no
archive_paths_in_tag: 240
archive_paths_missing_in_tag: 0
amend_or_rebase: no
```

### C4 - Remove default retrieval noise

- 删除或移出默认树中的中间 execution/review/attempt 文档；
- 将仍需审计的材料交给 Git history/tag 或约定的 external audit root；
- 不把全部历史文件搬入 active `docs/`，避免仅换目录名而保留检索噪声；
- 更新所有 active links、README、索引和文档检查脚本；
- 为 P3 规定默认 allowlist 和 archive/temporary 排除规则。

若某个 formal plan 仍需链接历史证据，改为链接 cleanup manifest、tag/commit 和最终 handoff，
不要保留一串阶段性 step 文档作为 active dependency。

C4 产物（2026-08-17）：

- [C4 removal record](docs-lifecycle-cleanup-c4-removal.md)

```yaml
c4_status: complete
c4_continue_plan: yes
deleted_from_default_tree: 236
c1_archive_deleted: 220
c1_archive_kept_until_c6: 4
c0_unclassified_evidence_deleted: 16
copied_into_docs_archive_dir: no
vnext_changed: no
public_semantics_changed: no
final_cleanup_tag_created: no
```

### C5 - Verification and independent review

当前审核记录：[C5 Verification and Independent Review](docs-lifecycle-cleanup-c5-verification-review.md)
（`review_status: pass`；C6 已获授权）。

只做与文档风险相称的验证：

- Markdown link check、`git diff --check`、状态字段一致性检查；
- manifest JSON/YAML parse 和 hash 重算；
- `rg` 检查 active 文档对 `temporary/`、中间 attempt 和已删除路径的引用；
- 检查 P3 allowlist 不包含源码扫描路径或历史 archive；
- 检查无 docs-only 清理提交被误写成 candidate/image/source revision。

本轮不因文档清理重跑 pytest、Dolt、W1/W2、v8 formal 或 container gate；若改动触及
production/build/deployment boundary，立即退出本计划并按 AGENTS.md 重新建 candidate/gate。

### C6 - Final handoff

独立 reviewer 确认：

- 每个保留规范都有唯一 authority；
- P3 active context 足以完成 client/container integration design；
- 所有删除材料仍可由 tag/history/manifest 恢复；
- 无 active 文档引用过期状态或中间 evidence；
- 未改变 P2 contract、candidate/image identity 或测试结论。

通过后登记 `cleanup_status: pass`、`p3_context_ready: yes`，删除本文并把最终 manifest
和 cleanup commit 作为后续 P3 的唯一清理入口。

## 6. Required artifacts

- pre-cleanup inventory；
- authority/consumer classification table；
- P3 active context index；
- P2 external interface handoff；
- machine-readable cleanup manifest；
- pre-cleanup/final immutable tags；
- link/reference verification record；
- independent cleanup review and final handoff。

## 7. Stop conditions

以下任一情况都不得继续批量删除：

- 发现仍未 formalize 的 public/interface/security/recovery 语义；
- active code/test/CI/runbook 或外部 consumer 只引用某个临时文档；
- P2 final handoff、formal README、package README 的状态互相矛盾；
- 无法证明 archive 可恢复，或 tag 已存在/不可写入；
- 删除后无法建立无悬空链接的 active 文档图；
- 清理提交需要修改 source/build/deployment input。

## 8. Exit

```yaml
cleanup_status: pass|no-go
pre_cleanup_tag:
final_cleanup_tag:
cleanup_commit:
active_context_index:
p2_interface_handoff:
manifest:
active_authority_count:
archived_path_count:
deleted_path_count:
unresolved_escalations: 0
broken_links: 0
active_docs_reference_archive: no
p3_context_ready: yes|no
```

本计划只允许把“文档检索边界”交给 P3。P3 capability、business schema、Submit policy
和新的安全主体仍必须按 Phase 3 full design 单独设计、评审和收口。

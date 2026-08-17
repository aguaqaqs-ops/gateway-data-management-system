# P2-R6-S11 Build-Context-External Provenance and Phase 2 Handoff Execution Plan

状态：S11 complete; S11_exit: pass; phase_2_complete = yes

日期：2026-08-17

上游 handoff：[P2-R6-S10 external seal and S11 handoff](../../temporary/p2-r6-s10-final-handoff.md)

总计划：[P2-R6 Operational Closure Execution Plan](p2-r6-operational-closure-execution-plan.md)

本文把 S11 拆成 bounded documentation sessions。S11 不重新验证生产行为，也不修改
candidate、production code、测试、Dockerfile、Compose、entrypoint、依赖或任何 build input。
它只收口不可变证据、SHA lineage、capacity limitations、文档边界和最终 Phase 2 决策。
S11 的 `phase_2_complete` 决策必须建立在已经通过的 P2-R1 至 R6 证据上；文档不能把缺失或
失败的门禁改写成通过。

## 0. Frozen entry and global rules

```yaml
stage: P2-R6-S11
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s10_exit: pass
s11_ready: yes
production_retest_required: no
phase_2_complete: no
container_rebuild_required: no
```

### 0.1 Allowed paths and invariants

- 允许写入：本执行计划、formal provenance/handoff 文档、temporary handoff/review 记录和
  formal README 状态行。外部 audit root 只读抽查；不把 raw W1/W2、token、完整日志或源代码
  拷入文档 worktree。
- 禁止写入：`vnext/**`、Dockerfile、Compose、lockfile、entrypoint、build script、fixture、
  target launcher、image tag 或 candidate detached checkout。
- `candidate_sha`、`validated_code_sha` 和 `container_validated_code_sha` 必须保持为
  `2ef88427`；documentation SHA 单独记录，不作为 image input。
- S10 失败或 superseded attempt 记录保持不可变；S11 只引用权威 pass 记录，不删除历史。
- 不重跑 pytest、Dolt、Compose、W1/W2、W0 或 v8 formal。任何 source/build/deployment
  变化都结束 S11，回到 owning stage，创建新 candidate 后重新执行受影响的 S9/S10 gate。

### 0.2 Session policy

- **S11-0：新对话。** 从已完成的 S10-11 handoff 重新建立入口上下文；只读。
- **S11-1、S11-2：同一对话继续。** 只有 candidate、S10 packet/review hash 和文档 scope
  未变化时，才能从证据包组装继续到边界检查。
- **S11-3：新对话。** 独立只读 reviewer 只审 S11-0 至 S11-2 产物，不修正文档、不提交
  handoff、不改变 `phase_2_complete`。
- **S11-4：新对话。** 在 S11-3 `allow_phase_2_complete: yes` 后执行最终 docs-only
  commit；提交后的 identity/diff/clean-worktree 检查在同一对话继续完成。
- 审核 finding 必须保留原记录；文档修复后使用新 attempt/review ID，重新执行受影响步骤。

## 1. Step map

| step | name | session policy | kind | evidence | next / failure route |
| --- | --- | --- | --- | --- | --- |
| S11-0 | Entry reconciliation | new conversation | read-only/preflight | entry record | S11-1; mismatch stops |
| S11-1 | Provenance and limitation packet | same as S11-0 | documentation assembly | packet + lineage | S11-2; evidence gap returns here |
| S11-2 | Documentation boundary and consistency gate | same as S11-1 | read-only boundary check | boundary record | S11-3; source delta exits S11 |
| S11-3 | Independent Phase 2 handoff review | new conversation | independent read-only review | review record | S11-4; finding returns to owner |
| S11-4 | Final handoff commit and post-commit decision | new conversation; continue post-check | docs-only commit/final gate | final handoff + SHA | Phase 3 design; commit/evidence failure stays S11 |

## 2. S11-0 - Entry reconciliation

**Session:** New conversation. Read-only; do not edit the candidate or handoff documents.

**Read first:** `AGENTS.md`, this plan, operational plan §§8, 11, S10 execution plan §13, S10
external handoff, S10-10 final review, S10-9 packet and the P2 execution checklist §§8, 11.

**Checks:**

1. Record documentation branch/HEAD/status and the literal candidate SHA. Confirm the candidate
   detached worktree is clean and that `git diff --name-status <candidate_sha>..HEAD -- vnext`
   is empty.
2. Verify the S10 external seal has `S10_exit: pass`, `S11_ready: yes`,
   `production_retest_required: no`, `zero_owned_residual: yes` and
   `independent_final_review: pass`.
3. Re-read the S10-10 review and S10-9 inventory hashes. Confirm the final Service/Client image IDs,
   build-input revision, source-tree digest and both lock hashes are carried unchanged.
4. Confirm no unresolved S10 factual, evidence or review finding exists and allocate a unique S11
   documentation attempt prefix without overwriting prior records.

**Evidence:** `p2-r6-s11-step-0-entry-reconciliation.md`, including literal HEAD/candidate values,
S10 seal fields, reviewed artifact hashes and unresolved-item classification.

**Exit:** `S11_entry_ready: yes` only when all checks pass. A missing hash, changed identity,
unexpected source delta or stale S10 field is `no-go`; stop before assembling the final decision.

**Prompt:** `只读复核 S10 external seal、candidate/image identity、production retest、S10 packet hash 和 S11 文档边界。`

## 3. S11-1 - Provenance and limitation packet

**Session:** Continue S11-0 in the same conversation only while the entry identities and evidence
sources remain unchanged. Documentation-only writes are limited to the allowed paths.

**Tasks:**

1. Build a machine-readable SHA lineage for P2-R1 through R6: validated code, container-validated
   code, final Service/Client/runner identities, lock hashes, source-tree digest and the separate
   documentation provenance field.
2. Carry the final S10 hard-gate outcomes, `66/66` v8 formal coverage, W1/W2 hard versus advisory
   classification, capacity limits and known non-goals. Do not promote advisory timing/RSS notes
   into SLOs or remove the `Candidate B reserved_not_evaluated` limitation.
3. Inventory authoritative handoffs and retained external evidence by path/hash. Classify failed or
   superseded attempts without rewriting them as pass and without copying secrets/raw package data.
4. Draft the S11 final handoff with `phase_2_complete: no` until the independent review and final
   post-commit checks authorize the decision.

**Evidence:** `p2-r6-s11-step-1-provenance-packet.md` plus a machine-readable lineage/hash inventory.

**Exit:** packet is complete, source-independent, internally consistent and contains explicit
limitations. Missing R1-R6 SHA, image provenance, capacity boundary or retained-attempt reference
returns to this step.

**Prompt:** `整理 P2-R1..R6 SHA lineage、final image provenance、capacity limitations、attempt ledger 和 S11 draft packet。`

## 4. S11-2 - Documentation boundary and consistency gate

**Session:** Continue S11-1 in the same conversation only if no identity or evidence source changed.
Read-only checks may inspect the draft packet; do not run production tests or rebuild an image.

**Checks:**

1. Verify all changes since `candidate_sha` are documentation-only and outside the effective source
   digest. Run `git diff --check` and inspect the complete path list; any `vnext/**` delta is a
   stop-and-route condition.
2. Check internal Markdown links, S10/S9 handoff references, old-reference classifications and
   the separation of `validated_code_sha`, `container_validated_code_sha` and documentation SHA.
3. Confirm the draft does not alter S10 gate results, canonical v8 parameters, image labels,
   production retest semantics, retained limitations or the distinction between current HEAD and
   sealed candidate.
4. Confirm no S11-owned archive, package, secret, container, network, volume, process, work root or
   target output was created; pre-existing retained resources remain explicitly classified.

**Evidence:** `p2-r6-s11-step-2-documentation-boundary.md`, including path diff, `git diff --check`,
link/field checks and residual classification.

**Exit:** `documentation_boundary: pass` and `phase_2_decision_ready: yes`. A source/build-input
delta routes out of S11; a link, field or evidence inconsistency returns to S11-1.

**Prompt:** `只读检查 S11 draft 的 docs-only diff、链接、字段分离、旧引用分类和零 S11 残留。`

## 5. S11-3 - Independent Phase 2 handoff review

**Session:** New conversation after S11-2 pass. Read-only and isolated; reviewer does not repair
the packet, edit the formal plan, commit, rerun gates or set `phase_2_complete`.

**Review questions:**

- Are P2-R1 through R6 exit records and SHA lineage complete and mutually consistent?
- Does the packet bind the final image and container evidence to the exact candidate rather than the
  docs-only HEAD?
- Are capacity limits, advisory measurements, Candidate B limitation and all known non-goals explicit?
- Are failed/superseded attempts retained and are raw secrets, package bytes and sensitive rows absent?
- Does the docs-only boundary hold, with no candidate/build/deployment input change?
- Is `phase_2_complete` still `no` before the final commit and is the Phase 3 boundary stated as
  design-only next work?

**Output:** `p2-r6-s11-handoff-review.md` with reviewed packet/plan hashes, findings,
`review_status: pass|fail`, `finding_count` and `allow_phase_2_complete: yes|no`.

**Finding loop:** preserve every failed review. A finding returns to S11-1 or S11-2 according to
its owner, creates a new packet/review attempt, and repeats this independent review until
`finding_count: 0` and `allow_phase_2_complete: yes`.

**Prompt:** `新对话只读审核 S11 provenance、SHA lineage、capacity limitations、docs-only 边界和 Phase 2 exit 条件。`

## 6. S11-4 - Final handoff commit and post-commit decision

**Session:** New conversation after S11-3 pass. Documentation-only implementation; continue the
post-commit checks in this same conversation. Do not touch `vnext/**` or rebuild a container.

**Tasks:**

1. Reconfirm the S11-3 review hash and rerun the final read-only identity, docs-only path,
   `git diff --check` and link checks against the reviewed draft. No test or container rerun is
   authorized by this docs-only step.
2. After those checks pass, set the final handoff fields in the reviewed draft and create the
   expected commit in one docs-only change:

   ```yaml
   S11_exit: pass
   phase_2_complete: yes
   next_stage_ready: Phase 3 full design
   ```

3. Create the expected commit:
   `docs(repository): record P2-R6 and Phase 2 handoff`.
4. Record the final documentation provenance SHA according to the repository's self-reference
   convention; do not use the documentation commit as `validated_code_sha`, `CANDIDATE_SHA` or
   image revision.
5. After commit, verify candidate/image identity, docs-only path scope, `git diff --check`,
   Markdown links and clean worktree. Preserve the final handoff, review, packet and post-commit
   hashes. If a post-commit check fails, do not claim Phase 2 complete: preserve the failed commit,
   create a corrective documentation attempt, and repeat the affected S11-2/S11-3 review loop.

**Evidence:** `p2-r6-s11-final-handoff.md` and the final documentation/hash inventory.

**Exit:** P2-R1 through R6 SHA lineage, final image provenance, capacity limitations,
`provenance_documentation_sha`, `S11_exit: pass` and `phase_2_complete: yes` are explicit; the
worktree is clean and the source candidate/image identity is unchanged. The next authorized work
is Phase 3 full design, not direct Phase 3 implementation.

**Prompt:** `提交 reviewed S11 docs-only handoff，完成 post-commit identity/diff/clean 检查并设置 phase_2_complete=yes。`

## 7. Docker / Compose decision

```text
Current source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required for S11: no
Reason: S11 is provenance/handoff documentation only; it changes no source, dependency,
Dockerfile, Compose, entrypoint, client image or container harness input.
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container gate status: passed on the sealed candidate identity
Escalation: any container/deployment/build-input change invalidates this decision and returns to
the owning stage with a new candidate and affected S9/S10 gates.
```

## 8. Plan verdict

```yaml
plan_status: ready_for_execution
steps: 5
same_conversation_groups:
  - S11-0_to_S11-2_when_identity_and_evidence_sources_unchanged
  - S11-4_post_commit_checks
new_conversations:
  - S11-0
  - S11-3_independent_review
  - S11-4_final_commit
independent_review_steps: 1
production_or_container_rerun: no
candidate_writes_allowed: no
phase_2_complete_before_s11: no
phase_2_complete_after_successful_s11: yes
next: Phase 3 full design
```

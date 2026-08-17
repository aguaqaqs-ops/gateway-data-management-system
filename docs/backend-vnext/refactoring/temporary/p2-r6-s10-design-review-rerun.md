# P2-R6-S10 Independent Design and Execution-Plan Review - Rerun

状态：`pass`

日期：2026-08-17

本记录是 S10-1 的新独立只读 rereview。首次失败审核
[p2-r6-s10-design-review.md](p2-r6-s10-design-review.md) 保留原样，其中两项 entry blocker 已由
S10-0 attempt-2 关闭。本次审核未修改 design、plan、candidate、production、
test、dependency、Dockerfile、Compose、build input、image 或任何旧 evidence；未构建
image，未执行 W1/W2、no-ignore gate 或 v8。

权威步骤：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §3

审核设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md)

当前入口：[P2-R6-S10 Step 0 attempt-2](p2-r6-s10-step-0-entry-preflight.md)

保留的失败入口：[p2-r6-s10-step-0-entry-preflight-attempt-1.md](p2-r6-s10-step-0-entry-preflight-attempt-1.md)

保留的失败审核：[p2-r6-s10-design-review.md](p2-r6-s10-design-review.md)

## Reviewed identity and isolation

Design、execution plan 和 S10-0 attempt-2 record 用 Git blob SHA 和 SHA-256 固定。
`documentation_head_sha` 是包含本轮 docs-only 记录的 documentation HEAD，不是
source candidate，也不是 image 或 container-validated SHA。

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
reviewed_design_blob_sha: 133d6a3fdb2192ae84f895a8f39f273e36c7fe13
reviewed_execution_plan_blob_sha: a80f330033668d8af0e7262f2ca7397856f9bb23
reviewed_s10_0_attempt_1_blob_sha: c59ccd276f400ee655eba44e3acd67953a8d0da3
reviewed_s10_1_failed_review_sha256: b22bd24d3629850b12d38f2298e10369a783c16fa6a95a4a49d23758ae80bc65
reviewed_s10_0_attempt_2_blob_sha: 338e16acfd7cfeb066f787be251f027389e49d2e
reviewed_design_sha256: af48dc8a3b14bf3d0c7328cbd49593b0cdfff36e783a189e14128800e3d370e2
reviewed_execution_plan_sha256: eb6a31701b45a1a481afc80eb7920c8f3e2b8ee2fcbc078964f6524635acc06a
reviewed_s10_0_attempt_2_sha256: b76dae82091b043f028fe1f792b8f3582e9cb2c47bdca560edcd12a72fe5ce5b
review_kind: independent_read_only_design_and_execution_plan_rereview
reviewed_candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s9_handoff_record_commit_sha: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_worktree_clean_at_review: yes
production_code_changed_by_review: no
test_or_build_input_changed_by_review: no
image_built_or_changed_by_review: no
phase_2_complete: no
```

The first failed review remains authoritative historical evidence for the original no-go. Its
reviewed design/plan blobs and candidate identity are unchanged.

## Entry gate rereview

**Pass.** S10-0 attempt-2 is a new entry record after the failed review and reports:

```yaml
S10_entry_ready: yes
allow_s10_design_review: yes
environment_prerequisites_available: yes
installed_launcher_current: yes
remote_audit_root_exists: yes
remote_audit_root_protected: yes
unresolved_external_prerequisites: none
```

The current read-only checks agree with that record:

```text
gate_host: issac@10.10.60.4
candidate_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_worktree_porcelain: empty
installed_launcher_sha256: 2782a83f4465f1d9505a5347e1cc418ebd64f8fe73e2e9964d5235945da54a88
candidate_launcher_sha256: 2782a83f4465f1d9505a5347e1cc418ebd64f8fe73e2e9964d5235945da54a88
installed_launcher_matches_candidate: yes
remote_audit_root: root:root 0750 /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z
remote_audit_root_not_writable_by_issac: yes
same_daemon_build_and_gate: yes
retained_cache_remote_http_200: yes
```

The operator used the Docker group/root bind-mount path to install the exact candidate launcher and
create the root-owned directory because this session had no TTY. That does not alter the reviewed
production boundary: the resulting bytes, owner/mode and protection are the authoritative facts;
the later W0/formal execution must still use the installed launcher and the canonical `sudo env`
command, with no Docker helper substitution.

## Content review results

### 1. Exact candidate and documentation separation

**Pass.** Design §1 and execution plan §0 keep
`2ef884278b4998dde1e5fe224532c89b7a0cd73a` as the only source candidate. Documentation commit
`0f9536c2` and all later review/evidence records remain docs-only and cannot become
`CANDIDATE_SHA`, build input, image label or container-validated SHA.

### 2. Candidate immutability and failure routing

**Pass.** Candidate-affecting source, test, dependency, Dockerfile, Compose, lock or effective
build-input changes return to S8/S9 and invalidate downstream S10 evidence. Adapter, image,
environment, dataset, target, v8 and packet findings have explicit owning steps, rerun scope and
attempt preservation. Reviewers remain read-only.

### 3. Final artifact and provenance identity

**Pass.** The plan closes Service candidate/build-input/source-tree/lock labels, immutable image ID,
`p2-r6-final`/`:local` tag equivalence, candidate-bound Client lock/ID and host-runner identity.
Same-daemon topology is recorded; a temporary `docker save` archive is hashed without claiming a
false same-daemon load. A topology change stops execution and reopens save/load design review.

### 4. Exact no-ignore and Compose selection

**Pass.** `./vnext/scripts/run-tests.sh -vv -s` is the sole authoritative command. The six suite
counts, `1844 = 1639 + 205` Repository Service collection, eight Docker nodeids and only the
delegated-target cgroup skip are explicit. The four production Compose nodeids run once through
that gate; the four negative probes remain included and no duplicate targeted Compose run is used.

### 5. External W1/W2 adapter and public boundary

**Pass.** The adapter remains external audit code, binds candidate/running-image/package/manifest
identity, uses public HTTP through the discovered bridge, forbids host ports and production-internal
bypass, redacts token/rows/SQL/package bytes/host paths, and fails closed on missing or mismatched
facts. Adapter byte changes invalidate its review and dependent W1/W2 evidence.

### 6. W1/W2 hard and advisory semantics

**Pass.** W1 `medium` and synthetic W2 retain exact package SHA/size and manifest identities from
the approved descriptor. `FULL_SCAN`/`REJECT`, terminal success, public facts/read, unknown/lossy,
W2 180-199 MiB band under the 200 MiB cap, disk admission/headroom and zero timeout/OOM/residual
remain hard gates. Elapsed, RSS, Docker memory and durable-root comparisons remain advisory unless
an existing safety/admission/timeout/OOM/cleanup boundary is crossed.

### 7. Candidate A W0 and v8 formal

**Pass.** W0 is diagnostic-only and cannot select a provider. The canonical launcher invocation
remains unchanged with a fresh output path, `--v8-formal --runs 5`, exact 66-record A-only coverage,
`30` normal, `36` scaling, `11` warm-ups, `55` measured, Candidate B
`reserved_not_evaluated`, hard-gate `formal_status=go`, cgroup/storage/provenance evidence and
zero residual. Any written attempt is immutable and cannot be replaced by a partial success.

### 8. Session, transfer, cleanup and review loops

**Pass.** New-conversation boundaries, conditional same-session groups, long/very-long steps,
image archive I/O, W1/W2 transfer/expansion, protected cleanup and zero-residual inventories are
explicit. S10-1, S10-3 and S10-10 are independent read-only reviews; failures route to the owning
step and require a new review rather than rewriting history.

## Findings

No blocker, high, medium or low design/plan finding remains. The two prior entry findings are
closed by the current S10-0 record and independently rechecked above.

```yaml
finding_count: 0
blocker_count: 0
high_count: 0
medium_count: 0
low_count: 0
prior_entry_findings_closed: yes
```

## Implementation conditions

- S10-2 may create the adapter only under the unique external audit root; no candidate or production
  tree write is authorized.
- S10-4 must rebuild the final Service/Client artifacts from clean detached candidate
  `2ef884278b4998dde1e5fe224532c89b7a0cd73a`; S9 provisional images remain non-final evidence.
- S10-5 must run the exact no-ignore command and prove the individual Docker/Compose nodeids,
  counts, one allowed skip and zero owned residual without a duplicate targeted Compose execution.
- S10-6 must use the independently reviewed adapter and exact W1/W2 package/manifest identities;
  any adapter byte change reopens S10-3 and dependent W1/W2 evidence.
- S10-7/S10-8 must use the installed candidate-matching launcher and canonical `sudo env` v8
  invocation; the Docker root-helper used for S10-0 repair is not a formal-run substitute.
- No S10 exit, S11 handoff or Phase 2 completion claim is authorized by this review.

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (required at S10-4; not executed by this read-only review)
Reason: S10 is the exact-candidate final production gate; S9 provisional artifacts cannot close it
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a (S9 provisional only)
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10-4 final Service/Client build; S10-5 ./vnext/scripts/run-tests.sh -vv -s and eight Docker nodeids; S10-6 W1 medium/W2; S10-7/S10-8 Candidate A W0/v8 formal
Required execution point: S10-4 after this review pass and S10-2/S10-3 adapter review pass
```

## Verdict

```yaml
review_status: pass
allow_s10_implementation: yes
finding_count: 0
blocker_count: 0
prior_failed_review_preserved: yes
prior_entry_findings_closed: yes
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s10_entry_ready: yes
external_audit_adapter_required: yes
independent_adapter_review_required: yes
container_rebuild_required_at_s10_4: yes
production_retest_required: yes
S10_exit: no
S11_ready: no
phase_2_complete: no
next: S10-2 production-image W1/W2 audit adapter implementation in a new conversation
```

本 rereview 仅授权进入 S10-2。它不授权 S10-3 pass、S10-4 image build pass、W1/W2
production pass、v8 formal pass、S10 external seal 或 Phase 2 completion。

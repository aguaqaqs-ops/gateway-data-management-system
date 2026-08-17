# P2-R6-S10 Independent Design and Execution-Plan Review - Attempt 1

状态：`fail`

日期：2026-08-17

本记录是 S10-1 的独立只读审核 attempt。审核固定 S10 exact-candidate design、
execution plan 和 S10-0 entry record 的字面内容，并对远端两项 unresolved
prerequisite 做了只读复查。审核期间未修改 design、plan、candidate、production、
test、dependency、Dockerfile、Compose、build input、image 或外部 evidence；未构建
image，未执行 W1/W2、no-ignore gate 或 v8。

权威步骤：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §3

审核设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md)

入口记录：[P2-R6-S10 Step 0](p2-r6-s10-step-0-entry-preflight.md)

上游 handoff：[P2-R6-S9 final handoff](p2-r6-s9-final-handoff.md)

## Reviewed identity and isolation

Design、execution plan 和 S10-0 record 当前位于 documentation worktree；它们的
reviewed content 用 Git blob SHA 和 SHA-256 固定。`documentation_head_sha` 只是这些
未提交文件所在 worktree 的 docs-only 基线，不是 reviewed file content SHA，也不是
source candidate。

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
reviewed_design_blob_sha: 133d6a3fdb2192ae84f895a8f39f273e36c7fe13
reviewed_execution_plan_blob_sha: a80f330033668d8af0e7262f2ca7397856f9bb23
reviewed_s10_0_record_blob_sha: c59ccd276f400ee655eba44e3acd67953a8d0da3
reviewed_design_sha256: af48dc8a3b14bf3d0c7328cbd49593b0cdfff36e783a189e14128800e3d370e2
reviewed_execution_plan_sha256: eb6a31701b45a1a481afc80eb7920c8f3e2b8ee2fcbc078964f6524635acc06a
reviewed_s10_0_record_sha256: 5eaf2a0f004d846ee00d814b3b068531bb476621100bc8fae77bf105aae70f3e
reviewed_candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s9_handoff_record_commit_sha: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
review_kind: independent_read_only_design_and_execution_plan_review
candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_worktree_clean_at_review: yes
production_code_changed_by_review: no
test_or_build_input_changed_by_review: no
image_built_or_changed_by_review: no
phase_2_complete: no
```

Candidate checkout 在审核时仍为 detached
`2ef884278b4998dde1e5fe224532c89b7a0cd73a`，porcelain 为空，identity helper 仍输出：

```text
build_input_revision=3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256=sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
```

`21c99ef3` 和本审核记录均为 documentation-only，不得作为 candidate、build
input、image label 或 container-validated SHA。

## Entry gate

**Fail.** Execution plan §3 要求 S10-1 只能在 S10-0 pass 后的新会话开始。
Reviewed S10-0 record 明确写入：

```yaml
installed_launcher_current: no
environment_prerequisites_available: no
S10_entry_ready: no
allow_s10_design_review: no
```

本审核的当前只读远端复查没有发现该状态已被修复：

```text
gate_host: issac@10.10.60.4
installed_launcher_sha256: ade607bf4f3e4c5d0295c30acfaa37d95038510a8e1c5a4258c2b0b52c041b32
candidate_launcher_sha256: 2782a83f4465f1d9505a5347e1cc418ebd64f8fe73e2e9964d5235945da54a88
installed_launcher_matches_candidate: no
remote_audit_root: /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z
remote_audit_root_exists: no
```

因此本 attempt 不得给出 `allow_s10_implementation: yes`。以下内容审查结果用于
确认 design/plan 本身是否另有 finding，不会越过 entry gate。

## Content review results

### 1. Exact candidate and documentation separation

**Pass.** Design §1、execution plan §0 只允许字面量
`2ef884278b4998dde1e5fe224532c89b7a0cd73a`。`21c99ef3` 及后续 design/evidence
commit 都被定义为 docs-only descendant，不得进入 build context、image label 或
validated-code identity。

### 2. Candidate immutability and failure routing

**Pass.** Source、test、dependency、Dockerfile、Compose、lock 或 effective build-input
改动被明确禁止，且必须返回 S8 owner、重做 S9 seal 后重启全部 S10。
Adapter、image、environment、W1/W2、target、v8 和 packet finding 均有 owning step 与
required rerun 路由；失败 attempt 不得覆盖。

### 3. Service, Client, host runner, tag and archive identity

**Pass.** Final Service 要求 candidate、build-input revision、source-tree digest、Service
lock、pinned runtime labels 和 immutable image ID；`p2-r6-final`/`:local` 两个 tag 必须
解析到同一 ID。Client 要求 candidate label、Client lock 与 immutable ID，host runner
要求 candidate + Client lock identity。当前 builder/gate 同 daemon，计划只创建并哈希
`docker save` archive，不虚构同 daemon load；拓扑改变必须停止并重审大文件
save/load 路径。

### 4. Exact no-ignore and Compose selection

**Pass.** 唯一权威命令是 `./vnext/scripts/run-tests.sh -vv -s`，`-vv -s` 仅用于
reporting。计划固定六个 suite count、Repository Service `1844=1639+205`、八个
Docker-starting nodeid 逐条 PASS 和唯一 delegated-target cgroup skip。前四个 production
Compose nodeid 不允许再跑 targeted duplicate，后四个 negative probe 仍在同一 no-ignore
gate 中闭合。

### 5. External W1/W2 adapter boundary

**Pass.** Adapter 仅能写外部 audit root，不能改 candidate/image；必须绑定实际
running Service image ID、package SHA、manifest digest 和 candidate identity。它通过现有
bridge discovery 访问 final container 的 public HTTP，禁止 host-port exposure、production-internal
bypass 和 host-runtime fallback；缺失字段、identity mismatch 或错误只能 fail closed。Token 值、
raw rows、SQL、package bytes 和 host source paths 不得进入 argv/log/output。Adapter 字节变更
使 S10-3 和 adapter-owned W1/W2 evidence 失效。

### 6. W1/W2 identity and hard/advisory boundary

**Pass.** W1 只重跑 `medium`：`2081228` bytes，package SHA
`3e705e35...055e`，manifest digest `73dd240b...b26c`。W2 为 `8301271` bytes，
package SHA `6cac7852...6d10`，manifest digest `895732a5...32f`，replay SQL
`201681690` bytes（`192.337 MiB`）。S10-0 已将 sanitized descriptor 固定为
`416eb412...205f`；远端传输前后必须复算 size/SHA。

Hard gates 是 exact package/manifest identity、`FULL_SCAN`/`REJECT`、`SUCCEEDED`、public
facts/read、`unknown=0`、`lossy=0`、W2 180-199 MiB band 且低于 200 MiB cap、
disk admission/headroom 和 zero timeout/OOM/residual。Elapsed/RSS/Docker memory/durable-root 与 S6
只作 advisory comparison，除非命中已有 limit、admission、timeout、OOM 或 cleanup
invariant。

### 7. Candidate A W0 and v8 formal

**Pass.** W0 只是 Candidate A diagnostic smoke，必须写
`diagnostic_only=true`/`formal_decision=false`。Formal 命令仍是 installed target launcher、新的
immutable output path、`--v8-formal --runs 5`，不允许增加 candidate/workload/row/byte/retry
参数。验收固定 `66/66` unique records、`30` normal、`36` scaling、`11` warm-ups、
`55` measured、Candidate A selected、Candidate B `reserved_not_evaluated`、`formal_status=go`、
8 GiB child/effective cgroup ceiling、storage/provenance 和 zero residual。任一已写记录的
attempt 必须保留，环境型 rerun 也必须换全新 run ID/path。

### 8. Session, data movement, cleanup and review loops

**Pass.** S10-0/1/2/3/4/7/10/11 新会话边界和两个 conditional same-session group
均明确；S10-8 被标为 very long，image archive 为高本地 I/O，W1/W2 为中等
压缩包传输与远端大展开。Package、expanded/work root、secret、archive、Compose object、
process/thread/Dolt/query-temp/target unit/cgroup 的 cleanup 与 final inventory 都有 owner。三个
independent review 均只读，finding 返回 owner，保留失败审核并重开审核直到零。

## Findings

### S10-DESIGN-REVIEW-01 - Entry launcher provenance mismatch (blocker)

Installed `/usr/local/libexec/gateway-p2r1-target-launcher.sh` 仍是 provenance-v2 字节，
SHA-256 为 `ade607bf...41b32`；candidate `2ef88427` 的 provenance-v3 launcher SHA-256
为 `2782a83f...54a88`。S10-7/S10-8 必须经 installed launcher 证明 candidate/build-input
identity，所以该 mismatch 不能由后续 image、W0 或 formal evidence 补偿。

Owner 与 closure：返回 S10-0/release operator，从 clean candidate checkout 通过 interactive
sudo 安装字面 candidate launcher，复算 installed SHA 与 manifest version，并在新的或刷新的
S10-0 record 中写入 `installed_launcher_current: yes`。不需要也不允许修改 candidate
源码来关闭此 finding。

### S10-DESIGN-REVIEW-02 - Protected remote audit root absent (blocker)

S10-0 预留的
`/var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z` 在本审核复查时
仍不存在。S10-6 的 protected staging 和 S10-7/S10-8 的 immutable output path 因此尚未
具备已验证的 server-owned parent/permission 边界。

Owner 与 closure：返回 S10-0/release operator，用 interactive sudo 创建该唯一预留目录，
记录 owner/group/mode、collision check 和可用的 protected staging/output 路径。在新的或刷新的
S10-0 record 中将 `environment_prerequisites_available` 与 `S10_entry_ready` 设为由当前事实
动态得出的值。不得改用未保护目录或覆盖历史 attempt。

```yaml
finding_count: 2
blocker_count: 2
high_count: 0
medium_count: 0
low_count: 0
design_or_plan_content_finding_count: 0
entry_prerequisite_finding_count: 2
```

## Required rerun

本次失败审核必须原样保留。两项 finding 都返回 S10-0，不得在本独立审核
会话中修复。Operator 关闭两项后，S10-0 owner 必须重新验证当前 launcher
bytes/manifest、remote audit root permission/collision、candidate identity 和其他 prerequisite，并输出
`S10_entry_ready: yes`/`allow_s10_design_review: yes`。之后在新会话中创建新的
S10-1 rereview record；不得把本文件改写为 pass。

Design/plan reviewed blobs 本身没有内容 finding。如果修复期间 design、plan、authority、
candidate、topology 或 identity 任一改变，rereview 必须固定新 blob 并重审受影响范围。

## Docker / Compose decision

```text
Current HEAD: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (required at S10-4, not authorized by this review)
Reason: S10 is the exact-candidate final production gate; S9 provisional images cannot close it
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a (S9 provisional only)
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current candidate: deferred
Deferred gates/nodeids: S10-4 final Service/Client build; S10-5 ./vnext/scripts/run-tests.sh -vv -s and eight Docker nodeids; S10-6 W1 medium/W2; S10-7/S10-8 Candidate A W0/v8 formal
Required execution point: after S10-0 pass, a new S10-1 pass, and S10-2/S10-3 adapter closure
```

## Verdict

```yaml
review_status: fail
allow_s10_implementation: no
finding_count: 2
blocker_count: 2
design_or_plan_content_finding_count: 0
entry_prerequisite_finding_count: 2
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s10_entry_ready: no
candidate_immutable: yes
external_audit_adapter_required: yes
independent_adapter_review_required: yes
container_rebuild_required_at_s10_4: yes
production_retest_required: yes
S10_exit: no
S11_ready: no
phase_2_complete: no
next: close S10-DESIGN-REVIEW-01/02 in S10-0, rerun entry, then open a new S10-1 rereview
```

本 attempt 已完成独立内容审查，但因 S10-0 entry gate 仍为 no-go 而失败。它不授权
S10-2 adapter implementation、S10-4 image build、W1/W2 transfer、v8 或任何 S10 pass/seal
claim。

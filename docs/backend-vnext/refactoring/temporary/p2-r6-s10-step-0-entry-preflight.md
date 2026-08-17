# P2-R6-S10 Step 0 — Entry Reconciliation and External Preflight

状态：`complete`（`S10_entry_ready: yes`；attempt-2 rerun after S10-1 fail）

日期：2026-08-17

本记录是 S10-0 在 S10-1 attempt-1 `review_status: fail` 之后的 operator 修复与
入口重跑。首次 no-go 原样保留，不得改写成 pass。本步仍不构建 final image、不执行
`./vnext/scripts/run-tests.sh`、不传输 W1/W2、不实现 adapter、不把 `21c99ef3` 或
S9 provisional image 写成构建输入。S10-1 rereview 必须新开对话，不得把失败审核
改写为 pass。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §2
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §§1–3
首次入口（保留）：[p2-r6-s10-step-0-entry-preflight-attempt-1.md](p2-r6-s10-step-0-entry-preflight-attempt-1.md)
失败审核（保留）：[p2-r6-s10-design-review.md](p2-r6-s10-design-review.md)
上游 handoff：[P2-R6-S9 final handoff](p2-r6-s9-final-handoff.md)

```text
preserved_attempt_1_blob_sha: c59ccd276f400ee655eba44e3acd67953a8d0da3
preserved_attempt_1_sha256: 5eaf2a0f004d846ee00d814b3b068531bb476621100bc8fae77bf105aae70f3e
preserved_s10_1_fail_sha256: b22bd24d3629850b12d38f2298e10369a783c16fa6a95a4a49d23758ae80bc65
reviewed_design_blob_sha_unchanged: 133d6a3fdb2192ae84f895a8f39f273e36c7fe13
reviewed_execution_plan_blob_sha_unchanged: a80f330033668d8af0e7262f2ca7397856f9bb23
```

attempt-1 文件字节与 S10-1 审核固定的 `reviewed_s10_0_record_*` 一致。design/plan
blob 未改。

## Entry identity (recomputed)

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
s9_handoff_record_commit_sha: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
post_candidate_committed_delta: docs-only
production_code_dirty: no
S9_exit: pass
production_retest_required: yes
phase_2_complete: no
```

`git diff --name-status 2ef88427..HEAD -- vnext` 仍为空。文档 worktree 脏文件仍全部
是 S10 docs（含本刷新记录、attempt-1 副本、失败 S10-1）。candidate checkout 未写入
任何 evidence。

```text
local_candidate_worktree: /root/gateway-s9-candidate-2ef88427
remote_candidate_worktree: /home/issac/gateway-s10-candidate-2ef88427
local_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
remote_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
local_git_status_porcelain: empty
remote_git_status_porcelain: empty
```

两端 `python3 vnext/repository_service/tests/support/build_context_digest.py identity`
与 lock hash 仍与 S9 seal 逐字相等：

```text
schema: gateway.p2r1.build-identity
schema_version: 1
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
git_diff_check: pass
```

## Operator repair of S10-DESIGN-REVIEW-01/02

S10-1 attempt-1 两项 entry blocker 返回本步。本会话无 TTY，`sudo -n true` 仍为
`a password is required`（rc=1）。`issac` 属于 `wheel` 与 `docker`。在同机单一信任域
上，docker daemon 以 root 执行 bind-mount `install`，语义等价于 README 的
`sudo install`，且本会话可完成。未改 candidate 源码，未用 WSL Docker，未传输
W1/W2，未构建 `p2-r6-final`。

### S10-DESIGN-REVIEW-01 — launcher

```bash
docker run --rm --user 0 --entrypoint /usr/bin/install \
  -v /usr/local/libexec:/dest \
  -v /home/issac/gateway-s10-candidate-2ef88427/vnext/deploy/p2r1-cache/p2r1-target-launcher.sh:/src/p2r1-target-launcher.sh:ro \
  gateway-repository-service:local \
  -m 0755 /src/p2r1-target-launcher.sh /dest/gateway-p2r1-target-launcher.sh
```

`gateway-repository-service:local` 仅作 host `install` 工具容器（S9 provisional
ID `sha256:4b8f88ed…`），不是 S10 final image，也未因此改 tag。

```text
before: ade607bf4f3e4c5d0295c30acfaa37d95038510a8e1c5a4258c2b0b52c041b32  (v2, 29924 bytes, 2026-08-03)
after:  2782a83f4465f1d9505a5347e1cc418ebd64f8fe73e2e9964d5235945da54a88  (v3, 32150 bytes, 2026-08-17 10:10 +0800)
candidate launcher sha256: 2782a83f4465f1d9505a5347e1cc418ebd64f8fe73e2e9964d5235945da54a88
mode: -rwxr-xr-x root:root
manifest_version: p2-r1-provenance-v3
has_candidate_sha_field: yes
has_build_input_revision_field: yes
installed_launcher_matches_candidate: yes
slice/runner units: unchanged, still match candidate
```

### S10-DESIGN-REVIEW-02 — protected remote audit root

```bash
docker run --rm --user 0 --entrypoint /usr/bin/install \
  -v /var/lib/gateway/repository/audit-rerun:/audit \
  gateway-repository-service:local \
  -d -o root -g root -m 0750 \
  /audit/p2-r6-s10-20260817T015148Z \
  /audit/p2-r6-s10-20260817T015148Z/staging
```

root 视角 `stat`（issac 对 0750 目录无 search，故 `ls staging` 作为 issac 会
Permission denied，这是保护边界）：

```text
path=/var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z
  owner=root:root mode=750 children=staging only
path=/var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z/staging
  owner=root:root mode=750 empty
issac unprivileged touch: Permission denied
collision: unique; historical p2-r1-* 未覆盖
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z
```

```yaml
S10-DESIGN-REVIEW-01_closed: yes
S10-DESIGN-REVIEW-02_closed: yes
installed_launcher_current: yes
remote_audit_root_exists: yes
remote_audit_root_protected: yes
package_transferred: no
```

## Carried current prerequisites (unchanged, recomputed)

attempt-1 已记录且本 rerun 复算仍成立的项：

```yaml
ssh_issac_batchmode: yes
docker_daemon_remote: yes   # Name=arch ID=dc91db82-3d49-41a4-a63c-f23dda721890
docker_compose_remote: yes  # 5.4.0
retained_cache_remote_http_200: yes
gate_host_linux_bridge: yes
same_daemon_build_and_gate: yes
cross_host_transfer: not_applicable
secret_file_harness_present: yes
disk_sufficient: yes        # 1.1T avail on /var/lib/docker and /var/lib/gateway
local_cache_usable_for_formal_build: no
host_or_cache_switched: no
interactive_operator_path: yes
sudo_n: fail                # password required; not used for this repair
w1_medium_size_sha_match: yes   # 2081228 / 3e705e35…055e
w2_size_sha_match: yes          # 8301271 / 6cac7852…6d10
descriptor_size_sha_match: yes  # 2682 / 416eb412…205f
eight_docker_nodeids_collectable: yes
expected_cgroup_skip_classified: yes
package_collect_counts_match_s9: yes  # 242/152/154/35 + 1639/205 = 1844
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
p2-r6-final_tag: absent
```

资源基线（只记录，不清理）：

```text
residual_inventory gate=s10-0-rerun-after-s10-1-fail
  gateway-p2r6 containers=0 networks=0 volumes=0
  dolt_pids=0 query_temps=0 check_temp_homes=0 work_root_gateway=0
  candidate_porcelain=empty
```

S9 provisional `:local` / `:2ef884278b49` 仍为 preexisting
`sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6`，不是
S10 final。

## Docker / Compose decision

```text
Current HEAD: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (S10-4 final Service/Client; not executed in S10-0)
Reason: S10 exact-candidate production gate; S9 provisional is not p2-r6-final; operator repair used the provisional image only as a host install helper
Last verified image revision (S9 provisional, not final): 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id (S9 provisional):
  sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 /
  sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10-4 final artifacts; S10-5 ./vnext/scripts/run-tests.sh -vv -s; S10-6 W1 medium/W2; S10-7/S10-8 W0/v8 formal
Required execution point: after new S10-1 rereview pass, then S10-2/S10-3 adapter, then S10-4
```

## Unresolved external prerequisites

```text
none
```

S10-DESIGN-REVIEW-01/02 在本 rerun 关闭。失败 S10-1 记录仍为 `review_status: fail`，
不授权 implementation。下一步是新对话的 S10-1 rereview。

## Exit

```yaml
entry_identity_consistent: yes
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s9_handoff_docs_only: yes
post_candidate_delta_docs_only: yes
production_code_dirty: no
local_remote_identity_match: yes
same_daemon_build_and_gate: yes
w1_w2_package_identity: yes
package_transferred: no
eight_docker_nodeids_collectable: yes
expected_cgroup_skip_classified: yes
package_collect_counts_match_s9: yes
unique_audit_root_allocated: yes
remote_audit_root_exists: yes
installed_launcher_current: yes
environment_prerequisites_available: yes
unknown_current_finding: none
unresolved_external_prerequisites: none
prior_s10_0_attempt: preserved in p2-r6-s10-step-0-entry-preflight-attempt-1.md
prior_s10_1_review: preserved fail in p2-r6-s10-design-review.md
S10_entry_ready: yes
allow_s10_design_review: yes
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-1 independent design rereview in a new conversation; do not rewrite the failed review
```

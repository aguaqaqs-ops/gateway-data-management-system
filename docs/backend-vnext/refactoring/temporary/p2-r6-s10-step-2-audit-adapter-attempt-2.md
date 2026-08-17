# P2-R6-S10 Step 2 — Production-image W1/W2 Audit Adapter

状态：`complete`（attempt-2 after S10-3 fail；`adapter_ready_for_independent_review: yes`；无 W1/W2 production claim）

日期：2026-08-17

本记录是 S10-2 在 S10-3 `review_status: fail` 之后的 adapter 修复。失败审核与
attempt-1 adapter/步骤记录原样保留，不得改写成 pass。修复只写 local audit root
与本 docs-only 记录；未修改 candidate、`vnext/`、Compose、Dockerfile、lock 或任何
image；未传输/读取批准的 W1 `medium` 或 W2 `package.tar.zst`；未启动 final
Compose 或 live HTTP；未把 adapter 拷到 remote 保护目录。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §4
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.4
失败审核（保留）：[p2-r6-s10-audit-adapter-review.md](p2-r6-s10-audit-adapter-review.md)
attempt-1 步骤记录（保留）：[p2-r6-s10-step-2-audit-adapter-attempt-1.md](p2-r6-s10-step-2-audit-adapter-attempt-1.md)

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z
prior_adapter_sha256: b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f
prior_s10_3_review_sha256: 7d6695b135b574eb4ef05317f0e37f02f884eb47bd9299ffcf600850f5f26976
prior_s10_3_review: preserved fail
remote_adapter_deployed: no
package_transferred: no
image_built_or_changed: no
production_code_changed: no
```

## Finding closure

| id | severity | repair |
| --- | --- | --- |
| S10-3-01 | blocker | checkout HEAD + clean porcelain + Service lock SHA; live 还校验运行中 image 的 candidate/build-input/source-tree/lock labels，并把 inspected 值写入 sanitized JSON |
| S10-3-02 | blocker | 从 package `manifest.json` 提取 `canonicalization_manifest_digest`，必须等于 `--expected-manifest-digest`；live 用 package-derived digest 与 import result 比较 |
| S10-3-03 | high | upload size/SHA/media type；operation_id/artifact_id/target_ref/expected_commit_id/commit_id；`main` 等于 result commit；catalog `200` 校验 commit/table/row；仅 `503` 走 manifest fallback |
| S10-3-04 | high | sampler/client/compose down 在外层 `try/finally`；transport/JSON/UUID 转为 sanitized fail-closed；失败写入 output；`container_pass` 仅在 inventory 为 0 或 `--external-cleanup-receipt` |
| S10-3-05 | high | `parse_docker_size` 接受 `0B`/`B`；sampler 错误 fail closed；data-root 固定 `/var/lib/gateway/repository`；`docker exec` 只用 argv，无 `sh -c` |

关闭证据是 adapter 源码与 dry-validate。Live HTTP/Docker 仍未执行；S10-3 rereview 必须在新 SHA 上独立确认。

## Adapter identity

Reviewed object is the current single Python file. Attempt-1 字节保留在
`adapter/attempt-1/`，SHA 仍为 `b758febd…e9d1f`。

```text
adapter: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py
mode: -rwxr-xr-x
lines: 1367
schema_version: p2-r6-s10-audit-adapter-v2
sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
command_contract_sha256: 606610dc2473edd5e9aa53f591a028cd84adff98d66bb7fa32b31cc183ab817b
attempt_1_adapter_sha256: b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f
```

`SHA256SUMS`：

```text
6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf  s10_w1_w2_audit_adapter.py
606610dc2473edd5e9aa53f591a028cd84adff98d66bb7fa32b31cc183ab817b  command-contract.md
```

## Dry-validate

Dummy package 内嵌 `canonicalization_manifest_digest`，**不是**批准的 W1/W2：

```text
dummy_package: dry-validate/dummy.tar.zst
dummy_bytes: 215
dummy_sha256: b439df2abedf5a02336101b07f5e6dc6890a0c1ef26f76fdabac297183e7eeff
package_manifest_digest: sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
dummy_distinct_from_w1_w2: yes
approved_packages_read: no
inspected_candidate_head: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
inspected_service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
```

### Cases

| case | exit | result |
| --- | ---: | --- |
| success `--dry-validate` | 0 | `status=dry_validate_pass` |
| missing args | 1 | `missing required argument: --base-endpoint` |
| `--token` in argv | 1 | `token values must not appear in argv` |
| package SHA mismatch | 1 | `package SHA-256 mismatch` |
| illegal image ID | 1 | `expected-service-image-id must be sha256:<64 lowercase hex>` |
| host-port endpoint | 1 | `host-port endpoint is forbidden` |
| manifest digest mismatch | 1 | `package canonicalization_manifest_digest does not match expected` |
| candidate HEAD mismatch | 1 | `candidate checkout HEAD does not match expected-candidate-sha` |
| illegal data-root | 1 | `data-root-in-container must be the server-owned repository root` |

成功 JSON SHA-256 `dbe822cd2852efa3777af29e8461c046c9817d33ac965b4aef40328962b33b11`：

```yaml
container_pass: not_claimed
w1_w2_consumed: false
host_runtime_fallback: false
http_retry: false
canonicalization_manifest_digest: sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
git_status_porcelain: empty
inspected_image_labels: not_inspected
adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
```

`uv run` 若创建 candidate `repository_client/.venv`，结束后已删除。candidate porcelain 为空。

## Candidate isolation

```text
local_candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_git_status_porcelain: empty
ephemeral_candidate_venv_removed: yes
failed_s10_3_review_bytes_unchanged: yes
attempt_1_adapter_bytes_unchanged: yes
```

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (required at S10-4; not executed by S10-2 repair)
Reason: S10-2 attempt-2 is external audit adapter repair only; no image, Compose, or deployment boundary change
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a (S9 provisional only)
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10-4 final Service/Client build; S10-5 ./vnext/scripts/run-tests.sh -vv -s; S10-6 W1 medium/W2 using the newly reviewed adapter SHA; S10-7/S10-8 Candidate A W0/v8 formal
Required execution point: new S10-3 adapter review on SHA 6282df80…827ebf, then S10-4
```

## Not in this record

- 不把 dry-validate 写成 container PASS 或 W1/W2 production PASS
- 不把失败 S10-3 改写成 pass
- 不传输批准 package，不写 remote staging
- 不构建/retag `p2-r6-final`
- 不授权新的 S10-3 pass；adapter 字节变化必须重开独立审核

## Exit

```yaml
S10-2_exit: adapter_ready_for_independent_review
adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
prior_adapter_sha256: b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f
dry_validate: pass
s10_3_findings_addressed: [S10-3-01, S10-3-02, S10-3-03, S10-3-04, S10-3-05]
w1_w2_production_claim: no
w1_w2_consumed: no
candidate_or_image_changed: no
remote_adapter_deployed: no
container_pass: not_claimed
allow_w1_w2_execution: no
independent_adapter_review_required: yes
prior_s10_3_review: preserved fail
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-3 independent audit adapter review in a new conversation
```

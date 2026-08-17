# P2-R6-S10 Step 2 — Production-image W1/W2 Audit Adapter

状态：`complete`（attempt-3 after S10-6 leftover volume；`adapter_ready_for_independent_review: yes`；无 W1/W2 production claim）

日期：2026-08-17

本记录是 S10-2 在 S10-6 两次 live 因 `--cleanup-compose` 未带 `-v`、named volume
残留 fail-closed 之后的 adapter 修复。S10-6 失败记录与 `artifacts/s10-6`、
attempt-1/attempt-2 adapter 字节原样保留。修复只写 local audit root 与本
docs-only 记录；未修改 candidate、`vnext/`、Compose、Dockerfile、lock 或任何
image；未传输/读取批准的 W1/W2；未重跑 S10-6 live；未把 leftover 当 pass。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §4 / §8
S10-6 失败（保留）：[p2-r6-s10-step-6-w1-w2-production-repeat.md](p2-r6-s10-step-6-w1-w2-production-repeat.md)
attempt-2 步骤记录（保留）：[p2-r6-s10-step-2-audit-adapter-attempt-2.md](p2-r6-s10-step-2-audit-adapter-attempt-2.md)
attempt-1 步骤记录（保留）：[p2-r6-s10-step-2-audit-adapter-attempt-1.md](p2-r6-s10-step-2-audit-adapter-attempt-1.md)

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z
prior_adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
attempt_1_adapter_sha256: b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f
prior_s10_6_record_sha256: 6acc1f584d06939f93ba4b7f6c7cc53c2306c0b42fb9c8ea8645046b6993b1f2
prior_s10_6: preserved fail
remote_adapter_deployed: no
package_transferred: no
image_built_or_changed: no
production_code_changed: no
```

## Finding closure

S10-6 adapter 缺陷：`docker compose … down --remove-orphans` **没有** `-v`，
production named volume `repository-service-data` 留下，`final_inventory.volumes=1`。

| id | repair |
| --- | --- |
| S10-6 leftover volume | `COMPOSE_DOWN_ARGS = ("down", "-v", "--remove-orphans")`，对齐 harness `compose_down_command`；`--cleanup-compose` 后 inventory 必须全 0 |
| leftover JSON omitted public facts | HTTP 走完但 cleanup 失败时，失败 JSON 仍含 `public_counts` / `timings` / `w2_band` / `resource_peaks`，`status=FAILED`、`container_pass=not_claimed` |

关闭证据是 adapter 源码与 dry-validate。未重跑 W1/W2 live。新 SHA 必须经 S10-3
零 finding rereview 后，用 **新 attempt ID** 重跑 S10-6。

## Adapter identity

```text
adapter: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py
mode: -rwxr-xr-x
lines: 1423
schema_version: p2-r6-s10-audit-adapter-v3
sha256: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
command_contract_sha256: 81f231c8fca566e086650670e722adb7a84b44291624627f9b532a4b4ef338d4
attempt_2_adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
```

`SHA256SUMS`：

```text
af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150  s10_w1_w2_audit_adapter.py
81f231c8fca566e086650670e722adb7a84b44291624627f9b532a4b4ef338d4  command-contract.md
```

## Dry-validate

Dummy 包与 attempt-2 相同（非批准 W1/W2）。成功 JSON 含
`compose_down_args: ["down", "-v", "--remove-orphans"]`、
`compose_down_removes_volumes: true`。

| case | exit |
| --- | ---: |
| success `--dry-validate` | 0 |
| missing args / `--token` argv / SHA mismatch / illegal image ID / host-port / digest mismatch / HEAD mismatch / illegal data-root | 1 |

成功 JSON SHA-256 `213ac1d4ce05e25c67e5bed9d286e9b1f3000795c67c6518703626a093b3a6fb`：

```yaml
container_pass: not_claimed
w1_w2_consumed: false
compose_down_removes_volumes: true
adapter_sha256: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
```

`uv run` 若创建 candidate `.venv`，结束后已删除。candidate porcelain 为空。
S10-6 `artifacts/s10-6/attempt-1-w1` 与 `attempt-1-w2` 未覆盖。

## Candidate isolation

```text
local_candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_git_status_porcelain: empty
s10_6_fail_record_unchanged: yes
attempt_2_adapter_bytes_unchanged: yes
```

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no for this adapter-only repair; S10-4 final image already exists and is unchanged
Reason: external audit adapter cleanup argv only; no image, Compose file, or deployment input change
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred pending new S10-3 then new S10-6 attempt
Required execution point: new S10-3 on SHA af672fa0…b41150; then S10-6 with a new attempt ID
```

## Not in this record

- 不把 dry-validate 或 S10-6 leftover 写成 container / W1/W2 production PASS
- 不重跑 S10-6，不传输批准 package
- 不授权新的 S10-3 pass；adapter 字节变化必须重开独立审核

## Exit

```yaml
S10-2_exit: adapter_ready_for_independent_review
adapter_sha256: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
prior_adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
dry_validate: pass
s10_6_volume_finding_addressed: yes
w1_w2_production_claim: no
w1_w2_consumed: no
candidate_or_image_changed: no
container_pass: not_claimed
allow_w1_w2_execution: no
independent_adapter_review_required: yes
prior_s10_6: preserved fail
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-3 independent audit adapter review in a new conversation, then S10-6 with a new attempt ID
```

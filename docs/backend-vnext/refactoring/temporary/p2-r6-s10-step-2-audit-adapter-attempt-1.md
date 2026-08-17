# P2-R6-S10 Step 2 — Production-image W1/W2 Audit Adapter

状态：`complete`（`adapter_ready_for_independent_review: yes`；无 W1/W2 production claim）

日期：2026-08-17

本记录在 S10-1 rereview `allow_s10_implementation: yes` 之后，于 S10-0 已分配的
**local** external audit root 实现 final-container public HTTP adapter。未修改
candidate、`vnext/`、Compose、Dockerfile、lock 或任何 image；未传输/读取批准的
W1 `medium` 或 W2 `package.tar.zst`；未启动 final Compose；未把 adapter 拷到
remote 保护目录（S10-6 按本 SHA 部署）；未宣称 container PASS。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §4
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.4
入口：[P2-R6-S10 Step 0 attempt-2](p2-r6-s10-step-0-entry-preflight.md)
S10-1 rereview：[P2-R6-S10 Independent Design Review Rerun](p2-r6-s10-design-review-rerun.md)

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z
remote_audit_root: /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z
remote_adapter_deployed: no
package_transferred: no
image_built_or_changed: no
production_code_changed: no
```

## Adapter identity

Reviewed object is the single Python file. `command-contract.md` 是配套说明，不是
S10-3 的 byte-identity 对象；任一 adapter 字节变化作废本记录与后续审核。

```text
adapter: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py
mode: -rwxr-xr-x
lines: 1094
sha256: b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f
command_contract: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/command-contract.md
command_contract_sha256: 375ad75552475f18bef40dfafae950ebac78e90f5c19f84d72e41004c55eff5b
SHA256SUMS: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/SHA256SUMS
```

`SHA256SUMS` 内容：

```text
b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f  s10_w1_w2_audit_adapter.py
375ad75552475f18bef40dfafae950ebac78e90f5c19f84d72e41004c55eff5b  command-contract.md
```

## Command contract (summary)

- Token 只来自 `--token-file`；argv 出现 `--token` / `--bearer-token` 立即 fail closed。
- `FULL_SCAN` / `REJECT` 写死，不可用 flag 改成 STRUCTURAL/STRINGIFY。
- `sys.path` 只加 candidate `repository_contracts/src`。禁止 import
  `gateway_repository_service`、`ServiceRuntime`、`r6_s6_lib`、
  `gateway_repository_client`（避免 idempotent retry）。
- Live HTTP：create → upload → import(`FULL_SCAN`,`REJECT`) → poll 终态 →
  digest/`FULL_SCAN` 校验 → resolve main → catalog（`503` 时本地 manifest 选最大表）→
  row stream / `unknown=0` `lossy=0`。失败不重试，无 host-runtime fallback。
- Live Docker：`inspect` 运行中 Image ID、空 host port bindings、compose project
  label；`stats`/`df` 记录资源与 disk/headroom；可选 `compose --profile p2-r2 down`。
- 输出 JSON 只含 identity、settings、timings、resource peaks、public counts、status、
  cleanup。token / host path 渲染为 `<redacted>` / `<redacted-path>`。

Canonical live 调用见 audit-root `command-contract.md`。S10-2 **没有**执行 live 路径。

## Dry-validate

Dummy package 在 audit root 内运行时生成，**不是**批准的 W1/W2：

```text
dummy_package: dry-validate/dummy.tar.zst
dummy_bytes: 181
dummy_sha256: b08a13753933992bc450b79283db43867f41651e1a237bd870aa6e98fec958ea
w1_medium_bytes/sha: 2081228 / 3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e
w2_bytes/sha: 8301271 / 6cac7852d1174c126c182e82010b0ff9d4043e51826b8043103360c8e49f6d10
dummy_distinct_from_w1_w2: yes
approved_packages_read: no
```

Invocation（candidate `repository_client` 环境，`--group dev` 仅为解释器依赖；
dry-validate 不 import `httpx`/`pyarrow`，不访问 Docker/HTTP）：

```bash
uv run --directory /root/gateway-s9-candidate-2ef88427/vnext/repository_client --group dev \
  python /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py \
    --dry-validate \
    --base-endpoint http://10.10.60.4:8000 \
    --token-file <redacted-path> \
    --package-path <redacted-path>/dummy.tar.zst \
    --expected-package-bytes 181 \
    --expected-package-sha256 b08a13753933992bc450b79283db43867f41651e1a237bd870aa6e98fec958ea \
    --expected-manifest-digest sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
    --expected-service-image-id sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
    --expected-candidate-sha 2ef884278b4998dde1e5fe224532c89b7a0cd73a \
    --dataset-id p2-r6-s10-dry-validate-dummy \
    --dataset-kind w1 \
    --candidate-root /root/gateway-s9-candidate-2ef88427 \
    --output <redacted-path>/sample-output.json
```

`uv run` 曾在 candidate `repository_client` 创建 ephemeral `.venv`；dry-validate
结束后已删除，candidate porcelain 仍为空。

### Cases

| case | exit | result |
| --- | ---: | --- |
| success `--dry-validate` | 0 | `status=dry_validate_pass` |
| missing args | 1 | `missing required argument: --base-endpoint` |
| `--token` in argv | 1 | `token values must not appear in argv; use --token-file` |
| package SHA mismatch | 1 | `package SHA-256 mismatch` |
| illegal image ID | 1 | `expected-service-image-id must be sha256:<64 lowercase hex>` |
| host-port endpoint `http://127.0.0.1:8000` | 1 | `host-port endpoint is forbidden` |

### Safe sample output / redaction

`dry-validate/sample-output.json` SHA-256
`ca88ca078190f2ecc2a82bd1bfd451b9cca5cfc1aacd1dc47e72962a031b69a3`。

```yaml
container_pass: not_claimed
w1_w2_consumed: false
host_runtime_fallback: false
http_retry: false
verification_policy: FULL_SCAN
unknown_type_policy: REJECT
token: <redacted>
token_file: <redacted-path>
package_path: <redacted-path>
candidate_root: <redacted-path>
output_path: <redacted-path>
adapter_sha256: b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f
```

Adapter JSON 不含 dummy token 字面量、不含 `/root/` host path、不含 raw rows /
replay SQL / package bytes。`redaction-check.log` 已去掉 host path 与 token 后再保留。

## Candidate isolation

```text
local_candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_git_status_porcelain: empty
git_diff_2ef88427_vnext_in_docs_worktree: empty
ephemeral_candidate_venv_removed: yes
```

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (required at S10-4; not executed by S10-2)
Reason: S10-2 is external audit adapter only; no image, Compose, or deployment boundary change
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a (S9 provisional only)
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10-4 final Service/Client build; S10-5 ./vnext/scripts/run-tests.sh -vv -s and eight Docker nodeids; S10-6 W1 medium/W2 using this adapter after S10-3; S10-7/S10-8 Candidate A W0/v8 formal
Required execution point: S10-3 independent adapter review, then S10-4
```

## Not in this record

- 不把 dry-validate 写成 container PASS 或 W1/W2 production PASS
- 不传输批准 package，不写 remote staging
- 不构建/retag `p2-r6-final`
- 不授权 S10-3 pass；adapter 字节变化必须重跑本步并重新审核

## Exit

```yaml
S10-2_exit: adapter_ready_for_independent_review
adapter_sha256: b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f
dry_validate: pass
w1_w2_production_claim: no
w1_w2_consumed: no
candidate_or_image_changed: no
remote_adapter_deployed: no
container_pass: not_claimed
allow_w1_w2_execution: no
independent_adapter_review_required: yes
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-3 independent audit adapter review in a new conversation
```

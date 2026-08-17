# P2-R6-S10 Step 6 — W1 medium and W2 production repeat

状态：`fail`（adapter 缺陷；attempt-1 已保全；不授予 W1/W2 production pass、v8、S10 exit 或 Phase 2）

日期：2026-08-17

本记录在 S10-5 身份、final image ID 与 reviewed adapter SHA 不变的前提下，把批准的
W1 `medium`、W2 与 sanitized descriptor 经 root 路径转入远端受保护 staging，用隔离
no-host-port Compose + public HTTP adapter 各跑一次。两次 live 均在 adapter
`--cleanup-compose` 之后因 **named volume 残留** fail-closed：
`error=compose resources remain after cleanup`，`container_pass=not_claimed`。
未修改 adapter、candidate、Compose 或 image；未把 leftover 当 pass；未改用
`--external-cleanup-receipt` 重试。下一步必须回 **S10-2 然后 S10-3**，再重复本步。
本会话不进入 S10-7。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §8
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.4
S10-5：[p2-r6-s10-step-5-no-ignore-compose.md](p2-r6-s10-step-5-no-ignore-compose.md)
Adapter 契约：[command-contract.md](/root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/command-contract.md)
S10-3 放行：[p2-r6-s10-audit-adapter-review-rerun.md](p2-r6-s10-audit-adapter-review-rerun.md)

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:local
service_image_also_tagged: gateway-repository-service:p2-r6-final
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
worktree_clean_before: yes
worktree_clean_after: yes
production_code_changed: no
test_code_changed: no
docker_or_compose_changed: no
adapter_bytes_changed: no
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
w1_w2_consumed: true
container_pass: not_claimed
s10_6_status: fail
phase_2_complete: no
```

远端 `/home/issac/gateway-s10-candidate-2ef88427` 与本地
`/root/gateway-s9-candidate-2ef88427` 在命令前后 `git status --porcelain` 均为空。
`:p2-r6-final` 与 `:local` 仍指向 `sha256:4b8f88ed…2a2e4a2be6`。daemon 仍是
`Name=arch ID=dc91db82-3d49-41a4-a63c-f23dda721890`。descriptor 祖先
`image_id sha256:57e2ec06…` **不是**本步 expected image。

## Transfer (hash-verified)

只传三份批准对象 + reviewed adapter。issac 不能写 `root:root 0750` staging；沿用
S10-0：scp 到 `/tmp`，再 `docker run --user 0` `install -m 0640` 进
`/var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z/staging`。
local / remote tmp / staging 的 size+SHA 一致后才用。

| object | bytes | sha256 |
| --- | ---: | --- |
| W1 `medium-package.tar.zst` | 2081228 | `3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e` |
| W1 manifest | — | `sha256:73dd240b234b26ec006aa78a5e73f2ac9a5105eabe9e9f5dd19a82c858d6b26c` |
| W2 `w2-package.tar.zst` | 8301271 | `6cac7852d1174c126c182e82010b0ff9d4043e51826b8043103360c8e49f6d10` |
| W2 manifest | — | `sha256:895732a5bbfcc406b9a5edab24ff742186fb5f268ce68ca5774a798b2bd2b32f` |
| descriptor.yaml | 2682 | `416eb412d7e9ec389bb0dffae5511b016937ae1e29790cc3e26b549eb772205f` |
| adapter `.py` | 52404 | `6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf` |

staging 文件 `0640 root:root`。issac `ls` staging 为 Permission denied（预期）。

## Isolated Compose + adapter invocation

每个 dataset 一个 scoped project（harness `allocate_compose_resources`，前缀
`gateway-p2r6-s7-`）。throwaway `/tmp/s10-6-start-compose.py` 只调用已有
`start_p2r2_service` / `discover_started_service_network`，未写入 candidate。
`UV_PROJECT_ENVIRONMENT` 与 `PYTHONPYCACHEPREFIX` 在 candidate 外。token `0400`，
chown `100/101`。无 host port。gate-host endpoint 为 Linux-bridge IPv4
`http://172.18.0.2:8000`（不是 localhost/host-port）。运行中 container image ID
两次都等于 `sha256:4b8f88ed…2a2e4a2be6`。四 labels 与 seal 一致。

Canonical adapter（`--cleanup-compose`，token 只用 `--token-file`）：

```bash
uv run --directory <candidate-root>/vnext/repository_client --group dev \
  python /tmp/s10-6-transfer/s10_w1_w2_audit_adapter.py \
    --base-endpoint http://<linux-bridge-ipv4>:8000 \
    --token-file <secret-file> \
    --package-path <staging>/<dataset>-package.tar.zst \
    …identity flags… \
    --dataset-id medium|p2-r6-synthetic-w2-medium-shape \
    --dataset-kind w1|w2 \
    --cleanup-compose --compose-file <candidate>/vnext/deploy/compose.yaml \
    --output /tmp/s10-6-results/<run>.json
```

整条 live 经 `alpine:3.20` nsenter 以 host root 执行（读 0750 staging + token
chown）。helper image 不是 candidate image。

| dataset | project | container_id (12) | nsenter |
| --- | --- | --- | --- |
| W1 medium | `gateway-p2r6-s7-s10-w1-abd168be215e` | `79f764f44ab0` | 2026-08-17T05:01:54Z–05:03:45Z，WRAPPER_EXIT=1 |
| W2 | `gateway-p2r6-s7-s10-w2-676c4d8b976a` | `b6f6f8dcee54` | 2026-08-17T05:06:41Z–05:10:19Z，WRAPPER_EXIT=1 |

## Hard gates

### Proven on both attempts (identity / inspect / disk)

- package size/SHA 与 package-derived `canonicalization_manifest_digest` 与 expected 一致
- 运行中 image ID + 四 labels 与 S10-4 seal 一致
- 无 host port；`git_status_porcelain: empty`；`host_runtime_fallback: false`；`http_retry: false`
- disk admission/headroom：before/after `admitted=1`；`query_temp_count=0`
- settings 写死 `verification_policy=FULL_SCAN`、`unknown_type_policy=REJECT`（这是 adapter 配置，不是 import 完成证据）

### Not proven — leftover JSON omitted public facts

两次 sanitized JSON 都是：

```text
status: FAILED
container_pass: not_claimed
error: compose resources remain after cleanup
final_inventory: containers=0 networks=0 volumes=1
compose_removed: true
w1_w2_consumed: true
```

JSON **没有** `public_counts`、`timings`、`w2_band`、`resource_peaks`。因此不能把
`SUCCEEDED` / 完成态 `FULL_SCAN` / `unknown=0` / `lossy=0` / row count / W2 replay
band 写成已证明。不得用代码路径推断替代这些字段。

S6 对照不记为 advisory pass（本步无 timings）。不发明百分比 SLO。

### Adapter defect

reviewed adapter `cleanup_compose` 执行：

```text
docker compose -f … -p … --profile p2-r2 down --remove-orphans
```

**没有** `-v`。production `compose.yaml` 声明 named volume `repository-service-data`。
`down` 之后该 volume 仍带 `com.docker.compose.project` label，`project_inventory`
计 `volumes=1`，随后 fail-closed。这是 adapter 与「`--cleanup-compose` 后 inventory
必须为 0 才能 `container_pass`」之间的缺陷，不是生产 Service 行为，也不是传输/权限失败。

未改 adapter。未把 operator 事后 `docker volume rm` 写成 adapter pass。未换
`--external-cleanup-receipt` 重跑当 pass。

## Repair ledger

```yaml
first_failure: adapter leftover named volume after compose down without -v
environment_repairs: none
source_or_build_input_repairs: none
adapter_bytes_changed: no
repairs: none
repairs_to_production_or_tests: none
source_or_build_input_changed: no
container_boundary_touched: no
retry_as_pass: no
new_attempt_after_adapter_fix: required
```

## Cleanup inventory

adapter `finally` 已 `compose down`（容器/网络为 0）。operator 在 fail-closed 之后删除
残留 named volume、staging 包、`/tmp` 传输副本、token、work roots、throwaway venv。
adapter 源码仍保留在 local audit root（未改字节）。

命令结束后（gate-host）：

```text
gateway-p2r6 containers=0 networks=0 volumes=0
staging_packages: removed
tmp_s10-6_transfer_work_results_scripts: removed
git_status_porcelain: empty (local and remote candidate)
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
identity: unchanged from S10-4/S10-5
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
```

远端 candidate 内 gitignore 的 `.venv` 仍是 S10-5 root `uv run` 遗留，未进入 porcelain，
本步 `UV_PROJECT_ENVIRONMENT` 在 `/tmp`。未删 S10-5 `.venv`。

## External audit artifacts

```text
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/artifacts/s10-6
failed_attempts_preserved: attempt-1-w1, attempt-1-w2
log_copied_to_docs_worktree: no
candidate_wrote_log: no
```

```text
5f15afb7e8f37cf24cc4f51fbc289b88069f3bcd251fe38f711f100ad16d11d1  attempt-1-w1/w1-medium.json
71193af8e91e8ec99c91f46bdc1bbf244f561bf934a5a179ef6358a853d389fa  attempt-1-w1/w1-run.log
987e8ec2a694201d3cb6cf2d8da4535ee3d2a8e725ef20da84b40c6663a15a04  attempt-1-w1/compose-meta.json
af4fb73c75334d8b97ee4f4c26daf644b1a16cb21928d1aabb246d6f3929702e  attempt-1-w2/w2.json
0c545883b26ae4c2b67daad9ff0ae1803f6f84838b88b0ec249dde39ddaa845c  attempt-1-w2/w2-run.log
d40eb8f73698858aeda7611f2365bd0aa0daaefe4ea8bad24a44a0b6d90cfa0b  attempt-1-w2/compose-meta.json
8299be5d0f8e412ed34e08f174b81377daa16925af7acf95d0e5d15434d9682c  s10-6-run-dataset.sh
3eefb7f637614bec046573cfe5f46311b592ad9213086d70060cdfcb91bb629d  s10-6-start-compose.py
6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf  adapter/s10_w1_w2_audit_adapter.py
```

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no (S10-4 final image reused; IDs unchanged)
Reason: S10-6 W1/W2 live adapter fail-closed on leftover named volume; adapter defect
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10-6 W1/W2 production pass after adapter repair+rereview; S10-7/S10-8 Candidate A W0/v8 formal
Required execution point: S10-2 adapter repair, S10-3 rereview, then repeat S10-6 on unchanged identity
```

本步不改变 `container_validated_code_sha`。

## Exit

```yaml
s10_6_status: fail
failure_class: adapter_defect
w1_medium_production_repeat: fail
w2_production_repeat: fail
container_pass: not_claimed
retry_as_pass: no
identity_unchanged: yes
adapter_sha_unchanged: yes
zero_owned_gateway_p2r6_residual: yes
packages_removed_from_staging: yes
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-2 then S10-3 (adapter leftover-volume cleanup), then repeat S10-6; do not start S10-7
```

S10-6 在 adapter 修复并经 S10-3 零 finding rereview 之前不得重跑当 pass。新 attempt
必须新 ID，保留本 attempt-1。身份与 adapter SHA 若在修复中变化，按计划作废后续门禁并
从对应 owner 重入。

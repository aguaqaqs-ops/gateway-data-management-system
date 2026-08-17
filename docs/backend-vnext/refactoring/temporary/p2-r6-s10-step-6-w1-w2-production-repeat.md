# P2-R6-S10 Step 6 — W1 medium and W2 production repeat

状态：`pass`（仅 S10-6 W1/W2 production repeat；attempt-2；不授予 v8、S10 exit 或 Phase 2）

日期：2026-08-17

本记录在 S10-5 身份与 final image ID 不变、S10-2 attempt-3 / S10-3 rerun-2 放行
adapter SHA `af672fa0…b41150` 之后，以 **新 attempt ID（attempt-2）** 重跑 W1
`medium` 与 synthetic W2。两次 live 均为 `status=SUCCEEDED`、
`container_pass=pass`、`--cleanup-compose` 后 inventory 全 0。attempt-1 leftover
失败记录与 `artifacts/s10-6/attempt-1-*` **未覆盖**。未修改 candidate、Compose
或 image。本会话不进入 S10-7。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §8
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.4
S10-5：[p2-r6-s10-step-5-no-ignore-compose.md](p2-r6-s10-step-5-no-ignore-compose.md)
S10-2 attempt-3：[p2-r6-s10-step-2-audit-adapter.md](p2-r6-s10-step-2-audit-adapter.md)
S10-3 rerun-2：[p2-r6-s10-audit-adapter-review-rerun-2.md](p2-r6-s10-audit-adapter-review-rerun-2.md)
Adapter 契约：`/root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/command-contract.md`
attempt-1 失败（保留）：[p2-r6-s10-step-6-w1-w2-production-repeat-attempt-1.md](p2-r6-s10-step-6-w1-w2-production-repeat-attempt-1.md)

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
adapter_sha256: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
prior_adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
attempt_id: attempt-2
prior_attempt: attempt-1 preserved fail
worktree_clean_before: yes
worktree_clean_after: yes
production_code_changed: no
test_code_changed: no
docker_or_compose_changed: no
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
w1_w2_consumed: true
container_pass: pass
s10_6_status: pass
phase_2_complete: no
```

远端 `/home/issac/gateway-s10-candidate-2ef88427` 与本地
`/root/gateway-s9-candidate-2ef88427` 在命令前后 `git status --porcelain` 均为空。
`:p2-r6-final` 与 `:local` 仍指向 `sha256:4b8f88ed…2a2e4a2be6`。daemon 仍是
`Name=arch ID=dc91db82-3d49-41a4-a63c-f23dda721890`。descriptor 祖先
`image_id sha256:57e2ec06…` **不是**本步 expected image。

attempt-1 失败记录 SHA-256 仍为 `6acc1f584d06939f93ba4b7f6c7cc53c2306c0b42fb9c8ea8645046b6993b1f2`
（现位于 `-attempt-1.md`）。attempt-1 JSON 哈希未变。

## Transfer (hash-verified)

只传三份批准对象 + reviewed adapter（attempt-3 SHA）。issac 不能写 `root:root 0750`
staging；scp 到 `/tmp/s10-6-a2-transfer`，再 `docker run --user 0` `install -m 0640`
进 `/var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z/staging`。
local / remote tmp / staging 的 size+SHA 一致后才用。

| object | bytes | sha256 |
| --- | ---: | --- |
| W1 `medium-package.tar.zst` | 2081228 | `3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e` |
| W1 manifest | — | `sha256:73dd240b234b26ec006aa78a5e73f2ac9a5105eabe9e9f5dd19a82c858d6b26c` |
| W2 `w2-package.tar.zst` | 8301271 | `6cac7852d1174c126c182e82010b0ff9d4043e51826b8043103360c8e49f6d10` |
| W2 manifest | — | `sha256:895732a5bbfcc406b9a5edab24ff742186fb5f268ce68ca5774a798b2bd2b32f` |
| descriptor.yaml | 2682 | `416eb412d7e9ec389bb0dffae5511b016937ae1e29790cc3e26b549eb772205f` |
| adapter `.py` | — | `af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150` |

staging 文件 `0640 root:root`。用后已删。

## Isolated Compose + adapter invocation

每个 dataset 一个 scoped project（harness `allocate_compose_resources`，前缀
`gateway-p2r6-s7-`）。throwaway `/tmp/s10-6-a2-start-compose.py` 只调用已有
`start_p2r2_service`。`UV_PROJECT_ENVIRONMENT` 与 `PYTHONPYCACHEPREFIX` 在
`/tmp/s10-6-a2-*`，candidate 外。token `0400`，chown `100/101`。无 host port。
gate-host endpoint 两次均为 Linux-bridge IPv4 `http://172.18.0.2:8000`。运行中
container image ID 两次都等于 `sha256:4b8f88ed…2a2e4a2be6`。四 labels 与 seal 一致。

Canonical adapter（`--cleanup-compose`，token 只用 `--token-file`，adapter SHA
fail-closed 校验为 `af672fa0…`）：

```bash
uv run --directory <candidate-root>/vnext/repository_client --group dev \
  python /tmp/s10-6-a2-transfer/s10_w1_w2_audit_adapter.py \
    --base-endpoint http://<linux-bridge-ipv4>:8000 \
    --token-file <secret-file> \
    --cleanup-compose --compose-file <candidate>/vnext/deploy/compose.yaml \
    --dataset-id medium|p2-r6-synthetic-w2-medium-shape \
    --dataset-kind w1|w2 \
    --output /tmp/s10-6-a2-results/<run>.json
```

整条 live 经 `alpine:3.20` nsenter 以 host root 执行。helper image 不是 candidate image。

| dataset | project | container_id (12) | nsenter | WRAPPER_EXIT |
| --- | --- | --- | --- | ---: |
| W1 medium | `gateway-p2r6-s7-s10-w1-3097a7f875f3` | `1f12bb8cc77a` | 2026-08-17T06:19:49Z–06:21:37Z | 0 |
| W2 | `gateway-p2r6-s7-s10-w2-ff0ea8910354` | `80f9bbd3c887` | 2026-08-17T06:22:22Z–06:26:02Z | 0 |

## Hard gates (attempt-2)

两次 sanitized JSON 均为 `mode=live`、`status=SUCCEEDED`、`container_pass=pass`、
`git_status_porcelain=empty`、`no_host_port=true`、`host_runtime_fallback`/`http_retry`
未作为成功路径使用。

| gate | W1 medium | W2 |
| --- | --- | --- |
| package bytes/SHA | 2081228 / `3e705e35…055e` | 8301271 / `6cac7852…9f6d10` |
| manifest digest | `sha256:73dd240b…d6b26c` | `sha256:895732a5…d2b32f` |
| running image + 4 labels | match S10-4 seal | match S10-4 seal |
| verification / unknown policy | FULL_SCAN / REJECT | FULL_SCAN / REJECT |
| catalog_status | pass | pass |
| table_count / streamed_table | 199 / `device_model_table` | 199 / `device_model_table` |
| streamed_rows | 66759 | 267036 |
| unknown / lossy | 0 / 0 | 0 / 0 |
| replay.sql bytes | 49323598 | 201681690 (192.337 MiB) |
| W2 band 180–199 MiB and `< 200 MiB` | n/a (`in_band=null`) | `in_band=true` `below_cap=true` |
| disk admission before/after | admitted=1 | admitted=1 |
| query_temp_count | 0 | 0 |
| final_inventory | containers=0 networks=0 **volumes=0** | containers=0 networks=0 **volumes=0** |
| compose_removed | true | true |

W2 replay `201681690` 落在 adapter 带 `188743680–208666624` 且 cap `209715200`。

## Advisory S6 comparison (not SLO)

不发明百分比阈值。

| | S6 reference | this attempt-2 |
| --- | --- | --- |
| medium elapsed / import | HTTP ~136s / import ~90s | elapsed 94.081s / import 56.954s |
| W2 elapsed / import | HTTP total ~538s / import ~411s | elapsed 210.303s / import 153.020s |
| W2 peak | RSS 635248 KiB | peak_container_memory_bytes 1035888230 (~1011601 KiB) |
| medium peak | — | 539702067 bytes |

W1 timings：upload 0.013s、catalog 13.792s、row_stream 19.901s。
W2 timings：upload 0.022s、catalog 14.387s、row_stream 38.412s。
无 timeout/OOM。

## Repair ledger

```yaml
first_failure: attempt-1 leftover named volume (adapter defect; preserved)
environment_repairs: none
source_or_build_input_repairs: none
adapter_bytes_changed_this_attempt: no
adapter_used: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
repairs_to_production_or_tests: none
retry_as_pass: no
new_attempt_id: attempt-2
```

attempt-1 不是本 attempt 的 retry-as-pass；本步使用经 S10-3 放行的新 adapter SHA
与新 attempt ID。

## Cleanup inventory

adapter `finally` 做 `compose down -v --remove-orphans`。operator 再删 staging 包、
`/tmp/s10-6-a2-*` 传输副本、token、work roots、throwaway venv。adapter 源码仍在
local audit root。

命令结束后（gate-host）：

```text
gateway-p2r6 containers=0 networks=0 volumes=0
staging_packages: removed
tmp_s10-6-a2_transfer_work_results_scripts: removed
git_status_porcelain: empty (local and remote candidate)
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
identity: unchanged from S10-4/S10-5
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
adapter_sha256: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
attempt-1 artifacts: preserved
```

## External audit artifacts

```text
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/artifacts/s10-6
failed_attempts_preserved: attempt-1-w1, attempt-1-w2
pass_attempt: attempt-2-w1, attempt-2-w2
log_copied_to_docs_worktree: no
candidate_wrote_log: no
```

```text
5f15afb7e8f37cf24cc4f51fbc289b88069f3bcd251fe38f711f100ad16d11d1  attempt-1-w1/w1-medium.json
af4fb73c75334d8b97ee4f4c26daf644b1a16cb21928d1aabb246d6f3929702e  attempt-1-w2/w2.json
6acc1f584d06939f93ba4b7f6c7cc53c2306c0b42fb9c8ea8645046b6993b1f2  p2-r6-s10-step-6-w1-w2-production-repeat-attempt-1.md
365712104a784579be1d439c438a23eaf610fbb06bdba818a1dab42a2944a573  attempt-2-w1/w1-medium.json
badf8346fe874084f49361481321400543832712ec89343b8f02c9a3b48dad7d  attempt-2-w1/w1-run.log
2bff90873e0b1dd40ee988e865a22c240fc52df6d2fa14984047682a54074cc3  attempt-2-w1/compose-meta.json
0f18233493b397d1da49eb923591ab47c2873ca23c0a4d1516eaa34882c7a017  attempt-2-w2/w2.json
4d2961ee24699a93f153c04d707cf744e1574f0a9bde0c009e944510bb5ab92d  attempt-2-w2/w2-run.log
6c1c2c3a5b1eb7022f665fe2f790f52ec25ab4806d243c8bcf4bdf1f6957301d  attempt-2-w2/compose-meta.json
636ccb7d6443eba4d88d2f408ca39bac5c5ae8636931f4b69488ccae09eb303b  attempt-2-s10-6-run-dataset.sh
af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150  adapter/s10_w1_w2_audit_adapter.py
```

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no (S10-4 final image reused; IDs unchanged)
Reason: S10-6 attempt-2 W1/W2 live adapter pass on unchanged final Service identity
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred pending S10-7/S10-8
Deferred gates/nodeids: S10-7/S10-8 Candidate A W0 smoke and v8 formal --runs 5
Required execution point: S10-7 in a new conversation on this unchanged identity
```

本步不单独改变 `container_validated_code_sha`（仍 deferred 到 W0/v8 完成）。

## Exit

```yaml
s10_6_status: pass
attempt_id: attempt-2
w1_medium_production_repeat: pass
w2_production_repeat: pass
container_pass: pass
prior_attempt_1: preserved fail
retry_as_pass: no
identity_unchanged: yes
adapter_sha256: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
zero_owned_gateway_p2r6_residual: yes
packages_removed_from_staging: yes
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-7 Candidate A W0 target smoke in a new conversation
```

下一步 S10-7 必须新对话。本记录不构成 v8 formal、S10 seal 或 Phase 2 completion。

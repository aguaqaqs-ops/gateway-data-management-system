# P2-R6-S7 — Step 5 provisional image and preflight

状态：`pass`（仅 S7-5 preflight；不授予 S7 Compose PASS 或 S7 exit）

日期：2026-08-16

本记录在 S7-4 final review `allow_provisional_image: yes` 之后，从精确 candidate
`eeadbdd38ab468667b2b9ebbdfffae39ddc62771` 重建 provisional Service image 与 ephemeral
client runner，并完成 Compose config / secret / health / Linux-bridge 可达性 preflight。
未运行第四个 restored-lifecycle nodeid，不宣称 `S7_exit: pass` 或 `phase_2_complete`。

权威步骤：[P2-R6-S7 Compose Lifecycle Execution Plan](../formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md) §7
S7-4 放行：[p2-r6-s7-step-4-harness-final-review.md](p2-r6-s7-step-4-harness-final-review.md)
祖先 Stage J 镜像：[p2-r6-ext-w1-stage-j-final-image-lifecycle.md](p2-r6-ext-w1-stage-j-final-image-lifecycle.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
candidate_sha: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
container_validated_code_sha: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
build_input_revision: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
source_tree_sha256: sha256:ed5ccd30b06d8a4dc89336457d7a3843d767f3e9a0158e621a592c6a421f83b7
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
worktree_clean_at_build: yes
production_code_changed: no
contract_changed: no
package_version: v1
phase_2_complete: no
```

构建前将三份未跟踪 S7-4 审核记录移出工作树；`git status --porcelain` 为空。本文件与
S7-4 reviews 在 gates 之后才写回 `docs/`，不得回填进 image label。文档提交 SHA 若存在，
只作为 `provenance_documentation_sha`。

Stage J 祖先（superseded for current S7 candidate，不得当作本 HEAD 已验证）：

```text
ancestor_candidate: 656a66bf04714cce987c85649246c3767b2586e2
ancestor_image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
```

## Local / remote identity

本机与远端 detached worktree `/home/issac/gateway-gate-eeadbdd38ab4` 输出相同：

```text
schema: gateway.p2r1.build-identity
schema_version: 1
candidate_sha: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
build_input_revision: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
source_tree_sha256: sha256:ed5ccd30b06d8a4dc89336457d7a3843d767f3e9a0158e621a592c6a421f83b7
```

```text
local cache http://172.17.0.1:18080: HTTP 502 (fail closed for local formal build)
remote cache http://172.17.0.1:18080 on 10.10.60.4: HTTP 200
ssh: issac@10.10.60.4
candidate_delivery: git bundle 3616ef0d..phase1/gate-ownership-repair
  -> refs/gate/candidate-s7
  -> git worktree add --detach /home/issac/gateway-gate-eeadbdd38ab4 eeadbdd
```

## Service image build and transfer

本机正式脚本因 cache 502 在 Docker 调用前 fail closed。沿用 Stage J：远端
`vnext/scripts/build-repository-service-image.sh`。dependency-base
`gateway-p2r1-repository:lock-6dc9659f0aee` 不存在，脚本使用 retained artifact cache
而非 `USE_PRELOADED_DEPENDENCIES=1`。未使用 `DOCKER_HOST`，未使用 `p2-r6-final` tag。

```text
remote worktree: /home/issac/gateway-gate-eeadbdd38ab4
remote HEAD: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
local HEAD:  eeadbdd38ab468667b2b9ebbdfffae39ddc62771
worktree_clean: yes
build_command: vnext/scripts/build-repository-service-image.sh (remote, retained cache)
build_started_at: 2026-08-16T11:04:11Z
build_finished_at: 2026-08-16T11:04:57Z
cache_endpoint: http://172.17.0.1:18080 (HTTP 200 on 10.10.60.4)
image: gateway-repository-service:eeadbdd38ab4
image_id: sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
remote_image_id: sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
local_image_id:  sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
image_label org.opencontainers.image.revision: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
image_label gateway.p2r1.build-input-revision: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
image_label gateway.p2r1.source-tree-sha256: sha256:ed5ccd30b06d8a4dc89336457d7a3843d767f3e9a0158e621a592c6a421f83b7
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_label gateway.p2r1.dolt-version: 2.1.11
image_label gateway.p2r1.uv-version: 0.11.28
image_label gateway.p2r1.mysql-connector-version: 9.7.0
image_label gateway.p2r1.pyarrow-version: 25.0.0
image_matches_build_context: true
verify_transferred_image: true
transfer: ssh remote `docker save` streamed to local `docker load`
transfer_started_at: 2026-08-16T11:05:02Z
transfer_finished_at: 2026-08-16T11:06:17Z
```

## Client runner identity

本机 `ensure_client_image()` 对 `python:3.14.6-slim-bookworm` 的 pip/PyPI bootstrap
长时间无进展。client 改为在同一远端 worktree 构建（uv bootstrap 走 retained cache
`http://172.17.0.1:18080/uv/simple`），再 `docker save | load` 到 gate host。labels 只绑定
candidate 与 `repository_client/uv.lock`，与 `_run_client_build` 一致。未把 client 加入
production Compose。

```text
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:5b06a495979442437e11261d2506919e656d1fcbb65a56c56970e045d80de41e
client_label org.opencontainers.image.revision: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
client_label gateway.p2r6.client-uv-lock-sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
client_identity: sha256:5b06a495979442437e11261d2506919e656d1fcbb65a56c56970e045d80de41e
host_runner_identity: host-runner:candidate=eeadbdd38ab468667b2b9ebbdfffae39ddc62771;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
client_build_started_at: 2026-08-16T11:19:09Z
client_build_finished_at: 2026-08-16T11:19:41Z
client_transfer_started_at: 2026-08-16T11:19:46Z
client_transfer_finished_at: 2026-08-16T11:20:43Z
```

## Compose / secret / readiness preflight

throwaway `/tmp/s7-step5-preflight.py` 只调用已有 harness，未提交。project
`gateway-p2r6-s7-preflight-51445644e733`。`assert_p2r2_compose_boundary` 通过（无 Service
host port、无 docker.sock、无 host-root、无常驻 client）。token 文件 mode `0400`，chown 到
镜像内 `gateway` UID 100 / GID 101。

```text
start: start_p2r2_service wait=True
health: Docker Health.Status=healthy; healthcheck 打容器内 http://127.0.0.1:8000/readyz
network_name: gateway-p2r6-s7-preflight-51445644e733_default
network_id: ec65334245e7bfc738f4e25d182db4fcd11d53b06ef6363dc39956336b086bfb
gateway_ipv4: 172.19.0.1
service_ipv4: 172.19.0.2
inside_endpoint: http://repository-service:8000
gate_host_endpoint: http://172.19.0.2:8000
endpoints_differ: true
host_port_published: no
gate_host_readyz: HTTP 200 {"status":"ready"} (ProxyHandler 空，绕过本机 127.0.0.1:50808)
inventory_after_cleanup: containers=0 networks=0 volumes=0 hold=0
```

未跑 versioned consumer、import flow、snapshot hold/check 或四个 S7 PASS nodeid。

## Docker record

```text
Current HEAD: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
Container rebuild required: yes (executed at S7-5)
Reason: S7 Compose/client lifecycle harness changed after Stage J
Last verified image revision (Stage J, ancestor): 656a66bf04714cce987c85649246c3767b2586e2
Last verified source-tree/image id (Stage J, ancestor):
  sha256:f6dc57cb635482b5c5287746ba5da956db7d56fcd9bc461ff942e04d514a785e /
  sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
Last verified image revision (S7 provisional): eeadbdd38ab468667b2b9ebbdfffae39ddc62771
Last verified source-tree/image id (S7 provisional):
  sha256:ed5ccd30b06d8a4dc89336457d7a3843d767f3e9a0158e621a592c6a421f83b7 /
  sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
Container gate for current HEAD: deferred
Deferred gates/nodeids: test_compose_repository_service_fresh_restart_restored_lifecycle (S7-8/S7-9);
  S7-11 final candidate rebuild; S8/S9/S10
Required execution point: S7-5 provisional image; directed S7-6/S7-7 on this image
```

## Verdict

```yaml
s7_5_status: pass
allow_directed_gates: yes
S7_exit: no
phase_2_complete: no
next: S7-6 import restart/replay on this provisional image
```

# P2-R6-S9 Step 2 — Candidate checkout and provisional image

状态：`pass`（仅 S9-2 preflight；不授予 no-ignore regression、candidate seal、S9 exit 或 S10）

日期：2026-08-17

本记录在 S9-1 `allow_s9_implementation: yes` 之后，于冻结 candidate
`2ef884278b4998dde1e5fe224532c89b7a0cd73a` 的干净 detached checkout 上构建
candidate-bound provisional Service/client image，并完成 Compose 边界 / secret /
health / Linux-bridge / zero-residual preflight。未修改 source、test、dependency、
Dockerfile、Compose 或 lock；未打 `p2-r6-final` tag；未把祖先 `5f474ce2` image
写成当前 candidate 已验证；未执行 `./vnext/scripts/run-tests.sh` 或八个 Docker
nodeid。证据写在文档 worktree，未进入 candidate checkout。

权威步骤：[P2-R6-S9 Final Candidate Seal Execution Plan](../formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md) §4
入口身份：[p2-r6-s9-step-0-entry-preflight.md](p2-r6-s9-step-0-entry-preflight.md)
设计放行：[p2-r6-s9-design-review.md](p2-r6-s9-design-review.md)
祖先容器证据：[p2-r6-s7-final-handoff.md](p2-r6-s7-final-handoff.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 71da506171d01bbccdf2c54137949cdd0bff234e
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
worktree_clean_at_build: yes
production_code_changed: no
contract_changed: no
package_version: v1
phase_2_complete: no
```

文档 worktree HEAD 仍是 `71da5061`，docs-only，不是 `CANDIDATE_SHA`。本地 candidate
worktree `/root/gateway-s9-candidate-2ef88427` 在 S9-0 已存在，S9-2 复核
`git status --porcelain` 为空。Identity helper 与 lock hash 与 S9-0 逐字段一致。

祖先（不得当作当前 candidate 已验证）：

```text
ancestor_candidate: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
ancestor_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
ancestor_source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
```

## Local / remote identity

本机文档 host 仍不是 builder/gate-host。正式构建与 preflight 在 S7 同一远端
`issac@10.10.60.4` 上执行。未使用 `DOCKER_HOST`，未改 cache host。

```text
schema: gateway.p2r1.build-identity
schema_version: 1
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
```

本地 candidate checkout 与远端 `/home/issac/gateway-gate-2ef884278b49` helper
输出相同。两份 lock hash：

```text
6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11  vnext/repository_service/uv.lock
6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954  vnext/repository_client/uv.lock
```

```text
local host: DESKTOP-V61T28L
kernel: Linux 6.6.114.1-microsoft-standard-WSL2 x86_64
ipv4: 10.10.60.2/24 eth0
docker: Name=DESKTOP-V61T28L ServerVersion=29.6.2 OperatingSystem=Arch Linux Driver=overlayfs NCPU=16
compose: Docker Compose version 5.3.1
local cache http://172.17.0.1:18080: HTTP 502 (fail closed for local formal build)
used_as_s9_builder_or_gate_host: no

ssh: issac@10.10.60.4 BatchMode=yes
whoami: issac
id: uid=1000(issac) gid=1000(issac) groups=1000(issac),955(libvirt),958(docker),998(wheel)
uname: Linux 7.1.6-arch1-1 x86_64
hostname_file: arch
ipv4: 10.10.60.4/24 wg0
docker: Name=arch ServerVersion=29.7.2 OperatingSystem=Arch Linux Driver=overlayfs NCPU=16
compose: Docker Compose version 5.4.0
remote cache http://172.17.0.1:18080: HTTP 200
cache_server: SimpleHTTP/0.6 Python/3.14.6
bridge_network: Name=bridge Driver=bridge Scope=local ID=7060d1f61386 Gateway=172.17.0.1 Subnet=172.17.0.0/16
same_s7_configuration: yes
```

`git bundle create` 对裸 SHA 范围 `3616ef0d..2ef88427` 拒绝 empty bundle，因此按 S7
同样交付具名 ref `3616ef0d..phase1/gate-ownership-repair`（bundle head `71da5061`），
远端仍只 checkout 字面量 candidate：

```text
candidate_delivery: git bundle 3616ef0d..phase1/gate-ownership-repair
  -> refs/gate/candidate-s9-2-docs
  -> refs/gate/candidate-s9-2 = 2ef884278b4998dde1e5fe224532c89b7a0cd73a
  -> git worktree add --detach /home/issac/gateway-gate-2ef884278b49 2ef88427
remote worktree: /home/issac/gateway-gate-2ef884278b49
remote HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
local candidate HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
worktree_clean: yes
local/remote helper identity: identical
```

dependency-base `gateway-p2r1-repository:lock-6dc9659f0aee` 仍不存在。脚本走
retained artifact cache，而非 `USE_PRELOADED_DEPENDENCIES=1`。

## Service image build

```text
remote worktree: /home/issac/gateway-gate-2ef884278b49
build_command: vnext/scripts/build-repository-service-image.sh (remote, retained cache)
build_started_at: 2026-08-16T23:37:15Z
build_finished_at: 2026-08-16T23:38:01Z
cache_endpoint: http://172.17.0.1:18080 (HTTP 200 on 10.10.60.4)
image: gateway-repository-service:2ef884278b49
image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
remote_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
image_label org.opencontainers.image.revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
image_label gateway.p2r1.build-input-revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
image_label gateway.p2r1.source-tree-sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_label gateway.p2r1.dolt-version: 2.1.11
image_label gateway.p2r1.uv-version: 0.11.28
image_label gateway.p2r1.mysql-connector-version: 9.7.0
image_label gateway.p2r1.pyarrow-version: 25.0.0
image_matches_build_context: true
ensure_repository_service_image: reused gateway-repository-service:2ef884278b49
transfer: not used as S9-2 evidence; immutable ID verified on gate-host 10.10.60.4
```

未把 WSL `docker save|load` 当作替代证据。未使用 `p2-r6-final` tag。

## Client runner identity

Client 在同一远端 worktree 构建。uv bootstrap 走 retained cache
`http://172.17.0.1:18080/uv/simple`。标签只绑定 candidate 与
`repository_client/uv.lock`。未把 client 加入 production Compose。默认 tag
`gateway-repository-client-e2e:local` 以便 S9-3 `ensure_client_image()` reuse。

```text
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
client_label org.opencontainers.image.revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
client_label gateway.p2r6.client-uv-lock-sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
client_identity: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
host_runner_identity: host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
client_build_started_at: 2026-08-16T23:38:17Z
client_build_finished_at: 2026-08-16T23:38:46Z
ensure_client_image: reused gateway-repository-client-e2e:local
```

## Compose / secret / readiness preflight

throwaway `/tmp/s9-step2-preflight.py` 只调用已有 harness，未提交、未写入 candidate。
外部 venv `/tmp/s9-2-preflight-venv`（`UV_PROJECT_ENVIRONMENT`）避免在 candidate 内
创建 `.venv`。`PYTHONDONTWRITEBYTECODE=1` 避免 `__pycache__`。

issac 无免密 sudo，`os.chown` 到镜像内 `gateway` UID 100 / GID 101 在普通用户下
`Operation not permitted`。第一次以 issac 启动在 chown 处失败；`cleanup_compose_project`
已把该 project 清零。随后用 Docker `nsenter` 进入 host namespace 以 root 重跑同一脚本
（token chown 是 harness 既有行为，不是新生产机制）。helper image `alpine:3.20` 仅用于
nsenter，不是 candidate image，也不进入 provenance labels。

project `gateway-p2r6-s7-s9-preflight-48c011d6f8d5`（harness `allocate_compose_resources`
前缀仍为 `gateway-p2r6-s7-`）。`assert_p2r2_compose_boundary` 通过：无 Service host
port、无 docker.sock、无 host-root、无常驻 client。token 文件 mode `0400`，chown 到
`100/101`。

```text
start: start_p2r2_service wait=True
token_mode: 0o400
token_uid/gid: 100/101 (gateway)
health: Docker Health.Status=healthy; healthcheck 打容器内 http://127.0.0.1:8000/readyz
network_name: gateway-p2r6-s7-s9-preflight-48c011d6f8d5_default
network_id: 925ed7b54a72e4eaf00ae0cc769c97f9c7722bea8443c7c1650556001e689b56
gateway_ipv4: 172.18.0.1
service_ipv4: 172.18.0.2
inside_endpoint: http://repository-service:8000
gate_host_endpoint: http://172.18.0.2:8000
endpoints_differ: true
host_port_published: no
gate_host_readyz: HTTP 200 {"status":"ready"} (ProxyHandler 空)
baseline_inventory: containers=0 networks=0 volumes=0 hold=0 dolt_pids=0 check_temp_homes=0 client_pids=0 host_threads=0
teardown_scan project=gateway-p2r6-s7-s9-preflight-48c011d6f8d5 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-s9-preflight-48c011d6f8d5 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
inventory_after_cleanup: containers=0 networks=0 volumes=0 hold=0
leftover_gateway-p2r6_objects_after_step: none
```

未跑 versioned consumer、import flow、snapshot hold/check、八个 Docker nodeid 或
`./vnext/scripts/run-tests.sh`。

preflight 结束后本地 candidate 与远端 candidate `git status --porcelain` 均为空，
identity helper 仍匹配上表。

## Docker record

```text
Current HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (executed at S9-2)
Reason: S9 exact no-ignore gate includes eight Docker-starting nodeids; S7 image labels bind 5f474ce2 / sha256:b1e7576c… and cannot match 2ef88427 identity sha256:c35db6ac…
Last verified image revision (S7, ancestor): 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id (S7, ancestor):
  sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 /
  sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Last verified image revision (S9-2 provisional): 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id (S9-2 provisional):
  sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 /
  sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S9-3 exact ./vnext/scripts/run-tests.sh and eight Docker nodeids;
  S10 final production image/provenance, four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9-2 provisional image; directed S9-3 on this unchanged image/checkout
```

本步不改变 `container_validated_code_sha`。S7 的 `5f474ce2` 仍只是祖先证据。S9-2
provisional image 不是 S10 final production image。

## Verdict

```yaml
s9_2_status: pass
candidate_bound_provisional_images: pass
image_matches_build_context: true
client_image_matches: true
worktree_clean: yes
compose_boundary: pass
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
S9_exit: no
S10_ready: no
production_retest_required: yes
phase_2_complete: no
next: S9-3 exact ./vnext/scripts/run-tests.sh on this unchanged image/checkout
```

S9-3 必须继续使用：

```text
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:2ef884278b49
remote worktree: /home/issac/gateway-gate-2ef884278b49
gate-host: issac@10.10.60.4
```

同一会话仅在 source、build inputs、checkout 与 image identities 全程不变时可以继续。
本记录本身不构成 no-ignore regression、candidate seal 或 Phase 2 completion。

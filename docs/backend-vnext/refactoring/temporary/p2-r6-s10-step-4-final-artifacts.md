# P2-R6-S10 Step 4 — Final Service/Client artifacts and provenance

状态：`pass`（仅 S10-4 final artifact identity；不授予 no-ignore、W1/W2、v8、S10 exit 或 Phase 2）

日期：2026-08-17

本记录在 S10-3 rereview `allow_w1_w2_execution: yes` 之后，于冻结 candidate
`2ef884278b4998dde1e5fe224532c89b7a0cd73a` 的干净 detached checkout 上构建
`gateway-repository-service:p2-r6-final`，把 `:local` 绑定到同一 immutable ID，requalify
candidate-bound Client，并记录 same-daemon `docker save` archive 哈希与 Compose 边界 /
资源基线。未修改 source、test、dependency、Dockerfile、Compose 或 lock；未执行
`./vnext/scripts/run-tests.sh`、八个 Docker nodeid、W1/W2 或 v8；未对 same-daemon 做
`docker load`，也未把 archive 传到 WSL。证据写在文档 worktree 与 external audit root，
未进入 candidate checkout。

权威步骤：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §6
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.2
入口身份：[p2-r6-s10-step-0-entry-preflight.md](p2-r6-s10-step-0-entry-preflight.md)
设计放行：[p2-r6-s10-design-review-rerun.md](p2-r6-s10-design-review-rerun.md)
adapter 放行：[p2-r6-s10-audit-adapter-review-rerun.md](p2-r6-s10-audit-adapter-review-rerun.md)

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
worktree_clean_at_build: yes
production_code_changed: no
contract_changed: no
adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
package_transferred: no
w1_w2_consumed: no
package_version: v1
phase_2_complete: no
```

文档 worktree HEAD 仍是 `0f9536c2`，docs-only，不是 `CANDIDATE_SHA`。本地 candidate
`/root/gateway-s9-candidate-2ef88427` 与远端 `/home/issac/gateway-s10-candidate-2ef88427`
在构建前与构建后 `git status --porcelain` 均为空。Identity helper 与 lock hash 与
S9 seal / S10-0 逐字段一致。

S9 provisional（本步执行 canonical 构建后 ID 相同，现同时作为 `p2-r6-final`；不得把
未执行 S10-4 构建的 S9 tag 单独写成 final）：

```text
s9_provisional_service: gateway-repository-service:2ef884278b49
s9_provisional_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
image_id_equals_s9_provisional: yes
```

祖先（不得当作当前 candidate 已验证）：

```text
ancestor_candidate: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
ancestor_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
ancestor_source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
```

## Local / remote identity

本机文档 host 仍不是 builder/gate-host。正式构建与 archive 在 S7/S9 同一远端
`issac@10.10.60.4` 上执行。未使用 `DOCKER_HOST`，未改 cache host，未用 WSL Docker。

```text
schema: gateway.p2r1.build-identity
schema_version: 1
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
```

本地 candidate checkout 与远端 helper 输出相同。两份 lock hash：

```text
6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11  vnext/repository_service/uv.lock
6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954  vnext/repository_client/uv.lock
```

```text
local host: DESKTOP-V61T28L
docker: Name=DESKTOP-V61T28L ID=a46a67b1-30fc-4954-8375-e1aa988ebe30 ServerVersion=29.6.2
used_as_s10_builder_or_gate_host: no

ssh: issac@10.10.60.4 BatchMode=yes
whoami: issac
id: uid=1000(issac) gid=1000(issac) groups=1000(issac),955(libvirt),958(docker),998(wheel)
hostname_file: arch
docker: Name=arch ID=dc91db82-3d49-41a4-a63c-f23dda721890 ServerVersion=29.7.2 OperatingSystem=Arch Linux Driver=overlayfs NCPU=16
compose: Docker Compose version 5.4.0
remote cache http://172.17.0.1:18080: HTTP 200
same_daemon_build_and_gate: yes
cross_host_transfer: not_applicable
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset (before and after)
```

Builder 与 gate 仍是同一远端 Docker daemon。未发现独立 daemon，因此未做跨主机
save/load。dependency-base `gateway-p2r1-repository:lock-6dc9659f0aee` 仍不存在。
脚本走 retained artifact cache，而非 `USE_PRELOADED_DEPENDENCIES=1`。

```text
local_candidate_worktree: /root/gateway-s9-candidate-2ef88427
remote_candidate_worktree: /home/issac/gateway-s10-candidate-2ef88427
local_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
remote_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
local_git_status_porcelain: empty
remote_git_status_porcelain: empty
```

## Service image build

```text
remote worktree: /home/issac/gateway-s10-candidate-2ef88427
build_command: vnext/scripts/build-repository-service-image.sh (remote, retained cache)
identity_env:
  GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:p2-r6-final
  GATEWAY_P2R1_CANDIDATE_SHA=2ef884278b4998dde1e5fe224532c89b7a0cd73a
  GATEWAY_P2R1_BUILD_INPUT_REVISION=3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
  GATEWAY_P2R1_SOURCE_TREE_SHA256=sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
  GATEWAY_P2R1_UV_LOCK_SHA256=6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
build_started_at: 2026-08-17T04:27:14Z
build_finished_at: 2026-08-17T04:27:15Z
cache_endpoint: http://172.17.0.1:18080 (HTTP 200 on 10.10.60.4)
no_cache: no
dependency_base: absent; retained artifact cache path
image: gateway-repository-service:p2-r6-final
also_tagged: gateway-repository-service:local
image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
p2-r6-final_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
local_tag_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
dual_tag_identical: yes
image_label org.opencontainers.image.revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
image_label gateway.p2r1.build-input-revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
image_label gateway.p2r1.source-tree-sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_label gateway.p2r1.dolt-version: 2.1.11
image_label gateway.p2r1.uv-version: 0.11.28
image_label gateway.p2r1.mysql-connector-version: 9.7.0
image_label gateway.p2r1.pyarrow-version: 25.0.0
image_matches_build_context: true
image_id_equals_s9_provisional: yes
historical_s9_tag_retained: gateway-repository-service:2ef884278b49
```

构建后立即 `unset GATEWAY_REPOSITORY_SERVICE_IMAGE`。远端环境在构建前与构建后均为
unset，S10-5 将使用默认 `:local` 合同。未删除 S9 tag `:2ef884278b49`。

cache hit 使 immutable ID 与 S9 provisional 相同。本步权威是执行了 canonical final
构建并打上 `p2-r6-final` / `:local`，不是人为换 digest。

## Client runner identity

现有 `gateway-repository-client-e2e:local` labels 已匹配 candidate 与 Client lock，
按计划 requalify，未 force-rebuild，也未把 client 加入 production Compose。

```text
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
client_label org.opencontainers.image.revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
client_label gateway.p2r6.client-uv-lock-sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
client_action: requalify
client_rebuild: no
client_identity: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
host_runner_identity: host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
gate_host_python: /usr/bin/python3
gate_host_python_version: Python 3.14.7
```

## Same-daemon archive

创建临时 Service `docker save` archive。builder 与 gate 为同一 daemon，**未**
`docker load`，**未** 把 archive 拷到 WSL 或文档/candidate worktree。archive 保留到
S10-9 packet 后再删。

```text
command: docker save -o /tmp/p2-r6-s10-20260817T015148Z-service.tar gateway-repository-service:p2-r6-final gateway-repository-service:local
archive_path: /tmp/p2-r6-s10-20260817T015148Z-service.tar
image_references: gateway-repository-service:p2-r6-final gateway-repository-service:local
immutable_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
size_bytes: 332429824
sha256: f2416c49c0e6b712fdf59fb2db7ba5bd62c81cdeefe67b83155b852cf6ed2245
same_daemon_build_and_gate: yes
cross_host_transfer: not_applicable
docker_load_performed: no
save_started_at: 2026-08-17T04:28:02Z
save_finished_at: 2026-08-17T04:28:06Z
```

## Compose render and baseline

只 `docker compose ... config`，**未** `up`。`GATEWAY_REPOSITORY_SERVICE_IMAGE` unset。
throwaway `/tmp/s10-4-compose-boundary.py` 复述 harness `assert_p2r2_compose_boundary`
不变量（无 Service host port、无 docker.sock、无 host-root、无常驻 client），未提交、
未写入 candidate。`PYTHONDONTWRITEBYTECODE=1`。

```text
command: docker compose -p gateway-p2r6-s10-render -f vnext/deploy/compose.yaml --profile p2-r2 config --format json
compose_up: no
rendered_services: backend, repository-service, worker
repository_service_image: gateway-repository-service:local
repository_service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
published_ports: none
has_docker_socket: no
has_host_root_mount: no
resident_client_services: none
assert_p2r2_compose_boundary: pass
```

`backend` / `worker` 无 profile，因此出现在同一 compose 文件的渲染结果中；边界检查
只约束 `repository-service`，与 S7/S9 harness 口径一致。client image 不在 production
Compose 中。

资源基线（只记录，不清理 preexisting 非本轮对象）：

```text
residual_inventory gate=s10-4-final-artifacts
  gateway-p2r6 containers=0 networks=0 volumes=0
  dolt_pids=0 query_temps=0 check_temp_homes=0 work_root_gateway=0
  candidate_porcelain=empty
```

preexisting、**不是本轮 owned residual**（不在本步清理）：

```text
exited/created containers: 26 (none named gateway-p2r6)
```

## External audit artifacts

```text
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/artifacts/s10-4
remote_metadata: /tmp/p2-r6-s10-20260817T015148Z-s10-4
remote_archive: /tmp/p2-r6-s10-20260817T015148Z-service.tar
archive_copied_to_wsl: no
candidate_or_docs_wrote_archive: no
```

权威 metadata SHA-256（`artifacts/s10-4/SHA256SUMS`）：

```text
7ab484b6d26a2ae6064fcca2f7b3b123dd5c282e525698b4e463b4ac7d27cb39  identity-*.json (local/remote before/after identical)
d53bb2c745f7ade32763d7b442931c6a1cd4fa21046944256a3c00a3618e9405  locks-*.txt (identical)
650f5c805c2d0a18eb48341ee508bcea231038b7e6c66ea747033cdb1b408ed0  service-labels.txt
274a162e06fd360ad8b101cc43a1ed896f18e5ce41ad408df1b194ccd69f0b2f  service-final-id.txt / service-local-id.txt
b9fb179ecbcdfe06a4501d0e5c47691da9b6d8dfa4e9b72dfe6f723c41a88dda  client-host-runner.txt
07629ad153135061446a48a3344d2c144ec2fb37d331b1c0ee19dbda7522904c  archive-metadata.txt
062ca8e1f4945f82989597fee9a16d7f747468685375d6d14da8bb32ed6ff1e3  compose-boundary.json
705cd1f28467d1a455fa8c8d74ad89560c1350e5c30eb53b530bc716e4a3ae28  baseline.json
```

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (executed at S10-4)
Reason: S10 exact-candidate production gate requires final Service/Client artifacts; S9 provisional is not p2-r6-final until this canonical build and dual-tag
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10-5 exact ./vnext/scripts/run-tests.sh -vv -s and eight Docker nodeids; S10-6 W1 medium/W2 with adapter SHA 6282df80…827ebf; S10-7/S10-8 Candidate A W0/v8 formal
Required execution point: S10-5 exact no-ignore on this unchanged identity
```

本步不改变 `container_validated_code_sha`（仍 deferred）。S9 provisional ID 现已被
S10-4 canonical 构建与 `p2-r6-final` tag 限定为 final Service identity。

## Verdict

```yaml
s10_4_status: pass
final_service_image_provenance: pass
final_client_and_host_runner_identity: pass
same_daemon_archive_evidence: pass
dual_tag_identical: yes
image_matches_build_context: true
client_image_matches: true
worktree_clean: yes
compose_boundary: pass
compose_up: no
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
docker_load_performed: no
cross_host_transfer: not_applicable
zero_owned_gateway_p2r6_residual: yes
container_validated_code_sha: deferred
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-5 exact ./vnext/scripts/run-tests.sh -vv -s on this unchanged image/checkout
```

S10-5 必须继续使用：

```text
GATEWAY_REPOSITORY_SERVICE_IMAGE unset
image: gateway-repository-service:local
  == gateway-repository-service:p2-r6-final
  == sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
  == sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
remote worktree: /home/issac/gateway-s10-candidate-2ef88427
gate-host: issac@10.10.60.4
adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
```

同一会话仅在 candidate、build inputs、Service/Client IDs、tags 与 baseline 全程不变时
可以继续到 S10-5。本记录本身不构成 no-ignore gate、W1/W2 production、v8 formal、
S10 seal 或 Phase 2 completion。

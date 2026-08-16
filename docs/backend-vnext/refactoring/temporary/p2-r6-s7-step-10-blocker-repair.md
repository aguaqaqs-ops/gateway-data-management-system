# P2-R6-S7 — Step 10 blocker repair (same-candidate directed gates)

状态：`pass`（关闭 F-001/F-002；不是 S7 四 nodeid 聚合 PASS，不授予 S7-11）

日期：2026-08-16

本记录在 S7-10 独立审核 `fail` 之后，提交 harness 残留 inventory 打印，于同一新
candidate 上重建 Service 与 client image，并独立重跑四个 exact nodeid。未改
production `snapshot_admin`、Contract 或 Compose 拓扑。未启动 S7-11。

权威步骤：[P2-R6-S7 Compose Lifecycle Execution Plan](../formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md) §12
S7-10 fail：[p2-r6-s7-step-10-lifecycle-review.md](p2-r6-s7-step-10-lifecycle-review.md)
祖先 S7-5/S7-9 image：
[p2-r6-s7-step-5-provisional-image.md](p2-r6-s7-step-5-provisional-image.md)、
[p2-r6-s7-step-9-restored-lifecycle.md](p2-r6-s7-step-9-restored-lifecycle.md)

## Why rebuild

S7-10 F-001：四条 nodeid 分属 `eeadbdd` 与 `da14606`。F-002：teardown 未打印
per-project residual counts。harness 打印改动位于 `vnext/repository_service/tests/**`，
effective-input `source_roots` 包含整个 `vnext/repository_service`。docs-only `a396a92`
已使 `candidate_sha=HEAD` 与 `da14606` image labels 不一致。`eeadbdd` / `da14606` 只作
ancestor，不得当作当前 HEAD 已验证。

## Identity

```yaml
branch: phase1/gate-ownership-repair
candidate_sha: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
container_validated_code_sha: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
build_input_revision: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:af36c325403d
service_image_id: sha256:57f5622c134a734dd2c8ab34bc7971e4af5f5b088d09812316213accf77e64af
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:051b4bfe982c0c8d4a8b41cfbcebcc3f22a7f5eb78ead8ec3bf1f5abb2a815db
image_matches_build_context: true
worktree_clean_during_gate: yes
oracle: repository_client.versioned_v1.c0_c1_c2
```

`container_validated_code_sha` 是测试提交 `af36c325`（`test(repository): emit S7 residual
inventory evidence`）。本文件的 docs-only 提交不是 `container_validated_code_sha`。

祖先（不得当作本 HEAD 已验证）：

```text
ancestor_candidate: da1460613bc330c4878785de74decff0a7d97d26
ancestor_image_id: sha256:c34d2e99587981e4b9925359f7db338a261f2446fead477b0784e1fcd4f97f9e
ancestor_candidate: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
ancestor_image_id: sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
```

## Rebuild and transfer

```text
local cache http://172.17.0.1:18080: timeout / unreachable
remote cache http://172.17.0.1:18080 on 10.10.60.4: HTTP 200
ssh: issac@10.10.60.4
candidate_delivery: git bundle 3616ef0d..HEAD
  -> refs/gate/candidate-s7-10
  -> git worktree add --detach /home/issac/gateway-gate-af36c325403d af36c325
remote worktree: /home/issac/gateway-gate-af36c325403d
remote HEAD: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
local HEAD:  af36c325403d2173b5e4dc5b2ca69fa40d8b7812
worktree_clean: yes
local/remote helper identity: identical
build_command: vnext/scripts/build-repository-service-image.sh (remote, retained cache)
build_started_at: 2026-08-16T12:13:06Z
build_finished_at: 2026-08-16T12:13:52Z
remote_image_id: sha256:57f5622c134a734dd2c8ab34bc7971e4af5f5b088d09812316213accf77e64af
local_image_id:  sha256:57f5622c134a734dd2c8ab34bc7971e4af5f5b088d09812316213accf77e64af
image_label org.opencontainers.image.revision: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
image_label gateway.p2r1.build-input-revision: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
image_label gateway.p2r1.source-tree-sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_label gateway.p2r1.dolt-version: 2.1.11
image_label gateway.p2r1.uv-version: 0.11.28
image_label gateway.p2r1.mysql-connector-version: 9.7.0
image_label gateway.p2r1.pyarrow-version: 25.0.0
transfer: ssh remote `docker save` streamed to local `docker load`
service_transfer_started_at: 2026-08-16T12:14:40Z
service_transfer_finished_at: 2026-08-16T12:15:54Z
```

Client 在同一远端 worktree 构建（uv bootstrap 走 retained cache
`http://172.17.0.1:18080/uv/simple`），再 `docker save | load`。labels 绑定当前
candidate 与 `repository_client/uv.lock`。未把 client 加入 production Compose。

```text
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:051b4bfe982c0c8d4a8b41cfbcebcc3f22a7f5eb78ead8ec3bf1f5abb2a815db
client_label org.opencontainers.image.revision: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
client_label gateway.p2r6.client-uv-lock-sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
client_build_started_at: 2026-08-16T12:14:02Z
client_build_finished_at: 2026-08-16T12:14:32Z
client_transfer_started_at: 2026-08-16T12:15:54Z
client_transfer_finished_at: 2026-08-16T12:16:50Z
```

## Preflight

throwaway `/tmp/s7-step10-preflight.py` 只调用已有 harness，未提交。

```text
compose_project: gateway-p2r6-s7-preflight-0dcf1f99c1c2
token_mode: 0o400
token_uid/gid: 100/101 (gateway)
health: healthy
network_name: gateway-p2r6-s7-preflight-0dcf1f99c1c2_default
network_id: 86d96ed0305f125df9e956c15d6e0647b2dcd5c8dac15730219e36d163035e58
gateway_ipv4: 172.19.0.1
service_ipv4: 172.19.0.2
inside_endpoint: http://repository-service:8000
gate_host_endpoint: http://172.19.0.2:8000
endpoints_differ: true
host_port_published: no
gate_host_readyz: HTTP 200 {"status":"ready"} (ProxyHandler 空)
teardown_scan project=gateway-p2r6-s7-preflight-0dcf1f99c1c2 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-preflight-0dcf1f99c1c2 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
inventory_after_cleanup: containers=0 networks=0 volumes=0 hold=0
```

## Directed gates

四个 nodeid **各自独立**运行。每次 pytest 进程 `unset HTTP_PROXY HTTPS_PROXY http_proxy
https_proxy`。结束后确认无 `gateway-p2r6-s7-*` container / network / volume 再跑下一条。
未改验收语义。

共用环境：

```bash
cd vnext/repository_service
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:af36c325403d \
  uv run pytest -m 'integration and serial' -n 0 -v -s <nodeid>
```

### 1. import restart/replay

```text
nodeid: tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
started_at: 2026-08-16T12:17:50Z
finished_at: 2026-08-16T12:18:19Z
elapsed: 27.84s
result: PASSED
candidate_sha: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
service_image_id: sha256:57f5622c134a734dd2c8ab34bc7971e4af5f5b088d09812316213accf77e64af
compose_project: gateway-p2r6-s7-import-bd51c9b234aa
teardown_scan project=gateway-p2r6-s7-import-bd51c9b234aa container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-import-bd51c9b234aa containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
leftover_after_gate: none
```

stdout 只打印 `compose_project=`；commit/ref 细节由 nodeid 内部 assert 持有。

### 2. inside-network pinned-read

```text
nodeid: tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
started_at: 2026-08-16T12:18:27Z
finished_at: 2026-08-16T12:18:55Z
elapsed: 27.05s
result: PASSED
candidate_sha: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
service_image_id: sha256:57f5622c134a734dd2c8ab34bc7971e4af5f5b088d09812316213accf77e64af
client_identity: sha256:051b4bfe982c0c8d4a8b41cfbcebcc3f22a7f5eb78ead8ec3bf1f5abb2a815db
service_endpoint: http://repository-service:8000
compose_project: gateway-p2r6-s7-inside-036493ec7ae6
consumer_summary: status=ok repository_id=26b8cb11-ca64-4a83-9f83-10f796e87f99
  c0=9eo124hpkdca56npk40tr04gtgpua2gv
  c1=5a369d0rudkdr6bkm7f428nkn1hbofha
  c2=0tl6s91o919g17hjthlbputi5fj3o6uf
  main=0tl6s91o919g17hjthlbputi5fj3o6uf
teardown_scan project=gateway-p2r6-s7-inside-036493ec7ae6 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-inside-036493ec7ae6 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
leftover_after_gate: none
```

c0/c1/c2 互异，main 解析为 c2。inside-network 使用 ephemeral client container，labels
绑定当前 candidate。

### 3. gate-host pinned-read

```text
nodeid: tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
started_at: 2026-08-16T12:19:00Z
finished_at: 2026-08-16T12:19:24Z
elapsed: 22.57s
result: PASSED
candidate_sha: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
service_image_id: sha256:57f5622c134a734dd2c8ab34bc7971e4af5f5b088d09812316213accf77e64af
client_identity: host-runner:candidate=af36c325403d2173b5e4dc5b2ca69fa40d8b7812;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_endpoint: http://172.19.0.2:8000
compose_project: gateway-p2r6-s7-gatehost-cb4de7e5929a
consumer_summary: status=ok repository_id=128b998b-a411-48f6-bc07-abf6427a2d0d
  c0=h6h22lsku3vdh7sntgela1atq2h8ns9g
  c1=lok13hshe7tcvqh9vdgqs4ftanvc38eb
  c2=s9j9opbr6ff5uj7d5n4a6og8h0p5tchk
  main=s9j9opbr6ff5uj7d5n4a6og8h0p5tchk
teardown_scan project=gateway-p2r6-s7-gatehost-cb4de7e5929a container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-gatehost-cb4de7e5929a containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
leftover_after_gate: none
```

gate-host endpoint 是 Linux-bridge IPv4，与 inside-network DNS 名不同；无 host port。

### 4. fresh / restart / restored lifecycle

```text
nodeid: tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle
started_at: 2026-08-16T12:19:37Z
finished_at: 2026-08-16T12:20:49Z
elapsed: 71.57s
result: PASSED
candidate_sha: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
service_image_id: sha256:57f5622c134a734dd2c8ab34bc7971e4af5f5b088d09812316213accf77e64af
client_identity: host-runner:candidate=af36c325403d2173b5e4dc5b2ca69fa40d8b7812;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_endpoint: http://172.20.0.2:8000
compose_project: gateway-p2r6-s7-lifecycle-5dee395367b0,gateway-p2r6-s7-restored-8689c1b304e7
fresh_summary: status=ok repository_id=acc335e6-adc3-4d5f-9dd1-70fc4a5263a0
  c0=0lga2doakac3h81s42pnn4ssm9s9e0fp
  c1=vrbkjbade3ot2oon2d0fp7osoqlbeu92
  c2=s98nj2qq09kluqpl7qjc822ldgnetvke
  main=s98nj2qq09kluqpl7qjc822ldgnetvke
restart_summary: identical to fresh
hold_ready: action=hold status=ready schema_version=1
check_passed: action=check status=passed repository_count=1 artifact_count=2
mutation_id: 3902ca9b-d4bd-4648-b445-33d85ed9add2
archive_volume_role: source.restore_volume
restore_volume_role: restored.data_volume
teardown_scan project=gateway-p2r6-s7-restored-8689c1b304e7 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-restored-8689c1b304e7 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
teardown_scan project=gateway-p2r6-s7-lifecycle-5dee395367b0 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-lifecycle-5dee395367b0 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
leftover_after_gate: none
```

两个 session 各打出一行 `teardown_scan` / `residual_inventory`。public facts 来自
`versioned_fixture_consumer`，不直读 SQLite/Dolt。

## Cleanup

四条 gate 结束后本机无 `gateway-p2r6-s7-*` container / network / volume。

## Docker record

```text
Current HEAD: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
Container rebuild required: yes (executed this round)
Reason: F-002 harness print changed repository_service source-tree; F-001 required same-candidate rerun
Last verified image revision: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
Last verified source-tree/image id:
  sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 /
  sha256:57f5622c134a734dd2c8ab34bc7971e4af5f5b088d09812316213accf77e64af
Container gate for current HEAD: four exact S7 nodeids on this candidate
Deferred: S7-11 final rebuild; S8/S9/S10
Required execution point: S7-10 independent lifecycle rereview
```

## Verdict

本轮关闭 F-001（四条 nodeid 同一 candidate / image）与 F-002（stdout 打印 per-project
residual counts）。不宣称 S7 PASS，不进入 S7-11。

```text
all_nodeids_current_candidate: yes
S7_exit: no
allow_final_s7_gate: pending S7-10 rereview
phase_2_complete: no
next: S7-10 independent lifecycle rereview
```

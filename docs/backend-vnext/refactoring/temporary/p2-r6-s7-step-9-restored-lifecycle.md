# P2-R6-S7 — Step 9 restored lifecycle gate

状态：`pass`（单 nodeid；不是 S7 四 nodeid 聚合 PASS）

日期：2026-08-16

本记录在 S7-8 commit `da14606` 上重建 provisional Service image，完成短 preflight，
并运行第四个 Compose lifecycle nodeid。未改 production/Contract。未把 Stage J 或
`eeadbdd` 镜像写成当前 HEAD 已验证。

权威步骤：[P2-R6-S7 Compose Lifecycle Execution Plan](../formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md) §11
S7-8 实现：`da1460613bc330c4878785de74decff0a7d97d26`
祖先 S7-5 image：[p2-r6-s7-step-5-provisional-image.md](p2-r6-s7-step-5-provisional-image.md)

## Why rebuild

S7-8 改动位于 `vnext/repository_service/tests/**`，而 effective-input `source_roots`
包含整个 `vnext/repository_service`。当前 helper identity 与 `eeadbdd` labels 不一致，
`ensure_repository_service_image()` 会拒绝旧 tag 并尝试重建。本机 cache
`http://172.17.0.1:18080` 仍为 HTTP 502。Dockerfile 只 COPY `src/`，生产层与祖先
镜像可能相同，但 provenance 仍要求新 candidate 的新 image。

本 nodeid 使用 gate-host host-runner，未重建 client image。

## Identity

```yaml
branch: phase1/gate-ownership-repair
candidate_sha: da1460613bc330c4878785de74decff0a7d97d26
container_validated_code_sha: da1460613bc330c4878785de74decff0a7d97d26
build_input_revision: da1460613bc330c4878785de74decff0a7d97d26
source_tree_sha256: sha256:20225a8c0466186be7cb59c58f4bdd6dc5b8316fb3d3a804e5866009c7b5f204
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:da1460613bc3
service_image_id: sha256:c34d2e99587981e4b9925359f7db338a261f2446fead477b0784e1fcd4f97f9e
image_matches_build_context: true
worktree_clean_during_gate: yes
oracle: repository_client.versioned_v1.c0_c1_c2
```

祖先（不得当作本 HEAD 已验证）：

```text
ancestor_candidate: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
ancestor_image_id: sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
stage_j_candidate: 656a66bf04714cce987c85649246c3767b2586e2
stage_j_image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
```

## Rebuild and transfer

```text
local cache http://172.17.0.1:18080: HTTP 502
remote cache http://172.17.0.1:18080 on 10.10.60.4: HTTP 200
ssh: issac@10.10.60.4
candidate_delivery: git bundle 3616ef0d..HEAD
  -> refs/gate/candidate-s7-9
  -> git worktree add --detach /home/issac/gateway-gate-da1460613bc3 da146061
remote worktree: /home/issac/gateway-gate-da1460613bc3
remote HEAD: da1460613bc330c4878785de74decff0a7d97d26
local HEAD:  da1460613bc330c4878785de74decff0a7d97d26
worktree_clean: yes
local/remote helper identity: identical
build_command: vnext/scripts/build-repository-service-image.sh (remote, retained cache)
build_started_at: 2026-08-16T11:45:31Z
build_finished_at: 2026-08-16T11:46:16Z
remote_image_id: sha256:c34d2e99587981e4b9925359f7db338a261f2446fead477b0784e1fcd4f97f9e
local_image_id:  sha256:c34d2e99587981e4b9925359f7db338a261f2446fead477b0784e1fcd4f97f9e
image_label org.opencontainers.image.revision: da1460613bc330c4878785de74decff0a7d97d26
image_label gateway.p2r1.build-input-revision: da1460613bc330c4878785de74decff0a7d97d26
image_label gateway.p2r1.source-tree-sha256: sha256:20225a8c0466186be7cb59c58f4bdd6dc5b8316fb3d3a804e5866009c7b5f204
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_label gateway.p2r1.dolt-version: 2.1.11
image_label gateway.p2r1.uv-version: 0.11.28
image_label gateway.p2r1.mysql-connector-version: 9.7.0
image_label gateway.p2r1.pyarrow-version: 25.0.0
transfer: ssh remote `docker save` streamed to local `docker load`
transfer_started_at: 2026-08-16T11:46:23Z
transfer_finished_at: 2026-08-16T11:47:42Z
```

## Preflight

throwaway `/tmp/s7-step9-preflight.py` 只调用已有 harness，未提交。

```text
compose_project: gateway-p2r6-s7-preflight-76e92df8c949
token_mode: 0o400
token_uid/gid: 100/101 (gateway)
health: healthy
network_name: gateway-p2r6-s7-preflight-76e92df8c949_default
network_id: 2e18e8d4f9c198818ea35fdb6bbbf59f79710ab1910d45cc0e48b8a63effe8c0
gateway_ipv4: 172.19.0.1
service_ipv4: 172.19.0.2
inside_endpoint: http://repository-service:8000
gate_host_endpoint: http://172.19.0.2:8000
endpoints_differ: true
host_port_published: no
gate_host_readyz: HTTP 200 {"status":"ready"} (ProxyHandler 空)
inventory_after_cleanup: containers=0 networks=0 volumes=0 hold=0
```

## Command

pytest 进程 unset `HTTP_PROXY`/`HTTPS_PROXY`，避免 mutation/`versioned_ref_status`
的 urllib 走本机代理。host-runner env 已在 S7-8 去掉代理变量。

```bash
cd vnext/repository_service
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:da1460613bc3 \
  uv run pytest -m 'integration and serial' -n 0 -v -s \
  tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle
```

```text
nodeid: tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle
started_at: 2026-08-16T11:48:56Z
finished_at: 2026-08-16T11:50:55Z
elapsed: 117.51s
result: PASSED
compose_project: gateway-p2r6-s7-lifecycle-b57d9928476c,gateway-p2r6-s7-restored-201ba3ad6303
service_image_id: sha256:c34d2e99587981e4b9925359f7db338a261f2446fead477b0784e1fcd4f97f9e
client_identity: host-runner:candidate=da1460613bc330c4878785de74decff0a7d97d26;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_endpoint: http://172.20.0.2:8000
```

## Required observations

Public facts 来自同一 `versioned_fixture_consumer`，不直读 SQLite/Dolt。

```text
fresh_summary:
  status=ok
  repository_id=683d588f-8155-4cca-adf1-99c6ceca4ac1
  c0=1evaln0uf0tqs1i1voctma5qhgn7rm65
  c1=57k4srbt63v62ddoqi02ek1kico3mhua
  c2=1gc8o6v07tn6dc0h185nhtkaegr73476
  main=1gc8o6v07tn6dc0h185nhtkaegr73476
restart_summary: identical to fresh (force-recreate same volume)
hold_ready: action=hold status=ready schema_version=1
archive_volume_role: source.restore_volume
restore_volume_role: restored.data_volume
check_passed: action=check status=passed repository_count=1 artifact_count=2
mutation_id: b24816c3-410d-4ce0-b6af-a61932eda881
restored_summary: identical to fresh
mutation_ref_on_restored: 404
host_port_published: no
```

c0/c1/c2 互异，main 解析为 c2。mutation id 与 snapshot 期 repository_id 不同。
check 在 restored Service `up` 之前通过。fresh 与 restored project 使用不同 named
volume，不共享可写状态。

## Cleanup

gate 结束后本机无 `gateway-p2r6-s7-*` container / network / volume。不得把本结果写成
完整 S7 PASS。S7-6/S7-7 仍是 `eeadbdd` 上的 ancestor nodeid 证据。

```yaml
fresh_restart_restored: pass
all_nodeids_current_candidate: no
S7_exit: no
phase_2_complete: no
next: S7-10 independent lifecycle review
```

```text
Current HEAD: da1460613bc330c4878785de74decff0a7d97d26
Container rebuild required: yes (executed at S7-9)
Reason: S7-8 changed repository_service source-tree digest; ensure() rejects eeadbdd labels
Last verified image revision: da1460613bc330c4878785de74decff0a7d97d26
Last verified source-tree/image id:
  sha256:20225a8c0466186be7cb59c58f4bdd6dc5b8316fb3d3a804e5866009c7b5f204 /
  sha256:c34d2e99587981e4b9925359f7db338a261f2446fead477b0784e1fcd4f97f9e
Container gate for current HEAD: directed lifecycle nodeid only
Deferred: remaining three nodeids on this candidate; S7-11 final rebuild; S8/S9/S10
Required execution point: S7-10 independent lifecycle review
```

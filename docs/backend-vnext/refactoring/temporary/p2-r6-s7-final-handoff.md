# P2-R6-S7 — Final candidate / container gate handoff

状态：`pass`

日期：2026-08-16

本记录是 S7-11 在 S7-10 rereview `allow_final_s7_gate: yes` 之后的 final candidate
重建与四条 exact Compose nodeid 门禁。未修改 production code、Contract、snapshot 语义或
Compose 拓扑。未打 `p2-r6-final` tag，不宣称 Phase 2 完成。

权威步骤：[P2-R6-S7 Compose Lifecycle Execution Plan](../formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md) §13–§14
S7-10 放行：[p2-r6-s7-step-10-lifecycle-rereview.md](p2-r6-s7-step-10-lifecycle-rereview.md)
Harness 审核：[p2-r6-s7-step-4-harness-final-review.md](p2-r6-s7-step-4-harness-final-review.md)

## Identity

```yaml
branch: phase1/gate-ownership-repair
entry_sha: 0b4969fe04ab3d133c297a474bac1ecc27111336
validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
container_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
build_input_revision: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:5f474ce2ccf1
service_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:d4e07d7900d70df49df6f2628cc1cf542a6e02c8772e8cab35cedf82972ee461
image_matches_build_context: true
worktree_clean_during_gate: yes
oracle: repository_client.versioned_v1.c0_c1_c2
snapshot_semantics: S4 whole-root hold/check
package_version: v1
public_contract_change: no
```

`container_validated_code_sha` 是门禁开始时的干净 HEAD `5f474ce2`（S7-10 修复证据的
docs-only descendant）。`build_input_revision` 仍为实现提交 `af36c325`。本文件的
docs-only 提交不是 `container_validated_code_sha`。

祖先（不得当作本 candidate 已验证）：

```text
ancestor_candidate: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
ancestor_image_id: sha256:57f5622c134a734dd2c8ab34bc7971e4af5f5b088d09812316213accf77e64af
ancestor_candidate: da1460613bc330c4878785de74decff0a7d97d26
ancestor_image_id: sha256:c34d2e99587981e4b9925359f7db338a261f2446fead477b0784e1fcd4f97f9e
ancestor_candidate: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
ancestor_image_id: sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
ancestor_candidate: 656a66bf04714cce987c85649246c3767b2586e2
ancestor_image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
```

## Source checks

在干净 HEAD `5f474ce2` 上执行（非 S8 五包全量 `run-tests.sh`）：

```text
repository_service ruff: pass
repository_service mypy: pass (195 source files)
repository_client ruff: pass
repository_client mypy: pass (26 source files)
git diff --check: pass
repository_service unit
  tests/test_compose_lifecycle_harness.py
  tests/test_compose_build_harness.py
  tests/test_versioned_read_http.py: 163 passed
repository_client unit tests/test_versioned_fixture_consumer.py: 42 passed
exact S7 nodeid collection: 4 tests collected
```

## Rebuild

```text
local cache http://172.17.0.1:18080: HTTP 502 (fail closed for local formal build)
remote cache http://172.17.0.1:18080 on 10.10.60.4: HTTP 200
ssh: issac@10.10.60.4
candidate_delivery: git bundle 3616ef0d..HEAD
  -> refs/gate/candidate-s7-11
  -> git worktree add --detach /home/issac/gateway-gate-5f474ce2ccf1 5f474ce2
remote worktree: /home/issac/gateway-gate-5f474ce2ccf1
remote HEAD: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
local HEAD:  5f474ce2ccf15f11ea07f263edf3fb04c771d410
worktree_clean: yes
local/remote helper identity: identical
build_command: vnext/scripts/build-repository-service-image.sh (remote, retained cache)
build_started_at: 2026-08-16T12:40:39Z
build_finished_at: 2026-08-16T12:41:27Z
remote_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
image_label org.opencontainers.image.revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
image_label gateway.p2r1.build-input-revision: af36c325403d2173b5e4dc5b2ca69fa40d8b7812
image_label gateway.p2r1.source-tree-sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_label gateway.p2r1.dolt-version: 2.1.11
image_label gateway.p2r1.uv-version: 0.11.28
image_label gateway.p2r1.mysql-connector-version: 9.7.0
image_label gateway.p2r1.pyarrow-version: 25.0.0
image_matches_build_context: true
```

Client 在同一远端 worktree 构建（uv bootstrap 走 retained cache
`http://172.17.0.1:18080/uv/simple`）。labels 绑定当前 candidate 与
`repository_client/uv.lock`。未把 client 加入 production Compose。

```text
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:d4e07d7900d70df49df6f2628cc1cf542a6e02c8772e8cab35cedf82972ee461
client_label org.opencontainers.image.revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
client_label gateway.p2r6.client-uv-lock-sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
client_build_started_at: 2026-08-16T12:41:45Z
client_build_finished_at: 2026-08-16T12:42:18Z
```

Directed gates 在构建主机 `10.10.60.4`（Linux Docker / Compose / bridge）上执行，因此
immutable image ID 在该主机核对，不把 workspace WSL (`10.10.60.2`) 的未完成 save/load
当作替代证据。未使用 `p2-r6-final` tag。

## Directed gates

四个 nodeid **各自独立**运行。每次 pytest 进程 `unset HTTP_PROXY HTTPS_PROXY http_proxy
https_proxy`。结束后确认无 `gateway-p2r6-s7-*` container / network / volume 再跑下一条。
未改验收语义。gate-host 与 lifecycle 的 host runner 使用 locked `uv run --offline` 和
预先 `uv sync --frozen` 的 `repository_client` 环境。

共用环境：

```bash
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:5f474ce2ccf1 \
  pytest -m 'integration and serial' -n 0 -v -s <nodeid>
```

### 1. import restart/replay

```text
nodeid: tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
started_at: 2026-08-16T13:07:31Z
finished_at: 2026-08-16T13:07:52Z
elapsed: 20.32s
result: PASSED
candidate_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
service_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
compose_project: gateway-p2r6-s7-import-7213496e3650
teardown_scan project=gateway-p2r6-s7-import-7213496e3650 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-import-7213496e3650 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
leftover_after_gate: none
```

### 2. inside-network pinned-read

```text
nodeid: tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
started_at: 2026-08-16T13:07:58Z
finished_at: 2026-08-16T13:08:14Z
elapsed: 16.03s
result: PASSED
candidate_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
service_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
client_identity: sha256:d4e07d7900d70df49df6f2628cc1cf542a6e02c8772e8cab35cedf82972ee461
service_endpoint: http://repository-service:8000
compose_project: gateway-p2r6-s7-inside-10962740c688
consumer_summary: status=ok repository_id=0038aaa3-8850-4f62-83c1-521115c0b9d3
  c0=9mjvtr4oakagv1v3ja2js63vfn8md6i5
  c1=jf1l5ibhq2ugmlvpqoof3alsq6r79rq9
  c2=q79rmhgo876ccftb8fofmgb0kgfhctsm
  main=q79rmhgo876ccftb8fofmgb0kgfhctsm
teardown_scan project=gateway-p2r6-s7-inside-10962740c688 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-inside-10962740c688 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
leftover_after_gate: none
```

c0/c1/c2 互异，main 解析为 c2。inside-network 使用 ephemeral client container，labels
绑定当前 candidate。

### 3. gate-host pinned-read

```text
nodeid: tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
started_at: 2026-08-16T13:09:44Z
finished_at: 2026-08-16T13:09:59Z
elapsed: 14.92s
result: PASSED
candidate_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
service_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
client_identity: host-runner:candidate=5f474ce2ccf15f11ea07f263edf3fb04c771d410;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_endpoint: http://172.18.0.2:8000
compose_project: gateway-p2r6-s7-gatehost-d2168803a357
consumer_summary: status=ok repository_id=b21d4653-43f1-4d3d-9fde-73067e1d9c87
  c0=ko6petp1jovr1bbe260tkc0reuf23r9c
  c1=bkrltpce8mp8angid32n5h7mo4c5aiau
  c2=65l9ao3r83623k7hns4dn0bdngloplp6
  main=65l9ao3r83623k7hns4dn0bdngloplp6
teardown_scan project=gateway-p2r6-s7-gatehost-d2168803a357 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-gatehost-d2168803a357 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
leftover_after_gate: none
```

gate-host endpoint 是 Linux-bridge IPv4，与 inside-network DNS 名不同；无 host port。

### 4. fresh / restart / restored lifecycle

```text
nodeid: tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle
started_at: 2026-08-16T13:10:08Z
finished_at: 2026-08-16T13:10:59Z
elapsed: 50.29s
result: PASSED
candidate_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
service_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
client_identity: host-runner:candidate=5f474ce2ccf15f11ea07f263edf3fb04c771d410;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_endpoint: http://172.19.0.2:8000
compose_project: gateway-p2r6-s7-lifecycle-d4e89cf005b1,gateway-p2r6-s7-restored-4d16d016b957
fresh_summary: status=ok repository_id=37271b72-c5f8-4cfb-9c92-7de9b7d14e74
  c0=n6o0lfrfam9gmockflltbb9o985vkk1k
  c1=b7bj9e7mrptbqrdhnhvcv2i3v0f6sjjs
  c2=kq1ll9gut62v6tb7dood6ci9v9srp8g6
  main=kq1ll9gut62v6tb7dood6ci9v9srp8g6
restart_summary: identical to fresh
hold_ready: action=hold status=ready schema_version=1
check_passed: action=check status=passed repository_count=1 artifact_count=2
mutation_id: 8f17a43c-b156-41cc-abb9-cfaadfb12792
archive_volume_role: source.restore_volume
restore_volume_role: restored.data_volume
teardown_scan project=gateway-p2r6-s7-restored-4d16d016b957 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-restored-4d16d016b957 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
teardown_scan project=gateway-p2r6-s7-lifecycle-d4e89cf005b1 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-lifecycle-d4e89cf005b1 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
leftover_after_gate: none
```

两个 session 各打出一行 `teardown_scan` / `residual_inventory`。public facts 来自
`versioned_fixture_consumer`，不直读 SQLite/Dolt。restart facts 与 fresh 相同；check 在
restored Service 启动前通过。

## Cleanup

四条 gate 结束后构建主机无 `gateway-p2r6-s7-*` container / network / volume。

## Docker / Compose decision

```text
Current HEAD: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Container rebuild required: yes
Reason: S7 Compose/client/lifecycle boundary changed
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current candidate: passed
Deferred gates/nodeids: S8 full regression/candidate preparation; S9 exact candidate seal; S10 production/v8/container (four Compose nodeids on the final P2 candidate, W1/W2, v8 --runs 5)
Required execution point: S7 final candidate
```

后续 docs-only handoff 提交会使 documentation HEAD 相对 image label 变为
stale-by-documentation-only-delta；`container_validated_code_sha` 仍为 `5f474ce2`。

## Handoff schema

```yaml
stage: P2-R6-S7
stage_status: pass
entry_sha: 0b4969fe04ab3d133c297a474bac1ecc27111336
validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
container_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
service_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
client_image_id: sha256:d4e07d7900d70df49df6f2628cc1cf542a6e02c8772e8cab35cedf82972ee461
source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
nodeids:
  import_restart_replay: pass
  pinned_read_inside_network: pass
  pinned_read_gate_host: pass
  fresh_restart_restored: pass
all_nodeids_current_candidate: yes
public_oracle: versioned_v1.c0_c1_c2
snapshot_semantics: S4 whole-root hold/check
zero_process_thread_query_temp_residual: yes
zero_container_network_volume_residual: yes
independent_harness_review: pass
independent_lifecycle_review: pass
S7_exit: pass
S8_ready: yes
production_retest_required: yes
phase_2_complete: no
deferred_scope:
  - S8 full regression/candidate preparation
  - S9 exact candidate seal
  - S10 final production/v8/container gate
```

S10 仍须在最终 P2 candidate 上重跑上述四条 nodeid，以及 W1/W2 与 Candidate A v8
formal `--runs 5`。任一项不得从 handoff 静默删除。

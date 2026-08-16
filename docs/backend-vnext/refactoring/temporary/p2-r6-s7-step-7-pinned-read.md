# P2-R6-S7 — Step 7 R5 inside-network and gate-host pinned-read

状态：`pass`（两条 per-node 记录均独立通过；不是 S7 四 nodeid 聚合 PASS）

日期：2026-08-16

本记录在同一 S7-5 provisional image 上分别运行两条 R5 remote-consumer nodeid。源码未改。
第四个 restored-lifecycle nodeid 未跑。

权威步骤：[P2-R6-S7 Compose Lifecycle Execution Plan](../formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md) §9
镜像证据：[p2-r6-s7-step-5-provisional-image.md](p2-r6-s7-step-5-provisional-image.md)

## Shared identity

```yaml
candidate_sha: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
container_validated_code_sha: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
service_image: gateway-repository-service:eeadbdd38ab4
service_image_id: sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:5b06a495979442437e11261d2506919e656d1fcbb65a56c56970e045d80de41e
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
oracle: repository_client.versioned_v1.c0_c1_c2
worktree_clean_during_gates: yes
```

两条 nodeid 使用同一 `versioned_fixture_consumer` 与 `versioned_v1` fixture，不直接读
SQLite/Dolt。`ensure_repository_service_image()` / `ensure_client_image()` 因 labels 匹配
跳过 rebuild。

---

## Per-node: inside-network

```bash
cd vnext/repository_service
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:eeadbdd38ab4 \
  uv run pytest -m 'integration and serial' -n 0 -v -s \
  tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
```

```text
nodeid: tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
started_at: 2026-08-16T11:22:42Z
finished_at: 2026-08-16T11:23:07Z
elapsed: 24.86s
result: PASSED
compose_project: gateway-p2r6-s7-inside-a3f710d20d3a
service_image_id: sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
client_identity: sha256:5b06a495979442437e11261d2506919e656d1fcbb65a56c56970e045d80de41e
service_endpoint: http://repository-service:8000
consumer_summary:
  status=ok
  repository_id=2aa67f6d-1ee7-4f6b-b38b-75b909c631c4
  c0=gdsp51thm1o399ttibpqcjhvgqqp2bp8
  c1=hd1mrgjq6ipc119moos1jrtjata5f0kj
  c2=m4lk4t3qa6qq3qst500h9sgk1psab2g5
  main=m4lk4t3qa6qq3qst500h9sgk1psab2g5
leftover_client_containers: none (ancestor=client_image, network=project_default)
host_port_published: no
```

c0/c1/c2 互异，main 解析为 c2。ephemeral client 容器退出后无残留。

---

## Per-node: gate-host

第一次运行（继承本机 `HTTP_PROXY=http://127.0.0.1:50808`）失败：consumer stdout
`{"http_status":502,"status":"failed"}`，stderr `missing X-Request-ID header`。这是 gate-host
进程经本机代理访问 `http://172.19.0.2:8000` 的环境干扰，不是 Service 未就绪。harness 的
`host_runner_env` allowlist 包含 `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`；Python/httpx 不把
`NO_PROXY=172.19.*` 识别为该 bridge IP。cleanup 仍把 project 级对象清零。

第二次运行在 pytest 进程中 unset `HTTP_PROXY`/`HTTPS_PROXY`（不改源码），直接走 Linux
bridge。这是 gate-host 拓扑要求的直连，不是 host-port 发布。

```bash
cd vnext/repository_service
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:eeadbdd38ab4 \
  uv run pytest -m 'integration and serial' -n 0 -v -s \
  tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
```

```text
nodeid: tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
started_at: 2026-08-16T11:24:38Z
finished_at: 2026-08-16T11:25:04Z
elapsed: 24.91s
result: PASSED
compose_project: gateway-p2r6-s7-gatehost-3a8d01fd9039
service_image_id: sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
client_identity: host-runner:candidate=eeadbdd38ab468667b2b9ebbdfffae39ddc62771;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_endpoint: http://172.19.0.2:8000
consumer_summary:
  status=ok
  repository_id=99056c98-9b61-4828-a5ea-66134560982e
  c0=kvap3qsm2e8fsvfbf90tnqs0sb7o78bc
  c1=4cmac3g6esbb65e6eheo5uhu752rbte1
  c2=gbjle6ap0miei6ocg8oj1vqgcelrucsm
  main=gbjle6ap0miei6ocg8oj1vqgcelrucsm
host_port_published: no
```

inside-network 与 gate-host 的 endpoint 形式不同（DNS 名 vs bridge IPv4），且都不是
localhost。两条 nodeid 使用独立 project/volume/token，facts 不共享。

---

## Cleanup and boundary

两条 nodeid 结束后本机无 `gateway-p2r6-s7-*` container / network / volume。inside 路径无
残留 client 容器；gate-host 为 host-runner 进程，不保留 client 容器。

```yaml
inside_network: pass
gate_host: pass
all_two_read_nodeids: yes
fresh_restart_restored: missing (S7-8/S7-9)
S7_exit: no
phase_2_complete: no
next: S7-8 restored lifecycle implementation
```

本轮三个 directed nodeid（S7-6 + 本文件两条）在同一 provisional candidate/image 上为
pass。当前 HEAD 的完整 S7 container gate 仍为 deferred，直到第四个 nodeid 与 S7-11
final rebuild。

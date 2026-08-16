# P2-R6-S7 — Step 6 R4 import restart/replay

状态：`pass`（单 nodeid；不是 S7 四 nodeid 聚合 PASS）

日期：2026-08-16

本记录在 S7-5 provisional image 上运行既有 R4 Compose nodeid。源码未改。未把 Stage J
旧镜像结果写成当前 HEAD 已验证。

权威步骤：[P2-R6-S7 Compose Lifecycle Execution Plan](../formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md) §8
镜像证据：[p2-r6-s7-step-5-provisional-image.md](p2-r6-s7-step-5-provisional-image.md)

## Identity

```yaml
candidate_sha: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
container_validated_code_sha: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
service_image: gateway-repository-service:eeadbdd38ab4
service_image_id: sha256:b8615ac898f9b370d2a2c7f69175c50ba352448f476b29ab756edf61c0e7e606
image_matches_build_context: true
worktree_clean_during_gate: yes
```

`ensure_repository_service_image()` 因 labels 匹配当前 build context，未再 rebuild。

## Command

```bash
cd vnext/repository_service
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:eeadbdd38ab4 \
  uv run pytest -m 'integration and serial' -n 0 -v -s \
  tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
```

```text
nodeid: tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
started_at: 2026-08-16T11:22:07Z
finished_at: 2026-08-16T11:22:34Z
elapsed: 25.66s
result: PASSED
compose_project: gateway-p2r6-s7-import-9a6503ab667c
```

## Required observations

测试在同一 named volume 上完成：

- rendered `p2-r2` Compose 无 Service host port；
- token 0400 + chown 到镜像 `gateway`；
- `up -d --no-build repository-service` 后 `wait_healthy`；
- 容器内 HTTP runner `flow`：create/upload/import；
- `up -d --no-build --force-recreate repository-service` 后再次 healthy；
- 容器内 `verify`：同一 `operation_id`，`status=SUCCEEDED`（无重复 publication）；
- artifact tomb/detach/unlink 残留计数为 0；
- `p2r2_project_session` finally：`down -v --remove-orphans` 后 project 级
  container/network/volume/hold 为空，并检查 Dolt/query-temp/thread/client PID baseline。

stdout 只打印 `compose_project=`；commit/ref 细节由 nodeid 内部 assert 持有，未向外泄露 secret
或 host path。

## Cleanup

gate 结束后本机无 `gateway-p2r6-s7-*` container / network / volume。不得把本结果写成完整
S7 PASS。

```yaml
nodeid_status: pass
S7_exit: no
phase_2_complete: no
next: S7-7 inside-network and gate-host pinned-read
```

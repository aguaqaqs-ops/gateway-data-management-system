# P2-R6-S3 Step E container gate provenance

状态：Executed

候选 SHA（`validated_code_sha` / `container_validated_code_sha`）：
`71250c8790be6688bc9d2042e2e0a0e79a783447`

本文件在 build-context digest 之外（不位于 `vnext/repository_service/**` 或
`vnext/repository_contracts/**`）。本提交的 SHA 是 `provenance_documentation_sha`，
不得回填进候选代码或镜像 label。

注：首次 provenance 提交 `37e01cba7fa7099cf219b041376929bd6033f07a` 将 candidate SHA
误记为 38 字符；本提交仅修正文档记录，不改变 `validated_code_sha`、镜像 identity 或
container gate 结论。

S2 image `e78b564` / `sha256:87e4e908bfa6...` 仅作祖先证据，已 superseded for S3 exit。

## Identity gate

```text
remote worktree: /home/tmpuser/gateway-gate-71250c8790be
remote HEAD: 71250c8790be6688bc9d2042e2e0a0e79a783447
local HEAD:  71250c8790be6688bc9d2042e2e0a0e79a783447
worktree_clean: yes
build_command: vnext/scripts/build-repository-service-image.sh (remote, --no-cache after label mismatch)
cache_endpoint: http://172.17.0.1:18080 (HTTP 200 on 10.10.60.4)
build_input_revision: 71250c8790be6688bc9d2042e2e0a0e79a783447
source_tree_sha256: sha256:5222659983e79f8f4c9a548fc6f9a749b66bffdd1c13c2aeec9278522349e6c0
image: gateway-repository-service:71250c8790be
image_id: sha256:0d0f6b4f9c547de5a0635b9af20175507e606028e1641e7064c567184d5a093f
remote_image_id: sha256:0d0f6b4f9c547de5a0635b9af20175507e606028e1641e7064c567184d5a093f
local_image_id: sha256:0d0f6b4f9c547de5a0635b9af20175507e606028e1641e7064c567184d5a093f
image_label org.opencontainers.image.revision: 71250c8790be6688bc9d2042e2e0a0e79a783447
image_label gateway.p2r1.source-tree-sha256: sha256:5222659983e79f8f4c9a548fc6f9a749b66bffdd1c13c2aeec9278522349e6c0
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_matches_build_context: true
transfer: ssh remote `docker save` streamed to local `docker load`
```

首次 cached build 的 revision label 因 shell 硬编码截断为 38 字符，identity gate 失败后以
`git rev-parse HEAD` 派生 revision 执行 `--no-cache` 重建；最终 remote/local image ID 一致。

## Compose wiring

`docker compose -f vnext/deploy/compose.yaml --profile p2-r2 config` 渲染结果中无
`artifact-broker`、`SCM_RIGHTS`、`pidfd`、`GATEWAY_REPOSITORY_ARTIFACT_BROKER` 或额外
broker/helper/socket 接线。`repository-service` 保留 production env、bearer secret、
`repository-service-data` volume 与 `/readyz` healthcheck。

## Directed container/process gates

1. **Compose config**：forbidden token scan **PASSED**。

2. **Fresh volume import/restart/replay**：
   `tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay`
   **PASSED (35.72s)**，镜像 `gateway-repository-service:local`。

3. **FULL_SCAN cumulative deadline**（`GATEWAY_REPOSITORY_FULL_SCAN_TIMEOUT_SECONDS=1`，
   65536-row package，compose project `gateway-p2r6-s3-e-57ec682ef3be`）：
   - operation `FAILED`，`VERIFICATION_FAILED_NOT_PUBLISHED`
   - dolt child 计数回到 baseline（2），query temp 为零

4. **Slow row streams 1/4/8**：directed probe 在容器内并发打开 1/4/8 路 row stream，
   全部成功，cleanup 后 query temp 为零。

5. **第九路 pre-header 503**：8 路 stream 持锁后第 9 路请求
   `503 SERVICE_NOT_READY`，未输出 Arrow body。

6. **Disconnect cleanup**：主动断开 row stream 后 dolt child 回到 baseline，query temp 为零。

7. **Restart**：`compose restart` 后 `/readyz` ready，`repository_import_operations`
   中 `RUNNING` 计数为 0。

8. **Teardown**：`compose down -v` 后该 project 的 container/network/volume 为空。

Directed probe 脚本位于 gate host `/tmp/s3_step_e_gate_probe.py` 与
`/tmp/s3_row_stream_probe.py`（非 production surface，未提交）。

完整 JSON report：`/tmp/s3-step-e-report.json`。

## Docker record

```text
Current HEAD: 71250c8790be6688bc9d2042e2e0a0e79a783447
Container rebuild required: yes (executed at Step E)
Reason: S3 exact candidate; source tree superseded S2 e78b564 image
Last verified image revision (S2, superseded): e78b564a112b2a040740e3e07d7e6f04329d06e9
Last verified source-tree/image id (S2): sha256:2cc377e74be2ab342ee09028ce54ff77a4690c5a5f12ce633959bfe6643172a2 / sha256:87e4e908bfa63370033256b380c6582c39fb6888749131633d5e856ae649a007
Container gate for current HEAD: passed
Deferred gates/nodeids: none for S3 exit
Required execution point: S3 exact-candidate Step E
```

```yaml
validated_code_sha: 71250c8790be6688bc9d2042e2e0a0e79a783447
container_validated_code_sha: 71250c8790be6688bc9d2042e2e0a0e79a783447
provenance_documentation_sha: <this commit>
image_id: sha256:0d0f6b4f9c547de5a0635b9af20175507e606028e1641e7064c567184d5a093f
source_tree_sha256: sha256:5222659983e79f8f4c9a548fc6f9a749b66bffdd1c13c2aeec9278522349e6c0
production_retest_required: yes
phase_2_complete: no
P2-R6-S3_exit: pass
P2-R6-S4_ready: yes
```

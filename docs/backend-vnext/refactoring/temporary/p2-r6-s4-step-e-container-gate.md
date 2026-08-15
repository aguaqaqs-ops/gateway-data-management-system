# P2-R6-S4 Step E container gate provenance

状态：Executed

候选 SHA（`validated_code_sha` / `container_validated_code_sha`）：
`b805d0d5f3c6164875319bd5e4b7b12d998cfe96`

本文件在 build-context digest 之外（不位于 `vnext/repository_service/**` 或
`vnext/repository_contracts/**`）。本提交的 SHA 是 `provenance_documentation_sha`，
不得回填进候选代码或镜像 label。

S3 image `71250c8` / `sha256:0d0f6b4f9c547de5a0635b9af20175507e606028e1641e7064c567184d5a093f`
仅作祖先证据，已 superseded for S4 exit。

## Identity gate

```text
remote worktree: /home/tmpuser/gateway-gate-b805d0d
remote HEAD: b805d0d5f3c6164875319bd5e4b7b12d998cfe96
local HEAD:  b805d0d5f3c6164875319bd5e4b7b12d998cfe96
worktree_clean: yes
build_command: vnext/scripts/build-repository-service-image.sh (remote, retained cache)
cache_endpoint: http://172.17.0.1:18080 (HTTP 200 on 10.10.60.4)
build_input_revision: b805d0d5f3c6164875319bd5e4b7b12d998cfe96
source_tree_sha256: sha256:dde82b4acfc86e6561f5c195daef31a75ae7e3417f9f808da41a7af6f37ae7f6
image: gateway-repository-service:b805d0d
image_id: sha256:0c93c04b15501b9db536016a729a6520252fca445dc0746a4f04c335f54de26e
remote_image_id: sha256:0c93c04b15501b9db536016a729a6520252fca445dc0746a4f04c335f54de26e
local_image_id: sha256:0c93c04b15501b9db536016a729a6520252fca445dc0746a4f04c335f54de26e
image_label org.opencontainers.image.revision: b805d0d5f3c6164875319bd5e4b7b12d998cfe96
image_label gateway.p2r1.source-tree-sha256: sha256:dde82b4acfc86e6561f5c195daef31a75ae7e3417f9f808da41a7af6f37ae7f6
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_matches_build_context: true
transfer: ssh remote `docker save` streamed to local `docker load`
candidate_delivery: git bundle fetch to remote refs/gate/candidate-s4
```

## Compose wiring

`docker compose -f vnext/deploy/compose.yaml --profile p2-r2 config` 渲染结果中无
`artifact-broker`、`SCM_RIGHTS`、`pidfd`、`GATEWAY_REPOSITORY_ARTIFACT_BROKER` 或额外
broker/helper/socket 接线。`repository-service` 保留 production env、bearer secret、
`repository-service-data` volume 与 `/readyz` healthcheck。未新增常驻 snapshot service。

## Directed container/process gates

Compose project：`gateway-p2r6-s4-e-cba761130572`。完整 JSON report：
`/tmp/s4-step-e-report.json`。Directed probe 脚本位于 gate host
`/tmp/s4_step_e_gate_probe.py`（非 production surface，未提交）。

1. **Compose config + forbidden token scan**：**PASSED**。

2. **Fresh volume import/read**：**PASSED** — fresh named volume 启动 candidate
   Service，容器内 `import_compose_http_runner.py flow` 创建 repository 并完成 import；
   保存 snapshot 时 `repository_id` / `commit_id` / ref+catalog public facts。

3. **Stopped-service hold ready JSON**：**PASSED** — entrypoint override、`gateway`
   euid、`snapshot_admin hold` 输出完整 `action=hold`、`status=ready` JSON，helper 仍存活。

4. **Hold lock exclusion**：**PASSED** — hold 存活期间 `compose up` 未使 Service 变为
   healthy；第二 helper `exit 3` 且无 ready stdout。

5. **Whole-volume snapshot + lock release**：**PASSED** — ready 窗口内 `alpine tar`
   复制整个 named volume（143360 bytes）；`SIGTERM` 后 hold `exit 0`；后续 verify hold
   可再次取得 ready 并受控退出。

6. **Post-snapshot mutation**：**PASSED** — 原 root 重启后创建 snapshot 之后的新
   repository，随后停止 Service。

7. **Empty-target / incomplete restore boundaries**：**PASSED** — 新 restore volume 在
   restore 前为空；sqlite-only partial copy `check exit 4`；non-empty overlay target
   `check exit 4`；均无 `passed` stdout。

8. **Restored lifecycle + public facts**：**PASSED** — restored volume 上 `check`
   输出 `status=passed`；同一 image 普通 entrypoint 启动后 `/readyz` ready；snapshot 时
   ref/catalog 与保存 facts 一致；post-snapshot mutation ref 返回 `404`。

9. **Corrupt control fail closed**：**PASSED** — 独立 scratch volume 上 corrupt control
   DB 后 `check exit 4`、无 `passed`、root 文件清单未被 helper 修改。

10. **Teardown inventory zero**：**PASSED** — `compose down -v` 后该 project 的
    container/network/volume 为空。

总耗时约 **51.8s**。

## Docker record

```text
Current HEAD: b805d0d5f3c6164875319bd5e4b7b12d998cfe96
Container rebuild required: yes (executed at Step E)
Reason: S4 exact candidate; source tree superseded S3 71250c8 image
Last verified image revision (S3, superseded): 71250c8790be6688bc9d2042e2e0a0e79a783447
Last verified source-tree/image id (S3): sha256:5222659983e79f8f4c9a548fc6f9a749b66bffdd1c13c2aeec9278522349e6c0 / sha256:0d0f6b4f9c547de5a0635b9af20175507e606028e1641e7064c567184d5a093f
Container gate for current HEAD: passed
Deferred gates/nodeids: none for S4 exit
Required execution point: S4 exact-candidate Step E
```

```yaml
validated_code_sha: b805d0d5f3c6164875319bd5e4b7b12d998cfe96
container_validated_code_sha: b805d0d5f3c6164875319bd5e4b7b12d998cfe96
provenance_documentation_sha: <this commit>
image_id: sha256:0c93c04b15501b9db536016a729a6520252fca445dc0746a4f04c335f54de26e
source_tree_sha256: sha256:dde82b4acfc86e6561f5c195daef31a75ae7e3417f9f808da41a7af6f37ae7f6
production_retest_required: yes
phase_2_complete: no
P2-R6-S4_exit: pass
P2-R6-S5_ready: yes
```

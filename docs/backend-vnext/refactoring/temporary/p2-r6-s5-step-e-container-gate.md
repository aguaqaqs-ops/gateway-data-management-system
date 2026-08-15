# P2-R6-S5 Step E container gate provenance

状态：Executed

候选 SHA（`validated_code_sha` / `container_validated_code_sha` / `candidate_sha`）：
`e7a6e42d961a75c5a35a385bd67d9417779c22b5`

本文件在 verified effective digest 之外（不位于 `vnext/repository_service/**` 或
`vnext/repository_contracts/**`，也不在 versioned build-definition path 内）。本提交的
SHA 是 `provenance_documentation_sha`，不得回填进候选代码或镜像 label。

S4 image `b805d0d` / `sha256:0c93c04b15501b9db536016a729a6520252fca445dc0746a4f04c335f54de26e`
仅作祖先证据，已 superseded for S5 exit。不得表述为当前 HEAD 已通过 S5 container gate。

Finding 关闭提交 `e7a6e42` 是 exact S5 code candidate；本 Step E 未夹带 tracked
build-input 修改。

## Identity and build gate

```text
local worktree: /root/git-project/gateway-data-management-system
local HEAD:     e7a6e42d961a75c5a35a385bd67d9417779c22b5
remote worktree: /home/issac/gateway-gate-e7a6e42d961a
remote HEAD:    e7a6e42d961a75c5a35a385bd67d9417779c22b5
worktree_clean: yes (local and remote detached checkout)
ssh: issac@10.10.60.4
candidate_delivery: git bundle 3616ef0d..phase1/gate-ownership-repair
  -> refs/gate/candidate-s5
  -> git worktree add --detach /home/issac/gateway-gate-e7a6e42d961a e7a6e42d
manifest_schema: gateway.p2r1.effective-input-manifest
manifest_schema_version: 1
digest_encoding_version: 1
identity_schema: gateway.p2r1.build-identity
identity_schema_version: 1
exact_input_inventory:
  source_roots:
    - vnext/repository_service
    - vnext/repository_contracts
  build_definition_paths:
    - vnext/.dockerignore
    - vnext/deploy/compose.yaml
    - vnext/scripts/build-repository-service-image.sh
  helper/manifest:
    - vnext/repository_service/tests/support/build_context_digest.py
    - vnext/repository_service/tests/support/repository_image_inputs.json
local_helper_identity:
  candidate_sha: e7a6e42d961a75c5a35a385bd67d9417779c22b5
  build_input_revision: e7a6e42d961a75c5a35a385bd67d9417779c22b5
  source_tree_sha256: sha256:8a0ecd681b3115cd9a64a951fcdba92b0a3e300bbd6b69a880e19b34e6e70383
remote_helper_identity: identical to local_helper_identity
uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
build_command: vnext/scripts/build-repository-service-image.sh (remote, retained cache)
build_started_at: 2026-08-15T12:10:24Z
build_finished_at: 2026-08-15T12:11:12Z
cache_endpoint: http://172.17.0.1:18080 (HTTP 200)
cache_status: retained artifact cache; dependency-base tag
  gateway-p2r1-repository:lock-6dc9659f0aee was absent, so the formal script used
  DOLT_DOWNLOAD_URL/UV_BOOTSTRAP_INDEX_URL from the cache rather than USE_PRELOADED_DEPENDENCIES=1
build_args:
  CANDIDATE_SHA=e7a6e42d961a75c5a35a385bd67d9417779c22b5
  BUILD_INPUT_REVISION=e7a6e42d961a75c5a35a385bd67d9417779c22b5
  SOURCE_TREE_SHA256=sha256:8a0ecd681b3115cd9a64a951fcdba92b0a3e300bbd6b69a880e19b34e6e70383
  UV_LOCK_SHA256=6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image: gateway-repository-service:e7a6e42d961a
image_id: sha256:1a8b6d2b706d7351d7392d9c2b42ac44aedea9818ac6c53bf87477af4c5a7ecb
remote_image_id: sha256:1a8b6d2b706d7351d7392d9c2b42ac44aedea9818ac6c53bf87477af4c5a7ecb
local_image_id:  sha256:1a8b6d2b706d7351d7392d9c2b42ac44aedea9818ac6c53bf87477af4c5a7ecb
image_label org.opencontainers.image.revision: e7a6e42d961a75c5a35a385bd67d9417779c22b5
image_label gateway.p2r1.build-input-revision: e7a6e42d961a75c5a35a385bd67d9417779c22b5
image_label gateway.p2r1.source-tree-sha256: sha256:8a0ecd681b3115cd9a64a951fcdba92b0a3e300bbd6b69a880e19b34e6e70383
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_label gateway.p2r1.dolt-version: 2.1.11
image_label gateway.p2r1.uv-version: 0.11.28
image_label gateway.p2r1.mysql-connector-version: 9.7.0
image_label gateway.p2r1.pyarrow-version: 25.0.0
image_matches_build_context: true
verify_transferred_image: true
transfer: ssh remote `docker save` streamed to local `docker load`
provenance_doc_in_verified_digest: no
```

candidate 与 build-input 因同一 finding-closure commit 恰好相等，仍作为两个独立字段
计算、写入 label 并逐一比较。S4 image 缺少 `gateway.p2r1.build-input-revision`，
directed different-ID case 对其 fail closed。

## Directed classification and launcher gate

Directed probe 脚本位于 gate host `/tmp/s5_step_e_classify.py`、
`/tmp/s5_step_e_manifest_faults.py`、`/tmp/s5_step_e_launcher_preflight.sh` 与
`/tmp/s5-step-e-preflight.sh`（非 production surface，未提交）。分类在 throwaway
clone `/tmp/s5-step-e-classify` 上执行，未修改 exact candidate worktree。

1. **Canonical helper local/remote identity**：**PASSED**。clean local checkout 与
   remote detached worktree 输出完全相同的 versioned identity JSON。

2. **docs-only fixture**：**PASSED**。只改变 `candidate_sha`；`build_input_revision`、
   `source_tree_sha256` 与 lock SHA 保持
   `e7a6e42d` / `sha256:8a0ecd681b3115cd9a64a951fcdba92b0a3e300bbd6b69a880e19b34e6e70383` /
   `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`。

3. **source fixture**：**PASSED**。`vnext/repository_service/README.md` 改变
   candidate、build-input 与 source digest。

4. **lock fixture**：**PASSED**。`uv.lock` 改变 candidate、build-input、source digest
   与 lock SHA。

5. **Dockerfile fixture**：**PASSED**。Dockerfile 改变 candidate、build-input 与
   source digest；lock SHA 稳定。

6. **`.dockerignore` / build script fixtures**：**PASSED**。二者都改变 candidate 与
   build-input；source digest 保持
   `sha256:8a0ecd681b3115cd9a64a951fcdba92b0a3e300bbd6b69a880e19b34e6e70383`。

7. **dirty fixtures**：**PASSED**。tracked、untracked、unmerged 均使 helper 与
   `build-repository-service-image.sh` 在 Docker 调用前失败（`worktree is dirty`）；
   launcher 非零且无 docker/systemctl sentinel。helper_rc=1，build_rc=1，
   launcher_rc=2。

8. **exact candidate remote retained-cache build**：**PASSED**。三个主 labels 与
   lock/tool labels 精确匹配 helper。

9. **stale/missing/malformed label 与 v2/legacy manifest**：**PASSED**，全部非零且
   无 formal output：

   | case | result |
   | --- | --- |
   | launcher tag-only `gateway-repository-service:e7a6e42d961a` | rc=2, `formal image reference must be an immutable sha256 ID`, empty stdout |
   | launcher different-ID S4 `sha256:0c93c04b...` | rc=2, missing/malformed identity fields, empty stdout |
   | launcher stale candidate label | rc=2, `image candidate label does not match source` |
   | launcher missing build-input label | rc=2, missing/malformed identity fields |
   | launcher malformed source-tree label | rc=2, `source tree label is invalid` |
   | launcher stale source-tree label | rc=2, `image source tree digest does not match source` |
   | matrix v2 manifest | `provenance_manifest_valid=false`, `build_revision=unknown`, `image_digest=unknown` |
   | matrix legacy-only `build_revision` | same fail-closed, no formal identity |
   | matrix missing/malformed candidate or build-input | same fail-closed |
   | matrix CLI/env cannot override verified candidate | `metadata_complete=false`, `build_revision=unknown` |
   | valid v3 control | accepted; `build_revision` maps to candidate |

10. **`docker save | load`**：**PASSED**。local immutable image ID 与 remote 一致。
    harness `image_matches_build_context=true`，`verify_transferred_image=true`。
    以 S4 image ID 作为 expected ID 对照当前 loaded image 时
    `verify_transferred_image=false`。launcher 拒绝 tag 作为 formal reference。

11. **target launcher preflight**：**PASSED**。remote 与 local 均从 candidate launcher
    提取 `image_metadata` + `clean_source_metadata`，消费同一 helper/manifest，接受
    exact image ID。未创建 run directory、systemd unit、Compose project 或 measurement
    output；未运行 v8 formal matrix、W1/W2 或 S7 lifecycle。

12. **Teardown inventory this round**：**PASSED**。

```text
this_round_containers: 0
this_round_networks: 0
this_round_volumes: 0
this_round_run_dir: absent (/run/gateway-p2r1)
this_round_systemd_runner_units: none
fault_images_removed: s5stepe-stale-candidate, s5stepe-missing-build-input,
  s5stepe-malformed-tree, s5stepe-stale-tree
retained_evidence_image: gateway-repository-service:e7a6e42d961a
preexisting_remote_residue_not_this_round:
  dependency-base probe containers from 2026-08-02..08-09
  gateway-p2r1-20260803*_repository-data volumes
```

## Docker record

```text
Current HEAD: e7a6e42d961a75c5a35a385bd67d9417779c22b5
Container rebuild required: yes (executed at Step E)
Reason: S5 exact candidate; Docker/build/launcher identity boundary superseded S4 b805d0d image
Last verified image revision (S4, superseded): b805d0d5f3c6164875319bd5e4b7b12d998cfe96
Last verified source-tree/image id (S4):
  sha256:dde82b4acfc86e6561f5c195daef31a75ae7e3417f9f808da41a7af6f37ae7f6 /
  sha256:0c93c04b15501b9db536016a729a6520252fca445dc0746a4f04c335f54de26e
Container gate for current HEAD: passed
Deferred gates/nodeids: none for S5 identity exit; W1/W2, Compose lifecycle, canonical v8
  and Phase 2 exit remain S6/S7/S10
Required execution point: S5 exact-candidate Step E
```

```yaml
validated_code_sha: e7a6e42d961a75c5a35a385bd67d9417779c22b5
container_validated_code_sha: e7a6e42d961a75c5a35a385bd67d9417779c22b5
provenance_documentation_sha: <this commit>
candidate_sha: e7a6e42d961a75c5a35a385bd67d9417779c22b5
build_input_revision: e7a6e42d961a75c5a35a385bd67d9417779c22b5
source_tree_sha256: sha256:8a0ecd681b3115cd9a64a951fcdba92b0a3e300bbd6b69a880e19b34e6e70383
image_id: sha256:1a8b6d2b706d7351d7392d9c2b42ac44aedea9818ac6c53bf87477af4c5a7ecb
production_retest_required: yes
phase_2_complete: no
P2-R6-S5_exit: pass
P2-R6-S6_ready: no
external_blocker: external W1 descriptor is not present; S5 pass does not imply S6 entry
```

# P2-R6-EXT-W1 Stage J — Final image and lifecycle gates

状态：`pass`

日期：2026-08-16

本记录在 Stage I 收口 SHA 上重建当前 HEAD 的 production image，跑完五包
ruff/mypy 与权威源码测试，并收集现有 Compose lifecycle 与 ENUM/SET 容器证据。
这不是完整 Phase 2 S7/S10 退出，也不把祖先 S5 镜像写成当前 HEAD 已验证。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
S5 历史镜像：[P2-R6-S5 Step E container gate](p2-r6-s5-step-e-container-gate.md)
Stage I S6：[P2-R6-EXT-W1 Stage I S6 Capacity](p2-r6-ext-w1-stage-i-s6-capacity.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
stage_j_entry_head_sha: 656a66bf04714cce987c85649246c3767b2586e2
stage_i_close_sha: 656a66bf04714cce987c85649246c3767b2586e2
stage_i_entry_head_sha: 108cb90d75884acfd6c6f9cd388edc9c20a33aaf
stage_h_reviewed_commit_sha: 7f068a2454addaded6eecd450e05571d6c939e8c
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
stage_i_is_ancestor: yes
worktree_clean_at_build: yes
package_version: v1
canonicalization_version: v1
image_rebuilt: yes
production_code_changed: no
contract_changed: no
```

HEAD 为 Stage I 收口 `656a66bf`（`feat(backend): close Stage I S6 capacity, W2, and concurrency matrix`）。
S5 候选 `e7a6e42d` 与 Stage I 入口 `108cb90d` 仍是祖先。构建与 Compose 期间 worktree
clean。本记录在 image 构建之后写入，因此后续 docs commit 的
`provenance_documentation_sha` 不等于 `container_validated_code_sha`。

## Source quality

五个包 `uv run ruff check . && uv run mypy` 全部通过：

| package | ruff | mypy |
| --- | --- | --- |
| shared_kernel | pass | 34 files |
| repository_contracts | pass | 15 files |
| repository_client | pass | 26 files |
| backend | pass | 26 files |
| repository_service | pass | 191 files |

权威脚本（重建前，排除会触发本机构建的 Compose e2e）：

```bash
./vnext/scripts/run-tests.sh --ignore=tests/test_import_compose_e2e.py
```

| suite | result |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 150 passed |
| backend | 35 passed, 1 warning |
| repository_service parallel (`not serial`) | 1591 passed, 1 skipped in 342.85s |
| repository_service serial | 158 passed, 1592 deselected in 295.62s |

## Image identity and build

Local helper 与 remote detached worktree 输出相同：

```text
schema: gateway.p2r1.build-identity
schema_version: 1
candidate_sha: 656a66bf04714cce987c85649246c3767b2586e2
build_input_revision: 02502f9aaf69d1c7573b9e0b4212b8b3a18e286d
source_tree_sha256: sha256:f6dc57cb635482b5c5287746ba5da956db7d56fcd9bc461ff942e04d514a785e
uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
```

本机 `http://172.17.0.1:18080` 返回 502，正式脚本在构建 Docker 调用前 fail closed。
沿用 S5：把 `3616ef0d..HEAD` bundle 送到 `issac@10.10.60.4`，detached checkout
`/home/issac/gateway-gate-656a66bf0471`，在远端跑
`vnext/scripts/build-repository-service-image.sh`。dependency-base
`gateway-p2r1-repository:lock-6dc9659f0aee` 不存在，脚本使用 retained artifact cache
而非 `USE_PRELOADED_DEPENDENCIES=1`。未使用 `p2-r6-final` tag。

```text
remote worktree: /home/issac/gateway-gate-656a66bf0471
remote HEAD: 656a66bf04714cce987c85649246c3767b2586e2
local HEAD:  656a66bf04714cce987c85649246c3767b2586e2
worktree_clean: yes
s5_image_superseded: e7a6e42d961a75c5a35a385bd67d9417779c22b5 / sha256:1a8b6d2b706d7351d7392d9c2b42ac44aedea9818ac6c53bf87477af4c5a7ecb
build_command: vnext/scripts/build-repository-service-image.sh (remote, retained cache)
build_started_at: 2026-08-16T06:56:54Z
build_finished_at: 2026-08-16T06:57:38Z
cache_endpoint: http://172.17.0.1:18080 (HTTP 200 on 10.10.60.4)
image: gateway-repository-service:656a66bf0471
image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
remote_image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
local_image_id:  sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
image_label org.opencontainers.image.revision: 656a66bf04714cce987c85649246c3767b2586e2
image_label gateway.p2r1.build-input-revision: 02502f9aaf69d1c7573b9e0b4212b8b3a18e286d
image_label gateway.p2r1.source-tree-sha256: sha256:f6dc57cb635482b5c5287746ba5da956db7d56fcd9bc461ff942e04d514a785e
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_label gateway.p2r1.dolt-version: 2.1.11
image_label gateway.p2r1.uv-version: 0.11.28
image_label gateway.p2r1.mysql-connector-version: 9.7.0
image_label gateway.p2r1.pyarrow-version: 25.0.0
image_matches_build_context: true
verify_transferred_image: true
transfer: ssh remote `docker save` streamed to local `docker load`
transfer_started_at: 2026-08-16T06:57:52Z
transfer_finished_at: 2026-08-16T06:59:30Z
```

## Compose lifecycle and necessary container gates

1. Existing S7 inventory nodeid（BIGINT restart/replay）：

```bash
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:656a66bf0471 \
  uv run pytest -m 'integration and serial' -n 0 \
  tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
```

**PASSED (36.24s)**。`ensure_repository_service_image()` 因 label 匹配当前 build
context 未再 rebuild。

2. EXT-W1 directed probe（throwaway `/tmp`，未提交）：同一 image 导入
   `/root/test-data/small_cut/package.tar.zst`（83838 bytes，
   `sha256:54fbe736d486216a44a0bcf9b81a0fc3c1d2afe5a900f3afc5ee2eb7e068de43`），
   `FULL_SCAN`+`REJECT`。project `gateway-p2r6-ext-w1-j-b15d77c4580f`。

```json
{
  "status": "SUCCEEDED",
  "completed_verification_policy": "FULL_SCAN",
  "canonicalization_manifest_digest": "sha256:459eb8e3abbaa58ae36aef4febe92131624f206eea9d5e0eef9d13abbd740d5a",
  "catalog_status": "pass",
  "table_count": 132,
  "stream_table": "device_model_table",
  "streamed_rows": 1678,
  "unknown": 0,
  "lossy": 0,
  "enum_cols": 5,
  "set_cols": 0
}
```

digest 与 Stage H 已发布 small_cut 字面量一致。stream 表含 5 列 ENUM、unknown=0、
lossy=0。package 级 1 列 SET 由 `FULL_SCAN`+`REJECT` 整包成功覆盖；该抽样表本身
没有 SET 列。

3. 本轮 Compose project 残留：container/network/volume = 0。失败的第一次探针
   `gateway-p2r6-ext-w1-j-67d162556e81` 也已 `down -v`，残留为 0。

未复用 S5 `e7a6e42d` 镜像关闭本 gate。

## Not in this record

以下仍归 [P2-R6 Operational Closure](../formal/plans/p2-r6-operational-closure-execution-plan.md)
S7/S10，本 stage 不宣称 `phase_2_complete`：

- `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network`（文件不存在）
- `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host`（文件不存在）
- fresh/restart/restored snapshot Compose harness
- Candidate A 66-record v8 `--runs 5`
- tag `gateway-repository-service:p2-r6-final`

未改 Contract、未改五份 SQL、未改写历史 S5 evidence。

## Docker / Compose

```text
Current HEAD: 656a66bf04714cce987c85649246c3767b2586e2
Container rebuild required: yes
Reason: Stage J final EXT-W1 candidate; production ENUM/SET code superseded S5 image e7a6e42d
Last verified image revision: 656a66bf04714cce987c85649246c3767b2586e2
Last verified source-tree/image id: sha256:f6dc57cb635482b5c5287746ba5da956db7d56fcd9bc461ff942e04d514a785e / sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
Container gate for current HEAD: passed
Deferred gates/nodeids: P2-R6-S7/S10 versioned-read compose e2e (absent), restored snapshot compose, v8 formal 66-record
Required execution point: Stage J final EXT-W1 image/lifecycle
```

```yaml
stage_j_exit: pass
image_rebuilt: yes
image_matches_build_context: true
compose_restart_replay: pass
small_cut_container_full_scan: pass
enum_set_unknown_or_lossy: no
phase_2_complete: no
next: Stage K — Final handoff
```

# P2-R6-S6 Entry Readiness — R6-EXT-W1

状态：`stage_k_handoff_pass`

本记录处理 `R6-EXT-W1` 的外部入口准备与 package validator gate。Stage H 已发布
五份 v1 `canonicalization_manifest_digest`，并将 `P2-R6-S6_ready` 改为 `yes`。
Stage I 已在同一五份 package 上完成 S6 capacity、synthetic W2 与 1/4/8
concurrency matrix。Stage J 已按当前 HEAD 重建 image 并收集现有 Compose
lifecycle 与 small_cut 容器 FULL_SCAN 证据。这仍不是完整 Phase 2 S7/S10 退出。
Stage K 已完成独立只读 handoff，发布脱敏 descriptor，并确认本轮没有新增 blocker。

权威审核：[P2-R6-EXT-W1 Stage H Validator Gate Review](p2-r6-ext-w1-stage-h-validator-gate-review.md)
Stage I S6：[P2-R6-EXT-W1 Stage I S6 Capacity](p2-r6-ext-w1-stage-i-s6-capacity.md)
Stage I W2：[P2-R6-EXT-W1 Stage I W2](p2-r6-ext-w1-stage-i-w2.md)
Stage I concurrency：[P2-R6-EXT-W1 Stage I Concurrency Matrix](p2-r6-ext-w1-stage-i-concurrency-matrix.md)
Stage G 证据：[P2-R6-EXT-W1 Stage G Production Validator](p2-r6-ext-w1-stage-g-production-validator.md)
Stage F 包：[P2-R6-EXT-W1 Stage F Five-fixture Packages](p2-r6-ext-w1-stage-f-five-fixture-packages.md)
Stage J 镜像：[P2-R6-EXT-W1 Stage J Final Image and Lifecycle](p2-r6-ext-w1-stage-j-final-image-lifecycle.md)
Stage K handoff：[P2-R6-EXT-W1 Stage K Final Handoff](p2-r6-ext-w1-stage-k-final-handoff.md)
脱敏 descriptor：[P2-R6-EXT-W1 external descriptor](p2-r6-ext-w1-external-descriptor.yaml)

## Entry identity

原始 S6 入口准备（历史，保持不变）：

```yaml
start_sha: b5b4cca3310959f45cc527ab3e7d4eb1754d12d3
head_sha_at_preparation: b5b4cca3310959f45cc527ab3e7d4eb1754d12d3
```

Stage H 发布身份：

```yaml
branch: phase1/gate-ownership-repair
stage_h_reviewed_commit_sha: 7f068a2454addaded6eecd450e05571d6c939e8c
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
worktree_clean_at_stage_h_review: yes
selected_w1: medium
selection_reason: default representative W1; package gate now passed on all five positive fixtures
package_version: v1
canonicalization_version: v1
```

Stage I 测量身份：

```yaml
stage_i_entry_head_sha: 108cb90d75884acfd6c6f9cd388edc9c20a33aaf
s6_capacity: pass
w2: pass
concurrency_matrix: pass
w2_replay_sql_bytes: 201681690
w2_package_bytes: 8301271
w2_package_sha256: sha256:6cac7852d1174c126c182e82010b0ff9d4043e51826b8043103360c8e49f6d10
w2_canonicalization_manifest_digest: sha256:895732a5bbfcc406b9a5edab24ff742186fb5f268ce68ca5774a798b2bd2b32f
```

Stage J 镜像身份：

```yaml
stage_j_entry_head_sha: 656a66bf04714cce987c85649246c3767b2586e2
container_validated_code_sha: 656a66bf04714cce987c85649246c3767b2586e2
image: gateway-repository-service:656a66bf0471
image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
source_tree_sha256: sha256:f6dc57cb635482b5c5287746ba5da956db7d56fcd9bc461ff942e04d514a785e
image_matches_build_context: true
compose_restart_replay: pass
small_cut_container_full_scan: pass
```

The selected source descriptor facts remain independently recomputed:

```yaml
source_sql_bytes: 49323598
source_sql_sha256: sha256:78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f
source_sql_utf8: pass
source_descriptor_consistent: yes
```

Direct replay into a temporary Dolt repository using exact Dolt `2.1.11` previously
returned 199 tables. That preflight is not S6 capacity evidence. Production
validator evidence is Stage G + Stage H.

## Canonicalization and package result

v1 identity-projection producer（Backend Storage Projection）已替换尚未发布的
one-off scheme 的内容定义。算法标识保持
`gateway-vnext:canonicalization-manifest:v1`。Repository 仍把
`canonicalization_manifest_digest` 当作 opaque 保存和回显。

selected W1（medium）：

```yaml
canonicalization_manifest_authority: v1 identity-projection producer
canonicalization_algorithm: RFC8785-JCS + gateway-vnext:canonicalization-manifest:v1\0 + SHA-256
canonicalization_manifest_digest: sha256:73dd240b234b26ec006aa78a5e73f2ac9a5105eabe9e9f5dd19a82c858d6b26c
formal_package_media_type: application/vnd.gateway.repository-import.v1+tar+zstd
formal_package_bytes: 2081228
formal_package_sha256: sha256:3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e
source_sql_bytes: 49323598
source_sql_sha256: sha256:78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f
```

全部五份正向 fixture（live `package.tar.zst` size/SHA 已由 Stage H 独立复算）：

```yaml
fixtures:
  small_cut:
    package_bytes: 83838
    package_sha256: sha256:54fbe736d486216a44a0bcf9b81a0fc3c1d2afe5a900f3afc5ee2eb7e068de43
    canonicalization_manifest_digest: sha256:459eb8e3abbaa58ae36aef4febe92131624f206eea9d5e0eef9d13abbd740d5a
  small:
    package_bytes: 613635
    package_sha256: sha256:e440af6963d99315ef632fcf34f57741de0791ec9a8942ce284b2900efbf82c3
    canonicalization_manifest_digest: sha256:5c01406aba92537be95b3ba904e6ff092661c7bce30352f3369bdf3cc6958b49
  medium:
    package_bytes: 2081228
    package_sha256: sha256:3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e
    canonicalization_manifest_digest: sha256:73dd240b234b26ec006aa78a5e73f2ac9a5105eabe9e9f5dd19a82c858d6b26c
  data2:
    package_bytes: 3173874
    package_sha256: sha256:72a266b25f2712d8f23f3010937693dc4a5a41dd93e2cb237928f711aa0fc813
    canonicalization_manifest_digest: sha256:c1cad27c519695ba9701cdf4b5572714dfcab295355bd614f42a0d5fad53e340
  data1:
    package_bytes: 5724227
    package_sha256: sha256:bd607ecbca4890d273188f93d1020fa32e2cc0cbd5f6f9ffdbfcffe49feb9bf2
    canonicalization_manifest_digest: sha256:29a37b49168a04da8e802471f8eaf6221b64abbdef16eb64cc1ba9fa848dd435
```

ENUM/SET 已进入 v1 Contract 并被 production validator 接受。medium catalog 扫描为
327 ENUM + 1 SET（readiness 预检曾记 328）；权威是 Stage F/G catalog。五份
unknown=0、lossy=0，无 stringify、无 SQL-type rewrite、无伪造 digest。

```yaml
schema_and_public_facts_preflight: superseded by Stage G FULL_SCAN+REJECT
production_validator_result: pass
read_only_access_proof: local dataset.yaml plus retained package.tar.zst under /root/test-data; raw SQL not in git
external_descriptor_sha256: sha256:416eb412d7e9ec389bb0dffae5511b016937ae1e29790cc3e26b549eb772205f
external_descriptor_bytes: 2682
external_descriptor_status: republished sanitized summary; no raw SQL, full schema values, rows, secrets, host paths or formal package
raw_payload_in_git: false
runtime_cleanup: pass; Stage G work root removed
```

The previously published 2746-byte descriptor was not retained on this host. Stage K replaced
that unavailable artifact with the recorded 2682-byte sanitized summary. The replacement contains
only fixture aliases, package/digest summaries, bounded counts and gate results; it contains no raw
SQL, full schema values, rows, secrets, host paths or formal package.

## Handoff

```yaml
owner_anonymization_approval: owner-declared fully desensitized
repository_files_recorded: this readiness record, Stage J evidence, Stage K handoff and sanitized descriptor
container_rebuild_required: yes
production_retest_required: yes
phase_2_complete: no
R6-EXT-W1: yes
P2-R6-S6_ready: yes
s6_capacity: pass
w2: pass
concurrency_matrix: pass
image_rebuilt: yes
remaining_blockers: []
deferred_scope:
  - P2-R6-S7/S10 versioned-read compose e2e, restored snapshot compose, v8 formal
```

Stage I HTTP 路径（uvicorn + `ServiceRuntime`）五份正向 package 全部 accepted。
synthetic W2 replay 201681690 bytes（192.3 MiB）FULL_SCAN pass；不是业务代表性。
concurrency 1/4/8 与第 9 路 `503 SERVICE_NOT_READY` pass。

Stage J 按 `656a66bf` 重建 production image
`sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296`，Compose
restart/replay 与 small_cut 容器 FULL_SCAN 通过。历史 S5 Step E evidence 仍绑定
`e7a6e42d`，不得表述为当前 HEAD。`phase_2_complete` 仍为 `no`：缺失的
versioned-read compose e2e、restored snapshot 与 v8 formal 归 P2-R6-S7/S10。
Stage K 只读审核本轮 fixture/package/validator/capacity/container evidence。

```yaml
stage_k_exit: pass
stage_k_reviewed_documentation_head_sha: 352d9097ddf26fb3e68397430f45d2e479473e51
container_validated_code_sha: 656a66bf04714cce987c85649246c3767b2586e2
history_s5_unchanged: yes
new_blocker_count: 0
phase_2_complete: no
production_retest_required: yes
next: P2-R6-S7/S10 operational closure
```

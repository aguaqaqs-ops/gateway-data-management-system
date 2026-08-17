# P2-R6-S10 Step 9 — Final packet and zero-residual audit

状态：`pass`（packet complete、hash consistent、zero owned residual；不授予
independent review、S10 seal、S10 exit 或 Phase 2）

日期：2026-08-17

本记录在 S10-8 Candidate A v8 formal `go` 之后，于冻结 candidate
`2ef884278b4998dde1e5fe224532c89b7a0cd73a` 上重算 identity、交叉核对
S10-0～S10-8 权威哈希、分类失败 attempt、删除 S10-4 `docker save` archive 与已
recover 的 S10-7 attempt-4 quarantine，并确认 owned residual 为零。未修改
candidate、Dockerfile、Compose、lock、adapter 或 image tag。未重跑 no-ignore、
W1/W2、W0 或 v8。失败 attempt 证据文件全部保留。本步不启动 S10-10，不写
S10-11 external seal。

权威步骤：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §11
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.6
S10-4：[p2-r6-s10-step-4-final-artifacts.md](p2-r6-s10-step-4-final-artifacts.md)
S10-5：[p2-r6-s10-step-5-no-ignore-compose.md](p2-r6-s10-step-5-no-ignore-compose.md)
S10-6：[p2-r6-s10-step-6-w1-w2-production-repeat.md](p2-r6-s10-step-6-w1-w2-production-repeat.md)
S10-7：[p2-r6-s10-step-7-w0-smoke.md](p2-r6-s10-step-7-w0-smoke.md)
S10-8：[p2-r6-s10-step-8-v8-formal.md](p2-r6-s10-step-8-v8-formal.md)

机器可读清单：`/root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/artifacts/s10-9/inventory.json`

## Recomputed identity

本地 `/root/gateway-s9-candidate-2ef88427` 与远端
`/home/issac/gateway-s10-candidate-2ef88427` 的 helper 输出相同；两端
`git status --porcelain` 为空；`git diff --check` pass。Service/Client labels
与 S10-4 逐字段相等。`GATEWAY_REPOSITORY_SERVICE_IMAGE` unset。

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:p2-r6-final
service_image_also_tagged: gateway-repository-service:local
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
historical_s9_tag_retained: gateway-repository-service:2ef884278b49
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
host_runner_identity: host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
adapter_sha256: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
installed_launcher_sha256: 2782a83f4465f1d9505a5347e1cc418ebd64f8fe73e2e9964d5235945da54a88
gate_host: issac@10.10.60.4
docker_daemon_id: dc91db82-3d49-41a4-a63c-f23dda721890
compose: 5.4.0
cache_http: 200
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
worktree_clean: yes
phase_2_complete: no
```

文档 worktree HEAD 仍是 `0f9536c2`，docs-only，不是 image input。未跟踪文件均为
S10 证据记录（含本 packet）。candidate `vnext/` 相对 `2ef88427` 无改动。

## Hash cross-check

对照 S10-4 labels/archive metadata、S10-5 权威日志、S10-6 sanitized W1/W2、
S10-7 W0、S10-8 v8 三件套与各步证据文档已记录 SHA。23 项 live 重算全部匹配，
0 mismatch。失败/被取代 attempt 字节未改写。

权威对象：

```text
af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150  adapter/s10_w1_w2_audit_adapter.py
59ae8de26c5a8e1b68d1af0a0308c5c721cc825b9d236dc4b98cd0c92983f2c7  s10-5-run-tests.log
365712104a784579be1d439c438a23eaf610fbb06bdba818a1dab42a2944a573  s10-6/attempt-2-w1/w1-medium.json
0f18233493b397d1da49eb923591ab47c2873ca23c0a4d1516eaa34882c7a017  s10-6/attempt-2-w2/w2.json
0720b5a1eec0fe5d9670d7757120490655436a125b2ebf1962b89b07796bdeab  s10-7/attempt-5/a-w0.jsonl
9dcdd1b458ec96a7391dc5cb96619155c02edaa6e17d5cd763abf42bf1d0a256  s10-8/attempt-1/p2-r1.jsonl
f530c36f331cc26e4c6fa8118a71ded8b0ca0d9d7225309f96ff9233cf327a4e  s10-8/attempt-1/p2-r1.summary.json
0e2054c762073cfef093b75ea8159ffb72012c1bd28c5d05591c7e0bebf1ec57  s10-8/attempt-1/p2-r1.md
f2416c49c0e6b712fdf59fb2db7ba5bd62c81cdeefe67b83155b852cf6ed2245  docker-save archive (deleted after match)
```

完整树哈希见 `artifacts/s10-9/audit-tree-SHA256SUMS` 与 `inventory.json`。

## Attempt ledger

失败与被取代记录全部保留，不得改写成 pass。

| step | attempt | status | note |
| --- | --- | --- | --- |
| S10-0 | 1 | fail | `S10_entry_ready: no` |
| S10-0 | 2 | pass | operator repair after S10-1 fail |
| S10-1 | 1 | fail | `review_status: fail` |
| S10-1 | rerun | pass | `allow_s10_implementation: yes` |
| S10-2 | 1 | superseded | adapter `b758febd…` |
| S10-2 | 2 | superseded | adapter `6282df80…` |
| S10-2 | 3 | pass | adapter `af672fa0…` |
| S10-3 | 1 | fail | adapter review fail |
| S10-3 | rerun | superseded | pass on attempt-2 adapter |
| S10-3 | rerun-2 | pass | `allow_w1_w2_execution: yes` |
| S10-4 | 1 | pass | final Service/Client/archive |
| S10-5 | 1 | pass | no-ignore + 8 Docker nodeids |
| S10-6 | 1 | fail | leftover named volume；adapter defect |
| S10-6 | 2 | pass | W1/W2 hard gates |
| S10-7 | 1–4 | fail | tag-only / git identity / cgroup EROFS |
| S10-7 | 5 | pass | W0 diagnostic only；非 formal |
| S10-8 | 1 | pass | 66/66 `formal_status=go` |

## Counts / Compose / W1/W2 / v8

摘录权威步骤，不重跑。

| suite | collected | passed | skipped | failed |
| --- | ---: | ---: | ---: | ---: |
| shared_kernel | 242 | 242 | 0 | 0 |
| repository_contracts | 152 | 152 | 0 | 0 |
| repository_client | 154 | 154 | 0 | 0 |
| backend | 35 | 35 | 0 | 0 |
| repository_service parallel | 1639 | 1638 | 1 | 0 |
| repository_service serial | 205 | 205 | 0 | 0 |

service total 1844 = 1639 + 205。唯一 skip：
`tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup`
（delegated-target cgroup；expected）。八个 Docker-starting nodeid 在 serial 段
原文 `PASSED`，per-node inventory 0。权威命令 `exit_code=0`。

W1 medium / W2 attempt-2：`status=SUCCEEDED`、`container_pass=pass`、final
inventory 全 0、packages 已从 staging 删除。W0 smoke `diagnostic_only=true`，
不得当作 S10-8 formal。v8 attempt-1：66 unique、30/36、11 warm-up / 55
measured、A `candidate_a_offline_cli` selected、B `reserved_not_evaluated`、
`formal_status=go`、`formal_decision=true`。v8 artifact 内历史
`production_retest_required: true` 不是 S10 stage 字段。

## Zero-residual

S10-4 写明 archive 保留到 packet 后再删。删除前重算
`sha256:f2416c49c0e6b712fdf59fb2db7ba5bd62c81cdeefe67b83155b852cf6ed2245` /
332429824 bytes，与 [archive-metadata.txt](/root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/artifacts/s10-4/archive-metadata.txt)
一致，然后 `rm`。S10-7 attempt-4 日志已在 audit；按 launcher「recover then
remove」删除 volume `gateway-p2r1-20260817150124_3123221_repository-data` 与空
staging dir。S10-named `/tmp` wrapper/log/pub 副本在与 audit 哈希一致后删除。
S10-5 `pytest-of-root/pytest-25..27` 含 nodeid token，作为 owned scratch 删除。

删除后扫描：Compose container/network = 0；本 run volume = 0；dolt = 0；
runner unit = 0；slice inactive；work-root 不存在；staging 空；archive 不存在。

分类保留（不是本 run owned residual，未删）：

- 2026-08-03 三份 `gateway-p2r1-20260803*_repository-data`
- host 空 cgroup `/sys/fs/cgroup/gateway-p2r1`（S10-7 环境修复；`child_dirs=0`）
- retained cache `gateway-p2r1-dependency-cache.service` / `http://172.17.0.1:18080`
- 最终 Service/Client image tags
- 2026-03-11 anonymous volume 与 `open-webui`
- `/tmp/pytest-of-issac`（08:02+08，早于本 run）、`/tmp/pytest-of-tmpuser`（08-11）
- `/tmp/compose-pkg.tar.zst`（345 bytes，08-09，不是 W1/W2 包）

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no
Reason: S10-4 已重建 final image；S10-5～S10-8 已在该 identity 上跑完 mandatory
  container gates；本步仅 packet/hash/residual
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: passed on candidate identity (docs-only worktree is not an image input)
Deferred: S10-10 independent review; S11 docs-only must not change container identity
```

本步不把 `container_validated_code_sha` 写成已 seal；那是 S10-11 字段。

## External audit artifacts

```text
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/artifacts/s10-9
remote_audit_root: /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z
log_copied_to_docs_worktree: no
candidate_wrote_log: no
2a3f355a24207beff87090e16474ec9550e79237a352399baa73d734302a90ad  inventory.json
bd5c2962736c3acd3e4945dd9a85ffa1eb3e4a8657f73a8a9eb8333cf3a3e504  residual-after.txt
```

## Exit

```yaml
s10_9_status: pass
packet_complete: yes
hash_crosscheck: pass
zero_owned_residual: yes
archive_removed: yes
s10_7_attempt_4_quarantine_removed: yes
historical_volumes_classified_not_deleted: yes
host_cgroup_mountpoint_retained: yes
identity_unchanged: yes
retry_as_pass: no
container_validated_code_sha: deferred
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-10 independent final production-gate review in a new conversation
```

下一步必须**新开对话**做只读 S10-10。审核人读本 packet、attempt ledger 与 raw
artifacts，不得修复证据、重跑命令、retag image 或写 external seal。本记录不构成
S10 seal 或 Phase 2 completion。

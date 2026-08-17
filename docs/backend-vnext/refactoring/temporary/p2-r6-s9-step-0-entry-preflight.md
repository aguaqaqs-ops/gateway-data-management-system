# P2-R6-S9 Step 0 — Entry Reconciliation and Environment Preflight

状态：`complete`

日期：2026-08-17

本记录只做 S9 入口身份、S8/S7 ancestry、clean detached checkout target、
remote builder/gate-host 前置、八个 Docker nodeid 收集与预期 cgroup skip 分类。
没有修改 production/test/deployment 文件，没有构建 candidate image，没有执行
`./vnext/scripts/run-tests.sh`，也没有把 `71da5061` 或祖先 `5f474ce2` 写成
`CANDIDATE_SHA`。S9-0 不对 S9 设计做 pass/fail 判定；独立设计审核归 S9-1。

权威计划：[P2-R6-S9 Final Candidate Seal Execution Plan](../formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md) §2
权威设计：[P2-R6-S9 Final Candidate Seal Design](../formal/plans/p2-r6-s9-final-candidate-seal-design.md) §§1–7
上游 handoff：[P2-R6-S8 final handoff](p2-r6-s8-final-handoff.md)
祖先容器证据：[P2-R6-S7 final handoff](p2-r6-s7-final-handoff.md)
总计划：[P2-R6 Operational Closure Execution Plan](../formal/plans/p2-r6-operational-closure-execution-plan.md) §§8–12
测试约定：[Testing Conventions](../../../testing-conventions.md)

## Entry identity

S9-0 开始时用 `git rev-parse HEAD` 取得文档 worktree 的字面量 SHA。该 SHA 与执行计划
冻结字段 `s8_handoff_head` 一致，是 documentation-only，不是 source candidate。
本文件后续若以 docs-only 提交，仍不是 `validated_code_sha`。

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 71da506171d01bbccdf2c54137949cdd0bff234e
s8_handoff_head: 71da506171d01bbccdf2c54137949cdd0bff234e
s8_handoff_head_match: yes
s8_handoff_head_docs_only: yes
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_container_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
s8_entry_is_ancestor: yes
candidate_is_ancestor: yes
merge_base_with_candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
merge_base_with_s7: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
post_candidate_committed_delta: docs-only
production_code_dirty: no
S8_exit: pass
S9_ready: yes
production_retest_required: yes
phase_2_complete: no
```

文档 worktree 开始时 `git status --short`：

```text
 M docs/backend-vnext/refactoring/formal/README.md
 M docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md
?? docs/backend-vnext/refactoring/formal/plans/p2-r6-s9-final-candidate-seal-design.md
?? docs/backend-vnext/refactoring/formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md
```

`vnext/**` 无已跟踪或未跟踪改动。脏文件全部是 S9 规划文档与 formal 索引，不是未知
生产漂移。分类见下一节。这不构成 `S9_entry_ready: no`。identity helper 未在该脏
worktree 上运行。

`git worktree list`：

```text
/root/gateway-data-management-system 71da5061 [phase1/gate-ownership-repair]
/root/gateway-s9-candidate-2ef88427  2ef88427 (detached HEAD)
```

## Ancestry and committed delta

S8 source candidate `2ef884278b4998dde1e5fe224532c89b7a0cd73a`、S8 entry
`1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09` 与 S7 candidate
`5f474ce2ccf15f11ea07f263edf3fb04c771d410` 都是当前文档 HEAD 的祖先。
`git merge-base --is-ancestor` 四项均为 yes。

`git log --oneline --decorate 5f474ce2..HEAD`：

```text
71da5061 (HEAD -> phase1/gate-ownership-repair) docs(repository): record P2-R6-S8 final handoff
2ef88427 docs(repository): record S8-2 marker repair rerun evidence
3e4bd1fc test(repository): classify snapshot_admin subprocess tests as integration
6ddd94d7 docs(repository): record P2-R6-S8 hygiene and candidate preparation
8e42bdd6 docs(repository): record P2-R6-S8 source full regression
a27fe004 docs(repository): record P2-R6-S8 worker convergence
be2d1a03 docs(repository): record P2-R6-S8 classification and static gates
601206e4 test(repository): classify snapshot_admin CLI tests as serial
97f0f454 docs(repository): record P2-R6-S8 design review
77a43ebe docs(repository): record P2-R6-S8 entry reconciliation
1bfa1d7f docs(repository): record P2-R6-S7 final handoff
```

`git diff --name-status 2ef88427..HEAD`：

```text
M	docs/backend-vnext/refactoring/formal/README.md
M	docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md
A	docs/backend-vnext/refactoring/temporary/p2-r6-s8-final-handoff.md
A	docs/backend-vnext/refactoring/temporary/p2-r6-s8-implementation-rereview.md
A	docs/backend-vnext/refactoring/temporary/p2-r6-s8-implementation-review.md
```

`git diff --name-status 2ef88427..HEAD -- vnext` 为空。该 committed delta 是
docs-only。`71da5061` 不得作为 `CANDIDATE_SHA`。S7 `container_validated_code_sha`
仍为 `5f474ce2`；文档 HEAD 相对 image label 是 stale-by-documentation-only-delta，
不得写成当前 HEAD 的 container PASS。

## Uncommitted worktree classification

| path | status | class |
| --- | --- | --- |
| `docs/backend-vnext/refactoring/formal/README.md` | modified | current S9 formal index and stage-status wording |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md` | modified | current S9 design/plan links under the S9 stage block |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s9-final-candidate-seal-design.md` | untracked | current S9 design authority |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md` | untracked | current S9 execution authority |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s9-step-0-entry-preflight.md` | this record | S9-0 evidence; added after the status snapshot above |

```yaml
tracked_production_dirty: no
untracked_production: none
uncommitted_docs_only: yes
unknown_current_finding: none
unresolved_scope_ownership: none
```

## Candidate checkout and expected identity

`identity` helper 要求 clean worktree，且 `candidate_sha` 取自该 checkout 的 `HEAD`。
因此在文档 worktree 之外创建只读 detached worktree，不构建镜像：

```bash
git worktree add --detach /root/gateway-s9-candidate-2ef88427 \
  2ef884278b4998dde1e5fe224532c89b7a0cd73a
```

```text
candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
git_status_porcelain: empty
worktree_clean: yes
```

在该 checkout 上执行：

```bash
python3 vnext/repository_service/tests/support/build_context_digest.py identity
sha256sum vnext/repository_service/uv.lock vnext/repository_client/uv.lock
```

```text
schema: gateway.p2r1.build-identity
schema_version: 1
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
```

`build_input_revision` 是 S8 marker 修复 `3e4bd1fc`，不是 S7 的 `af36c325`，也不是
docs HEAD `71da5061`。`source_tree_sha256` 不同于 S7 的
`sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2`，因为
manifest `source_roots` 包含 `vnext/repository_service`（含测试）。两份 lock hash
与 S7 记录一致。S7 image `sha256:ba0ac70a…85849fa3` 只能作为祖先证据，不能满足
S9 candidate-bound provisional identity。S9-2 必须按本记录的 identity 构建/核对。

本步未在远端 `10.10.60.4` 创建 builder worktree；远端 checkout 仍归 S9-2。

## S8 / S7 authority

来源：[p2-r6-s8-final-handoff.md](p2-r6-s8-final-handoff.md)、
[p2-r6-s7-final-handoff.md](p2-r6-s7-final-handoff.md)。S9-0 逐项核对，不重跑
S8 三 ignore 全量，也不重跑 S7 四条 Compose nodeid。

```yaml
stage: P2-R6-S8
stage_status: pass
entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: deferred
S8_exit: pass
S9_ready: yes
production_retest_required: yes
phase_2_complete: no
```

```yaml
stage: P2-R6-S7
stage_status: pass
validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
container_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
service_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
client_image_id: sha256:d4e07d7900d70df49df6f2628cc1cf542a6e02c8772e8cab35cedf82972ee461
source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
S7_exit: pass
```

祖先（不得当作当前 candidate 已验证）：

```text
ancestor_candidate: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
ancestor_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
ancestor_source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
```

## Environment preflight

沿用 S7 retained-cache remote builder / Linux gate-host，不静默换 host 或 cache。
本步只做发现性检查：不 `compose up`、不 `docker save|load`、不构建镜像。

### Local documentation host (WSL, not gate-host)

```text
host: DESKTOP-V61T28L
kernel: Linux 6.6.114.1-microsoft-standard-WSL2 x86_64
ipv4: 10.10.60.2/24 eth0
docker_daemon: ok
docker: Name=DESKTOP-V61T28L ServerVersion=29.6.2 OperatingSystem=Arch Linux Driver=overlayfs NCPU=16
compose: Docker Compose version 5.3.1
local cache http://172.17.0.1:18080: timeout after 5s / 2s (http_code=000)
formal_local_build: fail-closed
used_as_s9_builder_or_gate_host: no
```

本机 cache 相对 S7 记录的 HTTP 502 现为超时。仍 fail-closed，不得改走本机构建或
把 WSL Docker 当作 S9 gate-host。

### Remote builder / gate-host (`issac@10.10.60.4`)

```text
ssh: issac@10.10.60.4 BatchMode=yes
whoami: issac
id: uid=1000(issac) gid=1000(issac) groups=1000(issac),955(libvirt),958(docker),998(wheel)
uname: Linux 7.1.6-arch1-1 x86_64
hostname_file: arch
ipv4: 10.10.60.4/24 wg0
docker_daemon: ok
docker: Name=arch ServerVersion=29.7.2 OperatingSystem=Arch Linux Driver=overlayfs NCPU=16
compose: Docker Compose version 5.4.0
remote cache http://172.17.0.1:18080: HTTP 200
cache_server: SimpleHTTP/0.6 Python/3.14.6
bridge_network: Name=bridge Driver=bridge Scope=local ID=7060d1f61386 Gateway=172.17.0.1 Subnet=172.17.0.0/16
other_networks: host, none (no extra project networks probed)
same_s7_configuration: yes
```

### Secret-file prerequisite

未启动 Compose。只读确认 harness 仍按 S7 语义写 token：

```text
write_token_file: path.chmod(0o400) in tests/support/compose_lifecycle_harness.py
start_p2r2_service: docker run --entrypoint id <service_image> -u/-g gateway
                    then os.chown(token_file, gateway_uid, gateway_gid)
secret_file_prerequisite_discoverable: yes
```

```yaml
docker_daemon_remote: yes
docker_compose_remote: yes
retained_cache_remote_http_200: yes
gate_host_linux_bridge: yes
secret_file_harness_present: yes
local_cache_usable_for_formal_build: no
host_or_cache_switched: no
environment_prerequisites_available: yes
```

## Nodeid inventory

四个 Docker/cgroup 测试文件相对 `2ef88427` 的 working-tree diff 为空。收集在文档
worktree 的 `uv` 环境中执行（Python 3.14.6，pytest 9.1.1），`--collect-only`，
不启动容器。

```text
uv run pytest --collect-only -q \
  tests/test_import_compose_e2e.py \
  tests/test_versioned_read_compose_e2e.py \
  tests/test_compose_lifecycle_negative_probes.py
8 tests collected in 0.13s
```

| nodeid | markers | skipif | docker-absent behaviour |
| --- | --- | --- | --- |
| `tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay` | integration, serial | none | `pytest.fail` |
| `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network` | integration, serial | none | `pytest.fail` |
| `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host` | integration, serial | none | `pytest.fail` |
| `tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle` | integration, serial | none | `pytest.fail` |
| `tests/test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up` | integration, serial | none | `pytest.fail` |
| `tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up` | integration, serial | none | `pytest.fail` |
| `tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up` | integration, serial | none | `pytest.fail` |
| `tests/test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up` | integration, serial | none | `pytest.fail` |

三个 Docker-starting 文件无 `skipif` / `pytest.skip`。缺 docker 是失败，不是环境 skip。

预期唯一环境 skip：

```text
GATEWAY_P2R1_TARGET_CONTAINER=
uv run pytest --collect-only -q tests/test_p2_r1_target_cgroup_smoke.py
  tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup
  1 test collected
uv run pytest -q tests/test_p2_r1_target_cgroup_smoke.py -rs
  SKIPPED [1] tests/test_p2_r1_target_cgroup_smoke.py:11: runs only inside the delegated target container
  1 skipped in 3.08s
```

该 nodeid 不是 S9 required Docker nodeid。S9 no-ignore 全量仍允许这一条 skip。

```yaml
eight_docker_nodeids_collectable: yes
docker_nodeid_environment_skip: none
expected_cgroup_skip_classified: yes
cgroup_skip_reason: GATEWAY_P2R1_TARGET_CONTAINER != "1"
```

## Docker / Compose decision

```text
Current HEAD: 71da506171d01bbccdf2c54137949cdd0bff234e
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (S9-2 candidate-bound provisional image; not executed in S9-0)
Reason: S9 exact no-ignore gate includes eight Docker-starting nodeids; S7 image labels bind 5f474ce2 / sha256:b1e7576c… and cannot match 2ef88427 identity sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S9-2 candidate-bound provisional Service/client image; S9-3 exact ./vnext/scripts/run-tests.sh and eight Docker nodeids; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9-2 provisional image / S9-3 no-ignore / S10 final production
```

S7 image 与四条 Compose PASS 仍是祖先 `5f474ce2` 证据。本 docs-only 入口记录不改变
`container_validated_code_sha`。

## Unresolved external prerequisites

```text
none
```

远端 `issac@10.10.60.4` Docker / Compose / retained cache HTTP 200 / Linux bridge
与 secret-file harness 均可发现。本机 cache 超时不是 unresolved blocker：S7 已
fail-closed 并使用同一远端配置。

## Exit

```yaml
entry_identity_consistent: yes
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s8_handoff_head_docs_only: yes
s7_ancestor: yes
post_candidate_delta_docs_only: yes
production_code_dirty: no
environment_prerequisites_available: yes
eight_docker_nodeids_collectable: yes
expected_cgroup_skip_classified: yes
unknown_current_finding: none
unresolved_external_prerequisites: none
S9_entry_ready: yes
allow_s9_design_review: yes
S9_exit: no
S10_ready: no
production_retest_required: yes
phase_2_complete: no
next: S9-1 independent design review in a new conversation
```

下一步读取本记录、S9 设计 §§1–7 和执行计划，只读审核 candidate seal、image
provenance、no-ignore gate 和回退边界。S9-1 的 `reviewed_design_sha` 是本
docs-only 记录提交之后的干净文档 HEAD，不是 candidate SHA `2ef88427`。

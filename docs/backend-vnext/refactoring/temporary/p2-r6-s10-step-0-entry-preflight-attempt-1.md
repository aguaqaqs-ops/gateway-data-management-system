# P2-R6-S10 Step 0 — Entry Reconciliation and External Preflight

状态：`complete`（入口记录完成；`S10_entry_ready: no`）

日期：2026-08-17

本记录只做 S10 入口身份、S9 seal 对照、clean detached checkout、远端
builder/gate-host 前置、W1/W2 包身份（不传输）、八个 Docker nodeid 收集、
预期 cgroup skip 分类、final tag 盘点、资源基线和 unique audit root 分配。
没有修改 production/test/deployment 文件，没有构建 final image，没有执行
`./vnext/scripts/run-tests.sh`，没有传输 W1/W2 包，没有实现 audit adapter，
也没有把 `21c99ef3`、S9 provisional image 或祖先 `5f474ce2` 写成 S10 构建输入。
S10-0 不对 S10 设计做 pass/fail 判定；独立设计审核归 S10-1，且须在
`S10_entry_ready: yes` 之后另开对话。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §2
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §§1–3
上游 handoff：[P2-R6-S9 final handoff](p2-r6-s9-final-handoff.md)
S9 seal review：[p2-r6-s9-candidate-seal-review-rerun.md](p2-r6-s9-candidate-seal-review-rerun.md)
总计划：[P2-R6 Operational Closure Execution Plan](../formal/plans/p2-r6-operational-closure-execution-plan.md) §§7–8
v8 权威：[P2-R1 v8 Authority and Implementation Brief](../formal/plans/p2-r1-v8-authority-and-implementation-brief.md)
W1/W2：[P2-R6-EXT-W1 Stage I S6](p2-r6-ext-w1-stage-i-s6-capacity.md)、[Stage I W2](p2-r6-ext-w1-stage-i-w2.md)、[Stage K handoff](p2-r6-ext-w1-stage-k-final-handoff.md)
launcher：[vnext/deploy/p2r1-cache/README.md](../../../../vnext/deploy/p2r1-cache/README.md)
测试约定：[Testing Conventions](../../testing-conventions.md)

## Entry identity

S10-0 开始时用 `git rev-parse HEAD` 取得文档 worktree 的字面量 SHA。该 SHA 与执行计划
冻结字段 `s9_handoff_record_commit_sha` 一致，是 documentation-only，不是 source
candidate。本文件后续若以 docs-only 提交，仍不是 `validated_code_sha`。

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
s9_handoff_record_commit_sha: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
s9_handoff_record_commit_match: yes
s9_handoff_docs_only: yes
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s9_is_ancestor: yes
s8_entry_is_ancestor: yes
s7_is_ancestor: yes
candidate_is_ancestor: yes
merge_base_with_candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
merge_base_with_s9_handoff: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
post_candidate_committed_delta: docs-only
production_code_dirty: no
S9_exit: pass
S10_ready: yes
production_retest_required: yes
phase_2_complete: no
```

文档 worktree 开始时 `git status --short`：

```text
 M docs/backend-vnext/refactoring/formal/README.md
 M docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md
?? docs/backend-vnext/refactoring/formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md
?? docs/backend-vnext/refactoring/formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md
```

`vnext/**` 无已跟踪或未跟踪改动。脏文件全部是 S10 规划文档与 formal 索引，不是未知
生产漂移。分类见下一节。这不构成 identity 失败。identity helper 未在该脏 worktree
上运行。

`git worktree list`（S10-0 开始时）：

```text
/root/gateway-data-management-system 21c99ef3 [phase1/gate-ownership-repair]
/root/gateway-s9-candidate-2ef88427  2ef88427 (detached HEAD)
```

## Ancestry and committed delta

S9 candidate `2ef884278b4998dde1e5fe224532c89b7a0cd73a`、S9 handoff
`21c99ef3202f3cfd63a24d4e08cd869e36ff0af0`、S8 entry
`1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09` 与 S7 candidate
`5f474ce2ccf15f11ea07f263edf3fb04c771d410` 都是当前文档 HEAD 的祖先。
`git merge-base --is-ancestor` 四项均为 yes。文档 HEAD 就是 `21c99ef3`。

`git log --oneline --decorate 2ef88427..HEAD`：

```text
21c99ef3 (HEAD -> phase1/gate-ownership-repair) docs(repository): record P2-R6-S9 final candidate seal
71da5061 docs(repository): record P2-R6-S8 final handoff
```

`git diff --name-status 2ef88427..HEAD -- vnext` 为空。该 committed delta 是
docs-only。`21c99ef3` 不得作为 `CANDIDATE_SHA`。`container_validated_code_sha`
仍为 `deferred`；S9 provisional image 不是 S10 final production image。

## Uncommitted worktree classification

| path | status | class |
| --- | --- | --- |
| `docs/backend-vnext/refactoring/formal/README.md` | modified | current S10 formal index and stage-status wording |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md` | modified | current S10 design/plan links under the S10 stage block |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md` | untracked | current S10 design authority |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md` | untracked | current S10 execution authority |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s10-step-0-entry-preflight.md` | this record | S10-0 evidence; added after the status snapshot above |

```yaml
tracked_production_dirty: no
untracked_production: none
uncommitted_docs_only: yes
unknown_current_finding: none
unresolved_scope_ownership: none
```

## Candidate checkout and expected identity

`identity` helper 要求 clean worktree，且 `candidate_sha` 取自该 checkout 的 `HEAD`。
本地 **select** 既有干净 detached worktree；远端 **create** 新的 S10 路径，不复用
S9 `/home/issac/gateway-gate-2ef884278b49`（含测试 `.venv`）。

```text
local_candidate_worktree: /root/gateway-s9-candidate-2ef88427
local_action: select existing
local_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
local_git_status_porcelain: empty
local_worktree_clean: yes

remote_candidate_worktree: /home/issac/gateway-s10-candidate-2ef88427
remote_action: git worktree add --detach ... 2ef884278b4998dde1e5fe224532c89b7a0cd73a
remote_HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
remote_git_status_porcelain: empty
remote_worktree_clean: yes
```

两端执行：

```bash
python3 vnext/repository_service/tests/support/build_context_digest.py identity
sha256sum vnext/repository_service/uv.lock vnext/repository_client/uv.lock
```

本地与远端 helper 输出相同：

```text
schema: gateway.p2r1.build-identity
schema_version: 1
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
```

四字段与 S9 seal / S9-2 labels 逐字相等。`git diff --check` 两端 pass。本步未构建
镜像，未打 `p2-r6-final`。

## S9 / S7 authority

来源：[p2-r6-s9-final-handoff.md](p2-r6-s9-final-handoff.md)、
[p2-r6-s7-final-handoff.md](p2-r6-s7-final-handoff.md)。S10-0 逐项核对，不重跑
S9 no-ignore，也不把 S9 provisional 或 S7 祖先 image 写成当前 candidate 已验证。

```yaml
stage: P2-R6-S9
stage_status: pass
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: deferred
candidate_seal: pass
S9_exit: pass
S10_ready: yes
production_retest_required: yes
phase_2_complete: no
```

S9 provisional（不得当作 S10 final）：

```text
service_image: gateway-repository-service:local
service_image_also_tagged: gateway-repository-service:2ef884278b49
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
```

祖先（不得当作当前 candidate 已验证）：

```text
ancestor_candidate: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
ancestor_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
ancestor_source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
```

## Environment preflight

沿用 S7/S9 retained-cache remote builder / Linux gate-host，不静默换 host 或 cache。
本步只做发现性检查：不 `compose up`、不 `docker save|load`、不构建镜像。

### Local documentation host (WSL, not gate-host)

```text
host: DESKTOP-V61T28L
kernel: Linux 6.6.114.1-microsoft-standard-WSL2 x86_64
ipv4: 10.10.60.2/24 eth0
docker_daemon: ok
docker: Name=DESKTOP-V61T28L ServerVersion=29.6.2 OperatingSystem=Arch Linux Driver=overlayfs NCPU=16 ID=a46a67b1-30fc-4954-8375-e1aa988ebe30
compose: Docker Compose version 5.3.1
local cache http://172.17.0.1:18080: timeout after 5s (http_code=000)
df /: ext4 1007G 94G used 862G avail
formal_local_build: fail-closed
used_as_s10_builder_or_gate_host: no
```

本机 cache 超时。仍 fail-closed，不得改走本机构建或把 WSL Docker 当作 S10
gate-host。本机 Docker ID 与远端 `dc91db82-…` 不同，不是 same-daemon 证据。

### Remote builder / gate-host (`issac@10.10.60.4`)

```text
ssh: issac@10.10.60.4 BatchMode=yes
whoami: issac
id: uid=1000(issac) gid=1000(issac) groups=1000(issac),955(libvirt),958(docker),998(wheel)
uname: Linux 7.1.6-arch1-1 x86_64
hostname_file: arch
ipv4: 10.10.60.4/24 wg0
docker_daemon: ok
docker: Name=arch ServerVersion=29.7.2 OperatingSystem=Arch Linux Driver=overlayfs NCPU=16 ID=dc91db82-3d49-41a4-a63c-f23dda721890
compose: Docker Compose version 5.4.0
remote cache http://172.17.0.1:18080: HTTP 200
cache_server: SimpleHTTP/0.6 Python/3.14.6
bridge_network: Name=bridge Driver=bridge Scope=local ID=7060d1f61386 Gateway=172.17.0.1 Subnet=172.17.0.0/16
other_networks: host, none (no extra project networks)
same_s7_s9_configuration: yes
same_daemon_build_and_gate: yes
cross_host_transfer: not_applicable
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
```

Builder 与 gate 是同一远端 Docker daemon `Name=arch` / `ID=dc91db82-…`。未发现
独立 daemon。若后续拓扑变成双 daemon，须先停并审核 save/load 路径。

### Disk

```text
Filesystem /dev/nvme0n1p8 xfs 1.8T used 706G avail 1.1T 40%  (covers /, /home, /var/lib/docker, /var/lib/gateway)
DockerRootDir=/var/lib/docker
docker system df:
  Images 110 total / 18 active / 298GB / reclaimable 177.8GB
  Containers 26 / 0 active / 2.309GB
  Local Volumes 5 / 0 active / 279.1MB
S9 provisional service image size: 332411485 bytes (~317 MiB unpacked inspect Size; docker ls 1.34GB)
S9 client image size: 243128653 bytes
W2 expansion reference: ~192 MiB replay
disk_sufficient_for_image_archive_w2_v8: yes
```

### Secret-file prerequisite

未启动 Compose。只读确认 harness 仍按 S7 语义写 token（candidate checkout）：

```text
write_token_file: path.write_text + path.chmod(0o400)
                 in vnext/repository_service/tests/support/compose_lifecycle_harness.py:226
start_p2r2_service: docker run --entrypoint id <service_image> -u/-g gateway
                    then os.chown(token_file, gateway_uid, gateway_gid)
secret_file_prerequisite_discoverable: yes
```

### Interactive sudo and installed launcher

```text
sudo_binary: /usr/bin/sudo -rwsr-xr-x root:root
wheel: x:998:issac,tmpuser
sudo -n true: fail (password required; expected)
sudo -l: fail without TTY (password required; not policy-denied)
interactive_operator_path: yes (wheel + password sudo; historical root-owned audit-rerun artifacts)
tty_this_session: not a tty
```

`sudo -n` 不是验收项。operator 路径真实存在：`issac` 在 `wheel`，`sudo` 要密码而不是
拒绝。本会话无 TTY，不能在此代输密码。

已安装路径对照 [p2r1-cache README](../../../../vnext/deploy/p2r1-cache/README.md)：

```text
/usr/local/libexec/gateway-p2r1-target-launcher.sh: -rwxr-xr-x root:root 29924  2026-08-03 18:12
/etc/systemd/system/gateway-p2r1.slice: present; sha256=fdeec940…493bdf; matches candidate
/etc/systemd/system/gateway-p2r1-runner@.service: present; sha256=e172d64a…2d5dde; matches candidate
systemctl is-enabled gateway-p2r1.slice: static
```

**Installed launcher 不是 candidate 字节。** 这是当前 `S10_entry_ready: no` 的 blocking
prerequisite：

```text
installed sha256: ade607bf4f3e4c5d0295c30acfaa37d95038510a8e1c5a4258c2b0b52c041b32
candidate sha256: 2782a83f4465f1d9505a5347e1cc418ebd64f8fe73e2e9964d5235945da54a88
installed manifest_version: p2-r1-provenance-v2 (build_revision)
candidate manifest_version: p2-r1-provenance-v3 (candidate_sha + build_input_revision)
installed_launcher_matches_candidate: no
```

S10-7/S10-8 权威命令使用 `/usr/local/libexec/gateway-p2r1-target-launcher.sh`。v2
launcher 不能证明 S10 v3 identity。不得带着过期 launcher 先构建再期望后续 gate
补偿。owner：release operator，在 candidate checkout 上重装 launcher（不改 candidate
源码）：

```bash
sudo install -m 0755 \
  /home/issac/gateway-s10-candidate-2ef88427/vnext/deploy/p2r1-cache/p2r1-target-launcher.sh \
  /usr/local/libexec/gateway-p2r1-target-launcher.sh
```

重装后须复算 installed SHA 等于 `2782a83f…`，并刷新本记录或另写 S10-0 rerun。

```yaml
docker_daemon_remote: yes
docker_compose_remote: yes
retained_cache_remote_http_200: yes
gate_host_linux_bridge: yes
secret_file_harness_present: yes
local_cache_usable_for_formal_build: no
host_or_cache_switched: no
same_daemon_build_and_gate: yes
disk_sufficient: yes
interactive_operator_path: yes
installed_launcher_present: yes
installed_launcher_current: no
environment_prerequisites_available: no
```

## W1 / W2 package identity (not transferred)

本地复算，对照 S10 设计字面量。未 scp、未展开。

| artifact | path | bytes | sha256 |
| --- | --- | ---: | --- |
| W1 medium | `/root/test-data/medium/package.tar.zst` | 2081228 | `3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e` |
| W2 | `/root/test-data/w2/package.tar.zst` | 8301271 | `6cac7852d1174c126c182e82010b0ff9d4043e51826b8043103360c8e49f6d10` |
| sanitized descriptor | `docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-external-descriptor.yaml` | 2682 | `416eb412d7e9ec389bb0dffae5511b016937ae1e29790cc3e26b549eb772205f` |

与 Stage I/K / S10 设计逐字段一致。descriptor 无 raw SQL、rows、secrets 或 host path。

远端 protected staging 父目录 `/var/lib/gateway/repository/audit-rerun` 为 `root:root`
`0755`。issac 无 sudo 时 `touch`/`mkdir` Permission denied（符合保护语义）。wheel
operator 可通过 interactive sudo 创建 unique 子目录。本步 **未传输** 包。

```yaml
w1_medium_size_sha_match: yes
w2_size_sha_match: yes
descriptor_size_sha_match: yes
remote_staging_parent_exists: yes
remote_staging_issac_unprivileged_write: no
remote_staging_operator_sudo_required: yes
package_transferred: no
```

## Nodeid inventory and expected counts

四个 Docker/cgroup 测试文件相对 `2ef88427` 的 working-tree diff 为空。收集在文档
worktree 的 `uv` 环境中执行（Python 3.14.6，pytest 9.1.1），`--collect-only`，
不启动容器。`vnext/` 相对 candidate 无 diff，未在 candidate checkout 创建 `.venv`。

```text
uv run pytest --collect-only -q \
  tests/test_import_compose_e2e.py \
  tests/test_versioned_read_compose_e2e.py \
  tests/test_compose_lifecycle_negative_probes.py
8 tests collected in 0.16s
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
前四条是 S10 Compose nodeid；后四条 negative probe 仍须经 exact no-ignore 命令证明，
不得单独补跑替代。

预期唯一环境 skip：

```text
GATEWAY_P2R1_TARGET_CONTAINER=
uv run pytest --collect-only -q tests/test_p2_r1_target_cgroup_smoke.py
  tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup
  1 test collected
uv run pytest -q tests/test_p2_r1_target_cgroup_smoke.py -rs
  SKIPPED [1] tests/test_p2_r1_target_cgroup_smoke.py:11: runs only inside the delegated target container
  1 skipped in 7.81s
```

该 nodeid 不是 S10 required Docker nodeid。S10 no-ignore 全量仍允许这一条 skip；
S10-7/S10-8 target 执行直接关闭该环境能力缺口。

collect-only 包计数（对照 S9 seal inventory；本步不是 no-ignore 执行证据）：

| suite | collected |
| --- | ---: |
| shared_kernel | 242 |
| repository_contracts | 152 |
| repository_client | 154 |
| backend | 35 |
| repository_service `-m "not serial"` | 1639 / 1844 (205 deselected) |
| repository_service `-m serial -n 0` | 205 / 1844 (1639 deselected) |

RS 全集 1844 = 1639 + 205。与 S9 权威 counts 一致。

```yaml
eight_docker_nodeids_collectable: yes
docker_nodeid_environment_skip: none
expected_cgroup_skip_classified: yes
cgroup_skip_reason: GATEWAY_P2R1_TARGET_CONTAINER != "1"
package_collect_counts_match_s9: yes
```

## Final tag and preexisting image inventory

本步不打 tag、不 rebuild。远端当前：

```text
gateway-repository-service:p2-r6-final: absent
gateway-repository-service:local: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
gateway-repository-service:2ef884278b49: same ID (S9 provisional)
gateway-repository-client-e2e:local: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
```

S9 provisional `:local` / `:2ef884278b49` 是 preexisting candidate-bound artifacts，
不是 S10 final。S10-4 必须从干净 candidate 重建并打 `p2-r6-final` 与 `:local` 到
同一新 immutable ID。祖先 `5f474ce2` / Stage J `656a66bf` 等 image 仍在 daemon 上，
分类为 preexisting，不得当作 final。

S10-5 必须保持 `GATEWAY_REPOSITORY_SERVICE_IMAGE` unset（当前远端已 unset）。

## Resource baseline (record only; no cleanup)

gate-host `10.10.60.4`，S9-4 口径：

```text
residual_inventory gate=s10-0-entry-preflight
  gateway-p2r6 containers=0 networks=0 volumes=0
  dolt_pids=0 query_temps=0 check_temp_homes=0 work_root_gateway=0
  candidate_porcelain=empty
```

preexisting、**不是本轮 owned residual**（不在本步清理）：

```text
exited/created containers: 26 (unnamed historical + sglang/paddleocr; none named gateway-p2r6)
volumes: gateway-p2r1-20260803*_repository-data (3), anonymous, open-webui
networks: bridge, host, none
```

## Unique audit root

```text
run_id: p2-r6-s10-20260817T015148Z
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z
  adapter/ staging/ v8/ preflight/ ALLOCATED.txt  (empty tree except allocation + hash snapshots)
remote_audit_root: /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z
remote_staging: /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z/staging
remote_collision: none (ls audit-rerun | grep s10 empty)
remote_mkdir: not created; issac unprivileged Permission denied; requires interactive sudo
```

本地 audit root 在文档 worktree 与 candidate 之外。远端前缀已预留且不覆盖
historical `p2-r1-*` 或 `.p2-r1-export-*`。远端目录创建与 launcher 重装同属
operator sudo 动作。

## Docker / Compose decision

```text
Current HEAD: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (S10-4 final Service/Client; not executed in S10-0)
Reason: S10 exact-candidate production gate; S9 provisional image is not p2-r6-final; tag gateway-repository-service:p2-r6-final is absent; Testing Conventions require rebuild of the final production candidate
Last verified image revision (S9 provisional, not final): 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id (S9 provisional):
  sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 /
  sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Last verified image revision (S7, ancestor): 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id (S7, ancestor):
  sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 /
  sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10-4 final Service/Client artifacts; S10-5 exact ./vnext/scripts/run-tests.sh -vv -s and eight Docker nodeids on final image; S10-6 W1 medium/W2; S10-7/S10-8 Candidate A W0 smoke and v8 formal --runs 5
Required execution point: S10-4 final production after S10-0 pass, S10-1 design review, and S10-2/S10-3 adapter review
```

本 docs-only 入口记录不改变 `container_validated_code_sha`。

## Unresolved external prerequisites

| item | owner | blocks |
| --- | --- | --- |
| installed `/usr/local/libexec/gateway-p2r1-target-launcher.sh` is provenance-v2; candidate is v3 (`2782a83f…`) | release operator on `issac@10.10.60.4` (interactive sudo install from S10 candidate checkout) | S10_entry_ready; S10-7/S10-8 |
| remote audit root `/var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z` not created | same operator (interactive sudo mkdir) | S10-6 staging / S10-7 output path; prefix reserved |

identity、cache、disk、W1/W2 digest、same-daemon、secret-file harness、八个 nodeid
与 cgroup skip 分类不是 unresolved。本机 cache 超时不是 blocker：S7/S9 已 fail-closed
并使用同一远端配置。

## Exit

```yaml
entry_identity_consistent: yes
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s9_handoff_docs_only: yes
post_candidate_delta_docs_only: yes
production_code_dirty: no
local_remote_identity_match: yes
same_daemon_build_and_gate: yes
w1_w2_package_identity: yes
package_transferred: no
eight_docker_nodeids_collectable: yes
expected_cgroup_skip_classified: yes
package_collect_counts_match_s9: yes
unique_audit_root_allocated: yes
installed_launcher_current: no
environment_prerequisites_available: no
unknown_current_finding: none
unresolved_external_prerequisites: installed v2 launcher; remote audit dir mkdir pending operator sudo
S10_entry_ready: no
allow_s10_design_review: no
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: operator reinstall candidate launcher and create reserved remote audit root; then rerun S10-0 launcher/audit checks in this conversation or a new S10-0 before S10-1
```

在 `installed_launcher_current: yes` 且远端 audit 前缀已由 operator 创建之前，不要
开启 S10-1。修复不得改 candidate、不得构建 `p2-r6-final`、不得传输 W1/W2。

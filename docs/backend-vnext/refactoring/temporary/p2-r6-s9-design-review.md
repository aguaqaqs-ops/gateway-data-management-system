# P2-R6-S9 Independent Design Review

状态：`pass`

日期：2026-08-17

本记录完成 S9-1，只读审核 S9 candidate seal 设计、provisional image provenance、
no-ignore source gate、candidate immutability、failure routing 与 S10 deferred scope。
审核期间未修改 production、test、dependency、Dockerfile、Compose、build input、candidate
checkout 或 image，也未执行 S9-2 build 和 S9-3 no-ignore regression。

权威步骤：[P2-R6-S9 Final Candidate Seal Execution Plan](../formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md) §3

审核设计：[P2-R6-S9 Final Candidate Seal Design](../formal/plans/p2-r6-s9-final-candidate-seal-design.md) §§1-7

入口证据：[P2-R6-S9 Step 0](p2-r6-s9-step-0-entry-preflight.md)

上游 handoff：[P2-R6-S8 final handoff](p2-r6-s8-final-handoff.md)

## Reviewed identity and scope

S9 formal design、execution plan 和 S9-0 record 当前位于 documentation worktree；其
reviewed content 用 Git blob SHA 固定，避免把未提交文档内容错误归属于当前
documentation `HEAD`。`documentation_head_sha` 只表示这些文件所在 worktree 的提交基线，
不是 reviewed file content SHA，也不是 source candidate。

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 71da506171d01bbccdf2c54137949cdd0bff234e
reviewed_design_sha: 861fd08f7941fbc7490313f44831459c900b08b2
reviewed_plan_sha: d0184df48c173569b8aa60589eabb933222e17c1
reviewed_sha_kind: git_blob
reviewed_design_blob_sha: 861fd08f7941fbc7490313f44831459c900b08b2
reviewed_execution_plan_blob_sha: d0184df48c173569b8aa60589eabb933222e17c1
reviewed_s9_0_record_blob_sha: d78c1360088860ea4220950d354e5286ad6331a3
reviewed_candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s8_handoff_head: 71da506171d01bbccdf2c54137949cdd0bff234e
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
review_kind: independent_read_only_design_review
production_code_changed_by_review: no
test_or_build_input_changed_by_review: no
image_built_or_changed_by_review: no
phase_2_complete: no
```

`2ef88427` 是唯一允许进入 S9-2/S9-3 的 source candidate。`71da5061` 及后续 S9
evidence/documentation revision 均为 docs-only，不得作为 `CANDIDATE_SHA`、image label
或 current-candidate container evidence。

## Review results

### 1. Candidate authority and entry

**Pass.** Design §1、execution plan §0 和 S9-0 一致固定
`validated_code_sha=2ef884278b4998dde1e5fe224532c89b7a0cd73a`，并明确
`71da5061` 是 documentation-only handoff descendant。S9-0 已核对 candidate、S8 entry
和 S7 ancestor 的 ancestry，candidate detached worktree clean，post-candidate committed
delta 与当前未提交 delta 均为 docs-only；`S9_entry_ready: yes`。

### 2. Authoritative no-ignore gate

**Pass.** 唯一权威命令是：

```bash
./vnext/scripts/run-tests.sh
```

Design §3.1 与 execution plan §5 禁止 `-m`、`-k`、`--ignore`、`--ignore-glob`、xfail、
retry、accepted flake、stale image 或 host-only substitution。计划要求逐 package 记录
collected/passed/skipped/failed/duration，并分别记录 Repository Service parallel/serial
counts；不会把 S8 的三条 Docker file ignore 延续到 S9。

### 3. Docker nodeids and skip boundary

**Pass.** Execution plan §5 逐字冻结八个 Docker-starting nodeid，要求全部 collected 且
逐项 passed。S9-0 已验证八条均可收集，均为 `integration` + `serial`，没有 Docker-absent
environment skip。唯一允许的 skip 是
`tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup`，
且仅在 `GATEWAY_P2R1_TARGET_CONTAINER != "1"` 时成立；它不是八条 required nodeid 之一。

### 4. Candidate-bound provisional image provenance

**Pass.** Design §3.2/§4 和 execution plan §4 要求 Service image 同时匹配 immutable image
ID、candidate SHA、build-input revision、effective source-tree digest 和 Service lock hash；
client image/host runner 同时匹配 candidate SHA 与 client lock hash。S9-0 已固定 expected
identity：

```yaml
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
```

八条测试均经 `ensure_repository_service_image()` 获取 Service image；需要 client 的路径
经 `ensure_client_image()` 或明确的 candidate/lock-bound host-runner identity。旧 S7 image
`5f474ce2` 只能作为 ancestor evidence，不能关闭 S9-2/S9-3。

### 5. S9 provisional image versus S10 production image

**Pass.** S9 image 仅服务于 no-ignore source gate，S10 独立重建、传输并验证 sealed
candidate 的 final production image。S9 不继承、转称或发布 provisional image 为 final
production provenance，也不声称 current production/container gate pass。S10 的四条
Compose nodeid、W1/W2 repeat、Candidate A v8 formal `--runs 5` 和 final zero-residual gate
保持显式 deferred。

### 6. Immutability, external evidence and failure routing

**Pass.** Candidate 在 S9-0 选定后禁止 source、test、dependency、Dockerfile、Compose、
deployment 或其他 build-input edit。所有 S9 record、raw search 和 command log 必须写在
detached candidate checkout 之外。source/test/build-input failure 返回 S8 owner 并以新 clean
SHA 重启 S9；image/provenance/container boundary failure 返回 S9-2；纯 evidence/count/packet
gap 返回 S9-3/S9-4。S9-5 是新会话中的 read-only seal review，finding 必须保留且按 owner
route 修复后重新审核，reviewer 不修补 finding。

### 7. Carried evidence and downstream ownership

**Pass.** S8 的 parked-Dolt unit、五包 static、worker convergence、三 exact-ignore source
regression、old-reference classification 与 independent rereview 保持 carried pass；S7 image
和四条 Compose pass 明确只属于 `5f474ce2` ancestor。S9 不重开 S6 capacity，也不接管
S10 final production image、W1/W2、四条 Compose nodeid、v8 或 Phase 2 exit。

## Findings

未发现 blocker 或 non-blocking design finding。

```yaml
finding_count: 0
blocker_count: 0
high_count: 0
medium_count: 0
low_count: 0
```

## Implementation conditions

- S9-2 必须在 clean detached `2ef88427` checkout 和 S7 同一 remote
  builder/gate-host/retained-cache 配置上重新建立 provisional Service/client identity；不得用
  本机超时 cache、S7 stale image 或未标注 image 替代。
- S9-2/S9-3 只有在 source、build inputs、checkout 与 image identities 全程不变时才能在同一
  session 连续执行；任何 candidate-affecting change 都使已有 S9 evidence 失效。
- S9-3 必须原样执行 no-ignore command，并单独证明八条 Docker nodeid 全部 pass、唯一 skip
  分类正确、package counts 一致且 owned resources 返回零。
- 本审核只授权进入 S9-2；不授权 S9 exit、candidate seal、S10 readiness、production gate 或
  Phase 2 completion claim。

## Verdict

```yaml
review_status: pass
allow_s9_implementation: yes
finding_count: 0
blocker_count: 0
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s9_entry_ready: yes
candidate_bound_provisional_image_required: yes
container_rebuild_required_at_s9_2: yes
container_gate_for_candidate: deferred_to_s9_2_s9_3
final_production_image: deferred_to_s10
independent_seal_review: required_at_s9_5
S9_exit: no
S10_ready: no
production_retest_required: yes
phase_2_complete: no
next: S9-2 candidate checkout and provisional image in a new conversation
```

独立设计审核通过，允许进入 S9-2。后续必须保留 exact candidate、no-ignore、provisional
provenance、external evidence、zero-residual 和 failure-routing 条件；本记录本身不构成任何
image、source regression 或 seal PASS。

# P2-R6-S7 — Independent Design Review

状态：`pass`

日期：2026-08-16

本记录是 S7-1 的独立只读设计审核。审核对象为冻结的 S7 Compose lifecycle design、
execution plan 及其上游 Contract/S4 authority；审核不修改 production/test/Compose 输入，
不实现 harness，不运行 Compose lifecycle gate，也不把 Stage J image 证据升级为当前 S7
candidate 的 container PASS。

权威设计：[P2-R6-S7 Compose Lifecycle Design](../formal/plans/p2-r6-s7-compose-lifecycle-design.md)
权威执行计划：[P2-R6-S7 Compose Lifecycle Execution Plan](../formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md)
上游 handoff：[P2-R6-EXT-W1 Stage K Final Handoff](p2-r6-ext-w1-stage-k-final-handoff.md)
Contract：[Repository Service Contract](../formal/contracts/repository-service.md)
S4 authority：[P2-R6-S4 Staged Execution Guide](phase-2/p2-r6-s4-staged-execution-guide.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_design_sha: 34801a16e565d71d87884384c13c943822791915
reviewed_plan_sha: 34801a16e565d71d87884384c13c943822791915
stage_k_entry_sha: 0b4969fe04ab3d133c297a474bac1ecc27111336
stage_k_is_ancestor: yes
review_worktree_clean_at_start: yes
production_code_changed_by_review: no
compose_or_docker_input_changed_by_review: no
container_rebuild_required: no
container_validated_code_sha: 656a66bf04714cce987c85649246c3767b2586e2
stage_j_image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
public_contract_changed: no
nodeid_count: 4
phase_2_complete: no
```

`reviewed_design_sha` 是本审核开始时的完整 HEAD；该 commit 只引入 S7 formal design、
execution plan 和 operational-plan 索引变更。Stage J 的 `container_validated_code_sha`
与 image 仅作为 ancestor evidence，不能证明 `reviewed_design_sha` 或之后的 S7 harness
candidate 已通过容器 gate。

## Reviewed facts

- Contract §2 仍规定 Service 不依赖 Client；§13 要求以 immutable CommitId 读取 catalog
  与 Arrow rows；§15 只允许 quiescent whole-root operator snapshot/restore，不提供 public
  backup/restore API。
- 当前 `vnext/deploy/compose.yaml` 的 `repository-service` 位于 `p2-r2` profile，使用独立
  named volume、internal healthcheck 和 secret mount，没有 `ports:`；现有静态 test
  `test_compose_repository_service_has_no_host_ports` 继续拥有该部署不变量。
- S4 已有 `snapshot_admin` hold/check、whole-root copy、空目标/非空 overlay、live-root、
  incomplete restore、Dolt child/query-temp cleanup 以及
  `test_whole_root_restore_preserves_public_facts`。S7 设计复用这些语义，不新增 restore
  implementation。
- `vnext/repository_client/tests/support/versioned_fixture_consumer.py` 是现有 Contract-owned
  consumer；`tests/fixtures/versioned_v1/{c1,c2}` 与 expected oracle 均存在。consumer 内部
  验证 catalog、rows、CommitId pin、Arrow EOS，并返回严格的 `status/repository_id/c0/c1/c2/main_commit`
  summary。当前树中 R4 nodeid 已存在，三个 S7 versioned-read/lifecycle nodeid 尚待 S7-2/3
  实现；这符合 execution plan 的 deferred inventory，不是本设计审核的缺口。

## Required questions

### 1. Public Contract, S4 semantics and topology

**Pass.** Design §§2–3 明确禁止 public route、Service-to-Client dependency、常驻 client、
sidecar、broker、独立 UID 和 host-port publication；inside-network client 是 test-only
one-shot container，gate-host path 只使用动态发现的 bridge address。Snapshot boundary 明确
复用 S4 的 stop → hold/lock/checkpoint → one-time whole-root copy → empty target → restore →
check → same-image startup 顺序。没有改变 Contract、Dolt layout 或 public restore semantics。

### 2. Lifecycle nodeid ownership and public facts

**Pass.** Design §4 为四个 exact nodeid 分配唯一行为 owner；第四个 nodeid 独占 fresh/
restart/restored、snapshot public facts、post-snapshot mutation absence、hold/check 与最终
cleanup，不把 restore 断言藏入 gate-host read test。两条 remote-read nodeid 共用同一个
fixture consumer 和 oracle，并要求 c1/c2 catalog/rows、immutable CommitId、`main=c2`、
c1 在 c2 publication 后仍可读和 Arrow EOS。`c0/c1/c2` 的创建顺序和 expected fixture facts
在设计 §3.2 固定，足以让实现使用确定的 public oracle，而非 raw SQL/Dolt inspection。

### 3. Fresh, restart and restored semantics

**Pass.** Design §3.3 区分新 project/新 empty named volume 的 fresh、同一 volume 上
`up -d --no-build --force-recreate` 的 restart，以及独立 empty restore volume 上的
whole-root restored startup；明确拒绝以 `docker compose restart` 替代 container recreation。
设计还要求 snapshot-time c1/c2 facts 保留、post-snapshot mutation 在 restored root 中缺失，
并以 `check` 完成后才启动同一 image。源 volume 与 restore volume 不共享 writable state。

### 4. Ephemeral client boundary

**Pass.** Design §3.1/§5.2 将 client 限定为同一 S7 candidate 构建的 test-only image/process，
只读挂载 fixture/runner material，不挂 durable root、Docker socket 或 host root；production
Compose 不新增 client service 或 dependency。这个边界与 Contract §2 的 dependency direction
一致，后续实现仍须由 rendered Compose/static assertions 和 per-node inventory 证明。

### 5. Failure cleanup and bounded resources

**Pass.** Design §5.1、§6 和 acceptance matrix 将 cleanup 作为失败条件而非 warning：每个
nodeid 使用独立 project/volume/token/temp root，在 `finally` 中清理，并 inventory process、
thread、Dolt child、query temp、container、network、volume。S4 的 signal/lock/provider
cleanup owner 已存在；S7 plan 要求复用而非复制其 restore semantics。后续实现必须保留
expected-failure cleanup assertions，不能以 host-only smoke 或 skip 代替。

### 6. Provenance and old-image substitution

**Pass with implementation condition.** Design §5.3 要求 candidate SHA、container-validated
code SHA、build-input revision、source-tree digest、service/client identity 和两套 lock
identity 同时进入 evidence，并规定任何 Compose/Dockerfile/dependency/runtime wiring 变化
都 invalidates prior image evidence。该字段集合足以在实现按 immutable image ID、labels 和
locked client source 绑定时拒绝 old-image substitution。`client_image_id` 若采用 host-runner
而非 image，必须记录可复核的 candidate/source/lock identity；不能写入任意 tag 或未定义的
自由文本 identity。这是实现验收条件，不是当前设计 blocker。

### 7. S7/S10 ownership and phase boundary

**Pass.** Design §2.1、§7 和 execution plan §§12–14 明确 S7 只关闭当前 provisional
candidate 上的 deferred Compose/lifecycle inventory；S7-10 是独立 lifecycle review，
S7-11 才重建 exact final candidate。S8/S9/S10、production retest 和 v8 formal gate 仍
deferred，`phase_2_complete` 必须保持 `no`。

## Findings

No blocker findings.

## Non-findings and residual risks

- 三个新增 nodeid 尚不存在是 S7-0 handoff 已声明的 deferred implementation scope；本审核
  不把缺失实现误报为 design failure，也不允许后续以 missing/skip 宣称 S7 PASS。
- 当前 R4 implementation 使用 `restart`；S7 plan 已明确 S7 gate 必须改为同一 named volume
  上的 `--no-build --force-recreate`，故该现状不会被当作设计已满足。
- “move/reconfirm main where harness supports the branch movement” 的执行措辞不能削弱设计
  §4.2 的 pinned-read invariant；实现验收仍必须对 c1 pin、c2/main 和 mutation absence 给出
  deterministic public facts，无法提供时应回到 S7-3，而不是放宽断言。
- 本记录未运行 pytest、Docker、Compose、builder 或 remote bridge preflight；这些属于 S7-0、
  S7-2/3 focused gates 与 S7-5 之后的 owning steps。

## Verdict

```yaml
review_status: pass
reviewed_design_sha: 34801a16e565d71d87884384c13c943822791915
finding_count: 0
blocker_count: 0
allow_s7_implementation: yes
public_contract_changed: no
topology_changed: no
restore_semantics_changed: no
provenance_review: pass_with_client_identity_condition
production_code_changed_by_review: no
container_rebuild_required: no
phase_2_complete: no
next: S7-2 Compose/client harness implementation
```

独立设计审核通过，允许进入 S7-2。后续实现必须以本记录列出的 client identity、force-recreate、
public oracle 和 per-node zero-residual 条件为硬验收边界；本记录不授权 S7 container gate、
S7 exit 或 Phase 2 completion claim。

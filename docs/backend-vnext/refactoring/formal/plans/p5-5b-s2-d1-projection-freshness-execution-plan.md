# P5-5B-S2 D-1 Projection Freshness：设计裁定与窄范围执行计划

状态：条款已落盘；T1 projection freshness 已交付；独立评审 pending。

日期：2026-09-15

Owner：Backend vNext Architecture / design owner（条款）；P5-5B Delivery（实现）；独立 reviewer（验收）。

## 1. 基线与权限

- 代码基线：`f9414aa4813a2c0deb608ff3f36aba6b10ecbb36`。
- 文档/checkout 基线：`c0d607bc49b245dacc49f8c210cd069e12d39b43`。
- 输入：[Submit/Finalize Design](p5-5b-submit-finalize-design.md) §6.1、§6.3、§12、§13.1；
  [Execution Plan](p5-5b-submit-finalize-execution-plan.md) §1–3；
  [Round-2 Brief](p5-5b-s2-round2-remediation-brief.md) §4、§5、§8.2；
  [Round-2 Handoff](p5-5b-s2-round2-remediation-handoff.md)。
- 用户已确认：保留 T1 同库 transaction-fresh mapping/Head 保证，不采用 preflight-only 弱化路线。
- 本文编写授权仅为文档。用户方向确认不冒充 design owner 签署、S1 countersign 或 S2 final pass。
  实施前先完成 §3 签署、owning design/allowed paths 更新，再取得明确代码实施授权。

## 2. 事实纠正与决策

现有 `infrastructure/control_db/sqlite_mapping.py` 的 `ProvisionedScopeResolution`、
`ProvisionedBaselineHeadRead` 从 SQLite `provisioned_scope_mappings` 读取；该表已在
Workspace schema v2 建立。`seed_provisioned_mappings` 先读取 JSON，再在独立短事务内 upsert。
HTTP 与 worker bootstrap 已调用此 seed。故“control DB 无对应表”“只能在事务内读文件”
不成立；现有按 db_path 开新 UoW 的 adapter 也不等于 T1 同连接参与者。

采用最小决策：

1. JSON 是 server-owned provisioning 输入；运行时 mapping/Head 的生效视图是 control DB
   projection，生效点是该 projection 更新事务提交。单独改文件不承诺即时生效。
2. T1 在自身 `BEGIN IMMEDIATE` 的同一连接读取 projection；新 key 与并发 winner 转 replay
   两个分支都要检查当前 mapping 授权，阻断已在 T1 开始前提交的 disable、换 Repository。
   新 key 还要拒绝 Head node/business baseline commit/version 漂移；replay 不受 Head 漂移影响。
   T1 后发生的变更不追溯取消既有 effect。
3. 保留任何 SQLite 事务内禁止 session file、artifact、Repository network I/O。
   重读 SQLite row 不是跨边界外部 I/O，不新增跨文件原子协议。
4. T2 mandatory CAS 只保护 Repository main CommitId；不是 mapping 或 BaselineHead version
   CAS。Head version-only 漂移必须由 T1 拒绝，即使 main CommitId 不变。

Projection 是可重建状态，但它在 Accept 时决定跨 scope/Repository 写入授权和 caller binding；
风险归于 A 类业务边界。最小控制是既有 SQLite 事务 + typed read participant + negative tests，
不新增表、版本轴、broker、outbox、锁服务或 evidence 状态机。

## 3. 待签署的 owning-design 修改

以下是供 owner 签署并应用的替换文本，不是本文件已自动修改 owning design。

### §6.1：保留原顺序，追加说明

> 新 key 的 preflight 与 T1 使用同一 control DB projection 解释 active mapping/BaselineHead。
> Server-owned provisioning JSON 是该 projection 的输入；运行时变更以 projection 更新事务提交
> 为生效点。文件改写本身不承诺即时生效。T1 同连接的 SQLite 读取不属于本节禁止的外部 I/O。

### §6.3 step 1：替换，闭合并发 winner 的 replay 重新授权

> 在当前 T1 查询 `(workspace_id, accept_idempotency_key)`。若已存在，返回 replay 前必须用
> 当前 T1 UoW 的同一 SQLite 连接，按 caller device/project exact key 读取当前 mapping，
> 并结合 Workspace/Attempt 的 scope 检查 mapping 存在且 enabled、exact scope 与当前
> Repository visibility。禁用或换仓不能沿用 preflight 的 resolved_repository_id 通过授权。
> 授权通过后，再以既有 Attempt 冻结的 server facts 重建 effective fingerprint，same/same
> 返回 replay，same/different 返回既有 conflict。当前 Head 的 node/commit/version 不覆盖
> Attempt 的冻结值，也不触发新 key 的 Head CAS；当前授权与冻结 fingerprint 必须分开处理。
> 不为该分支重新调用 baseline digest/main resolve，亦不再写入新 Attempt。

### §6.3 step 2：替换，新 key 的 fresh facts

> 使用当前 T1 UoW 的同一 SQLite 连接，按 caller 的 device/project exact key
> transaction-fresh 读取 provisioned active mapping/BaselineHead，以及 Workspace、
> UploadRevision、PreviewResult。不得调用会新开连接/UoW 或读取 session/mapping 文件的 adapter。

### §6.3 step 3–4：明确 freshness 与冻结 facts 的关系

> 对新 key，当前 mapping 必须存在、enabled，且其 Repository 与 frozen scope/Workspace 一致；
> 沿用既有 exact-scope、Workspace OPEN、optimistic version、current pointers/generation guards。
> 当前 BaselineHead 必须满足 caller expected node/version，并与 preflight Head 及 immutable
> Preview 的 baseline binding 三字段完整一致：business_baseline_node_id、
> business_baseline_commit_id、baseline_head_version。Caller body 不新增 expected commit 字段；
> commit 由 server-owned Head/Preview facts 比较。Preview 必须非 derived-stale；仅在完整
> equality 通过后，使用绑定该 Head 的 preflight canonical digest 执行 NO_CANONICAL_CHANGE
> guard。包括 commit-only 在内的 Head 漂移均先拒绝，不混用 fresh Head 与旧 digest，
> 不在事务内重新获取 canonical digest，也不能仅复用现有 node/version guards 代替完整比较。
> Same-key replay 仍按既有冻结 fingerprint/Attempt facts 比较，不施加新 key 的当前 Head CAS；
> 当前 session/exact scope/Repository 可见性重新授权仍适用，不能借 replay 绕过 mapping 禁用。

### §13.1：追加 provisioning 生效说明

> HTTP/worker bootstrap 的 provisioning 输入按既有 seed 事务写入运行时 projection；文件更新
> 不意味着自动 hot reload。每次已授权 seed 提交是一次 provisioning 应用。本文不新增 reload
> writer、不改变 seed/upsert 生命周期；若要禁止旧 seed 覆盖、支持热更新或多 writer generation，
> 应另行修订对应 provisioning owner contract，不由 D-1 隐式实现。

签署时同步纠正 Round-2 Brief §4/§5/§8.2：“无表”“条款天然互斥”“T2 拦截 Head 漂移”的依据
撤回，旧 §8.2 preflight-only 候选标为 superseded，保留历史说明而不继续作为执行依据。
在 execution plan 中批准 §4 所列新增路径；相关 S2 handoff 引用本计划并保留独立 closure 门禁。

```yaml
decision_direction: same_uow_projection_freshness
user_direction_confirmation: confirmed_in_conversation_2026_09_15
design_owner: Backend vNext Architecture
design_owner_signature_or_decision_reference: d1_t1_implementation_plan_2026_09_15
owning_design_commit: pending_at_implementation_tip
allowed_paths_amendment_commit: pending_at_implementation_tip
implementation_authorization_reference: d1_t1_implementation_plan_2026_09_15
independent_design_review: pending
```

Owner 签署不是代码验收；在条款应用、实现符合性和独立复审完成前，不改
`unresolved_contract_drift` 为 `none`，不签 S2 pass。

## 4. 实施范围与步骤（获授权后）

批准路径：

- `vnext/backend/src/gateway_backend/application/submission/{ports,accept,accept_transaction}.py`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/{database,sqlite_mapping,__init__}.py`
- `vnext/backend/src/gateway_backend/domain/workspace/ports.py`（仅若最小 typed port 需要）
- `vnext/backend/tests/test_submit_transactions.py` 及确有需要的既有 typed test doubles。
- `vnext/backend/tests/test_architecture.py`（只对批准路径作对应 owner/allowlist 调整）
- 本文、owning design/plan、S2 brief/handoff。

其中 `sqlite_mapping.py` 必须显式补入原 S2 allowed paths；其他 test-double 路径若不在原授权内，
先记录 exact path 并批准，不能以测试修复为由扩大范围。

步骤：

1. 为 Submit transaction 暴露最小 typed projection read participant；基础设施绑定
   `unit_of_work.connection`，复用 existing row decoding，按 device/project key 查询。
   不把 sqlite3.Connection 泄漏到 application，不按 Repository-only `LIMIT 1` 猜 scope。
2. T1 查询 key 后按两个分支处理：已有 key 必须先做同连接 fresh mapping 重新授权，再按
   frozen fingerprint 返回 replay/conflict；没有 key 则读取 fresh mapping/Head，执行新 key
   validation。禁止把 projection read 仅放在新 key 分支，或在 fresh 授权前提前 return replay。
   新 key 明确比较 Head node/commit/version 完整 equality；replay 不套当前 Head CAS。
3. 测试前置状态显式 seed projection；Tracking UoW/typed fakes 同步适配，不依赖动态 monkeypatch
   attribute 补协议。仅在权威 semantic barrier 注入漂移，不穷举内部 SQL。
4. 更新 handoff：changed paths、code candidate 全 SHA、owner 决策、验证、容器延期与剩余门禁。

禁止：schema/migration 变更；新 provisioning writer/hot reload；T2/T3/abort 状态机修改；
Repository public wire、依赖/lock、Rust、UID/IPC、容器接线与跨文件锁。遇到这些需求先 reopen。

## 5. 验证与退出

权威测试 owner：`tests/test_submit_transactions.py`；不在 adapter/domain 重复完整漂移矩阵。

- 新 key 共享参数表：preflight 后、T1 前提交 Head version-only/node/commit-only 漂移、
  mapping disable/换仓。Version-only、commit-only 均保持 Repository main CommitId 不变，
  commit-only 还保持 node/version 不变，证明完整 Head equality 必须先于旧 canonical digest 复用。
- 断言既有 contract 错误及零新增 Attempt/idempotency/Operation/Step/occupancy/protection，
  Workspace version 不变；保留注入的 projection 变更，不能把“零写”误写为回滚另一事务。
- Happy path/replay、no-op 优先于 occupancy/closure、stale version 时 baseline_calls==0、
  外部 port 零活跃 UoW、T1 rollback 和 T3/abort fencing 继续通过。
- 并发 winner 转 replay 的代表性共享参数表：原请求 preflight 观察 key 不存在；在 fake
  main-resolve 回调中通过真实 Accept 提交同 key winner，再提交 projection 变更，原请求进入
  T1。至少覆盖 mapping disable → 授权拒绝；仅 Head 漂移 → 返回同一 winner replay。
  Winner 必须使用匹配的冻结 fingerprint，不能靠 idempotency conflict 偶然拒绝。断言原请求
  没有新增/改写 winner 的 Attempt/idempotency/Operation/Step/occupancy/protection，返回或拒绝
  均保留 winner 和注入的 projection 变更；Head 漂移 replay 不再调用外部 ports。
  原请求起初按新 key 已执行的 preflight baseline/main 调用不能算作 replay 违规；在 T1 入口
  记录调用计数，断言 replay 分支无额外调用，并单独记录 winner 的调用。回调使用不递归的
  winner main-resolve fake，无需线程或真实同时调度。
- 漂移用短事务在 fake main-resolve 回调中提交即可，不新增线程、sleep 或真实 Dolt fixture。

阶段性运行 backend 九文件 focused（现有基线 158 项；整改后以实际收集数为准），再运行 backend
unit；所有直接 uv 调用使用隔离配置的 `uv run --locked`。五包 ruff/mypy 必须通过。
最终阶段执行权威 `./vnext/scripts/run-tests.sh`，不把 focused 当全量证明。

退出：owner 已签署且 owning 文档对齐；上述实现/测试独立 pass；code candidate 全 SHA 与 source
一致；S1 countersign 独立完成；方可关闭 D-1 并评估 S2 pass，不能沿用此前代码 tip 的 closure。
D-2 不在本计划内，保持 reported。

容器：本计划当前为 docs-only，当前 HEAD 见 §1，rebuild required=no，最后 image
revision/source-tree 未独立核验，current gate=deferred。纯 T1 Python follow-up 可延期；
阶段最终候选/S3 ready 前必须重建并核对 final HEAD provenance、执行相应容器门禁。
建议先完成[uv.lock 工程计划](../../../uv-lockfile-canonical-guard-pending.md)，再进行该最终重建。

## 6. 启动提示词与独立评审

> 阅读本计划及 owning design/plan、AGENTS.md。先核验 owner 签署、条款落盘、allowed paths 和
> 明确 implementation authorization；任一 pending 则只做文档工作，不实施。获授权后仅完成
> T1 同连接 projection freshness：replay 返回前先 fresh mapping 授权，新 key 比较完整
> node/commit/version。保留 replay/no-op/I/O/版本 fencing 语义，不新增 provisioning
> 生命周期机制，不改锁或 Repository wire。保留工作区用户改动，focused 优先；handoff 记录
> exact candidate SHA、commands/results、deferred gates 和容器决策，不自行签独立 closure。

Owner 条款/计划评审与实施验收均建议新开独立 conversation/context，按 authority-first、
findings-first 检查。当前对话可继续答疑与讨论整改；执行者的自查不替代独立评审。

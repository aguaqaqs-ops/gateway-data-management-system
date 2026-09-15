# P5-5B-S2 Round-2 评审 Findings 与整改说明

状态:**frozen round-2 remediation input(含 2026-09-15 第四卷复审方反馈修订,见 §8)**

日期:2026-09-15

Owner:P5-5B Delivery(实现) + 独立评审(复核/签署)

评审对象 parent HEAD:`c561ffe9`(fix(backend): remediate P5-5B S2 T1/T3 control-DB findings)

Finding 输入:
- 第一卷:[p5-5b-s2-independent-review-findings.md](p5-5b-s2-independent-review-findings.md)(S2-F1–F13;本轮裁定 F14–F17 为其未穷尽部分,F11 的"部分以替代测试闭合"见 S2-F17)
- 第四卷:独立复审(2026-09-15,对 `c561ffe9` 出具「不通过:2 blocker + 1 P2 + 流程未闭合」)

裁定说明:本卷对第四卷复审的每条断言均已对 `c561ffe9` 源码与设计原文
(`p5-5b-submit-finalize-design.md`)独立复核;采纳/不采纳及理由见 §3 与 §5。

## 1. Traceability

```yaml
stage: P5-5B-S2-round2-remediation-input
parent_head: c561ffe9
round1_finding_closure: S2-F1..F13 视为闭合,例外 F11 → 由 S2-F17 收口
new_findings: [S2-F14, S2-F15, S2-F16, S2-F17, S2-F18]
design_clarifications_escalated: [D-1, D-2]
pass_gate: [F14-F18 闭合 且 §6 gate 绿, D-1 裁定/勘误落地 → unresolved_contract_drift none]
rejected_prescriptions: [T1-内重读-mapping/BaselineHead, Head-drift-零写入测试]
plan_alignment_note: 本轮整改不新增 S1 属路径例外(F3 对齐项沿用第一卷记录)
```

## 2. Findings 摘要

| # | 严重度 | 主题 | 处置 |
| --- | --- | --- | --- |
| S2-F14 | P1(blocker) | T3/abort 缺**调用方观察 version** fencing(lease identity 已补,version 未补) | 代码 + 测试 |
| S2-F15 | P1 | T1 preflight 违反 §6.1「顺序固定」:main_resolve 先于 NO_CANONICAL_CHANGE 裁决;no-op 先抢写锁再回滚 | 代码 + 测试 |
| S2-F16 | P2 | PREPARED stable-abort 为不可达死分支;合成态测试;handoff matrix 虚假行;P2 取消路径设计缺口 | 代码 + 测试删除 + 文档 + 设计上报 |
| S2-F17 | P2 | round-1 F11 残留:`save_workspace` CAS 失败回滚路径未被测试覆盖 | 测试 或 不可达论证记录(二选一) |
| S2-F18 | 流程(blocker) | candidate_head 未绑定、S1 countersign 未落盘、changed_paths 漏 1 文件 | docs only |

## 3. 整改规格

### S2-F14 [P1] T3/abort 补调用方观察 version fencing

**设计依据**:§10.2:639(SubmitAttempt 行「operation/result identity and expected version」)、
:643(Operation/await Step 行「current lease token、**Step/Operation expected versions**」)、
§11:677(JobDefinition/Step CAS 和 Attempt version fence)、:678(拒旧 lease publication)。
现状:lease identity fencing 已闭合(round-1 S2-F5),但三个 CAS 的 expected version 全部取
**事务内新鲜行值**(`finalize_transaction.py:87-90/132-152`,abort 同型 `abort_transaction.py:96-99/170-178/202-209`)。

**风险形态(单写者串行化下仍成立)**:caller 持 Step/Operation version v1 视图;其 effect 期间
另一已提交写入(cancel 请求)将记录推进到 v2;caller 的 T3 后启动、读 fresh v2、CAS 以 v2 恒成功
→ 已发出的 cancel 被静默覆盖为 SUCCEEDED,occupancy 照常释放(parent 复审已按此复现:
`old_version=1 / cancel_version=2 / final_status=SUCCEEDED / cancel_requested=True`)。

**整改**:
1. `FinalizeSubmitTransactionRequest` 新增**必填**字段:`expected_attempt_version: int`、
   `expected_await_step_version: int`、`expected_operation_version: int`(caller 调 T3 时**相信**
   记录所在的 version;replay 分支不做 CAS,不受影响)。
2. `finalize_submit_transaction` 的新鲜 finalize 路径:
   - `cas_update_attempt(…, expected_version=request.expected_attempt_version)`
   - await Step CAS:`WritePrecondition(expected_optimistic_version=request.expected_await_step_version, worker_id=…, lease_token=…)`
   - Operation CAS:`WritePrecondition(expected_optimistic_version=request.expected_operation_version, …)`
   - 失配由既有 P4 CAS / 提交仓储错误承载(`StaleWrite` / `SubmitAttemptVersionConflict`),
     **不新增错误类型**;§5.4:399-400 的 `OPERATION_VERSION_CONFLICT`/`STEP_VERSION_CONFLICT`
     409 码是 HTTP 层(S4)映射面,S2 不预造。
   - Workspace 行 CAS 保持 fresh expected version 不变(§10.2:640 对该行的 CAS 面是
     「current active Attempt must match」,不是 version)。
3. `AbortSubmitTransactionRequest` 新增**可选**字段(默认 None → 维持 fresh 行值语义,文档注明
   best-effort,因 §10.3 未对 abort 冻结 version fence):`expected_attempt_version/
   expected_await_step_version/expected_operation_version`;非 None 时同上用于对应 CAS。
4. 全部既有测试的 `_finalize`/`_abort` helper 扩展:happy path 传当前行观察值(行为不变);
   矩阵保持绿。

**必须新增的测试**:
- T3:lease token 不变、但 caller 传**旧** step version(构造:观察后由另一 UoW 以同 lease
  推进 step 并置 `cancel_requested=True`)→ 拒绝(`StaleWrite`),断言 step/operation/attempt
  均不终态、双 occupancy 未释放(即 parent 复审复现反转);
- T3:旧 attempt version → 拒绝;
- abort:旧 step version(可选字段非 None 场景)→ 拒绝;
- 既有 takeover 测试(旧 token)保持绿 → fencing 两面(token + version)各自有 owner 测试。

**验收**:round-4 复现场景由「成功终态化」翻转为「拒绝且零终态写」;原 152 测试集全绿。

### S2-F15 [P1] T1 preflight 对齐 §6.1 固定顺序

**设计依据**:§6.1:416「顺序固定」;step 4(:424-425)「对新 key 解析唯一 active
mapping/BaselineHead,检查 caller body binding、derived-stale、canonical digest 与 current
business base。`NO_CANONICAL_CHANGE`**在此**返回且不写 idempotency row」;step 6(:427)
`ResolveVersionedRef(main)`;:428-430(T1 后 main drift 由 T2 mandatory CAS 稳定拒绝)。

**现状偏差**:`accept_submit_transaction` 对每个 new key 都调用 `main_resolve`
(parent 复审实测 `NO_CANONICAL_CHANGE 场景 main_resolve_calls=1`),且 NO_CANONICAL_CHANGE
裁决发生在**写事务内**——no-op 请求先 `BEGIN IMMEDIATE` 再回滚(比「多调一次」更强:
no-op 串行化阻塞全部写者,且 main 库 503 会错误阻断纯本地 no-op)。

**整改**:
1. **preflight 阶段三分**(2026-09-15 复审修正 fix-2):§6.1:416 / plan :177 禁止的是
   **任何** SQLite transaction(含 read-only)内执行 session file / artifact / Repository
   network I/O——禁止对象是「transaction」,不是「写锁」。Round-2 初稿(本卷原版 item 1
   「不持写锁阶段」与 item 2「port 调用位置不变」)把 `baseline_digest` port 调用移入
   read-only UoW(`accept_transaction.py:136-145` 内 → `accept.py:197`;探针
   `connection.in_transaction=True, read_only=True`),相对 `c561ffe9` 是**回归**
   (该 HEAD 同一调用位于 read-only UoW **关闭之后**、完全无事务)。本轮回退并按下述
   子阶段重排:
   - **(a) read-only UoW**:只读取并物化 control DB 记录——replay 检测、Workspace、
     UploadRevision、PreviewResult、SubmitIdempotency;不调用任何外部 port、
     不执行 step 3-5 裁决;
   - **(b) 无任何事务**(读事务已关闭):在物化快照上执行 step 3-5 裁决(exact
     scope / repo 匹配 / open / version CAS binding、preview binding、derived-stale、
     `baseline_canonical_digest` port 调用 → digest 比对 → `NoCanonicalChange` 早返回、
     occupancy、closure digest)——**一切外部 I/O 只发生在本子阶段**;
   - **(c) `main_resolve`(step 6)**:同样在任何事务外,且仅在 no-op 已排除后调用。
   `validate_accept_submit_with_frozen` 的事务内重读不变(§6.3 step 2-8:
   workspace/upload/preview fresh、version CAS、指针/generation、**再次执行
   NO_CANONICAL_CHANGE guard**(:449-450)、occupancy、protection)——T1 内 I/O 全部
   是 control DB 读,无外部 port。当前 `preflight_new_accept_submit` 函数体可改为对
   物化快照的纯函数(由 (a) 的读结果喂入,baseline_digest 在 (b) 传参调用)。
2. 不变式(本子阶段自然满足,测试按事件证明):preflight 任一外部 port 回调期间
   `connection.in_transaction is False`,且全程从未请求 `read_only=False`。
3. `AcceptSubmitPreflight` frozen 字段与 `SubmitControlUnitOfWorkFactory` 读路径不变
   (round-1 S2-F4 结构保留)。
4. **明确不做**:不加 mapping/BaselineHead 读取参与者、不做「T1 事务内重读
   mapping/BaselineHead」、不加「preflight 后 Head 漂移 → 零写入」测试——见 §5 D-1 与
   §4 不采纳项。

**必须新增的测试(含复审 fix-2 升级)**:
- NO_CANONICAL_CHANGE 场景:`main_resolve.calls == 0`、零写入(无
  idempotency/attempt/occupancy/operation/step、workspace version 不变)、**writer 事件
  历史**断言——`WriterLockTracker` 必须记录 factory 调用事件(如 `writer_entries: int`
  或 `read_only` 参数历史),断言 no-op 路径**从未请求** `read_only=False`;
  终审态布尔标志(`writer_open` 最终值)不具证明力——2026-09-15 复审变异探针已证实:
  调用前插入一次写事务再关闭,现有断言仍通过(`inserted_writer_transactions=1` →
  用例假绿);
- 外部 I/O 事务外探针:`baseline_digest` / `main_resolve` 回调内
  `connection.in_transaction is False`(round-1 F4 探针测试同方式升级保持绿);
- happy path 回归:`main_resolve.calls == 1`、writer entry **恰好一次**(T1 写事务)。

### S2-F16 [P2] PREPARED stable-abort 死分支 + 文档虚假行 + 设计缺口上报

**依据**:§10.3:651「自动ABORT**只**接受原Repository operation identity的普通未发布stable
FAILED」;:657-659(pre-request 失败/`request_sent=false`/`PRE_REQUEST` 分类「不是
`NOT_PUBLISHED` 证明,也不扩充ABORT集合;它们保留occupancy并进入retry或
`MANUAL_RECOVERY_REQUIRED`」);§6.4:469(T1 不创建 Repository request/operation);
代码 `abort.py:25-29`(`repository_operation_id is None → AbortProofNotSatisfied("matching
repository operation identity is required for business abort")`)。即:**任何真实 PREPARED 行
必被 proof gate 拒绝**,`abort_submit_transaction` 的 PREPARED 接受门不可达;
`test_prepared_abort_releases_occupancy_without_live_lease` 用 `cas_update_attempt` 手工构造
「PREPARED + repository_operation_id」这一机器上不可能存在的行,再以「闭合」宣称
round-1 F11 的 PREPARED 项。

**整改**:
1. `abort_submit_transaction` / `_abort_submit_in_transaction` 状态门收窄为
   **EFFECT_PENDING-only**(read-only 快路径与写事务内双重检同步收窄,错误消息同步更新);
   S1 面 `abort.py` 不变。
2. 删除 `test_prepared_abort_releases_occupancy_without_live_lease`(含合成态构造);
   S4/S5 接入面无 PREPARED abort 调用方(§10.3 下由 P4 retry/MANUAL_RECOVERY 承接)。
3. 文档:`p5-5b-s2-handoff.md` matrix 删「PREPARED abort」行;补救卷 F11 行同步订正;
   第一卷 findings 文档 F11 项在 round-2 补救卷中记录为「以 S2-F16 收窄替代闭合」。
4. 设计缺口 **D-2** 上报(见 §5):QUEUED/prepare-PENDING 未拾取期的用户取消无释放
   business occupancy 的收口路径(P4 cancel → operation CANCELLED,但 attempt PREPARED +
   双 occupancy 保留 → 后续 Accept 被 occupancy 阻塞;§10.3 未提供非 stable-failure 释放口)。
   交设计 owner 裁定;S2 不得私补契约或新增释放口。

**验收**:PREPARED attempt 调 business abort → 状态门拒绝;EFFECT_PENDING abort 矩阵
(round-1 全组测试)保持绿。

### S2-F17 [P2] F11 残留:`save_workspace` CAS 回滚路径

**现状**:`test_t1_rejects_stale_workspace_version_without_writes` 在调用前 bump workspace、
由 pre-T1-validation(`assert_workspace_version_cas`)拒绝——未开写锁、无前缀写,未覆盖
round-1 F11 原文所指的 `save_workspace` CAS 失败回滚路径。

**裁定**:BEGIN IMMEDIATE 单写者下,事务内 `save_workspace` CAS 失败**不可达**(写锁持有
期间行不可被任何写者推进),仅 monkeypatch 注入可触达 → 属防御性覆盖。

**闭合方式(实现者择一并记录到 round-2 补救卷)**:
- **A.** 补注入测试:monkeypatch `SQLiteWorkspaceRepository.save_workspace` 恒抛
  `WorkspaceVersionConflict` → 断言全前缀回滚(idempotency/attempt/operation+step/
  双 occupancy/attempt protection intents 全缺、preview protection 保留、
  workspace version 不变);或
- **B.** F11 闭合记录写明单写者不可达论证 + 现有前置拒绝测试即覆盖可达契约。

### S2-F18 [流程] closure 与 provenance 落盘

1. **binding 提交**:两份 S2 handoff 的 `candidate_head` 由
   `uncommitted_working_tree_on_3d39fdcf` 改为本轮整改后 **review tip** 的全 SHA
   (镜像 S1 `f933c76c` 模式:代码 tip 在下、绑定文档提交在上)。
2. **S1 countersign 落盘**:S1 handoff `status`/`next_step` 闭字(closure 达成);
   签署依据记录于 round-2 补救卷:S1 focused gate 复跑 102 round-1 记录 + round-2 复审
   亲跑 9 文件 152/全包 1876/0 failed/ruff/mypy clean 交叉证据。签署方为独立评审,
   实现侧不得自签。
3. **changed_paths**:`p5-5b-s2-handoff.md` 补
   `docs/…/p5-5b-s2-independent-review-findings.md`(commit 实触 21 文件,现列 20)。
4. **round-2 补救卷**(实现侧新写
   `p5-5b-s2-round2-remediation-handoff.md`,对齐 round-1 卷结构):
   finding → fix → test owner → retest 矩阵(F14–F18 五行)+ D-1/D-2 上报状态 +
   verification record + 锁 diff 为空声明。

## 4. 不采纳项(含理由,供实现者与复核者引用)

| 处方(第四卷复审 #1) | 不采纳理由 |
| --- | --- |
| 「T1 使用同一事务连接重新读取 mapping/BaselineHead」「`SubmitControlTransaction` 增加 mapping/BaselineHead 读取参与者」 | **撤回（D-1 裁定）**。mapping/BaselineHead 已由 Workspace schema v2 `provisioned_scope_mappings` projection 承载；T1 同连接 SQLite 读取不属于 §6.1 禁止的外部 I/O。见 [D-1 执行计划](p5-5b-s2-d1-projection-freshness-execution-plan.md) 与 owning design §6.1/§6.3 勘误。 |
| 测试「preflight 后 Head 漂移 → 零写入」 | **撤回（D-1 裁定）**。新 key 在 T1 须完整比较 Head node/commit/version；T2 mandatory CAS 仅保护 Repository main CommitId，不替代 Head equality。见 D-1 执行计划 §5 测试规格。 |

## 5. 设计澄清项(上报设计 owner,不在 S2 授权面内解决)

- **D-1 —— S2 pass 门禁项**:design §6.3:446「transaction-fresh 读取 mapping、
  BaselineHead」与 §6.1:416「禁止事务内 session file I/O」互斥(mapping/BaselineHead 均为
  session/mapping file 来源,非 control DB 表)→ 冻结设计自相矛盾 = 未解 contract drift。
  依 plan authority gate(:45)`unresolved_contract_drift: none` 与 2026-09-15 第四卷复审
  门禁条件:**D-1 未裁定/勘误落地前不得签 S2 pass**。归责保持:矛盾先于 S2 存在于冻结
  设计,不归罪 `c561ffe9` 代码;round-2 代码以 §4 执行基线推进不变。裁定产物 = design
  owner 签署的勘误(候选文本 §8.2),使 §6.1/§6.3 不再互斥。
- **D-2 —— 登记上报,不 gate S2 pass**:QUEUED/prepare-PENDING 未拾取期的用户取消,无
  释放 business occupancy 的收口路径(见 S2-F16.4)。与 D-1 的非对称定性:D-1 是既有
  条款**自相矛盾**(= contract drift,属 authority gate 面);D-2 是设计**未定义**路径
  (缺口,非 drift),不触发 `unresolved_contract_drift`。请求裁定:该窗口靠 operator
  recovery 人工释放、新增非 stable-failure 释放口、还是取消语义保留 occupancy 至 retry;
  裁定前 S2 不实现任何释放行为。

## 6. Gate(round-2 整改最小并集)

```bash
cd /home/dev/gateway-data-management-system
git diff -- vnext/backend/uv.lock | wc -l   # 必须 0(锁卫生,round-1 F2 规则保持)

cd vnext/backend
uv run pytest -q -m unit \
  tests/test_architecture.py \
  tests/test_submit_domain.py \
  tests/test_submit_application.py \
  tests/test_submit_idempotency.py \
  tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py \
  tests/test_submit_transactions.py \
  tests/test_sqlite_workspace_repository.py \
  tests/test_workspace_control_db_migrations.py
uv run pytest -q -m unit      # 全包 0 failed
uv run ruff check . && uv run mypy
```

新增测试组(缺一不得声称对应 finding 闭合):

1. T3 旧 step version(token 未变 + cancel_requested 场景)→ 拒绝且零终态写(F14)
2. T3 旧 attempt version → 拒绝(F14)
3. abort 旧 version(可选字段)→ 拒绝(F14)
4. NO_CANONICAL_CHANGE → `main_resolve.calls == 0` + writer entry 事件历史为零 + 零写入 + 外部 port I/O 事务外探针(F15,含 fix-2)
5. PREPARED 拒绝门 + EFFECT_PENDING abort 矩阵回归(F16)
6. (若选 A)`save_workspace` 注入失败全前缀回滚(F17)

版本红线:不触碰 `uv.lock`、Dockerfile、P4 protocol、owning contracts;S1 属路径
零新增例外(D-1/D-2 均未落代码)。

## 7. 复核与 S2 pass 门禁

整改后独立评审按 §6 gate + 逐 finding 证据复核。**S2 PASS(= S3 entry 前置)是 join,
不是串行链**:

1. **代码轨(A)**:F14/F15/F16/F18 全闭合 + F17 选定方式记录在案 + §6 gate 全绿
   (9 文件 + 全包 unit + ruff/mypy + 锁 diff 为 0 + 6 条新增测试)。
2. **设计轨(B)**:**D-1 裁定落地**——design owner 签署勘误(§8.2),§6.1/§6.3 不再互斥,
   authority gate 恢复 `unresolved_contract_drift: none`(plan :45)。D-2 仅需上报在案,
   不 gate pass(裁定前不得实现释放行为)。
3. **过程轨(C)**:F18 四项完成(binding 提交 candidate_head → review tip 全 SHA、
   S1 countersign 落盘、changed_paths 补全、round-2 补救卷)。

两轨并行:A 的整改 spec 零依赖 D-1 裁定(§4 执行基线双方已确认);B 不等待 A。
**任一轨未完成不得签 S2 pass**——「代码修完而 D-1 悬置即 pass」被明确排除
(第四卷复审门禁条件,本卷采纳)。签署:独立评审按 §6 + 本节复核通过后,出具 S2
closure 签署(binding 提交后)与 S1 closure 落盘确认;S1 countersign 依据见 F18.2。

## 8. 第四卷复审反馈采纳记录与 D-1 勘误候选

### 8.1 反馈采纳(2026-09-15,第四卷复审方对本文仲裁的反馈)

| 反馈点 | 处置 |
| --- | --- |
| 「S2 allowed paths 含 `domain/workspace/ports.py`,'路径无授权'理由不成立;真正禁止是 plan :60 owning contract 语义规则」 | **采纳,已修正** §4 理由(plan :165/:60 亲验) |
| 处方问题应定性为「§6.1/§6.3 不可同时由现有架构实现 → design/ownership clarification」 | **采纳** 改写原文入 §4;D-1 定性为 design finding 而非 finding 无效 |
| 「D-1 不得在 S2 pass 时悬置:authority gate 要求 `unresolved_contract_drift: none`」 | **采纳,升级为 pass 门禁** §5 D-1 / §7 设计轨 |
| F15 评 P1 可接受(Blocker 保留给数据完整性/跨 scope 写/不可恢复状态机错误);F15 仍必须阻止 S2 pass | **确认**,与 §6 gate 一致(F15 在 gate 内即 pass-blocking) |
| F14 为真实新 finding(round-1 F5 规格漏 version half);F16 PREPARED 与 T2 crossing 顺序冲突 | **确认**,T2 crossing 佐证记入 F16 依据 |

### 8.2 D-1 勘误候选文本（**superseded** — 保留历史，不作执行依据）

> **状态：superseded。** 第四卷复审 preflight-only 弱化路线已被 D-1 裁定（`same_uow_projection_freshness`）取代；权威文本见 [D-1 执行计划 §3](p5-5b-s2-d1-projection-freshness-execution-plan.md) 与 owning design §6.1/§6.3 落盘版本。以下为历史候选原文:
>
> 建议将 design §6.3 step 2(:446)「transaction-fresh 读取 mapping、BaselineHead」勘误为:
> 「transaction-fresh 重读 control DB 可变业务 facts(Workspace、Upload、Preview、
> SubmitAttempt、SubmitIdempotency、双 occupancy);mapping/BaselineHead 使用 preflight
> step 4(replay 裁决后、T1 写锁前)最近解析并冻结的值;main 业务基线 drift 由 T2 的
> Repository mandatory CAS 对 expected business base 稳定拒绝」。§6.1:416 覆盖已足够,
> 无需改动。
>
> 若 design owner 裁定相反方向(要求 BaselineHead 跨边界真实屏障),该裁定构成新的
> owning-contract 特性 → 按 plan :60 触发 reopen/new slice,不得并入 S2 授权面。

### 8.3 Round-2 复审修正记录(2026-09-15,第二轮独立复审)

| 反馈点 | 裁定 |
| --- | --- |
| [P1] `baseline_digest` port 调用位于 read-only SQLite 事务内(`accept_transaction.py:136-145` → `accept.py:197`;探针 `in_transaction=True, read_only=True`);§6.1:416 禁止对象是任何 transaction 而非仅写锁;`c561ffe9` 原合规(read-only UoW 关闭后调用),round-2 初稿规格措辞(「不持写锁阶段」/「port 调用位置不变」)致回归 | **采纳**。P1 契约违规,round-2 新引入(非 `c561ffe9` 存量);本卷 §3 F15 已改为三分子阶段(物化 → 关读事务 → 外部 I/O → main_resolve),代码须回退该回归。本修正不依赖 D-1 裁定 |
| [P2] no-op 测试仅断言终审态 `writer_open=False`(`WriterLockTracker` 为状态标志,test :105-106);插入-关闭一次写事务后断言失效(变异探针 `inserted_writer_transactions=1` 仍 passed) | **采纳**。升级为 writer 事件历史断言(零 `read_only=False` factory 调用);happy path 钉 writer entry 恰一次 |
| [F18/文档] S2 handoff authority yaml 仍 `unresolved_contract_drift: none` 而 round-2 handoff 记 D-1 pending;changed_paths 漏 `p5-5b-s2-round2-remediation-brief.md`;SHA binding / S1 countersign 属已声明进程待办(不计闭合) | **采纳**。前两项为实现侧文档修正(对齐 authority 快照、补 changed_paths);后两项按 §7 过程轨待办 |

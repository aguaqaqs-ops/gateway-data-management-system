# P5-5B-S2 独立评审 Findings 并集(三份评审)

状态:**frozen finding input for S2 remediation round**

日期:2026-09-14

Owner:P5-5B Delivery(实现) + 独立评审(复核)

评审对象:commit `3d39fdcf884ff71899664154f4ef9c6e19fa6147`
(`feat(backend): deliver P5-5B S2 submit control DB and T1/T3 UoW`,branch `phase1/gate-ownership-repair`)

## 1. 评审输入

| 代号 | 对象 | 主要贡献 |
| --- | --- | --- |
| A | 首轮评审(工作树,提交前) | 架构守卫双向越界、uv.lock 漂移、T1 锁内 resolve、migration 探针缺失、matrix 缺行 |
| B | 第二轮独立评审(工作树) | S1 closure 门禁、lease fencing、abort 崩溃续跑死路(已复现)、registry 只验一步、occupancy 非 owner-qualified、handoff 超额声明 |
| C | 第三轮独立评审(commit `3d39fdcf`) | T3 replay 不验 closure、decoder 强制转换、F4 的 handoff 自相矛盾、preflight frozen-facts 字段不足 |

三份评审的全部关键断言均已被-coordinate 人重新对照源码逐条核实;无不实 finding。
现状基线(在 `3d39fdcf` 源码上亲跑):

- S2 focused 5 文件 `-m unit`:**27 passed**
- 全包 `-m unit`:**1851 passed / 2 failed**(2 个失败均为 `tests/test_architecture.py`)
- `ruff check`:clean;`mypy`:clean(332 files)
- `uv.lock`:**提交内未改动**(与基线 canonical `21c8da4f…` 一致,registry = pypi.org);
  当前**工作树**存在 640 行 mirror 漂移(313 处 `192.168.233.184`),为提交后环境再污染,非交付内容。

## 2. Findings 并集(去重后)

编号沿用 `S2-Fn`。`来源` = A/B/C 中谁先发现;同一条多个来源表示独立复证。

### Blocker(S2 不得视为 pass)

#### S2-F1 [blocker·流程] S1 独立 closure 未签署,S2 handoff 缺 provenance 字段(来源:B)

- plan `p5-5b-submit-finalize-execution-plan.md:154` S2 `Entry:S1 independent pass`;
  S1 handoff `p5-5b-s1-handoff.md:101` 仍为 `next_step: independent_re_review_of_S1_round_3_closure`;
  S1 remediation handoff `p5-5b-s1-remediation-handoff.md:131` 明确「`pass` 后可签署 S1 closure,再开 S2」。
  plans 目录不存在 S1 独立 closure 记录。
- S2 handoff 缺:candidate_head、authority 块、changed paths 清单、container
  rebuild decision/last_verified_image_revision(AGENTS.md 每轮评审记录要求 + S1 handoff 先例)。

解决建议:
1. 先跑 S1 focused gate(plan §S1 冻结命令:`test_submit_domain.py`/`test_submit_application.py`/
   `test_submit_idempotency.py`/`test_architecture.py` + ruff + mypy)记录 Round 结果,
   补 S1 独立 closure 文档(或在本卷补救卷中专门记录复跑+签署),将 S1 handoff `next_step` 更新为闭合。
2. S2 handoff 重写时(见 S2-F13)加入 candidate_head(= 整改后新 HEAD)、authority、changed paths、
   container decision(S2 纯 control DB/application 变更,未触碰 image/deployment 边界 → no,含理由)。
3. 注意:S2-F3 会动 S1 属路径,签署 S1 closure 与整改的先后顺序由实现者定,
   但提交 S2 candidate 前两个 gate 必须都绿。

#### S2-F2 [blocker·scope] uv.lock 工作树漂移(来源:A/B;状态:提交面已解决,余工作树卫生)

- `3d39fdcf` **未触碰** `vnext/backend/uv.lock`(与基线 canonical identity 一致)。
- 当前工作树 lock 被环境 index 改写为 LAN mirror(`http://192.168.233.184:3141/root/pypi/simple`),
  丢 `size`/`upload-time`,版本/哈希无 drift。plan S2 明令禁止改 lock;AGENTS.md 要求 canonical PyPI identity
  + 隔离 machine-level index。

解决建议:`git checkout -- vnext/backend/uv.lock`,确保后续每个 commit 的 `git diff ... uv.lock` 为空;
在 handoff 记录该环境现象(指认 index 隔离未生效的环节),防止下轮再漂。

#### S2-F3 [blocker·架构守卫] application 与 control_db 双向 import 越界,全包 unit 红(来源:A)

证据(在 `3d39fdcf` 源码亲跑确认):`uv run pytest -q tests/test_architecture.py` →
**2 failed / 41 passed**。

1. application → infrastructure(禁止边,`test_application_module_respects_import_boundary`):
   `accept_transaction.py:42`、`abort_transaction.py:14`、`finalize_transaction.py:19` 模块级导入
   `ControlDbUnitOfWork` 并以具体类型入参(`accept_transaction.py:94` 的 factory 签名)。
2. infrastructure → application(禁止边,`test_control_db_boundary_exists_and_has_no_application_wiring`):
   `sqlite_submission.py:13-21` 导入 `application.submission.contracts`(3 值对象)+
   `application.submission.errors`(2 异常);`sqlite_submission.py:22+` 导入的
   `domain.submission.models` 亦不在 control_db allowlist(被首条 assert 遮蔽,修复后会继续暴露)。

解决建议(最小修):
1. 三个 orchestrator 的 `unit_of_work`/factory 改注 `ports.py` 已有 `SubmitControlTransaction`
   protocol(已覆盖 `.submission`/`.workspace`/`.operations`/`.transaction_now`/
   `set|clear|list_artifact_protection`),删除具体 import;测试传 `ControlDbUnitOfWork` 实例结构满足。
2. 把 `SubmitAcceptanceRecord`/`WorkspaceSubmitOccupancy`/`RepositorySubmitOccupancy` 移入
   `domain/submission/models.py`;被基础设施 raise 的 `SubmitAttemptVersionConflict`/`SubmitOccupancyConflict`
   移入 `domain/submission/errors.py`(对齐 `domain/workspace` 既有惯例:
   `PreviewAcceptanceRecord`/`WorkspaceVersionConflict` 均在 domain)。批量更新全部引用
   (S1 `accept.py`/`ports.py`/S1 测试)。
3. `tests/test_architecture.py` control_db allowlist 增加 `gateway_backend.domain.submission`
   (与 `domain.workspace` 平列);application 规则不变。
4. **plan 对齐记录**:上述触碰 S1 属路径(`test_architecture.py`、`application/submission/{contracts,errors}.py`、
   S1 测试 import)。该越界是 S2 已授模块边界(`application/submission/**` + `control_db/**`)的固有结果,
   按 plan 规则须在整改卷记录此守护对齐,不得静默扩 scope。

#### S2-F4 [blocker·事务边界] T1 写锁内执行外部 I/O 且双 resolve;abort evidence 在 UoW 内(来源:A/B/C)

design §6.1:416「禁止在 SQLite transaction 内执行 session file、artifact 或 Repository network I/O」;
:427(步骤 6)要求 `ResolveVersionedRef(main)` 在 T1 前完成,失败 503 且不进 T1;
:443-455(§6.3)T1 只 transaction-fresh 重读 control DB 可变 facts。plan S2 Deliver(:177):
「Repository resolve/artifact I/O 使用 fake preflight,不在 transaction 内」。

代码:
- `database.py:221`:`ControlDbUnitOfWork` 默认 `read_only=False`,`__enter__` 直接 `BEGIN IMMEDIATE`。
  `accept_submit_transaction` 的**两个** UoW 块(`accept_transaction.py:102`、`:121`)都是写锁;
  连 replay 快路径也抢写锁两次。
- 两块各跑一次完整 `validate_accept_submit`(`:103`、`:143`),内含 `main_resolve.resolve` +
  `baseline_digest`(S1 `accept.py:106` 起)。第二轮探针:resolve 调用 2 次、**两次均在写锁下**、
  持久化的 `repository_expected_commit_id` 取自锁内第二次。
- `abort_transaction.py:50`:在已打开的写 UoW 内调 `validate_abort_proof(..., evidence=evidence)`
  → Repository evidence 端口(外部 I/O)在写锁内。S2 handoff 自相矛盾:其 S1 复用表写
  「`validate_abort_proof`(stable abort 事务外)」。

解决建议:
1. 拆成 `preflight(无写锁)→ frozen facts → 短 T1`。扩展 `AcceptSubmitPreflight`
   (现仅 snapshot/closure/protection,`:55-60`)冻结全部需 I/O 的 facts:resolved scope、
   baseline canonical digest、Repository main expected commit、closure digest 等(design §6.1 步骤 3-6)。
2. 第一轮 replay 检测可用 `read_only=True` UoW(或不进 UoW 的独立读);T1 内只做
   transaction-fresh control DB 重读 + unique/CAS/occupancy/protection 裁决(§6.3),**不再调用任何 port**。
3. abort:先在事务外取并验证 stable-failure evidence,把纯 proof + frozen facts 送进短事务;
   修正 handoff 措辞。
4. 新增测试组(与 C 一致):port 回调执行时断言 writer transaction 未打开
   (如注入记录 `SELECT 1 FROM pragma_transaction`/busy 状态,或断言 UoW 以 read_only 模式进入)。

#### S2-F5 [blocker·fencing] T3/abort 无 lease/version fencing,late writer 不可识别(来源:B)

design:§10.2 T3 matrix(:643)「current lease token、Step/Operation expected version」;
crash matrix(:678)「business checkpoint/T3 CAS 拒绝旧 lease publication」。plan exit(:201):
「独立 review 必须检查没有先读后写替代 unique/CAS」。

代码:`FinalizeSubmitTransactionRequest`(`finalize_transaction.py:27-32`)不携带
worker/lease token/expected version;`:101-125` 在同一写事务内新鲜读 `await_step` 后,
用**行上当前值**构造 `WritePrecondition(worker_id=await_step.worker_id, lease_token=await_step.lease_token)`。
`BEGIN IMMEDIATE` 单写者下 load→CAS 对自己读到的值恒成立 → 对旧 worker 零防护。
abort 同型(`abort_transaction.py:114-121`)。

解决建议:
1. `FinalizeSubmitTransactionRequest`/abort 调用上下文携带 worker 持有的
   `worker_id` + `lease_token`(来自 P4 claim/job payload),`WritePrecondition` 与
   **调用方身份**比较而非新鲜行值;`require_live_lease` 按行 RUNNING 判定保持。
2. operator recovery 路径保留 `worker_id=None` semantics(与 P4 recovery guarded CAS 一致)。
3. 新增测试:lease 已被 takeover(行上 token 更新)后旧 identity 调 T3/abort → 被拒;
   持有当前 lease 的 identity → 成功。
4. 注:V1 单 worker 假设(design :77)降低可利用性,但 design crash table 已冻结该语义,
   本项按 blocker 处理(plan exit 明令检查项)。

#### S2-F6 [blocker·真实 bug] P4 已 terminalize 后 business abort 永久卡死(来源:B,已复现)

design §10.3(:663-666):operator 先经 P4 guarded CAS 收口 Operation/Step;5B 随后执行
**幂等** business abort;「两者之间 crash 只会留下 FAILED Operation + 仍被占用的 Attempt,
startup/replay 继续后半段,绝不提前释放」。

代码:`abort_transaction.py:95-96` 无 active step 时回退
`next((step for step in steps if step.step_name == SUBMIT_STEP_AWAIT), steps[-1])` —
即选中**已 FAILED** 的 await step,`:103-122` 再构造新 FAILED candidate 去 CAS 一个 terminal step →
P4 `ConflictingDuplicate: terminal step has a different candidate` → 整事务回滚。
复现结果:attempt 恒 `EFFECT_PENDING`、双 occupancy 恒保留、**每次重放同型失败,永久卡死**。

解决建议:terminal 步骤/操作幂等跳过 — 选中的 step 已终态则不再 `compare_and_set_step`
(无论 diagnostic 是否相同,终态不可重写);operation 已终态同理跳过。保持其余裁决不变。
新增回归测试:seed EFFECT_PENDING + await step 已 FAILED(operator 收口、diagnostic 任意)→
abort 成功(attempt ABORTED、occupancy 双删、action 记录)、二次 abort → replay=True;
以及变体(await step FAILED 但 operation 仍 RUNNING 的半收口态)。

#### S2-F7 [blocker·跨 scope 误写] occupancy release 非 owner-qualified CAS(来源:B/C)

design §10.2 Repository occupancy 语义(:466「repository/baseline owner Attempt」、:238-239);
AGENTS.md 基础边界「transaction/CAS 和跨 scope 误写不能用比例化跳过」。

代码:`sqlite_submission.py:291-296` `DELETE … WHERE workspace_id = ?`;
`:320-325` `DELETE … WHERE repository_id = ?` — 无 `submit_attempt_id`/baseline 匹配、无 rowcount 检查。
abort 无条件调用两者(`abort_transaction.py:77-78`);T3 按 repository id 删
(`finalize_transaction.py:97`)。同文件正例:`switch_workspace_occupancy_to_submission`
(`:272-289`)已用 workspace+attempt 匹配 + `rowcount != 1 → SubmitOccupancyConflict`。

解决建议:
1. `delete_workspace_occupancy(workspace_id, expected_submit_attempt_id)` →
   `WHERE workspace_id=? AND active_submit_attempt_id=?`,`rowcount != 1` → `SubmitOccupancyConflict`。
2. `delete_repository_occupancy` 至少匹配 `repository_id + workspace_id + submit_attempt_id`
   (可加 `business_baseline_node_id + baseline_head_version`),`rowcount != 1` → conflict。
   调用方手上有 attempt 全部 owner 信息。
3. 端口签名同步更新(`SubmitTransactionRepository`)+ 全部调用点。
4. 新增测试:projection drift 下 mismatched owner 不可删(行属于 attempt B,以 A 调用 →
   conflict + 行不变);happy path 不变。

### 同轮必做(S2 owned,blocker 之后)

#### S2-F8 [P2] T3 replay 不验证完整 T3 closure(来源:C)

design §10.2(:645-647):replay 仅在 `Submission、Attempt、Workspace、Operation` 已形成
matching T3 closure 时 ACK;「任何不完整前缀是 integrity/recovery finding,不以补写新 Submission 掩盖」。

代码:`finalize_transaction.py:43-55` replay 分支只取 attempt + submission 就送
`finalize_submit()`(纯函数,只验 attempt↔submission binding + repository facts),
不读 workspace occupancy / repository occupancy / Operation / await Step。

解决建议:replay 分支增加 `_assert_finalized_closure()`:
Attempt↔Submission binding(既有)、workspace `active_submission_id == submission_id`、
repository occupancy 不存在、await Step SUCCEEDED、Operation SUCCEEDED,任一不符 →
fail closed(复用/就近新增稳定错误码,参照 design :685 `FINALIZE_RECOVERY_REQUIRED` 家族,
**不得 ACK**)。新增 negative tests:每个 closure 组件单独破坏 → fail closed。

#### S2-F9 [P2] T1 registry 只验证三步之首(来源:B)

design §6.3 步骤 7(:453)「校验 Submit 三步 JobDefinition/decoder/handler/version registry snapshot ready」;
§8.1(:516-518)全 identity 一致,fail closed。

代码:`accept_transaction.py:70-75` 只 resolve
`JobStepKey(SUBMIT_JOB_KIND, SUBMIT_STEP_PREPARE)`。registry 缺后两步时 Accept 仍可持久化
Attempt/Operation → worker claim 缺定义,操作卡死并长期占用双 occupancy。

解决建议:`assert_submit_job_registered` 改为对三个 step
(`prepare_import`/`submit_import`/`await_import_result`)逐个 resolve,任一缺失即拒。
新增测试:只含 prepare 的 registry → Accept 被拒且零写入。

#### S2-F10 [P2] migration fail-closed integrity 审计缺负路径测试(来源:A/B)

plan S2 Deliver(:176-177):「发现 existing integrity 冲突 fail closed,不自动选择 winner」。
`_assert_workspace_migration_integrity`(`migrations.py`,`PRAGMA integrity_check` +
`foreign_key_check`)无任何测试构造损坏库验证拒绝。

解决建议:新增 migration 测试 — 手工损坏 v2 库(如删除被他表 FK 引用的行并提交),
断言 `bootstrap_workspace_schema` 拒绝升级、ledger 停在 v2、不留半迁移状态。

#### S2-F11 [P2] 测试矩阵缺口 + handoff 超额声明(来源:A/B)

handoff matrix 声称 vs 实际:
- **T1 rollback 断言不全**(`test_submit_transactions.py:402-431`):注入点
  `insert_repository_occupancy` 之前的前缀写只有 idempotency(:429)与 workspace occupancy(:430)
  两条断言;attempt 行、Operation/Step 行、workspace version 未变、无 repository occupancy、
  protection intents 无残留均无断言。
- **「并发 occupancy」是顺序测试**(`:532` 起):第一个 Accept 提交后第二个顺序失败。
  SQLite writer 串行化下结论等价,可接受,但 handoff 措辞必须如实改为「serialization 顺序」,
  不得称并发。
- **workspace 版本过期 T1 无事务级测试**:`save_workspace` `SubmitWorkspaceVersionConflict`
  路径 + 前缀回滚未覆盖(占 CAS 防线行的一半)。
- **PREPARED 态 stable abort 无测试**:全部 abort 测试从 EFFECT_PENDING + RUNNING await + live lease seed;
  worker 未拾取的用户取消路径(active step = prepare PENDING、无 lease、`require_live_lease=False`)未覆盖。

解决建议:补上述四组测试(rollback 改为对全部前缀 participant 断言);handoff matrix 按实际行为改写措辞。

#### S2-F12 [P3] SQLite JSON decoder 强制转换而非 fail closed(来源:C)

`sqlite_submission.py:507-511` `_decode_string_list`:`tuple(str(item) for item in document)` —
`[123, null, {...}]` 被规整成字符串;`:527-540`/`:556-569` ref decoder 用 `str(...)`/`int(...)` 强转
(`int(True)→1` 会被接受)。同文件 `_required_int`(`:603`)是 strict 的 — 同文件内 strict/lax 不一致。
这些 BLOB 无 SQL CHECK 保护,损坏 durable 状态应 fail closed 而非 normalize。

解决建议:decoder 对 exact keys + exact primitive types 严格校验(拒绝 missing/extra/wrong-type),
与 `_required_int` 风格一致;为损坏 shape 补参数化负例(同文件既有 `MALFORMED_JSON_SHAPES` 型参数表惯例)。

#### S2-F13 [P3·文档] S2 handoff 重写(来源:B/A)

按 §2 解决项重写 `p5-5b-s2-handoff.md`:candidate_head(整改后新 HEAD)、authority 块、
changed paths(含 S2-F3 越出境 path 与 plan 对齐说明)、container decision 与理由、
transaction matrix(含新增 negative 测试行)、lockfile 未随交付变更的声明、
「validate_abort_proof 事务外」措辞与 S2-F4 修复后实际一致。

## 3. 非 finding(记录,不整改)

- 「concurrent occupancy」顺序测试:SQLite 单写者串行化下等价,保留但改措辞(见 S2-F11)。
- `submit_attempt_records`/`submission_records` 无 `workspace_id` 二级索引:S4 read 路径
  规模决策项,recorded,不在 S2 修。
- 双 occupancy projection 的 indexed 查询模式:同上,S4 评估。

## 4. 整改 gate(最小并集)

```bash
cd /home/dev/gateway-data-management-system
git checkout -- vnext/backend/uv.lock          # S2-F2,确保后续 diff 为空

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
uv run pytest -q -m unit                       # 全包必须 0 failed(S2-F3 修复后)
uv run ruff check . && uv run mypy
```

新增测试组(缺一不得声称对应 finding 闭合):

1. port 回调(main_resolve/baseline/evidence)执行时 writer transaction 未打开(S2-F4)
2. lease takeover 后旧 identity 调 T3/abort 被拒;当前 holder 成功(S2-F5)
3. P4 已收口(await step 已 FAILED)后 business abort 幂等成功 + 二次 replay(S2-F6)
4. mismatched occupancy owner 不可被 finalize/abort 删除(S2-F7)
5. FINALIZED + closure 半破坏(逐组件)→ replay fail closed(S2-F8)
6. registry 缺 submit_import/await_import_result → Accept 拒绝且零写入(S2-F9)
7. 损坏 v2 库 → v3 迁移拒绝、ledger 停 v2(S2-F10)
8. T1 rollback 全 participant 断言 + workspace 版本过期回滚 + PREPARED abort(S2-F11)
9. 损坏 JSON shape → decoder 拒绝(S2-F12)

版本红线:整轮不得触碰 `uv.lock`、Dockerfile、P4 protocol、owning contracts;
`test_architecture.py` 与 S1 `application/submission/{contracts,errors}.py` 仅为 S2-F3
守护对齐的最小例外并须在整改卷记录(见 S2-F3.4)。

## 5. 复核

整改提交后,独立评审按 §4 gate + 9 组新测试 + 逐 finding 证据复核,
输出 S2 closure 签署或下一轮 findings。S3 entry 以本卷全部 finding 闭合 + S1 closure 签署为准。

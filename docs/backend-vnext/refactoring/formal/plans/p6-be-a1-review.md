# A1 BE-a 独立审核

日期：2026-11-07。审核角色 `/root/be_a1_review`，GPT-6.1-Sol / xhigh；实施角色 `/root/be_a1_impl`，协调者 `/root`。依据 [A1 工作单](p6-be-a1-work-order.md)、[BE-a 设计](p6-be-a-design.md)全部条款，特别是 §2–§6/§9，以及[联合设计独审 §6](p6-be-a-d-archive-design-review.md#6-修订候选-16472197b4-复审与最终设计结论)。设计 GO 不代表产品通过。

当前结论：**首轮代码审核需修复后复审，06 定向/静态及触发的容器证据尚待。** 本报告不办理联合任务或阶段 exit，不向 FE3 宣称依赖已交付。

## 1. 固定范围与方法

- 起点 `8fbdcb7d54097a45cbbb7511f130f0585249930a`；首个固定候选 **`adc2863e7f93c34c5e96b298228d38e227772892`**。区间内协调文档不作为产品实现；逐项读取产品、测试、session 示例及 owning Contract 的实际 diff。
- 只读 detached worktree：`/home/dev/gdds-reviews/p6-be-a1-adc2863e7f`，已链接主仓库 `legacy/`，创建及读取时 clean。未审核 dirty 实现，未修改产品或测试；只编辑本报告。
- 已读 AGENTS、testing-conventions、比例化保障政策、工作单、kickoff §1.1/§2/§4、BE-a 设计及设计复审；对照 Business Lifecycle、P5-5A Workspace HTTP、P5-5C Review、P5-5D Archive 正文与实际代码。
- 本轮只读源码及后续证据；未在开发主机运行产品测试、编译或 lint，未抢占测试节点、重跑全量 runner、访问 CT108、改基准资源或推送。

## 2. 首轮 findings

### F1：删除旧动作时破坏模块级 reason 反例，阻断测试收集

状态：**待修复/06 验证**。定位为候选 `vnext/backend/tests/test_review_domain.py` L410–430。

`REVIEW_CLOSURE_VIOLATION_CASES` 的 `return_whitespace_only` 反例中，`ReviewProjection` 缺少必填 `status`，`ReviewEvent` 缺少 `event_kind` / `to_status`。这些构造发生在模块导入阶段，会产生 `TypeError`，整个 domain owner 无法收集。此结论来自 dataclass 定义与调用点的静态核对，未在开发主机执行测试。

修复边界：以剩余合法动作（例如 REJECT）的完整 projection/event 构造保留“reason 不满足动作 Contract 时 closure 拒绝”的不变量，并按业务语义更名；不能简单删掉反例。实施者已确认接收；修复后由06 focused 日志证明可收集并通过。

### F2：finalize 前后指针及 active→pending 门禁尚缺代表性验证

状态：**待补齐/06 验证**。定位为候选 `tests/test_workspace_http.py` L146–194 与 `tests/test_archive_concurrency.py` L313–343。

Workspace owner 已覆盖新建、PENDING、APPROVE、REJECT、WITHDRAW、归档释放、Operation FAILED 仍保留 Attempt 和一致快照；但缺少同一个 Attempt 经真实 finalize 原子切换为 Submission 指针、版本递增的前后检查。新增 archive 竞争覆盖 APPROVE/REJECT/WITHDRAW，但没有实际 finalize 将 Start 的阻塞从 `ACTIVE_SUBMIT_ATTEMPT` 切到 `ARCHIVE_PENDING_REVIEW` 的语义屏障。该衔接是 BE-a §9.3 明确要求的本节边界，不能只分别展示两个静态状态。

修复边界：复用现有 seed/finalize owner，补一个有界前后案例；不要求内部 statement 时序矩阵。ABORTED 的 `CreateOrGetWorkspace` 投影及版本已在 `test_submit_transactions.py::test_stable_abort_releases_occupancy_without_submission` 新增断言，可作为唯一 owner，不再复制完整 abort 矩阵。Workspace HTTP L179 的名称含 `until_confirmed_abort`，但实际只运行到 Operation FAILED，应据最终归属订正名称或补足事实。

### N1：owning 正文仍有三处旧语义残留

状态：**待正文订正**。

- Business Lifecycle §9 仍把 `returned` 列为可读取 History 节点；目标状态已删除。
- P5-5C §13 仍把 submitter self-withdraw 列为未来 reopen 条件；本节已明确接受该权限模型。
- P5-5D §5.3 的 Review 先提交一行混称 APPROVE/REJECT/WITHDRAW 都改变 candidate set 并释放占用。APPROVE 改变候选且保持占用；REJECT/WITHDRAW 清除 PENDING 并释放，候选集未必变化。

这些是本轮 owning 正文同步，不改写历史 DC 或旧审核报告。已直接交实施者修正。

## 3. 已核边界与唯一 owner

以下为固定候选的代码观察，不替代待运行证据，也不表示 F1/F2 已关闭。

| 边界/风险 | 代码观察与验证归属 |
| --- | --- |
| 当前授权、本人绑定及披露（A） | GET/WITHDRAW 接受两个显式 permission；APPROVE/REJECT 仅 reviewer。permission 先于业务读取，最小 Submission/Workspace scope 与持久 created_by 校验先于 Review closure/key；mutation 内再验。`test_review_http.py` 为公开权限/披露 owner，新增共享参数表及撤权、非本人、scope、跨目标 key 测试。 |
| 成功 replay 与完整性（A/B） | 原 project-wide actor-independent key/fingerprint、原 event actor 保留；完整性校验先于普通冲突，已授权原成功 replay 早于 closed/state/baseline/occupancy。HTTP owner 验响应/授权，transaction owner 保留损坏记录、CAS、精确释放及 rollback，不复制权限矩阵。 |
| Workspace 指针（派生读模型，关联 A 类 occupancy） | route 在单个 UoW 取得 Workspace/version/occupancy；新建构造 null，已有投影当前 occupancy，无新增持久副本/历史回退。DTO 两键 required nullable；mapper 使用事务结果。F2 补齐 finalize 衔接；ABORTED 由原 submit owner 验证。 |
| pending 与 fresh APPROVE（A） | 有界 SQL helper 分别读 APPROVED/PENDING；missing projection/event 或相关 latest-event 分叉仍进入 closure 校验。pending 另校 scope/Workspace/FINALIZED Attempt；Start 在自身 BEGIN IMMEDIATE 重查，原 active gate 保留。APPROVE 比较 node 与 commit，REJECT/WITHDRAW 保留旧基线出口。archive query/transaction/concurrency 与 review HTTP 各自承担屏障。 |
| 旧路径/schema/History/OpenAPI | 活动源码无旧动作/状态/事件，剩余旧字面量仅拒绝/不存在断言；domain terminal 与基线 CHECK 同步，现有 schema 不符启动拒绝机制沿用，无 migration/双读。History 以枚举映射。两创建路由的成功码及 response model、required nullable 与旧枚举删除由 `test_http_openapi.py` 验证。 |
| 生产接线 | 独立 self-only session，无 reviewer 权限；Review Compose 上传→查指针/review→撤回→再次上传；Archive 双 actor Compose 检查两项 PENDING preview/直接 Start 拒绝后处置归档。仅 smoke，不重复 HTTP 矩阵。 |
| 比例化 | Review events、Head/Plan/Result、权限与 occupancy 属 A 类，保留事务/CAS/幂等及失败无部分写；projection/指针派生且没有新持久协议。未引入新身份、锁服务、计数状态机或证据平台。删除旧 return 竞争与历史 proof，不重做 parser/性能/golden。 |

跨包静态检索已覆盖实际 Review enum/序列化/History/SQL 和直接 Workspace service callers；repository_service 等包的回归仍须以06 `-m unit` 和五包静态证据收口，不能用静态检索代替运行。新时间/内容事实、来源/时间接受规则、有理由关闭与 tar 属 V1/V2/D；APPROVED 不可本人撤回。

## 4. 证据及容器决策

首轮候选尚无本报告核对完成的06成功证据。实施者正在06 clean detached worktree 离线同步/验证；错误日志须保留，新候选完成后复审实际 diff 与证据，不把 S2b 来源视为 A1 产品验证。

```text
Current reviewed HEAD: adc2863e7f93c34c5e96b298228d38e227772892
Container rebuild required: yes
Reason: 实际 Review/Archive Compose e2e 及 session 示例接线发生变化
Last verified image revision: a6876d560050285321fd9f62942d590a03f35d64（历史 S2b 来源，非 A1）
Last verified RS source-tree: sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2
Last verified backend image: sha256:34130ae839ba946d07bee991f2a7e44b01f1f1f33b9416aba6b13c8c14644e3e
Last verified worker image: sha256:692cc893fdbbc4e5c5b336679334b3561c6e0ed1a0b36cf20e42e3d661334298
Container gate for current HEAD: deferred（待本节收敛候选06局部门禁）
Carried from: none
Deferred gates/nodeids:
  06: tests/test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey
  06: tests/test_review_compose_e2e.py::test_compose_self_only_submit_withdraw_and_upload_again
  06: tests/test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect
Required execution point: A1 本节代码收敛后完成上述受影响容器门禁
Joint final gates: 04 受影响包权威 runner/必要容器及合法闭包判定；05 一次 fresh t1，留联合最终候选
```

后续每轮核节点、clean 已提交 worktree、起止 HEAD/UTC、exit、日志路径/SHA、离线缓存及镜像 revision/source-tree。最终 A1 结论只可覆盖本节代码与定向证据；联合最终验收、FE3 同制品互通与阶段退出分别办理。

# A1 BE-a 独立审核

日期：2026-11-07。审核角色 `/root/be_a1_review`，GPT-6.1-Sol / xhigh；实施角色 `/root/be_a1_impl`，协调者 `/root`。依据 [A1 工作单](p6-be-a1-work-order.md)、[BE-a 设计](p6-be-a-design.md)全部条款，特别是 §2–§6/§9，以及[联合设计独审 §6](p6-be-a-d-archive-design-review.md#6-修订候选-16472197b4-复审与最终设计结论)。设计 GO 不代表产品通过。

最终结论：**A1 本节代码与06定向/静态及触发的小型容器门禁 GO，无剩余阻塞项。** F1/F2/N1 已由同一审核角色复审关闭（§5）。最终产品/容器候选为 `d8bee1a5914d00f473dc41fb76d9c57ca4b01f48`，实施交接已核至 `fb53d4f60f73615a6e893f725eae801054351728`。04/05联合最终验收仍待；本报告不办理联合任务或阶段 exit，不把 A1 通过扩称为 V1/V2/D 或 FE3 全部依赖已交付。

## 1. 固定范围与方法

- 起点 `8fbdcb7d54097a45cbbb7511f130f0585249930a`；首个固定候选 **`adc2863e7f93c34c5e96b298228d38e227772892`**。区间内协调文档不作为产品实现；逐项读取产品、测试、session 示例及 owning Contract 的实际 diff。
- 只读 detached worktree：`/home/dev/gdds-reviews/p6-be-a1-adc2863e7f`，已链接主仓库 `legacy/`，创建及读取时 clean。未审核 dirty 实现，未修改产品或测试；只编辑本报告。
- 已读 AGENTS、testing-conventions、比例化保障政策、工作单、kickoff §1.1/§2/§4、BE-a 设计及设计复审；对照 Business Lifecycle、P5-5A Workspace HTTP、P5-5C Review、P5-5D Archive 正文与实际代码。
- 本轮只读源码及后续证据；未在开发主机运行产品测试、编译或 lint，未抢占测试节点、重跑全量 runner、访问 CT108、改基准资源或推送。

## 2. 首轮 findings

### F1：删除旧动作时破坏模块级 reason 反例，阻断测试收集

状态：**已关闭，修复与06证据见§5**。首轮定位为候选 `vnext/backend/tests/test_review_domain.py` L410–430。

`REVIEW_CLOSURE_VIOLATION_CASES` 的 `return_whitespace_only` 反例中，`ReviewProjection` 缺少必填 `status`，`ReviewEvent` 缺少 `event_kind` / `to_status`。这些构造发生在模块导入阶段，会产生 `TypeError`，整个 domain owner 无法收集。此结论来自 dataclass 定义与调用点的静态核对，未在开发主机执行测试。

修复边界：以剩余合法动作（例如 REJECT）的完整 projection/event 构造保留“reason 不满足动作 Contract 时 closure 拒绝”的不变量，并按业务语义更名；不能简单删掉反例。实施者已确认接收；修复后由06 focused 日志证明可收集并通过。

### F2：finalize 前后指针及 active→pending 门禁尚缺代表性验证

状态：**已关闭，修复与06证据见§5**。首轮定位为候选 `tests/test_workspace_http.py` L146–194 与 `tests/test_archive_concurrency.py` L313–343。

Workspace owner 已覆盖新建、PENDING、APPROVE、REJECT、WITHDRAW、归档释放、Operation FAILED 仍保留 Attempt 和一致快照；但缺少同一个 Attempt 经真实 finalize 原子切换为 Submission 指针、版本递增的前后检查。新增 archive 竞争覆盖 APPROVE/REJECT/WITHDRAW，但没有实际 finalize 将 Start 的阻塞从 `ACTIVE_SUBMIT_ATTEMPT` 切到 `ARCHIVE_PENDING_REVIEW` 的语义屏障。该衔接是 BE-a §9.3 明确要求的本节边界，不能只分别展示两个静态状态。

修复边界：复用现有 seed/finalize owner，补一个有界前后案例；不要求内部 statement 时序矩阵。ABORTED 的 `CreateOrGetWorkspace` 投影及版本已在 `test_submit_transactions.py::test_stable_abort_releases_occupancy_without_submission` 新增断言，可作为唯一 owner，不再复制完整 abort 矩阵。Workspace HTTP L179 的名称含 `until_confirmed_abort`，但实际只运行到 Operation FAILED，应据最终归属订正名称或补足事实。

### N1：owning 正文仍有三处旧语义残留

状态：**已关闭，正文复审见§5**。

- Business Lifecycle §9 仍把 `returned` 列为可读取 History 节点；目标状态已删除。
- P5-5C §13 仍把 submitter self-withdraw 列为未来 reopen 条件；本节已明确接受该权限模型。
- P5-5D §5.3 的 Review 先提交一行混称 APPROVE/REJECT/WITHDRAW 都改变 candidate set 并释放占用。APPROVE 改变候选且保持占用；REJECT/WITHDRAW 清除 PENDING 并释放，候选集未必变化。

这些是本轮 owning 正文同步，不改写历史 DC 或旧审核报告。已直接交实施者修正。

## 3. 已核边界与唯一 owner

以下为首轮固定候选的代码观察；最终修复与证据见§5，不以首轮观察替代运行结果。

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

## 4. 首轮证据及容器决策（历史记录）

以下保留首轮候选的待验证状态；当前有效决策以§5–§6为准。首轮当时尚无本报告核对完成的06成功证据，不能把 S2b 来源视为 A1 产品验证。

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

## 5. 同角色修复与证据终审

2026-11-07，新建并读取两处 clean detached worktree，均链接主仓库 legacy：`/home/dev/gdds-reviews/p6-be-a1-2d9a39f191`、`/home/dev/gdds-reviews/p6-be-a1-d8bee1a591`。复审 `2d9a39f19107752a074f3d972fb6c7c56d066959` 的实际八文件修复，以及 `d8bee1a5914d00f473dc41fb76d9c57ca4b01f48` 的单文件 Compose provenance 接线。没有读取 dirty 实现或自行修改产品。

| 首轮项 | 修复及关闭依据 |
| --- | --- |
| F1 | reason 反例改为完整 `REJECTED` projection/event，名称为 `reject_whitespace_only`；没有删除 reason 不变量。2d9 focused 正式573+1分批和 mypy 均通过；d8 backend mypy再次通过。 |
| F2 | Workspace owner 新增同一个实际 Attempt 经 finalize 后双指针原子切换及 version+1；archive concurrency owner 新增同一 Start 在 finalize 前拒绝 `ACTIVE_SUBMIT_ATTEMPT`、之后拒绝 `ARCHIVE_PENDING_REVIEW`，Head/Plan不前移；保留原submit owner的ABORTED投影，原名称改为实际执行的 Operation failure 场景。上述文件均纳入573+1正式分批，没有增加内部statement调度矩阵。 |
| N1 | Business Lifecycle删除returned验收残留；P5-5C reopen改为扩展本人权限/状态时重审；P5-5D拆开APPROVE保持占用与REJECT/WITHDRAW清PENDING释放的竞争语义。旧迁移/backfill正文同步为现行单一基线schema，无兼容实现。 |

追加的公开 HTTP 回归验证 self-only 在归档后仍能 GET 本人 APPROVED facts，但不能借原 APPROVE key回放越权动作。d8两条Review Compose均补充“运行backend/worker等于本次build”的断言和独立provenance；三条小门禁全部通过。

审核者先以 SSH BatchMode 确认06连接，仅只读核原始日志、脚本、身份及现场状态，没有运行产品测试/编译/lint或占用节点。06执行WT为 `/home/dev/gdds-test-tmp/wt/p6-be-a1`；独立读取时clean、legacy链接正确。执行脚本在每项前检查clean与本人owner，设置 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、指定TMPDIR和Cargo PATH，移除proxy及toolchain覆盖；fresh五venv同步后Rust扩展输入与Git tree一致。依赖/锁/Rust未改变，复用已预填缓存且无新增跨节点镜像传输；backend d054完整输入、config digest与readiness所列CT201来源一致。没有用S2b功能结果代替本轮证据。

证据根为06 `/home/dev/gdds-test-tmp/artifacts/p6-be-a1`，CT201只读副本 `/home/dev/gdds-reviews/artifacts/p6-be-a1`。独立核过原日志hostname、起止HEAD/UTC、argv、exit和SHA，副本 `SHA256SUMS` 全部校验OK；其SHA为 `0011e81b42951b0744f2311c9222052329039857989c48d49d80384fbbe4a4be`。下表日期均为2026-11-07，全部成功项exit0，完整文件与静态检查SHA见[已核实施交接](p6-be-a1-handoff.md)。

| 范围/文件 | 来源、UTC及结果 | SHA256 |
| --- | --- | --- |
| `backend-parallel-2d9a39f1.log` | 2d9，08:02:28–08:03:17，573 passed；18个定向owner文件，4 workers | `5f131053eb1eb8cfa43c8f1756371a99fd98411c13cb8653537efa2c84c1e99b` |
| `backend-serial-2d9a39f1.log` | 2d9，08:03:17–08:03:18，1 passed/56 deselected；`test_archive_http.py` serial，0 workers | `7947e985d4f44dc6a31469986316b59ed7691ae00238da95f2b3d8c669d57ad9` |
| `repository-service-unit-2d9a39f1.log` | 2d9，08:00:09–08:02:28，1555 passed/1 skipped/396 deselected，0 workers；既有cgroup delegated-container smoke跳过 | `b32ee1fb326de64317736b276b1840269d3dc0c7771d7117b58dc2ffd325beac` |
| 五包ruff/mypy | 2d9，07:58:39–08:00:09，10项通过；四包源码在d8未变 | 全部十份原日志SHA已独立核对 |
| `backend-ruff-d8bee1a591.log` | d8，08:04:02，增量后重核通过 | `85c205234dde66b6da00a0c97a0a6230706b154e4da96438bca6fbd2ac5eba9a` |
| `backend-mypy-d8bee1a591.log` | d8，08:04:02–08:04:03，500 source files通过 | `856c1a63d9ec532fdc6c168a47466a83f62bf7bbdf1880018c89edb101e9b0b0` |
| `compose-review-approve-d8bee1a591.log` | d8，08:05:24–08:05:55，reviewer smoke 1 passed | `87b63a15ea96e766381cbebc5f76fe486e66ebd6b6d6f2af847f62adb41f0b01` |
| `compose-review-self-d8bee1a591.log` | d8，08:05:55–08:06:28，独立self-only撤回重传 smoke 1 passed | `e47c995c5050a8010906bb10b3c4943c4b661b63854c0141790d0113a3c934ab` |
| `compose-archive-dual-d8bee1a591.log` | d8，08:06:28–08:07:25，双人PENDING→处置→归档/重启 1 passed | `5ffcfe8f529ff03d69c4d901503cd868c409df8d6ac8e7d58c2e9a3cfc316642` |
| `cleanup-d8bee1a591.log` | d8，08:09:12，三栈down、现场无容器/Dolt/8000，比较本人owner后释放；WT保留clean d8 | `193182e98fc50acf52369e9d930402e29e0bfa329acfe39c569aac1dff6c66c1` |

失败链没有被计作成功来源：adc mypy日志SHA `f82f36812e4b2d5210f1137ca70ad29dbc1cc5920f678871d42d3d4fb6861727`、focused日志SHA `eae2f567faecc1f1de24aefa3caefacdc28aac558837934ff5bd04654b9bfe04` 证实漏必填字段与测试类型错误，491项通过但收集失败。2d9首次574项混含一个serial，仅作诊断；正式证据是上述573+1分批。这些都是focused调试，未称权威runner或按包carried。

OpenAPI导出的一次操作错误已按DC68核对：原命令为受控wrapper执行项目外 `.py`，原日志SHA `79486c208c72e713029c33450d88764b6c10ade461b9ca65c23769564bab25aa` 明示 `run may not execute scripts outside project directory`；`uv-consume.sh` 在路径检查失败时直接return2，早于uv和产品调用。metadata SHA `47b281896b08c3869b86d8356170dd5563f9fa3dd17bb7a2a799437036640229` 保留exit2/原因/一次修正。随后使用wrapper明确支持的 `python -c` 直接调用公开测试harness生成OpenAPI，未读取执行被拒外置脚本、未修改wrapper；08:05:23–08:05:24Z成功，日志SHA `75ea3058a38af8cc6653567cb1ced19a1570a69ab22a33a47ddd7080bb27b84e`。这属于产品执行前、无副作用的自身命令错误，不是自动审批拒绝或失败产品门禁。导出制品 `openapi-d8bee1a591.json` SHA为 **`e495013955516a283e8f2ef32901c2eda6e2717e6de2dcb41c3f4c0bdfa9725f`**。

## 6. 最终镜像绑定与剩余联合范围

三份运行provenance已独立读核：reviewer SHA `48c7569f6eaf750cb5c65fd5f65779af6998f6a64ba67318589e72d0aff08dda`，self-only SHA `c8d3865102e7efa1bb66defcab6e04e8480c7c96105334a4c8a7ea5096e2dc10`，archive SHA `61b66b7b9a537b5745d7e0b639145d896a8d956a37ee4e477e71ad6073623f5d`。RS在d8实际离线构建新tag，OCI revision为d8；其build-input仍为a687、source-tree仍为13cb，是RS输入未变化的身份，不是沿用旧容器结果。backend/worker无source label，按当前clean候选Compose本机构建和运行镜像一致性断言绑定。

`image-identities-d8bee1a591.json` SHA **`2f97f0f1e3ae48f9aad6297bc73d3aa9d7e53d2a7f045a4d1c363f3a47098d6c`** 包含三轮全部运行镜像与三种dependency-base共10项。已读生成脚本与exit0日志：逐项docker-save取manifest指定config原字节计算config digest，并比较全部有序RootFS DiffID与inspect一致；没有把本机manifest ID当config digest。最后双actor运行对应backend config为 `sha256:dad5cd695ea21cd323a7ccdb00950e1b979dfcf1b6cf6b4f0214e0751cf7c0bc`（13 DiffID）、worker `sha256:8afcfcfc32d05dd80a10d02f7062f8610965cfd8c45dfad965d5acdbb6fad98e`（13）、RS `sha256:28c01231bf201704eff2bdc063d3616b4c6c92f9ffc887f3cb8c0e467408f640`（28）；完整列表以该JSON为准。

```text
Current reviewed product HEAD: d8bee1a5914d00f473dc41fb76d9c57ca4b01f48
Reviewed handoff HEAD: fb53d4f60f73615a6e893f725eae801054351728
Container rebuild required: yes（本节已完成）
Reason: 实际Review/Archive Compose及session接线变动
Last verified image revision: d8bee1a5914d00f473dc41fb76d9c57ca4b01f48（06本机实际build/运行）
Last verified RS build-input: a6876d560050285321fd9f62942d590a03f35d64
Last verified RS source-tree: sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2
Last verified backend local image ID: sha256:0fd31de9ad7ed308b183bbfa1bc13987becfb4d113f42783ef299b6f2debeaca
Last verified worker local image ID: sha256:2c16bd4d32cdd75e1edbf3d6521c41e19f1f68c062c010b56c09131b04d180eb
Container gate for current product HEAD: passed（仅06本节三条受影响小Compose）
Carried from: none
Deferred A1 local gates: none
Joint final deferred:
  04: vnext/scripts/run-tests.sh，最终影响包及闭包判定；容器包含两条Review/一条Archive上述精确nodeid，最终范围按V1/V2/D实际增量收敛
  05: vnext/backend/benchmarks/real_dump_journey.py，补齐联合工具后一次fresh t1
Required execution point: 联合最终产品候选；本节不办理exit/发布
```

`d8..fb53` 无 `vnext/` 改动，候选vnext tree为 `1262797adea3d5e1d0b10188f069146d90dc40ff`；这里仅核文档交接与已测产品的对应，不声称完成权威包闭包carried。真实工具当前仅MODIFIED_ONLY、现有归档身份异常消费；V2/D必须在新产品候选先补FULL入口、新来源/时间异常逐项消费与Preview/History完整tar核验，再跑05联合fresh t1，原冻结V_ref工具不改。时间/内容事实、来源图、有理由关闭、tar、前端同制品互通及04/05最终证据均不属于本节已完成声明。

**A1本节GO。** 同一审核角色的修复闭环结束，可按已授权顺序启动下一小节；本角色停止本节工作，未创建额外角色、推送、改tag或办理全任务exit。

# BE-a 设计补充：工作区占用、本人撤回与归档审核收口

状态：2026-11-07 修订草案。DC75 原范围曾通过 kickoff 审核（`fcbfb4c1a0`）；Owner 本轮确认加入待审核阻塞归档及过期基线的新 APPROVE 拒绝（DC89，§9）。**旧审核不覆盖新增范围，修订设计待独审，未启动产品实施。** S2a/S2b 已退出；本文不是当前已部署接口或实施结果。

原引用基线：main `d0a8143d804e158e16b0712cc5f2aa007066f9cb`；原前端问题来源为 `55e6c0083c` 的 [FE2 kickoff Q16](../../../../frontend-vnext/fe2-kickoff.md) 与 [前端 kickoff §3.3](../../../../frontend-vnext/frontend-kickoff.md)。本轮按 main `a8de5e5346d2421e1237d52e8ff3f5025dc84aea` 核对占用、审核及归档实际源码；§9 为新目标，旧条款与其冲突时按§9收口。本轮仅设计文档，不改产品、前端或既有审核报告。

## 1. 目标与范围

BE-a 在原有删除 RETURN_FOR_REVISION/RETURNED_FOR_REVISION、修正两创建接口 OpenAPI 成功码之外，增加：

- WorkspaceResponse 的当前占用指针，解决上传顶栏定位提交、刷新后找回 attempt；
- `withdraw_own_submission` 权限，允许提交人撤回自己的待审核提交，并读取本人提交的 review facts；保留 `review_submission` 的现有跨 actor 审核能力。
- 当前基线下有未审核提交时阻塞归档，新 APPROVE 不得基于过期基线；具体事务、回放与前端行为见§9。时间／来源链能力单列于[归档核验补充](p6-archive-business-validation-design.md)，不冒称本节已有实现。

新增权限不是 upload_submit_workspace 的隐含权限，也不由“是提交人”自动授予。session claims 显式发放；示例配置与测试身份区分提交人、审核人和无权用户，不把所有用户都赋 review_submission 来通过测试。不新增角色系统、权限存储或认证机制。

本人身份只用已持久化的 `Submission.created_by` 与当前认证 `actor_id` 比较，不信任请求中的 actor，也不以 ReviewProjection.updated_by、最近事件 actor 或当前占用反推提交人。新增权限与指针本身不改 DB schema；原 BE-a 删除旧状态仍直接修改基线约束。

## 2. WorkspaceResponse 查询形态

```text
active_submit_attempt_id: string | null
active_submission_id: string | null
```

两个字段为响应必需键，空值显式输出 null；至多一个非空。它们投影自 workspace_submit_occupancy_records，表示当前占用，不是“最近一次提交”或“可撤回”的结论。无占用时均为 null，不回退查找历史 Submission。

现有 `POST /v1/workspaces` 的新建 201、已存在 200 两条真实路径都返回此形态。当前 mapper 仅拿 Workspace，需要应用查询结果同时携带 occupancy；Workspace、occupancy 与 optimistic_version 必须在同一 control DB 事务快照内读取，或从同一写事务提交的结果构造。禁止 route 分别查询再拼接、新增持久副本字段或通过扫描 History 猜当前提交。沿用 workspace_read 与 exact owner/device/project scope，不因暴露指针扩大读取他人工作区的权限。

| 生命周期 | attempt 指针 | submission 指针 | Workspace optimistic_version |
| --- | --- | --- | --- |
| 新建/无占用 | null | null | 原有规则 |
| Submit 受理 | attempt ID | null | +1 |
| 执行、等待、人工恢复或结果未知 | 保留 attempt ID | null | 不能按 Operation terminal status 推断释放 |
| 经既有规则确认 ABORTED 并释放 | null | null | +1 |
| finalize、PENDING | null | submission ID | +1，原子切换 |
| APPROVE | null | 保留 submission ID | 此动作不递增工作区版本 |
| WITHDRAW/REJECT | null | null | +1，清空当前上传与 Preview 指针 |
| StartArchive 事务释放该 submission 占用 | null | null | +1，发生在归档开始，不等待归档完成 |

RETURN_FOR_REVISION 现状也释放，但由原 BE-a 删除，不进入目标状态机。withdraw/reject 后工作区保持可复用，重新上传时 generation 按现行规则增加，重新 Preview/Submit 仍检查权限、基线和占用等条件；不是撤回后立即重用旧 Preview。历史 Submission 与 Repository commit 保留，撤回不回滚 main。

工作区版本只代表 Workspace/占用变化，不代表审核状态变化。前端用 active_submission_id 调现有 GET review 取得 `status`、`review_version`，提交撤回仍携带 `expected_review_version`。版本冲突刷新后处理，不能拿工作区版本替代审核版本。active_submit_attempt_id 经已有 attempt 查询取得 operation_id；保留前端 URL 的 operation_id 方案，不新增取消接口。

## 3. 授权与读取（对 P5-5C §4.3、§5 的目标修订）

| 身份权限 | GET review | POST WITHDRAW | POST APPROVE/REJECT |
| --- | --- | --- | --- |
| review_submission | 现有 scope 内全部提交 | 现有 scope 内，按状态/版本等约束 | 保持原权限，APPROVE另加§9当前基线门禁 |
| 仅 withdraw_own_submission | scope 内本人提交，所有审核状态 | 仅本人 PENDING、未关闭且精确占用匹配 | 403 |
| 二者都有 | 按 reviewer 能力 | 按 reviewer 能力，无额外本人限制 | 同上 |
| 二者均无（即使有上传权限） | 403 | 403 | 403 |

GET 返回既有 ReviewFactsResponse（包含状态、版本、事件及身份确认），只对本人提交开放；终态/归档后的本人 review facts 仍可读，不依赖当前占用存在。该权限不授予项目 History、他人 Workspace/Preview、bundle 或 artifact 读取权。

授权顺序：

1. 当前 session 认证；失败 401。
2. 对请求动作做粗粒度 permission 检查，发生在任何业务对象读取前。GET/WITHDRAW 接受两个 permission 之一；APPROVE/REJECT 只接受 review_submission。缺失返回 403。
3. 解析 scope，读取请求目标的最小 Submission/Workspace 绑定，校验原 project/device/repository 关系；仅本人权限再检查 Submission.created_by。目标不存在、跨 scope 或非本人统一 404，不返回他人状态、事件或 reason；映射与基础设施错误沿用原分类。
4. 目标授权通过后加载 review facts/closure。在同一 mutation 事务内重验当前目标和授权绑定，再进入幂等、版本、状态、占用检查与事件提交。closure 损坏沿用原 503，不能隐藏为业务冲突。

新权限只扩展 caller 资格，不扩展合法状态转换：新 WITHDRAW 仍仅 PENDING→WITHDRAWN；APPROVED 不可撤回，归档关闭不可变更。不能通过前端 actor 判断代替服务器授权，也不能为了支持新权限授予完整 review_submission。

## 4. 幂等与并发（对 P5-5C §3、§4.3 的目标修订）

保留 actor-independent 的 `(business_project_id, idempotency_key)` 命名空间与现有 request fingerprint，不新增 actor 字段、不重写历史事件。

- 每次请求及 replay 都重新做当前 session、动作 permission、scope 和本人资格检查；旧授权不是永久票据。
- 仅本人权限不得通过碰撞幂等键获得他人提交结果，或回放 APPROVE/REJECT。对请求目标未获授权时先 404；对已授权目标使用同项目另一提交的 key，按既有不同 fingerprint 返回 IDEMPOTENCY_CONFLICT，不返回那条记录/事件内容。
- 保留现有幂等记录 project、Submission、event sequence、fingerprint 的完整性检查；不能为方便处理冲突而把损坏记录直接当普通 conflict。
- 本人的 WITHDRAW same-key/same-fingerprint 在当前权限仍有效时可返回原结果，即使成功后占用已释放；不在 replay 前重新要求 PENDING 或占用存在。新 key 仍按最新状态拒绝重复撤回。
- reviewer 与本人针对同一提交的相同 WITHDRAW 请求可按原命名空间回放同一事件；响应保留首次事件 actor，不伪装为当前 caller。
- 无 existing 时继续使用 expected_review_version、状态转换、归档关闭、精确 workspace occupancy/generation/upload/preview 绑定、append event/CAS projection 与同事务释放。不增加工作区版本请求参数。
- 撤回与 APPROVE/REJECT/归档竞争保持现有事务屏障；成功结果只能形成一条有效转换，不产生重复释放、事件或后续误写。

## 5. 文档与代码落点

本页集中记录待实施的详细修订；当前 P5 设计/Contract 不应在产品尚未切换时被描述成已实现新权限。实施提交同步改 owning 文档正文及其相关权限说明：

| 落点 | 内容 |
| --- | --- |
| P5-5C review design §3、§4.3、§5、HTTP 权限/错误说明与测试矩阵 | 两权限、本人读取、scope/404、幂等回放；删除旧 return 状态/动作；目标授权逻辑按本文 |
| Business Lifecycle and State §4–§5、Workspace HTTP、P5-5D | 目标 review 状态、指针投影和生命周期；按§9增加归档受理门禁，释放时点与现有StartArchive事务一致，不改变唯一选中、sibling处置及Head原子提交 |
| application/submission/review.py、review_transaction.py 及公共端口/导出 | 共享授权规则、最小对象绑定读取与完整 facts 的先后顺序；命令和查询都覆盖 |
| application/workspace、control DB 查询/UoW、HTTP mapper/schema/routes | 同快照 WorkspaceResponse；新建与已存在路径均覆盖；不只改 DTO |
| session 示例配置、HTTP/Compose 测试身份 | 明确独立本人权限与 reviewer 权限，不修改外部实际账号/凭据 |
| 原 BE-a 范围 | 旧状态/动作/事件、schema 基线、History literal、两个创建接口 OpenAPI 成功码继续完成 |

HTTP 请求体不新增 caller identity；生成 OpenAPI 中两个指针为 required nullable。现有审核请求/响应形状保持，只更新授权与响应说明。前端快照与接口类型由前端 FE3 更新，后端不改 frontend/。

## 6. 程序验收及重跑范围

| 语义屏障 | 必需场景 | 权威测试 owner |
| --- | --- | --- |
| 权限和披露 | reviewer、self-only、双权限、均无；本人/他人/跨 scope/不存在；GET 与三种目标动作；未授权不返回事实 | HTTP 授权测试，参数表复用 |
| 查询与命令共享规则 | self-only GET 本人的 PENDING/APPROVED/终态；非本人 404；仅上传权限 403；POST 不可越权 | 上述 HTTP owner，应用层只验证必要接线 |
| replay 权限、披露与公开响应 | 当前 session 撤权后拒绝、self-only 动作限制/非本人 404、跨 actor 合法 WITHDRAW 回放、另一提交的 key 冲突不泄露、释放后同键返回原响应、新键终态拒绝 | `tests/test_review_http.py`（公开 HTTP，沿用 P5-5C §12 的唯一 owner） |
| replay 完整性 | 幂等记录的 project/Submission/event sequence/fingerprint 闭包；损坏记录保持完整性错误，不能伪装成普通 conflict | review transaction/replay 测试；不重复 HTTP 权限矩阵 |
| 事务与竞争 | WITHDRAW/APPROVE/REJECT 与归档现有合法竞争；事件/CAS/指针释放原子性，失败无部分写入 | 既有 review/archive transaction 测试，补新权限入口 |
| 指针投影 | create/get 两响应；受理、等待恢复、ABORTED、finalize、通过、撤回/拒绝、归档释放；显式 null、互斥与对应版本；并发读取不能混合快照 | Workspace 查询投影测试；生命周期 owner 提供状态构造 |
| 公开生产路径 | self-only 提交人上传→Preview→Submit→查 Workspace→查 review→撤回→刷新指针→再次上传；reviewer 原旅程回归 | 真实 wiring HTTP/Compose |
| OpenAPI | required nullable 字段；两创建接口成功码；旧动作/状态移除 | OpenAPI 测试 |

上述归属按 kickoff 审核 `fcbfb4c1a0` §3 的非阻塞建议订正：HTTP owner 负责 replay 权限与披露；事务 owner 负责完整性、CAS、原子释放及失败无部分写入。复用现有参数表，不将公开边界降为应用直调测试，也不把整个矩阵重复跑 Compose。

测试以业务行为命名，不枚举内部执行步骤；同构输入使用参数表。不能仅测试 reviewer 同时有全部权限的身份来宣称本人撤回通过。

06/05：按实际改动focused（含RS过时状态引用的定向回归）、五包ruff/mypy、门禁前预检；代码通过后04运行受影响包权威runner与当前候选容器门禁，未受影响包仅按合格闭包规则沿用。真实数据建议05 fresh t1一次；新增权限和归档竞争由合成HTTP/Compose承担，不为每轮修改另跑t4/2×t4。与BE-d/业务核验共用最终候选时合并一次取证。最终范围随修订kickoff审核确认，退出前Owner按DC33确认。

P6 基准仍测固定 p6-s1c-exit，不因本项重新测量；不重做 S2a parser 差分或计算类 golden。BE-a 本身删除 DB 状态属于既定 schema 变化，仍用新基线 DB，不能把旧旅程 DB 直接续到新候选。任何实际影响计时路径或业务 digest 的额外改动先停下交设计/owner。

## 7. 确认与交接

- owner 2026-11-04：同意上述方向，要求补充订正并给出各方提示词。
- kickoff 详细设计/验收审核：[报告](p6-be-a-kickoff-review.md)（提交 `fcbfb4c1a0`，审核候选 `f20f08bea919`），通过、无阻塞项；§3 非阻塞测试归属建议已在本文 §6 采纳。本记录仅引用审核结论，不评价实施结果。
- S2a前置已满足：`p6-s2a-exit`→`53b676a6298d408ccda3a85ee73c7ea223a2311a`；S2b亦已退出。Owner本轮授权修订设计，完整修订稿独审与实施kickoff仍待完成，不把S2b角色或开工授权自动延续到这里。
- 顺序：联合设计收口→修订独审→明确小节/验收/角色后实施。FE3随后按真实后端OpenAPI接回入口；BE-d规则见其新设计。当前不因等待旧基准退出而阻塞本设计。

## 8. 本次文档检查

本节下方为2026-11-04原设计的历史静态检查，不覆盖2026-11-07新增产品行为。当前修订仅文档；新的审核与产品证据另记，不能沿用原报告宣称新增门禁通过。

仅修改设计/计划文档，不触发镜像重建，不宣称新权限已通过产品测试。提交前在 05 clean checkout `55e6c0083c6e3a05dc97dad86974afd645d89a8e`（与引用基线相同 vnext tree：`2791d3ff3dd62ff454d7e9cac43885d39da8bf96`）运行五包 ruff/mypy，使用已有缓存、受控 uv wrapper、UV_OFFLINE=1、CARGO_NET_OFFLINE=true、no-sync；2026-11-04T02:46:25Z–02:46:26Z，exit 0。日志为 05 `/home/dev/gdds-test-tmp/p6-be-a-design-static-20261104T024625Z.log`，SHA256 `9278890e81be494ddbc2dfad448151101dcb00d34ce14ca81e34c2e6d50ba9a3`。节点占用已释放；不是阶段取证或 carried 判定。

2026-11-04 审核后订正仅改变测试归属说明与审核记录；`vnext/` tree 仍为上述值，沿用本节已通过的同源码静态检查，不重复运行产品检查，不作为新权限的验收证据。

## 9. 待审核阻塞归档与基线前移（2026-11-07，DC89）

### 9.1 业务规则

同一个固定 device/project/Repository scope、基于当前 baseline node/commit 的未关闭 `PENDING` Submission 任一存在，禁止新 StartArchive。范围覆盖同 scope 的所有 actor；新建Workspace、仅上传或仅Preview的草稿不算正式待审核内容。active SubmitAttempt原门禁继续生效，包括结果未知或需人工恢复的未终局Attempt；不得因为没有PENDING就绕过它。

归档预览列出有权限读取的待审核提交ID/计数，并显示 `ARCHIVE_PENDING_REVIEW`；Start仍须在自身写事务重查。无“确认后忽略”的入口。待审核项先APPROVE（进入候选）或REJECT/WITHDRAW（释放占用）后再归档；不能自动退回、自动通过或自动关闭其他人的PENDING。

所有已通过的当前候选仍参与原选择与排除规则：选一个成为新baseline，其余经逐项排除确认后CLOSED_NOT_ARCHIVED，原子释放各Workspace；不合并内容。上传者的self-only权限不因此获得归档列表或他人review权限。

### 9.2 新APPROVE与回放顺序

新增APPROVE在同一fresh control DB写事务内，校验Submission冻结baseline node/commit与当前Head匹配；不匹配以明确409基线冲突拒绝，无事件、projection或占用修改。REJECT/WITHDRAW不要求baseline仍当前，保留旧PENDING的正常退出途径。

原成功幂等请求在每次重新验证当前鉴权、scope及本人资格后按原记录回放，早于新动作的状态／当前baseline／占用检查。不能因随后发生归档而拒绝旧成功APPROVE或WITHDRAW的合法回放，也不能利用回放再次执行状态变更。Review expected version继续是review version，不改为Workspace version。

### 9.3 并发与一致性

| 竞争 | 必须成立的结果 |
| --- | --- |
| 有PENDING时先Start | 硬阻塞，Head/Plan/Result/Workspace均不变 |
| APPROVE先提交，再用旧预览Start | candidate-set变化，旧请求拒绝；刷新完整集合和确认后可开始 |
| Start已成功，再发旧baseline新APPROVE | 明确拒绝；若该项已归档关闭，可按既有ARCHIVE_CLOSED先拒绝，不伪造新审核结果 |
| Submit受理先完成 | active Attempt阻塞Start；finalize将其原子切为Submission/PENDING占用，不能产生可见检查空隙 |
| Start先完成，再受理旧Preview Submit | 既有baseline绑定检查拒绝；旧Preview不能把新Head回滚 |
| 最后一项REJECT/WITHDRAW与Start竞争 | 前者先完成则可重新计算候选；后者先执行则见PENDING并拒绝，不能预先释放未成功审核的占用 |

复用同一个control DB写事务和既有CAS，不建立独立锁服务／持久pending计数。读模型从一致快照派生，有界查询；不能只查调用人的Workspace或在路由做事务外检查。

### 9.4 文档、前端与验证

目标修订Business Lifecycle、P5-5C/5D审核和归档受理条款、HTTP错误/OpenAPI；原P5“旧baseline APPROVED可RETURN”的说明随BE-a删除，不能继续引用。现有status enum无需新增“过期”或“等待归档审核”状态。

前端归档页显示待审核阻塞与可执行的审核／本人撤回路径；原“APPROVED且基线前移需要管理员处理”的暂定行退出正常流程。UI禁用仅作提示，后端直接HTTP请求仍强制门禁。前端owner据后端正式接口更新FE3文案/场景，后端不直接编辑其源码。

验证归属：`test_archive_queries.py`候选与pending读取，`test_archive_transactions.py`拒绝无副作用，`test_archive_concurrency.py`实际事务竞争；`test_review_http.py`过期APPROVE错误、当前权限下历史回放及self-only边界。复用既有owner参数表；一条真实wiring旅程证明两人的PENDING阻塞→处置→归档释放，不在Compose重复全部状态矩阵。

时间/来源核验按[业务链路设计](p6-archive-business-validation-design.md)另节实施，不由这里的pending gate冒充覆盖。Owner另确认该设计§10的“有理由关闭、不归档”出口：保留APPROVED而释放占用，不恢复旧RETURN、不扩展self-only撤回权限；具体关闭权限、统一处置schema、History/Review DTO在V2收口。本节通过也不表示全部归档业务核验完成。

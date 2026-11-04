# BE-a 设计补充：工作区占用指针与本人撤回（DC75）

状态：2026-11-04，owner 已同意方案及并入 BE-a；详细条款与验收待 kickoff 审核，审核后由 owner 确认实施。本文不是当前已部署接口或实施结果。

引用基线：main `d0a8143d804e158e16b0712cc5f2aa007066f9cb`。以下源码事实及文档均指此提交；前端问题来源为 `55e6c0083c` 的 [FE2 kickoff Q16](../../../../frontend-vnext/fe2-kickoff.md) 与 [前端 kickoff §3.3](../../../../frontend-vnext/frontend-kickoff.md)。本轮不改产品代码、前端文件、审核报告及治理文件。

## 1. 目标与范围

BE-a 在原有删除 RETURN_FOR_REVISION/RETURNED_FOR_REVISION、修正两创建接口 OpenAPI 成功码之外，增加：

- WorkspaceResponse 的当前占用指针，解决上传顶栏定位提交、刷新后找回 attempt；
- `withdraw_own_submission` 权限，允许提交人撤回自己的待审核提交，并读取本人提交的 review facts；保留 `review_submission` 的现有跨 actor 审核能力。

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
| review_submission | 现有 scope 内全部提交 | 现有 scope 内，按状态/版本等约束 | 保持现有规则 |
| 仅 withdraw_own_submission | scope 内本人提交，所有审核状态 | 仅本人 PENDING、未关闭且精确占用匹配 | 403 |
| 二者都有 | 按 reviewer 能力 | 按 reviewer 能力，无额外本人限制 | 保持现有规则 |
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
| Business Lifecycle and State §4、Workspace HTTP 设计/响应说明 | 目标 review 状态、指针投影和生命周期；归档释放时点与现有 StartArchive 事务一致，不改变归档算法 |
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
| 幂等 | 同键回放（释放后也成功）、新键终态拒绝、跨 actor 合法 WITHDRAW 回放、另一提交的 key 冲突不泄露、权限撤销后拒绝、不同动作不可回放、损坏记录维持完整性错误 | review transaction/replay 测试 |
| 事务与竞争 | WITHDRAW/APPROVE/REJECT 与归档现有合法竞争；事件/CAS/指针释放原子性，失败无部分写入 | 既有 review/archive transaction 测试，补新权限入口 |
| 指针投影 | create/get 两响应；受理、等待恢复、ABORTED、finalize、通过、撤回/拒绝、归档释放；显式 null、互斥与对应版本；并发读取不能混合快照 | Workspace 查询投影测试；生命周期 owner 提供状态构造 |
| 公开生产路径 | self-only 提交人上传→Preview→Submit→查 Workspace→查 review→撤回→刷新指针→再次上传；reviewer 原旅程回归 | 真实 wiring HTTP/Compose |
| OpenAPI | required nullable 字段；两创建接口成功码；旧动作/状态移除 | OpenAPI 测试 |

测试以业务行为命名，不枚举内部执行步骤；同构输入使用参数表。不能仅测试 reviewer 同时有全部权限的身份来宣称本人撤回通过。

05：focused（含 RS unit 删除引用回归）、五包 ruff/mypy、门禁前预检；代码通过后 04 权威 runner 与当前候选的容器门禁。真实数据拟沿用原 BE-a 的 05 t1 完整旅程；新增授权矩阵由合成测试与真实服务 Compose 旅程承担，不为本人撤回另跑 t4/2× t4。最终范围随 kickoff 审核确认，退出前 owner 按 DC33 确认。

P6 基准仍测固定 p6-s1c-exit，不因本项重新测量；不重做 S2a parser 差分或计算类 golden。BE-a 本身删除 DB 状态属于既定 schema 变化，仍用新基线 DB，不能把旧旅程 DB 直接续到新候选。任何实际影响计时路径或业务 digest 的额外改动先停下交设计/owner。

## 7. 确认与交接

- owner 2026-11-04：同意上述方向，要求补充订正并给出各方提示词。
- kickoff 详细设计/验收审核：待 owner 转交；报告不得由设计会话代写。
- 审核后 owner 实施确认、S2a exit 合入提交：待记录；当前不授权提前执行。
- 顺序：后端审核会话审核 → owner 确认 → S2a 合入后实施 BE-a；前端设计可现在更新缺口登记，FE3 刷新快照并接回入口。BE-d 范围不变。

## 8. 本次文档检查

仅修改设计/计划文档，不触发镜像重建，不宣称新权限已通过产品测试。提交前在 05 clean checkout `55e6c0083c6e3a05dc97dad86974afd645d89a8e`（与引用基线相同 vnext tree：`2791d3ff3dd62ff454d7e9cac43885d39da8bf96`）运行五包 ruff/mypy，使用已有缓存、受控 uv wrapper、UV_OFFLINE=1、CARGO_NET_OFFLINE=true、no-sync；2026-11-04T02:46:25Z–02:46:26Z，exit 0。日志为 05 `/home/dev/gdds-test-tmp/p6-be-a-design-static-20261104T024625Z.log`，SHA256 `9278890e81be494ddbc2dfad448151101dcb00d34ce14ca81e34c2e6d50ba9a3`。节点占用已释放；不是阶段取证或 carried 判定。

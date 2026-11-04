# Phase 6 BE-a 扩项 kickoff 审核

- 结论：**通过，无阻塞项；详细设计与验收可交 owner 确认。** 第 3 节有一项非阻塞的验收归属澄清建议，交设计会话。本报告不审核实施结果，不构成提前开始实施或阶段 exit 的授权。
- 日期：2026-11-04；审核会话：`p6-backend-review`（DC73）。
- 候选：main `f20f08bea91971cd99470ca1dd859567109979a2`。
- 依据：AGENTS.md、DC73/DC75；候选中的 [BE-a 设计补充](p6-be-a-design.md) 全文、[kickoff](p6-be-a-d-kickoff.md) §2/§4、[P6 设计](p6-design.md) §13.1、[执行计划](p6-execution-plan.md) BE-a 安排及 §8。对照 P5-5C review design、Business Lifecycle 和既有授权、回放、Workspace/Submit/Archive 事务接线。
- 方法：在 `/home/dev/gdds-p6-be-a-review-f20f08be` clean detached worktree 只读审核；程序比较完整 HEAD、detached 状态和工作区清洁状态。未修改设计正文或产品；未运行产品测试、Compose 或测量。05 仅只读核对已有静态日志，未获取节点占用；未访问 ct108 测量节点。

## 1. 六项重点核对

| 项目 | 结论与依据 |
| --- | --- |
| GET/POST/replay 的权限与披露顺序 | 设计 §3–§4 已闭合：认证 401；业务对象读取前按动作检查权限，缺失 403；再解析 scope、读取最小 Submission/Workspace 绑定并检查 project/device/repository 与本人关系，不存在、跨 scope、self-only 非本人统一 404；授权后才读完整 facts/closure。APPROVE/REJECT 只接受 `review_submission`，GET/WITHDRAW 接受两权限之一。已授权目标的 closure 损坏仍为 503，映射/基础设施分类保留。mutation 在同一事务重验绑定，不以 route 判断代替应用授权。 |
| 当前权限、他人 key、跨 actor 与释放后回放 | §4 保留 project-wide、actor-independent namespace/fingerprint；每次 replay 都重验当前权限、scope 与本人资格。无权请求目标先拒绝；对有权目标碰撞另一 Submission 的 key，完整性校验后返回 conflict，不返回原记录内容。损坏记录不能伪装成普通 conflict。合法同键同 fingerprint 回放从原事件恢复，保留首次 actor；释放后不再要求 PENDING/当前占用，换新 key 仍受最新状态约束。 |
| 同快照指针与版本分离 | §2 要求 Workspace、occupancy、optimistic_version 来自同一事务快照或同一写事务结果，覆盖新建 201 与已存在 200。两个字段 required nullable、至多一个非空，不查历史补值。受理、abort、finalize、审核释放和 StartArchive 释放按既有规则递增工作区版本；APPROVE 保留占用且不递增该版本。撤回使用独立 `expected_review_version`，不能以工作区版本替代。 |
| reviewer 与既有屏障 | §3 的 reviewer/双权限行保留 scope 内跨 actor 能力；self-only 以持久化 `Submission.created_by` 判本人，不依赖更新人或占用。§4 保留 review CAS、归档关闭、精确 generation/upload/preview/occupancy 校验及同事务事件、projection、幂等记录和占用释放。删除旧 return 转换后，APPROVED 仍不能新撤回；不修改 Repository commit/main。 |
| 公开生产路径与独立身份 | §6 及 kickoff §2 要求真实 wiring HTTP/Compose 的独立 self-only 提交人上传→Preview→Submit→查询 Workspace/review→撤回→刷新指针→再次上传，并回归 reviewer 旅程；禁止全权限 reviewer 替代。HTTP 授权矩阵覆盖四种权限组合、本人/他人/跨 scope/不存在及所有保留动作。事务、同快照、原子释放、OpenAPI 各有测试 owner，详见第 3 节归属澄清。 |
| 原 BE-a 工作 | kickoff §2 保留旧 action/status/event、持久化 CHECK/映射、HTTP review/history literal、Contract 与测试的完整删除；要求盘点全部消费者，不以旧文件数作验收。基线 DB 直接修订，不加兼容或迁移。两个创建接口明确为 history-compares 首次 202/回放 200、workspaces 新建 201/已有 200，运行时与 OpenAPI 同时断言；前端快照由 FE3 更新。 |

这里的 self-only 指 **review 权限中只有 `withdraw_own_submission`、没有 `review_submission`**；完整提交旅程仍使用所需的 workspace/upload/preview 等显式权限。新增权限不隐含授予这些权限，也不授权项目 History、他人工作区或 artifact 读取。

## 2. 与现有边界的对照

候选与设计引用基线 `d0a8143d804e158e16b0712cc5f2aa007066f9cb` 的 `vnext/` tree 经程序比较相同，均为 `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`。读取源码仅用于核对扩项可行性及既有屏障，不能作为扩项已实现的证据：

- `application/submission/review.py` 当前加载 scope 后读取完整 projection/events；设计明确把最小对象绑定与完整 facts 分开，在后者之前加入 self-only 本人检查，覆盖 GET 和命令。
- `review_transaction.py` 当前先处理 existing idempotency，再检查新动作的归档、版本、状态与占用；设计保留此顺序，因此撤回后释放占用不妨碍合法 replay。另一 Submission 的记录仍须验证 project/event/fingerprint，不能直接按目标 ID 不同短路成 conflict。
- `application/workspace/services.py` 与 workspace route 当前只返回 Workspace；设计明确要求应用查询/UoW/mapper 一起修改，不能在 route 后补一次 occupancy 查询拼接响应。§6 的 create/get 是现有同一 POST 的新建/已存在两条路径，不要求另建 GET Workspace 接口。
- Submit accept/finalize/abort、review release 与 Archive start 的现有事务均支持 §2 的占用/版本表。StartArchive 释放时点已有实现，目标文档同步应消除旧 Lifecycle 中“直到 ArchiveResult 推进 BaselineHead”的滞后描述，不能据旧措辞延迟指针清空；设计 §5 已将该订正列入范围。

本轮不要求重审 BE-d/BE-b，不将待决 DC74 作为已确认规则；固定 P6 基准产品和 S2a parser 差分范围不变。

## 3. 非阻塞澄清建议——交设计会话

**建议在 BE-a 设计 §6“幂等”行明确 HTTP 授权验收与事务验收的分工。** 当前该行把权限撤销、跨 actor 回放、另一提交 key 的披露和损坏记录一起归为 `review transaction/replay 测试`；P5-5C §12 则明确 Review permission matrix（含 replay、跨 actor 和错误分类）的唯一 owner 为 `tests/test_review_http.py`。结合本设计 §3–§4 和 kickoff §2，语义本身已清楚，此处不构成设计缺口，但实施时不应把这些边界全部降到应用直调测试。

建议保留 HTTP owner 对当前 session 撤权、self-only 的动作限制/非本人 404、合法跨 actor WITHDRAW 回放、他人 key 不泄露及释放后原响应回放的验证；事务 owner 负责 event/fingerprint 完整性、CAS、原子释放与失败无部分写入。复用参数表和既有测试，不要求把全部事务矩阵重复跑一遍 Compose。由 owner 转交设计会话订正，不由审核会话修改设计正文或直接通信。

## 4. 验收范围、镜像与后续

同意设计 §6 的比例化范围：05 focused（包括 RS unit 旧引用回归）、五包 ruff/mypy、门禁前预检；代码候选通过审核后再做 04 权威 runner 与绑定最终候选的容器门禁，以及 05 t1 新基线 DB 的一次完整旅程。授权/审核矩阵由合成 HTTP 与真实 wiring Compose 补齐；不为此次扩项另跑 t4/2× t4，不重做未受影响的 parser 差分或计算 golden。按包沿用及容器 carried 只按 AGENTS 判定；真实数据范围退出前仍由 owner 按 DC33 确认。

本轮仅设计与报告文档，不触发镜像重建；没有本次 BE-a 实施的 image revision/source-tree 或门禁结果可判定。既有镜像不作为新权限的证据，实施后的镜像/容器验收按 kickoff 与 AGENTS 在候选阶段完成。

05 已有文档静态日志 `/home/dev/gdds-test-tmp/p6-be-a-design-static-20261104T024625Z.log` 只读复核：程序重算 SHA256 为 `9278890e81be494ddbc2dfad448151101dcb00d34ce14ca81e34c2e6d50ba9a3`，与设计记录一致；五次 ruff、五次 mypy 成功，exit 0，起止 HEAD 均为 `55e6c0083c6e3a05dc97dad86974afd645d89a8e`。其 `vnext/` tree 与候选、设计基线程序比较一致。本报告不改代码，未重复运行这些检查；该日志仅作同源码静态检查记录，不是 BE-a 产品验收或 carried 证据。候选文档 diff 另经 `git diff --check` 通过。

下一步由 owner 确认 kickoff 细则及验收范围，设计会话记录确认并在提示词填入审核提交、S2a exit/合入提交、实施起点与会话名；**S2a exit 合入 main 后、FE3 前**实施 BE-a。提交代码候选和 handoff 后另做代码审核及证据复核。本次未推送、未打 tag、未办理 exit。

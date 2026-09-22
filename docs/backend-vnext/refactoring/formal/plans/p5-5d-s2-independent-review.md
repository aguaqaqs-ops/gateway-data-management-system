# P5-5D-S2 Independent Review

日期：2026-09-21。结论：**REQUEST CHANGES；不支持 S2 stage exit**。

评审绑定 HEAD：`8af7fb44eb5ab4a5c66ebe77dcc0d1a43352c523`。
输入：[handoff](p5-5d-s2-handoff.md)、[accepted design](p5-5d-archive-design.md)、
[execution plan](p5-5d-archive-execution-plan.md)、testing conventions 与 proportional assurance policy。
本报告没有修改既有 handoff 的签署状态，没有执行部署或 Repository effect。

## Findings

### F1 — P1：Start 未验证候选的 Workspace、Review 和 finalized Attempt closure

位置：`vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py:185`；
`vnext/backend/src/gateway_backend/application/archive/snapshot.py:67`；
`vnext/backend/src/gateway_backend/application/archive/start.py:371`。

候选 SQL 只连接 Review projection 和 disposition；没有检查 Review event/projection
一致性、Submission 对应 Attempt 的终局绑定，也不读取 Workspace 的 scope/generation/input/preview。
snapshot 使用 caller context 填充 candidate digest 的 scope；release 读取当前 Workspace 后直接清空
指针，只对当前 version 做 CAS。CAS 不能证明这个 Workspace 仍与被冻结 Submission 匹配。

真实 SQLite 探针：先生成合法 approved candidate 并确认，分别单独修改 Workspace generation、
Workspace project、Review 最新事件的 `to_status`（projection 仍 APPROVED），Start 均成功，
Head 从 fixture 的 version 3 推进至 4。其中 project 不一致时还释放了归属不符的 Workspace。
这是 accepted Design §3.1 / §5.1 step 5 明确要求拦截的本地事实不一致，不涉及新增威胁模型。

最小修复：在同一 UoW 内通过 bounded facts/owner ports 校验 scope、Review closure、finalized
Attempt 和 involved Workspace 全部绑定；矛盾返回 typed integrity failure，且不产生 Plan/Result/
Head/release。不要用 SQL 过滤丢弃矛盾 sibling。测试 owner：archive transactions（完整性 gate），
queries（资格与全集）；不复制每一步 SQL 故障矩阵。

### F2 — P1：候选上限实际限制了同 base 的全部历史 Submission

位置：`vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py:194`。

`LIMIT 201` 和超限判断发生在 APPROVED/未关闭过滤之前；SQL 只按 repository/base 筛选。
同一 base 下累积 200 条 REJECTED/RETURNED 等历史记录后，即使只有一个 approved candidate，
GetCandidates、append 和 Start 也会被 `ARCHIVE_SCOPE_LIMIT_EXCEEDED` 阻塞。继续 Review
处置不会减少这些历史行，因而设计建议的“通过 Review 减少候选集合”无法恢复。

探针：用现有 bulk SQL fixture 创建 201 条同 base Submission，再把其中 200 条 projection
改成 REJECTED，读取仍抛 `ArchiveScopeLimitExceeded`。该 fixture 用于证明 SQL 计数位置，
不作为 201 条完整业务 closure 的证据。

最小修复：对真正候选应用 201 sentinel，同时独立保留 F1 所要求的完整性检查，不能把坏行
静默过滤。测试 owner：archive queries；增加“历史总量 > 200、合格集合 <= 200”的用例。

### F3 — P2：审计 append 接受并不存在于当前集合的 selection/anomaly

位置：`vnext/backend/src/gateway_backend/application/archive/audit.py:119`、`:221`。

新 append 只检查 current candidate-set digest，然后用 caller 提供的 selected/sibling 字段
重新计算 subject；没有检查 selected ID/digest 是当前候选，也没有从当前集合推导真实 sibling。
摘要算法是公开 codec，摘要一致不能代替集合成员资格检查。

真实 SQLite 探针：当前集合只有一个合法候选时，给不存在的 `nonexistent-submission` 计算
selection digest，confirmation 成功写入 sequence 1；把 selected 自己填为 excluded sibling，
resolution 也成功写入 sequence 1。这些是无效的 durable 审计事实。Start 自身仍校验真实
selected/anomaly，因此本 finding 不声称这些事件能直接绕过 Start。

最小修复：成功-key replay 之后，新动作验证 selected exact ref，并从 snapshot 推导 anomaly，
匹配固定 issue、非 selected sibling 及 digest。测试 owner：archive audit；保留 subject 过期
后的合法原请求 replay，不让新校验破坏它。

### F4 — P2：replay 绕过 transaction-fresh enabled mapping 检查

位置：`vnext/backend/src/gateway_backend/application/archive/start.py:88`、`:119`、`:136`；
`vnext/backend/src/gateway_backend/application/archive/audit.py` 的两个 replay 分支同样如此。

scope 在事务外解析；开启写事务后先查 key 并直接返回 replay，transaction-fresh scope 仅在
新动作分支读取。若控制面禁用/切换 mapping 的事务先提交，重放仍可读取旧 Repository 成功事实。
这与 Design §5.1 step 2→3 和“当前 scope/权限永不被 replay 绕过”不符。

真实 SQLite 探针：scope resolver 先调用真实 `ProvisionedScopeResolution.resolve`，随后用另一
UoW 提交 `enabled=0`，再返回刚读到的 scope；Start 开启事务后仍返回 `replay=True`。
这一交错只需要协作的 mapping 更新，不需要恶意 DB writer。

最小修复：进入 UoW 后、幂等查询前解析 enabled mapping，使用该事务的 exact scope 查询 key；
保持 replay 早于 expected Head/candidate/audit/occupancy 校验。测试 owner：archive
transactions/audit，各自验证本用例的当前授权屏障。

### F5 — P2：有效的多 sibling audit refs 因排序不同被 Start 拒绝

位置：`vnext/backend/src/gateway_backend/application/archive/start.py:338`。

`_derive_anomalies` 沿 candidate 的 submission ID 顺序生成异常，但 `_validate_audit_refs`
把异常与 caller refs 直接 zip。Design §3.2 定义 refs 按 subject digest 排序，fingerprint
实现也按 digest 排序；两种顺序没有必然对应关系。

真实 SQLite 探针：通过现有业务 fixture 生成多个 approved sibling、逐一确认/解决，传入
按 subject digest 排序的完整最新 refs，Start 抛
`CandidateBindingConflict: anomaly resolution audit reference subject mismatch`。
只有一个 sibling 的现有测试不能发现此问题。

最小修复：以 subject digest 比较 exact set，再逐项检查 sequence/action，明确拒绝重复；
或两侧使用同一规范排序。测试 owner：archive transactions，至少两个 excluded siblings。

### F6 — P2：Plan 未冻结设计要求的候选全集和 Workspace 接受绑定

位置：`vnext/backend/src/gateway_backend/application/archive/start.py:220`；
`vnext/backend/src/gateway_backend/domain/archive/models.py` 的 `ArchivePlan`。

静态核查：`frozen_input_json` 仅包含请求的集合摘要、selected、Head 和 audit refs；Plan
其他字段与 disposition 表也没有记录全集 candidate refs 或接受时各 Workspace 的 version/binding。
Design §5.1 step 6 明确要求这些接受输入。归档 release 会修改 Workspace，后续还可复用它；
届时不能从 current Workspace 还原接受时 version。仅有 candidate-set digest 不是该输入集合。

最小修复：在现有 immutable Plan payload 中保存已验证的必要 candidate refs 和 Workspace
version/Submission binding，无需新表或 evidence 状态机。测试 owner：archive transactions，
验证 Workspace 后续复用不改变成功 Plan 的接受输入。

### F7 — P2：S2 承诺的 Result query 尚未交付到 Application

位置：`vnext/backend/src/gateway_backend/application/archive/queries.py:83`；
`vnext/backend/src/gateway_backend/domain/archive/ports.py` 的 `get_result_by_id`。

Execution Plan S2 目标明确包括 `Start/replay/Result query`。当前 Application queries 只有
GetCandidates 和 Preview；SQLite 虽有裸 `get_result_by_id`，没有带当前权限、exact scope
校验的应用用例来读取 immutable Plan summary、Result 与接受时 audit references。
这是 Application 交付缺项，不是要求 S2 提前添加 HTTP routes。

最小修复：补齐只读 Application Result query 与必要 owner port，验证当前授权及跨 scope
不披露，并读取成功 Plan 接受的 sequence。测试 owner：archive queries；S3 只补 HTTP mapping。

## 验证与边界

重新运行 handoff 原 focused gate：**224 passed, 1 warning, 9.60s**。
命令通过 `vnext/scripts/uv-consume.sh`，涵盖 archive queries/audit/transactions/concurrency/
migrations、review transactions/HTTP、submit transactions/idempotency、architecture。
warning 为既有 Starlette/httpx deprecation。

补充探针通过同 wrapper 的 `run python -` 执行，使用临时真实文件系统 SQLite 数据库，
复用现有 fixture；没有修改生产源码、既有测试或锁文件。F1 的事实矛盾通过 SQL 定向注入；
F3/F5 经正常应用入口写入；F4 用 resolver 包装器确定性表达两次事务间的合法交错。
F6/F7 为静态交付核查，不冒称动态失败。未重新执行五包 static（本次无代码变更、无提交）。

容器证据：本次是发现阻塞项的阶段内评审，未触碰 image/deployment/container runtime，
未重建镜像，不宣称当前 HEAD 通过容器门禁。handoff 引用的最后 image revision 为
`04317788c2`，本次未独立重验其 image/source-tree。**正式 S2 exit 前**仍须按 Execution
Plan S2 和仓库规则重建最终候选并运行既有 Review+Submit+Backend conjunction；handoff
简单延期到 S3/S4 的记录不能作为 S2 exit 的豁免。Archive production journey 留待 S3/S4。

评审时已有未跟踪文件 `p5-5e-s0-independent-docs-review.md`，未改动、未纳入本次范围。
本次仅新增本报告，不代签 handoff，不修复实现，不执行 commit。

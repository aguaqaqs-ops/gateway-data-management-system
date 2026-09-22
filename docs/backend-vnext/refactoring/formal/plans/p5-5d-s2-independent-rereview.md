# P5-5D-S2 Independent Re-review

日期：2026-09-21。结论：**REQUEST CHANGES；仍不支持 S2 stage exit**。

本次评审对象为 `8af7fb44eb5ab4a5c66ebe77dcc0d1a43352c523` **加未提交工作区修复**，
不是该 commit 单独的实现。评审时 `git diff --binary` SHA-256：
`bc6f4a6382b79905346d9f506ccfb70ffd978a7de420e7d2cc4181d8f048a0c2`。
另含未跟踪源码 `vnext/backend/src/gateway_backend/application/archive/closure.py`，SHA-256：
`1ee6e01d85126b8c0603417c3deac0753d155244336c98f1757a1d6cd7179346`。
该绑定用于区分本次实际验证内容；handoff 的 HEAD-only candidate binding 尚不足以标识它。

依据：[handoff](p5-5d-s2-handoff.md)、[上轮报告](p5-5d-s2-independent-review.md)、
[accepted design](p5-5d-archive-design.md)、[execution plan](p5-5d-archive-execution-plan.md)。

## Findings

### R1 — P1：候选 SQL 仍会在 closure 校验前静默丢失坏 sibling（原 F1 未完全关闭）

位置：`vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py:196`；
`vnext/backend/src/gateway_backend/application/archive/snapshot.py:59`。

新增 `assert_archive_candidate_integrity` 能拦截被查询返回的坏候选，但 SQL 先要求
`p.status = 'APPROVED'`，因此 Review projection 缺失，或 projection 与 APPROVED event
矛盾而显示 REJECTED 的 sibling，根本不会进入校验。候选全集被缩小，Start 仍可成功。

真实 SQLite 复现（两例各用独立数据库）：

1. 用 `seed_approved_dual_sibling_archive` 创建两个完整 approved sibling。
2. 对 sibling 执行 `DELETE FROM review_projection_records WHERE submission_id = ?`；
   另一例执行 `UPDATE review_projection_records SET status = 'REJECTED' WHERE submission_id = ?`，
   保留 APPROVED event。
3. GetCandidates 返回一项；对这个缩小后的集合正常 append confirmation，再 Start。
4. 两例均成功推进 Head，Result 只有一项 disposition，遗漏 sibling 的 Workspace occupancy 仍存在。

这违反 Design §3.1 / §5.1 step 5 的“矛盾不得缩小候选全集”要求；原 F1 的修复建议也明确
要求不能通过 SQL 过滤隐藏坏行。这里验证的是既定本地事实一致性边界，不要求防御恶意同 euid writer。

最小修复：候选限额仍只计算真正候选，同时通过 bounded integrity 检查识别缺失/矛盾的
Review closure，发现即拒绝整个动作。不要撤回原 F2 的候选限额修复，也不要加载无限历史来补救。
测试 owner：archive queries/transactions 按已有职责分工；至少证明坏 sibling 不会被静默排除，
Start 不留下 Plan、Head advance 或 release。

### R2 — P2：审计 sequence 未执行严格整数校验，布尔值能形成持久审计事件

位置：`vnext/backend/src/gateway_backend/application/archive/contracts.py:253`、`:294`；
`vnext/backend/src/gateway_backend/application/archive/audit.py:137`。

confirmation/resolution fingerprint 直接使用 `expected_sequence`；新动作随后用 Python
数值相等判断 CAS，没有调用已有的 strict integer validator。`True == 1`、`False == 0`
使 bool 穿过校验，而 JCS 合法地将其编码为 JSON boolean。

真实 SQLite 复现：正常 CONFIRM 得到 sequence 1；再以 `expected_sequence=True`、
`action=REVOKE` 和有效 reason 调用 append，成功返回 sequence 2。错误类型进入 durable
request payload/fingerprint，而不是被拒绝。Design §3.3 明确要求 sequence/version 拒绝 bool，
并由 Application contracts 拥有同一 validator；当前尚无 Archive HTTP 层，不以未来 DTO
校验替代 S2 Application 契约。

最小修复：在 fingerprint/接受命令前对 sequence 和 expected Head version 统一执行
非负 I-JSON 整数校验；两类 audit 命令复用参数表验证错误类型不写事件，测试 owner 为 archive audit。

### R3 — P2：CONFIRM 的可选 reason 被所有持久化层强制设为必填

位置：`vnext/backend/src/gateway_backend/application/archive/contracts.py:255`；
`vnext/backend/src/gateway_backend/application/archive/audit.py:148`；
`vnext/backend/src/gateway_backend/infrastructure/control_db/migrations.py:1222`。

Design §3.3 定义 optional reason 的 omitted 归一化为 null；§4 明确要求 REVOKE 和
ACKNOWLEDGE_EXCLUSION 的 reason 非空。当前 CONFIRM 也无条件调用 `validate_utf8_reason`，
command/domain 的 reason 仅接受 str，confirmation 表使用 `reason TEXT NOT NULL`，
因此无法表达设计允许的无 reason 确认。

真实 SQLite 应用入口探针：合法 selection 的 CONFIRM 使用 `reason=None`，得到
`ValueError: reason must be a string`。这是贯穿 Application/Domain/DDL 的语义偏差，
不能在 S3 靠补一个 HTTP 默认文本解决，否则改变 caller 审计事实及规范 fingerprint。

最小修复：仅对允许省略的动作支持 null，fingerprint 保留显式 null；REVOKE/resolution
继续要求非空 reason。同步对齐未发布 v5 DDL、row mapping 与模型。测试 owner：archive audit，
覆盖 CONFIRM null 和需要 reason 的动作拒绝 null。

## 上轮问题复核

| 原 finding | 本次结论 |
| --- | --- |
| F1 候选 closure | 部分修复；已返回候选会校验 Workspace/Review/Attempt，仍存在 R1 的静默漏项 |
| F2 限额误计历史 | 原问题已修复；SQL 限制 APPROVED/未关闭集合，并新增 200 条 rejected 历史回归 |
| F3 审计成员资格 | 原问题已修复；新动作验证 selected exact ref，并匹配真实推导 anomaly |
| F4 replay 当前授权 | 原问题已修复；Start 和两类 append 都先在 UoW 内解析 mapping，再查成功 key |
| F5 引用排序 | 原问题已修复；按 subject 集合匹配，拒绝重复，新增 triple-sibling 验证 |
| F6 冻结输入缺失 | 原问题已修复；Plan JSON 保存 candidate refs 与 Workspace version/Submission binding |
| F7 Result query | 已补 Application 入口及当前 permission/scope 校验；返回 immutable Plan/Result 和 Plan audit refs |

“原问题已修复”不等于本阶段整体退出，也不把未来 S3 HTTP 接线纳入本次通过声明。

## 验证与退出边界

- 通过 `uv-consume.sh` 重跑 handoff focused gate：**235 passed, 1 warning, 10.27s**。
  warning 为既有 Starlette/httpx deprecation。
- Backend `ruff check .` 通过；`mypy` 通过，416 source files。
- 额外真实文件系统 SQLite 探针复现 R1 的两种坏 projection、R2 boolean sequence 和 R3 null reason。
  R1 使用 SQL 定向注入既定完整性故障，R2/R3 直接调用应用入口；未修改项目测试或生产源码。
- 本次未跑全量测试、未重跑其余四包 static、未提交；仅新增本复审报告。
- 本轮没有触碰 image/deployment/container runtime，没有重建镜像，不能声称当前工作区通过
  容器门禁。handoff 引用最后 image revision `04317788c2`；其 source-tree 本次未独立核验。
  此轮仍有阻塞项，按阶段内评审处理；正式 **S2 最终候选退出前**须重建并跑 execution plan
  要求的 Review+Submit+Backend conjunction，不能仅因 handoff 写了 deferred S3/S4 而跳过。
- 保留全部已有工作区修改和两份既有未跟踪评审文档；不修改 handoff countersign。

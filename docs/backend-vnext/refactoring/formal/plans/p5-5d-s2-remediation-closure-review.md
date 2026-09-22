# P5-5D-S2 Remediation Closure Review

日期：2026-09-22。

结论：**本轮修复代码复审通过；R1–R3 关闭。本次复审范围内未发现新的阻塞性代码问题。**
此结论不等于正式 S2 stage exit；最终候选的容器门禁仍待完成。

## 评审对象

评审对象为 `8af7fb44eb5ab4a5c66ebe77dcc0d1a43352c523` 加当前未提交修复，不能只用 HEAD
表示本次已验证的代码。验证完成时：

- `git diff --binary` SHA-256：`8a6ab59b5b6cc37c6b69ba95e7d4e3e65f8fd2e5f6a6ee056409c8b6d3b86b07`。
- 未跟踪源码 `vnext/backend/src/gateway_backend/application/archive/closure.py` SHA-256：
  `db5f7b66512a7c4e7670c3160b3ae81223683cd6838dd29e2565c71def507615`。

依据：[handoff](p5-5d-s2-handoff.md)、[上轮复审](p5-5d-s2-independent-rereview.md)、
[accepted design](p5-5d-archive-design.md)、[execution plan](p5-5d-archive-execution-plan.md)。
本次重点核对 R1–R3 及相邻 candidate limit、审计 replay、nullable reason 持久化路径。

## Finding closure

| Finding | 复核结果 |
| --- | --- |
| R1 坏 sibling 被候选 SQL 静默过滤 | 已关闭。选择条件纳入缺失 projection、缺失 event 和最新 APPROVED event 与 projection 矛盾的记录；随后通过 Review owner 的 closure 校验拒绝。两种上轮探针均返回 `ArchiveIntegrityFailure`。合法 rejected 历史仍排除，SQL 保留 `LIMIT 201`，200/201 边界回归通过。 |
| R2 bool sequence 被接受 | 已关闭。两类 append 在接受前校验 sequence/Head version，fingerprint 同步使用严格整数校验；Start fingerprint 的 Head version 也已对齐。额外探针确认 `expected_sequence=True`、`expected_baseline_head_version=True` 被拒绝。 |
| R3 CONFIRM 不支持 null reason | 已关闭。Application、Domain、未发布 v5 DDL 接受 CONFIRM null，row mapping 保留 null；REVOKE 和 resolution 仍要求非空 reason。额外探针证明 null reason 的写入、读取、后续 Start，以及 Head 推进后的原 key replay 均成功。 |

上轮对 F2–F7 原问题的修复结论保持；原 F1 的剩余 R1 漏项在本轮关闭。这里没有要求扩大
同 euid 威胁模型、引入新 evidence 状态机或穷举内部调度窗口。

## 验证

通过受控 `uv-consume.sh` 重跑 handoff 的 focused gate：

```text
248 passed, 1 warning in 11.21s
```

覆盖 archive queries/audit/transactions/concurrency/migrations、review transactions/HTTP、
submit transactions/idempotency、architecture。warning 为既有 Starlette/httpx deprecation。

五包 `ruff check .` 和 `mypy` 均通过：backend（416 files）、repository_service（198）、
repository_client（26）、repository_contracts（15）、shared_kernel（34）。
`git diff --check` 通过。

额外探针使用临时真实文件系统 SQLite 数据库及现有 fixture，经同 wrapper 执行。
R1 以定向 SQL 注入上轮两种已确认故障；R2/R3 调用真实 Application 入口。
没有新增项目测试、修改实现或依赖锁；未运行全量测试。

## 正式退出仍需完成的工作

Execution Plan S2 明确要求正式阶段退出时重建最终候选并运行已有
Review+Submit+Backend conjunction。本次是修复代码复审，未构建或运行容器，因此不签署
`p5_5d_s2_stage_exit: pass`，也不声明生产 Archive journey 已通过。

本轮未改 image/deployment/container runtime，镜像验证留待正式最终候选退出节点。
handoff 引用最后已验证 image revision `04317788c2`；该 image/source-tree 本次未独立核验。
handoff 中 `deferred: S3/S4` 不能替代 execution plan 对 S2 exit 的要求；退出前需更新
candidate binding 和实际容器证据，使其指向最终受验内容。

本次只新增本报告。保留用户已有源码、测试、文档及未跟踪评审文件，未修改 handoff
countersign，未执行 commit、部署或 Repository effect。

# P5-5D-S0 Archive Entry Brief

状态：**ACCEPTED — 2026-09-20 独立 docs review 通过；implementation 未授权**

审核依据：[S0 Independent Docs Acceptance](p5-5d-s0-independent-docs-acceptance.md)。

日期：2026-09-20

Owner：Backend Archive Application / Baseline Domain；独立评审由 Backend Architecture 负责。

评审顺序：本文 → [Business Lifecycle §1A](../contracts/business-lifecycle-and-state.md#repository-scope-ownership-amendment)
→ [Archive Detailed Design](p5-5d-archive-design.md) →
[Archive Execution Plan](p5-5d-archive-execution-plan.md)。三份设计文档与 Contract 补充已一起复审通过，不拆分接受事务、迁移与并发边界。

## 1. Authority and baseline

```yaml
entry_kind: p5_5d_s0_docs_only
observed_initial_head: 4710a7a37727700c5466e83085ba5389d5816428
accepted_p5_5c_candidate: 04317788c259b172e3b8580cfe42bac8d16735f0
p5_5c_slice_exit: pass
existing_workspace_docs_publication_head: 16f4112ee10536c3c8b82765167ff0454ad5f05f
code_inspection_base: 16f4112ee10536c3c8b82765167ff0454ad5f05f
p5_5d_docs_authorized: yes
p5_5d_design: accepted
p5_5d_execution_plan: accepted
independent_docs_review: pass
docs_revision_review: pass
closed_document_findings: [initial_empty_design_budget, audit_request_fingerprint, utf8_limits, repository_scope_contract_acceptance]
remaining_design_item: none
repository_scope_contract_amendment: accepted
p5_5d_implementation_authorized: no
source_tests_dependencies_deployment_change_authorized: no
production_deployment_authorized: no
new_repository_effect_authorized: no
p5_5d_slice_exit: not_evaluated
```

初稿编写时用户明确允许先提交当时工作区，并授权只读代码核查和直接落成文档。进入时有 8 份 tracked
文档改动及 1 份 untracked 5C independent acceptance；已核对并单独提交于上述 publication HEAD。
`git diff 04317788c2 -- vnext` 为空；publication 没有改变已验收实现。5D 文档已按用户授权由复审者标记 accepted，
不把 execution plan 的未来路径预算解释为实现授权，也不重开或扩大 5C 历史授权。

权威输入已阅读：

- [5C Independent Acceptance](p5-5c-s5-independent-acceptance.md)：5C pass 的 authority、candidate 和镜像证据。
- [P5 Baseline](p5-business-vertical-slices-design.md) §2A、§6.4：增量架构限制及 Archive 冻结边界。
- [Implementation Stages](implementation-stages.md) §8：5D/5E 及 P5 整体退出的区别。
- [Business Lifecycle](../contracts/business-lifecycle-and-state.md) §4–8：资格、审计、单事务及禁止持久状态。
- [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)：既有 commit、manifest/source 权威及 digest 语义域。
- [External Effect](../contracts/external-effect-and-recovery.md)：Archive 不属于 Submit T1/T2/T3 effect recovery。
- [Proportional Assurance](../policies/proportional-assurance-and-risk-based-verification-policy.md)、
  [Testing Conventions](../../../testing-conventions.md) 和仓库 AGENTS.md。

## 2. Readiness from actual code

详细源码证据及待实现接口见 [Design §2](p5-5d-archive-design.md#2-current-code-and-required-seams)。

| 已有事实 | 5D 必须补齐的接缝 |
| --- | --- |
| SQLite WAL/FULL、写 UoW `BEGIN IMMEDIATE`；Submission/Review/Workspace 共用 connection | 增加同 connection 的 Baseline/Archive participant，不另开事务 |
| Submit T1 重读 mapping/Head 并持久 repository occupancy | 读取同一个新 Head authority；Archive 对 active Attempt 与占用交叉检查 |
| Review events/projection 和 release 已实现 | 在新 Review 动作前查询 Archive closure；已有成功 replay 先返回原事件 |
| Head 只有 mapping 表中的三个字段；seed 每次 upsert 覆盖 | 独立 Node/Head，迁移及 HTTP/worker startup seed 不回退 Head |
| `Submission` 冻结 commit、业务 base、manifest digest 等 | 从这些 facts 派生候选及 Start 冻结输入，不重新计算 canonical 内容 |
| business/comparison projection capability 仍为占位 contract | Archive 本地 read model 有真实 consumer；不把占位模块写成已实现依赖 |
| Preview checkpoint 当前拒绝空 tables，Submit base digest 复用完整 pair pipeline | initial-empty 为 S1 原 Preview/Comparison/Submit owner 的明确前置修复/验证 gate，不能只新增 fixture |
| mapping 仅限制单 device active，未禁止跨 scope 共享 Repository | Business Lifecycle 3.0.0 已接受 V1 固定 Repository→业务 scope；migration/seed/update/历史 scope 一致拒绝共享或转交 |
| 无 Archive route/schema/record/use case | 均为已审核、待实现的设计，详见设计与执行计划 |

独立文档复审已通过，四项文档 finding 全部关闭。Repository 固定 scope 补充已接受为
Business Lifecycle 3.0.0，S1 Contract 前置已满足；initial-empty 仍为 S1 必须交付的实现缺口。
以下结论及接受依据见本页所链接的独立文档审核记录：

| 评审意见 | 文档修订及后续验证 |
| --- | --- |
| P1 initial-empty 已知代码阻塞 | **文档 finding closed（复审确认）**；Design §2.1、Execution Plan S1 增加 checkpoint/pipeline/Submit digest 前置缺口、原 owner 路径预算和 focused gate；保留零行表 fixture，但 Archive journey 必须从真实 initial commit 开始 |
| P2 审计 append fingerprint 漏字段 | **文档 finding closed（复审确认）**；Design §3.2/§4.2 纳入 selected、candidate-set digest 和完整语义 body，成功事件保存 canonical request；audit owner 参数化验证同 key 改绑定冲突及过期 subject 合法重放 |
| P2 Repository→scope 反向基数缺失 | Design §3.1/§6 提出 V1 固定归属，所有 mapping（含 disabled）及历史 scope 验证、全表 Repository unique、INITIAL scope 防止转交；Business Lifecycle §1A/§9A 已接受为 3.0.0；**文档 finding closed**，S1 Contract 前置已解除 |
| P2 字符/字节不一致 | **文档 finding closed（复审确认）**；Design §3.3 统一 strict UTF-8 bytes：ID/key 255、reason 4096，无额外 2000 字符限额；HTTP/Application 同规则，HTTP owner 一份参数表覆盖中文/四字节/ASCII 边界 |

反向基数以 3.0.0 不兼容补充正式接受，不追溯标成 2.0.0 已有规则。审计/异常/容量细化
一并接受为设计；initial-empty 当前仍未修源码。本次不重新授予历史 5A/5B/5C 实现权限。

## 3. Scope and risk

| 分类 | 本轮对象 / 风险 / 最小保障 |
| --- | --- |
| A 权威事实 | 审计事件、ArchivePlan/Result、BaselineNode/Head、sibling disposition、Workspace release；误归档或跨 scope 释放不可接受，要求权限、digest、CAS、单 SQLite commit 和 response-loss replay |
| B 可恢复 durable execution | 无新增；现有 SubmitAttempt 仅作为阻塞事实消费，不新增 Archive job、lease 或 recovery journal |
| C 派生状态 | CandidateProjection、PreviewArchivePlan、issue/有效性；bounded read，失败不落库、不持久化候选/选择/预览 |
| D 实现细节 | 本用例 codec、SQL mapping、HTTP DTO；最小 owner 公共入口及现有架构测试 |

信任假设维持单机 Backend/worker 同一信任域、同一 control DB；HTTP session/scope 与调用方字段
仍不可信。Archive 只引用既有 Submission commit，不调用 Repository 写接口，不移动 main、不
创建第二个 commit、Operation/ArchiveExecution、outbox、broker、持久 candidate 或通用审批框架。

## 4. Deliverable and review boundary

当前交付包含三份 accepted 设计、Business Lifecycle 3.0.0 及独立文档审核记录 及默认入口/阶段说明同步。后续实现拆分依据实际依赖：先建立 Baseline
持久 authority、反向 scope 约束与 seed 兼容，并完成 initial-empty 前置链路，再实现完整本地归档语义，再接生产 HTTP，最后执行当前候选镜像
conjunction；不照搬 Review 的 S1–S5。

独立 docs review 已覆盖 digest preimage、审计有效性、成功 replay 顺序、事务 closure、
Review/Submit 并发、初始 Baseline migration、P5 §2A 依赖和最终实际镜像证据要求。
最终复审确认 Contract 补充与设计/迁移一致，未发现新增阻塞项。实现还须另获明确授权。

## 5. Verification and image decision

- 本次最终复审：Contract 3.0.0 与三份设计 accepted，四项文档 finding closed；
  按用户此前授权直接记录 docs review pass，S1 Contract 前置已满足，implementation 未授权。
  接受文件摘要及本次验证见 [独立审核记录](p5-5d-s0-independent-docs-acceptance.md)。

- 已有工作区提交前：五包 `uv-consume.sh ... run ruff check .` / `run mypy` 均 pass。
- 初稿一致性自查（评审前）：8 份新增/修改文档的 262 个相对链接及锚点有效，candidate/授权状态一致，
  真实源码接缝已核对，`git diff --check` 通过。`vnext/**` 无差异；独立重算 874 个 tracked 文件
  source-tree 与 5C accepted evidence 相同。本自查不替代 independent docs review。
  本轮不运行实现测试、全量 runner、镜像构建或 deployment。
- 上一轮四项意见修订只做只读源码核对与文档一致性检查；未运行实现测试、静态检查或容器 gate，
  未修改 source/tests/依赖/部署。修订后 8 份文档的 263 个相对链接/锚点检查通过，`git diff --check` 通过，
  `vnext/**` 无差异，874 文件 source-tree 摘要与上述 5C evidence 保持一致。
- 上一轮新增 Contract 补充候选并同步关联文档：9 份文档的 279 个相对链接/锚点有效，
  `git diff --check`、candidate/授权状态和禁止范围检查通过；`vnext/**` 无差异。
  不运行实现测试/容器、不修改 source/tests/依赖/部署，不自行接受补充或启动 S1。
- Current HEAD / inspection baseline：`16f4112ee10536c3c8b82765167ff0454ad5f05f`。
- Container rebuild required：no；只读核查与 docs-only 接受，不是 5D 实现阶段退出。
- Current-HEAD container gate：not-applicable；不宣称已重新验证当前 HEAD。
- Last verified image revision（引用 5C acceptance，非本轮复跑）：`04317788c259b172e3b8580cfe42bac8d16735f0`。
- Last verified tracked `vnext/**` source-tree：`sha256:9b7f863c4d24596fdddb3bbd82a4e5b25a85fcf1af26dd8af2124dbb06c885d9`。
- 实际运行的 repository/backend/worker IDs 见 [5C acceptance evidence](p5-5c-s5-independent-acceptance.md#acceptance-and-evidence)。这些是历史证据，不是 5D gate。
- Required execution point：后续任一容器边界触发轮、每个实现阶段最终候选与 5D 最终 conjunction；
  精确文件集合见 Execution Plan §6，不因已有 5C 镜像而免除。

# P5-5E-S0 History Compare Entry Brief

- 状态：**ACCEPTED — 独立文档审核通过（v3.6）；5E slice exit pass @ `21723698`**
- Date: 2026-09-21
**修订记录**：v3.6.1（2026-09-23）接受同步：纳入主工作区 @ `6707a1ca01`；S1 kickoff pass。v3.6（2026-09-21）v3.5 独立复审 **F5 分类**：确认/映射分离；B→C 不降级；结构轨。v3.5 digest pair 语义。v3.4 P3。v3.1 R1–R4。v3 F1 + F5 骨架。v2 落实 F1–F6。
- Owner：Backend vNext Business Applications and Interfaces（History 读模型 + compare 编排提案方）；独立审核由 Backend Architecture 承担
- Review order：本文件 → [详细设计](p5-5e-history-compare-design.md) → [执行计划](p5-5e-history-compare-execution-plan.md)

## 1. 权威与基线

```yaml
entry_kind: p5_5e_s0_docs_only
stage: p5_5e_slice_exit_pass
status: slice exit pass; see p5-5e-slice-exit-final.md
fixed_start_commit: 6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c
docs_review_baseline_commit: 6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c
implementation_baseline_head: 6707a1ca01c7325220ec47261b4b69a6232313ab
observed_main_checkout_at_acceptance:
  head: 6707a1ca01c7325220ec47261b4b69a6232313ab
  branch: phase1/gate-ownership-repair
worktree_for_docs_round: /home/dev/gdds-5e-history-compare-docs
branch_for_docs_round: p5-5e-history-compare-docs（自 fixed_start_commit 独立）
code_inspection_base_at_s0: 6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c
code_inspection_base_at_s1_kickoff: 6707a1ca01c7325220ec47261b4b69a6232313ab
p5_5d_docs_accepted: yes（见 p5-5d-s0-independent-docs-acceptance.md）
p5_5d_slice_exit: pass（见 p5-5d-slice-exit-final.md @ af833695ef）
p5_5e_docs_authorized: yes
p5_5e_design: accepted
p5_5e_execution_plan: accepted
p5_5e_docs_review: pass（见 p5-5e-s0-independent-docs-review.md §10）
p5_5e_docs_acceptance: pass（见 p5-5e-s0-independent-docs-acceptance.md）
p5_5e_s1_kickoff: pass（见 p5-5e-s1-kickoff.md）
p5_5e_implementation_authorized: complete
source_tests_dependency_deployment_change_authorized: 5E slice scope complete
new_repository_effect_authorized: no
production_deployment_authorized: no
p5_5e_slice_exit: pass
p5_5e_slice_exit_record: docs/backend-vnext/refactoring/formal/plans/p5-5e-slice-exit-final.md
```

基线说明：入场时主 checkout 恰在固定起点且干净。按任务规则“优先使用上述提交的独立 worktree”，本轮新建独立 worktree/分支（`p5-5e-history-compare-docs`）承载全部文档写入，且**所有源码/测试只读核查均在钉住 fixed_start_commit 的 worktree 内执行**；主 checkout 零改动、零未提交文件。

交付时点基线漂移记录：本任务 docs-only 期间，**并行的 P5-5D-S1** 在同一分支 `phase1/gate-ownership-repair` 的**主 checkout** 上推进了实现类提交（如 `823661134e` Baseline Head DB authority + initial-empty preview、`d19b3efcab` close S1 review gaps）。这些提交**不属于**本任务代码基线、也**不是**已验收的 5D 事实；本 worktree 始终钉在 `6f6a780415`，未吸收上述任何改动。故本文一切 E 级源码事实以 `6f6a780415` 为准；5D-S1 的实际落地须经其自身 slice exit 独立验收后方可作为 5E 的 D→E 依据（见设计 §9 对齐门）。

本轮阅读的权威输入（全部在 fixed 起点读取）：

- `AGENTS.md`、`docs/backend-vnext/testing-conventions.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-business-vertical-slices-design.md`（§2A、§6.5、授权、持久化、artifact retention、退出条件）
- `docs/backend-vnext/refactoring/formal/plans/implementation-stages.md`（Phase 5、cross-stage workflow）
- `docs/backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md`（3.0.0：fixed scope、§6 History、§7 授权、§9 持久、§1A.3 改绑例外）
- `docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md`
- `docs/backend-vnext/refactoring/formal/contracts/operation-lifecycle-and-integrity.md`
- `docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md`
- `docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5d-s0-independent-docs-acceptance.md`、`p5-5d-archive-design.md`、`p5-5d-archive-execution-plan.md`
- 按真实调用链补读（worktree 内源码核查）：`vnext/backend/src/gateway_backend/capabilities/comparison/{contracts,pair_planning,standard,ordered}.py`、`application/preview_jobs.py`、`application/checkpoints.py`、`capabilities/snapshot_materialization/repository_ref.py`、`capabilities/{risk_evaluation,surface_assembly,bundle_assembly}/*`、`infrastructure/control_db/*`、`infrastructure/repository_read/http_arrow.py`、`http/{auth,dependencies,runtime,wiring,errors,routes,schemas,orchestration}/*`、`bootstrap/operation_worker.py`、`operations/*`、`vnext/deploy/config/session.json`、repository 侧 native diff 核查（`vnext/repository_service` `dolt_schema_diff` measurement provider，E non-production）。

一次性验证（**非测试、不入库、非门禁证据**）：`/tmp/verify_history_pair.py` —— 用 materialize 的只读路径 + 现有 comparison/risk/surface/bundle 入口真实跑通 HISTORY pair（同 commit → 全表 UNCHANGED、确定性 digest；结构不同 → 表级 DEGRADED），用于设计 §5.3 等价性声明。结论：capability 层无需为 HISTORY 改代码；Application 层装配为 5E 新增。该脚本不在 repo、不作为测试、不作为 slice 证据。

## 2. 实际代码得出的 readiness

“当前已有” 与 “本设计新提案” 的边界（细节与设计 §2 同一来源）：

| 已有（E，fixed 起点可证） | 本设计依赖的缝 / 新提案（D/P） |
| --- | --- |
| `PairViewKind.HISTORY` R5 词表 + `bind_pair_input`/`plan_pair` HISTORY 规则，planning 已测试 | HISTORY **执行** 在 Application 层的装配（P）；capability 零改动（E 证明：`compare_plan` 无 view 分支） |
| `materialize_repository_ref` 只读 exact-commit 流式恢复（`pinned_commit_hash` 强校验） | 零表 commit 的初始空链路修正属 5D-S1（D），5E compose 该腿引用其 gate 证据 |
| compare/risk/surface/bundle 公共入口 + FULL 三节点 → 相邻双 pair + MULTI_PAIR bundle 装配模式（preview 先例） | compare accept/3-step job/result 读（P）；复用同一调用链。**F1 缝（v3 闭合）**：`bind_pair_input.table_policies`（E 参数，默认空）在基线无 producer；5E accept 冻结 `table_ruleset_version`（accept-binding），materialize 后 union TableSet 经 `resolve_table_rule` 投影 policy 并冻结进 compare-binding checkpoint；assemble 只读 checkpoint，capability 词表零扩展 |
| artifact 命名空间 `comparison`/`bundle`；校验器保留 flow-local 前缀（含 `history-`/`history:`，`_RESERVED_REF_PREFIXES`） | compare artifact 沿用 `comparison` 命名空间（P 决定），不新建前缀 |
| 独立 Operation 运行时（record/store/step/idempotency/worker）+ preview accept 模板 | `backend-vnext/history-compare` 3-step JobDefinition + `history_compare_acceptance_records` + `history_compare_integrity_records`（P，v6） |
| 路由机制 / session 权限模型（4 既有权）/ admission / registry / shutdown 骨架；internal bearer（E `require_internal_bearer`，operator recovery 同型） | `read_project_history` 词表项 + 5 路由（前四条 session；integrity-ack 仅 internal bearer）+ 窄 `HistoryHttpDependencies`（P） |
| control DB v4 + mapping 3 字段 Head | baseline 节点表/Head 权威/archive disposition 表 = 5D-S1/S2 交付（D）；5E v6 基于 5D 最终 v5 |
| T 侧无 history 测试 | 7 个新测试文件 + 既有文件增量（设计 §8 owner 表，含 `test_history_compare_integrity.py`） |

## 3. Scope / 风险清单 / 信任假设

比例化保障分类（policy §1–§4）：

| 类 | 对象 | 处置 |
| --- | --- | --- |
| A（权威执行事实） | `history_compare_acceptance_records`（accept-binding replay 权威）、`history_compare_integrity_records`（类 c 等价 control record）、operation/step 记录（E runtime） | 单事务原子、accept-binding 幂等、短事务；integrity 保留至 ack + resolution；误 accept = 误 replay，有界处置 |
| B（可恢复持久执行状态） | 无新增（compare 为 PURE_RECOMPUTE，checkpoint 走 E 机制） | 不加新长期状态机 |
| C（派生/临时） | `HistoryTreeProjection`、`eligibility_note`、结果 bundle/artifact | 按请求派生；结果可从冻结输入重算；FAILED/CANCELLED 走既有 bounded TTL；不建二级 GC |
| D（内部实现细节） | codec/SQL 映射/DTO/mapper | bounded + 回归样例即可 |

信任假设（不扩大威胁模型）：

- 同机 backend/worker 同一信任域、同一 control DB（ADR 0012 边界）；不新增独立 UID/helper/sidecar 安全机制。
- `session.json` / `scope` / `actor` / HTTP 字段是 attacker 可控；compare 只读 + Repository 只读协议 + 每次读重新授权是全部边界。
- 读路径不以 “同 euid 即为安全” 豁免 path/symlink/root 边界（artifact store 走既有受保护路径机制，E）。

风险清单（非机制扩张项；触发即停，见设计 §10 停止条件）：5D 表形偏离假设、跨 scope 泄漏路径、词表被迫扩展、integrity 事件真实化、跨 version pair 需求、全量冻结需求。

## 4. 交付物与本轮审核边界

本轮交付（三份，全部 CANDIDATE / independent review pending / implementation unauthorized）：

- `docs/backend-vnext/refactoring/formal/plans/p5-5e-s0-entry-brief.md`（本文件）
- `docs/backend-vnext/refactoring/formal/plans/p5-5e-history-compare-design.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5e-history-compare-execution-plan.md`

**本轮明确不修改**（避免与 5D-S1 及共享入口冲突）：

- `docs/backend-vnext/refactoring/formal/README.md`（共享入口表）
- `docs/backend-vnext/README.md`（P5 当前入口行）
- `docs/backend-vnext/refactoring/formal/plans/p5-business-vertical-slices-design.md`（P5 总览表 / §13 下一步）
- `docs/backend-vnext/refactoring/formal/plans/implementation-stages.md`（阶段总表）
- 5D 全部已接受文档（design/execution/s0/read 修订）

审核接受后需要同步的入口见 §5（本轮只列出不执行）。

审核焦点（详见执行计划 §2 S0）：双层 binding、404 不披露/改绑/撤回、相邻 pair、replay 与 §6.2 integrity 门禁（replay 不阻塞）、类 (c) E 码/复现读、internal-bearer ack、HTTP/worker 码分层、只读零写、v6 纪律、测试 owner、镜像 provenance。若审核认为需修订上游 Contract：由 reviewer 列明 owning Contract 与最小替代；本轮**不**直接改写上游 accepted 文档。

## 5. 审核接受后入口同步（2026-09-23 已完成）

接受同步由 [p5-5e-s0-independent-docs-acceptance.md](p5-5e-s0-independent-docs-acceptance.md) 记录；
S1 kickoff 见 [p5-5e-s1-kickoff.md](p5-5e-s1-kickoff.md)。已同步：

1. `docs/backend-vnext/refactoring/formal/README.md` — 5E accepted 行 + P5 入口更新
2. `docs/backend-vnext/README.md` — P5 当前入口行
3. `p5-business-vertical-slices-design.md` — header + §13
4. `implementation-stages.md` — Slice 5E 状态
5. 本三份 5E 文件 — status → accepted；审核基线 SHA 保留于接受记录 §2

## 6. 验证与镜像决策

本轮已执行（docs-only）：

- 只读源码/测试/Contract 核查（全部在 fixed 起点 worktree）；
- 一次性 HISTORY 执行语义验证脚本（§1 末段；非测试、不入库）；
- v2 修订轮只读复核（F1–F6 引用事实在 fixed 起点 worktree 重新核实）；
- **v3 定向修订**：F1 双层 binding；F5 integrity record；非阻塞整理。
- **v3.1 定向补齐（R1–R4）**：类 (c) E 码/复现读；internal-bearer ack；§6.2 门禁步；稳定码分层。
- **v3.2–v3.4**：R1a 诊断指纹方案（**v3.5 废止**）。
- **v3.5 独立复审定向修订（F5）**：materialization 公开 `DigestRef` mismatch pair；History 只投影。
- **v3.6 独立复审定向修订（F5 分类）**：确认/映射分离；B→C；结构轨。
- **关闭自检（v3.6）**：

| ID | 状态 | 落点 |
| --- | --- | --- |
| F1 | 关闭 | 设计 §5.2 |
| F5 骨架 | 关闭 | §6.4 表、§7.1 ack、事务闭包 |
| F5 分类规则 | **S0 可审闭合** | §6.6 两层判断、证据轨 A/B |
| F5-R1 | 关闭 | B→C 仍升 (c)；首次 pair 写入 |
| F5-R2 | 关闭 | 结构轨；不得无 pair→(a) |
| F5 公开面映射 | **S2 阶段内闭合** | §6.6；Plan §3 窄例外；三场景参数表 |
| R1–R4 / N1–N4 / F1a–F1c / P3 | 关闭 | 各前版落点 |
| R2 | 关闭 | §4.1/§7.1/§7.3/§7.4 |

- 三份文件相对链接/锚点检查（无 broken 相对链接）、源码路径存在性检查、状态/授权一致性自检；
- `git add -N` 三文件后 `git diff --check`；grep 无残留 `policy/ruleset 漂移` / worker 码误入 `http/errors.py`。

本轮**未执行**（docs-only 边界）：实现测试、五包 ruff/mypy（无源码改动）、`./vnext/scripts/run-tests.sh` 全量、镜像构建/传输、部署变更。

容器/镜像判定：

- 需要重建镜像：**否**（docs-only，无 image/deployment/container-only runtime boundary 触碰）。
- 当前 HEAD 容器门禁：不适用（无源码改动）。
- 最后验证的 image revision（历史证据，本轮未重跑）：source tree 提交 `04317788c2aa4c62fedf08b61037cd9ac973cd81`（见 5C 独立接受与 5D 文档基线记录）；实际 image ID 以 5C 接受记录为准。
- 必须实际执行镜像构建/容器门禁的节点（见执行计划 §6.1）：5E-S1 末候选（production wiring 触碰）、5E-S2 末候选、5E-S3 最终候选 + 正式 journey 并合、S4 最终 fresh 候选并合；每节点按 §6.3 格式记录运行 image identity。旧镜像结果仅作回归证据，不表述为当前 HEAD 已验证。

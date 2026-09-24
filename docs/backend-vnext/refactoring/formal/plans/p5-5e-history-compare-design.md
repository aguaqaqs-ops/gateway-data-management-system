# P5-5E History Compare 详细设计

- 状态：**ACCEPTED — 独立文档审核通过（v3.6）；S1 实现已授权**
- Stage：`p5_5e_s0`（docs-only 设计交付，见 [S0 Entry Brief](p5-5e-s0-entry-brief.md)）
- 日期：2026-09-21
**修订记录**：v3.6.1（2026-09-23）接受同步；S1 kickoff pass。v3.6（2026-09-21）v3.5 独立复审 **F5 分类**：确认条件与字段映射分离；B→C 不降级；结构 mismatch 轨。v3.5 公开 digest pair 语义。v3.4 P3。v3.3 F1a–F1c。v3.1 R1–R4。v3 F1 + F5 骨架。v2 纳入 F1–F6。
- Owner：History Application（History 读模型 + compare 编排）；无新增 Domain aggregate。独立审核由 Backend Architecture 负责，业务闭环由 Backend vNext Business Applications and Interfaces 复核。
- 执行预算（路径/验收/handoff）：[P5-5E History Compare 执行计划](p5-5e-history-compare-execution-plan.md)

上游依据：
[P5 Business Vertical Slices Design §2A / §6.5 / §7–§12](p5-business-vertical-slices-design.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)（3.0.0，fixed scope、§6 History、§7 授权、§9 持久状态、§1A.3 改绑例外）、
[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)（DRAINING 拒收已列 “history compare”）、
[Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)、
[P5-5D Archive Design](p5-5d-archive-design.md)（accepted 设计，实现未完成）、
[Proportional Assurance and Risk-Based Verification Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)。

**基线声明**：本文全部代码事实基于固定基线 `6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c` 的只读核查（见 Entry Brief §1 的 worktree/分支状态）。5D-S1 实现/审核与本轮并行；所有尚未落地的 5D 内容一律标注为 **D**（accepted 但未实现）。事实三级标注：**E** = 基线已实现且有证据；**D** = 5D accepted 设计但基线未实现；**P** = 本轮 5E 新提案。除下表标注外，本文新引入的路径、权限、表、路由均为 P，不是现存接口。

## 1. 核心决定与非目标

核心提案：**History 是按请求派生的读模型**（Business Lifecycle §1 表已固定 `HistoryTreeProjection` owner 为 History Application read model，不持久化），**History Compare 是一个只读 Operation**：把两个或三个授权业务节点绑定到 exact immutable CommitId，复用已实现的 materialize/comparison/risk/surface/bundle 公共入口（HISTORY view 是基线已存在的 R5 vocabulary，E）完成只读执行与结果发布。不修改任何 Workspace/Submission/Archive/Baseline 业务状态，不触碰 Repository 写入、main 或 canonical storage。

决定（P，待审核后随实现交付）：

1. 不建持久业务树、不建 history 存储表；projection 从权威事实按请求组合。
2. 不扩展 comparison/risk/surface/bundle 词表：`PairViewKind.HISTORY` 的 binding/planning 规则已在基线实现并测试（E）；5E 的工作是 Application 层把业务节点映射到既有 `bind_pair_input`/`plan_pair`/`compare_plan` 入口，**并在 materialize 后从固定 ruleset 为每 table 构造 `ComparisonTablePolicy`（含 `ordered_policy`）并冻结进 compare-binding checkpoint**——基线该绑定无 producer（E 缺口，审核 F1 发现）：History 只按 `table_rules` 公共解析结果（E `resolve_table_rule`）做忠实数据投影，不猜 gid、不复制 rule 算法、不加新 capability 词表（`OrderedTablePolicy`/`BlankRowPolicy` 类型既有，E）。accept 短事务只冻结 ruleset identity（`table_ruleset_version`），不在 accept 时枚举 per-table policy（F1 v3 闭合）。
3. 三业务节点 = 两个相邻 pair（node-0→node-1、node-1→node-2）+ 3-input MULTI_PAIR bundle——预览 FULL 拓扑模式（E，`preview_jobs.py` 已实现同样拆分）；不存在原生三侧 comparison。
4. trusted_flow_binding 由 History Application 按 §5.2 的 preimage 生成；R5 只校验 binding 形状与 view_kind 一致性（E）。
5. 新增面：1 permission string（`read_project_history`）、5 条 HTTP 路由（含 integrity ack）、2 张 control 表（acceptance + integrity record，workspace schema v6）、1 个 job kind（按 step 注册 3 个 JobDefinition，E preview 先例 `preview_jobs.py:304–343` 同款）。
6. 只读边界：所有 Repository 输入经既有 `materialize_repository_ref` 只读通道流到 exact commit（E）；`dolt_schema_diff`/native diff 是 `schema_only` 的 non-production measurement provider（E），本设计不使用。

非目标：

- 不写 Repository、不移动 main、不产生新 commit、不 import；compare 不携带任何 Archive/Submit effect。
- 不暴露 Dolt `/log`、技术 parent 或 provider operation 作为业务树或产品字段（§3 仅限合同允许的语义保留）。
- 不删除/改写 `rejected/withdrawn` 历史节点或位移归档/审计记录；出现真实需求按 P5 §12 重开。
- 不实现 `SYSTEM_MIGRATION` 生成路径、迁移执行框架或 mock producer（§3.4 只保留词表与解析规则）。
- 不改动 Preview/Submit 的 initial-empty 基线语义；该链路修正由 5D-S1 负责，5E 只消费（§9）。
- 不实现 `comparison_projection`/`business_projection` 等无 consumer 占位（P5 §2A.4 允许延迟）；P5 §2A.4 的 “5E 有真实 Demand Comparison/Runtime consumer 时” 指的是 Application 层对既有 R5 入口的调用，不是 capability 层新消费者。
- 不新增通用任务平台、outbox、持久执行状态、双 GC/refcount 状态机。
- 产品面不暴露技术 parent（V1 无 consumer；Contract 保留为诊断字段，deferred）。

## 2. 当前代码与依赖

精度：B=`vnext/backend/src/gateway_backend/`，T=`vnext/backend/tests/`；与 5D 文档同款记号。

### 2.1 已实现（E）

| 事实 | 位置（基线 6f6a780415） | 对 5E 的含义 |
| --- | --- | --- |
| `PairViewKind.HISTORY`/`ARCHIVE_REPLAY`：HISTORY 强制 `FULL` + trusted flow binding + `NOT_APPLICABLE` identity；`plan_pair` 强制 `PairRole.HISTORY`（`pair_id` 是 caller 传入的不透明输入参数，非 path-like） | `B/capabilities/comparison/contracts.py`、`B/capabilities/comparison/pair_planning.py`；`T/test_comparison_planning.py`（HISTORY 参数化用例） | 词表与 planning 已实现并有测试；5E 直接把业务节点映射进 `bind_pair_input` |
| `compare_plan` 对 HISTORY **无 view 分支**：standard facts → RecordsClosure，与 preview 同一算法；`T/test_comparison_standard.py` 没有 HISTORY 执行用例 | `B/capabilities/comparison/standard.py`、`ordered.py`、`contracts.py`（capability 层无 HISTORY 特判） | 执行算法复用，无需 capability 改动；HISTORY 执行回归用例归 capability owner（§8） |
| `materialize_repository_ref`：read-only session + exact commit 流式恢复 Snapshot/Summary/TableSet，`pinned_commit_hash` 强校验；直接路径（`requested_tables=None`）允许零表 hidden summary 快照，而 bound document 恢复路径（`preview_jobs._bound_from_side_document`）拒绝空表集 | `B/capabilities/snapshot_materialization/repository_ref.py`；repository 读 provider 为单向 read protocol（`B/infrastructure/repository_read/http_arrow.py`） | compare 全部输入的唯一致能入口；initial-empty 的零表腿依赖 5D-S1 initial-empty 门禁（D） |
| compare/risk/surface/bundle 公共入口：`bind_pair_input → plan_pair → compare_plan → publish_records_closure`、`evaluate_risk`、`assemble_surface`、`assemble_bundle`；FULL 三节点 → 相邻双 pair + MULTI_PAIR bundle 的装配模式 | `B/application/preview_jobs.py` 与 `B/capabilities/{comparison,risk_evaluation,surface_assembly,bundle_assembly}/*` | 5E 照同一调用链装配，only view/persona/binding 不同 |
| artifact 身份校验器为保留 flow-local 前缀（含 `history-` / `history:`）；既有 namespace 为 `comparison`（`ComparisonPublishContext.artifact_id_prefix` 默认值）与 `bundle`，`build_artifact_id(namespace, suffix)` | `B/capabilities/{surface_assembly,bundle_assembly}/_refs.py`（`_RESERVED_REF_PREFIXES`）、`B/artifacts/digest.py`、`B/capabilities/comparison/artifacts.py` | compare artifact 沿用 `comparison` namespace；不新建 `history-` 前缀（否则需先扩 capability 校验器） |
| 独立 Operation 运行时：record/store/idempotency/step/state/worker 协议；preview 是可复制模板：deterministic `op-<sha256[:24]>`、幂等插入语义（exact idempotency）、acceptance 读写 port、completion 条件 | `B/operations/{contracts,lease_session,persistence,recovery,state,store,worker,worker_lifecycle,worker_runtime,worker_startup}.py` + `B/infrastructure/control_db/sqlite_operations.py`；preview 模板 `B/application/{preview_jobs,preview_registry}.py` + `B/http/orchestration/preview_acceptance.py` | compare 复用同一 runtime；5E 新增的是自己的 JobDefinition 与 accept 事务，不新增 runtime 能力 |
| publish 流水线：UNIT/PURE_RECOMPUTE/TERMINAL 分层、handoff checkpoint（OPERATOR_BLOCKING resumption）、progress 由 Python lease 缓存主导；checkpoint/ready-closure envelope 机制 | `B/application/preview_jobs.py`（publish 步骤）+ `B/application/checkpoints.py`（`prepare_step_checkpoint` / `load_checkpoint_envelope` / `ready_closure`）+ `B/http/orchestration/bundle_stream.py` | compare 3-step job 的 checkpoint/progress/terminal 直接套用 |
| HTTP 骨架：`register_workspace_http`、`WorkspaceHttpDependencies`、生产 router 集（含 `GET /v1/operations/{id}`）、session/auth（`IdentityContext`）、`Idempotency-Key` header 校验（1..255）、shutdown/drain registry | `B/http/{auth,dependencies,errors,mappers,runtime,shutdown,wiring}.py` + `B/http/orchestration/*` + `B/http/routes/*`（9 个 router）+ `B/http/schemas/*` | 5 条新路由挂在同一 router 机制上 |
| 权限模型：`IdentityContext`（定义）+ `assert_permission`（EPERM 语义）+ session → context 绑定；现网 portfolio 仅 `workspace_read`、`upload_submit_workspace`、`preview_workspace`、`review_submission` | `B/domain/workspace/{models,policies}.py` + `B/http/auth.py`；example 权限集 `vnext/deploy/config/session.json` | 新增 `read_project_history` 是词表扩展，非授权机制改动 |
| control DB：SQLite + migrations（operations v1、workspace v1..v4）、UoW/transaction、worker store；Head 当前在 workspace mapping 的 `baseline_head` JSON 字段（5D 设计 §6.3：5D-S1 迁入权威表）；scope 解析与 Head 只读 port 已存在（E `ScopeResolutionPort` / `BaselineHeadReadPort`，`B/domain/workspace/ports.py`） | `B/infrastructure/control_db/{database,migrations,sqlite_mapping,sqlite_operations,sqlite_submission,sqlite_review}.py` | 5E 新增 v6（acceptance 表）与 history 读 port；Head 权威以 5D 最终 v5 为准（D，port E 已就位） |
| 测试基建：integration/serial marker、dolt conftest 门禁、compose gate harness、materialization 协议测试脚手架（fake provider） | `T/conftest.py`、`T/support/compose_gate_harness.py`、`T/test_repository_ref_materialization_{protocol,digest,hidden_summary}.py`、`T/support/repository_ref_materialization.py` | 新增测试挂在同一门禁体系；compose e2e 用既有 harness 模式 |

### 2.2 缺失/占位（E 中不存在，5E 依赖的缝）

| 缺失 | 现状 | 5E 的缝（P） |
| --- | --- | --- |
| HistoryTreeProjection 读模型 | 不存在（无 B/application/history/） | 新建，见 §3 |
| node→commit 统一读口 | submission 的 `repository_commit_id`/`business_baseline_commit_id` 已实现（E `B/domain/submission/models.py` `Submission`）；baseline 节点行的 commit 字段属 5D-S1（D） | 5E 按 §4.2 分源读（submission 腿 E、baseline 腿 D）；baseline 腿在 5D-S1 落地前不能写代码 |
| `p5_5e_compose` 编排面 / compare 入口 | 不存在 | 见 §5、§7 |
| HISTORY 执行层回归（capability 层） | planning 有 HISTORY 用例，standard 无 | capability owner 增加执行用例（§8），5E 不复制 |
| 比较表策略绑定入口 | `bind_pair_input(table_policies=…)` 参数存在（E `pair_planning.py:72`，默认空 → 每表默认 policy：`ignored_columns=()`、`ordered_policy=None`，即 `no` 列参与普通 keyed 值比较）；基线 src 无任何调用方构造 `ComparisonTablePolicy`（核查：0 producer）；`OrderedTablePolicy`/ordered/blank 执行路径已实现并测试（E `ordered.py`、`T/test_comparison_ordered.py`）；per-table `ordered_policy`/key/pseudo 键属事实由 `table_rules` 持有（E `resolver.py:36`、`registry.py`） | P：accept 冻结 `table_ruleset_version`（`accept-binding`）；materialize 后 union TableSet 经 `resolve_table_rule` 投影 policy 列表，冻结进 `compare-binding` checkpoint（§5.2/§5.3）；assemble 只读 checkpoint，不重派生。Application 层 integration，不改 capability |

### 2.3 5D 已接受但未实现（D，5E 依赖的交付物）

| 5D 交付物 | 对 5E 的意义 | 5D 阶段 |
| --- | --- | --- |
| `baseline_node_records` + `baseline_head_records`（v5 workspace migration、seed 不变量、Head 权威自 mapping 迁移） | History 的 INITIAL/Baseline 节点与 node-head 来源；5E S1 读模型的前置 | 5D-S1 |
| ArchivePlan/Result/Disposition 持久化 + `archive_submission` 权限 | History 的 archive disposition 展示；compare 的 ARCHIVED 节点来源 | 5D-S2 |
| initial-empty 链路修正（Preview/Submit 原 owner） | 空 initial baseline 的 materialize/compare 一致性 | 5D-S1 |
| `p5_5d_compose` e2e（真实 Dolt 旅程） | 5E compose 旅程复用其 dolt 环境模式与 harness | 5D-S4 |
| scope resolution hardened（rebind-only 权限、`UNIQUE(repository_id)`） | 5E §4 的 scope→repository 解析前提 | 5D-S1/S3 |

**5E 实现启动的硬前置**：上述全部 D 项经 5D 独立 slice exit 验收（见 §9 依赖表与对齐点）。在 D 落地前，5E 只交付本文档；不得以“部分实现 5D”为由提前截断。

## 3. HistoryTreeProjection

§2A.4 定位：`HistoryTreeProjection` 是 5E 提案中的**应用读模型**（Application 层），owner 是 History（新 Application 入口），不是 capability 层组件；它的 consumer 是 History HTTP API 的只读端点。若未来出现 capability 级消费者（例如 archive plan preview 的主线对比），由 Capability Foundations owner 按 §2A 在原 owner 处开最小公开端口，5E 不预建。

### 3.1 input：按请求从权威事实派生

Projection 不持久化，每次 HTTP 请求在 readonly 快照内重新派生（WAL 快照隔离，读不加锁）。派生输入：

| 源 | 事实（D/E） | 说明 |
| --- | --- | --- |
| `baseline_node_records` | D（5D-S1 后 E） | INITIAL 节点 + 每次 archive 产生的 ARCHIVED_SUBMISSION 节点；含 `parent_node_id`、`business_baseline_commit_id`、`source_submission_id`、frozen scope、`created_at` |
| `submission_records` | E 表 / 5D-S1 后 scope 一致读 | 全部成功 Submission（五 review 状态都算），`repository_commit_id`（E）给出 exact commit |
| `review_projection_records` + `review_event_records` | E（v4） | 节点的 `review_status`（投影值）与事件闭包 |
| `archive_disposition_records` | D（5D-S2） | submission 节点的唯一 disposition（`ARCHIVED_BASELINE` / `CLOSED_NOT_ARCHIVED`），不另设 archive 状态字段 |
| `baseline_head_records` | D | current Head 指针（`head_version` 非回退单调） |
| validation/eligibility issues | 派生（§3.3） | `eligibility_note`，V1 仅一个推导码 |

**排除不变量**：失败 import / 私有 candidate / Operation marker 不进 projection——它们没有进入上述权威事实（contract §6 “非成功业务事实不得成为可比较快照”）。Projection 不持有或读取 Dolt log、provider operation 或任何技术游标。

**D 表字段警示**：上表 `baseline_node_records` / `baseline_head_records` 的字段名是 5D accepted 设计的字段名，**不是基线实际列**；submission → scope 归属路径走 E `provisioned_scope_mappings`（+ workspace 归属）；实际 join/列名在 kickoff gate 重核（§9 对齐门首行），实现前以 5D 最终代码为准。

### 3.2 节点模型（稳定引用）

```
HistoryNode {
  ref_kind:  "baseline_node" | "submission"          # 稳定节点引用
  ref_id:    node_id | sub_id                        # 稳定节点 ID（1..255 字节）
  node_kind: BASELINE_NODE | SUBMISSION | SYSTEM_MIGRATION   # see §3.4
  baseline_kind: INITIAL | ARCHIVED_SUBMISSION       # BASELINE_NODE only
  commit_id: exact immutable CommitId                # 权威事实解析结果（opaque string，1..1024 code points）
  created_at: datetime                                # 事实成立时刻（submit finalize / node created_at）
  parent: { ref_kind, ref_id } | null                # 业务父边（非技术 parent）
  review_status: PENDING|APPROVED|REJECTED|RETURNED_FOR_REVISION|WITHDRAWN | null   # SUBMISSION only
  archive_disposition: ARCHIVED_BASELINE | CLOSED_NOT_ARCHIVED | null              # SUBMISSION only
  promoted_baseline_node_id: node_id | null          # SUBMISSION only；被 archive 晋升时
  eligibility_note: NOT_CANDIDATE_BASE_ADVANCED | null # 派生，§3.3
}
```

- **Commit 传递纪律**：`CommitId` 是 repository-scoped opaque string（1..1024 code points；E `vnext/repository_contracts` `CommitIdString = BoundedOpaqueString`；契约 `repository-service.md` §2 表）。所有层（binding preimage、job payload、HTTP DTO）按 opaque 值原样传递：**不做** 40-hex 断言、不 re-encode/trim/normalize；HTTP path 传输用既有 base64url canonical 编码规则（repository HTTP 层 E 同款）。DTO 约束按 code point 计 1..1024。reserve：40-hex 只是 Dolt 常见形态，不是合法域。
- **CommitId 三方边界（5D 对齐门，S1 记录）**：设计/DTO 取 `CommitIdString`（1..1024 code points）；5D v5 control DB CHECK 将 `submission_records.repository_commit_id` 与 `baseline_node_records.commit_id` 限为 `length(...) BETWEEN 1 AND 255`（SQLite `length()` 对 UTF-8 TEXT 计字符）。S1 不迁移 DDL；持久化上界 255 字符、HTTP/Contract 上界 1024 code points 并存，避免 S2 compare DTO（`before_commit`/`current_commit`）重复踩坑。
- **ref_id 三方边界（5D 对齐门，S1 记录）**：设计/DTO 取 `BoundedOpaqueId`（1..255 **UTF-8 字节**，见 `http/schemas/constraints.py`）；5D v5 CHECK 将 `node_id` / `submission_id` 等限为 `length(...) BETWEEN 1 AND 255`（SQLite TEXT **字符**计数）。偏差：DB 可存 258 字节 CJK `node_id` 而 DTO 拒绝 → 500；生产 id 为 `uuid4()` ASCII（`application/archive/start.py` 等），**生产不可达**。S1 **决定**：保持 DTO 字节上界不变，仅记录；不新增「预期 500」测试。
- **同 commit 多业务身份**：同一 commit 可同时是 submission S 与由 S 晋升的 baseline node B。二者各自成节点、稳定引用不同（`ref_kind/ref_id` 不同），`commit_id` 相同；不合并、不去重，`promoted_baseline_node_id` 是唯一的跨引用（见基线核查：5D handoff 中 submission 与 baseline 行各自持有引用）。
- **业务父边 vs 技术 parent**：`parent` 由业务事实构造——SUBMISSION.parent = 其 `based_on_baseline_node_id` 指向的 baseline 节点；BASELINE_NODE.parent = `parent_node_id`（INITIAL 为 null）。Repository 技术 parent commit **不是** `parent`；V1 不暴露技术 parent（诊断字段允许的契约语义 deliver deferred，无 consumer）。
- **disposition 覆盖**：任一成功 submission 节点**恰好一个** disposition 来源（`archive_disposition_records` 的 result 子级或无记录）；`CLOSED_NOT_ARCHIVED` 节点保留 commit 与 review facts，仅不是 archive candidate。
- **有真实来源的 issue**：V1 只产出一个推导 issue（`NOT_CANDIDATE_BASE_ADVANCED`，§3.3）；没有的 issue 显式空，不造填充值。

### 3.3 排序、分页、限额

- **排序**（flat list，前端用 `parent` 边自建树；V1 不返回嵌套 JSON，与 5D pagination 同一传输考量）：
  1. `created_at` 升序（UTC 事实成立时刻）；
  2. 同刻 `node_kind` 秩：`BASELINE_NODE < SUBMISSION < SYSTEM_MIGRATION`；
  3. 仍同 `ref_id` UTF-8 字节升序。
- **分页**：`GET /v1/history?limit=&cursor=`。`limit` 默认 100，max 500（P5 §12 把 cursor/page 形状 defer 到本 slice，此处冻结）。响应含 `next_cursor`（opaque base64url，canonical JSON `{order_key, head_version}`，≤1024 字节，不可解析 → 422）。**无 `total`**（全集无界，不做全量冻结）。
- **每页是独立只读快照**：页间 Head 前进可接受；响应头字段 `head{node_id, commit_id, version}` 让客户端检测漂移。跨页不承诺一致性。
- **分页 DB 成本（S1 记录）**：生产页路径 Python 侧节点行与映射为 O(limit)；晋升关系 map 仅查询当前页 submission 的 `source_submission_id`（≤ 页内 submission 数，重复来源在 SQL 侧 `ORDER BY created_at_us, node_id` 后末位写入），不为全 scope 构造完整晋升字典。SQLite 侧 `UNION ALL + ORDER BY + LIMIT` 仍对全 scope history 行排序（无含 `created_at_us` 的索引）→ 单请求 DB 节点扫描成本 O(scope history)，归后续 perf slice，不阻断 S1。
- **读取语义（并发 Review/Archive）**：单请求一个 control DB readonly 快照（`BEGIN`，WAL）；无缓存、无跨请求状态；读到的节点/边/prompt 在同一快照内自洽。Head 并发推进不破坏页内一致性。

### 3.4 SYSTEM_MIGRATION 语义保留（无 consumer 框架不实现）

- `node_kind` 词表含 `SYSTEM_MIGRATION`，projection 解析器**接受**该 kind；V1 **无任何 producer**（P5 §12 把 rule migration 遗留为 deferred；未来真实迁移必须注册为 `SYSTEM_MIGRATION` 业务节点并注册真实 rule 事实）。
- 未来接入规则：迁移注册事实（node 行 + rule 事实）先行，projection 自然派生；**没有注册事实就不该有节点**——解析器禁止从 log/commit 推断。
- 重启/崩溃后的迁移 identity 由持久注册事实背书；V1 不实现迁移执行、回滚或任何 provider。
- **重开条件**：出现实际迁移 producer 时（rule 扩展或 schema 迁移真实启动），先修订 Business Lifecycle / Rule System contract，再在 5E 文档或新 slice 中 open 本语义；当前不预建。

### 3.5 派生 eligibility issue

- 唯一 V1 码：`NOT_CANDIDATE_BASE_ADVANCED` —— `review_status=APPROVED` 的 submission 节点，其 `based_on_baseline_node` 不再指向 current Head（base 已前进）。派生自 5D §3.1 candidate 资格规则，不持久化。
- 其他 issue 码一律不发明；consumer 解析器只接受已列码，未知码 = 数据异常 → `503 HISTORY_INTEGRITY_FAILURE`（§7.2），不静默丢弃。
- **S1 阶段说明**：V1 仅上述单一 producer 存在；「未知 issue 码 → 503」在 S1 无第二 producer 时为**空断言**（不可构造未知码）。S1 以 control DB 行解析损坏（enum/列值非法）证明 `HISTORY_INTEGRITY_FAILURE` 映射可达。

## 4. 授权与 exact commit 绑定

### 4.1 权限与 scope 解析

- 新 permission string **`read_project_history`**（P）：project/device 级独立权限；不被四个现有 permission 隐式授予，admin 可授予。五条 history 路由分两类：前四条（list / compare 发起 / result 读 / bundle 读）消费 `read_project_history`；**`POST …/integrity-ack` 仅** `require_internal_bearer`（E，与 `operator_recovery` 同型，§7.4）——**不**要求 `read_project_history`，**不**发明新 permission 词表。这是对 P5 §7 “Review/Archive/complete History 使用独立 project/device 权限”的实现。
- 每次请求（含 result/bundle 读，**不**依赖 accept 时的权限）：当前 session → transaction-fresh scope 解析 → exact `gateway_device_external_key` / `business_project_id` / `repository_id` → authorize `read_project_history` on that scope。
- caller **不可**发送 RepositoryId / CommitId / actor / device / project / server path；node 永远以 `ref_kind + ref_id` 表达。
- **同 scope 多 actor**（E，§1A.1）：凡持 `read_project_history` 的 actor 可读全 scope 全部 history 节点（含他人 submission）；compare replay 恢复也不限 initiator（§6.2 fingerprint 故意排除 actor_id，与 5D 审计 append 含 actor 的理由不同：那是署名事实，这是只读计算请求）。

### 4.2 node → exact commit 解析（read snapshot）

| ref_kind | 解析链（读快照内） | 失败行为 |
| --- | --- | --- |
| `baseline_node` | `baseline_node_records[node_id]` → 存在 → frozen scope == session scope 且 `repository_id` == session repository | 任一失败 → `404 RESOURCE_NOT_FOUND` |
| `submission` | `submission_records[sub_id]` → 存在 → frozen scope == session scope 且 `repository_id` == session repository → `repository_commit_id` | 同上 |

- compare accept 时**同快照**解析全部 node refs，结果（commit 等）冻结进 job_payload 与 acceptance record（server-owned）；执行不再回读 node 业务事实（materialize 阶段的 integrity gate 只校验 pinned commit 可解析，属 Repository 一致性检查）。
- **404 统一不披露**：不存在与跨 scope 同码同形状；响应不泄露对象存在性。
- **知道 CommitId 不能 bypass**（contract §6）：API 不接受 caller commit；commit 只能由服务端从冻结 scope 的权威事实解析。

### 4.3 改绑 / 撤回 / 历史对象

- **mapping 改绑**（3.0.0 §1A.3 唯一改写入口）：scope 指向新 Repository 后，读旧 Repository 的 history **不**自动获得授权；history 读永远解析“当前 scope 指向的 Repository”。再次读旧 Repository 需要 scope 合法改绑回该 Repository（单 Repository 归属仍成立）。V1 无权限维护、历史改写、或将旧 Repository “接入”新 scope 的读路径。
- **权限撤回**：后续读/发起即时 `403 SCOPE_FORBIDDEN`；在途已 accept 的 operation 不取消（授权在 accept 边界完成，worker 不重新授权，E operation accept/执行语义）；result/bundle 读被拒（403），持久事实不删除。
- **历史对象访问**：已归档/已关闭节点的 commit 恒可读（持权限时），不因 disposition 失去可读性；disposition 只改变候选资格展示。

## 5. History Compare 语义

### 5.1 节点集 → pair / input 映射

| 输入（ordered） | 映射 |
| --- | --- |
| 2 nodes `[A, B]` | 1 pair：`view_kind=HISTORY`，`before=A`，`current=B`；`pair_id = "{operation_id}-p0"` |
| 3 nodes `[A, B, C]` | 2 相邻 pair：`{op}-p0` A→B、`{op}-p1` B→C；bundle `BundleProfile.MULTI_PAIR`，3 个 bundle inputs（display roles `node-0/1/2` = 各自 node ref） |

- 每 pair 的 input 矩阵（E，R5 HISTORY 强制项，经 `bind_pair_input` 既有校验）：`InputCompleteness.FULL`、`ComparisonMode.DETAILED`、`ArtifactScope.ALL_CHANGES`、`IdentityApplicability.NOT_APPLICABLE`。**无自动补全、无顺序修正**：方向恒为 caller 声明的 before→current（`COMPARISON_DIRECTION=BEFORE_TO_CURRENT`）；caller 想反向就反向声明。V1 不强制时间序（无业务状态依赖）。
- 3 节点中间节点只物化一次，两个 pair 复用其 artifact ref（按 distinct commit 去重，§5.3）。
- 重复 node ref（`[A,A]`）或不同 ref 同 commit：合法，同快照 pair → 全表 UNCHANGED / zero row counts（E 已验证），不是错误。

### 5.2 输入冻结与 trusted flow binding

冻结纪律沿用 5D 的 canonical JCS / D-prefix（新 kind 前缀）：

```
D = 'sha256:' + hex_lower(SHA256(UTF8('gateway-vnext:history:' + kind + ':v1') + byte(0) + JCS(payload)))
```

**双层 binding（F1 v3 闭合）**：accept 短事务只能冻结 control DB 可得事实；per-table policy 需要 materialize 后的表名/schema（E `resolve_table_rule`），故拆成两层，各自在可得时点冻结。

| kind | 冻结时点 | payload（完整语义 preimage） | 用途 |
| --- | --- | --- | --- |
| `accept-binding` | accept 事务（§6.2 步 4） | `gateway_device_external_key`、`business_project_id`、`repository_id`、`nodes`（ordered：`{ref_kind, ref_id, commit_id}`）、`table_ruleset_version`、`comparison_contract_version`、`view_kind="HISTORY"`、`pair_count` | `request_fingerprint`、idempotency/replay、409 冲突检测 |
| `compare-binding` | materialize checkpoint 提交后（§5.3 步 1 末） | `accept-binding` 全部字段 **+** `table_policies`（canonical JCS：materialized TableSet union 经冻结 ruleset 公共解析投影的 per-table policy 列表） | R5 `trusted_flow_binding.binding_digest`、assemble 输入、resume 不重派生 |

- **`request_fingerprint` / `idempotency-fingerprint` ≡ D("accept-binding")`**：不含 `table_policies`（accept 时不可得）；replay 仍比对 nodes/scope/ruleset_version，语义与 v2 一致，仅从错误载体移除不可得字段。
- **`trusted_flow_binding.binding_digest` = D("compare-binding")`**：仅在 worker materialize 后可得表清单后写入 checkpoint `job_state.compare_binding_preimage`（`owner_kind: history-compare-checkpoint`，E preview checkpoint 同型）；3 节点的 pair 共享同一 compare-binding digest；R5 只校验存在、shape 与 view_kind 匹配（E）。
- **ruleset 版本纪律**：`table_ruleset_version` 在 accept 冻结；worker 若运行期 ruleset ≠ 冻结值 → 稳定 FAILED（worker 码 `HISTORY_RULESET_VERSION_MISMATCH`，映射 E `MaterializationDiagnosticCode.RULESET_VERSION_MISMATCH`，§7.2/§7.3），**禁止**静默按当前 ruleset 重算 policy；replay accept 时若 ruleset 版本已变 → `409 IDEMPOTENCY_CONFLICT`。
- **idempotency / replay 机制**：既有 acceptance record → 重算入的有序 refs 解析（§4.2 链）→ 与其 durable `nodes_json`（冻结 canonical JCS：refs + commits）+ `request_fingerprint`（accept-binding）比对：入的 ref 集合与冻结集合相等（ref_kind + ref_id + 解析 commit 全等）、当前 session scope == 冻结 scope、当前 `table_ruleset_version` 与冻结值一致、且当前 `read_project_history` 在**当前** scope 上再校验通过 → replay（200，返回既有 operation 的当前状态）。任一不满足（mapping 改绑、权限撤回、同 ref 解析结果变化、ruleset 版本漂移）→ 按 §4.2/§7.2 拒绝（不 replay）。Preimage schema 固定 `v1`；未来若升级 preimage 版本，replay 只认 durable fingerprint：新旧公式对同一逻辑输入算得不一致 → 保守 `409`，不假 replay。
- 信任边界：compare-binding digest 由 R5 形状校验（不重算值）——信任根是 History Application 的冻结事实 + accept 短事务中的 scope/permission 校验（E docstring：R5 故意不签 actor/session）。5E 维持该边界，不把 R5 变成业务授权校验器。

### 5.3 执行流水线（3-step worker job）

1. **`materialize_inputs`**：节点集中每个 distinct commit 调 `materialize_repository_ref`（E 公共入口：exact commit → Snapshot/Summary/TableSet，`pinned_commit_hash` 校验，`FINAL` / `ARTIFACTS_REQUIRED`）。全部 distinct commit materialize 完成后：① union 全部 TableSet 表名 + schema（`primary_key_columns`）；② 校验运行期 `TABLE_RULESET_VERSION` == job 冻结的 `table_ruleset_version`，不等 → 稳定 FAILED（worker 码 `HISTORY_RULESET_VERSION_MISMATCH`）；③ 取冻结 ruleset 快照（V1 = 基线 submit/preview 使用的唯一 migrated ruleset，E `migrated_table_ruleset_snapshot()` + `TABLE_RULESET_VERSION`；V1 单版本前提 §10 b），经 `table_rules` 公共解析（E `resolve_table_rule`）得 per-table 规则，忠实投影为 `ComparisonTablePolicy`（ordered 表 → `OrderedTablePolicy`：从 `ResolvedTableRule.decision` 投影 `order_key` ← `position_column`；`stable_key_candidates` ← 同名列表（canonical tuple，进 compare-binding digest，E `standard.py` policy digest 路径）；`row_identity_key` ← **恰为单候选时**取该列 `("col",)`，**零候选或多候选** → §10 停止线 8（V1 migrated registry 均为单候选 `("gid",)`，与默认 `OrderedTablePolicy` 等价）；`ignored_columns` ← 同名列表；`blank_row_policy=PSEUDO_BLANK_BY_MISSING_STABLE_KEY`；ordered 执行路径以 `row_identity_key` 做单列校验，E `ordered.py`）；keyed 表 → 默认 policy + ruleset 的忽略列/keyless 事实）；④ 构造 `compare-binding` preimage + digest，与 materialize sides refs 一并写入 checkpoint `job_state`（`compare_binding_preimage` + `compare_binding_digest`）。复用 preview checkpoint 模式：materialize 完成即 checkpoint，可从断点 resume。artifact namespace 沿用 `comparison`（E 既有命名空间）。
2. **`assemble_comparison`**：从 materialize checkpoint 读取 `table_policies` + `compare_binding_digest`；**禁止**从 live ruleset 重派生（resume/takeover 与 preview assemble-from-checkpoint 同型，F1 关闭条件）。每 pair `bind_pair_input(HISTORY, table_policies=cached, trusted_flow_binding=…)` → `plan_pair` → `compare_plan` → `publish_records_closure` → `evaluate_risk(V1_RISK_RULE_SPECS, RiskOptions())` → `assemble_surface(ref_scope=OPERATION_RELATIVE)`；随后 `assemble_bundle(ref_scope=BUNDLE_RELATIVE, profile 按 §5.1)`。与 preview pair 流水线同一调用链（E），只 view/persona/binding/policy 不同。History 不计算 pseudo key：pseudo/blank 占位算法留在 capability ordered/standard 执行路径（E）。
3. **`publish_result`**：bundle manifest/closure 落 artifact store → ready_closure 发布 + 短事务终态（E preview publish 模式）。

**“只读”的等价性依据（为什么不是技术 diff 冒充业务 compare）**：

- 业务 comparison 走 R5 标准事实流水线，与 preview/submit 同一算法、同一 digest 域、同一 artifact 闭包；HISTORY 只是 view context（identity NOT_APPLICABLE + trusted binding），`compare_plan` 无 view 分支（E）。per-table policy（ordered/pseudo/keyed）是 trusted table-rules owner 输入（E `ComparisonTablePolicy` docstring：“supplied by the trusted table-rules owner”）：History 在 materialize 后从固定 ruleset 公共解析绑定并冻结进 compare-binding checkpoint，assemble 只读该冻结副本，不从 live ruleset 重派生。**基线事实（F1）**：preview/submit 当前不传 `table_policies`（0 producer，基准核查），即 preview 现按每表默认 policy 运行（keyed、全列含 `no` 参与值比较）；5E History 提供 policy 绑定，使 ordered 表 move-only → `ROW_MOVED` 零内容更新、pseudo/blank → 占位语义成立（实现 Canonical Storage §3 “`no` 不参与普通行内容修改判定”的 ordered 侧）。History 与 preview 在带 policy 表上的差异是 **policy 差异不是算法差异**；回填 preview 链是 preview owner 的账，不在 5E 范围。
- 不使用 Repository native diff / `dolt_schema_diff`（E：non-production-only、schema-only measurement provider），也不用 provider commit row flow、`/log`、技术 parent；全部读经与 preview 相同的 provider 数据面，保证 archive/review/compare 读的是同一业务编码。
- vNext read provider 是单向 read protocol（`B/infrastructure/repository_read/http_arrow.py`），不存在写通道；repository 侧 `dolt_schema_diff`（`vnext/repository_service` measurement provider，E）不是 public route，本设计不接。
- 技术 parent/log 不是 comparison 输入（contract §6：Dolt log 不是业务树）。

### 5.4 输入情形矩阵

| 情形 | 行为 |
| --- | --- |
| 2/3 节点，均可解析 | 正常执行 |
| 重复 node ref / 不同 ref 同 commit | 合法；UNCHANGED / zero row counts（E 验证），非错误 |
| 空 initial（零表 commit） | 5D-S1 initial-empty 门禁通过后，arm/leg 可 materialize 零表快照；空↔空 = UNCHANGED；空↔表 = ADDED_TABLE 全集（5D §2.1 语义，5E 不另分支） |
| 结构不同 table（同名不同列） | capability 既有语义：表级 `DEGRADED`（E 验证），不 crash；非 5E 唯一分支 |
| ordered 表纯 move-only（同 stable-key 集、`no` 值互换） | 有 policy 绑定 → `ROW_MOVED`、零内容更新（E ordered 算法 + `OrderedTablePolicy`，`move_policy=STABLE_KEY_RELATIVE_ORDER_V1`）；不按普通行值变处理 |
| pseudo/blank 行（stable key 缺失） | `BlankRowPolicy.PSEUDO_BLANK_BY_MISSING_STABLE_KEY` 占位语义（E ordered 路径）；占位算法在 capability 层，History 不计算 |
| commit 在 Repository 不可解析（integrity） | materialize 稳定失败 → step FAILED，worker 码 `HISTORY_COMMIT_UNAVAILABLE`（类 a，§6.6）；bounded 诊断，不自动修复、不静默跳过 |
| 节点集含未识别 kind | 请求层 422；projection 解析器只接受已列 kind（§3.1） |
| admission DRAINING / 关闭 | `409` / `503`（E 既有 admission-first 机制；Operation Lifecycle §1 已列 history compare 为 DRAINING 拒收对象） |
| 跨 projection ruleset version 的两节点 | V1 不做；materialize 失败（稳定码），§10 重开条件 |

## 6. Operation、持久化与资源边界

### 6.1 identity 与步骤

- `job_kind = backend-vnext/history-compare`（E 正则 `^[A-Za-z0-9._:/-]{1,128}$`）；job contract `backend-vnext/history-compare/v1`；3 个 step：`materialize_inputs → assemble_comparison → publish_result`。
- decoder/handler identity：`backend-vnext/history-compare/{step}/decoder|handler/v1`；三 step 全部 `PURE_RECOMPUTE`（从冻结 commit + artifact ref 纯计算，E preview 模式）；terminal 发布能力 TERMINAL。
- **cancel** 走 E 既有协作边界；**无 supersede**——compare 无 “current 指针”、无 generation，每次 accept 独立，不会进入 SUPERSEDED 路径。
- `business_refs = [("history_compare", acceptance_id)]`（E business_ref kind 模式，`^[A-Za-z0-9._:/-]{1,255}$`）。

### 6.2 accept 事务（短、单一写、有序）

事务步骤顺序反映 preview accept 与 5D §5.1 的纪律；事务内不做 Repository I/O：

1. HTTP 严格 shape/size 校验；当前 session + `read_project_history` + `acquire_new_work(admission)`（E）。
2. 单 control DB 事务：transaction-fresh scope 解析，冻结 exact `device / project / repository`。
3. **Idempotency 先行（先解析后比对，同一快照内）**：按 `(scope, idempotency_key)` 查 acceptance；既有 record → 按 §4.2 解析入的 node refs → 与记录冻结集合（durable `nodes_json`：ref_kind + ref_id + commit 全等）比对：相等 且 当前 session scope == 冻结 scope 且 当前 `table_ruleset_version` 与冻结值一致 且 当前 `read_project_history` 再验证通过 → **replay**（200 既有 `operation_id` + 当前 status，**早于** integrity 门禁与插入）；不等 → 按 §4.2/§7.2 拒绝（跨 scope/不可解析 → 404 不披露；权限撤回 → 403；冻结集合不相等，含同 ref 不同解析结果或 **ruleset 版本漂移** → `409 IDEMPOTENCY_CONFLICT`）。**replay 路径不执行步 5。**
4. 无既有 record（新动作）：解析全部 node refs（同快照）→ 计算 §5.2 `accept-binding`（含 `table_ruleset_version`，**不含** `table_policies`）→ 确定性 ID：
   - `preimage_id = JCS({"kind": "history-compare-operation-id", "v": 1, "gateway_device_external_key": …, "business_project_id": …, "idempotency_key": …})`（canonical JSON **object**，named keys；JCS 纪律同 §5.2 D）
   - `operation_id = "op-" + sha256(UTF8(preimage_id))[:24]`；`acceptance_id = "hca-" + sha256(UTF8(preimage_id))[:24]`（hex 截断）；acceptance record 存同一 preimage。元组各字段是不同 JSON key 下的字符串值，`("dev:a","p","k")` 与 `("dev","a:p","k")` 不再碰撞（原版本冒号拼接字符串存在该碰撞，审核 F4）。
5. **integrity 门禁（仅新动作）**：对 nodes 中每个 resolved `commit_id`，查 scope 内 `acknowledgement_status=PENDING` 的 integrity record（`repository_id` + `commit_id` 匹配，§6.6）→ 任一命中 → `409 HISTORY_INTEGRITY_UNRESOLVED`（§7.2），**不**插入 acceptance/operation。
6. **单事务原子插入**：acceptance record + `OperationRecord(QUEUED)` + 初始 `StepRecord`（E `insert_operation_with_initial_step`）→ 提交成功后 `202` **`HistoryCompareAcceptResponse { operation_id, status: "QUEUED", replayed: false }`**（新 DTO，§7.1；E `OperationAcceptedResponse` 是 preview/submit 专属形状 `{operation_id, workspace_id, upload_revision_id, generation, status}`，E `schemas/preview.py:25–33`，history 无 workspace 概念不可构造——审核 F3）。replay 返回 `200` 同 DTO 形状，`status` = operation **当前**状态、`replayed: true`。
7. 失败全部回滚；key 不占用、无 partial prefix。Key 只有 submit 后已认领（E idempotency 语义同理）。

### 6.3 “只读”保证与事务纪律

- **只读** = 不改 workspace/submission/review/baseline/archive/mapping 任何业务行，不调 Repository 写接口，不移 main、不产 commit、不 import。
- **写入闭包**：仅 `history_compare_acceptance_records`、`history_compare_integrity_records`（类 c 才写，§6.6）、operation/step 记录（E 既有 runtime）、artifact store（结果 bundle + 中间 artifact + compare-binding checkpoint）、artifact protection（P 新 `owner_kind`：`history-compare-operation` / `history-compare-checkpoint`；E `set_artifact_protection(refs, owner_kind, owner_id, intent)` 模式，preview 先例 `preview-checkpoint`）。
- **短事务纪律**：accept 事务只读写 control DB 事实（SQLite），不做 Repository I/O、不长计算；publish step 是 artifact ref 发布 + 短事务终态；materialize 全部 Repository 流式读在 worker step 1，不在任何业务事务内。
- **证明**（执行计划 S3 门禁）：e2e 前后对 submission/review/baseline/archive/workspace 行集合做 checksum 不变断言；Repository commit 集合不变（无新 commit）；compare 永不 import。

### 6.4 存储与资源上限

新表（A 类执行事实；workspace schema **v6**，基于 5D 最终 v5——若 5D 最终占用了邻接版本号，S1 对齐门重排，本文不复用 v5）：

```
history_compare_acceptance_records
  acceptance_id            PK (hca-…，24 hex char)
  gateway_device_external_key   TEXT NOT NULL
  business_project_id           TEXT NOT NULL
  repository_id                   TEXT NOT NULL
  idempotency_key    TEXT NOT NULL  -- UNIQUE(gateway_device_external_key, business_project_id, idempotency_key)
  request_fingerprint TEXT NOT NULL  -- D("accept-binding")
  table_ruleset_version TEXT NOT NULL  -- 冻结 ruleset identity（accept 时可得）
  nodes_json         TEXT NOT NULL  -- 有序 node refs + resolved commits，canonical JCS
  operation_id       TEXT NOT NULL UNIQUE → operation_records
  created_at         TEXT NOT NULL

history_compare_integrity_records  -- 类 (c) 才创建；1 operation : 0..1 incident（F5 v3 闭合）
  incident_id        PK (hci-…，24 hex char)
  operation_id       TEXT NOT NULL UNIQUE → operation_records
  repository_id      TEXT NOT NULL
  commit_refs_json   TEXT NOT NULL  -- bounded：[{commit_id, ref_kind?, ref_id?}]
  failure_class      TEXT NOT NULL  -- 固定 HISTORY_REPOSITORY_INTEGRITY
  expected_digest    TEXT NOT NULL  -- DigestRef.value（§6.6：summary/声明侧）
  observed_digest    TEXT NOT NULL  -- DigestRef.value（§6.6：读回/重算侧）
  affected_tables_json TEXT NOT NULL  -- bounded 表名列表
  recommended_action TEXT NOT NULL  -- V1 固定 OPERATOR_REVIEW_REQUIRED
  first_seen_at      TEXT NOT NULL
  last_seen_at       TEXT NOT NULL
  acknowledgement_status TEXT NOT NULL  -- PENDING | ACKNOWLEDGED
  resolution_reference TEXT NULL  -- nullable opaque 1..255
  created_at         TEXT NOT NULL
  updated_at         TEXT NOT NULL
```

- **分类与保留**（比例化）：acceptance = **A**（replay 权威，单事务无 partial，误 accept = 误 replay，由 accept-binding fingerprint + 短事务内置处置）。integrity record = **A**（Operation Lifecycle §4 等价 control record；不进入普通 artifact cleanup；保留至 ack + `resolution_reference` 写入 + operator archive）。projection / `eligibility_note` / 结果 artifact = **C**（派生，可从冻结输入重算，无强持久化要求，无专为投影建的表）。结果权威读 = operation record + result ref（A，durable）；artifact bytes = C 类派生缓存（按需取、digest 校验；missing = 稳定错误 `ARTIFACT_UNAVAILABLE`，不 fake-ready）。compare-binding checkpoint（含 `table_policies` 正文）= C 类派生缓存（可从 materialized commits + 冻结 ruleset 重算，但 resume 只读 checkpoint 不重派生）。FAILED / CANCELLED 终态：operation 终态落库后 owner 释放保护（E `clear_artifact_protection(owner_kind, owner_id)` 模式，preview/submit 先例），走 E bounded TTL 协作清理（ADR 0012）；SUCCEEDED 结果 artifact 与 operation record 共存；V1 **不建二级 GC/refcount 状态机**（P5 §9 已明确）。各 A 类记录的保留语义不可互相替代。
- **`table_policies` 承载与预算**：正文存 materialize checkpoint artifact（`job_state.compare_binding_preimage`，JCS）；acceptance 表与 inline `job_payload` **不存** policy 列表。policy 列表大小由 distinct commit 表数 × 单表 policy JCS 上界约束，走 checkpoint artifact 预算而非 inline payload。
- `inline job_payload ≤ 64 KiB`（E operation contract §6.4 预算）：payload 只有 scope、node refs、commits、accept-binding digest、`table_ruleset_version`、comparison contract version，远低于上限。
- 不新增任务平台、outbox、持久执行状态或对账表（integrity record 是窄域 A 类 control 事实，非 incident 平台）。

### 6.5 恢复与重启

- Worker 重启：E 既有 durable runtime 的 claim/takeover/checkpoint resume 覆盖 compare job；`PURE_RECOMPUTE` 保证 resume 不依赖进程内状态。
- Startup reconcile：当初 launch 载入 queued operation 的既有 E 路径；compare job 与 preview job 同一入口，无独立 reconcile verb。
- `process exits before commit` → SQLite 回滚；`response lost after commit` → 原 key retry 命中 replay（E 模式）。
- 无 retry 拓扑、无 supersede、无 final-failure owner 变更（纯计算，无外部 effect）。

### 6.6 integrity 边界（比例化决定，三分法）

materialize 读回失败先分类再处置。原版本 “V1 无 delete/rewrite 能力故无 incident 触发源” 的论据**撤回**（审核 F5：I/O 失败、corruption、恢复不一致不需要删除 API；“既有 Repository-side owner” 在基线 vnext/** 无 production 实现，穷举核查确认）：

| 类 | 定义 | 处置 |
| --- | --- | --- |
| (a) 瞬时依赖不可用 | Repository service 不可用 / 超时 / I/O 失败，commit 内容本身未经验证 | step FAILED，worker 码 `HISTORY_COMMIT_UNAVAILABLE`（§7.2/§7.3）+ bounded 诊断 + metric；operation FAILED；用户 re-accept 重算；无 durable incident |
| (b) 可重建 artifact 缺失 | SUCCEEDED 后 bundle bytes 丢失 / protection 混淆 | 读侧 digest 校验失败或直接 missing → HTTP `ARTIFACT_UNAVAILABLE`（§7.2）；处置是人工有界诊断，不自动重建 bytes |
| (c) 已确认权威事实异常 | 同一 exact commit 经 §6.6 确认程序判定为可复现的内容矛盾 | 同一短事务：operation 终态 FAILED（worker 码 `HISTORY_REPOSITORY_INTEGRITY`）+ 创建 `history_compare_integrity_records` 行（§6.4）；不发布 result、不自动修复、不静默跳过 |

**两层判断（F5 v3.6）**：**确认条件**（是否升类 (c)）与 **字段映射**（incident 写入哪一次观测的公开事实）**显式分离**。确认不要求两次 `observed` 相同；不因读回值 B→C 变化而降级。**禁止**用失败诊断哈希冒充内容摘要（v3.2–v3.4 方案废止）。

**类 (c) 触发与确认程序**：

1. **E 码 → 类 (c) 候选**（`materialize_repository_ref` 内 hidden summary 交叉校验失败；E `MaterializationDiagnosticCode`，`repository_ref.py` hidden summary 自洽与 catalog vs summary / row digest vs summary / catalog 缺表路径）：
   - `HIDDEN_SUMMARY_CORRUPT`
   - `HIDDEN_SUMMARY_DIGEST_MISMATCH`
2. **确认程序（bounded）**：首次失败后，对**同一 exact commit** 做 **1 次** bounded 重读（复用 `materialize_repository_ref`，新 session；不无限重试）。`first_diagnostic` / `second_diagnostic` = 各次 FAILED 中 `code ∈` 候选集的那条（E `_with_diagnostic` 附加诊断忽略）。
   - **升 (c)**：两次均为同一候选 E 码；且**各自**完成 mismatch 证明（内容轨或结构轨，见下）；第二次非成功、非排除/默认码。
   - **降 (a)**：第二次成功；变为排除/默认码；**或**第二次不再是候选码。**不因** `observed_digest_ref` 从 B 变 C 而降级。
3. **明确排除（永不升 (c)）**：`RULESET_VERSION_MISMATCH`、`REPOSITORY_REF_*` 超时/不可用、`MATERIALIZATION_TIMEOUT`、`REPOSITORY_CATALOG_LOAD_FAILED` 等瞬时/依赖类码 → 类 (a)。
4. **默认归属**：未列入候选或排除清单的 `MaterializationDiagnosticCode`（如 `HIDDEN_SUMMARY_MISSING`、`ARTIFACT_*`、`REPOSITORY_TABLE_READ_FAILED`、`DUPLICATE_EFFECTIVE_KEY` 等）**一律类 (a)**，永不升 (c)。

**证据轨 A — 内容 mismatch（有 content digest pair）**：`MaterializationDiagnostic` 携带非空 `expected_digest_ref` 与 `observed_digest_ref`（summary/声明侧 vs 读回/重算侧）。**升 (c) 条件**：`second.code == first.code`；`second.expected_digest_ref == first.expected_digest_ref`（声明侧稳定）；两次 `observed_digest_ref ≠ expected_digest_ref`。**不要求** `second.observed_digest_ref == first.observed_digest_ref`。

**证据轨 B — 结构 mismatch（无 content digest pair）**：候选码触发但无 content pair（如 `repository_ref.py:413–417` catalog 缺表）。走 materialization 公开的**结构 mismatch 事实**（S2 同批交付：`expected_digest_ref`/`observed_digest_ref` 承载「声明存在 vs 观测缺失」等有界 `DigestRef`，**非** row content digest）。**升 (c) 条件**：两次同候选码且两次结构事实引用全等。**已确认的结构矛盾不得因缺 content pair 归 (a)**。

**轨 B 可判定规则（S2 exit 勘误）**：结构轨标签集合与 `repository_ref.py` `_select_hidden_tables` halt 点对齐：

- `catalog-table:missing`
- `catalog-table:{table}`
- `hidden-summary-table:missing:{table}`

其余 `expected_digest_ref`/`observed_digest_ref`（含 `hidden-summary-stage:*`、`hidden-row-count:*` / `catalog-row-count:*` 于 `repository_ref.py:388–396`）→ **内容轨**，允许 observed 漂移。实现引用：`compare_jobs.py::_is_structural_integrity_diagnostic`（S2 双轨 `_integrity_confirmed` 消费方）。若后续新增 halt 点，再评估是否引入 `digest_pair_kind` 等显式字段（方案 b）。

**`expected_digest` / `observed_digest` 字段映射（F5 v3.5/v3.6，§8.3 选项 1）**：Operation Lifecycle §4 要求两侧为 materialization 公开的 `DigestRef` 引用。History **只投影**，不重算、不复制 `_digest.py`。

**S2 阶段内交付（materialization owner，窄预算）**：扩展 `MaterializationDiagnostic`（`B/capabilities/snapshot_materialization/contracts.py`）增可选 `expected_digest_ref`/`observed_digest_ref`；在 `repository_ref.py` 类 (c) 相关 `_Halt` 点填充 content pair 或结构事实 pair。History consumer 在该公开面就绪后接线。

- **incident 映射（确认后）**：`expected_digest`/`observed_digest` = **首次** diagnostic 的 `expected_digest_ref.value` / `observed_digest_ref.value`（`DigestRef` 线格式 `sha256:`+64 hex）。`first_seen_at`/`last_seen_at` 覆盖两次观测窗口；复读仅作确认，不要求 `observed` 稳定。
- `affected_tables_json` = 两次用于确认的 diagnostic 的 `table` 并集（去重、bounded）；无 `table` 时 `[]`。
- **代表场景（`test_history_compare_integrity.py` 共享参数表，§8）**：
  - `content_stable`：声明 A，两次读回均为 B≠A → incident(A,B)。
  - `content_drifting`：声明 A，首次 B≠A、复读 C≠A（B≠C）、同码 → **仍类 (c)**，incident 存首次 (A,B)。
  - `structural_no_content_pair`：catalog 缺表类，两次同结构事实 → incident（结构映射）。
- S2 **阶段内**若 materialization 无法为已知 halt 点提供公开事实 → **§10 停止线 9**（停该轨回设计，非整体返工）；不得以 History 侧变通替代。

**Operation Lifecycle §4 等价 control record（F5 骨架闭合，字段映射 S2 前置）**：类 (c) 的权威事实载体是 `history_compare_integrity_records`（A 类 durable control record，对齐 ADR 0016 “现有 control metadata 足够”）。字段逐项映射 §4：`incident_id`、`repository_id`/`operation_id`、`failure_class`、`expected_digest`/`observed_digest`、`affected_tables`、`recommended_action`、`first_seen_at`/`last_seen_at`、`acknowledgement_status`、`resolution_reference`。`OperationDiagnostic`（E `code`/`message`）仅承载 bounded 用户可见摘要（`HISTORY_REPOSITORY_INTEGRITY` + 短 message 含 `incident_id`），**不是**权威事实载体；终态 operation/step 记录不可原地更新 ack/resolution。

**Compare 门禁**：scope 内存在 `acknowledgement_status=PENDING` 且涉及相同 `repository_id`+`commit_id` 的 integrity record 时，新 compare accept 若节点集含该 commit → `409 HISTORY_INTEGRITY_UNRESOLVED`（§7.2）；已 SUCCEEDED 的历史 result 只读不受影响。

**Ack/resolution**：经 `POST /v1/history-compares/{operation_id}/integrity-ack`（§7.1，**仅** `require_internal_bearer`）写入 `acknowledgement_status=ACKNOWLEDGED` + `resolution_reference`；响应返回完整 incident 块（operator 可通过日志/metrics/`incident_id` 定位，不要求必先走 user session GET）。不原地改 operation/step 终态。幂等：已 ACK 且相同 `resolution_reference` → 200；变更 resolution → 409。

## 7. HTTP 与 production wiring

### 7.1 路由 / DTO（proposed v1，冻结）

五路由；前四条共用 `read_project_history` + fresh scope 解析；integrity-ack **仅** `require_internal_bearer`（E `http/auth.py`，与 `operator_recovery` 同型）；body/DTO 走 E 既有 byte-constraint 公共类型（ID 1..255、digest 固定形状，与 5D §3.3 同款）；`body ≤ 256 KiB`。

| 路由 | 请求 | 响应（200 系） |
| --- | --- | --- |
| `GET /v1/history` | query `limit`(默认 100，max 500)、`cursor`(opaque ≤1024B) | `200` `{ head: {node_id, commit_id, version}, nodes: HistoryNode[], next_cursor: string \| null }` |
| `POST /v1/history-compares` | header `Idempotency-Key`（E 1..255，opaque，不施加 grammar）；body `{ nodes: [ {ref_kind, ref_id}, ×2..3 ] }`（ordered，拒绝重复 JSON key；重复 node ref `[A,A]` 合法） | `202` `HistoryCompareAcceptResponse { operation_id, status: "QUEUED", replayed: false }`；replay `200` `{ operation_id, status: <当前状态>, replayed: true }`（新 DTO，P `schemas/history.py`，`extra="forbid"` 纪律同 preview DTO） |
| `GET /v1/history-compares/{operation_id}` | —（路径参数 E 约束） | `200` `{ operation_id, status, diagnostic?: {code, message}, integrity_incident?: IntegrityIncident, result? }`；`integrity_incident` 仅 FAILED + 类 (c)（§6.6 全部 §4 字段，camelCase mapper）；`result` 仅 SUCCEEDED：`{ input: {nodes, commits[]}, pairs: [{pair_id, before_ref, before_commit, current_ref, current_commit, comparison_digest, risk_digest, surface_digest, record_count}], bundle_digest, completed_at }` |
| `GET /v1/history-compares/{operation_id}/bundle` | — | `200` `StreamingResponse` octet-stream；`Content-Disposition: attachment; filename="history-compare-{operation_id}.bundle"`（E `StreamingResponse` + adapter 模式） |
| `POST /v1/history-compares/{operation_id}/integrity-ack` | header internal bearer（E `require_internal_bearer`）；body `{ acknowledgement_status: "ACKNOWLEDGED", resolution_reference: string }`（1..255 opaque） | `200` `{ incident_id, acknowledgement_status, resolution_reference, …incident 全字段 }`；已 ACK 同 resolution → 200 幂等；变更 resolution → 409；无 bearer → 401 |

- `HistoryNode` HTTP 形状 = §3.2（字段定义与 DTO 校验在 `B/http/schemas/history.py`，snake_case 键名，与 E preview/archive 先例一致）。
- **pending vs terminal**：pending 返回 `{operation_id, status: QUEUED|RUNNING, step?}`；worker 不重新授权（授权在 accept 边界完成，E operation accept/执行语义），HTTP 读侧每次重新 authorize。
- **generic operation read**（`GET /v1/operations/{id}`，E）：授权按 job kind 分派——先加载 operation record：preview/submit 行为不变（现行 `workspace_read` + `authorize_operation_read`，E）；`job_kind == backend-vnext/history-compare` **不要求 `workspace_read`**，改由 acceptance record 再授权 scope + `read_project_history`（无 record / 跨 scope → 404 不披露）；FAILED + 类 (c) 时透传 `integrity_incident` 同形。实现面：`B/http/routes/operations.py` 的授权入口按 job kind 分派（现状 `assert_workspace_read_permission` 无条件前置，history-only actor 会在该路由 403——审核 F3），preview 路径行为零变化。读 incident 走 `read_project_history`；ack 走 internal bearer（§7.4），读/ack 分离。

### 7.2 稳定错误映射（5D §8.2 同款纪律）

| HTTP | code | 触发 |
| --- | --- | --- |
| 401 | `AUTHENTICATION_REQUIRED` | 无 session / 认证失败（E） |
| 403 | `SCOPE_FORBIDDEN` | 无 `read_project_history`（含当前时点 session 权限不足）；scope 未解析 / mapping 缺失（无法建立授权边界，不披露对象存在性） |
| 404 | `RESOURCE_NOT_FOUND`；`ARTIFACT_UNAVAILABLE` | 授权 scope 内无此 node / operation / result；跨 scope 引用一律 `RESOURCE_NOT_FOUND`；SUCCEEDED 后 bundle bytes 缺失或 digest 校验失败 → `ARTIFACT_UNAVAILABLE`（不把终态成功改写为失败） |
| 409 | `IDEMPOTENCY_CONFLICT`；`ADMISSION_CONFLICT`（E）；`HISTORY_INTEGRITY_UNRESOLVED` | 同 key 不同 accept-binding fingerprint（含 durable `repository_id` 与当前 scope 改绑 → `HistoryCompareBindingConflict`，在节点解析前检查，`compare.py`；不因节点是否仍可解析而分化 409/404；`test_history_compare_transactions.py` replay 改绑用例）；admission 冲突；未 ack 的 integrity incident 阻塞含相同 commit 的新 accept |
| 422 | `REQUEST_VALIDATION_FAILED` | node 数 ≠2..3、未知 `ref_kind`、重复 JSON key、cursor 不可解析、shape/byte 超限 |
| 413 | `REQUEST_TOO_LARGE` | body > 256 KiB（E） |
| 429 | `ADMISSION_LIMIT_REACHED` | E |
| 503 | `SERVICE_NOT_READY` / `DEPENDENCY_UNAVAILABLE`（E 既有：registry 未 ready / admin close / control DB busy）；`HISTORY_INTEGRITY_FAILURE` | 本地事实不一致 / 未识别 issue 码 / 依赖不可用；bounded 诊断，不自动修复 |

**History 稳定码分层（R4 v3.1）**：上表为 History **HTTP 新增 3 码**（`ARTIFACT_UNAVAILABLE`、`HISTORY_INTEGRITY_UNRESOLVED`、`HISTORY_INTEGRITY_FAILURE`），登记于 `http/errors.py`。下列 **worker/job contract 码**登记于 `B/application/history/contracts.py` `HistoryCompareDiagnosticCode`，**无**对应 HTTP 行：

| Worker 码 | 类 | 映射 / 用途 |
| --- | --- | --- |
| `HISTORY_COMMIT_UNAVAILABLE` | (a) | 瞬时/未确认类 materialize 失败 |
| `HISTORY_REPOSITORY_INTEGRITY` | (c) | 经 §6.6 确认程序判定 |
| `HISTORY_RULESET_VERSION_MISMATCH` | (a) | 映射 E `MaterializationDiagnosticCode.RULESET_VERSION_MISMATCH` |

### 7.3 production wiring 缝（精确到文件）

| 缝 | 动作（P） |
| --- | --- |
| 新模块 | `B/application/history/{__init__.py, contracts.py, projection.py, compare.py, compare_jobs.py, compare_registry.py}`（`contracts.py` 含 `HistoryCompareDiagnosticCode` worker 码枚举 + E `MaterializationDiagnosticCode` 映射注释）；`B/http/routes/history.py`（5 路由，单 router 文件；integrity-ack 挂 `Depends(require_internal_bearer)`）；`B/http/schemas/history.py`；`B/http/orchestration/history_read.py`、`history_compare.py`（accept）、`history_integrity.py`（ack，复用 `get_workspace_http`）；`B/infrastructure/control_db/sqlite_history.py`（history 读查询 + acceptance/integrity 写 port） |
| `B/http/dependencies.py` | 新增窄 `HistoryHttpDependencies`（scope_resolution、history read port、compare acceptance reader、admission_gate、bundle reader、artifact_store 引用、now…），fail-closed 默认；**不扩进 common context**（5D §7 “窄依赖”同原则） |
| `B/http/runtime.py` | 生产 factory 绑定 `HistoryHttpDependencies`；`build_workspace_job_registry` 注册 history 定义；`assert_workspace_registry_ready` 追加 history job + worker readiness 断言（worker `run()` 与 readyz 同入口，E 模式） |
| `B/http/wiring.py` | `register_workspace_http` 挂 history router；`PRODUCTION_OPENAPI_PATHS` 追加 5 路由（E `test_http_openapi` frozen set 同步） |
| `B/http/errors.py` | 追加 History HTTP 3 码稳定映射：`HISTORY_INTEGRITY_FAILURE`、`ARTIFACT_UNAVAILABLE`、`HISTORY_INTEGRITY_UNRESOLVED`（§7.2）；worker 码不在此登记 |
| `B/infrastructure/control_db/migrations.py` | workspace schema v6：建 `history_compare_acceptance_records` + `history_compare_integrity_records`（仅 S2 阶段；S1 只读查询无 DDL）。**v6 是最终一次性版本，不二次复用**（5D S1 同规则） |
| `B/infrastructure/control_db/database.py` | UoW 增 history 读/写成员（与 E UoW 同型） |
| `B/http/orchestration/operation_scope.py` | `authorize_operation_read` 增 `history_compare` business_ref 分支（§7.1 generic read） |
| `B/http/routes/operations.py` | 授权入口按 job kind 分派（§7.1 generic read）；preview/submit 路径行为不变，E `test_operation_http.py` 增量覆盖 |
| `B/bootstrap/operation_worker.py` | 组装 `history_compare_composition_bundle`（definitions/handlers/decoders），与 preview bundle 并列 |
| `vnext/deploy/config/session.json` | example 显式列出 `read_project_history`（**不**自动授予；5D §8.3 同纪律） |
| readiness/shutdown | 新增 `/readyz` 维度不改变（E：readyz = app.state.ready = registry 完整）；shutdown admission-first 天然覆盖 compare accept（E `submit_workspace` / `accept_submission` 同款）；读路由允许读到进程停 |

### 7.4 部署与授权

- `read_project_history` 由部署方在真实 session 文件按角色配置；example 只列名不授予。
- **integrity ack 授权（V1 冻结，R2 v3.1）**：`POST …/integrity-ack` **仅** `require_internal_bearer`（E `http/auth.py` + `WorkspaceHttpDependencies.internal_bearer_port`，与 `B/http/routes/operator_recovery.py` 同型）。部署方配置 `GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE`（compose/e2e 先例见 `tests/support/runtime_settings.py`）。**不是** `session.json` permission；普通 `read_project_history` actor 不能 ack。
- **镜像重建触发**：S2 触碰 `runtime.py` / `operation_worker.py` / `wiring.py` / `dependencies.py`（production wiring），S3 触碰 `session.json` 与（如有必要）`deploy/compose.yaml` —— 按 AGENTS 规则，该轮最终 HEAD 必须 fresh 构建并跑容器门禁；证据记录格式沿用 5D §6.3（`.Image`、image ID、revision/source-tree sha、Compose config digest、五锁 digest）。

## 8. 测试归属（唯一 owner 表）

T = `vnext/backend/tests/`。一个行为不变量只有一个 owner；其他层最多冒烟。HTTP 与 Application 共享参数表（不复制 5D 矩阵）。

| 行为不变量 | 唯一 owner（新文件粗体） | 环境 |
| --- | --- | --- |
| 节点 shape / 父边 / promotion link / 同 commit 双身份 / 排除不变量（失败 import 等不在列表） | **`test_history_projection.py`** | 纯 SQLite（control DB fact 构造，无 Dolt） |
| 排序确定性 / cursor / limit / 页内快照 / head 漂移字段 / 未识别 issue 码 → 503 | **`test_history_projection.py`** | 纯 SQLite |
| 2/3 节点映射 / 相邻 pair / distinct-commit 去重物化 / **table policy 绑定正确性（带 policy 的 move-only → `ROW_MOVED` 零内容更新 / pseudo-blank 占位 / keyed 按 policy 忽略列；≡ capability owner 同 policy 本地 oracle，复用 E `T/test_comparison_ordered.py` 场景参数，不复制矩阵）** / **compare-binding 在 materialize checkpoint 冻结、assemble resume 不重派生** / checkpoint resume / PURE_RECOMPUTE / cancel 边界 | **`test_history_compare_jobs.py`** | provider 用既有只读测试双（E repo provider test 模式）；**禁止** per-test `dolt init` |
| accept 有序 / replay 早于业务检查（含改绑/撤回/解析不一致/ruleset 版本漂移不 replay；**replay 不受 PENDING incident 阻塞**）/ **accept-binding fingerprint 不含 table_policies** / **新 accept 被 PENDING incident 拒绝（§6.2 步 5）** / fingerprint 异 → 409 / 异 key 独立 / **preimage-id 确定性与分隔符不碰撞** / 零业务写 | **`test_history_compare_transactions.py`** | 真实 SQLite 文件；2 连接并发代表点（AGENTS serial 纪律如需） |
| **类 (c) integrity：§6.6 确认/映射分离 + 三场景参数表（`content_stable` / `content_drifting` / `structural_no_content_pair`）/ GET 可读 + internal-bearer ack 闭环；未 ack 时同 commit 新 accept → 409** | **`test_history_compare_integrity.py`** | 真实 SQLite + provider harness（materialization 公开面）；三场景为唯一 owner |
| node 解析 / 跨 scope 404 不披露 / 改绑 / 权限撤回矩阵 / 5 路由 DTO+byte 限额+错误映射（含 `ARTIFACT_UNAVAILABLE` / `HISTORY_INTEGRITY_UNRESOLVED`）/ result 读再授权 / bundle 流式读 / pending vs terminal / **history-only actor generic operation read / integrity_incident** / **integrity-ack internal bearer（`runtime_settings` helper）** | **`test_history_http.py`** | app-level，无 Dolt |
| HISTORY 执行事实（UNCHANGED / DEGRADED / ADD_TABLES / zeronum）/ **带 policy 的 ordered move-only `ROW_MOVED` 零内容更新 / pseudo-blank 占位语义** | E `test_comparison_standard.py` / `test_comparison_planning.py` / `test_comparison_ordered.py` 增量 | capability owner，5E 不复制（policy 绑定集成代表点在 Application/`test_history_compare_jobs.py`，F1 关闭条件） |
| generic operation readback 经 acceptance 授权 | E `test_operation_http.py` 增量 | app-level |
| DRAINING 拒收 compare accept（进程级） | E `test_http_admission_shutdown.py` 增量（如需要则 `serial` marker） | 进程级 |
| OpenAPI frozen set 含 5 新路由 | E `test_http_openapi.py` | 静态 |
| 生产 factory 依赖 / registry readiness | E `test_production_wiring.py`、E `test_backend_readiness.py` | 静态 |
| import 边界 / FORBIDDEN 前缀 / owner 集合不变（无新 capability owner、无 `history-` artifact 前缀） | E `test_architecture.py` | 静态 |
| 正式入口 History→Compare→Result/Bundle journey + 零业务写证据 + Repository 无新 commit + 重启后 Head/facts 不变 + **零表腿（kickoff gate 已重核 5D 证据，必跑项）** + **实际 Repository 远端读 ≡ capability 同 policy 本地 oracle 的语义比较（“remote-vs-local oracle”，implementation-stages:622 的 5E 落位）** | **`test_history_compose_e2e.py`** | 真实 dolt，`@pytest.mark.integration` |

- **纯逻辑/SQLite（无 Dolt）**：projection、transaction、HTTP、jobs 单元（provider 双）。**真实 Repository / 容器**：仅 `test_history_compose_e2e.py`；其零表腿是必跑项（5D initial-empty 门禁证据在 kickoff gate 重核，§9；缺失 → 停 S1 kickoff，不 stage 内 deferred）。
- Backend 单进程：时序/进程相关测试 `serial` marker，不加 xdist（E 规则）。
- 同构用例模块级共享参数表：node ref byte 边界（ASCII / CJK / 4-byte 255 / 256 越界）、idempotency 同 key 突变（改 node 顺序 / 改 ref / 重复）、auth 矩阵。
- 不为纯解析/校验/类型映射逻辑引入任何执行 `dolt init` 的 fixture（AGENTS 红线）。

## 9. 5D 依赖与对齐

| 5E 消费 | 5D 交付位置 | 5E 需要的形态 | 对齐点 |
| --- | --- | --- | --- |
| `baseline_node_records`（INITIAL/ARCHIVED、`parent_node_id`、`source_submission_id`、frozen scope、`created_at`） | 5D-S1 migration v5 | 表（D）+ `BaselineHeadReadPort`（E 已存在，`B/domain/workspace/ports.py`；权威落位 = 5D-S1 `baseline_head_records`） | **5E-S1 kickoff 重核**：实际表名/port 签名 vs 5D 最终代码；若 5D 最终实现偏离 accepted 设计表形 → 先修订本文 §3/§4，再实现 |
| `baseline_head_records` 与 Head seed 不变量（不回退） | 5D-S1 | Head 只读 | 同上 |
| `archive_disposition_records` + result 子级闭包 | 5D-S2 | disposition 只读 + 覆盖性校验 | 5E-S1 |
| Review 闭包事实（archived 后 disposition 锁定） | 5D-S2 | 节点 review/disposition 一致的读 | 5E-S1 |
| submission `repository_commit_id` 业务列 | 5D-S1 | node→commit 解析源 | 5E-S1 |
| workspace v5 终态（Head 权威离开 mapping） | 5D-S1/S2, S3 收尾 | 5E v6 基于 v5，**不**基于 v4 | 5E-S1：schema 版本号邻接性重核（若重叠重排 v6+） |
| initial-empty 链路修正（零表 materialize/compare/digest 一致） | 5D-S1 门禁 | compose 旅程含零表 baseline 节点（**必跑项**） | **5E kickoff gate（S0→S1）**：5D-S1 门禁 pass 证据 + 5D 零表 compose 旅程证据齐备 → S1 kickoff；任一缺 → **停止 S1 kickoff，无 stage 内 deferred 分支**（S3 零表腿届时按冻结输入实跑）（审核 F6） |
| `archive_submission` 权限 + 7 archive routes | 5D-S3 | compose 旅程的 archive 前置 | 5E-S3 |
| `p5_5d_compose` 真实 dolt e2e + fresh image 并合证据 | 5D-S4 | 5E compose 的 harness 模式 + 并合先例 | 5E-S3 |
| 5D slice exit（独立验收） | 5D-S4 收尾 | **5E 实现启动硬前置** | 5E-S0（S1 kickoff gate） |
| HTTP byte 约束公共类型与 256 KiB body 上限 | 5D §3.3 纪律 | 5E 复用同 byte 规则 | 5E-S2/S3 共享参数表 |

**5D 完成前可设计/可验证**：本文全部 P 级设计；纯逻辑/SQLite 层（projection shape、acceptance 事务、HTTP DTO/jobs 单元）可先对 5D accepted 设计的表形/port 形式做设计级核验。**测试预算由本文 §8 与执行计划阶段验收冻结（唯一 owner 表）；实现测试的创建与执行属于授权后的实现阶段行为，本轮 docs-only 不创建实现测试**（审核 F6：不再表述 “T 侧先行”）。
**必须等待**：任何触真实 Dolt / 真实 baseline 表 / compose journey 的实现与验证（S1 实现、S3 全程、全部容器门禁）。实现次序仍严格 5D slice exit → 5E。

## 10. 开放决定 / 契约冲突 / 停止条件

- **已关闭决定（F5 骨架 v3）**：类 (c) 等价 control record = `history_compare_integrity_records` + §7.1 读/ack 接口（表形、ack、保留、事务闭包；对齐 ADR 0016 “现有 control metadata 足够”）。不是全局 `RepositoryIntegrityIncident` 平台。S2 须交付 integrity 闭环（非 deferred）。
- **已关闭决定（F5 分类 v3.6，S0 可审）**：确认条件与字段映射分离；B→C 不降级；结构 mismatch 轨不得因缺 content pair 归 (a)（§6.6）。S0 接受确认分类规则与预算方向。
- **开放决定（F5 公开面 + 映射 v3.5/v3.6，S2 阶段内闭合）**：`expected_digest`/`observed_digest` **必须**为 materialization 公开 `DigestRef` 的投影（content pair 或结构事实 pair；§6.6；§8.3 选项 1），**禁止**用失败诊断哈希替代内容摘要。闭合条件：S2 **阶段内**先交付 materialization 公开面（content + 结构），再接 History consumer；integrity owner 用 §8 三场景参数表验证。**禁止**将停止线 9 读成「S2 启动前必须已完成实现」。
- **其余 accepted 契约冲突**：本轮核查未发现。Business Lifecycle §9 “节点可从授权 History 读取并按 exact commit 比较” 是设计来源；Operation Lifecycle §1 已把 “history compare” 列名（DRAINING 拒收，本设计用既有 admission 执行）。若审核发现新冲突 → 列明 owning Contract 与最小替代，暂停受影响结论；**不**在本轮改上游。
- **显式假设**：
  a. 5D 最终实现保持 accepted 设计的表形与 port（偏离时 §9 对齐门处置）；
  b. V1 单一 projection/table ruleset version（不做跨版本 pair；version 不匹配 = materialize 稳定失败）。此为**设计前提而非已验证的跨版本兼容**：HTTP Arrow 可重放 canonical catalog/rows 不构成对历史 manifest/ruleset 读的版本兼容证明；真实出现跨版本输入 → 按停止条件 5 重开，本设计不宣称跨版本正确性（审核 N6）；
  c. compare result 读与 accept 同权 `read_project_history`（不另开第二权限）；
  d. 3 节点 = 相邻双 pair（无 1-base-2-branch 拓扑；真实 consumer 出现再修订增拓扑）。
- **停止条件（任一触发 → 停手重开）**：
  1. compare 需要写任何业务状态 / Repository，或需要 caller 传 `repository_id` / `commit`；
  2. 需要删除/改写历史节点、或在 scope 授权外读历史（P5 §12 / contract 重开线）；
  3. 需要扩展 comparison/risk/surface/bundle 词表，或替换 R5 view/identity 语义（原 owner 决定）；
  4. 需要持久业务树、持久执行状态、outbox、任务平台；
  5. 出现跨 version（不同 projection schema）pair 且 V1 ruleset 无法表达；
  6. 要求 all-History 全集“冻结”交付（读列表靠分页已覆盖；若业务真需要全量快照语义 → 修订设计 + 容量评估）。
  7. 5D slice exit 证据不完整（initial-empty 门禁或零表 compose 证据缺失）→ 停止 5E 实现 kickoff（含实现测试创建），不以 “deferred 部分” 绕过；
  8. 比较 policy 绑定发现需要 table-rules 内部算法的私有复制（公共解析结果事实不足）→ 按 P5 §2A 先向 policy owner 提最小公共边界修正，停实现等 owner 交付（先重建公开面，不私下猜算法）；
  9. integrity record 无法实现 Operation Lifecycle §4 任一必需字段的可执行映射 → 停 S2 回设计（F5 停止线）；
- **5E slice exit ≠ P5 overall 架构/性能收口**：exit 证据只覆盖本文不变量 + AGENTS 门禁规则，不合并签署（执行计划 §7 交付声明）。

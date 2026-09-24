# P5-5E History Compare 执行计划

- 状态：**ACCEPTED — 独立文档审核通过（v3.6）；S2 实现已授权**
- 日期：2026-09-21
**修订记录**：v3.6.1（2026-09-23）接受同步；S1 kickoff pass（见 [p5-5e-s1-kickoff.md](p5-5e-s1-kickoff.md)）。v3.6（2026-09-21）v3.5 独立复审 **F5 分类**：确认/映射分离；B→C；结构轨。v3.5 digest pair 语义。v3.4 P3。v3.3 F1a–F1c。v3.1 R1–R4。v3 F1 + F5 骨架。v2 纳入 F1–F6。
- 对应设计：[P5-5E History Compare 详细设计](p5-5e-history-compare-design.md)
- 入口：[P5-5E-S0 Entry Brief](p5-5e-s0-entry-brief.md)

## 1. 当前权威与执行形态

```yaml
entry_kind: p5_5e_execution_plan
stage: p5_5e_s2
status: docs accepted; S2 implementation authorized
implementation_authorized: S2 only
s1_stage_exit: pass
s2_kickoff: pass
s2_stage_exit: pass
docs_review_baseline_head: 6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c
implementation_baseline_head: 6707a1ca01c7325220ec47261b4b69a6232313ab
p5_5d_gate_head: af833695ef1c16b1ea0744d1b6eff6b5ada9924c
s1_kickoff: pass
worktree_for_docs_round: /home/dev/gdds-5e-history-compare-docs（分支 p5-5e-history-compare-docs）
硬前置:
  - p5_5d_slice_exit: pass（独立验收记录存在且结论有效）
  - p5_5d 全部 D 项落地（见设计 §9 表）
硬禁止:
  - 在 5D slice exit 前开始 5E 实现
  - 5E slice exit 与 P5 整体架构/性能收口合并签署
执行形态:
  - 5E 不照搬 5D 的阶段数量；按真实依赖分解为 S1 读投影+读面 → S2 compare 执行 → S3 production+compose → S4 最终并合。
  - 与 5D 的差别：5D 是单事务业务命令 + workspace 迁移 + authority 切主；5E 是读模型 + 只读 operation，无 authority 切主、无业务写。
```

本轮（S0）交付：本文档 + 设计 + entry brief；v3.6 已于 [独立审核 §10](p5-5e-s0-independent-docs-review.md) 通过。S1 kickoff 核查见 [p5-5e-s1-kickoff.md](p5-5e-s1-kickoff.md)；接受记录见 [p5-5e-s0-independent-docs-acceptance.md](p5-5e-s0-independent-docs-acceptance.md)。

## 2. 阶段定义

### S0 — 文档入口与独立审核（本轮）

- 产物：`p5-5e-s0-entry-brief.md`、`p5-5e-history-compare-design.md`、`p5-5e-history-compare-execution-plan.md`。
- 审核焦点（独立 reviewer 核对的 barrier 清单）：
  1. 双层 binding preimage 完整性与 5D 纪律一致性（设计 §5.2：`accept-binding` 用于 replay；`compare-binding` 含 table_policies，在 materialize checkpoint 冻结）；
  2. node 解析、404 不披露、改绑/撤回语义（§4）与 contract §6/§1A.3 一致性；
  3. 2/3 节点 → 相邻 pair / MULTI_PAIR 映射（§5.1）与 E FULL 拓扑先例一致性；
  4. replay 顺序（幂等先于业务检查）与单事务闭包（§6.2）；
  5. 只读零写证据面：写入闭包 + e2e 前后 checksum 断言设计（§6.3）；
  6. schema v6 邻接 5D v5 的版本纪律（§6.4）；
  7. 唯一测试 owner 与共享参数表（§8）；
  8. 镜像 provenance 记录规则与 5D §6.3 一致（§7.4 / 本文 §6.2）。
  9. 比较 policy 绑定链（设计 §5.3：materialize 后 ruleset 公共解析 → policy 投影 → 冻结进 compare-binding checkpoint；assemble 只读 checkpoint；F1 关闭条件）；
  10. integrity 等价 control record（设计 §6.6/§7.1：表形/ack/保留 + **确认条件与字段映射分离**（F5 v3.6 分类）+ materialization 公开面（content/结构 pair，S2 阶段内闭合）+ internal-bearer ack；S0 可审分类规则）；
  11. §6.2 integrity 门禁步（replay 不阻塞；新 accept 拦截 PENDING incident；R3）；
  12. HTTP/worker 稳定码分层（§7.2 三 HTTP 码 + `HistoryCompareDiagnosticCode`；R4）；
- 本轮验证（docs-only，不跑实现测试、不构建镜像、不部署）：
  - 相对链接/锚点检查（三份文件互链 + 上游引用路径存在）；
  - 文中源码路径存在性检查（`B/...`、`T/...` 相对 `vnext/backend`）；
  - 状态/授权一致性（三份文件同标 CANDIDATE / unauthorized）；
  - `git diff --check`；diff 仅限本任务新增文档；
  - 一次性 HISTORY 执行语义验证脚本（`/tmp/verify_history_pair.py`，不进 repo、非测试，证据见 entry brief §6）。
- 审核接受后：entry brief §5 列出需要同步的入口；执行者按清单修订共享文档（本轮不碰）。

### S1 — History 投影与读面

- **前置门禁（kickoff gate，只读核查）**：**2026-09-23 pass** — 详见 [p5-5e-s1-kickoff.md](p5-5e-s1-kickoff.md)。
  1. 5D slice exit pass（`p5_5d_slice_exit: pass` @ `af833695ef`）；
  2. 5D 最终代码重核：workspace schema v5、`baseline_node_records` / `baseline_head_records`、`archive_disposition_records`、`BaselineHeadReadPort`、`repository_commit_id` — 与实现一致，无设计修订阻塞；
  3. initial-empty / 零表证据：5D-S1 pass + S4 compose `zero_repository_effect` 旅程 — 证据对应齐备；S3 零表腿仍为必跑项。
- 目标：真实 control DB 事实 → `HistoryTreeProjection` 确定性 flat list；`GET /v1/history` 走**生产 factory wiring**（不是测试 router）。
- 交付物：`B/application/history/{projection,contracts}.py`、`sqlite_history.py` 读查询、`B/http/{routes/history.py（仅 list 路由）, schemas/history.py, orchestration/history_read.py}`、`HistoryHttpDependencies`（窄）、v6 **不建**（本阶段无 DDL）。
- 验收屏障：设计 §3 全部不变量（shape/父边/双身份/排除/派生 issue/排序/cursor/页内快照/404 不披露/权限矩阵/OpenAPI 集更新/零写）；focused：

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_history_projection.py tests/test_history_http.py \
  tests/test_http_openapi.py tests/test_http_auth_matrix.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py
```

- 独立审核：History/Baseline owner 核事实来源与不披露；Architecture 核 import 边界与窄依赖；HTTP owner 核 DTO/byte 限额。
- 镜像触发：S1 交付含 `http/wiring.py` / `runtime.py` / `dependencies.py`（路由注册 + 生产 factory 绑定）→ 按 AGENTS 属 production wiring 改动：**stage 内迭代证据可延期至阶段末候选，S1 阶段末候选必须 fresh 构建 + 容器回归**（旧镜像结果只作回归证据，不得表述为 S1 HEAD 已验证；记录延期节点 = S1 末候选）；S2 worker/runtime 改动后的 fresh 构建判定不变（§6.2）。
- 停止条件（S1）：投影需要持久化节点、需要能力层新词表、节点解析需要 caller 传 scope/commit、跨 scope 对象存在可泄漏路径、5D 表形与假设不符（回 gate 修订设计）。
- handoff 必须写明：“读面可用（production wiring）；compare 尚未存在；无 schema 迁移；5D 对齐 gate 记录（表名/port/版本号证据）”。

### S2 — Compare accept、执行与结果读

- 目标：设计 §5、§6、§7 全部语义落地：accept 有序事务 + replay（含 §5.2 accept-binding replay/拒绝机制）、3-step job（distinct-commit 去重物化 / compare-binding checkpoint / resume 不重派生 / PURE_RECOMPUTE / cancel 边界）、**per-table policy 在 materialize checkpoint 冻结（设计 §5.3）**、**integrity record 读/ack 闭环（设计 §6.6，非 deferred）**、result/bundle 读再授权、generic operation readback 按 job kind 分派、admission 覆盖、零业务写（DB 层断言）。
- 交付物：`B/application/history/{compare,compare_jobs,compare_registry}.py`、`B/http/orchestration/{history_compare,history_integrity}.py`、`routes/history.py` 追加 4 路由（compare result/bundle + integrity-ack）、`schemas/history.py` 补 DTO（含 `HistoryCompareAcceptResponse`、`IntegrityIncident`）、`migrations.py` v6（acceptance + integrity 表，一次性）、`database.py` UoW 成员、`operation_scope.py` 分支、**`http/routes/operations.py`（history job 授权分派，preview 路径行为不变）**、`operation_worker.py` bundle 组装、`errors.py` 映射、`dependencies.py`/`runtime.py` 绑定 + registry assert。
- 验收屏障：
  - replay 顺序（幂等命中早于业务校验；replay 仍需当前授权）；
  - fingerprint 相同 → 同 `operation_id`；不同 → 409；
  - id 确定性（同输入同 `op-`/`hca-`）；
  - 2/3 节点映射、相邻 pair、去重物化、3-input MULTI_PAIR；
  - pending/terminal 形状、`record_count` 与 `bundle_digest` 一致；
  - DRAINING 拒收 accept（进程级）；读路由允许读到进程停；
  - 零业务写：accept/publish 前后 submission/review/baseline/archive/workspace/mapping row-count 与 row-set checksum 不变；
  - 同 commit pair → UNCHANGED（抽查引用 capability owner 回归，不在 5E 复制）；
  - 比较 policy 绑定代表性场景（move-only → `ROW_MOVED` 零内容更新 / pseudo-blank 占位 / keyed 忽略列；≡ capability owner 同 policy 本地 oracle，场景参数复用 E `T/test_comparison_ordered.py`，F1 关闭条件）；
  - **accept-binding fingerprint 不含 table_policies**；compare-binding 在 materialize checkpoint 冻结；assemble resume 不重派生；
  - **类 (c) integrity：§6.6 确认/映射分离 + materialization 公开面（S2 阶段内）+ 三场景参数表（`content_stable` / `content_drifting` / `structural_no_content_pair`）→ incident + ack 闭环；未 ack 时同 commit 新 accept → 409**（F5 完整闭合条件）；
  - **replay 不受 PENDING incident 阻塞；新 accept 被 §6.2 步 5 拒绝**（R3）；
  - `business_refs` 与 protection owner 落位；inline job_payload ≤ 64 KiB 断言（不含 table_policies 正文）。
- focused：

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_history_compare_transactions.py tests/test_history_compare_jobs.py \
  tests/test_history_compare_integrity.py tests/test_history_http.py \
  tests/test_operation_http.py tests/test_http_admission_shutdown.py tests/test_architecture.py
```

  测试分类变动时按 AGENTS 跑「移开 dolt → `-m unit`」验证（本轮新增为 app-level unit + serial 进程级两类，不为 D 相关断言建 dolt fixture）。
- 独立审核：History Application + Operation owner 联审事务闭包/replay/resume；Architecture 审 worker 组装与 import 边界（operation 不得反向依赖 application 的业务入口——组装在 `operation_worker.py` 单点）。
- 镜像触发：**是**（runtime/worker/wiring 生产接线）→ S2 该轮最终 HEAD fresh 构建 + 既有 3-process readiness/submit restart 回归门禁（复用 5D S3 的文件集，见 §6.2）。
- 停止条件（S2）：需要改动 capability 词表或 R5 语义、需要 caller 传 commit/repository、出现外部 effect、job_payload 超预算、需要持久执行状态/outbox（任一 → 回设计 §10 对应停止线）。
- handoff 必须写明：“compare 可用（本地 focused 绿 + 容器回归）；integrity 闭环已交付（非 deferred）；compose journey 未跑；v6 为最终一次性迁移”。

### S3 — production wiring 与正式 compose journey

- 目标：真实 session/seed/迁移 + 端到端旅程（正式入口，非测试 router）：

  1. 真实 initial **空** commit baseline（5D-S1 gate pass 证据引用）；
  2. submit A（actor1）→ review approve → submit B（actor2，同 base）→ review approve → archive A（B 得 `CLOSED_NOT_ARCHIVED`）→ 第二轮 submit C（新 base）→ approve；
  3. `GET /v1/history`：shape 断言（INITIAL 节点 + 全部成功 submissions 节点 + disposition/review 事实 + 排序 + cursor 翻页 + head 字段）；跨 scope 与无权限矩阵（参数表）；
  4. 2 节点 compare（archived A ↔ closed B，同 commit 语义：预期 divergent facts）、3 节点 compare（initial → A → C）→ result/bundle 读 → 重启 → 事实仍可读（replay + durable artifact）；**至少一对 pair 覆盖 ordered（gid/no）表，验证 compare-binding checkpoint policy 在真实路径**；**引用 S2 类 (c) integrity 证据或 harness 代表场景**；
  5. **零写证据**：compare 前后 submission/review/baseline/archive/workspace 行集合 checksum 不变；Repository commit 集合不变；无新 canonicalization manifest；
  6. admission/DRAINING 行为（进程级 serial 测试）。

- 交付物：`vnext/deploy/config/session.json` example（`read_project_history` 列表，不授予）、`T/test_history_compose_e2e.py`（`@pytest.mark.integration`，真实 dolt）、必要时的 compose gate harness 共享 helper 迁移（最小化，双侧同步——5D S3 先例）；`deploy/compose.yaml` 仅在真实接线缺口时变动（预期无）。
- focused：

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_history_compose_e2e.py tests/test_history_http.py \
  tests/test_history_projection.py tests/test_history_compare_transactions.py \
  tests/test_http_auth_matrix.py tests/test_http_openapi.py tests/test_architecture.py
```

- 独立审核：HTTP/Deployment owner 核真实 session/seed/真实 image；Architecture 核零写证据完整性与 journey 覆盖（设计 §4.3 改绑/撤回场景在旅程或参数表中至少一处）。
- 镜像触发：**是**（session.json 部署面 + 最终候选）→ fresh 构建 + 下方全量并合。
- 停止条件（S3）：端点只到 test wiring、production 权限缺口、启动重置 Head、零写断言失败或缺失、必要 join 被 skip、真实 image 无法绑定、**零表腿未执行或 5D gate 证据缺失（kickoff gate 已验证；发现缺失 → 停整个 kickoff，非 stage 内 deferred）**。
- handoff 必须写明：journey 步骤清单 + 零写证据 + 镜像 provenance（§6.3）+ deferred 项。

### S4 — 最终 fresh 候选并合与独立 exit

- 目标：冻结候选；关闭独立审核 findings；五包静态 + 权威 runner + fresh image 并合全部通过。
- 任何 final fix 后重算 source-tree/lock/Compose digest 并重跑受影响门禁；**该轮最终候选无条件 fresh 构建 + 0 skipped 重跑（最终候选不得用旧镜像证明当前 HEAD）**；先前阶段结果只作回归输入。
- 并合（全部 0 skipped、all pass 才可宣称）：
  - `test_history_compose_e2e.py`（History→Compare→Result/Bundle journey）；
  - 零表腿显式记录：journey 的 initial 空 baseline 步骤实际执行通过（5D 证据 kickoff 重核完整；本计划无 deferred 分支，F6）；
  - 既有 Review/Submit restart/journey 与 Backend CMD/readiness/clean stop 门禁（5D S3 文件集）；
  - 五包 `ruff check` + `mypy`；
  - `./vnext/scripts/run-tests.sh`（权威全量；`GATEWAY_TEST_WORKERS` 按环境）。
- 交付声明：只交付 `pass_recommended` + 证据包；`p5_5e_slice_exit: pass` 只能由独立验收记录接受在权威位置声明。**5E slice exit ≠ P5 整体架构/性能收口**，不合并签署。

## 3. 具体路径预算

B=`vnext/backend/src/gateway_backend/`，T=`vnext/backend/tests/`（与设计 §2 同记号）。

| 阶段 | 新增（B） | 新增（T） | 修改（B/T/config） |
| --- | --- | --- | --- |
| S1 | `application/history/__init__.py`、`application/history/contracts.py`、`application/history/projection.py`、`infrastructure/control_db/sqlite_history.py`（读查询）、`http/routes/history.py`（list 路由）、`http/schemas/history.py`、`http/orchestration/history_read.py` | `test_history_projection.py`、`test_history_http.py`（list 路由部分） | `http/dependencies.py`、`http/runtime.py`、`http/wiring.py`、`T/test_http_openapi.py`、`T/test_http_auth_matrix.py`、`T/test_production_wiring.py`、`T/test_backend_readiness.py`、`T/test_architecture.py` |
| S2 | `application/history/compare.py`、`application/history/compare_bindings.py`、`application/history/compare_jobs.py`、`application/history/compare_registry.py`、`http/orchestration/history_compare.py`、`http/orchestration/history_integrity.py` | `test_history_compare_transactions.py`、`test_history_compare_jobs.py`、`test_history_compare_integrity.py` | `B/capabilities/snapshot_materialization/{contracts.py,repository_ref.py}`（**窄例外**：content digest pair + 结构 mismatch 最小公开事实；mismatch halt 填充）、`application/history/contracts.py`（`HistoryCompareDiagnosticCode`）、`application/submission/ports.py`、`infrastructure/control_db/migrations.py`（v6）、`infrastructure/control_db/database.py`、`infrastructure/control_db/sqlite_history_compare.py`、`infrastructure/control_db/sqlite_history.py`、`http/routes/history.py`（+4 路由，integrity-ack 挂 `require_internal_bearer`）、`http/routes/operations.py`、`http/schemas/history.py`、`http/schemas/constraints.py`、`http/errors.py`（仅 3 HTTP 码）、`http/dependencies.py`、`http/runtime.py`、`http/wiring.py`、`http/orchestration/operation_scope.py`、`bootstrap/operation_worker.py`、`T/support/history_compare_job_harness.py`、`T/support/http_shutdown_harness.py`、`T/support/repository_ref_materialization.py`、`T/support/history_zero_write_tables.py`、`T/test_history_http.py`、`T/test_operation_http.py`、`T/test_http_admission_shutdown.py`、`T/test_http_admission_shutdown_process.py`、`T/test_preview_read_http.py`、`T/test_review_persistence.py`、`T/test_submit_control_db_migrations.py`、`T/test_workspace_control_db_migrations.py`、`T/test_architecture.py` |
| S3 | — | `test_history_compose_e2e.py` | `vnext/deploy/config/session.json`、`T/test_http_auth_matrix.py`（如参数表扩展）、`T/support/compose_gate_harness.py`（仅共享 helper 必要时）、`deploy/compose.yaml`（仅真实缺口时，预期无） |
| S4 | 无业务能力新增 | findings 回修 S1–S3 | 仅 findings 涉及文件 |

预算外禁止（任一触碰 = 停止并回设计）：`B/capabilities/**` **除** `snapshot_materialization/{contracts.py,repository_ref.py}` 的 F5 窄例外（§6.6 content/结构公开面，S2 阶段内 materialization owner 同交付）、`B/operations/**`、`vnext/repository_service/**`、shared kernel、Rust、五包 `pyproject`/`uv.lock`、Dockerfile/构建机制/entrypoint、legacy；不新增 capability owner；不使用 `history-`/`history:` artifact 前缀（§设计 2.1 第 5 行）；不新增通用 context bag（窄依赖原则）。

## 4. 测试归属与比例化范围

- 唯一 owner 表 = 设计 §8；本计划不建第二注册制。
- 同构用例共享参数表（模块级）：node ref byte 边界（ASCII/CJK/4-byte 恰 255/256 越界）、idempotency 同 key 突变（改 node 顺序 / 改 ref_id / **重复 JSON key（拒绝用例）**；注意：重复 node ref `[A,A]` 是合法 UNCHANGED 回归用例，不得归入 “拒绝” 组，避免实现把 “duplicates” 误解为统一拒绝）、auth 矩阵（无权限/跨 scope/改绑/撤回 × 5 路由）、cursor 非法形态。
- A 类（acceptance record / operation record）只测业务行为失败面：事务前失败必回滚、响应丢失后原 key 恢复、并发/顺序（3 个高价值 barrier）；不注入 SQL/低层系统错误。
- C 类（projection/eligibility/result artifact）：有界读 + 清理不报错即可；不建强持久化证明。
- 关键崩溃语义用真实 SQLite 文件，不用 tmpfs 替代（AGENTS/policy）；容器内临时卷按 5D 既有规则。
- serial 纪律：进程级 admission/DRAINING 与重启测试按需 `@pytest.mark.serial`；backend 不加 xdist。

## 5. 命令草案（每阶段 focused 汇总，权威入口不变）

```bash
# 五包静态（提交前必跑，AGENTS；五包 = shared_kernel / repository_contracts / repository_client /
# repository_service / backend——基线 vnext/ 无 common / common_infra，修正旧命令拼写，F6）
for p in shared_kernel repository_contracts repository_client repository_service backend; do
  (cd vnext/$p && ../scripts/uv-consume.sh -C . run ruff check . \
    && ../scripts/uv-consume.sh -C . run mypy) || exit 1
done

# S1 focused（S1 结束后）
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_history_projection.py tests/test_history_http.py \
  tests/test_http_openapi.py tests/test_http_auth_matrix.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py

# S2 focused（S2 结束后）
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_history_compare_transactions.py tests/test_history_compare_jobs.py \
  tests/test_history_compare_integrity.py tests/test_history_http.py \
  tests/test_operation_http.py tests/test_http_admission_shutdown.py tests/test_architecture.py

# S3 compose（真实 dolt）
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_history_compose_e2e.py

# S4 权威全量
./vnext/scripts/run-tests.sh            # 或 GATEWAY_TEST_WORKERS=48 ...
```

阶段性验证不跑全量；`serial and not parallel_safe` 组按 AGENTS 收敛运行。

## 6. 镜像、provenance 与运行证据

### 6.1 重建判定（AGENTS 规则映射）

| 阶段 | 触碰 | 是否 fresh 重建 |
| --- | --- | --- |
| S0 | docs only | 否 |
| S1 | HTTP 路由/wiring（production wiring：`wiring.py` / `runtime.py` / `dependencies.py`） | **阶段末候选：是**（stage 内迭代延期至阶段末候选并记录；S1 独立候选含生产接线，旧镜像不能证明其 pass） |
| S2 | `runtime.py` / `operation_worker.py` / `wiring.py` / `dependencies.py`（production wiring） | **是**：该轮最终 HEAD |
| S3 | session.json 部署面 + 最终候选 | **是**：最终候选 HEAD |
| S4 | final fix 任一（或无 final fix 时引用 S3 结果） | **无条件 fresh 构建 + 0 skipped 全量重跑**（最终候选不用旧镜像；final fix 未触容器边界的内部逻辑修复同样重跑 focused 全量） |

旧镜像结果只作回归证据，不得表述为当前 HEAD 已验证；每阶段 handoff 必须记录当前 HEAD、是否重建及理由、最后验证的 image revision/source-tree、延期到哪个节点（AGENTS/testing-conventions 记录模板）。

### 6.2 S2/S3 容器门禁文件集（预期最小集，S1 kickoff 时按 5D 最终实际文件复核）

- Backend 3-process readiness + clean stop（既有 compose 门禁模式）；
- submit restart / journey 回归（5D S3 文件集）；
- S3 追加 `test_history_compose_e2e.py`。

### 6.3 运行镜像证据记录（每次容器门禁后，5D §6.3 最小格式）

```
HEAD: <commit>（分支 p5-5e-history-compare-docs 或其实现分支）
source_tree_sha / pyproject+uv.lock sha（五包） / deploy/compose.yaml sha256 / DEPLOYMENT.yaml.sha256（如有改动）
running image: docker inspect .Image + repo tag/revision
fresh_build: yes/no + 重建原因
focused 测试摘要 + 容器门禁结果（pass/skip 清单）
5D 对齐 gate 记录（S1）/ 零写证据（S3）
```

## 7. 最终 exit 证据与停止规则

最终 handoff（author，不签署）必须提供：

1. 设计 §10 停止条件**均未触发**的逐条声明；
2. 5D 对齐 gate 记录（表形/port/版本号实际值 vs accepted 设计）+ **5D exit 证据复核（含 initial-empty 门禁与零表 compose 旅程，F6）**；
3. 零写证据：e2e 前后业务表 checksum + Repository commit 集合不变断言的输出；
4. 容器并合证据：实际运行 image ID/revision + source-tree sha + 全部门禁 pass/0 skipped；
5. 唯一 owner 覆盖表（设计 §8 ↔ 实际测试文件映射）；
6. deferred 项清单（预期为空：零表腿为 S3 必跑项、integrity 闭环为 S2 必交付项、5D 证据 kickoff 重核；任何新增 deferral 必须写明最终关闭节点）；
7. 镜像 provenance 记录（§6.3 每阶段一份）。

停止规则：设计 §10 任一条触发 → 立即停止受影响工作，列明冲突 Contract/假设，等待 owner 决策后再继续；不扩大威胁模型（同机单一信任域，ADR 0012 边界内处置，不新增独立 UID/helper/sidecar 安全机制）；不宣称未跑过的门禁通过；不自行签署 `p5_5e_slice_exit`。

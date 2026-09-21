# P5-5D Archive Execution Plan

状态：**ACCEPTED — S1 pass；S2 implementation in progress**

审核依据：[S0 Independent Docs Acceptance](p5-5d-s0-independent-docs-acceptance.md)。

日期：2026-09-20

Owner：Backend Archive Application；Baseline/Submission/Workspace/HTTP/Control DB owners 按阶段参与。

上游：[S0 Entry Brief](p5-5d-s0-entry-brief.md)、[Archive Detailed Design](p5-5d-archive-design.md)、
[P5 §2A / §6.4](p5-business-vertical-slices-design.md)、[Implementation Stages](implementation-stages.md)、
[Testing Conventions](../../../testing-conventions.md)。

## 1. Current authority and execution shape

```yaml
inspection_head: 16f4112ee10536c3c8b82765167ff0454ad5f05f
accepted_p5_5c_candidate: 04317788c259b172e3b8580cfe42bac8d16735f0
p5_5c_slice_exit: pass
p5_5d_docs_authorized: yes
p5_5d_design: accepted
p5_5d_execution_plan: accepted
independent_docs_review: pass
docs_revision_review: pass
closed_document_findings: [initial_empty_design_budget, audit_request_fingerprint, utf8_limits, repository_scope_contract_acceptance]
remaining_design_item: none
repository_scope_contract_amendment: accepted
p5_5d_implementation_authorized: yes
first_authorized_implementation_stage: S2
p5_5d_s1_stage_exit: pass
p5_5d_s2_stage_exit: not_evaluated
production_deployment_authorized: no
new_repository_effect_authorized: no
p5_5d_slice_exit: not_evaluated
next_step: P5-5D-S2-implementation
```

S0 文档编写及独立复审已完成。S1 **pass**（Baseline Head authority、initial-empty 前置、v5
Baseline DDL、focused gate）；S2 实施授权中；S3–S4 未开始。S1 交付无 Archive API；v5 仍未
发布。未来测试环境中为构造 Submission 所需 Repository writes 限定为现有 Submit journey 测试；
Archive 自身始终零写。

阶段按 Archive 的实际依赖划分，不照搬 5C 的持久化/HTTP/评审轮次：S1 先建立可靠 Head authority，并由原 owner 补齐 initial-empty Preview/Submit 前置链路；
S2 在同 DB 交付候选、审计、归档与跨用例屏障；S3 暴露完整生产 API；S4 对精确候选进行 fresh
image conjunction 和独立退出验收。不得在 S1–S2 暴露半完成 Start HTTP endpoint。

每个阶段结束提供 handoff，由独立上下文评审行为、范围和证据；delivery 只给建议，不自行代签
阶段通过或 slice acceptance。未来实现中的普通修复在已授权预算内处理，不因文件整理新增逐项
审批；超出 contract/预算则停止相关依赖工作并更新计划。

## 2. S0 — docs entry and independent review

目标：把上游业务规则对齐当前代码，形成已审核的三份设计与默认入口；不改 source/tests/
依赖/部署，不运行 production deployment。当前 Head、工作区预提交及静态检查见 Entry Brief。

文档范围：本计划、Entry Brief、Archive Design、P5 baseline、implementation-stages、formal
README、backend-vnext README、architecture 总纲的当前状态说明，以及用户追加授权的
Business Lifecycle §1A/§9A 补充与版本说明，以及独立文档接受记录；本次复审正式接受 3.0.0。

审查屏障：

- 资格/稳定引用/所有 digest preimage、subject sequence、audit owner/真实 consumer 可直接实现。
- Preview 纯读与 Start 冻结点分开，全部权威效果一个 SQLite commit，无 Repository 写。
- Replay/auth/precondition 顺序明确，Review return、Submit、并发 Archive 有线性化结果。
- schema v4 现实、initial seed 接入及两进程重启、Baseline reader 的完整迁移路径。
- 公共 port 不泄漏 wire，不 import 私有能力、不制造 Application 运行时环；占位能力明确延期。
- HTTP DTO、permission、production factory、部署 initial-only seed 语义有预算。
- 测试唯一 owner、阶段 gate、最终实际运行镜像 provenance 可复核。

S0 focused 检查只有 Markdown links、源码路径存在性、状态/授权一致性、`git diff --check` 和禁区
差异检查；五包 static 作为提交前门禁。独立 reviewer 单独记录 findings/候选文件 tree；若需改变
上游 contract，列明冲突并暂停该设计结论，不静默更改。本次独立复审已接受 scope Contract
补充并关闭最后一项 finding；四项文档 finding 全部关闭，S1 实现仍未授权。

## 3. Concrete path budgets

以下为后续实施 **已审核 allowlist**，不是当前权限。`B` 表示
`vnext/backend/src/gateway_backend/`，`T` 表示 `vnext/backend/tests/`。
每阶段新增目录只限表内列出的文件（必要 `__init__.py` 同目录包含），不使用整层通配授权。

| 阶段 | 生产路径预算 | 测试路径预算 |
| --- | --- | --- |
| S1 initial-empty 前置（Preview/Comparison/Submit 原 owner） | 必改 `B/application/preview_jobs.py` 的合法空 checkpoint 恢复；同文件完整 pair pipeline 与 `compute_baseline_canonical_bundle_digest` 在既有公共入口上验证/最小修复；`B/http/runtime.py` 仅 baseline digest adapter 接线；其他 owner 路径限下文条件预算 | 既有 `T/test_preview_job_materialize.py, test_preview_job_assemble.py, test_comparison_planning.py, test_comparison_standard.py, test_repository_ref_materialization_hidden_summary.py, test_submit_transactions.py, test_production_wiring.py`；`T/support/preview_job_harness.py` 仅真实零表 input/恢复 fixture，不伪造表 |
| S1 Head authority / migration | 新 `B/domain/baseline/models.py, ports.py`、`B/infrastructure/control_db/sqlite_baseline.py`；改 `B/infrastructure/control_db/migrations.py, database.py, sqlite_mapping.py`；`B/http/runtime.py` 与 `B/bootstrap/operation_worker.py` 仅 seed/reader 接线；`B/domain/workspace/models.py, ports.py` 仅保留/说明旧 DTO adapter 边界 | 新 `T/test_archive_control_db_migrations.py`；既有 `T/test_workspace_control_db_migrations.py, test_submit_control_db_migrations.py, test_review_persistence.py, test_sqlite_workspace_repository.py, test_production_wiring.py, test_architecture.py` 的 Head/schema fixture 与精确边界增量 |
| S2 Complete local archive semantics | 新 `B/domain/archive/models.py, ports.py`；`B/application/archive/contracts.py, ports.py, queries.py, audit.py, start.py`；`B/infrastructure/control_db/sqlite_archive.py`；改 `B/infrastructure/control_db/database.py, migrations.py, sqlite_submission.py`（完善 v5 Archive 表与同 UoW）；`B/domain/submission/ports.py`（bounded read）；`B/application/submission/ports.py, review.py, review_transaction.py, errors.py`（closure port/授权区分）；`B/http/orchestration/review.py, routes/reviews.py`（既有 Review 新 closure error 映射） | 新 `T/test_archive_queries.py, test_archive_audit.py, test_archive_transactions.py, test_archive_concurrency.py`；既有 `T/test_review_transactions.py, test_review_http.py, test_submit_transactions.py, test_submit_idempotency.py, test_architecture.py` 仅必要接线/行为回归；S1 migration owner 补 Archive schema 验证 |
| S3 HTTP / production integration | 新 `B/http/routes/archives.py, schemas/archive.py, orchestration/archive.py`；改 `B/http/dependencies.py, runtime.py, wiring.py, errors.py`；`B/http/schemas/constraints.py` 仅复用既有公开 byte constraints；Archive 专用 digest/action/array validator 放新增 schema 并委托 Application contracts；`vnext/deploy/config/session.json` 仅示例显式 archive permission；`vnext/deploy/README.md`（若无则在同目录新建）说明权限与初始 seed/维护升级；`vnext/deploy/compose.yaml` 只在实际接线缺口确认后作最小修正并记录原因 | 新 `T/test_archive_http.py, test_archive_compose_e2e.py`；既有 `T/test_http_auth_matrix.py, test_http_openapi.py, test_production_wiring.py, test_backend_readiness.py, test_architecture.py`；共享 `T/support/compose_gate_harness.py` 仅经真实调用核实所需场景/权限/actual image capture，不能预设其已支持 Archive |
| S4 Final candidate gate / handoff | 不新增业务功能；findings 仅回到 S1–S3 已列路径并重跑受影响 gate；本组文档与各阶段 handoff/独立评审文档 | 同一最终候选测试集合；必要修复严格归属已有 owner，无新增 evidence platform |

S1 initial-empty 条件预算：只读确认和 focused gate 后，若存在可复现的零表支持缺口，原 owner
可在以下精确路径最小修复：`B/infrastructure/repository_read/http_arrow.py`、
`B/capabilities/snapshot_materialization/repository_ref.py`、
`B/capabilities/comparison/pair_planning.py, standard.py, artifacts.py`、
`B/capabilities/risk_evaluation/_engine.py`、`B/capabilities/surface_assembly/_assembly.py`、
`B/capabilities/bundle_assembly/_assembly.py`。对应已有 `T/test_risk_evaluation.py,
test_surface_assembly.py, test_bundle_contracts.py` 只补该 owner 语义缺口，不能复制 Preview
恢复矩阵。没有实际失败的路径保持不动；public contracts、digest 编码和 Repository wire 变更
不在此预算，若需要则停止并由原 owner 重评。Capability 私有文件只允许其原 owner 内部修复，
不授权 Archive 或其他消费者新增私有 import。无需为零表引入 Archive 专用计算分支。

反向 scope 基数及 migration/seed/update、历史不变规则已由
[Business Lifecycle §1A / §9A](../contracts/business-lifecycle-and-state.md#repository-scope-ownership-amendment)
接受为 `3.0.0`。S1 的 Contract 前置已满足，不替代后续明确 implementation authorization。
现有 schema 不具备反向约束，本轮不改源码。

S1 可先在未发布的 v5 migration 中完成 Baseline 部分，S2 在同一未发布 v5 内补完 Archive；S1/S2
只在可重建测试 DB 运行，不能将中间 v5 当受支持可升级生产 schema。S3 最终 v5 定稿前明确清理
中间测试 DB 或使用新临时目录；不能误称相同版本自动补齐中间 DDL。若需要保留中间数据，必须
追加 migration version 并重评计划，禁止修改已部署 migration。

已核查共享 harness 为 `T/support/compose_gate_harness.py`；现有 Review test 还复用
`T/test_submit_compose_e2e.py` 的私有测试 helper。S3 允许把确有第三个 consumer 的栈启动/
provision/journey helper 最小迁入 `T/support/compose_gate_harness.py`，同步修改
`T/test_submit_compose_e2e.py` 和 `T/test_review_compose_e2e.py` 的引用，保留原有语义 owner。
其他 fixture 改动须在 handoff 逐项列明，不能按 `tests/**` 放行。

所有实现阶段禁止路径/事项：Repository Service/Client/Contracts、Shared Kernel、Rust、全部
`uv.lock`/`pyproject.toml`、Dockerfile/基础镜像/构建传输机制、legacy source、上述 S1 条件预算以外的 capability 私有实现、
History 功能、Operations Runtime 业务扩展；不得新增 Archive worker/job、锁表、candidate 表、
outbox、broker/sidecar、Repository mount 或 write adapter。纯调用现有 build/test 脚本可用于 gate，
修改这些机制需另行证明范围并更新预算。现有 Submit 接受流程不是全量重构入口。

## 4. Stage goals, barriers and focused checks

### S1 — Baseline authority, seed compatibility and initial-empty prerequisite

目标：Node/Head 同 DB authority 与 v4 initial migration 可用；5A/5B/5C 继续通过原公共 reader 获取
当前业务 Head，HTTP/worker 重启不会回退。先在测试构造 Head advance 验证 seed invariants，正式
Archive 写命令尚不暴露。initial-empty 是本阶段明确交付前置，不等待 S3 才用 fixture 发现：
由 Preview owner 修复 checkpoint，Comparison/Submit owner 共同验证 Design §2.1 的完整链路；
未通过不得进入 Archive journey，即使 Head migration 单独通过也不能给 S1 pass。

验收屏障：version=0 initial ID/commit 保留；有既有 Submit/Review 的 v4 upgrade 不失事实；fresh DB
可 seed；错误历史/多 Head/跨 scope node 迁移失败且 v4 完整；Head 不再重复存于 mapping；两个
startup consumer 使用 DB authority；Review 对正常 Head advance 与 scope 撤销的区分在 S2 完成。
迁移、首次 seed、同批 seed、mapping update 均拒绝不同 scope 共享 Repository（包括相同 Head
和 disabled 行），错误不得部分写入；原 mapping 移走后通过 INITIAL Node 固定 scope 拒绝另一个
scope 接管。保留同 scope 重启和同 scope 多 actor 的合法路径。

initial-empty gate 覆盖：零表 catalog/summary/table set → 合法空 checkpoint 解码与恢复 → FULL
双 pair、MODIFIED_ONLY baseline 复用 → comparison records/risk/surface/bundle READY → 两种
拓扑的 Submit baseline canonical digest。缺失 tables/null/错误类型、非空 summary 丢 refs 和
错误 digest 继续 fail closed；新表改动可接受，canonical 无变更在 Attempt/Operation 前拒绝。
不能把“没有 rows 的一张表”或 absent baseline 对象当作 empty repository。

唯一 owner 分配见 Design §9；`test_preview_job_assemble.py` 用两种 mode 的共享参数表验证
空 checkpoint 恢复及 producer digest，不在 Archive tests 复制。Comparison 原 owner 只证明
empty→nonempty table addition 与 empty→empty facts。

Focused（均通过受控 wrapper，Backend 单进程）：

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_archive_control_db_migrations.py \
  tests/test_workspace_control_db_migrations.py tests/test_submit_control_db_migrations.py \
  tests/test_review_persistence.py tests/test_sqlite_workspace_repository.py \
  tests/test_preview_application.py tests/test_preview_job_materialize.py \
  tests/test_preview_job_assemble.py tests/test_comparison_planning.py \
  tests/test_comparison_standard.py tests/test_repository_ref_materialization_hidden_summary.py \
  tests/test_submit_transactions.py tests/test_production_wiring.py tests/test_architecture.py
```

独立评审：Preview/Comparison/Submit owner 先复核 initial-empty focused 证据与恢复语义；Baseline/Control DB owner 重点审升级、reader、initial identity 和回滚；Architecture 审旧
DTO adapter 与新 Domain 单向依赖。触及 startup 必须重建本阶段最终 HEAD 并运行现有三进程
Submit restart、Backend CMD/readiness gates（§6 现有文件）；阶段 pass 前不得延期此容器证明。

停止条件：真实 v4 数据无法映射 initial、需要 Repository 读写才能猜初始 base、需要混跑新旧
writer、修改公用 canonical/wire 语义、出现需重开反向基数 Contract 的需求或 initial-empty 仍有失败。
交付 S1 handoff 明确“无 Archive API；v5 尚未发布”，列明 initial-empty 已修复/仅验证的精确路径
和 focused 证据；不得把未验证能力标已支持。

**S1 stage exit: pass**（2026-09-21）。已交付 Baseline Head DB authority、v5 Baseline DDL、
initial-empty preview 修复与 focused gate；无 Archive API；v5 仍未发布。

### S2 — bounded read, audit and single-transaction Archive

目标：完整本地 candidate/preview、append audit、Start/replay/Result query；Review closure 和
AcceptSubmit 的共同 Head 语义真实生效。同步命令只消费既有冻结事实与本地 DB。

验收屏障：Design §3–6 全部业务不变量由唯一 owner 覆盖；尤其 candidate-set 不漏 sibling、确认
不绕过 blockers、same-key replay 在 Head advance 后成功；审计请求 fingerprint 覆盖全部
HTTP 绑定字段（selected ID/candidate digest、candidate_set_digest 也在内）；Plan/Result/Node/Head/disposition/
release 原子；两连接竞争两种获胜顺序；失败 Start 不留下 key 或 Plan；旧 base 普通 candidate
不重返；没有 Repository/Artifact I/O。Review 既有成功 replay 在归档后仍返回原事件，新 return
得到 closure 冲突，不能仅偶然在 Workspace occupancy 上报错。
`test_archive_audit.py` 使用共享参数表：confirmation/resolution 两类命令在同 key、原 subject
下分别修改 selected ID、selected candidate digest、candidate_set_digest，均拒绝为
IDEMPOTENCY_CONFLICT；单独保留 subject/Head 过期后的完全相同请求 replay 返回原事件。
不借当前 subject 重推导取代 fingerprint，也不在 HTTP 重复该 idempotency 负面矩阵。

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_archive_queries.py tests/test_archive_audit.py \
  tests/test_archive_transactions.py tests/test_archive_concurrency.py \
  tests/test_archive_control_db_migrations.py tests/test_review_transactions.py \
  tests/test_review_http.py tests/test_submit_transactions.py tests/test_submit_idempotency.py \
  tests/test_architecture.py
```

独立评审：Archive/Submission/Workspace owner 联合审单事务与 replay 顺序，评审是独立上下文，
不以实现者自查替代。阶段内纯 Python/SQL iteration 可延期镜像到本阶段最终候选；正式阶段退出
仍重建并运行已有 Review+Submit+Backend conjunction。S3 未完成前不声称生产 Archive journey
通过。本阶段停止于需复用私有 helper、反向 import job、确认/异常需未定义 producer 或超候选
预算不能完整验收的场景；修改候选文档后再续相应工作。

### S3 — public API, production composition and deployment inputs

目标：所有 Design §8 routes/DTO 与真实 production factory 接线、独立 permission、schema/seed
启动语义、真实 Archive Compose journey。mock app 或只挂 router 的 HTTP 测试不能替代 production。进入真实 Archive journey 前必须
引用 S1 initial-empty focused pass；S3 再以真实 Repository initial commit 完成集成证明，不能
只依赖现有零行表 seed helper。

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_archive_http.py tests/test_http_auth_matrix.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py
```

验收屏障：生产 OpenAPI 精确路径集合；session 当前授权及 cross-actor/project/Repository 拒绝；
POST Preview 无 mutation；append/Start 受 shutdown admission；不公开 caller commit/Repository
policy/fault control；权限示例不是自动授予真实用户；worker 无 Archive job。
`test_archive_http.py` 在一个共享参数表对同一输入同时调用 HTTP DTO 与 Application validator，
以 byte 规则为唯一期望：ID ASCII 255/256、中文 85/86（255/258 bytes）、四字节字符与 ASCII
混合的 255/256 bytes；reason ASCII 4096/4097、中文 1365 加一个 ASCII（4096）/加两个（4097）、
四字节字符 1024/1025。另明确 1500 汉字 reason 拒绝、2001 ASCII reason 接受；缺失/null/
非 string/非法 surrogate 按 action/strict shape 拒绝。纯校验不引入 Dolt fixture。

本阶段触及 production wiring/deployment permission/container harness，最终 HEAD 必须 fresh
build 并运行 §6 全部 conjunction（含从真实零表初始 commit 开始的新 Archive journey）。Archive journey 至少两位 actor 两份
同 base 成功 Submission：技术 main 在后提交者，选择先提交者归档，验证业务 Head 指向其 commit、
后提交者 CLOSED_NOT_ARCHIVED、全部相关 Workspace release。下一轮 Preview 用新 base，HTTP
与 worker restart 后 Head 不变，scope 内可读 Result/audit。

独立评审：HTTP/Deployment owner 核对真实 session/seed/migration、actual running image IDs；
不因 container tag 正确而签署 gate。停止条件：只有测试 wiring 有 endpoint、production permission
缺失、startup 重置 Head、实际镜像不可绑定或必要测试 skip。交付 S3 handoff 不签 slice exit。

### S4 — final fresh candidate conjunction and independent exit

目标：冻结精确 source/test/deployment 候选，关闭独立 findings，汇总所有唯一 owner 与真实生产
入口证据。在该候选运行五包 static、权威 runner、fresh image conjunction；之前阶段结果只作
回归输入，不能替代当前候选最终镜像。

任何 final 修复改变 `vnext/**` 后重新计算 source-tree/锁/Compose digest，重建并复跑受影响 gate
及最终 conjunction，不能拿之前的 build 标签续签。独立 slice acceptance 根据 §7 证据判定，
delivery 仅 `pass_recommended`；只有独立 acceptance authority 可声明 `p5_5d_slice_exit: pass`。
5E design/implementation、P5 整体架构收口与 production deployment 均不自动开放。

## 5. Test ownership and proportional scope

唯一权威测试 owner 以 [Design §9](p5-5d-archive-design.md#9-verification-ownership) 为准，
本计划不另建不变量注册系统。focused 文件组中旧 tests 是其原有行为的回归，不复制 Archive
矩阵。所有 nodeid 按业务行为命名，不按 S-stage/finding 名称；同构错误用模块级参数表。

三个高价值失败屏障足够指导第一轮：事务最终提交前失败全部 rollback；提交后进程/响应丢失原
key 恢复既有成功；与另一条 writer 的获胜顺序确定。只有发现独立漏洞/实际失败再增加有理由的
探针，不逐 SQL/syscall 注入。migration 用真实 SQLite 文件，关键 crash gate 不用 tmpfs 代替。

Archive 本地纯逻辑/SQLite tests 不引入 Dolt fixture；实际 Compose 使用现有 Submit 路径产生
真实 commit。依赖时间、Event/join 或子进程 timeout 的测试加 serial；repository_service 真实
Dolt 测试须 integration，按其 conftest gate；Backend 不加 xdist。未改测试分类不执行移走 Dolt
门禁；若后续确改 repository_service 分类则遵守 AGENTS 权威要求。

## 6. Commands, conjunction and running image provenance

### 6.1 Static and authoritative runner

提交前五包分别执行（不能只查 Backend；不更新依赖锁）：

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run ruff check .
./vnext/scripts/uv-consume.sh -C vnext/backend run mypy
./vnext/scripts/uv-consume.sh -C vnext/repository_service run ruff check .
./vnext/scripts/uv-consume.sh -C vnext/repository_service run mypy
./vnext/scripts/uv-consume.sh -C vnext/repository_client run ruff check .
./vnext/scripts/uv-consume.sh -C vnext/repository_client run mypy
./vnext/scripts/uv-consume.sh -C vnext/repository_contracts run ruff check .
./vnext/scripts/uv-consume.sh -C vnext/repository_contracts run mypy
./vnext/scripts/uv-consume.sh -C vnext/shared_kernel run ruff check .
./vnext/scripts/uv-consume.sh -C vnext/shared_kernel run mypy
./vnext/scripts/run-tests.sh
```

最后一条在 S4 最终候选运行，不每轮全量。不得用临时 `--ignore` 掩盖失败或依赖 ambient uv index
改写锁；记录所有 skip 原因，conjunction 必需项目不允许 skip。五锁 SHA 前后保持一致。

### 6.2 Fresh build and conjunction

已核查 `tests/support/compose_gate_harness.py` 的 `ensure_repository_service_image` 在 tag
存在时直接返回，`compose_image_ids` 只 inspect image tag，均不能单独证明 fresh build 或实际
运行镜像。先显式运行 `./vnext/scripts/build-repository-service-image.sh`（遵守现有 retained cache/
remote builder 前提），再以同一 project/config 环境运行
`docker compose -f vnext/deploy/compose.yaml build backend worker`；记录退出与 identity，
不得直接设置 PREBUILT 复用旧镜像。示例独立复跑命令（新 Archive 文件为本计划交付目标，当前不存在）：

```bash
cd vnext/backend
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5d-final-gate \
GATEWAY_COMPOSE_GATE_PREBUILT=1 \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
```

PREBUILT 仅用于已验证同一候选 fresh build 后的 conjunction/独立复跑，不是跳过构建的免责入口。
现有五个场景（5C 历史证据为 5 passed）全部保留：

- `test_compose_submit_to_review_approve_journey`。
- `test_compose_three_process_submit_stack_smoke_and_backend_restart`。
- `test_compose_accept_upload_import_poll_t3_read_journey`。
- `test_backend_image_builds_with_http_server_entrypoint`。
- `test_backend_container_ready_and_stops_cleanly_with_repository_service`。

新增 `test_archive_compose_e2e.py` 至少负责一个真实 Archive→下一 Preview→HTTP/worker restart
journey，可在同一案例串联以避免重复 provision。S3 明确 freeze 最终 nodeid 列表/数量，S4 记录
所有 nodeid、pass/skip、耗时、exit code；不能只写“六项通过”而遗漏具体 Archive 行为。

证明 Archive 零 Repository effect 的 observation window：先完成全部前置 Submit/Review、等待
无 active Attempt，记录技术 main 和 Repository commit 集合；仅执行 Archive/audit/只读预览并
再次读取，必须完全相同。新 Baseline commit 等于所选既有 commit；不能使用候选恰好等于 main
的单一案例掩盖 ref 移动，也不能把后续新 Submit 写入算作 Archive effect。窗口内 Backend
Operation 集合无新增 Archive operation。使用既有 repository read/test harness；测试观察不授权
生产后门或 Backend mount Repository volume。

### 6.3 Minimum provenance record

handoff 与 independent review 各记录一份简短记录，复用现有 harness/evidence 输出，不建新数据库：

| 证据 | 要求 |
| --- | --- |
| 候选 | 完整 Git HEAD、clean/dirty、必要 patch/source-tree 标识；最终实现候选不得有未记录 `vnext/**` 差异 |
| Source tree | 按路径排序 tracked `vnext/**`，每行 `path\tsha256\n` 后计算 SHA-256；路径数量、算法与输出一并记录 |
| 配置/依赖 | 五个 uv.lock SHA、Compose 文件/解析配置 digest（敏感值脱敏）、测试 harness revision、运行 project name |
| Fresh build | 本轮实际构建命令/exit、每服务 image ID、revision/source-tree labels、构建时间；相同 Dockerfile 的 backend/worker 仍分别绑定实际运行镜像 |
| Running containers | 每个场景或复用栈的实际 container ID、service、`.Image` immutable ID，在运行中采集；与 fresh build ID 对比，不能只读取 tag 的 image inspect |
| Conjunction | 精确 nodeids、环境/PREBUILT 使用前提、0 skipped、pass/exit/duration；独立复跑必须绑定相同 IDs，若重新构建则完整记录新 IDs 与同候选关系 |
| Runtime isolation | Backend CMD、readiness、clean-stop、non-root/shared control DB 与 Repository 独立 volume 等已有容器 owner 证据 |

每轮评审按 Testing Conventions 写 `Current HEAD / rebuild required / reason / last verified revision /
source-tree+image IDs / current gate / deferred nodeids / required execution point`。阶段内纯逻辑
iteration 可延期，但阶段最终候选和 S4 最终 conjunction 必须 fresh build。缺 Docker/依赖/资源时
标 blocked/deferred 并列缺口，不能把 5C accepted image 或 host-only tests 表述为当前 HEAD pass。

本轮 docs-only 的当前 HEAD 为 `16f4112ee1`，rebuild required=no；current container gate 为
not-applicable。最后被独立验证的镜像 revision 是 `04317788c2`，实际 IDs/source-tree 在
[5C Independent Acceptance](p5-5c-s5-independent-acceptance.md)；本轮没有运行这些容器。

## 7. Final exit evidence and stopping rules

最终 handoff 必须提供：

1. accepted docs review 的入口、后续明确 implementation authority、各阶段 candidate HEAD 与独立
   review、已关闭/未关闭 findings；未关闭 blocker 不建议 slice pass。
2. 三份设计与实际接口的差异说明：Candidate digest、audit validity、HTTP、schema/initial seed、
   public port/consumer；不得把未实现的规划能力列为已交付。
3. Start 成功一次性冻结 Plan/Result/Node/Head/disposition/release 的事务证明；same-key after-commit
   replay；三个并发竞争与 Review closure；新 base Preview/Submit 与旧 sibling 重新采用路径。
4. migration 数据前提/测试结果、反向 scope 基数的 owner Contract 决策、initial-empty 前置修复
   focused 证据与真实 provisioning journey；HTTP/worker restart 不回退；
   没有 production migration/deployment 的授权时明确只验证隔离测试环境。
5. 五包 static、focused owner、权威 runner、最终 fresh conjunction 与运行镜像 provenance，说明
   skip/延期与理由，必要 conjunction 任何 skip 都不能通过。
6. P5 §2A 增量未扩散证据及原有收口项的 owner/延期位置；占位 projection 无虚假依赖，未新增
   private import、wire 泄漏、基础层倒挂、反向 transaction→job 或无 consumer framework。
7. delivery 建议状态及独立 acceptance 待办；禁止交付者自签 `accepted` 或 `p5_5d_slice_exit: pass`。

全阶段停止条件：需要新 commit/Repository write/ref move、多 candidate merge、持久候选/执行
状态、另一 DB/broker/sidecar/outbox、跨 host writer、业务与技术 Head 合并、跨 scope 自动修复，
或者需要修改未授权源码/部署。先列出影响、owning Contract/ADR 冲突与最小替代方案，不静默
扩大预算。设计 §11 的审计/限额/迁移细化若后续独立 review 有不同决策，更新三份文档一致后再实现。

完成 5D 独立 exit 不代表 5E implementation、P5 整体架构收口或 production deployment 获授权。

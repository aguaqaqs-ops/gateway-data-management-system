# P5-5B Submit Acceptance and Finalize Execution Plan

状态：**EXECUTED — S8 gate pass；independent slice exit pass**

日期：2026-09-13

Exit acceptance：2026-09-18

计划基线 HEAD：`7e8cea7b3454a8cfdd7c2ba880becee5c427a0de`

Owner：P5-5B Delivery + Architecture Acceptance

设计输入：[P5-5B Submit/Finalize Detailed Design](p5-5b-submit-finalize-design.md)、
[P5-5B-S0 Entry Brief](p5-5b-s0-entry-brief.md)、
[Testing Conventions](../../../testing-conventions.md)、
[Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)

Finding输入：[P5-5B-S0 Independent Docs Review](p5-5b-s0-independent-docs-review.md)

本文给出未来获授权后的实施顺序、allowed paths、唯一test owner、验证和handoff gate。它不改变
owning contract，也不表示任何步骤已获实现授权或已执行。

## 1. Authority gate

以下 YAML 是计划起草时的 authority snapshot；执行后的当前状态见 §9 与 §11。

```yaml
plan_kind: p5_5b_submit_finalize_execution
plan_base_sha: 7e8cea7b3454a8cfdd7c2ba880becee5c427a0de
plan_status: candidate_draft
p5_5a_slice_exit: pass
p5_5b_s0_entry_brief: accepted
p5_5b_design_s0_authorized: yes
p4_r6_exit: pending
p5_5b_implementation_authorized: no
p5b_real_repository_effect_authorized: no
current_round_allowed_paths: [docs/**]
current_round_forbidden_paths: [vnext/**]
current_next_step: independent_docs_review
```

任何 S1–S8 implementation 工作开始前，独立 gate 必须在同一 current HEAD 明确记录：

```yaml
p4_r6_exit: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
p5b_real_repository_effect_authorized: yes
unresolved_contract_drift: none
first_authorized_step: P5-5B-S1
```

缺任一项即只允许 docs review/修订。特别是 `p5b_real_repository_effect_authorized=yes` 不能由
implementation authorization、P4/P5历史测试或本plan推导。若P4-R6改变Operation/Step/lease/
checkpoint/recovery语义，先reopen design，不开始S1。

## 2. Global execution rules

- 顺序执行S0 review → S1 domain/application → S2 persistence/T1/T3 UoW → S3 artifact builder →
  S4 HTTP → S5 JobDefinition/effect/recovery → S6 runtime/deployment → S7 independent functional
  acceptance/remediation → S8 final current-HEAD gate/handoff。
- 每阶段只改本节allowed paths；未列路径禁止。需要越界先停止并修订plan/authority，不以“顺手
  修复”扩大范围。
- 所有implementation阶段都禁止修改owning contract语义、Repository public wire、P4 runtime
  protocol、dependency/lockfile。若确需修改，触发reopen而非本slice remediation。
- 阶段性只跑focused范围；不在每阶段跑全量或重建镜像。五包static、权威runner和current-HEAD
  container gate在规定节点执行。
- 测试按业务行为命名；同构shape使用模块级共享参数表；每个不变量只有§4一个权威owner，其他层
  只做integration smoke。
- 后续真正执行时保留用户既有worktree改动，不以reset/checkout清理；handoff记录exact HEAD、
  changed paths、test commands/results、container decision和deferred/reopen。

所有阶段持续禁止：

```text
vnext/repository_contracts/**
vnext/repository_client/**
vnext/repository_service/**
vnext/shared_kernel/**
vnext/rust/**
dependency manifests and lockfiles
Repository public route/request/result changes
P4 Operation/Step state, lease, checkpoint envelope or recovery protocol changes
new broker/outbox/external DB/UID/helper/service/IPC/evidence state machine
```

现有Repository client已经提供所需upload/import/get-operation/resolve-ref wire；任何发现要求修改上列
路径，必须判断为contract drift/reopen。S6对现有Docker/Compose文件的条件性接线是唯一deployment
例外，不授权依赖或Repository Service source变化。

## 3. Stage plan

### S0 — Independent docs review

目标：对两份candidate做authority-first、findings-first review；不实现。

Allowed paths：

```text
docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md
docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p5-5b-s0-*-review.md
```

Forbidden：`vnext/**`、测试、migration、依赖、Docker、Compose、settings、deployment。

Reviewer必须逐项核对：owner重复、T1/T2/T3、四态、exact Repository wire、P4 identity/recovery、
artifact authority/nominal refs、deployment/trust boundary、test owner重复、授权前置。输出`pass`或
有编号且映射到accepted authority的findings；不能自行授权implementation。

Exit/handoff：review document记录candidate HEAD、reviewer context、findings、decision、
`p5_5b_design=accepted|changes_required`和仍为no的两项implementation authority。若changes required，
只在上述两份candidate做finding-scoped修订并重新独立review。

### S1 — Submission domain and application contracts

Entry：§1全部implementation gate已pass，S0 design accepted。

Allowed paths：

```text
vnext/backend/src/gateway_backend/domain/submission/**
vnext/backend/src/gateway_backend/domain/__init__.py
vnext/backend/src/gateway_backend/application/submission/**
vnext/backend/src/gateway_backend/application/__init__.py
vnext/backend/tests/test_submit_domain.py
vnext/backend/tests/test_submit_application.py
vnext/backend/tests/test_submit_idempotency.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p5-5b-s1-*.md
```

Deliver：SubmitAttempt/Submission immutable types、four-state guards、Accept/T3 ports、fingerprint、
effect-key derivation、occupancy commands、owner-specific errors。使用in-memory fakes证明纯业务行为，
不接SQLite/HTTP/Repository。

Focused gate：

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_submit_domain.py \
  tests/test_submit_application.py \
  tests/test_submit_idempotency.py \
  tests/test_architecture.py
uv run ruff check src/gateway_backend/domain/submission \
  src/gateway_backend/application/submission \
  tests/test_submit_domain.py tests/test_submit_application.py \
  tests/test_submit_idempotency.py
uv run mypy
```

Exit/handoff：`p5-5b-s1-handoff.md`，随后不同conversation/context独立review。S1不声明T1 SQLite
atomicity或真实Repository effect。

### S2 — Control DB schema, repositories and T1/T3 UoW

Entry：S1 independent pass。

Allowed paths：

```text
vnext/backend/src/gateway_backend/infrastructure/control_db/migrations.py
vnext/backend/src/gateway_backend/infrastructure/control_db/database.py
vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py
vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_workspace.py
vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_mapping.py
vnext/backend/src/gateway_backend/infrastructure/control_db/__init__.py
vnext/backend/src/gateway_backend/domain/workspace/models.py
vnext/backend/src/gateway_backend/domain/workspace/ports.py
vnext/backend/src/gateway_backend/application/submission/**
vnext/backend/tests/test_submit_control_db_migrations.py
vnext/backend/tests/test_sqlite_submit_repository.py
vnext/backend/tests/test_submit_transactions.py
vnext/backend/tests/test_sqlite_workspace_repository.py
vnext/backend/tests/test_workspace_control_db_migrations.py
docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-*.md
```

Deliver：additive Workspace schema v3、Attempt/Submission/idempotency/two occupancy relations、artifact
protection intents、single SQLite UoW。Migration重开DB后验证FK/unique/check/version；发现existing
integrity冲突fail closed，不自动选择winner。Repository resolve/artifact I/O使用fake preflight，
不在transaction内。

Focused gate：

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py \
  tests/test_submit_transactions.py \
  tests/test_sqlite_workspace_repository.py \
  tests/test_workspace_control_db_migrations.py
uv run ruff check src/gateway_backend/infrastructure/control_db \
  src/gateway_backend/application/submission \
  tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py tests/test_submit_transactions.py
uv run mypy
```

Marker：当前项目把isolated local SQLite repository/migration归为`unit`；若新增test依赖真实process、
fixed timing或non-isolated落盘语义，按§5升级而不是沿用文件默认。

Exit/handoff：记录T1/T3 transaction matrix、concurrency winner、migration reopen、rollback evidence；
独立review必须检查没有先读后写替代unique/CAS。

### S3 — Import builder and artifact boundary

Entry：S2 independent pass。

Allowed paths：

```text
vnext/backend/src/gateway_backend/application/submission/import_builder.py
vnext/backend/src/gateway_backend/application/submission/contracts.py
vnext/backend/src/gateway_backend/repository_import_artifact.py
vnext/backend/src/gateway_backend/artifacts/**
vnext/backend/tests/test_submit_import_builder.py
vnext/backend/tests/test_repository_import_artifact_package.py
vnext/backend/tests/test_submit_artifact_protection.py
vnext/backend/tests/test_artifact_boundary.py
docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-*.md
```

`capabilities/storage_projection/**`和`capabilities/mutation_planning/**`只作为public dependency，
不在S3 allowed paths；现有capability有缺口则reopen owner，不在consumer内复制语义。

Deliver：REBUILD_ALWAYS adapter、manifest-first/package-second publication、one durable package identity、
BackendArtifactRef/RepositoryArtifactRef nominal ports、pin transfer/release application integration。不得
调用Repository Service。

Focused gate：

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_submit_import_builder.py \
  tests/test_repository_import_artifact_package.py \
  tests/test_submit_artifact_protection.py \
  tests/test_artifact_boundary.py
uv run ruff check src/gateway_backend/application/submission \
  src/gateway_backend/repository_import_artifact.py \
  tests/test_submit_import_builder.py tests/test_submit_artifact_protection.py
uv run mypy
```

Exit/handoff：记录published ref/raw SHA复用、orphan边界、nominal type negative tests；独立review确认
未建立generic refcount/GC或第二canonical owner。

### S4 — Backend HTTP v1 and re-authorization

Entry：S3 independent pass。

Allowed paths：

```text
vnext/backend/src/gateway_backend/http/routes/submit_attempts.py
vnext/backend/src/gateway_backend/http/routes/submissions.py
vnext/backend/src/gateway_backend/http/routes/operations.py
vnext/backend/src/gateway_backend/http/routes/operator_recovery.py
vnext/backend/src/gateway_backend/http/schemas/submit.py
vnext/backend/src/gateway_backend/http/schemas/operator_recovery.py
vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py
vnext/backend/src/gateway_backend/http/orchestration/operation_scope.py
vnext/backend/src/gateway_backend/http/orchestration/operator_recovery.py
vnext/backend/src/gateway_backend/http/auth.py
vnext/backend/src/gateway_backend/http/dependencies.py
vnext/backend/src/gateway_backend/http/errors.py
vnext/backend/src/gateway_backend/http/wiring.py
vnext/backend/tests/test_submit_http.py
vnext/backend/tests/test_submit_read_http.py
vnext/backend/tests/test_operator_recovery_http.py
vnext/backend/tests/test_operation_http.py
vnext/backend/tests/test_http_auth_matrix.py
vnext/backend/tests/test_http_openapi.py
docs/backend-vnext/refactoring/formal/plans/p5-5b-s4-*.md
```

Deliver：terminal-user exact routes、closed DTO、header-only Accept key、status/error mapping、Operation
business-ref authorization，以及
`POST /internal/v1/operations/{operation_id}/steps/{step_id}/recovery`的existing-internal-bearer auth、
closed path/body identity、P4 capability rejection、success/replay/conflict mapping和OpenAPI path closure。
Admin route在S4使用fake recovery application port，不执行真实Repository effect；T1 dependencies使用
fakes或S2 local UoW。

Focused gate：

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_submit_http.py \
  tests/test_submit_read_http.py \
  tests/test_operator_recovery_http.py \
  tests/test_operation_http.py \
  tests/test_http_auth_matrix.py \
  tests/test_http_openapi.py
uv run ruff check src/gateway_backend/http tests/test_submit_http.py \
  tests/test_submit_read_http.py tests/test_operator_recovery_http.py
uv run mypy
```

Exit/handoff：附OpenAPI exact-path/unknown-field/status证据、每次read current-session matrix及admin
bearer/path-body/version/capability negative matrix；独立review检查没有把domain/Operation/Repository DTO
直接暴露为HTTP response，也没有让internal route绕过P4 guard。

### S5 — Submit JobDefinition, Repository effect and recovery

Entry：S4 independent pass；再次审计`p5b_real_repository_effect_authorized=yes`和P4-R6 lineage。

Allowed paths：

```text
vnext/backend/src/gateway_backend/application/submit_jobs.py
vnext/backend/src/gateway_backend/application/submit_registry.py
vnext/backend/src/gateway_backend/application/submission/**
vnext/backend/src/gateway_backend/infrastructure/repository_write/**
vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
vnext/backend/tests/test_submit_job_payload.py
vnext/backend/tests/test_submit_job_prepare.py
vnext/backend/tests/test_submit_job_effect.py
vnext/backend/tests/test_submit_finalize.py
vnext/backend/tests/test_submit_recovery.py
vnext/backend/tests/test_submit_worker.py
vnext/backend/tests/test_operation_effect_reconcile.py
vnext/backend/tests/test_operation_job_recovery.py
docs/backend-vnext/refactoring/formal/plans/p5-5b-s5-*.md
```

P4 core files`operations/**`、`application/recovery.py`和Repository packages仍禁止修改；5B通过既有
ports/composition使用它们。若现有protocol无法表达original-identity recovery，停止并reopen。

Deliver：三步static topology、closed payload/three checkpoint decoders、production handler registry、
Repository Client adapter、exact upload/import wire、poll/reconcile、matching T3和stable abort。
`prepare_import(PURE_RECOMPUTE)`只接受`RETRY_FROM_CHECKPOINT`；`submit_import`/
`await_import_result(EXTERNAL_EFFECT)`只接受`RESUME_RECONCILE`。Admin abort application adapter必须先
验证matching Repository Operation的三个普通未发布stable failure之一；`PRE_REQUEST`、
`request_sent=false`或未捕获operation identity均不得释放occupancy。真实Repository/Dolt tests只在
此阶段授权后出现。

Focused gates：

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_submit_job_payload.py \
  tests/test_submit_job_prepare.py \
  tests/test_submit_finalize.py
uv run pytest -q -m 'integration and not serial' \
  tests/test_submit_job_effect.py \
  tests/test_submit_recovery.py \
  tests/test_submit_worker.py
uv run pytest -q -m serial \
  tests/test_submit_recovery.py \
  tests/test_submit_worker.py
uv run ruff check src/gateway_backend/application/submit_jobs.py \
  src/gateway_backend/application/submit_registry.py \
  src/gateway_backend/infrastructure/repository_write \
  tests/test_submit_job_payload.py tests/test_submit_job_effect.py \
  tests/test_submit_finalize.py tests/test_submit_recovery.py
uv run mypy
```

Integration tests使用真实Repository Service/Dolt或process；fixed timeout/crash/lease/restart cases额外
标`serial`。不得给Backend包命令加xdist。

Exit/handoff：记录Repository operation IDs/commit/ref evidence、all fault barriers、manual recovery、
no-blind-replay/unknown-outcome-retains-occupancy negative tests、逐Step operator capability mapping和T3
response-loss；独立review必须区分Repository success与business finalize。

### S6 — Readiness, shutdown, settings and deployment wiring

Entry：S5 independent pass。

Allowed paths（仅为本阶段确有需要的最小diff）：

```text
vnext/backend/src/gateway_backend/app.py
vnext/backend/src/gateway_backend/settings.py
vnext/backend/src/gateway_backend/http/dependencies.py
vnext/backend/src/gateway_backend/http/wiring.py
vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
vnext/backend/tests/test_backend_settings.py
vnext/backend/tests/test_backend_readiness.py
vnext/backend/tests/test_http_admission_shutdown.py
vnext/backend/tests/test_production_wiring.py
vnext/backend/tests/test_submit_worker_process.py
vnext/backend/tests/test_submit_compose_e2e.py
vnext/backend/Dockerfile
vnext/deploy/**
docs/backend-vnext/refactoring/formal/plans/p5-5b-s6-*.md
```

Dockerfile/Compose只能为已设计的registry、settings、health/readiness、mount/signal和三进程journey接线；
不借机改base image/dependencies/network/trust shape。若现有image无需Dockerfile变化，保持不改，但
S6结束仍因deployment boundary和最终gate触发current-HEAD rebuild。

Deliver：Backend/worker同composition、Repository readiness、new-work drain、worker checkpoint/drain、
container environment/mount/secret接线、三进程smoke harness。

Focused gates：

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_backend_settings.py \
  tests/test_backend_readiness.py \
  tests/test_http_admission_shutdown.py \
  tests/test_production_wiring.py
uv run pytest -q -m serial \
  tests/test_submit_worker_process.py
uv run ruff check .
uv run mypy
```

S6 handoff记录container rebuild required=yes、reason、current HEAD、expected image provenance和S8
deferred nodeids；独立review先检查wiring，S6不以旧image关闭finding。

### S7 — Independent functional acceptance and scoped remediation

Entry：S1–S6 handoff/independent reviews全部pass。

Allowed paths：默认仅`docs/backend-vnext/refactoring/formal/plans/p5-5b-s7-*.md`。Reviewer只读全部
implementation和owner tests。发现问题后，remediation allowed paths必须逐finding写入review，且
只能来自该finding原owner阶段的allowed paths；其余路径继续禁止。

Review matrix：T1/no-change/idempotency/CAS/pin；exact Repository wire；builder/ref types；payload/
checkpoints；effect/reconcile；T3/abort；response-loss/PRE_REQUEST不释放；admin exact HTTP/internal bearer/
path-body/CAS/error；逐Step P4 capability guard；crash/takeover/late writer/restart；reauthorization；
readiness/shutdown；mechanism exclusions。

每个finding必须包含authority、business consequence、risk class、exact path、unique test owner、
focused retest。只在更强未接受threat model下成立的finding记录为reopen candidate，不是当前release
blocker。Remediation不得新增round/finding命名test、复制矩阵或扩大状态机。

Exit：all findings closed并由原independent reviewer复核；形成S7 acceptance，不授权省略S8。

### S8 — Final current-HEAD gate and slice handoff

Entry：S7 pass，worktree candidate内容完整且可追溯。

Allowed paths：默认只读验证和以下handoff docs：

```text
docs/backend-vnext/refactoring/formal/plans/p5-5b-s8-handoff.md
docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md
docs/backend-vnext/refactoring/formal/README.md
docs/backend-vnext/README.md
```

任何测试失败修复必须回到finding-scoped remediation和原阶段allowed paths，不能在gate现场自由改码。

Final gate顺序：focused accumulated Submit suite → Backend unit/integration/serial → five-package static →
无ignore权威runner → current-HEAD images/Compose/effect/restart smoke → provenance/diff检查。

Exit handoff必须记录：candidate/implementation HEAD、clean status、changed paths、各命令exact结果、
authority audit、review findings、current source-tree digest、每个image ID/source、Compose digest、
container conjunction、deferred/reopen和next authorization。只有全部pass才能建议5B slice exit；不能
自行授权5C或production release。

## 4. Unique test owner matrix

下表是权威断言owner；integration/Compose只能证明wiring，不复制完整组合矩阵。

| Invariant | Unique authoritative test owner | Marker |
| --- | --- | --- |
| Attempt fields/four states/illegal edges | `test_submit_domain.py` | unit |
| Submission immutable + unique Attempt binding at domain boundary | `test_submit_domain.py` | unit |
| accept/effect key derivation and effective fingerprint | `test_submit_idempotency.py` | unit |
| validation order and no-main-resolve on replay/no-change | `test_submit_application.py` | unit |
| same/same, same/different and new-key behavior | `test_submit_idempotency.py` | unit |
| T1 all-or-nothing Attempt+Operation+occupancy+pin | `test_submit_transactions.py` | unit |
| concurrent Workspace/Repository occupancy winner | `test_submit_transactions.py` | unit |
| T3 exactly-one Submission + Workspace switch + repository release | `test_submit_transactions.py` | unit |
| matching stable abort transaction | `test_submit_transactions.py` | unit |
| schema v3 forward migration/reopen/integrity | `test_submit_control_db_migrations.py` | unit |
| SQL row/closed-document roundtrip and optimistic CAS | `test_sqlite_submit_repository.py` | unit |
| REBUILD_ALWAYS mapping and one published package identity | `test_submit_import_builder.py` | unit |
| formal v1 package bytes/shape/determinism | `test_repository_import_artifact_package.py` | unit |
| Preview→Attempt transfer and terminal pin release | `test_submit_artifact_protection.py` | unit |
| Backend/Repository ref nominal separation | `test_artifact_boundary.py` | unit |
| Accept route/body/header/status/stable immediate errors | `test_submit_http.py` | unit |
| Attempt/Submission every-read reauthorization and redaction | `test_submit_read_http.py` | unit |
| Submit Operation current-session authorization | `test_operation_http.py` | unit |
| Internal recovery route/bearer/closed DTO/path-body/version/status/errors | `test_operator_recovery_http.py` | unit |
| Operator command/capability rejection matrix | `test_operator_recovery_http.py` | unit |
| OpenAPI exact paths/closed DTO | `test_http_openapi.py` | unit |
| payload/decoder/version/three-step registry | `test_submit_job_payload.py` | unit |
| prepare checkpoint/ref reuse | `test_submit_job_prepare.py` | unit |
| exact Repository path/body/header and operation identity | `test_submit_job_effect.py` | integration |
| matching result/business closure and Finalize replay | `test_submit_finalize.py` | unit |
| request/response loss, poll/reconcile, no blind replay and unknown-outcome occupancy retention | `test_submit_recovery.py` | integration; timing/crash cases serial |
| duplicate delivery/lease loss/late writer | `test_submit_worker.py` | integration; fixed timing cases serial |
| Repository restart and matching marker outcome | `test_submit_recovery.py` | integration + serial |
| T3 commit before worker ack crash barrier | `test_submit_recovery.py` | integration + serial |
| allowed operator command to business terminal/occupancy effect | `test_submit_recovery.py` | integration |
| settings/registry production composition | `test_production_wiring.py` | unit |
| Backend/worker/Repository readiness semantics | `test_backend_readiness.py` | unit |
| admission-first shutdown | `test_http_admission_shutdown.py` | unit |
| real process signal/drain/checkpoint | `test_submit_worker_process.py` | integration + serial |
| three-container real submit/restart journey | `test_submit_compose_e2e.py` | integration + serial |
| no forbidden dependency/mechanism expansion | `test_architecture.py` | unit |

Repository Service自身CAS/marker/recovery/package安全继续由其现有contract tests唯一拥有；P5B
`test_submit_job_effect.py`只证明consumer mapping和cross-service journey，不复制Service内部矩阵。

## 5. Marker and test construction rules

- `unit`：pure domain/DTO/decoder/fingerprint/fake ports、isolated local SQLite、artifact tempdir且无真实
  Dolt/process/network/fixed timing。
- `integration`：真实Repository/Dolt、subprocess、network或需要真实process/durable reopen的test。
- `serial`：任何Event.wait/thread.join、lease timeout、crash/restart、signal、Docker/Compose或依赖
  fixed relative timing的test；需要外部依赖时同时标integration。
- Backend和其余非Repository-Service package单进程，不添加xdist。Repository Service marker/xdist
  只由权威runner及其conftest管理。
- Pure DTO/parser/nominal type tests不得使用真实Dolt fixture。相同payload/error只用模块级共享
  parameter table。构造Repository状态按批，不循环spawn。任何新Dolt HOME使用既有versioncheck-off
  seed路径。

## 6. Verification ladder

### 6.1 Focused and accumulated

各阶段执行§3列出的focused commands。S5后维护一个accumulated Submit selection，只包含§4 owner
files；每个remediation至少重跑finding owner file、直接integration smoke和所有已受影响stage files。
不以一次通过的祖先结果代表新HEAD。

### 6.2 Five-package static gate

S7收口后、S8 current HEAD执行五包ruff/mypy：

```bash
(cd vnext/backend && uv run ruff check . && uv run mypy)
(cd vnext/shared_kernel && uv run ruff check . && uv run mypy)
(cd vnext/repository_contracts && uv run ruff check . && uv run mypy)
(cd vnext/repository_client && uv run ruff check . && uv run mypy)
(cd vnext/repository_service && uv run ruff check . && uv run mypy)
```

### 6.3 Authoritative runner

S8必须从仓库根运行无`--ignore`的唯一权威入口：

```bash
./vnext/scripts/run-tests.sh
```

不得用裸pytest、focused通过或历史P4/P5A结果替代。若临时调worker/base temp，只能使用AGENTS和
Testing Conventions已允许的环境变量并在handoff记录exact command。

### 6.4 Current-HEAD container gate

S6触碰container/deployment boundary，S8必须对最终HEAD重建并记录provenance：

```bash
cd vnext/deploy
docker compose build backend worker repository-service
docker compose up -d
```

Gate至少证明Backend `/healthz`/`/readyz`、worker ready、Repository Service ready、真实
Accept→upload→import→poll→T3→read、Backend/worker/Repository restart recovery、T3 response-loss
fixture、日志脱敏和clean shutdown。运行后按harness正常`docker compose down`并确认资源清理。
正式命令/fixture由S6在现有deployment convention内冻结；本draft不声称这些命令已运行。

Handoff必须包含：current HEAD、source-tree digest、Compose digest、三image ID及其source identity、
是否fresh rebuild、smoke nodeids/结果。任一image不是current HEAD对应build input则gate=`stale`。

### 6.5 Documentation/static hygiene

每份handoff和最终candidate运行Markdown local-link/fence检查、`git diff --check`、`git status --short`
和`git rev-parse HEAD`。这些不替代Python/static/container gates。

## 7. Handoff and independent review protocol

每阶段handoff至少包含：

```yaml
stage:
candidate_head:
input_authority:
scope_paths:
changed_paths:
invariants_delivered:
unique_test_owners:
focused_commands_and_results:
five_package_static: pass | deferred
authoritative_runner: pass | deferred
container_rebuild_required: yes | no
container_reason:
last_verified_image_revision:
container_gate_for_current_head: passed | deferred | stale | not_applicable
findings:
deferred:
reopen_required:
implementation_authority_unchanged: true
next_step:
```

Independent review必须由不同conversation/context执行，先核authority/changed paths，再findings-first
审阅实现和唯一owner tests。Review不能修改production代码或把建议直接标pass；它输出明确
`pass|changes_required|reopen`。

Finding-scoped remediation规则：

1. finding引用accepted authority、具体可复现失败和risk class；
2. review先指定唯一test owner和允许修改paths；
3. remediation只改这些paths，不做邻近cleanup/refactor；
4. 新test按业务行为命名并检查是否与§4重复；
5. 重跑owner focused + affected integration + static；触碰deployment则当前HEAD container gate不能延期；
6. 原reviewer复核closure；新发现另立finding，不静默扩大旧finding；
7. 若修复需要改变contract/state/wire/trust/deployment shape，结论为reopen而非remediation。

## 8. Stop/reopen and final exit

立即stop/reopen条件与详细设计§14一致，另外包括：allowed path不足、依赖/lockfile变化、P4-R6
lineage或schema base变化、需要修改Repository packages、测试只能靠新增private interleaving/evidence
framework证明、container支持面超出现有single-host local volume。

S8 exit要求所有contract barrier有且仅有一个test owner、independent findings closed、五包static与
无ignore权威runner pass、current-HEAD三image/container journey pass、authority/provenance完整。
即使全部通过，handoff也只能建议`p5_5b_slice_exit=pass`并把下一步交给独立acceptance authority；
不得自行授权implementation（本轮）、5C、production deployment或任何新Repository effect。

## 9. Current handoff

```yaml
stage: P5-5B-S8-final-current-head-gate
candidate_head: 460d6f5b1efdb24199534778bd5cc9d4a8131d13
gate_tested_head: 460d6f5b1efdb24199534778bd5cc9d4a8131d13
test_hygiene_fix_seal: 460d6f5b1efdb24199534778bd5cc9d4a8131d13
handoff: docs/backend-vnext/refactoring/formal/plans/p5-5b-s8-handoff.md
implementation_seal: e5c43c0c9f71de3cd2e602504ec9034f16add8af
test_evidence_seal: d3661fe0eda4a3463afed879c6a5bbec72f79404
s7_f2_remediation_seal: 4d1dc010deff17249bb2aa54b7563e7a86959096
s7_f2_closure_review: docs/backend-vnext/refactoring/formal/plans/p5-5b-s7-independent-review-8.md
s8_f1_closure_review: docs/backend-vnext/refactoring/formal/plans/p5-5b-s8-independent-review-1.md
five_package_static: pass
authoritative_runner: pass
container_gate_for_current_head: passed
findings_closed: [S7-F2, S8-F1]
findings_open: []
p5_5b_slice_exit: pass
independent_exit_acceptance: docs/backend-vnext/refactoring/formal/plans/p5-5b-s8-independent-acceptance.md
p5_5c_authorized: no
production_deployment_authorized: no
next_step: separate_p5_5c_entry_authorization
```

## 10. S0 finding-scoped remediation

| Finding | Design/plan closure | Unique verification owner |
| --- | --- | --- |
| S0-F1 | 删除PRE_REQUEST abort authority；只有matching Repository普通未发布stable failure允许business abort；response loss继续原identity reconcile | `test_submit_transactions.py`正向；`test_submit_recovery.py`unknown-outcome反向 |
| S0-F2 | S4增加Submit-only internal recovery exact route、existing bearer、closed DTO、path/body、CAS、status/error/redaction | `test_operator_recovery_http.py` |
| S0-F3 | prepare只允许RETRY_FROM_CHECKPOINT；两个external step只允许RESUME_RECONCILE；错误组合fail closed且P4 core禁止修改 | `test_operator_recovery_http.py` wire/guard；`test_submit_recovery.py` external identity |

```yaml
input_review_decision: changes_required
findings_addressed: [S0-F1, S0-F2, S0-F3]
owning_contract_reopen: not_required
implementation_authority_changed: false
candidate_status: candidate_draft_pending_new_independent_review
next_step: new_independent_docs_review
```

## 11. Independent slice exit acceptance

[P5-5B-S8 Independent Slice Exit Acceptance](p5-5b-s8-independent-acceptance.md) 对
`gate_tested_head: 460d6f5b`、container evidence、S7-F2/S8-F1 closure、当前 implementation
identity 与 provenance 完成独立复核，结论为：

```yaml
p5_5b_slice_exit: pass
p5_5c_authorized: no
production_deployment_authorized: no
next_step: separate_p5_5c_entry_authorization
```

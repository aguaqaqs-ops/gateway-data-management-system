# P5-5C Review Execution Plan

状态：**IMPLEMENTATION AUTHORIZED — S1 IN PROGRESS**

日期：2026-09-19

Owner：P5-5C Delivery + Architecture Acceptance

入口：[P5-5C-S0 Entry Brief](p5-5c-s0-entry-brief.md)

设计：[P5-5C Review Detailed Design](p5-5c-review-design.md)

权威上游：[P5-5B-S8 Independent Slice Exit Acceptance](p5-5b-s8-independent-acceptance.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)

## 1. Authority and entry gate

```yaml
plan_kind: p5_5c_review_execution
authority_base_sha: a7ed4090bd1e182a77aff074ac9573692cfce9d6
implementation_head: 0e9c131b6c90bd7f32c8cac886896740bbb99215
p5_5b_slice_exit: pass
p5_5c_s0_entry_authorized: yes
p5_5c_design_s0_authorized: yes
p5_5c_design: accepted
p5_5c_design_status: accepted
p5_5c_implementation_authorized: yes
source_or_test_change_authorized: true
unresolved_contract_drift: none
first_authorized_step: P5-5C-S1
repository_effect_authorized: false
production_deployment_authorized: false
```

本计划描述未来获权后的实施顺序，不自行授权任何 implementation。开始 S1 前必须由 independent
docs review 接受 detailed design 与本 execution plan，并由 repository owner 在同一 current HEAD
明确记录：

```yaml
p5_5b_slice_exit: pass
p5_5c_design: accepted
p5_5c_implementation_authorized: yes
source_or_test_change_authorized: true
unresolved_contract_drift: none
first_authorized_step: P5-5C-S1
```

缺任一项时只允许 docs/review/authority 工作。实现授权也不自动授权 production deployment、P5-5D、
P5-5E 或任何 Repository effect。

## 2. Delivery principles

- 严格按 `S1 -> S2 -> S3 -> S4 -> S5` 交付；每阶段形成 handoff，由新的独立 context 复核后再进入下一阶段。
- Review 只使用现有 Backend + SQLite/WAL；不得引入 Operation、worker job、outbox、broker 或 Repository call。
- 同一不变量只有一个测试 owner；跨层测试只验证 seam，不复制 domain/transaction矩阵。
- S1–S4 阶段性验证按 focused 范围；S5 才运行五包 static、权威 runner、fresh current-HEAD images 和容器 journey。
- 不改任何 `uv.lock` 或依赖；若实现发现必须改依赖，停止并重新授权 dependency scope。
- migration、HTTP route、session config 和最终 slice gate 触发 current-HEAD image rebuild，旧镜像结果不能作为最终证据。

## 3. Planned path budget

### 3.1 Production paths

```text
vnext/backend/src/gateway_backend/domain/submission/__init__.py
vnext/backend/src/gateway_backend/domain/submission/errors.py
vnext/backend/src/gateway_backend/domain/submission/review.py
vnext/backend/src/gateway_backend/domain/submission/ports.py
vnext/backend/src/gateway_backend/application/submission/__init__.py
vnext/backend/src/gateway_backend/application/submission/errors.py
vnext/backend/src/gateway_backend/application/submission/review_contracts.py
vnext/backend/src/gateway_backend/application/submission/review.py
vnext/backend/src/gateway_backend/application/submission/review_transaction.py
vnext/backend/src/gateway_backend/application/submission/finalize_transaction.py
vnext/backend/src/gateway_backend/application/submission/ports.py
vnext/backend/src/gateway_backend/infrastructure/control_db/migrations.py
vnext/backend/src/gateway_backend/infrastructure/control_db/database.py
vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_review.py
vnext/backend/src/gateway_backend/http/dependencies.py
vnext/backend/src/gateway_backend/http/errors.py
vnext/backend/src/gateway_backend/http/orchestration/review.py
vnext/backend/src/gateway_backend/http/routes/reviews.py
vnext/backend/src/gateway_backend/http/schemas/review.py
vnext/backend/src/gateway_backend/http/wiring.py
vnext/deploy/config/session.json
```

Composition 决策已冻结：Review 完全复用现有 `WorkspaceHttpDependencies` 中的 session、scope、
Workspace/Submission read、control UoW、admission gate 与 clock，不增加 Review-specific application
dependency，也不修改 `bootstrap/http_server.py` 或 `http/runtime.py`。因此不存在独立的“Review
composition missing”状态；`tests/test_production_wiring.py` 只证明 production runtime 通过现有 bundle
可达 Review route。若实现发现必须增加 Review-specific dependency，停止当前 stage，将
`http/runtime.py` 加入重新授权后的 path budget，再补 fail-closed wiring contract。

现有 dependency bundle 的 `unit_of_work_factory` 静态类型改为 application ports 定义的组合
`WorkspaceControlUnitOfWorkFactory`；其 transaction 同时满足既有 Submit 与新增 Review protocol。
production 继续注入同一个返回 `ControlDbUnitOfWork` 的 callable，不新增 dependency 字段、不做
unchecked cast，也不要求修改 runtime composition。

Review transition errors 放入现有 `domain/submission/errors.py`，`ReviewIntegrityFailure` 等 application
typed errors 放入现有 `application/submission/errors.py`。`http/errors.py` 只添加 stable mapping，不改
全局错误 envelope。

### 3.2 Test paths

```text
vnext/backend/tests/test_review_domain.py
vnext/backend/tests/test_review_persistence.py
vnext/backend/tests/test_review_transactions.py
vnext/backend/tests/test_review_http.py
vnext/backend/tests/test_review_compose_e2e.py
vnext/backend/tests/test_submit_transactions.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_http_openapi.py
vnext/backend/tests/test_production_wiring.py
vnext/backend/tests/support/http_workspace_harness.py
vnext/backend/tests/support/runtime_settings.py
```

Existing test/support files只允许为 Review seam、fixture permission 或 current production composition
做最小修改；不得复制已有 Submit journey/assertion matrix。

### 3.3 Docs/handoff paths

```text
docs/backend-vnext/refactoring/formal/plans/p5-5c-*.md
docs/backend-vnext/refactoring/formal/plans/p5-business-vertical-slices-design.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md
docs/backend-vnext/refactoring/formal/README.md
docs/backend-vnext/README.md
```

### 3.4 Forbidden by default

```text
vnext/shared_kernel/**
vnext/repository_contracts/**
vnext/repository_client/**
vnext/repository_service/**
vnext/backend/src/gateway_backend/operations/**
vnext/backend/src/gateway_backend/artifacts/**
vnext/deploy/compose.yaml
vnext/**/pyproject.toml
vnext/**/uv.lock
```

若 Review 需要触碰 forbidden path，必须停止当前 stage，说明具体 contract/consumer/risk，更新设计并
取得 finding-scoped 新授权；不得以“顺手复用”扩大 Slice。

## 4. S1 — Domain model, transition policy and application contracts

### Objective

交付纯 Review domain/application contract，不接 SQLite、HTTP 或 runtime wiring。

### Deliverables

- `ReviewStatus`、`ReviewEventKind`、immutable `ReviewEvent`、`ReviewProjection`、
  `ReviewIdempotencyRecord`；
- `ReviewAction`、`ApplyReviewCommand/Result`、`ReviewFacts`；
- transition policy 与 exact reason/key character and length contract；
- Review read/write/UoW ports，以及兼容既有 Submit consumer 的组合
  `WorkspaceControlTransaction` / `WorkspaceControlUnitOfWorkFactory`；
- versioned closed-object RFC 8785 JCS/SHA-256 request fingerprint builder；
- public exports only，禁止 import FastAPI/sqlite3/operations/repository client。

### Semantic barriers

- seed only maps `null -> PENDING`；
- `PENDING` 四条 direct transition；
- `APPROVED -> RETURNED_FOR_REVISION` only；
- terminal/new-key command rejected；
- invalid reason/action/status/version fail before persistence；
- reason 原样 round-trip，trim/Unicode normalization 不改变校验或 fingerprint；
- fingerprint golden 固定 exact object、contract version 和
  `sha256:f97a6da6f2c568efdbbecdf64b6687593f5dc10b708cca81e602ba1a4e77b909`；
- no start-review/intermediate state。

### Unique test owner

`tests/test_review_domain.py`

使用模块级共享 transition table覆盖 allowed/denied matrix，不为每个 payload复制测试函数。

### Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit tests/test_review_domain.py tests/test_architecture.py
../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/domain/submission \
  src/gateway_backend/application/submission tests/test_review_domain.py
../scripts/uv-consume.sh -C . run mypy
```

### Exit

`p5-5c-s1-handoff.md` 记录 changed paths、focused results、无 forbidden import；独立 review 通过后进入 S2。

## 5. S2 — Control DB schema, migration, repository and finalize seed

### Objective

交付 workspace schema v4、v3 backfill、SQLite Review adapter、UoW participant，以及未来 Submission
Finalize 的 initial Review seed closure。

### Deliverables

- `review_event_records`、`review_projection_records`、`review_idempotency_records`；
- v3 -> v4 transactional migration/backfill；
- schema no-op/newer-version/integrity/foreign-key behavior；
- immutable event inserts、projection CAS、idempotency lookup/insert、ordered read mapping；
- project-wide `(business_project_id, idempotency_key)` uniqueness and event binding；
- `ControlDbUnitOfWork.review` participant；
- T3 new Submission 同事务 seed；Finalize replay closure validation；
- no Review mutation transaction or HTTP yet。

### Migration barriers

- every existing Submission gets exactly sequence 0/PENDING projection；
- backfill preserves Submission/Workspace/occupancy/artifact bytes；
- rerun at v4 creates no duplicates；
- unsupported newer schema fails closed；
- partial failure rolls back migration；
- future Finalize and replay never create duplicate seed；
- event sequence 从 0 连续，projection version/sequence/status/updater/time exact 匹配 latest event；
- seed/projection/idempotency closure 损坏抛 `ReviewIntegrityFailure`，不返回 404 或伪成功。

### Unique test owners

- `tests/test_review_persistence.py`：schema、migration、backfill、row mapping、constraints；
- existing `tests/test_submit_transactions.py`：T3 seed/replay atomic closure only。

### Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_persistence.py tests/test_submit_transactions.py \
  tests/test_submit_control_db_migrations.py tests/test_sqlite_submit_repository.py
../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/infrastructure/control_db \
  src/gateway_backend/application/submission tests/test_review_persistence.py \
  tests/test_submit_transactions.py
../scripts/uv-consume.sh -C . run mypy
```

### Exit

`p5-5c-s2-handoff.md` 记录 schema version、backfill count assertions、T3 closure、lock identity 与独立 review。

## 6. S3 — Review command transaction and Workspace release

### Objective

交付 current-session scope、idempotency、optimistic CAS、event/projection update 与 Workspace release 的
application transaction；仍不注册 HTTP route。

### Deliverables

- project/device/Repository scope closure；
- authentication -> exact `review_submission` permission-before-object-read -> mapping -> object scope gate；
- apply/replay/conflict ordering；
- actor-independent project-wide idempotency replay/conflict；
- approve requires and retains exact occupancy；
- reject/return/withdraw require exact generation/upload/preview/occupancy bindings, then clear pointers + delete
  occupancy + update Workspace version；
- approved-return vs future Archive occupancy race barrier；
- read ReviewFacts query；
- deterministic error taxonomy for HTTP mapping。

### Transaction barriers

- same key/same fingerprint no second event/version/workspace update；
- same key/different fingerprint conflict；
- cross-actor same project/key/same fingerprint replays original event actor；另一 Submission 复用 same project/key
  conflicts；
- stale version、invalid transition，以及 generation/upload/preview/occupancy 任一 mismatch writes nothing；
- projection/event divergence、sequence gap 或 dangling/mismatched idempotency fails closed as typed integrity
  failure；
- any injected repository/CAS error rolls back event/projection/idempotency/workspace together；
- concurrent commands produce one commit and one stable conflict；
- release leaves Submission/source/commit facts untouched；
- no Repository Client/Operation/artifact cleanup call。

### Unique test owner

`tests/test_review_transactions.py`

Fault injection covers semantic transaction boundaries, not every SQL statement. SQLite concurrency tests must not
depend on fixed sleeps/timeouts; if unavoidable they receive `@pytest.mark.serial` and a documented timing reason。

### Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_domain.py tests/test_review_persistence.py tests/test_review_transactions.py \
  tests/test_submit_transactions.py
../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/application/submission \
  src/gateway_backend/domain/submission src/gateway_backend/infrastructure/control_db \
  tests/test_review_transactions.py
../scripts/uv-consume.sh -C . run mypy
```

### Exit

`p5-5c-s3-handoff.md` 记录 transaction matrix、fault cases、independent review 与 S4 entry。

## 7. S4 — HTTP contract, production wiring and deployed permission

### Objective

把 accepted S1–S3 application seam 暴露为 closed HTTP contract，并通过现有 production dependency
bundle 接入 session permission、OpenAPI 和 admission gate。

### Deliverables

- `POST /v1/submissions/{submission_id}/review-events`；
- `GET /v1/submissions/{submission_id}/review`；
- exact `Idempotency-Key`/reason character bounds、closed request/response DTO；
- stable 201/200/401/403/404/409/422/429/503 mapping，其中 permission missing 固定 403，object
  absent/cross-scope/mapping missing/disabled/drift 固定 404，provider failure 固定
  `503 DEPENDENCY_UNAVAILABLE`，Review integrity failure 固定 `503 SERVICE_NOT_READY`；
- current-session re-authorization and cross-actor project/device review；
- route registration and exact `PRODUCTION_OPENAPI_PATHS` update；
- production route 复用 existing `WorkspaceHttpDependencies`，不建立 Review-specific composition seam；
- deployment/test session fixtures add `review_submission`；
- no route for start-review、event mutation/delete、Archive 或 History Compare。

### Unique test owners

- `tests/test_review_http.py`：wire/auth/scope/status/error/replay/redaction；它是 Review permission matrix 的
  唯一 owner，并覆盖 POST/GET/replay permission-before-object-read 与跨 actor replay；
- existing `tests/test_http_openapi.py`：path/schema publication only；
- existing `tests/test_production_wiring.py`：existing production dependency bundle route reachability only；
- existing `tests/test_architecture.py`：dependency and exact route allow-list only。

既有 `tests/test_http_auth_matrix.py` 不在 5C path budget，也不承担 Review permission coverage；不得为 5C
在该文件复制 matrix。

### Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_http.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_architecture.py
../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/http \
  src/gateway_backend/bootstrap tests/test_review_http.py \
  tests/test_http_openapi.py tests/test_production_wiring.py tests/test_architecture.py
../scripts/uv-consume.sh -C . run mypy
```

阶段性 S4 可先运行 Python/static，不在每次 docs/test 修订后重复 build；由于本阶段触及 route、production
wiring 与 session config，S5 最终 candidate 必须 fresh rebuild。

### Exit

`p5-5c-s4-handoff.md` 记录 exact OpenAPI paths、permission/config diff、focused/static 与独立 review。

## 8. S5 — Independent functional acceptance and current-HEAD gate

### Objective

在一个 sealed candidate 上证明完整 Submit->Review behavior、全仓回归、容器路径与 provenance，随后只
建议 slice exit，不自行授权 P5-5D 或 production deployment。

### Functional acceptance

`tests/test_review_compose_e2e.py` 使用真实 deployed Backend/worker/Repository Service 完成必要最小旅程：

```text
Accept -> upload -> preview -> submit -> poll -> Submission
  -> project/device reviewer APPROVE
  -> Review read shows immutable event/projection
  -> Repository main/commit unchanged by Review
```

transaction suite另证明 reject/return/withdraw release；容器 journey不复制四态矩阵。若复用现有 Submit
compose helper，不移动其 Accept/upload/preview/submit assertions owner。

### Accumulated focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_domain.py tests/test_review_persistence.py \
  tests/test_review_transactions.py tests/test_review_http.py \
  tests/test_submit_transactions.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_architecture.py
```

### Five-package static

```bash
for pkg in shared_kernel repository_contracts repository_client backend repository_service; do
  (cd vnext/$pkg && ../scripts/uv-consume.sh -C . run ruff check . && \
    ../scripts/uv-consume.sh -C . run mypy)
done
```

### Authoritative runner

```bash
./vnext/scripts/run-tests.sh
```

不因 Review 无 Dolt effect 而给 runner 增加 ignore/skip。阶段性 `-m unit` 不得初始化真实 Dolt；最终
runner按仓库权威分组执行。CPU 充足的正式开发环境可选设置 `GATEWAY_TEST_WORKERS=48` 作为本地性能
优化，但该覆盖不是可移植 gate 配方，也不得写成 acceptance 前置条件。

### Current-HEAD image/container gate

最终 candidate 必须记录 clean worktree、candidate SHA、五锁 SHA、Compose SHA、`vnext/**` source-tree
digest、image IDs/labels 与测试对象一致性，然后 fresh rebuild：

```bash
./vnext/scripts/build-repository-service-image.sh
cd vnext/deploy
docker compose build --no-cache backend worker
```

随后运行 Review compose journey、既有 backend clean stop/readiness 门禁以及必要三服务 conjunction。
不得把 P5-5B 旧镜像证据表述为当前 5C candidate 已验证。

### Exit evidence

`p5-5c-s5-handoff.md` 至少记录：

```yaml
candidate_head: <sha>
gate_tested_head: <same sha>
clean_status: yes
five_package_static: pass
authoritative_runner: pass
container_gate_for_current_head: pass
review_findings_open: []
p5_5c_slice_exit: pass_recommended
p5_5d_authorized: no
production_deployment_authorized: no
```

最终由 separate independent acceptance context 决定 `p5_5c_slice_exit`。Delivery/handoff 不自签 exit。

## 9. Test classification and performance constraints

- pure transition、DTO、mapping、SQLite transaction tests 标记 `unit`；不得因方便引入 Dolt fixture；
- 只有真实三服务/container journey 标记 `integration`；
- 只有确有时间预算/进程顺序依赖的 tests 标记 `serial`；不把普通 SQLite write conflict 标成 serial；
- Review payload/error 同构用例使用模块级共享参数表；
- 不在循环中 spawn process 或重复构造全新 Dolt HOME；
- marker 使用 repository 已声明集合，`--strict-markers` 必须通过。

## 10. Contract drift and stop conditions

实现过程中发现以下任一项时停止，不在当前 allowed paths 内自行解决：

- 需要新增 Review status/event workflow、assignment、quorum 或 unbounded comments；
- 需要 Repository ref/commit mutation or readback 才能决定 Review；
- 需要 Operation/worker/outbox/external consumer；
- 需要不同于 project/device permission 的 submitter-only withdraw policy；
- Workspace release 无法与 Review event/projection 保持一个 SQLite transaction；
- Archive 不再是本地原子 transaction，导致 occupancy 不足以关闭 race；
- 需要改 wire/trust/deployment boundary、依赖或 forbidden package。

此时更新 owning Contract/ADR/Design，并取得 finding-scoped authority 后才能继续。

## 11. S0 current disposition

```yaml
p5_5c_entry: authorized
p5_5c_design: accepted
p5_5c_design_candidate: accepted
p5_5c_execution_plan: accepted
independent_docs_review: pass
p5_5c_implementation_authorized: yes
source_or_test_change_authorized: true
first_authorized_step: P5-5C-S1
current_stage: P5-5C-S1
next_step: P5-5C-S1-handoff
```

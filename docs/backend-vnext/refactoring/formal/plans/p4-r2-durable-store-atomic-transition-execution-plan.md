# P4-R2 Durable Store and Atomic Transition Detailed Execution Plan

状态：**S0 DESIGN ACCEPTED — IMPLEMENTATION NOT AUTHORIZED**

日期：2026-08-23

Owner：Operation Runtime persistence + Backend Control DB infrastructure

默认入口：[P4 Active Context Index](p4-active-context-index.md)

上游：[P4/R1 Runtime Contract and State Handoff](p4-r1-runtime-contract-state-handoff.md)、
[P4-R2-S0 Entry Brief](p4-r2-s0-entry-brief.md)、
[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)

## 1. Purpose and execution protocol

本文把 R2 从 S0 design acceptance到module handoff拆成可独立执行、验证和提交的context
packages。当前用户授权仅覆盖本文、S0 brief和S0 acceptance record的创建；没有授权任何
Python/SQL/test/deployment实现。收到单独S1a实施授权前，本文所有code steps保持blocked。

实施时每次只执行一个命名step：

1. 读取P4 Active Context、R1 handoff、本brief/plan、上一step handoff和当前Git状态；
2. 核对entry prerequisites、allowed paths、reopen conditions和input SHA；
3. 只修改该step授权路径，运行focused gate和适用static/integration/serial gate；
4. review diff，记录container/benchmark applicability与当前HEAD；
5. code step使用candidate commit + docs-only handoff的两段seal；
6. handoff明确下一step及是否授权，不自动连续实施。

每个handoff/review至少记录：

```yaml
step_id:
input_handoff_sha:
validated_code_sha:
result: pass | rework_required
changed_paths: []
commands_and_results: []
focused_tests:
integration:
serial:
five_package_static:
container_gate:
benchmark:
findings: []
deferred_items: []
reopen_conditions: []
next_step:
next_step_authorized: yes | no
```

若handoff后in-scope code/test tree变化、validated SHA不再是ancestor或HEAD含未记录变更，
必须停止并重新验证。

## 2. Frozen R2 boundary

### 2.1 Authority and dependency direction

R1的`OperationRecord`、`StepRecord`、parsers、transition guards与
`validate_write_precondition`仍是persisted semantic和transition唯一owner。R2只拥有SQLite
layout、storage metadata、transaction/CAS实现和owner-specific store errors；不得复制或放宽
R1 semantic validation。

`gateway_backend.operations`定义SQLite-neutral persistence port和guarded composition；
`gateway_backend.infrastructure.control_db`实现connection、migration、concrete Unit of Work和
SQLite adapter。Operations不得import infrastructure；future Application可以让更宽的concrete
Unit of Work同时满足Operations与business repository ports。

### 2.2 Allowed paths

代码候选：

```text
vnext/backend/src/gateway_backend/operations/store.py
vnext/backend/src/gateway_backend/operations/persistence.py
vnext/backend/src/gateway_backend/operations/__init__.py
vnext/backend/src/gateway_backend/infrastructure/control_db/
vnext/backend/tests/test_operation_store.py
vnext/backend/tests/test_control_db_migrations.py
vnext/backend/tests/test_sqlite_operation_store.py
vnext/backend/tests/test_sqlite_operation_store_integration.py
vnext/backend/tests/test_architecture.py
```

文档候选仅限P4 formal plan/index/contract owner引用修正。禁止修改Repository Service、P3
capability implementation、business modules、settings/app/Compose/Dockerfile/entrypoint或依赖锁。

若实现证明文件合并可以减少无意义抽象，可在同一owner目录内合并候选module，但handoff必须
记录最终public/physical surface；不能借合并跨越Operations与infrastructure方向。

### 2.3 Port and public outcome candidate

S1a冻结最小SQLite-neutral概念：

```text
OperationStore              # transaction-scoped participant; never commits
OperationUnitOfWork         # narrow structural port; concrete UoW may expose more repositories
ClaimCandidate              # bounded storage query result; no handler/business payload interpretation

RecordNotFound
StaleWrite
LeaseExpired
ConflictingDuplicate
StoreBusy
CorruptPersistedRecord
UnsupportedSchemaVersion
```

允许的store行为：

```text
get_operation(operation_id)
get_step(step_id)
list_steps(operation_id, bounded keyset)
list_operations_by_status(status, bounded keyset)
list_claim_candidates(now, limit)
insert_operation_with_initial_step(operation, step)
insert_successor_step(step)
compare_and_set_operation(candidate, precondition, recovery_authorized=False)
compare_and_set_step(candidate, precondition, recovery_authorized=False, require_live_lease=False)
```

精确Python signatures由S1a在不扩大上述语义的前提下冻结。成功只返回R1
`TransitionDisposition.APPLY | IDEMPOTENT`；not-found/conflict/busy/corruption不折叠为`None`、
boolean或generic database error。SQLite connection/cursor/row/SQL/path不得进入public port。

### 2.4 Schema v1

`control_schema_migrations`：

| Column | Storage | Rule |
| --- | --- | --- |
| `component` | TEXT | non-empty owner key |
| `version` | INTEGER | positive, composite PK with component |
| `applied_at_us` | INTEGER | UTC epoch microseconds |

`operation_records`：

| Column group | Columns |
| --- | --- |
| identity/version | `operation_id` PK, `contract_version`, `optimistic_version` |
| job binding | `job_kind`, `job_contract_version`, `job_payload`, `job_payload_ref` |
| refs | `business_refs`, `artifact_refs`, `repository_operation_id`, `checkpoint_ref`, `ready_closure_ref` |
| lifecycle | `status`, `diagnostic`, `cancel_requested` |
| time | `created_at_us`, `updated_at_us`, `completed_at_us` |

`step_records`：

| Column group | Columns |
| --- | --- |
| identity/version | `step_id` PK, `operation_id` FK, `contract_version`, `optimistic_version` |
| registry/attempt | `step_name`, `attempt_count` |
| lifecycle | `status`, `diagnostic`, `cancel_requested`, `retry_not_before_us` |
| lease | `worker_id`, `lease_token`, `lease_expires_at_us` |
| refs | `checkpoint_ref`, `prior_output_refs` |
| semantic time | `created_at_us`, `updated_at_us`, `started_at_us`, `completed_at_us` |
| storage metadata | `eligible_at_us` |

Direct scalars是唯一column authority；复合字段使用Shared Kernel JCS/canonical JSON bytes，
不要求SQLite JSON1。adapter readback重建closed R1 document并调用owner parser。`eligible_at_us`
在PENDING时等于created time、RETRY_WAIT时等于retry-not-before、其他状态为null；它不得进入
R1 document或digest/version axis。

Required indexes/constraints：

```text
PK operation_records(operation_id)
PK step_records(step_id)
FK step_records(operation_id) -> operation_records(operation_id) ON DELETE RESTRICT
UNIQUE step_records(operation_id, step_name)
UNIQUE ACTIVE step per operation WHERE status IN
  (PENDING, RUNNING, RETRY_WAIT, MANUAL_RECOVERY_REQUIRED)
INDEX claim(status, eligible_at_us, created_at_us, step_id)
  WHERE status IN (PENDING, RETRY_WAIT)
INDEX operation status readback(status, updated_at_us, operation_id)
```

DDL增加低成本type/range/enum/nullability CHECK；完整cross-field、append-only、timestamp和
transition semantic仍由R1 parser/guards拥有。不得增加`job_kind`、business/artifact ref索引或
可推导状态列。

### 2.5 Migration and connection profile

只使用stdlib`sqlite3`。connection明确启用：

```text
PRAGMA journal_mode=WAL
PRAGMA foreign_keys=ON
PRAGMA synchronous=FULL
PRAGMA busy_timeout=5000
```

每个Unit of Work使用独立connection和显式transaction；write使用`BEGIN IMMEDIATE`，read-only
可以deferred。connection不跨线程共享。调用方负责传入server-owned DB path且parent已存在；
R2不读取environment、不创建deployment目录、不接Compose volume。

bootstrap先在`BEGIN IMMEDIATE`内创建/确认migration ledger，再重读component version并顺序
执行Operations migration。migration forward-only、transactional；statement不要求逐条
幂等，但完整migration在commit前不可见。只接受absent/v0到v1；高于程序支持的version抛
`UnsupportedSchemaVersion`并阻止readiness。无downgrade、legacy import、checksum ledger、
shadow copy或online migration framework。

### 2.6 Atomic mutation and lease rules

每次CAS必须在同一write transaction内：

```text
load current
  -> parse/validate current
  -> validate transition(current, candidate)
  -> validate_write_precondition(current scalar lease/version, precondition)
  -> optional require current lease_expires_at > transaction_now
  -> UPDATE ... WHERE identity/version/lease conditions
  -> require affected_rows == 1
```

`affected_rows=0`后不得假定原因；在同一transaction/新read中分类为not-found、stale、expired或
conflict并返回owner-specific error。不得先读、退出transaction、再写。terminal exact duplicate
由guard返回IDEMPOTENT且不产生第二次UPDATE。

Atomic action matrix：

| Action | Operation row | Step row(s) | Policy owner |
| --- | --- | --- | --- |
| create | insert QUEUED | insert first PENDING | caller supplies accepted records |
| first claim | QUEUED→RUNNING if needed | PENDING/RETRY_WAIT→RUNNING | R2 structural claim |
| heartbeat/checkpoint | explicit candidate only | guarded same-status candidate | runtime caller; no effect inference |
| step success + successor | unchanged/RUNNING | terminal current + insert successor | R4 selects successor |
| final step + operation | accepted terminal | accepted terminal | R4/R5 selects outcome |
| cancel request | set monotonic intent | set current active intent | application requests; R4/R5 publishes terminal |

每个Operation V1最多一个active Step。R2不执行`RUNNING -> RUNNING` lease replacement；expired
RUNNING必须由R5 policy先转到RETRY_WAIT或MANUAL，普通claim才建立新worker/token并递增attempt。
过期worker在新状态尚未决定时也不能heartbeat/checkpoint/terminal publish。

### 2.7 Claim/read ordering and pagination

claim只读取已materialize的PENDING或due RETRY_WAIT，固定顺序为
`eligible_at_us, created_at_us, step_id`。production默认limit=1且不得由caller绕过store hard
maximum。expired RUNNING和MANUAL不在scan中。

readback只提供ID lookup、Operation内Steps、status/admin和claim所需bounded query。pagination
使用stable keyset而非offset；limit必须为positive且有hard maximum。R2不提供arbitrary SQL filter、
business ref/artifact ref/job-kind search或跨owner projection。

### 2.8 Time, IDs and diagnostics

- persisted time为aware UTC，adapter使用signed epoch microseconds无损round-trip；
- transaction通过injected UTC wall clock只采样一次；unit test使用fake clock；
- production lease duration 30s；R3 heartbeat建议10s；R2不实现heartbeat loop；
- operation/step/lease默认采用typed-prefix UUID4 string且保持R1 opaque-ID budget；
- Store不生成或替换caller identity；create retry重用original candidate；
- stale/expired/busy/conflict只发structured log和bounded metric；不写audit table；
- log不含payload、lease token、artifact bytes、SQL或absolute DB path。

### 2.9 Integrity and readiness seam

每个row读取必须重建并验证R1 record；scalar/compound mismatch、unknown contract version或非法
cross-field状态返回`CorruptPersistedRecord`。R2提供bounded active integrity scan供R3 startup
调用，但不拥有readiness route。

非终局record损坏时R3不得开放readiness；terminal历史损坏只影响对应readback并告警。R2不
自动修改损坏row为FAILED/MANUAL，不创建quarantine/repair journal，不从宽parser，也不删除
corrupt row。

### 2.10 Accepted risk/deferred register

| Item | Disposition |
| --- | --- |
| SQLite writer contention | bounded max-in-flight、short IMMEDIATE transactions、busy error/metric |
| capacity/throughput | no formal claim；first P5 journey owns measurement |
| production outbox | P5 Application/Integration owner；R2 only proves transaction seam |
| worker/settings/volume/readiness | R3 |
| JobDefinition/successor/checkpoint closure | R4 |
| retry/backoff/effect-aware takeover | R5 |
| terminal retention/GC/backup | later Operations/P5 policy with real consumer |
| fan-out/multi-host/external DB | future architecture reopen |

## 3. Shared verification commands

Focused commands由step handoff按实际test names收敛，候选入口：

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_operation_contracts.py \
  tests/test_operation_state.py \
  tests/test_operation_store.py \
  tests/test_control_db_migrations.py \
  tests/test_sqlite_operation_store.py \
  tests/test_architecture.py
uv run pytest -q -m integration tests/test_sqlite_operation_store_integration.py
uv run pytest -q -m serial tests/test_sqlite_operation_store_integration.py
uv run pytest -q -m unit
uv run ruff check .
uv run mypy
```

若integration文件内没有serial case，serial命令记录`not_applicable`而不是空跑。提交任何code
step前，其余四个Python包也必须分别执行`ruff check .`与`mypy`。R2不运行Dolt integration。

纯`:memory:` SQLite mapping/transaction test可标unit；依赖durable on-disk state、WAL或关闭
重开语义的必须标integration；依赖fixed timeout/process crash才标serial。不要把所有SQLite
测试机械标为integration，也不得用in-memory结果声称WAL通过。

## 4. P4-R2-S0 — Independent entry acceptance

```yaml
step_id: P4-R2-S0
entry: R1 S7 handoff pass and explicit R2 design-document authorization
objective: accept R2 boundary and execution context without authorizing implementation
```

Required checks：

1. R1 handoff SHA/validated code ancestry与当前source/test tree无漂移；
2. schema没有改变R1 persisted semantic document或增加business/effect字段；
3. transaction seam允许future T1/T3同库组合但不让Operations拥有business/outbox；
4. lease expiry与takeover没有绕过R1 matrix或抢占R5 policy；
5. storage metadata、indexes和budgets都有当前consumer/风险依据；
6. migration、integrity、test marker和container applicability明确；
7. architecture中的stale SQLite/`operation_kind`描述已校正；
8. acceptance明确S1a implementation仍需单独授权。

Allowed changes：本plan、S0 brief、S0 acceptance、P4 index/README和stale architecture wording。
禁止source/test/deployment changes。

Exit：`p4_r2_s0: accepted`、`p4_r2_s1a_authorized: no`，Active Context指向R2三份文档。

## 5. P4-R2-S1a — Store port and error boundary

```yaml
step_id: P4-R2-S1a
entry: S0 accepted plus explicit S1a implementation authorization
objective: publish SQLite-neutral transaction-scoped persistence boundary
```

Allowed paths：`operations/store.py`、必要的`operations/__init__.py`、focused tests和architecture
test。不得import sqlite3或infrastructure。

Implementation：定义transaction-scoped OperationStore、narrow OperationUnitOfWork、bounded
ClaimCandidate和七个owner-specific error kinds；冻结public signatures、pagination limits和
success disposition复用。不得引入generic repository/UoW framework、business repository或
NotImplementedError stub。

Tests：public exports/import boundary、error distinctions、limit/cursor validation、fake participant
transaction composition。测试不创建SQLite文件。

Exit：focused unit、backend ruff/mypy、五包static、diff check通过；创建S1a handoff并仅指向S1b。

## 6. P4-R2-S1b — Control DB schema and migration skeleton

```yaml
step_id: P4-R2-S1b
entry: S1a handoff pass
objective: create concrete SQLite boundary, schema v1 and forward migration
```

Allowed paths：`infrastructure/control_db/`、migration/store focused tests、architecture test；仅在
concrete adapter中importOperations port/contracts。

Implementation：connection factory、explicit UoW、PRAGMA profile、migration ledger、Operations
v1 DDL/indexes/constraints和row mapping skeleton。parent directory必须由caller提供；不接settings。

Tests：fresh v0→v1、repeat startup、higher-version rejection、migration rollback、schema/index/FK
identity、two concurrent startup connections。in-memory tests只证明DDL/mapping；file-backed
integration证明WAL/restart。

Exit：focused unit/integration、static和diff review通过；handoff记录schema version、PRAGMAs、
container N/A理由并指向S2a。

## 7. P4-R2-S2a — Create, readback and guarded CAS

```yaml
step_id: P4-R2-S2a
entry: S1b handoff pass
objective: implement durable round-trip and generic atomic record mutation
```

Implementation：exact create/idempotency、ID reads、bounded step/status lists、canonical composite
encoding、UTC microsecond mapping、operation/step guarded CAS和transaction-scoped multi-record
composition。所有read经过R1 parser；所有update组合guard/precondition。

Tests：完整R1 record round-trip、boundary timestamps、complex refs/payload、exact/conflicting create、
not-found/stale/terminal idempotency、rollback不留半状态、synthetic owner table与Operation共同
commit/rollback。不得复制R1全部非法shape矩阵。

Exit：focused unit/integration、five-package static与diff check通过；handoff指向S2b。

## 8. P4-R2-S2b — Claim, lease and action composition

```yaml
step_id: P4-R2-S2b
entry: S2a handoff pass
objective: implement bounded claim and lifecycle persistence actions
```

Implementation：eligible metadata维护、deterministic claim、first Operation RUNNING composition、
live-lease heartbeat/checkpoint/terminal CAS、cancel intent、successor/final atomic actions。R2只接受
caller已作出的successor/final/recovery candidate，不解释handler/effect policy。

Tests：duplicate claim、PENDING/RETRY due ordering、expired lease拒绝、late worker、heartbeat延长
同一lease、cancel与heartbeat竞争、terminal+successor/Operation rollback、MANUAL不claim、无
RUNNING token swap。

Exit：focused gates和static通过；handoff指向S3a。

## 9. P4-R2-S3a — Mapping, migration and integrity hardening

```yaml
step_id: P4-R2-S3a
entry: S2b handoff pass
objective: prove durable representation and corruption/readiness seam
```

Tests按共享参数表覆盖scalar/composite mismatch、unknown contract/schema version、invalid enum/
boolean/range、truncated canonical BLOB、FK/orphan、active vs terminal corruption、bounded integrity
scan和keyset pagination。migration覆盖commit/rollback/reopen；不制造per-statement crash matrix。

Production defect只允许在既有schema/port语义内修复；需要新field/version/repair state先finding
并reopen。

Exit：focused unit/integration、static、diff check通过；handoff指向S3b。

## 10. P4-R2-S3b — WAL, contention and crash visibility hardening

```yaml
step_id: P4-R2-S3b
entry: S3a handoff pass on clean candidate
objective: prove SQLite transaction/CAS barriers with bounded on-disk evidence
```

使用real temporary file和独立connections覆盖：uncommitted不可见、commit可见、rollback、writer
contention→StoreBusy、stale CAS、migration竞争、关闭重开、WAL mode保持和一个代表性process
termination barrier。使用barrier/IPC确定故障位置；只有真实fixed-time/process case标serial。

不得穷举每个SQL statement/interleaving，不建设generic fault runner或durable RunEvidence。

Exit：integration/serial applicability、focused/unit、static和diff check通过；handoff指向S4。

## 11. P4-R2-S4 — Focused owner review

Review必须独立检查：

- Operations/infrastructure/UoW owner与依赖方向；
- schema是否形成duplicate semantic authority；
- create/claim/terminal/successor/cancel跨表原子性；
- stale、expired、terminal duplicate与affected-row分类；
- migration race、unsupported version和corruption处理；
- busy/clock/limit budget是否可绕过；
- no outbox/business/Repository/worker/deployment越界；
- test owner是否重复R1 matrix或过度证明SQLite内部步骤。

P1/P2、contract ambiguity或stale-writer gap阻塞S7，进入S5/reopen。普通低风险finding可S5修复。
输出`p4-r2-s4-focused-review.md`及finding disposition。

## 12. P4-R2-S5 — Conditional remediation

只处理S4记录且在accepted R2 boundary内的finding。每项必须列owner、allowed paths、regression、
commands、closure criteria和reopen trigger。无finding时不创建空S5文件。

任何需要改变R1 contract、增加business/outbox/effect policy、直接lease swap、repair journal或
deployment主体的finding不得在S5静默修复。

## 13. P4-R2-S6 — Risk-based independent review

S6必需。独立复核S4/S5 candidate，重点证明B类durable状态、cross-table atomicity、CAS、migration
和corruption/readiness seam；不复查所有pure R1 shape tests或穷举SQLite schedule。

输出`p4-r2-s6-independent-review.md`。P1/P2和contract ambiguity必须closed或reopen；只有低风险、
有明确owner/trigger的容量与后续integration项可defer。

## 14. P4-R2-S7 — Module gate and handoff

Required gates：focused unit、backend unit、file-backed integration、适用serial、五包ruff/mypy、
`git diff --check`和source/test tree identity。R2不依赖Dolt。若最终candidate仍未触碰settings、
Compose、entrypoint、mount或container-only behavior，container build记录not applicable；否则必须
重建当前HEAD并运行相应gate。

输出`p4-r2-durable-store-atomic-transition-handoff.md`，至少记录：

```yaml
handoff_kind: p4_r2
validated_code_sha:
p4_r2_exit: pass | rework_required
applicable_steps: []
skipped_steps_with_reason: []
schema_component_version:
sqlite_profile:
public_store_symbols: []
atomicity_matrix:
focused_review:
independent_review:
unit:
integration:
serial:
five_package_static:
container_gate:
benchmark:
known_capacity_limits: []
deferred_items: []
reopen_conditions: []
next_entry: P4-R3-S0 | none
```

R2 handoff只允许R3 entry discussion；不自动授权worker、settings/Compose、R4/R5/P5或真实
Repository effect。

## 15. Global stop/reopen rules

任何step遇到以下情况必须停止：

- R1 persisted fields/status/guards不足且需要语义变化；
- 需要多个active Steps、DAG/fan-out或R2解释JobDefinition；
- 需要Operations拥有business table、production outbox或T1/T3；
- 需要blind retry expired external-effect Step或直接替换RUNNING lease；
- 需要Repository wire/marker/ref/CAS、network或Dolt；
- 需要settings/Compose/volume/worker entrypoint而当前step未授权container boundary；
- 需要SQLAlchemy/Alembic、新dependency、broker、sidecar、helper、UID/GID、外部DB或HA；
- 需要automatic repair/quarantine/durable rejection evidence；
- 真实部署不是同机可靠local SQLite volume，或accepted lock/capacity budget已不成立。

处理顺序：evidence → finding → owning Contract/ADR decision → 更新brief/plan/tests → re-review。

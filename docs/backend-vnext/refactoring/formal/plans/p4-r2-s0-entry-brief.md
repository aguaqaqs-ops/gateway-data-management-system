# P4-R2-S0 Entry Brief: Durable Store and Atomic Transition

状态：**ACCEPTED FOR DESIGN; IMPLEMENTATION AUTHORIZATION PENDING**

日期：2026-08-23

Owner：Operation Runtime persistence（semantic tables/port）与 Backend Control DB infrastructure
（connection/migration/transaction）

上游：[P4/R1 Runtime Contract and State Handoff](p4-r1-runtime-contract-state-handoff.md)、
[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[Proportional Assurance and Risk-Based Verification Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)

逐 step 执行 authority：
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

## 1. Entry identity and decision boundary

```yaml
step_id: P4-R2-S0
input_handoff_sha: 1c492b3aad6ff577e2966cc083b14a24337c4f50
input_validated_code_sha: e2703407a1c80d31f6888ce86c0ab9b125464ad5
p4_r1_exit: pass
p4_r2_entry_discussion_authorized: yes
p4_r2_s0_design: accepted
p4_r2_implementation_authorized: no
next_step: P4-R2-S1a
next_step_authorized: no
```

`input_handoff_sha` 是封存 R1 S7 PASS、更新 P4 Active Context 并只允许 R2 entry/design
conversation 的 documentation commit。当前 S0 只接受 R2 设计输入、步骤和 gate；不得据此
创建 SQLite schema、修改 Python source/tests、接线 settings/Compose 或开始 S1a。

## 2. Objective

在 backend application 的共享 SQLite/WAL control DB 中建立最小 durable Operation/Step
store，使 R3–R5 可以复用 R1 已接受的 record/transition guards 完成 claim、heartbeat、
checkpoint、terminal publication 和 recovery，而不把业务事实、Repository effect authority
或 JobDefinition policy移入 Operations。

## 3. Ownership and physical placement

冻结的依赖与所有权：

```text
gateway_backend.operations
  owns: Operation/Step store port, store-specific outcomes/errors,
        guarded persistence composition
  must not import: infrastructure, settings, application, capabilities,
                   Repository packages

gateway_backend.infrastructure.control_db
  owns: SQLite connection lifecycle, PRAGMA profile, migration runner,
        concrete Unit of Work and SQLite Operation adapter
  may import: gateway_backend.operations public contracts/port

future P5 application
  owns: business repositories, production outbox and T1/T3 Unit of Work shape
  reuses: the same concrete control DB transaction
```

候选路径：

```text
vnext/backend/src/gateway_backend/operations/store.py
vnext/backend/src/gateway_backend/operations/persistence.py
vnext/backend/src/gateway_backend/infrastructure/control_db/__init__.py
vnext/backend/src/gateway_backend/infrastructure/control_db/database.py
vnext/backend/src/gateway_backend/infrastructure/control_db/migrations.py
vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_operations.py
vnext/backend/tests/test_operation_store.py
vnext/backend/tests/test_control_db_migrations.py
vnext/backend/tests/test_sqlite_operation_store.py
vnext/backend/tests/test_sqlite_operation_store_integration.py
```

实际文件可在 S1a/S1b 合并低耦合 helper，但不得把 concrete SQLite adapter 放入
`gateway_backend.operations`，也不得让 Operations import infrastructure。

## 4. In-scope decisions

### 4.1 Shared transaction seam

- concrete control DB Unit of Work 拥有 connection、begin/commit/rollback；
- transaction-scoped Operation store 不自行 commit；
- R2 用 owner-neutral synthetic table 证明未来 business record、Operation 和 outbox 可以在
  同一 SQLite transaction 中共同 commit/rollback；
- R2 不创建 production business table 或 generic outbox schema；
- 禁止跨库 two-phase commit 和 callback 内隐式外部 I/O。

### 4.2 Runnable-step model

- 只有前置条件已满足的 Step 才以 `PENDING` 落库；materialized Step 即 runnable；
- 每个 Operation V1 最多一个非终局 Step；不持久化 ordinal、dependency、DAG 或 fan-out；
- predecessor terminal publication 与 successor insert 可以同事务完成；
- successor选择、step-specific retry/effect policy属于 R4/R5 JobDefinition owner；
- expired `RUNNING` 不直接参与普通 claim scan。

### 4.3 Storage representation

- direct scalar/CAS/query fields使用独立 SQLite columns；
- payload、diagnostic、business/artifact refs等复合值使用 bounded canonical JSON/BLOB；
- 不额外保存完整 record document，避免 document 与 projection 双份权威；
- readback 必须重建 exact R1 document并通过 R1 parser/constructor；
- timestamps使用 signed UTC epoch microseconds `INTEGER`；R1外部 document仍使用 canonical UTC；
- `eligible_at_us` 是 R2 storage metadata，不加入 R1 semantic document。

### 4.4 Identity and idempotency

- Application在 T1 前生成并重用 `operation_id`；Runtime/JobDefinition创建 runnable Step时
  生成 `step_id`；每次 claim 使用新 `lease_token`；`worker_id` 留给 R3 bootstrap；
- V1默认使用带类型前缀的 UUID4 字符串，但 ID 保持 opaque且不具有安全/顺序/业务语义；
- Store不自行替换 caller提供的 identity；
- duplicate create只有完整 persisted record相等才是 `IDEMPOTENT`，否则为
  `ConflictingDuplicate`。

## 5. Frozen SQLite profile and budgets

```yaml
journal_mode: WAL
foreign_keys: true
synchronous: FULL
write_begin: IMMEDIATE
busy_timeout_seconds: 5
lease_duration_seconds: 30
r3_heartbeat_interval_seconds: 10
max_in_flight: 1
claim_limit: 1
clock: injected_utc_wall_clock_sampled_once_per_transaction
```

connection不得跨线程共享；每个 Unit of Work使用显式 transaction。持锁期间禁止 network、
Repository、artifact或任意长计算。测试可注入更短 busy timeout和 fake clock，但不得改变
production默认语义。

## 6. Required atomicity matrix

| Action | Required atomic facts |
| --- | --- |
| create | one `QUEUED` Operation + first runnable `PENDING` Step |
| first claim | Operation `QUEUED -> RUNNING` when needed + Step `PENDING/RETRY_WAIT -> RUNNING` |
| heartbeat/checkpoint | explicit guarded candidate only; no inferred business/effect mutation |
| step success | current Step terminal + successor `PENDING`, or current Step + Operation terminal |
| cancel request | Operation and current non-final Step intent together; no automatic `CANCELLED` publication |
| terminal retry | exact-record duplicate only; approximate reconstructed candidate conflicts |

每次 mutation在 transaction内加载 current，执行对应 R1 transition guard与
`validate_write_precondition`，再以 identity/version/lease条件执行 SQL CAS。带 lease的
heartbeat、checkpoint和terminal publish还必须满足 current `lease_expires_at > now`。

R2不允许 `RUNNING -> RUNNING` 更换 worker/lease。lease过期后的下一状态由 R5/JobDefinition
owner选择 `RETRY_WAIT` 或 `MANUAL_RECOVERY_REQUIRED`，随后才可按 R1 matrix建立新 lease。

## 7. Readback, integrity and diagnostics

最小 read surface：

- get Operation/Step by ID；
- bounded list Steps by Operation；
- bounded claim candidate scan，顺序为
  `(eligible_at_us, created_at_us, step_id)`；
- bounded keyset-paginated Operation status/admin readback；
- bounded active-record integrity scan供 R3 startup使用。

不提供任意 filter、offset pagination、business/artifact ref搜索或 `job_kind` scan。

Store-specific error kinds冻结为：`RecordNotFound`、`StaleWrite`、`LeaseExpired`、
`ConflictingDuplicate`、`StoreBusy`、`CorruptPersistedRecord`、
`UnsupportedSchemaVersion`。成功只复用 R1 `APPLY | IDEMPOTENT` disposition，不增加通用
failure taxonomy。

stale/busy/expired/conflict使用结构化日志与 bounded metrics，不写 durable rejection ledger，
也不修改被拒绝记录。非终局记录损坏阻塞 startup readiness并要求人工处置；terminal历史
记录损坏只使对应 readback失败并告警。不得自动宽松解析、修复、quarantine或伪造
`FAILED` / `MANUAL_RECOVERY_REQUIRED`。

## 8. Schema and migration boundary

R2冻结三张 owner-level表：

```text
control_schema_migrations(component, version, applied_at_us)
operation_records(...R1 fields as scalar/canonical composite columns...)
step_records(...R1 fields + eligible_at_us...)
```

关键关系：

- `step_records.operation_id -> operation_records.operation_id ON DELETE RESTRICT`；
- `UNIQUE(operation_id, step_name)`；
- partial unique index保证每个 Operation最多一个
  `PENDING | RUNNING | RETRY_WAIT | MANUAL_RECOVERY_REQUIRED` Step；
- claim index只覆盖 `PENDING | RETRY_WAIT`；
- Operation status/admin index覆盖 `(status, updated_at_us, operation_id)`；
- 不为 `job_kind`、business refs或artifact refs建立索引。

migration使用stdlib `sqlite3`，component-scoped、forward-only、transactional。首版只接受
absent/v0到Operations v1；不支持 downgrade或legacy backend persistence。程序遇到更高版本
必须 readiness失败。migration table bootstrap与component migration在 `BEGIN IMMEDIATE`
下重读当前版本，允许 backend/worker竞争启动而不重复应用。

## 9. Non-goals and forbidden paths

- 不实现 production outbox、Workspace/Submission/Archive table或 T1/T3 use case；
- 不实现 worker loop、settings、HTTP、signal、readiness、Compose或volume wiring；
- 不实现 JobDefinition registry、retry/backoff、unknown effect reconcile或 Repository stub；
- 不修改 Repository Service control DB、marker/ref/CAS或wire；
- 不增加 SQLAlchemy/Alembic、broker、sidecar、helper、UID/GID或外部 durable DB；
- 不自动 cleanup terminal records，不建设backup/retention framework；
- 不声明 NFS、多主机、active-active或formal throughput baseline。

## 10. Applicable steps

| Step | Applicability | Output |
| --- | --- | --- |
| S0 | required | accepted brief、detailed plan、independent design acceptance |
| S1a | required | SQLite-neutral store/UoW port、typed outcomes/errors、architecture gate |
| S1b | required | control DB connection、schema、migration和SQLite adapter skeleton |
| S2a | required | create/readback/generic guarded CAS与跨表 transaction composition |
| S2b | required | claim/lease/heartbeat/checkpoint/cancel/terminal atomic actions |
| S3a | required | mapping、migration round-trip、integrity/readback conformance |
| S3b | required | file-backed WAL、lock、rollback、crash visibility和stale/expiry evidence |
| S4 | required | focused owner review |
| S5 | conditional | finding-scoped remediation only |
| S6 | required | risk-based independent transaction/CAS review |
| S7 | required | module gate、tested tip、known limits和R3 entry handoff |

S6为required，因为R2首次持久化 B类 durable recovery state并拥有跨表原子/CAS屏障；这不
授权穷举SQLite内部interleaving或创建通用evidence harness。

## 11. Test and gate classification

- pure mapping、port、guard composition和`:memory:` transaction tests标记 `unit`；
- on-disk WAL、双连接、migration restart和关闭重开测试标记 `integration`；
- 只有依赖固定时间预算或真实process crash的测试标记 `serial`；backend本身单进程运行，
  不增加xdist或`-n 0`；
- 优先 fake clock、barrier和显式transaction控制，不用 `sleep`穷举时序；
- R2不依赖 Dolt、Repository Service、network或外部process；
- 同构错误用模块级共享参数表；不复制 R1 transition matrix；
- 未触碰settings/Compose/entrypoint/container boundary时镜像重建不适用；一旦越界必须停止并
  按 AGENTS.md重建当前 HEAD。

## 12. Exit and reopen conditions

S0 exit要求：owner、schema、migration、atomicity、time/lock budgets、error/integrity matrix、
applicable steps和测试分类均被独立接受，且没有需要先修改 owning Contract/ADR的finding。

下列情况必须 reopen并停止对应实现 step：

- 需要直接 `RUNNING -> RUNNING` 更换 lease identity；
- 需要多个同时非终局 Step、DAG或fan-out；
- 需要 Operations拥有 production outbox或业务 table；
- backend与worker不能共享同机可靠本地SQLite volume；
- 需要新安全主体、broker、sidecar、跨库事务、外部 DB或多实例HA；
- 无法通过 R1 guard + precondition + SQL CAS拒绝 stale/expired writer；
- 需要宽松读取、自动修复损坏record或新的durable evidence状态机；
- 当前真实容量使 `max_in_flight=1` 或5秒busy budget不可接受。

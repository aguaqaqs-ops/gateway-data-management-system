# P2-R5 Commit-pinned Read Staged Execution Plan

状态：Accepted — P2-R5 functional exit complete, P2-R6 ready

日期：2026-08-09

Owner：Backend vNext Architecture（stage boundary与handoff）；Repository Service Contract
（wire、identifier、Arrow和失败语义）；Repository Service / Client（各自private implementation）

适用范围：`P2-R5 — Commit-pinned Read, Remote Client and Fixture Consumer`

本文件是P2-R5的权威逐阶段执行计划。公开wire语义仍由
[Repository Service Contract](../contracts/repository-service.md)拥有；总体组件与跨round
边界由[P2 Versioned Repository Implementation Design](p2-versioned-repository-implementation-design.md)
和[P2 Execution Checklist](p2-versioned-repository-execution-checklist.md)拥有。发生冲突时
按上述authority顺序暂停实现并修正文档，不用兼容代码维持两套语义。

## 1. S0 baseline and entry decision

S0只固化设计和执行边界，不实现DTO、route、provider、client、fixture或测试。

```yaml
round: P2-R5-S0
branch: phase1/gate-ownership-repair
s0_start_sha: f346ef943b41191a93ad5d8a5174d218c25fb543
worktree_at_s0_start: clean
p2_r4_exit: pass
p2_r5_ready_from_r4: yes
r4_validated_code_sha: bf8c3562018d264aed22987f00d14f2dbe233697
container_validated_code_sha: 901a13b92a0a92130d9afa001d8eb4273d544566
container_validation_deferred_to: P2-R6
production_retest_required: yes
p2_r5_s1_implementation_ready: yes
```

R4最新有效handoff是post-audit round-2。R4历史镜像不是R5代码证据；R5在未触碰
container/build/deployment boundary时只执行功能、真实Dolt和非container HTTP/client
gate。S0之后的首个code stage必须从S0文档commit的clean HEAD开始，并重新记录
`start_sha`。

设计准备度结论：无未决的public contract、数据模型、一致性、部署、安全、性能容量或
验收问题。已确认存在10–100 MB脱敏真实业务package，但它不作为R5代码或普通CI输入；
R6在最终production image上以external read-only dataset关闭真实W1。当前无真实近200 MB
package，R6生成确定性、同shape的synthetic W2并标记`synthetic=true`。

## 2. Scope, invariants and explicit non-goals

### 2.1 In scope

- `ResolveVersionedRef(main)`；
- `GetVersionedCatalog(commit_id)`；
- raw Arrow IPC `StreamVersionedTableRows(commit_id, table_name, policy)`；
- exact SQL/Arrow mapping热路径修复和FULL_SCAN schema复用；
- Candidate A commit-pinned public read adapter；
- Remote Repository client完整V1 surface；
- Backend-independent contract-owned fixture consumer；
- bounded streaming、backpressure、disconnect/cancel和subprocess reap证据；
- R5 functional handoff和R6 container/production retest inventory。

### 2.2 Global invariants

1. `gateway-repository-contracts <- gateway-repository-client`；
   `gateway-repository-contracts <- gateway-repository-service`。Service不得import Client，
   Client不得import Service、Backend或Shared Kernel。
2. Resolve只接受literal `main`；catalog/rows只绑定caller提供的immutable CommitId。
3. 禁止`LATEST`、`LATEST_AT_START`、branch-following read或implicit main fallback。
4. CommitId是repository-scoped bounded opaque token，不增加Dolt hash或UUID grammar。
5. Row stream为`application/vnd.apache.arrow.stream`，不使用JSON/base64/checkpoint/digest
   envelope，不承诺row或batch ordering。
6. 每个cell只做一次value conversion；每表只做一次mapping/schema compilation。
7. Batch按normalized logical payload和row count有界；不得整表materialize。
8. Disconnect/cancel必须显式关闭provider reader并TERM/KILL/wait/reap Dolt child。
9. 所有response带server-generated `X-Request-ID`；error不暴露SQL、stderr、path或raw row。
10. Fixture consumer不拥有Backend schema、business digest、Submit lifecycle、verification
    policy或P3 capability。

### 2.3 Explicit non-goals

- Current store、public ref CAS、table/schema CAS、partial merge/rebase；
- diff、export、ordering guarantee、public delete/repair/backup；
- generic ACL、多tenant isolation、multi-node writer；
- Candidate B production activation或formal selection；
- `inspect_marker()` branch-count退化修复；
- P3 Submit/Archive/History capability或Backend business consumer；
- production-equivalent W1/W2、final image、Compose或Phase 2 complete声明。

## 3. Frozen public contract

### 3.1 Endpoints

```text
GET /v1/repositories/{repository_id}/versioned/refs/{ref_name}
GET /v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog
GET /v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows
    ?table_name=...&unknown_type_policy=REJECT
```

三个GET均无request body，成功status均为`200`。Resolve/catalog返回closed JSON DTO；row
route返回raw Arrow IPC body。所有route复用global bearer、readiness guard、request ID
middleware和SimpleError handlers。

### 3.2 DTO and validation ownership

- Contracts拥有request/response DTO、enum、identifier约束、media type和stable code常量。
- RepositoryId使用`uuid.UUID`。
- Ref使用`Literal["main"]`。
- CommitId使用bounded opaque type；HTTP path只施加单path-segment transport边界。
- Table、column和primary-key column name分别建contract-owned constrained types：全部
  1..64 Unicode code points，拒绝NUL、ASCII control、`/`和`\`；table额外拒绝
  leading/trailing whitespace。比较exact、case-sensitive，不Unicode normalize/case fold。
- Row query的`unknown_type_policy`可省略，省略等价`REJECT`；read不继承import policy。

### 3.3 Stable read failures

| Condition | HTTP | stable code |
| --- | --- | --- |
| Repository absent/not visible | 404 | `REPOSITORY_NOT_FOUND` |
| literal main absent | 404 | `REF_NOT_FOUND` |
| opaque CommitId cannot be located | 404 | `COMMIT_NOT_FOUND` |
| exact table absent | 404 | `TABLE_NOT_FOUND` |
| REJECT policy meets unknown SQL type | 422 | `UNKNOWN_SQL_TYPE` |
| UUID/ref/table/policy wire validation | 422 | `REQUEST_VALIDATION_FAILED` |
| pre-header provider/timeout/malformed Dolt output | 503 | `SERVICE_NOT_READY` |

Headers发送后发生provider、conversion、timeout或transport failure时终止Arrow body，不在
binary body后发送JSON。Client使用transport/Arrow truncation和已收到的request ID报告
`RepositoryStreamError`。

### 3.4 OpenAPI

- resolve/catalog的200 schema引用contracts DTO；
- row 200声明`application/vnd.apache.arrow.stream`和`string/binary` body；
- 401/404/422/503声明`SimpleError`；
- 所有response声明`X-Request-ID` header；
- row query声明exact table constraints、enum和default `REJECT`；
- 不声明JSON row model、ordering、LATEST或P3字段。

## 4. Frozen internal architecture

### 4.1 Compiled Arrow plan

选择request/table-scoped compilation，拒绝caller SQL spelling驱动的process-lifetime
cache。内部nominal types建议为：

```text
CompiledColumnPlan
  field: pyarrow.Field
  converter: callable
  nullable/range validation
  copied immutable metadata bytes

CompiledTablePlan
  catalog: TableCatalog
  columns: tuple[CompiledColumnPlan, ...]
  expected_schema: pyarrow.Schema

NormalizedRow
  values: tuple[object, ...]
  logical_size_bytes: int
```

Plan identity为`(TableCatalog value, UnknownTypePolicy)`；生命周期不超过一次stream或
FULL_SCAN operation，容量为该operation涉及的table/column数，无invalidation。Primitive
Arrow singleton或immutable lookup可作为模块实现细节，但不得暴露mutable metadata dict。
Metadata先复制为immutable bytes pairs，再为field/schema建立fresh container。

`CompiledTablePlan.normalize_row(raw)`负责row width、nullability、logical range和value
conversion，并返回`NormalizedRow`。`record_batch(normalized_rows)`只接受nominal normalized
type，不提供`already_normalized=True`。兼容helper若保留，必须内部compile → normalize once →
batch，不能恢复双重conversion。

`SqlValueConversionError`增加table、column、sql_type ownership，不保存raw value。
必须补齐MEDIUMINT signed/unsigned 24-bit range、non-null NULL、BIT unused high bits以及现有
decimal/temporal/unsigned/binary malformed boundaries。

### 4.2 FULL_SCAN

Verification每表compile一次plan并把同一plan交给production Candidate A stream。每批仍
检查field count、name、type、nullability、metadata和batch row count，结束仍比较total row
count。Optimization不得跳过conversion failure、schema mismatch或manifest/catalog
bidirectional alignment。

Public row stream使用相同private plan abstraction但创建独立request-owned instance，不共享
跨request mutable state或无界cache。

### 4.3 Candidate A read boundary

新增private `versioned_read` application/port/adapter；不得复用import application service。

1. 使用既有visibility primitive确认Repository已发布且可见。
2. Resolve只调用Candidate A `read_ref("main")`。
3. Catalog/row在response前执行strict CommitId existence lookup。
4. 新增`catalog_at(commit_id)`，所有table/schema/count查询使用literal target `AS OF`，
   支持无parent的initial commit。
5. Exact table lookup后使用MySQL identifier quoting和literal CommitId执行row SQL。
6. Branch在步骤3后移动不影响步骤4/5；history无public delete且永久保留。

Import `read_catalog(candidate)`和`read_type_catalog(candidate)`继续要求唯一parent，只抽取
共享strict `_read_candidate_parent()`；不改变parent、marker、revision pinning和错误映射。
Existing bounded catalog memo可继续按target CommitId使用，但其纯LRU测试必须去掉真实Dolt
fixture。不得修改`inspect_marker()`。

### 4.4 Arrow streaming and cancellation

采用stdlib bounded queue/thread bridge为主路径；**不新增除已批准例外外的Service
production dependency**：

```text
ASGI async iterator
  <- bounded queue(maxsize=1)
  <- owned non-daemon worker thread
  <- Arrow IPC writer
  <- Candidate A iterator
  <- ProcessStream / Dolt child
```

**已批准架构例外（P2-R5-S3 Round-12/13 independent review）**：async cleanup在持续
取消下完成executor future时，可使用已属于ASGI栈的AnyIO `CancelScope(shield=True)`。
`anyio`须作为显式`pyproject.toml` runtime dependency钉版本（当前`anyio==4.14.2`）；
不得借此引入其他运行时分发包。该例外触发`container_trigger`（`pyproject.toml`、
`uv.lock`、`Dockerfile` lock SHA）并须在远程container gate记录provenance。

- Route在200前完成repository/commit/catalog/table/policy/plan preflight。
- Worker拥有provider iterator、Arrow writer和Dolt child；async iterator拥有worker lifecycle。
- Producer使用有界put/poll并检查`threading.Event`，形成backpressure。
- Async generator disconnect/cancel/finally设置event并等待worker结束。
- ProcessStream selector至多现有短poll周期检查event；取消执行`close(cancelled=True)`，
  保留TERM/KILL/wait/reap和pipe/query cleanup。
- 成功才关闭Arrow writer并输出EOS；failure/cancel不输出EOS。
- 空表输出schema+EOS、零batch。
- Row count上限1024；normalized logical payload target上限4 MiB；单个oversized row独占
  batch并明确metric，仍受64 MiB encoded-line cap。
- 不读取全表后再响应。Time-to-first-batch使用controlled barrier证明，不使用脆弱绝对
  wall-clock阈值。

### 4.5 Remote client

Client完成：create、upload、submit import、get operation、wait operation、resolve、catalog、
stream rows。

- GET只对network/502/503做最多3次bounded exponential retry；404/422不重试。
- create/import重试复用exact idempotency key和body。
- upload只对rewindable/reopenable source自动重试；nonrewindable只发送一次。
- Poll使用monotonic deadline和capped backoff，terminal operation直接返回。
- Finite request transport timeout、stream idle timeout和poll total deadline分离。
- `ArrowIpcByteStream`是async context manager，提供`aiter_bytes()`、`aclose()`、request ID
  和media type；production client不依赖PyArrow。
- Stream只在任何body byte暴露前允许open retry，暴露后不重试。
- Error body/header request ID mismatch、malformed success/error和wrong Arrow media type均为
  typed protocol error；不保存全局`last_request_id`。

### 4.6 Contract-owned fixture consumer

Consumer material放在Repository Client测试边界：

```text
vnext/repository_client/tests/support/versioned_fixture_consumer.py
vnext/repository_client/tests/fixtures/versioned_v1/
vnext/repository_service/tests/test_versioned_fixture_consumer_e2e.py
```

Client consumer只importcontracts/client和test-only Arrow decoder。Service harness启动真实
Dolt与uvicorn，再通过`uv run --project vnext/repository_client ...`启动consumer外部进程；
Service package和test module都不得importClient。

Consumer用两个小型opaque import package完成C1/C2流程；C2发布后重读C1和C2，比较公开
catalog/row facts。Row断言按key转成set/sorted view，不依赖batch/row order。Fixture不进入
Backend schema、digest、Submit lifecycle或verification policy。Teardown必须关闭stream/client、
停止/reap service并清除temporary durable root。

## 5. Testing and evidence contract

### 5.1 Markers

- pure DTO/mapping/parser/plan/cache/client MockTransport为`unit`，不得使用`import_layout`、
  `import_provider`、`lifecycle_settings()`或执行`dolt init`；
- 真实Dolt、subprocess、uvicorn或落盘lifecycle为`integration`；
- `Event.wait`、`thread.join`、sleep/timeout相对预算、disconnect/reap和真实HTTP fixture
  consumer同时标`serial`并以`-n 0`运行；
- 不手写Dolt `skipif`，统一由Repository Service `conftest.py`门禁。

### 5.2 Required evidence

| Requirement | Evidence |
| --- | --- |
| type mapping no longer rows × columns | compiler/type mapping call count = columns per table |
| each cell converted once | converter call count = rows × columns |
| schema reused | schema construction count = tables per operation |
| exact mapping | known family plus REJECT/STRINGIFY metadata and NULL/value boundaries |
| FULL_SCAN safety | every batch full field comparison plus total row count |
| commit pin | real Dolt C0/C1/C2 and branch movement |
| bounded batch | row/normalized-byte bounds and isolated oversized row |
| first batch | controlled provider barrier; no whole-table materialization |
| backpressure | queue capacity and stalled client evidence |
| disconnect | event propagation, TERM/KILL/wait/reap, no PID/thread/query leak |
| midstream failure | truncated Arrow/transport failure, no JSON trailer/EOS |
| client semantics | GET/mutation/nonrewindable/poll/stream/request-ID tests |
| public consumer | real HTTP create→upload→import→poll→C1/C2 reads |
| classification | parked-Dolt `-m unit` succeeds |

R5不使用10–100 MB真实业务SQL作为普通测试fixture，也不接收host path让Service直接执行。
R6接收真实producer生成的正式import package，以external read-only dataset ID/revision提供，
并通过public Remote client测量。若只有raw SQL，必须先由上游package producer在Repository
Service边界外生成合法package。

## 6. Global execution rules

每个stage开始必须：

1. `git status --short --branch`确认预期branch和clean worktree；
2. `git rev-parse HEAD`记录`start_sha`；
3. 复读本文件的stage、global invariants和上一步handoff；
4. 列出实际allowed paths；不修改用户已有或无关文件；
5. 先写本stage contract/behavior tests，再做最小实现；
6. 定向gate全绿后运行`git diff --check`，只提交本stage文件；
7. 记录commit SHA、commands/results、container trigger audit和下一stage readiness；
8. 当前stage失败时停留当前边界，不提前实现下一stage。

Dependency一律exact pin并使用`uv add --dev`或`uv add`。如果修改
`vnext/repository_service/uv.lock`，必须同步更新Service Dockerfile的
`ARG UV_LOCK_SHA256`，该行为同时触发本round提前container gate。

## 7. Green stages

### S1 — Compiled Arrow mapping and single normalization

**Goal and invariants**

建立private compiled plan/normalized row边界；每cell只转换一次，每表只构造一次schema，
保持现有public/helper mapping语义并补齐logical validation。S1不激活任何read route。

**Allowed paths**

```text
vnext/repository_service/src/gateway_repository_service/arrow_mapping.py
vnext/repository_service/src/gateway_repository_service/candidate_a/dolt_cli.py
vnext/repository_service/src/gateway_repository_service/candidate_a/sql.py
vnext/repository_service/src/gateway_repository_service/providers.py
vnext/repository_service/src/gateway_repository_service/workflow.py
vnext/repository_service/src/gateway_repository_service/versioned_import/ports.py
vnext/repository_service/src/gateway_repository_service/versioned_import/provider.py
vnext/repository_service/src/gateway_repository_service/versioned_import/verification.py
vnext/repository_service/src/gateway_repository_service/versioned_import/worker.py
vnext/repository_service/tests/test_p2_r1_primitives.py
vnext/repository_service/tests/test_import_verification.py
vnext/repository_service/tests/test_import_provider.py
vnext/repository_service/tests/test_arrow_mapping_plan.py                 # new if useful
vnext/repository_service/tests/support/import_worker_harness.py
vnext/repository_service/tests/test_p2_r1_audit_corrective.py
```

`providers.py`只允许适配shared nominal normalized type，禁止改变provider selection、SQL
server lifecycle、matrix或formal runner。Import port/provider/worker只允许传递compiled plan或
保持类型协议闭合，不改变import state/CAS/recovery。

**Explicit non-goals**

- contracts DTO、HTTP、runtime/settings、ProcessStream cancellation；
- public `versioned_read` package；
- Client/fixture；
- catalog parent parser；
- Candidate B activation；
- benchmark、Docker/Compose或R6 evidence。

**Production changes**

- `CompiledColumnPlan`、`CompiledTablePlan`、`NormalizedRow`或等价private nominal model；
- compile-time converter/metadata/schema；
- Candidate A row accumulator按normalized logical bytes分batch；
- FULL_SCAN每表复用plan；
- narrow compatibility wrapper保证probe/tests不双重normalize；
- `SqlValueConversionError`加入table ownership且不保存raw value。
- catalog memo测试改为pure object/cache construction，不再通过`import_layout`执行`dolt init`。

**Tests and markers**

全部S1新增测试必须是pure `unit`。覆盖：

- compiler/type mapping/schema/converter call count；
- known SQL family exact Arrow types和metadata；
- REJECT/STRINGIFY、NULL preservation和unknown stringify conversion failure；
- nullable/non-null NULL；
- MEDIUMINT signed/unsigned 24-bit min/max/underflow/overflow；
- BIT(1/7/8/9/64) valid、unused high bits、oversize；
- decimal128/256、temporal fsp/timezone、unsigned/binary malformed；
- normalized byte accounting、row bound、byte bound和isolated oversized row；
- FULL_SCAN每批schema比较与row count不回退；
- compatibility helper与Candidate A accumulator每cell一次；
- catalog memo test不得再请求`import_layout`、`import_provider`或其他真实Dolt fixture。

**Directed validation**

```bash
cd vnext/repository_service
uv run pytest -q tests/test_p2_r1_primitives.py tests/test_arrow_mapping_plan.py \
  tests/test_import_verification.py -m unit
uv run pytest -q tests/test_import_provider.py -k "stream or catalog_memo" -m unit
uv run pytest -m unit

mv /usr/local/bin/dolt /usr/local/bin/dolt.parked
uv run pytest -m unit
mv /usr/local/bin/dolt.parked /usr/local/bin/dolt

uv run ruff check .
uv run mypy
git diff --check
```

若未创建`tests/test_arrow_mapping_plan.py`，从命令移除该路径并在handoff说明测试实际归属，
不得创建空占位测试文件。Parked-Dolt验证后必须恢复exact `/usr/local/bin/dolt`；若pytest
失败，handoff记录失败且仍先恢复binary，不得让后续stage继承parked状态。S1不得运行
Docker/Compose或完整P2矩阵。

**Failure/rollback boundary**

任何import verification、Candidate A stream output、error attribution或batch bound回归都在
S1内修复；不得通过放宽contract、删除assertion或推迟到public route解决。S1为单个可回退
commit，无DTO/wire/durable migration。

**Expected commit**

```text
refactor(repository): compile Arrow table mappings once
```

**Exit**

```yaml
mapping_compilation_per_table: 1
schema_construction_per_table: 1
conversion_per_cell: 1
full_scan_field_checks_preserved: yes
logical_value_boundaries: pass
catalog_memo_unit_without_dolt: yes
unit_dolt_parked: pass
real_dolt_required: no
container_gate_triggered: no
s2_ready: yes
```

### S2 — Candidate A commit-pinned read provider

**Goal**：新增parent-independent public read provider，支持C0/C1/C2和branch movement；只对
import catalog抽取strict parent parser，不改变import行为。

**Allowed paths**：`candidate_a/`、new `versioned_read/` private modules、
`versioned_import/provider.py` narrow helper、`process.py` cancel primitive、provider/process
tests。不得修改HTTP/client/fixture、`inspect_marker()`、Candidate B selection。

**Tests**：pure parser/unit；真实Dolt `integration`覆盖main resolve、C0 catalog、C1/C2、
branch movement、exact identifiers、missing commit/table、malformed Dolt/timeout；固定取消预算
为`integration + serial`。

**Directed gate**：new provider/process tests的unit、integration、serial分组；import provider
regression；ruff/mypy；`git diff --check`。

**Failure boundary**：read adapter尚未注册wire，任何import regression必须在S2内关闭。

**Expected commit**：`feat(repository): add commit-pinned Candidate A reads`

**Exit**：C0/C1/C2 literal read通过，branch movement不改变pinned result，Dolt child可显式
cancel/reap，`s3_ready=yes`。默认不触发container gate。

### S3 — Contracts, HTTP routes and Arrow response

**Goal**：修正/完成contracts，注册三个GET route，激活stable error/OpenAPI和bounded async
Arrow response。

**Allowed paths**：Repository Contracts source/tests；Service `http/`、`versioned_read/`、
`app.py`、`runtime.py`、必要private settings/tests。不得修改Client/fixture、Compose、P3。

**Tests**：Contracts unit；DTO/OpenAPI/auth/readiness/error unit；Arrow body、empty/large/wide、
first-batch/backpressure/midstream/disconnect为integration，涉及固定预算者加serial。

**Directed gate**：Contracts四命令；Service new HTTP/stream unit/integration/serial；ruff/mypy；
`git diff --check`。

**Failure boundary**：DTO、router和registration同一commit；不得留下定义但返回placeholder的
route。若需要Service production dependency或lockfile，立即执行container trigger流程。

**Expected commit**：`feat(repository): expose commit-pinned versioned reads`

**Exit**：OpenAPI与contract一致，pre-header error均为SimpleError，post-header failure截断，
无thread/process/query leak，`s4_ready=yes`。

### S4 — Complete Remote Repository client

**Goal**：完成V1 async façade、poll、retry、protocol error和owned raw Arrow stream。

**Allowed paths**：Repository Client source/tests、必要Contracts exports（含
`path_transport`、`wire_limits`）、formal contract
[`repository-service.md`](../contracts/repository-service.md) §5/§6 wire 声明，以及为
对称执行上述 wire 所需的 Service `versioned_read` route/wire/tests 与 `versioned_import`
operation wire guard/tests。禁止 PyArrow production dependency、Backend adapter 或 P3。

**Tests**：MockTransport unit覆盖GET bounded retry、same-key mutation、nonrewindable单次、
poll deadline/backoff、stream pre-byte retry/after-byte no retry、context close、wrong media type、
malformed body和request-ID mismatch；catalog/operation success limit 与 error limit 分离；
Arrow in-flight open ownership。

**Directed gate**：Client `uv lock --check`、ruff、mypy、pytest；Contracts regression；
Service versioned_read/operation HTTP subset；`git diff --check`。

**Failure boundary**：Round-2/3/4 构成 **S3/formal wire reopen**（canonical base64url
`CommitId` path segment、catalog/operation JSON size limits）；Client、Contracts、Service
须同批交付或同批回退，**不得**再声明 Client distribution 单独可回退且 Service wire 不变。
证据 commit：`37208a6`（Round-2）、`bc9aa49`（Round-3）、Round-4 fix commit。

**Expected commit**：`feat(repository-client): complete V1 Repository client`（初版）；
后续 round fix：`fix(repository): close P2-R5-S4 independent round-N findings`。

**Exit**：全部V1 method typed，stream ownership确定，无Service dependency，formal wire 与
stage authority 一致，`s5_ready=yes`。

### S5 — Contract-owned fixture consumer

**Goal**：仅通过public HTTP/Remote client证明create→upload→import→poll→C1/C2 immutable
read。

**Allowed paths**：Client test support/fixtures/dev dependency；Service external-process E2E
harness。若需要PyArrow，以`uv add --dev 'pyarrow==25.0.0'`加入Client，不修改Service lock。

**Tests/markers**：Client fixture/parser unit；Service真实Dolt+uvicorn+consumer subprocess测试
明确`integration + serial`并`-n 0`。禁止Service test import Client。

**Directed gate**：Client四命令；fixture consumer nodeid；distribution boundary tests；
teardown/process leak evidence；ruff/mypy；`git diff --check`。

**Failure boundary**：fixture/test-only dependency独立可回退；不得为方便绕开HTTP、直接调用
Dolt或创建第四distribution。

**Expected commit**：`test(repository): add public Versioned fixture-consumer e2e`

**Exit**：C2发布后C1/C2均按exact expected public facts可读、无ordering假设、资源清理通过，
`s6_ready=yes`。Client dev-only lock不进入Service image；如实际build context相反，触发
container gate。

### S6 — Functional and evidence closure

**Goal**：关闭R5全部非container gate和read-path真实性/性能证据，不修改production。

**Allowed paths**：测试、test support、R5 evidence/handoff staging section。禁止Dockerfile、
Compose/harness、production dependency、真实业务数据入库。

**Required commands**：

```bash
cd vnext/repository_service
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m serial -n 0

mv /usr/local/bin/dolt /usr/local/bin/dolt.parked
uv run pytest -m unit
mv /usr/local/bin/dolt.parked /usr/local/bin/dolt

cd /root/gateway-data-management-system
./vnext/scripts/run-tests.sh --ignore=tests/test_import_compose_e2e.py
git diff --check
git status --short
```

五个Python package分别执行`uv run ruff check . && uv run mypy`。若parked-Dolt命令中途异常，
必须先恢复exact `/usr/local/bin/dolt`，不得遗留parked状态。

**Expected commit**：`test(repository): close P2-R5 read and stream gates`

**Exit**：required matrix全绿、unit分类正确、无process/thread/temp leak、container未被宽泛
marker隐式跳过，`s7_ready=yes`。

### S7 — R5 final handoff

**Goal**：记录final validated SHA、commands/counts、container provenance差异、R6 inputs和
reopen conditions；同步Service README的activated surface。

**Allowed paths**：本执行文档handoff、相关P2计划和Service README。不得改production/test。

**Expected commit**：`docs(repository): record P2-R5 handoff`

**Exit**：

```yaml
p2_r5_exit: pass
p2_r6_ready: yes
worktree_clean: yes
validated_code_sha: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
container_validated_code_sha: 901a13b92a0a92130d9afa001d8eb4273d544566
container_validation_deferred_to: P2-R6
production_retest_required: yes
phase_2_complete: no
```

S7不得写`image_matches_build_context: true`或把R4 image ID称为R5 evidence。

## P2-R5-S7 final handoff — 2026-08-12

### 1. SHA 与阶段状态

```yaml
round: P2-R5-S7
s7_start_sha: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
validated_code_sha: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
s6_external_review:
  round: P2-R5-S6-independent-round-1
  reviewed_tip: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
  verdict: approved
  blocking_findings: []
p2_r5_exit: pass
p2_r6_ready: yes
production_retest_required: yes
phase_2_complete: no
container_trigger: no
container_gate_run: no
s7_tests_rerun: no
```

`validated_code_sha`是S6 gate已运行且经外部独立审查批准的代码SHA，不是本S7文档commit
SHA。S7文档commit完成后成为`r6_entry_sha`/`handoff_documentation_sha`，只在最终实现报告
中记录，不在本提交内容中自引用。

### 2. Commit lineage

核对命令：

```bash
git log --reverse --format='%H %s' \
  f346ef943b41191a93ad5d8a5174d218c25fb543..7091c2c4836eebdc4cbee4424f20297b2d2f88bb
```

按stage分组（含全部累计remediation/review commits，不省略）：

```yaml
commit_lineage:
  s0:
    stage_initial: a61e664b45439dafc0ef8e2b01317400d27672f1  # docs(repository): add P2-R5 execution plan
    stage_final_reviewed_tip: a61e664b45439dafc0ef8e2b01317400d27672f1
    stage_exit: pass
  s1:
    stage_initial: 6b84b1d9142ab11d85727087de56503b674f97f4  # refactor(repository): compile Arrow table mappings once
    remediation_commits:
      - 806cc78675dbe3a98b0c4d54234f6a563b7e7698  # fix(repository): close S1 compiled-plan call-count gaps
      - 5fbf3ffdc9dff7b2f210b5c843da986c95618812  # fix(repository): close S1 round-2 compiled-plan audit gaps
      - b318d1a480603f7ec3e78372b89526fbeab3b625  # fix(repository): close S1 round-3 verification and boundary gaps
      - 862354af2b655aa480718464771ba4711c1f0dc0  # fix(repository): close S1 round-4 decimal and temporal boundary gaps
    stage_final_reviewed_tip: 862354af2b655aa480718464771ba4711c1f0dc0
    stage_exit: pass
  s2:
    stage_initial: 44b8ea00a93b65f2eb614d5f8366b57f52fcd5e1  # feat(repository): add commit-pinned Candidate A reads
    remediation_commits:
      - 8a8c5258f054f39c0a70b5038bd1d32e444452f4  # fix(repository): close P2-R5-S2 review findings
      - fc26fbac1ddd3a53dc220e8ba96cc9542bb68a79  # fix(repository): close P2-R5-S2 P3 residuals
      - 5a6c25f1a5a46916d0cad03515579d4bf9fac848  # fix(repository): close P2-R5-S2 round-2 review findings
      - ccd1cd5a6e4a0ff06fb3c4351316097477297bb7  # fix(repository): close P2-R5-S2 round-3 review findings
    stage_final_reviewed_tip: ccd1cd5a6e4a0ff06fb3c4351316097477297bb7
    stage_exit: pass
  s3:
    stage_initial: 83fc61a28bf083d99966b782d3f2648381057f34  # feat(repository): expose commit-pinned versioned reads
    remediation_commits:
      - 118c7e42e086c0e180f4cd6fb1284a3759ca5804  # fix(repository): close P2-R5-S3 review findings
      - 9ec640f9b169f0552ad3cacd0b851b90e91c9f6a  # fix(repository): close P2-R5-S3 review round-2 findings
      - 3cba5842009ca74ef314b29f8250d97cf421fa81  # fix(repository): close P2-R5-S3 independent review findings
      - b1ce410d46af04eac35c631a95af91ac7d8a1f51  # fix(repository): close P2-R5-S3 independent round-4 findings
      - 554d843adb0393d19b6dc26a50a0608576d5be3e  # fix(repository): close P2-R5-S3 independent round-5 findings
      - 16053d1319b16e63dc8d81c8fcfdba28d2298207  # fix(repository): close P2-R5-S3 independent round-6 findings
      - 15a097ab97b12f8c54f74131e782281d4a6aa30f  # fix(repository): close P2-R5-S3 independent round-7 findings
      - ab60abadb3be89812b8b2e20c013d5e7324d9c6c  # fix(repository): close P2-R5-S3 independent round-8 findings
      - d2d1b4256b5bf0f2aed32717341100bfef8953c2  # fix(repository): close P2-R5-S3 independent round-9 findings
      - e37cdd6d250e723c5502f5b7b2512c96600c31c2  # test(repository): mark control-db readiness test serial
      - 294e361469cfddb89955769323e23ad71757d902  # docs(AGENTS): refresh unit gate stats and mypy timing note
      - 09576de0d1b6cce67913f267e808ab1115d319ab  # test(repository): fix concurrent patch restore race in field_limit test
      - 43a40249317c3e0db8a54f15998ca45e443c91d4  # fix(repository): close P2-R5-S3 independent round-10 findings
      - 9b7d6529427a4fe4533edeca95ad92e4f3455596  # fix(repository): close P2-R5-S3 independent round-11 findings
      - 03aa47e9808af4a47be4e24d4ac14e3a86fe09c6  # fix(repository): close P2-R5-S3 independent round-12 findings
      - 9fe929beee2efc1cde2b0999043e9cad9d7948e6  # fix(repository): close P2-R5-S3 independent round-13 findings
      - b36c3a0c2f096f5dfdda91809a38bfe8c1c715cb  # fix(repository): close P2-R5-S3 independent round-14 findings
      - 25891d64b0952976eb2ce8ea45fc9275cda13f36  # docs(deploy): record remote container gate pass and sync exclusions
      - 684f7901bd95eb18ac1563cefcbb6d288aa703bb  # fix(repository): close P2-R5-S3 independent round-1 findings
      - cb1ef42db7dd4957d20cdc4ce3b61cb35c7b9596  # fix(repository): close P2-R5-S3 independent round-1 review findings
      - 13ec2137d7ed8f3da406bf550da68647d2536c77  # docs(deploy): record container gate provenance for cb1ef42
      - 1cab278aaf30e585468340dce0b04cfa6e254f17  # docs(deploy): record container gate provenance for 13ec213
      - 36c7da2c3ad9441efb176338efa44336bef8c532  # docs(repository): record SHA sealing and R5 cleanup inventory
    stage_final_reviewed_tip: 36c7da2c3ad9441efb176338efa44336bef8c532
    stage_exit: pass
  s4:
    stage_initial: 1c96416b6d81ea17ab7eb0dd80b054834be8d942  # feat(repository-client): complete V1 Repository client
    remediation_commits:
      - 8b0234ef450af67c4f0dd4511e729da0f585482f  # fix(repository-client): close P2-R5-S4 independent round-1 findings
      - 37208a6433273c301ede4997fbdd1a3d20d946c8  # fix(repository): close P2-R5-S4 independent round-2 findings
      - bc9aa49d9376439a9c0a88b9a0e273847caaf269  # fix(repository): close P2-R5-S4 independent round-3 findings
      - cec3e529feb6134204f4be8287e74e7edba1c3ec  # fix(repository): close P2-R5-S4 independent round-4 findings
      - cd66e08617ff6bc56316159de52ede6bc5c5e64c  # fix(repository): close P2-R5-S4 independent round-5 findings
      - 8907f892682f397275b6bcc4314e5c53d6f712aa  # fix(repository): close P2-R5-S4 independent round-6 findings
      - 55dbbbe66986c3afaa8a24791e57d61be2cdd2f8  # fix(repository): close P2-R5-S4 independent round-7 findings
      - 2e803aa5e2953ea8ff6d1ac8b8bcfd22558cb509  # fix(repository): close P2-R5-S4 independent round-8 findings
      - 4c9df9b79f45842e6be5ac14f84510ea9c0d7193  # fix(repository): close P2-R5-S4 independent round-9 findings
      - 73651768407f294953812939f79aca371995eba9  # fix(repository): close P2-R5-S4 independent round-10 findings
      - 74fc41b5988db62c4b3a0171484724c7157deafb  # fix(repository): close P2-R5-S4 independent round-11 findings
    stage_final_reviewed_tip: 74fc41b5988db62c4b3a0171484724c7157deafb
    stage_exit: pass
  s5:
    stage_initial: 430775f0249fa4d9d43b4575b55e4021c5b90e43  # test(repository): add public Versioned fixture-consumer e2e
    remediation_commits:
      - 0ea978d4c76c334e4fbb05a09e85eee74cc3729c  # fix(repository): close P2-R5-S5 review findings
      - df0245ec24aa34df4c10a434096a0a624749154e  # fix(repository): close P2-R5-S5 round-2 review findings
      - 37332ceb204e44e3c18f8cdccba81ab74aafe0f0  # fix(repository): close P2-R5-S5 round-3 review findings
      - ebb599952461e4c57b4f12ec834e79eac53ec169  # fix(repository): close P2-R5-S5 round-4 review findings
      - d77f0282bad4f76e822dcd24a9ec1445e52ef588  # fix(repository): close P2-R5-S5 round-5 review findings
      - caf4b30feaa8152d800aea90743eb2a0f3e94255  # fix(repository): close P2-R5-S5 round-6 P1-03 state-probe cleanup
    stage_final_reviewed_tip: caf4b30feaa8152d800aea90743eb2a0f3e94255
    stage_exit: pass
  s6:
    stage_initial: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb  # test(repository): close P2-R5 read and stream gates
    stage_final_reviewed_tip: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
    s6_external_review:
      round: P2-R5-S6-independent-round-1
      verdict: approved
    stage_exit: pass
```

### 3. S6 gate 事实

S6不重新运行；以下证据来自`P2-R5-S6-independent-round-1`外部独立审查，reviewed tip
`7091c2c4836eebdc4cbee4424f20297b2d2f88bb`。

```yaml
s6_functional_gate:
  cleanup_03_nodeid:
    command: uv run pytest tests/test_import_shutdown.py::test_runtime_shutdown_propagates_bridge_shutdown_error_after_releasing_resources
    result: 1 passed
  repository_service_unit:
    command: cd vnext/repository_service && uv run pytest -m unit
    result: 954 passed, 1 skipped
    unit_skip_nodeid:
      - tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup
    unit_skip_note: target-container-only evidence deferred to R6 delegated cgroup gate; not a unit classification error
  repository_service_integration_raw:
    command: cd vnext/repository_service && uv run pytest -m integration
    result: 329 passed, 1 failed
    deferred_failure:
      - tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
  repository_service_serial_raw:
    command: cd vnext/repository_service && uv run pytest -m serial -n 0
    result: 110 passed, 1 failed, 1174 deselected
    deferred_failure:
      - tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
  unit_dolt_parked:
    command: mv dolt.parked; uv run pytest -m unit; restore dolt
    result: 954 passed, 1 skipped
  authoritative_non_container_gate:
    command: ./vnext/scripts/run-tests.sh --ignore=tests/test_import_compose_e2e.py
    result: pass
    repository_service_parallel: 1173 passed
    repository_service_serial: 110 passed
  five_package_ruff_mypy: pass
  git_diff_check: pass
  resource_leaks: none
  process_thread_temp_leaks: no
```

integration/serial裸命令**不得**描述为全绿；各自唯一失败是已登记延期的Compose nodeid。
S6 pass的authority是精确排除该实际container文件后的非container gate。

**Transient parallel failure**（外部评审观察，如实记录）：

```yaml
transient_parallel_failure:
  nodeid: tests/test_import_worker.py::test_context_load_failure_releases_reservation_and_in_flight
  first_parallel_run: failed once
  isolated_rerun: pass
  authoritative_run_tests_ignore: pass
  code_fix: none
  external_review_severity: not P1/P2
  r6_obligation: if reproduced in final R6 matrix, must close within R6; cannot remain a known harmless flake
```

### 4. R5-CLEANUP inventory

见§8.1。S7状态摘要：

```yaml
post_r5_cleanup_inventory:
  - id: R5-CLEANUP-01
    status: open_deferred
    owner: P2-R6-capacity
    phase_2_exit_blocker: no
  - id: R5-CLEANUP-02
    status: open_deferred
    owner: P2-R6-capacity
    phase_2_exit_blocker: yes
  - id: R5-CLEANUP-03
    status: closed
    owner: P2-R5-S6-lifecycle-regression
    evidence:
      nodeid: tests/test_import_shutdown.py::test_runtime_shutdown_propagates_bridge_shutdown_error_after_releasing_resources
      validated_code_sha: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
      external_review: approved
  - id: R5-CLEANUP-04
    status: open_deferred
    owner: pre-P2-exit-cleanup
    phase_2_exit_blocker: no
  - id: R5-CLEANUP-05
    status: open_deferred
    owner: lifecycle-cleanup
    phase_2_exit_blocker: no
  - id: R5-CLEANUP-06
    status: open_deferred
    owner: batch-cleanup
    phase_2_exit_blocker: no
```

`R5-CLEANUP-02`必须由R6在Phase 2 exit前关闭。其余open项由R6重新确认owner、关闭或形成
authority允许的accepted defer；不得静默丢失。

### 5. Container provenance 差异

```yaml
container_provenance:
  validated_code_sha: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
  container_validated_code_sha: 901a13b92a0a92130d9afa001d8eb4273d544566
  current_source_container_validated: no
  image_matches_current_build_context: not_claimed
  historical_image_status: historical_or_superseded_for_current_r5_source
  container_validation_deferred_to: P2-R6
  production_retest_required: yes
```

`container_validated_code_sha`来自[P2-R4 Async Versioned Import Staged Execution
Plan](p2-r4-async-versioned-import-execution-plan.md) handoff，对当前R5 source为
historical/superseded evidence。S7不写`image_matches_build_context: true`，不把R4历史
image ID称为R5/current evidence。

S7文档commit完成后`r6_entry_sha`将不同于`validated_code_sha`。这不触发S7 container
gate，但意味着R6最终candidate必须从包含S7文档提交的source tree重新封板、build和验证。

### 6. Deferred container inventory

**实际已存在、延期的nodeid**：

```yaml
deferred_container_gate_nodeids:
  - tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
```

**R6计划新增、R5未收集的gates**（`test_versioned_read_compose_e2e.py`当前不存在）：

```yaml
r6_required_new_container_gates:
  status: planned_not_collected_in_r5
  nodeids:
    - tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
    - tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
```

不得把计划nodeid写入已存在deferred inventory，也不得声称已执行。

### 7. R6 input inventory

R6必须完整接收并关闭以下输入；canonical v8 command与§9一致，不自行改写formal参数。

1. 最终source candidate上无排除的`./vnext/scripts/run-tests.sh`。
2. final production image build、build-input revision、source-tree SHA、image identity。
3. 远端builder到gate host的可审计image transfer和identity校验。
4. R4 import restart/replay Compose gate（`test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay`）。
5. R5 compose内部Remote Client commit-pinned read（`test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network`）。
6. R5 gate-host Remote Client commit-pinned read（`test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host`）。
7. fresh/restart/restored Compose lifecycle。
8. Candidate A 66-record v8 formal rerun（§9 canonical command）。
9. external read-only 10–100 MB脱敏真实W1：dataset ID/revision、package SHA/size、producer、
   classification、schema/rows、expected public facts。
10. near-200 MB same-shape synthetic W2：`synthetic=true`；schema/row-width/NULL/key/index/
    value distribution与W1对齐。
11. `R5-CLEANUP-02` concurrent slow-stream polling pressure measurement/closure。
12. 全部container/network/volume/process/thread/temp cleanup。
13. 重新观察S6曾出现一次的transient import-worker test（§3 `transient_parallel_failure`）。
14. 关闭`production_retest_required`；否则Phase 2 exit为no-go。

### 8. Reopen conditions

保留§10全部reopen conditions。R6遇到以下情况必须回到owning authority，不得在实现中
自行扩展：

- 需要LATEST/ordering/public CAS/history pruning；
- Arrow需要envelope/resume/digest；
- disconnect后bridge/Dolt不能有界退出；
- 未知SQL type不接受REJECT/STRINGIFY；
- 单row超过64 MiB safety cap；
- 需要Service import Client/Backend/P3；
- 需要Candidate B production activation；
- final candidate container/provenance不一致。

## 8. Container trigger and R6 inventory

R5默认不触发container gate。以下任一变化立即终止延期，并在所属stage执行风险匹配的
build/Compose gate：

- Service Dockerfile、base image、OS package、build script/provenance/label；
- Service `uv.lock`、production dependency、lock SHA/build arg；
- Compose command/user/path/volume/network/secret/env/healthcheck；
- 真实Docker/Compose harness；
- 只有container boundary才能验证的安全、持久化或恢复结论。

S0时真实存在的deferred nodeid只有：

```yaml
deferred_container_gate_nodeids:
  - tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
```

R5不创建Compose test。R6在final candidate阶段新增并执行建议nodeid：

```yaml
r6_required_new_container_gates:
  status: planned_not_collected_in_r5
  nodeids:
    - tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
    - tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
```

上述建议nodeid在R5不存在，handoff必须与实际deferred inventory分栏，不得伪称已收集。

### 8.1 Post-R5 cleanup inventory

S3累计评审留下的下列项目不重开已闭合的HTTP/Arrow correctness结论，也不
扩展S4的Client-only allowed paths；但必须显式转交到后续cleanup/R6，不得因当前
gate全绿而静默关闭。每项只能在对应exit evidence形成后移出清单：

```yaml
post_r5_cleanup_inventory:
  - id: R5-CLEANUP-01
    status: open_deferred
    item: http_read_catalog_memo_lifetime
    evidence: per-request HTTP service/provider/CLI construction prevents cross-request memo hits
    owner: P2-R6-capacity
    phase_2_exit_blocker: no
    exit: measured shared-cache benefit with a bounded lifetime, or an explicit no-cache decision
  - id: R5-CLEANUP-02
    status: open_deferred
    item: arrow_bridge_to_thread_polling_pressure
    evidence: each slow stream repeatedly schedules queue.get polling on the default executor
    owner: P2-R6-capacity
    phase_2_exit_blocker: yes
    exit: concurrent slow-stream measurement within the frozen bound, or an event-driven bridge
  - id: R5-CLEANUP-03
    status: closed
    item: runtime_shutdown_bridge_failure_wiring_test
    evidence: cleanup ordering exists, but no direct regression forces close_all failure through runtime shutdown
    owner: P2-R5-S6-lifecycle-regression
    phase_2_exit_blocker: yes
    exit: direct test proves bridge error propagation after control store and root lock release
    closure_evidence:
      nodeid: tests/test_import_shutdown.py::test_runtime_shutdown_propagates_bridge_shutdown_error_after_releasing_resources
      validated_code_sha: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
      external_review: approved
  - id: R5-CLEANUP-04
    status: open_deferred
    item: global_arrow_bridge_test_hooks
    evidence: production lifecycle paths still consult process-global ClassVar test barriers
    owner: pre-P2-exit-cleanup
    phase_2_exit_blocker: no
    exit: instance-scoped probe/state-machine seam, or an explicit reviewed decision to retain the hooks
  - id: R5-CLEANUP-05
    status: open_deferred
    item: command_result_cancelled_observability
    evidence: upper-layer row cancellation can close ProcessStream without cancelled=True
    owner: lifecycle-cleanup
    phase_2_exit_blocker: no
    exit: upper-layer cancellation deterministically reports CommandResult.cancelled=true
  - id: R5-CLEANUP-06
    status: open_deferred
    item: dead_parameters_and_redundant_branches
    evidence: simple_error_response status_code, resolve_main re-raise, and duplicate provider fallback remain
    owner: batch-cleanup
    phase_2_exit_blocker: no
    exit: dead code is removed while existing public behavior tests remain green
```

`R5-CLEANUP-01`的共享memo不得在无measurement时直接改为process-wide cache；容量、
invalidation和并发共享周期由R6决定。`R5-CLEANUP-02`是Phase 2 exit前必关项；
`R5-CLEANUP-03`已在S6关闭。其余项可按owner批次清理或形成明确的accepted-defer记录。

## 9. Production retest handoff to R6

R5修改provider streaming、Arrow normalization和batch contract，因此P2-R1 v8 decision要求
在最终source/image上重跑Candidate A 66-record formal。R6拥有：

1. 无排除的`./vnext/scripts/run-tests.sh`；
2. final production image build/provenance和镜像传输；
3. R4 restart/replay及R5 Compose内外client smoke；
4. Candidate A 66-record v8 formal rerun；
5. 10–100 MB脱敏真实W1 public HTTP/client measurement；
6. near-200 MB same-shape synthetic W2 boundary；
7. fresh/restart/restored Compose和全部资源清理。

Canonical v8 command：

```bash
sudo env \
  GATEWAY_P2R1_REPO_ROOT=<clean-final-source-checkout> \
  GATEWAY_P2R1_IMAGE=gateway-repository-service:p2-r6-final \
  GATEWAY_P2R1_CACHE_CONDITION=retained-dependency-cache \
  /usr/local/libexec/gateway-p2r1-target-launcher.sh \
  --output /var/lib/gateway/repository/audit-rerun/<unique-r6-run>/p2-r1.jsonl \
  --v8-formal \
  --runs 5
```

真实W1输入在R6 kickoff预检时以external read-only正式import package提供，记录dataset
ID/revision、package SHA/size、脱敏分类、schema/rows、expected public facts和producer。
Synthetic W2必须匹配W1 schema、row width、NULL、key/index和value distribution，只证明
boundary safety/resource peak。只有final source/image provenance一致、W1/W2、66-record、
Compose和cleanup全通过，才可设置`production_retest_required=no`和`phase_2_complete=yes`。

## 10. Reopen conditions

以下情况暂停当前stage并回到owning contract/design，不在实现中自行扩展：

- 需要LATEST、ordering、public CAS、history pruning或CommitId provider grammar；
- Arrow response需要JSON envelope、resume/checkpoint或content digest；
- bounded bridge不能在disconnect后有界退出worker/Dolt；
- 真实业务出现contract未列known SQL type且不接受REJECT/STRINGIFY；
- 单row超过64 MiB provider framing safety cap；
- 需要Service依赖Client、Backend schema或P3 policy；
- 需要Candidate B production activation；
- container trigger发生但本stage无法运行required container evidence。

## 11. S0 handoff

```yaml
round: P2-R5-S0
status: pass
design_blockers: none
public_contract_frozen: yes
arrow_plan_frozen: request_table_scoped_compilation
normalization_boundary_frozen: nominal_normalized_row_single_conversion
public_catalog_frozen: parent_independent_catalog_at_commit
stream_bridge_frozen: stdlib_bounded_queue_explicit_cancel
client_stream_frozen: async_context_managed_raw_arrow_bytes
fixture_consumer_owner: repository_client_test_boundary
real_business_w1_available: yes
real_business_w1_used_in_r5: no
synthetic_w2_owner: P2-R6
container_validation_deferred_to: P2-R6
production_retest_required: yes
p2_r5_s1_implementation_ready: yes
```

S1开始前唯一operational prerequisite是S0文档commit已形成clean HEAD；除此之外无代码实现
阻塞条件。

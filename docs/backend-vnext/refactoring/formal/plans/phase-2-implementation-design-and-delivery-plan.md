# Phase 2 Implementation Design and Delivery Plan

状态：正式实施设计（Accepted）

日期：2026-07-30

适用阶段：Phase 2 — Repository Service Foundation

Owner：Backend vNext Architecture（交付顺序、physical ownership、gate与release）；
public/persisted/effect语义仍由对应contract owner拥有

详细范围：F0、WP0–WP9、37个review revision和exact-commit Phase exit

依赖：

- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](implementation-stages.md)
- [Repository Service Contract](../contracts/repository-service.md)
- [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)
- [External Effect and Recovery](../contracts/external-effect-and-recovery.md)
- [Fixture Oracle and Conformance](../contracts/fixture-oracle-and-conformance.md)
- [Performance Measurement and Baseline](../contracts/performance-measurement-and-baseline.md)
- [Phase 2 Requirement Traceability](phase-2-requirement-traceability.yaml)

## 1. Goal, scope and delivery invariants

本文把Phase 2收敛为：

```text
F0 formal closure
  -> WP0
  -> max(WP1, WP2)
  -> WP3
  -> WP4
  -> max(WP5, WP6)
  -> WP7
  -> WP8
  -> WP9-R1..R3
  -> WP9-R4 exact-commit exit
```

Phase 2交付独立containerized Repository Service、contracts/client/service三个Python
distribution、Dolt-backed VersionedTableStore、SQLite-backed CurrentTableStore、
journal/recovery、artifact、maintenance、安全、运维和可执行release evidence。

固定实施不变量：

1. 未完成的route不注册、capability不advertise、required cell不activate。
2. 每个revision只有一个semantic axis，并保持当时已激活gate全绿。
3. Public activation必须在同一revision原子加入contract、SDK、route、auth inventory、
   Local/Remote observation和required cells。
4. Storage format从第一次实现起带version；format change不得用silent downgrade或
   destructive startup migration回滚。
5. Caller可选verification/concurrency/read policy，但不能关闭auth、input safety、
   idempotency、journal、fencing、effect evidence和reconciliation。
6. 不建设无consumer framework、stub route、generic SQL/DDL、dynamic plugin、Celery/
   Redis/ORM、business workflow或multi-node shared writer。
7. Phase 1 source/runtime/image/locks/vectors/golden/scenario/sign-off identity只读保护。

## 2. Fixed engineering topology

```text
vnext/
  repository_contracts/
    pyproject.toml
    uv.lock
    src/gateway_repository_contracts/
    tests/
  repository_client/
    pyproject.toml
    uv.lock
    src/gateway_repository_client/
    tests/
  repository_service/
    pyproject.toml
    uv.lock
    src/gateway_repository_service/
      application/
      domain/
      infrastructure/
      transport/
      observability/
    tests/
  conformance/phase2/
  deploy/
  fixtures/
```

Dependency：

```text
contracts <- client
contracts <- service
contracts + client + service <- conformance
```

Backend production只依赖contracts/client。Service不得依赖client；contracts不得
依赖HTTP、Dolt、SQLite、filesystem或业务module。Local adapter位于service，
Fake/Remote位于client。

Runtime固定为single ASGI process、single durable-root OS lock、in-process bounded
scheduler、stdlib `sqlite3` transaction adapter和WP2选择的Dolt streaming driver。

下表使用以下exact repo-relative path alias；`ALIAS/{a,b}`表示两个明确文件，不表示
glob或待定目录：

```text
RC  = vnext/repository_contracts/src/gateway_repository_contracts
CL  = vnext/repository_client/src/gateway_repository_client
RS  = vnext/repository_service/src/gateway_repository_service
RST = vnext/repository_service/tests
CF  = vnext/conformance/phase2
FX  = vnext/fixtures
```

## 3. Gates, evidence and rollback classes

### 3.1 Gate classes

| Gate | Owner | Activation |
| --- | --- | --- |
| `P2-PR-STATIC` | architecture/policy/closure | WP0-R2 |
| `P2-PR-CONTRACT` | public/persisted behavior and compatibility | first real WP1/WP2 cells |
| `P2-PR-RECOVERY` | effect/crash/restart/maintenance | first real WP2 kill cells |
| `P2-PHASE-EXIT-CONTAINER` | production topology and exact candidate | WP9-R4 |

Affected-scope router fail closed；unknown path扩大为全部相关gate。Required cell缺失、
skip、xfail、UNSUPPORTED或非PASSED使owning gate FAIL。Gate attempt immutable，
结果为PASS/FAIL/BLOCKED；BLOCKED只适用于semantic execution前外部环境不可用。

### 3.2 Evidence

每个attempt至少绑定：

```text
candidate commit
RuntimeBuildIdentity
EnvironmentFingerprint
contracts/client/service/conformance artifact digests
image/base/Dolt/lock digests
required-cell inventory and observations
fault receipts
cleanup result
gate result and supersedes attempt
```

Evidence不得包含secret、private dataset digest/path、raw row或internal command。
同一assertion失败的重跑不得覆盖第一次结果。

### 3.3 Rollback classes

| Class | Meaning |
| --- | --- |
| `CODE_ONLY` | 无durable/public activation；revert revision并重跑active gates |
| `RUN_SCOPED_RESET` | 仅conformance disposable data；可删除明确run identity的数据 |
| `BACKUP_OR_FORWARD_FIX` | persisted format/effect已发布；只允许已验证backup/restore或forward fix |
| `NEW_EXPLICIT_EFFECT` | public mutation已成功；代码rollback不撤销effect，只能发起新typed action |
| `IRREVERSIBLE_RESTORE` | GC/purge后只从既有verified backup恢复 |

## 4. F0 — Formal closure

Entry：Round 0–11、Consolidated Design Review及bounded Phase 3 consumer check已确认；
用户已明确授权formalize。

Scope：

- 发布本计划、Repository Service contract、ADR 0008和traceability YAML；
- 显式supersede旧FULL-only、CAS-only、EXACT-only、verification-mismatch quarantine及
  full-only measurement规则；
- 更新formal index、architecture、implementation stages、canonical storage、
  external effect、business lifecycle、fixture和measurement owners；
- 建立空blocking register和Phase 1 protected-identity check。

Exit：formal无相互冲突或UNRESOLVED；141个ACCEPTED decision都有traceability；
7个SUPERSEDED decision保留历史且不被实现；relative link/diff/owner/closure checks
通过。F0不修改production code、lock、fixture、vector、golden或image。

## 5. WP0 — Delivery skeleton and gates

| R | Goal/scope | Prerequisite and delta | Exact files/modules | Fixtures/tests | Gate/evidence | Rollback, exit and forbidden |
| --- | --- | --- | --- | --- | --- | --- |
| WP0-R1 | 建立三个distribution workspace、独立lock和import boundary | F0 PASS；无public API/durable schema | `vnext/repository_contracts/{pyproject.toml,uv.lock,src/gateway_repository_contracts/__init__.py}`；`vnext/repository_client/{pyproject.toml,uv.lock,src/gateway_repository_client/__init__.py}`；`vnext/repository_service/{pyproject.toml,uv.lock}`；`vnext/repository-workspace.toml` | package/import/lock/offline-sync tests | Static package graph与lock evidence | `CODE_ONLY`；exit=三包离线可构建且backend不能import service；禁止DTO、route、storage feature |
| WP0-R2 | 建立affected-scope router和Static入口 | R1 PASS；新增gate CLI schema，无feature cell | `CF/{router.py,gate.py,affected-scope-v1.yaml}`、`CF/tests/test_router.py` | unknown path、rename/delete、formal/lock/deploy scope negatives | 激活`P2-PR-STATIC`；immutable command/result | `CODE_ONLY`；exit=fail-closed routing；禁止空Contract/Recovery PASS、CI-provider framework |
| WP0-R3 | 建立attempt/closure/traceability/Phase1保护lint | R2 PASS；实现gate-attempt/closure manifest schema | `CF/schemas/{gate-attempt-v1.json,closure-v1.json}`、`CF/{closure.py,phase1_protection.py}`、`CF/tests/test_closure.py` | missing owner/cell/blocker、mutated Phase1 identity negatives | Static PASS；closure lint evidence | `CODE_ONLY`；exit=offline deterministic且gate前后tracked tree不变；禁止重签Phase1或创建runtime gate |

## 6. WP1 — Public contracts, client and service shell

| R | Goal/scope | Prerequisite and delta | Exact files/modules | Fixtures/tests | Gate/evidence | Rollback, exit and forbidden |
| --- | --- | --- | --- | --- | --- | --- |
| WP1-R1 | 公共ID、enum、problem、wire version和stream envelope | WP0 PASS；只加入跨能力基础schema | `RC/{identities.py,enums.py,problem.py,wire.py,stream.py,schemas/}` | round-trip、unknown field/code、opaque identity、schema snapshot | Static；contract assets未激活route | `CODE_ONLY`；exit=closed schema离线验证；禁止repository DTO/provider/business type |
| WP1-R2 | Repository Port、Fake/Remote transport基础和service composition root | R1 PASS；无repository feature route | `CL/{port.py,fake.py,remote.py,transport.py}`；`RS/{application/runtime.py,transport/app.py,transport/problems.py}` | Fake/Remote codec、transport failure、dependency direction | Static；Contract只测transport primitive | `CODE_ONLY`；exit=client/service不反向依赖；禁止stub endpoint、storage |
| WP1-R3 | Auth、live/ready、capabilities/limits端到端 | R2 PASS；激活service-level public API | `RC/service.py`；`CL/capabilities.py`；`RS/{transport/auth.py,transport/health.py,application/capabilities.py,settings.py}` | OpenAPI snapshot、401/403、redaction、Fake/Local/Remote canonical observation | 激活service-level Contract cells | `CODE_ONLY`；exit=surface原子advertise；禁止RepositoryId/Dolt/storage和production TLS ownership |

## 7. WP2 — Dolt, SQLite and filesystem feasibility

| R | Goal/scope | Prerequisite and delta | Exact files/modules | Fixtures/tests | Gate/evidence | Rollback, exit and forbidden |
| --- | --- | --- | --- | --- | --- | --- |
| WP2-R1 | 固定image/Dolt identity、POSIX lock/fsync/rename、SQLite WAL/backup | WP0 PASS，可与WP1并行；无public/schema publication | `RS/infrastructure/probes/{identity.py,filesystem.py,sqlite.py}`；`RST/probes/{test_identity.py,test_filesystem.py,test_sqlite.py}` | temp root lock race、file/dir fsync、atomic rename、WAL transaction/backup | Static + provider Contract/Recovery probe | `RUN_SCOPED_RESET`；exit=target linux/amd64 volume GO；禁止accepted layout/public API |
| WP2-R2 | canonical replay、commit/ref/marker真实probe | R1 PASS；使用owner artifact fixture，无public import | `RS/infrastructure/probes/dolt_replay.py`、`FX/repository-import/v1/{manifest.json,replay.sql}`、`RST/probes/test_dolt_replay.py` | Dolt 2.1.11`sql -f`、type round-trip、closed grammar negative、commit/ref marker | Contract provider evidence | `RUN_SCOPED_RESET`；exit=CANONICAL_SQL_REPLAY GO；禁止arbitrary SQL/provider switch/性能收益 |
| WP2-R3 | repository-scoped sql-server、driver候选、pinned stream/cancel及owner exclusion | R2 PASS；选择driver但不公开read | `RS/infrastructure/probes/{dolt_runtime.py,driver_matrix.py}`、`RST/probes/test_dolt_runtime.py` | CLI/server exclusion、multi-repository bounded runtime、stream/cancel/type | Contract evidence及driver decision record | `RUN_SCOPED_RESET`；exit=唯一driver/ownership route；禁止node-wide all-repo server或per-repo permanent process |
| WP2-R4 | kill/restart closure和upgrade rerun入口 | R3 PASS；冻结feasibility manifest | `RS/infrastructure/probes/restart.py`、`CF/provider-compatibility-v1.yaml`、`RST/probes/test_restart.py` | service/Dolt kill、lock loss、restart、future identity mismatch | Contract+Recovery PASS；stop/go evidence | `RUN_SCOPED_RESET`；exit=WP3 preflight GO；禁止删除长期upgrade probe或建通用certification framework |

## 8. WP3 — Repository durable foundation

| R | Goal/scope | Prerequisite and delta | Exact files/modules | Fixtures/tests | Gate/evidence | Rollback, exit and forbidden |
| --- | --- | --- | --- | --- | --- | --- |
| WP3-R1 | durable-root lock、ServiceEpoch、server-derived layout/path resolver | WP1+WP2 PASS；storage layout v1首次落地，无route | `RS/infrastructure/storage/{root.py,layout.py,identity.py}` | duplicate owner、path concealment、future/unknown format | Static+Recovery | `RUN_SCOPED_RESET`；exit=exclusive root/identity durable；禁止caller path和feature API |
| WP3-R2 | global registry、per-repository control schema、ACL和accounting transaction adapter | R1 PASS；registry/control schema v1 | `RS/infrastructure/{registry/schema.py,registry/store.py,control/schema.py,control/store.py}`、`RS/domain/policy.py` | transaction/crash、future schema refusal、ACL generation/accounting | Static+Recovery persisted-state evidence | `BACKUP_OR_FORWARD_FIX`；exit=authority无重叠；禁止public create、ordinary op global locator、ORM |
| WP3-R3 | deterministic aggregate staging、Dolt initial state、atomic publication和formal-path reopen | R2 PASS；provision primitive完成，仍无route | `RS/infrastructure/storage/provision.py`、`RS/infrastructure/dolt/bootstrap.py`、`RST/storage/test_publication.py` | fsync/rename/crash、identity mismatch、orphan no-auto-adopt | Recovery PASS | `BACKUP_OR_FORWARD_FIX`或run-scoped reset；exit=WP4可消费primitive；禁止同步/无journal Create |

## 9. WP4 — Operation, create, policy and artifact

| R | Goal/scope | Prerequisite and delta | Exact files/modules | Fixtures/tests | Gate/evidence | Rollback, exit and forbidden |
| --- | --- | --- | --- | --- | --- | --- |
| WP4-R1 | RepositoryOperation、FailureDescriptor、idempotency、global create journal和GetOperation representation | WP3 PASS；operation/control DTO持久化，不激活public route | `RC/operation.py`；`RS/{domain/operation.py,infrastructure/registry/create_journal.py,application/get_operation.py}` | legal state/effect combinations、same/different digest、compaction shape | Static+Contract internal | `BACKUP_OR_FORWARD_FIX`；exit=monotonic schema；禁止generic job runtime和store mutation |
| WP4-R2 | Create executor、claim/lease/fencing、FaultController和staged-publication reconciler | R1 PASS；无public activation | `RS/{application/create_executor.py,application/reconcile.py,domain/lease.py,infrastructure/faults.py}` | accept/effect/publish/verify fault points、old executor fencing | Recovery internal cells | `BACKUP_OR_FORWARD_FIX`；exit=real Create effect可恢复；禁止dummy effect和Current/Versioned write |
| WP4-R3 | 原子激活Create/GetRepository/GetOperation和Get/UpdateRepositoryPolicy | R2 PASS；route/SDK/auth/cells一起激活 | `RC/{repository.py,policy.py}`；`CL/repository.py`；`RS/{application/repository.py,transport/repositories.py}` | Fake/Local/Remote、401/403/404、policy CAS/idempotency、restart/quarantine | Contract+Recovery PASS | `NEW_EXPLICIT_EFFECT`；exit=public lifecycle闭合；禁止global ordinary-op index、business owner推断 |
| WP4-R4 | repository-bound upload/download和staged publication | R3 PASS；ArtifactRef/upload schema v1激活 | `RC/artifact.py`；`CL/artifact.py`；`RS/{application/artifacts.py,infrastructure/artifacts/store.py,transport/artifacts.py}` | one-shot close/digest/response loss、auth、limits、traversal/bomb、cleanup | Contract+Recovery PASS | `BACKUP_OR_FORWARD_FIX`；已发布artifact按retention；exit=WP5/WP7 input ready；禁止URL/path/presigned/multipart |

## 10. WP5 — CurrentTableStore

| R | Goal/scope | Prerequisite and delta | Exact files/modules | Fixtures/tests | Gate/evidence | Rollback, exit and forbidden |
| --- | --- | --- | --- | --- | --- | --- |
| WP5-R1 | lazy Current SQLite materialization、identity/schema、catalog/table generation和transaction adapter | WP4 PASS；Current schema v1，无public mutation | `RS/infrastructure/current/{schema.py,store.py,transactions.py}`、`RS/domain/current.py` | first-file crash、identity mismatch、WAL/backup、future schema | Static+Recovery | `BACKUP_OR_FORWARD_FIX`；exit=empty Current可重开；禁止Dolt/ref/route |
| WP5-R2 | Create/Drop、GetCurrentCatalog/GetCurrentTable与async operation/concurrency/verification | R1 PASS；原子激活table lifecycle | `RC/current.py`；`CL/current.py`；`RS/{application/current_tables.py,transport/current.py}` | CHECK/LWW、NONE/STRUCTURAL/FULL、idempotency、generation、Local/Remote | Contract+Recovery PASS | `NEW_EXPLICIT_EFFECT`；exit=table lifecycle闭合；禁止row partial、cross-table transaction |
| WP5-R3 | Sync ApplyCurrentTableMutations和generation-pinned stream/filter/order/cursor | R2 PASS；激活bounded sync/stream | `RS/{application/current_mutations.py,application/current_reads.py,infrastructure/current/query.py,transport/current_stream.py}` | atomic batch variants、4MiB/1000/100000 limits、response loss、stale generation、backpressure/cancel | Contract+Recovery PASS | `NEW_EXPLICIT_EFFECT`；exit=data/generation/idempotency同transaction；禁止BEST_EFFORT、SQL、secondary index |
| WP5-R4 | Arrow bulk Replace/SubmitBatch、Export、三档verification和control/current reconcile | R3 PASS；完整Current surface | `RS/{application/current_bulk.py,infrastructure/current/bulk.py,infrastructure/current/export.py}` | Arrow/Parquet integrity、bounded buffers、all crash points、Fake/Local/Remote matrix | Contract+Recovery PASS + measurement spans | `BACKUP_OR_FORWARD_FIX/NEW_EXPLICIT_EFFECT`；exit=Current complete；禁止to_pylist、hidden size threshold、Dolt semantics |

## 11. WP6 — Versioned read and runtime

| R | Goal/scope | Prerequisite and delta | Exact files/modules | Fixtures/tests | Gate/evidence | Rollback, exit and forbidden |
| --- | --- | --- | --- | --- | --- | --- |
| WP6-R1 | DoltRuntimeCoordinator、ResolveRef、GetCommit、GetCatalog和runtime pin/eviction | WP4 PASS，可与WP5并行；激活metadata read | `RC/versioned.py`；`CL/versioned.py`；`RS/{application/versioned_reads.py,infrastructure/dolt/runtime.py,transport/versioned.py}` | CLI/server exclusion、bounded slots、EXACT/LATEST resolve、eviction pins | Contract PASS | `CODE_ONLY` for cache；exit=metadata Local/Remote；禁止write/import |
| WP6-R2 | StreamTableRows、filter/order/cursor和immutable pin | R1 PASS；framed Arrow schema激活 | `RS/{application/versioned_stream.py,infrastructure/dolt/query.py,transport/versioned_stream.py}` | exact/latest snapshot race、cursor binding、integrity、backpressure/cancel | Contract+Recovery process cells | `CODE_ONLY`；exit=pinned stream闭合；禁止business comparison和provider collation leakage |
| WP6-R3 | ExportTable和DiffRefs显式Arrow/Parquet路径 | R2 PASS；artifact result/raw diff schema激活 | `RS/{application/versioned_export.py,application/versioned_diff.py,infrastructure/dolt/diff.py}` | Parquet publish/expiry、COMPLETE/UNSUPPORTED no partial、fallback read | Contract+Recovery artifact cells | `BACKUP_OR_FORWARD_FIX` for published artifact；exit=read data plane complete；禁止ComparisonFacts |
| WP6-R4 | Driver/process restart、cancel/backpressure、artifact cleanup和read closure | R3 PASS；无新capability | `RST/versioned/test_read_recovery.py`、`CF/cells/versioned-read-v1.yaml` | service/Dolt kill、long read/write concurrency、cleanup、Local/Remote canonical observations | Contract+Recovery PASS | `CODE_ONLY`；exit=WP7 read prerequisite；禁止public write或provider optimization claim |

## 12. WP7 — Versioned write, ref and verification

| R | Goal/scope | Prerequisite and delta | Exact files/modules | Fixtures/tests | Gate/evidence | Rollback, exit and forbidden |
| --- | --- | --- | --- | --- | --- | --- |
| WP7-R1 | Mutable/immutable/protected ref lifecycle、checked/LWW、tombstone和ref verification | WP5+WP6 PASS；激活ref actions | `RC/refs.py`；`CL/refs.py`；`RS/{application/refs.py,infrastructure/dolt/refs.py}` | name grammar、CAS stale、LWW、immutable tombstone、protected negatives、response loss | Contract+Recovery PASS | `NEW_EXPLICIT_EFFECT`；exit=ref closed semantics；禁止force protected/internal mutation |
| WP7-R2 | 非公开SubmitImport executor、canonical replay、private operation ref、commit marker和attribution | R1 PASS；import schema/provider internal | `RS/{application/import_executor.py,infrastructure/dolt/importer.py,infrastructure/dolt/evidence.py}` | owner artifact fixture、grammar/security、base parent、effect crash matrix | Contract+Recovery internal | `BACKUP_OR_FORWARD_FIX`；exit=APPLIED可唯一归因；禁止route、raw user SQL、blind executor switch |
| WP7-R3 | 公开SubmitImport target publication、NONE/STRUCTURAL/FULL和完整reconciliation | R2 PASS；route/SDK/auth/cells原子激活 | `RC/importing.py`；`CL/importing.py`；`RS/{application/imports.py,application/verification.py,transport/imports.py}` | CHECK/LWW、three levels、mismatch FAILED+APPLIED、UNKNOWN、all crash points、idempotency | Contract+Recovery PASS | `NEW_EXPLICIT_EFFECT/BACKUP_OR_FORWARD_FIX`；exit=write closed；禁止FULL hidden default、auto rollback/replay/quarantine on ordinary mismatch |
| WP7-R4 | VerifyCommit、GetTableInventory、write conformance和Phase3 consumer-ready checkpoint | R3 PASS；最后public read-only actions | `RC/{verification.py,inventory.py}`；`CL/{verification.py,inventory.py}`；`RS/application/{verify_commit.py,inventory.py}`；`RS/transport/{verification.py,inventory.py}`；`CF/cells/phase3-consumer-v1.yaml` | upload→Submit→poll→EXACT readback、post-verify no retroactive mutation、same-name cross-store inventory、Fake/Local/Remote | Contract+Recovery PASS；consumer-ready evidence | `CODE_ONLY` for read action；exit=Phase3 detailed design handoff；禁止business T3/dual-write/workflow |

## 13. WP8 — Retention and maintenance

| R | Goal/scope | Prerequisite and delta | Exact files/modules | Fixtures/tests | Gate/evidence | Rollback, exit and forbidden |
| --- | --- | --- | --- | --- | --- | --- |
| WP8-R1 | Retention roots、operation/idempotency compaction、artifact expiry、cleanup/quarantine | WP7 consumer-ready及store recovery PASS；retention schema v1 | `RS/{application/retention.py,infrastructure/control/compaction.py,infrastructure/artifacts/gc.py}` | 30d/24h/1h-30d classes、permanent tombstone、UNKNOWN pin、privacy | Contract+Recovery PASS | `BACKUP_OR_FORWARD_FIX`；exit=no authority loss；禁止caller shortening recovery evidence |
| WP8-R2 | Plan/ExecuteGarbageCollection、root epoch/pins、maintenance barrier和checkpoint | R1 PASS；GC plan schema/action激活 | contracts/client/service`gc.py` | stale plan、active pin、interrupt/resume、exact candidates、auth reason | Contract+Recovery PASS | `IRREVERSIBLE_RESTORE`；exit=quiescent GC closure；禁止direct/cron GC和partial stale-plan execute |
| WP8-R3 | Quiescent backup/restore、新incarnation和RESTORED_RESTRICTED activation | R2 PASS；backup manifest/restore/policy replace actions | matching`backup.py`、`restore.py` modules | manifested aggregate、corrupt/missing part、new incarnation、old caller rejection、ACL replacement | Contract+Recovery PASS | `BACKUP_OR_FORWARD_FIX`；successful restore不可由old image撤销；exit=restore drill PASS；禁止partial restore/automatic ACL activation |
| WP8-R4 | Plan/ExecuteDelete、tombstone、trash/purge及operator repair | R3 PASS；destructive/repair actions | matching`delete.py`、`repair.py` modules | exact plan/reason/current auth、crash checkpoints、target-only failure、permanent tombstone | Contract+Recovery PASS | `IRREVERSIBLE_RESTORE`；exit=all maintenance complete；禁止rollback fiction、service cron、multi-node writer |

## 14. WP9 — Production hardening and exact exit

| R | Goal/scope | Prerequisite and delta | Exact files/modules | Fixtures/tests | Gate/evidence | Rollback, exit and forbidden |
| --- | --- | --- | --- | --- | --- | --- |
| WP9-R1 | Telemetry、typed audit、thin resource snapshot、readiness/degradation、scheduler和build/environment identity | WP8 PASS；无product capability | `RS/observability/{logs.py,metrics.py,tracing.py,audit.py,identity.py}`、`RS/application/resource_usage.py` | redaction、low-cardinality、collector failure、incremental reconcile fairness、shutdown | Static+Contract+Recovery PASS | `CODE_ONLY`；exit=operational signals closed；禁止audit DB/query、timeseries、full scan usage |
| WP9-R2 | Production image、OS hardening、TLS ingress、bearer rotation和volume topology | R1 PASS；deployment schema | `repository_service/Dockerfile`；`vnext/deploy/{compose.phase2.yaml,phase-2-image-pins.env,tls/,env/}` | non-root/read-only/drop caps/no-new-privileges/no socket/egress、TLS CA/hostname/time/plaintext、volume owner | pre-exit Container topology cells | `BACKUP_OR_FORWARD_FIX` for deployment/storage；exit=linux/amd64 production topology；禁止service TLS key lifecycle和extra platform claim |
| WP9-R3 | Compatibility snapshots、auth/requirement coverage、gate runners、capacity、runbook、cleanup proof和Phase1 adapter | R2 PASS；freeze candidate mechanisms | `CF/{required-cells-v1.yaml,authorization-v1.yaml,exit.py}`、`CF/snapshots/{openapi-v1.json,wire-v1.json}`、`docs/backend-vnext/runbooks/repository-service.md` | N/N-1、future state refusal、all route auth、capacity characterization、Phase1 protected comparison | all PR gates PASS；candidate-ready evidence | `CODE_ONLY/BACKUP_OR_FORWARD_FIX`；exit=blocking register empty；禁止numeric target claim和new product capability |
| WP9-R4 | Source-frozen exact candidate build、full gates和sign-off | R3 PASS；clean worktree提名唯一commit；本R禁止source mutation | generated immutable attempts、OCI/wheel manifests、sign-off bundle（不修改tracked source） | 全部required cells、production Remote TLS、persistent restart、cleanup、full Phase1 correctness/native | `P2-PHASE-EXIT-CONTAINER` PASS | 失败不得改evidence；assertion修复必须新commit并全重跑；exit=sign-off；禁止跨commit拼接、旧evidence复用、source/config/lock edit |

## 15. Parallelism and merge ownership

只允许两处最多两条feature track并行：

```text
WP1 || WP2
WP5 || WP6
```

Contracts、registry/control schema、journal、gate/evidence schema和shared fixtures由单一
merge owner串行合入。WP2只能消费WP1已稳定基础contract，不能在provider probe中
定义public DTO。WP5/WP6共享logical types/read primitives时由contracts owner先合入，
两线不得复制。

WP7 consumer-ready PASS后可以启动Phase 3详细交互设计并与WP8/WP9并行；Phase 3
不得静默修改已冻结Phase 2 contract。Phase 3 production implementation以Phase 2
exact-commit exit PASS为entry。

## 16. Requirement traceability and blocking register

Machine-readable authority是
[phase-2-requirement-traceability.yaml](phase-2-requirement-traceability.yaml)。
它必须覆盖全部141个ACCEPTED decision，并为每个requirement family固定formal owner、
WP/R、gate和evidence。7个SUPERSEDED decision只保留在temporary ledger和formal
supersession说明中，不映射为implementation requirement。

F0结束时blocking register：

| ID | Item | Owner | Status |
| --- | --- | --- | --- |
| F0-B1 | Round 0–11、CDR、consumer check、formalization authorization | User/design governance | CLOSED |
| F0-B2 | FULL/CAS/EXACT/verification mismatch/measurement formal supersession | Contract owners | CLOSED |
| F0-B3 | Requirement traceability complete | Phase 2 plan | CLOSED |
| F0-B4 | Relative links、owner、decision、Phase1 protection和exit checks | F0 validation | CLOSED — [validation PASS](phase-2-f0-validation-report.md) |

Non-blocking deferred：

- legacy repository migration/cutover；
- second provider/object storage/resumable transfer；
- multi-node/shared writer和repository sharding control plane；
- additional production platform；
- hard untrusted-tenant same-root isolation；
- service-owned durable audit query/delivery；
- secondary index/native loader和measurement-driven optimization；
- product-specific RPO/RTO/SLO。

## 17. Exact-commit Phase exit

WP9-R4严格执行：

1. 验证F0、WP0–WP9-R3、blocking和traceability closure。
2. 在clean worktree提名唯一candidate commit。
3. 只从该commit构建contracts/client/service/conformance wheels和所有images并记录
   digest。
4. 在同commit运行全部Phase 2 Static/Contract/Recovery、完整Phase 1 correctness/
   native及production TLS/container exit。
5. 验证required-cell coverage、fault receipts、cleanup、RuntimeBuildIdentity、
   EnvironmentFingerprint、locks和image bundle。
6. 只聚合同一candidate closure的PASS attempts。
7. Assertion failure产生新commit；任何tracked code/config/lock变化无条件重新运行
   全部exit gates。
8. 最终immutable sign-off后才声明Phase 2完成。

Container exit使用独立conformance-client container，经production Remote SDK和TLS
ingress访问service image。Client不挂载durable root、不加入private service network、
不调用private endpoint。

## 18. Completion definition

F0完成只表示具备开始WP0的设计条件，不表示Phase 2实现完成。Phase 2只有在37个
revision按依赖完成、blocking register为空、同一clean exact candidate通过所有gate
并形成immutable sign-off后完成。

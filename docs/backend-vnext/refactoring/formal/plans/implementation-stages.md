# Backend vNext Refactoring Implementation Stages

状态：正式设计基线（Accepted Baseline）

本文把 [整体架构总纲](../architecture/architecture-and-refactoring-plan.md) 转换为可执行的重构阶段。阶段编号表示主要依赖顺序，不表示必须完成整个水平层后才能继续；每一阶段只建设下一条业务纵切所需的最小能力，并保持可运行、可验证和可回退。

当前状态：Phase 2简化设计、D01 Phase 0–1同原则简化设计、DX cross-phase
interface reconciliation与S02联合代码清理均已闭合；P2-R1 v8 formal 已通过。
P2-R6-S11 `phase_2_complete: yes`。当前下一入口为 Phase 3 full design，见
[P3 Active Context Index](p3-active-context-index.md) 与
[P2 External Interface Handoff](p2-external-interface-handoff.md)。
P2-R1 默认 provider 为Candidate A offline CLI，Candidate B保留但默认禁用。该顺序由
[ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)
和[ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)共同约束；Phase 0–9的安全、
恢复、证据与测试强度统一遵守
[Proportional Assurance and Risk-Based Verification Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)。

## 1. 实施原则

### 1.1 从头实现的含义

“从头重构”指新代码不继承旧模块边界和内部 DTO，不代表重新猜测业务语义：

- 旧代码只作为业务行为、边界 case 和人工体验的发现 oracle；不作为 vNext 内部结构或性能 oracle。
- 新代码不得依赖旧业务模块，也不在旧实现上包一层 adapter 作为正式能力。
- 稳定的业务结果、digest、artifact 和状态变化必须由 fixture、contract 和验收用例固定。
- 新旧实现可以在测试或 shadow 阶段离线对照，但不共享可变业务状态。

### 1.2 纵向交付优先

禁止按以下方式长期水平推进：

```text
先写完全部 core
  -> 再写完全部 domain
  -> 再写完全部 capabilities
  -> 最后一次性接 API
```

推荐方式：

```text
最小基础
  -> upload preview vertical slice
  -> submit vertical slice
  -> review vertical slice
  -> archive vertical slice
  -> history compare vertical slice
```

每个纵切都应包含 contract、domain/application、capability、operation、adapter、API 和测试，形成可运行闭环。

### 1.3 正确性先于性能

- 第一版 capability 默认串行、确定性执行。
- 初始 production route 使用满足稳定 contract 和必要 golden 的 Rust provider；
  Python reference 只用于小规模测试和诊断，不是自动 fallback。
- 性能结果只统计 validation passed 的运行。
- 性能记录说明 dataset/version、环境和 raw results，不建立 formal baseline lifecycle
  或 capture gate。
- 优化不能改变 canonical scalar、排序、digest、records 或 diagnostics 语义。
- Backend vNext是偏业务系统，不追求极限性能；Rust使用必须遵守 [Rust Safety and Performance Policy](../policies/rust-safety-and-performance-policy.md)，第一方默认零unsafe、stable toolchain、无panic捷径，且没有证据时优先简单Safe Rust。

### 1.4 阶段门禁

每个 Phase 必须满足退出条件后，才能把下一 Phase 的产物接入正式主路径。允许提前开展验证性 spike，但 spike 代码不能绕过 contract 和门禁直接成为正式实现。

### 1.5 风险分级先于机制

每个Phase、WP或纵切在设计入口轻量登记authoritative/irreversible事实、recoverable durable
状态、derived/temporary状态、外部信任边界、最高风险等级、必要语义屏障和明确非目标。
新增安全主体/UID、自定义IPC、持久evidence状态机、sidecar/quarantine或syscall-window证明墙
属于架构升级，必须先有具体威胁/损失/consumer依据和ADR；不能由普通Finding逐轮累加形成。

## 2. 阶段总览

```text
Phase 0  Baseline and Oracle
    |
Phase 1  Executable Contracts and Walking Skeleton
    |
Phase 2  Repository Service Foundation
    |
Phase 3  Capability Foundation
    |
Phase 4  Durable Operation Runtime
    |
Phase 5  Business Vertical Slices
    |
Phase 6  Rust Coverage Expansion and Compute Optimization
    |
Phase 7  Concurrency, Cache and Performance
    |
Phase 8  Shadow Traffic and Cutover
    |
Phase 9  Cleanup and Production Hardening
```

Phase 3 production implementation必须等待修订后的Phase 2最小consumer纵切通过。
Phase 4及后续同样必须共同服务于Phase 5纵切，不得以“并行”为由静默修改已激活
Phase 2 contract或独立扩张范围。

## 3. Phase 0：Baseline and Oracle

### 目标

固定新实现必须保持或有意改变的业务语义、数据契约、必要 golden 和简明
performance measurement guidance。同时识别可派生状态、重复事实、无真实调用方
功能和无证据优化，形成明确的首版简化范围。

Normative outputs 由 [Business Lifecycle](../contracts/business-lifecycle-and-state.md)、[External Effect](../contracts/external-effect-and-recovery.md)、[Canonical Encoding](../contracts/shared-canonical-encoding.md)、[Fixture Conformance](../contracts/fixture-oracle-and-conformance.md)、[Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)和 [Performance Measurement](../contracts/performance-measurement-and-baseline.md) contracts 分别拥有。

### 主要工作

- 列出正式业务旅程：upload、preview、submit、review、archive、next baseline、history compare。
- 固定 Workspace、UploadRevision、PreviewResult、SubmitAttempt、Submission Review、BaselineNode/Head、ArchivePlan/Execution/Result 的 owner、状态、generation gate、权限和失败语义。
- 固定 SourcePackage raw authority、canonical Dolt storage、storage/comparison projection、SnapshotTableArtifact retention 和 Repository evidence 边界。
- 保留既有128个canonical cases和一个必要的mixed-scalar业务golden，由测试直接消费，
  不建立generic scenario manifest、runner/harness/profile matrix或RunEvidence。
- 固定JCS、typed scalar、identifier、row/collection framing、digest与Python/Rust
  canonical cases；Repository不消费vector corpus。
- 只为correctness-passed production path记录dataset/version、环境说明与raw results；
  不建立formal baseline lifecycle、environment identity或first-capture gate。
- 将 legacy 数据迁移/旧 Dolt compatibility 保留为独立 cutover gate，本阶段不决定策略。
- 记录当前人工验收路径和已知旧 bug，不把旧 bug 自动作为新 contract。
- 按 `KEEP / SIMPLIFY / DEFER / REMOVE` 审查现有状态、流程、provider、cache、compat 和前端操作；简化项必须说明被保留的业务事实与可恢复路径。
- 优先删除可由事实推导的持久状态、重复上传/重复校验、无调用方公共 API、预优化流程和跨模块重复结果。

### 交付物

- Correctness golden contract、既有canonical corpus与一个必要业务golden。
- Shared canonical encoding contract。
- Business lifecycle、external-effect/recovery、canonical storage 与 artifact retention contracts。
- 简明performance measurement guidance。
- Flow journey/oracle audit 与 intentional-change register。
- Legacy behavior audit 和 intentional change 清单。
- First-version simplification register，记录 `KEEP / SIMPLIFY / DEFER / REMOVE`、owner、理由、风险和恢复方式。
- 第一版明确功能范围及被推迟功能的重新进入条件。

### 退出条件

- canonical cases可由Python/Rust在隔离环境逐bytes重复验证。
- 关键输出可做结构化比较，不依赖人工查看日志。
- 每个旧新差异可归类为 old bug、new bug 或 intentional change。
- 旧 Dolt migration/compatibility 已被明确隔离为单独 cutover gate，未被默认兼容或迁移。
- 现有主要功能、状态和优化均已完成简化分类，不存在“因为旧系统已有”而默认进入第一版的范围。
- 已确认第一版业务旅程可以在不依赖被删除/推迟功能的情况下闭环，并保留必要的可靠性和审计能力。

### 本阶段不做

- 不修改正式流量。
- 不开始大规模目录搬迁。
- 不根据单次 benchmark 决定 Rust 或并行策略。
- 不要求尚不存在的 production path 产生 numeric baseline，也不建立 legacy-vs-vNext performance report。

## 4. Phase 1：Executable Contracts and Walking Skeleton

> 历史边界：本节以下记录2026-07-27原Phase 1 closure，便于解释已存在的代码与
> checkpoint；其中generic conformance、Repository vector consumer、RunEvidence、
> formal gate matrix、exact-commit identity和full semantic artifact reopen均不再是
> 现行要求。现行D01设计由[ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)、
> [Correctness Golden Contract](../contracts/fixture-oracle-and-conformance.md)、
> [Canonical Row Hash Boundary](../contracts/canonical-row-hash-compute-boundary.md)和
> [Rust Policy](../policies/rust-safety-and-performance-policy.md)拥有。代码清理须等DX
> 完成；不得以本历史节恢复已删除设计。

阶段状态：**Completed**（2026-07-27）。Phase 1 exit source commit
`7702d2127712193a8a88e66ba614dc073922ac15` 已在干净 exact commit 上通过
`PR-CORRECTNESS`、`PR-NATIVE` 与 `PHASE-EXIT-CONTAINER`；最终签署、immutable
identity 与九项退出条件核对见 tag `docs/p2-p3-cleanup-pre-20260817` 中的
`docs/backend-vnext/refactoring/temporary/phase-1/phase-1-closure-signoff.md`。

### 目标

把第一批Accepted语义变成language-neutral、可离线校验、可跨语言执行的contract，并通过一条可复用的真实data walking skeleton建立新代码隔离区。Phase 1固定最小边界，不提前实现完整业务流程、Repository transport、Operation runtime或通用框架。

Normative owner文档：

- [Shared Canonical Encoding](../contracts/shared-canonical-encoding.md) 与 [Canonical Encoding Normative Vector Schema](../contracts/canonical-encoding-normative-vector-schema.md)。
- [Fixture Oracle and Conformance](../contracts/fixture-oracle-and-conformance.md)。
- [Canonical Row Hash Compute Boundary](../contracts/canonical-row-hash-compute-boundary.md)。
- [Rust Safety and Performance Policy](../policies/rust-safety-and-performance-policy.md)。

WP0–WP2的package/crate拓扑、依赖接入时点、candidate-to-normative发布流程和可执行gate
以本节与 [DX Cross-Phase Interface Reconciliation](dx-cross-phase-interface-reconciliation.md)
为准；历史 Phase 1 实施计划见 tag `docs/p2-p3-cleanup-pre-20260817`。canonical byte/schema
语义仍以本节列出的owner contract为准。

### 主要工作

- 发布canonical encoding v1 static vectors：Python与Rust提供两份独立实现；Repository consumer直接发现并逐case消费同一vector root，但可复用Shared Kernel Python package，不复制第三套算法。
- 发布scenario manifest、golden envelope、runner/harness protocol/result/evidence schema v1；Phase 1使用Python in-process harness registry，runner固定lifecycle且唯一负责comparison/result。
- 建立唯一正式kernel `canonical_row_hashes_v1`：一个Arrow C Stream + JCS request/result bytes；覆盖全部canonical scalar kinds的Arrow mapping v1，拒绝complex/large/dictionary/extension types。
- Python facade只把`RecordBatch | Table | RecordBatchReader`包装为保留chunk的reader；禁止`to_pylist/to_pydict`、逐row/scalar FFI、任意Python generator和自动`combine_chunks()`。
- Rust core负责canonical row hashes/sort/table digest，native compute期间释放GIL；Python ArtifactStore负责Arrow IPC与generic `ArtifactRef`，并分离raw IPC hash和semantic content digest。
- 建立实际被walking skeleton使用的最小package/crate、architecture/import test和首个Linux x86_64 glibc release wheel/image路径；不预创建空目录树或未使用抽象。
- 将`unsafe_code=forbid`和stable-toolchain/production-no-panic policy提升到整个first-party Rust workspace；PyO3/Arrow只通过third-party safe API接入。
- 只发布一条真实walking-skeleton `data` scenario。Command/recovery shape与lifecycle使用schema/fake-harness contract tests，不伪造尚无owner/public entrypoint的业务scenario。

### 交付物

- Shared canonical encoding v1 vector closure、schema/validator和Python/Rust/Repository consumers。
- Scenario/golden/protocol/result/evidence schema与最小runner/harness skeleton。
- `canonical_row_hashes_v1` Python facade、Rust core/PyO3 adapter、Arrow mapping/failure envelope和ArtifactRef round-trip。
- Real data scenario及`reference | integration | provider-matrix` required profile evidence。
- Architecture/import tests、首个平台wheel/container evidence、component structural-performance evidence和清空的blocking decision register。
- Rust safety/performance policy的workspace lint、dependency inventory和release evidence。

### Gate classes

| Gate | 运行时机 | 失败效果 | Authority |
| --- | --- | --- | --- |
| `PR-CORRECTNESS` | 每个相关PR；离线、确定、无外部网络 | 禁止合入 | Schema/closure、vectors、runner contract、architecture、Python/Rust/Repository unit/conformance。 |
| `PR-NATIVE` | 每个相关PR；Linux x86_64 glibc | 禁止合入 | Release wheel import、Arrow C Stream/PyO3、GIL/failure、artifact round-trip。 |
| `PHASE-EXIT-CONTAINER` | Phase-exit candidate的exact commit | 禁止宣布Phase 1完成 | Pinned image、wheel-in-image、health/native smoke、Compose和immutable build identity/evidence。 |

外部registry/network故障可以在phase ledger记为`BLOCKED`，但不是runner第五种status，也不是pass。Phase exit只接受同一commit/toolchain/lock identity的完整证据；`Partially verified`不能宣布完成。

### Required scenario/profile matrix

| Material | Reference | Integration | Provider matrix | Process-crash |
| --- | --- | --- | --- | --- |
| Canonical encoding vectors | Python全量 | Repository consumer全量 | Python/Rust逐bytes全量 | 不适用 |
| Canonical row-hash data scenario | Python reference小场景全量 | Python facade→PyO3/Rust→IPC ArtifactRef/reopen | Python/Rust覆盖全部Arrow mapping cases | Phase 1不声明required |
| Manifest/golden conformance samples | Data/command/recovery valid+invalid schema fixtures | 不伪造业务integration | 不适用 | 只测protocol/schema，不冒充真实crash |
| Runner/harness self-tests | Fake owner固定lifecycle/result precedence | Real walking-skeleton harness | Support/observation comparison | Process-control protocol unit tests only |

只有canonical-row-hash `data` scenario进入正式scenario oracle root，其`required_profiles[]`固定为`integration | provider-matrix | reference`。Required cell未执行、缺case、返回`UNSUPPORTED`或非`PASSED`都使suite/phase gate失败。

### 验收矩阵

| Area | Required assertions | Gate/evidence |
| --- | --- | --- |
| Schema/YAML | JSON Schema 2020-12；strict JSON-compatible YAML；unknown/duplicate/alias/tag/multi-doc/non-JSON scalar fail closed；presentation不改semantic identity | `PR-CORRECTNESS` |
| Manifest identity/closure | ID/track/subject/path可逆；path escape/symlink/undeclared asset失败；size/raw/input/fixture digest及self-exclusion正确 | `PR-CORRECTNESS` |
| Golden | Manifest/envelope binding完全一致；kind决定inline/closure；owner schema validation、canonical exact compare和digest重算 | `PR-CORRECTNESS` |
| Vectors | Closure/case schema/ID/ordering/error registry有效；Python/Rust/Repository coverage set一致、zero skip；valid比完整bytes、invalid比stable code | `PR-CORRECTNESS` |
| Runner authority | Registry与fixed lifecycle；harness看不到golden且只返回actual；observation exact set；runner唯一compare | `PR-CORRECTNESS` |
| Result/cleanup | 四态result；`UNSUPPORTED`仅preflight；无automatic retry；cleanup泄漏覆盖final status但保留comparison outcome | `PR-CORRECTNESS` |
| Asset/security boundary | Harness只能用verified resolver读declared closure；host path、secret、stack和provider-private object不进入protocol/golden | `PR-CORRECTNESS` |
| Arrow mapping | 每个canonical scalar kind的positive/null/boundary case；24-bit integer、decimal/temporal/BIT/anomaly映射；unsupported physical type拒绝 | `PR-NATIVE` |
| Stream determinism | Empty/one/multi-batch；batch partition、input row/field order不改formal result；duplicate row hashes保留 | `PR-NATIVE` |
| FFI/materialization | One native call per stream；owned C Stream import/export；零Python row/list/dict materialization；无generator/combine-chunks慢路径 | `PR-NATIVE` + component evidence |
| GIL/failure | Compute/sort/digest期间其他Python thread可进展；request/version/schema/value/type/panic failure映射稳定、`effect=NONE` | `PR-NATIVE` |
| Rust safety | 所有first-party member继承`unsafe_code=forbid`且crate root防御性forbid；stable toolchain；production path无`unwrap/expect/panic/todo/unimplemented`；无local waiver | `PR-CORRECTNESS` + `PR-NATIVE` |
| Rust FFI/dependencies | PyO3/Arrow只用safe API；无手写C/PyCapsule/raw Arrow FFI；新增native/build/proc-macro dependency有lock、safe-boundary和回退review | `PR-NATIVE` + dependency evidence |
| Artifact | IPC write/reopen；size/raw hash/schema/sorted hashes/semantic digest全量复验；corrupt/truncated/mismatch拒绝 | `PR-NATIVE` |
| Identity separation | Provider/chunking可以产生不同IPC raw bytes，但formal semantic digest必须相同 | `PR-NATIVE` |
| Architecture/build | vNext不import legacy；Rust core不依赖PyO3/filesystem/ArtifactStore；adapter单向依赖core；locks/fmt/lint/type/unit/release wheel通过 | `PR-CORRECTNESS` + `PR-NATIVE` |
| Container | Pinned toolchain/base、release wheel in image、health/native smoke、Compose config和build identity | `PHASE-EXIT-CONTAINER` |
| Structural performance | 记录版本、规模/batches、GIL证据、Python materialization count、input/hash-sort/output IPC memory breakdown；不声明numeric收益 | `PR-NATIVE` artifact + phase ledger |
| Optimization restraint | Phase 1无nightly、unsafe、hand-written SIMD/intrinsics、custom allocator、unchecked/raw-memory path、unbounded parallelism或microbenchmark-only architecture | `PR-CORRECTNESS` + `PR-NATIVE` |
| Governance | Vector candidate人工byte review + 两个独立实现；普通CI不bless；owner/版本明确；blocking decisions清空 | Phase-exit review |

Property/fuzz tests补充static vectors，覆盖frame/ULEB128/scalar boundary/permutation；固定seed/budget可进入PR gate，长时间fuzz campaign不是每PR阻塞项。

### 退出条件

Phase 1只在以下条件全部满足时完成：

1. Exit commit的`PR-CORRECTNESS`与`PR-NATIVE`全部通过。
2. `PHASE-EXIT-CONTAINER`在同一commit/toolchain/lock identity通过并保存immutable evidence。
3. Required matrix全部`PASSED`，无required `UNSUPPORTED`、missing run或retry覆盖。
4. Python/Rust两份独立实现通过全部vectors，Repository直接通过同一root。
5. Walking-skeleton artifact可按ref恢复并重新验证raw/semantic identity。
6. 现有doubling/`to_pylist()` demo不再是public/formal path；若保留只能标注bootstrap evidence。
7. Blocking register为空；无`UNRESOLVED`、formal内部冲突或未分配owner。
8. 本阶段规则已按ownership写入formal；temporary讨论材料保留并标记Resolved。
9. Rust workspace、release wheel和container evidence全部满足cross-stage Rust safety/performance policy。

Phase exit不接受semantic waiver、`xfail`、advisory-only required lane、临时减少vector/profile coverage或以网络不可用代替通过。

### 本阶段不做

- 完整OS/architecture wheel matrix。
- 真实process-crash/takeover journey。
- Numeric throughput/latency baseline或Rust收益声明。
- Rayon/parallel、timeout/cancel、external sort、SIMD、Parquet、独立Rust worker/service。
- Nightly、first-party unsafe、手写intrinsic/custom allocator/raw-memory优化或任何临时safety waiver。
- Phase 2 Repository transport/Dolt integration、完整业务command/recovery流程。
- 通用workflow/DAG、schema registry/codegen、dynamic provider/plugin hierarchy、未使用目录树或无owner的`common/helpers/utils`。

## 5. Phase 2：Repository Service Foundation

### 目标

优先建立真正可运行、独立、通用、容器化的Repository Service，使业务系统不再
依赖Dolt CLI、SQLite文件或repository本地路径，并提供可做普通容量测量的真实
production environment。

完整实施顺序、revision、gate、evidence和rollback的现行摘要由
[P2 External Interface Handoff](p2-external-interface-handoff.md)
拥有；历史 Phase 2 实施计划见 tag `docs/p2-p3-cleanup-pre-20260817`。public/persisted语义由
[Repository Service Contract](../contracts/repository-service.md)拥有。Journal/
recovery与canonical import分别遵守
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)和
[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)。

### 2A：Contract 清理

- 保留`gateway-repository-contracts`、`gateway-repository-client`和
  `gateway-repository-service`三包单向依赖。
- 从wire移除Workspace、Submission、Preview、Archive、Baseline和History语义。
- 使用Pydantic DTO、普通UUID、bounded opaque token和简单error。
- 删除strict JSON/JCS、FailureDescriptor、custom stream、Current identity和
  handwritten schema snapshot。
- 删除Phase 2 router/closure/attempt/traceability体系。
- 外部contract不返回server path、run directory、provider command或本地Artifact
  `Path`。

### 2B：Durable foundation与lifecycle

- 固定single durable-root owner、Dolt、per-repository operation和临时artifact。
- 以真实Dolt和target filesystem验证initial commit、replay、marker、CAS、stream、
  atomic rename和增量存储。
- CreateRepository同步创建initial empty commit和main。
- UploadArtifact同步stream、增量校验size/SHA并atomic publish。
- SQLite control DB保存同步mutation最小幂等ledger与async import queue/result；不保存
  table data，也不占用未来Current component。
- 不实现create/upload Operation、ACL、policy、lease、fencing或ServiceEpoch。

### 2C：Versioned write与read

- Versioned import使用`manifest.json + replay.sql`固定package。
- `expected_commit_id`同时是新commit parent和main ref CAS预期。
- Operation只使用QUEUED/RUNNING/SUCCEEDED/FAILED。
- Caller选择NONE/STRUCTURAL/FULL_SCAN，默认STRUCTURAL；所有level强制package safety、
  marker、expected parent和main CAS，FULL_SCAN只做bounded full read/type/row-count检查，
  不做business digest rehash。
- Unknown type默认REJECT，caller可显式STRINGIFY为lossy Arrow large_string；commit CAS
  始终强制，不提供table/schema CAS或partial merge。
- 提供ResolveVersionedRef、commit-pinned catalog和raw Arrow IPC stream。
- 不提供standalone CAS、LATEST、diff/export/cursor或Current data plane。

### 交付物

- 三个Python distributions、Repository Service image和Remote client。
- 最小Versioned `/v1/` surface及FastAPI OpenAPI。
- 普通lint/type/unit、HTTP/Dolt integration和Backend consumer e2e。
- commit前中断、commit后response loss和manual recovery tests。
- 典型10–100 MB及接近200 MB package容量记录。
- 部署级global bearer、TLS入口和quiescent volume snapshot runbook。

### 退出条件

- 业务侧只使用RepositoryId/ref/commit/artifact/operation等public identity。
- upload → import → poll → resolve → catalog/stream真实纵切通过。
- CAS、幂等和matching commit recovery通过；矛盾状态显式人工恢复。
- 成功package被删除，RUNNING/manual-recovery package不被误删。
- Phase 0–1 canonical bytes、Python/Rust核心golden和Backend artifact主路径不变。
- 普通CI通过，不生成closure/evidence/exact-candidate材料。

### 本阶段不做

- Repository Service不解释SnapshotSummary、Comparison、Risk、业务hidden table或
  candidate/archive workflow。
- 不实现CurrentTableStore、server-owned store routing、cross-store consistency、
  arbitrary SQL/DDL或service-owned audit query。
- 不实现standalone ref CAS、public GC/backup/restore/delete/repair。
- 不实现multi-node shared writer、untrusted tenants共享root、legacy cutover、
  resumable multipart/object storage或额外production platform。

## 6. Phase 3：Capability Foundation

### 目标

建立可独立调用、独立测试、无环依赖的 capability 主链，并产出首个业务纵切需要的事实和 artifact。

Entry：Phase 2 `P2-R1`至`P2-R6`全部完成且最小Versioned fixture-consumer纵切通过。
P2实现期间不穿插Phase 3完整设计；P2-R5只实现contract-owned fixture consumer，不能
借此提前决定业务capability或Submit verification policy。P2-R6 exit后才开始Phase 3
完整设计。若consumer evidence需要改变Phase 2 public contract，必须显式reopen owning
contract或ADR。

Phase 3设计入口必须先按全局比例化保障policy登记每个capability的权威输出、可重建
projection/cache/artifact、外部输入边界和实际失败成本。默认不把同机可信模块/worker设为
攻击者；若需要不可信plugin/tenant、本地进程隔离或新的安全主体，先修订ADR再设计实现。

Storage/comparison projection、artifact retention、ordered identity和business
verification policy以
[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)
及[Repository Service Contract](../contracts/repository-service.md)为准。

### 实现顺序

```text
table_access + parser -> snapshot_materialization -> SnapshotTableArtifact
table_rules + SnapshotTableArtifact
  -> storage_projection -> RepositoryImportArtifact
  -> comparison_projection -> comparison
       -> risk_evaluation
       -> business_projection
       -> surface_assembly
       -> bundle_assembly
```

Repository import 在业务系统侧收敛为 Repository Client 调用和业务 readback validation，不重新拥有 Dolt lifecycle。

### 每个 capability 的固定步骤

1. 定义或收口 `contracts.py`，只固定当前consumer实际依赖的scalar、ordering、digest和
   Arrow/Parquet边界；未被消费的字段、version或digest不预建。
2. 实现只覆盖小规模语义和边界 case 的 Python reference oracle。
3. 只消费该capability已有consumer所需的golden/property fixtures；记录必要的component
   measurement和implementation route，不要求legacy对比、通用evidence closure或已不存在的
   numeric baseline。
4. 对满足 ADR 0001 门禁的稳定热点，直接实现 Rust production provider；其他能力使用 Python/Polars 验证语义。
5. 仅在consumer需要时实现artifact输入输出、retention/完整性和失败映射；不为每个
   capability复制通用closure、digest、journal或provider fallback。
6. 增加与风险和容量目标相称的kernel/end-to-end measurement与diagnostics；没有已接受
   性能目标时不把benchmark矩阵设为退出门。

### 重点调整

- 提取独立 storage/comparison projection，消除 snapshot 对 comparison digest 的反向依赖。
- 分离 storage projection 与 comparison projection；前者产出 CanonicalizationManifest/RepositoryImportArtifact，后者负责 schema alignment 与 compare records。
- Storage projection 直接执行 column policy、canonical key、ordered `no/gid` 与 row-integrity validation；Repository Service 不解释业务规则。
- 提取最小 `table_access` protocol，不把完整 Snapshot 泛化成通用表模型。
- 消费方只依赖 capability public contract，不 import 内部 `models.py`、planner 或 builder。
- 风险规则先保留 Python reference；大规模 row facts extraction 与规则决策分离。
- 第一批 Rust production 候选为 scalar/digest、storage/comparison projection、standard hash diff、records 和计算结果的 Arrow/Parquet materialization。
- `SnapshotTableArtifact` 只在 current Preview/active SubmitAttempt 期间 pin；Attempt 终态后可重算，不建设长期重复 full-row archive。
- Python reference 不是与 Rust 同等规模的 production provider；正式语义由 contract 和 golden fixtures 拥有。

### 交付物

- Capability contract、Python reference oracle 和按门禁选择的 production implementations。
- 首批 Rust core/PyO3 providers 及跨语言 differential tests。
- Capability-level unit、contract 和 benchmark tests。
- 当前consumer实际使用的Artifact schema和普通round-trip validation；没有artifact边界的
  capability不为形式统一创建artifact。
- 无环 capability dependency report。

### 退出条件

- 每个 capability 可脱离 API、application 和 Operation Runtime 单独调用。
- 相同输入、版本和policy产生稳定结果；digest只有在owner contract定义时才进入一致性断言。
- Rust production provider 与 Python reference 在 golden/property fixtures 上语义一致。
- Python/Rust直接消费既有canonical cases并逐字节一致；Repository不依赖该corpus。
- Capability 不包含 Workspace、Submission、Archive、History request 等 flow identity。
- 依赖图无环且无内部实现越界。

### 本阶段不做

- 不为每个 capability 同时维护 Python、Rust、Dolt native 多个同等权威的正式 provider。
- 不要求尚未满足 Rust 进入条件的 capability 为语言统一而使用 Rust。
- 不引入无 benchmark 依据的表级并行和 cache。

## 7. Phase 4：Durable Operation Runtime

### 目标

建立可持久化、可重试、可接管的最小执行运行时，为 submit、archive 和 history 等耗时流程提供可靠执行机制。

Operation 与业务 execution/effect evidence 的分界以 [External Effect and Recovery](../contracts/external-effect-and-recovery.md) 为准。

### 主要工作

- 持久化 operation/step store 和 optimistic version。
- 原子 claim、lease、heartbeat、timeout takeover。
- 稳定 `operation_kind + step_name -> JobDefinition handler` 注册。
- Step output 只保存稳定 DTO、business ID、artifact ref、repository operation ID 和 checkpoint。
- 大型 Comparison/Risk/Surface 结果必须通过 artifact/checkpoint 重载，不能依赖 Python 闭包。
- 实现retry、cancel、supersede、final failure和owner定义的READY条件，不引入通用
  evidence/closure状态空间。
- 建立 Repository remote operation 的 submit/poll/evidence checkpoint 模式，不占用线程阻塞等待。
- Takeover `RUNNING` step时先读取durable checkpoint并以既有Repository operation ID
  查询；SUCCEEDED进入T3，三种普通未发布stable failure允许abort，
  MANUAL_RECOVERY_REQUIRED保持occupancy并等待operator。连接失败或timeout只继续查询，
  不生成新key或blind replay。
- 第一版保持顺序 step；只预留固定 fan-out/fan-in contract。

### 交付物

- Durable Operation Runtime。
- JobDefinition registry。
- Worker entrypoint。
- Crash、lease、retry、duplicate delivery 和 cancellation tests。

### 退出条件

- 对具有外部effect或不可安全重算的step，终止worker后另一worker能从最小checkpoint继续、
  reconcile或给出明确attention；无外部effect且可重算的纯compute step允许幂等重算，不强制
  持久evidence。
- 已提交的 repository 写操作不会因业务 step 重试而重复提交。
- 不存在“保守重做整个 step”的 blind replay 路径。
- READY前owner contract要求的artifact存在且可读，READY后后台优化不改变正式结果；
  不建立跨所有artifact的通用closure协议。
- Operation Runtime 不依赖具体业务模型或 capability 实现。

### 本阶段不做

- 不实现任意 DAG、动态脚本工作流或跨服务分布式事务框架。
- 不把 capability 内部按表并行提升成 operation step，除非它需要独立恢复和业务可见进度。

## 8. Phase 5：Business Vertical Slices

### 目标

按业务价值和依赖顺序建立新的正式主路径。每个 Slice 通过后再进入下一 Slice，不等待所有功能一次完成。

所有 Slice 的对象、状态、占用、derived projection 与 freeze point 遵守 [Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)。

### Slice 5A：Upload Preview

```text
HTTP
  -> Workspace application use case
  -> source/snapshot
  -> comparison/risk
  -> surface/bundle
  -> consumer-required artifact retention
  -> preview response
```

重点验证 capability 组合、bundle contract 和同步/异步边界。该 Slice 不依赖 Repository 写路径，是首个端到端架构验证点。

Upload/Preview 产生 immutable UploadRevision、PreviewResult 与 full-row table facts；SnapshotTableArtifact 仅在未接受的 current Preview 或 active SubmitAttempt 期间持久 pin，T1 转移 pin responsibility，Attempt 终态释放。

退出条件：正式 preview bundle 可由新前端 loader 打开，golden comparison/risk/digest 一致，API 不内联 capability 算法。

### Slice 5B：Submit Acceptance and Finalize

```text
Workspace submit gate
  -> reject NO_CANONICAL_CHANGE before Attempt
  -> persist SubmitAttempt + Operation/outbox (T1)
  -> build/reuse one RepositoryImportArtifact
  -> Repository SubmitImport
  -> poll/checkpoint
  -> policy-matching import result + business-owned package/digest facts
  -> create Submission/finalize Workspace (T3)
```

重点验证跨服务幂等、事务边界、补偿和 worker takeover。

退出条件：重复请求、worker crash和Repository Service restart不产生重复
submission/ref/commit；Repository成功前不存在Submission；unknown effect不解锁或
blind replay。该slice correctness通过后可记录首份真实production-path容量结果，
但不创建formal baseline lifecycle或capture gate。

### Slice 5C：Review

实现直接approve、reject、withdraw和return；不建设单独start-review动作或中间审核
状态。领域状态变化归Submission/Workspace。若详细设计证明review必须独立移动或
回退Repository ref，再按ADR 0009 reopen condition增加standalone CAS。

退出条件：状态机、权限、幂等和 ref release conflict 全部由自动测试覆盖。

### Slice 5D：Archive

实现从approved Submission facts派生CandidateProjection、
confirmation/anomaly resolution、纯读PreviewArchivePlan与StartArchive execute
gate。Preview不持久化、不冻结；Start才重新校验并冻结ArchivePlan。使用immutable
BaselineNode + BaselineHead，不建设batch。若Archive需要把既有commit提升到main，
必须先以真实consumer重开standalone CAS设计；不能假设V1已经提供。

退出条件：并发 archive、base main conflict、重复执行和部分失败有确定结果，业务与 repository operation 可关联审计。

### Slice 5E：History Compare

实现 immutable commit resolve、repository read/native diff、comparison/risk/surface/bundle 和只读 operation。

退出条件：history compare 不修改 Workspace/Submission/Archive 状态，远程 repository read 与本地 oracle 等价。

### Phase 5 整体退出条件

- 完整 `upload -> submit -> review -> archive -> next baseline -> history compare` journey 通过。
- API、application、domain、capability、operation 和 repository 边界符合架构测试。
- 新主路径不依赖旧业务模块和统一 StateStore。

## 9. Phase 6：Rust Coverage Expansion and Compute Optimization

### 目标

在 Phase 3 首批 Rust production kernel 的基础上，根据完整业务 journey profile 扩大 Rust 覆盖并深度优化数据路径。Phase 6 不是首次引入 Rust，也不机械替换所有 Python/Polars 实现。

Provider route 遵守 [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)，收益声明遵守 [Performance Measurement and Baseline](../contracts/performance-measurement-and-baseline.md)。

### 推荐顺序

1. 复核 Phase 3 scalar/digest、projection、standard diff 和 records 的端到端收益与内存表现。
2. 优化 Arrow zero-copy、batch size、materialization 次数和 Rust/Polars 线程预算。
3. 根据 fixtures 和 profile 引入 ordered preparation、classification、interval 和 move。
4. 根据 risk records 规模评估 Rust facts extraction，规则定义和业务决策继续保留 Python。
5. 最后单独评估 SQL streaming parser，不按当前 Python parser 机械翻译。

### 实现形态

```text
gateway-compute-core       Rust algorithms
gateway-compute-python     PyO3/Arrow adapter
gateway-compute-worker     artifact-based worker/CLI
```

- 同步低延迟路径使用 PyO3 + Arrow 粗粒度调用。
- 大型异步任务可以由 Rust worker 消费 Parquet/Arrow artifact。
- Python 保留 domain、application、Operation Runtime、ruleset selection 和频繁变化的业务 policy。
- Risk 的大规模 facts extraction 可进入 Rust，规则定义和小规模决策优先保留 Python。

### 进入条件

- 目标阶段有独立 profile，且占正式请求 CPU 或内存的显著比例。
- Python reference oracle 和跨语言 golden fixture 已稳定。
- Arrow/Parquet 和 scalar/digest contract 已版本化。
- Phase 3 首批 Rust provider 已通过真实纵切验证，不存在尚未收口的基础 FFI/打包问题。
- Slice 5B 已按 measurement contract 产生 accepted vNext baseline；没有 baseline 不得声明 coverage/provider 优化收益。

### 退出条件

- Rust 与 Python reference 的 facts、records、排序和 digest 一致。
- Kernel 和端到端 benchmark 均达到预设收益门槛。
- Panic、超时、取消、内存不足和 native crash 有明确失败边界。
- Rust provider 可通过 feature flag 回退到 reference provider。

### 本阶段不做

- 不按 Python 文件、class 和 dataclass 一一翻译 Rust。
- 不通过逐行 PyO3 调用传递百万个 Python object。
- 不长期维护两个同等权威的正式算法实现；Python 逐步转为小数据 oracle/fallback。

## 10. Phase 7：Concurrency, Cache and Performance

### 目标

在完整正确路径稳定且首份 vNext baseline 已 accepted 后，根据同一可比 series 的 measurement 引入受控并行、cache 和 provider 优化。

### 主要工作

- Capability 内部按表/partition 并行和确定性汇总。
- Operation 固定 fan-out/fan-in，仅用于需要独立恢复的 pair/task。
- Repository Service 单 repository writer 和节点级资源队列。
- Snapshot table、projection、comparison core、risk 和 artifact cache。
- Cache authority、promotion、validation、eviction 和 cleanup。
- Polars LazyFrame/streaming、Arrow zero-copy、Rust Rayon 和 I/O pipeline 优化。
- 建立统一并发预算，控制 Operation worker、Python pool、Polars/Rayon 和 Repository worker。

### 退出条件

- 并行模式与串行模式产生相同正式结果和 digest。
- Cache miss/corruption 只影响性能，不改变业务事实。
- p50/p95、吞吐、峰值内存和磁盘放大满足目标。
- 过载时系统有背压，不通过无限线程/任务扩张维持吞吐。

## 11. Phase 8：Shadow Traffic and Cutover

### 目标

在不破坏正式业务状态的前提下验证新路径，并按风险从低到高切换流量。

### 切换顺序

1. 离线 language-neutral fixture/canonical correctness 对照，以及独立 vNext measurement。
2. 只读 shadow：catalog、history resolve、comparison。
3. Upload preview shadow，结果不对用户生效。
4. Upload preview 正式切换。
5. Submit 双重验证但单写，禁止两个系统同时提交 repository 写入。
6. Submit/Review 正式切换。
7. Archive plan preview shadow。
8. Archive mainline CAS 正式切换。

### 规则

- Shadow 比较使用规范化结果，不要求保留旧 host path、cache key 或 bundle layout。
- Shadow 只对照 canonical correctness 和明确 intentional change；不运行 legacy-vs-vNext 性能门禁。
- 任何写路径只能有一个 system of record 和一个 writer owner。
- 每次切换有明确 feature flag、回滚点和数据兼容说明。
- 回滚不得依赖删除新系统已经提交的 immutable commit。

### 退出条件

- 新路径承载全部正式旅程，旧路径不再写业务事实。
- Shadow 差异全部有结论。
- 回滚演练和数据一致性检查通过。

## 12. Phase 9：Cleanup and Production Hardening

### 目标

删除临时兼容边界，完成生产运维、容量和恢复能力，使目标架构成为唯一正式实现。

### 主要工作

- 删除旧 Flow、统一 StateStore、Dolt local adapter、重复 DTO 和路径字段。
- 从业务容器移除 Dolt 二进制和 repository volume。
- 删除不再使用的 feature flag、shadow writer 和 compatibility artifact。
- 只完成当时accepted contract和生产运维实际需要的Repository Service backup/restore、GC、
  Dolt upgrade/rollback与容量runbook；不得借production hardening重开已延期的通用治理surface。
- 完成 operation backlog、lease、cache、artifact、repository disk 和业务 journey observability。
- 按已登记A/B类风险执行关键故障注入、灾难恢复、滚动升级和安全审计；C/D类只验证失败不
  污染权威事实、可重试/诊断，不穷举内部interleaving。
- 更新所有架构、contract、部署和运维文档。

### 退出条件

- 目标架构是唯一正式主路径。
- 业务容器不执行 Dolt 命令、不访问 repository 本地目录。
- API 不拥有业务状态机，Domain 不依赖 infrastructure。
- Operation 可跨进程恢复，Repository 写操作可审计和恢复。
- 完整journey通过；accepted contracts与风险登记要求的故障、恢复、性能和安全验收通过，
  不以未接受的理论威胁或全故障点矩阵阻塞退出。

## 13. 跨阶段工作流

### 13.1 Contract 变更

任何跨模块或跨语言 contract 变更必须：

1. 更新 schema/version。
2. 更新 golden fixture。
3. 更新受影响owner implementation和consumer的contract tests；canonical bytes变更
   固定要求Python/Rust，Repository只在自身wire/structural contract受影响时更新。
4. 说明 cache/digest compatibility。
5. 说明滚动升级期间的兼容窗口。

### 13.2 数据迁移

- Legacy Dolt migration/compatibility 是独立 cutover gate；本计划不预设迁移或不迁移结论。
- Gate 若选择不迁移，必须提供明确环境初始化和切换边界。
- Gate 若选择迁移，迁移器是独立一次性应用，不把 legacy schema 兼容写入新 domain。
- 迁移结果通过业务 ID、commit、artifact digest 和抽样 journey 验证；不得把 raw legacy commit 与 canonical vNext commit 当作同版本 state 直接比较。

### 13.3 可观测性

从 Phase 1 开始统一 correlation ID：

```text
request_id
business operation_id
repository_operation_id
repository_id/ref/commit
artifact digest
capability/provider/version
```

日志不携带敏感 row payload 和服务端私有路径。

### 13.4 安全

- Interface 执行用户认证和业务授权。
- Repository Service v1执行global service bearer认证和server-owned repository scope，不预建
  per-tenant/per-repository ACL；需要多租户隔离时先reopen owning contract/ADR。
- Import、SQL、archive和artifact解压等不可信或高资源输入从第一版就采用有测量依据的bounded
  limits；不要求为所有内部对象建立通用quota/accounting平台。
- 同机受控模块/worker默认属于单一信任域。引入不可信plugin、本地恶意actor、独立UID/helper
  或自定义安全IPC前必须通过全局比例化保障policy的架构升级门。

## 14. 全局 Definition of Done

一个阶段或纵切只有同时满足以下条件才算完成：

- 行为和 contract 测试通过。
- 架构依赖测试通过。
- 按风险登记要求的关键语义屏障、幂等和失败测试通过；不要求全故障点矩阵。
- 产物有明确owner和必要diagnostics；只有当内容相等性、transport integrity或consumer
  contract确实需要时才要求digest，不为所有内部产物统一加digest/evidence。
- 没有新增 host path、隐式全局状态或跨层 DTO re-export。
- 初始 correctness route 有 component evidence；任何优化/回归性能结论都有 accepted vNext baseline 或容量数据支持。
- 文档、ADR、runbook 与实现一致。
- 新代码已接入正式入口或明确标记为未启用，不能长期处于无人使用的“已完成”状态。

## 15. 执行台账模板

每个 Phase/Slice 建议建立独立执行台账，至少记录：

```text
owner
scope
entry criteria
contract/ADR links
implementation PRs
test commands and results
benchmark dataset and results
manual verification
known differences
rollback point
exit criteria decision
```

台账只记录执行事实，不复制本文件的长期边界。阶段中出现的新架构决策必须回写总纲、专项 contract 或 ADR。

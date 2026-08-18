# P3-R1-S0 Existing Asset Inventory and Applicability Review

状态：S0 complete；S1 ownership skeleton complete；S2 shared-primitive gap decision complete；S3 artifact/staging conformance complete；S4 focused review complete（R1 implementation authorization remains pending）

日期：2026-08-18

Owner：Backend vNext Capability Architecture

Source tip：`d43207360e51ee2e246b83134828bf98195b0768`

审查开始时工作树：clean（branch `phase1/gate-ownership-repair`，无未提交变更）；本文件和
执行计划状态更新是本次 S0 文档交付。

## 1. Review boundary and evidence

本审查按照 [P3-R1 Capability Foundation Execution Plan](p3-r1-capability-foundation-execution-plan.md)
S0 的只读范围执行。语义 authority 依次采用 P3 contracts/ADR、P3 design/plan，再采用
Phase 1 源码和测试作为行为 evidence；legacy 与过程文档不作为当前 contract。

已读取并用于本结论的 authority：

- `shared-canonical-encoding.md`、`canonical-row-hash-compute-boundary.md`、
  `canonical-storage-and-repository-boundary.md`、`fixture-oracle-and-conformance.md`、
  `contract-taxonomy-and-ownership.md`；
- ADR 0001、0004、0005、0010、0012；
- P3 Capability Foundation Design、P3 active context index、P3-R1 execution plan；
- 本文列出的源码、直接相关测试和 repository-level fixtures。

本次没有修改业务代码、共享 primitive、artifact schema 或正式 contract/ADR。

## 2. Asset inventory

| Asset/path | Current owner / contract authority / consumers | Decision and P3 semantic fit | Dependency direction | Test evidence | Capacity/concurrency concern | Artifact/digest concern | Failure/recovery concern | Required follow-up |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `vnext/shared_kernel/src/gateway_shared_kernel/` | Shared Kernel；Shared Canonical Encoding；backend canonicalization、canonical row-hash provider、Rust shared kernel 通过同一 fixture 解释 | **KEEP**。canonical identifier、scalar/null、JCS、framing、semantic/raw digest 与 P3 一致；不承载 capability/business facts | `capability -> shared_kernel`；不反向依赖 backend/artifact | `vnext/shared_kernel/tests/`；canonical vectors、property tests、stable error codes | 纯 bytes/CPU primitive；不引入 Dolt 或线程池状态；批量并行由上层 owner 控制 | semantic digest 与 raw blob digest 分域；不把 provider/thread/input order 放入 digest | fail-closed error registry、invalid vector evidence；process/native takeover 由后续 Operation owner | S2 仅做 conformance；只有发现真实缺口且有两个独立 consumer 才 reopen Shared Kernel |
| `vnext/shared_kernel/tests/` | Shared Kernel test owner；Shared Canonical Encoding/Fixture Oracle；Python/Rust correctness consumers | **KEEP**。测试数据是 repository-level oracle，不搬到 capability package | tests consume public shared API/fixtures；不成为 production dependency | JCS/scalar/identifier/framing/digest/error/property coverage | unit-safe；不得创建 Dolt 或 durable external state | 直接比较 bytes/digest/error code；不使用已删除 self-digest/evidence wrapper | invalid cases 覆盖 deterministic rejection；recovery 不属于 primitive | S1/S2 保持薄 loader；新增 case 必须由现行 contract 语义推出 |
| `vnext/backend/src/gateway_backend/artifacts/types.py` | `gateway_backend.artifacts`；ADR 0010 minimal Backend `ArtifactRef`；Backend artifact consumers | **KEEP**。仅四字段 `artifact_id/media_type/size_bytes/raw_sha256`，不含 semantic metadata/host path，符合 P3 immutable ref 边界 | capability content owner -> artifacts envelope；artifact store 不解释 capability content | `test_artifact_boundary.py` exact shape、unknown field、host-path rejection | bounded ID/size；ref equality 不依赖 provider、root 或 thread | raw SHA/size 是 transport integrity；semantic content/schema metadata 留 capability owner | model validation、opaque ID/root escape gates；写入崩溃证据待 S3 | 禁止新增 `ArtifactRef` 变体；S1 import checks 保持 nominal boundary |
| `vnext/backend/src/gateway_backend/artifacts/{digest.py,serialize.py,validate.py}` | Artifacts owner；minimal ref serialization/validation；local/in-memory store | **KEEP**。JCS ref round-trip 和 fail-closed unknown fields 可作为 foundation | 只依赖 Shared Kernel digest/JCS 与 artifacts types；不依赖 compute/provider | `test_artifact_boundary.py` round-trip/unknown-field；架构测试禁止 compute import | serialization 是小型 metadata，不进入 bulk row path | 不携带 `content_digest`、`content_schema_id`、retention 或 access metadata | malformed ref、raw identity mismatch 映射 `ManifestVerificationError`/`ValueError`；partial write 见 F-001 | S3 增加 corruption/missing/partial-write conformance，不改变四字段 contract |
| `vnext/backend/src/gateway_backend/artifacts/store.py` | Artifacts owner；`ArtifactStorePort`、`InMemoryArtifactStore`；capability tests and local adapter | **KEEP**，仅作 port + hermetic test store；不承担 retention/cleanup policy | capability -> `ArtifactStorePort`；store -> Shared Kernel/artifacts validation | `test_artifact_boundary.py` in-memory publish/reopen and raw integrity | in-memory bounded to test data；不作为 production bulk storage或并发调度器 | exact ref and raw bytes verified on put/locate；semantic recompute intentionally absent on ordinary reopen | unknown/mismatched/malformed bytes fail closed；no durable crash simulation yet | S3 定义 missing/corrupt behavior and cleanup interaction；禁止 generic content schema |
| `vnext/backend/src/gateway_backend/infrastructure/artifact_store/local_store.py` | Infrastructure adapter；ADR 0010/0012 local artifact storage boundary；`tmp_path` tests and future staging tests | **KEEP with bounded use**。适合 R1 test staging/round-trip；不拥有 capability content schema、retention 或 production cleanup | `LocalArtifactStore -> artifacts port/serialization -> Shared Kernel`；capability 不直接使用 filesystem path | `test_artifact_boundary.py` tmp_path round-trip and ordinary reopen | atomic temp file + fsync + replace；每-artifact cache is process-local and not a cross-worker coordination mechanism | path is internal only; ref remains location-independent; sidecar stores minimal ref | root/path/symlink checks and read integrity exist；bytes/sidecar failure window and cleanup proof are open (F-001) | S3 only: partial/corrupt/missing artifact and cleanup tests; use pytest `tmp_path`, no durable workspace dependency |
| `vnext/backend/src/gateway_backend/capabilities/canonical_row_hash/contracts.py` | Canonical Row Hash capability；Canonical Row Hash Compute Boundary §8；row-hash IPC/publish tests | **KEEP as capability-specific reference; EXTEND only in its owner package**。S1 moved metadata from the backend root; it is not generic ArtifactRef and correctly carries semantic/schema digests | row-hash capability -> Shared Kernel `DigestRef` + artifacts envelope; artifacts must not import this module | `test_artifact_boundary.py`, `test_canonical_row_hash.py`, fixture schema | row_count is canonical decimal string; IPC/chunking/provider identity excluded from semantic identity | semantic `raw_content_digest`/`table_schema_digest` stays separate from raw IPC SHA | content manifest validation and ordinary Arrow reopen are covered; native crash/takeover belongs later Operation | Public contract is in the owner package; no root compatibility alias. Algorithm modules remain at backend root until a later capability R |
| `vnext/backend/src/gateway_backend/canonical_row_hash_ipc.py` and `compute.py` | Canonical Row Hash capability facade/adapter；Compute Boundary；Rust production provider | **KEEP as evidence/reference boundary; DEFER algorithm expansion to capability R**。coarse Arrow boundary matches P3 and no artifact locator crosses FFI | backend facade -> `gateway_compute` -> Shared Kernel semantics; IPC publisher -> ArtifactStore port | architecture import checks; mixed-scalar golden; artifact boundary tests | no `to_pylist`/row-wise FFI; batch/thread policy remains outside digest | validates Arrow schema/raw SHA/semantic content at publish; ordinary reopen does not rehash semantics per ADR 0010 | stable deterministic failure mapping; uncaught process termination explicitly deferred to Operation | S1 only adds public import checks/contracts; do not add automatic Python fallback or generic provider base |
| `vnext/backend/src/gateway_backend/canonicalization_cells.py` | Storage Projection/Table Rules owner；Canonical Storage §4；manifest producer/tests | **DEFER to P3-R4**。Reuses Shared Kernel scalar/collection bytes and correctly keeps ENUM/SET semantics out of shared kernel, but is outside R1 foundation | storage projection -> Shared Kernel; not a dependency of generic artifacts or row-hash owner | `test_canonicalization_manifest.py` ENUM/SET/null/order tests | row materialization is data-plane work; no Dolt in unit tests | per-cell/schema/content digest is business/storage semantic, not ArtifactRef raw SHA | malformed scalar/type errors are owner-level; full key/row-loss/recovery evidence belongs R4 | R1 must not copy or generalize these helpers; R4 owns further validation |
| `vnext/backend/src/gateway_backend/canonicalization_manifest.py` | Storage Projection owner；Canonical Storage §4 manifest/digest; manifest and package tests | **DEFER to P3-R4**。Outer domain-separated manifest digest and child raw digests fit current contract; not a shared primitive | storage projection -> Shared Kernel JCS/cell encoding; Repository consumes only structural package fields | manifest digest ordering, row count, keyless order, schema/content tests | table iteration/materialization scale and concurrency are R4 concerns | source/ruleset/schema/content/manifest digests remain distinct; package digest is transport-only | duplicate table/row-count checks exist; complete schema/key policy and recovery handoff remain R4 | R4 must validate full manifest invariants before package publication; no R1 changes |
| `vnext/backend/src/gateway_backend/repository_import_artifact.py` | Storage Projection package writer; Canonical Storage §6.1; repository import tests | **DEFER to P3-R4/R7**。Fixed two-entry tar+zstd writer is useful evidence, but Repository effect is explicitly out of R1 | storage projection -> package bytes -> Repository Service public contract; no reverse dependency | `test_canonicalization_manifest.py` reproducibility/USTAR tests | package size/replay limits and external execution belong P5B/Repository owner | package raw SHA uses minimal ArtifactRef; manifest digest remains opaque to Repository | package safety/reader rejection and import recovery are downstream contract | Do not make package writer a R1 generic artifact helper; reuse only through owner boundary |
| `vnext/backend/tests/test_architecture.py` | Backend architecture owner；P3-R1 import/ownership guard | **KEEP and EXTEND** for S1 checks. Existing tests already enforce artifact/compute/infrastructure separation and no deferred stubs | static source checks point downward; no runtime/provider selection dependency | legacy import, artifact locality, Rust boundary, IPC materialization, canonicalization checks | static checks are cheap and parallel-safe | catches ArtifactRef/infrastructure leakage into compute and artifacts | does not prove runtime crash/recovery; pair with S3 focused tests | Add concrete capability package owner/import checks; never create `capabilities/common`/`utils` |
| `vnext/backend/tests/test_artifact_boundary.py` | Backend artifact/canonical-row-hash owner tests | **KEEP; EXTEND in S3**。Current direct tests are the foundation for round-trip and ordinary reopen | tests consume public ports/owner metadata; no Dolt | minimal ref, tmp_path LocalStore, Arrow corrupt/truncate/schema, semantic-manifest independence | unit marker; tmp_path isolation | verifies minimal ref + Arrow fixed schema and separate semantic manifest | missing bytes/sidecar and write-failure injection absent | Add S3 test cases from F-001; preserve parameter-table style for malformed variants |
| `vnext/backend/tests/test_canonical_row_hash.py` | Canonical Row Hash capability owner | **KEEP** as one business golden consumer | facade -> public Arrow/DTO boundary; no artifact store required for golden | mixed-scalar golden exact row hashes/row count/schema/raw digest | small golden only; no Dolt; production scale belongs provider benchmark | expected excludes provider/thread/path and compares semantic outputs | deterministic compute failures covered by provider tests; takeover later | R1 only references; no new production capability algorithm |
| `vnext/backend/tests/test_canonicalization_manifest.py` | Storage Projection owner | **DEFER/KEEP as R4 evidence** | manifest/cell/package producer tests remain downstream of R1 | ENUM/SET, digest ordering, row count, package reproducibility | pure unit; no Dolt fixture | confirms storage semantic digest layering and opaque package association | structural/key/recovery matrix incomplete for R4 | Do not use these tests as R1 capability contract tests |
| `vnext/fixtures/golden/canonical-row-hash/mixed-scalars/` | Canonical Row Hash capability; ADR 0010 business golden | **KEEP**。Minimal request + Arrow input + expected semantic result is directly reusable | golden -> Python facade/Rust provider; no generic runner | `test_canonical_row_hash.py`, Rust core golden | deliberately small; no capacity claim | expected sorted hashes/schema/raw content, no fixture self-digest | malformed/recovery not encoded; separate failure tests required | Keep owner-local additions minimal and review semantic version impact |
| `vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/` | Shared Kernel; Shared Canonical Encoding contract | **KEEP**。Cross-language bytes/error corpus is the canonical primitive authority | Python/Rust shared-kernel tests -> static files; Repository does not consume | JCS/scalar/digest/invalid loaders and Rust tests | static read-only corpus; no external dependency | exact bytes/digest, no vector-set/self-evidence wrapper | invalid cases prove deterministic rejection, not operation recovery | S2 conformance only; no new generic fixture runner |
| `vnext/fixtures/vectors/compute/canonical-row-hash/v1/` | Canonical Row Hash capability; Compute Boundary | **KEEP as capability evidence; DEFER new scenario machinery** | provider tests -> static README/golden; no artifact owner dependency | Rust core test suite and repository golden | small test corpus; README records 77 tests and deferred corrupt IPC fixtures | capability semantic result only; artifact schema separate | categories A/B/C cover deterministic compute failures; corrupt IPC deferred to WP4 | S3 may add artifact round-trip fixtures without adding scenario manifest |
| `vnext/fixtures/vectors/repository/sql-enum-set/v1/` | Repository Service; Repository §10.1 + Shared Encoding §3.2 | **DEFER to R2/R4/Repository owner**。Not a third Shared Kernel corpus | Repository owner -> shared string/sequence bytes; R1 must not consume it as generic fixture | repository/Rust tests are downstream evidence | static JSONL only | ENUM/SET content bytes are storage/repository semantics, not artifact identity | malformed/illegal value cases exist; repository effect recovery is elsewhere | Keep owner-specific; no R1 common loader |
| `vnext/fixtures/schemas/artifacts/v1/canonical-row-hashes-artifact.schema.json` | Canonical Row Hash capability content schema | **KEEP as reference schema; EXTEND only with owner review** | schema -> metadata/IPC tests; does not define minimal ArtifactRef | runtime metadata validation and artifact tests; schema validator not currently required | static bounded manifest shape | semantic content/schema digest fields intentionally separate from minimal ref | schema invalidity is fail-closed at metadata parser; no cleanup semantics | S1/S3 may add direct schema/round-trip assertion if needed; no generic artifact schema registry |

## 3. Owner and dependency graph

```text
Shared Canonical Encoding (Shared Kernel)
  ^
  | public DigestRef / identifier / scalar / JCS / framing
  |
Capability owners (one owner per contract)
  |-- Canonical Row Hash -> Arrow/PyO3 facade -> ArtifactStore port
  |-- Source/Table Materialization -> Snapshot artifacts (R2/R3)
  |-- Storage Projection -> CanonicalizationManifest -> Repository package (R4/R7)
  |-- Comparison / Risk / Bundle (R5/R6) consume immutable public artifacts/facts
  `-- Mutation / ChangeSet (R7) consumes public projections, not provider objects

Backend Artifacts owner
  |-- minimal Backend ArtifactRef (nominal, raw transport integrity only)
  `-- ArtifactStorePort -> InMemoryArtifactStore / LocalArtifactStore (infrastructure)

Forbidden directions
  artifacts -X-> compute/capability-private metadata
  Rust core -X-> Backend artifacts / filesystem / Repository DTO
  capability -X-> another capability's _internal/provider/cache/builder
  capability -X-> HTTP / Workspace / Operation Runtime / Dolt business semantics (R1)
```

There is no observed cycle in the reviewed source/import checks. The graph deliberately keeps
`CanonicalRowHashesArtifactMetadata` with the Canonical Row Hash owner even though its current
Phase 1 module is at `gateway_backend` root; S1 may establish a concrete capability package, but
must not turn it into a shared artifact type.

## 4. Compatibility matrix

| P3 requirement | Existing evidence | Result | Gate/condition |
| --- | --- | --- | --- |
| Shared canonical primitive has one owner and cross-language bytes | Shared Kernel contract, Python tests, Rust/static vectors | **PASS / KEEP** | S2 conformance only; reopen on semantic mismatch |
| Capability contract does not own or duplicate canonical bytes | Row-hash boundary explicitly delegates bytes to Shared Kernel; architecture checks reject leakage | **PASS / KEEP** | S1 import checks must preserve direction |
| Immutable handoff can be represented without host path | Minimal ref + capability content metadata are separate; LocalStore stores path internally | **PASS** | S3 helper asserts published ref has no host path or workspace root |
| Raw transport digest differs from semantic/content digest | `ArtifactRef.raw_sha256` vs row-hash/manifest digests; tests assert minimal fields | **PASS** | No new combined digest or ref field |
| Provider identity/thread count/input ordering absent from semantic identity | row-hash contract and metadata identity key; canonical vectors | **PASS** | Keep execution policy outside contracts |
| Artifact store can support tmp_path/local staging | `LocalArtifactStore` atomic write, sidecar, root checks; tmp_path test | **PASS** | S3 helper uses pytest `tmp_path` only |
| Partial/corrupt/missing artifact has executable proof | S3 `STAGING_OBJECT_FAULTS` plus sidecar-replace crash barrier; Arrow corrupt/truncate/schema remain owner tests | **PASS** | Closed with F-001; no broker |
| Cleanup does not change durable business state | ADR 0012 owns production policy; S3 proves staging `rmtree` does not mutate sibling durable incident | **PASS / DEFER production** | Test cleanup helper recorded; production retention remains F-004 |
| Fixtures are language-neutral and owner-scoped | repository-level vectors/golden and ADR 0010 rules | **PASS / KEEP** | No generic runner/self-digest/evidence wrapper |
| R1 has no Dolt dependency | reviewed unit tests and plan boundary | **PASS** | Any Dolt fixture is integration and outside R1 pure contract tests |
| No capability cycle/generic common package | current architecture checks and plan invariants | **PASS / CONDITIONAL** | S1 must add import checks and reject `capabilities/common`/`utils` |
| Failure/recovery semantics are fully proven for R1 artifact foundation | S3 proves missing/corrupt/sidecar-replace fail-closed and test cleanup isolation | **PASS for R1 test staging** | Production crash/takeover remains later Operation/lifecycle owner |

## 5. Issue and decision register

### 5.1 Findings

| ID | Severity/status | Finding | Owner | Required action / reopen condition |
| --- | --- | --- | --- | --- |
| `F-001` | Closed in S3 | `LocalArtifactStore` has no executable test for bytes/sidecar failure between atomic replacements, missing bytes/sidecar after reopen, or cleanup interaction. Existing tests prove raw/Arrow rejection but not the complete partial/missing matrix. | Artifacts + Backend test owner | S3 added `tmp_path` staging conformance: missing/corrupt object and sidecar after reopen, sidecar-replace crash barrier, and staging cleanup that does not mutate a sibling durable integrity incident. No broker or atomic-publication ADR reopen. |
| `F-002` | Deferred to R4 | Manifest producer tests do not constitute the complete Storage Projection key/row-loss/structural policy matrix. | Table Rules/Storage Projection | R4 owns full manifest/key/ordering validation; R1 must not generalize these helpers. |
| `F-003` | Closed in S1 | Capability-specific row-hash metadata lived at the backend root rather than a concrete capability package. | Canonical Row Hash capability | S1 moved the public contract to `capabilities/canonical_row_hash/contracts.py` with architecture/import tests and no compatibility alias. Do not reintroduce a root-level shared metadata type. |
| `F-004` | Deferred to later lifecycle owner | `LocalArtifactStore` has no production retention/cleanup API by design; pytest `tmp_path` supplies test cleanup only. | ArtifactStore/business lifecycle owner | S3 recorded the test cleanup helper in `tests/support/artifact_staging.py`; production retention/cleanup remains outside R1 and follows ADR 0012. |

No S0 blocking finding required contract/ADR reopen. `F-001` was an evidence gate for S3
and is closed by the §10 staging conformance tests; that closure is not permission to invent
a broker, sidecar state machine, generic artifact schema, or automatic recovery mechanism.

### 5.2 Decisions

| ID | Decision | Rationale |
| --- | --- | --- |
| `D-001` | KEEP `gateway_shared_kernel` as the only cross-language canonical primitive owner | Existing semantics and vectors match P3; duplication would violate ADR 0005/0010. |
| `D-002` | KEEP `gateway_backend.artifacts` minimal nominal envelope/store port | Four-field ref expresses immutable location/integrity handoff without semantic ownership leakage. |
| `D-003` | KEEP `LocalArtifactStore` only as bounded local/test staging adapter | It satisfies tmp_path round-trip shape; it must not become retention, cleanup, or cross-worker coordination. |
| `D-004` | KEEP capability semantic metadata with its concrete owner; do not add `capabilities/common` or `capabilities/utils` | Artifact envelope and content schema have different owners under contract taxonomy. |
| `D-005` | DEFER canonicalization/manifest/import writer to R4/R7 | They are storage/repository semantics, not R1 foundation; current implementations are usable evidence only. |
| `D-006` | KEEP repository-level golden/vectors with owner-specific loaders | ADR 0010 requires direct bytes/result comparison and rejects generic runner/self-digest machinery. |
| `D-007` | No shared primitive gap is proven | S2 should add conformance checks only; a new primitive requires two independent consumers and an owning-contract update. |

## 6. R1-S0 recommendation and S1 entry package

**Recommendation：S0 complete，允许进入 S1 contract/skeleton；R1 尚未整体授权，且不得把本结论
表述为 R1 gate 通过。**

S1 的允许路径和边界：

- 在 `vnext/backend/src/gateway_backend/capabilities/<concrete-owner>/` 建立就近的
  public `contracts.py`/ports skeleton；不得创建 `capabilities/common`、
  `capabilities/utils` 或万能 provider base class；
- 仅更新 `vnext/backend/tests/test_architecture.py`、直接 contract/import tests 和本
  formal plan/handoff 文档；
- capability 只依赖上游 public contract、immutable artifact/ref 和 Shared Kernel public
  primitives；禁止 `_internal`、provider selection、planner、builder、cache layout、HTTP、
  Workspace、Submit、Operation Runtime、Repository business semantics；
- S2 默认不新增 shared primitive，只做 Python/Rust/static fixture conformance；
- S3 必须关闭 `F-001`，覆盖 manifest/schema/raw/content digest 分层、immutable
  write/read/reopen、partial/corrupt/missing artifact 和 tmp_path cleanup；不得依赖 Dolt。

S1 handoff 必须携带本 inventory、decision register 和 owner graph。R2 仍需等待 R1-S7
handoff；本 S0 文档不授权 SQL/XML parser 或 source materialization 实现。

## 7. Verification record

本审查的静态 evidence 来自 source/test readback。执行计划要求的运行验证在 S1/S3 按允许
路径执行；当前 S0 未宣称 artifact conformance、R1 gate、container 或 production
validation 已通过。S0 已执行的 focused 验证如下：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_artifact_boundary.py` | **16 passed**（1.31s） |
| `cd vnext/backend && uv run pytest -m unit tests/test_canonicalization_manifest.py` | **11 passed**（0.50s） |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **Success: no issues found in 26 source files** |
| `cd vnext/shared_kernel && uv run pytest` | **242 passed**（0.83s） |
| `cd vnext/shared_kernel && uv run pytest -m unit` | **242 deselected，退出码 5**；该包现有测试未声明 `unit` marker，不能把空选择记为通过 |
| `git diff --check` | **passed** |

建议 S1 首轮命令：

```text
cd vnext/backend
uv run pytest -m unit tests/test_architecture.py tests/test_artifact_boundary.py
uv run ruff check .
uv run mypy
git diff --check
```

## 8. S1 ownership skeleton record

S1 将 §3 owner graph 落成可导入、可静态检查的 package 边界。R1 仍未整体授权；本记录
不宣称 S2/S3 conformance、parser 实现或 R1 gate。

Owner packages under `vnext/backend/src/gateway_backend/capabilities/`：

```text
canonical_row_hash
table_access
table_rules
snapshot_materialization
storage_projection
comparison_projection
comparison
risk_evaluation
business_projection
surface_assembly
bundle_assembly
mutation_planning
```

Each owner has public `contracts.py`. There is no `capabilities/common`,
`capabilities/utils`, `_internal`, or generic provider base. Field-level Input/Result
types for R2–R7 are not pre-declared.

Allowed capability-to-capability imports (downstream → upstream `contracts` only):

```text
snapshot_materialization -> table_access, table_rules
storage_projection -> table_rules, snapshot_materialization
comparison_projection -> table_rules, snapshot_materialization
comparison -> comparison_projection
risk_evaluation -> comparison
business_projection -> comparison
surface_assembly -> comparison, risk_evaluation, business_projection
bundle_assembly -> surface_assembly
mutation_planning -> storage_projection
canonical_row_hash -> (none; Shared Kernel + artifacts envelope only)
```

Not moved in S1 (remain Phase 1 evidence / later-R owners):

```text
gateway_backend.compute
gateway_backend.canonical_row_hash_ipc
gateway_backend.canonicalization_cells
gateway_backend.canonicalization_manifest
gateway_backend.repository_import_artifact
```

Architecture/import checks live in `vnext/backend/tests/test_architecture.py`. `F-001`
remains the S3/R1 evidence gate.

## 9. S2 gap decision and conformance record

S2 执行基线：`908d5ea2140154c7efb162c020acbca9809651a7`（S1 HEAD）。本步不新增
shared primitive、不扩 128-case corpus、不修订 owning contract/ADR。

### 9.1 Gap decision

| ID | S2 disposition | Rationale |
| --- | --- | --- |
| `D-001` | KEEP | Python/Rust 仍共用同一 canonical encoding corpus；无语义 mismatch。 |
| `D-002` | KEEP | `ArtifactRef` 仍是四字段 nominal envelope；S2 只补 envelope conformance。 |
| `D-007` | Confirmed | 没有两个独立 consumer 所要求、且现有 primitive 无法表达的缺口。 |

未扩 corpus：`unordered_row_hashes_content_digest` 与
`CANONICAL_COLLECTION_SEMANTICS_UNKNOWN` 已有语言本地单测；把它们写入 v1 JSONL
会改合同硬编码的 128 验收计数，且不是新 primitive。`F-001` 仍属 S3。

Changed paths：

```text
vnext/shared_kernel/tests/conftest.py
vnext/backend/tests/test_artifact_ref_conformance.py
vnext/backend/tests/test_artifact_boundary.py
docs/backend-vnext/refactoring/formal/plans/p3-r1-s0-asset-inventory.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
```

### 9.2 Verification

| Command | Result |
| --- | --- |
| `cd vnext/shared_kernel && uv run pytest -m unit` | **242 passed**（1.06s）；S0 的空选择已关闭 |
| `cd vnext/shared_kernel && uv run ruff check . && uv run mypy` | **passed**；mypy 34 source files |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_artifact_boundary.py tests/test_artifact_ref_conformance.py` | **53 passed**（0.60s） |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 51 source files |
| `cd vnext/rust && cargo test -p gateway-shared-kernel --locked` | **passed**（lib 82、`vector_conformance` 含 `rust_canonical_cases_match_shared_kernel`、sql-enum-set 3） |
| `git diff --check` | **passed** |

S2 complete，允许进入 S3 artifact/staging conformance。R1 尚未整体授权；本记录不宣称
R1 gate、parser 实现或 `F-001` 已关闭。

## 10. S3 artifact and staging conformance record

S3 执行基线：`91c8e81dc78a3316e7888fa20008b18b794650b2`（S2 HEAD）。本步关闭
`F-001`；不新增 production retention/cleanup、generic content schema 或 ArtifactRef 字段。

Test helper contract（R2–R7 import，不拥有 capability content schema）：

```text
vnext/backend/tests/support/artifact_staging.py
```

`F-001` closed。`F-004` remains deferred：helper 只证明 pytest `tmp_path` staging cleanup
不改 sibling durable integrity incident；production cleanup 仍由 ADR 0012 后续 owner 拥有。

`locate`/`put` 将 sidecar JCS `CanonicalEncodingError` 映射为既有
`ManifestVerificationError`；发布语义与四字段 envelope 未改。

Changed paths：

```text
vnext/backend/tests/support/__init__.py
vnext/backend/tests/support/artifact_staging.py
vnext/backend/tests/test_artifact_staging_conformance.py
vnext/backend/tests/__init__.py
vnext/backend/src/gateway_backend/infrastructure/artifact_store/local_store.py
docs/backend-vnext/refactoring/formal/plans/p3-r1-s0-asset-inventory.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
```

### 10.1 Verification

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_artifact_boundary.py tests/test_artifact_ref_conformance.py tests/test_artifact_staging_conformance.py` | **62 passed**（0.43s） |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 55 source files |
| `git diff --check` | **passed** |

S3 complete，允许进入 S4 focused review。R1 尚未整体授权；本记录不宣称 R1 gate 或
parser 实现。

## 11. S4 focused architecture/import and contract review record

S4 reviewed source tip：`e3542ecac3076ae25a51d65f029fb6b852e88665`。独立 review
记录见 [p3-r1-s4-focused-review.md](p3-r1-s4-focused-review.md)。审核范围覆盖 formal
contracts/ADR、S0 inventory、S1/S2/S3 cumulative diff，以及 architecture/import、artifact
ref 和 staging conformance tests。

S4 result：**PASS；无未处理 P1/P2 finding；S5 remediation not required**。重点检查均无
blocking finding：Shared Kernel duplication、generic-common drift、Backend/Repository
nominal ArtifactRef 混用、capability cycle/private import、Dolt dependency、error mapping
越权和 R1 scope expansion。

`LocalArtifactStore` 的 process-local ref cache 作为已知、非协调状态保留，属于 accepted
artifact adapter boundary；S3 以 fresh-store reopen 证明 durable sidecar/bytes 故障在恢复
路径上 fail closed。该观察不触发 ADR reopen，也不授权新增 broker、sidecar state machine
或 production cleanup。

S4 完成，允许进入 S6 independent review；R1 尚未整体授权，且本记录不宣称 R1 gate、S7
handoff 或 parser 实现。

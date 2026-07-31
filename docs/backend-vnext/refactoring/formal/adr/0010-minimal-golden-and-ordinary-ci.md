# ADR 0010: Minimal Golden, Artifact Boundary and Ordinary CI

状态：Accepted

日期：2026-07-31

决策 owner：Backend vNext Architecture

关联阶段：Phase 0–1及后续持续验证

依赖决策：
[ADR 0009](0009-proportional-assurance-and-trusted-internal-repository.md)

## Context

Phase 0–1已经固定canonical encoding bytes并建立Python/Rust核心、一个真实
canonical row-hash walking skeleton、通用ArtifactRef、language-neutral scenario
runner、profile matrix、run evidence和exact-commit phase exit。

Canonical byte contract、Python/Rust独立实现和少量业务golden具有长期consumer；
fixture self-digest、通用runner/evidence、Repository vector consumer、通用artifact
content/access/retention字段及exact-commit交付控制没有当前业务或威胁依据。它们把
正确性、测试材料完整性、运行证据和发布身份混成一套机制，显著增加schema、脚本、
测试和依赖数量。

ADR 0009已经接受少量协作者、单一信任域和适度保障。本ADR把相同原则应用于
Phase 0–1。

## Decision

### 1. Canonical correctness

保留Shared Canonical Encoding v1的JCS、typed scalar、identifier、row/collection
framing和domain-separated digest bytes。保留Python与Rust两份独立实现、当前128个
canonical valid/invalid case及稳定canonical failure code。

测试材料继续位于repository-level `vnext/fixtures/`，但只作为普通只读golden数据。
Python与Rust使用各自的薄loader直接逐case比较完整bytes/digest/error code；不再
使用`vector-set.json`、closure digest、candidate generator、JSON Schema或
Repository第三consumer。

现有mixed-scalar canonical row-hash场景简化为request、Arrow input和expected
row hashes/result三类直接测试材料。普通pytest/Cargo test负责比较，不建立scenario
manifest、generic runner/harness、profile matrix、RunEvidence或bless framework。

### 2. Python/Rust compute boundary

Python继续拥有小规模reference oracle，用于golden、property test和诊断；Rust是
正式批量production provider。Python reference不承担生产容量，不作为自动fallback，
也不与Rust作为两套同等production实现演进。

跨语言边界继续使用一个Arrow C Stream加小型JCS DTO。DTO最小字段为：

```text
Request
  boundary_version
  canonical_encoding_version
  arrow_mapping_version
  declared_fields

Result
  boundary_version
  table_schema_digest
  row_count
  raw_content_digest

Failure
  code
  message
  details optional
```

删除重复contract binding、content schema identity和
`stage/effect/retry_class`。Pure compute无外部effect，不需要在每次failure中重复
保存`effect=NONE`。

### 3. Digest ownership

保留有业务或算法consumer的digest：

- raw bytes直接SHA-256；
- Shared Kernel `row`、`raw-content`、`table-schema`和collection framing内部的
  `collection-item`；
- Workspace Input拥有的SourcePackage content digest；
- Table Rules/Storage Projection拥有的ruleset、projection、
  CanonicalizationManifest、business content和ordering digest。

删除只为测试自证或交付控制存在的`vector-set`、`scenario-input`、
`scenario-fixture`、`run-evidence`和`canonical-table-result` digest kind。
Canonical row-hash golden直接比较sorted row hashes、row count、
table schema digest和raw content digest。

### 4. Artifact boundary

每个ArtifactRef scope只表达可定位的opaque identity和raw transport integrity：

```text
artifact_id
media_type
size_bytes
raw_sha256
```

Backend local artifact ID与Repository ArtifactId使用不同scope、nominal DTO和
serialization module，但字段责任一致；upload时Repository分配新ID。任何ref不携带
`content_digest`、`content_contract`、`content_schema_id`、
`retention_class`或`access_metadata`。Capability result/manifest拥有semantic
metadata；ArtifactStore policy拥有retention和physical access。任何public ref均不
出现host path。

Artifact发布时验证raw integrity、固定Arrow schema和semantic result。普通reopen
只验证size/raw SHA、Arrow可解析性和固定schema，不重复遍历全部row hashes计算业务
digest。完整semantic recompute只保留在golden/integration、诊断或明确不可信边界。

### 5. Source and import artifacts

产生有效Submission/commit的SourcePackageArtifact继续以内容寻址方式durable
保存，因为canonical Dolt不能还原原始DDL、被删除列或原始literal token。失败或被
替换的Preview输入按TTL清理；`NO_CANONICAL_CHANGE`不提升为submission durable。

Backend在Repository package可删除前持久化完整CanonicalizationManifest。临时
Repository import package固定为`manifest.json + replay.sql`：

```text
manifest.json
  package_version
  canonicalization_manifest_digest
  tables[]
    name
    schema
    row_count
```

Repository只解释结构字段；`canonicalization_manifest_digest`是opaque关联值。
业务source、ruleset、projection、列策略、content和ordering digest只由Backend
业务owner解释。

### 6. Ordinary CI and container verification

持续验证使用普通package命令：

```text
Python: ruff + mypy + pytest
Rust: cargo fmt + clippy + test + release build
Native: installed release wheel import/compute smoke
Backend: artifact round-trip
Container: one Compose health/native smoke
```

保留pinned dependency/base image、non-root、stable Rust toolchain、
`forbid(unsafe_code)`、production no-panic、Rust core/PyO3 adapter分离、粗粒度
Arrow调用和GIL release。

删除generic conformance distribution、gate router、affected-scope/closure、
phase protection、immutable attempt、exact-commit identity bundle、phase-exit
evidence和对应schema、脚本、故障注入矩阵。历史Phase 1 exact-commit checkpoint只
保留一份简短说明；完整过程由Git历史保存。

### 7. Performance measurement

保留下列原则：

- 不以legacy数字作为vNext门禁；
- 只对correctness-passed的真实production path作性能声明；
- 记录dataset、软件版本、主要环境参数、原始样本和限制；
- 优化前后使用可比workload。

删除immutable environment identity、baseline record状态机、
content-digested evidence、预建workload/profile矩阵、固定样本统计门槛和formal
capture gate。真实纵切或容量问题出现时，由对应owner维护普通benchmark runbook。

## Transition

1. 本ADR supersede ADR 0006的通用conformance方案和ADR 0007的形式化baseline框架。
2. ADR 0001、0004和0005按本文amend。
3. Fixture、vector、performance、Artifact、row-hash、taxonomy、Rust policy和
   implementation-stage formal语义同步简化。
4. D01完成后进入cross-phase interface reconciliation，闭合ArtifactRef、package、
   digest owner和Backend → Repository依赖。
5. DX完成前不执行Phase 0–2代码删除；代码清理必须按可独立revert的小批次进行。

2026-07-31 follow-up：DX已由
[DX Cross-Phase Interface Reconciliation](../plans/dx-cross-phase-interface-reconciliation.md)
闭合。它没有改变本ADR decision，只明确两个ArtifactRef scope、package/checkpoint
binding、digest owner、package依赖、ordinary CI和`S02-C1..C5`清理顺序。

## Consequences

- Canonical业务结果和Python/Rust核心保持，测试与交付外围显著缩小。
- Repository不再依赖Shared Kernel conformance extra，也不充当canonical实现。
- 普通CI失败直接作为工程失败处理，不生成waiver或第二套evidence result。
- Artifact semantic metadata回到capability owner，生命周期回到store/business owner。
- 少量罕见测试环境或交付故障不再具有专用状态机，需要开发者直接诊断。
- Durable SourcePackageArtifact需要后续独立容量和删除策略。

## Required verification

- Python/Rust对当前128个canonical case逐bytes/digest/error-code一致，zero skip。
- mixed-scalar sorted row hashes、row count、table schema digest和raw content digest
  与清理前一致。
- Release wheel、Arrow C Stream、GIL、artifact round-trip和container native smoke通过。
- 普通artifact reopen拒绝raw hash、截断和Arrow schema错误；不会默认全量rehash。
- Repository package structural fields与durable CanonicalizationManifest绑定明确。
- 全文不存在仍具有当前authority的generic runner/evidence、Repository vector
  consumer、exact-commit gate或formal performance capture gate。

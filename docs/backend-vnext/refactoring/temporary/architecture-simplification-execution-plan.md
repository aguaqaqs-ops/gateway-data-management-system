# Architecture Simplification Execution Plan

状态：Active / Temporary Execution Coordination

日期：2026-07-31

适用范围：WP1-R1 checkpoint、Phase 2简化、Phase 0–1后续简化

正式决策：
[ADR 0009](../formal/adr/0009-proportional-assurance-and-trusted-internal-repository.md)

本文只记录执行顺序、状态、迁移边界和验收检查，不拥有public/persisted/wire
语义。正式语义必须落入Architecture、ADR或对应owner contract。任务完成后删除
本文，Git历史作为执行记录。

## 1. Objective and confirmed baseline

目标是在不打断正在进行的WP1-R1、且不改变Phase 0–1 canonical业务结果的前提下，
删除缺少现实威胁或consumer依据的security/evidence/recovery复杂度，使后续设计
默认遵守“业务优先、适度保障、需要驱动”的原则。

已确认基线：

- Repository Service保持独立内网进程，使用单一global bearer token。
- WP1-R1按旧设计完成，但只形成历史checkpoint，不承担兼容义务。
- WP1-R1后先简化Phase 2 contract和delivery skeleton。
- 修订后的WP1-R2开始前，专门执行Phase 0–1简化。
- Phase 2首版只实现Versioned/Dolt已知consumer链路。
- CurrentTableStore作为未来additive sibling，不预建generic dual-store abstraction。
- Phase 0–1保留canonical encoding、Python/Rust核心实现和业务golden bytes。

### 1.1 Grill-me baseline

| Area | Confirmed baseline |
| --- | --- |
| 项目目标 | 降低无现实威胁/consumer依据的安全、恢复和证据复杂度，优先交付业务能力 |
| 用户与场景 | 少量协作者；Backend通过内网Repository Service保存和读取canonical versioned tables |
| 范围内 | 全局设计原则、WP1-R1过渡、Phase 2 contract/delivery简化、Phase 0–1外围清理 |
| 范围外 | 互不信任tenant、法规防篡改、零人工恢复、Current业务实现、legacy cutover |
| 核心流程 | WP1-R1 checkpoint → Phase 2简化 → Phase 0–1简化 → 修订WP1-R2+ |
| 功能需求 | 最小Versioned create/upload/import/operation/ref/catalog/stream链路 |
| 非功能需求 | 简洁契约、普通CI、可重试主路径、罕见矛盾允许人工修复 |
| 核心数据/状态 | Repository/Artifact/Operation/Commit/Ref；Operation仅四态 |
| 规模/性能 | 未设高保障或极限性能目标；stream使用Arrow，避免JSON/base64和默认full readback |
| 一致性 | Versioned mutation使用CAS和幂等；无LWW、dual-write或cross-store consistency |
| 权限/安全 | 单一信任域、global bearer、deployment TLS、无per-repository ACL |
| 部署 | 独立内网Repository Service、single process、single durable-root owner |
| 外部依赖 | Dolt、SQLite/Pydantic/FastAPI/Arrow及部署入口；不新增policy/queue/audit服务 |
| 兼容/迁移 | WP1-R1无发布兼容承诺；后续contract允许破坏性替换 |
| 失败边界 | matching commit marker恢复；无marker重试一次；矛盾状态人工修复 |
| 已确认决策 | ADR 0009及本文第1节全部基线 |
| 已排除 | 完整旧Phase 2、generic dual-store、full evidence recovery、exact-commit release |
| 采用假设 | token持有者可信；少量人工恢复可接受；Current没有当前consumer |
| 延后事项 | Current、maintenance API、multi-node、额外provider/platform、对象存储 |
| 主要风险 | 新旧authority冲突、canonical回归、过早抽象、人工恢复入口缺失 |
| 验收 | T2/T3 exit criteria及ADR 0009 Required verification |

## 2. Execution sequence

```text
T0  Formalize proportional-assurance decision
  -> T1  Finish old-design WP1-R1 checkpoint
  -> T2  Simplify Phase 2 contracts and delivery skeleton
  -> T3  Simplify Phase 0–1
  -> T4  Resume revised Phase 2 at WP1-R2
```

不得在T2完成前开始旧计划WP1-R2，不得在T3完成前继续扩张Phase 2 conformance或
进入Phase 3 production implementation。

## 3. T0 — Document contract

状态：COMPLETE

工作：

- 新增ADR 0009，固定适度保障、可信内网、最小Versioned范围和过渡顺序。
- 在架构总纲加入全局设计原则和阶段插入点。
- 将旧Repository Service Contract、Phase 2 plan和ADR 0008标记为WP1-R1过渡
  authority。
- 保持当前machine-readable traceability内容不变，避免在WP1-R1完成前破坏旧gate；
  T2统一删除或替代。

退出条件：

- 正式文档不存在“WP1-R1必须立即按新contract返工”的歧义。
- WP1-R2+明确被新简化阶段阻断。
- 本文不被正式owner引用为wire或runtime authority。

## 4. T1 — WP1-R1 legacy checkpoint

状态：COMPLETE

允许完成的旧范围：

- public identity wrappers；
- closed enum和FailureDescriptor；
- strict JSON/wire version；
- custom stream envelope；
- packaged JSON Schema和snapshot tests。

Checkpoint要求：

- 当前WP1-R1 tests、lint和type checks通过；
- 工作区形成独立commit，commit message明确`legacy design checkpoint`；
- 不发布package、不声明wire v1稳定、不启动WP1-R2；
- 记录checkpoint SHA到本文状态表。

该checkpoint之后，上述实现均允许被T2破坏性重构。

## 5. T2 — Phase 2 simplification

状态：READY / T1 PASS

### T2.1 Delivery control cleanup

- 删除Phase 2 affected-scope router、gate attempt/closure aggregator、Phase 1
  protected-path检查和exact-commit evidence要求。
- 冻结并移除旧141项runtime traceability；新的普通CI只保留lint/type/unit、
  Repository integration和Backend→Repository e2e。
- 删除WP0作为长期product subsystem的地位；三package workspace保留。

### T2.2 Replace WP1-R1 contracts

- 保留`contracts <- client/service`依赖方向。
- 使用Pydantic DTO和FastAPI OpenAPI；删除custom strict JSON/deep-freeze、手写
  schema authority、schema snapshot hash和重复validator。
- Service-owned ID使用普通UUID；provider/idempotency token使用简单bounded string。
- Error收敛为`code/message/details?/request_id?`。
- 删除JSON/base64 stream envelope；Versioned stream直接使用Arrow IPC HTTP body。
- 公共route和DTO显式使用Versioned命名，给未来`/current/` sibling留出自然空间。

### T2.3 Replace remaining Phase 2 design

新的最小surface：

```text
CreateRepository
UploadArtifact
SubmitVersionedImport
GetOperation
ResolveVersionedRef
CompareAndSetVersionedRef
GetVersionedCatalog(commit_id)
StreamVersionedTableRows(commit_id)
healthz / readyz
```

固定策略：

- one global bearer token；无CallerIdentity、ACL或policy API；
- import package为`manifest.json + replay.sql`的固定tar+zstd；
- raw upload SHA + committed table/schema/row-count validation；
- 无verification level、LWW、LATEST binding或full row rehash；
- operation四态、request fingerprint、operation commit marker、最多一次自动恢复；
- 矛盾结果进入`MANUAL_RECOVERY_REQUIRED`；
- single durable-root owner和per-repository process-local writer lock。

明确延期：

- CurrentTableStore和cross-store inventory；
- Diff/Export/VerifyCommit/cursor；
- resource governance、typed audit subsystem；
- GC/backup/restore/repair/delete public API；
- exact-commit/container evidence体系。

### T2 exit

- 精简后的Architecture、Repository contract和Phase 2 plan成为唯一authority。
- 旧WP1-R2+ requirements和decision ledger不再被实现或CI引用。
- Contracts package测试覆盖新DTO/OpenAPI/Arrow/error边界，不保留旧compat测试。
- T2只完成架构、契约和交付骨架重构；不要求提前交付Repository业务纵切。

## 6. T3 — Phase 0–1 simplification

状态：PENDING / entry requires T2 PASS

### Keep unchanged

- JCS、typed scalar、identifier、row/collection framing的canonical bytes；
- canonical row hash及business content equality；
- Python/Rust核心实现和少量跨语言golden vectors；
- Backend基本compute、artifact round-trip和container smoke。

### Simplify

- `ArtifactRef`收敛为`id/logical_ref + size + raw_sha256 + media_type`。
- capability-owned result保存真正被业务使用的content/schema digest。
- 删除通用content contract、access metadata、retention class和重复schema binding。
- Artifact在写入/上传边界验证raw hash；普通读取不默认全量重新hash。

### Remove

- fixture/scenario closure digest和self-verifying manifest；
- run evidence、gate closure和phase-exit identity digest；
- exact-commit identity bundle、frozen-path protection和不可变attempt；
- 重复schema/runtime validator和大规模negative evidence matrix；
- 已被ADR 0009取代的临时decision ledger和sign-off材料；Git历史作为归档。

### T3 exit

- canonical核心golden bytes不变；
- Python/Rust核心mapping tests通过；
- Backend artifact round-trip和container smoke通过；
- CI不再需要closure digest、phase-exit identity、exact commit或冻结路径证明；
- 删除内容不再被正式文档、脚本或测试引用。

## 7. T4 — Resume revised Phase 2

状态：PENDING / entry requires T3 PASS

从重新定义的WP1-R2开始交付client/service composition和最小Versioned纵切。未来
CurrentTableStore只有在存在真实caller、操作集合、生命周期与验收场景时才新增
计划；它共享基础types和operation mechanism，但拥有独立generation、SQLite
adapter和Current-specific API。

## 8. Risks and controls

| Risk | Control |
| --- | --- |
| WP1-R1完成后立即返工造成浪费 | checkpoint只用于关闭进行中工作，不建立compat承诺；T2按已确认边界一次替换 |
| 新旧正式文档短期冲突 | ADR 0009拥有WP1-R2+过渡顺序；旧contract只拥有WP1-R1 |
| Phase 0–1清理改变业务结果 | canonical bytes/golden为硬验收；先T2定义consumer边界，再T3删除外围机制 |
| 简化后Current难扩展 | Versioned-specific route/types；共享最小table/Arrow types；additive layout version |
| 手工恢复被忽略 | 明确`MANUAL_RECOVERY_REQUIRED`错误、runbook入口和故障测试 |
| temporary计划再次成为authority | 不从formal contract引用执行细节；完成后删除本文 |

## 9. Status

| Stage | Status | Evidence |
| --- | --- | --- |
| T0 Document contract | COMPLETE | ADR 0009 + architecture/contract/plan transition |
| T1 WP1-R1 checkpoint | COMPLETE | implementation closure `361a56a`; verified checkpoint `ed8a69c` |
| T2 Phase 2 simplification | READY | T1 PASS; awaiting simplification baseline implementation |
| T3 Phase 0–1 simplification | PENDING | requires T2 |
| T4 Revised WP1-R2+ | PENDING | requires T3 |

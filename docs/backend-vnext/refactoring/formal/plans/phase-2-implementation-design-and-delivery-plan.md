# Phase 2 Implementation Design and Delivery Plan

状态：Accepted — Complete P2 Design

日期：2026-08-02

适用阶段：Phase 2 — Versioned Repository Service Foundation

Owner：Backend vNext Architecture（交付顺序、实施边界和验收）

Public/persisted语义：
[Repository Service Contract](../contracts/repository-service.md)

决策依据：
[ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)、
[ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)与
[DX Reconciliation](dx-cross-phase-interface-reconciliation.md)

完整实现设计与逐轮执行：
[P2 Versioned Repository Implementation Design](p2-versioned-repository-implementation-design.md)
和[P2 Execution Checklist](p2-versioned-repository-execution-checklist.md)

## 1. Goal and delivery boundary

Phase 2只交付当前Backend consumer需要的Dolt-backed Versioned repository，不再
建设generic dual-store、细粒度ACL、默认全量verification、通用maintenance或
exact-commit evidence体系。

本计划区分两个时段：

1. simplification：先闭合Phase 0–2简化设计，再联合清理现有代码和CI；
2. feature delivery：从新的最小Repository纵切开始实现真实业务能力。

Simplification不得提前注册stub route或把DTO声明为已经激活的wire。Feature route
只有在真实service behavior、client和integration test同时存在时才进入`/v1/`
OpenAPI。

## 2. Fixed topology

```text
gateway-repository-contracts
  <- gateway-repository-client

gateway-repository-contracts
  <- gateway-repository-service
```

- Backend只依赖contracts/client；
- Service不依赖client；
- Contracts不依赖HTTP、Dolt、filesystem或Backend业务module；
- 保留三个独立pyproject和lockfile；
- 删除Phase 2专用router/closure/attempt/traceability subsystem；
- 普通CI由各package lint、type和tests，以及真实integration/e2e组成。

## 3. Design-before-code sequence

为避免Phase 2先改contract、Phase 0–1随后又改artifact/canonical边界，代码清理前
先完成两阶段设计：

```text
D2  Phase 2 simplified baseline
  -> D01  Phase 0–1 proportional-assurance design
  -> DX  Cross-phase interface reconciliation
  -> S02  Combined Phase 0–2 code simplification
  -> P2  Revised Repository feature delivery
```

`D2`由本计划、Repository Service Contract和T2 checklist闭合。`D01`必须固定
Phase 0–1的KEEP/SIMPLIFY/REMOVE边界。`DX`只协调真正共享的ArtifactRef、
canonical package、digest owner、CI和package依赖，不重新打开已确认的Repository
信任、安全或恢复边界。

当前状态：`D2`、`D01`、`DX`与`S02`均已闭合；P2-R1 v8 formal 已通过，下一入口为
`P2-R2`。P2实现必须遵守DX确定的nominal ArtifactRef、package binding、依赖图与
ordinary CI，不恢复旧五提交清理计划。

联合代码清理仍使用小提交和独立checkpoint，不允许一次大爆炸提交。

## 4. Simplification work packages

### S02-R1 — Authority and reference cleanup

- 以ADR 0009、精简Repository contract和本计划替代旧WP1-R2+ authority；
- 旧141项traceability和F0 validation formal文件已删除；
- 旧temporary Phase 2 ledger只作为历史材料，不能被代码、CI或正式文档引用；
- cross-stage artifact、canonical owner与package依赖以DX plan为唯一实施映射。

Exit：全文搜索不存在仍要求旧dual-store、ACL、FULL verification或exact-exit的
有效实现指令。

### S02-R2 — Delivery-control removal

- 删除`vnext/conformance/phase2/`中的affected-scope router、gate、closure、
  Phase 1 protected-path检查、attempt/closure schema及其测试；
- 清除代码、CI和temporary索引对已删除Phase 2 requirement traceability/F0 report的
  运行时依赖与链接；
- 删除Phase 2专用gate/closure命令、脚本和CI引用；
- 保留DX已确认的128个canonical cases与Python/Rust owner tests。

Exit：普通package commands可以直接运行，不再生成immutable attempt、closure
digest或exact-candidate evidence。

### S02-R3 — Thin contracts replacement

- 将`gateway-repository-contracts`替换为Pydantic DTO、普通UUID、bounded opaque
  string、少量enum和简单error；
- 删除strict JSON/JCS、deep-freeze、FailureDescriptor、Current identity、
  StoreKind、custom stream envelope和packaged handwritten schemas；
- DTO只覆盖精简contract，不保留WP1-R1 compatibility adapter；
- T2不注册业务route、不生成OpenAPI snapshot。

Exit：contracts source和tests只表达当前Versioned语义，client/service仍可在独立
环境构建和import。

### S02-R4 — Cross-phase regression

- 执行contracts/client/service的ruff、mypy和pytest；
- 执行D01确定保留的Phase 0–1 canonical Python/Rust tests和少量golden；
- 执行Backend artifact round-trip和container smoke；
- 搜索旧gate、traceability、schema和custom wire引用；
- 记录已删除文件、保留能力和后续feature入口。

Exit：Phase 0–2代码简化形成一组可独立revert的提交，canonical业务结果不变。

具体revision名称、依赖闭合和每步验证以DX plan的`S02-C1..C5`为准；本节R1..R4
是scope grouping，不建立第二套提交顺序。五轮跨对话执行使用
[S02 Code Cleanup Execution Checklist](s02-code-cleanup-execution-checklist.md)。

## 5. Revised feature delivery

Simplification完成后，Phase 2按纵切交付，不恢复旧WP编号和37 revision计划。

### P2-R1 — Runtime and provider feasibility

- single durable-root lock；
- server-owned layout；
- Dolt init、initial commit、main ref、replay、commit marker和stream probe；
- filesystem staging、fsync和atomic rename；
- 真实负载下测量Dolt import耗时和增量存储。

本轮的component-first layout、target filesystem、offline CLI与sql-server matrix、
受控process boundary、workload、hard gate和simplicity-first selection统一由
[P2-R1 Runtime and Provider Feasibility Contract](p2-r1-runtime-provider-feasibility.md)
拥有。实现不得从旧temporary Phase 2 ledger恢复其他provider/layout规则。

当前状态：P2-R1 implementation、v8 formal measurement和审核已完成；默认 provider
为Candidate A offline CLI，Candidate B保留但默认禁用；P2-R2已授权。
P2-R1基线为source revision `80aff3e`，formal artifact commits `d7a0aa7`和`67a0d05`。

Exit：目标部署环境中create/import/read主机制可行。

### P2-R2 — Service shell and authentication

- FastAPI composition root；
- global bearer；
- healthz/readyz；
- simple settings、error mapping和request ID；
- SQLite control DB lifecycle与forward-only migration；
- 不注册stub业务route；只生成health/readiness OpenAPI；
- 不启动import worker pool（延至P2-R4）。

Exit：认证成功/失败、脱敏和service lifecycle integration通过。

### P2-R3 — Synchronous create and upload

- CreateRepository：staging初始化、initial commit/main、atomic publication和幂等；
- UploadArtifact：bounded streaming、size/SHA、atomic publication、response-loss幂等；
- 首次激活真实`/v1/` business OpenAPI；
- PENDING/SUCCEEDED minimal ledger与startup reconciliation；
- orphan/failed TTL和disk admission；
- 不建立create/upload operation。

Exit：真实HTTP create/upload与restart tests通过。

### P2-R4 — Async Versioned import

详细内部设计与按单次实现对话容量拆分的green stages见
[P2-R4 Async Versioned Import Detailed Implementation Design](p2-r4-async-versioned-import-implementation-design.md)
和
[P2-R4 Async Versioned Import Staged Execution Plan](p2-r4-async-versioned-import-execution-plan.md)。

- durable repository-scoped operation；
- global bounded worker pool和per-repository writer lock；
- expected commit同时作为parent和target ref mandatory CAS，private operation ref上先
  replay/verify再发布；
- caller-selected NONE/STRUCTURAL/FULL_SCAN（默认STRUCTURAL）与REJECT/STRINGIFY
  （默认REJECT）；
- operation commit marker、SQLite durable queue和受限一次自动恢复；
- 矛盾状态终止为MANUAL_RECOVERY_REQUIRED。

Exit：commit前中断、commit后响应丢失、CAS冲突和人工恢复分支通过。

### P2-R5 — Commit-pinned read

- ResolveVersionedRef；
- GetVersionedCatalog(commit_id)；
- raw Arrow IPC StreamVersionedTableRows(commit_id)；
- bounded RecordBatch streaming和disconnect cleanup。
- 完成Remote client与contract-owned fixture consumer；不提前设计Phase 3业务能力。
- 开始实现前必须复核并为execution checklist §7登记的Arrow mapping逐cell热路径、重复
  normalization、batch schema复用、catalog parent解析和P2-R1 v8 production retest处置形成
  明确实施计划；public row route不得先于该计划激活。

Exit：contract-owned fixture consumer通过Remote client完成upload → import → poll →
resolve → catalog/stream；不import或预设计Phase 3 capability。

从2026-08-09起，P2-R4 post-audit后续修复和R5采用execution checklist §1.1的container
gate合并规则：未触碰build/deployment boundary时，R5只跑完整功能、真实Dolt和非container
HTTP/client gate，production image build、镜像传输及compose内外client smoke延期到R6最终
候选一次执行。R5 handoff必须区分`validated_code_sha`与`container_validated_code_sha`并列出
延期nodeid；旧镜像不能证明新代码。触发checklist列明的Dockerfile、依赖闭包、Compose wiring
或container harness变更时，本轮立即恢复相应容器门禁。

### P2-R6 — Operational closure

- 成功package清理和manual-recovery保留；
- configurable upload/import concurrency和free-disk admission；
- deployment-level quiescent volume snapshot/restore runbook；
- 真实10–100 MB及至少一个接近200 MB package测量；
- 普通CI和container smoke。
- 开始实现前必须复核并为execution checklist §8登记的marker branch退化、dispatcher轮询与
  barrier查询、FULL_SCAN累计期限/容量、single-dispatcher并发不变量、dead helper及遗留
  production retest形成明确实施计划和逐项关闭证据。

Exit：已知consumer纵切、容量记录和人工恢复路径可执行。

R6同时拥有全部延期container gate。Phase 2退出前必须安排一次针对最终candidate的正式
production image构建与传输，验证其build context/provenance，运行无排除项的权威测试入口，
完成R4 restart/replay、R5 compose内外client链路和fresh/restart/restored Compose，并关闭
P2-R1 v8 `production_retest_required`。任一项失败都保持Phase 2 no-go，修复后必须对新的
最终candidate重跑受影响门禁；不能用R5以前的镜像证据替代。

P2-R1至R6全部exit后Phase 2才完成，并在此后开始Phase 3完整设计。Phase 3设计不与P2
实现穿插；R5 fixture consumer只是P2 contract test double，不是P3 capability设计。

## 6. Confirmed load and defaults

已确认：

- 通常10–100 MB/package，极端约200 MB；
- 日常10–200次/天，极端1,000次/天；
- 峰值分散在多个Repository，单Repository通常一周一次；
- 每次成功import形成永久Versioned commit；
- 数据大多重复、少量变化；
- package由外部系统按业务流程备份，不在Repository Service常驻。

初始实现建议采用256 MiB upload上限、8 concurrent uploads、4 import workers、
per-repository single writer和24小时orphan TTL。这些是可配置起点，不是wire
compatibility或SLO承诺。

## 7. Ordinary verification

每个真实纵切只维护与风险相称的测试：

- unit：DTO、idempotency、state transition和path/size边界；
- HTTP integration：auth、status、OpenAPI和stream；
- Dolt integration：initial commit、replay、marker、CAS、catalog和Arrow；
- failure：commit前中断、commit后response loss、ambiguous manual recovery；
- consumer e2e：Backend owner package到commit-pinned read；
- capacity：典型和极端package，不将未经测量的去重率写成保证。

不生成gate attempt、closure manifest、requirement coverage matrix、source-frozen
candidate或signature-like evidence。

## 8. Rollback and migration

- 当前没有已发布wire和production durable Repository，因此simplification允许
  破坏性删除；
- 每个S02 revision形成独立commit，可按文件边界revert；
- 首个durable layout在P2-R1之后才建立版本；
- 已成功的未来import不能由代码revert撤销，只能通过新的显式业务操作处理；
- 当前不提供legacy Repository migration。

## 9. Completion

Phase 2只有在P2-R1–R6真实纵切通过后才完成。S02完成只表示旧设计已清理、具备
按新计划实施的基础，不表示Repository业务能力已交付。

当前设计判定：整个P2 design complete；P2-R1 v8 exit=`go`，P2-R2已授权并进入实施入口，
P2-R3–R6仍按顺序受前序 round gate约束。P2-R6通过前不得宣称Phase 2 implementation
complete。

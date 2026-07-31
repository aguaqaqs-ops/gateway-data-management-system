# T2 Phase 2 Simplification Implementation Checklist

状态：READY FOR CROSS-PHASE DESIGN / CODE EXECUTION BLOCKED

日期：2026-07-31

正式语义：

- [ADR 0009](../../formal/adr/0009-proportional-assurance-and-trusted-internal-repository.md)
- [Repository Service Contract](../../formal/contracts/repository-service.md)
- [Phase 2 Implementation Plan](../../formal/plans/phase-2-implementation-design-and-delivery-plan.md)

本清单只协调实施，不拥有public、persisted或wire语义。Phase 0–1同原则简化设计及
cross-phase reconciliation完成前，不执行代码删除。

## 1. Entry

- [x] WP1-R1 legacy checkpoint已完成并提交。
- [x] Proportional assurance原则已由ADR 0009接受。
- [x] T2 `$grill-me`需求和设计访谈已收敛。
- [x] Versioned trust、API、容量、artifact和灾难恢复边界已确认。
- [x] 精简Repository contract和Phase 2 plan已发布。
- [ ] Phase 0–1同原则简化设计完成。
- [ ] ArtifactRef、canonical package、digest owner和CI边界完成cross-phase核对。
- [ ] 联合代码简化开始前工作区干净并记录baseline commit。

## 2. Confirmed KEEP

- [ ] 三个独立distribution及`contracts <- client/service`依赖方向。
- [ ] Repository Service独立内网进程。
- [ ] Pydantic DTO和未来FastAPI OpenAPI。
- [ ] 普通UUID、bounded opaque token和简单error。
- [ ] Dolt Versioned commit/ref/import/catalog。
- [ ] Raw Arrow IPC HTTP stream。
- [ ] Upload size/raw SHA验证和安全package path。
- [ ] Import CAS、idempotency、operation marker和一次自动恢复。
- [ ] Single durable-root lock和per-repository process-local writer lock。
- [ ] Phase 0–1 canonical bytes、Python/Rust核心和少量业务golden。

## 3. Confirmed REMOVE

### Delivery control

- [ ] 删除`vnext/conformance/phase2/router.py`。
- [ ] 删除`vnext/conformance/phase2/gate.py`。
- [ ] 删除`vnext/conformance/phase2/closure.py`。
- [ ] 删除`vnext/conformance/phase2/phase1_protection.py`。
- [ ] 删除`vnext/conformance/phase2/affected-scope-v1.yaml`。
- [ ] 删除`vnext/conformance/phase2/schemas/`。
- [ ] 删除`vnext/conformance/phase2/tests/`。
- [ ] 删除Phase 2专用CLI、script、CI和package引用。
- [ ] 删除旧requirement traceability YAML和F0 validation report。

### WP1-R1 contract

- [ ] 删除custom strict JSON/JCS实现。
- [ ] 删除deep-freeze/materialize JSON tree。
- [ ] 删除自定义wire version parser和schema loader。
- [ ] 删除FailureCategory、RecoveryAction和EffectClassification。
- [ ] 删除FailureDescriptor和复杂problem scan。
- [ ] 删除StoreKind和Current-specific identity/metadata。
- [ ] 删除UUIDv7和每类identity wrapper。
- [ ] 删除custom stream frame/envelope/checkpoint/end-hash。
- [ ] 删除手写JSON Schema和snapshot/hash tests。
- [ ] 删除只验证上述旧机制的property/negative/round-trip tests。

### Old feature scope

- [ ] 不保留CallerIdentity、ACL、policy API或存在性隐藏。
- [ ] 不保留CurrentTableStore占位DTO或route。
- [ ] 不保留verification level、LWW或LATEST read binding。
- [ ] 不保留standalone CompareAndSetVersionedRef。
- [ ] 不保留Diff/Export/VerifyCommit/cursor。
- [ ] 不保留public GC/backup/restore/delete/repair。
- [ ] 不保留lease、fencing、ServiceEpoch或UNKNOWN/APPLIED/VERIFIED状态机。

## 4. Thin contracts target

- [ ] 增加Pydantic runtime dependency并更新contracts lockfile。
- [ ] 定义Repository、ArtifactRef、Operation、VersionedImportResult和Catalog DTO。
- [ ] ID使用`uuid.UUID`，CommitId/ref/idempotency使用bounded string。
- [ ] Error固定为`code/message/details?/request_id?`。
- [ ] Operation status只包含QUEUED/RUNNING/SUCCEEDED/FAILED。
- [ ] Create request/result表达initial commit和default main。
- [ ] Upload metadata表达media type、declared size、raw SHA和idempotency key。
- [ ] Import request表达artifact、target ref、expected commit和idempotency key。
- [ ] `expected_commit_id`同时表达parent和CAS预期。
- [ ] Read DTO只接受explicit CommitId。
- [ ] Arrow stream不进入JSON DTO或自定义frame类型。
- [ ] 不创建stub FastAPI业务route或OpenAPI snapshot。

## 5. Package and test cleanup

- [ ] 保持repository workspace inventory与三包独立lock。
- [ ] Client和Service在各自隔离环境中可import。
- [ ] Backend production仍不能依赖/import Service。
- [ ] 删除只为旧conformance提供的dev dependency。
- [ ] Contracts tests聚焦Pydantic validation、ID、error和DTO round-trip。
- [ ] Service tests保留settings和distribution boundary。
- [ ] Phase 0–1 design裁决Repository端shared-kernel vector consumer是否保留。

## 6. Cross-phase coordination

- [ ] Phase 0–1明确ArtifactRef最小字段并与Upload ArtifactRef一致。
- [ ] Phase 0–1明确raw SHA与业务content digest的不同owner。
- [ ] Canonical import package owner只生成`manifest.json + replay.sql`。
- [ ] Repository structural check所需table/schema/row-count字段由package owner提供。
- [ ] 外部package backup不进入Repository Service接口。
- [ ] 删除共享closure/evidence代码时不改变canonical encoding bytes。
- [ ] 保留的Python/Rust golden集合在联合清理前后逐字节一致。

## 7. Combined code execution batches

每批独立commit并在合入下一批前运行对应测试：

- [ ] `C0`：记录clean baseline、保留测试和删除清单。
- [ ] `C1`：删除旧Phase 2 delivery-control和traceability引用。
- [ ] `C2`：按Phase 0–1设计删除共享closure/evidence外围。
- [ ] `C3`：破坏性替换Repository contracts和tests。
- [ ] `C4`：清理workspace dependencies、locks、scripts和文档引用。
- [ ] `C5`：运行Phase 0–2联合回归并修正遗漏，不增加新业务feature。

`C1–C4`可以在同一工作阶段连续执行，但不能压成一个不可审查commit。

## 8. Verification commands

实际命令在Phase 0–1设计闭合后按保留的package入口填写。最低要求：

- [ ] `git diff --check`。
- [ ] contracts ruff、mypy、pytest。
- [ ] client ruff、mypy、pytest。
- [ ] service ruff、mypy、pytest。
- [ ] 保留的Phase 0–1 Python canonical tests。
- [ ] 保留的Rust canonical tests。
- [ ] Backend artifact round-trip。
- [ ] Backend container smoke。
- [ ] `rg`确认无旧gate/closure/traceability/custom wire引用。

不得继续调用将被删除的Phase 2 closure作为新设计验收authority。

## 9. Exit

- [ ] 正式文档只有一套有效Repository语义。
- [ ] 旧WP1-R1 checkpoint只存在于Git历史和明确的historical材料中。
- [ ] 代码、CI和正式文档不引用141项旧traceability。
- [ ] Phase 0–1 canonical业务结果未改变。
- [ ] Repository contracts已缩减为新DTO骨架。
- [ ] 工作区形成按批次可回滚的commits。
- [ ] 尚未实现的业务route未advertise。
- [ ] 可以按修订后的P2-R1开始真实Repository feature delivery。

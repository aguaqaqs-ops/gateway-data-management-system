# Phase 2 Round 11 Convergence and Consolidated-Review Readiness Scan

状态：**Resolved / Round 11 confirmed / Consolidated Review pending**

日期：2026-07-30

本文件是临时readiness evidence，不拥有semantic decision，也不替代
Consolidated Design Review、formal plan或blocking register。Decision语义仍以
三个Decision Ledger为准。

## 1. Scan scope and evidence

本次扫描覆盖：

- Round 0–11全部Decision Ledger；
- Guide的Round 11交付要求与Consolidated Design Review 12项检查；
- WP0–WP9、37个R、gate/evidence/rollback及exact-commit exit主线；
- public action到WP的完整性；
- 已知formal冲突及其supersession owner；
- Phase 1 protected identity/locks/vectors/golden/scenario边界。

机械检查结果：

- `146`个Decision ID，全部唯一；
- `139 ACCEPTED / 7 SUPERSEDED`；
- 无blocking `OPEN`、`DEFERRED`或`REJECTED`；
- 每个decision均具有ID、Topic、Status、Decision、Rationale、
  Rejected alternatives、Constraints、Downstream impact、Formal owner和
  Reopen condition。

## 2. Readiness result

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| Accepted decision内部兼容 | PASS | Caller-selected rigor不降低auth、input safety、effect identity、journal、fencing或reconciliation。 |
| API、identity、data model闭合 | AMENDMENT | `GetRepositoryPolicy/UpdateRepositoryPolicy`已有语义但尚未显式分配到WP/R。 |
| Read/write/recovery identity一致 | PASS | CommitId、Current generation、RepositoryIncarnationId、OperationRef、ArtifactRef分别拥有closed binding。 |
| Journal/lease/idempotency/concurrency空窗 | PASS | Create使用global lifecycle journal；Current和Versioned store marker随真实mutation激活；UNKNOWN禁止blind replay。 |
| Fake/Local/Remote equivalence | PASS | Local只绕过transport/authentication parsing，不绕过application policy/effect path。 |
| Path或业务语义泄漏 | PASS | Public contract不暴露path/provider，也不含Workspace/Submission/Archive等业务概念。 |
| Container/restart recovery | PASS | Root lock、ServiceEpoch、repository-scoped runtime、incremental reconciliation和exact provider identity有owner。 |
| Gate/exit coverage | PASS | Static/Contract/Recovery/Container四类唯一owner，required coverage、fault receipt和immutable attempt均有closure。 |
| Phase 3/4/5越界 | PASS | 只有两处Phase 3 design handoff；Phase 3 implementation等待Phase 2 exit。 |
| Owner/formal冲突 | PASS WITH REQUIRED SUPERSESSION | 冲突集合已知且必须在F0一次性消除，见§4。 |
| Deferred/non-goal | PASS | 没有blocking deferred；future provider/platform/resumable upload等均有reopen condition。 |
| Implementation-plan materialization | AMENDMENT | 语义/R/gate已闭合，但formal plan仍需固定physical module/test/evidence owner和per-WP forbidden-content map。 |

## 3. Accepted closure amendments

### A1 — Policy surface assignment

`P2-R11-D25`已确认把以下能力加入`WP4-R3`，与Repository lifecycle首次公开
同时激活：

- `GetRepositoryPolicy`；
- `UpdateRepositoryPolicy`；
- `POLICY_READ/POLICY_WRITE` action；
- expected policy generation、idempotency及同control-SQLite transaction；
- 401/403/404、cache generation和Local/Remote authorization coverage。

它复用WP3已建立的ACL authority，不新增WP或R，也不把policy变成通用engine。

### A2 — Physical ownership and forbidden-content map

`P2-R11-D26`已确认正式Phase 2 implementation plan必须按以下owner
materialize exact
file/module/test/evidence清单；文件可在实现前按仓库实际命名细化，但依赖方向不得
改变：

| WP | Production/module owner | Test/evidence owner | 禁止混入 |
| --- | --- | --- | --- |
| WP0 | workspace、locks、architecture/gate routing | static/router/closure evidence | feature route、durable schema、provider capability |
| WP1 | contracts、client transport、service composition/auth | schema snapshot、Fake/Local/Remote service cells | repository storage/data route、完整v1 stub surface |
| WP2 | Dolt/SQLite/filesystem feasibility adapters | permanent provider probes与identity evidence | public capability、generic provider framework、numeric claim |
| WP3 | storage layout、registry、control、ACL/accounting adapters | filesystem/SQLite/Dolt publication fixtures | public lifecycle route、business semantics |
| WP4 | operations、create lifecycle、policy、artifact transfer | create/policy/artifact Contract/Recovery cells | Current/Versioned data mutation、monitoring platform |
| WP5 | Current storage/application/transport | Current transaction/stream/bulk/export evidence | Dolt/ref mutation、cross-store transaction |
| WP6 | Dolt runtime/versioned read/stream/diff/export | pinned-read/backpressure/restart evidence | public write/ref effect |
| WP7 | ref/import/verification/inventory | write/ref/verification crash evidence | business submit/archive workflow、dual-write |
| WP8 | retention/GC/backup/restore/delete/repair | destructive lifecycle/recovery evidence | service-owned cron、multi-node writer、rollback fiction |
| WP9 | observability/security/deploy/compatibility/release | full gate/identity/container/sign-off evidence | new product capability；R4 source mutation |

每个formal WP/R block必须显式列出goal、scope、non-goals、prerequisites、
contract/schema/API delta、files/modules、fixtures/tests、required gate、evidence、
rollback、entry/exit及禁止混入内容。

## 4. Formal supersession register

F0不得只修改Phase 2 plan；必须由semantic owner一次性处理：

1. FULL-only `VERIFIED`与SnapshotManifest要求
   → caller-selected `NONE | STRUCTURAL | FULL`及level-specific evidence；
2. CAS/expected-only mutable publication
   → explicit `CHECK_EXPECTED | LAST_WRITE_WINS`；
3. exact-only read
   → explicit `EXACT | LATEST_AT_START`并返回resolved binding；
4. verification mismatch一律保持APPLIED占用/attention/quarantine
   → ordinary`FAILED + effect=APPLIED`、持久failure evidence后释放Repository
   mutation lane；authority contradiction仍quarantine；
5. full-readback-only performance eligibility
   → 按verification level分离measurement series。

至少同步检查canonical-storage、external-effect/recovery、architecture、
implementation stages、performance baseline、Phase 2 exit/T3 consumer和必要ADR。

## 5. Protected and deferred boundaries

- 当前tracked变化只涉及`docs/backend-vnext/refactoring/temporary/README.md`；
  Phase 2工作目录仍是untracked temporary design material。
- 未修改Phase 1 source/runtime/image identity、locks、vectors、golden、scenario或
  sign-off。
- Exact driver、batch size、SQLite statement shape、compression参数、capacity
  数值和具体告警阈值是implementation/measurement detail，不阻塞架构确认。
- Legacy repository migration、第二provider、multi-node writer、resumable upload、
  hard tenant isolation及service-owned audit retention保持future/non-goal。

## 6. Readiness conclusion

A1、A2已通过`P2-R11-D25/D26`接受。没有剩余会改变Phase 2核心架构、WP依赖、
public data model、recovery boundary或exact-exit模型的问题。

1. Round 11已明确确认；
2. Session State已进入`CONSOLIDATING / Consolidated Review ready to start`；
3. 下一步是输出完整但仍可修改的Consolidated Design Review；
4. 未得到“整体设计确认，可以 formalize”前仍不得修改formal authority或实现代码。

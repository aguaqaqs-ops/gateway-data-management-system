# P3 Active Context Index

状态：Accepted P3 design entry（`phase_2_complete: yes`；P3 design complete；P3-R1 gate pass；P3-R2 gate pass；P3-R3 gate pass；P3-R4 gate pass）

日期：2026-08-20

Owner：Backend vNext Architecture

本文是 Phase 3 设计的**默认入口**。它只组织检索边界，不拥有 wire、字段、状态机或
错误矩阵。精确语义由 [P3 Capability Foundation Design](p3-capability-foundation-design.md)
及其列出的 normative owner 拥有。不得把本文当作 capability contract，也不得直接开始
P3 实现，除非另有 implementation authorization。

上游身份：[P2 External Interface Handoff](p2-external-interface-handoff.md)
清理动作：[P2–P3 Cleanup Manifest](p2-p3-cleanup-manifest.yaml)
阶段顺序：[Implementation Stages §6 Phase 3](implementation-stages.md#6-phase-3capability-foundation)

```yaml
phase_2_complete: yes
p3_design_started: yes
p3_design_status: accepted
p3_r1_exit: pass
p3_r2_ready: yes
p3_r2_detail_plan: p3-r2-table-access-parser-execution-plan.md
p3_r2_detail_plan_status: accepted_for_execution
p3_r2_s0: completed
p3_r2_s0_record: p3-r2-s0-entry-and-budget-freeze.md
p3_r2_s1: completed
p3_r2_s2: completed
p3_r2_s3: completed
p3_r2_s4: completed
p3_r2_s4_review: p3-r2-table-access-parser-execution-plan.md#8-s4-focused-review-record
p3_r2_s6: completed
p3_r2_s6_review: p3-r2-table-access-parser-execution-plan.md#9-s6-independent-review-record
p3_r2_s7: completed
p3_r2_s7_handoff: p3-r2-table-access-parser-handoff.md
p3_r2_exit: pass
p3_r3_ready: yes
p3_r3_detail_plan: p3-r3-source-materialization-execution-plan.md
p3_r3_detail_plan_status: accepted_for_execution
p3_r3_s0: completed
p3_r3_s0_record: p3-r3-s0-entry-and-budget-freeze.md
p3_r3_s1: completed
p3_r3_s2: completed
p3_r3_s3: completed
p3_r3_s4: completed
p3_r3_s5: completed
p3_r3_s6: completed
p3_r3_s6_review: p3-r3-s6-focused-review.md
p3_r3_s7: completed
p3_r3_s7_review: p3-r3-s7-independent-review.md
p3_r3_s8: completed
p3_r3_s8_handoff: p3-r3-source-materialization-handoff.md
p3_r3_exit: pass
p3_r4_ready: yes
p3_r4_design: p3-r4-storage-projection-design.md
p3_r4_detail_plan: p3-r4-storage-projection-execution-plan.md
p3_r4_detail_plan_status: accepted_for_staged_planning
p3_r4_s0: completed
p3_r4_s0_record: p3-r4-s0-entry-and-budget-freeze.md
p3_r4_s1: completed
p3_r4_s2: completed
p3_r4_s3: completed
p3_r4_s4: completed
p3_r4_s5: completed
p3_r4_s6: completed
p3_r4_s6_review: p3-r4-s6-focused-review.md
p3_r4_s7: completed
p3_r4_s7_review: p3-r4-s7-independent-review.md
p3_r4_s8: completed
p3_r4_s8_handoff: p3-r4-storage-projection-handoff.md
p3_r4_exit: pass
p3_r5_ready: yes
p3_implementation_authorized: no
default_retrieval: this_index
public_semantics_changed_in_c2: no
cleanup_status: pass
p3_context_ready: yes
final_cleanup_tag: docs/p2-p3-cleanup-final-20260817
cleanup_commit: this_cleanup_commit
```

## 1. 默认从这里开始

按这个顺序读。不要从 `temporary/`、decision ledger、阶段 execution plan 或
`vnext/repository_service/README.md` 的状态行开始。

1. 本 index。
2. [P2 External Interface Handoff](p2-external-interface-handoff.md)：封印
   candidate/image、支持面、限制、non-goals、reopen、archive 引用。
3. [Repository Service Contract](../contracts/repository-service.md) 及其直接引用：
   [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)、
   [External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
   [Shared Canonical Encoding](../contracts/shared-canonical-encoding.md)。
4. [Architecture Plan](../architecture/architecture-and-refactoring-plan.md) 与
   [Implementation Stages](implementation-stages.md)（阶段语义；状态散文以本 index
   和 P2 handoff 为准）。
5. [P3 Capability Foundation Design](p3-capability-foundation-design.md) 及其
   [Storage Mutation and Change Set](../contracts/storage-mutation-and-change-set.md)、
   [External Target Sync and Recovery](../contracts/external-target-sync-and-recovery.md)、
   [Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
   [Ruleset Activation and Migration](../contracts/ruleset-activation-and-migration.md)。
6. [P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)：
   R1-R7、滚动 S 级步骤、审核/门禁、独立测试、staging artifact 和 benchmark 规则。
7. [P3-R1 Capability Foundation Handoff](p3-r1-capability-foundation-handoff.md)：R1 gate /
   历史 R2 entry。稳定 owner/import 边界、staging helper、no-open-blocker。
8. [P3-R2 Table Access and Parser Handoff](p3-r2-table-access-parser-handoff.md)：R2 gate /
   R3 entry。稳定 descriptor/reader/diagnostic 边界、budgets、deferred register。
   不授权 source materialization。
9. [P3-R2 Table Access and Parser Execution Plan](p3-r2-table-access-parser-execution-plan.md)：
   R2 的 SQL/XML parser、bounded reader、diagnostics、对话上下文和 S4/S6/S7 记录。
10. [P3-R2-S0 Entry, Applicability and Budget Freeze](p3-r2-s0-entry-and-budget-freeze.md)：
    R2 入口适用性、ADR 0013 双边界、SQL allowlist、known types、XML security、
    numeric budgets 与 fixture roots。
11. [P3-R3 Source Materialization and Snapshot Handoff](p3-r3-source-materialization-handoff.md)：
    R3 gate / R4 entry。稳定 Snapshot/Artifact public boundary、digest ownership、
    deferred register。不授权 storage projection。
12. [P3-R3 Source Materialization and Snapshot Execution Plan](p3-r3-source-materialization-execution-plan.md)：
    R3 detail plan；SourcePackage、SQL/XML business materialization、RepositoryRef、artifact/cache、
    review conversation 和 S8 gate 记录。
13. [P3-R3-S0 Entry, Applicability and Budget Freeze](p3-r3-s0-entry-and-budget-freeze.md)：
    R3 入口适用性、package/zstd 范围、owner DAG、budgets、result/trust、allowlist 与 reopen。
14. [P3-R3-S6 Focused Contract, Resource and Security Review](p3-r3-s6-focused-review.md)：
    SourcePackage/archive/resource/security findings closure、exact reruns 与 S7 carry-forward。
15. [P3-R3 S7 Independent Owner, Import, Digest and Recovery Review](p3-r3-s7-independent-review.md)：
    独立 owner/import/digest/recovery 复核与 S8 carry-forward。
16. 运行约束：[ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)、
   [ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)、
   [Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)、
   [Testing Conventions](../../../testing-conventions.md)、
   [AGENTS.md](../../../../../AGENTS.md)。

17. [P3-R4 Storage Projection Design Baseline](p3-r4-storage-projection-design.md)：legacy
    rule-resolution parity、ignored-column canonical drops、StorageRuleView、canonical key/schema、
    ordered identity 和 manifest/package boundary。
18. [P3-R4 Storage Projection Execution Plan](p3-r4-storage-projection-execution-plan.md)：
    R4 S0-S8 steps、legacy matrix、tests/reviews、对话上下文策略和 R5 handoff。
19. [P3-R4-S0 Entry, Applicability, Legacy Matrix and Budget Freeze](p3-r4-s0-entry-and-budget-freeze.md)：
    R4 入口适用性、完整 legacy 矩阵、ignored→storage 派生、ruleset identity、
    budgets、allowlist 与 reopen。S5 manifest/import publication complete；S6 focused review
    complete；S7 independent review complete；S8 module gate complete。
20. [P3-R4-S6 Focused Contract, Resource and Security Review](p3-r4-s6-focused-review.md)：
    R4 focused findings closure and exact reruns。
21. [P3-R4 S7 Independent Owner, Import, Digest and Recovery Review](p3-r4-s7-independent-review.md)：
    R4 independent owner/import/digest/recovery pass and S8 carry-forward。
22. [P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)：
    R4 gate / R5 entry。稳定 public projection/artifact boundary、digest ownership、
    deferred register。不授权 comparison projection。

ENUM/SET 语义：[ADR 0013](../adr/0013-enum-set-v1-import-semantics.md)（P3-R2-S0 已修订
source dump / repository import 双边界）。
Fixture 材料：[Fixture Oracle](../contracts/fixture-oracle-and-conformance.md)、
[Testing Fixtures](../../../testing-fixtures.md)。
术语：[glossary](../../../glossary.md)。

## 2. Wire 与 Client

HTTP wire authority 是激活 route 生成的 FastAPI OpenAPI，加上
[Repository Service Contract](../contracts/repository-service.md) 的语义。
生成入口：

`vnext/repository_service/src/gateway_repository_service/http/openapi.py`

不要手写第二份 schema，也不要在摘要里复制字段表。

### 2.1 已激活 V1 surface

权威在 contract §6。当前 7 条业务 route 加 health：

```text
POST /v1/repositories
POST /v1/repositories/{repository_id}/artifacts
POST /v1/repositories/{repository_id}/versioned/imports
GET  /v1/repositories/{repository_id}/operations/{operation_id}
GET  /v1/repositories/{repository_id}/versioned/refs/{ref_name}
GET  /v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog
GET  /v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows?table_name=...
GET  /healthz
GET  /readyz
```

认证、容量、错误映射和未激活能力见 contract §3–§4 与 P2 handoff，不在此重述。

### 2.2 Repository Client（docs-only）

包：`vnext/repository_client`（distribution `gateway-repository-client`）。
**没有** `vnext/repository_client/README.md`。本计划不得在 `vnext/` 创建它。
本小节只列出稳定入口，语义仍由 contract 与 client 源码拥有。

- 公共类型：`RepositoryClient`（`gateway_repository_client.client`）。
- 方法：`create_repository`、`upload_artifact`、`submit_versioned_import`、
  `get_operation`、`wait_operation`、`resolve_versioned_ref`、
  `get_versioned_catalog`、`stream_versioned_table_rows`。
- 认证：构造参数 `bearer_token`；请求带 `Authorization: Bearer …`。
- Upload：`RewindableBody` 可重试；`NonRewindableBody` 只发送一次。
- 幂等重试：`retry_idempotent_request`；retryable HTTP 为 `502/503`。
- 依赖：`gateway-repository-contracts`。Backend 不 import
  `gateway-repository-service`。
- 可执行入口：`vnext/repository_client/tests/`；全量脚本
  `vnext/scripts/run-tests.sh`。

## 3. 不是默认上下文

以下材料**不要**当作 P3 默认规则。需要时走 handoff / manifest / Git tag。

| 材料 | 原因 |
| --- | --- |
| `vnext/repository_service/README.md` 状态行 | 冻结在 P2-R5；不是 `phase_2_complete` authority |
| `temporary/` 执行记录、review、attempt | 过程证据；已归档到 pre-cleanup tag |
| decision ledger Round 0–11 | 过期 ACCEPTED 与现行 RS contract 冲突 |
| 各轮 execution/design plan 正文 | 完成后过程文档；reopen/限制已抽到 P2 handoff |
| 旧 `docs/backend-vnext/contracts/` 当作 RS wire | Architecture 已降为 oracle |

## 4. P3 capability 设计 oracle（非 RS 默认入口）

Phase 3 是 Capability Foundation。Snapshot / Comparison / Risk / Flow 的既有语义仍可
从这些 oracle 发现行为；新 mutation、external target、lifecycle/integrity 和 ruleset
语义已经由 P3 formal contracts 拥有，冲突以 owning contract 和 Architecture Plan 为准：

- [flows](../../../flows.md)、[operations](../../../operations.md)、
  [artifacts](../../../artifacts.md)、[modules](../../../modules.md)
- [docs/backend-vnext/contracts/](../../../contracts/)
- [docs/backend-vnext/capabilities/](../../../capabilities/)
- [docs/backend-vnext/adr/](../../../adr/)

完整路径表见 [cleanup manifest](p2-p3-cleanup-manifest.yaml) 的
`paths.retain_oracle`。

## 5. Allowlist / 排除

P3 默认 allowlist（设计检索，不是源码扫描）：

- 本 index、P2 handoff、P3-R1 capability foundation handoff、P3-R2 table access
  parser handoff、P3-R3 source materialization handoff、P3-R3 source materialization
  execution plan、P3-R3-S0 freeze、P3-R4 storage projection design、P3-R4 storage
  projection execution plan、P3-R4-S0 freeze、P3-R4 storage projection handoff、cleanup manifest
- `docs/backend-vnext/refactoring/formal/contracts/` 中现行 contract（不含已
  superseded 的 vector-schema）
- `docs/backend-vnext/refactoring/formal/adr/0001-0005`、`0009`、`0010`、`0012`、`0013`、
  `0014`、`0015`、`0016`
- `formal/architecture/`、`formal/policies/`、`formal/plans/implementation-stages.md`、
  `formal/plans/dx-cross-phase-interface-reconciliation.md`
- `docs/backend-vnext/testing-conventions.md`、`testing-fixtures.md`、`glossary.md`
- `AGENTS.md`

默认排除：

- `docs/backend-vnext/refactoring/temporary/`（除因
  `vnext/deploy/p2r1-cache/README.md` 唯一指针而保留的
  `p2-r9-s2-step-e-container-gate.md`）
- 已完成的 formal execution/design plan、v8 archive、decision ledger、`notes/`、
  `dolt-test/`（走 pre-cleanup tag 与 manifest）
- 源码树、fixture payload、lockfile、OpenAPI 生成物的手写副本
- 已完成 gate 的 raw logs / JSON summary（走 manifest 与外部 audit root）

pytest 仍读取
[P2-R1 runtime-provider feasibility](p2-r1-runtime-provider-feasibility.md)
的 methodology version 字符串；该路径必须保持稳定，但不是 P3 设计入口。

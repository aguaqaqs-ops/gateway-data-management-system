# P3 Active Context Index

状态：Accepted for P3 design entry（`phase_2_complete: yes`；P3 design plan 尚未开始）

日期：2026-08-17

Owner：Backend vNext Architecture

本文是 Phase 3 设计的**默认入口**。它只组织检索边界，不拥有 wire、字段、状态机或
错误矩阵。精确语义仍由下列 normative owner 拥有。尚未存在单独的 P3 design plan；
不得把本文当作 capability contract，也不得直接开始 P3-R1 实现。

上游身份：[P2 External Interface Handoff](p2-external-interface-handoff.md)
清理动作：[P2–P3 Cleanup Manifest](p2-p3-cleanup-manifest.yaml)
阶段顺序：[Implementation Stages §6 Phase 3](implementation-stages.md#6-phase-3capability-foundation)

```yaml
phase_2_complete: yes
p3_design_started: no
p3_implementation_authorized: no
default_retrieval: this_index
public_semantics_changed_in_c2: no
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
5. 运行约束：[ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)、
   [ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)、
   [Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)、
   [Testing Conventions](../../../testing-conventions.md)、
   [AGENTS.md](../../../../../AGENTS.md)。

ENUM/SET 语义：[ADR 0013](../adr/0013-enum-set-v1-import-semantics.md)。
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
| `temporary/` 执行记录、review、attempt | 过程证据；C4 归档 |
| decision ledger Round 0–11 | 过期 ACCEPTED 与现行 RS contract 冲突 |
| 各轮 execution/design plan 正文 | 完成后过程文档；reopen/限制已抽到 P2 handoff |
| 旧 `docs/backend-vnext/contracts/` 当作 RS wire | Architecture 已降为 oracle |

## 4. P3 capability 设计 oracle（非 RS 默认入口）

Phase 3 是 Capability Foundation。Snapshot / Comparison / Risk / Flow 等业务语义
尚未进入 `refactoring/formal/contracts`。需要时从这些 oracle 发现行为，冲突以
Architecture Plan 与未来 P3 owning contract 为准：

- [flows](../../../flows.md)、[operations](../../../operations.md)、
  [artifacts](../../../artifacts.md)、[modules](../../../modules.md)
- [docs/backend-vnext/contracts/](../../../contracts/)
- [docs/backend-vnext/capabilities/](../../../capabilities/)
- [docs/backend-vnext/adr/](../../../adr/)

完整路径表见 [C1 classification](../../temporary/docs-lifecycle-cleanup-c1-classification.md)
的 `retain_oracle`。C4 不得删除这些路径。

## 5. Allowlist / 排除

P3 默认 allowlist（设计检索，不是源码扫描）：

- 本 index、P2 handoff、cleanup manifest
- `docs/backend-vnext/refactoring/formal/contracts/` 中现行 contract（不含已
  superseded 的 vector-schema）
- `docs/backend-vnext/refactoring/formal/adr/0001-0005`、`0009`、`0010`、`0012`、`0013`
- `formal/architecture/`、`formal/policies/`、`formal/plans/implementation-stages.md`、
  `formal/plans/dx-cross-phase-interface-reconciliation.md`
- `docs/backend-vnext/testing-conventions.md`、`testing-fixtures.md`、`glossary.md`
- `AGENTS.md`

默认排除：

- `docs/backend-vnext/refactoring/temporary/`（除 C4 完成前仍需的 cleanup 过程文件）
- 源码树、fixture payload、lockfile、OpenAPI 生成物的手写副本
- 已完成 gate 的 raw logs / JSON summary（走 manifest 与外部 audit root）

pytest 仍读取
[P2-R1 runtime-provider feasibility](p2-r1-runtime-provider-feasibility.md)
的 methodology version 字符串；该路径必须保持稳定，但不是 P3 设计入口。

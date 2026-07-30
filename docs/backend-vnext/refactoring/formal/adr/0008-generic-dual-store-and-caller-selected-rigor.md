# ADR 0008: Generic Dual-Store Repository and Caller-Selected Rigor

状态：Accepted

日期：2026-07-30

决策 owner：Repository Service Architecture

关联阶段：Phase 2及后续Repository consumers

## Context

Repository consumer既有需要版本历史的table，也有只保存latest state的table。
同时，不同caller对content verification、lost-update protection和read freshness的
成本/严谨度需求不同。若Repository Service自动判断store authority、强制所有请求
使用最高成本policy，或把宽松路径实现为旁路，会扩大业务耦合并产生两套recovery
语义。

## Decision

Repository Service在同一RepositoryId下提供相互独立的Dolt-backed
`VersionedTableStore`和SQLite-backed`CurrentTableStore`。Caller显式选择store；
Service不拥有table persistence policy、不自动routing、不提供dual-write或cross-store
consistency。同名table可以独立存在于两侧。

Caller还必须显式选择：

- async content write的`NONE | STRUCTURAL | FULL` verification；
- mutable write的`CHECK_EXPECTED | LAST_WRITE_WINS` concurrency；
- read的`EXACT | LATEST_AT_START` binding。

这些选择只影响caller-owned结果严谨度。Authentication/authorization、input/resource
safety、idempotency、request/effect identity、journal、fencing、atomic publication
evidence和unknown-effect reconciliation始终强制，不存在fire-and-forget旁路。
精确语义由
[Repository Service Contract](../contracts/repository-service.md)唯一规定。

## Alternatives

- 全部table写Dolt：拒绝，latest-only workload承担无必要历史成本。
- Service保存table policy并自动routing：拒绝，引入业务authority和migration。
- Server-side dual-write：拒绝，需要composite identity、partial outcome和跨store
  recovery。
- 所有write强制FULL和CAS、所有read强制EXACT：拒绝，把caller风险偏好固化为
  service-wide最高成本。
- 宽松路径关闭journal/idempotency：拒绝，Service无法解释response loss和crash后
  effect。

## Consequences

Public API形成store-specific typed family并共享transport、schema、stream、
authorization和resource primitives。Caller必须记录所选store/policy并正确处理
`FAILED + effect=APPLIED`、LATEST freshness和LWW覆盖风险。Conformance必须覆盖所有
显式policy组合；不同verification level的measurement不得混入同一series。

## Required verification

- 同名table跨store独立存在且inventory不推断authority/equality。
- NONE/STRUCTURAL/FULL各自成功并保存level-specific evidence。
- CHECK_EXPECTED stale conflict与LWW覆盖均可重复、幂等、crash-safe。
- EXACT与LATEST_AT_START都返回resolved immutable snapshot identity。
- 所有宽松policy仍通过auth、journal、fencing和reconciliation negative tests。

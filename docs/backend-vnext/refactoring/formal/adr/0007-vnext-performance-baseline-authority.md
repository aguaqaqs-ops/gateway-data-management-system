# ADR 0007: vNext Performance Baseline Authority

状态：Accepted

日期：2026-07-19

决策 owner：Backend vNext Performance Measurement

关联阶段：Phase 0、Phase 2–8

## Context

Phase 0时完整
`storage projection -> Repository import -> requested verification`
路径尚不存在，无法产生可信numeric baseline。使用legacy numbers或小型方向性实验
作为目标会混合不同架构、dataset、verification policy、环境和计时边界，也会把
兼容对比错误提升为性能门禁。

## Decision

Phase 0 只固定 measurement contract、profiles、workloads、environment authority、result schema 和 capture gate。首份 accepted numeric baseline 由首条 correctness-passed、containerized vNext production path产生；正式环境是 Backend/worker container 通过 public contract 调用拥有 Dolt lifecycle 的 Repository Service container。

Baseline record 使用独立 `INCOMPLETE/CANDIDATE/ACCEPTED/SUPERSEDED` 生命周期，只有 ACCEPTED 可作为后续 regression/optimization 比较权威。初始正确路径可以本身采用满足 contract/evidence 的 Rust provider；后续 Rust coverage、并行、cache 或 provider 优化必须等待 accepted baseline。精确 contract 位于 [Performance Measurement and Baseline Contract](../contracts/performance-measurement-and-baseline.md)。

## Alternatives

- 以 legacy 性能为 oracle/门禁：拒绝，架构与测量边界不可比。
- Phase 0 预填估算或方向性实验数字：拒绝，不具备 production-path authority。
- 为 benchmark 建私有 fast path：拒绝，不能代表用户旅程。
- 等所有优化完成再捕获 baseline：拒绝，会失去优化前可比基线。

## Consequences

Phase 0 没有 numeric report，但形成可执行 capture contract。Repository containerized production path 必须较早完成，才能解锁后续性能声明。环境、dataset、contract 或 provider identity 变化会新建 series；raw evidence 需要在 Git 外 content-addressed 保存。

## Required Verification

- Profile/workload/stage/metric schema 与 production entrypoint validation。
- Container health、restart、volume、environment fingerprint和requested
  verification gate；不同verification level使用独立series。
- Sample eligibility、multi-generation retention/GC 和 immutable record lifecycle tests。
- Formal/CI 中不存在 legacy-vs-vNext performance gate。

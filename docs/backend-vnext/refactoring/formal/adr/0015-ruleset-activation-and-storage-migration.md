# ADR 0015: Ruleset Activation and Storage Migration

状态：Accepted

日期：2026-08-18

决策 owner：Backend vNext Table Rules, Risk Rules and Canonical Storage

关联阶段：Phase 3、Phase 4/5 activation integration、future migration

## Context

业务现场可能出现 ruleset 外的 keyless 或异常表，需要快速补充规则以继续上传。规则又可能
改变 canonical key、字段集合、类型或 storage projection；直接在线替换会让同一 repository
混用新旧语义，破坏 digest、history 和 mutation plan。

## Decision

首版使用 immutable ruleset snapshot 和安全重启 activation：

```text
candidate -> validate -> pending_restart -> graceful drain
          -> safe restart -> activate
```

运行中的 operation 保持启动时捕获的 snapshot。Table ruleset snapshot 可作为 protected
`__gateway_meta_*` metadata 随正式 canonical commit 原子保存，但不进入业务 listing、
comparison、risk、bundle、mutation plan 或 external sync。Risk ruleset 首版保存在 risk
和 operation/audit metadata。

Activation validator 分类 `ADDITIVE`、`COMPARISON_BEHAVIORAL`、`RISK_ONLY` 和
`STORAGE_BREAKING`。后者只能进入 `MIGRATION_REQUIRED`；migration 是后续独立 durable
operation，从 FINAL canonical state 完整 rebuild 受影响表并创建新 Dolt commit，不改写旧
commit、不自动创建空 commit。external target 另行 full resync。

## Alternatives

- 自动 watcher/热替换 live object：拒绝，增加切换和一致性风险且没有首版必要性。
- 所有 ruleset 变化都重建历史 repository：拒绝，代价高且改写权威历史。
- 改变 storage projection 后继续正常 Submit：拒绝，可能混用 incompatible projection。
- 为紧急异常表保留任意 Python/plugin 规则：拒绝，规则必须声明式且可验证。

## Consequences

紧急 additive 规则可以通过安全重启面向未来 operation 生效；storage-breaking 规则需要
明确 migration window。历史 compare 继续使用程序当前默认 ruleset，历史 snapshot 仅作
provenance。后续若需要秒级生效，必须在同一 immutable snapshot/activation contract 上
新增可选 hot activation，不改变 operation 语义。

## Required Verification

- candidate validation、impact classification 和 pending/active rollback；
- safe drain/restart、ruleset snapshot capture 和 startup health check；
- storage-breaking candidate 被阻止且不会半激活；
- additive candidate 不改写旧 commit；
- migration commit、external full resync 和 failure recovery。

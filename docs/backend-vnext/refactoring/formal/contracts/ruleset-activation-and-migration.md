# Ruleset Activation and Migration Contract

状态：正式设计基线（Accepted）

阶段：Phase 3 provider/identity boundary；Phase 4/5 activation integration；future migration

Contract ID：`gateway-vnext.ruleset-activation-and-migration`

Owner：Table Rules / Risk Rules Policy

## 1. Immutable snapshot

首版 ruleset 使用 hardcoded registry/provider，但 capability 依赖 immutable snapshot。未来
配置源必须经过：

```text
candidate -> validate -> activate -> immutable snapshot
```

已运行 operation 在启动时捕获 ruleset snapshot，运行期间不受后续 activation 影响。

Table ruleset snapshot 可以作为 protected hidden metadata table 随正式 canonical commit
原子保存，例如保留 `__gateway_meta_*` namespace；它不进入 ordinary listing、comparison、
risk、bundle、`StorageMutationPlan` 或 external sync。普通上传不得创建、覆盖或删除该
namespace。

Risk ruleset 首版保存在 RiskEvaluation、risk annotation artifacts 和 operation/audit
metadata，不强制写入业务 commit。

## 2. Safe activation

首版不实现 online watcher。ruleset 变更采用：

```text
validate -> pending_restart -> graceful drain -> safe restart -> activate
```

graceful lifecycle 及 `180s` 默认 timeout 由
[Operation Lifecycle and Repository Integrity](operation-lifecycle-and-integrity.md)拥有。
activation 失败时继续使用上一个 active snapshot；不允许半激活状态。

## 3. Impact classification

activation validator 至少区分：

- `ADDITIVE`：新增此前不存在的表或规则，不改变已有 storage projection；
- `COMPARISON_BEHAVIORAL`：改变 comparison/surface，不改变 storage；
- `RISK_ONLY`：改变 risk 计算，不改变 repository state；
- `STORAGE_BREAKING`：改变 canonical key、字段集合、类型、null 语义或 storage projection。

`STORAGE_BREAKING` candidate 只能进入 `MIGRATION_REQUIRED`，不能直接进入 `ACTIVE`，
也不能让不同表混用新旧 projection。

## 4. Migration

Migration 是后续独立 durable operation，不属于 Phase 3。它从 FINAL canonical repository
state 读取数据，按新 ruleset 对受影响表完整 rebuild，创建新的 Dolt commit；不改写旧 commit、
不自动创建空 commit。受影响 external target 另行 full resync，不使用 `ADAPTIVE_PATCH`。

此前不存在的新异常表可以按 `ADDITIVE` 规则面向未来 source 生效。已有表从无有效 key/不
支持变为新 canonical storage 语义时属于 `STORAGE_BREAKING`。

## 5. History and rollback

History compare 统一使用程序当前默认 ruleset；历史 snapshot 仅作 provenance，不增加
mismatch 分支。ruleset rollback 只影响未来 operation，不回滚已有 repository commit；
已捕获旧 snapshot 的 operation 继续使用原规则。

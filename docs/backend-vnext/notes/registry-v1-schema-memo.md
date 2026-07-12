# Registry v1 Schema Memo

本文收口 repository-local SQLite registry 的 v1 schema 决策。它不是新的 contract，只是把当前实现方向固定下来，方便后续编码和 review。

## 结论

- `repository_server` 和 application/domain 使用独立 registry / DB，不共享同一 SQLite 文件、schema 或生命周期。
- v1 先用单个核心表承载 repository-local technical facts，不把 artifact / cache / scan / debug-hold 拆成多套独立 registry。
- registry 对上层优先提供 read-only query 视图；写入只走 repository-service / repository_server 内部操作。
- TTL、pin、eviction、quota、cleanup 策略字段不进入 v1 schema。

## Core Table

### DDL Draft

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

CREATE TABLE IF NOT EXISTS registry_entry (
  entry_id INTEGER PRIMARY KEY,
  repository_id TEXT NOT NULL,
  entry_key TEXT NOT NULL,
  entry_kind TEXT NOT NULL,
  namespace TEXT NOT NULL DEFAULT '',
  logical_ref TEXT NOT NULL DEFAULT '',
  owner TEXT NOT NULL DEFAULT '',
  tag TEXT NOT NULL DEFAULT '',
  operation_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  content_digest TEXT,
  manifest_digest TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  CHECK (length(trim(repository_id)) > 0),
  CHECK (length(trim(entry_key)) > 0),
  CHECK (length(trim(entry_kind)) > 0),
  CHECK (length(trim(status)) > 0)
  -- If JSON1 is available, add:
  -- CHECK (json_valid(metadata_json))
);

CREATE UNIQUE INDEX IF NOT EXISTS registry_entry_uq_key
  ON registry_entry(repository_id, entry_key);

CREATE INDEX IF NOT EXISTS registry_entry_idx_kind_namespace_created
  ON registry_entry(repository_id, entry_kind, namespace, created_at_ms);

CREATE INDEX IF NOT EXISTS registry_entry_idx_logical_ref
  ON registry_entry(repository_id, logical_ref);

CREATE INDEX IF NOT EXISTS registry_entry_idx_owner
  ON registry_entry(repository_id, owner);

CREATE INDEX IF NOT EXISTS registry_entry_idx_tag
  ON registry_entry(repository_id, tag);

CREATE INDEX IF NOT EXISTS registry_entry_idx_operation
  ON registry_entry(repository_id, operation_id);

CREATE INDEX IF NOT EXISTS registry_entry_idx_status
  ON registry_entry(repository_id, status);
```

### 说明

- `entry_kind` 可以表达 artifact、cache、scan、orphan、debug_hold、failure 等技术事实。
- `entry_key` 是稳定的内部幂等键，推荐由 repository-service 根据规范化后的 identity payload 生成，不暴露给业务 API。
- `namespace`、`logical_ref`、`owner`、`tag`、`operation_id` 用于过滤和 cleanup 计划，不承载业务状态机。
- `content_digest` / `manifest_digest` 对某些 kind 可为空；kind-specific payload 统一放进 `metadata_json`。
- `metadata_json` 只承载 kind-specific 扩展，不放业务流程判定。
- `created_at_ms` 和 `updated_at_ms` 统一存 UTC epoch milliseconds，应用层负责和 UTC aware datetime 转换。
- v1 不硬编码 `entry_kind` / `status` 的完整枚举集；应用层验证语义，schema 只保留通用约束。

### Upsert 规则

- `entry_key` 对同一 repository 必须稳定，可用于幂等重试。
- 写入默认采用 `INSERT ... ON CONFLICT(repository_id, entry_key) DO UPDATE ...`。
- 冲突更新时保留 `created_at_ms`，刷新 `updated_at_ms` 和 kind-specific payload。
- `metadata_json` 的更新应整体替换，不做局部 patch。

## 索引建议

已包含在上面的 DDL draft 中。

## 延后字段

以下字段先不进 v1 schema，等确实需要清理/保留/过期策略再补：

- `expires_at`
- `last_accessed_at`
- `pin_until`
- `ttl`
- `eviction_state`

## 后续拆分条件

如果未来某一类 fact 出现明显不同的生命周期、 retention 或性能特征，再把它从 `registry_entry` 中拆成专表；v1 不预先拆分。

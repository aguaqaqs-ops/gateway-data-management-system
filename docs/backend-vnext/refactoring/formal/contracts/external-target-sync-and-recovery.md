# External Target Sync and Recovery Contract

状态：正式设计基线（Accepted）

阶段：Phase 3 target-neutral contract；P5B integration；future PostgreSQL adapter

Contract ID：`gateway-vnext.external-target-sync-and-recovery`

Owner：External Target Sync Capability

## 1. Authority and first sync

Dolt canonical repository 是权威事实。external target 是异步 consumer，不与 Dolt 使用
2PC。target 首次同步必须是 `FULL_REBUILD`，并建立 target registration：

```text
target_id
target dialect
canonical schema/projection digest
repository base commit
applied change_set_digest
target generation
```

非空且没有匹配管理记录的 target 默认拒绝覆盖；只有显式授权的
`REPLACE_MANAGED_TARGET` 才能重建。

## 2. Apply lifecycle

```text
PREPARE -> APPLYING -> VERIFYING -> SUCCEEDED
                              \-> FAILED
                              \-> UNKNOWN_OUTCOME
```

executor 必须支持 target precondition、transaction boundary、idempotency/change-set
digest、conditional DML 和足够 readback，或明确声明不支持。未知结果先查询 target ledger、
transaction status 或 readback，不能盲目重放。

只有 canonical content digest/readback 与 target digest 相等时才是
`EXTERNAL_SYNC_SUCCEEDED`。只能 row-count/结构校验的 target 最多是
`EXTERNAL_SYNC_APPLIED_UNVERIFIED`。

## 3. Repository ordering

```text
Dolt canonical commit
  -> immutable ChangeSetArtifact
  -> external target apply
  -> target readback
```

external failure 不回滚 Dolt commit，记录 `EXTERNAL_SYNC_PENDING` 或
`EXTERNAL_SYNC_FAILED`，并从 immutable artifact 重试。Dolt commit 已完成后，重新上传
业务数据不能替代 target resync。

## 4. Drift and resync

base commit mismatch、schema/projection mismatch、target drift、guard mismatch 或
readback mismatch 均 fail closed，要求针对原 canonical commit 的 `FULL_RESYNC`。首版
不自动 merge、不自动覆盖未知外部数据。

不支持事务、conditional DML 或充分 readback 的 target 不能报告完整同步成功。首个 executor
是 fault-injectable reference state machine，可使用 SQLite 做部分 dialect tests，但不得
将 SQLite 结果表述为 PostgreSQL production validation。真实 PostgreSQL adapter/e2e 是
后续 target-specific work。

## 5. Multi-target and recovery

多个 external target 各自独立记录 status，不引入跨 target 事务。某个 target 失败不阻止
repository canonical commit，也不伪造其他 target 的成功。服务重启后从 durable checkpoint
接管；unknown outcome 先 reconcile 再 apply。

## 6. Verification

reference executor 必须覆盖首次 full rebuild、transaction rollback、重复 digest、
中途 crash、affected-row mismatch、drift、readback mismatch、checkpoint takeover 和
full-resync 要求。renderer 与 apply executor 分离测试。

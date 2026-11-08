# Storage Mutation and Change Set Contract

状态：正式设计基线（Accepted）

阶段：Phase 3 contract；P5 Submit/external integration

Contract ID：`gateway-vnext.storage-mutation-and-change-set`

Owner：Canonical Storage / Mutation Planner

## 1. Scope

本 contract 定义 canonical storage snapshot 之间的 mutation plan，以及供 Dolt 和其他
target renderer 消费的 target-neutral `ChangeSetArtifact`。它不定义前端 row comparison
records，也不把 SQL 方言写入中间 artifact。

```text
before canonical storage snapshot
  + current canonical storage projection
  -> StorageMutationPlan
  -> REBUILD_TABLE | PATCH_DML | NOOP per table
  -> target renderer
```

## 2. Policy

支持两种 policy：

- `REBUILD_ALWAYS`：每个变化表生成完整重建 mutation；
- `ADAPTIVE_PATCH`：planner 对每张表独立判断 patch eligibility，允许 mixed plan。

生产 `RepositoryImportArtifact` 路径冻结使用 `ADAPTIVE_PATCH`，planner 对每张变化表独立判断，
允许 mixed plan。通用 planner 仍保留 `REBUILD_ALWAYS` 供明确选择该策略的非生产调用方使用；它不是
Submit 的生产默认值。

## 3. Patch eligibility

首版仅允许同时满足以下条件的表使用 `PATCH_DML`：

- canonical storage key 稳定、唯一、可直接定位行；
- schema、key、storage projection 没有变化；
- table 不是 keyless、degraded 或 unsupported table；`GID_NO_V1` ordered table 可 patch，
  以 `gid` 为稳定 canonical storage key，`no` 作为普通 persisted column；
- 没有 foreign key、trigger、cascade、generated/server-default 或其他未建模外部副作用；
- target renderer 支持该表所有 logical types 与其目标所需的 apply semantics；外部目标保留
  条件 DML、affected-row 检查、事务与 readback 要求，生产 Dolt 路径按 §6 的 expected-parent CAS
  边界执行；
- `changed_row_count <= 1,000`；
- `change_ratio <= 1%`。

`change_ratio` 定义为：

```text
changed_row_count / max(before_row_count, after_row_count, 1)
```

阈值 policy 冻结为 `1,000` 行和 `1%`。INSERT、UPDATE、DELETE replay 每条 SQL 最多包含
`256` 行，且多行语句最多 `4 MiB`。字节数按完整 UTF-8 语句计算，包含 SQL 前缀、行间分隔符、
值和结尾的 `;\n`；若加入下一行会超限，先结束当前批次。单行语句即使超过 `4 MiB` 也独立成句，
不因该批次上限失败。S1a 在 t4 v2 的真实变化表上验证逐行路径与整表重建耗时并冻结行数阈值。
没有 estimated patch bytes eligibility 条件。最终 renderer 产生的 `replay.sql` 仍受
`200 MiB` artifact admission 限制；超过限制直接拒绝，不拆分、不 fallback。

派生表在 materialization 后按普通 canonical table 判断，不因来源而默认 rebuild。

## 4. Counting and net diff

- 多字段更新同一行计一次 `UPDATE`；字段数量不放大计数。
- `DELETE`、`INSERT` 各计一次 physical mutation。
- canonical key 变化表达为 `DELETE + INSERT`，计两次 physical mutation。
- 同一 key 的中间变化先归并为最终 before/after；最终无变化为 `NOOP`。
- `StorageMutationPlan` 使用 canonical storage key，而非仅用于前端 comparison 的
  `effective compare key`。生产 Submit 独立按稳定、唯一的存储键及完整 persisted 列判断
  patch；比较键不同本身不构成 rebuild 条件（Owner 2026-11-08，DC94，澄清 DC45 与
  ADR0014 的现行边界）。不得以 comparison records、共有列或显示身份替代存储输入；
  不稳定/缺失键、schema/key/storage projection 变化及其他不合格项仍按 §3 处理。

## 5. ChangeSetArtifact

artifact 为结构化数据，不保存 Dolt、PostgreSQL 或其他 SQL 文本。每个 mutation 至少包含：

```text
table_id
operation: INSERT | UPDATE | DELETE
canonical_storage_key
before_row_digest: optional
after_image: optional full persisted row
```

`UPDATE` 使用完整 persisted after-image，不只保存 changed columns；key 不作为 SET
字段。generated/server-default/无法直接写入字段使该表不满足 patch eligibility。

`manifest.json` 至少保存：

```text
source_identity
base_repository_commit/ref
target_identity
storage_projection_digest
table_ruleset_digest
threshold_policy
per_table operation/count summary
change_set_digest
artifact schema/encoding
```

logical scalar、NULL、DECIMAL、datetime、JSON、binary 等值遵守 shared canonical encoding；
renderer 负责 target-specific physical encoding，不得静默 stringify unsupported values。

## 6. Determinism and apply semantics

表按 canonical table identity 排序；表内操作按固定阶段排序：

```text
DELETE -> UPDATE -> INSERT
```

每个阶段按 canonical key 排序。所有 digest 使用 canonical encoding，不受输入顺序、
线程调度或 provider language 影响。

外部目标的 `UPDATE/DELETE` 带 canonical key 和 before-image guard，并要求 affected-row 数
精确匹配；`INSERT` 遇到已存在 key 为冲突。生产 Dolt renderer 在 Repository Service 私有 ref
上按 expected parent 构造确定性 replay，变化表 parent rows 先按 parent manifest 的行数与
`raw_content_digest` 校验；不生成 conditional DML，不做 affected-row 检查或提交后 readback。
其正确性依赖受信 Repository、expected-parent CAS 与上述 parent 行校验。各目标的 drift 与
capability failure 按其既定 full-resync/error contract 处理，不自动 merge。

## 7. Renderer boundary and lifecycle

Dolt renderer 生成 deterministic `replay.sql`。外部 renderer 生成 target-specific
parameterized command stream。renderer capability 必须参与 plan identity；effect 前
发现不支持时返回稳定的 `TARGET_CAPABILITY_UNSUPPORTED`，不得偷偷改变 plan。

artifact 在 Preview/Submit reuse、Dolt replay、可选 external ChangeSet、readback/audit
完成前保持 pinned。生产 Submit 的冻结/恢复以 Canonical Storage §5 的 prepare checkpoint
分界为准（Owner 2026-11-08 DC94）：T1 后冻结规范输入缺失或损坏稳定失败，不从 durable
SourcePackage 重建；prepare checkpoint 持久化后必须复用其包/ref/raw SHA，缺失不得
重建包或换 key。T1 前可重新 Preview；需要重传时创建新 attempt，不能覆盖已有 effect。
可选 external ChangeSet 的 source/readback/full-resync 沿该目标 owning Contract，不将
外部目标的恢复能力套用于已冻结的 Submit。

## 8. Verification

必须覆盖 no-op、multi-column update、key change、mixed plan、threshold boundary、
before-image conflict、input reorder、unsupported type、replay size admission、
renderer failure、retry、crash 和 readback mismatch。前端 comparison records 不能直接
作为 mutation source。

## 9. Submit 的表级进程内边界（Phase 6 S4）

Submit 可直接消费冻结的完整 canonical storage IPC 与精确 parent 表，逐表生成同一
`replay.sql`，无需构造无消费者的通用 `ChangeSetArtifact`。通用 planner/ChangeSet 与外部
target 的完整计数、digest 和 renderer 契约仍保留。此边界不新增 durable artifact、版本轴或
业务状态；`StorageTableTaskV1` 的 V1 仅标识进程内输入形状。

```text
StorageTableTaskV1(table, before?, after?, after_ddl_layout)
  side = manifest table + storage view + projection version + Arrow C stream/schema
prepare_storage_table(task, caller_operation) -> StorageTableHandle
handle.summary() -> StorageTableSummary
choose_table_mutation(metadata, summary, frozen_threshold) -> StorageTableDecision
handle.render(decision) -> bounded bytes chunks
handle.close()
```

缺侧表示表不存在；存在的零行表仍有显式 schema 的空 stream。after 存在时须有完整
stream 和 DDL layout。before 在强制 rebuild 时可只带 metadata；若拟 patch，必须从精确
parent 读取完整 before，校验 count/content 与绑定并拒绝重复 storage key。NOOP 也要打开并
核验冻结 after 输入，不能只信 manifest。`StorageTableSummary.net_counts=None` 明确表示未
读取 before 或未做 diff，不得伪填 0 或 before+after；已完成 diff 的 insert/update/delete
计数为最终净变化，多列同键更新计一行、键变计 delete+insert。强制 rebuild 的实际 INSERT
数单列记录，不能冒充净 diff。最多保留 1000 个 patch action locator；超限后仍完成计数。

Python Mutation Planning 是唯一表级策略 owner：INITIAL/新增、删除、projection/schema/key/
retained/storage view 变化、keyless/不稳定键和 before=0 时不读取无用 parent 行而按既定
规则 rebuild/drop；可比较 keyed 表的零净差 NOOP，否则同时满足 changed≤1000 与
`100*changed≤max(before,after,1)` 才 patch。source schema 独变且完整 storage diff 为零的
候选可 NOOP；该例外不扩展到不读 parent 的 keyless。非法 profile、重复键、坏绑定和未建模
副作用必须在 effect 前失败，不能通过 rebuild 隐藏。ordered `gid/no` 仅 `gid` 是 storage
key，`no` 为普通 persisted 列；comparison effective key 不参与此选择。

排序与 hash 域分开：表名和 persisted INSERT/UPDATE 列名按 UTF-8；key 列数组先按
canonical 名 UTF-8 排列，key document 的 JSON object 再按 JCS UTF-16 排序，按完整
JCS UTF-8 bytes 比较（整数十进制字符串不做数值比较）；keyless rebuild 保留重复行，
以 `JCS([]), mutation row_digest` 排序。mutation row digest 使用 Shared Kernel row frame，
不能用 IPC raw digest 或业务表 SET sequence frame 代替。SQL 全部删除表 DROP 在前，
接全部 rebuild DROP+CREATE，最后才按表名及 DELETE→UPDATE→INSERT 顺序输出 DML。

`caller_operation` 必须是调用方已开启的有效 `KernelExecutionContext`，使用同一个 M、N、
cancel/deadline 与共享池；contracts.py 的内部 `StorageTableOperation` Protocol 只作
静态 typing view，不是独立预算会话、运行时初始化或绕过 active/closed context 检查。
Arrow C Stream 所有权转移后，table handle 保持当前表的 stream、mapping、native leases
与未消费 chunk 有效；render 只发有界 bytes chunk。关闭顺序为完成/停止 render、释放 native
Arrow/index/chunk、关闭 stream/reader/mmap，再退还 native 子额度并打开下一表。package
汇集仍在同一 M 的既有 package envelope，不能与 native 子额度重复计费；返回 bytes 的最后
使用者须保留相应 charge。异常按同序释放，不依赖 GC。

native code/message 及有界 stage/table 诊断映射到现有边界：取消为 `InterruptedError`，
截止为 `TimeoutError`，预算为 `KernelMemoryLimit`；普通输入/能力/SQL cap 通过现
ImportReplay/SubmitPublication 错误边界，通用 renderer 继续以 `ReplayRenderOutcome`
返回 `TARGET_CAPABILITY_UNSUPPORTED` 或 `RESOURCE_EXCEEDED` failure code。
panic 属内部失败，不返回部分 SQL、不假装 unsupported；不新增 HTTP/Repository public
failure code。通用 `render_change_set_replay` 与 schema replay facade 在迁移后要求显式
`context: KernelExecutionContext`，仍保留原返回形状；Submit 使用同一 operation。

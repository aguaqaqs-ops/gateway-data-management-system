# P5 架构收口 G3：control DB 基线 schema 实施规格

日期：2026-10-11

状态：**owner 已确认（2026-10-11）**：D1–D6 与“G3 作为独立阶段”全部同意（§9）。实施前设计 DC6、§10 与执行计划中的 migration 表述保持原状，改写由实施提交 1 完成。
实施在 G8a（census 口径修订，不改生产代码）审核完成之后开始；二者都写主工作区，不并行。

关联：[治理修订计划](p5-arch-closure-post-s1-governance-plan.md) G3（owner 2026-10-10 选方案 A）；[设计](p5-arch-closure-design.md) DC6、§10；
[执行计划](p5-arch-closure-execution-plan.md) §2、§3 S2a/S2b、§6；[Business Lifecycle](../contracts/business-lifecycle-and-state.md)；AGENTS.md「项目前提」。

## 1. 目标与非目标

目标：把 control DB 的 schema 创建改为单一基线，删除历史迁移链，使 S2a、S2b 的 schema 变更直接修改基线，同时保证：

1. 基线与现有迁移链的终态逐项相同（表、列、CHECK、外键、索引、触发器）；
2. 启动时 schema 与代码不符即拒绝启动（fail-closed），不修改文件；
3. 业务规则（首次 seed、批量 seed、mapping update 的同一验收规则）与其测试不丢。

非目标：不改任何表结构、不改任何业务行为、不改 HTTP DTO、不碰 S2a/S2b 要新增的表和列、不碰 STORAGE_BREAKING migration operation 与在线 ruleset 迁移（未来工作）。
本步骤是“只合并、不改 schema”。命名上避免与业务 Baseline（Archive 的初始基线）混淆：代码里叫 schema，文档里叫“基线 schema”。

## 2. 现状（2026-10-11，`p5-g2-exit` 之后实测）

- `infrastructure/control_db/migrations.py` 1,761 行：Operations v1，Workspace v1–v6。v2 重建 preview idempotency 表并拷贝数据；v4 从 submission 回填 review seed；
  v5 做 baseline authority、archive 表与 mapping 重建，含约 320 行针对历史行的校验与迁移函数（`_validate_v5_*`、`_migrate_v5_baseline_authority`、`_rebuild_v5_provisioned_scope_mappings` 等）；v6 是增量 DDL。
- 版本台账是表 `control_schema_migrations(component, version, applied_at_us)`；`UnsupportedSchemaVersion`（`operations/store.py`，属于 operation store 的错误契约，`worker_startup.py` 据此映射启动失败）在库版本高于代码时抛出。
- 运行时只经 `database.py` 的 `initialize_control_db` 调用 `bootstrap_control_schema` 与 `bootstrap_workspace_schema`；其他运行时代码不复用 `migrations.py` 的任何私有函数（已 grep 核对）。
  调用方：`bootstrap/composition.py`、`bootstrap/operation_worker.py`（经 `initialize_and_verify_control_db`），测试若干。
- 触及迁移内部的测试：`test_control_db_migrations.py`（6）、`test_workspace_control_db_migrations.py`（5）、`test_submit_control_db_migrations.py`（6）、
  `test_archive_control_db_migrations.py`（14）、`test_review_persistence.py`（21 项中约 6 项是迁移测试，其余是 review repository 行为），共 52 项；
  另有 `test_sqlite_operation_store_integration.py`、`test_operation_worker_integration.py`、`test_operation_worker_process.py` 直接读写 `control_schema_migrations`。
- 其他文档中的表述：`vnext/deploy/README.md` 的“mixed v4/v5 writers / Upgrade flow”。

## 3. 设计决定

**D1 schema 与代码是否相符：比较结构，不用版本号。**
新模块 `infrastructure/control_db/schema.py` 持有一个有序的 DDL 元组 `CONTROL_DB_SCHEMA_STATEMENTS`。启动时（`BEGIN IMMEDIATE` 内）：

- 库中没有任何非 `sqlite_` 对象 → 执行全部 DDL，提交；
- 否则读取 `sqlite_master`（type、name、tbl_name、sql，按 type 与 name 排序），与“在内存库里执行同一份 DDL 得到的结构”逐项比较，相同则不写任何东西；
- 不同（缺对象、多对象、`sql` 文本不同、或根本不是 control DB）→ 抛 `UnsupportedSchemaVersion`，不修改文件，消息只含对象名、不含行数据，并提示删除本地 control DB 重建。

这样“之后直接改基线”不依赖谁记得改版本号：基线 DDL 一变，旧文件自动被拒绝。考虑过的替代是 `PRAGMA user_version`（实现更小，但要人工递增，S2a/S2b 反复改基线时容易遗漏），不推荐。

**D2 单一入口，删除台账。** 用 `bootstrap_control_db_schema(connection)` 取代 `bootstrap_control_schema`、`bootstrap_workspace_schema`；删除 `control_schema_migrations` 表与四个 `*_SCHEMA_*` 常量
（`OPERATIONS_SCHEMA_COMPONENT/VERSION`、`WORKSPACE_SCHEMA_COMPONENT/VERSION`）。`UnsupportedSchemaVersion` 保留并复用（错误契约与启动映射不变）。`BEGIN IMMEDIATE`、忙/锁到 `StoreBusy` 的映射、失败即回滚保持原样。

**D3 删除仅为台账时间戳服务的 `now` 参数。** `initialize_control_db` / `initialize_and_verify_control_db` / `bootstrap` 的 `now`（迁移时钟，必须是 aware UTC）随台账消失；
实施者核对 `database.py` 中 `now` 是否另有用途（`ControlDbUnitOfWork` 的 `now` 与此无关），有则保留并在 handoff 记录。

**D4 数据完整性检查随历史数据删除。** `_assert_workspace_bootstrap_integrity`（同一 scope 多个 OPEN）与 `_assert_workspace_migration_integrity` 只在对已有数据升级时需要；
前提是基线 DDL 已含对应的唯一索引或约束，由 D5 的终态对照证明。`database.py` 的 `assert_control_db_integrity`（`PRAGMA integrity_check`、`foreign_key_check`）保留。

**D5 终态对照是一次性的等价证明，不入库。** 在 `p5-g2-exit` 上，对空库依次执行现有 `bootstrap_control_schema` 与 `bootstrap_workspace_schema`，导出规范化的 `sqlite_master`（排除台账表），
写到 worktree 外（`/home/dev/gdds-p5-closure-s1-gate-logs/g3-*`），handoff 记录其 sha256。新基线在空库上建出的结构必须与之逐项相同（排除台账表）。
永久保留的是行为测试（§5 的“合并保留”项：表、约束、索引、触发器与枚举断言），不是 DDL 的 golden 副本，避免 S2a/S2b 每次改基线都要同步两处。

**D6 契约措辞（须 owner 确认）。** Business Lifecycle「固定 scope 归属」中，“migration、首次 seed、批量 seed 和 mapping update 必须遵循同一业务验收规则”的 migration 一项消失：

- 第 2 条后半句（“没有归属事实但历史已存在时，只有在 migration 明确验证全部既有事实一致后…”）依赖历史数据，删除；
- 第 3 条“整个 migration / seed 批次 / mapping update 事务拒绝”去掉 migration，“失败不改…schema migration 版本”去掉末项；
- 第 1、4 条与实质规则（一个 Repository 只能得到一个 exact scope；已有固定归属只接受同 scope；不覆盖已推进的 Head；失败整批拒绝、无部分写入）不变，由运行时 seed 与 mapping update 路径承担。
5D 设计与执行计划中的历史阶段文档（`p5-5c-*`、`p5-5d-*` 等）是当时的记录，不改写。

## 4. 范围与路径预算

生产代码：`infrastructure/control_db/{migrations.py → schema.py, database.py, __init__.py}` 与按 grep 命中的直接调用方（`bootstrap/composition.py`、`bootstrap/operation_worker.py` 经 `initialize_and_verify_control_db`，预期不改调用形式）。
不得新增依赖、不得改其他包。`import_rules` 须保持 3 / 0 / 14。

测试：见 §5。文档：设计 DC6 与 §10（`grep -n migration`：DC6 行、§10 兼容性、`history_compare_integrity_records` 删除行、control DB 新增前向 migration 行）、
执行计划 §2/§3/§6 中 S2a、S2b 的 control DB migration 条目（验收、路径预算中的 `test_*_control_db_migrations.py`、§6 判定表）、`business-lifecycle-and-state.md`（D6）、`vnext/deploy/README.md` 的升级流程。
设计 DC6 与 §10 里已有的“见治理修订计划 G3”注记改为已实施的最终规则；新规则一句话：schema 与代码不符时拒绝启动，开发者删除本地 control DB 重建；首次出现需要保留数据的部署时，再从当时的基线重新引入前向 migration（重开 DC6）。

## 5. 测试处置

原则：每个被删测试，先说明它证明的不变量要么只属于历史迁移，要么已有运行时权威测试；不确定的保留。按业务行为命名，同构用例收敛为参数表，不按“v5”“迁移”命名。

| 文件 | 保留或改写（合并进一个 control DB schema 测试文件） | 删除 |
| --- | --- | --- |
| `test_control_db_migrations.py` | 新建库创建全部表、约束、索引；重复调用无写入；失败回滚（注入一条失败的 DDL）；schema 不符被拒绝且不改文件（由“版本更高”改写，用参数表覆盖缺表、多表、列定义变化、缺索引、无关的 SQLite 文件、空库） | v0 台账推进到 v1；迁移时钟必须是 aware UTC |
| `test_workspace_control_db_migrations.py` | 创建表、约束、索引；重复调用；失败回滚；不符被拒绝 | 历史 v1 文件重开并 seed 的迁移部分（其中“seed mappings”的运行时部分由下面的 seed 测试承担，须核对） |
| `test_submit_control_db_migrations.py` | 创建 submit 相关表与约束（合并） | 重复/回滚/版本拒绝（与上同构，已由合并后的一份承担）；历史 v2 重开升级；损坏的 v2 外键拒绝升级 |
| `test_archive_control_db_migrations.py` | 创建 archive 表；disposition 选中的唯一索引；baseline head 拒绝跨 Repository 节点引用（DDL 约束）；`test_seed_restart_does_not_regress_advanced_head`、`test_seed_rejects_cross_scope_repository_reassignment`（运行时 seed 规则，移到 `sqlite_provisioned_scope` 的 owner 测试文件） | v4 mapping 迁移初始身份；v5 迁移拒绝非零 head、不可解释的 baseline 引用与 idempotency、跨 scope 共享；v5 迁移保留历史；v5 失败回滚到 v4；“重建 mapping”部分 |
| `test_review_persistence.py` | 创建 review 表与约束；`test_review_migration_enums_match_domain_literals`（DDL 枚举与领域字面量一致，改为引用 schema 模块）；全部 repository 行为测试 | 重复/回滚/版本拒绝/历史 v3 重开/backfill 每个 submission 一个 seed |
| `test_sqlite_operation_store_integration.py`、`test_operation_worker_integration.py`、`test_operation_worker_process.py` | 改为断言新库可用与结构相符；`higher_schema` 参数改为“结构不符”，仍要求非零退出、输出脱敏 | 读写 `control_schema_migrations` 的断言 |

契约对照表：handoff 须列出 Business Lifecycle 该条款第 1–4 条各由哪个运行时测试承担；任何一条只有迁移测试覆盖时，停止并交 owner（不自行补语义）。
新增测试：结构比较的参数表（见上）、并发或忙时映射为 `StoreBusy`（沿用现有测试，若现有测试依附于迁移文件则随之迁移）、第二次调用不改库（用 `total_changes` 或文件字节比较）。

## 6. 提交与门禁

1. `docs(p5-g3)`：此规格 owner 确认后，设计 DC6、§10、执行计划、Business Lifecycle、deploy README 的改写（纯文档，可先于代码）。
2. `feat(p5-g3)`：终态对照导出（外部）→ `schema.py`、新 bootstrap、调用方切换、测试迁移与删除；每个提交后五包 ruff/mypy、`import_rules`、相关 focused 测试通过。
3. `refactor(p5-g3)`：删除 `migrations.py` 与迁移专属测试（与上一提交分开，便于审核时看清“只删不改”）。
4. 门禁提交 V 是最后一个非 handoff 提交；G3 改动 `backend/src`，backend/worker 镜像内容变化，**必须在 V 上真实重建并完整运行权威 runner**，遵守 AGENTS.md「权威入口的运行前提」；handoff 提交 H 只改 handoff，按 carried 第 3 条在 V 的 worktree 内判定。
5. 区间起点 R0 是 G3 kickoff 时 main 的提交（G8a 审核完成后的 HEAD，kickoff 时写入实施提示词）；独立审核通过后在审核报告提交上打 `p5-g3-exit`；S2a 的区间起点改为 `p5-g3-exit`。

## 7. 停止条件（停止并在 handoff 记录，交 owner，不用兼容代码绕过）

- 终态对照有任何一项不同，或需要为通过对照而改变现有表结构；
- 需要改变任何运行时行为、HTTP DTO、golden、digest 或 checkpoint 载荷；
- 契约对照表中有条款只被迁移测试覆盖；
- `import_rules` 增长，或需要新增依赖；
- 发现运行时代码依赖 `control_schema_migrations`、迁移私有函数或 `now` 的其他用途（先记录，再按 D2、D3 处理）；
- 设计 §14 的停止条件。

## 8. 验收

- 终态对照一致，对照结果与导出文件的 sha256 写入 handoff；
- 结构不符被拒绝且文件不被修改，启动映射（HTTP、worker）仍是失败退出、输出脱敏；
- 迁移代码与迁移专属测试已删除；§5 的保留测试全部通过，契约对照表完整；
- 五包 ruff/mypy、`import_rules` 3 / 0 / 14；V 上权威 runner exit 0，三镜像 provenance 与 carried 判定记录齐全；
- 文档改写完成，设计与执行计划中不再有“control DB 新增前向 migration”的现行描述（STORAGE_BREAKING 与在线 ruleset 迁移除外）；
- 独立审核通过。

## 9. owner 决议（2026-10-11）

D1–D6 均获同意：

| # | 决定 | owner 决议 |
| --- | --- | --- |
| D1 | 校验方式：结构比较（不用 `PRAGMA user_version`） | 同意 |
| D2 | 单一入口、删除台账与四个版本常量，保留 `UnsupportedSchemaVersion` | 同意 |
| D3 | 删除迁移时钟 `now` 参数（实施者核对无其他用途） | 同意 |
| D4 | 历史数据完整性检查随迁移删除，`assert_control_db_integrity` 保留 | 同意 |
| D5 | 终态对照一次性、不入库；永久保留的是行为测试 | 同意 |
| D6 | Business Lifecycle 的措辞改写（§3 D6，删 migration 一项，实质规则不变） | 同意（正式契约措辞已获 owner 明确） |
| 阶段 | G3 作为独立阶段，打 `p5-g3-exit`，经完整门禁与独立审核 | 同意 |

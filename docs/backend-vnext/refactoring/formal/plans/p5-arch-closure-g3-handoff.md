# P5 架构收口 G3 实施交接（停止记录）

状态：**STOPPED — 停止于契约对照门，交 owner 决定。** Business Lifecycle §1A.2 第 3 条（整批 seed 拒绝、无部分写入、失败不改 mapping/Head/历史）在运行时没有任何测试覆盖，此前的覆盖只来自被删除的迁移测试。按规格 §2 停止条件，未进入门禁提交 V，未做 carried 判定，未声明任何容器门禁结果。

日期：2026-10-11
分支 / worktree：`p5-g3` / `/home/dev/gdds-p5-g3`（保留，未推送，未打 tag，未合并 main）
R0：`e2bea5bab2dd3dadb74afd9fb4aa47834ce02c28`（main 祖先；建立 worktree 时 HEAD 相同，`git status` 为空）

## 1. 提交序列

| 序 | SHA | 提交 | 内容 |
| --- | --- | --- | --- |
| 1 | `6d2d11a7a9` | `docs(p5-g3): rewrite control DB schema and migration wording` | 设计 DC6、§1 兼容性段、§10 前向 migration 条目、DC9 删除行、§12 测试归属行；执行计划 S2a/S2b 的 control DB migration 条目（内容、验收、路径预算、§6 判定表）；Business Lifecycle §1A（D6 措辞）；`vnext/deploy/README.md` 升级流程 |
| 2 | `60f90c1e7f` | `feat(p5-g3): create the control DB from a single schema` | `schema.py`；运行时切换；删除 `migrations.py` 与四个迁移测试文件；删除 review 迁移测试；新增 `test_control_db_schema.py`、`test_provisioned_scope_seed.py`；其余测试去除 ledger 与 `now=` |
| H | 本提交 | `docs(p5-g3): record G3 stop at the contract coverage gate` | 本文件 |

**偏离规格的提交形态**：规格提交 3（`refactor`，只删不改）并入提交 2。原因：`test_production_reachability_matches_frozen_baseline` 要求运行时停止引用 `migrations.py` 时同一提交删除该模块，且基线（`tests/architecture_baseline.py`）不得扩展。提交 2 因此包含删除，不能拆成“只删不改”的独立提交。

## 2. 前置核对

- `git rev-parse R0` 与 kickoff 一致，R0 是 main 的祖先；worktree HEAD = R0，`git status` 为空。
- `plans/p5-arch-closure-g8a-handoff.md` 与 `plans/p5-arch-closure-g8a-independent-review.md` 存在。
- `legacy` 符号链接建于 worktree 内（不在提交中），建后 `git status` 仍为空。
- 依赖准备：`GATEWAY_DEV_OFFLINE=1 ./vnext/scripts/prepare-dev-dependencies.sh`，exit 0，日志 `g3-prepare-offline.log`。五个 `uv.lock` 的 SHA256 与 R0 相同（`g3-uvlock-sha-R0.txt`），提交后仍相同。

## 3. 终态对照（D5 等价证明）

- 旧链导出（R0，`bootstrap_control_schema` + `bootstrap_workspace_schema` 于内存库，`now` 为固定 aware UTC，排除 `control_schema_migrations`）：`g3-terminal-old.json`，sha256 `ef36c416512d377358b2af280ef22a2e17b4db3f551a8d4589ad7b5ad03cc73d`。
- 新基线导出（HEAD `60f90c1e7f`，`bootstrap_control_db_schema` 于内存库）：`g3-terminal-new-HEAD.json`，sha256 `da99c68fdea335884b54b99fa9074313a174ae92681d0afc5a528e91cb666ae2`。
- 比对：`g3-schema-compare.py`，报告 `g3-compare-HEAD.txt`，exit 0。

| 层 | 检查项 | 规模 | 结果 |
| --- | --- | --- | --- |
| L1 | 对象集合 `(type, name, tbl_name)` | 43 对象（26 表 + 17 显式索引） | 0 差异 |
| L1 | 每表 `table_xinfo`（列序、类型、notnull、默认值、pk、hidden） | 277 列 | 0 差异 |
| L1 | 外键 `foreign_key_list` | 32 条 | 0 差异 |
| L1 | 索引 `index_list` / `index_xinfo`（名称、unique、origin、partial、列与排序） | 59 项（含 42 个 autoindex） | 0 差异 |
| L2 | 规范化 SQL（表：子句多重集合；索引：规范化全文） | 43 | 43 全部一致；0 残留差异；0 条仅空白/顺序差异，无需逐条解释 |

规范化规则：去注释；折叠空白；去掉标点两侧空白；未加引号的文本小写；引号内容保持原样；表定义按深度 0 逗号拆分为子句后比较多重集合。原始 `sql` 文本 43/43 不同（SQLite 按 ALTER 链改写，且新基线为可读格式），规范化后全部一致。

**比较器自检**（对 HEAD 导出的副本做变异后比较）：引号内字面量大小写改动、`AND`→`OR`、去掉 `NOT NULL`、删除索引、交换列序均被报告为差异（exit 1）；纯空白改动不报告（exit 0）。

**结构生成方式**：基线 DDL 由终态 `sql` 经仅改变空白的格式化器生成（`g3-format-baseline.py`，保持 token 不变），再由 `g3-splice-schema.py` 写入 `schema.py`。生成后已用上述比较验证；之后对 `schema.py` 的改动只涉及校验函数，未改 DDL。

## 4. 契约对照表（Business Lifecycle §1A.2 第 1–4 条）

| 条款 | 运行时测试 | 结论 |
| --- | --- | --- |
| 1. 一个 Repository 只能得到一个 exact scope | `test_provisioned_scope_seed.py::test_seed_rejects_cross_scope_repository_reassignment`（由迁移测试文件迁入）：已持久化归属与新 scope 冲突被拒绝 | 有覆盖。缺口（非迁移专属，未由本次改动引入）：同一批次内 `seed batch assigns one repository to multiple scopes` / `assigns one scope to multiple repositories` 两条校验没有测试 |
| 2. 已有固定归属时只接受同 scope | 同上；`test_seed_restart_does_not_regress_advanced_head` 覆盖同 scope 重复 seed 被接受 | 有覆盖 |
| 3. 任一跨 scope、无法解释的历史或初始归属冲突使整个 seed 批次 / mapping update 事务拒绝，无部分写入；失败不改既有 mapping、Head 或历史 | **无运行时测试。** 此前仅有 `test_archive_control_db_migrations.py::test_v5_migration_rejects_cross_scope_repository_sharing` 与 `test_failed_v5_migration_rolls_back_to_v4`，二者是迁移专属且已随迁移链删除。实现侧：`seed_provisioned_mappings` 在单一 `ControlDbUnitOfWork` 事务内逐条应用（`sqlite_mapping.py` 的 `seed_provisioned_mappings` 与 `_seed_provisioned_mappings_in_transaction`），异常即回滚，但没有测试证明 | **STOP：此条款只有迁移测试覆盖，且迁移测试已删除。** 按规格停止，交 owner（见 §12 第 1 项） |
| 4. 同 scope 的重复 seed、禁用/启用、重启沿用合法身份，不覆盖已推进的业务 Head | 重复 seed 与重启、Head 不回退：`test_seed_restart_does_not_regress_advanced_head`。禁用的效果（消费方）：`test_review_http.py`（provisioned mapping is disabled）、`test_archive_transactions.py::test_start_archive_replay_requires_transaction_fresh_enabled_mapping`、`test_submit_transactions.py::test_t1_replay_rejects_when_mapping_disabled_after_concurrent_winner`、`test_history_projection.py::test_get_project_history_rejects_disabled_mapping_in_same_transaction` | 重复 seed 与重启有覆盖。缺口（非迁移专属）：禁用后重新启用并沿用合法身份，没有 seed 级测试 |

另：5D 设计 §9 与 Business Lifecycle §9A（行 332）指定 `test_archive_control_db_migrations.py` 为“migration/seed/update 归属矩阵”的唯一 owner，该文件已删除。owner 文件需由 owner 指定（见 §12）。

## 5. 停止条件逐项核对

- 终态对照有无法解释的差异，或需要改变现有表结构：**否**（0 差异，表结构未改）。
- 需要改变运行时行为、HTTP DTO、golden、digest 或 checkpoint 载荷：**否**。唯一行为变化是规格 D1 要求的：schema 不符或非 SQLite 的 control DB 启动被拒绝，旧链库不再升级。DTO、golden、digest、checkpoint 载荷未改。
- 契约对照表有条款只被迁移测试覆盖：**是，第 3 条。停止。**
- `import_rules` 增长或需要新增依赖：**否**。`import_rules` 为 3 / 0 / 14（`tests/architecture_baseline.py` 的 `IMPORT_RULE_BASELINE`、`RUNTIME_CYCLE_BASELINE`、`UNREACHABLE_MODULE_BASELINE` 计数），未新增依赖。
- 运行时代码依赖 `control_schema_migrations`、迁移私有函数或 `now` 的其他用途：**否**（见 §6 的核对）。
- 设计 §14 停止条件：**否**。第 5 条“需要兼容旧数据的真实部署”未出现。

## 6. `now` 参数核对

- `initialize_control_db(db_path, now=...)` 与 `initialize_and_verify_control_db(db_path, now=...)`：仅用于迁移台账时间戳（`_datetime_to_epoch_us`），已删除。运行时调用方（`bootstrap/composition.py`、`bootstrap/operation_worker.py`）本就不传 `now`，未改。测试与 support 中 31 处传参删除（9 个文件，其中 5 处位于随后删除的迁移测试文件中）。
- `ControlDbUnitOfWork(now=...)`：事务时钟，与迁移无关，保留（`database.py` 的 `_utc_now` 仍为其默认值）。
- `test_sqlite_operation_store_integration.py` 中 `MIGRATION_TIME` 改名为 `FIXED_TRANSACTION_TIME`，因为它现在只作为事务时钟。
- 精确名称搜索（`control_schema_migrations`、`control_db.migrations`、`*_SCHEMA_COMPONENT`、`*_SCHEMA_VERSION`、`bootstrap_control_schema`、`bootstrap_workspace_schema`、两个 `_assert_*_integrity`）在 `vnext/` 下只命中一处：`test_control_db_schema.py` 中用于模拟旧台账的测试夹具。

## 7. 测试处置

| 文件 | R0 函数数 | 处置与理由 |
| --- | --- | --- |
| `test_control_db_migrations.py` | 6 | **删除 6。** fresh bootstrap 的表/索引断言 → `test_empty_control_db_gets_every_table_and_index`；重复调用 → `test_repeat_bootstrap_writes_nothing`；失败回滚 → `test_failed_schema_statement_rolls_back_every_object`；版本更高拒绝 → 结构不符参数表；v0 推进与迁移时钟 aware UTC → 删除（历史迁移专属） |
| `test_workspace_control_db_migrations.py` | 5 | **删除 5。** 创建表/约束/索引、重复调用、回滚、拒绝 → 同上新测试；历史 v1 文件重开并 seed → 删除（历史迁移专属；seed 运行时行为由 `test_provisioned_scope_seed.py` 与 `tests/support/baseline_fixtures.py` 的 seed 调用承担） |
| `test_submit_control_db_migrations.py` | 6 | **删除 6。** submit 表创建 → `test_empty_control_db_gets_every_table_and_index` 的表集合；重复/回滚/拒绝 → 同上；历史 v2 重开升级、损坏 v2 外键拒绝升级 → 删除（历史升级专属，新基线无升级路径）。submit 表列级约束由 `test_submit_transactions.py` 等运行时测试承担 |
| `test_archive_control_db_migrations.py` | 14 | **删除 9，移动 2，改写 3。** 移动：`test_seed_restart_does_not_regress_advanced_head`、`test_seed_rejects_cross_scope_repository_reassignment` → `test_provisioned_scope_seed.py`（运行时 seed 规则）。改写：`test_v5_baseline_head_rejects_cross_repository_node_reference` → `test_baseline_head_rejects_node_of_another_repository`；`test_workspace_v5_creates_archive_tables` → `test_archive_tables_and_selected_disposition_index_are_created`；disposition 选中唯一索引 → 同一测试。删除 9 项的理由：v4→v5 迁移、迁移时的历史数据校验与拒绝、迁移回滚、mapping 重建（历史迁移专属）。其中 `test_v5_migration_rejects_cross_scope_repository_sharing` 与 `test_failed_v5_migration_rolls_back_to_v4` 是契约第 3 条的唯一覆盖来源，见 §4 |
| `test_review_persistence.py` | 21 | **删除 6**（v4 bootstrap、重复、回滚、版本拒绝、历史 v3 重开、backfill 每个 submission 一个 seed：均为迁移专属）；`test_review_migration_enums_match_domain_literals` 改写为 `test_review_schema_enums_match_domain_literals`，从 `schema.py` 的 DDL 解析 `status`、`event_kind` 的 IN 列表与领域枚举比较；其余 repository 行为测试保留（函数 15 个，参数化后 18 项） |
| `test_sqlite_operation_store_integration.py` | — | 去除 ledger 断言（2 处）；并发 bootstrap 测试改用 `bootstrap_control_db_schema`；保留 WAL/FK/busy 断言与所有 store 行为测试；`MIGRATION_TIME` 改名 |
| `test_operation_worker_integration.py` | — | ledger 断言改为 `step_records` 存在性断言 |
| `test_operation_worker_process.py` | — | ledger 断言改为表存在性断言；`higher_schema` 参数改为 `structure_mismatch`（在库中加入 `unexpected_probe` 表），仍断言非零退出、`operation_worker_failed`、不泄露路径与 token；`corrupt` 参数保留 |
| `test_sqlite_operation_store.py`（规格列表未包含） | — | 直接调用旧 `bootstrap_control_schema` 的两处改为 `bootstrap_control_db_schema(connection)` |
| `test_architecture.py` | — | `migrations.py` 存在性断言改为 `schema.py` |
| `test_backend_readiness.py` | — | **新增 1**：`test_prepare_backend_runtime_rejects_control_db_with_a_different_schema`，HTTP 启动路径对结构不符的 control DB 失败关闭，错误中不含 tmp 路径，文件字节不变 |

新增文件：
- `test_control_db_schema.py`：8 个函数，14 项（含 7 项结构不符参数化用例）。覆盖：空库创建全部表与索引（精确集合）；空文件创建；重复调用不写入（`total_changes` 与文件字节）；注入失败 DDL 回滚；结构不符（额外表、缺表、列定义改变、缺索引、额外索引、旧台账表、无关 SQLite 文件）被拒绝且文件字节不变；非 SQLite 文件被拒绝且文件字节不变；archive 表与 disposition 选中唯一索引；baseline head 拒绝跨 Repository 节点引用（外键）。
- `test_provisioned_scope_seed.py`：2 个函数（移动）。**该文件由实施方新建**：规格要求移到“sqlite_provisioned_scope 的 owner 测试文件”，但仓库中不存在按该模块归属的测试文件，5D 设计 §9 的 owner 也指向已删除的迁移测试。

删除合计：四个迁移测试文件共 31 个函数，其中删除 26（control 6、workspace 5、submit 6、archive 9）、移动 2（archive seed）、改写 3（archive DDL）；review 迁移测试删除 6；另改写 1（enum）。合计删除 32 个函数。

## 8. 文档改写（提交 1）

规格 §4 列出的范围均已改写：设计 DC6 行（行 50）、§1 兼容性段（行 81）、DC9 删除行（行 407）、§10 前向 migration 条目（行 568）、§12 测试归属行（行 638）；执行计划 S2a/S2b 的验收文字、路径预算中的 `test_*_control_db_migrations.py` 与 `migrations.py`、§6 判定表；Business Lifecycle §1A 的 D6 措辞（引言、第 2 条、第 3 条；第 1、4 条未改）；`vnext/deploy/README.md` 的升级流程（改为说明 schema 不符即拒绝启动与删除重建）。

**超出规格逐条列举的改动**（均为 S2a/S2b 的 control DB migration 条目，或指向已删除文件的描述，已逐处核对）：
- 执行计划 S2a 内容第 6 条（行 128）“需 control DB migration”、S2b 内容第 6 条（行 159）、S2b 验收（行 169）；
- 执行计划 S2a 路径预算（行 302、314）与 S2b 路径预算（行 342、360）中的模块与测试文件名；
- 设计 §12 行（行 638）：指向已删除测试文件的 control DB migration 测试归属行。

Business Lifecycle §1A 中第 1 条与第 4 条未改；§1A 行 115 的“migration/seed 保障”未改（见 §9）。

## 9. 冲突描述清单（未改，交审核方或 owner）

| 文件:行 | 现行描述 | 处理建议 |
| --- | --- | --- |
| `contracts/business-lifecycle-and-state.md:301` | §8：“control DB 以前向 migration 增加，不做兼容回填” | D6 只授权 §1A 的改写，本条未改。建议 owner 改为基线 schema 规则 |
| `contracts/business-lifecycle-and-state.md:322–323` | §9A：“migration 拒绝两个不同 scope 指向同 Repository…原数据和 migration version 完整保留” | 迁移专属验收，无对应运行时测试（与契约第 3 条相关）。建议 owner 决定保留为运行时 seed 验收或删除 |
| `contracts/business-lifecycle-and-state.md:332` | §9A：`test_archive_control_db_migrations.py` 拥有 migration/seed/update 归属矩阵 | 该文件已删除。建议 owner 指定 seed 规则的 owner 文件（实施方新建了 `test_provisioned_scope_seed.py`） |
| `contracts/business-lifecycle-and-state.md:115` | §1A.2：“不将文档确认表述为已存在的 migration/seed 保障” | 按 D6“其他内容不变”未改。建议 owner 改为 seed 保障 |
| 执行计划 §8.5 行 542、551 | S2b.1、S2b.6 工作项中的 “control DB migration” | 位于 §8（阶段推进约定），不在规格列出的 §2/§3/§6 范围，未改 |
| 执行计划 §3 S4 路径预算行 389、397 | `infrastructure/control_db/{migrations,...}.py` 与 `test_*_control_db_migrations.py` | S4 条目，不在规格范围，未改。S4 实施前需修订 |
| `AGENTS.md:11` | “control DB schema 的演进方式以 owning 设计为准（当前为 P5 收口设计 DC6 的前向 migration）” | 规格：G3 通过后由审核方更新，未改 |
| `docs/backend-vnext/refactoring/formal/adr/0019-commit-canonical-metadata-authority.md:76` | “control DB 新增前向 migration；compose harness 的初始基线改为空提交” | accepted ADR，未改。建议审核方决定是否加注 |
| 设计 行 81 后半段 | “新增列允许旧行为空，旧行在新判定中按‘不可用’处理…derived-stale 拒绝” | 在“结构不符即拒绝 + 删除重建”规则下，同一 schema 内不会产生旧行。该段是否保留由审核方决定，未改 |

以下保留，不属于 G3 范围：设计行 343、350、369、713，BL 行 271–272、297（在线 ruleset 迁移、`SYSTEM_MIGRATION`、STORAGE_BREAKING 与“不自动升级 SQLite schema”的非目标表述）。`formal/README.md`、`testing-conventions.md` 无冲突。

## 10. 实施中的偏差与补充（请审核方确认）

1. **提交结构**：规格提交 3 并入提交 2（见 §1）。
2. **read-only 预检**：规格 D1 要求结构不符“不修改文件”。`connect_control_db` 的 WAL profile 会写入已存在的 SQLite 文件头（已用探针验证：对 rollback-journal 模式的外来库，先调用 profile 会改变文件字节；先调用 `verify_control_db_file`（`mode=ro`）则拒绝且字节不变）。因此新增 `verify_control_db_file`，在 profile 之前只读检查非空文件；空库和不存在的文件仍由 `bootstrap_control_db_schema` 创建。
3. **错误消息**：规格要求消息只含对象名。实现区分“unexpected objects”（库中多出的）与“missing or changed objects”（缺失或定义不同），各最多列 8 个，超出以 “and N more” 表示。
4. **非 SQLite 文件**：规格 D1 要求“根本不是 control DB”抛 `UnsupportedSchemaVersion`。`verify_control_db_file` 将 `sqlite3.DatabaseError` 映射为 `UnsupportedSchemaVersion`，`OperationalError` 中的 busy/locked 仍映射为 `StoreBusy`。
5. **D4 前提已核对**：`workspace_records_open_exact_scope` 是 `UNIQUE` 部分索引，列为 `(owner_actor_id, gateway_device_external_key, business_project_id) WHERE state = 'OPEN'`，与被删除的 `_assert_workspace_bootstrap_integrity` 的分组一致。
6. **运行时行为**：仅 D1 规定的启动拒绝。worker 路径的失败输出由进程级测试 `test_module_worker_failure_is_nonzero_and_redacted`（`structure_mismatch` 与 `corrupt` 两个参数）验证：非零退出，输出含 `operation_worker_failed`，不含路径与 token；消息只含对象名。HTTP 路径由 `test_prepare_backend_runtime_rejects_control_db_with_a_different_schema` 在 `prepare_backend_runtime` 层验证（抛出 `UnsupportedSchemaVersion`，文件字节不变）。HTTP 进程的非零退出由代码路径核对：`create_app` 不捕获该异常，uvicorn 工厂失败向上传播，未做进程级验证。

## 11. 运行检查记录（非门禁，记录供审核对照）

- 提交 1（`6d2d11a7a9`）：五包 ruff/mypy 均 exit 0；`import_rules` exit 0；`tests/test_architecture.py` 77 passed。日志 `g3-checks-commit1.log`。
- 提交 2（`60f90c1e7f`）：五包 ruff/mypy 均 exit 0；`import_rules` exit 0；`tests/test_architecture.py` 77 passed。日志 `g3-checks-commit2.log`。
- 提交 2：backend `pytest -m unit` 2555 passed，167 deselected，exit 0。日志 `g3-backend-unit-commit2.log`。
- 提交 2：控制 DB 相关 focused 与 integration/process 组（schema、seed、review、architecture、store、readiness、worker、recovery、takeover、submit worker process）273 passed，exit 0。日志 `g3-focused-control-db-commit2.log`。
- 注：`g3-backend-unit-commit2-candidate.log` 为在 read-only 预检前的候选运行，已被 `g3-backend-unit-commit2.log` 取代，不作为证据。

## 12. 门禁与 carried：未执行

- 门禁提交 V：**未形成**（停止）。未运行 `build-repository-service-image.sh` 与 `run-tests.sh`，无 provenance，无三镜像 image ID，无 carried 判定。
- 因此本交接**不声明**当前 HEAD 通过任何容器门禁，也不声明 `run-tests.sh` 通过。
- 一旦 owner 决定，V 与 carried 需按规格 §6 与 AGENTS.md 在本 worktree 内完成。

## 13. 需要 owner 决定的事项

1. **契约第 3 条的运行时覆盖（阻塞项）**。选项：
   - (a) 接受现状，在审核报告中记为已知缺口；
   - (b) 要求补一条运行时测试。建议内容：在 `test_provisioned_scope_seed.py` 中，先建立一条有效 mapping（scope A → repo-1），再提交一个批次，其中包含有效的新 scope（scope B → repo-2）与一条冲突记录（如 scope C → repo-1）。断言抛出 `ValueError`，scope B 未写入，scope A 的 mapping 与 Head 不变。owner 批准后，实施方在 `p5-g3` 上追加提交，再进入 V。
2. **seed 规则的 owner 测试文件**：规格写“sqlite_provisioned_scope 的 owner 测试文件”，仓库中不存在。当前为新建的 `test_provisioned_scope_seed.py`。是否接受，或指定其他文件。
3. **提交结构**：规格提交 3 并入提交 2（§1、§10 第 1 项），是否接受。
4. **§9 冲突描述**（BL §8、§9A、§1A.2 行 115；ADR 0019；AGENTS.md）由谁改。D6 只授权了 §1A。
5. **同批次内 scope 冲突的两条校验**（§4 第 1 条的缺口）是否一并补测试。
6. **S4 路径预算**（执行计划行 389、397）在 S4 kickoff 前修订。

## 14. 范围核对

`git diff --name-only e2bea5bab2dd3dadb74afd9fb4aa47834ce02c28..HEAD`（HEAD = `60f90c1e7f`）共 26 个路径，全部位于允许范围：

- 文档（提交 1）：`business-lifecycle-and-state.md`、`p5-arch-closure-design.md`、`p5-arch-closure-execution-plan.md`；`vnext/deploy/README.md`。
- control DB 模块：`control_db/__init__.py`、`database.py`、`schema.py`（新增）、`migrations.py`（删除）。
- 调用方：未改动 `bootstrap/*`（调用形式不变）；`tests/support/submit_job_harness.py` 为测试支撑调用方。
- 测试：`test_architecture.py`、`test_backend_readiness.py`、`test_control_db_schema.py`（新增）、`test_provisioned_scope_seed.py`（新增）、`test_operation_job_recovery.py`、`test_operation_recovery_process.py`、`test_operation_takeover.py`、`test_operation_worker_integration.py`、`test_operation_worker_process.py`、`test_review_persistence.py`、`test_sqlite_operation_store.py`、`test_sqlite_operation_store_integration.py`、`test_submit_worker_process.py`；迁移测试删除 4 个（`test_archive_control_db_migrations.py`、`test_control_db_migrations.py`、`test_submit_control_db_migrations.py`、`test_workspace_control_db_migrations.py`）。
- 本交接：`plans/p5-arch-closure-g3-handoff.md`（H 提交）。

未改动：`AGENTS.md`、`testing-conventions.md`、治理修订计划、G3 规格、`formal/README.md`、历史阶段文档、Compose、镜像、环境变量接线、`uv.lock`、`import_rules` 基线。

## 15. 产物与日志

目录 `/home/dev/gdds-p5-closure-s1-gate-logs/`（worktree 外）：

- 依赖：`g3-uvlock-sha-R0.txt`，`g3-prepare-offline.log`
- 终态对照：`g3-schema-export.py`，`g3-export-old.log`，`g3-terminal-old.json`，`g3-terminal-old.sha256`，`g3-terminal-new-HEAD.json`，`g3-terminal-new-HEAD.sha256`，`g3-schema-compare.py`，`g3-compare-HEAD.txt`
- 生成：`g3-format-baseline.py`，`g3-splice-schema.py`，`g3-assemble-schema.py`（初次生成用，已被 splice 取代），`g3-docs-commit1.py`，`g3-baseline-body.txt`，`g3-terminal-old-sql.txt`
- 检查：`g3-checks.sh`，`g3-checks-commit1.log`，`g3-checks-commit2.log`，`g3-backend-unit-commit2.log`，`g3-focused-control-db-commit2.log`，`g3-scope-R0-HEAD.txt`
- 探针：`g3-scratch/wal_probe.py`（WAL profile 对外来库字节的影响，§10 第 2 项）

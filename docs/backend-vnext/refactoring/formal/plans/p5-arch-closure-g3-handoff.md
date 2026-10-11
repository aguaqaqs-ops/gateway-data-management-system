# P5 架构收口 G3 实施交接（门禁与 carried 记录）

状态：**G3 实施完成，门禁提交 V 通过。** 权威 runner 在 V 上 exit `0`；五包 ruff/mypy、`import_rules`、架构 focused 检查在 V 上全部通过。V→H 的 carried 判定在本提交之后、于同一 worktree 执行，结果记录于 `g3-carried-check-H.log` 末行 `RESULT`（见 §4.3，并在实施方最终回复中报告）。等待独立审核；审核通过后由审核方打 `p5-g3-exit` 并合并 main。

日期：2026-10-11
分支 / worktree：`p5-g3` / `/home/dev/gdds-p5-g3`（保留；未推送，未打 tag，未合并 main）
R0：`e2bea5bab2dd3dadb74afd9fb4aa47834ce02c28`（main 祖先；建 worktree 时 HEAD 相同，status 为空）
V（门禁提交，最后一个非 handoff 提交）：`dad131350bac48ade02a8ef1f19c4ef9387a05ca`
H（本提交，只改本文件）：`git log -1` 所示提交。

## 1. 提交序列

| 序 | SHA | 提交 | 内容 |
| --- | --- | --- | --- |
| 1 | `6d2d11a7a9` | `docs(p5-g3): rewrite control DB schema and migration wording` | 设计 DC6、§1 兼容性段、§10、DC9 删除行、§12 行；执行计划 S2a/S2b 的 migration 条目；BL §1A（D6）；deploy README |
| 2 | `60f90c1e7f` | `feat(p5-g3): create the control DB from a single schema` | `schema.py`；运行时切换；只读预检；删除 `migrations.py` 与迁移专属测试；新增 `test_control_db_schema.py`、`test_provisioned_scope_seed.py`；其余测试去除 ledger 与 `now=` |
| 3 | `9b120bd002` | `docs(p5-g3): record G3 stop at the contract coverage gate` | 停止记录（第一版 handoff） |
| 4 | `7989117825` | `docs(p5-g3): align migration references with the single baseline rule` | owner §9 决定：BL §8、§9A、§1A.2；ADR 0019 加注；设计 81 行后半段删除；执行计划 §8.5 与 S4 路径预算 |
| 5（V） | `dad131350b` | `test(p5-g3): refuse rejected seed batches as a whole without partial writes` | 契约第 3 条的运行时测试（§2） |
| H | 本提交 | `docs(p5-g3): record G3 gate result and carried procedure` | 本文件 |

偏离规格的提交形态：规格提交 3（只删不改）并入提交 2。原因：`test_production_reachability_matches_frozen_baseline` 要求运行时停止引用 `migrations.py` 时同一提交删除该模块，基线不得扩展。owner 已接受。

## 2. owner 决定的执行

1. **契约第 3 条，选 (b)。** 在 `test_provisioned_scope_seed.py` 增加模块级参数表 `REJECTED_SEED_BATCHES`（5 行）。每个批次先列有效的新 scope `_NEW_SCOPE`（device-2/project-2 → repo-2），再列使批次无效的一条记录。断言抛出约定的 `ValueError`，并断言 `provisioned_scope_mappings`、`baseline_node_records`、`baseline_head_records` 三张表的快照与拒绝前完全相同。
   - 校验阶段拒绝（未写入任何行）：
     - `repository-owned-by-another-scope`：C→repo-1，repo-1 已属于 A（owner 建议的用例）；
     - `repository-assigned-to-two-scopes`：同一批次 repo-2 分给两个 scope；
     - `scope-assigned-to-two-repositories`：同一批次 device-2/project-2 分给两个 repo。
   - 应用阶段拒绝（`_NEW_SCOPE` 已在同一事务内写入，靠回滚恢复）：
     - `first-seed-with-nonzero-head-version`：新 repo 首次 seed 使用 `baseline_head_version 3`；
     - `initial-identity-mismatch`：repo-1 的 INITIAL node 与库中不一致。
   - 应用阶段两行是 owner 列出三条之外的补充：owner 列出的三条都在校验阶段拒绝，不经过事务回滚；“无部分写入”中依赖回滚的部分由这两行覆盖。
   - 回滚检验：临时把 `ControlDbUnitOfWork.__exit__` 改为异常时也 COMMIT，运行该文件，两条应用阶段行 FAILED，校验阶段三条与其余两个既有测试仍 PASS；随后 `git checkout` 恢复 `database.py`，工作区只剩测试文件。
   - 实现未改。测试未暴露实现不满足契约，因此未触发“停止并报告”。
2. **“禁用后重新启用”不补**，作为已知缺口记入 §5。
3. **owner 接受** `test_provisioned_scope_seed.py` 作为 seed 规则的 owner 文件。
4. **owner 接受** 提交 2、3 合并（§1）。
5. **文档对齐**（提交 4）按 owner 决定执行，见 §8.2、§9。AGENTS.md 未改。

## 3. 前置核对与门禁前检查

- R0 与 kickoff 一致；worktree 建立于 R0；`legacy` 符号链接建于 worktree 内（不在提交中）。
- 依赖准备：`GATEWAY_DEV_OFFLINE=1 ./vnext/scripts/prepare-dev-dependencies.sh` exit 0；五个 `uv.lock` 的 SHA256 与 R0 相同（`g3-uvlock-sha-R0.txt`），提交后仍相同。
- 门禁前检查（`g3-gate-V-preflight.log`，运行前记录）：HEAD `dad131350b`，分支 `p5-g3`，`git status` 为空，`pgrep -x dolt` 为空，无 compose project 标签的容器，`docker compose ls` 为空，8000 端口无监听。
- 镜像目录中存在历史测试残留镜像（`gateway-backend-gate-*`、`gateway-repository-client-e2e*:local` 等），按规格未做任何 docker 清理，也未触碰 `gateway-repository-client-e2e:local` 与 `gateway-repository-client-e2e-base:local`。

## 4. 门禁 V：权威 runner、镜像与 provenance

### 4.1 repository-service 镜像

- 命令：`./vnext/scripts/build-repository-service-image.sh`，exit `0`。日志 `g3-gate-V-rs-image-build.log`，起止记录 `g3-gate-V-rs-image-build.summary`。
- 基于保留的依赖基础镜像 `gateway-p2r1-repository:lock-6dc9659f0aee`（repository_service/uv.lock SHA `6dc9659f…`，未变）。
- `build_context_digest.py identity`（V）：`{"schema": "gateway.p2r1.build-identity", "schema_version": 1, "candidate_sha": "dad131350bac48ade02a8ef1f19c4ef9387a05ca", "build_input_revision": "29f7dfd3c349f9943590765c2b90ca49e47f8eb3", "source_tree_sha256": "sha256:2c92331c021958fc4ea425973e59695195f88397e1a39e42572cb3e874f5ff5f"}`。
- 镜像 `gateway-repository-service:local`：ID `sha256:fa88988be830b20ac3e54c2794fd1a78aea99452b1c01de9812a0089ec49e7c7`；labels `gateway.p2r1.build-input-revision=29f7dfd3c349f9943590765c2b90ca49e47f8eb3`、`gateway.p2r1.source-tree-sha256=sha256:2c92331c021958fc4ea425973e59695195f88397e1a39e42572cb3e874f5ff5f`；`org.opencontainers.image.revision=dad131350b…`（revision 不参与比较）。
- 身份说明：identity 覆盖 `vnext/repository_service`、`vnext/repository_contracts` 与三个构建定义文件（`vnext/.dockerignore`、`vnext/deploy/compose.yaml`、`vnext/scripts/build-repository-service-image.sh`）。它与 S1 候选 `d9c20976` 的值不同，原因是 S1 之后 main 上的其他提交改动了其中的 `vnext/.dockerignore`、`vnext/repository_service/tests/support/compose_lifecycle_harness.py` 与 `vnext/repository_service/tests/test_compose_lifecycle_harness.py`；本轮 R0..V 在这些身份路径上无差异（`git diff --stat R0 V` 为空）。

### 4.2 权威 runner

- 命令：`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`（无 `--ignore`），包装脚本 `g3-gate-run-tests.sh attempt1`。
- 日志：`g3-gate-V-run-tests-attempt1.log`；起止与 runner exit code：`g3-gate-V-run-tests-attempt1.summary`。
- 起止 HEAD：`dad131350bac48ade02a8ef1f19c4ef9387a05ca` / `dad131350bac48ade02a8ef1f19c4ef9387a05ca`；`git status` 起止均为空。运行期间未提交、未重建或重新 tag 镜像；provenance 写入的是 git 忽略的测试支撑文件。
- runner 自身 exit code：**`0`**（`GATE_DONE attempt=attempt1 runner_exit_code=0`）。

| 批次 | 结果 |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend（全部，含 compose 旅程） | 2727 passed，1 warning（既有 StarletteDeprecationWarning），耗时 19:54 |
| repository_service（parallel，`-n 48`） | 1681 passed，1 skipped |
| repository_service（serial，`-n 0`） | 205 passed，1682 deselected |

- 日志全文 96 行，无 FAILED 或 ERROR 行。
- 运行后 `vnext/backend/tests/support/.last_compose_gate_provenance.json` 复制为 `g3-gate-V-compose-provenance-attempt1.json`（mtime 13:12:43，位于本次运行期间）。
- provenance：compose project `ordered-bisect-b-1813352-baseline`；
  - backend `sha256:e9bca238b9e688c337a52366a3600946761a53021ed0bbe1c35ca55b673c838d`；
  - worker `sha256:6fcc90ad5a95aa62a92844af9884e821cd8ce3b7c28829980ed1d192a890f70a`；
  - repository-service `sha256:fa88988be830b20ac3e54c2794fd1a78aea99452b1c01de9812a0089ec49e7c7`（与运行前构建的 RS 镜像一致，运行未重建）。
- `docker image inspect` 三镜像：`g3-gate-V-image-inspect-attempt1.log`。backend、worker 的 labels 只含 compose project/service/version，无 source identity label（与 AGENTS.md 一致，按 carried 第 3 条处理）。

### 4.3 carried 判定（V → H）

在同一 worktree（`/home/dev/gdds-p5-g3`）内、H 提交之后执行 `g3-carried-check.sh dad131350bac48ade02a8ef1f19c4ef9387a05ca <provenance> g3-carried-check-H`，日志 `g3-carried-check-H.log`。判定结果见该日志末行 `RESULT`。过程如下：

- (a) `git diff --name-only V H` 必须只含本文件；另检查不含容器边界路径（Dockerfile、依赖锁、Compose、entrypoint、env 接线、healthcheck、Docker e2e 测试、harness 与其 support 模块）。
- (b) 在 H 上用 `build_context_digest.py identity` 重算 repository-service 身份，`build-input-revision` 与 `source-tree-sha256` 必须等于 RS 镜像 label。
- (c) backend、worker 在同一 worktree 中以 provenance 的 project 名 `ordered-bisect-b-1813352-baseline` 连续重建两次，两次之间不运行任何测试；每次的 image ID 都必须等于 provenance 中实际运行容器的 image ID。

## 5. 契约对照表（Business Lifecycle §1A.2 第 1–4 条）

| 条款 | 运行时测试 | 结论 |
| --- | --- | --- |
| 1. 一个 Repository 只能得到一个 exact scope | `test_provisioned_scope_seed.py::test_seed_rejects_cross_scope_repository_reassignment`（跨批次，已持久化归属）；`test_rejected_seed_batch_is_refused_as_a_whole[repository-assigned-to-two-scopes]`（同批次） | 有覆盖（同批次缺口由 V 补齐） |
| 2. 已有固定归属时只接受同 scope | 同上 reassignment 测试；`test_seed_restart_does_not_regress_advanced_head`（同 scope 重复 seed 被接受）；`[scope-assigned-to-two-repositories]`（同批次一个 scope 分两个 repo） | 有覆盖 |
| 3. 任一跨 scope、无法解释的历史或初始归属冲突使整个 seed 批次 / mapping update 事务拒绝，无部分写入；失败不改既有 mapping、Head 或历史 | `test_rejected_seed_batch_is_refused_as_a_whole` 的 5 行：`[repository-owned-by-another-scope]`、`[repository-assigned-to-two-scopes]`、`[scope-assigned-to-two-repositories]`（校验阶段）；`[first-seed-with-nonzero-head-version]`、`[initial-identity-mismatch]`（应用阶段，靠回滚） | **有覆盖（由 V 补齐）。** 此前唯一覆盖来自被删除的迁移测试 |
| 4. 同 scope 的重复 seed、禁用/启用、重启沿用合法身份，不覆盖已推进的业务 Head | 重复 seed 与重启、Head 不回退：`test_seed_restart_does_not_regress_advanced_head`；禁用的消费方效果：`test_review_http.py`（provisioned mapping is disabled）、`test_archive_transactions.py::test_start_archive_replay_requires_transaction_fresh_enabled_mapping`、`test_submit_transactions.py::test_t1_replay_rejects_when_mapping_disabled_after_concurrent_winner`、`test_history_projection.py::test_get_project_history_rejects_disabled_mapping_in_same_transaction` | **部分覆盖。已知缺口：禁用后重新启用、沿用合法身份，没有 seed 级测试**（owner 决定不补） |

注：BL §9A 的 owner 文件已改为 `test_provisioned_scope_seed.py`（提交 4）。5D 设计 §9 是历史阶段记录，仍写着已删除的迁移测试文件，按历史文档政策未改写。

## 6. 停止条件逐项核对（本轮）

- 终态对照有无法解释的差异，或需要改变表结构：**否**（0 差异，§11.1）。
- 需要改变运行时行为、HTTP DTO、golden、digest 或 checkpoint 载荷：**否**。唯一运行时行为变化是规格 D1（启动拒绝结构不符或非 SQLite 的 control DB）。本轮 seed 实现未改。
- 契约对照表有条款只被迁移测试覆盖：**原触发（第 3 条），已由 owner 决定 (b) 解决**，现由运行时测试 `test_rejected_seed_batch_is_refused_as_a_whole` 覆盖。
- 测试暴露实现不满足契约：**否**（回滚检验与 5 行全部与契约一致；门禁 V 全部通过）。
- `import_rules` 增长或新依赖：**否**。`import_rules` 为 3 / 0 / 14。
- 运行时依赖 `control_schema_migrations`、迁移私有函数或 `now` 的其他用途：**否**（精确名称搜索 `vnext/` 只命中测试夹具）。
- 设计 §14 停止条件：**否**。

## 7. now 参数核对

- `initialize_control_db(db_path, now)`、`initialize_and_verify_control_db(db_path, now)`：迁移台账时钟，已删除。运行时调用方（`bootstrap/composition.py`、`bootstrap/operation_worker.py`）本就不传 `now`。测试与 support 中 31 处传参删除（9 个文件，其中 5 处位于随后删除的迁移测试文件）。
- `ControlDbUnitOfWork(now=...)`：事务时钟，与迁移无关，保留。
- `MIGRATION_TIME` 在 `test_sqlite_operation_store_integration.py` 中改名为 `FIXED_TRANSACTION_TIME`。

## 8. 测试处置与文档改写

### 8.1 测试（文件与数量）

| 文件 | R0 函数数 | 处置与理由 |
| --- | --- | --- |
| `test_control_db_migrations.py` | 6 | 删除。fresh bootstrap → `test_empty_control_db_gets_every_table_and_index`；重复调用 → `test_repeat_bootstrap_writes_nothing`；失败回滚 → `test_failed_schema_statement_rolls_back_every_object`；版本更高拒绝 → 结构不符参数表；迁移时钟与 v0 推进 → 删除（历史迁移专属） |
| `test_workspace_control_db_migrations.py` | 5 | 删除。创建、重复、回滚、拒绝 → 同上新测试；历史 v1 文件重开并 seed → 删除（历史迁移专属；seed 运行时行为由 `test_provisioned_scope_seed.py` 承担） |
| `test_submit_control_db_migrations.py` | 6 | 删除。submit 表创建 → 表集合断言；重复/回滚/拒绝 → 同上；历史 v2 重开升级、损坏 v2 外键拒绝升级 → 删除（新基线无升级路径）。submit 表列级约束由 `test_submit_transactions.py` 等运行时测试承担 |
| `test_archive_control_db_migrations.py` | 14 | 删除 9：v4→v5 迁移与迁移时历史校验、回滚、mapping 重建（历史迁移专属）。移动 2 到 `test_provisioned_scope_seed.py`：seed 重启不回退、跨 scope 重分配拒绝。改写 3 到 `test_control_db_schema.py`：baseline head 跨 Repository 引用（外键）、archive 表创建、disposition 选中唯一索引 |
| `test_review_persistence.py` | 21 | 删除 6：v4 bootstrap、重复、回滚、版本拒绝、历史 v3 重开、backfill（均为迁移专属）。enum 测试改写为 `test_review_schema_enums_match_domain_literals`（从 `schema.py` DDL 解析 IN 列表）。其余 repository 行为测试保留（函数 15 个，参数化后 18 项） |

新增与改写：

- `test_control_db_schema.py`（新增）：8 个函数，14 项。空库创建全部表与索引（精确集合）；空文件创建；重复调用不写入（`total_changes` 与文件字节）；注入失败 DDL 回滚；结构不符（额外表、缺表、列定义改变、缺索引、额外索引、旧台账表、无关 SQLite 文件）被拒绝且文件字节不变；非 SQLite 文件被拒绝且字节不变；archive 表与 disposition 唯一索引；baseline head 外键。
- `test_provisioned_scope_seed.py`（新增，owner 已接受）：2 个函数 + 5 个参数化行，共 7 项（§2）。
- `test_backend_readiness.py`：新增 `test_prepare_backend_runtime_rejects_control_db_with_a_different_schema`，HTTP 启动层的失败关闭。
- `test_sqlite_operation_store.py`（规格列表未包含）：两处直接调用的旧 bootstrap 改为 `bootstrap_control_db_schema(connection)`。
- `test_operation_worker_process.py`：`higher_schema` 参数改为 `structure_mismatch`（在库中加入 `unexpected_probe`），仍断言非零退出、`operation_worker_failed`、不泄露路径与 token。
- `test_sqlite_operation_store_integration.py`、`test_operation_worker_integration.py`：去除 ledger 断言。
- `test_architecture.py`：`migrations.py` 存在性断言改为 `schema.py`。

删除合计：四个迁移测试文件共 31 个函数（删除 26、移动 2、改写 3）；review 迁移测试删除 6；合计删除 32 个函数。

### 8.2 文档（提交 1 与提交 4）

- 提交 1（`6d2d11a7a9`）：规格 §4 列出的范围——设计 DC6 行（50）、§1 兼容性段（81）、DC9 删除行（407）、§10（568）、§12 行（638）；执行计划 S2a/S2b 的内容项、验收、路径预算与 §6 判定表；BL §1A（D6）；deploy README。
- 提交 4（`7989117825`，owner §9 决定）：
  - BL §8（301）：control DB 以单一基线 schema 创建，schema 与代码不符即拒绝启动，删除本地 control DB 后重建；
  - BL §9A（322–323）：改为运行时 seed 验收，失败整批回滚，既有 mapping/Head/历史完整保留（删去 migration version）；
  - BL §9A（331–332）：owner 文件改为 `test_provisioned_scope_seed.py`，并注明 G3 取代 5D §9 中对应的迁移测试文件；
  - BL §1A.2（114–115）：删去 migration；seed 与 mapping update 规则由实现承担，由 `test_provisioned_scope_seed.py` 验证；禁用后重新启用尚无专门测试；
  - ADR 0019（76）：正文不变，加注“control DB schema 规则由 G3 取代，见设计 DC6”；
  - 设计第 81 行后半段（旧行按“不可用”处理）删除；
  - 执行计划 §8.5（542、551）：改为“control DB 基线 schema 直接修改；测试按表归属”；
  - 执行计划 S4 路径预算（389、397）：`{schema,...}` 与 `test_control_db_schema.py（按表归属）`。
- 超出规格逐条列举的改动（均为 S2a/S2b 或指向已删文件的描述，已在提交 1 中逐处核对）：执行计划 S2a 内容第 6 条、S2b 内容第 6 条与验收；S2a/S2b 路径预算的模块与测试文件名；设计 §12 行。

## 9. 冲突描述清单（更新）

| 文件:行 | 现行描述 | 状态 |
| --- | --- | --- |
| BL §8（301） | “control DB 以前向 migration 增加” | 已改（提交 4） |
| BL §9A（322–323） | migration 拒绝跨 scope 共享 | 已改为运行时 seed 验收（提交 4） |
| BL §9A（332） | owner 文件指向已删除的迁移测试 | 已改为 `test_provisioned_scope_seed.py`（提交 4） |
| BL §1A.2（115） | “migration/seed 保障”的表述 | 已改（提交 4） |
| 执行计划 §8.5（542、551） | S2b.1、S2b.6 的 control DB migration | 已改（提交 4） |
| 执行计划 S4 路径预算（389、397） | `migrations` 模块与迁移测试文件 | 已改（提交 4） |
| ADR 0019（76） | “control DB 新增前向 migration” | 正文不变，已加注（提交 4） |
| 设计 行 81 后半段 | 旧行按“不可用”处理 | 已删除（提交 4） |
| `AGENTS.md:11` | “当前为 P5 收口设计 DC6 的前向 migration” | **未改**：规格指定 G3 通过后由审核方更新 |
| 5D 设计 §9（历史阶段文档） | 指向 `test_archive_control_db_migrations.py` | **未改**：历史阶段记录不改写 |
| 设计 行 343、350、369、713；BL 行 271–272、297 | 在线 ruleset 迁移、`SYSTEM_MIGRATION`、STORAGE_BREAKING、“不自动升级 SQLite schema” | 非目标，保留 |

`formal/README.md`、`testing-conventions.md` 无冲突。

## 10. 实施偏差与补充（交审核方复核）

1. 提交形态：规格提交 2、3 合并（§1）。owner 已接受。
2. 只读预检：规格 D1 要求结构不符时不修改文件；`connect_control_db` 的 WAL profile 会写入已存在的 SQLite 文件头。探针证实（`g3-scratch/wal_probe.py`）：profile 先执行则外来库字节改变；预检先执行则拒绝且字节不变。因此新增 `verify_control_db_file`（`mode=ro`），在 profile 之前只读检查非空文件。
3. 错误消息：列出 unexpected objects（库中多出的）与 missing or changed objects（缺失或定义不同），各最多 8 个，超出以 “and N more” 表示。只含对象名。
4. 非 SQLite 文件：映射为 `UnsupportedSchemaVersion`；busy/locked 仍为 `StoreBusy`。
5. D4 前提已核对：`workspace_records_open_exact_scope` 为 `UNIQUE` 部分索引，列 `(owner_actor_id, gateway_device_external_key, business_project_id) WHERE state = 'OPEN'`，与被删除的 `_assert_workspace_bootstrap_integrity` 的分组一致。
6. 运行时行为：worker 路径的失败输出由进程级测试 `test_module_worker_failure_is_nonzero_and_redacted`（`structure_mismatch` 与 `corrupt`）验证：非零退出，含 `operation_worker_failed`，不含路径与 token。HTTP 路径由 `test_prepare_backend_runtime_rejects_control_db_with_a_different_schema` 验证到 `prepare_backend_runtime` 层（抛出 `UnsupportedSchemaVersion`，文件字节不变）。**HTTP 进程级非零退出未做进程级测试**，依据代码路径核对：`create_app` 不捕获该异常，uvicorn 工厂失败向上传播。owner 已指定由审核方复核。
7. 测试文件 `test_sqlite_operation_store.py` 超出规格列表，已改为新入口。
8. 超出规格列表的文档改动见 §8.2。

## 11. 运行检查记录

### 11.1 V 上的检查（dad131350b，本轮）

- 五包 ruff 与 mypy：`g3-checks-V.log`，每包 `ruff_exit=0 mypy_exit=0`。
- `import_rules`：exit `0`，3 / 0 / 14。
- `tests/test_architecture.py`：77 passed，exit `0`。
- 终态对照（V）：导出 `g3-terminal-new-V.json`，sha256 `da99c68fdea335884b54b99fa9074313a174ae92681d0afc5a528e91cb666ae2`（与提交 2 时的导出相同，`schema.py` 的 DDL 未再改动）；与 R0 导出比较，`g3-compare-V.txt`，exit `0`，layer 1 零差异，layer 2 43/43 一致，无残留差异。

### 11.2 每个提交的包检查（已完成）

- 提交 1（`6d2d11a7a9`）、提交 2（`60f90c1e7f`）：五包 ruff/mypy 均 exit 0；`import_rules` exit 0；`tests/test_architecture.py` 77 passed。日志 `g3-checks-commit1.log`、`g3-checks-commit2.log`。
- 提交 2：backend `pytest -m unit` 2555 passed，167 deselected，exit 0。日志 `g3-backend-unit-commit2.log`。
- 提交 2：控制 DB 相关 focused 与 integration/process 组 273 passed，exit 0。日志 `g3-focused-control-db-commit2.log`。
- 提交 4（文档）与 V：backend ruff 与 mypy（strict，462 个源文件）exit 0；`tests/test_provisioned_scope_seed.py` 7 passed。

### 11.3 门禁 V 与 carried

- 门禁 V 的 runner、provenance 与三镜像记录见 §4。
- carried 判定见 §4.3 与 `g3-carried-check-H.log`。

## 12. 范围核对

- `git diff --name-only e2bea5bab2dd3dadb74afd9fb4aa47834ce02c28..V`：28 个路径，记录于 `g3-scope-R0-V.txt`。分类：docs 5（BL、设计、执行计划、ADR 0019、停止记录）；`vnext/backend/src` 4（`control_db/__init__.py`、`database.py`、`schema.py` 新增、`migrations.py` 删除）；`vnext/backend/tests` 18；`vnext/deploy/README.md` 1。全部在允许范围内。
- `git diff --name-only V..H`：仅本文件（由 `g3-carried-check-H-diff-names.txt` 记录）。
- 未改动：`AGENTS.md`、`testing-conventions.md`、治理修订计划、G3 规格、`formal/README.md`、历史阶段文档、Compose、Dockerfile、镜像构建脚本、依赖锁、环境变量接线、`import_rules` 基线。

## 13. 已知缺口与待审核事项

1. **契约第 4 条：禁用后重新启用、沿用合法身份**：无 seed 级测试（owner 决定不补，记为已知缺口）。
2. 5D 设计 §9 历史记录仍指向已删除的迁移测试文件（不改写）。
3. `AGENTS.md:11` 由审核方在 G3 通过后更新。
4. HTTP 进程级非零退出：代码路径核对，未做进程级测试（§10 第 6 项）。
5. 只读预检与 `test_sqlite_operation_store.py` 的改动超出规格列表（§10）。
6. carried 判定按 AGENTS.md 执行；(c) 连续重建两次，覆盖“两次构建之间不运行任何测试”的要求。

## 14. 产物与日志

目录 `/home/dev/gdds-p5-closure-s1-gate-logs/`（worktree 外）。关键文件：

- 终态对照：`g3-schema-export.py`、`g3-schema-compare.py`、`g3-terminal-old.json`（sha256 `ef36c416512d377358b2af280ef22a2e17b4db3f551a8d4589ad7b5ad03cc73d`）、`g3-terminal-new-V.json`（sha256 `da99c68fdea335884b54b99fa9074313a174ae92681d0afc5a528e91cb666ae2`）、`g3-compare-V.txt`；提交 2 时的导出 `g3-terminal-new-HEAD.json`、`g3-compare-HEAD.txt`。
- 门禁 V：`g3-gate-V-preflight.log`、`g3-gate-V-rs-image-build.log` / `.summary`、`g3-gate-V-run-tests-attempt1.log` / `.summary`、`g3-gate-V-compose-provenance-attempt1.json`、`g3-gate-V-image-inspect-attempt1.log`、`g3-gate-run-tests.sh`；五包检查 `g3-checks-V.log`。
- carried：`g3-carried-check.sh`、`g3-carried-check-H.log`、`g3-carried-check-H-diff-names.txt`。
- 其他检查：`g3-checks-commit1.log`、`g3-checks-commit2.log`、`g3-backend-unit-commit2.log`、`g3-focused-control-db-commit2.log`。
- 探针：`g3-scratch/wal_probe.py`（WAL profile 对外来库字节的影响）。

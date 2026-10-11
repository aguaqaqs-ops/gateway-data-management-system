# P5 架构收口 G3（control DB 基线 schema）独立审核

- 结论：**通过**
- 日期：2026-10-11
- 审核对象：`p5-g3` @ `6dfb5bd6c9a2da81cf3979afc05d8f20a562aafa`（H；门禁提交 V = 实现 HEAD = `dad131350bac48ade02a8ef1f19c4ef9387a05ca`），区间 `e2bea5bab2..6dfb5bd6c9`（分支只含实施方提交）。
- 依据：G3 规格（§3 D1–D6、§5–§8，§9 含实施中停止点的 owner 决议 S1–S4）；治理修订计划 G3；设计 DC6、§10、§12、§14；执行计划 §2/§3、§6、§8；
  Business Lifecycle §1A、§8、§9A；AGENTS.md「权威入口的运行前提」「镜像身份等价」；handoff `plans/p5-arch-closure-g3-handoff.md`。
- 审核在只读 detached worktree `/home/dev/gdds-review-g3`（H）与 `/home/dev/gdds-review-g3-r0`（R0，只用于导出旧链终态）中进行。
  carried 复核在实施 worktree `/home/dev/gdds-p5-g3` 中只做一次 backend/worker 重建，期间没有运行测试，HEAD 与 `git status`（clean）前后不变。

## 1. 结论摘要

G3 的目标达成：control DB 由 `infrastructure/control_db/schema.py` 的单一 DDL 序列创建，已有库只在结构与该序列在内存库中产生的结构完全相同时被接受、且不写入；
否则以 `UnsupportedSchemaVersion` 拒绝，文件字节不变。`migrations.py`、台账表、四个版本常量、迁移时钟与两个历史完整性检查已删除，`import_rules` 仍为 3 / 0 / 14。
新基线与旧迁移链终态等价：我用实施方的导出脚本复现了两份导出的 sha256，又用自己写的导出与比较独立复核，没有语义差异（只有 3 张表的索引创建顺序不同，见 §4）。
Business Lifecycle §1A.2 第 1–4 条都有运行时测试，第 3 条的 5 行参数表中两条应用阶段行确实依赖事务回滚（变异验证）。
V 上权威 runner exit 0，V → H 只改 handoff，carried 在 V 的同一 worktree 复现成立。

没有阻塞项；三项非阻塞问题（G3-F1 至 G3-F3）不要求在 tag 前修订。可以在本报告提交上打 `p5-g3-exit`；按 G8 决议，S2a 之前还有 G8b，S2a 的区间起点为 `p5-g8b-exit`。

## 2. Findings

### G3-F1：handoff 对 HTTP 启动失败路径的说明不准确

- 类型：非阻塞建议（记录更正）；是否阻塞：否
- 位置：handoff §10 第 6 项。
- 依据：handoff 写“`create_app` 不捕获该异常，uvicorn 工厂失败向上传播”。实际上 `prepare_backend_runtime` 在 `app.py` 的 lifespan 中调用，`create_app` 本身不会失败；
  失败发生在 uvicorn 的 lifespan startup。我用 `tests/support/http_shutdown_harness.py` 的环境以子进程运行 `python -m gateway_backend.bootstrap.http_server`：
  结构不符的 control DB → 进程 exit 3，日志为 `UnsupportedSchemaVersion: control DB schema does not match this build (unexpected objects: unexpected_probe; …)` 与
  `Application startup failed. Exiting.`，输出不含数据目录路径，控制库未被改动；对照组（schema 正确、Repository 不可达）同样 exit 3。
- 触发场景与影响：结论（非零退出、输出脱敏）成立，只是机制描述有误；不影响行为。进程级退出由 uvicorn 提供，`prepare_backend_runtime` 层的拒绝测试已是该不变量的合适 owner，不要求补进程级测试。
- 最小修正方向：无须修订；本报告即为更正记录。

### G3-F2：seed 参数表的注释与用例数量不符

- 类型：非阻塞建议；是否阻塞：否
- 位置：`vnext/backend/tests/test_provisioned_scope_seed.py`，`REJECTED_SEED_BATCHES` 上方注释。
- 依据：注释写“The first two rows fail in batch validation … The last two fail while records are applied”，参数表实际是 3 行校验阶段、2 行应用阶段。
- 最小修正方向：下次改动该文件时改为“前三行在批次校验阶段失败，后两行在写入阶段失败并依赖回滚”。
- 关闭标准：注释与参数表一致。

### G3-F3：设计 §10 仍有“新增列允许旧行为空”

- 类型：非阻塞建议（文档残留）；是否阻塞：否
- 位置：设计 §10 列表项“control DB 直接修改基线 schema，不做数据回填；新增列允许旧行为空（DC6）”。
- 依据：owner 决议 S4 删去了第 81 行“旧行按不可用处理”的说明；单一基线下不存在旧行，这一项的后半句同样失去意义。
- 最小修正方向：S2a 修改设计 §10 时删去“新增列允许旧行为空”。
- 关闭标准：设计中不再有以“旧行”为前提的 control DB 表述。

## 3. 验收核对

| 验收项（G3 规格 §8 与审核提示词） | 结果 | 证据 |
| --- | --- | --- |
| 终态对照一致，结果与 sha256 写入 handoff | 通过 | 在 R0 worktree 用 `g3-schema-export.py --mode old`、在 H 用 `--mode new` 重导出，sha256 分别为 `ef36c416…3cc73d`、`da99c68f…666ae2`，与 handoff 相同；`g3-schema-compare.py` exit 0（layer 1 零差异，layer 2 43/43）。独立复核见 §4。 |
| 结构不符被拒绝且文件不变；启动映射仍是失败退出、输出脱敏 | 通过 | `test_control_db_schema.py` 的参数表（额外表、缺表、列定义改变、缺索引、额外索引、旧台账表、无关 SQLite 文件）与非 SQLite 用例都断言文件字节不变；`initialize_control_db` 先调用只读的 `verify_control_db_file`，再由 `connect_control_db` 设置 WAL。worker 进程级测试 `structure_mismatch`、`corrupt` 非零退出且脱敏；HTTP 进程见 G3-F1 的复核（exit 3）。 |
| 迁移代码与迁移专属测试已删除；保留测试通过；契约对照表完整 | 通过 | `migrations.py` 与四个迁移测试文件删除；`grep` 无 `control_schema_migrations`、`bootstrap_control_schema`、`bootstrap_workspace_schema` 残留。契约第 1–4 条的运行时测试见 §4。 |
| 五包 ruff/mypy、`import_rules` 3 / 0 / 14；V 上 runner exit 0；provenance 与 carried 记录齐全 | 通过 | 审核 worktree 内五包 0/0，`import_rules` 3 / 0 / 14；V 的日志与 carried 复核见 §4。 |
| 文档改写；设计与执行计划中不再有“control DB 新增前向 migration”的现行描述 | 通过（G3-F3 为残留措辞） | BL §1A.2 引言与第 2、3 条与 D6 目标文字逐字一致，第 1、4 条未改；§8、§9A 的改写限于 owner 决议 S4；ADR 0019 正文未改，只在该行末加注；设计 DC6、§10、§12 与执行计划 §2/§3/§6/§8.5、S4 路径预算已改为基线 schema；deploy README 改为“不符即拒绝、删除本地 control DB（含 `-wal`、`-shm`）后重建”。AGENTS.md 未改（由审核方在通过后更新）。 |
| 停止条件 | 未触发（契约第 3 条的停止已由 owner 决议 S1 处置） | handoff §6；表结构未改，运行时行为只增加 D1 规定的启动拒绝，DTO、golden、digest、checkpoint 未改，未新增依赖。 |

## 4. 实际执行的检查

| 检查 | 命令或方法 | 结果 |
| --- | --- | --- |
| 终态对照（实施方脚本） | R0 与 H 分别重导出，比较 | sha256 与 handoff 相同；compare exit 0 |
| 终态对照（独立） | 自写导出：旧链 `bootstrap_control_schema` + `bootstrap_workspace_schema` 与新 `bootstrap_control_db_schema`，各取 `sqlite_master`（排除台账表）、`table_xinfo`、`foreign_key_list`、`index_list`/`index_xinfo`；SQL 去空白并在引号外转小写后逐对象比较 | 43 个对象名一致；列定义、外键、索引内容一致；43 条 SQL 规范化后全部相同。差异只有 `archive_disposition_records`、`baseline_node_records`、`step_records` 三张表的 `index_list` 顺序（索引的创建先后），索引名、唯一性、partial、列与排序都相同，无语义影响 |
| 重启与并发 | 探针：初始化后干净关闭再启动；另一连接打开时启动；另一连接持有写事务时启动；只读文件 | 均通过；持写事务时为 `StoreBusy`；外来 SQLite 文件被拒绝且字节不变；非 SQLite 文件以 `UnsupportedSchemaVersion` 拒绝 |
| HTTP 进程启动失败 | 子进程运行 `gateway_backend.bootstrap.http_server` | exit 3，脱敏（G3-F1） |
| 契约第 3 条的回滚依赖 | 将 `ControlDbUnitOfWork.__exit__` 临时改为异常时也提交，运行 `REJECTED_SEED_BATCHES` | 应用阶段 2 行失败、校验阶段 3 行通过，与 handoff 一致；未改文件 |
| 契约第 1 条的 disabled mapping | 探针：先 seed disabled 的 A→repo-1，再 seed B→repo-1 | 拒绝（`repository is already owned by a different scope`）；行为正确，但没有测试（§5） |
| 被删测试 | 在 R0 逐个读取被删文件的测试函数 | 删除的是台账推进、迁移时钟、历史版本重开、v4/v5 升级与拒绝、迁移回滚等迁移专属不变量；fresh 创建、重复无写入、失败回滚、版本拒绝由 `test_control_db_schema.py` 的新测试承担；列清单断言不再保留（规格 D5：永久保留行为测试，不复制 DDL）；唯一的约束行为断言（Head 引用他库节点）保留 |
| 五包 ruff 与 mypy | 各包 `uv-consume.sh run ruff check .` / `run mypy` | 全部 0 / 0 |
| `import_rules` | `tests/architecture_baseline.py` 三个基线计数 | 3 / 0 / 14 |
| focused 测试 | `test_control_db_schema.py`、`test_provisioned_scope_seed.py`、`test_review_persistence.py`、`test_architecture.py`、`test_backend_readiness.py`、`test_sqlite_operation_store.py`、`test_sqlite_operation_store_integration.py`、`test_operation_worker_integration.py`、`test_operation_worker_process.py`、`test_archive_transactions.py` | 239 passed |
| V 的门禁记录 | `g3-gate-V-run-tests-attempt1.summary`、runner 日志、provenance、image inspect | runner exit 0；起止 HEAD 均为 V，status 为空；六个批次 242 / 152 / 154 / 2,727 / 1,681 + 1 skipped / 205 passed，无失败；三镜像 ID 与 provenance 一致；RS label 的 revision 为 V |
| carried 复核 | 在 `/home/dev/gdds-p5-g3`：`git diff --name-only V H`；`build_context_digest.py identity`；以 provenance 的 project 名 `ordered-bisect-b-1813352-baseline` 执行一次 `docker compose build backend worker` | (a) 只有 handoff；(b) H 上的 identity（`29f7dfd3…`、`sha256:2c92331c…`）与 RS 镜像 label 相等；(c) backend `sha256:e9bca238…`、worker `sha256:6fcc90ad…` 与 provenance 相同。carried 成立 |

## 5. 验证限制与剩余前置

- 我没有重跑全量 runner，门禁结果取自实施方在 V 上的完整运行日志，并复核了日志、provenance 与 carried。
- 已知测试缺口（行为正确或由消费方覆盖，非 G3 引入）：seed 层“禁用后重新启用并沿用合法身份”（handoff 已记录）；
  契约第 1 条“disabled mapping 的 Repository 不能被另一 scope 取得”只经审核探针验证，没有测试。可在下次改动 `test_provisioned_scope_seed.py` 时各加一行参数。
- 偏差复核：只读预检（WAL profile 会写外来库文件头，先只读检查是必要的，重启与并发探针均通过）、提交 2 与 3 合并（owner 决议 S3）、
  `test_sqlite_operation_store.py` 改为新入口（调用方随入口改名，属必要改动）、设计 §12 与执行计划 S2a/S2b 内容项的改写（同属 migration 措辞），均接受。
- 合并：`main` 已被其他对话的文档提交前进，`p5-g3` 以 `--no-ff` 合并提交并入；AGENTS.md「项目前提」中 control DB 演进方式一句在合并后由审核方更新。

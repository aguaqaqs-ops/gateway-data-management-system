# P5 架构收口 G8a（census 口径修订与重跑）独立审核

- 结论：**通过**（G8a 不是阶段，不打 tag）
- 日期：2026-10-11
- 审核对象：main @ `4ff6c44e60ffaa57b12da03749f217b28c0302de`（H；门禁提交 V = 实现 HEAD = H，本任务只要求 focused 与静态检查），区间 `cd8eea32f7..H`。
  区间内 `db0e9a6c3a`、`c52f25fdb0`、`ffa2f35810`、`8b4536f884` 是另一个对话提交的 `docs/frontend-vnext/**`，不属于 G8a，按路径排除；
  实现方提交是 `15fdda8607`（census 工具与测试）、`7d41852229`（census JSON schema v3）、`4ff6c44e60`（handoff）。
- 依据：治理修订计划 G8「进展」与 G8a；执行计划 §8；Canonical Storage 契约（gid 域与 pseudo 分配）；`storage_projection/_ordered.py`、`project.py`；handoff `plans/p5-arch-closure-g8a-handoff.md`。
- 审核在只读 detached worktree `/home/dev/gdds-review-g8a`（H）中进行。审核者没有读取真实数据（`GATEWAY_REAL_DUMP_ROOT`、`summary*.json`），census 的运行结果没有被独立复现；
  核对的是提交内 census JSON 的内部一致性、它与 `3c42f64140` 版本的差异、census 工具与生产代码的口径一致性，以及测试与静态检查。

## 1. 结论摘要

G8a 的目标达成：census 现在对 `GID_NO_V1` 有序表只把真实 gid 纳入重复扫描，空白 gid（NULL、空串、整数 0）按 `_parse_gid_source` 的同一函数识别并单列，
每张有序表的 reader 只消费一次，同一份行集合同时用于重复统计、F5 统计与 `project_ordered_rows`。8 份数据重跑后：真实 gid 重复额外行 50,565 → 0，空白 gid 行 50,818，
558 张有序表的投影全部 COMPLETE、0 FAILED。没有阻塞项，有一项非阻塞问题（G8a-F1：诊断模式下扫描未执行时 `ordered_projection.status` 会误报 COMPLETE，目前没有任何已记录结果受影响）。

另有一条环境前置要在 G3 开始前处理（见 §5）：新建的 worktree 缺少被 git 忽略的 `legacy/` 参考目录时，`test_table_rules_resolver.py` 的 58 个用例会失败；
G3 的独立 worktree 必须先建这个符号链接。

## 2. Findings

### G8a-F1：`ordered_projection.status` 在扫描未执行时仍为 COMPLETE

- 类型：已证实缺陷（工具的潜在误报）；是否阻塞：否
- 位置：`vnext/backend/benchmarks/real_dump_census.py` `_ordered_projection_report`（`status` 只由 `diagnostic_mode` 与 `failed_count` 决定）。
- 依据：`_duplicate_and_effective_key_stats` 在 `table_set is None` 或物化不完整时返回 `duplicate_scan_status` 为 `materialization_unavailable` / `materialization_incomplete`、
  `ordered_projection_by_table` 为空；`census_one` 以 `diagnostic_mode=True` 调用 `_ordered_projection_report({}, ...)`，我实际调用得到
  `{'status': 'COMPLETE', 'ordered_table_count': 0, ...}`。
- 触发场景与影响：诊断模式下某份数据物化失败（例如以后 dump 又出现不被接受的 SET 语句）时，JSON 会写出“有序投影 COMPLETE、0 张表”，与同一记录里的物化状态矛盾。
  本轮 8 份数据的物化与扫描均为 complete、558 张表都有逐表记录，所以不影响任何已记录的数字或 G8 的事实陈述。
- 另有两个分支没有测试覆盖：有序表 `reader is None`（记为 FAILED / `READER_UNAVAILABLE`）与有序表缺 `gid` 或 `no` 列（记为 FAILED / `ROW_INTEGRITY`）。这两个分支的逻辑与 `project.py` 一致，仅缺测试。
- 最小修正方向：`_ordered_projection_report` 接收 `duplicate_scan_status`，非 `complete`（含 `partial`）时把 `status` 设为该状态而不是 COMPLETE；补两条参数化用例。
- 关闭标准：参数表中有“物化不可用/不完整”用例，断言 `ordered_projection.status` 与扫描状态一致。
- 处理时机：不要求在 G8 决议前修；census 工具下一次被使用（S2a 的 census 重跑对照）前修掉即可。

## 3. 验收核对

| 验收项（G8a 与审核提示词） | 结果 | 证据 |
| --- | --- | --- |
| 1 重复扫描与 `_parse_gid_source` 一致 | 通过 | 工具直接 import `_ordered._parse_gid_source`、`OrderedProjectionError`、`project_ordered_rows`（benchmarks 不在 import_rules 扫描范围，import_rules 仍 3/0/14）。有序表键为 `(str(gid_value),)`，即解析后的整数，不是 `repr(cell)`；返回 `None` 的行计 `blank_gid_rows`，抛 `OrderedProjectionError` 的行计 `unparseable_gid_rows`，都不进入分组。空白为 NULL、空串、整数 0 的断言在参数表 `null-empty-and-zero-gids-are-pseudo` 中。 |
| 2 参数表覆盖与 reader 单次消费 | 通过 | `ORDERED_GID_CENSUS_SHAPES` 六条：三种空白形态、空白与真实重复混合、`no` 非连续、`no` 重复、gid 落在 pseudo 保留段、gid 不可解析；`KEY_SCAN_COVERAGE_SHAPES` 增加非有序表空白键仍按原指纹分组的用例，并断言 `ordered_projection_by_table == {}`。有序表 `iter_rows` 第二次调用即 `AssertionError`，`reader_calls == 1`。 |
| 3 `ordered_projection` 索引、固定消息、汇总一致 | 通过 | gid/no 索引取法与 `project.py::_ordered_indexes` 逐字相同（`canonicalize_rule_identifier` 后取 `ORDERED_IDENTITY_COLUMN`、`ORDERED_POSITION_COLUMN`）。逐表记录只含状态、固定诊断码与消息、计数。我用脚本复核 8 份数据：每份的 `ordered_table_count`、`complete_count`、`failed_count`、`real_rows_total`、`pseudo_rows_total` 都等于逐表之和；COMPLETE 表的 `pseudo_gid_count == blank_gid_rows`；`real + pseudo == row_count`。 |
| 4 census JSON schema v3 与旧字段 | 通过 | `schema_version` 2 → 3；与 `3c42f64140` 版本逐字段比较，数据集记录里只有 `duplicate_key_scan` 的 `by_table`/`table_details`/`extra_rows`/`exact_duplicate_extra_rows`/`conflicting_extra_rows`、`effective_key_scan.duplicate_tables_with_explicit_effective_key`（由重复明细派生，现为空）、新增的 `ordered_projection` 变化；其余字段（含 `production_materialization_path`、DC12/DC15 统计、覆盖统计）完全相同。顶层 `datasets_with_duplicate_keys` 变为空，重复额外行总数 50,565 → 0。`materialization_diagnostics` 与 `materialization_diagnostic_details` 在 8 份数据上同空同非空（G2R-F1 的同类错误没有再出现）。`contains_row_data=false`。 |
| 5 改动路径范围 | 通过 | `git diff --name-only 15fdda8607^..H -- . ':!docs/frontend-vnext'` 只有 census 工具、其测试、census JSON、handoff 四个文件。没有 `backend/src`、规则注册表、表角色、ordered policy、golden/digest/fixtures、治理计划或 G3 规格的变化。 |
| 6 运行记录与事实陈述 | 通过 | 日志 `g8a-census-runs.log`：工具提交 `15fdda86` 后才运行，两条路径 exit 0，起止 HEAD 与各检查点工作区状态已记录；运行期间 HEAD 前进到 `8b4536f884` 只因前端文档提交，我复核了 `15fdda8607..8b4536f884` 在 `vnext/` 下没有任何变化。handoff §6 只陈述事实（真实重复 0、投影失败 0、受影响表），没有作 G8 决议，也没有改规则键、表角色或去重行为。 |

独立复核的新旧关系：8 份数据共 160 个“含空白 gid 的有序表”条目。对每一条，`blank_gid_rows − 旧口径额外行` 都在 1 到 3 之间（共 253 个分组），
即每种空白写法（NULL、空串、0）在旧口径下各自成为一个 `repr` 分组、只有分组内多出的行被计为额外行；没有一条有序表在 `blank_gid_rows = 0` 时存在旧口径额外行；
旧口径的额外行全部落在有序表上。这说明旧口径的 50,565 条“重复”可以完整地由空白 gid 解释，没有留下无法解释的残余。

## 4. 实际执行的检查

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 范围 | `git diff --name-only cd8eea32f7..4ff6c44e60 -- . ':!docs/frontend-vnext'` | 4 个文件，均在 G8a 范围内 |
| 无生产代码变化 | `git diff --stat 15fdda8607..4ff6c44e60 -- vnext` | 空（`vnext/` 在工具提交之后没有变化） |
| 五包 ruff 与 mypy | 各包 `uv-consume.sh -C . run ruff check .` 与 `run mypy` | backend、repository_service、repository_client、repository_contracts、shared_kernel 均为 0 / 0 |
| focused 测试 | backend：`test_real_dump_census.py`、`test_table_rules_contracts.py`、`test_table_rules_resolver.py`、`test_storage_projection_contracts.py`、`_core.py`、`_integrity.py`、`test_comparison_ordered.py` | 247 passed（resolver 需要 `legacy/` 链接，见 §5）；除 resolver 外的 6 个文件共 113 passed，不依赖该链接 |
| import_rules | `python -m tests.support.import_rules`；`pytest -k import_rules` | 违例基线 3、运行时环 0、不可达 14；测试 1 passed |
| census JSON 自检（独立重做） | 脚本：比较新旧 JSON 字段、重算各级汇总、逐表关系、字符串叶子扫描 | 全部成立；仅有的“路径样”字符串是 provenance 说明文字里的 `/`，没有主机路径或行值 |
| gid 空白口径 | 读 `_ordered._parse_gid_source`；census 参数表中 0、NULL、空串均记空白 | 与生产一致 |
| 状态误报复现 | 调用 `_ordered_projection_report({}, diagnostic_mode=True)` | `status: COMPLETE`、0 张表（G8a-F1） |

没有改动审核 worktree 里被跟踪的文件；`git status` 为空（`legacy` 链接被 `.git/info/exclude` 忽略）。

## 5. 验证限制与剩余前置

- **没有读取真实数据，census 数字没有被独立复现。** 我核对的是 JSON 的内部一致性与新旧关系（上面的 160 条逐表关系是不依赖原始数据的有力旁证），不是对原始 dump 的重算。
- **“投影 COMPLETE”的范围。** census 调用的是 `project_ordered_rows`（gid 解析与唯一性、`no` 正且唯一连续、pseudo 分配），没有走完整 `project()`；
  `_require_row_count`、单元格编码与列 codec 不在这次统计里。对 G8 要回答的问题（真实 gid 是否重复、有序表的身份与位置检查能否通过）这个范围足够，但不能表述为“8 份数据都能完整投影”。
- **环境前置（G3 开始前必须处理）。** `legacy/` 是 git 忽略的本地参考目录（`.gitignore` 的 `/legacy/`，且 `.git/info/exclude` 的 `legacy` 使符号链接也被忽略），不在任何提交里。
  `tests/support/table_rules_legacy_oracle.py` 读取 `<worktree>/legacy/backend_vnext/contracts/versions.py`，在没有它的新 worktree 里 `test_table_rules_resolver.py` 有 58 个用例失败（FileNotFoundError），
  `run-tests.sh` 的 backend 批次会因此失败。`/home/dev/gdds-p5-closure-s1` 一直靠符号链接 `legacy -> /home/dev/gateway-data-management-system/legacy` 通过。
  G3 的独立 worktree 与以后的审核 worktree 都要先建：`ln -s /home/dev/gateway-data-management-system/legacy <worktree>/legacy`（建后 `git status` 仍为空）。
  这一前置没有写在 AGENTS.md 或 testing-conventions 里，审核方会补。
- handoff 记录 focused 测试 228 passed，我的选择范围略大（含 table_rules resolver），为 247 passed；两者没有矛盾。

## 6. 对 G8 的输入（事实，不是决议）

- 真实 gid 重复额外行：8 份数据全部为 0。因此“规则键需要加 `no` 才不会 KEY_DUPLICATE”这个动机不成立；现有设计（`gid` 为身份、`no` 为位置列、空白 gid 分配 pseudo）在这 8 份数据上没有产生重复或身份检查失败。
- 空白 gid 行 50,818，占有序表行（419,752）的 12.1%，分布在 160 个数据集-表条目里（含空白的表数 1、1、16、14、24、24、40、40）。这些行按契约在每张表内从 `4_000_000_000` 起按 `no` 顺序连续分配 pseudo gid，只作物理身份。
- **未验证（不是 finding）：** 空白 gid 行占比不小，它们在 v1 → v2 比较时的配对行为取决于 pseudo gid 的分配顺序与有序比较的实现。census 没有做 v1 与 v2 的比较，我也没有在这次审核里读比较路径。
  如果 owner 的顾虑是“同一张表里含大量空白 gid 的行如何在两个版本间配对”，这需要另做一次基于真实配对（同层 v1/v2）的比较检查，不是改规则键能回答的问题。是否需要由 owner 在 G8 决议时决定。
- 工具后续用法：G8a-F1 在 census 下一次使用前修掉；census JSON 现在可以作为 G8 决议的依据。

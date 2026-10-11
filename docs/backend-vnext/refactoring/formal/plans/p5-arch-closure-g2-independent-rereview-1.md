# P5 架构收口 G2（含 G6、G7）独立审核（第 1 次复审）

- 结论：**通过**
- 日期：2026-10-11
- 审核对象：main @ `eece236590c9dfc71fafbbecbe3bd94492251154`（H′；门禁提交 V′ = 实现 HEAD = `0889fa953da9116d2fc0722bf1031ecaa7352cf6`），
  上次审核对象 `c9a09ddb35e4c8c5aaef0a4cba8175ac3488536a`，报告 `plans/p5-arch-closure-g2-independent-review.md`；区间 `p5-s1-exit..H′`，本次复审的差异区间为 `c9a09ddb35..eece236590`。
  区间内 `2a2abffd8f`、`ab4db5791d` 是审核方的报告与治理文档提交，不属于实现范围；实现方提交是 `6a6eb546ec`（R1）、`29f7dfd3c3`（R3a）、`0889fa953d`（R2 = V′）、`eece236590`（H′，仅 handoff）。
  H′ 由首次提交 `6d23cb9284` amend 而来（两者只差 handoff 的 3 行），实现方的 carried 记录覆盖了两者，我复核的是最终的 `eece236590`。
- 依据：上次审核报告 G2-F1 的四条关闭标准与 G2-F2 至 G2-F6；治理修订计划 G2、G6、G6b、G7；执行计划 §8；AGENTS.md「权威入口的运行前提」「镜像身份等价」；handoff §8（修订轮）。
- 审核在只读 detached worktree `/home/dev/gdds-review-g2-r2`（H′）中进行。carried 复核在主工作区（V′ 的门禁 worktree）里只做了一次 backend/worker 重建，期间没有运行测试，
  HEAD 与 `git status`（clean）前后不变。`p5-s1-exit` 的源码用 `git archive` 导出到审核者的临时目录，只用于新旧对照。
- 审核者没有读取真实数据（`GATEWAY_REAL_DUMP_ROOT`、`summary*.json`），census 的运行结果没有被独立复现，只核对了提交内 census JSON 的内部一致性与新旧差异。

## 1. 结论摘要

上次的阻塞项 G2-F1 已关闭：`_allowed_set_name` 只在 `p5-s1-exit` 的逻辑之前增加了一个精确名 `@saved_cs_client`，我用 36 条语句在 `p5-s1-exit` 与 H′ 上逐条对照，
两者只在 `@saved_cs_client` 的三种大小写写法上不同（拒绝 → 接受），其余结果完全一致。标准 mysqldump 头尾的 18 条 `SET` 语句全部接受。
`rd-t3-c-v1` 在重跑的 census 中 SQL、物化、composite 全部 COMPLETE（199 张 DDL 表、200 张物化表、268,661 行、最大 XML 深度 66）。
V′ 上的完整权威 runner exit 0（242 / 152 / 154 / 2734 / 1681 + 1 skipped / 205），V′ → H′ 只改 handoff，我在 V′ 的同一 worktree 复现了镜像身份等价（`carried`）：RS 身份与 label 一致，backend/worker 的 image ID 与 V′ 的 provenance 完全相同。
`import_rules` 为 3 / 0 / 14，golden、digest、checkpoint、HTTP DTO 没有变化。

没有阻塞项。有一项非阻塞问题（G2R-F1）：census JSON 中 `rd-t3-c-v1` 的 `materialization_diagnostics` 是上一版遗留的过期值，与同一记录里的状态和细节自相矛盾。
它不进入任何统计或门禁，但这份 JSON 是 G8 的决议依据，应在 G8 决议前更正（见 G2R-F1）。

“原 finding 已关闭”与“G2 阶段退出门禁已满足”是两个独立结论，本报告的结论是两者都成立。可以在本报告提交上打 `p5-g2-exit`，S2a 的区间起点为 `p5-g2-exit`，除非 G3 先行（以后者为准）。

## 2. Findings

### G2R-F1：census JSON 里 `rd-t3-c-v1` 的 `materialization_diagnostics` 是过期值

- 类型：已证实缺陷（记录不一致）；是否阻塞：否
- 位置：`plans/p5-arch-closure-s1-census.json` 第 1811–1813 行（`datasets[]` 中 `rd-t3-c-v1` 的 `materialization_diagnostics`）。
- 依据：
  - 该记录的 `materialization_status`、`production_materialization_status` 均为 `COMPLETE`，`materialization_diagnostic_details` 为 `[]`，`duplicate_key_scan.coverage.reader_unavailable_table_count` 为 0，
    但 `materialization_diagnostics` 仍是 `["TABLE_READER_UNAVAILABLE"]`。
  - `real_dump_census.py` 的 `census_one` 用同一个列表 `business.diagnostics` 生成这两个字段（`materialization_diagnostics=[item.code.value …]` 与 `materialization_diagnostic_details=[{"code": item.code.value, …}]`，
    `code` 恒不为空），工具不可能输出“列表非空、细节为空”。
  - 对 `c9a09ddb35` 的版本逐字段比较：`rd-t3-c-v1` 的 `materialization_diagnostic_details` 从含 SET 失败消息的一项变为 `[]`，而 `materialization_diagnostics` 保持不变，是这条记录里唯一该变而没有变的字段；
    其余 7 份数据与 `rd-t3-c-v2` 的该字段都是 `[]`。
- 触发场景与影响：读 census 的人（G8 决议、S2a 重跑对照）会得到“`rd-t3-c-v1` 有 reader 不可用的表”的误导；不影响任何计数、状态、重复键统计或门禁。
- 最小修正方向：把该字段改为 `[]`，由实施方对照 `summary-diagnostic.json` 确认（审核者没有读取权限）后，作为纯文档提交更正；在 G8 决议前完成。
  审核方曾准备在本报告提交中直接更正这一字段，但该编辑被执行环境拒绝，审核方没有绕过，因此留给实施方或 owner 授权后处理。
- 关闭标准：该字段与同记录的状态、细节一致；更正只改这一处，其余字段与本次复审核对的数值不变。

## 3. 上次 finding 的关闭情况

| 编号 | 结果 | 证据 |
| --- | --- | --- |
| G2-F1（阻塞） | 关闭 | 标准 1：`MYSQLDUMP_SET_SHAPES` 含 10 条头部 `SET`、8 条恢复 `SET` 与 saved-client 四种形态，共 22 项，参数表通过。标准 2：见 §4 的新旧对照，接受集合只多出 `@saved_cs_client`，拒绝集合不变；`@character_set_client` 的错误拒绝用例已删除，保留 `@@saved_cs_client`、`@other_client`。标准 3：`rd-t3-c-v1` 的 SQL / 物化 / composite COMPLETE，键统计已更新，另外 7 份数据除新增的两个字段外与上一版完全一致（G2R-F1 是同一记录里的一个标签字段，不影响这条）。标准 4：V′ 上的权威 runner exit 0，见 §4 |
| G2-F2（文档，审核方已修） | 关闭 | 实现方按恢复后的 carried 第 3 条在 V′ 的同一 worktree 判定，结论 true；我独立复现（§4） |
| G2-F3（镜像含空目录 `gateway_backend/cache`） | 仍开放，已登记 | 实现方明确声明不关闭，并关联 G6b；本轮没有改构建上下文 |
| G2-F4（G7 证据与测试） | 关闭 | 新增 `test_client_dependency_base_rebuilds_when_lock_and_final_image_are_stale`，断言 `docker build` 的完整命令；候选 `815ef56a…` 的层数没有补造，改以 V、H、V′ 的 final 20 层、base 12 层为准，handoff §8.4 已写明 |
| G2-F5（census 新增两项统计） | 关闭 | 每个重复表有排序的 `differing_columns` 与 `max_group_size`；只含列名与计数，见 §4；参数表覆盖相同行、单列冲突、多列冲突（列名排序）、混合重复组，并强制每个 reader 只消费一次 |
| G2-F6（临时资源） | worktree 已关闭；Docker 残留仍开放，已登记 | `git worktree list` 只剩主工作区与 `/home/dev/gdds-p5-closure-s1`；Docker 镜像与卷并入 G10，没有在门禁期间清理，client final / base 镜像完好 |

## 4. 实际执行的检查

| 检查 | 结果 |
| --- | --- |
| 区间文件范围 | `c9a09ddb35..eece236590` 中实现范围的文件为 8 个：`_sql_statements.py`、`real_dump_census.py`、`test_real_dump_census.py`、`test_table_access_sql_parser.py`、`test_table_access_sql_rejects.py`、`test_compose_lifecycle_harness.py`、census JSON、handoff；没有 fixtures、golden、Dockerfile、Compose、`.dockerignore`、`architecture_baseline.py` |
| 生产源码相对 `p5-s1-exit` | 3 个文件、5 行增、3 行删：`_sql_statements.py` +2（`@saved_cs_client` 精确名）、`_ast.py`（`Digital` 的 `value`，G2.2）、`contracts.py`（`max_xml_depth=128`，G2.3），与上次已通过的 G2.2、G2.3 一致 |
| SET 白名单新旧对照 | 36 条语句，旧 = `git archive p5-s1-exit` 导出的源码，新 = H′（探针打印了被导入的包路径以确认来源）。10 条头部、8 条恢复语句、`@@unique_checks`、`@@character_set_client`、`@character_set_client`、`SET NAMES`、`SET sql_mode=''`、`@@old_x`、`@collation_foo` 两边都是 COMPLETE；`@other_client`、`@@saved_cs_client`、`@@@saved_cs_client`、`@ saved_cs_client`、`SET @OLD = 1`、`SET @a=1`、`SET foo = 1`、`SET autocommit=0`、`SET GLOBAL sql_mode=''` 两边都是 FAILED；只有 `@saved_cs_client`、`@SAVED_CS_CLIENT`、`@Saved_Cs_Client` 三条从 FAILED 变为 COMPLETE。与 handoff §8.2 的 30 条表一致 |
| 审核 worktree 内 focused 测试 | backend：SQL parser / rejects / census / composite AST / table_access contracts 共 101 项通过；`test_architecture.py` 与 `test_table_access_xml_limits.py` 共 85 项通过；repository_service：`test_compose_lifecycle_harness.py` 与 `test_build_context_digest.py` 共 147 项通过 |
| 静态检查 | backend 的 `ruff check .` 通过、`mypy` 464 个文件无问题；repository_service 的 `ruff check .` 通过、`mypy` 198 个文件无问题。shared_kernel、repository_contracts、repository_client 在区间内没有改动，未重跑 |
| `import_rules` | 直接调用 `tests/support/import_rules.py`：违例 3、运行时环 0、不可达 14，与基线条目数一致；基线与规则文件自 `p5-s1-exit` 起无改动 |
| V′ 门禁日志 | `g2r-preflight.log`：HEAD 为 V′、status 为空、无 Dolt、无带 Compose 标签的容器、8000 空闲；`g2r-runner.log`：起止 HEAD 均为 V′、status 为空、`runner_exit_code=0`，耗时 05:31:19Z–05:57:29Z；批次 242 / 152 / 154 / backend 2734（1 warning）/ RS 并行 1681 + 1 skipped / RS 串行 205 + 1682 deselected。相对 V 的增量合理：backend +17 = 参数表 +18、拒绝用例 −1，RS 并行 +1 = 新增的 harness 用例 |
| V′ 三镜像 provenance | `g2r-compose-provenance.json` 与 `g2r-images-inspect.log` 一致：project `ordered-bisect-b-1055182-baseline`；backend `sha256:668e532f…`（15 层）、RS `sha256:e184e610…`（28 层，build-input-revision `29f7dfd3…`、source-tree `sha256:2c92331c…`、revision `0889fa95…`）、worker `sha256:55dd7a9f…`（15 层）。runner 之后 client final `sha256:ca24dce1…`（20 层，revision 为 V′）、base `sha256:dafde407…`（12 层，不变），lock label 一致 |
| V′ → H′ carried（独立复现） | 在主工作区（V′ 的门禁 worktree）、HEAD = H′、status 为空、无 Dolt / Compose 容器、8000 空闲：`V′..H′` 的变更路径只有 handoff；`build_context_digest.py identity` 重算的 build-input-revision `29f7dfd3…`、source-tree `sha256:2c92331c…` 与运行中 RS 镜像的 label 完全一致；用 V′ 的 project 名 `docker compose -f compose.yaml build backend worker` 后 backend 为 `sha256:668e532f…`、worker 为 `sha256:55dd7a9f…`，与 V′ 的 provenance 相同。构建之间没有运行测试。记录在 `/home/dev/gdds-p5-closure-s1-gate-logs/review-g2r2-carried.log`。三个条件都成立，H′ 沿用 V′ 的容器门禁结果 |
| census JSON 内部一致性 | 各数据集的表级细分求和等于数据集总数（9,817 = 9,817 等）；总额外行 50,565 = 0 + 50,565；160 个重复表记录，键来源均为 `EXPLICIT_RULE`；`differing_columns` 全部是排序的标识符、不含键列、合计 430 个名字、160 张表均非空；`max_group_size` 最大 1,625；`contains_row_data=false`；没有主机路径或 `gateway-real-dumps` 字样；`rd-t3-c-v1` 的 199 张 DDL 表 = 13 + 54 + 8 + 4 + 120 个角色计数，200 张物化表 = 165 张已扫描 + 8 张规则跳过 + 27 张键未解析，与其他数据集 “DDL + 1” 的关系一致。另外 7 份数据与 `c9a09ddb35` 版本逐字段比较，只多出 `differing_columns` 与 `max_group_size`；生产路径两段（`parser_production_path`、`production_materialization_path`）除 `rd-t3-c-v1` 外无变化 |
| G2 handoff 修订轮 | 逐项核对 §8.2 至 §8.7 的数字与 §2–§4 的验证结果一致；只改 handoff 一个文件，没有改治理文档 |

停止条件：golden / digest / checkpoint / HTTP DTO 无变化（区间内没有 fixtures 与 expected 的改动，V′ 的 runner 全绿）；`import_rules` 3 / 0 / 14；AST 结构与业务语义未改（`rd-t3-c-v1` 在 SQL 之后没有暴露新差异）；白名单接受集合只增 `@saved_cs_client`。全部满足。

## 5. 验证限制

- 没有读取真实数据，census 的运行结果没有被独立复现；`rd-t3-c-v1` 的数字是对提交内 JSON 做内部一致性与新旧差异核对的结果。
- census 运行时 `real_dump_census.py` 与测试还是未提交的改动（日志 `status_begin` 为 ` M`），提交 `0889fa953d` 在运行结束后 3 分钟；没有办法证明运行时的工具与提交内的版本逐字节相同，提交内的版本通过了全部相关测试，JSON 的内部一致性也成立（G2R-F1 是例外）。
- carried 复现依赖主工作区里仍在的 BuildKit 缓存与本地状态；跨 worktree 的可复现性没有，也没有声称，仍由 G6b 处理。
- 没有重新运行权威 runner：V′ 的门禁有效，V′ → H′ 判定为 carried，规则不要求重跑。

## 6. 对后续工作的输入

- **G8**：更新后的统计为额外行 50,565（完全相同 0、冲突 50,565），160 个 dataset-table 重复记录，键来源均为 `EXPLICIT_RULE`；`rd-t3-c-v1` 与 `rd-t3-c-v2` 的重复统计相同（9,817 条、24 张表）。
  从 JSON 可直接读出的分布（观察，不是结论）：160 条记录中 130 条的 `differing_columns` 只有 `no`（这 130 条占 44,880 条额外行），其余 30 条在 `no` 之外还有多个列（15 条含 `dev_addr`、`entry`、`fcda`、`grp`、`name`，另 15 条再加上限值与系数列）；
  重复表的键列是 `gid`，集中在 IEC104 的 `syx`、`yc`、`syk`、`yt` 四类列表。这些决议属于 owner：规则键是否需要包含 `no`，或这些表的角色、数据是否另行处理。G8 决议前先更正 G2R-F1。
- **S2a**：区间起点为 `p5-g2-exit`（G3 先行时以 G3 的 tag 为准）。
- **G6b**：仍待 owner 选 A / B / C，审核方建议 C；本轮实测的 carried 复现再次说明规则（同一 worktree、两次构建之间不运行测试）足够当前使用。

## 7. 复审记录

- 第 1 次审核（定向修订）：`plans/p5-arch-closure-g2-independent-review.md`，对象 `c9a09ddb35`。
- 第 1 次复审（通过）：本报告，对象 `eece236590`。

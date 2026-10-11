# P5 架构收口 G8a handoff

## 1. 区间、提交与范围

- `R0`：`cd8eea32f77b83c5b2346f60a516a12c590ddfd3`（审核方确认 G3 规格的提交；也是 `15fdda8607` 的父提交）。
- `H`：本 handoff 提交；精确 SHA 由该提交对象确定，最终回复记录。
- 审核区间：`cd8eea32f7..H`。另一个对话提交的 `docs/frontend-vnext/**` 按路径排除；区间中 `db0e9a6c3a`、`c52f25fdb0`、`ffa2f35810`、`8b4536f884` 的前端文档不属于本次审核范围。
- 本轮只实施 G8a，不作阶段退出；不打 tag、不推送。

| 提交 | 用途 | 主要路径 |
| --- | --- | --- |
| `15fdda86078a5aaccf5d28150413c5c8ec2cdcfe` `fix(p5-g8a): count only real gids and run ordered projection in the census` | 只统计真实 gid；同一份有序表 reader 行用于重复统计、F5 与有序投影 | `vnext/backend/benchmarks/real_dump_census.py`、`vnext/backend/tests/test_real_dump_census.py` |
| `7d4185222975ad573553a5d9b8108e1256209b25` `docs(p5-g8a): rerun real dump census with real-gid duplicate scan` | 合并已完成的生产/诊断 census 输出，自检并更新 schema v3 | `docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-s1-census.json` |
| `H` `docs(p5-g8a): record handoff` | 本记录与审核提示词 | 仅本文件 |

范围核对命令：

```text
git diff --name-only 15fdda8607^..HEAD -- . ':!docs/frontend-vnext'
```

在 H 上预期且实际结果只有以下四条；其中 `docs/frontend-vnext/**` 已按用户指定的 pathspec 排除：

```text
docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-s1-census.json
docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-g8a-handoff.md
vnext/backend/benchmarks/real_dump_census.py
vnext/backend/tests/test_real_dump_census.py
```

R0 之前的 G3 规格确认提交属于基线。区间内前端文档提交按 `docs/frontend-vnext/**` 排除；除此之外没有其他路径。

## 2. 修订摘要

GID_NO_V1 有序表重复扫描现在先以生产 `_parse_gid_source` 的解析语义识别 gid，只将真实 gid 纳入重复组；NULL、空串、整数 0 作为空白 gid，不进入重复键分组，无法解析的 gid 也不进入分组并单独计数。非有序表的重复统计路径与计数保持原样。

每张有序表的 reader 只消费一次。该行集合同时用于重复键与 F5 统计、以及调用 `project_ordered_rows`；gid/no 列位置按生产 `_ordered_indexes` 的规则，以 `canonicalize_rule_identifier` 解析。JSON 为 schema_version 3，逐表记录投影状态、固定诊断码/消息、行数、真实/pseudo gid 数、空白 gid 行数及不可解析 gid 行数；数据集级记录投影汇总。`contains_row_data=false`，没有行值或主机路径。

没有修改 `backend/src`、规则注册表、表角色、ordered policy、golden、digest、fixtures、checkpoint 载荷或 HTTP DTO；没有去重，也没有修改 G3 规格或治理计划。

## 3. census 运行与 HEAD 记录

生产路径和诊断路径均在已提交的工具版本 `15fdda86078a5aaccf5d28150413c5c8ec2cdcfe` 上运行，顺序执行且各自 exit code 为 0；八份数据均成功生成结果。运行日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g8a-census-runs.log` 的起止记录原样如下：

```text
overall_head_start=15fdda86078a5aaccf5d28150413c5c8ec2cdcfe
overall_status_start=## main (clean)
overall_head_end=8b4536f88449b42df1e2b1ca70fa5f7c6cd752df
overall_status_end=## main (clean)
```

同一日志逐路径记录了运行时 HEAD：

```text
[production]
head_at_start=15fdda86078a5aaccf5d28150413c5c8ec2cdcfe
head_at_completion_checkpoint=c52f25fdb0459b5ef2afd1bf20cfe8c3baae9bf2
runner_exit_code=0

[diagnostic]
head_at_start=c52f25fdb0459b5ef2afd1bf20cfe8c3baae9bf2
head_at_completion_checkpoint=8b4536f88449b42df1e2b1ca70fa5f7c6cd752df
runner_exit_code=0
```

运行期间 HEAD 因无关的 `docs/frontend-vnext/**` 文档提交前进。工具与测试文件从 census 工具提交到运行结束 HEAD 均未改变；核对命令及结果：

```text
git diff --quiet 15fdda8607..8b4536f88449b42df1e2b1ca70fa5f7c6cd752df -- vnext/backend/benchmarks/real_dump_census.py vnext/backend/tests/test_real_dump_census.py
exit_code=0
```

生产 census 与诊断 census 的原始输出只写到授权的 `census/` 目录，真实输入目录只读。运行期间没有修改 census 工具；合并使用的是上述已提交版本产生的结果。

## 4. census JSON 合并步骤与自检

更新后的 census 为 schema_version 3。合并按以下步骤进行：

1. 以 3c42f64140 后的 checked schema-v2 census 为基底，分别载入本轮生产与诊断 summary；按 `dataset_id` 对齐并要求三者均恰有相同的八份数据。
2. 核对生产与诊断输出的 SQL parser 路径、DC12/DC15 统计和重复键总数相同；从生产输出重建 `production_materialization_path`，并逐项确认与原 census 完全相同。
3. 对每份数据，用诊断输出替换 `duplicate_key_scan` 的计数、逐表详情与覆盖统计；从新重复表明细重新计算 `duplicate_tables_with_explicit_effective_key`；将同一轮的 `ordered_projection` 逐表记录及数据集汇总写入 JSON。
4. 从诊断汇总刷新顶层重复额外行、exact/conflicting 计数及重复数据集列表；设 `schema_version=3`，在 provenance 中说明 GID_NO_V1 只扫描真实 gid、空白 gid 独立记入有序投影统计。
5. 自检 materialization diagnostics 与 details 的空/非空关系；校验逐表、数据集及顶层重复统计，逐表与数据集有序投影行数/状态/失败码汇总；比较所有其他既有字段。
6. 扫描序列化 JSON，确认没有行数据或主机路径，且 `contains_row_data=false`。

完整自检结果保存在 `/home/dev/gdds-p5-closure-s1-gate-logs/g8a-census-self-check.log`。结果：旧字段除重复扫描及其派生计数外保持一致；`production_materialization_path` 与原值完全相同；每份数据的 `materialization_diagnostics` 为空当且仅当 `materialization_diagnostic_details` 为空；逐表分类及各级汇总相等；有序投影状态、失败码、行数和汇总与逐表记录相等；没有行值或主机路径。

Schema-v3 总计：真实 gid 重复额外行 0，完全相同重复额外行 0，冲突重复额外行 0；有序表 558 张，COMPLETE 558 张，FAILED 0 张；真实 gid 行 368,934，pseudo gid 行 50,818，空白 gid 行 50,818，不可解析 gid 行 0。每张有序表均记录 `diagnostic_code` 与固定 `diagnostic_message`；本轮没有投影失败，故失败码集合为空。

与 schema-v2 相比，明确变化仅包括重复扫描及其派生的顶层/数据集统计、`ordered_projection`、schema_version 与新增的口径 provenance。其他既有字段保持一致；重复派生字段归零的原因是新扫描排除了依契约应生成 pseudo gid 的空白值，新增投影字段和 provenance 是 G8a 要求。

## 5. 八份数据新旧对照

表中“旧额外行”是原 repr 分组口径；“新真实 gid 额外行”是 GID_NO_V1 真实 gid 分组口径。“空白 gid 表数”是该数据集中 `blank_gid_rows > 0` 的有序表数。

| 数据集 | 旧额外行 → 新真实 gid 额外行 | blank_gid_rows | 空白 gid 表数 | 有序表数 | 投影 COMPLETE / FAILED | 失败码 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `rd-t1-a-v1` | 3 → 0 | 4 | 1 | 9 | 9 / 0 | 无 |
| `rd-t1-a-v2` | 3 → 0 | 4 | 1 | 9 | 9 / 0 | 无 |
| `rd-t2-b-v1` | 3,032 → 0 | 3,056 | 16 | 72 | 72 / 0 | 无 |
| `rd-t2-b-v2` | 2,653 → 0 | 2,674 | 14 | 72 | 72 / 0 | 无 |
| `rd-t3-c-v1` | 9,817 → 0 | 9,858 | 24 | 54 | 54 / 0 | 无 |
| `rd-t3-c-v2` | 9,817 → 0 | 9,858 | 24 | 54 | 54 / 0 | 无 |
| `rd-t4-d-v1` | 12,616 → 0 | 12,676 | 40 | 144 | 144 / 0 | 无 |
| `rd-t4-d-v2` | 12,624 → 0 | 12,688 | 40 | 144 | 144 / 0 | 无 |
| **合计** | **50,565 → 0** | **50,818** | **160 dataset-table 条目** | **558** | **558 / 0** | **无** |

生产 SQL parse、materialization 与 composite 均为 COMPLETE；新统计没有改变这些字段。逐表 blank gid 数在 census JSON 的 `datasets[].ordered_projection.tables` 中记录。

## 6. G8 分支所需信息（事实）

- 真实 gid 重复额外行总数为 0；`duplicate_key_scan.table_details` 没有真实重复表。
- 有序投影失败总数为 0；没有失败表或失败码。
- 有序表中含空白 gid 的 dataset-table 条目共 160 个，逐份数据计数为 1、1、16、14、24、24、40、40；表名和逐表 blank gid 行数见 census JSON 的 `ordered_projection.tables`。

本节只陈述 census 事实，不作 G8 决议，不改规则键、表角色或去重行为。

## 7. 验证与日志

G8a 每个提交后均运行五包 `ruff check .`、五包 `mypy`、`import_rules` 和 backend focused 测试。import_rules 三项计数为 `3/0/14`。focused 测试覆盖 census、table_rules、storage_projection 有序表行为和 import_rules 基线；每次均为 228 passed。

- 提交 1 验证：`/home/dev/gdds-p5-closure-s1-gate-logs/g8a-commit1-verification.log`。
- 提交 2 验证：`/home/dev/gdds-p5-closure-s1-gate-logs/g8a-commit2-verification.log`。
- 提交 3 提交后的验证：`/home/dev/gdds-p5-closure-s1-gate-logs/g8a-commit3-verification.log`。
- census 运行记录：`/home/dev/gdds-p5-closure-s1-gate-logs/g8a-census-runs.log`。
- census JSON 合并与自检记录：`/home/dev/gdds-p5-closure-s1-gate-logs/g8a-census-self-check.log`。

没有改动镜像、Compose、backend/src 或部署边界；本轮按执行范围未重建镜像、未运行完整 `run-tests.sh`。

## 8. 审核提示词

```text
任务：独立审核 P5 架构收口 post-S1 G8a。你没有参与 G8a 的实现；按
 docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：main @ H（focused/static 门禁提交 V = H，实现 HEAD = H），区间 cd8eea32f7..H。只审该区间；对 docs/frontend-vnext/** 按路径排除。
在只读 detached worktree 中工作：git worktree add --detach /home/dev/gdds-review-g8a <H>；不在主工作区运行测试或写入。
权威依据：plans/p5-arch-closure-post-s1-governance-plan.md（G8“进展”与 G8a）、plans/p5-arch-closure-execution-plan.md §8.7、Canonical Storage 契约、storage_projection/_ordered.py、storage_projection/project.py；实现方记录 plans/p5-arch-closure-g8a-handoff.md。

必须核查：
  1. GID_NO_V1 重复扫描与 _parse_gid_source 一致：NULL、空串、整数 0 为空白；真实 gid 纳入重复组；不可解析 gid 单独统计且不进入重复组。
  2. 参数表覆盖空白值不计重复、真实 gid 重复与 differing_columns/max_group_size、混合表、投影成功和三类投影失败、不可解析 gid、非有序表不变；确认 reader 单次消费，重复扫描/F5/投影复用同一次 reader 行集合。
  3. ordered_projection 的 gid/no 索引解析、逐表固定诊断信息和计数、数据集/顶层汇总与 census JSON 的逐表明细一致；材料化 diagnostics/details 空值关系及新旧数据集对照与 handoff / 外部自检日志相符。
  4. census JSON schema_version=3，旧有字段除重复扫描口径及其派生统计外无未解释变化；JSON 不含行值或主机路径，contains_row_data=false。
  5. 核对范围命令 `git diff --name-only 15fdda8607^..H -- . ':!docs/frontend-vnext'` 的输出仅为 census 工具、测试、census JSON 与本 handoff；确认没有 backend/src、规则、表角色、ordered policy、golden/digest/fixtures、治理计划或 G3 规格变化。
  6. 核对运行期间 HEAD 前进记录、工具与测试文件未变命令、每次验证日志；真实 gid 重复为 0、有序投影失败为 0，不据此代替 owner 作 G8 决议。

验证：在审核 worktree 中自行运行 backend focused 测试（census、table_rules、storage_projection 有序表测试）、五包 ruff/mypy 与 import_rules（预期 3/0/14）。无需重跑 census runner 或完整 run-tests.sh。
交付：按执行计划 §8.8 写 plans/p5-arch-closure-g8a-independent-review.md，作为单独纯文档提交并快进合入 main；除审核报告外不修改文件；不推送、不打 tag。
审核允许结论：通过 / 定向修订 / 整体返工。
```

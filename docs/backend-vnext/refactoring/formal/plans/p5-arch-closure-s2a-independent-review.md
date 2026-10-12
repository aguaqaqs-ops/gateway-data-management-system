# P5 架构收口 S2a（规范快照与比较规则的能力层）独立审核

- 结论：**通过**
- 日期：2026-10-12
- 审核对象：`p5-s2a` @ `39efa08db1a2803a436e7b969929bc0114998826`（H；门禁提交 V = 实现 HEAD = `741d227991f8b76235a36649830f34b3920df6f0`），区间 `p5-g8b-exit..39efa08db1`。
  区间中的 `e04a6eb041`（合并 G8b）、`57fb9b4dc8`、`1c7398572f` 是审核方文档提交，先于分支 base `1c7398572f`；实施方提交为 `396cfa2d28..39efa08db1` 共 11 个。
- 依据：执行计划 §2 S2a、§3 S2a、§6、§7、§8；设计 §4.1–§4.5、§4.7、§6、§12、§14；Canonical Storage §7；治理修订计划 §3 第 6 项（携带项）；AGENTS.md「项目前提」「镜像身份等价」；
  handoff `plans/p5-arch-closure-s2a-handoff.md`。
- 审核在只读 detached worktree `/home/dev/gdds-review-s2a`（H）中进行。唯一的写入是一个临时探针测试文件（真实 Dolt 往返，见 §4），运行后即删除，`git status` 前后均为 clean。
  carried 复核在实施 worktree `/home/dev/gdds-p5-s2a` 中只做一次 backend/worker 重建，期间没有运行测试，HEAD 与 `git status`（clean）前后不变。

## 1. 结论摘要

S2a 的能力层目标达成，具体如下：

- table_rules 有 `compare_excluded_columns`，`composite_signal_point` 的两列已按设计 §4.4 移入；9 条 ordered 规则不再忽略 `no`。
- 快照有 business schema digest 与 canonical state digest；规范投影入口 `project_canonical_table_set` 已落地；manifest 写 3.1.0、读 3.0.0/3.1.0。
- 比较改由运行期规则集驱动；BROWSE_ONLY/SNAPSHOT_ONLY 呈现表级内容事实。
- Preview 与 History 都在受理时冻结运行期规则集 digest，三个步骤执行前都检查，以 `PREVIEW_RULESET_VERSION_MISMATCH` / `HISTORY_RULESET_VERSION_MISMATCH` 稳定失败。
- 四个携带项均已关闭。

真实 Dolt 同一性 owner 在 V 的权威 runner 中通过。我另用探针在真实 Dolt 上往返了这些值：非二进制精确的 FLOAT、次正规数、`INT UNSIGNED` 上限、BIGINT 两端，都无损。
唯一不能往返的是 `-0.0`（S2a-F1）。

V 上权威 runner exit 0；V → H 只改 handoff；carried 在同一 worktree 复现成立。

没有阻塞项。S2a-F1、S2a-F2 并入 S2b，须在 Preview 切到规范域（R1）之前完成。可以在本报告提交上打 `p5-s2a-exit`。

## 2. Findings

### S2a-F1：FLOAT/DOUBLE 的 `-0.0` 不能经 Dolt 往返，规范编码与存储结果不一致

- 类型：已证实缺陷（条件触发）；是否阻塞：否（S2a 中 Preview 上传侧仍是原始快照，S2b 起才可见）
- 位置：
  - 规范编码保留 `-0.0` 的位模式：`Float32Scalar(bits_hex="80000000")`，经 `project_canonical_table_set` 原样进入规范 reader 与 canonical state digest。
  - 写入端 `capabilities/mutation_planning/_repository_replay_renderer.py` `_ascii_float_text` 把 `-0.0` 改写为 `0`。
- 依据：
  - 审核探针：以 `test_canonical_snapshot_identity.py` 的同一流程，经真实 Repository Service 与 Dolt 导入 `FLOAT` 列值 `-0.0`。读回为 `Float32Scalar(bits_hex="00000000")`，与规范侧 `80000000` 不等。
  - 同一探针中，`0.1`、`1e-7`、`-1.23`、`16777218`、`-123.456`、`1/3`、最小次正规数、最小正规数都无损。
  - Dolt 与渲染器两侧都会把负零归一化。
- 触发场景与影响：上传的 dump 中某个 FLOAT/DOUBLE 单元为 `-0`。S2b 切到规范域后：
  - 上传侧的规范状态含 `-0.0`，Submit 写入后读回的基线是 `+0.0`，两侧 canonical state digest 不同；
  - 同一份 dump 重新上传不会得到 `NO_CANONICAL_CHANGE`（执行计划 §2 S2b 真实数据验收第 2 条），Preview 会对该行报修改。
  - 真实数据是否含负零未知，审核方不读真实 dump。
- 最小修正方向：
  - 在规范化环节把浮点负零归一为正零，与 Dolt 和渲染器一致，float32 与 float64 都要处理。位置取 snapshot_materialization 的规范类型规范化或 storage_projection 的 codec，二者择一，由 S2b 实施方在 handoff 写明。
  - 同时在规范内容摘要上验证：`-0.0` 与 `0.0` 的规范状态相同。
- 关闭标准：
  - `test_canonical_snapshot_identity.py` 的参数行含 `-0.0` 并通过真实 Dolt 往返；
  - `test_canonical_state_identity.py` 断言两种零的 canonical state digest 相同。
- 处理时机：S2b 第一项、R1 切换之前。若所需路径不在 S2b 预算内，按预算外路径记录。

### S2a-F2：真实 Dolt 同一性 owner 的类型覆盖低于设计 §12

- 类型：非阻塞建议（证明强度不足；审核探针已补证当前实现正确）；是否阻塞：否
- 位置：`vnext/backend/tests/test_canonical_snapshot_identity.py:71-108`
- 依据：
  - 设计 §12 要求该 owner 覆盖 `INT/BIGINT/INT UNSIGNED`。现有用例没有 BIGINT 列；`INT UNSIGNED` 只经 ordered `gid`（规范化为 `INT UNSIGNED`）覆盖伪 gid 一个值，而普查中 `INT UNSIGNED` 有 6018 列。
  - FLOAT 只用了 `1.5`、`2.5` 两个二进制精确值，证明不了“十进制文本 → float32”的往返。DC15 的停止条件（设计 §14 第 2 项）正是以这一往返为判据。
- 触发场景与影响：当前实现经审核探针验证无误（见 §4）。但 owner 是 S2b 的门槛，以后改动编码或渲染（例如 `.15g` 格式）时，这个用例发现不了回归。
- 最小修正方向：
  - 在同一用例的列与行中加入 `INT UNSIGNED`（含 `4294967295`）、`BIGINT`（含两端）；
  - FLOAT 加入 `0.1`、`-1.23`、`1e-7` 与一个次正规数；
  - 以及 S2a-F1 的 `-0.0`。
  - 保持一个用例、一次 Repository Service 启动，不新增 fixture。
- 关闭标准：owner 用例包含上述值并在 S2b 的门禁 runner 中通过。处理时机：与 S2a-F1 同一提交。

### S2a-F3：handoff 没有说明 V1 有序 Compose 失败的根因：Preview 首次对有序表使用有序比较

- 类型：非阻塞建议（记录不完整）；是否阻塞：否
- 位置：handoff §4、§8；`application/pair_pipeline.py`；`application/submission/contracts.py:67-68`（`741d227991`）
- 依据：
  - base `1c7398572f` 的 `run_preview_pair_pipeline` 不传 `table_policies`，Preview 对所有表都按标准比较。
  - S2a 起 Preview 传入运行期规则集，有序表第一次在 Preview 中走有序比较，于是产生 `comparison-ordered-*`、`comparison-blank-*` 工件，并由 Preview 持有。
  - 这些工件进入 Submit 受理的 `snapshot_table_artifact_refs` 候选，被当作快照 manifest 打开。
  - handoff 只描述了现象与修复，没有写出这一行为变化。
- 触发场景与影响：
  - 修复本身正确且最小，扩展的是设计 §4.8 要求 S2b 删除的按前缀过滤启发式；
  - 但非空基线上 Preview 对有序表的展示从标准记录变为有序记录。执行计划 §2 S2a 允许这类变化，前提是在 handoff 说明原因。
- 最小修正方向：本报告记录即可。S2b 实施 §4.8（Submit 受理按规范闭包精确转移）时，删除 `_SUBMIT_NON_TABLE_ARTIFACT_PREFIXES` 与 `is_submit_snapshot_table_binding_candidate`，包括本阶段新增的两个前缀。
- 关闭标准：S2b 审核时启发式已删除。

### S2a-F4：handoff 的预算偏差少列三处路径

- 类型：非阻塞建议；是否阻塞：否
- 位置：handoff §3
- 依据：以下三个路径不在执行计划 §3 S2a 的必改、条件路径中，handoff 也没有列出：
  - `capabilities/comparison/row_encoding.py`：S1 从 standard 拆出的公共编码模块，承接 compare-excluded 与提前退出条件；
  - `tests/test_preview_job_materialize.py`；
  - `tests/test_storage_projection_integrity.py`。

  三处改动都随所属内容项而来，范围合理。
- 最小修正方向：本报告记录即可。S2b 起，S1 拆分出的子模块（如 `row_encoding.py`）视为其能力包的必改路径。
- 关闭标准：无需复审。

### 观察（不计 finding）

- 运行期规则集目前就是迁移后的静态规则集。它由组合根、`pair_pipeline`（`rule_set` 缺省时兜底）、Preview worker、History worker 各自用 `comparison_rule_set(migrated_table_ruleset_snapshot())` 计算，测试用 `patch` 模拟“激活”。
  在线 ruleset 迁移属于设计的“非目标”。以后引入规则激活时，应改为由组合根注入同一个运行期规则集来源，并删除 `pair_pipeline` 的兜底。
- `normalize_sql_type_spelling` 把单参数 `FLOAT(p)` 一律规范为 `FLOAT`；MySQL 中 `p` 为 25–53 时是 `DOUBLE`。mysqldump 输出的是 `float`、`float(M,D)` 或 `double`，不会出现单参数形式，因此不影响真实数据。
- `test_history_compare_jobs.py::test_ruleset_mismatch_publishes_stable_failed_code` 与同文件参数化用例的 `materialize` 行证明同一不变量。下次修改该文件时可以合并。

## 3. 验收核对

| 验收项（执行计划 §2 S2a） | 结果 | 证据 |
| --- | --- | --- |
| 内容 1 table_rules：`compare_excluded_columns`、列处置校验、ordered 去 `no`、`ComparisonRuleView/RuleSet` | 满足 | `396cfa2d28`；ruleset golden：9 条 ordered 规则的 `ignored_columns` 去掉 `no`，`composite_signal_point` 按设计 §4.4 将 `formula_ast_json`、`point_name` 移入 compare-excluded |
| 内容 2 snapshot_materialization：两种 digest、SET 解码、类型规范化、编解码并入 contracts | 满足 | `c3a44e785b`、`52229dcfd0`、`f5073e792a`；5 个 snapshot golden 增加两种 digest；ordered `gid` 规范为 `INT UNSIGNED NOT NULL` |
| 内容 3 storage_projection：canonical set、manifest 发布、存储约束、DC14、DC15、manifest 3.1.0 读写分开 | 满足 | `937c7b4cb9`。写入经 `publish.py:84` 与 `package.py:92` 只接受 3.1.0；解码接受 3.0.0/3.1.0；`test_projection_collects_schema_failures_for_every_table_and_column`；`test_storage_vocabulary_accepts_observed_unsigned_float_and_datetime_types` |
| 内容 4 comparison：`ComparisonRequest`、角色语义与 DC16、列名与有效键对齐、提前退出、`ComparisonTablePolicy` 内部化 | 满足 | `24db2eb802`。`_can_table_early_exit` 要求 business schema digest 相等；`ComparisonTablePolicy` 不再从包导出、包外无引用；`test_comparison_rule_roles.py` 三组参数表 |
| 内容 5 surface_assembly：自有身份标注、内容事实计入变化计数 | 满足 | `d0c44c55f9`；surface_assembly 不再导入 `IdentityStatus` |
| 内容 6 Application：受理冻结 digest、每步检查、两个 MISMATCH 码、删除三个函数、History oracle | 满足 | `711870cf97`。Preview：`preview_jobs.py:487/568/694` 三步检查；History：`compare_jobs.py:_assert_runtime_ruleset`；control DB 基线 `comparison_ruleset_digest TEXT NOT NULL`；受理指纹含该 digest（`test_accept_binding_fingerprint_freezes_comparison_ruleset_digest`）；三个函数在 src 中已无引用 |
| owner：`test_canonical_snapshot_identity.py`（真实 Dolt，S2b 门槛） | 满足（覆盖不足见 S2a-F2） | V runner backend 批次 2794 passed、0 skipped；审核 worktree 中重跑通过 |
| owner：Preview（含受理后、materialize 前激活）与 History 的恢复用例 | 满足 | `test_preview_rejects_ruleset_change_before_each_step`、`test_history_compare_rejects_runtime_ruleset_change_before_each_step`，均为 materialize/assemble/publish 三行参数表 |
| BROWSE_ONLY/SNAPSHOT_ONLY 先与 legacy oracle 核对再冻结 | 满足 | handoff §4 列出 legacy planner/engine、assembler、semantic 三处结论；冻结形态（表级内容事实、无行记录）与设计 §4.3/§4.5 一致 |
| golden 与 digest 一次性更新并写明理由 | 满足 | handoff §6：9 个 golden 文件，逐类说明 |
| 导入基线不新增条目 | 满足 | 审核 worktree 中 `import_rules` 输出 3 / 0 / 14 |
| 阶段末重建并运行 compose 旅程；History 与空基线旅程不变 | 满足 | V 重建 RS 并完整运行 runner；Compose 旅程在 backend 批次中通过。非空基线 Preview 对有序表的变化见 S2a-F3 |
| 中间状态：Preview 上传侧仍为原始快照（R1） | 满足 | handoff §4；条件路径 `http_arrow.py` 未启用 |
| DC12 / DC15 处置 | 满足 | DC12 未触发，JSON fail-closed（`test_json_remains_fail_closed_without_dc12_evidence`）；DC15 词表扩充，含 FLOAT 的真实 Dolt 往返通过；负零见 S2a-F1 |
| 携带项 G8b-F1、G8b-F3、G3-F2、G3-F3 | 满足 | `ordered.py` 状态随 mode，`test_comparison_ordered.py:436` 对全部参数行断言；`risk.md:189` 引用 R5 §8（锚点存在）；seed 注释已改；设计 §10 已删去该句 |
| 路径预算 | 满足（少列三处，见 S2a-F4） | 预算外路径 handoff 已列出 Preview HTTP 受理接线、`storage_projection/package.py`、Submit 候选筛选 |

## 4. 实际执行的检查

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 依赖准备 | `GATEWAY_DEV_OFFLINE=1 ./vnext/scripts/prepare-dev-dependencies.sh`（审核 worktree） | exit 0，`git status` clean |
| 五包静态检查 | 每包 `ruff check .` 与 `mypy` | 全部通过（backend 466、repository_service 198 个源文件） |
| 导入规则 | `cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules` | 3 violations / 0 cycles / 14 unreachable |
| S2a owner 抽跑 | `pytest` 运行 `test_canonical_snapshot_identity`、`test_canonical_state_identity`、`test_table_rules_comparison_view`、`test_comparison_rule_roles`、`test_comparison_planning`、`test_comparison_ordered`、`test_storage_projection_core`、`test_surface_assembly`、`test_snapshot_materialization_contracts`、`test_preview_job_worker`、`test_history_compare_jobs`、`test_history_compare_transactions`、`test_control_db_schema`、`test_submit_transactions` | 218 passed |
| 真实 Dolt 往返探针 | 复制 `test_canonical_snapshot_identity.py` 的流程，替换列与值后逐组运行，随后删除 | FLOAT `3dcccccd/33d6bf95/bf9d70a4/4b800001/c2f6e979/3eaaaaab/00000001/00800000`、`INT UNSIGNED` 0 与 4294967295、BIGINT 两端均无损；`-0.0` 读回为 `+0.0`（S2a-F1）。FLT_MAX 的失败来自探针自身用 `.9g` 写出的越界字面量，与生产渲染无关 |
| 根因追溯（S2a-F3） | 读取 base `1c7398572f` 的 `pair_pipeline.run_preview_pair_pipeline` 与 Submit 受理候选筛选 | base 的 Preview 不传 `table_policies` |
| 门禁日志 | `/home/dev/gdds-p5-closure-s1-gate-logs/s2a-gate-741d227991.log` | preflight 全部为空闲状态；runner 起止 HEAD 均为 V，起止 status 均 clean；`runner_exit_code=0`；各批次 242 / 152 / 154 / 2794 / 1681+1 skipped / 205 |
| V1 失败日志 | `s2a-gate-711870cf97.log` | 5 个失败：4 个 checkpoint 诊断期望、1 个有序 History Compose 旅程 Submit 超时。与 handoff §8 一致 |
| carried（RS） | 在 `/home/dev/gdds-p5-s2a`（H）运行 `build_context_digest.py identity`，并 `docker image inspect gateway-repository-service:local` | build-input `29f7dfd3…`、source-tree `sha256:2c92331c…` 与 label 一致；镜像 ID `7f4fdcc3…` 等于 provenance |
| carried（backend/worker） | 同一 worktree：`COMPOSE_PROJECT_NAME=ordered-bisect-b-3454106-baseline docker compose -f vnext/deploy/compose.yaml build backend worker` | exit 0；backend `887130ce…`、worker `5170755…` 与 V provenance 相同 |
| V..H 路径 | `git diff --name-only 741d227991..39efa08db1` | 只有 handoff |

## 5. 验证限制与剩余前置

- 我没有完整重跑权威 runner；门禁证据取自 V 的日志，并以 carried 复核绑定到 H。
- 真实数据中是否有 FLOAT/DOUBLE 负零未核实。审核方不读真实 dump；S2b 的真实数据验收第 2 条（同一 dump 重传为 `NO_CANONICAL_CHANGE`）会覆盖这一点。
- 进入 S2b 的前置：
  - S2a exit pass 及真实 Dolt 同一性 owner 通过，均已满足；
  - S2b 第一项先处理 S2a-F1 与 S2a-F2，再做 R1 切换；
  - S2b 实施 §4.8 时删除 Submit 前缀启发式（S2a-F3）。
- G8a-F1（普查 `ordered_projection.status` 在未扫描时为 COMPLETE）仍待下一次使用普查前修复。S2b 若重跑普查，须先修。

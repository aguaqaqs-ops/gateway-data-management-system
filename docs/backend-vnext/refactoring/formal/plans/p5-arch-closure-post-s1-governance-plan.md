# P5 架构收口：S1 合入后的治理修订计划

日期：2026-10-10

状态：owner 授权（2026-10-10）。S1 已于同日以 `139ee5fffd` 合入 `main`（tag `p5-s1-exit`，第 3 次复审通过）。
G1、G5、G9 已完成（执行计划 §1、§8 与 AGENTS.md「主线开发与阶段边界」）。owner 于同日决定：G3 选方案 A（实施为独立一步）；G8 先由 G2 的普查重跑补齐统计，再决议；
S1 旧 worktree 与分支留到 P5 exit 清理（G10）。G6、G7 为构建与 harness 修订，随 G2 的门禁一并验证；G2 按阶段流程独立审核；G4 可选。

关联：[执行计划](p5-arch-closure-execution-plan.md) §1、§8；[S0 owner 决议](p5-arch-closure-s0-owner-decisions.md)；[AGENTS.md](../../../../../AGENTS.md)；[testing-conventions](../../../testing-conventions.md)。

## 1. 背景与已完成部分

S1 的三轮复审暴露了三类流程成本：阶段分支与 `main` 的同步、门禁之后的纯文档提交使容器门禁按字面失效、权威 runner 在 dirty worktree 上必然失败。owner 于 2026-10-10 决定：

- 容器门禁结果可在镜像身份等价时沿用（已提交 `918a6e5ef8`）；
- AGENTS.md 增加“项目前提”和权威 runner 运行前提，修正测试项数与命令示例（与本计划同一提交）；
- S1 合入后改为在 `main` 上直接推进，阶段边界用 tag 标记（本计划 G1、G5）；
- 全新项目，没有兼容或迁移要求（已写入 AGENTS.md“项目前提”；对现有计划的影响见 G3）。

本计划只登记上述决定引出的后续修订，不改变 §2 各阶段的验收内容与 §3 的路径预算。

## 2. 修订项

### G1. 执行计划 §1、§8 改为主线开发（文档；已完成）

- **§8.1 分支与提交**：
  - 阶段实施直接提交到 `main`，在主工作区进行；只有确需并行的工作才开短期分支，完成后尽快合回。
  - 审核与复审在 `git worktree add --detach /home/dev/gdds-review-s<N> <候选 SHA>` 的只读 worktree 中进行，结束后删除；审核者不在主工作区运行测试，避免与实施互相写入。
  - 阶段边界：审核通过后，owner（或受托的审核对话）在记录通过结论的审核报告提交上打附注 tag `p5-s<N>-exit`；审核报告作为纯文档提交快进合入 `main`，按镜像身份等价沿用容器门禁结果。
  - 审核对象为提交区间 `<上一阶段 tag>..<候选 SHA>`；复审对象为 `<上次候选 SHA>..<新候选 SHA>`。
  - 删除“以 `--no-ff` 合入 `main`、删除工作分支与 worktree”的条目。
- **§8.2 handoff**：`authorized_base`、`merge_base_with_main`、`candidate_ref` 改为 `range_start`（上一阶段 tag）与 `candidate`（handoff 所在提交）；“实现 HEAD 与分支末端”改为“实现 HEAD 与候选末端”；镜像记录按 testing-conventions 的 `carried` 字段填写。
- **§8.7 提示词模板**：实施、审核、复审三个模板改用提交区间和只读审核 worktree；审核验证项改为“在候选提交上按 AGENTS.md 的运行前提执行权威 runner，或复核 `carried` 判定”。
- **§1 执行形态**：把“parser 修复”前置改为 G2 的“真实数据格式保真前置”。
- §8.4、§8.5 的子步编号与内容不变。

### G2. 真实数据格式保真前置（代码，S1 合入后、S2a kickoff 前）

状态：已完成。第 1 次审核（2026-10-11）为**定向修订**（`plans/p5-arch-closure-g2-independent-review.md`）：阻塞项 G2-F1 是 G2.1 把 `SET` 白名单收紧得比 `p5-s1-exit` 更严，
标准 mysqldump 头的 `@OLD_*` 语句被拒绝，`rd-t3-c-v1` 因此失败。修订后只在原白名单上增加精确名 `@saved_cs_client`，新的门禁提交 V′ `0889fa953d` 完整门禁 exit 0，census 重跑。
第 1 次复审（同日，`plans/p5-arch-closure-g2-independent-rereview-1.md`）**通过**，tag `p5-g2-exit` 在复审报告提交 `1e0da258e8` 上；遗留一项非阻塞问题 G2R-F1（census JSON 中 `rd-t3-c-v1` 的
`materialization_diagnostics` 是过期值，须在 G8 决议前更正）。G2.2、G2.3 已通过审核。

S1 普查发现 vnext 解析器有三处与真实数据或 legacy 实现不一致。生产上传当前只走 SQL 物化，composite 与 XML 解析器在不可达基线中，因此只有第 1 项影响现行生产路径；第 2、3 项在 S3 接入 composite 后才会生效，但普查和 S2a 重跑都依赖它们。

| # | 问题 | 位置 | 修复 |
| --- | --- | --- | --- |
| 1 | `SET @saved_cs_client` 不在 source dump allowlist 中，8 份数据在生产解析路径上全部失败 | `capabilities/table_access/_sql_statements.py` `_allowed_set_name` | 按 mysqldump 标准输出放行该语句；同时删除普查脚本中仅供诊断的 `_diagnostic_sql_parser_context` 补丁 |
| 2 | composite AST 要求 `Digital` 的属性写作 `Value`；legacy 与真实数据（t2）都用小写 `value`，backend 测试中没有任何 `Digital` 用例 | `capabilities/composite_signal/_ast.py` `_ATTR_VALUE`（P3-R3 `7989e47d08` 引入） | `Digital` 属性改为 `value`；补真实形态的 AST 用例；digest 输出键本就是 `"value"`，不受影响 |
| 3 | `max_xml_depth=64`，t3/t4 的 `logics.xml` 超限；legacy 默认 512 | `capabilities/table_access/contracts.py` | 普查先记录 8 份 XML 的实际最大深度，按实测值加余量确定上限并写明依据；保持 fail-closed（资源上限属于 AGENTS.md 规定不得跳过的基础边界） |

执行形态（owner 2026-10-10）：G2 连同 G6、G7 作为一个阶段性任务在 `main` 上实施，区间起点 `p5-s1-exit`，独立审核通过后在审核报告提交上打 tag `p5-g2-exit`；S2a 的区间起点为 `p5-g2-exit`。
handoff 为 `plans/p5-arch-closure-g2-handoff.md`，审核报告为 `plans/p5-arch-closure-g2-independent-review.md`。G2 改变生产 SQL 解析、构建上下文与 harness，容器门禁必须在门禁提交上真实重建并运行，不得沿用 S1 的结果。

补充要求：

- 修复 `Digital` 属性后，t2 可能暴露后续的格式不一致（composite 阶段在第一个错误处停止）。每个新增差异都按 legacy 解析器与真实数据核对，只修大小写、命名这类格式保真问题；
  涉及 AST 结构或业务语义的差异，停止并在 handoff 中交 owner，不自行改语义。
- `max_xml_depth` 取值必须验证整条 composite 链路：XML 解析、AST 构建、`ast_to_json` 与 JCS 序列化都有按层递归，取值接近 Python 递归上限时会在更深的文档上以 `RecursionError` 失败而不是 fail-closed。
  用恰好等于上限深度的合成文档走完整条链路，并写明上限的依据。
- 普查记录增加每份 `logics.xml` 的最大深度，以及重复键的分类统计（只记数量与表名、键列名，不含行内容）：整行完全相同的额外行数，与同键但取值不同的冲突行数；这两项是 G8 owner 决议的依据。
  普查 JSON 仍不含行数据与主机路径。

验收：

- 三项各有一个按业务行为命名的权威用例；
- 普查脚本以诊断模式重跑 8 份数据并更新 census JSON：业务快照 COMPLETE，或失败原因登记 owner 处置；
- 五包 ruff/mypy、`import_rules` 不增；
- 按阶段流程独立审核；第 2、3 项不改变现行生产路径行为，第 1 项改变生产 SQL 解析，审核须核对 golden 与 digest 不变。

### G3. control DB 基线 schema（owner 决议 2026-10-10：选方案 A；实施为独立一步，G2 之后、S2a 之前）

设计 DC6 规定 control DB 通过新增前向 migration 修改 schema、不做数据回填；S2a、S2b 的路径预算和验收包含 `test_*_control_db_migrations.py` 与“control DB migration 在启动时执行”。
状态：实施规格 `plans/p5-arch-closure-g3-spec.md` 已获 owner 确认（2026-10-11，D1–D6 与独立阶段）；G8a 已审核通过（`cd41349f0b`）；实施在独立 worktree `/home/dev/gdds-p5-g3` 与短期分支 `p5-g3` 上进行（owner 2026-10-11 同意；规格 §6），在 S2a 之前，门禁通过并审核后打 `p5-g3-exit`。
**已完成（2026-10-11）**：独立审核通过（`plans/p5-arch-closure-g3-independent-review.md`），tag `p5-g3-exit` 在 `cc551fc3ad`（V = `dad131350b`，H = `6dfb5bd6c9`，carried），`p5-g3` 以合并提交 `b27b1b5bd7` 并入 `main`；AGENTS.md「项目前提」已改为单一基线规则。

项目没有已部署数据，owner 决定采用方案 A：

- 把现有 migration（`infrastructure/control_db/migrations.py`，Operations v1、Workspace v1–v6，约 1,760 行，含按版本的完整性断言）合并为单一基线 schema；
  之后的 schema 变更直接修改基线；启动时 schema 版本与代码不符即拒绝启动（fail-closed），由开发者删除重建本地 control DB。
- 删除各 migration 测试，保留一个基线 schema 的权威测试。首次出现需要保留数据的部署时，再从当时的基线重新引入前向 migration。
- 其余兼容性条目（STORAGE_BREAKING migration operation、在线 ruleset 迁移）属于未来工作，不受影响。

这不是纯文档修订，所以不与 G2 合并，也不在本次提交中改写设计：它需要自己的实施规格与独立审核。规格须先核对两处契约约束，再决定哪些保留：

1. Business Lifecycle（固定 scope 归属）与 5D 设计 §6 对“migration、首次 seed、批量 seed、mapping update 必须遵循同一业务验收规则、失败不改 schema migration 版本”的要求。
   合并为基线后，历史数据的 migration 验证路径不再存在，但 seed 与 mapping update 路径必须保留这些规则；需要判断是否要修订契约文字。
2. 设计 DC6 的“新增前向 migration”表述，及 §10 中 PreviewResult、SubmitAttempt、History acceptance、archive 事件字段、`history_compare_integrity_records` 删除的描述（改为直接修改基线）；
   执行计划 §2 S2a/S2b 验收、§3 S2a/S2b 路径预算与 §6 镜像重建判定表中的 migration 条目随之改写。

实施规格完成并获 owner 确认之前，设计与执行计划中的 migration 表述保持原状，仅在 DC6 与 §10 处加了指向本节的注记。

### G4. 普查工具（随 G2，可选）

G2 完成后，SQL 回退扫描只用于定位残余失败。若 G2 之后仍有业务快照失败，可把回退扫描扩展到所有业务阶段失败（目前只在 `COMPOSITE_LOGIC_FAILED` 时启用），使键扫描统计不依赖 XML 与 composite。

### G5. AGENTS.md 增加主线开发规则（文档，与 G1 同一提交；已完成）

在“Docker / Compose 验证”之前增加一节，内容取自 G1：直接提交到 `main`、阶段 tag、审核使用只读 detached worktree、只为并行工作开短期分支、审核对象为提交区间。

### G6. backend/worker 镜像的构建上下文卫生与身份（构建，随 G2 的门禁；源自 S1 第 3 次复审 R3-F1）

状态：部分完成。`**/.hypothesis` 已排除且镜像内为空（G2 审核通过）；“在干净 worktree 重建的 image ID 与门禁一致”**未达成**（G2-F2、G2-F3），carried 第 3 条的“同一 worktree”限制已于 2026-10-11 恢复并写明原因；可复现性转入 G6b。

- 现象：`vnext/.dockerignore` 没有排除 `**/.hypothesis`，`COPY shared_kernel` 把 worktree 里被 git 忽略的 Hypothesis 缓存（门禁用的 backend 镜像中实测 `/app/shared_kernel/.hypothesis`，108 KB）打进镜像。
  backend/worker 的 image ID 因此依赖构建它的 worktree 的本地状态：换 worktree 或两次构建之间运行过测试，ID 都会变化；开发缓存也进入了 production 镜像。
- 修复：把 `**/.hypothesis` 加入 `vnext/.dockerignore`（同时检查其他测试缓存与 `tests/` 是否需要进入 production 镜像）；可选地为 backend/worker 增加与 RS 同类的 source identity label，使 `carried` 判定不再依赖 image ID。
- 验收：下一次阶段门禁中 backend/worker 镜像内没有 `.hypothesis`（已满足）；在干净 worktree 重建的 image ID 与门禁一致（未满足，见 G6b）；满足后才删除 carried 第 3 条的“只接受同一 worktree 内比较”限制。
- 这属于 AGENTS.md 的强制重建项（构建上下文变化），按 G2 的门禁在最终 HEAD 重建并运行。

### G6b. backend/worker 镜像身份的可复现性（构建；owner 决定是否实施；源自 G2 审核 G2-F2、G2-F3）

- 事实（G2 审核实测）：backend/worker 的 image ID 取决于构建上下文里 git 不记录的本地状态。同一提交在两个 worktree 中，只要 `repository_client` 文件的权限位不同（644/755 对 664/775，由创建文件的 umask 决定），
  `COPY repository_client` 及其后的全部层就不命中缓存，重新执行 `uv sync` 并得到不同的 ID；mtime 不是缓存键。被忽略的残留目录（V 的镜像里有 git 中不存在的空目录 `gateway_backend/cache`）也会进入镜像。
  G2 实施方在新 worktree 里核对 carried 得到假的“不等价”，多跑了一次完整门禁；在 V 的门禁 worktree 里同样的重建与 V 的 provenance ID 完全一致。
- 选项：
  - A. 给 backend/worker 增加与 RS 同类的 source identity label（由已跟踪文件内容计算），carried 判定改为重算 label，不再比较 image ID；
  - B. 让构建上下文只取已跟踪文件（导出目录作为 context），并用 `COPY --chmod` 等消除权限位依赖；
  - C. 不做；接受“同一 worktree + 缓存仍在”的规则，阶段退出的 carried 判定由实施方在门禁 worktree 内完成，独立审核在同一 worktree 复现。
- 审核方建议：C 足够当前使用；若独立审核需要在门禁 worktree 之外复核 carried，或再次因此多跑门禁，改做 A。A 改动 Dockerfile 与 Compose，属强制重建项，应并入下一个本来就要重建镜像的提交。
- **owner 决议（2026-10-11）：选 C**，不实施。carried 判定继续按 AGENTS.md 第 3 条在门禁 worktree 内完成，G2 复审已按此复现成立。
  重新评估条件：独立审核需要在门禁 worktree 之外复核 carried，或再次因此多跑一次完整门禁，则改做 A。G2-F3 的空目录问题随之不处理，除非 A 被启用。

### G7. client e2e 测试镜像的叠层缺陷（harness，随 G2 的门禁；源自 R3-F2）

状态：已完成，详见 `plans/p5-arch-closure-g2-handoff.md`。

- 现象：`compose_lifecycle_harness.py` 在 `gateway-repository-client-e2e:local` 带有相同 uv-lock label 时，把它自己当作 `BASE_IMAGE` 并以同一 tag 输出，
  每换一个候选 SHA 重建一次就叠一批层；S1 门禁前该镜像已有 124 层，超出 overlay2 深度上限后所有依赖它的 Compose 用例报 `max depth exceeded`。
  处置办法（手工 `docker rmi`）会同时丢掉预装依赖基础镜像，使下一次构建在慢网络上超时。
- 修复：依赖基础镜像与最终测试镜像使用不同 tag，基础镜像只在 uv-lock 变化时重建；或在构建前检查层数。
- 验收：连续在两个不同候选 SHA 上运行权威 runner，client 镜像层数不增长。修改 harness 属于强制重建项。

### G8. 真实数据中的重复有效键（owner 决议，S2a kickoff 前；源自 R3-F3）

- 事实（S1 census，均为 partial 统计）：t1 两份各在 `b1_n2_iec104_syx_list` 有 3 条额外行；t2 v1 有 3,032 条（16 张表），v2 有 2,653 条（14 张表），集中在各 `b1_n<k>_iec104_syx_list`（每张 362 条）与 `_yc_list`（每张 17 条）。
  t1 只覆盖 102/133 张表，t2 只覆盖 181/216 张表，t3/t4 未评估，未覆盖表中也可能有重复。
- 契约后果：Canonical Storage §3 要求规范键整表唯一，禁止 dedup、last-write-wins；设计 §4.2 规定无键、重复键、缺键 fail closed。t1、t2 经公开 HTTP 的 Preview 因此不能成功，S2b 的 DC22 验收无法通过，除非先决定这些重复的处置。
- 需要 owner 决议的方向（不允许实现侧悄悄去重）：这些表在规则中的有效键定义是否有误（改规则键，使其唯一）；该表是否不应作为 canonical keyed table（改表角色）；或者数据本身需要清理（由 owner 处理源数据）。
- owner 于 2026-10-10 同意：先由 G2 的普查重跑补齐统计（含整行重复与冲突行的分类），再作决议；在此之前不改规则键，也不改任何去重行为。
- 时点与落点：在 S2a kickoff 前决议并写入决议记录；S2a、S2b 的验收文字写明 DC22 对这些表的预期结果；G2 之后的普查重跑补齐 t3/t4 与未覆盖表的统计，作为决议依据。
- 统计已补齐（G2 普查重跑，`p5-s1-exit..p5-g2-exit`，census JSON 与 handoff §8）：八份数据共 50,565 条重复有效键额外行（完全相同 0、冲突 50,565），160 个 dataset-table 重复记录，键来源均为 `EXPLICIT_RULE`；
  t3 两份各 9,817 条、24 张表，t4 两份各约 1.26 万条、40 张表。每个重复表有 `differing_columns` 与 `max_group_size`：160 条记录中 130 条只有 `no` 不同（占 44,880 条额外行），重复表的键列为 `gid`，最大重复组 1,625 行。
  决议前置 G2R-F1 已更正（`3c42f64140`，owner 授权审核方直接改为 `[]`）。
- **进展（2026-10-11）：owner 提出“规则键加上 `no`”；审核方核对后建议先不实施，先做 G8a。** 依据：
  - 160 条重复记录全部在 IEC104 有序表（`iec104_{syx,yc,syk,yt}_list`），这些表的规则是 `ORDERED_DIFF`、`ordered_policy=GID_NO_V1`、`compare_key_columns=(gid)`，
    `no` 是 `ORDERED_POSITION_COLUMN`（`ignored_columns`、`structural_columns`、`position_column`）。把 `no` 加入规则键会使位置变化被判为删除加新增，破坏 `ORDERED_STABLE_KEY` 语义，
    也与 Canonical Storage 的有序身份相冲突（真实 gid 必须唯一，`no` 必须正、唯一、连续，二者是不同概念）。
  - Canonical Storage 规定：source `gid` 为 `0 | NULL | empty` 才生成 pseudo gid（`4_000_000_000` 起、按 `no` 排序连续分配），不是重复键；`storage_projection/_ordered.py` 的 `project_ordered_rows` 也是这样实现的。
    census 的重复键扫描按 `repr(cell)` 分组，不区分 NULL、`0`、空串与真实 gid，会把空白 gid 行合并成一个“重复组”。
  - 与统计吻合（观察，不是结论）：160 条中 130 条只有 `no` 不同；93 条的额外行数恰为最大组大小减 1（只有一个大组）；`rd-t3-c-v2` 的 `b1_n2_iec104_syx_list` 最大组 1,625 行。
- **G8a（census 工具修订，不改生产代码与规则）**：对 `GID_NO_V1` 的表，重复键扫描只统计真实 gid（排除 `0 | NULL | empty`）；
  另对每张有序表调用 `project_ordered_rows`，记录成功/失败诊断码、`real_count`、`pseudo_count`（需要 `no` 正、唯一、连续）。重跑 8 份数据，更新 census JSON 与 G8 统计后再决议。
  若真实 gid 仍有重复，或投影失败，再讨论规则键与表角色；若全部为 pseudo 空白，则 G8 的“重复有效键”问题不成立，S2b 的 DC22 对这些表的预期结果随之改写。
- **G8a 结果（2026-10-11，实施 `15fdda8607`…`4ff6c44e60`，独立审核通过：`plans/p5-arch-closure-g8a-independent-review.md`）**：8 份数据的真实 gid 重复额外行 50,565 → 0；
  空白 gid 行 50,818（占有序表行 12.1%，160 个数据集-表条目），旧口径的“重复”可由空白 gid 完整解释；558 张有序表的 `project_ordered_rows` 全部 COMPLETE、0 FAILED。
  这满足上面“全部为 pseudo 空白”的条件。投影范围仅是有序身份与位置检查，不是完整 `project()`。**G8 决议仍待 owner**：规则键不需要加 `no`；DC22 对这些表的预期结果如何改写；
  以及空白 gid 行（pseudo gid 按 `no` 顺序分配）在 v1 → v2 比较中的配对行为是否需要另做一次基于真实配对的检查（未验证，审核报告 §6）。
- **owner 决议（2026-10-11）**：
  - 空白行（`gid` 为 NULL、0 或空串）没有业务意义：字段变化不比较，三种写法等价，物理存储可以归一化（现已统一为 pseudo gid，按空白行在 `no` 顺序中的先后编号）；
    空白行的新增、删除必须体现，但不要求精确位置。这与 R5 §9 一致，规则键不加 `no`，表角色与去重行为不变。G8 的“重复有效键”问题不成立。
  - 只改了空白行字段的上传：Preview 无变化，规范内容摘要变化使 Submit 照常生成新版本——接受，不改契约。
  - 审核方用合成数据运行现有比较，发现空白区间未按骨架划分、移动判定逐位置比较、位置后移逐行记录（G8b 规格 §1）。owner 决定：G8b 作为独立一步修正，`ORDERED_POSITION_CHANGED` 聚合为表级汇总。
    规格 `plans/p5-arch-closure-g8b-spec.md`；顺序在 G3 之后、S2a 之前，审核通过后打 `p5-g8b-exit`。
  - DC22 对这些表的预期采用方案 B，写入执行计划 §2 S2b。

### G9. 文档小偏差（文档；源自 R3-F4；已完成）

决议记录 §10 与 handoff §1 的“S1 不修改 `table_access` 与 `composite_signal` 的生产代码”改为“未改动 G2 涉及的解析逻辑”（S1 整体只在 `composite_signal` 的 facade 中搬迁了一个惰性包装）；
handoff traceability 的 `merge_base_with_main` 更正；handoff 中缺日志支撑的网速表述改为引用运行 2 日志。

### G10. P5 exit 清理清单（登记；owner 2026-10-10 同意留到 P5 exit 一并清理）

S1 旧 worktree 占用约 950 MB（`vnext/rust/target` 429 MB、`backend/.venv` 312 MB 等），主机可用空间 243 GB，保留的成本可以忽略；
分支 `p5-closure/s1` 已由 `139ee5fffd` 完整合入，tag `p5-s1-exit` 是阶段边界，保留分支只是被旧 worktree 占住的引用。留到 P5 exit 清理是合理的，条件是下面三点：

- worktree 里仅有的有价值内容是 `gate-logs/` 下 8 个第一轮历史日志（handoff 以 `gate-logs/...` 引用）。已于 2026-10-10 复制到
  `/home/dev/gdds-p5-closure-s1-gate-logs/s1-worktree-gate-logs/` 并核对一致；清理后 handoff 中的 `gate-logs/...` 路径对应该目录。
- 不要在旧 worktree 中运行任何测试或构建，也不要把它当作 `main` 的副本；它的 `.venv` 只用于只读核对历史。
- 清理动作在 P5 exit 之后、没有任何门禁运行期间执行。

清理清单：

1. `git worktree remove --force /home/dev/gdds-p5-closure-s1`（需要 `--force`，因为含被忽略的 `.venv` 与 `target`），再 `git branch -d p5-closure/s1`。
2. `/home/dev/gdds-p5-closure-s1-gate-logs/`：按 owner 意愿归档或删除；S1 的 `final-*` 日志是 `p5-s1-exit` 门禁证据，handoff 与第 3 次复审报告引用了它们。
3. Docker 残留：每次权威 runner 都会留下以 project 命名的 backend/worker 镜像与卷（2026-10-10 实测 892 个镜像、76 个卷；2026-10-11 为 985 个镜像、76 个卷）。只在没有门禁运行时清理，
   **不得删除或重新 tag `gateway-repository-client-e2e:local`**（它同时是预装依赖基础镜像；删除会让下一次构建在慢网络上超时，S1 因此多跑了两次完整门禁）；该镜像层数过多时用 `docker export | docker import` 压平，而不是删除。
4. 本计划各项（G2、G3、G6b、G7、G8）完成后，复核 AGENTS.md 与 testing-conventions 中 carried 规则的“同一 worktree”限制是否仍然需要。
5. G2 实施方留在 `/tmp` 的 6 个已注册临时 worktree（`gdds-g2-h-check`、`gdds-g6-final-a`、`gdds-g6-final-b`、`gdds-g6-identity-old`、`gdds-g6-verify-a`、`gdds-g6-verify-b`）：
   由实施方在 G2 修订结束时 `git worktree remove --force` 清理（不属于 P5 exit 才处理的项）。已完成：复审时 `git worktree list` 只剩主工作区与 `/home/dev/gdds-p5-closure-s1`。

## 3. 顺序

1. 已完成：S1 第 3 次复审通过 → `--no-ff` 合入 `main`（`139ee5fffd`）→ tag `p5-s1-exit`；G1、G5、G9。
2. G2（含 G6、G7，可选 G4）：在 `main` 上实施，独立审核通过后打 tag `p5-g2-exit`。G6、G7 改变构建上下文与 harness，须在门禁提交上重建并运行完整门禁，不得用 `carried` 沿用旧结果。
   实施期间只有实施者写入主工作区；其他对话不向 `main` 提交。
   2026-10-11 第一次审核结论为定向修订（G2-F1）：修订 → 新门禁提交 V′ 的完整门禁 → handoff H′ → 复审（区间 `c9a09ddb35..H′`）→ 通过后打 `p5-g2-exit`。
   已完成：复审通过，tag `p5-g2-exit` 在 `1e0da258e8`（V′ = `0889fa953d`，H′ = `eece236590`，carried）。
3. G3 实施规格 → owner 确认 → 在独立 worktree `p5-g3` 上实施并独立审核（control DB 基线 schema）。已完成：tag `p5-g3-exit`（`cc551fc3ad`），合并提交 `b27b1b5bd7`。
4. G8：G8a 已完成并审核通过（`cd41349f0b`，真实 gid 重复为 0）；owner 已决议（2026-10-11，见 G8“owner 决议”）。
5. G8b：有序比较的骨架、移动与位置变化（规格 `plans/p5-arch-closure-g8b-spec.md`），G3 之后在独立 worktree `p5-g8b` 上实施并独立审核，打 `p5-g8b-exit`。 已完成（2026-10-11）：独立审核通过（`plans/p5-arch-closure-g8b-independent-review.md`），tag `p5-g8b-exit` 在 `3c3d71fed1`，合并提交 `e04a6eb041`。
6. S2a kickoff（区间起点 `p5-g8b-exit`）。S2a 携带的非阻塞项：G8b-F1（尾部空白增删时有序状态与 mode 不一致，规定状态随 mode）、G8b-F3（`contracts/risk.md` 的 `position_changed_count` 语义）、G3-F2（seed 参数表注释）、G3-F3（设计 §10“新增列允许旧行为空”）；G8b-F2（并列规则）owner 2026-10-11 决定保留现规则。
7. P5 exit：按 G10 清理。

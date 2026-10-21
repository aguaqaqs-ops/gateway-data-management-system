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
2. `/home/dev/gdds-p5-closure-s1-gate-logs/`：按 owner 意愿归档或删除；S1 的 `final-*` 日志是 `p5-s1-exit` 门禁证据，handoff 与第 3 次复审报告引用了它们。G12 起的日志在专用测试节点 `ct108-gw-dms` 的同名目录中，开发主机上没有。AGENTS.md 与 testing-conventions 把该节点的 `TMPDIR` 设在这个目录下的 `g12-default-tmp`；归档或删除前，先把 `TMPDIR` 改到别处并同步这两份文档。
3. Docker 残留：每次权威 runner 都会留下以 project 命名的 backend/worker 镜像与卷（2026-10-10 实测 892 个镜像、76 个卷；2026-10-11 为 985 个镜像、76 个卷）。只在没有门禁运行时清理，
   **不得删除或重新 tag `gateway-repository-client-e2e:local`**（它同时是预装依赖基础镜像；删除会让下一次构建在慢网络上超时，S1 因此多跑了两次完整门禁）；该镜像层数过多时用 `docker export | docker import` 压平，而不是删除。
   G7 之后，预装依赖基础镜像是单独的 `gateway-repository-client-e2e-base:local`。这条禁令的范围由 owner 于 2026-10-18 澄清（见 §3 第 9 项）：禁止的是手工对这两个镜像执行 `docker rmi`、`docker tag` 或其他删除操作，以及任何会让 `-base:local` 被重建或删除的操作。权威 runner 按候选 label 以 `-base:local` 为底重建、并用 `-t` 改变 `:local` 的指向，属于预期行为。
4. 本计划各项（G2、G3、G6b、G7、G8）完成后，复核 AGENTS.md 与 testing-conventions 中 carried 规则的“同一 worktree”限制是否仍然需要。
5. G2 实施方留在 `/tmp` 的 6 个已注册临时 worktree（`gdds-g2-h-check`、`gdds-g6-final-a`、`gdds-g6-final-b`、`gdds-g6-identity-old`、`gdds-g6-verify-a`、`gdds-g6-verify-b`）：
   由实施方在 G2 修订结束时 `git worktree remove --force` 清理（不属于 P5 exit 才处理的项）。已完成：复审时 `git worktree list` 只剩主工作区与 `/home/dev/gdds-p5-closure-s1`。

### G11. 缩短完整门禁（runner；owner 2026-10-14，DC30；S2b 合入后、S3 kickoff 前）

状态：已完成（2026-10-17）。两位审核方均通过（`plans/p5-arch-closure-g11-independent-review.md`），tag `p5-g11-exit` 在 H `dcff8c0685`，合并提交 `fa902aa200`。
验收条款全部满足，但完整门禁只缩短约 2%（backend 批次缩短约 8%）：backend 耗时的 91.7% 来自 7 个 Compose 旅程文件，原计划的前提不成立。后续见 G11b。

backend 批次单进程约 24 分钟（S2b 门禁 2,818 个用例），占完整门禁约 30 分钟中的大部分。AGENTS.md“其余包单进程”的前提（足够快、xdist 启动开销占主导）对 backend 已不成立。

1. 先测量：在 clean worktree 上对 backend 批次加 `--durations=50` 跑一次，拆出 Compose 旅程、其他 serial 类用例与普通用例各自的耗时；
2. 参照 repository_service：backend 普通用例 `-n ${GATEWAY_TEST_WORKERS}` 并行，Compose 旅程与依赖时序、端口、Dolt 或共享持久状态的用例标 `serial` 单进程运行；
   标记与 `parallel_safe` 例外按 AGENTS.md「写测试」的审查要求逐项确认，不按 CPU 数盲目并行；
3. 同步修改 `vnext/scripts/run-tests.sh`、AGENTS.md「跑测试」与 testing-conventions；用例数量与结果不变，只改运行方式；
4. 验收：两次完整 runner exit 0，用例数与改动前一致；记录改动前后各批次耗时；独立审核后打 `p5-g11-exit`，作为 S3 的区间起点。

kickoff 补充（审核方 2026-10-16，S2b 合入后）：

- 基线：S2b 门禁 V `753c5768a5` 的 backend 批次 2,847 passed、1,631.86 s（27 分 12 秒），是改动前耗时与用例数的参照；kickoff 时仍须在 kickoff base 上自行测量一次（第 1 点）。
- 依赖授权：backend dev group 增加 `pytest-xdist==3.8.0`（与 repository_service 同版本），按 AGENTS.md「改依赖」用 `uv add --dev` 更新 `vnext/backend/uv.lock`，
  lock 必须保持 canonical PyPI identity（`test_canonical_lock_identity.py`）。不授权其他依赖变化（xdist 自身的传递依赖除外）。backend 镜像构建复制 `uv.lock`，
  因此这是强制重建项：门禁 V 上的完整 runner 本身会重建全部镜像，不从 S2b 沿用 carried。
- 范围：只改测试的运行方式与隔离（marker、`xdist_group`、测试侧固定路径或端口改为每用例独立）。不改生产代码，不删除、跳过或放宽任何用例；需要这样做才能并行的用例，标 `serial` 留在单进程批次，并在 handoff 登记。
- Compose 旅程（共享 host 8000 与 `/tmp/gateway-compose-gate.lock`）、依赖固定时间预算的用例，一律留在 `serial and not parallel_safe` 批次。
  `parallel_safe` 例外按 repository_service 的同等标准逐项审查。
- 停止条件：需要改生产代码才能让用例隔离；需要删除、跳过或放宽用例；需要 xdist 以外的依赖；两次完整 runner 中任一次出现只在并行下出现的失败且无法在测试侧定位。
- 工作区：`/home/dev/gdds-p5-g11`，分支 `p5-g11`，kickoff base 为 `main` 当时的 HEAD；按执行计划 §8 的阶段流程独立审核。

### G11b. Compose 旅程的 RS 镜像绑定与耗时测量（harness；owner 2026-10-17；S3 kickoff 前）

来源：G11 第二审 R2-F1、R2-O1 与 §2.2（`plans/p5-arch-closure-g11-independent-review.md`）。

状态：已完成（2026-10-17）。两位审核方均通过（`plans/p5-arch-closure-g11b-independent-review.md`），tag `p5-g11b-exit` 在 H `944982eb91`，合并提交 `e8b5322b3c`。
R2-F1 已修复，carried 第 3 条已写明检出最终 HEAD。方案报告推荐维持现状（完整门禁约 32.5 分钟）；两路并发预计节省约 3 分钟，是否另立一步由 owner 决定，不阻塞 S3。

1. **R2-F1 修复。** backend 的 Compose 旅程不得使用身份与当前树不一致的 repository-service 镜像。
   - 当前行为：`compose_gate_harness.ensure_repository_service_image()` 只在镜像不存在时才构建。
   - 要求：比对镜像的 build-input/source-tree label 与当前树的 identity，不一致时重建；无法计算 identity 时（例如 worktree 有未提交改动），行为与 repository_service 的 Compose harness 一致，不得静默使用旧镜像。
   - 测试：增加一个权威测试，以参数表覆盖“一致→不构建”和“不一致或缺失→构建”。
   - 修改 harness 属于强制重建项。
2. **测量。** 对 11 个 Compose 旅程用例逐个拆分以下阶段的耗时：
   - 镜像构建；
   - 起栈与就绪；
   - 旅程本身，并单独列出其中的固定等待，如租约过期、超时、轮询间隔；
   - 重启；
   - 拆栈与清理。

   测量用的计时代码不进入提交：可以临时加在调试运行里，补丁存放在 worktree 外的日志目录，供审核核对。
3. **方案报告（不实施）。** 根据测量结果，评估以下方案的预期节省、风险、涉及文件，以及是否属于强制重建项：
   - 多个旅程并发运行：需要按 project 参数化 host 端口和 gate 锁，涉及 `deploy/compose.yaml`；
   - 同一文件内共享 Compose 栈；
   - 在测试栈中缩短固定等待；
   - 部分旅程只在阶段退出时运行；
   - 维持现状。

   报告交 owner 决定是否另立一步实施。
4. **文档。** 在 AGENTS.md 与 testing-conventions 的 carried 第 3 条中写明：backend/worker 重建时检出的应是最终 HEAD（R2-O1）。
5. **验收。**
   - 门禁提交上运行一次完整权威 runner，exit 0，用例数与 G11 一致（R2-F1 新增的用例除外，须逐项说明）；
   - provenance 中的 RS 镜像 label 与 V 的 identity 一致；
   - 提交测量报告；
   - 独立审核通过后打 `p5-g11b-exit`，取代 `p5-g11-exit` 作为 S3 的区间起点。

### G12. 缩短阶段取证耗时（owner 2026-10-17，DC33；第 1 项在 S3 合入后、S4 kickoff 前实施，第 2 项即时生效）

来源：owner 要求后续过程尽量避免全量运行。耗时构成（G11b、S2b 实测）：权威 runner 约 33 分钟，其中 backend 的 Compose 旅程 25 分钟、RS serial 6 分钟；真实数据 t1–t4 约 5.5 小时，其中 t4 为 2.8 小时。
调试阶段已按 DC30 只跑 focused 测试；全量只发生在各阶段的最终 V 上，各一次。决议见 [决议记录](p5-arch-closure-s0-owner-decisions.md) §16（DC33）。

1. **按包沿用测试结果（规则与工具，需实施并独立审核）。**
   - **状态：已完成（2026-10-20 终审通过，合并提交 `86a60e58da`；见 §3 第 10 项）。** 以下为实施时的记录。
   - **实施状态（2026-10-19）：** G12 闭包摘要、runner 包选择、单测和文档已在 `p5-g12` 实施。v7 audit hook 与 `python3 -I` manifest 补测对五包均未发现闭包外读取；专用节点 `ct108-gw-dms` 上 clean V=`62a4122f9ce97615113beae3bbbf6497b3ab2adf` 的完整权威 runner exit 0，逐包结果为 242 / 152 / 154 / backend 2,839+36 / repository_service 1,715+1 skipped+205。五包 Ruff/mypy 与 `import_rules` 0/0/6 通过。V self compare 五包均可沿用；S3 V 到 G12 V 五包均需运行；`shared_kernel` 单包实跑通过。新 V 的 H carried 判定将在 handoff 文档提交后、V runner 同一 LXC worktree 完成并记录；独立审核通过前不开始 S4。完整证据见 `plans/p5-arch-closure-g12-handoff.md`；main 上的状态由审核方合入时更新。
   - **目的：** 包的测试输入没有变化时，沿用上一次已验证 V 的结果，不再运行。后续阶段主要改 backend，预计每阶段可沿用 RS 与三个小包，约省 6 分钟；backend 一旦改动，其 Compose 旅程照常运行。
   - **测试输入闭包：** 对每个包定义保守的闭包，至少包括：
     - 包自身的源码、测试与 `pyproject.toml`、`uv.lock`、`.python-version`，以及其传递路径依赖：repository_client → repository_contracts；backend → shared_kernel、repository_contracts、repository_client、`rust/gateway-compute-python` 的 workspace crate；repository_service → repository_contracts；
     - 所有包共同读取的 `vnext/fixtures/`、`vnext/scripts/`、`vnext/repository-workspace.toml`、`vnext/rust/rust-toolchain.toml`、`vnext/deploy/` 与五个 `uv.lock`（runner 的 uv wrapper 会检查五锁）；
     - 包实际使用的 Hypothesis storage directory（`HYPOTHESIS_STORAGE_DIRECTORY` 或包目录下 `.hypothesis`）及包内 `.pytest_cache` 的非 Git 内容和权限；缓存可能被测试工具读取并参与生成输入，Hypothesis Unicode JSON gzip 以解压后的 payload 摘要；
     - backend 和 repository_service 测试会构建的镜像输入：完整 `vnext/` Docker build context、Compose 文件和相关 Dockerfile。backend 覆盖 backend、worker 与 repository-service 镜像；repository_service 覆盖 repository-service、repository-client e2e 与 dependency-base 镜像。完整 context 同时覆盖 Dockerfile COPY 的其他目录；有效 build 参数/镜像选择需纳入摘要；所有可能被复用的 base、service 与 dependency-base tag 对应的本机 image ID 逐项记录，backend 的 prebuilt 模式还要摘要本机镜像清单；
     - backend Rust 扩展读取的 workspace crate、`Cargo.lock` 与 `rust-toolchain.toml`；生成的 `target/` 不属于 Git tree，也不进入镜像 context；
     - 不在 Git 中的 `legacy/` 内容摘要（`test_table_rules_resolver.py` 读取它）；每包 Python `-VV` 与 Unicode database 版本、Dolt、uv、rustc 版本；有 Docker 测试的包还记录 Docker/Compose 工具与 daemon identity、effective build 参数指纹及本机选用镜像 ID。可能含凭据的 proxy/cache URL 仅记录 SHA-256，不输出原值。

     Git 中的部分按当前提交的 tree/blob object id 比较；不在 Git 中的 `legacy/` 按排序后的相对路径和文件内容计算摘要，环境项按内容计算摘要。
     每包实际使用的 uv 环境也按目录内容计算摘要，排除由锁定源码与解释器派生的 `__pycache__`、`.pyc`、`.pyo`。
   - **闭包完整性必须实测：** 对每个包运行完整测试，用 worktree 外加载的 Python audit hook 记录仓库内 `open` 路径；对 Docker build、Dolt、Rust 扩展和 shell 脚本等非 Python 读取方，说明其输入由上述完整 context、workspace、工具版本与共享脚本覆盖，并在需要时使用 `strace -f -e trace=openat` 补测。将实测路径集合与 manifest 比较；有遗漏时扩大闭包，不得缩小测试范围。审计 hook、trace 与日志留在 worktree 外。
   - **沿用条件：**
     - 来源 V 必须是实际运行了该包的权威 runner；worktree clean、日志记录起止 HEAD、该包通过且整次 runner exit 0。只运行部分包的 runner 也可作为来源；链式沿用必须直接引用最初实际运行该包的来源 V；
     - 逐项比较包 manifest，来源 V 与当前 V 完全相同才可沿用；当前 V 上闭包有变化的包都必须实际运行并通过；
     - handoff 逐包记录 manifest 总摘要、运行或沿用、来源 V 与来源日志。
   - **工具与文档：**
     - `run-tests.sh` 支持只运行指定的包，例如 `GATEWAY_TEST_PACKAGES=backend`；不指定时行为不变；
     - 新增计算与比较闭包 manifest 的标准库脚本，使用 `python3 -I`，带 unit 测试；runner 开始时为待运行包写 manifest，结束时逐包给出状态；
     - AGENTS.md「跑测试」「镜像身份等价」与 testing-conventions 写明规则。包沿用决定当前 V 运行哪些包，镜像身份等价决定 V..H 能否 carried，两者分别判定。backend 闭包含完整镜像构建输入，因此 backend 沿用时其 Compose 旅程一并沿用；
   - **不适用：** S5 的最终门禁（执行计划 §2 S5 要求全量）与发布门禁，仍运行全部包。
   - **停止条件：** 需要改生产代码；闭包无法覆盖实测到的读取；需要新增依赖。
   - **工作区：** `/home/dev/gdds-p5-g12`，分支 `p5-g12`。验收：脚本与 runner 改动的 unit 测试；一次完整权威 runner exit 0（改了 `vnext/scripts/`，所有包都必须实际运行）；闭包实测记录；独立审核后由审核方打 `p5-g12-exit`，S4 的区间起点改为 `p5-g12-exit`。
2. **真实数据按阶段改动面确定范围（即时生效）。**
   - DC30 中“在最终 V 上完整运行真实数据一次”改为：真实数据的取证范围由阶段改动面决定，在阶段 kickoff 时写明，阶段退出前由 owner 确认。范围之外的不变量依靠更小的档位或既有的 focused / Compose 覆盖。
   - 剩余阶段的范围：
     
     | 阶段 | 范围 |
     | --- | --- |
     | S3（已完成） | 完整 t1–t4。2026-10-17 第二次停止后修订为：新 V 上完整运行 t4，t1 作冒烟；t2、t3 沿用 `f73deee604` 上的通过结果（见 §3 第 9 项） |
     | S4 | t1–t3 完整运行；t4 只运行 v1 提交与 v2 Preview（SAME_PROJECT）；DIFFERENT_PROJECT 用小档之间的跨档上传验证；不运行 t4 的重传 Preview 与 History。2026-10-20 停止后修订为：新 V 上运行 t4 的 v1 Preview、v1 提交与 v2 Preview，跨档旅程，t1 冒烟；t2、t3 有条件沿用 `938d41d171` 的通过结果（见 §3 第 11 项） |
     | S5 最终候选 | 完整 t1–t4，按执行计划 §2 S5 保留 |
   - 不在 P5 内建设多档并发运行的基础设施。
   - 已同步修订：执行计划 §8.9、§2 S4 的真实数据验收、AGENTS.md「主线开发与阶段边界」中 DC30 的表述。

## 3. 顺序

1. 已完成：S1 第 3 次复审通过 → `--no-ff` 合入 `main`（`139ee5fffd`）→ tag `p5-s1-exit`；G1、G5、G9。
2. G2（含 G6、G7，可选 G4）：在 `main` 上实施，独立审核通过后打 tag `p5-g2-exit`。G6、G7 改变构建上下文与 harness，须在门禁提交上重建并运行完整门禁，不得用 `carried` 沿用旧结果。
   实施期间只有实施者写入主工作区；其他对话不向 `main` 提交。
   2026-10-11 第一次审核结论为定向修订（G2-F1）：修订 → 新门禁提交 V′ 的完整门禁 → handoff H′ → 复审（区间 `c9a09ddb35..H′`）→ 通过后打 `p5-g2-exit`。
   已完成：复审通过，tag `p5-g2-exit` 在 `1e0da258e8`（V′ = `0889fa953d`，H′ = `eece236590`，carried）。
3. G3 实施规格 → owner 确认 → 在独立 worktree `p5-g3` 上实施并独立审核（control DB 基线 schema）。已完成：tag `p5-g3-exit`（`cc551fc3ad`），合并提交 `b27b1b5bd7`。
4. G8：G8a 已完成并审核通过（`cd41349f0b`，真实 gid 重复为 0）；owner 已决议（2026-10-11，见 G8“owner 决议”）。
5. G8b：有序比较的骨架、移动与位置变化（规格 `plans/p5-arch-closure-g8b-spec.md`），G3 之后在独立 worktree `p5-g8b` 上实施并独立审核，打 `p5-g8b-exit`。 已完成（2026-10-11）：独立审核通过（`plans/p5-arch-closure-g8b-independent-review.md`），tag `p5-g8b-exit` 在 `3c3d71fed1`，合并提交 `e04a6eb041`。
6. S2a kickoff（区间起点 `p5-g8b-exit`）。S2a 携带的非阻塞项：G8b-F1（尾部空白增删时有序状态与 mode 不一致，规定状态随 mode）、G8b-F3（`contracts/risk.md` 的 `position_changed_count` 语义）、G3-F2（seed 参数表注释）、G3-F3（设计 §10“新增列允许旧行为空”）；G8b-F2（并列规则）owner 2026-10-11 决定保留现规则。 已完成（2026-10-12）：四个携带项均已关闭；独立审核通过（`plans/p5-arch-closure-s2a-independent-review.md`），tag `p5-s2a-exit` 在 `6f3e2ed67a`，合并提交 `0ce71cac27`。
7. S2b kickoff（区间起点 `p5-s2a-exit`）。S2b 携带项：
   - S2a-F1：FLOAT/DOUBLE 的 `-0.0` 经 Dolt 读回为 `+0.0`，须在规范化环节归一，在 R1 切换之前完成；
   - S2a-F2：真实 Dolt 同一性 owner 补 `INT UNSIGNED` 上限、BIGINT 两端、非二进制精确的 FLOAT 与 `-0.0`，与 S2a-F1 同一提交；
   - S2a-F3：实施设计 §4.8 时删除 Submit 的按前缀过滤启发式，包括 S2a 新增的 `comparison-ordered-`、`comparison-blank-`；
   - G8a-F1：若 S2b 重跑普查，先修普查 `ordered_projection.status`。
   2026-10-12：S2b 在真实数据旅程中停止（t1-v1 投影 23 项 `KEY_MISSING`，源 DDL 无主键）；owner 决议 DC29（无主键表兜底规则，决议记录 §12），S2b 按执行计划 §8.5 S2b.8 恢复。
   已完成（2026-10-16）：第 1 次复审通过（`plans/p5-arch-closure-s2b-independent-rereview-1.md`），tag `p5-s2b-exit` 在 `bd0b1d042f`，合并提交 `b130c35e3d`。
8. G11：S2b 合入后、S3 kickoff 前，缩短完整门禁（backend 并行化）。调试与取证分开（执行计划 §8.9，DC30）自 2026-10-14 起对 S2b 剩余部分与之后各阶段生效。
   已完成（2026-10-17）：tag `p5-g11-exit`（`dcff8c0685`），合并提交 `fa902aa200`。
   G11b：Compose 旅程的 RS 镜像绑定（R2-F1）与耗时测量；S3 kickoff 前完成，S3 的区间起点改为 `p5-g11b-exit`。
   已完成（2026-10-17）：tag `p5-g11b-exit`（`944982eb91`），合并提交 `e8b5322b3c`。S3 kickoff 的区间起点为 `p5-g11b-exit`。
9. S3 kickoff（区间起点 `p5-g11b-exit`；worktree `/home/dev/gdds-p5-s3`，分支 `p5-s3`，kickoff base `be5fd5a970`）。
   2026-10-17 停止（STOP handoff `72bdb6a9ee`）：审核方的实施提示词要求“用公开接口取得的逐表 Preview 状态，证明除 `composite_signal_point` 外各表与 S2b 相同”。这超出了执行计划 §2 S3 的验收，而且 Backend 没有公开读取逐表状态的接口。实施方没有新增接口，也没有用容器内读取代替，这样处理是对的。

   owner 决议（2026-10-17）：
   - **不新增公开接口。** 逐表 Preview 读取接口属于新的公开 Contract，不在 S3 范围内。
   - **证据要求改为公开汇总事实，并与 S2b 对照基准（s2b handoff §8.5）比较：**
     - Preview：`table_count` = S2b + 1，degraded 与 failed 为 0；v2 的 changed = S2b 值 + (composite 有变化 ? 1 : 0)；
     - RS Catalog：表数 = S2b + 1；总行数减去 `composite_signal_point` 的行数等于 S2b 的总行数；
     - History：`record_count` 与 S2b 的差值等于 composite 的 v1→v2 记录数。这个记录数由主机侧离线投影从同一批包计算，只输出计数，再用生产比较能力比较 composite 表。
     - S2b 已有的真实数据不变量继续成立。
   - **恢复 `test_comparison_canonical_domain.py` 的“同内容 → 全表 UNCHANGED”不变量。** S3 实施中，这个测试被改成断言 composite 为 `ADDED_TABLE`，原因是 Repository 侧基线夹具里没有那张零行的 composite 表。按 DC6，S3 之后的提交都带这张表，应修正夹具，不应改变测试的含义。
   - **取证期间暂停主机上与本项目无关的批量负载。** preflight 以 Dolt、Compose、8000 端口为硬条件，并记录负载。

   2026-10-17 第二次停止（STOP 记录 `ac9146da7f`；V `f73deee604` 的权威 runner exit 0）：
   - t1–t3 全部通过，t4 的 v1 Preview 也通过；t4 v1 Submit 运行到 594.8 s 时，查询 operation 状态返回 HTTP 500 `INTERNAL_ERROR`，没有留下终态证据。
   - 容器日志没有保存。
   - 审核方从代码确认了一处既有缺陷：
     - `GET /v1/operations/{id}` 用的 `ReadOnlyOperationStore` 实际执行 `BEGIN IMMEDIATE`（`bootstrap/composition.py` 传入的工厂默认 `read_only=False`）；
     - 写锁被占用超过 `busy_timeout` 5 s 时，抛出 `StoreBusy`；
     - HTTP 层没有映射 `StoreBusy`，于是返回 500。
   - 是谁持有写锁超过 5 s，尚未查明。可能与以下两件事同源：t4 v1 Preview 末尾心跳出现 `StaleWrite` 后 worker 重启；S2b 的 t4 v2 Preview 也出现过 worker cpu.stat 重置。

   owner 决议（2026-10-17）：
   - **在 S3 内修复，不另立治理项。**
     - 先在开发模式下只复现 t4 v1 Preview 与 Submit：记录写事务的持锁时长，保存全部容器日志。
     - 然后修复：HTTP 只读查询改用只读事务；`StoreBusy` 映射为 503 `SERVICE_NOT_READY`；按复现结果修正持锁过长的写入方，以及心跳在锁竞争下丢失租约、导致进程退出的路径。
     - 真实数据脚本在失败时先保存容器日志再拆栈；状态查询遇到 503 时在超时预算内重试。
     - 路径预算与停止条件见恢复提示词。
   - **取证范围（修订 DC33 中 S3 的范围）：**
     - 新 V 上完整运行一次权威 runner；
     - 真实数据完整运行 t4，t1 作为冒烟；
     - t2、t3 沿用 `f73deee604` 上的通过结果。理由：本次修复只涉及事务模式、错误映射与心跳，不触及投影、比较与 composite。
     - S5 最终候选仍完整运行 t1–t4。

   2026-10-18 独立审核初审（V `dc9c08a410`，H `96c835ac90`；V 的权威 runner exit 0，t1、t4 通过，t2/t3 按上一决议沿用）：结论为定向修订，唯一阻塞项是 S3-F1。
   - **S3-F1 的内容：** V 的 runner 中，`ensure_client_image()`（`vnext/repository_service/tests/support/compose_lifecycle_harness.py`）用 `docker build -t` 把 `gateway-repository-client-e2e:local` 指向了新镜像。审核方认为这触及实施提示词中“不得 `docker rmi` 或重新 tag 两个 client e2e 镜像”的限制。
   - **事实：**
     - 这是 G7（`84177001e1`，2026-10-10）之后 harness 的既有行为：候选 label 不一致时，以 `-base:local` 为底重建 `:local`。S1 之后的各次门禁每换一个候选都会这样做。
     - `p5-g11b-exit..H` 没有改动 harness。
     - `-base:local` 仍是 2026-10-10 构建的 `dafde407833e`（12 层）。`:local` 现为 `55c506d6ef48`（20 层），建在 base 之上，label 为 V。

   owner 决议（2026-10-18）：
   - **S3-F1 不构成违规，不需要豁免，也不需要重跑。** 禁令范围按 G10 第 3 项的澄清执行。提示词的措辞没有排除 runner 的内部构建，责任在提示词。审核方按字面严格把关，做法正确。
   - **S3-F1 改为观察项并关闭。** S3-F2（终态确认后 `completed.wait()` 无界等待，延迟 drain）保留为非阻塞观察。如果其他各项核查不变，审核结论改为通过，按惯例提交审核报告、打 `p5-s3-exit`。
   - **之后各阶段的提示词统一写为：** “不得手工 `docker rmi`、`docker tag` 或删除 `gateway-repository-client-e2e:local` 与 `-base:local`；权威 runner 按候选 label 重建 `:local` 属于预期行为。”

   已完成（2026-10-18）：按 owner 授权由审核方直接定稿，审核报告 `plans/p5-arch-closure-s3-independent-review.md`（结论通过），tag `p5-s3-exit` 在 `6b2b5fd0e1`，合并提交 `d3ce70df7a`；S3 worktree 与分支已清理。
10. **G12 第 1 项（按包沿用测试结果，已完成）**：在分支 `p5-g12` 实施；门禁 V 为 `62a4122f9c`，H 为 `5fbae736b0`。初审通过（`plans/p5-arch-closure-g12-independent-review.md`），tag `p5-g12-exit` 在 `13d97dc2db`；2026-10-20 终审通过（同一报告 §终审），合并提交 `86a60e58da`。G12 第 2 项（真实数据按阶段确定范围）即时生效，S4 按 G12 中的范围执行。
   终审的三项 finding 与 owner 决议（2026-10-20）：
   - **G12-F1（实现缺陷，不会错误沿用；转入 S4 第一步）：** manifest 在 runner 开始时记录了 `gateway-repository-client-e2e:local` 与 `gateway-repository-service:local` 的本机 image ID，而这两个镜像正是被测运行自己会重建的（client 镜像以 HEAD 为候选 label，每换提交运行 RS Compose 测试都会重建；RS 镜像在 identity 变化时重建）。来源 runner 一旦重建它们，后续任何提交都无法沿用该包；RS 在文档提交上重跑又会重建 client 镜像，无法收敛。G12 自己的证据之所以没暴露，是因为 V 的 runner 之前，审计运行已在 V 上建好了 `:local`。修正方向：这两个镜像只记录 tag 名与决定其内容的输入（`-base:local`、python base、RS dependency-base 的 ID），不记录自身 ID。
   - **G12-F2（规则）：** 专用测试节点使用 containerd image store，同一棵树连续两次全缓存构建，backend/worker 的 image ID 也不相同（`g12-H1-carried-backend-worker.log`）。carried 第 3 条的 image ID 比较在该节点上无法满足；G12 自身的退出实际依靠 H1 的 backend 实跑加 H1→H 的闭包相等。owner 决议：backend/worker 的身份改用 backend 包 manifest 在同一 worktree 中逐项相等来判定，不再比较 image ID（DC34 第二部分）。已同步修订 AGENTS.md 与 testing-conventions 的 carried 第 3 条。
   - **G12-F3（规则）：** G12 实施期间 AGENTS.md 新增“所有测试、容器门禁和取证都在专用 LXC `ct108-gw-dms` 上执行”，owner 确认这是其要求，记为 DC34 第一部分。
11. **S4 kickoff**（区间起点 `p5-g12-exit`）。S4 携带项：G12-F1，作为 S4 的第一步修复。修复改动 `vnext/scripts/`，S4 的门禁 V 因此五个包全部运行。

   2026-10-20 停止（V `938d41d171`，在 ct108 上的完整权威 runner exit 0；五包静态检查通过；`import_rules` 0 / 0 / 6）：
   - t1–t3 完整旅程通过；t4 v1 Preview 通过，`table_count` 与 changed 均为 312，composite 435 行，与 S3 一致。
   - t4 v1 Submit 在 4,047 s 预算内没有进入终态，运行 4,049 s 后按停止条件结束；没有运行 t4 v2、跨档旅程和 carried 判定。
   - 审核方只读核查日志（`s4-realdata-t4-identity-938d41d171.log` 与对应 Compose 日志，均在 ct108）：
     - 这不是变慢：S3 的同一步用时 800.757 s；S4 的 t2、t3 Submit 比 S3 更快（237→195 s、485→341 s）。
     - worker 在 Submit 第三步（每秒查询一次 RS import 的状态）中，于 10:44:13 同时停止心跳和查询，此后没有任何输出；Submit 期间 worker 的 487 s CPU 基本都在前两步，之后不再消耗 CPU；容器没有退出；backend 与 RS 的 readyz 一直正常。
     - ct108 的 `memory.events`、`pids.events` 均为 0，内存峰值约 31 GB。
     - 卡住处的代码（`operations/`、worker runtime、repository client）不在 S4 的改动中；S3 的真实数据在开发主机上运行，这是 ct108 上第一次运行 t4。原因可能是 S4 引入，也可能是既有的偶发卡死或节点差异。

   owner 决议（2026-10-20）：
   - **不加长超时，在 S4 内修复，不另立治理项。** operation 永远停在运行中、没有自动恢复，属于 A 层缺陷。
   - **real-data journey 增加 worker 停滞检测：** 心跳停滞超过阈值时，先在拆栈前保存诊断（worker 各线程的内核等待点与栈、Python 栈、容器状态、RS operation 状态、control DB 中该 operation 与租约的行、全部容器日志），再以独立的失败原因提前结束，不等满超时。只改 `vnext/backend/benchmarks/` 与对应测试。诊断留在 ct108 的日志目录，不进入 Git。允许在 ct108 上把 py-spy 装在仓库外，作为调试工具。
   - **调试：** 先在 S4 代码上只复现 t4 v1 Preview 与 Submit；复现后在 S3 V `dc9c08a410` 上同样运行一次，区分 S4 回归与节点差异。在 S4 代码上连续两次没有复现，停止并交 owner。原因在节点环境、需要改 Dockerfile/Compose/依赖或 Contract 时，同样停止。
   - **取证范围（修订 DC33 中 S4 的范围）：**
     - 新 V 上运行权威 runner，闭包未变的包可按 G12 规则沿用 `938d41d171` 的运行；
     - 真实数据运行 t4 的 v1 Preview、v1 Submit 与 v2 Preview，跨档 `DIFFERENT_PROJECT` 旅程，t1 作冒烟；
     - t2、t3 沿用 `938d41d171` 的通过结果，前提是 `938d41d171..V` 不触及投影、比较、项目身份、composite、规范存储与 census 的业务路径；触及时重跑这两档。
     - S5 最终候选仍完整运行 t1–t4。

   2026-10-21 第二次停止（候选 V `22c1a7e530`；在 ct108 上运行全部五个包，runner exit 1）：
   - **对 10-20 停止原因的更正。** 当时说 worker 卡死，不准确。实际情况是：
     - Submit 的 `await_import_result` 用一个 60 s 的对账会话轮询 RS import；会话到期时 import 仍在运行，原代码直接把 operation 置为人工恢复；
     - 此后 worker 空闲，所以既没有心跳也不消耗 CPU；
     - harness 不把这个状态视为结束，一直等到超时。
     - 在 S3 V `dc9c08a410` 上同样复现，属于既有问题，不是 S4 引入的回归。
   - **修复。** `bafd64bf53` 把这种情况改为走 R5 已有的重试策略：最多 3 个会话，每个 60 s，用尽后仍转人工恢复。撤掉修复后负向测试失败，修复后通过。修复后的 t4 调试运行中，v1 Submit 用时 576.182 s，operation 进入终态。
   - **runner 失败。** `repository_service/tests/test_upload_artifact_visibility.py::test_ready_file_without_db_is_not_visible` 报 `sqlite3.OperationalError: cannot commit - no transaction is active`。
     - 这是既有的偶发失败：2026-09-27 开发主机的 `run-tests-r2.log` 里，同一用例、同一行出现过完全相同的报错。
     - 原因在测试本身：RS 的 control DB 只有一个连接，由 app 内的后台线程和各个 store 经 `transaction_lock` 共享；该测试绕过锁，直接对私有的 `mutation_store._connection` 执行 DELETE 和 commit，与后台线程的事务竞争。
     - `938d41d171..22c1a7e530` 只改了 backend，与该失败无关。其余四个包通过。

   owner 决议（2026-10-21）：
   - **在 S4 内修复这个测试。** 只改 `repository_service` 的测试：在 `transaction_lock` 下、在明确的事务中完成删除，不改变测试要证明的内容；同一包内其他绕过锁直接操作 `_connection` 的测试一并修正。这些文件超出 S4 路径预算，在 handoff 中说明理由。
   - **新 V 上运行 backend 与 `repository_service`。** `22c1a7e530` 的 runner exit 1，按 G12 规则不能作为任何包的沿用来源；另外三个包按 `compare` 结果沿用 `938d41d171`。
   - **随后按 2026-10-20 的决议**完成真实数据、H 与 carried，范围不变。
   - **审核必查项新增两条：**
     - t4 v1 Submit 中 RS import 的用时与实际使用的对账会话数，以及与 R5 上限之间的余量。S5 要完整运行 t4，余量不足时交 owner 判断。
     - 修复中传入 `reconcile_elapsed_seconds=0.0` 是否绕过了 R5 的耗时预算。

   2026-10-21 审核（候选 H `d0b20ede10`，初审报告 `plans/p5-arch-closure-s4-independent-review.md`）：
   - 初审结论为定向修订，S4-F1：handoff 没有说明全部超出 §3 S4 路径预算的改动。终审确认成立：另有 8 个生产文件、17 个测试或测试支持文件未说明；它们都是设计 §7 验收的接线、命名调整或 DTO 目标形态带来的测试更新，没有扩大范围。
   - 终审新提出 S4-F2：`bafd64bf53` 传入 `reconcile_elapsed_seconds=0.0`，跳过了 R5 的耗时检查。R5 设计 §6 规定对账预算（60 s）用尽即转人工恢复，Submit 的 checkpoint 也持久保存 `reconcile_started_at`，按设计应从对账开始累计计时；修复后的实际上限是 3 个 60 s 会话。累计预算函数 `reconcile_session_budget_exhausted`、`parse_reconcile_started_at` 目前没有生产调用方。修复后的行为合理且有上限（t4 v1 Submit 中 RS import 79 s，使用 2/3 个会话），但它以字面量隐性改变了 R5 的规则。

   owner 决议（2026-10-21）：
   - **S4-F2 采用方案一。** Submit 的 `await_import_result` 以 R5 的 3 个 60 s 对账会话为上限，替代累计 60 s 预算；S4 不再改代码。该项作为 S5 携带项（见第 12 项）。
   - **S4-F1 只改 handoff。** 授权审核方直接修订 handoff、完成终审、打 tag 并合入，不再经实施方和初审方。
12. **S5 kickoff**（区间起点 `p5-s4-exit`）。S5 携带项：S4-F2，把 `await_import_result` 中的 `reconcile_elapsed_seconds=0.0` 改为显式、有名字的 Submit import 轮询预算（5B 设计 §13.1 允许的有上限 Repository poll 参数），在 Contract 层面写明它与 R5 会话上限的关系，并清理没有生产调用方的累计预算函数；S5 的完整 t4 记录每次 Submit 的 RS import 用时与使用的会话数。
13. P5 exit：按 G10 清理。

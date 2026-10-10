# P5 架构收口：S1 合入后的治理修订计划

日期：2026-10-10

状态：owner 授权（2026-10-10）。G1、G5 为文档修订，S1 合入 `main` 并打 tag 后直接在 `main` 上提交；G2 为代码修订，按阶段流程独立审核；G3 需 owner 决议。

关联：[执行计划](p5-arch-closure-execution-plan.md) §1、§8；[S0 owner 决议](p5-arch-closure-s0-owner-decisions.md)；[AGENTS.md](../../../../../AGENTS.md)；[testing-conventions](../../../testing-conventions.md)。

## 1. 背景与已完成部分

S1 的三轮复审暴露了三类流程成本：阶段分支与 `main` 的同步、门禁之后的纯文档提交使容器门禁按字面失效、权威 runner 在 dirty worktree 上必然失败。owner 于 2026-10-10 决定：

- 容器门禁结果可在镜像身份等价时沿用（已提交 `918a6e5ef8`）；
- AGENTS.md 增加“项目前提”和权威 runner 运行前提，修正测试项数与命令示例（与本计划同一提交）；
- S1 合入后改为在 `main` 上直接推进，阶段边界用 tag 标记（本计划 G1、G5）；
- 全新项目，没有兼容或迁移要求（已写入 AGENTS.md“项目前提”；对现有计划的影响见 G3）。

本计划只登记上述决定引出的后续修订，不改变 §2 各阶段的验收内容与 §3 的路径预算。

## 2. 修订项

### G1. 执行计划 §1、§8 改为主线开发（文档，S1 合入后）

- **§8.1 分支与提交**：
  - 阶段实施直接提交到 `main`，在主工作区进行；只有确需并行的工作才开短期分支，完成后尽快合回。
  - 审核与复审在 `git worktree add --detach /home/dev/gdds-review-s<N> <候选 SHA>` 的只读 worktree 中进行，结束后删除；审核者不在主工作区运行测试，避免与实施互相写入。
  - 阶段边界：审核通过后，owner（或受托的审核对话）在审核对象上打附注 tag `p5-s<N>-exit`；审核报告作为纯文档提交加到 `main`，按镜像身份等价沿用容器门禁结果。
  - 审核对象为提交区间 `<上一阶段 tag>..<候选 SHA>`；复审对象为 `<上次候选 SHA>..<新候选 SHA>`。
  - 删除“以 `--no-ff` 合入 `main`、删除工作分支与 worktree”的条目。
- **§8.2 handoff**：`authorized_base`、`merge_base_with_main`、`candidate_ref` 改为 `range_start`（上一阶段 tag）与 `candidate`（handoff 所在提交）；“实现 HEAD 与分支末端”改为“实现 HEAD 与候选末端”；镜像记录按 testing-conventions 的 `carried` 字段填写。
- **§8.7 提示词模板**：实施、审核、复审三个模板改用提交区间和只读审核 worktree；审核验证项改为“在候选提交上按 AGENTS.md 的运行前提执行权威 runner，或复核 `carried` 判定”。
- **§1 执行形态**：把“parser 修复”前置改为 G2 的“真实数据格式保真前置”。
- §8.4、§8.5 的子步编号与内容不变。

### G2. 真实数据格式保真前置（代码，S1 合入后、S2a kickoff 前）

S1 普查发现 vnext 解析器有三处与真实数据或 legacy 实现不一致。生产上传当前只走 SQL 物化，composite 与 XML 解析器在不可达基线中，因此只有第 1 项影响现行生产路径；第 2、3 项在 S3 接入 composite 后才会生效，但普查和 S2a 重跑都依赖它们。

| # | 问题 | 位置 | 修复 |
| --- | --- | --- | --- |
| 1 | `SET @saved_cs_client` 不在 source dump allowlist 中，8 份数据在生产解析路径上全部失败 | `capabilities/table_access/_sql_statements.py` `_allowed_set_name` | 按 mysqldump 标准输出放行该语句；同时删除普查脚本中仅供诊断的 `_diagnostic_sql_parser_context` 补丁 |
| 2 | composite AST 要求 `Digital` 的属性写作 `Value`；legacy 与真实数据（t2）都用小写 `value`，backend 测试中没有任何 `Digital` 用例 | `capabilities/composite_signal/_ast.py` `_ATTR_VALUE`（P3-R3 `7989e47d08` 引入） | `Digital` 属性改为 `value`；补真实形态的 AST 用例；digest 输出键本就是 `"value"`，不受影响 |
| 3 | `max_xml_depth=64`，t3/t4 的 `logics.xml` 超限；legacy 默认 512 | `capabilities/table_access/contracts.py` | 普查先记录 8 份 XML 的实际最大深度，按实测值加余量确定上限并写明依据；保持 fail-closed（资源上限属于 AGENTS.md 规定不得跳过的基础边界） |

验收：

- 三项各有一个按业务行为命名的权威用例；
- 普查脚本以诊断模式重跑 8 份数据并更新 census JSON：业务快照 COMPLETE，或失败原因登记 owner 处置；
- 五包 ruff/mypy、`import_rules` 不增；
- 按阶段流程独立审核；第 2、3 项不改变现行生产路径行为，第 1 项改变生产 SQL 解析，审核须核对 golden 与 digest 不变。

### G3. “无兼容、无迁移”对现有计划的复核（owner 决议，S2a kickoff 前）

设计 DC6 规定 control DB 通过新增前向 migration 修改 schema、不做数据回填；S2a、S2b 的路径预算和验收包含 `test_*_control_db_migrations.py` 与“control DB migration 在启动时执行”。在没有已部署数据的前提下，可以考虑：

- **选项 A（建议）**：S2a 前把现有 migration 合并为单一基线 schema；之后的 schema 变更直接修改基线，启动时 schema 版本不符即拒绝启动（fail-closed），由开发者删除重建本地 control DB。删除各 migration 测试，只保留一个基线 schema 的权威测试。首次出现需要保留数据的部署时，再从当时的基线重新引入前向 migration。
- **选项 B**：维持 DC6 现状。

选择 A 时同步修订：设计 DC6 与 §10、执行计划 §2 S2a/S2b 验收、§3 S2a/S2b 路径预算、§6 镜像重建判定表中的 migration 条目，并在决议记录中登记。其余兼容性条目（STORAGE_BREAKING migration operation、在线 ruleset 迁移）本就属于未来工作，不受影响。

### G4. 普查工具（随 G2，可选）

G2 完成后，SQL 回退扫描只用于定位残余失败。若 G2 之后仍有业务快照失败，可把回退扫描扩展到所有业务阶段失败（目前只在 `COMPOSITE_LOGIC_FAILED` 时启用），使键扫描统计不依赖 XML 与 composite。

### G5. AGENTS.md 增加主线开发规则（文档，与 G1 同一提交）

在“Docker / Compose 验证”之前增加一节，内容取自 G1：直接提交到 `main`、阶段 tag、审核使用只读 detached worktree、只为并行工作开短期分支、审核对象为提交区间。

## 3. 顺序

1. S1 最终复审通过 → 合入 `main` → 在合入提交上打 `p5-s1-exit`。
2. G1 + G5：一次文档提交。
3. G3：owner 决议并按所选选项修订文档。
4. G2（含可选 G4）：在 `main` 上实施，独立审核通过后打 tag。
5. S2a kickoff。

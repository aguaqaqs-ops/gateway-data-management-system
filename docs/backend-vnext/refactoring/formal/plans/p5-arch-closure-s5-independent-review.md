# P5 架构收口 S5 独立审核

- 结论：**定向修订**
- 日期：2026-10-22
- 审核对象：`p5-s5` 的 H `89deee36a9e317c0893fc955a01950d4db1aacf4`。
- 门禁 V / 实现 HEAD：`b79844ddc2304a23a3e6fe386f40aed671c5047b`。
- 区间：`p5-s4-exit`（`5634dc6f9b`）..H；V..H 只修改 S5 handoff。
- 依据：[执行计划](p5-arch-closure-execution-plan.md) §2 S5、§3 S5、§6–§8.9；[收口设计](p5-arch-closure-design.md) §9/§11/§13/§14；[P5](p5-business-vertical-slices-design.md) §2A.5；DC30–DC34、G10/G12；[Performance Measurement Guidance](../contracts/performance-measurement-and-baseline.md)；[Phase 6 讨论稿](p6-planning-discussion.md) §3/§9 V2；AGENTS.md、testing-conventions.md、[S5 handoff](p5-arch-closure-s5-handoff.md)，以及本次任务指定的 main owner 决议。
- 审核位置：CT108 上新建的 detached worktree `/home/dev/gdds-p5-s5-independent-review`；审核和检查期间固定 H、tracked 内容只读。检查结束后仅写本报告。未参与 S5 实现。

## 1. 结论摘要

S5 的生产修复方向、fresh 镜像、V 全量 runner、真实 t1–t4 终态与 V→H carried 证据成立。独立运行的五包 ruff/mypy 和 import_rules 通过，未发现需要重建核心架构的错误。

有两项阻塞：S4-F2 要求清理的无生产调用方累计预算分支仍然存在，且文档误称有其他生产 caller；DC32 必交测量存在 Submit 父子计时重复相加、覆盖缺口及时间边界混用，不能按 handoff 的现有数字作成本归因。另有一项非阻塞的 owner 决议记录修正。应完成定向修订后独立复审；本报告不宣布 S5 通过、P5 exit，也不执行 G10 cleanup。

## 2. Findings

### S5-F1：累计耗时模式没有生产调用方，S4-F2 清理尚未完成

- 类型：已证实缺陷；阻塞：是。
- 位置：`operations/recovery.py:98,205,438,524,709`；`application/submit_jobs.py:852`（均相对 `vnext/backend/src/gateway_backend/`）；handoff §2（第 50 行）、R5 设计 §6（第 147 行附近）、5B 设计 §13.1（第 767 行附近）。
- 依据：S4-F2 / 治理计划 §3 第 12 项要求显式命名 Submit poll/session 预算，并清理没有生产调用方的累计预算函数；AGENTS 要求删除被替代的实现。按生产源码引用和调用链，全部调用点如下。

| 调用点 | 实际模式 / 参数 | 是否形成累计耗时生产 consumer |
| --- | --- | --- |
| `application/submit_jobs.py:852`，await poll timeout | `RECOVERY_SESSIONS_ONLY`，elapsed=`None` | 否 |
| `operations/recovery.py:709`，`finalize_handler_recovery` | `RECOVERY_SESSIONS_ONLY`，elapsed=`None` | 否 |
| `operations/recovery.py:485,510,530,557`，函数内部递归 | 原样传递 caller 的 mode；其中 530 位于累计分支内 | 不产生新的入口；530 从现有生产入口不可达 |

没有生产入口使用默认值或显式选择 `CUMULATIVE_ELAPSED_TIME`。`reconcile_budget_exhausted` 只由上述累计分支调用；其余引用是导出和测试。三个 Application 层 helper 已删除，Submit checkpoint 时间字段已删除，但 Operations 层的累计分支、helper 及仅证明该分支的测试仍保留。

这不意味着 S5 把其他 operation 从实际累计预算切换成了 session 预算：在区间起点，通用恢复路径已在 `operations/recovery.py:685` 传 `reconcile_elapsed_seconds=0.0`；S5 将其改成显式 session-only，保留了原有有效行为。S4 的 Submit caller 同样传 0.0。函数签名中仍有默认值，不能证明“其他 R5 caller 继续使用默认累计耗时检查”；handoff 和两份新增设计文字把未被使用的机制写成了运行事实。

- 影响：收口遗留无 consumer 分支及误导性设计，后续维护者可能错误依赖一个生产路径从未执行的累计上限。当前证据没有显示其他 operation 的实际恢复行为回归。
- 最小修正：按当前生产调用面删除无 consumer 的累计分支/helper 和专属证明代码，简化预算接口；保留 Submit 60 秒 poll 与三次 claimed session 行为。同步修正 R5、5B 和 handoff；不要为保留旧分支新增假想 caller。
- 关闭标准：生产调用方清单与文档一致；无生产 consumer 的累计机制清理完成；现有恢复语义、Submit session 1/2 重试和 session 3 人工恢复、Repository 已终态成功路径的 focused 回归通过。若 owner 决定保留累计能力，须先明确实际 consumer 与 owning 理由，不能用测试调用替代。

### S5-F2：DC32 成本汇总重复计算，阶段覆盖和两个时间指标尚未按定义交付

- 类型：已证实测量缺陷；阻塞：是（必交物准确性，不是性能阈值失败）。
- 位置：`vnext/backend/benchmarks/s5_dc32_capability_measurement.py:314,640,690,720,752`；`benchmarks/real_dump_journey.py:1484,1644,1871,2473,2503`；handoff §8/§10/§11。
- 依据：DC32 第一、二、四部分；Performance Measurement Guidance §1–§4/§8 要求真实路径、准确边界和明确不可比项。

**Submit 的四段并不独立。** 测量同时包装了 `build_import_mutation_snapshots`、`plan_storage_mutation`、`render_change_set_replay` 和 `render_import_mutation_dml`，赋予相同 stage 名，再直接求和。生产 `capabilities/mutation_planning/import_replay.py:123,130` 明确在最后一个函数内部调用 planning 和 replay renderer。外层耗时已包含两者；`build_and_readback_wall_seconds` 又是整个 adapter build/publish/readback 的外层计时，并非可另加的一段 package 开销。

| t4 Submit | 原记录四段 wall 秒（执行完成顺序） | 去除父子重复后的 snapshot + DML 父段 wall / thread CPU | adapter build/readback 外层 wall |
| --- | --- | --- | --- |
| v1 | 69.052371 + 228.623462 + 7.117419 + 235.775946 = 540.569198 | 304.828317 / 304.650772 | 371.923292 |
| v2 | 64.654044 + 227.583001 + 6.972622 + 234.590703 = 533.800370 | 299.244747 / 299.112571 | 367.528370 |

上表中间列只是两段不重叠的已测子工作，并非完整 prepare。冻结 artifact 转 keyed rows 另测得 v1/v2 共 30.308073/33.640184 秒，其他 adapter 工作也在外层计时中。现有 raw samples 足以证明重复计算，不需要重跑长链路才能确认。

真实 V 的 t4 v1 Submit 为 operation terminal 565.761 秒、worker cgroup CPU 479.216 秒，RS import 79 秒；v2 为 573.831 / 477.801 / 83 秒。把 540 秒称为生产 prepare 的独立成本，再加 372 秒 package 或 79 秒 RS，会得到错误结论。扣除重复后不再存在该算术矛盾，但仍不能把不同运行的组件和容器测量强行相加来解释差额：

- capability benchmark 使用同一个生产 `SubmitImportPublicationAdapter.build_and_publish`，没有调用已删除的重新投影路径；生产 handler 经 `publish_prepare_import_package` 进入该 adapter。
- benchmark 使用 `ScratchArtifactStore(InMemoryArtifactStore)`，自行建立冻结输入，在计时外 resolve bindings，以占位 expected parent/base digest 调用，并额外 readback。它没有完整生产 handler 的 parent catalog、durable store、checkpoint/事务、上传、RS effect 和 finalize；thread CPU 也不是整个 worker 的 cgroup CPU。
- 因而 handoff §11 “mutation planning/replay 约 534–541s”的数值结论不成立。Phase 6 候选第 5 条作为进一步拆分成本的调查方向可以保留，不能以这个总和确定成本比例或优化优先级。其余 A 层成功事实及 Preview 的 CPU 成本观察不因此失效。

**必交覆盖也有缺口。** 外层 Submit build/readback 没有 CPU field。14,939 条“逐表阶段记录”不等于每阶段均已实测：pair artifact_write 1,775 条、Submit schema_sql_rendering 624 条和 Submit artifact_write 624 条全部为 `measured=false`、零计时；business materialization 另有 9 条未测。更关键的是 Submit 标为 mutation planning/replay 的逐表数据只包装 `_keyed_rows_from_frozen_artifact`，没有覆盖耗时最大的 planning/render 本体。不能把这些零值解释为零成本，也不能称 §10 为完整的逐表阶段成本分布。可以明确标注不适用或共享成本；实际执行但未测的必需阶段须补齐，或由 owner 明确接受范围调整。

**两个时间指标和历史 C 表混用了边界。** `_poll_operation` 已采到 `operation_terminal_seconds`，但 Preview/Submit/History 的 `completion_seconds` 在后续 GET result/bundle 与核对之后才记录。例如 History 第 2503 行发生在 bundle GET 之后；handoff 把这几毫秒说成 operation 调度收尾不符合代码。DC32 的完成时间是 operation 终态，宜直接使用现有 terminal 指标，把核对完成另行命名。历史对照 §11 声称均为 operation wall，却从 S2b/S3/S4 抄了 journey step wall；例如 S4 v1 Submit 的 578.201 是 step wall，实际 operation 为 576.497；S3 对应为 802.912 与 800.757。该差异虽小，后续基准仍须保持同一口径。

- 最小修正：为父/子计时标明边界，只汇总不重叠 span；补 Submit 外层 CPU 及缺失阶段，逐表数据区分实际计时、共享成本和不适用；以 terminal 字段修正完成时间，统一历史 C 表边界。重写 handoff §8/§10/§11 的数字解释与限制。
- 关闭标准：从 raw samples 可重算且无父子重复；受影响 t4 Submit 组件测量包含 wall/CPU 与真实调用范围；逐表分布不把未测值当成本；两时钟和历史表均符合定义。用现有数据可修正的部分直接修正；缺失数据只做必要的 focused 测量，按 DC30 与最终门禁规则安排取证，不把全量长链路作为调试循环。

### S5-F3：handoff 的 owner 决议来源和最终范围归因需要校正

- 类型：已证实记录错误；阻塞：否，随定向修订修正。
- 位置：handoff §4 第 92–94 行、§6 第 128 行、§8 第 180 行。
- 依据：在 CT108 读取任务指定 main 提交的实际 diff；仅同步 Git 对象用于核查，没有将 main 合入 H。

| 事项 | 实际决议来源 | handoff 问题 |
| --- | --- | --- |
| project_identity 拓扑修复 | `e0054eceec8399dc05d94155a79acf18c2b1dfd4` | §4 写 `72a30b2edb`。后者的树包含此前决定，但其新增内容是最终 runner 失败后修测试 seam 的决定，不是拓扑决定的引入提交。 |
| Submit A/B ruleset 冻结修复 | `d876aea9fb3dcf903d8f94cc2215f8b30698ae7a` | 应明确引用该决定，并补其要求的原偏差引入定位；`git log -S "def _resolve_ruleset"` 可定位该 adapter 路径到 `90e7f90759`。 |
| 后续真实数据范围 | `f84b930d4a` → `398204b4c0` → `0b8c2bac41` | 分别允许 t1–t3 沿用 241ee66、改沿用 a92、继续沿用 a92；最终要求在新 V 完整跑 t4。§8 却将最终全 t1–t4 重跑归为 owner 的选择，未交代这些后续决定。 |

`d876aea9fb` 初次修复授权确曾要求全 t1–t4，但后续决议已收窄；不能把较早决定当作最后一次范围选择。§6 的 t1 调试试跑则由 `398204b4c0` 明确要求。当前 harness 的 `--dc32-output` 在第 3651 行拒绝 `--tier`，可以解释为什么实现实际选择了全档命令，却不是新的 owner 决议。

- 影响：授权和取证历史的归因不准确。V 上额外完成 t1–t3 的证据是真实有效的，不因本记录问题失效；审核未推断存在未记录的新授权。
- 最小修正：补正两项 owner 决议 SHA 和原偏差来源，区分“最后 owner 允许沿用的范围”与“实现实际重跑范围及原因”；如另有后续明确决定，准确引用。
- 关闭标准：§4/§6/§8 与 main 决议时间顺序相符，继续明确 V t1–t3 为本次实跑而非沿用。

## 3. 验收核对

### 3.1 任务要求与 S5 验收

| 项目 | 结果 | 独立核对依据 |
| --- | --- | --- |
| §2 S5 / §3 路径预算 | 部分完成 | 31 个变更路径；生产修改集中在 S4-F2、project_identity import 和冻结 Submit adapter，符合相应 owner 修复授权。测量位于 benchmarks，测试位于 tests；没有为测量提交产品插桩。F1/F2 未关闭。 |
| Submit poll deadline / 3-session bound | 行为成立，清理未完成 | 显式 60 秒 deadline；attempt 1/2 timeout 重试、3 timeout 人工恢复；已终态按结果处理。参数化权威测试在 V runner 中通过。F1 列明全部 caller 与 S5 前的 0.0。 |
| 两组延期、import_rules | 成立 | 设计 §9 仅 canonical_row_hash 三模块和 external_target_sync 三模块；owner 分别为 Backend vNext Architecture / Mutation Planning，理由与重开条件齐全。独立实跑 0/0/6。 |
| §11 文档 11 项 / owner 决议 | 主要实现对齐 | 逐项表见 §3.2；Contract 目录在审核区间无 diff；F3 校正决议记录。 |
| DC32 四部分、t1–t4 范围 | 部分完成 | 18 capability 场景，真实链路 28 条 timing、5 组 baseline read、1 组 History read、2 条 Submit reconciliation；基本吞吐均有结果。阶段归因、逐表缺口与时间口径见 F2。 |
| fresh images / 全量 runner / skip | 成立 | V fresh RS build、backend/worker Compose harness fresh build 与运行镜像断言、client e2e candidate label；5,423 passed、1 个 delegated container unit skip，Compose 0 skipped。见 §4。 |
| 同 V 真实 t1–t4 / S2b–S4 对照 | 正确性成立 | 08:44:28Z–12:57:26Z，起止 V、exit 0；无 stall/人工恢复/assertion failure。各档 facts 见 §3.3；历史时钟可比性修正见 F2。 |
| P5 §2A.5 五项 | 尚不能整体签署完成 | 逐项见 §3.4；容量与字节余量可定位，测量和无 consumer 清理仍待修订。 |
| DC34 V→H carried | 成立 | 原 V runner 同一 CT108 worktree 重算 RS identity 与五包 manifest；全部 compare 为可沿用，changed_components=[]。源 manifest 与 runner 内嵌起始 JSON 完全相同。 |
| 停止条件 / P5 exit / G10 | 未发现新触发；未提前 exit | 设计 §14 七项未见本区间新触发；owner 已处置的历史停顿有记录。当前正确性链路正常，t4 session 余量非零。handoff 仍等待审核；旧 S1 worktree/分支、日志和 retained images 未作 G10 清理。 |
| checkpoint v1→v2 | 成立 | Submit/await writer 与 reader 只使用 v2，精确 schema 检查拒绝其他版本；生产/tests 中两种 v1 schema 字面量均为 0，无兼容分支。详见下文。 |

**Checkpoint / golden / digest。** `submit_jobs.py:166–168`、`1711`、`1978` 固定新 schema；closed key set 不再接收 `reconcile_started_at`，两种内联 canonical checkpoint fixture（`test_submit_job_payload.py:237,257`）同步为 v2，旧字段拒绝用例也同步。checkpoint 序列化把实际 job_state 纳入 canonical bytes（`application/checkpoints.py:123–134`），artifact identity 从这些 bytes 计算（第 584 行），没有沿用 v1 的固定摘要。仓库没有这两种 checkpoint 的独立落盘 golden/digest 常量需要另改；不能把它描述成修改了某个外部 golden 文件。Import schema/DML/package 属于另一组回归：A/B 测试比较旧 A 路径与新冻结路径的 SQL bytes 和 package raw digest，V 全量通过，既有 canonical/manifest golden 未放宽。

### 3.2 设计 §11 的 11 项

未受本区间影响的 owning 语义以现存 public port、对应回归 owner 和 V 全量结果核对，不把 S5 扩大为重做 S0–S4。

| §11 项 | 核对结果与证据 |
| --- | --- |
| 规范快照、schema/状态摘要、单遍物化、标量 | snapshot_materialization public facade 及 canonical identity / repository materialization protocol tests；本区间未改变这些 owner。 |
| 规范投影、manifest、schema 打包、存储词表 | storage_projection API 未改；canonical manifest/package golden 与 projection publication tests 仍通过。新 Submit 以冻结 descriptor 构造 import schema。 |
| import DML | mutation_planning 的 planner/renderer 未改；adapter 继续经其公开入口生成 DML，A 下新旧 bytes/digest 对照通过。 |
| Submit 包组装/发布 | application port + infrastructure adapter；无 runtime ruleset 读取/重新投影；后述 bindings 保留。 |
| ComparisonRuleView 与列处置 | table_rules/comparison public contracts 未变；规则/角色/comparison planning 回归在 V 全量内。 |
| comparison 输入和替换模式 | pair_pipeline、Preview/History 原接线保持；真实 unchanged/v2 facts 与 Compose replacement 覆盖通过。 |
| 规则激活 | 按 DC11、Ruleset Activation §1/§5 修实现；两项 A/B 回归分别证明 application prepare 恢复和 adapter 字节等价。未修改 Contract。 |
| 项目身份 | S4 `3d3ab764ba` 引入的 table_access 依赖由 `ba4ee7a5e6` 修正；facade 改为 snapshot_materialization，allowlist 同步收窄。 |
| Preview/Submit/Archive 身份与持久事实 | 本区间未修改相应事务/CAS/授权模型；完整 Compose 与真实 Submit→approve/archive 结果成立。 |
| History integrity / read inconsistency | 本区间未修改 History owner；相关 unit/integration、Compose 与四档 History 均有通过证据。 |
| 目标 DAG | 无新 import violation/cycle；6 个不可达模块准确对应两组 owning 登记。独立 import_rules 和 V architecture tests 支持。 |

冻结绑定的实际检查链：`_assert_payload_matches_attempt` → `resolve_canonical_snapshot_bindings` 校验 closure raw digest、manifest semantic digest、精确 embedded ref 与表集合 → `open_snapshot_table_artifact` / reader 校验 artifact 内容 → 新 `_build_frozen_projection` 校验 descriptor、raw SHA、table snapshot_digest 与 attempt 的 source binding、schema digest、key/column/row-count facts。非空规范快照的 snapshot digest 与原 manifest 的源摘要具有不同含义，不能强制二者相等；原 manifest 的 source identity 随冻结 manifest 被带入 mutation planner。空集保留 source binding 检查。Package readback/semantic binding、checkpoint 与 build input 的 closure/manifest/expected-parent/removed-tables 绑定，以及实际 import request 的 expected-parent CAS 继续存在。

S5 没有增加跨 scope 输入、路径、权限或事务例外；没有为测量改 Repository DTO/公开 API。DB 探针按后续 owner 决议只读打开并先 backup、精确按 operation/attempt 查询，生产 effect 不由探针驱动。

### 3.3 真实数据与容量

下表由 V 的原始 journey summary、measurement JSON 与 S3/S4 既有证据交叉核对。t2 v2 的 Preview union 为 220 表，提交后 canonical Catalog 为 209 表，不混用这两个计数。

| 档 | canonical 表/行 v1 → v2 | Preview changed v1 / 重传 / v2 | composite v1/v2 | History records |
| --- | --- | --- | --- | ---: |
| t1 | 125/3,733 → 125/3,731 | 125 / 0 / 4 | 4/4 | 12 |
| t2 | 209/73,693 → 209/68,909 | 209 / 0 / 57 | 45/45 | 11,511 |
| t3 | 192/122,452 → 193/122,458 | 192 / 0 / 54 | 201/201 | 744 |
| t4 | 312/246,794 → 312/246,874 | 312 / 0 / 26 | 435/435 | 168 |

每档重传 Submit 为 NO_CANONICAL_CHANGE；v1→v2 为 SAME_PROJECT。t1–t3 canonical state digests 与 S4 实际来源日志相同；t1/t4 与 S3 handoff 中已列出的 digest 相同。S4 t4 是 identity scope，没有相同完整 Submit/History 证据，不把缺项解释为差异。source SQL 规模、包 SHA/bytes 与 handoff §9 对应，审核没有读取或解包真实 dump。

t4 v1/v2 的 RS import 都为 SUCCEEDED，elapsed 79/83 秒、queue 0/0 秒、await session 2/2、上限 3/3、余量 1/1。后台、worker、RS CPU 分开记录；79/83 秒来自 RS control DB 的 completed_at − started_at，并由公开状态核对，不是从不存在的 HTTP 时间字段推测。

容量算术成立：t4 v1 Preview 1684.782 秒 ×2 = 3369.564 秒，距 600 秒目标 2769.564 秒（5.616 倍目标时长）。2× 数据未实跑；该线性推算不能证明尺度关系、并发能力或 Phase 6 SLO。约 640 表指源 SQL 的近似规模；规范表为 312×2，规范行约 493,588。

| 上限 | 2×外推 bytes | 剩余 bytes |
| --- | ---: | ---: |
| replay SQL v1，209,715,200 | 101,132,094 | 108,583,106 |
| replay SQL v2，209,715,200 | 101,145,128 | 108,570,072 |
| Catalog，2,097,152 | 572,274 | 1,524,878 |

旧实现 t4 Preview 没有同环境、同数据和两时钟口径的运行证据；legacy 参考树不等于已恢复的应用/依赖环境。handoff 明确不把旧“约 60 秒返回”作为数值基准，符合 DC32 的条件允许条款，不阻塞 S5。该限制不影响要求当前 vNext 的测量先修正 F2。

### 3.4 P5 §2A.5 五项

| 项 | 结论 | 证据索引 |
| --- | --- | --- |
| 1. 架构泄漏/环/归属及 bytes/digest | 本区间成立 | §3.2；独立 import_rules；V architecture、canonical/manifest、import replay 回归。 |
| 2. Contract 执行边界与实际 consumer | 尚未完整收口 | 冻结 Submit / project_identity 修复成立；R5 无 consumer 分支见 F1。 |
| 3. 依赖、真实链路测量、Phase 6 候选 | 部分完成 | 唯一新增 dev-only blake3==1.0.10；lock canonical PyPI、cp314 wheel、2026-09-29 upload-time 元数据。真实链路成立；测量与候选依据须修 F2。 |
| 4. 语义回归、静态、runner/container | 成立 | §4 的独立检查、V 全量与 fresh/carried 原始证据。 |
| 5. 不可达基线与 owning 处置 | 模块基线成立 | §9 两组共 6 模块有 owner/reason/reopen；模块级 0/0/6 不会检测同一可达模块中的死分支，不能据此关闭 F1。 |

## 4. 实际执行的检查

证据目录均在 CT108，以下简写仅用于本报告：

- E = `/home/dev/gdds-p5-closure-s1-gate-logs/s5/`。
- R = `/home/dev/gdds-p5-closure-s1-gate-logs/s5-independent-review/`。
- D = `/home/dev/gateway-real-dumps/runs/`。

### 4.1 审核方本次运行

| 检查 | 命令 / 对象 | 结果 |
| --- | --- | --- |
| SSH / 固定输入 | BatchMode SSH；在 CT108 git worktree add --detach H；建立 legacy symlink | 成功；检查前后 tracked clean、HEAD=H。 |
| 五包静态 | 各包通过 uv-consume.sh 执行 `run --offline ruff check .` 与 `run --offline mypy` | 全通过；mypy source files 34 / 15 / 26 / 484 / 200。R/static-import-rules.log，13:58:16Z–13:59:07Z，exit 0。 |
| import_rules | backend `uv-consume.sh -C . run --offline python -m tests.support.import_rules` | 0 import / 0 cycle / 6 unreachable；同上日志。 |
| V→H 复算 | 原 `/home/dev/gdds-p5-s5` worktree，V runner 的 s5-env.sh 完整环境；RS identity + label；五包 manifest / compare | 13:59:49Z–13:59:57Z，起止 H、exit 0；R/carried-H.log、R/recomputed-H-*-current.json。没有在新审核 worktree 计算 carried。 |
| 来源真实性 | 逐包解析 V runner 内嵌 JSON，与 E/s5-b79844ddc2-manifest-*-start.json 比较 | 五包完整对象相同；R/evidence-audit.txt。 |
| 差异 / 调用链 / 权威记录 | git diff/log/show/grep；原日志与 metrics JSON 只读归纳；读取指定 main 决议对象 | F1–F3 与 §3/§4 证据；没有修改实现、测试或 handoff。 |

静态检查使用受控 locked/offline wrapper，未跳过五锁检查，未改锁文件。TMPDIR 使用指定磁盘目录；GATEWAY_TEST_BASETEMP 未设置。未运行新的 pytest、全量 runner、Compose 旅程或真实数据；这些结果来自对 V 原始证据的核查，不冒充审核方重跑。

### 4.2 V 权威 runner 和 provenance

V runner 日志 E/s5-b79844ddc2-full-runner.log：2026-10-22 08:03:04Z–08:41:07Z，起止 HEAD 都为 V，起始 clean，runner_exit_code=0，全部五包实际执行，workers=48，未设包筛选。runner 自身在起止比较五锁；wrapper 的 skip flag 是 runner 的正常内层设置，并不关闭 runner 外层五锁检查。E/s5-preflight-b79844ddc2-final.log 与 E/s5-b79844ddc2-postflight.log 记录 clean、无 Dolt/Compose 残留、8000 空闲；真实数据前另有 E/s5-b79844ddc2-realdata-preflight.log。

| 包 / 批次 | S4 合格来源 | S5 V |
| --- | --- | --- |
| shared_kernel | 242（S4 V 从 938d 沿用） | 242 |
| repository_contracts | 152（同上） | 152 |
| repository_client | 154（同上） | 154 |
| backend parallel / serial | 2901 / 36，S4 V ed70ca1be2 | 2907 / 39 |
| repository_service parallel / serial | 1724 + 1 skipped / 205，S4 V | 1724 + 1 skipped / 205 |

唯一 skip 的 nodeid/reason 由 E/s5-v241ee66-repository-service-unit-rs.log 和未变化的源码核对：`tests/test_p2_r1_target_cgroup_smoke.py:11`，仅 delegated target container 运行。不是跳过 Compose；V backend 全批次无 skip，RS 的这一个 skip 与该记录一致。失败的 a2cfe03c21、abb7968bbe runner 没有被用作通过来源。

镜像核对：

- RS fresh build：E/s5-b79844ddc2-fresh-rs-build-verify.log，08:02:51Z–08:02:58Z、exit 0；image ID 从 d4da542a… 变为 `sha256:5092011e2761964071228179d698d215d441c2ef684c90e3a66666f5c8193495`。candidate label=V；build-input revision=`ed70ca1be262653bb49267940e73e7edd09a2267`；source-tree=`sha256:a3e56c4d90e67ba80b632599ead9dca8fc65d13d2193ad0f42472d9a9f68be3a`。RS production inputs 未变，build-input revision 早于 V 与 fresh 重建不矛盾。
- backend/worker：V harness `build_compose_stack_images` 执行 build，`assert_running_backend_worker_images_match_build` 校验实际容器。runner 留下的外部 provenance 实际位于 TMPDIR/gateway-compose-gate-provenance.json（08:20:57Z，属于 V runner 时间窗）；本次复制到 R/V-runner-last-compose-provenance.json。其 ordered-bisect-b 栈 backend/worker IDs 为 `sha256:209650a791ed611f0a3bdeb8d484a9cbe2ac6349b4049c964c2b789a63a8d7d3` / `sha256:c1447c345981193cb9530d8fa13fe35ca6f739949029c0a122e9bc570cd42149`，RS 为上述 fresh image，均与 V postflight inventory 对上。此文件只保留最后一次 capture，不能声称覆盖每个旅程的全部容器。
- client e2e：postflight 的 `gateway-repository-client-e2e:local` 为 `sha256:954c9c5a48ad49b1f78733b528604b324fc9fef0b5ac2ec62434516eb8ef6b35`；本次独立 inspect 的 revision label=V，构建时间 08:31:44Z，在 runner 内。-base:local 仍为 `sha256:ba6c64db44f5f5b7f573fb1df6295c11a5c9e20d9c188189921e717a623ff38c`，符合 G10 对 runner 自动候选重建的例外。

### 4.3 H carried 的独立结果

复算使用原 runner worktree `/home/dev/gdds-p5-s5`，当时已经检出 H，未 checkout、sync、改权限或重建镜像。PATH、HOME=/root、LC_ALL、TMPDIR、CARGO_LCHAIN/UV_CACHE_DIR 未设置、workers=48、包筛选未设置与来源一致；完整 manifest 再次相等。RS identity 的两项值也再次与现有镜像 label 相同。

| 包 | V / 本次 H 相同的 total_digest | compare |
| --- | --- | --- |
| shared_kernel | c50ed6636ebed5dc3c67c2c788a556e60bae3981d4213d5f96bf620f6f2b8ff9 | 可沿用 |
| repository_contracts | cf02462ed6d4e953501e9a97e2b7f9f7c0fa8275f8a1d8b16abe540cd26b4517 | 可沿用 |
| repository_client | a9a541548bb64db8e0cf1067c72c18a08600eab0ca4cd5046f5b1227cde46d92 | 可沿用 |
| backend | ab337285f850b0e6318eb54785833795bb8ffeda9be65fbc86dfa7968e4095f0 | 可沿用 |
| repository_service | acbe7c9b712fef2aef1b2386e40f48bc6f77073021b02106eaf0cb2141c62509 | 可沿用 |

每包 changed_components=[]，直接来源均为 V 实跑，不引用中间 handoff 的沿用结果作来源。由此满足 DC34 对 backend/worker 的条件；没有用另一 worktree 的本地模式或 image ID 再构建结果替代。

本轮镜像记录：Current HEAD=H；Container rebuild required=no（审核仅读、V..H 只有 handoff）；Last verified candidate revision=V；RS build-input/source-tree 见上；Container gate for H=carried from V。此结论不替代 S5 整体验收，也不是发布/最终 production gate 的免重建许可。

### 4.4 真实数据与测量索引

- E/s5-b79844ddc2-realdata-dc32-full.log：V，08:44:28Z–12:57:26Z，exit 0；D/s5-dc32-realdata-b79844ddc2.json：PASS、36 条 measurement。日志及 JSON 为 0600，runs 为 0700。
- E/s5-dc32-capability-v1.log 与 D/s5-dc32-capability-v1.json：a2cfe03c21，18 场景、14,939 条逐表记录，exit 0；只是诊断测量，不是包门禁来源。
- a2cfe03c21..V 仅改 real_dump_journey.py、其测试与 test_submit_recovery.py；capability runner 不调用被改的 journey 探针，符合后续 owner 的沿用范围。沿用许可不消除 F2 的测量错误。
- S4 原始来源：日志根的 s4-v-runner-ed70ca1be2.log、s4-realdata-t1-full-ed70ca1be2.log、s4-realdata-t2-938d41d171.log、s4-realdata-t3-938d41d171.log、s4-realdata-t4-identity-ed70ca1be2.log；S2b/S3 handoff 的 C 表与事实用于历史对照。未重新审核这些历史实现。
- R/evidence-audit.txt 保存本次安全摘要核对及 span 计算；仅含数字、计数、dataset ID、digest，不复制真实行数据或精确 Repository operation ID 到 Git。

## 5. 验证限制与剩余前置

本次独立审核没有重跑全量 runner 或真实数据，也没有改动源证据。clean 起止记录、pre/postflight、harness 校验和原日志互相支持 V 的有效性；它们不等于对运行期间每一次系统调用的重新证明，按现有比例化规则已足够。

S5-F1、S5-F2 修订及相应 focused 验证完成后形成复审候选，按实际改动与 DC30–DC34 / S5 最终门禁规则准备证据。F3 随修订校正。不要把当前 corrected 子段算术视为已经补齐缺失 CPU、逐表成本或整条生产路径归因。

保留的两组不可达模块按 §9 的 owner/重开条件处理。性能优化和容量目标继续属于 Phase 6；本报告不要求在 P5 优化算法。S5 审核通过后下一步仍由 owner 决定；P5 exit、G10 清理另行安排。本次仅提交独立报告到 p5-s5，不推送、不打 tag。


## 6. 复审（2026-10-23）

- 结论：**通过**。
- 审核对象：`p5-s5` 的最终 H `fc2b63c521fb13f743c3b3b9f33d8f23223c4c0e`；门禁 V / 实现 HEAD `55a8b810249649b403339d406cd2b5744feb7863`；backend 的最终直接运行来源为 H1 `1dd049742c1a04636a0e5ea8171a2ac63411d8fb`。
- 重点区间：`ac679c3961..H`，逐项审核 `7ff34be684`、`55a8b81024`、`1dd049742c`、`fc2b63c521`；整体判断仍限于 `p5-s4-exit..H`。初审正文原样保留；其“定向修订”结论对应旧 H，本节结论对应新 H。
- 依据沿用初审列出的权威文档，并在 CT108 通过 `git -C /home/dev/gateway-data-management-system show <sha>` 阅读 main 的 `b5d2961d33`、`3159e4e083`、`1f271ad8a1` 实际 diff。仅传输 Git 对象，没有合并 main。
- 审核位置：CT108 detached worktree `/home/dev/gdds-p5-s5-independent-review`，固定 H，补齐 legacy symlink；检查期间 tracked 内容只读。本次未参与修订实现，未运行全量 runner、Compose 或真实数据。
- 以下 E、D 沿用 §4 定义；新增 R2 = `/home/dev/gdds-p5-closure-s1-gate-logs/s5-independent-rereview/`，所有取证文件均在 CT108、worktree 外。

### 6.1 结论与原 finding 关闭情况

F1、F2、F3 均已关闭。修订没有引入新的生产行为、Contract、依赖或部署边界变化；S5 的实现、全量门禁、真实数据沿用及最终 carried 可以接受。没有剩余阻塞项；另有一项非阻塞的日志字段缺失，详见 §6.2，不能把它写成“所有指定主日志均已记录 umask”。

| 原 finding | 关闭情况 | 核对依据 |
| --- | --- | --- |
| S5-F1：无 consumer 的累计预算及错误设计文字 | 已关闭 | 两个生产 caller 和内部递归不再传 elapsed/mode；枚举、累计分支、helper、导出及专属测试/fixture 一并删除。R5 §6、5B §13.1 与代码一致，授权为 main b5d2961d33。五个指定符号在 H 的 src/tests 中 rg 均 0 命中。 |
| S5-F2：重复计时、覆盖与时间口径 | 已关闭 | 新 V 整套 18 场景重测；Submit 父子/outer 边界、包级共享成本与外层 CPU 均明确，数值可从新 JSON 复算。完成时间采用已有 operation_terminal_seconds，核对完成单列；历史 C 表统一 operation wall。包级 planning/render 的逐表限制符合 b5d2961d33 的明确取舍。 |
| S5-F3：owner 决议及真实数据范围归因 | 已关闭 | handoff §4 正确引用 e0054eceec、d876aea9fb 和偏差引入 90e7f90759；§6/§8 区分最后允许沿用的范围与 b79844ddc2 实际全量重跑及 CLI 原因。新 V 的真实数据沿用单独引用 b5d2961d33，未混淆两轮决定。 |

通过的是本节固定 H 的 S5 独立复审，不是 P5 exit 或发布授权。后续仍交 owner 决定；本次不推送、不打 tag，不执行 G10 cleanup。

### 6.2 非阻塞记录缺陷：DC32 r2 主日志漏记 umask

- 类型：已证实记录缺陷；阻塞：否。
- 位置：E/`s5-dc32-capability-55a8b81024-r2.log:1–13`；外部启动脚本 E/`s5-run-command.sh`。
- 依据：main `3159e4e083` 要求在 umask 022 下启动并在日志头部记录；本次任务追加第 11 项明确要求核对。该主日志第 12 行直接执行 uv wrapper，第 13 行已经是第一个 measurement checkpoint，全文没有 umask 字段；通用启动脚本也没有记录它。
- 已有旁证：E/`s5-dc32-preflight-55a8b81024-r2.log:1–4` 在 23:08:49Z 记录 `umask=0022`、clean V；主运行 23:08:54Z 开始。运行 exit 0、输出 JSON 和日志实际为 0600，runs 为 0700。V r2 runner、H1 backend r2、最终 carried 的主日志均实际包含 `umask=0022`。
- 影响与判定：追加第 11 项的“主日志头部全部记录”没有完全满足；preflight 不能冒充测量进程自身的记录。本次无法仅从 DC32 主日志独立确认该进程的 umask。该缺行不证明实际使用了 077，也不推翻已复算的测量结果；DC32 是直接 capability/本机 Dolt 诊断，没有发生此前容器降权读取 secret 的失败，私密输出权限另有显式设置与检查。结合紧邻的同 V preflight，按指南 §6 和比例化政策将其列为非阻塞记录缺陷，不因缺一个字段要求重跑整套长测量。
- 最小修正与关闭标准：后续启动记录显式打印实际 umask；如有当时保存的启动记录，单独关联到本次运行。保留原日志，不能事后添加一行并当作当时证据。本报告已如实登记当前证据限制；不以“当前 shell 是 022”反推历史进程。

### 6.3 生产差异、回归与真实数据沿用

逐行阅读 `git diff b79844ddc2..55a8b81024 -- vnext/backend/src`，生产改动仅两个文件：

1. `operations/recovery.py`：删除 `ReconcileBudgetMode`、`reconcile_budget_exhausted`、累计分支及 elapsed/mode 参数、内部递归实参和导出；给 60 秒常量补单次 poll 注释。原 session-count 分支、取消/失败/终态转换、退避与 occupancy 逻辑没有改动。
2. `application/submit_jobs.py`：删除枚举导入、poll timeout caller 的两个实参，调整注释；poll deadline 和三个 claimed session 的控制没有改动。

H 中非递归生产调用仍只有 `operations/recovery.py:659` 与 `application/submit_jobs.py:850`，内部递归为 recovery.py:463/486/509。原 V 的两个入口已显式 session-only；S5 之前通用恢复曾传 0.0 的事实见初审 F1，不能把本次删除解释为停用了一个原先有效的累计限制。实际真实旅程不受影响，满足 b5d2961d33 对沿用 b79844ddc2 的条件。

`55a8b81024` 的整个提交仅从 `test_operation_effect_reconcile.py` 删除 `load_checkpoint_envelope` 导入和未使用的 `envelope = ...` 赋值。修订区间共 12 个路径；b79844ddc2..V 共 13 个路径，多出的为初审报告。V..H 只改 handoff。没有测量生产插桩、锁/生产依赖变化或 Contract 文本变化，符合 §3 路径预算和 owner 授权。

复核回归 owner：`test_reconcile_pending_uses_three_recovery_sessions`、Submit 的 bounded poll/session 参数化用例、Repository 已终态成功、通用状态转换矩阵、未知结果/取消后继续 reconcile 等仍在。删除的是累计分支专属断言及其合成时间状态；V focused 430 passed，backend unit 2,757 passed / 178 deselected，随后全量门禁覆盖。Submit/await checkpoint 仍只读写 v2，两种 v1 schema 字面量在 src/tests 中均 0；内联 canonical fixture、旧字段拒绝及实际 bytes digest 路径未被本轮放宽。

真实数据来源仍为 b79844ddc2 的 t1–t4：原日志起止该提交、exit 0；JSON PASS / 36 measurements，其中 operation timing 28、baseline read 5、History read 1、Submit reconciliation 2。复核 handoff 的 28 组时间与原 JSON 一致；重复 Submit 无新 operation terminal，以“—”表示。t4 两次 Submit terminal 565.761 / 573.831 秒、worker CPU 479.216 / 477.801 秒、RS import 79 / 83 秒、session 2/3、余量各 1，沿用事实不变。

### 6.4 DC32 新数据复算与范围

新 JSON D/`s5-dc32-capability-55a8b81024.json` 的 head=V、schema=v2、status=PASS；运行日志从 0 场景连续 checkpoint 到 18，不是拼接旧 v1。场景构成为 materialize/project 9、Preview pair 6、Submit prepare 2、History 1，覆盖所需 t1–t4 范围。

逐表计数独立复算为：

- v1：14,939；v2：17,435；差 2,496。
- 两个 Submit 场景各 312 张表，共 624 张表次；每张表从 3 条 stage 变成 7 条，故增加 `624 × (7 − 3) = 2,496`。原 mutation 合并行改为 frozen row read、snapshot build、plan、replay、DML parent 五行，另保留 schema/artifact 两行。
- 实测 11,907、共享成本 5,519、不适用 9；所有 shared/not-applicable 的 wall/CPU 为 null。handoff §10 的 stage 汇总、20 行 role/row 分布和最慢三表均与 JSON 重算一致。
- 9 条 not-applicable 均为派生 `composite_signal_point` 的 SQL 逐表 materialization 探针未执行；其派生工作由 `compose.py::materialize_business_snapshot` 的包级计时覆盖。此标签不表示 composite 无业务工作或零成本。pair artifact、Submit schema/artifact 的包级成本有实际 wall/CPU。

| t4 Submit | v1 wall / thread CPU 秒 | v2 wall / thread CPU 秒 |
| --- | ---: | ---: |
| frozen artifact row read，逐表求和 | 30.236716 / 30.200350 | 33.676161 / 33.630934 |
| snapshot build | 69.060765 / 69.022034 | 65.166574 / 65.102553 |
| plan child | 230.808288 / 230.776276 | 228.957770 / 228.936570 |
| replay child | 7.140672 / 7.139179 | 6.922427 / 6.921293 |
| DML parent inclusive | 237.983897 / 237.950377 | 235.915228 / 235.892878 |
| DML parent exclusive = parent − children | 0.034937 / 0.034922 | 0.035031 / 0.035015 |
| 非重叠 subtotal = row read + snapshot + DML parent | 337.281378 / 337.172761 | 334.757963 / 334.626365 |
| adapter outer build/publish/readback | 373.979684 / 373.753891 | 369.455820 / 369.208861 |

表中 subtotal 等价于 row read + snapshot + plan + replay + parent-exclusive；没有父子重复。schema SQL 与 artifact write 不计入 mutation subtotal，已包含于 outer。handoff §8/§10/§11 数字一致；旧的 534–541 秒归因已撤除。

生产 adapter 的 frozen row read、snapshot build、schema render、DML 为顺序调用，DML 内含 plan/replay；计时边界与这条调用链一致。benchmark 仍是内存 store 的直接 adapter 路径，计时外 resolve bindings，额外 readback，不能代表完整生产 prepare、持久化/事务和 RS import，thread CPU 不能等同 worker cgroup CPU。修订后的 B 层和 Phase 6 候选第 5 条按分开的边界调查，不再把组件与真实 operation 强行相加，结论成立。

时间口径已校正：handoff §9 把原 `completion_seconds` 标成结果读取/核对完成，operation 完成取 terminal；§11 的 S3、S4 数字与各自 handoff 的 operation 字段一致，S2b 只有 step wall 因而留空并说明来源限制。旧实现 t4 对照限制、2×t4 未实跑的外推限制和 replay SQL/Catalog 字节余量均保留，没有以估算冒充验收实测。

### 6.5 失败、重跑与通过来源

以下时间均为 UTC。失败日志仅作诊断；没有被列为包或容器门禁的通过来源。

| 运行 | 原始日志与核对结果 | 证据用途 |
| --- | --- | --- |
| 7ff34be684 focused/静态 | E/s5-focused-7ff34be684.log：focused 与 unit 先通过，backend ruff 第 243 行 F841；末尾 FOCUSED_CHECK_EXIT_CODE=1，起止 7ff34be684 | 失败记录；V 上从头重跑静态、focused 和 unit 后通过 |
| V 全量 r1 | E/s5-full-runner-55a8b81024.log：21:52:25Z 开始；backend serial 2 failed / 2 passed 后中断；runner_exit_code=143，end_head=V | 不沿用。主日志没有 umask；077/secret 降权故障是 owner 3159e4e083 记录的调查结论，日志直接证明 readiness 失败及 RS exit 3 |
| r1 清理 | E/s5-cleanup-55a8b81024.log：仅两个指定 Compose project，3 容器、2 网络、4 卷；清理后无匹配项，images_touched=no；r2 preflight 清洁 | 没有把这次残留清理混作 G10 cleanup |
| V 全量 r2 | E/s5-full-runner-55a8b81024-r2.log：22:04:07Z–22:42:17Z，umask=0022，起止 V、clean，exit 0，五包实际运行 | V 唯一全量通过来源 |
| DC32 错参数 | E/s5-dc32-capability-55a8b81024.log：22:42:49Z–22:42:50Z，exit 1，索引 datasets.json 不存在 | 未启动场景；r2 preflight 记录 failed_output=absent、scratch_candidates 为空。源码在建 scratch/checkpoint 之前读取索引，与记录一致 |
| DC32 成功重测 | E/s5-dc32-capability-55a8b81024-r2.log：23:08:54Z–次日 00:31:58Z，起止 V、clean、exit 0；18 场景 / 17,435 行 | 新 capability 唯一来源；umask 字段缺失单列 §6.2 |
| H1 初次 carried | E/s5-carried-H1-1dd049742c-r3.log：四包可沿用；backend 因 non-git:pytest-cache 返回“运行” | compare 命令 exit 0 不是“所有包通过”。handoff 没有把该 backend 结果当作 carried |
| H1 backend 首次 | E/s5-backend-runner-1dd049742c.log：01:10:57Z–01:38:30Z，起止 H1、umask=0022、exit 0；2896 + 39 passed | 合格实跑；最终选择下一行 r2 为直接来源 |
| H1 backend r2 | E/s5-backend-runner-1dd049742c-r2.log：01:41:06Z–02:08:20Z，起止 H1、umask=0022、exit 0；2896 + 39 passed | 最终 backend 与其 Compose 门禁直接来源；此前五包静态已全部通过 |

V 五包计数为 242、152、154、backend 2896+39、RS 1724+205 和 1 skipped，合计 **5,412 passed / 1 skipped**。相对初审 V backend parallel 少 11，符合专属累计证明删除及测量用例调整；相对 S4 为 parallel −5、serial +3。其余包不变。唯一 skip 仍是 delegated target container 的 cgroup smoke，RS 源码未变；Compose journeys 0 skipped。

V r2 的 backend 起始 total_digest 为 b1669d67…，H1 两次 backend 起始完整 manifest 完全相同，均为 828a304a…，不是只比较前缀。独立比较 V r2 → 当前 H 仍只差 pytest-cache（0d73e66e… → 6dced36c…）；没有手工清空缓存以制造沿用。按 main 1f271ad8a1 改用 H1 实跑，处置正确。

### 6.6 Fresh 镜像、provenance 与最终 carried

- RS：E/s5-build-rs-55a8b81024.log 起止 V、build/独立 label 校验 exit 0；fresh image `sha256:a1d2e14c8574ea10557c3d16a6643d17ae4c6dd440499379442edfab052f3fec`，candidate revision=V。build-input revision 仍为 `ed70ca1be262653bb49267940e73e7edd09a2267`，source-tree 仍为 `sha256:a3e56c4d90e67ba80b632599ead9dca8fc65d13d2193ad0f42472d9a9f68be3a`；这是未变的 RS build 输入身份，不是沿用旧 image ID。
- backend/worker：H1 backend r2 执行原 fresh-build/运行镜像一致性 harness。TMPDIR 的最后一次 provenance 修改时间 01:58:51Z 落在该 runner 内，backend 为 `sha256:730e02af87d859b1ec112ae22f8254e8f287839d08c66d4471e31dc6dd58cb17`、worker 为 `sha256:7ee87691c042086b3fcd5a9ca7bac184da0f4b5f5a565ea461bc9d8198212eae`，RS 为上述 fresh image；只代表最后一次 capture，副本在 R2/H1-last-compose-provenance.json。handoff 的“未重建镜像”应结合上下文理解为未手工重建所沿用的 RS/client，不能解释成 backend harness 没有 build。
- client e2e：V r2 postflight 与本次 inspect 一致，`sha256:8c01290166c5a95d2e386cfe3dddd994fca25da0f519917e261a62615c140e91`，revision=V，创建于 22:32:52Z；base 仍为 ba6c64db…，没有手工删 tag 的证据。
- 最终作者 carried：E/s5-carried-H-final-after-backend-run.log，02:09:27Z–02:09:35Z，起止 H、clean、umask=0022、exit 0，RS 两 label 相同，五包 changed_components=[]。
- 本次独立复算：在**原 V/H1 runner 的同一** CT108 `/home/dev/gdds-p5-s5` worktree，以 s5-env.sh 完整环境和 umask 022 重算；只把输出写到 R2，没有 checkout、sync、改权限、清 cache 或重建镜像。03:06:45Z–03:06:52Z，起止 H、exit 0，结果再次相同。

| 包 | 直接实跑来源 | 来源起始 / 当前 H 相同 total_digest | 本次 compare |
| --- | --- | --- | --- |
| shared_kernel | V r2 | c50ed6636ebed5dc3c67c2c788a556e60bae3981d4213d5f96bf620f6f2b8ff9 | 可沿用 |
| repository_contracts | V r2 | cf02462ed6d4e953501e9a97e2b7f9f7c0fa8275f8a1d8b16abe540cd26b4517 | 可沿用 |
| repository_client | V r2 | a9a541548bb64db8e0cf1067c72c18a08600eab0ca4cd5046f5b1227cde46d92 | 可沿用 |
| backend | H1 backend r2 | 828a304a68e201a65fd878f1f87c73de345184553d87805463d2defd603e16a7 | 可沿用 |
| repository_service | V r2 | d498559964fdb430d3b09000f33a544057c28dd69ed6ca7615426b57a4a4cf6e | 可沿用 |

逐包抽取原 runner 内嵌 manifest，与 handoff 指定来源 JSON 比较完整对象，全部相等；没有引用中间 carried 结果作为来源。H1..H 仅 handoff，满足 DC34 backend/worker 沿用规则。审核本轮 Current HEAD=H；rebuild required=no（只读复审）；最后直接验证来源为 RS/client 的 V 与 backend/worker 的 H1；最终 H container gate=carried。发布/最终 production gate 仍按其独立规则处理。

### 6.7 验收总表与本次检查

| 验收项 | 复审结果 |
| --- | --- |
| §2 S5 / §3 路径预算、fresh、全量 runner | 成立；owner 修订范围、V 全五包及 H1 backend 来源均闭合 |
| 两组延期与 import_rules | 仍仅 canonical_row_hash / external_target_sync 两组，owner/reason/reopen 未改；本次实跑 0/0/6 |
| §11 的 11 项、冻结 A/B、golden、bindings、Contract | 初审已核对且本轮未触碰相关实现；全量回归继续通过；Contract 目录整阶段无 diff |
| DC32 四部分、逐表分布、两时钟及 t1–t4 | 数据与校正成立；包级分摊、直接 adapter 与完整 journey 的差异有明确限制；日志字段例外见 §6.2 |
| 真实数据与容量/Phase 6 候选 | b79844ddc2 沿用条件逐行满足；composite/History/Preview facts 与 session 余量不变；容量估算仍不冒充 2×实跑 |
| P5 §2A.5 五项 | 架构/摘要、执行边界/consumer、依赖/测量、回归/门禁、不可达 owning 处置逐项成立；F1/F2 原缺口已关闭 |
| 停止条件与 G10 | 三次停止及 carried 不满足均已交 owner 并按决定恢复；无未处置停止项。G10 第 6、7 项已登记到 main，尚未执行；没有提前宣布 P5 exit |

| 审核方本次实际检查 | 结果 / 证据 |
| --- | --- |
| 五包 ruff/mypy | H detached worktree，受控 wrapper `run --offline ruff check .` / `run --offline mypy`；全部通过，34/15/26/484/200 files；R2/static-import-rules.log，03:05:35Z–03:06:27Z，起止 H、exit 0、umask 0022 |
| import_rules | 同日志；0 import / 0 cycle / 6 unreachable |
| 五个 R5 符号及 checkpoint v1 | 在 CT108 使用随审核传入日志目录的 rg 15.2.0；src/tests 无命中，rg exit 1 是正常 no-match；R2/symbol-search.log |
| identity 与五包 carried | R2/carried-H.log、recomputed-H-*.json；label 一致、五包可沿用；R2/provenance-audit.txt 核对起始对象 |
| 新测量/历史来源/计数与分布 | R2/measurement-audit.txt、distribution-audit.txt；raw JSON 只读重算；未读取真实 dump 行内容 |
| umask 与文件权限 | R2/umask-audit.txt；指定成功日志及 JSON 实际 0600、runs 0700；DC32 主日志字段缺口已单列 |
| 原报告与差异边界 | 写本节前原报告 SHA-256 为 a82b7a764475e614dd44e66940bc63f30a3f3ae46b301bf8cd47cf5e17c05e74；确认与 ac679c3961 完整 bytes 相同，仅追加本节 |

本次没有重新运行实现测试、容器或长链路测量；通过结论基于源码差异、上述独立静态/闭包检查与已有原始执行证据。一次尝试把历史 H1 manifest 作为 current 比较被 HEAD guard 正确拒绝（exit 2）；未改任何证据，改为在原 runner worktree 用实际 H 重算 manifest 比较，确认 V backend 的唯一变化为 pytest-cache，记录在 R2/V-backend-cache-difference.log。

剩余工作归属明确：owner 决定 S5 后续与终审；G10 第 6 项 secret 权限隐患、第 7 项 pytest-cache 沿用问题及其他 exit 清理按 main 决议处理。S5 通过不等于这些事项已完成，也不等于 P5 exit。

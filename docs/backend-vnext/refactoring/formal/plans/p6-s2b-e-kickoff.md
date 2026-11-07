# S2b E：唯一生产路径与阶段最终候选

当前状态（2026-11-07）：`1de3fa4084` 的 04 backend 权威与 05 fresh t1 均完整通过；t2/t3 未跑，最终门禁暂缓至资源配置确定。隔离宽裕档 `4f808c111b` 完成 v1/v2 后在 History 失败，原结果保留为 FAIL；已确认并修复 FD 生命周期缺陷，main 产品为 `d6c88cafb3`，06 定向证据独审通过。同窄修隔离候选 `1f9df50a5c` 的独立副本 History 已成功并获独审，见下方结果。已观测最大预约约 12.173 GiB，Owner 已选最终 24 GiB 容器/8 GiB reserve/M16 GiB、N1，正在实施并集中验证最终候选；临时配置/观测未进入 main。原三代失败资源及证据保留，成功副本已清理，准确事实见 [handoff](p6-s2b-e-handoff.md) 与 [独立审核](p6-s2b-e-review.md)。E/S2b 尚未退出。

**History 定向诊断接续（Owner，2026-11-07）：** 同镜像 profile 的独立探针测得 soft FD limit 1024，Arrow 小样本证明关闭 source 后可保留 buffer 零拷贝读取；这两项尚不足以确认原 History 根因。真实 C 双侧各 312 表的诊断连续两次在准备阶段失败，按 DC68 暂停后，Owner 明确批准“允许按已审第三稿续做，明确问题修复后定向验证”。第三稿 SHA `4b982cb016eb3ff4903f42e6cdda489cf4e9136751019d26fc7c81523bf8df65` 已独立静态审核，将 factory 放回有效 operation scope 后在 06 运行；保留两次失败，不改写为通过。若证实 FD 生命周期缺陷，最小修复及 focused 独立审核后，使用本任务保留资源的独立冷拷副本、当前修复镜像和现有 `--from-step history` 定向验证，不重跑 Submit/全旅程。原校准 FAIL 与后续局部结果分别记录，最终资源档仍待 Owner 依据补全证据选择；此授权不等于 E GO/S2b exit，不扩大为任意失败循环重试。

**FD 因果与最小修复已核（2026-11-07）：** 第三稿在真实 C/Store/SQLite 双侧各 312 表、soft limit 1024 下复现同 WAL 错误：FD 5→317→629→941→1023，scope 关闭后回 5；是 scope 内映射持有句柄达到上限，并非跨 scope 永久泄漏。修复 `d6c88cafb38255c66dbb5f8fae091af75e289d62` 仅在同一 mapping 校验成功后关闭 source FD，保留原 buffer/预算生命周期与零拷贝；一个 owner 测试验证 96 个同时借用 reader 的 FD 与可读性。06 的四模块 57 项、Ruff/mypy 和同双 312 表正向对照均通过，后者全部 publication 完成、FD 始终 5；源码和原始证据均经独立审核。后续仍需隔离校准候选的真实 History 副本验证及最终资源选择，不将 focused 结果充作 E exit。

**最终配置后的验证边界：** History 局部结果已齐，Owner 已选最终 24/8/M16；临时 64/16/48 不直接成为生产配置。若最终方案修改 `vnext/deploy`，六包 manifest 的共同 deployment 组件均变化，必须在最终产品候选取得六包实际合格来源，不能沿用旧 Rust/三小包的闭包结论；该轮 backend 已覆盖的 Compose 旅程不再另跑。临时校准与 FD 修复只做上述定向验证，不提前重跑六包。既有 A–D 恢复/取消/事务/CAS 等独立证据仍按影响面复用；最终容器绑定、t1–t4 范围和资源边界按本节原验收收齐，不将原失败前缀、局部 History 或性能延期替代最终候选门禁。

**History 局部结果与已选最终配置（2026-11-07）：** 隔离候选 `1f9df50a5c01173b82febc3a74b01bae549b1bb0` 的独立冷拷副本已完成 History，02:09:25Z driver 结束、journey 0、同一新 worker 正常 stop、仅副本清理完成及节点释放，独立审核通过。三个真实 claim/counter 一致，materialize/assemble/publish 预约高水位分别 398,673,952 / 11,218,037,646 / 3,761,894 bytes；History 最大约 10.448 GiB，局部新 worker cgroup peak 263,307,264 bytes、VmHWM 423,704 KiB，无 OOM/失租/重启。原 cal 前缀最大预约 13,070,921,208 bytes（12.173 GiB），cgroup peak 6.519 GiB；两次 worker 峰值分列，不求和或拼为完整校准 PASS。具体 SHA 与副本身份见 handoff/review。

设计推荐与独审意见一致：**最终候选 24 GiB envelope / 8 GiB reserve / 显式 M16 GiB，N1/单 active**；对已观测最大预约留 3.827 GiB（约 31%）余量。备选为 32 GiB envelope / 8 GiB reserve / M24 GiB，增加容量余量。Owner 随后明确选择推荐的 24/8/M16，按 DC87 当前配置直接实施与集中验证，不继续逐档试跑。charged 未覆盖全部 Rust 局部 temporary，因此上述数据与余量支持的是待验证配置，不是严格实耗上界或更大输入承诺；选定后完成最终候选必要门禁及同 worker 完整 t4。W1/W2 和原基准结论仍按既有安排。

前序收敛记录（2026-11-06）：Owner 批准的额外四工具 mypy 修正已在 06 实际通过，并经独立审核；该暂停已关闭。`d0f5602d6f9f352b493bb31fbaf6b0a24dde4c5f` 的 04 Rust 权威来源仍合格。首轮五 Python 权威运行暴露测试夹具迁移漏项；修正 `ff970567f8` 后，06 全 backend 收集 3230 项成功、受影响 184+16 项及 Ruff/mypy 通过，04 backend-only 主体 3173 项通过。但该次串行部分 55 通过/2 失败，整次 runner1，不能形成 backend 来源。两个真实远端操作成功，失败位于 History/ordered 测试核对 helper 的默认仓库 scope 与缺少显式调用参数；独立审核确认是此前未运行到的 adapter 漏迁，不据此降低生产校验或修改业务预期。

修正候选 `7c023971397a8fba2c9e2aa86e9e7cbb9f088fe1` 仅改三个测试路径，已获独立源码核对；06 本地 History 27 项、两个原失败 Compose 场景及 Ruff/mypy 已通过并独立核验。随后同 04 E worktree 的 backend-only 权威 runner 于 23:56:36Z 完整退出 0，主体 3173 项、串行 57 项通过。保存完整来源并独立核对后继续其余四个 Python 包；Rust 在同节点同 worktree 比较原合格来源，实际闭包相同。失败整次中通过的包不抽作合格来源；四包镜像构建结束再核 backend 闭包及最终容器绑定。

2026-11-07 更新：三节点于前日 23:58:30Z 实际启动。05 的 7c fresh t1 全旅程及资源/正常停止/清理均成功，00:03:36Z 释放；t2/t3 未启动。CT108 的 7c fresh t4 于 00:01:07Z 在首次 Preview 的 `assemble_preview` 被 `RESOURCE_LIMIT_EXCEEDED` 拒绝，materialize 已成功。实际输入为 MODIFIED_ONLY（BASELINE/INITIAL 空、MODIFIED 312 表）；旅程 `--scope full` 不等于上传 InputCompleteness.FULL。失败阶段 cgroup peak 为 660467712 B、上限 12884901888 B，N1/M8 正确，OOM/重启为零、正常 stop0；这些事实不能证明完整档容量足够。

保留 checkpoint/元数据的只读核算发现明确预算缺陷：standard 与 ordered 的单侧 ADDED/DELETED 路径仅生成表级事实、不读取 rows，但 `comparison_python_memory_upper` 为其中 278 个任务预扣全量行对象包络。仅行项与基费已至少 13703443328 B（约 12.763 GiB），尚未加非负 Arrow 项，超过 M8。按既有 DC80 小明确修正授权，只去掉单侧未消费 rows 的费用，保留元数据基费、真实双侧及 ordered identity 读行预算；不提高 M/容器上限或更改业务预期。修正候选 `1de3fa408433b344faac222d28736a82405e566a` 已获独立源码核对；06 于 00:18:52–55Z 实际完成 81 项 focused 与 backend Ruff/mypy，退出 0，包含单侧不读行/预算不随行数膨胀的行为，以及既有真正读行预算拒绝 owner。证据复核、最新节点环境绑定完成后，04 backend 权威与 CT108 fresh t4 可在同一候选上跨节点并行，不再人为要求先等 backend 全部完成；05 同候选按有效占用逐档 fresh t1–t3，04 backend 后再 RS。若后续真实读行路径仍无法承载，停止该路径，将事实及配置取舍交 Owner，不静默改 DC87 或调整预算系数。

04 当前四包运行自然收束，合格后 Rust/三小包按同 worktree 实际闭包比较沿用；新 backend 源码/测试要求补 backend，RS 来源 manifest 的 `docker:context:vnext` 也随之变化，须补 RS，不能因业务无关径自沿用。t1 旧成功结果保作回归，其已清理卷无法按 DC64 从受影响首次 Preview 续跑，最终新候选需 fresh t1；t2/t3 尚未跑、t4 尚未完成，均须新候选实际完成。不新建恢复工具或重跑全部六包。t4 本 E 停止容器/卷/network/证据原样保留，只在整机 idle、HEAD clean 和本任务 marker 精确核对后释放占用；后续新项目不得复用失败资源。最终证据未齐，不记 E GO/S2b exit。

启动时前置记录：**D 前置通过，按 DC86 启动 E**（2026-11-06）。D 固定产品 `93678f8439ec1393d496182f16ae5049b220242f`、[handoff](p6-s2b-d-handoff.md) `abfe7cb66b`、[独立 GO](p6-s2b-d-review.md) `78411aa40b` 已收齐，06 已释放、D 二角色结束。本节重新创建 **GPT-6.1-Sol/high 实施者、GPT-6.1-Sol/max 独立审核者**；因涉及旧算法与独立预期移交、累计恢复证据、跨节点最终门禁及闭包判定，审核选择 max。按下述范围先收敛删除与工具消费者，再固定最终候选验证，不把 D focused 结果充作最终权威来源。

## 1. 消费者收口与删除

目标是已批准的唯一 Rust 批量路径 `parse → business validation/materialization → canonical projection/hash → IPC`。Python 保留业务 orchestration、ruleset、XML/AST/composite、small metadata/digest 以及真实 IO/恢复 owner；不为语言统一迁移这些职责，不删除仍有消费者的公共 row reader/DTO。

逐项核整体 kickoff §2 的消费者表，并以实际 import/call graph 补缺：上传 FULL 双侧、Preview baseline、History exact commit、repository-ref 两种 artifact policy、pair/identity/ordered 单侧读取、export/import-replay、Submit/T1/PREPARED 与恢复。D 已切的入口只复核差异，剩余入口在 E 替换；同一消费者不保留生产 fallback、旧格式双读或引擎开关。

删除被替代 Python 批量 materialize/projection/hash 实现及只服务其差分的入口、mock/probe。保留已确认的独立 fixed vectors/Contract：删除旧 oracle 前，将仍需保留的预期明确绑定到既有 Contract/golden/旧 oracle 已验证值，不能从新 Rust actual 反写 expected，也不为了测试长期保留第二套算法。按行为与 owner 保留测试，不按修复轮次复制测试矩阵。

D 的 direct RepositoryRef capability 用例可暂用 test-only committed-tables port 适配已有 reference helper，以隔离 metadata/选表策略。fixture 必须补齐显式合法 identity/scope，生产缺 identity/port 仍拒绝；真实 HTTP/C 恢复另有 owner。E 一并删除这些临时 reference 依赖，将必要预期交给独立固定向量或真实 C port，不保留生产 fallback，也不把旧算法复制成长期 test oracle。D handoff 必须列清临时项。

D 首个生产 parser 接线后，旧 parser 已无生产 consumer；为本节删除前的临时差分移交，D 明确登记六项 `gateway_backend.capabilities.table_access.{sql,_sql_reader,_sql_scan,_sql_statements,_sql_types,_sql_values}` 的 temporary unreachable。E 必须将尚需的独立语义预期固定并核实后，删除这六模块、只服务它们的测试辅助/差分入口与六项 baseline；不能通过假 import、长期重命名 oracle 或最终豁免保留。每项删除前核当前 consumer，S2b 最终架构门禁不接受这六项临时记录。

内部 canonical IPC 与 raw/client Parquet 是不同用途；只删除被替代的内部规范表路径。面向客户端的 Parquet、通用 Repository row 访问、原始 SourcePackage 与外层 DDL/export layout 按其真实消费者保留。

已核到工具消费者 `benchmarks/real_dump_journey.py → real_dump_census.py::compare_composite_packages`：后者目前仍导入旧 parser/materialize/projection，E 删除时须同步迁移实际需要的工具调用，不能只检查 application imports。该 helper 原本就使用 production projection/comparison 计算 composite counts，属于跨层一致性检查，不是独立算法 oracle；可接唯一新生产路径，不能将这种同源结果冒称独立 golden。真正固定向量仍按上面的独立预期规则移交；已有 census/已验证结果优先复用，不为此重新生成全套输入或增加双实现完整旅程。

这些实际 CLI 的初始化按 [Rust policy v6](../policies/rust-safety-and-performance-policy.md#4-core-and-adapter-boundary) 复用薄 `bootstrap.compute_kernel.initialize_compute_kernel(threads)`，将 D 的 private initializer 精确允许边迁到该唯一 owner；worker/CLI 显式启动调用，M/control/operation scope 仍归原调用方。不引入通用配置或未来工具框架，不让工具直接访问 private FFI。

2026-11-06 原基准设计会话核对 DC79、剩余 handoff 和实际入口后确认：旧 scanner 依赖的 `p6_s1b_synthetic_load`、`s5_dc32_capability_measurement`、`s5_v5b_segment_measurement`、`p6_s1a_mutation_replay_measurement` 没有必须在当前 main 执行的消费者。后续必要输入生成仍使用已审 `p6-baseline`/固定 Git 历史（含四路接线 `4007619abd`），优先复用既有输入；旧 V5b/DC63/S1a 测量如需重开也在其冻结源码执行，当前局部诊断固定 `1f9731dfc3`。因此 E 可按真实依赖闭包退役当前 main 上这些旧工具、孤立 helper 和 tool-only tests，以及已核无消费者的 `p3_capability_diagnostics`/`p6_v6_parser_diff`。不得删掉 `real_dump_journey` 及仍有效依赖、独立业务 Contract/golden；不复制旧 parser 为永久工具库，不重做 S1 或新建 S6 框架。原线确认只提供消费者事实，不代替 E 对具体删除和覆盖移交的独立审核；冻结 refs/worktree、输入、镜像、卷、产物和证据全部保留。此范围同步记于 DC79 的后续使用边界。

## 2. 收敛与最终验证

日常在 06 对实际删除/迁移范围做 focused/Contract/差分残余检查、静态与必要容器验证。最终候选前收敛全部代码与测试；按 AGENTS 记录最后已验证 image revision/source tree、是否触发重建及理由。不每轮执行全量 runner、完整真实旅程或重新生成输入。

最终 S2b 候选必须覆盖：

- Mapping/业务摘要/诊断/特殊 catalog 与 FULL、MODIFIED_ONLY、DATASET_REPLACEMENT 正确性；W2 结构计数及内容命中不重写。
- IPC handle、强引用/TTL、Archive CAS、精确 commit 回填、T1/PREPARED 冻结，真实 worker cancel/drain/lease_lost/deadline 与资源拒绝。沿 A–D 已验证 owner 按最终差异核对，不机械重做所有中间测试。
- 04 权威 runner 与最终候选绑定的容器门禁；Rust 必须覆盖，其余包按同节点、同 worktree 的实际来源 V 和闭包规则判运行/沿用。包沿用和镜像身份等价分别判断；普通 06 focused 不能冒充 04 来源。
- t1–t3 在 05、t4 在 CT108 完成改动面内的 Preview/History/Submit 生产路径正确性。CT108 忙时尊重有效占用，空闲后原子取得标志直接使用，不例行申请窗口；若要换节点，先向 Owner 给出具体替代方案并取得授权，不能以性能延期豁免 t4。

各节点分别按有效占用、clean committed worktree、离线缓存和日志规则执行；正式测试不在开发机运行。runner 非零先停并处理失败，不接着计算 carried；最终门禁提交固定后不在运行中修改 worktree、提交或手工 retag 镜像。保留 04 门禁 worktree 至阶段退出合入，以便同节点同 worktree 判等。

本轮来源核对：原合格五 Python 包来源 `3b037adf4c` 至 E `d0f5602d6f`，`test_input_closure.py::COMMON_GIT_COMPONENTS` 中的 `vnext/scripts` 与 `vnext/deploy` 均已变化，分别涉及新增容量脚本和 Compose 资源接线。因此三小 Python 包也必须实际运行；不是仅因成本小或换 worktree 而默认重跑，且 `vnext/fixtures` 本轮并未变化。04 可新建 E 自有 clean worktree，保留 S2a 原 worktree 与证据。额外工具 mypy 续做待 Owner 时，可在具体 driver/缓存前置独立核准后先运行权威 `rust` 包，整次 exit0 才形成实际来源；后续五 Python 包另行实际运行。若其间仅 Python 工具/测试变化，Rust 仍须在同 E 节点/同 worktree 按该实际来源做闭包比较再沿用；任何一轮失败不作来源，也不把两轮结果写成一次六包 runner。

真实数据入口沿当前候选的 `vnext/backend/benchmarks/real_dump_journey.py --tier <t1|t2|t3|t4> --scope full --kernel-threads 1 --kernel-memory-budget-bytes 17179869184`，由受控 uv 入口在相应节点执行；E 工具迁移后两个 kernel 参数显式提供，约束 host-side composite 对照的同一 operation scope，不替代 Compose worker 自己的 DC87 配置及 24 GiB 容器上限。使用既有 `GATEWAY_REAL_DUMP_ROOT` 输入并核绑定，不重生成输入。此处是正确性旅程，不使用原基准冻结 checkpoint/resume、卷或正式计时入口；不以旧整镜像 prebuilt 跳过当前候选的节点本机离线构建。05/CT108 按最新 DC82 现场核闲并原子取得占用标志直接使用，不以跨会话窗口申请为前置；原线 STOP 不代表节点已释放。仅实际冲突或涉及他人资源时针对性协调。

t4 为收齐同一次完整 worker 的资源证据，在上述 fresh full 命令加现有 `--keep-stack --project-name <E 独占新名>`；不传 `--from-step`，不从任何 checkpoint 续跑。外置 driver 全程持本节点占用，在成功或失败的清理前读取本 project worker 的 StartedAt/RestartCount、24/8/M16 GiB 配置、OOM 状态、实际 N/M 和 cgroup `memory.max`/`memory.peak`/`memory.events`，再正常 stop、保留日志及停止后的状态/退出码。只有旅程成功且必需证据完整时才清本任务 project 资源并释放占用；真实 journey 非零、资源异常或必需证据不完整时，保本 E 容器/卷与占用并立即交设计协调，按 DC80 主动诊断、最小修正和独立审核，不丢弃 control DB/artifacts、不自动重跑或 resume。诊断后不再需要节点时，按具体保卷与残留核对方案释放，不无限等候。用 StartedAt/RestartCount 核同一 worker；peak 是该 fresh 容器生命周期的 cgroup 高水位，含 startup/page cache 等，不称单进程 RSS 或 M 硬上限。异常退出后不可读的项、`memory.events` 缺失的必需 `oom`/`oom_kill` 键均记 missing/incomplete，不默认零或补 PASS。只保留证据所需字段，不输出凭据；新 runstate 仅归本 E 证据，不作恢复入口。本安排复用现有 CLI 与平台能力，不新增采样服务、不重复旅程；具体 driver 经独立只读核对后执行。

## 3. 退出记录与后续性能复核

节点协调更新（2026-11-06 19:23:49Z）：原基准设计会话只读确认 CT108 无占用标记、运行容器、8000 监听或相关运行进程；原线正式测量 STOP、无 CT108 恢复 GO，新 GC 诊断仅在 05。E 最终候选与自身验收前置齐备后，可按执行时有效占用原子取得 CT108 运行独立 fresh full t4，不需等基准整体 exit 或原线再次回执。此前“窗口未确认”是协调前状态；本次确认不是立即执行或排他预约，实际前检仍须完成。E 占用期间原线不启动 CT108，E 保留原线全部卷/checkpoint/镜像/证据，不 prune，后续按 2026-11-07 的 DC82 补充不再例行通报占用与释放。05 的 t1–t3 尊重有效占用、空闲即取用；旧旅程耗时不作本候选承诺。

E handoff 将最终产品候选、删除/保留清单、逐包来源与闭包、容器 provenance、t1–t4、容量/N/M 配置、恢复/控制证据、未决问题集中交独立审核。设计会话不能自行判实施证据。S2b 的阶段退出记录与附注 tag 按既有退出流程办理，不推送、不改写被审核引用的提交。

W2 30 秒目标及口径保留，完整路径测量最迟 S6；W1 无 CT108 窗口时同样最迟 S6；W3 从 S3 起按原设计取证。未知数值保持 unknown，功能退出不写性能 PASS。原 W4 租约故障由原线跟踪，若当前功能候选出现租约或正确性故障，仍须处理，不能归入可延期性能项。

CT108 本次资源窗口确认后，优先从同一次最终 t4 fresh 旅程开始 W1 型初步诊断，不再笼统套用“无窗口”。现工具已在 t4 收集 `operation_timing`，E 仅将普通 full 报告原本丢弃的这些字段保留在 JSON；不新增计时点、轮询、HTTP 调用、输入或完整旅程。报告按实际口径区分受理响应后到首次结果可读观测、操作终态、后续读取完成，注明 2 秒轮询和 visibility fallback；这些观测不等于精确 READY 事件时刻，也不与包含请求/读取/断言的整个 step wall time 混用。最终候选实际范围为 t4、N1/M16 GiB、单次正确性运行，不能替代 2×t4、预热与正式重复采样或用于宣称 W1/W2 达标；正式 W1 仍归 S6，W2 按 DC83。若实际运行未完成，诊断也保持未完成。

本节使用上述新建二角色，实施者修改产品/测试，审核者只读固定候选及证据、维护审核文档，明确小问题可直接通信修复后复审。设计/审核可修改各自 owning 文档。额外角色、真实设计冲突或多轮修复不收敛交 Owner；不复用 D 角色，不推送或改写被引用提交。当前进入 E 实施，不代表 E GO 或 S2b exit。

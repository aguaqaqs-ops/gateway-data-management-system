# Preview bundle 重复读取优化设计

日期：2026-11-14。状态：Owner 已批准范围；本文件是新会话实施依据，不表示代码、测试或性能验收已完成。

## 1. 目标与本次授权

在保持 Preview 业务结果、完整性屏障和资源边界的条件下，消除 bundle 同一校验点内紧邻的第二次读取，用五份真实演进数据检验局部工作量及端到端等待是否改善。没有预设提速百分比或秒数门槛。

Owner 已同意上一轮提出的窄优化和初测方案，并要求本轮仅落成设计、实施文档及新会话提示词。**新会话可实施、验证和修复本方案，真实 Preview 总预算 12 次。** 这替代旧调查在本任务范围内的“只读、不实施、新增 Preview 为零”；不改变历史调查的结论和执行事实，也不授权部署、推送、公共 Contract 行为变更、扩产品资源或其他优化方向。

Owner 指定实施者 `gpt-6.1-terra` / `xhigh`、独审者 `gpt-6.1-sol` / `xhigh`；持续协调者统一分包、合入、日志监控及收尾，可直接并行调用多组实施/审核子 agent，遇到问题可直接派排查与修复。此为本阶段对默认 Astra 审核及不同模型家族要求的专项角色安排，按实际模型如实记录，不宣称 Terra/Sol 的名称本身证明不同模型家族。新上下文、实施与审核职责分离、同 finding 原审复审仍保留。协调者建议同样使用 Terra xhigh。

## 2. 固定来源与适用性

- 产品基准：`7469fbcb4afccf31bfc212f7609ca6ab2f2d45e5`。
- 本轮起点：`f3ff008710c2c038dfa5467a4117df64754c4974`，工作区 `/home/dev/gdds-gw08-dual-env`，既有分支 `gw08-dual-env`。经只读核对，其相对产品基准仅三份文档变化。性能控制版本以该提交的产品代码为准；可添加双方相同且已审的旅程工具，准确记录实际运行 SHA 和差异。
- [综合报告](/home/dev/gdds-stage-exchange/gw08-preview-optimization-investigation/REPORT.md)、[Astra 分析](/home/dev/gdds-stage-exchange/gw08-preview-optimization-investigation/ASTRA-ANALYSIS.md)、[候选矩阵](/home/dev/gdds-stage-exchange/gw08-preview-optimization-investigation/CANDIDATE-MATRIX.md)、[适用性](/home/dev/gdds-stage-exchange/gw08-preview-optimization-investigation/BASELINE-APPLICABILITY.md)、[索引](/home/dev/gdds-stage-exchange/gw08-preview-optimization-investigation/EVIDENCE-INDEX.md)为背景。
- 旧空 baseline 的 312 对 annotation、约 22 秒 risk 和首轮已实施的 bundle 复用不得再次记为本轮收益。旧插桩时间不是当前控制样本。
- 旧远端归档读取未取得占用的偏差保留；不作为新的合规运行或门禁证据，也不为掩盖该偏差重跑旧调查。
- 既有业务修复的 deferred 项不因本次方案自动关闭。启动时检查增量，固定双方适用的源码；不静默追随移动 HEAD 或合入其他正确性修复。

## 3. 实现边界与责任表

主要改动 `vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_assembly.py`。现状 `_verify_store_bytes(store, ref, raw)` 先验传入 bytes 的 size/SHA，再 `locate` 并比较；部分调用方已经刚刚 `locate`，部分调用方刚刚 `put`，两种责任混在同一 helper。

| 屏障/调用点 | 目标实现 | 必须保留 |
| --- | --- | --- |
| `_plan_artifacts` 的 source 规划 | `raw = store.locate(ref)` 后只校验已读 bytes | 每个实际 source 完整读取、精确 ref、size/SHA、JSON canonical、嵌入引用闭合 |
| `validate_bundle` 的 final 成员 | 每个 entry 实际 locate 后只校验已读 bytes | 所有 final 引用完整回读；不能借 source 读取或 ref 声明跳过 |
| 新成员、manifest、closure 的 put 后检查 | 保留已生成 bytes 校验和一次实际 readback，并核与预期 bytes 一致 | 已有错误边界、写后损坏检测；独立 destination 的实际写入与校验 |
| manifest/closure 文档读取与验证 | 保持既有文档读取、绑定和结构校验 | 完整文档语义及 bundle 身份 |
| READY、checkpoint、发布 | 不改 | 恢复读验、CAS、取消、current-preview 保护和旧保护释放 |

可采用私有 `_verify_bytes(ref, raw)` 与 `_verify_written_bytes(store, ref, raw)` 两个职责清晰的 helper；命名由实施者决定。只保留需要的目标路径，删除被替代的混合职责 helper，不引入兼容别名、特性开关、持久验证标志、digest/version/ID 或扩大公共 ArtifactStorePort 保证。

同 store 成员复用、alias 内容匹配、canonical → EXPORT、独立 destination 复制保持不变。每个 alias source 仍独立读验，不凭相同 hash 声明跳过。manifest/closure、语义 preimage、digest、ID、版本、referenced_artifacts 与 golden 预期不变，出现差异先调查，不能靠更新 golden 接受。source/final 间不保留额外 raw bytes，不增长常驻内存；不跨阶段复用校验结论，不增加长锁。依然遵守 root/symlink、跨 scope 和协作清理边界及 [ADR 0012](refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)。

## 4. 语义设计核对与停止条件

准备会话的 Sol 只读核查支持窄方案，未发现依赖第二次读取的已确认 consumer；公开 `validate_bundle` 当前生产调用是 assembler 自调，但 Preview 和 History 均经 `assemble_operation_bundle` 使用该实现。实现者仍须针对最终固定源码确认调查 Q1 的窄核对：公开 `validate_bundle` 所有生产调用方、ArtifactStorePort 与生产/测试 adapter、既有异常向量，以及 [comparison-bundle Contract](contracts/comparison-bundle.md) 的 source、final、新写对象读回要求。输出三类调用责任表和必要错误/取消映射到交接区；无需再做全链路调查。

source 第一次 locate 的普通错误维持 `SOURCE_ARTIFACT_NOT_FOUND` 映射；`InterruptedError`、`TimeoutError`、`MemoryError` 传播及已有 checkpoint 保持。M admission 与预约因子不变。调用方必须自行核 raw size/SHA，不能以 Local adapter 已校验为由省略通用保证。保留 `ARTIFACT_INTEGRITY_MISMATCH`；put 后 bytes 不符仍按原业务错误处理。只有被删除的第二次 I/O 才触发的人工故障不要求原样重现，不将每个 syscall 窗口冻结为 Contract；但已确认 consumer 依赖的业务错误、取消、截止时间或保护语义不得被静默弱化。

若方案必须合并 source/final、删 put 后读回、扩公共 port、改变输出/版本、引入持久状态、修改信任域或扩大业务范围，停止受影响部分并交 Owner 决策。其余独立准备继续。

风险初判 C（可重建 Preview 产物，D 类 helper 改动）；协调者以实际调用链和失败后果复核，不因“校验”一词一律定 A，也不得忽略真实权威提交或跨 root 后果。本阶段无论该局部定级是否为 C，都安排一次代码与工具独审及最终全范围独审，可在无后续代码变化时复用同一审核主体并补最终证据核收。

## 5. 真实输入与业务预期

输入根 `/home/dev/gateway-data-management-system/legacy/data/test/`，按 `1/` 至 `5/` 顺序使用，每份含 `<编号>.pmc`。准备会话仅确认目录、文件名与约 304 MiB/份的目录占用，**未验证 parser 可接受性、业务差异、项目身份或替换分支覆盖**。目录总大小不是产品读取量。

新会话在合格专用节点先复用既有输入适配方式确认受支持的文件集合，禁止凭 `.pmc` 后缀臆造上传格式或直接执行输入中的 SQL/脚本。原输入只读，派生包另存；身份、相邻差异、表/行规模和预期变化记录在 `INPUTS.md`。复用已有输入摘要机制，由协调者在传输、包装及运行前核对，防止两版使用不同输入；不新增产品身份协议。

输入中同时存在 `sql/dbcfg.sql` 与 `source/sql/dbcfg.sql`，后者不能替代每步根下的实际 SQL；当前五份根下 SQL 大小不同而 source 副本大小相同。使用受支持的 SQL/logic/marker 集合并核现行输入 Contract，不能凭 `.pmc` 文件名判断同项目；身份由 canonical `version_manager` overlap 等现行规则决定。

四次变化逐项记录新增/删除/修改、项目身份、风险/导航预期及其来源。可从已有说明、源码 Contract 与离线输入检查得到的内容直接完成；只有实质业务意图无法确定时问 Owner。没有独立预期时可做两版回归对照，但不得将“两版相等”当作独立业务正确性证明。未覆盖 replacement、no-change 或极端容量如实说明，不自动补数据或追加运行。

## 6. 场景与 12 次预算

控制版和候选版各有独立仓库/control DB/artifact/cache/workspace，按相同逻辑前置状态运行。每版 MO 共五次：

| 场景 | baseline | 上传 modified | 完成后的动作 |
| --- | --- | --- | --- |
| M1 | 空 | 数据 1 | 断言通过后 Submit→Review APPROVE→Archive，建立 B1 |
| M2 | B1 | 数据 2 | 断言通过后 Submit→Review APPROVE→Archive，建立 B2 |
| M3 | B2 | 数据 3 | 断言通过后 Submit→Review APPROVE→Archive，建立 B3 |
| M4 | B3 | 数据 4 | 断言通过后 Submit→Review APPROVE→Archive，建立 B4 |
| M5 | B4 | 数据 5 | 断言通过后 Submit→Review APPROVE→Archive，核历史和最终状态 |

这里 B 是已归档业务 baseline：Submit 仅推进技术 main，必须继续 Review APPROVE 和 Archive，再核技术提交与业务 baseline head；不能只做 Submit 后假设 B 已推进。若实际无变化或身份异常导致无法按 Contract 提交，停止依赖步骤，不伪造变更或强推 Archive。

另每版一次 F：在 M2–M5 中事先选定代表变化 k，baseline=B(k−1)、initial=数据(k−1)、modified=数据k。FULL 的 baseline→initial 预期同内容，initial→modified 为选定变化；真实身份和输出按 Contract 核对。默认 k=2，即归档数据1后做 initial=1/modified=2；输入核对显示另一变化更适合时，可在任何真实 Preview 前改选并对两版冻结。此 F 不宣称两个 pair 均有业务变化；但选定的 initial→modified 必须按实际产物确认有非零业务变化，不能凭文件不同断言。若为零、身份异常或结果不可判定，不算满足代表性变化，保留已消耗次数并停止该项依赖验收，按影响和余额处理；不能改清单掩盖缺项或擅自追加。选择依据为业务变化覆盖及输入规模，不能跑完多个 FULL 后挑最好成绩。

在该版执行 Mk 之前、baseline 仍为 B(k−1) 时，优先用独立 workspace 运行 F（已知同 actor/device/project 仅允许一个 OPEN workspace，按最终源码复核，必要时使用获准测试 actor 的同 scope 独立 workspace；若沿用原 workspace，核 version 并按受支持流程重新上传 MO），只 Preview、下载并核对，不提交 FULL；然后继续 MO 主链。由两个版本各自 MO 链提供前置状态，避免重建 FULL baseline 时额外调用 Preview。若现有接口/入口无法这样表达，先修改并审核最小测试编排；不能暗中增加 Preview 或通过直写数据库伪造提交。若仍无法满足，停止该场景并说明实际需要的范围变更。

总计 `2 × (5 MO + 1 FULL) = 12`。所有额外诊断、重试、准备用真实 Preview 都计入次数，已受理的失败也计入；受理不明先查 operation，禁止盲重发。未到受理的环境准备失败不算 Preview。默认不做 no-change、额外 warmup 或重复采样。剩余额度内按影响接续；需要超过 12 次才交 Owner 确认，不因单个失败默认全链重跑。

## 7. 对照设计与指标

同组同节点、同资源/存储条件、同输入、同配置和同旅程工具；生产保持 N1、单 active、M24 GiB、32 GiB worker envelope、8 GiB reserve。不把测试并发配置变为产品并发。CPU 限额按实际批准配置固定并记录，不仅写 guest 核数。

双方应用缓存从隔离的同类初态开始，沿各自五步自然积累；候选版不消费控制版产物或缓存。OS/page cache 不假称冷缓存，不执行全局 drop cache；记录运行顺序和相关干扰，单次对照承认次序偏差。性能组内不并发其他测试、构建或镜像操作；物理宿主干扰按现行规则处理。

| 指标 | 定义与用途 |
| --- | --- |
| 用户等待 | 受理到同 operation 结果可读，双方相同轮询；主要端到端指标 |
| bundle 时间 | 同边界单调时钟差；不混 READY/publish 时间 |
| source/final 次数与逻辑 bytes | 只记录执行中已有 ref/bytes；验证预期减少的调用，不等同物理磁盘 I/O |
| 正确性 | comparison/risk/navigation、表和侧绑定、完整引用、提交与历史状态；按现行 Contract 及既有 comparator |
| 资源 | 既有可靠 telemetry 的峰值内存、CPU、I/O；缺失记未知，counter delta 不冒称峰值 |
| 准备和提交 | 单列耗时，不混入 Preview 时间；失败和前置状态一起留存 |

优先既有计时/日志和局部测试计数。若必要观测缺失，仅可加相同的最小 harness/普通计数与现有阶段计时，明确观测 SHA、作用范围、开销与双方对称性；不安装 profiler、另建监控服务或扫描全量产物来计时。若运行需源码插桩，双方用相同观测补丁且均已提交；去插桩后产品 SHA 的门禁单独绑定，性能结果只属于被测版本，不假称去插桩版本实测。没有必要指标时可以交付未知，不为补齐表格加真实运行。

两版业务内容按确定性字段比较；不同 repository/workspace scope 的身份按已有明确映射处理，所有排除字段及依据先审后冻结。不整体忽略风险、导航、digest 或时间相关业务字段；一致性失败先作为 finding。source/final 两处预期各少一次相应成员读取，其他调用不作总次数减半承诺。

每场景报告原始时间、绝对差、相对差及适用限制，不用五个不同场景当五次同分布重复样本，不宣称 p95 或统计显著性。局部调用少但总等待不改善，结论为“局部工作减少，用户收益未证明”。没有明确收益或资源退化时可停止推广，保留工程判断和原件；不自动开启第二优化方向。

## 8. 验证与退出

focused 以现有 bundle 完整性测试为权威 owner，覆盖错误返回 bytes、缺失/错 ref、发布中复用成员损坏由 final 拒绝、新写对象读回、独立 destination、alias/mixed roots/canonical 重写；按实际影响补取消/预算、READY/恢复/保护消费者向量。避免逐私有 I/O 次序故障矩阵，新增测试只补缺失的业务屏障。

具体建议：先跑 `tests/test_bundle_assembly.py`，按缺口补同长度错 bytes、公开 final verifier 拒绝坏 adapter raw、destination 写后读回不一致向量；可用一个同/独立 destination 参数化的 binary 成员读取计数断言证明明确消除的工作，避免测试内部无关调用序列。必要 Local/mixed-root smoke 复用 `test_bundle_download.py::test_download_reopens_mixed_root_members_and_independent_destination`。History 受影响消费者由既有 backend 权威包覆盖，不新增真实 History 旅程。

代码变更必须在专用节点完成五 Python 包 ruff/mypy；Rust 未变不额外启 rustfmt/clippy，Rust 有变按规范执行并强制重装 backend 扩展。序列敏感 focused 使用 `-n 0`。必要权威包与最终候选容器结果按自动门禁闭包处理，不能以本次 12 次旅程代替；本阶段不是项目 S5/发布/production，不自动扩大为六包 fresh。

退出须分别给出：实现与独审结论、focused/静态/门禁结果、最多 12 次 Preview 尝试（6 种逻辑场景各两版）和正确性结果、性能观察及未测限制。未知/失败不被摘要覆盖。因收益不明停止也可交付调查结论，但不称优化收益或阶段验收通过。详细执行依 [实施计划](preview-bundle-read-optimization-implementation.md)。

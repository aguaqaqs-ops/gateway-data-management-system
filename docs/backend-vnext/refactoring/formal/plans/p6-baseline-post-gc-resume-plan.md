# GC 修复后的基准接续取舍

2026-11-07，p6-backend-design。**Owner 已明确选择 A，分版本参考补齐及下述限定来源输入例外生效；B 未选。** 本文件据此固定接续范围，取代此前“等待 Owner 选择、所有后续测量停止”的阶段快照。既有唯一实施者、接续审核者及直接协作方式继续有效，不新增会话/角色；接续审核者只集中核本次有限恢复关系与结果，不接管基准 exit。

## 已核事实

冻结 GC 修复产品为 `9704d0b286049073529d60036dbd999032f97e0a`，镜像和小 Compose 已由审核 §87 通过；候选 b 的实际 prepare-only 完成性由[审核 §91](p6-submit-single-step-diagnostic-scope-review.md)（`7649d0c624`）限定通过。一次 POST/claim，prepare 成功、submit_import 尚未领取，375 次续租成功、全部 10 个阶段正常返回、GC 观察及正常空闲回收有证据。guardian 派生 flag 的末轮读取差异非阻塞，仅更正文书，不重跑。

这不是一次完整 Submit/History 或 CT108 正式计时。约 63 分钟的 CT05 诊断耗时带 observer 扰动，不能填为正式 v2-submit 时长；b 原卷和所有旧证据保留。输入生成、composite/cache 的合格摘要复用，与旧业务步骤/性能数据的沿用是不同问题。

## 为什么需要一次实质取舍

[DC64 §2](p6-s0-owner-decisions.md) 对共享 worker/Repository Service 变化默认要求整档，受影响计时须在目标产品实测；DC66 的失败 checkpoint 续跑默认同产品。DC80 的跨版本例外只覆盖 READY 容量修正，不能自动扩展到后续 RS/JCS/GC 修复。诊断来源 `p6bw4s4h120261105b:v2-preview` 的 source RS run-bound full identity 缺口，仅获准作诊断输入，不能隐去后标成正式 carried。

因此本次决定涉及冻结版本与证据复用口径，超出普通脚本 GO。Owner 已取消的逐 manifest GO 不再增加；也不能用其替代这一实质决定。

## A：分版本补齐参考基准（Owner 已批准）

- 保留已关闭场景的原产品、镜像、节点和实际结果，作为历史参考，不冒充 `9704` 或单一冻结版本的完整矩阵。H3 原身份历史 PASS 不重跑。
- Owner 已接受原 `p6bw4s4h120261105b` 的限定来源输入例外：使用其 `evidence/checkpoints/v2-submit`，其中 **`completed_through=v2-preview`，`resume_step=v2-submit`**，不是更早 `p6bw4s4h120261105a` 的 Preview 前 checkpoint。新 project/key/三卷，在 `9704` 及全身份已核目标镜像下补 W4 Submit/History 等路径。来源 RS run-bound full identity 缺口原样保留，不宣称 MATCH 或 carried；关键输入、卷摘要、规则/cache/TTL 及目标身份仍须核实。不使用候选 b 的 prepare 后状态缩短计时，凡记录完整 v2-submit 就包含其 prepare。
- 正式路径计时仍在 CT108 独占，沿原计时区间；新数据明确绑定目标产品和实际来源。CT05 prepare 结果只作修复及分段参考，不跨节点拼成完整正式时长。既有输入合格即复用，不重生成 SQL。
- 补齐尚缺 W4 负载/分段及报告材料，逐项保留真实覆盖；缺项仍标未测，不因使用多个版本将其填零或写 PASS。最终交付明确为**分版本参考材料及剩余路径实测**，不是所有结果均属于同一产品的完整正式基准。

此方案减少重测，适合 DC81“完整测量作为后续参考参数”的开发安排；代价是跨版本性能不能直接作同一冻结版本的严格可比结论。跨版本数值偏差须解释并标明来源，不机械地按旧参考偏差重复整个场景；真实数据不符、必要守护失效或明确干扰仍按原停止/诊断规则处理。

## 场景与版本映射、执行顺序

| 项目 | A 的接续处理与版本来源 |
| --- | --- |
| 已完成 t1–t4、2× core（W1/W2/W3、S1–S3、H1）、W3-FULL/H1-FULL、H1-REFILL、H2 两/三节点、H3 | 保留各原 run 的 HEAD/镜像/节点及实际完成结论，逐项引用旧记录；不重测、不改记为9704。较新完成记录优先于旧待办快照，旧清单仍写未完不自动构成重跑依据。若索引确有实际缺口，明确报告而不补造。 |
| 首轮 W4/S4/H1 缺口 | 从上述 source 已完成 v2-preview 的输入状态接续 v2-submit 及其后 Repository read/History/核对；新运行绑定9704产品、新 project/key/三卷及已核三镜像，完整 Submit 计时保留 prepare。 |
| W4-FULL、W4-STRESS | 只跑未完成范围；10% cold Preview/healthy History与100%压力按原定义分别记录，不把同名已完成的W3-FULL误列未完成。输入根可复用，压力结果如实报告，不写未证性能 PASS。 |
| 631/631 表哈希、DC63 #1、V5b A–D | 在适用的已完成状态或新测量上补真正缺项；复用原工具，写明每项产品/步骤/节点来源，不为采集同一不变量重跑已闭合旅程。 |
| JSON/SHA、comparator 与总报告 | 保存按实际版本分列的记录及索引，报告差异与缺口；单版本 schema 不能如实表达时采用多份既有记录加总索引或最小工具修正，不伪填统一 HEAD，不以文案/字段统计问题重跑产品。 |
| 04 最终权威 runner | 归属本冻结参考线的最终工具候选 V_ref，其产品路径须等于已审9704；可含必要 benchmarks/tests/docs 修正。不借当前 main/S2b 的六包结果冒充本线结果。按原入口、最终候选及按包闭包规则核验/执行，不重复已合格且闭包相等的包；原最终门禁作为独立收口待办，与 CT108 补测可在不同节点并行，不新增“每轮先全量”门槛。阶段 exit 仍另行办理。 |

实施者维护原运行/步骤到上述各行的具体证据索引；首轮只集中核本次 source→目标与必要执行条件，不把所有历史记录重新审一遍作为启动前提。原 handoff 较新记录已把 full-v2、H1-REFILL、H2/H3 从待办扣除，其旧 §200 待办不再驱动执行。

本地 Git 已核 `e798ec87a37330250b0c051162e7962dba1daa60` 是 `9704d0b286` 的祖先，且 `application/checkpoints.py` 无差异，READY 容量修复已被目标包含；无需再证明两棵产品树相同。目标相对该 H 的生产路径差异只有 RS metadata/cold catalog、JCS digest sink、worker GC 调度及其必要导出，按已审具体差异映射，不使用任意版本或通用 skip。

## 工具、镜像和时间预算

允许现有实施者在隔离参考线把已审9704产品与必要恢复工具固定为 clean 候选；只改本次 benchmarks/测试/运行文书，不另改产品语义、不合当前 main。已有 §87 镜像和已核归档可向 CT108 离线预置，比较 config digest/全部有序 DiffID；不为统一标签无故重建，实际边界变化按既有镜像规则处理。

先做受影响接线的必要 focused，普通修正直接闭环，不重跑已通过小 Compose 或 b 的 prepare-only。计时只用原旅程边界及轻量既有采样，不把诊断 wrapper/profiling 放入参考计时。

运行前一次给足工具等待预算：冻结工具 t4:v2-submit 当前为 `ceil(810.961×5)=4055s`，而 b 的 prepare 本身已用约3755s，不能机械沿用仅剩约300s余量的等待窗。W4 新目标的 v2-submit 工具等待采用已批10800s观察上限；产品 lease/heartbeat/stall、HTTP单请求及Repository业务超时不改。每个实际运行按所选完整步骤的一次性上限加初始化/清理余量固定总截止，不能把 prepare-only 的14400s总限机械套到多个长步骤的总和，也不在运行中滑动加时。关键恢复核验一并确认这些数值；完成即收尾，不等待用满，不将预算当ETA或性能门槛。

首轮实际选项固定为 t4、scope=full、MODIFIED_ONLY、resume_step=v2-submit，`full_v2=false`、`three_node_history=false`、`cross_project=false`、`history_cache_mode=none`；不重做旧步骤、不新增 Archive/v3 旅程。实际新步骤为 v2-submit、v2-repository-read、v2-approve、history，以及既有尾部 hash/比较/HTTP artifact 读取和证据收尾。普通 HTTP/归档 helper 若属于这些步骤，其等待计入所属阶段，不另开无界路径。

| 首轮阶段 | 工具预算（秒） |
| --- | ---: |
| 初始化、预检、恢复和必要目标快照 | 1800 |
| 完整 v2-submit（包含 prepare） | 10800 |
| v2-repository-read、v2-approve 及相应普通 HTTP | 1800 |
| History 与其结果读取 | 7200 |
| 尾部表哈希/比较、artifact/归档和正常证据收尾 | 3600 |
| **固定工作截止：以上合计，从 launcher 起点计算** | **25200** |
| **停止、reap、Compose cleanup/postflight 预留** | **1800** |
| **全流程 hard 截止：work + cleanup，从同一起点计算** | **27000** |

这是一次充分且有界的首轮安排，不是7.5小时完成预测；完成即退出。Submit/History 等长操作的等待截止为 `min(操作起点 + 本操作预算, 固定 work 截止)`；辅助阶段数值用于一次计算总 work 和余量，普通 HTTP/Repository read/Archive helper 沿已有单次 I/O 超时并受总 work 截止约束，不要求为每个 helper 新建强取消层。进入新阶段不重置总截止，初始化和尾部也不能漏出外层预算。沿既有外层进程/容器有界收束和保卷逻辑，work耗尽即停止新业务并进入清理，全部收束不得越hard截止；不为此建设另一套guardian或持久状态机。实现/固定runbook应一致，恢复关系审核一次核对即可，不重复Owner或最终manifest签字。

## B：保留单一修复版本的完整正式基准（未选）

将目标产品固定为 `9704`，在 CT108 按原口径重新取得所有实际受共享 runtime/RS/JCS 修复影响的场景计时；无法证明未受影响的既有旅程不沿用为该目标产品的结果。不使用缺失正式来源资格的诊断 checkpoint 冒充 carried。

同样复用合格的 SQL 输入、缓存及已验证工具，不重生成数据；按影响面进行必要门禁及计时，不无依据加矩阵。代价是多档长旅程，需要更多计算时间，目前不提供无证据的完成估计。纯工具或确实不受影响的结果仍按原规则独立判定，无需一律重跑。

## Owner A 选择后的直接执行方式

Owner 已明确交付口径及 A 的限定来源例外。实施者现在直接准备必要工具、focused、镜像/环境与首轮执行材料；既有接续审核者集中核本次 source→9704 关系、必要守护和关键预算一次，通过后实施者现场取锁直接执行首轮并顺序推进上述未完成范围，结果事后独审，不逐摘要申请 GO，不等新 Owner/设计回执。普通接线/测试/文书修正沿 Owner 简化流程直接闭环。

b 的原卷、旧 source 原卷和所有证据保持只读保留；不能直接启动 b 的 successor，也不把旧GO当新执行许可。源输入/目标身份或必要守护实际不符仍停止该运行并按DC80诊断/最小修正；需新业务取舍、资源上限变化或无法满足本次已批准来源条件时，提出具体替代方案。未授权 main 产品合入、push/tag；阶段 exit 与定时巡检结束仍按 Owner 及既有角色范围另行办理。统一版本的完整正式基准未被宣称恢复，但 A 的分版本参考接续已授权，不得再以旧“所有测量 STOP/Owner未选择”快照阻塞。

# GC 修复后的基准接续取舍

2026-11-07，p6-backend-design。**Owner 已明确选择 A，分版本参考补齐及下述限定来源输入例外生效；B 未选。接续审核 §92（`d4c098d9dc`）已集中通过本次有限恢复关系及首轮预算，并直接通知实施者。** 本文件据此固定接续范围，取代此前“等待 Owner 选择、所有后续测量停止”的阶段快照。既有唯一实施者、接续审核者及直接协作方式继续有效，不新增会话/角色；接续审核者只核本次有限接续与结果，不接管基准 exit。

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
| 首轮 W4/S4/H1 缺口 | **已完成本次有限接续：** `p6w4resume970420261107b`、工具HEAD `3fd64dc2fe`、handoff `945d9141c4`，由接续审核§101（`59b96c3cd9`）独立PASS。从上述source的v2-preview完成态接续，9704产品上的Submit/read/approve/History及收尾通过，完整Submit保留prepare。该项从待办扣除，不重跑；history cache mode=none，不代替healthy History/H3，也不代表完整矩阵或阶段exit。 |
| W4-FULL | **已独审PASS：** `p6w4full20261107a`、工具HEAD `18a4851d8c`，2026-11-07 11:49:34–15:56:39Z，18步及输入/清理通过，接续审核§113（`0bf7218401`）闭合。RS完整身份用原首operation前记录的同节点immutableID作16:13事后元数据链接，不冒称11:49新快照；不重跑该业务。 |
| W4-STRESS | **已独审PASS：** `p6w4stress20261107a`、工具HEAD `1742a8bcd6`，2026-11-07 16:21:02–19:24:06Z于CT108完成，接续审核§124（`40112a8a17`）关闭旅程/取证项。100%/cold Preview、14个本run PASS步骤、13checkpoint及输入/三镜像/清理均已核；v2 Preview READY/完成4661.281s。scope止于v2 Preview，未执行v2 Submit或History，不重跑；按record_only保留，不记性能目标PASS，worker指标旁证已由§127通过，标准record派生仍待。 |
| 631/631 表哈希 | **三组实际对照已独审PASS：** 2× v1/v2及H2三节点v3与各自S1c参考的完整表集合及逐值一致，接续审核§115（`0bf7218401`）关闭§105待办。复用原summary，不再重取卷/重跑已闭合旅程，保留各真实版本。 |
| DC63 #1、V5b A–D | **journey/coverage完成，V5b局部修复中：** 接续审核已核d2ffe在CT108的完整journey返回、23:47:34Z History timing及coverage PASS/8 expectations/91 events；V5b测量helper以旧READERS_REQUIRED构造空before，真实pair pipeline要求artifact，00:12:23Z整命令exit1。保原FAILED raw的两段materialization及已完旅程，不判产品缺陷/整链PASS；仅修helper为ARTIFACTS_REQUIRED，按[最小补缺方案有限接续](p6-dc63-v5b-measurement-completion-plan.md)复用本次v1 commit/必要RS做V5b-only，不重跑journey/业务任务。原绝对截止/剩余预算、冻结身份和保卷保持，结果待独审。 |
| JSON/SHA、comparator 与总报告 | 实施者已在05生成W4-FULL与2×core标准record及来源索引；core初稿schema通过但场景语义须按下文修订，FULL与修订后的core均待独审；STRESS所需原launch/resources/run/state已有§124认证的CT201副本，可LAN到05派生，不因当前派生目录缺副本记原证据UNAVAILABLE。按实际版本分列、报告具体差异与缺口；单版本schema不足时用多份真实记录加总索引或最小工具修正，不伪填统一HEAD，不因文案/字段问题重跑产品。 |
| 04 最终权威 runner | **H780本轮exit1，窄修继续：** `78000beb62e927190092e315135e7bc1cbdda615`获§129代码/05定向及五包静态通过后，于2026-11-07 23:55:57Z启动全六包，实施者报告2026-11-08 00:19:48Z exit1、起止clean，backend/RS各一并行失败、serial已完成。实施者已报告按所有权安全释放04标记、失败材料保留，closed结果/收尾待独审，不原样重跑或作carried。按下述范围只修历史恢复测试输入及RS环境隔离，严格guard及实际门禁network-none保持。旧fcc全六包exit1及原日志/收尾均保留，不重跑已关测量、不借main/S2b结果，最终门禁及阶段exit尚未完成。 |

实施者维护原运行/步骤到上述各行的具体证据索引；首轮只集中核本次 source→目标与必要执行条件，不把所有历史记录重新审一遍作为启动前提。原 handoff 较新记录已把 full-v2、H1-REFILL、H2/H3 从待办扣除，其旧 §200 待办不再驱动执行。

**04最终镜像准备补充：** 已核本冻结线RS测试harness同时检查candidate SHA、build-input、source-tree和lock，而backend harness只检查RS的source身份；共享闭包又包含所选RS本机image ID。最终V_ref冻结后，在04专用tag上预先核齐RS revision等身份，避免后段测试自动重建同tag。沿现有取证方式保存实际运行前不可变config digest、全部有序DiffID及同节点image ID，并核对结束时RS tag是否漂移；不能以终态tag代旧runtime或仅凭same-source宣称carried。这里不借其他开发线的结果或补验方案，不提前运行未冻结候选，不修改CT108的测量镜像/tag；client e2e的既有正常自动重建规则保持。

**开发构建源定位（2026-11-07）：** 原获准CT201开发构建源的实际hostname为当前本机`heavy-dev-01.lan`；本线§87构建原日志首行、标为`source=heavy-dev-01 CT201`的传输记录及S2a handoff §6均可核。本线在同一开发源按固定clean候选/原脚本本地预构建，无需等待不存在的`ct201` SSH别名；先核实际daemon、锁及基镜像并记真实host。节点编号不等于IP末段，当前SSH配置的`.201`属于CT108测量节点，不作为开发构建目标。此处不新增构建节点或改变冻结镜像流程；开发机只构建，测试仍在指定04/05，其他节点取用仍按现场配置和有效占用。

Repository Service原官方预置依赖分支仍可在04离线构建，不被上述开发源定位覆盖。本次04已核`gateway-p2r1-repository:lock-6dc9659f0aee`及lock label匹配，按接续审核核定的clean detached候选和官方脚本、`UV_OFFLINE=1`/build network none直接构建专用RS tag；不用为此等待CT201 SSH或另起重复开发源构建。backend/worker如需旧冻结流程的整镜像预构建，仍使用既有开发源；RS candidate revision在backend manifest前固定，已起的合法构建继续而不双头执行。

**后处理指标口径更正：** owning设计§16.3要求W系列分别保留单operation的READY与完成时间，H1/H1-FULL/H1-回填/H2/H3以READY为主，H2三节点取完成，S1/S3/S4取main前移的Submit完成，S2取同步受理并核无Repository operation。整旅程elapsed单列，不作为这些指标的替代；不得统一改成completion而丢失READY。S2没有新operation不等于受理耗时为零，缺精确受理计时时只单列实际可得的代理口径并说明限制。

已发现部分deviation selector误取整旅程、H2三节点的旧参考19361.157s也取整旅程。现有双方从认证的原run/state/summary中修正派生actual与同operation/同端点reference，保留产品/输入/节点及原SHA，不修改原证据或共享计时；record builder与deviation工具分别核实际影响，不将一个工具的修正泛化成另一个已错。原policy及统计规则保持，不能恢复合法参考时明确UNAVAILABLE/不可比及原因，不伪填或静默改policy。本修正不因错误selector、字段抽取或A下跨版本旧差异触发已关闭业务重跑；实际干扰、数据/身份不符仍按原停止和DC80处置。

**基准性能目标与当前推进分开：** DC66明确本重建对照基准不进行性能门槛判定，Owner也已说明性能指标须结合物理限制评估。H2三节点同operation完成时间已由接续审核§114（`0bf7218401`）认证原state并核验闭合：b96历史参考4892.584s、e076目标4886.678s，取代错误的整旅程比较，原raw保持不变；超过600s目标须如实标未达，不能记性能PASS。此处保留旧版本参考事实及未来S5/S6目标，不降低目标、不改变compare policy，也不把预优化基准的目标未达当产品失败或已关闭业务的重跑理由；原结果/身份异常仍正常处置。

其余13项record-only selector及逐指标来源标注已有定向验证；各场景完整record/comparator的最终汇总仍待完成，不能据局部修正宣称全量收口。

**现有comparator的实际范围：** H780的p6_baseline_compare.compare_records本来用于跨阶段，只比较inputs及相应scenario的result_fingerprint/counts/state，不要求两个record的HEAD相同，timing明确不在其中比较。版本不同本身不是“缺少兼容comparator”的理由；有同输入/同场景及相同解释口径的合法baseline record时使用现有工具。若缺对应baseline record或指标范围已变，外部索引应明确具体缺项/不可比原因及已审§115正确性旁证，不虚构一致、补造统一版本或建设兼容层，也不扩大重测矩阵。H2同端点时长仍由既有timing工具及其原policy单独比较。

**派生元数据的场景语义（2026-11-08）：** schema通过只证明形状合法。bb348 core原三upload的input_completeness均为MODIFIED_ONLY，W1/W2/W3及对应S1/S2/S3应按原输入标MODIFIED_ONLY；该负载的H1属于§16.3普通Preview之后的首查，state.mode同样标MODIFIED_ONLY，不能因History读取完整commit或“完整旅程”改记FULL，FULL Preview之后的另列H1-FULL。baseline按各原operation及实际提交关系逐项描述，不把所有场景统一为v1→v2。W2原cache_state_before/after已有行数/TTL/对象文件事实时如实保留，不能写成均未记录；实际命中计数仍未知。H1引用§127起点342对象健康证明，after保留未知。只修派生metadata/record/index并保留初稿，不改raw/schema、不补造字段或重测业务，当前core语义修订及FULL实际计时/旁证仍待独审。

**producer与被测来源分开：** 审核发现初稿实际调用0739旧record builder，不含§119/fcc已审资源规则，须在05以clean已审H780 producer真实重建，确认执行/导入路径与代码身份，保留旧输出，不只改标签。record中的被测run HEAD仍为各原18a/bb348等来源；实际producer HEAD、文件SHA/命令及六个Git tree字段的确切路径映射另记外部索引，不伪填统一H780或把可复现的不同路径摘要误报产品漂移。沿已审规则将0周期samples的cores/memory/disk峰值记未知及原因，独立step CPU端点有观测时保留；这不要求新增补丁或业务重测。重建记录、元数据及索引统一交独审，整体资格未提前结案。

**Preview worker步骤漏采的派生补取：** 旧producer从`operation_timing`取operation ID，而真实Preview ID位于`preview.result`，因此FULL及部分core历史summary未存对应DB worker步骤；这不推翻已保存的READY/完成、指纹或资源值。未来非在途producer修正真实消费路径并做必要focused；现有记录优先核已存结构，真缺时在正式压力测量结束后，只取该运行已停control DB/合格checkpoint的私有小副本，沿原SQL和时钟按原operation ID补同次步骤，另记来源SHA及派生，不改raw、复制Repository大卷、起旧栈或重跑产品。DB started/completed时间不冒称DC63 executor细span；仅确实不可恢复时明确UNAVAILABLE及具体资格，不填零或直接弱化record校验。core H1缺后加的显式cache字段也不自动失效，可在同次副本按原History起点UTC核规则/TTL及相关对象，不用今天过期反推历史失效、不追加H3后设字段，也不以重复查询替首查。

**core主文件的有限派生路径（2026-11-07）：** 接续审核者只读文件核验报告，bb348 before-History源现为主DB、32768B SHM和空WAL三文件，完整目录仍与原checkpoint不符；主DB单文件按原摘要字段的投影则精确等于原control树`4baede398e55e77569836c0b51c98d1edd6b7aab6451b7cbb7d9793ff6d1aad4`、2150400B。本次不恢复或修改源目录，也不把当前源全树标MATCH。允许保留原三文件及实际差异记录，只复制该已认证主文件到新私有目录，开库前用原算法核验私有目录的**完整树**精确等于原checkpoint，再在专用节点复制件提取同run worker步骤及H1历史DB字段；逐项保存原state/operation ID、复制与提取节点、文件/目录摘要及派生结果，由接续审核者核实际资格。此路径仅补历史记录，不用于业务恢复、checkpoint续跑或carried，不泛化为忽略WAL/SHM的摘要规则；H1实际缓存对象仍须各自来源核验，不能仅凭DB字段宣称健康。不要求唯一定位旧SHM创建者作为新前置，主文件/空WAL/复制前后完整摘要等实际条件不满足时停该派生并具体诊断，其他任务继续。

**历史补证交付状态（2026-11-07）：** 接续审核§127（`bffd60baac`）已通过合并sidecar `9bdce65c7e519cd56264c1f01b73f3d5ee7829e8fad173b1a5555c09ba7a03de`，范围限FULL/STRESS/core三来源的历史worker步骤及core H1查询起点输入条件：05实际提取、源DB/私有目录身份、7个operation/21个UTC步骤与认证state一致，原H1 compare起点07:36:37.829Z的342条缓存记录及实际引用对象/JCS引用逐项相符，过期、缺失及内容差异均0。artifact整个目录未重新hash的限制明确保留，此次只认证这些引用对象；core当前源全目录MISMATCH及私有原main完整MATCH分别保留。实施者可直接在派生record中消费该旁证，不改raw的none、cache_after或命中计数，不转为业务恢复许可，也不为修改sidecar内原REVIEW_PENDING字节再签一轮。该项从待补证扣除；完整record/comparator、DC63/V5b及04门禁仍须各自完成。

本地 Git 已核 `e798ec87a37330250b0c051162e7962dba1daa60` 是 `9704d0b286` 的祖先，且 `application/checkpoints.py` 无差异，READY 容量修复已被目标包含；无需再证明两棵产品树相同。目标相对该 H 的生产路径差异只有 RS metadata/cold catalog、JCS digest sink、worker GC 调度及其必要导出，按已审具体差异映射，不使用任意版本或通用 skip。

**H780历史恢复测试与环境隔离修正（2026-11-08）：** 实际`_require_post_gc_product_transition`以固定target.product_commit=`9704`比较所传候选，source=`e798`用于来源身份核验，不能把e798→9704已审产品修订误报为新候选产品漂移。9704→H780超旧白名单的RS测试文件不属于该固定历史恢复工具的既定路径。本轮采用审核者更小的修法：固定恢复身份测试使用真实已执行恢复提交`3fd64dc2fe9a9c11ceebf8cd458983b9507f5364`，严格guard及路径白名单保持，撤回前一文书允许扩展RS测试路径的实施方向。固定9704祖先/产品tree、来源e798、clean及真实产品路径拒绝不变；历史测试通过不证明H780或未来候选可用于该固定恢复，当前V_ref身份仍按本线实际产品/镜像/闭包核验。

RS的`test_build_script_defaults_docker_build_network_to_host`由测试环境准备显式隔离ambient build-network，并保留default/override语义；实际04门禁network-none及真实构建harness不变。两项仅测试输入修正由唯一实施者在独立worktree完成必要focused/静态并交独审，原H780运行/证据自然收尾，不改在途worktree或原样重试，CT108诊断和其他独立收尾保持，无新Owner或逐摘要GO。

**058门禁的Compose环境接线修正（2026-11-08）：** `058e26da3c`全六包运行中，实施者发现`test_ordered_submit_bisect_compose.py::_compose_env`以裸字典替换子进程环境，实际RS容器使用旧`gateway-repository-service:local`，而provenance读取宿主配置后记了新候选tag。该次于02:02Z受控停止并保全，整次runner exit 1，不作为当前镜像门禁或qualified carried。继续沿既有测试工具修复授权，仅修该fixture对已配置镜像及必要离线构建环境的传递，实际容器与provenance须对应；不通过修改记录掩盖旧镜像，不改产品、严格恢复guard或路径白名单。受管门禁子任务完成最小diff、必要focused/静态，关键变化集中独审后，在新clean候选及其实际镜像上完成最终门禁；保留原失败，不原样重试或重开已关测量。镜像重建及逐包沿用仍按实际闭包和容器边界判定，不因测试修复另设性能或历史重核门槛。

**同根因fixture一次收齐（2026-11-08）：** `46e2bb63f7`已由§153通过上述bisect修正及必要05验证，但新runner尚未启动。准备中核对权威runner实际使用的七个Compose fixture，发现`test_ordered_compare_compose.py::_compose_env`也以裸字典丢弃同一环境；其余五个已复制受控环境。有限扩展为该compare fixture同样`import os`与字典首项`**os.environ`两行修正，专属fixture键继续优先。门禁子任务一次交清七个消费者的现有接线清单，并用同一真实Compose config focused覆盖两个修订fixture，集中审核增量及必要验证；其余五个不新增业务重测，不机械重跑已过1+20用例。最终每个既有旅程的实际RS对象均须与当次候选配置对应，不能用最后一次正确provenance替代前序旅程；消费原有取证能力，不为此新增框架或证明矩阵。46e准备态04于02:17:43Z安全释放，旧构建材料保留为准备事实，不能冒充修订后最终候选门禁；新clean候选仍按原授权及实际镜像边界继续，无新Owner或逐摘要GO。

**本次门禁的原生旁路取证：** 已发生的实际RS镜像错位及既有provenance单文件覆盖，支持本次04门禁外部使用标准Docker create事件及原样inspect，按准确project/RS服务过滤、逐container保存实际镜像对象和现有fixture挂载来源。仅在本次wrapper前后启动/有界停止，不改仓库harness、产品或Contract，不新增旅程、服务、持久机制或测试矩阵。具体短入口和候选增量/共同focused集中独审一次；正常镜像准备可并行，不等重复代码GO。采集覆盖缺口、命令失败或超时只列独立取证状态，不能当产品失败或自动中断runner；真实身份不符仍按原停止规则处置。runner真实exit与collector状态分别保留，缺项先核既有原件及必要定向补足，不默认重跑全量。最终资格由独审依据实际材料判断，不因采集器存在就宣逐旅程身份成立。

## 工具、镜像和时间预算

允许现有实施者在隔离参考线把已审9704产品与必要恢复工具固定为 clean 候选；只改本次 benchmarks/测试/运行文书，不另改产品语义、不合当前 main。已有 §87 镜像和已核归档可向 CT108 离线预置，比较 config digest/全部有序 DiffID；不为统一标签无故重建，实际边界变化按既有镜像规则处理。

先做受影响接线的必要 focused，普通修正直接闭环，不重跑已通过小 Compose 或 b 的 prepare-only。计时只用原旅程边界及轻量既有采样，不把诊断 wrapper/profiling 放入参考计时。

**launcher/sampler 启动契约修正（2026-11-07）：** `p6w4resume970420261107a` 的09:08:13Z启动在旅程及Submit之前以125退出；sampler前置校验将launcher的固定GNU `timeout`前缀误当作Python解释器。按实施报告及接续审核者已核记录保留本次失败、清理和释放日志，不复用该项目。允许仅在sampler启动元数据校验中识别launcher已有的精确前缀 `timeout --foreground --signal=INT --kill-after=1200s 25200s`，随后仍严格核本worktree的backend `.venv/bin/python`及原manifest/census/evidence绑定；直接Python入口保持原行为，不扩展为任意wrapper、shell或跳过身份。采样循环、频率、CPU/墙钟计时、产品及已批预算均不变。必要定向验证覆盖真实sampler消费者对该argv的接受及错误解释器/前缀的拒绝，并复用已有小GNU停止用例；不重跑历史成功计时、小Compose或大输入诊断。

本次新运行身份为 `p6w4resume970420261107b`；同步项目、幂等键、证据路径及固定身份绑定，执行前现场核未使用并按原规则取得有效占用。旧a证据保持，源checkpoint与9704产品保持；此次工具启动失败未发生业务POST，修正不增加业务运行次数。实施者和接续审核者直接完成必要修订/验证、普通预检后沿原A授权接续，结果事后独审，不另开Owner、最终manifest GO或协调回执。会话消息限1000 UTF-8字节，发送短状态及本地handoff/证据路径，完整报告留本地，不因消息超长新开会话。

运行前一次给足工具等待预算：冻结工具 t4:v2-submit 当前为 `ceil(810.961×5)=4055s`，而 b 的 prepare 本身已用约3755s，不能机械沿用仅剩约300s余量的等待窗。W4 新目标的 v2-submit 工具等待采用已批10800s观察上限；产品 lease/heartbeat/stall、HTTP单请求及Repository业务超时不改。每个实际运行按所选完整步骤的一次性上限加初始化/清理余量固定总截止，不能把 prepare-only 的14400s总限机械套到多个长步骤的总和，也不在运行中滑动加时。关键恢复核验一并确认这些数值；完成即收尾，不等待用满，不将预算当ETA或性能门槛。

首轮实际选项固定为 t4、scope=full、MODIFIED_ONLY、resume_step=v2-submit，`full_v2=false`、`three_node_history=false`、`cross_project=false`、`history_cache_mode=none`；不重做旧步骤、不新增 Archive/v3 旅程。实际新步骤为 v2-submit、v2-repository-read、v2-approve、history，以及既有尾部 hash/比较/HTTP artifact 读取和证据收尾。普通 HTTP/归档 helper 若属于这些步骤，其等待计入所属阶段，不另开无界路径。

这里的尾部“归档”仅指 artifact/证据文件打包，**不包含业务 v2-archive**；冻结旅程只有 `three_node_history=true` 才进入该业务步及 v3，本首轮不调用。read/approve 的1800秒也不含它。只请求实际经过的 checkpoint，首轮默认 v2-submit（按需要保存）、v2-repository-read 和 history；不为未执行的 v2-archive/v3 请求 checkpoint，避免成功收尾时产生“缺少断点”的工具错误。额外 before-approve 副本非必要，已完成 Submit 后的断点可保护昂贵 prepare，无需为同一边界多次复制。

**`history_cache_mode=none` 的 TTL 解释（2026-11-07）：** cache/TTL 核查用于记录本轮实际起点，不要求所有 `snapshot_table_export_cache` 条目仍在有效期。冻结产品 `SQLiteSnapshotTableExportCache.lookup_many` 对过期条目按 miss 处理并由正常路径重建，旅程只有非 none 模式才执行缓存条件准备；healthy/refill 的健康 TTL 要求不适用于本首轮。实施者07:58Z报告523条全部过期、缓存artifact缺失0，日志SHA256 `4dac4836be733644015828ea7b723aa57bde5073ff8d9251ef2edb403e361322`；此正常时间流逝不构成来源失效，不需新Owner例外/GO。保留原源、expiry和卷，不手动延长TTL、清缓存或预热；目标产品正常prune/rebuild及其成本如实计入，记录实际cache状态，不冒称warm/healthy或与旧缓存条件相同。权威输入/原artifact完整性仍核；本澄清不推广到H3或明确healthy/refill场景，也不解除F1等实际守护阻塞。

**同次 SQLite 查询副作用的精确可逆恢复（2026-11-07，DC80）：** 后续完整守卫发现源 control 树新增 `control.sqlite3-shm`（32768B）及空 `control.sqlite3-wal`，目录不再匹配原摘要；事故事实保留，不将单文件投影冒称完整目录 MATCH。接续审核者独立只读确认主 DB 3608576B、原内容和元数据稳定，按未修改的原树算法计算其单文件投影精确匹配原 expected。允许在确认相关 SQLite 检查进程已退出、持自有诊断占用时，先在原 checkpoint 之外保全事故三文件副本、完整 SHA/元数据与日志，再仅将本事故确认新增的两个 sidecar 原样移至事故证据目录；不删文件、不改 DB/run/state/expected 或元数据、不增加通用 ignore。移动后用未修改的完整 `_volume_tree_digest` 重核本 control 树；完全回归原 expected 即按原 A 授权接续，恢复记录直接交审核者核验，不再等 Owner 或新 GO。任有额外差异或守卫不匹配即停该步骤，不调整 mtime/权限/摘要凑值；其余两卷不为本事故重新扫描。后续确需源 SQLite 内容时先用私有小副本查询，不能再次以普通 SQLite connect 打开冻结源；不能将本次处置推广到非空 WAL、主 DB 已变或无法证明的来源。原卷、事故与恢复过程均如实保留。

**普通准备命令与派生日志封口：** 沿 c58/§88 的最新 Owner 流程，低风险准备错误停止原错误命令并留证后，查明原因、最小修正即可接续，不按累计次数再次等待 Owner；原 DC68 两次失败事实保留。源运行文件名以已审入口中的 `evidence/run.json`、`state.json` 及项目 `launch.log` 为准，不另猜 `run.log`。本轮恢复/status 日志是派生追溯材料，封口后将完整 SHA 写外部索引，不能把自身 SHA 追加到同一文件再用追加前摘要校验；已产生的自引用行原样保留并记录前后时点，不删行凑旧摘要。此次审核者已核 recovery.log 完整 SHA `8887a76025e09974ee6d8e6fcddf12beaff1d3ce36c31f5f081c41bf58d7729b` 稳定，去掉末行后的完整前缀精确匹配追加前的 `40642e40ca75201b9f730d6230625289b572e1e2d414fe4c29a11e13bf1b5918`，源 control 仍匹配；普通索引更正后直接正常预检，不重做源恢复/SQL/测试或重开 GO。既有源 run/state/launch、快照、输入和目标镜像等核心守卫继续有效；不在其外叠加手写派生元数据审批链，不把此类日志追加误判为源再次失配。

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

**后续W4-FULL的独立预算：** 本项为冻结runbook所定义的fresh `w4-10pct` 完整旅程，`full_v2=true`、cold Preview、healthy History及FULL两上传角色，不能使用107b的恢复身份或仅四步预算。旧fresh v2 Submit的4055s上限仅略高于107b实测4027.732s API耗时，须在启动前修正必要bench接线；v1 Submit沿4047s，v2 Submit10800s、History7200s，其余沿原步骤上限，计时上限合计61105s，辅助9000s。固定work70200s、cleanup1800s、hard72000s；沿已审session/timeout/清理机制的等待闭包71673s低于hard，不新建guardian。这是一次给足的保守工具上限，不是20小时ETA；完成即收尾。新固定producer前缀、sampler前置校验和实际fresh操作等待保持一致；不改变107b的原配置、共享采样/计时或产品lease/HTTP，必要定向验证后沿原授权执行，普通接线修正不重开GO。

**FULL局部等待与条件恢复限制：** 总work余量不证明所有局部等待均已校准。v2 Preview11300s仍来自旧t4实测2259.980s乘5，并非9704 FULL实测；v1 Submit4047s也沿旧参考。单次HTTP600s、Repository读取300s、快照/哈希3600s各自可能先触发，辅助9000s只是规划余量，并非所有helper最坏上限之和。后续STRESS、分段旁证与04收尾启动前分别核实操作、局部I/O、外层及清理预算，不能仅放大总截止；当前在途FULL不修改或重启。

审核已查明当前工具的cold/healthy校验尚不支持普通FULL checkpoint恢复，且cold准备在Preview计时入口外执行。现在只记录条件方案，不为未发生的失败预跑或修改在途候选。若真实失败，先停止受影响运行并保全源，再沿DC66/DC80认证同9704产品、FULL manifest、原输入/镜像/卷摘要及失败前通过步骤，在新project/key上作必要的有限恢复接线：仅当Preview会实际重执行时进行cold准备，跳过已完成Preview时不再清缓存；保留来源条件/TTL，仅请求恢复边界后的checkpoint。healthy不满足时如实诊断，不改成none、不静默延长TTL或增加通用skip；仍无法证明证据沿用时提出具体问题。既有实施者与接续审核者直接闭环最小bench修正、必要focused和恢复资格，不以当前validator限制盲目重跑全部前缀，也不新增Owner/逐摘要GO。

## B：保留单一修复版本的完整正式基准（未选）

将目标产品固定为 `9704`，在 CT108 按原口径重新取得所有实际受共享 runtime/RS/JCS 修复影响的场景计时；无法证明未受影响的既有旅程不沿用为该目标产品的结果。不使用缺失正式来源资格的诊断 checkpoint 冒充 carried。

同样复用合格的 SQL 输入、缓存及已验证工具，不重生成数据；按影响面进行必要门禁及计时，不无依据加矩阵。代价是多档长旅程，需要更多计算时间，目前不提供无证据的完成估计。纯工具或确实不受影响的结果仍按原规则独立判定，无需一律重跑。

## Owner A 选择后的直接执行方式

**2026-11-08 Owner组织调整：** Owner已明确授权本设计会话作为协调主会话，采用短任务子agent并在合适节点交接，原实施会话直接终止。旧实施者`01a1b107-11ba-7681-a7cf-afb1591a67d2`已提交安全交接、确认无在途命令，并于01:35:14Z停止执行及归档；不再唤醒。当前三个独立子任务为`/root/p6_v5b_resume`、`/root/p6_record_finalize`、`/root/p6_gate_closeout`，分别仅负责V5b-only、记录/比较索引、两测试修正及最终H门禁，均使用GPT-6.1-SOL/xhigh。机械工具任务默认Luna/max；新增范围或不同角色/模型仍须按Owner要求沟通，不自行扩大。

协调主会话负责当前事实、分工、设计决定与审核投递，不写产品或自判实施证据；现有独立审核会话及原阶段exit权限保持。子任务使用独立工作树/外部产物目录，本文旧“唯一实施者”按各任务唯一写入者解释，禁止并行改同一文件或被测worktree。子任务通过受管通信交小摘要和准确包路径，协调主会话统一通知既有审核；明确对应HEAD/来源的独审结果后按原授权接续，不再增加协调回执/GO。05按实际有效marker单飞，record与gate可内部沟通真实占用，不预留窗口。当前交接及任务状态索引位于`/home/dev/.local/state/gdds-p6-watch/coordinator-handoff-20261108.md`；原2小时巡检仅更新检查对象，不改间隔或新建监控。历史日志/已审成果、原绝对预算及停止/DC80恢复边界全部保留，不因组织切换重测。

Owner 已明确交付口径及 A 的限定来源例外，§92 已通过本次 source→9704 关系、必要守护及关键预算。实施者完成必要工具、静态/focused、镜像/环境及运行前核对后，现场取锁直接执行首轮并顺序推进上述未完成范围，结果事后独审，不逐摘要申请 GO，不等新 Owner/设计回执；不再以“恢复关系待核”作为等待理由。普通接线/测试/文书修正沿 Owner 简化流程直接闭环。

**2026-11-07 Owner 连续完成授权：** 持续推进至本方案A的全部测量和收尾完成，不以单个场景PASS、handoff已提交或等待协调回执结束推进。唯一实施者与接续审核者按实际缺口直接闭环W4-FULL、W4-STRESS、正确性/分段旁证、record/SHA/comparator及04最终V_ref门禁；已完成场景不重跑，按已批准分版本来源报告。实施者维护逐项状态、实际来源和下一步，设计跟踪执行关系及未决设计问题；普通工具/测试/文书修正、必要定向验证和资源取得按既有授权直接接续，充分预算在运行前一次给足。

**并行收尾范围澄清（2026-11-07）：** 现在由同一唯一实施者在监控原CT108诊断进程的同时，直接并行推进既有04门禁及05记录收尾；旧交接基点“先只DC63/V5b”不再作为等待设计扩大范围的理由，不新增会话或角色。以已审`78000beb62e927190092e315135e7bc1cbdda615`为当前门禁候选：backend/worker在原获准CT201（heavy-dev-01）独立clean worktree按冻结pre-backend-image-exit/DC67整镜像流程构建新专用tag，经LAN传04，按config digest及全部有序DiffID核身份；RS仍在04使用官方精确预置base、离线/network-none流程构建当前候选专用tag，固定candidate/build-input/source-tree/lock后，按原权威入口在04运行全六包。CT05在独立clean worktree消费§127已审旁证和认证原run副本，生成标准record/SHA/comparator及分版本总索引；必要工具小修按原双方直接闭环，不为已关输入/场景增加重测。

04/05各自现场核空闲并原子取自有占用，收尾释放，无窗口预约或跨会话回执前置；保持CT108原进程、监控、预算、冻结tag及源卷，不并行正式产品计时、不重跑FULL/STRESS。各工作流的worktree/镜像在运行期间固定；若后续必要工具修正形成更晚最终候选，按原逐包闭包及镜像绑定规则收口，不写在途worktree或提前宣称当前候选门禁已通过。并行授权不包含新角色、push/tag、主线产品合入或阶段exit权限。

只有严重设计冲突/缺口、难以解决的情况或多轮修复仍无法完成等才暂停整体推进并向Owner给出具体事实及方案；实际产品、输入/身份、资源或守护异常仍先停受影响运行、保留证据，按DC80主动诊断、最小修复、独审和合格恢复，不原样盲重试，也不把局部停止变成整条任务无限等待。性能数值按既定参考/record-only口径如实报告，不自行转成硬性验收线。完成须逐项实测或有已批准来源、必要结果独审及最终汇总，不能以派生字段PASS代替；此授权不新增会话/角色、push/tag、main产品合入或阶段exit权限，不改变原2小时巡检及其停用条件。

b 的原卷、旧 source 原卷和所有证据保持只读保留；不能直接启动 b 的 successor，也不把旧GO当新执行许可。源输入/目标身份或必要守护实际不符仍停止该运行并按DC80诊断/最小修正；需新业务取舍、资源上限变化或无法满足本次已批准来源条件时，提出具体替代方案。未授权 main 产品合入、push/tag；阶段 exit 与定时巡检结束仍按 Owner 及既有角色范围另行办理。统一版本的完整正式基准未被宣称恢复，但 A 的分版本参考接续已授权，不得再以旧“所有测量 STOP/Owner未选择”快照阻塞。

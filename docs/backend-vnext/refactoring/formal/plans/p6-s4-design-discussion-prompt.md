# S4 补充设计与执行计划：新对话任务提示词

以下内容可整段复制到新对话。此任务先讨论设计，不开始产品实施或测试。

---

你是 `/home/dev/gateway-data-management-system` 的 Phase 6 S4「Submit 渲染直通」设计协调者。
本轮先补齐设计缺口，形成可独立审核、可分节实施的具体计划。**不要立即修改产品代码、启动验证、实施 S4，或把本提示词解释为实施放行。**
可以读取源码、Contract、证据及节点现场；可以更新 S4 职责内设计、kickoff、审核提示词与交接材料；不推送、不打 tag、不改写引用提交。
先根据仓库事实讨论；信息足够就提出明确建议，不重复询问已确认决策。只问会实质改变核心方案的少量阻塞问题。

## 一、已确认决策与真实起点

1. Owner 同意 **S4 设计并独审后，可以在 S3 尚未 exit 时提前实施**，与 S3 预约归因及临时增预算诊断逻辑并行；这是阶段顺序例外，不是 S3 通过、S4 立即开工或 S5 放行。S4 的具体设计和实施在本新对话讨论，先设计后审核，再核实施授权。
2. 五测试节点 `ct108-gw-dms-04`、`ct108-gw-dms-05`、`ct108-gw-dms`、`ct107-gw-dms-06`、`ct109-gw-dms-07` 均为 32 vCPU / 64 GiB，取消前后端、门禁、真实数据、性能固定节点分工；执行时按空闲和原子标记选择合格节点。现有缓存、源 worktree carried、离线与工具链前提继续适用；不在开发机测试、编译或 lint。已知 04/06/07 同宿主，不当作五套独立硬件。
3. 生产资源仍为 **N1、单 active、32 GiB worker envelope、8 GiB reserve、M24 GiB**。临时大预算诊断的方向已认可，具体 M/envelope、执行稿和有效性口径尚未固定；不得据低 RSS 降低安全估算，或自行把临时参数变成生产默认。
4. Q18 独立后端补缺可先完成、可与 S3 补测共享验证窗口，不能塞为 S4 算法职责。已知实现候选 `a1ca3bad93a25cb47384a81fbc985075b1299c39` 在归档候选读响应加入权威 `review_version`；当前提示词整理时尚无专用节点验证结果。进新对话须核最新 handoff/独审，不能假定 FE3c 前置已解除。
5. S3 A–D 已独审 GO；E 固定产品 V=`774acf33a3f12eeccfbb440d9446ffde9c1c6d43`、H=`685c97f4e275e5e52b42ea403a07a5e96b0695b2`、独审报告提交 `0bf64540389e13b80735b483e1b9616bf8dca1e0`，结论 **BLOCKED_CAPACITY**，不是 S3 exit。不要重做已核收的 A–D 或重开 S3 kickoff 审核。
6. 最新 main 可能含并行前端/文档/Q18提交。先核 status、staged/untracked、提交区间、worktree、tags、现有角色及节点有效占用，区分实际 S3/S4 增量；不 reset/restore 他人文件，不回退 main 到历史设计起点。

## 二、必读与事实核对

完整阅读相关章节和最新追加结论，不能只读旧状态或文件开头：

- `AGENTS.md`、`docs/backend-vnext/testing-conventions.md`。
- `docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md`、`rust-safety-and-performance-policy.md`。
- 同 plans 目录的 `p6-design.md`（尤其 §4.3、§10、§14–§16）、`p6-execution-plan.md`、`p6-s0-owner-decisions.md`（DC45、DC55、DC57、DC78、DC91–DC93）。
- `p6-s3-s4-parallel-plan.md`、`p6-s3-candidate-handoff.md`、`p6-s3-e-capacity-stop.md`、`p6-s3-e-review.md` 最新结论、`p6-s3-coordination.md` §16 及最新追加。
- S3 `p6-s3-design.md`、`p6-s3-kickoff.md` 及 A–D handoff/review，按实际共享接口追读；S2b 规范表读写/预算最终 handoff 与 review。
- `p6-s1a-handoff.md`、`p6-s1a-independent-review.md`、S1a 阈值/分批冻结的直接原件；文件名若不同先用 `rg --files` 确认，不能猜不存在的结论。
- `p6-be-q18-handoff.md`、`p6-be-q18-review.md`；前端最新 FE3c kickoff/评估只核接口与职责，不修改前端产品。
- Owning Contract：`formal/contracts/storage-mutation-and-change-set.md`、`canonical-storage-and-repository-boundary.md`、`shared-canonical-encoding.md`、`performance-measurement-and-baseline.md`，以及实际引用的 repository import、operation lifecycle、artifact、Submit 恢复/保护条款和 ADR 0014。路径在 `docs/backend-vnext/` 下按仓库实际定位。

源码优先核：

- `vnext/backend/src/gateway_backend/infrastructure/repository_write/import_publication.py`。
- `capabilities/mutation_planning/`、`capabilities/storage_projection/`（含 import replay）、`application/submission/`、`application/submit_jobs.py`；相对上述 backend package。
- `capabilities/table_access/kernel.py` 的操作预算/资源 owner、canonical mmap/Arrow 实际读取、Rust comparison 公共入口与存储键表达。
- `vnext/rust/` 当前 core/Python adapter 分层及共享线程池/取消/截止/预算接口。
- 当前 replay renderer、固定 SQL 向量、Submit 计数、打包/发布/恢复与 Compose 的实际消费者测试；先列消费者再决定删除范围。

## 三、必须基于的容量事实

原 W3 MODIFIED_ONLY warm 在 **基线 v1 Submit** 被 `OperationMemoryBudget.ensure` 拒绝：`RESOURCE_LIMIT_EXCEEDED` / `operation memory reservation exceeded`；v1 Archive 和受测 v2 比较尚未到。不是已证物理 OOM，也不能用 v1 Preview 114.783 秒替代 W3 READY。
原证据未观测首次拒绝的 stage、具体表、requested/live 数值；相关高水与实际占用不能跨 operation 混用。

当前 Submit 约 2.469 GiB replay 预约与按表 Python 行/索引/变化集上界并存，后者可能留到 operation 结束。代码存在
`logical_size_bytes*32 + rows*(columns*1024 + 2048 + name_bytes*64) + 64KiB`
这一估算；仅凭它可提出机制假设，不能认定首个抛点、重复预约或不安全系数。
此前 20.338 GiB DDL 粗估未经独立复算，不作为选新 M 的依据。
W3/W4 共用 v1 输入；W3 FULL、W4 MO/FULL 和 100% 压力的后续样本未运行/受阻，不是已测通过，也没有合格 1 预热+3 次统计。

故障原件/只读诊断与 SHA 在容量报告；封存状态路径为
`/home/dev/gdds-test-tmp/p6-s3-e-tool-final-774acf33a3/w3-capacity-preserved-state/stopped-volumes.tar`（CT108），不得改写或拿它冒 fresh 旅程。
保留 04 当前 carried 来源 worktree 及环境/镜像至实际阶段退出。原冻结基准资源、golden、真实输入不接管、不清理。

## 四、需要补齐的 S4 设计问题

请逐项给出“当前实现证据 → 缺口 → 推荐方案/替代方案 → owning 接口 → 验证与停止条件”，对未知明确标记，不能把设想写成已实现：

1. **存储 diff 的业务定义与共用内核边界。** storage key 与前端 effective compare key、完整 persisted 列与 comparison 共有列/结构过滤不同；ordered 的 gid/no、keyless、schema/投影变化如何处理？不得直接把前端 records 作为 mutation source，也不得为复用删内部身份字段。哪些 S3 组件能复用，哪些需一个明确的 storage task/view？
2. **表级规划与渲染直通。** NOOP/PATCH_DML/REBUILD_TABLE 由谁决定，如何从冻结 IPC/mmap 到 Rust 确定性 SQL 流；生产路径删除哪些逐行 Python ChangeSet、摘要、回读或全表复制？逐项列真实消费者，不误删通用 planner/外部目标 ChangeSet、替换规划器或独立 metadata 路径，不增加第二套生产 fallback/部署开关。
3. **SQL 字节与独立预期。** 固定表/列/阶段/key顺序、DELETE→UPDATE→INSERT、重建语句、literal escaping、NULL/二进制/JSON/DECIMAL/时间/Unicode及不支持类型的边界；复用已有冻结 SQL/golden 和独立业务断言，不用新 Rust 输出反填 expected。完整语句 UTF-8 大小计算必须支持增量累计，避免每加一行重渲染整批。
4. **冻结阈值与打包边界。** PATCH 同时满足 1,000 行和 1% 等现有 eligibility；INSERT/UPDATE/DELETE 每条最多 256 行、多行最多 4 MiB，包含完整前缀/分隔符/值/`;\n`；单行超 4 MiB 单独成句。最终 replay artifact 200 MiB admission 保留，超限拒绝而非拆包/fallback。S4 默认逐字节不变，若必须改阈值/golden先停并交 Owner。
5. **端到端内存与 owner 生命周期。** 画出规划、mmap/Arrow、索引、diff、渲染 buffer、writer/包、发布/校验的同时驻留与释放点，明确 FFI 借用/拥有、失败/取消/截止/panic 收尾和最后消费者。复用 worker 共享池、N/M 准入，不建独立计算服务、通用缓存框架或新恢复状态机；不以 mmap 自动等于零预算、低 RSS 等于安全。设计需可在原 N1/32-8/M24 校准并解释容量改善来源。
6. **事务、恢复与发布语义。** expected-parent CAS、parent 行数/raw digest 校验、STRUCTURAL validation、PREPARED 前后、冻结导入包身份、保护引用/释放及现有恢复边界逐项沿用。直接渲染不能绕过真实 Submit/审核/Archive，Submit 不提前推进业务 BaselineHead。不要为内部优化重做 durable 状态机。
7. **S3 预约故障与诊断接口。** 如何用实际 canonical descriptors 和现有 stage_admissions/high-water 定位必要驻留/重复计费/过度保守/释放迟延；S3-only 最小诊断与 S4 优化如何分工？临时增预算准备/原预算计时或换 worker 如另设场景，必须显式标识，不暗改原 same-worker 守卫或宣称原 M24 全旅程通过。
8. **比较、Submit 与性能归因。** 分开 storage diff、SQL 编码、包写/校验、Repository import、step 等待及端到端 main 前移，记录调用/读取/跳表计数和资源账本/RSS/磁盘。含 S4 的联合候选不能倒签原 S3 V 或把 Submit 改善归于 S3 比较。W2 无行比较，不计 S3 比较收益。
9. **并行与验收依赖。** S3 补测候选、S4 实施候选、独立 Q18 与最终联合候选如何固定；同文件写入序列、测试 WT 禁写、适用 evidence carried、镜像与逐包闭包绑定、真实数据范围 DC33 确认、S3/S4 exit 各自未决如何交接？S5 前置不变。

## 五、具体执行计划的交付要求

先报告实际起点、已确认事实、真正阻塞决策及推荐方向，再完成以下文档（名称可按仓库现有同类材料调整，避免重复建同义文档）：

- `p6-s4-design.md`：上述缺口、数据流/资源生命周期、冻结语义与明确非目标、消费者与删除清单、Contract 所属。
- `p6-s4-kickoff.md`：可独立交付的小节、每节输入/输出和依赖、显式路径归属、验收标准、focused 范围、角色与提交/独审时序、集中验证及 DC33 待确认范围。
- `p6-s4-review-prompt.md`：独立审核固定候选与检查点；审核者不得是设计/实施者自己。
- 更新必要的执行计划与协调交接引用，保留历史结论，不把 S3 BLOCKED_CAPACITY 改成通过。

建议评估的分节是：A 语义/接口/独立向量；B 存储 diff 与表级规划；C Rust SQL 流与精确分批；D 生产接线/资源生命周期/旧实现删除；E 固定最终候选、集中证据与累计退出交接。这只是讨论起点，须按实际代码耦合决定，不机械拆散同一事务或资源不变量。

每节安排“实施与 focused → 固定候选 → 独审 → 修复/原审复审 → 适用证据核收 → 下一节”。
最终代码独审收敛后才集中跑必要权威包/容器/真实数据，按影响闭包决定运行或合格沿用，不每节重复全 runner/完整旅程。保留 S1a 独立 replay 字节预期、真实 Dolt 表结果、CAS/恢复和资源断言。
临时大预算、原配置功能容量、性能目标、压力档及未知分列；正式统计同组 1 预热+3 次、给中位数/范围，失败不变成功。

当前工具最多 4 个活跃槽（含协调者）。设计材料准备妥后可创建独立设计审核者：Sol xhigh（复杂语义/FFI/资源可 max），固定 detached WT 审核；不递归扩队。
后续实施者 Sol xhigh，机械执行/测试 Luna max；测试脚本先固定审核、每次运行只有一位责任人，测试中不写被测 WT。
本轮不启动测试或产品实施；若补充设计讨论出现改变 SQL/Contract/golden/生产预算/FE接口/恢复边界的需要，清楚列方案和推荐交 Owner，不能以普通优化自行放宽。

最后给出：设计缺口是否闭合、固定设计候选/独审状态、待 Owner 决策项、具体实施计划及新对话下一步。不要仅给泛泛路线图，也不要在设计未讨论/独审前宣布可开工。

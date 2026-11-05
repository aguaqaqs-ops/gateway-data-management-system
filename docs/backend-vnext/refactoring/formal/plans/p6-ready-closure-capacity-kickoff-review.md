# Phase 6 READY 闭包容量修正范围审核

- 结论：**范围设计通过，无阻塞性设计缺项；容量定值尚待补齐并定向审核，不代表产品代码通过或恢复条件已满足。**
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 候选：`463f53765d809f3a5616191995d96548f955ed18`。
- 对象：DC80、[容量修正 kickoff](p6-ready-closure-capacity-kickoff.md) 全文及执行计划对应安排；对照 DC64/DC66、AGENTS 和既有 READY closure 边界。本报告与 W4 停止证据复核分开，不代判失败日志、实际引用数或快照恢复资格。
- 方法：在 `/home/dev/gdds-p6-capacity-scope-463f5376` detached worktree 只读审核，程序核对完整 HEAD、detached 与 clean 状态；未访问测试节点、运行测试或启动产品。

## 1. 范围判断

| 核对项 | 结论 |
| --- | --- |
| 授权与停止 | DC80 明确受影响运行先停止，诊断、最小修复设计和审核继续；本次恢复明确例外于冻结产品、DC66 同产品镜像和 DC64 共享设施变更的默认整档要求，不泛化为任意产品差异可续跑。条件满足后无需再次请求 owner 确认。 |
| 产品边界 | 从冻结产品独立分支起步，仅改 READY closure 有界容量及对应测试；prior-output、inline payload、schema、格式、版本、排序、JCS/digest 和输出集合均不得改变。其他必要变化先交设计确定影响面。 |
| 容量前提 | 先核对实际 refs 构成、去重结果、文档字节规模及剩余批准场景上界；未落盘的实际值不能用推导值冒充。数值补入设计并独立审核后才实施。尚未确定数值是明确的后续门槛，不是已获认可的容量预算。 |
| 验证顺序 | 05 focused 与五包静态 → 代码审核 → 04 实际恢复候选的 backend 权威包及容器门禁 → H 镜像身份核对 → 恢复资格审核。旧边界内规范字节、扩容区间 round-trip、新边界/超限与既有完整性屏障均有要求。未要求无差别重跑全部基准。 |
| 身份例外 | 来源 V′ 按原证据核验，目标 H 按新提交及镜像身份核验；产品和镜像两项校验同时表达精确 V→H 关系，不将不同镜像报为 MATCH，不提供通用忽略开关。 |
| 快照与沿用 | 仅从指定失败运行的 v2-preview 前快照复制三卷，复制后校验摘要；新项目、新证据目录，运行该步及全部后续步骤。源证据、原卷和失败末态不改写。旧成功步骤须有可核验的未受影响依据；计时受影响即在 H 实测，record 逐步骤保留真实来源。 |

## 2. Contract 与比例化边界

READY closure 的 owning 边界见 [P4 runtime 设计](p4-durable-operation-runtime-design.md) 的 READY closure 定义和 [R4 执行计划 §9](p4-r4-jobdefinition-checkpoint-execution-plan.md#9-p4-r4-s2a--artifact-checkpoint-and-ready-closure-contract)：有序 exact ArtifactRefs、size/raw digest、版本轴、完整性验证及一次性 CAS publication。Operation Contract 拥有 ReadyClosureRef，application 拥有 job-specific payload/step 语义。

候选 `checkpoints.py` 与冻结产品对应文件的 Git blob 经程序比较相同；当前读写使用同一 READY refs 上限。该 4096 refs 上限不同于 Operation Lifecycle Contract 的 inline JSON aggregate 4096，不能借本次修正修改后者。容量接受范围扩大必须有预算，但不自动等同于 schema、序列化或摘要算法变化；这些不变条件仍须在代码审核验证。

## 3. 后续审核点

当前没有必须交设计会话修订的实质缺项。按现有文本继续完成 refs 计数与容量预算，补入具体有限值及依据后作短范围补审；随后分别审核产品修正、benchmark 限定恢复接线及最终恢复条件。实际计数、候选 SHA、新镜像和原快照匹配事实未齐备前，不将本报告作为恢复放行结论。

本轮仅文档范围审核，不触发镜像重建；没有 H 的 image revision/source-tree 或门禁结果可沿用。实施候选按 kickoff 完成新镜像与容器验证。候选文档 `git diff --check` 通过；本报告未改产品或设计正文，未推送、未合入产品、未办理 exit。

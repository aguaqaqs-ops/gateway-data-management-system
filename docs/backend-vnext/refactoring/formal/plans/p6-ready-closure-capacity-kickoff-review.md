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

## 4. 容量定值补审（2026-11-05）

**结论：补审通过，READY output refs 上限定为 32,768，可按 kickoff 进入产品修复实施；不是恢复放行。** 本节更新第 3 节的容量待补状态，范围边界不变。补审候选为 `160af3428d73766f20045355e4030d250cff6807`，在 `/home/dev/gdds-p6-capacity-budget-160af342` detached worktree 核对 HEAD 和 clean 状态。

静态核对冻结产品的 Preview/History refs 收集、surface refs 枚举、snapshot artifact 创建/读回路径：每 pair 最多 5 个根引用，每表 9 个普通引用和 2 个 ordered 引用，每 projection 3 项。当前 builder 固定无 projection，snapshot 创建单项 rowfile tuple，读回拒绝非单项，包含 Repository baseline 物化路径。Preview 固定项最多 4；History 固定项为 1。相关六个源码文件与冻结产品 Git blob 经程序比较一致。

各 side 最多 639 表，pair 表集合取两侧之和作为保守并集界 1,278，不要求精确同名并集取证。最多三 side、两 pair 时，程序复算 FULL Preview 为 31,964，History 为 28,127，分别距 32,768 余 804、4,641；标准 W4/STRESS 的两 side、一 pair 界为 16,623。新增表、分片、projection 或更多 pair 不在此证明范围。

字节预算曾发现两份 DigestRef 遗漏 `sha256:` 前缀，已交设计修订；候选 `160af3428d` 已关闭该项。按真实 entry shape、128 字节 ASCII ID、64 字节固定 media type、16 位 size、两份各 71 字节 DigestRef，静态复算每项 477 字节，含分隔符及预留文档头为 `(477+1)×32768+1024 = 15,664,128` 字节，约 14.938 MiB。核对的 11 个相关固定 media 常量最大 55 字节，均为无需 JSON 转义的 ASCII；identity producer 为固定 `application/json`。当前 READY 收集路径未把调用者任意 media 作为新增输出，持久引用仍依原完整性和来源绑定校验。该预算不新增通用 media/字节限制，不代表峰值 RSS，也不替代既有独立 surface/bundle 限制。

证据复核采用只读 SSH，不取节点占用标记、不启动产品或测试：

- 校正诊断日志 `/home/dev/gdds-p6-logs/baseline/monitor/w4-ready-closure-capacity-20261105c.log` 的 SHA256 重算匹配 `df571d860d8ac6220c37884bd228067c06fd3a031d06520b32dc124f3aed670c`。
- 直接读取当前输入根 `w4-generator-correction-20261105b`，input-summary SHA256 为 `6b63cf2e8c58cadc96b7ac716a523f9b5554fcb496eea16c0c2f5089199a3896`。其 2×、W4-100%、W4-10% census 均有 8/8 生产物化 COMPLETE、最大单侧 639 表、t4 两侧均 639；两份 W4 generator summary 均为 638 表、638 changed。三份 census SHA256 依次为 `4c05fd9f16256403494dabea7cb90ee7a797c4add29ffa584d466b033d2a73dd`、`29c1e25c3925040fe3b9020354581ccbcb838377776034302a4223869f445fe6`、`04952cb5523b9b6d44530654994bcad2a692a132697cacc2f157a7e8c66eea67`。
- 校正日志报告两份既有成功闭包为 2,528 refs/847,834 字节和 910 refs/282,866 字节，仅作样本，不充当新容量字节上界。失败 assemble state 未持久化，精确失败计数不可恢复；已核失败位置只证明去重后超过 4,096。不为此重跑 Preview。
- 独立重读原 run/state，实际均为 13 项 PASS，checkpoint 的 completed_through、卷摘要及快照路径全部相等；state 额外含步骤与耗时字段。初稿 0/0 和整对象不等来自错误取值/比较，不是原证据失败。当前 W4 census 与旧作废来源分开核验，不采用旧来源的 False。校正日志末句“before v2-upload completion”为文字笔误，真实起点为 `completed_through=v2-upload`，即 upload 完成后、preview 前；保留原日志，由 handoff 更正，不改证据。

旧成功步骤若有绑定固定旧产品/镜像、确实经过闭包构造或读回的成功证据，可依据旧代码强制 4,096 上限证明未触发容量限制，不要求逐历史闭包重数；不经过闭包的步骤按 diff→step 映射证明。此处认可证据粒度，逐步骤沿用和快照恢复资格另行审核。后续仍依序完成产品与限定工具代码审核、05 验证、04 backend/容器门禁、新镜像身份及恢复条件核对；不重复请求 owner 授权。

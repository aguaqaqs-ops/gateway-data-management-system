# Phase 6 READY 闭包容量修正与限定续跑

状态：2026-11-05，owner 已要求继续排查解决并主动处置后续暂停，授权来源见 DC80。范围与容量定值已通过[独立审核](p6-ready-closure-capacity-kickoff-review.md)（范围 `fcfd19b946`，定值 `f1d860580e`、顺序澄清 `6ecfb6a36d`）。READY 上限定为 32,768，已交独立产品任务实施；本结论不代表产品修复或快照恢复已通过门禁。

## 1. 问题与结果目标

W4/S4/H1 场景 `p6bw4s4h120261105a` 在 `v2-preview` 报 `operation.pure_recompute_failed`。底层为 `ReadyClosureDocument.build` 拒绝超过 4096 个 output refs，堆栈经过 Preview assemble 与 `prepare_ready_closure`。现有路径在 build 前已经去重；不能把本次错误直接解释为漏做去重。实际引用数与类别由实施者从保留元数据核对，不为取得计数重跑整段 Preview。

目标是让当前已批准输入规模的完整 READY 闭包在有限预算内正常生成、读回和发布，并从经核验的失败前快照完成剩余旅程。不得丢引用、改输入或跳过完整性检查以绕过错误；四路输入生成不解决本次产品容量问题。

## 2. 分工与代码边界

产品修正在独立短期分支从冻结产品 `9f288ad50475030ddb496ad00b3b79f4abdc0082` 起步，仅拥有 `vnext/backend/src/gateway_backend/application/checkpoints.py` 中 READY closure 容量边界、相应 checkpoint/closure focused 测试和独立 handoff。不得修改 prior-output 上限、inline payload 限制、schema、持久格式、版本、排序/JCS/digest、输出集、生成/比较算法、锁文件或 Dockerfile。若检查发现其他必需修正，先回设计明确影响面，不悄悄扩项。

基准实施者继续负责实际 refs 计数、原证据保留、benchmarks 的限定续跑接线、镜像与节点准备和实际旅程；不得与独立产品任务同时修改产品文件。产品修正通过后，以同一窄修正分别纳入 main 和 baseline，避免把全部未退出的 baseline 工具提前并入 main。设计维护 DC、本文与计划正文，审核者判断代码/证据/恢复资格。测试只在专用节点；05 当前可能有前端独立工作，必须等其释放并原子取得自有占用。

## 3. 容量与证明

先核对失败输入的引用构成、去重后实际数量及引用文档字节规模，并对剩余 W4-FULL、W4-STRESS 与已批准多节点 History 说明覆盖范围。若某项实际状态没有落盘，明确标注推导上界与假设，不伪造实际计数。新上限取能够覆盖这些场景的明确有限值，不能简单去掉限制或按全机器内存无界放大；具体定值与独立审核依据见下文。

容量定值为 **32,768 个 READY output refs**，仅扩大该数量边界。依据当前生产结构，令 `T_side` 为某侧实际物化表数，`T_pair` 为某 pair 的 Surface 表集合数量（两侧表集合的并集，不直接等于任一侧表数），`P_pair` 为 projection 数量：

- Preview 保守界：`4 + 2 × ΣT_side + Σpair(5 + 11 × T_pair + 3 × P_pair)`。固定部分最多 4 项；每侧每表为 manifest 与单 rowfile 两项；每 pair 最多 5 个全局 ref，每表最多 9 个普通 ref 与 2 个 ordered ref，每 projection 最多 3 项。去重只会减少数量。
- History 保守界：`1 + Σpair(5 + 11 × T_pair + 3 × P_pair)`。
- 当前获准场景至多三侧、两 pair，当前 builder 的 `projections=()`；各侧最多 639 表时，可直接取 `T_pair ≤ 1,278`，不依赖各侧表名相同。FULL Preview 上界为 **31,964**，两 pair History 上界为 **28,127**，分别低于候选上限 804 和 4,641 项。W4-STRESS 只增行数、不增表数；单 rowfile 前提须包括 baseline 导入侧。新增表、分片 rowfile、projection 或更多节点必须重算，不能把本次容量证明泛化到任意输入。
- 实施者已报告 W4 10%/100% summary 各 638 表、t4 v1/v2 census 各 639 表，以及原成功 v1 闭包 2,528/910 refs。失败 assemble state 未持久化，实际失败数量不可恢复，只能确定超过 4,096。上述报告值须绑定诊断日志及 SHA，由审核者独立复核；不为取得失败精确值重跑 Preview。

字节预算限定当前 producer 的固定 ASCII media type（保守按不超过 64 字节）、ArtifactRef 既有 ASCII ID 上限 128 字节、I-JSON size 上限的 16 位十进制整数、两份各 71 字节 DigestRef（`sha256:` 前缀加 64 位 hex），以及当前固定 job contract version。按现有 entry JSON shape，每项最多 477 字节；计入分隔逗号、32,768 项和宽松 1,024 字节文档头，预算为 **15,664,128 字节（约 14.938 MiB）**。这是当前获准路径的序列化预算，须核实实际 producer/media 来源；不是任意 ArtifactRef 的通用字节上界，不新增 media type 限制或 READY 字节 cap，也不等同于解析/JCS 的峰值内存。既有成功闭包的实际 bytes 仅作对照样本。独立的 surface/bundle 16 MiB 限制保持不变，不与 READY 文档混用。

定值补审只需核实上述输入/单 rowfile/producer 前提和日志出处，不要求重扫全部历史卷或精确还原未落盘的失败集合。前提与预算已在审核报告 §4 核实，按 32,768 实施。诊断日志为 `/home/dev/gdds-p6-logs/baseline/monitor/w4-ready-closure-capacity-20261105c.log`，SHA256 为 `df571d860d8ac6220c37884bd228067c06fd3a031d06520b32dc124f3aed670c`；原始初稿的取值/比较问题、旧作废 census 和末行 checkpoint 时点笔误保留在日志并由 handoff 解释，校正与来源复核见审核报告。如后续新增输入使任一前提不成立，先修正本节的容量推导。

保持 read/write 同一容量规则；既有版本、closed shape、排序、唯一 ref、size/digest、missing/corrupt 和 set-once/CAS 检查继续有效。用有界 fixtures 验证旧上限以内的规范字节不变、超过旧上限但在新上限内的合法闭包可 round-trip、恰达新边界与超限拒绝。复用已有不变量测试，不复制全量业务矩阵，不增加新的持久恢复机制。

05 clean 已提交候选跑相关 focused 与五包 Ruff/mypy，固定代码与 handoff 交代码审核。通过后在 04 对实际恢复候选运行受影响 backend 包及其容器门禁；按原 DC67 旧产品整镜像流程从 CT201 构建、LAN 传输，核 config digest 与全部 DiffID，不能复用旧 V′ 镜像冒充 H。无依赖变更时沿用已填充缓存；最终 runner 的沿用仍按现有包闭包与镜像等价规则判定。

## 4. 本次限定的跨修正恢复

来源仅为该失败运行 `v2-preview` 前、`completed_through=v2-upload` 的 checkpoint。run/state 必须有结束时间、exit/failure，前 13 项检查全部 PASS，三卷快照实物摘要匹配；原输入 manifest/census/accepted summary、原镜像和源产品身份逐项保持绑定。已有审核核对只能引用其真实报告，不用人工改 state 来满足校验。

在具体 V/H 固定后，程序证明除批准容量修正及 benchmark 工具/测试/docs 外产品无变化；给出旧成功步骤的实际 refs 计数或其他可核验的未受影响依据。通用续跑校验目前同时要求产品一致和镜像一致，因此两项都须扩展为本次精确的 V→H 关系：来源仍按自己的 V′/原日志核验，目标按批准 H 及新镜像身份核验。禁止通用 `skip identity` 或任意允许产品差异的入口，也不把两个不同镜像报告为 MATCH。

目标用新 project、新 evidence 根、新幂等键，从核验快照复制三卷；复制后再核摘要。只恢复 `v2-preview` 及后续全部步骤，失败末态不作源；之前步骤明确引用原始运行的 HEAD/log，之后步骤绑定 H。按照 DC80 限定例外恢复，不修改原证据/原卷，不补造新版本下已执行的历史事实。

受影响计时在 H 实测；既有场景只在审核能证明未受本修正影响时沿用。新基准 record 与后续对照保留精确产品/镜像/步骤来源；若原计时工具无法表达该关系，先做必要的最小工具修正，不写虚假的统一版本。恢复条件审过即可由原实施者执行，无需再等一次 owner 催办。

## 5. 后续暂停的主动处置

暂停首先阻止继续使用可疑结果，并不阻止只读诊断、保存证据、最小修复设计、定向实现与审核。实施者发现问题后及时发送具体异常和已知影响，设计/审核直接协作推进；有可执行的获准下一步就继续。涉及新的业务取舍、不可逆处置或无法满足限定恢复条件时，给 owner 具体方案和影响，不只发送“等待处置”。巡检继续每 2 小时核对进展，不强迫越过实际安全或一致性边界。

## 6. 最终恢复核验的现有会话接续（2026-11-05）

原审核会话 `01a1a44e-9dfe-7971-9a7f-4b2bc6614c44` 明确当前用户任务限于 BE-a kickoff，不能受理本次新增恢复证据核验；其此前已提交的基准审核结论保留，不覆盖该会话当前指令。设计按 DC80 主动协调现有会话接续，避免把职责冲突变成无限等待。已有 S1b 独立审核会话 `01a182d8-4dfd-7441-b9db-4deefdc4e0ac` 已确认原任务完成、无冲突，可在原会话承接有限终核；不新建会话。

此次接续仅核定候选 `e798ec87a37330250b0c051162e7962dba1daa60` 是否满足本 kickoff 的恢复条件，并给出明确 GO 或具体阻塞项。交接提交为 `5730ef68584cf99423cfb95a8fbb9b1f2d7c41e0`，位于 `p6-baseline`；最终准备及 04 闭包证据根为 `/home/dev/gdds-p6-logs/baseline/scenarios/capacity-resume-h-20261105/`。复用 main 中容量设计/产品代码/工具代码/停止复核/04 环境修复审核；只读核验修正后 04 成功 runner 与 manifest、同一 worktree 到 e798 的 backend 闭包沿用、固定 approval JSON 和 CT108 H/RS/源 checkpoint 身份。来源三卷已审，不再重复全卷哈希；运行时目标复制后的校验仍由已审旅程执行。

临时审核者不跑测试或测量、不改产品/设计正文、不修改既有证据、不推送；只写自己的限定恢复审核报告，不重审已经通过的无关场景，不接管基准 exit 或 S2a exit。结论直接发原实施者 `01a193fa-ecf4-7782-b6e1-430856f414ea` 并抄设计；若当前任务禁止直接通信，可在 final 给完整结论，由设计读取转交。明确 GO 后实施者直接启动固定 runbook 中的新项目/新卷副本恢复，不另等设计或 owner 确认；任何实际未满足条件仍以具体缺口处理。此接续改变审核分工，不降低恢复条件，也不把设计会话变为证据裁决者。

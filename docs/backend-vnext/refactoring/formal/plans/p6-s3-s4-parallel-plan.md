# S3 补测、S4 顺序例外与 Q18：决策和新对话交接

日期：2026-11-08。本文记录 Owner 本轮决策与执行约束，不是 S4 详细设计、开工稿或通过报告。
Owner 随后明确：**S4 的设计和实施在新对话进行，本对话仅作合理性判断与决策。**
新对话入口见 [S4 设计讨论任务提示词](p6-s4-design-discussion-prompt.md)。

## 1. 判断与已确认边界

方向可行：Q18 可先独立交付；S4 设计完成并独审后提前实施，与 S3 预约归因及条件性增预算诊断逻辑并行。
S3 的未知首次拒绝点不能先命名为算法故障，低 RSS 也不能证明预约上界可以安全降低。
生产仍为 N1、单 active、32 GiB worker envelope、8 GiB reserve、M24 GiB。
Owner 对临时增预算测试方向的认可，不指定具体新 M，也不构成提高生产预算或修改正式验收场景的授权。

S3 原产品 V=`774acf33a3f12eeccfbb440d9446ffde9c1c6d43`、H=`685c97f4e275e5e52b42ea403a07a5e96b0695b2`、
独审报告 `0bf64540389e13b80735b483e1b9616bf8dca1e0` 保持 **BLOCKED_CAPACITY**。
完整事实与来源见 [累计候选交接](p6-s3-candidate-handoff.md) 和 [容量停止报告](p6-s3-e-capacity-stop.md)。
提前 S4 不等于 S3 exit，不放宽 S5 的 S3/S4 exit 前置，也不授权 tag、push 或改写引用提交。

## 2. 三条工作线的顺序

| 工作线 | 下一步 | 交付条件 |
| --- | --- | --- |
| 独立 BE-Q18 | 固定接口修复，代码独审、focused、静态及适用容器验证 | archive-only 从候选响应取得真实 review_version，CAS/权限/幂等不变；前端收到固定后端结果后刷新类型和 mock |
| S3 容量诊断与补测 | 先定位拒绝阶段和完整预约生命周期，再固定临时参数与执行稿 | 原失败保留；增预算结果按实际条件报告，不替代 M24 原场景或宣称性能通过 |
| S4（新对话） | 补设计缺口、固定可执行 kickoff、独立设计审核；随后依新对话授权实施 | SQL 字节、阈值、批量、计数、资源和恢复边界明确，逐节实现/独审，最终集中验证 |

Q18 当前实现候选为 `a1ca3bad93a25cb47384a81fbc985075b1299c39`，尚无节点验证结果。
见 [Q18 handoff](p6-be-q18-handoff.md)；不能把已有候选等同于 FE3c 前置已解除。
生成时间问题沿用 S3 协调 §16 的源码口径与前端修订预期，不为减少异常数量改变业务语义。

## 3. 预约诊断与临时大预算的具体边界

1. 先核 `OperationMemoryBudget` 的实际 stage、requested/live/limit、高水与 owner 释放；以当前 canonical descriptor 为输入核算，不能用未经核收的 DDL 粗估选新 M。现有 `stage_admissions` 和 `high_water_bytes` 可复用，必要的最小临时诊断不发展为通用监控/持久 evidence 机制。
2. 区分保守估算偏差、重复预约、必要同时驻留与 owner 延迟释放。只对已证实且职责内的问题修复；迁移 Submit 算法按 S4 审核，不伪装成 S3 普通 finding。
3. 在 64 GiB guest 内明确 worker hard limit、reserve、Repository Service、系统及工具余量，才选择有限的新参数。不得给 worker 分配全部 64 GiB 后再忽略其余进程，不机械复制旧 64 GiB worker 档。
4. 固定诊断候选、输入、资源参数与执行稿并独审后执行，原失败及每次实际 exit 保留。首失败先停止；DC68 三轮自主修复只用于已确定工具根因，不能无修改试到成功。
5. 若准备阶段使用大预算、计时阶段改回 M24 或更换 worker，显式建立另条件场景，不能静默移除当前 driver 的同 worker 守卫或计为原完整旅程容量通过。正式口径若须变化，先交 Owner 决策。

## 4. 并行写入与归因

逻辑上可并行，不能让两名实施者同时修改同一生产文件。协调者维护文件归属和 main 提交次序；必要时按仓库规则用短期分支隔离，已引用提交不改写。
所有测试使用固定 clean detached worktree，测试期间不写入、不提交、不手工重 tag 镜像。

S3 归因使用不含 S4 改动的明确候选；Q18 属 API 扩展，仍列出独立增量及其受影响闭包。
若在含 S4 的联合候选补测，报告清楚产品区间，不把 Submit 改善归因为纯 S3 收益。
S4 新结果可作为后续共同候选的证据，但不能倒签原 S3 V 或抹去失败。
最终必要门禁按实际影响和合格来源绑定；同一权威 runner 已执行的 Compose 不重复运行。

角色仍最多四个活跃槽（含协调者）；三条逻辑工作线不表示同时创建三套实施/审核/测试团队。
实施者与独审者分离，同节修复由原审核者连续核收；测试只有一个执行责任人。

## 5. 统一节点池与清理

DC91 已将五节点改为统一池，各为 32 vCPU / 64 GiB，未来前后端/门禁/真实数据/性能不固定节点。
执行时核空闲并原子获取本节点标记；工具链、离线缓存及同节点 carried 条件不因配置一致而豁免。
正式样本同组同节点同配置，硬件调整前后分别报告。规范见 [AGENTS](../../../../../AGENTS.md) 与 [testing-conventions](../../../testing-conventions.md)。

本轮只读实核：五节点 BatchMode 均成功，`nproc=32`、MemTotal=`67,108,864 kB`；核对时标记缺席，未见运行中的 Docker 容器、8000 监听及目标测试进程。
这只是现场快照，不是后续预约或工具链全部就绪的证明。07 未见本次 backend dependency-base tag，04/05/CT108 的 SSH 默认 PATH 未包含 Cargo；实际执行仍需按规则显式设置 PATH、检查 selector 与缓存。
原件 `/home/dev/gdds-test-tmp/p6-node-pool-20261108/readonly-node-pool-audit.log`，UTC 15:32:32–15:35:55、exit0，
SHA256=`abc2f4ff632e8ebed6be6068f582302f79b1ae8f9a1d6d6b533637a0304c8d3d`。

Owner 授权一轮历史文件清理，本次只读核对**尚未删除文件**。后续先列明确白名单（路径、所属任务、派生性质、无运行者/无保留消费者、空间），在对应空闲节点取本人标记后执行，记录实际删除和前后空间。可重建且无消费者的旧编译 target 可优先核查；仅“时间较早”不足以认定可删。

至少保留：

- 04 carried 来源 worktree `/home/dev/gdds-test-tmp/p6-s3-e-final-3a7e088b2a/wt/subject` 及本地环境/镜像，直至实际阶段 exit 完成。
- 所有被引用成功/失败原始日志、manifest、捕获文件、真实输入与冻结原基准资源。
- CT108 未决 W3 故障归档 `/home/dev/gdds-test-tmp/p6-s3-e-tool-final-774acf33a3/w3-capacity-preserved-state/stopped-volumes.tar`，SHA256=`ba1b07d4e5d19824532f70a432dc0557cc7781904c26e4f1621a90a16cae4444`；保持私有权限。

不全局 Docker prune，不批量清理他人 worktree/卷，不接管原基准线；有保留归属不明的路径先跳过。

## 6. 本轮输出与后续

本轮输出是节点规则、顺序例外决议及可复制到新对话的设计任务提示词，不启动 S4 设计/实施或测试。
新对话先核实际 main、并行状态与 S3/Q18 最新证据，再进行 S4 设计讨论；不得因本文决策已确认就省略设计独审。

## 7. S4设计对话交接（2026-11-08，后续增补）

新对话从clean main `572359d3a7` 核查实际源码，已形成[S4设计](p6-s4-design.md)、[逐节kickoff](p6-s4-kickoff.md)及[独审提示词](p6-s4-review-prompt.md)。Owner已在DC94确认storage key独立判定、prepare checkpoint恢复分界/非INITIAL缺parent拒绝的文字澄清和S4真实数据范围；没有实施或运行授权。

建议实现为逐表native storage diff→Python表级policy→Rust精确SQL chunk，表后释放输入/索引；保有界DML字节汇集与原publisher，保持全部DDL先于DML。补齐旧256窗口分批、mutation排序hash和float拼写等隐藏字节约束。三线共享文件与候选隔离见kickoff§3，最终集中证据见§5–7。

设计固定候选和独审结论见随后S4设计审核报告；在报告核收前不宣布可开工。S3原V/H仍BLOCKED_CAPACITY，Q18仅静态CLEAR/证据待核；旧章节保留其当时事实。本轮只读节点快照不构成预约，未执行测试、清理、构建或真实旅程。

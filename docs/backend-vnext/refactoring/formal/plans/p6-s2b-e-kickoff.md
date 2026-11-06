# S2b E：唯一生产路径与阶段最终候选

状态：**设计准备；尚未启动实施**（2026-11-06）。DC86 已授权顺序推进，本节等待 D 的固定代码、handoff 与独立 GO；当前不创建 E 角色，不提前删除仍有生产消费者的实现。最终输入与实际改动范围在 D 结束后核实。

## 1. 消费者收口与删除

目标是已批准的唯一 Rust 批量路径 `parse → business validation/materialization → canonical projection/hash → IPC`。Python 保留业务 orchestration、ruleset、XML/AST/composite、small metadata/digest 以及真实 IO/恢复 owner；不为语言统一迁移这些职责，不删除仍有消费者的公共 row reader/DTO。

逐项核整体 kickoff §2 的消费者表，并以实际 import/call graph 补缺：上传 FULL 双侧、Preview baseline、History exact commit、repository-ref 两种 artifact policy、pair/identity/ordered 单侧读取、export/import-replay、Submit/T1/PREPARED 与恢复。D 已切的入口只复核差异，剩余入口在 E 替换；同一消费者不保留生产 fallback、旧格式双读或引擎开关。

删除被替代 Python 批量 materialize/projection/hash 实现及只服务其差分的入口、mock/probe。保留已确认的独立 fixed vectors/Contract：删除旧 oracle 前，将仍需保留的预期明确绑定到既有 Contract/golden/旧 oracle 已验证值，不能从新 Rust actual 反写 expected，也不为了测试长期保留第二套算法。按行为与 owner 保留测试，不按修复轮次复制测试矩阵。

内部 canonical IPC 与 raw/client Parquet 是不同用途；只删除被替代的内部规范表路径。面向客户端的 Parquet、通用 Repository row 访问、原始 SourcePackage 与外层 DDL/export layout 按其真实消费者保留。

## 2. 收敛与最终验证

日常在 06 对实际删除/迁移范围做 focused/Contract/差分残余检查、静态与必要容器验证。最终候选前收敛全部代码与测试；按 AGENTS 记录最后已验证 image revision/source tree、是否触发重建及理由。不每轮执行全量 runner、完整真实旅程或重新生成输入。

最终 S2b 候选必须覆盖：

- Mapping/业务摘要/诊断/特殊 catalog 与 FULL、MODIFIED_ONLY、DATASET_REPLACEMENT 正确性；W2 结构计数及内容命中不重写。
- IPC handle、强引用/TTL、Archive CAS、精确 commit 回填、T1/PREPARED 冻结，真实 worker cancel/drain/lease_lost/deadline 与资源拒绝。沿 A–D 已验证 owner 按最终差异核对，不机械重做所有中间测试。
- 04 权威 runner 与最终候选绑定的容器门禁；Rust 必须覆盖，其余包按同节点、同 worktree 的实际来源 V 和闭包规则判运行/沿用。包沿用和镜像身份等价分别判断；普通 06 focused 不能冒充 04 来源。
- t1–t3 在 05、t4 在 CT108 完成改动面内的 Preview/History/Submit 生产路径正确性。CT108 忙时协调窗口；若要换节点，先向 Owner 给出具体替代方案并取得授权，不能以性能延期豁免 t4。

各节点分别按有效占用、clean committed worktree、离线缓存和日志规则执行；正式测试不在开发机运行。runner 非零先停并处理失败，不接着计算 carried；最终门禁提交固定后不在运行中修改 worktree、提交或手工 retag 镜像。保留 04 门禁 worktree 至阶段退出合入，以便同节点同 worktree 判等。

## 3. 退出记录与后续性能复核

E handoff 将最终产品候选、删除/保留清单、逐包来源与闭包、容器 provenance、t1–t4、容量/N/M 配置、恢复/控制证据、未决问题集中交独立审核。设计会话不能自行判实施证据。S2b 的阶段退出记录与附注 tag 按既有退出流程办理，不推送、不改写被审核引用的提交。

W2 30 秒目标及口径保留，完整路径测量最迟 S6；W1 无 CT108 窗口时同样最迟 S6；W3 从 S3 起按原设计取证。未知数值保持 unknown，功能退出不写性能 PASS。原 W4 租约故障由原线跟踪，若当前功能候选出现租约或正确性故障，仍须处理，不能归入可延期性能项。

E 开始时新建既定二角色并记录模型/强度；额外角色、真实设计冲突或多轮修复不收敛交 Owner。本文是后续准备，不是当前 E GO 或 S2b exit。

# Worker 活跃 claim 的自动循环 GC 调度修复候选

2026-11-06，p6-backend-design，依据 Owner DC80；接续[结果审核 §77](p6-submit-single-step-diagnostic-scope-review.md)及[GC 观察设计](p6-mutation-plan-gc-window-diagnostic-plan.md)。范围已由 §78 通过，最终产品与定向验证由 §86 通过，新镜像及小 Compose 由 §87 通过；后续测试执行按下述 2026-11-07 Owner 补充授权推进，不授主线合入或正式测量恢复。

设计指定现有 `01a1b107-11ba-7681-a7cf-afb1591a67d2` 为唯一实施者，`01a182d8-4dfd-7441-b9db-4deefdc4e0ac` 为独立审核者。既有接管/通信条件已完成，范围通过后双方直接准备、修订、定向验证和复审，不重开身份确认或等待 Owner 重复许可。不得新建角色。

## 测试环境执行授权（Owner 2026-11-07）

Owner 明确当前测试环境的审核/执行流程过严，应放宽独立运行 GO 条件，减少反复沟通确认。本节按[比例化保障政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)取代本诊断链后续“每个最终 manifest 再签一次 GO”的前置；旧候选的运行、失败和 GO 消耗记录保持历史事实。

- 范围及关键产品变化独审一次。当前 `9704d0b286049073529d60036dbd999032f97e0a` 已满足 §86–87；本次 Owner 授权覆盖其后续必要工具接线、focused、预检、新 manifest 和**一次原定真实 prepare-only 运行**。实施者准备合格后直接执行，审核者不再为该最终摘要另发 GO，不等待 Owner、设计或协调回执。
- 运行前由实施者核实 clean 源码、已核镜像、原输入/checkpoint 来源、新 project/key/三卷副本、节点占用及既有资源/截止/回收条件，并保存实际 manifest/日志。身份、缓存或必要守护不符仍停止，不能通过通用 skip 放行。最终摘要用于追溯，不是逐版本审批凭据；新工具若保留 GO/授权字段，记录本 Owner 范围授权即可，不要求 `POST-GO.txt` 或审核者回执，不伪称最终字节已独审。
- 同范围脚本接线、测试断言/类型、语法、日志和文书修正，完成必要检查后直接接续，不逐次申请复审或 GO。低风险准备命令失败先停止原样试错、留日志、查明原因后最小修正；恢复不因累计失败次数再等 Owner。实际产品语义、输入来源、镜像身份例外、必要守护或资源/运行范围变化，才集中交审核者/设计评估关键差异；不把每份新摘要视为新范围。
- 结果由独立审核者事后核验。非阻塞文案、计数及补充统计问题后置更正，不据此重跑已通过场景。实际产品失败仍停止受影响运行并保卷留证，按 DC80 直接诊断/修复；需要关键修正时，将代码/恢复资格合成一次审核决定，不再追加一轮最终 manifest GO。没有修正或新依据，不重复同一大输入；本次原定运行次数及预算不增加。

本补充调整测试审批流程；原资源上限、45 分钟观察/3600 秒总限、真实失败处理及正式基准验收口径继续有效。独立结果审核、主线合入/推送和正式测量恢复仍按各自原有范围处理。

## 已知故障与候选目标

g 的闭合 generation 2 区间 wall 24.015076449 秒、同线程 CPU 24.011767181 秒，覆盖续租 due 到 helper 迟到窗口；helper marker 已超真实 deadline 2.628630207 秒，最终入口 emit 和原 helper 调用各约 5 毫秒，未进入下一次 session。mutation_plan 当时未返回。§77 支持这一正向共现，不单独证明 GIL 或唯一原因，也不把旧 c/h 的原因追认相同。

候选针对这一已观察到的调度风险：把自动循环 GC 的机会移到没有活跃 executor/续租责任的 claim 间隙。保持引用计数回收、所有显式资源 close、业务/事务/幂等/CAS/checkpoint/digest 和原 lease/heartbeat/drain/stall 数值。它不会使任意长的 native 调用、手动 GC 或全部调度延迟自动安全；效果仍待实际候选验证，根因不因设计成立就关闭。

## 最小产品变化与边界

- 从 clean 固定 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 建隔离产品候选 worktree；只改 owning worker runtime 的 GC 调度及必要现有测试。不合入当前 main，不改 parser/planner 算法、依赖、Schema/Contract、DTO、golden、输入或公开配置，不引入新 executor/进程/队列/状态机/兼容或回退路径。
- 在生产 run 循环 startup 完成后、每次读取 claim_anchor 和 claim_one **之前**记下原 GC enabled 状态；原本 enabled 时暂停自动循环 GC。原本 disabled 则全程保留 disabled，不把恢复写成无条件 enable。策略只属于独立 worker 进程，影响其全部线程，backend/RS 进程不受此解释器状态影响。
- 原 claim、executor、heartbeat、事务和生命周期代码原样委托，不复制循环或改变异常分类。无工作和 claim StoreBusy 分支在原 idle/backoff 等待前恢复原状态；真实 `_run_claim` 的 StoreBusy/lease 异常不得被错归为 claim_busy 并自动重试。所有返回/异常路径用 finally 恢复，不能把初始状态留错。
- 真实有工作时，自动 GC 暂停覆盖原 claim 到 `_run_claim` 的完整执行、executor join 和原 ack/发布收束。fence 不代表 executor 已停止；原 join 未返回时不得为了恢复 GC 提前宣称空闲或强杀线程。正常返回、或原异常路径已确认 executor 不再运行后才恢复原 GC 状态。
- 原本 enabled 且确实执行过一个 claim 时，可在上述空闲边界做一次标准 `gc.collect()`，在下一 claim_anchor 读取之前完成；空 claim/claim_busy 不新增反复 full collect，初始 disabled 不强制 collect。先丢弃已无用途的当前 claim 局部引用，避免为回收另建持久持有。回收与恢复异常不得掩盖原业务失败或抑制退出，不在持有活跃 lease 时主动 collect，不更改 GC thresholds/freeze。
- 不建设跨线程 GC 设置协议。实现前核冻结生产路径对 GC 状态/手动 collect 的现有调用；未协调的第三方手动 collect 仍是残余风险，不能因自动 GC 暂停就声称不可能再有 collection。若发现此策略无法保住原状态/单 executor/显式资源释放边界，具体报告并交设计收窄，不自行扩大机制。

## 内存、版本及证据限制

暂缓自动循环 GC 可能使不可达循环对象滞留到 claim 结束，大小目前未知；引用计数不等于全部对象都会即时释放。旧 g 的约 23.9 GB worker RSS 也不能预测新峰值。本轮只在既有独立测试节点和原诊断资源 envelope 内验证：启动 available 至少 48 GiB，worker RSS 40 GiB/host available 8 GiB/disk 10 GiB 停止线不变；越线即停止，不自动提高限额。

主线 DC87 的 worker 12 GiB、kernel M=8 GiB 是另一个部署约束。本候选即使通过旧测量环境验证，也不能声称满足主线预算或已获准合入/部署；当前 Rust projection 后仍有 Python mutation snapshots/planner，不能假设 Rust 会自然修复本问题。后续主线采用须与新开发设计协调实际资源与验证影响。

新 GC 策略可能改变既有场景的 CPU/时长/峰值，旧性能数字不能自动作为新候选结果。H3 原 PASS 保留为原身份历史事实，不据此声称新候选已运行该场景。正式 V→H、冻结口径和基准剩余范围另审；本方案不通过工具修复许可追认正式恢复，不改旧结果/输入/日志/卷。

## 比例化验证与一次实际候选

范围通过后实施。复用现有真实 WorkerRuntime/生命周期和必要 SQLite fixtures：验证初始 enabled/disabled、无 work/claim_busy 等待、正常完成及原异常恢复；真实原 runtime 的 heartbeat/发布/ack 与异常不变，自动 GC 不在活跃 claim 发生，空闲回收位于新 anchor 之前。process-global GC 或固定时间测试标 serial，并在测试 finally 恢复原设置/移除自有 callback，不让测试污染后续运行。不要纯 GC 状态测试引入 Dolt fixture，不只靠自造 fake runtime/API 证明生产接线。

只跑受影响 worker/runtime focused 与五 Python 包既定 Ruff/mypy；不跑全量 runner 或重测关闭矩阵，Rust/依赖未变不重编 Rust。最终 clean 产品候选提交和源码差异先独立审；只读状态/summary 记录原、活跃、恢复后的 GC 状态，保留“自动暂停不等于无手动 GC”的解释边界，不为此重造观察器。

需要真实新 backend/worker 镜像。沿冻结版本 DC67 在 CT201 构建、LAN 传至05、比较 config digest/全部 DiffID，独立 tag，不覆写已审镜像；不用当前 main 的新 dependency-base 流程替换冻结 Dockerfile/依赖。RS 代码/上下文身份满足原规则时复用 §52 已核 RS，不为统一 revision 标签无故重建。对最终镜像只跑原已用的一个小 Compose 旅程作接线验证，不再另跑一轮外挂禁 GC ablation 或合成大 probe。

产品/镜像/小门禁通过后，复用原 g 已审 controller/observer 和 partial 规则，为明确旧 source checkpoint→新产品/镜像组合、新 project/key/三卷副本固定独立 manifest；身份例外只允许本次确切 GC 修复差异，不用通用 skip。45 分钟观察/3600 秒总限与全部原停止/回收/保卷条件保持，05 按实际有效占用，CT108 不加负载。依上述 Owner 测试环境授权，实施者完成必要接线验证及运行前核对后直接执行原定一次 prepare-only，不再另等精确清单 GO，不自动重试。

此次一次实际候选既用于检验处置效果，也记录循环对象/峰值与是否触线，不承诺完成耗时，不预先排两套全输入运行。成功与否由独立审核核；不因没有失租就单独声称全部容量安全或唯一根因已被证明。若需要改变资源上限、业务语义或正式基准口径，带具体结果与选项交 Owner，不能自行越界。

# Phase 6 change-set 摘要与心跳局部诊断

状态：2026-11-06，DC80 下的设计候选，待独立范围审核；不授权新的 Submit、正式测量或产品修正。

## 事实与待区分的问题

依据 [单步诊断审核 §36](p6-submit-single-step-diagnostic-scope-review.md)，`p6catalogsubmit20261106f` 的 lease 在 04:43:28 到期，04:43:31 明确记录 `lease_lost / heartbeat_busy_deadline`，随后才触发 120 秒无心跳的旅程停止。没有 `heartbeat_busy` 事件；该错误类别也可由续约调用前的 deadline 检查发出，不能认定 SQLite 竞争。观察器本次未降级或发停止信号，资源未越限。

123–125 栈中主线程仍在 Event.wait，执行线程构建全量 mutation 文档；126 起主线程进入异常分支的 thread.join，执行线程继续 Unicode/digest。采样时持 GIL 不能证明连续占用，也不能用最后一份 Unicode 栈替代实际迟滞时点。需区分 payload 构建/GC/释放等调度窗口，以及续约前取得的 monotonic anchor 与实际事务续约之间的差异。

冻结 e798 的精确摘要前像是 `JCS({"mutations": [...]})`，不是裸数组。当前流程先检查所有 mutation 类型与顺序、构造全部文档，再按全树 Unicode、全树数值、JCS 序列化的顺序处理。cell envelope 可以含字典，不能未经证明就把逐 mutation 校验/哈希当作错误语义完全相同；本次不改摘要算法、Contract 或校验顺序。后续 closure 还会重复计算摘要，不在此处顺手删除这些验证。

## 单次探针范围

只在 05 的 clean、已提交 e798 backend worktree，使用已核绝对解释器及离线环境。原实施者先核 SSH、实际占用和依赖；开发主机不运行探针。代码为独立外置 harness，固定摘要后送审，不修改产品 worktree、旧脚本或历史证据。

复用现有 `test_operation_worker_scheduler.py` 的 RuntimeStore/RuntimeUowFactory/FakeStartup 和活动 operation/step fixture，以及现有 mutation Contract 构造辅助。采用真实 monotonic、UTC、Thread 和 Event；事务时间不能沿用固定 BASE_TIME/FakeClock。保留产品原 10 秒心跳、30 秒 lease 及原 fence/安全 handoff，不改 worker 的线程结构。内存 UOW 明确不代表真实 SQLite 锁行为，不能据此排除现场数据库因素。

唯一固定输入最多 **20,000 个有序合法 mutations、每行 33 列、每字符串最多 64 UTF-8 bytes**。在执行前固定具体数量、INSERT/UPDATE 构成和可复现的生成规则，不使用真实导出文件、不读取数据卷、不生成 SQL/大型磁盘 fixture。构造输入也计入总预算；只调用一次真实 `compute_change_set_digest`，不加入新旧算法、关闭 GC 或不同规模的矩阵。不要为满足某个停顿阈值自动补大输入。

整个探针由独立外层监督，**含构造、摘要、hand-off、线程退出共最多 120 秒，探针进程 RSS 上限 2 GiB**；每 200 ms 轻量核原 PID/starttime 和 RSS。必要指标不可读、超时或越限时终止并回收本次探针，保留已产生记录，分类为诊断截断，不当作产品断言失败。不能依赖可能正遭调度迟滞的同一 Python 线程实现总截止；沿用标准子进程管理和短小外层监督，不建立常驻监控或新产品生命周期。

不启动 Dolt、Compose、HTTP、实际 Submit 或 control DB，不使用 CT108；实际节点单飞与日志规则保持。执行一次后停止，未复现也不自动重跑或扩大。

## 观测与判读

通过外置轻量 wrapper 与有界 GC 回调记录以下时序，不替换实际计算实现：输入构造、类型/顺序检查、全量 payload 构造、Unicode、数值、JCS、hash、返回/临时引用释放；心跳尝试前后、成功事件、runtime 使用的 lease_deadline/renewal_anchor、事务产生的期限；执行线程与主线程完成/异常 join。

记录 monotonic、UTC、process CPU、输入计数、RSS、异常类型/代码及 GC 各代次数、总耗时和最大停顿。不得逐 cell 打日志或输出值、SQL、凭据。GC 回调和时序记录采用有界聚合，避免回调内 I/O 或无限事件列表；若保留具体 GC 窗口，明确固定条数上限及截断标志，具体规则在候选中冻结。观测有扰动，不能把探针耗时当正式产品性能。

若单次调用太短而没有跨过一次真实续约，只报告未覆盖该关系，不额外等待/重复计算来制造心跳。若读数不足以对应全图释放或某个 C 调用，明确缺口，不把 phase wrapper 边界当作 GC/解释器内部证明。

结果应分别回答：是否发生真实线程续约迟滞、是否达到本探针内存 UOW 的租期、哪些阶段/GC 窗口与迟滞重合、anchor 到实际续约的间隔。20,000 行/2 GiB 不模拟现场约 24 GB，未复现不能排除大堆调度问题。无论结果如何，不因一份相关性记录就认定唯一根因；先依据实际观测决定是否值得最小产品修正。

## 接续与审核

既有工具任务只读提供源码与方案，原实施者准备固定 harness/命令/manifest，现有接续审核者独立核范围及最终执行候选。范围通过后可准备工具；实际运行须具体候选 GO，不重跑已完成的 observer 测试或旧单步旅程。

如后续考虑 JCS writer/hash sink，必须保持原字节、摘要、错误类别与优先级；仅消除序列化 bytes 不代表消除全量 payload，也不保证解决当前迟滞。若进一步改变稳定输入假设、逐 mutation 校验顺序、Rust 接口或 lease 行为，先另列设计影响并核共享产品开发线，不在本诊断中实施。正式测量仍停止，H3 保留；本次不是 DC68 重做，也不是正式恢复许可。

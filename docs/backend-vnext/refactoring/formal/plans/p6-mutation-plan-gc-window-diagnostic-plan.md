# mutation_plan 续租延迟：有界 GC 与观测耗时诊断

2026-11-06，p6-backend-design，依据 Owner DC80。本范围接续[prepare-only 设计](p6-prepare-step-lease-diagnostic-plan.md)和[审核报告 §67–68](p6-submit-single-step-diagnostic-scope-review.md)，须定向范围审核后准备，最终精确候选另取一次 GO。

**执行归属已明确：** 设计指定现有会话 `01a1b107-11ba-7681-a7cf-afb1591a67d2` 为本计划唯一实施者，现有会话 `01a182d8-4dfd-7441-b9db-4deefdc4e0ac` 为接续独立审核者。原实施会话仅供历史交接。双向通信和只读交接门槛早已完成，Owner 已解除接管前只读限制；§69 范围 PASS 后直接准备本计划候选和必要 CT05 focused，不重复接管或等待角色确认。此处只澄清既有角色与准备授权，技术范围及最终运行 GO 要求不变。

## 证据缺口与这一次要回答的问题

§67 已确认真实失租：mutation_plan 尚未返回，190 次 session heartbeat 均返回；最后 helper 标记比 derived due 晚 22.272004 秒、比真实 deadline 实参晚 2.272004 秒，未进入下一 session。仍不能区分 GC、调度、其他 Python/native 工作和外置观测扰动。

已有源码表明 mutation planning 包含大批对象构造、键转换/排序、重复 Contract/digest 校验及释放。EventWriter 在真正调用被包装函数之前先记时间、JSON 编码、取得锁并 write/flush，因此 marker 不是未插桩的真实函数入口。已有 100k 合成探针 checkpoint 13 保存的 GC generation 2 最大时长约 2.249 秒，且缺少最终被截断窗口；其产品/形状/堆量与本次不同，不能外推现场停顿或关闭任何根因。

本次只问：失租前的续租空窗是否与实际 GC collection 区间重叠，GC 所在区间的 wall/thread CPU 是多少，以及 observer 的入口记录/锁/写入是否占据了明显时间。区间重叠、CPU 耗时或未观察到重叠均只按实际覆盖解释，不单独证明 GC/GIL 因果或排除未覆盖阶段。此次不增加另一套 planner 内部阶段插桩。

## 保持的真实路径与成本

复用 §66 受审候选的 controller、guardian、一次真实 acceptance、唯一目标 prepare claim、正常返回后 drain、no-restart、原线程/LeaseSession/SQLite/RS、输入/缓存/卷身份及停止回收行为。产品继续固定 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 和 §52 三镜像，不改产品或重建镜像。

现存材料没有序列化的 MutationTableSnapshot 或其他可直接重放 planner 的完整输入；源码也未把该 closure 发布至 artifact_store。不能声称能免除 parent 物化，也不为此增加大中间 checkpoint/pickle 或伪造输入。新候选须使用原 pre-submit checkpoint 的新隔离目标副本、新项目/key/证据目录，不能继续已失败 c 的卷。parent_materialization 的 907.302 秒是此次必要重复成本的已知参考，完整耗时未知；不把旧失败时长当完成时间。

这是一次新的局部诊断，不是自动重试 c，也不附带先跑合成大输入、完整 Submit 或正式基准的第二轮要求。若此观察不能回答缺口，再按实际证据决定下一步，不能预先排队多轮全输入运行。

## 最小外置观测变化

- 仅在外置 worker wrapper 注册一个本候选自有的标准 `gc.callbacks` callback；沿已审合成探针的有界记录方式，记录各 generation 的 start/stop monotonic、执行线程 ID、thread/process CPU、计数与耗时。callback 只作常量规模内存更新，不做日志/文件 I/O，不获取 EventWriter 锁，不逐对象扫描，不调用 collect、disable、freeze 或改变阈值，不覆盖其他 callbacks；正常退出只移除自己的 callback。
- 固定最多三个 generation 的当前区间、计数/累计/最大耗时；为每个 generation 保留自上一 heartbeat snapshot 以来最长的一个区间，另保留全程最长的最多 16 个完整区间。内存有界，不为所有 collection 留事件队列。超出可表达范围、callback 异常、开放区间或未取得最终摘要须明确 incomplete，不能用来宣称没有 GC。
- 复用现有 heartbeat helper 入口/返回事件和最终结果输出聚合摘要。每条只带固定大小的计数及最多三个窗口区间，仍满足每事件 2 KiB、4096 条/8 MiB；完整有限摘要只在正常收尾写入一个小 JSON（最多 32 KiB）。没有 callback 内 fsync、逐 row/key 事件、GC 对象内容、stack profiler、额外后台采样线程或新的服务。
- helper 与 session wrapper 在入口 EventWriter.emit 返回后，紧接着记录真正调用原函数前的 monotonic；在返回/异常事件中分别报告 entry emit 耗时、原调用起止/耗时和原 wrapper 总耗时。EventWriter 自身将锁等待及 write/flush 的区间作有界聚合，供下一条事件/最终结果报告，不为测量 logger 再输出一条 logger 事件。
- 时间名必须区分 wrapper marker、entry emit、original call 和 derived due。原 deadline/renewal_anchor 参数、返回及异常原样传播；不把新记录称为实际 run-loop 唤醒时间。若原调用未返回或进程被停止，没有持久化的调用起点/最终摘要须记缺口，不补造结束或成功。

新观察会改变调度/分配和 I/O 开销，不能称为正式性能测量。先用已有原始事件的可计算边界解释已有结果，不把本次观察当作推翻 §67 已确认失租事实的依据；h 等未用这套函数边界观测的失租也仍保留。

## 预算、验证与直接闭环

保留原 45 分钟绝对业务观察和 3600 秒全流程硬上限、原初始化/清理预算、48 GiB 启动可用内存及全部资源/身份/lease_lost/cancel/120 秒 stall 停止条件。不得为了得到完整摘要延长 lease、heartbeat、drain 或诊断预算。标准 outer cleanup 对自有进程/容器有界收束，保卷/留证、未确认静止不解锁；collector 正常关闭不代表 worker 正常退出。

本候选可在 05 正常取得有效占用后运行；此前释放不是排他预约，E 的 t1–t3 可能已占用，应等待其释放，不抢节点。CT108 不增加负载。唯一实施者准备，接续审核者独立审；常规修复/定向测试/精确清单及一次 GO 直接闭环，不等协调者中继。

范围通过后只补必要 focused：真实 callback 的 start/stop 和有界聚合/开放或异常区间；事件最大形状；entry emit 延迟与原函数返回/异常透传的计时区分；不改变原 worker/LeaseSession API 或状态。使用冻结真实入口及原 fixtures，测试在 05 clean 已提交环境运行；不重跑已关闭的 controller/回收矩阵、旧合成大 probe、小 Compose 或全量 runner。代码/测试/日志、原始失败包与最终新 manifest 精确绑定后独立审，取得候选专属一次 GO 才执行。无推送、产品合入或正式测量恢复授权。

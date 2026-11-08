# Phase 6 完整 change-set closure 局部诊断

状态：2026-11-06，DC80 下待独立范围审核的设计；仅可准备候选，执行须另获固定 manifest 的一次 GO。不授权 Submit、正式测量、产品改动或合入。

## 目的与现有依据

前一探针结果见审核 `d240b1e599` / `p6-submit-single-step-diagnostic-scope-review.md` §40：20,000 mutations 的单次 digest 可完成并续租，不能解释现场约 24GB 堆下的 lease 失效。原事件在重复 payload 构造附近发生；前一探针仅计算一次 digest，且保留的 GC 窗口全在 worker 开始前。

最小 JCS hash sink 候选 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`、handoff `172d53cfebeb1a6dc6ae1ea4068483b129285e70` 经审核 `b37041df2f` §42 通过代码及局部语义。它去除完整序列化输出的聚合，但保留全量对象图与重复校验，尚无镜像、性能或 lease 修复结论。本轮选择覆盖更完整的调用链，不把旧/新小样本速度对照设为前置，也不沿用旧 probe 的时间作为对照。

## 唯一固定工作负载与预算

在 CT05 clean、已提交的上述代码候选上，使用实际 backend venv 绝对解释器、离线缓存和原 10 秒 heartbeat / 30 秒 lease。沿用已核真实 Thread/Event/monotonic/UTC 与内存 Store/UOW、LeaseSession 接线；不能使用固定时间或可控假线程。产品源代码和镜像不修改。不得换成新 main、系统解释器或升级依赖。

一次真实 `build_change_set_closure` 调用，生成且核对恰好 **100,000 mutations：50,000 UPDATE、50,000 INSERT，无 DELETE，单表、每个 after-image 33 列、每字符串至多 64 UTF-8 bytes**。复用现有合法 planning request/plan/decision/snapshot fixture，构造对应 before/after 数据，通过产品路径生成 mutations，不手工调用三次 compute 来模拟完整链，不创建无关填充堆。key、排序、before/after row digest 及 manifest 绑定须符合原 Contract；生成规则、期望计数和来源 fixture 在候选 manifest 固定。完整链保留首次 change-set digest、artifact 重算和 closure digest。

所有输入与 fixture 构造、导入、计算、handoff、引用释放及线程退出均纳入单次外层预算：**最多 300 秒，290 秒触发停止；子进程 RSS 上限 8 GiB；独立监督每 200ms 核 PID/starttime/RSS**。TERM/KILL/reap 共用绝对截止，至多使用剩余预算；无法确认回收则保留节点锁并报告。信号/异常亦进入相同有界回收，不自动重试或扩大规模。

预算依据仅用于限制任务：上一探针构造 1.64 秒、单 digest 11.72 秒，按五倍输入与三次摘要粗算约 184 秒；旧采样峰值约 689MB 乘五约 3.45GB。新路径存在额外 snapshots/校验，且算法、GC、分配并非线性；因此 300 秒/8 GiB 是诊断上限，不是完成时间预测或性能门槛。截断是允许的诊断结果，不临场追加预算。

执行前按已有规则核 SSH、节点有效占用、clean HEAD、绝对解释器、锁定依赖和 LAN 缓存。候选额外要求启动时 host available 至少 **16 GiB**，运行中低于 **4 GiB** 停止；证据目录可用磁盘至少 **1 GiB**，运行中低于 **512 MiB** 停止。只采必要轻量指标，不遍历其他任务数据。不能满足即不启动，不调整规模抢跑，不抢有效占用。

无 SQL/真实数据、control DB、Dolt、Compose、HTTP、Submit、CT108、产品镜像或全量 runner。原 probe 的 GO/attempt marker 已消耗且保留；新工具采用独立目录、候选 ID、manifest 和一次性 attempt marker。

## 观测与解释

记录实际调用链的粗粒度序号与 monotonic 起止、process/thread CPU：输入构造、closure builder、每次 ordering/payload 构造、第一次/第二次 change-set digest、closure digest、Unicode/数值/serialization、handoff 与 runtime 退出。保持原函数委托、校验及异常顺序，不通过跳过真实逻辑来采样。排序中逐 key 的 JCS 仅聚合，不逐 key/cell 持久化；必须能与全量 payload 的 JCS 区分。对象释放能定位则记录，不能独立定位时明确包含于哪个外层调用，不把时间差作为精确 GC 或释放耗时。

heartbeat 保存真实调用入口/返回、原 deadline/anchor、实际 UTC 续租事务和失败类别；**heartbeat 前不执行 checkpoint/fsync**。heartbeat 与 GC callback 只更新有界内存记录。粗粒度业务阶段边界低频保存已完成观察，记录保存耗时/次数；正常和异常结束尽可能保存最终观察，硬截断未保存的窗口明确缺失。不新增常驻 observer/sidecar 或产品日志机制。

GC 全程按代保留次数、总时长和最大时长，窗口改为固定最近 **128** 个环形记录加最长 **32** 个窗口；保存 monotonic、generation 和截断/覆盖计数。不能只留导入期最初窗口，不关闭 GC 或强制 collect。回调不做 I/O，不持有业务 payload 引用；窗口与阶段仅证明时间重叠，不能独立证明唯一因果。

heartbeat/worker 事件各最多 **128** 条，粗粒度阶段每类最多 **32** 个窗口并保留全程聚合，checkpoint 最多 **64** 个；所有丢弃/覆盖和持久化失败显式记录。观测开销、外层 RSS 采样间隙与内存 UOW 不覆盖 SQLite 的限制必须写入结果。

结果分别回答：实际完成到哪一步、完整链计数是否匹配、是否真实续租、是否错过 deadline、最后有效阶段和 GC/调度窗口关系、资源/截止是否触发、child 是否回收及锁状态。无论成功、失败还是截断，仅解释本固定数 GiB 级合成输入，不称复现现场 24GB 或完整 Submit。成功只减少一个局部疑点；失败或截断按已有阶段记录选择下一项最小措施，不自动扩规模、修改 TTL 或重试。

## 分工与接续

设计负责本范围及后续选择；原测量实施者准备外置 harness/manifest 和候选命令，现有接续 reviewer 独立核实际脚本、输入生成链、观测和监督边界。只复用旧工具适用部分，旧脚本/证据保持不变，按新 JCS writer 接口实际接线。范围通过后不再等待 Owner 重确认；具体候选未审完不能运行。

收到绑定新 manifest 的一次 GO 后，原实施者自行核节点条件并执行，普通回复与 handoff 由设计/reviewer 主动读取，不等待缺失的外发工具。结果经独立复核后再决定是否需要产品修正、镜像或恢复候选；本计划本身不授予这些动作。

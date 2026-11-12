# Preview 固定双 pair 并行详细设计

状态：设计草案，待独立设计审核与 Owner 确认；本轮只交付设计和实施计划，不授权产品实施、资源扩容或部署。源码核对基线为 main `64b89505f4`（`p7-s2b-exit`）。本专项简称 PP，不占用尚未实施的 P7 S3 编号。实施安排见 [实施计划](p7-preview-pair-parallel-execution-plan.md)。

## 1. 目标、范围与 FE4b 的关系

Owner 已明确的方向：一次 Preview 只有一个或两个 pair；双 pair 固定最多两路，各自完成本 pair，不在一路空闲后介入另一路，不建设通用线程/进程池、动态调度或任务窃取。

本稿将这一方向具体化为设计建议，以下线程、预算、缓存选择不是已确认的 Owner 决议。

- `FULL` 的 `baseline_to_initial`、`initial_to_modified` 在公共快照准备完成后并行；`MODIFIED_ONLY` 保持单 pair。按实际 pair 计划判断，不按上传文件数判断。
- 覆盖 pair 的 comparison → records → risk → surface；两路结果齐备后统一生成 closure/bundle 并发布 READY。解析、公共物化和最终 bundle 不在本次并行范围。
- 不拆成两个持久 operation，不分派到两个 worker，不改 Submit/Review/Archive，不扩展 History 的多 pair 调度，不修改比较、风险、展示语义和正式 digest。
- 继续使用一份 kernel 算法；N1 与 N2 是同一执行入口的不同资源档，不保留两套业务实现。
- FE4b 未合并不阻塞设计与后端编码准备。本专项不改 `frontend/`、HTTP DTO 或 bundle 格式；FE4b 合并后的实际集成候选仍需绑定证据。发生前端可见协议变化时退出本范围，先更新设计并通知前端。
- 多设备并发、S3 公平调度/准入/背压与本专项分别验收。两个 worker 不等于一个 Preview 内两个 pair 并行。

## 2. 当前实现与必须消除的误解

| 源码接点（均相对仓库根） | 基线事实 | 设计影响 |
| --- | --- | --- |
| `vnext/backend/src/gateway_backend/application/preview_jobs.py::_assemble_preview` | 按固定 pair_specs 顺序调用 `_run_pair_pipeline`，随后组装 bundle | 并行结果仍须按原顺序归并，不能按完成顺序输出 |
| `application/pair_pipeline.py::declare_pair_comparison_session` | 两个计划共用一个 `ComparisonTaskSession` | 不直接把该实例传给两个线程 |
| `capabilities/comparison/production.py::ComparisonTaskSession` | 保存 dict、remaining_uses、native handle、pending_risk、租约及释放状态；可写比较/风险持久缓存 | 业务独立不代表执行对象独立；不能把 Preview 当成只读缓存 |
| `capabilities/snapshot_materialization/client_parquet.py` | 导出缓存命中读取，miss 生成并 store；损坏项可条件删除 | 公共导出收敛到协调方，不在两路同时补同一快照 |
| `capabilities/table_access/kernel.py` | `OperationMemoryBudget`、`ExitStack`、上下文生命周期为可变对象；通过 ContextVar 绑定 | 不浅拷贝一个上下文让两路共同修改 |
| `capabilities/comparison/production.py::compare_plan_native` | native 阶段按 available 计算大额预约 | 给总账加锁仍可能使第一路吃掉第二路容量；需明确分额 |
| `vnext/rust/gateway-compute-python/src/comparison_records.rs::_compare_records_native` | `py.detach` 后进入 `shared_parser_pool(...).install(...)` | GIL 已有释放，但共享 N1 池仍可能串行；不能用两线程启动证明计算重叠 |
| `statistics/metrics.py`、`artifacts/scratch.py` | 通过 ContextVar 保存统计与 scratch 会话 | 新线程须显式绑定各自上下文，不能共享同一个可变 Metrics/scratch 清理栈 |

正式引用还包括 [P7 S2 设计](p7-s2-design.md)、[S0 决议 D24](p7-s0-owner-decisions.md)、[比较 Contract](../../../contracts/comparison.md)、[Operation Contract](../contracts/operation-lifecycle-and-integrity.md)。上述源码相对路径均以 `vnext/backend/src/gateway_backend/` 为前缀，表中完整路径除外。

## 3. 执行模型：协调方 + 最多两个固定线程

选择线程作为首选实现，不增加子进程、IPC、跨进程缓存或额外常驻服务。每次双 pair 执行只创建两个非 daemon 线程，各自领取预先固定的一个 pair；无任务队列、无重分配，完成后 join 并释放。单 pair 在原执行线程直接调用同一函数。

协调方保留原 operation/step、LeaseSession 和最终发布权。两路只生成派生结果，不能直接发布 CANCELLED/FAILED/READY 或释放 operation pins。

执行顺序：

1. 原流程完成受理、解析、冻结输入、公共物化；建立一或两个不可变 pair 输入规格。
2. 协调方持有公共输入的借用与生命周期，核资源档，分配两路预算及独立 scope。
3. 每路在线程内创建自己的 kernel context、scratch session、Metrics、comparison session；运行 pair 流水线，关闭本线程创建的 Arrow/native reader 与可变句柄。
4. 协调方在有界 join 轮询中刷新 lease/control，广播取消、drain、失租或同伴失败。沿用既有心跳所有权，不另起持久心跳协议。
5. 两路退出后，按 pair_specs 顺序接收小型 facts/refs/结果；保留其内存所有权，再关闭不再使用的 lane scope。
6. 协调方按既有 `surface_artifact_closure`/bundle 路径复用或生成快照导出，最后重新核 lease/cancel，再以原 CAS 发布 READY。

边界：线程无法安全强杀。join 超过监督期限不允许释放输入、启动替代任务或宣称已清理；沿既有 executor/process 停止与人工恢复边界处置，并保留 worker 占用。失败不升级为新自动恢复服务。

### 3.1 真正的 Rust 并发与 N

保持 `kernel_threads=N` 为单 operation 的总计算并发上限，不暗中改为“每 pair N”。首版正式支持 N1 对照档和 N2 双路档：

- N1：同一入口按原顺序执行，可作真实串行对照；不声称开启双路。
- N2：双 pair 每路最多一个活跃计算线程；单 pair 不因另一执行位置空闲获得额外并行。无 pair 内表级抢占或借用另一位置。
- 既有解析/物化 Rayon 池继续用于公共准备阶段，不为 pair 新建池。pair 阶段的纯串行 Rust 比较函数在调用线程的 `py.detach` 区间执行，移除该路径不必要的 `pool.install` 排队；单/双路调用同一内核。核对所有 comparison/probe 入口，不能只改主比较函数。
- pair 调用链不得落入 Rayon 全局池、调用嵌套并行算法，或在执行期间修改全进程 Arrow 线程配置。Arrow/Parquet helper 的实际线程来源须固定并计入 CPU 档；无法满足时调整局部执行接点，不以线程数量配置冒称上限已成立。
- 不为本专项新开放 N>2。已有 N>2 的配置合法性不在此擅自收紧；在适用部署中限制 pair fanout=2，超出 N2 的性能与容量不作本轮承诺。

N2 启用仍受 D24 约束：同真实输入 N2/N1 正式结果/digest 核对。默认 N1、32/8/M24 档本次设计不改；N2 的生产/人工验证部署启用必须在验证后明确记录，不能通过新增 pair 线程绕过 N1 约束。

## 4. 内存、输入与输出的所有权

采用静态分额，不引入动态借贷或等待内存的调度器。

在分叉点，父 scope 已保留公共输入和 metadata，并根据现有结果 schema 的条数/字符串/字节上限预留两份有界小结果交接区，合记有效 charge 为 R；operation 总预算仍为 M。交接区上界必须在 A 包定出计算公式，不能以“结果很小”免计费；超界拒绝，不保留任意大的异常/traceback 对象。协调方冻结父 scope 的并行期间新增分配，并先在父账本预约剩余容量的两个分额：`B1=floor((M-R)/2)`、`B2=M-R-B1`。每路独立 `OperationMemoryBudget(Bi)`，本路 native/Python/Arrow/缓存/导出均在该分额内，不各自获得一个 M。首版不按数据大小预测比例，不在一路完成后转移额度。

- 公共已经物化的不可变数据由父 scope 保持到两路真正退出；可变 reader、scanner、PythonChargeOwner、native handles 必须在线程内创建/关闭。
- 公共对象借用若暂不能准确复用父 charge，可保守在 lane 中重复计费；禁止漏计或让 lane 释放父所有权。实现须列出借用对象与关闭顺序，用生命周期测试证明。
- 不能一边持有同一份数据一边把父预约释放给 lane。输出转换为交接区所覆盖的小型独立 facts/refs，再关闭 lane scope；父预留持续覆盖结果直到归并消费。不能把依赖 lane 的懒求值对象直接传出，也不返回 live Arrow/native handle。原 `kernel_execution_scope` 退出会关闭其 metadata charge，必须明确转换先于退出，不以 Python 引用仍活着证明账本有效。
- 两路工作完成并退出后，剩余额度统一回到父 scope，由原流程完成 closure/bundle。公共导出如在 pair 内确有消费者，应改为协调方准备所需子集或传入已验证 refs；不得无差别预导出全部表而恶化首屏时间。
- 子预算不足沿既有资源错误退出；不在同一已开始的 Preview 内自动串行重跑，不静默增 M，也不缓存冷热不同导致随机切换执行模型。

**待实测收口的容量问题：**原算法的保守预约可能使每路半额不足，即使历史 RSS 较低。A 包应先计算真实 FULL 计划的 R/metadata/native 下界；不满足时停止该资源档启用，交具体测算选择资源档或修改分额设计。不能把“32 GiB 机器/容器够用”写成已证明。失败的资源档不以退回串行掩盖双路未实现。

## 5. 缓存与产物：独立会话，复用现有发布协议

本稿选择**每 pair 独立可变缓存会话**，而非把当前共享会话全面加锁，也不集中保留两个 pair 的全部缓存候选到末尾。

| 对象 | 所有者与处理 |
| --- | --- |
| operation 输入、规则、快照描述 | 协调方冻结；lane 只读借用 |
| ComparisonTaskSession / native handles / pending risk | 每 lane 私有，声明只包含本 pair 的 plan，在线程内关闭 |
| 持久比较/风险缓存 | 复用当前 lookup/pin/store/no-replace/条件失效协议；每线程独立短事务，不共享 SQLite connection/UoW |
| operation pins | 两路使用同一 operation owner，但只有协调方在全部退出且结果生命周期安全后统一释放；关闭 lane 不得删除另一 lane 的保护 |
| Parquet 快照导出 | 优先在协调方 closure/bundle 阶段按已有 key 复用或生成；共享 initial 的相同导出只安排一次 |
| records/risk/surface 业务派生产物 | lane 独立 staging，完整校验后按既有协议原子发布；同目标竞态须验证等价而非原地覆盖 |

这一选择意味着不再依赖同一次 FULL 的跨 pair **内存**去重；两路同 key miss 可各自计算，最多两份，受 Bi 限制。已发布的持久缓存仍可复用，但一路不等待另一路生产，不增加 single-flight。统计和性能验证必须计入重复计算的代价，不能只测不共享输入的小 fixture。

现有 S2a 已为多个 worker 规定同 key 并发 miss 可重复计算，但这不自动证明线程内 store/锁对象安全：实施前核 `ControlDbComputationCache`、root borrow、scratch、transaction factory 的线程归属；必要时为每路构造独立 adapter，保留相同持久根和发布协议。

允许完整、经校验的派生缓存先于整个 Preview 成功存在，不能让其成为业务 READY。失败后清理沿既有保护/TTL 规则，不删除其他执行者已接纳的同 key 值。

上一轮讨论的“并行前只读缓存、末尾统一写全部缓存”不作为本稿方案：它会延长 native/Arrow 候选生命周期，提高峰值并扩大接口改动。本稿只把公共导出和最终 bundle 汇总收敛到协调方。

## 6. 控制、失败、恢复与确定性

- coordinator-only LeaseSession：刷新、checkpoint 持久化和 terminal publish 都由协调方执行。lane 的 checkpoint 读取线程安全停止信号及原 deadline，不直接竞争 CAS。
- 停止信号包含真实 cancel/drain/lease_lost 和内部 peer_failure；后者不能伪装成用户取消或 drain。只允许一个最终业务状态发布者。
- 一路失败后停止另一 lane 并等待回收；已发生的真实取消/失租按现有优先级处理。两路独立业务错误按原 pair 顺序选主错误，保留两路诊断，内部 peer-stop 不覆盖原始错误。
- 两路结果按固定 pair_id/计划位置归并；cache key、records/risk/surface/bundle 的正式摘要规则不变。谁先完成不得影响诊断顺序、导航、默认视图或 READY 内容。
- 使用当前 operation checkpoint 重新执行纯计算，不新增 pair 级持久恢复状态或单独 step；有效缓存可复用。失租后不能发布业务结果，旧线程未退出前不能把它视为已释放资源。
- 单 pair、History、Submit 的原停止/恢复行为保持，公共函数重构须有相应回归覆盖。

## 7. 统计与性能判据

每 lane 独立 Metrics 和有界表项，协调方按 pair 顺序合并，最终仍遵守 D23 的条数/字节上限、缺失值规则及失败不影响业务原则。cache 次数可求和；pair 耗时之和是累计工作时间，不是 Preview 墙钟时间，不能把它当作用户等待时长或新增一个假串行阶段。

用外部验证记录补充 pair 开始/结束单调时间、两路重叠、完整 Preview READY 耗时、worker cgroup peak、主进程 RSS、backend/RS 的资源、OOM events、CPU 秒与采样并行度。阶段内若需要新增产品统计字段，先改 owning 文档与固定向量，不扩成 profiler 或监控平台。

启用必须同时证明：真实 Rust 重任务发生重叠；N1/N2 正式结果一致；选定真实 FULL 大输入的 Preview 耗时稳定改善；内存/CPU 在所选资源档内。小输入可受启动开销影响，不设任意“减半”承诺。具体性能目标在第一次受控对照后提交 Owner；无收益时如实记录，不以“线程启动成功”退出。

## 8. 真实容量参考与限制

以下是 P6 S3 `4b0a2eec72`、05 节点、N1、32 GiB envelope/8 GiB reserve/M24 的完整真实旅程，不是当前 P7 的并行证明。

| tier | worker cgroup peak B | 主 worker VmHWM KiB |
| --- | ---: | ---: |
| t1 | 266403840 | 259712 |
| t2 | 2515931136 | 2334296 |
| t3 | 4636471296 | 4232460 |
| t4 | 6578016256 | 6289824 |

来源：[P6 S3 独审](p6-s3-e-review.md)中的四档 05 fresh 核收记录，本地捕获根 `/home/dev/gdds-test-tmp/p6-s3-v2-sort-functional-4b0a2eec72-fixed/t{1,2,3,4}-control/captured/` 中 resources/result/manifest。四档 OOM 键均零。另一个真实 `t4-identity` 暖身在 N1、48/8/M40 档记录 cgroup peak `16863698944 B`（同独审 §98）；不能把 6.13 GiB 当成所有 t4 的上界。

上述峰值是 worker 生命周期而非 Preview 独占值，不含全栈总峰，不等于预算预约额；不按两倍 RSS 决定 M，不混用极端合成输入、历史配置或不同旅程来声称当前容量通过。

## 9. 审核前必须定稿的事项

设计已经足以启动独立设计审核和 A 包静态准备，但以下不以本稿冒称已解决：

1. 每路半额在目标真实 FULL 输入上的预约可行性；若不足，Owner 选择资源档或修订预算方案。
2. 比较/probe Rust 路径去掉不必要池调度后，线程及 Arrow helper 上限确能满足 N2；结果/生命周期一致性测试覆盖。
3. 独立 lane session 与 operation-level pins 的具体关闭顺序、root/adapter 线程归属。
4. 最终 DC33 输入清单、节点、N1/N2 配置和性能接受标准。本稿提出范围，不代替执行前确认。

不需要等 FE4b 来解决这些后端事项；也不据此提前修改 FE4b、P7 S3 或默认生产资源档。

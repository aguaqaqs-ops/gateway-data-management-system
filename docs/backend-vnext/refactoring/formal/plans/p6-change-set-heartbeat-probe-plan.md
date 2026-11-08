# Phase 6 change-set 摘要与心跳局部诊断

状态：2026-11-06，局部探针已完成，结果经独立审核 §40 通过；现场 lease 根因仍 OPEN。下方分配削减方案待范围审核，不授权新的 Submit、正式测量或产品修正。

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

## 单次结果与接续（2026-11-06）

实施 handoff `22251147a8`，独立审核 `d240b1e599` / [报告 §40](p6-submit-single-step-diagnostic-scope-review.md)：固定 manifest `c5163458bf7c289fb6ea7f16c45ef83dff07aa4d4e48528028de3f3a92ceb548` 的唯一 probe completed、exit 0，child 14.094 秒、supervisor 14.416 秒、最大 RSS 688,930,816 bytes。一次 digest、一次真实 heartbeat/续租，child 已回收、节点锁已释放。该 GO 已消耗，不重跑或扩规模。

审核确认心跳发生在完整 JCS serialization 窗口内；handler 入口相对应到时点晚 5.223ms，入口到实际 attempt 96.719ms 含 checkpoint 扰动，heartbeat 本身约 0.215ms。这证明本次合成输入可以续租，不证明现场约 24GB 堆上的行为。保留的前 64 个 GC 窗口均早于 worker 开始，只能利用聚合值，不能据此关联 digest GC。其余 checkpoint/fsync、窗口截断、join 未独立计时的限制继续有效。

以下复用既有只读源码分析，不再启动相同调查或完整旅程。它是一个可审阅的资源削减候选，不是已判定的 lease 根因修复。

## 冻结 e798 的分配与校验链

| 位置 | 顺序及同时存活的主要对象 | 本候选处理 |
| --- | --- | --- |
| `_changeset.build_change_set_closure` | 保留 planner snapshots、mutation 列表及 ordered tuple；排序验证后首次 `compute_change_set_digest` | 不改变 snapshots、列表生命周期、排序和调用次数 |
| `compute_change_set_digest` | 类型检查、ordering、全部 `to_document`，然后完整 `{"mutations": [...]}` 的 Unicode、数值、JCS、raw SHA-256；原 mutations 与新 payload 并存 | 仅评估取消完整 JCS 输出 bytes 的聚合 |
| `ChangeSetClosure.__post_init__` → `ChangeSetArtifact.__post_init__` | 构造 artifact 再次核排序、计算 change-set digest 并比较 manifest；再次构造全量 payload | 保留校验、重复计算及错误顺序，不引入可信构造捷径或 memoization |
| `compute_change_set_closure_digest` | 再构造完整 `{"manifest": ..., "mutations": [...]}` 并 JCS/hash，原 closure 引用仍在 | 同样仅评估取消完整 JCS 输出 bytes |

`CanonicalStorageKey.to_document` / `PersistedRowImage.to_document` 会为每个 cell 创建包装 dict、复制 envelope 外层 dict，并创建列表。字符串和部分嵌套值可以共享；frozen dataclass 不等于嵌套深不可变。三次全量载荷构造是顺序发生的，不能把各次峰值简单相加；局部返回后引用释放及 GC 行为也不能仅凭源码推算停顿。

现有 `canonicalize_json_value` 完成全树 Unicode 检查后才检查全树数值，再调用固定 `rfc8785==0.1.4` 序列化。输出 bytes 随后交 `raw_blob_digest`，无 domain prefix。整体 payload 的构造异常先于 JCS；逐 mutation 边校验边 hash 会改变后部 Unicode 错误与前部数值/序列化错误的优先级，故不采用。原库序列化时的内部浅拷贝、排序、字符串编码仍可能分配，不能把去除整块输出描述为整体有界内存。

## 单一最小候选：保留全局验证的 JCS 摘要输出

只评估 shared_kernel 拥有的 JSON 值直接摘要入口：先沿用原全树验证顺序，再由原 `rfc8785` writer 向私有 SHA-256 sink 输出，全部成功后返回 `DigestRef`。与 `raw_blob_digest(canonicalize_json_value(value))` 的成功值、错误类别、错误码和优先级一致；失败时不返回部分摘要。不得复制 JCS 规则、改变 JSON 前像、增加 domain prefix 或在 backend 自写编码器。

writer 与原 bytes API 共用验证及原序列化异常映射，保持现有 bytes API 供实际需要字节的 consumer 使用。这不是保留被替代热点作为回退：选中的 digest consumer 只有新输出路径，不做运行时 fallback；bytes consumer 的原职责继续存在。writer 仅供受控内部 BytesIO/hash sink 使用，不建设可插拔存储或 IPC 框架。

hash sink 使用固定、至多 64KiB 的暂存区合并细碎 write，再交标准 hashlib；大块直接更新，不能为缓冲再次聚合整份输出。此上限只约束新增 sink buffer，不约束序列化器内部单个字符串或原 payload。实现前确认固定依赖 writer 的实际语义、类型签名及原异常映射；若无法复用则报告具体差异，不悄悄换库或升级依赖。小块输出与 Python 回调可能增加 CPU，不能预设更快。

backend 接入限定 `compute_change_set_digest` 和 `compute_change_set_closure_digest` 两个消费点；所有输入构造、排序、全局校验及 artifact/closure 的再次验证保持。暂不处理其他 digest、映射循环、worker 调度、lease anchor、TTL、stall、Rust 接口、checkpoint 或清理协议。基线仍基于 e798 及已有独立 RS 修正，不合入新 main 来替换冻结对象。

## 比例化验证与进入实施的条件

先由接续审核者复核本范围；通过后由设计分配明确的产品实现责任，不能把上一探针 GO 复用为产品或测试运行授权。共享 `jcs.py` / digest helper 与 backend 两消费点会影响新开发线，实施前同步精确范围、合入前核对实际提交与其冻结点。

拟议验证仅在专用调试节点的 clean、已提交 worktree，按实际占用与离线前提进行：

- shared_kernel 作为 JCS/hash 不变量的唯一测试 owner：小样本字节对应摘要，覆盖空值、字符串转义/Unicode/键排序、数值边界和固定 buffer 边界；以现有 golden 和原公开 bytes 结果为对照，保留跨成员 Unicode/数值/序列化错误优先级及异常映射。不为每个内部 write 步骤建测试。
- backend 只验证真实 change-set 与 closure 的摘要绑定、错误 digest 拒绝及代表性跨 mutation 错误顺序，不重复共享层全矩阵，不引入 Dolt fixture。
- 一次限域 focused 验证及仓库要求的五包 ruff/mypy 静态检查；不因改动小就宣称当前镜像通过，后续必要产品镜像/恢复门禁按实际改动面另行绑定。不先跑六包全量或完整真实数据旅程。

本次 probe 已不能提供新旧对照；不得修改其文件、用其时长判改进或自动补跑。是否做额外小规模分配对照，在候选收敛后按剩余问题提出单一具体范围；没有绝对速度门槛。若仅能证明省去整块输出而无法解释/消除现场续租失败，明确保留该缺口，再决定下一项局部措施，不靠放宽 TTL 或盲目全量重试收尾。任何恢复 Submit 或正式基准，仍须独立的候选、镜像与恢复资格审核。

# S2b D：Worker 配置、执行控制与生产调用链

状态：**实施与独立审核进行中，尚无 D GO**（2026-11-06）。C 产品 `0048040af5`、handoff/容量 `7cd2b548c8`、独立 GO `e9bef6efe8` 已收齐；06 在 C 交接时释放、C 二角色结束，现由 D 使用。DC87 已关闭容量配置前置：12 GiB/4 GiB/显式 M8 GiB、N1/单 active。当前为本节新建的 **GPT-6.1-Sol/high 实施者、GPT-6.1-Sol/max 独立审核者**；本节涉及实际租约、冻结恢复、跨阶段资源预约，故审核选择 max。DC88 已批准正常 drain 的纯重算让出，仍须完成其实现及下述真实 worker/容器验收。

## 1. 实际接入点

`settings.py::OperationWorkerSettings` 当前以 `GATEWAY_BACKEND_OPERATION_WORKER_` 为环境前缀，固定 `max_in_flight=1`、claim limit 与既有 lease/heartbeat/drain 设置；不要因新增 kernel N/M 顺带放开既有生命周期预算。`bootstrap/operation_worker.py::run` 创建生产 Preview、Submit、History 依赖并组装 registry/runtime；显式 kernel 初始化应在任何 kernel operation 注册/派发前完成，不改为一次假 parse。

`operations/worker_runtime.py` 持有一个 active executor 和 `LeaseSession`，已有 heartbeat、drain 监督与 fencing。`ExecutionControl` 保留 cancel、drain、lease_lost 三个原始状态；`LeaseSession` 是 operation-owned checkpoint、READY/Attempt 正式输出与业务终态 mutation/publication 的串行入口。内容 key/TTL 等 derived cache 维护沿 C 的短 UoW，当前 Head/Archive CAS 沿 C 的既有事务 owner；cache 登记不等于正式 operation 发布，也不能绕过后者的 fencing。D 将这些真实 owner 接入 A/B/C，不能另建并行租约、逐文件租约或发布状态机。

生产 parser 的直接 native owner 固定为 `capabilities.table_access.native`，只导入 `gateway_compute._native._parse_sql_native`；bootstrap `operation_worker` 只用 `_init_kernel_native` 初始化共享池。Rust policy v5 拥有这两个已批准 consumer 的边界；snapshot materialization 不越过 Table Access 直接调用 parser，既有 capability DAG 与精确导入规则保持，不加 IMPORT/cycle baseline。

完整 caller 列表以整体 kickoff §2 为准：上传 FULL 两侧、Preview baseline、History exact commit、repository-ref 的 READERS_REQUIRED/ARTIFACTS_REQUIRED、Submit/T1/PREPARED 与恢复，以及 export/import-replay 的真实调用面。C 提供真实 store/ref/recovery 能力与事务 hooks，D 接生产 IPC 路由及 operation control；E 清理最后剩余 caller 和被替代算法。每个迁移点记录旧消费者、新入口、证据 owner 与剩余引用，避免只切上传路径。

C 经明确理由与独立审核暂记的五个生产不可达项见 [C 任务单 §5](p6-s2b-c-kickoff.md#5-验证与完成条件)；本节接入真实 Preview/History/Submit 等 consumer 后逐项从 `UNREACHABLE_MODULE_BASELINE` 删除。保留 Python import-boundary/cycle/reachability gate，native 调用边按 Rust policy §4 的精确 owner/entrypoint 规则，不靠假 import或延续临时例外完成接线。

实际 payload 接线沿 [Snapshot Table Access 的目标 manifest](../../../contracts/snapshot-table-access.md#s2b-内部规范表边界)：复用公共 artifact wrapper，canonical 明示 arrow-ipc/none/绑定 repository_id，raw parquet/zstd/repository_id=null；严格新形态不双读旧规范格式。Preview/History checkpoint、canonical closure、Submit frozen reader 同步，客户端 surface/export 经有界列式转换获得真正 Parquet。格式分界不改业务 scalar profile/digest，也不以 generic reader 越过 T1/PREPARED 来源冻结。

D 首个生产 parser 切换后，原 parser 的六个模块已失去生产入口，仍暂作本阶段差分参考。按既定 E 删除范围，允许 `UNREACHABLE_MODULE_BASELINE` 临时精确记录 `gateway_backend.capabilities.table_access.` 下的 `sql`、`_sql_reader`、`_sql_scan`、`_sql_statements`、`_sql_types`、`_sql_values` 六项。独立审核核实际只剩 test/diff 消费者；E 将预期移交到独立 fixed vectors/Contract 后删除六模块及 entries，不得保留到 S2b exit。不得新增生产引用、假 import、IMPORT/cycle baseline 或永久 oracle。此项与 C 的五个新能力临时项不同：后者仍须在 D 真实接线后移除。

RepositoryRef 实际接线采用 Snapshot Materialization owning contract 中的小型 `committed_tables` port：capability 仅 metadata/选表/identity，application 用 C 实现，composition 注入所有真实选表/导出消费者（包含 publication 的 READERS_REQUIRED）。INITIAL/identity-only 不需 port、不读行；需要真实表而缺 port 时拒绝，无旧 rows fallback。不反向导入 application/storage_projection，不扩 native 白名单。返回 SnapshotTable 的句柄存活、exact commit/repository、caller control/deadline/timeout 与健康 cache hit 沿同一 owner 验证。

## 2. N/M 前置和生命周期

沿已批准 kickoff §5：`GATEWAY_BACKEND_OPERATION_WORKER_KERNEL_THREADS` 为整数 1..256，正确性默认 1，4 仅是后续调优比较点。每进程初始化一次固定 N 的 Rayon pool，PyArrow CPU/I/O pool 同步为 N。adapter 不再每次自由设置 `pool_threads=1`；未初始化或 N 冲突稳定拒绝。不同 N 的验证分进程，不重置 OnceLock。

`GATEWAY_BACKEND_OPERATION_WORKER_KERNEL_MEMORY_BUDGET_BYTES` 的 M 是单 operation 的 bytes 预约，不是 RSS 硬上限；缺失/非法值按已批准 required-setting 约定拒绝启动。Owner 已按 DC87 选择 A：单 worker 容器 limit/envelope **12 GiB**、reserve **4 GiB**、显式 M **8 GiB（8,589,934,592 bytes）**，本档 M 上限同为 8 GiB，N=1、单 active。部署示例显式填写 M，不能把它变成缺配置时的隐式 fallback，也不能从 06 的 32 GiB 推导。启动验证 `M <= envelope - reserve`，配置声明与实际部署限额一致；不为此建设通用 cgroup 自动发现框架。配置选择不等于 production worker capacity PASS，D 仍须实测。

预约覆盖同一 operation 同时存活的输入、parser buffers、规范结果、排序/filter 索引、IPC 及 Vec→PyBytes 复制、打开的 mmap/Arrow views、FULL 双侧和发布 staging。共享 backing/mapping 只计一次，未打开的全局历史文件只计磁盘。增长前拒绝；两个局部 kernel 各自满足 M 不能证明其同时存活总量满足 M。复用 A/B 的有界控制并按 C 实测生命周期串接，不引入全局 allocator 追踪框架。D 接线后记录实际 worker 峰值与预约偏差，不将 RSS、page cache 或 cgroup limit 混同预约。

实际 worker 校准可先以既有 t4 FULL 两上传侧、INITIAL 空 catalog fixture，经真实注册的 `materialize_inputs` handler、Runtime/LeaseSession 执行到 checkpoint/后继 PENDING；这是该阶段的容量证据，不等于整个 worker 容量通过。后续仍使用 Python 的 comparison 双侧 rows/cell frames、keyed/keyless/ordered 索引与 records，以及 records 的 Arrow/Parquet spool 和 Submit replay/打包重叠，按真实 changed/selected 表在现 pair/Submit 边界纳入可解释的保守预约与持有期。已有 rows/file/spool/package quota 可用于上界，但须与当前 operation 剩余额度合并，不能计入 4 GiB runtime reserve 后略过。沿既有 owner 做增长拒绝与必要阶段校准，不提前迁移 S3 算法或建设 allocator 框架。reader 传播的 stop/deadline/resource 拒绝必须保留控制类别，不能被普通表错误降级吞掉；返回句柄的关闭仅释放资源，不能在已提交交接后再次制造停止异常。

代码核对发现 S2a parser 的原配额不包含整体 live bytes，且先保留全部 chunk builders 再 merge。D 因真实 operation M 接线补局部 `max_live_bytes`：采用分配前、源序确定性的整次预预约，覆盖 phase A 元数据/jobs、builder capacity/merge/Arrow 转移；SQL 借用由外层计一次。新增整体额度不足使用文档级 `RESOURCE_LIMIT_EXCEEDED` / `max_live_bytes` / offset 0，原配额定位与成功语义不改。规则归 [Snapshot Table Access](../../../contracts/snapshot-table-access.md#s2b-生产-parser-的-operation-预算)。具体估计与小规模边界测试由实施/独立审核核实，不以设计批准预判容量通过，不引入 allocator 框架或重跑旧全量差分。

D 的 staging 预约同时覆盖普通 entry/文档数据及独立 tar 扩展头工作量。已确认标准库在返回成员前读取 PAX/GNU，不能以成员 expanded quota 冒称整个读入有界；按 [SourcePackage Contract](../../../contracts/source-package.md#扩展头与增长前资源准入) 增长前准入并委托固定 stdlib parser，保正常格式/路径语义。普通 ArtifactStore source 读取也先按 opened fd 核真实 size，再 bounded read，与 ref 预约一致；oversize 损坏仍走原错误/root 边界。各沿已有 owner 做一个有界拒绝回归，不引入同 euid 对抗协议或全量解压压力测试。

## 3. 取消、deadline、租约和冻结恢复

kernel probe 可在 cancel/drain/lease_lost 任一状态到达时停止长调用；返回后由 caller 读取原始 control 决定分类，不把三者合并为用户取消。没有 operation 固定截止时传 `deadline_monotonic=None`；真实 finite deadline 原样使用单调时钟。不能用可续租 lease deadline、drain timeout 或 benchmark ceiling 构造 operation timeout。

EOF、kernel 完成和发布前仍核真实 control。lease_lost 必须沿现有 LeaseSession 禁止 checkpoint、正式 artifact 引用和业务终态发布；局部未挂接临时产物沿原清理规则处理，不新增逐文件租约证明。异常不返回成功的部分 projection/manifest。native abort/OOM 的恢复边界仍是原 Operation Runtime 接管，不能冒称 Rust panic envelope 覆盖进程终止。

生产接线须重新覆盖 C 已定义的四种恢复状态：T1 前重新 Preview；T1 后/PREPARED 前冻结缺损稳定失败，不重新选来源；PREPARED 复用冻结包；已提交派生副本按 exact commit 核验回填。Archive Head CAS/引用事务继续由 C 的真实 owner 承担，不在 D 将 Head 推进挪到 Submit finalize。

Owner 已确认 DC88：尚未产出新 checkpoint 的、已注册 PURE_RECOMPUTE 且 effect 前阶段，真实 drain 下可经有效 LeaseSession/CAS 转已有 RETRY_WAIT，保留旧 checkpoint/prior outputs/业务保护并立即可重领；独立 drain 诊断使下 claim 不增也不重置失败次数，保留 operator recovery session 语义。cancel 优先，失租禁写，外部 effect 后仍走原 reconcile，不能把 drain 塞进普通 retryable failure 或冒用 healthy external wait。具体 owner 及验证见 [lifecycle Contract](../contracts/operation-lifecycle-and-integrity.md#正常-drain-的纯重算让出dc88)。不新增 schema/status，最小 LeaseSession/R5 接线仍须独立审核和真实 worker drain→重领验收。

## 4. 比例化实施与验收

1. 在 C 的接口和容量输入固定后收口 settings、startup 一次初始化及预算传递。focused 验证非法/缺失 N/M、重复初始化冲突、同池复用；不改既有 lease 参数含义。
2. 逐个接生产 caller，优先一条真实 Preview FULL 链，再覆盖 baseline/History、Submit/recovery 与其共用读写边界。沿既有 Contract/golden 验证业务结果与冻结绑定，直接替换目标路径，不增加生产引擎 flag。
3. 用真实 worker integration 覆盖运行中 cancel/drain/lease_lost、EOF/cancel-before-publish、真实可选 deadline、M 增长拒绝/单表超限/FULL 重叠；沿现有 owner 测语义屏障，不复制 worker runtime 的全套内部时序矩阵。
4. 在最终候选做受影响静态/架构与必要容器门禁。settings/env/startup/Compose 接线必须有当前候选真实容器证据；检查 Compose 示例和 worker startup 所用值一致。完整 04 runner/container 与 t1–t4 正确性仍留给 S2b 最终候选，已通过未影响的证据按既有规则引用。

日常执行在 06 的 clean committed worktree，沿 C 交接的节点占用、离线缓存、固定 ref 源码同步和日志规则，不占 CT108 正式线。D 开始时新建既定实施/审核二角色；模型与强度按 DC86 在创建前记录。实质设计缺口、容量不足或重复失败交 Owner；明确小问题实施者修复、审核者复核。

## 5. 与原基准线的边界

准备时核到原基准冻结产品 `1f9731dfc3` 的 bounded JCS 修复不在 B 产品 `b820321c1e` 的祖先中，对应主线文件也尚未包含这份修复；原线继续其 h 局部诊断。该修复不因 D 准备自动合入，待原线给出共享修复的固定提交、独立审核、适用证据与合入安排再评估影响。

W4 租约失效仍 OPEN，不能假设 Rust 切换已经解决，也不以原基准产品结果替代当前 D 的 lease/control 证据。W1/W2 性能补验最迟 S6、W3 从 S3 起按已批准安排执行；未知数值不记 PASS。此稿不改变或接管原线的冻结 worktree、镜像、输入、卷、占用或测量工作。

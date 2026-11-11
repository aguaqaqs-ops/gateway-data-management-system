# P7 S1b 基础统计与只读查询详细设计稿

日期：2026-11-11。状态：**产品未实施、未进行产品验证；当前修订结论和受审 SHA 见[仓库外最新报告](/home/dev/gdds-stage-exchange/p7-s1b/reviews/design-workflow-rereview.md)。** [原独立复审](p7-s1b-independent-rereview.md)的 GO 仅绑定其列出的设计 SHA256 `b9a19624228bec64a47a34c4239b9c3a6be34e33abcefdb46b60da25e0094086` 和计划 SHA256 `e7f994aa965ab8b1803769ce3749aeb773d872cc57eabb3ebefb0c914c6d9798`，不覆盖本次新增内容；历史过程见[首轮审核记录](p7-s1b-design-review.md)。Owner 最新授权新实施会话按[实施计划](p7-s1b-execution-plan.md)连续完成 A–F 至本地 S1b exit，实质阻塞等待明确答复；当前会话仍只补文档，不提前实施、测试、部署或 push。

依据：[P7 总体设计](p7-design.md)、[执行计划](p7-execution-plan.md)、[Owner 决议](p7-s0-owner-decisions.md)、[比例化保障政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)。本文收敛此前 S1a/P7 草稿中的通用共享归属与精确计量设想，不追改 S1a 的历史验收事实，不放宽业务事务、权限、数据保护或恢复约束。

## 1. 产品基线和目标

产品基线为本地 main / `be-b-exit`：`3e5f24583dee3d3c44705e4ef34557890557568b`；此前 `p7-s1a-exit` 为 `42780a12303c8040526bf5dc8f9c6f0acb12dbb1`。两阶段最终独审均已通过，附注 tag 绑定审核与测试来源。S1b 使用 S1a 的布局/资源身份和 BE-b 后的实际产物；不以当前较早 FE 分支的代码代替产品基线。

首版在单组、单 worker 下回答三个问题：设备最近为何增长、一次任务耗时和资源怎样、整盘主要占用在哪里。统计服务于容量分析与故障排查，非计费或精确审计账本。**减少复杂度优先于提高测量精度**，允许延迟、小幅并发误差和明确的缺失。

交付三个模块：占用采集、任务观测、只读查询。S1b 以接口为主；详细可见页面可以独立建设，必要时有独立展示后端，但不成为本阶段退出前置。无需等待 FE4b 截图或接入完成。

## 2. 边界和明确非目标

- 设备有独立 repository/Dolt 库；全局目录维护设备到组的归属，组内维护设备到 repository 的映射。组内共用进程、control DB 和 root，不等于设备共享业务数据。
- Dolt 内部块、历史结构复用和 GC 由 Dolt 负责。外部只观测库目录；不分析每版本独占块或修改 Dolt 结构。
- 规范表、diff/risk、导出和原始输入仍是 Dolt 外产物，按已有 repository 关联统计；规范表/导出缓存的 repository scope 继续有效。
- 业务状态、幂等、审核、checkpoint、保护和清理由原 owner 负责。统计不能决定任务已提交、解除保护、触发 GC 或删除业务对象。
- 不增加通用引用图、跨设备成本分摊、跨环境 SHA 去重、硬链接全局索引、reflink/thin pool 成本分析或物理量强制核平。
- 不增加消息队列、可靠事件投递/outbox、采集 receipt、统计恢复状态机、查询会话、独立采集服务或新特权。
- 多 worker、跨组汇总、外部映射/回灌和测试抽取仍按 S2/S4 实施；S1b 只保留必要的环境、组和运行实例身份。

## 3. 统计口径

### 3.1 设备与组级占用

| 类别 | 来源和口径 |
| --- | --- |
| repository | RS 对该 Dolt 库目录有界测量；逻辑文件大小和可取得的 allocated bytes 分列 |
| durable / canonical / comparison / export | 复用 ref/cache/业务记录中的 repository 关联和 size；同设备内同一服务的同 artifact ID 只计一次 |
| scratch | 可直接关联设备/任务时记录；其他列组级临时占用，允许采样遗漏短暂峰值 |
| metadata / 公共或未归属 | control DB、RS 元数据、日志、telemetry 及不能简单归属的对象单列，不分摊 |
| filesystem | 通过部署的 filesystem 身份汇总容量、可用字节和可取得的 inode 数；同盘多个 slot 不重复加 free bytes |

location 表示物理类别，Head/Preview 等用途不重复贡献对象字节。IPC 多用途只计一次，另生成 Parquet 是新的 export 对象。BE/RS 和源/测试环境的真实副本分别计算，不按相同内容 SHA 合并。

少量确实多库关联或无法简单归属的对象进入组级公共/未归属桶；不建立每设备共享份额。保护状态已有且便宜时可列出，否则 unknown；不能只统计当前 pins，也不能把未保护量称为立即可回收量。

历史业务 ref 可能在对象清理后继续存在，不能把 ref.size 永久累计成当前占用。后台按有界页读取候选，再用 owning adapter 的无内容读取 stat 确认可见存活对象；找不到则不计入当前存活量，失败/截断标 partial。预算内未核实的引用量必须单列或不返回，不能与当前测量混加。首版无需为此建立持久对象索引或删除事件账本。

设备对象逻辑汇总与文件系统实际占用允许不相等。allocated bytes 仅为该扫描范围的文件系统观测，不称独占物理成本；标准工具若已处理本次扫描内硬链接，保留其能力，但不为此新建全局 inode 账本。压缩、快照、thin pool 和外部目录开销不反推归属，差额不命名为垃圾。

### 3.2 repository 写入观测

RS 在首次实际导入写库前和结果确定后设置轻量接点，关联 RS operation、repository、已知前后 commit 和可取得的业务 ID，失败尝试也保留。测量有明确时间/条目预算，不阻止下一业务写入来等待统计完整。

实际取得对应窗口且同口径的 before/after 才产生净变化；`logical_net_change_bytes` 与 `allocated_net_change_bytes` 分列，各自可负，不能用 allocated after 减 logical before。已知窗口混入其他写入/维护时标记 partial/interference；某口径前后缺失则该净变化为 null。最近后台值可另作参考，附其时间，**不能冒充本次 before/after**。每次写入都有机会留下观测，但不保证每次有完整增量。

不为测量执行 GC、获取覆盖整个扫描的业务独占锁或延长事务；无法在预算内得到数据就缺失。只有未来确有归因需求时才安排专项串行回放，不把它列为 S1b 必跑旅程。

具体时序为：RS 本次执行开始、原有 repository_execution 范围内，非阻塞通知后台扫描；正常继续 package 校验等工作。在 `create_private_ref` 首次 mutation 之前只记录单调时钟 cutoff。仅本次请求的扫描已完整结束且 end≤cutoff 才能成为 before；未赶上就 null，不等待、不同步补扫。pipeline 返回（含既有失败清理）后记录 end cutoff 并请求 after；after 必须完整且 start≥end cutoff。已知下一写入介入标 interference；不为其建立持久写入世代协议。每次都有观测记录的机会，不要求每次有净变化。

### 3.3 资源和时间

CPU 用可读取的进程/cgroup 累计计数在同实例窗口内求差；平均使用核数由 CPU 时间/窗口时长得到。内存记录采样峰值，不对生命周期 HWM 求差；进程 RSS 与 cgroup 内存分别标范围。I/O 使用实际可取得的计数和单位，不假装是设备独占物理 I/O。

worker 执行窗口可能含常驻开销；共享 RS/backend 观测保持服务范围，不归为单设备独占消耗，不相加不同时间的进程峰值。缺计数器或权限时为 null/unavailable，不增加宿主权限。

排队、执行和上传等阶段使用已有时间事实；不存在可靠时间来源则缺失。耗时使用单调时钟，展示时间使用 UTC。进程实例变更、计数下降或窗口不完整时不跨实例求差。业务结果和观测完整性是两个独立字段。

### 3.4 逐尝试性能摘要（P7-D21–D24、D27）

逐尝试摘要另收产品已经算出的输入形态：表数、总行数、最大表行数、SQL 字节数、变化表数、变化行数、有序表行数；记录解析、物化、比较、风险、导出、bundle、RS 导入、finalize 的分阶段耗时，以及各层缓存查找/命中整数。附一个有界表数组，项为表名、比较模式、前后行数、变化行数。已有描述符、比较事实和缓存分支是来源，不为统计重读 SQL/表内容、重算比较或扫描历史产物。允许在现有阶段边界加单调时钟、在现有缓存分支加普通整数计数；未运行或来源不可靠为 null，已完整观测且未命中才是 0。阶段有嵌套或不同窗口时保留范围，不相加伪造总耗时。

复用执行摘要记录及其 claim 窗口键，不新增性能账本：每次尝试/执行窗口一行，加一个受条目数和记录字节约束的表数组；多 pair 的表项保留已有 pair 标识以区分，不改变业务尝试协议。数组截断保留总表数和截断标志，不能把截断子集当全量输入。此摘要取代 `s3_pair_metrics` 临时日志作为持久查询来源，写失败仍不影响业务。实施计划明确字段、接点和验证责任。

P7-D27 对新增扫描/profiler/服务的限制针对上述性能细分，不取消 Owner 已批准的 §3.1–3.3 有界资源采样和目录占用观测。W1–W4、H1–H3、S1–S4 原数值性能目标已由 P7-D21 撤回，P6 历史结果不改。真实操作不因期限、租约或内存上限失败仍是功能门槛；默认不做引入新机制的优化，按 P7-D22 以真实累计耗时占比和预期收益取舍，缓存以实际命中率决定是否列为删除候选。

## 4. 模块、存储与采集责任

### 4.1 部署和写入

在现有 backend application/query、HTTP 和后台生命周期内实现统计；backend metadata 的独立 telemetry 子目录保存独立 SQLite 数据库，**不并入 control DB 事务**。使用标准 SQLite 事务、有限批量和短锁等待。采集方使用有界内存缓冲，关闭时只有限等待，缓冲丢失不阻止退出或恢复。

worker 记录本实例任务窗口；backend 负责设备汇总、后台拉取和查询。RS 只在自己的 roots 上测库和本服务资源，经既有认证 HTTP 边界提供有界只读观测供 backend 后台拉取；不让 backend 挂载 RS 库。具体 RS route/DTO 在实现前按 repository_contracts/client/service 同步定稿，不新增 transport 或可靠投递协议；RS 可用有界内存保存尚未读取的观测，重启或满额允许丢失。

事件只传现成标量/标识，不在业务回调内序列化大对象、扫描目录或同步写统计 DB。SQLite 锁/写入失败、采集队列满和 RS 拉取失败均不撤销业务成功。队列既限制条目数也限制单条/总字节；失败日志限频。复用既有后台任务机制，不新增通用调度平台。

现有 `WorkerRuntime._emit` 会直接调用 observer 且没有成功执行结束事件。新增专用 telemetry adapter 在自身边界隔离普通采集异常；不得通过吞掉整个业务/原 observer 的异常实现“非干扰”。在实际 executor 调用前和其 finally 中记录开始/结束，仅表示执行窗口，不凭返回推断业务成功；business outcome 从既有提交结果/记录读取，无法确认则 unknown。shutdown、lease lost 和线程启动失败保持原有语义。

采集和统计查询不调用会改变业务状态的预检。S1a `runtime_preflight.observations()` 当前先调用 `check()`，实现时拆取窄只读来源或复用已经确认的配置事实，不能把调用这个方法直接当成无副作用采样。

### 4.2 最小记录模型

以下为逻辑记录模型，不要求为字段额外引入框架。物理 SQLite DDL、索引及既有 attempt 字段映射在实施准备时收口；不增加平行的业务尝试编号。

| 记录 | 核心字段 |
| --- | --- |
| 占用快照 | environment/group、repository（组级为 null）、类别、对象数、logical/allocated bytes；filesystem 类另带 filesystem_id、total/available bytes、available inodes；window start/end、generated_at、quality/reason |
| 写入观测 | environment/group/repository、RS operation、既有尝试关联、已知 submission/前后 commit、before/after 各自值与时间、logical/allocated 净变化分列、observed outcome、quality/reason |
| 执行窗口摘要 | environment/group、repository、operation/既有 attempt/step/claim_version、worker 与进程实例、阶段时间、业务结果观测、CPU/采样内存/I/O/scratch 摘要、§3.4 输入形态/阶段耗时/缓存查找与命中整数及有界表数组、非空记录时间、quality/reason |
| 资源样本 | scope（任务窗口或共享服务）、运行实例、可选 attempt/claim_version 关联、sampled_at、可用计数、quality/reason |

摘要关联程序 revision、规则/输入身份及 storage/resource 配置摘要；硬件类别、冷暖条件等没有可靠来源时标 unknown，不扫描宿主或伪造。配置公共字段可去重保存在同库，避免每秒重复大载荷，不要求持久来源证明。

一次 Submit 可有多个 RS 写入尝试，不能以 submission ID 覆盖之前观测。业务 API 仍是当前业务状态权威；缺统计行不代表未执行。可从现有元数据重新核对当前占用，但过去曲线、写入前大小、资源峰值不可重建，不宣称删除 telemetry 后能恢复历史。

BE 业务尝试保留 `(operation_id, step_id, StepRecord.attempt_count)`，但它不唯一标识执行窗口：现有健康等待/纯计算 drain 的再次 claim 可保持 attempt_count。每个执行窗口使用 claim 时 `ClaimedWork.step.optimistic_version` 固定为 `claim_version`，键为 `(operation_id, step_id, claim_version)`，不随 heartbeat 更新。业务 `SubmitAttempt.submit_attempt_id` 是另一关联。一个 attempt 下可有多个窗口，摘要、样本和 API 均保留该区分，不覆盖旧窗口或跨进程求差；这是复用既有非秘密版本，不新增业务尝试协议。`process_instance_id` 划分进程计数窗口。RS 环形观测的 observation ID/读取位置仅供短期去重分页。

### 4.3 周期与背压

| 参数 | 本轮确认的初始值/行为 |
| --- | --- |
| 任务开始/结束/结果 | 事件记录，尽力保存 |
| 运行中资源采样 | 1 秒，批量写入；不保证捕获短于间隔的尖峰 |
| 文件系统容量采样 | 60 秒 |
| 设备占用 | 变化后安排更新，10 分钟目标周期低频轮询补齐；按有限批次执行，不承诺全部设备准点完成 |
| 细曲线保留 | 7 天 |
| 摘要/低频趋势保留 | 90 天 |

所有周期和保留期可配置，首版随服务正常重启生效，不建设配置写 API/热更新。重复“设备有变化”通知可按 repository 合并，缓冲满时由后续轮询补齐。目录扫描分批、有时间和条目上限，允许并发变动误差；不锁整库、不生成强一致扫描快照。

## 5. 空间上限与故障降级

每组设置 telemetry 总预算，包含 DB、WAL 和维护余量；不是只限制行数。7 天曲线是正常容量条件下的目标。默认字节值按实际记录、索引、采样实例数和 7 天样本数测算，再写入运行配置；不得假称未经测量的固定 GiB 值足够。

清理按有限批次进行：先删除超保留期记录；空间压力下优先清理最旧细曲线，必要时早于 7 天。仍不足则暂停新增采样，摘要尽力保存；不继续无限缓冲、不扩大磁盘预算、不删除业务数据。SQLite 删除后页可复用但文件未必缩小，不能以已删行数冒充磁盘已回收；使用标准 SQLite 空间/WAL 管理，不在业务热路径做全库 VACUUM。

数据库不可用时，业务照常执行，统计接口按既有错误格式明确返回统计不可用。采集健康可保留进程内的有限状态和限频日志，不依赖先成功写入坏掉的统计 DB。恢复后继续采样，返回实际覆盖范围、已知丢失/清理原因；不填零、插值或回填不存在的历史。

启用后逐步补当前设备占用，历史资源从启用时开始；未测量显示 not_collected。统计库 schema 不符或损坏时停用统计并报告，既有业务 control DB 检查不变；不自动删库或静默迁移。人工修复/受控重建统计库须明确历史观测丢失。

## 6. 只读查询与导出

### 6.1 API 能力及权限

沿用现有 HTTP session、repository scope；现有代码没有通用运维角色，本阶段只在普通 session permissions 中新增 `statistics_read_group` 只读权限用于本部署组级容量/服务指标。不把拥有恢复写权限的 internal bearer 交给独立展示系统，不增加认证体系。精确路由/DTO 见实施计划。

| 查询族 | 输入 | 权限/输出 |
| --- | --- | --- |
| 设备占用 | repository | 设备读取权限；最新分类量、测量时间、质量 |
| 趋势/写入 | repository、时间范围、分页 | 同上；占用趋势和写入观测明细 |
| 执行摘要 | operation 或 repository、时间范围、分页 | 核业务归属；各次尝试的摘要和直接相关指标 |
| 曲线 | attempt 或服务 scope、时间范围、点数上限 | 设备仅看获准任务范围；共享服务详情限运维 |
| 组级容量/健康 | 当前环境/组 | 运维；filesystem、公共/未归属、采集状态和允许公开的配置 |

详细技术指标由运维查询承载，设备接口优先提供可解释摘要。所有标识都先解析业务授权再访问统计；不凭 telemetry 中的孤立关联授予权限，不泄漏其他设备身份。外部展示后端只能通过授权 API，不读业务 DB/挂载业务卷。

设备当前占用/趋势/写入列表使用 `workspace_read` 加当前 enabled mapping 的精确 repository 校验；操作/执行曲线沿既有 `authorize_operation_read`，History 则沿 `authorize_history_compare_operation_read` / `read_project_history`。`statistics_read_group` 不绕过这些设备/操作权限，不默认为全设备浏览授权。业务 owner 记录缺失时拒绝对应设备/操作查询，不能用 telemetry 重新造授权。

基础字段含数值和明确单位、scope、window start/end、generated_at、`quality=available|partial|unavailable`、可选稳定 reason。初始 reason 范围为 not_collected/counter_unavailable/counter_reset/interference/budget_exceeded/retention/collection_failed；可用只表示按已声明口径可解释，不是逐字节精确证明。有效零与 null 区分。绝对路径、凭据、原业务 payload 不返回；原始配置摘要以外的详情限运维。

### 6.2 分页、曲线与导出

普通稳定排序加有界分页即可，可沿现有游标模式；不建立跨页快照、持久查询会话或一致扫描 generation。并发更新/保留清理可造成跨页少量变化，下一轮刷新获得新结果。

时间范围、页大小、曲线点数、导出条数和响应字节都有有限上限。曲线需要降采样时使用简单时间桶，返回桶宽/样本数及必要的平均/最大值，不用单纯平均掩盖峰值，不跨缺口插值。长窗口查询仍限制读取/聚合成本，不能仅限制最终输出点数。

JSON/CSV 导出复用相同过滤和权限，每次有界；超限返回明确错误或分页继续信息，不静默截断。不增加导出任务、文件仓库、任意全量下载或服务器路径参数。CSV 按标准转义并防止外部文本被电子表格解释为公式。

每 backend 同时只允许一个导出准备/发送，使用普通进程内 semaphore，忙即返回 429 `STATISTICS_EXPORT_BUSY`，不排队。持有到响应完成/断连/失败的清理结束再释放；scratch 仍受原有额度约束，不用多个32MiB响应绕过统计内存/磁盘边界。

HTTP 查询仅访问已生成数据；页面刷新不触发采集、重算、GC 或写配置。暂不提供“立即精确刷新”接口。数据库正常但尚无样本返回空/未采集；数据库整体不可用返回明确服务错误，两者不混淆。

## 7. 工程收口责任

下列工程内容已在[实施计划](p7-s1b-execution-plan.md)给出源码落点、字段/键/索引、接口与有限初值；编码时按计划实现并测定容量。不是新的 Owner 阻塞问题，不把“可配置”当成无默认值或无限制。

| 事项 | 最小完成要求 |
| --- | --- |
| DTO/OpenAPI/SQLite DDL | 将 §4/§6 模型映射到基线已有 ID 和路由；枚举/单位/null/权限一致，必要索引支持有界查询 |
| 缓冲、批量、锁等待和扫描预算 | 明确最大条目/字节、batch、时间、单轮扫描量及失败行为；不影响业务事务 |
| RS 接点和读取 | 首次实际写入前/结果后、失败尝试、服务采样；复用既有 transport/auth，Contract/client 同步 |
| 容量默认值 | 以实际行/索引/WAL 大小与采样实例数计算 7 天预算；记录实际结果和余量，有限配置先用于 focused 验证 |
| 查询/导出上限 | 页/时间/点/字节均有界；普通分页，不新增查询协议 |
| 接点可得性 | 核实 owning adapter/缓存/业务关联实际来源；拿不到则 null/公共或未归属，不承诺通用 lineage |
| P7-D23 摘要 | A 固定字段和来源，B/C/E 接已有数值与边界计时/整数，D 查询同一受限载荷，F 核真实可查和缺失/截断语义 |

若接点实际不可得且替代方案需要修改业务顺序、增加特权/新服务或强一致计量，才带具体损失与替代方案重新讨论。普通字段、内部表名、可逆配置和批量参数自主确定。

## 8. 实施顺序与 Contract 影响

1. 按 BE-b exit 核接点、权限和已有业务身份，定稿记录/DTO/配置及查询上限。
2. 建独立 telemetry SQLite、有限缓冲/批写/保留和故障降级，接 worker 运行窗口。
3. 接设备分类汇总、RS 窄观测、后台轮询及写入窗口；处理缺失和重启计数。
4. 增加五类只读查询和有界导出，更新 OpenAPI/运行说明，形成真实输入可查询证据。

新增观测不进入 canonical、comparison、surface、bundle 的业务 digest 或缓存身份，不为统计改变 golden。BE-b 新增对象按现有 ref/location/归属计数，不复制专用导航计数算法。若实现确实触碰 owning Contract，按实际边界同步，不能把期望“不改”冒充已验证不改。

实施时新增统计接口的 owning 说明及必要 OpenAPI；RS 只读观测涉及 repository_contracts/client/service 同步；Operation Lifecycle 只说明 best-effort hook，不增加业务状态。S1a 已交付接口是来源，不宣称统计 API 已存在。

## 9. 验证和退出

遵守 main 的专用节点资源池、clean 已提交源码、离线缓存、日志和阶段门禁规则；不以旧 FE 工作区的节点表覆盖 main。日常 focused 在合格空闲节点按现场占用运行；最终由自动阶段门禁固定 04、同一门禁 worktree 选择受影响包并判定运行/carried，04 忙等待，不迁移旧证据。若触及容器生命周期/挂载/配置或阶段退出要求，完成相应容器门禁，不提前假定可沿用。流程以 P7-D25–D27、S0 §11 和实施计划为准：取消专职测试者，A–F 每节新实施和不同家族新独审上下文，按风险缩小 C/D 类审核范围；F 的新独审覆盖阶段全范围，不重复叠加一轮。

| 行为 | 最小验证 |
| --- | --- |
| 分类汇总 | 同设备同对象多用途只计一次；BE/RS 真副本分别计；公共/未归属不强制分摊；同盘 free 不重复 |
| 写入与尝试 | 成功/失败/重试分别可查；同attempt的健康handoff再次claim不覆盖前窗口；受控scanner/时钟验证完整before/after的正负差值及错过cutoff/截断为null，不能只实现null；缺失不填零 |
| 资源 | CPU/I/O 实例内计差；重启重置不产生假增量；采样峰值/共享服务范围明确 |
| 逐尝试摘要 | 现成形态/阶段耗时/缓存查找与命中整数与来源相符；有效零和缺失不同；多 pair/多 claim 不误覆盖；表数组和整条载荷上限、截断标志明确 |
| 非干扰 | 统计不可写、短锁等待超限、缓冲满时，既有业务结果/事务/保护不改变 |
| 保留和查询 | 有限保留/容量降级、分页/导出上限、授权与路径不泄漏；查询不扫描业务 roots |
| 真实链 | 一个已有真实设备输入，经实际业务链得到可查占用、摘要、曲线与写入观测；记录覆盖/缺失与采集开销 |

真实输入的具体档位、模式、次数与节点在实施 kickoff/验收准备按 DC33 一次确认，不从 BE-b 的 t1/t4 许可自动继承。使用最小代表链，不把全 t1–t4、多轮容量/性能或未来多 worker 矩阵列为默认验收。开启/关闭采集的有限对照报告 CPU、内存、耗时、统计磁盘增长及运行条件，不承诺零开销或伪造通用百分比阈值；明显影响业务再修正。

P7-D24 继续有效：N>1 开放调参前，必须以一次真实 N=2 端到端旅程核正式结果和 digest 与 N=1 一致，最迟 S5 完成，不另建性能矩阵。S1b 默认 N=1，不开放 N>1；本阶段未执行则明确移交 S2a/S5，并由 S5 退出核收，不能把缺证据写成通过。阶段退出的真实 t4 旅程须保存 §3.4 逐尝试摘要、输入身份、配置和结果引用作为同输入参考，不设数值阈值；S1b 未获 DC33 t4 范围时不擅自增加或冒领旧旅程，移交后续阶段最迟 S5 闭合。试运行“现象到参数”映射表同交 S5。

不要求逐字节核平设备总量与整盘使用，不要求每次提交完整增量，不要求独立页面。测试按公开行为收敛，共用参数表、不为纯统计逻辑引入真实 Dolt fixture、不复制业务 recovery 矩阵。

退出前交付实现/Contract/OpenAPI、有限默认值及依据、真实可查询示例、必要门禁、已知误差/缺口和运行说明。过程日志、审核、角色提示词、门禁原件和 t4 参考放仓库外 `/home/dev/gdds-stage-exchange/p7-s1b/`；正式设计/Contract 仍入库，退出仅另提交一页阶段总结，引用原件不复制过程墙。设计落稿、绑定摘要的独审、产品实现和测试通过分别记录；本次修订不能继承旧摘要的 GO。

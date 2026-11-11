# P7 S1b 基础统计与查询实施计划

日期：2026-11-11。状态：**产品未实施、未验证；当前修订结论和受审 SHA 见[仓库外最新报告](/home/dev/gdds-stage-exchange/p7-s1b/reviews/design-workflow-rereview.md)。** [原独立复审](p7-s1b-independent-rereview.md)的 GO 仅绑定设计 SHA256 `b9a19624228bec64a47a34c4239b9c3a6be34e33abcefdb46b60da25e0094086`、计划 SHA256 `e7f994aa965ab8b1803769ce3749aeb773d872cc57eabb3ebefb0c914c6d9798`，不覆盖本次修订。Owner 最新授权新实施会话连续完成 A–F 至本地 S1b exit，实质阻塞等待确认；当前会话只准备文档，不提前实施、测试、push 或部署。

设计依据：[S1b 详细设计](p7-s1b-statistics-and-query-design.md)、[S0 决议 §8/§11](p7-s0-owner-decisions.md)、main 已有 P7-D21–D27、[门禁与交接规格](p7-gate-and-stage-workflow-design.md)、[审核记录](p7-s1b-design-review.md)。产品基线 `be-b-exit` / main=`3e5f24583dee3d3c44705e4ef34557890557568b`。当前文档工作区在较早 FE 分支，代码核对使用 `git show/grep main`；编码应从实际 main 开始，若 main 已前进，先只核增量是否改变下列接点。

## 1. 交付范围和工作方式

一组一 worker、已有设备库、现有进程和信任域。交付有界占用采集、执行摘要/7天曲线、写入观测及授权只读 API/JSON/CSV 导出。公共/未归属单列，不分摊；不建立通用引用图、历史物理账本或可靠投递平台。详细展示和独立展示后端另行建设，不阻塞本阶段。

按 A–F 顺序形成可审的小提交；遵守 main 开发、测试节点 clean 已提交 worktree、离线缓存及阶段门禁规则。Owner 最新授权覆盖新会话 A–F 产品/Contract/测试/正式文档同步、必要验证与普通修复复审、本地提交、最终独立核收和满足退出条件后的本地附注 `p7-s1b-exit`；正常推进不逐节再申请，不含 push/部署或进入 S2。真实范围尚未确认的部分仍按 DC33 一次确认，不把完整实施授权解释为任意扩大真实数据清单。

一个持续协调者；按 Owner 本轮每节新角色要求，A–F 每节分别新建实施与 Astra 独审上下文，按实际风险缩小 C/D 类审核范围，不因此增加完整门禁；F 的新独审覆盖全部 A–F，无需另叠一轮相同全范围独审。取消专职测试者；focused 由实施者执行，阶段门禁由协调者触发脚本。角色/模型固定如下，不沿用 S1a 早期 Sol 自家独审或 Luna 测试分工：

| 角色 | 模型/强度 | 责任 |
| --- | --- | --- |
| 持续协调者 | `gpt-6.1-terra` / high | 核基线/授权、风险和提交，触发自动门禁，串行追加阶段日志，交付/退出，不代签独审 |
| 每节实施者 | `gpt-6.1-sol` / high | 新上下文，实施及 focused、普通修复和本人资源收尾 |
| 每节独审；F 覆盖阶段全范围 | `gpt-6-astra` / xhigh（复杂判断可 max） | 不同模型家族、新上下文、只读 clean detached 候选；同 finding 由原审持续复审 |

子角色显式模型/强度并 `fork_turns="none"`，任务单绑定候选、路径、依赖和可写范围；不静默替换模型，不递归扩队，最多四个活跃角色含协调者。当前文档修订结论以页首外部报告及其受审 SHA 为准，不把协调自查或旧摘要 GO 当作新签署。真正无法在授权范围解决的来源/业务冲突、范围变化、他人资源或指定模型不可用才交 Owner；阻塞等待明确答复。暂停时可保留本人仍需使用的 worktree、进程/资源及占用标志，登记用途和现场状态，不为暂停强制释放；恢复前复核，实际完成清理且无消费者后再释放，不触碰他人资源。

## 2. 已核源码与最小改动位置

下面首项给完整路径，后续 `backend/.../` 指 `vnext/backend/src/gateway_backend/`，RS 指 `vnext/repository_service/src/gateway_repository_service/`；新增路径为实施目标，可按仓库现有依赖层规则小幅调整，但不得把产品逻辑放进 benchmark。

| owner/现有接点 | 实施动作 |
| --- | --- |
| `vnext/backend/src/gateway_backend/operations/worker_runtime.py` `_run_claim` / 内层 `execute` | executor 调用前及 finally 记录窗口；不改变 join、heartbeat、lease 和异常传播 |
| 同目录 `worker.py` `ClaimedWork`、`WorkerEvent`；`state.py` / `persistence.py` | 取 committed operation/step；attempt_count在健康handoff可保持，窗口键为operation/step/claim时optimistic_version，不复用SubmitAttempt ID；现有observer没有成功完成事件 |
| `backend/.../bootstrap/operation_worker.py`、`bootstrap/composition.py`、`app.py` | 注入 telemetry no-op/active adapter；启动角色采样和有限批写，关闭只有限等待 |
| `backend/.../infrastructure/control_db/schema.py` 及只读 adapters | 读现有 mapping、cache、业务关联；不往 control DB 增加 telemetry 表、触发器或事务 outbox |
| `backend/.../infrastructure/artifact_store/local_store.py` `observe_object` | 后台有限 stat 核对象存活与大小；不读内容、不获取保护、不把历史 ref 永久累计为当前占用 |
| `backend/.../runtime_preflight.py`、RS 同名文件 | 复用启动后的配置身份/纯读取辅助方法；`observations()` 调用 `check()`，不能直接用于周期采集 |
| `backend/.../http/auth.py`、`http/orchestration/operation_scope.py` | 复用当前 session/permission/mapping，增加一个组级只读 permission；复用 History 独立授权路径 |
| `vnext/repository_service/src/gateway_repository_service/versioned_import/worker.py` `_execute_operation` | 在已有 repository_execution 内非阻塞请求 before；pipeline结束后请求 after，不增加扫描锁/等待 |
| RS `versioned_import/command.py` `_run_pipeline` | 在首个 `provider.create_private_ref` 前记 mutation cutoff；不只围住 commit，失败路径也保留观测 |
| RS `runtime.py`、`app.py`、`layout.py`、`storage_roots.py` | 使用 RS 自己的库目录/注册映射；生命周期接后台扫描和有限环形观测，不暴露路径 |
| RS `artifact_observation.py` | 现成单 ready artifact stat；不是全库扫描或写入观测实现 |
| `vnext/repository_contracts`、`repository_client`、RS HTTP | 同步窄统计 feed DTO/客户端和 bearer 保护；复用 HTTP transport，不改变原 import 响应 |
| `backend/.../application/pair_pipeline.py`、`capabilities/comparison/production.py` | 复用 `s3_pair_metrics` 现成比较/风险/导出时间、`ComparisonRunMetrics` 及表比较事实，改接摘要 sink；不解析日志作产品数据源 |
| `backend/.../application/preview_jobs.py`、`history/compare_jobs.py`、`submit_jobs.py`、`application/submission/finalize.py`；现有 parser/materialization/bundle 调用边界 | 复用输入描述符和已有 cache 分支，补边界单调计时/整数命中；A 列清具体函数/来源，缺失为 null，不读取大对象补数字 |

新增 BE 模块建议为 `statistics/models.py`、`statistics/ports.py`、`statistics/collection.py`、`statistics/query.py`；SQLite 放 `infrastructure/statistics/sqlite_store.py`，采样放同目录 `sampling.py`，HTTP 放 `http/routes/statistics.py` / `http/schemas/statistics.py`。RS 可用 `statistics.py` 和 `http/routes/statistics.py`，先按最小实现拆分，不建设通用框架。

## 3. 进程、数据流和生命周期

### 3.1 backend 与 worker

backend 和 worker 已共享本组 metadata；各角色只有一个有界 telemetry 缓冲和一个批写/采样循环，使用独立线程自己的 SQLite connection。原 executor/HTTP 业务回调只传受限字段并 nonblocking offer。采样文件读取、JSON 编码、SQL 和清理都不在业务回调内执行。DB 不可用、缓冲满、线程无法启动时只降级统计。

新增 `TelemetrySink.begin_execution/end_execution` 是专用 best-effort adapter，默认 no-op。调用边界隔离其普通 Exception，保留 KeyboardInterrupt/SystemExit 和既有业务控制流；不把整个 executor 或原 observer 包进吞异常。`end_execution` 在 executor 的 finally 内调用，其后必达原 completed/wake 信号；结束只表示执行窗口，不代表 operation 成功。

资源采样面向当前进程和可读 cgroup，使用标准库 `/proc`/cgroup 读取，单次读取字节有界，缺计数器 null。worker 同时最多一个 active execution，维护一个内存关联即可；不以线程 CPU 值冒充 Rust 子线程总 CPU。process_instance_id 每次进程启动新建，计数差只在相同实例计算。

`begin_execution` 从 `ClaimedWork.step` 捕获 `claim_version=optimistic_version` 和 attempt_count；直到 end/sample 均用该固定值，不随 lease heartbeat 的后续版本变化。`claim_attempt_count()` 对健康等待和纯计算drain重领可保持 attempt_count，因此同attempt的多个窗口分别保存，不能用(op,step,attempt_count)做upsert主键。单个窗口内的缺失样本不补零，跨窗口不相减累计计数。

摘要业务 outcome 从原执行 acknowledgment/权威记录读已确定结果，unknown 合法；不增加同步查询来阻塞提交。Telemetry 中保留的 outcome 是历史观测，不作为 GET operation 的权威来源。启动时已有历史仅补当前占用，不回填资源曲线。

### 3.2 RS 写入观测

严格保持异步，不引入“20ms 同步扫描”例外。执行开始且已取得原 repository_execution 后，向现有统计循环请求本次 before 扫描；正常继续 package 校验。在首个 mutation 前记单调 cutoff，检查本次扫描是否已经完成，不等待。完整且 scan_end≤cutoff 才接纳 before，否则 null。后台扫描若未开始而 cutoff 已过，可取消该次 before 工作。

`executor.execute` 返回（含失败处理/清理）后记 end cutoff，请求 after；只接纳 scan_start≥end cutoff 的完整结果。现有下一次执行开始事件与 after 扫描重叠时标 interference，不阻止下一次执行，也不建立持久世代/精确维护追踪。pipeline 在 mutation 前失败时记录失败尝试和无写入信息，不制造增量。没有可靠 committed after 值则 null，不凭成功函数返回猜 commit。

before 请求早于 package 校验有机会完成，但无命中率保证；首版允许真实链中的某些乃至全部写入净变化缺失。若这样不能满足后来实际用户问题，再讨论测量成本；本阶段不能为非空数字改业务顺序。

RS 不新增持久统计 DB。有限环形 feed 保存资源样本、设备占用和写入观测，backend 每 5 秒拉取已生成记录。记录的随机 observation_id 只供 SQLite 去重；feed 的进程实例/递增序号仅用于普通分页，重启可重置、溢出可丢失，不发 ack、不重放、不影响 import。backend 拉取超时只丢本次，下一周期继续，业务客户端不等待。

### 3.3 占用来源和存活判定

按 enabled `provisioned_scope_mappings` 有界页轮询；变化通知只将 repository 放进有界去重集合，满额依靠下一轮轮询。每库候选来源固定为 canonical_table_cache、snapshot_table_export_cache、computation_cache_entries 的 manifest/member refs，以及 Workspace/SubmitAttempt/Submission/Head 等现有结构化 ref owner。只读专用 adapter 每次短事务取一页，关闭事务后 stat；不在 stat 扫描时保持 control DB 读事务。

编码 A 包列出实际采用的每个 ref 字段和已有 decoder；不递归探索任意业务 JSON、拉全历史 bundle 或全表拷入内存。拿不到简单归属则公共/未归属，不建 lineage。候选在本轮按 `(service_owner, artifact_id)` 去重，有限集合最多 10000 个；达上限则发布 partial、known_count 与截断原因，不能把它称完整总量。

只有 owning adapter 确认当前 payload 可见的对象进入 measured logical/allocated bytes；not found 不计且记录 stale candidate，其他错误为 partial。不需要逐字节 hash 验证。元数据有引用但未核实的大小不混入 measured；若显示则另名 `unverified_reference_bytes`。同对象重复 stat 可缓存于本轮有界集合，不持久化对象账本。

RS repository 使用已有 create_repository 事实和 layout 决定根目录：为 `MutationStore` 增加只读keyset页，关联 `synchronous_mutation_effects` 与 `mutation_idempotency`，限定 succeeded/create_repository，按effect_id每页至多100条取得resource_id；不全量调用旧iter_effects、不执行Dolt。每600秒目标周期轮询一轮，已存在的发布目录由 `DurableLayout.published_repository(repository_key(id))`定位，后台scandir分片、总时间/条目有限、不跟随symlink；缺目录为partial/null，不触发修复/创建。SQL也受有限执行预算，过大可分轮完成。

不同 slot 的 public/unknown/temporary 量能便宜获取才给数值，不能扫描完整则 partial/null。backend与RS各自每60秒通过纯statvfs采集本角色配置root的filesystem容量，RS经新增`filesystem_capacity` feed记录传入，backend存为category=filesystem快照。组API只取已保存值，按配置filesystem_id去重，同一filesystem优先最新观测（等时按service_owner固定排序），不相加；缺跨服务身份时分别显示“无法合并”，不凭相同容器设备号合并。不需要组API请求时跨服务采集。

## 4. 记录、SQLite schema 与索引

数据库位于本组 `be-metadata/telemetry/statistics.sqlite3`，backend/worker 同一服务用户可写；不新增卷或 UID。单一基线 schema，`PRAGMA user_version=1`；结构不匹配/损坏只禁用统计并报诊断，不自动删除、不影响 control DB 的既有严格检查。DDL 在 `sqlite_store.py` 定义并在空库短事务创建；普通已有数据库只读核结构后使用。

全部时间落库 INTEGER UTC microseconds，耗时 `duration_ms` 来自 monotonic；bytes/count 为非负 INTEGER，净变化可负，缺失 SQL NULL。环境/组/业务 ID 用现有字符串/UUID编码；不复制 lease_token、原始 payload、服务秘密或物理路径。JSON 仅用于受限指标载荷，禁止无限自由字典。下表规定必须查询的结构列；实现可将其余有界字段置 JSON，不改变外部 DTO。

### 4.1 P7-D23 受限摘要载荷

在下表 `execution_summaries` 增加 nullable `metrics_json`，复用原 claim 键和 upsert，不增性能表/索引/投递协议。DTO 使用固定 typed 对象而非自由字典：

| 字段 | 固定内容/来源与限制 |
| --- | --- |
| `input_shape` | `table_count,total_rows,max_table_rows,sql_bytes,changed_tables,changed_rows,ordered_table_rows`：非负整数或 null，来自现成 parser/物化描述符/比较事实；A 明确当前侧/范围，多个 pair 不重复累计同一输入 |
| `stage_duration_ms` | `parse,materialize,compare,risk,export,bundle,rs_import,finalize`：单调窗口毫秒或 null；现有边界轻量计时，明确 scope/是否嵌套，不将嵌套阶段相加作总耗时；rs_import 首版为客户端端到端时间（含网络/等待），不冒称 Dolt 内部耗时 |
| `cache_lookups` / `cache_hits` | A 列清实际缓存层的固定名字与 scope，至少核 canonical/materialization、comparison、risk_candidate、snapshot export 现有分支；各层查找与命中分别为非负整数或 null，lookup/restore 不混作 hit，窗口/口径相同且分母非零才计算命中率；普通整数计数，不扫描、不建全局 cache 注册表 |
| `tables` | 最多100项；每项 `table_name,comparison_mode,before_rows,after_rows,changed_rows`，有多 pair 时带已有 `pair_id`；名字至多256 UTF-8 bytes，计数可 null；超出不切坏名字，跳过该项并标截断 |
| `tables_total,tables_truncated` | 现有总表项数或 null、截断布尔值；超条目或字节预算只保留可容纳项，不把截断数组当全量 |

`metrics_json` 最多12 KiB，整条事件仍受16 KiB上限，先保留固定标量，再按现有稳定顺序放表项；固定字段也放不下则该载荷缺失并报告 partial/budget_exceeded，不阻塞业务。零仅表示在完整已知窗口实际为零，未执行/缺来源/丢失均 null。每次尝试的不同 claim 窗口仍分别一行，不跨窗口重放或覆盖；同窗口多 pair 有限聚合，未完成字段不清除已有值。性能摘要替代 `s3_pair_metrics` 临时日志，正式业务日志不改成可靠统计协议。

P7-D27 仅限制新增性能细分机制，允许现有阶段边界计时和 cache 分支整数；本文已批准的有界 `/proc`/cgroup 资源采样、目录观测照常实现。A 必须把每字段到具体已有变量/分支/函数的映射写入正式统计说明；拿不到的明确 null，不以补 profiler/重读表补齐。

### 4.2 基线表

| 表 | 字段/主键 | 索引 |
| --- | --- | --- |
| `storage_observations` | id INTEGER PK；source_event_id TEXT UNIQUE；environment_id/group_id；repository_id nullable；service_owner/category；object_count/logical_bytes/allocated_bytes nullable；unverified_reference_bytes nullable；filesystem_id nullable、total_bytes/available_bytes/available_inodes nullable；window_start_us/window_end_us/generated_at_us；quality/reason | `(repository_id,category,window_end_us,id)`、`(category,filesystem_id,window_end_us,id)`、`(window_end_us,id)` |
| `execution_summaries` | environment/group；operation_id/step_id/claim_version/attempt_count；process_instance_id/worker_id；repository_id nullable；submit_attempt_id nullable；started_at_us/ended_at_us/duration_ms nullable；recorded_at_us NOT NULL；observed_outcome；cpu_time_us/rss_peak_bytes/cgroup_peak_bytes/read_bytes/write_bytes/scratch_peak_bytes nullable；revision/config_digest/rules_digest/input_digest nullable；metrics_json nullable（§4.1固定载荷）；quality/reason；PK `(operation_id,step_id,claim_version)` | `(repository_id,recorded_at_us,operation_id,step_id,claim_version)`、`(operation_id,step_id,attempt_count,claim_version)`、`(recorded_at_us)` |
| `resource_samples` | id INTEGER PK；source_event_id TEXT UNIQUE；environment/group；role/process_instance_id；operation_id/step_id/attempt_count/claim_version nullable；sampled_at_us；cpu_time_us/rss_bytes/cgroup_bytes/read_bytes/write_bytes nullable；quality/reason | `(role,process_instance_id,sampled_at_us,id)`、`(operation_id,step_id,claim_version,sampled_at_us,id)`、`(sampled_at_us,id)` |
| `write_observations` | observation_id TEXT PK；environment/group/repository_id；rs_operation_id/process_instance_id；BE operation/submission 关联 nullable；before_commit/after_commit nullable；before_start/end_us、after_start/end_us nullable；before/after logical/allocated_bytes nullable；logical_net_change_bytes/allocated_net_change_bytes nullable；observed_outcome/quality/reason；recorded_at_us NOT NULL | `(repository_id,recorded_at_us,observation_id)`、`(rs_operation_id)`、`(recorded_at_us)` |

execution_summaries 的同一claim窗口start/end使用upsert；end事件可能单独到达，start保持null/partial，绝不补造。`recorded_at_us`为首次成功落库时间，后续upsert不刷新，90天清理按它执行，即使start/end均未知也可清理。SQL合并只更新已知字段，不因end未知覆盖已有值；同attempt的旧claim不覆盖新claim。RS 同 observation_id 的后续完成观测在 ring 追加新sequence，backend upsert补齐已知字段且保留首次recorded_at；同sequence重复拉取不重计，不能原位修改旧sequence而让已前进的读取游标永远漏掉after。其他快照/样本的source_event_id由进程实例/序号派生，避免拉取重复计样本。这只是普通短期去重，不增加持久投递状态。

category取repository/durable/canonical/comparison/export/scratch/metadata/public_unknown/filesystem。filesystem记录的repository_id=null、filesystem_id非空，其total/available bytes和可用inode来自同次statvfs，object/logical/allocated字段为null；其他类别容量字段为null。写入两种净变化分别由同口径前后完整测量计算，不足则分别null。resource_samples的operation/step/attempt/claim_version四字段要么全null（共享服务），要么全部提供（执行窗口）。

组内只有一个 environment/group，启动核与配置一致；跨组不可共用此 DB。无跨 control DB 外键或级联删除，业务记录缺失时权限查询拒绝，历史统计按保留期清理。

## 5. 有限参数与空间行为

下列除已确认周期/保留期外，均为**工程起始默认值，非容量实测承诺**。允许在包内依据 focused 数据调整并记录，不必向 Owner 逐项请示；不能改成无限值或突破既有业务资源预算。

| 配置（建议 `GATEWAY_STATISTICS_` 前缀） | 初值/上限行为 |
| --- | --- |
| ENABLED | true；false 使用 no-op，查询明确 disabled |
| SAMPLE_INTERVAL_SECONDS / FILESYSTEM_INTERVAL_SECONDS | 1 / 60 |
| STORAGE_REFRESH_SECONDS / RS_POLL_SECONDS | 600 目标周期 / 5 |
| CURVE_RETENTION_DAYS / SUMMARY_RETENTION_DAYS | 7 / 90 |
| QUEUE_MAX_ITEMS / QUEUE_MAX_BYTES / RECORD_MAX_BYTES | 512 / 4 MiB / 16 KiB，先到先限，满不阻塞 |
| WRITE_BATCH_ITEMS / WRITE_BATCH_BYTES / FLUSH_SECONDS | 128 / 256 KiB / 1 秒 |
| SQLITE_BUSY_TIMEOUT_MS | 50，仅后台统计连接，不改业务连接 |
| STORAGE_PAGE_SIZE / SCAN_SLICE_ENTRIES / SCAN_SLICE_MS | 100 / 256 / 50；时间为协作预算，不声称可抢占单次 filesystem syscall |
| SCAN_TOTAL_ENTRIES / SCAN_TOTAL_SECONDS | 每库每轮 10000 / 2 秒，达限发布 partial；不接续为强一致 snapshot |
| RS_RING_ITEMS / RS_RING_BYTES | 4096 / 16 MiB，满丢最旧，返回 dropped/覆盖范围 |
| RS_HTTP_TIMEOUT_SECONDS / FEED_PAGE_ITEMS | 2 / 100，响应上限 1 MiB，取消/超限不无限重试 |
| RETENTION_BATCH_ROWS / MAINTENANCE_SECONDS | 1000 / 60，过期删除与压力清理均分批 |
| SHUTDOWN_FLUSH_SECONDS | 1，丢缓冲不延长业务 drain；后台循环读/写均有界 |
| EXPORT_CONCURRENCY | 每backend 1；进程内semaphore，忙即429 STATISTICS_EXPORT_BUSY，不排队 |
| TOTAL_BUDGET_BYTES | 初始 2 GiB/组，是预算而非“能保7天”的保证；首次节点验证必须测量后校准 |

SQLite 初始 page_size=4096，main DB max_page_count=`floor(TOTAL_BUDGET_BYTES / 2 / 4096)`，2 GiB初值对应262144页（1 GiB）。总预算剩余用于WAL和维护余量；WAL观测软阈值为`min(128 MiB, TOTAL_BUDGET_BYTES/16)`。每个写入连接核相同页上限；短事务/短读，wal_autocheckpoint 使用标准有限设置，maintenance 先用非阻塞 PASSIVE checkpoint；WAL达软阈值时以busy_timeout=0机会式TRUNCATE checkpoint回收可截断文件，读者阻止时不等待。注意 journal_size_limit 不是活动 WAL 硬上限，不能据此宣称严格总额保证。调整预算只在正常重启生效；缩小到现有DB大小以下时停写统计并说明原因，不自动删库。

每次有限批写前查 DB/WAL 大小和现有 filesystem 低水位；达预算/低水位则只做可行清理、暂停采样，保持足够批次余量，不循环写错误记录。多进程竞态可有一个有限批次的观测超量，明确为工程预算；不建跨进程配额仲裁。删除先用过期项，再最旧曲线；SQL 页回收复用而非立刻缩文件，不在热路径全库 VACUUM。长期空间无法恢复则停止统计并人工处理，不自动删库。

暂时不可写/锁忙/容量压力由后台每60秒有限重试打开或检查，不忙循环，不重试业务操作。schema不符或损坏保持统计停用，人工修复后重启恢复；不通过自动重建伪装修复。服务业务readiness不依赖统计可用，组统计健康说明当前降级。

容量校准在测试节点用真实 schema 的样本插入测 DB+索引+WAL 实际平均大小，按角色数×604800 样本/角色/7天，加摘要和趋势、维护余量估算；记录输入与结果。若 2 GiB 不足，可配置更大**已有授权资源内**预算或明确实际覆盖缩短，不把默认保留目标当精确承诺。依赖仍优先 stdlib/现有包，不因统计默认加数据库服务。

## 6. HTTP/DTO 与权限定稿

### 6.1 backend 路由

下列 URL 为新统计接口，不兼容旧占位格式。公用 `schema_version=1`，质量 `available|partial|unavailable`，原因允许 disabled/not_collected/counter_unavailable/counter_reset/interference/budget_exceeded/retention/collection_failed。单次响应标明单位、窗口、生成时间及实际覆盖；DTO 不返回存储路径或业务原文。执行摘要及同权限 JSON/CSV 导出承载 §4.1 固定字段，表数组在 JSON 中有界嵌套、CSV 中按标准转义的 JSON 单元格表达，不增表级查询协议；有界表名/模式属于已授权 operation 的技术指标，组级资源接口不返回这些设备明细。

| GET 路由 | 权限/返回 |
| --- | --- |
| `/v1/repositories/{repository_id}/statistics/storage` | workspace_read + 当前 enabled mapping 精确 repository；最新分类项 |
| `/v1/repositories/{repository_id}/statistics/storage/history` | 同上；按时间排序的有限趋势 |
| `/v1/repositories/{repository_id}/statistics/writes` | 同上；写入观测，不返回输入包内容 |
| `/v1/operations/{operation_id}/statistics/executions` | 复用原 operation read 分支，History 用 read_project_history + acceptance；所有 step attempts 摘要 |
| `/v1/operations/{operation_id}/statistics/resources` | 同上；必填step_id、attempt_count，claim_version可选；先查该attempt的有限执行窗口再分别取曲线，不跨窗口/进程连接 |
| `/v1/statistics/group` | 普通 session permission `statistics_read_group`；当前配置组容量/公共开销/采集健康 |
| `/v1/statistics/group/resources` | 同上；role和process_instance_id必填，走对应复合索引；共享服务曲线去掉operation/设备标识 |

不新增全设备任务浏览接口。设备统计不要求调用方拥有额外运维权限；组只读权限不等于所有设备访问权，也不能调用恢复管理 API。部署管理员在原 session 文件显式授予 `statistics_read_group`，无新 token 服务；独立展示不得使用内部 recovery bearer。

集合公用参数 `from`/`to` UTC、limit、cursor，默认 limit=100、最大500；cursor 采用时间+稳定主键，长度上限2048字节，不建持久查询会话。from<to，普通摘要/趋势最大90天；资源默认最近1小时、单次最大6小时、max_points默认600/最大2000，服务端原始读取上限50000行且SQL时间预算1秒，超限显式缩小范围错误，不静默截断。仅普通客户端分页，不保证跨页强一致。

每条时间曲线只对单scope/process实例或已授权的claim窗口查询，按时间桶给avg/max/count；未指定claim_version时最多返回100个窗口的独立series，超过则要求选择claim_version，不将同attempt多个窗口或不同实例累计计数连成一条。每次总读取/输出仍遵守统一上限，不按series倍增。counter delta在同实例同窗口有效区间计算，缺口不插值。组摘要只提供各角色当前/最近实例标识供客户端选取，不新增无限实例目录。单查询读完有限数据立即关闭DB read transaction，不随客户端下载保持事务。

有界导出复用以上集合端点，参数 `export=false|true` 默认false，`format=json|csv`默认json；format=csv隐含export=true。普通JSON模式limit默认100/最大500；export模式limit默认1000/最大10000且32MiB/响应，权限、时间范围及SQL/扫描预算不变。两种模式均可分页，不增加独立endpoint或持久导出任务。结果先在有限内存/既有scratch中准备再发送，避免半途超限却报成功；分页元信息用标准response headers表达并在OpenAPI说明，不能创建长期导出文件。公式样字符串按CSV规则转义，数字字段保留数值语义。

所有export=true（包括format=csv隐含启用）的准备/发送共用每backend一个导出semaphore，不按本次实际条数绕开；获取失败立即429 `STATISTICS_EXPORT_BUSY`，不等待、不排队。许可在准备、发送和清理全程持有，正常结束、生成异常、客户端断连/取消均释放；scratch仍通过现有额度入口。普通小页JSON沿现有HTTP并发边界。只增加一个并发超限和释放行为验证，不建设独立报表admission平台。

鉴权401/403/404沿 owning route 风格；设备跨scope/映射缺失不泄漏存在性。统计DB健康但无记录返回200加空/未采集；统计禁用/DB失败返回503 `STATISTICS_UNAVAILABLE`，输入/预算拒绝沿现有校验错误格式并给稳定原因，不能把SQL/路径原错误带出。运维健康读取可不依赖数据库成功，使用当前进程有限状态。

### 6.2 RS feed

新增内部 GET `/v1/statistics/observations`，复用 RS `require_bearer_token`；只面向受信 backend 网络客户端。参数 instance_id/after_sequence/limit，输出当前 instance、oldest/next sequence、dropped_count、至多100条受限记录及可用覆盖时间；实例变化/游标落后返回显式 reset/truncated，不自动历史恢复。GET 只取环形中已生成记录，不触发扫描。

DTO包含observation_id、kind（repository_storage/write/resource/filesystem_capacity）、sequence、instance、environment/group、可选repository/RS operation、观测时间及固定类型载荷。filesystem_capacity带filesystem_id/total_bytes/available_bytes/available_inodes及测量时间，不带路径；在RS自己的周期采集后入ring。不能让caller指定路径或要求扫描任意repository。backend按类型写上表并去重；repository UUID和当前组校验后存，不把RS数据当HTTP caller授权依据。现有import/get_operation DTO保持不变；仅新增统计DTO/API/client方法与有限body读取。

## 7. 分工作包交付

| 包 | 必须交付 | focused 与审核重点 |
| --- | --- | --- |
| A 身份与schema/API | 新统计owning说明；本文表/字段落成DDL和Pydantic DTO；默认配置、权限与RS feed契约；D23每字段现成来源/阶段范围/cache层映射 | units/null/大小边界、版本、索引；claim窗口/attempt/SubmitAttempt分开；group只读不授予恢复写权限 |
| B 存储和运行窗口 | 独立SQLite、no-op/active sink、batch/retention、worker start/finally、纯proc/cgroup采样；D23受限载荷及已有阶段/缓存分支接点 | buffered start/end缺失和非空recorded_at保留清理、计数reset；同attempt多claim不覆盖；缺失/有效零、表数组截断、多pair不误累计；统计异常不阻止completed或改变原业务异常 |
| C 设备与RS观测 | 固定来源列表和存活stat、有界扫描、RS异步before/after、ring/client/poll及filesystem容量 | 清理后的旧ref不计现存量；受控scanner/时钟参数化验证完整窗口正负净变化、错过cutoff/截断为null；不能只实现null；不在回调扫描/等待；路径root边界 |
| D 查询与导出 | backend七端点、权限矩阵、普通分页/曲线桶/CSV、OpenAPI | workspace与History各自权限；禁用mapping；不触发扫描；claim分段、SQL/输出上限；导出并发拒绝和结束/失败释放 |
| E 集成与校准 | 生命周期/Compose配置、运行说明、真实schema容量实测、小规模功能链调试 | startup/stop统计失效不阻业务；有限预算；实际采集开销；修复后只复测受影响项 |
| F 最终核收 | 最终candidate必要权威包/容器、一次已确认最小真实链、阶段全范围独审/一页总结/本地exit | 日志/HEAD/exit/节点/缓存身份；carried按现行脚本；真实D23摘要可查；D24未执行责任移交；未测和近似边界明确 |

A只固化必要Contract，不把无consumer的内部helper变成协议。C如某历史ref来源缺失，降级partial而不是重构业务。每包实施与审核以当前公开行为为对象，不建立全故障矩阵；实现出现范围外要求先按复杂度优先删减。风险初判：A 为 B 类（权限/跨服务Contract），B 为 B 类（worker异常和生命周期），C 为 A/B 类（业务写入接点/root边界），D 为 B 类（授权与资源上限），E 按实际 Compose/部署变化为 B 类。A–F 均新独审；纯内部 C/D 类按实际后果缩减审核范围，不能因工作包字母降级，F 新独审同时覆盖阶段全范围。

## 8. 测试、节点和退出

文档阶段不运行产品测试。编码阶段 focused/真实旅程按 main AGENTS 的 DC91/DC97 五节点资源池、现场状态和有效占用执行；所有测试/编译/lint核合格空闲后先原子取得本节点标志，无常规重复申请；stage-gate由脚本取得，勿在外层重复占用；初始 Cargo jobs/pytest workers=4。自动阶段门禁固定04及 `/home/dev/gdds-stage-gate`，04忙则等待后重新触发，不迁移旧carried。测试源码须已提交且clean，SSH BatchMode预核、legacy链接、TMPDIR、UV_OFFLINE/CARGO_NET_OFFLINE及LAN预填充按main；不继承BE-b真实范围或将当前旧FE工作区AGENTS当新规则。

最终V由协调者调用 `scripts/run-stage-gate.py <完整SHA> --packages <实际受影响包> --purpose stage`；准确参数/节点配置以main `scripts/README.md` 与工具为准。由脚本按同节点、同worktree的实际闭包决定run/carried，prepared manifest不冒充实际runner manifest。整次runner失败不收录部分通过、不继续依赖验收；修复按现行快速修复规则保留原始失败，产品失败回实施/原审。中间包只做必要focused及影响后续接线的最小容器验证，最终F集中受影响权威包/容器，不每包全量。S5/发布/production另强制fresh六包，S1b不提前承担。

修改面预计 backend、repository_contracts/client/service；未改Rust时按实际闭包决定运行或沿用，最终包选择/容器判定由现行runner与stage gate脚本产生。涉及进程启停、Compose/env或容器才可证明的权限/资源边界，需要当前候选容器验证，不以宿主unit替代。锁/基础镜像不变则复用现有合法缓存；若变化严格按DC67补齐依赖基础，不临时公网拉取。

最小真实范围提案为合格节点已有t1的一条上传→Preview→Submit→Review/Archive及查询链，含一次正常重复输入以检查无变化/关联；在实施准备按DC33确认具体输入/模式/节点后执行。这里是提案而非用户已经确认该清单；等待其确认不妨碍A–E中无需真实范围的已授权工作。不自动增加全t1–t4或容量/性能矩阵。

P7-D24继续作为退出移交义务：S1b默认产品N=1，不开放N>1调参。N>1开放前须用同一真实输入做一次N=2端到端旅程，核正式结果/digest与N=1一致，最迟S5完成；N是产品kernel并行参数，不能以多个worker或pytest worker数量代替。若未纳入本次DC33范围，F写清未执行并移交S2a/S5，S5最终核收，不能标通过或无声取消。阶段退出已有真实t4旅程应保存D23逐尝试摘要、输入身份、配置与结果引用至阶段区 `reference/<sha>/t4/` 作为同输入参考，不设数值退出门槛；S1b不自动继承BE-b的t4授权，缺少本阶段真实t4来源时明确移交后续阶段最迟S5闭合。S5试运行说明再交付“现象到参数”映射表，不另建性能测试。

N=1/N=2 两次实际旅程保持同产品提交、输入、规则、业务初态、冷暖条件及除 N 外的参数等价，记录有效配置并核实际 N；第二次仅返回既有幂等结果不算 N=2 已执行。用受控等价初态/独立运行范围验证，不为凑执行破坏既有幂等语义。

主要证明：任务统计可查询；before未完成明确缺失而非强求差值；开关统计不改变业务成功/失败与保护；清理/缓冲/查询有界；权限正确。真实存储不必核平，开销有限对照报告实际CPU/内存/耗时和DB增长，不做“必须小于某百分比”的伪造性能承诺。存在明显主路径干扰时先修复，不通过新增复杂隔离平台绕开。

D23用共享参数表验证现成数字、空缺与有效零、计时窗口/缓存命中、表数组/整条字节上限和多pair；不用真实Dolt fixture证明纯载荷逻辑。真实链核摘要可查询且输入身份一致，不能仅记录空对象。P7-D21已撤回W1–W4/H1–H3/S1–S4旧数值目标，P6结果不改；P7-D22要求真实操作不因期限/租约/内存上限失败，性能报告不设新百分比门槛。引入新机制的优化另按真实累计阶段占比/预期收益评估，已有缓存以命中率列删除候选，不为统计顺便做优化平台。

过程原件统一 `/home/dev/gdds-stage-exchange/p7-s1b/`：协调者串行追加 `log.md`，`reviews/<sha>.md` 保存审核及原审复审，`gate/<sha>.json`引用节点原result/run ID/路径/SHA，`reference/<sha>/t4/`存D24参考，提示词入`prompts/`。跨节点复制保留原字节和来源，不能因此取得carried资格。不迁移或改写历史审核，必要正式设计/Contract继续入库。

退出交付列产品提交、文档/Contract/API、已验证范围和缺失比例、D23字段来源与实测默认参数、门禁/容器/真实原件、采集覆盖/保留限制、D24移交及本人资源状态。阶段末全范围独审通过、当前main可达最终H的门禁/容器与已确认真实范围证据闭合后，按最新授权本地创建附注 `p7-s1b-exit`，不重复申请；不预打、不覆盖冲突tag、不push或部署。仅新增入库一页 `p7-s1b-summary.md`（建议约800汉字内）引用原件；总结后的H仍由脚本绑定门禁，不能将总结提交冒称已实测。本人任务完成后收尾释放无消费者资源；有效evidence/carried worktree保留，暂停可保留本人资源并登记，不为结束对话清理他人内容。

## 9. 开工前只需核清的事项

1. 取得本次修订的Astra独审结论/绑定摘要；[旧报告](p7-s1b-independent-rereview.md)的GO仅绑定原SHA，不能覆盖补齐的决议/字段/流程。
2. 新会话A–F至本地exit实施授权已给，按S0 §11和本文推进；无需重新询问已经确认的统计口径、复杂度、保留、角色和界面边界。
3. 从当前main核实际增量，普通文件名/索引可调整但保留本文接口语义和有限参数。
4. 在实际真实验收之前一次确认DC33输入/节点；容量用节点实测校准，不把它升级成新业务决策。

以上是执行状态和验收前提，不再保留未定的核心schema、权限、attempt身份或扫描时序选择。

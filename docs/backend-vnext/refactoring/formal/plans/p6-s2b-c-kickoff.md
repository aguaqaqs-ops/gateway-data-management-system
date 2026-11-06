# S2b C：规范表存储、引用与恢复

状态：**设计准备；尚未启动实施**（2026-11-06）。DC86 已授权逐节推进，但 C 的产品实施须等 B 固定候选、handoff 和独立 GO。当前仅提前核对现有 owner 和落点；B 的最终 API/证据到位后补齐交接，再按 Owner 最新 DC86 补充创建本节 **GPT-6.1-Sol/high 实施者与 GPT-6.1-Sol/max 审核者**。C 涉及 BaselineHead 的事务/CAS、强引用与 TTL 同事务释放及冻结恢复边界，因此选择 max；这不预设 D/E 的强度。本文不表示 B 已通过，也不新增角色。

## 1. 接入边界

只复用 A 唯一 canonical IPC codec 和 B 已验证的业务 kernel，不另写 Python IPC writer。C 接 `CanonicalTableStore.open(ref, bound_descriptor) -> ContextManager[ArtifactReadHandle]`、atomic put、raw SHA、mmap、内容引用与恢复；D 才接 worker N/M 和全部 operation control，E 才完成最后的生产 caller 迁移与旧算法删除。不建立兼容双读、生产 fallback 或引擎开关。

现有实现落点：`artifacts/store.py` 的 minimal ref/内存实现，`infrastructure/artifact_store/local_store.py` 的 root-bound path、temp/fsync/rename，`control_db/sqlite_protection.py` 的事务保护记录，以及 `sqlite_snapshot_export_cache.py` 的 lookup/put/touch/expiry 模式。保留 `ArtifactStorePort.locate(ref) -> bytes` 的真实非规范表消费者，不为新 API 删除仍有用途的通用读口。

内容身份按 DC42 五项与现有 scope：projection version、business schema digest、row count、table digest、mapping version；business schema 已含 table name。外层保留 DDL/导出 row layout。不能以 raw SHA 替代业务摘要，也不能把当前表名不同的对象当成可跨表去重。具体类型与序列化字段应依 B 最终输出收口，不先造平行通用 DTO。

## 2. 文件和读取生命周期

local handle 持有只读 fd/mapping，在同一 mapping 上分块校验 raw SHA 与 size，再以固定 profile 和绑定声明打开 reader；只暴露 schema/batch reader，不暴露路径。内存实现以 BufferReader 保持同一协议。同 ref 再 open 是独立 handle；close 幂等，关闭后 read 稳定失败。arrays/readers 及 Rust 借用不得超出 handle 生命周期；先释放借用再关闭 mapping。拒绝 schema/metadata/profile 或绑定不符及超预算输入，不把 A 的内存 decoder 当作外来 IPC 业务导入验证器。

写入沿现有临时文件和原子 rename，去掉为确认成功而整份读回。实际消费者读取时的校验保留。Rust 不接路径/文件系统；Python/adapter buffer ownership、C Stream 借用和 mmap 保留期必须在实际调用中成立。使用标准 safe API，不能因接 mmap 放开 Rust unsafe 政策或绕过架构守卫。

root/symlink 边界、普通 I/O 错误、协作并发和 crash 保留；按 ADR 0012 不建设同 euid 恶意换名的 broker、隔离 service、持久发布状态机或额外证据机制。

## 3. 引用、事务与恢复 owner

强引用沿 Preview → T1 Attempt 的真实 owner 转移；正式引用只绑定业务 BaselineHead，旧 head 与无强引用对象按 TTL。最后一个强引用释放与 TTL 登记/触达在同一事务；所有强引用释放且无未过期 TTL 保护才可清理。复用先登记保护再检查文件；lookup 对过期条目拒绝命中。

**Head 事务落点是归档，不是 Submit。** DC42 和 Business Lifecycle Contract §5 对应 `application/archive/start.py::start_archive` 的 `save_archived_node_and_cas_head`；`submission/finalize_transaction.py` 只结束 Submit、释放冻结引用，不移动业务 Head。P6 旧措辞已在 `0484b36f14` 订正。正式引用切换与 Archive Head CAS/业务结果同事务；失败不能留下前缀，合法重放不重复改变引用。初始化与当前 head 的精确 commit 回填也要具有正确 owner。归档事务不能新增物化、Repository import 或长文件读取；缓存丢失不能迫使归档重新计算业务数据。

恢复边界不重新选择来源：

| 状态 | 处理 |
| --- | --- |
| T1 前上传侧 | 重新 Preview，从 SourcePackage 重算 |
| T1 后、PREPARED 前 | 冻结文件缺失/损坏稳定失败，不从 parent、新 ruleset 或 SourcePackage 重建，不前移 main |
| PREPARED 后 | 复用已冻结导入包及 raw SHA，沿既有 Submit 恢复 |
| 已提交派生副本 | 读对应精确 Dolt commit，按绑定业务摘要核验后回填；不能读当前 main 代替 |

owning 文档须同步：Canonical Storage §5 旧“仅 Preview/Attempt pin”和泛化 source 重建文字由上述目标替换；Snapshot Table Access、Snapshot Materialization 的 raw Parquet/internal canonical IPC/客户端 Parquet 角色明确分开。直接修改唯一 control DB 基线 schema，不建迁移/双读。不要将缓存索引缺失提升成新的 durable evidence 状态机。

## 4. 容量校准与 D 前置

在本节真实 kernel/codec/store 上测 canonical 列/行、payload/buffers、IPC file bytes、writer/adapter 复制与临时文件峰值。复用既有输入，按已批准范围做有限校准；不每轮重生成合成输入、跑全旅程或接管 CT108 基准。

FULL 校准按实际同时存活项给出峰值：两侧结果、输入与 parser buffers、排序/filter、IPC 输出与边界复制、当前 operation 打开的 baseline/Attempt mmap、发布前 staging。区分 reservation、实际 RSS、page cache/cgroup 与磁盘；同 mapping 共享引用只预约一次，未打开的全局历史文件不计本次 RAM。所有值注明输入、提交、节点、口径和限制。

D 接线前交付有依据的 M/default/max 候选与 worker envelope/reserve 方案，满足 `M <= envelope - reserve`，说明增长前拒绝、单表超限及 FULL 重叠行为。06 的 32 GiB 不是已批准生产 envelope；未知值不填成通过。若实际结果不足以收口，报告具体缺口与方案给 Owner，暂停依赖它的 D 接线，继续不依赖缺口的已授权工作。

## 5. 验证与完成条件

先冻结每个不变量的一个 owner，沿现有 storage/SQLite/Submit/Archive 测试补真实语义，不重复三层矩阵：

- storage：独立 reopen、幂等 close/closed read、借用释放、raw SHA/profile/metadata/绑定拒绝、stream error 无可发布产物、普通 I/O 与真实文件系统原子写入。
- control DB：共享 refs/强引用/TTL expiry、最后释放触达、当前 head 引用及 Archive CAS 原子性/失败/重放；复用现有 protection/cleanup 行为，不穷举内部 syscall。
- 恢复：上述四种状态和 exact commit，沿现有 Snapshot artifact faults 与 Submit T1/PREPARED owner；generic lease/CAS/recovery 不另造框架。
- 容量：实际 IPC/FULL 口径及拒绝边界；EOF/cancel-before-publish 的真实 worker 验证移交 D，不能只凭 store mock 宣称已证明。

日常在 06 clean、已提交 worktree 做受影响 focused/Contract/SQLite/filesystem integration，遵守离线缓存、节点占用和日志规则；本节最终候选按实际 Python/Rust/镜像边界完成必要静态与容器检查。04 完整阶段门禁及 t1–t4 正确性仍留给最终 S2b 候选；跨节点结果不作 carried。C handoff 必须含固定代码、API/消费者、实际证据、容量报告与 D 尚待决定项，经本节新审核者独立 GO 后才转 D。

## 6. 新角色执行交接

实施者先读取 B 最终 handoff 与交付审核，取得 06 自身节点占用，再使用本节 clean、已提交 worktree；审核者在新的只读 detached worktree 审码，两者不复用 B 的角色上下文。不修改 B 保留的证据或 A 的工作区。

源码同步沿用 B 已审并成功执行的外置脚本结构（CT201 `/tmp/s2b-b-publish-source.sh`、`/tmp/s2b-b-sync-resume.sh`，具体成功日志由 B handoff 引用）。为 C 显式调整任务路径、ref 和占用 owner，由审核者核对一次，不重新拼装复杂内联 SSH。previous 读取目标 worktree 实际 HEAD，不能用共享 main 的 `HEAD~1` 推断；candidate 先固定为完整 SHA，以任务自有 `refs/codex/<任务>-transfer/<fullsha>` 打包，bundle 的 advertised ref、校验和与 fetch 使用同一组参数。不能要求其他会话暂停 main 提交来保障同步。先独立检查同步实际 exit 0 与目标 clean HEAD，再发起测试；工具返回非零不会自动阻止下一工具调用，调用者必须显式停止。失败日志保留，按 DC68/DC80 最小诊断和独立复核，不循环试错。

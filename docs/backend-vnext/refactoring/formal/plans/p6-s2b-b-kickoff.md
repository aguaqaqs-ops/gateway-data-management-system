# S2b B：业务 kernel 与规范投影/摘要

状态：**实施准备已收口，产品与证据待交付**（2026-11-06）。Owner 已按 DC86 授权 B–E 逐节推进；本任务只实施 B。前置 A 产品 `db7767ffbb`、handoff `b625d775e0`、独立审核 `83b927207a` 已交付。B 前置独立审查 `8f3cf2421f` 的具体细节由下文冻结，不把前置审查当作产品通过。

## 1. 边界与实际消费者

B 在既有 Rust core 内接 SQL 标量物化、完整诊断、特殊 device/point catalog 验证过滤、canonical projection 与 row/content hash，输出 Arrow 和小型 facts，末端只复用 A 的 `canonical_ipc`。输入是按实际阶段提供的 parser/已物化 Arrow batches，不是已经替换生产 parser 的假设；当前生产 `table_access.sql.parse_sql` 仍走 Python，B 以真实 Rust parser C Stream 验证新路径，生产 caller 迁移与旧算法删除按 D/E 安排。

Python 继续拥有 ruleset 选择/解析、XML、composite AST/公式绑定、derived rows 和快照/manifest 小型 metadata 组装。B 不把所有 SQL/规范表行转成 Python `SourceRow/SourceCell` object graph 再送回 FFI；只有真实 composite consumer 需要的已过滤 catalog facts 与 derived rows 是现有 Python 业务例外。不要为语言统一移植小型摘要 metadata 或高变化业务规则。

不接 C 的 ArtifactStore、mmap、reference/TTL、事务与恢复；不接 D 的 startup N/M、operation control；不提前执行 E 的生产 parser/callers 切换。原 Python 算法在尚有生产消费者时保留，替换期只作为 frozen semantic oracle；不引入生产 fallback 或可选引擎 flag。C–E 最终仍迁移 `repository_ref`、`import_replay`、export、Preview FULL 两侧、History exact commit 和 Submit/T1/PREPARED，不因 B 暂不调用而删除这些消费者。

owning 依据：Canonical Storage Contract §3/§4/§5.2、Shared Canonical Encoding、Snapshot Materialization、Composite Signal、已批准 kickoff §2/§5.4，以及 [B 前置审核](p6-s2b-b-review.md) 的一次性验收清单。当前 projection 对 JSON/DECIMAL/BLOB/BIGINT UNSIGNED 等不支持类型的既有 fail-closed 规则保持；A 的类型表达能力不扩大 B 的业务词汇。

## 2. 最小 API 和已冻结细节

core 按既有 owner 提供三个窄操作：SQL table materialization facts、catalog filter facts、canonical table projection facts。输入复用 `ColumnDescriptor`/Arrow batches，另传已解析的小型 compare-key/storage-rule view、materialization stage 与明确的 source/canonicalized-input 区别；输出为 Arrow batches、规范描述、row count、row/content digest、warning/typed diagnostics。允许共享内部 table/frame helper，不建设新的通用 DTO/调度/资源框架。adapter 只做有界 metadata 转换和粗粒度 C Stream transfer，不直接依赖 Shared Kernel，不通过 re-export 或修改 architecture guard 绕过禁边。

重用既有 Shared Kernel scalar、collection、ULEB128、semantic digest 和 unordered-row-hash 聚合。**SET 非 NULL 单元格直接是 sequence frame；不得用通用 `encode_row` 替代现有 row preimage。** NULL、空 SET、空 ENUM label 分清；A 中 SET 的逗号文本只是存储表示。business schema 包含 table name、列序无关；manifest schema 保留 DDL/PK 顺序；snapshot/raw-state/manifest/IPC raw SHA 不混用。小型 schema/summary digest 可保留其现有 Python owner，批量 row/hash 不回读 Python 行。

### 2.1 内部物理行序

普通 keyed 先校验 retained 有效键、非空和唯一，再严格按 `StorageRuleView.canonical_key_columns` 顺序形成 canonical cell-frame tuple，逐项按无符号 bytes 词典序升序。不得复用 replay 的未分帧文本拼接；该顺序不承诺业务数值或展示排序。Ordered 按现有 `no` 校验/伪 gid 分配，内部物理行按 numeric gid，业务读取仍显式按 `no`。Keyless 按现有 row-hash bytes 升序并保留重复；沿现有摘要信任边界处理相同 hash，不引入碰撞证明机制。外部 replay/export 继续自己的 owning 顺序。

空表与 `EXPLICIT_KEYLESS` 全删列产生的零列非零行都保留实际 row count 和重复数，接 A 标准 row-count 能力。输入行/DDL/chunk/N 置换不能改变相同规范内容的 IPC bytes；不要求 manifest 的 DDL 顺序摘要在 DDL 置换后不变。

### 2.2 Catalog 与诊断优先级

`SpecialDeviceCatalog` 增加必填 `source_device_row_count`，为过滤前真实读取并验证的 device 行数；旧 Python extractor/empty factory/test factory 同步显式填写。B 可只返回命中设备，不能用命中数代替源行数，不造 sentinel 或兼容默认值。Python binder 用该 count 判断原表是否为空，再按精确命中判断恰一个设备。0/多命中身份错误保留原 binder 时点，不能提前越过 XML/AST 诊断；业务 digest 与 `COMPOSITE_SIGNAL_CONTRACT_VERSION` 不变。

所有 device 行先校验 gid/dev_addr/description 类型及非 NULL，合法空 description 保留；point 表先校验 gid/name/dev_addr 三列和全部 dev_addr 类型，NULL addr 按原行为跳过，只对命中行再校验 gid/name。原非空零命中、双命中、坏普通行、failed 表分别保持原语义。Python 只消费过滤后真实所需 facts，payload 的 IJSON 边界/大整数文本、float、binary hex、SET list、时间文本保留原规则。

SQL materialization 的重复有效键是 warning 且保留全部行，canonical keyed projection 的重复键是 blocker，不能合并两层。PROVISIONAL、表级 PARTIAL 与整体 FAILED 按原 Contract；schema/column failures 完整聚合，projection 的 1024 cap 与 omitted count 不变。cancel/timeout/resource 失败不得返回可发布的部分 projection/manifest；运行时 control 分类及 lease 发布禁止由 D 接真实 owner。

### 2.3 局部资源与执行控制

调用者显式提供局部预算：metadata/columns/batches/rows/input bytes 以及同时存活的 row/key/hash/sort/filter 索引、输出 Arrow/IPC、adapter 转换与诊断。增长前 checked 预约，拒绝溢出或超限；不得先完整收集 C Stream 再检查。复用已有 caller-owned Rayon pool；cancel 和真实可选 monotonic deadline 在有界循环与大段库调用前后检查。没有 deadline 时传 None，不用 lease/drain/benchmark 时限替代。

这些预算不是生产 M/RSS。B 不提前填部署默认值，不新增全局 allocation registry；后续 C 对实际 kernel/IPC/FULL 的生命周期校准，D 接线前再定 M/envelope/reserve。性能未知不阻塞无关 B 功能，也不据此跳过资源拒绝。

## 3. 实施顺序与验证

同一 B 实施/审核二角色覆盖以下小步，明确问题直接闭环；不为每个小步再创建角色。

1. 收口上述 catalog 必填事实及现有构造方，搭建最小 core 公共类型/操作；尽早运行架构守卫、focused 编译与已有 composite Contract，避免到镜像步骤才发现依赖禁边。
2. 实现 SQL materialization/cell-row framing/content hash 和 catalog Arrow 验证/过滤。复用现有 SQL Snapshot、scalar/SET 与 composite golden，一次明确原语义差分矩阵；不要用 Rust actual 反写 expected。
3. 实现 canonical projection：规则/声明诊断、retained 列、keyed/keyless、ordered no/gid 与伪 gid、负零/unsigned coercion、明确行序及 A codec 串接。验证 dropped/retained/structural 列变化、重复/空表/零列、N/chunk/DDL/行置换与取消/预算。
4. 接真实安全 C Stream adapter，完成 Rust parser → B kernel → A IPC 的定向链路及 Python composite 例外。安装当前扩展并核 build-input、释放 GIL、错误类别、停止流消费与必要生命周期；生产路由保持原样直到 D/E。

各小步只在 06 跑受影响的 focused/Contract/差分。既有测试 owner 按 B 审核清单复用，不在 Rust/Python/容器三层复制完整矩阵。Repository-ref/export/import-replay 的业务 Contract 保留为后续迁移依据；B 不重做全旅程或合成输入。

最终固定 B 候选在 06 一次完成适用 Rust policy：workspace fmt、all-targets clippy、串行 workspace tests、release build、架构 lint/依赖守卫；五 Python 包 Ruff/mypy；重装扩展并核 Rust tree、相关 native golden/focused；本候选实际离线构建的 health/clean-stop 和新业务 kernel native smoke。构建前先收敛静态/架构问题。dependency-base 以实际完整输入与 config/全部 DiffID 判定复用或更新，不能仅根据 tag 猜测；依赖变化时 CT201 clean 来源构建制品、LAN 预填，测试仍在 06。A 已通过结果只引用其适用的未改部分，不冒称 B 通过或正式 carried。

B 不替代 S2b 最终 04 权威 runner/container 与 t1–t4 正确性。完整功能阶段门禁、W1/W2 时点及原 W4 故障仍按 DC81–84；不得修改 CT108 冻结资源或把旧基准结果当当前产品 gate。

## 4. 分工、操作与交付

实施者 `/root/s2b_b_impl`：GPT-6-Luna/max，拥有产品/测试与 `p6-s2b-b-handoff.md`。独立审核者 `/root/s2b_b_review`：GPT-6-Astra/high，在 detached worktree 审码，拥有 `p6-s2b-b-review.md`；原则上不改产品/测试代码。主设计拥有本任务、DC、总体计划与 owning 文档。需要任何额外角色/子 agent，先停该依赖工作并向 Owner 说明原因、模型和思考强度，获确认后才创建。

CT201 当前主机 `heavy-dev-01` 不跑测试/编译/lint。06 使用 `ct107-gw-dms-06`，按 AGENTS 核 SSH、有效占用、clean committed worktree/legacy、离线缓存、Rust selector；jobs 4、TMPDIR/target/log 在 worktree 外。复杂远程命令写外置脚本并记录 SHA，实际命令、hostname、起止 HEAD/时间、exit、外部日志 SHA 清楚记录。失败保留，按 DC68/DC80 诊断并经明确修正/独立审核恢复，不盲试；有实质设计冲突或多轮不收敛交主设计/Owner。

handoff 给出固定产品提交、API/真实消费者、每项测试 owner/独立预期、实际节点日志、当前 image/source 绑定、局部数据/预算口径与 C–E 移交清单。独立审核对代码与实际证据作 B GO 后结束二角色，再按 DC86 新建 C 两角色并推进；不推送、不改写已引用提交、不擅自清理他人工作区或冻结证据。

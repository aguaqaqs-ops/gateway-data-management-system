# S2b A：纯内存规范映射与 IPC codec

状态：Owner 于 2026-11-06 明确“批准这份 kickoff 并且启动 A 节”；依据 DC85。整体技术方案为已审候选 `1a4adaae05`，审核报告 `8b4be7434b`。本任务仅授权 A，B–E 仍按后续小节安排，不提前切换生产路径。

## 1. 交付边界

交付一个 Rust 纯内存 canonical Arrow mapping/IPC codec，复用锁定的 Arrow 59.1.0 标准 writer/reader；core 不访问文件系统。输入是业务物化、规范投影之后、已按 owning 规则排好行的数据与规范声明；A 固定列序、类型映射、metadata、buffers 和 file profile，输出 Arrow/file bytes 并能在内存中按绑定描述校验读取。B 负责业务列选择、伪 gid、业务过滤与行排序/hash pipeline；C 负责文件/mmap/引用与恢复；D 才接 worker/config。A 不把内部 IPC 替代客户端 Parquet 或 Repository wire。

实现先给出最小 API、声明类型复用、局部预算与测试 owner，由设计/审核对齐后落代码。优先复用现有 Shared Kernel 标量、JCS、framing 和 Table Access 描述；热路径保持 Arrow/列式数据，不为未来 consumer 提前建通用框架。必要的 Python 调用/互操作验证只做本 codec 的最小边界，不增加引擎 flag 或生产路由；A 不删除仍服务生产的 Python 算法。旧路径在 E 完成迁移和验证后删除，不能变成永久回退。

输入 `sql_type` 是规范投影 owner 的 `normalize_sql_type_spelling` 既有输出，不把 parser 的类型 mapper 当作同一规范化函数；例如 `DATETIME(0)`/`REAL` 的归一由该 owner 负责。原始拼写等价用例在进入 A 前按该 owner 归一，或仅改变 display/provenance；A 不新增完整 SQL normalizer。

Owning Contract 为 [Canonical Storage §5.1](../contracts/canonical-storage-and-repository-boundary.md#51-canonical-ipc-v1-内存-codecs2b-a)。规范细节以 [映射 v1](p6-s2b-arrow-mapping-design.md) 为准：UTF-8 canonical 列序、唯一 metadata/JCS 声明、SET 文本存储与 sequence 业务编码分离、64-byte/V5/non-legacy 无压缩无 dictionary file、65,536 行固定切批、空表零 batch、确定的 offsets/null slots/bitmaps。业务摘要不改为 IPC raw SHA；既有业务 schema digest 包含表名的事实不变。

### 1.1 实施前已对齐的最小 API

`gateway_compute_core::canonical_ipc` 复用现有 `ColumnDescriptor`、`SqlLogicalType` 与 `DeclaredType`。`encode_v1(columns, batches, caller_pool, options)` 返回 IPC bytes；`decode_v1(bytes, bound_columns, caller_pool, options)` 返回按外层列名布局重排的 batches。输入字段按实际 canonical 列名绑定，拒绝重复/缺失/矛盾声明；不依赖原始 ordinal。局部 options 明示 rows、columns、input/output bytes、codec peak 的上限及 cancel/可选单调 deadline，不填生产 M。 `max_input_bytes` 管借用输入保守总量，`max_codec_peak_bytes` 管 codec/adapter 自身同时存活的分配（含输出复制），总体占用合看二者；这不是完整 worker M/RSS。

decode 在标准 Arrow reader 前对借用输入做 footer/block 长度及 raw metadata 唯一键预检；避免依赖标准 reader 的 HashMap 覆盖重复键或按未经边界检查的长度先分配。encode 的 checked 预约包含标准 writer 在实际 Write 前生成的 encoded data，不仅限制最终 Vec。采用标准 writer/reader，不自行实现另一套 IPC。

允许最小 PyO3 Arrow C Stream encode 入口用于真实 backend 互操作测试和后续 B 消费者，沿用现有 FFI/GIL/shared-pool 安全规则；N/chunk 确定性主要由 Rust core 验证。A 不新增 worker initializer、第二 Python 算法或通用绑定框架。仅提升实际用到的 `arrow-ipc` 生产依赖，`arrow-select` 如不需要则不调整；锁/features 与缓存未变可复用现有 dependency-base，生产镜像闭包仍按 §3 判断。

该最小 Python 入口要求调用者显式传入局部 budgets，不提供 `None` 所隐含的默认容量。描述转换前核数量与大小，C Stream 逐 batch 消费时核累计行数、批次数、输入 bytes 与 adapter 自有分配，输出转 Python bytes 前核同时驻留；不能先无限收集再交 core 检查。仍不制定生产 M。

接口遵守既有 architecture-check 的 adapter → Shared Kernel 禁边：adapter 只提取有界的 kind/bits/precision/scale/bit_width 小型 metadata，由 core 的最小 setter/factory 构造既有 `DeclaredType` 并校验槽一致性；不新增 DTO 框架或通过类型 re-export 绕过边界。首次实现曾按设计意见增加直接依赖，最终 workspace 检查揭示其与既有守卫冲突，现撤回该意见；守卫和反向禁边均不放宽。依赖及锁通过新提交修正，不改写已引用提交。最终 dependency-base 按实际完整输入摘要选择；为中间锁构建的 `lock-994c32446656` 不自动成为最终候选基础层，恢复原输入且已有镜像身份合格时可复用对应原 base。

## 2. 局部边界与验收

| 内容 | 验证与独立来源 |
| --- | --- |
| 声明和值映射 | signed/unsigned、Float32/64、DECIMAL、BIT、ENUM/SET、JSON 文本、UTC/civil/time、NULL/空值；复用 Shared Kernel、parser、SET 已有向量，新增向量记录独立期望依据 |
| IPC profile | 固定小向量按标准 reader/布局独立核验 schema、metadata、offset/validity/值、batch/footer；不能仅由新 Rust 输出生成 golden 后自证，不建第二 writer |
| 确定性 | 相同规范输入的 N=1/N、输入 chunk 划分及 DDL 列序/原始拼写变化产出相同 bytes；外层 row-layout 重排用实际列名验证，A 不实施业务行排序 |
| 错误边界 | 不支持声明、metadata/version/type/绑定描述冲突、截断/损坏输入稳定拒绝；按既有信任边界处理，不引入新安全子系统 |
| 局部资源与控制 | 输入/输出/临时分配的有界检查和溢出检查在增长前执行；取消与有限 deadline 按 core 调用者实际传值检查，错误不返回可用的部分结果。阈值分支用小型边界测试，不分配数 GiB |
| 实际 bytes | codec 完成后记录固定向量实际 bytes/profile 开销；只是 A 局部实测，不宣称业务 FULL、worker RSS、生产 M 或 W2 通过 |

预算 API 复用现有 core 约定并保持局部、可校验；调用者已持有的 Arrow buffers 与 codec 新分配区分计数，不把“纯内存”解释为无上限。部署 M、完整 FULL 驻留、实际 worker 的资源行为按 DC84 在 C/D 收口；A 不提前填写生产默认值。复用已有 caller-owned Rayon 池，不新增每表或每调用全局池，不在 A 接 worker startup。

## 3. 验证节点与候选

实施者统一使用 `ct107-gw-dms-06`，执行前 SSH、有效占用、clean 已提交 worktree/legacy、离线依赖与工具链前提按 AGENTS 核对。日常 Rust focused、对应 Contract/互操作及必要静态检查按变化范围运行；Rust fmt/clippy 和五 Python 包 Ruff/mypy 均在专用节点。Rust 改动后跑 backend 时强制重装扩展并核 build-input，不使用 stale extension。

最终 A 候选按 Rust policy §7 在 06 完成一次 workspace fmt、all-targets clippy、workspace test 与 release build（locked/offline），核各 member 继承 workspace lints。PyO3/Arrow 接线另验 installed release extension import/build-input、相关 native golden、GIL progress、Arrow round-trip，以及当前镜像实际调用新 codec 的 native smoke；健康检查不能单独代替新 codec 验证。这些是 A 的适用检查，不要求每次修改执行，也不扩展为六包全量 runner 或完整真实数据旅程。

`arrow-ipc`/`arrow-select` 当前是 core dev-dependencies，转为生产使用即检查真实 production/feature/lock 闭包。版本不变不豁免容器边界；收敛到本节最终产品候选后，在 06 按实际影响完成必要 backend/worker 容器/native smoke。锁/依赖基础层输入变化时按 DC67 在 CT201 clean worktree 准备制品并 LAN 预填，测试仍在 06。保留 backend/worker 本机构建，不启用 prebuilt gate 绕过。

不为每次修改跑完整 runner、全旅程或合成输入生成；未受影响证据注明直接来源及适用范围。A 不是 S2b 阶段 exit，不产生替代最终 04 runner/container 或 t1–t4 正确性的新豁免；正式计时和原基准冻结资源不在本任务内。

最终交付包括固定产品提交、最小 Contract/实现说明、独立向量来源、06 日志/起止 HEAD/exit/SHA、依赖与 image revision/source-tree 判定、局部 bytes 结果及 A handoff。独立审核核代码与实际证据后结束本节；不自动进入 B。

## 4. 分工与协调

实施者 `/root/s2b_a_impl`：GPT-6-Luna/max，负责产品/测试/向量及 handoff。审核者 `/root/s2b_a_review`：GPT-6-Astra/high，在独立 detached worktree 审核，拥有 A 审核报告。主设计负责本任务、DC/计划与方案边界；设计/审核允许直接修改已协调归属的文档，代码修复原则上交实施者后复审。小问题直接闭环；业务缺口、目标/设计冲突或多轮不收敛带事实交 Owner，不无限等待。

原基准线拟议 Python JSON/digest 临时分配方案不在 A 范围；A 优先只复用 Rust Shared Kernel 已有接口，若需共享模块修改先同步精确路径/影响。原线尚未合入的修复不默认为 A 已具备。main 上其他会话文档修改保留；不推送、不改写引用提交。每小节结束停止本节两个角色，下节重新创建。

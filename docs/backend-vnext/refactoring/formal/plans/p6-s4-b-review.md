# P6 S4 B 独立代码审核（累计）

2026-11-08。当前结论：**CHANGES_REQUIRED**。这是 B 固定候选的累计独立审核：首候选 43a8 与修复候选 83fd 的 Rust 阶段均未通过，后者 F2/F5 静态修复已具备但 fmt/clippy 失败；尚无 Python focused 或 t1–t4 逐表差分结论，更不是 S4 退出结论。

## 固定对象与边界

- 直接 base `e76342ef0b58bb0120fc60d8a063d838140ee28d`；B 候选 `43a8f1e16592ae9726d019e73a2c65a4d03253ec`；Rust tree `5b87acea208ec03af3e22c1b6a61b4f584eda059`。base 含并行 S3 资源档产品，不作为 B 增量。
- 审核 worktree `/home/dev/gdds-s4-b-review-43a8f1e1` 是固定候选 detached，已链接仓库 `legacy/`，`git status --porcelain` 空。`git diff --check` 空；B diff 为 20 文件、1167 行新增/59 行删除。
- 只读依据：AGENTS、testing-conventions、S4 design/kickoff/review prompt、A GO/handoff、Storage Mutation/Canonical Storage/Shared Encoding、ADR0014、Rust/比例化政策，以及旧 planner/renderer、canonical reader、Table Access kernel、S3 comparison kernel。未运行测试、编译、lint、节点或容器取证，未改产品。
- 当前 HEAD 触发最终镜像重建：**yes**，新增 Rust core/PyO3 扩展；本候选最后已验证的 S4 image revision/source-tree：**none**；容器门禁延期到最终候选。B 只可按 focused 范围核收，不冒用 S3/A 镜像和权威门禁。

## 阻塞 finding

### B-F1：输入 Arrow backing 没有由 native 入口建立或核验同 M charge

`vnext/backend/src/gateway_backend/capabilities/mutation_planning/native.py:101-110` 把 `active.memory.available_bytes` 全部预约为 native 子额度，并仅以注释假定 caller 已计费完整 Arrow backing。`StorageTableTaskV1` 允许直接传任何 `pa.RecordBatchReader`，facade 没有 input owner/charge 参数或可核对的 backing 凭证；测试 `test_storage_mutation_native.py:79-87` 手工 `retain_arrow`，这只是测试约定。Rust `gateway-compute-python/src/storage_mutation.rs:132-147` 实际读入并持有全部批次，`gateway-compute-core/src/storage_mutation/mod.rs:42-51` 把这些 Arrow owner 保留到表结束。未计费 reader 可让真实驻留超过 M，且先占满 available 后无法再计费。请在同一 operation 建立明确的输入 backing owner/charge 与最后释放顺序，由 facade 验证或自己取得，并覆盖未计费调用、mmap/Arrow 共享和失败释放。C/D 接线前必须闭合，不能靠调用方注释。

### B-F2：`identity_validated` 超过实际验证范围，NOOP 可跳过未核的 persisted cell

`storage_mutation/mod.rs:59-72,214-220,252-257` 只核 Arrow schema、列名和行数，keyed 的 `indexed_rows` 只读取 key；非键 persisted 单元格在无 diff 的路径没有扫描。它仍把 `after_validated=after.is_some()`、`before_validated=before.is_some()` 返回。Python `native.py:45-49` 还把 metadata-only before 强行标为 validated；`storage.py:66-74` 以这些标志和 manifest metadata 相等直接判 NOOP。因此该接口可把实际 after cell 不同或非法的 reader 当作“完整身份已验证”并不产 SQL。canonical reader 能核其受信 ref 的 raw SHA/IPC count，但此 FFI 接口未接 ref/descriptor/content 的证明，不能把任意 task 的 schema/row count 检查称为完整绑定。请明确由哪个 owner 核 frozen after 的 raw/content 和 parent manifest 绑定，并把验证证明绑定到 task/summary；NOOP 不得以布尔伪证明跳过实际校验。无需在 Rust 重算业务摘要，但错误标志必须收窄并在 D 前落实正式 owner。

### B-F3：native 可比条件与 Python 唯一 policy 不一致

`native.py:91-100` 用 `before.storage_view == after.storage_view` 控制 diff，比较包含 `storage_rule_digest`。`storage.py:13-23,26-34` 和旧 `_planner.py::_storage_views_compatible` 仅比较存储语义字段。两侧唯 `storage_rule_digest` 不同时，新 policy 仍认为可 patch，但 native 返回 `net_counts=None`，`storage.py:77-78` 报错；旧 planner 会正常 diff 并作 NOOP/PATCH/REBUILD。它也说明目前只把阈值放入 `_decision.py`，可比资格仍有两个不同实现。请统一实际 diff eligibility 与表级 policy，并用该差异的测试锁定行为；如认为 digest 改变必须重建，须在唯一 policy 中一致作决定并核旧行为/Contract。

### B-F4：读入批次头部未严格先收费

`gateway-compute-python/src/storage_mutation.rs:132-147` 先把最多 4096 个 `RecordBatch` 放入 `Vec`，没有在增长前申请 native lease。`gateway-compute-core/src/storage_mutation/mod.rs:224-260` 等所有 stream 消费完才计算并申请 `index_upper`，其中 batch header 容量直到 `:316-327` 的结果收缩阶段才核，零行多批次也能先分配大量头部。请在读入前或增长前预留批次头部的保守上界，按实际 capacity 收缩，确保预算拒绝早于分配；对零行多批、低 M 做有界验证。

### B-F5：原生编码 scratch 不能用输入字节的固定倍数证明

`gateway-compute-core/src/storage_mutation/mod.rs:147-158` 的 `key_at` 同时持有逻辑 cell/JSON 值、`serde_json::to_vec` 输入、JCS 解析对象及最终 key bytes。长字符串由大量 NUL/控制字符组成时，两个 JSON byte buffer 各可膨胀至原 UTF-8 的约六倍，且解析 graph、Vec capacity 和 metadata clone 仍驻留。`:235-253` 的 `index_upper` 使用 `input_bytes * 8` 加固定 per-row 系数，无法证明峰值在已预约 native 子额度内；keyless `row_hash_at` 的行 frame 也要按同一原则核实际同时驻留。请按每阶段输入长度、最坏 escape/encode 膨胀与同时存活对象计算 checked 上界，在每次分配前预留，增长按实际 capacity 对账；用一个长控制字符 key 的小 M 边界验证先拒绝，不用 RSS 系数或大量同构探针替代。

## 实现期需核，不计本次单独阻塞

- `storage_mutation/mod.rs:309-334` 在 diff 后保留 before batches 与 patch locators，超过阈值并选择 rebuild 时，B handle 尚无 early-release 接口。C renderer/D 调用必须在保留 after 的同时先释放无用 before/index/patch，核双表峰值与最后 owner；不能宣称当前 B 已达表级峰值。
- B 的 Rust `row_hash_at` 调用 Shared Kernel `encode_row`，并按旧 `_digest.py::_row_field` 映射整数/DECIMAL/BIT 类型；keyless 重复使用 `(JCS([]), row digest)` 排序。当前测试只覆盖一个小型 keyless 表，t1–t4 逐表差分尚待 driver 原件；不得把构造测试当真实数据通过。
- pool 通过 `shared_parser_pool(Some(pool_threads))` 核初始化/N，Table Access 的 `require_active_kernel_context` 核真实实例、active/closed；经 Storage Projection/Snapshot 单向 helper 导出，没有直接 Mutation Planning→Table Access import。实际取消/截止、panic/GIL 和最后 charge 的节点测试仍待核。

## 执行稿与证据

固定 05 node 脚本 `/home/dev/gdds-test-tmp/p6-s4-b-plan/run-focused-05.sh` SHA256 `a4ed8ceb585cab7e229270da4da2b50f7b017f9e24328b1bef6040e6a6353082`，source bundle SHA256 `e9ae8a22ef720ffa38ae940d701df7bf74526bf16087e09ecbbf480f13089c38`；`git bundle verify` 为 complete history，唯一 HEAD 是 B 候选。对这份精确脚本结论 **SCRIPT_CLEAR_FOR_FOCUSED_DEBUG**：它固定 05/HEAD/Rust tree，原子占用后取 bundle 建 clean detached WT、链接 ignored legacy，检查 Docker/8000/进程、离线与工具链，依次执行 Rust fmt/clippy/workspace test 三步（任失败停 Python）、强制重装扩展及 build-input、五包 ruff/mypy、六文件非 serial/serial 两遍，记录起止 HEAD/status、六锁与入口/最终 exit，释放本人 marker。测试/编译/构建输出均在 WT 外。脚本的 workspace 全 Rust test 比 `execution.md` 旧 filtered 命令严格，handoff 以精确脚本为准。此 CLEAR 仅允许唯一执行者在合格专用节点调试，不等于 B code GO；脚本 SHA 变化须重审。

固定外层 `/home/dev/gdds-test-tmp/p6-s4-b-plan/execute-focused-05.sh` SHA256 `8ddec8c63f556fd4fabeb9de6d566b394d9775435a43a0a7a606f43499a37675`，对与上述 node/bundle 两 SHA 的组合亦为 **SCRIPT_CLEAR_FOR_FOCUSED_DEBUG**。外层本地先核输入 SHA，BatchMode 逐项具名核 05 hostname/root/marker/唯一 staging，SCP 后远端复核 SHA；node 入口非零仍抓原日志与 sidecar，记录 SSH entry/capture/outer 原 exit。若 node 在日志创建前失败，capture 会显示失败而非补造日志。外层不在 marker 外运行测试或写被测 worktree。

首候选节点实际结果见下节：Rust 三步失败后未运行扩展重装、五包静态、Python focused 或逐表真实数据。A GO 仅是 A 自身六文件与 05 focused 证据；S3 仍 BLOCKED_CAPACITY，Q18/其他并行路径不计入本节。

### 首候选 05 原始调试失败核收

唯一执行者的外层原件 `/home/dev/gdds-test-tmp/p6-s4-b-plan/controller-43a8f1e165/outer.log` SHA256 `097660e1215789933580dbedce4772373126bcfcc2998b7ff6f18600e0937470`；captured node `focused.log` SHA256 `ae385835712c1ef48f9211ce8bc9fdba2a665e10e4adba6f1c673f971efb9080`，与原 node sidecar 相同。外层本地/远端脚本和 bundle SHA 均 OK，起止 UTC 17:25:35–17:26:01，`ssh_node_entry_exit=1`、`capture_exit=0`、`outer_exit=1`。node 起止 17:25:36–17:26:01，worktree 结束 HEAD 固定 `43a8f1e16592ae9726d019e73a2c65a4d03253ec`、status 空，六锁前后相同，marker file/dir release 均 0，`entry_exit=final_exit=1`。

Rust fmt 原始 exit **1**，显示新增 core/adapter 多处格式 diff；Rust clippy 原始 exit **101**、workspace test 原始 exit **101**，同一源码编译错误 `E0618`：`storage_mutation/mod.rs:230` 的局部 `indexed_rows: usize` 遮蔽了 `:183` 的同名函数，`:258/:275` 两处试图调用这个整数。脚本按已审三步都执行后停止，没有进入 backend native 重装、五包静态或 Python focused。这是 B 候选源码的格式/编译失败，**不重分类为工具故障或测试通过**；修复后固定新候选并按适用范围复验。此原始失败保留，后续成功不得倒改它。

## 修复候选 1d4ace 独立静态复审（未运行）

- 固定 HEAD `1d4ace5d73fb0131a6766ed8977fc8bf79a0d390`、直接 parent `96e113c16841b17e867e861c0ffb89b03d94cbdb`、Rust tree `d7ef475c61aa0b0b1b5875b9dd9fa95354fe87e7`。本提交 14 文件；期间 S3 a393 的 typing/docs 不记 B 增量。审核 WT `/home/dev/gdds-s4-b-review-1d4ace5d` clean detached、已链接 legacy，`git diff --check` 空。
- **B-F1 已按设计修复，待 focused 证据**：`StorageInputLease` 从真实 `ArrowSnapshotTableReader` 重开受信 canonical IPC reader，验证 artifact/descriptor、stream、schema、同一真实 active operation 和 Arrow/mmap backing 的同 M owner；native 子额度从余量预约，handle 延迟释放 reader。当前仍须修复 F2 中 lease 与 manifest item 的绑定。
- **B-F2 仍阻塞**：`open_storage_input` 初次核的是传入的 `manifest_table`，但 lease 未保存该 item；`require_storage_input_owner` 只核 stream/schema/operation。调用方可 `replace(after, manifest_table=replace(after.manifest_table, source_schema_digest=old.source_schema_digest))` 保留同一 verified stream/lease；`StorageTableSideV1` 不核该字段，native 会报告 `after_identity_validated=True`。在 metadata-only before 的 source-only changed 情况，真实新 source digest 不同应走 `BEFORE_ROWS_UNAVAILABLE` 重建，替换后 `same_identity` 成立却会选择 `STORAGE_IDENTITY_UNCHANGED` NOOP。source_row_count、gid 统计也可同法脱离真实 producer。请把完整原 manifest item 绑定在 lease，并于 `prepare_storage_table` 比较；若任务的 frozen manifest 有整体身份要求，同时绑定/核整体 manifest。新增一例 metadata-only before 的替换拒绝即可证明屏障。
- **B-F3 已修，待 focused 证据**：`storage_views_compatible` 和 `keyed_patchable` 收敛到 `_decision.py`，旧 planner、B policy、native diff 使用同一 predicate；digest-only 变化有测试。
- **B-F4 已修，待 focused 证据**：FFI 在 `into_stream`/`consume_stream` 前按 4097 批 header、列引用及名称长度 reserve，再按实际保留量 shrink；零行多批低 M 有 focused 测试。
- **B-F5 部分修复，仍需预算依据**：core 改为逐行 raw/name/列数计算 64x scratch，key payload 逐行求和，index 上限以 key payload 16x 计入 JCS escape 与 Vec spare；长控制字符 key 小 M 测试已加。尚未看到 `comparison::ordered::encode_set` 对每个 SET cell 从 `gdds.canonical_type` metadata 解析 `serde_json::Value`/labels 的 graph 如何计入并发预算：该 cell 可为空，`row_scratch` 的 raw=0 且每列仅 4096；Python 固定 64 MiB `metadata_charge` 的注释只覆盖 FFI schema/String 拷贝。请列出 metadata charge 与 SET parser graph 同时驻留的安全上界，或按字段 metadata 长度在解析前增收费，不以经验 RSS 系数解释。该点待精确答复和节点小 M 证据，不先签 F5 CLEAR。
- **early-release 方向已实现，C/D 接线待核**：Rust `discard_before` 清 before/patch 并 shrink；Python `apply_decision` 对非 PATCH 先清 native，再关闭 before owner 与 reconcile。公共 `StorageTableHandle` Protocol 尚无 `apply_decision`，应补入并在 C/D render 前调用；当前 focused 只直接调用 concrete handle，不能充当生产接线证明。
- 修复候选仍未运行 Rust fmt/clippy/test、扩展重装、五包静态、六 focused 或 t1–t4 逐表差分。此前 43a8 节点失败不转为通过。本次 HEAD 仍触发最终扩展/image 重建；最后已验证 S4 image revision/source-tree 仍为 none，最终容器门禁延期到阶段最终候选。

### 1d4ace 格式准备脚本精确静审

节点 `node.sh` SHA256 `5d2b37f20b97ce6b9c47f961fc29e0455b3fb5d3ab3951b7d152a4315aa69d4b`；外层 `run.sh` SHA256 `6d25ff878cacb6a15cc3f747a0e690f8f368190658e9f5a9c3c08d3cd954f1d8`；source bundle SHA256 `c959e5d677a4bb479f034d32308f9f66733b24fcb80f15cab878717e51cbbe14`。本地 `git bundle verify` 证实 complete history、唯一 HEAD `1d4ace5d73fb0131a6766ed8977fc8bf79a0d390`。结论 **SCRIPT_CLEAR_FOR_FORMAT_PREP**：05 root/marker/空闲/工具链与离线前提、固定 clean detached WT 和 legacy、锁/HEAD 前后记录及原始 exit/capture 都具备；唯一格式操作从两份 Rust 源按字节读入 `rustfmt --edition 2024 --emit stdout`，仅写 WT 外 formatted 文件和 SHA manifest。该许可仅供唯一节点执行者准备格式制品，不是 focused、编译/lint、B code GO 或正式证据；格式输出回填为新提交后须另审新固定候选和 focused 脚本。

节点原件已核：外层 `outer.log` sidecar SHA 匹配，节点 `format.log` 实际 SHA256 `e84ec9ee01a43109f17fb4ae3586f88864578631b094fdc667e07c55833eb4fa` 与 node sidecar 相同。`ssh_node_entry_exit=0`、`log_capture_exit=0`、`formatted_capture_exit=0`、`outer_exit=0`；节点两份 rustfmt raw exit 0，entry/final 0，结束 HEAD 固定、status 空、六锁不漂、marker file/dir release 0。manifest 的 source SHA 分别为 `5291f24c3f91cae99317c101aa3edddc183507928e9e266df3535d9b5dea4bf6` 和 `103e83fe3ee10cb4612378529bd8748eb07aa1023c05f76290806d49ceefcafb`，与固定 WT 源相同；捕获格式制品 SHA 分别为 `0f6c8ba40d33a2871deccc994b7a5d159e94b51f63587c60000a9668a0b8628b`、`4dac8fff38f4ec28464f24a18c2e368d7809e68d6c9f6f2339ea3a64d84cbc89`，与 manifest 相同。它们可供纯格式回填，不构成 Rust fmt workspace check 或 B 验收。

## 修复候选 83fd51 静态复审（待节点 focused）

- 固定 HEAD `83fd51aeade5a067523af22bd973e7f8e4f81f9d`，直接 parent 为纯格式提交 `e49b4f9276d0e62497eef0edfe88561e87e889b0`，Rust tree `2b2184b2edf802a4fdb2e6b8360c19fdd946deb7`；本提交 5 文件。审核 WT `/home/dev/gdds-s4-b-review-83fd51ae` clean detached、linked legacy；`git diff --check` 空。1d4..83fd 另含两份已核格式回填，不把它当行为修复。
- **B-F2 静态修复已具备，仍待真实 focused**：`StorageTableSideV1` 强制完整 manifest membership/版本；`StorageInputLease` 保存首次打开的 manifest object 与完整 table item；native 入口核同一 manifest object、相等 item、同 stream/schema/operation。此前 `replace` 后改 `source_schema_digest` 以 metadata-only before 错选 NOOP 的反例现在在入口拒绝；新测试覆盖 content/source digest 重新绑定。metadata-only before 仍独立核完整 manifest digest。stream side 的 manifest digest 前置验证由现有 publication/open owner 负责，`open_storage_input` 注释显式委托；D 必须把同一已验证 frozen manifest object 传至每个表，并在 S4 D 审核核其完整性与原 source/wrapper 绑定。本条不把尚未实施的 D 接线算成 B 通过。
- **B-F5 静态修复已具备，仍待 Rust/小 M 证据**：在 canonical schema 检查前按最大 field metadata 的 64 倍、字段名/列数 reserve parse scratch，检查后释放；逐行 scratch 再计同一 metadata 上界，覆盖空 SET 值的 declaration JSON/labels 解析，checked arithmetic 在分配前。合法 64 个、每个 249 字符的 SET 声明低预算失败并回收 lease 的 Rust 测试已加。Rust 行/索引原有 raw/JCS 预算也保留。该 64 倍是按单个同时解析的 metadata/value graph 作保守上界；最终 M24 容量/性能仍需 D/E 测量，B focused 仅证明代表性边界。
- **early-release 接口补齐**：公共 `StorageTableHandle` Protocol 已声明 `apply_decision`；concrete handle 对非 PATCH 清 before/patch 并 reconcile，C/D 必须在 render 前实际调用。
- 当前结论 **STATIC_REPAIR_READY_FOR_FOCUSED_DEBUG**，不等于 B GO。尚须审核精确 node/outer/bundle SHA、执行 Rust fmt/clippy/workspace test、扩展强制重装、五包静态与六 focused，核原始日志；t1–t4 逐表差分仍未交付。最后已验证 S4 image revision/source-tree 为 none，容器门禁留最终候选。

### 83fd51 精确 focused 调试脚本静审

`/home/dev/gdds-test-tmp/p6-s4-b-r2-83fd51aead/node.sh` SHA256 `89802e36b4b5840638f9e67827ebc057b08acb778ad4e7206bc9f45c0323301a`；同目录 `run.sh` SHA256 `48d5a0cdce3534a9fa97a45c6a9e83739cc170aa76a018629d43e3baeb797c1f`；`source.bundle` SHA256 `decb3b767695209e48b4051154ddf70694c92f13b06f84429972f405a3b5fa74`。`git bundle verify` 完整历史、唯一 HEAD 83fd51。结论 **SCRIPT_CLEAR_FOR_FOCUSED_DEBUG**：外层在 05 逐项核 root、hostname、marker、唯一 staging 与传输 SHA；节点原子占用后取固定 bundle，建 clean detached WT/legacy，核 HEAD/Rust tree、四工具同 selector、offline、六锁、终态和 marker。先将两 Rust 文件 stdin rustfmt stdout 写 WT 外制品；随后全 workspace Rust fmt/clippy/test 三步全部取原 exit，任一失败就停 Python。三步全 0 后才强制重装 native、核 extension build-input，再跑五 Python 包 ruff/mypy 与六 focused 文件 nonserial/真实 serial 两遍。外层即使 Rust 失败也捕获日志和格式输出，原 entry exit 优先。此许可不含 t1–t4 driver、Compose、完整 runner 或 B GO；实际节点结果须按原件另核。

### 83fd51 节点原始调试失败核收

外层 `controller/outer.log` SHA256 `eb0c75df580c060bb96d22247946113a98728ee1a34cf7248dbf134f89a625f9` 与 sidecar 相同；captured `focused.log` SHA256 `df32403ac2eded3e4be6faa61587033199d99d2842baa7d431c21fc8630adc75` 与 node sidecar 相同。05 节点起止 17:58:49–17:59:26 UTC；`ssh_node_entry_exit=outer_exit=entry_exit=final_exit=1`，log/格式 capture 0；结束 HEAD 固定 83fd51、status 空、六锁不漂、marker file/dir release 双 0。Rustfmt stdout 两源 raw exit 0，core 捕获格式文件 SHA256 `28aa383d4b04cbc86490b0ebac34da7ab72d30f00465c1920d59447374e47c46`，adapter `4dac8fff38f4ec28464f24a18c2e368d7809e68d6c9f6f2339ea3a64d84cbc89`，source SHA 与固定审核 WT 一致。Rust workspace fmt exit **1**（新增 core metadata/test 格式差异）；clippy exit **101**，源码 lint 为 `mod.rs:586` 不需要 `mut after_index`、`:516` 可合并 if；workspace test exit **0**。三步后按脚本停止，未执行扩展重装、五包静态、Python focused 或逐表真实数据。故该提交本轮 **FAIL**，是产品格式/lint 问题，不改写成工具故障或因 test0 记 B 通过；修复并固定后继提交再验。

## 机械修复候选 b9c878 与 r3 脚本静审

- 固定 HEAD `b9c8783cdafccc6d4c73ea486b3cdf0736d940af`，直接 parent 83fd51，Rust tree `1b01deb923a4433738a680eee613fc9a5aa9b9ec`。审核 WT `/home/dev/gdds-s4-b-review-b9c8783c` clean detached、linked legacy；`git diff --check` 空。提交仅改 core `storage_mutation/mod.rs`：相对 r2 节点捕获 formatter 文件逐字 diff，只有 clippy 报出的 `if let` let-chain 与删除不必要 `mut` 两处语义等价机械修；其余格式与 r2 stdout 制品一致。未在开发机运行格式器、编译或测试。
- r3 精确 node `/home/dev/gdds-test-tmp/p6-s4-b-r3-b9c8783cda/node.sh` SHA256 `66760616abe3fa531896a66fd4edad516ea2badd166cfe87a1b5aa50ec959379`；outer `run.sh` SHA256 `3aa47e9a07828b7da1cca913ce451b51b8256fcdf03bf260d122fcbd8f1662da`；bundle SHA256 `ee049a31acb1e39bf18840444e18b441f1c2bca14905f4ce48b70061e2e97b1d`，`git bundle verify` 完整、唯一 b9 HEAD。相对已审 r2 两脚本仅固定身份、唯一路径/session/SHA 变化，执行逻辑与停止/捕获边界不变，故 **SCRIPT_CLEAR_FOR_FOCUSED_DEBUG**。仍须核实际 Rust 三步、native 强制重装、五包静态、六 focused 原件；t1–t4 driver 另核。未签 B GO。

### b9c878 节点原始调试失败核收

r3 外层 `outer.log` SHA256 `34d1eb3b6d795e9650c0ed7f763bdbfbc058cfcc743258556768f4c71a37af55` 与 sidecar 相同；captured `focused.log` SHA256 `cd4678ef3bb50c60e79689c90af4408526d16b55058b65764a34d68baf297524` 与 node sidecar 相同。05 节点 Rust fmt exit **0**，clippy exit **101**：`gateway-compute-python/src/storage_mutation.rs:99` 的 summary tuple 触发 type_complexity、`:262` `while let Some(next) = reader.next()` 触发 while_let_on_iterator；workspace test exit **0**（207 passed）。格式 stdout 两文件 raw exit 0、输出 SHA 等于 b9 固定源 SHA。外层/节点 entry/final exit **1**，log/格式 capture **0**，结束 HEAD b9 固定、status 空、六锁不漂、marker release 双 0。按脚本 Rust 非全通过即停止，未运行扩展重装、五包静态、Python focused/t1–t4。该候选仍为 **FAIL**，是产品源码 lint 问题；workspace test0 不升级为 B 通过，也不重分类为工具错误。

## 机械修复候选 b7fc36 与 r4 脚本静审

固定 HEAD `b7fc36b2d92203ebf6477082dd880a18e5206bc9`，直接 parent b9c878，Rust tree `9eb2046156f59736f03a1f299081cd522af0e3ed`。审核 WT `/home/dev/gdds-s4-b-review-b7fc36b2` clean detached、linked legacy，`git diff --check` 空。单一 PyO3 adapter diff 把 `summary()` 同一六元返回形状抽成 `type StorageSummary`，把 `while let Some(next) = reader.next()` 改为 `for next in reader` 并去 `mut`；schema 获取、count/4096批上限/错误映射均保留，属于 r3 clippy 两条机械修。未在开发机运行格式、编译或测试。

r4 `/home/dev/gdds-test-tmp/p6-s4-b-r4-b7fc36b2d9/`：node.sh SHA256 `feeaf6d3ea8c62fd65788b7bbc333e88104f83f9b4f17582f8ae47c4d8f7889a`；run.sh SHA256 `ee89f1def8e2978d58c1fa2fada2328688b90358d8bfb0e8059a0bfe74bb94b9`；source.bundle SHA256 `c3d95295a0c9b42ec51b6ac3c85b3912a3f2a73236ca5ffdc2ec7e4ac8691c7b`，`git bundle verify` complete、唯一 b7 HEAD。两脚本相对 r3 字面 diff 仅固定身份/新唯一目录/session/SHA，节点占用、Rust三步、失败停Python、强制native重装与focused范围及捕获逻辑不变。结论 **SCRIPT_CLEAR_FOR_FOCUSED_DEBUG**，不是 B GO；实际节点原件和 t1–t4 driver 待核。

### b7fc36 节点原始调试失败核收

r4 外层 `outer.log` SHA256 `232591a9f168a59121ee489b0d35be70e49cc03c89ecefccb4a7f6a3276fd392` 与 sidecar 相同；captured `focused.log` SHA256 `e687fdeec3d74287e2dd01da44d9c263baadeaf41a6d56c87be5639e2039bd4e` 与 node sidecar 相同。Rust workspace fmt exit **1**，只报 PyO3 adapter `StorageSummary` 类型别名应多行排版；clippy exit **0**、workspace test exit **0**。格式 stdout 源 SHA `bfdae1409d25effd82e67018cb641e28040c92f20186ca5177cc1ddcd67486f6`，输出 SHA `a16c8454cc2484d7e1323e9c7c2d90f6d693a083f86331bd15c0083244ae79c5`，两份外置制品已抓获。outer/entry/final exit **1**，capture **0**，结束 HEAD b7、status 空、六锁不漂、marker release 双 0。按脚本 Rust 非全通过即停，未运行扩展/五包静态/Python focused/t1–t4。此候选仍为 **FAIL**；只需将已核格式制品纯格式回填为新固定提交再复验，不把 clippy/test0 升为 B GO。

## 纯格式候选 ece2ec 与 r5 脚本静审

固定 HEAD `ece2ec745fd1b35db629eda81022c54761bcb452`，直接 parent b7fc36，Rust tree `fdfe6daed59cb58d5c2aa7c39fa3cccba94424d2`。审核 WT `/home/dev/gdds-s4-b-review-ece2ec74` clean detached、linked legacy；单 adapter 文件仅将 `StorageSummary` alias 多行排版，整文件 SHA256 `a16c8454cc2484d7e1323e9c7c2d90f6d693a083f86331bd15c0083244ae79c5` 与 r4 节点外置 formatter 捕获完全相等。`git diff --check` 空；未在开发机格式/编译/测试。

r5 `/home/dev/gdds-test-tmp/p6-s4-b-r5-ece2ec745f/`：node.sh SHA256 `265279f85c34f7d1e6248cbf3f3077e6d7f6848daf0ed210074bce7a634abc16`；run.sh SHA256 `ec308afd2d21304482d81674943172a62a310a74ccff9aed75ded20a9d20d088`；source.bundle SHA256 `717d44f0016fb71e86e4d492d534642584f512bfc88328243ea7b23705a40b20`，bundle verify complete、唯一 ece HEAD。相对已审 r4，脚本只替换固定身份/唯一目录/session/SHA，逻辑及停止范围全同，结论 **SCRIPT_CLEAR_FOR_FOCUSED_DEBUG**。须另核实际节点原件；非 B GO。

### ece2ec 节点原始静态失败核收

r5 外层 `outer.log` SHA256 `927361995595623984a6d659d18dda42240f7e694ba00490c07dfd7b49926323` 与 sidecar 相同；captured `focused.log` SHA256 `b2af25679405a7f87c76f90f53ba6b3da2dfad52809dc932245a5ffb40d81826` 与 node sidecar 相同。Rust workspace fmt/clippy/test 三步均 **0**；强制 backend native reinstall **0**、extension build-input check **0**（Rust tree fdfe6dae）；shared_kernel/repository_contracts/repository_client 的 ruff/mypy 和 backend ruff 均 **0**。backend mypy exit **1**，9 条类型错误、2 文件：`mutation_planning/native.py:132,137` 把 Optional manifest 传给非 Optional owner helper；`tests/test_storage_mutation_native.py:283` 动态 `dataclasses.replace(..., **{field: digest})` 推断出 7 条字段类型错误。脚本按失败停止，repository_service 静态和六 focused/t1–t4 均未运行。outer/entry/final exit **1**，capture **0**；结束 HEAD ece、status 空、六锁不漂、marker release 双 0。该提交整体 **FAIL**，虽 Rust/native 构建已过，也未达到 B focused 或 B GO；后继修 typing 后固定复验。

## 外置 t1–t4 逐表 driver 草稿静审（未许可执行）

`/home/dev/gdds-test-tmp/p6-s4-b-plan/table_diff_driver.py` 当前 SHA256 `f565216452db5450e561fa2528ae91d6bbd977e4e89d59767338b60da4c79b68`。其旧 Python `_keyed_rows_from_frozen_artifact` 加 `_digest.row_digest_from_image` 与 B Rust summary 分离，临时作为 keyed D/U/I oracle 方向成立；脚本尚未固定为可运行版本，**DRIVER_CHANGES_REQUIRED**：

1. `project()` 仅生成内存 canonicalization manifest 并 `publish_canonical_tables`，没有调用现有 `publish_canonicalization_manifest`/`open_canonicalization_manifest` 或 owning decode 来验证完整 frozen manifest；B `open_storage_input` 的前置是调用者已通过 publication owner 验证。请每档一次 publish/open 后由 `Prepared` 保存 opened manifest，同一 object 交给 side/lease，避免每表重复全量 rehash。
2. `comparable` 是手写且未完全覆盖唯一 policy 的 projection_version/key policy 条件；脚本只在 `summary.net_counts is not None` 时比较 oracle，可能静默漏掉应做 diff 的表。请依据 Contract 固定资格并断言 `net_counts is not None` 与资格相等；有计数时以旧 Python 路线独立计算 expected D/U/I 和整数阈值，不用 B 输出反填 expected。
3. 八包只对 `datasets.json` 中的可变 SHA/size 做比对；driver 输出 datasets/census 摘要却不核固定预期 SHA。应在外层/driver 固定并核 metadata、census SHA，再逐包核八件 source SHA/bytes；日志记录同一输入集合，拒绝漂移。
4. 当前先打开 after verified lease，再运行旧 Python oracle 行图；这些对象不计入同一个 M，`memory_high_water` 不能称 M admission。先算并释放旧 oracle 图再开 native before/after lease，或者把账本标成 differential-only 且不作 M 容量断言。driver 一次投影整档所有表也不代表 D 的 lazy 逐表内存峰值。

B kickoff 另明确 N1/允许N 与输入 batch split 确定性。当前 Rust/Python B 向量未见同一非空表跨 N 与不同 RecordBatch 分割的 summary/count/order 等价测试；唯一多批测试是零行低 M header 拒绝。补一个小型参数化语义屏障即可，不必扩大成内部穷举矩阵。

## 固定 driver fe76dd 与 1432dc N/batch 测试静审

外置 `table_diff_driver.py` 固定 SHA256 `fe76ddbb8b855f053b303d98996f9cb3754b98f2ce73b317c726e786eea2fd5e`；相对前草稿，逐档用 existing `publish_canonicalization_manifest`→`open_canonicalization_manifest` 验完整 manifest，一次保存已验证 object，side 与 lease 从该 manifest 取 item；核 source snapshot digest。固定 datasets metadata SHA256 `78c7cbba05acbbe92cc9a22351f8caf800824c4520e0d9685c6e776d6042da4f` 与 committed census SHA256 `733b506e43164a62f30d3a1d665449471e8edf25b515701150f6e73a824a6988`（后者已在固定 WT 只读核相等），八包逐件 size/SHA 再预检。手写 Contract 可比资格含 projection version/key policy，断言 native `net_counts` 是否存在与资格相等；旧 Python keyed adapter 与独立 row digest 先算 expected D/U/I 和阈值，释放行图后才开 native lease。内存输出明确标 diagnostic only，不能当 D/E 生产容量。就 driver 内容而言，前述阻塞已修，待外层固定脚本/节点输入身份核后可作 B 的逐表差分调试，尚无实际结果或 B GO。

产品/测试候选 `1432dcabea8f4dd82f3138c26573a180f3c1a0b6`，Rust tree仍 `fdfe6daed59cb58d5c2aa7c39fa3cccba94424d2`，直接 parent d814；clean detached WT `/home/dev/gdds-s4-b-review-1432dcab`，仅增 Python N1/N2 子进程与非空 3/1 batch split 向量，手算 D/U/I=(1,1,1)、locator=3。按本仓 kernel pool 只可初始化一次，子进程分开 N 合理；固定时间预算标 `serial`。原测试对 handle close 后 `used_bytes==0` 忽视 `OperationMemoryBudget.retain_metadata` 的 operation-lifetime charge；已要求保留 before/after early-release 下降断言，并在最后只 flush metadata 或独立 scope 退出后再断言0。`OperationMemoryBudget.close()` 只释放 metadata，不掩盖 Arrow/native 泄漏；该调整须固定新候选复核，未把当前 1432测试静审签成已通过。

## 99b4c374 候选与 r6 combined 调试稿静审

固定 HEAD `99b4c37409f463d1dc489f87e3fcb74bd8f86ec8`，Rust tree `fdfe6daed59cb58d5c2aa7c39fa3cccba94424d2` 与 r5 已实跑通过的 Rust 三步相同。审核 WT `/home/dev/gdds-s4-b-review-99b4c374` clean detached、linked legacy；`git diff --check` 空。相对 1432 产品 Rust 与 native 接线未变，仅 Python focused 测试在表 handle/input owner 离开后调用 `context.memory.close()`，按现有实现只释放 operation-lived metadata，然后断言 `used_bytes == 0`；Arrow/native 保留占用仍会使断言失败。rebuild 路径在调用前的 `used_bytes` 下降断言保留。N1/N2 子进程测试现在每种 batch split 用独立 `kernel_execution_scope`，退出后断言零，符合 operation metadata 生命周期。此为测试语义修正的静态结论，尚未实跑。N/batch 测试验证精确 D/U/I 与 locator 数；逐表真实差分另由固定 driver 验。

r6 固定目录 `/home/dev/gdds-test-tmp/p6-s4-b-r6-99b4c37409/`：node.sh SHA256 `2e26e2defd20ec5aa8ea077a22bf4299b8bb225126be04b06979073b9f07b047`，outer run.sh SHA256 `63625958efb1e701dd4b81c3b9b39bed82b8615456eb9ca64cf6b8b8530e8bc5`，source.bundle SHA256 `3b04e61dbefcb531c5720a25df0d2c49bdaab84a0efa127ad3e7c79ff8ef0fdd`，driver SHA256 `fe76ddbb8b855f053b303d98996f9cb3754b98f2ce73b317c726e786eea2fd5e`，本地 SHA 逐项相等；`git bundle verify` complete history、唯一 99b4 HEAD。相对已审 r5，Rust tree 完全相同，脚本明确复用 r5 Rust fmt/clippy/workspace test 三步均 0 的原始日志及同节点 WT 外 Cargo target；本轮不重复这三步，仍强制重装 native 扩展并核 build input。随后五包 ruff/mypy、六 focused 文件非 serial/serial 两遍，全部 0 才运行 N1 M24 t1–t4 逐表差分 driver。marker/整机空闲、clean detached WT/legacy、HEAD/tree/锁、离线工具链、原始 entry/final/outer exit、日志 SHA 与本人 marker 释放仍受脚本检查，任何失败停止后续步骤。结论 **SCRIPT_CLEAR_FOR_FOCUSED_AND_TABLE_DIFF_DEBUG**，仅供唯一节点执行者在合格 05 节点执行；不是 B GO，也不宣称完整 runner、Compose 或 D/E 生产容量。实际结果须核原件后另记。

### r6 节点原始 focused 失败核收

外层 `/home/dev/gdds-test-tmp/p6-s4-b-r6-99b4c37409/controller/outer.log` SHA256 `6fad64365cace8deec3699d3c9971df82883e77242d9d645ee6fb037fb508cfe` 与 sidecar 相同；captured node `focused.log` SHA256 `1cb1b524c891be84068cef70dddb19f14bd77d40c5eb19136b08664040237f47` 与 node sidecar 相同。05 上 forced native reinstall 与 build-input check 均 **0**，五包 ruff/mypy 十步均 **0**。非 serial focused exit **1**：`163 passed, 13 failed`。其中 12 个新增 native focused 用例均在 `_side` fixture 的 `digest(source_fill)` 入口因单字符填充值只形成 32 个 hex 而触发 `DigestRef` 要求 64 hex 的 `ValueError`，尚未触及目标语义；另一个 architecture 检查指出新 `.mutation_planning.native` 与 `.mutation_planning.storage` 在 B 阶段尚未有生产入口可达。未执行 serial focused 与 t1–t4 driver，不据此推断它们通过或失败。outer/entry/final exit **1**、capture **0**，结束 HEAD 固定 99b4、status 空、六锁前后相同、marker file/dir release 双 **0**。本候选整体 **FAIL**，是测试 fixture 与阶段架构登记问题，不重分类为工具故障；原始失败保留。

`unreachable_modules` 对 facade re-export 按实际导入的符号求可达，单在 `mutation_planning/__init__.py` 导出 B API 不会使两个新模块真实可达，不能靠虚构生产调用通过。B→D 冻结分工把生产接线放 D；可复审的最小阶段例外是仅对这两个确切模块在现有 `UNREACHABLE_MODULE_BASELINE` 同一 diff 加明确 B 暂存、D 真接线时删除、S4 E 不得残留的理由。`architecture_baseline.py` 顶部要求新增项有明确已审理由且过时即删，虽亦写 baseline 原则上只收缩；这里须作为有限阶段例外公开记录，不能扩大 import/cycle 基线或把测试豁免当真实生产消费。实际修订 diff 与后继节点结果待核。

## 4e9c042e 受影响修复静审（未运行）

固定 HEAD `4e9c042e2a4951f52fb2382d676639bd69e4c7a0`，Rust tree仍 `fdfe6daed59cb58d5c2aa7c39fa3cccba94424d2`；审核 WT `/home/dev/gdds-s4-b-review-4e9c042e` clean detached、linked legacy，`git diff --check` 空。相对 99b4 的 B 相关改动只有两份测试文件：`test_storage_mutation_native.py` 将 `_side` 的单字符 fill 在调用现有共享 `digest()` 前双写，并将 rule/rebound 的单字符参数改成双字符，产出要求的 64 个 lowercase hex，测试期望业务语义未变；不动共享 helper 或产品。`architecture_baseline.py` 仅加入 `.mutation_planning.native` 与 `.mutation_planning.storage` 两个确切暂存项，同一 diff 注释列明 B 先落地、D 生产接线时删除、S4 E 不得残留；不改 import/cycle baseline、reachability 算法或生产调用。按现有明确审核例外，**B 相关静审 CLEAR**，实际架构/focused 仍待专用节点后继固定稿验证。99b4 的 13 个原始失败保持原状；本区间另有 S3 并行文档三文件，不计 B 增量。

r7 固定目录 `/home/dev/gdds-test-tmp/p6-s4-b-r7-4e9c042e2a/`：node.sh SHA256 `f5d380444526450cbaa50eccdb09ea7e5d8be50e683b21a4ea046120b40ac068`，run.sh SHA256 `a23f0a424e948fb014d5906e67780dfc3c7eacd517d60ad9e7f81218e9a2c8f9`，source.bundle SHA256 `c1f19fad2fda4744c3241c573103bccd82d43cc50fee4c49c678585240705040`，driver SHA256 `fe76ddbb8b855f053b303d98996f9cb3754b98f2ce73b317c726e786eea2fd5e`，逐项本地相等；bundle complete history、唯一 4e9c HEAD。相对已审 r6 的两脚本字面 diff 只替换候选、唯一目录/session、脚本/bundle SHA 与固定 driver 路径，执行范围、失败停止、原始捕获和节点占用不变。结论 **SCRIPT_CLEAR_FOR_FOCUSED_AND_TABLE_DIFF_DEBUG**，非 B GO，实际结果待核。

### r7 节点 focused 通过、外置 driver 启动失败核收

外层 `controller/outer.log` SHA256 `c34197dc36c36efdcb78d1eb390d2b8cfd1b25fe3e53cec9fb8c19580f3460f4` 与 sidecar 相同；captured node `focused.log` SHA256 `08afd54cd06887ac82b7ace48a3f2107d904b3f627bb2c2b29c2c10a57254880` 与 node sidecar 相同。05 上 forced native reinstall/build-input **0**，五包 ruff/mypy 十步 **0**，六文件非 serial focused **176 passed/exit 0**，serial focused **3 passed、176 deselected/exit 0**。随后 t1–t4 driver 尚未进入 Python：`uv-consume.sh` 的跨项目脚本路径检查拒绝 WT 外绝对 `.py`，原始 exit **2**，因此逐表差分 **未运行**，不能记 B GO 或真实表结果。outer/entry/final **2**、capture **0**；结束 HEAD 4e9c 固定、status 空、六锁不漂、marker file/dir release 双 **0**。此为固定执行稿工具边界错误，保留原始失败；可在固定 SHA 的外置脚本上用 `python -` 从 stdin 交付字节，经同一 uv-consume 与锁检查运行，先独审修订精确脚本，再只复验受影响的 driver 步骤并引用本次已过的 focused 原件。

r8 driver-only 固定目录 `/home/dev/gdds-test-tmp/p6-s4-b-r8-driver-4e9c042e2a/`：node.sh SHA256 `9885f0cc79da23a7331f13216d34a3db1e371c844cf7c6a23416ca9853ec9376`、run.sh SHA256 `41c49d6ce0831a4bac2bc2b46f80681abb8c0a39a77fde5378c6cd41212331d3`、driver SHA256 `fe76ddbb8b855f053b303d98996f9cb3754b98f2ce73b317c726e786eea2fd5e`，本地逐项相等。脚本在同 05 新 session 原子占用后复核原 r7 clean detached WT 的固定 4e9c HEAD/Rust tree、六锁、legacy、离线工具链及 extension build-input，不 fetch/checkout/sync 或写 WT；引用已核 r7 focused 原件，仅跑受影响 t1–t4 driver。外层/节点先核 driver SHA，再经 `uv-consume run --no-sync python - < fixeddriver.py` 从 stdin 交付脚本内容，保留 uv 锁检查且不把 WT 外路径作为 `.py` 参数；原始 exit/log SHA/capture 与 marker 收尾仍记录。结论 **SCRIPT_CLEAR_FOR_DRIVER_ONLY_DEBUG**，不是 B GO，实际节点输出待核。

### r8 真实首表产品失败核收

外层 `controller/outer.log` SHA256 `28a54b914b4652efe4b829d5350fa47f90baa750dcf82fe0ad5bb5258649758a` 与 sidecar 相同；captured node `focused.log` SHA256 `d916780b763133b84c56f5b94cfd611520914f1afbcabded2a884ee6ef1f1ec6` 与 node sidecar 相同。05 原 r7 WT 固定 HEAD 4e9c、status 空，六锁不漂，marker file/dir release 双 **0**；extension build-input check **0**。driver 实际启动并通过固定 datasets/census 摘要及八件真实 source package 的 size/SHA 预检，随后在首个 `prepare_storage_table` 抛 `ValueError: CANONICAL_SCHEMA_REQUIRED`，逐表差分 exit **1**，outer/entry/final **1**、capture **0**；没有完整 t1–t4 结果。此是 B 接真实 canonical producer 的**产品 finding**，不是 r7 的脚本路径工具错误，也不能改真实数据或放宽验证。

**B-F6（真实 fresh canonical view 缺口）**独立源核：Rust `storage_mutation::checked_rows` 复用 `comparison::kernel::validate_canonical_batches`，明确要求 schema metadata `gdds.canonical_mapping_version=1` 和每 field 的 `gdds.canonical_type`。真实 `publish_canonical_tables` fresh-write 分支在已验证 canonical IPC 输出后仅 `table.reader.reopen()` 并标 `canonical_comparison_verified`，返回的是仍无 profile metadata 的 projection Arrow backing；现有 Comparison `production._stream` 对此有专门受信分支，调用 SnapshotMaterialization owner 的 `canonical_comparison_profile` 创建带 metadata 的只读视图及字段 indices，并保留原 backing/profile/必要 BIT cast 的 M charges 至最后 owner。B `storage_projection.open_storage_input` 当前直接传 `isolated.arrow_stream()`，缺少这条共享 view 桥，故真实首表拒绝。修复应复用 SnapshotMaterialization owning canonical profile 语义，维护同一 operation/M 和 last owner；不得跳过 Rust canonical validator、直接伪造 metadata 或给 B 添加另一套 mapping。后继产品修订与节点逐表差分待复审。driver 可在每表处理前增加有界 table/tier 诊断行，固定新 SHA 后审，避免失败时丢具体表名。

**B→C 资源移交限制**：现 B adapter 的 `_prepare_storage_table_native` 在 reconcile 后把 Python native reservation 缩至当下 Rust `KernelContext` 已用量；Rust context 仍以初始 remaining 创建，直到 operation close 才 seal。B 当前只暴露 summary/discard，后续无新分配路径，阶段内可用。C 若在同一 context 上新增 renderer 分配，不能沿用已归还给 Python 的 native 余额而只在 Rust `reserve/grow` 中扣减；需在 render 前建立同 M 的新预约/phase 或按既定封存子额度设计使两边账一致，最后 owner 仍释放。B GO 不代表 C native render 的未来预算已证明。

## 807c7666 真实 fresh canonical view 修复静审（未运行）

固定 HEAD `807c7666e9f410a7de08c426739e6364a5b352c5`、Rust tree仍 `fdfe6daed59cb58d5c2aa7c39fa3cccba94424d2`；审核 WT `/home/dev/gdds-s4-b-review-807c7666` clean detached、linked legacy，`git diff --check` 空。B 修复跨五份 Python 产品/测试文件，另有 S3 并行文档一行，不计 B。SnapshotMaterialization 新 `canonical_view.py` 抽取 Comparison 既有 fresh canonical profile 的 metadata/bit 预算、字段 indices、BIT cast 和原 Arrow backing 借用；schema/indices 仍由 `canonical_comparison_profile` owning Native API 生成，未复制映射或跳过 native validator。Comparison `_stream` 普通 Arrow 分支改调用公共 `canonical_comparison_input`；原 `_fresh_view_budget` 名为该公共预算函数的薄别名，供既有 S3 测试消费，不留旧算法。StorageProjection 在验证 artifact/完整 manifest/descriptor/同一 active operation 后调用公共 view，lease 持有其 stream 与 input owner 至最后关闭。

新 `_FreshViewOwner.close()` 以 `ExitStack` 登记原 stream、reader、BIT charge、profile charge，使任一 `.close()` 抛错时其余项仍尝试关闭；`StorageInputLease.close()` 的 nested finally 也保留 stream/input owner/table readers 的全项尝试。新 focused 向量实际调用 `publish_canonical_tables` fresh-write，先证返回 schema 无 canonical profile metadata，再经 B lease/native 验 D/U/I=(0,1,0) 与 operation 结账，针对 r8 真实缺口有语义价值。外置 driver SHA256 `9277ea22d04c0dd671fadf615d0480af6284617cd9255af6344a8298a55e85db`，相对 fe76 只添每表开始标识和有界 schema 诊断（最多八 schema keys、字段数/带类型字段数）；原 oracle、资格、固定 datasets/census 与八件源 SHA 不变。静态修复方向 **CLEAR**；实际五包静态、B focused、`test_comparison_s3_d_production.py` 既有 fresh/BIT/partial metadata/预算回归及 t1–t4 逐表须在固定节点稿核，r8 原始产品失败保留。

r9 固定目录 `/home/dev/gdds-test-tmp/p6-s4-b-r9-807c7666e9/`：node.sh SHA256 `d1804731c11fa4316acfe71e743637b8c13c2c63e5a3a709153053ad99120cca`，run.sh SHA256 `6178adf551aa002776878cad341f57a8186138c4381d38c7ae4d8b3e3ce866ac`，source.bundle SHA256 `66688968f0d4871757c6cc20c40000d4811cf30713f31993542c71bbb2d914ec`，driver SHA256 `9277ea22d04c0dd671fadf615d0480af6284617cd9255af6344a8298a55e85db`，本地逐项相等；bundle complete、唯一 807c HEAD。相对 r7 两脚本字面 diff 只改固定身份/唯一路径/SHA、加入 `test_comparison_s3_d_production.py` 为第七 focused 文件，并沿 r8 已验证可启动的 `python - < fixeddriver` 方式；原子占用、force native ext/check、五包静态、非 serial/serial 两遍、成功后逐表与失败停止/捕获不变。结论 **SCRIPT_CLEAR_FOR_FOCUSED_AND_TABLE_DIFF_DEBUG**，实际节点结果未核，非 B GO。

### r9 节点 typing 失败核收与静审修正

外层 `controller/outer.log` SHA256 `40ba42355956f04b38e7b17ad747cb913e0225a0677e08316bc898cc14e59cca` 与 sidecar 相同；captured node `focused.log` SHA256 `090c070242d519d6fb9b23eb019ffd818b1b03e631a60f16e3a058f8d2be4321` 与 node sidecar 相同。force native reinstall/build-input **0**，shared_kernel/repository_contracts/repository_client ruff/mypy 与 backend ruff **0**；backend mypy exit **1**，唯一 `test_comparison_s3_d_production.py:31`：从 `comparison.production` import 的 `_fresh_view_budget` 仅是重命名别名，strict mypy 视作未显式导出的私有属性。脚本失败即停，repository_service static、七文件 focused 与 t1–t4 driver **未运行**。outer/entry/final **1**、capture **0**；结束 HEAD 固定 807c、status 空、六锁不漂、marker file/dir release 双 **0**。此为受影响测试 import 的 typing 问题，候选整体 **FAIL**；此前静审认为薄别名可供既有测试消费而未识别 mypy 导出规则，该判断在此纠正。后继应把真实测试消费改为 SnapshotMaterialization public `fresh_canonical_view_budget`，生产同用该名称，保现有测试名和断言；另固定新候选复验。B-F6 仍仅静态修复，尚未以节点真实逐表结果关闭。

固定修订 HEAD `fab776cf3f3777eb69609b398ee6354e0c9ab5ce`、Rust tree不变；审核 WT `/home/dev/gdds-s4-b-review-fab776cf` clean detached、linked legacy，`git diff --check` 空。相对 807c 仅 Comparison production 与既有 S3 D production test 两文件把 `_fresh_view_budget` 私有别名改为从 SnapshotMaterialization 公共 facade 直接 import/use `fresh_canonical_view_budget`，原求和与两处预算断言不变；无算法、golden、测试名修改。受影响修复**静态 CLEAR**；节点 mypy/focused/真实差分待新固定稿。

r10 固定目录 `/home/dev/gdds-test-tmp/p6-s4-b-r10-fab776cf3f/`：node.sh SHA256 `a2ead3b900ca4858e0716e287a371d1f6c28b306811e4b29b92a989b6ba525ba`，run.sh SHA256 `a507a6846ea3b3e762f67b0b2828a0abe61495707b1a1f392d83e746994e4020`，source.bundle SHA256 `dd22a5535db751a0177be00ab1514f188ca9ec45aaa90d9fd0570eda3eebe5e6`，driver SHA256 `9277ea22d04c0dd671fadf615d0480af6284617cd9255af6344a8298a55e85db`，本地逐项相等；bundle complete、唯一 fab HEAD。相对 r9 两脚本只替换固定身份/独立目录/session/SHA 与 driver 路径，七 focused、force native ext/check、五包静态、`python -` 逐表、占用/失败停止/原始捕获逻辑均未改。结论 **SCRIPT_CLEAR_FOR_FOCUSED_AND_TABLE_DIFF_DEBUG**，非 B GO，实际结果待核。

### r10 真实首表字段顺序产品失败核收

外层 `controller/outer.log` SHA256 `d2e49f82c4a98625cfe3f91bbf0d5e79a0f7530d017f32fa507a8767caa38286` 与 sidecar 相同；captured node `focused.log` SHA256 `05913cf9ac63ba515a89ca5f4fd69d87ab1d07891da71facae17976b64d64921` 与 node sidecar 相同。05 上 force native reinstall/build-input **0**，五包 ruff/mypy 十步 **0**，七文件非 serial focused **209 passed/exit 0**，serial **3 passed、209 deselected/exit 0**。driver 固定 datasets/census 与八件 source SHA 预检通过，首表 `tier=1, adv_app_list` 的 after schema 已有 mapping version 1、六个 canonical type metadata，说明 B-F6 的 fresh profile 桥已实际到达 native；但该表 `prepare_storage_table` 抛 `STORAGE_COLUMN_BINDING_INVALID`，逐表 exit **1**，无完整 t1–t4 差分。outer/entry/final **1**、capture **0**，结束 HEAD fab 固定、status 空、六锁不漂、marker file/dir release 双 **0**。此为第二个真实产品 finding，B-F6 的 schema 缺失症状已消除但整段尚不能 GO。

**B-F7（manifest 逻辑列序与 canonical IPC 物理列序绑定）**：Rust `canonical_ipc::canonical_plans` 按 `canonical_name.as_bytes()` 排序，`comparison_profile_v1` 返回的 schema/indices 同物理顺序；StorageProjection manifest `retained_columns` 保留 storage view/declaration 逻辑顺序，`open_storage_input` 正确核 descriptor 与 manifest 原顺序。B `_columns` 当前把 manifest 原 tuple 直接传 Rust core，`checked_rows` 对真实 schema 字段名逐位严格比较，且 `row_hash_at` 用此 tuple 与物理列索引配对；真实 `adv_app_list` 首次揭示两顺序不同。应在 FFI 边界从已验证 manifest 名称按 UTF8 bytes 排序得到 canonical IPC 物理序，再由 core 逐位核真实 schema；不能改 frozen manifest、把校验改成集合或直接信 stream.names。SharedKernel `encode_row` 自身按字段名排序，故可保 row digest。现有 B fixture `board/link_no/status` 恰为已排序序列，需一例非字典序真实 fresh writer 小向量证明该绑定。后继固定修订和逐表原件待核。

**B-F7 修法勘误**：以上 FFI 全局排序建议仅适用于 fresh `comparison_profile_v1`，对 cached persisted IPC 不成立。复核 `canonical_ipc.rs:2705–2731` 的 decode：它按调用方 descriptor columns 构造 `output_indices/output_schema`；Python `ArtifactReadHandle` 也按 descriptor 重排外部 stream，故 cached schema 已是 manifest retained 原序。若一律排序，反而会拒绝或错配 cached。正确边界是共享 SnapshotMaterialization canonical view 增 B 可选 `field_order=manifest.retained_columns`，在受信 fresh writer profile 的 schema、indices 和数组引用创建前建立双射并重排到 manifest 原序；Comparison 默认仍用原排序语义，persisted verified stream 原样传给 B 并由 core 逐位严格核。重排 scratch 在 profile charge 内预留，异常和最后 owner 释放不变。回归须覆盖非字典序 fresh **及** cached reader；此前原始发现和 r10 失败保持有效，仅撤回不适用的修法建议。

固定修订 `e8d649c0cd755609fa8b514cff4af41a977c3e17`、Rust tree不变；审核 WT `/home/dev/gdds-s4-b-review-e8d649c0` clean detached、linked legacy，`git diff --check` 空。共享 `canonical_comparison_input` 的新可选 `field_order` 在已预留 profile metadata charge 后，将受信 fresh profile 字段/indices 按 frozen manifest 名称做双射重排；cached 有 metadata 分支保持原样，Comparison 不传该参数，B `open_storage_input` 传 manifest retained 原序，Rust core 严格逐位核不变。该实现方向与 fresh/cached 真实边界一致。测试新增同表非字典序 cached before + fresh after 真实 publication/open，能覆盖顺序差异；但 `_side(column_names=...)` 初稿只改 manifest/descriptor/source/layout，未同步 `storage_view.retained_columns`，形成真实 producer 不会产出的 view/manifest 不一致 fixture。已请实施者同步 view 并固定后继候选；当前 e8d **静审未 CLEAR、未运行**，不将 B-F7 标已关闭。

后继固定 `edfa0ccb32b78eeeda1130cb57245eb76256a8fa`、Rust tree不变；审核 WT `/home/dev/gdds-s4-b-review-edfa0ccb` clean detached、linked legacy，`git diff --check` 空。相对 e8d 唯一一行在 `_side` 中按 `column_names` 同步 `storage_view.retained_columns`，使非字典序真实 cached/fresh 小向量的 view、manifest、descriptor/source/layout一致。B-F7 修复与 focused fixture **静态 CLEAR**，仍待节点静态/focused/逐表验证。已审 r11 e8d 脚本字面仅相对 r10 换固定身份/路径/SHA，但因 e8d 已知 fixture 缺口且 edfa 已固定，建议不执行 r11，转为 edfa 新稿；未运行 r11 不形成任何证据。

重固定 r11 edfa 目录 `/home/dev/gdds-test-tmp/p6-s4-b-r11-edfa0ccb32/`：node.sh SHA256 `946ad66ceafd30d5d132328c6534067c1ea68abb7f82beea20121c26bed4e13b`，run.sh SHA256 `0b7291ed68e0201a4cc29a621c15c3214a56fe545b065208a98dacf70d8cf2bd`，source.bundle SHA256 `9278ad6d150fa41551eed1f3eb5b68cd49cfa3dfb1493e10238708a51bda3eea`，driver SHA256 `9277ea22d04c0dd671fadf615d0480af6284617cd9255af6344a8298a55e85db`，本地逐项相等；bundle complete、唯一 edfa HEAD。相对 r10 两脚本仅固定身份/唯一路径/session/SHA 与 driver 路径变化，原子占用、force native ext/check、五包静态、七文件两遍 focused、`python -` 逐表及失败停/原件捕获不变。结论 **SCRIPT_CLEAR_FOR_FOCUSED_AND_TABLE_DIFF_DEBUG**，非 B GO，节点结果待核。旧 e8d 稿未送节点。

r11 edfa 外层实际在 2026-11-08 18:54:44 UTC 预检遇 `busy_marker_present`，`outer_exit=2`；`controller/outer.log` SHA256 `487cdd97a8aaa7daf7be4562954eef511c20c887ba443d6d833593ced2e22e10` 与 sidecar 相同。未建远端 staging、未 SCP、未进 node 脚本或跑测试，故无 node capture、focused/逐表结果；这不是 B 产品失败，也不能算 B 通过。保持他人 marker，不抢占或删除；后续须在实际空闲节点以新唯一固定执行稿重进。

04 新固定稿 `/home/dev/gdds-test-tmp/p6-s4-b-r11-04-edfa0ccb32/`：node.sh SHA256 `7d8ff1fa60fe1f1f307469831952de9a098d2059af10f841e14b79adcda35559`，run.sh SHA256 `087c209e2a406f570b619b7c568352382859129bed7373f240049a9e68545d15`，source.bundle SHA256 `9278ad6d150fa41551eed1f3eb5b68cd49cfa3dfb1493e10238708a51bda3eea`，driver SHA256 `9277ea22d04c0dd671fadf615d0480af6284617cd9255af6344a8298a55e85db`，本地逐项相等；bundle complete、唯一 edfa HEAD。脚本固定 `ct108-gw-dms-04`/实际 hostname `gw-dms-test-04`、新 RUNROOT 与外置新 Cargo target；原子 marker 后取 bundle 建 clean detached WT/legacy，核六锁、离线/四 Rust 工具链、HEAD/tree，先在 04 全 workspace 跑 Rust fmt/clippy/test 三步，任一失败即停 Python，不借 05 Rust 结果作跨节点 carried。全 0 后 force native ext/build-input、五包 ruff/mypy、七文件非 serial/serial 两遍、固定 driver `python -` 的 t1–t4 差分，原始 exit/log SHA/status/锁/marker 收尾仍完整。结论 **SCRIPT_CLEAR_FOR_FOCUSED_AND_TABLE_DIFF_DEBUG**，非 B GO；实际 04 结果待核。

### 04 r11 新 cached/fresh 用例 operation metadata 断言失败核收

外层 `controller/outer.log` SHA256 `086133d718bbc3d2ec48f58569ed3fec10c87b02a70e3cff2c19da19ee9551a7` 与 sidecar 相同；captured node `focused.log` SHA256 `e439172505db084aa74d21770d3e76456a584387872508423ce9ee18918a408e` 与 node sidecar 相同。04 上 Rust workspace fmt/clippy/test 三步 **0**（workspace各 crate 测试均通过）、forced native reinstall/build-input **0**、五包 ruff/mypy 十步 **0**。七文件非 serial focused **208 passed、1 failed/exit 1**；唯一失败为新 `test_fresh_and_cached_canonical_inputs_keep_declaration_order_for_storage_diff` 的末尾 `used_bytes == 0`，实值 **56320**。该测试此前 cached before + fresh after schema 均为非字典 manifest 顺序，native D/U/I=(0,1,0) 等目标断言均已越过。原件末尾显示 `open_snapshot_table_artifact` 在 `artifact.py:349` 为 returned manifest/descriptor AST 将 `manifest_ref.size_bytes * 32 + 4096` 放入 `context.resources`，此 charge 持续到 operation scope 退出；本次值恰为 56320，`context.memory.close()` 只 flush retained metadata，不能释放此 operation-lived reservation。不能删正确产品 charge 或提前 `context.resources.close()` 掩盖表级 Arrow/native 泄漏。修订测试应在 handle/lease 关闭且 metadata flush 后精确断账本等于该唯一 operation-lived manifest charge，额外 Arrow/native 占用仍使断言失败；其他零账本用例保持原断言。脚本按失败停止，serial focused 和 t1–t4 driver **未运行**。outer/entry/final **1**、capture **0**，结束 HEAD edfa 固定、status 空、六锁不漂、marker file/dir release 双 **0**。B-F7 语义障碍已有 focused 局部证据，但整体候选仍 **FAIL**、不得 B GO 或记逐表通过。

固定测试修订 `788ed36e7742a067bf01c16ad2e6aaed2fed91fb`，Rust tree不变；审核 WT `/home/dev/gdds-s4-b-review-788ed36e` clean detached、linked legacy，`git diff --check` 空。相对 edfa 仅重构上述新 test 到独立 operation scope，保留真实 cached/fresh 与 D/U/I 断言；table handle/两个公开 lease 已关闭后，scope 内先 `context.memory.close()` 只 flush metadata，再精确断 `used_bytes == manifest_ref.size_bytes * 32 + 4096`，该公式来自未改动的 SnapshotMaterialization `artifact.py:349` operation-lived manifest AST owner，非 B 新实现输出反填期望。任何额外 Arrow/native reservation 会使等式失败；scope 退出后再断账本零。未提前关闭 `context.resources` 或修改产品收费/测试业务期望。受影响测试修订**静态 CLEAR**，实际节点 focused/逐表待新固定稿。

r12 04 固定目录 `/home/dev/gdds-test-tmp/p6-s4-b-r12-04-788ed36e77/`：node.sh SHA256 `8522fc8808dfb0941809bfd41efe2b9168837b942dbad7ff9ae616bcff85fc78`，run.sh SHA256 `d9e802ad27b19b25efc71e61a8214164bebdd13de959a7484c8a96dacf41ca5a`，source.bundle SHA256 `de140fb5b6eabb791474158a58c3d2ae72f2b936731fc4369cfaf72006f99384`，driver SHA256 `9277ea22d04c0dd671fadf615d0480af6284617cd9255af6344a8298a55e85db`，本地相等；bundle complete、唯一 788 HEAD。相对 04 r11，脚本仅换固定候选/独立目录/session/SHA，并注明相同 Rust tree 在同 04 r11 已跑全 workspace fmt/clippy/test 三步 exit0、原日志 SHA `e439172505db084aa74d21770d3e76456a584387872508423ce9ee18918a408e`，本次复用同节点外置 Cargo target；该引用只减省 focused 调试重复，不作跨 worktree package carried。force native reinstall/build-input、五包静态、七 focused 两遍、成功后 driver stdin、marker/HEAD/六锁/失败停/原件捕获不变。结论 **SCRIPT_CLEAR_FOR_FOCUSED_AND_TABLE_DIFF_DEBUG**，待实际结果，非 B GO。

## r12 04 原件独立核收与 B 最终结论

固定候选 HEAD `788ed36e7742a067bf01c16ad2e6aaed2fed91fb`，Rust tree `fdfe6daed59cb58d5c2aa7c39fa3cccba94424d2`；04 上 clean detached WT 结束 HEAD 固定、status 空。外层 `controller/outer.log` SHA256 `21ecf1714eba271a4c444590d19d0816ce7cfc3f846a762247e4b2b80feb340d` 与 sidecar 相同；captured node `focused.log` SHA256 `8fb0db9d7cde02e24d503859dab845295dee655b5abdf9f38f5448a5cce84e28` 与 node sidecar 相同。开始 2026-11-08 19:08:43 UTC、结束 19:15:14 UTC；`ssh_node_entry_exit=capture_exit=outer_exit=entry_exit=final_exit=0`，六锁前后相同，marker file/dir release 双 **0**。上游同 04 r11 对相同 Rust tree 的 workspace fmt/clippy/test 三步均 exit0 且原件已核，本次仅作为同节点 focused 调试引用，不声称跨 worktree按包 carried。r12 强制 native extension 重装与 build-input check **0**，五包 ruff/mypy 十步全 **0**，七文件非 serial focused **209 passed/exit0**，serial **3 passed、209 deselected/exit0**；含 B native、架构、N/batch、资源/取消及受影响 Comparison S3 D production 回归。

固定 driver 的 datasets metadata SHA256 `78c7cbba05acbbe92cc9a22351f8caf800824c4520e0d9685c6e776d6042da4f` 与 census SHA256 `733b506e43164a62f30d3a1d665449471e8edf25b515701150f6e73a824a6988` 均实核；八件 `rd-t1-a` 至 `rd-t4-d` v1/v2 原包各自 size/SHA 均实核。`s4-b-t1-t4-differential` exit **0**。独立解析原始逐表 JSON：每档的 `table_start`、`table_input`、完成行数与名称顺序逐一相等，完成表名无重复；可比资格数与 `net_counts is not None` 数逐档完全相等，driver 对每个可比表先以旧 Python adapter/row digest 算 D/U/I，再核 B 结果与整数阈值决策，非可比表按 metadata identity 核决策且保持 net counts 缺席。

| 档 | 完成表 | 有 D/U/I | `net_counts=None` | NOOP | REBUILD | PATCH |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| t1 | 125 | 43 | 82 | 121 | 4 | 0 |
| t2 | 220 | 88 | 132 | 159 | 60 | 1 |
| t3 | 193 | 71 | 122 | 139 | 54 | 0 |
| t4 | 312 | 138 | 174 | 285 | 15 | 12 |
| 合计 | **850** | **340** | **510** | **704** | **133** | **13** |

以上 D/U/I 只适用于 340 张完整 keyed、满足可比资格的表，不能把其计数推广为 850 表的通用净变化。driver 一次投影全档并用内存 artifact store 与独立 Python oracle，输出内存 high-water 仅作差分诊断，**不证明 D/E 生产逐表 M 容量**；此次也不是完整 Submit/SQL/Compose/权威六包 runner。

**独立审核结论：B GO（限定 S4 B 代码、focused 与 t1–t4 逐表差分）**。B-F1 真实 Arrow lease 同 operation/M、B-F2 完整 frozen manifest/item owner 绑定、B-F3 共用唯一 policy、B-F4 FFI 预收费、B-F5 长转义 key/metadata scratch 的资源界限、B-F6 fresh canonical profile、B-F7 非字典序 fresh/cached 绑定均经固定源码复审与对应 focused/真实逐表结果闭合。所有此前失败原件保持原始分类，不倒改为通过。B 新 Rust/扩展进入 backend image 输入闭包；当前 B HEAD 最后验证的容器 image revision/source-tree 为 **none**，镜像构建与 Compose 门禁延期至 S4 最终候选，由 E 按阶段身份/闭包规则执行。D 真正接线时必须删除 `UNREACHABLE_MODULE_BASELINE` 的 `.mutation_planning.native/.storage` 两个临时项，S4 E 不得带出；C renderer 须解决上文 native reconcile 后新分配同 M 重预约/封存问题。B GO 不替代 C/D/E 各自验证，也不解除并行 S3 容量或 Q18 等其他工作状态。

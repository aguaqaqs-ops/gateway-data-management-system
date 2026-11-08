# P6 S4 B 独立代码审核（累计）

2026-11-08。当前结论：**CHANGES_REQUIRED**。这是固定 B 首候选的静态代码审核，不是 focused 测试或 S4 退出结论；固定执行脚本、t1–t4 逐表差分和节点原件待单独核收。

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

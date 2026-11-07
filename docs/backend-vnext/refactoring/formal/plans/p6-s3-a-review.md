# Phase 6 S3 A 独立审核

2026-11-07。初审固定候选 `34f68dc0c0016aeadbba53cd8e0c11b8b5869bcd`，相对协调起点 `748de5034d`；结论 **CHANGES_REQUIRED**。本结论只针对 A 的 Contract、内部接口与独立预期移交，不评价 B/C 内核或 S3 阶段退出。设计固定 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`，kickoff 复审 `83ba4979044179256aa8c3d5d1d7b3424e648884` 最新 §5 已 READY_FOR_OWNER；不重开其已关闭的 kickoff findings。

## 1. 对象与方法

审核在新 detached worktree `/home/dev/gdds-s3-a-review-34f68dc0` 完成，HEAD 固定、tracked worktree clean，已链接 `legacy`。候选仅改 `docs/backend-vnext/contracts/comparison.md`、`risk.md`，新增 `p6-s3-a-contract-handoff.md` 与 `test_comparison_s3_contract_vectors.py`；未改产品代码、部署、锁或镜像。`vnext` tree 为 `ca38e24002e1cf6e9aa970ec56fdbc0c25fbbfc8`，相对设计起点的变化只有新测试。

只读核对 AGENTS、testing conventions、比例化/Rust 政策、S3 设计/kickoff 与 Comparison/Ordered Diff/Risk、Shared Canonical Encoding、Canonical Storage、Snapshot Table Access、Surface/Bundle 和 Operation Lifecycle 边界；逐项追 `comparison/row_encoding.py`、`standard.py`、`artifacts.py`、`risk_evaluation/_facts.py`、`_engine.py`、现有 tests/Parquet 固定向量及 benchmark/example consumer。没有在开发主机或审核 worktree 执行测试、编译、lint、容器或性能测量；06 测试者的 focused 原始证据尚未提交，不记 PASS。

## 2. Findings

### A-F1 / P2：比较与三族记录的 A 向量尚未形成可核收的 06 证据和逐项 expected 映射

**位置与复现：** kickoff §2 的 A 行要求 06 Contract 向量覆盖负零/NULL/UTF-8 与 JCS 顺序、keyless 重复、LIS 并列、schema 变化和三族 records，并审 expected 来源。候选 handoff §3 的 C1–C6 给出了文字输入/关系，但没有把每项绑定到实际测试 nodeid、固定 fixture、预期 bytes/digest 或明确需新增的纯向量；§4 的唯一 pytest 命令仅执行新 `test_comparison_s3_contract_vectors.py`，其中三个测试都在 Risk 分支。已有 `test_comparison_standard.py`、`test_comparison_ordered.py`、`test_comparison_records.py`、`test_comparison_artifacts.py` 与 `vnext/fixtures/vectors/comparison/records/{standard,ordered,blank}-v1.parquet.b64` 可作为部分独立来源，但候选未列明哪些现有断言支撑 C1–C6，也未有本 A 候选在 06 的运行证据。

**影响：** B/C 接手时仍需猜测 C1–C6 的权威 expected、具体字节与缺项归属；当前三个风险测试即使全过也不能证明 kickoff 指定的比较/记录 A 向量已核收。此项影响派生 comparison facts、records content/raw identity 的冻结回归，属于现有 Contract 边界，不要求 A 实现新 Rust 内核。

**最小修复：** handoff 按 C1–C6 各列具体 nodeid/fixture 与独立 expected（字节、摘要或确定性的完整逻辑结果），注明仍由 B/C 实现 adapter 后才可执行的断言；对现有测试缺的 A 纯语义向量补最小测试。测试者在 06 的 clean 固定提交上运行 A 适用 focused nodeids并提供 hostname、起止 HEAD/时间、exit、日志 SHA256；不能用新 Rust 输出生成 expected。避免复制 Shared Kernel 已有全编码矩阵。

### A-F2 / P2：风险 Arrow 批消费边界尚未固定为可对接接口

**位置与复现：** kickoff §2 的 A 行要求固定风险 batch 接口和预算 owner。设计 §5 已给建议入口 `iter_record_batches(table,family,columns)`，§9.1 将 facts 序与 artifact 序明确区分。候选 Comparison Contract 新段、Risk Contract 末段及 handoff §1/§2 只称“按需投影 Arrow batches/最少列”，没有确定调用所用的 family、facts 顺序选择、返回批的必要列与 owner 生命周期，以及 `_facts.py::has_visible_change/_risk_scope/_ordered_unsupported` 所需的 records count/存在性小事实如何与批接口配合。`_engine.py::_emit_row_risks` 目前按 ROW_ADDED、ROW_DELETED、ROW_MODIFIED 三轮遍历 facts 记录；`_require_records_closure` 只在 matching_count 为零且未全部 suppressed 时触发，必须保持其原位置与当前 pair 绑定。现文字不足以使 C 的 producer 与 D 的 consumer 对同一接口验收。

**影响：** 两种记录顺序、重复遍历和 closure 控制步骤可能在语言交界处被误接，改变风险标注编号、pair cap 或失效分支；若 consumer 为补接口而整表转 tuple，也会背离已接受的预算边界。风险输出及 closure 均为现有可见派生事实。

**最小修复：** 在 A handoff/owning Contract 固定最小内部批入口（family、columns、facts-order、只读可重放批/owner 的有效期与失败语义）及 count/存在性小事实；逐风险 consumer 写明所取列、是否读行和原控制步骤的位置。保持 Python 规则 owner，不新建持久协议、缓存框架或生产接线。R1–R5 的独立预期仍按既有 `_engine.py` 控制流，不由新实现生成。

## 3. 已核边界与待证

候选已明确三种逻辑视图不能互代：table/core 摘要使用完整 facts payload，records 内容按 artifact 序/detail 裁剪，risk 使用 facts 序；Blank 私有 `entity_key_kind` 不进 Parquet。三族物理字段、nullable list element、metadata、1024 row group、真实 raw SHA 与 content digest 的区分同设计及现 `artifacts.py::_schema_for`/Rust `records.rs` 对齐。R1/R2 的异常与正常返回计数区别、过滤 Emit 在上限后仍触发、closure 当前 pair 校验都列有正确预期；新增测试是否实际通过待 06 原始证据。consumer 表已包含 replacement、`_facts.py` 存在性路径、真实 open/restore、`bundle_tar.py`、两项 benchmark 和 Rust example；没有把 Submit 存储 mutation 误并入 S3，也没有把 bundle raw/ref 校验说成全份 records 语义校验。

尚未运行的 C1–C6、R4/R5、K1、O1、真实 Arrow/PyO3、raw golden、FULL 驻留和 W3/W4 均不得由本次 A 静态审核推导为 PASS。A 可以通过明确移交 B/C/D 的后续断言关闭本节，不以本轮要求提前交付后续内核。

## 4. 容器与证据状态

Current HEAD=`34f68dc0c0016aeadbba53cd8e0c11b8b5869bcd`；container rebuild required=`no`，理由是本候选只改 Contract/交接文档和纯测试，未触 image/deployment/container-only runtime 或容器 harness。当前 HEAD 容器门禁=`deferred`，本 A 不宣称通过或 carried；最近既有已验证产品 image revision=`49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0`，source tree=`56720104af34a1eb677336f57bdbc07444a56615`，仅引用 BE-a/d 退出记录。B/C/D 生产接线和 E 最终候选按既定触发规则在专用节点重建/验证；A 的 06 focused 证据待测试者提交后独立核收。

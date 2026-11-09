# Phase 6 S3 A 独立审核

**最终结论：A GO。** 固定实测提交 `4d5a4b0d98ee2942a26eba794ce9f36a6826a9ec`；仅文档交接提交 `b8c0697df2be6629fb62ef75abc68396e36206bc`。下文初审 CHANGES_REQUIRED 保留为历史记录，A-F1/A-F2 的关闭与证据见 §5。A GO 只放行 kickoff 所列下一节依赖，不是 S3 阶段退出、容器门禁或生产接线验收。

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

## 5. 修复复审、证据核收与最终结论

固定修订 `29e4c442305222e5e5b47b9023e3f6aa66f0d422` 补 A-F1/F2；`4d5a4b0d98ee2942a26eba794ce9f36a6826a9ec` 仅纠正 shared_kernel pytest 命令中的 `-n 0`（该包 lock 没有 xdist），作为 06 唯一实测候选。最后 `b8c0697df2be6629fb62ef75abc68396e36206bc` 仅增补 A handoff 证据，`vnext` tree 与 4d5 同为 `3a97be17d966c410c61e92bb3ed70b2dba88246a`。修订及交接分别在新 detached worktree 只读核对，均 clean；未使用移动 main 替代固定候选。

| 初审项 | 独立复核与关闭依据 |
| --- | --- |
| A-F1/P2 | **关闭。** handoff §3 按 C1–C6 逐项绑定具体 shared_kernel/backend/Rust nodeid、现有 v1 scalar/JCS 与三族 Parquet fixture，列负零/NULL/UTF-8/JCS bytes、keyless occurrence digest、LIS 并列索引、schema 分类、三族 content digest 与 1024+1 row group、读侧三类语义损坏的独立 expected。来源为 owning Contract、S1b 冻结 Python 行为及先存 fixture，不从新 Rust 输出生成。06 对相应 focused 命令实际执行：shared_kernel 132 passed、backend 40 passed、Rust 三族固定向量 3 passed/51 filtered，三项原始 exit 均 0。C 的真实 Arrow/PyO3 adapter 与 raw golden 对照仍按后续 C 验收，A 不预记其 PASS。 |
| A-F2/P2 | **关闭。** Risk Contract 与 handoff §1 固定 `iter_record_batches(table,family,columns,order=FACTS)` 的合法族/列、全局 facts 顺序、可重复批遍历、借用 owner 和异常释放；`record_count/has_records/ordered_degraded` 保留 `_facts.py` 的记录存在性与 ordered 三来源。producer 的 artifact 序独立，Risk 的闭包检查仍由当前 pair 的 `records_access` 在原控制位置执行。Python 继续拥有规则/编号/cap；没有增加持久 DTO、兼容 tuple 或部署开关。 |

06 原始证据目录为 `/home/dev/gdds-test-tmp/logs/p6-s3-a-4d5a4b0d98ee/`；最终索引 `evidence-index.tsv` SHA256=`86974f17672252e85377d92f3ef41474e7ac149faa9ef66cbc3c87f447130093`，现场与侧车相同。只读 SSH 原件核对了 `gw-dms-06.lan`、各命令起止 HEAD 均为 4d5、原 exit、日志 SHA 和结束时 clean worktree。三份 focused 日志摘要依次为 `33a9a81b613aae1561f1ed140115fc3afa0eecde10db72bd35998a9de1b655d8`、`b2aa97504d72e243c6362e20f7d4c96dd8a7e602c5e958382c223fd6e90e4a4d`、`856bb8dc22da96a89d80bb14c2f2e05d9870c9879dc81b364bb9f435ef424c2a`。五个 Python 包的 ruff 和 mypy 共十项均 exit 0，逐项摘要、文件数、时间与命令见最终索引及 handoff §5；我逐原件复核，未重复执行测试。源码 bundle 由 `heavy-dev-01.lan` 经 LAN 到 06，源/目标 SHA256 均为 `4d69735712c1f714438eceafb864f4cc970d51f9c4c8246141e083ed3036171c`；节点本机预置离线缓存完成五包同步与 Rust 编译，无 cache miss，未使用代理。backend 强制重装后的扩展 build input expected=installed=`e6ac6e3b05cbd923affc5773106e51ab9cc9c2ec`，等于 4d5 的 Rust tree；六锁准备/收尾摘要一致。产品 N1 与 Cargo jobs4、pytest 单进程分开。

两次自身取证错误保留而未冒充产品失败。17:41:57Z backend sync 前断言误用旧 S2b-E Rust tree `137d499975f3c104ae9c3268b9e12befb2817ba1`；候选实际 tree 为 `e6ac...`，失败日志 SHA256=`7d67b353a114a4f6386980454a7ca5878006b56dc5c6f9b68addcf827d89da99` 证明 sync、focused 和被测对象尚未启动，按 DC68 从该步骤唯一更正后 backend sync 17:43:44–17:45:02Z exit 0，日志 SHA256=`dd42fe63bda28b068ac625838904656cb2ed0977cb3fb817ba9c3f91f4965c6f`。另在 focused 已成功后补录 backend 完整 argv 时，嵌套 heredoc 分隔符碰撞使首次补录命令非零；失败日志 SHA256=`76aa9e8e70318f48fd4dd966d4f16e9c04c895e2df697dc243fdeb3f3c38369f`，没有重跑测试或改原日志。实际 argv 是 17:54:01Z **事后逐字转录**，补件 SHA256=`8975df0082cb999a564f23bd75ca26f48f6fb9e973c5fef589b97492f0dcbcfa`，与 handoff §4 nodeids 对齐；原 backend 日志自身仅有占位命令行，不能把补件称为事前脚本。此出处限制已明确披露，原 40 passed/exit 0 日志保持原 SHA。

17:56:56Z 本人 marker 释放日志 SHA256=`ab398f9a814e915d288d55c867c9c529885af8985580b1b0f1714f339e39f905`；我另在 06 确认 marker absent、测试 worktree 仍固定 4d5 且 clean，无本任务测试进程、容器或 8000 listener。A 没有运行 04 权威 runner、Compose、真实旅程或正式性能，均属后续节点。本轮没有未关闭的 A finding。最终受审交接 HEAD=`b8c0697df2be6629fb62ef75abc68396e36206bc`；container rebuild required=`no`，仅 Contract/测试/交接，无 Docker、部署、container harness 或生产 runtime 边界变化；current container gate=`deferred`，last verified image revision/source-tree 仍为 BE-a/d 的 `49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0`/`56720104af34a1eb677336f57bdbc07444a56615`，不称本 HEAD passed/carried。B/C/D 生产接入及 E 最终候选按 kickoff 触发容器重建和集中门禁。

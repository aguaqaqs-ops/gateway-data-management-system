# S2b A 独立审核

状态：**PASS / A GO**（2026-11-06）。独立审核通过固定产品候选 `db7767ffbb5e4eee269b3c0e4778351dd98a092a` 的 A 范围代码、固定向量、06 实际验证与依赖/容器来源；无未关闭 Finding。Owner 已按 DC85 批准整体 kickoff 并启动 A，本结论仅完成 A 审核，不是 S2b exit，也不授权 B–E。

最终证据见 §7：[实施交接](p6-s2b-a-handoff.md) 记录具体执行范围与来源；workspace 四步、五包静态、实际安装扩展、8 项 adapter 行为、真实容器 readiness/clean-stop 和同镜像 codec smoke 均通过。最终 dependency-base 的完整输入及 config/全部 DiffID 已独立核对。容器扩展 build-input 实际为空，报告保留此限制，以固定 clean 候选的实际构建和运行 image provenance 绑定；不冒称字段匹配。以下 §2–6 保留增量审核与失败历史，最终状态以本段和 §7 为准。

交接已固定于 `b625d775e0e0a041a45bf6099e95b08c32a1cec5`，审核者核其相对产品候选仅新增上述交接文档，产品代码未变。已复核原始 ordinal 不写入 schema、framing 的原 owner 归属、worker 实际 image ID、两次身份提取失败的不同原因，以及最终 d054 完整身份来源。所有结论绑定已实际验证的 db776 产品候选，不宣称后续文档提交另跑了验证。

审核在独立 detached worktree `/home/dev/gdds-test-tmp/s2b-a-review` 进行，已建 `legacy` 链接；起点为 `d240b1e599a0149eec24c57b473fa53507bea66d`。开发主机仅做只读源码审核及本报告编辑，未运行测试，未操作 CT108 的冻结资源。测试节点 06 由实施者统一运行，审核者读取实际证据；本报告不改写失败日志或实施证据。

## 1. 已对齐的边界

依据 [A 任务单](p6-s2b-a-kickoff.md)、[映射 v1](p6-s2b-arrow-mapping-design.md) 和 [Canonical Storage Contract §5.1](../contracts/canonical-storage-and-repository-boundary.md#51-canonical-ipc-v1-内存-codecs2b-a)：A 接受已业务物化、规范投影、按 owning 语义排序的 Arrow batches；不实现业务列选择、伪 gid、行排序或表摘要 pipeline，不接 store/mmap/引用恢复或 worker/config，不切换生产 parser 或删除现有 Python 算法。

`ColumnDescriptor`、`SqlLogicalType`、Shared Kernel `DeclaredType` 与 JCS 复用既有实现；`sql_type` 是现有 projection owner 已规范化的输出。A 不移植完整 SQL normalizer，也不复制 DECIMAL、时间和 JSON 的业务语法。映射必需的声明/物理类型、整数范围、有限浮点、SET/BIT 与可空性仍检查。decoder 的格式/profile/绑定检查不是外来业务 IPC 的导入验收；后续 C 仍须核 raw SHA 和绑定身份。

局部 `max_input_bytes` 限制借用输入，`max_codec_peak_bytes` 限制 codec/adapter 拥有的同时存活分配；保守输入求和允许重复计费共享 backing buffer。A 不建立通用 allocation registry，不宣称这些值是完整 operation M 或 RSS。已有 caller-owned pool 可复用，N 确定性不要求为 codec 强行增加并行算法。

## 2. 固定代码审核记录

`bf5092bdb1` 交付 encoder、module export 与 `arrow-ipc` production dependency；`8b995d6866` 增补 decoder。两者均已在独立 detached worktree 读取；最终候选复核另见 §6–7。

encoder 早审发现并在固定差异中确认修正的事项：descriptor/JCS 分配前检查与转义扩张估算；持续存活的 schema/layout、规范 batch、writer encoded data 和累计输出增长的同时驻留；footer 按输出 batch 数计费；先统计整列 payload 再决定 schema 的 small/large 类型；实际输出限额不使用松估计误判；初始 schema 写入超限保留 Resource 分类。最终预算实现及相关定向用例后续在固定候选和 §7 证据中闭合。

零列但非零行的 `RecordBatch` 曾在输出构造中丢失行数。最初提出入口拒绝，随后主设计核实 `SnapshotTableDescriptor` 与 `EXPLICIT_KEYLESS` 全删列路径并不禁止零列，故撤回该建议。`112abf8c5a` 改用标准 `RecordBatchOptions.with_row_count(Some(rows))`；pinned Arrow reader 本身也使用 IPC batch length 保留零列行数。decoder 重排同样显式传入行数；定向用例后续通过，不改变业务 Contract 为“列必须非空”。

固定 decoder 问题及复审：

1. **P1：物理 schema 校验晚于标准 reader。** `8b995d6866` 的 raw preflight 核 metadata/name/children 后直接调用 `FileReaderBuilder`，物理型直到后置 `validate_reader_schema` 才比较。pinned Arrow 对非法 `Int.bitWidth`、缺失嵌套类型字段等会 panic；零列时 `schema.fields=None` 也不能当作合法空 vector。必须在标准 reader 前，用公开 safe FlatBuffer accessor 校验实际支持的 type union、必需 payload、宽度和绑定，并要求 fields 存在。共用同一 raw schema helper 核 header/footer 的声明一致，不建设第二 reader。实施者已接受。
2. **P2：decode 输入预算及 non-legacy profile。** `8b995d6866` 没有执行 `max_input_bytes`，仅用 `max_output_bytes` 限制传入 file；raw record-batch parser 同时接受 legacy 四字节前缀。应在 decoder 入口执行借用输入限额，并只接受 v1 continuation marker 与八字节前缀。实施者已接受。

`1a8d7b1552` 已在独立 detached worktree 复审上述修复：标准 reader 前核支持的 raw type 与必需字段，header/footer 共用同一绑定 helper；零列允许存在的空 fields vector，不能接受缺失 vector；decode 实际执行 `max_input_bytes`，`max_output_bytes` 只用于 encode；仅接受 continuation framing，连续 blocks 与 EOS 按固定 profile 校验。Utf8/Binary 的 raw 类型预检允许 small/large 两支，随后按完整列 payload 确认，未错误依赖尚未统计的初始 `large_offsets=false`。两项代码问题已修，代表性回归用例与 06 编译/运行证据后续已核对（§3、§7）。

## 3. 向量与证据状态

向量预期不得由新 encoder 输出反向生成。审核者在实现前手算了一组可复用布局：三行 nullable Boolean `[true, NULL, false]` 的 validity 为 `05`、values 为 `01`；Int64 `[7, NULL, -1]` 的 little-endian slots 为 `0700000000000000 / 0000000000000000 / ffffffffffffffff`；UTF8 `[é, NULL, 空字符串]` 的 offsets 为 `0,2,2,2`、payload 为 `c3a9`；BIT(9) `[0001, NULL, 0100]` 的 slots 为 `0001 / 0000 / 0100`。三行全有效字段的 writer validity 按 profile 是 `ff`。这些是独立布局预期，后续实现直接使用字节断言并在 06 通过，不新增重复 fixture。

本节记录固定向量与早期验证过程；最终 fixed vectors、SET/Shared Kernel 复用、N/chunk/列序确定性、零列行数、错误边界、取消/有限 deadline、实际 bytes 和 backend 互操作均已核对。06 最终日志、起止 HEAD、exit code、SHA256 与 installed extension build-input 见 §7。

`de2cf0906d` 的首批 Rust 用例已独立读取：上述手算 buffer 预期直接作为字节断言，覆盖三行 NULL/空值、all-valid bitmap、65,536 行切批、外层布局与零列行数；非法 Int96 的测试改写 footer 类型并捕获意外 panic，再断言 Schema 分类；借用 file 限额有直接 Resource 断言。live deadline/cancel 用例使用实际单调时钟及 atomic probe，运行时应串行处理，其输入大小与时间仅用于触发控制，不是性能 Contract。其余映射种类、N/DDL 确定性、空表与 output/peak 边界在后续最小补齐中完成，未重复完整业务 grammar 矩阵。

`4e6ab88703` 的扩展用例已独立读取：UInt、Float32/64、DECIMAL、ENUM、SET、JSON、日期/时间物理映射，N=1/2、descriptor 列序、空表与实际输出限额均已有断言。metadata 固定预期的 `bit_width`/`bits` 顺序修正有独立 JCS 根据：共同前缀 `bit` 后，`_`（U+005F）先于 `s`（U+0073），不能以 actual 反向确定 oracle。`9accf0bef9` 已复核规范时间文本、JSON 原文本、SET members 薄读、display_name/ordinal 不变性和纯计数 offset 阈值补充。

`4cd2df80fa1822b780ff5a6c5c48d25965d38ef6` 的中间 focused 日志已由审核者 SSH 只读核实：`gw-dms-06`，`08:18:12Z–08:18:18Z`，起止 HEAD 相同，`worktree_clean=yes`，offline/jobs=4 及同一 Rust 1.97 工具链已记录；fmt 通过，core 42/42 通过，`final_exit=0`。日志 `s2b-a-core-focused-4cd2df8.log` 的 SHA256 为 `6f3a2767f2682e5522e4b5dbad6b580528f6c308be206b5405a139d762b37f42`。这是该中间候选的 focused 证据，不能代替后续最终 workspace/adapter/container 验证。

最后一轮核心补齐已一次性汇总给实施者，完成后转入 adapter，不因既有映射表继续逐项扩大测试矩阵：

- 从既有 Shared Kernel scalar 向量取规范 DECIMAL、含 T/Z 的时间文本及浮点 bits（存储宽度、subnormal、负零）；JSON 保留原空白和键序。A 只验证映射保值，不重测业务 grammar 或新增 literal parser。
- SET 薄读既有 `values.set.declaration-order-members` 的 members，与解码后的声明序文本对应；sequence framing 仍由原 Shared Kernel owner 测试负责。small/large 阈值只作纯计数边界检查，不分配 2 GiB。
- 在已有确定性/布局用例覆盖 descriptor `display_name`/`ordinal` 变化、全 NULL 列及普通 Binary 小值。
- 在已有 Int96 与输入限额回归旁补最小 metadata/profile 拒绝组；不扩展为通用 Arrow 安全矩阵。
- peak 用例需至少一例允许入口 metadata、随后因规范 batch/输出增长而拒绝；仅 `max_codec_peak_bytes=1` 不能证明增长检查。实际 IPC bytes/profile overhead 在最终证据中记录，不新建性能框架。

后续追加仅限新实现或实际失败揭示的问题。当时固定的最小 Python C Stream 入口审核要求为：budgets 必填，descriptor 转换前限数量/字节，消费每个 batch 时累计检查 rows/batches/input bytes，PyBytes 复制计入 owned peak；沿用现有安全 FFI、pool、GIL 释放、取消监视与 panic 边界。

上述核心补齐在 `efad73aa38d9981157327cc9508cbc8f9a8c3fca` 固定差异中已逐项复核：整数 64-bit 最大值、DECIMAL(65,30) 与时间文本来自既有 scalar 预期；浮点测试按固定规范 bits 独立断言 little-endian buffer，不用新 encoder 生成 oracle；SET 仅引用既有 members；Binary、全 NULL、未知版本及 header/footer small/large 分歧均有直接断言。peak=64 KiB 允许单列 metadata/schema 入口，65,536 行 Int64 batch 随后的增长预约超限。核心补齐范围至此闭合，进入 adapter。

06 `s2b-a-core-final-efad73a38.log` 已独立读取：`gw-dms-06`，`08:42:31Z–08:42:37Z`，起止 HEAD 均为上述 efad 提交，起止 porcelain 输出为空（标签后缺换行但没有 dirty 行），offline/jobs=4 与 Rust 1.97 工具链已记录，fmt 与 core 46/46 通过，`final_exit=0`。**完整文件的实际 SHA256 为 `d4fc7b1bba5b0f9c222e564ee0f2bcf43d7a6b6b20648e4de17e4a073a070fd3`**。日志末尾内嵌的 `352c0c...` 是追加该 hash 行之前的摘要，不能作为完整文件摘要；已通知实施者在 handoff 使用外部最终 hash，保留原日志且不重跑。最终 workspace/adapter/container 已由 §7 的候选证据闭合。

06 初轮记录已通过 SSH 只读核对：`gw-dms-06`，2026-11-06 `08:08:46Z–08:09:08Z`，起止 HEAD 均为 `de2cf0906de8d0243b77a2e0b2982943885564b6`；core 37/37 passed（含实际 future deadline 与并发取消），`cargo_test_exit=0`，格式检查失败使 `final_exit=1`。这不是最终通过证据。原命令在错误目录调用 rustup selector，未触及 compiler/被测对象；原日志保留，修正目录后重做一次。两日志均位于 06 `/home/dev/gdds-test-tmp/logs/`：

| 日志 | SHA256 |
| --- | --- |
| `s2b-a-behavior-de2cf0906.log` | `6b8921249462a9d29511f0bef72889109a19d7f65afd6726726614bbe81ef4e1` |
| `s2b-a-behavior-de2cf0906-retry1.log` | `8990e003b99352e96c7df350de822034b4d9003352dcbfe56bb3e383c3a81532` |

## 4. 容器与依赖判定

`arrow-ipc` 从 core dev dependency 转 production dependency，触发本轮最终候选 backend/worker 的必要离线重建与 native/health 验证。版本仍为 Arrow 59.1.0 不能豁免实际生产闭包变化。若锁、features 与 dependency-base 输入不变且缓存已有全部 crate，可复用现有 dependency-base：其 `cargo fetch --locked` 已包含 workspace dev dependencies，不为挪动依赖栏目虚构新 base tag。

adapter 首批实现直接使用 `gateway-shared-kernel::DeclaredType`，新增 workspace 内直接依赖并改变 Cargo.lock。主设计当时允许该依赖并据此执行新 dependency-base 流程；独立审核者也只核了锁触发，漏查现有 architecture-check 的明确禁边。后续 workspace 检查发现这是实际架构违规，详见 §6；不能把该直接依赖描述成最终认可的边界。`lock-994c32446656` 已建并验证的事实保留，但仅为中间产物，最终 base 由修正后完整 input digest 决定，不能默认沿用它。

最终容器状态：**A 所需验证通过**，实际 image/source-tree 与 06 日志见 §7；不是按包 carried，也不替代 S2b 最终 04 权威 runner/container 与 t1–t4 正确性验收。

dependency-base 取证发生两次自身提取脚本错误，审核者已读取原日志并核 SHA：首次 `p6-s2b-a-dependency-base-load-451c315.log`（`efb9452191bb4bc50df7a9c7acc349a80cc610eeacf37f7dd86ba22c87e18830`）在 06 `09:25:26Z` 已成功 load `gateway-backend-deps:lock-994c32446656`，随后对 `tarfile r|` 流随机回 seek 失败；重做 `p6-s2b-a-dependency-base-load-identity-retry-451c315.log`（`df2308bc81efc5607519ebdac76ac035a4c105176f9477a4584b3a1803b701f3`）在 `09:29:23Z–09:29:24Z` 错假设 manifest 必须是首成员，exit 1。实施者停止第三次盲试；这两次不构成身份验证通过，也不改写为成功记录。

停止后的只读诊断确认 CT201 来源归档有 46 个成员，以 `blobs/` 目录开头；`manifest.json` 实际存在且只有一个 image，Config 引用 `blobs/sha256/8085d8d981cad1c9b0aaba2ad1d1b75ee4eaddddbd032ad334e488dc3d2affde`。审核者独立读取该 config 原始 bytes 的 SHA256 及全部 19 项 DiffID，与来源 `archive-identity.json` 一致。归档摘要记录为 `e93021c49acfc11631fd4f76e535985be0b4fce1fcb2a0557d373b82bb6b9f7a`；这不是目标节点身份验证结果。

具体最小修正复用 [dependency-base builder](../../../../../vnext/scripts/build-backend-dependency-base.sh) 已有文件 `tarfile.open(path, mode="r:*")` → `manifest.json` → manifest.Config 的读取路径：06 先 `docker image save --output` 到新的外置临时目录，再比较原始 config SHA、完整 DiffID 与来源记录及本机 inspect 的 RootFS list。全绝对路径、`set -euo pipefail`、不依赖 tar 顺序、不使用本机 inspect ID 作跨机 config digest、不 reload/retag。已审临时脚本 SHA 为 `138eade578d3f9e06e3b3cc1b7f62a16cc04c64f64095eafa62c6b598738a972`；中途曾提出直接 inline 复用 helper 的备选且也获技术复审，但未执行。为避免执行方案漂移，主设计最终固定复建并核对同 SHA 的原脚本作为唯一实际执行来源，不再切换 inline。

主设计依据其核实的既有 Owner DC80/本会话小明确问题授权，已明确给出上述**仅单步身份提取**的恢复 GO；不是默认第三试，也不增加 Owner 审批。恢复条件是保留两失败与新日志/实际命令/exit，身份不符或再次提取失败即停止。固定 SHA 脚本已独立审核，审核者未在 06 执行第三次操作；后续实际恢复结果如下。

授权后 `p6-s2b-a-dependency-base-load-identity-authorized-451c315.log` 已独立读取并复算 SHA256 `5721e09a7c637f46ecce66158e2ff627b38c2d1045b99ba9431ae0ec833e4b3f`：06 clean `451c315bf2`，`09:36:17Z–09:36:36Z`，实际脚本 SHA 与固定 `138eade...` 相符，save/inspect/verify/final 均 exit 0。审核者另将日志实际身份 JSON 与 CT201 source record 程序比较：config digest `sha256:8085d8d981cad1c9b0aaba2ad1d1b75ee4eaddddbd032ad334e488dc3d2affde`、全部 19 项同序 DiffID 及 tag 均一致。此停止点已闭合，可继续原授权范围的当前产品镜像验证；两次失败不被抹去或并为成功。

架构修正删除 direct dependency 后，实施者报告最终 dependency input 恢复为 `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`。来源可复用 [06/07 readiness §7](p6-node-06-07-readiness.md#7-新传输镜像完整身份) 已验证的 `gateway-backend-deps:lock-d054366c02fa`。审核者已重新读取真实原归档 `/home/dev/gdds-p6-artifacts/s2a/gateway-backend-deps-lock-d054366c02fa.tar`，复算完整归档 SHA256 `3fd859201de06757c8ce5af6dd4ad6e26d99b7439bc2edabb59035b5dd0c9ce6`，并按 manifest 引用计算原始 config digest `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a`；全部 19 项 DiffID 与 readiness 完整列表逐项同序相等。这一来源不依赖对 CT201 或 06 inspect ID 存储语义的猜测。最终完整 input 输出和 06 当前目标身份随后独立核对如下。

06 d054 目标身份日志 `p6-s2b-a-dependency-base-existing-d054-identity-retry-db7767.log` 已独立读取并核 SHA256 `c0e93bf597c504b2b99548aa15872ae7a008b8b6d74f1bb2faf3e5d4f793492c`：clean db776、`09:56:29Z–09:56:46Z`，固定 138eade 脚本、save/inspect/verify/final exit 0，b5b542 config 与全部 19 DiffID、tag 一致。source identity JSON 的 SHA256 `c1d692c43760e4b56cda70d9a2c7d692c15c5a0c30ae0005dbe31291a6973245` 与 CT201 文件一致，内容与上述原归档相符。此前 `p6-s2b-a-dependency-base-existing-d054-identity-06.log`（SHA256 `b0feee0807ad9218e91be65a8c3d75f5ff2e77ef55a56f2e4865e3be5fad49bd`）在 `09:54:11Z` 因 451c worktree 有未提交格式/修订而预检 exit 2，尚未调用 Docker，失败保留；同步已提交 clean db776 后才执行身份复核。目标身份已闭合，最终完整 input 的原始重算输出核验见下一段。

完整 input 原始重算输出随后已核：CT201 `p6-s2b-a-dependency-base-input-db7767.log`，SHA256 `d858f34e811b60cec8f5c2a772a4284b817421e5e08efd368b2fc32e4f980ce3`，clean db776、`09:50:29Z–09:50:37Z`，实际调用 `build-backend-dependency-base.sh --print-input`；输出 JSON `inputs-db7767.json` 的 SHA256 为 `f7df461e1f4b3f3fd45a9fbfb014942fa3dd0d017cc0a95e2e93ffcf4d7eac44`。审核者另独立重算 tag_inputs 规范 JSON 的 SHA，得到上述完整 d054 digest；按 db776 的五个 Git blob 重算所有输入文件 SHA，也全部匹配。最终复用 d054 的完整输入与实际目标镜像身份均已闭合，994c 只保留为中间产物。

## 5. Adapter 复审

首批实现沿 safe `pyo3-arrow` C Stream reader、现有共享 pool、取消监视与 `adapter_boundary` 接线；core 调用位于 `Python::detach`，逐 batch 检查 rows/batches/input bytes，adapter 保留的描述与 batch metadata 从 core peak 额度中扣除，返回后先丢 batches/descriptors，再按 Rust Vec capacity + Python bytes 长度预约复制峰值。固定提交和实际 release 行为后续核对如下。

早审发现 `logical_type` 与 declared_type `kind` 未纳入 descriptor preflight，却先通过 `required_python_string` 无上限复制，超大无效枚举字符串可绕 descriptor/peak 检查后才拒绝。已交实施者在转换前限定这些有限枚举并借用匹配；Python Unicode 转 UTF8 的潜在临时分配也须先按字符数作边界检查。新增 backend metadata oracle 再次把 bits 放在 bit_width 前，已依据既定 JCS 顺序指出，不等待 actual 反向修正。两项随后经固定差异复审闭合。

`9400fcfe42`/`25fab48ff1` 及修正 `7d2d87eb6e908116fc6b4019db473d7e640d092c` 已在 detached worktree 复审：有限枚举先限字符数；描述 UTF8 转换前按 4×codepoint + NUL 预约 cache 与 Rust 描述空间，之后才检查准确字节并复制，实际 Vec/String capacity 也计入同时驻留；metadata 阶段前后有取消/deadline 检查。上述预算问题和 JCS oracle 问题已修。batch-cap 用例改为第三次拉取即失败的 iterator，必须在第二批超限时返回 MemoryError，能区分逐 batch 停止与先 collect 后拒绝。

06 `s2b-a-adapter-check-7d2d87e.log` 已独立核对：`gw-dms-06`，`09:12:54Z–09:12:55Z`，起止 HEAD 均为上述 7d2 提交，porcelain 为空，fmt 与 `gateway-compute-python` cargo check 通过，`final_exit=0`；外部 SHA256 为 `f845fe72a4555a4834659bcf681a155c1b075e3ec28459badeeec492b5c690d7`。首次 25fab 编译因 PyO3 0.29 字符长度 API 返回 PyResult 而失败，实施者保留失败日志后以 `?` 修正；本次是编译复验，仍不能替代 release 安装、Python 行为和最终容器结果。

同提交的 06 Python focused 日志 `s2b-a-python-adapter-focused-7d2d87e.log` 已独立读取并核 SHA256 `efc95e6e39ebbffcc14599d0927ca6b2f67c77bae90ebe58892eb21683bb1c50`：`09:20:14Z–09:20:17Z`，起止 HEAD 一致、porcelain 为空，7 passed / 1 failed、pytest exit 1。失败仅为 Python 固定 expected 多放了 `nullable`，数据与 schema roundtrip 的前置断言已通过。审核者早审指出 JCS 键序时漏掉此额外键，此处如实记录为实际运行发现的 oracle 错误。独立修正依据是映射 v1 明文规定四键，nullability 仅由 Arrow Field 表达；应删 expected 的多余键并在同一用例核 Field.nullable，不改产品 metadata。该中间日志只打印 build-input 环境值；随后另核实际 installed extension 值与 source tree 比较的独立记录。

`451c315bf2fd794fc6deb085e1078bdd5f88f528` 的唯一产品范围变化为上述 oracle 修正及原用例的 Field.nullable 断言，已独立复审。06 `s2b-a-python-adapter-focused-451c315.log`（`09:22:22Z–09:22:23Z`）记录起止同 HEAD、porcelain 为空、8/8 passed、pytest exit 0；实际 extension checker 输出 installed=expected=`be885c80f01b59b2e875941023ab0d7651cd12dc`、exit 0，审核者另以 Git 核实其确为该 HEAD 的 `vnext/rust` tree。完整日志 SHA256 `18402f3908ca2a16bc1110325fd3bd01a4f3990a659c4611f8e9f913579db397` 已外部复算一致。此批覆盖真实 C Stream/标准 PyArrow reader、必填预算、逐 batch 停止、输入 bytes、初始控制及 GIL 释放后的取消；最终 workspace/native golden/static/container 证据另见 §7。

## 6. Workspace 架构屏障发现的问题

workspace 检查指出 adapter 直接依赖 SharedKernel 违反既有规则。审核者随后独立核实 `gateway-architecture-check/src/lib.rs` 的依赖规则与 source import 规则，且 S2a kickoff/handoff 将此边界交给单一 architecture owner；Rust policy §4 仍要求薄 adapter 和 core 的小型 metadata 输入。前期设计与审核均漏查此明确禁边，不能为通过测试放宽 guard，也不能包装为工具缺陷。

主设计已固定最小修正：移除 adapter 的直接依赖/import，不使用裸类型 re-export 绕过目的；把 kind/四个可选数值槽到 `DeclaredType` 的构造及一致性校验移入 core 的窄 setter/factory，adapter 只作有界 Python metadata 提取并调用 core。复用既有类型/错误，不新增业务算法或通用 DTO 框架。guard 保持不变；最终锁文件与 dependency-base 按完整实际输入重新核对，若原 base 输入和身份精确一致可复用。固定差异及修复后的最终 workspace/扩展证据如下。

`db7767ffbb5e4eee269b3c0e4778351dd98a092a` 已在 detached worktree 复审：`set_declared_type_from_parts` 位于 core canonical_ipc，保留原 SharedKernel 构造/validate 和 metadata 槽比较，只在成功后修改 descriptor；adapter 只提取有界字段后调用该 setter，None 路径仍不设置 scalar 声明。两个私有 context 聚合原有参数，其余 clippy 修订为 lifetime/contains/is_empty 的语义等价改写。审核者核 `d240b1e599..db7767ffbb` 的 architecture-check 目录没有差异，Cargo.lock 与起点恢复为同一 Git blob `3c502f334fdd0034aae901e8bbae636067f47b60`。代码层问题已修，最终 workspace 与新 Rust tree 的扩展/镜像证据已在 §7 闭合；中间 451c 的行为结果不能冒充新 tree 的构建身份。

失败原日志 `s2b-a-final-rust-451c315.log` 已独立读取并核 SHA256 `b02b0747da9778f416ef9b7cb4ef1c9c26b417a8d9834652e4b20f0bd54e1e1f`：06 `09:38:03Z–09:40:04Z`，起始 451c/clean，fmt exit 0，clippy 的 11 项警告被 `-D warnings` 拒绝（exit 101），architecture crate 20/21 passed、真实 workspace 禁边失败（test exit 101），release build exit 0，整批 final exit 1。后续 release 成功不抵消前两项失败。

五 Python 包 Ruff/mypy 原日志 `s2b-a-python-static-451c315.log` 已独立读取并核 SHA256 `aa3261756345fbb118524fb088ddedb4139b3fa0050d346b96c2398edc119eaf`：06 `09:40:56Z–09:41:21Z`，起始 451c/clean、UV_OFFLINE=1，shared_kernel/repository_contracts/repository_client/backend/repository_service 共十步全部 exit 0、final exit 0。日志没有结束 HEAD 字段，本报告不虚构该字段；主设计允许后续仅 Rust 修正时直接引用此静态结果，不将其称为按包 carried。最终另在 db776 实际补跑五包静态并记录起止 HEAD，未将此中间结果作为最终来源。

此前 release 扩展同步原日志 `s2b-a-extension-sync-7d2d87e.log` 已独立读取并核 SHA256 `debcef64882b5c4312735394aa58afaaeae68647abf330ef005cb08b8892c544`：06 `09:17:52Z–09:19:09Z`，起止 7d2/porcelain 空，实际重建并安装 gateway-compute-python，sync 与 build-input checker 均 exit 0。仅支持中间 Rust tree `be885c80f01b59b2e875941023ab0d7651cd12dc` 的 451c 行为证据，最终修正 tree 必须刷新扩展并独立核对。

## 7. 最终 db776 验证结论

以下成功日志均已由审核者 SSH 只读获取并外部复算 SHA；开发机没有运行产品测试。最终产品候选为 `db7767ffbb5e4eee269b3c0e4778351dd98a092a`，其 Rust tree 经独立 Git 核对为 `5b222191f4689b0eb0a7c2a1123bb299efb13e9d`。

| 06 日志 | 实际结果 | SHA256 |
| --- | --- | --- |
| `s2b-a-final-rust-db7767.log` | `09:57:51Z–09:59:57Z`；起止 db776/clean；fmt、clippy、workspace tests、release build 与 final 均 exit 0。测试共 169 项：architecture 21+13、core 46、adapter 1、SharedKernel 82+3+3，含原禁边及 lint inheritance；全部成功 | `2dd387cb4f40be5fbb94aabfa85498ec00ebb7b27b8d8884f08c4ffab95ad6dd` |
| `s2b-a-python-static-db7767.log` | `10:00:25Z–10:00:27Z`；起止 db776/clean；五包 Ruff/mypy 十步与 final 均 exit 0；明确 UV_OFFLINE=1 和完整 wrapper 命令 | `57ecd8dd64aa0290a660946af521df2df1c94cd1a61501b641858d034ff74587` |
| `s2b-a-extension-sync-db7767.log` | `10:03:13Z–10:03:24Z`；起止 db776/clean；明确 `--reinstall-package gateway-compute-python` 并实际重建/安装，sync 与 extension import/build-input checker exit 0，installed=expected=上述 5b222 Rust tree | `63c177e6f22f04d73e478cc069b3d6373e14bf5a10ae439cb8351f1540eb9acb` |
| `s2b-a-python-adapter-focused-db7767.log` | `10:03:52Z–10:03:53Z`；起止 db776/clean；再次核 installed build-input 相等，完整 `test_table_access_rust_adapter.py` 8/8 passed、pytest exit 0 | `49d3bb268ec9129cdf37af48644b7cde707d219d7c153391b54af2a10d272284` |
| `s2b-a-container-smoke-db7767.log` | `10:23:23Z–10:24:18Z`；起止 db776/clean；既有真实 readiness/正常停止单例 1 passed；backend/worker 本机构建，native 对同一实际 health image 成功调用 codec；清理自己的项目/占用，final exit 0 | `e73a1acff0f9cb936de50bd6d4e8d5b05fd87929cd5f9751395cb243a1bbf6bf` |
| `artifacts/s2b-a-db7767/compose-provenance.json` | 同一 06 外置证据；health backend container 的实际 image ID 与后续 native 固定 ID 相同，另含 RS 实际 image 和 source/build-input labels | `170566393b6e16d962573b0b8aec385676385a0fec0698a25d07c0fd0a261e69` |

Rust 日志记录各 step 与结果但未打印完整 cargo 命令；实施者从该次实际调用记录提供：`cargo fmt --all --check`、`cargo clippy --workspace --locked --offline --all-targets -- -D warnings`、`cargo test --workspace --locked --offline -- --test-threads=1`、`cargo build --workspace --release --locked --offline`。命令清单来源与日志结果区分记录，不伪称日志本身包含命令，也不为打印格式重复整轮。审核者直接核四个 workspace member 均继承 `[lints] workspace = true`。A 的相关 native golden 由 core 独立 buffer/metadata/全类型固定向量与 installed C Stream 的标准 PyArrow reader、独立 metadata/value 预期共同覆盖，至此关闭，不另加旧 kernel 或完整 parser/真实旅程矩阵。current-image codec 与实际 bytes 已由本节容器记录闭合。

扩展刷新前另有 `10:02:17Z` shell quoting 错误说明 `s2b-a-extension-sync-shell-parse-fail-db7767.log`，SHA256 `9854efddd98f57b5c3eda0e97ba6425f9e0253fb5ed6f1a9bcaf7f0f3f53be0c` 已核。记录包含远程 bash exit 2 的原错误输出及实施者“命令体尚未执行”的分类；去掉重复的单独 import 命令后重做，成功同步/checker 日志另列，失败不改判通过。

最终容器 wrapper SHA256 `126c4c2daadce7da5629184715aa2be55cddfc70c4fa5bb411c5680b37a9f11f`、native 输入脚本 SHA256 `8bb7824df9c338ba2f69824b6f3d97352d6aa14f5c74606532e575c85f246918` 在执行前已独立审核。只调用既有 `test_backend_container_ready_and_stops_cleanly_with_repository_service`，没有完整业务旅程；worker 用同候选 Compose 本机构建。健康用例运行的 backend、新构建 backend 与实际 native 容器均绑定同一 image ID `sha256:88665d846710bd26891acbba7fbcb516e57cfaf95edd3314af457e4a48d5b6a0`；worker image ID `sha256:452decd04cbdf87b2a604b6e6802448ae041bc6c243b59dcf812d514b88c7eac`。这些是同节点实际镜像绑定，不是跨节点 config digest。

backend/worker 使用已验证 d054 base、预置依赖开关与 build network none，未设置 prebuilt gate。为现有 health harness 的精确源码身份，RS 使用唯一新 tag，从本机 `gateway-p2r1-repository:lock-6dc9659f0aee` 构建；日志验证其 lock label，provenance 中 RS build-input 为 `3b037adf4caf33f65e124a34f56f12f42e529641`、source tree 为 `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`。没有借用 CT108 镜像或证据。原 Dockerfile 没有传入扩展 `GATEWAY_RUST_BUILD_INPUT`，容器实际输出为空串；本轮如实记录，以固定 clean db776 的实际构建和运行 image provenance 绑定，不新增 Dockerfile 印章机制，也不冒称容器字段匹配 Git tree。

固定 native 输入为 nullable Int64 `[7, NULL, -1]`：输入 Arrow buffers `[1,24]` 共 **25 bytes**，规范 IPC file **1,314 bytes**，相减余量 **1,289 bytes**（包含 schema/metadata/framing/alignment/footer 等，不是纯 value payload）。输出 SHA256 为 `974bb1c6317b3820c55e0388e575ee7cd7d671cab814ce7e7e0442addca5a094`；标准 PyArrow reader 的值、nullable 与四键 JCS 预期均实际断言通过。这只是 A 小向量的局部 bytes 记录，不宣称完整 FULL、worker RSS、生产 M、W2 或性能目标通过。

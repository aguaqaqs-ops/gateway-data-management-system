# S2b 容量输入小样本普查

状态：已完成的设计输入，仅描述现有 parser 的 Arrow C Stream buffers；不代表规范 IPC、生产峰值 RAM、M 或容量 PASS。S2b 产品实现尚未获 kickoff 授权。

普查依据 [DC84](p6-s0-owner-decisions.md)、[S2b kickoff](p6-s2b-kickoff.md) 与 [映射候选](p6-s2b-arrow-mapping-design.md)。源码候选为 `d368413861dbcce10691fb65e8dbaba2a208af68`，S2a 退出源码仍为 `p6-s2a-exit^{commit}=53b676a6298d408ccda3a85ee73c7ea223a2311a`。有界普查原始工具提交 `583b69c838533a28cdc30d9aeb6c36ab30270cf2`，脚本 SHA256 `b5c08a8a4f9ab98a980f08571f0995f08a2b243fa8fe6a8335c055026bca740b`；后续 `f5dafdfce86b48b412b87b02671f798d73c2c0f3` 只增加计数类型缩窄，不改变输入或统计语义，最终文件 SHA256 `ae8b0bce9d24950cda513e9c7c3e9758fa026e3138672e5ad05c446adfbf5287`。

## 范围与口径

在 06 `gw-dms-06` 的 clean、已提交 worktree 中，源码以获准 LAN bundle 到达；后端依赖使用 06 已预填充缓存，`UV_OFFLINE=1`/`CARGO_NET_OFFLINE=true`，没有转发代理或下载。工具分别读取一个既有 t1 SQL 输入和一个已跟踪的两行类型 fixture，调用现有 S2a Rust parser（N=1），将其现有 Arrow C Stream 读入 PyArrow。固定来源的读取有字节/成员数上限，SQL SHA256 在调用 parser 前核对。没有运行完整旅程、生成或扩展输入、Dolt、Compose、规模测试或新 IPC writer；工具不输出原始行值。

| 口径 | 本次可以报告什么 |
| --- | --- |
| 实测 | 输入 SQL bytes、解析后的表/行/列/单元格数、PyArrow logical nbytes、每表 `get_total_buffer_size()`、按列累计的 buffer reference spans；均是现有 parser 的输出 |
| 推导 | 映射后仍须根据声明和已投影行计算列 buffers：fixed-width 值 bytes 加 validity；small/large variable-width offsets 加 payload；逐 record batch 的对齐、schema/footer 和临时复制需在 writer 落地后校准 |
| 未知 | 规范投影删列/增伪 gid 或 composite 的具体输出、排序与转换临时副本、真实 IPC file bytes、映射与 writer 同时存活的峰值、worker RSS、生产大表/并发/TTL 分布及部署内存上限 |

`logical_nbytes` 是数组逻辑跨度；`get_total_buffer_size()` 反映每张表引用的底层 buffer spans。报告的 t1 “每表 unique buffer 总和”是逐表数值求和，不是跨所有表的指针级全局去重，因此可能重复计入跨表共享的底层 buffer。它不是分配器 capacity，也不等于 RSS、内存页驻留或 IPC 文件大小。

## 两份输入的测量值

| 输入 | 输入摘要 | 解析规模 | logical nbytes | 每表 unique buffer 字节求和 |
| --- | --- | ---: | ---: | ---: |
| 既有 `rd-t1-a-v1` SQL | SQL 1,296,177 B；SHA256 `f8da5b9608981f91ba4cef66e593a6e2299386871d53af71ba203802140748f5` | 132 表、6,093 行、151,751 单元格 | 1,405,885 B | 1,409,489 B |
| 跟踪的 `s2-null-and-types` fixture | 180 B；SHA256 `6a6d00571cb7d5a631a17b9a1f554f38c43854bf9eac869228ba0ed47f94d0f6` | 1 表、2 行、4 列、8 单元格 | 37 B | 45 B |

t1 的分布边界为最大单表 1,678 行、最大单表 buffers 480,621 B、最大单列 buffer reference span 42,105 B。三个最大值分别统计，不能推断它们属于同一表或列。两行 fixture 的 45 B 与独立手算一致：INT64 16 B、两个 UTF8 列各 14 B、Boolean 1 B；37 B 与 45 B 分别是 PyArrow logical 与实际 buffer 口径，不应混用。

两份输入都由现有 parser 完整解析，`gateway-compute-python` 已安装扩展的 `__build_input__` 与 Rust tree `61a76caa0e789aef1eea53a8c98d4c4c3cbb2af4` 一致。工具没有创建规范 IPC 文件，也没有测量 RSS。

## 保守公式与容量边界

映射/IPC 实现候选的原始 buffer 字节按实际映射后每批行数 `n` 和该批 payload 计算，再逐列/批相加，而非按 SQL 文件大小乘常数：

```text
validity_bytes = ceil(n / 8)                    # all v1 field types, nullable or not
fixed_width_column = width_bytes * n + validity_bytes
boolean_column = ceil(n / 8) + validity_bytes   # values and validity are separate bitmaps
small_utf8_or_binary_column = 4 * (n + 1) + payload_bytes + validity_bytes
large_utf8_or_binary_column = 8 * (n + 1) + payload_bytes + validity_bytes
```

公式适用于映射 v1 支持的类型；fixed-width 项不含 Boolean。标准 Arrow 59.1 writer 对这些 field 都写 validity bitmap；无 NULL 时采用其全 `0xff` 输出（含末 byte 未用位），含 NULL 时由规范数组构造保证末 byte 未用位为 0。空表的 file profile 为 0 个 batch，只有 schema/footer，不把空数组的 offsets 重复计为已写 batch。以上公式不含 IPC schema/footer、64-byte 对齐 padding、record-batch framing、排序索引、转换副本或 Python/Rust 边界复制，因此不是 IPC 或 M 上界。映射后的列集合、伪列/composite 以及 batch 数据必须由真实 kernel/writer 输出校准，不能把 parser 原始 buffer 当 canonical 上界。

因此本次不填 M 数值，不从约 100 MB SQL 输入猜 GiB，也不宣称生产容量可通过。M 至少要覆盖实际同时存活的 SourcePackage/解析输入、当前 parser buffers、规范转换与排序临时量、IPC 输出及 `Vec → PyBytes` 复制；FULL 的两侧、当前 operation 打开的 baseline/Attempt mmap 读句柄和 publish 前 staging 按真实生命周期分别计入。对本 operation pin/read 的 mmap 文件与 Arrow views，按 handle 生命周期保守预约被引用 bytes，共享 mapping 只计一次；未被本 operation 读取的全局文件只占磁盘，不算本次 M，不能把所有历史文件误算为 RAM。

## DC84 分阶段闭合

1. **当前输入阶段（完成）**：固定的 t1 与小类型 fixture 给出既有 parser 实测单位输入和公式；结果只支持这些输入与 parser，不推生产 M、大表或完整 FULL。
2. **A：mapping/codec**：单一 Rust in-memory canonical IPC codec 与纯值映射、profile bytes vectors；不接 ArtifactStore/worker。实际 codec bytes 校准固定 metadata、batch/alignment 开销与 deterministic output。
3. **B：业务 kernel**：将实际物化、projection、过滤与业务摘要接到 A 的唯一 codec；记录 canonical 输出列行数、payload、buffers 和转换/排序数组的峰值重叠。
4. **C：store/ref/recovery**：用 A 的唯一 codec 接入 mmap/store/引用恢复；测实际业务 IPC bytes 与 FULL 两侧/临时重叠。B/C 校准复用既有较大样本，并核少数大表分布；代表性不足时才协调额外样本，不现在生成大输入。worker 接线前据此确定每 operation M 的 bytes、默认/上界、准入/增长拒绝和 worker memory envelope/reserve，关闭 DC84 的 M 前置循环依赖。
5. **接线后复核**：实际 Preview/History worker 运行中复核进程峰值与预约差异；这是最终实现校准，不要求在 IPC 与 FULL measurement 尚不存在时伪称其为实测，也不重开 M 的前置循环依赖。

当前缺口具体是：新 IPC 尚未实现，因此真实 canonical bytes 和 writer 高水位不存在；现有部署配置也没有已确认可作为 M 上限来源的 worker memory envelope。前两项必须先在 S2b 的 mapping/IPC 阶段产生，后者须在 worker 接线前由容量测量和部署资源边界共同给出。它不阻止 owner 批准首个纯 mapping/kernel 切片，但不允许提前接入一个猜测的 M。

## 可复核记录

所有运行位于 06，输入/tool/output JSON 与 worktree 外日志按 SHA256 留存；本次单机占用于 2026-11-06T06:02:50Z–06:14:39Z，已释放。完整 JSON 输出只含匿名表/列索引、类型和计数，不含行值。以下时刻均为 2026-11-06 UTC。

| 记录 | 时段 / HEAD | 结果 | 日志与 SHA256 |
| --- | --- | --- | --- |
| t1-v1 原 parser buffers | 06:05:51–06:05:52Z，`a3f49290628caf5c1cb626bac6cc7b26cb2c5f00` | exit 0 | `/home/dev/gdds-test-tmp/p6-s2b-capacity-census-583b/t1-v1-census.log`，`26ce38f1b079acb89c8b30b37b230764859d7590ee81d881ad5819e0c7dc3f13` |
| types fixture 原 parser buffers | 06:06:12–06:06:13Z，同上 | exit 0 | `/home/dev/gdds-test-tmp/p6-s2b-capacity-census-583b/types-fixture-census.log`，`8fae4260335301f007549e98ece8762fb4bd7c77ea3c3008237bcc74b257acf6` |
| 扩展 build input | 06:05:30–06:05:31Z，同上 | installed/expected Rust tree 相同，exit 0 | `/home/dev/gdds-test-tmp/p6-s2b-capacity-census-583b/extension-build-input.log`，`71eb0e20532a08a5c09c0d55e2fe2a8dc55f5caa233239dda15989ac5dabfd12` |
| 五个 Python 包 Ruff/mypy 加工具单独 mypy | 06:07:33–06:07:58Z，同上 | 五包 Ruff/mypy 全部 exit 0；工具单独 mypy 发现 4 处动态计数类型错误。仅增加整数类型缩窄 helper，不改统计计算；样本不重跑，修复经只读审核确认 | `/home/dev/gdds-test-tmp/p6-s2b-capacity-census-583b/python-static-checks.log`，`a62739ff431268bcc9dc0aade828e4fd67530da06c05cc8bffc9965f8864ed93` |
| 工具修复静态复核 | 06:13:48Z，`d368413861dbcce10691fb65e8dbaba2a208af68` | clean WT；tool Ruff=0、显式 mypy=0、wrapper `bash -n`=0；起止 HEAD 相同 | `/home/dev/gdds-test-tmp/p6-s2b-capacity-census-583b/tool-fix-static-checks.log`，`b86851471ac438ad447fa8f62c39a9e9f08fccb87315466aa568f966bd0b4006` |
| 释放与清理 | 06:14:39Z，同上 | 仅删除本任务 Cargo target，释放本任务占用；保留 clean detached worktree 与日志 | `/home/dev/gdds-test-tmp/p6-s2b-capacity-census-583b/node-release.log`，`d5d467202bbe1f4af3c411567826ed06f9832070c9dc8b20247c8715b844a640` |

审核者独立复核了两个输出 JSON、输入与日志 SHA、扩展 build-input 身份以及 37/45 B fixture 手算；并确认类型缩窄未改变两份样本结果。容量结论只按本报告所列范围使用。

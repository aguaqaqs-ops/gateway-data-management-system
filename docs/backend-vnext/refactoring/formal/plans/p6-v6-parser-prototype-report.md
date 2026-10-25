# Phase 6 前置验证 V6：SQL 解析器 Rust 原型

## 结论

- **一致性：通过。** 第 ① 层子集与合成字面量 118 例、第 ④ 层 t1–t4 的 v1 与 v2 共 8 份真实数据（1,733 张表、1,612,822 行、33,895,148 个值）与参照实现逐值对照，差异为 0；诊断码、字节偏移与表全部相同。testdata1 与 t3 是同一份 SQL。唯一不同的是 1 个合成用例中的 FLOAT 值：参照实现两次舍入，与 Shared Canonical Encoding Contract 不符，Rust 按 Contract 实现，登记为待澄清语义。
- **并行确定：通过。** 1 到 32 线程、1 字节到 1 MiB 的块大小，输出逐字节相同。
- **吞吐：达标。** 参考节点 `ct108-gw-dms` 上独占测量，2× t4（158.7 MB）单线程解析 1.250 s，32 线程 0.277 s，远低于 10 s 的门槛；单线程约 121 MiB/s，任何线程数都达标。峰值内存 569–753 MiB（输入的 3.8–5.0 倍）。调试节点 05 的初步数字与之相差 5% 以内。
- **主要发现：** 参照实现有 9 处行为与 Contract 或 MySQL 不一致，其中 BIT 与深层 JSON 会抛出未捕获的异常，需在 S1b 定稿；顺序扫描占单线程时间约 14%，限制了加速比，但目标余量很大，S2a 不必优化。

## 范围与实现

### 范围

- 实现了扫描（语句与表边界；单引号、反引号、反斜杠转义、`--`/`#`/`/* */` 注释、条件注释 `/*!NNNNN ... */`、CRLF）与 INSERT 值解析，按表与按块用 Rayon 并行，直接产出 Arrow 列。
- 解析值所需的列声明类型来自 CREATE TABLE 解析。为让第 ① 层语料与真实数据可以逐值、逐诊断对照，CREATE TABLE、INSERT 头与 mysqldump 样板语句（`SET`、`LOCK/UNLOCK TABLES`、`DROP TABLE IF EXISTS`、条件注释中的 `ALTER TABLE ... DISABLE/ENABLE KEYS`）按参照实现的允许清单移植，类型映射移植 `map_sql_type` 全部规则。
- 不在本任务内、留给 S2a：完整诊断（每张表的全部诊断、消息文本）、预算偏移量的精确语义（行预算按块粒度报告）、PyO3 adapter 与 Arrow C Stream 交接、取消与截止时间的接口定稿。遇到不支持的输入时以诊断稳定失败；公开入口用 `catch_unwind` 兜底，panic 转为 `PARSER_INTERNAL_ERROR`（测试中未出现）。
- 未修改参照实现、Phase 6 讨论稿、决议记录、implementation-stages、AGENTS 与 testing-conventions；旧扩展未动（DC52）。

### 模块结构

新增 `vnext/rust/gateway-compute-core/src/table_access/`（DC47 的 core crate 内按 capability 分模块；core 不读写文件，只接收字节）：

| 文件 | 内容 |
| --- | --- |
| `mod.rs` | 公开入口 `parse_sql_dump(sql, options, pool)`、`build_parser_pool(threads)`（1..=256，固定大小、由调用方持有）、预算（默认值同 Python `RESOURCE_BUDGETS`）、两阶段编排与合并 |
| `scan.rs`、`cursor.rs` | 阶段 A：顺序扫描语句边界（memchr），同时记录 INSERT 中顶层元组之间的分割点（间距 ≥ `chunk_bytes`） |
| `statements.rs`、`types.rs` | CREATE TABLE、INSERT 头、样板语句允许清单；SQL 类型映射 |
| `literal.rs`、`convert.rs`、`json_check.rs` | 字面量词法；按声明类型转换为类型化值（整数、浮点有快速路径，其余与快速路径的交叉校验都走 Shared Kernel `normalize_logical_literal`）；JSON 合法性按 Python `json.loads` 的接受范围（迭代实现，无递归） |
| `values.rs`、`columns.rs` | 阶段 B：每块独立解析元组并写入列构建器；按源顺序拼接为 Arrow 数组 |
| `canonical.rs` | 解析结果规范形编码（仅测试与测量使用） |
| `tests.rs` 等 | 单元测试与 proptest（共 22 项） |

两阶段：阶段 A 顺序扫描全文，得到语句、表描述与分块计划；阶段 B 在固定大小的 Rayon 池中并行解析所有块（块是一段完整元组，来自任意表），每块记录首个表级错误与文档级错误及其偏移；合并时按偏移取最早的错误，复现参照实现顺序执行的结果，再按表并行生成 Arrow 数组。输出与线程数、分块大小无关。

测试与测量入口（不进入生产）：

- `gateway-compute-core/examples/table_access_parse.rs`：读 SQL 文件，按给定线程数与分块大小解析，只计时解析本身，输出 JSON 摘要（表名、行数、诊断码与偏移、规范形 SHA-256、`VmHWM`），可选写出规范形；不输出值。
- `vnext/backend/benchmarks/p6_v6_parser_diff.py`：参照实现输出转为同一规范形；逐表、逐列、逐值比较，报告第一个差异的表、列、行与两侧类型标记；`corpus` 与 `real` 子命令。
- `vnext/backend/benchmarks/p6_v6_measure_inputs.py`：只用标准库，取 SQL、生成 2× t4、跑吞吐与确定性测量。

### 新增依赖

| crate | 版本 | 用途 | 影响 |
| --- | --- | --- | --- |
| `rayon` | `=1.12.0` | 固定大小线程池与并行迭代（DC47 第 8 条） | 新增 `rayon-core 1.13.0`、`crossbeam-deque/epoch/utils`、`either`；纯 safe API 使用 |
| `memchr` | `=2.8.3` | 扫描与引号内查找 | 已在 lock 中（arrow 间接依赖），本次只改为直接依赖 |
| `proptest` | `=1.11.0`，`default-features = false, features = ["std"]` | 仅 dev-dependency：不崩溃与资源上界的属性测试 | 新增 `rand 0.9.5`、`rand_chacha`、`rand_core`、`rand_xorshift`、`ppv-lite86`、`regex-syntax`、`unarray`；不进入生产构建；固定种子、关闭失败持久化，不写 worktree |

`Cargo.lock` 新增 14 个包。runner 的 `rust` 包以 `--offline` 运行，因此在三台节点的分支 worktree 中各执行一次 `cargo fetch --locked`（2026-10-25，`ct108-gw-dms-04` 09:58:50Z、`ct108-gw-dms` 09:59:01Z、`ct108-gw-dms-05` 随后，均 exit 0），之后 `cargo metadata --locked --offline` 在三台节点上都成功。

## 规范形

按讨论稿 §6.3 定义“解析结果规范形”，格式名 `gateway.table-access.parse-canonical`，版本 1，两侧逐字节相同即判定一致（`canonical.rs` 文件头有完整布局）：

- 魔数 `GDMSPCF1`；文档头 JSON（`format`、`status`、`table_count`、`version`）。
- 每张表按源顺序：表 JSON（`canonical_name`、`display_name`、`columns`、`primary_key`、`reader_ready`、`row_count`；不可读的表 `row_count` 为 `null`、不输出值）。列 JSON 含 `ordinal`、两种名称、`sql_type`、`logical_type`、`nullable`、`labels`（ENUM/SET）与 `declared_type`（kind 加位宽、精度、标度、BIT 宽度）。JSON 键排序、无空白，与 Python `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 相同。
- 可读的表按列输出：`C` + 列序号，随后逐行 `类型标记 u8 + 长度 u32 + 载荷`。载荷就是 Shared Kernel 的规范标量载荷（`encode_typed_scalar`）：整数 8 字节、浮点 IEEE 位、文本 UTF-8、二进制原样、BIT 按声明宽度补齐的字节；SET 为按声明顺序以 `,` 连接的成员（标签不允许含 `,`，无歧义）。
- 类型标记：null `0x00`、boolean `0x01`、signed `0x10`、unsigned `0x11`、decimal `0x12`、float32 `0x13`、float64 `0x14`、string `0x20`（含 ENUM、JSON）、binary `0x21`、bit `0x22`、date `0x30`、datetime `0x31`、timestamp `0x32`、time-duration `0x33`、set `0x40`。

取舍：

- ENUM、JSON 与普通字符串共用 `0x20`，靠列 JSON 中的声明类型区分；需要的话可在 S2a 拆标记，不影响本次结论。
- 诊断不进规范形；差分工具另外逐项比较 `(诊断码, byte_offset, 表)`，不比较消息文本（DC46 第 4 条）。
- 规范形表达不了参照实现拒绝的值：零日期、`_binary` 前缀、BIT 负数等在参照实现中整表或整份文档失败，规范形里只有“不可读”。若 S1b 的 Contract 改为接受零日期，规范形需增加对应标记（例如零时间值单独一类），版本号加一。
- 规范形是测试工具，不是存储格式，与 Arrow 物理类型无关；表摘要仍按规范标量编码计算（DC46 第 6 条）。

## 一致性（差分）

判定：两侧规范形逐字节相同，即每张表的描述、行数与逐值的类型标记和载荷都相同；另外逐项比较诊断的 `(诊断码, byte_offset, 表)`（DC46 第 4 条：诊断码、表与语句位置相同，消息不比）。所有运行都在 clean 提交 `ee516edb69` 上，节点 `ct108-gw-dms-05`。

### 第 ① 层子集与合成字面量（118 例）

| 来源 | 例数 |
| --- | ---: |
| golden `vnext/fixtures/golden/table-access/sql/`（valid 2、malformed 2） | 4 |
| `test_table_access_sql_parser.py`：mysqldump `SET` 形态 22、INSERT 列序置换 1 | 23 |
| `test_table_access_sql_rejects.py`：语句拒绝 9、类型拒绝 7、值非法 4 | 20 |
| `test_table_access_sql_reader.py` 的 SQL 与其他测试中的错误用例（重复表、标识符碰撞、重复主键、行宽不符、PARTIAL、未知类型） | 7 |
| 合成字面量类（讨论稿 §6.2 全部类别） | 64 |

合成类覆盖：转义（`\0 \' \" \b \n \r \t \Z \\ \% \_`、未知转义 `\a` 与 `''`）、多字节与 4 字节 UTF-8、非字符码位、引号内换行与 CRLF（§12 登记的“一次性统计脚本漏计多行 INSERT”）、`x'..'`/`0x..` 与奇数长度、`b'..'`/`0b..` 与 BIT 各种写法、整数边界与 `-0`、浮点负零与指数、FLOAT/DOUBLE 溢出、`DECIMAL(65,30)` 大值与 `.5`、零日期与零日期时间、DATETIME/TIMESTAMP/TIME 的小数秒与范围、布尔、ENUM/SET/JSON 的合法与非法值、每种类型的 NULL 与 NOT NULL 违例、各处的注释、条件注释 `/*!40101 ... */` 与行内条件注释拒绝、`LOCK TABLES` 样板、列序置换、反引号与库名限定、`_binary` 拒绝、`DEFAULT`、尾随逗号、空元组、未闭合字符串、双引号字符串、`ON DUPLICATE KEY UPDATE`、未知 INSERT 目标、400 行的分块用例、一张表失败而另一张可读、空文档与只有注释的文档。

结果：60 例 COMPLETE、2 例 PARTIAL、56 例 FAILED（其中 18 例为文档级失败）；1,450 个值逐值相同；**117 例规范形逐字节相同，差异 0**；诊断码、偏移与表全部相同（0 例不一致）。唯一不同的是登记为已知偏差的 `literal:float32-double-rounding`（2 个值，见“需要澄清的语义”第 1 条），这是参照实现与 Contract 不一致，不计为差异。每例 Rust 侧都以 1、4 线程与 1 MiB、16 B、1 B 块各跑一次，输出相同。

日志：`/home/dev/gdds-p6-logs/v6/evidence-corpus-20261025T095831Z.log`，汇总 `/home/dev/gdds-p6-logs/v6/corpus-evidence.json`。

### 第 ④ 层真实数据（t1–t4 全部，v1 与 v2）

| 输入 | 字节 | 表 | 行 | 值 | 差异 | 逐字节相同 | 参照 `parse_sql` s | Rust 1 线程 s | Rust 8 线程 s |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| t1 v1 | 1,296,177 | 132 | 6,093 | 151,751 | 0 | 是 | 2.424 | 0.019 | 0.011 |
| t1 v2 | 1,296,079 | 132 | 6,091 | 151,737 | 0 | 是 | 2.427 | 0.019 | 0.011 |
| t2 v1 | 14,956,886 | 216 | 97,095 | 2,134,693 | 0 | 是 | 31.061 | 0.169 | 0.054 |
| t2 v2 | 14,668,224 | 216 | 93,109 | 2,103,570 | 0 | 是 | 30.418 | 0.165 | 0.053 |
| t3 v1 | 49,323,598 | 199 | 268,460 | 5,922,515 | 0 | 是 | 91.858 | 0.447 | 0.139 |
| t3 v2 | 49,981,672 | 200 | 268,466 | 6,062,168 | 0 | 是 | 93.244 | 0.468 | 0.139 |
| t4 v1 | 79,446,967 | 319 | 436,714 | 8,683,933 | 0 | 是 | 142.061 | 0.707 | 0.207 |
| t4 v2 | 79,269,322 | 319 | 436,794 | 8,684,781 | 0 | 是 | 140.747 | 0.706 | 0.198 |

- 全部为 COMPLETE，所有表可读，两侧都没有诊断。合计 1,733 张表、1,612,822 行、33,895,148 个值，差异 0。
- testdata1 的 `data1`、`data2` 两份 `sql/dbcfg.sql` 与 t3 v1、v2 的 SQL 的 SHA-256 完全相同，t3 的结果即 testdata1 的结果，没有另外复制。
- 计时为同一节点上的单次运行，只作参考；参照 `parse_sql` 的时间与 DC46 记录的 t4 解析 140 s 一致。正式吞吐见下文 ct108 的测量。
- 日志：`/home/dev/gdds-p6-logs/v6/real-evidence.log`；每份输入的汇总与两侧规范形在 `/home/dev/gdds-p6-logs/v6/real/evidence/`（目录 `0700`、文件 `0600`）。汇总只含计数、表名、位置、类型标记、耗时与摘要。

## 并行确定性

- 真实数据：每份输入以 `{1, 8} 线程 × {1 MiB, 64 KiB} 块` 各运行一次，4 个规范形摘要相同（上表 8 份全部）。
- 2× t4：以 `{1, 2, 4, 8, 16, 32} 线程 × {1 MiB, 64 KiB, 4 KiB} 块` 共 18 种配置运行，规范形（237,353,178 字节）摘要全部相同（见吞吐一节）。
- 语料：每例 `{1, 4} 线程 × {1 MiB, 16 B, 1 B} 块`；1 字节块意味着每个元组一块，是最细的切分。
- 单元测试：`output_is_identical_across_threads_and_chunk_sizes` 在 `{1, 2, 4, 8} 线程 × {1, 7, 64, 4096, 1 MiB} 块` 上比较规范形；proptest `dump_shaped_input_is_deterministic` 用随机 dump 片段拼成的输入，比较默认配置与 3 线程、2 字节块的输出。

## 吞吐与内存

输入：2× t4 = t4 v1 加上表名改为 `<原名>__x2` 的 t4 v2，拼接而成（`p6_v6_measure_inputs.py make-2x`，只用于测量）。共 158,723,653 字节（151.4 MiB），SHA-256 `3263196c…0910f4`；改名 1,841 条语句；解析结果为 COMPLETE，638 张表全部可读，873,508 行。

方法：每个线程数单独起一个进程（峰值内存按进程计），块大小 1 MiB，连续解析 4 次，取后 3 次的中位数（DC35：1 + 3 次取中位数）。计时只含 `parse_sql_dump`（UTF-8 校验到 Arrow 数组生成完毕），不含读文件与规范形编码。峰值内存为进程 `VmHWM`，包含整份输入（151 MiB）。

### 正式结果（`ct108-gw-dms`，AMD EPYC 9654，128 vCPU，2026-10-25T13:24:09Z–13:24:47Z）

条件：V5b 结束且其 Compose 栈拆除后独占测量。开始前确认没有 runner、pytest、dolt、Compose 命令、py-spy、cargo 与 rustc 进程，也没有任何运行中的容器，1 分钟负载 0.28。worktree 为 clean 的 `110e5459fd`，起止 HEAD 相同。二进制是 05 上从 clean 提交 `ee516edb69` 构建的 release 版 `table_access_parse`（SHA-256 `186e16f0…72bede`；之后的提交只改了本报告，Rust 源码相同），复制到 ct108 后核对 SHA-256 一致。2× t4 在 ct108 上从 t4 包重新生成，SHA-256 与 05 相同。

| 线程 | 中位数 s | MiB/s | 加速比 | 并行效率 | 校验 s | 扫描 s | 值解析 s | 合并 s | 峰值内存 MiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.250 | 121.1 | 1.00 | 1.00 | 0.044 | 0.125 | 0.962 | 0.117 | 569 |
| 2 | 0.725 | 208.8 | 1.72 | 0.86 | 0.044 | 0.127 | 0.481 | 0.072 | 601 |
| 4 | 0.481 | 314.7 | 2.60 | 0.65 | 0.044 | 0.124 | 0.248 | 0.067 | 628 |
| 8 | 0.358 | 422.9 | 3.49 | 0.44 | 0.044 | 0.129 | 0.125 | 0.056 | 674 |
| 16 | 0.293 | 515.8 | 4.26 | 0.27 | 0.045 | 0.128 | 0.069 | 0.050 | 703 |
| 32 | 0.277 | 546.5 | 4.51 | 0.14 | 0.044 | 0.132 | 0.046 | 0.048 | 753 |

- **单线程吞吐**约 121 MiB/s（127 MB/s），是参照实现（t4 约 0.54 MiB/s）的约 225 倍。
- **2× t4 在任何 N 下都 ≤ 10 s**：单线程 1.250 s 已有约 8 倍余量；目标对应的 16 MiB/s 单线程即可达到。
- **加速曲线**：值解析阶段接近线性（1 → 32 线程为 0.962 → 0.046 s，约 21 倍）；UTF-8 校验与阶段 A 扫描是顺序的，合计约 0.17 s，占单线程时间的约 14%，因此 32 线程时总加速约 4.5 倍后趋平。并行效率 ≥ 60% 的最大 N 为 4（0.65）。
- **峰值内存**为输入的 3.8 倍（1 线程，569 MiB）到 5.0 倍（32 线程，753 MiB）；线程越多，同时存在的块构建器越多。确定性一轮还要生成规范形（237,353,178 字节，约 226 MiB），该进程峰值 1,440 MiB；规范形只在测量与差分中出现。
- **确定性**：`{1, 2, 4, 8, 16, 32} 线程 × {1 MiB, 64 KiB, 4 KiB} 块` 共 18 种配置，规范形 SHA-256 全部为 `17f6a2df…7c68b`，与 05 相同。
- **与先前两次测量对比**：13:18:56Z 在 ct108 上测过一次，当时 V5b 的 Compose 栈（3 个空闲容器，CPU 合计不到 0.5%）尚未拆除；为排除其影响，拆栈后重测，以本次为准。两次各线程数的中位数相差 2% 以内（1 线程 1.249 对 1.250 s，32 线程 0.281 对 0.277 s），确定性摘要相同。05 上的初步数字与本次相差 4% 以内（两台节点 CPU 型号相同）。

日志：`ct108-gw-dms:/home/dev/gdds-p6-logs/v6/measure-ct108-20261025T132409Z.log`（开头记录 hostname、内核、nproc、起始时间、HEAD、二进制 SHA-256、忙碌进程数、容器数与负载，结尾记录结束时间、HEAD 与 exit code 0），汇总 JSON 同名，每个线程数的原始输出在同名目录中。先前一次的日志为同目录的 `measure-ct108-20261025T131856Z.log`。

### 初步结果（`ct108-gw-dms-05`，调试节点，非正式）

V5b 期间先在 05 上用同一个二进制与同一份输入测过一次（AMD EPYC 9654，64 vCPU，2026-10-25T11:12:30Z–11:13:05Z），只作参考：

| 线程 | 中位数 s | MiB/s | 加速比 | 并行效率 | 校验 s | 扫描 s | 值解析 s | 合并 s | 峰值内存 MiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.243 | 121.8 | 1.00 | 1.00 | 0.044 | 0.123 | 0.959 | 0.119 | 570 |
| 2 | 0.719 | 210.5 | 1.73 | 0.86 | 0.043 | 0.128 | 0.482 | 0.064 | 597 |
| 4 | 0.484 | 312.5 | 2.57 | 0.64 | 0.044 | 0.127 | 0.245 | 0.069 | 640 |
| 8 | 0.356 | 425.4 | 3.49 | 0.44 | 0.044 | 0.125 | 0.128 | 0.058 | 685 |
| 16 | 0.282 | 536.2 | 4.40 | 0.28 | 0.044 | 0.126 | 0.069 | 0.045 | 747 |
| 32 | 0.268 | 564.4 | 4.63 | 0.14 | 0.044 | 0.128 | 0.045 | 0.052 | 771 |

18 种配置的规范形摘要同为 `17f6a2df…7c68b`。日志：`ct108-gw-dms-05:/home/dev/gdds-p6-logs/v6/measure-05-20261025T111230Z.log`。

## 需要澄清的语义（参照实现与 Contract 或 MySQL 不一致处）

按任务要求只记录、不修改参照实现。下列行为都用节点上的参照实现实测确认（合成输入，`/home/dev/gdds-p6-logs/v6/` 不保存真实值）；Rust 原型在第 1 条按 Contract 实现，第 3、9 条给出确定的结果而不抛异常，其余与参照实现一致。

| # | 行为 | 参照实现 | Contract / MySQL | Rust 原型 | 建议 |
| --- | --- | --- | --- | --- | --- |
| 1 | FLOAT 列的十进制字面量 | 先 `float()` 到 binary64，再 `struct.pack('>f')` 到 binary32，两次舍入。例如 `1.000000059604644775390626` 得 `3f800000` | Shared Canonical Encoding Contract 要求直接舍入到 binary32，应得 `3f800001` | 按 Contract 直接舍入；语料 `literal:float32-double-rounding` 两个值不同，登记为已知偏差，未计入差异 | S1b 确认以 Contract 为准并修正参照实现；真实数据 t1–t4 中未出现受影响的值（逐值 0 差异） |
| 2 | BIT 列的十进制数字字面量只含 0/1 时 | 按二进制读：`10` 得 `0x02` | MySQL 按十进制读，`10` 应为 `0x0a` | 与参照实现一致（语料 `literal:bit-literals`） | S1b 决定语义；mysqldump 对 BIT 输出 `b'..'`，真实数据不受影响 |
| 3 | BIT 负数、超宽、`b'..'` 含非 ASCII | 未捕获的 `OverflowError` / `UnicodeDecodeError` 越过 `parse_sql` | 应为确定的诊断 | 前两者为 `SQL_VALUE_ILLEGAL`（表级），非 ASCII 为 `MALFORMED_SQL`（文档级） | S2a 前修正参照实现并补 golden；这几类不在差分语料里（Python 侧会抛异常） |
| 4 | `_binary 'abc'` 字符集前缀 | `MALFORMED_SQL`，整份文档失败 | mysqldump 不加 `--hex-blob` 时会为二进制列输出 `_binary` 前缀 | 一致 | 真实数据 t1–t4 未出现；讨论稿 §6.2 把 `_binary` 列为需对齐的类别，S1b 决定是否支持 |
| 5 | 零日期 `0000-00-00`、零日期时间 | `SQL_VALUE_ILLEGAL`，该表不可读 | MySQL 允许；讨论稿 §6.2a 预期保留规范文本 | 一致 | t1–t4 所有表均可读，说明当前真实数据的日期类型列中没有零日期；S1b 决定，规范形与 Arrow 映射随之加类别 |
| 6 | 转义 `\%`、`\_` | 去掉反斜杠，得 `%`、`_` | MySQL 在字符串字面量中保留反斜杠（`\%` 为两个字符） | 一致 | S1b 决定；mysqldump 不产生这两种转义 |
| 7 | 列类型中间夹注释，例如 `int /* x */ unsigned` | 注释进入类型拼写，得 `UNKNOWN_SQL_TYPE`，表不可读 | MySQL 忽略注释 | 一致 | 低风险，记录即可 |
| 8 | JSON 值合法性 | 以 `json.loads` 判定，接受 `NaN`、`Infinity` 与孤立代理 | MySQL JSON 不接受 `NaN`/`Infinity` | 按 `json.loads` 的接受范围迭代实现 | S1b 决定是否收紧 |
| 9 | 深层嵌套 JSON（10 万层） | 未捕获的 `RecursionError` | 应为确定的结果 | 迭代检查，不受嵌套深度影响，按 `json.loads` 的语法接受 | 与第 3 条一起修正参照实现，或在 Contract 中规定嵌套上限 |

另外两点只影响诊断细节，S2a 实现时注意：

- 行预算（`max_rows_per_table`/`max_rows_per_source`）在原型中按块报告偏移，参照实现报告超限的那个元组；语料没有覆盖，S2a 需要按元组计数。
- 原型对每张表只登记首个表级错误。语料中两侧的诊断列表完全相同，但没有专门构造“同一张表多处错误”的用例；S2a 需补这类用例，并按 Contract 核对诊断的完整性。

## Arrow 列映射建议（DC46 第 6 条）

原型的映射（未加版本号，只为测量与差分）：

| 声明类型 | 原型 Arrow 类型 | 说明 |
| --- | --- | --- |
| 有符号整数（TINYINT–BIGINT） | `Int64` | 范围按声明位宽检查 |
| 无符号整数 | `UInt64` | 同上 |
| BOOLEAN | `Boolean` | |
| FLOAT / DOUBLE | `Float32` / `Float64` | `-0` 归一为 `+0`，与规范标量相同；SQL 字面量不产生 NaN |
| BLOB / BINARY / VARBINARY | `Binary` | |
| BIT(n) | `Binary`（每值 ⌈n/8⌉ 字节） | |
| CHAR/VARCHAR/TEXT、ENUM、JSON | `Utf8` | ENUM 存标签文本 |
| DECIMAL | `Utf8` 规范文本 | |
| DATE / DATETIME / TIMESTAMP / TIME | `Utf8` 规范文本 | |
| SET | `Utf8`，成员按声明顺序以 `,` 连接 | |

`Utf8`/`Binary` 用 32 位偏移；单列超过 2 GiB 时以 `RESOURCE_LIMIT_EXCEEDED`（偏移 0）失败。真实数据远小于此，但现有预算（单值 4 MiB、单表 200 万行）允许超出，S2a 应改用 `LargeUtf8`/`LargeBinary` 或按批输出，并给出准确偏移。

设计阶段定稿的建议：

1. **整数、布尔、浮点、二进制用原生类型**：这几类的规范标量载荷与 Arrow 值一一对应，原型已证明直接构建没有额外成本；整数可按声明位宽收窄到 `Int8`–`Int64`，省内存，但比较与投影 kernel 要多处理几种宽度，收益在 t4 规模上不明显，建议先统一 64 位。
2. **BIT 用 `FixedSizeBinary(⌈n/8⌉)`**：宽度由声明决定，比 `Binary` 少一个偏移数组。
3. **DECIMAL 保留规范文本**：MySQL DECIMAL 最多 65 位，`Decimal128` 放不下，`Decimal256` 可以，但规范文本的尾零与符号规则由 Shared Kernel 定义，换成数值类型后摘要仍要还原文本；比较时按文本相等即可。
4. **日期时间保留规范文本**：TIME 的范围（±838 小时）与零日期都超出 Arrow 时间类型的语义。
5. **ENUM 可选 `Dictionary<UInt16, Utf8>`**：字典就是声明的标签列表，省内存且便于比较；SET 可选 `List<Utf8>`，或保持连接文本（标签不含 `,`）。建议 ENUM/SET 先保持文本，等 V1 的比较 kernel 定型后再看。
6. 映射单独加版本号（DC46 第 6 条），表摘要按规范标量编码计算，与上述物理类型无关。

## S2a 建议

**缺口（原型未做或只做到够用）：**

1. 诊断完整性：消息文本、同一张表多处错误、行预算的元组级偏移（见上节）；补第 ③ 层负例与预算语料。
2. 第 ② 层 Hypothesis 差分没有做；第 ① 层只取了现有测试与 golden 的子集，S2a 应把现有解析器测试改为双实现参数化（讨论稿 §6.3）。
3. PyO3 adapter：`py.detach` 释放 GIL、取消标志与截止时间接到 `ParserRuntime`、Arrow C Stream 交给 Python；panic 转诊断的路径已在 core 入口，adapter 侧仍需一层。
4. 上节第 3、9 条的参照实现异常先修正，否则这些输入无法进差分。
5. 第 ④ 层的下游摘要对照（business snapshot digest、规范表摘要）属于 S2b，原型只到解析输出。

**风险与建议：**

1. **顺序部分决定加速上限。** 2× t4 上 UTF-8 校验加阶段 A 扫描约 0.17 s，是单线程总时间的约 14%，按 Amdahl 加速不超过约 7×，ct108 上实测 32 线程约 4.5×（见吞吐一节）。目标已有 7 倍以上余量，S2a 不必优化；以后 S2b 把物化与投影接到同一条路径时，阶段 B 的比重会变大，加速曲线应重新测。若需要，扫描可以按“预扫描找语句边界 + 分段并行”的方式做，但引号与注释状态跨段传递，复杂度明显上升，没有必要提前做。
2. **N 的暂定值。** 每 kernel 一个固定 N 的池（DC47 第 5 条）。按“并行效率 60–70% 以上的最大值”，ct108 上的暂定 N 为 4（并行效率 0.65，见吞吐一节）；解析只占 W1 的一小部分，N 应由 S2b 合并后的整条路径决定。
3. **内存。** 输入整份驻留，加上 Arrow 结果，峰值约为输入的 3.8–5.1 倍（见吞吐一节）。S2b 若改为解析完一张表就投影、写 IPC 并释放，峰值可以降到“输入 + 最大表”；`M` 的准入估算应按这个口径。
4. **块边界只在顶层逗号处切分**，大表内并行（L3）在原型中已经实现并通过 1 字节到 1 MiB 各种块大小的确定性检查；表级（L2）与块级并行混在一个任务列表里，没有单独的 LPT 排序，t4 规模下不需要。
5. **参照实现的语义问题应在 S1b 定稿**，S2a 不应同时改语义和换实现（讨论稿 §6.3 的差分前提）。

## 环境、取证与清理

- 分支 `p6-v6`（基于 `main` 的 `92d9439d65`），开发主机 linked worktree `/home/dev/gdms-p6-v6`；开发主机只编辑，编译、测试与差分都在节点上运行。分支用 git bundle 同步到各节点的临时 ref `refs/p6-v6/head`，节点 worktree 为 detached（`/home/dev/gdds-p6-v6`，含 `legacy` 符号链接）。
- 05 上的第一次编译在 V8 结束（runner exit 0，`end_utc 2026-10-25T08:48:01Z`）、确认没有 runner、pytest、dolt 与 Compose 进程之后开始。
- 代码提交 `ee516edb69` 的门禁：`ct108-gw-dms-05` 上 `GATEWAY_TEST_PACKAGES=rust ./vnext/scripts/run-tests.sh`，clean worktree，起止 HEAD 均为 `ee516edb69590d7c207394f9fb2f5d3640f04547`，runner exit 0（fmt、clippy `-D warnings`、`cargo test` 三步通过），日志 `/home/dev/gdds-p6-logs/v6/rust-runner-20261025T095748Z.log`。另在调试中通过 backend 的 ruff、mypy 与 `tests/test_architecture.py`（77 项）；两个 benchmark 脚本单独过了 mypy。
- 分支头 `2a17616874`（只改报告）的门禁：`ct108-gw-dms-05` 上同一命令，clean worktree，起止 HEAD 均为 `2a17616874f3316aebec9e87249c602a42b650be`，runner exit 0，日志 `/home/dev/gdds-p6-logs/v6/rust-runner-20261025T111420Z.log`（11:14:20Z–11:14:48Z）。
- 吞吐正式测量：`ct108-gw-dms`，V5b 报告提交（`main` 的 `38530841d1`）之后、其 Compose 栈拆除且确认节点空闲时开始，测量期间独占（见吞吐一节）。
- 提交 `110e5459fd`（只改报告）的门禁：`ct108-gw-dms-05` 上同一命令，clean worktree，起止 HEAD 均为 `110e5459fd53b88ea876b5f7963e4f1958dbc84f`，runner exit 0，日志 `/home/dev/gdds-p6-logs/v6/rust-runner-20261025T132124Z.log`（13:21:24Z–13:21:52Z）。同一 HEAD 上之前一次运行因 SSH 会话的 PATH 缺少 `/home/dev/.cargo/bin` 而在开始时退出（`rustc` 缺失，exit 1，日志 `rust-runner-20261025T132108Z.log`），补上 PATH 后重跑通过，代码未改。
- 真实数据日志的开头记录 hostname、起止时间与 HEAD；原始规范形、汇总 JSON 与取出的 SQL 都在节点上 worktree 外的 `/home/dev/gdds-p6-logs/v6/`（目录 `0700`、文件 `0600`），不进 Git。本报告只含计数、位置、类型标记、耗时与摘要，不含真实数据的表名与值。
- 参照实现、Phase 6 讨论稿、决议记录、implementation-stages、AGENTS 与 testing-conventions 均未修改。

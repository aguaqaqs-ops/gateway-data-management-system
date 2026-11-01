# Phase 6 S2a 代码审核

- 结论：**定向修订（F1–F3，另有低优先级 F4、F5）。** 实现本身没有发现正确性问题：adapter 的 FFI 边界、取消桥接、线程池、Arrow 输出、旧实现删除与构建链路都符合 DC52、DC72。需要修订的是测试证据：一部分双实现测试对 Rust 实际只测到测试垫片；第 ② 层范围过窄；第 ⑤ 层尚未建立。修订后做针对性复审，通过后再运行完整 runner 与第 ④ 层正式差分（DC64）。
- 日期：2026-11-01。
- 对象：`p6-s2a`，代码候选 `c7fc18ecd2`，handoff `d430806507`；审核区间 `49d0846d86..c7fc18ecd2`（91 个文件，+1647/−7816，不含 fixtures 删除）。
- 依据：设计 §7；执行计划 S2a；DC47、DC50、DC52、DC62、DC64、DC72；kickoff（`e9b3e04de9` 确认版）与 kickoff 审核。
- 方法：在开发节点只读 detached worktree `/home/dev/gdds-p6-logs/s2a-review-wt` 阅读全部产品与测试 diff；在 05 另建 detached worktree `/home/dev/gdds-p6-s2a-review-05` 复跑 focused 测试与 `cargo test --workspace`（第 3 节）。

## 1. 核对通过的部分

| 项 | 结果 |
| --- | --- |
| O2 | 首个产品提交 `229845a6c9` 只改 `_sql_values.py`：JSON 解码后遍历检查 float，非有限值按表级 `SQL_VALUE_ILLEGAL` 拒绝，写法与既有孤立代理检查一致；`1e400` 用例在共享 reject 参数表中，两个实现都运行。Rust 只对带小数部分或指数的数字做 f64 有限性检查，与 Python 的 int/float 划分一致（大整数不会被误拒） |
| Python 语义冻结 | 除 O2 外，没有提交修改 Python 产品代码；四个“对齐 S1b”的修订（`_binary`、类型注释、BIT 十进制、`\%`/`\_`）只改 Rust |
| 生产路由 | `vnext/backend/src` 不引用 `gateway_compute`；`pyproject.toml` 的改动只是 mypy override。双实现入口只在 `tests/support`（DC72 第 3 项） |
| adapter FFI 边界 | `_parse_sql_native` 整体包在 `catch_unwind` 中，panic 返回稳定的 `PARSER_INTERNAL_ERROR` envelope；core 入口另有 `catch_parser_panic`，两处各有测试。workspace 没有 `panic = "abort"`（`panic = "deny"` 是 clippy lint），catch 有效。`#![forbid(unsafe_code)]` |
| GIL 与取消 | 解析在 `py.detach` 中进行，输入为不可变 `bytes` 的借用。取消由进程内一个监视线程每 10 ms `try_attach` 调用 `is_set()`，结果写入 `AtomicBool`；core 在 chunk 检查点读取。探针异常或解释器不可用时按取消处理，并报告 probe 失败。没有发现死锁路径：主线程重新持有 GIL 后只做无阻塞的 channel 发送 |
| 线程池 | `OnceLock` 进程内唯一，首次按 N 创建（1..=MAX），之后 N 不同则拒绝，不嵌套建池（DC72 第 6 项）。worker 接线留给 S2b |
| 输出 | 每表一个 `RecordBatch`，经 `pyo3-arrow` 以 Arrow C Stream 交给 pyarrow；Utf8/Binary 超过 `i32::MAX` 字节改用 large 变体，阈值有单元测试 |
| 预算映射 | adapter 读取的 13 个 SQL 解析预算与 Python `ResourceBudgets` 中对应字段一一对应；读取器批次与 XML 预算不属于 SQL 解析 |
| 编码 | `SqlParseRequest` 构造时要求严格 UTF-8，非法 UTF-8 到不了任一实现；Rust 的 `INVALID_SOURCE_ENCODING` envelope 只是直接调用 adapter 时的防御路径 |
| 表内分块（DC72 第 4 项） | `output_is_identical_across_threads_and_chunk_sizes`（1/2/4/8 线程 × 5 种分块）、`row_budget_fault_uses_the_exact_over_limit_tuple_across_chunks`（1/4 线程 × 4 种分块，偏移固定在超限元组）、FRAGMENTS proptest（畸形输入产生多处诊断，在分块 2 字节、3 线程下与单线程不分块比较规范输出）。条件满足 |
| 旧实现删除 | 与 kickoff §3 一致。代码中已无 `canonical_row_hash`、`native_kernel_component`、`gateway-compute-python-impl` 引用；剩余出现在 AGENTS、testing-conventions（handoff §7 已写建议条文）与两份历史文档 |
| 架构检查 | 约束从旧 crate 平移到新 adapter，没有放松：core 与 shared kernel 不得依赖 adapter，adapter 不得带 hook 依赖，cdylib 名称同步为 `gateway_compute_native` |
| 构建链路 | Dockerfile 与 dependency-base 去掉 impl crate；runner 去掉 `cargo test` 排除；build-input 检查改为 `gateway_compute._native`；闭包路径同步。dependency-base 的锁定输入自构建提交 `132fc621d5` 起未变，SHA256 与 handoff 一致 |

## 2. Findings

### F1（中）：读取器生命周期测试对 Rust 只测到测试垫片

`test_table_access_sql_reader.py` 整个文件对两个实现参数化。其中三项在 rust 参数下验证的是 `tests/support/table_access_sql.py` 里的 `_ArrowSqlTableReader`，不是 Rust：

- `test_reader_single_consumer_reopen_and_close`
- `test_reader_stream_error_invalidates_reader_instance`
- `test_reader_checks_cancellation_at_successful_eof_commit_point`

Rust 一次性解析完全部值，迭代期间不会产生错误；这些行为来自垫片在迭代中套用的 Python `ParserRuntime`。垫片还把行号当作 byte offset 传给 `checkpoint`，语义不对。这样的通过会被计为双实现证据，但没有证明 Rust 的任何行为。

**修订：** 这三项在 S2a 只运行 python 参数；从垫片中去掉 `ParserRuntime` 模拟，垫片只做 Arrow 到标量的转换。handoff 写明：Rust 输出之上的产品读取器随 S2b 生产接入建立，届时这些测试对产品读取器双实现运行。其余三项读取器测试（列表重排、启动前超时或取消）确实经过 Rust，保持双实现。

### F2（中）：第 ② 层 Hypothesis 范围过窄

`test_table_access_sql_property.py` 只生成一种表（`BIGINT` + `VARCHAR`），值只有整数与文本，64 个样例，没有 NULL、其他类型、注释、多表或负例。kickoff §5 与设计 §7 要求第 ② 层覆盖语句结构、引号/注释/转义、类型化字面量与 S1b 边界。

**修订**（按比例，不求穷举）：
- 生成器覆盖各声明类型：有符号/无符号整数（含边界）、DECIMAL、FLOAT/DOUBLE、DATE/DATETIME/TIMESTAMP/TIME、BIT（`b'..'` 与十进制）、BINARY/VARBINARY（`x''`、`0x`、`_binary`）、JSON（含嵌套、转义与非有限值）、ENUM/SET，以及 NULL；
- 多表、INSERT 列清单、语句之间的注释与条件注释；
- 一个变异策略（截断、破坏引号等）产生非法输入，比较 status 与 (code, table, byte_offset)；
- 样例数适度（例如 100–200），`database=None`、`derandomize=True` 保持不变。

### F3（中）：第 ⑤ 层尚未建立

handoff §3 把第 ⑤ 层留到“审核与审核后完整验证时逐项核对”。kickoff §5 承诺：G2 census 记录到的每种 SQL 形态都有合成样本，在普通 CI 中运行；设计 §7 的验收是“五层语料全部通过”。

**修订：** 在测试中建立一张参数表，把 G2 census 的每个格式类别映射到双实现用例。已有第 ①/③ 层用例覆盖的类别直接引用，缺的补合成样本。没有对应用例的类别不能留空。handoff 附上这张映射表，并写明 census 类别清单的来源。

### F4（低）：`test_installed_extension_matches_the_current_rust_tree` 名不副实

该测试只断言 `len(__build_input__) == 40`，并不比较当前 tree。权威检查是 runner 调用的 `check-rust-extension-build-input.sh`。**修订：** 删除这个测试，或改名为它实际检查的内容；同时更正 handoff §2 测试归属表，把 build input 的 owner 写成 runner 脚本。

### F5（低）：非法值用例对 Rust 只比较诊断码

`test_illegal_values_invalidate_table` 在 rust 分支只断言 `any(item.code is code)`。kickoff 约定错误路径比较 (code, table, statement offset)。**修订：** rust 分支与同一输入的 Python 结果比较 (code, table, byte_offset) 列表；`test_unsupported_statements_fail_document` 同理。

## 3. 审核者复跑（05，调试证据）

- 节点 `gw-dms-test-05`，detached worktree `/home/dev/gdds-p6-s2a-review-05`，HEAD `c7fc18ecd2`，clean，legacy 链接存在；离线环境，无代理；获取并释放节点占用标记（会话 `p6-s2a-review`），cargo target 在 worktree 外并已清理。
- backend 同步使用 `--reinstall-package gateway-compute-python` 与当前 Rust tree 的 build input；`check-rust-extension-build-input.sh` 结果 `status=ok`。
- 同一组 12 个 focused 文件：**383 passed**（与 handoff 相同）。
- `cargo test --workspace --locked --offline`（与 runner rust 步骤相同，不再排除旧 crate）：全部通过，其中 core 29、adapter 1、shared kernel 82 等；adapter 测试二进制在 05 能正常链接 libpython。
- 日志 `/home/dev/gdds-p6-logs/s2a/review/focused-review-c7fc18ecd2.log`，SHA256 `f708dc61e627db0b06d49b342b9f7b15abe583b0f79dd01e1e8075c7a3ea663b`。一次编码探针因审核者构造请求时漏改 `source_size_bytes` 而在比较前退出（`utf8-probe.log`），随后确认 Contract 已在构造时要求严格 UTF-8，不再需要该探针。
- handoff 引用的 05 日志（focused、runner/closure、rust core/adapter、clippy）SHA256 已核对一致。

## 4. 观察（不阻塞）

1. adapter 的 `budget_value` 在属性缺失时静默使用 Rust 默认值。现在 13 个字段都存在，不会产生差异；S2b 接入生产时建议改为必须提供全部字段，避免日后字段改名造成静默分歧。
2. 第 ④ 层工具 `p6_v6_parser_diff.py` 通过 core 的 `table_access_parse` example 调用 Rust，不经过 adapter 与 Arrow C Stream。比较解析语义是有效的；adapter 这一段转换由第 ①–③ 层在小语料上覆盖。可选：差分时再加一项经 adapter 的行数与摘要核对。
3. `cargo test --workspace` 现在链接 adapter 的测试二进制。05 已通过，04 由最终权威 runner 验证；若 04 因环境无法链接，按 runner 停止规则处理。
4. 测试支持层的线程数固定为 1；进程内线程池固定 N，adapter 路径无法在同一进程内比较 1 与 N。1 对 N 的确定性由 core 测试证明，符合 DC72。
5. handoff 未记录 dependency-base 归档的传输起始时间（已如实披露）。AGENTS 要求记录构建/传输起止时间；今后的传输请记录。

## 5. 下一步

1. 实施方按 F1–F5 追加提交（不改写已有提交），更新 handoff，并在 05 复跑相关 focused 测试。
2. 本会话做针对性复审。
3. 复审通过后按 DC64：在最终候选上运行六包权威 runner（04 空闲且不占用基准最终 runner 时；按 handoff §8 第 2 项的 dependency-base 与离线构建设置），并在 05 运行第 ④ 层正式差分（t1–t4 的 v1/v2 与 testdata1）。
4. 05 审核 worktree `/home/dev/gdds-p6-s2a-review-05` 保留到复审结束。

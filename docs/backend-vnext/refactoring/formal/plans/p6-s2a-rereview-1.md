# Phase 6 S2a 针对性复审 1

- 结论：**通过。** F1–F5 均已关闭，修订没有引入新问题。可以按 DC64 在最终候选上运行完整权威 runner 与第 ④ 层正式差分，证据由本会话复核。
- 日期：2026-11-01。
- 对象：代码候选 `30d67140d4`（`c7fc18ecd2..30d67140d4`，7 个提交），handoff `f7dc36ddbd`；分支 `p6-s2a`，clean，未推送。
- 依据：[代码审核](p6-s2a-code-review.md)（F1–F5）；DC64、DC72。

## 1. Finding 关闭情况

| # | 修订 | 结论 |
| --- | --- | --- |
| F1 | 三项读取器生命周期测试用 `indirect` 参数只跑 python；`_ArrowSqlTableReader` 去掉 `ParserRuntime` 模拟，只做 Arrow 到标量的转换；列表重排与启动前超时/取消三项保持双实现。handoff 写明产品读取器随 S2b 建立 | 关闭 |
| F2 | 生成器覆盖 BIGINT（含 ±2^63 边界）、BIGINT UNSIGNED（含 2^64−1）、DECIMAL(18,6) 边界、FLOAT（float32 可表示范围）、DOUBLE、DATE、DATETIME(6)、TIMESTAMP(6)、TIME(6)（含负值与 838 小时）、BIT（`b'..'` 与十进制）、BINARY/VARBINARY（`x''`、`0x`、`_binary`）、JSON（嵌套、转义、`1e400`）、ENUM、SET、VARCHAR，每列均可为 NULL；2–3 张表，INSERT 列清单正反顺序交替，语句间三种注释与条件注释。128 个样例比较完整结果；另有 64 个变异样例（截断最后一个元组、未闭合字符串）比较 status 与 (code, table, byte_offset)。`database=None`、`derandomize=True` | 关闭 |
| F3 | `test_table_access_sql_census.py` 读取 G2 census（`p5-arch-closure-s1-census.json`），断言其中出现的类型集合与映射表完全相等，census 不含行数据、无 JSON 列、无未知类型；每个类别映射到双实现用例，缺直接 owner 的语句边界形式（行注释、块注释、条件注释、CRLF）补了一个合成样本。审核者核对四个 owner 测试都存在且双实现运行，`s2-dump-boilerplate` golden 存在 | 关闭 |
| F4 | 删除名不副实的 build input 测试；handoff 测试归属表把 build input 的 owner 写为 `check-rust-extension-build-input.sh` | 关闭 |
| F5 | 两个 reject 参数表在 rust 分支与同一输入的 Python 结果比较 status 与 (code, table, byte_offset) | 关闭 |

## 2. 修订中的产品改动

- `values.rs`：元组未闭合时，诊断偏移改为元组起点，与 Python 参照实现一致；补上“值之后直接到达 EOF”的分支，同样报在元组起点。这是 F2 变异样例发现的偏移差异，按 S1b 冻结语义对齐 Rust，不改 Python。跨线程数与分块大小的确定性测试仍然通过。
- `fixtures/vectors/table-access/sql-known-types/v1/cases.json` 与类型参数表增加 census 中出现的类型拼写（TINYINT、TINYINT UNSIGNED、INT、SMALLINT UNSIGNED、DATETIME、VARCHAR(128)、TEXT），只扩大覆盖，不改已有用例的期望。

## 3. 审核者复跑（05，调试证据）

- 节点 `gw-dms-test-05`，新建 detached worktree `/home/dev/gdds-p6-s2a-rereview-05`，HEAD `30d67140d4`，clean；离线环境，无代理；节点占用标记已获取并释放；cargo target 在 worktree 外并已清理。
- 扩展的 build input 与 Rust tree `61a76caa…` 一致。
- 原 12 个 focused 文件加 `test_table_access_sql_census.py`：**403 passed**。实施方报告的 284 项不含 architecture 与 artifact 的 4 个文件；本轮修订没有改动这些文件，审核者一并复跑以覆盖两轮集合的并集。
- `cargo test --workspace --locked --offline`：全部通过（core 29、adapter 1、shared kernel 82 等）。
- 日志 `/home/dev/gdds-p6-logs/s2a/review/focused-rereview-30d67140d4.log`，SHA256 `faeb1baf31379cac6af99664d3eeeac997383859fefefe21a2cc71fcd6498705`。

## 4. 观察（不阻塞）

1. census 映射表中的 owner 是测试 ID 字符串，测试只检查非空，不检查对应测试是否存在。目前四个 owner 都已人工核对；改名时需要同步更新映射表。
2. 实施方在审核者的 05 worktree `/home/dev/gdds-p6-s2a-review-05` 中做了本轮验证。结论不受影响，但审核 worktree 应只由审核方使用；本轮复审另建了 worktree。
3. 代码审核第 4 节的观察 1–5 仍然有效（预算字段静默默认、第 ④ 层工具经 core example、04 上 `cargo test --workspace` 的 libpython 链接、测试支持层线程数固定为 1、传输时间记录）。

## 5. 下一步（DC64 证据）

1. **04 六包权威 runner**（04 空闲时；先获取节点占用标记，基准的最终 runner 优先）：
   - backend/worker 在 04 本机离线构建：`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-d054366c02fa`、`GATEWAY_DOCKER_BUILD_NETWORK=none`，保留 Compose build，不设 `GATEWAY_COMPOSE_GATE_PREBUILT`；
   - `lock-d054366c02fa` 目前只在开发节点与 05，须先经 LAN 传到 04，用程序比对 config digest 与全部 DiffID（期望值从归档 config 机器生成），记录传输起止时间；
   - RS 与 client e2e 镜像的 label 若与候选不符，用 04 上已预置的依赖基础镜像离线重建（S1c 取证的做法）；
   - runner 环境 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，代理与 `GATEWAY_DOCKER_BUILD_NETWORK`（除构建步骤外）不带入 runner。
2. **05 第 ④ 层正式差分**：t1–t4 的 v1/v2 与 testdata1（按输入 digest 与 t3 去重并记录），用 `p6_v6_parser_diff.py real`；日志只含计数、位置与类型标记，不含值或 SQL；在最终候选的 clean worktree 运行。
3. 两项证据交本会话复核。S2a 的 exit 在基准 exit 之后办理。

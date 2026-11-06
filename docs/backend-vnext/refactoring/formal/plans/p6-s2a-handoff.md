# Phase 6 S2a implementation handoff

状态：**F1–F5 定向复审 1 与证据复核 2（`7c5cc2a49efb`）均已通过；候选 `3b3d9c97bc` 的 05 定向验证、第 ④ 层正式差分与 04 六包权威 runner 均通过。现按 DC81 在当前 main 上办理整合收尾，固定合并候选审核和最终 04 逐包判定/定向 runner 尚待完成；S2a exit/tag 尚未办理。**历史失败见 §10，原候选证据见 §11，整合计划见 §13。

日期：2026-11-01

## 1. 候选与授权边界

- 分支：`p6-s2a`；起点为合入 S1c 与 backend image 任务的 merge commit `49d0846d8625a8a928735c4fa0ea5126cf7ab741`。原代码候选 `c7fc18ecd20bb8455a8a54ba3a090e468a42d785` 经 main 本地审核提交 `41844c4958554f0d8c68e41702783b86469d526a`（`p6-s2a-code-review.md`）给出 F1–F5 定向修订；证据复核 1 通过的候选为 `30d67140d499383e855e361378bf5ef70a946edd`；删除过时 repository_service 测试后的当前代码候选为 `3b3d9c97bcb6d79d6c087099fbe6353f170bf68f`。
- Kickoff 初稿 `30de9c1cae` 未改写；按审核意见与 DC72 追加确认提交 `e9b3e04de98769faf6a66e93bcdde0b3e7958979`。
- O2 是首个产品提交 `229845a6c97786c4c8384607733bff2363b4a62f`，只修改 Python 参照实现和现有 reject 参数表；之后实现 Rust parser/adapter。原实现候选为 `c7fc18e`；本次追加 F1–F5 测试修订及未闭合 INSERT 元组诊断偏移对齐，证据复核 1 候选为 `30d67140d4`；随后仅删除 `test_uv_consume_allows_component_pytest_invocation_pattern` 的测试提交 `3b3d9c97bc`。没有改产品代码，所有修订均追加提交。
- Owner 已在 main `0749edb8e6` 以 DC72 确认 kickoff。DC81（2026-11-05）解除 S2a exit 对基准整体 exit 的等待依赖；退出仍须经独立审核，并按最终整合影响补足证据。没有推送、打 tag 或改写已审核提交。
- `backend.parse_sql()` 与 worker 生产路由仍使用 Python。`implementation="python" | "rust"` 只存在于测试支持层；没有 production flag、部署配置或 shadow 执行。

## 2. 实现与删除范围

1. **O2（Python 参照实现）：** JSON 解码后迭代检查 float，拒绝包括 `1e400` 溢出为 `inf` 的非有限值，按表级 `SQL_VALUE_ILLEGAL` 处理。现有 reject 参数表增加对应例子；Rust 实现与之对齐。O2 focused 测试 `28 passed`，日志 `o2-focused-retry-229845a6c9-20261031T2229Z.log`，SHA256 `e2b92fc4851c49b6f0d4ce90cc9056fd65bca3fe89b60e72900229ce9490575a`。S1b 冻结语义未作其他变更。
2. **Rust parser 与 adapter：** V6 `table_access` parser 补齐诊断、预算、值转换与 S1b 边界行为；保留 parser 专属 INSERT 元组 chunking。新 adapter 沿用 `gateway-compute-python` distribution/crate 名称，对外提供全新接口；删除 `gateway-compute-python-impl` 和旧 API symbols。adapter 使用 `py.detach`、owned Arrow C Stream、安全取消/deadline bridge，core 与 FFI 两层捕获 panic 并转诊断。Rust core 不依赖 PyO3，不物化逐行 Python 对象。
3. **线程池：** adapter 中一次创建、进程内共享、固定 N 并跨调用复用有界 pool；调用方传入 N。首次初始化后不另建或嵌套 pool；不一致的后续 N 被拒绝。adapter pool reuse 测试默认 N=1；一致性测试分别比较 N=1 与 N。worker 启动接线及部署配置 N、M 留给 S2b。
4. **旧实现删除：** 删除 `capabilities/canonical_row_hash`、旧 Rust row-hash pipeline/专属模块与重复语义测试、旧 adapter/impl crate 与旧扩展测试、canonical row-hash golden/schema/vector、旧 Contract、`native_kernel_component.sh` 及相关架构基线条目。保留通用 ArtifactStore/ArtifactRef、comparison 与 Table Access Contract 测试。完整逐项来源/调用方和删除清单见已确认的 [kickoff §3](p6-s2a-kickoff.md#3-旧实现调用方与清理范围dc52)。
5. backend Dockerfile 的 maturin 构建目标改为新 adapter，并以 `49d0846d86` 中 `p6-backend-image-exit` 的新 Dockerfile 为基线；dependency-base、Cargo workspace、extension build-input 校验、runner 与输入闭包同步更新。Cargo workspace 删除旧 crate 后，candidate 中 runner 的 `cargo test --workspace --locked --offline` 不再排除旧 crate。
6. F2 的截断变异在首次调试中暴露了 Rust 对未闭合 INSERT 元组报告 EOF 偏移、Python 参照报告元组起点的差异。Rust core 现对元组结束于输入边界的情况报告元组起点，与 Python 对齐；未修改 Python 参照语义。生成的 `0x` VARBINARY 样本至少含一个字节，空二进制由 `x''` 覆盖，确保非法变异作用于有效基础文档。

### 测试归属

| 不变量 | 唯一权威 owner | 本候选的职责边界 |
| --- | --- | --- |
| Table Access SQL 对外语义、typed values、诊断 code/table/offset 与双实现差分 | backend parser/reject/limits/conformance/property/census tests | Python/Rust 使用同一测试支持参数化；F1 三项生命周期测试在 S2a 仅运行 Python，其他三项读取器测试保持双实现。 |
| Rust parser 有界、诊断排序、row-budget offset、chunk/线程确定性 | `gateway-compute-core::table_access` 测试 | Rust core 测内部边界；backend 测已安装 adapter。 |
| detach、Arrow C Stream、取消/deadline、adapter panic envelope 与共享 pool 复用 | backend `test_table_access_rust_adapter.py` | Rust adapter crate 只测 FFI panic 边界；build input 的权威 owner 是 runner 调用的 `vnext/scripts/check-rust-extension-build-input.sh`；worker 接线归 S2b。 |
| core/adapter 依赖方向、unsafe 与 Python row materialization 禁止项、extension 形状 | `gateway-architecture-check` / backend architecture owner | 不在 feature flag 或差分测试中重复证明。 |

## 3. 五层差分状态

规范结果按 kickoff §5 的 V6 `parse-canonical` 形比较；成功路径逐值比较，错误路径比较 diagnostic code、table、statement offset，不要求两实现的 message 文本相等。真实数据日志不记录 SQL 或值。

| 层 | 候选状态 |
| --- | --- |
| ① 既有 parser/reject/limits/types/reader/conformance 用例双实现 | F1 指定的三个 Rust 输出读取器生命周期测试仅跑 Python；列清单重排、启动前超时与取消三项仍双实现。其他 parser/reject/limits/types/conformance 测试双实现。当前 focused suite 通过。 |
| ② Hypothesis 生成的语法、literal 与 S1b 边界差分 | 128 个通用样例覆盖类型化值、整数与 DECIMAL 边界、多表/列清单/注释、嵌套转义 JSON 与 `1e400`；64 个变异样例覆盖截断和未闭合字符串，比较 status 与 diagnostic 三元组。两项均保持 `database=None`、`derandomize=True`。当前 focused suite 通过；这是调试验证，不宣称完整随机样本/CI gate。 |
| ③ 负例、资源预算、诊断截断及超限元组 offset | F5 两个错误路径参数表在 Rust 分支比较 Python 同输入结果的 status 与 diagnostic 三元组；parser/core 现有资源预算与截断测试仍是各自不变量的权威 owner。focused suite 与 gateway-compute-core focused tests 通过。 |
| ④ t1–t4 v1/v2 与 testdata1 真实值逐项差分 | **05 已通过**。候选 `3b3d9c97bc` 上覆盖 10 个输入别名、按 SHA256 去重为 8 个唯一 SQL 输入；8 份均为逐值差异 0、诊断差异 0，testdata1 两份分别命中 t3 v1/v2。逐份计数与摘要见 §11。 |
| ⑤ G2 census 覆盖到的 SQL 格式类别 | 下方新增完整映射表；测试读取 aggregate census JSON 校验 SQL type 类别闭合，并以双实现 synthetic 样本覆盖缺少直接 owner 的 statement-boundary 形式。当前 focused suite 通过。 |

N=1/N 及不同 chunk size 的逐字节确定性由 core/adapter focused 测试覆盖。V6 原型的吞吐数据不是 S2a 当前候选证据。

### 第 ⑤ 层 G2 census 格式映射

G2 census 类别清单取自 `docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-s1-census.json` 的 `datasets[*].storage_column_type_counts` 与 `datasets[*].version_manager_saved_time_type`。类型集合为 `DATETIME`、`ENUM`、`FLOAT`、`INT`、`INT UNSIGNED`、`SET`、`SMALLINT UNSIGNED`、`TEXT`、`TINYINT`、`TINYINT UNSIGNED`、`VARCHAR`，另有 manager 时间列 `VARCHAR(128)`。该 JSON 是 aggregate-only（`contains_row_data=false`），没有 JSON 列，也没有 unknown SQL type。

SET 语句类别根据 G2 handoff §2.4 与 §8.7 的接受/保留失败结论整理；mysqldump boilerplate 与条件注释类别由 G2 handoff §2.4 和 V6 原型报告 §7 补充。census 不保存 t3-c-v1 的原始 SQL，因此该失败类别映射到既有双实现 unsupported-user-variable 参数用例；测试不复制真实 SQL。表中每个 owner 都由同一 Python/Rust 参数化测试执行。

| G2/V6 格式类别 | 双实现 owner | 覆盖方式 |
| --- | --- | --- |
| SQL type DATETIME | `test_sql_parser_type_descriptors_match_the_type_mapper[DATETIME]` | 既有第 ① 层类型参数用例。 |
| SQL type ENUM | `test_sql_parser_type_descriptors_match_the_type_mapper[ENUM('a','b')]` | 既有第 ① 层类型参数用例。 |
| SQL type FLOAT | `test_sql_parser_type_descriptors_match_the_type_mapper[FLOAT]` | 既有第 ① 层类型参数用例。 |
| SQL type INT | `test_sql_parser_type_descriptors_match_the_type_mapper[INT]` | census 对应类型参数新增到第 ① 层表。 |
| SQL type INT UNSIGNED | `test_sql_parser_type_descriptors_match_the_type_mapper[INT UNSIGNED]` | 既有第 ① 层类型参数用例。 |
| SQL type SET | `test_sql_parser_type_descriptors_match_the_type_mapper[SET('x','y')]` | 既有第 ① 层类型参数用例。 |
| SQL type SMALLINT UNSIGNED | `test_sql_parser_type_descriptors_match_the_type_mapper[SMALLINT UNSIGNED]` | census 对应类型参数新增到第 ① 层表。 |
| SQL type TEXT | `test_sql_parser_type_descriptors_match_the_type_mapper[TEXT]` | census 对应类型参数新增到第 ① 层表。 |
| SQL type TINYINT | `test_sql_parser_type_descriptors_match_the_type_mapper[TINYINT]` | census 对应类型参数新增到第 ① 层表。 |
| SQL type TINYINT UNSIGNED | `test_sql_parser_type_descriptors_match_the_type_mapper[TINYINT UNSIGNED]` | census 对应类型参数新增到第 ① 层表。 |
| SQL type VARCHAR | `test_sql_parser_type_descriptors_match_the_type_mapper[VARCHAR(16)]` | census 的聚合类别映射到已有 VARCHAR descriptor 参数。 |
| Version manager saved-time type VARCHAR(128) | `test_sql_parser_type_descriptors_match_the_type_mapper[VARCHAR(128)]` | census 中直接记录的完整类型参数，新增到第 ① 层表。 |
| 条件注释中的允许项 `SET @saved_cs_client` | `test_mysqldump_session_setup_statements_are_accepted` | 既有第 ① 层 mysqldump SET 参数表。 |
| t3-c-v1 保留的 unsupported bare SET 类别 | `test_unsupported_statements_fail_document` | 既有第 ① 层 synthetic user-variable 拒绝参数（`SET @other_client = 1;`）；不把 census 失败记录当作可重放 SQL fixture。 |
| mysqldump SET/DROP/CREATE/LOCK/ALTER KEYS/INSERT/UNLOCK boilerplate | `test_sql_golden_parser_matches_expected[sql/valid/s2-dump-boilerplate]` | 既有第 ① 层双实现 golden。 |
| 行注释、块注释、条件注释与 CRLF 语句边界 | `test_synthetic_census_format_sample_matches_reference` | 第 ① 层没有单项直接 owner，补充一个双实现 synthetic 样本。 |

## 4. 05 编码前合入组合基线

运行节点为 `ct108-gw-dms-05`（hostname `gw-dms-test-05`），clean detached worktree `/home/dev/gdds-p6-s2a-baseline-05`，起止 HEAD 均为 `49d0846d8625a8a928735c4fa0ea5126cf7ab741`，会话 `p6-s2a-impl`。日志位于节点 `/home/dev/gdds-p6-logs/s2a/`。

| 步骤 | 结果与日志 |
| --- | --- |
| 首次 S1c/backend + SQL focused 基线 | `471 passed, 4 failed, 1 warning`；4 项均因 backend 启动真实 Repository Service 时未准备该 worktree 的 `repository_service/.venv`。首次日志保留：`baseline-49d0846d86-20261031T221122Z.log`，SHA256 `3bf3b9f48aa3a1b5f09dbb6a81d9c6f0295f8ebbbf39963bf2ba811bb5d910ee`。这是编码前调试准备遗漏，不是产品断言失败。 |
| 离线同步 repository_service 后重跑原 4 项 | `UV_OFFLINE=1` 经 `uv-consume.sh` 同步；4 项全过，`4 passed, 1 warning`。日志 `baseline-followup-49d0846d86-20261031T2226Z.log`，SHA256 `daacea6aaa577e3a7e95568869101b7e2332114824d2f84568b7f33664f2cf6b`。 |
| 同一基线的 rust package | fmt、clippy、cargo test 三步全部执行并通过；cargo test 使用 S2a 前规则排除 `gateway-compute-python` 与 `gateway-compute-python-impl`。同一 followup 日志记录 `rust status=passed`、exit 0；结束时间 `2026-10-31T22:26:55Z`。 |

首次失败日志未覆盖。按用户指定，该基线是调试运行，不适用 DC68 的取证重做次数限制。

## 5. 原候选 c7fc18e 的 focused 与静态结果（历史记录）

本节记录原代码候选 `c7fc18e` 的审核前运行，不能替代 §9 的 F1–F5 最终候选验证。所有结果均在 05 的 clean、已提交 worktree `/home/dev/gdds-p6-s2a-impl-05`，HEAD `c7fc18ecd20bb8455a8a54ba3a090e468a42d785`，`vnext/rust` tree `2ef56a15b038481fe13395fc248061e014d376d1`。环境使用 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`TMPDIR=/home/dev/gdds-test-tmp`、worktree 外 `CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/p6-s2a-impl-cargo-target`；未用转发代理。日志均在节点 `/home/dev/gdds-p6-logs/s2a/`，下表给出 SHA256。

| 检查 | 结果 | 日志 SHA256 |
| --- | --- | --- |
| backend parser/adapter/limits/reader/types/conformance/property/architecture/artifact focused | **383 passed**, 2.35 s，exit 0 | `focused-backend-c7fc18ecd20b-05.log` — `3ce542a9b238214d758f8e3cf3248d98db1d78549e7a43bf523c01e6c6d32835` |
| runner 与 input closure focused | **58 passed**, 4.03 s，exit 0 | `focused-runner-closure-c7fc18ecd20b-05.log` — `4b871e4b79006ca19a9fc80d0868737d5e801f9bc78442429a1de54ea57aabe6` |
| Rust `cargo fmt --all --check` | exit 0 | `rust-fmt-c7fc18ecd20b-05.log` — `d246c039d5a33fae948375c27796ddba63b1cd1c64b07dcc4b18d0db7939099d` |
| Rust `cargo clippy --workspace --locked --offline --all-targets -- -D warnings` | exit 0 | `rust-clippy-c7fc18ecd20b-05.log` — `421d0062a73c545c462118c7dd3d6e0cb315a6470cbc75fc5be7668a8a58cc42` |
| focused `cargo test --locked --offline -p gateway-compute-core` | **29 passed**, exit 0 | `rust-core-tests-c7fc18ecd20b-05.log` — `afe6253fb72d452684fea3b9768ca4fec33f77b33f8e5b498f8233431bda3565` |
| focused `cargo test --locked --offline -p gateway-compute-python` | **1 passed**, exit 0 | `rust-adapter-tests-c7fc18ecd20b-05.log` — `6c7dfa70585baa4339f52ac6743418b52c392b677c5258bd130e9af78f3388bc` |
| backend Ruff / mypy | 均通过 | `backend-ruff-c7fc18ecd20b-05.log` — `2a17c329299e08e550e62b5fb8cc8b1c1280cb91e0af26aa36cf4372464f79a2`; `backend-mypy-c7fc18ecd20b-05.log` — `7d3193bef331a1e44b771d041ab308f915454d70a0854597961587aba8913e86` |
| shared_kernel Ruff / mypy | 均通过 | `shared_kernel-ruff-c7fc18ecd20b-05.log` — `4e0ad13fd32014cb76237d04cfcda170d438d5a647aa5d49e634a230d2ed6876`; `shared_kernel-mypy-c7fc18ecd20b-05.log` — `469987811003e09d28076ed4feedd4d27c85ab0e10929f500f226341f38ddfb3` |
| repository_contracts Ruff / mypy | 均通过 | `repository_contracts-ruff-c7fc18ecd20b-05.log` — `be64b64ef872500c877ba513e1e11b85f1b7f87d3c7072ed1a1df416a34ef5be`; `repository_contracts-mypy-c7fc18ecd20b-05.log` — `ce87282ed1d54e3e8af67b5c4f749fe10cfd52868458d945d56ba07b60097cc7` |
| repository_client Ruff / mypy | 均通过 | `repository_client-ruff-c7fc18ecd20b-05.log` — `82470ac274ed525d00cab746db561c74ed51bf68cb1a4a2bb3157158ee0fc466`; `repository_client-mypy-c7fc18ecd20b-05.log` — `4f0f2f77ed10a997f906ac5a79d786b199b31e9eabeb68fe6a3b5d66df2ae087` |
| repository_service Ruff / mypy | 均通过 | `repository_service-ruff-c7fc18ecd20b-05.log` — `c798d96037f4ccf555ad5fa6442d1aa8f84f8dac2805176f5a45597df4d5a01e`; `repository_service-mypy-c7fc18ecd20b-05.log` — `89d997a22197c2eecc9c2fd151735a30b5e96a7d5fad6fd3e1d40d6fddf603dd` |

本次未运行六包完整权威 runner、`cargo test --workspace`、backend/worker Compose 重建或第 ④ 层正式差分。focused 结果仅供代码审核和调试；按 DC64 在审核通过后绑定最终候选。

### 调试迭代记录

差分逐步发现并修复：`_binary` 前缀值在非 binary 列的拒绝语义、列类型注释忽略、unquoted BIT 数值按十进制解析、`%` 与 `\_` 的 SQL 转义保留。对应失败日志 `focused-backend-20c8adf198-05.log` (`419b553e7dbcb4da70900da5db1d21982cb805578ae093fd3dffeffca9c6e841`)、`focused-backend-e49451fc6c41-05.log` (`946d02800ccb482c73b062b8616f9b5a2395fa1453476c4d4d06a07d7c680381`)、`focused-backend-bd2455fe500d-05.log` (`7df46d1852bdc3a17f73c52477f7c392b1765510cd2ef00027b4e4d2b4c1320b`) 与 `focused-backend-cae5510cfb35-05.log` (`23113b81dc6fce317e9d53855a3c3fe194de44b3caf4f93551190851261954d4`) 均在 05 保留；当前最终 focused log 全绿。

初次 focused 收集还因测试从错误模块导入 `NullScalar` 退出 2，日志 `focused-backend-132fc621d5-05.log`，SHA256 `987a1941fb867d668d747e3d22cf63a6de3022d6bada680b0461bbe4ea375279`；测试导入修正后复跑。

在 `2077eac0` 构建扩展时，Rust 测试字节串用了无效 `\%`/`\_` 转义；日志 `rust-extension-sync-2077eac0dffa-05.log` SHA256 `bb9a0f0cd395589b8d881830c28c298d8443efb663468d7fdd4df86737a86ae4` 的 wrapper 错记 exit 0，但日志本身记录 maturin/Cargo 编译失败，不能当作通过证据。修正字节串后，最终 HEAD 的扩展同步日志 `rust-extension-sync-c7fc18ecd20b-05.log` SHA256 `d7b9b70e271a6d254dbfc696d0ad0f0b66978feaaa8e4152087d8db4a7079545` exit 0。

另有一次从 selector 目录外调用 `cargo fmt` 的命令失败；保留日志 `rustfmt-command-failure-ccf21ae357-05.log` SHA256 `3eec63a058a9a841b4ed174b2a1d854321995bd15aa4312f5e4fc0ed152c4373`，随后在 `vnext/rust` 正确执行格式化，日志 `rustfmt-apply-ccf21ae357-05.log` SHA256 `626f3d61c7bfaaf3630aeec1c4732d4767302c021c97bd579d43e69d79f2385`。首次依赖镜像身份检查的内联 Python 引号错误也已保留在 `dependency-base-05-identity-command-failure.log`；该命令在比较前失败、只创建了临时 archive，随后用独立 helper 成功比较。以上操作错误均未被用于验收结论。

## 6. Dependency-base 与节点记录

`Cargo.lock` 有变化，按 AGENTS 在 CT201 clean source worktree 构建并经批准 LAN 预填充 05；代码候选后续未再改变这些输入。05 仅做本机离线 backend extension 构建与 focused 验证，未运行 Compose；05 无受限代理，未设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。

| 字段 | 记录 |
| --- | --- |
| 来源节点/提交 | `heavy-dev-01.lan`（CT201），commit `132fc621d5711ae39ac8f1dc66f4349b2f6fe428`，2026-10-31 23:03:02–23:04:41 UTC，build exit 0；日志 `/home/dev/gdds-p6-logs/s2a/dependency-base-132fc621d5-ct201.log`，SHA256 `1f673c30f48b7f7f77afa3fdc41fbf5bc75f94f2d03da81cbed840173fd88e7b`。 |
| lock/base inputs SHA256 | `backend/pyproject.toml` `4c091e36d4762f11b4085f207528548502ae723e7876d2feeeedcd4cd56f9c7f`; `backend/uv.lock` `d18d89a24a8acae02eb6b3b23c342c1b673ea0e7e87add93d0762edfa18b822d`; `.python-version` `3a55324cbeddc91df012407d051dad08c88624c95a82fbdb856728729fbd14ab`; `rust/Cargo.lock` `bac3443e4d16c22ed16adaadbaf3d3e7b713d78516e14938cdbca50ebd837d29`; `rust/rust-toolchain.toml` `0506c53cddc8435a55513d5f662c302ff6eb4035f012d5d5e5a47e96a7f40420`。base `rust:1.97.0-bookworm` config digest `sha256:7ea53b11a01d2d52b4af8fa073cd76ecbaf7dc385b88cc9d0ce8205a7c941ff1`。 |
| dependency-base | tag `gateway-backend-deps:lock-d054366c02fa`; full tag-input digest `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`; resulting config digest `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a`。 |
| archive | `/home/dev/gdds-p6-artifacts/s2a/gateway-backend-deps-lock-d054366c02fa.tar`; SHA256 `3fd859201de06757c8ce5af6dd4ad6e26d99b7439bc2edabb59035b5dd0c9ce6`。 |
| 05 prefill / identity | node `gw-dms-test-05.lan`; `docker load` identity verification 2026-10-31 23:08:09–23:08:31 UTC, exit 0; log SHA256 `c3ff4e4adddf6125e2647d496d90a83dc9e82d44029e8dc150293f9d3513040e`。跨节点比较 config digest 与下列全部 DiffID，未使用 inspect ID。单独的传输起始时刻未落入日志；目标加载/身份校验时间如上。 |

RootFS DiffIDs（完整）：

```text
sha256:f2c42f900cb3b12d5456f76b4fa6454a52df3981323d3a1b1a17fe4c4955ab4a
sha256:d13007d6a3979078792cbc2afff5c74eb1a14f5a02394f6cae0a873a0752c104
sha256:af68230260cdbb7ac206fc2f95bf67c1a75ebdcf3e4014accffd3c8bcb478e15
sha256:ac06852f1f7254083486500d54ef4292d46b2c868df62ba93466e633c78a7cf1
sha256:a9a1dcf9cd75357904971362ed8395b2feb40790c75a06b85852133a204ba79a
sha256:c7b432c3f658b7dd011573e85ed7bdbe36769855537890eef470c62367b68c25
sha256:ca61d18a121a5670b32df53fa9afeeee4290a8f2680c8621a7076d8253151588
sha256:d9100de052a9a4cbb39754e9bcdbebe082b0c8e4cd1a5d4f446cef2cd4ac87e1
sha256:01614bf2b27515a3ea31f460030cef9e37a2d7d65d7cffdac5f3d7b6d49671c1
sha256:2f04268a672be20980a33289ad5086de8a8a7db36b51cff7fcfea0995baec29f
sha256:3c5de003195a21e12a21ff7a4976b687ef61ef946f74a6465281c6f6f2720cc6
sha256:3b36040844dfd8c76fbc316aafd0929d65e602016261737368cf63e245598dd6
sha256:bfb2b2a172006ee7882fcc751dcef85d418a0e24837b11d30220cf21183c1dce
sha256:b6b4b17f0450d4b8b752e1fb44298477f29e1f74d65584d3182227e9ff20b12c
sha256:50e4a188b1446b8b9a51ccb3d9745164e86d6b9bdb1f342e9774fe93a4f853d3
sha256:a7afafdb6a8aa5d13ade8b6eef2986bd37d07e84b2d0b3767f7bb0eb535bf5f4
sha256:678693472110b1f3f8c40466db580981b7952ede803eaa1518f59d3730ab2814
sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef
sha256:c338f3f88c37281e775f0b6dfdfa4c079858214cf04733e88f0bda4e4ca4a1f0
```

一次身份解析命令的引号错误日志 `/home/dev/gdds-p6-logs/s2a/dependency-base-05-identity-command-failure.log` 记录在 23:07:48 UTC，SHA256 `19818595ca347ddc41b9f770e44b690b8194704dca99dc4ea29e224459b13a24`；失败发生在比较前，只留下临时 `loaded-deps-check.tar`，随后移除并用独立 helper 完成上述身份检查。该失败不影响原 archive 或镜像。

今后的 dependency-base 局域网传输要在 handoff 记录传输起始与结束 UTC 时间；本次旧记录只留有目标节点加载/身份校验时间，未留单独传输起点。

原 focused worktree 的清理记录仍指向 c7fc18e。当前用于 F1–F5 的 05 worktree 与最终状态见 §9。

## 7. 治理文档 handoff（由治理会话同步）

按 DC72，本分支没有改 `AGENTS.md`、`testing-conventions.md` 或 execution plan 的 path list。建议治理会话按以下内容更新：

1. **`AGENTS.md` Rust runner 段落：** 删除 `cargo test` 对 `gateway-compute-python` 与 `gateway-compute-python-impl` 的排除说明，改为 rust package 始终运行 `cargo test --workspace --locked --offline`；说明 S2a 已删除旧嵌入 Python 的 crate tests，当前 adapter 的 PyO3 行为由 backend tests 覆盖。controlled uv consumer 清单删除 `native_kernel_component.sh`。
2. **`testing-conventions.md`：** 同步删除旧 crate 的 `cargo test --exclude` 规则和嵌入解释器说明，Rust package 命令恢复完整 workspace test；controlled wrapper 清单不再列 `native_kernel_component.sh`。
3. **`p6-execution-plan.md` S2a path list：** 将 `gateway-compute-python*` 写成“复用 `gateway-compute-python` 新 adapter、删除 `gateway-compute-python-impl`”；把 `capabilities/table_access/` 标为测试支持层双实现，不写成生产 flag 接入；保留 `capabilities/canonical_row_hash/`、旧 adapter crate 与 `native_kernel_component.sh` 的删除项；记录 runner 取消旧 crate 排除和 Docker/build-input 更新。
4. **旧文档状态核对：** `internal-build-environment-handoff.md` 是 2026-09-13 已 PASS 的历史 handoff，保留其当时 `native_kernel_component.sh` 的证据内容即可；`uv-lockfile-canonical-guard-pending.md` 顶部仍称待独立审核/host-container gate，但后段记录 `2da4d71f` 实现及 gate pass，建议治理会话将其标为已完成/历史，避免其旧操作表被读作当前入口。不要机械改写 P5/P6 历史决议、review 与 handoff 中当时真实的旧实现记录。`implementation-stages.md` 的 canonical row-hash Phase 1/旧 P5 生产链叙述按其历史计划属性由治理会话判定是否加 superseded 注记。

## 8. 审核后状态与待办

1. 原 S1c 审核会话的针对性复审 1 已通过，记录为 main 本地提交 `797f499b92`。证据复核 1 的测试缺陷按报告修订并追加提交 `3b3d9c97bc`。
2. 新候选在 05 的 repository_service 定向文件、unit、Ruff 与 mypy 均通过，第 ④ 层 t1–t4 与 testdata1 正式逐值差分也通过；证据和日志见 §11。
3. 基准会话释放 04 后，S2a 在该节点按本机离线依赖与镜像策略完成候选 `3b3d9c97bc` 的 backend/worker、RS、client e2e 构建及六包权威 runner；完整结果、逐包 manifest 与日志 SHA 见 §11。
4. 本候选 04 runner exit 0，05 第④层正式逐值差分全部为零差异。两项正式证据均不经代理；runner 未设置包过滤，完整运行六包。运行与停止历史见 §10、§11。
5. DC81 解除 S2a exit 对基准整体 exit 的顺序依赖。仍需在最新 main 上整合，独立审核合并候选，并按 §13 对最终候选办理同节点逐包 manifest 判定及受影响包验证；通过后再由 owner 办理 exit tag。

## 9. F1–F5 定向复审候选与验证

本次定向修订范围为 `c7fc18ecd20b..30d67140d499`，最终代码 HEAD `30d67140d499383e855e361378bf5ef70a946edd`，Rust tree `61a76caa0e789aef1eea53a8c98d4c4c3cbb2af4`。所有验证均在节点 `ct108-gw-dms-05`（hostname `gw-dms-test-05`）的 clean、已提交 detached worktree `/home/dev/gdds-p6-s2a-review-05` 运行；开始与结束 HEAD 均为该候选。会话 `p6-s2a-impl` 于 `2026-11-01T00:35:48Z` 建立节点占用标记，验证期间持有，清理后已删除；复核时 marker 不存在。未使用代理；Python 与 Cargo 离线，Rust toolchain 1.97.0，`CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/p6-s2a-f1-f5-30d67140d4-cargo-target` 在 worktree 外并于结束清理。

| 检查 | 时间（UTC）与结果 | 日志及 SHA256 |
| --- | --- | --- |
| backend Rust extension 离线同步及 build-input 检查 | 00:42:41–00:43:08；exit 0，安装 build input 与 `vnext/rust` tree 均为 `61a76caa…` | `rust-extension-sync-30d67140d4-05.log` — `a4af6745e86ebc112c640cb690a172c0cc1769741b438b1cc92bffe294052b42` |
| F1–F5 相关 backend focused pytest | 00:43:08–00:43:14；**284 passed**，exit 0 | `focused-review-f1-f5-30d67140d4-05.log` — `c15f263459a3962a7febb659c874a1ffe8288b3af2c9359197d8b3263d381c93` |
| Rust fmt、workspace clippy 与 core focused tests | 00:43:14–00:43:45；fmt 与 clippy exit 0；`gateway-compute-core` **29 passed**，exit 0 | `rust-focused-f1-f5-30d67140d4-05.log` — `200f833453246773273be2e661a923a1b4fb46cb831276b2b05c23bb863cc8e6` |
| 五个 Python 包 Ruff 与 mypy | 00:43:45–00:43:46；backend、shared_kernel、repository_contracts、repository_client、repository_service 均通过 | `python-static-f1-f5-30d67140d4-05.log` — `2ab3ced569a0bbb5099cda3c497c34bab5d55f864af9e0cc02d79112f588cc09` |

focused pytest 覆盖 reader、property、census、rejects、types、parser、Rust adapter、conformance 与 SQL limits 测试模块。F1 中 `test_reader_single_consumer_reopen_and_close`、`test_reader_stream_error_invalidates_reader_instance`、`test_reader_checks_cancellation_at_successful_eof_commit_point` 仅以 Python 参数运行；`test_insert_column_list_permutes_to_descriptor_order`、`test_expired_deadline_fails_without_reader`、`test_cancel_probe_fails_without_reader` 继续双实现。测试支持层 `_ArrowSqlTableReader` 只将 Arrow 值转成标量，不再模拟 `ParserRuntime`。

F2 的有效文档策略固定 `max_examples=128`、`database=None`、`derandomize=True`，非法输入策略固定 `max_examples=64` 且保持相同数据库与确定性设置。差分比较完整解析结果或非法结果的 status 与 `(code, table, byte_offset)`。F3 census 映射见 §3；F4 build input 的唯一 owner 是 `vnext/scripts/check-rust-extension-build-input.sh`；F5 两个 reject 参数表对 Python 与 Rust 的同一 SQL 输入比较 status 及诊断三元组。

调试迭代发现并收敛了生成器与诊断边界问题：FLOAT32 样本边界收窄到可由两个实现共同表示；移除了并非 unsupported 的 `SET @OLD_CHARACTER_SET_CLIENT` 假设；非法变异稳定为末尾 tuple 截断与未闭合字符串；截断输入暴露 Rust EOF offset 与 Python tuple 起始 offset 不一致，Rust core 已对齐到 tuple 起点；生成的裸 `0x` 样本限制为非空，空二进制由 `x''` 覆盖。最终通过结果取自上述最终 HEAD。失败迭代日志保留于节点 `/home/dev/gdds-p6-logs/s2a/`，包括 `focused-review-f1-f5-bd1b789541-attempt1-failed.log`（SHA256 `006ef4562ef6727865c7632a23ffc1784df779c9388feb149ceeb022d3f82d3c`）、`focused-review-f1-f5-5fba4d7e46-05.log`（SHA256 `d44e3d72889ede2e2c2c8a023adabe64fc80727fffc76832c77c04256d49d501`）与 `focused-review-f1-f5-21dd69f607-05.log`（SHA256 `e59dd59cf5ebe4c777ebf56583c16c0fa1a35d770632f5809d0cdb29f41439be`）。第一次尝试的日志文件后来被重试覆盖，不作为独立证据。一次缺少 Cargo bin 路径的早期构建在 pytest 前失败，随后以正确 toolchain PATH 离线重做；该次失败不计入最终结果。

这轮只运行了 focused pytest、Rust fmt/clippy、core focused cargo test 与五包静态检查；**没有**运行完整权威 runner、`cargo test --workspace`、Compose 门禁或第 ④ 层正式真实数据差分。审核通过后按 §8 继续。

## 10. DC64 最终候选证据尝试与停止记录

候选为代码提交 `30d67140d499383e855e361378bf5ef70a946edd`，Rust tree `61a76caa0e789aef1eea53a8c98d4c4c3cbb2af4`。runner 在 `ct108-gw-dms-04`（hostname `gw-dms-test-04`）的 clean detached worktree `/home/dev/gdds-p6-s2a-runner-30d` 运行；开始与结束 HEAD 均为候选提交，运行时 worktree clean。节点 busy marker 会话 `p6-s2a-impl` 于 `2026-11-01T01:20:19Z` 建立，runner 与后续清理完成后于 `01:50:55Z` 删除。全过程未使用代理。

### 04 依赖镜像准备

CT201 上由提交 `132fc621d5711ae39ac8f1dc66f4349b2f6fe428` 构建的归档经 LAN 传输到 04。归档 tag 为 `gateway-backend-deps:lock-d054366c02fa`，完整输入摘要 `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`，归档 SHA256 `3fd859201de06757c8ce5af6dd4ad6e26d99b7439bc2edabb59035b5dd0c9ce6`，大小 `2,292,455,936` 字节。传输从 `2026-11-01T01:20:35Z` 至 `01:20:55Z`，exit 0；04 于 `01:21:31Z–01:21:48Z` `docker load`，exit 0。

机器从归档生成的期望身份 JSON SHA256 为 `b187cbf62c3e06e87d866e572d9f614ca4af2329a7b7c288930d359bad242a33`。04 比较结果为 `MATCH`：config digest `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` 与全部 19 个 RootFS DiffID 均一致；DiffID 全表见 §6。未用 `docker inspect` ID 作跨节点身份比较。

04 保留 Compose build，并在本机离线构建 backend/worker，设置 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-d054366c02fa`、`GATEWAY_DOCKER_BUILD_NETWORK=none`，未设置 `GATEWAY_COMPOSE_GATE_PREBUILT`；构建于 `01:23:19Z–01:24:08Z` exit 0。Repository Service 使用 `GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE=gateway-p2r1-repository:lock-6dc9659f0aee` 离线构建，于 `01:24:18Z–01:24:24Z` exit 0。client e2e 镜像使用 `GATEWAY_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE=gateway-repository-client-e2e-base:local` 离线重建，于 `01:24:33Z–01:24:38Z` exit 0，镜像 label revision 为候选 `30d67140d499383e855e361378bf5ef70a946edd`，锁摘要 `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954`。runner 前的只读预检确认 RS/client label 指向候选；RS build-input revision 为 `132fc621d5711ae39ac8f1dc66f4349b2f6fe428`，source-tree SHA256 为 `bfa33180295b685cb4e920449dd1087f67244ee5a296b710cd781c457f2def2a`。

成功的离线环境预检于 `01:26:27Z–01:26:55Z` exit 0：五个 Python 环境均以 `UV_OFFLINE=1` 同步；Rust selector 解析到同一 Rust 1.97.0 toolchain；backend 扩展安装 build input 与 Rust tree 均为 `61a76caa0e789aef1eea53a8c98d4c4c3cbb2af4`。此前两个只读预检命令分别因 `PATH` 未含 Cargo bin、及未在 `vnext/rust` selector 目录执行检查而失败，均发生在测试开始前且无副作用，修正后预检通过；失败日志与 SHA256 保留在 CT201 `/home/dev/gdds-p6-logs/s2a/`，遵循 DC68 补充的只读预检重试规则。

### 04 六包权威 runner

runner 于 `2026-11-01T01:28:14Z` 启动，结束于 `01:50:26Z`，起止 HEAD 均为 `30d67140d499383e855e361378bf5ef70a946edd`，最终 exit **1**。运行设置 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`TMPDIR=/home/dev/gdds-test-tmp`；没有设置 `GATEWAY_TEST_PACKAGES`，因此选择六包。代理变量、`GATEWAY_DOCKER_BUILD_NETWORK`、`GATEWAY_COMPOSE_GATE_PREBUILT` 均未传入 runner；dependency-base 预置变量保留，Compose 在节点本机离线构建。runner 自动删除 Cargo target 与 Hypothesis storage；结束预检确认它们均不存在，worktree clean、无活动 Dolt、无 Compose 项目且 port 8000 空闲，随后释放节点 marker。

runner 日志在 04：`/home/dev/gdds-p6-logs/s2a/authoritative-runner-04-30d67140d4.log`，SHA256 `7a2c5ba3374f9b8faedc5a1d449cc7934890ea824045018733d2a91c56f62d20`。每个 package manifest 的 `total_digest`：

| package | manifest `total_digest` | runner 结果 |
| --- | --- | --- |
| rust | `94e1a069bfe912f3521cbf5351da0b19a0de0d989aed13eb2835b315786a173f` | fmt、clippy、cargo test 全通过；workspace cargo test 共 152 passed。 |
| shared_kernel | `015d9342f3dc96c274c1cb4786cdedb4ad923299a2119455f671ce12c8f26091` | 243 passed。 |
| repository_contracts | `cc345ccad74864294058549c7ed0378704379ad07985bbc1c1f07bd6edb2e97b` | 152 passed。 |
| repository_client | `0ca12ede1d473cb56cbc526dacaac860edc25580ecf397dbbd5c4b5312d27f5a` | 161 passed。 |
| backend | `63bbeffa7d25c068b2451faf7cdd0f502e7bdab8b7a40c362898b2fabea672e2` | 并行 3,235 passed；串行 52 passed。 |
| repository_service | `20c89d5de3858d09682a62d52bf083e678aedd786277050dada67ffc8510c81e` | 并行 1,742 passed、1 skipped、1 failed；串行 207 passed。 |

唯一失败为 `repository_service/tests/test_uv_consume_script.py::test_uv_consume_allows_component_pytest_invocation_pattern`：测试仍断言已删除路径 `vnext/rust/gateway-compute-python/tests/test_v1.py` 存在。权威 runner 记录 `repository_service status=failed` 与 `runner_exit=1`。串行批次是同一 runner 已排定的后续步骤，完整结束且通过；没有在失败后启动新的 runner。按停止规则没有继续 05 第 ④ 层差分；因此本次未提取或记录任何 t1–t4/testdata1 输入 digest、表/值数量或差分计数，也没有真实数据内容进入日志。

### 可复核日志

以下构建和预检日志位于 CT201 `/home/dev/gdds-p6-logs/s2a/`，各自记录主机、HEAD、起止 UTC 时间与 exit；runner 主日志保存在 04：

| 步骤 | 日志 SHA256 |
| --- | --- |
| dependency-base 与源码 LAN 传输 | `b618846bd2ceaa193ddc17353e7e8a51d8fe4ba5c1f35f3b4f33ea2e372b5385` |
| 04 docker load | `8bb0812b94d310594acdd974ada1e0fdf49a77694f114601b55b349ed88edb6b` |
| 04 config digest 与 19 个 DiffID 身份校验 | `dd3d401c0ada342e056906370f7bf03f672130e456073250f82b551d8839bcb0` |
| backend/worker 离线 Compose build | `f6b6d2f0bb5911100be7a3a4f82b4999ddfe9c41eadd05d337e7d11fb507f697` |
| Repository Service 离线镜像 build | `fa64c27b775de994300318698584770f5802e17a40ad6ff00c093a83f6f4bdf0` |
| client e2e 离线镜像 build | `b6cb4247acdc98cbcffbbb77a1b1ce330efe0c06786d55705cadd16703960820` |
| 成功离线环境预检 | `a40c5d94fd8885b789255cae21b193e8207d87c50b92d0e5dc283e3699d263a4` |

## 11. S2a 证据复核 2（05 与 04 完成）

### 测试缺陷修订与定向验证

新增代码提交 `3b3d9c97bcb6d79d6c087099fbe6353f170bf68f`，只删除 `vnext/repository_service/tests/test_uv_consume_script.py::test_uv_consume_allows_component_pytest_invocation_pattern`。该用例断言的旧 `gateway-compute-python/tests/test_v1.py` 路径随 `native_kernel_component.sh` 和旧 crate 一并删除；一般的外部 pytest 路径调用由保留的 `test_uv_consume_allows_pytest_external_test_path` 覆盖。没有修改产品代码或其他测试；该提交与 evidence handoff 一起由证据复核 2 审查。

以下检查均在 05（hostname `gw-dms-test-05`）clean detached worktree `/home/dev/gdds-p6-s2a-evidence2-05`、HEAD `3b3d9c97bcb6d79d6c087099fbe6353f170bf68f` 上执行。`legacy` 链接有效；Python/Rust 离线，PATH 以 `/home/dev/.cargo/bin` 开头，Cargo target 在 worktree 外；未使用代理。

| 检查 | 时间 UTC 与结果 | 日志 SHA256 |
| --- | --- | --- |
| `tests/test_uv_consume_script.py` | 02:04:02–02:04:06；**18 passed**，exit 0 | `repository-service-targeted-file-3b3d9c97bc-retry1-05.log` — `ea4a96d163cb62410eb9475adb629de41e2eafe908e252d3d18990e94a3adce8` |
| `repository_service -m unit` | 02:04:06–02:04:45；**1,553 passed, 1 skipped**，exit 0 | `repository-service-unit-3b3d9c97bc-retry1-05.log` — `62105e484ccd595d5550847c2fbe5fcc1f0389ba7092aedad8e005eec82cd552` |
| Repository Service Ruff | 02:04:45；通过，exit 0 | `repository-service-ruff-3b3d9c97bc-retry1-05.log` — `46c306805550e68d7b6a43c9bdb1f236cda95464b4fad3f5fdfd65eed25dbee3` |
| Repository Service mypy | 02:04:45；200 source files 无问题，exit 0 | `repository-service-mypy-3b3d9c97bc-retry1-05.log` — `18ae36b4a4214abade0a2f16d8383b1b8904d085c5c90b815e896c03ba594e60` |

首次 `repository_service -m unit` focused 运行发生于 `02:02:32–02:03:11Z`，1 项失败：`test_prepare_preserves_all_lockfiles` 的子进程缺少 Cargo bin PATH，maturin 转入 Rust bootstrap 并失败。该次没有代码改动；日志 `repository-service-unit-3b3d9c97bc-05.log` SHA256 `ff7c25d9ee71e4ee833351698ff1f74aebff908fc0cdf4fd3bf458a5c8240e8c` 保留。按正确 PATH 修正环境后重跑，unit 与其他指定检查全部通过。重跑使用的外部 Cargo target `/home/dev/gdds-test-tmp/p6-s2a-reviewfix-unit-cargo-target` 已清理。

正式差分前在 05 以 `UV_OFFLINE=1` 经 `uv-consume.sh` 同步 backend，exit 0，build input 与 Rust tree 为 `61a76caa0e789aef1eea53a8c98d4c4c3cbb2af4`；日志 `backend-offline-sync-3b3d9c97bc-05.log` SHA256 `9e8d398e0c40edf31fab035e4559f239c869750618bbe97bf110d624d2f99060`。Rust parser binary 由 05 在 `CARGO_NET_OFFLINE=true` 下用 `cargo build --locked --offline --release --example table_access_parse` 构建，`CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/p6-s2a-evidence2-rust-target`；exit 0，日志 SHA256 `efcca3a8d2716b647683c37fb657b41bcc4e094d8e2c978126106f9433f2c704`。backend 与 Rust 构建 target 均在差分结束后清理。

### 第 ④ 层正式真实数据差分

工作节点 marker 会话 `p6-s2a-impl` 从 `2026-11-01T02:01:31Z` 持有至 `02:29:33Z`；开始与结束 worktree 均 clean，HEAD 固定为新候选。全程 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、未设置代理；未运行完整业务旅程或基准性能测量。比较使用 `p6_v6_parser_diff.py real`，threads `1,8`、chunk bytes `1048576,65536`，每份有 4 个 Rust 配置且 `rust_deterministic=true`。

testdata1 的两份 `sql/dbcfg.sql` 由 CT201 `heavy-dev-01` 经 LAN 传到 05 的真实数据目录；传输时间 `02:08:09–02:08:10Z`，exit 0。源与目标 SHA256 完全相同：data1 `78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f`（49,323,598 bytes），data2 `f039dd6f03a492c3f9f4fcaebf798108457d719efacbdcb1ca2c02e838f1b70b`（49,981,672 bytes）。差分前按输入 SHA256 去重，data1 映射到 t3 v1，data2 映射到 t3 v2；保留两项 testdata1 覆盖记录，只对 8 个唯一 digest 运行解析器。

| 唯一输入 | SQL bytes | 输入 SHA256 | 表数 | 行数 | 值数 | 逐值差异 / 诊断差异 |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| t1 v1 | 1,296,177 | `f8da5b9608981f91ba4cef66e593a6e2299386871d53af71ba203802140748f5` | 132 | 6,093 | 151,751 | 0 / 0 |
| t1 v2 | 1,296,079 | `8fdbd3d207b81e933da9a4812b97239737541e574e7be4777dffa4f0c80ec059` | 132 | 6,091 | 151,737 | 0 / 0 |
| t2 v1 | 14,956,886 | `7e858ce1eb9c070814b29e9799548695ee71537f812373a021c5ca9681dce027` | 216 | 97,095 | 2,134,693 | 0 / 0 |
| t2 v2 | 14,668,224 | `5ef7cc963ad5546fac73cee943a8d8c94f669ca875b4e7315527743a0480eabe` | 216 | 93,109 | 2,103,570 | 0 / 0 |
| t3 v1 | 49,323,598 | `78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f` | 199 | 268,460 | 5,922,515 | 0 / 0 |
| t3 v2 | 49,981,672 | `f039dd6f03a492c3f9f4fcaebf798108457d719efacbdcb1ca2c02e838f1b70b` | 200 | 268,466 | 6,062,168 | 0 / 0 |
| t4 v1 | 79,446,967 | `b3089d8a734651eb6dd439f11951699d176b7c1b3794bb55142d4532e8d721e8` | 319 | 436,714 | 8,683,933 | 0 / 0 |
| t4 v2 | 79,269,322 | `65358db2cfba310f145446698d6d20b580ba3b805d520bd3ff9ae33a12ad01af` | 319 | 436,794 | 8,684,781 | 0 / 0 |

覆盖别名：testdata1 data1 SHA 等于 t3 v1；testdata1 data2 SHA 等于 t3 v2。10 个覆盖输入由 8 个唯一 SHA 完成。所有解析均为 `status=COMPLETE`、`parser_exit=0`；日志仅含 alias、SHA、计数与比较状态，没有 SQL、行值或表/列名称。

差分日志在 05：`/home/dev/gdds-p6-logs/s2a/layer4-formal-diff-3b3d9c97bc-05.log`，SHA256 `da4be0d15e903016b1c74f0d093641f6b36de69d3f6d1a7f958e1259dad339bc`；用于提取、去重和摘要的 wrapper SHA256 `a9be5e67226a33d8c4a30c3d20e6e339b7e2a816ea10c216621e3ab30528e2c8`。本次抽取的临时 SQL 与 canonical 文件已删除；作为输入来源保留在 05 数据目录的两份 testdata1 SQL 不在 worktree/log 中。worktree clean，Rust targets 清理，Dolt/Compose/port 8000 均空闲，05 marker 已释放。

一次只读输入预检 wrapper 最初使用了错误的 archive 根路径并有 heredoc 结束符错误；只留下空的 mode-0700 临时目录，没有读取或提取 SQL、没有启动 parser。改用 `packages/rd-t*-*.tar.gz` 后重做成功。DC68 记录 `/home/dev/gdds-p6-logs/s2a/layer4-input-preflight-error.log`，SHA256 `9ce395aab3f24e54449e0f03555521e2cffb4ef5918e7f18e72990f8fa5b9973`。

### 04 六包权威 runner

基准会话释放 04 后，在 marker `p6-s2a-impl` 下运行新候选 `3b3d9c97bcb6d79d6c087099fbe6353f170bf68f`。候选 bundle 经 LAN 传输到 04，SHA256 `30277bd6d8cc81fc2b193a1f4a010153856e38de8a15817f1dcfc95c2a28842f`；传输记录在 CT201 `/home/dev/gdds-p6-logs/s2a/source-bundle-transfer-04-3b3d9c97bc.log`，SHA256 `527683809b338d97135ce596398222eb72e0820a17432f2d4d4b8f51dd7ccae9`。clean detached worktree 为 `/home/dev/gdds-p6-s2a-runner-3b3d9c97bc-04`，`legacy` 链接有效。起止 HEAD 均为候选提交。

04 未重新传输 dependency-base。`gateway-backend-deps:lock-d054366c02fa` 的本机 image ID 为 `sha256:d363b45a33be8d0034f49f156998753086d09c4c171e75896f1e4beab4ff49ff`，与前次加载校验后的记录一致。backend/worker 使用该镜像并保留 Compose build，在 04 离线构建；RS 用 `gateway-p2r1-repository:lock-6dc9659f0aee`，client e2e 用 `gateway-repository-client-e2e-base:local` 离线重建。三次 build 分别在 `02:43:07–02:43:08Z`、`02:43:15–02:43:20Z`、`02:43:27–02:43:31Z` 完成，均 exit 0。RS image label revision/build-input revision 均为候选提交，source-tree SHA256 为 `sha256:ee92f50f55fd9a134ddc1684aabc64fff32a32bffba680f5139cb9e692fe4015`；client image label revision 为候选提交、uv lock SHA256 为 `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954`。构建日志分别为：backend/worker `backend-worker-offline-build-04-3b3d9c97bc.log` — `1bfc2da836298a1ea7c062ab58ab5211d0553d7ee8a62f6cf42232235b4f086c`；RS `repository-service-offline-build-04-3b3d9c97bc.log` — `3626dc6d8229ebe4815a041daeef5c1bf67f979275e608ae8792b06ebea4ae31`；client e2e `client-e2e-offline-build-04-3b3d9c97bc.log` — `ffddd69bd5c59435fef604d9b5f0a6728c4e77fc19d030e46f262552e1476734`。镜像标签与候选的只读核验日志 SHA256 `1f975ae24c719310e730bdb4046b6008dde98e575b559f3c401684fbd3c87b55`。

离线环境预检于 `02:44:08–02:44:36Z` 结束，五个 Python 包经 `uv-consume.sh` 同步成功，backend 扩展 build-input 与当前 `vnext/rust` tree `61a76caa0e789aef1eea53a8c98d4c4c3cbb2af4` 一致。预检日志 `offline-env-preflight-04-3b3d9c97bc.log` SHA256 `619041ce1621d916cabff32508c97974b226ebe910b3a3dec5bc28a48856ec42` 中，四个 Rust 工具版本查询实际报告“未选择工具链”；该预检不能作为工具链版本通过证据。权威 runner 起始 manifest 在 selector 下记录 `rustc`/`cargo` 1.97.0、`rustfmt` 1.9.0-stable、`clippy-driver` 0.1.97，且 Rust fmt、clippy、workspace test 均通过。证据复核 2 已独立复算 manifest 并确认正式证据充分，无需重跑；以后查询须在 `vnext/rust` selector 目录执行并传播查询失败。此前两个只读预检命令封装错误：一处本地 SSH 命令引号不匹配、未触达远端；另一处远端没有 `rg` 可执行文件，仅读命令停止。均无副作用，改用正确引用和可用命令后完成预检/核验；记录在 CT201 `preflight-shell-quote-error-04-3b3d9c97bc.log`（SHA256 `9fa27fe6fdab586f5e72e1d96fff6f0de6ab30285ccd574b2344ea9d1b42fe22`）与 `preflight-missing-rg-04-3b3d9c97bc.log`（SHA256 `785c26232211cc343aca8cc1fc40a6b5f8c38ccd6442da84cfbffbaa59ab41fe`）。04 的 image build、image identity 与环境预检日志均位于 `/home/dev/gdds-p6-logs/s2a/`。

六包权威 runner 在 hostname `gw-dms-test-04` 的上述 clean worktree 中于 `2026-11-01T02:45:07Z–03:06:41Z` 运行，起止 HEAD 均为候选，exit **0**。环境为 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`TMPDIR=/home/dev/gdds-test-tmp`；未设置 `GATEWAY_TEST_PACKAGES`，全六包运行。代理、`GATEWAY_DOCKER_BUILD_NETWORK` 与 `GATEWAY_COMPOSE_GATE_PREBUILT` 均未传入；backend/worker dependency-base 预置选择保留。逐包 manifest `total_digest` 与结果如下：

| package | manifest `total_digest` | 权威 runner 结果 |
| --- | --- | --- |
| rust | `94e1a069bfe912f3521cbf5351da0b19a0de0d989aed13eb2835b315786a173f` | fmt、clippy 通过；workspace cargo test 152 passed。 |
| shared_kernel | `d04e73f382d2be7b83f6237c7eb47672621c4302019fee9a5e92c2c8637ae05a` | 243 passed。 |
| repository_contracts | `a9e4f8cb96755d2068229d90d3f8fe72b4f9e607905a0e33f443d99a4dd7f521` | 152 passed。 |
| repository_client | `f84540586d6f4fbc6ef0c5a223b52a9da78d32355edc2dd9915ec4a8a00d41b0` | 161 passed。 |
| backend | `502d92b4dfa6b6cc5ebb8a6a1132e72e674aa5ce2a325f8ea975588b75109de3` | 并行 3,235 passed；串行 52 passed。 |
| repository_service | `fabf123f17dbcd258cae61d8f40f7c3ed0eb1d163234ceff018af9ade0d67ad4` | 并行 1,742 passed、1 skipped；串行 207 passed。 |

完整 runner 日志在 04 `/home/dev/gdds-p6-logs/s2a/authoritative-runner-04-3b3d9c97bc.log`，SHA256 `e39675de73554a9908d2c9b1b8c3485f8278cef80c04bd40a9452dffba986ce5`。完成后 worktree clean、无活动 Dolt/Compose、port 8000 空闲；Cargo target 与五个 Hypothesis storage 路径均清理。marker 从 `02:40:49Z` 持有至 `03:07:39Z` 后释放。清理记录在 CT201 `/home/dev/gdds-p6-logs/s2a/runner-04-cleanup-and-release-3b3d9c97bc.log`，SHA256 `2c9b7791e2651cdadab6db8c8a87361c8cab35968b328c054220b9a06ff6b4dd`。

## 12. 审核与后续

证据复核 2（main `7c5cc2a49efb`）已通过：原候选 `3b3d9c97bc` 的六包 runner、05 第④层差分、日志 SHA 与该次测试删除均核对一致。DC81 解除 S2a exit 等待基准整体 exit 的约束；本 handoff 不把基准未完成或 W2 待测记作 S2a 阻塞。退出前仍需按 §13 审核最新 main 上的固定整合候选，并在原 04 来源 worktree 做逐包比较和受影响包验证。

## 13. 最新 main 整合的最小影响与证据计划（2026-11-06）

- **整合基线：** 当前候选从 main `5c867985647592c9f5d2ae1aa4be2bacc84ddf0c` 整合；该提交记录 DC83，纯文档改动，`vnext/` 与 `a89acb12ee` 相同。整合保留原 `p6-s2a` 历史及产品 V=`3b3d9c97bcb6d79d6c087099fbe6353f170bf68f`、handoff=`c3c95282bfe90f2d2fd0f2110b7be9bfa134ab38`，不 rebase、squash 或改写这些引用。固定候选须经独立审核后才运行权威测试。
- **当前可见的 vnext 影响：** 从共同基点 `49d0846d8625a8a928735c4fa0ea5126cf7ab741` 到整合基线的 `vnext/` 变化仅为 `backend/src/gateway_backend/application/checkpoints.py` 与 `backend/tests/test_operation_checkpoint_contracts.py`。backend 与 repository_service 的闭包按完整 `vnext/` tree 建模；这两项变化都进入对应闭包摘要，且 checkpoint 源码属于 backend 镜像输入。因此两包不能沿用原候选 runner，最终候选上须运行并完成本机 Compose build。DC83 只改文档，不扩展该范围。
- **04 按包判定：** 在实际门禁窗口获协调后，使用同一 04 节点、原 clean source worktree `/home/dev/gdds-p6-s2a-runner-3b3d9c97bc-04` 检出固定候选；以来源 runner log 中的六份 JSON manifest 为 source，对 `rust`、`shared_kernel`、`repository_contracts`、`repository_client` 实算 `compare`。来源 JSON 原文嵌在 04 `/home/dev/gdds-p6-logs/s2a/authoritative-runner-04-3b3d9c97bc.log`（SHA256 `e39675de73554a9908d2c9b1b8c3485f8278cef80c04bd40a9452dffba986ce5`）；复核副本位于 CT201 `/home/dev/gdds-p6-logs/s2a/evidence-check-2-review/`。每个比较结果如实记录；有任一变化/错误时保留结果并仅补运行受影响包，不改写来源 manifest，也不拿其他 worktree 的结果替代。
- **最小权威 runner：** `backend` 与 `repository_service` 因 `vnext/` Docker context 改变而运行；其余四包只有在同一 worktree compare 返回“可沿用”时才 carried。候选 runner 仅在候选审核通过后开始，设置 `GATEWAY_TEST_PACKAGES=backend,repository_service`，维持离线缓存与原 runner 环境：`TMPDIR=/home/dev/gdds-test-tmp`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`PATH` 以 `/home/dev/.cargo/bin` 开头；Rust selector/工具与 `CARGO_*`、`RUST*`、`PYO3_*` 按原实际环境核对，不带入 06 的 `CARGO_BUILD_JOBS=4`。backend/worker 使用 `gateway-backend-deps:lock-d054366c02fa`，RS 使用 `gateway-p2r1-repository:lock-6dc9659f0aee` 及 `GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES=1`，按节点已校验的 dependency-base 离线 Compose build；不设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。runner exit 非 0 时按停止规则先处理失败，不继续 carried 或其他验收。若逐包 compare 还要求其他包运行，再仅扩展相应包。
- **05 第④层证据：** 可沿用 §11 的 t1–t4 与 testdata1 正式逐值差分（8 个唯一输入、33,895,148 个值、值/诊断差异均为 0；日志 SHA256 `da4be0d15e903016b1c74f0d093641f6b36de69d3f6d1a7f958e1259dad339bc`）。整合影响只在 backend checkpoint 代码/测试与文档，不改 parser、输入或其 owning Contract；不重复跑完整真实数据差分。
- **DC81/DC83 边界：** S2a exit 不等待重建对照基准整体 exit。DC83 保留 W2 的 30 秒目标及受理到 READY 口径；CT108 可用时补测，最迟纳入 S6。该性能复核时点不是 S2a exit 条件；超时导致业务失败等正确性停止条件照常适用。

## 14. 04 整合候选收尾记录（2026-11-06；最终 runner 待完成）

- **固定候选与最小影响：** 整合提交 `38ccf8234fa559c47146ed93d054354201a4953a` 保留为已审核引用，不改写。首次 runner 暴露两条 `repository_service/tests/test_compose_build_harness.py` 单元测试受 ambient `GATEWAY_REPOSITORY_SERVICE_IMAGE` 影响：测试断言默认 tag，但权威流程使用独占 tag。修复提交 `3b037adf4caf33f65e124a34f56f12f42e529641` 以 `38cc` 为父提交，仅参数化这两个测试的 default/custom 配置并显式清理或设置环境变量；没有修改生产 helper。测试表以独立常量提供预期 tag，custom 用固定测试 tag。该提交是本节当前产品候选；后续纯文档提交不改变本节 runner 的 V。
- **38cc 首次 runner 失败记录：** 04 runner 在 2026-11-06 04:28:25Z–04:49:16Z 使用独占 RS tag `gateway-repository-service:s2a-closeout-38ccf8234fa5`，最终 `runner_exit=1`。repository_service parallel 批次为 1,740 passed、1 skipped、2 failed，失败恰为 `test_ensure_repository_service_image_rebuilds_when_labels_stale` 与 `test_ensure_repository_service_image_skips_rebuild_when_labels_match` 的默认 tag 断言；同包 serial 批次 207 passed。backend parallel 为 3,238 passed，backend serial 52 passed。因整次 runner 非零退出，所有包的这些结果均不作为 V 或 carried 来源。权威日志 `/home/dev/gdds-p6-logs/s2a/closeout-38ccf8234fa5/run-20261106T042819Z-1731032/authoritative-runner.log` SHA256 `c3438c9a45669e6cfc8258ca712dd5093be2c61ce1028c684ea7c27e9841263b`；operation log SHA256 `7ef5cf4123a271f71da53c54d9823e88400ec845561f24e13ee73838b42b581c`；SSH transcript SHA256 `d7f0e6456257e3328b2398d3172404330312b305c99b47c63ce6db31579a4a3b`。旧审核 wrapper 已保存在同一 38cc 证据目录 `closeout-wrapper-04-reviewed.sh`，SHA256 `2935acf2ec7e312201d0509a2708635ee9be3e0093417017a6a4d9d1d02d09d0`。
- **测试修复的定向验证：** 提交 `3b037ad` 在 06 的 clean worktree `/home/dev/gdds-p6-s2a-testfix-3b037ad-06` 上，focused `tests/test_compose_build_harness.py` 在外层设置独占 tag `gateway-repository-service:s2a-closeout-3b037ad` 时 45 passed；五个 Python 包的 `ruff check .` 与 `mypy` 均通过。日志目录 `/home/dev/gdds-p6-logs/s2a/closeout-3b037ad/06-validation-20261106T045624Z-23250/`，operation log SHA256 `3bd29ab7bf286d040def026b757ff973c4b12794da362b06f54e0a3d213b9229`；起止 HEAD 均为 `3b037adf4caf33f65e124a34f56f12f42e529641`，结束时 worktree clean。命令上下文：`UV_OFFLINE=1 CARGO_NET_OFFLINE=true TMPDIR=/home/dev/gdds-test-tmp`；focused 命令为 `env GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:s2a-closeout-3b037ad ../scripts/uv-consume.sh -C . run pytest -q tests/test_compose_build_harness.py`；五包分别运行 `../scripts/uv-consume.sh -C . run ruff check .` 与 `../scripts/uv-consume.sh -C . run mypy`。`GATEWAY_REPOSITORY_SERVICE_IMAGE` 只为 focused 调用设置，Ruff/mypy 没有使用该变量。
- **当前 04 compare 与 V 选择：** 在原 04 source worktree `/home/dev/gdds-p6-s2a-runner-3b3d9c97bc-04` 检出 `3b037ad`，worktree clean；保留首轮占用 session `p6-s2a-closeout-38ccf8234fa5`，没有重新 acquire。原 runner log 中的六份 source manifest 仍直接来自 §11 记录的 SHA `e39675de73554a9908d2c9b1b8c3485f8278cef80c04bd40a9452dffba986ce5`。本轮 compare 结果为 Rust“可沿用”；shared_kernel、repository_contracts、repository_client 为“运行”，唯一变化是当前离线 Dolt 输出 `unable to query latest released Dolt version`，来源 V 则输出发现 2.6.0 的提示，两侧二进制均为 2.1.11。manifest 将完整输出建模为环境输入，因此按变化运行，不改变缓存、联网状态或摘要器。backend 和 repository_service 因完整 `vnext/` context 变化运行。compare operation log SHA256 `a3770d77cf4f04ebd62b13f675503e1124c5b3858f6b7c0ca795756ce1106c5b`；SSH transcript SHA256 `283beeb8dbce1e0ba919e1808f173c67c3be060cf382ce1f83c7c267ceede904`；结果目录 `/home/dev/gdds-p6-logs/s2a/closeout-3b037ad/compare-20261106T050156Z-2117740/`。
- **3b037ad 权威 runner（进行中）：** reviewer 已审核 test-only 修复及 06 定向证据，并放行在 04 运行五个 Python 包。新 wrapper SHA256 `301240491c0b004b80247fda6a0e6bcf04566ffb4cd19b0c2708b84f5065a7b5`，仅更新 candidate、专属 RS tag 与日志目录；原 session 标记保持不变。bundle SHA256 `59cb7e922356813e1a5a1c78c5dc19388bfd9befdabb612903f9f1297054a0d0`。RS tag `gateway-repository-service:s2a-closeout-3b037ad` 使用已校验的 `gateway-p2r1-repository:lock-6dc9659f0aee` 离线构建；`repository-service-image-identity.txt` 记录本机 image ID、标签及全部 RootFS DiffID，文件 SHA256 `6ff4c19035f0f98c285707fa42c607527093613f67b056d719a4b7d384c401d5`。runner 于 05:02:05Z 在 04、HEAD=`3b037ad` 开始，包选择为 `backend,repository_service,shared_kernel,repository_contracts,repository_client`。当前日志 `/home/dev/gdds-p6-logs/s2a/closeout-3b037ad/run-20261106T050200Z-2118255/authoritative-runner.log`；最终 exit、日志 SHA 和清理状态待 runner 完成后补录。在此之前不将其表述为通过，不继续其他验收。
- **原证据与最终绑定：** 05 的 parser 第④层逐值差分仍沿用 §11 原证据，不重跑。最终文档 HEAD 固定后，需在同一 04 原来源 worktree 再对六包计算最终 manifest compare，并核 repository_service image identity；Rust 若仍匹配原 3b3d 来源则沿用，变化则按结果运行。04 worktree 与占用标记保留到最终绑定审核通过。main 后续纯文档提交 `9277e87896` 不改变 `vnext/`，整合和最终 HEAD 的绑定结论仍以实际 compare 记录为准。

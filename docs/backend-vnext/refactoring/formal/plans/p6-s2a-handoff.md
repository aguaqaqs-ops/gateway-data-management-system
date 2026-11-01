# Phase 6 S2a implementation handoff

状态：**F1–F5 定向修订已完成，待原 S1c 审核会话针对性复审**。本文件只绑定 focused/debug 结果；完整权威 runner、Docker/Compose 门禁与第 ④ 层正式真实数据差分按 DC64 在代码审核通过后执行。

日期：2026-11-01

## 1. 候选与授权边界

- 分支：`p6-s2a`；起点为合入 S1c 与 backend image 任务的 merge commit `49d0846d8625a8a928735c4fa0ea5126cf7ab741`。原代码候选 `c7fc18ecd20bb8455a8a54ba3a090e468a42d785` 经 main 本地审核提交 `41844c4958554f0d8c68e41702783b86469d526a`（`p6-s2a-code-review.md`）给出 F1–F5 定向修订；当前候选为 `30d67140d499383e855e361378bf5ef70a946edd`。
- Kickoff 初稿 `30de9c1cae` 未改写；按审核意见与 DC72 追加确认提交 `e9b3e04de98769faf6a66e93bcdde0b3e7958979`。
- O2 是首个产品提交 `229845a6c97786c4c8384607733bff2363b4a62f`，只修改 Python 参照实现和现有 reject 参数表；之后实现 Rust parser/adapter。原实现候选为 `c7fc18e`；本次追加 F1–F5 测试修订及未闭合 INSERT 元组诊断偏移对齐，最终代码候选为 `30d67140d4`。所有修订均追加提交，没有改写审核引用的提交。
- Owner 已在 main `0749edb8e6` 以 DC72 确认 kickoff。没有推送、打 tag 或改写已审核提交。S2a exit 与合入 main 等基准 exit 后办理。
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
| ④ t1–t4 v1/v2 与 testdata1 真实值逐项差分 | **未运行**。依 DC50/DC72，审核通过后全部在 05 运行；testdata1 与 t3 按输入 digest 去重并保留覆盖记录。只解析差分，不跑完整业务旅程或性能测量。 |
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

## 8. 审核后待完成事项

1. 原 S1c 审核会话对 `c7fc18e..30d67140d4` 的 F1–F5 修订、未闭合 tuple offset 对齐、测试归属表与本 handoff 做针对性复审；审核发现再追加新提交，不改写既有提交。
2. 复审通过后，在最终候选 `30d67140d4` 按 DC64 跑完整六包权威 runner。Dockerfile 已变，且 Cargo.lock 变化：在 04 空闲且不占用基准最终 runner 时，本机使用 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-d054366c02fa`、`GATEWAY_DOCKER_BUILD_NETWORK=none` 重建 backend/worker 并执行 Compose 门禁；保留 Compose build，不设 `GATEWAY_COMPOSE_GATE_PREBUILT`。缺少基础镜像或依赖缓存时先停下预填充。
3. 在同一最终候选上于 05 做第 ④ 层 t1–t4 v1/v2 与 testdata1 逐值差分；按输入 digest 记录 testdata1/t3 去重。t1–t4 全在 05；不使用 ct108，不跑完整业务旅程，不让真实 SQL/值进入 Git 或日志。
4. 04/05/CT201 按各自用途单飞；所有节点先确认连接和 busy marker。正式 runner/真实数据证据不经代理。审核先行、证据后补；runner exit 非 0、缓存缺失或身份不符时按 AGENTS 停止规则处理。
5. S2a exit tag 与合入 main 等基准 exit 后由 owner 办理。

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

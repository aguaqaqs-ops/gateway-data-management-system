# Phase 6 S2a kickoff：SQL 解析器

- **状态：** 已确认（DC72；repository owner，main `0749edb8e6`）。
- **日期：** 2026-10-31。
- **分支与基线：** `p6-s2a`，从 S1c 合入 main 且包含 backend 镜像依赖层调整的 merge commit `49d0846d8625a8a928735c4fa0ea5126cf7ab741` 创建。重建对照基准仍测量 `p6-s1c-exit` 本身。
- **审核：** 由原 S1c 审核会话负责 S2a 代码审核与证据复核。
- **并行关系：** S2a 开发、审核以及所需的 05 差分可与重建对照基准正式测量并行；S2a exit、tag 与合入 main 在基准 exit 之后办理。

## 1. 目标与冻结边界

S2a 把 Python 参照 SQL parser 的实现替换为 V6 原型发展而来的 Rust parser adapter，完成五层差分与旧 Rust 扩展清理。S1b 已冻结的解析语义、diagnostic code、table/statement offset 与下游行为不随实现切换而改变。S2a 只在测试支持层提供双实现入口；生产 `parse_sql()` 与 worker 路由继续使用 Python，不增加部署 flag，也不做 shadow 执行。生产 feature flag 在 S2b 随上传侧数据路径合并时引入，S6 删除。

阶段依据为 [p6-design.md §7](p6-design.md#7-s2a-sql-解析器)、[p6-execution-plan.md 的 S2a 与 §8](p6-execution-plan.md)、[DC46–DC52、DC55、DC62、DC64、DC66–DC72](p6-s0-owner-decisions.md；DC72 当前在 main `0749edb8e6`)、[V6 原型报告](p6-v6-parser-prototype-report.md)、[Rust Safety and Performance Policy](../policies/rust-safety-and-performance-policy.md)。

## 2. 当前设计与代码核对

### V6 原型现状

`vnext/rust/gateway-compute-core/src/table_access/` 已实现 SQL 扫描、CREATE TABLE 与 INSERT 头解析、mysqldump 样板语句 allowlist、Shared Kernel 类型和值转换、JSON 迭代校验、按 INSERT 元组分块并用 Rayon 并行解析，以及可逐值比较用的 parse canonical 编码。它接收 SQL bytes 和调用者提供的固定 Rayon pool，不访问文件系统；入口尚未接入 PyO3。

V6 验收已通过：第 ① 层 118 例与 t1–t4 的 v1/v2 共 8 份真实 SQL（1,733 张表、约 33.9M 个值）逐值差异为 0；1–32 线程及 1 B–1 MiB chunk 的输出逐字节一致；ct108 上 2× t4 单线程约 1.25 s、32 线程约 0.28 s。该结果是原型证据，不是 S2a 当前 HEAD 的验收结果，也不要求在基准测量期间使用 ct108。

原型与 §7 对照后，S2a 仍须补齐：

- 与 Python `ParserRuntime` 一致的完整诊断列表、消息、诊断预算/截断、同一张表多处错误，以及按超限元组定位的 row-budget offset；差分只要求 diagnostic code、table 和 statement offset 相同，消息文本不要求两实现一致。
- 第 ③ 层负例与预算语料、第 ② 层 Hypothesis 差分，以及现有 SQL parser 用例的双实现参数化。
- PyO3 adapter：`py.detach` 长调用、取消与 deadline、Arrow C Stream、core 与 adapter 两个 panic 边界。
- `Utf8`/`Binary` 32-bit offset 的 2 GiB 上限处理：使用 large Arrow 变体或有界分批输出，并测试边界；不允许因物理 offset 上限默默改变现有资源 Contract。
- 按 S1b §5.5 实现冻结语义，包括 JSON 最大深度 100、非有限值与孤立代理拒绝、BIT/`_binary`/转义/类型注释等已确认行为。

V6 报告中“完整 parser”缺口不代表允许在 S2a 调整解析语义。第 ④ 层值比较严格按类型化值相等；并行/分块确定性比较规范输出字节。

### S1b 参照语义与待确认项

S1b 与 DC62 已确认的语义按 p6-design.md §5.5 和 DC62 第 2 项执行：BIT 十进制字面量按十进制解释；只在二进制列接受 `_binary`；保留 `\%`、`\_`；忽略列类型中的注释；拒绝 NaN、Infinity、孤立代理；JSON 深度超过 100 稳定报 `SQL_VALUE_ILLEGAL`；零日期继续拒绝。FLOAT binary32 单次舍入由 Shared Kernel 负责，S2a 不再修改。

**O2 已按 DC72 确认：** JSON 数值解码后非有限（包括 `1e400` 这类溢出为 `inf` 的值）按表级 `SQL_VALUE_ILLEGAL` 拒绝。这是 DC62 第 2 项 e 的一致性修正，不是新语义。先在 Python 参照实现中单独提交修正，再由 Rust 实现对齐；第 ④ 层差分记录真实数据中此类值的出现次数。

截至本次对照，未发现其他会改变 S1b 语义的新增项。实现前若差分复核发现新的参照行为与 Contract 不符，先登记并交 owner，不通过“对齐 Python”扩大 S2a 语义。

**Parser L3 已按 DC72 确认：** 保留 V6 已实现并验证的 INSERT 元组分块，作为 SQL parser 专属的表内并行；只使用 adapter 的同一个共享池，不嵌套建池。row-budget offset、同表多处错误的诊断顺序在不同 chunk size 下必须相同，列入第 ③ 层及 Rust 确定性测试；不把 L3 扩展到其他 kernel。

DC71 记录的非 operator 启动时过期 RUNNING step 可能触发 `BLOCK_STARTUP_FATAL`，属于 S1c 之前的 worker runtime 遗留 O1，交后续维护；它与 SQL parser 无关，不并入 S2a。

## 3. 旧实现调用方与清理范围（DC52）

现有 `canonical_row_hash` 在生产 journey 中没有 consumer；P5 exit review 将其列为不可达。S2a 删除其实现和测试，不迁移旧实现或建立兼容入口。清理时保留仍有独立职责的通用 ArtifactStore、ArtifactRef、comparison 原型与 Table Access Contract 测试。

| 当前实现/引用 | 当前用途或调用方 | S2a 处理 |
| --- | --- | --- |
| `vnext/backend/src/gateway_backend/capabilities/canonical_row_hash/`（`__init__.py`、`contracts.py`、`compute.py`、`canonical_row_hash_ipc.py`） | 只由 canonical-row-hash 专项测试调用；生产代码没有 journey 调用 | 删除整个 capability。 |
| `vnext/rust/gateway-compute-core/src/pipeline.rs`、`lib.rs` 旧导出及其旧 row-hash 模块：`arrow_extract.rs`、`arrow_mapping.rs`、`contract.rs`、`errors.rs`、`request.rs`、`result.rs`、`row_encode.rs`、`schema_digest.rs` | 实现 canonical row-hash 计算/结果，不被 V6 `table_access` 使用 | 删除旧 pipeline 和只服务该 pipeline 的模块、API、单元测试；保留 `comparison/`（V1）与 `table_access/`（V6）。`records.rs` 是 S5 comparison-record Parquet reader，属独立现有能力，保留。 |
| `vnext/rust/gateway-compute-core/tests/` 的 row-hash、schema、request、matrix、decimal 等旧集成测试及 `tests/support/` | 覆盖旧 request/envelope 与 compute pipeline | 按 DC52 删除，不迁移为新 parser 证明；新 parser 的 Rust core 测试归 `table_access`。 |
| `gateway-compute-python-impl` crate 的 `adapter.rs`、`errors.rs`、`kernel_component_tests/`；`gateway-compute-python` 的旧 facade、exceptions、PyO3 entrypoint 与 Rust 内嵌解释器测试（含 `adapter_errors.rs`） | 旧 PyO3/Arrow row-hash adapter；旧测试要求 Rust 内嵌 Python | 删除 `gateway-compute-python-impl` crate、旧实现与旧测试，不迁移。复用 distribution/crate 名称 `gateway-compute-python`，但对外提供全新的 parser adapter 接口，不保留旧 API symbols。 |
| `vnext/scripts/native_kernel_component.sh` 及其 wheel/ABI/source `.so` smoke | 专门构建和验证旧 native kernel | 删除脚本；移除其活跃操作文档引用。 |
| `vnext/fixtures/golden/canonical-row-hash/`、`vnext/fixtures/schemas/artifacts/v1/canonical-row-hashes-artifact.schema.json`、`vnext/fixtures/vectors/compute/canonical-row-hash/v1/` | 旧 boundary 的 golden、artifact schema 与 vector 导航 | 删除旧格式专属 fixtures；不把它们改造成 parser golden。新 SQL parser 差分 fixture 继续归 Table Access。 |
| `docs/backend-vnext/refactoring/formal/contracts/canonical-row-hash-compute-boundary.md` | 旧 compute API、Arrow map 与 artifact boundary 的 Contract | 删除该 Contract；从 ADR 0001、Fixture Oracle and Conformance、Shared Canonical Encoding 等现行文档移除失效链接/旧 boundary 表述。 |
| `vnext/backend/tests/test_architecture.py`、`architecture_baseline.py`、`tests/support/import_rules.py`；`vnext/rust/gateway-architecture-check/` | 当前显式列出 `canonical_row_hash` owner、`gateway_compute` extension zone、双 adapter crate、CDYLIB/module shape 与旧源码路径 | 删除旧 owner/baseline 条目；按新单 adapter + Table Access 归属更新静态规则和 fixture。保留通用安全约束（无 unsafe、core 不依赖 PyO3、无 Python row materialization、extension 无额外 hook 等），不得因删除旧代码而削弱。 |
| `vnext/backend/Dockerfile`、`Dockerfile.dependency-base`、`pyproject.toml`/`uv.lock` | maturin 当前编译 `gateway-compute-python`，dependency-base 为两个旧 crate 复制 Cargo manifest/stub，backend 锁定路径依赖 | 基于 `p6-backend-image-exit` 的新 Dockerfile 调整 maturin 单一目标、stub/manifests 与安装配置，构建出的镜像始终含新 adapter。若 distribution 名称/路径或锁定依赖变化，同步更新 `pyproject.toml` 与 `uv.lock`；按 AGENTS 更新 Dockerfile 中 `UV_LOCK_SHA256`（若 repository_service 锁也变化）。 |
| `vnext/scripts/run-tests.sh`、`test_input_closure.py`、`check-rust-extension-build-input.sh` | runner 当前排除两个旧 crate 的 `cargo test`，backend 强制重装旧 Python package；build-input 检查导入旧 module | 去掉两个旧 crate 的 cargo test 排除；新 adapter 的 pytest 检查、`__build_input__`、当前扩展强制重装与 closure paths 同步更新。pytest 继续测试已安装的扩展，Rust 测试不嵌入 Python。 |
| 活跃操作文档 `AGENTS.md`、`docs/backend-vnext/testing-conventions.md`、`p6-design.md` §2.2/§7 与 `p6-execution-plan.md` S2a 路径清单 | 仍将 `native_kernel_component.sh` 或旧 crate 排除/重装描述为当前流程，或把旧实现写成当前代码事实 | S2a 更新 `p6-design.md` §2.2/§7 的当前事实与失效 Contract/ADR 链接；AGENTS.md 和 testing-conventions.md 的建议条文写入 handoff，交治理会话同步；execution plan 路径清单的修改也在 handoff 中提出，由治理会话办理。P5/P6 历史审核、handoff、决议记录保留其历史事实，不做全库机械改写。`internal-build-environment-handoff.md` 与 `uv-lockfile-canonical-guard-pending.md` 有历史脚本引用，先按文档状态确认是否仍为操作说明，不把历史证据当作活跃 caller。 |

实施前再以 `git grep` 扫描上述标识，核对删除后没有运行时代码、测试或活跃文档继续指向旧实现。`Cargo.lock`/`uv.lock` 只在依赖图实际变化时按显式依赖更新流程修改；不得为保留旧包/API 增加 alias。

## 4. 新 PyO3 adapter 与差分开关

- Rust core 保持纯 Safe Rust：只接收 SQL bytes、预算与小型 invocation metadata，返回表描述、诊断和 Arrow 数据；不读写文件、环境变量或业务 workflow，不依赖 PyO3。第一方代码禁止 `unsafe`、nightly、raw Arrow C pointer 与手写 Python C API。
- 新 adapter 使用 `pyo3-arrow` 公共 safe API，以 owned Arrow C Stream 传递输入/输出；不把逐行 Python object/list/dict 作为 bulk path。长 parse 调用放在 `py.detach` 中，adapter 只在检查 Python cancellation signal 所需的短边界重新 attach。
- `ParserInvocationContext` 的取消和 monotonic deadline 必须传到 core parser checkpoint，保持 `PARSER_CANCELLED`、`PARSER_TIMEOUT` 与偏移语义；core 不持有 `PyObject`。adapter 在进入 detach 前绑定调用上下文，并以有界间隔检查取消。需在 adapter 设计中记录 Python signal 到 Rust 线程安全标志的具体 safe bridge 及检查延迟。
- 在 core 公开入口捕获 parser panic 并转为稳定 parser diagnostic；adapter 在 FFI 边界再次兜住 panic，转为稳定 diagnostic/error envelope，保证 unwind 不跨语言边界。两个边界分别测试。native abort、segfault 与 OOM/allocator termination 不伪装为诊断，交给现有 Operation Runtime lease/recovery 处理。
- Rayon pool 是 S2a adapter 的进程内共享有界资源：由调用方在初始化时传入 N，首次创建后固定大小并在后续 parser/kernel 调用间复用；adapter 每次调用不得另建 pool 或嵌套建池。测试默认 N=1，一致性测试在分别以 N=1 与 N 初始化的进程中比较结果。worker 启动接线及部署配置 N、M 留给 S2b；S2a 不加入部署配置。
- **差分开关形式（已确认）：** 仅在测试支持层提供显式 `implementation="python" | "rust"`/双实现参数化入口；backend 公共 `parse_sql()` 与 worker 生产路由仍固定 Python。这个 test-only 开关不作为部署环境变量，不做 shadow production 执行，也不改变 production feature flag 状态。扩展 pytest 直接导入已安装的新 adapter。adapter 的 distribution/crate 名称沿用 `gateway-compute-python`，但提供全新接口；删除 `gateway-compute-python-impl` 与旧 API symbols。

## 5. 五层语料与差分验收

解析结果规范形按 V6 `gateway.table-access.parse-canonical` 版本化格式比较：表描述、列声明、主键、行数、类型化值与行顺序均纳入；可读表按列/行逐值相等。错误路径按 diagnostic code、table 与 statement offset 比较，message 文本不要求跨实现一致。真实数据日志只写位置、类型、计数和摘要，不打印值或 SQL。

| 层 | S2a 计划 | 执行位置与频次 |
| --- | --- | --- |
| ① 现有用例双实现参数化 | `test_table_access_sql_parser.py`、`test_table_access_sql_rejects.py`、`test_table_access_sql_limits.py`、`test_table_access_sql_types.py`、`test_table_access_sql_reader.py`、SQL conformance 与现有 golden 对 Python/Rust 各跑一遍；原用例成为差分用例 | backend focused/普通 CI |
| ② Hypothesis | 按 mysqldump 结构生成 statement、引号/注释/转义、类型化 literal 与 S1b 边界；两侧比输出或诊断；固定/受控随机设置，不写入 worktree `.hypothesis` | 普通 CI 有限样本，另有增样本调试运行 |
| ③ 负例与预算 | 截断/引号未闭合、非法类型和值、超长字段/tuple、表/行/source 预算、diagnostic 截断、超限元组 offset；两侧以同一 Contract 诊断失败 | 普通 CI |
| ④ 真实数据 | t1–t4 的 v1/v2 与 testdata1，逐表逐列逐值；V6 报告称 testdata1 与 t3 是同 SQL，先按输入 digest 核验避免重复跑而漏记覆盖；按 DC50 补充全部在 05 | 每次差分取证一次；不跑完整业务旅程 |
| ⑤ 普查覆盖的格式类别 | G2 census 记录到的 SQL 形态各有合成样本，保证已见格式都有覆盖 | 普通 CI |

差分验收还包括：五层全通过；t1–t4（含 v1/v2）逐值差异为 0；N=1 与 N、各 chunk size 的输出逐字节相同。完整解析器诊断按 Contract 覆盖消息、同表多错与预算截断，但消息文字跨 Python/Rust 不作为等价条件。性能不设 CI 门槛；不参与 ct108 基准测量，不以 V6 吞吐代替 S2a 正确性验收。

### 测试归属：每个不变量一个权威 owner

| 不变量 | 唯一权威测试 owner | 其他位置的职责 |
| --- | --- | --- |
| Table Access 对外语义、类型化输出、诊断码/table/offset 与双实现差分 | backend Table Access SQL 现有 parser/reject/limits/conformance 测试，按单一测试参数表运行两实现 | Rust unit tests 只测 core 内部边界，不另造同一业务语义的平行 oracle |
| Rust parser 在畸形/预算输入下保持有界、结果排序与 chunk/线程确定性 | `gateway-compute-core` 的 `table_access` Rust 测试 | pytest 只做已安装 adapter smoke/差分；row-budget offset 与同表多错顺序在 chunk size 改变时保持一致 |
| PyO3 detach、owned Arrow C Stream、cancel/deadline bridge、FFI panic envelope 与 `__build_input__` | backend 新 adapter pytest 文件（拟 `test_table_access_rust_adapter.py`） | Rust adapter 不内嵌 Python 测试；core panic 边界由上一行 Rust owner 单独验证 |
| adapter 进程内共享有界 pool 一次创建并跨调用复用 | backend 新 adapter pytest 的 pool reuse 测试（N 默认 1） | Rust 测试负责 parser 确定性；S2b 的 worker 启动接线测试归 S2b |
| core/adapter 依赖方向、无 unsafe、无 row materialization 与 extension 构建形状 | `gateway-architecture-check` / backend `test_architecture.py` 对应单一 architecture owner | feature/diff 测试不代替静态边界证明 |

如果同一 Contract 不变量已经由现存测试 owner 覆盖，修改其参数表，不新增以修复轮次或分层编号命名的重复证明。

## 6. 依赖、镜像与节点方案

- backend maturin 构建改为 S2a 新 adapter，基础为 merge commit `49d0846d86` 中 `p6-backend-image-exit` 后的新 `vnext/backend/Dockerfile`。同步检查 `Dockerfile.dependency-base`、Compose build args、backend package path、`check-rust-extension-build-input.sh` 和 build-input closure。
- 若 `vnext/rust/Cargo.lock`、`rust-toolchain.toml`、`backend/pyproject.toml`、`backend/uv.lock`、`backend/.python-version` 或 Rust base image 变化：在 CT201 clean worktree 执行 `vnext/scripts/build-backend-dependency-base.sh --save <archive>`，生成 `gateway-backend-deps:lock-<12>`；通过批准的 LAN 方式传给实际节点并 `docker load`。handoff 记来源提交、完整输入摘要、tag、config digest、全量 RootFS DiffID、archive SHA256 与构建/传输时间。跨节点按 config digest + 每个 DiffID 校验，不比较 inspect ID。
- 当前 `gateway-backend-deps:lock-c668cef8e47e` 仅确认在 CT201 与 04；S2a 首轮 05 需要它时，先从开发节点或 04 经 LAN 传输并校验。不得假定 05 已有镜像。若 lock inputs 变化则不能沿用此 tag，须重新构建并传输。
- 在 05 与 04 的 backend/worker 本机 Compose build 设置 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=<lock-tag>`、`GATEWAY_DOCKER_BUILD_NETWORK=none`；保留 Compose build，不设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。由于 Dockerfile 改动，最终 HEAD 必须重建 backend/worker 并运行相应 Compose 门禁。
- Rust 依赖精确 pin，只有需要时显式更新 `Cargo.lock`/`uv.lock`。依赖或镜像变化先 CT201 获取并 LAN 预填充，禁止测试节点访问公网。04 runner、carried 与真实数据取证不经代理；05 调试构建若确需受限代理，只放行必要主机、不传凭据、用后停止，并在 handoff 记录放行范围、起止时间与用途，结果不作证据。

## 7. 节点、预编码基线与阶段证据

### 节点分工与单飞

- 开发主机只改代码/文档，不运行测试、cargo、Dolt 或 Compose；CT201 只用于获准的依赖制品/dependency-base 构建，不跑测试。
- 05（`ct108-gw-dms-05`）是 S2a 的主要调试与真实数据节点；t1–t4 第 ④ 层差分全部在 05。基准如需 05 的 t1 预热或工具验证，双方先协调，不并用。
- 04（`ct108-gw-dms-04`）只在节点空闲且基准最终 runner 不需要时运行 S2a 权威 runner。ct108（`ct108-gw-dms`）在基准正式测量期间由基准独占，S2a 不使用。
- 每个节点整机单飞。任何将在测试节点触及 Dolt、Compose、pytest 或 cargo 的命令前，先执行 `mkdir /home/dev/gdds-node-busy.d`；失败即视为占用，等待、不抢占。成功后在目录写 owner 文件（会话名、用途、开始时间），运行与清理完成后删除 busy 目录。长时间未释放报告 owner。只读检查不受此锁约束。
- 连接测试节点前执行 `ssh -o BatchMode=yes <alias> 'echo OK'`。测试在节点 clean、已提交 worktree 运行；linked worktree 预先建立 `legacy` 符号链接。TMPDIR 使用 `/home/dev/gdds-test-tmp`，日志与真实数据输出在 worktree 外；不写 `/tmp/pytest-of-root`，真实数据不入 Git。

### 编码前合入组合预检

依据 S1c 终审 §3.2，在任何产品代码编辑前，于 05 的 clean worktree、HEAD `49d0846d86` 完成合入组合 focused 基线。首次运行已完成 backend 的七个 S1c focused 文件与 SQL parser focused 文件：471 passed、4 failed、1 warning；4 项均因 backend 启动真实 Repository Service 时该 worktree 缺少 `repository_service/.venv` 而失败，不是被测代码断言失败。首次失败日志保留在 `/home/dev/gdds-p6-logs/s2a/baseline-49d0846d86-20261031T221122Z.log`，闭合文件 SHA256 为 `3bf3b9f48aa3a1b5f09dbb6a81d9c6f0295f8ebbbf39963bf2ba811bb5d910ee`。审核报告 §4 确认这是调试环境准备遗漏，DC68 重做次数限制不适用于该调试运行。按 owner 后续指令，重跑前先以 `UV_OFFLINE=1` 通过 `uv-consume.sh` 同步 Repository Service 环境，再仅重跑以下 4 项和 rust 包三步：

1. 在 `/home/dev/gdds-p6-s2a-baseline-05` 的 `vnext/repository_service` 中以 `UV_OFFLINE=1` 执行 `../scripts/uv-consume.sh -C . sync`，保留已存在的 backend 环境；随后在 backend focused suite 中只重跑首次失败的 4 项：`test_submit_upload_and_import_wire_mapping_against_live_repository`、`test_operator_abort_evidence_rejects_unknown_repository_operation`、`test_operator_abort_import_rejected_via_recovery_port`、`test_await_import_result_consumes_matching_terminal_after_repository_restart`。首次失败日志不得覆盖。
2. 通过后运行权威 runner 的 `rust` 包，使 fmt、clippy、cargo test 三步全部执行；cargo test 仍按 S2a 前规则排除 `gateway-compute-python` 与 `gateway-compute-python-impl`，不运行六包完整 runner。设置 `CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/p6-s2a-baseline-cargo-target`（worktree 外）、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，并遵守 toolchain/PATH 约束。

该次重做使用节点占用会话名 `p6-s2a-impl`；运行前确认 05 空闲并成功取得 `/home/dev/gdds-node-busy.d`，在 owner 文件记录会话、用途与 UTC 开始时间。命令输出另存 `/home/dev/gdds-p6-logs/s2a/` 下的新日志，记录 hostname、起止 UTC、起止 HEAD、命令和 runner/命令 exit code；清理 worktree 外 cargo target 并移除节点占用标记。该基线是调试运行，不作为阶段正式证据。日志均保存在 worktree 外。该预检通过后再开始产品编码；若重跑的 4 项或 Rust 任一步失败，则停止并交 owner 处理。

### 审核与正式证据（DC64）

1. 代码收敛后交候选：focused 测试、五个 Python 包的 ruff 与 mypy、Rust fmt/clippy、改动范围内的调试差分与 handoff 代码部分。候选交原 S1c 审核会话做代码审核与修订复审。
2. 代码审核通过后，在最终候选运行一次完整六包权威 runner；若 04 空闲且不影响基准最终 runner，则在 04 运行。runner 含 backend Compose 旅程；依 Dockerfile 变化重建 backend/worker 并执行相应容器门禁。
3. 同一最终候选上运行第 ④ 层正式解析器逐值差分（t1–t4 v1/v2、testdata1；均在 05），日志不输出真实值。按 DC64 审核先行、正式证据后补：完整 runner 与第 ④ 层正式差分均在代码审核通过后执行。修订若影响差分输入/解析输出则重跑受影响差分；无法给出可审核的影响映射时整档重跑。证据复核由同一审核会话执行，不重复审代码。
4. 权威 runner 逐包按 manifest 运行或沿用；来源必须是 clean worktree 上实际通过的权威 runner，且整次 runner exit 0。backend/Rust 修改使对应闭包重变时在当前候选实际运行。完整 handoff 记录节点、HEAD、hostname、时间、exit、日志 SHA256、逐包来源、dependency-base 身份/缓存来源、镜像重建理由、数据差分范围与摘要。
5. 调试与取证分开。focused/debug 结果不代替正式 runner；阶段 exit 的 tag、合入 main 等待重建对照基准 exit 后由 owner 办理。

## 8. DC72 确认记录

Owner 于 main `0749edb8e6` 确认本 kickoff（DC72）：

1. O2 按 §2 执行：JSON 数值解码后非有限值（含 `1e400` 溢出）由 Python 参照实现先单独修正为表级 `SQL_VALUE_ILLEGAL`，随后 Rust 对齐；第 ④ 层统计出现次数。
2. S2a 不改 S1b 冻结语义。保留 V6 parser 专属 INSERT 元组 chunking L3，row-budget offset 与同表多错顺序跨 chunk size 一致；不扩展到其他 kernel。
3. 复用 distribution/crate 名称 `gateway-compute-python`，删除 `gateway-compute-python-impl`，对外提供全新 parser adapter 接口，不保留旧 API symbols。
4. S2a 在 adapter 实现一次创建、固定 N、进程内共享并跨调用复用的有界 pool；调用方传入 N，测试默认 N=1 且比较 N=1 与 N。S2b 才接 worker 启动接线和部署配置 N、M。
5. 本 §3 删除清单与节点、依赖、审核边界获确认。AGENTS.md、testing-conventions.md 建议条文及 execution plan 路径清单变更写入 handoff，由治理会话同步；S2a 自行维护 p6-design.md §2.2 当前事实及删除 Contract/ADR 后的失效链接。
6. 第 ④ 层正式真实数据差分在 05 执行，范围为 t1–t4 v1/v2 与 testdata1，按 DC50 补充；testdata1 与 t3 按输入 digest 去重记录。只做逐值解析差分，不做完整业务旅程或基准性能测量。
7. 原 S1c 审核会话负责代码审核及证据复核；审核通过后才运行完整 runner 与第 ④ 层正式差分。S2a exit、tag 与合入 main 在重建对照基准 exit 后办理。

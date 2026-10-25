# DC48 实施 handoff：Rust 测试进入权威门禁

- 日期：2026-10-25
- 依据：[DC48 交接说明](p6-dc48-rust-test-gate-handoff.md)；[Phase 6 S0 Owner 决议记录](p6-s0-owner-decisions.md) DC48、DC51、DC52
- 实施提交 V：`4526084da1239e0f0daebdcee1d3323b2b308068`（main，未推送）
- 节点：调试 `ct108-gw-dms-05`（hostname `gw-dms-test-05`），门禁与 carried `ct108-gw-dms-04`（hostname `gw-dms-test-04`）
- 日志根：两台节点的 `/home/dev/gdds-p6-logs/dc48/`（0700；日志 0600）

## 1. 结论

DC48 第 1 项已实施并通过第 4 节验收：

- 权威 runner 有了第六个包 `rust`（fmt、clippy、test），排在 Python 包之前；04 上全量六包 runner **exit 0**（2456 s），`rust` 包 26 s，205 个 Rust 测试通过。
- 3.2 选 **B**（runner 每次以 `--reinstall-package gateway-compute-python` 重建扩展）；一致性检查是扩展编译时嵌入 `HEAD:vnext/rust` 的 tree id，runner 同步后比较，不一致即失败。05 的反例证实：只改 `.rs` 时普通 `uv sync` 不重建，检查失败；runner 的强制重装会重建，检查通过。
- 04 同一 worktree 的 carried 演练：六个包全部“可沿用”，`changed_components=[]`。
- 与交接说明的一处不一致已由 owner 当场决定：`gateway-compute-python-impl` 的测试同样嵌入解释器，`cargo test` 一并排除到 S2a（§5 第 1 条）。
- clippy 首次启用无告警，没有修改任何现有 Rust 行为；旧扩展的生产代码未删除（只在 `#[pymodule]` 中多导出一个 `__build_input__` 属性）。

## 2. 实施内容

| 文件 | 改动 |
| --- | --- |
| `vnext/scripts/run-tests.sh` | 第六个包 `rust`，固定顺序最前；fmt、clippy、test 三步都执行并逐步记录耗时与状态；`CARGO_TARGET_DIR=<TMPDIR>/gateway-runner-cargo-target`，选中 `rust` 或 backend 时使用前删除残留、退出时删除；backend 同步改为 `--reinstall-package gateway-compute-python` 并传入 `GATEWAY_RUST_BUILD_INPUT`；同步后运行构建输入一致性检查；Hypothesis 隔离只作用于 Python 包 |
| `vnext/scripts/check-rust-extension-build-input.sh`（新） | 比较已安装扩展的 `__build_input__` 与 `HEAD:vnext/rust` 的 tree id；不一致、为空或无法导入时 exit 1 |
| `vnext/rust/gateway-compute-python/src/lib.rs` | 编译时用 `option_env!("GATEWAY_RUST_BUILD_INPUT")` 嵌入构建输入，导出为 `__build_input__`（未设置时为空串）；不改其他行为 |
| `vnext/scripts/test_input_closure.py` | `PACKAGES` 加入 `rust`，`SCHEMA_VERSION` 8 → 9；`rust` 包闭包见 §3.3；lock-root 覆盖只遍历五个 Python 包 |
| `vnext/repository_service/tests/test_run_tests_script.py`、`test_test_input_closure.py` | 覆盖 `rust` 的选择与顺序、三步命令与 target 目录、`rust` 失败只影响该包、backend 扩展以当前 tree 重建、不一致时停止；`rust` manifest 组成、cargo config 与 Cargo.lock 变化、工具链与 PyO3 解释器记录。顺带修正 fixture 中假 `uv-consume` 缺少有效 shebang 的问题（`\n` 拆行使 `dedent` 失效，此前靠 bash 的 ENOEXEC 回退才能运行） |
| `AGENTS.md`、`docs/backend-vnext/testing-conventions.md` | 合法包名与顺序、`rust` 三步与 S2a 前的排除、`CARGO_TARGET_DIR` 位置与清理、强制重装与一致性检查、`rust` 闭包组成、提交前的 `cargo fmt`/`clippy` 示例；DC51 第 2 项写入两处的 carried 规则旁 |

### 2.1 3.2 选择 B（runner 强制重装）

节点 05 实测（`exp-a.log`、`exp-b.log`）：

- 只提交 `.rs` 改动后，普通 `uv sync` 输出 `Checked 46 packages`，`.so` 哈希不变，扩展的 `__version__` 仍是旧值，确认交接说明第 1 节第 2 项的推断。
- A（在扩展的 `pyproject.toml` 加 `tool.uv.cache-keys`，含 `../*/src/**/*.rs` 等）在 `uv --no-config` 下也生效，`.rs` 改动后重建，且不改 `backend/uv.lock`。
- B（`--reinstall-package gateway-compute-python`）每次重建，增量约 7 s，空 target 目录约 27 s。
- 同一源码重建得到逐字节相同的 `.so`（`exp-b.log` 步骤 A3：改回原源码后重建，哈希回到 `c69a189b…`），所以 B 不会让 backend 的 uv 环境摘要在同一提交上漂移。

选 B 的理由：不依赖文件 mtime，不需要维护与 crate 依赖图同步的 glob 列表（新 crate、`build.rs` 等都要记得加），与 `native_kernel_component.sh` 写法一致；代价只是每次门禁多一次约 27 s 的构建。

### 2.2 构建输入一致性检查

- runner 计算 `git rev-parse HEAD:vnext/rust`，只在 backend 同步的子 shell 中导出 `GATEWAY_RUST_BUILD_INPUT` 与 `CARGO_TARGET_DIR`，不进入 manifest 与 pytest 的环境（backend 闭包会对 `GATEWAY_*` 变量取指纹，导出到全局会让 carried 比出“运行”）。
- 扩展以 `option_env!` 嵌入该值；cargo 跟踪 `option_env!` 读取的变量，值变化时重编该 crate。不需要 `build.rs`，不新增依赖，`Cargo.lock` 不变；`test_architecture.py` 禁止 `gateway-compute-python/src` 出现 `std::env`，`option_env!` 是编译期宏，不受影响。
- 镜像构建不设置该变量，镜像内的值为空串；检查只针对 runner 的 backend 环境，Compose 旅程的扩展由 Dockerfile 中的 maturin 全新构建，不受 uv 缓存影响。
- 新扩展（S2a）沿用：在其 `#[pymodule]` 中同样导出 `__build_input__`，runner 与检查脚本不变。

### 2.3 `PYO3_PYTHON`

排除两个旧 crate 的测试后，`cargo test` 中没有 crate 嵌入 Python，runner 不设置 `PYO3_PYTHON`。clippy 仍运行 PyO3 构建脚本，它按 `PYO3_PYTHON`、`VIRTUAL_ENV`、`CONDA_PREFIX`、PATH 上 `python3` 的顺序选解释器；闭包记录 `pyo3_python`（本次为空）与所选解释器的 `-VV`（本次为系统 `Python 3.13.5`）。

## 3. 验收

以下全部在已提交的 clean worktree 中运行；固定环境：umask 022、`HOME=/root`、`LC_ALL=C.UTF-8`、
`PATH=/home/dev/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`、`TMPDIR=/home/dev/gdds-test-tmp`、
`GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`；未设置 `GATEWAY_TEST_BASETEMP`、`UV_CACHE_DIR`、`HYPOTHESIS_STORAGE_DIRECTORY`、
`CARGO_TARGET_DIR`、`PYO3_PYTHON`。runner 日志由 `run-gate.sh` 包装，开头记录 hostname、起始时间、起始 HEAD 与 dirty 项数，
结尾记录结束时间、结束 HEAD、dirty 项数、worktree 内是否出现 `vnext/rust/target`、总耗时与 runner exit code。

### 3.1 调试节点 `ct108-gw-dms-05`

| 项 | worktree | 日志 | 结果 |
| --- | --- | --- | --- |
| `GATEWAY_TEST_PACKAGES=rust ./vnext/scripts/run-tests.sh` | `/home/dev/gdds-p6-dc48-accept05` @ V | `05-rust-runner-4526084da1.log` | **exit 0**；10:42:47 → 10:43:13（+08:00），26 s；fmt 0 s、clippy 11 s、test 15 s；起止 HEAD = V，clean，worktree 内无 `vnext/rust/target` |
| 一致性检查反例 | `/home/dev/gdds-p6-dc48-counter`（临时，已删除）@ V + 临时分支 | `05-counterexample.log`、`05-counter-C1-runner.log`、`05-counter-C4-runner.log` | 见下 |

同一套检查也在只差一行文档的前一版提交 `d54be78c61` 上跑过一次（`05-rust-runner-d54be78c61.log`，exit 0，manifest 摘要相同）。

反例过程（`05-counterexample.log`，10:43:13 → 10:44:24）：

1. **C1**：V 上 `GATEWAY_TEST_PACKAGES=backend run-tests.sh --co -q`（只收集，走真实的同步、重建与检查路径）exit 0；扩展从空 target 目录构建，`Prepared 5 packages in 26.74s`；检查 `expected=installed=cdc36c1a22dd…`（V 的 `vnext/rust` tree）`status=ok`；`__version__ = 0.1.0`。
2. **C2**：临时分支 `dc48-counterexample` 上只改 `gateway-compute-python-impl/src/lib.rs` 中 `__version__` 的值并提交；新 tree `1aa7f7621269…`。
3. **C3**：普通 `uv-consume.sh -C . sync`（不带重装）：`Checked 46 packages`，未重建，`__version__` 仍为 `0.1.0`；检查 `status=mismatch`（installed 为旧 tree），**exit 1**。
4. **C4**：runner 再跑一次（B）：`Building gateway-compute-python … Prepared 1 package in 26.78s`；检查 `status=ok`（新 tree）；`__version__ = dc48-counterexample`，exit 0。
5. **C5**：worktree 切回 V、不重新同步：检查 `status=mismatch`，**exit 1**。
6. 删除临时分支（`Deleted branch dc48-counterexample`）并移除该 worktree；临时分支未合入、未同步到其他节点。

### 3.2 门禁节点 `ct108-gw-dms-04`

门禁 worktree：`/home/dev/gdds-p6-dc48-gate04`（detached @ V，`legacy` 指向主 checkout；按 DC51 保留到 Phase 6 S0 合入之后）。

| 步骤 | 日志 | 结果 |
| --- | --- | --- |
| preflight | `04-gate-preflight.log` | worktree clean @ V；无 Dolt 进程、容器、Compose 项目、8000 监听；TMPDIR 为空；工具版本 rustc/cargo 1.97.0、rustfmt 1.9.0、clippy 0.1.97、uv 0.11.28、Dolt 2.1.11、Docker 29.9.1、Compose v5.6.0 |
| fresh repository-service 镜像（`build-repository-service-image.sh`） | `04-rs-image.log` | build_rc=0；10:42:16 → 10:42:22；`org.opencontainers.image.revision` 与 `build-input-revision` = V，`source-tree-sha256`=`sha256:cbf35f69…2a167c27`，`uv-lock-sha256`=`6dc9659f0aee…` |
| 全量 runner（`GATEWAY_TEST_WORKERS=48`，六包） | `04-full-runner-4526084da1.log` | **exit 0**；10:42:22 → 11:23:18（+08:00），**2456 s**；起止 HEAD = V，clean |
| postflight | `04-gate-postflight.log` | worktree clean @ V；无 Dolt、容器、Compose 项目、8000 监听；Hypothesis 包目录与 `gateway-runner-cargo-target` 均不存在；worktree 内无 `vnext/rust/target`；RS 镜像标签仍与 V 匹配 |
| carried 演练（同 worktree、同 HEAD、同环境） | `04-carried.log`；`v-manifests-04/`、`v-carried-04/`（0700/0600） | 六包全部 **可沿用**，`changed_components=[]` |

逐包结果：

| 包 / 批次 | 耗时 | 结果 |
| --- | --- | --- |
| rust（fmt / clippy / test） | 0 s / 11 s / 15 s，合计 26 s | 205 passed |
| shared_kernel | 1.04 s | 242 passed |
| repository_contracts | 0.28 s | 152 passed |
| repository_client | 2.80 s | 154 passed |
| backend (parallel) | 50 s | 2917 passed |
| backend (serial) | 1694 s | 39 passed |
| repository_service (parallel) | 53 s | 1739 passed, 1 skipped |
| repository_service (serial) | 589 s | 205 passed |

backend 同步中扩展从空 target 目录构建 29.23 s（`Prepared 2 packages`），随后 `rust extension build input … status=ok`。repository_service parallel 比节点核对时多 9 项，来自本次新增的 runner/闭包测试。

逐包闭包总摘要（runner 起始 manifest，schema version 9；carried 时 source 与 current 相等）：

| 包 | total digest | carried |
| --- | --- | --- |
| rust | `ce1386874287431b7e8a0e641e8b7b6a82186a5dd98c68442a21fadaee07aebd` | 可沿用 |
| shared_kernel | `378024ba566093dcb9bf8276d3f86c7b70cf020c347bd7a677fe73b0050a8c9e` | 可沿用 |
| repository_contracts | `c054e290d914d1e6a4c47ccd11415cc9bca01b15407f0b75fc2fb23bad4097bf` | 可沿用 |
| repository_client | `3fe14f3742204fc521bf17eeb78a06eca43057f1627c64f51923252e4b0b6a3e` | 可沿用 |
| backend | `e84e72475e71fc6a1adc5a071d0a1b383787574e7c9a5d91351a7943a299a7db` | 可沿用 |
| repository_service | `c4f2fc717f48e855bf8b238ae9cf71864cdcab98140dc24e3eed9d3ac2bd36cd` | 可沿用 |

`rust` 包 manifest 的组成：`package:rust`=`cdc36c1a22dd…`（`vnext/rust` tree）、`rust:cargo-lock`=`e9d8bccbf688…`、`shared:*` 共享组件 10 项、`non-git:cargo-config`（两台节点均无 cargo config 文件，entries 为空）、`environment:rust-toolchain`（rustc 1.97.0 `2d8144b78`、cargo 1.97.0、rustfmt 1.9.0-stable、clippy 0.1.97、`pyo3_python` 为空、PyO3 所选解释器 `Python 3.13.5`）。同一 V 在 05 与 04 上的 `rust` 摘要相同，符合“manifest 不记录节点身份”；判定仍只在同一节点、同一 worktree 内进行。

本 handoff 的提交只改 `docs/`，不在任何包的闭包内。

## 4. clippy 首次启用

`cargo clippy --workspace --locked --offline --all-targets -- -D warnings` 在现有代码上无告警（节点 05，`exp-c.log`），无需修复。`cargo fmt --all --check` 同样通过。

## 5. 与交接说明不一致或未完成的事项

1. **`gateway-compute-python-impl` 也须排除（已由 owner 决定）。** 交接说明 §2 只排除 `gateway-compute-python`；05 实测排除它之后，`gateway-compute-python-impl` 的 `kernel_component_tests::gil_probe::kernel_component_gil_boundaries_low_concurrency` 仍失败（`ModuleNotFoundError: No module named 'pyarrow.lib'`）：该模块同样嵌入解释器并读取 `backend/.venv/lib/python3.14/site-packages`。节点核对报告只看到一个失败，是因为 cargo 在第一个失败的测试二进制后停止（`exp-c.log`、`exp-d.log`，`--no-fail-fast` 下确认只有这两处）。owner 2026-10-25 选择一并排除到 S2a，未采用 `--skip` 过滤或以 uv CPython 3.14 加 `LD_LIBRARY_PATH` 运行（后者在 05 上可通过，但会让 `rust` 包依赖 backend 环境）。impl 中 11 个不嵌入解释器的单元测试因此暂不运行，S2a 随旧 crate 删除。
2. **闭包环境比交接说明列的多两项**：除 `rustc`/`cargo`/`rustfmt`/`clippy-driver` 版本与 `PYO3_PYTHON` 外，还记录 PyO3 构建脚本实际选中解释器的 `-VV`、`CARGO_*`/`RUST*`/`PYO3_*` 等设置的指纹，以及 cargo config 文件内容摘要。理由：clippy 会运行 PyO3 构建脚本，未设置 `PYO3_PYTHON` 时它依赖 PATH 上的 `python3`；cargo config 与 `RUSTFLAGS` 能改变构建结果。均为保守方向，不放宽任何判定。
3. **Hypothesis 隔离只作用于 Python 包**：AGENTS 原文“为每个选中包无条件设置 `HYPOTHESIS_STORAGE_DIRECTORY`”改为“每个选中的 Python 包”；`rust` 包不运行 pytest。
4. **“每包起止时间”按现有粒度记录**：runner 对其他包记录的是批次 `elapsed_seconds` 与 `status`，`rust` 同样逐步与整体记录 `elapsed_seconds`/`status`；墙钟起止时间在包装日志的开头与结尾。
5. **DC51 第 2 项**写入了 AGENTS（镜像身份等价第 3 条之后）与 testing-conventions（同一位置），没有写入 Phase 6 执行计划（不在本会话范围）。
6. **测试 fixture 修正**：`test_run_tests_script.py` 的假 `uv-consume` 原本没有有效 shebang（Python 字符串中的 `\n` 拆开了一行，`textwrap.dedent` 失效），此前靠 bash 的 ENOEXEC 回退运行；本次修正，未改变断言含义。
7. **backend serial 批次 1694 s**，比节点核对时（1591 s）多约 100 s；本次改动不涉及该批次的测试或 Compose 旅程，未单独分析，交给 V8 门禁耗时剖析参考。
8. **未清理项（auto-mode 分类器拒绝了批量清理，按指示停下，由 owner 决定）**：05 上本会话的实验/调试残留——worktree `/home/dev/gdds-p6-dc48-exp`、`/home/dev/gdds-p6-dc48-debug`，实验分支 `dc48-exp-plain`、`dc48-exp-cachekeys`（A/B 对比用，不是反例分支），TMPDIR 中的 `dc48-exp-cargo-target`、`dc48-debug-cargo-target`、`pytest-of-root`、`uv-*.lock`。04 的 TMPDIR 有本次 runner 产生的 `tmp.*`、`uv-*.lock`、`repository-import-*.sqlite3-shm/-wal`、`pytest-of-root/`、`gateway-compose-gate-provenance.json`，与节点核对报告 §7 第 3 条同类，不来自 `rust` 包。两台节点的 `/home/dev/gdds-bundles/` 有本次同步用的 bundle，仓库中有 `refs/dc48/main`（= V）；节点主 checkout 仍在 `0c5a3f458c`，未同步 V（等 owner 决定推送或同步方式）。05 的 `/home/dev/gdds-p6-dc48-accept05` 与 04 的门禁 worktree 保留。
9. **未推送**：V 与本 handoff 只在开发主机 main 上。

## 6. 每轮评审记录（Docker/Compose）

```text
Current HEAD: 4526084da1239e0f0daebdcee1d3323b2b308068（V；本 handoff 提交只改 docs/）
Container rebuild required: yes
Reason: vnext/rust/gateway-compute-python/src/lib.rs 改动进入 backend/worker 镜像（Dockerfile 中 maturin 构建）；runner/闭包脚本改动
Last verified image revision: 4526084da1239e0f0daebdcee1d3323b2b308068
Last verified source-tree/image id: repository-service source-tree sha256:cbf35f692c46ce420f8a3ae4ad4b7eb875e4012fbdcf2dd8def8d7dc2a167c27；backend/worker 由同一次 runner 的 Compose 旅程从 V 构建
Container gate for current HEAD: passed（04 全量 runner，backend 与 repository_service 的 Compose 旅程均在其中）
Carried from: none（V 实际运行）；同 worktree carried 演练六包可沿用
Deferred gates/nodeids: none
Required execution point: 本轮结束（已完成）
```

# DC48 交接说明：Rust 测试进入权威门禁

- 日期：2026-10-25
- 交给：负责 DC36、AGENTS.md、testing-conventions 与执行计划 §8.9 的会话（以下简称“实施方”）
- 来自：Phase 6 S0 讨论会话
- 依据：[Phase 6 S0 Owner 决议记录](p6-s0-owner-decisions.md) DC48（经 DC52 修订）、DC51 第 2 项；[节点核对报告](p6-node-init-report.md) §5、§7；[Phase 6 规划讨论稿](p6-planning-discussion.md) §12、§13 D5/D6。
- 时限：Phase 6 开工的前置任务，须在前置验证 V1、V6（两者都要写 Rust）开始之前完成。

## 1. 要解决的问题

1. **权威 runner 不运行任何 cargo 命令。** `vnext/scripts/run-tests.sh` 只跑五个 Python 包；`cargo fmt`、`cargo clippy`、`cargo test` 都不在门禁中，Rust 代码的单元测试只在开发者手动运行时执行。
2. **Python 测试可能使用过时的扩展。** backend 以路径依赖引用 maturin 构建的扩展（`vnext/backend/pyproject.toml` 中 `gateway-compute-python = { path = "../rust/gateway-compute-python" }`），没有配置 `tool.uv.cache-keys`。uv 默认只在 `pyproject.toml`、`setup.py`、`setup.cfg` 变化时重建本地路径依赖，所以只改 `vnext/rust/**` 时，runner 的 `uv sync` 很可能不会重建扩展，Python 测试运行旧的 `.so`。闭包 manifest 会因 Git tree 变化判定为“运行”，却测不出扩展是旧的。Compose 旅程不受影响（镜像中由 maturin 全新构建）。Phase 6 会频繁修改 Rust，这一点会直接削弱门禁证据。
3. **`cargo test --workspace --locked` 在固定环境下失败 1 例**（节点报告 §5）：`gateway-compute-python` 的 `adapter_errors` 测试在 Rust 中嵌入 Python 解释器，并写死 `backend/.venv/lib/python3.14/site-packages`（`vnext/rust/gateway-compute-python/tests/common/mod.rs`）；PyO3 构建时选中系统 Python 3.13，运行时找不到 cp314 的 pyarrow。

## 2. 与 DC52 的关系

owner 决定现有 Rust 扩展（`gateway-compute-python` 与 `canonical_row_hash`）视为过时，**不迁移、不复用**，在 Phase 6 的 S2a 删除并由新 crate 替换（DC52）。因此：

- 不需要把 `adapter_errors.rs` 等嵌入解释器的测试迁移成 pytest，也不需要专门验证“旧扩展是否过时”。
- 但第 1 节第 2 项的机制问题对新扩展同样存在：新扩展仍以 maturin 路径依赖装进 backend 环境。本交接要建立的是**对任何扩展都成立的机制**，S2a 的新 crate 直接沿用。
- 在 S2a 之前旧扩展仍然存在。`rust` 包的 `cargo test` 在此期间排除 `gateway-compute-python`（`--exclude gateway-compute-python`），S2a 删除旧 crate 时去掉该排除。这样不提前删除仍在镜像中的代码的测试，也不让嵌入解释器的旧测试阻塞门禁。

## 3. 实施内容

### 3.1 权威 runner 增加第六个包 `rust`

- **检查内容**（在 `vnext/rust` 下）：
  - `cargo fmt --all --check`
  - `cargo clippy --workspace --locked --offline --all-targets -- -D warnings`
  - `cargo test --workspace --locked --offline`（S2a 之前加 `--exclude gateway-compute-python`）
- **环境**：
  - 离线运行；节点 05 已核实 crate 缓存完整、无需联网（节点报告 §5）。
  - `CARGO_TARGET_DIR` 放在 worktree 外，例如 `<TMPDIR>/gateway-runner-cargo-target`。它是构建缓存，不是测试输入，不进闭包摘要；是否在 runner 前后清理由实施方决定，并写进 testing-conventions。
  - 如仍有 crate 需要嵌入 Python（S2a 之前被排除的除外），通过 `PYO3_PYTHON` 显式指定解释器，并把它记进闭包的环境部分；不依赖系统 `python3`。
- **runner 集成**：
  - `ALL_PACKAGES` 与 `GATEWAY_TEST_PACKAGES` 的合法包名加入 `rust`；重复或未知名称仍以 exit 2 拒绝；在固定顺序中的位置由实施方决定（建议放在 Python 包之前，失败最快）。
  - 每包的 `status`、起止时间、exit code 与其他包同样记录；“S5 最终门禁与发布门禁必须运行全部包”自然包含 `rust`。
- **闭包 manifest**（`vnext/scripts/test_input_closure.py`）：
  - `PACKAGES` 加入 `rust`；组成部分包括 `vnext/rust` 的 Git tree（排除 `target/`）、`Cargo.lock`、`rust-toolchain.toml`、五个 lockfile 与 runner/wrapper 脚本（与其他包一致），环境部分记录 `rustc`、`cargo`、`rustfmt`、`clippy-driver` 的版本，以及 `PYO3_PYTHON`（若设置）。
  - `SCHEMA_VERSION` 相应递增。
  - `compare` 对 `rust` 包的“可沿用 / 运行”判定与其他包相同。
- **耗时预期**：节点 05 上 build 约 15 s、test 约 6 s（缓存命中时），clippy 另计；对 39 分钟的全量门禁几乎没有影响。
- **首次启用**：`clippy -D warnings` 可能在现有代码上报警。修复只限于让检查通过、不改变行为；如需修改 `gateway-compute-python` 等过时代码，以最小改动为准，不做重构。

### 3.2 保证 Python 测试使用当前的扩展

二选一，由实施方根据实测决定，并写明理由：

- **A. `tool.uv.cache-keys`：** 在 backend（或扩展自身）的 `pyproject.toml` 中把 `vnext/rust` 下的 `**/*.rs`、各 `Cargo.toml`、`Cargo.lock`、`rust-toolchain.toml` 加入 cache-keys，使 `uv sync` 在 Rust 源码变化时重建。改动 `pyproject.toml` 涉及锁文件时，按 AGENTS“改依赖”的规则处理。
- **B. runner 强制重装：** runner 同步 backend 环境时对 `gateway-compute-python` 使用 `--reinstall-package`（`native_kernel_component.sh` 已有同样写法），每次门禁都重建扩展。

无论选哪种，门禁都增加一条**构建输入一致性检查**：确认已安装扩展的构建输入与当前提交一致，不一致时该包失败。实现方式由实施方定。可选做法：

- 扩展构建时嵌入一个构建输入摘要（例如 `vnext/rust` 的 Git tree id），runner 比较它与当前提交的值；若需要 `build.rs`，按 Rust safety policy §5 在 review 中说明用途与影响。
- 或比较已安装 wheel 的 `RECORD` 与刚构建的产物。

### 3.3 文档

- **AGENTS.md**：“跑测试”中的合法包名列表、runner 两遍拆分的说明、“提交前”增加 `cargo fmt --check` 与 `cargo clippy` 的示例。
- **testing-conventions**：`rust` 包的闭包组成、`CARGO_TARGET_DIR` 的位置与清理、构建输入一致性检查、S2a 之前的 `--exclude`。
- **DC51 第 2 项**（可选写入）：阶段的门禁 worktree 保留到该阶段 exit 合入之后再清理。owner 决议要求写入 Phase 6 执行计划；是否同时写入 AGENTS 或 testing-conventions，由实施方判断。

## 4. 验收

在已提交的 clean worktree 上，按 AGENTS 与 DC36 的节点分工：

1. **调试节点 `ct108-gw-dms-05`：**
   - `GATEWAY_TEST_PACKAGES=rust ./vnext/scripts/run-tests.sh` exit 0。
   - **一致性检查的反例**：在临时 worktree 中只改一个 `vnext/rust/**/*.rs` 文件（任意源码改动即可，提交到临时分支，不合入），确认：采用 3.2 A 时 `uv sync` 重建了扩展；采用 B 时扩展被重装；构建输入一致性检查在人为制造的不一致下失败。记录过程，临时分支用后删除。
2. **门禁节点 `ct108-gw-dms-04`：**
   - 全量权威 runner（六个包）exit 0，日志记录 `hostname`、起止时间、起止 HEAD 与 exit code。
   - 同一 worktree 的 carried 演练：`rust` 包在不变的 HEAD 上判定为“可沿用”。
3. 运行期间不写 worktree；postflight 与现有规则相同。

## 5. 边界

- 不修改 Phase 6 讨论稿、`p6-s0-owner-decisions.md` 与 implementation-stages；如发现与 DC48 不一致之处，回报 Phase 6 S0 讨论会话，由 owner 决定。
- 不删除现有扩展的生产代码（S2a 的范围，DC52）。
- 不改变 AGENTS 中其他门禁规则的语义；超出本说明的规则变化（例如 backend 与 repository_service 跨节点分开运行，DC48 第 3 项）先报 owner。
- 未经 owner 授权不推送。

## 6. 回报内容

- 提交 ID，以及 3.2 选择了 A 还是 B、构建输入一致性检查的实现方式；
- 第 4 节各项的日志位置（节点上的路径）、exit code、耗时，`rust` 包的闭包摘要；
- `clippy` 首次启用时修复的告警清单（如有）；
- 与本说明不一致或未完成的事项。

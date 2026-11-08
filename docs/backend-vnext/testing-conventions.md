# Testing Conventions

状态：2026-08-07 建立；2026-08-09 增补P2后半段container gate合并规则；
2026-08-13 冻结Docker/Compose触发式重建、评审记录、全局风险验证与artifact cleanup规则
2026-10-25 增加 `rust` 包、backend Rust 扩展强制重装与构建输入一致性检查（DC48），门禁 worktree 保留规则（DC51）
2026-11-02 增加前端测试规则（FD7）
2026-11-08 从 AGENTS 收拢执行细节，收入 FE3a 真实 e2e 约定；相关措辞按 owner 确认澄清

本文规定 vNext 各包（五个 Python 包与 `rust` 包）的测试分层、执行入口与性能约束；前端（`frontend/`）的运行位置、
工具链与证据见“前端测试（FD7）”一节。Fixture 材料语义由
[Testing Fixtures](testing-fixtures.md) 拥有，本文不重复。

## 执行入口

Host 依赖准备与权威测试分为两阶段，不得混用机器级 index：

```bash
./vnext/scripts/prepare-dev-dependencies.sh
./vnext/scripts/run-tests.sh
```

所有测试、容器门禁与取证都在专用测试节点上执行（owner 决议 DC34、DC36），不回退到开发主机。分工：
门禁节点 `ct108-gw-dms-04` 运行权威全量 runner、容器门禁与 carried；调试节点 `ct108-gw-dms-05` 运行
focused 测试、Rust 编译、解析器差分测试与真实数据 t1–t3；参考节点 `ct108-gw-dms` 用于 Phase 6 性能测量
（测量期间独占）与真实数据 t4。Owner 于 2026-11-06 新增后端开发节点 `ct107-gw-dms-06`（16 vCPU / 96 GiB / 300 GiB thin，`192.168.233.207`；内存于 2026-11-07 从 32 GiB 扩容并实核），用于 Rust、focused/Contract/差分和小规模 Compose；新增前端开发节点 `ct109-gw-dms-07`（8 vCPU / 16 GiB / 200 GiB thin，`192.168.233.208`），用于类型检查、lint、单测、构建、截图与 mock e2e。它们不承接正式性能测量、权威 runner/carried 或默认真实数据全旅程；[节点核对与证据](refactoring/formal/plans/p6-node-06-07-readiness.md)另记。

原 04、05、CT108 互不共享硬件；新增 06/07 与 04 共享物理宿主，不与 CT108 共享宿主。Owner 确认宿主资源宽裕，06/07 日常开发与测试自主并行，不自动与 04 互斥，不为新节点占用 04 或向原基准总协调申请窗口/汇报资源。各节点自身占用、服务/端口及同节点计时独占规则不变；只有实际干扰、跨节点操作或明确冲突才针对性协调，不以存在竞态的跨节点空闲查询建立常规前置。cpuset 分离不证明 SMT、内存和磁盘 I/O 无竞争，新节点不提供正式性能数值。06 初始 pytest workers/Cargo jobs 建议各为 4，与产品 kernel N/M 分开。07 使用 `GATEWAY_FE_TEST_WORKERS=2` 限制 Playwright 并发。宿主 thin pool 的 data/metadata 余量由管理员监测，guest `df` 不能代替；这不作为日常开发的额外审批。克隆的历史 worktree、日志、镜像标签和卷不自动成为新节点证据，初始化不擅自删除。

Owner 于 2026-11-07 简化全部 CT 的常规资源协调：以执行时现场状态与有效占用标志为准，需要占用的工作在核空闲后原子取得标志即可直接使用，完成本任务收尾后释放；无需跨会话或向 Owner 反复申请、预留窗口、确认及例行通报起止。只有实际占用冲突或操作涉及他人资源时才针对性协调；尊重他人有效标志及原有节点用途，不抢占或移除他人占用。前端不需整机占用的既有例外沿用原规则。

开始前用 `ssh -o BatchMode=yes <别名> 'echo OK'` 检查连接。运行前提在每台
节点上分别满足，同一节点整机单飞，不同节点按上述物理宿主边界并行。carried 与来源 V 必须在同一节点、同一 worktree；
闭包 manifest 不记录节点身份（克隆节点首次重建镜像前 image ID 也相同），因此 runner、carried 与真实数据日志
开头记录 `hostname` 与起止时间，handoff 写明运行节点，评审逐项核对。SSH 会话以 root 登录时，
设置磁盘上的 `TMPDIR=/home/dev/gdds-test-tmp`，避免复用其他用户拥有的
`/tmp/pytest-of-root`；不需要 pytest tmpfs 时保持 `GATEWAY_TEST_BASETEMP` 未设置，以保留默认批次与 Compose 路径。

### 测试节点网络与缓存（owner 2026-10-28）

CT201 是联网开发节点，不用于运行测试。专用测试 CT 禁止直接访问公网，但可经局域网访问 CT201 或指定的公共缓存 CT 提供的获准缓存。该访问只用于依赖、镜像和构建制品，不开通任意公网出口。测试代码通过获准的局域网 Git/文件传输方式同步到各自的 clean、已提交 worktree；测试、Compose 与真实数据旅程仍在指定测试 CT 上执行。

缓存按节点分别准备，不能假设一个节点的 cache、image 或 build layer 已存在于其他节点：

- **Python：**测试节点的权威 runner 与环境同步设置 `UV_OFFLINE=1`，使用已填充的 uv 缓存/环境。`prepare-dev-dependencies.sh` 的 `GATEWAY_DEV_OFFLINE=1` 只约束准备步骤，不代替 runner 的 `UV_OFFLINE=1`。保留 lockfile 中的 canonical registry identity，不得通过机器级 index 配置改写 lock source。
- **Rust：**测试节点的权威 runner 设置 `CARGO_NET_OFFLINE=true`；对应 rustup toolchain 与 crates 必须预先齐全。root SSH 环境的 `PATH` 以 `/home/dev/.cargo/bin` 开头，不设置 `RUSTUP_TOOLCHAIN`、`RUSTUP_HOME` 或 `CARGO_HOME`；在 `vnext/rust` 下用仓库 selector 检查 `rustc` 版本，并确认 `cargo`、`rustfmt` 与 `clippy-driver` 使用同一工具链。不可依赖测试节点联网安装工具链。
- **DC67 预填充与代理：**依赖、锁文件或基础镜像变化时，先在 CT201 取得制品，经获准的局域网预填充到实际使用的节点；handoff 记录来源节点/提交、制品摘要与预填充时间。04 权威 runner、carried、ct108 测量与各节点真实数据取证不经任何转发代理；缓存缺失即停止，完成预填充后从头运行。仅 05 调试构建可临时使用受限转发代理：只放行所需主机、不传凭据、用完即停；handoff 记录放行主机范围、起止时间与用途，调试结果不作证据。
- **Docker/Compose：** 基础镜像须已在节点本地或可从批准的 LAN registry/cache 获取。Dockerfile 下载的 uv、Python、Dolt 与 Python 包须命中现有构建层、预置依赖镜像或 LAN 制品缓存。Repository Service 可使用已校验的依赖基础镜像；使用 `build-repository-service-image.sh` 的 `GATEWAY_P2R1_CACHE_URL` 时，须设置为该节点实际可达的获准缓存地址（owner 2026-11-08 确认保留两种方式）；默认 `172.17.0.1:18080` 是本机 Docker bridge gateway 的假设，不是通用 CT 地址。
- **backend/worker dependency-base（自 `p6-backend-image-exit` 起）：** `vnext/backend/pyproject.toml`、`vnext/backend/uv.lock`、`vnext/backend/.python-version`、`vnext/rust/Cargo.lock`、`vnext/rust/rust-toolchain.toml` 或 Rust 基础镜像变化时，在 CT201 的 clean worktree 执行 `vnext/scripts/build-backend-dependency-base.sh --save <归档>`，构建 `gateway-backend-deps:lock-<12>`。通过获准 LAN 传到实际使用的测试节点后执行 `docker load`。handoff 记录来源提交、完整输入摘要、tag、config digest、全部 RootFS DiffID、归档 SHA256、构建/传输起止时间与缓存来源类别/端点标识，不记录凭据；inspect ID 仅作参考。
  - backend/worker 特有的 build 设置为 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=<lock-tag>`、`GATEWAY_DOCKER_BUILD_NETWORK=none`。保留 Compose build，由节点在无构建网络时本机实际构建 backend/worker；不设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。
  - 历史版本说明：`p6-backend-image-exit` 之前的产品提交（包括 S1c 候选 V 与 `p6-s1c-exit`）仍使用旧 Dockerfile，按 DC67 补充第 2 项由 CT201 预构建并传输完整 backend/worker 镜像。
- **跨节点镜像身份：**传输镜像用 config digest 与全部 RootFS DiffID 逐项比较，不比较 `docker inspect` ID；containerd store 的 inspect ID 是本机生成的 manifest digest。同节点闭包 manifest 与按包 carried 判定使用本机 image ID；这不改变下文容器门禁镜像等价规则。
- **Repository Service 与 client e2e：**继续使用各自的预置依赖模式。若 client e2e 镜像的 revision label 与当前 HEAD 不同，门禁会在本机重建，这是正常行为；不要手工执行 `docker rmi`。
- **本地运行依赖：** Dolt、Compose 本地网络、真实数据文件、Docker daemon 和测试端口仍须在各测试节点就绪；断公网不应影响节点 loopback、容器间网络或获准 LAN 缓存连接。

启动 runner 或容器门禁前，确认本次闭包涉及的缓存端点可达，且依赖、基础镜像和必需构建层可从本机或获准 LAN 缓存取得。若发生 cache miss 且缓存不可达，停止验收并补齐缓存/恢复端点，不得回退到 CT201 执行测试。handoff 记录 cache 来源类别/端点标识与使用方式；runner 和 carried 证据仍按原规则记录 hostname、起止 HEAD、exit code，凭据不得写入日志。proxy/cache URL 的 manifest 指纹只作闭包判定，不应反推出或打印凭据。

**DC68 现行规则（Owner 2026-11-08 修订）：工具故障最多三轮自主修复。** 自身命令、脚本、参数、执行范围或 DC66 第 5 项工具缺陷导致失败时，首次失败后允许对同一具体根因最多三轮“定位→固定修订→适用独审→受影响步骤复验”，不因被测对象已经运行而立即要求 Owner 恢复。首次失败不计修复轮次；第三轮仍未解决后交 Owner，不以更换候选、目录、节点或角色重计同一根因。既有只读后处理/预检和代码传输准备不计次数的澄清继续适用。

- 每次首失败仍先停止该次执行及后续验收，保留原始 numeric exit、日志和 SHA256，确认资源/状态可安全收尾后再修复。若只留工具stdout而没有独立原文件，明确来源限制，不补造实时原日志。后续成功不改写旧失败、缺失或未知。
- 三轮授权用于修复后复验，不是无修改自动重试。修订稿继续适用本轮独审、clean 固定候选、节点占用/离线和输入身份规则；只重跑受影响步骤，不重复已有合格未受影响结果。正式runner自身不增加自动重试逻辑。
- 不确定故障原因、无法确认副作用/资源收尾、需改冻结语义/Contract/golden/输入或超出现有授权时，仍停止受影响部分交Owner。真实产品failure按阶段已有修复授权和同根停止规则处理，不伪装成工具错误，也不靠DC68放宽断言。
- 缓存缺失、镜像/HEAD/输入身份不符、结果不一致时不得继续该次验收。明确由错误工具/命令选择引起的，可按本条修正后重新核验；可按DC67既有授权准备正确缓存，但不绕过预置来源/离线规则或接受错误身份。真实来源/正确性冲突未解决时交Owner。
- runner已开始测试后exit非0仍先停止后续carried/验收并处理失败；确认属于工具故障后，可在上述三轮和适用独审内恢复，不能直接继续原失败链。原始失败与修正、每轮结果及计数写入普通handoff即可，不增建持久计数/evidence机制。

linked worktree 里先建 `legacy` 符号链接（`ln -s /home/dev/gateway-data-management-system/legacy <worktree>/legacy`；该目录不在提交里，缺它时 backend 的
`test_table_rules_resolver.py` 有 58 个用例失败），再执行上面的两步。

`prepare-dev-dependencies.sh` 只同步五包 venv，不跑 pytest。`run-tests.sh` 先跑 `rust` 包，再按正确顺序跑
完全部 Python 包：

```bash
./vnext/scripts/run-tests.sh
```

阶段允许通过 `GATEWAY_TEST_PACKAGES` 指定部分包，例如
`GATEWAY_TEST_PACKAGES=backend,repository_service ./vnext/scripts/run-tests.sh`。合法值按固定顺序是
`rust`、`shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service`；
未知或重复名称以 exit 2 拒绝，实际执行顺序仍按权威 runner 固定顺序。未设置变量时运行全部六个包，
原有包顺序、backend 与 `repository_service` 的两遍拆分、`GATEWAY_TEST_BASETEMP` 下的 Compose 文件
处理和五锁检查不变。项目最终门禁与发布门禁不允许缩小范围，必须运行全部六包（含 `rust`）；其他阶段按范围与闭包规则选择。

### `rust` 包与 backend 的 Rust 扩展（DC48）

`rust` 包最先运行，失败最快暴露。它在 `vnext/rust` 下依次执行以下三步；三步都执行，每步记录
`elapsed_seconds` 与 `status`，任一失败则 `rust status=failed`，其余包照常运行：

```bash
cargo fmt --all --check
cargo clippy --workspace --locked --offline --all-targets -- -D warnings
cargo test --workspace --locked --offline
```

- **S2a 后的 workspace**：旧嵌入 Python 的 adapter tests 与 `gateway-compute-python-impl` 已删除（DC52）；
  `gateway-compute-python` 复用为新 parser adapter，`cargo test` 不再排除 crate。新扩展需要 Python/Arrow 的行为
  由 backend pytest 测已安装扩展，不在 Rust 用例中嵌入解释器；clippy 与 fmt 覆盖全部 crate。
- **离线**：cargo 以 `--locked --offline` 运行，crate 缓存在 `CARGO_HOME`（固定环境下为 `/root/.cargo`）。
- **`CARGO_TARGET_DIR`**：固定为 worktree 外的 `<TMPDIR>/gateway-runner-cargo-target`（`TMPDIR` 未设置或为空时为
  `/tmp`）。它是构建缓存，不是测试输入，不进闭包。选中 `rust` 或 backend 时，runner 在使用前删除残留、退出时
  （包括失败与可捕获的中断）删除，因此每次门禁都从空目录完整构建（节点 05 实测：空目录下 `rust` 包三步合计约
  26 s，backend 同步中扩展的 release 构建约 27 s）；runner 不再向 worktree 的 `vnext/rust/target` 写入。
- **`PYO3_PYTHON`**：删除旧嵌入解释器的测试之后，`cargo test` 中没有 crate 嵌入 Python，runner 不设置 `PYO3_PYTHON`。
  clippy 仍会运行 PyO3 的构建脚本，它按 `PYO3_PYTHON`、`VIRTUAL_ENV`、`CONDA_PREFIX`、PATH 上的 `python3` 的顺序选择
  解释器；闭包记录 `PYO3_PYTHON` 的值与所选解释器的 `-VV`。今后若有 crate 需要嵌入解释器，通过 `PYO3_PYTHON`
  显式指定，不依赖系统 `python3`。
- runner 的额外命令行参数只传给 pytest，不传给 cargo。

backend 以 maturin 路径依赖安装 Rust 扩展（`gateway-compute-python = { path = "../rust/gateway-compute-python" }`）。
uv 默认只在扩展的 `pyproject.toml` 等文件变化时重建路径依赖；节点 05 实测只提交 `.rs` 改动后 `uv sync`
不重建，Python 测试继续使用旧的 `.so`。为此：

- **强制重装（DC48 3.2 的 B 方案）**：runner 同步 backend 时始终使用
  `uv-consume.sh -C . sync --reinstall-package gateway-compute-python`，`CARGO_TARGET_DIR` 同上。选 B 而不选
  `tool.uv.cache-keys`（A）的理由：B 不依赖文件 mtime，也不需要维护与 crate 依赖图同步的 glob 列表；
  代价只是每次门禁重建一次扩展。A 经实测同样可用，未采用。
- **构建输入一致性检查**：runner 以 `GATEWAY_RUST_BUILD_INPUT=<HEAD:vnext/rust 的 Git tree id>` 构建扩展，扩展在编译时用
  `option_env!` 嵌入该值，暴露为 `gateway_compute._native.__build_input__`（未设置时为空串，镜像构建即如此）。
  同步后 `vnext/scripts/check-rust-extension-build-input.sh` 读取已安装扩展的值并与当前提交比较，不一致、为空或无法导入时
  backend 失败，runner 在 manifest 之前以 exit 1 停止。该变量只传给 backend 的同步命令，不导出到 manifest 与 pytest 的环境。
  cargo 跟踪 `option_env!` 读取的变量，值变化时重新编译所在 crate。此机制对任何以 maturin 路径依赖装入 backend 的扩展都成立，
  S2a 的新 crate 沿用：在扩展的 `#[pymodule]` 中同样导出 `__build_input__`。
- 开发者在 Rust 改动后跑 backend focused 测试时，同样先用 `--reinstall-package gateway-compute-python` 同步。

### Hypothesis 隔离与按包闭包沿用

权威 runner 为每个选中的 Python 包无条件设置 `HYPOTHESIS_STORAGE_DIRECTORY` 为
`<TMPDIR>/gateway-runner-hypothesis/<包名>`；路径不含随机部分。`TMPDIR` 未设置或为空时固定使用 `/tmp`，
有效 TMPDIR 必须是 worktree 外已存在的绝对路径。runner 在 manifest 前打印各包的有效 storage directory 并删除选中包的残留目录，并在退出时（包括失败与
可捕获的中断）清理这些包专属目录；不会删除 worktree 的 `.hypothesis` 或 TMPDIR 下的其他内容。同一包的
所有 pytest 调用共用一个目录，包括 backend 与 `repository_service` 的并行、串行两遍。worktree 内的
`.hypothesis` 只用于开发者直接运行 focused 测试，不是权威 runner 的输入。

权威 runner 不跨运行保留 Hypothesis 失败样例，这是隔离目录带来的代价。失败时依据 Hypothesis 输出的反例分析；
runner exit 非 0 时先停止并处理失败，不继续做 carried 或后续验收。

runner 先经受控 wrapper 同步待运行包的 locked uv 环境，再为每个待运行包写出一份 JSON 闭包 manifest，可单独运行
`python3 -I vnext/scripts/test_input_closure.py manifest --package <包名>` 查看；dirty worktree 会被拒绝。
Python 包还摘要该包实际使用的 uv 环境目录内容；由锁定源码与对应 Python
解释器派生的 `__pycache__`、`.pyc`、`.pyo` 不计入 uv 环境摘要。
Git 组成部分使用当前提交对应路径的 tree/blob object id，`legacy/` 使用排序后的相对路径与文件内容摘要，
环境部分记录每包 Python `-VV`、Dolt、uv、rustc 版本；每包还对有效 Hypothesis storage directory
（`HYPOTHESIS_STORAGE_DIRECTORY` 或包目录下 `.hypothesis`）及包内 `.pytest_cache` 的路径、内容和权限做摘要，涵盖可能参与输入生成或被测试工具读取的缓存。backend 与 `repository_service` 还记录 Docker/
Compose 工具与 daemon 身份、有效 build 环境变量指纹、基础/服务/dependency-base 镜像 tag 和本机 image ID；backend 另记录所选 dependency-base 名称与 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES` 开关；
backend 的 prebuilt Compose 选项启用时，manifest 还摘要本机镜像清单。proxy/cache URL 等可能含凭据的值只记录 SHA-256，
不将原值写入 manifest。每包闭包包括自身与传递路径依赖、fixtures、全部五个 lockfile、
runner/wrapper 脚本、workspace 配置、deployment 输入和共享 rust-toolchain selector。backend 的 Rust
闭包包含 workspace crate、`Cargo.lock` 与 `rust-toolchain.toml`（生成的 `target/` 排除）；backend 和
`repository_service` 还包括 Compose 镜像使用的完整 `vnext/` build context、相关 Compose 与 Dockerfile。
repository_service 的 context 因而包含 `repository_client` 及 e2e/dependency-base Dockerfile。manifest 记录
本机 base image ID、repository-service 与 dependency-base ID、client e2e 与 client dependency-base ID，以及
会影响 build 的环境设置指纹。backend 所选 dependency-base 名称、本机 image ID 或预置开关任一变化，都要求 backend 重新运行。`compare --source <来源-manifest.json> --current <当前-manifest.json>`
逐项比较并输出“运行”或“可沿用”及变化的组成部分。

`rust` 包的闭包（schema version 9 起）：`package:rust` 为 `vnext/rust` 的 Git tree（未跟踪的 `target/` 不在其中），
`rust:cargo-lock` 单列 `Cargo.lock`；共享组件与 Python 包相同（fixtures、`vnext/scripts`、workspace 配置、
rust-toolchain selector、deployment、五个 lockfile）；`non-git:cargo-config` 按路径与内容摘要 cargo 会读取的
`.cargo/config.toml`/`.cargo/config`（`vnext/rust` 及其祖先目录、`CARGO_HOME`，不存在的文件不记录）；
`environment:rust-toolchain` 记录 `rustc -vV`、`cargo`、`rustfmt`、`clippy-driver` 版本（在 `vnext/rust` 下按
`rust-toolchain.toml` 选择）、`PYO3_PYTHON` 与 PyO3 构建脚本所选解释器的 `-VV`，以及 `CARGO_*`、`RUST*`、
`PYO3_*`、`HOME`、`PATH`、`VIRTUAL_ENV`、`CONDA_PREFIX`、`LANG`、`LC_ALL`、`TZ` 的 SHA-256 指纹（`CARGO_TARGET_DIR`
除外）。`rust` 包没有 uv 环境、Hypothesis storage、pytest cache，也不读 `legacy/`，这些组件不出现在它的 manifest
中；crate 内容由 `Cargo.lock` 的 checksum 固定。`compare` 对 `rust` 包的“可沿用 / 运行”判定与其他包相同。
对 backend 与 `repository_service` 的 `vnext/` Docker context，tracked 内容由 Git tree 覆盖；Git 只记录
tracked 文件的 executable bit，普通权限模式由闭包单独摘要 `vnext/` 下 tracked 路径、祖先目录和 context
根的本机 `0o7777` 模式。通过 `vnext/.dockerignore` 后仍进入 context 的非 Git 文件和目录按相对路径、类型、权限和内容摘要。
当前摘要器遇到 Dockerfile 专属 ignore 文件或未建模的 ignore 语法时失败关闭，加入此类规则前须扩展并测试闭包实现。

来源 V 必须满足：该包在该次权威 runner 中实际运行并通过；worktree clean；日志记录起止 HEAD；整次
runner exit 0。只运行部分包的权威 runner 也可作为来源。当前 V 上闭包有变化的包都必须实际运行并通过。
carried 计算必须为每个包设置与来源 V runner 相同的 `HYPOTHESIS_STORAGE_DIRECTORY`
（`<TMPDIR>/gateway-runner-hypothesis/<包名>`；TMPDIR 未设置或为空时为 `/tmp`）；该目录须不存在，若有残留会使
`hypothesis-storage` 组件变化并要求运行。worktree 内 `.hypothesis` 仅用于开发者 focused 测试。
handoff 逐包记录总摘要、运行或沿用、来源 V 与来源日志。链式沿用必须直接引用最初实际运行该包的 V，
不得把一次沿用结果当作新来源。manifest 比较只证明闭包相等；它不替代来源 runner 的 clean、包通过、
整体 exit 0 与 HEAD 日志要求。

按包沿用与镜像身份等价分别判定：包沿用决定当前 V 上哪些包需要运行，镜像身份等价决定 V..H 的容器结果能否
carried。backend manifest 覆盖其 Compose 旅程使用的所有镜像构建上下文、Dockerfile、Rust workspace、
Docker build 设置与实际选择的本机 image ID（启用 prebuilt 时包括本机镜像清单），因此 backend 沿用时，
同一次权威 runner 的 backend Compose 旅程一并沿用；V..H
仍须独立满足下文的镜像身份等价。项目最终门禁与发布门禁始终运行全部六包；其他阶段按范围与闭包规则选择。

### 内网构建环境变量（仅记录名与语义；不得写入 lockfile 或 production runtime）

Host 准备使用 `GATEWAY_DEV_DEPENDENCY_MODE=internal` 时须显式提供 `UV_INDEX_URL` 或 `UV_DEFAULT_INDEX`；默认 `pypi` 在同步时剥离机器级 index，保持 lock 的 canonical PyPI identity。`GATEWAY_DEV_OFFLINE=1` 使用 `uv sync --locked --offline`，不代替 runner 的 `UV_OFFLINE=1`。
`run-tests.sh`、`prepare-dev-dependencies.sh` 与 `build-repository-service-image.sh` 均接入 `uv-consume.sh`。普通 `run`/`sync` 默认 `--locked`，隔离 ambient index/config；`--no-sync` 先只读 `uv lock --check --offline` 再 `uv run --locked --no-sync`，不得以自动 sync 替换待验证 wheel。消费前后比较五锁 SHA，漂移即非零退出、不自动 restore；测试不得隐式改锁，依赖变更须显式授权并重新同步环境。

Docker build 的 `GATEWAY_DOCKER_BUILD_NETWORK` 由 `deploy/compose.yaml` 与 `build-repository-service-image.sh` 读取，默认分别为 bridge 与 `host`。`GATEWAY_BACKEND_UV_BOOTSTRAP_*` / `GATEWAY_REPOSITORY_UV_BOOTSTRAP_*` 仅为 build-time 参数，不进入 production runtime ENV。Compose 测试客户端镜像在 Linux nested LXC 中默认用 Docker `host` build 网络，可设 `GATEWAY_DOCKER_BUILD_NETWORK=default`；不改变 production Compose 服务网络边界。

| 变量 | 阶段 | 说明 |
| --- | --- | --- |
| `GATEWAY_DEV_DEPENDENCY_MODE` | host 准备 | `internal` 需显式 index；`pypi`（默认）剥离机器 index |
| `GATEWAY_DEV_OFFLINE` | host 准备 | `1` → `uv sync --locked --offline` |
| `UV_INDEX_URL` / `UV_DEFAULT_INDEX` | host 准备（internal） | 内网 PyPI mirror；不得进入 `run-tests.sh` |
| `UV_INSECURE_HOST` | host 准备 / Docker build | HTTP mirror trusted-host |
| `GATEWAY_DOCKER_BUILD_NETWORK` | Docker build | 仅 build 网络；不改变 Compose 服务 runtime |
| `GATEWAY_BACKEND_UV_BOOTSTRAP_*` | backend/worker build | build-time pip 装 uv；不进 runtime ENV |
| `GATEWAY_REPOSITORY_UV_BOOTSTRAP_*` | repository-service build | 同上 |
| `GATEWAY_P2R1_CACHE_URL` | repository-service build | retained artifact cache 根 URL |

权威 runner 与提交前静态检查须通过上述受控消费入口：

```bash
./vnext/scripts/run-tests.sh
./vnext/scripts/uv-consume.sh -C vnext/<package> run pytest ...
./vnext/scripts/uv-consume.sh -C vnext/<package> run ruff check .
```

五锁 canonical registry identity 的权威 owner 为
`backend/tests/test_canonical_lock_identity.py`。

### 测试批次与 focused 运行

权威 runner 将 backend 与 `repository_service` 分成并行主体和 serial 两遍：
`-m "(not serial) or parallel_safe" -n "$TEST_WORKERS"` 后接
`-m "serial and not parallel_safe" -n 0`。其余三个包单进程运行。`rust` 包最先运行，由 cargo 自行并行，不受 `GATEWAY_TEST_WORKERS` 影响。
两遍拆分避免 timing-sensitive 测试争用 CPU；`parallel_safe` 只包括下文经逐项隔离审查的例外，backend 当前没有此例外。其余三个 Python 包的 worker 启动开销超过并行收益，因此保持单进程。

非串行 worker 默认 `auto`，可在 CPU 充足的测试节点设置 `GATEWAY_TEST_WORKERS=48`；06/07 按上文各自并行度，不照搬该值。阶段性验证不要跑全量；日常迭代用 marker 缩小范围：

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -m unit
cd ../repository_service
../scripts/uv-consume.sh -C . run pytest -m unit          # 约 1490 项，无外部依赖，约 12 秒
../scripts/uv-consume.sh -C . run pytest -m integration   # 需要真实 dolt
../scripts/uv-consume.sh -C . run pytest -m 'serial and not parallel_safe' -n 0   # 未确认可隔离的时序敏感组
../scripts/uv-consume.sh -C . run pytest -m parallel_safe -n 4  # 已逐项审查、可进入并行批次的 serial 来源测试
```

`parallel_safe` 不是“运行较快”的别名，而是严格的隔离审查结论：测试不得依赖真实线程
或进程、sleep/wait/固定时序、网络、Dolt、Docker、socket 或共享持久化状态。测试仍可保留
`serial` 标记以记录其来源；权威入口会将 `parallel_safe` 纳入并行批次，并只对
`serial and not parallel_safe` 使用 `-n 0`。当前仅审查通过以下 4 项：

- `test_diagnostics.py::test_streaming_cleanup_error_survives_failing_log_event`
- `test_row_stream_admission.py::test_ninth_row_stream_rejected_before_response_start`
- `test_runtime_admission_ownership.py::test_shutdown_closes_admission_then_stops_cleaner_before_db_and_lock`
- `test_upload_concurrency_admission.py::test_closed_pool_denies_new_upload`

专用测试节点可通过 `GATEWAY_TEST_BASETEMP=/mnt/gateway-test-tmpfs/pytest` 将 pytest 临时工作区
放入有容量上限的 tmpfs（变量必须为绝对路径）；这不会替换 Docker named volume，也不能替代真实文件系统上的
持久化、崩溃恢复、快照和容量语义验收。权威脚本在启用该变量时，会让三个实际 Compose
e2e 文件回到真实磁盘临时目录，以避开 unprivileged LXC 下 Docker secret bind mount 的
remount 限制；其余测试仍使用 tmpfs。

不带 marker 直接运行 pytest 会执行全部测试并自动并行；结果正确，但 `serial` 组会与其他
测试争用 CPU，判定 flaky 时以脚本为准。

权威脚本的运行前提（已提交的 clean worktree、运行期间不写 worktree、整机单飞、日志记录
HEAD 与 exit code）见 [AGENTS.md](../../AGENTS.md)“跑测试”一节；不满足时结果不能作为门禁
证据。

### P2后半段的功能门禁与最终container门禁

本节保留 P2 后半段的历史阶段安排；当时的功能门禁与最终 container 门禁规则见本节与 [AGENTS.md](../../AGENTS.md)。
历史 P2 execution checklist 见 tag `docs/p2-p3-cleanup-pre-20260817`。
从P2-R4 post-audit后续修复到R5，在未触碰build/deployment boundary时，允许把镜像构建、
跨主机传输和实际Compose测试合并到R6最终候选一次执行。期间整仓功能门禁仍使用权威脚本，
只精确排除实际启动Docker的测试文件：

```bash
./vnext/scripts/run-tests.sh \
  --ignore=tests/test_import_compose_e2e.py \
  --ignore=tests/test_versioned_read_compose_e2e.py \
  --ignore=tests/test_compose_lifecycle_negative_probes.py
```

当时的延期inventory为（P2-R6-S7 已在 candidate `5f474ce2` 上收集并通过；S10 仍须在最终
P2 candidate 上重跑，不得从 inventory 删除）：

```text
tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle
```

`tests/test_compose_lifecycle_negative_probes.py` 是 expected-failure cleanup 的独立
probe（missing readiness / wrong token / wrong network / non-empty restore），不是第五个
S7 PASS nodeid，同样按精确 path ignore，不用宽泛 marker。
静态Dockerfile/Compose测试、build script/harness单测和真实Dolt integration仍属于功能门禁，
不得一并跳过。以后新增实际Docker测试时，round handoff必须登记精确path/nodeid并同步更新
调用参数；不新增宽泛`container` marker来隐式改变现有三类marker语义。

此命令不是新的全局权威入口，也不能用于Phase 2最终退出。R6必须对最终source tree运行无
`--ignore`的`./vnext/scripts/run-tests.sh`，完成production image build/provenance、镜像传输、
全部延期Compose nodeid和资源清理后，才可宣布P2完成。任何Dockerfile、production依赖闭包、
Compose/container wiring或container harness变更都会提前终止延期，并要求在所属round执行
相应容器门禁。

### P5-5E S3 compose 门禁串行（port 8000 + flock）

`test_ordered_compare_compose.py`、`test_ordered_submit_bisect_compose.py`、
`test_history_compose_e2e.py` 共享 host `127.0.0.1:8000`，**必须串行**执行。

- harness 在 `start_three_container_stack` 入口先对 `/tmp/gateway-compose-gate.lock` 加 `flock`，
  再检查 port 8000；`cleanup_compose_project_artifacts` 释放锁。并发会话会阻塞等待（默认 30 分钟上限）。
- compose project 名默认含会话成分（`GATEWAY_COMPOSE_GATE_SESSION` 或 pid），避免跨会话
  project/卷/网络碰撞；可用 `GATEWAY_COMPOSE_GATE_PROJECT_NAME` 显式覆盖。
- **S4 权威 runner 必须单飞**：不得并行跑上述三门禁或与其它占用 8000 的 compose 栈混跑。

### Docker / Compose触发式重建

镜像构建验证的是某个精确source tree的image/deployment/container runtime行为，不是所有
代码修改的默认单元测试入口。阶段迭代不要求每轮、每个提交都重建；同一轮内即使有多个触发
改动，也允许先完成相关修改，再对该轮最终HEAD构建一次。是否重建按以下边界判定。

必须重建当前HEAD并运行受影响容器门禁：

- Dockerfile、依赖锁或production依赖闭包、基础镜像、OS package、build/save/load脚本发生变化；
- entrypoint、Compose、环境变量接线、healthcheck/readiness接线发生变化；
- UID/GID、ownership/mode、volume/mount、socket、pidfile、broker/helper协议或生命周期发生变化；
- startup/shutdown、signal、子进程监督或filesystem行为的正确性依赖容器用户、PID namespace、
  mount namespace或双UID隔离；
- 修改实际Docker/Compose e2e、container harness，或评审结论要声称当前HEAD已经通过容器门禁；
- 阶段退出、S3 ready、发布或最终production gate。发布与最终production gate必须在最终候选
  HEAD重新构建并核对provenance，不能用祖先提交的镜像替代；阶段退出与S3 ready可按下文
  “镜像身份等价与结果沿用”沿用已验证提交的结果。

通常可以延期到必要节点：

- 可由focused/unit/integration完整覆盖的纯Python内部算法、SQL、projection或状态机修改；
- 不改变production artifact的测试、注释和普通文档修改；
- 只读审核，以及没有修改image/deployment/container-only runtime boundary的修复轮。

“可以延期”不等于旧镜像仍代表当前HEAD。除非满足下文的镜像身份等价，旧Compose结果只能
作为祖先提交的回归证据；报告必须把当前HEAD的container gate标为`deferred`或`stale`，
不得写成“当前HEAD PASSED”。若后续任一改动触发上面的强制条件，应在相关改动收敛后重建，
不必为中间提交重复构建。

### 镜像身份等价与结果沿用

适用范围：阶段退出与S3 ready；发布与最终production gate不适用。目的是让门禁之后只改
handoff、评审报告或普通文档的提交不必重跑Compose，而不是放宽容器门禁本身。

已验证提交`V`与最终HEAD同时满足以下条件时，`V`的容器门禁结果视为最终HEAD的结果，
记为`carried`：

1. **门禁运行合格**：`V`是已提交的clean worktree；全量或容器门禁由权威入口执行；日志记录
   开始与结束时的`git rev-parse HEAD`和明确的exit code；运行期间未写worktree，也未提交或
   重建其他镜像。若client e2e镜像revision label与HEAD不符，允许门禁在本机正常重建该镜像并更新本机tag；实施者不得手工`docker rmi`。在dirty worktree或临时index tree上的运行不能作为`V`。
2. **diff不触及容器边界**：`git diff --name-only V HEAD`中没有上文“必须重建”前五项所列的
   内容，也没有Docker/Compose e2e测试、container harness或其support模块。
3. **镜像身份相等**，逐个镜像核对：
   - 带`gateway.p2r1.build-input-revision`与`gateway.p2r1.source-tree-sha256` label的镜像
     （repository-service）：在最终HEAD用`build_context_digest.py identity`重算，两项都等于`V`
     门禁所用镜像的label。`org.opencontainers.image.revision`随提交变化，不参与比较。
   - 没有source identity label的镜像（backend、worker）：以backend包的闭包manifest判定。在运行
     `V`门禁的同一worktree中检出最终HEAD，用`python3 -I vnext/scripts/test_input_closure.py manifest
     --package backend`计算，与`V`那次runner起始时记录的backend manifest用`compare`逐项比较，必须
     为“可沿用”。完整输入成分见 [Hypothesis 隔离与按包闭包沿用](#hypothesis-隔离与按包闭包沿用)。
     专用测试节点使用containerd image store，同一棵树
     连续两次全缓存构建的image ID也不相同（G12终审实测），因此不再比较image ID（owner决议DC34）。
     manifest 包含 worktree 本机权限、非 Git context 内容与测试缓存等本地状态，Git 不会规范化这些状态；
     换 worktree 可能得到不同摘要，因此 G13 复核后保留“同一 worktree”限制（治理修订计划 G6b）；不得用另一个
     worktree 的结果判定“等价”或“不等价”。同一 worktree 也意味着同一节点（owner 决议 DC36）。
     因此阶段的门禁 worktree 保留到该阶段 exit 合入之后再清理（owner 决议 DC51）。

任一条件不满足，就在最终HEAD重建镜像并重跑受影响的容器门禁。等价判定由实现方记录，独立
评审逐项复核；复核不通过时不得以`carried`关闭finding。

按包沿用与 V..H 镜像等价的关系、backend Compose 随包沿用及合格来源条件，统一见
[Hypothesis 隔离与按包闭包沿用](#hypothesis-隔离与按包闭包沿用)；阶段退出绑定最终 HEAD 仍须满足本节全部条件。

避免重复执行：权威runner的backend批次已包含backend Compose旅程。同一提交上runner已运行
并通过的Compose旅程不再单独重跑，provenance从该次运行的
`vnext/backend/tests/support/.last_compose_gate_provenance.json`复制到worktree外的日志目录。
只有需要单独复现失败或runner未覆盖的nodeid时，才单独运行Compose旅程。

### 每轮评审记录

实现汇报和独立评审都必须记录Docker/Compose决策，即使决定不构建。最少包含：

```text
Current HEAD: <sha>
Container rebuild required: yes | no
Reason: <命中的触发项，或未触碰container boundary的依据>
Last verified image revision: <sha | none>
Last verified source-tree/image id: <digest | none>
Container gate for current HEAD: passed | carried | deferred | stale | not-applicable
Carried from: <V sha、门禁日志、逐镜像身份比较结果 | none>
Deferred gates/nodeids: <精确命令、path或nodeid>
Required execution point: <本轮结束 | 阶段最终候选 | S3 ready前 | 发布前>
```

若`Container rebuild required: yes`，评审不得用旧镜像结果关闭相关finding；若为`no`，评审应
检查理由是否确实不依赖容器边界。无论中间轮次如何决定，阶段最终候选都必须让容器门禁结果
绑定到最终HEAD：要么在最终HEAD执行权威Compose/production gate，要么在阶段退出、S3 ready
节点满足上文镜像身份等价并记为`carried`。

## 前端测试（FD7）

来源：[前端 kickoff §6](../frontend-vnext/frontend-kickoff.md#6-测试与证据fd7)（owner 2026-11-02 确认，FD7）。
本节只规定前端测试的运行位置、工具链与证据；前端测试分层见 kickoff §4.2。

### 位置与入口

前端工程位于仓库根目录 `frontend/`，不在 `vnext/` 下。backend 与 `repository_service` 的闭包和镜像身份以整个
`vnext/` 为 Docker context，前端不进入后端测试闭包，前端提交不影响后端按包沿用与 carried 判定。前端权威入口为
`frontend/scripts/run-tests.sh`，与 `vnext/scripts/run-tests.sh` 相互独立。

### 节点

与后端相同，前端测试不在开发主机上运行：

| 用途 | 节点 | 内容 |
| --- | --- | --- |
| 日常开发 | `ct109-gw-dms-07` | 类型检查、lint、单元测试、构建、截图、模拟接口 e2e |
| 集成调试 | `ct108-gw-dms-05` | 连真实 backend 的 e2e；其他前端调试按协调窗口安排 |
| 证据 | `ct108-gw-dms-04` | 阶段退出时在 clean、已提交 worktree 上用权威入口完整运行一次 |
| — | `ct108-gw-dms` | 前端不使用 |

### 工具链镜像

测试节点宿主机不安装 Node.js。前端测试在固定版本的工具链镜像中运行，镜像包含 Node.js、浏览器与所需系统库：

1. 在 CT201 取得镜像，经 `docker save`/`docker load` 通过获准的局域网传到实际使用的节点（07、05、04）。
2. 跨节点身份比较 config digest 与全部 RootFS DiffID（同 DC67），不比较 `docker inspect` ID。身份不符即停止。
3. 镜像版本变化时按同一流程重新取得与传输。

### npm 依赖缓存（DC67）

在 CT201 依 `package-lock.json` 取得 npm 缓存，经获准的局域网预填充到实际使用的节点；运行时把缓存挂载进工具链
容器，在容器中执行 `npm ci --offline`。缓存缺失即停止，补齐预填充后从头运行。DC67 关于转发代理的限制同样适用：
04 证据运行不经任何转发代理。

### 节点协调（DC70 补充）

- 类型检查、lint、单元测试、构建和模拟接口 e2e 不涉及 Dolt 与 Compose，不获取节点占用标记，可与后端调试并行。
- 连真实 backend 的 e2e 要起 Compose 栈（共享 host 端口 8000），按 DC70 补充获取整机占用：
  `mkdir /home/dev/gdds-node-busy.d` 原子获取，失败即等待、不抢占；获取后写入会话名、用途与开始时间（UTC）；
  运行与清理完成、确认无本次容器与进程后删除。仍须满足 AGENTS 的整机单飞与运行前残留检查。
- 某节点占用标记的用途写明为计时测量时，前端在该节点上的任何运行（含不需要占用标记的项目）都等待其释放。
- 07 与 04 同宿主，但按 Owner 最新资源安排可自主运行，不建立常规整宿主互斥或资源报批；保留本节点规则，实际干扰时协调。

### 日志与 handoff

与后端相同：日志写到 worktree 外，开头记录 `hostname`、起止时间、起止 `git rev-parse HEAD` 与入口自身的 exit
code（经 `tee` 时用 `set -o pipefail` 或 `${PIPESTATUS[0]}`），并记录日志 SHA256。handoff 另记：

- 每次运行所在节点；
- 工具链镜像 tag、config digest 与全部 RootFS DiffID；
- npm 缓存来源：来源节点/提交、缓存摘要与预填充时间；不记录凭据。

### 截图验收

FE2 起，在 1280 与 1920 两种宽度下对 [UI 优化方向](../frontend-vnext/ui-optimization-direction.md) §7 草图清单中的每个页面与状态截图（模拟接口，固定示例数据）。截图与运行日志
存于 worktree 外的证据目录并记录 SHA256。审核会话逐张对照 `docs/frontend-vnext/sketches` 核对布局、层级、
语义色、按钮层级、禁用原因与焦点样式，不做像素级比对（示例数据不同）。与草图不符处要么修正，要么作为偏差列入
handoff 交 owner 确认。

### 真实 backend e2e

依据 [FE3a handoff §8](../frontend-vnext/fe3a-handoff.md#8-给-agents-与-testing-conventions-的建议条文41)，运行框架与场景见 [FE3 kickoff §4](../frontend-vnext/fe3-kickoff.md#4-真实-backend-e2e-的运行框架)，M1 范围和判断见 [§8.4](../frontend-vnext/fe3-kickoff.md#84-m1打包峰值内存)。

独立入口 `frontend/scripts/run-real-backend-e2e.sh` 不并入 `run-tests.sh`，使用独立 Playwright 配置与目录；`--session` 必填并写入占用标记和日志。脚本自行获取、核对和释放占用；调用前不要手工获取，即使同会话已有标记也以 exit 3 退出。
输入来源遵循 [FE3 kickoff §4.6（Q10）](../frontend-vnext/fe3-kickoff.md#46-测试身份与初始数据)。

**占用与清理顺序：**

1. 脚本以 `mkdir /home/dev/gdds-node-busy.d` 原子取得占用，写入会话名、用途、UTC 开始时间、hostname、worktree 与 HEAD；目录存在即退出，不抢占。再用 `flock -n` 取得 `/tmp/gateway-compose-gate.lock`，失败退出。
2. 核对没有发布 8000 的容器、`/proc` 中的 Dolt 进程，以及本脚本命名前缀的 Compose 项目、卷、网络和工具链容器残留；不满足即退出，不清理他人资源。
3. 退出（含失败与可捕获中断）先停止并删除本次工具链容器、保存 Compose logs，再按 kickoff §4.8 `down -v --remove-orphans --rmi local`，按项目 label 清理本次残留卷/网络，删除本次 RS tag 和 secret 目录。不删除共享镜像、后端遗留镜像或他人资源。
4. 核对本次容器、卷、网络与进程已无残留，8000 空闲且无 Dolt；成功后先释放 flock，再删本会话 marker 文件，最后 `rmdir` busy 目录。核对失败保留占用，标为 `cleanup-failed`，非零退出交 owner；顺序与核对由脚本执行。

**Compose secret：**session/token 文件只写在 worktree 外运行目录，权限 `0644`（或保证服务用户可读）；`0600 root` 会使服务无法读取。

**M1 方法与报告：**每次测量新建 browser/context，经浏览器级 CDP 枚举 PID（不可用时按 kickoff §8.4 的 `/proc` 方法识别），记录各进程；确认上传前向 `/proc/<pid>/clear_refs` 写 `5`，以重置后的 `VmHWM` 为基线，同时记录 `VmRSS`，请求发出后读取 `VmHWM`，峰值增量为后测 `VmHWM` 减重置后 `VmHWM`。判定只看 renderer，浏览器主进程增量单列报告；`performance.memory` 仅作参考。包大小取 multipart manifest 的 `size_bytes`，不用整个 multipart body；打包耗时取页面 `data-phase` 对应 packaging 阶段，不用 click→request。逐次报告 renderer/主进程增量、manifest size、打包耗时，多次测量报告中位数与最大值；场景、次数、FE3c 单次与三次测量的差异说明、附加采样和阈值均按 kickoff §8.4，不在此另设标准。

**日志字段：**日志与证据放 worktree 外，结束写日志 SHA256 旁注；沿用 FD7 的缓存来源与预填充记录，并记：

- 开头/结尾 hostname、UTC 时间、HEAD、`HEAD:frontend`/`HEAD:vnext` 树、clean 状态，结尾入口 exit code；
- 占用 marker 内容及获取/释放时间、flock 路径及获取/释放时间、前后残留核对结果；
- 工具链身份沿用 FD7；依赖、RS、backend/worker 的每次运行身份按 [FE3 kickoff §4.3](../frontend-vnext/fe3-kickoff.md#43-镜像)：依赖镜像 tag、dependency-input label、本机 image ID 与全部 `RootFS.Layers`；RS tag、本机 ID 与 build-input/source-tree/revision labels；backend/worker 本机 ID；Docker/Compose 版本。跨节点传输时才比较 config digest 与全部 DiffID 并记入 handoff，不要求每次运行 save 依赖镜像；
- npm 缓存归档 SHA256 与来源提交；
- Compose 项目名、网络 ID、工具链容器名；运行时 OpenAPI SHA256 与比对结果；
- 逐 scope 仓库 ID、`INITIAL` 提交 ID、身份名和权限，不含 token；
- 用例名称、起止时间与结果；每次 bundle 的 `Content-Length`、实收字节、`ETag`；
- 清理核对结果；t1 另记输入文件数、字节数、逐文件 SHA256 聚合值、M1 指标与各步骤耗时（只报告）。

Playwright trace、Compose 日志和 t1 参考截图只留节点，不入仓库或 handoff 正文；handoff 只记路径与 SHA256（trace 可能含临时 token 和输入数据，截图可能含真实值）。

## Marker 分层

`unit`、`integration` 与 `serial` 在全部包的 `[tool.pytest.ini_options]` 中声明，
并由 `--strict-markers` 强制：拼错的 marker 会让收集直接失败。`repository_service` 与
backend 还声明 `parallel_safe`，记录经逐项隔离审查、可进入并行主体的 serial 来源例外。

| Marker | 含义 |
| --- | --- |
| `unit` | 无重量级外部依赖，可全并发运行 |
| `integration` | 需要真实 dolt、子进程或落盘状态 |
| `serial` | 时序敏感，不得与其他测试争用 CPU |
| `parallel_safe` | serial 来源中已逐项确认隔离、允许进入并行主体的例外 |

`repository_service` 的 `tests/conftest.py` 统一处理分类与门禁：

- 请求 `import_layout` / `import_provider` fixture 的测试**自动**判定为 `integration`，
  无论是否写了装饰器。这两个 fixture 会真实执行 `dolt init`。
- 未被判定为 `integration` 的测试自动补 `unit`。
- 标了 `integration` 而 dolt 不可用时统一 skip；**不要**在测试里手写
  `@pytest.mark.skipif(not dolt_available(), ...)`，门禁只有一处。
- 标了 `serial` 的测试自动获得 `xdist_group("serial")`。

backend 的 `tests/conftest.py` 保留默认 `unit` 分类：未标 `integration` 的测试（包括保留
`serial` 的 unit 测试）自动获得 `unit`；serial 测试自动获得
`xdist_group("serial")`，除非它们显式标了 `parallel_safe`。所有通过
`requires_dolt` 或其他方式依赖真实 Dolt 的 backend 测试显式标 `integration`。

G11 将 backend 也按上述两遍执行。kickoff base 收集到 2,847 项，其中 2,665 项有
`unit`、205 项有 `integration`、56 项有 `serial`；后三项计数会重叠。
改动前 7 个 Compose 旅程文件耗时约 1,575 秒，其他 serial 用例约 38 秒，剩余用例约
100 秒。Compose 旅程的精确耗时构成见 G11 handoff。

### 新增测试时

- 测试通过 `lifecycle_settings()`、`ServiceRuntime.start()`、`DoltRunner()` 等方式
  间接依赖真实 dolt 的，**必须**显式加 `@pytest.mark.integration`。fixture 自动判定
  只覆盖 `import_layout` / `import_provider` 两个入口，覆盖不到函数体内的直接构造。
- 依赖固定时间预算（`Event.wait(timeout=...)`、`thread.join(timeout=...)`、
  子进程 sleep 与 stream timeout 的相对关系）的测试，必须加 `@pytest.mark.serial`。

### 分类正确性怎么验

仅在专用测试节点按占用规则把 dolt 移开再跑 `-m unit`，任何错分类都会直接失败：

```bash
mv /usr/local/bin/dolt /usr/local/bin/dolt.parked
uv run pytest -m unit; mv /usr/local/bin/dolt.parked /usr/local/bin/dolt
```

这是唯一可靠的判据，静态扫描做不到。建立本规范时用它发现了 13 个漏标的测试。

## 性能约束

### 不得让纯逻辑测试付真实建仓代价

验证纯解析、纯校验、纯类型映射的测试，不得引入会执行 `dolt init` 的 fixture。
典型反例是「用 `import_provider` 建真实仓库，再把 `run_cli` 整个 mock 掉」——真实
仓库状态在断言路径上根本没被用到，却让每个测试多付数百毫秒。

`read_catalog` 一类方法只经 `self._cli.query_json` / `self._cli.catalog` 与外部交互，
行宽与 schema 校验都在纯函数里，直接对纯函数断言即可。

### 同构用例必须收敛为共享参数表

payload 与期望错误消息之外完全相同的用例，不得复制粘贴成多个测试函数，要收敛为
`tuple[tuple[bytes, str], ...]` 形式的模块级共享表。现有范例见
`tests/test_import_provider.py` 的 `MALFORMED_JSON_SHAPES`、`MARKER_FAULT_JSON_SHAPES`、
`CATALOG_ROW_SHAPE_FAULTS`。

复制粘贴的直接后果已经出现过：`test_catalog_count_rejects_extra_cell` 的 payload 与
同文件另一个已参数化用例逐字节相同，是纯冗余。

### 子进程要按批构造，不要按次 spawn

构造测试前置状态时，避免在循环里反复 spawn 外部进程。进程启动开销会主导测试耗时，
在并行执行下还会成为整个套件的关键路径。

### 私有 HOME 必须离线

`DoltRunner` 给子进程设置私有 `HOME`，并在其中预置 `.dolt/config_global.json` 关闭
dolt 的版本检查与 metrics 上报。该写入发生在 `DoltRunner` 构造期，属于 provider
process boundary 的生产语义，不仅服务于测试提速。全新 HOME 下 `dolt version` 会联网
查询最新发布版本，单次 3~5 秒。任何新增的、会创建全新 dolt HOME 的代码路径都必须
沿用这一预置，否则既拖慢测试，也违反 offline provider 边界。

## 全局风险分级与测试预算

权威规则见
[Proportional Assurance and Risk-Based Verification Policy](refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md)。
该规则适用于Repository Service之外的Phase 3 capability、Phase 4 Operation Runtime、Phase 5
业务纵切以及后续优化、cutover和production hardening。

新增或修改功能时，先标出测试对象：

| 对象 | 测试重点 |
| --- | --- |
| 权威/不可逆事实与外部安全边界 | Contract、negative、transaction/CAS/idempotency、关键crash/restart和scope隔离 |
| 可恢复durable workflow | claim/terminal、retry/takeover、一个代表性矛盾与人工修复分支 |
| derived/temporary/rebuildable对象 | 正常/边界输入、失败不污染权威事实、bounded重试/诊断 |
| 私有helper/adapter/纯转换 | 最小输入输出、类型和owner contract；不复制production状态机 |

测试设计约束：

- 证明业务语义屏障，不默认在每两个syscall、transaction statement或线程事件间注入；
- 每个不变量只有一个权威owner；其他层只保留必要integration smoke；
- 参数矩阵的每个维度必须会改变行为或错误边界，否则合并；
- 测试按Contract行为命名，不用`rNN_*`、finding编号或实现技巧命名；
- production机制删除时同步删除mock、fixture、probe和historical proof；
- 单文件/单功能测试明显主导所在包，或新增用例主要证明私有interleaving时，暂停追加并复核
  风险等级、owner和重复性。没有机械LOC比例，通过拆文件不能规避复核。

新增独立UID/helper/service、自定义IPC/capability、持久evidence状态机、sidecar/quarantine、
tombstone或同机恶意actor调度证明，不是普通测试扩展；必须先有owning Contract/ADR接受的威胁、
损失和验收场景。安全探针可以交给实现者执行，但探针不能自行扩大当前威胁模型。

## Artifact cleanup 比例化验证（S2）

权威边界见
[ADR 0012](refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)：
V1把同euid本地进程视为可信部署组件，不对抗恶意pathname换名。测试必须证明功能自身在
协作并发、崩溃和普通I/O错误下健壮，不得把directory-broker、inode-CAS unlink、双UID、
SCM_RIGHTS、pidfd或sidecar收敛重新设为S2/S3硬门。

保留的核心验证按业务后果组织：

- eligibility纯逻辑：SUCCEEDED、ordinary FAILED TTL、orphan TTL与protected引用；
- 正常成功删除、eligible `ENOENT`幂等、I/O失败重试且不改变commit/result；
- PENDING/QUEUED/RUNNING/manual-recovery保留，admission pin与cleaner协作竞态；
- server-owned root、caller path拒绝、symlink/regular-file/scope与跨repository边界；
- 业务成功持久化前、成功后cleanup前、cleanup失败后重试三个crash/restart语义屏障；
- bounded candidate pagination、shutdown无遗留线程，以及一条legacy sidecar/DB fixture路径。

以下不再是权威验证：

- `r8_*`、`r9_*`至`r22_*`按历史修复轮次命名的quarantine/detach/unlink-verify/stage、
  generation、receipt、residual proof或broker syscall-window矩阵；
- 同euid恶意ancestor/pathname替换、broker partial frame、capability/peer角色、fd/pidfd与双UID
  隔离证明。生产机制删除时对应测试一并删除，不保留mock实现考古。

不可逆或大故障域不变量不能因本次简化而降级：Dolt commit/main CAS、control DB transaction、
跨repository/root误操作和protected artifact误删仍需强验证。但测试语义屏障，不穷举每两个
系统调用之间的调度窗口。同一Contract不变量只保留一处权威断言，同构shape用共享参数表；
保留的测试不得继续使用round编号命名。

## 历史基线

| 阶段 | `repository_service` 全量耗时 |
| --- | ---: |
| 整改前 | 46m47s |
| 关闭 dolt 版本检查后 | 4m14s |
| 叠加 xdist 并行后 | 2m03s |
| 长历史 fixture 改批量提交后 | 63s |

整仓五个 Python 包合计 1031 项测试，`run-tests.sh` 全程约 1m07s。

测量过程原文见 tag `docs/p2-p3-cleanup-pre-20260817` 中的
`docs/backend-vnext/notes/test-suite-runtime-investigation.md`。

### G11 与静态检查历史观测

G11 kickoff base
`676110a74b68` 的 backend 基线为 2,847 passed；marker 数为 `unit` 2,665、
`integration` 205、`serial` 56（marker 可重叠）。`--durations=0` 的可见阶段耗时为
Compose 1,575.36 秒、其他 serial 37.97 秒、其余用例 100.30 秒，基线墙钟 1,717.23 秒。
Compose 占 backend 基线约 91.7%；细节与日志见
[G11 handoff](refactoring/formal/plans/p5-arch-closure-g11-handoff.md)。

整理前 AGENTS（`4b224865e4`）曾记录：mypy 增量缓存命中时五个包合计约 1.5 秒。该值为当时的历史观测，不作为当前耗时承诺；五包提交前静态检查要求仍见 [AGENTS「提交前」](../../AGENTS.md#提交前)。

### 历史阶段说明

以下保留已退出阶段的一次性授权，不扩为新节点的常设用途。

Owner 于 2026-11-07 按 DC87/DC33 另明确授权：06 在本次 S2b E 最终验收运行 fresh 完整 t1–t3 功能/容量旅程，与 04 六包及 Compose 跨节点并行；t4 按独审具体依据沿用。此为本轮真实数据用途扩展，不改变 04 权威 runner/carried 与 CT108 正式性能职责；06 仍按本节点占用、clean 提交及离线证据规则执行。

# Backend vNext Refactoring Environment Preparation

状态：Draft

记录日期：2026-07-15

适用阶段：Phase 0 收尾、Phase 1 环境与 walking skeleton、Phase 2 Repository Service bootstrap

用途：为后续独立对话中的重构环境配置提供可执行输入。本文件记录候选版本、目录、安装顺序和验收门禁，不替代正式架构、contract 或 ADR。环境实际创建并通过验证后，应将最终版本、命令和差异写入 Phase 1 执行台账；长期约束再回写正式文档或 ADR。

## 1. 已确认前提

- 本轮重构不要求兼容旧 API、旧内部 DTO、旧持久化 schema 或旧数据。
- 旧代码只用于提取业务规则、fixture、golden output、digest、benchmark 和人工行为参考。
- 新代码不得 import 旧业务模块，也不通过 legacy adapter 将旧实现包装为正式能力。
- 重构开始时选择一次新的稳定技术基线；基线通过验证后锁定。
- 开发、CI、镜像构建和部署不得自动追踪最新版本。后续升级必须是显式变更并重新通过测试。
- Python 控制面与 Rust 数据面采用 Phase 1 的 PyO3 + Arrow 粗粒度 walking skeleton；第一阶段不建立独立 Rust 网络服务。
- Repository Service 是独立进程、镜像和数据所有权边界，但初期仍与业务系统保留在同一个 Git 仓库。

“最新版本”在本文中的含义是：截至记录日期的最新正式稳定版，目标 Linux 平台有可用发行物，并且需要通过本文验证矩阵后才能成为锁定基线。预发行版、仅源码发布且无法在目标镜像稳定构建的版本不进入基线。

## 2. 目标仓库布局

```text
legacy/
  backend_vnext/                  # 旧源码；保留原 Python package 名称
  README.md                       # 冻结范围、oracle 用法和修改规则

vnext/
  backend/                        # 新 Python 业务模块化单体
    .python-version
    pyproject.toml
    uv.lock
    src/gateway_backend/
    tests/

  rust/                           # Rust compute workspace
    rust-toolchain.toml
    Cargo.toml
    Cargo.lock
    gateway-compute-core/
    gateway-compute-python/

  repository_service/             # 独立 Repository Service
    .python-version
    pyproject.toml
    uv.lock
    src/gateway_repository_service/
    tests/
    Dockerfile

  deploy/
    compose.yaml
    env/
```

约束：

- 旧目录从 `backend_vnext/` 移至 `legacy/backend_vnext/`，但内部 package 名称暂不改动，避免破坏 oracle 的 import 语义。
- 新后端 package 使用 `gateway_backend`，不得再次使用 `backend_vnext`。
- `backend` 与 `repository_service` 是两个独立 uv project，分别维护 `pyproject.toml` 和 `uv.lock`，不使用一个共享运行环境。
- `rust` 是一个 Cargo workspace；`gateway-compute-python` 构建 native wheel，算法放在 `gateway-compute-core`。
- 不预创建完整业务目标树。只创建 walking skeleton 实际使用的 package、crate 和测试。
- `.venv/`、`target/`、native wheel、Dolt 数据、artifact、SQLite 文件、日志和 `.env` 不进入 Git。

## 3. 候选版本基线

以下版本在 2026-07-15 从官方发行源查询。它们是环境配置的首选输入，不是未经验证即可进入生产的承诺。

### 3.1 平台和构建工具

| 组件 | 候选版本 | 用途与约束 |
| --- | --- | --- |
| 目标平台 | Linux x86_64, glibc | Phase 1 唯一必须支持的平台；其他平台后续按需求增加。 |
| Python | 3.14.6 | 最新 Python 3.14 稳定补丁版；固定到 `.python-version` 和基础镜像。 |
| uv | 0.11.28 | Python 安装、依赖解析、虚拟环境和锁文件。 |
| Rust | 1.97.0 | 固定在 `rust-toolchain.toml`；安装 `rustfmt`、`clippy`。 |
| Cargo | 随 Rust 1.97.0 | 由 Rust toolchain 管理，不单独浮动。 |
| maturin | 1.14.1 | 构建 PyO3 wheel。 |
| Dolt | 2.1.11 | Repository Service 专用；固定 binary/image 版本。 |
| Docker Engine | 29.6.1 | 开发宿主机候选版本；允许更高 patch，但实际版本进入执行台账。 |
| Docker Compose | 5.3.1 | 使用 `docker compose` plugin；不使用旧 `docker-compose` Python 工具。 |
| Python runtime image | `python:3.14.6-slim-bookworm` | 固定完整 tag，首次拉取后记录 manifest digest；不使用 `latest`。 |
| Rust builder image | `rust:1.97.0-bookworm` | builder 使用；通过 uv 安装精确 Python 3.14.6。 |

不建议使用 Alpine 作为 Phase 1 基础镜像。PyArrow、Polars、Pydantic Core 和 PyO3 wheel 的 glibc 路径更接近预期生产环境，也减少 musl 差异。

### 3.2 Python 运行依赖

| 包 | 候选版本 | 现有代码/新架构用途 | 首次加入阶段 |
| --- | --- | --- | --- |
| `fastapi` | 0.139.0 | HTTP interface；旧代码已使用。 | Phase 1 最小入口 |
| `pydantic` | 2.13.4 | interface/application/capability DTO 与版本化 boundary model；旧代码已使用。 | Phase 1 |
| `pydantic-settings` | 2.14.2 | 显式环境配置，不使用散落的 `os.environ`。 | Phase 1 |
| `uvicorn` | 0.51.0 | 开发和单进程 HTTP server；旧代码已使用。 | Phase 1 |
| `httpx` | 0.28.1 | HTTP contract test 和后续 remote client；旧代码已使用。 | Phase 1 测试 |
| `polars` | 1.42.1 | Python/Polars reference、已有表达式和 profile；旧代码已使用。 | Phase 1/3 按实际调用加入 |
| `pyarrow` | 25.0.0 | Python/Rust 批量边界、Arrow/Parquet schema 和 artifact。 | Phase 1 walking skeleton |
| `python-multipart` | 0.0.32 | 上传接口解析。 | Upload Preview slice 前加入 |

核验事实：`pyarrow 25.0.0` 提供 CPython 3.14 的 Linux x86_64 wheel；`polars-runtime-32 1.42.1` 提供 `cp310-abi3` Linux x86_64 wheel，可由 CPython 3.14 使用；`pydantic 2.13.4` 实际解析的 `pydantic-core 2.46.4` 提供 CPython 3.14 Linux x86_64 wheel。上述精确候选组合已使用 uv 按 Python 3.14/Linux x86_64 完成依赖解析；环境配置仍必须实际执行一次安装和 import smoke test。

不要因为旧项目曾经间接安装某个包就把它加入新项目。`SQLAlchemy`、数据库 driver、对象存储 SDK、`orjson`、任务队列、遥测 SDK 等只在真实 port/ADR 和首个消费者出现时加入。

### 3.3 Python 开发和验证依赖

| 包 | 候选版本 | 用途 |
| --- | --- | --- |
| `pytest` | 9.1.1 | 单元、contract、integration 测试。 |
| `pytest-asyncio` | 1.4.0 | async interface/client/runtime 测试。 |
| `hypothesis` | 6.156.6 | scalar、ordering、digest 和 Python/Rust differential property tests。 |
| `pytest-cov` | 7.1.0 | 有针对性的覆盖率报告；不以覆盖率替代 contract 门禁。 |
| `ruff` | 0.15.21 | lint 和 format。 |
| `mypy` | 2.3.0 | Python 静态类型检查。 |
| `maturin` | 1.14.1 | 本地和 CI native wheel 构建。 |

Phase 1 先使用这些最小工具，不同时引入多个 formatter、linter 或 type checker。

### 3.4 Rust crate 候选版本

| crate | 候选版本 | 用途与约束 |
| --- | --- | --- |
| `pyo3` | 0.29.0 | Python extension boundary；首版使用 `extension-module`，不要求 abi3。 |
| `pyo3-arrow` | 0.19.0 | PyArrow/Rust Arrow 互操作；该版本依赖 PyO3 0.29 和 Arrow 59。 |
| `arrow` / `arrow-*` | 59.1.0 | Rust Arrow arrays、schema、compute。只启用实际需要的 feature。 |
| `parquet` | 59.1.0 | Parquet artifact 读写。只启用实际需要的 feature。 |
| `serde` | 1.0.228 | 小型 metadata/config DTO。 |
| `serde_json` | 1.0.150 | 版本化 JSON metadata；canonical digest 不直接依赖默认 JSON 输出。 |
| `thiserror` | 2.0.18 | core/domain error 类型。 |
| `sha2` | 0.11.0 | 与正式 digest contract 对齐后使用。 |
| `proptest` | 1.11.0 | Rust property tests。 |
| `criterion` | 0.8.2 | 独立 kernel benchmark。 |
| `rayon` | 1.12.0 | 仅 Phase 7 或 benchmark 证明需要时加入，不在 walking skeleton 默认启用。 |

Python `pyarrow 25.0.0` 与 Rust Arrow `59.1.0` 的版本号不需要一致。兼容边界是 Arrow C Data/Stream 或 IPC/Parquet schema 与实际 round-trip 测试，不以版本号相等作为判断依据。

### 3.5 暂不选择的组件

| 组件 | 原因 | 何时决定 |
| --- | --- | --- |
| Domain database 和 driver | 正式架构尚未决定数据库和事务/outbox 策略。 | 对应 persistence ADR 前 |
| 对象存储和 SDK | Artifact 存储、上传和授权方式尚未收口。 | Repository/artifact ADR 前 |
| Repository transport | REST、gRPC、Arrow Flight 或组合尚未决定。 | Phase 2 开工前 |
| Redis、消息队列、Celery 等 | Phase 1/4 没有证据需要；Operation Runtime 有自己的持久化边界。 | 真实可靠性或规模需求出现后 |
| Kubernetes | Phase 1 只需可复现 image/Compose 环境。 | 生产部署平台决定后 |
| 独立 Rust worker/service | ADR 已决定第一阶段使用进程内 PyO3。 | 异步规模、隔离或扩缩容需求证明后 |

Phase 1 可以使用 Python 标准库 SQLite 和本地 artifact store 验证 walking skeleton，但它们不自动成为最终生产选型。

## 4. 执行顺序

### 4.1 冻结旧实现参考输入

移动目录前记录：

```text
git revision
host/platform
Python version
可恢复的依赖清单（如存在）
fixture/golden 生成命令
关键 benchmark 命令和结果
已知无法运行项
```

没有兼容和迁移要求不等于可以丢失业务 oracle。应先把仍需保留的行为转换为 fixture、golden contract 或明确业务规则；之后旧环境可以停止维护。

### 4.2 移动旧目录并建立最小新目录

在独立结构性提交中执行：

```bash
mkdir -p legacy vnext
git mv backend_vnext legacy/backend_vnext
mkdir -p vnext/backend vnext/rust vnext/repository_service vnext/deploy/env
```

同一提交还应完成：

- 新增 `legacy/README.md`，声明只读/oracle 规则。
- 更新只因物理路径变化而失效的旧运行命令。
- 保留旧 package 名称；需要运行时显式设置 `PYTHONPATH=$PWD/legacy` 或使用其冻结环境。
- 增加架构测试，禁止 `vnext/` import `legacy` 或旧 `backend_vnext`。
- 更新根 `.gitignore`，排除 `.venv/`、`target/`、`.env`、runtime data、artifact、Dolt volume 和本地数据库。

验收：目录移动前后的选定 oracle fixture/digest 必须一致；如果旧环境本来不可恢复，应在台账中明确记录，而不是临时修改旧业务语义。

### 4.3 安装并固定 uv 与 Python

安装官方固定版本 uv；如果机器已经安装，先验证版本：

```bash
uv --version
uv self update 0.11.28
uv python install 3.14.6
uv python find 3.14.6
```

如果 `uv self update` 不适用于当前安装方式，使用 uv 官方安装器或系统包管理方式安装 `0.11.28`，不要在同一次执行中无版本约束地安装。

初始化新后端：

```bash
uv init --package --name gateway-backend --python 3.14.6 --vcs none vnext/backend
cd vnext/backend
uv python pin 3.14.6
uv add fastapi==0.139.0 pydantic==2.13.4 pydantic-settings==2.14.2 uvicorn==0.51.0 pyarrow==25.0.0
uv add --dev httpx==0.28.1 pytest==9.1.1 pytest-asyncio==1.4.0 hypothesis==6.156.6 pytest-cov==7.1.0 ruff==0.15.21 mypy==2.3.0 maturin==1.14.1
uv lock
uv sync --frozen
```

`polars` 和 `python-multipart` 在 walking skeleton 或 upload slice 出现真实调用方时分别执行：

```bash
uv add polars==1.42.1
uv add python-multipart==0.0.32
```

初始化 Repository Service 的独立 Python project：

```bash
uv init --package --name gateway-repository-service --python 3.14.6 --vcs none vnext/repository_service
cd vnext/repository_service
uv python pin 3.14.6
uv add pydantic==2.13.4 pydantic-settings==2.14.2
uv add --dev pytest==9.1.1 pytest-asyncio==1.4.0 hypothesis==6.156.6 pytest-cov==7.1.0 ruff==0.15.21 mypy==2.3.0
uv lock
uv sync --frozen
```

Repository transport 收口后再增加 FastAPI/HTTPX 或 gRPC/Flight 相关依赖。不得为了提前填满环境而同时安装所有候选 transport。

注意：`uv add package==version` 用于明确本次候选解析输入，真正的完整传递依赖版本由提交的 `uv.lock` 固定。CI 和镜像只运行 `uv sync --frozen`，不得运行 `uv lock --upgrade`。

### 4.4 安装并固定 Rust

通过 rustup 安装固定 toolchain：

```bash
rustup toolchain install 1.97.0 --profile minimal --component rustfmt,clippy
rustc +1.97.0 --version
cargo +1.97.0 --version
```

创建 `vnext/rust/rust-toolchain.toml`：

```toml
[toolchain]
channel = "1.97.0"
profile = "minimal"
components = ["rustfmt", "clippy"]
```

创建 Cargo workspace 时使用 edition 2024 和 workspace `resolver = "3"`。首批只创建：

```text
gateway-compute-core
gateway-compute-python
```

`gateway-compute-worker` 暂不创建。crate 依赖使用上表版本起步，并提交生成的 `Cargo.lock`。Library workspace 也提交 lock，因为本仓库交付的是应用和固定构建产物，不是面向 crates.io 的通用库集合。

### 4.5 建立 Python/Rust/Arrow walking skeleton

walking skeleton 必须是后续可复用代码，不是一次性 demo。最小链路：

```text
Python facade
  -> PyArrow RecordBatch/Array
  -> one PyO3 call
  -> Rust batch kernel
  -> Arrow result + compact diagnostics
  -> ArtifactRef + digest verification
```

构建验证：

```bash
cd vnext/rust
cargo fmt --all --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace --locked

cd ../backend
uv run maturin develop --release --manifest-path ../rust/gateway-compute-python/Cargo.toml
uv run python -c "import gateway_compute; print(gateway_compute.__version__)"
```

实际 module 名称由 bootstrap 确认后替换示例中的 `gateway_compute`。验收必须覆盖 GIL release、panic/error mapping、scalar/NULL/datetime、Arrow schema、digest、artifact round-trip 和 Python/Rust differential fixture。

### 4.6 固定 Dolt 与 Repository Service 运行边界

Repository Service 使用 Dolt `2.1.11`。开发镜像可以从官方 `dolthub/dolt-sql-server:2.1.11` 获取已发布 binary，或按官方 release artifact 安装；最终 Repository Service image 必须记录 Dolt 版本和镜像/binary digest。

截至记录日期，官方 `dolthub/dolt-sql-server:2.1.11` 的 Linux amd64 image digest 查询结果为：

```text
sha256:5776d9249ed37075bb587f74e4542d5dcb81d04d64506eb28667d3bd470b8cb7
```

配置时必须重新核验该 digest 与目标 manifest/platform，不能只依赖可变 tag。

运行约束：

- 业务后端镜像不安装 Dolt，不挂载 Repository volume。
- Repository Service image 拥有 Dolt lifecycle、registry、operation journal 和 repository volume。
- 每个 repository 同时只有一个 writer owner。
- 开发环境也使用 CAS/idempotency，不以“单机”理由绕过 contract。
- Dolt volume、registry 和 operation journal 使用独立命名 volume。
- Phase 2 前补齐 readiness、liveness、restart recovery、backup/restore smoke test。

### 4.7 建立容器化开发环境

Phase 1/2 推荐使用 Debian Bookworm 系列、Linux amd64 和多阶段构建：

```text
rust:1.97.0-bookworm builder
  + uv 0.11.28
  + uv-managed Python 3.14.6
  -> maturin release wheel

python:3.14.6-slim-bookworm runtime
  + uv 0.11.28
  + committed uv.lock
  + built native wheel
```

首次配置时记录所有 base image manifest digest。Dockerfile 和 Compose 不使用 `latest`、浮动 minor tag 或部署时在线解析依赖。

`vnext/deploy/compose.yaml` 的最小阶段性服务：

```text
backend                 Phase 1 HTTP/bootstrap
worker                  Phase 4 前可以与 backend 使用同一 image、不同 entrypoint
repository-service      Phase 2 启用
```

Database、对象存储等未决组件不提前加入 Compose。旧系统如果需要进行 oracle/shadow 验证，放入独立 Compose profile，并使用不同端口、数据库、artifact root 和 Dolt volume；新旧系统不得同时拥有写 authority。

## 5. 配置与安全规则

- 所有配置通过明确 settings model 注入，并在启动时完成类型和必要字段校验。
- `.env.example` 只列键名和非敏感示例；真实 `.env` 不提交。
- 生产 secret 不进入 image layer、Compose 文件、日志或 diagnostics。
- 路径配置只能指向本服务拥有的目录；业务后端不得接受或保存 Repository Service host path。
- 限制 upload/import 的文件大小、解压大小、CPU、内存、磁盘和 timeout。
- 日志至少关联 `request_id`、business `operation_id`、`repository_operation_id`、repository/ref/commit、artifact digest 和 provider/version。
- native extension 必须在 worker crash 后由 Operation Runtime 恢复；不能假设 Rust panic 只影响当前函数。

## 6. 环境验收门禁

### 6.1 版本与锁文件

```bash
uv --version
uv run python --version
rustc --version
cargo --version
dolt version
docker version
docker compose version
```

验收：输出与执行台账一致；两个 uv project 都存在已提交的 `uv.lock`；Rust workspace 存在已提交的 `Cargo.lock`；Dockerfile/Compose 无 `latest`。

### 6.2 Python smoke test

```bash
cd vnext/backend
uv sync --frozen
uv run python -c "import fastapi, pydantic, pyarrow, uvicorn; print(fastapi.__version__, pydantic.__version__, pyarrow.__version__, uvicorn.__version__)"
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest -q
```

如果已加入 Polars，再验证 `import polars` 及一条 Arrow/Polars 零拷贝或受控拷贝 round-trip。

### 6.3 Rust 和跨语言门禁

```bash
cd vnext/rust
cargo fmt --all --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace --locked
```

必须另外通过：

- Python/Rust scalar、ordering 和 digest golden tests。
- Arrow schema/C Data 或 stream round-trip。
- Property-based differential tests。
- Rust 计算释放 GIL 的并发测试。
- Panic 和受控错误映射测试。
- Release wheel 在干净 runtime image 中安装和 import。
- Linux x86_64 image build，不依赖开发机 `.venv` 或 `target/`。

### 6.4 Repository Service 门禁

- Repository Service image 内 `dolt version` 为 `2.1.11`。
- 业务 backend image 中不存在 `dolt` binary。
- 业务容器看不到 Repository volume 和服务端路径。
- Repository Service readiness/liveness 通过。
- 重启后 repository registry、operation journal 和已完成 commit 可恢复。
- 重复 import/CAS 使用相同 idempotency key 得到确定结果。
- 本地/远程 client contract fixture 等价。

### 6.5 可复现构建

在清理 `.venv`、Cargo `target` 和 Docker build cache 后重新构建，结果必须满足：

- `uv sync --frozen` 不修改 `uv.lock`。
- `cargo build --locked` 不修改 `Cargo.lock`。
- wheel 能在干净 runtime image import。
- fixture/digest 结果一致。
- image 构建不访问未声明的宿主机路径。

## 7. 后续升级策略

基线验收完成后：

- CI/CD 不自动升级 Python、uv、Python package、Rust、crate、Dolt 或 base image。
- 安全修复和版本升级由独立 PR/执行台账触发。
- Patch/minor 可以按固定周期审查；major 和 Python minor 需要单独升级窗口。
- 每次升级都更新 lock、镜像 digest、版本清单和变更说明。
- 至少运行 contract/golden、Python/Rust differential、API、image build 和相关 benchmark。
- 性能结果只有在 correctness validation passed 后才有效。
- 如果升级改变 scalar、Arrow schema、ordering、digest、Parquet 或 diagnostics，必须按 contract 变更流程处理，不能作为普通依赖更新合入。

部署阶段只允许：

```bash
uv sync --frozen
cargo build --locked
docker build with pinned base references
```

部署阶段禁止：

```text
uv lock --upgrade
uv add without an explicit reviewed change
rustup update
cargo update
floating Docker tags
installing latest Dolt at container startup
```

## 8. 下一次环境配置对话的完成标准

下一次对话应基于本文件执行，并在结束前交付：

1. 完成旧目录移动，且没有覆盖当前未提交的用户改动。
2. 创建最小 `vnext/backend`、`vnext/rust`、`vnext/repository_service` 和 `vnext/deploy` 骨架。
3. 生成并提交候选 `pyproject.toml`、`.python-version`、`uv.lock`、`rust-toolchain.toml`、Cargo workspace 和 `Cargo.lock`。
4. 完成 Python/Rust/Arrow walking skeleton 的 release wheel 构建与 smoke test。
5. 完成最小 backend/repository-service Dockerfile 和 Compose 配置；未决基础设施保持未选型。
6. 输出实际版本、命令、测试结果、镜像 digest、已知差异和下一门禁。
7. 如果任一候选最新版不兼容，选择最新可验证组合，并记录降级证据；不得静默改用较旧版本。

## 9. 官方版本来源

查询日期均为 2026-07-15：

- Python releases：<https://www.python.org/downloads/>
- uv releases：<https://github.com/astral-sh/uv/releases>
- PyPI package metadata：<https://pypi.org/>
- Rust stable manifest：<https://static.rust-lang.org/dist/channel-rust-stable.toml>
- crates.io：<https://crates.io/>
- maturin releases：<https://github.com/PyO3/maturin/releases>
- Dolt releases：<https://github.com/dolthub/dolt/releases>
- Dolt image：<https://hub.docker.com/r/dolthub/dolt-sql-server>
- Docker Engine releases：<https://github.com/moby/moby/releases>
- Docker Compose releases：<https://github.com/docker/compose/releases>
- Official Python image metadata：<https://github.com/docker-library/official-images/blob/master/library/python>
- Official Rust image metadata：<https://github.com/docker-library/official-images/blob/master/library/rust>

本文中的版本不会自动更新。实际配置开始时先重新查询这些来源；只有发现候选版本已撤回、存在阻断安全问题或 incompatibility 时才调整，并在执行台账中记录理由。

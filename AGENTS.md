# AGENTS

本仓库的 agent 硬约束。完整背景见 [docs/backend-vnext/testing-conventions.md](docs/backend-vnext/testing-conventions.md)。

## 项目前提

这是全新项目：没有已部署的使用方、没有需要保留的历史数据，也没有兼容或迁移要求。

- 改 Contract、checkpoint 载荷、digest 或 HTTP DTO 时，直接改到目标形态，不建设兼容层、
  双读/双写、旧字段别名或数据回填；同步更新 golden 与测试。control DB schema 的演进方式以
  owning 设计为准（当前为 P5 收口设计 DC6 的前向 migration）。
- 删除被替代的实现，不保留“以防万一”的旧路径。
- `legacy/` 只作行为与数据格式的参考来源，不是兼容目标；vnext 与真实数据不一致时，以真实
  数据和 owning Contract 为准。
- 这不放宽阶段内的冻结约定：某阶段声明“不改行为”时，golden 与 digest 仍作为该阶段的回归
  基准。

## 跑测试

权威入口：

```bash
./vnext/scripts/run-tests.sh
```

权威入口的运行前提（不满足时结果不能作为门禁证据）：

- 在已提交的 clean worktree 上运行。`repository_service` 的 Compose 用例经
  `require_clean_worktree()` 计算 image identity，worktree 有未提交改动时这些用例必然失败。
- 运行期间不写 worktree、不提交、不重建或重新 tag 镜像。
- linked worktree（含审核用的 detached worktree）要先建本地参考目录的符号链接：`ln -s /home/dev/gateway-data-management-system/legacy <worktree>/legacy`
  （`legacy/` 不在任何提交里，由 `.git/info/exclude` 忽略）。缺它时 `test_table_rules_resolver.py` 的 58 个用例失败，权威 runner 随之失败。
- 同一主机上不并行运行其他 Dolt 进程或 Compose 栈：残留检查扫描整机 `/proc` 中的 dolt
  进程，backend Compose 旅程共享 host 端口 8000。
- 日志写到 worktree 外，并记录开始与结束时的 `git rev-parse HEAD` 和 runner 自身的 exit code
  （经 `tee` 时用 `set -o pipefail` 或 `${PIPESTATUS[0]}`）。

阶段性验证不要跑全量。按范围收敛：

```bash
cd vnext/repository_service
../scripts/uv-consume.sh -C . run pytest -m unit          # 约 1490 项，无外部依赖，约 12 秒
../scripts/uv-consume.sh -C . run pytest -m integration   # 需要真实 dolt
../scripts/uv-consume.sh -C . run pytest -m 'serial and not parallel_safe' -n 0   # 未确认可隔离的时序敏感组
```

`repository_service` 默认并行（`-n auto`）；其余包单进程，不要给它们加 xdist。
在 CPU 充足的正式开发环境中可显式调整非串行 worker 数量，例如
`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`；默认 `auto` 保留
pytest-xdist 的自适应行为。`parallel_safe` 是从 `serial` 中经过逐项审查、确认不依赖
时序、线程、进程、网络、Dolt 或共享持久化状态的例外；权威脚本会将它们加入并行批次。
其余 `serial` 组始终 `-n 0`，不按 CPU 数量盲目并行化。

开发机有临时 tmpfs 时，可将 pytest 临时工作区切换到指定的绝对路径，例如：
`GATEWAY_TEST_BASETEMP=/mnt/gateway-test-tmpfs/pytest GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`。
该变量只影响测试临时目录，不改变正式服务数据卷；涉及持久化、崩溃恢复和快照语义的正式验收
仍须使用真实文件系统。

Host 依赖准备权威入口：

```bash
./vnext/scripts/prepare-dev-dependencies.sh
```

`GATEWAY_DEV_DEPENDENCY_MODE=internal` 时须显式提供 `UV_INDEX_URL` 或 `UV_DEFAULT_INDEX`；
默认 `pypi` 模式在同步时会剥离机器级 index，保持 lock 的 canonical PyPI identity。
可选 `GATEWAY_DEV_OFFLINE=1` 使用 `uv sync --locked --offline`。该脚本不跑测试。

受控 uv 消费入口：

```bash
./vnext/scripts/uv-consume.sh -C vnext/<package> <sync|run|lock-check|pip-install> ...
```

`run-tests.sh`、`prepare-dev-dependencies.sh`、`native_kernel_component.sh` 与
`build-repository-service-image.sh` 已接入该 wrapper。普通 `run`/`sync` 默认 `--locked` 并隔离
ambient index/config；`--no-sync` 路径先执行只读 `uv lock --check --offline`，再
`uv run --locked --no-sync`。消费入口在执行前后比较五锁 SHA，漂移即非零退出且不自动 restore。

权威测试入口通过 `uv-consume.sh` 消费依赖，测试过程不得根据开发机的包镜像配置隐式改写
`uv.lock`；依赖变更必须经显式授权步骤更新锁文件并重新同步环境。提交前静态检查示例：

```bash
cd vnext/<package> && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy
```

Docker 镜像构建可通过 `GATEWAY_DOCKER_BUILD_NETWORK` 控制 build 网络（`deploy/compose.yaml`
与 `build-repository-service-image.sh` 均读取；默认分别为 bridge 与 `host`）。
`GATEWAY_BACKEND_UV_BOOTSTRAP_*` / `GATEWAY_REPOSITORY_UV_BOOTSTRAP_*` 仅作为 build-time
参数，不进入 production runtime ENV。Compose 测试客户端镜像在 Linux nested LXC 中默认使用
Docker `host` 网络；可通过 `GATEWAY_DOCKER_BUILD_NETWORK=default` 覆盖。该设置只影响镜像
构建，不改变 production Compose 服务网络边界。

## 写测试

`repository_service` 的四个 marker 已声明，`--strict-markers` 生效，拼错会导致收集失败。

- **不要**手写 `@pytest.mark.skipif(not dolt_available(), ...)`。dolt 门禁只有一处，
  在 `vnext/repository_service/tests/conftest.py`。
- 通过 `lifecycle_settings()`、`ServiceRuntime.start()`、`DoltRunner()` 等方式依赖
  真实 dolt 的测试，**必须**加 `@pytest.mark.integration`。请求 `import_layout` /
  `import_provider` fixture 的会被 conftest 自动判定，无需重复标注。
- 依赖固定时间预算（`Event.wait(timeout=...)`、`thread.join(timeout=...)`、子进程
  sleep 与 stream timeout 的相对关系）的测试，**必须**加 `@pytest.mark.serial`。
- 改动测试分类后，用「移开 dolt 再跑 `-m unit`」验证，静态扫描不可靠：

```bash
mv /usr/local/bin/dolt /usr/local/bin/dolt.parked
uv run pytest -m unit; mv /usr/local/bin/dolt.parked /usr/local/bin/dolt
```

## 测试性能红线

- **禁止**为纯解析、纯校验、纯类型映射的逻辑引入会执行 `dolt init` 的 fixture。
  「建真实仓库再把 `run_cli` 整个 mock 掉」是明确的反模式。
- 仅 payload 与期望错误消息不同的同构用例，**必须**收敛为模块级共享参数表
  （范例：`MALFORMED_JSON_SHAPES`、`CATALOG_ROW_SHAPE_FAULTS`），不得复制粘贴成多个
  测试函数。
- 构造测试前置状态时，不要在循环里反复 spawn 外部进程，按批构造。
- 任何创建全新 dolt HOME 的代码路径，必须预置 `.dolt/config_global.json` 关闭
  versioncheck（见 `DoltRunner._seed_private_dolt_config`）。否则每次都会联网查版本，
  单次 3~5 秒，且违反 offline provider 边界。

## 改依赖

各包依赖一律精确钉版本（`==`），用 `uv add --dev` 添加。

改动 `vnext/repository_service/uv.lock` 后，**必须**同步更新
`vnext/repository_service/Dockerfile` 里的 `ARG UV_LOCK_SHA256`，否则
`test_dockerfile_uv_lock_sha256_matches_lockfile` 会失败：

```bash
sha256sum vnext/repository_service/uv.lock
```

## 主线开发与阶段边界

- 直接在 `main` 上提交，不为每个阶段开分支；只有确需并行的工作才开短期分支，并尽快合回。
- 阶段边界用附注 tag（例如 `p5-s1-exit`）标记；审核对象是 `<上一阶段 tag>..<候选提交>` 的提交区间。
- 审核与复审在只读 detached worktree 中进行（`git worktree add --detach`），不在主工作区运行测试；
  测试运行期间任何人都不得在被测 worktree 中写入。
- 未经 owner 授权不推送，不改写已被审核引用的提交。流程细节见
  [P5 收口执行计划 §8](docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-execution-plan.md)。

## Docker / Compose 验证

阶段性修改不要求每轮、每个提交都重建镜像。是否重建按改动是否触碰 image、deployment
或 container-only runtime boundary 判定；同一轮内可先完成相关修改，再对该轮最终 HEAD
构建一次。

以下改动必须重建当前 HEAD 并运行相应容器门禁：

- Dockerfile、依赖锁/production 依赖闭包、基础镜像、镜像构建或传输脚本；
- entrypoint、Compose、环境变量接线、healthcheck/readiness 接线；
- UID/GID、目录权限、volume/mount、socket、pidfile、broker/helper；
- 依赖容器用户、PID、signal、mount 或 filesystem 隔离才能证明的 startup/shutdown 行为；
- 修改实际 Docker/Compose e2e 或 container harness，或本轮要宣称当前 HEAD 已通过容器门禁；
- 阶段退出、S3 ready、发布或最终 production gate。最终候选 HEAD 必须有绑定到它的容器
  门禁结果：发布与最终 production gate 必须在最终 HEAD 重建并完整运行；阶段退出与 S3 ready
  可按下文“镜像身份等价”沿用已验证提交的结果。

纯 Python 内部逻辑、SQL/状态机、测试或普通文档改动，在 focused/unit/integration 已覆盖
且未触碰上述边界时，可以把镜像构建延期到必要节点。旧镜像结果只能作为回归证据，不得
表述为当前 HEAD 已验证；唯一例外是满足下面的镜像身份等价。

镜像身份等价（仅阶段退出、S3 ready）：已验证提交 `V` 与最终 HEAD 同时满足以下条件时，`V`
的容器门禁结果视为最终 HEAD 的结果，记为 `carried`，不重跑 Compose：

1. `V` 的门禁在已提交的 clean worktree 上由权威入口执行，日志记录 HEAD 与 exit code，运行期间
   未写 worktree；
2. `V..HEAD` 未改动上面前五项列出的任何内容，也未改动 Docker/Compose e2e 测试或 harness；
3. 每个门禁镜像身份相等：带 build-input/source-tree label 的镜像（repository-service）在最终
   HEAD 重算的身份与 label 一致；没有此类 label 的镜像（backend/worker）在 `V` 的同一 worktree
   中、两次构建之间不运行任何测试，用与 `V` 相同的构建命令（含 provenance 中的 project 名）
   重建，image ID 必须与 `V` 的 provenance 中实际运行的 ID 相同。构建上下文带入 worktree 的
   本地状态（文件权限位由创建文件的 umask 决定、git 不记录；被忽略的残留目录），换 worktree
   重建通常得到不同的 ID，不得用另一个 worktree 的结果判定“等价”或“不等价”（治理修订计划 G6b）。

任一条件不满足，就在最终 HEAD 重建并重跑。同一提交上权威 runner 已运行过的 Compose 旅程
（含 backend 批次中的 Compose 测试）不再单独重跑，provenance 取自该次运行。

每轮评审必须记录当前 HEAD、是否触发重建及理由、最后验证的 image revision/source-tree，
以及延期到哪个节点或从哪个提交沿用。完整规则与记录模板见
[docs/backend-vnext/testing-conventions.md](docs/backend-vnext/testing-conventions.md)。

## 全局比例化保障

Phase 0–9及后续维护统一遵守
[Proportional Assurance and Risk-Based Verification Policy](docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md)。

- 新安全、恢复、一致性、evidence或治理机制必须对应当前威胁、明确业务损失、已确认consumer
  或已发生的可复现故障；否则使用标准平台能力和最小机制。
- 先区分权威/不可逆事实、可恢复durable状态、derived/temporary状态和内部实现细节。
  前两类保持强Contract、事务/CAS/幂等及关键crash验证；后两类优先bounded处理、重试、诊断
  和人工处置，不自动建立同等证明。
- 同机受控模块、worker和同一Service euid默认属于单一信任域。新增独立UID/helper/service、
  自定义IPC/capability、持久evidence状态机、sidecar/quarantine/tombstone或syscall-window
  安全证明前，必须先修订owning Contract/ADR，不能由普通审核Finding直接扩大威胁模型。
- 测试证明Contract语义屏障，不穷举内部步骤。每个不变量只有一个权威测试owner；测试按业务
  行为命名，不按round/finding编号命名；删除production机制时同步删除其mock和证明探针。
- API认证授权、secret、caller输入、path/archive/symlink/root逃逸、非shell执行、资源上限、
  transaction/CAS和跨scope误写等基础边界不能用“比例化”跳过。

## Artifact cleanup 保障边界

权威决策是
[ADR 0012](docs/backend-vnext/refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)：
V1同机Service进程属于单一信任域。实现和评审聚焦协作并发、崩溃、I/O错误、protected
artifact、server-owned path与root/symlink边界；不要为同euid恶意pathname换名新增broker、
sidecar状态机或安全探针，除非先按reopen conditions修订ADR。

cleanup测试按Contract行为命名，不按`r8_*`、`r19_*`等修复轮次命名；不可逆的Dolt commit/
main CAS、control DB事务和跨root误操作仍保持强验证。完整测试取舍见
[docs/backend-vnext/testing-conventions.md](docs/backend-vnext/testing-conventions.md)。

## 提交前

五个 Python 包都要过 ruff 与 mypy（`repository_service` 为 `strict = true` 且覆盖
`tests`）。mypy 增量缓存命中时五个包合计约 1.5 秒，不是耗时项，不要为了省时间跳过：

```bash
cd vnext/<package> && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy
```

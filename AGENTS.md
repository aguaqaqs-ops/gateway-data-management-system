# AGENTS

本仓库的 agent 硬约束。完整背景见 [docs/backend-vnext/testing-conventions.md](docs/backend-vnext/testing-conventions.md)。

## 项目前提

这是全新项目：没有已部署的使用方、没有需要保留的历史数据，也没有兼容或迁移要求。

- 改 Contract、checkpoint 载荷、digest 或 HTTP DTO 时，直接改到目标形态，不建设兼容层、
  双读/双写、旧字段别名或数据回填；同步更新 golden 与测试。control DB 以单一基线 schema
  创建（P5 收口设计 DC6）：改 schema 时直接修改基线，schema 与代码不符即拒绝启动，开发者删除本地
  control DB（含 `-wal`、`-shm`）后重建；首次出现需要保留数据的部署时，再引入前向 migration。
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

### 专用测试节点

所有测试、容器门禁和测试取证都在专用测试节点上执行，不在开发主机上运行（owner 决议 DC34、DC36）。
Owner 于 2026-11-08 将五节点统一为 **32 vCPU / 64 GiB**，取消前后端、门禁、真实数据和性能的固定节点用途（DC91）。以下任一空闲且本次工具链、缓存、输入满足前提的节点均可使用，不再为池内换节点另申请用途例外：

| 节点（SSH 别名） | 当前配置 |
| --- | --- |
| `ct108-gw-dms-04` | 32 vCPU / 64 GiB |
| `ct108-gw-dms-05` | 32 vCPU / 64 GiB |
| `ct108-gw-dms` | 32 vCPU / 64 GiB |
| `ct107-gw-dms-06` | 32 vCPU / 64 GiB |
| `ct109-gw-dms-07` | 32 vCPU / 64 GiB |

- 开始前核现场空闲、服务/端口和有效标记；所有测试、编译、lint、构建、mock/真实 e2e、取证及有写入的清理，均以 `mkdir /home/dev/gdds-node-busy.d` 原子取得本节点占用，写会话、用途与开始 UTC，收尾后只释放本人标记。已有自行管理标记的入口（前端真实 backend e2e）由入口获取，外层不要重复获取。只读现场核对无需占用；不抢占、不删除他人标记，不以旧空闲快照代替执行时检查。
- 同节点整机单飞；计时测量期间该节点不运行其他任务。已知物理拓扑仍是 04/06/07 同宿主、原 04/05/CT108 分属不同宿主，不能因配置一致就视为五套独立硬件。跨节点不自动互斥，实际干扰时针对性协调。
- 已授权测试不需逐次与并行S4或其他会话沟通、预约或通报；核实时空闲并原子取标记即可。只有实际占用／资源干扰、共享文件写入或涉及他人资源时才协调（Owner 2026-11-08补充，DC97）。
- 正式测量可选池内合格节点；同一统计组的预热和测量留在同一节点与配置，记录冷暖、CPU/内存及存储条件。换节点或硬件配置后的样本分组报告，不能混入旧组或直接宣称同条件提速。
- pytest workers/Cargo jobs 初始建议各 4；前端设置 `GATEWAY_FE_TEST_WORKERS=2`。测试并发与产品 N/M 分开。64 GiB guest 不改变已冻结的 N1、32 GiB worker envelope、8 GiB reserve、显式 M24 GiB；临时增预算诊断须另外固定参数与证据，不能照搬旧 64 GiB worker 配置。 Owner 随后按 DC95 明确授权本轮 S3 worker 在现有资源内上调、最大 32C/64G；实际资源档须留系统/其他服务余量并固定独审，新档结果与原 M24 失败分列，生产默认不因授权本身自动变更。
- 缓存不跨节点共享。按包 carried 和镜像等价仍须在来源 V 的同一节点、同一 worktree 判定，不能随调度搬迁证据。旧记录中的实际节点和阶段专项授权保留历史含义，未来调度以本规则为准。
- Owner 同时授权一轮历史测试文件清理：仅删除已确认无运行者、无待用消费者、无需保留的本任务/明确废弃派生文件，逐项留路径、理由及前后空间记录。保留已引用成功/失败原始证据、当前 carried worktree/环境/镜像、真实输入、冻结基准资源及未决故障状态；不按年龄批删，不执行全局 Docker prune，不清他人有效资源。具体白名单及执行记录见 [并行推进计划](docs/backend-vnext/refactoring/formal/plans/p6-s3-s4-parallel-plan.md)。

网络与缓存遵守 [测试节点网络与缓存](docs/backend-vnext/testing-conventions.md#测试节点网络与缓存owner-2026-10-28)：

- CT201 只作联网开发与获准缓存来源；测试 CT 禁止直连公网，只经获准 LAN 获取源码、依赖、镜像与制品。各节点分别预填充并确认本次缓存端点可达，不能假设缓存跨节点共享。
- Python runner/同步设置 `UV_OFFLINE=1`；Rust runner 设置 `CARGO_NET_OFFLINE=true`。root SSH 的 `PATH` 以 `/home/dev/.cargo/bin` 开头，不设 `RUSTUP_TOOLCHAIN`、`RUSTUP_HOME`、`CARGO_HOME`，按仓库 selector 核对四个 Rust 工具为同一工具链。
- **DC67 缓存与代理：**依赖、锁或基础镜像变化先在 CT201 获取并向实际节点预填充；缓存缺失或 LAN 不可达即停止，补齐后从头运行。任何池内节点的 runner/carried、正式测量及真实数据取证均不经转发代理；只有 05 调试构建可按链接中的受限代理例外执行，结果不作证据。离线隔离不关闭本机 Docker 网络、loopback、测试端口或获准 LAN。
- **backend/worker（自 `p6-backend-image-exit` 起）：**依赖输入变化时，按链接列明的输入与 `build-backend-dependency-base.sh --save` 流程在 CT201 clean worktree 构建、传输并记录完整身份；节点使用预置 dependency-base、`GATEWAY_DOCKER_BUILD_NETWORK=none`，保留 Compose 本机 build，不设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。旧产品流程见链接中的历史版本说明。
- **镜像身份：**跨节点比较 config digest 与全部 RootFS DiffID，不比较 `docker inspect` ID；同节点闭包/按包 carried 使用本机 image ID，容器门禁等价另按下节判定。RS/client e2e 保留各自预置依赖模式；client e2e revision 不符由门禁本机重建，不手工 `docker rmi`。
- handoff 记录缓存来源类别/端点标识、来源节点/提交、制品摘要、预填充时间与使用方式；镜像另按链接记录完整身份。不得记录凭据，manifest 中 proxy/cache 值只存摘要。
- **DC68 工具/取证错误（Owner 2026-11-08 修订）：**首次失败后，同一具体故障允许最多三轮自行修复、适用独审与受影响步骤复验；不因被测对象已经运行就立即交 owner。每轮先停止该次执行、保留原始失败及日志/SHA、确认收尾，再固定修订稿复验；三轮仍未解决、原因/副作用不明或超出既有授权时交 owner。不得无修改自动重试、改预期掩盖结果或跳过身份/缓存前提；产品 finding 按阶段已有修复与停止规则办理。只读后处理/预检、代码传输准备的不计次数澄清继续适用。细则见 [testing-conventions](docs/backend-vnext/testing-conventions.md) 的 DC68 现行规则与 [Owner 决议](docs/backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md)。

权威入口的运行前提（不满足时结果不能作为门禁证据）：

- 开始前用 `ssh -o BatchMode=yes <别名> 'echo OK'` 确认连接；在指定节点 clean、已提交 worktree 运行。节点不可用或前提不满足可改选池内合格空闲节点，不回退开发主机；carried 的来源节点/worktree 不能更换。
- 运行期间不写 worktree、不提交、不重建或重新 tag 镜像；client e2e 由门禁正常重建的例外如上。
- linked worktree（含 detached 审核 worktree）先建 `ln -s /home/dev/gateway-data-management-system/legacy <worktree>/legacy`；`legacy/` 不入 Git，由 `.git/info/exclude` 忽略。
- 各节点分别满足整机单飞；不并行其他 Dolt 进程或 Compose 栈，残留扫描整机 `/proc`，backend 共用 host 8000。不同节点按占用/宿主边界并行；真实数据与门禁可在不同节点测同一 V，同档完整旅程留在同一节点。
- root SSH 使用磁盘目录 `TMPDIR=/home/dev/gdds-test-tmp`，不改 `/tmp/pytest-of-root` 属主。默认不设 `GATEWAY_TEST_BASETEMP`，显式验证该选项时除外。
- runner、carried 与真实数据日志放 worktree 外，记录 hostname、起止时间、起止 HEAD、入口自身 exit code（经 `tee` 用 `pipefail` 或 `${PIPESTATUS[0]}`）；handoff 写明节点。
- runner exit 非 0 时先停止处理失败，不继续 carried 或后续验收；Hypothesis 失败依据输出反例分析，不依赖跨运行缓存。

阶段性验证只跑所需 focused/marker 范围，不跑全量。权威入口可用 `GATEWAY_TEST_PACKAGES` 选包；固定顺序为 `rust`、`shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service`，未知或重复名称 exit 2，未设置则全六包。**项目最终门禁与发布门禁必须运行全部六包**；其他阶段按范围与闭包规则选择。

Rust 包依次执行全 workspace 的 fmt、clippy（`-D warnings`）、test（locked/offline），三步都执行、任一失败则包失败，不排除 crate；扩展 Python/Arrow 行为由 backend pytest 覆盖。Rust 改动后跑 backend focused 前须强制重装扩展，不能使用旧 `.so`；构建输入检查、额外参数仅传 pytest 及 worktree 外 Cargo 缓存处理见 [Rust 扩展规则](docs/backend-vnext/testing-conventions.md#rust-包与-backend-的-rust-扩展dc48)。

runner 管理 Python 包专属 Hypothesis 目录及其清理，worktree 内 `.hypothesis` 仅供 focused 使用；carried 须使用来源 V 的同一节点、同一 worktree、同一包专属路径且目录不存在。闭包无节点身份，禁止跨节点判定；[Hypothesis 与闭包细节](docs/backend-vnext/testing-conventions.md#hypothesis-隔离与按包闭包沿用)规定全部输入、清理时机和比较方法。
来源 V 须为该包实际通过、整次 exit 0、clean 且有起止 HEAD 日志的权威 runner（可只选部分包）；闭包变化的包必须重跑通过。handoff 逐包记录摘要、运行/沿用、来源 V 和日志，沿用链直接指最初实跑 V。

backend/RS 主体并行，`serial and not parallel_safe` 始终 `-n 0`，其余三个 Python 包单进程；`parallel_safe` 须逐项审查不依赖时序、线程/进程、网络、Dolt 或共享持久状态，backend 当前无此例外。worker 默认 `auto`，按节点资源设置，不盲目并行 serial；[执行入口](docs/backend-vnext/testing-conventions.md#执行入口)列明 marker 命令、两遍拆分与参数。
专用测试节点可显式以绝对路径 `GATEWAY_TEST_BASETEMP` 使用 tmpfs，仅影响 pytest 临时目录，不改变服务卷；持久化、崩溃恢复和快照验收必须用真实文件系统，详见同节。

Host 依赖准备使用 `./vnext/scripts/prepare-dev-dependencies.sh`（不跑测试）；所有 uv 消费使用 `./vnext/scripts/uv-consume.sh -C vnext/<package> <sync|run|lock-check|pip-install> ...`。保持 canonical registry identity，禁止隐式改锁；依赖变更须显式授权并重新同步。internal 模式须给 index、pypi 默认剥离机器 index，`GATEWAY_DEV_OFFLINE=1` 只约束准备步骤；locked/无同步检查与五锁漂移拒绝规则见 [内网构建环境变量](docs/backend-vnext/testing-conventions.md#内网构建环境变量仅记录名与语义不得写入-lockfile-或-production-runtime)。
Docker build 网络与 uv bootstrap 参数只影响构建，不进入 production runtime、不改变 Compose 服务网络；默认值、覆盖方式与接入脚本见同节。

## 前端测试（FD7）

依据 [前端 kickoff §6](docs/frontend-vnext/frontend-kickoff.md#6-测试与证据fd7)（owner 2026-11-02 确认）；
细节见 [testing-conventions.md](docs/backend-vnext/testing-conventions.md#前端测试fd7) “前端测试”一节。
真实 backend e2e 的独立入口为 `frontend/scripts/run-real-backend-e2e.sh`，不并入 `run-tests.sh`；`--session` 必填；脚本自行获取与释放 DC70 占用，调用前不要手工获取，否则脚本以 exit 3 退出。

- **位置与入口：**前端工程位于仓库根目录 `frontend/`，不在 `vnext/` 下，不进入后端测试闭包与 Docker context。
  权威入口为 `frontend/scripts/run-tests.sh`，与 `vnext/scripts/run-tests.sh` 相互独立。
- **节点：**与后端共用上述五节点池；静态检查、mock/真实 backend e2e 和阶段证据均可在合格空闲节点运行，不在开发主机运行。阶段证据仍使用 clean、已提交 worktree 与权威入口，记录实际节点。
- **工具链镜像：**测试节点宿主机不安装 Node.js。前端测试在固定版本的工具链镜像中运行（含 Node.js、浏览器与
  系统库）：在 CT201 取得，经 `docker save`/`docker load` 传到节点；跨节点身份比较 config digest 与全部
  RootFS DiffID，不比较 `docker inspect` ID。镜像版本变化时按同一流程重新取得与传输。
- **npm 缓存：**按 DC67 在 CT201 依 `package-lock.json` 取得缓存，经获准的局域网预填充到实际使用的节点，挂载进
  工具链容器，在容器中 `npm ci --offline`。缓存缺失即停止，补齐后从头运行。
- **节点协调：**所有前端运行均遵守上述原子占用规则，取消轻量前端运行不取标记的旧例外。`run-real-backend-e2e.sh` 自行取得/释放标记；外层不得重复取得。核本机 Dolt/Compose、8000 端口及实际资源干扰，清理本人运行后释放。
- **日志：**与后端相同，写到 worktree 外，记录 `hostname`、起止时间、起止 HEAD、exit code 与日志 SHA256；
  handoff 另记工具链镜像 tag 与身份（config digest、全部 RootFS DiffID）、npm 缓存来源（来源提交、缓存摘要、
  预填充时间）与运行节点。
- **截图验收：**FE2 起在 1280 与 1920 两种宽度下截图，截图存于 worktree 外的证据目录并记录 SHA256。审核会话对照
  `docs/frontend-vnext/sketches` 核对布局、层级、语义色、按钮层级、禁用原因与焦点样式，不做像素级比对；不符处
  修正或作为偏差列入 handoff 交 owner 确认。

## 写测试

`repository_service` 的四个 marker 已声明，`--strict-markers` 生效，拼错会导致收集失败。

- **不要**手写 `@pytest.mark.skipif(not dolt_available(), ...)`。dolt 门禁只有一处，
  在 `vnext/repository_service/tests/conftest.py`。
- 通过 `lifecycle_settings()`、`ServiceRuntime.start()`、`DoltRunner()` 等方式依赖
  真实 dolt 的测试，**必须**加 `@pytest.mark.integration`。请求 `import_layout` /
  `import_provider` fixture 的会被 conftest 自动判定，无需重复标注。
- 依赖固定时间预算（`Event.wait(timeout=...)`、`thread.join(timeout=...)`、子进程
  sleep 与 stream timeout 的相对关系）的测试，**必须**加 `@pytest.mark.serial`。
- 改动测试分类后，仅在专用测试节点按占用规则用「移开 dolt 再跑 `-m unit`」验证，静态扫描不可靠：

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
- 调试与取证分开（P5 决议 DC30）：调试期间只跑 focused 测试与出问题的那一段真实数据，不跑完整 runner；收敛后在最终门禁提交上
  完整运行权威 runner 一次、运行真实数据一次作为证据。真实数据的范围由阶段改动面决定，在 kickoff 时写明、阶段退出前由 owner 确认（DC33）。细节见执行计划 §8.9。
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
3. 每个门禁镜像身份相等：RS 在最终 HEAD 重算 build-input/source-tree 与 label 对照；backend/worker 在来源 V 的同一节点、同一 worktree 检出最终 HEAD，以 backend 闭包 manifest 判定“可沿用”。具体身份、权限、缓存和 context 规则见 [镜像身份等价与结果沿用](docs/backend-vnext/testing-conventions.md#镜像身份等价与结果沿用)。阶段门禁 worktree 保留至 exit 合入后再清理。

任一条件不满足，就在最终 HEAD 重建并重跑；同提交已由权威 runner 通过的 Compose 旅程不单独重跑，provenance 取自该次运行。
按包沿用决定当前 V 运行哪些包，镜像身份等价决定 V..H 能否 carried，两者分别判定；backend 包合格沿用包含同次 Compose 旅程，阶段退出仍须独立满足镜像身份等价。完整闭包、同 worktree 比较与记录方法见上述链接。

每轮评审必须记录当前 HEAD、是否触发重建及理由、最后验证的 image revision/source-tree，
以及延期到哪个节点或从哪个提交沿用。完整规则与记录模板见
[docs/backend-vnext/testing-conventions.md](docs/backend-vnext/testing-conventions.md)。

## 全局比例化保障

Phase 6退出按[DC97](docs/backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc97-性能可靠测量与节点协调补充owner2026-11-08)：性能数值目标只报告，是否达标不作退出门槛；仍须完成已确认范围的可靠测量、真实统计、正确性／资源安全／来源与独审核收，失败和未知不得写为通过。可由Luna max只读监视并向协调者汇报；不额外启动测试或替代唯一执行者／独立审核。

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
`tests`），不要为了省时间跳过：

```bash
cd vnext/<package> && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy
```

改动 `vnext/rust` 时还要过 rustfmt 与 clippy。它们会编译 crate，在五节点池内合格空闲节点上按占用规则运行，
`CARGO_TARGET_DIR` 放在 worktree 外：

```bash
cd vnext/rust && cargo fmt --all --check \
  && CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/<任务>-cargo-target \
     cargo clippy --workspace --locked --offline --all-targets -- -D warnings
```

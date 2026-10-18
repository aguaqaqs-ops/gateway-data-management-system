# Testing Conventions

状态：2026-08-07 建立；2026-08-09 增补P2后半段container gate合并规则；
2026-08-13 冻结Docker/Compose触发式重建、评审记录、全局风险验证与artifact cleanup规则

本文规定 vNext Python 包的测试分层、执行入口与性能约束。Fixture 材料语义由
[Testing Fixtures](testing-fixtures.md) 拥有，本文不重复。

## 执行入口

Host 依赖准备与权威测试分为两阶段，不得混用机器级 index：

```bash
./vnext/scripts/prepare-dev-dependencies.sh
./vnext/scripts/run-tests.sh
```

权威 runner 将 backend 与 `repository_service` 分成并行主体和 serial 两遍：
`-m "(not serial) or parallel_safe" -n "$TEST_WORKERS"` 后接
`-m "serial and not parallel_safe" -n 0`。其余三个包单进程运行。G11 kickoff base
`676110a74b68` 的 backend 基线为 2,847 passed；marker 数为 `unit` 2,665、
`integration` 205、`serial` 56（marker 可重叠）。`--durations=0` 的可见阶段耗时为
Compose 1,575.36 秒、其他 serial 37.97 秒、其余用例 100.30 秒，基线墙钟 1,717.23 秒。
Compose 占 backend 基线约 91.7%；细节与日志见
[G11 handoff](refactoring/formal/plans/p5-arch-closure-g11-handoff.md)。

linked worktree 里先建 `legacy` 符号链接（`ln -s /home/dev/gateway-data-management-system/legacy <worktree>/legacy`；该目录不在提交里，缺它时 backend 的
`test_table_rules_resolver.py` 有 58 个用例失败），再执行上面的两步。

`prepare-dev-dependencies.sh` 只同步五包 venv，不跑 pytest。`run-tests.sh` 按正确顺序跑
完全部 Python 包：

```bash
./vnext/scripts/run-tests.sh
```

阶段允许通过 `GATEWAY_TEST_PACKAGES` 指定部分包，例如
`GATEWAY_TEST_PACKAGES=backend,repository_service ./vnext/scripts/run-tests.sh`。合法值是
`shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service`；
未知或重复名称以 exit 2 拒绝，实际执行顺序仍按权威 runner 固定顺序。未设置变量时运行全部包，
原有包顺序、backend 与 `repository_service` 的两遍拆分、`GATEWAY_TEST_BASETEMP` 下的 Compose 文件
处理和五锁检查不变。S5 最终门禁与发布门禁不允许缩小范围，必须运行全部包。

runner 开始时为每个待运行包写出一份 JSON 闭包 manifest，可单独运行
`python3 -I vnext/scripts/test_input_closure.py manifest --package <包名>` 查看；dirty worktree 会被拒绝。
Git 组成部分使用当前提交对应路径的 tree/blob object id，`legacy/` 使用排序后的相对路径与文件内容摘要，
环境部分记录每包 Python `-VV`、Dolt、uv、rustc 版本；backend 与 `repository_service` 还记录 Docker/
Compose 版本和 Docker base image ids。每包闭包包括自身与传递路径依赖、fixtures、全部五个 lockfile、
runner/wrapper 脚本、workspace 配置、deployment 输入和共享 rust-toolchain selector。backend 的 Rust
闭包包含 workspace crate、`Cargo.lock` 与 `rust-toolchain.toml`（生成的 `target/` 排除）；backend 和
`repository_service` 还包括 Compose 镜像使用的完整 `vnext/` build context、相关 Compose 与 Dockerfile。
repository_service 的 context 因而包含 `repository_client` 及 e2e/dependency-base Dockerfile。manifest 对
Docker 测试记录本机 base image id。`compare --source <来源-manifest.json> --current <当前-manifest.json>`
逐项比较并输出“运行”或“可沿用”及变化的组成部分。

来源 V 必须满足：该包在该次权威 runner 中实际运行并通过；worktree clean；日志记录起止 HEAD；整次
runner exit 0。只运行部分包的权威 runner 也可作为来源。当前 V 上闭包有变化的包都必须实际运行并通过。
handoff 逐包记录总摘要、运行或沿用、来源 V 与来源日志。链式沿用必须直接引用最初实际运行该包的 V，
不得把一次沿用结果当作新来源。manifest 比较只证明闭包相等；它不替代来源 runner 的 clean、包通过、
整体 exit 0 与 HEAD 日志要求。

按包沿用与镜像身份等价分别判定：包沿用决定当前 V 上哪些包需要运行，镜像身份等价决定 V..H 的容器结果能否
carried。backend manifest 覆盖其 Compose 旅程使用的所有镜像构建上下文、Dockerfile、Rust workspace 与
Docker base image id，因此 backend 沿用时，同一次权威 runner 的 backend Compose 旅程一并沿用；V..H
仍须独立满足下文的镜像身份等价。S5 最终门禁与发布门禁始终运行全部包。

### 内网构建环境变量（仅记录名与语义；不得写入 lockfile 或 production runtime）

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

权威 runner 与提交前静态检查须通过受控消费入口（`uv-consume.sh` 或 `run-tests.sh`），
隔离机器 index/config 并在退出时比较五锁 SHA：

```bash
./vnext/scripts/run-tests.sh
./vnext/scripts/uv-consume.sh -C vnext/<package> run pytest ...
./vnext/scripts/uv-consume.sh -C vnext/<package> run ruff check .
```

`--no-sync` 消费路径必须先执行只读 `uv lock --check --offline`；不得以自动 sync 替换待验证
wheel。五锁 canonical registry identity 的权威 owner 为
`backend/tests/test_canonical_lock_identity.py`。

`repository_service` 与 backend 分两遍执行：主体并行，未确认可隔离的 `serial` 组单独串行，避免
CPU 争用导致时序敏感测试 flaky。少量从 serial 来源逐项审查通过的 `parallel_safe` 测试
会加入主体并行批次。backend 当前没有 `parallel_safe` 例外；其余三个包体量小，
worker 启动开销会超过并行收益，因此单进程执行。

日常迭代用 marker 缩小范围：

```bash
cd vnext/repository_service
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

开发机可通过 `GATEWAY_TEST_BASETEMP=/mnt/gateway-test-tmpfs/pytest` 将 pytest 临时工作区
放入有容量上限的 tmpfs；这不会替换 Docker named volume，也不能替代真实文件系统上的
持久化、崩溃恢复、快照和容量语义验收。权威脚本在启用该变量时，会让三个实际 Compose
e2e 文件回到真实磁盘临时目录，以避开 unprivileged LXC 下 Docker secret bind mount 的
remount 限制；其余测试仍使用 tmpfs。

不带 marker 直接运行 pytest 会执行全部测试并自动并行；结果正确，但 `serial` 组会与其他
测试争用 CPU，判定 flaky 时以脚本为准。

权威脚本的运行前提（已提交的 clean worktree、运行期间不写 worktree、整机单飞、日志记录
HEAD 与 exit code）见 [AGENTS.md](../../AGENTS.md)“跑测试”一节；不满足时结果不能作为门禁
证据。

### P2后半段的功能门禁与最终container门禁

P2后半段的功能门禁与最终container门禁规则见本节与 [AGENTS.md](../../AGENTS.md)。
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

当前延期inventory为（P2-R6-S7 已在 candidate `5f474ce2` 上收集并通过；S10 仍须在最终
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
   重建镜像。在dirty worktree或临时index tree上的运行不能作为`V`。
2. **diff不触及容器边界**：`git diff --name-only V HEAD`中没有上文“必须重建”前五项所列的
   内容，也没有Docker/Compose e2e测试、container harness或其support模块。
3. **镜像身份相等**，逐个镜像核对：
   - 带`gateway.p2r1.build-input-revision`与`gateway.p2r1.source-tree-sha256` label的镜像
     （repository-service）：在最终HEAD用`build_context_digest.py identity`重算，两项都等于`V`
     门禁所用镜像的label。`org.opencontainers.image.revision`随提交变化，不参与比较。
   - 没有source identity label的镜像（backend、worker）：在运行`V`门禁的同一worktree中检出
     最终HEAD后，两次构建之间不运行任何测试，用与`V`相同的构建命令重建（project名取自
     provenance），image ID必须等于`V`的Compose provenance中实际运行容器的image ID。构建上下文带入worktree的本地状态：
     文件权限位由创建文件的umask决定、git不记录，并且影响COPY层的缓存键；被忽略的残留目录
     （例如只含`__pycache__`的旧包目录）会作为空目录进入镜像。换worktree重建通常得到不同ID
     （G2审核实测，治理修订计划G6b），不得用另一个worktree的结果判定“等价”或“不等价”。
     缓存层被清理导致ID变化时，按不等价处理并重跑。

任一条件不满足，就在最终HEAD重建镜像并重跑受影响的容器门禁。等价判定由实现方记录，独立
评审逐项复核；复核不通过时不得以`carried`关闭finding。

按包沿用与镜像身份等价分别判定：包沿用决定当前V要运行哪些包，镜像身份等价决定V..H能否
`carried`。包 manifest 还摘要该包实际使用的 uv 环境目录内容；由锁定源码与对应 Python
解释器派生的 `__pycache__`、`.pyc`、`.pyo` 不计入内容摘要。backend闭包包括Compose使用的完整`vnext/`
Docker build context、Compose与相关Dockerfile、Rust workspace，以及运行时本机Docker base image ids；因此backend包从合格来源V
沿用时，该次权威runner中的backend Compose旅程也一并沿用。V..H仍须单独满足镜像身份等价，阶段退出
才能把容器门禁绑定到最终HEAD。RS闭包同样包含其`vnext/`构建上下文、repository-service和
repository-client Dockerfile及Docker base image ids。

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

把 dolt 移开再跑 `-m unit`，任何错分类都会直接失败：

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

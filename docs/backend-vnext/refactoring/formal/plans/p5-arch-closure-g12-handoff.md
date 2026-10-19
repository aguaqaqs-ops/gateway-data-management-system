# P5 架构收口治理修订 G12 第 1 项 handoff

## 1. 授权、区间与结论

- 本项只实施 G12 第 1 项“按包沿用测试结果”（DC33 第一部分）。未开始 S4；真实数据范围为空，未运行真实数据。
- kickoff base：`46c5684c98`。审核区间起点：`p5-s3-exit`（`6b2b5fd0e1`）。分支：`p5-g12`；实施 worktree：`/home/dev/gdds-p5-g12`。
- 门禁提交 **V**：`62a4122f9ce97615113beae3bbbf6497b3ab2adf`。V 在 clean worktree 上由完整权威 runner 通过，起止 HEAD 相同、`clean_end=1`、runner exit 0。
- 最终 **H** 是本 handoff 证据补齐后的文档提交。V 后只改文档；package manifest 与 Docker build 输入保持不变。H1 `e9921cf32771943dd6a2622b07bf886025b07f3b` 上的 backend-only 权威 runner 已在运行 V 完整 runner 的同一专用 LXC worktree 通过。最终 H 已在同一 worktree 完成五包 manifest 比较和 carried 判定，并以逐包实际运行来源判定沿用。
- 独立审核通过前不进入 S4。没有合并或 rebase `main`，没有推送；审核通过后按授权标记 `p5-g12-exit`，作为 S4 的区间起点。
- 测试迁移到专用 LXC `ct108-gw-dms`（hostname `gw-dms-test`，root SSH）。`ssh -o BatchMode=yes ct108-gw-dms 'echo OK'` 已通过；该 LXC 有 128 CPU、96 GiB 内存。项目要求已补到 `AGENTS.md` 与 testing conventions：后续测试、容器门禁和取证均在此节点运行，不回退到开发主机。
- 停止条件均未触发：未发现闭包外仓库文件读取；无需改生产代码、Compose、Dockerfile、harness、依赖或锁文件；未缩小测试范围或削弱断言。最终 H 的五包 manifest 与镜像 carried 结果按 §6–§7 记录；独立审核前不开始 S4。

## 2. 实施内容与路径预算

- 新增 `vnext/scripts/test_input_closure.py`：只依赖 Python 标准库，以 `python3 -I` 生成逐包 JSON manifest。Git 组成部分用选定提交的 tree/blob object ID；非 Git 组成部分用内容摘要。dirty worktree 失败退出。`compare` 验证来源和当前 manifest 后逐项比较，输出“运行”或“可沿用”以及变化的组成部分。
- 修改 `vnext/scripts/run-tests.sh`：支持 `GATEWAY_TEST_PACKAGES` 逗号分隔选择；未知包、重复包、空值或空项 exit 2。未设置时五包全部执行。始终按既有顺序运行，backend 与 `repository_service` 仍分并行主体和 serial 两遍；`GATEWAY_TEST_BASETEMP` 下 Compose 文件处理与五锁检查保持不变。开始时逐包写 manifest，结束时逐包写状态。
- 新增 `vnext/repository_service/tests/test_test_input_closure.py`，并扩展现有 owner `test_run_tests_script.py`。同构场景收敛为参数表，覆盖闭包组成、Docker context 与 tracked mode、路径依赖传递、dirty worktree 拒绝、比较结果、包选择和默认 runner 行为。focused closure tests：24 passed，日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-focused-closure-v7b-62a4122f9c.log`。
- 文档更新限于本项授权范围：`AGENTS.md`、`docs/backend-vnext/testing-conventions.md`、执行计划 §8.9、治理修订计划 G12 状态与本 handoff。其余代码/文档路径未在 kickoff base 后改动。

G12 在 S3 baseline 上新增 31 个 `repository_service` 并行用例：闭包脚本 24 项（原 22 项加上 tracked Dockerfile 和目录权限模式的 2 个参数场景），runner 包选择与默认行为 7 项；均在 V 完整 runner 中执行。没有删测、跳过旧用例或减弱断言。

## 3. 闭包定义

manifest schema：`gateway.vnext.test-input-closure` v7。每个包的 JSON manifest 列出组件名、类型、路径、纳入理由、摘要及适用的环境值，再计算总摘要。V runner 起始 manifest 原样记录在：`/home/dev/gdds-p5-closure-s1-gate-logs/g12-V7-runner-62a4122f9c-20261019T173659Z.log`；拆分文件在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V7-manifests/runner-source/`。

### 所有包共有的组成部分

| 组成部分 | 闭包与纳入理由 |
| --- | --- |
| `package:<name>` | 对应 `vnext/<package>/` Git tree：源码、测试、`pyproject.toml`、`uv.lock`、Python 版本选择与包配置。 |
| `path-dependency:*` | 按 uv/Cargo 路径依赖传递展开并逐 crate 计入；避免直接依赖摘要漏掉传递依赖。具体包集合见下表。 |
| `shared:fixtures` | `vnext/fixtures/` Git tree：golden、schema、向量与共享 fixture。 |
| `shared:scripts` | `vnext/scripts/` Git tree：权威 runner、`uv-consume.sh` 和测试调用脚本。该目录属于五包闭包，因此 runner 与摘要脚本修改使五包相对 S3 来源都须重跑。 |
| `shared:workspace-definition`、`shared:deployment` | `vnext/repository-workspace.toml` 与 `vnext/deploy/` Git tree；uv/workspace 和 Compose/deployment 测试会读取。 |
| `shared:lock-snapshot:*` | 五个包的 `uv.lock` 分别纳入；`uv-consume.sh` 在每条命令前后检查五锁。 |
| `shared:rust-toolchain-selector` | `vnext/rust/rust-toolchain.toml`；rustup 读取并选择 Rust 工具链。 |
| `non-git:legacy-content` | `legacy/` 按排序后的相对路径、类型、权限和内容摘要；linked worktree 通过仓库外符号链接提供，resolver 测试读取它。 |
| `non-git:package-uv-environment` | 每包实际 `.venv` 内容与执行权限摘要，排除由锁定源码和记录的解释器派生的 `__pycache__`、`.pyc`、`.pyo`。 |
| `non-git:hypothesis-storage`、`non-git:pytest-cache` | 有效 Hypothesis storage 和包内 `.pytest_cache` 的内容及权限摘要；缺失目录也有明确摘要。Hypothesis Unicode JSON gzip 按解压 payload 摘要，忽略临时文件名带来的 gzip header 差异。 |
| `environment:runtime-and-docker-build` | 记录包 Python `-VV`、Unicode 数据版本、Dolt、uv、rustc、Docker/Compose 客户端与 daemon/context 身份。敏感或可能含凭据的环境设置只保存 SHA-256；Docker 包另记录有效构建设置、被选镜像 ID 和适用的镜像清单。 |
| `non-git:docker-context-tracked-modes:vnext`（有 Docker context 的包） | Git tree 不记录普通权限位。对 `vnext/` 内所有 tracked 路径、祖先目录和 context 根按本机 `0o7777` 模式摘要；保守包含 Docker ignore 排除项，确保 Docker 实际收到的权限模式变化也会改变闭包。 |

### 每包的路径依赖与容器输入

| 包 | 包级/传递依赖与额外输入 | Docker/Compose 输入 |
| --- | --- | --- |
| `shared_kernel` | 自身 package tree 与共有输入；无路径依赖。 | 无镜像构建。 |
| `repository_contracts` | 自身 package tree 与共有输入；无路径依赖。 | 无镜像构建。 |
| `repository_client` | 自身 package tree；传递依赖 `vnext/repository_contracts/`。 | 无本包测试构建；但它和其依赖的 Docker 输入会因 RS 的完整 `vnext/` context 归入 `repository_service` 闭包。 |
| `backend` | 自身 package tree；传递路径依赖 `vnext/shared_kernel/`、`vnext/repository_contracts/`、`vnext/repository_client/`、`vnext/rust/gateway-compute-python/`、`gateway-compute-python-impl/`、`gateway-compute-core/`、`gateway-shared-kernel/`。`rust:workspace` 覆盖 workspace 下全部 crate、`Cargo.lock`、`rust-toolchain.toml`；生成的 `target/` 不计入。 | Compose 文件 `vnext/deploy/compose.yaml`；完整 `vnext/` build context；`vnext/backend/Dockerfile`（backend、worker）与 `vnext/repository_service/Dockerfile`（同一 Compose 旅程的 repository-service）。同时摘要 Docker ignore 规则、Docker 未忽略的非 Git context 项、context tracked 路径权限、构建参数/设置和被选 base/service 镜像 ID。 |
| `repository_service` | 自身 package tree；路径依赖 `vnext/repository_contracts/`；额外纳入测试读取的 `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md`。 | Compose 文件与完整 `vnext/` build context；`vnext/repository_service/Dockerfile`、`vnext/repository_client/tests/Dockerfile`、`vnext/repository_client/tests/Dockerfile.dependency-base`。Compose lifecycle 测试用 `vnext/` context 构建 client e2e 与 dependency-base 镜像，所以 context 内的 `repository_client`、`repository_contracts` 及 Dockerfile 引用目录均由 context tree/content/mode 摘要覆盖。有效 build 设置、repository-service/client e2e/dependency-base 选择及对应本机 image ID 入环境组件。 |

Git tree 覆盖 tracked 内容；Docker context 组件另按 `.dockerignore` 规则枚举实际发送的 context，并哈希 Docker 包含的 Git ignored/其他非 Git 项；tracked 路径和祖先目录的本机权限模式由单独组件覆盖。Dockerfile 专属 ignore 规则及未建模的 ignore 语法 fail closed。backend 与 RS 的 Docker context 因而覆盖 tracked 内容、tracked 权限和 Docker 可能读取的非 Git 文件。

## 4. 读取方覆盖与闭包实测

每包完整测试使用 worktree 外的 `sitecustomize.py` audit hook 记录 Python `open` 事件中的仓库内路径，覆盖 xdist worker 和继承 `PYTHONPATH` 的 Python 子进程。权威 runner 以 `python3 -I` 启动 manifest CLI，隔离模式会忽略 `PYTHONPATH`；因此另用 worktree 外 `audit-isolated-manifest.sh` 启动同一个 `python3 -I ... manifest` 命令，并在 `-c` bootstrap 中先安装同一 hook。该补测覆盖隔离 CLI 对脚本、`.venv`、缓存等输入的读取。逐包运行完整测试，没有排除测试；backend 的 Compose journey 包括在内。

hook、快照、汇总、隔离 CLI bootstrap 和 package runner 脚本原样保存在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v7/`。该 audit hook 记录 Python `open` 事件和 `os.open` 的路径、模式及 flags，不跟踪 `read(2)`，所以下表的总数准确含义是“以 read/read-write 模式打开的唯一现存仓库内普通文件路径”，不能解释为实际读取了每个路径的内容。backend 的机械 summary 将唯一一个生成的 `.hypothesis/tmp/tmpg00z0dwa` 按其 `.hypothesis` 路径前缀算入覆盖；它由 Hypothesis `mkstemp` 以 O_RDWR 创建后立即关闭，再由 gzip 写入并改名。源码检查确认该临时路径没有内容读取，因此修正计数时将它从输入中剔除。五包实测中没有测试生成后再读的输入文件。bytecode 是明确排除于环境摘要、由已摘要 Python 源派生的文件。校正后的逐包账目保存在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v7/corrected-open-input-accounting.json`；该文件同时列出 raw event stream 和原 summary 的对应文件名。

| 包 | read/read-write 模式打开的唯一仓库内路径 | manifest 覆盖的输入路径 | 派生 bytecode | 生成后仅写的临时路径 | 闭包外输入路径 | 测试 runner 日志 / audit summary |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `shared_kernel` | 8,771 | 8,737 | 34 | 0 | 0 | `g12-audit-shared_kernel-v7-20261019T155410Z.log`；`g12-audit-v7/shared_kernel-20261019T155410Z-summary.json` |
| `repository_contracts` | 8,607 | 8,592 | 15 | 0 | 0 | `g12-audit-repository_contracts-v7-20261019T155416Z.log`；`g12-audit-v7/repository_contracts-20261019T155416Z-summary.json` |
| `repository_client` | 9,906 | 9,871 | 35 | 0 | 0 | `g12-audit-repository_client-v7-20261019T155422Z.log`；`g12-audit-v7/repository_client-20261019T155422Z-summary.json` |
| `backend` | 12,056 | 12,055 | 0 | 1 | 0 | `g12-audit-backend-v7-20261019T155435Z.log`；`g12-audit-v7/backend-20261019T155435Z-summary.json` |
| `repository_service` | 11,045 | 11,045 | 0 | 0 | 0 | `g12-audit-repository_service-v7-20261019T162240Z.log`；`g12-audit-v7/repository_service-20261019T162240Z-summary.json` |

每个 Python-open event stream 以 `g12-audit-<package>-v7-<timestamp>-python-opens.jsonl` 保存；审计 hook 为 `g12-audit-v7/hook/sitecustomize.py`，隔离补测脚本为 `g12-audit-v7/audit-isolated-manifest.sh`。表中输入路径总数可由“manifest 覆盖的输入路径 + 派生 bytecode + 生成后仅写临时路径”复核；五包闭包外输入路径均为 0。唯一生成临时路径的审计记录在 backend 的 raw stream 中，其他四包没有 `.hypothesis/tmp` 事件。

非 Python 读取方逐项覆盖如下：

- **Docker/Compose/buildkit**：枚举 backend、worker、repository-service、client e2e、dependency-base 的 Dockerfile、Compose 定义与完整 `vnext/` context；`.dockerignore` 和专用 ignore 规则决定内容项，tracked tree、context 内非 Git 内容、tracked 路径权限模式、Docker/Compose 工具和 daemon identity、有效 build 参数与选中 base/service 镜像 ID 一起覆盖 build 输入。权威 runner 重建 `gateway-repository-client-e2e:local` 与 `gateway-repository-client-e2e-base:local` 属预期行为；未手工对两标签执行 rmi、tag 或删除。
- **Dolt**：Dolt 版本进入环境组件；repository-service Dockerfile/build context、所选 dependency-base 镜像 ID 与 build 参数覆盖容器内安装/运行输入。测试数据库位于 pytest 临时目录，来源由测试代码、fixtures 和 `legacy/` 摘要覆盖。
- **Cargo/rustup/本地 Rust 扩展**：backend 闭包包含整个 Rust workspace、全部传递 crate、`Cargo.lock`、toolchain selector、rustc 版本和 backend `.venv` 内扩展；`target/` 是生成物，不作为提交输入。
- **shell/uv**：`vnext/scripts/`、包配置、workspace 定义、五个 lock snapshot、uv 版本、实际 `.venv` 内容和有效 index/config 设置摘要覆盖 runner、uv wrapper 与同步操作。

未使用 `strace`：Python 读取已由 audit hook 实测；Docker context/Compose/Dockerfile/build args、Cargo workspace/lock/toolchain、shell/uv 脚本及工具/镜像 identity 定义了非 Python 读取边界。审计没有发现闭包外仓库文件读取。

## 5. V 完整权威 runner 与计数

取证仅在 `ct108-gw-dms` 完成，使用磁盘 `TMPDIR=/home/dev/gdds-p5-closure-s1-gate-logs/g12-default-tmp`，未设置 `GATEWAY_TEST_BASETEMP`。V 前 preflight 日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-preflight-20261019T173700Z.log`：128 CPU、96 GiB；load average `0.05, 0.02, 0.00`；容器清单为空、Compose project 为 `[]`、无 Dolt 进程、8000 端口空闲。V 后 preflight `/home/dev/gdds-p5-closure-s1-gate-logs/g12-preflight-20261019T181440Z.log` 同样通过且无容器、Dolt 或 8000 listener。

命令：

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

runner 日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V7-runner-62a4122f9c-20261019T173659Z.log` 记录 `clean_start=1`、`GATEWAY_TEST_PACKAGES=unset`、起止 HEAD 均为 `62a4122f9ce97615113beae3bbbf6497b3ab2adf`、`clean_end=1`、runner exit 0；开始 `2026-10-19T17:37:00Z`，结束 `2026-10-19T18:14:27Z`。每包起始 manifest 均在该日志中。

| 包 | V manifest 总摘要 | G12 V 结果 | S3 V `dc9c08a410` 结果 | 变化 |
| --- | --- | --- | --- | --- |
| `shared_kernel` | `d7f8576efc5852ddb1286d7cdfc7556118b2a9a3c64d653f03fd44a457f856c8` | 242 passed | 242 passed | 无 |
| `repository_contracts` | `34824b4131307bfe178b6d0d870f7d1409b708d0e5dd491d00dbb8d0337db3ad` | 152 passed | 152 passed | 无 |
| `repository_client` | `8c719ccf5bc772287feca799876affd1db7e8ece071861971a53f4393f4401fb` | 154 passed | 154 passed | 无 |
| `backend` | `0b81d651a3a4a17ecefd0a3c0b6c64ddfb350430557770b74519ce523f643c2b` | 并行 2,839 passed；serial 36 passed | 并行 2,839；serial 36 | 无 |
| `repository_service` | `79bbb50c94012d71826d71bb3eff4083b016432ff3cc2c1b3ab8890c7df3b1f0` | 并行 1,715 passed、1 skipped；serial 205 passed | 并行 1,684 passed、1 skipped；serial 205 | 并行 +31 passed；serial/skipped 不变 |

RS 并行主体多出的 31 个用例全部来自 G12：closure tests 从 22 增至 24（新增 tracked 文件和目录权限场景），runner 包选择与默认行为 7 项；其余 S3 用例计数不变。

## 6. 沿用规则演示与 H 的包判定

沿用规则按 DC33 实现：来源 V 必须是该包实际运行并通过的权威 runner，clean worktree 上起止 HEAD 可核，整次 runner exit 0；部分包 runner 也可作来源，但链式沿用必须直接引用最初实际运行该包的来源。当前 manifest 与来源 manifest 逐项相等才可沿用；闭包有变化的包必须在当前 V 实际运行并通过。handoff 逐包记录总摘要、运行/沿用、来源 V 与来源日志。

V runner 原始 manifest、重算结果和比较 JSON 位于 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V7-manifests/`；演示汇总日志为 `g12-V7-manifest-demos-summary.log`。

1. **V 与自身比较**：五包均“可沿用”，变化组件均为空；current 与 runner-source 总摘要逐包一致。比较环境复现 runner 内部的 `GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`。在 `shared_kernel` 单包实跑后再次比较，该包仍“可沿用”、无变化组件。
2. **S3 V 到 G12 V**：五包均“运行”。`shared_kernel`、`repository_contracts`、`repository_client` 的变化组件为 `shared:scripts`；backend 为 `docker:context:vnext`、`shared:scripts`；`repository_service` 为 `docker:context:vnext`、`package:repository_service`、`shared:scripts`。这符合 runner/closure 脚本属于五包闭包的定义。
3. **指定包实跑**：preflight `/home/dev/gdds-p5-closure-s1-gate-logs/g12-preflight-20261019T181536Z.log` 通过后，运行 `GATEWAY_TEST_PACKAGES=shared_kernel GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`。日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-selective-shared-kernel-V7-20261019T181536Z.log` 记录只生成 `shared_kernel` manifest、只执行该包、242 passed、`shared_kernel status=passed`、runner exit 0，起止 HEAD 均为 V 且 clean。运行后 preflight `/home/dev/gdds-p5-closure-s1-gate-logs/g12-preflight-20261019T181547Z.log` 通过；该包 manifest 仍可沿用。

H1 backend-only runner 在 clean worktree、HEAD `e9921cf32771943dd6a2622b07bf886025b07f3b` 上由权威入口运行，开始 `2026-10-19T18:21:23Z`、结束 `2026-10-19T18:48:07Z`，起止 HEAD 相同、`clean_start=1`、`clean_end=1`、exit 0。命令为 `GATEWAY_TEST_PACKAGES=backend GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`；并行 2,839 passed，serial 36 passed。runner log 为 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H1-backend-runner-20261019T182123Z.log`，起始 backend manifest 总摘要 `0b81d651a3a4a17ecefd0a3c0b6c64ddfb350430557770b74519ce523f643c2b`，manifest 副本为 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H1-manifests/backend-runner-source/backend.json`。该部分 runner 自身 exit 0，故可作为 backend 包的直接实际运行来源。

H 最终 manifest 复核记录在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-final-manifests/`，比较汇总为该目录的 `summary.log`；backend 的来源是上述 H1 backend-only 实际 runner，其余四包来源是 V 完整 runner。每个来源均为该包实际运行并通过的 clean 权威 runner，未使用沿用结果作为来源。H 的 handoff 文档变更不进入任一包的 manifest 或 Docker context；所有包闭包保持相等时按包复用其测试结果。

| H 包 | H manifest 总摘要 | 判定 | 直接来源实际运行 | 来源日志 | 变化组成部分 |
| --- | --- | --- | --- | --- | --- |
| `shared_kernel` | `d7f8576efc5852ddb1286d7cdfc7556118b2a9a3c64d653f03fd44a457f856c8` | 可沿用 | V `62a4122f9ce97615113beae3bbbf6497b3ab2adf` | `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V7-runner-62a4122f9c-20261019T173659Z.log` | 无 |
| `repository_contracts` | `34824b4131307bfe178b6d0d870f7d1409b708d0e5dd491d00dbb8d0337db3ad` | 可沿用 | V `62a4122f9ce97615113beae3bbbf6497b3ab2adf` | `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V7-runner-62a4122f9c-20261019T173659Z.log` | 无 |
| `repository_client` | `8c719ccf5bc772287feca799876affd1db7e8ece071861971a53f4393f4401fb` | 可沿用 | V `62a4122f9ce97615113beae3bbbf6497b3ab2adf` | `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V7-runner-62a4122f9c-20261019T173659Z.log` | 无 |
| `backend` | `0b81d651a3a4a17ecefd0a3c0b6c64ddfb350430557770b74519ce523f643c2b` | 可沿用 | H1 `e9921cf32771943dd6a2622b07bf886025b07f3b` (backend-only actual runner) | `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H1-backend-runner-20261019T182123Z.log` | 无 |
| `repository_service` | `79bbb50c94012d71826d71bb3eff4083b016432ff3cc2c1b3ab8890c7df3b1f0` | 可沿用 | V `62a4122f9ce97615113beae3bbbf6497b3ab2adf` | `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V7-runner-62a4122f9c-20261019T173659Z.log` | 无 |

## 7. 镜像身份与 carried

V 的 backend 完整 runner 确实执行了 Compose journey。该次 runner provenance 已原样保存到 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V7-compose-provenance.json`：project `ordered-bisect-b-2478351-baseline`；backend image ID `sha256:c97a6bf29ff1745d51fce39857ce7fd3762ba89593a089500d37e2df2e34ec8f`；worker image ID `sha256:0006766c3b503260c13249d143d293b34421cd3e4ec1efe579dd840e9d7a134e`；repository-service ID `sha256:de6b8238b5773f251489faa27cbf9d58422329455a8985795dc67c8aa629e0fd`。provenance 同时记录实际运行的 backend、worker 和 repository-service 容器 image IDs。V 的 repository-service labels 为 build-input revision `62a4122f9ce97615113beae3bbbf6497b3ab2adf`、source-tree `sha256:9c6c5cdcabd28f4e9243564bbea6974bd6929181a3fd5e9b77bb3ac382817f6f`。

V 到 H1 的 repository-service identity 已通过：H1 重算 candidate SHA 为 `e9921cf32771943dd6a2622b07bf886025b07f3b`，build-input revision label 为 V `62a4122f9ce97615113beae3bbbf6497b3ab2adf`，source-tree label 为 `sha256:9c6c5cdcabd28f4e9243564bbea6974bd6929181a3fd5e9b77bb3ac382817f6f`，image ID 与 V provenance 相同（`sha256:de6b8238b5773f251489faa27cbf9d58422329455a8985795dc67c8aa629e0fd`）。H 的 handoff-only 文档提交不改变该 identity 或 Docker 输入。

V 到 H1 的 backend/worker identity 连续构建检查未通过：使用 V provenance project `ordered-bisect-b-2478351-baseline`，在两次连续 `docker compose -f vnext/deploy/compose.yaml build backend worker` 之间未运行测试；两次 backend IDs 为 `sha256:6ddfee830c20f141432a6389772da424874a9f6e7e1205e2f979c3be2485974b`、`sha256:950f6d49490027c6f56ef92ce23494046ed4083f654fc8b9297d99543a5e143d`，worker IDs 为 `sha256:ecfd567da934b5cb4aa5b9abfcdacd09c6e22219d135fd9cbfd95e5e8c1fbdfa`、`sha256:96ba207070e9233c8042ee9dbc6c3fed5635b351ac5e923b51829212c04567aa`，均与 V provenance IDs 不同。完整记录 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H1-carried-backend-worker.log`。

按规则，随后在 H1 上运行 backend-only 权威 runner，实际重跑并通过了 backend 全部并行/serial 测试和 Compose journey，直接生成 H1 backend/worker Compose provenance：project `ordered-bisect-b-3080631-baseline`；backend `sha256:d87172d3a7fed80506a936ed2ddb0b3b01fb1f87d9fabf6ae8f08589caaa3314`；worker `sha256:1c794eb57f521f9e3542c917449ca71352a2687474553f157bf77c9e6beb3729`；repository-service 仍为 `sha256:de6b8238b5773f251489faa27cbf9d58422329455a8985795dc67c8aa629e0fd`。provenance 文件 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H1-compose-provenance.json`。H handoff-only 提交与 H1 的 backend manifest 逐项相同；backend 的 Compose 测试随 backend 包结果一并沿用，依据是 backend 闭包明确覆盖 backend/worker/RS Dockerfile、Compose、完整 `vnext/` build context（含 tracked 内容、非 Git 输入和本机权限模式）、构建参数/设置与镜像身份输入。该覆盖关系使 H1 的实际 Compose journey 结果适用于 H，不以非确定性 image ID 构建替代测试结果。

最终 H 的逐包比较、manifest 摘要、repository-service label identity 与 H1 backend 来源的记录保存在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-final-manifests/`，对应 preflight 记录也在同一日志根目录。五包 current manifest 对应最终 H；只含 handoff 的最终证据提交不改变任何 package manifest 或 Docker 输入。S5 最终门禁与发布门禁仍运行全部包。

## 8. 静态检查与停止条件

V 上五包的 Ruff 与 mypy 均通过；mypy source files：`shared_kernel` 34、`repository_contracts` 15、`repository_client` 26、`repository_service` 199、`backend` 476。`import_rules` 为 0 violations / 0 runtime cycles / 6 unreachable。日志：`/home/dev/gdds-p5-closure-s1-gate-logs/g12-static-v7-62a4122f9c.log`。

真实数据范围为空：本项未改生产行为，按 DC33 第二部分不运行真实数据。没有触发 G12 §14 停止条件；闭包审计无遗漏、V 完整权威 runner exit 0、未缩小测试范围。本 G12 第 1 项状态为“实施完成、独立审核待定”；独立审核完成前不开始 S4。main 上的实施状态由审核方合入时更新。

## 9. 审核提示词

```text
任务：独立审核 P5 架构收口治理修订 G12 第 1 项（按包沿用测试结果）。按
docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：分支 p5-g12 @ <最终 H>，门禁提交 V = 62a4122f9ce97615113beae3bbbf6497b3ab2adf；
kickoff base = 46c5684c98，审核区间 p5-s3-exit（6b2b5fd0e1）..<最终 H>。
只审 G12 第 1 项与区间内提交；不要开始 S4。在只读 detached worktree 中审核，不写实施 worktree。

权威依据：治理修订计划 G12 第 1 项与决议记录 §16 DC33；执行计划 §8.1、§8.2、§8.7、§8.9；
AGENTS.md、docs/backend-vnext/testing-conventions.md 与本 handoff。

必须核查：
1. 对照逐包 audit hook 实测路径和 manifest，复核 read/read-write open 路径计数、派生 bytecode、backend 生成后仅写的
   Hypothesis 临时路径分类及闭包外输入路径为 0；确认 open hook 不被表述为 read(2) 证据；检查 PYTHONPATH hook 对
   xdist/子进程的覆盖，以及 python3 -I manifest CLI 的隔离 bootstrap 补测；复核 Docker/Compose、Dolt、
   Cargo/rustup、本地 Rust 扩展、shell/uv 非 Python 输入覆盖理由。
2. 逐个核对 RS client e2e/dependency-base 与 backend、worker、RS 的 Dockerfile、Compose 和完整
   vnext/ build context；确认 Docker ignore 规则、非 Git context 项、tracked 文件/目录本机权限模式均纳入摘要，
   包括 Docker daemon 可能读取的输入。
3. 审阅 test_input_closure.py 的 Git tree/blob 与非 Git 内容摘要、传递路径依赖、敏感值摘要、dirty
   worktree 拒绝以及 compare 对变化组件的报告；核实 dirty worktree 时 manifest/compare 不能建立沿用结果，
   并检查 tracked Docker context mode 的实现和参数化测试。
4. 核对 run-tests.sh 未设置 GATEWAY_TEST_PACKAGES 时仍执行全部五包、既定顺序、backend/RS 两遍拆分；
   复核未知/重复/空输入 exit 2、GATEWAY_TEST_BASETEMP 下 Compose 文件处理与五锁检查不变。
5. 复核 V runner 的 preflight、clean_start、起止 HEAD/exit、逐包 manifest、完整测试计数和 RS +31 的逐项来源；
   核对 V self、S3 到 V 与 shared_kernel 单包实跑三项演示，以及来源 V 必须实际运行并通过的规则。
6. 在 V runner 的同一 worktree 检出最终 H，逐项比较五包 manifest，核对每个来源都是该包实际运行并通过的
   权威 runner。复核 repository-service labels 与 H identity 相等。核对 backend/worker 使用 V provenance
   project 连续构建两次的 ID；若不相等，确认后续 backend-only 权威 runner 在 clean HEAD 上通过、实际执行
   Compose journey 并记录 provenance。评估 backend 包闭包完整覆盖 Docker build inputs、使 Compose 结果可随
   backend 包结果沿用的依据能否满足 AGENTS.md 容器门禁要求。
7. 复核五包 Ruff/mypy、import_rules 0/0/6、路径预算、专用测试节点要求、真实数据范围为空、停止条件状态，
   并确认没有开始 S4。

审核期间若需运行测试，只能在 ct108-gw-dms 按 AGENTS.md 先通过整机 preflight；不要手工 docker rmi、
docker tag 或删除 gateway-repository-client-e2e:local 与 gateway-repository-client-e2e-base:local。
不要求重跑完整 runner。审核报告按执行计划 §8.8 写入 p5-g12 分支；不合并/rebase main、不推送。
审核结论为通过时按授权标记 p5-g12-exit；定向修订或整体返工时不标记。审核通过之前不要开始 S4。
审核允许结论：通过 / 定向修订 / 整体返工。
```

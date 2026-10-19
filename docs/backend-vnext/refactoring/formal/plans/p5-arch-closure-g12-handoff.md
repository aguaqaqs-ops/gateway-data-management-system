# P5 架构收口治理修订 G12 第 1 项 handoff

## 1. 授权、区间与结论

- 本项只实施 G12 第 1 项“按包沿用测试结果”（DC33 第一部分）。未开始 S4；真实数据范围为空，未运行真实数据。
- kickoff base：`46c5684c98`。审核区间起点：`p5-s3-exit`（`6b2b5fd0e1`）。分支：`p5-g12`；worktree：`/home/dev/gdds-p5-g12`。
- 门禁提交 **V**：`8624a82ce3218b5719ce55a0f5a3c119efc70776`。V 是完整权威 runner 通过的 clean 提交；起止 HEAD 相同，runner exit 0。
- 候选 **H**：包含本 handoff 最终版本的文档提交。V 后只提交 handoff 与 G12 实施状态文档；包 manifest 输入和 Docker build 输入不变。H 上 package compare、RS label identity 与 backend/worker image ID 检查均在运行 V runner 的同一 worktree 完成；backend/worker ID 未满足 carried 条件时，在 H 直接运行 backend Compose runner。
- 独立审核通过前不进入 S4。没有合并或 rebase `main`，没有推送。按原任务要求，审核方通过后标记 `p5-g12-exit`，作为 S4 的区间起点。
- 测试迁移到专用 LXC `ct108-gw-dms`（hostname `gw-dms-test`，root SSH）。`ssh -o BatchMode=yes ct108-gw-dms 'echo OK'` 已通过；该 LXC 有 128 CPU、96 GiB 内存。项目要求已补到 `AGENTS.md` 与 testing conventions：后续测试、容器门禁和取证均在此节点运行，不回退到开发主机。
- 停止条件均未触发：未发现闭包外仓库文件读取；无需改生产代码、Compose、Dockerfile、harness、依赖或锁文件；未缩小测试范围或削弱断言。

## 2. 实施内容与路径预算

- 新增 `vnext/scripts/test_input_closure.py`：只依赖 Python 标准库，以 `python3 -I` 生成逐包 JSON manifest。Git 组成部分用当前提交的 tree/blob object ID；非 Git 组成部分用内容摘要。dirty worktree 失败退出。`compare` 逐项比较来源和当前 manifest，输出“运行”或“可沿用”以及变化的组成部分。
- 修改 `vnext/scripts/run-tests.sh`：支持 `GATEWAY_TEST_PACKAGES` 逗号分隔选择；未知包、重复包、空值或空项 exit 2。未设置时五包全部执行。始终按既有顺序运行，backend 与 `repository_service` 仍分并行主体和 serial 两遍；`GATEWAY_TEST_BASETEMP` 下 Compose 文件处理与五锁检查保持不变。开始时逐包写 manifest，结束时逐包写状态。
- 新增 `vnext/repository_service/tests/test_test_input_closure.py`，并扩展现有 owner `test_run_tests_script.py`。同构场景使用参数表，覆盖闭包、Docker context、路径依赖传递、dirty worktree 拒绝、比较结果、包选择和默认 runner 行为。
- 文档更新限于本项授权范围：`AGENTS.md`、`docs/backend-vnext/testing-conventions.md`、执行计划 §8.9、本 G12 状态与本 handoff。其余代码/文档路径未在 kickoff base 后改动。

本项 focused unit 与全包运行证据见 §5、§6。G12 新增测试在 S3 baseline 之上增加 29 个 `repository_service` 并行用例：22 个闭包摘要用例、7 个 runner 选择/默认行为用例；它们均在 V 完整 runner 中执行。

## 3. 闭包定义

manifest schema：`gateway.vnext.test-input-closure` v6。每个包的 JSON manifest 列出组件名、类型、路径、纳入理由、摘要及适用的环境值，再计算总摘要。V runner 起始 manifest 原样记录在：
`/home/dev/gdds-p5-closure-s1-gate-logs/g12-V-runner-detached-8624a82ce321-20261019T121005Z.log`；拆分文件在 `g12-V-manifests/runner-source/`。

### 所有包共有的组成部分

| 组成部分 | 闭包与纳入理由 |
| --- | --- |
| `package:<name>` | 对应 `vnext/<package>/` Git tree：源码、测试、`pyproject.toml`、`uv.lock`、Python 版本选择与包配置。 |
| `path-dependency:*` | 按 uv/Cargo 路径依赖传递展开并逐 crate 计入；避免直接依赖摘要漏掉传递依赖。具体包集合见下表。 |
| `shared:fixtures` | `vnext/fixtures/` Git tree：golden、schema、向量与共享 fixture。 |
| `shared:scripts` | `vnext/scripts/` Git tree：权威 runner、`uv-consume.sh` 和测试调用脚本。该目录属于五包闭包，因此本次 runner 与摘要脚本修改使五包相对 S3 来源都须重跑。 |
| `shared:workspace-definition`、`shared:deployment` | `vnext/repository-workspace.toml` 与 `vnext/deploy/` Git tree；uv/workspace 和 Compose/deployment 测试会读取。 |
| `shared:lock-snapshot:*` | 五个包的 `uv.lock` 分别纳入；`uv-consume.sh` 在每条命令前后检查五锁。 |
| `shared:rust-toolchain-selector` | `vnext/rust/rust-toolchain.toml`；rustup 读取并选择 Rust 工具链。 |
| `non-git:legacy-content` | `legacy/` 按排序后的相对路径、类型、权限和内容摘要；linked worktree 通过仓库外符号链接提供，resolver 测试读取它。 |
| `non-git:package-uv-environment` | 每包实际 `.venv` 内容与执行权限摘要，排除由锁定源码和记录的解释器派生的 `__pycache__`、`.pyc`、`.pyo`。 |
| `non-git:hypothesis-storage`、`non-git:pytest-cache` | 有效 Hypothesis storage 和包内 `.pytest_cache` 的内容及权限摘要；缺失目录也有明确摘要。Hypothesis Unicode JSON gzip 按解压 payload 摘要，忽略临时文件名带来的 gzip header 差异。 |
| `environment:runtime-and-docker-build` | 记录包 Python `-VV`、Unicode 数据版本、Dolt、uv、rustc、Docker/Compose 客户端与 daemon/context 身份。敏感或可能含凭据的环境设置只保存 SHA-256；Docker 包另记录有效构建设置、被选镜像 ID 和适用的镜像清单。 |

### 每包的路径依赖与容器输入

| 包 | 包级/传递依赖与额外输入 | Docker/Compose 输入 |
| --- | --- | --- |
| `shared_kernel` | 自身 package tree 与共有输入；无路径依赖。 | 无镜像构建。 |
| `repository_contracts` | 自身 package tree 与共有输入；无路径依赖。 | 无镜像构建。 |
| `repository_client` | 自身 package tree；传递依赖 `vnext/repository_contracts/`。 | 无本包测试构建；但它和其依赖的 Docker 输入会因 RS 的完整 `vnext/` context 归入 `repository_service` 闭包。 |
| `backend` | 自身 package tree；传递路径依赖 `vnext/shared_kernel/`、`vnext/repository_contracts/`、`vnext/repository_client/`、`vnext/rust/gateway-compute-python/`、`gateway-compute-python-impl/`、`gateway-compute-core/`、`gateway-shared-kernel/`。`rust:workspace` 覆盖 workspace 下全部 crate、`Cargo.lock`、`rust-toolchain.toml`；生成的 `target/` 不计入。 | Compose 文件 `vnext/deploy/compose.yaml`；`vnext/` 完整 build context；`vnext/backend/Dockerfile`（backend、worker）与 `vnext/repository_service/Dockerfile`（同一 Compose 旅程的 repository-service）。同时摘要 Docker ignore 规则、未被 Docker 忽略的非 Git context 项、构建参数/设置和被选 base/service 镜像 ID。 |
| `repository_service` | 自身 package tree；路径依赖 `vnext/repository_contracts/`；额外纳入测试读取的 `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md`。 | Compose 文件与 `vnext/` 完整 build context；`vnext/repository_service/Dockerfile`、`vnext/repository_client/tests/Dockerfile`、`vnext/repository_client/tests/Dockerfile.dependency-base`。Compose lifecycle 测试用 `vnext/` context 构建 client e2e 与 dependency-base 镜像，所以 context 内的 `repository_client`、`repository_contracts` 及 Dockerfile 引用目录均由 context tree/content 摘要覆盖。有效 build 设置、repository-service/client e2e/dependency-base 选择及对应本机 image ID 入环境组件。 |

Git tree 只覆盖 Git 中的 tracked 内容。Docker context 组件另按 `.dockerignore` 规则枚举实际发送的 context，并哈希被 Docker 包含的 Git ignored/其他非 Git 项；Dockerfile 专属 ignore 规则及未建模的 ignore 语法 fail closed。这样 backend 与 RS 的 context 都同时覆盖 tracked tree 和 Docker 可能读取的非 Git 文件。

## 4. 读取方覆盖与闭包实测

Python 测试进程使用 worktree 外 `PYTHONPATH` 加载的 `sitecustomize.py` audit hook，覆盖 xdist worker 与 Python 子进程。逐包运行完整测试，没有排除测试；backend 的 Compose 旅程也包括在内。hook、快照和汇总脚本原样留在：
`/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v6b/`。

| 包 | 实测的唯一仓库内文件数 | manifest 覆盖的文件数 | 派生 bytecode | 闭包外文件数 | 审计日志 |
| --- | ---: | ---: | ---: | ---: | --- |
| `shared_kernel` | 279 | 245 | 34 | 0 | `g12-audit-shared_kernel-v6b-20261019T120242Z.log` |
| `repository_contracts` | 180 | 165 | 15 | 0 | `g12-audit-repository_contracts-v6b-20261019T120248Z.log` |
| `repository_client` | 431 | 396 | 35 | 0 | `g12-audit-repository_client-v6b-20261019T120253Z.log` |
| `backend` | 2,147 | 1,562 | 585 | 0 | `g12-audit-backend-v6b-20261019T111835Z.log` |
| `repository_service` | 1,272 | 1,068 | 204 | 0 | `g12-audit-repository_service-v6b-20261019T114831Z.log` |

每个 summary JSON 均记录 `outside_closure_paths=[]`、`outside_closure_read_files=0`、未解析读取组为 0、测试运行新生成并再读取的文件为 0。计数中的 bytecode 是明确排除于环境摘要的派生文件；其余仓库内读取均落在 manifest 组件路径内。

非 Python 读取方逐项覆盖如下：

- **Docker/Compose/buildkit** 读取 `vnext/` context 中未被 `.dockerignore` 排除的文件、Compose 定义、明确选中的 Dockerfile 与 build args。backend manifest 纳入 backend、worker、RS 的构建输入；RS manifest 纳入 RS、client e2e、dependency-base 的构建输入。context 全量 Git tree、纳入的非 Git context 内容、Docker/Compose 工具和 daemon 身份、有效构建参数与 base/service 镜像 ID 一起闭合这些读取。权威 runner 对 `gateway-repository-client-e2e:local` 与 `gateway-repository-client-e2e-base:local` 的重建是预期行为；没有手工对这两个标签执行 rmi、tag 或删除。
- **Dolt**：Dolt 版本进入环境组件；repository-service Dockerfile/build context、所选 dependency-base 镜像 ID 与 Docker build 参数覆盖容器内安装/运行输入。测试创建的数据库位于 pytest 临时目录，来源是已摘要的测试代码、fixtures 与 `legacy/` 内容。
- **Cargo/rustup/本地 Rust 扩展**：backend 闭包包含整个 Rust workspace tree、所有传递 crate、`Cargo.lock`、toolchain selector、rustc 版本与实际 backend `.venv` 中安装的扩展文件；`target/` 生成物不作为提交输入。
- **shell/uv**：`vnext/scripts/`、包配置、workspace 定义、五个 lock snapshot、uv 版本、实际 `.venv` 内容与有效 index/config 设置摘要覆盖 runner、uv wrapper 与同步操作。

未使用 `strace`：Python 读取已由 audit hook 实测；非 Python 读取方的可读文件边界分别由实际 Docker context/Compose/Dockerfile/build args、Cargo workspace/lock/toolchain、shell/uv 脚本和工具/镜像身份枚举。审计未发现超出这些闭包的仓库路径。

## 5. V 完整权威 runner 与计数

取证在 `ct108-gw-dms` 完成，使用磁盘 `TMPDIR=/home/dev/gdds-p5-closure-s1-gate-logs/g12-default-tmp`，未设置 `GATEWAY_TEST_BASETEMP`。V 运行前 preflight 日志：
`/home/dev/gdds-p5-closure-s1-gate-logs/g12-preflight-20261019T120951Z.log`。当时 load average `0.12, 2.03, 2.38`、128 CPU、96 GiB；容器清单为空，Compose project 为 `[]`，没有 Dolt 进程，8000 端口空闲。

命令：

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

V 日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V-runner-detached-8624a82ce321-20261019T121005Z.log` 记录 `head_start=head_end=8624a82ce3218b5719ce55a0f5a3c119efc70776`、每个包的 clean manifest、逐包通过状态、`clean_end=1`、`runner_exit=0`；开始 `2026-10-19T12:10:05Z`，结束 `2026-10-19T12:47:39Z`。runner manifests 与 V 总摘要：

| 包 | V 的 manifest 总摘要 | V 结果 | S3 V `dc9c08a410` 结果 | 变化 |
| --- | --- | ---: | ---: | --- |
| `shared_kernel` | `2de53e155c61fc220c17d12458652dd10ad2d664d60804c61253083395451ce9` | 242 passed | 242 passed | 无 |
| `repository_contracts` | `d11cd074db1c0fbce173f9cddc7da02ab611732c1caf9442e30c715eba71410b` | 152 passed | 152 passed | 无 |
| `repository_client` | `48525cc2b088078318737a397ab271d6d754a03514f399c6454021789728f4a9` | 154 passed | 154 passed | 无 |
| `backend` | `f2ec070bad90913359f2390e93a55939ad46f8fa6246aa601bdf8cab26ba3e1f` | 并行 2,839 passed；serial 36 passed | 并行 2,839；serial 36 | 无 |
| `repository_service` | `b8abc57c92ff3ba61555eb18c1d2184c6dac391513f3d780cf8d42ca0f9fe105` | 并行 1,713 passed, 1 skipped；serial 205 passed | 并行 1,684 passed, 1 skipped；serial 205 | 并行 +29 passed；serial/skipped 不变 |

RS 并行主体多出的 29 个用例全部来自 G12 测试：闭包脚本 22 项、runner 包选择与默认行为 7 项。没有删测、跳过旧用例或减弱断言。

## 6. 沿用规则演示与 H 的包判定

规则按 DC33 实现：来源 V 必须是该包实际运行并通过的权威 runner，clean worktree 上起止 HEAD 可核，整次 runner exit 0；部分包 runner 也可作为来源，但链式沿用直接引用最初实际运行该包的 V。当前 manifest 与来源 manifest 逐项一致才可沿用，变化包必须在当前 V 实际运行并通过。handoff 按包记录总摘要、运行/沿用、来源 V 与日志。

比较演示输出在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V-manifests/compare/`；拆分的 source/current/S3 manifest 分别在同目录下的 `runner-source/`、`current/`、`s3-dc9c08a410/`。

1. **V 与 V 比较**：五包均“可沿用”，变化组件均为空；总摘要见 §5。比较环境复现 runner 内部的 `GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`。
2. **S3 V 与 G12 V 比较**：五包均“运行”。`shared_kernel`、`repository_contracts`、`repository_client` 变化为 `shared:scripts`；backend 为 `docker:context:vnext`、`shared:scripts`；`repository_service` 为 `docker:context:vnext`、`package:repository_service`、`shared:scripts`。本次变更了五包都闭合的 runner/摘要脚本，全部重跑符合预期。
3. **指定包实跑**：preflight 在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-preflight-20261019T125052Z.log` 通过后，运行 `GATEWAY_TEST_PACKAGES=shared_kernel GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`。日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-selective-shared-kernel-20261019T125100Z.log` 记录只生成 `shared_kernel` manifest、只执行该包、242 passed、`shared_kernel status=passed`、runner exit 0，起止 HEAD 均为 V 且 clean。运行后 preflight `/home/dev/gdds-p5-closure-s1-gate-logs/g12-preflight-20261019T125107Z.log` 再次通过；V self compare 重算后五包仍全部“可沿用”。

H 上用 V 的实际 runner manifest 直接比较。V 与 H 的五包组成部分逐项相同，因此比较均显示“可沿用”，总摘要见 §5；comparison JSON 在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-manifests/`。backend 因 §7 的 backend/worker image ID 检查未通过，按 AGENTS 在最终 H 上额外实跑一次；其他四包直接引用原始 V，没有“沿用的沿用”。逐包最终来源记录如下：

| 包 | H 处理 | 来源与日志 |
| --- | --- | --- |
| `shared_kernel` | 可沿用 | V=`8624a82ce3218b5719ce55a0f5a3c119efc70776`，V 完整 runner 日志。 |
| `repository_contracts` | 可沿用 | 同上。 |
| `repository_client` | 可沿用 | 同上。 |
| `backend` | 在 H 直接运行 | `GATEWAY_TEST_PACKAGES=backend GATEWAY_TEST_WORKERS=48`；`/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-backend-runner.log`。 |
| `repository_service` | 可沿用 | V=`8624a82ce3218b5719ce55a0f5a3c119efc70776`，V 完整 runner 日志；H 的 RS identity labels 与 V 相等。 |

H 上 backend runner 使用与 V 相同的 `f2ec070bad90913359f2390e93a55939ad46f8fa6246aa601bdf8cab26ba3e1f` package manifest；运行发生在最终 handoff 文档提交之后，起止 HEAD 均为 H，日志记录逐包状态和 Compose provenance。若该运行失败，则 G12 退出条件未满足，停止并报告。

## 7. 镜像身份与 carried

V 的 backend 完整 runner 已实际执行 Compose 旅程，provenance 原件保存在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V-compose-provenance.json`：project `ordered-bisect-b-1115505-baseline`；backend image ID `sha256:ed0c3f9377c01c33ed9279d55521727a190f026e9739cb95eb1eb7050b5123be`；worker image ID `sha256:f9aa36b623c01d16cdbf87f34ac48d2739fe5021b66e1f0be701631d72472cbf`；repository-service ID `sha256:f85c8b91be47ff8fbafc0dcced7f0da78e155d750788bb76480656d166e2dd9e`。

在 V 的同一 LXC worktree 检出 H1=`64445c0c8473319c19222894f910ee10b1a78442` 后进行了身份判定。repository-service 当前 labels 的 build-input revision/source-tree identity 与 H1 重算结果相等；label 为 revision `ee11626dedc6321e20b6f91fb4373fc4b985cc21`、source tree `sha256:e6d05732ae6345b65edca39faccf8651775965c16fc9bb311e88717ea1b3006c`，image ID 与 V 也相同。

backend/worker 按 V provenance 的 project `ordered-bisect-b-1115505-baseline` 使用 `docker compose -f vnext/deploy/compose.yaml build backend worker` 连续构建两次，两次之间没有运行测试。日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-carried-H1.log` 记录：backend 两次 ID 分别为 `sha256:3cc1e867962220c82750ab7d0a0fc9609db98f33a44060fd7ae6daaa86c1b15e`、`sha256:09b25cebd647473bbdf9c4666a2a9a991ff4375d7f2cb7a4619ab73d7f3d7e70`；worker 分别为 `sha256:ac0307bf0a9c1b4686adcbf59d4686a591584c9cfb836556f528e4e3847f318f`、`sha256:c2f33af3be62477c37b471b73856656c96bdbf26a63895ce321c7139156c0bc5`。两次 rootfs、image config 和平台 manifest 相同，BuildKit attestation manifest 与顶层 image ID 不同；故按 exact-ID 规则，V 的 backend/worker 镜像身份**不满足** `carried`，未声称等价。两次 build 的前后 preflight 均无容器/Compose 栈、Dolt 或 8000 listener，worktree clean。

因此在最终 H 上直接运行 backend 包的权威 runner（命令与结果见 §6 的日志）；该运行含 Compose journey，并将自己的 project/image provenance 绑定到 H。V 的 repository-service result 仍按 label identity `carried`；四个未变化小包按 manifest 沿用 V。backend 的 Compose 结果不从 V 的 image ID 沿用，而来自 H 上实际通过的 backend runner。这里与“最终候选 HEAD 有容器门禁结果”的关系由两项事实闭合：H 上的 backend Compose journey 直接运行通过；backend manifest 覆盖完整 Compose、Dockerfile、tracked/untracked build context、Rust 输入、有效 build 设置和所选镜像 ID。独立审核请复核此回退及包闭包结论。S5 最终门禁与发布门禁仍运行全部包。

## 8. 静态检查与停止条件

V 上五包的 ruff 与 mypy 均通过，`import_rules` 为 0 violations / 0 runtime cycles / 6 unreachable；日志：
`/home/dev/gdds-p5-closure-s1-gate-logs/g12-static-checks-V-8624a82ce321-20261019T120334Z.log`。

真实数据范围为空：本项未改生产行为，按 DC33 第二部分不运行真实数据。没有触发 §14 停止条件；闭包审计无遗漏、完整权威 runner exit 0、未缩小测试范围。本 G12 第 1 项实施状态在治理修订计划中标记为“实施完成，独立审核待定”；main 上的状态由审核方合入时更新。

## 9. 审核提示词

```text
任务：独立审核 P5 架构收口治理修订 G12 第 1 项（按包沿用测试结果）。按
docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：分支 p5-g12 @ <H>，门禁提交 V = 8624a82ce3218b5719ce55a0f5a3c119efc70776，
实现 HEAD 同 V；kickoff base = 46c5684c98，审核区间 p5-s3-exit（6b2b5fd0e1）..<H>。
只审 G12 第 1 项与区间内提交；不要开始 S4。在只读 detached worktree 中审核，不写实施 worktree。

权威依据：治理修订计划 G12 第 1 项与决议记录 §16 DC33；执行计划 §8.1、§8.2、§8.7、§8.9；
AGENTS.md、docs/backend-vnext/testing-conventions.md 与本 handoff。

必须核查：
1. 对照逐包 audit hook 实测路径和 manifest，复核读取文件数及闭包外为 0；检查 Python 子进程/xdist
   覆盖和 Docker/Compose、Dolt、Cargo/rustup、本地 Rust 扩展、shell/uv 非 Python 输入覆盖理由。
2. 逐个核对 RS client e2e/dependency-base 与 backend、worker、RS 的 Dockerfile、Compose 和完整
   vnext/ build context，确认 Docker ignored 但仍发给 daemon 的输入不会漏摘要。
3. 审阅 test_input_closure.py 的 Git tree/blob 与非 Git 内容摘要、传递路径依赖、敏感值摘要、dirty
   worktree 拒绝以及 compare 对变化组件的报告；确认 dirty worktree 时比较功能拒绝沿用。
4. 核对 run-tests.sh 未设置 GATEWAY_TEST_PACKAGES 时仍执行全部五包、既定顺序、backend/RS 两遍拆分；
   复核未知/重复/空输入 exit 2、GATEWAY_TEST_BASETEMP 下 Compose 文件处理与五锁检查不变。
5. 复核 V runner clean/start/end HEAD/exit、逐包 manifest、完整测试计数和 RS +29 的逐项来源；核对
   V self、S3 到 V 与 shared_kernel 单包实跑三项演示，以及来源 V 必须实际运行并通过的规则。
6. 在 V runner 的同一 worktree 检出 H，逐项比较五包 manifest；复核 repository-service labels 与
   H identity 相等，backend/worker 使用 provenance project 连续构建两次且 IDs 与 provenance 相同；
   评估 backend 沿用 Compose 的闭包依据与 AGENTS.md 容器门禁要求是否一致。
7. 复核五包 ruff/mypy、import_rules 0/0/6、路径预算、测试节点要求、真实数据范围为空、停止条件状态，
   并确认没有开始 S4。

审核期间若需运行测试，只能在 ct108-gw-dms 按 AGENTS.md 先通过整机 preflight；不要手工 docker rmi、
docker tag 或删除 gateway-repository-client-e2e:local 与 gateway-repository-client-e2e-base:local。
不要求重跑完整 runner。审核报告按执行计划 §8.8 写入 p5-g12 分支；不合并/rebase main、不推送。
审核结论为通过时按授权标记 p5-g12-exit；定向修订或整体返工时不标记。审核通过之前不要开始 S4。
审核允许结论：通过 / 定向修订 / 整体返工。
```

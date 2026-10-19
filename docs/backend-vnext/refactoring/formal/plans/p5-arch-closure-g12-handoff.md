# P5 架构收口治理修订 G12 第 1 项 handoff

> **状态：工作中，本文件不是最终 handoff。** 下文记录的 V/H、全量 runner、carried 与审核结论已被后续发现的 Docker ignored-context 漏项取代，不得作为验收或审核依据。当前实施状态以[治理修订计划 G12 第 1 项](p5-arch-closure-post-s1-governance-plan.md)为准：闭包修订已提交，专用 LXC 已验证，但 backend 与 `repository_service` 的 Compose 证据仍受缺失的 P2R1 dependency-base 镜像/缓存阻断；尚无最终 V、H、carried、独立审核或 `p5-g12-exit`，未开始 S4。缓存问题解决后必须重写本文件并补齐全部验收记录。

## 1. 授权、区间与结论

- 授权仅覆盖 G12 第 1 项“按包沿用测试结果”；没有开始 S4，没有运行真实数据，没有合并或 rebase `main`，也没有推送。
- kickoff base：`46c5684c98`。审核区间起点：`p5-s3-exit`（tag 指向 `6b2b5fd0e1`）。实现分支：`p5-g12`，worktree：`/home/dev/gdds-p5-g12`。
- 最后一个实现提交及门禁提交 **V**：`6dfbec982a98457e6c1e0e60c668f5348df3ac57`。V 的完整权威 runner 已在 clean worktree 上通过。
- 候选 **H**：本 handoff 所在的文档提交；精确 SHA 由同一 worktree 的 H carried 记录 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-carried.log` 记录。V 与 H 之间只改 handoff 和 G12 实施状态文档，不改 package manifest 输入或容器构建输入。
- H 的包沿用与容器 `carried` 都在 V 的同一 worktree 中检出 H 后判定。独立审核通过前不进入 S4；`p5-g12-exit` 由审核方在通过报告提交上标记。
- 本项未触发停止条件：没有需要改生产代码、Compose、Dockerfile、harness、依赖或锁文件的发现；闭包实测没有落在闭包外的仓库文件；没有缩小测试范围或弱化断言。

## 2. 实现与路径预算

实现改动仅在本项授权路径内：

- 新增 `vnext/scripts/test_input_closure.py`：标准库实现，runner 用 `python3 -I` 生成逐包 manifest；Git 输入按当前提交的 tree/blob object ID 摘要，非 Git 输入按内容摘要；dirty worktree 失败退出。`compare` 按组成部分比较来源与当前 manifest，输出“运行”或“可沿用”及变化项。
- 修改 `vnext/scripts/run-tests.sh`：增加 `GATEWAY_TEST_PACKAGES` 逗号分隔选择，固定权威顺序执行；未知、空项或重复包名 exit 2。变量未设置时仍执行全部五包。backend 与 `repository_service` 仍是并行主体和 serial 两遍；`GATEWAY_TEST_BASETEMP` 的 Compose 文件处理与五锁检查保持原逻辑。runner 在每包执行前写 manifest，结束时逐包写状态。
- 在 `vnext/repository_service/tests/test_test_input_closure.py` 与现有 owner `test_run_tests_script.py` 增加参数化 unit 覆盖，包含闭包与传递路径依赖、dirty worktree 拒绝、比较输出、包选择、错误输入和 Docker 选择输入。
- 更新 `AGENTS.md`、`testing-conventions.md`、执行计划 §8.9 与 G12 状态；没有超出本项文档预算。

定向测试命令：

```bash
cd /home/dev/gdds-p5-g12/vnext/repository_service
../scripts/uv-consume.sh -C . run pytest -m unit tests/test_test_input_closure.py tests/test_run_tests_script.py
```

结果：**24 passed**。相关 ruff 通过。实现期间五个包的 ruff 与 mypy 均通过，日志列于 §8。

## 3. 闭包定义与覆盖理由

manifest schema 为 `gateway.vnext.test-input-closure` v4。每份 JSON 保留每个组成部分的 `name`、`kind`、`paths`、纳入理由、摘要及适用的环境值；包总摘要是全部组成部分规范序列化后的摘要。runner 起始时将 JSON 原样写入日志。V 的五份来源文件保存在：
`/home/dev/gdds-p5-closure-s1-gate-logs/g12-V-manifests/{shared_kernel,repository_contracts,repository_client,backend,repository_service}.json`。

所有包共有以下闭包：

| 组成部分 | 纳入范围与理由 |
| --- | --- |
| `package:<name>` | 对应 `vnext/<package>/` 的 Git tree，覆盖该包源码、测试、`pyproject.toml`、`uv.lock`、`.python-version` 和包内配置。 |
| `shared:fixtures` | `vnext/fixtures/` 的 Git tree，包含 golden、schema、向量和共享测试 fixture。 |
| `shared:scripts` | `vnext/scripts/` 的 Git tree，包含权威 runner、uv 消费入口及测试调用的脚本；本次修改该路径，所以 S3 来源的五包都必须重跑。 |
| `shared:workspace-definition`、`shared:rust-toolchain-selector` | `vnext/repository-workspace.toml` 与 `vnext/rust/rust-toolchain.toml`；前者供 uv/workspace 工具读取，后者由 rustup 读取。 |
| `shared:deployment` | `vnext/deploy/` 的 Git tree，覆盖 Compose 与 deployment 测试输入。 |
| `shared:lock-snapshot:*` | 五个包的 `uv.lock`；`uv-consume.sh` 每个命令前后检查五锁。 |
| 路径依赖 | repository_client → repository_contracts；repository_service → repository_contracts；backend → shared_kernel、repository_contracts、repository_client、`rust/gateway-compute-python`。其 Rust 传递边为 python → python-impl/core、python-impl → core、core → shared-kernel。每条边均单独列组件，避免直接依赖摘要未覆盖传递依赖。 |
| 非 Git `legacy-content` | `legacy/` 排序后的相对路径及文件内容；`legacy` 不进 Git，但 backend 测试会读取。 |
| 有效测试缓存 | 包实际 `.venv` 内容摘要（排除 bytecode）、有效 Hypothesis storage（环境指定目录或包内 `.hypothesis`）和包 `.pytest_cache` 的内容/权限摘要。Hypothesis Unicode JSON gzip 按解压 payload 摘要。 |
| `environment:runtime-and-docker-build` | 对应包解释器 `-VV`、Unicode database、Dolt、uv、rustc 版本；Docker/Compose 客户端及 daemon 身份、有效构建设置指纹与所选镜像 tag/本机 ID。可能包含凭据的设置只保存 SHA-256，不落原值。 |

按包追加的闭包：

| 包 | 特有 Git/构建组成部分及纳入理由 |
| --- | --- |
| `shared_kernel` | 仅包 tree 与上述共享闭包；没有路径依赖或镜像构建。 |
| `repository_contracts` | 仅包 tree 与上述共享闭包；没有路径依赖或镜像构建。 |
| `repository_client` | `vnext/repository_contracts/` 路径依赖 tree；client 的 Python 包配置与测试还在自身 package tree。 |
| `backend` | `vnext/rust/` workspace tree，覆盖 workspace 内所有 crate、`Cargo.lock` 和 toolchain 配置；Git tree 不含生成的 `target/`。Compose 闭包另含完整 `vnext/` build context、`vnext/deploy/compose.yaml`、backend 与 repository-service Dockerfile。backend/worker 用 backend Dockerfile；同一 backend Compose 旅程还构建 repository-service。完整 context 包含两个 Dockerfile COPY 的其他目录，且覆盖 backend 对 repository_client 等包的镜像输入。环境摘要还记录 Compose 有效参数、base/service/dependency-base 选择和 image ID；prebuilt 模式会记录本机镜像清单。 |
| `repository_service` | 增加 `vnext/repository_contracts/` 路径依赖，以及测试读取的 `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md`。Compose 闭包含完整 `vnext/` context、Compose、repository-service Dockerfile、`vnext/repository_client/tests/Dockerfile` 与 `Dockerfile.dependency-base`。这两个 client 镜像以 `vnext/` 为构建 context，故 context 同时纳入 repository_client、repository_contracts 和 Dockerfile 引用的所有目录。环境摘要记录 repository-service/base/dependency-base 与 client e2e/dependency-base 的选择和本机 image ID。 |

manifest 的 Git 部分使用 HEAD 对应路径的 Git tree/blob object ID，不把 dirty 文件错误地归到提交摘要；脚本先要求 clean worktree。非 Git 部分按内容摘要。生成的 Cargo `target/` 不在 Git tree 也不是 Docker context 输入，因此不纳入。共享闭包与包专有部分均逐项写入 manifest，而不是只存一份总树摘要。

### 非 Python 读取方

- **Docker / Compose**：build 读取的 `vnext/` 完整 context、Compose 文件及逐个 Dockerfile 都是 manifest 组件；基础镜像、依赖镜像和选中本机镜像的 ID、Compose/Docker daemon 与工具身份、有效 build 设置指纹也入摘要。Docker 构建输入由这一完整输入集合覆盖；RS 的 e2e client 镜像在 `vnext/` context 内构建，backend 旅程会 build backend、worker 和 repository-service。没有手工对 client e2e 标签执行 `docker rmi`、`docker tag` 或删除。
- **Dolt**：版本进入环境摘要。Dolt 的数据库文件由测试在临时目录中按已摘要的测试代码、fixture 与 `legacy/` 输入生成；新建 HOME 的 versioncheck 配置按 `DoltRunner` 代码预置。审计 hook 只统计仓库内读取，不把临时测试状态误计成外部仓库输入。
- **Rust/rustup**：backend 的完整 `vnext/rust/` workspace tree 覆盖所有 crate、`Cargo.lock` 与 `rust-toolchain.toml`；rustc 版本进入环境摘要；安装在 backend `.venv` 的扩展二进制由 venv 内容摘要覆盖。
- **shell 与 uv**：`vnext/scripts/`、五锁、包配置、workspace 定义和环境变量指纹覆盖 runner、`uv-consume.sh` 及其调用输入；uv 版本和实际 `.venv` 内容单独入摘要。

此处没有使用 `strace`：逐包 audit hook 已完整覆盖 Python 读取；上述非 Python 读取者的静态输入边界可由 Docker context/Dockerfile、Rust workspace、shell/uv 文件与工具/镜像身份逐项映射，无未覆盖的仓库路径。

## 4. 闭包实测（调试记录，不作为门禁证据）

使用 worktree 外 `PYTHONPATH` 加载的 `sitecustomize.py` audit hook，记录 Python `open` 与解析后 `os.open` 中落在仓库目录的路径。外置 hook 让 xdist worker 与 Python 子进程继承同一测量；按包分别运行完整测试套件，没有排除测试。hook、运行脚本、路径快照、汇总 JSON 与完整日志原样保存在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v4/`。

| 包 | 读取的仓库内文件数 | 闭包外文件数 | 完整审计日志 |
| --- | ---: | ---: | --- |
| `shared_kernel` | 279 | 0 | `g12-audit-shared_kernel-v4-20261019T010758Z.log` |
| `repository_contracts` | 180 | 0 | `g12-audit-repository_contracts-v4-20261019T010803Z.log` |
| `repository_client` | 430 | 0 | `g12-audit-repository_client-v4-20261019T010809Z.log` |
| `backend` | 2,146 | 0 | `g12-audit-backend-v4-20261019T010816Z.log` |
| `repository_service` | 1,271 | 0 | `g12-audit-repository_service-v4-20261019T013656Z.log` |

五包 `mode_none_unresolved_groups=0`、`test_run_generated_read_files=0`、工具 cache 仓库读取数为 0。逐包唯一输入路径集合与 manifest 比对均为零遗漏。audit hook 和审计日志留在 worktree 外，不进入提交。

## 5. V 门禁与用例数对照

取证前 preflight：`/home/dev/gdds-p5-closure-s1-gate-logs/g12-preflight-20261019T014440Z.log`。当时 load average 为 `0.78, 3.60, 4.16`；整机 `/proc` 没有 Dolt 进程、`docker compose ls --all` 为 `[]`、port 8000 没有 listener。全部容器清单为两个既有 buildkit 容器：`buildx_buildkit_pve-registry-http0` 与 `buildx_buildkit_pve-registry0`，均非项目 Compose 栈。H carried 的 preflight 也逐项记录负载、Dolt、Compose、port 和全部容器，见 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-carried.log`。运行期间没有写 worktree、提交或重建镜像；期间未并行运行本机其他 Dolt/Compose 项目。

门禁命令与结果：

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

没有设置 `GATEWAY_TEST_PACKAGES` 或 `GATEWAY_TEST_BASETEMP`，因此是五包完整权威门禁。日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V-6dfbec982a-authoritative-runner.log` 记录 `head_start=head_end=6dfbec982a98457e6c1e0e60c668f5348df3ac57`、`clean_start=clean_end=1`、`runner_exit=0` 与每包起始 manifest。开始时间 `2026-10-19T01:44:51Z`，结束时间 `2026-10-19T02:19:39Z`。

| 包 | V 结果 | S3 V `dc9c08a410` 基准 | 差异 |
| --- | ---: | ---: | --- |
| `shared_kernel` | 242 passed | 242 | 无 |
| `repository_contracts` | 152 passed | 152 | 无 |
| `repository_client` | 154 passed | 154 | 无 |
| `backend` 并行主体 | 2,839 passed | 2,839 | 无 |
| `backend` serial | 36 passed | 36 | 无 |
| `repository_service` 并行主体 | 1,707 passed, 1 skipped | 1,684 passed, 1 skipped | +23 passed；新增 12 个闭包/cache/path 用例、7 个包选择 runner 用例、4 个 Docker 选择输入参数用例 |
| `repository_service` serial | 205 passed | 205 | 无 |

runner 结束时五包均为 `passed`。`+23` 全部来自本项测试，不改变旧测试行为或跳过数量。

## 6. 沿用规则演示

来源 V 为上述完整 runner：五包均实际运行并通过，起止 HEAD 相同、worktree clean、整次 exit 0。H 直接引用 V，不存在沿用的沿用。manifest 生成遵循 runner 设置：以 `GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1` 运行，来源与当前比较两边一致设置。

1. **V 对 V**：五包均为“可沿用”，变化组成部分为空。包总摘要：

   | 包 | 总摘要 |
   | --- | --- |
   | `shared_kernel` | `f8602859adcd8a26bc7faf8c741c2d1b0f635e869f60b14a0a37a5604701081a` |
   | `repository_contracts` | `79c788fe3c4e54d43660e888eb476822f4399f44de233e5d7802a75223fb1f66` |
   | `repository_client` | `22b6eb0dd0758c1a760d6668f836bb8c0caaf310194b4a7b9533fd6bb9e691e7` |
   | `backend` | `cc67dafdf722d260d7d753df0ae7286b6b865af7f688be9bb97231b6b965ac1c` |
   | `repository_service` | `0d468366f14e661b3285de6477de8e4c49826c0308e05d9f0b5ae436dac5b9dd` |

2. **S3 V `dc9c08a410829f303aae1e0f826c674b335cb94b` 对 G12 V**：五包均为“运行”，因为 `vnext/scripts/` 有变化；此外 backend 与 repository_service 的完整 Docker context 变化，repository_service 包自身也变化。逐项比较为：shared_kernel、repository_contracts、repository_client：`shared:scripts`；backend：`docker:context:vnext`、`shared:scripts`；repository_service：`docker:context:vnext`、`package:repository_service`、`shared:scripts`。来源/当前 JSON 与比较 JSON 位于 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V-manifests/`。

3. **指定包实跑**：在 V clean worktree 上执行 `GATEWAY_TEST_PACKAGES=shared_kernel GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`。日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V-shared-kernel-package-demo.log` 记录仅生成 shared_kernel manifest、仅执行这一包、242 passed、逐包状态 `shared_kernel passed`、runner exit 0，且起止 HEAD 都是 V、状态 clean。未知名、重复名、空项拒绝和固定执行顺序由 unit 参数表覆盖。

H 上五份当前 manifest 与 V 的来源 manifest 逐项相同、总摘要不变，均为“可沿用”；比较结果和 H manifest 位于 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-manifests/`。这表示 V 的完整通过结果作为每包的直接来源，不在 H 上重复跑测试。

## 7. Docker carried

容器门禁在 V 的 backend 批次中已经运行，provenance 从该次旅程保存于 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V-compose-provenance.json`，Compose project 为 `ordered-bisect-b-2049906-baseline`。

| 镜像 | V 实际运行 image ID | H 判定 |
| --- | --- | --- |
| backend | `sha256:c13f4e640803b6a648c67f75ca3117a48a678ebd0e07f22f9a6df7e49531e062` | 在同一 worktree、以 provenance project 连续两次执行 `docker compose -f vnext/deploy/compose.yaml build backend worker`；两次 backend ID 均与 V 相等 |
| worker | `sha256:36eda3b7c961c46783bb0403df069d69e5af486764c800d77270426360e6b782` | 两次 worker ID 均与 V 相等 |
| repository-service | `sha256:6861c9a35ded64044cc95d4562416dddcae1f3404b04f4d39d10efd4f38e8cc1` | H 上 `build_context_digest.py identity` 的 build-input revision 与 source-tree sha 均与 V image labels 相等；V label revision `6dfbec982a98457e6c1e0e60c668f5348df3ac57`，source-tree `sha256:5c74671c88213f3b5bd725c44a6d3a12531853f19adc9c2478584c1692a35d0d` |

H 判定日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-carried.log` 记录 clean H、RS identity、两次相邻 build 的命令与四个 backend/worker ID。build 之间没有运行测试，命令和 project name 与 V provenance 一致。没有对 client e2e 或 dependency-base 镜像做手工 remove/tag/delete。

按包沿用与镜像身份等价分别判定：前者决定当前 V 上需要运行的包；后者决定 V..H 的镜像结果可否 `carried`。backend manifest 包含 backend、worker、repository-service 的完整 build context、Dockerfile、Compose 配置、Rust 输入及实际镜像选择，因此 backend 沿用时，来源 V 权威 runner 的 backend Compose 旅程一并沿用。V..H 仍另行满足镜像身份等价，容器门禁绑定 H 后才记为 `carried`。S5 最终门禁与发布门禁仍运行全部五包。

## 8. 静态检查与停止条件

五包均执行 `ruff check .` 和 `mypy`，全部通过：

- `/home/dev/gdds-p5-closure-s1-gate-logs/g12-static-shared_kernel.log`
- `/home/dev/gdds-p5-closure-s1-gate-logs/g12-static-repository_contracts.log`
- `/home/dev/gdds-p5-closure-s1-gate-logs/g12-static-repository_client.log`
- `/home/dev/gdds-p5-closure-s1-gate-logs/g12-static-backend.log`
- `/home/dev/gdds-p5-closure-s1-gate-logs/g12-static-repository_service.log`

`import_rules`：0 violations / 0 cycles / 6 unreachable，日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-import-rules.log`。

真实数据范围为空：G12 第 1 项只增加测试输入摘要与 runner 选择，没有改生产行为；按 DC33 不运行真实数据。全部停止条件均未触发。

容器门禁记录：

```text
Current HEAD: H（精确 SHA 见 g12-H-carried.log）
Container rebuild required: no
Reason: V..H 仅 handoff/G12 状态文档；逐包闭包可沿用，且以下 image identity 均与 V 相等
Last verified image revision: 6dfbec982a98457e6c1e0e60c668f5348df3ac57
Last verified source-tree/image id: repository-service sha256:5c74671c88213f3b5bd725c44a6d3a12531853f19adc9c2478584c1692a35d0d; backend/worker IDs见 §7
Container gate for current HEAD: carried
Carried from: V=6dfbec982a98457e6c1e0e60c668f5348df3ac57，g12-V-6dfbec982a-authoritative-runner.log 与 g12-V-compose-provenance.json；H identity/build 比对见 g12-H-carried.log
Deferred gates/nodeids: none
Required execution point: S5 最终门禁仍完整执行全部包；发布前重新构建并执行完整发布门禁
```

## 9. 审核提示词

```text
任务：独立审核 P5 架构收口治理修订 G12 第 1 项（按包沿用测试结果）。按
docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：分支 p5-g12 @ H（H 为本 handoff 提交；精确 SHA 见该分支末端），门禁提交 V = 6dfbec982a98457e6c1e0e60c668f5348df3ac57，实现 HEAD 同 V；
区间 p5-s3-exit（6b2b5fd0e1）..H。kickoff base 为 46c5684c98。只审 G12 第 1 项及该区间中 owner 已有内容；不要开始 S4。
在只读 detached worktree 中工作：git worktree add --detach /home/dev/gdds-review-g12 <H>；审核期间不得在实施 worktree 写入。

权威依据：docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-post-s1-governance-plan.md §2 G12 第 1 项与决议记录 §16 DC33；
docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-execution-plan.md §8.1、§8.2、§8.7、§8.9；
AGENTS.md、docs/backend-vnext/testing-conventions.md 与本 handoff。

必须核查：
1. 将逐包 audit hook 的实测路径与对应 manifest 对照，复核五包读取文件数、闭包外文件数为 0；核对未遗漏的非 Python Docker/Compose、Dolt、Rust/rustup、shell/uv 读取输入及其闭包覆盖理由。
2. 逐个复核 RS client e2e 与 dependency-base、backend/worker/RS 镜像对应的 Dockerfile 和 `vnext/` 构建上下文覆盖；特别确认 RS 的 `vnext/` context 含 repository_client、repository_contracts 和 Dockerfile 使用目录，backend 包括 Compose 旅程的全部镜像输入。
3. 复核 `test_input_closure.py` 的 Git tree/content 摘要、路径依赖传递、dirty worktree 拒绝、manifest compare 组件差异，以及敏感环境值只记摘要。
4. 复核 run-tests.sh 未设置 GATEWAY_TEST_PACKAGES 时仍运行全部五包；未知/重复输入 exit 2；包顺序、backend/RS 两遍拆分、BASE TEMP 下 Compose 文件处理与五锁检查没有回归。
5. 核对来源 V 必须是该包实际运行并通过、起止 clean/HEAD 可核、整次 runner exit 0；核对 V 自比较、S3 到 V 比较及 shared_kernel 指定包实跑演示。
6. 复核 V 的完整权威 runner 日志、clean/start/end/exit、每包 manifest 与计数差异；确认新增 23 个 RS unit 项逐项解释，没有缩小测试。
7. 在同一 worktree 验证 V→H package manifest 逐项相等；复核 H 上 repository-service labels/identity 以及 backend/worker 使用 provenance project 连续构建两次得到的 image IDs；两次 build 之间没有测试。评估 backend 沿用 Compose 结果的闭包依据与 AGENTS.md 镜像身份等价规则一致。
8. 复核五包 ruff/mypy、import_rules 0/0/6、路径预算、真实数据范围为空、G12 状态和无 S4 改动。

验证：在 detached worktree 自行检查差异、unit/静态证据与外部日志；不要求重跑完整 runner。若需运行依赖 Dolt/Compose 的证据，先按 AGENTS.md preflight 严格整机单飞并记日志；不要手工 docker rmi/tag/delete 两个 client e2e 镜像。
交付：按执行计划 §8.8 写独立审核报告并提交到 p5-g12 分支；不合并/rebase main、不推送。审核通过时由审核方按授权在通过报告提交上打附注 tag `p5-g12-exit`，作为 S4 的区间起点；定向修订或返工时不打 tag。
审核允许结论：通过 / 定向修订 / 整体返工。
```

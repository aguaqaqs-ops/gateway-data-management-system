# P5 架构收口治理修订 G12 第 1 项 handoff

## 1. 候选与范围

- 范围起点 `range_start`：`p5-s3-exit`，`6b2b5fd0e1a82ae036b8ad19d233f3d68559465b`。
- kickoff base：`46c5684c98`（本地分支 `p5-g12`，worktree `/home/dev/gdds-p5-g12`）。
- 实施 HEAD 与门禁提交 `V`：`8d42d61f7b8fe6c7fabe3a3e7e6cc9eea18fea7e`。
- 候选 `H`：只增加本 handoff 的提交；V 上的全量权威 runner、manifest 与 Compose provenance 已记录在下文。准确 H SHA 由审核提示词和最终交付记录填写。
- 本项只实施治理修订计划 G12 第 1 项。没有改生产代码、Compose、Dockerfile、harness、依赖或锁文件；没有运行真实数据；没有开始 S4。
- `legacy/` 通过 `/home/dev/gateway-data-management-system/legacy` 符号链接接入，不属于 Git。

## 2. 实施提交

| 提交 | 内容 |
|---|---|
| `3741778f76` | 新增逐包闭包摘要脚本，增加 runner 的包选择与 manifest 输出，并补充对应测试和规则文档。 |
| `b78f3f65a6` | 将 Git 组件对象类型写入 manifest，并纳入总摘要与逐项比较。 |
| `0a740ec7de` | 以 `uv python find` 解析包解释器，不触发依赖同步。 |
| `bb6bea1516` | 显式纳入 `rust-toolchain.toml`。 |
| `6299b0d85e` | 根据审计发现纳入 RS 测试读取的运行时 provider feasibility 权威文档。 |
| `8d42d61f7b` | 为 runner 测试 fixture 补入上述权威文档，修复 V1 上两项 fixture 错误。 |

相对 kickoff base 的改动均在 G12 许可路径中：`AGENTS.md`、testing conventions、执行计划 §8.9、G12 治理状态、runner、闭包脚本及其 unit 测试。没有路径预算偏差。G12 状态在此分支标记为“已实施，待独立审核”；main 上状态由审核方合入时更新。

## 3. 闭包定义

`vnext/scripts/test_input_closure.py` 仅依赖 Python 标准库，由 runner 使用 `python3 -I` 调用。每个组件列出名称、路径、类型、理由和摘要；Git 组件以指定提交中该路径的 Git blob/tree 对象 ID 标识，非 Git `legacy/` 以排序后的相对路径和文件内容计算 SHA-256（符号链接同时记录 link target 和目标文件内容）。包总摘要是规范 JSON 的 SHA-256。manifest 记录提交 HEAD 与 clean-worktree 状态。

摘要和比较都拒绝 dirty worktree；比较还核对当前 manifest 的 HEAD 与 clean worktree 的 HEAD。未提交或未跟踪的非忽略变更不能被误判为已提交闭包。比较按组件名称、种类、对象类型、路径和摘要逐项对照，输出 `可沿用` 或 `运行` 以及变化项。

每包公共闭包包括：

- 本包完整 Git tree（源代码、测试、`pyproject.toml`、锁文件、Python 选择器）；
- `vnext/fixtures`、`vnext/scripts`、`vnext/deploy`、`vnext/repository-workspace.toml` 和 `vnext/rust/rust-toolchain.toml`；
- 五个包的 `uv.lock`。`uv-consume.sh` 对每个消费命令前后检查全部五锁；
- `legacy/` 的内容摘要；包实际解释器 `-VV`、Dolt、uv、rustc 版本。

包间路径依赖按显式图传递展开：`repository_client` 和 `repository_service` 纳入 `repository_contracts`；`backend` 纳入 `shared_kernel`、`repository_contracts`、`repository_client` 及 Rust Python crate 的传递依赖。

| 包 | 包专有组成部分与纳入理由 |
|---|---|
| `shared_kernel` | 自身完整包 tree；公共闭包。 |
| `repository_contracts` | 自身完整包 tree；公共闭包。 |
| `repository_client` | 自身完整包 tree；`repository_contracts` 完整 tree；公共闭包。 |
| `backend` | 自身完整包 tree；Python 路径依赖及其传递依赖；`vnext/rust` workspace 完整 tree，覆盖 `Cargo.toml`、`Cargo.lock` 和所有 crate 源码，Git tree 不含 `target/`；Compose、backend Dockerfile、repository-service Dockerfile 和完整 `vnext/` Docker build context。完整 context 包含 backend、worker、RS 镜像构建使用的所有源目录。另记录 Docker client/server/Compose 版本及 Python、Rust base image IDs。 |
| `repository_service` | 自身完整包 tree；`repository_contracts` 路径依赖；`p2-r1-runtime-provider-feasibility.md`（测试读取的权威方法文档）；Compose、repository-service Dockerfile、`repository_client/tests/Dockerfile`、`Dockerfile.dependency-base` 和完整 `vnext/` Docker build context。该 context 包含 client、contracts、fixtures 及两个 client 镜像 Dockerfile 使用的其他目录。另记录 Docker client/server/Compose 版本及 Python base image ID。 |

Docker 输入覆盖的实测与来源：RS 的 `compose_lifecycle_harness.py` 以 `vnext/` 为 client e2e 和 dependency-base 镜像的构建上下文；backend 的 Compose 旅程构建 backend、worker 和 repository-service 镜像。对应 Dockerfile、Compose 文件及完整 context 均独立列入包闭包；manifest 另记录 Docker 工具版本与外部 base image ID。Docker daemon 的 context 读取不经过 Python audit hook；镜像构建文件和上下文由 Git tree 摘要覆盖，完整 Compose 旅程在 V 上通过。

非 Python 读取方：

- shell runner 与 `uv-consume.sh` 读取的脚本由 `vnext/scripts` 覆盖；workspace 配置和五锁快照单独列入。
- Dolt 进程读到的测试数据、fixtures、包代码和 legacy 参考由包 tree、公共 fixtures、legacy 内容摘要覆盖；各包 manifest 都记录 Dolt 版本。`strace -f -e trace=openat` 的读取路径集合已与相应闭包比较。
- Rust/maturin 编译读取的 workspace 文件由完整 `vnext/rust` tree、Cargo.lock 与 rust-toolchain selector 覆盖；生成的 `target/` 不作为输入。
- Docker daemon 读取的 build context 由 backend/RS 的完整 `vnext/` tree、Dockerfile 与 Compose 组件覆盖；base image IDs 记录在 manifest 环境组件。

V 的五个 manifest 总摘要：

| 包 | `total_digest` |
|---|---|
| `shared_kernel` | `3296c0aa8893ed6ad6f80709bdc4b0a69e7d4ea2312416cb786acb59b393c147` |
| `repository_contracts` | `9f35a5b997f06262fae9be0c7b9f87cc0f03ec0561229da41252f00ac0e874ae` |
| `repository_client` | `1d4bcd2bd9cde9e6761b6852f31e6cf271e89859de5c34b62132473af95ce238` |
| `backend` | `577168fa1cb77367469da022ebe54078bf027f27508f01bbc8641f338482d9ed` |
| `repository_service` | `c4c84a57366c0ffcbeaa43ad8384b473af9f2db0b43a2a637338bb3f1e526072` |

Manifest JSON 由 V 的 runner 输出提取并保存在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-v2-manifests/`；完整原始输出见 `g12-v2-authoritative-runner-20261018.log`。

## 4. Debug 审计与实测闭包

按 DC30，以下路径审计属于调试，不是门禁证据。Python audit hook 位于 worktree 外的 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit/sitecustomize.py`；RS 的低开销 buffered hook 源文件为同目录 `sitecustomize-buffered.py`，运行时以 Python 自动导入的 `sitecustomize.py` 名称放在 `g12-audit/buffered-hook/`。审计目录通过外部 `PYTHONPATH` 注入，以覆盖 xdist worker 和 Python 子进程。backend 与 RS Compose package run 都完整执行。

`shared_kernel`、`repository_contracts`、`repository_client`、`backend` 的审计测试运行于 `bb6bea1516c38380bb4bb20cb118df6d60e60e59`。RS 初次审计发现测试读取 `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md`，因此在 `6299b0d85e` 将它加入 RS 闭包。之后在最终 V 上以独立 buffered hook 目录重新完整审计 RS，hook 文件经 import probe 确认为 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit/buffered-hook/sitecustomize.py`；该次 manifest 与最终 V 一致。V2 额外修正的 fixture 只在临时 Git fixture 中写入上述权威文档；完整 V2 runner 已通过。

| 包 | Python open 事件 / 唯一路径 | `strace` 唯一仓库读取路径 | Python / `strace` 闭包外路径 |
|---|---:|---:|---:|
| `shared_kernel` | 332 / 292 | 6,522 | 0 / 0 |
| `repository_contracts` | 232 / 195 | 6,422 | 0 / 0 |
| `repository_client` | 1,162 / 551 | 6,741 | 0 / 0 |
| `backend` | 127,730 / 10,383 | 10,453 | 0 / 0 |
| `repository_service` | 47,980 / 9,536 | 7,507 | 0 / 0 |

五包各自实测的闭包外路径数均为 0；strace 相对路径未解析数均为 0。`.git`、`.gitignore` 和测试创建的临时 Git metadata 是 clean-tree/provenance 控制输入，由审计汇总单独记录，不作为测试内容路径计数。

原始日志及汇总（均在 worktree 外）：

- `shared_kernel`：`g12-debug-shared_kernel-20261018T162740Z-python-opens.jsonl`、`...-openat.strace`、`...log`。
- `repository_contracts`：`g12-debug-repository_contracts-20261018T162852Z-python-opens.jsonl`、`...-openat.strace`、`...log`。
- `repository_client`：`g12-debug-repository_client-20261018T162902Z-python-opens.jsonl`、`...-openat.strace`、`...log`。
- `backend`：`g12-debug-backend-20261018T163016Z-python-opens.jsonl`、`...-openat.strace`、`...log`。
- `repository_service`：成功的 buffered audit 为 `g12-debug-repository_service-buffered-correct-20261018T191053Z-python-opens.jsonl` 和 `...log`；hook import probe 记录在 `g12-audit/buffered-hook-load-check.txt`。strace 路径集来自 `g12-debug-repository_service-20261018T170128Z-openat.strace`。最初的 RS 同步 hook + strace 运行因观察开销导致并行批次超时失败；随后正确 buffered hook 的完整 RS runner 以 exit 0 完成。失败调试日志保留，未用作门禁证据。
- 最终 V 闭包与这些读取集合的逐包结果：`g12-v2-audit-summary-<package>.json`；hook 与汇总脚本原样保存在 `g12-audit/`。

## 5. Runner 改动与测试

`GATEWAY_TEST_PACKAGES` 未设置时仍按固定顺序运行五包，并保留 backend 与 RS 各自的并行/serial 两遍拆分。设置后按逗号分隔名选择包，仍按权威固定顺序运行；未知名、重复名或格式错误 exit 2。指定包的 manifest 在任何包测试开始前写入 runner 输出；结束时逐包输出 passed/failed。锁文件快照、runner 两次锁检查、`GATEWAY_TEST_BASETEMP` 下 Compose 测试临时目录处理和既有 pytest 参数保持原行为。

- `test_test_input_closure.py` 覆盖闭包组成、传递路径依赖、逐项比较与 dirty worktree 拒绝；同构环境用例使用参数表。
- `test_run_tests_script.py` 覆盖指定包与权威顺序、未设置选择时的全包及两遍拆分、未知/重复/格式错误退出码；多种无效选择收敛为参数表。
- 首个候选门禁 V1（`6299b0d85e`）暴露 runner 测试临时 Git 仓库缺少新闭包权威文档，相关两个用例失败；`8d42d61f7b` 补入 fixture 后，在 V2 重跑完整权威 runner 并通过。V1 日志 `g12-v-authoritative-runner-20261018.log` 仅作修复记录。

## 6. V 门禁与计数对照

取证 preflight：`g12-v2-preflight-20261018.log`。开始与结束 HEAD 均为 V；load average 为 `3.72, 5.54, 5.17`；Dolt 进程 0、Compose project 0、8000 端口空闲；全部容器已记录（当时只有两项 BuildKit 容器）。

V 的权威命令：`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`，未设置 `GATEWAY_TEST_PACKAGES`。开始/结束 HEAD 均为 V，worktree clean，runner exit 0。外部证据：`g12-v2-authoritative-runner-envelope-20261018.log` 与 `g12-v2-authoritative-runner-20261018.log`。runner 开始位置逐包输出 manifest，结束逐包状态均为 passed。

| 包 | S3 V `dc9c08a410` 基准 | G12 V2 结果 | 差异 |
|---|---:|---:|---|
| `shared_kernel` | 242 passed | 242 passed | 0 |
| `repository_contracts` | 152 passed | 152 passed | 0 |
| `repository_client` | 154 passed | 154 passed | 0 |
| `backend` | 2,839 parallel + 36 serial passed | 2,839 parallel + 36 serial passed | 0 |
| `repository_service` | 1,684 parallel passed + 1 skipped；205 serial passed | 1,696 parallel passed + 1 skipped；205 serial passed | +12 passed |

RS 的 12 项净增是本项新增的 5 个 closure unit cases 与 runner 包选择测试新增的 7 个用例（2 个选择顺序、1 个默认全包、4 个无效选择参数）。未减少任何测试或断言。

Compose provenance 来自本次 V runner 的真实 Compose 旅程，副本位于 `g12-v2-compose-provenance.json`：项目 `ordered-bisect-b-550745-baseline`；backend image ID `sha256:827d04ec17e3dc7ec93e2f8e9c10decdd3158a304dd84395f3067eb56d5b06ca`；worker `sha256:ec784a6ef2c79fe07d218ef9ef5118bbc262983c1dc5aa11a4ee9ed4888813b6`；repository-service `sha256:bedfe5bdd95955e4dc82525cba75c10788421ec40d6ec4cc6d41e97a2d693ea1`。RS 标签记录 build-input revision `8d42d61f7b8fe6c7fabe3a3e7e6cc9eea18fea7e` 与 source-tree SHA-256 `sha256:fbef57ab58c8e390a0a57d7660a488cd3a9082c52c942cfd41c4179b4df748b1`。

## 7. 三项规则演示

1. V manifest 与 V 自身逐包比较：五包均 `可沿用`，变化组件为空。
2. 对 `dc9c08a410829f303aae1e0f826c674b335cb94b` 计算来源 manifest 后与 V 比较：五包均 `运行`。共同变化是 `shared:scripts`；backend 与 RS 还包含 Docker context 变化，RS 另有包 tree 变化。
3. 在 V clean worktree 上运行 `GATEWAY_TEST_PACKAGES=shared_kernel GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`：exit 0，只执行 `shared_kernel`，242 passed；启动日志只有该包 manifest，结束日志只有该包 passed 状态。preflight 和运行 envelope 见 `g12-v2-demo-preflight-20261018.log`、`g12-v2-demo-shared-kernel-envelope-20261018.log`、`g12-v2-demo-shared-kernel-only-20261018.log`。

比较输出为 `g12-v2-manifest-comparisons.log`。V 的五个 manifest JSON 位于 `g12-v2-manifests/`。历史比较的变化项逐包列出，没有把 `shared:scripts` 变化当成唯一变化。

## 8. V → H `carried`

判定规则分别适用：逐包沿用决定当前版本哪些 package tests 必须运行；镜像身份等价决定 V..H 的容器旅程能否 carried。backend 的包闭包覆盖完整 Compose build context、Compose 与 Dockerfile、Rust workspace 和 base image IDs，因此 backend 包从合格来源 V 沿用时，其 Compose 结果一并沿用。

H 只增加本 handoff 文档，`vnext/`、Docker/Compose 输入及五包 manifest 闭包不变。H 上的 carried 在 V 门禁的同一 worktree 中判定，并在最终 H 上复核。日志写到 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-v2-carried-final-H.log`：

- RS：在 H 上运行 `python3 -I vnext/repository_service/tests/support/build_context_digest.py identity`。`gateway-repository-service:local` 的 build-input revision 标签为 `8d42d61f7b8fe6c7fabe3a3e7e6cc9eea18fea7e`，source-tree SHA-256 标签为 `sha256:fbef57ab58c8e390a0a57d7660a488cd3a9082c52c942cfd41c4179b4df748b1`，均与 H 重新计算值相等。
- backend/worker：使用 V provenance 中的 Compose project `ordered-bisect-b-550745-baseline`，连续两次运行 `docker compose --project-name ordered-bisect-b-550745-baseline -f /home/dev/gdds-p5-g12/vnext/deploy/compose.yaml build backend worker`；两次之间未运行测试。两次构建所得 backend ID 均为 `sha256:827d04ec17e3dc7ec93e2f8e9c10decdd3158a304dd84395f3067eb56d5b06ca`，worker ID 均为 `sha256:ec784a6ef2c79fe07d218ef9ef5118bbc262983c1dc5aa11a4ee9ed4888813b6`，都与 V provenance 中实际运行的 ID 一致。
- 判定日志记录 H、worktree clean 状态、RS labels、Compose project、两次命令与每次镜像 ID。此项不手工执行 `docker rmi`、`docker tag` 或删除 `gateway-repository-client-e2e:local`、`gateway-repository-client-e2e-base:local`。

## 9. 静态检查与真实数据

V clean worktree 上五个 Python 包均通过 `ruff check .` 和 `mypy`；`import_rules` 为 0 违例 / 0 runtime cycles / 6 unreachable。完整命令、每个退出码和 HEAD 见外部日志 `g12-v2-static-checks-20261018.log`。

真实数据范围为空；本项未运行或读取真实数据。G12 第 1 项只变更测试 runner、闭包摘要、测试与治理文档。

## 10. 停止条件

未触发停止条件：不需要改生产代码、Compose、Dockerfile、harness、依赖或锁；最终实测路径均被闭包覆盖；逐包沿用与容器门禁规则由 backend 闭包与镜像身份等价分别覆盖；最终 V 全量权威 runner exit 0；没有缩小测试范围或削弱断言。

V1 fixture 缺项已在授权范围内修复；最终 V2 的完整门禁通过。V2 是本项门禁提交，不把任何调试运行作为门禁证据。

## 11. 审核提示词

```text
任务：独立审核 P5 架构收口治理修订计划 G12 第 1 项（按包沿用测试结果）。
按 docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：分支 p5-g12 @ <候选 H SHA>（门禁提交 V = 8d42d61f7b8fe6c7fabe3a3e7e6cc9eea18fea7e，实施 HEAD 同 V），
区间 p5-s3-exit (6b2b5fd0e1a82ae036b8ad19d233f3d68559465b)..<候选 H SHA>。只审该区间差异。
在只读 detached worktree 中工作：git worktree add --detach /home/dev/gdds-p5-g12-review <候选 H SHA>；
建立 legacy 符号链接；不改实现文件、不推送、不合并或 rebase main。

权威依据：G12 治理修订计划第 1 项、决议记录 §16 DC33 第一部分、执行计划 §8.2/§8.7/§8.9、
AGENTS.md、docs/backend-vnext/testing-conventions.md；handoff 为
docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-g12-handoff.md。

必须核查：
1. Python audit hook 与 strace 的实测读取路径是否被对应包闭包覆盖，尤其是 RS 新纳入的 authority document；确认没有用漏项换取可沿用。
2. 各包 Docker 构建 context、Dockerfile、Compose 文件与环境镜像身份是否覆盖完整；backend Compose 结果沿用的理由是否由 backend 闭包支持。
3. 摘要与比较是否拒绝 dirty worktree；Git tree、legacy 内容摘要、版本环境和逐组件比较是否按合同工作。
4. 未设置 GATEWAY_TEST_PACKAGES 时五包全跑、顺序与两遍拆分不变；指定包、未知名和重复名行为正确，GATEWAY_TEST_BASETEMP 与锁文件检查仍保持原处理。
5. V 权威 runner clean worktree、起止 HEAD、runner exit 0、逐包计数、manifest 与 Compose provenance；V→H carried 是否在同一 worktree 经 RS identity 和 backend/worker 两次构建验证。
6. 路径预算、S3 计数增量说明、静态检查、停止条件状态，以及本项没有开始 S4。

验证：审核 V 的门禁日志与外部 audit 汇总；按 AGENTS.md 规则复核 V→H 的 carried。不得在主工作区写入或并行运行测试。
审核结论通过后，按阶段流程记录 review report，并由 owner/授权审核方创建 p5-g12-exit；在审核通过前不开始 S4。
```

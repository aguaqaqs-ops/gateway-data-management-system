# P5 架构收口治理修订 G12 第 1 项 handoff

## 1. 候选、范围与状态

- `range_start`：tag `p5-s3-exit`，提交 `6b2b5fd0e1a82ae036b8ad19d233f3d68559465b`。
- kickoff base：`46c5684c98`；分支 `p5-g12`，worktree `/home/dev/gdds-p5-g12`；已建立指向 `/home/dev/gateway-data-management-system/legacy` 的 `legacy` 符号链接。
- 门禁提交 `V`：`ba486393137f8fe6d93464d05cce00a1a87aec98`。全量门禁在该 clean HEAD 上完成。
- 候选 `H`：V 之后仅提交本 handoff；H 的 SHA 由最终审核请求和 `p5-g12-exit` tag 标识。本 handoff 只包含非构建输入文档，因此逐包 manifest 与 V 相同。
- 实施范围仅为 G12 第 1 项：按包闭包比较后沿用测试结果。未改生产代码、Compose、Dockerfile、harness、依赖或锁文件；未合并/rebase main，未推送，未运行真实数据，未开始 S4。
- G12 治理计划在本分支标为“已实施，待独立审核”；main 上的状态由审核方合入时更新。

## 2. 实施提交与复核修正

| 提交 | 内容 |
|---|---|
| `3741778f76` | 新增标准库闭包摘要脚本、runner 包选择和相应测试/规则文档。 |
| `b78f3f65a6` | manifest 区分 Git blob/tree 类型，并纳入总摘要与逐组件比较。 |
| `0a740ec7de` | 使用 `uv python find` 解析包解释器，避免摘要前触发环境同步。 |
| `bb6bea1516` | 将 `rust-toolchain.toml` 纳入闭包。 |
| `6299b0d85e` | 按审计发现，把 RS 测试读取的 provider feasibility 权威文档纳入 RS 闭包。 |
| `8d42d61f7b` | 修复 runner 测试临时 Git fixture 缺少该权威文档的问题。 |
| `90fc9c5bb6` | 初版 handoff；初次独立审核指出包 `.venv` 内容摘要与 Python Unicode 数据版本未覆盖。该版数据已由本 handoff 替换。 |
| `73c98c8bb2` | 将每个包实际 `.venv` 的内容和可执行权限纳入摘要，排除派生 bytecode/cache。 |
| `ba48639313` | 增加 `unicodedata.unidata_version`，闭合 Python Unicode 数据版本输入。 |
| H | V 后唯一提交；仅更新本 handoff 为最终证据。 |

上述实施改动均位于授权路径预算内。V1/V2 修复、审计与门禁关系见本 handoff 后文；最终结论只使用 V 的权威门禁与最终闭包审计，不把调试运行作为门禁证据。

## 3. 闭包定义

`vnext/scripts/test_input_closure.py` 只使用 Python 标准库，由 runner 以 `python3 -I` 调用。每包 manifest 列出组件名、路径、类型、纳入理由和摘要，再计算 `total_digest`。Git 组件以候选 HEAD 中对应 blob/tree 对象及类型为摘要来源；非 Git 的 `legacy/` 和包 `.venv` 以内容摘要为来源。`.venv` 摘要包括文件内容和可执行权限，排除 `__pycache__` 与 `.pyc/.pyo`；Python `-VV` 和 Unicode 数据版本独立记录。dirty worktree 会失败，未提交改动不会被 tree hash 冒充为来源输入。

比较按包和组件名称、kind、对象类型、路径、digest 逐项比较；闭包完全相等输出“可沿用”，任一组件变化输出“运行”及变化组件。来源 manifest 必须来自 clean worktree 上实际运行并通过的权威 runner；该次 runner 整体 exit 0 且日志记录起止 HEAD。链式沿用直接引用最初实际运行的来源 V。当前 V 上所有闭包变化的包必须实际运行并通过。S5 最终门禁与发布门禁仍运行全部包。

所有包的公共组件为：

- `vnext/<package>` 完整 Git tree（包源码、测试、配置、lockfile、Python selector）；
- `vnext/deploy`、`vnext/fixtures`、`vnext/scripts`、`vnext/repository-workspace.toml`；
- 五个包的全部 `uv.lock`（`uv-consume.sh` 每次消费前后检查五锁）；
- `vnext/rust/rust-toolchain.toml`；
- 非 Git `legacy/` 内容摘要（排序后的相对路径与文件内容；符号链接目标一并计入）；
- 本包实际 `.venv` 的内容摘要；Python `-VV`、Python Unicode 数据版本、Dolt、uv 和 rustc 版本。

V 上记录到的环境版本为 Python 3.14.6、Unicode database 16.0.0、Dolt 2.1.11、uv 0.12.5、rustc 1.97.0。Docker build 相关包另记录 Docker client/server、Compose 和 base image IDs。

| 包 | 额外路径及理由 |
|---|---|
| `shared_kernel` | 自身完整 package tree；公共组件。 |
| `repository_contracts` | 自身完整 package tree；公共组件。 |
| `repository_client` | 自身完整 package tree 和 `vnext/repository_contracts` 完整 tree；公共组件。 |
| `backend` | 自身完整 package tree；Python 传递依赖 `shared_kernel`、`repository_contracts`、`repository_client`；Rust workspace 中 `gateway-compute-python`、`gateway-compute-python-impl`、`gateway-compute-core`、`gateway-shared-kernel` 及整个 `vnext/rust` tree。完整 Rust tree 覆盖 crate 清单/源码、workspace `Cargo.toml`、`Cargo.lock`；单独记录 toolchain selector；`target/` 是派生产物且不在 Git tree。另纳入 Compose 文件、backend 与 repository-service Dockerfile 和完整 `vnext/` 构建上下文。 |
| `repository_service` | 自身完整 package tree、`vnext/repository_contracts` 完整 tree，以及测试读取的 `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md`。另纳入 Compose 文件、repository-service Dockerfile、client e2e 与 dependency-base Dockerfile 和完整 `vnext/` 构建上下文。 |

Docker 输入映射与覆盖：

- backend Compose 测试会构建 backend、worker 与 repository-service。backend 和 worker 共用 `vnext/backend/Dockerfile`，三个服务都以 `vnext/` 为 context；对应 Compose 文件、Dockerfile、完整 context 均在 backend 闭包。完整 `vnext/rust` tree 与 `.venv` 摘要覆盖 Rust 源码和已安装 native extension；Rust、Python base image IDs 以及 Docker 工具版本都记录在 backend manifest。
- RS Compose 测试构建 repository-service；`compose_lifecycle_harness.py` 还以 `vnext/` 为 context 构建 `gateway-repository-client-e2e:local` 与 `gateway-repository-client-e2e-base:local`，分别由 `vnext/repository_client/tests/Dockerfile` 和 `Dockerfile.dependency-base` 构建。RS manifest 对应包含完整 `vnext/` tree、Compose、三个 Dockerfile、Python base image ID 和 Docker 工具版本。context 因此覆盖 client、contracts 和两个 Dockerfile 使用的其他目录。
- `vnext/.dockerignore` 属于完整 `vnext/` Git tree。以整个 tracked context 作为组件是对 Docker 实际过滤后输入的保守超集；没有依据缩小该闭包。

非 Python 读取方与覆盖方式：

- Docker daemon 读取 Dockerfile 和 build context；上表的 context、Dockerfile、Compose 及 base image/tool identity 覆盖其输入。
- Dolt 由 backend/RS 的真实集成测试启动；被测代码、测试和 fixtures 在 package/shared tree 中，表规则测试使用的参考数据在 `legacy/` 内容摘要中，Dolt 版本也记录在 manifest。测试运行期创建的临时仓库/数据库是测试输出状态，不是来源 V 的可复用输入；本项没有读取真实数据。
- Rust/maturin 读取 workspace crate、`Cargo.lock` 和 `rust-toolchain.toml`；闭包包含整个 Rust workspace 和 toolchain selector。编译输出 `target/` 排除，已装入测试 `.venv` 的扩展二进制纳入 `.venv` 内容摘要。
- shell runner、uv wrapper 与 image build 脚本由所有包共同纳入的 `vnext/scripts` 覆盖；uv workspace 配置和五锁快照单独列出。

## 4. Python 读取审计

按 DC30，audit hook 测试只用于调试取证，不是门禁。外部 audit hook 位于 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v3/hook/sitecustomize.py`，通过 worktree 外的 `PYTHONPATH` 注入，覆盖 xdist worker 和 Python 子进程；原始 hook、wrapper、路径快照和 JSONL 全部保存在日志目录，不进入提交。RS 的 v6 hook 同时解析 `os.open` descriptor 路径；RS v6 的汇总脚本为 `g12-audit-v3/summarize-v6.py`。

统计为每包完整测试执行期间唯一的、位于 worktree 内的普通文件读取路径。表中的“闭包输入”是 manifest 覆盖路径；bytecode 和工具 cache 是分别由闭包源文件/解释器派生的读取；生成路径和闭包外读取均为 0。

| 包 | 唯一读取文件 | manifest 覆盖 | 派生 bytecode | 派生 cache | 闭包外 |
|---|---:|---:|---:|---:|---:|
| `shared_kernel` | 278 | 226 | 34 | 18 | 0 |
| `repository_contracts` | 180 | 164 | 15 | 1 | 0 |
| `repository_client` | 421 | 385 | 35 | 1 | 0 |
| `backend` | 2,146 | 1,252 | 585 | 309 | 0 |
| `repository_service` | 1,271 | 1,065 | 204 | 2 | 0 |

各包 generated-read count 均为 0。RS v6 的 `mode=None` audit 行均为 stat 时不存在的 open 尝试，不计作文件读取；成功的 `os.open` descriptor 路径由 hook 单独记录，未解析的实际读取数为 0。backend v6、client v6 同样未解析实际 descriptor 读取。cache 文件（包括测试工具/Hypothesis cache）属于派生运行状态，不参与 pytest 的默认测试选择；记录 Python/Unicode 版本、源码和锁文件后无需把 cache 当作独立输入。

审计运行和摘要（均在 worktree 外）：

- `shared_kernel`：`g12-debug-shared_kernel-v3-20261018T194055Z.log`、对应 `-python-opens.jsonl`；汇总 `g12-audit-v3/shared_kernel-20261018T194055Z-summary.json`。
- `repository_contracts`：`g12-debug-repository_contracts-v3-20261018T194121Z.log`、对应 `-python-opens.jsonl`；汇总 `g12-audit-v3/repository_contracts-20261018T194121Z-summary.json`。
- `repository_client`：v6 runner/open logs `g12-debug-repository_client-v6-20261018T211245Z.log` 与 `...-python-opens.jsonl`；汇总 `g12-audit-v3/repository_client-20261018T211245Z-v6-summary.json`。
- `backend`（含 Compose 旅程）：v6 runner/open logs `g12-debug-backend-v6-20261018T204347Z.log` 与 `...-python-opens.jsonl`；汇总 `g12-audit-v3/backend-20261018T204347Z-v6-summary.json`。
- `repository_service`（含 Compose 旅程）：v6 runner/open logs `g12-debug-repository_service-v6-20261018T203637Z.log` 与 `...-python-opens.jsonl`；路径快照及汇总分别为 `g12-audit-v3/repository_service-20261018T203637Z-v6-before.json` 和 `...-v6-summary-corrected.json`。

审计 summary 中的 HEAD 与 `total_digest` 均匹配 V runner manifest。每包 full test run 的 exit code 均为 0。非 Python 读取路径的覆盖边界见上一节：Docker/Rust 的完整构建输入树被哈希，Dolt 输入由测试代码/fixtures 和 legacy 内容覆盖；未将未经观察的文件路径当作可沿用依据。

## 5. Runner 改动与测试

`GATEWAY_TEST_PACKAGES` 接受逗号分隔包名；未设置时按原固定顺序运行五包。指定包仍按原顺序子集运行；未知包、重复包和非法空项 exit 2。包环境同步后、测试前，为本次要运行的每包输出 JSON manifest；结束时逐包输出状态。backend/RS 两遍拆分、worker 分组、`GATEWAY_TEST_BASETEMP` 下 Compose 测试文件处理及五锁前后检查保持原逻辑；未设置包选择的 runner unit test 覆盖完整顺序和两遍拆分。

- `vnext/repository_service/tests/test_test_input_closure.py` 覆盖组件组成、transitive path dependencies、逐项比较、dirty worktree CLI 拒绝和 `.venv` digest 行为；同构输入经参数表共享。
- `vnext/repository_service/tests/test_run_tests_script.py` 覆盖指定包、选择顺序、unset 时默认全包、两遍拆分、未知/重复/非法输入 exit 2；同构无效输入使用参数表。
- 最终 V 的 RS 总数相较 S3 增加 13 项：闭包摘要 6 项，runner 选择 7 项；没有减少测试或削弱断言。

## 6. V 的 preflight 与权威门禁

最终取证前 preflight 在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-final-preflight-20261018.log`。开始/结束 HEAD 均为 V，worktree clean；load average `0.44, 0.91, 1.33`，整机 Dolt 进程 0、Compose 项目 0、8000 端口占用 0；记录了全部容器，当时仅有两个 BuildKit 容器。

V 上只运行一次完整权威 runner，命令为：

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

`GATEWAY_TEST_PACKAGES` 与 `GATEWAY_TEST_BASETEMP` 均未设置。外部日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-v-authoritative-runner-20261018.log` 记录开始/结束 UTC、起止 HEAD、clean status、每包 JSON manifest、逐包状态与 runner 自身 exit code。开始/结束 HEAD 都是 `ba486393137f8fe6d93464d05cce00a1a87aec98`，runner exit 0，结束 worktree clean。

| 包 | S3 V `dc9c08a410` 基准 | G12 V 结果 | 差异 |
|---|---:|---:|---:|
| `shared_kernel` | 242 passed | 242 passed | 0 |
| `repository_contracts` | 152 passed | 152 passed | 0 |
| `repository_client` | 154 passed | 154 passed | 0 |
| `backend` | 2,839 parallel + 36 serial passed | 2,839 parallel + 36 serial passed | 0 |
| `repository_service` | 1,684 parallel passed + 1 skipped；205 serial passed | 1,697 parallel passed + 1 skipped；205 serial passed | +13 passed |

RS +13 全部来自本项新增的 6 个闭包测试与 7 个 runner 包选择测试。其他包计数完全一致。V manifest `total_digest`：

| 包 | `total_digest` |
|---|---|
| `shared_kernel` | `91b18eea6087a14f530f451ca8cc38858f0164b8889289b36bf7c3ee52f42138` |
| `repository_contracts` | `4e180843559e99ffc2e227b79e78c7437b91a68442fe0da0c0ac544eacd00882` |
| `repository_client` | `758cb11ad8b3a7c72a3ad6019cbfa076ce5898d488251a096f0d9d7976ed0830` |
| `backend` | `c77d4481fb2db8ad21d3700a1ee94efc51d9f5e7e0dffaa1b75b9b8a56d52c58` |
| `repository_service` | `21a4922a74b647e869a41088c791793929aac044c9bf2133f372d8767258c104` |

manifest JSON 副本在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-final-v-manifests/`，原始逐包 manifest 在上述权威 runner 日志中。

V 的 Compose provenance 副本 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-V-compose-provenance.json` 来自本次 backend/RS Compose 旅程：project `ordered-bisect-b-3141235-baseline`；backend `sha256:5172a3f6590229af3fe54a730c635cb52ea39b5e587ad600b3467e2ee9976731`；worker `sha256:e263c7b0d8d040286e4f8c33a03f24e6a1a7e64bdd2fb95e03cc47243dfb7484`；repository-service `sha256:017282612a607297c231507386637471edc6e5e5fc2247ac07c921476129611d`。RS image labels：build-input revision `ba486393137f8fe6d93464d05cce00a1a87aec98`，source tree `sha256:f650a0727b5a83f9a9be14ea5ed76c961ecc27e7230fe3c266096151ff3097d1`。

## 7. 沿用规则的三项演示

比较结果和每包 JSON 在 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-manifest-comparisons-20261018.json`、`g12-final-v-manifests/`：

1. V 的成功权威 runner manifest 与 clean V 当前 manifest 逐包比较：五包全部“可沿用”，变化组件为空。
2. 对 S3 V `dc9c08a410829f303aae1e0f826c674b335cb94b` 计算 manifest 后与 V 比较：五包全部“运行”。五包共同变化 `shared:scripts`；backend 和 RS 另有 `docker:context:vnext`；RS 另有 `package:repository_service`。这些变化没有被忽略。
3. 在 clean V 上实际运行 `GATEWAY_TEST_PACKAGES=shared_kernel GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`：仅输出/运行 `shared_kernel`，242 passed，exit 0；日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-package-selection-shared-kernel-20261018.log`。preflight、起止 HEAD 和 envelope 见相邻 `g12-demo-preflight-20261018.log` 与日志目录内 package-selection envelope。

## 8. V → H `carried`

逐包沿用与镜像身份等价分别判定：闭包比较决定当前 H 上需要运行哪些包；AGENTS.md 的镜像规则决定 V..H 容器结果是否 carried。backend 闭包包含 backend/worker/RS 的 Compose context、Dockerfile、Compose、Rust workspace、base image IDs 和工具版本，因此 backend 包从合格来源 V 沿用时，其 Compose 结果一并沿用。S5 最终门禁仍运行全部包。

为满足“提交 H 后判定”，先提交 handoff-only 候选，再在运行 V 门禁的同一 worktree 完成比较与镜像构建；随后仅把这些实测结果写入 handoff，并以最终 handoff commit 作为 H。最终 H 的 compare、identity、preflight 和两次构建在最终提交上复核。完整最终日志写到 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-carried-final.log`，最终 preflight 写到 `g12-H-carried-preflight-final.log`。

最终 H 上五包 manifest 逐项等于来源 V，全部可沿用。来源 V 是实际运行成功的 V 权威 runner，不是链式沿用来源：

| 包 | H `total_digest` | H 状态 | 来源 V | 来源日志 |
|---|---|---|---|---|
| `shared_kernel` | `91b18eea6087a14f530f451ca8cc38858f0164b8889289b36bf7c3ee52f42138` | 可沿用 | `ba486393137f8fe6d93464d05cce00a1a87aec98` | `g12-v-authoritative-runner-20261018.log` |
| `repository_contracts` | `4e180843559e99ffc2e227b79e78c7437b91a68442fe0da0c0ac544eacd00882` | 可沿用 | `ba486393137f8fe6d93464d05cce00a1a87aec98` | `g12-v-authoritative-runner-20261018.log` |
| `repository_client` | `758cb11ad8b3a7c72a3ad6019cbfa076ce5898d488251a096f0d9d7976ed0830` | 可沿用 | `ba486393137f8fe6d93464d05cce00a1a87aec98` | `g12-v-authoritative-runner-20261018.log` |
| `backend` | `c77d4481fb2db8ad21d3700a1ee94efc51d9f5e7e0dffaa1b75b9b8a56d52c58` | 可沿用 | `ba486393137f8fe6d93464d05cce00a1a87aec98` | `g12-v-authoritative-runner-20261018.log` |
| `repository_service` | `21a4922a74b647e869a41088c791793929aac044c9bf2133f372d8767258c104` | 可沿用 | `ba486393137f8fe6d93464d05cce00a1a87aec98` | `g12-v-authoritative-runner-20261018.log` |

最终 H 的逐包比较输出、manifest 与 clean/head envelope 在 `g12-H-manifest-comparisons-final.log` 和 `g12-H-manifests-final/`。五包 `changed_components` 均为空。

镜像身份结果：

- repository-service：最终 H 上 `python3 -I vnext/repository_service/tests/support/build_context_digest.py identity` 的 build-input revision 为 `ba486393137f8fe6d93464d05cce00a1a87aec98`，source-tree SHA-256 为 `sha256:f650a0727b5a83f9a9be14ea5ed76c961ecc27e7230fe3c266096151ff3097d1`；两项均与 `gateway-repository-service:local` labels 相同。identity 的 candidate SHA 是日志中记录的最终 H。
- backend/worker：在同一 worktree 使用 V provenance project `ordered-bisect-b-3141235-baseline`，连续两次执行 `docker compose --project-name ordered-bisect-b-3141235-baseline -f /home/dev/gdds-p5-g12/vnext/deploy/compose.yaml build backend worker`，两次之间没有运行测试。两次 backend ID 均为 `sha256:5172a3f6590229af3fe54a730c635cb52ea39b5e587ad600b3467e2ee9976731`；两次 worker ID 均为 `sha256:e263c7b0d8d040286e4f8c33a03f24e6a1a7e64bdd2fb95e03cc47243dfb7484`，均匹配 V provenance 实际运行 ID。
- 最终 H preflight 再次记录 clean HEAD、负载、全部容器，并确认 Dolt 进程 0、Compose 项目 0、8000 端口空闲。未手工对 `gateway-repository-client-e2e:local` 或 `gateway-repository-client-e2e-base:local` 执行 docker rmi、tag 或删除。

## 9. 静态检查、真实数据与容器记录

`import_rules` 对照：kickoff base `46c5684c98` 承接的 S3 结果为 0 import violations / 0 runtime cycles / 6 unreachable modules；V 上再次执行后仍为 0/0/6（S3 handoff §4；V 输出见当前静态检查日志）。本项没有修改 backend 架构/import 边界。

V clean worktree 上五包 `ruff check .`、`mypy` 均通过；各包 mypy 检查数为 shared_kernel 34、contracts 15、client 26、backend 476、RS 199。`import_rules` 为 0 violations / 0 runtime cycles / 6 unreachable modules。命令、每包 exit code、开始/结束 HEAD 见 `/home/dev/gdds-p5-closure-s1-gate-logs/g12-static-checks-20261018.log`。

真实数据范围为空，本项未运行或读取真实数据。镜像结果绑定于 V；V..H 只增加 handoff，闭包与 image source tree 不变，按上一节复核 `carried`。容器版本、base IDs、V image IDs 和 RS labels 已在 manifest、Compose provenance 与 carried 日志中记录。

## 10. 停止条件

均未触发：无需改生产代码、Compose、Dockerfile、harness、依赖或锁；Python 实测没有闭包外路径；Docker/Rust/Dolt/shell 输入均有闭包组成覆盖；逐包沿用与容器门禁要求由完整 build-input 闭包及独立 image-identity 判定连接；V 全量权威 runner exit 0；未缩小测试范围或削弱断言。审核通过前不开始 S4。

## 11. 审核提示词

```text
任务：独立审核 P5 架构收口治理修订计划 G12 第 1 项（按包沿用测试结果）。你未参与本项实现；按
 docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：分支 p5-g12 @ <H>（门禁提交 V = ba486393137f8fe6d93464d05cce00a1a87aec98；实现 HEAD 与 V 相同），
区间 p5-s3-exit (6b2b5fd0e1a82ae036b8ad19d233f3d68559465b)..<H>。只审该区间差异。
在只读 detached worktree 中工作：git worktree add --detach /home/dev/gdds-p5-g12-review <H>；建立 legacy 符号链接；不在主工作区写入。
权威依据：G12 治理修订计划第 1 项、决议记录 §16 DC33 第一部分、执行计划 §8.2/§8.7/§8.9、
AGENTS.md、docs/backend-vnext/testing-conventions.md 和本 handoff。

必须核查：
1. Python audit hook 实测路径、逐包闭包和计数；尤其确认 RS authority document、包 .venv 和 Python Unicode 版本都在最终 manifest；闭包外文件为 0。
2. backend/worker/RS Compose 镜像、RS client e2e/dependency-base 镜像各自的 Dockerfile、Compose 与完整 vnext/ context；backend Compose 沿用依据是否由 backend 闭包完整覆盖。
3. manifest 的 Git tree/blob 与非 Git 内容摘要、传递路径依赖、Rust workspace/Cargo.lock/toolchain、版本环境以及逐组件比较；dirty worktree 必须被拒绝。
4. 未设置 GATEWAY_TEST_PACKAGES 时 runner 是否仍运行五包、顺序和两遍拆分是否保持；指定、未知、重复包行为；GATEWAY_TEST_BASETEMP 与五锁检查是否不变。
5. V 权威 runner 的 clean worktree、起止 HEAD、exit 0、每包计数、manifest、Compose provenance；V→H carried 是否在同一 worktree 以 RS identity 和 backend/worker 连续两次构建验证。
6. 路径预算、S3 计数增量 +13 的组成、五包 ruff/mypy、import_rules 0/0/6、真实数据为空、停止条件，以及本项未开始 S4。

验证：在只读审核 worktree 复核 V 的权威 runner、audit summaries 和 H carried 日志；按审核流程复核五包静态检查。不要在审核前开始 S4；不推送、不合并或 rebase main。
交付：按执行计划 §8.8 记录独立审核报告；通过后由 owner/授权审核方在阶段审核记录上创建 p5-g12-exit。
```

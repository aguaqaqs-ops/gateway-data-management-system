# P5 架构收口治理修订 G12 第 1 项 handoff

## 1. 候选、范围与状态

- 区间起点：tag p5-s3-exit，提交 6b2b5fd0e1a82ae036b8ad19d233f3d68559465b。
- kickoff base：46c5684c98b087d2e1114f5c612ec47b08b6ad54；分支 p5-g12；worktree /home/dev/gdds-p5-g12。
- worktree 的 legacy 符号链接指向 /home/dev/gateway-data-management-system/legacy。
- 门禁提交 V：ba650d668249f593ef4f4c991cf40eade32cf6db。
- 候选 H：V 之后的 handoff-only commit；审核请求从分支当前 HEAD 读取其完整 SHA。本 handoff 位于 H。
- 本项只实施 G12 第 1 项。没有改生产代码、Compose、Dockerfile、测试 harness、依赖或锁文件；没有合并/rebase main、推送或手工操作两个 repository-client e2e 镜像；没有运行真实数据或开始 S4。
- G12 第 1 项已实施，最终独立审核待进行。审核通过前不打 p5-g12-exit，也不开始 S4。
- 本分支 V、H 的所有提交均带 trailer：Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>。G12 治理计划的实施状态已在本分支更新；main 的状态由审核方合入时更新。

## 2. 实施摘要

实施改动从 kickoff base 46c5684c98 开始，均在授权路径预算内：

| 提交 | 内容 |
| --- | --- |
| 3741778f76 | 新增标准库闭包摘要脚本、runner 包选择和相应测试/规则文档。 |
| b78f3f65a6 | Git 闭包项记录 blob/tree 类型，并纳入总摘要和逐项比较。 |
| 0a740ec7de | 使用 uv python find 解析包解释器，不在摘要前同步环境。 |
| bb6bea1516 | 将 Rust toolchain selector 纳入闭包。 |
| 6299b0d85e | 按完整性审计把 RS 测试读取的 runtime-provider-feasibility 权威文档纳入 RS 闭包。 |
| 8d42d61f7b | 为 runner 测试 fixture 补入上述权威文档。 |
| 90fc9c5bb6、d9929e96b6 | 初版 handoff；独立复核提出包 uv 环境与 Python Unicode 数据版本缺口，已在后续提交修正。 |
| 73c98c8bb2 | 摘要每包实际 uv 环境的内容和权限，排除由锁定源码与解释器派生的 bytecode。 |
| ba48639313 | 记录 Python Unicode database 版本。 |
| f1ea8348c5 | 加入每包 Hypothesis storage 和 pytest cache 内容摘要。 |
| ba650d6682 | 处理 Hypothesis Unicode gzip header 的随机临时文件名，使用解压 payload 摘要，避免同一缓存语义导致 V 自比漂移。 |

初始独立复核指出的包环境、Unicode 版本与 Hypothesis 缓存问题均已闭合。gzip 归一化得到独立定向复核：Hypothesis 读取解压后的 JSON payload；路径、权限和其余 storage 项仍计入目录摘要。

## 3. 闭包定义与组成

vnext/scripts/test_input_closure.py 只使用 Python 标准库，runner 通过 python3 -I 调用。manifest schema version 为 3。每个 JSON manifest 逐项列出组件名、路径、类型、纳入理由和摘要，再计算 total_digest。比较按组件名、kind、Git object type、路径和摘要逐项进行；全部一致输出“可沿用”，任一项不同输出“运行”及变化项。

- Git 中的文件或目录以候选提交对应的 blob/tree object id 与 object type 为摘要；未提交改动不能被 tree id 代表，dirty worktree 在 manifest/compare 时失败。
- 非 Git 的 legacy 内容按排序后的相对路径、文件内容和链接目标摘要。
- 每包实际 uv environment 记录目录结构、文件内容、权限和符号链接；排除 __pycache__、.pyc、.pyo 这类由已锁定源码和解释器派生的文件。
- 每包有效 Hypothesis storage directory（HYPOTHESIS_STORAGE_DIRECTORY，或包目录下 .hypothesis）和包内 .pytest_cache 记录路径、类型、权限和内容。Unicode JSON gzip 以解压 payload 的长度与 SHA-256 计入，忽略 header 中随机临时文件名。
- 环境项记录该包实际 Python 的 -VV、unicodedata 版本、Dolt、uv、rustc 版本。Docker 测试包另记录 Docker client/server、Compose 和 base image ids。

所有包公共 Git 组成：

- 自身 vnext/<package> tree。
- vnext/fixtures、vnext/scripts、vnext/repository-workspace.toml、vnext/deploy。
- 五个包的 uv.lock；uv-consume 在每次包命令前后检查五锁。
- vnext/rust/rust-toolchain.toml。
- legacy 内容摘要、包 uv environment、Hypothesis storage、pytest cache 和环境版本摘要。

路径依赖图按传递关系扩展：

- repository_client → repository_contracts。
- repository_service → repository_contracts。
- backend → shared_kernel、repository_contracts、repository_client、rust/gateway-compute-python → gateway-compute-python-impl → gateway-compute-core → gateway-shared-kernel。
- backend 还直接闭包 Rust workspace vnext/rust，覆盖 Cargo workspace、所有 crate 的 Cargo.toml 和源码、Cargo.lock；target/ 是派生产物，不在 Git tree，且被 Docker ignore 排除。
- RS 额外包括测试读取的 docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md。

Docker 构建矩阵与闭包：

| 测试包 | 构建镜像 | Dockerfile | 构建上下文 |
| --- | --- | --- | --- |
| shared_kernel | 无 | 无 | 不适用 |
| repository_contracts | 无 | 无 | 不适用 |
| repository_client | 无 | 无 | 不适用 |
| backend | backend、worker | vnext/backend/Dockerfile | vnext/ |
| backend | repository-service | vnext/repository_service/Dockerfile | vnext/ |
| repository_service | repository-service | vnext/repository_service/Dockerfile | vnext/ |
| repository_service | gateway-repository-client-e2e:local | vnext/repository_client/tests/Dockerfile | vnext/ |
| repository_service | gateway-repository-client-e2e-base:local | vnext/repository_client/tests/Dockerfile.dependency-base | vnext/ |

backend 的闭包另含 vnext/deploy/compose.yaml、backend 与 repository-service Dockerfile、整个 vnext/ Git tree、Rust workspace、Docker 工具和 base image ids。backend 和 worker 使用同一 backend Dockerfile。backend Compose 旅程包含这三个镜像构建输入，因此 backend 包满足沿用条件时，同一 runner 中 backend Compose 旅程一并沿用。

repository_service 的闭包含 vnext/deploy/compose.yaml、repository-service Dockerfile、client e2e 与 dependency-base Dockerfile、完整 vnext/ Git tree 和 Docker base image/tool identity。这个完整 context 覆盖 repository_client、repository_contracts、Dockerfile COPY 的其他目录及 vnext/.dockerignore。vnext/.dockerignore 会排除 .venv、Hypothesis/pytest/tool caches、Rust target、scripts、fixtures 等非构建内容；闭包仍取整个 tracked vnext tree，作为 Docker 实际过滤后输入的保守超集。

非 Python 读取方：

- Docker/BuildKit 读取 Compose、Dockerfile、.dockerignore 与 context 文件；上述完整 context、Compose、Dockerfile、Docker 版本和 base image id 覆盖这些输入。其 Compose builds 在 V 的完整 runner 中实际运行。
- Dolt 由 backend/RS 的集成与 Compose 用例启动。被测代码、测试、fixtures 和表规则参考数据分别落在 package/shared Git tree、vnext/fixtures 和 legacy 内容摘要；Dolt 版本在每包 manifest 中记录。测试期新建的临时仓库与数据库是测试产生的运行态，不是来源 V 的预先存在输入；没有读取真实数据。
- Rust 扩展读取 package uv environment 中的已安装二进制；该目录内容被摘要。源码重建输入由 backend 的完整 Rust workspace、Cargo.lock、rust-toolchain.toml、backend Dockerfile/context 覆盖。rustc 版本记录在环境组件。
- shell runner、uv wrapper、image build helper 均位于所有包共同纳入的 vnext/scripts；uv workspace 定义、五锁快照及工具版本另行纳入。
- 未使用 strace：Python 路径由 audit hook 测量；Docker/BuildKit、Dolt、Rust 与 shell 的 repository input roots 已分别由完整 context/workspace/scripts 或 package environment 覆盖，没有需要额外扩大到仓库外路径的文件输入。非 Python 输入来源和覆盖边界逐项列在上方。

V 记录的工具环境：Python 3.14.6，Unicode database 16.0.0，Dolt 2.1.11，uv 0.12.5，rustc 1.97.0。Docker client 26.1.5+dfsg1 build a72d7cd，server 26.1.5+dfsg1，Compose 2.26.1-4。Python base image id 为 sha256:41bf03017a7e6559c7899e56da8317e2e2caa17dde53ce6482b17a197904f4c2；backend 另外记录 rust:1.97.0-bookworm id sha256:7ea53b11a01d2d52b4af8fa073cd76ecbaf7dc385b88cc9d0ce8205a7c941ff1。

## 4. 完整性实测

按照 DC30，Python audit hook 和完整逐包测试仅用于实现期取证，不作为门禁。hook 经 worktree 外 PYTHONPATH 注入，以覆盖 xdist worker 与 Python 子进程。hook、逐包 runner 日志、快照、总结脚本和结果均在 worktree 外：

- Hook：/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v3/hook/sitecustomize.py
- Audit runner：/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v3/run-package-audit-v6.sh
- Summary：/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v3/summarize-v6.py
- 最终五包汇总：/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v7/
- 各包完整 runner log 和 python-opens.jsonl：下表所列 g12-debug 文件。

| 包 | 完整审计 log 时间戳 | 唯一存在的仓库内普通文件 open 路径 | manifest 覆盖 | 派生 bytecode | 闭包外 |
| --- | --- | ---: | ---: | ---: | ---: |
| shared_kernel | 20261018T232811Z | 279 | 245 | 34 | 0 |
| repository_contracts | 20261018T232816Z | 180 | 165 | 15 | 0 |
| repository_client | 20261018T232821Z | 430 | 395 | 35 | 0 |
| backend | 20261018T232828Z | 2,146 | 1,561 | 585 | 0 |
| repository_service | 20261018T235711Z | 1,271 | 1,067 | 204 | 0 |

五包 test-run-generated-read 为 0，derived-tool-cache-read 为 0，mode=None unresolved os.open groups 为 0。Hypothesis 与 pytest cache 已作为 manifest content component，因此计入 manifest 覆盖路径，不再作为未覆盖的 derived cache。每包 audit 汇总 JSON 中保留了事件数、total_digest、覆盖数和闭包外路径清单。

计数口径是测试期间在 worktree 内观察到的、事件时已存在的普通文件 open 路径去重数。Python audit-open 事件发生在 open 调用之前，因此单独的 builtins.open 记录表示打开尝试；mode=None 的低层 os.open 事件按 descriptor 结果配对，未解析数为 0。该口径对闭包检查取保守超集：失败的既存路径尝试也必须落在闭包中。所有包均为闭包外 0，未发现需扩大的路径。

逐包 runner log 均记录 HEAD ba650d668249f593ef4f4c991cf40eade32cf6db 起止一致和 exit 0。backend 并行 2,839、serial 36 全通过；repository_service 并行 1,703 passed/1 skipped、serial 205 全通过；其余三包分别 242、152、154 passed。审计执行了每个包的完整测试，backend 与 RS 均包含其 Compose 旅程。

## 5. Runner 改动与测试覆盖

run-tests.sh 接受 GATEWAY_TEST_PACKAGES 逗号分隔子集；合法值为 shared_kernel、repository_contracts、repository_client、backend、repository_service。重复、未知、空项以 exit 2 拒绝；选择结果仍按权威 runner 固定顺序。unset 时仍运行全部包，backend/RS 两遍拆分、GATEWAY_TEST_BASETEMP 下 Compose 文件处理和五锁检查保持原样。每个待运行包在开始时先输出 JSON manifest，结束时逐包输出状态和测试结果。

repository_service 测试新增 12 个 closure test cases（含 cache 与 path dependency 参数表）和净增 7 个 package-selection/validation cases；原有 runner failure-propagation case 保留。因此 RS 在 parallel 批次比 S3 增加 19 项，serial 与 skipped 数不变。

- vnext/repository_service/tests/test_test_input_closure.py 覆盖 package/shared/Docker 输入组成、非 Git environment/cache 内容、Hypothesis gzip payload 归一化、传递路径依赖、比较变化和 dirty worktree 拒绝。
- vnext/repository_service/tests/test_run_tests_script.py 覆盖指定单包、多包选择顺序、unset 时全包两遍、不合法/未知/重复包 exit 2。
- 同构输入通过参数表归并。完整 V runner 同时包含这两组 unit tests，无需缩小测试范围。

## 6. V 的 preflight 与权威门禁

最终门禁前 preflight：/home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-preflight.log。时间 2026-10-19 00:04:39 UTC，HEAD 为 V，git status clean；load average 4.52 / 4.89 / 3.47；Dolt 0、Compose project 0、8000 listener 0。记录的全部容器仅有两个长期 BuildKit 容器。

在 V clean worktree 上运行一次完整权威 runner；GATEWAY_TEST_PACKAGES、GATEWAY_TEST_BASETEMP 均 unset，workers=48：

GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh

日志：/home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-authoritative-runner.log。开始时间 2026-10-19 00:04:43 UTC，结束时间 00:39:32 UTC；起止 HEAD 均为 ba650d668249f593ef4f4c991cf40eade32cf6db，结束 git status clean，runner 自身 exit 0。

| 包 | S3 V dc9c08a410 计数 | G12 V 计数 | 增减 |
| --- | --- | --- | --- |
| shared_kernel | 242 | 242 | 0 |
| repository_contracts | 152 | 152 | 0 |
| repository_client | 154 | 154 | 0 |
| backend | 2,839 parallel + 36 serial | 2,839 parallel + 36 serial | 0 |
| repository_service | 1,684 parallel + 1 skipped + 205 serial | 1,703 parallel + 1 skipped + 205 serial | +19 passed |

RS 的 +19 为本项新增 12 个 closure test cases 与 7 个 runner 包选择/校验 cases；S3 既有的 1 skipped 与 205 serial 数不变。其他包计数完全一致。

V runner-start manifest total_digest：

| 包 | total_digest |
| --- | --- |
| shared_kernel | d598cb66404201f9df9e9a36e07c1797121939ce43b5e0e36f97a3b7391da19d |
| repository_contracts | a9b7db21069fbaf12eb9d3543f37998729601190abb7547476a7e8183db74713 |
| repository_client | 8650c951ba9d8ee1deebaa73029abbcbf0474f0da5e0a790769b58018dba6078 |
| backend | 2f6ab410800178dfbb9724744980d48344885c0ced385973601d03cad98d622f |
| repository_service | d6bf440fdfff7b03c116287a2e3b469eb3a32f539caa2e72c7af607f5038809c |

原始 manifest JSON 位于 V runner log；独立副本、逐包比较日志位于 /home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-manifests/。

本次 V Compose provenance：/home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-compose-provenance.json。project ordered-bisect-b-852072-baseline；backend image sha256:c77ee003b84d236f8d70dd950344a21dea372a7bd000a72b44ee21271bec02e7；worker sha256:c30f6e2ec49c9d0e499aceacd925e3a9aea0628adca9fa4bb4c3578d507aeed5；repository-service sha256:f2a46d9a5dcfa02f9d78482be3ed9ade5d5d6ada160cc738fcb5e69c04302b12。RS image labels 的 build-input revision 为 ba650d668249f593ef4f4c991cf40eade32cf6db，source-tree SHA-256 为 sha256:f92c586df7159406d2afe2d333c3114fdb2f4857425fc9d8c71bdca46c5f6ab4。

## 7. 沿用规则的演示与 H carried

沿用演示日志均位于 /home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-manifests/：

1. V runner-start manifests 与 V 当前 manifests 对比，五包均为“可沿用”，changed_components 为空；V post-demo 再比较也全部“可沿用”。V total_digest 见上一节。
2. 以当前 schema 对 S3 V dc9c08a410829f303aae1e0f826c674b335cb94b 计算 manifest 再和 V 比较，五包均为“运行”。shared_kernel、repository_contracts、repository_client 的变化项为 shared:scripts；backend 为 shared:scripts 与 docker:context:vnext；repository_service 为 shared:scripts、docker:context:vnext、package:repository_service。
3. V 上实际运行 GATEWAY_TEST_PACKAGES=shared_kernel GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh。只运行 shared_kernel，242 passed，exit 0；起止 HEAD 均为 V。日志 /home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-package-demo.log。之后五包仍与 V runner-start manifests 全部可沿用。

V 与 H 的包沿用和镜像身份等价分别判定：包比较决定 H 上哪些包要运行；V..H 的容器结果继续按 AGENTS.md 镜像身份规则判定。H 相对 V 只改本 handoff 文件；H 五包 manifest 与 V runner-start manifest 逐项相同，均可沿用。backend 闭包包含其 Compose 旅程的完整镜像构建输入，所以 backend 沿用时，其 Compose 结果也沿用；RS image identity 与 backend/worker 实际构建按同一 worktree H 复核。

H carried 证据：
- 最终 H preflight：/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-carried-preflight-final.log；记录 clean HEAD、load、所有容器、Dolt 进程、Compose projects 与 8000 listener。
- 最终 H 五包 manifest compare 与 identity/build 结果：/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-carried-final.log；清单和逐项 compare JSON 位于 /home/dev/gdds-p5-closure-s1-gate-logs/g12-H-manifests-final/。
- RS identity 使用 python3 -I vnext/repository_service/tests/support/build_context_digest.py identity；build-input revision 与 V RS label 一致，为 ba650d668249f593ef4f4c991cf40eade32cf6db；source-tree SHA-256 与 V RS label 一致，为 sha256:f92c586df7159406d2afe2d333c3114fdb2f4857425fc9d8c71bdca46c5f6ab4。
- backend/worker 在该 V 门禁 worktree 上，以 V provenance project ordered-bisect-b-852072-baseline 连续两次执行 docker compose --project-name ordered-bisect-b-852072-baseline -f /home/dev/gdds-p5-g12/vnext/deploy/compose.yaml build backend worker；两次之间没有运行测试。两次 backend ID 均为 sha256:c77ee003b84d236f8d70dd950344a21dea372a7bd000a72b44ee21271bec02e7；两次 worker ID 均为 sha256:c30f6e2ec49c9d0e499aceacd925e3a9aea0628adca9fa4bb4c3578d507aeed5，均与 V provenance 实际运行 ID 一致。
- 没有手工 docker rmi、docker tag 或删除 gateway-repository-client-e2e:local 和 gateway-repository-client-e2e-base:local；权威 runner 按候选 label 重建 :local 属于预期行为。

## 8. 静态检查与真实数据

五包 ruff/mypy 日志分别为：

- /home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-static-shared_kernel.log：ruff、mypy 通过，34 source files。
- /home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-static-repository_contracts.log：通过，15 source files。
- /home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-static-repository_client.log：通过，26 source files。
- /home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-static-backend.log：通过，476 source files；同一日志的 import_rules 为 0 violations / 0 runtime cycles / 6 unreachable modules。
- /home/dev/gdds-p5-closure-s1-gate-logs/g12-V3-static-repository_service.log：通过，199 source files。

本项真实数据范围为空；未运行或读取真实数据。停止条件均未触发：不需要预算外生产/Compose/Dockerfile/harness/依赖/锁修改；实测路径都可由闭包覆盖；G12 与容器门禁关系由完整构建输入闭包和独立 image identity 判定连接；V 全量 runner exit 0；没有缩小测试范围或削弱断言。

## 9. 独立审核提示词（执行计划 §8.7）

任务：独立审核 P5 架构收口治理修订计划 G12 第 1 项“按包沿用测试结果”。按执行计划 §8.2、§8.7、§8.8 与 slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：p5-g12 分支当前 HEAD（执行 git rev-parse HEAD 取得候选 H）；审核区间 p5-s3-exit 6b2b5fd0e1a82ae036b8ad19d233f3d68559465b..H。只审核该区间。使用只读 detached worktree /home/dev/gdds-p5-g12-review，并创建指向 /home/dev/gateway-data-management-system/legacy 的 legacy 符号链接；不要改写实现 worktree、不要在测试运行期间写被测 worktree。

权威依据：治理修订计划 G12 第 1 项、owner 决议 §16 DC33 第一部分、执行计划 §8.2/§8.7/§8.8/§8.9、AGENTS.md、testing-conventions.md 与本 handoff。

必须核查：
1. 外部 Python audit hook 的逐包日志、manifest 与总结；复核五包唯一读取文件数与闭包外为 0，检查 audit-open 是尝试事件的统计口径说明。
2. 按包复核闭包组件、Git tree/blob 与非 Git 内容摘要、transitive path dependencies、Rust workspace/Cargo.lock/toolchain、Python/Dolt/uv/rustc 版本、RS authority document、package uv environments 和 Python Unicode database 版本。
3. 复核 Docker build matrix：backend、worker、repository-service、repository-client e2e 和 dependency-base 的 Dockerfile、Compose 与 vnext/ context；确认 backend Compose carried 的闭包依据完整。
4. 复核 dirty worktree 拒绝、组件差异比较；未设置 GATEWAY_TEST_PACKAGES 时 runner 五包顺序/两遍拆分、GATEWAY_TEST_BASETEMP Compose 文件处理和五锁检查行为；核对指定/未知/重复包。
5. 复核 V clean preflight、起止 HEAD、完整 runner exit 0、每包计数、manifest 与 Compose provenance。重算 V↔V 与 dc9c08a410↔V 的比较，并检查 shared_kernel 单包演示日志。
6. 复核 H 五包 manifest、RS image identity label、backend/worker 两次连续构建 ID 与 V provenance；确认所有检查在运行 V 门禁的同一 worktree 完成，期间没有运行测试。
7. 核对 repository_service 相比 S3 +19 的组成（12 closure cases + 7 runner cases）、五包 ruff/mypy、import_rules 0/0/6、真实数据范围为空、停止条件和未开始 S4。

验证约束：审核不修改候选实现，不推送、不合并/rebase main，不运行真实数据。按执行计划 §8.8 记录独立审核结论；只有审核通过后才按阶段流程将 p5-g12-exit 标在审核报告 commit，并把它作为 S4 区间起点。

# P5 G13 handoff

## 范围与提交

- 审核区间：p5-s5-exit（peeled commit 5f2127f8babbb1c0cd11d4ac2f17e2ee3b369da6）..H。
- 原始 G13 owner 决议在 e92d9823ac0101a98bc04c2e12fd77b9c077d6ec；Hypothesis exclusion 方案记录于 f5911dc215，后由 owner 在 63db3730f5 修订为权威 runner 隔离 Hypothesis storage。closure 测试 fixture 恢复为本次授权修复，无新增 owner 决议。
- 当前 V：b93748c04e63be4eeece66cb5abaadf13fd7b6d3，父提交为候选 28ab8098f7c9a7e6670cf6984b4ac50245f91b2b。
- 当前 H：本 handoff-only commit；审核提示词中的完整 SHA 由审核方在 worktree 中运行 git rev-parse HEAD 后填写。
- `0e430ff990` 与 `28ab8098f7` 是历史候选，分别因 carried Hypothesis storage 与全量 runner closure 测试失败停止；本 handoff 下文保留其记录。当前门禁与 carried 只以本节所列 V 为准。
- 容器及包门禁都在 ct108-gw-dms 的 `/home/dev/gdds-p5-g13` clean detached worktree 执行；未合并、rebase、推送或打 tag。

## 环境

- HOME=/root；LC_ALL=C.UTF-8。
- PATH=/home/dev/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin。
- TMPDIR=/home/dev/gdds-test-tmp（目录权限 0700）；旧的 g12-default-tmp 未删除，留待 G10 清理。
- GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1；未设置 UV_CACHE_DIR。
- Python 3.14.6、uv 0.11.28、Dolt 2.1.11；五包使用仓库锁定环境。
- G13 日志目录 /home/dev/gdds-p5-closure-s1-gate-logs/g13 权限 0700；日志和 manifest 权限 0600，均显式 chmod。log-runner.sh 权限 0700。V 门禁在 umask 022 下运行。

## 一、供容器读取的 secret 与配置文件普查

backend 在 ct108 以 root 创建临时 Compose 输入；repository-service 容器的入口会降权为 gateway。原先用 Path.write_text 的文件在 umask 077 下为 root:root、0600，容器中的 gateway 用户无法读取。V 新增 tests/support/container_input_files.py：写入后对文件显式 chmod(0o644)，不依赖创建时 umask。此权限使 bind-mounted 文件对非 root 容器用户可读；文件内容均为 Compose 测试的假 token、假 session 和假 mapping，不含真实凭据。

| 分类 | 写入点与文件 | 状态/理由 |
| --- | --- | --- |
| 原先依赖 umask；现已显式设置 | backend 七个 Compose 文件的 _compose_env：test_archive_compose_e2e.py、test_backend_http_container_gate.py、test_history_compose_e2e.py、test_ordered_compare_compose.py、test_ordered_submit_bisect_compose.py、test_review_compose_e2e.py、test_submit_compose_e2e.py。各写 bearer token、session.json、internal bearer、provisioned mapping。 | 统一改用 tests/support/container_input_files.py 的 write_container_readable_text；chmod 0644。文件由宿主 root 创建并 bind mount，repository-service 的 gateway euid 需要读权限。 |
| 原先依赖 umask；现已显式设置 | tests/support/compose_gate_harness.py 的 seed_repository_and_mapping() 在仓库 seed 后重写 provisioned-mapping.json（约 1160 行）。 | 改用同一个 backend helper，显式 chmod 0644；容器输入同上。 |
| 原先依赖 umask；现已显式设置 | benchmarks/real_dump_journey.py 的 _write_compose_secrets()（约 1114–1178 行）：bearer、session、internal bearer、mapping。 | 改用同一个 backend helper，显式 chmod 0644。这里只执行测试/测量旅程时写假值；本次没有运行真实数据。 |
| 已显式设置权限；保持不变 | repository_service/tests/support/compose_lifecycle_harness.py 的 write_token_file()（231–234 行）写 Compose bearer token，chmod 0400。由 test_import_compose_e2e.py、test_versioned_read_compose_e2e.py、test_compose_lifecycle_negative_probes.py 使用。 | start_p2r2_service()（1527–1578 行）先从 service image 取得 gateway UID/GID，再调用 prepare_secret_file_for_container()（249–293、1565–1572 行）对宿主 secret 文件 chown；本地 chown 被拒绝时，已有 root helper 容器对 bind-mounted 源路径执行 chown。Compose file secret 在本机通过源文件挂载；文件属主因此为容器 gateway UID，0400 的 owner-read 权限足够。Dockerfile 45–51 行创建 gateway 系统用户，docker-entrypoint.sh 14–16 行以 runuser 降权到该用户。 harness 测试在 test_compose_lifecycle_harness.py 168–171 行断言 0400，并在 185–202 行覆盖 helper chown 路径。权限有意限制为属主可读，未改。 |
| 已显式设置权限；保持不变 | repository_service/tests/support/compose_lifecycle_harness.py 的 write_client_env_file()（686–701 行）写 client 环境文件，chmod 0600。 | ephemeral_client_docker_command()（704–723 行）把该文件作为 docker run 的 --env-file 参数交给宿主 Docker CLI；文件不 bind mount 进容器，宿主 root CLI 读取后将变量传给容器。测试 test_compose_lifecycle_harness.py 391–415 行断言 --env-file 用法及 0600。保持最小权限，不改。 |
| 非容器输入；保持不变 | backend tests/support/http_shutdown_harness.py 调用 subprocess.Popen 启动本机 Python HTTP server；repository_ready_stub.py 写 repository-ready-stub.json 端口文件（46–49 行），由 host harness 读取（http_shutdown_harness.py 62–94 行）。其中 runtime_settings.py 的 session、mapping、bearer 文件也供本机启动的 backend/worker 测试进程使用。 | 这些路径没有 Compose/Docker 容器消费者；不属于容器读取文件，不改权限。http_shutdown_harness.py 不改。 |
| 非容器输入；保持不变 | backend tests/support/submit_job_harness.py 的 token 写入点（约 537 行）供测试启动的本机 worker 进程使用；compose_gate_harness.py 的 provenance JSON 与 mkstemp index 是宿主诊断/临时文件。repository_service Compose 测试中的 state_path.write_text 是容器旅程的宿主输出。 | 均非容器读取的 secret/config 输入。real_dump_journey.py 的证据目录和敏感输出已有显式 0700/0600，继续保持；不改。 |

生产侧检查：tracked production code 没有创建这些宿主 secret/config 文件的 writer。vnext/deploy/compose.yaml 消费调用方提供的文件路径，deploy/README.md 的 required secret file paths 要求文件仅对容器服务 user/group 可读。未发现 production writer 依赖调用方 umask；没有修改生产代码、Compose 或部署文档。

## 二、pytest cacheprovider

实施前扫描五包 tests 与 pytest 配置中的 cache fixture、request.cache、config.cache、pytest.Cache、getfixturevalue('cache')，以及 --lf、--ff、--nf、--sw 选项，没有发现测试读取 pytest cache fixture/API 或依赖这些选择选项。复核最终树时，唯一包含 cacheprovider 字符串的是 repository_service/tests/test_run_tests_script.py:298 对新 runner 命令行的断言，不是测试对 cacheprovider 的依赖。

vnext/scripts/run-tests.sh 的 run_locked_pytest() 给每次 pytest 调用加入 -p no:cacheprovider；脚本仍打印自身实际 umask。test_input_closure.py 的 manifest 仍摘要包内 .pytest_cache（non-git:pytest-cache）；闭包规则未改。B 组演示记录了 pytest-cache 唯一变化以及修复后的可沿用结果。

## 三、TMPDIR 与 carried 的同一 worktree 限制

- AGENTS.md 和 docs/backend-vnext/testing-conventions.md 的 TMPDIR 已从 g12-default-tmp 迁到 /home/dev/gdds-test-tmp；旧目录未删除。ct108 新目录权限 0700。
- test_input_closure.py 规则未修改。testing-conventions.md 的 carried 段说明：闭包包含 vnext tracked 路径/祖先目录的本机权限位、Docker context 中仍发送的非 Git 文件和目录，以及有效 .hypothesis、.pytest_cache 的路径、内容和权限。Git tree 不记录这些本机状态；即使 commit 相同，换 worktree 也可能产生不同摘要。因此保留“同一 worktree”限制，不能跨 worktree 判定等价。

## 历史验证：候选 V 0e430ff990 的 focused 检查与验收 A/B

### 静态检查与 focused 测试

V 上在 ct108 从头执行五包 ruff/mypy：shared_kernel 34、repository_contracts 15、repository_client 26、backend 486、repository_service 200 个 source files 均通过；import_rules 为 0/0/6。日志：/home/dev/gdds-p5-closure-s1-gate-logs/g13/g13-static-0e430ff990.log。

全部相关测试文件在 V 上执行，不只跑新 helper 用例。backend 命令运行 test_container_input_files.py、七个 Compose 测试文件、test_compose_gate_provenance.py、test_compose_repository_service_image_identity.py、test_real_dump_journey.py；结果 73 passed，1 条既有 Starlette deprecation warning。repository_service 命令运行 test_run_tests_script.py 与 test_test_input_closure.py；结果 41 passed。均用 -p no:cacheprovider -n 0。日志：g13-focused-0e430ff990.log。repository_service 的 lifecycle harness 未改，故 §5 要求的 RS umask 077 代表性 Compose 用例不适用；RS Compose 用例随后由 V 全量 runner 覆盖。

### 验收 A：umask 077

RS identity 使用 vnext/repository_service/tests/support/build_context_digest.py identity 计算；两个 label gateway.p2r1.build-input-revision 与 gateway.p2r1.source-tree-sha256 均匹配当前 HEAD。结果 identity 为 build_input_revision=ebb1a777ac3fe2e0787c48bd8be689254930f4dd、source_tree_sha256=sha256:a7fa14b3df3a3ccb3c9880e5b7237918566de3ce52ff37da182819b338f4a94d。

分别执行，两个命令均显式 umask 077、-n 0，日志头也记录 0077：

- cd /home/dev/gdds-p5-g13/vnext/backend && ../scripts/uv-consume.sh -C . run pytest -p no:cacheprovider -n 0 tests/test_archive_compose_e2e.py：1 passed，exit 0，219.58 s。
- cd /home/dev/gdds-p5-g13/vnext/backend && ../scripts/uv-consume.sh -C . run pytest -p no:cacheprovider -n 0 tests/test_backend_http_container_gate.py：2 passed，exit 0，14.30 s。

日志分别为 g13-acceptance-a-archive-0e430ff990.log、g13-acceptance-a-http-gate-0e430ff990.log；两次 RS identity 比较还记录于 g13-acceptance-a-identity-0e430ff990.log 与 http-gate 日志。repository_service harness 未改。

### 验收 B：失败运行后的 manifest 对照

两组都在 ct108 临时 detached worktree 中运行，均创建 legacy 链接；环境同上，GATEWAY_TEST_PACKAGES=shared_kernel，未设置 UV_CACHE_DIR。为了不把 Hypothesis storage 的首次初始化误认为缓存差异，每个 worktree 先运行一次完整 shared_kernel runner 预热。预热本身 exit 0，日志分别为 g13-cache-control-warmup-e92d9823ac.log 与 g13-cache-fix-warmup-0e430ff990.log。

对照组以 e92d9823ac 为基线，在 vnext/shared_kernel/tests/test_framing.py 的 test_encode_row_empty 临时加入一个失败断言，创建 detached 临时提交 a5d3a44c7a1e90b5cadc91701ef7689f172cb1b9（父提交 e92d9823ac0101a98bc04c2e12fd77b9c077d6ec）。GATEWAY_TEST_PACKAGES=shared_kernel run-tests.sh 因该测试失败而 exit 1。随后 checkout 回 e92d9823ac，运行相同 runner，242 passed，exit 0。抽取该次成功 runner 日志中的起始 manifest，并以 python3 -I vnext/scripts/test_input_closure.py manifest --package shared_kernel 重算后 compare：status=运行；唯一变化 component=non-git:pytest-cache，digest 从 148db795e8ad8b8372d5c2d7d29688f74832b07148c02382cfd263cce4d458e6 变为 edbabeb5358bc80e7388988d6ec9ade8d7af575cd75214fbc102be7ca292df75。没有其他变化组件。

修复组同样以 V 为基线，临时失败提交 840a4d5088ee5a298318191fa1ffd6c072ddb49c（父提交 V），失败 runner exit 1；checkout 回 V 后运行 runner，242 passed，exit 0。修复 runner 的每次 pytest 均禁用 cacheprovider。起始 manifest 与重算 manifest compare 为 status=可沿用，changed_components=[]；.pytest_cache digest 前后均为 7b7cdf61a5bd791412c5ae7f8fed3b44418caa975183af9a2384e524fef70c70。

两组临时 worktree 均已删除；git for-each-ref --contains 对两个临时提交均无输出，没有分支或 tag 引用保留。两组的失败/通过 runner、manifest、compare、setup 与 cleanup 日志，以及 source/current JSON 均在 g13 目录中，文件权限 0600；文件名前缀分别为 g13-cache-control- 与 g13-cache-fix-。

## 历史门禁：候选 V 0e430ff990

V preflight 日志 g13-v-preflight-0e430ff990.log：无 Dolt 进程、无运行容器、Compose project list=[]、8000 空闲、worktree clean。之后由 vnext/scripts/build-repository-service-image.sh fresh 重建 RS image，日志 g13-v-rs-image-build-0e430ff990.log；g13-v-rs-image-identity-0e430ff990.log 核对 identity labels 匹配。

V 全量 runner 命令为 GATEWAY_TEST_WORKERS=48 /home/dev/gdds-p5-g13/vnext/scripts/run-tests.sh；GATEWAY_TEST_PACKAGES 未设置，umask 022，runner 自身输出 umask=0022。worktree 从头到尾均 clean，起止 HEAD 均为 V，runner exit 0。日志：g13-runner-0e430ff990.log。

| 包 | runner 结果 | V 起始 manifest total_digest | manifest 文件 |
| --- | --- | --- | --- |
| shared_kernel | 242 passed | 9e9ad30fdfd3942cb4fee0b8794e445a380bdf560d1439aa00e25c95decfa4b7 | g13-runner-manifest-shared_kernel-0e430ff990.json |
| repository_contracts | 152 passed | e368fb938924fc6771286faa15d0d550d07eab9e45647a5b8d8d86bc807db53a | g13-runner-manifest-repository_contracts-0e430ff990.json |
| repository_client | 154 passed | 9c0c114830f04d13672257404a01714f5bcc6b0f10398dcb28657f8f24436813 | g13-runner-manifest-repository_client-0e430ff990.json |
| backend | parallel 2897 passed；serial 39 passed，2897 deselected | c4bf909aa249ae5a8cc8059034ae94fa73648374e9aef11b616fcf11c7485057 | g13-runner-manifest-backend-0e430ff990.json |
| repository_service | parallel 1724 passed、1 skipped；serial 205 passed，1725 deselected | c1f525ff418fd2cfa065499035c64c1fa5cb56a9ab894bd34a302ea39d306ca6 | g13-runner-manifest-repository_service-0e430ff990.json |

五份 manifest 均从 g13-runner-0e430ff990.log 中 runner 起始输出原样提取，记录 V、clean_worktree=true。日志与 JSON 均在 /home/dev/gdds-p5-closure-s1-gate-logs/g13/，权限 0600；manifest source 是 V 的全量权威 runner，本 handoff 不使用其他运行或临时 worktree 作为来源。

V postflight 日志 g13-v-postflight-provenance-0e430ff990.log：无 Dolt、容器、Compose project，8000 空闲，worktree clean。RS identity label 仍匹配。关键镜像 provenance：

- gateway-repository-service:local：sha256:c45193ae66f30057ee60cc82b24bfeaa65a1c382eca73a79d513e6d40e2e1773；build-input 与 source-tree labels 同上。
- gateway-repository-client-e2e:local：sha256:3f1fc555959e0b406257e412b47f32b4d1fde70ab85eac7f2cdf853da7f55482；label revision=V。
- gateway-repository-client-e2e-base:local：sha256:ba6c64db44f5f5b7f573fb1df6295c11a5c9e20d9c188189921e717a623ff38c。
- gateway-p2r1-repository:lock-6dc9659f0aee：sha256:63b7e79899d4379f24a1d58f0e22e1960847733a76e684dd170b8e631e00367f；UV lock label 对应 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11。
- backend/worker Compose 镜像使用项目专属 tag；tag 与 image ID 的完整 inspect 列表见 postflight 日志，backend manifest 记录 runner 起始时选用的构建输入。gateway-backend:local 与 gateway-worker:local 不存在。未手工 docker rmi、docker tag 或删除 client e2e 镜像。

H 的 carried 在 handoff-only 提交完成后执行，必须在同一个 ct108 worktree、umask 022 和上列环境中重算 RS identity，并将五个 H manifest 分别与表中 V runner 起始 manifest compare。carried 日志保存在 g13 目录，文件名含 H 短 SHA；只有 RS labels 相符且五包均为“可沿用”才完成 G13。若任一不符，按 owner 指令停止，不改写本 handoff。

## 当前恢复与最终验证（权威记录：V b93748c04e）

### 第六项环境隔离修复

owner 决议 `63db3730f5` 将 Hypothesis 第六项改为权威 runner 隔离存储；原来按 Hypothesis 派生缓存排除条目的提案停止，不改 `test_input_closure.py`、manifest 摘要规则或 schema 8。修复提交 `b93748c04e63be4eeece66cb5abaadf13fd7b6d3` 建立于候选 `28ab8098f7c9a7e6670cf6984b4ac50245f91b2b`，只修改 `vnext/repository_service/tests/test_test_input_closure.py`：新增模块级 autouse fixture，以 `monkeypatch.delenv("HYPOTHESIS_STORAGE_DIRECTORY", raising=False)` 让 fixture-repo manifest 用例按默认本地目录测试。原有显式 `setenv("HYPOTHESIS_STORAGE_DIRECTORY", "custom-hypothesis")` 用例仍覆盖此删除并保持原意。

检查 `test_test_input_closure.py` 和 `test_run_tests_script.py` 的环境访问后，runner 新增设置且会影响 focused 与权威 runner 差异的变量只有 `HYPOTHESIS_STORAGE_DIRECTORY`。`test_run_tests_script.py` 不依赖该变量缺失：它构造调用方传入值并验证 runner 覆盖该值、manifest 与 pytest 使用同一 runner 路径。因此该文件不需改动。没有改 `run-tests.sh`、`test_input_closure.py` 或其他文件。

runner 的存储路径为 `$TMPDIR/gateway-runner-hypothesis/<package>`；TMPDIR 未设置或为空时固定使用 `/tmp`。路径只由 TMPDIR 与包名决定。runner 覆盖外部 `HYPOTHESIS_STORAGE_DIRECTORY`，打印各包实际路径；先清除所选包的残留目录，再在设置了该包变量且目录不存在时生成起始 manifest。该包的所有 pytest 调用共用该路径。runner 在整个调用退出时通过统一 EXIT cleanup 删除所有所选包目录，而不是逐包测试结束即删除；这同样满足“runner 结束后目录不存在”。非零退出由 EXIT trap 清理；HUP、INT、TERM handler 转成退出码后也进入 EXIT cleanup。只删除这些 runner 专用路径，不删除 worktree 的 `.hypothesis` 或 TMPDIR 其他内容。

这一隔离让权威 runner 之间不保留 Hypothesis 失败样例；代价与决议一致：当 runner exit 非 0，先停止并记录结果，再从失败日志中分析 Hypothesis 打印的反例，不依赖下一次 runner 自动复用样例。worktree 中的 `.hypothesis` 仍供开发者 focused 运行使用，不再是权威 runner 的输入。

### 候选 `28ab8098f7` 停止与验收 A/B/C 沿用

候选 `28ab8098f7` 的全量 runner 曾 exit 1，日志保留在 `g13-v-runner-28ab8098f7.log`。repository_service 并行批次 1727 passed、1 skipped、3 failed；三个失败均来自 `tests/test_test_input_closure.py`：两个参数化 hypothesis-storage 内容摘要用例，以及 `test_closure_manifest_lists_package_shared_and_docker_build_inputs`。runner 设置的外部存储变量被这些 fixture manifest 子进程继承，而测试写入/断言的是 fixture repo 下的 `.hypothesis`。focused 原先没有设置该变量，所以当时未暴露。runner 的 serial 批次结束后最终 exit 1，并清理所有 runner 专用目录；worktree clean。此提交不作为 V。

在 `28ab8098f7..b93748c04e` 上执行 `git diff --stat`，结果只有 `vnext/repository_service/tests/test_test_input_closure.py | 5 +++++`（1 file changed, 5 insertions）。同一范围的 name-only 检查也只有该文件，详见 `g13-scope-diff-28ab-b937.log`。因此没有改 Compose 用例、harness、secret 写入点、runner、镜像输入或闭包实现，验收 A/B/C 沿用 `28ab8098f7` 的结果：

- **A（umask 077）**：`g13-acceptance-a-archive-28ab8098f7.log`，`test_archive_compose_e2e.py -n 0` 为 1 passed、exit 0；`g13-acceptance-a-http-28ab8098f7.log`，`test_backend_http_container_gate.py -n 0` 为 2 passed、exit 0。两份日志均记录 umask 0077；RS image identity 与标签比较见 `g13-rs-identity-for-a-28ab8098f7.log`。
- **B（失败后合格运行）**：e92 对照失败 runner 后紧接着运行基线，compare 为“运行”，唯一变化为 `non-git:pytest-cache`；digest 从 `148db795e8ad8b8372d5c2d7d29688f74832b07148c02382cfd263cce4d458e6` 到 `edbabeb5358bc80e7388988d6ec9ade8d7af575cd75214fbc102be7ca292df75`。修复 runner 在 `28ab8098f7` 上失败退出 1 后确认 runner Hypothesis storage 已删除；切回候选并通过 242 项后，以相同外部 Hypothesis 路径比较，结果“可沿用”、`changed_components=[]`，总摘要前后均为 `dfa177d8be1746eea83ffc74cc2f6d0f656e5ee7574c349d1d0a6d4135c1efad`。正确重试的日志前缀为 `g13-cache-control-*-retry*-e92d9823ac-28ab8098f7` 与 `g13-cache-fix-*-28ab8098f7`；source/current JSON 和 compare JSON 均留在 g13 目录。
- **C（Hypothesis storage）**：V 候选 fresh detached worktree 开始时本地与 runner `.hypothesis` 均不存在；shared_kernel runner 242 passed，结束后两处仍不存在，compare 为“可沿用”、无变化，总摘要 `7342382c98b2429d20b790d0a2c873bd4703e4235d02274fe7e60ae9d625cc32`。e6 对照 fresh worktree 运行 242 passed 后生成本地 `.hypothesis`；compare 为“运行”，唯一变化 `non-git:hypothesis-storage`，digest 从 `7b7cdf61a5bd791412c5ae7f8fed3b44418caa975183af9a2384e524fef70c70` 到 `ad93cf8bb4a1c7db792b7c10695825d39c7d3fda85779b93841ccac8978e2efb`。两组的起始/当前 manifest、compare 与状态日志分别以 `g13-acceptance-c-*-v-28ab8098f7`、`g13-acceptance-c-*-e6-28ab8098f7` 命名；scratch worktree 均已用 `git worktree remove` 删除。

B 演示中的方法偏差也保留：最初对照组临时新增的失败测试在 checkout 回 e92 后不存在，导致首次 compare 错误地为“可沿用”；随后改为让基线已有的 `test_encode_row_empty` 失败，才正确观察到 pytest-cache 改变。修复组第一次临时注入因引号转义形成 SyntaxError；它仍验证 runner 收集失败时会清理存储，但不作为测试失败演示，之后用 `assert 1 == 0` 正确重试并通过。相关初始/重试日志均保留；临时提交 `1bd6770bfff2f72f1548b7ee75b1c7655529762d`、`8a585c08c2cb6a578eb10132039ab584f5c020ba`、`375d95daa90402f7505746de2ea90ceb6363e14d` 均不在任何引用中，临时 worktree 已删除。

### 新 V `b93748c04e` 验证

- 环境：ct108；HOME=/root；LC_ALL=C.UTF-8；PATH=`/home/dev/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`；TMPDIR=/home/dev/gdds-test-tmp（0700）；GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1；未设置 UV_CACHE_DIR。静态、focused、全量 runner 均 umask 022。
- 静态：五包 ruff 与 mypy 全通过（分别检查 shared_kernel 34、repository_contracts 15、repository_client 26、backend 486、repository_service 200 个 source files）；import_rules 为 0/0/6。日志 `g13-static-b93748c04e.log`。
- focused：`test_test_input_closure.py` 与 `test_run_tests_script.py` 两份完整文件合跑，各 47 passed、exit 0。第一次未设置 HYPOTHESIS_STORAGE_DIRECTORY，日志 `g13-focused-unset-b93748c04e.log`；第二次设置为 `/home/dev/gdds-test-tmp/gateway-runner-hypothesis/repository_service`，日志 `g13-focused-runner-env-b93748c04e.log`，结束时该路径不存在。
- preflight `g13-v-preflight-b93748c04e.log`：无 Dolt、无容器、Compose project list=[]、8000 空闲、V worktree clean。
- fresh RS image 由 `build-repository-service-image.sh` 在 V 上重建；日志 `g13-v-rs-image-build-b93748c04e.log`。identity/log `g13-v-rs-image-identity-b93748c04e.log` 显示 candidate 与 build-input revision 均为 `b93748c04e63be4eeece66cb5abaadf13fd7b6d3`，source tree 为 `sha256:b24fa92dbbb59d00617eec838a22ca947fa98fe42fab996770aa9b9e20f7f15c`，三项对应镜像 labels 全部匹配。
- 全量 runner：`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`，未设置 GATEWAY_TEST_PACKAGES；runner 自身打印 umask=0022。日志 `g13-v-runner-b93748c04e.log`，起止 HEAD 均为 V，worktree clean，exit 0。shared_kernel 242 passed；repository_contracts 152 passed；repository_client 154 passed；backend 并行 2897 passed，serial 39 passed / 2897 deselected；repository_service 并行 1730 passed、1 skipped，serial 205 passed / 1731 deselected。runner 退出时五包专用 Hypothesis storage 均清除。

V runner 起始 manifest 由上述全量权威 runner 日志提取；JSON mode 0600：

| 包 | 起始 total_digest | manifest |
| --- | --- | --- |
| shared_kernel | `2245a7210125b2b61e010f6a2f53e8bb6fa6b58955f0766db5169bbadf2be653` | `g13-runner-manifest-shared_kernel-b93748c04e.json` |
| repository_contracts | `3b0a3a67423a9c066644eac78cf5b1ce889d3eb2fdf88dfeb6056f25986221c7` | `g13-runner-manifest-repository_contracts-b93748c04e.json` |
| repository_client | `2c10e4d5f5a58b1995f8498c8595fc9910b46a41eb0c2c4b0e5da1618899de1f` | `g13-runner-manifest-repository_client-b93748c04e.json` |
| backend | `11db91e37d2137a5bf710f05bd8f8ecc8daf310d605bfd019469fd637df47dce` | `g13-runner-manifest-backend-b93748c04e.json` |
| repository_service | `aa889758a6fa7496cc045bf3b5347c0613d65ae25c70dfa6d72a5a815e439efe` | `g13-runner-manifest-repository_service-b93748c04e.json` |

- postflight `g13-v-postflight-provenance-b93748c04e.log`：无 Dolt、容器或 Compose project，8000 空闲，worktree clean，五包 runner storage 均不存在。RS identity 与 labels 仍一致。RS `gateway-repository-service:local` ID `sha256:5f9fb45eda9d6234fc988f9417e1f6cff10b2b1b4f35602fcea9181f6ac97a06`；client e2e `gateway-repository-client-e2e:local` ID `sha256:0776d0b9be1e3db56b18d9ea033bc71bb23c15fb391b7e66cc479eb0c28844b0`，revision label 为 V；client e2e base ID `sha256:ba6c64db44f5f5b7f573fb1df6295c11a5c9e20d9c188189921e717a623ff38c`；P2R1 dependency base ID `sha256:63b7e79899d4379f24a1d58f0e22e1960847733a76e684dd170b8e631e00367f`。runner 按 label 重建 client e2e 镜像是预期行为。没有手工 docker rmi/tag 或删除受保护镜像。

### H carried 记录

本 handoff-only commit 是 H。commit 后在同一 `/home/dev/gdds-p5-g13` worktree、umask 022、与 V runner 相同的 HOME、LC_ALL、PATH、TMPDIR、GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT、Docker daemon 与 build 环境下，为每包设置 `/home/dev/gdds-test-tmp/gateway-runner-hypothesis/<package>`，并确保目录无残留。逐包在 H 计算 manifest，与上表 V 全量 runner 的起始 manifest 比较；repository_service 还重算 RS identity 并与 image labels 比较。carried 原始输出和 H manifests 使用 g13 目录下包含 H 短 SHA 的 `g13-carried-<H-short>-<package>.log`、`g13-carried-manifest-<package>-<H-short>.json`、`g13-carried-compare-<package>-<H-short>.json` 命名；结果只允许五包全部“可沿用”且 RS identity/labels 匹配。日志在 H 提交后生成，不改变 H。任一包为“运行”则按 owner 指令停止，不再做其他验证。

### 追加停止与偏差记录

- Hypothesis exclusion 原方案停止：在 `f5911dc215` 的决议后检查锁定的 Hypothesis 6.156.6 源码，发现 `constants/` 与 `unicode_data/` 的缓存只要可解析就可能被直接采用，因此不能作为无输入的派生缓存排除。证据保留于 `g13-hypothesis-source-e6ea9be727.log`、`g13-hypothesis-source-e6ea9be727-retry.log`、`g13-hypothesis-source-excerpts-e6ea9be727.log`、`g13-hypothesis-source-details-e6ea9be727.log`。owner 随后以 `63db3730f5` 修订为 runner 隔离，不改摘要规则或 schema。
- carried 停止：旧 V `0e430ff9902677709b4f27c373c547cefc7a1441` 到旧 H `e6ea9be727e6bc4ad2dad65e2fc3ffcc3cf3a2ab` 的 shared_kernel compare 为“运行”；唯一变化 `non-git:hypothesis-storage`，从 `7b7cdf61a5bd791412c5ae7f8fed3b44418caa975183af9a2384e524fef70c70` 到 `1f667af373b805cce079b931f95f8cb18a84d946c60b7f872a3e0fc7227da005`，见 `g13-carried-e6ea9be727.log` 与 `g13-carried-compare-shared_kernel-e6ea9be727.json`。新 worktree 起始无 `.hypothesis`，V runner 测试后生成内容，导致 shared_kernel 和 backend 不可沿用；旧结果仅作历史，不作为当前 V 来源。
- runner 停止：`28ab8098f7` 的 3 个 closure 测试失败及原因见本节；修复提交 `b93748c04e` 在其上新建，未 amend。focused 最初未复现是因为没有 runner 设置的环境变量；本次通过两种 focused 环境验证修复。
- 更早的 mypy 停止与修复、preflight 对 `pgrep -af "[d]olt"` 自身误报后改用 `pgrep -x dolt` 的经过，保留于前文历史停止记录和对应日志。此前一次 preflight 命令拼装错误及修正记录也保留；未因此运行容器或修改镜像。
- DC33 真实数据范围为空；本轮不运行真实数据，没有生产代码变更。


## 历史路径清单（截至候选 V 0e430ff990）

本轮 G13 实现文件（e92d9823ac..V）：

- AGENTS.md
- docs/backend-vnext/testing-conventions.md
- vnext/scripts/run-tests.sh
- vnext/repository_service/tests/test_run_tests_script.py
- vnext/backend/tests/support/container_input_files.py
- vnext/backend/tests/support/compose_gate_harness.py
- vnext/backend/tests/test_container_input_files.py
- vnext/backend/tests/test_archive_compose_e2e.py
- vnext/backend/tests/test_backend_http_container_gate.py
- vnext/backend/tests/test_history_compose_e2e.py
- vnext/backend/tests/test_ordered_compare_compose.py
- vnext/backend/tests/test_ordered_submit_bisect_compose.py
- vnext/backend/tests/test_review_compose_e2e.py
- vnext/backend/tests/test_submit_compose_e2e.py
- vnext/backend/benchmarks/real_dump_journey.py

在旧 handoff 对应的候选 V 0e430ff990 阶段，仅新增了 handoff 文件；本次后续恢复提交 b93748c04e 的单文件差异见“当前恢复与最终验证”。没有修改生产代码、Contract、Dockerfile、Compose 文件或依赖锁。

## 历史停止与偏差记录（截至候选 V 0e430ff990）

- ebb1a777ac 不能作为 V：五包静态检查停在 backend mypy，八个消费者因从 compose_gate_harness 隐式再导出 helper 收到 attr-defined。原日志 g13-static-ebb1a777ac.log 保留。按 owner 指令在其上新建 0e430ff990；修复提交只改七个 Compose 测试文件和 real_dump_journey.py 八个消费者，直接从 tests.support.container_input_files 导入，不改 harness 导出。V 上五包 ruff/mypy 已从头通过。
- 前一次 preflight 的 pgrep -af "[d]olt" 把包含该模式的 preflight 自身命令行当作 Dolt，形成误报；日志 g13-preflight-focus-ebb1a777ac.log。随后改用 pgrep -x dolt，g13-preflight-focus-retry-ebb1a777ac.log 退出 0，未发现 Dolt。
- V 恢复后第一次新 preflight 命令有 shell 引号拼装错误，日志 g13-preflight-0e430ff990.log exit 2；修正 sport filter 后 g13-preflight-0e430ff990-retry.log exit 0。该失败没有启动测试、Compose 或镜像构建。
- 在旧 handoff 写入时，handoff-carried 尚待其 H 提交后执行；该历史待办由本 handoff 当前恢复章节记录的新 V/H 流程取代。若当前 carried 不满足条件，停止并报告，不自行修改实现或继续门禁。
- DC33 范围为空：本轮不运行真实数据；没有生产代码变更。

## 审核提示词

任务：独立审核 P5 G13 当前最终候选。审核方请先在审核 worktree 运行 `git rev-parse HEAD`，将输出的 40 位完整 SHA 填入下文 H；不要从短 SHA 推断。

审核对象：当前 H = <审核方填写完整 SHA>；V = b93748c04e63be4eeece66cb5abaadf13fd7b6d3；审核区间为 p5-s5-exit（5f2127f8babbb1c0cd11d4ac2f17e2ee3b369da6）..H。权威依据包括 G13/G10 owner 决议 e92d9823ac、f5911dc215 与 63db3730f5、AGENTS.md、testing-conventions.md 及比例化保障政策。历史阶段记录见本 handoff 中标为“历史”的章节；当前 V 证据见“当前恢复与最终验证”。

请在只读 detached worktree 中审核，不修改实现或 handoff，不推送、不合并、不 rebase、不打 tag。重点核查：

1. 对比 p5-s5-exit..H 与文件路径清单；确认 G10 secret 权限修改、runner 禁用 pytest cacheprovider、TMPDIR 迁移及当前 runner Hypothesis 隔离均在预算内；确认新恢复提交只改 test_test_input_closure.py，模块级 autouse fixture 清除 runner 变量，显式 setenv 用例仍有效。
2. 复核 backend 与 repository_service 容器输入普查表。确认 backend helper 在写后显式 chmod 0644；RS 0400 token 经 gateway uid/gid chown 后可读，0600 env file 由 host Docker CLI 的 --env-file 读取；http_shutdown_harness 不属于容器输入；生产侧没有发现依赖调用方 umask 的 tracked writer。
3. 检查五包 cache 扫描结论、run_locked_pytest 的 -p no:cacheprovider、test_run_tests_script.py 断言，以及 manifest 仍摘要 .pytest_cache。核对 B 的 e92 compare 唯一变化是 pytest-cache、V compare 为可沿用且 changed_components=[]；核对 runner 的 Hypothesis 固定路径、manifest 与 pytest 环境一致、统一退出清理和失败/信号清理。
4. 复核 TMPDIR 迁移到 /home/dev/gdds-test-tmp、旧目录保留，以及同一 worktree 限制由本机权限位、非 Git Docker context、.hypothesis 与 .pytest_cache 支持。
5. 复核当前 V 的五包 ruff/mypy、import_rules、两种 HYPOTHESIS_STORAGE_DIRECTORY 环境下的 focused 文件、A/B/C 沿用依据与日志；A 的 umask 为 077，28ab..V diff stat 仅包含 closure test fixture 文件。
6. 复核当前 V full runner clean worktree、起止 HEAD、umask 022、48 workers、exit 0、五包起始 manifest；复核 fresh RS 镜像、identity/labels、preflight/postflight 与 client e2e image provenance。
7. 复核 H carried 证据：同一 ct108 worktree 下 RS identity/labels 相符，五包 manifest 与 V runner 起始 manifest compare 均为“可沿用”；若任一项不符，不能确认 G13 完成。
8. 核对停止记录包含 ebb1 mypy 停止和 0e 修复、pgrep 自匹配误报及更正、0e/e6 carried Hypothesis storage 停止、f591 exclusion 源码核查停止、28ab 全量 runner 三失败与 b937 fixture 修复；确认 DC33 真实数据范围为空。

交付独立审核结论（通过 / 定向修订 / 整体返工）及按严重度排序的发现，注明文件位置与证据。等待 owner 初审，不要自行合并或打 tag。

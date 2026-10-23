# P5 G13 handoff

## 范围与提交

- 审核区间：p5-s5-exit（peeled commit 5f2127f8babbb1c0cd11d4ac2f17e2ee3b369da6）..H。
- G13 owner 决议在 e92d9823ac0101a98bc04c2e12fd77b9c077d6ec；实施 worktree 从该提交建立。此次 mypy 恢复没有新增 owner 决议。
- V：0e430ff9902677709b4f27c373c547cefc7a1441，父提交 ebb1a777ac3fe2e0787c48bd8be689254930f4dd。
- H：本 handoff-only commit；审核提示词中的完整 SHA 由审核方在 worktree 中运行 git rev-parse HEAD 后填写。
- 容器及包门禁都在 ct108-gw-dms 的 /home/dev/gdds-p5-g13 clean detached worktree 执行；未合并、rebase、推送或打 tag。

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

## 五、focused 检查与验收 A/B

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

## 六、V 门禁、manifest 与 provenance

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

## 路径清单

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

V 之后仅新增本 handoff 文件。没有超出路径预算；没有修改生产代码、Contract、Dockerfile、Compose 文件或依赖锁。

## 停止与偏差记录

- ebb1a777ac 不能作为 V：五包静态检查停在 backend mypy，八个消费者因从 compose_gate_harness 隐式再导出 helper 收到 attr-defined。原日志 g13-static-ebb1a777ac.log 保留。按 owner 指令在其上新建 0e430ff990；修复提交只改七个 Compose 测试文件和 real_dump_journey.py 八个消费者，直接从 tests.support.container_input_files 导入，不改 harness 导出。V 上五包 ruff/mypy 已从头通过。
- 前一次 preflight 的 pgrep -af "[d]olt" 把包含该模式的 preflight 自身命令行当作 Dolt，形成误报；日志 g13-preflight-focus-ebb1a777ac.log。随后改用 pgrep -x dolt，g13-preflight-focus-retry-ebb1a777ac.log 退出 0，未发现 Dolt。
- V 恢复后第一次新 preflight 命令有 shell 引号拼装错误，日志 g13-preflight-0e430ff990.log exit 2；修正 sport filter 后 g13-preflight-0e430ff990-retry.log exit 0。该失败没有启动测试、Compose 或镜像构建。
- Handoff-carried 尚待 H 提交后执行。若不满足 carried 条件，停止并报告，不自行修改实现或继续门禁。
- DC33 范围为空：本轮不运行真实数据；没有生产代码变更。

## 审核提示词

任务：独立审核 P5 G13。审核方请先在审核 worktree 运行 git rev-parse HEAD，将输出的 40 位完整 SHA 填入下文 H；不要从短 SHA 推断。

审核对象：p5-g13 的最终 handoff-only 提交 H = <审核方填写完整 SHA>；V = 0e430ff9902677709b4f27c373c547cefc7a1441；审核区间为 p5-s5-exit（5f2127f8babbb1c0cd11d4ac2f17e2ee3b369da6）..H。权威依据为治理修订计划 G13、G10 第 4/6/7 项、§3 第 12 项 owner 2026-10-23 决议、AGENTS.md、testing-conventions.md 及比例化保障政策。

请在只读 detached worktree 中审核，不修改实现或 handoff，不推送、不合并、不 rebase、不打 tag。重点核查：

1. 对比 p5-s5-exit..H 与文件路径清单；确认 V 之后只新增 handoff，八处 mypy 修复直接导入 helper，harness 无 __all__/别名导出，改动处于路径预算内。
2. 复核 backend 与 repository_service 容器输入普查表。确认 backend helper 在写后显式 chmod 0644；RS 0400 token 经 gateway uid/gid chown 后可读，0600 env file 由 host Docker CLI 的 --env-file 读取；http_shutdown_harness 不属于容器输入；生产侧没有发现依赖调用方 umask 的 tracked writer。
3. 检查五包 cache 扫描结论、run_locked_pytest 的 -p no:cacheprovider、test_run_tests_script.py 断言，以及 manifest 仍摘要 .pytest_cache。复核 control compare 唯一变化为 pytest-cache、修复 compare 为可沿用且 changed_components=[]。
4. 复核 TMPDIR 迁移到 /home/dev/gdds-test-tmp、旧目录保留，以及同一 worktree 限制是否由本机权限位、非 Git Docker context、.hypothesis 和 .pytest_cache 组成支持。
5. 复核 V 的五包 ruff/mypy、import_rules、focused 测试、验收 A/B 日志与退出码；确认 A 在 umask 077，RS labels 与当前 identity 一致。
6. 复核 V full runner 的 clean worktree、起止 HEAD、umask 022、48 workers、exit 0、五包起始 manifest；复核 fresh RS 镜像 build、labels、preflight/postflight 与 image provenance。
7. 复核 H carried 日志：同一 ct108 worktree 下 RS identity/labels 相符，五包 manifest 与 V runner 起始 manifest compare 均为“可沿用”；若任一项不符，不能确认 G13 完成。
8. 核对停止记录包含 ebb1 mypy 停止和 0e430 修复提交、pgrep 自匹配误报及更正；确认 DC33 真实数据范围为空。

交付独立审核结论（通过 / 定向修订 / 整体返工）及按严重度排序的发现，注明文件位置与证据。等待 owner 初审，不要自行合并或打 tag。

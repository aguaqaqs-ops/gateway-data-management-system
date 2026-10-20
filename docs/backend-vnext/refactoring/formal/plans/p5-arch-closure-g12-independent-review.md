# P5 架构收口 G12 第 1 项独立审核

- 结论：**通过**（初审 2026-10-19；终审 2026-10-20 维持通过，见 §7）
- 日期：2026-10-19；终审 2026-10-20
- tag：`p5-g12-exit`（附注 tag，初审方创建，指向 `13d97dc2db`）；合并提交 `86a60e58da`（`--no-ff`）。
- 审核对象：`p5-g12` @ H4 `5fbae736b028d2c30b3fa73f60e44d3d67810eeb`；门禁提交 V `62a4122f9ce97615113beae3bbbf6497b3ab2adf`；G12 实施基线 `46c5684c98`；审核区间 `p5-s3-exit`（`6b2b5fd0e1a82ae036b8ad19d233f3d68559465b`）..H4
- 依据：治理修订计划 G12 第 1 项、决议记录 §16 DC33、执行计划 §8.1、§8.2、§8.7–§8.9、`AGENTS.md`、`docs/backend-vnext/testing-conventions.md` 和 G12 handoff。

## 1. 结论摘要

G12 第 1 项的按包闭包、权威来源规则、选择性 runner 和证据流程均已落地，独立复核未发现阻塞项。V 的完整权威 runner 通过，最终 H4 五包 manifest 与各自实际运行来源逐项相等；镜像身份和 backend Compose 结果的沿用依据也满足治理规则。审核对象只包含 G12 第 1 项，未开始 S4；按 owner 授权可将已审核阶段头标记为 `p5-g12-exit`，之后再进入 S4。

## 2. Findings

无。

## 3. 验收核对

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| 按包闭包与实测路径覆盖 | 通过。五包闭包外输入路径均为 0。审计计数为唯一现存仓库内普通文件的 read/read-write 模式 open 路径：shared_kernel 8,771 = manifest 输入 8,737 + 派生 bytecode 34；repository_contracts 8,607 = 8,592 + 15；repository_client 9,906 = 9,871 + 35；backend 12,056 = manifest 输入 12,055 + 生成后仅写临时路径 1；repository_service 11,045 = 11,045。 | `/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v7/corrected-open-input-accounting.json`；五份 `g12-audit-v7/*-summary.json`；raw open streams 与 `g12-audit-v7/hook/sitecustomize.py`；handoff §4。hook 记录 open 事件和 `os.open` 的 mode/flags，不作为 `read(2)` 证据。 |
| 审计覆盖边界与非 Python 输入 | 通过。worktree 外 `PYTHONPATH` hook 覆盖 xdist worker 和继承环境的 Python 子进程；另有 bootstrap 覆盖 runner 用 `python3 -I` 启动的 manifest CLI。backend 唯一 `.hypothesis/tmp` 路径由 `mkstemp` 创建后关闭，再由 gzip 写入并改名；源码未显示读取该临时内容。`.pytest_cache` 和有效 Hypothesis storage 都进入内容摘要；runner 未使用 `--lf`/`--nf`。 | `/home/dev/gdds-p5-closure-s1-gate-logs/g12-audit-v7/audit-isolated-manifest.sh`、`hook/sitecustomize.py`、backend raw event stream；`vnext/scripts/test_input_closure.py`；handoff §3–§4。 |
| Docker build-context 闭包 | 通过。覆盖 backend、worker、repository-service、client e2e 和 dependency-base 的 Dockerfile、Compose 定义与完整 `vnext/` context；纳入 tracked tree、Docker 会收到的非 Git 内容、tracked 路径/目录权限模式、ignore 规则、构建参数与工具/镜像身份。RS client 两个测试 Dockerfile 的 context 确认为 `vnext/`。交叉枚举的 19,560 个 ignored paths 均被 `.dockerignore` 排除。 | `vnext/scripts/test_input_closure.py`；`vnext/repository_service/tests/test_test_input_closure.py`（Docker context、ignore、tracked mode 参数化用例）；handoff §3。未手工对两项 client e2e `:local` 标签执行 rmi、tag 或删除。 |
| manifest、dirty 拒绝与比较 | 通过。Git 输入使用当前提交 tree/blob identity，非 Git 输入用内容/权限摘要；传递路径依赖、Rust workspace/lock/toolchain、解释器及运行时工具版本、legacy、缓存、实际 `.venv` 均有建模。manifest 和 compare 均要求 clean worktree；compare 列出变化组件。 | `vnext/scripts/test_input_closure.py:284,1164,1337,1462`；`vnext/repository_service/tests/test_test_input_closure.py:262,635,645,693`。dirty CLI 回归断言 exit 2。 |
| runner 默认与包选择行为 | 通过。未设置 `GATEWAY_TEST_PACKAGES` 仍按原顺序运行全部五包；backend 与 RS 保留并行/serial 两遍。未知、重复、空值/空项 exit 2；`GATEWAY_TEST_BASETEMP` 下 Compose 文件拆分/忽略逻辑和五锁快照检查保留。 | `vnext/scripts/run-tests.sh:21,44-80,100-136,141-270`；`vnext/repository_service/tests/test_run_tests_script.py`；V 日志记录 `GATEWAY_TEST_PACKAGES=unset`。 |
| V 门禁、计数和三项演示 | 通过。V preflight 记录无 Dolt、无 Compose、8000 空闲及容器/负载；runner clean start/end、起止 HEAD 相同、exit 0，逐包记录 manifest。相对 S3，RS 并行 +31 的来源是 G12 新增的闭包测试 24 项（含 2 个 tracked 文件/目录 mode 场景）和包选择/默认行为测试 7 项；没有缩小既有测试。V 自比五包可沿用，S3→V 五包均运行，`shared_kernel` 单包实跑只运行该包并通过 242 项。 | `/home/dev/gdds-p5-closure-s1-gate-logs/g12-preflight-20261019T173700Z.log`、`g12-preflight-20261019T181440Z.log`；`g12-V7-runner-62a4122f9c-20261019T173659Z.log`；`g12-V7-manifest-demos-summary.log`；`g12-selective-shared-kernel-V7-20261019T181536Z.log`；handoff §5–§6。 |
| H4 逐包来源与容器门禁关系 | 通过。H4 五包 `changed=[]`、均可沿用：shared_kernel `d7f8576efc5852ddb1286d7cdfc7556118b2a9a3c64d653f03fd44a457f856c8`、repository_contracts `34824b4131307bfe178b6d0d870f7d1409b708d0e5dd491d00dbb8d0337db3ad`、repository_client `8c719ccf5bc772287feca799876affd1db7e8ece071861971a53f4393f4401fb`、backend `0b81d651a3a4a17ecefd0a3c0b6c64ddfb350430557770b74519ce523f643c2b`、repository_service `79bbb50c94012d71826d71bb3eff4083b016432ff3cc2c1b3ab8890c7df3b1f0`。前四个非 backend 包的来源为 V 实际完整 runner；backend 直接来源为 H1 clean backend-only 权威 runner，不是沿用链。RS identity 的 build-input/source-tree labels 与 V provenance 一致，image ID 也相同。V provenance project 下 backend/worker 连续重建 ID 不等，随后 H1 clean backend-only runner 实际重跑并通过 Compose journey，记录了新 provenance。backend 闭包覆盖该 Compose journey 的完整构建输入，因此 backend 包 manifest 相等时其 Compose 结果随包沿用；未发现与 AGENTS.md 阶段门禁要求冲突。 | LXC `/home/dev/gdds-p5-closure-s1-gate-logs/g12-H-final-manifests/summary.log`、`repository-service-identity-check.log`、`g12-H1-carried-backend-worker.log`、`g12-H1-backend-runner-20261019T182123Z.log`、`g12-H1-compose-provenance.json`；V provenance `g12-V7-compose-provenance.json`；handoff §6–§7。 |
| 静态检查、范围与停止条件 | 通过。五包 Ruff/mypy 通过；import_rules 为 0 violations / 0 runtime cycles / 6 unreachable。路径改动在授权范围；无生产、Compose、Dockerfile、harness、依赖或锁文件修改。真实数据范围为空；无停止条件触发，未开始 S4。 | `/home/dev/gdds-p5-closure-s1-gate-logs/g12-static-v7-62a4122f9c.log`；`git diff --name-only 46c5684c98..H4`；handoff §2、§8。 |

## 4. 实际执行的检查

| 检查 | 命令/方式 | 结果 |
| --- | --- | --- |
| 确认审核对象与只读 worktree | `git status --short --branch`、`git rev-parse HEAD`（`/home/dev/gdds-p5-g12-review`） | clean，HEAD 为 H4；保持 detached，只读审核。 |
| 审核区间和路径预算 | `git diff --stat 46c5684c98..H4`、`git diff --name-only 46c5684c98..H4` | 仅 `AGENTS.md`、runner/closure 脚本和测试、指定治理文档及 handoff；没有超预算生产或镜像输入改动。 |
| 代码与测试审阅 | 阅读 `test_input_closure.py`、`run-tests.sh`、两份 runner/closure 测试；用 `rg -n` 定位 dirty 检查、Docker mode、传递依赖、比较及包选择分支 | 逻辑和回归覆盖符合 G12 要求。审核者未运行测试或权威 runner。 |
| 证据日志审阅 | 通过 `ssh -o BatchMode=yes ct108-gw-dms` 读取 H4 manifest summary、preflight 和 RS identity 日志；审阅 handoff 引用的 V、H1、audit、static、demo 与 carried 日志 | 五包比较全可沿用且变化组件为空；RS label/image identity PASS；V/H1 来源与 runner 证据一致。 |
| Docker context 覆盖交叉检查 | 审阅 context 发现/摘要实现及参数化测试，并核对 ignored-path 清单摘要 | context、ignore、非 Git 输入及 tracked mode 均有覆盖；19,560 个 ignored paths 中 0 个会进入 context。 |

## 5. 验证限制与剩余前置

审核者没有在审核 worktree 重新运行测试、Dolt、Compose 或完整 runner；结论依据只读源码、handoff 与 `ct108-gw-dms` 上的既有权威日志。Python audit hook 只能证明文件被以相应 mode 打开，不能证明发生了 `read(2)` 或重建完整事件时序；报告按此边界解释计数，并核对唯一生成临时文件的 Hypothesis 源码写入路径。V/H 门禁、审计和 static 的原始记录保留在 `/home/dev/gdds-p5-closure-s1-gate-logs/`。本项真实数据范围为空；S4 尚未开始，后续阶段按其自身授权和门禁执行。

## 6. 复审记录

非复审；本次为 H4 的独立审核。原先发现的 closure mode/audit-accounting 缺口已在候选中修复并由最终实现、校正计数和 H4 对照证据覆盖，本次未发现遗留项。

## 7. 终审（2026-10-20）

终审方在开发主机上用只读方式核对区间与源码，通过 `ssh -o BatchMode=yes ct108-gw-dms` 读取原始日志，没有采信初审与 handoff 的结论。结论：**维持通过**，另有三项 finding；其中两项是规则问题，已由 owner 决议（DC34）。

### 7.1 核对结果

- 区间 `46c5684c98..13d97dc2db` 共 32 个提交，均带 trailer；V 之后只改文档；没有改动生产代码、Compose、Dockerfile、harness 或依赖。
- `g12-V7-runner-62a4122f9c-20261019T173659Z.log`：`clean_start=1`、`GATEWAY_TEST_PACKAGES=unset`、起止 HEAD 均为 V、`clean_end=1`、`runner_exit=0`；计数 242 / 152 / 154 / 2,839 + 36 / 1,715 + 1 skipped / 205，五包均 `status=passed`。
- `g12-selective-shared-kernel-V7-*.log` 只运行 `shared_kernel`，exit 0；`g12-H1-backend-runner-*.log` 在 clean H1 上只运行 backend（含 Compose 旅程），exit 0。
- `g12-H-final-manifests/summary.log`：在 H、初审报告提交 `ef4701ccc6` 与 tag 提交 `13d97dc2db` 上，五包 manifest 均与各自直接来源一致，变化组件为空。
- `g12-audit-v7/corrected-open-input-accounting.json`：五包闭包外输入路径均为 0，与 handoff §4 一致。
- `run-tests.sh` 未设置 `GATEWAY_TEST_PACKAGES` 时，包顺序、两遍拆分、`GATEWAY_TEST_BASETEMP` 处理与五锁检查不变；新增的是测试前的 env sync 与 manifest 计算。manifest 失败（含 dirty worktree）会使整次 runner 失败，与权威入口必须在 clean worktree 上运行的前提一致。
- `compare_manifests()` 核验 schema、`clean_worktree` 与总摘要后逐组件比较，只会报告变化，不会放宽。

### 7.2 Findings

#### G12-F1：manifest 记录了被测运行自己会重建的镜像 ID（实现缺陷；不阻塞；转入 S4 第一步）

- 位置：`vnext/scripts/test_input_closure.py` `_docker_build_inputs()` 的 `image_ids`。
- 事实：RS manifest 记录 `gateway-repository-client-e2e:local` 与 `gateway-repository-service:local` 的本机 ID，backend manifest 记录 `gateway-repository-service:local` 的 ID，都在 runner 开始时取值。client 镜像以 HEAD 为候选 label（`expected_build_metadata().candidate_sha`），每换一个提交运行 RS Compose 测试都会重建；RS 镜像在 identity 变化时由 harness 重建。
- 影响：来源 runner 一旦重建这两个镜像，后续任何提交的 manifest 都与来源不同，该包无法沿用；RS 在文档提交上重跑又会以新 HEAD 重建 client 镜像，无法收敛。只会多判“运行”，不会错误沿用。G12 的证据没有暴露它，是因为 V 的 runner 之前审计运行已在 V 上建好 `:local`（label `62a4122f9c`、ID `3133afd8…`，等于 V runner 起始 manifest 中的值）。
- 修正方向：这两个镜像只记录 tag 名与决定其内容的输入（`-base:local`、python base、RS dependency-base 的 ID），不记录自身 ID；补参数表测试，证明重建这两个镜像不改变 manifest，而输入镜像 ID 变化会改变 manifest。

#### G12-F2：专用节点上 carried 第 3 条无法满足（规则；owner 已决议）

- `g12-H1-carried-backend-worker.log`：同一 worktree、同一 project 名，连续两次全缓存构建，backend 为 `6ddfee83…` / `950f6d49…`，worker 为 `ecfd567d…` / `96ba2070…`，与 V provenance 也不同。节点 Docker 29.9.1 使用 containerd image store（`io.containerd.snapshotter.v1`）。原因推测为镜像 ID 取 manifest digest，buildx 默认 attestation 每次不同；未验证。
- G12 的退出实际依靠 H1 的 backend 实跑与 H1→H 的闭包相等，与当时 AGENTS.md 中“V..H 仍须单独满足镜像身份等价”不一致。
- owner 决议（DC34 第二部分）：backend/worker 的身份改用同一 worktree 中 backend manifest 逐项相等判定，不再比较 image ID。按此规则，G12 的 H 由 H1 实跑与 manifest 相等绑定，满足要求。

#### G12-F3：专用测试节点规则缺少 owner 决议记录（规则；owner 已决议）

- AGENTS.md 与 testing-conventions 新增“所有测试都在 `ct108-gw-dms` 上执行，不回退到开发主机”，决议记录中原本没有对应条目。owner 确认这是其要求，记为 DC34 第一部分。
- 规则中的 `TMPDIR` 位于 `gdds-p5-closure-s1-gate-logs/` 下，而 G10 第 2 项计划在 P5 exit 时归档或删除该目录；已在 G10 第 2 项中注明先迁移 `TMPDIR`。

### 7.3 其他

- 本报告的行尾空格已在合入后清除。
- 本项真实数据范围为空；S4 的区间起点为 `p5-g12-exit`，携带 G12-F1。

# P5 架构收口 G12 第 1 项独立审核

- 结论：**通过**
- 日期：2026-10-19
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

# P5 S4 — 项目身份与数据替换 handoff

## 1. 区间、提交与子步

- `range_start`：`p5-g12-exit`，`13d97dc2db5cef4bd82583ab7ac339ed09b5aec3`。
- kickoff base：`368163c1b02575c7f253bd73ee7b2f7c1ac510ea`。未合并或 rebase `main`。
- 实现 HEAD：`ed70ca1be262653bb49267940e73e7edd09a2267`。
- 门禁提交 `V`：`ed70ca1be262653bb49267940e73e7edd09a2267`。
- 候选 `H`：`p5-s4` 分支 tip 上仅包含本 handoff 的提交；准确 SHA 见本 handoff 最终提交和实现者交付消息。
- 审核通过前不开始 S5。没有 tag，也没有推送到 GitHub。

S4 子步与提交对应如下；每个提交均包含 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

| 子步 | 提交 |
| --- | --- |
| G12-F1：剔除 harness 自身会重建的镜像 ID | `8234294785` `refactor(p5-closure-s4): exclude rebuilt image IDs from manifests` |
| 项目身份 capability、比较/替换事实、Preview 与双侧 bundle | `3d3ab764ba`, `d03d33656c`, `d5d63fcc84`, `7ba92915cc` |
| Submit 身份确认、共享理由规则、授权和 exact-scope 顺序 | `f977c7b9a9`, `5bb6153968`, `216b6e8848`, `7797186308` |
| Archive 身份异常与 Review/Archive 行为 | `216ae69c22`, `b4ebacdce9`, `af3301a8e4` |
| Compose 身份旅程、fixture 绑定和同源投影对照 | `191197c40f`, `a46de2ee78`, `aec9684445`, `7e00092d14`, `5d1af74eb8` |
| 闭包稳定性、类型收敛与真实数据 harness | `98fd6c912b`, `a37f0ca144`, `3210d4eaae`, `9e70383ec1`, `150a2167f3`, `61541c270f`, `22c1a7e530` |
| worker 诊断、Submit 有界对账重试 | `83fe6a2bec`, `648436cfbb`, `fd0913e36b`, `3c3c7cb7c0`, `55f3d13979`, `77281259d8`, `bafd64bf53`, `22c1a7e530` |
| 修复 RS 测试共享连接竞争 | `ed70ca1be2` `test(p5-closure-s4): serialize shared control database test access` |

实施范围依据为执行计划 §2 S4、§3 S4，设计 §7.1–§7.7、§12、§14，ADR 0020，Business Lifecycle 3.1.0 身份条款，以及决议记录 DC28、DC30、DC33、DC34。第二次停止后的范围由 main 上 `8091397641`（治理修订计划 §3 第 11 项）授权；该提交只读核查，没有合并进本分支。

## 2. G12-F1 修复与调试证据

`vnext/scripts/test_input_closure.py` 的 manifest schema 从 7 升到 8。对 harness 按候选 label 重建的 `gateway-repository-client-e2e:local` 和 `gateway-repository-service:local` 只记录 tag 名，不记录这两个 tag 的本机 image ID。决定内容的输入镜像 ID 继续记录：Python base、Repository Service dependency-base、RS client dependency-base，以及 backend 的 Rust base。`test_test_input_closure.py` 用共享参数表覆盖：两个 harness 重建 tag 的 ID 变化不改变 manifest；输入镜像 ID 变化会改变 manifest。

ct108 调试证据：`s4-g12f1-client-compose-98fd6c912b.log` 在另一个 HEAD `98fd6c912b` 上通过一次真实 Compose client 用例，并将 `gateway-repository-client-e2e:local` 从原 image ID `sha256:3133afd89ce222836fa5428a53363091ecfbc9e9cc70ad81c938c55bce16fac3` 重建为 `sha256:befb5bbabb18e71425d8c7ac9fbc2c8b78b96fcc0577e660660c4bb0dcb17eec`，候选 revision label 为 `98fd6c912b`。回到 RS manifest 后，source HEAD `7e00092d14` 与 current HEAD `98fd6c912b` 的总摘要均为 `01b82d2a25536f4ea3a2e8b54bda71bd6c2b70e32a83d84da8b6db45137a4664`，compare 为“可沿用”，没有 changed components。证据在 `s4-g12f1-client-compose-post-98fd6c912b.log` 和 `s4-g12f1-rs-manifest-{before-7e00092d14,after-98fd6c912b}.json`。第一次 manifest 命令因该临时 worktree 缺 `rustc` 失败；补齐运行环境后重算成功，失败尝试没有作为证据。

`gateway-repository-client-e2e:local` 与 `gateway-repository-client-e2e-base:local` 均未手工 `docker rmi`、`docker tag` 或删除；client tag 的变化来自获准的 Compose 构建。

## 3. S4 实施、路径预算与 import_rules

按设计 §7 实施：身份规则在投影侧与 Repository 侧共用同一判定；比较加入替换事实；Preview 和 bundle 记录身份与双侧快照；Submit 冻结确认事实；Archive 可记录和处置身份异常。control DB 直接更新单一基线 schema，没有 migration。HTTP DTO 与 checkpoint 使用目标形态，没有旧字段别名或兼容读写。身份确认理由使用 Submission 领域共享校验的多行模式；Review 既有行为保持不变（DC28）。OpenAPI 和对应请求/响应 fixture 断言同步到新 DTO；没有新增独立 golden 文件。没有修改 Dockerfile、Compose、依赖或 lock。

`test_archive_compose_e2e.py` 复用既有 Compose 栈，覆盖跨项目替换、`UNVERIFIABLE` 和 FULL 混合模式（替换基线 pair 与 initial→modified 详细比较）。没有新建 Compose 栈。`test_review_transactions.py` 条件路径未启用。

超出原 §3 S4 预算的路径及原因：

| 路径 | 原因与授权 |
| --- | --- |
| `vnext/scripts/test_input_closure.py`、`vnext/repository_service/tests/test_test_input_closure.py` | G12-F1 修复必须同步改变 manifest 语义与验证；属于本轮 S4 的首个提交，且受 kickoff 明确授权。 |
| `vnext/backend/benchmarks/real_dump_journey.py`、`vnext/backend/tests/test_real_dump_journey.py` | 上一份恢复决议明确要求加入 heartbeat 停滞检测、先取证再拆栈、t4 scope 与确定性测试。 |
| `vnext/backend/src/gateway_backend/application/submit_jobs.py`、`vnext/backend/tests/test_submit_job_effect.py` | t4 Submit 在 60 s 对账会话结束后进入人工恢复且 operation 不终态；owner 决议 `cefd29398b` 授权在 S4 内修复 R5 重试。 |
| `vnext/repository_service/tests/support/control_db_harness.py` 和下表九个 RS 测试文件 | 22c1a7e530 的权威 runner 因已知共享连接竞争失败；owner 决议 `8091397641` 明确授权只在 RS tests 内修复并同类排查。无 production API 或代码改动。 |

RS 测试竞争修正涉及：

```text
vnext/repository_service/tests/support/control_db_harness.py
vnext/repository_service/tests/test_import_http.py
vnext/repository_service/tests/test_import_submission.py
vnext/repository_service/tests/test_import_worker.py
vnext/repository_service/tests/test_mutation_readiness.py
vnext/repository_service/tests/test_operation_http.py
vnext/repository_service/tests/test_settings.py
vnext/repository_service/tests/test_upload_artifact_integration.py
vnext/repository_service/tests/test_upload_artifact_visibility.py
```

`import_rules` 起点是 0 / 0 / 6；最终仍为 0 / 0 / 6（import violations / runtime cycles / unreachable modules），没有增加。每个子步结束的 focused 测试与 import_rules 记录留在 ct108 的 `s4-import-rules-*.log` 和各 focused log 中；最终日志为 `s4-import-rules-ed70ca1be2.log`。

## 4. 停滞事实、根因更正与修复

### 4.1 938d41d171 停止记录

V `938d41d171` 的 t4 v1 Preview 成功；v1 Submit 在 4,047 s 的 harness timeout 内没有终态，完整权威 runner exit 0，之后 t4 真实数据未通过。事实日志为 `s4-realdata-t4-identity-938d41d171.log`，Compose 日志位于 `s4-realdata-compose-logs/`。按 owner 在 `8091397641` 中的更正，原因不是 worker 卡死：`await_import_result` 的一个 60 s 对账会话到期后，step 转入 `MANUAL_RECOVERY_REQUIRED`；worker 随后空闲，而 harness 仍将父 operation 视为运行中，继续等到 4,047 s timeout。S3 V `dc9c08a410` 的对照也出现同一状态，说明这是既有的 operation 收敛缺陷，不是 S4 引入的回归。

### 4.2 停滞检测与诊断

检测器读取 worker `operation_worker_event code=heartbeat_succeeded` 日志事件；心跳周期 10 s，默认阈值 120 s，可由 `GATEWAY_REAL_DUMP_WORKER_STALL_SECONDS` 配置。只在操作运行期间监测。超过阈值时先写 `s4-stall-<UTC 时间戳>/`，再拆栈，并以 `worker_stalled` 独立于 timeout 返回。诊断采集覆盖 worker host PID、每线程 `/proc` 的 `comm/wchan/stack/status`、`py-spy dump --native`、三容器 inspect、RS 公开 import operation 状态、只读 control DB operation/step/lease 字段和全部容器日志。`test_real_dump_journey.py` 中的 `test_worker_heartbeat_log_resets_stall_clock_and_normal_heartbeats_do_not_trip` 用确定性日志流覆盖心跳推进与正常心跳不误触发；`test_worker_stall_monitor_tracks_nonterminal_status_after_running` 覆盖运行中的阈值检测；`test_worker_stall_diagnostics_precede_teardown_and_have_distinct_failure_reason` 覆盖诊断先于拆栈及独立失败原因；`test_worker_stall_diagnostics_capture_nested_repository_operation_status` 覆盖 RS 状态采集；`test_operation_timeout_remains_distinct_from_worker_stall` 覆盖 timeout 区分。测试不依赖真实时间。

10 月 20 日两份诊断为：

- `s4-stall-20261020T132915988408Z/`：control DB 中父 operation 和 `await_import_result` 均为 `MANUAL_RECOVERY_REQUIRED`，`attempt_count=1`、无 owner/lease；Repository 公开 API 返回 HTTP 200、import operation `SUCCEEDED`。46 个 worker 线程的内核等待点均为 `futex_do_wait`；py-spy 的 Python-only 栈显示主线程在 `worker_runtime._wait_interruptibly` 等待新工作。没有线程停在 HTTP socket、数据库锁或 Python 互斥锁上。
- `s4-stall-20261020T151720059085Z/`（S3 V 对照）：同样是 `MANUAL_RECOVERY_REQUIRED`、`await_import_result`、无 lease；100 个线程处于 `futex_do_wait`。本次采集的 `worker_stalled` 标签是检测器对“无心跳”的分类，不是根因；按 owner 更正，它反映 worker 已因人工恢复状态空闲。
- 两次 `py-spy dump --native` 均因 `UNW_EBADREG: bad register number` 无法拆 native/Python 栈，错误保存在 `py-spy-pid-*.txt`。仍继续保留 `/proc` 线程数据、control DB 与公开 RS 状态、容器 inspect 和日志；第一份另有成功的 Python-only dump。

### 4.3 调试运行和修复

所有调试日志均在 ct108，诊断文件留在日志目录，没有进入 Git。运行记录：

| 运行 | 结果、时长与诊断 |
| --- | --- |
| `s4-debug-stall-t4-v1-submit-attempt1-fd0913e3.log` | 作废的启动尝试，遇到 `NameError: COMPOSE_FILE is not defined`，未运行真实 Preview/Submit，也无 Compose 栈；`journey_exit_code=1`。 |
| `s4-debug-stall-t4-v1-submit-valid1-3c3c7cb7.log` | S4 调试 V 的 t4 v1 Preview 1,675.744 s 成功；Submit 启动后运行约 1,528 s 被外部中断（exit 130），没有作为通过证据。诊断目录 `s4-stall-20261020T132915988408Z/`；见上文状态更正。 |
| S3 `dc9c08a410` 初次 overlay 尝试 `s4-debug-stall-s3-t4-v1-submit-dc9c08a410.log` | 作废的测试/overlay 启动尝试，未形成可用真实数据结果；完整日志保留。 |
| S3 V overlay rerun `s4-debug-stall-s3-t4-v1-submit-dc9c08a410-rerun.log` | Preview 1,693.764 s 成功；S3 没有 S4 的 identity assessment digest，harness 在 Submit 前以 digest invalid 退出，未用于判断根因。 |
| S3 V 对照 `s4-debug-stall-s3-t4-v1-submit-dc9c08a410-rerun2.log` | Preview 1,693.796 s；Submit 在 120.222 s 后被检测器标记，诊断目录 `s4-stall-20261020T151720059085Z/`。control DB/RS 状态证明这是 60 s 会话到期后的人工恢复和空闲 worker，依 `8091397641` 更正为非卡死。 |
| S4 修复前后聚焦调试 `s4-debug-stall-reconcile-fix-bafd64bf.log` | 修复后 t4 v1 Preview 1,693.847 s，Submit operation 574.474 s 终态 `SUCCEEDED`，整段 PASS。 |
| 修复负向测试 `s4-debug-stall-reconcile-negative-4a02bea8.log` | 临时撤掉 bafd64bf53 的重试修复后，`test_await_import_result_timeout_retries_until_repository_operation_is_terminal` 失败；恢复修复后 focused 测试通过。 |

`bafd64bf53` 在 60 s 单次 poll timeout 后调用现有 R5 `transition_for_outcome(RECONCILE_PENDING, ...)`，进入 checkpointed retry；由既有预算限制最多 3 个 60 s 会话，用尽后仍走人工恢复路径。它不是延长 timeout 或自动重启 worker。传入的 `reconcile_elapsed_seconds=0.0` 是否会重置/绕过累计耗时预算、是否与 R5 原规则一致，作为独立强制审核项，不在 handoff 中替 reviewer 作结论。

## 5. 22c1a7e530 runner 失败与 RS 测试修复

第二次停止：V `22c1a7e530` 的完整五包 runner exit 1，日志 `s4-v-runner-22c1a7e530.log`。失败为 `repository_service/tests/test_upload_artifact_visibility.py::test_ready_file_without_db_is_not_visible`：`sqlite3.OperationalError: cannot commit - no transaction is active`。同一用例、同一行在 2026-09-27 开发主机 `run-tests-r2.log` 曾出现，属既有偶发失败；其余包通过。根据 `8091397641`，22c1a7e530 不能作为任何包的沿用来源。

根因是测试绕过 `transaction_lock`，对与 app 后台线程共享的 `runtime.mutation_store._connection` 执行 DELETE 和 commit，与后台线程事务竞争。修正后，在测试持有 store `transaction_lock` 时通过明确的 `BEGIN IMMEDIATE`、DELETE、COMMIT（失败则 rollback）删除记录。断言仍证明“已发布文件存在，但 DB 记录缺失时 artifact 不可见”；没有新增 production API。

按 owner 要求在 `vnext/repository_service/tests/` 全量搜索直接访问 `_connection` / control store 共享连接，并区分写入与 app 运行时读取：

```bash
rg -n '(_connection|control_store\.connection|env\.control_store\.connection|runtime\.control_store\.connection|\.mutation_store\._connection|\.import_store\._connection)' vnext/repository_service/tests --glob '*.py'
rg -n '(_connection\.execute|_connection\.commit|connection\.execute|connection\.commit)' vnext/repository_service/tests --glob '*.py'
```

逐项审查了命中：测试应用运行期间与后台线程共享连接且未持锁的读写一并改为在 store 锁下执行；其余访问属于已加锁、独立测试连接、app 启动前或不与后台线程并行的 fixture。改动文件见 §3 九文件清单。

在 ct108 上不添加 `pytest-repeat` 依赖，以 shell 重复方式分两批、每批 8 个并发 pytest 进程，共 16 次运行该用例；16 份日志 `s4-rs-repeated-ed70ca1be2-1.log` 至 `-16.log` 均为 1 passed。共享连接 focused 用例 12 passed（`s4-rs-focused-shared-connection-ed70ca1be2.log`），worker 锁 focused 用例 3 passed（`s4-rs-focused-worker-lock-ed70ca1be2.log`），RS `-m unit` 为 1,534 passed、1 skipped（`s4-rs-unit-ed70ca1be2.log`）；涉及的 integration 用例通过。

## 6. 子步验证与静态检查

- V 前 focused/RS unit 的 preflight 均记录 ct108 load、Dolt 进程、Compose project、全部容器及 8000 端口；相关日志 `s4-preflight-rs-test-ed70ca1be2.log`、`s4-preflight-rs-unit-ed70ca1be2.log`。测试只在 ct108 执行。
- `import_rules` 最终 0 / 0 / 6，exit 0：`s4-import-rules-ed70ca1be2.log`。
- 五包 ruff 与 mypy 均通过，日志 `s4-static-five-packages-ed70ca1be2.log`：shared_kernel 34 source files、repository_contracts 15、repository_client 26、backend 483、repository_service 200；无 ruff 或 mypy 错误。
- 运行依赖只通过受控 `uv-consume.sh` / 权威 runner 使用；五个 lock 未改。

验收 owner 与实际验证入口：身份投影和 Repository 行为分别由各自领域测试持有，跨边界身份判断由 `test_archive_compose_e2e.py` 持有；worker 诊断由 `vnext/backend/tests/test_real_dump_journey.py` 持有（含 §4.2 列出的五个测试）；artifact 可见性不变量由 `test_ready_file_without_db_is_not_visible` 持有。ct108 上的命令入口及结果如下：

| 验收 | 命令 | 结果 / 日志 |
| --- | --- | --- |
| RS 可见性竞争复现与并行重复 | `cd vnext/repository_service && ../scripts/uv-consume.sh -C . run pytest -p no:randomly -n 8 tests/test_upload_artifact_visibility.py::test_ready_file_without_db_is_not_visible`；通过 shell 分 16 次调用，不安装 `pytest-repeat` | 16/16 次各 1 passed；`s4-rs-repeated-ed70ca1be2-{1..16}.log` |
| RS unit | `cd vnext/repository_service && ../scripts/uv-consume.sh -C . run pytest -m unit` | 1,534 passed、1 skipped；`s4-rs-unit-ed70ca1be2.log` |
| 架构导入规则 | `cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules` | 0 / 0 / 6；`s4-import-rules-ed70ca1be2.log` |
| 五包静态检查 | 对 `shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service` 分别执行 `../scripts/uv-consume.sh -C . run ruff check .` 和 `../scripts/uv-consume.sh -C . run mypy` | 五包均通过；`s4-static-five-packages-ed70ca1be2.log` |
| 权威 runner | `GATEWAY_TEST_PACKAGES=backend,repository_service GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh` | exit 0；`s4-v-runner-ed70ca1be2.log` |
| t4、跨项目、t1 真实数据 | `python -m benchmarks.real_dump_journey --tier t4 --scope t4-identity`；`python -m benchmarks.real_dump_journey --cross-project`；`python -m benchmarks.real_dump_journey --tier t1 --scope full`（从 `vnext/backend` 通过 `uv-consume.sh -C . run` 启动） | 均 PASS；各日志见 §8.1。 |

## 7. V 权威 runner、计数与镜像记录

### 7.1 按包来源和 runner

在运行 `938d41d171` 的同一个 ct108 worktree `/home/dev/gdds-p5-s4` 中比较五包 manifest。新 V 的前三包与 938d 完全一致，沿用 938d；backend 与 repository_service 闭包变化，在 V 上实际运行。22c 的失败 runner 不作为来源。

| 包 | 938d manifest → V manifest | 处置与来源 |
| --- | --- | --- |
| shared_kernel | `c17741f99a8f62d6564fac4cc7abef43b922bd8b345ea7bfbcd602c846c7e44e` → 相同 | 可沿用 938d；938d 包通过且整次 runner exit 0。 |
| repository_contracts | `aca07576becbe8cee5a24b4d74c5577a0874263054bd7b37bd773796b2ba7657` → 相同 | 可沿用 938d。 |
| repository_client | `4b7fd4989420e4457f9e6a8dea018810647c2c582e8465892b575e145a0c2f1b` → 相同 | 可沿用 938d。 |
| backend | `93fbe070a48ee9866761a50057a2dcdeabd1cc8f8174cf29ce1d2ae69a26605c` → `a7f4ccc910ecf7502740fd080aafbc520ca0c8ded8e70415f46fc950cba62473` | 运行；Docker `vnext/` context、tracked mode、Hypothesis/cache 与 package digest 变化。 |
| repository_service | `67dc6b8d299fdfd6f58eeebc42bbb000aaed5a1526f8886f76fc6ff99c1f0b52` → `33cc2fe2919184c7951fad1eb742845c47e6429d8652dd1d48759d4ac024b941` | 运行；Docker `vnext/` context、tracked mode、pytest cache 与 package digest 变化。 |

逐包 compare 汇总在 `s4-manifest-summary-ed70ca1be2.log`、`s4-manifest-compare-ed70ca1be2.log`；五包 V manifests 在 `s4-manifest-ed70ca1be2/`。V runner 的 backend 与 RS 起始 manifest 在 `s4-v-runner-ed70ca1be2.log`。

命令及结果：

```bash
GATEWAY_TEST_PACKAGES=backend,repository_service GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

ct108 日志 `s4-v-runner-ed70ca1be2.log` 记录起止 HEAD 均为 V、clean worktree、五锁检查、所选包的起始 manifest 和 `runner_exit_code=0`。V preflight 为 `s4-v-preflight-ed70ca1be2.log`：没有 Dolt、Compose 栈或容器，8000 端口空闲，并记录了 load 和全部容器清单。按 compare 只运行 backend 与 repository_service；其他三包直接沿用 938d。

| 包 | G12 V `62a4122f9c` | 938d V | 22c1 V（runner exit 1） | 新 V `ed70ca1be2` |
| --- | ---: | ---: | ---: | ---: |
| shared_kernel | 242 passed | 242 passed | 242 passed | 沿用 938d：242 passed |
| repository_contracts | 152 passed | 152 passed | 152 passed | 沿用 938d：152 passed |
| repository_client | 154 passed | 154 passed | 154 passed | 沿用 938d：154 passed |
| backend 并行 / serial | 2,839 + 36 passed | 2,894 + 36 passed | 2,901 + 36 passed | 2,901 + 36 passed |
| repository_service 并行 / skipped / serial | 1,715 + 1 skipped + 205 passed | 1,724 + 1 skipped + 205 passed | 1,723 passed + 1 failed + 1 skipped + 205 passed | 1,724 + 1 skipped + 205 passed |

计数变化：三个可沿用包均无变化。backend 相比 G12 增 62、相比 938d 增 7、相比 22c 不变。RS 相比 G12 增 9、相比 938d 不变；22c 与新 V 收集数相同，原来失败的 1 项在修复后变为通过。G12 对照来自 `g12-V7-runner-62a4122f9c-20261019T173659Z.log`；938d、22c、新 V 分别见对应 `s4-v-runner-*.log`。

### 7.2 provenance 与 image record

```text
Current HEAD: ed70ca1be262653bb49267940e73e7edd09a2267
Container rebuild required: yes
Reason: S4 修改 backend / repository-service 容器测试输入，且 V 权威 runner 在 backend、RS 批次运行 Compose journey。
Last verified image revision: ed70ca1be262653bb49267940e73e7edd09a2267
Last verified source-tree/image identity: repository-service label source-tree sha256:a3e56c4d90e67ba80b632599ead9dca8fc65d13d2193ad0f42472d9a9f68be3a
Container gate for current HEAD: passed (backend 与 RS 在 V runner 中运行)
Carried from: 无；backend 与 RS 在 V 上运行，另三包按包 manifest 沿用 938d
Deferred gates/nodeids: 无
Required execution point: S4 V 已完成；V..H 按 DC34 核验 carried
```

runner 起始环境摘要：Docker 29.9.1、Compose 5.6.0、`linux/x86_64 overlayfs`、Python 3.14.6、Dolt 2.1.11、uv 0.11.28、rustc 1.97.0。manifest 记录输入 ID：Python base `sha256:1207cca291a30bc7f4125ed627edb22256cdcdc05bfbe3fb3b6c9544cc19fe4b`，Repository dependency-base `sha256:63b7e79899d4379f24a1d58f0e22e1960847733a76e684dd170b8e631e00367f`，client dependency-base `sha256:ba6c64db44f5f5b7f573fb1df6295c11a5c9e20d9c188189921e717a623ff38c`，Rust base `sha256:99709b7838d7ca5a59028a462348daf3ee413e3a4b05e3c8a3954b13c1247986`。manifest 对 `gateway-repository-service:local` 与 `gateway-repository-client-e2e:local` 只记 tag、不记自身 ID；没有记录被测运行会重建的本机 ID。

V Compose 的 `gateway-repository-service:local` image ID 为 `sha256:432529419b082ff3fd1a15af3263aaeb17db5cda29761089714b3309bf73ec28`，label revision/build-input revision 为 V，source-tree 为上述 digest。client e2e 的本机 tag 在 RS Compose 中由 V 重建；其 post-run image ID 为 `sha256:c24a208585a4f8b6838ae399895a7a4759f555a2582bd616a780ba15132e4b04`，revision label 为 V。image ID 仅作运行记录，不进入自身 manifest 闭包。未手工删除或重新 tag 镜像。

## 8. 真实数据与 S3 对照

数据在 ct108 的 `$GATEWAY_REAL_DUMP_ROOT`，`packages/` 和 `datasets.json` 均存在；V 的输入验证为 `INPUTS_VALID`，日志 `s4-realdata-inputs-938d41d171.log` 与 `s4-realdata-preflight-ed70ca1be2.log`。未读取或输出原始行内容。下面只记录 dataset ID、SHA-256、包大小和结构统计。

| Dataset ID | SHA-256 | bytes | source tables | rows | pseudo rows |
| --- | --- | ---: | ---: | ---: | ---: |
| rd-t1-a-v1 | `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2` | 107,115 | 133 | 6,097 | 4 |
| rd-t1-a-v2 | `4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0` | 107,066 | 133 | 6,095 | 4 |
| rd-t2-b-v1 | `acd1b5e6f92083c3a6d53e9996be0bf46f520ae7fdea94d8449069748a3817c0` | 1,247,459 | 217 | 97,140 | 3,056 |
| rd-t2-b-v2 | `c66e3921c7774a38bfeb2f407c24a39209225e962f593ec88d17db0d85fcba98` | 1,197,404 | 217 | 93,154 | 2,674 |
| rd-t3-c-v1 | `c34e266c458d9b2cfb630fec56fa7c893113e11b56f768710aecebb0715eec7e` | 3,356,815 | 200 | 268,661 | 9,858 |
| rd-t3-c-v2 | `658422efd2583963cc04bdff6e88e2b733d33396bdd92ff5b3635dc00cffc28d` | 3,370,171 | 201 | 268,667 | 9,858 |
| rd-t4-d-v1 | `95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675` | 5,597,503 | 320 | 437,149 | 12,676 |
| rd-t4-d-v2 | `5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611` | 5,596,595 | 320 | 437,229 | 12,688 |

### 8.1 新 V 真实数据结果

三次实际运行均在 ct108 的 V worktree 中通过 `vnext/scripts/uv-consume.sh -C vnext/backend run python -m benchmarks.real_dump_journey` 启动，分别使用以下参数；日志文件名见各条结果：

```bash
python -m benchmarks.real_dump_journey --tier t4 --scope t4-identity
python -m benchmarks.real_dump_journey --cross-project
python -m benchmarks.real_dump_journey --tier t1 --scope full
```

日志均绑定 clean V，真实数据前 preflight 记录 node load、Dolt、Compose、全部容器和 8000 端口；运行后 `s4-postflight-realdata-ed70ca1be2.log` 再次确认工作区 clean、没有 Dolt/Compose/容器，端口空闲，`POSTFLIGHT_HARD_CONDITIONS=PASS`。

- **t4**：`s4-realdata-t4-identity-ed70ca1be2.log`，scope `t4-identity`，总计 3,799.369 s。v1 Preview / Submit、v1 Repository read / approve / archive、v2 Preview 完成；不运行 t4 重传或 History。v1 Preview `312 tables / 312 changed`，degraded/failed 均 0；v1 Catalog read 验证 `312 tables / 246,794 rows`（扣除 435 composite 后 246,359，符合 S3 基线）。offline composite `435 → 435`，`UNCHANGED`，added/removed/modified/History record 差均为 0。v2 Preview 为 `SAME_PROJECT`、`DETAILED`，`312 / 26 changed`，degraded/failed 为 0，composite 435。Preview operation `SUCCEEDED` 用时 1,677.773 s；v1 Submit operation `SUCCEEDED` 用时 **576.497 s**；v2 Preview `SUCCEEDED` 用时 1,463.100 s。无 worker_stalled、timeout、HTTP 500 或人工恢复状态。
- **t4 v1 Submit 对账细节**：backend operation `operation_wall_seconds=576.497`（step wall 578.201 s）；RS import operation 从公开 API/step 与只读 metadata 记录得 elapsed 79 s，状态 `SUCCEEDED`。`prepare_import` 1 attempt、`submit_import` 1 attempt；`await_import_result` 使用 2 个 R5 对账会话（每会话最多 60 s），`attempt_count=2`，最多 3 个会话，余 1 个会话（60 s）。与 S3 完成的同一步 800.757 s 比，快 224.260 s；本次仍比 S3 更快。来源是 worker `heartbeat_succeeded` 事件、operation `step_succeeded`/attempt metadata 与 RS operation 状态字段；没有读取真实行内容。余量不为 0，未触发本次 stop 条件，但 S5 完整 t4 是否有足够余量交审核/owner判断。
- **跨项目**：`s4-realdata-cross-project-ed70ca1be2.log`，t1 v1 建基线后上传 t2 v1；source Preview、Submit、approve/archive 成功。replacement Preview 为 `DIFFERENT_PROJECT` / `DATASET_REPLACEMENT`，`211 tables / 211 changed`，degraded/failed 为 0；带确认 Submit、Review、带理由处置和 Archive 均完成；整段 603.615 s，PASS。
- **t1 完整冒烟**：`s4-realdata-t1-full-ed70ca1be2.log`，总计 373.269 s。v1 Preview `125 / 125 changed`，Catalog `125 tables / 3,733 rows`（含 composite 4）；v1 approve/archive 成功。v1 重传 Preview `125 / 0 changed`，Submit 为 `NO_CANONICAL_CHANGE`。v2 Preview `125 / 4 changed`，身份 `SAME_PROJECT`；Catalog `125 / 3,731 rows`（含 composite 4）；Submit/approve 成功。History `record_count=12`，composite `4`，unchanged，History composite record 差 0。所有 operation 都 `SUCCEEDED`。
- **t2、t3 沿用**：沿用 `938d41d171` 的通过结果，来源日志 `s4-realdata-t2-938d41d171.log`、`s4-realdata-t3-938d41d171.log`。S4 区间 `938d41d171..V` 的文件清单在 §8.3；没有触及 projection、comparison、project identity、composite、canonical storage 或 census 业务路径。t2 v1/v2 Preview 为 `209/209`、`220/57 changed`，Catalog 为 `209/73,693`、`220/68,909`，composite 45，History 11,511；t3 v1/v2 Preview 为 `192/192`、`193/54 changed`，Catalog 为 `192/122,452`、`193/122,458`，composite 201，History 744。两个来源日志各自逐档 PASS，且 t2/t3 的 v1→v2 为 `SAME_PROJECT`。

与 S3 结果对照：t1 新 V 的 Preview、Catalog、History、composite 汇总与 S3 V `dc9c08a410` 一致；t4 新 V 已实测的 v1 Preview/Catalog 与 v2 Preview/composite 分别为 312/312、312 tables/246,794 rows、312/26、435，与 S3 一致。受本次 t4 范围限制，t4 v2 Submit、v2 Catalog 与 History 没有在新 V 重跑；S3 V 的 History 168 / composite 435 留作对照，不当作新 V 实测。t2/t3 的具体 S3 汇总见 S3 handoff §8–§10，new V 的 938d 逐档运行继续符合这些值。t1/t4 对照 S3 `dc9c08a410`；t2/t3 对照 S3 `f73deee604`。A/B/C 数据逐步记录见 §9。

### 8.2 938d..V 文件清单与 t2/t3 carried 依据

```text
vnext/backend/benchmarks/real_dump_journey.py
vnext/backend/src/gateway_backend/application/submit_jobs.py
vnext/backend/tests/test_real_dump_journey.py
vnext/backend/tests/test_submit_job_effect.py
vnext/repository_service/tests/support/control_db_harness.py
vnext/repository_service/tests/test_import_http.py
vnext/repository_service/tests/test_import_submission.py
vnext/repository_service/tests/test_import_worker.py
vnext/repository_service/tests/test_mutation_readiness.py
vnext/repository_service/tests/test_operation_http.py
vnext/repository_service/tests/test_settings.py
vnext/repository_service/tests/test_upload_artifact_integration.py
vnext/repository_service/tests/test_upload_artifact_visibility.py
```

该区间只含 worker diagnosis/realdata harness、Submit bounded reconcile 和 RS tests 锁定，不改投影、比较、项目身份、composite 物化、规范存储或 census 的业务实现。故按 owner 条件保留 938d 的 t2/t3 逐档结果。

## 9. A/B/C 逐步 wall 与 CPU

以下数据均来自 CT108 日志的 `step_succeeded` 事件。Wall 是 journey step wall；CPU 列依次为 backend / repository-service / worker。A 对 operation 行列出公开 operation wall 与终态；C 表示起止时间与三个容器 CPU 已记录。B 只报告可见的运行现象，不把本轮测量扩张成 S5 性能结论。t2/t3 是沿用的 938d 证据。

### t4 identity scope（new V）

| Step | Wall s | Backend CPU s | RS CPU s | Worker CPU s | A |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.650 | 0.008 | 0.001 | 0.002 | — |
| v1-upload | 0.843 | 0.183 | 0.095 | 0.002 | — |
| v1-preview | 1,678.457 | 38.217 | 35.616 | 1,643.478 | SUCCEEDED, operation 1,677.773 s |
| v1-submit | 578.201 | 14.904 | 179.815 | 483.310 | SUCCEEDED, operation 576.497 s |
| v1-repository-read | 74.329 | 1.660 | 183.101 | 0.125 | Catalog assertion passed |
| v1-approve | 0.652 | 0.010 | 0.001 | 0.002 | — |
| v1-archive | 0.695 | 0.029 | 0.001 | 0.000 | — |
| v2-workspace | 0.636 | 0.103 | 0.100 | 0.000 | — |
| v2-upload | 0.862 | 0.188 | 0.002 | 0.002 | — |
| v2-preview | 1,463.782 | 33.704 | 126.608 | 1,389.798 | SUCCEEDED, operation 1,463.100 s |

### 跨项目 t1→t2（new V）

| Step | Wall s | Backend CPU s | RS CPU s | Worker CPU s | A |
| --- | ---: | ---: | ---: | ---: | --- |
| cross-source-workspace | 0.655 | 0.009 | 0.001 | 0.002 | — |
| cross-source-upload | 0.658 | 0.013 | 0.051 | 0.000 | — |
| cross-source-preview | 42.828 | 1.071 | 0.874 | 26.318 | SUCCEEDED, operation 42.153 s |
| cross-source-submit | 43.361 | 1.410 | 50.512 | 8.993 | SUCCEEDED, operation 42.189 s |
| cross-source-approve | 0.646 | 0.009 | 0.095 | 0.000 | — |
| cross-source-archive | 0.685 | 0.034 | 0.001 | 0.000 | — |
| cross-replacement-workspace | 0.630 | 0.004 | 0.001 | 0.000 | — |
| cross-replacement-upload | 0.707 | 0.045 | 0.001 | 0.000 | — |
| cross-replacement-preview | 313.763 | 7.177 | 74.602 | 258.832 | SUCCEEDED, operation 313.093 s |
| cross-replacement-submit | 198.098 | 5.213 | 112.614 | 131.958 | SUCCEEDED, operation 196.856 s |
| cross-replacement-approve | 0.644 | 0.006 | 0.001 | 0.000 | — |
| cross-replacement-archive | 0.694 | 0.027 | 0.001 | 0.002 | — |

### t1 full（new V）

| Step | Wall s | Backend CPU s | RS CPU s | Worker CPU s | A |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.641 | 0.008 | 0.001 | 0.002 | — |
| v1-upload | 0.666 | 0.012 | 0.068 | 0.000 | — |
| v1-preview | 42.827 | 1.069 | 0.876 | 26.663 | SUCCEEDED, operation 42.155 s |
| v1-submit | 43.356 | 1.417 | 50.170 | 8.999 | SUCCEEDED, operation 42.191 s |
| v1-repository-read | 21.232 | 0.408 | 47.183 | 0.032 | Catalog assertions passed |
| v1-approve | 0.653 | 0.106 | 0.001 | 0.002 | — |
| v1-archive | 0.682 | 0.034 | 0.001 | 0.000 | — |
| repeat-v1-workspace | 0.633 | 0.005 | 0.001 | 0.000 | — |
| repeat-v1-upload | 0.665 | 0.012 | 0.001 | 0.000 | — |
| repeat-v1-preview | 62.887 | 1.429 | 24.930 | 30.277 | SUCCEEDED, operation 62.224 s |
| repeat-v1-submit | 0.643 | 0.007 | 0.077 | 0.000 | NO_CANONICAL_CHANGE |
| v2-workspace | 0.635 | 0.005 | 0.001 | 0.000 | — |
| v2-upload | 0.683 | 0.014 | 0.001 | 0.000 | — |
| v2-preview | 66.905 | 1.549 | 25.037 | 30.246 | SAME_PROJECT, SUCCEEDED 66.237 s |
| v2-submit | 45.295 | 1.439 | 61.828 | 9.174 | SUCCEEDED, operation 44.200 s |
| v2-repository-read | 21.118 | 0.411 | 48.163 | 0.034 | Catalog assertions passed |
| v2-approve | 0.647 | 0.006 | 0.001 | 0.000 | — |
| history | 62.848 | 1.409 | 49.609 | 22.113 | SUCCEEDED, operation 62.184 s; record_count 12 |

### t2 carried from 938d V

| Step | Wall s | Backend CPU s | RS CPU s | Worker CPU s | A |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.654 | 0.008 | 0.001 | 0.002 | — |
| v1-upload | 0.689 | 0.045 | 0.001 | 0.000 | — |
| v1-preview | 492.396 | 11.270 | 10.374 | 461.665 | SUCCEEDED, operation 491.716 s |
| v1-submit | 196.256 | 5.257 | 105.414 | 134.372 | SUCCEEDED, operation 194.844 s |
| v1-repository-read | 44.935 | 0.933 | 109.214 | 0.078 | Catalog assertions passed |
| v1-approve | 0.654 | 0.010 | 0.001 | 0.000 | — |
| v1-archive | 0.686 | 0.030 | 0.001 | 0.000 | — |
| repeat-v1-workspace | 0.624 | 0.005 | 0.001 | 0.002 | — |
| repeat-v1-upload | 0.707 | 0.043 | 0.001 | 0.000 | — |
| repeat-v1-preview | 414.096 | 9.506 | 60.826 | 366.518 | SUCCEEDED, operation 413.435 s |
| repeat-v1-submit | 0.636 | 0.007 | 0.001 | 0.000 | NO_CANONICAL_CHANGE |
| v2-workspace | 0.633 | 0.006 | 0.001 | 0.000 | — |
| v2-upload | 0.702 | 0.033 | 0.001 | 0.000 | — |
| v2-preview | 468.305 | 10.775 | 62.286 | 416.871 | SAME_PROJECT, SUCCEEDED 467.635 s |
| v2-submit | 188.164 | 5.092 | 119.517 | 130.099 | SUCCEEDED, operation 186.800 s |
| v2-repository-read | 46.333 | 0.937 | 113.934 | 0.085 | Catalog assertions passed |
| v2-approve | 0.648 | 0.006 | 0.001 | 0.002 | — |
| history | 343.644 | 7.698 | 116.531 | 270.957 | SUCCEEDED, operation 342.971 s; record_count 11,511 |

### t3 carried from 938d V

| Step | Wall s | Backend CPU s | RS CPU s | Worker CPU s | A |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.658 | 0.009 | 0.001 | 0.002 | — |
| v1-upload | 0.779 | 0.117 | 0.099 | 0.000 | — |
| v1-preview | 823.497 | 18.799 | 17.440 | 795.070 | SUCCEEDED, operation 822.818 s |
| v1-submit | 342.849 | 8.692 | 107.843 | 282.086 | SUCCEEDED, operation 341.474 s |
| v1-repository-read | 41.189 | 0.825 | 97.722 | 0.075 | Catalog assertions passed |
| v1-approve | 0.650 | 0.010 | 0.001 | 0.000 | — |
| v1-archive | 0.675 | 0.029 | 0.001 | 0.000 | — |
| repeat-v1-workspace | 0.628 | 0.005 | 0.001 | 0.002 | — |
| repeat-v1-upload | 0.799 | 0.216 | 0.001 | 0.000 | — |
| repeat-v1-preview | 893.756 | 20.511 | 74.604 | 841.184 | SUCCEEDED, operation 893.085 s |
| repeat-v1-submit | 0.645 | 0.007 | 0.001 | 0.000 | NO_CANONICAL_CHANGE |
| v2-workspace | 0.625 | 0.005 | 0.001 | 0.000 | — |
| v2-upload | 0.795 | 0.121 | 0.001 | 0.000 | — |
| v2-preview | 1,008.178 | 23.137 | 76.921 | 948.950 | SAME_PROJECT, SUCCEEDED 1,007.501 s |
| v2-submit | 354.829 | 8.893 | 121.757 | 292.773 | SUCCEEDED, operation 353.503 s |
| v2-repository-read | 40.900 | 0.830 | 102.283 | 0.061 | Catalog assertions passed |
| v2-approve | 0.656 | 0.006 | 0.001 | 0.000 | — |
| history | 624.433 | 14.010 | 129.997 | 539.090 | SUCCEEDED, operation 623.765 s; record_count 744 |

B-layer observation: operation wall and all three cgroup CPU counters were captured. No run showed wall time materially above aggregate service/worker CPU that would support a new idle-wait finding. t4 v1 Submit step was 578.201 s with 678.029 aggregate CPU seconds, including RS import work; the separate R5 session margin is called out in §8.1. No S4 performance claim is made beyond these measurements; remaining capacity analysis belongs to S5.

## 10. Carried 到 H 與同步方式

V 的 manifest 来源及 runner 日志见 §7.1。按 DC34，carried 只在运行 V runner 的同一个 ct108 worktree `/home/dev/gdds-p5-s4`、检出 H 后判定：

- repository-service：H 上用 `python3 -I vnext/repository_service/tests/support/build_context_digest.py identity` 重算。H 的 `build_input_revision=ed70ca1be262653bb49267940e73e7edd09a2267`、`source_tree_sha256=sha256:a3e56c4d90e67ba80b632599ead9dca8fc65d13d2193ad0f42472d9a9f68be3a`，与 V 镜像的 `gateway.p2r1.build-input-revision`、`gateway.p2r1.source-tree-sha256` 两个 label 相同；按 DC34 不比较 image ID。记录在 `/home/dev/gdds-p5-closure-s1-gate-logs/s4-h-carried-identity-final.log`。
- 五包：均在 H 上执行 `python3 -I vnext/scripts/test_input_closure.py manifest --package <package>`，再用 `compare` 对应最初实际运行并通过的 V 起始 manifest。结果如下；changed components 均为空。

| 包 | 来源 V | 来源总摘要 | H 总摘要 | compare |
| --- | --- | --- | --- | --- |
| shared_kernel | `938d41d1714fcd3f04d8125f61e742a17a6f536d` | `c17741f99a8f62d6564fac4cc7abef43b922bd8b345ea7bfbcd602c846c7e44e` | `c17741f99a8f62d6564fac4cc7abef43b922bd8b345ea7bfbcd602c846c7e44e` | 可沿用 |
| repository_contracts | `938d41d1714fcd3f04d8125f61e742a17a6f536d` | `aca07576becbe8cee5a24b4d74c5577a0874263054bd7b37bd773796b2ba7657` | `aca07576becbe8cee5a24b4d74c5577a0874263054bd7b37bd773796b2ba7657` | 可沿用 |
| repository_client | `938d41d1714fcd3f04d8125f61e742a17a6f536d` | `4b7fd4989420e4457f9e6a8dea018810647c2c582e8465892b575e145a0c2f1b` | `4b7fd4989420e4457f9e6a8dea018810647c2c582e8465892b575e145a0c2f1b` | 可沿用 |
| backend | `ed70ca1be262653bb49267940e73e7edd09a2267` | `a7f4ccc910ecf7502740fd080aafbc520ca0c8ded8e70415f46fc950cba62473` | `a7f4ccc910ecf7502740fd080aafbc520ca0c8ded8e70415f46fc950cba62473` | 可沿用 |
| repository_service | `ed70ca1be262653bb49267940e73e7edd09a2267` | `33cc2fe2919184c7951fad1eb742845c47e6429d8652dd1d48759d4ac024b941` | `33cc2fe2919184c7951fad1eb742845c47e6429d8652dd1d48759d4ac024b941` | 可沿用 |

V 起始 manifest 从 `s4-v-runner-938d41d171.log` 的前三包以及 `s4-v-runner-ed70ca1be2.log` 的 backend/RS 段提取；H compare 输出为 `/home/dev/gdds-p5-closure-s1-gate-logs/s4-h-manifest-compare-final.log`，H manifests 与来源 JSON 分别在同目录的 `s4-h-manifest-current-final/`、`s4-h-manifest-source-final/`。环境不完整的尝试均保留但不作为判定：缺少 rustc 的 `s4-h-manifest-compare-e6e9075793-missing-rustc.log`；backend/RS 环境变量不匹配的 `s4-h-manifest-compare-e6e9075793-ambient-env.log`；以及 PATH 缺少 `/usr/bin:/sbin` 的 `s4-h-manifest-compare-b051067f3d-incomplete-path.log`。最终判定使用与 V runner 相同的 PATH、`TMPDIR=/home/dev/gdds-p5-closure-s1-gate-logs/g12-default-tmp` 和 `GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`，五包均为“可沿用”。

H 对 V 仅增加 handoff 文档；`vnext/` 与 Docker context 未变。实现 HEAD、V 均为 `ed70ca1be262653bb49267940e73e7edd09a2267`，没有从 `22c1a7e530` 沿用任何包。

bundle 同步方式（没有 GitHub）：开发主机在 `/home/dev/gdds-p5-s4` 提交后，用 `git bundle create` 从当前 `p5-s4` 到 ct108 已有的 V 生成 bundle，通过 `scp` 放入 `/home/dev/gdds-p5-closure-s1-gate-logs/`，然后在 ct108 clone 中 fetch，并在同一 worktree detached checkout 目标 HEAD。V bundle 为 `s4-sync-ed70ca1be2.bundle`；handoff H 初稿也经 bundle 同步，最终 H 经 `/home/dev/gdds-p5-closure-s1-gate-logs/s4-sync-handoff-final.bundle` 同步。H 的分支 ref 已存在于另一个 linked worktree，因此 fetch 到独立 `refs/s4/p5-s4-final*` 后在门禁 worktree detached checkout；未覆盖已 checkout 的分支 ref。没有网络 Git remote 操作。

## 11. 停止条件状态

- `22c1a7e530` runner exit 1 已按 owner `8091397641` 修复；新 V 的 backend/RS runner exit 0。此前 `938d41d171` t4 v1 Submit 停止原因已按同一决议更正为 60 s 对账会话超时转人工恢复、worker 随后空闲。
- 新 V t4 v1 Submit 使用 2/3 个 R5 会话，尚余 1 个 60 s 会话；本次没有用尽或余量为 0。余量是否支撑 S5 完整 t4 由 reviewer 提交 owner 判断。
- 新 V 真实数据未出现 `worker_stalled`、timeout、HTTP 500、人工恢复状态或身份预期不符；数据汇总与 S3 对照通过。
- 没有修改 Dockerfile、Compose、依赖、锁、Contract 或超出 ADR 0020 / Business Lifecycle 3.1.0 / 设计 §7 的行为。没有缩小测试范围或弱化断言。
- 无当前触发且未处置的 §14 停止条件。S4 仍等待独立审核，尚未开始 S5。

## 12. 审核提示词

审核 `p5-g12-exit..H`：`range_start=13d97dc2db5cef4bd82583ab7ac339ed09b5aec3`，实现 HEAD 与 `V=ed70ca1be262653bb49267940e73e7edd09a2267`；`H` 是此分支 tip 上最终 handoff-only commit（完整 SHA 由实现者交付消息提供）。审核工作在只读 detached worktree 中进行；所有测试与容器取证依 DC34 在 `ct108-gw-dms` 运行，不使用开发主机。

必须核查：

1. 执行计划 §2 S4 的所有验收和 §3 S4 的路径预算；本 handoff 对超预算路径的 owner 决议和具体理由是否完整。复核设计 §7.1–§7.7、§12、§14，ADR 0020 与 Business Lifecycle 3.1.0 身份条款。
2. G12-F1 是否只排除了两个 harness 自身重建 tag 的 ID、保留所有决定内容的输入镜像 ID、提高 schema version，并由参数化测试证明两个方向；另核对“跨 HEAD 重建 client image 后 RS manifest 不变”的日志和 compare。
3. 投影侧与 Repository 侧 identity assessment 是否使用同一规则；同项目、不同项目、排除 no、缺表、空表、无非 no 列、列集合不一致与 UNVERIFIABLE 覆盖是否各有唯一测试 owner。
4. Submit 受理的判定顺序是否正确；授权和 exact scope 是否早于重放；撤权或 scope 不符的重放是否被拒。身份确认理由是否走 Submission 共享多行校验，Review 行为是否保持不变。
5. control DB 是否只改单一基线 schema；HTTP DTO/checkpoint 是否直接采用目标形态；OpenAPI/fixture/golden 断言是否同步，没有兼容层。
6. 三条 Compose 旅程是否分别覆盖跨项目替换、UNVERIFIABLE、FULL 混合模式，且没有新建独立 Compose 栈。
7. 938d..V 的文件清单是否足以支持 t2/t3 carried；真实数据身份判定与 Preview、Catalog、History、composite 汇总是否符合 S3 对照。t4 新 V 未运行 History 和 v2 Submit 的范围是否依 owner 2026-10-20 决议执行并清楚说明。
8. `938d41d171` 的 10-20 停止归因是否使用 owner 更正：60 s R5 会话到期后转人工恢复，worker 随后空闲；检查两个诊断目录的 thread `/proc`、control DB、RS 状态和容器日志是否支持这项结论。
9. worker stall detection 的心跳来源、10 s 周期、120 s 默认阈值、先取证再拆栈，以及 `worker_stalled` 与 timeout 的区分和测试；py-spy native 栈失败是否如实记录并继续保存其他诊断。
10. bafd64bf53 的根因修复是否真正阻止 worker 无限期阻塞、是否沿既有 R5 有界重试/失败路径；撤掉修复后根因测试失败的证据是否充分。
11. **必须审查** bafd64bf53 传入 `reconcile_elapsed_seconds=0.0` 是否绕过累计 R5 耗时预算、是否与 R5 既有规则一致。新 V t4 v1 Submit 用时 576.497 s、RS import 79 s、2/3 会话及剩余 1×60 s 来自 worker event、step attempt 和 RS 公开状态；余量是否足以支持 S5 完整 t4，若不足请报告并交 owner 判断。
12. 22c1a7e530 的 runner 失败及 `ed70ca1be2` 的修复是否保留原 artifact 不可见断言、是否只改 RS tests；直接共享连接读写搜索是否完整，同类无锁读写是否均已修正。
13. 每包 runner 是否使用正确来源：前三包由 exit-0 的 938d V 沿用，backend/RS 在新 V 运行；22c exit-1 不得作为任何包来源。五包用例数变化是否与日志一致。
14. H carried 是否按 DC34 在同一 ct108 worktree 判定：RS build-input/source-tree labels 与 V 一致；backend manifest 与新 V runner 起始 backend manifest compare 为“可沿用”；五包 manifest 逐项结果与各自最初运行通过的来源 V 一致。
15. preflight/postflight、静态检查与 `import_rules` 是否满足要求；runner 起止 HEAD、clean worktree、exit code 和镜像记录是否完整。

测试与镜像证据日志根目录：`/home/dev/gdds-p5-closure-s1-gate-logs/`。真实数据行内容和诊断材料不纳入 Git。

# P5 G11b handoff：Compose RS 镜像绑定与耗时构成

## 提交与审核区间

工作在 `/home/dev/gdds-p5-g11b` 的 `p5-g11b` worktree 完成。

| 标识 | 提交 | 内容 |
| --- | --- | --- |
| kickoff base | `460cfc77763fa23850dca2f58d5a59d25f36820c` | 建立 worktree 时 `main` 的 HEAD；满足 G11b 的 `460cfc7776` 下限。 |
| V | `d4c991f77c08d5e21ebfd5ca98155c420c971b6d` | 修复 RS 镜像 identity 绑定、增加参数表测试、记录 RS provenance label，并同步 carried 规则。唯一门禁提交。 |
| H2 | `db601d171c065f13161f79a65edffa8f8fdf651e` | handoff 报告与初次复审修订：补全同文件共享栈候选分析。 |
| H3 | `4d69184a8cb625c15e4abbfa8df813df5fbf9ec8` | handoff 审核提示词及 H2 复审记录；H3 复审后发现 §8.2 最小项遗漏，未打 tag。 |
| H | 本 handoff-only commit | 补全 §8.2 要求的 `import_rules` 对照、路径预算和停止条件记录；仅增加本文件。最终完整 SHA 由审核请求中的 `git rev-parse HEAD` 给出。 |

V、H2、H3 与 H 均带有 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。最终区间为 kickoff base..H；实现 HEAD 与门禁提交均为 V。没有合并、rebase `main`、推送或由实施方打 tag。独立审核通过后由审核方打 `p5-g11b-exit`，作为 S3 区间起点。

## R2-F1 修复

`ensure_repository_service_image()` 先以当前 Python 解释器调用 repository_service 已有的 `tests/support/build_context_digest.py identity`，读取 `build-input-revision` 与 `source-tree-sha256`。没有复制或重新实现 identity/digest 算法。

- 两项 label 都匹配时复用指定镜像；镜像不存在、任一 label 缺失或不匹配时调用现有 `build-repository-service-image.sh` 重建，并在构建后再次核验两项 label。
- canonical identity 无法计算时（包括 dirty worktree），harness 在检查/使用旧镜像前失败关闭，不会静默沿用旧镜像。
- `GATEWAY_REPOSITORY_SERVICE_IMAGE` 指定镜像时使用相同的 identity 检查和构建脚本。
- 权威参数表测试 `test_repository_service_image_is_bound_to_current_build_identity` 覆盖：label 一致时不构建、source-tree label 不一致时构建、镜像缺失时构建。每个 Docker 调用均由替身处理，没有真实构建；3 个参数案例均通过。
- provenance 顶层增加 `repository_service_image`，记录 image ref、image ID，以及 `gateway.p2r1.build-input-revision` 和 `gateway.p2r1.source-tree-sha256` 两个 label。provenance JSON 形状因此扩展；既有 `containers` 字段保留。

只改了测试 harness、测试和文档；没有改生产代码、Dockerfile、Compose 文件、既有用例或断言。

## 路径预算、import_rules 前后对照与停止条件

G11b 是治理计划中的测试 harness 与测试证据工作，不分配设计 §3 的生产代码路径预算；本轮没有启用条件路径、预算外路径或文件改名。实际实现改动只涉及 `compose_gate_harness.py`、新增参数表测试、AGENTS/testing-conventions 与本 handoff。

按执行计划 §8.2 在 kickoff base 与 V 分别运行 `cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules`，外置日志为 `/home/dev/gdds-p5-closure-s1-gate-logs/g11b-import-rules-base-v.log`。三个基线值前后相同：

| 节点 | violations | runtime cycles | unreachable modules |
| --- | ---: | ---: | ---: |
| kickoff base `460cfc77763fa23850dca2f58d5a59d25f36820c` | 0 | 0 | 14 |
| V `d4c991f77c08d5e21ebfd5ca98155c420c971b6d` | 0 | 0 | 14 |

设计 §14 的停止条件均未触发：G11b 没有改动数据类型、Dolt 一致性、比较语义、部署兼容性、身份交互、协议族或生产软件版本；本轮只改测试 harness、测试与文档。G11b 自身停止条件也未触发：无需改生产代码、Dockerfile 或 Compose；没有删除、跳过或放宽用例；identity 算法成功复用；完整 runner exit 0。

G11b 验收由治理计划第 5 项承接。R2-F1 focused 参数表命令为 `cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest tests/test_compose_repository_service_image_identity.py -q`（3 passed）；完整门禁、测量调试、五包 ruff/mypy 与 import_rules 的命令和结果记录在下文对应章节。完整门禁是唯一阶段验收 runner；调试测量只用于估算耗时，不作为门禁证据。

## Compose 旅程测量

计时插件通过 `pytest -p g11b_timing` 从 worktree 外加载，以保持 V clean 并使 canonical RS identity 可以计算。调试运行在 V `d4c991f77c08d5e21ebfd5ca98155c420c971b6d` 上只跑 backend serial 一遍：

```bash
PYTHONPATH=/home/dev/gdds-p5-closure-s1-gate-logs \
G11B_TIMING_LOG=/home/dev/gdds-p5-closure-s1-gate-logs/g11b-compose-timing-events.jsonl \
GATEWAY_COMPOSE_GATE_PROVENANCE_PATH=/home/dev/gdds-p5-closure-s1-gate-logs/g11b-measurement-compose-provenance.json \
../scripts/uv-consume.sh -C . run pytest \
  -m 'serial and not parallel_safe' -n 0 -p g11b_timing --durations=0
```

外置 instrumentation patch：`/home/dev/gdds-p5-closure-s1-gate-logs/g11b-timing-instrumentation.patch`；backend serial 日志：`/home/dev/gdds-p5-closure-s1-gate-logs/g11b-backend-serial-measurement.log`；逐用例原始事件：`/home/dev/gdds-p5-closure-s1-gate-logs/g11b-compose-timing-events.jsonl`。计时代码没有进入提交。

该次收集 2,850 项，选中 34 个 serial 项，34 passed、exit 0，用时 1,505.71 秒（25:05）；起止 HEAD 均为 V，起止 worktree 均 clean。11 个 Compose gate 用例的阶段墙钟如下，单位为秒。`旅程剩余`为测试调用时间扣除其他阶段后的残差；固定轮询 sleep 是旅程中的组成部分，不要与该列再次相加。

| Compose gate 用例 | 总计 | RS identity 检查 | `docker compose build` | 起栈到就绪 | 旅程剩余 | 重启 | 拆栈/清理、gate 锁、端口检查 | 实测固定等待（来源） |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect` | 193.90 | 0.12 | 4.21 | 16.13 | 167.26 | 2.90 | 3.29 | `poll_operation` 160s（2s × 80）；readiness 2s；repository-service ready 2s；worker ready 4s |
| `test_backend_image_builds_with_http_server_entrypoint` | 2.61 | 0.12 | 2.45 | 0 | 0.02 | 0 | 0.02 | 无固定 sleep |
| `test_backend_container_ready_and_stops_cleanly_with_repository_service` | 15.16 | 0.25 | 1.22 | 10.32 | 0.95 | 0 | 2.43 | `_wait_http_ok` 4s（2s × 2） |
| `test_compose_history_compare_journey_zero_write_restart` | 291.91 | 0.12 | 3.25 | 16.46 | 265.10 | 2.84 | 4.13 | `poll_operation` 168s；`poll_history_compare_result` 88s；readiness 2s；repository-service ready 2s；worker ready 4s |
| `test_ordered_history_compare_compose_journey` | 199.19 | 0.12 | 3.61 | 16.12 | 175.69 | 0 | 3.65 | `poll_operation` 138s；`poll_history_compare_result` 28s；repository-service ready 2s；worker ready 4s |
| `test_ordered_submit_bisect_control_cases` | 236.85 | 0.37 | 10.45 | 48.59 | 167.15 | 0 | 10.28 | `poll_operation` 106s；`_run_preview_and_submit` 58s；repository-service ready 6s；worker ready 12s |
| `test_preview_worker_restart_takes_over_expired_running_operation` | 168.15 | 0.12 | 3.79 | 16.42 | 144.02 | 0.36 | 3.44 | `poll_operation` 142s；repository-service ready 2s；worker ready 4s；观察 RUNNING 前 0.05s × 17（0.85s） |
| `test_compose_submit_to_review_approve_journey` | 76.90 | 0.12 | 3.82 | 16.10 | 53.43 | 0 | 3.43 | `poll_operation` 52s；repository-service ready 2s；worker ready 4s |
| `test_compose_three_process_submit_stack_smoke_and_backend_restart` | 25.11 | 0.13 | 2.31 | 16.12 | 0.02 | 2.80 | 3.73 | restart readiness 2s；repository-service ready 2s；worker ready 4s |
| `test_compose_accept_upload_import_poll_t3_read_journey` | 75.20 | 0.13 | 2.35 | 16.53 | 52.79 | 0 | 3.39 | `poll_operation` 52s；repository-service ready 2s；worker ready 4s |
| `test_compose_submit_removes_deleted_user_and_sibling_tables` | 194.34 | 0.12 | 2.43 | 16.15 | 172.18 | 0 | 3.45 | `poll_operation` 168s；repository-service ready 2s；worker ready 4s |
| **合计** | **1,479.32** | **1.73** | **39.90** | **188.96** | **1,198.61** | **8.90** | **41.23** | 固定 sleep 合计 1,236.85s，重叠于以上阶段 |

固定等待的来源与含义：

- harness 的 `poll_operation()`、`poll_history_compare_result()`、`wait_repository_service_ready()`、`worker_ready()` 和 `wait_http_ok()` 使用 2 秒轮询；操作终态轮询默认上限为 300 秒，lease takeover 用例传 240 秒，readiness 上限分别为 180/120 秒。这些是轮询间隔和失败上限，不代表所有墙钟都是可删的 sleep。
- `test_ordered_submit_bisect_compose.py` 的 `_SUBMIT_STEP_TIMEOUT_SECONDS` 是 90 秒；`_run_preview_and_submit` 按 2 秒轮询。preview worker restart 用例在 30 秒 RUNNING deadline 内每 0.05 秒观察一次，实测 17 次。
- lease/heartbeat 属于 `OperationWorkerSettings` 固定预算：`lease_duration_seconds=30.0`、`heartbeat_interval_seconds=10.0`；`_WORKER_FIXED_BUDGETS` 拒绝用环境配置改小。lease takeover 用例的 142 秒 operation poll 包含任务实际执行时间，不是 142 秒 lease idle。
- Compose backend 与 repository-service healthcheck 在 `deploy/compose.yaml` 中为 5 秒 interval、5 秒 timeout、12 次 retries、30 秒 start period；backend 依赖服务 healthy。起栈到就绪测量包含实际启动和这些 readiness 条件。
- gate lock 的 poll 常量为 2 秒、等待上限 1,800 秒；本次没有等锁。端口检查使用 `docker ps` 且调用 timeout 为 30 秒。清理阶段包含 Compose down、volume/network 清理、端口检查及 gate lock。
- 固定 `time.sleep` 实测合计为 1,236.85s / 635 次：`poll_operation` 986s，`poll_history_compare_result` 116s，`_run_preview_and_submit` 58s，`worker_ready` 44s，`wait_repository_service_ready` 22s，`wait_http_ok` 6s，backend local `_wait_http_ok` 4s，0.05s RUNNING probe 0.85s。该合计与 11 个测试调用时间重叠，主要体现异步 operation 执行时间；按来源分组为轮询/操作终态 1,160s、服务就绪轮询 66s、HTTP readiness 10s、RUNNING 探针 0.85s。

### 测量解释与过程偏差

- Compose gate 总调用时间占 backend serial 调试批次的 98.2%。按阶段合计，RS identity 核验约 1.73 秒、Compose build 39.90 秒、起栈就绪 188.96 秒、旅程 1,198.61 秒、restart 8.90 秒、cleanup/lock/port 41.23 秒。旅程的主要时间是后台操作执行及轮询。
- 原始插件在 `test_backend_container_ready_and_stops_cleanly_with_repository_service` 上因同一测试模块有两个用例，将本地 `_wait_http_ok` 包了两层。完整 serial 运行仍然 exit 0；后处理只去掉同一来源、时长相同的重复 readiness 事件。为核对这一点，随后只重跑了该单个用例一次，使用外置修正版 `g11b_timing_v2.py`；它 1 passed、exit 0，用时 18.70 秒，确认起栈/readiness 10.30 秒。目标用例计时日志与修正 patch 分别是 `g11b-compose-timing-container-gate-rerun.log`、`g11b-compose-timing-container-gate-rerun.jsonl` 和 `g11b-timing-instrumentation-correction.patch`。主表保留完整 serial 批次的构建与总时长，避免把单项重跑的 build-cache 波动混入批次值。
- 第一次 backend mypy 检查发现新增测试通过模块属性访问 `subprocess`，触发 strict mypy `attr-defined`。测试替身改为按导入路径 monkeypatch 后，focused 测试、ruff、mypy 和最终五包静态检查均通过；这不是 runner 或产品失败。
- 测量期间 CPU 为 96 个在线逻辑 CPU；开始快照 load average `4.30 / 4.52 / 4.40`，结束快照 `3.64 / 4.40 / 4.62`。测量前有两个 idle minisweagent sleep 容器与两个 idle buildkit 容器；测量期间只有当前测试 project 的 backend/worker/repository-service 栈活动，未发现并行 Compose 栈或宿主 Dolt 进程。同期快照见 `g11b-compose-timing-host.log`。

## 方案报告（未实施）

| 方案 | 基于测量的预期节省 | 主要风险 | 涉及文件 | 强制重建 |
| --- | --- | --- | --- | --- |
| 多个旅程并发运行 | 初始最多 2 路；把 archive/history/ordered zero-write、lease takeover、restart smoke 和带 90 秒步骤预算的 control case 留在 serial。其余 5 个候选（image build、container ready、review approve、upload/import、delete/sibling）合计 364.21s；两路 LPT makespan 194.34s，理想节省 169.87s（2:50）。完整 runner 理想约 29:42；计入端口分配、Compose/I/O争用后约 30–31 分钟。若将 `test_ordered_submit_bisect_control_cases` 加入并发，6 案例 LPT makespan 312.05s，理想节省 289.01s（4:49），完整 runner 理想约 27:43，但该用例有 90 秒步骤预算，不建议初次并发。 | 当前 `8000:8000` host port、单一 gate lock、静态 `BACKEND_URL` 不允许并发。需按 Compose project/slot 参数化 host port（包括 `deploy/compose.yaml`）、gate lock 和 `BACKEND_URL`。敏感用例涉及 30s lease、10s heartbeat、restart；CPU/I/O争用可能使任务越过预算。96 CPU、当前 load 约 4 支持先试 2 路，不支持直接按 48 个 xdist workers 并发 Compose。 | `vnext/deploy/compose.yaml` 的 `8000:8000`、`vnext/backend/tests/support/compose_gate_harness.py` 的 port check/lock/URL、6 个 Compose 测试文件中的 `BACKEND_URL` 使用、`vnext/backend/pyproject.toml` markers、`vnext/scripts/run-tests.sh` 批次调度、testing-conventions 的单飞说明。 | **是**：Compose 与 container harness / Compose E2E 调度变化后须按最终 HEAD 重建并运行门禁。 |
| 同一文件内共享 Compose 栈 | 有 3 组值得区分。① `test_ordered_submit_bisect_compose.py` 的 `test_ordered_submit_bisect_control_cases` 内 3 个 project，可在新增 repository/control DB seed-reset 后共栈；重复的两次 build、RS identity、ready 与 cleanup 上限约 `2 × (3.5 + 16.2 + 3.4) = 46s`（该用例总计236.85s）。同文件的 `test_preview_worker_restart_takes_over_expired_running_operation`（168.15s）须独立，依赖 RUNNING lease 与 worker restart。② `test_submit_compose_e2e.py` 的 smoke/restart（25.11s）、upload/import（75.20s）、deleted/sibling（194.34s）都各自建栈；若合为一个栈，build、ready、RS identity、cleanup 的重复阶段理论可省约44.6s（按三个实测行各减去一份共享 build/ready/cleanup，重叠于总计，不含 journey）。其中 restart smoke 可先运行，但后两项都写入同一 repository/control DB；delete/sibling 又依赖自己建立的 baseline→sibling→delete 状态链。需设计每项的独立 workspace、idempotency key 和 repository/control DB reset，实际收益须扣除 reset 成本及额外状态验证，当前不建议共栈。③ `test_backend_http_container_gate.py` 的 image-build-only（2.61s）和 live ready/stop（15.16s）不需要共享 live stack；可把 entrypoint 检查并入 live test 并复用 backend build，最多省前者约2.61s，但收益很小。archive（193.90s）与 history zero-write/restart（291.91s）各自单独成文件，且必须观测 restart 后零写入；submit restart smoke（25.11s）与 lease takeover（168.15s）也保留其重启/lease 行为，不能通过共用已运行栈削弱这些不变量。 | `vnext/backend/tests/test_ordered_submit_bisect_compose.py`、`test_submit_compose_e2e.py`、`test_backend_http_container_gate.py`，以及需要时的 `tests/support/compose_gate_harness.py`、seed/mapping helper。 | **是**：修改实际 Compose E2E 或 container harness 属于强制重建项。 |
| 缩短测试栈固定等待 | 11 项中 2 秒 sleep 累计 1,236.85 秒，但它们大多与 backend/Dolt operation 执行重叠。降低测试客户端轮询间隔只减少终态发现延迟；保守估计总节省小于 60 秒。 | 不能把所有 sleep 总量当成可节省时间。降低间隔会增加 HTTP 查询量。30s lease/10s heartbeat 是 runtime 固定值，环境变量不可覆写；若测试栈换短 lease/heartbeat，会偏离 production runtime contract（例如 30s→2s 是缩短 93%，并需同步调整 heartbeat），且可能改变 lease race。healthcheck interval 改动也会改 Compose readiness 行为。 | Poll cadence：`tests/support/compose_gate_harness.py`、`test_ordered_submit_bisect_compose.py`；lease/heartbeat：`backend/src/gateway_backend/settings.py`；healthcheck：`deploy/compose.yaml`。 | **是**：改测试 E2E/harness 或 Compose readiness 后必须重建；改 runtime budget 还需先修改 owning contract。 |
| 部分旅程只在阶段退出时运行 | 例如将三项最长的 history zero-write/restart（291.91s）、ordered submit controls（236.85s）、ordered compare（199.19s）移出日常门禁，日常理想节省 727.95s（12:08），完整日常 runner 约 20:24。 | 日常门禁将失去历史 compare restart 后零写入、ordered submit control outcomes、ordered history compare 的 add/delete/modify 及零写入检查，缺陷要到阶段退出才发现。该选项削弱日常 Contract 覆盖，不推荐。 | `vnext/scripts/run-tests.sh`、backend 测试 marker/选择、对应三个 Compose 测试文件与 testing-conventions。 | runner 调度本身不改镜像输入；但 S3/阶段退出仍须按最终 HEAD 运行完整 container gate，届时强制重建要求照常生效。 |
| 维持现状 | 0 秒。V 的实测完整 runner 为 32:32；保持所有 11 个 Compose gate 每日覆盖。 | 耗时仍约 32–33 分钟。 | 无新增改动。 | 方案本身否；G11b harness 改动已在 V 触发并完成强制门禁。 |

推荐组合是：保留全部旅程在日常门禁、维持 30s lease/10s heartbeat 与当前 poll interval；不跨测试共享栈；未来若 owner 决定投入 port/lock/URL 改造，先把五个低时序敏感案例放入独立的 2 路 Compose 批次，archive/history/ordered zero-write、lease takeover、restart smoke 和 90 秒 control case 保持 serial。按当前数据预计完整 gate 约 30–31 分钟；在未完成改造与重复稳定性验证前，维持当前 32:32 的门禁是低风险选择。

## 审核与过程偏差

首次独立审核对象是 H1 `d786dcf4bd96ecc7701148f29e07d3cfc6c621f0`，审核结论阻塞：方案报告没有评估 `test_submit_compose_e2e.py` 与 `test_backend_http_container_gate.py` 的同文件候选，也未说明 `test_ordered_submit_bisect_compose.py` 中单独的 lease/restart 用例。该报告缺口已在本次修订中补充，现有数据没有重跑。

首次审核尚未完成时，审核方曾短暂创建 `p5-g11b-exit`；在发现阻塞项后已删除并确认 tag 不存在。该次审核不通过，临时 tag 不构成阶段退出证据；最终 H 仍须重新独立审核，通过后再创建退出 tag。H1 上 carried 结果已记录在 `/home/dev/gdds-p5-closure-s1-gate-logs/g11b-carried-final.log`，但修订后的最终 H 必须重算 identity 并重建 backend/worker，最终结果以 `g11b-carried-final-h2.log` 为准。

H2 复审确认 G11b 要求的三种参数场景已覆盖；额外的单 label 缺失案例属于增强覆盖，不是本阶段验收项。复审按执行计划 §8.2 指出 handoff 缺少最后一节“审核提示词”，因此 H2 结论为定向修订。H3 补上提示词后，独立复审再次给出定向修订：§8.2 还要求 `import_rules` 前后对照与设计 §14 停止条件状态；这两项已在本修订中补齐。两次定向修订都只改 handoff，不改代码、不重跑测试；最终 H 的 carried 重新执行并记录如下。

## V 上完整门禁与 provenance

完整权威 runner 仅在 V 上运行一次，未预先构建 RS 镜像：

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

日志 `/home/dev/gdds-p5-closure-s1-gate-logs/g11b-authoritative-run-1.log` 记录起止 HEAD、起止 clean status 与 runner 自身 exit code。时间为 `2026-10-17T01:12:40Z` 至 `2026-10-17T01:45:12Z`，耗时 32:32；起止 HEAD 均为 V，status 均 clean，exit 0。

| 包/批次 | 结果 |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend parallel | 2,816 passed（新增参数表测试 3 案例已计入） |
| backend serial | 34 passed |
| repository_service parallel | 1,684 passed、1 skipped |
| repository_service serial | 205 passed |

相较 G11，backend 新增 3 个参数化案例：2,813 → 2,816 parallel，serial 仍 34；没有删除、跳过或放宽既有用例。backend 输出 FastAPI/Starlette `httpx` deprecation warnings（parallel 48 条、serial 1 条），不影响 exit 0；RS 的 1 skipped 与 G11 数量一致。

runner 前只 inspect、没有重建 `gateway-repository-service:local`。`g11b-authoritative-preflight.log` 记录其旧 `org.opencontainers.image.revision=3223152f26d1edecba4f674da95f9e9576c0741e`，但两项有效 identity label 已等于 V，故 Compose harness 按 identity 复用，不按旧 revision label 误判。

V identity 由 `python3 vnext/repository_service/tests/support/build_context_digest.py identity` 计算：

| identity 字段 | V 值 | runner provenance 值 | 相等 |
| --- | --- | --- | --- |
| `build_input_revision` | `adc5d87fea073545fde6416d123c3d7845e715ff` | `gateway.p2r1.build-input-revision`：同值 | 是 |
| `source_tree_sha256` | `sha256:5b34d0c51e8d4798beb06d7524e9610785a2ad95763fbfd0ddcb942cb2eb8fd4` | `gateway.p2r1.source-tree-sha256`：同值 | 是 |

权威 provenance：`/home/dev/gdds-p5-closure-s1-gate-logs/g11b-authoritative-compose-provenance.json`；project `ordered-bisect-b-554228-baseline`；RS image `sha256:df34df3e9e8763f9a320f25583c133f3985c407170bf2e415b6efca64e287146`；backend image `sha256:b752628c64b425749753e1f568fcc95ba12596faf3ad93e161675e81a546ed56`；worker image `sha256:e1759450dd4ba444b8f40f5d362a063114f5b3ef2d2784f515503dcdb021fcc9`。

## 静态检查

V 前五包全部通过 `ruff check .` 与 `mypy`：

```bash
(cd vnext/shared_kernel && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
(cd vnext/repository_contracts && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
(cd vnext/repository_client && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
(cd vnext/backend && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
(cd vnext/repository_service && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
```

| 包 | mypy 检查文件数 | 结果 |
| --- | ---: | --- |
| shared_kernel | 34 | ruff/mypy passed |
| repository_contracts | 15 | ruff/mypy passed |
| repository_client | 26 | ruff/mypy passed |
| backend | 476 | ruff/mypy passed |
| repository_service | 198 | ruff/mypy passed |

`cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules`：0 violations / 0 runtime cycles / 14 unreachable modules。focused R2-F1 测试为 3 passed。五个 lock SHA 无改动。

## V → H carried 结果

本文件修订后的 handoff-only commit 是最终 H；审核时以 `git rev-parse HEAD` 取得其 SHA。carried 操作须在同一个 `p5-g11b` worktree 的最终 H 状态执行：canonical `build_context_digest.py identity` 重算出的 RS `build_input_revision=adc5d87fea073545fde6416d123c3d7845e715ff`、`source_tree_sha256=sha256:5b34d0c51e8d4798beb06d7524e9610785a2ad95763fbfd0ddcb942cb2eb8fd4` 应与 V provenance 和本地 RS 镜像 labels 相等。

使用 V provenance project `ordered-bisect-b-554228-baseline`，执行同一命令两次：

```bash
docker compose --project-name ordered-bisect-b-554228-baseline \
  -f /home/dev/gdds-p5-g11b/vnext/deploy/compose.yaml build backend worker
```

两次构建之间不运行测试。V、H1、H2 与 H3 上已得到的 backend image ID 均为 `sha256:b752628c64b425749753e1f568fcc95ba12596faf3ad93e161675e81a546ed56`，worker image ID 均为 `sha256:e1759450dd4ba444b8f40f5d362a063114f5b3ef2d2784f515503dcdb021fcc9`，与 V provenance 相等。H1、H2、H3 的 carried 日志分别为 `/home/dev/gdds-p5-closure-s1-gate-logs/g11b-carried-final.log`、`g11b-carried-final-h2.log`、`g11b-carried-final-h3.log`，都不能替代最终 H carried。H 上 identity 和两次 build 的结果记录在 `/home/dev/gdds-p5-closure-s1-gate-logs/g11b-carried-final-h4.log`：RS labels 为 build-input `adc5d87fea073545fde6416d123c3d7845e715ff`、source-tree `sha256:5b34d0c51e8d4798beb06d7524e9610785a2ad95763fbfd0ddcb942cb2eb8fd4`；两次 backend ID 均为 `sha256:b752628c64b425749753e1f568fcc95ba12596faf3ad93e161675e81a546ed56`，两次 worker ID 均为 `sha256:e1759450dd4ba444b8f40f5d362a063114f5b3ef2d2784f515503dcdb021fcc9`；日志 exit 0、起止 HEAD 相同且 clean。

## 审核提示词

```text
任务：独立审核 P5 G11b 的 backend Compose repository-service 镜像绑定修复与耗时方案报告。审核方未参与实施；按阶段验收与风险证据审核，不预设结论。

审核对象：`p5-g11b` worktree 的最终 H（本 handoff-only commit；用 `git rev-parse HEAD` 解析 SHA），门禁提交 V = `d4c991f77c08d5e21ebfd5ca98155c420c971b6d`，实现 HEAD = V；区间 `460cfc77763fa23850dca2f58d5a59d25f36820c..H`。在只读 detached worktree 中审核，不改实现、测试或 handoff，不推送、不合并。

权威依据：治理修订计划 G11b、`p5-arch-closure-g11-independent-review.md` §2.2–§2.3（R2-F1/R2-O1）、AGENTS.md、`testing-conventions.md`（P5-5E serial Compose 与 carried）、执行计划 §8.1–§8.2、§8.7、§8.9，以及 ADR 0012。

必须核查：
1. `ensure_repository_service_image()` 复用 canonical `build_context_digest.py identity`，比较两个 RS identity labels；dirty/identity 失败时关闭；缺失或不匹配时重建并核验。测试表覆盖一致不建、身份不一致构建、镜像缺失构建，Docker 调用由替身处理。
2. V provenance 中 RS labels 与 V 上 canonical identity 相等；provenance 形状变化有说明。
3. V 上权威 runner clean start/end、exit 0、命令与日志，以及各包计数：backend 2,813 + 34，再加新增 3 案例；其余包与 G11 一致，RS 1,684 + 1 skipped / 205。核对没有预构建 RS 镜像、没有删改既有用例。
4. 11 个 Compose case 的测量阶段、固定等待来源、CPU/load 与 Docker 活动；核对外置 instrumentation patch/logs、重复 readiness 计时的校正依据，以及没有把调试运行误报为门禁证据。
5. 方案报告评估并发、同文件共栈、缩短测试栈等待、阶段退出才运行、维持现状；每项给出节省、风险、文件和强制重建项；不实施方案。特别检查 3 个 ordered control projects、lease/restart case、submit 三旅程、backend image-only/live gate 的隔离与计时。
6. 最终 H carried：RS identity 在 H 重算；在同一 worktree 与 V provenance project 下连续构建 backend/worker 两次，中间不运行测试；两个 image ID 均与 V provenance 相同。核对 `g11b-carried-final-h4.log` 的起止 HEAD、clean status、identity、project、IDs 和 exit code。
7. 五包 ruff/mypy、backend `import_rules`、commit trailer，以及 H 仅在 V 之后新增 handoff 文档。
8. Handoff 按执行计划 §8.2 记录 kickoff base/V 的 `import_rules` 前后值、路径预算与文件改名情况、设计 §14 和 G11b 停止条件状态、实际验收命令与结果；核对这些记录有对应证据。

验证：在审核 worktree 独立运行五包 ruff/mypy 与 `import_rules`；核对上述日志和 provenance。不要求重跑完整 runner，不运行 Compose 旅程。

交付：回复审核结论（通过 / 定向修订 / 整体返工）和发现。只有全部通过时，按 owner 授权在 H 上创建附注 tag `p5-g11b-exit`；不推送。
```

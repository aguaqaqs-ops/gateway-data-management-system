# P5 G11 handoff：缩短完整门禁

## 提交与审核区间

| 标识 | 提交 | 内容 |
| --- | --- | --- |
| kickoff base | `676110a74b68f68ea89866e25fa7cffdaae8bf73` | 建立 `/home/dev/gdds-p5-g11` 时 `main` 的 HEAD；基线日志也确认 worktree clean。 |
| V | `3223152f26d1edecba4f674da95f9e9576c0741e` | backend xdist、分类调整、runner 与规则文档；完整门禁在此提交执行。 |
| H | 本文件所在的 handoff-only 提交 | 仅增加本文件，形成审核区间 `676110a74b68f68ea89866e25fa7cffdaae8bf73..H`。实际完整 SHA 是提交后的分支 HEAD，见审核请求。 |

V 与 H 的提交均带有 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。工作在 `p5-g11` worktree 完成；未合并、rebase、推送或由实施方打 tag。独立审核通过后由审核方创建 `p5-g11-exit`。

## 改动前基线

基线在 clean kickoff base 上只运行 backend 一次，使用 `uv-consume.sh`，日志为：

`/home/dev/gdds-p5-closure-s1-gate-logs/g11-baseline-backend-676110a74b68f68ea89866e25fa7cffdaae8bf73.log`

收集到 2,847 项，2,847 passed，用时 1,717.23 秒（28:37）。marker 数有重叠：`unit` 2,665、`integration` 205、`serial` 56。审阅到的 7 个 Compose 旅程文件是 `test_archive_compose_e2e.py`、`test_backend_http_container_gate.py`、`test_history_compose_e2e.py`、`test_ordered_compare_compose.py`、`test_ordered_submit_bisect_compose.py`、`test_review_compose_e2e.py`、`test_submit_compose_e2e.py`。

按 `--durations=0` 的测试调用时间分组：Compose 旅程 1,575.36 秒；其他 serial / 时序敏感用例 37.97 秒；其余用例 100.30 秒。三组之和 1,713.63 秒，与 pytest 墙钟相差 3.60 秒（收集、fixture 与 runner 等开销）。Compose 占基线墙钟约 91.7%，serial 与 Compose 合计约 93.9%。S2b 参考值仍为 `753c5768a5` 上 2,847 passed、1,631.86 秒；G11 的 kickoff 实测比该参考慢 85.37 秒。

G11 指定的改动前基线只跑 backend，因此没有在 kickoff 上另测 repository_service 两遍或完整 runner；下表以“未采样”标出，不把 V 的数据冒充改动前对照。

## 批次耗时与用例数

以下 runner elapsed 是 `run-tests.sh` 记录的阶段墙钟；括号内为 pytest 自身时间。G11 kickoff 的 backend 是一遍单进程，V 上分为并行与 serial 两遍。

| 批次 | kickoff base | V 第一次 | V 第二次 |
| --- | ---: | ---: | ---: |
| backend 并行 | 未拆分；单遍 1,717.23 秒 / 2,847 passed | 68 秒（67.70 秒）；2,813 passed | 69 秒（68.33 秒）；2,813 passed |
| backend serial | 未拆分 | 1,511 秒（1,509.76 秒）；34 passed | 1,507 秒（1,505.60 秒）；34 passed |
| repository_service 并行 | G11 kickoff 未采样 | 20 秒（18.82 秒）；1,684 passed、1 skipped | 20 秒（18.90 秒）；1,684 passed、1 skipped |
| repository_service serial | G11 kickoff 未采样 | 353 秒（351.57 秒）；205 passed | 346 秒（345.31 秒）；205 passed |
| 完整 runner 墙钟 | G11 kickoff 未采样 | 1,958 秒（32:38） | 1,945 秒（32:25） |

V 上 backend 两遍相加分别为 1,579 秒与 1,576 秒，相对 kickoff 单遍 1,717.23 秒减少约 8.0% 与 8.2%。并行遍只有约 68–69 秒，serial 遍仍占 backend 新批次约 95.6–95.7%。因此实际收益低于“backend 全量并行”的直觉预期，剩余耗时仍主要由 serial / Compose 决定。

backend 完整 runner 使用 `-q`，没有采集本轮每个 serial 用例的独立 duration。focused serial 调试运行记录 34 passed、总计 1,816.73 秒；其中 Compose 旅程 1,794.60 秒，其他 serial 22.13 秒，Compose 占该调试 serial 样本约 98.8%。这是调试样本的构成，不与两次权威 runner 的 1,509.76 / 1,505.60 秒直接混作同一测量口径。改动前 Compose 占 backend 基线 91.7%；改动后权威 runner 的 serial phase 占 backend 两遍总时间约 96%，调试样本显示 serial 内部几乎全由 Compose 旅程构成。

## Marker 分类与隔离审查

基线有 26 个 backend 测试文件含 serial 标记（56 个收集项）；逐文件检查其 Compose、固定预算、信号、子进程、Dolt、端口及持久状态含义。V 上保留 34 个 serial 项，分布在 18 个文件。backend 没有 `parallel_safe` 用例；marker 在 `pyproject.toml` 的 strict-marker 列表中声明，`tests/conftest.py` 对 `serial and not parallel_safe` 自动加入 `xdist_group("serial")`，并继续给未标 `integration` / `unit` 的项默认加 `unit`。

### serial 保留项

- Compose / host 资源共 7 个文件：`test_archive_compose_e2e.py`、`test_backend_http_container_gate.py`、`test_history_compose_e2e.py`、`test_ordered_compare_compose.py`、`test_ordered_submit_bisect_compose.py`、`test_review_compose_e2e.py`、`test_submit_compose_e2e.py`。这些测试实际启动 Compose 栈、使用 host 8000 与 `/tmp/gateway-compose-gate.lock`，全部保持 serial。
- 固定时间预算或线程时序：`test_archive_http.py::test_archive_body_middleware_returns_on_client_disconnect`（thread join 5 秒）；`test_operation_worker_integration.py` 中 3 个 worker readiness / drain / concurrent-cancel 用例（Event、join、future 5 秒预算）；`test_sqlite_operation_store_integration.py` 中 writer contention 与进程终止用例（5 秒等待 / 子进程回收）；`test_submit_job_effect.py::test_await_import_result_timeout_marks_manual_recovery`（固定 0.2 秒 poll deadline）；`test_upload_streaming.py::test_stalled_body_times_out_while_waiting_for_next_chunk`（stream timeout）。
- 信号、子进程或重启：`test_http_admission_shutdown_process.py`、`test_operation_recovery_process.py`、`test_operation_worker_process.py`、`test_submit_worker_process.py` 保留 serial；`test_submit_recovery.py::test_await_import_result_consumes_matching_terminal_after_repository_restart` 保留 serial 并显式标为 integration；`test_submit_worker.py::test_submit_worker_reaches_ready_with_live_repository_service` 保留 serial 与 integration（真实 Dolt / repository service、Event.wait 与 thread.join 各 15 秒）。

### serial 移除或转为 integration 的项

以下测试实现没有改动；只移除了不再需要的 serial 标记。涉及真实 Dolt / repository service 的保留 `integration`，并且每个用例的持久状态位于自己的 `tmp_path`，不绑定共享 host 端口，也没有固定时间预算；因此进入并行批次。

- `test_archive_concurrency.py`：移除模块级 serial；各用例使用独立 fixture 数据库，模块其余用例是 unit。
- `test_canonical_snapshot_identity.py`：移除模块级 serial，保留 integration；Dolt 状态按用例隔离。
- `test_history_compare_transactions.py::test_concurrent_accept_with_same_idempotency_key_has_single_winner`：移除 serial；只在本用例数据库中验证事务竞争，没有固定 wait timeout。
- `test_http_admission_shutdown.py::test_admission_first_server_pre_drains_before_super_shutdown`：移除 serial；app 与 TestClient 在同一用例内运行，使用临时状态与动态端口，没有子进程 / signal 时序预算。
- `test_operation_takeover.py::test_concurrent_recovery_cas_leaves_single_retry_wait`：移除 serial；integration harness 使用独立 `tmp_path`，CAS 竞争无固定等待预算。
- `test_preview_job_publish.py::test_publish_supersedes_when_baseline_head_drifts` 与 `test_successful_publish_does_not_insert_preview_idempotency`：移除 serial；独立临时 harness、同步执行。
- `test_review_transactions.py::test_apply_review_concurrent_commands_produce_one_commit_and_stable_conflict`：移除 serial；并发线程只竞争该用例自己的 review 数据库，Barrier 没有共享状态或固定 timeout。
- `test_submit_job_effect.py::test_submit_upload_and_import_wire_mapping_against_live_repository`：serial 改为 integration；真实 repository 数据按 `tmp_path` 隔离，不使用共享 host 端口或固定预算。该文件中固定 poll deadline 的 timeout 用例仍 serial。
- `test_submit_job_prepare.py::test_prepare_checkpoint_payload_binding_mismatch_worker_aborts_and_allows_reaccept`：移除 serial；独立临时 SQLite / artifact harness，没有线程或时间预算。
- `test_submit_prepare_removed_tables.py`：移除模块级 serial、保留 integration；真实 Dolt 仓库和状态按用例隔离。
- `test_submit_recovery.py`：移除 `test_await_import_finalize_commits_lease_acknowledgment_via_worker_runtime`、`test_await_import_finalize_response_loss_after_terminal_commit_before_worker_ack`、`test_await_import_stable_abort_completes_via_worker_runtime` 的 serial；各用例使用临时 harness 和 recording transport，无固定等待。`test_operator_abort_evidence_rejects_unknown_repository_operation` 与 `test_operator_abort_import_rejected_via_recovery_port` 从 serial 转为 integration；模块级 integration 保留。repository restart 用例仍 serial，原因见上。
- `test_submit_worker.py`：移除 `test_submit_worker_duplicate_claim_is_exclusive` 与 `test_submit_import_w2_crash_rebuilds_checkpoint_via_claim` 的 serial；均使用独立 `tmp_path`，前者的 `127.0.0.1:9` 是未发起连接的占位 URL，不绑定或共享主机端口。真实 repository-service readiness 用例仍 serial，原因见上。

新增 serial 只有 `test_archive_http.py::test_archive_body_middleware_returns_on_client_disconnect`：它启动线程驱动 ASGI disconnect，并以 `thread.join(timeout=5.0)` 作为“必须及时返回”的断言，受固定时间预算约束。

`parallel_safe` 新增、移除：无。`test_compose_gate_provenance.py` 虽名称含 compose，但只校验临时 Git/source-tree provenance，不启动 Compose 栈、不占用 8000 或 Compose flock；`test_backend_dockerfile_contract.py` 是静态契约检查，均无需 serial。

测试侧隔离修正：无。本轮没有固定路径改 `tmp_path`、固定端口改动态端口的代码修改；原有可并行项已经逐项满足每用例临时状态 / 动态端口边界。diff 中的测试变化只有 marker，断言、测试数量与测试体均未放宽或删除。

## 依赖、runner 与文档

用 `uv add --dev pytest-xdist==3.8.0` 更新 backend dev group。lock 仅增加 `pytest-xdist==3.8.0` 与其传递依赖 `execnet==2.1.2`；registry 为 `https://pypi.org/simple`，wheel / sdist 为 canonical `files.pythonhosted.org`。没有其他依赖变化。`uv lock-check` 通过；canonical lock identity 与 backend Dockerfile contract focused 检查共 9 passed。

runner 将 backend 分成 `-m "(not serial) or parallel_safe" -n "${TEST_WORKERS}"` 与 `-m "serial and not parallel_safe" -n 0` 两遍，其他三个小包仍单进程，repository_service 原有两遍保留。设置 `GATEWAY_TEST_BASETEMP` 时 backend Compose 文件与 repository_service 一样从 tmpfs pytest 批次中排除，再在真实文件系统上单独执行。AGENTS.md 与 testing-conventions 已同步新入口、marker 规则与 kickoff 实测示例。

## 调试与静态检查

- backend 并行 `GATEWAY_TEST_WORKERS=48`：2,813 passed，68.38 秒；`auto`：2,813 passed，61.64 秒。没有发现只在并行下出现的顺序依赖或共享状态失败。
- backend serial focused：34 passed，1,816.73 秒；其中 Compose 旅程 1,794.60 秒。
- 按要求移开 `/usr/local/bin/dolt` 再执行 backend `-m unit`：2,668 passed、179 deselected；Dolt 已恢复。
- canonical lock identity + backend Dockerfile contract：9 passed。
- 五包 ruff 与 mypy 全部 exit 0；backend mypy 检查 475 个 source files。import_rules exit 0。
- 没有需要修正的并行专属失败；没有修改断言、生产代码、依赖边界或测试行为。

## 两次权威 runner 与 provenance

两次均通过 `set -o pipefail` / `tee` 记录日志与 runner 自身 exit code，起止 HEAD 均为 V，起止 worktree 均 clean。两次连续执行之间没有 worktree 写入、提交或独立镜像重建 / retag；run 2 只包含权威 runner 自身的门禁操作。

| 运行 | 起止 UTC | HEAD / status / exit | 日志与 Compose provenance |
| --- | --- | --- | --- |
| 1 | 16:48:07–17:20:45 | 起止 `3223152f26d1edecba4f674da95f9e9576c0741e`；clean → clean；exit 0 | `/home/dev/gdds-p5-closure-s1-gate-logs/g11-authoritative-run-1.log`；`g11-authoritative-run-1-compose-provenance.json`；provenance SHA-256 `22038d09e2896cc57642858f098c0b728d2e5aaeae2e2c68d40cdea4441772e1` |
| 2 | 17:20:58–17:53:23 | 起止 `3223152f26d1edecba4f674da95f9e9576c0741e`；clean → clean；exit 0 | `/home/dev/gdds-p5-closure-s1-gate-logs/g11-authoritative-run-2.log`；`g11-authoritative-run-2-compose-provenance.json`；provenance SHA-256 `2fcc8036289709bb2b3fa32d2e17af656d23fc0dff13ef6df8ed4ef17ecd1771` |

每轮的包计数都一致：shared_kernel 242；repository_contracts 152；repository_client 154；backend 2,813 parallel + 34 serial = 2,847；repository_service 1,684 parallel + 1 skipped、205 serial。没有数量差异。

run 2 最后一次 Compose provenance 的 project 为 `ordered-bisect-b-1890406-baseline`：backend `sha256:4d3c6a4113b1d636fc436f5de900808cee0d90f6b6e1e7c632da372d0106644e`、worker `sha256:44e9d79611b733ea00decbef0092e92b9d2fac054985d9e5a2bd520daca53b0b`、repository-service `sha256:df34df3e9e8763f9a320f25583c133f3985c407170bf2e415b6efca64e287146`。repository-service label 记录 revision `3223152f26d1edecba4f674da95f9e9576c0741e`、source-tree `sha256:5b34d0c51e8d4798beb06d7524e9610785a2ad95763fbfd0ddcb942cb2eb8fd4`、uv-lock `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`。

## V → H carried 判定

V→H 只增加本 handoff 文档，不改 Dockerfile、依赖锁、deployment、Compose、container runtime、Docker / Compose 测试或 harness。

- repository-service 使用 build-input/source-tree label；run 2 provenance 中的 source-tree 与 V 镜像 label 一致。handoff 位于 `docs/`，不属于 repository-service build context。
- backend / worker 在 V 的同一 worktree、同一 Compose project `ordered-bisect-b-1890406-baseline` 上，用测试 helper 实际调用的 `docker compose -f vnext/deploy/compose.yaml build backend worker` 连续构建两次；两次之间没有运行测试。两次都得到 backend `sha256:4d3c6a4113b1d636fc436f5de900808cee0d90f6b6e1e7c632da372d0106644e`、worker `sha256:44e9d79611b733ea00decbef0092e92b9d2fac054985d9e5a2bd520daca53b0b`，与 run 2 实际容器 provenance 完全相同。证据日志：`/home/dev/gdds-p5-closure-s1-gate-logs/g11-carried-compose-build-1.log`、`g11-carried-compose-build-2.log`。
- 有一组早先的 host-network 手动重建日志 `g11-carried-build-1.log` / `g11-carried-build-2.log`，其 ID 不等于 provenance，不作为 carried 证据。原因是 Compose 测试 helper 的 `run_compose()` 给子进程传独立环境字典，不会继承 runner shell 的 `GATEWAY_DOCKER_BUILD_NETWORK=host`；最终判定复现了测试 helper 的默认网络环境并精确匹配 provenance。repository-client 受保护标签未删除或 retag。

因此 V 的容器门禁结果对 H 为 `carried`；不需要在 H 上重跑 Compose。G11 没有触发任何停止条件。

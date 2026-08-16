# P2-R6-S7 — Harness Implementation Review

状态：`fail`

日期：2026-08-16

本记录是 S7-4 的独立只读实现审核。审核对象为 S7-2/S7-3 的实际提交与当前工作树中的
Compose/client harness、四个 exact nodeid 及 README inventory；审核不修改 production、
Compose、Dockerfile 或测试实现，不运行 provisional image/Compose gate。

权威设计：[P2-R6-S7 Compose Lifecycle Design](../formal/plans/p2-r6-s7-compose-lifecycle-design.md)
权威执行计划：[P2-R6-S7 Compose Lifecycle Execution Plan](../formal/plans/p2-r6-s7-compose-lifecycle-execution-plan.md)
前置审核：[P2-R6-S7 Independent Design Review](p2-r6-s7-step-1-design-review.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_head: 5aea9dd9796957d5db10335884c5f91955a43b4b
reviewed_commits:
  - 10f84a19e47fb6991dba53318efd9c44024cdf69
  - 5aea9dd9796957d5db10335884c5f91955a43b4b
review_worktree_clean_at_start: yes
production_code_changed_by_review: no
compose_or_docker_input_changed_by_review: no
container_rebuild_required: yes
container_rebuild_reason: S7 Compose/client/container harness changed
last_verified_image_revision: none
last_verified_source_tree_image_id: none
container_gate_for_current_head: deferred
phase_2_complete: no
```

`reviewed_head` 是审核开始时的完整 source SHA。S7-2/S7-3 改动触及实际 Compose/container
harness、client Dockerfile 和 Docker lifecycle nodeids，因此任何 provisional image 必须
从修复后的 candidate 重新构建；Stage J image 不能关闭本审核 finding。

## Verification performed

- 四个 exact nodeid 已在 `test_compose_lifecycle_harness.py::test_s7_exact_compose_nodeids_collect`
  中收集；README 和 testing-conventions inventory 与 formal design 的四项一致。
- `cd vnext/repository_service && uv run pytest -m unit tests/test_compose_lifecycle_harness.py
  tests/test_versioned_read_compose_e2e.py`：`64 passed`。
- touched repository-service files 的 `ruff`、`mypy` 和 `git diff --check`：通过。
- 未运行 Docker/Compose lifecycle gate；因此没有当前 candidate 的 image、network、volume 或
  public-fact PASS 证据。

## Findings

### P1 — Service startup failure bypasses cleanup in two nodeids

`test_compose_remote_client_commit_pinned_read_inside_network` 和
`test_compose_remote_client_commit_pinned_read_from_gate_host` 在进入 `try` 前调用
`start_p2r2_service`（`tests/test_versioned_read_compose_e2e.py:94-101`、`:154-161`）。该
helper 已可能完成 `compose up`、创建 volume/network/container，但 readiness timeout、
`compose ps` 失败或 image/user probe 失败会使赋值异常，`finally` 根本不会建立。此时生成的
project 资源没有 bounded cleanup，违反设计 §5.1/§6 的 expected-failure cleanup 条件。

修复应让资源启动和后续断言处于可达的 `finally`，预先保存 project/env，并在启动部分失败时
仍执行 scoped `down -v --remove-orphans` 与零残留 inventory；不能用 skip 或 host-only smoke
替代失败路径证明。

### P1 — Hold helper is outside the inventory and removal failure is ignored

`snapshot_hold_command` 创建未带 Compose project label 的独立容器
(`tests/support/compose_lifecycle_harness.py:843-864`)；`project_inventory` 只查询 Compose
project label (`:687-710`)，因此 hold 容器不会出现在最终 inventory。`remove_hold_container`
又忽略 `docker rm -f` 的返回码 (`:1261-1269`)。在 signal/timeout、daemon error 或 name
collision 时，残留 hold 容器可被吞掉，而 cleanup 仍报告 project inventory 为空，不能满足
S7 要求的 zero-container/process cleanup。

修复必须把 hold 纳入生成资源的显式 inventory，或在移除后用 scoped inspect/`ps` 断言其确实
不存在，并传播非零删除结果；expected failure 和 `finally` 都必须走同一证明。

### P1 — No per-node process/thread/Dolt/query-temp cleanup proof

`DockerObjectInventory` 只包含 containers、networks、volumes
(`tests/support/compose_lifecycle_harness.py:133-140`)，`project_inventory` 也只返回这三类
(`:705-710`)。四个 nodeid 没有检查 Service 内的 child process/thread、Dolt child、query
temporary files 或 test work-root；inside-network nodeid 只查询遗留 client container
(`tests/test_versioned_read_compose_e2e.py:112-125`)。这不足以证明 formal design §6 和
acceptance matrix 要求的每个 nodeid zero process/thread/query-temp residual，不能进入
container gate。

修复应复用既有 lifecycle/Dolt cleanup owner，按 nodeid 收集并断言 bounded、project-scoped
的 process/thread/Dolt/query-temp/work-root inventory；不能以容器删除推断所有内部资源已归零。

### P1 — Gate-host client inherits Docker control environment

`host_runner_env` 从 `os.environ.copy()` 开始，只移除 `PYTHONHOME`、`PYTHONPATH` 和
`VIRTUAL_ENV` (`tests/support/compose_lifecycle_harness.py:1022-1039`)。因此 gate host 若设置
`DOCKER_HOST` 或相关 Docker credential/context 变量，test-only client 会继承 Docker API
边界，违背设计 §5.2 的“不接收 Docker socket/host control”约束。现有 unit 只验证
`ephemeral_client_env`，没有覆盖 host runner 的 Docker 环境清除。

修复应使用最小 allowlist 环境，或至少显式删除 `DOCKER_HOST`、Docker context/credential
变量，并增加负向测试；不能把 inherited environment 当作无害输入。

### P1 — Fixed-time unit test is missing `serial`

`test_wait_healthy_times_out_when_readiness_missing` 使用 `time.monotonic`、polling timeout
和 `time.sleep` patch (`tests/test_compose_lifecycle_harness.py:503-515`)，但文件只有模块级
`pytestmark = pytest.mark.unit`，没有 `pytest.mark.serial`。这违反仓库硬约束中“依赖固定时间
预算的测试必须加 serial”，也使该测试不能作为严格 marker/时序门禁下的有效证据。

修复应标记 `unit` + `serial` 并在 serial focused 命令中验证；不应通过删掉 timeout 断言来规避
分类。

### P1 — Required negative probes and their cleanup evidence are absent

S7-2 明确要求在 harness 边界支持时覆盖 missing readiness、wrong token、wrong network 和
non-empty restore target 的 focused negative probes。当前实现只有 parser/classifier unit
case；四个 Compose nodeid 只运行成功路径，未执行 wrong-token/network 或 readiness failure
后的 scoped cleanup。因而“expected failure cleanup”没有行为证据，且 `classify_client_auth_failure`
并未被实际 client boundary 使用来证明错误路径。

修复应增加独立、带 `integration`/`serial` 分类的负向 probe，逐项记录错误分类和 zero residual；
若某 probe 无法在当前边界实现，应在 owning step 明确记录 no-go，而不是把 parser unit 结果
当作容器行为证明。

## Non-findings

- Compose rendered boundary 检查拒绝 Service host ports、Docker socket、host-root mount 和
  resident client/snapshot service；其 focused 参数化测试通过。
- client image 使用 locked `repository_client` project、candidate/lock labels、只读 fixture
  bind mount，且不会写入 production Compose dependency。
- consumer summary 只允许 typed `status/repository_id/c0/c1/c2/main_commit`，并断言 c0/c1/c2
  distinct 且 `main=c2`；README 与 formal 四项 nodeid inventory 一致。

## Verdict

```yaml
review_status: fail
reviewed_commits: 10f84a19e47fb6991dba53318efd9c44024cdf69..5aea9dd9796957d5db10335884c5f91955a43b4b
finding_count: 6
blocker_count: 6
allow_provisional_image: no
production_code_changed_by_review: no
container_rebuild_required: yes
container_gate_for_current_head: deferred
next: return to S7-2/S7-3; repair cleanup, boundary and marker findings before S7-5
phase_2_complete: no
```

本审核不启动 Docker gate，也不把 focused unit 通过或旧 image 证据升级为 S7 PASS。修复
S7-2/S7-3 后必须重新进行独立 harness review，再进入 S7-5 provisional image。

# P2-R6-S7 — Harness Implementation Re-review

状态：`fail`

日期：2026-08-16

本记录复审 `2264ecc787704373e95b6c5daf5eff448793f8ec`，并对照此前的
[S7-4 fail review](p2-r6-s7-step-4-harness-review.md) 逐项核对修复。复审只读，不修改
production、Compose、Dockerfile 或测试实现；未运行 Docker/Compose gate。

## Identity and verification

```yaml
branch: phase1/gate-ownership-repair
reviewed_head: 2264ecc787704373e95b6c5daf5eff448793f8ec
reviewed_parent: 5aea9dd9796957d5db10335884c5f91955a43b4b
review_worktree_clean_at_start: no
untracked_preexisting_review_record: docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-4-harness-review.md
production_code_changed_by_review: no
compose_or_docker_input_changed_by_review: no
container_rebuild_required: yes
container_rebuild_reason: S7 harness, client Dockerfile boundary and negative probes changed
last_verified_image_revision: none
container_gate_for_current_head: deferred
phase_2_complete: no
```

已执行：

- `uv run pytest -m unit tests/test_compose_lifecycle_harness.py tests/test_versioned_read_compose_e2e.py`：`73 passed`；
- serial focused collect：timeout unit 与 4 个 negative probe 均收集，`5/77`；
- touched repository-service `ruff`、`mypy`、`git diff --check`：通过。

以上不包含 Docker 运行结果，不能作为 Compose PASS。

## Previous findings disposition

- startup failure cleanup：`p2r2_project_session` 已覆盖四个 gate nodeid，修复有效；
- hold inventory/removal：project/role labels、inspect-after-rm 和错误传播已加入，修复有效；
- query-temp、Dolt、snapshot-check temp、work-root、host client PID：已有 baseline/inventory
  接线，但见下方 residual finding；
- gate-host Docker control environment：allowlist 并移除 `DOCKER_*`，修复有效；
- fixed-time marker：timeout unit 已标 `serial`，修复有效；
- negative probe inventory：4 个 probe、精确 collect 和 README/testing-conventions ignore
  已加入，但 wrong-token 行为仍失败，见下方 finding。

## Findings

### P1 — Cleanup can abort before scoped teardown

`cleanup_compose_project` 在执行 `docker compose down -v --remove-orphans` 之前调用
`collect_project_query_temps` 和 `list_project_container_dolt`，并在发现任一残留时直接抛出
(`tests/support/compose_lifecycle_harness.py:893-915`)。因此 failure/timeout 路径若确实留下
query temp 或 Dolt child，`p2r2_project_session` 的 `finally` 会进入 cleanup，但 cleanup
会在 teardown 前退出，project/container/network/volume 仍然存在；后续 zero-inventory 断言
也不会执行。这与 S7 §5.1、§6 的“清理必须在 expected failure 后仍完成”相反。

修复必须先执行 scoped teardown（同时保留残留快照/证据），再做 query-temp/Dolt/volume/
process assertions；任何 assertion 失败都不能跳过 `down` 和 hold removal。

### P1 — Real wrong-token probe is classified as `failed`, not `unauthorized`

`test_compose_wrong_token_cleans_up` 断言 `classify_completed_client(completed) == "unauthorized"`
(`tests/test_compose_lifecycle_negative_probes.py:121-128`)。但真实 consumer 的异常出口只打印
`str(exc)` (`repository_client/tests/support/versioned_fixture_consumer.py:904-907`)，而
`RepositoryClientError.__str__` 只包含 `SimpleError.message`，不会包含 `status_code`。Service
401 的 message 是 `missing or invalid bearer token`；因此 stderr 不匹配
`_HTTP_STATUS`，`classify_completed_client` 会返回 `failed`。现有 unit 只使用人工构造的
`status_code=401` stderr，不能证明真实 wrong-token probe。

修复应让错误分类使用结构化、已脱敏的 HTTP status（或让 test-only consumer 以 typed summary
返回 status），并增加与真实 client stderr/response 形状一致的 unit；不能把 synthetic
`status_code=401` 当作容器 probe 通过。

### P1 — Thread residuals still have no baseline or assertion

新增 baseline 覆盖 Dolt PID、snapshot-check temp、work-root 和 host consumer PID
(`tests/support/compose_lifecycle_harness.py:1658-1688`)，但没有 thread baseline、thread
owner 或 teardown assertion。S7 design §6/acceptance matrix 要求每个 nodeid 的
process/thread/Dolt/query-temp cleanup；当前实现仍无法证明 thread residual 为零。容器删除
和 host PID 差分不能替代线程证明。

修复应明确 S7 harness 产生的 thread owner，采集入口/退出前后的 bounded thread baseline
并断言无新增线程；若该边界不产生可审计线程，应在 harness contract 中固定并测试这一事实。

## Verdict

```yaml
review_status: fail
reviewed_head: 2264ecc787704373e95b6c5daf5eff448793f8ec
finding_count: 3
blocker_count: 3
allow_provisional_image: no
container_rebuild_required: yes
container_gate_for_current_head: deferred
next: return to S7-2/S7-3; repair cleanup ordering, real 401 classification and thread ownership
phase_2_complete: no
```

在上述 finding 修复并重新进行独立 S7-4 review 前，不得进入 S7-5，也不得把 focused/serial
结果或旧 image 证据写成当前 candidate 的 Compose PASS。

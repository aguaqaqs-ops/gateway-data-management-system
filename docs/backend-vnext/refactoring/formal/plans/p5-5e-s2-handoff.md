# P5-5E-S2 Compare Accept Handoff（Review-Fix Round 5）

状态：**review-fix round 5 完成 — 不签署 `p5_5e_s2_stage_exit`**

日期：2026-09-24

Owner：History Application

## Authority gate snapshot

```yaml
p5_5e_s1_stage_exit: pass
p5_5e_s2_kickoff: pass
p5_5e_s2_stage_exit: not_evaluated
implementation_authorized: S2 only
workspace_schema_version: 6
compare_implemented: yes
integrity_closed: partial
compose_journey: deferred_to_s3
production_deployment_authorized: no
next_step: P5-5E-S3
```

## Traceability

```yaml
stage: P5-5E-S2-compare-accept-execution-result-read-review-fix-round-5
parent_plan: docs/backend-vnext/refactoring/formal/plans/p5-5e-history-compare-execution-plan.md
implementation_parent_head: a2f8a0a2b0f892020f49a6676e535355b8674645
review_fix_head: uncommitted worktree (round 5)
uv_lock_in_diff: no
```

## Review-fix round 5 摘要

本轮按执行计划收口 S2 第五轮：**cancel release 判别测试、进程级 bundle 路由探针、F1 kinds 去跳过、台账勘误**。不改设计、不扩能力面；**不触发 fresh 镜像重建**（未触碰 production wiring）。

### T7-1 — fixed

| 项 | 回归测试 | 反事实 |
| --- | --- | --- |
| cancel release 判别 | `test_cancel_at_assemble_entry_releases_materialize_checkpoint_protection` | 注释 `compare_jobs.py` `_release_history_compare_step_protection`（L1769）→ materialize checkpoint protection 残留转红 |
| 现有两条空集断言 | `test_cancel_before_materialize_*`、`test_confirmed_integrity_incident_*`（注释：无凭空多 pin，不判别 release 丢失） | — |

### T7-2 — fixed

| 项 | 回归测试 |
| --- | --- |
| drain 窗口 bundle 探针 | `test_uvicorn_sigterm_rejects_new_history_compare_while_reads_remain` 补 `GET .../bundle` → 404 `RESOURCE_NOT_FOUND` |
| reads remain 探测集 | list (`GET /v1/history`) + result (`GET /v1/history-compares/{id}`) + bundle 404 语义探针 |

### T7-3 — fixed

| 项 | 回归测试 |
| --- | --- |
| F1 kinds 去跳过 | `test_f1_policy_binding_integration_cases` 无条件 `assert kinds == list(expected_kinds)`（含 `pseudo_blank` / `keyed_ignored_column` 空元组） |

### T7-4 — fixed

| 项 | 要点 |
| --- | --- |
| provenance / §6.3 | 修正 `fresh_build_reason`（`COPY uv.lock` + `uv sync --frozen`，非 `ARG UV_LOCK_SHA256`）；补 `source_tree_sha` / compose sha256 / running image；dolt 未 park 事实表述 |
| Round 4 勘误 | T6-2 #2 反事实：同 key 同 nodes 重放 → **200 + `replayed: true`**（非 202）；T6-2 #3 降级为「无凭空多 pin」 |
| 并发 | `test_concurrent_accept_with_same_idempotency_key_has_single_winner` 败者补 `status_code == 409` |
| 台账 | 执行计划 §3 S2 行 + 预算列外补列；§4 L111 → app-level unit + serial 进程级两类 |

## Review-fix round 4 摘要

本轮按执行计划收口 S2 第四轮：**恢复 `vnext/backend/uv.lock` 并作废 Round 3 漂移锁证据、进程级 admission 屏障、§2 明示缺口、partial 加固、handoff/台账勘误**。不改设计、不扩能力面。

### T6-1 P0 — fixed

| 项 | 修复 | 证据 |
| --- | --- | --- |
| uv.lock 漂移 | `git checkout -- vnext/backend/uv.lock`；`grep -c pypi.org` = 39；wrapper 纪律 | §6.3 lock 恢复披露 |
| Round 3 证据作废 | focused / unit / 容器证据在漂移锁上取得，全部作废 | §6.3 |
| 镜像重建 | lock 进入 Dockerfile → fresh build + 容器门禁 | `p5-5e-s2-compose-gate-provenance.json` |

### T6-2 §2 明示屏障 — fixed

| # | 回归测试 |
| --- | --- |
| 1 | `test_uvicorn_sigterm_rejects_new_history_compare_while_reads_remain`（SIGTERM 后 503 / 409 `ADMISSION_CONFLICT` / `GET /v1/history` 200 / `GET /v1/history-compares/{id}` 200） |
| 2 | `test_history_compare_accept_idempotency_conflict_on_changed_nodes`（同 key 不同 nodes → 409；同 key 同 nodes 重放 → 200 + `replayed: true`） |
| 3 | cancel 路径空集断言（**Round 5 降级**：仅「无凭空多 pin」；release 丢失判别见 `test_cancel_at_assemble_entry_releases_materialize_checkpoint_protection`） |
| 4 | `test_distinct_idempotency_keys_create_independent_accept_chains` |

### T6-3 partial 加固 — fixed

| # | 回归测试 |
| --- | --- |
| 1 | `test_concurrent_accept_with_same_idempotency_key_has_single_winner`（败者显式 replay 或 `IDEMPOTENCY_CONFLICT`，非 500） |
| 2 | `test_replay_requires_current_permission`（改绑两次 `code` + `message` 全等；待 owner 3 裁决后改单码） |
| 3 | F1 ordered 字面 dict + `test_f1_standard_diff_keyed_ignored_column_net_cfg`（`net_cfg` STANDARD_DIFF 忽略 `no` 列） |

### T6-4 文档与小清理 — fixed

| # | 要点 |
| --- | --- |
| handoff | stage→round-4、预算列外去重、Round 3 证据作废披露 |
| digest | `test_materialize_records_integrity_failure_for_corrupt_hidden_summary` 去掉 `startswith`（F5 参数表覆盖精确 digest） |
| F5 | `test_integrity_scenario_parameter_table` 合并 `commit-b` 默认 provider |
| helper | `_table_fingerprint` / `capture_business_table_state` → `tests/support/history_zero_write_tables.py` |

## Review-fix round 3 摘要

本轮按执行计划收口 S2 第三轮：**F5 三场景真实化、Idempotency 直测、cancel 真实路径、T5-2 十一项屏障测试、代码/类型小清理、handoff/台账披露**。不改设计、不扩能力面。

### T5-1 Major — fixed

| 项 | 修复 | 回归测试 |
| --- | --- | --- |
| T5-1a F5 三场景 | `per_read_rows` + `catalog_without` harness；精确 digest/affected_tables 断言 | `test_integrity_scenario_parameter_table`（3/3） |
| T5-1b Idempotency | `_validate_idempotency_key` 模块级 helper + 字节参数表直测 | `IDEMPOTENCY_KEY_VALIDATION_CASES`、`test_validate_idempotency_key_rejects_multibyte_by_bytes_not_chars` |
| T5-1c cancel | 删除 integrity 假 SQL cancel；jobs 未确认 CANCELLED + 已确认 FAILED+incident | `test_cancel_before_materialize_leaves_operation_cancelled`、`test_confirmed_integrity_incident_published_despite_cancel_signal` |

### T5-2 屏障（11 项）— fixed

| # | 回归测试 |
| --- | --- |
| 1 | `test_checkpoint_bytes_tamper_returns_artifact_unavailable`（同长度语义篡改，bounded + memory） |
| 2 | `test_history_compare_cross_scope_node_returns_404_without_disclosure`（repo-2 真实节点 vs 虚构 ref 同码同体） |
| 3 | `HISTORY_ZERO_WRITE_TABLES` 共享；`test_accept_history_compare_is_read_only`、`test_publish_job_does_not_mutate_business_tables` |
| 4 | `test_three_node_compare_job_uses_multi_pair_bundle`（MULTI_PAIR、pair_id、pairs commits、manifest inputs） |
| 5–7 | `test_integrity_gate_rejects_accept_without_persisting_rows`、`test_concurrent_accept_with_same_idempotency_key_has_single_winner`（`serial`）、`test_replay_requires_current_permission` |
| 8–9 | `test_integrity_ack_route_replays_same_resolution_reference`、`test_accept_history_compare_rejects_pending_integrity_incident` |
| 10–11 | `test_create_routes_reject_after_admission_close_while_reads_remain`（含 `GET /v1/history` 200）、`test_admission_first_server_pre_drains_before_super_shutdown`（`serial` + DRAINING 语义断言） |

### T5-3 代码小清理 — fixed

| # | 要点 |
| --- | --- |
| 1 | `database.history_compare` → `HistoryComparePort`（`TYPE_CHECKING`） |
| 2 | 去 worker 双层 bind；唯一绑定点 `history_compare_composition_bundle`（worker 以 submit-bound 为 inner） |
| 4 | `verify_readable` 缺失即 fail-closed |
| 5 | `bundle_reader` 联合类型（`InMemoryBundleReader \| LocalArtifactBundleReader`） |
| 6 | `_integrity_confirmed` 内容轨注释 |
| 7 | `test_get_operation_returns_200` / `test_get_submit_operation_returns_200` 断言 `integrity_incident is None` |

（Round 4 已将 F1 ordered 改为字面 dict，并补 `net_cfg` STANDARD_DIFF 真 keyed 表例。）

## Review-fix round 2 摘要（历史）

本轮按执行计划收口 S2 第二轮：**2 blocker + 11 minor + 4 项 S2 闭合测试 + handoff 修正**。不改设计、不扩能力面。

### T4-1 Blocker — fixed

| 项 | 修复 | 回归测试 |
| --- | --- | --- |
| T4-1a checkpoint digest 校验 | `_load_checkpoint_envelope_from_store` 优先 `locate`；否则 `read_exact` + `verify_readable`；失败 → `404 ARTIFACT_UNAVAILABLE` | `test_checkpoint_bytes_tamper_returns_artifact_unavailable`（**同长度语义篡改**：decode → 改 comparison_digest → re-canonicalize；bounded + memory） |
| T4-1b 字节 Idempotency-Key | 路由按 UTF-8 字节 1..255 校验；模块级 `_validate_idempotency_key` 直测 | `IDEMPOTENCY_KEY_VALIDATION_CASES`、`test_validate_idempotency_key_rejects_multibyte_by_bytes_not_chars`、HTTP ASCII 边界 |

### T4-2 Minor（11 项）— fixed

| # | 修复要点 | owner 测试 |
| --- | --- | --- |
| 1 | `last_observed_at` 移至第二次 materialize 之后 | `test_row_digest_mismatch_publishes_integrity_incident` |
| 2 | `accept_compare_operation` registry `ValueError` → `503 SERVICE_NOT_READY` | `test_production_wiring` |
| 3 | pair/record_count/bundle_digest 解析失败 → `404 ARTIFACT_UNAVAILABLE` | `test_get_history_compare_result_*` |
| 4 | **删除** `_integrity_confirmed` 分支 2（owner 项 13 闭合） | `test_integrity_confirmed_allows_drifting_observed_digest` |
| 5 | 删除死异常 `HistoryCompareIntegrityAckUnavailable` | integrity-ack 路由测试 |
| 6 | `Sha256Digest` / `HistoryNodeRefResponse` / `integrity_incident` / `updated_at` 类型化 | schema + HTTP 测试 |
| 7 | `HistoryComparePort` import 移入 `TYPE_CHECKING`（property 返回 `Any`） | `test_architecture` |
| 8 | `sqlite_history.py` docstring 同步 T2-5 纪律 | `test_architecture` |
| 9 | `compare_bindings` 白名单注释 | `test_architecture` |
| 10 | dependencies 413 文案中性化 | `test_operation_http` |
| 11 | 去掉双层 `bind_history_compare_transaction_factory` | `test_production_wiring` |

### T4-3 / T4-4 S2 闭合测试 — fixed

| 项 | 回归测试 |
| --- | --- |
| T2-2 publish pin assemble + 清空 step checkpoint protection | `test_publish_pins_assemble_checkpoint_and_clears_step_checkpoints` |
| HTTP validation / ack / scope / bundle | `test_history_compare_http_validation_cases`、`test_integrity_ack_route_*`、`test_history_compare_cross_scope_node_returns_404_without_disclosure`、`test_get_history_compare_bundle_streams_attachment` |
| accept binding 指纹 8 字段 + policy 不敏感 | `test_accept_binding_fingerprint_ignores_table_policies` |
| cancel 竞态 | `test_cancel_before_materialize_leaves_operation_cancelled`、`test_confirmed_integrity_incident_published_despite_cancel_signal` |
| F1 三场景 policy 绑定 | `test_f1_policy_binding_integration_cases` |
| F5 三场景参数表 | `test_integrity_scenario_parameter_table` |
| assemble resume 不重派生 | `test_assemble_resumes_without_rederiving_compare_binding` |
| 零写 checksum | `test_accept_history_compare_is_read_only`、`test_publish_job_does_not_mutate_business_tables` |
| job_payload / business_refs / terminal oracle | `test_job_payload_within_budget_without_table_policies`、`test_accept_operation_sets_business_refs_and_protection_owner`、`test_f1_policy_binding_integration_cases`（oracle digest） |

## 未覆盖项与遗留风险

- **integrity_closed: partial** — 剩余 partial：owner 12 轨 B；replay 改绑待 owner 3 单码裁决；容器不覆盖 result/bundle **成功**读路径（Round 5 bundle 探针仅为 QUEUED 404 语义）。
- 容器门禁**不覆盖** result/bundle 成功读路径（见 §6.3）。
- compose journey 仍归 S3。
- HTTP 多字节 Idempotency 255B 接受：`TestClient`/httpx 无法发送非 ASCII header；路由字节校验由 `IDEMPOTENCY_KEY_VALIDATION_CASES` 直测 `_validate_idempotency_key`，HTTP 接受用 255 ASCII 字节。
- **锁漂移纪律**：Round 3 根因为裸 `uv sync`/`uv lock` 改写 `vnext/backend/uv.lock`；须全程 `uv-consume.sh`。`run-tests.sh` 前置 `git diff --exit-code -- vnext/*/uv.lock` 为计划外增强，**待 owner 追认**。

## §6.3 运行镜像证据（review-fix round 4；Round 5 未重跑容器门禁）

```
uv_lock_drift_event:
  when: 2026-09-24
  cause: 内网 mirror 隐式改写 vnext/backend/uv.lock（pypi.org 计数归零）
  recovery: git checkout -- vnext/backend/uv.lock（禁止 uv lock / uv sync）
  pypi_org_count_after_recovery: 39
round_3_evidence_invalidated:
  - focused 8 files / 161 passed（漂移锁上取得）
  - 容器门禁 2 passed（漂移锁语境）
source_tree_sha: a2f8a0a2b0f892020f49a6676e535355b8674645
gate_tested_head: a2f8a0a2b0f892020f49a6676e535355b8674645 (+ round-4 worktree, uncommitted)
vnext/deploy/compose.yaml_sha256: f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0
fresh_build: yes (Round 4 only; Round 5 未触发重建)
重建理由: backend Dockerfile COPY backend/uv.lock + uv sync --frozen（非 repository_service 的 ARG UV_LOCK_SHA256）
五锁 SHA:
  shared_kernel: 7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898
  repository_contracts: b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3
  repository_client: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
  repository_service: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
  backend: 21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea
focused 测试摘要 (Round 5):
  - S2 focused (9 files): 168 passed
  - 五包 ruff + mypy: all pass
  - pytest -m unit → 2465 passed（dolt 未 park：/usr/local/bin 对 dev 只读；marker 纯度由逐文件审查确认）
round_5_fresh_build: no（未触碰 runtime/dependencies/wiring/routes/operation_worker）
容器门禁结果 (Round 4 证据):
  - tests/test_backend_http_container_gate.py: 2 passed
  - running_image: gateway-backend-gate-test_backend_container_ready_a0-backend:latest
  - image_revision: sha256:0dd74b005f9fc0dfc6369ba6172b7c364dd6223eae1b97bcc92c11b37ed3909d
注: 容器门禁不覆盖 result/bundle 成功读路径
```

## Focused 命令（权威口径）

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_history_compare_transactions.py tests/test_history_compare_jobs.py \
  tests/test_history_compare_integrity.py tests/test_history_http.py \
  tests/test_operation_http.py   tests/test_http_admission_shutdown.py tests/test_http_admission_shutdown_process.py \
  tests/test_architecture.py tests/test_production_wiring.py
```

## 预算列外文件（本 round 披露）

- `tests/test_http_admission_shutdown_process.py` — serial 进程级 admission/bundle 探针
- `tests/support/http_shutdown_harness.py` — 进程级 seed/session helper
- `application/submission/ports.py` — submit 事务端口（review seed 依赖）
- `tests/test_preview_read_http.py` — preview 读路径（共享 harness）
- `tests/test_review_persistence.py` — review 持久化（seed 依赖）
- `tests/test_submit_control_db_migrations.py` — control DB 迁移（seed 依赖）
- `tests/test_workspace_control_db_migrations.py` — workspace 迁移（seed 依赖）
- `application/history/ports.py` — `HistoryComparePort` 契约
- `application/history/compare_bindings.py` — binding 派生
- `application/history/errors.py` — 错误类型清理
- `infrastructure/control_db/sqlite_history_compare.py` — integrity/acceptance 持久化
- `tests/support/history_compare_job_harness.py` — ordered/net_cfg provider + per-read rows/catalog 子集
- `tests/support/http_shutdown_harness.py` — 进程级 history compare seed + session helper
- `tests/support/repository_ref_materialization.py` — per-read rows + catalog_without
- `tests/support/history_zero_write_tables.py` — 零写表共享清单 + fingerprint helper
- `http/schemas/constraints.py` — `Sha256Digest` 等
- `http/schemas/history.py`、`http/schemas/operation.py` — 响应类型化
- `tests/support/http_workspace_harness.py` — artifact_store/bundle_reader 注入
- `tests/test_production_wiring.py` — wiring 断言

## awaiting owner decision（§5，原样保留，本轮不改行为）

1. §5.4 结构不同 table → 表级 DEGRADED vs 实现整 job FAILED
2. §6.2 `acquire_new_work`（closed→429）vs DRAINING→409
3. §7.2 history 读侧 mapping 缺失 → 403 vs E 全局 404 helper
4. `StoreBusy` → 500（E 级缺口，非 S2 引入）
5. v6 两表缺 FK `operation_id → operation_records`
6. pending 形状缺 `step?` 字段
7. GET incident camelCase 注记矛盾
8. §8 唯一 owner 表双 owner / 错位
9. **已补列（见计划 §3），待 owner 追认**
10. §10 停止线 9：row-digest 轨在 materialization 补齐 refs 后应不可达
11. 设计勘误候选（v6 时间戳列、索引、decoder identity 短 token）
12. **轨 B 是否强制两次 observed 全等**（设计字面 vs 实现；分支 2 已删除）
13. ~~`_integrity_confirmed` 分支 2~~ → **已闭合（删除）**
14. **SUCCEEDED 后 pin 集合无 unpin 通路、随 compare 次数增长**（对标 E preview supersede）→ **awaiting owner decision**
15. **M12**：三节点 MULTI_PAIR bundle manifest 字段（`test_three_node_compare_job_uses_multi_pair_bundle`）— **closed（round 3）**

## 范围声明

- 本 handoff **不** 签署 `p5_5e_s2_stage_exit`
- 本 handoff **不** 授权 production deployment
- compose journey 仍归 S3

# P5-5E-S3 Production Wiring & Compose Journey Handoff

状态：**S3 remediation in progress — author handoff（未签署 slice exit）**

日期：2026-09-25

Owner：History Application / Deployment

## Authority gate snapshot

```yaml
p5_5e_s2_stage_exit: pass
p5_5e_s3_implementation_authorized: yes
p5_5e_s3_stage_exit: not_evaluated
compose_journey: remediation_in_progress
production_deployment_authorized: no
next_step: P5-5E-S4
```

## Traceability

```yaml
stage: P5-5E-S3-production-wiring-compose-journey
parent_plan: docs/backend-vnext/refactoring/formal/plans/p5-5e-history-compare-execution-plan.md
parent_head_at_handoff: 25f2c916249403430095b1f47a1dc8911a06542d
s3_candidate: working tree (compose harness + e2e + deploy surface + worker diagnostic)
compose_gate_provenance: docs/backend-vnext/refactoring/formal/plans/p5-5e-s3-compose-gate-provenance.json
```

## 交付物

| 路径 | 说明 |
| --- | --- |
| `vnext/deploy/config/session.json` | `documented_permissions` 列出 `read_project_history`；`local-dev-session-token` **未**授予 |
| `vnext/deploy/README.md` | 权限表含 `read_project_history`（与四权限无继承） |
| `vnext/backend/tests/test_history_compose_e2e.py` | 正式三容器 compose 旅程（真实空 commit、零写 manifest、A↔B oracle、restart） |
| `vnext/backend/tests/test_ordered_submit_bisect_compose.py` | T3 三组对照（C 空 baseline / B′ `DECIMAL(10,2)` / A′ sized ordered） |
| `vnext/backend/tests/test_ordered_compare_compose.py` | ordered 双 submit + history compare（policy checkpoint + materialize oracle） |
| `vnext/backend/tests/test_storage_projection_integrity.py` | F2 单元证据参数表 `test_storage_projection_scalar_type_vocabulary_cases` |
| `vnext/backend/tests/test_repository_import_artifact_diagnostics.py` | submit 诊断含 code + message + table |
| `vnext/backend/tests/test_compose_gate_provenance.py` | dirty tree `source_tree_sha` 可复现性单测 |
| `vnext/backend/tests/support/compose_gate_harness.py` | temp-index provenance（`repo_root` 参数）、`cleanup_compose_project_artifacts`、ordered upload helpers、materialize oracle helper |
| `vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py` | `_resolve_declared_scalar_type`（`VARCHAR(n)`/`BIGINT` 归一化） |
| `vnext/backend/src/gateway_backend/application/submit_jobs.py` | prepare projection 失败 → operation `FAILED` |
| `vnext/backend/src/gateway_backend/application/submission/errors.py` | `SubmitImportPublicationError` 应用层异常 |
| `vnext/backend/src/gateway_backend/repository_import_artifact.py` | projection 失败首条 diagnostic 格式化 |
| `vnext/backend/tests/support/history_compare_oracle.py` | remote≡local comparison digest oracle |
| `vnext/backend/src/gateway_backend/bootstrap/operation_worker.py` | executor 异常 type/message/traceback 诊断 |
| `vnext/backend/tests/test_http_auth_matrix.py` | `POST /v1/history-compares` 无 `read_project_history` → 403 |

`deploy/compose.yaml`：**无改动**（符合执行计划预期）。

## Unmet / Blocked 清单（remediation 前基线）

| 项 | 状态 | Owner | 关闭节点 |
| --- | --- | --- | --- |
| F1 零表腿（真实空 commit） | unmet → 见下方 closed | History Application | T1 e2e + digest 证据 |
| F2 ordered gid/no 真实 pair | unmet → 见下方 closed | History Application | storage projection 类型归一化 + ordered compare compose |
| F3 ordered submit 崩溃 | unmet → 见下方 closed | Submit / Storage Projection | prepare FAILED 终态 + B′ 断言 |
| F4 manifest 零写第三子项 | unmet → 见下方 closed | History Application | T4 `r4-manifest-` 前缀断言 |
| F5 deploy 权限面 | unmet → 见下方 closed | Deployment | T5 README + session 断言 |
| F6 §8 compose owner（oracle + restart history） | unmet → 见下方 closed | History Application | T6 |
| F7 精度（docker/provenance/finally/命名） | unmet → 见下方 closed | History Application | T7 |
| F8 门禁与 provenance | unmet → 见下方 closed | History Application | T8 |

## Submit / worker runtime（非 5E deferred，单列）

| 项 | 状态 | Owner | 关闭节点 |
| --- | --- | --- | --- |
| sized 类型 submit `UNSUPPORTED_TABLE`（已支持 `VARCHAR(n)`/`BIGINT`） | closed | Storage Projection | `_resolve_declared_scalar_type`；仍不支持类型（如 `DECIMAL`）见 B′ |
| prepare 投影公布失败 → operation FAILED + occupancy 释放 | closed | Submit runtime | `abort_prepared_submit_in_control_transaction` + `_publish_prepare_projection_failure`；`test_prepare_handler_publication_failure_marks_operation_failed`；B′ 同 workspace 再提交 compose |

### F2 定性（storage projection 词表 vs repository 原样上报）

根因 **非** ordered 表 submit 特异：`capabilities/storage_projection/project.py` 声明类型词表仅 `INT` / `INT UNSIGNED` / `VARCHAR`（`:78-82`）；repository `normalize_sql_type` 对 `varchar(8)` 保留 `VARCHAR(8)`（`arrow_mapping.py:297-354`）；`_codec_for` 在 `:537-545` 对未入词表列返回 `UNSUPPORTED_TABLE`。ordered 表 `gid` 列在 `GID_NO_V1` 下 `:505-511` 硬绕过为 `INT UNSIGNED`，**不能**掩盖同表 `value VARCHAR(8)` 或普通表 `BIGINT` 失败。

单元证据（`test_storage_projection_integrity.py`）：

| Case | 输入 | 预期 |
| --- | --- | --- |
| `ordered_vocab` | ordered + bare `VARCHAR`/`INT` | `COMPLETE` |
| `ordered_sized_varchar` | ordered + `VARCHAR(8)` | `COMPLETE`（归一化后） |
| `plain_sized_varchar` | `t3(label VARCHAR(8))` | `COMPLETE` |
| `plain_bigint` | `t4(big BIGINT)` | `COMPLETE`（64-bit `SIGNED_INTEGER`） |
| `bigint_above_int32_max` / `bigint_large_positive` / `bigint_below_int32_min` | `BIGINT` 边界值 | `COMPLETE` |
| `unsupported_decimal` | `t5(amount DECIMAL(10,2))` | `FAILED` |

ordered `gid` 保持 catalog `INT UNSIGNED`（32-bit，值域 `0..4294967295`）。现场 gid 在该范围内；越界由 cell/codec 失败处理，区别于词表 `UNSUPPORTED_TABLE`。

（owner：`test_storage_projection_integrity.py::test_storage_projection_scalar_type_vocabulary_cases`；映射统一见 ADR 0017）

一次性核对命令：

```bash
cd vnext/repository_service && ../scripts/uv-consume.sh -C . run python -c \
  "from gateway_repository_service.arrow_mapping import normalize_sql_type; print(normalize_sql_type('varchar','varchar(8)'))"
# 期望输出: VARCHAR(8)
```

**T3 bisect 结论（对照实验）**：

| Case | 内容 | 预期 |
| --- | --- | --- |
| C | 空 baseline + 标准 `modified_table_upload_files` | submit **SUCCEEDED** |
| B′ | 普通新表 `t3(amount DECIMAL(10,2))` | submit **FAILED**；operation diagnostic `UNSUPPORTED_TABLE` + `column scalar_type is not supported` + `table=t3` |
| A′ | ordered sized DDL（`VARCHAR(8)`/`BIGINT` 经归一化） | submit **SUCCEEDED** |

submit 诊断格式（T-2）：`storage projection failed: UNSUPPORTED_TABLE: column scalar_type is not supported (table=…)`

## 零写证据（三项）

1. 业务表：`HISTORY_ZERO_WRITE_TABLES` row-count + row-set SHA256；compare 前后相等。
2. Repository：`list_repository_commit_ids` compare 前后集合相等。
3. **Canonicalization manifest（决策 (a)）**：`artifact_root` 内 `artifact_id` 前缀 `r4-manifest-` 的条目集合 compare 前后不变（不用 `media_type=application/json` 过滤）。命名空间依据 `storage_projection/publish.py:171`。

## Ordered policy / integrity

- **Ordered（gid/no）**：**closed**（F2，ADR 0017）。`test_ordered_compare_compose.py` 双 submit + history compare；materialize checkpoint `table_policies[0]==ORDERED_SYX_TABLE_EXPECTED_POLICY`；oracle = 容器内重跑 bind→plan→compare digest 一致性（`oracle_history_compare_digest_from_materialize_checkpoint`）；语义断言经 `ordered_compare_facts_from_materialize_checkpoint`（非 DEGRADED + `ORDERED_ROW_*` by gid）。policy 绑定 owner：S2 `test_history_compare_jobs.py::test_f1_policy_binding_integration_cases` + compose ordered 旅程。
- **Integrity 类 (c)**：compose 不复现 incident；引用 S2 `test_history_compare_integrity.py` 三场景参数表。

## §6.3 运行镜像证据

| 项 | 值 |
| --- | --- |
| gate_tested_head | `13068babaeeccaf9e71d7c1d0bc6ddd893fc5514`（ADR 0017 remediation round 2） |
| worktree_clean | true（gate 后 provenance 写入） |
| source_tree_sha | `abd5d807b5ac574e54efe1816eb22056589c7326`（clean commit 临时索引） |
| source_tree_sha_command | `GIT_INDEX_FILE=$(mktemp) && git -C "$REPO_ROOT" read-tree HEAD && git -C "$REPO_ROOT" add -A && git -C "$REPO_ROOT" write-tree`（clean tree：`git -C "$REPO_ROOT" rev-parse 'HEAD^{tree}'`） |
| source_tree_sha_excludes | full repo tree via temporary index（含 unstaged + untracked）；非 `HEAD^{tree}` 快照 |
| docker 残留清理 | `compose down -v --remove-orphans` + `docker volume rm`（`label=com.docker.compose.project=<project>`）+ `docker network rm`（同 label）；`ordered-debug*` / `gateway-submit-debug*` 容器已清理 |
| fresh_build | yes（backend/worker）；见 provenance JSON |
| S3 focused | `2493 passed, 0 skipped`（`-m unit`）+ compose 串行 3/3 |
| backend image | `sha256:c1c513f4a35a6f69841e535fa33b930559ecfe2488b54c8da7a20ec3508c3dc5` |
| worker image | `sha256:dd3029ca4fcda035322890150671beb5ab6cbe862dd9c28cd53dd7fc984c2db1` |
| 零表 pair digest | `sha256:42861bfe…`（**content-stable across runs**；4 次独立运行同值；可交叉核对 veto 证据） |
| 零表 bundle digest | run-scoped（观测 3 次三值；journey IDs/commit IDs 每轮 compose 不同） |

权威 provenance: `docs/backend-vnext/refactoring/formal/plans/p5-5e-s3-compose-gate-provenance.json`

## Unmet → Closed 映射表

| ID | 关闭条件 | 状态 |
| --- | --- | --- |
| F1 | INITIAL==POST 空 commit；零表 pair `record_count==1`；digest 入证 | **closed** |
| F2 | storage projection 类型归一化 → compose 真实 DDL ordered pair | **closed** |
| F3 | prepare FAILED 终态 + B′ DECIMAL 负例 + diagnostic 断言 | **closed** |
| F4 | manifest 前缀集合断言 | **closed** |
| F5 | README + session 断言 | **closed** |
| F6 | oracle ≥1 pair（A↔B）；restart history head 不变；restart 后 idempotent replay | **closed** |
| F7 | T7 清理项 | **closed** |
| F8 | focused + ruff/mypy + 0 skipped | **closed** |

## 范围声明

- 本 handoff **不** 授权 production deployment
- `p5_5e_slice_exit` **未** 签署（S4 权威 runner + 全量容器并合）

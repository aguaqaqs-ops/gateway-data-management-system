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
parent_head_at_handoff: a8c955171cc909a4bddf1bb74978daba50cedda6
s3_candidate: 205e43da8504f72ca77f0255040c1b70dc7745f8
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
| `unsupported_decimal_single_precision` | `t5(amount DECIMAL(10))` | `FAILED`（mapper 可解析；投影词表仍拒绝 DECIMAL 族） |
| `bigint_unsigned` | `t6(big BIGINT UNSIGNED)` | `FAILED` |

**词表边界（round 3）**：投影 `_resolve_declared_scalar_type` 仅放行 signed `{32,64}` + unsigned `32`。
`TINYINT`/`SMALLINT`/`MEDIUMINT`、`BIGINT UNSIGNED` 等仍 `UNSUPPORTED_TABLE`；`SET` 拼写经共享 mapper 映射为 `STRING`（守卫见 `test_sql_declared_type_mapping.py`）。

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
| B′ | 普通新表 `t3(amount DECIMAL(10,2))` | submit **FAILED**；operation diagnostic `UNSUPPORTED_TABLE` + `column scalar_type is not supported` + `table=t3`；同 workspace 重 accept **409**；retry accept **202** + 终态 **SUCCEEDED** |
| A′ | ordered sized DDL（`VARCHAR(8)`/`BIGINT` 经归一化） | submit **SUCCEEDED** |

submit 诊断格式（T-2）：`storage projection failed: UNSUPPORTED_TABLE: column scalar_type is not supported (table=…)`

## 零写证据（三项）

1. 业务表：`HISTORY_ZERO_WRITE_TABLES` row-count + row-set SHA256；compare 前后相等。
2. Repository：`list_repository_commit_ids` compare 前后集合相等。
3. **Canonicalization manifest（决策 (a)）**：`artifact_root` 内 `artifact_id` 前缀 `r4-manifest-` 的条目集合 compare 前后不变（不用 `media_type=application/json` 过滤）。命名空间依据 `storage_projection/publish.py:171`。

## Ordered policy / integrity

- **Ordered（gid/no）**：**closed**（F2，ADR 0017）。`test_ordered_compare_compose.py` 双 submit + history compare；materialize checkpoint `table_policies[0]==ORDERED_SYX_TABLE_EXPECTED_POLICY`；oracle = 容器内重跑 bind→plan→compare digest 一致性（`oracle_history_compare_digest_from_materialize_checkpoint`）；语义断言经 `ordered_compare_facts_from_materialize_checkpoint`（非 DEGRADED + `ORDERED_ROW_ADDED`/`DELETED`/`MODIFIED`）。policy 绑定 owner：S2 `test_history_compare_jobs.py::test_f1_policy_binding_integration_cases` + compose ordered 旅程。
- **Integrity 类 (c)**：compose 不复现 incident；引用 S2 `test_history_compare_integrity.py` 三场景参数表。

## §6.3 运行镜像证据

| 项 | 值 |
| --- | --- |
| gate_tested_head | `205e43da8504f72ca77f0255040c1b70dc7745f8`（S3 remediation round 3） |
| worktree_clean | true（gate 后 provenance 写入） |
| source_tree_sha | `edac1ad7a191af3954cedc3df810817b1de9b9cd`（clean tree = `HEAD^{tree}` at gate commit） |
| source_tree_sha_command | `git -C "$REPO_ROOT" rev-parse 'HEAD^{tree}'` |
| source_tree_sha_excludes | clean worktree at gate commit only；dirty tree 回退临时索引（见 `compose_gate_harness.source_tree_sha_for_provenance`） |
| S1 对照规则 | 各门禁 `assert_running_backend_worker_images_match_build`：gate running image **==** gate fresh build（backend/worker）；逐门禁见 provenance `running_images_by_gate` |
| reference_deploy_build | **非门禁运行镜像**（`deploy-backend:latest` 等）；见 provenance JSON `reference_deploy_build` |
| running_images_by_gate | `ordered_compare` / `ordered_bisect`（**仅 B′ baseline 子栈**）/ `gateway_history_5e` 三组 `{backend,worker,repository_service}` container_id + immutable image |
| compose 串行 | port **8000** 硬串行点；harness `flock` `/tmp/gateway-compose-gate.lock`；S4 权威 runner 必须单飞（见 `testing-conventions.md`） |
| provenance commits | gated `205e43da`；provenance SHA 对齐 `499468f362`（docs-only）；N1–N6 harness/test 变更不刷新 S3 stage exit 证据 |
| docker 残留清理 | `compose down -v --remove-orphans` + volume/network label 清理 |
| fresh_build | yes（backend/worker per gate）；见 provenance JSON |
| S3 focused | `2508 passed, 0 skipped`（`-m unit`）+ compose 串行 3/3 |
| 零表 pair digest | `sha256:42861bfe…`（content-stable across runs） |

### DECIMAL(10) 回归（round 3）

| 阶段 | 现象 |
| --- | --- |
| 复现前 | `declared_type_for_sql_spelling('DECIMAL(10)')` → `IndexError` |
| 复现后 | `DeclaredType(DECIMAL, precision=10, scale=0)`；`project_storage` 对 `DECIMAL(10)` → `FAILED` + `UNSUPPORTED_TABLE`（无未处理异常） |
| 静态门禁 | mypy 先红（4 errors / 3 files，`no_implicit_reexport`）→ 显式重导出后 `mypy --no-incremental` 五包绿 |

### 已知边界

非 `SubmitImportPublicationError` 的确定性 prepare 失败仍可能不释放 occupancy（仅 `SubmitImportPublicationError` 路径经 `abort_prepared_submit_in_control_transaction` 释放）；B′ compose 在 FAILED 后直接读 control DB 断言 occupancy 已清（非 409 代理），retry accept 202 + `SUCCEEDED` 为可再次提交证明。

**S4 评估（未实施）**：prepare handler 全部确定性异常统一 FAILED + attempt 释放 + compose 断言。

### Mapper 宽容解析（有意）

`DECIMAL(10,)` / `DECIMAL(10, )` → `(precision=10, scale=0)`（mapper 空 scale 段默认 0）。MySQL 会拒绝该 DDL；属测试拼写宽容，非 catalog 语义。

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
| F8 | focused + ruff/mypy（`--no-incremental` 判定）+ 0 skipped + per-gate running image provenance | **closed**（round 3） |

## 范围声明

- 本 handoff **不** 授权 production deployment
- `p5_5e_slice_exit` **未** 签署（S4 权威 runner + 全量容器并合）

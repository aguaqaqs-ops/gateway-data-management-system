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
parent_head_at_handoff: 387174fc85e42d4e30c18ae9c3e3886be254dc3b
s3_candidate: working tree (compose harness + e2e + deploy surface + worker diagnostic)
compose_gate_provenance: docs/backend-vnext/refactoring/formal/plans/p5-5e-s3-compose-gate-provenance.json
```

## 交付物

| 路径 | 说明 |
| --- | --- |
| `vnext/deploy/config/session.json` | `documented_permissions` 列出 `read_project_history`；`local-dev-session-token` **未**授予 |
| `vnext/deploy/README.md` | 权限表含 `read_project_history`（与四权限无继承） |
| `vnext/backend/tests/test_history_compose_e2e.py` | 正式三容器 compose 旅程（真实空 commit、零写 manifest、A↔B oracle、restart） |
| `vnext/backend/tests/test_ordered_submit_bisect_compose.py` | T3 三组对照（C 空 baseline / B′ `VARCHAR(8)` / A′ 词表内 ordered） |
| `vnext/backend/tests/test_storage_projection_integrity.py` | F2 单元证据参数表 `test_storage_projection_scalar_type_vocabulary_cases` |
| `vnext/backend/tests/test_repository_import_artifact_diagnostics.py` | submit 诊断含 code + message + table |
| `vnext/backend/tests/test_compose_gate_provenance.py` | dirty tree `source_tree_sha` 可复现性单测 |
| `vnext/backend/tests/test_ordered_real_ddl_compose.py` | F2 blocked 真实 DDL compose（`xfail strict`） |
| `vnext/backend/tests/support/compose_gate_harness.py` | temp-index provenance、`cleanup_compose_project_artifacts`、ordered upload helpers |
| `vnext/backend/src/gateway_backend/repository_import_artifact.py` | projection 失败首条 diagnostic 格式化 |
| `vnext/backend/tests/support/history_compare_oracle.py` | remote≡local comparison digest oracle |
| `vnext/backend/src/gateway_backend/bootstrap/operation_worker.py` | executor 异常 type/message/traceback 诊断 |
| `vnext/backend/tests/test_http_auth_matrix.py` | `POST /v1/history-compares` 无 `read_project_history` → 403 |

`deploy/compose.yaml`：**无改动**（符合执行计划预期）。

## Unmet / Blocked 清单（remediation 前基线）

| 项 | 状态 | Owner | 关闭节点 |
| --- | --- | --- | --- |
| F1 零表腿（真实空 commit） | unmet → 见下方 closed | History Application | T1 e2e + digest 证据 |
| F2 ordered gid/no 真实 pair | blocked | History Application | storage projection 类型归一化修复后 compose 实跑 ordered pair |
| F3 ordered submit 崩溃 | blocked（外部缺陷） | Submit / Storage Projection | 独立 defect slice；见 §Submit runtime / §F2 定性 |
| F4 manifest 零写第三子项 | unmet → 见下方 closed | History Application | T4 `r4-manifest-` 前缀断言 |
| F5 deploy 权限面 | unmet → 见下方 closed | Deployment | T5 README + session 断言 |
| F6 §8 compose owner（oracle + restart history） | unmet → 见下方 closed | History Application | T6 |
| F7 精度（docker/provenance/finally/命名） | unmet → 见下方 closed | History Application | T7 |
| F8 门禁与 provenance | unmet → 见下方 closed | History Application | T8 |

## Submit / worker runtime（非 5E deferred，单列）

| 项 | 状态 | Owner | 关闭节点 |
| --- | --- | --- | --- |
| sized 类型 submit `UNSUPPORTED_TABLE` | blocked | Submit / Storage Projection | storage projection 类型归一化独立 slice（`capabilities/**` 预算外） |
| 确定性 executor 异常 → operation 永久悬挂 + worker `restart: unless-stopped` 重启循环 | blocked | Operation Lifecycle / Submit runtime | 独立 PR（`B/operations/**` 预算外） |

### F2 定性（storage projection 词表 vs repository 原样上报）

根因 **非** ordered 表 submit 特异：`capabilities/storage_projection/project.py` 声明类型词表仅 `INT` / `INT UNSIGNED` / `VARCHAR`（`:78-82`）；repository `normalize_sql_type` 对 `varchar(8)` 保留 `VARCHAR(8)`（`arrow_mapping.py:297-354`）；`_codec_for` 在 `:537-545` 对未入词表列返回 `UNSUPPORTED_TABLE`。ordered 表 `gid` 列在 `GID_NO_V1` 下 `:505-511` 硬绕过为 `INT UNSIGNED`，**不能**掩盖同表 `value VARCHAR(8)` 或普通表 `BIGINT` 失败。

单元证据（`test_storage_projection_integrity.py`）：

| Case | 输入 | 预期 |
| --- | --- | --- |
| `ordered_vocab` | ordered + bare `VARCHAR`/`INT` | `COMPLETE` |
| `ordered_sized_varchar` | ordered + `VARCHAR(8)` | `FAILED` + `column scalar_type is not supported` |
| `plain_sized_varchar` | `t3(label VARCHAR(8))` | `FAILED` |
| `plain_bigint` | `t4(big BIGINT)` | `FAILED` |

（owner：`test_storage_projection_integrity.py::test_storage_projection_scalar_type_vocabulary_cases`）

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
| B′ | 普通新表 `t3(label VARCHAR(8))` | submit **FAILED**；worker 含 `UNSUPPORTED_TABLE` + `column scalar_type is not supported` + `table=t3` |
| A′ | ordered DDL 词表内类型（仅 `INT` 列；Dolt 要求 `VARCHAR(n)` 无法产出 bare `VARCHAR`） | submit **SUCCEEDED**（证伪 policy 路径；sized `VARCHAR(8)` 失败见 B′ + 单元证据） |

submit 诊断格式（T-2）：`storage projection failed: UNSUPPORTED_TABLE: column scalar_type is not supported (table=…)`

## 零写证据（三项）

1. 业务表：`HISTORY_ZERO_WRITE_TABLES` row-count + row-set SHA256；compare 前后相等。
2. Repository：`list_repository_commit_ids` compare 前后集合相等。
3. **Canonicalization manifest（决策 (a)）**：`artifact_root` 内 `artifact_id` 前缀 `r4-manifest-` 的条目集合 compare 前后不变（不用 `media_type=application/json` 过滤）。命名空间依据 `storage_projection/publish.py:171`。

## Ordered policy / integrity

- **Ordered（gid/no）**：**blocked**（F2）。现实 DDL（`VARCHAR(8)`/`BIGINT`）在 storage projection 词表处失败；compose 以 A↔B 标准 divergent pair 完成 remote≡local oracle。关闭节点：**storage projection 类型归一化修复后**按真实 DDL 实跑 ordered pair；**不再**改派 S2 unit oracle。policy 绑定 owner 仍为 S2 `test_history_compare_jobs.py::test_f1_policy_binding_integration_cases`。
- **Integrity 类 (c)**：compose 不复现 incident；引用 S2 `test_history_compare_integrity.py` 三场景参数表。

## §6.3 运行镜像证据

| 项 | 值 |
| --- | --- |
| gate_tested_head | `387174fc85e42d4e30c18ae9c3e3886be254dc3b` |
| worktree_clean | false |
| source_tree_sha | `9a49190180a111fa6b969062b3443c6cf6c01811`（≠ `HEAD^{tree}` `80fd2894…`） |
| source_tree_sha_command | `GIT_INDEX_FILE=$(mktemp) && git -C "$REPO_ROOT" read-tree HEAD && git -C "$REPO_ROOT" add -A && git -C "$REPO_ROOT" write-tree`（clean tree：`git -C "$REPO_ROOT" rev-parse 'HEAD^{tree}'`） |
| source_tree_sha_excludes | full repo tree via temporary index（含 unstaged + untracked）；非 `HEAD^{tree}` 快照 |
| docker 残留清理 | `compose down -v --remove-orphans` + `docker volume rm`（`label=com.docker.compose.project=<project>`）+ `docker network rm`（同 label）；`ordered-debug*` / `gateway-submit-debug*` 容器已清理 |
| fresh_build | yes（backend/worker）；见 provenance JSON |
| S3 focused | `150 passed, 1 xfailed, 0 skipped` |
| backend image | `sha256:f029860f95002d824e7399fb148723c7971f9d975de2f85d10b3c36d955d884d` |
| worker image | `sha256:60d3e7bed6370f7ed9b3c4cc861a0436a1e6da859cf88f0dcb74b929ba4f1778` |
| 零表 pair digest | `sha256:42861bfe…`（**content-stable across runs**；4 次独立运行同值；可交叉核对 veto 证据） |
| 零表 bundle digest | run-scoped（观测 3 次三值；journey IDs/commit IDs 每轮 compose 不同） |

权威 provenance: `docs/backend-vnext/refactoring/formal/plans/p5-5e-s3-compose-gate-provenance.json`

## Unmet → Closed 映射表

| ID | 关闭条件 | 状态 |
| --- | --- | --- |
| F1 | INITIAL==POST 空 commit；零表 pair `record_count==1`；digest 入证 | **closed** |
| F2 | storage projection 类型归一化 → compose 真实 DDL ordered pair | **blocked**（owner: Storage Projection） |
| F3 | 诊断+bisect+owner 记录 | **closed** |
| F4 | manifest 前缀集合断言 | **closed** |
| F5 | README + session 断言 | **closed** |
| F6 | oracle ≥1 pair（A↔B）；restart history head 不变 | **closed** |
| F7 | T7 清理项 | **closed** |
| F8 | focused + ruff/mypy + 0 skipped | **closed** |

## 范围声明

- 本 handoff **不** 授权 production deployment
- `p5_5e_slice_exit` **未** 签署（S4 权威 runner + 全量容器并合）

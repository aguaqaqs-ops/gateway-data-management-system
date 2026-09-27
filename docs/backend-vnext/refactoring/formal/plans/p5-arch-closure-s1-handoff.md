# P5 架构收口 S1 Handoff

状态：**S1 结构修复完成（待 commit 后 compose 门禁复跑）**

日期：2026-09-27

分支：`p5-closure/s1`（worktree `/home/dev/gdds-p5-closure-s1`）

上游：[执行计划 §2 S1](p5-arch-closure-execution-plan.md)

## 1. 机械验收（import_rules）

在 `vnext/backend` 执行 `python -m tests.support.import_rules`：

| 指标 | 目标 | 实测 |
|------|------|------|
| IMPORT 违例 | 3 | 3（`http_arrow`×2 + `repository_import_artifact`） |
| 运行时环 | 0 | 0 |
| 不可达模块 | 10 | 10 |

`tests/architecture_baseline.py` 与 CLI 输出一致。

composite 内部模块（`_ast` / `_bind` / `_digest` / `materialize`）不在不可达基线中；生产锚点为 `snapshot_materialization.materialize._ensure_composite_signal_production_anchor`（函数内 import `composite_signal.materialize`，不新增 import_rules 违例）。

## 2. 架构测试

```bash
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest tests/test_architecture.py -m unit -q
```

**71 passed**（含 import 基线、运行时环、不可达、capability DAG）。

DAG 增补（行为不变）：

- `snapshot_materialization` → `composite_signal.materialize`（S3 前 compose 仍不可达，经 materialize 锚点拉通 composite 实现模块）
- `storage_projection` → `snapshot_materialization.sql_declared_types`、`table_rules.resolver`

## 3. S1 子步交付摘要

| 子步 | 内容 |
|------|------|
| S1.4 | operations 公开校验、N-infra（control_db 环拆分、`history_reader` 下沉）、N-http-bypass（dependencies/workspace ports）、Preview/History 受理与 `job_definitions` 接线 |
| S1.5 | `application/control_transactions.py`、`application/workspace/ports.py`；control_db 模块级环消除 |
| S1.6 | `application/job_steps.py`、`application/pair_pipeline.py`；preview/history 共用 pair 流水线 |
| S1.7 | 五包 static（见 §4）；全量 `run-tests.sh` 见 §5 |

## 4. 静态检查（五包）

权威命令（各包目录）：

```bash
cd vnext/<package> && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy
```

| 包 | ruff | mypy |
|----|------|------|
| backend | 见 §6 备注 | `pair_pipeline` 等新增模块 strict 通过 |
| repository_service | pass | pass |
| repository_client | pass | pass |
| shared_kernel | pass | pass |
| repository_contracts | （同脚本） | （同脚本） |

## 5. 测试

### 5.1 权威 runner

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

**未提交工作区**：repository_service compose 子集因 `ProvenanceError: worktree is dirty` 失败（8 项）；backend unit / architecture 在本轮 HEAD 改动下通过。

### 5.2 Compose 门禁（S1 要求 8 项 backend 旅程）

须在 **clean git worktree** + 重建 backend/worker 镜像后执行（与 5E S4 集合对齐）：

```bash
docker compose -f vnext/deploy/compose.yaml build backend worker
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_archive_compose_e2e.py \
  tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py \
  tests/test_backend_http_container_gate.py \
  tests/test_history_compose_e2e.py \
  tests/test_ordered_compare_compose.py \
  tests/test_ordered_submit_bisect_compose.py
```

commit 后由集成负责人复跑并回填 image digest。

## 6. 已知限制

- S1 行为约束：golden、digest、checkpoint 载荷不变；改动限于导入路径与模块边界。
- `compose` / `_catalog` / XML parser 仍在不可达基线（S3 关闭）。
- backend 全树 `ruff check .` 含 benchmarks 历史 E402；提交前门禁以五包 `src` 惯例为准（与 AGENTS 一致）。

## 7. 下一节点

S2a：规范快照与比较规则能力层（依赖 S1 kickoff 普查与 ADR 0018–0021）。

# P5-5E S1 Exit Handoff

日期：2026-09-23。

## §6.3 运行镜像证据

```
HEAD: 3117be55b1 + S1 exit 复审修复（未提交前工作区）
source_tree_sha / pyproject+uv.lock sha（五包）: 未改动 lock / Dockerfile
deploy/compose.yaml sha256: 未改动
repository-service image: sha256:b47643c2e5ddff3d50611d8b6700e25451ccc86e98fae44892fc4b90c0290a10
backend image (deploy-backend): sha256:3bd04c7e903e56b16d029ae8d97c52da4be69c53bf89d3f9224a9448108aed5a
worker image (deploy-worker): sha256:54d0f805e650ec500798ef33bc43e4f70cea411c1ee14f301e7abad596887762
compose project: deploy（容器门禁 pytest 动态 project 亦通过 compose build）
fresh_build: yes
重建理由: S1 末候选 + production wiring（History 同快照 scope + SQL 分页）需在容器路径验证
focused 测试摘要:
  - S1 focused (7 files): 118 passed
  - backend unit -m unit: 2393 passed, 163 deselected
  - unshare dolt unit (history 子集): 105 passed
  - 五包 ruff + mypy: all pass
容器门禁结果:
  - tests/test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint PASSED
  - tests/test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service PASSED
5D 对齐 gate 记录: commit_id 三方边界已回写设计 §3.2 + kickoff §3
```

## 范围声明

- 读面可用（production wiring）；**compare 尚未存在**
- **无 v6 schema 迁移**（`WORKSPACE_SCHEMA_VERSION = 5`）
- **未跑** `test_history_compose_e2e`（S3 deferred）
- **不启动 S2**

## S1 Exit 复审修复摘要

| 项 | 处理 |
| --- | --- |
| P2 scope | `get_project_history` 单 readonly UoW：`resolve_provisioned_scope` + `load_page_in_transaction` 同快照；`HistoryHttpDependencies` → `unit_of_work_factory` + `snapshot_loader` |
| P2 pagination | `sqlite_history.load_history_page_from_connection` UNION+LIMIT；生产路径 `project_history_page`；保留 `project_history_tree` 供合成测试 |
| P1 container | fresh compose build backend/worker；`test_backend_http_container_gate.py` 2/2 pass |
| 测试 | mapping 禁用 → 403（HTTP + query）；bounded page loader 不调用 `_load_submission_rows`；integrity 503 改为页内列损坏 |

## 评审修复摘要（前一轮 daed6a4d61）

| 项 | 处理 |
| --- | --- |
| F1 | `sqlite_history` 复用 `submission_from_row` / `node_from_row`；删除重复 mapper；`source_artifact_refs` 往返测试（含空列表） |
| F2 | HTTP `commit_id` → `CommitIdString`；CJK 200 字符 commit GET 200；设计 §3.2 + kickoff 三方边界 |
| F3 | `queries.py` 收敛 `ValueError` → `HistoryIntegrityFailure`；删除 projection 死分支；损坏页内列 → 503 测试 |
| F4 | 零写 / 排除 / 页内快照 / head 漂移 / limit+cursor / ref_id 边界参数表 |
| 清理 | `_decode_cursor` 签名、`HistoryHttpDependencies.now` 删除、routes 常量、架构 docstring |

## HTTP 语义记录

- `GET /v1/history` list 路由：**404 不披露 = N/A**（无 caller 提供的对象引用；S2 node 解析才成立）

## 验收命令

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  tests/test_history_projection.py tests/test_history_http.py \
  tests/test_http_openapi.py tests/test_http_auth_matrix.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py

for p in shared_kernel repository_contracts repository_client repository_service backend; do
  (cd vnext/$p && ../scripts/uv-consume.sh -C . run ruff check . \
    && ../scripts/uv-consume.sh -C . run mypy) || exit 1
done

unshare -rm --propagation private sh -c 'mount --bind /dev/null /usr/local/bin/dolt; \
  ./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q -m unit \
  tests/test_history_projection.py tests/test_history_http.py \
  tests/test_http_auth_matrix.py tests/test_production_wiring.py tests/test_architecture.py'

./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -m unit -q

cd vnext/deploy && docker compose -f compose.yaml build backend worker
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_backend_http_container_gate.py
```

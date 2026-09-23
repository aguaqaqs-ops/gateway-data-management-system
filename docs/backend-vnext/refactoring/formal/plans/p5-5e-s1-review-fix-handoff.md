# P5-5E S1 评审修复轮 Handoff

日期：2026-09-23。

## §6.3 运行镜像证据

```
HEAD: daed6a4d61（分支 phase1/gate-ownership-repair）
source_tree_sha / pyproject+uv.lock sha（五包）: 未改动 lock / Dockerfile
deploy/compose.yaml sha256: 未改动
running image: 未构建 / 未运行容器门禁
fresh_build: no
重建理由: S1 stage 内迭代；本轮仅读面评审修复（mapper/DTO/integrity/测试），未触碰 entrypoint/Compose/session
延期节点: S1 末候选 fresh 构建 + 容器回归（production wiring 已在 S1 交付）
focused 测试摘要:
  - S1 focused (7 files): 115 passed
  - backend unit -m unit: 2390 passed, 163 deselected
  - unshare dolt unit (history 子集): 102 passed
  - 五包 ruff + mypy: all pass
容器门禁结果: N/A（不得表述为当前 HEAD 已通过容器门禁）
5D 对齐 gate 记录: commit_id 三方边界已回写设计 §3.2 + kickoff §3
```

## 范围声明

- 读面可用（production wiring）；**compare 尚未存在**
- **无 schema 迁移**（`WORKSPACE_SCHEMA_VERSION = 5`）
- 本轮未跑容器门禁；旧镜像结果不得证明当前 HEAD

## 评审修复摘要

| 项 | 处理 |
| --- | --- |
| F1 | `sqlite_history` 复用 `submission_from_row` / `node_from_row`；删除重复 mapper；`source_artifact_refs` 往返测试（含空列表） |
| F2 | HTTP `commit_id` → `CommitIdString`；CJK 200 字符 commit GET 200；设计 §3.2 + kickoff 三方边界 |
| F3 | `queries.py` 收敛 `ValueError` → `HistoryIntegrityFailure`；删除 projection 死分支；损坏 JSON blob → 503 测试 |
| F4 | 零写 / 排除 / 页内快照 / head 漂移 / limit+cursor / ref_id 边界参数表 |
| 清理 | `_decode_cursor` 签名、`HistoryHttpDependencies.now` 删除、routes 常量、架构 docstring |

## G1 预算偏差（可接受）

- 预算外已存在模块：`app.py` history 参数、`application/history/{ports,errors,queries}.py`、`http/history_reader.py`
- `http/errors.py` 未登记 3 个 History 稳定码（与 E `ARTIFACT_UNAVAILABLE` 先例一致）
- 计划列「修改」但未动：`test_architecture.py`、`test_http_openapi.py`、`test_backend_readiness.py`（通用覆盖已足）

## G2 设计文字（docs-only）

- 设计 §7.1：`HistoryNode` HTTP 形状改为 `http/schemas/history.py` snake_case（非 `mappers.py` camelCase）
- 设计 §3.2 / §3.5：commit_id 三方边界、S1 integrity 空断言说明

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
```

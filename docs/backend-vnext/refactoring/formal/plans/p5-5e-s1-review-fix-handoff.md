# P5-5E S1 Exit Handoff

日期：2026-09-23。

## §6.3 运行镜像证据

```
gate_tested_head: pending-step-3-gate-run
gate_tested_source_tree_sha: pending-step-3-gate-run
built_source_tree_sha: 990989628801caee4cd36db977c59fba3176a4b1
built_source_tree_sha 说明: 生产接线改动（P2 bounded promotion fetch）所在的源码树（23285084f0^{tree}）；其 vnext/ 内容与本记录最终候选逐字节相同；容器镜像内容已用 md5sum 逐字节核对（sqlite_history.py = 6ca630ee487a3aac9c9a8d5a798d862b，worktree == deploy-backend）。09bbbe9f4145a156262f49c35aa1999770b65bfc / 5d56d205fa8ed61b854dc67f8ab2d2bd919b3542 为 pre-amend 悬空对象，不属于本记录，不得引用。
backend/uv.lock sha256: 21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea
repository_client/uv.lock sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
repository_contracts/uv.lock sha256: b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3
repository_service/uv.lock sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
shared_kernel/uv.lock sha256: 7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898
deploy/compose.yaml sha256: f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0
repository-service image: sha256:b47643c2e5ddff3d50611d8b6700e25451ccc86e98fae44892fc4b90c0290a10
backend image (deploy-backend compose build): sha256:ddd872935178a1ef8303c85cf859bf481dca3ee95d19d10843b8ebfb044757e0
worker image (deploy-worker compose build): sha256:765948a61980c009582d87443f95d3b228212af89f169627b3a17dc1f8bc8db5
compose gate provenance (authoritative): docs/backend-vnext/refactoring/formal/plans/p5-5e-s1-compose-gate-provenance.json
gate running backend container image: sha256:835cab12283e03e93f3167769d153a7d4ba7fe562f8c2f5f02cff8ddfe42a288
gate running == gate built (pytest assert): yes（gate 内 backend 镜像；≠ deploy-backend compose build ddd87293…）
sqlite_history.py md5 (worktree vs deploy-backend): 6ca630ee487a3aac9c9a8d5a798d862b == 6ca630ee487a3aac9c9a8d5a798d862b
fresh_build: yes
重建理由: S1 复审 P2 修复（页路径 bounded promotion fetch + gate provenance 挂接）；须以新 HEAD 证明 production wiring
focused 测试摘要:
  - S1 focused (7 files): 125 passed
  - backend unit -m unit: 2400 passed, 163 deselected
  - 五包 ruff + mypy: all pass
容器门禁结果:
  - tests/test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint PASSED
  - tests/test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service PASSED
5D 对齐 gate 记录: commit_id / ref_id 三方边界已回写设计 §3.2 + kickoff §3
```

## 范围声明

- 读面可用（production wiring）；**compare 尚未存在**
- **无 v6 schema 迁移**（`WORKSPACE_SCHEMA_VERSION = 5`）
- **未跑** `test_history_compose_e2e`（S3 deferred）
- **不启动 S2**

## S1 Exit 收尾摘要

| 项 | 处理 |
| --- | --- |
| D1 | `_load_promoted_by_submission` 加 `ORDER BY created_at_us ASC, node_id ASC`；与 tree 路径末位写入一致 |
| R-a | 保留 facts 测试夹具 + owner 声明；`HISTORY_TREE_PAGE_DIFF_LIMITS` 差分测试 + 重复 `source_submission_id` 确定性用例 |
| R-e | 删除恒真页内快照测试；替换为 head 前进后 cursor 页路径行为测试 |
| R-c | 删除 `project_history_page` 死参数 `limit` |
| R-b | 损坏 `source_artifact_refs` 时 GET /v1/history 仍 200（页路径不解码重列） |
| R-d | 设计 §3.2 ref_id 三方边界脚注 + kickoff 对齐行 |
| R-f | 设计 §3.3 + handoff：页内节点 O(limit)；晋升 map 仅查页内 submission（≤ 页内 submission 数 × 重复来源上界）；SQLite 单请求 O(scope history)，归 perf slice |

## D1 可达性

- v5 DB **允许**同 `source_submission_id` 多行 ARCHIVED baseline；服务写入路径（archive/start 等）**不产生**该状态
- 重复行仅测试/不变量破坏场景；DB 级 UNIQUE 约束为 S2+/v6 候选，本轮不实施

## S1 Exit 复审修复摘要（ba81a39e87）

| 项 | 处理 |
| --- | --- |
| P2 scope | 单 readonly UoW：`resolve_provisioned_scope` + `load_page_in_transaction` 同快照 |
| P2 pagination | `UNION ALL + LIMIT` 生产分页；`project_history_page` |
| P1 container | fresh compose build；gate 记录 running container image + built image 一致性；`test_backend_http_container_gate.py` 2/2 pass |
| P2 promotion | 先 `_load_history_page_rows` 分页，再 `_load_promoted_by_submission_for_submissions(IN 页内 submission_ids)`；`test_paginated_history_loader_bounds_promotion_fetch` |

## HTTP 语义记录

- `GET /v1/history` list 路由：**404 不披露 = N/A**

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

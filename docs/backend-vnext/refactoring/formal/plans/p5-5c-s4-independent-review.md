# P5-5C-S4 Independent Review — HTTP Contract and Remediation Closure

状态：**PASS — S4 closed；P2-1/P2-2 closed；未发现新增阻塞问题**

日期：2026-09-20 (UTC+8)

Owner：Independent reviewer（read-only；本文件是唯一写入）

> **Follows** [p5-5c-s4-handoff.md](p5-5c-s4-handoff.md)、
> [p5-5c-s4-remediation-handoff.md](p5-5c-s4-remediation-handoff.md)

## 1. Decision

```yaml
stage: P5-5C-S4-http-contract-production-wiring-deployed-permission
review_target: 161b805ad8
implementation_candidate_head: 83dc907cb5
remediation_implementation_head: 161b805ad8
sealed_doc_tree_head: pending_publication
parent_handoff: p5-5c-s4-handoff.md
remediation_handoff: p5-5c-s4-remediation-handoff.md
decision: pass
findings_closed: [P2-1, P2-2]
findings_open: []
p5_5c_slice_exit: not_declared
p5_5d_authorized: no
production_deployment_authorized: no
timezone: Asia/Shanghai
```

## 2. Findings closure verification

### 2.1 P2-1 — Idempotency-Key raw validation

| Item | Result |
| --- | --- |
| `parse_review_idempotency_key` no longer strips header | **confirmed** |
| Domain `validate_review_idempotency_key` on raw header | **confirmed** |
| HTTP param table: whitespace/length/control → 422 | **confirmed** |
| padded-key 422 then unpadded-key fresh 201 (not replay) | **confirmed** |

### 2.2 P2-2 — Cross-scope / permission / mapping HTTP matrix

| Barrier | Result |
| --- | --- |
| same-database cross-scope POST/GET → 404 | **confirmed** |
| replay without `review_submission` → 403 | **confirmed** |
| GET existing submission without permission → 403 | **confirmed** |
| mapping missing/disabled → 404 (POST/GET) | **confirmed** |
| mapping drift (`repo-other`) → 404 (POST/GET) | **confirmed** |
| `ScopeResolutionError` mapping missing/disabled → 404 in `http/errors.py` | **confirmed** |
| shared error mapping regression | **none observed** |

### 2.3 Changed paths audit（remediation `83dc907c..161b805a`）

| Path | Role |
| --- | --- |
| `vnext/backend/src/gateway_backend/http/orchestration/review.py` | P2-1 raw idempotency key validation |
| `vnext/backend/src/gateway_backend/http/errors.py` | P2-2 scope/mapping → 404 mapping |
| `vnext/backend/tests/test_review_http.py` | P2-1/P2-2 HTTP matrix owner extensions |

## 3. Focused gate results（@ `161b805ad8` remediation code）

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_http.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_architecture.py
# 102 passed

../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/http \
  tests/test_review_http.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_architecture.py
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: no issues found in 389 source files
```

其他 HTTP 路由回归（独立验证）：**94 passed**。

## 4. Boundary confirmations

- S4 触及 route、production wiring、`session.json`；**container rebuild 延期至 S5**（符合 execution plan §7）。
- 本 review **未**验证当前 HEAD 的容器镜像，**未**核实最近已验证镜像的 revision/source-tree。
- 未触碰 forbidden paths；未改 `uv.lock` 或依赖。
- 本 review 不声明 `p5_5c_slice_exit`；不授权 P5-5D 或 production deployment。

## 5. Next step

```yaml
next_step: P5-5C-S5
s4_countersign: pass
```

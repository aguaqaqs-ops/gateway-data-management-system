# P5-5B-S7 Independent Review 8 — S7-F2 Remediation Closure

状态：**PASS — S7-F2 closed；S8 handoff provenance 可复核**

日期：2026-09-18 (UTC+8)

Owner：Independent reviewer（read-only；本文件是唯一写入）

> **Follows** [p5-5b-s7-independent-review-7.md](p5-5b-s7-independent-review-7.md)（S7-F2 在 review-7 为 `reclassified_deferred_to_s8`，非 closed）。

## 1. Decision

```yaml
stage: P5-5B-S7-s7-f2-remediation-closure
review_target: 4d1dc010deff17249bb2aa54b7563e7a86959096
gate_candidate: 87c497634e4f6417de7fbb46b42086fd61af9031
test_hygiene_seal: 87c497634e4f6417de7fbb46b42086fd61af9031
implementation_seal: e5c43c0c9f71de3cd2e602504ec9034f16add8af
records_head: ed202d846f609fb60a047c0e01422b13d535c7d0
parent_review: p5-5b-s7-independent-review-7.md
authority:
  - p5-5b-s7-independent-review.md §S7-F2
  - p5-5b-s7-independent-review-4.md §4.3
decision: pass
findings_closed: [S7-F2]
findings_open: []
implementation_authority_unchanged: false
s8_gate_evidence: p5-5b-s8-handoff.md
p5_5b_slice_exit: not_declared
p5_5c_authorized: no
production_deployment_authorized: no
timezone: Asia/Shanghai
```

## 2. S7-F2 closure verification

### 2.1 Changed paths audit（`8f86f872..4d1dc010`）

| Path | Role |
| --- | --- |
| `vnext/backend/tests/test_submit_compose_e2e.py` | S6 owner：完整 Accept→upload→preview→submit→poll→T3→read journey |
| `vnext/deploy/compose.yaml` | S6：`worker.restart: unless-stopped` |
| `vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py` | S5 扩展：preflight 仅记录可打开的 snapshot table manifest |
| `vnext/backend/src/gateway_backend/application/submit_jobs.py` | S5 扩展：`_snapshot_bindings_from_operation` 过滤/去重 |
| `vnext/backend/src/gateway_backend/application/submission/contracts.py` | S2 扩展：`is_submit_snapshot_table_binding_candidate` |

`git diff --name-only 8f86f872..4d1dc010` 与上表完全一致，无 missing/extra。

### 2.2 Allowed paths 判定

- **原 S6 remediation paths**（review-1 §S7-F2）：`test_submit_compose_e2e.py`、`vnext/deploy/**`。
- **扩展生产 paths**（S5/S2 family）：`submit_jobs.py`、`submit_acceptance.py`、`contracts.py`。
- **触发原因**：真实 preview artifact 集合含不可被 prepare-import 打开的条目；compose journey 在 submit 前失败，需最小生产修订过滤 snapshot table binding 候选。
- **结论**：finding-scoped 最小修订；`implementation_seal: e5c43c0c` 的 Submit finalize 核心语义不变；**非** contract reopen。

### 2.3 Owner evidence

| Owner | Test | Result |
| --- | --- | --- |
| Compose Accept→T3→read | `test_compose_accept_upload_import_poll_t3_read_journey` | **pass** |
| Compose stack smoke + backend restart | `test_compose_three_process_submit_stack_smoke_and_backend_restart` | **pass** |

## 3. Focused gate results（@ `87c49763`，worktree clean）

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_compose_e2e.py
# 2 passed in 102.92s

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
# 3 passed, 1 skipped in 132.28s

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_recovery.py \
  -k 'after_terminal_commit_before_worker_ack or repository_restart'
# 2 passed, 11 deselected in 7.49s
```

S8 全量 gate（五包 static、权威 runner、三镜像 conjunction）见 [p5-5b-s8-handoff.md](p5-5b-s8-handoff.md)；本 review 不重跑，仅补 S7-F2 owner focused 证明。

## 4. Boundary confirmations

- `implementation_authority_unchanged: false`：`4d1dc010` 扩展了 S6 原 allowed paths 外的最小生产修订；其余 seal 边界不变。
- 未触碰 `operations/**`、`application/recovery.py`、Repository packages。
- 本 review 不声明 `p5_5b_slice_exit`；不授权 P5-5C 或 production deployment。
- S8 handoff `records_head` hygiene 由同期 docs publication 修正（见 [p5-5b-s8-handoff.md](p5-5b-s8-handoff.md) Hygiene）。

## 5. Next step

```yaml
next_step: P5-5B-S8-handoff-provenance-publication
s7_f2_closure: pass
```

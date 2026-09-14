# P5-5B-S1 Finding-Scoped Remediation Handoff

状态：**round-3 closure complete — independent re-review required**

日期：2026-09-14

Owner：P5-5B Delivery

## Authority gate snapshot

用户确认 gate 已通过；remediation 绑定以下 exact YAML（非叙述性授权）：

```yaml
p4_r6_exit: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
p5b_real_repository_effect_authorized: yes
unresolved_contract_drift: none
first_authorized_step: P5-5B-S1
```

## Implementation traceability

```yaml
parent_head: 6b8e7fc5468389c5f2907d8d3a9a5f52566e5ef6
candidate_head: 28b890571588045bb8a95d2b5a2f34dbd63fb16b
git_rev_parse_HEAD: 28b890571588045bb8a95d2b5a2f34dbd63fb16b
implementation_commit: 1d1d47f8593ad6a3556f341c7aed56c853647579
round3_closure_commit: 28b890571588045bb8a95d2b5a2f34dbd63fb16b
handoff_docs_commit: see git log -- docs/backend-vnext/refactoring/formal/plans/p5-5b-s1-remediation-handoff.md
uv_lock_sha256: 21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea
uv_lock_in_diff: no
verification_index_isolation: gateway_with_isolated_index / env -u UV_INDEX_URL -u UV_DEFAULT_INDEX
git_status_short: clean
```

## Finding → fix → owner → retest

### Round 1（已关闭：F1、F2、F4–F6）

| Finding | 修复摘要 | Test owner | Retest |
| --- | --- | --- | --- |
| **S1-F1** | exact gate YAML + git 审计 | docs | YAML 快照 |
| **S1-F2** | resolved / preview repository scope fail-closed | `test_submit_application.py` | `test_validate_accept_submit_rejects_mismatched_scope_repository` |
| **S1-F4** | `MatchingFinalizeFacts` / replay closure / binding | `test_submit_application.py`（**S1 smoke only**） | `FINALIZE_MATCHING_FAULTS`；authoritative owner 见 F9 |
| **S1-F5** | `MatchingAbortProof` + evidence port | `test_submit_application.py` | abort 负例 |
| **S1-F6** | occupancy XOR + row existence | `test_submit_domain.py`, `test_submit_application.py` | XOR + occupancy 负例 |

### Round 2（本轮关闭：F3、F7、F8、F9）

| Finding | 修复摘要 | Test owner | Retest |
| --- | --- | --- | --- |
| **S1-F3** | fingerprint payload 增加 `preview_ready_closure_digest`；`SubmitAttempt` 冻结该字段；`compute_new/replay` 接线 | **`test_submit_idempotency.py`（唯一语义 owner）** | closure digest 参数表；digest 非 ref-only 负例 |
| **S1-F7** | revert canonical `uv.lock`；隔离 index 下验证；lock 不得出现在 diff | docs + gate | `git diff vnext/backend/uv.lock` empty；SHA 与 parent 一致 |
| **S1-F8** | `assert_workspace_open` 仅 new-key 路径；replay 在 idempotency lookup 之后 | **`test_submit_idempotency.py`（唯一语义 owner）** | CLOSED workspace + same-key replay 成功 |
| **S1-F9** | finalize test owner 与 execution plan 对齐 | docs | 见下方 Test owner 治理 |

## Test owner 治理（S1-F9）

| 文件 | 角色 |
| --- | --- |
| [`test_submit_application.py`](vnext/backend/tests/test_submit_application.py) | **S1 contract smoke**：Accept ordering、occupancy、abort、finalize 纯函数窄负例；**非** matching/business closure 的 authoritative owner |
| [`test_submit_finalize.py`](vnext/backend/tests/test_submit_finalize.py) | **Execution plan §4 authoritative unit owner**：matching result、business closure、Finalize replay（S5 交付；S1 不宣称已覆盖） |
| [`test_submit_recovery.py`](vnext/backend/tests/test_submit_recovery.py) | **Execution plan §4 Repository/recovery integration owner**（S1 不宣称已覆盖） |
| [`test_submit_idempotency.py`](vnext/backend/tests/test_submit_idempotency.py) | **Accept fingerprint / replay 唯一 unit owner**（含 closure digest 与 CLOSED replay） |

### Round 3（本轮关闭：F3 fail-closed、F9 措辞）

| Finding | 修复摘要 | Test owner | Retest |
| --- | --- | --- | --- |
| **S1-F3** | `preview_ready_closure_digest` 必传；`assert_preview_ready_closure_digest` 在 Accept/fingerprint 边界拒绝空值 | **`test_submit_idempotency.py`** | 空 digest → `PreviewBindingConflict`；不 resolve main |
| **S1-F9** | handoff 统一为 **authoritative unit owner**（`test_submit_finalize.py`）；recovery integration 单独指 `test_submit_recovery.py` | docs | 无 integration owner 指称 finalize unit file |

## Scope paths（unchanged）

- `vnext/backend/src/gateway_backend/domain/submission/**`
- `vnext/backend/src/gateway_backend/application/submission/**`
- `vnext/backend/tests/test_submit_domain.py`
- `vnext/backend/tests/test_submit_application.py`
- `vnext/backend/tests/test_submit_idempotency.py`
- `vnext/backend/tests/test_architecture.py`
- `docs/backend-vnext/refactoring/formal/plans/p5-5b-s1-*.md`

## Invariants delivered（round-3 后）

- Repository scope fail-closed on Accept（resolved + preview vs workspace）
- Server-computed accept fingerprint with `source_digest` / `snapshot_digest` / **`preview_ready_closure_digest`**
- New Accept **fail-closed** on missing/empty closure digest before main resolve
- Same-key replay 跳过 `assert_workspace_open`；仍执行 scope re-authorization
- Workspace occupancy XOR + row existence guard
- Pure T3 matching/replay closure **smoke** in S1；**authoritative unit owner** = `test_submit_finalize.py`（S5）
- Repository/recovery **integration owner** = `test_submit_recovery.py`（execution plan；S1 不宣称）
- Abort proof shape + matching identity guard
- `uv.lock` 未纳入 delivery diff（post-fix verified）

## Focused verification

```bash
git checkout 6b8e7fc -- vnext/backend/uv.lock   # if drifted
bash vnext/scripts/prepare-dev-dependencies.sh
cd vnext/backend
env -u UV_INDEX_URL -u UV_DEFAULT_INDEX uv run pytest -q -m unit \
  tests/test_submit_domain.py \
  tests/test_submit_application.py \
  tests/test_submit_idempotency.py \
  tests/test_architecture.py
env -u UV_INDEX_URL -u UV_DEFAULT_INDEX uv run ruff check \
  src/gateway_backend/domain/submission \
  src/gateway_backend/application/submission \
  tests/test_submit_domain.py tests/test_submit_application.py \
  tests/test_submit_idempotency.py
env -u UV_INDEX_URL -u UV_DEFAULT_INDEX uv run mypy
git diff --check
git status --short
git diff vnext/backend/uv.lock
sha256sum vnext/backend/uv.lock
```

结果（2026-09-14 round-3）：

- pytest：**102 passed**
- ruff：**pass**
- mypy：**Success (324 source files)**
- `git diff --check`：**pass**
- `uv.lock` diff：**empty**
- `uv.lock` SHA-256：**21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea**
- container_rebuild_required：**no**（纯 Python/domain/docs 变更）

历史（round-2）：99 passed

## Next step

Independent reviewer 复跑 focused gate + round-3 probes（空 closure digest 负例、finalize **unit** owner 措辞）。`pass` 后可签署 S1 closure，再开 S2。

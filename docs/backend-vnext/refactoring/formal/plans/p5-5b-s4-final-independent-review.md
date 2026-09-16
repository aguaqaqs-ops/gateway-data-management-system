# P5-5B-S4 Final Independent Review and S5 Entry Authorization

状态：**PASS — S4 closed; S5 entry authorized**

日期：2026-09-16

Owner：Independent reviewer + explicit user authority

## 1. Review target and decision

```yaml
stage: P5-5B-S4-backend-http-v1-re-authorization
implementation_candidate: 0fdc0cb6cf4f6549331e989b7eb8994ebef46c9a
candidate_binding_commit: 765a2a3810c6cdb311363e4f0313c12565e78d89
decision: pass
findings_open: []
R3_RR_F1: closed
worktree_at_review: clean
uv_lock_identity: canonical_pypi
docker_rebuild_required: no
```

R3-RR-F1 已按 accepted design §6.1/§6.3 关闭。新 key 的 HTTP preflight 顺序为：

```text
local guards
→ baseline I/O（read-only UoW 外）
→ NO_CANONICAL_CHANGE
→ post-noop occupancy/closure guards
→ artifact verification
→ T1 transaction
```

唯一 HTTP owner `tests/test_submit_http.py` 覆盖已有 occupancy 且 canonical no-op 时返回
`409 NO_CANONICAL_CHANGE`，不被 `SUBMIT_OCCUPANCY_CONFLICT` 遮蔽。

## 2. Independent verification

全部命令通过受控 dependency consumer 执行，执行前后五锁无漂移：

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q -m unit \
  tests/test_submit_http.py \
  tests/test_submit_read_http.py \
  tests/test_operator_recovery_http.py \
  tests/test_operation_http.py \
  tests/test_http_auth_matrix.py \
  tests/test_http_openapi.py
# 62 passed

./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q -m unit \
  tests/test_submit_transactions.py -k "baseline or canonical"
# 3 passed, 32 deselected

./vnext/scripts/uv-consume.sh -C vnext/backend run ruff check .
# pass

./vnext/scripts/uv-consume.sh -C vnext/backend run mypy
# pass; 352 source files
```

仅观察到既存 Starlette/httpx deprecation warning，不影响 S4 判定。候选只修改 Python、测试和
文档，不触及 image/deployment/container boundary，因此当前阶段不要求 Docker 重建。

## 3. S5 authority audit

```yaml
p4_r6_exit: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
p5b_real_repository_effect_authorized: yes
unresolved_contract_drift: none
s4_independent_review: pass
explicit_s5_authorization: yes
authorization_source: user_instruction_in_current_conversation_2026-09-16
s5_entry: authorized
```

P4-R6 lineage 由 `p4-r6-s7-final-handoff.md` 的 sealed candidate exit=pass 提供；P5-5B 的
implementation 与真实 Repository effect 授权已在 S1–S3 authority handoff 明确记录。本次用户指令
明确允许修改、提交并直接授权 S5，满足执行计划 §S5 的最后一个显式入口条件。

## 4. F6 entry disposition

S4 handoff 登记的 F6（message sniffing / P4 文案耦合）在 S5 entry audit 中确认：现有 public
types、operation/step status 与 recovery capability 已足够完成 typed/stable classification，不需要
修改 owning contract、P4 core 或 Repository public wire，因此不触发 reopen。

F6 是 S5 的首个强制工作项。在其关闭前不得开始真实 Repository effect。除执行计划 §S5 原 allowed
paths 外，仅授权以下 finding-scoped 路径：

```text
vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py
vnext/backend/src/gateway_backend/http/orchestration/operator_recovery.py
vnext/backend/tests/test_submit_http.py
vnext/backend/tests/test_operator_recovery_http.py
docs/backend-vnext/refactoring/formal/plans/p5-5b-s5-*.md
```

修复必须使用 typed exception 或基于 typed state/capability 的稳定分类，不得把新的异常文案匹配
作为替代。关闭 F6 后，S5 可继续执行既定 JobDefinition、Repository effect、recovery 与 T3 工作。

## 5. Authorization boundary

```yaml
next_step: P5-5B-S5 F6 typed-error closure
s5_authorized: yes
real_repository_effect_after_F6_closure: authorized
s6_authorized: no
contract_or_wire_change_authorized: no
dependency_or_lockfile_change_authorized: no
```

本记录不授权 S6、owning contract/P4 core/Repository wire 变更、依赖或 lockfile 变更；出现这些需求时
必须停止并按 execution plan reopen。

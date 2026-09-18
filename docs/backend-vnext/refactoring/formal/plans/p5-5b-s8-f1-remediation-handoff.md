# P5-5B-S8-F1 Remediation Handoff

状态：**pending_closure — S8-F1 finding-scoped remediation**

日期：2026-09-18 (UTC+8)

Owner：P5-5B Delivery

上游：[P5-5B Submit Finalize Execution Plan §6.2 / §7 / §8](p5-5b-submit-finalize-execution-plan.md)、
[P5-5B-S8 Handoff](p5-5b-s8-handoff.md)

```yaml
handoff_kind: p5_5b_s8_f1_remediation
finding: S8-F1
gate_candidate_before_fix: 87c497634e4f6417de7fbb46b42086fd61af9031
test_hygiene_seal: 87c497634e4f6417de7fbb46b42086fd61af9031
authority:
  - p5-5b-submit-finalize-execution-plan.md §6.2
  - p5-5b-submit-finalize-execution-plan.md §7
  - p5-5b-submit-finalize-execution-plan.md §8
  - retroactive: test_hygiene_seal @ 87c49763 (test_live_session.py autouse fixture)
allowed_paths:
  - vnext/backend/tests/test_live_session.py
risk_class: static_gate_blocker
implementation_authority_unchanged: true
container_rebuild_required: no
container_reason: S8-F1 test-only; backend Dockerfile copies backend/src only
findings_open: [S8-F1]
findings_closed: []
next_step: test_hygiene_fix_seal_then_rerun_gates
timezone: Asia/Shanghai
```

## 1. Finding

**S8-F1** — backend `strict = true` mypy 在 `tests/test_live_session.py:28` 失败：

```text
The return type of a generator function should be "Generator" or one of its supertypes  [misc]
```

根因：`test_hygiene_seal` @ `87c49763` 新增 autouse fixture `_skip_repository_ready_probe() -> None` 内含 `yield`。

**授权缺口**：`test_live_session.py` @ `87c49763` 在 S6/S7 allowed paths 与 review-8 changed-path 审计（`8f86f872..4d1dc010`）外引入；本 finding 以 retroactive authority 闭合。

## 2. Remediation

| Path | Change |
| --- | --- |
| `vnext/backend/tests/test_live_session.py` | `from collections.abc import Iterator`；`_skip_repository_ready_probe() -> Iterator[None]` |

不触碰 production、`uv.lock`、Dockerfile、Compose。

## 3. Verification plan

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run ruff check .
../scripts/uv-consume.sh -C . run mypy

for pkg in shared_kernel repository_contracts repository_client backend repository_service; do
  (cd vnext/$pkg && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done

./vnext/scripts/run-tests.sh
```

Closure 由 [p5-5b-s8-independent-review-1.md](p5-5b-s8-independent-review-1.md) 独立复核。

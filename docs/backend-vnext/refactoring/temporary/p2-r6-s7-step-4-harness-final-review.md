# P2-R6-S7 — Harness Implementation Final Re-review

状态：`pass`

日期：2026-08-16

本记录是对 S7-4 修复提交 `eeadbdd` 的独立只读复审。复审对照此前的 fail records，检查
cleanup ordering、typed 401 failure boundary、thread residual ownership、四个 exact gate
nodeid 和四个 expected-failure probe；未修改 production/test/Compose 输入，未运行 Docker
或 Compose lifecycle gate。

## Identity and verification

```yaml
branch: phase1/gate-ownership-repair
reviewed_head: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
reviewed_parent: 2264ecc787704373e95b6c5daf5eff448793f8ec
review_worktree_clean_at_start: no
preexisting_untracked_review_records:
  - docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-4-harness-review.md
  - docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-4-harness-rereview.md
production_code_changed_by_review: no
compose_or_docker_input_changed_by_review: no
container_rebuild_required: yes
container_rebuild_reason: S7 Compose/client lifecycle harness and test-only consumer boundary changed
last_verified_image_revision: none
last_verified_source_tree_image_id: none
container_gate_for_current_head: deferred
phase_2_complete: no
```

## Verification performed

- `repository_service` focused unit: `76 passed`;
- `repository_client` `tests/test_versioned_fixture_consumer.py`: `42 passed`;
- serial focused collect includes the timeout unit and all four negative probes (`5/80` selected);
- touched-package `ruff`, `mypy` and `git diff --check`: passed;
- README/testing-conventions keep exactly four S7 PASS nodeids; the negative probe file is an
  explicitly ignored expected-failure probe, not a fifth PASS nodeid.

No Docker e2e, image build, bridge preflight, or public-fact evidence was run in this review.

## Previous blocker disposition

- **Cleanup ordering — closed.** `cleanup_compose_project` snapshots query-temp/Dolt state,
  attempts hold removal and `compose down` regardless of snapshot/removal errors, then performs
  project/volume/residual assertions and raises an aggregated error. The focused regression test
  proves teardown occurs before query-temp assertion.
- **401 classification — closed.** The test-only consumer emits only a typed one-line failure JSON
  on stdout and keeps the redacted human message on stderr. The harness accepts this JSON for
  non-zero clients and rejects stderr-only synthetic status text; repository-client tests verify
  the real `RepositoryClientError(status_code=401)` shape.
- **Thread residual — closed.** All four gates and all four negative probes capture
  `list_host_thread_idents()` before execution and pass `thread_baseline` through the session
  teardown. The harness owns no host thread prefixes (`S7_OWNED_HOST_THREAD_PREFIXES=()`), and a
  focused test rejects any new host thread ident.
- Earlier startup cleanup, hold inventory/removal, Docker environment allowlist, and serial marker
  findings remain covered by the prior repair and focused tests.

## Review questions

| invariant | result |
| --- | --- |
| no Service host port, Docker socket, host-root mount or resident client | pass; rendered boundary tests remain green |
| ephemeral client image/source lock identity and read-only fixture boundary | pass; labels and Dockerfile checks remain green |
| exact four nodeids and unique restore owner | pass; collection and README inventory agree |
| expected-failure cleanup | pass; four probes are integration+serial and scoped through project session |
| typed client summary and secret/path redaction | pass; success and failure shapes are distinct and bounded |
| cleanup on snapshot/diagnostic failure | pass; teardown is attempted before aggregated residual assertions |
| thread/process/Dolt/query-temp/work-root residual checks | pass within declared S7 ownership boundaries |

## Verdict

```yaml
review_status: pass
reviewed_head: eeadbdd38ab468667b2b9ebbdfffae39ddc62771
finding_count: 0
blocker_count: 0
allow_provisional_image: yes
production_code_changed_by_review: no
container_rebuild_required: yes
container_gate_for_current_head: deferred
next: S7-5 provisional image and preflight
phase_2_complete: no
```

该复审只允许进入 S7-5；它不授予当前 HEAD 的 Compose PASS、S7 exit 或 Phase 2 completion。
S7-5 必须从 `eeadbdd` 之后的精确 candidate 重新构建并记录 service/client provenance，之后
再运行 directed Docker gates。

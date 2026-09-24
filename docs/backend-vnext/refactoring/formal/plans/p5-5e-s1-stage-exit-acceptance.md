# P5-5E-S1 Stage Exit Acceptance

状态：**PASS — `p5_5e_s1_stage_exit: pass`**

日期：2026-09-24

Owner：Backend vNext Architecture Acceptance（independent acceptance context）

上游：[Execution Plan §S1](p5-5e-history-compare-execution-plan.md)、
[S1 Kickoff](p5-5e-s1-kickoff.md)、
[S1 Review Fix Handoff](p5-5e-s1-review-fix-handoff.md)。

```yaml
acceptance_kind: p5_5e_s1_stage_exit
acceptance_authority: explicit_user_authorization_after_independent_review
p5_5e_s1_stage_exit: pass
p5_5e_s1_gate_tested_head: fdf430e76811085a29c268c1f09c1239499fbd84
p5_5e_s1_exit_candidate_head: 930d241dfdf29f15f23e77135ca434fa605e6921
exit_candidate_source_tree_sha: 515a486a1effa1e41b27a18f5b7aca7d3e6767ca
built_source_tree_sha: 990989628801caee4cd36db977c59fba3176a4b1
implementation_binding: 23285084f00e618e6ea9fadf31d1768c9e2d610d
compose_gate_provenance: docs/backend-vnext/refactoring/formal/plans/p5-5e-s1-compose-gate-provenance.json
handoff: docs/backend-vnext/refactoring/formal/plans/p5-5e-s1-review-fix-handoff.md
compare_implemented: no
workspace_schema_version: 5
production_deployment_authorized: no
new_repository_effect_authorized: no
p5_5e_s2_implementation_authorized: no
p5_5e_slice_exit: not_evaluated
next_step: P5-5E-S2
```

`p5_5e_s2_implementation_authorized: no` — 执行计划 `implementation_authorized` 仍为 `S1 only`；
S2 代码须在 owner 将 [Execution Plan](p5-5e-history-compare-execution-plan.md) 的
`implementation_authorized` 字段推进至 S2 后方可启动。

## Acceptance and evidence

独立签署复核（2026-09-24）确认 handoff §6.3 与落盘 provenance JSON 中全部 hash 均可由
`git rev-parse` / `sha256sum` / `md5sum` 复现；`vnext/**` 自 provenance 修复基线
`3976f62f01` 起无改动；悬空 pre-amend 对象（`09bbbe9f…` / `5d56d205…` / 填充式 hash）
已自权威字段移除。

- **E1** S1 focused gate（七文件）：**125 passed**（handoff §6.3）
- **E2** backend unit `-m unit`：**2400 passed, 163 deselected**
- **E3** 五包 ruff + mypy：**全部通过**
- **E4** 容器门禁（`gate_tested_head` `fdf430e768`）：**2 passed**
- **E5** `vnext/` 字节一致性：`git diff 23285084f0 930d241dfd -- vnext/` → **0 bytes**
- **E6** `sqlite_history.py` md5（worktree == `deploy-backend`）：`6ca630ee487a3aac9c9a8d5a798d862b`

### Provenance verification（签署时复跑）

| 检查项 | handoff / JSON 值 | `git rev-parse` / 工具输出 | 结果 |
| --- | --- | --- | --- |
| `gate_tested_source_tree_sha` | `095fcf2d7b30a4f515e0168968c21593725c21ac` | `git rev-parse fdf430e768^{tree}` | match |
| `exit_candidate_source_tree_sha` | `515a486a1effa1e41b27a18f5b7aca7d3e6767ca` | `git rev-parse 930d241dfd^{tree}` | match |
| `built_source_tree_sha` | `990989628801caee4cd36db977c59fba3176a4b1` | `git rev-parse 23285084f0^{tree}` | match |
| 五锁 + compose.yaml | 见 handoff §6.3 | `sha256sum` 六项 | match |
| gate running backend image | `sha256:835cab12283e…` | provenance JSON + handoff | match |

## Build / running provenance（S1 exit 绑定）

权威来源：[p5-5e-s1-compose-gate-provenance.json](p5-5e-s1-compose-gate-provenance.json)
（**不得**使用 gitignored `vnext/backend/tests/support/.last_compose_gate_provenance.json`）。

Project `gateway-backend-gate-test_backend_container_ready_a0`；`gate_tested_head`
`fdf430e76811085a29c268c1f09c1239499fbd84`。

| Service | Container ID | Immutable image ID |
| --- | --- | --- |
| repository-service | `3411a3680d35` | `sha256:b47643c2e5ddff3d50611d8b6700e25451ccc86e98fae44892fc4b90c0290a10` |
| backend | `95a5361decde` | `sha256:835cab12283e03e93f3167769d153a7d4ba7fe562f8c2f5f02cff8ddfe42a288` |

gate running backend image == gate build（pytest 断言）；≠ `deploy-backend` compose build
`sha256:ddd872935178a1ef8303c85cf859bf481dca3ee95d19d10843b8ebfb044757e0`（handoff §6.3 已区分）。

## Evidence chain

| Stage | Authority |
| --- | --- |
| S0 docs | [p5-5e-s0-independent-docs-acceptance.md](p5-5e-s0-independent-docs-acceptance.md) |
| S1 kickoff | [p5-5e-s1-kickoff.md](p5-5e-s1-kickoff.md) |
| S1 实现（P2 bounded promotion） | `23285084f0`（`built_source_tree_sha` `9909896288…`） |
| S1 复审修复（D1/R-a…R-f + P2 scope/pagination/promotion） | [p5-5e-s1-review-fix-handoff.md](p5-5e-s1-review-fix-handoff.md) §S1 Exit 收尾 / 复审修复摘要 |
| S1 provenance 修复 | `gate_tested_head` `fdf430e768` + 落盘 JSON；`exit_candidate_head` `930d241dfd` |

## Scope declarations

- **读面可用**（production wiring）；**compare 尚未存在**（`compare_implemented: no`）。
- **无 v6 schema 迁移**（`workspace_schema_version: 5`）。
- 本记录 **不** 声明 `p5_5e_slice_exit: pass`（整个 5E slice 的 exit 归 S4）。
- 本记录 **不** 授权 S2 代码实现（须 execution plan `implementation_authorized` 推进）。
- 本记录 **不** 授权 production deployment 或新的 Repository effect。
- S3 deferred：`test_history_compose_e2e` 未跑；S2 仍须按执行计划 fresh-build 与 focused gate。

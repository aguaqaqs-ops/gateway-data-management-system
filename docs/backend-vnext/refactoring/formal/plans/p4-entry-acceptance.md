# P4 Entry Acceptance Candidate

状态：**READY FOR INDEPENDENT ACCEPTANCE**

日期：2026-08-23

Owner：Backend vNext Architecture Acceptance

范围：Phase 4 Durable Operation Runtime entry；不包含 P4 implementation authorization。

上游：[P4 Active Context Index](p4-active-context-index.md)、[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)、[P4 Durable Operation Runtime Execution Plan](p4-durable-operation-runtime-execution-plan.md)

## 1. Candidate identity

```yaml
acceptance_kind: p4_entry
candidate_base_sha: 51ee61647451be63665e8d2754270ca996771ba9
candidate_worktree_state: clean_after_document_seal
candidate_document_set_sha256: 7362546aed23e0427cf6cd44749ea7dd45b31985df7efad0aabfe26f607c9c30
candidate_document_set: backend-vnext README + formal README + formal architecture + P4 index/design/plan + R1-S0 brief
candidate_acceptance_record_excluded_from_hash: true
source_code_changed: false
runtime_implementation_authorized: no
independent_acceptance: pending
```

`candidate_base_sha` 是本轮文档变更前的 source baseline；`candidate_document_set_sha256` 是
已封存候选文档路径集合的内容摘要，明确排除本 acceptance record 本身以避免自引用。最终
提交 SHA 由 Git history 记录，不在自身文件中重复嵌入。提交或重新生成候选后必须更新本节，
不能继续沿用旧 provenance。

## 2. Acceptance checklist

| Gate | Result | Evidence / condition |
|---|---|---|
| P3 final closure | PASS | F0–F5、`p3_exit: pass`、`p4_ready: yes` |
| P3→P4 cleanup | PASS | C7 independent acceptance、`p4_entry_context_ready: yes` |
| Scope and non-goals | PASS | P4 design §1；P5 business flow excluded |
| Physical package placement | PASS | `gateway_backend/operations/`；`backend_vnext` 仅为逻辑架构名称 |
| Owner and dependency direction | PASS | design §3；Operations 不拥有业务 payload 或 Repository authority |
| Durable Store topology | PASS | same modular monolith, SQLite/WAL, shared control DB transaction boundary |
| State and recovery semantics | PASS | design §4–6；CAS/lease/checkpoint/evidence-first recovery |
| Worker and lifecycle boundary | PASS | design §3/§5；独立 entrypoint、顺序 step、有界并发、drain/restart |
| JobDefinition/checkpoint boundary | PASS | design §4；versioned envelope、artifact refs、READY closure |
| Registry key/version naming | PASS | `(job_kind, step_name)`；`backend-vnext/operation-runtime/v1` |
| Retry/cancel/takeover boundary | PASS | design §4–6；unknown 不盲重放，协作取消 |
| Initial module plan | PASS | execution plan R1–R6；S-step 可裁剪而非机械固定 |
| Test and gate strategy | PASS | execution plan §9–10；serial/integration/container applicability |
| Deferred/reopen register | PASS | design §7、execution plan §11 |
| Current HEAD provenance | READY | 文档候选尚未提交；独立 acceptance 前必须重新核对 |
| Independent acceptance | PENDING | 需独立审查本清单及关联文档 |
| Implementation authorization | NO | 保持 `p4_implementation_authorized: no`，直到独立 acceptance 和明确授权 |

## 3. Acceptance decision rule

独立 acceptance 只有在以下条件全部成立时才能标记 `PASS`：

1. candidate identity 与工作区文档内容一致；
2. P3 handoff、P4 design、execution plan 和本清单的 owner/边界无冲突；
3. 没有未处理的 P1/P2 finding、架构级 contract ambiguity 或隐式部署边界；
4. R1-S0 brief 已被接受，且没有把 R1-S1 实现误写为 entry deliverable；
5. deferred/reopen 条目有 owner、触发条件和后续阶段。

Acceptance PASS 只表示允许进入 R1-S0；是否开始 R1-S1 实现必须由独立 acceptance 记录或
明确的 implementation authorization 更新另行确认。

## 4. Reopen conditions

- P4 引入 broker、sidecar、独立 UID/helper、外部 durable DB 或多实例 HA；
- Runtime 解释业务 payload、拥有 T3 finalize 或改变 Repository marker/ref/CAS authority；
- lease/CAS 无法阻止 stale worker 写入；
- unknown outcome 存在 blind replay 或新 idempotency key 路径；
- P4 状态空间扩展为 generic evidence/closure 状态机；
- 当前真实 consumer、部署形态或容量目标与本候选假设冲突。

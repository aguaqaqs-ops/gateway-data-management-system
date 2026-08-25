# P4-R4 JobDefinition and Checkpoint Detailed Execution Plan

状态：**R4-S0 DESIGN/PLAN ACCEPTED — S1a IMPLEMENTATION NOT AUTHORIZED**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

默认入口：[P4 Active Context Index](p4-active-context-index.md)

Entry brief：[P4-R4-S0 Entry Brief](p4-r4-s0-entry-brief.md)

设计基线：[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)

上游：[P4/R3 Worker Lifecycle Handoff](p4-r3-worker-lifecycle-handoff.md)

## 1. Purpose and execution protocol

本文把 R4 拆成可以由简短提示词逐个推进的 named steps。每次执行只做一个 step，执行者
必须从磁盘重新读取 context，不从聊天记忆推断授权或下一步：

1. 读取 Active Context、R3 handoff、R4 entry brief、本 plan、上一 handoff 和 Git 状态；
2. 核对 input SHA ancestry、允许路径、当前 source/test tree 和 stop/reopen 条件；
3. 只修改本 step 的 allowed paths，运行 focused 及适用 unit/integration/serial/static gate；
4. 审查 diff、marker 分类、container/benchmark applicability 和日志脱敏；
5. code step 先形成 candidate code commit，再形成 docs-only handoff commit；
6. handoff 只指向下一 step，不自动开始、隐式授权或跨越 review round。

任何 source/test/build-input drift、validated SHA 非 ancestor、未记录 worktree change 或
跨 owner finding 都必须停止，不得在当前 step 顺手修复。

## 2. Shared handoff schema

每个 implementation/review/handoff 至少记录：

```yaml
step_id:
context: same_conversation | new_conversation | mandatory_new_conversation
input_handoff_sha:
input_validated_code_sha:
validated_code_sha:
validated_source_tree:
candidate_worktree:
result: pass | rework_required | not_applicable
changed_paths: []
commands_and_results: []
focused_tests:
backend_unit:
integration:
serial:
five_package_static:
container_rebuild_required: yes | no
container_reason:
last_verified_image_revision:
container_gate: passed | deferred | stale | not_applicable
benchmark:
findings: []
deferred_items: []
reopen_conditions: []
next_step:
next_step_authorized: yes | no
```

Review handoff 还必须记录 reviewer 是否读取完整 source/test/diff、finding severity、owner、
regression、closure 和 reopen disposition。S5 没有 finding 时必须写明
`not_applicable_no_findings`，不能创建空 production step。

## 3. Conversation strategy

R4 保留 review 隔离，并将每个会改变 public/persisted/test contract 的 step 放入新对话：

| Step | Context | Reason |
|---|---|---|
| S0 | **mandatory_new_conversation** | 独立接受 R3 handoff、R4 design 和本 plan，不继承设计讨论偏置 |
| S1a | **new_conversation** | JobDefinition/registry public boundary；需单独审查 owner/import |
| S1b | **new_conversation** | payload/checkpoint version decoder 是独立 compatibility seam |
| S2a | **new_conversation** | artifact/checkpoint/READY closure 和 CAS publication 是一致性 seam |
| S2b | **new_conversation** | composition root/worker adapter 会跨 application、bootstrap、Operations port |
| S3a | **new_conversation** | pure-compute synthetic job 建立第一个可恢复 consumer |
| S3b | **new_conversation** | external-effect stub 建立 identity/unknown boundary，不混入 S3a 假设 |
| S3c | **new_conversation** | duplicate/crash/cancel/READY fault matrix 跨越多个 consumer |
| S4 | **mandatory_new_conversation** | focused reviewer 与实现对话隔离 |
| S5 | **new_conversation**（有 finding 时） | 只按 finding appendix 修复；docs-only disposition 可留在 S4 |
| S6 | **mandatory_new_conversation** | independent reviewer 只依 sealed evidence，不继承实现假设 |
| S7 | **new_conversation** | final current-HEAD gate、image provenance 和 handoff seal |

同一对话只允许完成一个 named step 的 implementation、validation、diff review 和 handoff。
禁止在一个长对话中连续执行 S1a-S3c。

## 4. Frozen boundary and allowed surfaces

R4 application owner 定义 JobDefinition、payload/checkpoint/closure decoder、normal successor/
final candidate 和两个 synthetic jobs；R3 继续拥有 claim/lease/heartbeat/publication serialization/
drain；R5 继续拥有 retry/takeover/unknown outcome/manual recovery；P5 拥有 T1/T3、HTTP/global
readiness 和真实 Repository journey。

R4 复用现有 `ArtifactStorePort`/`ArtifactRef`，不创建 generic manifest、delete/quarantine、
cleanup broker 或第二套 registry。active Step 的 `checkpoint_ref` 是恢复权威；Operation-level
checkpoint 不作为普通 checkpoint 的第二写入目标。

候选代码面：

```text
vnext/backend/src/gateway_backend/application/__init__.py
vnext/backend/src/gateway_backend/application/job_definitions.py
vnext/backend/src/gateway_backend/application/synthetic_jobs.py
vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
vnext/backend/src/gateway_backend/operations/worker.py       # adapter only if required

vnext/backend/tests/test_job_definition_contracts.py
vnext/backend/tests/test_job_definition_registry.py
vnext/backend/tests/test_job_payload_decoding.py
vnext/backend/tests/test_operation_checkpoint_contracts.py
vnext/backend/tests/test_operation_job_synthetic.py
vnext/backend/tests/test_operation_job_recovery.py
vnext/backend/tests/test_operation_worker_process.py
vnext/backend/tests/test_architecture.py
```

文档面可修改本 plan、entry brief、step handoffs/reviews、Active Context、formal README 和
owner-reference clarification。禁止改 R1/R2 persisted contract/schema/CAS/error taxonomy、
Repository Service、P5 business route、Compose、dependency lock，除非先 reopen owner。

## 5. Shared verification commands

步骤按实际文件收窄，但遵守以下 marker 和包级门禁：

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_job_definition_contracts.py \
  tests/test_job_definition_registry.py \
  tests/test_job_payload_decoding.py \
  tests/test_operation_checkpoint_contracts.py \
  tests/test_architecture.py
uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_job_synthetic.py \
  tests/test_operation_job_recovery.py \
  tests/test_operation_worker_process.py
uv run pytest -q -m serial \
  tests/test_operation_job_recovery.py \
  tests/test_operation_worker_process.py
uv run pytest -q -m unit
uv run ruff check .
uv run mypy
```

其余四个 Python 包分别执行 `uv run ruff check . && uv run mypy`。纯解析/校验/fake clock 标
`unit`；真实 artifact files/WAL/reopen 标 `integration`；固定 timeout、thread/process crash、
signal 或 drain/restart 标 `serial`。R4 不运行 Dolt/Repository integration；stub 不能被表述
为 production effect validation。

## 6. P4-R4-S0 — Independent entry acceptance

```yaml
step_id: P4-R4-S0
context: mandatory_new_conversation
change_kind: docs_only
objective: accept R4 design/plan and preserve implementation authorization boundary
```

Entry：R3 S7 handoff pass；R3 source/test tree无 drift；R4 design §2.1 closure已写入；本 plan
和 entry brief 可审查。

Required checks：

1. R3 handoff SHA、validated code ancestry、image/source tree identity 和当前 worktree；
2. registry/payload/checkpoint/closure/successor/stub/cancel owner 均唯一；
3. R4 不需要 R1/R2 schema/status/CAS/error taxonomy 扩展；
4. ArtifactStorePort、path-neutral ArtifactRef、bounded temporary orphan policy 明确；
5. S1a-S3c 的拆分理由、review rounds、marker 和 container applicability 明确；
6. acceptance record 记录 design accepted、implementation not authorized、deferred/reopen；
7. semantic candidate hash 排除 acceptance record 自引用；
8. Active Context/formal README 的检索入口与状态接线一致。

Allowed changes：R4 entry brief、R4 plan、R4 S0 acceptance、P4 design/index/README 的状态和
owner references。不得改 Python/tests/dependencies/deployment。

Exit：`p4_r4_s0: accepted`、`p4_r4_s1a_authorized: no`；下一步只能进入 S1a authorization
discussion。

Short prompt：

```text
在新对话执行 P4-R4-S0 independent entry acceptance。按 R4 entry brief 和 detailed plan
核对 R3 handoff、设计边界、step/review/test/provenance；只修 docs acceptance，不改 source/tests，
不授权 S1a。
```

## 7. P4-R4-S1a — JobDefinition contract and immutable registry

```yaml
step_id: P4-R4-S1a
context: new_conversation
objective: freeze application-owned JobDefinition and registry adapter without executing jobs
```

Entry：S0 accepted；获得明确的 S1a implementation authorization。

Allowed paths：

```text
vnext/backend/src/gateway_backend/application/__init__.py
vnext/backend/src/gateway_backend/application/job_definitions.py
vnext/backend/src/gateway_backend/operations/worker.py       # only adapter-compatible type additions
vnext/backend/tests/test_job_definition_contracts.py
vnext/backend/tests/test_job_definition_registry.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r4-s1a-handoff.md
```

Implementation requirements：

1. 定义 immutable `JobDefinition` descriptor，至少绑定 `JobStepKey`、supported payload versions、
   decoder/handler identity 和 normal successor/final capability；不把业务 entity 放入 generic record；
2. 定义 application-owned immutable registry；lookup 纯内存、有界、无 I/O、无 hot reload；
3. 将 registry definition 映射到既有 R3 `WorkerRegistry`/`ClaimedExecutor`，不让 Operations import
   application implementation；
4. unknown key 在 claim 前返回 bounded failure，不生成 lease/token、不写 RUNNING；
5. 不创建 production fake、dynamic script runner、generic `WorkerError` 或第二套 `operation_kind`；
6. public exports 只暴露 R4 最小 contract，不导出 handler closure、mutable map 或 private adapter。

Tests：exact export/import boundary、registry immutability、duplicate key/version、unknown lookup、
bounded key validation、no filesystem/network/SQLite in resolver。相同 fault shape 使用参数表。

Review focus：application/Operations dependency direction、registry mutability、payload policy leakage、
R3 protocol widening、dynamic registration 和 new error taxonomy。

Container：`no`，本步不组合 concrete bootstrap；benchmark N/A。

Short prompt：

```text
执行 P4-R4-S1a，按 detailed execution plan 冻结 JobDefinition/immutable registry contract，完成
focused unit/static gates、diff review 和 handoff；不开始 S1b。
```

## 8. P4-R4-S1b — Payload and versioned decoder boundary

```yaml
step_id: P4-R4-S1b
context: new_conversation
objective: implement strict payload/checkpoint decoder seams without business interpretation in Operations
```

Allowed paths：

```text
vnext/backend/src/gateway_backend/application/job_definitions.py
vnext/backend/src/gateway_backend/application/payloads.py
vnext/backend/tests/test_job_payload_decoding.py
vnext/backend/tests/test_job_definition_contracts.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r4-s1b-handoff.md
```

Implementation requirements：

1. inline payload 使用既有 R1 bounded canonical JSON shape；payload ref 通过 injected ArtifactStorePort
   exact locate 并验证 size/raw digest；
2. decoder 先检查 `job_kind`/`job_contract_version`/document type，再调用 registered typed decoder；
3. unknown version、malformed shape、missing/corrupt ref、oversize/depth/aggregate violation fail closed；
4. decoder 不在 R2 transaction 内运行，不自动迁移、不回写 payload、不从宽读取旧字段；
5. checkpoint decoder 和 payload decoder 使用独立 version axis；错误只返回 owner-bounded diagnostic，
   不创建 generic recovery taxonomy；
6. 所有 output 必须可重新编码为 closed bounded document 或 immutable ArtifactRef，不返回 closure graph。

Tests：module-level parameter tables 覆盖 malformed JSON/version/ref/size/depth/duplicate refs；unit
覆盖 fake store，integration 覆盖 LocalArtifactStore missing/corrupt/reopen。不得为纯 parser 创建
真实 SQLite/Dolt fixture。

Review focus：implicit migration、payload business leakage、unbounded artifact reads、path/token leakage、
decoder I/O under transaction。

Container：`no`，benchmark N/A。

Short prompt：

```text
执行 P4-R4-S1b，按 plan 完成 strict payload/checkpoint decoder、参数化 fault tests、static gate 和
handoff；不开始 S2a。
```

## 9. P4-R4-S2a — Artifact, checkpoint and READY closure contract

```yaml
step_id: P4-R4-S2a
context: new_conversation
objective: define immutable checkpoint/closure documents and publication-ready reference validation
```

Allowed paths：

```text
vnext/backend/src/gateway_backend/application/checkpoints.py
vnext/backend/src/gateway_backend/application/job_definitions.py
vnext/backend/src/gateway_backend/artifacts/serialize.py       # only owner-compatible helper if required
vnext/backend/tests/test_operation_checkpoint_contracts.py
vnext/backend/tests/test_job_payload_decoding.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r4-s2a-handoff.md
```

Implementation requirements：

1. 定义 versioned JCS checkpoint envelope，绑定 job/step identity、checkpoint generation、prior output
   refs 和 job-owned payload state；不保存 Python object graph；
2. 定义最小 READY closure document，按稳定顺序列出 exact ArtifactRefs、size/raw digest、closure
   version 和 job contract version；不建立 generic cross-capability manifest；
3. 使用既有 `ArtifactStorePort.put/locate`，同一 exact ref 的 `put` 幂等，identity mismatch 失败；
4. `StepRecord.checkpoint_ref` 是 active recovery cursor；`ready_closure_ref` 只能一次性设置；
5. artifact 先写、durable CAS 后提交；CAS 失败的未引用 artifact 不触发 R4 cleanup；
6. publication builder 只消费 transaction-fresh record，I/O 完成后才进入 R3 session publication；
7. 需要 R1/R2 mutation/schema 变更时停止并记录 reopen finding。

Tests：canonical round-trip、ordering/digest/duplicate ref、missing/corrupt closure、closure set-once、
stale CAS after artifact put、same-ref idempotency、reopen readback。on-disk tests 标 integration；
不穷举 filesystem interleavings。

Review focus：closure completeness、artifact scope/path boundary、orphan handling、checkpoint authority、
operation/step duplicate semantic authority。

Container：`no`，除非本步实际触碰 bootstrap/entrypoint；benchmark N/A。

Short prompt：

```text
执行 P4-R4-S2a，按 plan 冻结 checkpoint/READY closure contract，完成 round-trip/integrity/CAS focused
gates、diff review 和 handoff；不开始 S2b。
```

## 10. P4-R4-S2b — Registry composition and executor adapter

```yaml
step_id: P4-R4-S2b
context: new_conversation
objective: compose immutable R4 registry into the existing worker entrypoint without changing R3 lifecycle policy
```

Allowed paths：

```text
vnext/backend/src/gateway_backend/application/job_definitions.py
vnext/backend/src/gateway_backend/application/__init__.py
vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
vnext/backend/tests/test_job_definition_registry.py
vnext/backend/tests/test_operation_worker_integration.py
vnext/backend/tests/test_operation_worker_process.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r4-s2b-handoff.md
```

Implementation requirements：

1. composition root 创建 immutable registry 和 R3-compatible adapter；Operations 不 import application；
2. worker startup 在 candidate claim 前解析 key/version/payload support；unknown runnable candidate 保持
   durable unchanged 并 fail closed；
3. empty DB 的 idle/ready 语义保持兼容；R4 registered synthetic jobs 只增加 resolver coverage；
4. handler invocation 前完成 payload/ref load 和 bounded decode；DB transaction 内不执行 handler/artifact I/O；
5. 不增加 worker identity、registry table、socket、IPC、hot reload、second executor 或 real effect；
6. process logs 只包含 bounded IDs/categories，不能泄露 payload/path/token/SQL。

Tests：composition import gate、empty registry compatibility、registered key startup、unknown key no mutation、
subprocess startup/exit redaction。涉及真实 process 的测试标 `integration`/`serial`。

Container：`yes`（触碰 worker bootstrap/composition boundary）；本步只记录
`container_gate: deferred`，required execution point 为 S7 current-HEAD image gate。

Review focus：bootstrap/Operations/application direction、entrypoint compatibility、empty/unknown behavior、
container trigger、R3 lifecycle regression。

Short prompt：

```text
执行 P4-R4-S2b，按 plan 组合 R4 immutable registry 与 R3 executor adapter，完成 process/integration
focused gates、diff review 和 handoff；不开始 S3a。
```

## 11. P4-R4-S3a — Idempotent pure-compute synthetic job

```yaml
step_id: P4-R4-S3a
context: new_conversation
objective: prove one restartable pure-compute JobDefinition and normal terminal publication
```

Allowed paths：

```text
vnext/backend/src/gateway_backend/application/synthetic_jobs.py
vnext/backend/tests/test_operation_job_synthetic.py
vnext/backend/tests/test_operation_job_recovery.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r4-s3a-handoff.md
```

Implementation requirements：

1. 使用 deterministic bounded input，产生 canonical output artifact/checkpoint，不读取业务数据库；
2. 相同 durable payload + prior outputs + checkpoint 重复执行产生相同 semantic output/digest；
3. 正常 completion 只通过 R3 session publication，READY closure 在所有 output refs 验证后设置；
4. handler 可观察 cooperative cancel；effect boundary 前 cancel 只发布允许的 `CANCELLED`；
5. 不实现 retry/takeover、动态 successor 或 generic job runner。

Tests：fresh run、checkpoint reload、duplicate delivery、output digest、READY closure、cancel-before-
publication、terminal publication idempotency。纯逻辑用 unit；artifact file/reopen 用 integration。

Review focus：determinism、payload interpretation leakage、checkpoint completeness、duplicate terminal、
artifact reference ordering。

Container：`deferred_to_s7`，因为本步不再改 bootstrap；benchmark N/A。

Short prompt：

```text
执行 P4-R4-S3a，按 plan 完成纯计算 synthetic job、checkpoint reload/duplicate/cancel tests、focused
gates 和 handoff；不开始 S3b。
```

## 12. P4-R4-S3b — Deterministic external-effect stub synthetic job

```yaml
step_id: P4-R4-S3b
context: new_conversation
objective: prove request checkpoint and identity preservation without real external effects
```

Allowed paths：

```text
vnext/backend/src/gateway_backend/application/synthetic_jobs.py
vnext/backend/src/gateway_backend/application/external_effect_stub.py
vnext/backend/tests/test_operation_job_synthetic.py
vnext/backend/tests/test_operation_job_recovery.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r4-s3b-handoff.md
```

Implementation requirements：

1. test-only stub 接收 immutable request artifact/ref 和 stable idempotency key；返回 deterministic
   operation identity；
2. 支持 accepted、confirmed、unknown 三种 test outcome；unknown 不映射为 FAILED/CANCELLED；
3. request/checkpoint identity 在重复 delivery 中保持不变；禁止生成 second key；
4. R4 只记录 durable request/checkpoint/identity，R5 才决定 poll/reconcile/takeover/manual；
5. stub 不使用网络、Dolt、Repository path、真实 external target 或 production fault control。

Tests：before request、after request sent、confirmed、unknown、duplicate delivery、cancel-before-
request、cancel-after-request、crash-before/after durable checkpoint。unknown outcome tests must
assert no blind replay and no new idempotency key。

Review focus：effect identity ownership、unknown outcome boundary、cancel semantics、test-only isolation、
R5 policy leakage。

Container：`deferred_to_s7`；本步不宣称 production effect validation。

Short prompt：

```text
执行 P4-R4-S3b，按 plan 完成 deterministic external-effect stub、identity/unknown/cancel fault tests、
focused gates 和 handoff；不开始 S3c。
```

## 13. P4-R4-S3c — Cross-boundary reload and fault matrix

```yaml
step_id: P4-R4-S3c
context: new_conversation
objective: validate R4 consumers across reload, corruption, duplicate, crash and READY barriers
```

Allowed paths：

```text
vnext/backend/tests/test_operation_job_recovery.py
vnext/backend/tests/test_operation_worker_process.py
vnext/backend/tests/test_operation_worker_integration.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r4-s3c-handoff.md
```

Required matrix：

| Boundary | Required assertion |
|---|---|
| payload reload | restart resolves same registered version and same semantic input |
| checkpoint round-trip | active Step checkpoint is readable, bounded and digest-verified |
| artifact missing/corrupt | no READY, no false terminal success, bounded diagnostic |
| closure set-once | second closure or conflicting ref is rejected without durable overwrite |
| duplicate delivery | one terminal publication and one semantic output |
| cancel before request | allowed `CANCELLED` with no external identity |
| cancel after request/unknown | original identity/checkpoint retained; no blind replay |
| crash before/after CAS | durable state proves either pre-publication or committed publication |
| stale CAS | artifact may remain unreferenced, but no stale durable ref is published |

Process crash/restart tests must distinguish durable readback from R5 takeover; they may not claim that
expired RUNNING disposition or reconciliation is implemented. Fixed wait/process tests are `serial`;
on-disk artifact/WAL tests are `integration`.

Review focus：one authoritative test owner per invariant, no copied private interleaving matrix, no evidence
state machine expansion, marker correctness and redaction.

Container：`deferred_to_s7` unless process harness changes require earlier diagnostic build.

Short prompt：

```text
执行 P4-R4-S3c，按 plan 完成 reload/corruption/duplicate/crash/cancel/READY fault matrix、marker review
和 handoff；不开始 S4。
```

## 14. P4-R4-S4 — Focused review

```yaml
step_id: P4-R4-S4
context: mandatory_new_conversation
change_kind: review_docs_only
objective: independently review R4 implementation against sealed design and owner boundaries
```

Reviewer 必须从磁盘读取 entry brief、plan、S1a-S3c handoffs、全部 R4 source/tests、当前 diff、
R1/R2/R3 handoffs 和 artifact contracts。不得只读 handoff 摘要。

Review checklist：

1. JobDefinition owner、registry key/version 和 Operations/application dependency direction；
2. immutable registry、unknown key/version no-mutation 和 empty-registry compatibility；
3. decoder bounds、payload/checkpoint version separation、no implicit migration；
4. ArtifactStorePort/ArtifactRef path, size, digest and identity boundary；
5. Step checkpoint authority、Operation summary non-duplication 和 CAS publication freshness；
6. READY closure exact refs, one-time set, missing/corrupt fail-closed；
7. deterministic output、successor/static chain、terminal duplicate；
8. external stub identity、unknown outcome、cancel-before/after request and R5 boundary；
9. artifact-before-CAS/orphan policy does not create cleanup/evidence authority；
10. no handler/artifact/network/long compute in DB transaction；
11. test marker ownership, parameter-table convergence and no Dolt misuse；
12. bootstrap/image/container trigger, logs and implementation authorization boundary。

P1/P2、contract ambiguity、stale writer gap、unknown outcome replay、READY false positive、unbounded
resource or owner violation 必须 `rework_required`。跨 R1/R2/R5/P5/deployment/security 的 finding
必须 reopen owning contract，不得在 S4 直接修 production。

Allowed change：
`docs/backend-vnext/refactoring/formal/plans/p4-r4-s4-focused-review.md` only。

Short prompt：

```text
在新对话执行 P4-R4-S4 focused review。读取 R4 sealed handoffs、source/tests 和 Git diff，按 checklist
只输出 finding/disposition，不就地修改 production 或 tests。
```

## 15. P4-R4-S5 — Conditional finding-scoped remediation

S4 无 finding 时创建 docs-only disposition：`not_applicable_no_findings`，不创建空 code step。

存在 finding 时，先写 `p4-r4-s5-remediation-appendix.md`，逐项记录 severity、owner、allowed
paths、regression test、commands、container impact、closure 和 reopen condition；只有 finding
appendix 明确授权的文件可改。每项修复必须重跑对应 focused tests、marker gate、ruff/mypy 和
S4 focused rereview。

S5 默认开启新对话；若仅补充 review 文档且不修改 source/test，可留在 S4 对话，但仍需产生
独立 disposition。任何 production fix 不得自动进入 S6。

Short prompt（有 finding）：

```text
执行 P4-R4-S5，按 S4 finding appendix 只做 finding-scoped remediation、回归验证和 handoff；不开始 S6。
```

Short prompt（无 finding）：

```text
记录 P4-R4-S5 not_applicable_no_findings，封存 S4 disposition 和下一步 S6 边界，不修改 production。
```

## 16. P4-R4-S6 — Independent review

```yaml
step_id: P4-R4-S6
context: mandatory_new_conversation
applicability: required
objective: prove cross-owner barriers without inheriting implementation assumptions
```

Independent reviewer 只依 sealed docs、source/tests、Git evidence 和适用 S5 closure。发现 defect
只输出 finding 并回 S5，不在 S6 就地修 production。

Required bounded probes：

1. unknown key/version first candidate 不生成 RUNNING/lease；
2. registry immutable，resolver 不执行 filesystem/network/hot reload；
3. payload/checkpoint decoder 不在 DB transaction 内 I/O 或回写；
4. artifact ref digest mismatch、missing bytes 和 closure mismatch 不产生 READY；
5. stale CAS 在 artifact 已写入后不能发布 stale checkpoint/terminal ref；
6. ready closure 只能设置一次，所有 refs 在 publication 前可读；
7. duplicate pure compute/stub delivery 不生成第二 terminal 或第二 idempotency key；
8. cancel-before-request 与 cancel-after-request 分别遵守 `CANCELLED`/R5 handoff boundary；
9. process termination before/after CAS 留下可解释的 durable state；
10. logs 不包含 path/token/payload/SQL，failure exit 非零且无 false READY。

不穷举 SQL/thread schedule，不建立 generic fault runner、durable evidence、broker 或 cleanup
probe。S6 输出 `p4-r4-s6-independent-review.md`，并明确所有 finding closed/reopen 后才可 S7。

Short prompt：

```text
在新对话执行 P4-R4-S6 independent review。只依 sealed R4 handoffs、source/tests 和 Git evidence
执行 bounded probes；输出 finding，不就地修 production，不开始 S7。
```

## 17. P4-R4-S7 — Current-HEAD module gate and handoff

```yaml
step_id: P4-R4-S7
context: new_conversation
objective: seal R4 tested tip, synthetic contracts, reload evidence and current image provenance
```

Entry：S4 pass；适用 S5 closed；S6 pass；final source/test committed；validated candidate 是 HEAD
ancestor；无未记录 in-scope changes。

Allowed changes：R4 handoff、Active Context、formal README、本 plan/brief 的状态、SHA、命令结果和
owner reference。若 gate 发现 source/test defect，停止并回 S5，不在 S7 即兴修 production。

Required backend gates：

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_operation_contracts.py tests/test_operation_state.py \
  tests/test_operation_store.py tests/test_sqlite_operation_store.py \
  tests/test_job_definition_contracts.py tests/test_job_definition_registry.py \
  tests/test_job_payload_decoding.py tests/test_operation_checkpoint_contracts.py \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py \
  tests/test_operation_worker_contracts.py tests/test_operation_lease_session.py \
  tests/test_operation_worker_startup.py tests/test_operation_worker_scheduler.py \
  tests/test_operation_worker_lifecycle.py tests/test_architecture.py
uv run pytest -q -m unit
uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
uv run pytest -q -m serial \
  tests/test_operation_job_recovery.py tests/test_operation_worker_process.py
uv run ruff check .
uv run mypy
```

五包 `ruff/mypy`、`git diff --check`、SHA ancestry、R4 source/test tree identity 和 docs link
validation 必须记录。R4 不运行 Dolt/Repository integration；stub 和 process harness 不得表述
为 production effect validation。

由于 S2b 触碰 worker bootstrap/composition，Current-HEAD container gate 为 required：

```text
docker build -f vnext/backend/Dockerfile -t <r4-candidate-tag> vnext
docker run --rm \
  -e GATEWAY_BACKEND_OPERATION_WORKER_CONTROL_DB_PATH=/var/lib/gateway/control/control.sqlite3 \
  -v <exact-host-control-dir>:/var/lib/gateway/control \
  <r4-candidate-tag> python -m gateway_backend.bootstrap.operation_worker
```

Container smoke 必须使用精确 `mktemp -d` host directory，启动后观察 synthetic registry coverage
和 `worker_ready`，运行一个 bounded pure-compute/stub fixture，发送 SIGTERM，断言 drain/no-new-claim/
exit 0 或规定的 non-zero failure；reopen DB 验证 WAL/schema/ref readback；检查日志无 path/token/
payload/SQL；记录 Git SHA、source tree、image ID/digest、commands 和 cleanup。任何后续 source、
bootstrap、settings、Dockerfile 或 process harness change 都使 image stale，必须重建。

S7 handoff 必须包含：public symbols、registry/version matrix、payload/checkpoint/closure documents、
synthetic job contracts、fault/reload evidence、review records、test commands、image provenance、
single-worker/local-SQLite limits、deferred/reopen register 和 `next_entry: P4-R5-S0`。R4 handoff
不得授权 R5/P5 implementation 或真实 Repository effect。

Short prompt：

```text
在新对话执行 P4-R4-S7 module gate。按 sealed R4 handoffs 重跑适用 gates，重建当前 HEAD image，
执行 synthetic worker container smoke，记录 provenance 并生成 R4 handoff；发现 source/test defect
立即回 S5，不开始 R5。
```

## 18. Global R4 stop/reopen rules

任何 step 命中以下情况立即停止：

- 修改 R1 record/status/transition、R2 schema/migration/store/CAS/error taxonomy；
- direct RUNNING lease replacement、Operation same-status checkpoint mutation 或 terminal Step-only publication；
- dynamic registry/hot reload、任意 DAG、多 executor、IPC、sidecar、新 principal；
- handler、decoder、artifact/network I/O 或长计算进入 DB transaction；
- retry/takeover/expired lease/manual recovery/reconcile policy 或真实 Repository effect；
- artifact cleanup、quarantine、durable evidence 或 generic external-effect journal；
- 需要改 Dockerfile/project install/Compose 但没有记录 container rebuild trigger；
- 现有 marker 无法表达新增 timeout/process/artifact boundary。

处理顺序固定为：evidence -> finding -> owning contract/ADR decision -> update brief/plan ->
finding-scoped implementation -> focused/independent rereview。


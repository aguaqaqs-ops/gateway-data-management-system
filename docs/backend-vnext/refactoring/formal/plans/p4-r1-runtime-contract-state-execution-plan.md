# P4-R1 Runtime Contract and State Detailed Execution Plan

状态：**R1 MODULE GATE PASS — R2-S0 ENTRY DISCUSSION AUTHORIZED**

日期：2026-08-23

Owner：Operation Runtime (`gateway_backend.operations`)

候选上游 revision：`1f3d5382f1ec26635e65103e09d017e21c784257`

上游：[P4 Entry Acceptance Candidate](p4-entry-acceptance.md)、[P4-R1-S0 Entry Brief](p4-r1-s0-entry-brief.md)、[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)、[P4 Durable Operation Runtime Execution Plan](p4-durable-operation-runtime-execution-plan.md)

Normative owners：[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、[Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)

## 1. Purpose and execution protocol

本文把 R1 从 entry acceptance 到 module handoff 拆成可独立执行、验证和提交的 context
packages。后续对话可以使用“执行 `P4-R1-S1a`”或“继续 R1 下一步”这样的短提示，但执行者
必须先读取本文、P4 Active Context、上一 step handoff 和当前 Git 状态，不能仅凭提示词补全
遗漏的 contract。

每次只执行一个命名 step：

1. 核对当前 HEAD 与上一步 handoff；工作区存在无关修改时保留并隔离处理；
2. 检查 entry prerequisites 与 reopen conditions；不满足则停止并记录 finding；
3. 只修改该 step 的 allowed paths，不顺手进入下一 step；
4. 运行 focused tests、适用的 backend static checks 和提交前五包 ruff/mypy；
5. review diff，记录 container/benchmark applicability；
6. 生成或更新 step handoff，提交当前 step；
7. 不自动开始下一 step。

“继续下一步”只在上一 handoff 为 `pass` 且明确写出 next step 时有效。S4 产生 finding 后，
“继续”进入 S5；没有 finding 时按 S4 disposition 决定 S6 或 S7，不能机械执行所有编号。

代码 step 使用两段 seal，避免 handoff 自引用尚不存在的 commit SHA：先在未提交的 code/tests
和适用 normative contract tree 上完成 focused gate、五包 static 与 diff review，再提交 candidate；
然后在 clean candidate 上复核 focused gate 和 tree identity，最后创建只含 formal handoff/index
的 docs commit，记录 `validated_code_sha`。handoff commit 后不得再改该 step production/tests。
Documentation-only step 记录 `reviewed_candidate_sha`，提交 acceptance/review record 后结束。

每个 handoff/review record 至少包含：

```yaml
step_id:
input_handoff_sha:
validated_code_sha:  # documentation-only step 使用 reviewed_candidate_sha
result: pass | rework_required
changed_paths: []
commands_and_results: []
focused_tests:
five_package_static:
container_gate:
benchmark:
findings: []
deferred_items: []
reopen_conditions: []
next_step:
next_step_authorized: yes | no
```

执行者若发现 handoff 后 code/test tree 已变化、`validated_code_sha` 不再是 ancestor、或新 HEAD
含未记录的 in-scope 修改，必须停止并重新验证；不得沿用旧 PASS。

## 2. Frozen R1 boundary

本节在 S0 前是待独立接受的 **decision packet**，不是新的永久 normative owner。S0 acceptance
record 必须逐项记录 accepted snapshot；S1b 再把 accepted public/persisted/state 规则同步进
`operation-lifecycle-and-integrity.md` 的 Phase 4 section。自 S1b handoff 起，该 contract 是唯一
语义 owner，本文只继续拥有 step/path/gate/handoff 编排；二者冲突必须 reopen，不能任选其一。

### 2.1 Physical paths

R1 production owner 只有：

```text
vnext/backend/src/gateway_backend/operations/__init__.py
vnext/backend/src/gateway_backend/operations/contracts.py
vnext/backend/src/gateway_backend/operations/state.py   # S2b 才创建
```

R1 tests：

```text
vnext/backend/tests/test_operation_contracts.py
vnext/backend/tests/test_operation_state.py
vnext/backend/tests/test_architecture.py
```

不创建 `backend_vnext` 顶层 Python package。R1 不移动 `app.py`、settings、HTTP、worker、
artifact adapter 或 capability；这些迁移属于 R3/P5 composition work。

### 2.2 Public surface candidate

S0 acceptance 必须确认或要求修改下列最小 public surface；未接受前不得实现：

```text
OPERATION_RUNTIME_CONTRACT_VERSION = "backend-vnext/operation-runtime/v1"

OperationStatus
StepStatus
JobStepKey
BusinessReference
OperationRecord
StepRecord
OperationDiagnostic
WritePrecondition
TransitionDisposition

operation_record_from_document(...)
step_record_from_document(...)
validate_operation_transition(...)
validate_step_transition(...)
validate_write_precondition(...)
```

所有 public symbols 从 `gateway_backend.operations` 受控导出；实现私有 helper 不进入
`__all__`。R1 不定义 JobDefinition handler、registry implementation、SQLite record、worker
claim result 或 Repository client DTO。

分步 publication 冻结为：S1a 只导出 version、两个 status enum 和 `JobStepKey`；S1b 增加
`BusinessReference`、record、diagnostic 和两个 parser；S2b 最后增加 precondition、disposition
和三个 guard。
S2b handoff 后 `__all__` 必须与上述清单完全一致。`JobStepKey` 是 frozen/slotted value object，
字段固定为 `job_kind`、`step_name`；它只表达 registry identity，不持有 handler/callable。
`BusinessReference` 同样是 frozen/slotted value object，只有 bounded opaque `kind`、`value`；
runtime 不枚举 kind，也不据此读取业务 entity。

候选函数形状如下；S0 可以整体接受或记录有依据的替代签名，S1a 不得临场改名：

```python
operation_record_from_document(document: object) -> OperationRecord
step_record_from_document(document: object) -> StepRecord
validate_operation_transition(
    current: OperationRecord,
    candidate: OperationRecord,
    *,
    recovery_authorized: bool = False,
) -> TransitionDisposition
validate_step_transition(
    current: StepRecord,
    candidate: StepRecord,
    *,
    recovery_authorized: bool = False,
) -> TransitionDisposition
validate_write_precondition(
    *,
    current_optimistic_version: int,
    current_worker_id: str | None,
    current_lease_token: str | None,
    precondition: WritePrecondition,
) -> None
```

`TransitionDisposition` 只有 `APPLY` 与 `IDEMPOTENT`。Contract/transition/precondition 拒绝统一
抛 `ValueError`；R1 不为纯逻辑 guard 创建跨 owner error taxonomy。`WritePrecondition` 固定包含
`expected_optimistic_version`、optional `worker_id`、optional `lease_token`。Operation-level mutation
后二者必须为 null；修改已租赁 RUNNING Step 时必须同时提供二者；claim 未租赁 Step 时二者为
null，由 candidate 建立新 lease。R2 负责把校验放进数据库原子 CAS，不能把 R1 的先读后验
当作持久化实现。

### 2.3 Contract representation

- frozen dataclass + `StrEnum`，遵循现有 backend contract 风格；
- `to_document()` 返回 JCS-compatible closed JSON object；parser 拒绝 unknown field/version/type；
- operation runtime contract 与 job payload contract 分开版本化；
- inline payload 只能是 JobDefinition owner 已验证的 bounded JSON document；runtime 只验证
  JSON/I-JSON shape 和资源预算，不解释业务字段；
- payload 与 payload ref 必须采用 S0 接受的互斥规则；不得保存 Python closure、class identity、
  callable、`Path`/host-path object、PID 或 provider-private object；runtime 不扫描 opaque payload
  中合法 JSON string 的业务含义，JobDefinition owner 必须在 admission 前把 server-owned path
  转换为 `ArtifactRef`；
- artifact/checkpoint 使用既有 public `ArtifactRef`，Repository operation ID 只作 bounded opaque ref。

R1 允许依赖 `gateway_shared_kernel` 的 public JCS/I-JSON primitives，以及
`gateway_backend.artifacts` 的 public `ArtifactRef`/serializer；不得 import capability package、
artifact store implementation、`infrastructure` 或 Repository package。Operations 不重新导出
`ArtifactRef`，其 wire/document shape 继续由 artifact owner 决定。

### 2.4 Closed document candidate

S0 冻结的是 persisted semantic document，不是 R2 SQLite column layout。两类 document 都是
closed object，`to_document()` 发出全部 keys（不适用值为 `null`），parser 要求 exact key set：

| Operation document keys | Step document keys |
|---|---|
| `contract_version`, `document_type`, `operation_id`, `job_kind`, `job_contract_version` | `contract_version`, `document_type`, `step_id`, `operation_id`, `step_name` |
| `job_payload`, `job_payload_ref`, `business_refs`, `artifact_refs` | `status`, `attempt_count`, `diagnostic`, `cancel_requested`, `retry_not_before` |
| `repository_operation_id`, `checkpoint_ref`, `ready_closure_ref` | `worker_id`, `lease_token`, `lease_expires_at`, `checkpoint_ref`, `prior_output_refs` |
| `status`, `diagnostic`, `cancel_requested` | `created_at`, `updated_at`, `started_at`, `completed_at`, `optimistic_version` |
| `created_at`, `updated_at`, `completed_at`, `optimistic_version` | |

`document_type` 分别固定为 `operation` / `step`。`business_refs` item 是 closed
`{"kind": ..., "value": ...}`；`diagnostic` 是 closed `{"code": ..., "message": ...}`；
所有 artifact/ref item 复用 `ArtifactRef` 的正式 document shape。`job_payload` 与
`job_payload_ref` 恰有一个非 null；inline payload root 必须是 JSON object，空 payload 使用
`{}`，不以二者都 null 表达。Record 内的 `job_payload` 保存 canonical JCS `bytes`，避免 frozen
record 暴露可原地修改的 `dict`；`to_document()` 解码为 JSON object，parser 将 object canonicalize
为 bytes。Runtime 仍不解释 object keys。

Timestamp 使用 UTC `datetime` 语义，document 只接受 canonical
`YYYY-MM-DDTHH:MM:SS[.ffffff]Z`；拒绝 naive datetime、非 UTC offset、leap second 和额外
fraction 精度。tuple/list 输出保持 owner 提供的 semantic order；要求 identity 唯一的 refs
拒绝重复，不由 parser 静默排序或去重。

Python record fields 与 persisted keys 一一对应；`document_type` 是 serializer/parser
discriminator，不作为 record field：

| Record | Exact fields |
|---|---|
| `OperationRecord` | `contract_version: str`, `operation_id: str`, `job_kind: str`, `job_contract_version: str`, `job_payload: bytes | None`, `job_payload_ref: ArtifactRef | None`, `business_refs: tuple[BusinessReference, ...]`, `artifact_refs: tuple[ArtifactRef, ...]`, `repository_operation_id: str | None`, `checkpoint_ref: ArtifactRef | None`, `ready_closure_ref: ArtifactRef | None`, `status: OperationStatus`, `diagnostic: OperationDiagnostic | None`, `cancel_requested: bool`, `created_at: datetime`, `updated_at: datetime`, `completed_at: datetime | None`, `optimistic_version: int` |
| `StepRecord` | `contract_version: str`, `step_id: str`, `operation_id: str`, `step_name: str`, `status: StepStatus`, `attempt_count: int`, `diagnostic: OperationDiagnostic | None`, `cancel_requested: bool`, `retry_not_before: datetime | None`, `worker_id: str | None`, `lease_token: str | None`, `lease_expires_at: datetime | None`, `checkpoint_ref: ArtifactRef | None`, `prior_output_refs: tuple[ArtifactRef, ...]`, `created_at: datetime`, `updated_at: datetime`, `started_at: datetime | None`, `completed_at: datetime | None`, `optimistic_version: int` |

`OperationDiagnostic` exact fields 为 `code: str`, `message: str`；`BusinessReference` exact fields
为 `kind: str`, `value: str`；`JobStepKey` exact fields 见 §2.2。所有 dataclass 构造与 parser
共享同一 validator，不能形成 trusted-constructor 绕过。

Enum 提供 exact read-only predicates：`is_final_terminal` 对 §2.5 final set 返回 true；
`requires_manual_recovery` 只对 `MANUAL_RECOVERY_REQUIRED` 返回 true。它们不推断业务 occupancy、
external effect 或 claim eligibility。

### 2.5 Status interpretation to freeze at S0

候选状态集合保持：

```text
Operation: QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED,
           SUPERSEDED, MANUAL_RECOVERY_REQUIRED
Step:      PENDING, RUNNING, RETRY_WAIT, SUCCEEDED, FAILED,
           CANCELLED, MANUAL_RECOVERY_REQUIRED
```

Enum member 与 persisted value 均使用上面列出的 uppercase exact spelling；不提供 lowercase、
legacy alias 或宽松 coercion。

推荐将 `SUCCEEDED | FAILED | CANCELLED | SUPERSEDED` 定义为 final terminal；
`MANUAL_RECOVERY_REQUIRED` 是不可自动 claim 的 attention state，不是可释放业务占用的普通
terminal。只有 authorized recovery 可以从 attention state 恢复执行或发布 owner 允许的终局。
S0 acceptance 必须明确该解释，消除“MANUAL 是否 terminal”的歧义。

结构状态矩阵候选：

| From | Allowed target |
|---|---|
| Operation `QUEUED` | `RUNNING`, `CANCELLED`, `SUPERSEDED` |
| Operation `RUNNING` | `SUCCEEDED`, `FAILED`, `CANCELLED`, `SUPERSEDED`, `MANUAL_RECOVERY_REQUIRED` |
| Operation `MANUAL_RECOVERY_REQUIRED` | `RUNNING`, `SUCCEEDED`, `FAILED`，且要求 authorized recovery |
| Operation final terminal | same-state idempotent publication only |
| Step `PENDING` | `RUNNING`, `CANCELLED` |
| Step `RUNNING` | `RETRY_WAIT`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `MANUAL_RECOVERY_REQUIRED` |
| Step `RETRY_WAIT` | `RUNNING`, `CANCELLED` |
| Step `MANUAL_RECOVERY_REQUIRED` | `RUNNING`, `SUCCEEDED`, `FAILED`，且要求 authorized recovery |
| Step final terminal | same-state idempotent publication only |

R1 guard 只证明结构合法性和 recovery authorization；外部 effect 是否允许 cancel、fail 或
supersede 由 R5/JobDefinition owner 证明。R1 不用通用 boolean 猜测 Repository effect。

状态字段规则也在 S0 一并冻结：

- Step `RUNNING` 必须同时有 worker/lease token/lease expiry；其他 Step 状态三者必须同时为
  null。Operation 不复制 lease identity；
- Operation `FAILED | MANUAL_RECOVERY_REQUIRED` 和 Step
  `RETRY_WAIT | FAILED | MANUAL_RECOVERY_REQUIRED` 必须有 diagnostic；Operation
  `CANCELLED | SUPERSEDED` / Step `CANCELLED` 可有 owner reason；其他状态禁止 diagnostic；
- final terminal 必须有 `completed_at`；非 final（包括 MANUAL attention）必须为 null；
- Step `PENDING` 的 `attempt_count=0` 且 `started_at=null`；RUNNING/RETRY/MANUAL/SUCCEEDED/FAILED
  的 attempt 至少为 1 且必须有 `started_at`；CANCELLED 可为 0/null（claim 前取消）或保留已开始
  attempt；重试后保留第一次 started timestamp；
- Step `RETRY_WAIT` 必须有 `retry_not_before >= updated_at`；其他状态必须为 null；该时间只表达
  R5 已作出的 durable retry decision，不由 R1 读取 wall clock 或决定 backoff；
- `created_at <= updated_at`；started/completed 不得早于 created，也不得晚于 updated；started 与
  completed 同时存在时 started 不得晚于 completed；RUNNING lease expiry 必须晚于 updated；
- attention state 不可 claim；authorized recovery 先产生 accepted `RUNNING` 或允许的 final，
  不能原地只改 diagnostic/version；
- final same-state publication 只有 current/candidate 的完整 persisted record 相等才是
  `IDEMPOTENT`；包括 optimistic version 与 updated timestamp 在内的任何差异都是 conflicting
  duplicate。重试者必须重用最初 publication candidate，不得重建“近似相同”终态。

### 2.6 Budgets to freeze at S0

S0 应接受以下保守默认值或记录替代值及依据：

| Budget | Recommended default |
|---|---|
| opaque operation/step/worker/lease/repository ID | 1..255 UTF-8 bytes；拒绝 NUL/control/host path |
| `job_kind` / `step_name` | 1..128 ASCII `[A-Za-z0-9._:/-]`；`/` 是 opaque namespace 字符，不是 path separator |
| business reference `kind` / `value` | kind 同 `job_kind` pattern；value 1..255 UTF-8 bytes 且拒绝 control/host path |
| contract version | 1..128 ASCII printable |
| owner-provided failure/diagnostic code | 1..128 ASCII `[A-Z][A-Z0-9_.:-]{0,127}` |
| diagnostic message | 1..4 KiB UTF-8，不保存 row payload/secret |
| inline job payload canonical JSON | 最大 64 KiB；更大内容必须使用 artifact ref |
| inline JSON structure | 最大 depth 32、aggregate member/element count 4096、key 128 UTF-8 bytes、单个 string 16 KiB |
| business refs / artifact refs | 每个 tuple 最多 64；单 record 内所有 ArtifactRef 合计最多 64 |
| optimistic version / attempt count | non-negative I-JSON safe integer |

这些是 admission/持久化边界，不是性能 baseline。若 S0 认为某个 pattern 或数值缺少 consumer
依据，可缩减字段或保留为 S1a 明确 decision，但不能完全取消 bounded validation。

### 2.7 Immutable identity and mutation scope

Transition candidate 必须保持 record identity/envelope immutable：Operation 的 contract/identity、
job binding、payload/ref、business refs 与 `created_at` 不得改变；Step 的 contract、step/operation
identity、step name、prior output refs 与 `created_at` 不得改变。

其余 mutation 规则固定为：

- `cancel_requested` 只能 `false -> true`，不能复位；
- Operation `repository_operation_id` / `ready_closure_ref` 只能 `null -> value` 一次；
- Operation `artifact_refs` 只允许 append unique refs，current tuple 必须是 candidate prefix；
- operation/step checkpoint ref 可以替换，但必须是完整 immutable `ArtifactRef`；
- candidate `updated_at >= current.updated_at`；APPLY 时 optimistic version 恰为 current + 1；
- Attempt 只在 `PENDING | RETRY_WAIT -> RUNNING` 时递增一位；其他 transition 保持不变；
- 每次进入 RUNNING 建立新 worker/lease，离开 RUNNING 清空；任何跳号、回退或同次换 worker
  均拒绝。

R2 可增加 storage metadata，但不能把它加入 R1 persisted semantic contract。

`validate_operation_transition` / `validate_step_transition` 是 status matrix 与候选 record
mutation 的共同关系校验 owner。heartbeat、checkpoint、cancel intent 等非终态、非 attention
state same-status mutation 必须通过现有 transition guard；返回 `APPLY` 只表示 mutation
validation 通过，不增加 status matrix edge，也不把 mutation 伪装成状态 self-loop。R2 在 CAS
前必须组合执行 transition guard 与 `validate_write_precondition`。Final terminal duplicate
仍只有在完整 persisted record 相等时返回 `IDEMPOTENT`；`MANUAL_RECOVERY_REQUIRED` 禁止原地
same-status mutation。

## 3. Shared verification commands

Focused R1 commands按 step 选择：

```bash
cd vnext/backend
uv run pytest -q -m unit tests/test_operation_contracts.py tests/test_operation_state.py tests/test_architecture.py
uv run ruff check src/gateway_backend/operations tests/test_operation_contracts.py tests/test_operation_state.py tests/test_architecture.py
uv run mypy
```

封存任何代码 step handoff 前，五个 Python package 必须全部通过：

```bash
cd vnext/shared_kernel && uv run ruff check . && uv run mypy
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
cd vnext/repository_client && uv run ruff check . && uv run mypy
cd vnext/repository_service && uv run ruff check . && uv run mypy
cd vnext/backend && uv run ruff check . && uv run mypy
```

R1 测试不得创建 Dolt、启动外部进程或依赖固定时间预算，默认全部为 `unit`。若实际实现引入
timeout/Event/thread/subprocess，说明 R1 boundary 已漂移，先 reopen，不通过补 `serial` 掩盖。
R1 不触碰 image/deployment/container boundary；container rebuild 与 benchmark 均
`not_applicable`。S7 仍需记录当前 HEAD、未触发重建的理由和最后已知 image provenance，
不得声称 R1 HEAD 已通过容器门禁。

## 4. P4/R1-S0 — Independent entry acceptance

```yaml
step_id: P4-R1-S0
status: ready_for_independent_acceptance
objective: independently accept or reject P4 entry and the R1 execution boundary
implementation_authority: none_until_explicit_decision
```

### Inputs

- current Git revision and clean worktree;
- P4 Active Context、entry candidate、design、phase execution plan；
- R1-S0 brief 和本文；
- normative contracts/ADR/policy；
- actual `gateway_backend` package/test inventory。

### Required checks

1. 分别裁定 `p4_entry_acceptance` 与 `p4_r1_s0`，不得用一个 PASS 隐含另一个；
2. 核对候选 revision/document hash 与 Git tree；旧 hash 不能用于修改后的候选；
3. 检查 `gateway_backend/operations` 落点与 architecture dependency direction；
4. 冻结 §2 public surface/signatures、closed key sets、MANUAL attention semantics、状态矩阵和 budgets；
5. 确认 R1 不接 SQLite/worker/HTTP/P5/Repository authority；
6. 核对 S1a–S7 每步的 path、test、review、handoff 和 reopen conditions；
7. 判断是否存在需先修改 owning contract/ADR 的 P1/P2 ambiguity。

### Allowed changes

- P4 formal plans/index/acceptance records；
- 不得修改 `vnext/**` source、tests、dependency 或 deployment files。

### Output

创建 `p4-r1-s0-entry-acceptance.md`，至少记录：

```yaml
acceptance_kind: p4_r1_s0
reviewed_candidate_sha:
p4_entry_acceptance: pass | rework_required
p4_r1_s0: accepted | rework_required
r1_s1a_authorized: yes | no
accepted_status_semantics:
accepted_public_surface:
accepted_document_keys:
accepted_budgets:
accepted_contract_source: p4-r1-runtime-contract-state-execution-plan.md@<reviewed_candidate_sha>#2
open_findings: []
deferred_items: []
next_step: P4-R1-S1a | none
```

同时更新 P4 Active Context。只有 `p4_entry_acceptance: pass`、`p4_r1_s0: accepted` 且
`r1_s1a_authorized: yes` 同时出现，短提示“执行 S1a”才有效。

通过时 Active Context 至少更新为：

```yaml
p4_entry_acceptance: pass
p4_r1_s0: accepted
p4_implementation_authorized: r1_s1a_only
r1_s1a_authorized: yes
```

### Exit

- independent record 与 reviewed revision 对齐；
- 无 open P1/P2 或 owner ambiguity；
- `git diff --check` 通过；
- documentation-only，tests/static/container `not_applicable` 并说明理由；
- acceptance 文档提交，worktree clean。

## 5. P4-R1-S1a — Package skeleton and public identity

```yaml
step_id: P4-R1-S1a
entry: S0 pass + r1_s1a_authorized yes
objective: create the sole operations package and freeze public identity
```

### Allowed paths

```text
vnext/backend/src/gateway_backend/operations/__init__.py
vnext/backend/src/gateway_backend/operations/contracts.py
vnext/backend/tests/test_operation_contracts.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/refactoring/formal/plans/p4-r1-*.md
```

### Implementation

- 创建唯一 `gateway_backend.operations` package；
- 定义 contract version、status enums 的 accepted names、`JobStepKey` value object；
- 建立显式 `__all__`，只导出 §2.2 规定的 S1a subset；
- architecture test 证明 capability 不反向 import operations、operations 不 import app/settings/
  infrastructure/capability private/Repository packages；
- `operation_kind` 不作为字段、alias、export 或兼容 shim。

S1a 不创建 record/parser/transition placeholder；这些 symbols 按 §2.2 的 publication step 引入。

### Tests

- package/contracts 可导入；
- version exact；enum 值 exact；registry key 使用 `job_kind + step_name`；
- S1a public export subset exact，无 `operation_kind`；
- architecture dependency tests。

运行 S1a focused tests、backend ruff/mypy、五包 ruff/mypy、`git diff --check`。

### Review / reopen

阻塞：第二个 package root、兼容 alias、业务状态字段、import private capability、需要新增依赖。

### Exit / handoff

创建 `p4-r1-s1a-handoff.md`：validated code SHA、commands/results、public exports、architecture
decision、container/benchmark N/A、deferred S1b work、`next_step: P4-R1-S1b`。提交后 clean。

## 6. P4-R1-S1b — Closed document contract

```yaml
step_id: P4-R1-S1b
entry: S1a handoff pass
objective: define closed persisted document shapes and parser rules
```

### Allowed paths

S1a paths，并允许修改
`docs/backend-vnext/refactoring/formal/contracts/operation-lifecycle-and-integrity.md`；不修改
dependency/deployment，`test_operation_contracts.py` 是主要 test owner。

### Implementation

- 按 §2.4 完成 Operation/Step exact key sets、nested diagnostic/ref shapes 和 `to_document`；
- 实现 strict `operation_record_from_document` / `step_record_from_document` parser skeleton；
- 校验 contract version、I-JSON integers、UTC/RFC3339 timestamp representation、bounded strings；
- payload/payload_ref 互斥、inline object/JCS compatibility、callable/`Path`/non-JSON object rejection；
- envelope identity/ref 执行 host-path rejection；不扫描 opaque payload JSON string 的业务含义；
- failure code 是 owner-provided bounded opaque code，不创建全局业务 failure enum；
- canonical bytes 只用于稳定 persistence round-trip，不新增 semantic digest/version axis。
- 把 S0 accepted public/persisted/state snapshot 同步到 Operation Lifecycle contract 的 Phase 4
  section；不接受本文与 contract 双 authority。

### Tests

- minimal/full document round-trip；object key reorder 后 canonical JSON 相同；
- shared module-level malformed shape tables覆盖 unknown/missing/type/version/budget；
- payload/ref exclusivity、identity/ref host path、non-JSON object、non-I-JSON、non-UTC timestamp；
- field/public symbol inventory；无重复同构 test functions。

### Review / reopen

阻塞：runtime 开始解释 job fields、复制 ArtifactRef contract、持久化 secret/row payload、
引入未接受 digest 或兼容 parser。

### Exit / handoff

`p4-r1-s1b-handoff.md` 记录 normative contract anchor、accepted document schema、parser limits、
test results、下一步 `P4-R1-S2a`。提交前执行 shared verification。

## 7. P4-R1-S2a — Immutable records and validation

```yaml
step_id: P4-R1-S2a
entry: S1b handoff pass
objective: complete immutable semantic records and cross-field invariants
```

### Implementation

- frozen/slotted `OperationRecord`、`StepRecord`、diagnostic 和 owner-local value objects；复用
  `ArtifactRef`，不复制 artifact value type；
- accepted status-specific required/forbidden field rules；
- optimistic version、attempt count、timestamps、lease identity/expiry 交叉校验；
- RUNNING step 的 lease fields 与非 RUNNING 状态清理规则；
- attention/final terminal semantics 可由显式 predicates 查询；
- parser 只构造已验证 record，不保留 caller-owned mutable objects。

Allowed production/test paths 与 S1b 相同。S2a 不创建 `state.py`，也不新增 public symbol；
只把 S1b record skeleton 收紧为 §2.5/§2.7 的完整 invariant。

### Tests

- 每个 status 的最小合法 record；
- shared parameter tables 覆盖 field combinations；
- frozen/tuple defensive ownership；
- final terminal 与 MANUAL attention predicates；
- record -> document -> record equality。

### Review / reopen

阻塞：状态字段无法表达 accepted invariant、MANUAL 被普通 terminal 释放、record 依赖业务
entity、需要 SQLite 默认值才能成立。

### Exit / handoff

`p4-r1-s2a-handoff.md` 记录 record invariants、focused/static results 和 `next_step: P4-R1-S2b`。

## 8. P4-R1-S2b — Pure transition and stale-write guards

```yaml
step_id: P4-R1-S2b
entry: S2a handoff pass
objective: implement pure structural transition and write-precondition guards
```

### Allowed additions

```text
vnext/backend/src/gateway_backend/operations/state.py
vnext/backend/tests/test_operation_state.py
```

### Implementation

- 实现 accepted Operation/Step transition matrix；
- same final status + matching terminal identity 返回 idempotent/no-op disposition；冲突 publication 拒绝；
- MANUAL recovery edges 必须显式 `recovery_authorized`；
- `WritePrecondition` 校验 expected optimistic version、worker identity 和 lease token；
- guard 只返回/抛出 Operations-owned结构结果，不执行 DB CAS、不读取 clock、不调用 Repository；
- cancel/supersede 只做 structural guard；effect safety 延后 R5。

函数签名、disposition 和 precondition fields 必须与 §2.2 一致。所有 accepted mutation 要求
candidate optimistic version 恰为 current + 1；terminal duplicate 的 `IDEMPOTENT` 是唯一不写入
也不递增版本的结果。

### Tests

- 模块级共享 transition matrix逐边验证 allowed/denied；
- final duplicate 与 conflicting duplicate；
- MANUAL 无授权拒绝、有授权允许；
- version/token/worker mismatch 全部拒绝；
- guard deterministic、无 wall clock/thread/process dependency。

### Review / reopen

阻塞：通过 bool 猜测外部 effect、guard 产生 side effect、允许 stale writer、允许 MANUAL
直接 CANCELLED/SUPERSEDED、状态矩阵与 S0 acceptance 漂移。

### Exit / handoff

`p4-r1-s2b-handoff.md` 记录 exact matrices、guard API、results 和 `next_step: P4-R1-S3a`。

## 9. P4-R1-S3a — Contract conformance hardening

```yaml
step_id: P4-R1-S3a
entry: S2b handoff pass
objective: prove persisted contract closure and malformed-input rejection
```

不新增 production semantics。扩展 `test_operation_contracts.py`：

- exhaustive public document key inventory；
- shared malformed tables覆盖所有 nested shapes/budgets；
- JCS canonical round-trip；unknown future version fail closed；
- payload/artifact/repository ref boundary；无 host path/Python object；
- property tests仅用于 bounded JSON round-trip，不扩大正式状态空间。

若测试揭示 contract 缺陷，先记录 finding；修复只能保持 S0 accepted semantics，否则 reopen。

Allowed production changes 默认 `none`；allowed tests/docs 为
`test_operation_contracts.py`、R1 plan/handoff。若发现保持 accepted semantics 的 production defect，
先在 handoff/finding 中记录，再只修改 `operations/contracts.py` 与对应 regression test。

Exit：focused/unit、五包 static、diff check 通过；`p4-r1-s3a-handoff.md` 指向 S3b。

## 10. P4-R1-S3b — State and recovery barrier hardening

```yaml
step_id: P4-R1-S3b
entry: S3a handoff pass
objective: prove lifecycle barriers independently of persistence implementation
```

不新增 DB/worker。扩展 `test_operation_state.py`：

- accepted matrices complete coverage；
- cancel request 与 CANCELLED publication 分离；
- SUPERSEDED 不绕过 attention/unknown-effect barrier；
- MANUAL 不释放、不可自动 claim、authorized recovery only；
- terminal status 不等于业务 finalize；
- stale-write precondition 在 heartbeat/checkpoint/terminal mutation 类型上一致；
- repeated evaluation deterministic。

Allowed production changes 默认 `none`；allowed tests/docs 为 `test_operation_state.py`、R1
plan/handoff。保持 accepted semantics 的 defect 只允许在记录 finding 后修改 `operations/state.py`
及对应 regression test。

Exit：focused/unit、五包 static、diff check 通过；`p4-r1-s3b-handoff.md` 指向 S4。

## 11. P4-R1-S4 — Focused owner review

```yaml
step_id: P4-R1-S4
entry: S3b handoff pass on a clean candidate
objective: review contract ownership, state barriers and implementation proportionality
production_changes: none unless findings are remediated in S5
```

Reviewer 必须检查：

- public/persisted/wire 是否混用；Operations 是否解释 job payload；
- MANUAL/unknown/cancel/supersede 是否破坏业务占用或 external-effect owner；
- stale writer contract 是否足够供 R2 原子 CAS 实现；
- parser/budgets 是否 bounded 且未建多余 digest/evidence/version axis；
- `gateway_backend.operations` import direction 和 public surface；
- tests 是否证明 contract barrier，而非内部逐行步骤；
- 是否意外触碰 container/dependency/P5/Repository boundary。

输出 `p4-r1-s4-focused-review.md`，finding 分级：

- P1/P2、contract ambiguity、recovery/authority gap：阻塞，进入 S5 或 reopen；
- P3 local maintainability/test clarity：可在 S5 合并处理；
- 无 finding：记录 `S5 not_required`，评估 S6。

## 12. P4-R1-S5 — Conditional remediation

S5 不预写固定修改。只有 S4 finding 存在时，先生成包含 finding ID、owner、allowed paths、
regression test、focused rerun 和 exit 的 remediation appendix。禁止用 S5 扩大 R1 scope。

所有 P1/P2 必须关闭或明确 reopen owning contract；不能以 deferred 绕过。完成后更新 S4
disposition，并生成 `p4-r1-s5-handoff.md`。无 finding 时不创建空 S5 文件。

## 13. P4-R1-S6 — Risk-based independent review

触发条件：

- S4/S5 曾发现状态、恢复、owner、持久 schema 或 stale-write P1/P2；
- MANUAL/unknown outcome 语义仍存在合理的不同解释；
- R1 修改了上游 contract/ADR；
- focused reviewer 参与了主要实现且无法形成独立证据。

未触发时，S4 record 写明 `S6: not_required` 与比例化理由。触发时由独立上下文读取 formal
owners、R1 candidate 和 tests，输出 `p4-r1-s6-independent-review.md`；不得把低层偏好升级为
新安全主体、broker、evidence service 或通用状态机。

若 S6 为 `rework_required`，其下一步仅可先执行 docs-only finding disposition：在 owning
Contract 与本计划中明确唯一语义 owner、允许路径、回归证明和 reopen 条件。该 disposition
完成前不得修改 production/tests；disposition 完成后仍须获得 remediation 授权，才能执行
conditional code/test 修复并重新运行独立审核。历史 S3b、S5、S6 记录保持封存，不通过改写
历史结论消除 finding。

## 14. P4-R1-S7 — Module gate and handoff

```yaml
step_id: P4-R1-S7
entry: S4 pass; S5/S6 dispositions closed
objective: seal R1 public contract and authorize R2 entry discussion
```

Required gates：

```bash
cd vnext/backend
uv run pytest -q -m unit tests/test_operation_contracts.py tests/test_operation_state.py tests/test_architecture.py
uv run pytest -q -m unit
uv run ruff check .
uv run mypy
```

以及其余四包 ruff/mypy。R1 不要求 Dolt integration、serial、benchmark 或 container build；
必须按 AGENTS.md 记录不适用理由和最后 image provenance。

输出 `p4-r1-runtime-contract-state-handoff.md`：

```yaml
handoff_kind: p4_r1
validated_code_sha:
p4_r1_exit: pass | rework_required
applicable_steps: []
skipped_steps_with_reason: []
focused_review:
independent_review:
focused_tests:
backend_unit:
five_package_static:
container_gate: not_applicable_r1_no_runtime_boundary_change
benchmark: not_applicable_contract_state_only
public_symbols: []
contract_version:
status_semantics:
deferred_items: []
reopen_conditions: []
next_entry: P4-R2-S0 | none
```

R1 handoff 必须更新 P4 Active Context。R1 不授权 P5、真实 Repository effect、worker 或
deployment implementation；只允许开始 R2 entry/design conversation。

## 15. Global stop/reopen rules

任何 step 遇到以下情况必须停止：

- 需要增加业务特定状态、解释 job payload 或执行 T1/T3；
- 需要修改 Repository wire、marker/ref/CAS 或推断 external effect；
- SQLite/worker/clock/thread/process 成为 R1 contract test 前置；
- 无法用 optimistic version + lease identity 表达 stale-write precondition；
- 需要 broker、sidecar、新 UID/helper/service、自定义 IPC 或外部 durable DB；
- 需要改变已接受的 MANUAL/unknown/cancel 语义；
- dependency、Dockerfile、Compose、entrypoint 或 container boundary 被触碰。

处理顺序：evidence -> finding -> owning contract/ADR decision -> 更新本文/fixture -> re-review；
不得通过兼容 shim、宽松 parser、额外状态或 mock 掩盖冲突。

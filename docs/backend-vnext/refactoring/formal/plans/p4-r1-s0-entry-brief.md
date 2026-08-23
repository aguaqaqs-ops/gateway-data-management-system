# P4-R1-S0 Entry Brief: Runtime Contract and State

状态：**READY FOR ACCEPTANCE**

日期：2026-08-23

Owner：Operation Runtime (`operations`)

上游：[P4 Entry Acceptance Candidate](p4-entry-acceptance.md)、[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)、[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、[Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)

## 1. Physical placement decision

逻辑架构名为 `backend_vnext`，当前 distribution 的物理 package root 为
`gateway_backend`。R1 正式落点冻结为：

```text
vnext/backend/src/gateway_backend/operations/__init__.py
vnext/backend/src/gateway_backend/operations/contracts.py
vnext/backend/tests/test_operation_contracts.py
vnext/backend/tests/test_operation_state.py
```

不创建平行的 `backend_vnext` Python package，不以兼容旧内部 import 为理由保留第二套
Operation Runtime。后续 `app.py`、settings、HTTP 和 worker interface 的迁移属于 R3/P5
composition work，必须保持功能语义不变并由对应 owner 冻结迁移步骤。

S0 asset inventory：

| 资产 | 当前事实 | R1 处理 |
|---|---|---|
| Python distribution root | `vnext/backend/src/gateway_backend/`；pyproject entrypoint 为 `gateway_backend:main` | 保留 root，在其下新增 `operations/` |
| Capability owners | `gateway_backend/capabilities/*` 已有 public `contracts.py` 和 architecture DAG | R1 不改 capability owner 或依赖 |
| Artifact boundary | `gateway_backend/artifacts/` 与 infrastructure adapter 已存在 | R1 只引用 ref/contract，不接 artifact store implementation |
| Operations package | 当前不存在 `gateway_backend/operations/` | S1a 创建唯一 package skeleton |
| Operations tests | 当前没有 `test_operation_*` contract/state owner tests | S3a/S3b 新增 focused unit tests |
| Architecture gate | capability import checker 禁止 capability 反向 import `operations` | 保持单向 `operations -> shared_kernel` |
| App/bootstrap | `gateway_backend/app.py`、settings 在 root | R3/P5 按 owner 迁入 interfaces/bootstrap，R1 不触碰 |

## 2. Objective

冻结 P4 Operations owner 的最小通用 contract，使后续 Durable Store、worker、JobDefinition
和 recovery 实现可以在不解释业务 payload 的前提下独立推进。

## 3. Non-goals

- 不实现 SQLite schema、worker loop、HTTP operation query 或业务 application use case；
- 不定义 Workspace、Submission、Archive、History、T1/T3 或 Repository marker/ref/CAS 语义；
- 不建立 generic evidence/closure 状态空间、任意 DAG 或动态脚本 workflow；
- 不把 Python closure、未版本化 context dict 或 provider-private object 作为 contract；
- 不改变已有 normative contracts 的 owner、wire 或错误语义。

## 4. Inputs and decisions to freeze

### 3.1 Operation/Step state

候选最小集合：

```text
Operation: QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED | SUPERSEDED | MANUAL_RECOVERY_REQUIRED
Step:      PENDING -> RUNNING -> RETRY_WAIT | SUCCEEDED | FAILED | CANCELLED | MANUAL_RECOVERY_REQUIRED
```

`READY` 是 output closure/readability predicate，不是通用 terminal status；Operation terminal
status 不表示业务 T3 已完成。

### 3.2 Generic envelope

Operation 必须只持久化通用 envelope：

```text
operation_id
job_kind
job_contract_version
job_payload or job_payload_ref
business IDs (opaque references only)
artifact refs/digests
repository_operation_id (optional)
checkpoint_ref (optional)
ready_closure_ref (optional)
created_at / updated_at
optimistic_version
```

Step 至少增加 `step_name`、`attempt_count`、`lease_token`、`lease_expires_at`、
`last_failure_code`、checkpoint ref 和 prior output refs。业务 payload 的 schema、retry policy
和 handler 语义由 application JobDefinition owner 拥有。

Runtime contract version 固定为 `backend-vnext/operation-runtime/v1`；JobDefinition registry
只使用 `(job_kind, step_name)`，`operation_kind` 不再作为别名或第二个持久字段。

### 3.3 State invariants

- 所有状态转移必须经过 owner-defined guard；terminal publication 幂等；
- claim、heartbeat、checkpoint、cancel request 和 terminal publish 均受 optimistic version/CAS 保护；
- lease token 与 worker identity 绑定；stale worker 的写入必须失败；
- cancellation 是 request/intent，不保证外部 effect 可取消；安全边界后才停止；
- unknown outcome 不得被表达为普通失败并释放业务占用；
- `MANUAL_RECOVERY_REQUIRED` 保持相关业务占用，直到 owner/operator 产生允许的终局；
- runtime 不解释 job payload，也不自行判断 Repository commit/ref/effect 事实。

## 5. Allowed paths and forbidden paths

允许修改：

- `vnext/backend/src/gateway_backend/operations/`；
- `vnext/backend/tests/` 中 R1 contract/state focused tests；
- P4 formal contract/design/plan 文档；
- 必要的 architecture/import test fixture。

禁止触碰：

- `vnext/repository_service/` wire、control DB、marker/ref/CAS 或 Docker runtime；
- `Workspace`、`Submission`、`Archive`、`History` 业务模块和 T1/T3 实现；
- P3 capability provider-private modules、R7 renderer/executor implementation；
- 依赖锁、Dockerfile、Compose、entrypoint 或部署配置（除非后续 R3 entry 明确授权）；
- 新 broker、sidecar、helper、UID/GID、独立服务或自定义 IPC。

允许路径已由本 S0 的 asset inventory 冻结；本 brief 仍不授权预创建空目录，S1a 才创建 package skeleton。

## 6. Applicable steps

R1 采用可裁剪模板，当前冻结为：

| Step | Applicability | Output |
|---|---|---|
| S0 | required | 本 entry brief、asset inventory、owner/reopen decision |
| S1a | required | package skeleton, version, registry key and public exports |
| S1b | required | closed document schema, enums and parser rules |
| S2a | required | frozen record/value validation |
| S2b | required | pure state transition and stale-write guards |
| S3a | required | contract round-trip and malformed document tests |
| S3b | required | transition/recovery barrier tests |
| S4 | required | focused owner review |
| S5 | conditional | 仅在 S4 finding 或 regression 需要时启用 |
| S6 | risk-based | 若状态/恢复/跨 owner ambiguity 未由 S4 充分证明则启用 |
| S7 | required | R1 handoff、tested tip、deferred/reopen register |

S1-S3 若实际上下文仍跨越多个独立 contract，必须拆分为 `S1a/S1b` 或 `S3a/S3b`；
若没有对应产物，不得为了模板完整性制造空步骤。

## 7. Tests and review focus

测试必须保持纯逻辑、无 Dolt、无外部进程：

- 合法状态转移和非法转移拒绝；
- terminal idempotency 与重复 terminal publish；
- cancel request、supersede 和安全边界语义；
- payload contract version、unknown version 和禁止任意 context dict；
- lease token/version 字段约束和 stale-writer guard 的 contract-level proof；
- unknown outcome、`MANUAL_RECOVERY_REQUIRED` 不被归类为普通失败；
- architecture/import test：Operations 不 import 业务模块或 capability 私有实现。

若测试包含固定 timeout、Event wait、thread join 或 subprocess timing，必须标记 `serial`；
纯状态/解析测试不得创建真实 repository。

Focused review checklist：

- 是否把 Operation terminal status 错当业务终局；
- 是否引入 generic failure/evidence taxonomy；
- 是否让 runtime 解释业务 payload；
- 是否缺少 stale worker、unknown outcome 或 cancel 的状态屏障；
- 是否产生跨模块反向依赖或新的安全主体；
- 是否有未版本化持久字段或不可恢复的 Python object。

## 8. Exit and handoff

R1-S0 通过条件：

- owner、scope、non-goals、allowed/forbidden paths 已接受；
- applicable steps 及合并/拆分理由已记录；
- 状态集合、envelope 和关键不变量没有与既有 contract 冲突；
- 测试 owner、review focus、reopen conditions 已明确；
- 没有需要先修改 ADR/contract 的 P1/P2 finding。

R1-S0 handoff 必须包含：accepted brief、asset inventory、tested tip（若有代码）、
applicable_steps、未决参数和 R1-S1 entry prerequisites。R1-S0 不包含生产代码实现，也不
改变 `p4_implementation_authorized`。

## 9. Reopen conditions

- 状态集合必须增加业务特定状态或 generic evidence 状态；
- Operation 需要解释 job payload 或直接持有业务 entity；
- stale worker CAS 无法由通用 contract 表达；
- cancel 必须调用外部 target 的强制取消接口；
- R1 需要修改 Repository Service wire 或引入新部署主体。

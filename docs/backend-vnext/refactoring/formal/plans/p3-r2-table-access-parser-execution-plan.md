# P3-R2 Table Access and Parser Execution Plan

状态：Accepted for staged execution；S7 module gate complete，R2 gate pass；handoff: [p3-r2-table-access-parser-handoff.md](p3-r2-table-access-parser-handoff.md)

日期：2026-08-19

阶段：P3-R2 complete；R3 detail plan pending

Owner：Backend vNext Table Access

上级计划：[P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)

设计基线：[P3 Capability Foundation Design §4.1](p3-capability-foundation-design.md#41-p3-r2-table-access-and-parser-design-baseline)

R1 入口：[P3-R1 Capability Foundation Handoff](p3-r1-capability-foundation-handoff.md)

## 1. Objective and exit

R2 建立可独立调用的 `table_access` public boundary：SQL source parser、generic XML
document parser、bounded descriptors/readers 和 stable parser diagnostics。R2 不实现
SourcePackage staging、Snapshot materialization、business XML materializer、Repository/Dolt
reader、storage/comparison projection、HTTP、Workspace、Submit 或 Operation Runtime。

R2 退出时必须交付：

- accepted `table_access` contracts and import/architecture checks；
- Python bounded SQL/XML providers with no automatic fallback；
- `COMPLETE | PARTIAL | FAILED` result semantics and stream completion commit point；
- deterministic typed descriptor/row/diagnostic fixtures；
- malformed, security, resource, cancellation and timeout conformance evidence；
- explicit deferred register and R3 entry handoff；
- no unresolved P1/P2 finding, contract ambiguity, dependency cycle or unbounded path。

## 2. Conversation and remediation policy

每个 step 的上下文策略固定如下。对话编号是治理边界，不要求复制全部历史内容；新对话
必须携带本计划、上一步 handoff、changed diff 和命令结果。

| Step | Conversation | Context rule |
| --- | --- | --- |
| S0 entry/handoff | 新开 R2 入口对话 | 读取 R1 handoff、P3 design §4.1、normative contracts、当前 git status；冻结 scope、ADR reopen 和 budgets |
| S1 contract/skeleton | 与 S0 同一对话 | 将 S0 决策落成 public contracts、owner/import checks 和最小 fixture shape |
| S2 SQL implementation | 新开实现对话 | 携带 S0/S1 handoff、允许路径、SQL grammar/type decisions 和测试命令 |
| S3 XML/conformance | 与 S2 同一实现对话 | 在同一实现上下文完成 XML provider、diagnostics、resource/cancel tests 和跨 provider conformance |
| S4 focused review | 新开审查对话 | 审查者只依赖计划、formal contracts、diff、fixtures 和测试输出，不依赖实现者口述 |
| S5 remediation | 不单独开 step/对话 | 发现问题时回到 S2/S3 实现对话修复、补 regression test；再回到原 S4 审查对话复审。该 loop 可重复，不另造 S5 记录 |
| S6 independent review | 新开独立审查对话 | 与实现/首次审查隔离，复核 owner、resource、failure、security、stream atomicity 和 deferred closure |
| S7 module gate | 新开验收/文档对话 | 汇总 tested tip、命令、结果、review closure、deferred register 和 R3 handoff |

审查 finding 的处理顺序固定为：

```text
S4/S6 finding
  -> issue register
  -> return to S2/S3 implementation conversation
  -> fix + regression test + focused rerun
  -> return to original review conversation
  -> re-review and close/reopen
```

P1/P2、contract ambiguity、digest/type mismatch、resource/security/recovery finding 未关闭或
正式 reopen owning contract/ADR 前，不得进入下一 gate。修复/复审不单独伪造 step、对话或
阶段编号，但必须在当前 review record 和最终 handoff 中留下 closure 引用。

## 3. Shared invariants and ownership

- `table_access` 是 capability layer leaf owner；不得 import 其他 capability、`_internal`、
  provider selection、builder、planner、cache layout、Repository Service 或 application。
- `snapshot_materialization` 是未来 consumer；R2 不反向依赖它。
- canonical identifier 只做 unquote 和 ASCII `A-Z -> a-z`；不 trim、Unicode normalize 或
  Unicode case-fold；canonical collision fail closed。
- descriptor 保留 DDL column order 和 primary-key order；row 是 positional tuple；raw/display
  names 不进入 semantic digest。
- R2 不计算 canonical business/storage digest；只传 parser facts、provenance 和 diagnostics。
- provider/thread/batch partition 不改变 descriptor/row/diagnostic semantic result；implementation
  identity 不进入 digest。
- reader single-consumer、non-rewind、reopenable；successful end-of-stream 是发布提交点。
- partial rows、host path、temporary path、Dolt path、SQL command 和 mutable provider object
  不跨 R2 boundary。

## 4. Allowed and forbidden paths

S0 必须确认以下 allowlist 的最终文件路径；新增路径必须在 step handoff 中登记。
S0 已确认并新增登记见 [P3-R2-S0 §11](p3-r2-s0-entry-and-budget-freeze.md)：

```text
vnext/backend/src/gateway_backend/capabilities/table_access/
vnext/backend/tests/test_table_access_*.py
vnext/backend/tests/support/table_access_*.py
vnext/fixtures/golden/table-access/
vnext/fixtures/vectors/table-access/
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/plans/p3-r2-table-access-parser-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r2-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r2-table-access-parser-handoff.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md
vnext/backend/tests/test_architecture.py
```

禁止：

```text
vnext/repository_service/
vnext/backend/src/gateway_backend/capabilities/common/
vnext/backend/src/gateway_backend/capabilities/utils/
snapshot_materialization implementation
storage/comparison/risk/mutation/application/HTTP/Operation Runtime
production retention/cleanup or new security principal
```

## 5. Step execution plan

### S0 — Entry, applicability and budget freeze

**Conversation**：新开 R2 入口对话。

**Objective**：证明 R1 handoff 可作为 R2 输入；解决 SQL ownership/ADR 0013 边界；冻结
SQL allowlist、known type closure、XML security policy、numeric budgets、allowed paths 和
fixture roots。

**Inputs**：R1 handoff、P3 design §4.1、P3 contracts、ADR 0013、testing conventions、当前
git status/source tip。

**Outputs**：S0 brief、decision register、resource budget table、reopen record、R2 owner graph。

**Must decide**：

- source parser grammar 属于 table_access；Repository import 只做 manifest/catalog validation；
- SQL statement allowlist 和 complete known type set；
- strict UTF-8 XML、DTD/entity/XInclude/network refusal；
- statement/table/column/row/field/XML/batch/diagnostic limits；
- parser-specific timeout/cancel input shape；
- fixture naming and parameter-table ownership。

**Tests/checks**：只读 contract cross-reference、`git status --short`、`git diff --check`、
owner/import graph review；S0 不改业务代码，不创建 Dolt。

**Exit**：无 unresolved ownership/contract ambiguity；S1 可只在 allowlist 内建立 skeleton。
S0 记录：[P3-R2-S0 Entry, Applicability and Budget Freeze](p3-r2-s0-entry-and-budget-freeze.md)。

### S1 — Public contract and import skeleton

**Conversation**：与 S0 同一对话。

**Objective**：落成 `table_access/contracts.py` 及最小 public entrypoint，不实现 parser algorithm。

**Outputs**：

- SQL/XML input refs and parser context contracts；
- descriptor、typed positional row、reader lifecycle、ParseResult、diagnostic contracts；
- `COMPLETE | PARTIAL | FAILED` and `READER_CLOSED/timeout/cancel` semantics；
- architecture/import tests proving table_access has no capability upstream；
- minimal valid/invalid fixture shapes。

**Forbidden**：business Snapshot fields、Repository DTO、generic common DTO、cache/retention schema。

**Tests**：backend unit architecture/import checks；ruff/mypy；no Dolt/no external process。

**Exit**：public contract importable；每个 type/field/code 有唯一 owner；S2/S3 不需猜测语义。
S1 记录见 [P3-R2-S0 §16](p3-r2-s0-entry-and-budget-freeze.md#16-s1-public-contract-skeleton-record)。

### S2 — SQL parser and SQL reader provider

**Conversation**：新开实现对话。

**Objective**：实现 bounded incremental SQL parser 和 deferred SQL reader，严格执行 S0 grammar。

**Required behavior**：

- parse comments、allowlisted boilerplate、`CREATE TABLE`、`INSERT INTO`；
- reject unsupported statements, duplicate schema/key, canonical collision, incomplete INSERT/default
  dependency and row shape mismatch；
- normalize identifiers only by accepted rules；preserve display names and DDL order；
- map known types to typed scalar values；ENUM/SET use accepted v1 malformed/value codes；unknown type
  yields bounded diagnostic and no READY reader；
- preserve source INSERT row order in reader; no dedup/overwrite/sort;
- enforce all S0 budgets and explicit cancellation/deadline;
- stream errors invalidate the table and all partial rows。

**Tests**：valid grammar/type cases；malformed statement/type/value cases；duplicate/collision cases；
NULL/default/row-shape cases；large input/statement/row/field limits；reader reopen/close/single-
consumer/stream-completion tests；timeout/cancel tests. Fixed timeout/event tests are `serial`.

**Exit**：SQL provider passes focused unit tests and exposes no host path, SQL executor or repository
dependency；S3 can consume only public contracts。

### S3 — XML parser, diagnostics and cross-provider conformance

**Conversation**：与 S2 同一实现对话。

**Objective**：实现 secure bounded XML event/node reader，并完成 SQL/XML shared diagnostics、
  resource and result conformance。

**Required behavior**：

- strict UTF-8; reject malformed XML, DTD, external entity, XInclude, network/external resource;
- preserve namespace-expanded names without business schema interpretation;
- enforce depth/node/attribute/text/document budgets;
- expose bounded event/node stream, not unbounded DOM;
- use same status, diagnostic ordering/truncation, cancellation, timeout and stream commit semantics;
- no `logics.xml` business materializer or derived table.

**Tests**：XML valid namespace cases；malformed/truncated/encoding cases；XXE/DTD/XInclude refusal；
  depth/node/text/size limits；partial stream and close/cancel/timeout；shared diagnostic ordering and
  max-size truncation；SQL/XML fixture oracle exact comparison；ruff/mypy and `git diff --check`。

**Exit**：SQL/XML providers satisfy one public result/diagnostic/lifecycle contract；all pure tests
  are unit-only and do not create Dolt。

### S4 — Focused contract/resource/security review

**Conversation**：新开 focused review 对话。

**Review inputs**：S0/S1 decisions, S2/S3 diff, fixture corpus, test output, budget evidence,
architecture/import output and deferred register。

**Review focus**：ownership/ADR 0013 closure；SQL allowlist/type mapping；identifier/schema facts；
  XML parser security；bounded memory/streaming；partial-result atomicity；diagnostic determinism；
  cancellation/timeout；no Repository/Dolt/application scope expansion；test marker correctness。

**Exit**：findings register complete；no unclassified P1/P2; accepted non-blockers and reopen owner
  recorded. Findings are remediated through the S2/S3 loop described in §2, not a new S5 dialogue。

### S5 — Embedded remediation loop (no standalone step)

S5 不作为独立执行步骤、独立对话或独立编号记录。S4/S6 发现问题后，回到对应 S2/S3 实现
对话修复并补 regression test，再回到原审查对话复审；若 contract/ADR 改变，先 reopen owner，
更新 S0/S1 decision record，再继续实现。最终 handoff 必须列出 finding、修复 commit、复审结果。

### S6 — Independent review

**Conversation**：新开独立审查对话。

**Minimum checks**：独立重跑 unit/architecture/ruff/mypy/diff check；抽查 SQL/XML fixture
  expected output；复核 resource budgets、stream completion commit point、cancel/timeout、
  XML external-resource refusal、partial status、forbidden imports/paths、deferred register 和
  R3 entry prerequisites。

**Exit**：independent pass；无未处理 P1/P2、contract ambiguity、unbounded path、import cycle 或
  hidden Repository/application dependency。否则使用 §2 loop，不创建额外 remediation step。

### S7 — R2 module gate and R3 handoff

**Conversation**：新开验收/文档对话。

**Required record**：tested source tip、changed paths、精确命令和结果、fixture roots、budget
  revision、S4/S6 findings closure、known limitations、deferred register、contract/ADR refs、
  implementation authorization status。

**R2 gate commands**：

```text
cd vnext/backend && uv run pytest -m unit
cd vnext/backend && uv run ruff check . && uv run mypy
git diff --check
```

如新增固定时间预算测试，另跑 `uv run pytest -m serial -n 0` 的精确 nodeid；R2 纯 parser/table-
access 测试不得创建 Dolt。若 S0/S1 新增独立 benchmark runner，S7 记录其 dataset/provider/
budget、raw samples、peak RSS、wall time、cancellation latency 和限制；无 numeric performance
claim。

**R3 handoff prerequisites**：

- stable descriptor/reader/diagnostic public boundary；
- accepted SQL/XML input and resource budgets；
- typed row/NULL/unknown-type semantics；
- `COMPLETE | PARTIAL | FAILED` and stream commit point；
- no Repository/Dolt implementation dependency；
- R2-D04–D09 deferred items explicitly linked；
- parser output can be consumed by R3 materialization without importing provider-private state。

## 6. Reopen conditions

- source parser 与 Repository import ownership 无法通过 ADR/contract 明确分离；
- SQL grammar/type mapping 与 accepted canonical/storage semantics 冲突；
- XML parser 可访问外部资源、构造无界 DOM 或绕过 UTF-8/budget 门禁；
- reader 在错误后允许 partial rows 伪装为 READY；
- cancellation/timeout/resource limit 无稳定诊断或测试证明；
- table_access import capability、Repository、application 或 provider-private state；
- 纯 R2 test 创建 Dolt、依赖永久 workspace path 或使用宽泛 skip/错误 marker；
- 新增 shared primitive 不能证明至少两个独立 consumer。

## 7. Status and deferred references

```yaml
module: P3-R2
status: s7_complete
implementation_authorized: no
current_step: S7_complete
s0_record: p3-r2-s0-entry-and-budget-freeze.md
upstream: p3-r1-capability-foundation-handoff.md
design_baseline: p3-capability-foundation-design.md#41-p3-r2-table-access-and-parser-design-baseline
deferred_register: p3-capability-foundation-design.md#r2-provider-assurance-and-deferred-register
next_module: P3-R3
s6_record: this_plan#9-s6-independent-review-record
s7_record: this_plan#10-s7-module-gate-record
s7_handoff: p3-r2-table-access-parser-handoff.md
p3_r2_exit: pass
p3_r3_ready: yes
```

## 8. S4 focused review record

状态：**PASS；无未处理 P1/P2 finding；S5 remediation loop 已完成**。

审查只依赖本计划、S0/S1 records、当前累计 diff、fixture corpus、formal contracts/ADR 和
可重现命令输出，不采用实现者口述。审查 source tip 为 `9e70e4bf6ae1341b4013a1a2d3ab9dd67b64b7bb`
加当前 worktree 的 R2 implementation/test changes；本记录与这些 changes 尚未提交。

### 8.1 Evidence

| Check | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit` | **211 passed**；1 existing Starlette deprecation warning |
| Focused SQL/XML reader/resource/conformance rerun | **40 passed** |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed**；77 source files |
| `git diff --check` | **passed** |
| Architecture/import and forbidden-path scan | **passed**；table_access remains a leaf |
| Dolt/Repository/application/external process use | **none** |

No fixed wait, event budget, thread join, subprocess sleep or stream timeout test was added, so no
additional `serial -n 0` run was required. No Docker/Compose/image boundary changed; container rebuild
is deferred to the S7 final candidate per the execution-plan rule.

### 8.2 Findings register and closure

| ID | Area / severity | Finding | Closure evidence |
| --- | --- | --- | --- |
| `S4-001` | SQL bounded streaming / **P1** | `iter_statements()` accumulated every statement span in a list, allowing statement-count memory to grow independently of table/row budgets. | Changed `_sql_scan.iter_statements` to yield spans incrementally; full unit and focused reruns pass. |
| `S4-002` | XML text budget / **P2** | Expat character callbacks accumulated a whole text node before checking `max_xml_text_node_bytes`. | Enforced byte budget during `_character_data`; `max_xml_text_node_bytes` regression passes and failed results publish no events. |
| `S4-003` | Reader stream atomicity / **P1** | Reader exceptions did not retain an invalidated state, so descriptor access after a stream cancel/error remained visible. | `SqlTableReader` records the stable `TableAccessError`; regression `test_reader_stream_error_invalidates_reader_instance` passes. |
| `S4-004` | Ownership / ADR 0013 | No finding. | Source parser/type mapping remains table_access-owned and independent from Repository validation; architecture checks pass. |
| `S4-005` | XML security | No finding. | Expat external entity, DTD, XInclude, network and non-UTF-8 refusal fixtures pass; no external resolver/resource path exists. |
| `S4-006` | Diagnostics/cancel/timeout | No finding. | Shared SQL/XML status, ordering/truncation, cancellation and deadline conformance passes. |
| `S4-007` | Scope/test classification | No finding. | No forbidden capability/import path, Dolt fixture, broad skip, or incorrect marker; all pure parser tests are unit-only. |

All initial findings are closed in the S2/S3 remediation loop with regression evidence. No contract or
ADR reopen is required, no deferred item was silently promoted, and no new security principal or
shared primitive was introduced.

### 8.3 Decision and carry-forward

S4 is complete and the implementation may proceed to the separately isolated S6 independent review.
S6 must independently re-run the unit/architecture/ruff/mypy/diff checks and recheck stream commit
semantics, XML external-resource refusal, resource budgets, forbidden imports/paths and the deferred
R2-D04--D09 register. This S4 record does not claim S6 or S7 completion.

## 9. S6 independent review record

状态：**PASS；无未处理 P1/P2 finding、contract ambiguity、unbounded path 或 import cycle。**

本审核与 S2/S3 实现及 S4 focused review 对话隔离。结论只依据本计划、S0/S1 records、累计
implementation/test diff、fixture corpus、formal contracts/ADR 和下列可重现命令输出；不采用
实现者口述作为 evidence。

### 9.1 Review tip and changed surface

```yaml
reviewed_source_tip: 9e70e4bf6ae1341b4013a1a2d3ab9dd67b64b7bb + current_worktree_R2_changes
worktree_state: dirty; R2 implementation/tests/fixtures are uncommitted
container_rebuild: no
container_rebuild_reason: S6 review and current R2 changes do not touch image, deployment, or container-only runtime boundaries
last_validated_image_revision: none
container_validation_deferred_to: S7 final candidate if an image/deployment/container boundary is introduced
```

The changed implementation surface remains within the S0 allowlist: `table_access` contracts,
bounded SQL/XML providers, table-access tests/support helpers, and table-access fixtures. No
Repository Service, Dolt, application/HTTP, materialization, storage, comparison, retention,
Operation Runtime or new security principal was added.

### 9.2 Independent checks

| Check | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit` | **212 passed**; 1 pre-existing Starlette deprecation warning |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py` | **14 passed** |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed**; no issues in 77 source files |
| `git diff --check` | **passed** |
| Forbidden import/path and external-resource scan | **passed**; no Repository/Dolt/application/external process or resolver path |

The unit run includes SQL/XML golden oracle, malformed/security/resource-limit, cancellation,
timeout, reader lifecycle/stream invalidation, and cross-provider diagnostic conformance tests.
No fixed event/thread/process timeout test was added, so no additional `serial -n 0` run was
required. No Docker/Compose/image boundary changed; source-tree validation is authoritative for
this review tip.

### 9.3 Minimum boundary review

| Area | Result | Evidence / disposition |
| --- | --- | --- |
| Contract owner and dependency graph | **Pass** | `table_access` remains a capability leaf; architecture tests pass and imports are contracts/shared-kernel only. |
| SQL grammar/type and identifier facts | **Pass** | Allowlist, known-type vectors, canonical collision, DDL/PK order, row shape and typed values match S0/ADR 0013 fixtures. |
| Bounded resource handling | **Pass** | SQL source/statement/table/column/row/field/tuple and XML document/depth/node/attribute/text/name/diagnostic budgets have boundary tests; statement spans are incremental. |
| Stream completion and failure atomicity | **Pass** | Reader is single-consumer, reopenable and invalidates on stream cancel/error; failed XML and parser results publish no partial events/readers. |
| Cancellation and timeout | **Pass** | Shared `PARSER_CANCELLED`/`PARSER_TIMEOUT` diagnostics are covered for SQL, XML and reader streaming. |
| XML security | **Pass** | Strict UTF-8, DTD/entity, external entity, XInclude, network and non-UTF-8 refusal fixtures pass; no external resolver/resource access exists. |
| Diagnostics and determinism | **Pass** | Stable offset/code ordering, bounded messages/total size, truncation marker and SQL/XML oracle comparison pass. |
| Scope and test classification | **Pass** | All pure parser tests are unit-only; no Dolt fixture, broad skip, forbidden path or incorrect marker. |

### 9.4 Finding closure and deferred register

S4 findings `S4-001`–`S4-003` remain closed with their regression tests passing; `S4-004`–`S4-007`
remain no-finding dispositions with no regression. S6 identified and closed one P2 stream-boundary
finding during this review:

| ID | Area / severity | Finding | Closure evidence |
| --- | --- | --- | --- |
| `S6-001` | Reader EOF cancellation / **P2** | `SqlTableReader.iter_rows()` had no cancellation checkpoint after the final yielded row, so cancellation at successful EOF (including an empty stream) could be treated as a committed completion. | Added the EOF commit-point checkpoint and regression `test_reader_checks_cancellation_at_successful_eof_commit_point`; focused and full unit reruns pass. |

`S6-001` was fixed in the S2/S3 remediation loop boundary and rechecked in this independent review;
no contract or ADR reopen is required.

The deferred register is unchanged and explicitly carried forward: `R2-D04` business XML
materialization, `R2-D05` Repository/Dolt reader, `R2-D06` canonical/storage projection,
`R2-D07` retention/lifecycle, `R2-D08` Rust/optimization, and `R2-D09` durable cancellation/
checkpoint/takeover remain outside R2. `R2-D01`–`R2-D03` remain closed by S0/ADR 0013 and their
boundary evidence is included in this review.

### 9.5 Independent review decision

**S6 PASS.** The current R2 candidate satisfies the S6 minimum checks and has no blocking finding.
It may proceed to S7 module gate/handoff. This record does not claim S7 completion, R2 final gate,
container validation, or authorization of any deferred R3/P4 capability.

S7 must record the final tested source tip, exact changed paths, commands/results, fixture roots,
S4/S6 closure, deferred register, R3 entry prerequisites, and implementation authorization status.

## 10. S7 module gate record

状态：**PASS**；handoff: [P3-R2 Table Access and Parser Handoff](p3-r2-table-access-parser-handoff.md)。

S7 confirmatory rerun against `validated_code_sha`
`2a799cf30508ab6a380718eeacd6f721fc247b20`（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit` | **212 passed**（1.16s）；1 pre-existing Starlette deprecation warning |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 77 source files |
| `git diff --check` | **passed** |

No serial nodeid, Dolt, or container rebuild. S4-001–003 and S6-001 remain closed.
`R2-D04`–`R2-D09` are carried forward. `p3_r2_exit: pass`；`p3_r3_ready: yes`；
`p3_implementation_authorized: no`。R3 必须先写详细计划再实现。

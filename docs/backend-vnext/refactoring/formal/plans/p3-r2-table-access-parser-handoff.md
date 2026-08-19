# P3-R2 Table Access and Parser Handoff

状态：`pass`（R2 module gate；R3 entry。不是 Phase 3 全部实现授权，不含 source materialization）

日期：2026-08-19

Owner：Backend vNext Table Access

本文是 P3-R3 的**默认 R2 入口**。它记录 R2 gate 身份、稳定 public boundary、测试证据、
限制和 R3 prerequisites。`logics.xml` 业务解释、Snapshot 字段和 Repository/Dolt reader
仍由后续 owner 拥有；不得从 parser 私有模块猜测。过程证据见 S0 freeze、S4/S6 reviews
和 R2 执行计划。

上级计划：[P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)
R2 执行计划：[P3-R2 Table Access and Parser Execution Plan](p3-r2-table-access-parser-execution-plan.md)
S0 冻结：[P3-R2-S0 Entry, Applicability and Budget Freeze](p3-r2-s0-entry-and-budget-freeze.md)
设计基线：[P3 Capability Foundation Design §4.1](p3-capability-foundation-design.md#41-p3-r2-table-access-and-parser-design-baseline)

```yaml
handoff_kind: p3_r2_table_access_parser
round: P3-R2-S7
s4_review: pass
s6_review: pass
p3_r2_exit: pass
p3_r3_ready: yes
p3_implementation_authorized: no
worktree_at_validated_tip: clean_after_implementation_commit
validated_code_sha: 2a799cf30508ab6a380718eeacd6f721fc247b20
s0_entry_sha: 9e70e4bf6ae1341b4013a1a2d3ab9dd67b64b7bb
container_rebuild: no
benchmark: not_applicable
```

`validated_code_sha` 是 S6 已审且本 S7 复跑通过的代码 SHA，不是本 handoff 文档 commit
SHA。S7 开始时工作树含未提交的 R2 实现与 S0–S6 记录；它们已收进 `validated_code_sha`。
文档提交完成后成为 `r3_entry_sha` / `handoff_documentation_sha`，不在本文件中自引用。

## 1. Gate identity

```yaml
branch: phase1/gate-ownership-repair
s6_reviewed_tip: 2a799cf30508ab6a380718eeacd6f721fc247b20
s6_review_record: p3-r2-table-access-parser-execution-plan.md#9-s6-independent-review-record
s4_review_record: p3-r2-table-access-parser-execution-plan.md#8-s4-focused-review-record
s0_record: p3-r2-s0-entry-and-budget-freeze.md
s5: embedded_in_s2_s3_loop
s7_tests_rerun: yes
container_rebuild_reason: R2 candidate is pure Python parser/test/docs and does not touch image, deployment, or container-only runtime boundaries
last_validated_image_revision: none; source-tree validation is the authoritative evidence
container_validation_deferred_to: a later R if an image/deployment/container boundary is introduced, or the P3 final candidate
benchmark_reason: S0/S1 did not add an independent benchmark runner; no numeric performance claim
```

```text
Current HEAD at S7 rerun: worktree that became 2a799cf30508ab6a380718eeacd6f721fc247b20
Container rebuild required: no
Reason: no Dockerfile, lock, entrypoint, Compose, UID/GID, volume, or container-only runtime change
Last verified image revision: none
Last verified source-tree/image id: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: none
Required execution point: later R if an image/deployment/container boundary is introduced, or P3 final candidate
```

## 2. Commit lineage

核对命令：

```bash
git log --reverse --format='%H %s' \
  9e70e4bf6ae1341b4013a1a2d3ab9dd67b64b7bb..2a799cf30508ab6a380718eeacd6f721fc247b20
```

```yaml
commit_lineage_count: 1
commit_lineage:
  s0_s6:
    stage_final_reviewed_tip: 2a799cf30508ab6a380718eeacd6f721fc247b20
    subject: "feat(backend): add P3-R2 table access SQL and XML parsers"
    stage_exit: pass
    note: S0–S6 were executed and reviewed in-tree before this single implementation commit; S4/S6 records live in the R2 execution plan
  s7:
    reviewed_tip: 2a799cf30508ab6a380718eeacd6f721fc247b20
    stage_exit: pass
    note: S7 independently retested this tip; the S7 handoff documentation commit follows and is not this SHA
```

## 3. Changed paths

Cumulative implementation/test/docs surface in `9e70e4b..2a799cf`, plus this S7
handoff documentation commit:

```text
vnext/backend/src/gateway_backend/capabilities/table_access/
vnext/backend/tests/test_table_access_*.py
vnext/backend/tests/support/table_access_*.py
vnext/backend/tests/test_architecture.py
vnext/fixtures/golden/table-access/
vnext/fixtures/vectors/table-access/
docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-r2-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r2-table-access-parser-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r2-table-access-parser-handoff.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

S1 已登记 `tests/test_architecture.py`。S7 新增登记 handoff 与上级状态索引路径。
`p3-r1-capability-foundation-execution-plan.md` 与 `p3-r1-s0-asset-inventory.md`
仅同步「R2 detail plan accepted」状态行，不改变 R1 合同。

No SourcePackage staging, Snapshot materialization, storage/comparison projection,
HTTP, Workspace, Submit, Operation Runtime, Repository/Dolt reader, production
retention, or new security principal was introduced.

## 4. Commands and results

S7 confirmatory rerun against the worktree that became `validated_code_sha`
`2a799cf`（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit` | **212 passed**（1.16s）；1 pre-existing Starlette deprecation warning |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 77 source files |
| `git diff --check` | **passed** |

No command used Dolt, Repository Service, HTTP, Workspace, Submit, an operation
runtime, or an external parser process. No `@pytest.mark.serial` test was added,
so no `uv run pytest -m serial -n 0` run was required. Timeout/cancel tests use an
already-expired `deadline_monotonic` or cooperative probe, not a sleep/join budget.

## 5. Findings closure and deferred register

| ID | Status |
| --- | --- |
| `S4-001` | Closed; incremental `iter_statements()`; unit rerun passes |
| `S4-002` | Closed; XML text budget enforced during character data; unit rerun passes |
| `S4-003` | Closed; stream error invalidates the reader instance; unit rerun passes |
| `S4-004`–`S4-007` | No-finding dispositions; no S6/S7 regression |
| `S6-001` | Closed; EOF commit-point cancellation checkpoint; unit rerun passes |
| `R2-D01` | Closed in S0; §8 budgets unchanged in S7 |
| `R2-D02` | Closed in S0 / ADR 0013 dual-boundary |
| `R2-D03` | Closed in S0; stdlib SQL scanner + `xml.parsers.expat` |
| `R2-D04` | Deferred to R3；owning materialization contract |
| `R2-D05` | Deferred to R3 / P2 integration；repository provider contract |
| `R2-D06` | Deferred to R3/R4；storage owner contract |
| `R2-D07` | Deferred to P4/P5；lifecycle/retention owner |
| `R2-D08` | Deferred to P6 or later；accepted profile + Python oracle |
| `R2-D09` | Deferred to P4；Operation Runtime contract |

**No-open-blocker.** 无未处理 P1/P2 finding、contract ambiguity、import cycle、
unbounded path 或 hidden Repository/application dependency。S7 未 reopen ADR 或
owning contract；S0 numeric budgets 未修订。

权威延后表：[P3 design §4.1 deferred register](p3-capability-foundation-design.md#r2-provider-assurance-and-deferred-register)。

## 6. Contract, ADR and fixture references

```text
docs/backend-vnext/refactoring/formal/plans/p3-r2-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md
docs/backend-vnext/refactoring/formal/contracts/repository-service.md
docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md
docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md
docs/backend-vnext/refactoring/formal/contracts/fixture-oracle-and-conformance.md
docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md
vnext/fixtures/golden/table-access/sql/valid/
vnext/fixtures/golden/table-access/sql/malformed/
vnext/fixtures/golden/table-access/xml/valid/
vnext/fixtures/golden/table-access/xml/malformed/
vnext/fixtures/golden/table-access/xml/security/
vnext/fixtures/vectors/table-access/sql-known-types/v1/
vnext/fixtures/vectors/table-access/sql-identifier/v1/
vnext/fixtures/vectors/table-access/xml-security/v1/
```

S0 resource budgets remain the authority and were not revised in S7. Fixture
naming and parameter-table ownership remain `table_access`.

## 7. Stable public boundary

R3 可消费 `gateway_backend.capabilities.table_access` 的 public surface 与
`contracts.py`。不得 import `_sql_*`、`_xml_parser`、`_parser_runtime` 或构造
private `TupleSpan`。

Public entrypoints and result types：

```text
parse_sql(SqlParseRequest, *, budgets=RESOURCE_BUDGETS) -> ParseResult
parse_xml(XmlParseRequest, *, budgets=RESOURCE_BUDGETS) -> XmlParseResult
ParseStatus: COMPLETE | PARTIAL | FAILED
SourceTableDescriptor / SourceColumnDescriptor / SourceRow / SourceCell
TableReader (descriptor / iter_rows / close)
ParserDiagnostic + ParserDiagnosticCode + diagnostic_sort_key
RESOURCE_BUDGETS / ParserInvocationContext
```

`ParseResult.tables[].reader` 在 READY 表上发布 `TableReader`。R3 应对该协议编程，
不依赖 `SqlTableReader` 构造函数。`SqlTableReader` 虽由 package 重导出，其
`reopen()` 与 source-span 状态仍是 provider 细节；重新打开应调用 `reopen()` 或
再次 `parse_sql`，不要复制私有 span。

`XmlParseResult.events` 是 domain-neutral 的 bounded event 流，保留
namespace-expanded name。`logics.xml` schema 与 `composite_signal_point`
derived-table 解释属于 `R2-D04`，不在本边界内。

Capability DAG 不变：`table_access` 仍是 leaf；`snapshot_materialization` 可以
import `table_access` contracts，R2 不得反向依赖它。Architecture tests 覆盖
forbidden tokens（`dolt`、`gateway_repository`、`host_path`、`lxml`、`defusedxml`）。

## 8. Known limitations and deferred items

- R2 不计算 canonical business/storage digest；只传 parser facts、provenance 和
  diagnostics（`R2-D06`）。
- unknown SQL type 可保留 bounded descriptor/diagnostic，但不发布 READY reader。
- INSERT 必须提供完整列值；DEFAULT / generated / expression default 不由 parser
  推导。
- XML 不建立无上限 DOM，也不做业务 namespace alias。
- in-process cancel/deadline only；durable cancellation/checkpoint/takeover 是
  `R2-D09`。
- 无独立 parser benchmark runner；不得从本 handoff 读取 numeric performance claim。
- `MaterializedTableReader` 仅用于 contract/fixture lifecycle，不是 SQL/XML
  production reader。

## 9. R3 entry prerequisites

R3 详细计划已创建：[P3-R3 Source Materialization and Snapshot Execution Plan](p3-r3-source-materialization-execution-plan.md)。R3 entry 必须拿到并保持：

- stable descriptor/reader/diagnostic public boundary（§7）；
- accepted SQL/XML input and resource budgets（S0 §8；S7 未修订）；
- typed row / SQL `NULL` / unknown-type semantics（READY reader 禁 unknown）；
- `COMPLETE | PARTIAL | FAILED` 与 successful end-of-stream commit point；
- no Repository/Dolt implementation dependency in `table_access`；
- `R2-D04`–`R2-D09` explicitly linked（§5）；
- parser output can be consumed without importing provider-private state。

R3 仍须先写详细计划再实现。本 handoff 不授权 source materialization、business XML
materializer、Repository/Dolt reader 或其他 P3 capability 算法。

## 10. Non-goals and authorization

R2 未做、R3 不得从本文推断为已授权：

- `logics.xml` / `composite_signal` 业务 materializer 与 derived tables（`R2-D04`）；
- Snapshot artifact closure、reuse/fallback profile；
- Repository/Dolt-backed reader 与 hidden summary readback（`R2-D05`）；
- canonical raw/business digest 与 storage projection（`R2-D06`）；
- HTTP、Workspace、Submit、Operation Runtime；
- production retention/cleanup、新的安全主体、container/image validation；
- Rust parser 或 automatic fallback（`R2-D08`）。

```yaml
p3_r2_exit: pass
p3_r3_ready: yes
p3_implementation_authorized: no
```

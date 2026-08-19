# P3-R2-S0 Entry, Applicability and Budget Freeze

状态：S0 complete；S1 skeleton complete；S2 SQL parser complete；S3 XML parser complete；`p3_implementation_authorized: s2_s3`

日期：2026-08-19

Owner：Backend vNext Table Access

本文是 P3-R2 的 **S0 权威记录**。它冻结 ownership、SQL allowlist、known type closure、
XML security、numeric budgets、timeout/cancel 输入形状和 fixture 根目录。字段级
public contract 由 S1 落成；parser 算法由 S2/S3 实现。不得从 R1 skeleton 猜测 parser
语义。

上级计划：[P3-R2 Table Access and Parser Execution Plan](p3-r2-table-access-parser-execution-plan.md)
设计基线：[P3 Capability Foundation Design §4.1](p3-capability-foundation-design.md#41-p3-r2-table-access-and-parser-design-baseline)
R1 入口：[P3-R1 Capability Foundation Handoff](p3-r1-capability-foundation-handoff.md)

```yaml
handoff_kind: p3_r2_s0_entry_and_budget_freeze
round: P3-R2-S0
p3_r1_exit: pass
p3_r2_ready: yes
p3_r2_s0_exit: pass
p3_implementation_authorized: s2_s3
r1_validated_code_sha: fc5159576b30de5bd8c1428446537aa92a23642b
r1_handoff_documentation_sha: 9e70e4bf6ae1341b4013a1a2d3ab9dd67b64b7bb
s0_worktree: dirty_docs_only
container_rebuild: no
benchmark: not_applicable
```

`r1_validated_code_sha` 是 R1-S6 已审代码 tip。`r1_handoff_documentation_sha` 是
R1-S7 handoff 文档 commit。S0 开始时工作树仅有未提交的 R2 design/plan 文档，无
`vnext/` 代码变更。本文件和 ADR/plan 状态更新是本次 S0 文档交付。

## 1. Review boundary and evidence

本审查按照 [P3-R2 execution plan](p3-r2-table-access-parser-execution-plan.md) S0
只读范围执行。语义 authority 依次采用 P3 contracts/ADR、P3 design §4.1、R1 handoff，
再采用现有 architecture/import tests 作为边界 evidence。legacy 与过程文档不作为
当前 contract。

已读取并用于本结论的 authority：

- [P3-R1 Capability Foundation Handoff](p3-r1-capability-foundation-handoff.md)；
- [P3 Capability Foundation Design §4.1](p3-capability-foundation-design.md#41-p3-r2-table-access-and-parser-design-baseline)；
- [Repository Service](../contracts/repository-service.md) §10 / §10.1；
- [Shared Canonical Encoding](../contracts/shared-canonical-encoding.md)；
- [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)；
- [Fixture Oracle](../contracts/fixture-oracle-and-conformance.md)；
- [Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md)；
- [ADR 0013](../adr/0013-enum-set-v1-import-semantics.md)；
- [Testing Conventions](../../../testing-conventions.md)、[Testing Fixtures](../../../testing-fixtures.md)；
- `vnext/backend/src/gateway_backend/capabilities/table_access/`、
  `vnext/backend/tests/test_architecture.py`。

本次没有修改业务代码、parser 实现、fixture 文件或 Repository Service contract。
ADR 0013 仅修订 source-parser / import-validation 双边界，不改变 ENUM/SET 值、
Arrow 或 wire 语义。

## 2. R1 handoff applicability

| P3-R2 entry requirement | Evidence | Result |
| --- | --- | --- |
| stable public owner/import checks | R1 handoff §7；`ALLOWED_UPSTREAM_OWNERS["table_access"] = frozenset()` | **PASS** |
| accepted shared primitive inventory | R1 `D-001`–`D-007`；无新 primitive | **PASS** |
| artifact/staging helper contract | `vnext/backend/tests/support/artifact_staging.py`；R2 parser 可不消费它 | **PASS / unused in R2 algorithm** |
| no-open-blocker | R1 §5 | **PASS** |
| parser questions from P3 contracts, not R1 skeleton | `table_access/contracts.py` 未预声明 TableReader 字段；本 S0 从 §4.1 与 Repository §10 读取 | **PASS** |
| R1 未授权 parser 实现 | `p3_implementation_authorized: no` 保持 | **PASS** |

R1 可作为 R2 输入。S0 不把 R1 skeleton 当作 parser 合同。无 blocking finding
要求暂停 R2 entry。

## 3. Owner graph

```text
Shared Canonical Encoding (Shared Kernel)
  ^
  | public identifier ASCII fold / scalar / null / DigestRef
  |
table_access (R2 leaf owner)
  |-- source SQL dump grammar, identifier unquote, typed positional rows
  |-- generic XML event/node stream
  |-- parser diagnostics registry and ParseResult
  `-- no capability upstream; no Repository/Dolt/application import

snapshot_materialization (R3 consumer)
  `-- may import table_access.contracts only; R2 must not import it

table_rules (independent leaf)
  `-- not a table_access dependency

Repository Service §10 / §10.1
  |-- catalog/manifest sql_type, Arrow, import/read wire codes
  `-- known type closed set is authority for dump-side recognition;
      implementations are not shared
```

Forbidden directions:

```text
table_access -X-> snapshot_materialization / other capability
table_access -X-> gateway_repository_service / candidate_a.sql
table_access -X-> capabilities/common / capabilities/utils / sql_utils
table_access -X-> HTTP / Workspace / Submit / Operation Runtime / Dolt
artifacts -X-> table_access parser-private state
```

Existing architecture tests already encode the capability DAG. S1 只扩展
`table_access` public contracts，不得改变该图方向。

## 4. Decision register

| ID | Decision | Rationale |
| --- | --- | --- |
| `R2-S0-D01` | source dump grammar 属于 `table_access`；Repository import 只做 manifest/catalog validation | P3 design §4.1；Repository §10 已限定在 catalog/manifest `sql_type` |
| `R2-S0-D02` | 修订 ADR 0013 为双边界；不共享 parser implementation | 关闭 R2-D02 的 ownership 歧义；ENUM/SET 值/Arrow/wire 语义不变 |
| `R2-S0-D03` | known type 闭合集以 Repository §10 为权威；table_access 独立识别并映射 Shared Kernel typed scalar，不产出 Arrow | dump parser 与 import converter 是不同物理 mapping |
| `R2-S0-D04` | 冻结 §5 SQL statement allowlist | dump boilerplate 必须可验收；未列 statement fail closed |
| `R2-S0-D05` | 冻结 §6 known type closure 与 ENUM/SET fail-closed codes | 与 ADR 0013 / Repository §10.1 对齐 |
| `R2-S0-D06` | XML 使用 stdlib `xml.parsers.expat` incremental handler；不加第三方 parser | 关闭 R2-D03；现有 backend 依赖无 parser library |
| `R2-S0-D07` | 冻结 §8 numeric budgets | 关闭 R2-D01；外层 256 MiB / 1 GiB 不是 R2-specific 替代品 |
| `R2-S0-D08` | 冻结 §9 `ParserInvocationContext` | in-process cancel/deadline；durable takeover 仍是 R2-D09 |
| `R2-S0-D09` | 冻结 §10 fixture roots 与参数表 ownership | table_access 唯一 owner；不消费 Repository ENUM/SET corpus |
| `R2-S0-D10` | 登记 §11 新增允许路径；不改 `repository-service.md` | Repository contract 已限定 catalog/manifest，无需本步扩写 |

无 S0 blocking finding。不新增 shared primitive。

## 5. SQL statement allowlist

Keyword 大小写不敏感。唯一 delimiter 是 `;`。源必须是严格 UTF-8；非法 UTF-8 在
source admission fail closed。

### 5.1 Accepted

- comments：`--`、`#`、`/* */`。
- MySQL versioned comment `/*!NNNNN ... */`：仅当内层 statement 属于本 allowlist
  时展开；否则 fail closed。
- `CREATE TABLE [IF NOT EXISTS]`：
  - descriptor 保留 display name、canonical identifier、DDL column order、
    nullability、primary-key order（inline 或 table-level）和 bounded normalized
    SQL type；
  - table option `ENGINE` / `CHARSET` / `COLLATE` / `AUTO_INCREMENT` / `COMMENT`
    忽略；
  - `KEY` / `INDEX` / `UNIQUE` / `FOREIGN` / `CHECK` 忽略且不进入 descriptor；
  - `GENERATED` / 需推导的 default expression fail closed。
- `INSERT INTO t VALUES (...)`，或带**完整**列清单的
  `INSERT INTO t (cols) VALUES (...)`。多 tuple 允许。省略列、依赖 `DEFAULT`、
  generated column、`INSERT ... SET`、`INSERT ... SELECT` fail closed。
- 无语义 dump boilerplate：
  - `DROP TABLE IF EXISTS t`（R2 parser 无 catalog，故无 mutation）；
  - 受限 `SET`：`NAMES`、`CHARACTER_SET_*`、`COLLATION_CONNECTION`、`TIME_ZONE`、
    `UNIQUE_CHECKS`、`FOREIGN_KEY_CHECKS`、`SQL_MODE`、`SQL_NOTES` 及其 `@OLD_*`
    恢复赋值；
  - `LOCK TABLES` / `UNLOCK TABLES`；
  - `ALTER TABLE t DISABLE KEYS` / `ENABLE KEYS`。

同一 table 重复定义、duplicate column、duplicate primary key、canonical identifier
collision 和 row shape 不一致均为明确错误；不做 dedup、覆盖或 last-write-wins。
`CREATE TABLE IF NOT EXISTS` 不改变 duplicate-table 错误。

### 5.2 Rejected

`REPLACE`、upsert / `ON DUPLICATE KEY UPDATE`、`INSERT IGNORE`、其它 DDL、
trigger / procedure / event、`DELIMITER`、`USE` / `CREATE DATABASE`、ANSI_QUOTES
双引号标识符、隐式执行语义，以及未列 statement。

### 5.3 Identifier normalization

Parser 先 unquote：反引号 `` ` ``，` `` ` 转义；或 unquoted
`[A-Za-z_][A-Za-z0-9_$]*`。然后交给 Shared Kernel：只做 ASCII `A-Z -> a-z`；不
trim、不 Unicode normalize、不 Unicode case-fold。空值、非法 Unicode 和 canonical
collision fail closed。display names 保留；raw/display names 不进入 semantic digest。

## 6. Known type closure

与 [Repository Service](../contracts/repository-service.md) §10 同一闭合集。
table_access 独立实现 dump 侧识别；不 import Repository converter，不产出 Arrow。

| Normalized SQL type | R2 dump mapping |
| --- | --- |
| `BOOLEAN` | Shared Kernel boolean scalar |
| `TINYINT [UNSIGNED]` | signed/unsigned integer 8-bit |
| `SMALLINT [UNSIGNED]` | signed/unsigned integer 16-bit |
| `MEDIUMINT [UNSIGNED]` | signed/unsigned integer 24-bit |
| `INT [UNSIGNED]` | signed/unsigned integer 32-bit |
| `BIGINT [UNSIGNED]` | signed/unsigned integer 64-bit |
| `DECIMAL(p,s)`，`p=1..65`、`s=0..30`、`s<=p` | Shared Kernel decimal |
| `FLOAT` / `DOUBLE` | float32 / float64 |
| `BIT(n)`，`n=1..64` | binary + bit width |
| `DATE` | date |
| `TIME(fsp)`，`fsp=0..6` | time |
| `DATETIME(fsp)`，`fsp=0..6` | datetime, no timezone |
| `TIMESTAMP(fsp)`，`fsp=0..6` | timestamp UTC |
| `CHAR(n)` / `VARCHAR(n)` / `TINYTEXT` / `TEXT` / `MEDIUMTEXT` / `LONGTEXT` | UTF-8 string |
| `BINARY(n)` / `VARBINARY(n)` / `TINYBLOB` / `BLOB` / `MEDIUMBLOB` / `LONGBLOB` | binary |
| `JSON` | UTF-8 string + logical JSON |
| `ENUM(label_list)` / `SET(label_list)` | ADR 0013 / Repository §10.1 |

规范化：`INTEGER → INT`；剥离 display width、`ZEROFILL`、列级 `CHARACTER SET` /
`COLLATE`。ENUM/SET 规范化后 `sql_type` 上限 64 KiB，与 Repository §10.1 一致。

YEAR、spatial、vector 和其它未列 type 为 unknown：可保留 bounded descriptor 与
diagnostic，**不**发布 READY reader。ENUM/SET 族内畸形一律 `SQL_TYPE_MALFORMED`，
非法值一律 `SQL_VALUE_ILLEGAL`，不得落入 unknown/stringify。

SQL `NULL` 保持独立状态。row 是与 descriptor 对齐的 immutable positional tuple。

## 7. XML security policy

R2 只提供 domain-neutral XML document boundary。`logics.xml` schema interpretation
和 `composite_signal_point` materialization 仍是 `R2-D04`。

- Provider：stdlib `xml.parsers.expat` incremental handler。不引入 `defusedxml`、
  `lxml` 或其它第三方 parser。
- 输入只接受严格 UTF-8；encoding 声明缺省视为 UTF-8，非 UTF-8 fail closed。
- 禁止 DOCTYPE、DTD、ENTITY、XInclude、external resource、network fetch。
- 输出 bounded event/node stream，不建立无上限通用 DOM。
- 保留 namespace-expanded name；不做业务 namespace alias 或字段解释。
- 超限、malformed、安全拒绝均 fail closed，丢弃 partial events，不发布 READY
  reader。

## 8. Resource budget table

既有 Source compressed ingress `256 MiB`、expanded SourcePackage `1 GiB` 是外层
边界，不是本表替代品。依据 large dataset evidence（311 表 / 246359 行）、MySQL
identifier 64 code points、ENUM/SET `sql_type` 64 KiB。

| Budget | Limit | Notes |
| --- | --- | --- |
| `max_sql_source_bytes` | 512 MiB | 解码后的 SQL document；位于 1 GiB expanded package 内 |
| `max_statement_bytes` | 16 MiB | 单条 CREATE/INSERT/boilerplate |
| `max_tables_per_source` | 2048 | 覆盖 311 表并留余量 |
| `max_columns_per_table` | 512 | |
| `max_identifier_code_points` | 64 | 与 Repository DDL identifier 门及 MySQL 对齐 |
| `max_rows_per_table` | 2_000_000 | streaming fail-closed；不是全表缓冲 |
| `max_rows_per_source` | 10_000_000 | |
| `max_field_bytes` | 4 MiB | 不得大于 statement 上限 |
| `max_insert_tuple_bytes` | 16 MiB | 单行 VALUES tuple |
| `max_reader_batch_rows` | 1024 | 实现内存界；不进入 semantic digest |
| `max_reader_batch_bytes` | 8 MiB | 同上 |
| `max_xml_document_bytes` | 64 MiB | generic XML；非业务 `logics.xml` 解释 |
| `max_xml_depth` | 64 | |
| `max_xml_nodes` | 1_000_000 | |
| `max_xml_attributes_per_element` | 256 | |
| `max_xml_attribute_bytes` | 64 KiB | |
| `max_xml_text_node_bytes` | 1 MiB | |
| `max_xml_expanded_name_bytes` | 1024 | |
| `max_diagnostics` | 1024 | 稳定排序后截断 |
| `max_diagnostic_message_bytes` | 4 KiB | |
| `max_diagnostics_total_bytes` | 256 KiB | |
| ENUM/SET normalized `sql_type` | 64 KiB | 沿用 Repository §10.1；不是新语义 |

超限产生稳定 `RESOURCE_LIMIT_EXCEEDED`（指明哪个 budget）。任何 resource / parse /
timeout / cancel 错误都禁止发布 READY reader；调用方必须丢弃 partial rows。
diagnostics 按 source offset/code 稳定排序；截断后追加
`PARSER_DIAGNOSTICS_TRUNCATED`。

## 9. Timeout and cancellation input shape

```text
ParserInvocationContext:
  cancel_requested: is_set() protocol    # in-process cooperative signal
  deadline_monotonic: float | None       # time.monotonic() seconds; None = no parser default timeout
```

- 在 statement 开始、INSERT tuple、XML node、diagnostic append 边界检查。
- 稳定码：`PARSER_CANCELLED`、`PARSER_TIMEOUT`。
- 上层决定具体 timeout policy，并把 HTTP/operation deadline 映射进本形状。
- R2 无 durable cancellation / checkpoint / takeover（`R2-D09`）。
- 固定时间预算测试必须 `@pytest.mark.serial`。

reader 仍是 single-consumer、non-rewind、可重新打开；`close()` 幂等；close 后访问
返回稳定 `READER_CLOSED`。successful end-of-stream 是发布提交点。

`ParseResult` 状态：`COMPLETE | PARTIAL | FAILED`。PARTIAL 只为成功表提供 reader；
FAILED 不发布可消费 reader。

## 10. Fixture naming and parameter-table ownership

Owner：`table_access`。S0 只冻结命名；最小 valid/invalid shape 由 S1 建立。

```text
vnext/fixtures/golden/table-access/sql/valid/<case_id>/
vnext/fixtures/golden/table-access/sql/malformed/<case_id>/
vnext/fixtures/golden/table-access/xml/valid/<case_id>/
vnext/fixtures/golden/table-access/xml/malformed/<case_id>/
vnext/fixtures/golden/table-access/xml/security/<case_id>/
vnext/fixtures/vectors/table-access/sql-known-types/v1/
vnext/fixtures/vectors/table-access/sql-identifier/v1/
vnext/fixtures/vectors/table-access/xml-security/v1/
vnext/backend/tests/test_table_access_*.py
vnext/backend/tests/support/table_access_*.py
```

同构错误使用模块级参数表，例如 `SQL_STATEMENT_REJECTS`、`SQL_TYPE_MALFORMED_SHAPES`、
`SQL_VALUE_ILLEGAL_SHAPES`、`XML_SECURITY_PAYLOADS`、`RESOURCE_LIMIT_CASES`。
不恢复 legacy compatibility matrix。不把
`vnext/fixtures/vectors/repository/sql-enum-set/v1/` 当作通用 corpus。纯 R2 tests
不创建 Dolt、不依赖永久 workspace path、不使用宽泛 skip。

## 11. Allowed and forbidden paths

S0 确认并登记最终 allowlist。相对 R2 execution plan §4，本步新增：

```text
docs/backend-vnext/refactoring/formal/plans/p3-r2-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
```

完整允许路径：

```text
vnext/backend/src/gateway_backend/capabilities/table_access/
vnext/backend/tests/test_table_access_*.py
vnext/backend/tests/support/table_access_*.py
vnext/fixtures/golden/table-access/
vnext/fixtures/vectors/table-access/
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/plans/p3-r2-table-access-parser-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r2-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md
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

S1 不得越出本 allowlist。再新增路径必须在后续 step handoff 登记。

S2 在已允许目录内新增并登记：

```text
vnext/backend/src/gateway_backend/capabilities/table_access/sql.py
vnext/backend/src/gateway_backend/capabilities/table_access/_parser_runtime.py
vnext/backend/src/gateway_backend/capabilities/table_access/_sql_scan.py
vnext/backend/src/gateway_backend/capabilities/table_access/_sql_statements.py
vnext/backend/src/gateway_backend/capabilities/table_access/_sql_types.py
vnext/backend/src/gateway_backend/capabilities/table_access/_sql_values.py
vnext/backend/src/gateway_backend/capabilities/table_access/_sql_reader.py
vnext/backend/tests/test_table_access_sql_*.py
vnext/backend/tests/support/table_access_sql.py
vnext/fixtures/golden/table-access/sql/valid/s2-*
vnext/fixtures/golden/table-access/sql/malformed/s2-*
vnext/fixtures/vectors/table-access/sql-known-types/v1/
vnext/fixtures/vectors/table-access/sql-identifier/v1/
```

S3 在已允许目录内新增并登记：

```text
vnext/backend/src/gateway_backend/capabilities/table_access/xml.py
vnext/backend/src/gateway_backend/capabilities/table_access/_xml_parser.py
vnext/backend/tests/test_table_access_xml_*.py
vnext/backend/tests/test_table_access_conformance.py
vnext/backend/tests/support/table_access_xml.py
vnext/fixtures/golden/table-access/xml/valid/s3-*
vnext/fixtures/golden/table-access/xml/malformed/s3-*
vnext/fixtures/golden/table-access/xml/security/s3-*
vnext/fixtures/vectors/table-access/xml-security/v1/
```

## 12. Reopen record

S0 正式 reopen/修订的 owning ADR：

| Item | Action | Scope |
| --- | --- | --- |
| ADR 0013 | 修订为 source dump grammar 与 repository import validation 双边界 | 不改变 ENUM/SET 值、Arrow、content encoding 或 import wire codes |

未 reopen：Repository Service §10 字段表、Shared Canonical Encoding、ADR 0012、
artifact envelope。未把 `repository-service.md` 扩写成 dump parser contract。

若后续发现下列情况，必须先 reopen owning contract/ADR，再改 S0/S1 记录：

- source parser 与 Repository import ownership 无法保持分离；
- SQL grammar/type mapping 与 accepted canonical/storage semantics 冲突；
- XML parser 可访问外部资源、构造无界 DOM 或绕过 UTF-8/budget 门禁；
- reader 在错误后允许 partial rows 伪装为 READY；
- 需要第三方 parser library 或 Rust parser；
- 需要提高本表 numeric budget 才能接纳已确认业务 fixture。

## 13. Deferred register impact

| ID | S0 status |
| --- | --- |
| `R2-D01` | **Closed in S0**；§8 budgets；S2/S3 必须做 boundary tests |
| `R2-D02` | **Closed in S0**；§5–§6 allowlist/type closure + ADR 0013 双边界 |
| `R2-D03` | **Closed in S0**；stdlib custom SQL scanner + `xml.parsers.expat`；无第三方 parser |
| `R2-D04`–`R2-D09` | 仍延后；不得从 S1 skeleton 推断为已实现 |

## 14. Verification record

S0 不宣称 parser conformance、R2 gate、container 或 production validation 已通过。
Container rebuild：**no**。理由：只改 formal docs，未触碰 image、deployment 或
container-only runtime boundary。Last verified image revision：none；source-tree
文档审查是本步权威 evidence。Container gate for current HEAD：`not-applicable`。

S0 执行时工作树仅 docs dirty（含既有未提交的 R2 detail plan 与本步 ADR/S0 记录）；
无 `vnext/` 代码变更。

| Command | Result |
| --- | --- |
| `git status --short` | **docs only**；无 `vnext/` 变更。tracked 修改 7 个 plan/ADR 文件；untracked `p3-r2-s0-entry-and-budget-freeze.md`、`p3-r2-table-access-parser-execution-plan.md` |
| `git diff --check` | **passed**（tracked）；untracked S0/R2 plan 文件 `--no-index` 同样无 whitespace error |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py` | **13 passed**（0.47s）；`table_access` 仍为 capability leaf |

```yaml
Current HEAD: 9e70e4bf6ae1341b4013a1a2d3ab9dd67b64b7bb
r1_validated_code_sha: fc5159576b30de5bd8c1428446537aa92a23642b
Container rebuild required: no
Reason: formal docs only; no image, deployment, or container-only runtime boundary
Last verified image revision: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: none
Required execution point: later R if an image/deployment/container boundary is introduced
```

建议 S1 首轮命令：

```text
cd vnext/backend
uv run pytest -m unit tests/test_architecture.py
uv run ruff check .
uv run mypy
git diff --check
```

## 15. S1 entry package

**Recommendation：S0 complete，允许进入 S1 public contract/skeleton；不得把本结论
表述为 R2 gate 通过或 parser 实现授权。**

S1 必须：

- 只在 §11 allowlist 内落成 `table_access/contracts.py` 及最小 public entrypoint；
- 不实现 parser algorithm、不引入第三方依赖、不创建 Dolt；
- 每个 type/field/code 有唯一 owner；
- 最小 valid/invalid fixture shape 使用 §10 命名；
- 证明 `table_access` 仍无 capability upstream。

S1 可与 S0 同一对话。本文件不自动授权 S2 SQL 实现。

## 16. S1 public contract skeleton record

S1 将 §5–§11 落成可导入的 `table_access` public types。不实现 SQL/XML parser
algorithm，不引入第三方依赖，不创建 Dolt。`p3_implementation_authorized` 仍为
`no`。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/table_access/contracts.py
vnext/backend/src/gateway_backend/capabilities/table_access/__init__.py
vnext/backend/tests/test_table_access_contracts.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/support/table_access_fixtures.py
vnext/fixtures/golden/table-access/
```

Public types live in `table_access/contracts.py` and are re-exported from the
package. `SourceTableDescriptor` is the R2 boundary name；R3 maps it to
materialization types. There is no parse function and no `NotImplementedError`
stub. `MaterializedTableReader` only proves reader lifecycle for fixtures/tests.

S1 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_table_access_contracts.py` | **29 passed**（0.36s） |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 57 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python contract/test/docs，未触碰 image/deployment
boundary。无 Dolt。`p3_implementation_authorized` 仍为 `no`。

S2 必须严格执行 §5 grammar 与 §8 budgets；不得从本 skeleton 猜测未冻结语义。

## 17. S2 SQL parser record

S2 实现 bounded SQL scanner、known-type 映射和 deferred `SqlTableReader`。XML parser
仍未实现。`p3_implementation_authorized` 为 `s2_sql_only`，不授权 S3。

Public entry：`parse_sql(SqlParseRequest, *, budgets=RESOURCE_BUDGETS) -> ParseResult`。
生产路径使用默认 budgets；测试可传入缩小后的 `ResourceBudgets` 证明 resource 边界。

S2 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_table_access_contracts.py tests/test_table_access_sql_parser.py tests/test_table_access_sql_types.py tests/test_table_access_sql_rejects.py tests/test_table_access_sql_reader.py tests/test_table_access_sql_limits.py` | **98 passed** |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 70 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python parser/test/docs，未触碰 image/deployment
boundary。无 Dolt。S3 XML 仍待实现。

## 18. S3 XML parser record

S3 实现 bounded XML event parser、fail-closed 安全拒绝，以及 SQL/XML 共享
diagnostic/cancel/timeout/oracle conformance。不实现 `logics.xml` 业务 materializer。
`p3_implementation_authorized` 为 `s2_s3`，不进入 S4 审查。

Public entry：`parse_xml(XmlParseRequest, *, budgets=RESOURCE_BUDGETS) -> XmlParseResult`。
成功才发布 `COMPLETE` events；错误/cancel/timeout 为 `FAILED` 且 `events` 为空。

S3 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_table_access_contracts.py tests/test_table_access_sql_*.py tests/test_table_access_xml_*.py tests/test_table_access_conformance.py` | **142 passed**（0.50s） |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 77 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python parser/test/docs，未触碰 image/deployment
boundary。无 Dolt。不进入 S4。

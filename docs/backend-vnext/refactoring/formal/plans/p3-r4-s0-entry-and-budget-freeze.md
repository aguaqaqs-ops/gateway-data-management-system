# P3-R4-S0 Entry, Applicability, Legacy Matrix and Budget Freeze

状态：S0 complete；S1 complete；S2 complete；S3 complete；S4 complete；S5 complete；S6 complete；S7 complete；S8 module gate complete，R4 gate pass；implementation authorization pending

日期：2026-08-20

Owner：Backend vNext Table Rules / Storage Projection

本文是 P3-R4 的 **S0 权威记录**。它证明 R3 handoff 是有效输入，冻结完整 legacy
规则矩阵、ignored-column → storage 派生顺序、selector 优先级与冲突策略、ruleset
identity、role-to-storage 映射、resource budgets、fixture 根目录、allowlist 与
reopen 条件。字段级 public contract 由 S1 落成；legacy parity resolver、projection
算法、digest 与 artifact publish 由 S2–S5 实现。不得从 R3 skeleton、identity-projection
helper 或 capability 文档中的 Preview/Submit 名称猜测 R4 语义。

上级计划：[P3-R4 Storage Projection Execution Plan](p3-r4-storage-projection-execution-plan.md)
设计基线：[P3-R4 Storage Projection Design Baseline](p3-r4-storage-projection-design.md)
R4 gate / R5 entry：[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)
R3 入口：[P3-R3 Source Materialization and Snapshot Handoff](p3-r3-source-materialization-handoff.md)
R3 冻结：[P3-R3-S0 Entry, Applicability and Budget Freeze](p3-r3-s0-entry-and-budget-freeze.md)

```yaml
handoff_kind: p3_r4_s0_entry_and_budget_freeze
round: P3-R4-S0
p3_r3_exit: pass
p3_r4_ready: yes
p3_r4_s0_exit: pass
p3_r4_s1_authorized: yes
p3_r4_s1_exit: pass
p3_r4_s2: completed
p3_r4_s2_exit: pass
p3_r4_s3: completed
p3_r4_s3_exit: pass
p3_r4_s4: completed
p3_r4_s4_exit: pass
p3_r4_s5: completed
p3_r4_s5_exit: pass
p3_r4_s6: completed
p3_r4_s6_exit: pass
p3_r4_s7: completed
p3_r4_s7_exit: pass
p3_r4_s8: completed
p3_r4_s8_exit: pass
p3_r4_exit: pass
p3_r5_ready: yes
p3_implementation_authorized: no
r3_validated_code_sha: 7989e47d08c48fda46e7d8b6b3550ef9ee266d92
r3_handoff_documentation_sha: f07c387f513ee735fe69e65c94804d7c63115f0d
s0_worktree: dirty_docs_only
container_rebuild: no
benchmark: not_applicable
ruleset_id: backend-vnext/table-ruleset
ruleset_version: v2
table_ruleset_contract_version: gateway-vnext.table-ruleset:v1
storage_projection_version: "1"
canonicalization_manifest_contract: "3.0.0"
```

`r3_validated_code_sha` 是 R3-S6/S7 已审且 S8 复跑通过的代码 tip。
`r3_handoff_documentation_sha` 是当前 HEAD 上的 R3-S8 handoff 文档 commit。S0
开始时工作树已有未提交的 R4 design/detail plan 与相关 formal docs，无 `vnext/`
业务代码变更。本文件和 plan/index 状态更新是本次 S0 文档交付。

## 1. Review boundary and evidence

本审查按照 [P3-R4 execution plan](p3-r4-storage-projection-execution-plan.md) S0
只读范围执行。语义 authority 依次采用 P3 contracts/ADR、R4 design baseline、R3
handoff 与 R3-S0 freeze，再采用 legacy `TableRuleRegistry` 作为 **read-only oracle**，
最后用现有 architecture/import tests 作为边界 evidence。legacy 与过程文档不作为当前
contract。capability 文档中的 upload/preview/submit helper 名称不授权 HTTP 或
application flow。

已读取并用于本结论的 authority：

- [P3-R3 Source Materialization and Snapshot Handoff](p3-r3-source-materialization-handoff.md)；
- [P3-R3-S0](p3-r3-s0-entry-and-budget-freeze.md)、
  [P3-R3-S6](p3-r3-s6-focused-review.md)、
  [P3-R3-S7](p3-r3-s7-independent-review.md)；
- [P3-R4 Storage Projection Design Baseline](p3-r4-storage-projection-design.md)；
- [P3 Capability Foundation Design §4.3](p3-capability-foundation-design.md#43-p3-r4-storage-projection-design-baseline)；
- [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)；
- [Ruleset Activation and Migration](../contracts/ruleset-activation-and-migration.md)；
- [Shared Canonical Encoding](../contracts/shared-canonical-encoding.md)；
- [ADR 0004](../adr/0004-raw-source-artifact-and-canonical-dolt-storage.md)、
  [ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)、
  [ADR 0013](../adr/0013-enum-set-v1-import-semantics.md)、
  [ADR 0015](../adr/0015-ruleset-activation-and-migration.md)；
- [Testing Conventions](../../../testing-conventions.md)、[Testing Fixtures](../../../testing-fixtures.md)；
- legacy oracle：
  `legacy/backend_vnext/capabilities/table_rules/{models,semantic,registry}.py`、
  `legacy/backend_vnext/capabilities/comparison/ruleset_registry.py`、
  `legacy/backend_vnext/capabilities/snapshot_materialization/{rules,canonical_storage}.py`、
  `legacy/backend_vnext/capabilities/repository_import/canonical_storage.py`；
- `vnext/backend/src/gateway_backend/capabilities/{table_rules,storage_projection,snapshot_materialization}/`、
  `vnext/backend/src/gateway_backend/canonicalization_{cells,manifest}.py`、
  `vnext/backend/src/gateway_backend/repository_import_artifact.py`、
  `vnext/backend/tests/test_architecture.py`。

本次没有修改业务代码、fixture 文件、artifact schema 或正式 contract/ADR。S0 不
reopen ADR 0004、0012、0013、0015。

## 2. R3 handoff applicability

| P3-R4 entry requirement | Evidence | Result |
| --- | --- | --- |
| R3 module gate pass | handoff `p3_r3_exit: pass`；`p3_r4_ready: yes` | **PASS** |
| stable public Snapshot/Artifact | `Snapshot` / `SnapshotTableArtifact` / `SnapshotTableReader` / four-field `ArtifactRef`；handoff §7 | **PASS** |
| consume public contracts only | 禁止 import `_digest` / `_parquet` / `_reader` / `_catalog` / `_ruleset` / `scalar_encoding` | **PASS** |
| COMPLETE/PARTIAL/FAILED 与原子 publish | R3 handoff §7–§8；失败表无 partial reader | **PASS** |
| digest ownership split | R3 拥有 raw/business/`snapshot_digest`；storage projection 仍是 `R3-D04` | **PASS** |
| `COMMIT_VALIDATED` 不可自提升 | R3-S0-D06；handoff §8 | **PASS** |
| no Repository/HTTP/application in R3 capabilities | architecture forbidden prefixes；handoff §4 / §10 | **PASS** |
| `R3-D01`–`R3-D07` explicitly linked | handoff §5；`R3-D04` 由本轮接管 | **PASS** |
| no-open-blocker | handoff §5；S6/S7 无未处理 P1/P2 | **PASS** |
| R3 未授权 storage projection | `p3_implementation_authorized: no` 保持 | **PASS** |
| R4 skeleton 未预声明字段 | `storage_projection/contracts.py` 仅 owner 注释；`table_rules` 仍是 R3 最小注入面 | **PASS** |

R3 可作为 R4 输入。S0 不把 identity-projection helper、R1 skeleton 或 capability
文档中的 Preview/Submit helper 当作已实现合同。无 blocking finding 要求暂停 R4
entry。

当前代码面（不阻塞 S0）：

- `table_rules` 公开三项：`TABLE_RULESET_VERSION = 1`、`TableCompareKey`、
  `TableRulesetSnapshot(table_ruleset_version, compare_keys=())`。
- `storage_projection` 包已注册于 architecture DAG，contracts 为空骨架。
- 根模块 `canonicalization_*` / `repository_import_artifact` 实现 identity-projection，
  且 capability 禁止导入它们。

## 3. Owner graph

目标 DAG（S1 扩展 public contracts；当前 architecture 已登记边，尚未落字段）：

```text
Shared Canonical Encoding (Shared Kernel)
  ^
  | public identifier ASCII fold / scalar / null / DigestRef
  |
artifacts envelope (not a capability owner)
  |-- four-field ArtifactRef; no host path; raw transport integrity only
  `-- ArtifactStorePort; LocalArtifactStore stays in infrastructure

table_access (R2 leaf)                 -- R4 does not import
source_package_staging (R3 leaf)       -- R4 does not import
composite_signal (R3)                  -- R4 does not import

table_rules (leaf)
  |-- additive immutable TableRulesetSnapshot identity
  |-- LegacyRuleDecision (parity / comparison provenance)
  `-- StorageRuleView derivation (canonical storage authority)

snapshot_materialization (R3)
  |-- Snapshot / SnapshotTableArtifact / SnapshotTableReader (contracts.py)
  `-- R4 consumes bound public types only; not artifact.py / private modules

storage_projection (R4 consumer/composer)
  |-- canonical key/schema/column policy and row integrity
  |-- canonical schema/content/ordering/storage/manifest digests
  |-- CanonicalizationManifest producer
  `-- RepositoryImportArtifactInput structural package input
```

Allowed capability edges after S1（与现有 `test_architecture.py` 一致，不得改方向）：

```text
table_rules: frozenset()
storage_projection: frozenset({"table_rules", "snapshot_materialization"})
snapshot_materialization: frozenset({
    "table_access",
    "table_rules",
    "source_package_staging",
    "composite_signal",
})
```

跨 capability 只允许 `*.contracts`。capability 可 import `gateway_backend.artifacts`
与 `gateway_shared_kernel` public primitives。production capability 代码不得 import
`gateway_backend.infrastructure`。

Forbidden directions:

```text
table_rules -X-> storage_projection / snapshot_materialization
storage_projection -X-> snapshot_materialization private modules
storage_projection -X-> snapshot_materialization.artifact (open/publish helpers)
storage_projection -X-> gateway_backend.canonicalization_cells
storage_projection -X-> gateway_backend.canonicalization_manifest
storage_projection -X-> gateway_backend.repository_import_artifact
any R4 owner -X-> gateway_repository_service / candidate_a.sql / dolt
any R4 owner -X-> HTTP / Workspace / Submit / Operation Runtime
any R4 owner -X-> comparison / risk / surface / bundle / mutation implementation
any R4 owner -X-> capabilities/common / capabilities/utils
any R4 owner -X-> infrastructure.LocalArtifactStore
any R4 owner -X-> legacy / backend_vnext production imports
```

`ProjectionRequest` 携带已绑定的 public `SnapshotTableReader` / `SnapshotTableArtifact`
类型。编排层（`tests/support` 或未来 application）可调用
`open_snapshot_table_artifact`；production `storage_projection` 不得 import 该 helper。

不得创建 `capabilities/common` 或 `capabilities/utils`。

## 4. Decision register

| ID | Decision | Rationale |
| --- | --- | --- |
| `R4-S0-D01` | R3 public Snapshot/Artifact/reader 是 R4 唯一表输入；不 import R3 private 模块 | R3 handoff §7 / §9；关闭“入口未就绪”歧义 |
| `R4-S0-D02` | PARTIAL、provisional-only、missing、mismatched 或 corrupt closure fail-closed；R4 不发布 partial Repository import | design §7；执行计划 frozen invariants |
| `R4-S0-D03` | 根 `canonicalization_*` / `repository_import_artifact` 是 candidate assets，不是第二 owner。现有实现是 identity-projection（`gateway-vnext.identity-sql-dump`），不是 migrated table-ruleset。R4 public 类型与算法落在 `storage_projection/`（及 `table_rules/`）。S1/S4/S5 可将 cell encoding、JCS manifest prefix 与两入口 package writer 迁入 capability；根模块可改为 thin re-export 供既有测试/R6 脚本。未分类表走 raw-PK fallback，禁止静默退回 identity ruleset | architecture `FORBIDDEN_IMPORT_PREFIXES`；Canonical Storage §4 |
| `R4-S0-D04` | 双层规则：`LegacyRuleDecision` 保留 selector/role/key/ignored/scope/position/stable keys 做 parity；`StorageRuleView` 才是 canonical 列/key/ordered 权威 | design §4 |
| `R4-S0-D05` | ignored → storage 派生顺序见 §5。IEC104 `no` 为 `RETAIN_FOR_STRUCTURE`，不是 DROP，也不是 matrix blocker。ignored key/`gid`/其它 required structural 冲突 fail-closed。不复制 legacy comparison 的 ignored-key 降级 | Canonical Storage §2–§3；design §4.2 / §5.3 |
| `R4-S0-D06` | Runtime oracle 是 `classify_static_role` / `key_rule_for_table`。优先级 SKIP > SNAPSHOT_ONLY > BROWSE_ONLY > ORDERED_DIFF > STANDARD_DIFF。不兼容重叠 fail-closed；禁止插入序静默决胜。不采用 comparison planner first-match 或有损 `table_rule_definitions()` 作为 production resolver | legacy `registry.py`；执行计划 §5 / S2 |
| `R4-S0-D07` | 双 identity 不合并：R3 注入整数 `TABLE_RULESET_VERSION = 1` 只允许 additive 扩展；R4 业务 `ruleset_id=backend-vnext/table-ruleset`、`ruleset_version=v2`、`contract_version=gateway-vnext.table-ruleset:v1`、`storage_projection_version=1`。不采用 comparison snapshot 的 `default`/`v1` | design §3.3；R3-S0-D08 |
| `R4-S0-D08` | Storage ordered policy 是 `gid_no_v1`：real `1..3_999_999_999`，pseudo `4_000_000_000..4_294_967_295`，`0` forbidden。Legacy `pseudo_key_start=2_000_000_000` 只留在 LegacyRuleDecision 供 R5。Keyless 仅显式规则；raw-PK 空 key 不是 keyless | ADR 0004；Canonical Storage §3 |
| `R4-S0-D09` | `version_manager` 是 BROWSE_ONLY exact，不是 SKIP。canonical 表保留。identity assessor 排除列 `no` 不是 table-rules ignored，R4 不据此 DROP | legacy registry + materializer special-case |
| `R4-S0-D10` | `UPDATE_ONLY` 只抑制 comparison INSERT/DELETE records，不删列、不改 snapshot 保留 | design §4.3；Canonical Storage §2 |
| `R4-S0-D11` | 源表行/列/字段预算继承 R2-S0 / `table_access.RESOURCE_BUDGETS`，不复制第二份 parser 表。Repository `manifest.json` 16 MiB 与 `replay.sql` 200 MiB 是上游上限；R4 发布前拒绝超限。无吞吐 SLO | 执行计划 S0 item 6 |
| `R4-S0-D12` | Manifest digest 保持 `RFC8785-JCS + gateway-vnext:canonicalization-manifest:v1\0 + SHA-256`；`CONTRACT_VERSION=3.0.0`；`STORAGE_PROJECTION_VERSION=1`。不另开 v2 digest | Canonical Storage §4 |
| `R4-S0-D13` | SNAPSHOT_ONLY / BROWSE_ONLY 无 Legacy key rule；StorageRuleView 在表保留时用 DDL PK（列均 retained 且有效）；缺 PK 是 typed fail-closed，不是隐式 keyless | design §5.2 |
| `R4-S0-D14` | 生产入口禁止 hidden mutable global registry。R4 projection 要求完整 ruleset identity + matching `storage_projection_version`。R3-only 注入可缺 `ruleset_digest`，但 S1 扩展必须 additive，不得破坏 `TableRulesetSnapshot(table_ruleset_version=1)` | R3-S0-D08；现有 R3 测试构造 |

无 S0 blocking finding。不新增 shared primitive。不 reopen ADR。

## 5. Two-layer mapping and ignored-column derivation

### 5.1 Views

`LegacyRuleDecision` 可含 storage 不使用的字段，供 parity 与下游 comparison：

```text
selector
static_role
compare_key_mode
compare_key_columns
ignored_columns
artifact_scope
position_column
stable_key_candidates
pseudo_key_start          # comparison-only; not a storage gid domain
```

`StorageRuleView` 是 canonical 权威：

```text
canonical_table
storage_policy: PERSIST_BUSINESS | RETAIN_FOR_STRUCTURE | DROP_FROM_STORAGE
canonical_key: explicit | ddl_primary_key | explicit_keyless
ordered_policy: none | gid_no_v1
retained_columns: DDL-order tuple
structural_columns: DDL-order tuple
dropped_columns: tuple(name, reason)
storage_rule_digest
```

SKIP 表不产生 StorageRuleView 行：source snapshot 与 canonical storage 均省略。

### 5.2 Derivation order

每个 resolved rule 按以下顺序派生，S1/S2/S3 不得改写：

```text
1. classify static role and effective selector after §6 precedence
2. classify ordered_policy / position_column / canonical key
3. if ordered_policy = gid_no_v1 and position_column = no:
     map no -> RETAIN_FOR_STRUCTURE
     do not emit DROP_FROM_STORAGE for this column
4. remaining legacy ignored_columns -> DROP_FROM_STORAGE
     reason = legacy_ignored_column:<selector>
5. if any DROP column is in the effective key, ordered identity (gid),
   or another required structural column:
     fail ruleset validation (never silently retain or degrade to empty key)
6. every non-ignored, non-structural source column defaults to PERSIST_BUSINESS
7. UPDATE_ONLY remains artifact/comparison scope and does not drop columns
```

当前 frozen matrix 在步骤 5 **没有** blocker 行。IEC104 九族的 `no` 在步骤 3
已转为 `RETAIN_FOR_STRUCTURE`。`composite_signal_point` 五列与
`net_cfg`/`com_cfg`/`scdmod_para` 的 `no` 均非 key。`rdb_cfg.no` 与 protocol option
`(page_no, no)` 不是 ignored。

Legacy comparison 若 key 落在 ignored 集会返回空 key。R4 **不复制**该行为。

列名一律 `canonical_identifier`（strip、去成对引号、lower）。matrix 中的 `NO`
已规范为 `no`。

### 5.3 Role to storage

| Legacy role | Source Snapshot | Canonical storage | Comparison meaning |
| --- | --- | --- | --- |
| SKIP | omitted，`version_manager` 除外（它不是 SKIP） | omitted | no comparison |
| SNAPSHOT_ONLY | retained | retained；非 ignored 默认 `PERSIST_BUSINESS`；key = DDL PK 或 fail-closed | no comparison records |
| BROWSE_ONLY | retained | retained；含 `version_manager`；key = DDL PK 或 fail-closed | presence/browse facts only |
| STANDARD_DIFF | retained | keyed projection；ignored → DROP（§5.2） | normal comparison；`UPDATE_ONLY` 只限 artifact |
| ORDERED_DIFF | retained | ordered projection；`no` = `RETAIN_FOR_STRUCTURE` | ordered comparison |

## 6. Selector precedence and conflict policy

### 6.1 Runtime oracle

权威实现是
`legacy/backend_vnext/capabilities/table_rules/registry.py` 的
`classify_static_role` / `key_rule_for_table`。`table_rule_definitions()` 与
comparison `TableRulesetSnapshot` 是有损导出：缺少 fallback 行、ordered 的
gid/no/ignored/position、`device_cfg` 的 PK 与 `compare_key_mode`。Parity oracle
不得只用 definitions。

Role 优先级是显式 if 链，不是 dict 插入序：

```text
SKIP > SNAPSHOT_ONLY > BROWSE_ONLY > ORDERED_DIFF > STANDARD_DIFF
```

Exact 匹配使用 `canonical_identifier(table_name)`。Regex 使用
`re.compile(pattern, re.IGNORECASE).search(table_name)`；当前 pattern 均带 `^$`。
Protocol option/device 在 STANDARD 路径上对 **原始** `table_name` 做 `fullmatch`
（IGNORECASE）。

STANDARD 内解析顺序：

```text
exact dict lookup
  -> device_cfg special case (RAW_PRIMARY_KEY + UPDATE_ONLY)
  -> protocol option fullmatch
  -> protocol device fullmatch
  -> RAW_PRIMARY_KEY fallback using caller DDL PK
```

ORDERED 命中后返回共享 `_ordered_rule`，不再走 STANDARD。

### 6.2 Conflict policy

- 保持 §6.1 优先级。
- 一张表在优先级与冲突校验后至多一个有效 selector。
- 不兼容重复或重叠规则（同一表可匹配多个 selector 且 outcome 不一致）在
  ruleset validation 失败；resolver 不得用插入序、dict 序或 list first-match
  静默决胜。
- 当前 hardcoded 集合 **无跨角色重叠**。已核对：
  - `pointref_forwardtbl` 不匹配 `^forwardtable_.*$`；
  - `scdmod_para` 不在 SKIP `scdmod_*` 列表；
  - `device_model_table`（SKIP）≠ `device_model_cfg`（BROWSE_ONLY）；
  - IEC104 `_list` 与 protocol `_cfg` / `_dev_cfg` 不重叠；
  - `device_cfg` 无 `bN_nN_` 前缀，不匹配 protocol device。
- S2 必须用显式 overlap/collision 参数表钉死 fail-closed，而不是复制
  comparison planner 的 list first-match。

## 7. Complete legacy matrix

列含义：

| Column | Meaning |
| --- | --- |
| selector | exact name or regex |
| type | `exact` / `regex` / `fallback` |
| prec | 1 SKIP … 5 STANDARD；5b/5c/5d 为 STANDARD 内顺序 |
| role | static role |
| key mode | LegacyRuleDecision compare key mode；`—` = no key rule |
| key cols | canonical names |
| ignored | canonical names in LegacyRuleDecision |
| scope | artifact scope；`—` = unused at runtime |
| pos / stable | position column / stable key candidates |
| storage | table/column policy after §5.2 |
| storage key | canonical key policy |
| ordered | `none` / `gid_no_v1` |
| owner | legacy source |
| consumer | R4 consumer；comparison 细节 = `R4-D08` |
| fixture | S0 状态；实现后由对应 step 更新 |
| migration | migrated storage treatment |
| step | earliest implementation step |
| reopen | guard before changing this row |

所有行的 `source owner` 运行时均为 `TableRuleRegistry`；下表 owner 列指向常量或
规则对象。Consumer 默认 `storage_projection`；SKIP 的 comparison consumer 延后
`R4-D08`。

### 7.1 SKIP exact names（prec 1）

八个精确名。key/ignored/scope/pos/stable 皆空。storage = **table omitted**。
ordered = none。fixture = `pending_s2`。migration = `migrated_omit`。step = S2。
reopen = undocumented SKIP exception or retaining a SKIP table in canonical
storage。

| selector | type | owner |
| --- | --- | --- |
| `device_model_table` | exact | `DEFAULT_SKIPPED_TABLE_NAMES` |
| `scdmod_fcda` | exact | same |
| `scdmod_yk` | exact | same |
| `scdmod_dataset` | exact | same |
| `scdmod_rpt` | exact | same |
| `scdmod_ld` | exact | same |
| `scdmod_log` | exact | same |
| `scdmod_sgcb` | exact | same |

### 7.2 SNAPSHOT_ONLY pattern（prec 2）

| selector | type | role | key mode | ignored | storage | storage key | ordered | owner | fixture | step | reopen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `^forwardtable_.*$` | regex | SNAPSHOT_ONLY | — | {} | retain；all `PERSIST_BUSINESS` | DDL PK or fail-closed | none | `DEFAULT_SNAPSHOT_ONLY_TABLE_PATTERNS` | `pending_s2` | S2 | treating `pointref_forwardtbl` as snapshot-only |

migration = `migrated_retain`。

### 7.3 BROWSE_ONLY exact names（prec 3）

十三精确名。key mode —；ignored {}；scope unused；storage = retain；all
`PERSIST_BUSINESS`；storage key = DDL PK or fail-closed；ordered = none。
fixture = `pending_s2`。migration = `migrated_retain`。step = S2。owner =
`DEFAULT_BROWSE_ONLY_TABLE_NAMES`。拼写保持遗留 `praser`。

| selector | reopen |
| --- | --- |
| `version_manager` | treating as SKIP, dropping identity `no`, or omitting canonical table |
| `device_model_cfg` | undocumented browse exception |
| `board_cfg` | same |
| `dev_grp` | same |
| `dev_list` | same |
| `model_grp` | same |
| `primary_equipment_object_cfg` | same |
| `prot_list` | same |
| `prot_right` | same |
| `project` | same |
| `rule_61850dev_praser_cfg` | same |
| `rule_61850dev_praser_default_cfg` | same |
| `rule_61850point_praser_cfg` | same |

`version_manager` 额外硬编码（registry 之外，S0 单列，不另开 SKIP 行）：

1. parse 路径永不 skip INSERT；
2. 禁止 provisional FAST alias；
3. project identity assessor 读 canonical 表并排除列 `no`——**不是**
   `ignored_columns`，R4 不 DROP。

### 7.4 IEC104 ORDERED families（prec 4）

九个 regex 共享 `_ordered_rule`：

```text
key mode     = ORDERED_STABLE_KEY
key cols     = (gid,)
ignored      = {no}          # LegacyRuleDecision / comparison value-ignore
scope        = ORDERED_SEMANTIC
pos          = no
stable       = (gid,)
legacy pseudo_key_start = 2_000_000_000   # comparison-only
storage      = retain; no = RETAIN_FOR_STRUCTURE; other non-ignored = PERSIST_BUSINESS
storage key  = explicit (gid,)
ordered      = gid_no_v1
fixture      = pending_s2 (parity) / pending_s4 (gid/no projection)
migration    = migrated_ordered
step         = S2 then S4
reopen       = DROP no, change gid domain, or treat as blocker
```

| selector | type |
| --- | --- |
| `^b\d+_n\d+_iec104_syx_list$` | regex |
| `^b\d+_n\d+_iec104_dyx_list$` | regex |
| `^b\d+_n\d+_iec104_yc_list$` | regex |
| `^b\d+_n\d+_iec104_syk_list$` | regex |
| `^b\d+_n\d+_iec104_dyk_list$` | regex |
| `^b\d+_n\d+_iec104_yt_list$` | regex |
| `^b\d+_n\d+_iec104_ym_list$` | regex |
| `^b\d+_n\d+_iec104_sc_list$` | regex |
| `^b\d+_n\d+_iec104_yp_list$` | regex |

源：`IEC104_ORDERED_FAMILIES` 编译为 `rf"^b\d+_n\d+_{re.escape(family)}$"`。

### 7.5 Explicit STANDARD rules（prec 5）

owner = `_standard_rules_by_table_name`。lookup 不依赖插入序。ordered = none。
step = S2（parity）+ S3（projection）。fixture = `pending_s2` / `pending_s3`。

| selector | type | key mode | key cols | ignored | scope | storage | storage key | migration | reopen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `composite_signal_point` | exact | EXPLICIT_KEY | `(source_table, point_gid)` | `{dev_addr, device_gid, point_name, point_payload_json, formula_ast_json}` | ALL_CHANGES | five ignored DROP `legacy_ignored_column:composite_signal_point`；其余 PERSIST | explicit | `migrated_drop_ignored` | retaining an ignored column |
| `net_cfg` | exact | EXPLICIT_KEY | `(board, link_no)` | `{no}` | ALL_CHANGES | `no` DROP `legacy_ignored_column:net_cfg` | explicit | same | dropping a key column |
| `com_cfg` | exact | EXPLICIT_KEY | `(index,)` | `{no}` | ALL_CHANGES | `no` DROP `legacy_ignored_column:com_cfg` | explicit | same | same |
| `pointref_forwardtbl` | exact | EXPLICIT_KEY | `(refname,)` | {} | ALL_CHANGES | all PERSIST | explicit | `migrated_retain` | merging with `forwardtable_*` |
| `scdmod_para` | exact | EXPLICIT_KEY | `(ied_model,)` | `{no}` | ALL_CHANGES | `no` DROP `legacy_ignored_column:scdmod_para` | explicit | `migrated_drop_ignored` | merging with SKIP `scdmod_*` |
| `app_cfg` | exact | EXPLICIT_KEY | `(app_name,)` | {} | ALL_CHANGES | all PERSIST | explicit | `migrated_retain` | inventing drops |
| `rdb_cfg` | exact | EXPLICIT_KEY | `(no,)` | {} | ALL_CHANGES | `no` is key，禁 DROP | explicit | `migrated_retain` | treating `no` as ignored |

### 7.6 Device point UPDATE_ONLY（prec 5）

十张 exact STANDARD_DIFF。key mode = EXPLICIT_KEY；key = `(gid,)`；ignored {}；
scope = **UPDATE_ONLY**；pos/stable 空；storage = all PERSIST（不删列）；
storage key = explicit `(gid,)`；ordered = none；owner = dict 展开
`DEVICE_POINT_UPDATE_ONLY_TABLE_NAMES`；fixture = `pending_s2`；migration =
`migrated_update_only_scope`；step = S2；reopen = inferring storage drop from
UPDATE_ONLY。

| selector |
| --- |
| `device_st` |
| `device_mx` |
| `device_co` |
| `device_sg` |
| `device_sp` |
| `device_cnt` |
| `device_sn` |
| `device_tap` |
| `device_other` |
| `device_disturb` |

### 7.7 `device_cfg` special case（prec 5）

不在 exact dict。runtime：`RAW_PRIMARY_KEY`，key cols = 调用方 DDL PK，ignored
{}，scope = **UPDATE_ONLY**。storage = all PERSIST；storage key = `ddl_primary_key`；
缺 PK fail-closed（不是 keyless）。owner = `key_rule_for_table` 特判。fixture =
`pending_s2`。migration = `migrated_update_only_scope`。step = S2。reopen =
hardcoding a non-DDL key or dropping columns。

### 7.8 Protocol option and device patterns（prec 5b / 5c）

Segments：`iec104`, `iec61850c`, `nr103d`, `dev103`, `dev104`, `nbridge`。
ignored {}；scope ALL_CHANGES；ordered none；fixture `pending_s2`；migration
`migrated_retain`；step S2。

| selector | prec | key mode | key cols | storage key | owner | reopen |
| --- | --- | --- | --- | --- | --- | --- |
| `^b\d+_n\d+_(?:iec104\|iec61850c\|nr103d\|dev103\|dev104\|nbridge)_cfg$` | 5b | EXPLICIT_KEY | `(page_no, no)` | explicit；`no` 是 key 禁 DROP | `_protocol_option_cfg_rule` | treating option `no` as ordered ignored |
| `^b\d+_n\d+_(?:iec104\|iec61850c\|nr103d\|dev103\|dev104\|nbridge)_dev_cfg$` | 5c | EXPLICIT_KEY | `(gid,)` | explicit | `_protocol_device_cfg_rule` | overlapping with IEC104 `_list` |

### 7.9 Raw-primary-key fallback（prec 5d）

任何未命中 7.5–7.8 的 STANDARD_DIFF 表：

| selector | type | key mode | key cols | ignored | scope | storage | storage key | ordered | owner | fixture | migration | step | reopen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `<any other STANDARD_DIFF>` | fallback | RAW_PRIMARY_KEY | DDL PK | {} | ALL_CHANGES | all PERSIST | `ddl_primary_key`；empty PK fail-closed，不是 keyless | none | `key_rule_for_table` else | `pending_s2` | `migrated_ddl_pk` | S2 | implicit keyless, identity-projection fallback, or last-write-wins |

该行 **不在** `table_rule_definitions()` 中。S2 parity 必须覆盖未知表名。

### 7.10 Inventory completeness

| Required inventory item | Matrix location | Unresolved? |
| --- | --- | --- |
| eight skipped exact names | §7.1 | no |
| forwardtable snapshot-only pattern | §7.2 | no |
| browse-only exact names | §7.3 | no |
| nine IEC104 ordered families | §7.4 | no；`no` mapping frozen in §5.2 |
| explicit standard rules | §7.5 | no |
| device point update-only rules | §7.6 | no |
| `device_cfg` | §7.7 | no |
| protocol option/device patterns | §7.8 | no |
| raw-primary-key fallback | §7.9 | no |
| `version_manager` exception | §7.3 + §4 `R4-S0-D09` | no |

无 unclassified legacy baseline row。无 matrix blocker 行。

## 8. Ruleset identity and digest input shape

冻结字符串（canonical matrix 审查后）：

```text
ruleset_id       = backend-vnext/table-ruleset
ruleset_version  = v2
contract_version = gateway-vnext.table-ruleset:v1
storage_projection_version = 1
canonicalization_manifest CONTRACT_VERSION = 3.0.0
```

R3 注入整数保持独立：

```text
TABLE_RULESET_VERSION = 1    # table_ruleset_version matching; additive only
```

`ruleset_digest` 输入形状（S1 钉 canonical bytes；本步冻结包含/排除）：

```text
include:
  selector order and precedence class
  selector type and pattern/name
  static role
  compare key mode and canonical key columns
  ignored columns (legacy view)
  artifact scope, position_column, stable_key_candidates
  storage derivation outcome (policy, canonical key, ordered policy, drop reasons)
  storage_projection_version
  contract_version
exclude:
  provider name
  Python module path
  generated code identity
  host path
  thread count
  package compression metadata
  source row order
  legacy comparison snapshot id "default" / version "v1"
  legacy pseudo_key_start (comparison-only; not storage identity)
```

算法：SHA-256 of the canonical ruleset document；S1 选择 JCS 或与 Shared Canonical
Encoding 一致的确定性序列化。R4 projection 入口要求 snapshot 同时匹配
`ruleset_id` / `ruleset_version` / `ruleset_digest` / `storage_projection_version`。
后续 activation 不能改变已捕获 snapshot。drop/restore 或 canonical key 变更是
`STORAGE_BREAKING` / `MIGRATION_REQUIRED`（ADR 0015）；R4 只记录分类，不实现
executor。

## 9. Resource budgets

R4 不宣称 numeric throughput 或 SLO。SQL/XML/table/row/field/diagnostic 上限的
权威是 [R2-S0 §8](p3-r2-s0-entry-and-budget-freeze.md#8-resource-budget-table) 与
`table_access.RESOURCE_BUDGETS`；本步不修订、不复制为第二份 parser 表。Canonical
manifest 与 projected rows 受源/表预算约束。

| Budget | Limit | Owner/evidence |
| --- | ---: | --- |
| source table/row/field/column | R2 frozen values | R2-S0 §8；`max_rows_per_table=2_000_000`；`max_columns_per_table=512`；`max_field_bytes=4 MiB`；`max_tables_per_source=2048` |
| canonical manifest size | bounded by source/table budgets | R4 publication validation |
| Repository `manifest.json` | 16 MiB | upstream `max_manifest_json_bytes`；R4 发布前拒绝；不实现 Repository Service |
| Repository `replay.sql` | 200 MiB | upstream `max_replay_sql_bytes`；R4 不生成 replay SQL（R7），但若校验两入口 envelope 则拒绝超限 |
| diagnostics | 1024 / 4 KiB message | align R2/R3 bounded diagnostics |

现有 identity package writer **尚未** enforce 16/200 MiB。S5 必须在
`storage_projection` publication 边界补上，不得依赖 Repository 进程做第一道门。

超限产生稳定 resource 诊断并 fail-closed，不发布 canonical result、manifest 或
import input。不允许无界 DOM、host path、SQL executor、shell、external XML
resource 或 automatic fallback。

## 10. Fixture naming, markers and parameter-table ownership

Owner 按目录划分：`table_rules` 拥有 selector/parity；`storage_projection` 拥有
projection/digest/manifest/import input。S0 只冻结命名；最小 valid/invalid shape
由 S1 建立。

```text
vnext/fixtures/golden/storage-projection/
vnext/fixtures/vectors/storage-projection/
vnext/backend/tests/test_table_rules_*.py
vnext/backend/tests/test_storage_projection_*.py
vnext/backend/tests/test_canonicalization_manifest.py
vnext/backend/tests/test_repository_import_artifact_*.py
vnext/backend/tests/support/storage_projection_*.py
vnext/backend/tests/support/table_rules_*.py
```

同构错误使用模块级参数表（malformed ruleset、selector collision、ignored-key
conflict、key/row-integrity、gid/no faults）。不把
`vnext/fixtures/vectors/repository/`、`table-access/` 或
`snapshot-materialization/` 当作 R4 通用 corpus；R4 可引用 R3 public Snapshot
output，但 golden 由 R4 owner 维护。

Marker：

- 纯 contract / parity / projection / digest / package-shape = `@pytest.mark.unit`；
- 真实 Repository Service / Dolt = `@pytest.mark.integration`（本轮不引入）；
- 固定时间预算（`Event.wait` / `thread.join` / stream timeout）=
  `@pytest.mark.serial`（S0/S1 不引入）。
- 禁止手写 `skipif(not dolt_available())`。
- 禁止为纯解析/校验引入会 `dolt init` 的 fixture。
- legacy oracle 只允许出现在 test support，不得进入 production import。

既有 `test_canonicalization_manifest.py` 覆盖 identity-projection helper，不是
migrated matrix 的权威 golden。

## 11. Allowed and forbidden paths

S0 相对 R4 execution plan §4 新增本 freeze 文件。完整允许路径：

```text
vnext/backend/src/gateway_backend/capabilities/table_rules/
vnext/backend/src/gateway_backend/capabilities/storage_projection/
vnext/backend/src/gateway_backend/canonicalization_cells.py
vnext/backend/src/gateway_backend/canonicalization_manifest.py
vnext/backend/src/gateway_backend/repository_import_artifact.py
vnext/backend/tests/test_table_rules_*.py
vnext/backend/tests/test_storage_projection_*.py
vnext/backend/tests/test_canonicalization_manifest.py
vnext/backend/tests/test_repository_import_artifact_*.py
vnext/backend/tests/support/storage_projection_*.py
vnext/backend/tests/support/table_rules_*.py
vnext/fixtures/golden/storage-projection/
vnext/fixtures/vectors/storage-projection/
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-design.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-s6-focused-review.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-s7-independent-review.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md
docs/backend-vnext/refactoring/formal/contracts/ruleset-activation-and-migration.md
docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md
docs/backend-vnext/refactoring/formal/adr/0004-raw-source-artifact-and-canonical-dolt-storage.md
docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md
docs/backend-vnext/refactoring/formal/adr/0015-ruleset-activation-and-storage-migration.md
vnext/backend/tests/test_architecture.py
```

根 canonicalization 模块仅允许按 `R4-S0-D03` 迁移/re-export，不得在 capability
外长出第二套 migrated matrix。`table_rules/` 扩展必须 additive。

S1 必须在 `tests/test_architecture.py` 为 `storage_projection` 补 forbidden-token
扫描（至少 `dolt`、`host_path`、`fastapi`、SQL execution、`legacy`），对标 R2/R3
leaf。

禁止：

```text
vnext/repository_service/
vnext/repository_client/
vnext/backend/src/gateway_backend/capabilities/common/
vnext/backend/src/gateway_backend/capabilities/utils/
HTTP, Workspace, Submit, PreviewResult, Operation Runtime or application modules
comparison/risk/surface/bundle/mutation implementation
gateway_repository_service imports
legacy/ production imports
snapshot_materialization private modules (_digest, _parquet, _reader, _catalog, _ruleset, scalar_encoding)
SQL execution, shell execution, external XML resources
host path fields in public contracts
new service/helper/security principal
formal TAR_ZST SourcePackage admission
production retention/cleanup/quota implementation
identity-projection as migrated fallback
comparison planner first-match as production resolver
```

S1 不得越出本 allowlist。再新增路径必须在后续 step handoff 登记。

## 12. Reopen record

S0 未 reopen 任何 owning ADR 或 contract：

| Item | Action | Scope |
| --- | --- | --- |
| ADR 0004 | 不修订 | gid domain 与 raw/canonical 分离保持 |
| ADR 0012 | 不修订 | 同机单一信任域；不新增 broker/sidecar |
| ADR 0013 | 不修订 | ENUM/SET 双边界仍有效；R4 消费 Shared Encoding |
| ADR 0015 | 不修订 | R4 只记录 identity 与 STORAGE_BREAKING 分类 |
| Canonical Storage contract | 不改 ignored→DROP 条文 | §5.2 将 ordered `no` 解释为 RETAIN 派生，而不是合同例外草案 |
| table_rules R3 injection | additive only | 不破坏整数 `table_ruleset_version` |

若后续发现下列情况，必须先 reopen owning contract/ADR，再改 S0/S1 记录：

- 任一 legacy registry 行缺少 owner、consumer、fixture、implementation step 或 guard；
- selector 优先级或重叠无法在不依赖插入序的情况下证明；
- 将 IEC104 `no` 改为 DROP，或把 ignored key 降级为空 key；
- 非 ignored comparison-only metadata 被当作 storage drop 且无显式证据；
- SKIP / snapshot-only / browse-only / `version_manager` 用未登记默认处理；
- keyless/ordered 不变量无法证明，或 raw-PK 空 key 被当作 keyless；
- R4 复制 R3 digest 逻辑或 import R3 private 模块；
- partial/corrupt artifact 可被 promote；
- Repository/HTTP/application/SQL execution 进入 capability；
- 新的 source/package 格式或安全主体；
- 需要提高 §9 numeric budget 才能接纳已确认业务 fixture；
- identity-projection 被当成 migrated table-ruleset fallback。

IEC104 `no` 映射已冻结为 `RETAIN_FOR_STRUCTURE`。除非修订 ordered 合同，不再把
该行当作未解 blocker。

## 13. Deferred register impact

| ID | S0 status |
| --- | --- |
| `R3-D04` | **关闭**；本轮 owner 接管 storage projection / CanonicalizationManifest / RepositoryImportArtifactInput |
| `R3-D01` | 仍延后；formal `TAR_ZST` |
| `R3-D02` | 仍延后；Repository Service/Dolt production adapter 与 hidden-summary write |
| `R3-D03` | 仍延后；retention/pinning/eviction/quota |
| `R3-D05` | 仍延后；projection cache 与 export-format matrix |
| `R3-D06` | 仍延后；Rust provider / automatic fallback |
| `R3-D07` | 仍延后；durable cancel/checkpoint/takeover |
| `R4-D01` | 延后；Repository Service/Dolt production adapter and commit/readback write |
| `R4-D02` | 延后；protected hidden ruleset metadata commit integration |
| `R4-D03` | 延后；retention, pinning, eviction, quota, durable operation ownership |
| `R4-D04` | 延后；mutation plan, ADAPTIVE_PATCH and replay renderer（P3-R7） |
| `R4-D05` | 延后；Rust storage provider/automatic fallback |
| `R4-D06` | 延后；online ruleset watcher and migration executor |
| `R4-D07` | 延后；formal TAR_ZST SourcePackage admission |
| `R4-D08` | 延后；comparison projection/display/risk semantics beyond LegacyRuleDecision |

权威延后表仍是 [P3-R4 execution plan §7](p3-r4-storage-projection-execution-plan.md#7-deferred-register-and-reopen-conditions)。

## 14. Failure and publication freeze

- Missing source/artifact、incomplete closure、rule mismatch、unsupported type、
  invalid key、row loss、ordered invariant failure 或 digest mismatch → 无
  publishable canonical result。
- 表级 diagnostics 允许；任一 **required** 表失败使 ProjectionResult `FAILED`；
  不发布 partial Repository import closure。
- Publication：staging write → manifest/schema/content validation → atomic publish。
- Cancel / deadline / I/O 不得发布 partial manifest、canonical rows 或 import
  reference。
- Cache miss 必须能从 source package 或 pinned RepositoryRef 重建；cache hit 无
  exact binding 则非权威。
- `COMMIT_VALIDATED` 永不由 R4 自提升。
- 不生成、不执行 replay SQL。

## 15. S1 entry package

**Recommendation：S0 complete，允许进入 S1 public ruleset contract 与 skeleton；
不得把本结论表述为 R4 gate 通过或 S2+ 实现授权。**

S1 必须：

- 只在 §11 allowlist 内落成 `table_rules` additive public types 与
  `storage_projection` ports；
- 扩展 `TableRulesetSnapshot` 时保持 `table_ruleset_version: int` 与现有
  `compare_keys` 构造可用；
- 落成 `TableRuleSelector`、static role、compare key mode、ignored/artifact/
  position/stable-key 字段、storage/ordered/keyless policy、
  `LegacyRuleDecision`、`StorageRuleView`、immutable snapshot identity、
  `ProjectionRequest` / `ProjectionResult` / `ProjectionTable` /
  `ProjectionDiagnostic`、CanonicalizationManifest 与
  RepositoryImportArtifactInput **类型或 owner ports**；
- 未知字段、重复 selector、无效优先级、malformed ruleset、ignored key/ordered
  structural conflict fail-closed；
- public types 不含 host path、SQL text、provider-private object 或可变 registry；
- 为 `storage_projection` 增加 architecture forbidden-token 扫描；
- 不实现 resolver 算法、projection、gid 分配、digest 计算或 package writer；
- 最小 valid/invalid fixture shape 使用 §10 命名；同构错误用参数表。

S1 可与 S0 同一对话。本文件不自动授权 S2 legacy parity provider。
`p3_implementation_authorized` 保持 `no`。

## 16. Verification record

S0 不宣称 projection conformance、R4 gate、container 或 production validation
已通过。Container rebuild：**no**。理由：只改 formal docs，未触碰 image、
deployment 或 container-only runtime boundary。Last verified image revision：
none；source-tree 文档审查是本步权威 evidence。Container gate for current HEAD：
`not-applicable`。

S0 执行时工作树仅 docs dirty（含既有未提交的 R4 design/detail plan、相关
contract/index 同步，以及本步 S0 记录）；无 `vnext/` 业务代码变更。

| Command | Result |
| --- | --- |
| `git status --short` | **docs only**；无 `vnext/` 变更。tracked 修改 8 个 formal docs；untracked `p3-r4-s0-entry-and-budget-freeze.md`、`p3-r4-storage-projection-design.md`、`p3-r4-storage-projection-execution-plan.md` |
| `git diff --check` | **passed**（tracked）；untracked R4 design/plan/S0 文件 `--no-index` 无 whitespace error 输出 |
| forbidden path/import scan | **pass**；`table_rules` / `storage_projection` 无 `legacy` / `backend_vnext` / `gateway_repository_service` / `host_path` / `fastapi` production import；无根 `canonicalization_*` import |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -m unit tests/test_architecture.py` | **16 passed**（0.70s）；DAG 已登记 `storage_projection -> {table_rules, snapshot_materialization}`，contracts 仍为空骨架 |

```yaml
Current HEAD: f07c387f513ee735fe69e65c94804d7c63115f0d
r3_validated_code_sha: 7989e47d08c48fda46e7d8b6b3550ef9ee266d92
r3_handoff_documentation_sha: f07c387f513ee735fe69e65c94804d7c63115f0d
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
uv run pytest -m unit tests/test_architecture.py tests/test_table_rules_*.py tests/test_storage_projection_*.py
uv run ruff check .
uv run mypy
git diff --check
```

S1 若尚未创建全部测试 glob，按实际新增文件收敛，不机械扩大范围。无 Dolt。

## 17. S1 public ruleset contract and skeleton record

S1 将 §4–§5 / §8 / §11 / §15 落成可导入的 R4 public types 与 document skeleton。
不实现 `resolve_*` / `project_*` / gid 分配 / 表内容 digest / package writer。
无 `NotImplementedError` stub。`p3_implementation_authorized` 仍为 `no`。不授权 S2。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py
vnext/backend/src/gateway_backend/capabilities/table_rules/__init__.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/contracts.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/__init__.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_table_rules_contracts.py
vnext/backend/tests/test_storage_projection_contracts.py
vnext/backend/tests/support/table_rules.py
vnext/backend/tests/support/storage_projection.py
vnext/fixtures/golden/storage-projection/ruleset/
docs/backend-vnext/refactoring/formal/plans/p3-r4-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

`table_rules.contracts` 保持 R3 `TableRulesetSnapshot(table_ruleset_version=1)` 可构造，
并 additive 增加 selector/两层规则/ruleset document walking path
（`table_ruleset_document` / `table_ruleset_from_document` / `compute_ruleset_digest`）。
`ruleset_digest` 为 JCS SHA-256 `DigestRef`，不加 manifest 域前缀。空 `rules` 允许
`digest=None`（R3-only）。`storage_projection.contracts` 落地 Projection/Manifest/ImportInput
ports、16 MiB / 200 MiB publication 上限，以及本地 `ProjectionInvocationContext`
（不 import `table_access`）。无 `project_*` 入口。

S1 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -m unit tests/test_architecture.py tests/test_table_rules_*.py tests/test_storage_projection_*.py` | **37 passed**（0.75s） |
| `cd vnext/backend && uv run --offline ruff check . && uv run --offline mypy` | **passed**；mypy 124 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python contract/test/docs，未触碰
image/deployment boundary。无 Dolt。`p3_implementation_authorized` 仍为 `no`。

S2 必须严格执行 §6–§9；不得从本 skeleton 猜测 resolver、投影算法、gid 分配或 package
writer 语义。

```yaml
Current HEAD: f07c387f513ee735fe69e65c94804d7c63115f0d
Container rebuild required: no
Reason: Python contracts, unit tests, golden document shapes, and formal docs only
Last verified image revision: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: none
Required execution point: later R if an image/deployment/container boundary is introduced
```

## 18. S2 legacy rule-resolution parity provider record

S2 将 §6–§7 矩阵落成不可变 `migrated_table_ruleset_snapshot()` 与
`resolve_table_rule()`。52 条 `TableRuleRecord` 按 precedence rank 然后 selector
serialization 排序。无 hidden mutable registry。空 `rules` 或无 FALLBACK 的未命中
fail-closed。production 不 import legacy；oracle 只在 `tests/support`。不实现
`project_*`、gid 分配、表内容 digest 或 package writer。`p3_implementation_authorized`
仍为 `no`。S3 已授权、尚未实现。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py
vnext/backend/src/gateway_backend/capabilities/table_rules/resolver.py
vnext/backend/src/gateway_backend/capabilities/table_rules/__init__.py
vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_table_rules_resolver.py
vnext/backend/tests/support/table_rules.py
vnext/backend/tests/support/table_rules_legacy_oracle.py
vnext/fixtures/golden/storage-projection/ruleset/valid/s2-migrated-matrix/document.json
docs/backend-vnext/refactoring/formal/plans/p3-r4-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-design.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

S2 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -m unit tests/test_architecture.py tests/test_table_rules_*.py tests/test_storage_projection_*.py` | **172 passed**（0.83s） |
| `cd vnext/backend && uv run --offline ruff check . && uv run --offline mypy` | **passed**；mypy 128 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python resolver/test/golden/docs，未触碰
image/deployment boundary。无 Dolt。S3 可在同一实现上下文消费
`ResolvedTableRule.record`；不得改写 S2 selector/precedence/parity 语义。

```yaml
Current HEAD: f07c387f513ee735fe69e65c94804d7c63115f0d
Container rebuild required: no
Reason: Python resolver, unit tests, golden document, and formal docs only
Last verified image revision: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: none
Required execution point: later R if an image/deployment/container boundary is introduced
```

## 19. S3 canonical storage projection core record

S3 实现普通 keyed 表的 `StorageRuleView` 派生与 `project_storage()`。消费 S2
`resolve_table_rule`（经 `table_rules.contracts` 再导出，不跨 capability 直接 import
`resolver`）。SKIP 表省略；`ORDERED_DIFF` / `EXPLICIT_KEYLESS` / ENUM·SET 仍
`UNSUPPORTED_TABLE`。COMPLETE 只返回内存 `CanonicalizationManifest` +
`RepositoryImportArtifactInput` + `manifest_digest`；不写 staging、不打 tar、不
atomic replace。任一 required 表失败则 `FAILED` 且不发布 manifest。
`p3_implementation_authorized` 仍为 `no`。S4 已完成；S5 已完成。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py
vnext/backend/src/gateway_backend/capabilities/table_rules/resolver.py
vnext/backend/src/gateway_backend/capabilities/table_rules/__init__.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/__init__.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/view.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/_digest.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/_runtime.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py
vnext/backend/tests/test_storage_projection_core.py
vnext/backend/tests/test_storage_projection_contracts.py
vnext/backend/tests/support/storage_projection.py
docs/backend-vnext/refactoring/formal/plans/p3-r4-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-design.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

S3 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -m unit tests/test_architecture.py tests/test_table_rules_*.py tests/test_storage_projection_*.py` | **203 passed**（1.08s） |
| `cd vnext/backend && uv run --offline ruff check . && uv run --offline mypy` | **passed**；mypy 133 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python projection/test/docs，未触碰
image/deployment boundary。无 Dolt。S4 可在新实现上下文扩展 ordered/keyless 与
ENUM/SET；不得改写 S2 selector/precedence/parity 或 S3 keyed digest 算法。

```yaml
Current HEAD: f07c387f513ee735fe69e65c94804d7c63115f0d
Container rebuild required: no
Reason: Python storage projection, unit tests, and formal docs only
Last verified image revision: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: none
Required execution point: later R if an image/deployment/container boundary is introduced
```

## 20. S4 ordered/keyless and digest integrity record

S4 闭合显式 keyless 多重集、IEC104 `gid_no_v1` 有序投影，以及 schema/content/
ordering/manifest digest。Keyed 流式 content digest 算法保持 S3；`no` 为
`RETAIN_FOR_STRUCTURE` 且不进入 ordinary content digest。pseudo gid 从
`4_000_000_000` 按 canonical `no` 连续分配。ENUM/SET 单元格走 Shared Kernel
`encode_typed_scalar` / `encode_collection`，不 import R3 private digest 或根
`canonicalization_cells`。COMPLETE 仍只返回内存 manifest + import input；不写
staging、不打 tar。`p3_implementation_authorized` 仍为 `no`。S5 已完成；S6 focused review 已完成。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/storage_projection/view.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/contracts.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/_digest.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/_ordered.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py
vnext/backend/tests/test_storage_projection_core.py
vnext/backend/tests/test_storage_projection_integrity.py
vnext/backend/tests/support/storage_projection.py
vnext/backend/tests/support/table_rules.py
docs/backend-vnext/refactoring/formal/plans/p3-r4-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-design.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

S4 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -m unit tests/test_architecture.py tests/test_table_rules_*.py tests/test_storage_projection_*.py` | **221 passed**（1.15s） |
| `cd vnext/backend && uv run --offline ruff check . && uv run --offline mypy` | **passed**；mypy 135 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python projection/test/docs，未触碰
image/deployment boundary。无 Dolt。S5 已发布 durable manifest 与 structural
package；不得改写 S2 selector/parity、S3 keyed digest 或本步 gid/no/ENUM/SET
content 算法。

```yaml
Current HEAD: f07c387f513ee735fe69e65c94804d7c63115f0d
Container rebuild required: no
Reason: Python ordered/keyless projection, digest integrity tests, and formal docs only
Last verified image revision: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: none
Required execution point: later R if an image/deployment/container boundary is introduced
```

## 21. S5 Manifest, Import Input and atomic publication record

S5 把 S2–S4 的内存 `CanonicalizationManifest` / `RepositoryImportArtifactInput` 做成
durable 发布：JCS 持久化（含 `manifest_digest`）、合同 §6.1 nested `schema` 的
`manifest.json`、固定两入口 USTAR+zstd，以及 ArtifactStorePort 上的 staging write →
locate/validate → 成对 atomic publish。16/200 MiB 在 `storage_projection` publication
边界强制执行。`replay.sql` 由调用方显式传入，本步不生成、不执行。根
`repository_import_artifact.py` 改为 thin wrap capability packer；identity assembler
仍不是 migrated fallback。capability 不 import 根 canonicalization 三模块、R3 private
模块或 Repository/Dolt。`p3_implementation_authorized` 仍为 `no`。S6 focused review 已完成。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/storage_projection/contracts.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/__init__.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/package.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/publish.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py
vnext/backend/src/gateway_backend/repository_import_artifact.py
vnext/backend/tests/test_storage_projection_contracts.py
vnext/backend/tests/test_storage_projection_publication.py
vnext/backend/tests/test_repository_import_artifact_package.py
vnext/fixtures/golden/storage-projection/manifest/valid/s5-durable-roundtrip/document.json
vnext/fixtures/golden/storage-projection/package/valid/s5-structural-shape/manifest.json
docs/backend-vnext/refactoring/formal/plans/p3-r4-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-design.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

S5 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -m unit tests/test_architecture.py tests/test_table_rules_*.py tests/test_storage_projection_*.py tests/test_repository_import_artifact_*.py tests/test_canonicalization_manifest.py` | **265 passed**（1.19s） |
| `cd vnext/backend && uv run --offline ruff check . && uv run --offline mypy` | **passed**；mypy 139 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python publication/test/golden/docs，未触碰
image/deployment boundary。无 Dolt。S6 focused review 已完成；不得改写 S2 selector/parity、
S3 keyed digest 或 S4 gid/no/ENUM/SET content 算法。

```yaml
Current HEAD: f07c387f513ee735fe69e65c94804d7c63115f0d
Container rebuild required: no
Reason: Python durable manifest/package publication, unit tests, golden documents, and formal docs only
Last verified image revision: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: none
Required execution point: later R if an image/deployment/container boundary is introduced
```

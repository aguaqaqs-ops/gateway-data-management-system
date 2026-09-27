# P3-R4 Storage Projection Design Baseline

状态：Accepted design baseline；S0 freeze complete；S1 complete；S2 complete；S3 complete；S4 complete；S5 complete；S6 complete；S7 complete；S8 module gate complete，R4 gate pass；implementation authorization pending

日期：2026-08-20

阶段：P3-R4 design complete；S0 freeze complete；S1 complete；S2 parity complete；S3 projection core complete；S4 ordered/keyless/digest complete；S5 publication complete；S8 module gate complete

Owner：Backend vNext Table Rules / Storage Projection

上级设计：[P3 Capability Foundation Design](p3-capability-foundation-design.md)

上级执行计划：[P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)

R3 入口：[P3-R3 Source Materialization and Snapshot Handoff](p3-r3-source-materialization-handoff.md)

Normative storage boundary：[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)

Ruleset activation：[Ruleset Activation and Migration](../contracts/ruleset-activation-and-migration.md)

## 1. Objective

P3-R4 将 R3 的 immutable Snapshot/SnapshotTableArtifact 投影为 canonical storage
facts，并提供后续 Repository import 所需的 immutable structural input：

~~~text
Snapshot / SnapshotTableArtifact
  + immutable TableRulesetSnapshot
  -> legacy-compatible rule decision
  -> canonical storage projection
  -> CanonicalizationManifest
  -> RepositoryImportArtifactInput
~~~

R4 的第一目标不是重新设计业务规则，而是迁移 legacy TableRuleRegistry 的有效业务
语义并把它拆成两个明确视图：

1. LegacyRuleDecision：保留旧实现的 selector、role、effective key、ignored columns
   和 artifact scope，供 parity、provenance 与下游 comparison 复用；它不代表这些列仍在
   canonical storage 中存在。
2. StorageRuleView：只表达 canonical storage 需要的 physical key、保留列、结构列、
   ordered identity 和 fail-closed 条件。

R4 已确认 legacy `ignored_columns` 直接形成 canonical authority：它们必须从
`StorageRuleView.retained_columns`、canonical schema、canonical content digest 和 Dolt
business state 中排除，并以 `DROP_FROM_STORAGE` 及 manifest reason 记录。原始列仍由
SourcePackageArtifact/Snapshot 保留，供 parity、provenance 和原始表读取；这不是恢复原始表的
要求。`UPDATE_ONLY` 仍只表达 artifact/comparison 范围，不自动触发删列。

## 2. Scope and non-goals

### 2.1 In scope

- legacy registry 的完整 rule-resolution parity；
- selector 优先级、exact/regex pattern、fallback 和 special-case 语义；
- immutable TableRulesetSnapshot 的完整 identity：ruleset_id、ruleset_version、
  ruleset_digest、contract version；
- canonical storage key/schema、column policy、ordered gid/no preparation、keyless
  explicit policy 和 row-integrity validation；
- canonical schema/content/ordering digest；
- durable CanonicalizationManifest 的 producer contract；
- RepositoryImportArtifactInput 的 structural manifest、canonical rows 和 opaque binding；
- staging validation、atomic publication、missing/corrupt artifact fail-closed；
- legacy/vNext differential fixtures、golden fixtures、component benchmark 和 review evidence。

### 2.2 Out of scope

- HTTP、Workspace、PreviewResult、Submit/application flow 和 Operation Runtime；
- Repository Service/Dolt production adapter、commit/readback write 和 hidden-summary write；
- StorageMutationPlan、ADAPTIVE_PATCH、Dolt replay SQL renderer 和 external target renderer；
- comparison records、risk/surface/bundle presentation；
- retention/eviction/quota、durable checkpoint/takeover 和 online ruleset watcher；
- formal TAR_ZST SourcePackage admission；
- Rust provider or automatic fallback；
- arbitrary legacy bugs, unsafe behavior or unowned compatibility aliases。

R4 may expose a package-builder input and deterministic package-envelope validation, but replay
SQL generation remains R7-owned. R4 must not send SQL to a Repository or execute it.

## 3. Authority and migration policy

### 3.1 Authority order

When sources disagree, use this order:

1. current formal Contract/ADR and user-confirmed R4 decisions;
2. accepted P3-R3 public contracts and immutable artifact boundary;
3. legacy registry and downstream behavior as a reference oracle;
4. legacy tests, fixtures and generated presentation rules;
5. implementation convenience.

Legacy behavior is preserved when it is valid business semantics. A legacy bug, unsafe path,
unbounded behavior or behavior contradicted by a current Contract is not copied; it becomes a
typed diagnostic or hard failure and is recorded in the R4 decision register.

### 3.2 Legacy baseline

The migration source is:

~~~text
legacy/backend_vnext/capabilities/table_rules/models.py
legacy/backend_vnext/capabilities/table_rules/semantic.py
legacy/backend_vnext/capabilities/table_rules/registry.py
legacy/backend_vnext/capabilities/comparison/ruleset_registry.py
~~~

The baseline includes:

- SKIP, SNAPSHOT_ONLY, BROWSE_ONLY, STANDARD_DIFF, ORDERED_DIFF roles;
- exact names and regex selectors;
- selector precedence SKIP > SNAPSHOT_ONLY > BROWSE_ONLY > ORDERED_DIFF > STANDARD_DIFF;
- explicit keys, raw-primary-key fallback and protocol table pattern keys;
- ignored columns and artifact scopes ALL_CHANGES, UPDATE_ONLY, ORDERED_SEMANTIC;
- IEC104 ordered families and gid/no policy;
- composite_signal_point, net_cfg, device point tables, com_cfg, pointref_forwardtbl,
  scdmod_para, app_cfg, rdb_cfg, device_cfg and protocol config patterns;
- the version_manager identity exception, which must not be treated as an ordinary skip.

Presentation-only generated rules, frontend widths, risk labels and comparison renderer details
are not part of the R4 storage contract. They remain downstream owner inputs.

### 3.3 Version identity

The legacy-compatible baseline uses a structured identity rather than a bare integer:

~~~text
ruleset_id       = backend-vnext/table-ruleset
ruleset_version  = v2
ruleset_digest   = sha256:<digest of canonical ruleset document>
contract_version = gateway-vnext.table-ruleset:v1
~~~

The exact string values are frozen by S0 after canonicalizing the migrated matrix. The digest
includes selector order/precedence, rule fields, storage projection version binding and contract
version. Provider name, Python module path and generated code identity are excluded.

An immutable snapshot is captured at operation entry. A later activation cannot change an active
operation. Storage-breaking rule changes are MIGRATION_REQUIRED under ADR 0015 and are not
silently applied to an existing repository.

## 4. Two-layer rule model

### 4.1 LegacyRuleDecision

This view preserves decision parity and may contain fields that storage projection does not use:

~~~text
selector
static_role
compare_key_mode
compare_key_columns
ignored_columns
artifact_scope
position_column
stable_key_candidates
~~~

Resolution is deterministic. A table must match at most one effective selector after precedence
and conflict validation. Duplicate or overlapping rules with incompatible outcomes fail ruleset
validation; the resolver must not use insertion order as a hidden tie-breaker.

### 4.2 StorageRuleView

> 取代说明（2026-09-27）：列处置由 [ADR 0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md) 补充与取代：新增 `compare_excluded_columns`（保留在存储中、
> 不参与值比较）；ordered 表的 `no` 是 `RETAIN_FOR_STRUCTURE` 列，不得列入 `ignored_columns`；比较语义由
> table_rules 的 `ComparisonRuleView` 提供。本节历史正文不改写。

Storage projection consumes an explicit derived view:

~~~text
canonical_table
storage_policy: PERSIST_BUSINESS | RETAIN_FOR_STRUCTURE | DROP_FROM_STORAGE
canonical_key: explicit | ddl_primary_key | explicit_keyless
ordered_policy: none | gid_no_v1
retained_columns: DDL-order tuple
structural_columns: DDL-order tuple
dropped_columns: tuple(name, reason)
storage_rule_digest
~~~

The derivation rules are canonicalization rules:

- every legacy `ignored_columns` entry becomes `DROP_FROM_STORAGE` with reason
  `legacy_ignored_column:<selector>`;
- v1 migrated rules default every non-ignored source column to `PERSIST_BUSINESS`;
- an ignored column selected as effective key, ordered identity or required structural column
  fails ruleset validation; it is never silently retained;
- ordered no is RETAIN_FOR_STRUCTURE, not an ordinary modified-value column;
- comparison-only metadata other than legacy `ignored_columns` is not a storage drop without an
  explicit R4 storage rule and manifest reason.

### 4.3 Legacy role to storage mapping

The R4 baseline is:

| Legacy role | Source Snapshot | Canonical storage | Comparison meaning |
| --- | --- | --- | --- |
| SKIP | omitted, except explicit version_manager identity path | omitted | no comparison |
| SNAPSHOT_ONLY | retained | retained with all non-ignored columns by default | no comparison records |
| BROWSE_ONLY | retained | retained with all non-ignored columns by default | presence/browse facts only |
| STANDARD_DIFF | retained | projected keyed table with all non-ignored columns | normal comparison |
| ORDERED_DIFF | retained | projected ordered table with all non-ignored columns | ordered comparison |

`UPDATE_ONLY` remains a comparison/artifact input. `ignored_columns` are canonical storage drops;
this intentionally means the canonical table is not a full physical reproduction of the source.

## 5. Canonical storage semantics

### 5.1 Input binding

Every projection request must carry:

~~~text
SnapshotTableArtifact closure or equivalent complete SnapshotTableReader closure
SourceArtifactBinding / source artifact digest
immutable TableRulesetSnapshot
storage_projection_version
requested table policy
~~~

R4 rejects missing, mismatched or provisional-only bindings. It never reads R3 private modules,
reconstructs a summary from arbitrary catalog rows, or infers rules from table names outside the
frozen snapshot.

### 5.2 Keyed tables

- Explicit legacy storage key wins over DDL primary key.
- If no explicit key exists, the DDL primary key is accepted only when all key columns are
  retained, non-null as required, non-empty and unique.
- An effective key column marked `ignored_columns` is a ruleset conflict and fails validation;
  DDL fallback cannot reintroduce a column that the canonical ruleset drops.
- After publication, the projected `canonical_key` is the authoritative physical key. A source DDL
  primary-key change is provenance/schema input; changing the persisted canonical key requires a
  new ruleset/storage projection identity and `STORAGE_BREAKING` migration.
- Keyless/multiset is accepted only through an explicit ruleset classification.
- Missing key, duplicate key, null/empty key, key column removal or row loss is a typed blocker.
- Projection row count equals source row count for every successfully projected table.

### 5.3 Ordered tables

The v1 ordered policy is the formal gid/no contract:

~~~text
gid real:   1 .. 3_999_999_999
gid pseudo: 4_000_000_000 .. 4_294_967_295
gid 0:      forbidden
no:         positive, unique, continuous
~~~

Real gid values must be unique and in the real range. Null, empty or zero source gid receives
deterministic pseudo allocation after canonical no ordering. Source values in the pseudo range,
duplicate no, missing no or non-continuous no fail closed. no is retained for structural
ordering and ordering digest; it is not an ordinary business modified column.

### 5.4 Digest ownership

R3 retains ownership of raw_content_digest, business_content_digest and snapshot_digest.
R4 owns:

- canonical schema digest;
- canonical content digest over retained canonical cells;
- ordered identity/ordering digest where applicable;
- storage projection digest;
- complete CanonicalizationManifest digest.

R4 must not copy or reinterpret R3 raw/business digest algorithms. The manifest digest uses
RFC 8785 JCS and the domain-separated canonicalization-manifest prefix. ENUM/SET cell bytes follow
ADR 0013 and Shared Canonical Encoding v1.

Canonical schema/content digests cover retained canonical columns only. A source value change in a
`DROP_FROM_STORAGE` column therefore cannot change R4 canonical storage/business identity; the R3
raw/business/snapshot digest may still change as source provenance and must remain distinct. The source
and dropped-column facts remain available through the durable source artifact and manifest. A rule
change that adds or removes a dropped column changes the canonical schema/ruleset identity and is
`STORAGE_BREAKING`.

## 6. Manifest and repository import boundary

### 6.1 Durable manifest

The durable CanonicalizationManifest records at least:

- contract, storage projection, ruleset ID/version/digest and source artifact digest;
- source and canonical schema/row counts per table;
- retained, structural and dropped columns with reasons;
- canonical key and key policy;
- canonical content digest and optional ordering digest;
- ordered identity policy, gid range/count and relevant diagnostics;
- manifest digest.

The manifest is Backend-owned. Repository Service consumes only the minimal structural subset
and treats the manifest digest as opaque.

The manifest's canonical key, retained columns and dropped-column set are authoritative structural
facts for the resulting canonical repository state. `RepositoryImportArtifactInput` repeats only
the minimal structural projection needed by Repository; it is not a comparison hint. The source
DDL/key remains provenance, while the projected canonical schema/key is the storage authority.

### 6.2 Repository import input

R4 publishes an immutable RepositoryImportArtifactInput containing canonical schema, rows,
structural manifest and opaque manifest binding. R7 owns mutation policy and replay generation.
The R4 package boundary may validate the fixed two-entry manifest.json/replay.sql envelope,
but R4 does not generate or execute replay.sql.

### 6.3 Hidden ruleset metadata

R4 includes ruleset identity in the durable Backend manifest. Protected hidden ruleset metadata
may be atomically persisted with a formal canonical commit under ADR 0015, but the Repository
adapter/commit write is outside R4. It is not listed as an ordinary business table and is not
consumed by comparison, risk, bundle or mutation planning.

## 7. Failure and lifecycle semantics

- Missing source/artifact, incomplete closure, rule mismatch, unsupported type, invalid key,
  row loss, ordered invariant failure or digest mismatch yields no publishable canonical result.
- Independent table diagnostics are allowed during projection, but a required table failure makes
  the projection result FAILED; R4 does not publish a partial Repository import closure.
- Publication is staging write -> manifest/schema/content validation -> atomic publish.
- Cancellation, deadline, I/O, provider or process failure cannot publish a partial manifest,
  canonical rows or import reference.
- Artifact cache miss has a source/ref rebuild route; a cache hit is never authoritative without
  exact binding validation.
- COMMIT_VALIDATED is never self-promoted by R4.

## 8. Verification and acceptance

R4 exits only when:

- every legacy selector and fallback has a matrix entry and differential fixture;
- selector precedence and conflict rejection are deterministic;
- legacy-compatible LegacyRuleDecision output matches the reference oracle for valid behavior;
- every legacy ignored column is absent from canonical retained columns and has a manifest drop reason;
- an ignored key/ordered/required structural column fails ruleset validation;
- source-only changes to dropped columns produce no R4 canonical content/storage-business change;
- keyed, explicit keyless and ordered projections satisfy row/key/gid/no invariants;
- schema/content/ordering/manifest digests are deterministic across input row order where required;
- manifest/package validation and atomic publication reject incomplete/corrupt inputs;
- no R3 private import, Repository/HTTP/application dependency or SQL execution exists;
- focused and independent review pass with no unclassified P1/P2 or contract ambiguity;
- component benchmark evidence is recorded without inventing a numeric performance gate;
- R4 handoff identifies the R5 input boundary and all deferred/reopen conditions.

S8 module gate is recorded in
[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)。
R4 gate pass；`p3_r5_ready: yes`；`p3_implementation_authorized: no`。

## 9. Deferred and reopen conditions

Deferred beyond R4:

- Repository Service/Dolt production adapter and commit/readback write;
- durable hidden metadata persistence integration;
- retention/eviction/quota and durable operation ownership;
- mutation planning, adaptive patch and replay renderer;
- Rust provider and automatic fallback;
- online ruleset activation and migration executor.

Reopen R4 before its gate if the legacy baseline cannot be represented without changing valid
business semantics, a selector conflict is unresolved, an ignored column is retained or omitted
from its manifest drop reason, a non-ignored comparison-only rule is proposed as a storage drop
without evidence, an ordered/keyless rule lacks a complete invariant, a digest changes with
forbidden input metadata, a partial artifact can become publishable, or a new consumer requires
Repository/HTTP/application behavior.

# P3-R4 Storage Projection Execution Plan

状态：S0 complete；S1 complete；S2 complete；S3 complete；S4 complete；S5 complete；S6 complete；S7 complete；S8 module gate complete，R4 gate pass；handoff: [p3-r4-storage-projection-handoff.md](p3-r4-storage-projection-handoff.md)

日期：2026-08-20

阶段：P3-R4 S0 freeze complete；S1 public contract complete；S2 parity complete；S3 projection core complete；S4 ordered/keyless/digest complete；S5 publication complete；S6 focused review complete；S7 independent review complete；S8 module gate complete

Owner：Backend vNext Table Rules / Storage Projection

设计基线：[P3-R4 Storage Projection Design Baseline](p3-r4-storage-projection-design.md)

上级计划：[P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)

R3 handoff：[P3-R3 Source Materialization and Snapshot Handoff](p3-r3-source-materialization-handoff.md)

S0 冻结：[P3-R4-S0 Entry, Applicability, Legacy Matrix and Budget Freeze](p3-r4-s0-entry-and-budget-freeze.md)

## 1. Objective and exit

R4 将 R3 immutable Snapshot/SnapshotTableArtifact 闭合为 canonical storage projection，并
产出 Backend-owned CanonicalizationManifest 与 RepositoryImportArtifactInput。

R4 必须交付：

- legacy TableRuleRegistry 的完整 rule-resolution parity；
- immutable ruleset snapshot with ruleset_id/version/digest；
- LegacyRuleDecision 与 StorageRuleView 两层 owner contract；
- explicit selector precedence、fallback、special-case 和 conflict semantics；
- conservative column policy、canonical key/schema、keyless and ordered gid/no projection；
- canonical schema/content/ordering/storage projection digests；
- durable CanonicalizationManifest producer and structural import input；
- staging validation、atomic publication、partial/failure/cancel/timeout/I/O semantics；
- legacy/vNext differential fixtures、golden fixtures、resource diagnostics and benchmark record；
- focused review、independent review、R4 gate and R5 handoff；
- explicit deferred/reopen register with no hidden legacy compatibility gap。

R4 不实现 HTTP、Workspace、Submit/application flow、Operation Runtime、Repository Service/
Dolt adapter/write/readback、comparison engine、risk/surface/bundle、mutation planner、replay
renderer、external target、retention lifecycle、Rust provider or online ruleset activation.

## 2. Conversation and remediation policy

R4 uses nine step boundaries. The context rule is part of the execution contract.

| Step | Conversation | Context rule |
| --- | --- | --- |
| S0 entry, applicability and matrix freeze | 新开 R4 entry 对话 | 读取 R3 handoff、R4 design、normative contracts、legacy registry、current git status；冻结 scope、matrix source、budgets、allowlist、reopen |
| S1 public ruleset contract and skeleton | 与 S0 同一对话 | 将 S0 决策落成 public contracts、ruleset identity、matrix schema、architecture/import checks；不实现 projection algorithm |
| S2 legacy rule parity provider | 新开 implementation 对话 | 携带 S0/S1 records、legacy source paths、selector precedence、parity oracle and fixtures；实现 resolver and immutable snapshot |
| S3 storage projection core | 与 S2 同一实现对话 | 在同一上下文消费 S2 public rule view，实现 column policy、key/schema、unknown/unclassified fail-closed 和 row-integrity |
| S4 ordered/keyless and digest integrity | 新开 implementation/integrity 对话 | 携带 S2/S3 handoff、ordered contract、canonical encoding、digest ownership and fault matrix；实现 gid/no、keyless and digest closure |
| S5 manifest/import input and atomic publication | 新开 artifact/integrity 对话 | 携带 stable S2-S4 public contracts；验证 durable manifest、structural package input、artifact staging and publish failure atomicity |
| S6 focused review | 新开 focused review 对话 | reviewer 只依赖 plan、design、formal contracts、legacy matrix、diff、fixtures and exact test output，不依赖 implementer 口述 |
| S7 independent review | 新开 independent review 对话 | 与 implementation/S6 隔离；独立核对 parity、owner/import、digest、resource、recovery and forbidden boundaries |
| S8 module gate and R5 handoff | 新开 acceptance/documentation 对话 | 汇总 tested tip、commands/results、review closure、deferred/reopen、container decision and R5 prerequisites |

Remediation is embedded, not a standalone S-step:

~~~text
S6/S7 finding
  -> issue register
  -> return to owning S2/S3/S4/S5 implementation conversation
  -> fix + regression fixture + focused rerun
  -> return to original review conversation
  -> re-review and close or reopen owner
~~~

P1/P2 finding、contract ambiguity、selector conflict、digest mismatch、row-loss/key failure、
resource/security/recovery failure or hidden dependency must be closed or formally reopen its
owner before the next gate. Do not invent a separate remediation conversation or round number.

## 3. Authority, inputs and ownership

Normative owners:

| Fact | Owner | R4 treatment |
| --- | --- | --- |
| Snapshot/Artifact public input | R3 snapshot_materialization | consume public contracts only |
| legacy rule decision semantics | table_rules | migrate valid legacy behavior; no legacy import in production |
| canonical storage key/schema/column policy | storage_projection + table_rules | R4 owner |
| canonicalization manifest | storage_projection | R4 owner |
| Repository generic effect | Repository Service | R4 supplies structural input only |
| legacy ignored columns | table_rules + storage_projection | preserve in LegacyRuleDecision, but map every entry to `DROP_FROM_STORAGE` in StorageRuleView and manifest |
| UPDATE_ONLY/artifact scope | comparison/table_rules | preserve as comparison/artifact range; do not infer storage drop |
| mutation/replay policy | P3-R7 | R4 does not implement |
| activation/migration lifecycle | ADR 0015 / future P4/P5 | R4 records identity and impact classification only |

Legacy reference inputs:

~~~text
legacy/backend_vnext/capabilities/table_rules/models.py
legacy/backend_vnext/capabilities/table_rules/semantic.py
legacy/backend_vnext/capabilities/table_rules/registry.py
legacy/backend_vnext/capabilities/comparison/ruleset_registry.py
legacy/backend_vnext/capabilities/snapshot_materialization/rules.py
legacy/backend_vnext/capabilities/snapshot_materialization/canonical_storage.py
legacy/backend_vnext/capabilities/repository_import/canonical_storage.py
~~~

Legacy is read-only oracle. No vNext production module may import legacy packages.

## 4. Allowed and forbidden paths

S0 confirmed exact changed paths. Frozen allowlist:

~~~text
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
docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-handoff.md
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
~~~

Existing root canonicalization modules are candidate R4 assets, not a second owner. S0 freeze
`R4-S0-D03` retains identity-projection helpers and requires R4 public surface to live in
`storage_projection` (with optional later re-export). Do not create generic capabilities/common
or capabilities/utils.

Forbidden:

~~~text
vnext/repository_service/
vnext/repository_client/
HTTP, Workspace, Submit, PreviewResult, Operation Runtime or application modules
comparison/risk/surface/bundle/mutation implementation
gateway_repository_service imports
legacy/ production imports
SQL execution, shell execution, external XML resources
host path fields in public contracts
new service/helper/security principal
formal TAR_ZST SourcePackage admission
production retention/cleanup/quota implementation
~~~

## 5. Frozen invariants

- R4 consumes only complete R3 SnapshotTableArtifact/reader closure plus explicit source binding.
- Missing, provisional-only, mismatched or corrupt input fails closed and publishes no canonical result.
- Required table failure makes the projection result FAILED; R4 never publishes a partial Repository
  import closure.
- Projection does not deduplicate, overwrite, last-write-wins, sort away duplicates or add a
  surrogate key.
- Keyed projection preserves row count and validates effective key presence, nullability and
  uniqueness.
- Keyless/multiset is explicit ruleset policy only; no implicit fallback.
- Ordered policy uses gid real range 1..3_999_999_999, pseudo range 4_000_000_000..4_294_967_295,
  forbidden 0, and positive unique continuous no.
- Null/empty/zero ordered gid receives deterministic pseudo allocation after canonical no ordering.
- no is retained structural data and ordering digest input; it is not ordinary modified business
  data.
- every legacy `ignored_columns` entry maps to `DROP_FROM_STORAGE` with
  `legacy_ignored_column:<selector>` manifest reason;
- UPDATE_ONLY remains comparison/artifact semantics and does not drop columns;
- v1 migrated rules default every non-ignored source column to `PERSIST_BUSINESS`;
- an ignored key/ordered/required structural column fails ruleset validation rather than being
  silently retained.
- R3 owns raw/business/snapshot digests; R4 owns canonical storage/schema/content/ordering/manifest
  digests without copying R3 private algorithms.
- Repository receives only minimal structural import fields and opaque manifest binding; it does not
  select keys, drops, gid allocation or business digests.
- Publication is staging write -> validation -> atomic publish.
- COMMIT_VALIDATED is never self-promoted by R4.
- provider identity, module path, thread count, package compression metadata and source row order
  do not alter semantic identity where the owning contract declares order independence.

## 6. Step execution plan

### S0 — Entry, applicability, legacy matrix and budget freeze

Conversation: new R4 entry conversation.

状态：complete。权威记录：[P3-R4-S0](p3-r4-s0-entry-and-budget-freeze.md)。S1 仅在
该 freeze 的 allowlist 内授权。

Objective: prove R3 handoff is a valid input, inventory the complete legacy ruleset, freeze the
canonicalization mapping in which legacy ignored columns become storage drops, separate remaining
comparison semantics from storage semantics, freeze R4 budgets and record all reopen conditions.

Inputs:

- R3 handoff and S0/S6/S7 records;
- R4 design baseline and canonical storage/repository contracts;
- ADR 0004, ADR 0013, ADR 0015 and shared encoding;
- all legacy reference files listed in §3;
- current git status and architecture tests.

Required decisions and outputs:

1. Matrix schema with columns: selector, selector type, precedence, static role, compare key mode,
   key columns, ignored columns, artifact scope, position column, stable key candidates, storage
   policy, storage key, ordered policy, source owner, consumer, fixture status, migration status,
   earliest implementation step and reopen guard. Every ignored-column cell must resolve to
   `DROP_FROM_STORAGE`; a key/ordered/structural conflict is a matrix blocker.
2. Complete legacy inventory: eight skipped exact names; forwardtable snapshot-only pattern;
   browse-only exact names; nine IEC104 ordered families; explicit standard rules; device point
   update-only rules; device_cfg; protocol option/device patterns; raw-primary-key fallback;
   version_manager exception.
3. Conflict/overlap policy: preserve legacy precedence, reject incompatible duplicate rules and
   never use dict insertion order as a hidden tie-breaker.
4. Ruleset identity document and digest input shape. Freeze legacy-compatible ID/version only after
   canonical matrix review.
5. Role-to-storage mapping from the design baseline. Every ignored column is dropped from canonical
   storage; every non-ignored source column defaults to `PERSIST_BUSINESS`. Any structural conflict
   is an explicit blocker row, not an implementation default.
6. Resource budgets: source table rows/fields inherit R3/R2 limits; canonical manifest is bounded
   by source/table budgets; Repository import manifest 16 MiB and replay 200 MiB remain upstream
   limits; R4 must reject before publication if its output exceeds contract limits.
7. Allowed paths, fixture roots, marker classification and container rebuild decision.

Checks: read-only contract cross-reference, legacy matrix extraction review, git status, forbidden
path/import scan, git diff --check. No business code, Dolt, Repository process or external process.

Exit: no unresolved legacy source, selector precedence, role mapping, ruleset identity, budget,
owner or artifact boundary ambiguity. S1 is authorized only within the allowlist.

S0 outcome: [P3-R4-S0](p3-r4-s0-entry-and-budget-freeze.md) records a complete matrix with no
unclassified row and no blocker row. Ordered `no` is `RETAIN_FOR_STRUCTURE` via the frozen
derivation order; remaining ignored columns are `DROP_FROM_STORAGE`. S1–S8 are complete;
R4 gate pass.

### S1 — Public ruleset contract and skeleton

Conversation: same conversation as S0.

状态：complete。权威记录：[P3-R4-S0 §17](p3-r4-s0-entry-and-budget-freeze.md#17-s1-public-ruleset-contract-and-skeleton-record)。S2 complete。

Objective: expand the minimal R3 injection surface into a stable R4 public contract without
implementing projection algorithms.

Required public concepts:

- TableRuleSelector exact/regex representation with canonical serialization;
- static role and compare key mode;
- ignored columns, artifact scope, position/stable-key metadata;
- storage policy (including mandatory ignored-column drops), storage key policy, ordered policy and explicit keyless policy;
- immutable TableRulesetSnapshot with ruleset_id, ruleset_version, ruleset_digest and contract version;
- LegacyRuleDecision and StorageRuleView;
- ProjectionRequest, ProjectionResult, ProjectionTable, ProjectionDiagnostic;
- CanonicalizationManifest and RepositoryImportArtifactInput public types or owner ports;
- typed failure/status categories for unsupported, key, row-integrity, digest, binding and publication
  failures.

Required behavior:

- canonical identifiers and selector serialization are deterministic;
- unknown fields, duplicate selectors, invalid precedence and malformed ruleset documents fail closed;
- an ignored key/ordered/required structural column fails ruleset validation;
- snapshot verifies matching ruleset identity and storage_projection_version;
- public types contain no host path, SQL text, provider-private object or mutable registry;
- downstream imports target contracts/public package only.

Tests/checks: contract construction and malformed parameter tables, ruleset digest stability,
selector serialization, architecture/import checks, ruff/mypy, git diff --check. No Dolt.

Exit: S2 can implement parity without inventing fields; S3 can consume only public StorageRuleView.

### S2 — Legacy rule-resolution parity provider

Conversation: new implementation conversation.

状态：complete。权威记录：[P3-R4-S0 §18](p3-r4-s0-entry-and-budget-freeze.md#18-s2-legacy-rule-resolution-parity-provider-record)。S3 complete。

Objective: implement a vNext immutable registry/provider whose valid outputs match the legacy
reference registry.

Required behavior:

- implement exact and regex selectors;
- preserve precedence SKIP > SNAPSHOT_ONLY > BROWSE_ONLY > ORDERED_DIFF > STANDARD_DIFF;
- implement explicit rules for composite_signal_point, net_cfg, device point tables, device_cfg,
  com_cfg, pointref_forwardtbl, scdmod_para, app_cfg and rdb_cfg;
- implement protocol option cfg and protocol device cfg patterns;
- implement raw-primary-key fallback;
- preserve ignored columns, artifact scopes, position column and stable-key candidates;
- emit storage projection metadata that maps every ignored column to `DROP_FROM_STORAGE` without
  mutating the parity-facing LegacyRuleDecision;
- preserve version_manager identity exception;
- reject incompatible selector collisions rather than choosing by insertion order;
- produce immutable snapshot and deterministic ruleset digest;
- never import legacy code in production.

Tests:

- one parameterized parity table for every exact, regex and fallback category;
- selector precedence and overlap cases;
- compare key mode/key columns;
- ignored column and artifact scope preservation;
- ignored-column-to-storage-drop mapping and key/ordered conflict rejection;
- ordered family classification;
- default/fallback behavior for unknown table names;
- ruleset serialization/digest property cases;
- legacy reference oracle tests run only in test support, not production imports.

Exit: complete LegacyRuleDecision parity with no unclassified legacy baseline row; S3 may proceed
in the same implementation context.

### S3 — Canonical storage projection core

Conversation: same implementation conversation as S2.

状态：complete。权威记录：[P3-R4-S0 §19](p3-r4-s0-entry-and-budget-freeze.md#19-s3-canonical-storage-projection-core-record)。S4 complete。

Objective: derive StorageRuleView and project ordinary tables into canonical schema/key/rows.

Required behavior:

- bind complete SnapshotTableArtifact/reader, source artifact digest, immutable ruleset snapshot and
  storage projection version;
- apply explicit storage key, then DDL primary key, then explicit keyless policy;
- exclude every legacy ignored column from retained canonical columns and canonical schema;
- publish the resolved canonical key as physical storage authority; source DDL primary-key changes
  are not silently substituted after a canonical key has been established;
- validate retained key columns, non-null/empty key values, duplicate keys and row count;
- retain every non-ignored source column by default for migrated legacy rules;
- record `legacy_ignored_column:<selector>` for every dropped ignored column in the manifest;
- fail closed when an ignored column is required by the effective key or ordered structure;
- publish canonical effective key and retained/dropped column sets as structural authority in the
  manifest and RepositoryImportArtifactInput; do not leave them as comparison-only hints;
- preserve descriptor DDL order and canonical identifier semantics;
- reject degraded/unsupported/failed tables at publication boundary;
- produce deterministic projected rows and canonical schema digest;
- expose table-level diagnostics without publishing partial Repository closure.

Tests:

- ordinary keyed table with explicit key and DDL fallback;
- source DDL primary-key change versus canonical-key stability, plus explicit canonical-key migration
  classification;
- missing/duplicate/null/empty key;
- row loss, duplicate rows and input reorder;
- ignored column absent from canonical storage with manifest reason;
- source-only change in a dropped column yields unchanged R4 canonical content/storage-business
  digest while preserving any changed R3 source/provenance digest;
- ignored key/ordered structural conflict;
- unknown/unclassified table fail-closed;
- schema/type/nullability mismatch;
- requested table selection and missing requested table;
- cancellation/deadline/I/O before publication;
- no SQL execution, no Dolt and no host path.

Exit: ordinary keyed and explicit policy paths are deterministic and atomic; S4 may independently
extend the same public result without changing S2 rule semantics.

### S4 — Ordered/keyless and digest integrity

Conversation: new implementation/integrity conversation.

状态：complete。权威记录：[P3-R4-S0 §20](p3-r4-s0-entry-and-budget-freeze.md#20-s4-ordered-keyless-and-digest-integrity-record)。S5 complete。

Objective: close high-risk ordered identity, keyless multiset, canonical content and ordering digest
semantics.

Required behavior:

- explicit keyless/multiset rules only, preserving duplicate rows and row count;
- no surrogate key or last-write-wins;
- ordered gid/no validation and deterministic pseudo gid allocation;
- real/pseudo range and forbidden values;
- positive unique continuous no;
- no retained as structural column and excluded from ordinary business modified content;
- schema digest includes normalized type, nullability and canonical key order;
- content digest uses retained R4 canonical cells in DDL order; dropped ignored columns are not
  part of canonical content; ENUM/SET follows ADR 0013;
- source-only changes to dropped ignored columns leave R4 canonical schema/content/storage-business
  digest unchanged, while a ruleset drop/restore change is STORAGE_BREAKING; R3 source/business
  digest remains a distinct provenance fact;
- ordering digest includes ordered identity policy and canonical no/gid facts;
- input row order independence applies only to contracts that require it;
- source/package compression metadata does not enter semantic digest;
- digest mismatch fails before publication.

Tests:

- keyless duplicate/order invariance;
- ordered real gid, pseudo allocation, reserved range, duplicate/missing/non-continuous no;
- position reorder and row content change;
- null/empty/zero gid;
- schema/key/nullable/type changes;
- ENUM/SET/null/empty-set digest vectors;
- manifest child digest and outer digest determinism;
- malformed scalar and unsupported type parameter tables;
- cancellation, output write failure and digest validation failure.

If a digest rule needs to change R3 ownership or shared encoding, stop and reopen the owner; do not
add a second digest implementation.

Exit: canonical schema/content/ordering facts are exact, bounded and independently testable.

### S5 — Manifest, RepositoryImportArtifactInput and atomic publication

Conversation: new artifact/integrity conversation.

状态：complete。权威记录：[P3-R4-S0 §21](p3-r4-s0-entry-and-budget-freeze.md#21-s5-manifest-import-input-and-atomic-publication-record)。S6 focused review complete。

Objective: publish the durable Backend manifest and Repository structural input without crossing into
Repository effect or R7 replay generation.

Required behavior:

- assemble complete CanonicalizationManifest with ruleset/storage/source bindings;
- record source/canonical schema and row counts, retained/structural/dropped columns and reasons,
  canonical key, content/ordering digests and ordered gid facts;
- record every legacy ignored column as a dropped column with
  `legacy_ignored_column:<selector>` reason; do not publish it in canonical schema or rows;
- compute manifest digest using JCS and the domain-separated manifest prefix;
- build immutable RepositoryImportArtifactInput with minimal structural manifest and opaque manifest
  digest binding;
- validate package safety, exact entry names, UTF-8 manifest, bounded manifest/replay sizes and raw
  transport identity;
- write to staging, validate descriptor/schema/content/manifest, then atomically publish;
- fail closed on missing/corrupt/mismatched rows, manifest or refs;
- never generate or execute replay SQL; replay generation is R7;
- preserve source/ref rebuild route on cache miss.

Tests:

- manifest round-trip and JCS property cases;
- canonical key/retained/dropped column authority survives manifest-to-import-input round-trip;
- structural package shape, duplicate/unknown entry, traversal/link/device/size rejection;
- manifest digest mismatch, row count/schema/content mismatch;
- partial write, cancellation, deadline, I/O and atomic replace failures;
- opaque ArtifactRef and raw SHA identity;
- package reproducibility independent of mtime/host path;
- no Repository process and no Dolt.

Exit: complete canonical artifact closure is publishable; incomplete closure is unpublishable.

### S6 — Focused contract/resource/security review

Conversation: new focused review conversation.

状态：complete。权威记录：[P3-R4-S6](p3-r4-s6-focused-review.md)。S7 已完成，权威记录：[P3-R4-S7](p3-r4-s7-independent-review.md)。S8 module gate complete。

Review inputs: S0 matrix, S1 contracts, S2-S5 diff, fixtures, exact test output, resource budget,
legacy oracle comparison and deferred register.

Review focus:

- every legacy selector/rule/fallback has a matrix row and parity fixture;
- selector precedence/conflict behavior;
- version_id/version/digest and storage projection binding;
- every ignored column is a storage drop, while UPDATE_ONLY remains artifact/comparison scope;
- dropped-column source changes are canonical no-change, and drop/restore ruleset changes are
  STORAGE_BREAKING;
- SKIP/snapshot-only/browse-only/version_manager mapping;
- explicit key/keyless/ordered row integrity;
- ignored key/ordered/required structural conflicts fail closed;
- gid/no/pseudo allocation and digest semantics;
- manifest/package safety and atomic publication;
- partial/failure/cancel/timeout/I/O cleanup;
- R3 private import, Repository/HTTP/application dependency and SQL execution;
- test marker correctness and no unnecessary Dolt/integration fixture.

Exit: findings register complete; no unclassified P1/P2, contract ambiguity, hidden dependency,
unbounded path or unsafe publication. Remediation returns to S2-S5 and then back to this review.

### S7 — Independent owner/import/digest/recovery review

Conversation: new independent review conversation.

状态：complete。权威记录：[P3-R4-S7](p3-r4-s7-independent-review.md)。S7 PASS；无未处理
P1/P2 finding；S8 module gate complete。

The reviewer receives the plan, design baseline, normative contracts, S0 matrix, cumulative diff,
fixtures and exact commands, but not implementer explanations.

Minimum checks:

~~~text
cd vnext/backend && uv run pytest -m unit
cd vnext/backend && uv run ruff check . && uv run mypy
git diff --check
~~~

Also run focused nodeids for:

- legacy parity matrix and selector conflicts;
- storage key/row-integrity and explicit unsupported cases;
- ordered/keyless/gid/no vectors;
- canonicalization manifest and import input;
- artifact atomic publication and corrupt/missing closure;
- architecture/forbidden imports.

If any fixed event/thread/stream timeout is introduced, mark the exact test serial and run the
required serial nodeid with -n 0. If a real Repository/Dolt test is introduced, mark integration
and run its exact nodeid; pure projection tests must remain unit-only.

Exit: independent pass; no unclosed P1/P2, contract ambiguity, digest mismatch, wrong marker,
unbounded path, import cycle or hidden Repository/application dependency.

### S8 — R4 module gate and R5 handoff

Conversation: new acceptance/documentation conversation.

状态：complete。权威记录：[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)。R4 gate pass；`p3_r5_ready: yes`；`p3_implementation_authorized: no`。

Required record:

- tested source tip and commit lineage;
- changed paths and fixture roots;
- complete legacy matrix revision and parity result;
- exact commands/results and environment notes;
- S6/S7 findings closure;
- ruleset/storage projection version and digest identity;
- known limitations and deferred/reopen register;
- container rebuild decision and provenance;
- R5 input contract and implementation authorization status.

R4 gate commands are the focused unit suite, full backend unit suite, ruff, mypy and diff check
appropriate to the final changed surface. No container rebuild is required for pure Python,
fixtures and docs; it becomes mandatory if Dockerfile, lock, entrypoint, Compose, environment,
UID/GID, volume, socket, healthcheck or container-only runtime boundaries are touched, or if the
final candidate claims container validation.

R4 exit requires:

- complete legacy rule matrix and valid behavior parity;
- every legacy ignored column is a canonical `DROP_FROM_STORAGE` with manifest reason and is absent
  from Repository structural schema/rows;
- stable public Snapshot/Artifact input binding;
- complete canonical storage projection and manifest/import input;
- no partial canonical publication;
- deterministic key/schema/content/ordering/manifest digests;
- focused and independent review pass;
- no unlisted capability or production integration;
- R5 can consume only R4 public projection/artifact contracts.

## 7. Deferred register and reopen conditions

| ID | Deferred item | Earliest owner | Guard before use |
| --- | --- | --- | --- |
| R4-D01 | Repository Service/Dolt production adapter and commit/readback write | Repository/P5B | public structural input, exact integration nodeids |
| R4-D02 | protected hidden ruleset metadata commit integration | Repository/P5B | ADR 0015 metadata contract and atomic commit evidence |
| R4-D03 | retention, pinning, eviction, quota, durable operation ownership | P4/P5 | lifecycle contract and cleanup evidence |
| R4-D04 | mutation plan, ADAPTIVE_PATCH and replay renderer | P3-R7 | target-neutral ChangeSet contract and renderer tests |
| R4-D05 | Rust storage provider/automatic fallback | P6+ | Python oracle, accepted profile and differential fixtures |
| R4-D06 | online ruleset watcher and migration executor | future P4/P5 | activation/migration contract and durable operation |
| R4-D07 | formal TAR_ZST SourcePackage admission | future SourcePackage/HTTP owner | real consumer or measured deployment need |
| R4-D08 | comparison projection/display/risk semantics beyond LegacyRuleDecision | P3-R5/R6 | downstream owner contract; no R4 storage inference |

Reopen R4 before the next gate if:

- any legacy registry row lacks owner, consumer, fixture, implementation step or guard;
- selector precedence or overlap is ambiguous;
- an ignored column is retained, omitted from the manifest, or used as key/ordered structure;
- non-ignored comparison-only metadata is proposed as storage drop without explicit evidence;
- a SKIP/snapshot-only/browse-only exception is handled by an undocumented default;
- keyless/ordered invariants cannot be proved;
- R4 duplicates R3 digest logic or imports R3 private modules;
- partial/corrupt artifact can be promoted;
- Repository/HTTP/application/SQL execution enters the capability;
- a new source/package format or security principal is proposed.

## 8. R5 entry prerequisites

R5 may start only after R4 handoff records:

- public canonical storage projection and table reader/artifact boundary;
- immutable CanonicalizationManifest and manifest digest;
- canonical schema/key/row/content/ordering facts;
- explicit storage projection/ruleset/source bindings;
- complete/failed publication semantics and cache miss rebuild route;
- no dependency on R4 private modules;
- deferred register and exact R5 guard conditions;
- R4 implementation authorization and tested tip.

R4 does not authorize R5 implementation or any application integration.

## 9. S8 module gate record

状态：**PASS**；handoff: [P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)。

原 S8 confirmatory rerun 针对 `f07c387f513ee735fe69e65c94804d7c63115f0d` 加 dirty R4
worktree（2026-08-20），实现随后封存为 `4effb6eefa16d246e75213212f884b2546e6d6ef`；
当前 sealed HEAD 的复核结果见 handoff：

| Command | Result |
| --- | --- |
| 原 S8：`cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -m unit`（`f07c387` + dirty R4 worktree） | **609 passed**（2.36s）；1 pre-existing Starlette deprecation warning；历史 gate 证据 |
| 当前 sealed HEAD：`cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit tests/test_architecture.py tests/test_table_rules_*.py tests/test_storage_projection_*.py tests/test_repository_import_artifact_*.py tests/test_canonicalization_manifest.py` | **268 passed**（1.47s） |
| 当前 sealed HEAD：`cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check . && uv run --offline mypy` | **passed**；mypy 139 source files |
| 当前 sealed HEAD：`cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache timeout 60s uv run --offline pytest -q -m unit` | **未完成（exit 124）**；停在既有 `tests/test_app.py::test_healthz_uses_injected_settings`，无断言失败输出 |
| 当前文档修正工作树：`git diff --check` | **passed** |

No serial nodeid, Dolt, or container rebuild. S6-001–003 remain closed. `S6-004`
and `R4-D01`–`R4-D08` are carried forward. `R3-D04` is closed by R4.
`p3_r4_exit: pass`；`p3_r5_ready: yes`；`p3_implementation_authorized: no`。
R5 必须先写详细计划再实现。当前 sealed HEAD 的全量 unit 独立复跑在既有
`tests/test_app.py::test_healthz_uses_injected_settings` 处 60 秒超时；历史 S8 的
609-pass 仍保留为 gate 证据，但不冒充本次 sealed HEAD 的新全量复跑结果。

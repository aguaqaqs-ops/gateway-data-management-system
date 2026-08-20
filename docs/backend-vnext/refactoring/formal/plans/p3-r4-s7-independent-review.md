# P3-R4 S7 Independent Owner, Import, Digest and Recovery Review

状态：**S7 complete；independent review PASS；无未处理 P1/P2 finding**

日期：2026-08-19

reviewed source tip：`f07c387f513ee735fe69e65c94804d7c63115f0d` plus the existing dirty
worktree changes; this review adds this S7 record and the corresponding documentation status/index updates.

本审核独立重读 R4 design baseline、S0 legacy matrix/budget freeze、S6 findings closure、
normative canonical-storage/repository and shared-encoding contracts、累计 diff、fixture
corpus 和 capability import graph。不依赖实现者口头解释，也不重复 S6 的修复推理。

## 1. Review boundary

本轮独立覆盖：

- complete legacy selector matrix、precedence/conflict behavior、LegacyRuleDecision 与
  StorageRuleView owner split、SKIP/snapshot-only/browse-only/version_manager 和 raw-PK
  fallback parity；
- ignored-column 到 `DROP_FROM_STORAGE` 的 manifest reason、UPDATE_ONLY comparison scope、
  canonical key/schema authority、keyless/multiset 和 keyed row-integrity closure；
- ordered `gid/no` real/pseudo ranges、pseudo allocation、no continuity/uniqueness、
  structural ordering ownership 与 digest behavior；
- R3 source/snapshot digest separation、R4 schema/content/ordering/storage/manifest digest
  ownership、JCS preimage and deterministic table/row ordering；
- durable CanonicalizationManifest、minimal Repository import input、opaque manifest binding、
  exact two-entry USTAR package、UTF-8/size/path/link/device/duplicate/unknown-field safety；
- staging write/readback validation、atomic publication, cancellation/deadline/reader/I/O
  failure, corrupt/missing ref and cache-miss rebuild behavior；
- forbidden imports/paths, SQL/shell/Repository/HTTP/application boundaries and pytest marker
  classification.

未纳入真实 Repository Service/Dolt adapter、HTTP/Workspace/Submit/Operation Runtime、R7
replay generation、retention/eviction/quota、online activation、Rust provider 或
Docker/Compose/image boundary；本轮不声称这些能力。

## 2. Independent evidence

| Check | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit` | **609 passed** (2.18s; one existing Starlette deprecation warning) |
| exact R4 parity/projection/integrity/publication/package/architecture suite | **262 passed** (1.42s) |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed**; 139 source files |
| `git diff --check` | **passed** |
| forbidden import/path and capability-DAG scan | **passed**; storage_projection depends only on table_rules and snapshot_materialization; no Repository/Dolt/HTTP/application/SQL/shell/legacy production dependency |
| marker/timeout scan over R4 tests | **passed**; no integration/serial marker or fixed process/stream timeout introduced |

The focused nodeids cover the migrated legacy parity table and selector collisions, explicit
key/keyless/row-integrity blockers, ordered gid/no vectors, schema/content/ordering/manifest
digests, manifest/package safety, corrupt/missing refs, atomic publication failures and
architecture boundaries. All are pure unit tests using in-memory readers/stores and `tmp_path`;
no Dolt, Repository process or external process was started.

No Dockerfile, lockfile, Compose, entrypoint, environment, UID/GID, volume, socket, healthcheck
or container-only runtime boundary changed. Container rebuild is therefore not triggered by this
Python/test/doc-only review, and no container validation is claimed.

## 3. Independent findings register

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| — | — | No new implementation finding. S6-001 through S6-003 remain covered by the owning boundary and regression tests; S6-004 remains the explicitly deferred artifact lifecycle item. | Closed by current code/tests or deferred under `R4-D03` and ADR 0012; no new mechanism or scope introduced. |

No parity gap, selector ambiguity, ignored-column retention, UPDATE_ONLY storage leak, key/row
loss acceptance, ordered invariant failure, digest ownership duplication, partial/corrupt
publication, unbounded package extraction, unsafe archive member, import cycle, hidden
Repository/application dependency or incorrect marker was found.

## 4. Boundary dispositions

| Area | Result | Independent evidence |
| --- | --- | --- |
| Legacy parity and owner split | **Pass** | Parameterized migrated matrix/oracle cases and rank-based collision tests; storage view is derived explicitly from the immutable ruleset snapshot. |
| Storage key/columns/rows | **Pass** | Explicit key precedence, DDL fallback, keyless opt-in, duplicate/null/missing-key and row-count tests; ignored structural conflicts fail closed. |
| Ordered identity | **Pass** | Real/pseudo gid range checks, deterministic blank allocation, continuous unique `no`, reorder stability and position-shift digest cases. |
| Digest and import authority | **Pass** | R3 source digest remains separate; manifest JCS round-trip, schema/content/ordering checks and opaque manifest digest binding pass. |
| Package and publication recovery | **Pass** | Exact USTAR shape, UTF-8, size, traversal/link/device/duplicate/unknown-field rejection, staging readback, cancellation/deadline/I/O and missing/corrupt ref cases pass. |
| Scope/imports/markers | **Pass** | Architecture tests and source scans pass; no forbidden capability or runtime boundary entered. |

## 5. Decision and next authorization

**S7 PASS for the R4 implementation surface.** There is no unclosed P1/P2, contract ambiguity,
digest mismatch, unbounded path escape, import cycle, hidden Repository/application dependency or
incorrect marker in the reviewed tip. S6 is not reopened.

S8 remains the next authorized conversation. It must carry this record, the exact reviewed source
tip and dirty-path context, S6/S7 closure, the deferred/reopen register, ruleset/storage identity
and the no-container-rebuild decision. S7 does not authorize R5 implementation, production
Repository/Dolt integration, HTTP wiring, retention or any deferred item.

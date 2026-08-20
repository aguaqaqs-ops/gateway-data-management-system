# P3-R4 S6 Focused Contract, Resource and Security Review

状态：**S6 complete；无未处理 P1/P2 finding；S7 未执行**

日期：2026-08-19

reviewed source tip：`f07c387f513ee735fe69e65c94804d7c63115f0d` plus the existing dirty
worktree changes. 本轮审查新增 R4 reader-failure mapping、durable manifest size gate、
publication final checkpoint 及其回归测试；未依赖实现者口头解释。

## 1. Review boundary

本轮覆盖：

- S0 legacy matrix、S1 public ruleset identity、S2 selector parity/conflict、S3 keyed
  projection and ignored-column storage mapping；
- S4 explicit keyless/multiset、ordered `gid/no`、schema/content/ordering/manifest digest；
- S5 durable manifest、structural Repository import input、two-entry package safety、size
  gates、staging validation and fail-closed publication；
- cancellation/deadline/I/O/reader lifecycle failures、opaque artifact refs、forbidden
  imports/paths、SQL execution and Repository/HTTP/application boundaries；
- test marker classification and unnecessary Dolt/integration fixture use.

未纳入：真实 Repository Service/Dolt adapter、HTTP/Workspace/Submit/Operation Runtime、
retention/eviction/quota、online ruleset activation、R7 replay renderer、Rust provider 和
Docker/Compose/image boundary。

## 2. Evidence

| Check | Result |
| --- | --- |
| changed-surface R4 unit + architecture suite | **265 passed** before review remediation；final result recorded below |
| exact table-rules, projection core/integrity/publication, package and architecture suite | **268 passed** after remediation |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed**; 139 source files |
| `git diff --check` | **passed** |
| forbidden import/path scan | **passed** after removing the attempted direct `table_access` import; storage_projection DAG remains limited to `table_rules` and `snapshot_materialization` |

All reviewed tests are pure unit tests using in-memory readers/stores and `tmp_path`; no Dolt,
Repository process, shell/SQL execution or fixed process/stream timeout was introduced. No
`integration` or `serial -n 0` rerun is required. No Dockerfile, lockfile, Compose, entrypoint,
UID/GID, mount/socket, healthcheck or other container-only runtime boundary changed; container
rebuild is not triggered by this Python/test/doc-only review.

## 3. Findings register

| ID | Area / severity | Finding | Closure evidence |
| --- | --- | --- | --- |
| `S6-001` | Reader contract failure mapping / **P2** | `SnapshotTableReader.descriptor()` and `iter_rows()` may raise the public reader lifecycle/contract exception (or an I/O exception). Those exceptions previously escaped `project_storage()` instead of producing the required typed FAILED result. | `_bound_descriptor()` and `_iter_source_rows()` now map reader exceptions to `BINDING_INVALID`; `test_reader_contract_failure_does_not_escape_projection` and the existing I/O regression pass; readers are closed in the outer `finally`. |
| `S6-002` | Durable manifest resource gate / **P2** | The S5 durable manifest encoder did not enforce the frozen 16 MiB `manifest.json` limit; only the Repository structural package path had a size check. | `durable_manifest_bytes()` and durable manifest decode now reject over-budget bytes with `RESOURCE_LIMIT_EXCEEDED`; `test_durable_manifest_size_gate_applies_to_write_and_read` passes. |
| `S6-003` | Publication cancellation boundary / **P2** | Publication had checkpoints around writes but no final checkpoint after package validation and before returning a COMPLETE publication. A cancellation arriving in that window could still return success. | Final `_checkpoint(context)` is now executed after raw/package validation and before constructing the publication result; `test_cancellation_after_final_store_read_does_not_return_complete` passes. |
| `S6-004` | Multi-artifact orphan cleanup / accepted defer | If the second artifact write fails, the first opaque artifact can remain unreachable because `ArtifactStorePort` has no delete/transaction primitive. No incomplete manifest/package ref is returned and no public publication is produced. | Existing second-put failure test verifies fail-closed visibility. Durable orphan cleanup/retention remains `R4-D03` under ADR 0012; no broker, sidecar or new security principal is introduced. |

`S6-001` through `S6-003` were remediated in the owning R4 boundary and re-run in this review.
`S6-004` is explicitly classified as deferred lifecycle work, not a hidden publication or
security assumption. No parity gap, selector ambiguity, ignored-column retention, UPDATE_ONLY
scope leak, key/row-loss acceptance, ordered invariant failure, digest ownership violation,
partial public publication, unbounded package extraction, unsafe archive member, Repository/HTTP
dependency, SQL execution, import cycle or incorrect marker was found.

## 4. Boundary dispositions

| Area | Result | Evidence / disposition |
| --- | --- | --- |
| Legacy parity and precedence | **Pass** | Complete migrated matrix and legacy oracle fixtures cover SKIP, snapshot-only, browse-only, nine IEC104 ordered families, explicit rules, UPDATE_ONLY, protocol patterns, version_manager and raw-PK fallback; same-rank collisions fail closed. |
| Storage ownership | **Pass** | Every legacy ignored column is `DROP_FROM_STORAGE` with `legacy_ignored_column:<selector>`; ordered `no` is structural `RETAIN_FOR_STRUCTURE`; UPDATE_ONLY remains artifact/comparison scope. |
| Key/row/ordered integrity | **Pass** | Explicit key/keyless/ordered paths reject missing/null/empty/duplicate keys, row loss, reserved gid, duplicate/non-continuous `no`; no surrogate or last-write-wins. |
| Digest and binding | **Pass** | R3 source digest remains separate; R4 owns schema/content/ordering/manifest digests; manifest and import input bind exact ruleset/storage/source identities and opaque manifest digest. |
| Package and publication security | **Pass** | Exact two regular USTAR entries, UTF-8 manifest, duplicate/unknown JSON rejection, traversal/link/device/PAX rejection, 16/200 MiB limits, staging validation and no public ref on failure. |
| Recovery/runtime | **Pass with deferred lifecycle** | cancel/deadline checkpoints, reader close, I/O failure and corrupt/missing refs fail closed; orphan cleanup is explicitly R4-D03/ADR 0012. |
| Scope/imports/markers | **Pass** | Capability DAG and forbidden scans pass; no R3 private import, Repository/Dolt/HTTP/application dependency, SQL/shell execution or unapproved integration/serial marker. |

## 5. Deferred and reopen register

S0/R4 deferred items remain unchanged: Repository/Dolt production effect and hidden metadata
commit, retention/eviction/quota and durable operation ownership, R7 mutation/replay generation,
Rust provider/automatic fallback, online activation/migration, formal TAR_ZST admission and
comparison semantics beyond `LegacyRuleDecision`.

Reopen R4 before S7/S8 if a deferred item is promoted, a source/table budget is revised, an
ignored or structural column is retained/dropped contrary to the frozen derivation, a partial or
corrupt artifact becomes publicly visible, a reader can expose incomplete rows as ready, R3
private digest code is imported, or Repository/HTTP/application/SQL execution enters the owner.

## 6. Decision

**S6 PASS.** Findings register is complete; no unclassified P1/P2 finding or contract ambiguity
remains. S7 independent review is the next authorized conversation. This record does not claim
S7, the R4 module gate, container validation, production Repository/Dolt integration, or any
deferred capability authorization.

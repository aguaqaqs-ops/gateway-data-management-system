# P3-R3 S6 Focused Contract, Resource and Security Review

状态：**S6 complete；无未处理 P1/P2 finding；S7 未执行**

日期：2026-08-19

本审核依据 P3-R3 S0 freeze、S1-S5 implementation/test surface、SourcePackage/Snapshot/
SnapshotTableAccess/Artifact contracts、ADR 0012、fixture corpus 和下列可重现命令。
审核不依赖实现者口头解释。当前 worktree 是 dirty、尚未提交，因此本记录以当前 source
tree 为 reviewed tip，不伪造 commit SHA。

## 1. Review boundary

本轮覆盖：

- SourcePackage normalized path、archive member、symlink/hardlink、canonical collision、
  TAR_GZ/ZIP/document budget 和 zstd internal-only transport；
- SQL Snapshot ruleset injection、keyless/duplicate preservation、row-order-independent
  digest、PARTIAL/FAILED 和 reader commit-point；
- composite XML failure atomicity、hidden FINAL summary authority、RepositoryRef pinned
  session/read-only close；
- SnapshotTableArtifact manifest + Parquet validation、cache trust promotion、opaque refs；
- architecture/import boundary、forbidden dependency/path、pytest marker classification。

未纳入：真实 Repository Service/Dolt adapter、HTTP/Workspace/Submit/Operation Runtime、
retention/eviction/quota、durable takeover/checkpoint、Docker/Compose/image boundary。

## 2. Evidence

| Check | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit` | **372 passed**; 1 pre-existing Starlette deprecation warning |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_source_package_*.py tests/test_snapshot_materialization_*.py tests/test_repository_ref_materialization_*.py tests/test_snapshot_artifact_*.py tests/test_composite_signal_*.py` | **170 passed** (1.23s) |
| `cd vnext/backend && uv run pytest -m unit tests/test_source_package_*.py` | **35 passed** (0.47s) |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed**; 121 source files |
| `git diff --check` | **passed** |
| forbidden import/path scan over R3 capability roots | **passed**; no Dolt, Repository Service, HTTP/application, subprocess, host path or external XML resolver |

All R3 tests are pure unit tests using in-memory/local artifact stores and `tmp_path`; no Dolt,
fixed process/stream timeout, or thread/event budget was added. Therefore no `integration` or
`serial -n 0` rerun is required. No Dockerfile, lockfile, Compose, entrypoint, UID/GID,
mount/socket, healthcheck or other container-only runtime boundary changed; container rebuild is
deferred to the S7/final candidate if such a boundary is introduced.

## 3. Findings register

| ID | Area / severity | Finding | Closure evidence |
| --- | --- | --- | --- |
| `S6-001` | ZIP/TAR document extraction / **P1** | Materialized ZIP members and TAR documents were read without an incremental SQL/XML document limit; a document could consume substantially more memory than its document budget before rejection. | `_read_bounded(..., limit=...)` is now used for both archive formats; the ZIP SQL-over-budget parameter case passes and the expanded-budget counter remains bounded. |
| `S6-002` | SourcePackage artifact failure mapping / **P2** | `ArtifactStorePort.put()` verification failures escaped `stage_source_package()` instead of producing the required result-level `FAILED` without public refs. | `ARTIFACT_PUBLISH_FAILED` diagnostic added; injected store failure regression passes and result publishes no refs. |
| `S6-003` | SourcePackage cancel/deadline boundary / **P2** | SourcePackage staging checked cancel/deadline only at entry, so a request could continue across archive entries or artifact writes after cancellation. | Entry and each artifact-write boundary now checkpoint; deterministic cancellation regression passes. |
| `S6-004` | SourcePackage multi-artifact cleanup / accepted defer | A failure after an earlier opaque artifact write can leave an unreachable L3 object because the existing artifact port has no delete/transaction primitive. No incomplete manifest or public ref is returned. | Existing artifact contract and fault tests verify fail-closed publication. Durable orphan cleanup/retention remains `R3-D03` under ADR 0012; no new broker or security mechanism is introduced. |

`S6-001` through `S6-003` were remediated in the owning SourcePackage staging boundary and re-run in
this review. `S6-004` is explicitly classified as deferred lifecycle work, not a hidden security
assumption. No contract ambiguity, unbounded path, digest/order regression, hidden-summary
reconstruction, partial business publication, trust-level self-promotion, import cycle, or
incorrect marker was found.

## 4. Boundary dispositions

| Area | Result | Evidence / disposition |
| --- | --- | --- |
| Package path/archive/security | **Pass** | normalized paths reject traversal, host-shaped paths, NUL/backslash, empty segments, canonical collisions and symlink/hardlink/non-regular members; `TAR_ZST` remains refused. |
| Resource budgets | **Pass** | compressed ingress, expanded bytes, entry count, normalized path, SQL/XML document and diagnostic limits are enforced; document streams now fail at the document budget boundary. |
| Snapshot semantics | **Pass** | ruleset/version is explicit and immutable; keyless and duplicate rows are preserved; canonical multiset digests preserve duplicate multiplicity and ignore source row order where required. |
| Composite business failure | **Pass** | malformed/security/unknown XML and catalog invariant failures return FAILED and never publish `composite_signal_point`. |
| RepositoryRef authority | **Pass** | session pins an immutable commit, validates hidden FINAL summary/version/digests against catalog and rows, and never reconstructs missing hidden summary from catalog data. |
| Artifact/cache integrity | **Pass** | manifest and Parquet schema/row-count/raw digest are revalidated; cache promotion requires matching repository authority; consumers receive opaque `ArtifactRef`. |
| Scope/imports | **Pass** | R3 capability DAG remains contracts-only across capability boundaries; no Repository write, SQL execution, HTTP/application, host path, shell or external XML resource exists. |

## 5. Deferred and reopen register

The S0 deferred register is unchanged: `R3-D01` formal TAR_ZST admission, `R3-D02` production
Repository Service/Dolt adapter/readback, `R3-D03` retention/eviction/quota/durable artifact
lifecycle, `R3-D04` storage projection/import package, `R3-D05` projection cache/export matrix,
`R3-D06` Rust/automatic fallback, and `R3-D07` durable cancellation/takeover remain outside S6.

Reopen R3 before S7/S8 if a deferred item is promoted, document/package ownership changes,
artifact publication becomes externally visible before manifest validation, a reader exposes
partial rows as ready, hidden summary is reconstructed after mismatch, or any Repository/HTTP/
application dependency enters an R3 capability.

## 6. Decision

**S6 PASS.** Findings register is complete; no unclassified P1/P2 finding or contract ambiguity
remains. S7 independent review is the next authorized conversation. This record does not claim
S7, the R3 module gate, container validation, production Repository/Dolt integration, or new
capability authorization.

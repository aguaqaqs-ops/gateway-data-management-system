# P3-R3 S7 Independent Owner, Import, Digest and Recovery Review

状态：**S7 complete；implementation review PASS；无未处理 P1/P2 finding**

日期：2026-08-19

reviewed source tip：`3c142f8e7616fb4cc2594a61128b2ccce494dd46` plus the existing dirty
worktree changes; this review added only this S7 record and the plan status update.

本审核以当前 dirty source tree 为 reviewed tip，独立重读 R3 public contracts、S0
预算冻结、S6 findings closure、累计 diff、fixture corpus 和 capability import graph。
不依赖实现者口头解释，也不重做 S6 的修复推理。

## 1. Review boundary

本轮独立覆盖：

- SourcePackage package/path/archive/symlink、zstd internal transport、entry/document
  digest 和 fail-closed publication；
- SQL/XML materialization oracle、ruleset injection、duplicate/keyless/NULL、digest
  determinism、partial/failure atomicity；
- protocol-conformant RepositoryRef fake、pinned commit、hidden FINAL summary authority、
  requested-table filtering、reader close and row digest validation；
- SnapshotTableArtifact Parquet round-trip、corrupt/mismatch rejection、cache trust
  revalidation/promotion 和 opaque refs；
- cancellation/timeout checkpoints、artifact atomic publish、forbidden import/path scan
  和 pytest marker classification。

未纳入真实 Repository Service/Dolt adapter、HTTP/Workspace/Submit/Operation Runtime、
durable artifact retention/takeover 和 Docker/Compose boundary；本轮没有声称这些能力。

## 2. Independent evidence

| Check | Result |
| --- | --- |
| changed-surface unit/architecture/artifact/provider/composite suite | **170 passed** (1.32s) |
| exact security/digest/hidden-summary/artifact fault subset | **61 passed** (0.68s) |
| all backend unit tests except pre-existing HTTP smoke test | **371 passed** (1.63s) |
| `ruff check .` | **passed** |
| `mypy` | **passed**; 121 source files |
| `git diff --check` | **passed** |
| forbidden import/path scan over R3 roots | **passed**; no Dolt, Repository Service, HTTP/application, subprocess, host path, SQL execution or external XML resolver |
| test marker scan | **passed**; R3 tests use the default `unit` classification and add no unapproved `integration`/`serial` marker |

The pytest `uv` invocations were run with `UV_CACHE_DIR=/tmp/gateway-data-uv-cache` and
`--offline` because the default `/root/.cache/uv` is read-only in this environment; ruff
and mypy used the same writable cache override.
The full `pytest -m unit` invocation was also attempted directly. The unchanged
`tests/test_app.py::test_healthz_uses_injected_settings` hangs inside Starlette's
`TestClient` request (reproduced with a 20-second timeout); its file and its application
code are outside this R3 diff. It is recorded as a verification-environment limitation,
not as an implementation pass or an R3 finding. S8 must rerun that baseline when the
HTTP test environment is repaired.

No test in this R3 surface creates Dolt, starts a subprocess, relies on fixed stream/process
timeouts, or writes durable state outside `tmp_path`; no `integration` or `serial -n 0`
rerun is therefore claimed. No image/deployment/container boundary changed.

## 3. Independent findings register

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| — | — | No implementation finding. S6-001 through S6-003 remain covered by the owning boundary and regression parameters; S6-004 remains the explicitly deferred artifact lifecycle item. | Closed by existing code/tests or deferred under R3-D03; no new mechanism or scope was introduced. |

The HTTP smoke-test hang is `S7-V01` verification debt only: it is not caused by the R3
changed paths, does not weaken the capability contract evidence above, and must not be
reported as a successful full-suite run.

## 4. Boundary dispositions

| Area | Result | Independent evidence |
| --- | --- | --- |
| Package security and bounded extraction | **Pass** | parameterized traversal/collision/link/non-regular/TAR_ZST/size cases; valid ZIP/TAR_GZ/DIRECTORY/SQL helper paths |
| SQL/XML oracle and identity | **Pass** | golden SQL cases, XML AST/bind cases, composition failure atomicity, duplicate/keyless/NULL and order/multiplicity digest tests |
| RepositoryRef authority | **Pass** | fake provider protocol matrix, pinned commit/catalog checks, hidden summary missing/corrupt/version/digest mismatch cases, close/read failure cases |
| Artifact/cache integrity | **Pass** | Parquet round-trip, manifest/schema/row/digest corruption, cache revalidation and explicit authority promotion tests |
| Cancellation and publication | **Pass** | entry/stream checkpoints, timeout/cancel result closure, no reader/artifact publication on failure, manifest validation before return |
| Scope/import/markers | **Pass** | architecture tests plus independent forbidden dependency scan; all R3 tests classified as unit |

## 5. Decision and next authorization

**S7 PASS for the R3 implementation surface.** There is no unclosed P1/P2, contract
ambiguity, unbounded host/path escape, import cycle, hidden Repository/application dependency,
or incorrect marker in the reviewed tip. S6 is not reopened.

S8 remains the next authorized conversation. It must carry this record, the exact current
source tip and dirty-path list, the `S7-V01` full-unit verification limitation, the deferred
register, and the decision that no container rebuild was triggered by this Python/test/doc-only
review. S7 does not authorize R4 implementation, production Repository/Dolt integration,
HTTP wiring, retention, or any deferred item.

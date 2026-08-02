# P2-R1 Runtime and Provider Feasibility Decision

## Decision

| Field | Result |
|---|---|
| Round | `P2-R1` |
| Selected provider | `null` |
| Round exit | `no-go` |
| Next round ready | `no` |
| Raw records | `60` |

The two candidates completed the full deterministic matrix, but neither passed
all hard gates. This report is a feasibility result only. It is not a
production SLO, and the synthetic workloads must not be used to infer real
business-data deduplication or import behavior.

The exact target Dockerfile image was subsequently built from the retained
dependency-base image and completed the same 60-record matrix on a real named
volume. The target-image raw records and summary are preserved alongside this
report; the provider decision remains `no-go` because both candidates still
fail the bounded-stream gate.

## Meaning of this `no-go`

This `no-go` is scoped to the current development-equivalent measurement
environment. It means that the implementation, with the tested Candidate A/B
paths and the tested resource/filesystem profile, has not yet earned permission
to enter P2-R2 under the formal gates. It does not mean that either provider is
proven impossible in the final production environment, and it does not select
an alternative provider.

The final production runtime is expected to have stronger compute and I/O
capacity than this development environment. Faster CPUs, more available memory
and higher-throughput storage may reduce import duration, improve rows/second
and move the capacity projection above its threshold. Those gains are not
assumed by this report: they must be demonstrated by repeating the same matrix
with the production-equivalent CPU, memory limit, filesystem and volume
backend. A stronger machine also cannot by itself waive the bounded-stream
memory rule, correctness checks, cancellation cleanup, or the target-image
smoke requirement.

In particular, the failed results mean:

- Candidate A and B both failed the tested bounded-stream rule. The W2 RSS
  increase was too large relative to W1, so this run did not demonstrate that
  memory remains bounded as workload size grows. This is a failed feasibility
  observation, not a claim that production memory will necessarily grow in the
  same way; the implementation and the production-equivalent runtime both need
  to be re-measured.
- Both candidates cleared the current W1 capacity projection gate in the
  target-image run. This is a calculation from measured W1 timings and the
  duty-cycle rule, not a production SLO or a forecast that production will
  remain above the threshold.

Accordingly, the actionable conclusion is: keep the round at `no-go`, do not
start P2-R2 from this evidence, and repeat the gates after either improving the
streaming/memory behavior or running the unchanged probe on a production-like
host. A `go` decision requires the formal gates to pass in that re-run; stronger
production hardware is a reason to re-test, not an automatic waiver.

## Matrix result

The matrix was run as one warm-up plus five measured samples for each of W0,
W1, W2, W3-1% and W3-10%, for both candidates. Correctness, restart,
cancellation cleanup, pinned revision reads, catalog checks, marker parent and
marker uniqueness checks passed for every completed sample.

| Candidate | W1 max import | Capacity projection | 60-minute safety | Incremental storage | Bounded stream | Hard gate |
|---|---:|---:|---:|---:|---:|---:|
| A offline CLI | 81.26 s | 2977.16/day | pass | pass | fail | fail |
| B sql-server | 219.11 s | 1104.12/day | pass | pass | fail | fail |

The capacity projection uses the formal feasibility formula with a 70% duty
cycle. It is deliberately reported only as a projection.

### Failed gates

- Candidate A W1 measured stream RSS delta peaked at `181288 KiB`; W2 peaked
  at `607024 KiB`. The bounded-stream rule permits at most twice the W1 peak
  (or 64 MiB, whichever is larger), so A fails this gate.
- Candidate B W1 measured stream RSS delta peaked at `24620 KiB`; W2 peaked at
  `443008 KiB`, so B fails the same bounded-stream rule.

The original development-equivalent raw records preserve all measured samples
and failure fields in
[`p2-r1-provider-measurements-2026-08-02.jsonl`](./p2-r1-provider-measurements-2026-08-02.jsonl).
The machine-readable decision summary is
[`p2-r1-provider-summary-2026-08-02.json`](./p2-r1-provider-summary-2026-08-02.json).
The exact target-image matrix is preserved in
[`p2-r1-target-image-measurements-2026-08-02.jsonl`](./p2-r1-target-image-measurements-2026-08-02.jsonl)
with summary
[`p2-r1-target-image-summary-2026-08-02.json`](./p2-r1-target-image-summary-2026-08-02.json).

## Implementation covered by this probe

- Component-first durable layout: `control/`, `versioned/`, `staging/`,
  `artifacts/`, `service-state/` and `provider/`; all components are checked
  to share one device. No `current/` and no control SQLite are created.
- Root-exclusive `flock`, fsync barriers, atomic same-device publication,
  and explicit before/after rename fault points.
- Exact Dolt `2.1.11`, fixed author identity, allowlisted environment,
  `shell=False`, explicit argv, server-owned cwd, process groups,
  terminate/grace/kill, direct-child wait/reap, bounded tails, and adopted
  Dolt-helper reaping for the PID-1 container case.
- Candidate A offline CLI metadata/row probes with stdin SQL and bounded
  Arrow `RecordBatch` output.
- Candidate B service-owned loopback/private-socket `dolt sql-server` with
  `mysql-connector-python==9.7.0`, asynchronous non-buffered cursors,
  `fetchmany`, same-session replay/commit/ref checks, and graceful cursor,
  connection, server stop and reap.
- Background Dolt statistics are disabled and purged in Candidate B so
  `.dolt/stats` is not intentionally part of the canonical-storage result.
- W0 covers NULL, UTF-8, single/composite keys, known normalized SQL families
  and nullable unknown `ENUM`; unknown types are tested with both REJECT and
  nullable `large_string` STRINGIFY policies.
- W1 is about 11.7 MB SQL input / 40,000 rows, W2 is about 192 MB / 100,000
  rows, and W3 applies deterministic 1% and 10% updates to W1.

## Verification evidence

Passed locally in `vnext/repository_service`:

- `uv lock --check`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest -q` — 17 passed
- `git diff --check`
- `docker compose -f vnext/deploy/compose.yaml config`
- `docker compose --profile p2-r1 -f vnext/deploy/compose.yaml config`
- required primitive tests for root-lock exclusion, same-device layout,
  restart/reopen behavior, and before/after rename faults.

The target-image named-volume matrix used the retained dependency-base image,
the exact Dolt 2.1.11 binary, the repository-service environment and the
image's non-root `gateway` user. The real Docker named volume reported XFS;
the backend was recorded as `remote-named-volume`. Both candidates completed
all 30 records (one warm-up plus five measured samples for each of five
workloads), with correctness, restart, cancellation cleanup, pinned revision
reads, catalog checks, marker parent and marker uniqueness checks passing.
The matrix ended with no remaining Dolt process or zombie child. The
machine-readable summary marks this environment as
`development-equivalent-smoke` and `production_environment_assessed: false`.

## Target-image result and retained cache

The target Dockerfile image was built successfully by reusing a retained
dependency-base image containing the exact Dolt 2.1.11 binary, uv 0.11.28 and
the lock-resolved Python environment. The image was tagged for the 2026-08-02
probe, passed non-root version/settings smoke and completed the full named-
volume matrix above. This certifies the tested target-image path for P2-R1
feasibility; it does not override the bounded-stream failure or make a
production SLO claim.

The development host retains the versioned internal Dolt/uv artifact cache,
the dependency-base image and the successfully built target image for future
source-only rebuilds. Probe cleanup removed only the matrix container, test
named volume and temporary build contexts; it did not remove the cache or
retained images.

An additional controlled probe was performed on the supplied temporary
internal Arch Linux host. After a manual reboot it ran kernel `7.1.5`, with
the `veth` module present; a manual veth pair and the Docker bridge endpoint
both succeeded. The unchanged target Dockerfile then reached its Dolt
download step using the normal bridge network, but the proxy closed the
connection with `RemoteDisconnected`. A bounded host-side probe received only
about 0.49 MB of the approximately 44 MB release in 30 seconds and timed out.
This separates the former bridge/veth failure from the remaining external
dependency transport failure.

To isolate the image/runtime path, a non-production offline probe image was
built with the exact Dolt 2.1.11 binary and the already-resolved Python
environment injected as build inputs. That image built successfully on the
Docker bridge. After adding the missing `/home/gateway` directory required by
Dolt when `HOME` is set to that path, non-root runtime smoke passed and a W0
matrix run completed 12 workflows (A/B, warm-up plus five measured runs) with
all workflow correctness gates true. This was not the unchanged Dockerfile
build and was not used to replace the full 60-record matrix decision.

The earlier external-download failure remains useful as transport history:
the remote Docker bridge/veth path was repaired and the original build then
reached dependency retrieval, where the configured proxy stalled. The
versioned internal cache and dependency-base path now remove that external
transport dependency from source-only rebuilds. A future dependency version
update must add a new retained cache artifact and rebuild the dependency-base
image before repeating the formal target-image probe.

## Scope and limitations

This change is private P2-R1 probe code only. It does not implement HTTP,
control DB, `Current`, public repository operations, upload/import lifecycle,
P2-R2 or later phases, and it does not change Backend, Rust, canonical storage
semantics, contracts or runtime/container data. All fixture data is synthetic.

No final regression/handoff claim is made. P2-R2 must not start from this
result until the hard-gate failures are addressed and the target image,
named-volume matrix, smoke and cleanup are repeated successfully.

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

## Matrix result

The matrix was run as one warm-up plus five measured samples for each of W0,
W1, W2, W3-1% and W3-10%, for both candidates. Correctness, restart,
cancellation cleanup, pinned revision reads, catalog checks, marker parent and
marker uniqueness checks passed for every completed sample.

| Candidate | W1 max import | Capacity projection | 60-minute safety | Incremental storage | Bounded stream | Hard gate |
|---|---:|---:|---:|---:|---:|---:|
| A offline CLI | 135.44 s | 1786.12/day | pass | pass | fail | fail |
| B sql-server | 259.92 s | 930.74/day | pass | pass | fail | fail |

The capacity projection uses the formal feasibility formula with a 70% duty
cycle. It is deliberately reported only as a projection.

### Failed gates

- Candidate A W1 measured stream RSS delta peaked at `168136 KiB`; W2 peaked
  at `580488 KiB`. The bounded-stream rule permits at most twice the W1 peak
  (or 64 MiB, whichever is larger), so A fails this gate.
- Candidate B W1 measured stream RSS delta peaked at `29756 KiB`; W2 peaked at
  `443596 KiB`, so B fails the same bounded-stream rule.
- Candidate B's W1 capacity projection is `930.74/day`, below the hard gate
  of `1000/day`.

The raw records preserve all measured samples and failure fields in
[`p2-r1-provider-measurements-2026-08-02.jsonl`](./p2-r1-provider-measurements-2026-08-02.jsonl).
The machine-readable decision summary is
[`p2-r1-provider-summary-2026-08-02.json`](./p2-r1-provider-summary-2026-08-02.json).

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

The named-volume matrix used a Python 3.14.6 slim target container, a real
Docker named volume, the exact Dolt 2.1.11 binary, and the repository service
package environment. The source and package mounts were read-only and the
matrix ran as root because this was an equivalent smoke environment, not the
final image. The filesystem probe reported `ext2/ext3` for the named-volume
mount (the backend was recorded as `named-volume-ext4`). The matrix completed
with 60 records and no remaining Dolt process or zombie child.

## Target-image limitation

The target Dockerfile image build was attempted but did not complete because
the environment stalled on external downloads:

1. the normal build stalled without progress during `apt-get update`;
2. the `--network=host` retry stalled at the same package-index step;
3. after replacing apt/curl with Python URL retrieval, the retry stalled while
   downloading the GitHub Dolt release.

The equivalent named-volume container matrix above is therefore useful for
provider feasibility, but it does not certify the Dockerfile-built runtime.
The target-image build and the exact non-root image smoke remain required
before any future round can be marked ready. This limitation reinforces the
`no-go` result; no production provider selection is made.

An additional controlled probe was performed on the supplied temporary
internal Arch Linux host. It had x86_64, 16 CPUs, 62 GiB RAM, about 1.2 TiB
free disk, Docker 29.6.2 and working GitHub/PyPI HEAD requests. The first
legacy build attempt failed while creating a Docker bridge/veth endpoint with
`operation not supported`. The `--network=host` retry reached the Dolt release
download step, but the download made no progress for approximately eight
minutes with zero CPU; the intermediate container was stopped and removed.
The stopped build returned exit `137`. No target image or temporary build
context remained on that host afterward.

## Scope and limitations

This change is private P2-R1 probe code only. It does not implement HTTP,
control DB, `Current`, public repository operations, upload/import lifecycle,
P2-R2 or later phases, and it does not change Backend, Rust, canonical storage
semantics, contracts or runtime/container data. All fixture data is synthetic.

No final regression/handoff claim is made. P2-R2 must not start from this
result until the hard-gate failures are addressed and the target image,
named-volume matrix, smoke and cleanup are repeated successfully.

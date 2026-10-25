# Phase 6 V1 ordered Rust prototype report

## Decision for the owner

V1 shows that the IEC104 `gid` / `no` ordered comparison is a good S3 Rust candidate. Include it with the standard and keyless comparison kernel in S3. The Python reference took 32.648 s for the 12 changed t4 ordered tables; the Rust one-thread median was 2.643 s, and the 16-thread median was 0.256 s. The measured Rust result is byte-identical to the reference. At one thread the t4 ordered set uses 4.4% of W3 and 1.5% of W4, compared with 54.4% and 18.1% for the Python reference.

Use one caller-owned fixed-size pool and table-level parallelism. For the measured t4 workload, 8 threads took 0.451 s with 692 MiB process peak RSS; 16 threads took 0.256 s with 1,195 MiB. 32 threads were slower than 16 and peaked at 1,548 MiB, so V1 provides no reason to default to 32 threads. The owner should choose the production pool size with the combined S3 workload and memory budget in view.

## Implementation scope

The prototype adds `gateway_compute_core::comparison::ordered` under the existing core crate. The core accepts Arrow `RecordBatch` pairs and comparison options in memory; it does not open files or depend on Python. `comparison/mod.rs` exposes the capability module. The implementation handles the GID_NO_V1 identity and ordering columns, common-column value comparisons, ordered logical digests, blank-row provenance and interval facts, schema facts, standard row facts, deterministic record ordering, and bounded failure results.

Only table-level parallelism is implemented. `compare_ordered_tables_parallel` accepts a caller-owned Rayon `ThreadPool`; the public entry catches panics and converts them to bounded error results. The prototype uses no `unsafe`, nightly features, or handwritten SIMD. It enforces limits of 2,000,000 rows, 512 columns, 4 MiB per cell, 256 MiB of encoded frames per table, and 256 pool threads.

The only new crates are exact-pinned `arrow-ipc = 59.1.0` (compression disabled) and `arrow-select = 59.1.0`. Both are core-crate dev-dependencies used by the measurement example to read uncompressed IPC and concatenate batches; they do not add runtime dependencies. The initial implementation commit records these purposes under Rust safety policy §5. Existing `rayon` and `proptest` are reused; the latter remains a stable-channel dev dependency. The Rust release binary used for measurement was built on ct108-gw-dms-05. Its source tree was `ee567e3cea87c243c8e4a209beaacacbfab4a2db`.

`vnext/backend/benchmarks/p6_v1_ordered_diff.py` is test and measurement tooling. It invokes the Python reference to materialize/project inputs, writes uncompressed Arrow IPC and expected normal forms into private node directories, and prepares deterministic synthetic and random cases. The Rust example reads these files, invokes the core, optionally verifies the expected normal forms, and records timings and process high-water RSS. Neither core comparison code nor the report contains real row values.

## Test-only canonical form

The example writes a test-only `GDMSOCF1` frame: the eight-byte magic, a big-endian u32 payload length, and JCS-canonical JSON bytes. This makes a single table result comparable byte-for-byte without defining a production transport. Canonical scalar values are represented by a type marker and the shared-kernel scalar frame in hex. Real output is kept only in private node storage; this report contains no scalar values, row identities, or digest strings.

The JSON contains the complete per-table `ComparisonTableFact` envelope and both extensions:

| Part | Canonical fields |
| --- | --- |
| Table facts | format/version, table name, status, before/current row counts, added/deleted/modified and suppressed counts, content-changed flag, schema-change facts, diagnostics, standard records |
| Standard record | table, record kind, stable row identity when applicable, changed columns, before/current canonical values, field changes, diagnostics |
| Ordered extension | contract version/status, add/delete/modify/move and position-change counts, degraded count, before/current ordered digest, replay guarantee, table-processing mode, policy digest, diagnostics, ordered records |
| Ordered record | table, record and semantic kinds, real-stable entity-key marker, gid identity, before/current `no` positions, changed columns, before/current canonical values, diagnostics |
| Blank extension | contract version/status, inserted/deleted/changed interval counts, degraded count, occupancy digests, replay guarantee, interval records with anchor and before/current position bounds, diagnostics |

All record collections are sorted by stable semantic fields before serialization; facts use the same field values and counts as the reference. The pseudo gid is represented as blank provenance and is never emitted as a real row identity. Ordered logical digest columns come from the ordered policy; `compare_excluded_columns` affect value-change detection but do not silently rewrite the policy's digest column set. This keeps the two roles explicit in the prototype options.

## Consistency and determinism

All listed differential checks compared the complete canonical frame, not a selected subset of fields.

| Corpus | Tables/cases | Before → current rows | Canonical records | Differences |
| --- | ---: | ---: | ---: | ---: |
| Synthetic contract cases | 30 | 95 → 97 | 46 | 0 |
| Random sequences, seed 20261025 | 96 | 1,053 → 1,045 | 487 | 0 |
| t1 changed ordered tables | 1 | 17 → 17 | 12 | 0 |
| t2 changed ordered tables | 39 | 41,801 → 36,575 | 10,810 | 0 |
| t3 changed ordered tables | 6 | 31,830 → 31,830 | 708 | 0 |
| t4 changed ordered tables | 12 | 117,864 → 117,936 | 168 | 0 |
| t1–t4 total | 58 | 191,512 → 186,358 | 11,698 | 0 |

The synthetic cases cover additions, deletions, modifications, moves, full reorders, blank-row additions/deletions/shifts, duplicate and tied identities, degradation cases, and schema addition with comparison restricted to shared columns. The 96 random sequences use operations accepted by the Python reference and include blank rows. The Rust property test separately runs 96 stable proptest cases, checks bounded outcomes, and compares one-thread and multi-thread output. The Rust table-parallel unit test also checks byte determinism.

On ct108-gw-dms-05, `tests/test_comparison_ordered.py` and `tests/test_comparison_blank.py` passed: 40 tests. The 30 synthetic and 96 random Rust outputs were each verified against Python with both 1 and 8 threads; the output directories were byte-identical across thread counts. The 12 t4 Rust outputs were verified against Python at 1, 2, 4, 8, 16, and 32 threads; all six output directories were byte-identical. The all-tier Rust verification ran with one thread over all 58 tables. Rust module format/clippy checks and the five Python packages' ruff/mypy checks passed on ct108-gw-dms-05. The required final `GATEWAY_TEST_PACKAGES=rust` runner is run on the clean report-bearing commit; its exit code and log are included in the completion handoff.

## Performance

### t4 changed ordered set

The Python and Rust runs used the same 12 changed ordered tables and the same canonical Arrow IPC inputs. Python and Rust timing excludes snapshot/package materialization, IPC generation/reading, and canonical output encoding. Each result below is the median of seven measured runs after one warmup. Rust used table-level parallelism.

| Implementation | Threads | Median seconds | Speedup vs Python | Process peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Python reference | 1 | 32.648 | 1.0× | 2,264,128 KiB during comparison; 2,415,156 KiB process high-water |
| Rust | 1 | 2.643 | 12.4× | 195,880 KiB |
| Rust | 2 | 1.317 | 24.8× | 269,220 KiB |
| Rust | 4 | 0.663 | 49.2× | 414,020 KiB |
| Rust | 8 | 0.451 | 72.4× | 708,776 KiB |
| Rust | 16 | 0.256 | 127.6× | 1,223,252 KiB |
| Rust | 32 | 0.314 | 104.0× | 1,585,328 KiB |

Python comparison-window RSS started at 2,263,908 KiB and sampled a 2,264,128 KiB peak (220 KiB delta) after the snapshot objects were already materialized and the process allocator was warm. The process high-water includes earlier materialization and is not a clean comparison-only peak. Rust process RSS includes all 12 Arrow inputs loaded for the run, comparison, and retained output summaries. Treat these as process-footprint evidence, not as a like-for-like allocation benchmark.

### Near-total reorder size curve

Each synthetic table is reversed so that n−1 rows are classified as moved. Both implementations use seven measured runs and one warmup. The corrected scale normal forms verify byte-for-byte against Python.

| Rows | Moved rows | Python median seconds | Rust one-thread median seconds | Python/Rust |
| ---: | ---: | ---: | ---: | ---: |
| 10,000 | 9,999 | 1.295 | 0.157 | 8.3× |
| 50,000 | 49,999 | 6.895 | 0.885 | 7.8× |
| 100,000 | 99,999 | 13.992 | 1.990 | 7.0× |

Five times as many rows took 5.32× as long in Python and 5.65× in Rust; doubling from 50k to 100k took 2.03× and 2.25×. A 10× increase took 10.81× and 12.71×, respectively, so the measured curve shows no quadratic growth. The implementation uses an O(n log n) longest-increasing-subsequence backbone and deterministic O(n log n) sorting/lookup around it; full moved-record emission is at least O(n) in output size. The Rust group median over all three scale tables was 3.140 s. Its process peak RSS was 1,616,044 KiB because the example loads the three Arrow input pairs together. The Python scale-only process high-water was 539,196 KiB; its fixture builds and releases scale tasks one at a time, so the memory figures are not directly comparable.

### W3/W4 budget estimate

DC35 budgets W3 at 60 s and W4 at 180 s. The 32.648 s Python t4 comparison uses 54.4% of W3 and 18.1% of W4. Rust at one thread uses 4.4% and 1.5%. At 8 threads Rust uses 0.75% and 0.25%; at 16 threads, 0.43% and 0.14%. These are estimates for the V1 t4 changed ordered set only, not the full W3/W4 journey.

## Specification and reference notes

1. `ordered-diff.md` describes the IEC104 pseudo key start as 2,000,000,000, while G8 in `canonical-storage-and-repository-boundary.md` reserves the physical pseudo gid range 4,000,000,000–4,294,967,295. The Python and Rust implementation path used by this prototype follows G8's 4-byte canonical storage range. The owning contract should state explicitly that G8 supersedes the older ordered-diff pseudo start, or reconcile the two before S3 integration.
2. DC39 says unchanged ordered tables are filtered by their table summaries before reading or comparing rows. V1 manifests contain only changed ordered tables; unchanged tables are not part of the measured/differential input. The prototype therefore does not implement table-summary filtering, which remains the S1a owner.
3. The first scale-manifest draft omitted the Python policy digest. Record counts, positions, and ordered digests already matched, but canonical bytes did not. The benchmark manifest was corrected to copy the digest from the Python ordered fact; the final three scales now verify with zero differences. This was a harness defect, not a Python/Rust behavior difference.

## S3 integration guidance and risks

Bring the ordered capability into S3 with the standard/keyless Rust comparison kernel. Share canonical scalar-frame encoding, common-schema projection, stable row-identity handling, deterministic record encoding/sorting, resource-limit reporting, and the outer table-facts/digest plumbing. DC45 storage diff should call the same shared comparison kernel and consume the same facts. Keep ordered-specific LIS/backbone selection, absolute `no` positions, and blank-row interval rules in the ordered capability; do not force these into standard/keyless row pairing.

The main integration risks are the pseudo-gid contract ambiguity, policy digest and excluded-column boundaries, memory growth as table concurrency increases, and bounded handling when row/cell/output limits are exceeded. V1 demonstrates parity through 100k-row near-total reorder and real t1–t4 changed tables, but it does not measure a full production W3/W4 journey or establish a production pool size. The owner should use the V1 performance result to include ordered in S3 and confirm the pool/memory budget alongside the broader S3 workload.

## Measurement provenance and private artifacts

The reference node was `ct108-gw-dms` (`gw-dms-test`, 128 logical CPUs); the debug/differential node was `ct108-gw-dms-05` (`gw-dms-test-05`). `ct108-gw-dms-04` was not used. The reference node was checked for runners, pytest, Dolt, Compose, and running containers before exclusive performance runs. The Rust binary was built on 05 and transferred to the reference node; its SHA-256 was `1f80323beec5e89830ab26e58117ff29db0b504f54429e2c8f2e1da9a8364be8`. The t4 thread sweep ran 15:16:23–15:19:16 UTC at candidate HEAD `69b876de659cd25412c81f0227acfa87d1faad6f`. The corrected scale Python baseline ran 15:23:51–15:27:18 UTC at candidate HEAD `f3e9ec75ac4282a33802eb7503dc812cb1818dd4`; the corrected Rust scale run ran 15:27:32–15:28:24 UTC with the same branch HEAD and Rust tree `ee567e3cea87c243c8e4a209beaacacbfab4a2db`. Since the Rust build HEAD, only the scale manifest's policy-digest field and this report were added; the `vnext/rust` tree hash is unchanged. The Python reference source was the installed tree `863330e75781e545ea8551fea3cd53c32b263c42`, whose backend and shared-kernel package trees match the branch base.

Private inputs, expected/actual canonical forms, JSON metrics, and logs are outside Git under `/home/dev/gdds-p6-logs/v1/` with mode 0700 directories and 0600 files. Key records are:

- t1–t4 Rust verification and aggregate audit: `rust-real-all-58.log`, `real-05/rust-all-58.audit.json`.
- Synthetic/random differential: `synthetic-final/`, `synthetic-final-release.log`.
- Python t4 reference and initial scale run: `real-reference/python-measurements.json`, `real-prepare-reference.log`.
- Corrected Python scale baseline: `real-reference-scale-final/python-measurements.json`, `official-reference/scale-python-prepare-final.log`.
- Rust t4 sweep and determinism: `official-reference/rust-t4-thread-sweep.log`.
- Corrected Rust size curve: `official-reference/rust-scale-1-thread-fixed.log`, `official-reference/scale-threads-1-fixed.audit.json`.
- 05 focused tests, static checks, Rust checks/build, and test-runner logs are in `/home/dev/gdds-p6-logs/v1/`.

An earlier scale measurement exposed the missing policy-digest fixture field above and is not used. Two accidental reference-node build attempts were also excluded: an unused release build went into `/home/dev/gdds-test-tmp/p6-v1-ref-cargo-target`; later, `uv-consume` created `/home/dev/gdms-p6-v1-reference/vnext/backend/.venv` and began building the Python extension into the worktree's ignored `vnext/rust/target`. That process was terminated; neither artifact was used for any Rust measurement. They remain in the cleanup list for owner review.

# Phase 6 synthetic load inputs

Run these steps only on the designated measurement node and in its private
scratch area. Never put extracted SQL, generated SQL, archives, or benchmark
output under the Git worktree. Use a private copy of the t4 package; the
generator prints table names and counts only.

## Generate the 2x-t4 dataset

Extract `sql/dbcfg.sql` from the private t4 package with
`p6_v6_measure_inputs.py extract-sql`. Run the generator through the locked
backend environment:

```bash
../scripts/uv-consume.sh -C . run python benchmarks/p6_s1b_synthetic_load.py \
  make-2x --source /private/scratch/t4.sql \
  --output /private/scratch/t4-2x.sql --suffix __x2
```

The tool copies every source table, gives the copy a deterministic `__x2`
name, and changes every row in one safe non-key column per nonempty table.
This prevents identical copied row contents from inflating content-address
deduplication results. Empty tables remain empty because they have no row
content to perturb. It checks the generated dump with the reference parser and
fails closed if a table has no safe field or if table names collide.

## Check real-data JSON depth

Extract each private t1–t4 package's `sql/dbcfg.sql` to scratch, then run the
depth counter on each dump:

```bash
../scripts/uv-consume.sh -C . run python benchmarks/p6_s1b_synthetic_load.py \
  json-depth --source /private/scratch/t1.sql
```

The output contains only the number of JSON cells, maximum container nesting
depth, and a depth-to-cell-count distribution. Record those counts under the
t1–t4 aliases in the handoff. Stop and ask the owner if the maximum approaches
the parser limit of 100.

## Generate W4 and the pressure input

Use the same t4 SQL as the baseline and generate two target dumps:

```bash
../scripts/uv-consume.sh -C . run python benchmarks/p6_s1b_synthetic_load.py \
  make-w4 --source /private/scratch/t4.sql \
  --output /private/scratch/t4-w4-10pct.sql --rate 0.1
../scripts/uv-consume.sh -C . run python benchmarks/p6_s1b_synthetic_load.py \
  make-w4 --source /private/scratch/t4.sql \
  --output /private/scratch/t4-w4-100pct.sql --rate 1.0
```

For every table with rows, the rate is the ceiling of the requested share of
baseline rows, with at least one changed row. The deterministic split uses
insert, delete, and non-key update actions as evenly as the table size permits.
Keyed insertions receive a fresh supported key; keyless insertions change a
safe non-key value. Ordered tables also move a row to a later position. Empty
tables receive one valid synthetic row so every table changes. The command
reports per-table before/inserted/deleted/updated/after counts; it never prints
cell values. The 100% input is a report-only pressure run and has no pass/fail
threshold.

## Measurement handling

- Keep generated inputs and logs outside the worktree with mode `0600`.
- Run on `ct108-gw-dms` while it is otherwise idle. Record hostname, UTC start
  and end, candidate HEAD, command exit code, wall time, CPU time, peak
  parallelism, peak memory, temporary-disk high-water mark, and table/row
  counts. Do not record SQL cell values.
- Run one warmup and three measured repetitions for each measured workload;
  report median and range. Keep W1/W4 cold-start conditions and W2/W3 cache
  reuse conditions as specified by design §16.4, and state cache health and
  READY/terminal timing endpoints.
- Run the generated t4 2x input through the Phase 6 workload matrix. W4 uses
  the 10% input for its gate and the 100% input for reporting only.
- Never run a measurement or diagnostic as root against a Dolt repository that
  Repository Service is actively serving. Use a private database copy. Do not
  attach a sampling profiler to workers.
- Synthetic-input summaries contain only table names and counts. Handoff
  measurements may add the timings and digest summaries required by design
  §16.3; generated SQL, row values, and per-cell diagnostics stay in private
  scratch.

# P6 S4 E: fixed-source execution and evidence map

Status: execution and evidence map, not an acceptance receipt. The c9e candidate
has actual 04 all-six authority/Compose and the old B independent expectation
capture and S1a component replay have actual evidence; the DC97 successor still
needs affected-package/image review and the 05 complete journeys. The final
handoff binds exact source, script and raw evidence identities. The independent
E reviewer clears changed source and node/controller bytes before Luna runs them.

## Independent input and expected values

- Standard eight packages: `/home/dev/gateway-real-dumps/datasets.json`, SHA256
  `78c7cbba05acbbe92cc9a22351f8caf800824c4520e0d9685c6e776d6042da4f`;
  committed census SHA256
  `733b506e43164a62f30d3a1d665449471e8edf25b515701150f6e73a824a6988`.
  The node uses its own fresh read-only copied package root; `--keep-stack`
  writes only to the run's separate input-copy `runs/` directory.
- Frozen 2×t4, W4-10%, W4-100% source: controller copy
  `/home/dev/gdds-test-tmp/p6-s3-input-copy-20261108/source/`, with the
  13-file bytes/SHA manifest at sibling `copied-inputs.json`. A run uses its
  own node copy and checks all 13 files before business work. The 2× metadata
  SHA is `f7f420e730c27c684f527439dc60dce57415417b318dc7a50e39f0143d0509e1`;
  W4-10% is `5b63f895c0c9c6c8b247aa64cd120f6215f3d3428fc601dc3e12a0232e791efb`;
  W4-100% is `38ac821822b87b8c94b121de350bc85a910cb0f604d534bd8c48a0fbc28d5c8e`.
  The accepted `input-summary.json` SHA is
  `6b63cf2e8c58cadc96b7ac716a523f9b5554fcb496eea16c0c2f5089199a3896`.
  The six package and three census SHA values are in the 13-file manifest;
  the driver verifies every path, byte count and SHA, never regenerates them.
- Old independent source: B `788ed36e7742a067bf01c16ad2e6aaed2fed91fb`, its
  fixed external `table_diff_driver.py` SHA
  `9277ea22d04c0dd671fadf615d0480af6284617cd9255af6344a8298a55e85db`.
  `s4_expected_capture.py` checks the B worktree HEAD/clean state and that
  driver SHA, then invokes only B source staging and canonical projection.
  One output per dataset holds full catalog schema/name/count SHA plus selected
  table row-multiset SHA. The selected rows include keyed, ordered, keyless
  and composite tables where present. Capture on a dedicated node under its
  own marker; the old B package/hash inputs and capture code SHA remain in
  the controller record. Merge the two dataset expectations for each load
  into `{"datasets": {"rd-...-v1": <expected>, "rd-...-v2": <expected>}}`,
  SHA-pin that exact JSON before the current candidate uses it. Never produce
  expected bytes from current C/D SQL or a current Repository read.

For B capture, `uv-consume.sh` rejects an absolute Python script outside its
project. The reviewed node command feeds the SHA-pinned E script over stdin:

```text
GATEWAY_S4_B_WORKTREE=<clean B worktree> \
  <B worktree>/vnext/scripts/uv-consume.sh -C <B worktree>/vnext/backend \
  run --no-sync python - \
  --source-root <node copied root> --datasets-sha256 <fixed metadata SHA> \
  --package-id <dataset ID> --select <keyed> --select <ordered> \
  --select <keyless if present> --select composite_signal_point \
  --old-driver <fixed B table_diff_driver.py> \
  --old-driver-sha256 9277ea22d04c0dd671fadf615d0480af6284617cd9255af6344a8298a55e85db \
  --output <new worktree-external JSON> \
  < <SHA-pinned s4_expected_capture.py>
```

The 2×/W4 t4 representative names are keyed
`b1_n11_iec104_syx_list` and `b1_n11_iec104_syx_list__x2`, ordered
`b1_n11_iec104_dyk_list`, keyless `app_cfg__x2`, plus
`composite_signal_point`. For standard t1–t4, fix each selection against its
frozen source manifest before the node run; selected names must exist and
remain the same across that pair where possible. The standard historical
census lacks per-table row counts; the B expectation supplies the full
schema/count identity. The synthetic census has exact per-table rows, which
the journey also compares with the Repository Catalog.

## Focused and authority sequence

1. Reviewer clears the exact E candidate and B capture/node/controller
   scripts. On a currently free eligible test node, Luna uses an atomic
   `/home/dev/gdds-node-busy.d` marker, a clean committed detached worktree,
   offline pinned toolchain/caches, six unchanged locks and worktree-external
   logs. The focused backend scope is `tests/test_real_dump_journey.py` in
   nonserial and `serial and not parallel_safe` passes. Run five Python
   Ruff/Mypy checks. A new Rust package run is required in the final
   authority, with forced backend extension reinstall before backend pytest.
2. Once any finding is fixed and a final product V is committed, run
   `./vnext/scripts/run-tests.sh` with **all six packages** in the required
   fixed order and its current HEAD normal Compose build. No prebuilt flag;
   backend dependency base is preloaded and build network is `none`. Record
   config digest/all RootFS DiffIDs across nodes; use local image IDs only
   for same-node runtime binding. Any nonzero package stops later acceptance.
3. Capture the B source expectations under independently reviewed script,
   then run current final-V functional and measured journeys. Build/input
   preparation and source logs are outside worktrees. Both all-six authority
   and B expectation capture require the current node's toolchain/cache and
   start/end HEAD, exit, hostname, timestamps, log SHA and own marker release.

## Real journey and timing matrix

Each run is a fresh project and complete Preview/Submit/Repository read/
Review/Archive/History journey. V1 Preview uses MODIFIED_ONLY; v2 uses the
selected MODIFIED_ONLY or FULL mode. Synthetic MODIFIED_ONLY groups skip the
repeat-v1 upload/Preview/Submit after v1 Archive, preserving the cold v1
canonical baseline for v2 Preview. Synthetic FULL and all four official
groups retain repeat-v1 upload/Preview/NO_CANONICAL_CHANGE, bracketed by
read-only Repository import and sync mutation IDs; before/after must match
exactly. The official groups supply the S2 zero-operation evidence. FULL and
MODIFIED_ONLY groups have different cache conditions and separate statistics.
Both real Submit commits are
checked against technical `main` and independent B schema/selected row
expectations. The business baseline only advances at Archive.

| Group | Input and mode | Run count | Reference Submit target |
| --- | --- | --- | --- |
| Functional | Standard fresh t1, t2, t3, t4; v2 FULL | One complete run each | Every Submit ≤10 min; t4 v1 ≤5 min |
| W3 MO | Frozen 2×t4, MODIFIED_ONLY | 1 warm + 3 successful measurements | v1 ≤5 min; v2 ≤2 min; all ≤10 min |
| W3 FULL | Frozen 2×t4, FULL | 1 warm + 3 successful measurements | Same; separate statistic group |
| W4 10% MO cold | Frozen W4-10%, MODIFIED_ONLY | 1 warm + 3 successful measurements | v2 ≤5 min; all ≤10 min |
| W4 10% FULL | Frozen W4-10%, FULL | 1 warm + 3 successful measurements | Same; separate statistic group |
| W4 100% stress MO/FULL | Frozen W4-100%, separate modes | Each mode: 1 warm + 3 successful measurements | No time threshold; business/resource failure still fails |

The W3 MO group's *one* v1 Submit sample group also supplies the 2×t4
fresh INITIAL S1 timing; do not mix it with W3 FULL or add a duplicate S1
title run. Owner confirmed DC97 for this round: record every valid raw Submit
time, applicable target and `met` result. A numeric miss remains a valid sample
and does not by itself block S4 exit; missing, negative or nonfinite clocks,
missing technical-main movement, and business, Repository or resource failures
remain hard failures.
No failed or resource-invalid run enters a median/range. Every
group's warm and measurements stay on the same actual node, same worker
profile and storage condition, with no concurrent test task; changing node
or hardware starts a separate group. The original N1/32−8/M24 failure stays
in its own column. Current explicit profile is worker envelope 48 GiB,
reserve 8 GiB, operation M40 GiB, kernel N1 and one active operation;
production defaults remain 32/8/M24.

The `s4_submit_measurement_driver.py` checks input and independent expected
SHA, exact final HEAD/clean worktree, actual three-service ready guard before
business (MemAvailable ≥56 GiB), end MemAvailable ≥8 GiB, service identity,
zero OOM/restarts, actual worker cgroup 48 GiB and environment N1/M40/48/8,
same worker since first business observation, source/lock/image IDs, normal
SIGTERM/exit 0 and sampled host disk high-water. Before successful cleanup it
archives all three stopped owned Compose volumes, including backend artifacts,
control and Repository state, to `stopped-volumes.tar` with SHA; a failed run
retains its project volumes and marker. It extracts D table/summary,
publish/readback/checkpoint logs and the journey's control DB/RS wait facts.
The target clock is **POST request start to verified Repository technical main
read**, a conservative upper bound. The accepted-response clock is separately
reported. Its target result is a report fact, while the valid completion clock
and business/resource guards remain acceptance conditions. The driver seals
`sample_pre_release_pass` with
`acceptance_complete=false`; a sample is accepted only after controller sees
the unique `s4_sample_release PASS` stdout receipt, entry exit 0 and a
read-only postrelease marker/host check. A failed sample stops its queue and
preserves original logs, stopped project and marker for diagnosis. No
unmodified retry or threshold change is implied.

S1a threshold verification is a separate fixed old-source capture and current
generic planner/Rust facade replay into a private Dolt repository. This is a
component scope result, not a production Submit/StorageTableTask or worker
capacity result. Its source table is `b1_n11_iec104_syx_list`, parent
9822 → target 9828, 98 logical changes = 92 UPDATE + 6 INSERT + 0 DELETE;
the extra 85 updated rows are a fixed old S1a synthetic perturbation of
unchanged t4 rows, not the natural t4 pair. The old JSON/log supplies PATCH
36,238 bytes and REBUILD 1,576,977 bytes with three alternating equal-result
hashes. Current output cannot generate its own expected. This verification
has a separate owner/script and is not folded into the full journey timing
statistics.

## Exit evidence map

For each sample preserve raw log, SHA manifest, input copy origin/time and
SHA, prepared/runtime image identities, three cgroup peaks/OOM counters,
worker RSS high-water, M admission/high-water logs, host memory/disk endpoints,
source HEAD and status, full business result, Repository schema/selected row
digests, table decision/net counts or null, SQL/DDL/DML bytes, package
publish/readback/checkpoint times, Repository import queue/run and operation
wait times. Nested timings are not added as disjoint costs. `native_calls=2`
is only coarse prepare/render; `parent_read` counts Repository parent reads,
not every frozen-after open. Any unknown or failure stays explicit. The final
S4 H compares package closure and image identity to the actual final HEAD on
the source node/worktree, cites original V and raw logs, and obtains E
independent acceptance before the local annotated exit tag. S3's original
M24 failure and S3-only result cannot be signed by these S4 samples.

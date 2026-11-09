# S6 II fixed sources and minimal execution

This is the reviewed-draft input for III, not an execution receipt. I candidate
`a18492186985913a4d7ae08f3c656ec811d8e348` has focused/static evidence only.
II does not execute a real journey, full runner or container gate. Final H is
resolved from the independently frozen clean candidate, then passed literally
to the node wrapper; the actual results live in
`/home/dev/gdds-s6-logs/final/<H>/`. Do not write results back into H.

## Frozen input and independent oracle

Standard datasets `/home/dev/gateway-real-dumps/datasets.json` SHA256
`78c7cbba05acbbe92cc9a22351f8caf800824c4520e0d9685c6e776d6042da4f`;
committed `p5-arch-closure-s1-census.json` SHA256
`733b506e43164a62f30d3a1d665449471e8edf25b515701150f6e73a824a6988`.
Only `rd-t4-d-v1.tar.gz`, 5,597,503 bytes, SHA256
`95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675`,
is consumed. No derived census or v2 input is used. Give the node a task-owned
copy of standard metadata and packages, with an independent writable `runs/`;
source files stay read-only. Transfer through the approved LAN and verify
before execution; never regenerate these inputs.

The [fixed asset directory](p6-s6-assets) contains unchanged saved bytes:

| File | SHA256 | Authority |
| --- | --- | --- |
| `old-b-t4-expected.json` | `0e67afac5eb529282b2aa59ed833ccf40cbb3ab82b2da64861e1b904079e7915` | old B `788ed36e7742a067bf01c16ad2e6aaed2fed91fb`, complete 312-table names/column SQL type/nullability/PK/count digest and five typed-row multisets |
| `old-b-mapped-t4.json` | `258a99660244281532a1c14e50ad9dd40a214289925248bc84b3c25bba39a19f` | old B raw 24 app_cfg rows and independently mapped Repository wire rows |

Controller originals are respectively
`/home/dev/gdds-test-tmp/p6-s4-e-b-expected-control/controller/captured/expected/t4-repository-expected.json`
and
`/home/dev/gdds-test-tmp/p6-s4-e-04-6786-real-plan/appcfg-t4-b-mapped-r0-control/old-b-mapped-t4.json`.
These paths currently exist on CT201; the former node04 paths are no longer
present there. Preserve the controller archive; its bytes match the accepted
[S4 coordination §§18–19](p6-s4-coordination.md#18-set口径闭合与dc98短真实验证固定稿).
The original S4 full capture report SHA is
`373c6e9558e3b9b1777dc777a096d2a6bc46bfcc4f0e2624dca7d70ecf3cb7b2`.
Do not run the old algorithm or use current SQL/Repository output as expected.

The five names are `app_cfg` (keyless SET, 24),
`b1_n11_iec104_syx_list` (keyed/ordered, 9822),
`b1_n11_iec104_dyk_list` (ordered empty), `cnt_manage_cfg` (keyless empty),
and `composite_signal_point` (435). Empty representatives prove schema and
emptiness only. The full schema/count digest is
`sha256:26677e772c8ad022c4b570fdaf566c78073041be73e9cda42f13398bce1c37b0`.
SET is declared `SET('1','3','5','7')`; raw digest
`sha256:1ac38b4634a80eb8f1d42d13ce197a507781317869f554a1a8418d1d71427149`
maps to wire digest
`sha256:2c9c580537840e71b6d35f4704a9ade016adbc8521894e1483621d28da696a93`.
The driver independently reconstructs all mapped rows and compares full typed
Counters, retaining row multiplicity. The other four table expectations and
full catalog digest stay unchanged. The actual read verifier is retained from
S4 `short-t4-business.py`, SHA
`5b02e2f53e7ed1381e4c896ba02274e00c02efe575ca36ec9cac858a9d5de982`,
with only current caller/import wiring; it checks public exact-commit HTTP.

## Executable scope and count ownership

[t4-evidence.py](p6-s6-assets/t4-evidence.py) wraps the existing journey methods;
[t4-node.sh](p6-s6-assets/t4-node.sh) owns node admission/process lifecycle and
normal local builds. They are frozen by the final clean H and independently
reviewed before execution. No runtime instrumentation, new DB schema, cache
reset, direct baseline write or alternate business path is introduced.

1. Unique III Luna checks BatchMode SSH, current node availability, offline
   toolchain/LAN-prefill identity and actual cache records; transfers clean H,
   both fixed JSON assets and own standard input copy. Set node alias and input
   root in the command environment. The wrapper itself atomically acquires the
   node marker; do not take a second outer marker. The worktree is clean,
   detached at H with the standard legacy symlink. Source/public Docker context
   permissions must allow the configured container user to read them; never
   broaden secrets, inputs, environments or protected old worktrees.
2. The wrapper sets offline/locked consumption, force-reinstalls the extension
   with HEAD Rust tree and verifies build-input, checks both preloaded bases,
   builds current RS locally with network none. Existing run_journey normally
   builds backend/worker on this node; no external prebuilt override. Capture
   true image config bytes/digest and all RootFS DiffIDs for the two bases and
   three runtime images as part of III's image provenance; inspector local IDs
   alone cannot establish cross-node identity. No image/tag writes during gate.
3. Run exactly one `t4-w1-w2`, fresh standard t4 MODIFIED_ONLY, N1, single
   worker, envelope32GiB/reserve8GiB/explicitM24. Driver uses the original
   `_run_kernel_journey` initialization/context. No timeout/algorithm/expected
   override; original operation timeouts and 2-second polls remain.
4. After first Submit, existing journey reads actual ordered data; the added
   read checks all 312 catalog schemas/counts and all five tables against old B.
   This exact read also positively calibrates rows and catalog access logging
   on the same RS container, outside W2. Require at least six successful rows
   and one catalog request in the calibration window (five selected table
   reads plus app_cfg typed-wire read). No HTTP validator runs inside W2.
5. Preserve full timestamped stdout/stderr before/after each Preview and the
   calibration. Each after log must start with its full before byte prefix;
   exact container/image/start identity, zero restarts/OOM and complete lines
   are checked. Count the actual exact-repository/exact-commit rows/catalog GET
   access records from the byte delta, reject other data targets and non-200.
   A missing positive calibration or rotated/truncated/restarted stream fails;
   absence alone never proves zero. Raw boundaries and deltas remain saved.
6. Each isolated Preview window must have exactly one `s3_pair_metrics` for its
   actual manifest pair and worker events for the accepted operation (lifecycle
   `-` sentinel separately allowed). Preserve kernel, ordered-current-side,
   restore, records-validation, rebind and native input_reads separately. W2
   kernel and actual RS rows must be zero; catalog, ordered single-side,
   restore, rebind and validation need not be zero. Required metrics cannot be
   UNKNOWN. RSS and lifecycle cgroup peak remain distinct from reservation HWM.
7. After W2, query the same backend DB read-only and decode the actual succeeded
   materialize checkpoint with its owner. Open both the accepted Submission
   and W2 canonical manifests with full digest/ref validation. Independently
   enumerate U/X/A/D by complete descriptor business schema, nonempty raw
   content/count, source/canonical schema, full StorageRuleView and projection
   version, checking side facts against each manifest. Require U312 and X/A/D
   empty, baseline demand0. This is metadata verification outside the HTTP
   counting window, never a new row reader or a SQL baseline constructor.
8. Existing journey performs legal approve/Archive and fresh workspace/token,
   upload and Preview; its no-change Submit must return NO_CANONICAL_CHANGE
   with unchanged Repository mutation IDs, technical main and business head.
   Return at repeat completion, never create v2/History. Preserve initial,
   post-Submit and post-Archive head facts and all operation/key bindings.
9. The two existing complete Preview GETs save verified tar bytes to new `xb`
   destinations. Content-Length, actual bytes, raw SHA256, ETag/bundleDigest,
   ordinary/closure members and full logical records validation are retained;
   corrupt responses never publish a saved tar. No extra GET. Source Surface
   and final tar Surface each bind their own digest; no cross-layer equality.
10. Capture actual same-service cgroup peak/events and process RSS HWM at ready,
    boundaries and final running state. On success or caught failure, send
    normal TERM to owned services, wait for exit0, save final logs and preserve
    stopped volumes/secrets/input/evidence for review. The wrapper releases only
    its own marker after processes/containers/port and HEAD/clean closure are
    verified; an unknown cleanup retains the marker and stops acceptance.

The reviewed node invocation is, with literal final H and new external paths:

```bash
GATEWAY_S6_TEST_NODE_ALIAS=<actual-pool-alias> \
GATEWAY_REAL_DUMP_ROOT=<task-owned-standard-copy> \
bash <H-worktree>/docs/backend-vnext/refactoring/formal/plans/p6-s6-assets/t4-node.sh \
  <H-worktree> <new-external-evidence> <unique-session> <H>
```

The controller captures numeric wrapper/tee exits and hashes the completed log;
then copies recursively and hashes every evidence file. Luna does not change
parameters, retry or sign GO. First failure stops this attempt and dependent
acceptance; preserve numeric exit, full logs/SHA and touched extent. Sol fixes
known authorized causes, original reviewer clears revisions, then Luna repeats
only the affected step; DC68 same root max3 repairs. Budget refusal, required
UNKNOWN, unexplained identity/oracle conflict or unsafe cleanup is not bypassed
with M40, altered data or weakened assertion. III supplies the exact H/source,
base config/DiffIDs/cache provenance and actual receipt before launch.

## II-only verification draft

On a dedicated occupied CT, clean II candidate: five-package ruff/mypy, forced
native build-input, full `tests/test_real_dump_journey.py -n 0`; compile the two
fixed Python draft sources via builtin `compile` without writing pycache;
`bash -n t4-node.sh`; run driver `--prepare-only` against standard input and
tracked old B assets; run `historical-bundles.py` via controlled Python stdin
against the saved four tar copies. No stack, full runner or real chain. Fixed
external II node script and literal candidate are in the II handoff; all source
and result hashes/actual node facts remain external. Any nonzero stops later
commands, followed by owned lifecycle closure.

## Historical BE-c and storage sources

[history-index.json](p6-s6-assets/history-index.json) pins four saved S5 tar
paths/bytes/SHA, source V2, node, inputs/mode/pair count and integrity owner.
Task-owned CT201 copies are
`/home/dev/gdds-s6-logs/ii/sources/history/bundle-{00,01,02,03}/`; approved LAN
file transfer to the actual II node precedes read-only revalidation. The new
JSON report preserves original facts and computes only `8*bytes/1000000`
seconds as a theoretical 1Mbps lower bound, excluding protocol/browser cost.
It is not network measurement or a download performance gate. Cold pf3 overall
exit1 and subsequent saved-tar recheck remain separately attributed. New t4
adds only its two existing Preview packages. FULL/three-node/2×t4 and other
missing BE-c scenes remain NOT_RUN; no new History request is authorized.

Storage uses already accepted sources only: [Canonical Storage §5](../contracts/canonical-storage-and-repository-boundary.md#5-artifact-lifecycle)
defines SourcePackage, durable manifest and recoverable derived copies;
[S3 performance report](p6-s3-performance-report.md) records its separate 2×t4,
M40 lifecycle/resource and whole-filesystem sampled usage, not current t4 object
capacity; [S4 handoff](p6-s4-handoff.md) records accepted t4 M40 SQL package
50,566,368/2,125,772 bytes and retained stopped volumes; [S5 handoff](p6-s5-handoff.md)
records t1 M24 tar and cache/object counts. Do not label SQL bytes as Dolt size,
artifact logical bytes as physical disk, a whole-node df delta as per-project
staging peak, or retained failed volumes as cleanup-complete. Current exact
per-object physical values and staging/cleanup peaks without an existing source
stay UNKNOWN; no capacity census or V8 profiling is added. Final gate duration
comes only from the final runner's existing package/batch clock fields.

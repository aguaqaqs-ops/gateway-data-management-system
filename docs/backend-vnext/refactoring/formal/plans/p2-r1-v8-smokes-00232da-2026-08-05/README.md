# P2-R1 v8 smoke archive

These artifacts are retained for review and are not formal decision evidence.

## Provenance

- Source revision: `00232dab47b0158b01d8c5bdbb640947a0e0015f`
- Image digest: `sha256:68e1ce8415bba225e714fb05a22a6f062dfb57c21aaf51a16ccdc009072e6e61`
- Methodology implementation: `p2-r1-audit-corrective-v8`
- Storage: verified target named volume, XFS
- Cleanup: current smoke containers, networks, volumes and per-run cgroups removed
- Historical quarantine resources were not modified

## Artifact classification

`v8-smoke-00232da-a2/a-w0.*` is the earlier generic v7 diagnostic. It contains
12 records for both candidates, uses the v7 4 MiB diagnostic bound, and does
not contain the v8 8 GiB memory-limit evidence. It must not be described as an
A-only v8 smoke.

`v8-smoke-00232da-b/b-w0.*` is the v8 reserved Candidate B W0 smoke. It contains
one record, uses the v8 1 MiB bound and 8 GiB sample limit, and is diagnostic
only with `candidate_b_status=reserved_not_evaluated`.

Both runs are `no-go`, select no provider, and do not authorize P2-R2.

The new A-only v8 W0 smoke will be stored in a separate output directory after
the corrective implementation is built and verified.

# P2-R1 v8 corrective smoke

Diagnostic-only target smoke from the corrected v8 implementation. These
artifacts are not the 66-record formal decision evidence.

- Source commit: `36f8c2f654653c16fb9ad11cf2c4fc1b254cbc6b`
- Source tree digest: `sha256:14e67df35f0cdf0fe99b81a2f634cbcb95688512152d335a22402f34c8085041`
- Image ID/digest: `sha256:3354bc73841180aab2edb34499503e9a036f848323ccf5a1798bb8b8478a2339`
- Methodology: `p2-r1-audit-corrective-v8`
- Dependencies: Dolt `2.1.11`, uv `0.11.28`, connector `9.7.0`, PyArrow `25.0.0`
- Lock SHA-256: `fce9185b59b654729670c618c352f9f7a458fb2de40bbd2e088158e81a771e65`
- Storage: verified named volume, XFS, writable
- Cleanup: containers and networks absent; exact per-run cgroups removed
- Formal status: `no-go`; selected provider: `null`; P2-R2: not ready

## A v8 W0

Run/project identity: `20260805004323_2811189` /
`gateway-p2r1-20260805004323_2811189`.

One Candidate A record was produced with `diagnostic_only=true`, v8 1 MiB
byte bound, and 8 GiB sample memory limit. Raw, summary and report SHA-256
are recorded by the files in this directory.

## B reserved W0

Run/project identity: `20260805004348_2815512` /
`gateway-p2r1-20260805004348_2815512`.

One Candidate B record was produced with `diagnostic_only=true` and
`candidate_b_status=reserved_not_evaluated`; it cannot select a provider.

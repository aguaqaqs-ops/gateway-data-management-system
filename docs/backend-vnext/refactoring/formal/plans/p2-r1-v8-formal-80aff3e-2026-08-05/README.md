# P2-R1 v8 Formal A-only Matrix Archive

This directory contains the one approved v8 A-only formal run. The machine
artifacts are copied byte-for-byte from the remote target and are not rewritten
by this archive note.

## Run and provenance

- Remote run: `20260805011107_2971199`
- Compose project: `gateway-p2r1-20260805011107_2971199`
- Source commit: `80aff3e6ff92e6d21aaa7fe73c9a2feafdc1efce`
- Source tree digest: `sha256:ab97a6d628f24ede8ff4ed0adb24a0749d186e990b51073bffed0a0bc4ceeab1`
- Image ID: `sha256:ddc7a41226ea50997ebaa8ec2c3227aa9b83adc7ee3bc1f226d661bf051cea98`
- Methodology: `p2-r1-audit-corrective-v8`
- Lock SHA-256: `fce9185b59b654729670c618c352f9f7a458fb2de40bbd2e088158e81a771e65`
- Dolt: `2.1.11`
- uv: `0.11.28`
- mysql-connector-python: `9.7.0`
- PyArrow: `25.0.0`
- Storage: verified writable named volume, XFS
- Cache condition: `retained-dependency-cache`
- Cgroup safety limit: `8 GiB` exact; effective sample limit also `8 GiB`

The remote journal records a wall-clock duration of approximately 2 h 20 m 36
s. The target service completed successfully on the remote host.

## Coverage and hard gates

- Records: `66/66`
- Normal: `30/30`
- Scaling: `36/36`
- Unique measurement keys: `66`
- Warm-ups: `11`; measured records: `55`
- Execution failures: `0`
- Correctness failures: `0`
- Sample failures: `0`
- Candidate A matrix coverage, metadata, memory evidence, storage provenance,
  support envelope, batch contract and W2 byte split: all passed
- Every raw record had `batch_contract_valid=true`, verified storage mount
  provenance and exact `memory_limit_bytes=8589934592`
- W2 observed `max_batch_rows=562` and `max_batch_bytes=1048415`, within the
  v8 limits (`1024` rows and `1048576` bytes)
- W3 storage evidence: `12` available records; other normal/scaling records
  were not W3 workloads

The machine summary mechanically reports:

```text
formal_status = go
selected_provider = candidate_a_offline_cli
candidate_b_status = reserved_not_evaluated
p2_r2_ready = true
production_retest_required = true
```

Candidate B was not part of the 66-record matrix and has no pass/fail result.

## Advisory measurements

- Ratio observation: `warning`; maximum observed ratio was `4.077391` for the
  256-row cgroup final-window observation. Ratio is advisory-only in v8 and
  did not affect the hard gate.
- Resource advisory: `within_reference`
- Observed maximum workflow cgroup peak: `2577833984` bytes
- Ordinary workflow reference: `2684354560` bytes
- Recommended concurrency: `2`
- Capacity advisory: `within_reference`
- Capacity projection: `1543.524254` imports/day

## Artifact integrity

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `p2-r1-v8.jsonl` | 690097 bytes | `d9d31ca7ad4fc90d21f7b4ca0dc1d03493773c89ae18683fb76fd99b8d9dbf3d` |
| `p2-r1-v8.summary.json` | 10334 bytes | `0d0b72844e0ad9f01d16c57a006dc68882d0700c13a1b91a24caafb62f30fe73` |
| `p2-r1-v8.md` | 656 bytes | `0e2054c762073cfef093b75ea8159ffb72012c1bd28c5d05591c7e0bebf1ec57` |

Remote transfer archive SHA-256:

`f13406c93ffc1330a5a4e01e90f308fb211a2a5236348b32c55e08f11946c648`

## Cleanup and decision boundary

Remote verification showed no remaining container, project network or named
volume. The container, supervisor and samples cgroups were removed; the empty
per-run slice was then stopped and its cgroup path disappeared. No quarantine
was retained. Dependency cache, image and unrelated Compose projects were not
modified.

The machine artifacts are formal v8 evidence, but they have not yet received
the final human review. Until that review is complete, the external project
status remains:

```text
external_status = no-go
external_selected_provider = null
enter_p2_r2 = false
```

This archive does not activate Candidate A or authorize P2-R2 by itself.

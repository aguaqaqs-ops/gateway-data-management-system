# P2-R1 v8 Formal Go Decision Record

状态：Accepted — v8 formal decision approved

本记录是 P2-R1 当前有效的正式决定，supersedes
[P2-R1 2026-08-04 no-go decision](p2-r1-no-go-decision-2026-08-04.md)。旧记录保留为
历史证据，不删除、不覆盖。

## Decision

- `formal_status`: `go`
- `selected_provider`: `candidate_a_offline_cli`
- `default_provider`: `candidate_a_offline_cli`
- `candidate_b_status`: `reserved_not_evaluated`
- `candidate_b_sql_server`: preserved but disabled by default
- `p2_r2_status`: `authorized`
- `p2_r2_ready`: `true`
- `production_retest_required`: `true`

Candidate A 的 66 条 v8 formal records 通过全部 hard gates。Candidate B 未计入本轮
coverage，不产生 pass/fail 结论，也不得因代码仍存在而被默认启用。

## Provenance

- Source commit: `80aff3e6ff92e6d21aaa7fe73c9a2feafdc1efce`
- Formal artifact archive commits: `d7a0aa7`, `67a0d05`
- Image ID: `sha256:ddc7a41226ea50997ebaa8ec2c3227aa9b83adc7ee3bc1f226d661bf051cea98`
- Source tree digest: `sha256:ab97a6d628f24ede8ff4ed0adb24a0749d186e990b51073bffed0a0bc4ceeab1`
- Lock SHA-256: `fce9185b59b654729670c618c352f9f7a458fb2de40bbd2e088158e81a771e65`
- Methodology: `p2-r1-audit-corrective-v8`
- Dolt/uv/connector/PyArrow: `2.1.11` / `0.11.28` / `9.7.0` / `25.0.0`
- Formal run: `20260805011107_2971199`
- Compose project: `gateway-p2r1-20260805011107_2971199`

## Formal artifacts

All three artifacts are archived unchanged under
[p2-r1-v8-formal-80aff3e-2026-08-05](p2-r1-v8-formal-80aff3e-2026-08-05/):

| Artifact | SHA-256 |
| --- | --- |
| [raw JSONL](p2-r1-v8-formal-80aff3e-2026-08-05/p2-r1-v8.jsonl) | `d9d31ca7ad4fc90d21f7b4ca0dc1d03493773c89ae18683fb76fd99b8d9dbf3d` |
| [machine summary](p2-r1-v8-formal-80aff3e-2026-08-05/p2-r1-v8.summary.json) | `0d0b72844e0ad9f01d16c57a006dc68882d0700c13a1b91a24caafb62f30fe73` |
| [runner report](p2-r1-v8-formal-80aff3e-2026-08-05/p2-r1-v8.md) | `0e2054c762073cfef093b75ea8159ffb72012c1bd28c5d05591c7e0bebf1ec57` |

## Scope and retained boundaries

- Formal coverage is Candidate A only: `66/66` records, `30` normal and `36`
  scaling, with zero execution or correctness failures.
- Validated support is pinned to at most `100,000` rows and replay SQL no larger
  than `200 MiB`.
- `100,000`–`1,000,000` rows remain controlled preview only, not a production
  support declaration.
- Recommended concurrency is `2`; resource, ratio and capacity observations are
  advisory and are not production hard thresholds.
- `production_retest_required=true`: before production activation, capacity,
  resource use and lifecycle must be retested in a production-equivalent
  environment with real business samples.
- No new 66-record synthetic rerun is required unless provider streaming, Arrow
  normalization, batch contract, Dolt/connector/lock, cgroup runner or the formal
  execution environment changes.

## Review conclusion

The final review approved the v8 formal result. This record authorizes P2-R2
planning/implementation entry and establishes Candidate A as the default provider
policy; it does not by itself activate production traffic or enable Candidate B.

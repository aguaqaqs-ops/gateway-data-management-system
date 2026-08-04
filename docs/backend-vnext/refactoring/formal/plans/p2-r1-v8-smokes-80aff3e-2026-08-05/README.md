# P2-R1 v8 W0 Smoke Archive

This directory archives the latest target-container v8 W0 smoke results after
the canonical payload normalization and mixed-oversized-batch gate fixes.
These are diagnostic-only results, not formal decision evidence.

## Provenance

- Source commit: `80aff3e6ff92e6d21aaa7fe73c9a2feafdc1efce`
- Source tree digest: `sha256:ab97a6d628f24ede8ff4ed0adb24a0749d186e990b51073bffed0a0bc4ceeab1`
- Image: `gateway-p2r1-repository:v8-smoke-80aff3e`
- Image ID: `sha256:ddc7a41226ea50997ebaa8ec2c3227aa9b83adc7ee3bc1f226d661bf051cea98`
- Methodology: `p2-r1-audit-corrective-v8`
- Dolt: `2.1.11`
- uv: `0.11.28`
- mysql-connector-python: `9.7.0`
- PyArrow: `25.0.0`
- Lock SHA-256: `fce9185b59b654729670c618c352f9f7a458fb2de40bbd2e088158e81a771e65`
- Cache condition: `retained-dependency-cache`
- Target storage: verified named volume, XFS filesystem, writable
- Cgroup safety ceiling: `8 GiB` (`memory.max=8589934592`)

The A and B runs used independent per-run Compose projects. The launcher
observed these run/project identities:

- Candidate A: run `20260805010138_2916939`, project `gateway-p2r1-20260805010138_2916939`
- Candidate B: run `20260805010152_2920193`, project `gateway-p2r1-20260805010152_2920193`

## Smoke results

Each side contains one W0 diagnostic record. Both raw records are v8, use the
1 MiB effective byte bound and the 1024 row bound, and are marked
`diagnostic_only=true` and `formal_decision=false`.

| Candidate | Records | Payload total | Max row | Status |
| --- | ---: | ---: | ---: | --- |
| Candidate A offline CLI | 1 | 344 bytes | 225 bytes | diagnostic pass |
| Candidate B SQL server | 1 | 344 bytes | 225 bytes | reserved diagnostic pass |

The normalized W0 payload totals and maximum row sizes now match exactly across
providers. Candidate B remains `reserved_not_evaluated`; it is not a v8 formal
candidate.

## Artifact integrity

### Candidate A

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `v8-smoke-80aff3e-a/a-w0.jsonl` | 7722 bytes | `2ac59b9738547408479d644d2190aa619fe66b359f97116c17825fd37c71ebeb` |
| `v8-smoke-80aff3e-a/a-w0.summary.json` | 2976 bytes | `336beefaadc179e38f901d29de3f355787a85fadd47f4dbfbf5358f9733ac00e` |
| `v8-smoke-80aff3e-a/a-w0.md` | 478 bytes | `cd3beb8eb265a287c5f390c0a921d35ada3cbbc87285831213ac5c9812abe6bb` |

### Candidate B

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `v8-smoke-80aff3e-b/b-w0.jsonl` | 7840 bytes | `9774003a040a6604d73e544aeadd74c7613e522fcab66d46dd010bb17d732bb3` |
| `v8-smoke-80aff3e-b/b-w0.summary.json` | 504 bytes | `3f40261414d4f1026df52ae67ef553585c46a2f3bb09bbcc10fb5733a50a2605` |
| `v8-smoke-80aff3e-b/b-w0.md` | 409 bytes | `767841de79288d938c162e00da057776c74f26e0e13d31486359411dc23adadc` |

The remote transfer archive was independently verified before extraction:

`f804784b6df2e2b4648b7709913dc65a02ad8d9b27529009d808b35105c40c3a`

## Cleanup and decision boundary

Both target runs completed artifact publication and project-scoped cleanup.
Container, network, named-volume and per-run cgroup cleanup were verified; no
quarantine was retained for these two successful smoke runs. Dependency cache,
images and unrelated Compose projects were not removed.

The smoke results do not select a provider and do not authorize P2-R2:

```text
formal_status = no-go
selected_provider = null
enter_p2_r2 = false
```

The 66-record v8 formal matrix has not been run in this archive.

# P2-R6-S6 Entry Readiness — R6-EXT-W1

状态：`not_ready`

本记录只处理 `R6-EXT-W1` 的外部入口准备。没有开始 S6 容量证据、W2、
1/4/8 concurrency matrix、S7 Compose lifecycle 或 S10 final gate。

## Entry identity

```yaml
start_sha: b5b4cca3310959f45cc527ab3e7d4eb1754d12d3
head_sha_at_preparation: b5b4cca3310959f45cc527ab3e7d4eb1754d12d3
branch: phase1/gate-ownership-repair
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
worktree_clean_before_docs_only_commit: yes
selected_w1: medium
selection_reason: default representative W1; formal publication was blocked by the production type boundary
```

The selected source descriptor facts were independently recomputed:

```yaml
source_sql_bytes: 49323598
source_sql_sha256: sha256:78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f
source_sql_utf8: pass
source_descriptor_consistent: yes
```

Direct replay into a temporary Dolt repository using exact Dolt `2.1.11` completed and
returned the expected 199 tables. This is only a structural/semantic preflight and is
not S6 capacity evidence.

## Canonicalization and package result

The authorized initial producer scheme was prepared for evaluation:

```yaml
canonicalization_manifest_authority: one-off initial producer scheme under explicit task-owner authorization
canonicalization_algorithm: RFC8785-JCS + gateway-vnext:canonicalization-manifest:v1\0 + SHA-256
canonicalization_manifest_digest: not_computed
formal_package_media_type: application/vnd.gateway.repository-import.v1+tar+zstd
formal_package_bytes: not_published
formal_package_sha256: not_published
replay_sql_bytes: not_published
replay_sql_sha256: not_published
```

The production `ImportManifest` SQL type gate rejects unmappable `ENUM` and `SET` types.
The medium candidate contains 328 such columns. The only permitted fallback was also
checked: `data2` contains 545 unmappable columns, including 544 `ENUM` and 1 `SET`.
Therefore neither candidate can produce a manifest that is simultaneously exact to the
Dolt catalog and accepted by the current production model. No stringify, SQL-type rewrite,
or fabricated digest was used.

```yaml
schema_and_public_facts_preflight: direct replay pass; table count pass; production type gate fail
production_validator_result: not_run; no production-valid package existed to validate
read_only_access_proof: descriptor-only controlled handoff; directory mode 0555, descriptor mode 0444; formal package unavailable
external_descriptor_sha256: sha256:4098ccb7d2671874a2abbb66be284e2341f77463701f2f67ea0f6cd8cf175295
external_descriptor_bytes: 2746
raw_payload_in_git: false
runtime_cleanup: pass; temporary Dolt HOME, staging, server process and temporary container count zero
```

The external descriptor is `not_ready` and contains only safe summaries. It does not contain
raw SQL, full schema values, rows, secrets, host paths or a formal package.

## Handoff

```yaml
owner_anonymization_approval: owner-declared fully desensitized; task owner explicitly authorized the one-off producer scheme
repository_files_committed: this docs-only readiness record
container_rebuild_required: no
production_retest_required: yes
phase_2_complete: no
R6-EXT-W1: no
P2-R6-S6_ready: no
remaining_blockers:
  - current production ImportManifest/arrow mapping rejects ENUM and SET SQL types; both allowed W1 candidates fail this boundary
```

This record does not modify historical S5 Step E evidence. The S5 image evidence remains
bound to `e7a6e42d`; no image rebuild was triggered.

# P3-R7 Mutation and Target Closure Design Baseline

状态：Accepted design baseline；S0 entry freeze complete；implementation authorization pending

日期：2026-08-22

Owner：Backend vNext Canonical Storage / Mutation Planner / External Target Sync

上游 handoff：[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)、[P3-R6 Risk, Surface and Bundle Handoff](p3-r6-risk-surface-bundle-handoff.md)

Normative contracts：[Storage Mutation and Change Set](../contracts/storage-mutation-and-change-set.md)、[External Target Sync and Recovery](../contracts/external-target-sync-and-recovery.md)

本文冻结 P3-R7 的 target-neutral mutation planning、ChangeSet closure、确定性 Dolt renderer 和
fault-injectable reference executor 边界。R7 不授权真实 Repository/Dolt effect、P5B flow 接线、
durable Operation Runtime 或 production external target adapter。

## 1. Objective

R7 将 R4 的 immutable canonical storage projection 转换为可复验的 mutation plan 和
target-neutral `ChangeSetArtifact`，并验证 Dolt replay 与 external target apply 的公共语义。

```text
R4 immutable canonical before/after projection
  -> StorageMutationPlan
  -> REBUILD_TABLE | PATCH_DML | NOOP per table
  -> ChangeSetArtifact
  -> deterministic Dolt renderer / external target sync
```

## 2. Scope and non-goals

### 2.1 In scope

- immutable `StorageMutationPlan`、`ChangeSetArtifact`、manifest 和 semantic digest；
- `REBUILD_ALWAYS` 与显式启用的 `ADAPTIVE_PATCH`；
- per-table mixed `REBUILD_TABLE` / `PATCH_DML` / `NOOP` planning；
- initial/empty baseline、table add/remove、schema/key/projection change 和 destructive confirmation boundary；
- deterministic Dolt `replay.sql` artifact generation；
- in-memory fault-injectable external target reference executor；
- before-image guards、exact affected-row checks、idempotency、drift、readback 和 fail-closed recovery tests；
- R7 budgets, golden fixtures, benchmark evidence and architecture/import review.

### 2.2 Out of scope

- real Repository/Dolt writes, commit/ref publication or repository lifecycle；
- P5B Submit/finalize, confirmation persistence, authorization, durable business state and flow wiring；
- P4 Operation Runtime, lease, checkpoint takeover and durable unknown-outcome reconciliation；
- production PostgreSQL or other external target adapters；
- cache, retention, artifact GC, orphan reclamation and cross-target transactions；
- frontend comparison records as mutation input；
- arbitrary caller SQL, shell interpolation, silent value stringification or automatic patch/rebuild fallback.

## 3. Authority and owner DAG

```text
R4 CanonicalizationManifest / RepositoryImportArtifactInput
  -> R7 Mutation Planner
       -> ChangeSetArtifact
            -> Dolt Renderer
            -> External Target Reference Executor
```

| Object | Owner | R7 treatment |
| --- | --- | --- |
| `CanonicalizationManifest` / `RepositoryImportArtifactInput` | R4 storage projection | immutable authoritative input |
| `StorageMutationPlan` | R7 mutation planner | R7-owned plan and policy identity |
| `ChangeSetArtifact` | R7 mutation planner | immutable structured mutation closure |
| Dolt `replay.sql` | R7 Dolt renderer | derived deterministic artifact; no execution |
| external apply state | R7 reference executor, later P4/P5 durable owner | in-memory state machine only |
| confirmation, expiry, actor policy | P5B application | R7 carries requirement/digest only |
| repository commit/ref and operation evidence | Repository Service | R7 does not own |

R7 may consume an R6 bundle only as an immutable preview/result reference where a later consumer needs
provenance. Surface or Bundle data is never mutation authority.

The implementation package boundary is explicit:

```text
gateway_backend.capabilities.mutation_planning
  owns StorageMutationPlan, ChangeSetArtifact, planner and ChangeSet closure

gateway_backend.capabilities.external_target_sync
  owns target-neutral apply contract and in-memory reference executor
  consumes only public ChangeSetArtifact and shared canonical/artifact ports
```

The Dolt renderer remains a target-specific submodule of `mutation_planning` for R7, but may not import
Repository/Dolt execution adapters. S1 must add the `external_target_sync` capability to the architecture
owner graph and prove that it cannot import planner-private modules.

## 4. Plan policy and eligibility

`REBUILD_ALWAYS` is the default policy. `ADAPTIVE_PATCH` only enables per-table eligibility checks; it
does not force patching. A table may use `PATCH_DML` only when canonical key/projection/schema are stable,
the table is not keyless/ordered/degraded/unsupported, no unmodeled side effect exists, the renderer
supports all logical types and conditional DML/readback, `changed_row_count <= 1,000`, and
`changed_row_count / max(before_row_count, after_row_count, 1) <= 5%`.

Any schema, key or storage projection change uses `REBUILD_TABLE`. Unsupported renderer capability is a
stable `TARGET_CAPABILITY_UNSUPPORTED` failure; the plan never silently changes operation kind.

Initial and empty baselines are explicit:

- missing before + non-empty after: rebuild only;
- non-empty before + empty after: destructive full deletion requires explicit confirmation;
- both empty: `NOOP`, with no transaction and no empty commit;
- table add/remove: table-level rebuild/drop semantics, never row-patch masquerading.

## 5. ChangeSet identity and apply semantics

Plan and artifact identity bind source identity, base repository commit/ref, target identity/dialect,
before/after storage projection digests, policy/threshold version, renderer capability/version and
canonical encoding/schema version. Any change creates a new identity; equal identity is idempotently
reusable.

One ChangeSet maps to one renderer transaction/commit. Operations are deterministic:

```text
tables by canonical identity
DELETE -> UPDATE -> INSERT
within each phase by canonical storage key
```

`UPDATE` and `DELETE` carry before-image guards and require exact affected-row counts. `INSERT` on an
existing key is a conflict. Any guard, encoding, capability or readback failure rolls back the whole
batch and publishes no successful effect.

Artifact formats are deliberately separate:

- ChangeSet closure: canonical JSON document with manifest and semantic digest;
- Dolt renderer: independent deterministic `replay.sql` golden artifact;
- reference executor: test-only JSON checkpoint/state fixture, never a production durable record.

## 6. Confirmation, renderer and recovery boundaries

Destructive plans carry `requires_confirmation` and a stable reason. R7 does not persist, authorize or
revoke confirmation; P5B validates confirmation together with expected base, identity and idempotency.

The Dolt renderer emits only controlled canonical DDL/DML with adapter identifier quoting and canonical
value encoding. It never accepts caller SQL or interpolates shell text. Unsupported logical types,
generated/server-default columns, foreign-key/trigger/cascade behavior or other unmodeled capabilities
fail closed.

The reference executor uses:

```text
PREPARE -> APPLYING -> VERIFYING -> SUCCEEDED | FAILED | UNKNOWN_OUTCOME
```

Unknown outcome must reconcile target ledger/transaction/readback before retry; blind replay and new
idempotency identities are forbidden. Durable checkpoint, lease, takeover and multi-target state belong
to P4/P5.

## 7. Resource, artifact and benchmark policy

R7 inherits existing R4/R5 artifact and canonical encoding caps. R7-specific frozen limits are:

| Budget | Limit | Exceedance |
| --- | ---: | --- |
| changed rows eligible for patch | 1,000 | use rebuild or reject by eligibility |
| adaptive patch change ratio | 5% | use rebuild or reject by eligibility |
| rendered `replay.sql` | 200 MiB | direct rejection; no split/fallback |

ChangeSet and renderer artifacts remain pinned through validation/readback/audit. Cache, retention, GC
and orphan reclamation remain deferred under ADR 0012. Benchmarks are measurement-only and record
dataset/revision, policy, renderer, wall time, CPU, RSS, queue wait, artifact bytes and cancellation
latency; no numeric performance gate is introduced.

## 8. Acceptance and reopen

R7 must prove deterministic plan/artifact/renderer digests, mixed plan correctness, no-op and initial
baseline behavior, destructive confirmation, schema/key changes, threshold boundaries, input reorder,
before-image conflict, duplicate identity, renderer capability failure, replay-size rejection, atomic
rollback, crash, unknown-outcome reconcile, retry idempotency and readback mismatch.

Reopen R7 or its owning contract if mutation authority moves to R6 presentation data, plan identity is
not immutable, effect is partially published, unknown outcomes are blindly replayed, unsupported values
are stringified, a new helper/service/security principal is proposed, or durable P4/P5 state is added to
the R7 capability.

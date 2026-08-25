# P4-R4-S4 Focused Review

状态：**PASS AFTER S5 FOCUSED REREVIEW — S6 required and not authorized**

日期：2026-08-25

Reviewer：Independent R4 focused reviewer

上游：P4-R4-S0 entry brief、P4-R4 detailed execution plan、S1a-S3c handoffs、R1/R2/R3
handoffs、ArtifactStore/Operation contracts

```yaml
step_id: P4-R4-S4
context: mandatory_new_conversation
change_kind: review_docs_only
input_handoff_sha: 3a8d9ff3dec8502258629d68347657a1ca958d37d71c78270f2f6de606ff85de
input_validated_code_sha: pending_explicit_commit_authorization
reviewed_head: 9ea535e138a7e498aeade69042bfbbff559fcfc0
reviewed_candidate_sha: uncommitted_worktree_candidate
validated_source_tree: sha256:910537f9cb1780269824745852f6d5d89da194ae217f90a6dac80ce69ecd7063
candidate_worktree_at_entry: tracked_and_untracked_r4_source_test_changes
result: pass_after_s5_focused_rereview
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s4-focused-review.md
focused_tests: pass_143_unit_29_integration_8_serial
backend_unit: pass_143_selected_unit
integration: pass_29_non_serial
serial: pass_8
five_package_static: pass
container_rebuild_required: yes
container_reason: S2b changed worker bootstrap/composition boundary
last_verified_image_revision: none_for_r4_candidate
container_gate: deferred
benchmark: not_applicable_no_performance_claim
findings:
  - id: P4-R4-S4-F1
    status: closed
  - id: P4-R4-S4-F2
    status: closed
  - id: P4-R4-S4-F3
    status: closed
deferred_items:
  - S6 independent review
  - S7 current-HEAD image build and container smoke
reopen_conditions:
  - any fix requiring R1/R2 schema, status, CAS or error-taxonomy changes
  - any fix requiring R5 retry/takeover/reconcile policy or real Repository effect
  - any fix requiring a second registry, executor, IPC, cleanup/evidence state machine or new principal
next_step: P4-R4-S6
next_step_authorized: no
```

## 1. Review basis and decision

The reviewer read the complete R4 entry brief and plan, all S1a-S3c handoffs, the R1/R2/R3
handoffs and contracts, every R4 application source file, the changed bootstrap/worker source,
the R4 tests, the changed R3 tests, and the complete current diff. The review did not rely on the
handoff PASS summaries alone.

The package direction is otherwise preserved: Operations does not import application code;
unknown keys and versions are checked before claim; handlers use the existing `ArtifactStorePort`
and R3 `LeaseSession`; checkpoint/closure writes occur before publication CAS; READY closure is
set once; the external stub does not use network, Dolt or Repository paths; and logs remain bounded.
The three findings below blocked the initial focused review because they violated persisted document integrity,
the immutable-registry boundary, or a valid payload representation promised by S1b.

## 2. Finding and disposition table

| Finding | Severity | Owner | Required disposition |
| --- | --- | --- | --- |
| P4-R4-S4-F1 | P2 | `application.checkpoints` | Reject non-canonical JSON and duplicate keys before constructing checkpoint or READY-closure documents; add one parameterized unit owner for both decoder axes and rerun S4. |
| P4-R4-S4-F2 | P2 | `application.job_definitions` / `application.payloads` | Deep-freeze registry maps (including the R3 executor adapter and decoder registry) so process-local lookup cannot be mutated after composition; add mutation regression coverage. |
| P4-R4-S4-F3 | P2 | `application.synthetic_jobs` / payload decoder boundary | Make both synthetic handlers consume the already validated decoder result or use the shared loader, so valid `job_payload_ref` operations execute identically to inline payloads; add inline/ref parity coverage. |

### P4-R4-S4-F1 — P2: checkpoint and READY closure decoders accept non-canonical and duplicate-key JSON

`StepCheckpointEnvelope.from_canonical_bytes()` at
`vnext/backend/src/gateway_backend/application/checkpoints.py:169-177` and
`ReadyClosureDocument.from_canonical_bytes()` at `:300-308` call `json.loads()` and then parse the
resulting dictionary. They never compare the input bytes with `canonicalize_jcs(raw_bytes)` and
therefore accept whitespace/key-order changes. JSON duplicate keys are also silently collapsed by
`json.loads()` before `_require_closed_document()` sees the dictionary. This contradicts the
versioned JCS document requirement and permits two byte representations, or two meanings for a
duplicate field, to enter the checkpoint/closure path.

The counterexample was run against the reviewed tree:

```text
uv run python - <<'PY'
... StepCheckpointEnvelope.from_canonical_bytes(noncanonical_bytes)
-> accepted_noncanonical_checkpoint True
... StepCheckpointEnvelope.from_canonical_bytes(duplicate_key_bytes)
-> accepted_duplicate_checkpoint_key other
```

S5 must keep the fix inside the application decoder owner. It must reject non-canonical bytes,
duplicate keys, and raw documents outside the existing bounded JSON policy before any semantic
document is returned. A regression must cover both checkpoint and closure paths with a shared
parameter table. No R1/R2 schema change or new evidence mechanism is authorized.

### P4-R4-S4-F2 — P2: the claimed immutable registries retain mutable dictionaries

`JobDefinitionRegistry.build()` stores the mutable `by_key` dictionary directly at
`vnext/backend/src/gateway_backend/application/job_definitions.py:89-104`. The worker adapter stores
the mutable `bound` executor dictionary at `:228-250`; `PayloadDecoderRegistry.build()` similarly
stores a mutable `bound` dictionary at
`vnext/backend/src/gateway_backend/application/payloads.py:63-72`. `@dataclass(frozen=True)` only
prevents replacing the field; it does not freeze the mapping. The private maps can therefore be
changed after startup and alter `get()`/`resolve()` behavior, despite the frozen contract forbidding
dynamic registration and hot reload.

The reviewed tree reproduces this directly by assigning a second `JobDefinition` into
`registry._by_key` and then resolving the new version. S5 must use a read-only mapping (or an
equivalent deep-freeze owned by the application composition) for every registry lookup map and add
a regression that attempts mutation and proves the lookup remains unchanged. This finding does
not authorize a durable registry, watcher, new executor, or R3 protocol widening.

### P4-R4-S4-F3 — P2: synthetic handlers bypass the shared payload/ref decoder

The composition wrapper correctly calls `decode_job_payload()` in
`vnext/backend/src/gateway_backend/application/job_definitions.py:253-275`, and S1b explicitly
supports either inline `job_payload` or an exact `job_payload_ref`. The actual synthetic handlers
then bypass that result: `build_pure_compute_handler()` calls `_load_pure_compute_payload()` at
`vnext/backend/src/gateway_backend/application/synthetic_jobs.py:152`, whose helper at `:554-567`
rejects every operation without inline bytes; the external-effect stub does the same through
`_load_external_effect_stub_payload()` at `:276` and its helper. A valid persisted operation with
an exact, readable payload artifact is decoded successfully by the wrapper and then fails inside
the handler with `PAYLOAD_SHAPE_INVALID`.

This is a compatibility failure at the first R4 consumer, not merely duplicate test logic. S5 must
make the handler consume the typed decoder output or call the shared `load_job_payload_bytes()` path
with the injected store. The regression must run both synthetic jobs through inline and artifact-ref
payloads and assert equal semantic output/identity. It must not add a second decoder or broaden the
payload contract.

## 3. Initial review matrix

| Review item | Disposition | Evidence |
| --- | --- | --- |
| JobDefinition owner, key/version and Operations direction | pass | Application owns descriptors; Operations has no application import; bootstrap supplies the adapter. |
| Unknown key/version and empty-registry behavior | pass | Startup and claim preflight leave queued/pending records unchanged; focused integration tests pass. |
| Decoder bounds and version-axis separation | rework required | F1 permits non-canonical/duplicate checkpoint and closure bytes; payload decoder itself is strict. |
| ArtifactRef path/size/digest/identity boundary | pass | Exact `locate`, digest verification, and idempotent `put` tests pass. |
| Step checkpoint authority and CAS freshness | pass | Active Step ref and R3 session publication are used; stale CAS leaves no READY ref. |
| READY closure completeness and set-once | pass | Exact sorted refs, readback verification and set-once integration tests pass. |
| Deterministic output, terminal duplicate and cancellation | pass | Pure/stub focused and recovery tests pass; no R5 takeover claim is made. |
| External stub identity/unknown/R5 boundary | pass | Unknown maps to bounded manual recovery and reload does not resubmit. |
| Immutable registry and no hot reload | rework required | F2 finds mutable internal dictionaries in all registry layers. |
| Handler/ref payload compatibility | rework required | F3 finds synthetic handlers rejecting the S1b-supported artifact-ref form. |
| No handler/artifact I/O in DB transactions | pass | R3 session builders receive fresh records; artifact preparation is outside publication UoW. |
| Marker ownership and parameter-table convergence | pass | Selected gates pass; R4 integration/serial ownership is explicit and no Dolt fixture is used. |
| Bootstrap/container trigger and log redaction | pass with deferral | S2b changes bootstrap, so the required current-HEAD image gate remains deferred to S7; selected process tests pass. |

## 4. Initial verification record

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_job_definition_contracts.py tests/test_job_definition_registry.py \
  tests/test_job_payload_decoding.py tests/test_operation_checkpoint_contracts.py \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py \
  tests/test_architecture.py
  -> 132 passed, 30 deselected

cd vnext/backend && uv run pytest -q -m 'integration and not serial' \
  tests/test_job_payload_decoding.py tests/test_operation_checkpoint_contracts.py \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
  -> 29 passed, 60 deselected

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_operation_job_recovery.py tests/test_operation_worker_process.py \
  tests/test_operation_worker_integration.py
  -> 8 passed, 22 deselected

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 229 source files

git diff --check
  -> pass
```

The focused tests are regression evidence only; they do not close F1-F3. No Dolt, Repository
integration, benchmark, or production-effect validation was run.

## 5. Container and authorization disposition

```text
Current HEAD: 9ea535e138a7e498aeade69042bfbbff559fcfc0
Container rebuild required: yes
Reason: S2b changed worker bootstrap/composition boundary
Last verified image revision/source tree: none for the R4 candidate
Container gate for current HEAD: deferred
Required execution point: P4-R4-S7 final committed candidate
```

The initial S4 review completed with `rework_required`; S5 was authorized only through its
finding-scoped appendix. The initial decision did not authorize S6 or S7, and did not authorize R5,
P5, Dockerfile, Compose, real Repository effect, or cross-owner contract changes.

## 6. S5 focused rereview

S5 remediation was reviewed against the authorized appendix and handoff, then the complete changed
source/test files and current worktree were reread. The fixes remain within the three finding-scoped
path sets; no bootstrap, R1/R2 schema, R5 policy, dependency, deployment or container-boundary path
was changed.

| Finding | Rereview result | Independent closure evidence |
| --- | --- | --- |
| P4-R4-S4-F1 | **closed** | `_parse_canonical_document_bytes()` canonicalizes and requires byte equality before parsing. The shared `CANONICAL_DOCUMENT_BYTE_FAULTS` owner rejects non-canonical and duplicate-key checkpoint and closure bytes; the original counterexamples now fail closed. |
| P4-R4-S4-F2 | **closed** | `MappingProxyType` wraps `_by_key`, `_executors` and `_decoders` at build time. Mutation probes raise `TypeError` and lookup remains unchanged. |
| P4-R4-S4-F3 | **closed** | Both synthetic handlers use `load_job_payload_bytes()` before typed decoding. `PAYLOAD_BINDING_PARITY` covers inline/ref bindings for pure-compute and external-effect-stub and proves equal semantic output/identity. |

Rereview gates:

```text
focused unit -> 143 passed, 30 deselected
integration and not serial -> 29 passed, 69 deselected
serial -> 8 passed, 22 deselected
backend ruff/mypy -> pass; mypy 229 source files
shared_kernel ruff/mypy -> pass; mypy 34 source files
repository_contracts ruff/mypy -> pass; mypy 15 source files
repository_client ruff/mypy -> pass; mypy 26 source files
repository_service ruff/mypy -> pass; mypy 195 source files
git diff --check -> pass
```

The focused rereview is `pass_after_s5_focused_rereview`. S6 independent review remains required
and unauthorized; S7 remains responsible for the current-HEAD image rebuild and container smoke.
The container decision is unchanged:

```text
Current review input HEAD: 9ea535e138a7e498aeade69042bfbbff559fcfc0
Reviewed source/test tree: sha256:910537f9cb1780269824745852f6d5d89da194ae217f90a6dac80ce69ecd7063
Container rebuild required: yes
Reason: S2b changed worker bootstrap/composition boundary
Last verified image revision/source tree: none for the R4 candidate
Container gate: deferred
Required execution point: P4-R4-S7 final committed candidate
```

No new finding or reopen condition was found. This rereview authorizes no S6 implementation, R5,
P5, Dockerfile, Compose or real Repository effect work.

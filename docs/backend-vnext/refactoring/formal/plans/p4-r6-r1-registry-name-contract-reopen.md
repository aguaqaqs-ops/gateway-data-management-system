# P4-R6/R1 Registry-Name Contract Reopen

状态：**ACCEPTED — bounded registry-name grammar amendment validated by R6-S0 rereview**

日期：2026-09-13

Owner：Operation Runtime (`gateway_backend.operations`) + Backend vNext Architecture Acceptance

上游：[P4-R6-S0 Entry Brief](p4-r6-s0-entry-brief.md)、
[P4/R1 Runtime Contract and State Handoff](p4-r1-runtime-contract-state-handoff.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[P5-5A Upload/Preview Design](p5-5a-upload-preview-design.md)

```yaml
disposition_kind: p4_r6_r1_registry_name_contract_reopen
input_candidate_head: 7e8cea7b3454a8cfdd7c2ba880becee5c427a0de
input_r1_validated_code_sha: e2703407a1c80d31f6888ce86c0ab9b125464ad5
input_r5_validated_code_sha: 0fa2b897a75436b4319d4490bc97c54ced494783
triggered_reopen_condition: post_R5_change_to_Operation_and_Step_registry_name_acceptance
result: accepted_docs_only_contract_amendment
accepted_registry_name_pattern: "[A-Za-z0-9._:/-]{1,128}"
slash_semantics: opaque_namespace_character_only
runtime_contract_version_changed: false
persisted_keys_changed: false
schema_or_migration_changed: false
status_or_cas_semantics_changed: false
production_or_tests_modified_by_this_disposition: false
p4_r6_s0_acceptance: accepted
p4_r6_implementation_authorized: no
next_step: issue_P4-R6-S1-S7_gate_execution_task
next_step_authorized: no
```

## 1. Trigger and decision

R1 sealed `job_kind` / `step_name` as 1..128 ASCII characters from
`[A-Za-z0-9._:-]`. Current candidate `7e8cea7b` contains a post-R5 change that accepts `/`, and the
accepted P5-5A consumer uses `job_kind: backend-vnext/preview`. Because the validator is part of the
Operation/Step persisted admission boundary, R6-S0 correctly stopped instead of treating that change
as an unreviewed composition detail.

The owning decision is to accept the bounded widening:

```text
job_kind, step_name, BusinessReference.kind:
  length: 1..128 ASCII characters
  exact character set: [A-Za-z0-9._:/-]
```

`/` is an opaque namespace character. It is not a filesystem separator, URL delimiter, hierarchy,
authorization scope or routing instruction. Registry names remain data-only identities and must not
be joined to a host path. The amendment accepts every value valid under R1 and one additional
character, so it requires no migration or compatibility shim and retains
`backend-vnext/operation-runtime/v1`.

Renaming the accepted P5 consumer was rejected: `backend-vnext/preview` is already frozen in the P5
design and may already exist in durable records. A rename would create avoidable persisted-identity
migration and compatibility work without reducing a current threat.

## 2. Bounded owner matrix

| Dimension | Accepted | Explicitly rejected |
| --- | --- | --- |
| Grammar | Add `/` to the existing bounded registry-name character set | Whitespace, backslash, control characters, Unicode or unbounded names |
| Meaning | Opaque namespace identity | Path, URL, hierarchy, routing or authorization semantics |
| Persisted contract | Existing `job_kind`, `step_name` and `BusinessReference.kind` fields | New field, alias, second registry or compatibility shim |
| Version/schema | Retain runtime v1 and Operations schema v1 | Version bump, data migration or schema change for this widening |
| P5 boundary | Permit the existing Preview JobDefinition consumer | Pull Workspace/HTTP/PreviewResult or Repository Submit effect into R6 |

## 3. Required remediation and regression proof

The production validator already implements the accepted pattern. The separately authorized
tests-only remediation closed the finding by:

1. Add explicit positive contract cases proving `backend-vnext/preview` and a slash-bearing
   `BusinessReference.kind` round-trip through the R1 constructors and document parsers.
2. Retain shared negative cases for empty, overlong, whitespace and backslash-containing names.
3. Add `serial` to
   `test_operation_worker_integration.py::test_registered_key_reaches_ready_with_empty_queue`, which
   uses fixed `Event.wait` and `Thread.join` timeouts.
4. Running the R1 contract owner tests, the affected worker integration/serial owners and
   five-package ruff/mypy before the repeated P4-R6-S0 independent entry acceptance.

The repeated review confirmed that no R2–R5 store index, registry lookup, checkpoint, recovery
identity, log field or artifact path interprets `/`; no R2–R5 contract reopen is required. See
[P4-R6-S0 Independent Entry Acceptance](p4-r6-s0-independent-entry-acceptance.md).

## 4. Verification and authorization boundary

This disposition is docs-only. No Python test, static check, Docker build, Compose gate or benchmark
was run, and no current-HEAD pass is claimed. The final R6 runner, process/fault matrix and image/
Compose provenance gates remain pending.

The remediation and focused validation are complete. The next permitted action requires new explicit
authorization for the P4-R6 S1–S7 gate-execution task. This reopen does not authorize P5-5B, S1–S7
execution or `p4_r6_exit`.

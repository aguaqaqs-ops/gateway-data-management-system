# P2-R6-S10 Independent Audit Adapter Review — Rerun

状态：`pass`

日期：2026-08-17

本记录是 S10-3 的新独立只读 rereview，审核对象为 S10-2 attempt-2 adapter。attempt-1
adapter、失败审核及失败步骤记录均原样保留；本审核没有修改 adapter、candidate、production、
test、dependency、Dockerfile、Compose、image、W1/W2 package 或已有 evidence。没有读取批准
的 W1 `medium` / W2 package，也没有启动 HTTP、Docker 或 Compose live path。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §5

审核设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.4

修复记录：[P2-R6-S10 Step 2 — Production-image W1/W2 Audit Adapter](p2-r6-s10-step-2-audit-adapter.md)

失败审核（保留）：[p2-r6-s10-audit-adapter-review.md](p2-r6-s10-audit-adapter-review.md)

## Reviewed identity and isolation

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_worktree_clean_at_review: yes
adapter: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py
adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
attempt_1_adapter_sha256: b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f
command_contract_sha256: 606610dc2473edd5e9aa53f591a028cd84adff98d66bb7fa32b31cc183ab817b
prior_failed_review_sha256: 7d6695b135b574eb4ef05317f0e37f02f884eb47bd9299ffcf600850f5f26976
review_kind: independent_read_only_adapter_review_rerun
approved_packages_read: no
production_code_changed_by_review: no
image_built_or_changed_by_review: no
phase_2_complete: no
```

The current adapter and command contract both pass the recorded `SHA256SUMS` check. Attempt-1
bytes remain under `adapter/attempt-1/` with the historical SHA above. Candidate `HEAD` is the
literal sealed candidate and its porcelain is empty. The S10-2 dry-validation record reports the
current adapter SHA, candidate HEAD/lock inspection, package-derived dummy manifest digest and
`container_pass: not_claimed`, `w1_w2_consumed: false`.

## Review results

### 1. Final-container boundary and isolation

**Pass.** The adapter remains external audit code. It does not import
`gateway_repository_service`, `gateway_repository_client`, `gateway_backend` or `r6_s6_lib`, does
not start a host runtime, and does not use HTTP retry. The endpoint check and Docker inspection
reject published host ports; the live path requires a cleanup option or an external cleanup receipt.
`FULL_SCAN` and `REJECT` remain hardcoded.

### 2. S10-3-01 — Candidate and image provenance

**Pass.** `verify_candidate_checkout` obtains `git rev-parse HEAD`, requires exact
`expected-candidate-sha`, requires empty porcelain, and hashes the candidate Service `uv.lock`
([adapter.py:243](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:243)).
The live path compares the running immutable image ID and all four required labels: candidate,
build-input, source-tree and Service lock ([adapter.py:1120](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:1120)).
Inspected labels are retained only as sanitized identity data.

### 3. S10-3-02 — Package manifest identity

**Pass.** The package is hashed and size-checked, `manifest.json` is parsed, and its
`canonicalization_manifest_digest` is required, normalized and compared to the expected descriptor
([adapter.py:885](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:885)).
The import result is compared to this package-derived digest, not merely to an independent argv
value ([adapter.py:933](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:933)).
The dry mismatch case exits `1` with `package canonicalization_manifest_digest does not match expected`.

### 4. S10-3-03 — Public HTTP identity and readback

**Pass.** Upload readback checks exact size, raw SHA and media type
([adapter.py:628](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:628)).
Terminal operation readback checks operation ID, artifact ID, `target_ref=main`, expected parent,
result commit, package digest, `FULL_SCAN` and `REJECT`
([adapter.py:933](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:933)).
Resolved `main` must equal the import result commit. A `200` catalog must bind its commit and the
selected manifest table row count; only HTTP `503` takes the documented manifest fallback
([adapter.py:966](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:966)).
Rows are read through public HTTP and checked for manifest row count, `unknown=0` and `lossy=0`.

### 5. S10-3-04 — Failure handling, cleanup and redaction

**Pass for the live operation path.** Sampler and client lifecycle, operational failure capture,
optional Compose down and final inventory are in one outer `try/finally`
([adapter.py:1151](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:1151)).
Transport/protocol exceptions become a generic sanitized failure; failed live attempts write
`status=FAILED`, `container_pass=not_claimed` and cleanup inventory before returning nonzero
([adapter.py:1215](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:1215)).
Live pass requires Compose cleanup with zero inventory or the explicitly declared external cleanup
receipt ([adapter.py:1288](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:1288)).
Output redaction rejects secrets and registered host paths. Dry-validation and the redaction log
do not claim live cleanup or container PASS.

### 6. S10-3-05 — Resource and path boundaries

**Pass.** `parse_docker_size` accepts `B`/`0B`; sampler errors stop sampling and are raised at
finish rather than swallowed ([adapter.py:468](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:468),
[adapter.py:590](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:590)).
The data root is fixed to `/var/lib/gateway/repository`, and both `df` and query-temp checks use
argv-only `docker exec` without `sh -c` ([adapter.py:499](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:499)).
The dry illegal-data-root case exits `1` with the expected fail-closed error.

## Verification performed

The following checks were read-only and consumed no approved package:

- Python AST parse passed for the attempt-2 adapter.
- AST scan found no `subprocess` call with `shell=True`.
- Pure checks passed for `parse_docker_size("0B")`, fixed data-root rejection, package manifest
  digest extraction and import identity assertions.
- Current and attempt-1 adapter hashes, command-contract hash and `SHA256SUMS` were verified.
- Retained dry-validation log showed success exit `0`, eight fail-closed cases exit `1`,
  `container_pass: not_claimed`, and `w1_w2_consumed: false`.

No live HTTP/Docker execution was performed, so this review does not claim W1/W2 production pass.
S10-6 must use exactly this adapter SHA; any byte change invalidates this review and reopens S10-3.

## Findings and verdict

```yaml
finding_count: 0
blocker_count: 0
high_count: 0
medium_count: 0
low_count: 0
prior_review_status: fail
prior_finding_count: 5
prior_findings_closed: yes
review_status: pass
allow_w1_w2_execution: yes
approved_packages_consumed: no
candidate_or_image_changed_by_review: no
production_retest_required: yes
S10_exit: no
S11_ready: no
phase_2_complete: no
next: S10-4 final Service/Client artifacts and provenance
```

This pass authorizes S10-4 and, after unchanged identities, the downstream S10-5/S10-6 steps.
It does not authorize a W1/W2 production result, S10 exit, S10 seal, S11 handoff or Phase 2
completion. The failed attempt remains immutable evidence and must stay in the final attempt ledger.

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (required at S10-4; this read-only review changed no image/deployment input)
Reason: S10 final Service/Client artifacts are not yet built; S9 provisional image remains non-final
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a (S9 provisional only)
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Required execution point: S10-4 rebuild, then S10-5 exact no-ignore gate and S10-6 W1/W2 with adapter SHA 6282df80…827ebf
```

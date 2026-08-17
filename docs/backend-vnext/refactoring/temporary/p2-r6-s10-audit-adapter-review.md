# P2-R6-S10 Independent Audit Adapter Review

状态：`fail`

日期：2026-08-17

本记录是 S10-3 的独立只读审核。审核没有修改 external adapter、candidate、production、
test、dependency、Dockerfile、Compose、image、W1/W2 package 或任何已有 evidence；没有
执行批准的 W1 `medium` / W2 package，也没有启动 HTTP、Docker 或 Compose live path。S10-2
的实现记录保持不变；以下 finding 必须返回 S10-2，修复后以新的 adapter SHA 重开本审核。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §5

审核设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.4

实现记录：[P2-R6-S10 Step 2 — Production-image W1/W2 Audit Adapter](p2-r6-s10-step-2-audit-adapter.md)

## Reviewed identity and isolation

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_worktree_clean_at_review: yes
adapter: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py
adapter_sha256: b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f
command_contract_sha256: 375ad75552475f18bef40dfafae950ebac78e90f5c19f84d72e41004c55eff5b
review_kind: independent_read_only_adapter_review
approved_packages_read: no
production_code_changed_by_review: no
image_built_or_changed_by_review: no
phase_2_complete: no
```

The adapter source parses successfully with Python `ast`. The S10-2 dry-validation output and
redaction log were inspected as retained evidence; they prove argument/redaction probes only and
do not prove a container or W1/W2 result. The expected external package identities remain the
S10 descriptor values: W1 `2081228` bytes / `3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e`,
W2 `8301271` bytes / `6cac7852d1174c126c182e82010b0ff9d4043e51826b8043103360c8e49f6d10`.

## Review results

### 1. Public boundary and import isolation

**Partial pass.** The adapter uses the supplied bridge endpoint, rejects localhost/loopback
endpoints, checks Docker host-port bindings, avoids `gateway_repository_service` and the host
`ServiceRuntime`, and hardcodes `FULL_SCAN`/`REJECT`. It performs no HTTP retry and its dry output
redacts token, package, candidate and output paths. These checks do not close the identity and
cleanup findings below.

### 2. Identity binding

**Fail.** `expected_candidate_sha` is only syntax-checked and copied into output
([adapter.py:705](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:705),
[adapter.py:1080](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:1080)).
`add_candidate_contracts` only checks that a contracts directory exists
([adapter.py:151](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:151));
it never verifies the checkout HEAD or clean state. `running_image_id` compares only the immutable
Docker ID ([adapter.py:288](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:288));
it never reads the required candidate/build-input/source-tree/lock labels. A caller can therefore
pair the reviewed SHA and expected image ID with a different checkout or image while the adapter
reports the claimed identity.

**Finding S10-3-01 (blocker):** fail closed unless the candidate checkout resolves to the expected
commit and the running image labels resolve to the expected candidate provenance (at minimum the
candidate revision; the final artifact review also requires the build-input/source-tree/lock
labels). Preserve the actual inspected values in sanitized evidence. Owner: S10-2; any byte change
invalidates this review and requires a new S10-3 review before S10-6.

### 3. Package and manifest identity

**Fail.** `load_package_manifest` parses the package manifest but does not read or validate its
`canonicalization_manifest_digest` ([adapter.py:224](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:224)).
`verify_package_identity` returns the manifest without deriving that digest
([adapter.py:767](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:767)).
The live path merely compares the service result to the caller-supplied `--expected-manifest-digest`
([adapter.py:963](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:963)).
The dry sample consequently passes with an arbitrary `sha256:aaaa...` digest that is not tied to
the dummy package. A wrong or missing package manifest digest can pass the adapter if the same
wrong value is supplied on argv.

**Finding S10-3-02 (blocker):** extract and validate the package's manifest digest, require it to
equal the approved descriptor value, and compare the service result with that package-derived
value. Missing, malformed or mismatched manifest identity must fail closed. Owner: S10-2; repeat
S10-3 and all adapter-owned W1/W2 evidence after repair.

### 4. Public HTTP facts and readback

**Fail.** The upload response checks only that four keys exist; it does not compare `size_bytes`,
`raw_sha256` and `media_type` with the bytes and media type sent
([adapter.py:535](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:535)).
The import result checks status, manifest digest and policies but not `operation_id`, `artifact_id`,
`target_ref`, `expected_commit_id` or the returned `commit_id`
([adapter.py:950](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:950)).
The resolved `main` commit is then used without comparing it to the import result commit
([adapter.py:969](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:969)).
When catalog returns `200`, only that `tables` is a list and its length are checked; the catalog
commit and selected table facts are not validated ([adapter.py:972](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:972)).
This permits an inconsistent public response/read chain to be recorded as `SUCCEEDED`.

**Finding S10-3-03 (high):** validate every public identity edge: upload ref exact size/SHA/media
type; operation ID and result artifact/target/expected-parent/commit; resolved `main` equals the
successful result commit; and successful catalog commit/table/row facts match the selected package
table. The documented 503 manifest fallback must remain explicit and fail closed for other malformed
responses. Owner: S10-2; repeat S10-3 and S10-6 after repair.

### 5. Failure cleanup and attempt safety

**Fail.** Compose cleanup is optional and is reached only after the full HTTP path and post-import
disk checks succeed ([adapter.py:993](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:993)).
Any HTTP exception, malformed response, import failure, disk failure or row-stream failure exits
before `cleanup_compose`; the running project, container, repository data and query/work artifacts
are then left for an external operator. If client construction fails after `ResourceSampler.start`,
the sampler is not joined because the `try` block starts later ([adapter.py:939](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:939)).
The main handler catches only `AdapterError` ([adapter.py:1088](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:1088));
HTTP/JSON/UUID exceptions can bypass sanitized failure handling altogether. A successful record can
also have `compose_removed: false` and a nonzero project inventory when the optional flag is omitted.

**Finding S10-3-04 (high):** put the client, sampler and bounded Compose cleanup in an outer
`try/finally`, convert transport/JSON/UUID failures to sanitized fail-closed errors, and do not
emit a container pass until owned resources are zero (or an explicitly recorded external cleanup
receipt is supplied). Preserve every failed attempt and its cleanup inventory. Owner: S10-2;
repeat S10-3 and S10-6 after repair.

### 6. Resource and path boundaries

**Fail.** `parse_docker_size` rejects the normal Docker stats value `0B` because its regex requires
a unit prefix ([adapter.py:387](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:387)).
`ResourceSampler._loop` catches that error and silently continues
([adapter.py:500](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:500)),
so a live run can report a zero/absent memory peak without proving `docker stats` worked. In
addition, `query_temp_count` interpolates caller-controlled `--data-root-in-container` into
`sh -c` ([adapter.py:427](</root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py:427)),
and the path is not constrained to the server-owned data root. This violates the required
caller-input/root boundary and can execute arbitrary commands inside the Service container.

**Finding S10-3-05 (high):** accept all valid Docker byte forms including `B`, fail closed on
sampler errors instead of swallowing them, and constrain the data-root argument to the expected
absolute server-owned path. Replace the shell-based query-temp probe with a non-shell bounded
command or a safely encoded fixed-root probe. Owner: S10-2; repeat S10-3 and S10-6 after repair.

## Findings summary and route

```yaml
finding_count: 5
blocker_count: 2
high_count: 3
medium_count: 0
low_count: 0
review_status: fail
allow_w1_w2_execution: no
prior_s10_3_review: none
candidate_or_image_changed_by_review: no
approved_packages_consumed: no
production_retest_required: yes
S10_exit: no
S11_ready: no
phase_2_complete: no
next: S10-2 adapter repair, then a new independent S10-3 review
```

The adapter SHA is the reviewed identity. Any source-byte change, even a documentation or comment
change inside the external adapter file, invalidates this record. No S10-4, S10-5 or S10-6 execution
is authorized by this review. Findings must be repaired in S10-2; the failed review remains
immutable, and a new review must establish `finding_count: 0` and
`allow_w1_w2_execution: yes` before approved packages are transferred or consumed.

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: yes (S10-4; not authorized by this read-only adapter review)
Reason: S10 final Service/Client artifacts are not yet built; this review changed no image or deployment input
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a (S9 provisional only)
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Required execution point: S10-4 only after a passing S10-3 review; S10-6 must use the new reviewed adapter SHA
```

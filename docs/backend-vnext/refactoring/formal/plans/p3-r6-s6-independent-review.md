# P3-R6-S6 Independent Owner, Import, Digest and Recovery Review

状态：**S6 independent re-review complete；无未处理 P1/P2 finding；S7 current-candidate revalidation required**

日期：2026-08-22

本记录对既有 S6 PASS 重新执行独立复核。复核只依赖公开 contracts、当前累计 source tree、
tests 和下列命令，不依赖 S1-S5 implementer explanations。当前候选由以下二元身份精确标识：

```yaml
review_base_sha: e09ff32cc3562b744ff5718357a529c7b8ce3e6f
r6_source_test_patch_sha256: b7bd5f98c344c9ac61ddb8c4960fba581d35b53d54f6162221f9fef08a4cecbe
worktree: dirty_s6_independent_review_remediation_and_record
```

patch digest 只覆盖本记录 §7 列出的 R6 source/test paths，不包含 review 文档。它与 base SHA
共同固定本次实际测试的 dirty candidate；S7 必须先把该 candidate 原样 seal 为 commit SHA，
再在新 conversation 重跑 module/container disposition gate。原 `9739bf0` S7 gate 和 handoff 是
历史证据，不得表述为当前候选已验证。

## 1. Review boundary

独立复核覆盖：

- Risk、Surface、Bundle owner DAG 和 forbidden HTTP/application、flow、Repository/Dolt、
  legacy、private-provider、test-support imports；
- ruleset/comparison separation、status precedence、pair/table resource degradation、
  cancellation/deadline publication boundary；
- Risk/Surface/Bundle semantic digest ownership，raw ref/diagnostic exclusion，以及 artifact
  integrity 在 before/current/records/risk 等语义角色上的绑定；
- annotation、surface、manifest、closure 的 exact schema、canonical bytes、redundant semantic
  metadata binding 和 recovery replay；
- degraded no-record/no-partial-closure semantics、cross-pair sharing、logical path scope、
  host/cache/repository ref rejection；
- unit marker 分类及 Dolt/process/network/fixed-timeout absence。

Out of scope：static-risk provider、R5 comparison algorithm、cache/GC/retention、P5 flow、Rust
risk parity、production Repository/Dolt adapters 和 inherited image gate。

## 2. Independent findings register

| ID | Severity / disposition | Evidence |
| --- | --- | --- |
| `S6-001` | Bundle manifest/closure semantic binding / **P2 closed in prior review** | `validate_bundle()` recomputes manifest semantic payload and `bundle_manifest_digest` and rejects unknown top-level/full-entry fields. |
| `S6-002` | Artifact orphan lifecycle / **accepted defer** | A later destination write can leave opaque derived artifacts unreachable; no public Bundle ref is returned. Reclamation remains ADR 0012 lifecycle work because `ArtifactStorePort` has no delete/transaction primitive. |
| `S6-003` | Owner/import boundary / **pass** | Architecture DAG passes. Bundle still imports only Surface public seams; Surface imports only Risk public contracts; no flow, Repository/Dolt, legacy, provider implementation or test-support edge was added. |
| `S6-004` | Bundle closure redundant semantic entries / **P2 closed** | Recovery formerly reconstructed only `closure_entries` and ignored the parallel semantic `entries` payload. It now compares `closure_semantic_payload()` exactly; tampered semantic path/shape fails closed. |
| `S6-005` | Surface artifact-role digest binding / **P2 closed** | Surface formerly flattened artifact integrity identities, so swapping different before/current contents preserved the digest, while projection raw ref identity could enter it. Digest payload now binds integrity to each semantic role, excludes diagnostic refs and raw ref IDs, and preserves the digest only for same-integrity ref rewrites. |
| `S6-006` | Risk pair-cap degradation propagation / **P1 closed** | Pair annotation overflow formerly returned `DEGRADED` with an empty report, allowing Surface to lose the failure. It now discards partial annotations/closure and emits explicit `UNKNOWN`/`KEY_DEGRADED` table risks for every visible changed table, so downstream Surface preserves review-required state. |
| `S6-007` | Published Risk annotation conformance / **P2 closed** | Surface's public artifact-validation seam now checks Risk v1 content/manifest media types, size/SHA, canonical exact schema, array field types, unique annotation order and canonical evidence order before Bundle publication. Empty placeholders and malformed current-contract lookalikes fail closed without widening Bundle's owner DAG. |

No additional P1/P2 finding, digest owner collision, resource-cap bypass, partial READY publication,
unsafe logical path, cross-pair scope leak, automatic provider fallback or incorrect marker remains.

## 3. Exact remediation rerun

```text
tests/test_architecture.py::test_capability_modules_respect_import_dag
tests/test_risk_evaluation.py::test_pair_annotation_cap_discards_partial_annotation_closure
tests/test_risk_evaluation.py::test_annotation_document_validator_rejects_malformed_record_fields
tests/test_surface_assembly.py::test_replacement_uses_independent_side_browse_and_no_records
tests/test_surface_assembly.py::test_input_order_and_ref_rewrite_do_not_change_surface_digest
tests/test_bundle_assembly.py::test_nested_json_refs_are_rewritten_and_closure_remains_replayable
tests/test_bundle_assembly.py::test_placeholder_risk_annotation_artifacts_fail_before_bundle_publication
tests/test_bundle_assembly.py::test_recovery_rejects_manifest_and_closure_semantic_metadata_tampering
```

Result：**8 passed**。独立 reviewer 另以 multi-table pair-cap probe 验证 `alpha/beta/gamma`
visible tables 全部保留 `UNKNOWN`，且 Surface 不再丢失 review-required risk；该 probe 不是新增
第二测试 owner。

## 4. Gate evidence

| Check | Result |
| --- | --- |
| focused Risk/Surface/Bundle/architecture unit gate | **PASS**；90 passed |
| `cd vnext/backend && uv run --offline pytest -q -m unit --ignore tests/test_table_rules_resolver.py` | **PASS**；714 passed，1 existing Starlette deprecation warning |
| `cd vnext/backend && uv run --offline ruff check .` | **PASS** |
| `cd vnext/backend && uv run --offline mypy` | **PASS**；188 source files |
| other four Python packages `uv run --offline ruff check .` / `uv run --offline mypy` | **PASS**；mypy 26 / 15 / 195 / 34 source files |
| `git diff --check` | **PASS** |

Focused command：

```text
cd vnext/backend && uv run --offline pytest -q -m unit \
  tests/test_bundle_assembly.py tests/test_bundle_contracts.py \
  tests/test_surface_assembly.py tests/test_surface_contracts.py \
  tests/test_risk_evaluation.py tests/test_risk_contracts.py tests/test_architecture.py
```

所有新增测试使用 in-memory store；未创建 Dolt repository，未启动 process、shell/SQL、网络
或 fixed-timeout fixture，因此不需要 `integration` 或 `serial -n 0` rerun。S6 未触碰依赖、
Dockerfile、Compose、deployment 或 container-only runtime boundary，本轮不触发镜像重建；
S7 作为 stage exit 仍必须对 sealed current candidate 重新处理 inherited image/container gate。

## 5. Boundary dispositions

| Area | Result | Evidence / disposition |
| --- | --- | --- |
| Status and resource precedence | **Pass after S6-006** | FAILED/CANCELLED 不发布 outputs；pair cap 以显式 UNKNOWN table risks 降级且不发布 partial annotation closure。 |
| Digest ownership | **Pass after S6-005** | Risk/Surface/Bundle semantic digests排除 runtime ref identity/diagnostics；Surface artifact integrity 按语义角色绑定。 |
| Recovery and exact schema | **Pass after S6-004/S6-007** | Bundle redundant closure metadata、Risk content/manifest schema、media/integrity 和 canonical record shapes 均 fail closed。 |
| Closure atomicity | **Pass with deferred lifecycle** | 每次 source/destination readback 完整校验后才返回 Bundle；opaque orphan reclamation 按 ADR 0012 deferred。 |
| Ref/path and sharing | **Pass** | host path、reserved cache/repository/flow prefixes、duplicate logical path、undeclared nested ref 和 cross-pair shared rewrite gates 通过。 |

## 6. Deferred and reopen register

Carry forward：static-risk rules/provider、unified static/diff aggregation、Rust risk kernels/
differential、risk/surface/bundle cache、artifact GC/retention、P5 flow integration、R5 legacy
table-rules oracle gap 和 inherited image gate。

Reopen R6 if：forbidden owner import；risk 改写 comparison semantics；static risk 进入 R6 DTO；
partial artifact 公开可见；degraded table 丢失 terminal/no-record facts；resource cap failure 被下游
解释成无风险；artifact integrity 在角色交换后 digest 不变；placeholder 占用 typed artifact ref；
automatic provider fallback；或新增 security principal/helper/service。

## 7. Tested source/test patch inventory

```text
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/__init__.py
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/contracts.py
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/_artifacts.py
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/_engine.py
vnext/backend/src/gateway_backend/capabilities/surface_assembly/__init__.py
vnext/backend/src/gateway_backend/capabilities/surface_assembly/_assembly.py
vnext/backend/src/gateway_backend/capabilities/surface_assembly/_digest.py
vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_assembly.py
vnext/backend/tests/test_risk_evaluation.py
vnext/backend/tests/test_surface_assembly.py
vnext/backend/tests/test_bundle_assembly.py
```

Patch identity command：

```text
git diff --binary -- <the paths above> | sha256sum
```

## 8. Decision

**S6 PASS.** 当前候选无 open P1/P2；四项 re-review finding 均由 contract behavior tests
关闭。由于 remediation 晚于历史 S7 gate，S7 必须在新 conversation seal 当前候选、重跑
module gate 并刷新 handoff；本记录不宣称当前候选已通过 S7、container gate 或 production gate，
也不改变全局实现授权。

```yaml
p3_r6_s6: completed
p3_r6_s6_exit: pass
p3_r6_s6_review_base_sha: e09ff32cc3562b744ff5718357a529c7b8ce3e6f
p3_r6_s6_source_test_patch_sha256: b7bd5f98c344c9ac61ddb8c4960fba581d35b53d54f6162221f9fef08a4cecbe
p3_r6_s6_worktree: dirty_s6_independent_review_remediation_and_record
p3_r6_s6_remediation: closure_semantic_entries;surface_role_digest;pair_cap_degraded_risk;typed_risk_artifact_conformance
p3_r6_s6_deferred: orphan_reclamation_under_adr_0012;legacy_table_rules_oracle_gap;inherited_image_gate
p3_r6_s7_current_candidate: revalidation_required
p3_r6_implementation_authorized: no
p3_implementation_authorized: no
```

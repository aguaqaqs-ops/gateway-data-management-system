# Archive Parity Audit

本文是 Slice 6.0 的 archive 功能继承审计。目标不是设计新的 archive 功能，而是把旧后端已经具备的 archive 语义逐项映射到 backend vNext，并明确后续 Slice 6.1-6.5 的实现与验收边界。

## Scope

- 本审计只记录 parity matrix，不实现业务代码、不迁移 formal archive route、不调整前端。
- 旧后端功能语义是验收标准；vNext 可以简化模型和 DTO，但不能简化功能。
- Slice 6.1 前必须先补齐 batch graph / snapshot summary 判据；不得直接进入 formal archive API 整体迁移。

## Sources

| Kind | Source | Notes |
| --- | --- | --- |
| Design source | `docs/backend/initial-alignment-and-batch-graph.md` | Defines batch graph, time anomaly checks, root abnormal initial, anomaly resolution, baseline archive nodes, and formal tree visibility. |
| Old backend oracle | `gateway-data-management-system/backend/tests/unit/test_archive_use_cases.py` | Main oracle for archive use cases, anomaly graph, resolution, candidate selection, and archive node persistence. |
| Formal workflow oracle | `gateway-data-management-system/backend/tests/contract/test_formal_workspace_workflow_routes.py` | End-to-end formal route oracle for archive snapshot, dry-run, execute, second-batch abnormal initial, and history node behavior. |
| vNext current implementation | `gateway-data-management-system/backend/backend_vnext/archive/*` | Current vNext archive records, selection, policy, store, and service. |
| vNext current flow | `gateway-data-management-system/backend/backend_vnext/flows/archive.py` | Current `ARCHIVE_PROMOTE` flow skeleton and operation step order. |
| vNext current tests | `gateway-data-management-system/backend/tests/backend_vnext/unit/test_archive_service.py`, `gateway-data-management-system/backend/tests/backend_vnext/unit/test_archive_flow.py` | Current vNext coverage for promote/open-ref closeout and explicit candidate/resolution flow. |

## Current vNext Gap Summary

- vNext has archive records, candidate roles, anomaly resolution records, selection hashes, execute flow, repository promote, and open-ref closeout.
- vNext `ArchiveBatchSnapshot` currently contains confirmations, candidates, selected ids, hashes, eligibility, and failure reasons, but does not yet expose old-style `batch_graph`.
- vNext `SnapshotSummary` must also carry `configuration_generated_at` before time-abnormal archive checks are meaningful. The formal contract and old backend tests define this field as coming from `version_manager.saved_time`; current vNext archive code only has candidate/archive-node fields that can store it, not a proven SQL -> provisional summary -> FINAL hidden summary table -> archive graph source chain.
- vNext policy currently checks only selected `BASELINE_INITIAL_HISTORY` candidates that explicitly require anomaly resolution. It does not yet infer abnormal initial/modified conditions from protected snapshot summaries.
- Current vNext unit tests cover explicit archive candidate/resolution flow and open-ref closeout. They do not yet cover automatic batch graph inference, pending/incomplete summary, peer chain explanation, or time anomaly parity.
- Therefore Slice 6 must proceed in domain parity order: 6.1 graph判据 -> 6.2 resolution/selection闭环 -> 6.3 execute/tasks -> 6.4 formal API -> 6.5 frontend journey.

## Configuration Generated Time Source Chain

`configuration_generated_at` is not an archive-layer input that can be invented during dry-run or candidate selection. It is a protected business fact derived from the uploaded SQL content and carried forward by snapshot summaries.

Formal source chain:

1. Parse the original SQL package and read the last valid `version_manager.saved_time` value.
2. Materialization / snapshot summary emits `configuration_generated_at`.
3. Upload preview may carry this value in provisional summary artifacts, but those artifacts are not archive decision truth.
4. Submit finalize writes the FINAL `SnapshotSummary` into the repository commit/ref hidden summary table; this L2 fact is the archive/history source of truth.
5. Repository ref materialization/readback restores `configuration_generated_at` from the hidden summary table or an equivalent protected summary record.
6. Archive batch graph reads only FINAL/protected summary `configuration_generated_at` for time-abnormal decisions.
7. Archive candidate and baseline archive node DTOs copy the value from the selected summary/commit; they do not create a new business time.

Rules:

- Do not use upload time, submit time, review time, archive time, operation `generated_at`, or server clock as `configuration_generated_at`.
- Do not accept public request-body `configuration_generated_at` as archive decision truth.
- Do not use upload provisional summary, operation-local summary files, or recomputable cache as the only archive time fact after submit finalize; they can accelerate or diagnose, but the archive decision must be grounded in FINAL/protected summary.
- If baseline, initial, or modified summary lacks `configuration_generated_at`, skip only the affected time-abnormal comparison.
- Missing time must not be filled by copying another node's time; especially `BASELINE_INITIAL_HISTORY` must keep the initial's own business time.
- Slice 6.1a must implement or verify this source chain before Slice 6.1b enables A06/A07 time-abnormal graph parity.

## Parity Matrix

Status values:

- `covered`: vNext has equivalent behavior and focused tests.
- `partial`: vNext has data model or adjacent flow, but not full old semantics.
- `missing`: vNext lacks the behavior or test coverage.
- `formal-only-gap`: domain may exist elsewhere, but formal vNext route/journey is not migrated.

| ID | Behavior | Old oracle | Expected vNext behavior | Current vNext status | Target slice | Acceptance tests |
| --- | --- | --- | --- | --- | --- | --- |
| A00 | Configuration generated time source chain | `test_snapshot_summary_freezer_reads_configuration_generated_at_from_version_manager`, `test_snapshot_summary_freezer_reads_saved_time_from_insert_column_list`, `test_snapshot_summary_freezer_reads_configuration_generated_at_from_manual_fixture`, `test_snapshot_summary_freezer_leaves_configuration_generated_at_empty_without_generated_time` | vNext parses `version_manager.saved_time` from original SQL, stores it on `SnapshotSummary`, carries it through upload preview as provisional data, writes it into submit finalize FINAL hidden summary table, restores it through protected summary/readback, and archive graph uses only that FINAL/protected summary field for time checks. | missing/partial: formal contract and old tests define the behavior; vNext archive/candidate models can store the value, but current vNext summary/materialization chain does not prove end-to-end hidden-summary field preservation. | 6.1a prerequisite | Add vNext materialization/summary roundtrip tests, submit-finalize hidden summary persistence/readback test, and archive graph fixture proving no request/server/provisional-only time substitution. |
| A01 | Normal reachable submission passes batch graph | `test_dry_run_batch_graph_passes_reachable_submission` | `dry_run` returns `eligible_for_execute=true`, `batch_graph.overall_status=PASS`, reachable submission ids, matched path, and candidate tail state. | missing: current vNext snapshot has no `batch_graph` and no summary-index reachability check. | 6.1b | Add vNext archive graph test for baseline modified summary matching submission initial summary by business digest. |
| A02 | Pending projection blocks execute | `test_dry_run_batch_graph_blocks_pending_projection` | Incomplete business projection yields `PENDING_SUMMARY`, pending submission ids, and failure reason; execute remains blocked unless manually resolved. | missing: current vNext does not read snapshot summary status. | 6.1b / 6.2 | Add vNext graph test for `PENDING_PROJECTION`; add resolution test in 6.2 for manual incomplete summary. |
| A03 | Missing modified summary blocks execute | `test_dry_run_batch_graph_requires_modified_summary_index` | Missing modified summary yields `PENDING_SUMMARY` and `MODIFIED_SUMMARY_PENDING`. | missing. | 6.1b | Add vNext graph test for missing modified summary index. |
| A04 | Ready but unresolved abnormal initial needs confirmation | `test_dry_run_batch_graph_marks_unresolved_ready_summary` | Initial state not reachable from baseline or peer chain yields `NEEDS_CONFIRMATION`, `UNRESOLVED_INITIAL_STATE`, and unresolved submission id. | missing. | 6.1b | Add vNext graph test for business digest mismatch between baseline and initial. |
| A05 | Raw-exact summaries can still require abnormal initial confirmation | `test_dry_run_batch_graph_marks_raw_exact_unresolved_ready_for_confirmation` | `RAW_EXACT_READY` without business projection should avoid pending status but still produce `UNRESOLVED_INITIAL_STATE` when initial cannot be explained. | missing. | 6.1b | Add vNext graph test for raw-exact status with unresolved initial. |
| A06 | Abnormal modified time check | `test_dry_run_batch_graph_marks_time_abnormal_modified_independently` | `modified.configuration_generated_at < initial.configuration_generated_at` yields `TIME_ABNORMAL_MODIFIED`, `abnormal_kind=modified`, and `time_abnormal_reason`. | partial: candidate models carry `configuration_generated_at`, `abnormal_kind`, and `time_abnormal_reason`, but vNext does not infer the condition. | 6.1b / 6.2 | Add vNext graph inference test and later resolution/selection test for abnormal modified confirmation. |
| A07 | Initial and modified time anomalies can both be reported | `test_dry_run_batch_graph_can_report_initial_and_modified_time_abnormal_together` | Initial older than baseline and modified older than initial/baseline can emit both `TIME_ABNORMAL_INITIAL` and `TIME_ABNORMAL_MODIFIED`. | missing. | 6.1b | Add vNext graph test asserting both reason codes and separate `abnormal_kind` values. |
| A08 | Peer chain explains downstream initial; only root abnormal initial blocks | `test_dry_run_batch_graph_only_blocks_root_abnormal_initial_in_peer_chain` | Batch graph records downstream predecessor path, blocks only root abnormal initial, and root resolution unlocks downstream chain. | missing. | 6.1b / 6.2 | Add vNext graph test with `data1->data2` and `data2->data3`; add resolution test for root unlock. |
| A09 | Manual external change resolution covers unresolved initial | `test_manual_external_change_resolution_covers_unresolved_graph_block` | `MANUAL_ACCEPT_EXTERNAL_CHANGE` with reason covers abnormal initial blocking reason and allows execute eligibility. | partial: vNext can store anomaly resolutions, but does not link them to inferred graph reasons. | 6.2 | Add vNext resolution test binding resolution to submission/candidate and clearing graph failure. |
| A10 | Manual incomplete summary resolution covers pending graph block | `test_manual_incomplete_summary_resolution_covers_pending_graph_block` | `MANUAL_ACCEPT_INCOMPLETE_SUMMARY` can cover pending summary failure with audit data and preserved initial summary ref. | partial: vNext can store resolution record, but does not apply it to pending summary graph failure. | 6.2 | Add vNext pending summary resolution test. |
| A11 | Manual abnormal modified resolution covers time abnormal modified | `test_manual_abnormal_modified_resolution_covers_time_abnormal_modified_block` | `MANUAL_ACCEPT_ABNORMAL_MODIFIED` authorizes abnormal modified as mainline point; it does not create `BASELINE_INITIAL_HISTORY`. | partial: vNext models support resolution type and candidate abnormal metadata, but inference and coverage binding are absent. | 6.2 | Add vNext abnormal modified resolution test and ensure selected mainline candidate retains audit metadata. |
| A12 | Anomaly resolution reason is required | `test_accept_anomaly_resolution_requires_reason` | Empty/blank manual reason is rejected with archive confirmation reason error or formal `ErrorEnvelope`. | partial: vNext command validates basic types but formal route is not present. | 6.2 / 6.4 | Add vNext service validation test, then formal API error-envelope test. |
| A13 | Selected mainline candidate creates immutable candidate tag snapshot | `test_selection_creates_archive_candidate_tag_snapshot_for_selected_mainline` | Selecting mainline candidate creates immutable archive candidate ref/tag for the selected modified commit. | partial: vNext builds repository ref snapshots for promote, but focused parity around selection-time immutable candidate tag is not complete. | 6.2 | Add vNext candidate selection ref snapshot test or explicitly map to vNext repository ref contract if selection-time tag is intentionally moved. |
| A14 | Candidate tag conflict does not mutate selected state | `test_selection_tag_conflict_maps_to_application_error_without_selected_state` | Immutable ref conflict fails selection and leaves candidate unselected. | partial: vNext repository promote/open-ref path exists, but conflict parity for candidate selection needs explicit vNext test. | 6.2 | Add vNext selection conflict test. |
| A15 | Selected initial history is carried into promote request without main replay | `test_selected_initial_history_is_carried_in_contract_without_main_replay` | `BASELINE_INITIAL_HISTORY` candidate is passed as history candidate, while only selected modified promotes mainline. | partial/covered: vNext service and flow cover explicit selected initial history in current tests, but not graph-derived abnormal initial. | 6.2 / 6.3 | Extend current vNext archive service/flow tests with graph-derived initial history candidate. |
| A16 | Execute creates baseline archive nodes for mainline and initial history | `test_execute_creates_baseline_archive_nodes_for_mainline_and_initial_history` | Execute persists `MAINLINE_MODIFIED` and `BASELINE_INITIAL_HISTORY` nodes, summary refs, immutable refs, associated mainline id, anomaly resolution id, and time anomaly metadata. | partial: vNext marks submission archive statuses and records open-ref closeout, but focused archive-node parity must be verified/implemented. | 6.3 | Add vNext execute test asserting both archive node roles and metadata. |
| A17 | Execute promote and open-ref closeout are ordered and failure is recorded | vNext current `test_archive_service_execute_mainline_runs_open_ref_last_and_records_failure` | Promote mainline occurs before open-ref closeout; open-ref failure is recorded without pretending transfer succeeded. | covered for explicit candidates. | 6.3 | Keep current test and adapt once snapshot materialization becomes required async task. |
| A18 | `ARCHIVE_PROMOTE` flow records archive ladder steps | vNext current `test_archive_promote_flow_runs_archive_ladder_and_open_ref_last` | Operation records archive steps, promote result, open-ref result, and ready closure digest. | covered for explicit candidates, not async required-task semantics. | 6.3 | Extend operation tests for background required tasks and final READY gating. |
| A19 | Formal normal archive route workflow | `test_formal_workspace_workflow_routes.py` normal archive path | Formal `archive-snapshot`, candidate, confirmation, selection, dry-run, execute, current/latest batch, and explicit next batch open work end-to-end. | formal-only-gap: current formal vNext app does not expose archive routes; compat route exists separately. | 6.4 | Add formal app route tests after domain parity is stable. |
| A20 | Formal second-batch abnormal initial workflow | `test_formal_second_batch_initial_diagnostics_matches_workbench_contract` | Second batch can detect abnormal initial, generate diagnostics, accept anomaly, create history candidate, select mainline + history, execute, and return both archive node roles. | formal-only-gap plus domain gaps. | 6.4 / 6.5 | Add formal app integration test after 6.1-6.3; keep workflow oracle as high-value regression. |
| A21 | Formal tree/history visibility for initial history nodes | `tests/contract/test_formal_workspace_tree.py`, history compare tests | Archived `BASELINE_INITIAL_HISTORY` is visible as an independent history node and usable by history compare, not as a normal submission. | covered: formal tree projects independent `baseline_initial_history` nodes and formal history compare accepts `BASELINE_INITIAL_HISTORY` archive node ids. | 6.5 / 7 | Keep as high-value regression for future direct bundle loader work. |
| A22 | Archive execute READY waits for required archive tasks | Slice 6 planning requirement | Required tasks include promote mainline and archive snapshot materialization; future compression/remote transfer can be modeled as required or optional tasks. | missing: current vNext archive flow is synchronous and open-ref closeout is part of execute service. | 6.3 | Add operation test where execute returns non-READY until required tasks complete. |

## Target Slice Mapping

### Slice 6.1a: Configuration Generated Time Source Chain

Must implement row A00 before graph time-abnormal parity:

- Add `configuration_generated_at` to the vNext summary source chain if missing: SQL parse -> provisional `SnapshotSummary` -> submit finalize FINAL hidden summary table -> repository ref materialization/readback -> archive graph input.
- Treat upload preview/operation-local summary as provisional only; archive must consume FINAL/protected summary facts after submit finalize.
- Preserve null semantics: missing/invalid `version_manager.saved_time` stays null and only disables affected time comparisons.

### Slice 6.1b: Batch Graph / Snapshot Summary

Must implement rows A01-A08 after 6.1a:

- Add vNext batch graph model/projection equivalent to old `batch_graph`.
- Read protected summary facts for baseline, submission initial, and submission modified.
- Compute reachable, conditionally reachable, unresolved, pending, matched paths, candidate tail states, and blocking reasons.
- Infer time anomalies from `configuration_generated_at` without overwriting hash/graph abnormal initial reasons.

Implemented in the current checkpoint:

- `archive-snapshot` now emits `batch_graph` with graph status, blocking reason codes, submission id buckets, nodes, edges, and diagnostics.
- Archive dry-run and execute precheck consume graph blocking reasons.
- Candidate creation requires approved FINAL submit facts (`repository_commit_hash` and `configuration_generated_at`).
- `initial_configuration_generated_at` is an internal workspace/submission projection populated from initial materialization for graph time checks.
- Duplicate/canonical table grouping remains outside batch graph authority; it only affects history/readback/storage optimization.

Still deferred to 6.3:

- Archive execute domain-flow migration and async task projection.
- Final persistence of selected `BASELINE_INITIAL_HISTORY` archive nodes, immutable refs, associated mainline links, and history tree visibility.

### Slice 6.2: Resolution and Selection

Implemented in the current checkpoint:

- `POST /api/baseline-batches/{batch_id}/anomaly-resolutions` now persists manual anomaly resolution records with actor, reason, affected submissions, abnormal kind, time abnormal reason, and covered reason codes.
- Batch graph keeps raw diagnostics while exposing effective `blocking_reason_codes`, `raw_blocking_reason_codes`, and `resolved_reason_codes`.
- Resolution coverage is diagnostic-scoped: one root's resolution does not clear another root's identical global reason code.
- `MANUAL_ACCEPT_EXTERNAL_CHANGE` covers root `UNRESOLVED_INITIAL_STATE` and `TIME_ABNORMAL_INITIAL`; `MANUAL_ACCEPT_INCOMPLETE_SUMMARY` covers only `SUMMARY_FACT_MISSING`; `MANUAL_ACCEPT_ABNORMAL_MODIFIED` covers only `TIME_ABNORMAL_MODIFIED`.
- `BASELINE_INITIAL_HISTORY` candidates can be created and selected only for root abnormal initial submissions with a covering resolution; peer-chain downstream submissions remain explained by the root and cannot create their own initial history candidate.
- `MAINLINE_MODIFIED` selection with `TIME_ABNORMAL_MODIFIED` requires a covering abnormal-modified resolution.
- Selection stale-hash protection remains atomic: failed selection does not mutate selected batch fields.

Implemented in the current checkpoint:

- Compat execute materializes selected `BASELINE_INITIAL_HISTORY` archive nodes alongside the selected `MAINLINE_MODIFIED` node.
- Initial-history nodes carry immutable symbolic refs, summary refs, source candidate/submission/workspace ids, associated mainline node id, anomaly resolution id, initial configuration time, and abnormal metadata.
- Only the selected `MAINLINE_MODIFIED` promotes the batch main hash; initial-history nodes are retained as immutable history refs and do not become mainline.
- Workspace tree exposes `baseline_initial_history` as an independent read-only node, not as a normal submission.
- History compare can resolve `BASELINE_INITIAL_HISTORY` archive node ids through the retained initial source package.

Still deferred after 6.3:

- Async archive operation / required task READY gating.
- Formal archive API migration and frontend archive journey.

### Slice 6.3: Execute Domain Flow and Required Tasks

Implemented for compat domain flow:

- Persist `MAINLINE_MODIFIED` and `BASELINE_INITIAL_HISTORY` archive nodes with immutable refs, summary refs, anomaly metadata, and associated mainline node id.
- Promote only selected mainline modified to `main`.
- Preserve idempotent replay with the original execution record and node set.
- Keep archive execute synchronous in the compat adapter; required operation task semantics are intentionally deferred.

### Slice 6.4: Formal Archive API

Implemented for formal route migration:

- `formal_app.py` now exposes archive snapshot, anomaly resolution, candidate, confirmation, selection, dry-run, execute, and execution-record routes on the formal API paths.
- Formal routes call `VNextFormalStateStore` archive methods directly from `formal_state_store.py`; the old route adapter has been removed.
- Archive access is granted only by signed formal session permissions (`archive_mainline`); display-context hints do not grant archive authority.
- Workspace/batch scope checks use the formal session gateway and project context before route-level archive mutations.
- Store `KeyError`, `ValueError`, and `PermissionError` failures are converted to formal `ErrorEnvelope` responses instead of leaking compat exceptions.
- Formal archive responses remain additive and must not expose host paths, repo paths, cache-local refs, or debug-only fields.
- Archive execute remains the synchronous 6.3 domain flow by design; operation/required-task READY gating remains deferred.

Still deferred after 6.4:

- Archive Execute Operation Gating / required task READY semantics.
- Frontend archive journey migration and operation polling UX.
- Real Dolt immutable ref creation beyond the current stable symbolic refs.

### Slice 6.5 Prerequisite: Archive Execute Operation Gating

Implemented for the formal API and frontend session path:

- `POST /api/baseline-batches/{batch_id}/archive-mainline/execute` now performs synchronous precheck and returns an `ARCHIVE_PROMOTE` operation envelope instead of a completed archive payload.
- The background archive operation runs the existing 6.3 domain execute flow and publishes the archive execute payload only when the operation reaches `READY`.
- Before `READY`, execution records, archive nodes, batch closeout, workspace closeout, and next-batch opening are not visible as completed state.
- Workspace tree `active_operations` includes in-flight archive operations for affected workspaces.
- The formal frontend session archive execute path polls `/api/operations/{operation_id}` and consumes the archive payload from `ready_result`, matching the submit operation pattern.
- Workspace tree operation tags now display archive queue/running/ready/failure states for `ARCHIVE_PROMOTE`.
- Stale hashes and other execute precheck conflicts still return formal `ErrorEnvelope` synchronously and do not create an operation.
- Compat archive execute remains synchronous as a legacy/manual parity path.

Ready boundary correction after large-data manual testing:

- `ARCHIVE_PROMOTE` now includes a required `PREPARE_NEXT_BASELINE_SOURCE` step before the domain execute publishes archive state.
- The preparation step probes the selected mainline submit source package artifact and must succeed before execution records, archive nodes, current batch closeout, or next batch opening are visible.
- Preparation failure leaves the current batch in `OPEN` / `READY_FOR_ARCHIVE` so the operator can retry after fixing the source readiness problem.
- Formal operation resource refs include `blocks_upload=true`; the frontend upload and archive entry points stay disabled while the active archive operation is queued/running.

Still deferred after the gating prerequisite:

- Frontend archive journey visual/interaction refinement beyond the formal session polling path.
- Real Dolt immutable ref creation beyond the current stable symbolic refs.
- Optional post-archive tasks such as compression/remote transfer.

### Slice 6.5: Frontend Archive Journey

Implemented for the formal workspace frontend journey:

- `ArchiveMainlineReviewPanel` is the formal review surface for pending summary, multi-workspace confirmation, unresolved initial, time-abnormal, candidate selection, dry-run, and operation-polled execute flows.
- Normal archive remains a one-click path when graph/precheck state is clean; non-ready graph states open the review panel instead of directly executing.
- Formal archive execute uses the operation-gated session path and consumes `ARCHIVE_PROMOTE` updates through the same polling model as submit.
- In-flight archive operations disable duplicate execute attempts and show archive queued/running state in the panel and workspace tree.
- On completion, the frontend refreshes the formal tree so closed batch, next batch, mainline archive nodes, and `BASELINE_INITIAL_HISTORY` nodes become visible from the canonical projection.
- Abnormal graph/reason data continues to drive human explanation and confirmation; initial history appears as its own formal history node after archive.

Still deferred after 6.5:

- UX refinements that are purely visual or copy-level.
- Real Dolt immutable ref creation beyond the current stable symbolic refs.
- Optional post-archive tasks such as compression/remote transfer.

### Slice 7: History Compare

Implemented for the formal session path:

- `POST /api/history-comparisons`, `GET /api/history-comparisons/{operation_id}`, and direct comparison bundle download/artifact routes are exposed by the vNext formal app.
- Requests accept only business nodes: `BASELINE_MAINLINE`, `BASELINE_INITIAL_HISTORY`, and `SUBMISSION_MODIFIED`; extra ref/path/cache/table fields are rejected by the strict formal DTO.
- Formal history compare remains read-only and resolves inputs through session-scoped store nodes, not through client-provided Dolt refs, commit hashes, host paths, cache refs, or table names.
- READY responses include `history-comparison-bundle/v1` metadata and `comparison_bundle_download`; non-READY/failed operations keep `bundle=null` and `comparison_bundle_download=null`.
- Archived `BASELINE_INITIAL_HISTORY` nodes are usable as independent history compare inputs and participate in 2-node or 3-node pair plans.

Implemented after 8:

- Formal history compare now publishes and opens direct `ComparisonBundle` / `ComparisonSurface` bundles through `comparison_bundle_download`.
- The formal frontend path no longer consumes preview-compatible sidecars or synthetic preview identity for history compare.
- Frontend-facing row diff artifacts use Parquet inside the formal comparison bundle; JSON remains the metadata format for manifest/surface/closure/risk documents.

Implemented after 9:

- The vNext formal flow no longer exposes old history workbench routes or legacy download fields.
- The formal state store, operation wait helper, and session security modules use formal names.
- Legacy history workbench adapter code and compat route tests have been removed; upload preview sidecar cleanup remains a later bundle/data-surface task.

Still deferred after 8:

- Real Dolt immutable ref creation beyond the current stable symbolic refs.

## Do Not Proceed Conditions

Do not start Slice 6.4 formal archive API migration until:

- A00 proves vNext summary facts carry SQL-derived `configuration_generated_at` into FINAL/protected archive graph inputs.
- A01-A08 have vNext domain tests or explicit documented parity exceptions.
- A09-A12 demonstrate that manual resolutions bind to graph blocking reasons and cannot over-cover unrelated roots.
- A16 confirms archive node persistence for both mainline and initial history.
- A22 has an explicit documented exception: 6.4 keeps synchronous execute and defers Archive Execute Operation Gating to a standalone later slice.

Do not start Slice 6.5 frontend journey until:

- Formal archive route DTOs include the batch graph fields needed for unresolved/pending/time-abnormal explanation.
- Formal operation polling can distinguish archive main flow from optional post-archive tasks.
- Formal workspace tree can project archived mainline and initial history nodes without compat store dependency.

## Verification Commands

Focused old oracle check:

```bash
cd gateway-data-management-system/backend
./.venv/bin/pytest -q tests/unit/test_archive_use_cases.py -k "batch_graph or anomaly or baseline_archive_nodes"
```

Current vNext archive baseline:

```bash
cd gateway-data-management-system/backend
./.venv/bin/pytest -q tests/backend_vnext/unit/test_archive_service.py tests/backend_vnext/unit/test_archive_flow.py
```

Documentation check:

```bash
git diff --check
git status --short --branch
```

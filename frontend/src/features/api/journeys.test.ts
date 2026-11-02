import { describe, expect, it, vi } from "vitest";
import type { GatewayApi } from "./client";
import { applyReviewAction, runArchiveJourney, runDatasetReplacementPreview, runPreviewJourney, runReviewHistoryJourney, runSubmitJourney } from "./journeys";
import { MemoryBundleStore } from "../bundle/local-bundle";
import { installedGoldenBundle, responseForTar } from "../../test/helpers";

const operation = { operation_id: "op-1", job_kind: "PREVIEW", status: "SUCCEEDED", optimistic_version: 3, created_at: "2026-11-02T12:00:00Z" };
const upload = { upload_revision_id: "upload-1", workspace_id: "ws-1", generation: 4, input_completeness: "FULL", source_artifacts: {}, optimistic_version: 9, created_at: "2026-11-02T12:00:00Z" };
const acceptedSubmit = { submit_attempt_id: "attempt-1", operation_id: "submit-op", workspace_id: "ws-1", preview_result_id: "preview-1", generation: 4, state: "ACCEPTED" };

describe("simulated user journey data flows", () => {
  it("runs upload, Preview operation, result lookup and one local bundle download", async () => {
    const fixture = await installedGoldenBundle();
    const getPreviewBundle = vi.fn().mockResolvedValue(responseForTar(fixture.tar, fixture.manifest.bundle_digest));
    const api = {
      createWorkspace: vi.fn().mockResolvedValue({ workspace_id: "ws-1", gateway_device_external_key: "device-1", business_project_id: "project-1", state: "ACTIVE", generation: 4, optimistic_version: 10, created_at: "2026-11-02T12:00:00Z", updated_at: "2026-11-02T12:00:00Z", current_preview_result_id: "preview-1" }),
      uploadRevision: vi.fn().mockResolvedValue(upload),
      startPreview: vi.fn().mockResolvedValue({ operation_id: "op-1", workspace_id: "ws-1", upload_revision_id: "upload-1", generation: 4, status: "QUEUED" }),
      getOperation: vi.fn().mockResolvedValue(operation),
      getPreviewResult: vi.fn().mockResolvedValue({ preview_result_id: "preview-1", workspace_id: "ws-1", upload_revision_id: "upload-1", generation: 4, operation_id: "op-1", business_baseline_node_id: "baseline-1", business_baseline_commit_id: "commit-a", derived_stale: false, bundle_digest: fixture.manifest.bundle_digest, identity_assessment_set_digest: "sha256:identity", identity_pairs: [], created_at: "2026-11-02T12:00:00Z" }),
      getPreviewBundle,
    } as unknown as GatewayApi;
    const result = await runPreviewJourney(api, new MemoryBundleStore(), {
      workspaceRequest: { gateway_device_external_key: "device-1", business_project_id: "project-1" },
      upload: { inputCompleteness: "FULL", initial: { partName: "initial", mediaType: "application/zip", file: new File(["initial"], "initial.zip") }, modified: { partName: "modified", mediaType: "application/zip", file: new File(["modified"], "modified.zip") }, idempotencyKey: "upload-key" },
      baselineNodeId: "baseline-1",
      baselineHeadVersion: 12,
      poll: { intervalMs: 0, wait: async () => undefined },
    });
    expect(api.uploadRevision).toHaveBeenCalledWith("ws-1", expect.objectContaining({ expectedWorkspaceVersion: 10 }));
    expect(api.startPreview).toHaveBeenCalledWith("ws-1", expect.objectContaining({ expected_workspace_version: 9, expected_baseline_head_version: 12 }));
    expect(api.getOperation).toHaveBeenCalledWith("op-1", undefined);
    expect(getPreviewBundle).toHaveBeenCalledTimes(1);
    expect(result.bundle.manifest.bundle_digest).toBe(fixture.manifest.bundle_digest);
  });

  it("uses MODIFIED_ONLY input for the dataset replacement Preview route", async () => {
    const fixture = await installedGoldenBundle();
    const api = {
      createWorkspace: vi.fn().mockResolvedValue({ workspace_id: "ws-1", gateway_device_external_key: "device-1", business_project_id: "project-1", state: "ACTIVE", generation: 4, optimistic_version: 10, created_at: "2026-11-02T12:00:00Z", updated_at: "2026-11-02T12:00:00Z", current_preview_result_id: "preview-1" }),
      uploadRevision: vi.fn().mockResolvedValue({ ...upload, input_completeness: "MODIFIED_ONLY" }),
      startPreview: vi.fn().mockResolvedValue({ operation_id: "op-1", workspace_id: "ws-1", upload_revision_id: "upload-1", generation: 4, status: "QUEUED" }),
      getOperation: vi.fn().mockResolvedValue(operation),
      getPreviewResult: vi.fn().mockResolvedValue({ preview_result_id: "preview-1", workspace_id: "ws-1", upload_revision_id: "upload-1", generation: 4, operation_id: "op-1", business_baseline_node_id: "baseline-1", business_baseline_commit_id: "commit-a", derived_stale: false, bundle_digest: fixture.manifest.bundle_digest, identity_assessment_set_digest: "sha256:identity", identity_pairs: [], created_at: "2026-11-02T12:00:00Z" }),
      getPreviewBundle: vi.fn().mockResolvedValue(responseForTar(fixture.tar, fixture.manifest.bundle_digest)),
    } as unknown as GatewayApi;
    await runDatasetReplacementPreview(api, new MemoryBundleStore(), {
      workspaceRequest: { gateway_device_external_key: "device-1", business_project_id: "project-1" },
      upload: { inputCompleteness: "MODIFIED_ONLY", modified: { partName: "modified", mediaType: "application/zip", file: new File(["modified"], "modified.zip") } },
      baselineNodeId: "baseline-1",
      baselineHeadVersion: 12,
      poll: { intervalMs: 0, wait: async () => undefined },
    });
    expect(api.uploadRevision).toHaveBeenCalledWith("ws-1", expect.objectContaining({ inputCompleteness: "MODIFIED_ONLY" }));
  });

  it.each([
    ["operation", { operation_id: "other-operation", upload_revision_id: "upload-1" }, "不属于本次预览操作"],
    ["upload revision", { operation_id: "op-1", upload_revision_id: "other-upload" }, "不属于本次上传版本"],
  ])("rejects a Preview result tied to a different %s", async (_label, identities, message) => {
    const api = {
      createWorkspace: vi.fn().mockResolvedValue({ workspace_id: "ws-1", gateway_device_external_key: "device-1", business_project_id: "project-1", state: "ACTIVE", generation: 4, optimistic_version: 10, created_at: "2026-11-02T12:00:00Z", updated_at: "2026-11-02T12:00:00Z", current_preview_result_id: "preview-1" }),
      uploadRevision: vi.fn().mockResolvedValue(upload),
      startPreview: vi.fn().mockResolvedValue({ operation_id: "op-1", workspace_id: "ws-1", upload_revision_id: "upload-1", generation: 4, status: "QUEUED" }),
      getOperation: vi.fn().mockResolvedValue(operation),
      getPreviewResult: vi.fn().mockResolvedValue({ preview_result_id: "preview-1", workspace_id: "ws-1", ...identities, generation: 4, business_baseline_node_id: "baseline-1", business_baseline_commit_id: "commit-a", derived_stale: false, bundle_digest: "sha256:bundle", identity_assessment_set_digest: "sha256:identity", identity_pairs: [], created_at: "2026-11-02T12:00:00Z" }),
      getPreviewBundle: vi.fn(),
    } as unknown as GatewayApi;

    await expect(runPreviewJourney(api, new MemoryBundleStore(), {
      workspaceRequest: { gateway_device_external_key: "device-1", business_project_id: "project-1" },
      upload: { inputCompleteness: "MODIFIED_ONLY", modified: { partName: "modified", mediaType: "application/zip", file: new File(["modified"], "modified.zip") } },
      baselineNodeId: "baseline-1",
      baselineHeadVersion: 12,
      poll: { intervalMs: 0, wait: async () => undefined },
    })).rejects.toThrow(message);
    expect(api.getPreviewBundle).not.toHaveBeenCalled();
  });

  it("submits with expected versions, polls, and resolves the finalized submission", async () => {
    const api = {
      acceptSubmit: vi.fn().mockResolvedValue(acceptedSubmit),
      getOperation: vi.fn().mockResolvedValue({ ...operation, operation_id: "submit-op", job_kind: "SUBMIT" }),
      getSubmitAttempt: vi.fn().mockResolvedValue({ submit_attempt_id: "attempt-1", workspace_id: "ws-1", upload_revision_id: "upload-1", preview_result_id: "preview-1", generation: 4, operation_id: "submit-op", state: "FINALIZED", business_baseline_node_id: "baseline-1", business_baseline_commit_id: "commit-a", canonical_business_digest: "sha256:business", created_at: "2026-11-02T12:00:00Z", submission_id: "submission-1" }),
      getSubmission: vi.fn().mockResolvedValue({ submission_id: "submission-1", submit_attempt_id: "attempt-1", workspace_id: "ws-1", upload_revision_id: "upload-1", preview_result_id: "preview-1", generation: 4, repository_id: "repo-1", based_on_baseline_node_id: "baseline-1", business_baseline_commit_id: "commit-a", repository_commit_id: "commit-b", canonical_business_digest: "sha256:business", canonicalization_manifest_digest: "sha256:manifest", created_by: "user-1", created_at: "2026-11-02T12:00:00Z" }),
    } as unknown as GatewayApi;
    const result = await runSubmitJourney(api, { workspaceId: "ws-1", previewResultId: "preview-1", uploadRevisionId: "upload-1", generation: 4, expectedWorkspaceVersion: 11, baselineNodeId: "baseline-1", baselineHeadVersion: 12, poll: { intervalMs: 0, wait: async () => undefined } });
    expect(api.acceptSubmit).toHaveBeenCalledWith("ws-1", expect.objectContaining({ expected_workspace_version: 11, expected_baseline_head_version: 12 }));
    expect(result.submission.submission_id).toBe("submission-1");
  });

  it("compares a submission from its parent when History head has advanced", async () => {
    const fixture = await installedGoldenBundle();
    const getHistoryBundle = vi.fn().mockResolvedValue(responseForTar(fixture.tar, fixture.manifest.bundle_digest));
    const getPreviewBundle = vi.fn();
    const api = {
      getReviewFacts: vi.fn().mockResolvedValue({ submission_id: "submission-1", status: "PENDING", review_version: 5, updated_by: "reviewer", updated_at: "2026-11-02T12:00:00Z", identity_exception: false, events: [] }),
      listHistory: vi.fn().mockResolvedValue({
        head: { node_id: "baseline-2", commit_id: "commit-b", version: 18 },
        nodes: [{ ref_kind: "submission", ref_id: "submission-1", node_kind: "SUBMISSION", commit_id: "commit-c", created_at: "2026-11-02T12:00:00Z", parent: { ref_kind: "baseline_node", ref_id: "baseline-1" }, eligibility_note: "NOT_CANDIDATE_BASE_ADVANCED", identity_exception: false, review_status: "PENDING" }],
        next_cursor: null,
      }),
      startHistoryCompare: vi.fn().mockResolvedValue({ operation_id: "history-op", status: "QUEUED", replayed: false }),
      getOperation: vi.fn().mockResolvedValue({ ...operation, operation_id: "history-op", job_kind: "HISTORY_COMPARE" }),
      getHistoryCompare: vi.fn().mockResolvedValue({ operation_id: "history-op", status: "SUCCEEDED", result: { bundle_digest: fixture.manifest.bundle_digest, input: {}, pairs: [] } }),
      getHistoryBundle,
      getPreviewBundle,
    } as unknown as GatewayApi;
    const result = await runReviewHistoryJourney(api, new MemoryBundleStore(), "submission-1", { intervalMs: 0, wait: async () => undefined });
    expect(api.startHistoryCompare).toHaveBeenCalledWith({ nodes: [{ ref_kind: "baseline_node", ref_id: "baseline-1" }, { ref_kind: "submission", ref_id: "submission-1" }] });
    expect(getHistoryBundle).toHaveBeenCalledTimes(1);
    expect(getPreviewBundle).not.toHaveBeenCalled();
    expect(result.bundle.manifest.bundle_digest).toBe(fixture.manifest.bundle_digest);
  });

  it("reports when the reviewed submission is missing from History", async () => {
    const api = {
      getReviewFacts: vi.fn().mockResolvedValue({ submission_id: "submission-1", status: "PENDING", review_version: 5, updated_by: "reviewer", updated_at: "2026-11-02T12:00:00Z", identity_exception: false, events: [] }),
      listHistory: vi.fn().mockResolvedValue({ head: { node_id: "baseline-2", commit_id: "commit-b", version: 18 }, nodes: [], next_cursor: null }),
      startHistoryCompare: vi.fn(),
    } as unknown as GatewayApi;

    await expect(runReviewHistoryJourney(api, new MemoryBundleStore(), "submission-1")).rejects.toThrow("History 中找不到唯一提交节点");
    expect(api.startHistoryCompare).not.toHaveBeenCalled();
  });

  it("reports when the reviewed History submission has no parent", async () => {
    const api = {
      getReviewFacts: vi.fn().mockResolvedValue({ submission_id: "submission-1", status: "PENDING", review_version: 5, updated_by: "reviewer", updated_at: "2026-11-02T12:00:00Z", identity_exception: false, events: [] }),
      listHistory: vi.fn().mockResolvedValue({ head: { node_id: "baseline-2", commit_id: "commit-b", version: 18 }, nodes: [{ ref_kind: "submission", ref_id: "submission-1", node_kind: "SUBMISSION", commit_id: "commit-c", created_at: "2026-11-02T12:00:00Z", parent: null, eligibility_note: null, identity_exception: false, review_status: "PENDING" }], next_cursor: null }),
      startHistoryCompare: vi.fn(),
    } as unknown as GatewayApi;

    await expect(runReviewHistoryJourney(api, new MemoryBundleStore(), "submission-1")).rejects.toThrow("History 提交节点没有基线 parent");
    expect(api.startHistoryCompare).not.toHaveBeenCalled();
  });

  it("uses the current review version for approve/reject and requires a rejection reason", async () => {
    const api = {
      getReviewFacts: vi.fn().mockResolvedValue({ submission_id: "submission-1", status: "PENDING", review_version: 8, updated_by: "reviewer", updated_at: "2026-11-02T12:00:00Z", identity_exception: false, events: [] }),
      applyReview: vi.fn().mockResolvedValue({ submission_id: "submission-1", status: "APPROVED", review_version: 9, event: { sequence: 2, event_kind: "APPROVED", to_status: "APPROVED", actor_id: "reviewer", occurred_at: "2026-11-02T12:00:00Z" } }),
    } as unknown as GatewayApi;

    await expect(applyReviewAction(api, "submission-1", "REJECT", "  ")).rejects.toThrow("退回时必须填写理由");
    expect(api.applyReview).not.toHaveBeenCalled();
    await applyReviewAction(api, "submission-1", "APPROVE");
    expect(api.applyReview).toHaveBeenCalledWith("submission-1", { expected_review_version: 8, action: "APPROVE" });
  });

  it("previews the archive plan and applies the candidate snapshot with current versions", async () => {
    const plan = { head: { business_baseline_node_id: "baseline-4", business_baseline_commit_id: "commit-a", baseline_head_version: 21 }, candidate_set_digest: "sha256:candidates", confirmation_requirements: [], anomalies: [], audit_validity: true, dispositions: [], workspace_releases: [], can_start: true, blockers: [] };
    const api = {
      listArchiveCandidates: vi.fn().mockResolvedValue({ head: { business_baseline_node_id: "baseline-4", business_baseline_commit_id: "commit-a", baseline_head_version: 21 }, candidates: [], candidate_set_digest: "sha256:candidates", blockers: [] }),
      listArchiveEvents: vi.fn().mockResolvedValue({ events: [], next_after_sequence: null }),
      previewArchive: vi.fn().mockResolvedValue(plan),
      startArchive: vi.fn().mockResolvedValue({ archive_plan_id: "plan-1", archive_result_id: "archive-1", baseline_node_id: "baseline-4", baseline_commit_id: "commit-a", baseline_head_version: 21, selected_submission_id: "submission-1", dispositions: [], released_workspace_ids: [], archived_by: "owner", archived_at: "2026-11-02T12:00:00Z" }),
      getArchiveResult: vi.fn().mockResolvedValue({ archive_result_id: "archive-1", archive_plan_id: "plan-1", baseline_node_id: "baseline-4", baseline_commit_id: "commit-a", baseline_head_version: 21, selected_submission_id: "submission-1", selected_repository_commit_id: "commit-b", candidate_set_digest: "sha256:candidates", confirmation_refs: [], anomaly_resolution_refs: [], dispositions: [], archived_by: "owner", archived_at: "2026-11-02T12:00:00Z" }),
    } as unknown as GatewayApi;
    const result = await runArchiveJourney(api, { selected: { submission_id: "submission-1", expected_candidate_digest: "sha256:candidate" }, idempotencyKey: "archive-key" });
    expect(api.startArchive).toHaveBeenCalledWith(expect.objectContaining({ expected_baseline_node_id: "baseline-4", expected_baseline_head_version: 21, candidate_set_digest: "sha256:candidates" }), "archive-key");
    expect(result.result.archive_result_id).toBe("archive-1");
  });

  it("records archive confirmations and anomaly resolutions with monotonic audit versions", async () => {
    const firstPlan = { head: { business_baseline_node_id: "baseline-4", business_baseline_commit_id: "commit-a", baseline_head_version: 21 }, candidate_set_digest: "sha256:candidates", confirmation_requirements: ["SELECTION_CONFIRMATION"], anomalies: [{ subject_kind: "PROJECT_IDENTITY_EXCEPTION", issue_code: "IDENTITY_UNVERIFIABLE", target_submission_id: "submission-1", target_candidate_digest: "sha256:candidate", subject_digest: "sha256:anomaly" }], audit_validity: true, dispositions: [], workspace_releases: [], can_start: false, blockers: ["AUDIT_CONFIRMATION_REQUIRED"] };
    const readyPlan = { ...firstPlan, confirmation_requirements: [], anomalies: [], can_start: true, blockers: [] };
    const listArchiveCandidates = vi.fn().mockResolvedValue({ head: firstPlan.head, candidates: [], candidate_set_digest: "sha256:candidates", blockers: [] });
    const api = {
      listArchiveCandidates,
      listArchiveEvents: vi.fn().mockResolvedValue({ events: [{ event_id: "event-5", subject_kind: "SELECTION", subject_digest: "old", sequence: 5, action: "CONFIRM", actor_id: "owner", occurred_at: "2026-11-02T12:00:00Z" }], next_after_sequence: null }),
      previewArchive: vi.fn().mockResolvedValueOnce(firstPlan).mockResolvedValueOnce(readyPlan),
      appendArchiveConfirmation: vi.fn().mockResolvedValue({ event_id: "event-6", sequence: 6 }),
      appendArchiveAnomalyResolution: vi.fn().mockResolvedValue({ event_id: "event-7", sequence: 7 }),
      startArchive: vi.fn().mockResolvedValue({ archive_plan_id: "plan-1", archive_result_id: "archive-1", baseline_node_id: "baseline-4", baseline_commit_id: "commit-a", baseline_head_version: 21, selected_submission_id: "submission-1", dispositions: [], released_workspace_ids: [], archived_by: "owner", archived_at: "2026-11-02T12:00:00Z" }),
      getArchiveResult: vi.fn().mockResolvedValue({ archive_result_id: "archive-1", archive_plan_id: "plan-1", baseline_node_id: "baseline-4", baseline_commit_id: "commit-a", baseline_head_version: 21, selected_submission_id: "submission-1", selected_repository_commit_id: "commit-b", candidate_set_digest: "sha256:candidates", confirmation_refs: [{ subject_digest: "sha256:selection", sequence: 6 }], anomaly_resolution_refs: [{ subject_digest: "sha256:anomaly", sequence: 7 }], dispositions: [], archived_by: "owner", archived_at: "2026-11-02T12:00:00Z" }),
    } as unknown as GatewayApi;
    await runArchiveJourney(api, {
      selected: { submission_id: "submission-1", expected_candidate_digest: "sha256:candidate" },
      confirmations: [{ subjectDigest: "sha256:selection", action: "CONFIRM", reason: "已核对" }],
      anomalyResolutions: [{ subjectDigest: "sha256:anomaly", action: "ACKNOWLEDGE_IDENTITY_EXCEPTION", reason: "已人工确认" }],
    });
    expect(api.appendArchiveConfirmation).toHaveBeenCalledWith(expect.objectContaining({ expected_sequence: 6, expected_baseline_head_version: 21 }));
    expect(api.appendArchiveAnomalyResolution).toHaveBeenCalledWith(expect.objectContaining({ expected_sequence: 7, issue_code: "IDENTITY_UNVERIFIABLE", subject_kind: "PROJECT_IDENTITY_EXCEPTION" }));
    expect(api.startArchive).toHaveBeenCalledWith(expect.objectContaining({ confirmation_refs: [{ subject_digest: "sha256:selection", sequence: 6 }], anomaly_resolution_refs: [{ subject_digest: "sha256:anomaly", sequence: 7 }] }), undefined);
  });
});

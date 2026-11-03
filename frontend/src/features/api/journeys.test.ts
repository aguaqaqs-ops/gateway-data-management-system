import { describe, expect, it, vi } from "vitest";
import type { GatewayApi } from "./client";
import { applyReviewAction, runArchiveJourney, runDatasetReplacementPreview, runPreviewJourney, runReviewHistoryJourney, runSubmitJourney } from "./journeys";
import { MemoryBundleStore } from "../bundle/local-bundle";
import { installedFixtureBundle, installedGoldenBundle, responseForTar } from "../../test/helpers";
import { ARCHIVE_PLAN_NEEDS_CONFIRMATION, ARCHIVE_PLAN_READY, TEST_ARCHIVE_CANDIDATES, TEST_ARCHIVE_CONFIRM_APPEND, TEST_ARCHIVE_EVENTS_EMPTY, TEST_ARCHIVE_EVENTS_WITH_CONFIRMATION, TEST_ARCHIVE_RESOLUTION_APPEND, TEST_ARCHIVE_RESULT, TEST_ARCHIVE_STARTED, TEST_OPERATION_ACCEPTED, TEST_OPERATION_SUBMIT_SUCCEEDED, TEST_OPERATION_SUCCEEDED, TEST_PREVIEW_RESULT_OTHER_OPERATION, TEST_PREVIEW_RESULT_OTHER_UPLOAD, TEST_REVIEW_FACTS, TEST_REVIEW_HISTORY, TEST_REVIEW_HISTORY_EMPTY, TEST_REVIEW_HISTORY_NO_PARENT, TEST_SUBMISSION, TEST_SUBMIT_ACCEPTED, TEST_SUBMIT_ATTEMPT_FINALIZED, TEST_UPLOAD_FULL, TEST_WORKSPACE, testArchiveResultWithRefs, testHistoryCompareAcceptance, testHistoryCompareSucceeded, testPreviewResult, testUploadRevision, TEST_REVIEW_APPLIED } from "../dev/mock-data";

const operation = TEST_OPERATION_SUCCEEDED;
const upload = TEST_UPLOAD_FULL;
const acceptedSubmit = TEST_SUBMIT_ACCEPTED;

describe("simulated user journey data flows", () => {
  it("runs upload, Preview operation, result lookup and one local bundle download", async () => {
    const fixture = await installedGoldenBundle();
    const getPreviewBundle = vi.fn().mockResolvedValue(responseForTar(fixture.tar, fixture.manifest.bundle_digest));
    const api = {
      createWorkspace: vi.fn().mockResolvedValue(TEST_WORKSPACE),
      uploadRevision: vi.fn().mockResolvedValue(upload),
      startPreview: vi.fn().mockResolvedValue(TEST_OPERATION_ACCEPTED),
      getOperation: vi.fn().mockResolvedValue(operation),
      getPreviewResult: vi.fn().mockResolvedValue(testPreviewResult(fixture.manifest.bundle_digest)),
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
      createWorkspace: vi.fn().mockResolvedValue(TEST_WORKSPACE),
      uploadRevision: vi.fn().mockResolvedValue(testUploadRevision("MODIFIED_ONLY")),
      startPreview: vi.fn().mockResolvedValue(TEST_OPERATION_ACCEPTED),
      getOperation: vi.fn().mockResolvedValue(operation),
      getPreviewResult: vi.fn().mockResolvedValue(testPreviewResult(fixture.manifest.bundle_digest)),
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
    ["operation", TEST_PREVIEW_RESULT_OTHER_OPERATION, "不属于本次预览操作"],
    ["upload revision", TEST_PREVIEW_RESULT_OTHER_UPLOAD, "不属于本次上传版本"],
  ])("rejects a Preview result tied to a different %s", async (_label, identities, message) => {
    const api = {
      createWorkspace: vi.fn().mockResolvedValue(TEST_WORKSPACE),
      uploadRevision: vi.fn().mockResolvedValue(upload),
      startPreview: vi.fn().mockResolvedValue(TEST_OPERATION_ACCEPTED),
      getOperation: vi.fn().mockResolvedValue(operation),
      getPreviewResult: vi.fn().mockResolvedValue(identities),
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
      getOperation: vi.fn().mockResolvedValue(TEST_OPERATION_SUBMIT_SUCCEEDED),
      getSubmitAttempt: vi.fn().mockResolvedValue(TEST_SUBMIT_ATTEMPT_FINALIZED),
      getSubmission: vi.fn().mockResolvedValue(TEST_SUBMISSION),
    } as unknown as GatewayApi;
    const result = await runSubmitJourney(api, { workspaceId: "ws-1", previewResultId: "preview-1", uploadRevisionId: "upload-1", generation: 4, expectedWorkspaceVersion: 11, baselineNodeId: "baseline-1", baselineHeadVersion: 12, poll: { intervalMs: 0, wait: async () => undefined } });
    expect(api.acceptSubmit).toHaveBeenCalledWith("ws-1", expect.objectContaining({ expected_workspace_version: 11, expected_baseline_head_version: 12 }));
    expect(result.submission.submission_id).toBe("submission-1");
  });

  it("compares a submission from its parent when History head has advanced", async () => {
    const fixture = await installedFixtureBundle("history-three-nodes");
    const getHistoryBundle = vi.fn().mockResolvedValue(responseForTar(fixture.tar, fixture.manifest.bundle_digest));
    const getPreviewBundle = vi.fn();
    const api = {
      getReviewFacts: vi.fn().mockResolvedValue(TEST_REVIEW_FACTS),
      listHistory: vi.fn().mockResolvedValue(TEST_REVIEW_HISTORY),
      startHistoryCompare: vi.fn().mockResolvedValue(testHistoryCompareAcceptance("history-op")),
      getHistoryCompare: vi.fn().mockResolvedValue(testHistoryCompareSucceeded(fixture.manifest.bundle_digest)),
      getHistoryBundle,
      getPreviewBundle,
    } as unknown as GatewayApi;
    const result = await runReviewHistoryJourney(api, new MemoryBundleStore(), "fe2a-history-ref-2", "review-key", { intervalMs: 0, wait: async () => undefined });
    expect(api.startHistoryCompare).toHaveBeenCalledWith({ nodes: [{ ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1" }, { ref_kind: "submission", ref_id: "fe2a-history-ref-2" }] }, "review-key");
    expect(getHistoryBundle).toHaveBeenCalledTimes(1);
    expect(getPreviewBundle).not.toHaveBeenCalled();
    expect(result.bundle.manifest.bundle_digest).toBe(fixture.manifest.bundle_digest);
  });

  it("reports when the reviewed submission is missing from History", async () => {
    const api = {
      getReviewFacts: vi.fn().mockResolvedValue(TEST_REVIEW_FACTS),
      listHistory: vi.fn().mockResolvedValue(TEST_REVIEW_HISTORY_EMPTY),
      startHistoryCompare: vi.fn(),
    } as unknown as GatewayApi;

    await expect(runReviewHistoryJourney(api, new MemoryBundleStore(), "fe2a-history-ref-2", "review-key")).rejects.toThrow("History 中找不到唯一提交节点");
    expect(api.startHistoryCompare).not.toHaveBeenCalled();
  });

  it("reports when the reviewed History submission has no parent", async () => {
    const api = {
      getReviewFacts: vi.fn().mockResolvedValue(TEST_REVIEW_FACTS),
      listHistory: vi.fn().mockResolvedValue(TEST_REVIEW_HISTORY_NO_PARENT),
      startHistoryCompare: vi.fn(),
    } as unknown as GatewayApi;

    await expect(runReviewHistoryJourney(api, new MemoryBundleStore(), "fe2a-history-ref-2", "review-key")).rejects.toThrow("History 提交节点没有基线 parent");
    expect(api.startHistoryCompare).not.toHaveBeenCalled();
  });

  it("uses the current review version for approve/reject and requires a rejection reason", async () => {
    const api = {
      getReviewFacts: vi.fn().mockResolvedValue(TEST_REVIEW_FACTS),
      applyReview: vi.fn().mockResolvedValue(TEST_REVIEW_APPLIED),
    } as unknown as GatewayApi;

    await expect(applyReviewAction(api, "fe2a-history-ref-2", "REJECT", "  ")).rejects.toThrow("退回时必须填写理由");
    expect(api.applyReview).not.toHaveBeenCalled();
    await applyReviewAction(api, "fe2a-history-ref-2", "APPROVE");
    expect(api.applyReview).toHaveBeenCalledWith("fe2a-history-ref-2", { expected_review_version: 5, action: "APPROVE" });
  });

  it("previews the archive plan and applies the candidate snapshot with current versions", async () => {
    const api = {
      listArchiveCandidates: vi.fn().mockResolvedValue(TEST_ARCHIVE_CANDIDATES),
      listArchiveEvents: vi.fn().mockResolvedValue(TEST_ARCHIVE_EVENTS_EMPTY),
      previewArchive: vi.fn().mockResolvedValue(ARCHIVE_PLAN_READY),
      startArchive: vi.fn().mockResolvedValue(TEST_ARCHIVE_STARTED),
      getArchiveResult: vi.fn().mockResolvedValue(TEST_ARCHIVE_RESULT),
    } as unknown as GatewayApi;
    const result = await runArchiveJourney(api, { selected: { submission_id: "submission-1", expected_candidate_digest: "sha256:candidate" }, idempotencyKey: "archive-key" });
    expect(api.startArchive).toHaveBeenCalledWith(expect.objectContaining({ expected_baseline_node_id: "baseline-4", expected_baseline_head_version: 21, candidate_set_digest: "sha256:candidates" }), "archive-key");
    expect(result.result.archive_result_id).toBe("archive-1");
  });

  it("records archive confirmations and anomaly resolutions with monotonic audit versions", async () => {
    const firstPlan = ARCHIVE_PLAN_NEEDS_CONFIRMATION;
    const readyPlan = ARCHIVE_PLAN_READY;
    const listArchiveCandidates = vi.fn().mockResolvedValue(TEST_ARCHIVE_CANDIDATES);
    const api = {
      listArchiveCandidates,
      listArchiveEvents: vi.fn().mockResolvedValue(TEST_ARCHIVE_EVENTS_WITH_CONFIRMATION),
      previewArchive: vi.fn().mockResolvedValueOnce(firstPlan).mockResolvedValueOnce(readyPlan),
      appendArchiveConfirmation: vi.fn().mockResolvedValue(TEST_ARCHIVE_CONFIRM_APPEND),
      appendArchiveAnomalyResolution: vi.fn().mockResolvedValue(TEST_ARCHIVE_RESOLUTION_APPEND),
      startArchive: vi.fn().mockResolvedValue(TEST_ARCHIVE_STARTED),
      getArchiveResult: vi.fn().mockResolvedValue(testArchiveResultWithRefs()),
    } as unknown as GatewayApi;
    await runArchiveJourney(api, {
      selected: { submission_id: "submission-1", expected_candidate_digest: "sha256:candidate" },
      confirmations: [{ subjectDigest: "sha256:selection-subject", action: "CONFIRM", reason: "已核对" }],
      anomalyResolutions: [{ subjectDigest: "sha256:anomaly", action: "ACKNOWLEDGE_IDENTITY_EXCEPTION", reason: "已人工确认" }],
    });
    expect(api.appendArchiveConfirmation).toHaveBeenCalledWith(expect.objectContaining({ expected_sequence: 6, expected_baseline_head_version: 21 }));
    expect(api.appendArchiveAnomalyResolution).toHaveBeenCalledWith(expect.objectContaining({ expected_sequence: 7, issue_code: "PROJECT_IDENTITY_EXCEPTION", subject_kind: "PROJECT_IDENTITY_EXCEPTION" }));
    expect(api.startArchive).toHaveBeenCalledWith(expect.objectContaining({ confirmation_refs: [{ subject_digest: "sha256:selection-subject", sequence: 6 }], anomaly_resolution_refs: [{ subject_digest: "sha256:anomaly", sequence: 7 }] }), undefined);
  });
});

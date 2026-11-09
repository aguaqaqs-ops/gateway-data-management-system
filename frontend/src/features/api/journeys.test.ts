import { describe, expect, it, vi } from "vitest";
import type { GatewayApi } from "./client";
import { applyReviewAction, buildArchiveSelectedRef, createArchiveJourneyProgress, runArchiveJourney, runDatasetReplacementPreview, runPreviewJourney, runReviewHistoryJourney, runSubmitJourney } from "./journeys";
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
    expect(api.startPreview).toHaveBeenCalledWith("ws-1", expect.objectContaining({ expected_workspace_version: 9, expected_baseline_head_version: 12 }), expect.any(String));
    expect(api.getOperation).toHaveBeenCalledWith("op-1", expect.any(AbortSignal));
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

    await expect(applyReviewAction(api, "fe2a-history-ref-2", TEST_REVIEW_FACTS.review_version, "REJECT", "  ")).rejects.toThrow("退回时必须填写理由");
    expect(api.applyReview).not.toHaveBeenCalled();
    await applyReviewAction(api, "fe2a-history-ref-2", TEST_REVIEW_FACTS.review_version, "APPROVE");
    expect(api.applyReview).toHaveBeenCalledWith("fe2a-history-ref-2", { expected_review_version: TEST_REVIEW_FACTS.review_version, action: "APPROVE" });
  });
  it("sends the on-screen review version with the dialog key (B6 probe target)", async () => {
    // Contract: §6.2 + journeys applyReviewAction must send facts.review_version (the version the
    // reviewer saw) with the per-dialog idempotency key. Negative probe (§9 B6): re-reading the
    // version inside applyReviewAction or minting a fresh key per click must fail here.
    const api = {
      getReviewFacts: vi.fn().mockResolvedValue({ ...TEST_REVIEW_FACTS, review_version: 999 }),
      applyReview: vi.fn().mockResolvedValue(TEST_REVIEW_APPLIED),
    } as unknown as GatewayApi;
    await applyReviewAction(api, "fe2a-history-ref-2", TEST_REVIEW_FACTS.review_version, "APPROVE", undefined, "dialog-key-1");
    expect(api.getReviewFacts).not.toHaveBeenCalled();
    expect(api.applyReview).toHaveBeenCalledWith("fe2a-history-ref-2", { expected_review_version: TEST_REVIEW_FACTS.review_version, action: "APPROVE" }, "dialog-key-1");
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

  it("builds archive selected refs with exactly the two backend-accepted keys", () => {
    const candidate = { submission_id: "submission-9", expected_candidate_digest: "sha256:candidate-9", review_version: 42, extra: "must-not-forward" };
    expect(buildArchiveSelectedRef(candidate)).toEqual({ submission_id: "submission-9", expected_candidate_digest: "sha256:candidate-9" });
    expect(Object.keys(buildArchiveSelectedRef(TEST_ARCHIVE_CANDIDATES.candidates[0]!)).sort()).toEqual(["expected_candidate_digest", "submission_id"]);
  });

  it("records archive confirmations and references every accepted anomaly of the latest preview", async () => {
    const firstPlan = ARCHIVE_PLAN_NEEDS_CONFIRMATION;
    const acceptedAnomaly = {
      ...ARCHIVE_PLAN_READY.anomalies[0]!,
      resolution_status: "ACCEPTED" as const,
      latest_sequence: 7,
      accepted_by: "archiver-1",
      accepted_at: "2026-11-07T15:20:00Z",
      reason: "已人工确认",
    };
    const readyPlan = { ...ARCHIVE_PLAN_READY, anomalies: [acceptedAnomaly] };
    const listArchiveCandidates = vi.fn().mockResolvedValue(TEST_ARCHIVE_CANDIDATES);
    const api = {
      listArchiveCandidates,
      listArchiveEvents: vi.fn(async (query: { subjectKind: string; subjectDigest: string }) => query.subjectDigest === "sha256:selection-subject"
        ? TEST_ARCHIVE_EVENTS_WITH_CONFIRMATION
        : TEST_ARCHIVE_EVENTS_EMPTY),
      previewArchive: vi.fn().mockResolvedValueOnce(firstPlan).mockResolvedValueOnce(readyPlan),
      appendArchiveConfirmation: vi.fn().mockResolvedValue(TEST_ARCHIVE_CONFIRM_APPEND),
      appendArchiveAnomalyResolution: vi.fn().mockResolvedValue(TEST_ARCHIVE_RESOLUTION_APPEND),
      startArchive: vi.fn().mockResolvedValue(TEST_ARCHIVE_STARTED),
      getArchiveResult: vi.fn().mockResolvedValue(testArchiveResultWithRefs()),
    } as unknown as GatewayApi;
    await runArchiveJourney(api, {
      selected: buildArchiveSelectedRef(TEST_ARCHIVE_CANDIDATES.candidates[0]!),
      confirmations: [{ subjectDigest: "sha256:selection-subject", action: "CONFIRM", reason: "已核对" }],
    });
    expect(api.listArchiveEvents).toHaveBeenCalledWith(expect.objectContaining({ subjectKind: "CONFIRM_SELECTION", subjectDigest: "sha256:selection-subject", afterSequence: 0 }));
    expect(api.appendArchiveConfirmation).toHaveBeenCalledWith(expect.objectContaining({ expected_sequence: 5, expected_baseline_head_version: 21 }), expect.any(String));
    // Anomaly acceptances are appended in the dialog, not here: the journey must
    // not call appendArchiveAnomalyResolution, and the start refs must cover the
    // ACCEPTED item of the re-fetched (latest) preview.
    expect(api.appendArchiveAnomalyResolution).not.toHaveBeenCalled();
    expect(api.startArchive).toHaveBeenCalledWith(expect.objectContaining({ confirmation_refs: [{ subject_digest: "sha256:selection-subject", sequence: 6 }], anomaly_resolution_refs: [{ subject_digest: "sha256:anomaly", sequence: 7 }] }), expect.any(String));
  });

  it("covers every accepted anomaly without filtering by visibility", async () => {
    const firstAnomaly = ARCHIVE_PLAN_NEEDS_CONFIRMATION.anomalies[0]!;
    const acceptedSecond = { ...firstAnomaly, subject_digest: "sha256:anomaly-2", target_submission_id: "submission-2", resolution_status: "ACCEPTED" as const, latest_sequence: 8 };
    const acceptedFirst = { ...firstAnomaly, resolution_status: "ACCEPTED" as const, latest_sequence: 7 };
    const twoAnomaliesPlan = {
      ...ARCHIVE_PLAN_NEEDS_CONFIRMATION,
      confirmation_requirements: [],
      can_start: true,
      audit_validity: true,
      anomalies: [acceptedFirst, acceptedSecond],
    };
    const api = {
      listArchiveCandidates: vi.fn().mockResolvedValue(TEST_ARCHIVE_CANDIDATES),
      listArchiveEvents: vi.fn().mockResolvedValue(TEST_ARCHIVE_EVENTS_EMPTY),
      previewArchive: vi.fn().mockResolvedValue(twoAnomaliesPlan),
      startArchive: vi.fn().mockResolvedValue(TEST_ARCHIVE_STARTED),
      getArchiveResult: vi.fn().mockResolvedValue(testArchiveResultWithRefs()),
    } as unknown as GatewayApi;
    await runArchiveJourney(api, {
      selected: buildArchiveSelectedRef(TEST_ARCHIVE_CANDIDATES.candidates[0]!),
    });
    expect(vi.mocked(api.startArchive).mock.calls[0]?.[0].anomaly_resolution_refs).toEqual([
      { subject_digest: "sha256:anomaly", sequence: 7 },
      { subject_digest: "sha256:anomaly-2", sequence: 8 },
    ]);
  });

  it("resumes archive retries after a failed start without resending audit events", async () => {
    const progress = createArchiveJourneyProgress();
    const api = {
      listArchiveCandidates: vi.fn().mockResolvedValue(TEST_ARCHIVE_CANDIDATES),
      listArchiveEvents: vi.fn().mockResolvedValue(TEST_ARCHIVE_EVENTS_EMPTY),
      previewArchive: vi.fn().mockResolvedValueOnce(ARCHIVE_PLAN_NEEDS_CONFIRMATION).mockResolvedValue(ARCHIVE_PLAN_READY),
      appendArchiveConfirmation: vi.fn().mockResolvedValue(TEST_ARCHIVE_CONFIRM_APPEND),
      appendArchiveAnomalyResolution: vi.fn().mockResolvedValue(TEST_ARCHIVE_RESOLUTION_APPEND),
      startArchive: vi.fn().mockRejectedValueOnce(new Error("start unavailable")).mockResolvedValue(TEST_ARCHIVE_STARTED),
      getArchiveResult: vi.fn().mockResolvedValue(testArchiveResultWithRefs()),
    } as unknown as GatewayApi;
    const input = {
      selected: { submission_id: "submission-1", expected_candidate_digest: "sha256:candidate" },
      confirmations: [{ subjectDigest: "sha256:selection-subject", action: "CONFIRM" as const, reason: "已核对" }],
    };
    await expect(runArchiveJourney(api, input, progress)).rejects.toThrow("start unavailable");
    await runArchiveJourney(api, input, progress);
    expect(api.appendArchiveConfirmation).toHaveBeenCalledTimes(1);
    expect(api.appendArchiveAnomalyResolution).not.toHaveBeenCalled();
    const startCalls = vi.mocked(api.startArchive).mock.calls;
    expect(startCalls).toHaveLength(2);
    expect(startCalls[0]?.[1]).toEqual(expect.any(String));
    expect(startCalls[0]?.[1]).toBe(startCalls[1]?.[1]);
    expect(startCalls[1]?.[0].confirmation_refs).toEqual([{ subject_digest: "sha256:selection-subject", sequence: 6 }]);
    expect(api.getArchiveResult).toHaveBeenCalledTimes(1);
  });
});

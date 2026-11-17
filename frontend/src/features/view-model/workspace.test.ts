import { describe, expect, it } from "vitest";
import type { components } from "../api/generated/openapi";
import { HISTORY_PAGE_ONE, HISTORY_PAGE_TWO, WORKSPACE_RESPONSE } from "../dev/mock-data";
import {
  buildWorkspaceTree,
  compareToggle,
  deriveWorkbenchActions,
  sortWorkspaceTreeRows,
} from "./workspace";

describe("formal workbench tree and contextual actions", () => {
  const history = {
    ...HISTORY_PAGE_ONE,
    nodes: [...HISTORY_PAGE_ONE.nodes, ...HISTORY_PAGE_TWO.nodes],
    next_cursor: null,
  } satisfies components["schemas"]["HistoryListResponse"];

  it("builds the workspace from CreateOrGet plus History and keeps backend refs intact", () => {
    const rows = buildWorkspaceTree(WORKSPACE_RESPONSE, history);
    const head = rows.find((row) => row.isHead);
    const workspace = rows.find((row) => row.kind === "workspace");
    const pending = rows.find((row) => row.refId === "fe2a-history-ref-2");
    expect(head).toMatchObject({ status: "当前基线", refId: "fe2a-history-ref-1" });
    expect(workspace).toMatchObject({
      kind: "workspace",
      status: "可提交",
      previewResultId: "preview-full",
      uploadRevisionId: "upload-fe2b-3",
      depth: 1,
      parentKey: "baseline_node:fe2a-history-ref-1",
    });
    expect(pending).toMatchObject({
      label: "提交 2",
      status: "待审核",
      depth: 1,
      parentKey: "baseline_node:fe2a-history-ref-1",
      parentRef: { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1" },
    });
    expect(rows.find((row) => row.eligibilityNote === "NOT_CANDIDATE_BASE_ADVANCED")).toMatchObject(
      { status: "已归档", identityException: true },
    );
    expect(rows.some((row) => row.label.includes("历史初始备份"))).toBe(false);
    expect(rows.filter((row) => row.kind === "baseline").map((row) => row.depth)).toEqual([0, 0]);
    expect(rows.find((row) => row.refId === "fe2a-history-ref-0")?.status).toBe("");
    expect(rows.find((row) => row.refId === "fe2a-history-ref-1")?.hasChildren).toBe(true);
  });

  it("offers the workspace Preview only before Submit and points to the submission after it", () => {
    const workspaceRow = (overrides: Partial<components["schemas"]["WorkspaceResponse"]>) =>
      buildWorkspaceTree(
        { ...WORKSPACE_RESPONSE, ...overrides } as components["schemas"]["WorkspaceResponse"],
        history,
      ).find((row) => row.kind === "workspace") ?? null;
    const previewed = workspaceRow({ active_submission_id: null, active_submit_attempt_id: null });
    expect(previewed?.status).toBe("可提交");
    expect(deriveWorkbenchActions(previewed)).toEqual([
      { id: "continue-preview", label: "继续预览并提交", enabled: true, reason: null },
    ]);
    // The backend keeps the Preview pointer until review; the submission wins.
    const submitted = workspaceRow({ active_submission_id: "submission-1" });
    expect(submitted).toMatchObject({
      status: "已提交·待审核",
      statusTone: "pending",
      activeSubmissionId: "submission-1",
    });
    expect(deriveWorkbenchActions(submitted)).toEqual([
      { id: "open-submission", label: "转到提交", enabled: true, reason: null },
    ]);
    const beforePreview = workspaceRow({
      current_preview_result_id: null,
      active_submission_id: null,
    });
    expect(beforePreview?.status).toBe("已上传");
    expect(deriveWorkbenchActions(beforePreview)).toEqual([]);
    expect(deriveWorkbenchActions(workspaceRow({ state: "CLOSED" }))).toEqual([]);
  });

  it("offers the compare checkbox on baselines and submissions and caps it at three nodes", () => {
    const rows = buildWorkspaceTree(WORKSPACE_RESPONSE, history);
    const baseline = rows.find(
      (row) => row.kind === "baseline" && row.refId === "fe2a-history-ref-1",
    )!;
    const workspace = rows.find((row) => row.kind === "workspace")!;
    expect(deriveWorkbenchActions(baseline)).toEqual([]);
    expect(compareToggle(baseline, 0, false)).toEqual({
      available: true,
      enabled: true,
      reason: null,
    });
    expect(compareToggle(baseline, 3, false)).toEqual({
      available: true,
      enabled: false,
      reason: "比较托盘最多选择 3 个节点",
    });
    expect(compareToggle(baseline, 3, true)).toMatchObject({ enabled: true });
    expect(compareToggle(baseline, 1, false, true)).toMatchObject({
      enabled: false,
      reason: "历史比较执行中，暂不能调整比较节点",
    });
    expect(compareToggle(workspace, 0, false).available).toBe(false);
  });

  it("separates the submission-time diff, review and parent History compare on a submission", () => {
    const rows = buildWorkspaceTree(WORKSPACE_RESPONSE, history);
    const pending = rows.find((row) => row.refId === "fe2a-history-ref-2") ?? null;
    const stale = rows.find((row) => row.eligibilityNote) ?? null;
    expect(deriveWorkbenchActions(pending)).toEqual([
      { id: "view-submission-diff", label: "查看提交时差异", enabled: true, reason: null },
      { id: "open-review", label: "去审核", enabled: true, reason: null },
      { id: "compare-parent", label: "比较父节点 → 此提交", enabled: true, reason: null },
      { id: "archive-mainline", label: "归档主线", enabled: false, reason: "提交尚未审核通过" },
    ]);
    expect(
      deriveWorkbenchActions(pending, true).find((action) => action.id === "compare-parent"),
    ).toMatchObject({ enabled: false, reason: "历史比较执行中，暂不能发起新比较" });
    expect(
      deriveWorkbenchActions(pending, true).find((action) => action.id === "view-submission-diff"),
    ).toMatchObject({ enabled: true });
    const approved = { ...pending!, reviewStatus: "APPROVED" as const };
    expect(deriveWorkbenchActions(approved).map((action) => action.id)).not.toContain(
      "open-review",
    );
    expect(compareToggle(pending!, 3, false)).toMatchObject({
      enabled: false,
      reason: "比较托盘最多选择 3 个节点",
    });
    expect(
      deriveWorkbenchActions(stale).find((action) => action.id === "archive-mainline"),
    ).toMatchObject({ enabled: false, reason: "该提交已归档" });
    const eligible = { ...pending!, reviewStatus: "APPROVED" as const, eligibilityNote: null };
    expect(
      deriveWorkbenchActions(eligible).find((action) => action.id === "archive-mainline"),
    ).toMatchObject({ enabled: true, reason: null });
  });

  it("keeps tree children attached to their parent while sorting siblings", () => {
    const rows = buildWorkspaceTree(WORKSPACE_RESPONSE, history, [
      { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-0" },
      { ref_kind: "submission", ref_id: "fe2a-history-ref-2" },
    ]);
    const sorted = sortWorkspaceTreeRows(rows, { column: "label", direction: -1 });
    expect(sorted.find((row) => row.refId === "fe2a-history-ref-2")).toMatchObject({
      depth: 1,
      parentKey: "baseline_node:fe2a-history-ref-1",
      compareOrder: 2,
    });
    expect(sorted.find((row) => row.refId === "fe2a-history-ref-0")).toMatchObject({
      depth: 0,
      compareOrder: 1,
    });
    const currentIndex = sorted.findIndex((row) => row.refId === "fe2a-history-ref-1");
    const oldIndex = sorted.findIndex((row) => row.refId === "fe2a-history-ref-0");
    expect(currentIndex).toBeGreaterThan(-1);
    expect(oldIndex).toBeGreaterThan(-1);
    expect(sorted.find((row) => row.key === "workspace:workspace-fe2b")?.parentKey).toBe(
      "baseline_node:fe2a-history-ref-1",
    );
  });
  it("numbers archived baselines by creation time and breaks ties by ref_id (Q11)", () => {
    const initial = HISTORY_PAGE_TWO.nodes.find((node) => node.baseline_kind === "INITIAL")!;
    const archived = HISTORY_PAGE_ONE.nodes.find((node) => node.node_kind === "BASELINE_NODE")!;
    const tied = { ...archived, ref_id: "fe2a-history-ref-a", created_at: "2026-11-02T10:00:00Z" };
    const later = { ...archived, ref_id: "fe2a-history-ref-b", created_at: "2026-11-02T10:00:00Z" };
    const customHistory = {
      ...history,
      head: { ...history.head, node_id: "fe2a-history-ref-a" },
      nodes: [initial, later, tied],
    } satisfies components["schemas"]["HistoryListResponse"];
    const rows = buildWorkspaceTree(WORKSPACE_RESPONSE, customHistory);
    expect(rows.find((row) => row.refId === "fe2a-history-ref-0")?.label).toBe("初始基线");
    expect(rows.find((row) => row.refId === "fe2a-history-ref-a")?.label).toBe("归档基线 1");
    expect(rows.find((row) => row.refId === "fe2a-history-ref-b")?.label).toBe("归档基线 2");
  });

  it("maps terminal dispositions onto the tree and archive action (D1-D4)", () => {
    const approved = HISTORY_PAGE_TWO.nodes.find((node) => node.review_status === "APPROVED")!;
    const archivedNode = {
      ...approved,
      ref_id: "fe2a-history-ref-d1",
      commit_id: "commit-d1",
      submission_disposition: "ARCHIVED_BASELINE" as const,
      disposition_source_kind: "ARCHIVE" as const,
      disposition_result_id: "archive-result-1",
      eligibility_note: "NOT_CANDIDATE_BASE_ADVANCED" as const,
    };
    const closedAtArchive = {
      ...approved,
      ref_id: "fe2a-history-ref-d2",
      commit_id: "commit-d2",
      submission_disposition: "CLOSED_NOT_ARCHIVED" as const,
      disposition_source_kind: "ARCHIVE" as const,
      disposition_result_id: "archive-result-1",
    };
    const manualClose = {
      ...approved,
      ref_id: "fe2a-history-ref-d3",
      commit_id: "commit-d3",
      submission_disposition: "CLOSED_NOT_ARCHIVED" as const,
      disposition_source_kind: "MANUAL_CLOSE" as const,
      disposition_result_id: null,
      closure: { closed_by: "owner-1", closed_at: "2026-11-06T08:00:00Z", reason: "有理由关闭" },
    };
    const customHistory = {
      ...history,
      nodes: [approved, archivedNode, closedAtArchive, manualClose, ...HISTORY_PAGE_ONE.nodes],
    } satisfies components["schemas"]["HistoryListResponse"];
    const rows = buildWorkspaceTree(WORKSPACE_RESPONSE, customHistory);
    const archived = rows.find((row) => row.refId === archivedNode.ref_id)!;
    expect(archived).toMatchObject({
      status: "已归档",
      statusTone: "info",
      submissionDisposition: "ARCHIVED_BASELINE",
    });
    expect(
      deriveWorkbenchActions(archived).find((action) => action.id === "archive-mainline"),
    ).toMatchObject({ enabled: false, reason: "该提交已归档" });
    const closed = rows.find((row) => row.refId === closedAtArchive.ref_id)!;
    expect(
      deriveWorkbenchActions(closed).find((action) => action.id === "archive-mainline"),
    ).toMatchObject({ enabled: false, reason: "该提交已关闭（未归档）" });
    const manual = rows.find((row) => row.refId === manualClose.ref_id)!;
    expect(manual.closure).toMatchObject({ closed_by: "owner-1", reason: "有理由关闭" });
    expect(
      deriveWorkbenchActions(manual).find((action) => action.id === "archive-mainline"),
    ).toMatchObject({ enabled: false, reason: "该提交已关闭（未归档）" });
    const flagOnly = {
      ...approved,
      ref_id: "fe2a-history-ref-d5",
      commit_id: "commit-d5",
      submission_disposition: null,
      disposition_source_kind: null,
      disposition_result_id: null,
      eligibility_note: "NOT_CANDIDATE_BASE_ADVANCED" as const,
    };
    const flagHistory = {
      ...history,
      nodes: [flagOnly, ...HISTORY_PAGE_ONE.nodes],
    } satisfies components["schemas"]["HistoryListResponse"];
    const flagRow = buildWorkspaceTree(WORKSPACE_RESPONSE, flagHistory).find(
      (row) => row.refId === flagOnly.ref_id,
    )!;
    expect(flagRow).toMatchObject({
      status: "已通过",
      eligibilityNote: "NOT_CANDIDATE_BASE_ADVANCED",
      submissionDisposition: null,
    });
    expect(
      deriveWorkbenchActions(flagRow).find((action) => action.id === "archive-mainline"),
    ).toMatchObject({ enabled: false, reason: "该提交所基于的基线已不是当前基线" });
  });
});

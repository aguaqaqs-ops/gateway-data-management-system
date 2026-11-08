import { describe, expect, it } from "vitest";
import type { components } from "../api/generated/openapi";
import { HISTORY_PAGE_ONE, HISTORY_PAGE_TWO, WORKSPACE_RESPONSE } from "../dev/mock-data";
import { buildWorkspaceTree, deriveWorkbenchActions, sortWorkspaceTreeRows } from "./workspace";

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
    expect(workspace).toMatchObject({ kind: "workspace", status: "可提交", previewResultId: "preview-full", uploadRevisionId: "upload-fe2b-3", depth: 1, parentKey: "baseline_node:fe2a-history-ref-1" });
    expect(pending).toMatchObject({ label: "提交 2", status: "待审核", depth: 1, parentKey: "baseline_node:fe2a-history-ref-1", parentRef: { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1" } });
    expect(rows.find((row) => row.eligibilityNote === "NOT_CANDIDATE_BASE_ADVANCED")).toMatchObject({ status: "已通过", identityException: true });
    expect(rows.some((row) => row.label.includes("历史初始备份"))).toBe(false);
    expect(rows.filter((row) => row.kind === "baseline").map((row) => row.depth)).toEqual([0, 0]);
    expect(rows.find((row) => row.refId === "fe2a-history-ref-0")?.status).toBe("");
    expect(rows.find((row) => row.refId === "fe2a-history-ref-1")?.hasChildren).toBe(true);
  });

  it("shows workspace actions and gates upload on card readiness", () => {
    const workspace = buildWorkspaceTree(WORKSPACE_RESPONSE, history).find((row) => row.kind === "workspace") ?? null;
    expect(deriveWorkbenchActions(workspace, 0, false)).toEqual([
      { id: "original-backup", label: "原始组态备份", enabled: true, reason: null },
      { id: "current-archive", label: "本次归档组态", enabled: true, reason: null },
      { id: "upload", label: "上传", enabled: true, reason: null },
    ]);
    const beforePreview = buildWorkspaceTree({ ...WORKSPACE_RESPONSE, current_preview_result_id: null }, history).find((row) => row.kind === "workspace") ?? null;
    expect(beforePreview?.status).toBe("已上传");
    expect(deriveWorkbenchActions(beforePreview, 0, false).slice(0, 2).every((action) => action.enabled)).toBe(true);
    const closed = buildWorkspaceTree({ ...WORKSPACE_RESPONSE, state: "CLOSED" }, history).find((row) => row.kind === "workspace") ?? null;
    expect(deriveWorkbenchActions(closed, 0, false).slice(0, 2).every((action) => !action.enabled && action.reason?.includes("工作区已关闭"))).toBe(true);
  });

  it("offers compare on baselines and caps it at three selected nodes", () => {
    const rows = buildWorkspaceTree(WORKSPACE_RESPONSE, history);
    const baseline = rows.find((row) => row.kind === "baseline" && row.refId === "fe2a-history-ref-1") ?? null;
    expect(deriveWorkbenchActions(baseline, 0, false)).toEqual([{ id: "join-compare", label: "加入比较", enabled: true, reason: null }]);
    expect(deriveWorkbenchActions(baseline, 3, false)[0]).toMatchObject({ enabled: false, reason: "比较托盘最多选择 3 个节点" });
    expect(deriveWorkbenchActions(baseline, 1, true)[0]).toMatchObject({ id: "remove-compare", enabled: true });
  });

  it("shows submission review and archive eligibility with explicit disabled reasons", () => {
    const rows = buildWorkspaceTree(WORKSPACE_RESPONSE, history);
    const pending = rows.find((row) => row.refId === "fe2a-history-ref-2") ?? null;
    const stale = rows.find((row) => row.eligibilityNote) ?? null;
    expect(deriveWorkbenchActions(pending, 0, false)).toEqual([
      { id: "view-diff", label: "查看差异", enabled: true, reason: null },
      { id: "join-compare", label: "加入比较", enabled: true, reason: null },
      { id: "archive-mainline", label: "归档主线", enabled: false, reason: "提交尚未审核通过" },
    ]);
    expect(deriveWorkbenchActions(pending, 3, false).find((action) => action.id === "join-compare"))
      .toMatchObject({ enabled: false, reason: "比较托盘最多选择 3 个节点" });
    expect(deriveWorkbenchActions(stale, 0, false).find((action) => action.id === "archive-mainline"))
      .toMatchObject({ enabled: false, reason: "该提交所基于的基线已不是当前基线" });
    const eligible = { ...pending!, reviewStatus: "APPROVED" as const, eligibilityNote: null };
    expect(deriveWorkbenchActions(eligible, 0, false).find((action) => action.id === "archive-mainline"))
      .toMatchObject({ enabled: true, reason: null });
  });

  it("keeps tree children attached to their parent while sorting siblings", () => {
    const rows = buildWorkspaceTree(WORKSPACE_RESPONSE, history, [
      { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-0" },
      { ref_kind: "submission", ref_id: "fe2a-history-ref-2" },
    ]);
    const sorted = sortWorkspaceTreeRows(rows, { column: "label", direction: -1 });
    expect(sorted.find((row) => row.refId === "fe2a-history-ref-2")).toMatchObject({ depth: 1, parentKey: "baseline_node:fe2a-history-ref-1", compareOrder: 2 });
    expect(sorted.find((row) => row.refId === "fe2a-history-ref-0")).toMatchObject({ depth: 0, compareOrder: 1 });
    const currentIndex = sorted.findIndex((row) => row.refId === "fe2a-history-ref-1");
    const oldIndex = sorted.findIndex((row) => row.refId === "fe2a-history-ref-0");
    expect(currentIndex).toBeGreaterThan(-1);
    expect(oldIndex).toBeGreaterThan(-1);
    expect(sorted.find((row) => row.key === "workspace:workspace-fe2b")?.parentKey).toBe("baseline_node:fe2a-history-ref-1");
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
    const customHistory = { ...history, nodes: [approved, archivedNode, closedAtArchive, manualClose, ...HISTORY_PAGE_ONE.nodes] } satisfies components["schemas"]["HistoryListResponse"];
    const rows = buildWorkspaceTree(WORKSPACE_RESPONSE, customHistory);
    const archived = rows.find((row) => row.refId === archivedNode.ref_id)!;
    expect(archived).toMatchObject({ status: "已归档", statusTone: "info", submissionDisposition: "ARCHIVED_BASELINE" });
    expect(deriveWorkbenchActions(archived, 0, false).find((action) => action.id === "archive-mainline"))
      .toMatchObject({ enabled: false, reason: "该提交已归档" });
    const closed = rows.find((row) => row.refId === closedAtArchive.ref_id)!;
    expect(deriveWorkbenchActions(closed, 0, false).find((action) => action.id === "archive-mainline"))
      .toMatchObject({ enabled: false, reason: "该提交已关闭（未归档）" });
    const manual = rows.find((row) => row.refId === manualClose.ref_id)!;
    expect(manual.closure).toMatchObject({ closed_by: "owner-1", reason: "有理由关闭" });
    expect(deriveWorkbenchActions(manual, 0, false).find((action) => action.id === "archive-mainline"))
      .toMatchObject({ enabled: false, reason: "该提交已关闭（未归档）" });
    const flagOnly = { ...approved, ref_id: "fe2a-history-ref-d5", commit_id: "commit-d5", submission_disposition: null, disposition_source_kind: null, disposition_result_id: null, eligibility_note: "NOT_CANDIDATE_BASE_ADVANCED" as const };
    const flagHistory = { ...history, nodes: [flagOnly, ...HISTORY_PAGE_ONE.nodes] } satisfies components["schemas"]["HistoryListResponse"];
    const flagRow = buildWorkspaceTree(WORKSPACE_RESPONSE, flagHistory).find((row) => row.refId === flagOnly.ref_id)!;
    expect(flagRow).toMatchObject({ status: "已通过", eligibilityNote: "NOT_CANDIDATE_BASE_ADVANCED", submissionDisposition: null });
    expect(deriveWorkbenchActions(flagRow, 0, false).find((action) => action.id === "archive-mainline"))
      .toMatchObject({ enabled: false, reason: "该提交所基于的基线已不是当前基线" });
  });

});

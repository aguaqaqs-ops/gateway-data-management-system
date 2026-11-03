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

  it("shows workspace actions and keeps upload disabled with its prerequisite", () => {
    const workspace = buildWorkspaceTree(WORKSPACE_RESPONSE, history).find((row) => row.kind === "workspace") ?? null;
    expect(deriveWorkbenchActions(workspace, 0, false)).toEqual([
      { id: "original-backup", label: "原始组态备份", enabled: true, reason: null },
      { id: "current-archive", label: "本次归档组态", enabled: true, reason: null },
      { id: "upload", label: "上传", enabled: false, reason: "需先选择本次归档组态目录" },
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
      .toMatchObject({ enabled: false, reason: "该提交所基于的基线已不是当前基线，不能归档" });
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
});

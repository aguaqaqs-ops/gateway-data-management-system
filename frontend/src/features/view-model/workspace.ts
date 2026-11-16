import type { components } from "../api/generated/openapi";
import { baselineDisplayLabel, baselineDisplayLabelFor } from "./baseline-labels";

type Schemas = components["schemas"];

export type WorkspaceTreeRow = {
  key: string;
  kind: "workspace" | "baseline" | "submission" | "migration";
  label: string;
  status: string;
  statusTone: "success" | "info" | "pending" | "warning" | "neutral";
  depth: number;
  parentKey: string | null;
  hasChildren: boolean;
  compareOrder?: number;
  createdAt: string | null;
  submitAt: string | null;
  /** The one time the tree shows: baseline creation, submit time, or the workspace's last update. */
  time: string | null;
  refKind?: Schemas["HistoryNodeResponse"]["ref_kind"];
  refId?: string;
  parentRef?: Schemas["HistoryNodeRefResponse"] | null;
  baselineKind?: Schemas["HistoryNodeResponse"]["baseline_kind"];
  reviewStatus?: Schemas["HistoryNodeResponse"]["review_status"];
  eligibilityNote?: Schemas["HistoryNodeResponse"]["eligibility_note"];
  identityException?: boolean;
  isHead?: boolean;
  previewResultId?: string | null;
  uploadRevisionId?: string | null;
  workspaceState?: Schemas["WorkspaceResponse"]["state"];
  /** Set while the workspace's current Preview is bound to a submission awaiting review. */
  activeSubmissionId?: string | null;
  submissionDisposition?: Schemas["HistoryNodeResponse"]["submission_disposition"];
  dispositionSourceKind?: Schemas["HistoryNodeResponse"]["disposition_source_kind"];
  dispositionResultId?: string | null;
  closure?: Schemas["SubmissionClosureSummaryResponse"] | null;
  promotedBaselineNodeId?: string | null;
  dispositionBaselineLabel?: string | null;
};

function dispositionStatus(node: Schemas["HistoryNodeResponse"]): string | null {
  if (node.submission_disposition === "ARCHIVED_BASELINE") return "已归档";
  if (node.submission_disposition === "CLOSED_NOT_ARCHIVED") return "已关闭（未归档）";
  return null;
}

function historyStatus(node: Schemas["HistoryNodeResponse"], isHead: boolean): string {
  if (node.node_kind === "BASELINE_NODE") return isHead ? "当前基线" : "";
  if (node.node_kind === "SYSTEM_MIGRATION") return "";
  const disposition = dispositionStatus(node);
  if (disposition) return disposition;
  switch (node.review_status) {
    case "PENDING": return "待审核";
    case "APPROVED": return "已通过";
    case "REJECTED": return "已退回";
    case "WITHDRAWN": return "已撤回";
    default: return "状态未知";
  }
}

function historyStatusTone(node: Schemas["HistoryNodeResponse"], isHead: boolean): WorkspaceTreeRow["statusTone"] {
  if (node.node_kind === "BASELINE_NODE") return isHead ? "info" : "neutral";
  if (node.node_kind === "SYSTEM_MIGRATION") return "neutral";
  if (node.submission_disposition === "ARCHIVED_BASELINE") return "info";
  if (node.submission_disposition === "CLOSED_NOT_ARCHIVED") return "neutral";
  switch (node.review_status) {
    case "PENDING": return "pending";
    case "APPROVED": return "success";
    case "REJECTED": return "warning";
    default: return "neutral";
  }
}

function historyKind(node: Schemas["HistoryNodeResponse"]): WorkspaceTreeRow["kind"] {
  if (node.node_kind === "BASELINE_NODE") return "baseline";
  if (node.node_kind === "SUBMISSION") return "submission";
  return "migration";
}

function nodeKey(refKind: string, refId: string): string {
  return `${refKind}:${refId}`;
}

// The backend keeps current_preview_result_id after Submit until review,
// withdrawal or close, so a submission (or a submit in progress) wins over
// the Preview pointer.
function workspaceStatus(workspace: Schemas["WorkspaceResponse"]): string {
  if (workspace.state === "CLOSED") return "已关闭";
  if (workspace.active_submission_id) return "已提交·待审核";
  if (workspace.active_submit_attempt_id) return "提交中";
  if (workspace.current_preview_result_id) return "可提交";
  if (workspace.current_upload_revision_id) return "已上传";
  return "未上传";
}

function workspaceStatusTone(workspace: Schemas["WorkspaceResponse"]): WorkspaceTreeRow["statusTone"] {
  if (workspace.state === "CLOSED") return "neutral";
  if (workspace.active_submission_id || workspace.active_submit_attempt_id) return "pending";
  if (workspace.current_preview_result_id) return "success";
  return workspace.current_upload_revision_id ? "info" : "neutral";
}

function workspaceRow(workspace: Schemas["WorkspaceResponse"], parentKey: string | null, depth: number): WorkspaceTreeRow {
  return {
    key: `workspace:${workspace.workspace_id}`,
    kind: "workspace",
    label: `工作区 ${workspace.gateway_device_external_key}`,
    status: workspaceStatus(workspace),
    statusTone: workspaceStatusTone(workspace),
    depth,
    parentKey,
    hasChildren: false,
    createdAt: workspace.created_at,
    submitAt: null,
    time: workspace.updated_at,
    previewResultId: workspace.current_preview_result_id,
    uploadRevisionId: workspace.current_upload_revision_id,
    workspaceState: workspace.state,
    activeSubmissionId: workspace.active_submission_id,
  };
}

export function buildWorkspaceTree(
  workspace: Schemas["WorkspaceResponse"],
  history: Schemas["HistoryListResponse"],
  comparisonRefs: Schemas["HistoryCompareNodeRequest"][] = [],
): WorkspaceTreeRow[] {
  const rows: WorkspaceTreeRow[] = [];
  const byRef = new Map(history.nodes.map((node) => [nodeKey(node.ref_kind, node.ref_id), node]));
  const compareOrder = new Map(comparisonRefs.map((node, index) => [nodeKey(node.ref_kind, node.ref_id), index + 1]));
  const submissionLabels = new Map(history.nodes
    .filter((node) => node.node_kind === "SUBMISSION")
    .sort((left, right) => left.created_at.localeCompare(right.created_at))
    .map((node, index) => [nodeKey(node.ref_kind, node.ref_id), `提交 ${index + 1}`]));
  const isHead = (node: Schemas["HistoryNodeResponse"]) => node.node_kind === "BASELINE_NODE" && node.ref_id === history.head.node_id;
  const baselines = history.nodes.filter((node) => node.node_kind === "BASELINE_NODE")
    .sort((left, right) => Number(isHead(right)) - Number(isHead(left)) || right.created_at.localeCompare(left.created_at));
  const baselineOwner = (node: Schemas["HistoryNodeResponse"]): Schemas["HistoryNodeResponse"] | null => {
    let parentRef = node.parent;
    const visited = new Set<string>();
    while (parentRef) {
      const key = nodeKey(parentRef.ref_kind, parentRef.ref_id);
      if (visited.has(key)) return null;
      visited.add(key);
      const parent = byRef.get(key);
      if (!parent) return null;
      if (parent.node_kind === "BASELINE_NODE") return parent;
      parentRef = parent.parent;
    }
    return null;
  };
  const appendNode = (node: Schemas["HistoryNodeResponse"], parentKey: string | null, depth: number): void => {
    const key = nodeKey(node.ref_kind, node.ref_id);
    const current = isHead(node);
    rows.push({
      key,
      kind: historyKind(node),
      label: node.node_kind === "BASELINE_NODE"
        ? baselineDisplayLabel(history, node)
        : node.node_kind === "SYSTEM_MIGRATION" ? "规则迁移" : submissionLabels.get(key) ?? "提交",
      status: historyStatus(node, current),
      statusTone: historyStatusTone(node, current),
      depth,
      parentKey,
      hasChildren: false,
      createdAt: node.created_at,
      submitAt: node.node_kind === "SUBMISSION" ? node.created_at : null,
      time: node.created_at,
      refKind: node.ref_kind,
      refId: node.ref_id,
      parentRef: node.parent,
      baselineKind: node.baseline_kind,
      reviewStatus: node.review_status,
      eligibilityNote: node.eligibility_note,
      identityException: node.identity_exception,
      isHead: current,
      compareOrder: compareOrder.get(key),
      submissionDisposition: node.submission_disposition,
      dispositionSourceKind: node.disposition_source_kind,
      dispositionResultId: node.disposition_result_id,
      closure: node.closure,
      promotedBaselineNodeId: node.promoted_baseline_node_id,
      dispositionBaselineLabel: node.promoted_baseline_node_id ? baselineDisplayLabelFor(history, node.promoted_baseline_node_id) : null,
    });
  };

  const appended = new Set<string>();
  for (const baseline of baselines) {
    const key = nodeKey(baseline.ref_kind, baseline.ref_id);
    appendNode(baseline, null, 0);
    appended.add(key);
    if (isHead(baseline)) rows.push(workspaceRow(workspace, key, 1));
    const descendants = history.nodes.filter((node) => node.node_kind !== "BASELINE_NODE" && baselineOwner(node)?.ref_id === baseline.ref_id)
      .sort((left, right) => left.created_at.localeCompare(right.created_at));
    for (const node of descendants) {
      const childKey = nodeKey(node.ref_kind, node.ref_id);
      if (appended.has(childKey)) continue;
      appendNode(node, key, 1);
      appended.add(childKey);
    }
  }
  for (const node of history.nodes) {
    const key = nodeKey(node.ref_kind, node.ref_id);
    if (appended.has(key)) continue;
    appendNode(node, null, 0);
    appended.add(key);
  }

  const parentKeys = new Set(rows.flatMap((row) => row.parentKey ? [row.parentKey] : []));
  for (const row of rows) row.hasChildren = parentKeys.has(row.key);
  if (!rows.some((row) => row.kind === "workspace")) rows.unshift(workspaceRow(workspace, null, 0));
  return rows;
}

export function sortWorkspaceTreeRows<T extends WorkspaceTreeRow>(
  rows: T[],
  sort: { column: "label" | "time"; direction: 1 | -1 } | null,
): T[] {
  if (!sort) return rows;
  const children = new Map<string | null, T[]>();
  for (const row of rows) {
    const group = children.get(row.parentKey) ?? [];
    group.push(row);
    children.set(row.parentKey, group);
  }
  const compare = (left: T, right: T) => String(left[sort.column] ?? "").localeCompare(String(right[sort.column] ?? ""), "zh-CN") * sort.direction;
  const result: T[] = [];
  const visit = (parentKey: string | null): void => {
    for (const row of [...(children.get(parentKey) ?? [])].sort(compare)) {
      result.push(row);
      visit(row.key);
    }
  };
  visit(null);
  return result;
}

export type WorkbenchActionId = "continue-preview" | "open-submission" | "view-submission-diff" | "open-review" | "compare-parent" | "archive-mainline";

export interface WorkbenchAction {
  id: WorkbenchActionId;
  label: string;
  enabled: boolean;
  reason: string | null;
}

/**
 * Node actions shown at the top of the details panel (and on the row when the
 * panel is collapsed). Upload controls live in the workspace panel itself;
 * compare selection is the per-row checkbox (see compareToggle).
 *
 * The workspace offers its Preview only before Submit: once a submission
 * holds that Preview, its diff belongs to the submission node.
 *
 * A submission offers two different diffs: the frozen submission-time Preview
 * result (read-only, Submission result permission) and an explicit History
 * compare from its parent node (current rules, read_project_history).
 */
export function deriveWorkbenchActions(row: WorkspaceTreeRow | null, comparisonLocked = false): WorkbenchAction[] {
  if (!row) return [];
  const blocked = (id: WorkbenchActionId, label: string, reason: string): WorkbenchAction => ({ id, label, enabled: false, reason });
  const enabled = (id: WorkbenchActionId, label: string): WorkbenchAction => ({ id, label, enabled: true, reason: null });
  if (row.kind === "workspace") {
    if (row.workspaceState === "CLOSED") return [];
    if (row.activeSubmissionId) return [enabled("open-submission", "转到提交")];
    return row.previewResultId ? [enabled("continue-preview", "继续预览并提交")] : [];
  }
  if (row.kind === "submission") {
    const dispositionReason = row.submissionDisposition === "ARCHIVED_BASELINE"
      ? "该提交已归档"
      : row.submissionDisposition === "CLOSED_NOT_ARCHIVED"
        ? "该提交已关闭（未归档）"
        : null;
    return [
      enabled("view-submission-diff", "查看提交时差异"),
      ...(row.reviewStatus === "PENDING" ? [enabled("open-review", "去审核")] : []),
      comparisonLocked
        ? blocked("compare-parent", "比较父节点 → 此提交", "历史比较执行中，暂不能发起新比较")
        : row.parentRef ? enabled("compare-parent", "比较父节点 → 此提交") : blocked("compare-parent", "比较父节点 → 此提交", "提交缺少基线节点"),
      dispositionReason
        ? blocked("archive-mainline", "归档主线", dispositionReason)
        : row.reviewStatus === "APPROVED" && row.eligibilityNote == null
          ? enabled("archive-mainline", "归档主线")
          : blocked("archive-mainline", "归档主线", row.eligibilityNote ? "该提交所基于的基线已不是当前基线" : row.reviewStatus === "PENDING" ? "提交尚未审核通过" : "当前提交不符合归档条件"),
    ];
  }
  return [];
}

/** The per-row compare checkbox: only baselines and submissions can be compared. */
export function compareToggle(row: WorkspaceTreeRow, comparisonCount: number, isCompared: boolean, comparisonLocked = false): { available: boolean; enabled: boolean; reason: string | null } {
  if (row.kind !== "baseline" && row.kind !== "submission" || !row.refId) return { available: false, enabled: false, reason: null };
  if (comparisonLocked) return { available: true, enabled: false, reason: "历史比较执行中，暂不能调整比较节点" };
  if (!isCompared && comparisonCount >= 3) return { available: true, enabled: false, reason: "比较托盘最多选择 3 个节点" };
  return { available: true, enabled: true, reason: null };
}

/** B7: a provisioned device whose History still has only the initial baseline. */
export function hasOnlyInitialBaseline(history: Schemas["HistoryListResponse"]): boolean {
  return history.nodes.length > 0
    && history.nodes.every((node) => node.node_kind === "BASELINE_NODE" && node.baseline_kind === "INITIAL");
}

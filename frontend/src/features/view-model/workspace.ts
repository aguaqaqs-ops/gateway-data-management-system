import type { components } from "../api/generated/openapi";

type Schemas = components["schemas"];

export type WorkspaceTreeRow = {
  key: string;
  kind: "workspace" | "baseline" | "submission" | "migration";
  label: string;
  status: string;
  depth: number;
  createdAt: string | null;
  submitAt: string | null;
  reviewAt: string | null;
  refKind?: Schemas["HistoryNodeResponse"]["ref_kind"];
  refId?: string;
  parentRef?: Schemas["HistoryNodeRefResponse"] | null;
  baselineKind?: Schemas["HistoryNodeResponse"]["baseline_kind"];
  reviewStatus?: Schemas["HistoryNodeResponse"]["review_status"];
  archiveDisposition?: Schemas["HistoryNodeResponse"]["archive_disposition"];
  eligibilityNote?: Schemas["HistoryNodeResponse"]["eligibility_note"];
  identityException?: boolean;
  isHead?: boolean;
  previewResultId?: string | null;
  uploadRevisionId?: string | null;
};

function historyStatus(node: Schemas["HistoryNodeResponse"], isHead: boolean): string {
  if (isHead && node.node_kind === "BASELINE_NODE") return "当前基线";
  if (node.archive_disposition === "ARCHIVED_BASELINE") return "已归档";
  if (node.archive_disposition === "CLOSED_NOT_ARCHIVED") return "未归档关闭";
  if (node.node_kind === "BASELINE_NODE") {
    if (isHead) return "当前基线";
    return node.baseline_kind === "INITIAL" ? "初始基线" : "已归档";
  }
  if (node.node_kind === "SYSTEM_MIGRATION") return "已迁移";
  switch (node.review_status) {
    case "PENDING": return "待审核";
    case "APPROVED": return "已通过";
    case "REJECTED":
    case "RETURNED_FOR_REVISION": return "已退回";
    case "WITHDRAWN": return "已撤回";
    default: return "状态未知";
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

function workspaceStatus(workspace: Schemas["WorkspaceResponse"]): string {
  if (workspace.state === "CLOSED") return "已关闭";
  if (workspace.current_preview_result_id) return "可提交";
  if (workspace.current_upload_revision_id) return "已上传";
  return "未上传";
}

export function buildWorkspaceTree(
  workspace: Schemas["WorkspaceResponse"],
  history: Schemas["HistoryListResponse"],
): WorkspaceTreeRow[] {
  const rows: WorkspaceTreeRow[] = [];
  const byRef = new Map(history.nodes.map((node) => [nodeKey(node.ref_kind, node.ref_id), node]));
  const submissionLabels = new Map(history.nodes
    .filter((node) => node.node_kind === "SUBMISSION")
    .sort((left, right) => left.created_at.localeCompare(right.created_at))
    .map((node, index) => [nodeKey(node.ref_kind, node.ref_id), `提交 ${index + 1}`]));
  const children = new Map<string, Schemas["HistoryNodeResponse"][]>();
  const roots: Schemas["HistoryNodeResponse"][] = [];
  for (const node of history.nodes) {
    const parent = node.parent ? byRef.get(nodeKey(node.parent.ref_kind, node.parent.ref_id)) : undefined;
    if (!parent) roots.push(node);
    else {
      const key = nodeKey(parent.ref_kind, parent.ref_id);
      const values = children.get(key) ?? [];
      values.push(node);
      children.set(key, values);
    }
  }
  roots.sort((left, right) => Number(right.ref_id === history.head.node_id) - Number(left.ref_id === history.head.node_id));
  const visited = new Set<string>();
  const append = (node: Schemas["HistoryNodeResponse"], depth: number): void => {
    const key = nodeKey(node.ref_kind, node.ref_id);
    if (visited.has(key)) return;
    visited.add(key);
    const isHead = node.ref_id === history.head.node_id;
    rows.push({
      key,
      kind: historyKind(node),
      label: node.node_kind === "BASELINE_NODE"
        ? (node.baseline_kind === "INITIAL" ? "初始基线" : "归档基线")
        : node.node_kind === "SYSTEM_MIGRATION" ? "规则迁移" : submissionLabels.get(key) ?? "提交",
      status: historyStatus(node, isHead),
      depth,
      createdAt: node.created_at,
      submitAt: node.node_kind === "SUBMISSION" ? node.created_at : null,
      reviewAt: null,
      refKind: node.ref_kind,
      refId: node.ref_id,
      parentRef: node.parent,
      baselineKind: node.baseline_kind,
      reviewStatus: node.review_status,
      archiveDisposition: node.archive_disposition,
      eligibilityNote: node.eligibility_note,
      identityException: node.identity_exception,
      isHead,
    });
    if (isHead) {
      rows.push({
        key: `workspace:${workspace.workspace_id}`,
        kind: "workspace",
        label: `工作区 ${workspace.gateway_device_external_key}`,
        status: workspaceStatus(workspace),
        depth: depth + 1,
        createdAt: workspace.created_at,
        submitAt: null,
        reviewAt: null,
        previewResultId: workspace.current_preview_result_id,
        uploadRevisionId: workspace.current_upload_revision_id,
      });
    }
    const orderedChildren = [...(children.get(key) ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at));
    for (const child of orderedChildren) append(child, depth + 1);
  };
  for (const root of roots) append(root, 0);
  for (const node of history.nodes) if (!visited.has(nodeKey(node.ref_kind, node.ref_id))) append(node, 0);
  if (!rows.some((row) => row.kind === "workspace")) {
    rows.unshift({
      key: `workspace:${workspace.workspace_id}`, kind: "workspace", label: `工作区 ${workspace.gateway_device_external_key}`,
      status: workspaceStatus(workspace), depth: 0, createdAt: workspace.created_at,
      submitAt: null, reviewAt: null, previewResultId: workspace.current_preview_result_id, uploadRevisionId: workspace.current_upload_revision_id,
    });
  }
  return rows;
}

export type WorkbenchActionId = "original-backup" | "current-archive" | "upload" | "view-diff" | "join-compare" | "remove-compare" | "archive-mainline";

export interface WorkbenchAction {
  id: WorkbenchActionId;
  label: string;
  enabled: boolean;
  reason: string | null;
}

export function deriveWorkbenchActions(row: WorkspaceTreeRow | null, comparisonCount: number, isCompared: boolean): WorkbenchAction[] {
  if (!row) return [];
  const blocked = (id: WorkbenchActionId, label: string, reason: string): WorkbenchAction => ({ id, label, enabled: false, reason });
  const enabled = (id: WorkbenchActionId, label: string): WorkbenchAction => ({ id, label, enabled: true, reason: null });
  if (row.kind === "workspace") return [
    row.previewResultId ? enabled("original-backup", "原始组态备份") : blocked("original-backup", "原始组态备份", "当前工作区还没有 Preview 结果"),
    row.previewResultId ? enabled("current-archive", "本次归档组态") : blocked("current-archive", "本次归档组态", "当前工作区还没有 Preview 结果"),
    blocked("upload", "上传", "需先选择本次归档组态目录"),
  ];
  const compareAction = isCompared
    ? enabled("remove-compare", "移出比较")
    : comparisonCount >= 3
      ? blocked("join-compare", "加入比较", "比较托盘最多选择 3 个节点")
      : enabled("join-compare", "加入比较");
  if (row.kind === "baseline") return [compareAction];
  if (row.kind === "submission") {
    const reviewReady = row.reviewStatus === "PENDING";
    const archiveReady = row.reviewStatus === "APPROVED" && row.eligibilityNote == null;
    return [
      row.parentRef ? enabled("view-diff", "查看差异") : blocked("view-diff", "查看差异", "提交缺少基线节点"),
      compareAction,
      archiveReady
        ? blocked("archive-mainline", "归档主线", "归档主线操作在 FE2c 接入")
        : blocked("archive-mainline", "归档主线", row.eligibilityNote ? "该提交所基于的基线已不是当前基线，不能归档" : reviewReady ? "提交尚未审核通过" : "当前提交不符合归档条件"),
    ];
  }
  return [];
}

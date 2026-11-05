import type { components } from "../api/generated/openapi";

type Schemas = components["schemas"];
type HistoryNode = Schemas["HistoryNodeResponse"];
type HistoryList = Schemas["HistoryListResponse"];

/**
 * Submit-dialog summary labels (FE3a M7).
 *
 * The dialog summary must show the same display names as the workspace tree
 * instead of raw History IDs: baselines as "当前基线（归档基线 2）" /
 * "初始基线" / "归档基线 1", submissions as "提交 2", Preview results as
 * "本次预览". Callers fall back to the raw ID when a label is unavailable
 * and keep the raw ID in the hover title (C6).
 */

function nodeKey(node: Pick<HistoryNode, "ref_kind" | "ref_id">): string {
  return `${node.ref_kind}:${node.ref_id}`;
}

/** Submission label by creation order, same rule as the workspace tree. */
export function submissionDisplayName(
  history: Pick<HistoryList, "nodes">,
  refKind: HistoryNode["ref_kind"],
  refId: string,
): string | null {
  const ordered = history.nodes
    .filter((node) => node.node_kind === "SUBMISSION")
    .sort((left, right) => left.created_at.localeCompare(right.created_at));
  const index = ordered.findIndex(
    (node) => nodeKey(node) === `${refKind}:${refId}`,
  );
  return index === -1 ? null : `提交 ${index + 1}`;
}

/** Baseline label with the head marker, same rule as the workspace tree. */
export function baselineDisplayName(
  history: Pick<HistoryList, "head" | "nodes">,
  refId: string,
): string | null {
  const node = history.nodes.find(
    (item) => item.node_kind === "BASELINE_NODE" && item.ref_id === refId,
  );
  if (!node) return null;
  const kindLabel =
    node.baseline_kind === "INITIAL"
      ? "初始基线"
      : `归档基线 ${
        history.nodes
          .filter((item) => item.baseline_kind === "ARCHIVED_SUBMISSION")
          .sort((left, right) => left.created_at.localeCompare(right.created_at))
          .findIndex((item) => item.ref_id === refId) + 1
      }`;
  const isHead = node.ref_id === history.head.node_id;
  return isHead ? `当前基线（${kindLabel}）` : kindLabel;
}

export interface SubmitSummaryRow {
  term: string;
  display: string;
  raw: string | number;
}

/** Dialog summary rows for a Preview submission. */
export function describeSubmitSummary(
  preview: Pick<
    Schemas["PreviewResultResponse"],
    "workspace_id" | "preview_result_id" | "business_baseline_node_id" | "generation"
  >,
  history: Pick<HistoryList, "head" | "nodes"> | null,
): SubmitSummaryRow[] {
  const baselineLabel =
    (history ? baselineDisplayName(history, preview.business_baseline_node_id) : null) ??
    preview.business_baseline_node_id;
  return [
    { term: "工作区", display: preview.workspace_id, raw: preview.workspace_id },
    { term: "Preview", display: "本次预览", raw: preview.preview_result_id },
    {
      term: "业务基线",
      display: baselineLabel,
      raw: preview.business_baseline_node_id,
    },
    { term: "代次", display: String(preview.generation), raw: preview.generation },
  ];
}

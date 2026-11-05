import type { components } from "../api/generated/openapi";

type Schemas = components["schemas"];
type HistoryNode = Schemas["HistoryNodeResponse"];

/** Minimal History shape needed to order archived baselines. */
export type BaselineHistory = Pick<Schemas["HistoryListResponse"], "nodes">;

/**
 * FE3a Q11: baseline display labels are shared by the workspace tree and the
 * submit dialog. Archived baselines are numbered by creation time (ties by
 * ref_id); the INITIAL baseline never carries a number.
 */
export function baselineDisplayLabel(history: BaselineHistory, node: HistoryNode): string {
  if (node.baseline_kind === "INITIAL") return "初始基线";
  const archived = history.nodes
    .filter((item) => item.node_kind === "BASELINE_NODE" && item.baseline_kind === "ARCHIVED_SUBMISSION")
    .sort((left, right) => left.created_at.localeCompare(right.created_at) || left.ref_id.localeCompare(right.ref_id));
  const index = archived.findIndex((item) => item.ref_id === node.ref_id);
  return index === -1 ? "归档基线" : `归档基线 ${index + 1}`;
}

/** Label for a baseline ref, or null when the ref is not in the history page. */
export function baselineDisplayLabelFor(history: BaselineHistory, refId: string): string | null {
  const node = history.nodes.find(
    (item) => item.node_kind === "BASELINE_NODE" && item.ref_id === refId,
  );
  return node ? baselineDisplayLabel(history, node) : null;
}

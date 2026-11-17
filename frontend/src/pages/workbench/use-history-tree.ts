import { useEffect, useMemo, useState } from "react";
import {
  buildWorkspaceTree,
  sortWorkspaceTreeRows,
  type WorkspaceTreeRow,
} from "../../features/view-model/workspace";
import { refKey, type Schemas, type SortColumn } from "./workbench-helpers";

export function useHistoryTree(options: {
  workspace: Schemas["WorkspaceResponse"] | null;
  history: Schemas["HistoryListResponse"] | null;
  compareRefs: Schemas["HistoryCompareNodeRequest"][];
  selectedKey: string;
  setSelectedKey: (value: string | ((current: string) => string)) => void;
}) {
  const { workspace, history, compareRefs, selectedKey, setSelectedKey } = options;
  const [filter, setFilter] = useState("");
  const [currentBaselineOnly, setCurrentBaselineOnly] = useState(false);
  const [sort, setSort] = useState<{ column: SortColumn; direction: 1 | -1 } | null>(null);
  const [collapsedNodes, setCollapsedNodes] = useState<Set<string>>(() => new Set());

  const rows = useMemo(
    () => (workspace && history ? buildWorkspaceTree(workspace, history, compareRefs) : []),
    [workspace, history, compareRefs],
  );
  useEffect(() => {
    if (!rows.length) return;
    const queryNode = new URLSearchParams(window.location.search).get("workbenchNode");
    const found =
      queryNode && rows.some((row) => row.key === queryNode)
        ? queryNode
        : (rows.find((row) => row.kind === "workspace")?.key ?? rows[0]?.key);
    setSelectedKey((current) =>
      current && rows.some((row) => row.key === current) ? current : (found ?? ""),
    );
  }, [rows]);
  useEffect(() => {
    if (!selectedKey || !rows.some((row) => row.key === selectedKey)) return;
    const url = new URL(window.location.href);
    if (url.searchParams.get("workbenchNode") === selectedKey) return;
    url.searchParams.set("workbenchNode", selectedKey);
    window.history.replaceState(null, "", url);
  }, [rows, selectedKey]);

  const rowByKey = useMemo(() => new Map(rows.map((row) => [row.key, row])), [rows]);
  const nodeLabel = (ref: Schemas["HistoryCompareNodeRequest"]) =>
    rowByKey.get(refKey(ref))?.label ?? ref.ref_id;
  const selected = rowByKey.get(selectedKey) ?? null;
  const comparedKeys = useMemo(() => new Set(compareRefs.map(refKey)), [compareRefs]);

  const visibleRows = useMemo(() => {
    const query = filter.trim().toLocaleLowerCase();
    const rowMap = new Map(rows.map((row) => [row.key, row]));
    // "Current baseline only" keeps the head baseline's whole branch (its
    // workspace and submissions), not just the head row.
    const underHead = (row: WorkspaceTreeRow): boolean => {
      for (
        let current: WorkspaceTreeRow | undefined = row;
        current;
        current = current.parentKey ? rowMap.get(current.parentKey) : undefined
      ) {
        if (current.isHead) return true;
      }
      return false;
    };
    const matches = new Set(
      rows
        .filter(
          (row) =>
            (!currentBaselineOnly || underHead(row) || row.kind === "workspace") &&
            (!query ||
              `${row.label} ${row.status} ${row.refId ?? ""}`.toLocaleLowerCase().includes(query)),
        )
        .map((row) => row.key),
    );
    if (query)
      for (const key of [...matches]) {
        let parent = rowMap.get(key)?.parentKey ?? null;
        while (parent) {
          matches.add(parent);
          parent = rowMap.get(parent)?.parentKey ?? null;
        }
      }
    const filtered = rows.filter((row) => matches.has(row.key));
    return sortWorkspaceTreeRows(filtered, sort).filter((row) => {
      let parent = row.parentKey;
      while (parent) {
        if (collapsedNodes.has(parent)) return false;
        parent = rowMap.get(parent)?.parentKey ?? null;
      }
      return true;
    });
  }, [rows, filter, currentBaselineOnly, sort, collapsedNodes]);

  const sortBy = (column: SortColumn) =>
    setSort((state) =>
      state?.column === column
        ? { column, direction: state.direction === 1 ? -1 : 1 }
        : { column, direction: 1 },
    );
  const toggleCollapse = (key: string) =>
    setCollapsedNodes((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return {
    filter,
    setFilter,
    currentBaselineOnly,
    setCurrentBaselineOnly,
    sort,
    collapsedNodes,
    rows,
    rowByKey,
    nodeLabel,
    selected,
    comparedKeys,
    visibleRows,
    sortBy,
    toggleCollapse,
  };
}

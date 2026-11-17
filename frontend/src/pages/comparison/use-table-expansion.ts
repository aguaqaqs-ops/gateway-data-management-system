import { useEffect, useState } from "react";

export function useTableExpansion(
  selectedNodeKey: string,
  tabKey: string | undefined,
  tableName: string | undefined,
) {
  const [expandedRuns, setExpandedRuns] = useState<Set<string>>(new Set());

  // Opened unchanged runs belong to one tab; run keys repeat across tables.
  useEffect(() => {
    setExpandedRuns((old) => (old.size ? new Set() : old));
  }, [selectedNodeKey, tabKey, tableName]);

  const toggleRun = (key: string) =>
    setExpandedRuns((old) => {
      const next = new Set(old);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return { expandedRuns, toggleRun };
}

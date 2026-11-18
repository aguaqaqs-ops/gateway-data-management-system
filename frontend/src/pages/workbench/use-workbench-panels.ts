import { useState } from "react";

export function useWorkbenchPanels() {
  const [selectedKey, setSelectedKey] = useState("");
  // The panel carries the node actions, so it starts open on normal widths.
  const [detailExpanded, setDetailExpanded] = useState(() => window.innerWidth > 1100);
  const [notice, setNotice] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("notice"),
  );
  const [archiveSubmissionId, setArchiveSubmissionId] = useState<string | null>(null);
  return {
    selectedKey,
    setSelectedKey,
    detailExpanded,
    setDetailExpanded,
    notice,
    setNotice,
    archiveSubmissionId,
    setArchiveSubmissionId,
  };
}

import { useEffect } from "react";

export function useTabStripScroll(selectedNodeKey: string, tabKey: string | null) {
  useEffect(() => {
    document
      .querySelector(".overflow-tabs button.is-active")
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [selectedNodeKey, tabKey]);
}

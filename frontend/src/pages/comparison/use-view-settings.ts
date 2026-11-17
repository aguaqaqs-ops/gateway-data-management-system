import { useEffect, useRef, useState } from "react";
import {
  clampSidebar,
  COLUMN_WIDTHS_KEY,
  DEFAULT_SETTINGS,
  readColumnWidths,
  readSettings,
  SETTINGS_KEY,
  type ColumnWidths,
  type Settings,
} from "./sidebar-settings";

export function useViewSettings() {
  const [settings, setSettings] = useState<Settings>(readSettings);
  const [columnWidths, setColumnWidths] = useState<ColumnWidths>(readColumnWidths);
  const workspaceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch {
      /* defaults remain in memory */
    }
  }, [settings]);

  useEffect(() => {
    try {
      window.localStorage.setItem(COLUMN_WIDTHS_KEY, JSON.stringify(columnWidths));
    } catch {
      /* widths remain in memory */
    }
  }, [columnWidths]);

  // Double-clicking the sidebar edge fits the longest visible name; doing it
  // again at that width goes back to the default.
  const fitSidebarWidth = () => {
    const sidebar = workspaceRef.current?.querySelector<HTMLElement>(".navigation-sidebar");
    if (!sidebar) return;
    let needed = 0;
    for (const button of sidebar.querySelectorAll<HTMLElement>(
      ".nav-item__button, .nav-group__heading",
    )) {
      const label = button.querySelector<HTMLElement>(".nav-item__label, .nav-group__label");
      if (!label) continue;
      needed = Math.max(needed, sidebar.clientWidth - label.clientWidth + label.scrollWidth);
    }
    const fitted = clampSidebar(Math.ceil(needed) + 4);
    setSettings((state) => ({
      ...state,
      sidebarWidth:
        Math.abs(state.sidebarWidth - fitted) <= 2 ? DEFAULT_SETTINGS.sidebarWidth : fitted,
    }));
  };
  const updateSidebarWidth = (clientX: number) => {
    const left = workspaceRef.current?.getBoundingClientRect().left ?? 0;
    setSettings((state) => ({ ...state, sidebarWidth: clampSidebar(clientX - left) }));
  };

  return {
    settings,
    setSettings,
    columnWidths,
    setColumnWidths,
    workspaceRef,
    fitSidebarWidth,
    updateSidebarWidth,
  };
}

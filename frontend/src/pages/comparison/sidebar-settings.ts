import type { DeletionLayout } from "../../features/view-model/table-rows";

export type Settings = {
  sidebarWidth: number;
  sidebarCollapsed: boolean;
  collapsedGroups: string[];
  deletionLayout: DeletionLayout;
};

export const SETTINGS_KEY = "gateway-comparison-sidebar-v2";
export const SIDEBAR_MIN = 180;
export const SIDEBAR_MAX = 520;
export const DEFAULT_SETTINGS: Settings = {
  sidebarWidth: 220,
  sidebarCollapsed: false,
  collapsedGroups: [],
  deletionLayout: "interleave",
};
export const clampSidebar = (width: number) => Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, width));

export function readSettings(): Settings {
  try {
    const value = JSON.parse(
      window.localStorage.getItem(SETTINGS_KEY) ?? "null",
    ) as Partial<Settings> | null;
    return {
      sidebarWidth:
        typeof value?.sidebarWidth === "number"
          ? clampSidebar(value.sidebarWidth)
          : DEFAULT_SETTINGS.sidebarWidth,
      sidebarCollapsed:
        typeof value?.sidebarCollapsed === "boolean" ? value.sidebarCollapsed : false,
      collapsedGroups: Array.isArray(value?.collapsedGroups)
        ? value.collapsedGroups.filter((item): item is string => typeof item === "string")
        : [],
      deletionLayout: value?.deletionLayout === "group" ? "group" : "interleave",
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export type ColumnWidths = Record<string, Record<string, number>>;
export const COLUMN_WIDTHS_KEY = "gateway-comparison-column-widths-v1";

/** Column widths the viewer set, per table name; a convenience that may be absent. */
export function readColumnWidths(): ColumnWidths {
  try {
    const value = JSON.parse(window.localStorage.getItem(COLUMN_WIDTHS_KEY) ?? "null") as unknown;
    if (!value || typeof value !== "object") return {};
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).flatMap(([table, widths]) => {
        if (!widths || typeof widths !== "object") return [];
        const clean = Object.fromEntries(
          Object.entries(widths as Record<string, unknown>).filter(
            (entry): entry is [string, number] =>
              typeof entry[1] === "number" && Number.isFinite(entry[1]),
          ),
        );
        return [[table, clean]];
      }),
    );
  } catch {
    return {};
  }
}

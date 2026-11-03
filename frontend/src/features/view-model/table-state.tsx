import { AlertTriangle } from "lucide-react";
import type { DerivedTable } from "./model";

export type SurfaceChangeKind = "UNCHANGED" | "BUSINESS_EQUIVALENT" | "ADDED" | "DELETED" | "UPDATED" | "SCHEMA_CHANGED" | "DEGRADED" | "FAILED" | "REPLACED";
export interface SurfaceChangePresentation {
  text: string;
  badgeText: string | null;
  badgeKind: "ADDED" | "DELETED" | "UPDATED" | "FAILED" | "REPLACED" | null;
  tooltip: string | null;
  deleted: boolean;
}

export const SURFACE_CHANGE_PRESENTATION: Readonly<Record<SurfaceChangeKind, SurfaceChangePresentation>> = {
  UNCHANGED: { text: "未变化", badgeText: null, badgeKind: null, tooltip: null, deleted: false },
  BUSINESS_EQUIVALENT: { text: "业务等价", badgeText: null, badgeKind: null, tooltip: "内容写法不同，业务含义相同", deleted: false },
  ADDED: { text: "新增表", badgeText: "新增", badgeKind: "ADDED", tooltip: null, deleted: false },
  DELETED: { text: "删除表", badgeText: "删除", badgeKind: "DELETED", tooltip: null, deleted: true },
  UPDATED: { text: "有修改", badgeText: "更新", badgeKind: "UPDATED", tooltip: null, deleted: false },
  SCHEMA_CHANGED: { text: "结构变化", badgeText: "更新", badgeKind: "UPDATED", tooltip: null, deleted: false },
  DEGRADED: { text: "降级比较", badgeText: "更新", badgeKind: "UPDATED", tooltip: null, deleted: false },
  FAILED: { text: "比较失败", badgeText: "失败", badgeKind: "FAILED", tooltip: null, deleted: false },
  REPLACED: { text: "数据集替换", badgeText: "替换", badgeKind: "REPLACED", tooltip: null, deleted: false },
};

export function surfaceChangePresentation(kind: string): SurfaceChangePresentation {
  return SURFACE_CHANGE_PRESENTATION[kind as SurfaceChangeKind] ?? SURFACE_CHANGE_PRESENTATION.UNCHANGED;
}

export function tableStatusText(table: Pick<DerivedTable, "changeKind">): string {
  return surfaceChangePresentation(table.changeKind).text;
}

export function SurfaceChangeBadge({ kind }: { kind: string }) {
  const presentation = surfaceChangePresentation(kind);
  if (!presentation.badgeText) return null;
  const title = presentation.tooltip ?? presentation.text;
  return <span className={`surface-change-badge surface-change-badge--${presentation.badgeKind?.toLowerCase() ?? "neutral"}`} title={title}>
    {presentation.badgeKind === "FAILED" && <AlertTriangle size={12} aria-hidden="true" />}{presentation.badgeText}
  </span>;
}

export function TableFailureNotice({ table }: { table: Pick<DerivedTable, "changeKind"> }) {
  if (table.changeKind !== "FAILED") return null;
  return <div className="table-failed" role="alert"><AlertTriangle size={20} /><strong>比较失败</strong><span>该表没有可显示的比较结果。</span></div>;
}

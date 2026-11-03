export interface ViewStatusPresentation {
  text: "一致" | "更新";
  tooltipItems: string[];
}

function positiveCount(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return 0;
  return Math.floor(value);
}

export function presentViewStatus(view: Record<string, unknown> | undefined, diagnosticTableCount: number): ViewStatusPresentation {
  const summary = view ?? {};
  const changed = positiveCount(summary.changed_table_count);
  const degraded = positiveCount(summary.degraded_table_count);
  const failed = positiveCount(summary.failed_table_count);
  const diagnostics = positiveCount(diagnosticTableCount);
  const tooltipItems = [
    degraded > 0 ? degraded + " 张表降级比较" : null,
    failed > 0 ? failed + " 张表比较失败" : null,
    diagnostics > 0 ? diagnostics + " 张表有比较提示" : null,
  ].filter((item): item is string => item !== null);
  return { text: changed > 0 ? "更新" : "一致", tooltipItems };
}

export const RISK_REASON_CODES = [
  "PROJECT_IDENTITY_MISMATCH",
  "TABLE_ADDED",
  "TABLE_DELETED",
  "SCHEMA_CHANGED",
  "ROW_ADDED",
  "ROW_DELETED",
  "ROW_MODIFIED",
  "KEY_DEGRADED",
  "ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED",
  "COMPARISON_FAILED",
  "COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED",
  "UNKNOWN_CHANGE_TARGET",
] as const;

const RISK_REASON_COPY: Readonly<Record<(typeof RISK_REASON_CODES)[number], string>> = {
  PROJECT_IDENTITY_MISMATCH: "项目身份不同，可能是数据集替换，需要复核。",
  TABLE_ADDED: "新增了整张表。",
  TABLE_DELETED: "删除了整张表。",
  SCHEMA_CHANGED: "表结构发生变化。",
  ROW_ADDED: "新增了数据行。",
  ROW_DELETED: "删除了数据行。",
  ROW_MODIFIED: "修改了数据行。",
  KEY_DEGRADED: "比较键降级，建议复核。",
  ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED: "有序表差异无法可靠比较，建议复核。",
  COMPARISON_FAILED: "比较失败，结果需要复核。",
  COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED: "复合信号公式发生变化，需要复核。",
  UNKNOWN_CHANGE_TARGET: "变化目标无法识别，需要复核。",
};

export function describeRiskReason(code: string): string {
  return code in RISK_REASON_COPY
    ? RISK_REASON_COPY[code as (typeof RISK_REASON_CODES)[number]]
    : "风险原因待说明。";
}

export const RISK_REASON_CODES = [
  "PROJECT_IDENTITY_MISMATCH",
  "TABLE_ADDED",
  "TABLE_DELETED",
  "SCHEMA_CHANGED",
  "ROW_ADDED",
  "ROW_DELETED",
  "ROW_MODIFIED",
  "STANDARD_NAME_UPDATE",
  "ORDERED_MOVE",
  "ORDERED_REPLACEMENT",
  "ORDERED_MIDDLE_INSERT_DELETE",
  "ORDERED_TAIL_INSERT_DELETE",
  "ORDERED_NAME_UPDATE",
  "ORDERED_CONTENT_UPDATE",
  "ORDERED_RISK_UNKNOWN",
  "ORDERED_MIDDLE_BLANK_INTERVAL",
  "ORDERED_TAIL_BLANK_INTERVAL",
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
  // Also emitted without changed-column evidence (missing columns, COUNTS_ONLY): say no more than "a row changed".
  ROW_MODIFIED: "修改了数据行（未确认只涉及名称或描述，按普通修改评估）。",
  STANDARD_NAME_UPDATE: "只修改了名称或描述（name、description），属于低风险。",
  ORDERED_MOVE: "测点在有序表中换了位置，转发顺序随之改变，需要复核。",
  ORDERED_REPLACEMENT: "有序表同一位置的测点被替换。",
  ORDERED_MIDDLE_INSERT_DELETE: "在有序表中间新增或删除了测点，其后测点的序号整体偏移，需要复核。",
  ORDERED_TAIL_INSERT_DELETE: "在有序表末尾新增或删除了测点。",
  ORDERED_NAME_UPDATE: "只修改了测点的名称或描述（name、description），属于低风险。",
  ORDERED_CONTENT_UPDATE: "修改了测点名称、描述以外的内容。",
  ORDERED_RISK_UNKNOWN: "有序表的变化无法可靠判定风险，需要复核。",
  ORDERED_MIDDLE_BLANK_INTERVAL: "在有序表中间插入或删除了空点，其后测点的序号整体偏移，需要复核。",
  ORDERED_TAIL_BLANK_INTERVAL: "在有序表末尾插入或删除了空点。",
  KEY_DEGRADED: "比较键降级，建议复核。",
  ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED: "有序表差异无法可靠比较，建议复核。",
  COMPARISON_FAILED: "比较失败，结果需要复核。",
  COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED: "复合信号公式发生变化，需要复核。",
  UNKNOWN_CHANGE_TARGET: "变化目标无法识别，需要复核。",
};

/**
 * Blank-interval reasons carry the side (CURRENT = inserted, BEFORE = deleted)
 * and the net count as evidence. The interval is an affected region whose
 * positions are not each changed, so the copy states the net count only.
 */

function describeBlankInterval(code: string, evidence: ReadonlyArray<readonly [string, unknown]>): string | null {
  const value = (key: string) => evidence.find(([name]) => name === key)?.[1];
  const side = value("side");
  const count = value("count");
  if (side !== "CURRENT" && side !== "BEFORE") return null;
  const action = (side === "CURRENT" ? "净增 " : "净减 ") + (typeof count === "number" ? count + " 个" : "若干") + "空点";
  return code === "ORDERED_TAIL_BLANK_INTERVAL"
    ? "有序表末尾的空点区间" + action + "，其后没有保留的有效测点。"
    : "有序表中间的空点区间" + action + "，其后有效测点的序号随之偏移，需要复核。";
}

export function describeRiskReason(code: string, evidence: ReadonlyArray<readonly [string, unknown]> = []): string {
  if (code === "ORDERED_MIDDLE_BLANK_INTERVAL" || code === "ORDERED_TAIL_BLANK_INTERVAL") {
    const specific = describeBlankInterval(code, evidence);
    if (specific) return specific;
  }
  return code in RISK_REASON_COPY
    ? RISK_REASON_COPY[code as (typeof RISK_REASON_CODES)[number]]
    : "风险原因待说明。";
}

export function isKnownRiskReason(code: string): boolean {
  return code in RISK_REASON_COPY;
}

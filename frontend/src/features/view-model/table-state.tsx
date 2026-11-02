import { AlertTriangle } from "lucide-react";
import type { DerivedTable } from "./model";

export function tableStatusText(table: Pick<DerivedTable, "changeKind">): string {
  const copy: Record<string, string> = {
    UNCHANGED: "未变化",
    BUSINESS_EQUIVALENT: "业务等价",
    ADDED: "新增表",
    DELETED: "删除表",
    UPDATED: "有修改",
    MODIFIED: "有修改",
    SCHEMA_CHANGED: "结构变化",
    DEGRADED: "降级比较",
    FAILED: "比较失败",
    REPLACED: "数据集替换",
  };
  return copy[table.changeKind] ?? "比较过程有提示";
}

export function TableFailureNotice({ table }: { table: Pick<DerivedTable, "changeKind"> }) {
  if (table.changeKind !== "FAILED") return null;
  return <div className="table-failed" role="alert"><AlertTriangle size={20} /><strong>比较失败</strong><span>该表没有可显示的比较结果。</span></div>;
}

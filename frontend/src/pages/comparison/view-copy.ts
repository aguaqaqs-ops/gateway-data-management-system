import type { BrowseState } from "../../features/view-model/commands";
import { formatSurfaceDiagnostic } from "../../features/view-model/diagnostics";
import type {
  DeviceDefinitionChange,
  NavigationTableNotice,
  RiskLevel,
  TabScope,
} from "../../features/view-model/model";
import { describeRiskReason, isKnownRiskReason } from "../../features/view-model/risk-copy";
import { scopeChangeText as describeScopeChange } from "../../features/view-model/scope-copy";
import { blankIntervalLabel, rowMove, type BrowseRow } from "../../features/view-model/table-rows";
import { surfaceChangePresentation } from "../../features/view-model/table-state";
import type { PairPresentation } from "./view-helpers";

export function reviewStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    PENDING: "待审核",
    APPROVED: "已通过",
    REJECTED: "已退回",
    WITHDRAWN: "已撤回",
  };
  return labels[status] ?? "状态未知";
}

export function viewLabel(
  pair: PairPresentation,
  index: number,
  total: number,
  mode: BrowseState["mode"],
): string {
  if (mode === "REVIEW" && total === 1) return "基线 → 修改";
  if (mode === "HISTORY") return "节点 " + (index + 1) + " → 节点 " + (index + 2);
  if (total === 1) return "当前基线 → 本次归档组态";
  const id = pair.pair.pair_id.toLowerCase();
  if (id.includes("baseline_to_initial")) return "原始组态视图";
  if (id.includes("initial_to_modified")) return "本次组态视图";
  return "比较视图 " + (index + 1);
}

export function viewTitle(
  pair: PairPresentation,
  index: number,
  total: number,
  mode: BrowseState["mode"],
): string {
  if (mode === "REVIEW" && total === 1) return "提交绑定比较：基线 → 修改";
  if (mode === "HISTORY") return "节点 " + (index + 1) + " → 节点 " + (index + 2);
  if (total === 1) return "当前基线 → 本次归档组态";
  if (pair.pair.pair_id.toLowerCase().includes("baseline_to_initial"))
    return "已归档数据 → 原始组态备份";
  if (pair.pair.pair_id.toLowerCase().includes("initial_to_modified"))
    return "原始组态备份 → 本次归档组态";
  return "比较对 " + pair.pair.pair_id;
}

/** Reason codes in a public notice mix risk reasons and surface diagnostics; both have user copy. */
export function noticeReasonText(code: string): string {
  return isKnownRiskReason(code) ? describeRiskReason(code) : formatSurfaceDiagnostic(code).message;
}

/** One line per public fact of a shared table; never phrased as a device's own result. */
export function noticeLines(notice: NavigationTableNotice): string[] {
  const lines: string[] = [];
  if (notice.table_scope) {
    if (notice.initial_table_change) {
      if (notice.table_scope.risk_level)
        lines.push("整表风险：" + riskLevelText(notice.table_scope.risk_level));
    } else {
      lines.push(
        (notice.table_scope.change ? "整表发生表级变化" : "整表无表级变化") +
          (notice.table_scope.risk_level
            ? " · 整表风险：" + riskLevelText(notice.table_scope.risk_level)
            : ""),
      );
    }
  }
  const unlocated = notice.unlocated_row_risk;
  if (unlocated && (unlocated.risk_level !== null || unlocated.count !== null)) {
    lines.push(
      "待定位风险" +
        (unlocated.risk_level ? "：" + riskLevelText(unlocated.risk_level) : "") +
        (unlocated.count !== null ? " · " + unlocated.count + " 项" : "") +
        "（不能归属到具体装置）",
    );
  }
  if (!notice.risk_complete) lines.push("风险信息不完整：未生成标注不代表没有风险");
  return lines;
}

export function definitionChangeText(change: DeviceDefinitionChange): string {
  const verb =
    change.change_kind === "ADDED" ? "新增" : change.change_kind === "DELETED" ? "删除" : "修改";
  const address =
    change.before_dev_addr !== null &&
    change.current_dev_addr !== null &&
    change.before_dev_addr !== change.current_dev_addr
      ? `地址 ${change.before_dev_addr} → ${change.current_dev_addr}`
      : `地址 ${change.current_dev_addr ?? change.before_dev_addr ?? "未知"}`;
  return `${verb}装置定义 · ${address}`;
}

/** Local risk status text for a filtered tab: confirmed, none generated, or incomplete. */
export function localRiskText(scope: TabScope): string | null {
  if (scope.kind === "WHOLE_TABLE") return null;
  if (!scope.riskComplete)
    return scope.riskLevel ? "已确认风险之外，风险信息不完整" : "风险信息不完整";
  return scope.riskLevel ? null : "未生成风险标注";
}

export function itemBadgeKind(kinds: readonly string[]): string {
  return kinds.find((kind) => surfaceChangePresentation(kind).badgeText !== null) ?? "UNCHANGED";
}

export function itemStatusTooltip(kinds: readonly string[]): string {
  return [
    ...new Set(
      kinds
        .map((kind) => surfaceChangePresentation(kind).tooltip)
        .filter((tooltip): tooltip is string => Boolean(tooltip)),
    ),
  ].join(" · ");
}

export function riskLevelText(level: RiskLevel): string {
  return {
    HIGH: "高风险",
    MEDIUM_HIGH: "中高风险",
    MEDIUM_LOW: "中低风险",
    LOW: "低风险",
    UNKNOWN: "未知风险",
  }[level];
}

export const scopeChangeText = (scope: TabScope) =>
  describeScopeChange(scope, (kind) => surfaceChangePresentation(kind).text);

export function tabTitle(scope: TabScope): string {
  const change = scope.changeKind === null ? null : surfaceChangePresentation(scope.changeKind);
  return [
    scopeChangeText(scope),
    scope.kind === "WHOLE_TABLE" ? change?.tooltip : null,
    scope.riskLevel ? riskLevelText(scope.riskLevel) : null,
    !scope.membershipComplete && !scope.membershipInitialBaseline ? "归属变化未知" : null,
    localRiskText(scope),
    scope.notice ? "该表另有公共提示" : null,
    `${scope.beforeCount ?? "—"} → ${scope.currentCount ?? "—"} 行`,
  ]
    .filter((item): item is string => Boolean(item))
    .join(" · ");
}

export function rowLabel(row: BrowseRow): string {
  if (row.kind === "collapsed")
    return row.expanded
      ? "▴ 收起 " + (row.collapsedCount ?? 0) + " 行未变更"
      : "▾ " + (row.collapsedCount ?? 0) + " 行未变更 · 展开";
  if (row.kind === "blank-interval" && row.interval) return blankIntervalLabel(row.interval);
  if (row.kind === "added") return "+ 新增";
  if (row.kind === "deleted") return "− 删除";
  if (row.recordKind === "ORDERED_ROW_MOVED" || row.kind === "ordered")
    return "↕ 移动 · " + (row.beforePosition ?? "—") + " → " + (row.currentPosition ?? "—");
  // Leading space keeps room for the line drawn between a modified pair.
  if (row.kind === "modified-before" || row.kind === "modified-after") {
    const move = rowMove(row);
    return "\u2002\u2002修改" + (move ? " · ↕ " + move.from + " → " + move.to : "");
  }
  return "";
}

export function formatSchemaSummary(value: Record<string, unknown> | null | undefined): string {
  if (!value) return "表结构发生变化，请检查新增或删除的列。";
  const addedValues = value.current_only_columns ?? value.added_columns;
  const removedValues = value.before_only_columns ?? value.removed_columns;
  const added = Array.isArray(addedValues) ? addedValues.map(String) : [];
  const removed = Array.isArray(removedValues) ? removedValues.map(String) : [];
  const details = [
    added.length ? "新增列：" + added.join("、") : "",
    removed.length ? "删除列：" + removed.join("、") : "",
  ].filter(Boolean);
  return details.length
    ? "表结构发生变化。" + details.join("；")
    : "表结构发生变化，请检查新增或删除的列。";
}

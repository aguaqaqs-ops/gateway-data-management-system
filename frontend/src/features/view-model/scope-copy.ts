import type { DerivedNavigationGroup, TabScope } from "./model";

/**
 * How a scope's change is shown. Only real content additions/deletions use the
 * add/delete badges; rows that only moved between devices and registry-only
 * membership changes get neutral markers, never "新增"/"删除".
 */
export type ScopeChangeMark =
  | { kind: "unknown" }
  | { kind: "badge"; changeKind: string }
  | { kind: "marker"; text: "移入" | "移出" | "迁移" | "归属变化"; title: string };

export function scopeChangeMark(scope: TabScope): ScopeChangeMark {
  if (scope.changeKind === null) return { kind: "unknown" };
  if (scope.kind === "WHOLE_TABLE") return { kind: "badge", changeKind: scope.changeKind };
  const changes = scope.rowChanges;
  if (!changes) return { kind: "badge", changeKind: scope.changeKind };
  if (changes.added > 0 || changes.deleted > 0) return { kind: "badge", changeKind: scope.changeKind };
  const moved = changes.moved_in + changes.moved_out;
  if (changes.modified > moved) return { kind: "badge", changeKind: "UPDATED" };
  if (changes.moved_in > 0 && changes.moved_out === 0) return { kind: "marker", text: "移入", title: "测点从其他装置移入本装置，不是新建" };
  if (changes.moved_out > 0 && changes.moved_in === 0) return { kind: "marker", text: "移出", title: "测点移出本装置，未被删除" };
  if (moved > 0) return { kind: "marker", text: "迁移", title: "测点在装置之间迁移，不是新建或删除" };
  if (scope.membershipChanged) return { kind: "marker", text: "归属变化", title: "测点内容未变，注册归属变化，不是新建或删除" };
  return { kind: "badge", changeKind: "UNCHANGED" };
}

/** User wording for a scope's change: whole-table status, or local rows created/removed vs moved between devices. */
export function scopeChangeText(scope: TabScope, wholeTableText: (changeKind: string) => string): string {
  if (scope.changeKind === null) return "变化未知";
  if (scope.kind === "WHOLE_TABLE") return wholeTableText(scope.changeKind);
  const changes = scope.rowChanges;
  const parts: string[] = [];
  if (changes) {
    if (changes.added) parts.push(`新建 ${changes.added} 行`);
    if (changes.deleted) parts.push(`删除 ${changes.deleted} 行`);
    if (changes.moved_in) parts.push(`移入本装置 ${changes.moved_in} 行`);
    if (changes.moved_out) parts.push(`移出本装置 ${changes.moved_out} 行`);
    const plainModified = changes.modified - changes.moved_in - changes.moved_out;
    if (plainModified > 0) parts.push(`修改 ${plainModified} 行`);
  }
  if (scope.membershipChanged) parts.push("注册归属变化");
  return parts.length ? parts.join("、") : "未变化";
}

type NavItem = DerivedNavigationGroup["items"][number];

/**
 * Item badge: the backend summary kinds, unless every nonempty device tab
 * changed only by migration or registry membership, which is not a creation
 * or deletion of the device's rows.
 */
export function itemChangeMark(item: NavItem, scopes: readonly TabScope[]): ScopeChangeMark | null {
  const local = scopes.filter((scope) => scope.kind !== "WHOLE_TABLE");
  if (local.length === 0 || local.length !== scopes.length) return null;
  const marks = local.map(scopeChangeMark);
  if (marks.some((mark) => mark.kind !== "marker" && !(mark.kind === "badge" && mark.changeKind === "UNCHANGED"))) return null;
  const markers = marks.filter((mark): mark is Extract<ScopeChangeMark, { kind: "marker" }> => mark.kind === "marker");
  if (markers.length === 0 || item.changeKinds.length === 0) return null;
  const texts = new Set(markers.map((mark) => mark.text));
  return texts.size === 1 ? markers[0]! : { kind: "marker", text: "迁移", title: "测点在装置之间迁移或注册归属变化，不是新建或删除" };
}

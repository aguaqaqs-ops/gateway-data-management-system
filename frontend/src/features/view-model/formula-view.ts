import type { FormulaSourceRow } from "./model";

export interface FormulaLine {
  key: string;
  alignmentKey: string;
  comparisonText: string;
  text: string;
  kind: "expression" | "group";
  depth: number;
}

export interface AlignedFormulaLine {
  before: FormulaLine | null;
  current: FormulaLine | null;
  state: "same" | "changed" | "before-only" | "current-only";
}

type FormulaNode = { kind?: unknown; operator?: unknown; name?: unknown; value?: unknown; children?: unknown };

function parse(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try { return JSON.parse(value) as unknown; } catch { return null; }
}

function pointLabel(value: unknown, devices: readonly FormulaSourceRow[]): string {
  if (typeof value !== "string") return "未知测点";
  const match = /^Device ([0-9]+):(.*)$/.exec(value);
  if (!match) return value;
  const address = match[1];
  const pointName = match[2] ?? "";
  const mapped = devices.filter((device) => String(device.dev_addr ?? "") === address
    && typeof device.description === "string" && device.description.trim().length > 0);
  return mapped.length === 1 ? `${mapped[0]?.description}:${pointName}` : value;
}

function flattenChildren(children: unknown[], operator: string): unknown[] {
  return children.flatMap((child) => {
    if (!child || typeof child !== "object" || Array.isArray(child)) return [child];
    const node = child as FormulaNode;
    if (node.kind === "EXPRESS" && node.operator === operator && !node.name && Array.isArray(node.children)) {
      return flattenChildren(node.children, operator);
    }
    return [child];
  });
}

export function renderFormulaLines(value: unknown, devices: readonly FormulaSourceRow[] = []): FormulaLine[] {
  const root = parse(value);
  const lines: FormulaLine[] = [];
  const occurrences = new Map<string, number>();
  const append = (kind: FormulaLine["kind"], comparisonText: string, text: string, depth: number) => {
    const occurrenceBase = `${kind}\0${comparisonText}`;
    const occurrence = occurrences.get(occurrenceBase) ?? 0;
    occurrences.set(occurrenceBase, occurrence + 1);
    const alignmentKey = `${occurrenceBase}\0${occurrence}`;
    lines.push({ key: alignmentKey, alignmentKey, comparisonText, text, kind, depth });
  };

  const visit = (raw: unknown, depth: number, prefix = "", parentOperator = "", showNameGroup = false): void => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      const text = raw == null ? "" : String(raw);
      append("expression", prefix + text, prefix + text, depth);
      return;
    }

    const node = raw as FormulaNode;
    if (node.kind === "POINT") {
      const original = typeof node.name === "string" ? node.name : "未知测点";
      append("expression", prefix + original, prefix + pointLabel(node.name, devices), depth);
      return;
    }
    if (node.kind === "DIGITAL") {
      const valueText = node.value === undefined ? "" : String(node.value);
      append("expression", prefix + valueText, prefix + valueText, depth);
      return;
    }
    if (node.kind !== "EXPRESS" || !Array.isArray(node.children) || typeof node.operator !== "string") {
      append("expression", prefix + "公式结构暂不支持", prefix + "公式结构暂不支持", depth);
      return;
    }

    if (showNameGroup && typeof node.name === "string" && node.name) {
      const groupText = `${prefix}${parentOperator ? parentOperator + " " : ""}${node.name} =`;
      append("group", groupText, groupText, depth);
      visitChildren(node.children, node.operator, depth + 1);
      return;
    }
    if (!node.operator && node.children.length === 1) {
      visit(node.children[0], depth, prefix, parentOperator);
      return;
    }
    if (node.children.length === 1) {
      const unaryPrefix = `${prefix}${node.operator} `;
      visit(node.children[0], depth, unaryPrefix, node.operator);
      return;
    }
    if (!node.name && parentOperator && node.operator !== parentOperator) {
      const groupPrefix = prefix || parentOperator + " ";
      const groupText = groupPrefix + "（" + node.operator + " 分组）";
      append("group", groupText, groupText, depth);
      visitChildren(node.children, node.operator, depth + 1, node.operator + " ");
      return;
    }
    const operationPrefix = parentOperator && parentOperator !== node.operator ? `${node.operator} ` : prefix;
    visitChildren(node.children, node.operator, depth, operationPrefix);
  };

  const visitChildren = (children: unknown[], operator: string, depth: number, leadingPrefix = ""): void => {
    if (!operator && children.length === 1) {
      visit(children[0], depth, leadingPrefix, operator);
      return;
    }
    const terms = ["|", "+", "*"].includes(operator) ? flattenChildren(children, operator) : children;
    terms.forEach((child, index) => {
      const childIsNamedExpression = Boolean(child && typeof child === "object" && !Array.isArray(child)
        && (child as FormulaNode).kind === "EXPRESS" && typeof (child as FormulaNode).name === "string" && (child as FormulaNode).name);
      if (childIsNamedExpression) {
        visit(child, depth, index === 0 ? leadingPrefix : "", operator, true);
        return;
      }
      const prefix = index === 0 ? leadingPrefix : `${operator ? operator + " " : ""}`;
      visit(child, depth, prefix, operator);
    });
  };

  visit(root, 0);
  return lines;
}

function lcsAnchors(before: FormulaLine[], current: FormulaLine[]): Array<[number, number]> {
  const rows = before.length + 1;
  const columns = current.length + 1;
  const table = Array.from({ length: rows }, () => new Uint32Array(columns));
  for (let i = before.length - 1; i >= 0; i -= 1) {
    for (let j = current.length - 1; j >= 0; j -= 1) {
      table[i]![j] = before[i]?.alignmentKey === current[j]?.alignmentKey
        ? (table[i + 1]?.[j + 1] ?? 0) + 1
        : Math.max(table[i + 1]?.[j] ?? 0, table[i]?.[j + 1] ?? 0);
    }
  }
  const anchors: Array<[number, number]> = [];
  let i = 0;
  let j = 0;
  while (i < before.length && j < current.length) {
    if (before[i]?.alignmentKey === current[j]?.alignmentKey) { anchors.push([i, j]); i += 1; j += 1; }
    else if ((table[i + 1]?.[j] ?? 0) >= (table[i]?.[j + 1] ?? 0)) i += 1;
    else j += 1;
  }
  return anchors;
}

export function alignFormulaLines(before: FormulaLine[], current: FormulaLine[]): AlignedFormulaLine[] {
  const anchors = lcsAnchors(before, current);
  const result: AlignedFormulaLine[] = [];
  let beforeAt = 0;
  let currentAt = 0;
  const appendGap = (beforeEnd: number, currentEnd: number) => {
    const beforeGap = before.slice(beforeAt, beforeEnd);
    const currentGap = current.slice(currentAt, currentEnd);
    const length = Math.max(beforeGap.length, currentGap.length);
    for (let i = 0; i < length; i += 1) {
      const oldLine = beforeGap[i] ?? null;
      const newLine = currentGap[i] ?? null;
      result.push({ before: oldLine, current: newLine, state: oldLine && newLine ? "changed" : oldLine ? "before-only" : "current-only" });
    }
  };
  for (const [beforeIndex, currentIndex] of anchors) {
    appendGap(beforeIndex, currentIndex);
    result.push({ before: before[beforeIndex] ?? null, current: current[currentIndex] ?? null, state: "same" });
    beforeAt = beforeIndex + 1;
    currentAt = currentIndex + 1;
  }
  appendGap(before.length, current.length);
  return result;
}

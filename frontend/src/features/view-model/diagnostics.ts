import type { SurfaceTable } from "./model";

export type DiagnosticSide = "BEFORE" | "CURRENT" | null;

export interface NavigationDiagnostic {
  code: string;
  target: {
    group_key: string | null;
    item_key: string | null;
    tab_key: string | null;
    table_id: string | null;
  };
  side: DiagnosticSide;
  params: Record<string, string | number | null | string[]>;
}

export interface NavigationDiagnosticsDocument {
  contract_version: "backend-vnext/business-navigation/v1";
  diagnostics: NavigationDiagnostic[];
}

const NAVIGATION_COPY: Readonly<Record<string, { template: string; params: readonly string[] }>> = {
  DEVICE_ADDRESS_DUPLICATE: { template: "{side}装置总表中装置地址 {dev_addr} 重复", params: ["dev_addr"] },
  DEVICE_GID_DUPLICATE: { template: "{side}装置总表中 gid {gid} 重复，按 gid 筛选的页签可能不准确", params: ["gid"] },
  DEVICE_TAB_COUNT_UNKNOWN: { template: "{side}{table}无法按 {identity_column} 统计行数，装置页签已保留，内容可能为空", params: ["identity_column"] },
  DEVICE_ROWS_UNASSIGNED: { template: "{side}{table}有 {row_count} 行的 {identity_column} 不属于任何装置（其中 {changed_row_count} 行有变化），可查看整表", params: ["identity_column", "row_count", "changed_row_count"] },
  CHANNEL_TABLE_UNCLAIMED: { template: "{table}按名称属于通道 b{board}_n{link_no}，但网口配置表中没有该通道，或该通道不满足转发通道条件（规约为 IEC104 且 tab_num 大于 0），已放入“其他表”", params: ["board", "link_no"] },
  PROTOCOL_EXE_MISSING: { template: "{side}通道 b{board}_n{link_no} 未配置规约，无法确定规约表", params: ["board", "link_no"] },
  PROTOCOL_TABLE_NOT_FOUND: { template: "{side}通道 b{board}_n{link_no} 的规约 {protocol} 没有对应的规约表（{expected_tables}）", params: ["board", "link_no", "protocol", "expected_tables"] },
  APP_TABLE_CFG_MISSING: { template: "{side}全局参数 {app_name} 未指定参数表", params: ["app_name"] },
  APP_TABLE_CFG_DUPLICATE: { template: "{side}全局参数 {app_name} 指向的参数表 {table_cfg} 已被其他行使用，只显示一次", params: ["app_name", "table_cfg"] },
  APP_TABLE_NOT_FOUND: { template: "{side}全局参数 {app_name} 指向的参数表 {table_cfg} 不存在", params: ["app_name", "table_cfg"] },
};

export const NAVIGATION_DIAGNOSTIC_CODES = Object.keys(NAVIGATION_COPY);

const SURFACE_COPY: Readonly<Record<string, string>> = {
  KEYLESS_FALLBACK: "缺少可用主键，已按规则回退为逐行比较。",
  ORDERED_DIFF_UNSUPPORTED: "该有序表无法生成可靠差异，建议打开整表核对。",
  DATASET_REPLACEMENT: "识别为不同数据集，已切换为双侧浏览。",
  PROJECT_IDENTITY_UNVERIFIABLE: "项目身份无法验证，提交前需要人工确认。",
  BUSINESS_SCHEMA_CHANGED: "表结构发生业务变化，请检查新增或删除的列。",
};

export const SURFACE_DIAGNOSTIC_CODES = Object.keys(SURFACE_COPY);

function displayParam(value: NavigationDiagnostic["params"][string]): string {
  if (Array.isArray(value)) return value.join("、");
  if (value === null) return "未指定";
  return String(value);
}

export function formatNavigationDiagnostic(
  diagnostic: NavigationDiagnostic,
  tables: readonly SurfaceTable[],
): string {
  const definition = NAVIGATION_COPY[diagnostic.code];
  if (!definition) return `导航提示（${diagnostic.code}）`;
  const params = Object.fromEntries(definition.params.map((key) => [key, displayParam(diagnostic.params[key] ?? null)]));
  const tableName = diagnostic.target.table_id
    ? tables.find((table) => table.table_id === diagnostic.target.table_id || table.table_name === diagnostic.target.table_id)?.display_name
    : undefined;
  const side = diagnostic.side === "BEFORE" ? "改前侧" : diagnostic.side === "CURRENT" ? "改后侧" : "";
  return definition.template
    .replaceAll("{side}", side)
    .replaceAll("{table}", tableName ?? diagnostic.target.table_id ?? "该表")
    .replace(/\{([a-z_]+)\}/g, (_match, key: string) => params[key] ?? "未指定");
}

export function formatSurfaceDiagnostic(value: string): { message: string; raw: string } {
  return { message: SURFACE_COPY[value] ?? "比较过程有提示", raw: value };
}

export function navigationDiagnosticParamKeys(code: string): readonly string[] | null {
  return NAVIGATION_COPY[code]?.params ?? null;
}

export function navigationDiagnosticTemplateParamKeys(code: string): readonly string[] | null {
  const template = NAVIGATION_COPY[code]?.template;
  if (!template) return null;
  return [...template.matchAll(/\{([a-z_]+)\}/g)]
    .map((match) => match[1])
    .filter((key): key is string => key !== undefined && key !== "side" && key !== "table");
}

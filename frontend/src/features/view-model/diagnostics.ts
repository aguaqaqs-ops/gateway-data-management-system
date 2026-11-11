import type { ComparisonSurface, SurfaceTable } from "./model";

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

const REASON_COPY: Readonly<Record<string, string>> = {
  RECORDS_UNAVAILABLE: "变更记录不完整",
  RISK_ATTRIBUTION_UNAVAILABLE: "风险无法归属到行",
  TABLE_DEGRADED: "该表比较已降级",
  INTEGER_OUT_OF_RANGE: "数值超出可精确处理的范围",
  UNSUPPORTED_TYPE: "列类型不支持筛选",
  IDENTITY_EXCLUDED: "该列未参与比较",
};

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
  DEVICE_TAB_FACTS_UNAVAILABLE: { template: "{table}的装置页签无法确定逐行的变化与风险（{reason}），页签按整表提示", params: ["identity_column", "reason"] },
  DEVICE_FILTER_VALUE_UNSUPPORTED: { template: "{side}{table}的 {identity_column} 无法用于按装置筛选（{reason}），已改为整表显示", params: ["identity_column", "reason"] },
};

export const NAVIGATION_DIAGNOSTIC_CODES = Object.keys(NAVIGATION_COPY);

const SURFACE_COPY: Readonly<Record<string, string>> = {
  DEGRADE_NO_COMPARE_KEY: "本表没有可用的比较键",
  EFFECTIVE_KEY_CHANGED: "两侧的比较键不同",
  DUPLICATE_EFFECTIVE_KEY: "比较键有重复值",
  EFFECTIVE_KEY_IGNORED: "比较键中有列被比较规则忽略",
  SOURCE_PRIMARY_KEY_CHANGED: "两侧的源表主键定义不同",
  ORDERED_REQUIRED_COLUMN_MISSING: "有序表缺少排序或行标识所需的列",
  ROW_IDENTITY_MISSING: "有序表缺少行标识列",
  ROW_IDENTITY_DUPLICATE: "有序表的行标识有重复值",
  ORDERED_PROVENANCE_MISSING: "有序表缺少空行来源信息，或该信息无效",
  ORDERED_PROVENANCE_INVALID: "有序表缺少空行来源信息，或该信息无效",
  BLANK_PROVENANCE_INVALID: "有序表的 gid 或空行标记无效",
  ORDER_KEY_MISSING: "有序表的序号缺失、无效或重复",
  ORDER_KEY_INVALID: "有序表的序号缺失、无效或重复",
  ORDER_KEY_DUPLICATE: "有序表的序号缺失、无效或重复",
  ORDERED_INTEGER_INVALID: "有序表的序号缺失、无效或重复",
  SOURCE_GID_INVALID: "有序表的 gid 或空行标记无效",
  SOURCE_RESERVED_PSEUDO_GID: "有序表的 gid 或空行标记无效",
  CANONICAL_GID_INVALID: "有序表的 gid 或空行标记无效",
  BLANK_PROVENANCE_MISSING: "有序表的 gid 或空行标记无效",
  CANONICAL_BLANK_PROVENANCE_INVALID: "有序表的 gid 或空行标记无效",
  ORDERED_DIFF_UNSUPPORTED: "该有序表无法生成可靠差异，建议打开整表核对",
  BEFORE_ONLY_COLUMNS: "部分列只在改前侧存在，未参与行比较",
  CURRENT_ONLY_COLUMNS: "部分列只在改后侧存在，未参与行比较",
  INCOMPATIBLE_SELECTED_COLUMNS: "部分共有列两侧类型不兼容",
  NO_SELECTED_COLUMNS: "两侧没有可比较的共有列",
  BUSINESS_SCHEMA_CHANGED: "表结构有业务变化",
  KEYLESS_FALLBACK: "没有可用主键，已按整行内容比较（只识别新增与删除）",
  SET_VALUE_INVALID: "本表数据无法按列类型解析",
  SCALAR_VALUE_INVALID: "本表数据无法按列类型解析",
  SCALAR_TYPE_MISMATCH: "本表数据无法按列类型解析",
  SCALAR_TYPE_UNKNOWN: "本表数据无法按列类型解析",
  CANONICAL_COLUMN_COLLISION: "本表数据无法按列类型解析",
  ROW_SHAPE_MISMATCH: "本表数据无法按列类型解析",
  TABLE_READER_UNAVAILABLE: "比较时发生内部错误",
  TABLE_DESCRIPTOR_MISSING: "比较时发生内部错误",
  TABLE_TASK_INVALID: "比较时发生内部错误",
  TABLE_TASK_HAS_NO_SIDE: "比较时发生内部错误",
  TABLE_POLICY_MISSING: "比较时发生内部错误",
  METADATA_ROUTE_REQUIRES_NATIVE_ROWS: "比较时发生内部错误",
  METADATA_ROLE_REQUIRES_NATIVE_ROWS: "比较时发生内部错误",
  COMPARISON_INTERNAL_ERROR: "比较时发生内部错误",
  RISK_TABLE_BUDGET_EXCEEDED: "风险标注不完整（超出上限），请打开整表核对",
  RISK_DIAGNOSTICS_TRUNCATED: "风险标注不完整（超出上限），请打开整表核对",
  RISK_ANNOTATION_ARTIFACT_BUDGET_EXCEEDED: "风险标注不完整（超出上限），请打开整表核对",
  PROJECT_IDENTITY_UNVERIFIABLE: "项目身份无法验证，提交前需要人工确认",
  DATASET_REPLACEMENT: "识别为不同数据集，已切换为双侧浏览",
  RISK_ANNOTATION_LIMIT_EXCEEDED: "风险标注数量超出上限，部分行没有标注",
  COMPARISON_RULESET_DIGEST_MISSING: "比较未能完成（内部错误）",
};

export const SURFACE_DIAGNOSTIC_CODES = [
  "DEGRADE_NO_COMPARE_KEY",
  "EFFECTIVE_KEY_CHANGED",
  "DUPLICATE_EFFECTIVE_KEY",
  "EFFECTIVE_KEY_IGNORED",
  "SOURCE_PRIMARY_KEY_CHANGED",
  "ORDERED_REQUIRED_COLUMN_MISSING",
  "ROW_IDENTITY_MISSING",
  "ROW_IDENTITY_DUPLICATE",
  "ORDERED_PROVENANCE_MISSING",
  "ORDERED_PROVENANCE_INVALID",
  "BLANK_PROVENANCE_INVALID",
  "ORDER_KEY_MISSING",
  "ORDER_KEY_INVALID",
  "ORDER_KEY_DUPLICATE",
  "ORDERED_INTEGER_INVALID",
  "SOURCE_GID_INVALID",
  "SOURCE_RESERVED_PSEUDO_GID",
  "CANONICAL_GID_INVALID",
  "BLANK_PROVENANCE_MISSING",
  "CANONICAL_BLANK_PROVENANCE_INVALID",
  "ORDERED_DIFF_UNSUPPORTED",
  "BEFORE_ONLY_COLUMNS",
  "CURRENT_ONLY_COLUMNS",
  "INCOMPATIBLE_SELECTED_COLUMNS",
  "NO_SELECTED_COLUMNS",
  "BUSINESS_SCHEMA_CHANGED",
  "KEYLESS_FALLBACK",
  "SET_VALUE_INVALID",
  "SCALAR_VALUE_INVALID",
  "SCALAR_TYPE_MISMATCH",
  "SCALAR_TYPE_UNKNOWN",
  "CANONICAL_COLUMN_COLLISION",
  "ROW_SHAPE_MISMATCH",
  "TABLE_READER_UNAVAILABLE",
  "TABLE_DESCRIPTOR_MISSING",
  "TABLE_TASK_INVALID",
  "TABLE_TASK_HAS_NO_SIDE",
  "TABLE_POLICY_MISSING",
  "METADATA_ROUTE_REQUIRES_NATIVE_ROWS",
  "METADATA_ROLE_REQUIRES_NATIVE_ROWS",
  "COMPARISON_INTERNAL_ERROR",
  "RISK_TABLE_BUDGET_EXCEEDED",
  "RISK_DIAGNOSTICS_TRUNCATED",
  "RISK_ANNOTATION_ARTIFACT_BUDGET_EXCEEDED",
  "PROJECT_IDENTITY_UNVERIFIABLE",
  "DATASET_REPLACEMENT",
  "RISK_ANNOTATION_LIMIT_EXCEEDED",
  "COMPARISON_RULESET_DIGEST_MISSING",
] as const;

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
  const changedRowCount = diagnostic.params.changed_row_count ?? null;
  const template = diagnostic.code === "DEVICE_ROWS_UNASSIGNED" && changedRowCount === null
    ? "{side}{table}有 {row_count} 行的 {identity_column} 不属于任何装置（其中变化行数未知），可查看整表"
    : definition.template;
  const params = Object.fromEntries(definition.params.map((key) => [key, displayParam(diagnostic.params[key] ?? null)]));
  if (typeof diagnostic.params.reason === "string") {
    params.reason = REASON_COPY[diagnostic.params.reason] ?? "原因未提供";
  }
  const tableName = diagnostic.target.table_id
    ? tables.find((table) => table.table_id === diagnostic.target.table_id || table.table_name === diagnostic.target.table_id)?.display_name
    : undefined;
  const side = diagnostic.side === "BEFORE" ? "改前侧" : diagnostic.side === "CURRENT" ? "改后侧" : "";
  return template
    .replaceAll("{side}", side)
    .replaceAll("{table}", tableName ?? diagnostic.target.table_id ?? "该表")
    .replace(/\{([a-z_]+)\}/g, (_match, key: string) => params[key] ?? "未指定");
}

export function formatSurfaceDiagnostic(value: string): { message: string; raw: string } {
  const message = SURFACE_COPY[value] ?? "比较过程有提示";
  return { message, raw: value };
}

export function firstDegradedDiagnostic(codes: readonly string[]): string {
  const priority = new Map<string, number>(SURFACE_DIAGNOSTIC_CODES.map((code, index): [string, number] => [code, index]));
  const known = codes
    .filter((code) => SURFACE_COPY[code] !== undefined)
    .sort((left, right) => (priority.get(left) ?? Number.MAX_SAFE_INTEGER) - (priority.get(right) ?? Number.MAX_SAFE_INTEGER));
  return known[0] ? formatSurfaceDiagnostic(known[0]).message : "降级原因未提供";
}

export function pairSurfaceDiagnosticCodes(surface: ComparisonSurface): string[] {
  const view = surface.view && typeof surface.view === "object" ? surface.view as Record<string, unknown> : {};
  const summary = Array.isArray(view.diagnostics_summary) ? view.diagnostics_summary.filter((code): code is string => typeof code === "string") : [];
  const tableCodes = new Set(surface.tables.flatMap((table) => table.diagnostics?.diagnostics_summary ?? []));
  return [...new Set(summary.filter((code) => !tableCodes.has(code)))];
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

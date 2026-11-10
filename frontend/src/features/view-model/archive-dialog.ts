import type { components } from "../api/generated/openapi";

type Schemas = components["schemas"];
type Anomaly = Schemas["ArchivePreviewAnomalyResponse"];

/** Issue codes this frontend build can explain and accept (kickoff §16.3). */
export const KNOWN_ISSUE_CODES: ReadonlySet<string> = new Set([
  "INITIAL_SOURCE_UNEXPLAINED",
  "GENERATION_TIME_MISSING",
  "GENERATION_TIME_INVALID_VALUES",
  "GENERATION_TIME_LAST_NOT_MAX",
  "TIME_ABNORMAL_MODIFIED",
  "TIME_ABNORMAL_INITIAL",
  "BASELINE_TIME_UNAVAILABLE",
  "APPROVED_SIBLING_EXCLUDED",
  "PROJECT_IDENTITY_EXCEPTION",
]);

export const ISSUE_COPY: Readonly<Record<string, string>> = {
  INITIAL_SOURCE_UNEXPLAINED: "原始组态备份的来源无法解释",
  GENERATION_TIME_MISSING: "缺少组态生成时间",
  GENERATION_TIME_INVALID_VALUES: "生成时间中有无法识别的值",
  GENERATION_TIME_LAST_NOT_MAX: "最后一个生成时间不是最大值",
  TIME_ABNORMAL_MODIFIED: "本次归档组态的生成时间早于对照",
  TIME_ABNORMAL_INITIAL: "原始组态备份的生成时间早于当前基线",
  BASELINE_TIME_UNAVAILABLE: "当前基线没有可用的生成时间，本轮无法比较时间先后",
  APPROVED_SIBLING_EXCLUDED: "归档后该已通过的提交将被关闭（不归档）",
  PROJECT_IDENTITY_EXCEPTION: "选中的提交有项目身份例外",
};

export const SIDE_COPY: Readonly<Record<string, string>> = {
  INITIAL: "①原始组态备份",
  MODIFIED: "②本次归档组态",
  BASELINE: "当前基线",
};

export const RELATION_COPY: Readonly<Record<string, string>> = {
  MODIFIED_BEFORE_INITIAL: "②与①比较",
  MODIFIED_BEFORE_BASELINE: "②与当前基线比较",
  INITIAL_BEFORE_BASELINE: "①与当前基线比较",
};

export const COMPARISON_STATUS_COPY: Readonly<Record<string, string>> = {
  NORMAL: "正常",
  BACKWARD: "倒退",
  NOT_COMPARABLE: "无法比较",
  NOT_APPLICABLE: "不适用",
};

export const GENERATED_TIME_STATUS_COPY: Readonly<Record<string, string>> = {
  TABLE_ABSENT: "SQL 中没有 version_manager 表",
  COLUMN_ABSENT: "version_manager 表没有 saved_time 列",
  NO_ROWS: "version_manager 表没有数据行",
  NO_VALUE: "saved_time 全部为空",
  NO_VALID_VALUE: "saved_time 没有可识别的时间",
};

export interface GeneratedTimeFacts {
  status: string;
  empty_count?: number;
  invalid_count?: number;
}

/** §16.3 detail text shared by GENERATION_TIME_MISSING and BASELINE_TIME_UNAVAILABLE. */
export function generatedTimeStatusText(generated: GeneratedTimeFacts): string {
  if (generated.status === "NO_VALUE") return `saved_time 全部为空（${generated.empty_count ?? 0} 行）`;
  if (generated.status === "NO_VALID_VALUE") return `saved_time 没有可识别的时间（${generated.invalid_count ?? 0} 个无法识别）`;
  return GENERATED_TIME_STATUS_COPY[generated.status] ?? generated.status;
}

export const GROUP_DEFS: ReadonlyArray<{ key: string; title: string; kinds: ReadonlyArray<Anomaly["subject_kind"]> }> = [
  { key: "source", title: "原始组态来源", kinds: ["CONFIGURATION_SOURCE"] },
  { key: "time", title: "生成时间", kinds: ["CONFIGURATION_TIME_QUALITY"] },
  { key: "baseline-time", title: "基线时间", kinds: ["CONFIGURATION_TIME_QUALITY"] },
  { key: "order", title: "生成时间先后", kinds: ["CONFIGURATION_TIME_ORDER"] },
  { key: "sibling", title: "同级提交", kinds: ["APPROVED_SIBLING_EXCLUDED"] },
  { key: "identity", title: "项目身份", kinds: ["PROJECT_IDENTITY_EXCEPTION"] },
];

export function anomalyGroupKey(anomaly: Anomaly): string {
  if (anomaly.subject_kind === "CONFIGURATION_TIME_QUALITY" && anomaly.issue_code === "BASELINE_TIME_UNAVAILABLE") return "baseline-time";
  return GROUP_DEFS.find((group) => group.key !== "baseline-time" && group.kinds.includes(anomaly.subject_kind))?.key ?? "source";
}

export function utf8Length(text: string): number {
  return new TextEncoder().encode(text).length;
}

/** Server UTC instants are shown as entered, without local conversion. */
export function formatServerTimeUtc(value: string): string {
  return `${value.replace("T", " ").replace(/Z$/, "")} UTC`;
}

export function detectedStatusCopy(anomaly: Anomaly): string {
  if (anomaly.subject_kind === "CONFIGURATION_SOURCE") return "来源未解释";
  return "已发现";
}

export type StatusTone = "neutral" | "warning";

/** ACCEPTED is neutral, never the success tone (§16.3, V3). */
export function resolutionStatusCopy(status: Anomaly["resolution_status"]): string {
  if (status === "ACCEPTED") return "已接受";
  if (status === "REVOKED") return "已撤销接受，需要重新处理";
  return "未处理";
}

export function resolutionStatusTone(status: Anomaly["resolution_status"]): StatusTone {
  return status === "ACCEPTED" ? "neutral" : "warning";
}

export function statusTagClass(tone: StatusTone): string {
  return tone === "warning" ? "status-tag status-tag--warning" : "status-tag status-tag--neutral";
}

export type ReasonKind = "accept" | "revoke" | "close";

export function formatReasonLimitError(kind: ReasonKind, trimmed: string, bytes: number): string | undefined {
  if (trimmed.length === 0) return kind === "close" ? "请填写关闭理由" : kind === "accept" ? "请填写接受理由" : "请填写撤销理由";
  if (bytes > 4096) return "理由不能超过 4096 字节";
  return undefined;
}

export type AnomalyAction = Schemas["AppendArchiveAnomalyResolutionRequest"]["action"];

export function anomalyAction(anomaly: Anomaly): AnomalyAction {
  switch (anomaly.subject_kind) {
    case "APPROVED_SIBLING_EXCLUDED": return "ACKNOWLEDGE_EXCLUSION";
    case "PROJECT_IDENTITY_EXCEPTION": return "ACKNOWLEDGE_IDENTITY_EXCEPTION";
    case "CONFIGURATION_SOURCE": return "ACKNOWLEDGE_SOURCE_EXCEPTION";
    case "CONFIGURATION_TIME_QUALITY": return "ACKNOWLEDGE_TIME_QUALITY";
    case "CONFIGURATION_TIME_ORDER": return "ACKNOWLEDGE_TIME_ORDER";
    default: return assertNever(anomaly.subject_kind);
  }
}

function assertNever(value: never): never {
  throw new Error(`未知异常类型：${String(value)}`);
}

/** §16.5 blockers: known codes use the kickoff copy; anything else is generic. */
export function blockerCopy(code: string): { text: string; pendingReview: boolean } {
  if (code === "ARCHIVE_PENDING_REVIEW") return { text: "待审核的提交", pendingReview: true };
  if (code === "ACTIVE_SUBMIT_ATTEMPT") return { text: "已有提交正在处理，完成后才能归档", pendingReview: false };
  if (code === "ARCHIVE_INTEGRITY_FAILURE") return { text: "归档数据完整性校验未通过，不能继续，请联系管理员", pendingReview: false };
  return { text: "当前不能归档", pendingReview: false };
}

export interface StartDisabledInput {
  loading: boolean;
  loadError: { code: string | null } | null;
  plan: unknown;
  blockerCount: number;
  unknownCount: number;
  unprocessedCount: number;
  confirmSelection: boolean;
  running: boolean;
}

/** §16.5 order: precheck state first, then blocker, unknown, unprocessed, checkbox, running. */
export function startDisabledReason(input: StartDisabledInput): string | undefined {
  if (input.loading) return "正在预检";
  if (input.loadError) return input.loadError.code === "SCOPE_FORBIDDEN" ? "当前身份没有归档权限" : "预检失败，请先处理错误";
  if (!input.plan) return "预检失败，请先处理错误";
  if (input.blockerCount > 0) return "当前预检存在阻断项";
  if (input.unknownCount > 0) return "存在当前版本不能处理的项";
  if (input.unprocessedCount > 0) return `还有 ${input.unprocessedCount} 项异常未处理`;
  if (!input.confirmSelection) return "请确认归档选择";
  if (input.running) return "归档中…";
  return undefined;
}

export interface ApiFailureLike {
  code?: string | null;
  status?: number;
  message?: string;
}

function isApiFailureLike(cause: unknown): cause is ApiFailureLike {
  return typeof cause === "object" && cause !== null && "status" in cause && Number.isInteger((cause as { status?: unknown }).status);
}

export function archiveError(cause: unknown): { title: string; code: string; refresh: boolean } {
  if (isApiFailureLike(cause)) {
    if (cause.code === "SCOPE_FORBIDDEN") return { title: "当前身份没有该操作的权限", code: "SCOPE_FORBIDDEN", refresh: false };
    if (cause.code === "ARCHIVE_PENDING_REVIEW") return { title: "出现了新的待审核提交，请重新预检", code: "ARCHIVE_PENDING_REVIEW", refresh: true };
    if (cause.code === "ACTIVE_SUBMIT_ATTEMPT") return { title: "已有提交正在处理，完成后才能归档", code: "ACTIVE_SUBMIT_ATTEMPT", refresh: false };
    if (cause.code === "ARCHIVE_SCOPE_LIMIT_EXCEEDED") return { title: "候选提交超过归档上限，需要管理员处理", code: "ARCHIVE_SCOPE_LIMIT_EXCEEDED", refresh: false };
    if (cause.code === "ARCHIVE_ANOMALY_UNRESOLVED" || cause.code === "ARCHIVE_CONFIRMATION_REQUIRED" || cause.code === "ARCHIVE_AUDIT_VERSION_CONFLICT" || cause.code === "CANDIDATE_SET_CONFLICT" || cause.code === "CANDIDATE_BINDING_CONFLICT" || cause.code === "BASELINE_VERSION_CONFLICT" || cause.code === "WORKSPACE_OCCUPANCY_CONFLICT") {
      return { title: "归档候选或核验结果已变化，请重新预检", code: cause.code, refresh: true };
    }
    if (cause.code === "IDEMPOTENCY_CONFLICT") return { title: "本次操作与服务器记录不一致，请关闭对话框后重试", code: "IDEMPOTENCY_CONFLICT", refresh: false };
    return { title: "归档失败", code: cause.code ?? "ARCHIVE_FAILED", refresh: false };
  }
  return { title: cause instanceof Error ? cause.message : "归档失败", code: "ARCHIVE_FAILED", refresh: false };
}

export function resolutionError(cause: unknown): { title: string; code: string } {
  if (isApiFailureLike(cause)) {
    if (cause.code === "SCOPE_FORBIDDEN") return { title: "当前身份没有该操作的权限", code: "SCOPE_FORBIDDEN" };
    if (cause.code === "IDEMPOTENCY_CONFLICT") return { title: "本次操作与服务器记录不一致，请关闭对话框后重试", code: "IDEMPOTENCY_CONFLICT" };
    if (cause.code === "REQUEST_VALIDATION_FAILED" || cause.code === "UNPROCESSABLE_ENTITY") return { title: "理由或请求不符合要求", code: cause.code };
    if (cause.code) return { title: "操作未完成", code: cause.code };
  }
  return { title: "操作未完成", code: "ARCHIVE_RESOLUTION_FAILED" };
}

export function closeError(cause: unknown): { title: string; code: string } {
  if (isApiFailureLike(cause)) {
    if (cause.code === "SCOPE_FORBIDDEN") return { title: "当前身份没有该操作的权限", code: "SCOPE_FORBIDDEN" };
    if (cause.status === 404 || cause.code === "RESOURCE_NOT_FOUND") return { title: "未找到该提交，请重新预检", code: cause.code ?? "RESOURCE_NOT_FOUND" };
    if (cause.code === "ARCHIVE_CLOSED") return { title: "该提交已归档或关闭", code: "ARCHIVE_CLOSED" };
    if (cause.code === "IDEMPOTENCY_CONFLICT") return { title: "本次操作与服务器记录不一致，请关闭对话框后重试", code: "IDEMPOTENCY_CONFLICT" };
    if (cause.code === "REQUEST_VALIDATION_FAILED" || cause.code === "UNPROCESSABLE_ENTITY") return { title: "理由或请求不符合要求", code: cause.code };
    if (cause.code) return { title: "关闭未完成", code: cause.code };
  }
  return { title: "关闭未完成", code: "ARCHIVE_CLOSE_FAILED" };
}

export function anomalyDetailText(anomaly: Anomaly, displayName: (id: string) => string): string {
  const details = anomaly.details as Record<string, unknown>;
  switch (anomaly.issue_code) {
    case "INITIAL_SOURCE_UNEXPLAINED": {
      const edges = (details.edges as Array<{ submission_id: string; initial: { canonical_state_digest: string }; modified: { canonical_state_digest: string } }> | undefined) ?? [];
      const states = (details.states as Array<{ canonical_state_digest: string }> | undefined) ?? [];
      const edgeText = edges.map((edge) => `${displayName(edge.submission_id)}的①/②（${edge.initial.canonical_state_digest.slice(0, 12)}…/${edge.modified.canonical_state_digest.slice(0, 12)}…）`).join("、");
      return `与当前基线及本轮已通过的提交都对不上，可能漏传了现场的改动。候选：${edgeText || "无"}；状态数 ${states.length}。`;
    }
    case "GENERATION_TIME_MISSING": {
      const generated = details.generated_time as GeneratedTimeFacts | undefined;
      if (!generated?.status) return "基线没有生成时间记录";
      if (generated.status === "VALID") return "生成时间有效";
      return generatedTimeStatusText(generated);
    }
    case "GENERATION_TIME_INVALID_VALUES": {
      const generated = details.generated_time as { invalid_count?: number; selected_time_utc?: string | null; last_valid_source_row?: number | null } | undefined;
      return `${generated?.invalid_count ?? 0} 个值无法识别，采用最后一个有效值 ${generated?.selected_time_utc ?? "—"}（第 ${generated?.last_valid_source_row ?? "—"} 行）。`;
    }
    case "GENERATION_TIME_LAST_NOT_MAX": {
      const generated = details.generated_time as { selected_time_utc?: string | null; max_valid_time_utc?: string | null; last_valid_source_row?: number | null; max_valid_source_row?: number | null } | undefined;
      return `采用最后一个有效值 ${generated?.selected_time_utc ?? "—"}（第 ${generated?.last_valid_source_row ?? "—"} 行），最大值为 ${generated?.max_valid_time_utc ?? "—"}（第 ${generated?.max_valid_source_row ?? "—"} 行）。不会自动改用最大值。`;
    }
    case "TIME_ABNORMAL_MODIFIED":
    case "TIME_ABNORMAL_INITIAL": {
      const comparisons = (details.comparisons as Array<{ relation: string; left_time_utc: string | null; right_time_utc: string | null }> | undefined) ?? [];
      return comparisons.map((comparison) => {
        const left = comparison.left_time_utc ? formatServerTimeUtc(comparison.left_time_utc) : "—";
        const right = comparison.right_time_utc ? formatServerTimeUtc(comparison.right_time_utc) : "—";
        if (anomaly.issue_code === "TIME_ABNORMAL_MODIFIED") {
          return comparison.relation === "MODIFIED_BEFORE_INITIAL" ? `② ${left} 早于 ① ${right}` : `② ${left} 早于当前基线 ${right}`;
        }
        return `① ${left} 早于当前基线 ${right}`;
      }).join("；") || "时间对照异常";
    }
    case "BASELINE_TIME_UNAVAILABLE": {
      const generated = details.generated_time as GeneratedTimeFacts | null | undefined;
      const statusText = generated?.status ? generatedTimeStatusText(generated) : "基线没有生成时间记录";
      return `${statusText}；比较结果：无法比较`;
    }
    case "APPROVED_SIBLING_EXCLUDED":
      return `目标提交${displayName(anomaly.target_submission_id)}`;
    case "PROJECT_IDENTITY_EXCEPTION":
      return "该提交的项目身份与当前基线不一致，需要人工确认";
    default:
      return anomaly.issue_code;
  }
}

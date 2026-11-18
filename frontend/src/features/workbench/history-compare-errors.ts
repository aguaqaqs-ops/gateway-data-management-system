import { ApiError } from "../api/authenticated-fetch";

/**
 * How the workbench answers a failed History compare request or read.
 *
 * - `retry: "same"`: the request was not settled; retrying with the same
 *   idempotency key is safe and may reattach to an accepted operation.
 * - `retry: "new"`: the original key can no longer give a usable result
 *   (expired, conflicting or unreadable); only a new key can start again.
 * - `operationIds`: existing compares the user can jump to instead.
 */
export interface HistoryCompareFailure {
  code: string;
  message: string;
  retry: "same" | "new" | null;
  operationIds: string[];
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
}

function detail(cause: ApiError, key: string): unknown {
  return cause.details && typeof cause.details === "object"
    ? (cause.details as Record<string, unknown>)[key]
    : undefined;
}

const UNREADABLE_RESULT: Record<string, string> = {
  ARTIFACT_UNAVAILABLE: "原比较结果的文件已不可用",
  HISTORY_INTEGRITY_FAILURE: "原比较结果的绑定校验失败",
  BUNDLE_INTEGRITY_FAILURE: "原比较结果的 bundle 校验失败",
};

/** POST /v1/history-compares failures. */
export function describeHistoryStartError(cause: unknown): HistoryCompareFailure {
  if (cause instanceof DOMException && cause.name === "TimeoutError") {
    return {
      code: "TimeoutError",
      message: "请求超时；历史比较可能已经受理。使用同一请求重试会接回同一个比较。",
      retry: "same",
      operationIds: [],
    };
  }
  if (!(cause instanceof ApiError)) {
    return {
      code: cause instanceof Error ? cause.name : "REQUEST_FAILED",
      message: cause instanceof Error ? cause.message : String(cause),
      retry: "same",
      operationIds: [],
    };
  }
  const code = cause.code ?? `HTTP_${cause.status}`;
  const fail = (
    message: string,
    retry: HistoryCompareFailure["retry"],
    operationIds: string[] = [],
  ): HistoryCompareFailure => ({ code, message, retry, operationIds });
  if (cause.status === 403 || code === "SCOPE_FORBIDDEN")
    return fail("当前身份没有历史比较权限", null);
  switch (code) {
    case "IDEMPOTENCY_CONFLICT":
      return fail("本次请求与服务器上同一请求编号的记录不一致，请重新发起比较", "new");
    case "HISTORY_COMPARE_REQUEST_EXPIRED":
      return fail("原比较请求已过保留期，请重新发起比较", "new");
    case "HISTORY_COMPARE_SCOPE_LIMIT":
      return fail(
        "该设备已有正在执行的历史比较，达到同时执行上限；可查看已有比较，或稍后重试",
        "same",
        stringList(detail(cause, "operation_ids")).slice(0, 2),
      );
    case "HISTORY_COMPARE_ALIAS_LIMIT": {
      const operationId = detail(cause, "operation_id");
      return fail(
        "同一比较的重复请求过多；请直接查看已有比较",
        null,
        typeof operationId === "string" && operationId ? [operationId] : [],
      );
    }
    case "OPERATION_QUEUE_FULL":
      return fail("服务器任务队列已满，请稍后用同一请求重试", "same");
    case "SERVICE_NOT_READY":
      return fail("服务暂未就绪，可用同一请求重试", "same");
    case "RESOURCE_NOT_FOUND":
      return fail("所选节点不存在或已不可比较，请刷新后重新选择", null);
    default:
      if (code in UNREADABLE_RESULT)
        return fail(`${UNREADABLE_RESULT[code]}；可重新发起比较生成新结果`, "new");
      if (cause.status === 429 || cause.status >= 500)
        return fail(cause.message || "服务器暂时无法受理，可用同一请求重试", "same");
      return fail(cause.message, null);
  }
}

/** GET result / bundle failures for an accepted History compare. */
export function describeHistoryReadError(cause: unknown): HistoryCompareFailure {
  if (!(cause instanceof ApiError)) {
    return {
      code: cause instanceof Error ? cause.name : "REQUEST_FAILED",
      message: cause instanceof Error ? cause.message : String(cause),
      retry: null,
      operationIds: [],
    };
  }
  const code = cause.code ?? `HTTP_${cause.status}`;
  const fail = (message: string, retry: HistoryCompareFailure["retry"]): HistoryCompareFailure => ({
    code,
    message,
    retry,
    operationIds: [],
  });
  if (cause.status === 403 || code === "SCOPE_FORBIDDEN")
    return fail("当前身份没有历史比较权限", null);
  if (code === "HISTORY_COMPARE_RESULT_EXPIRED")
    return fail("比较结果已过保留期，需要重新比较", "new");
  if (code === "RESOURCE_NOT_FOUND") return fail("未找到该历史比较", null);
  if (code in UNREADABLE_RESULT) return fail(`${UNREADABLE_RESULT[code]}，可重新比较`, "new");
  return fail(cause.message, null);
}

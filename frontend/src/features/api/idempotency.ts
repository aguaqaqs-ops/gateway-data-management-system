import type { components } from "./generated/openapi";

export interface IdempotentIntent<T> {
  key: string;
  request: T;
}

type HistoryCompareRequest = components["schemas"]["HistoryCompareAcceptRequest"];

export function createIdempotentIntent<T>(request: T, createKey: () => string = () => crypto.randomUUID()): IdempotentIntent<T> {
  return { key: createKey(), request };
}

function sameHistoryCompareRequest(left: HistoryCompareRequest, right: HistoryCompareRequest): boolean {
  return left.nodes.length === right.nodes.length
    && left.nodes.every((node, index) => {
      const other = right.nodes[index];
      return other?.ref_kind === node.ref_kind && other.ref_id === node.ref_id;
    });
}

export function readHistoryCompareIntent(raw: string | null): IdempotentIntent<HistoryCompareRequest> | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<IdempotentIntent<HistoryCompareRequest>>;
    const request = value.request;
    if (typeof value.key !== "string" || !value.key || !request || !Array.isArray(request.nodes)) return null;
    if (request.nodes.length < 2 || request.nodes.length > 3) return null;
    if (request.nodes.some((node) => !node || !["baseline_node", "submission"].includes(node.ref_kind)
      || typeof node.ref_id !== "string" || !node.ref_id)) return null;
    return { key: value.key, request };
  } catch {
    return null;
  }
}

export function resolveHistoryCompareIntent(
  current: IdempotentIntent<HistoryCompareRequest> | null,
  request: HistoryCompareRequest,
  createKey: () => string = () => crypto.randomUUID(),
): IdempotentIntent<HistoryCompareRequest> {
  if (current && sameHistoryCompareRequest(current.request, request)) return current;
  return createIdempotentIntent(request, createKey);
}

export function requestWithTimeout<T>(request: Promise<T>, timeoutMs: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new DOMException("历史比较请求仍在处理", "TimeoutError")), timeoutMs);
    request.then((value) => { window.clearTimeout(timer); resolve(value); }, (cause: unknown) => { window.clearTimeout(timer); reject(cause); });
  });
}

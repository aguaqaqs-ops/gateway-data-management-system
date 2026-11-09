import type { SafeReviewFacts } from "../api/client";

/** Short local time shared with the group tree (MM/DD HH:mm); hover shows the UTC original. */
export function formatDispositionTime(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/**
 * Closure reason: full text with line breaks preserved, collapsed only when
 * the reason spans more than 3 lines (§6.4).
 */
export function ClosureReason({ reason }: { reason: string }) {
  const lines = reason.split("\n").length;
  if (lines <= 3) {
    return <span style={{ whiteSpace: "pre-wrap" }}>{reason}</span>;
  }
  return (
    <details>
      <summary>展开理由</summary>
      <span style={{ whiteSpace: "pre-wrap" }}>{reason}</span>
    </details>
  );
}

/**
 * REVIEW-mode top bar line under the status tags (§6.4): for an archive
 * closure the fixed line, for a manual close the actor/time line with the
 * reason expandable.
 */
export function ReviewDispositionLine({ facts }: { facts: SafeReviewFacts }) {
  const disposition = facts.submission_disposition;
  if (!disposition || disposition.disposition !== "CLOSED_NOT_ARCHIVED") return null;
  if (disposition.source_kind === "ARCHIVE") {
    return <p className="review-disposition-line">归档时选中了其他提交</p>;
  }
  const closure = disposition.closure;
  if (!closure) return <p className="review-disposition-line">该提交已关闭（未归档）</p>;
  return (
    <div className="review-disposition-line">
      <p>
        由 {closure.closed_by} 于{" "}
        <span title={closure.closed_at}>{formatDispositionTime(closure.closed_at)}</span> 关闭
      </p>
      <details>
        <summary>查看关闭理由</summary>
        <span style={{ whiteSpace: "pre-wrap" }}>{closure.reason}</span>
      </details>
    </div>
  );
}

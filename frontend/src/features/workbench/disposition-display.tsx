import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
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
 * Reason text folded after three rendered lines. The clamp is applied first and
 * the toggle is shown only when the rendered content actually overflows, so a
 * long single line wraps like any other long reason and a short reason keeps
 * its exact pre-fold layout. Line breaks are preserved.
 */
export function ReasonText({ children, as: Tag = "span" }: { children: ReactNode; as?: "p" | "span" }) {
  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);
  const textRef = useRef<HTMLSpanElement | null>(null);

  useLayoutEffect(() => {
    const node = textRef.current;
    if (!node || expanded) return;
    const measure = () => setOverflowing(node.scrollHeight > node.clientHeight + 1);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [children, expanded]);

  return (
    <Tag className="reason-text">
      <span ref={textRef} className={expanded ? "reason-text__body" : "reason-text__body reason-text__body--clamped"}>{children}</span>
      {(overflowing || expanded) && (
        <button type="button" className="link-button" onClick={() => setExpanded((value) => !value)}>{expanded ? "收起" : "展开"}</button>
      )}
    </Tag>
  );
}

/** Closure reason in the workbench detail panel and the review top bar. */
export function ClosureReason({ reason }: { reason: string }) {
  return <ReasonText>{reason}</ReasonText>;
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

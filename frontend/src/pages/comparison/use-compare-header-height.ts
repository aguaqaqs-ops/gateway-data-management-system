import { useEffect, useRef } from "react";
import type { GatewaySessionState } from "../../features/session/handoff-session";

export function useCompareHeaderHeight(sessionState: GatewaySessionState) {
  const pageRef = useRef<HTMLElement | null>(null);
  const headerRef = useRef<HTMLElement | null>(null);

  // R15: the sticky sidebar tracks the measured compare-header height so the
  // navigation title and search box are never covered by a taller top bar.
  // This effect stays above every early return: skipping it on some renders
  // would change the hook order and crash the page. It re-runs when the
  // session state settles because the header only mounts after the session
  // gate opens; otherwise the variable would stay unset on session-gated
  // first renders.
  useEffect(() => {
    const header = headerRef.current;
    const page = pageRef.current;
    if (!header || !page) return;
    const apply = () => {
      page.style.setProperty(
        "--compare-header-height",
        `${Math.max(1, Math.round(header.getBoundingClientRect().height))}px`,
      );
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(header);
    return () => observer.disconnect();
  }, [sessionState]);

  return { pageRef, headerRef };
}

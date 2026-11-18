import { useEffect, useState } from "react";
import {
  connectionStatusLabel,
  getConnectionStatus,
  type ConnectionStatus,
} from "../api/connection-status";

export function ConnectionStatusIndicator({
  hideConnected = false,
  compact = false,
}: {
  hideConnected?: boolean;
  compact?: boolean;
}) {
  const [status, setStatus] = useState<ConnectionStatus>(getConnectionStatus);
  useEffect(() => {
    const update = (event: Event) =>
      setStatus((event as CustomEvent<Exclude<ConnectionStatus, null>>).detail);
    window.addEventListener("gateway-connection-status", update);
    return () => window.removeEventListener("gateway-connection-status", update);
  }, []);
  const label = hideConnected && status === "connected" ? null : connectionStatusLabel(status);
  // Compact mode shows only the dot while connected; problems keep their text.
  if (label && compact && status === "connected")
    return (
      <span className="connection-status connection-status--compact" role="status" title={label}>
        <i aria-hidden="true" />
        <span className="sr-only">{label}</span>
      </span>
    );
  return label ? (
    <span className={`connection-status connection-status--${status}`} role="status">
      <i aria-hidden="true" />
      {label}
    </span>
  ) : null;
}

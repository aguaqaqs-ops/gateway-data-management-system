import { useEffect, useState } from "react";
import { connectionStatusLabel, getConnectionStatus, type ConnectionStatus } from "../features/api/connection-status";

export function ConnectionStatusIndicator({ hideConnected = false }: { hideConnected?: boolean }) {
  const [status, setStatus] = useState<ConnectionStatus>(getConnectionStatus);
  useEffect(() => {
    const update = (event: Event) => setStatus((event as CustomEvent<Exclude<ConnectionStatus, null>>).detail);
    window.addEventListener("gateway-connection-status", update);
    return () => window.removeEventListener("gateway-connection-status", update);
  }, []);
  const label = hideConnected && status === "connected" ? null : connectionStatusLabel(status);
  return label ? <span className={`connection-status connection-status--${status}`} role="status"><i aria-hidden="true" />{label}</span> : null;
}

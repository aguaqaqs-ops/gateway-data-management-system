import type { ReactNode } from "react";
import { AlertTriangle, Info, ListTree, MapPin } from "lucide-react";
import { formatHandoffDisplay, type GatewaySessionState, type HandoffDisplay } from "./handoff-session";

const RETURN_DIRECTORY_TITLE = "离开网关工作台，返回设备目录";

/**
 * Device location supplied by the directory handoff, rendered as separate
 * segments so a long project name never pushes the station code out of view.
 * The full text stays available through `title` and the accessible name.
 */
export function DevicePath({ display }: { display: HandoffDisplay }) {
  const label = formatHandoffDisplay(display);
  return <span className="device-context" title={label}>
    <span className="device-context__icon"><MapPin size={14} aria-hidden="true" /></span>
    <span className="device-path" aria-label={`设备位置：${label}`}>
      <span className="device-path__region">{display.region1}</span>
      <span className="device-path__sep" aria-hidden="true">/</span>
      <span className="device-path__region">{display.region2}</span>
      <span className="device-path__sep" aria-hidden="true">/</span>
      <span className="device-path__project">{display.project_name}</span>
      <span className="device-path__station">（{display.station_code}）</span>
    </span>
  </span>;
}

/** Link back to the device directory; only handoff sessions carry a trusted URL. */
export function ReturnToDirectoryLink({ href }: { href: string }) {
  return <a className="return-directory" href={href} title={RETURN_DIRECTORY_TITLE}>
    <ListTree size={14} aria-hidden="true" /><span>返回目录</span>
  </a>;
}

/**
 * First row of the comparison header for handoff sessions. Injected test
 * sessions carry no display, so this row is absent for them.
 */
export function DeviceBar({ state }: { state: GatewaySessionState }) {
  if (state.kind !== "handoff") return null;
  return <div className="device-bar">
    <DevicePath display={state.session.display} />
    <ReturnToDirectoryLink href={state.session.returnUrl} />
  </div>;
}

const MESSAGES = {
  none: "未选择设备，请从设备目录进入",
  invalid: "跳转信息无效，请从设备目录重新进入",
  expired: "会话无效或已过期，请从设备目录重新进入",
} as const;

/**
 * Full-page state for a missing, unusable, or expired handoff session. The
 * expired state keeps the device display and the directory return link in
 * memory (never storage); the other states have no trusted return address.
 */
export function SessionGate({ state, identityControl }: { state: GatewaySessionState; identityControl?: ReactNode }) {
  if (state.kind === "handoff" || state.kind === "preset") return null;
  const expired = state.kind === "expired";
  return <main className="workspace-page">
    <header className="workspace-topbar">
      <div className="workspace-brand"><strong>网关数据工作台</strong></div>
      {identityControl && <div className="workspace-topbar__right">{identityControl}</div>}
    </header>
    <section className="session-gate">
      <div className="session-gate__panel" role={expired ? "alert" : "status"}>
        <span className={`session-gate__icon${expired ? " session-gate__icon--problem" : ""}`} aria-hidden="true">
          {expired ? <AlertTriangle size={20} /> : <Info size={20} />}
        </span>
        <h1>{MESSAGES[state.kind]}</h1>
        {expired && state.display && <p>设备：{formatHandoffDisplay(state.display)}</p>}
        {expired && state.returnUrl && <a className="button button--primary" href={state.returnUrl} title={RETURN_DIRECTORY_TITLE}>
          <ListTree size={14} aria-hidden="true" /><span>返回目录</span>
        </a>}
      </div>
    </section>
  </main>;
}

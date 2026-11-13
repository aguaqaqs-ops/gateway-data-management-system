// Only enabled by CT110 A's development entry; B uses its device directory.
import { useLayoutEffect, useRef } from "react";

let controls: HTMLElement | null = null;
let applicationRoot: HTMLElement | null = null;

export function Manual08Controls() {
  const slot = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    if (controls) slot.current?.append(controls);
    return () => { if (controls && applicationRoot) applicationRoot.before(controls); };
  }, []);
  return <span ref={slot} className="manual08-reset-slot" />;
}

export async function prepareManual08(root: HTMLElement): Promise<boolean> {
  const toolbar = document.createElement("div");
  toolbar.className = "manual08-controls";
  toolbar.style.cssText = "display:inline-flex;align-items:center;gap:12px";
  controls = toolbar;
  applicationRoot = root;
  const status = document.createElement("span");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "button button--secondary";
  reset.textContent = "重置";
  toolbar.append(status, reset);
  // The comparison page has no reset button; only a floating status remains
  // so a reset started from the workbench is still visible here.
  if (new URLSearchParams(location.search).get("page") === "compare") {
    reset.hidden = true;
    toolbar.classList.add("manual08-controls--floating");
  }
  root.before(toolbar);
  let busy = false;
  let resetObserved = false;
  let pageLocked = false;
  const resetKey = "gdds-a-reset-pending";
  const stages: Record<string, string> = {
    stopping: "正在停止服务…", rebuilding: "正在重置…",
    provisioning: "正在开通设备…", checking: "正在检查…",
  };

  async function readStatus(): Promise<string> {
    const response = await fetch("/manual-api/status", { cache: "no-store" });
    if (!response.ok) throw new Error("无法读取重置状态，请重试。");
    const result = await response.json() as { state: string; stage: string };
    lockPage(result.state === "running" || result.state === "failed");
    reset.disabled = result.state === "running";
    if (result.state === "running") {
      resetObserved = true;
      sessionStorage.setItem(resetKey, "1");
      status.textContent = stages[result.stage] ?? "正在重置…";
    } else if (result.state === "failed") {
      status.textContent = `重置失败（${result.stage || "未知阶段"}），可重试。`;
    } else {
      status.textContent = "";
    }
    return result.state;
  }

  function lockPage(locked: boolean): void {
    pageLocked = locked;
    for (const element of root.querySelectorAll<HTMLElement>("main > :not(.workspace-topbar), .workspace-topbar .workspace-brand, .workspace-topbar__right > :not(.manual08-reset-slot)")) element.inert = locked;
  }

  async function waitForReset(): Promise<void> {
    while (await readStatus() === "running") {
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    if (pageLocked) throw new Error(status.textContent ?? "重置失败，请重试。");
  }

  reset.addEventListener("click", () => {
    if (busy || !window.confirm("确认清除环境 A 的测试数据并重置？")) return;
    busy = true;
    reset.disabled = true;
    lockPage(true);
    void (async () => {
      try {
        const response = await fetch("/manual-api/reset", { method: "POST", headers: { "X-GDDS-Reset": "confirm" } });
        if (!response.ok && response.status !== 409) throw new Error("重置请求未确认，请重试。");
        sessionStorage.setItem(resetKey, "1");
        await waitForReset();
        location.replace("/");
      } catch (error) {
        status.textContent = error instanceof Error ? error.message : "重置失败，请重试。";
      } finally {
        busy = false;
        reset.disabled = false;
      }
    })();
  });

  try {
    await waitForReset();
    if (sessionStorage.getItem(resetKey)) {
      for (const key of Object.keys(sessionStorage)) {
        if (key === "gdds-gateway-session" || key === "gateway-preview-operation"
          || key === "gateway-history-compare-pending-intent" || key.startsWith("gateway-review-history-key:")) sessionStorage.removeItem(key);
      }
      const storage = await navigator.storage.getDirectory();
      try { await storage.removeEntry("gateway-comparison-bundles-v1", { recursive: true }); }
      catch (error) { if (!(error instanceof DOMException) || error.name !== "NotFoundError") throw error; }
      sessionStorage.removeItem(resetKey);
    }
    const catalog = await fetch("/api/catalog", { cache: "no-store" });
    if (!catalog.ok) throw new Error("无法读取设备，请刷新重试。");
    const projects = (await catalog.json() as { projects: { station_code: string; provisioned: boolean; device_key: string }[] }).projects;
    const devices = projects.filter((project) => project.station_code === "TEST-SINGLE-001" && project.provisioned);
    if (devices.length !== 1) throw new Error("设备未就绪，请重试重置。");
    const response = await fetch("/api/handoffs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ device_key: devices[0].device_key }) });
    if (!response.ok) throw new Error("无法进入设备，请刷新重试。");
    const target = new URL((await response.json() as { gateway_url: string }).gateway_url);
    if (target.origin !== location.origin || !target.hash.startsWith("#gdds-handoff=")) throw new Error("设备交接无效，请刷新重试。");
    history.replaceState(history.state, "", location.pathname + location.search + target.hash);
    resetObserved = false;
    setInterval(() => {
      if (busy) return;
      void readStatus().then((state) => {
        if (resetObserved && state === "success") location.replace("/");
      }).catch(() => { status.textContent = "无法读取重置状态，请刷新重试。"; });
    }, 2000);
    return true;
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "无法进入设备，请刷新重试。";
    return false;
  }
}

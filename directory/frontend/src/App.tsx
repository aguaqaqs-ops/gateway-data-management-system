import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { duplicateCounts, matches, readState, regionCounts, stateSearch, visible } from "./model";
import type { Catalog, Project, ViewState } from "./model";

const RECENT_KEY = "gdds-directory-recent";
const errors: Record<string, string> = {
  DEVICE_NOT_FOUND: "该设备已不在目录中，请刷新后重试。",
  DEVICE_NOT_PROVISIONED: "该设备尚未在网关系统开通。",
  SESSION_EXPIRED: "会话已过期，请联系运维续期。",
  SESSION_UPDATING: "会话正在更新，请联系运维完成续期。",
  INVALID_REQUEST: "跳转请求无效，请刷新后重试。"
};

function readRecent(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(value) ? [...new Set(value.filter((item): item is string => typeof item === "string"))].slice(0, 10) : [];
  } catch { return []; }
}
function saveRecent(value: string[]): void {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(value.slice(0, 10))); } catch { /* Storage is optional. */ }
}

export default function App() {
  const [view, setView] = useState<ViewState>(() => readState(window.location.search));
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [load, setLoad] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const [recent, setRecent] = useState<string[]>(readRecent);
  const [selected, setSelected] = useState(-1);
  const [handoffError, setHandoffError] = useState("");
  const [busy, setBusy] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  const update = useCallback((change: Partial<ViewState>) => {
    const next = { ...view, ...change };
    window.history.pushState(null, "", `${window.location.pathname}${stateSearch(next)}`);
    setView(next);
    setSelected(-1);
  }, [view]);

  useEffect(() => {
    const onPop = () => { setView(readState(window.location.search)); setSelected(-1); };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    let active = true;
    setLoad("loading");
    fetch("/api/catalog").then(async (response) => {
      if (!response.ok) {
        const failure: { code?: string } = await response.json().catch(() => ({}));
        if (response.status === 503 && failure.code === "CATALOG_EMPTY") return null;
        throw new Error("catalog unavailable");
      }
      return await response.json() as Catalog;
    }).then((data) => {
      if (!active) return;
      if (!data) { setCatalog(null); setLoad("empty"); return; }
      if (!Array.isArray(data.projects)) throw new Error("catalog unavailable");
      setCatalog(data);
      setLoad("ready");
      const known = new Set(data.projects.map((project) => project.device_key));
      const next = readRecent().filter((key) => known.has(key));
      saveRecent(next);
      setRecent(next);
    }).catch(() => { if (active) setLoad("error"); });
    return () => { active = false; };
  }, [attempt]);

  const projects = useMemo(() => catalog?.projects || [], [catalog]);
  const filtered = useMemo(() => visible(projects, view), [projects, view]);
  const counts = useMemo(() => regionCounts(projects, view.q), [projects, view.q]);
  const duplicates = useMemo(() => duplicateCounts(projects), [projects]);
  const pages = Math.max(1, Math.ceil(filtered.length / 50));
  const currentPage = Math.min(view.page, pages);
  const rows = filtered.slice((currentPage - 1) * 50, currentPage * 50);
  const recentProjects = recent.map((key) => projects.find((item) => item.device_key === key)).filter((item): item is Project => !!item);

  const enter = useCallback(async (project: Project) => {
    if (!project.provisioned || busy) return;
    setBusy(true);
    setHandoffError("");
    try {
      const response = await fetch("/api/handoffs", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_key: project.device_key, return_query: window.location.search || undefined }) });
      if (!response.ok) {
        const data: { code?: string } = await response.json().catch(() => ({}));
        setHandoffError(errors[data.code || ""] || "进入失败，请稍后重试。");
        return;
      }
      const data: { gateway_url?: unknown } = await response.json();
      if (typeof data.gateway_url !== "string") throw new Error("invalid response");
      const target = new URL(data.gateway_url);
      if ((target.protocol !== "http:" && target.protocol !== "https:") || !target.hash.startsWith("#gdds-handoff=")) throw new Error("invalid response");
      const next = [project.device_key, ...recent.filter((key) => key !== project.device_key)].slice(0, 10);
      saveRecent(next);
      setRecent(next);
      window.location.assign(target.href);
    } catch { setHandoffError("进入失败，请稍后重试。"); }
    finally { setBusy(false); }
  }, [busy, recent]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      const editing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target.isContentEditable;
      if (event.key === "Escape" && view.q) { event.preventDefault(); update({ q: "", page: 1 }); return; }
      if (event.key === "/" && !editing) { event.preventDefault(); searchRef.current?.focus(); return; }
      if (editing || target instanceof HTMLButtonElement || target instanceof HTMLAnchorElement) return;
      if ((event.key === "ArrowDown" || event.key === "ArrowUp") && rows.length) {
        event.preventDefault();
        const next = event.key === "ArrowDown" ? Math.min(selected + 1, rows.length - 1) : Math.max(selected < 0 ? 0 : selected - 1, 0);
        setSelected(next);
        rowRefs.current[next]?.focus();
      } else if (event.key === "Enter" && selected >= 0 && rows[selected]) {
        event.preventDefault(); void enter(rows[selected]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enter, rows, selected, update, view.q]);

  const totalMatches = projects.filter((project) => matches(project, view.q)).length;
  const orderedRegions = [...counts.entries()].sort(([a], [b]) => a.localeCompare(b, "zh-CN"));
  const regionLabel = [view.r1, view.r2].filter(Boolean).join(" / ") || "全部地区";

  return <div className="page">
    <header className="top"><div className="brand"><span className="brand-mark">网</span>网关设备目录</div><span className="tag">试运行</span><span className="vsep"/><span className="muted">{projects.length.toLocaleString()} 个项目</span><span className="spacer"/><span className="muted">进入身份</span><span className="identity" title="跳转到网关系统时使用的测试身份">test1 · 全部权限</span></header>
    <div className="searchbar"><label className="search"><span aria-hidden="true">⌕</span><input ref={searchRef} aria-label="搜索项目" placeholder="搜索项目名、站号或拼音首字母，如 cnbdz" value={view.q} onChange={(event) => update({ q: event.target.value, page: 1 })}/>{view.q && <span className="muted">{totalMatches} 个结果</span>}<span className="kbd">/</span></label>
      <div className="seg" role="radiogroup" aria-label="搜索范围"><button role="radio" aria-checked={view.scope === "all"} onClick={() => update({ scope: "all", page: 1 })}>全部地区</button><button role="radio" aria-checked={view.scope === "region"} onClick={() => update({ scope: "region", page: 1 })}>仅 {regionLabel}</button></div>
      <span className="spacer"/><div className="recent"><span className="muted">◷ 最近访问</span>{recentProjects.map((project) => <button className="chip" key={project.device_key} disabled={!project.provisioned || busy} title={!project.provisioned ? "该设备尚未在网关系统开通" : project.name} onClick={() => void enter(project)}>{project.name}<span className="muted">{project.region2}</span></button>)}</div></div>
    <div className="body"><nav className="tree" aria-label="地区"><div className="tree-head">{view.q ? "按地区筛选结果" : "地区筛选"}</div><div className="tree-list"><button className={`node root ${!view.r1 ? "selected" : ""}`} onClick={() => update({ r1: "", r2: "", scope: "all", page: 1 })}>{view.q ? "全部匹配" : "全部地区"}<span>{view.q ? totalMatches : projects.length}</span></button>{orderedRegions.map(([region, children]) => <div key={region}><button className={`node ${view.r1 === region && !view.r2 ? "selected" : ""}`} aria-expanded={view.r1 === region} onClick={() => update({ r1: view.r1 === region && !view.r2 ? "" : region, r2: "", scope: view.q ? "region" : view.scope, page: 1 })}><span aria-hidden="true">{view.r1 === region ? "⌄" : "›"}</span>{region}<span>{[...children.values()].reduce((a, b) => a + b, 0)}</span></button>{view.r1 === region && [...children.entries()].sort(([a], [b]) => a.localeCompare(b, "zh-CN")).map(([name, count]) => <button className={`node child ${view.r2 === name ? "selected" : ""}`} key={name} aria-current={view.r2 === name ? "true" : undefined} onClick={() => update({ r1: region, r2: name, scope: view.q ? "region" : view.scope, page: 1 })}>{name}<span>{count}</span></button>)}</div>)}</div></nav>
      <main className="content">{view.q && <div className="notice">搜索“{view.q}”；左侧数字为各地区的匹配数，点击可只看该地区。</div>}{handoffError && <div role="alert" className="error">{handoffError}<button aria-label="关闭错误提示" onClick={() => setHandoffError("")}>×</button></div>}
        <section className="card" aria-label="项目列表"><div className="card-head"><strong className="crumb">{view.q && view.scope === "all" ? "搜索结果" : regionLabel}</strong><span className="muted">共 {filtered.length} 个项目</span><span className="spacer"/><span className="muted">按名称排序</span></div>
          {load === "loading" ? <div className="empty">正在加载目录…</div> : load === "empty" ? <div className="empty"><strong>目录尚未导入</strong><p>请联系运维导入设备名单。</p></div> : load === "error" ? <div className="empty"><strong>目录加载失败</strong><p>请检查服务连接后重试。</p><button className="primary" onClick={() => setAttempt((value) => value + 1)}>重试</button></div> : <><div className="table-wrap"><table><thead><tr><th>项目名</th><th>站号</th><th>设备标识</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{rows.map((project, index) => <tr key={project.device_key} ref={(node) => { rowRefs.current[index] = node; }} tabIndex={-1} aria-selected={selected === index} className={selected === index ? "focused" : ""}><td><span className="name">{project.name}</span>{(duplicates.get(project.name) || 0) > 1 && <span className="dup" title={`全目录有 ${duplicates.get(project.name)} 个同名项目，按站号区分`}>同名</span>}</td><td className="mono">{project.station_code}</td><td className="mono muted">{project.device_key}</td><td>{project.provisioned ? <button className="enter" disabled={busy} onClick={() => void enter(project)}>进入提交树 ›</button> : <span title="该设备尚未在网关系统开通"><button className="unavailable" disabled aria-label={`未开通：${project.name}，该设备尚未在网关系统开通`}>未开通</button></span>}</td></tr>)}</tbody></table>{rows.length === 0 && <div className="empty">没有匹配的项目</div>}</div><div className="card-foot"><span>第 {filtered.length ? (currentPage - 1) * 50 + 1 : 0}–{Math.min(currentPage * 50, filtered.length)} 项，共 {filtered.length} 项</span><div className="pager"><button disabled={currentPage <= 1} onClick={() => update({ page: currentPage - 1 })} aria-label="上一页">‹</button><span>{currentPage} / {pages}</span><button disabled={currentPage >= pages} onClick={() => update({ page: currentPage + 1 })} aria-label="下一页">›</button></div><span className="spacer"/><span>↑ ↓ 选择　Enter 进入提交树</span></div></>}
        </section></main></div>
  </div>;
}

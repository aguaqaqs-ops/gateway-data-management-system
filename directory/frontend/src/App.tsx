import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PAGE_SIZE, duplicateCounts, filterRegions, handoffQuery, highlightParts, matches, readState, regionCounts, stateSearch, visible } from "./model";
import type { Catalog, ListView, Project, ViewState } from "./model";

const RECENT_KEY = "gdds-directory-recent";
const VIEW_KEY = "gdds-directory-view";
const RECENT_SHOWN = 5;
const UNPROVISIONED = "该设备尚未在网关系统开通";
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
function readViewPreference(): ListView {
  try { return localStorage.getItem(VIEW_KEY) === "tiles" ? "tiles" : "list"; } catch { return "list"; }
}
function saveViewPreference(view: ListView): void {
  try { localStorage.setItem(VIEW_KEY, view); } catch { /* Storage is optional. */ }
}
const formatCount = (value: number): string => value.toLocaleString("zh-CN");

function Highlighted({ text, query, prefix = false }: { text: string; query: string; prefix?: boolean }) {
  return <>{highlightParts(text, query, prefix).map((part, index) => part.hit ? <mark key={index}>{part.text}</mark> : part.text)}</>;
}

export default function App() {
  const [view, setView] = useState<ViewState>(() => readState(window.location.search, readViewPreference()));
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [load, setLoad] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const [recent, setRecent] = useState<string[]>(readRecent);
  const [recentExpanded, setRecentExpanded] = useState(false);
  const [regionFilter, setRegionFilter] = useState("");
  const [selected, setSelected] = useState(-1);
  const [handoffError, setHandoffError] = useState("");
  const [busy, setBusy] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);
  const tileRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const gridRef = useRef<HTMLDivElement>(null);

  const update = useCallback((change: Partial<ViewState>) => {
    const next = { ...view, ...change };
    window.history.pushState(null, "", `${window.location.pathname}${stateSearch(next)}`);
    setView(next);
    setSelected(-1);
  }, [view]);
  const switchView = useCallback((next: ListView) => {
    if (next === view.view) return;
    saveViewPreference(next);
    update({ view: next, page: 1 });
  }, [update, view.view]);

  useEffect(() => {
    const onPop = () => { setView(readState(window.location.search, readViewPreference())); setSelected(-1); };
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
  const pageSize = PAGE_SIZE[view.view];
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(view.page, pages);
  const rows = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const recentProjects = recent.map((key) => projects.find((item) => item.device_key === key)).filter((item): item is Project => !!item);
  const shownRecent = recentExpanded ? recentProjects : recentProjects.slice(0, RECENT_SHOWN);

  const enter = useCallback(async (project: Project) => {
    if (!project.provisioned || busy) return;
    let returnQuery: string | undefined;
    try { returnQuery = handoffQuery(window.location.search); }
    catch {
      setHandoffError("当前返回位置过长，请缩短搜索内容后再进入；当前页面状态已保留。");
      return;
    }
    setBusy(true);
    setHandoffError("");
    try {
      const response = await fetch("/api/handoffs", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_key: project.device_key, return_query: returnQuery }) });
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
      const onTile = target.dataset.tile !== undefined;
      if (event.key === "Escape" && view.q) { event.preventDefault(); update({ q: "", page: 1 }); return; }
      if (event.key === "/" && !editing) { event.preventDefault(); searchRef.current?.focus(); return; }
      if (editing || ((target instanceof HTMLButtonElement || target instanceof HTMLAnchorElement) && !onTile)) return;
      if (view.view === "tiles") {
        // Tiles are buttons, so Enter on a focused tile already activates it.
        const columns = gridRef.current ? getComputedStyle(gridRef.current).gridTemplateColumns.split(" ").length : 1;
        const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -columns, ArrowDown: columns };
        if (step[event.key] !== undefined && rows.length) {
          event.preventDefault();
          const next = selected < 0 ? 0 : Math.min(Math.max(selected + step[event.key], 0), rows.length - 1);
          setSelected(next);
          tileRefs.current[next]?.focus();
        } else if (event.key === "Enter" && !onTile && selected >= 0 && rows[selected]) {
          event.preventDefault(); void enter(rows[selected]);
        }
        return;
      }
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
  }, [enter, rows, selected, update, view.q, view.view]);

  const totalMatches = projects.filter((project) => matches(project, view.q)).length;
  const orderedRegions = [...filterRegions(counts, regionFilter).entries()].sort(([a], [b]) => a.localeCompare(b, "zh-CN"));
  const regionLabel = [view.r1, view.r2].filter(Boolean).join(" / ") || "全部地区";
  // The scope choice only matters while searching inside a selected region.
  const showScope = !!view.q && !!view.r1;
  const searchingAll = !!view.q && (view.scope === "all" || !view.r1);
  const first = filtered.length ? (currentPage - 1) * pageSize + 1 : 0;

  const crumb = searchingAll ? <strong className="crumb">搜索结果</strong>
    : !view.r1 ? <strong className="crumb">全部地区</strong>
    : <nav className="crumb" aria-label="当前地区">
      {view.r2 ? <button className="crumb-link" onClick={() => update({ r2: "", page: 1 })}>{view.r1}</button> : <strong>{view.r1}</strong>}
      {view.r2 && <><span className="crumb-sep" aria-hidden="true">›</span><strong>{view.r2}</strong></>}
    </nav>;

  const enterButton = (project: Project) => project.provisioned
    ? <button className="enter" disabled={busy} onClick={() => void enter(project)}>进入提交树 ›</button>
    : <span title={UNPROVISIONED}><button className="unavailable" disabled aria-label={`未开通：${project.name}，${UNPROVISIONED}`}>未开通</button></span>;

  const table = <div className="table-wrap">
    <table className={view.q ? "search-results" : undefined}>
      <thead><tr>
        <th aria-sort="ascending">项目名<span className="sort-mark" aria-hidden="true">↑</span></th>
        {view.q && <th>地区</th>}
        <th>站号</th><th>设备标识</th><th><span className="sr-only">操作</span></th>
      </tr></thead>
      <tbody>{rows.map((project, index) => <tr key={project.device_key} ref={(node) => { rowRefs.current[index] = node; }} tabIndex={-1}
        aria-selected={selected === index} className={selected === index ? "focused" : ""} onClick={() => setSelected(index)}>
        <td><span className="name"><Highlighted text={project.name} query={view.q}/></span>
          {(duplicates.get(project.name) || 0) > 1 && <span className="dup" title={`全目录有 ${duplicates.get(project.name)} 个同名项目，按站号区分`}>同名</span>}</td>
        {view.q && <td className="muted" title={`${project.region1} / ${project.region2}`}>{project.region1} / {project.region2}</td>}
        <td className="mono"><Highlighted text={project.station_code} query={view.q} prefix/></td>
        <td className="mono key">{project.device_key}</td>
        <td>{enterButton(project)}</td>
      </tr>)}</tbody>
    </table>
    {rows.length === 0 && <div className="empty">没有匹配的项目</div>}
  </div>;

  const tiles = <div className="tiles-wrap">
    <div className="tiles" ref={gridRef} role="list" aria-label="项目概览">{rows.map((project, index) => {
      const detail = `${project.name}\n站号 ${project.station_code} · ${project.region1} / ${project.region2}`;
      return <div role="listitem" key={project.device_key}>
        <button data-tile="" ref={(node) => { tileRefs.current[index] = node; }}
          className={`tile${selected === index ? " focused" : ""}${project.provisioned ? "" : " off"}`}
          aria-disabled={!project.provisioned || busy || undefined}
          title={`${detail}\n${project.provisioned ? "点击进入提交树" : UNPROVISIONED}`}
          onFocus={() => setSelected(index)} onClick={() => void enter(project)}>
          <span className="tile-name"><Highlighted text={project.name} query={view.q}/></span>
          {(duplicates.get(project.name) || 0) > 1 && <span className="tile-code">{project.station_code}</span>}
          {!project.provisioned && <span className="tile-off">未开通</span>}
        </button>
      </div>;
    })}</div>
    {rows.length === 0 && <div className="empty">没有匹配的项目</div>}
  </div>;

  return <div className="page">
    <header className="top">
      <div className="brand"><span className="brand-mark">网</span>网关设备目录</div><span className="tag">试运行</span><span className="vsep"/>
      <label className="search"><span aria-hidden="true">⌕</span>
        <input ref={searchRef} aria-label="搜索项目" placeholder="搜索项目名、站号或拼音首字母，如 cnbdz" value={view.q} onChange={(event) => update({ q: event.target.value, page: 1 })}/>
        {view.q && <span className="muted">{formatCount(totalMatches)} 个结果</span>}<span className="kbd">/</span>
      </label>
      {showScope && <div className="seg" role="radiogroup" aria-label="搜索范围">
        <button role="radio" aria-checked={view.scope === "all"} onClick={() => update({ scope: "all", page: 1 })}>全部地区</button>
        <button role="radio" aria-checked={view.scope === "region"} onClick={() => update({ scope: "region", page: 1 })}>仅 {regionLabel}</button>
      </div>}
      <span className="spacer"/>
      <span className="identity" title="跳转到网关系统时使用的测试身份"><span className="muted">进入身份</span>test1 · 全部权限</span>
    </header>
    <div className="body">
      <aside className="side">
        {recentProjects.length > 0 && <section className="recent" aria-label="最近访问">
          <div className="side-title">◷ 最近访问</div>
          {shownRecent.map((project) => <button className="recent-item" key={project.device_key} disabled={!project.provisioned || busy}
            title={project.provisioned ? `${project.name} · ${project.region1} / ${project.region2}` : UNPROVISIONED} onClick={() => void enter(project)}>
            <span className="recent-name">{project.name}</span><span className="muted">{project.region2}</span>
          </button>)}
          {recentProjects.length > RECENT_SHOWN && <button className="recent-more" aria-expanded={recentExpanded} onClick={() => setRecentExpanded((value) => !value)}>
            {recentExpanded ? "收起" : `更多（${recentProjects.length - RECENT_SHOWN}）`}
          </button>}
        </section>}
        <nav className="tree" aria-label="地区">
          <div className="tree-head">
            {view.q && <div className="side-title">按地区筛选 · 数字为匹配数</div>}
            <label className="tree-filter"><span aria-hidden="true">⌕</span><input aria-label="筛选地区" placeholder="筛选地区" value={regionFilter} onChange={(event) => setRegionFilter(event.target.value)}/></label>
          </div>
          <div className="tree-list">
            <button className={`node root ${!view.r1 ? "selected" : ""}`} onClick={() => update({ r1: "", r2: "", scope: "all", page: 1 })}>{view.q ? "全部匹配" : "全部地区"}<span>{formatCount(view.q ? totalMatches : projects.length)}</span></button>
            {orderedRegions.map(([region, children]) => {
              const expanded = view.r1 === region || !!regionFilter.trim();
              const total = [...(counts.get(region)?.values() || [])].reduce((a, b) => a + b, 0);
              return <div key={region}>
                <button className={`node ${view.r1 === region && !view.r2 ? "selected" : ""} ${view.q && !total ? "zero" : ""}`} aria-expanded={expanded}
                  onClick={() => update({ r1: view.r1 === region && !view.r2 ? "" : region, r2: "", scope: view.q ? "region" : view.scope, page: 1 })}>
                  <span aria-hidden="true">{expanded ? "⌄" : "›"}</span>{region}<span>{formatCount(total)}</span>
                </button>
                {expanded && [...children.entries()].sort(([a], [b]) => a.localeCompare(b, "zh-CN")).map(([name, count]) =>
                  <button className={`node child ${view.r1 === region && view.r2 === name ? "selected" : ""} ${view.q && !count ? "zero" : ""}`} key={name}
                    aria-current={view.r1 === region && view.r2 === name ? "true" : undefined}
                    onClick={() => update({ r1: region, r2: name, scope: view.q ? "region" : view.scope, page: 1 })}>{name}<span>{formatCount(count)}</span></button>)}
              </div>;
            })}
            {orderedRegions.length === 0 && <p className="muted">没有匹配的地区</p>}
          </div>
        </nav>
      </aside>
      <main className="content">
        {handoffError && <div role="alert" className="error">{handoffError}<button aria-label="关闭错误提示" onClick={() => setHandoffError("")}>×</button></div>}
        <section className="card" aria-label="项目列表">
          <div className="card-head">{crumb}<span className="muted">共 {formatCount(filtered.length)} 个项目</span><span className="spacer"/>
            <div className="seg small" role="radiogroup" aria-label="显示方式">
              <button role="radio" aria-checked={view.view === "list"} onClick={() => switchView("list")}>☰ 列表</button>
              <button role="radio" aria-checked={view.view === "tiles"} onClick={() => switchView("tiles")}>▦ 概览</button>
            </div>
          </div>
          {load === "loading" ? <div className="empty">正在加载目录…</div>
            : load === "empty" ? <div className="empty"><strong>目录尚未导入</strong><p>请联系运维导入设备名单。</p></div>
            : load === "error" ? <div className="empty"><strong>目录加载失败</strong><p>请检查服务连接后重试。</p><button className="primary" onClick={() => setAttempt((value) => value + 1)}>重试</button></div>
            : <>{view.view === "tiles" ? tiles : table}
              <div className="card-foot">
                <span>第 {formatCount(first)}–{formatCount(Math.min(currentPage * pageSize, filtered.length))} 项，共 {formatCount(filtered.length)} 项</span>
                <div className="pager">
                  <button disabled={currentPage <= 1} onClick={() => update({ page: currentPage - 1 })} aria-label="上一页">‹</button>
                  <span>{currentPage} / {pages}</span>
                  <button disabled={currentPage >= pages} onClick={() => update({ page: currentPage + 1 })} aria-label="下一页">›</button>
                </div>
                <span className="spacer"/>
                <span>{view.view === "tiles" ? "方向键选择，Enter 或单击进入提交树" : "↑ ↓ 选择，Enter 进入提交树"}</span>
              </div></>}
        </section>
      </main>
    </div>
  </div>;
}

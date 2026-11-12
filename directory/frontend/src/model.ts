export interface Project {
  device_key: string;
  station_code: string;
  name: string;
  region1: string;
  region2: string;
  pinyin_initials: string[];
  pinyin_full: string[];
  provisioned: boolean;
}

export interface Catalog {
  catalog_version: string;
  imported_at: string;
  projects: Project[];
}

export interface ViewState { r1: string; r2: string; q: string; scope: "all" | "region"; page: number }

export function readState(search: string): ViewState {
  const params = new URLSearchParams(search);
  const page = Number(params.get("page"));
  return { r1: params.get("r1") || "", r2: params.get("r2") || "", q: params.get("q") || "",
    scope: params.get("scope") === "region" ? "region" : "all",
    page: Number.isSafeInteger(page) && page > 0 ? page : 1 };
}

export function stateSearch(state: ViewState): string {
  const params = new URLSearchParams();
  if (state.r1) params.set("r1", state.r1);
  if (state.r2 && state.r1) params.set("r2", state.r2);
  if (state.q) params.set("q", state.q);
  if (state.scope === "region") params.set("scope", "region");
  if (state.page > 1) params.set("page", String(state.page));
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function handoffQuery(search: string): string | undefined {
  // I3 counts Unicode characters, not the browser's percent-encoded bytes.
  // Decode only UTF-8 non-ASCII runs: %25, %26, %2B etc. must stay escaped.
  const query = search.replace(/(?:%[89a-f][0-9a-f])+/gi, (encoded) => {
    try { return decodeURIComponent(encoded); } catch { return encoded; }
  });
  if (Array.from(query).length > 1000) throw new Error("return query too long");
  return query || undefined;
}

export function matches(project: Project, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return project.name.toLowerCase().includes(q) || project.station_code.toLowerCase().startsWith(q) ||
    project.pinyin_initials.some((value) => value.toLowerCase().includes(q)) ||
    project.pinyin_full.some((value) => value.toLowerCase().includes(q));
}

const compare = (a: string, b: string): number => {
  const left = Array.from(a, (character) => character.codePointAt(0) ?? 0);
  const right = Array.from(b, (character) => character.codePointAt(0) ?? 0);
  for (let index = 0; index < Math.min(left.length, right.length); index++) {
    if (left[index] !== right[index]) return left[index] - right[index];
  }
  return left.length - right.length;
};
export function sorted(projects: Project[]): Project[] {
  return [...projects].sort((a, b) => compare(a.pinyin_full[0] || a.name, b.pinyin_full[0] || b.name)
    || compare(a.name, b.name) || compare(a.station_code, b.station_code));
}
export function inRegion(project: Project, state: ViewState): boolean {
  return (!state.r1 || project.region1 === state.r1) && (!state.r2 || project.region2 === state.r2);
}
export function visible(projects: Project[], state: ViewState): Project[] {
  return sorted(projects.filter((project) => matches(project, state.q) &&
    ((!state.q || state.scope === "region") ? inRegion(project, state) : true)));
}
export function regionCounts(projects: Project[], query: string): Map<string, Map<string, number>> {
  const regions = new Map<string, Map<string, number>>();
  for (const project of projects) {
    const children = regions.get(project.region1) || new Map<string, number>();
    if (!regions.has(project.region1)) regions.set(project.region1, children);
    if (!children.has(project.region2)) children.set(project.region2, 0);
    if (matches(project, query)) children.set(project.region2, (children.get(project.region2) || 0) + 1);
  }
  return regions;
}

// This only filters the tree's labels; counts and project selection stay intact.
export function filterRegions(regions: Map<string, Map<string, number>>, query: string): Map<string, Map<string, number>> {
  const q = query.trim().toLowerCase();
  return new Map([...regions].flatMap(([region, children]) => {
    const visibleChildren = region.toLowerCase().includes(q) ? children
      : new Map([...children].filter(([name]) => name.toLowerCase().includes(q)));
    return visibleChildren.size ? [[region, visibleChildren] as const] : [];
  }));
}

export interface HighlightPart { text: string; hit: boolean }

// The same literal, case-insensitive matching as the displayed search fields.
// Pinyin has no character alignment in the catalog, so it cannot locate Hanzi.
export function highlightParts(text: string, query: string, prefix = false): HighlightPart[] {
  const q = query.trim().toLowerCase();
  const lower = text.toLowerCase();
  if (!q || (prefix && !lower.startsWith(q))) return [{ text, hit: false }];
  const parts: HighlightPart[] = [];
  // Case folding can expand a character (e.g. İ); keep source text intact.
  const starts: number[] = [];
  const ends: number[] = [];
  let sourceOffset = 0;
  for (const character of text) {
    for (let unit = 0; unit < character.toLowerCase().length; unit++) {
      starts.push(sourceOffset);
      ends.push(sourceOffset + character.length);
    }
    sourceOffset += character.length;
  }
  let offset = 0;
  let index = lower.indexOf(q);
  while (index !== -1) {
    const start = starts[index];
    const end = ends[index + q.length - 1];
    if (start > offset) parts.push({ text: text.slice(offset, start), hit: false });
    if (end > offset) parts.push({ text: text.slice(Math.max(offset, start), end), hit: true });
    offset = end;
    if (prefix) break;
    index = lower.indexOf(q, index + q.length);
  }
  if (offset < text.length) parts.push({ text: text.slice(offset), hit: false });
  return parts;
}

export function duplicateCounts(projects: Project[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const project of projects) counts.set(project.name, (counts.get(project.name) || 0) + 1);
  return counts;
}

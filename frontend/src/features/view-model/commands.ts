export type BrowseMode = "PREVIEW" | "REVIEW" | "HISTORY";

export interface BrowseState {
  mode: BrowseMode;
  bundleDigest: string | null;
  workspaceId: string | null;
  previewResultId: string | null;
  submissionId: string | null;
  operationId: string | null;
  operationKind: "history-compare" | "operation" | null;
  pairId: string | null;
  nodeKey: string | null;
  workbenchNodeKey: string | null;
  tabKey: string | null;
  changeIndex: number;
  expandedGroups: string[];
  onlyInteresting: boolean;
  debug: boolean;
  search: string;
  comparisonNodeRefs: string[];
}

export const initialBrowseState: BrowseState = {
  mode: "PREVIEW",
  bundleDigest: null,
  workspaceId: null,
  previewResultId: null,
  submissionId: null,
  operationId: null,
  operationKind: null,
  pairId: null,
  nodeKey: null,
  workbenchNodeKey: null,
  tabKey: null,
  changeIndex: 0,
  expandedGroups: [],
  onlyInteresting: false,
  debug: false,
  search: "",
  comparisonNodeRefs: [],
};

export type BrowseCommand =
  | { name: "select-pair"; pairId: string }
  | { name: "set-bundle"; mode: BrowseMode; bundleDigest: string }
  | { name: "set-operation"; operationId: string | null; operationKind: "history-compare" | "operation" | null }
  | { name: "select-node"; nodeKey: string }
  | { name: "select-tab"; tabKey: string }
  | { name: "jump-to-change"; index: number }
  | { name: "toggle-group"; groupKey: string }
  | { name: "set-only-interesting"; enabled: boolean }
  | { name: "set-debug"; enabled: boolean }
  | { name: "set-search"; search: string }
  | { name: "add-comparison-node"; ref: string }
  | { name: "remove-comparison-node"; ref: string }
  | { name: "clear-comparison-nodes" };

export type CommandSource = "human" | "external";

export interface CommandResult {
  state: BrowseState;
  externalOperationActive: boolean;
}

function normalizeState(state: BrowseState): BrowseState {
  return {
    ...state,
    changeIndex: Math.max(0, Math.floor(state.changeIndex)),
    expandedGroups: [...new Set(state.expandedGroups)],
    comparisonNodeRefs: [...new Set(state.comparisonNodeRefs)].slice(0, 3),
  };
}

export function executeBrowseCommand(state: BrowseState, command: BrowseCommand): BrowseState {
  let next = state;
  switch (command.name) {
    case "select-pair": next = { ...state, pairId: command.pairId, changeIndex: 0 }; break;
    case "set-bundle": next = { ...state, mode: command.mode, bundleDigest: command.bundleDigest, pairId: null, nodeKey: null, tabKey: null, changeIndex: 0 }; break;
    case "set-operation": next = { ...state, operationId: command.operationId, operationKind: command.operationKind }; break;
    case "select-node": next = { ...state, nodeKey: command.nodeKey }; break;
    case "select-tab": next = { ...state, tabKey: command.tabKey }; break;
    case "jump-to-change": next = { ...state, changeIndex: Math.max(0, Math.floor(command.index)) }; break;
    case "toggle-group": next = {
      ...state,
      expandedGroups: state.expandedGroups.includes(command.groupKey)
        ? state.expandedGroups.filter((key) => key !== command.groupKey)
        : [...state.expandedGroups, command.groupKey],
    }; break;
    case "set-only-interesting": next = { ...state, onlyInteresting: command.enabled }; break;
    case "set-debug": next = { ...state, debug: command.enabled }; break;
    case "set-search": next = { ...state, search: command.search }; break;
    case "add-comparison-node":
      if (state.comparisonNodeRefs.length < 3 && !state.comparisonNodeRefs.includes(command.ref)) {
        next = { ...state, comparisonNodeRefs: [...state.comparisonNodeRefs, command.ref] };
      }
      break;
    case "remove-comparison-node": next = { ...state, comparisonNodeRefs: state.comparisonNodeRefs.filter((ref) => ref !== command.ref) }; break;
    case "clear-comparison-nodes": next = { ...state, comparisonNodeRefs: [] }; break;
  }
  return normalizeState(next);
}

export function encodeBrowseState(state: BrowseState): string {
  const params = new URLSearchParams();
  params.set("page", "compare");
  params.set("mode", state.mode);
  if (state.bundleDigest) params.set("bundle", state.bundleDigest);
  if (state.workspaceId) params.set("workspaceId", state.workspaceId);
  if (state.previewResultId) params.set("previewResultId", state.previewResultId);
  if (state.submissionId) params.set("submissionId", state.submissionId);
  if (state.operationId) params.set("operationId", state.operationId);
  if (state.operationKind) params.set("operationKind", state.operationKind);
  if (state.pairId) params.set("pair", state.pairId);
  if (state.nodeKey) params.set("node", state.nodeKey);
  if (state.workbenchNodeKey) params.set("workbenchNode", state.workbenchNodeKey);
  if (state.tabKey) params.set("tab", state.tabKey);
  if (state.changeIndex > 0) params.set("change", String(state.changeIndex));
  if (state.onlyInteresting) params.set("changed", "1");
  if (state.debug) params.set("debug", "1");
  if (state.search) params.set("q", state.search);
  for (const group of state.expandedGroups) params.append("group", group);
  for (const ref of state.comparisonNodeRefs) params.append("compare", ref);
  return params.toString();
}

export function decodeBrowseState(search: string): BrowseState {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const mode = params.get("mode");
  const change = Number.parseInt(params.get("change") ?? "0", 10);
  return normalizeState({
    ...initialBrowseState,
    mode: mode === "REVIEW" || mode === "HISTORY" ? mode : "PREVIEW",
    bundleDigest: params.get("bundle"),
    workspaceId: params.get("workspaceId"),
    previewResultId: params.get("previewResultId"),
    submissionId: params.get("submissionId"),
    operationId: params.get("operationId"),
    operationKind: params.get("operationKind") === "history-compare" || params.get("operationKind") === "operation" ? params.get("operationKind") as "history-compare" | "operation" : null,
    pairId: params.get("pair"),
    nodeKey: params.get("node"),
    workbenchNodeKey: params.get("workbenchNode"),
    tabKey: params.get("tab"),
    changeIndex: Number.isFinite(change) ? change : 0,
    expandedGroups: params.getAll("group"),
    onlyInteresting: params.get("changed") === "1",
    debug: params.get("debug") === "1",
    search: params.get("q") ?? "",
    comparisonNodeRefs: params.getAll("compare"),
  });
}

/** Internal command runtime; it exposes browsing commands only and has no mutation API. */
export class BrowseCommandRuntime {
  private state: BrowseState;
  private externalController: AbortController | null = null;
  private readonly listeners = new Set<(result: CommandResult) => void>();

  constructor(initial = decodeBrowseState(window.location.search), private readonly browserWindow: Window = window) {
    this.state = initial;
  }

  get snapshot(): CommandResult {
    return { state: this.state, externalOperationActive: this.externalController !== null };
  }

  subscribe(listener: (result: CommandResult) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  beginExternalOperation(): AbortSignal {
    this.externalController?.abort(new DOMException("外部操作已被替换", "AbortError"));
    this.externalController = new AbortController();
    this.publish();
    return this.externalController.signal;
  }

  finishExternalOperation(signal: AbortSignal): void {
    if (this.externalController?.signal !== signal) return;
    this.externalController = null;
    this.publish();
  }

  execute(command: BrowseCommand, source: CommandSource = "human"): BrowseState {
    if (source === "human" && this.externalController) {
      this.externalController.abort(new DOMException("用户已接管", "AbortError"));
      this.externalController = null;
    }
    this.state = executeBrowseCommand(this.state, command);
    const search = encodeBrowseState(this.state);
    const url = new URL(this.browserWindow.location.href);
    url.search = search;
    this.browserWindow.history.replaceState(null, "", url);
    this.publish();
    return this.state;
  }

  restoreFromUrl(): BrowseState {
    this.state = decodeBrowseState(this.browserWindow.location.search);
    this.publish();
    return this.state;
  }

  private publish(): void {
    const result = this.snapshot;
    for (const listener of this.listeners) listener(result);
  }
}

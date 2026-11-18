import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BrowseCommandRuntime, BrowseState } from "../../features/view-model/commands";
import {
  navigationTabHasDifferences,
  type DerivedNavigationGroup,
} from "../../features/view-model/model";
import {
  matchesGroup,
  matchesItem,
  type NavItem,
  type NavTab,
  type PairPresentation,
} from "./view-helpers";

export function useComparisonNavigation(options: {
  pairs: PairPresentation[];
  browse: BrowseState;
  runtime: BrowseCommandRuntime;
}) {
  const { pairs, browse, runtime } = options;
  const activePair = pairs.find(({ pair }) => pair.pair_id === browse.pairId) ?? pairs[0];
  const presentation = activePair?.presentation ?? null;
  const groups = useMemo(() => presentation?.view.groups ?? [], [presentation]);
  const navigationDiagnostics = presentation?.navigationDiagnostics;
  // Tabs an item shows in the tab strip; the sidebar lists an item only when it has some.
  // Showing empty tabs lasts for this page only, so it cannot silently stick.
  const [showEmptyTabs, setShowEmptyTabs] = useState(false);
  const selectedNavRef = useRef<HTMLDivElement>(null);

  const shownTabs = useCallback(
    (item: NavItem): NavTab[] =>
      item.tabs.filter((tab) => {
        if (!showEmptyTabs && tab.empty) return false;
        if (!browse.onlyInteresting) return true;
        return (
          navigationTabHasDifferences(tab) ||
          (navigationDiagnostics ?? []).some(
            ({ target }) =>
              target.item_key === item.itemKey &&
              (!target.tab_key || target.tab_key === tab.tabKey),
          )
        );
      }),
    [browse.onlyInteresting, navigationDiagnostics, showEmptyTabs],
  );
  const shownItems = useCallback(
    (group: DerivedNavigationGroup): NavItem[] => {
      const groupMatches = group.label
        .toLocaleLowerCase()
        .includes(browse.search.trim().toLocaleLowerCase());
      return group.items.filter(
        (item) => (groupMatches || matchesItem(item, browse.search)) && shownTabs(item).length > 0,
      );
    },
    [browse.search, shownTabs],
  );
  const visibleGroups = useMemo(
    () =>
      groups.filter((group) => {
        if (!matchesGroup(group, browse.search)) return false;
        return (
          group.items.some((item) => shownTabs(item).length > 0) ||
          navigationDiagnostics?.some(
            (diagnostic) => diagnostic.target.group_key === group.groupKey,
          ) === true
        );
      }),
    [browse.search, groups, navigationDiagnostics, shownTabs],
  );
  const navigationEntries = useMemo(
    () =>
      groups.flatMap((group) =>
        group.items.flatMap((item) => item.tabs.map((tab) => ({ group, item, tab }))),
      ),
    [groups],
  );
  const wholeTableName = browse.tabKey?.startsWith("__whole__:")
    ? browse.tabKey.slice("__whole__:".length)
    : null;
  const wholeTable = wholeTableName
    ? presentation?.view.tables.find((item) => item.tableName === wholeTableName)
    : null;
  // A saved location identifies both the item and its tab, including hidden empty tabs.
  const selectedEntry = useMemo(
    () =>
      navigationEntries.find(
        ({ item, tab }) => item.itemKey === browse.nodeKey && tab.tabKey === browse.tabKey,
      ) ??
      navigationEntries.find(
        ({ item, tab }) => item.itemKey === browse.nodeKey && shownTabs(item).includes(tab),
      ) ??
      navigationEntries.find(({ item }) => item.itemKey === browse.nodeKey) ??
      navigationEntries.find(({ item, tab }) => shownTabs(item).includes(tab)) ??
      navigationEntries.find(({ tab }) => !tab.empty) ??
      navigationEntries[0] ??
      null,
    [browse.nodeKey, browse.tabKey, navigationEntries, shownTabs],
  );
  const emptyTabCount = useMemo(
    () => navigationEntries.filter(({ tab }) => tab.empty).length,
    [navigationEntries],
  );
  const toggleEmptyTabs = () => {
    if (showEmptyTabs && selectedEntry?.tab.empty && !wholeTable) {
      const next =
        visibleGroups
          .flatMap((group) =>
            shownItems(group).flatMap((item) => shownTabs(item).map((tab) => ({ item, tab }))),
          )
          .find(({ tab }) => !tab.empty) ?? navigationEntries.find(({ tab }) => !tab.empty);
      if (next) {
        runtime.execute({ name: "select-node", nodeKey: next.item.itemKey });
        runtime.execute({ name: "select-tab", tabKey: next.tab.tabKey });
      }
    }
    setShowEmptyTabs((value) => !value);
  };
  const selectedTab = useMemo(
    () =>
      wholeTable && wholeTableName
        ? {
            tabKey: "__whole__:" + wholeTableName,
            label: wholeTable.label,
            tableName: wholeTableName,
            empty: false,
            rowFilter: null,
            facts: null,
            table: wholeTable,
            notice:
              presentation?.view.tableNotices.find(
                (notice) => notice.table_id === wholeTableName,
              ) ?? null,
          }
        : (selectedEntry?.tab ?? null),
    [presentation, selectedEntry, wholeTable, wholeTableName],
  );
  const selectedNodeKey = wholeTableName
    ? (groups
        .flatMap((group) => group.items)
        .find((item) => item.tabs.some((tab) => tab.tableName === wholeTableName))?.itemKey ??
      browse.nodeKey ??
      "")
    : (selectedEntry?.item.itemKey ?? "");
  const globalNavigationDiagnostics =
    presentation?.navigationDiagnostics.filter(
      ({ target }) => !target.group_key && !target.item_key && !target.tab_key && !target.table_id,
    ) ?? [];
  const table =
    presentation?.view.tables.find((item) => item.tableName === selectedTab?.tableName) ?? null;
  const surfaceTable =
    presentation?.surface.tables.find((item) => item.table_name === selectedTab?.tableName) ?? null;
  const replacement =
    presentation?.surface.comparison_mode === "DATASET_REPLACEMENT" ||
    table?.changeKind === "REPLACED";

  useEffect(() => {
    if (!presentation || !selectedTab) return;
    if (browse.tabKey !== selectedTab.tabKey)
      runtime.execute({ name: "select-tab", tabKey: selectedTab.tabKey }, "external");
    if (browse.nodeKey !== selectedNodeKey)
      runtime.execute({ name: "select-node", nodeKey: selectedNodeKey }, "external");
  }, [browse.nodeKey, browse.tabKey, presentation, runtime, selectedNodeKey, selectedTab]);
  useEffect(() => {
    selectedNavRef.current?.scrollIntoView({ block: "nearest" });
  }, [browse.nodeKey, browse.tabKey]);

  const chooseTab = (tableName: string, tabKey: string, itemKey = tableName) => {
    runtime.execute({ name: "select-node", nodeKey: itemKey });
    runtime.execute({ name: "select-tab", tabKey });
  };
  const choosePair = (pair: PairPresentation) => {
    runtime.execute({ name: "select-pair", pairId: pair.pair.pair_id });
    runtime.execute({ name: "select-node", nodeKey: "" });
    runtime.execute({ name: "select-tab", tabKey: "" });
  };
  const openWholeTable = (tableName: string, itemKey?: string | null) => {
    const owner = groups
      .flatMap((group) => group.items)
      .find(
        (item) => item.itemKey === itemKey || item.tabs.some((tab) => tab.tableName === tableName),
      );
    runtime.execute({ name: "select-node", nodeKey: itemKey ?? owner?.itemKey ?? selectedNodeKey });
    runtime.execute({ name: "select-tab", tabKey: "__whole__:" + tableName });
    // "查看整表" means the whole table, even when the same table is open as an orphan subset.
    if (runtime.snapshot.state.unassignedSide)
      runtime.execute({ name: "set-unassigned", side: null });
  };
  const itemLabels = useMemo(
    () =>
      new Map(
        groups.flatMap((group) => group.items.map((item) => [item.itemKey, item.label] as const)),
      ),
    [groups],
  );
  // A definition change may point at an item whose tabs are all empty; it still opens.
  const openItem = (itemKey: string) => {
    const item = groups
      .flatMap((group) => group.items)
      .find((candidate) => candidate.itemKey === itemKey);
    const tab = item ? (shownTabs(item)[0] ?? item.tabs[0]) : undefined;
    if (item && tab) chooseTab(tab.tableName, tab.tabKey, item.itemKey);
  };

  // The tab strip belongs to the selected navigation item only; the selected
  // tab stays visible even when the scope filter would hide it.
  const selectedItem = useMemo(
    () =>
      groups.flatMap((group) => group.items).find((item) => item.itemKey === selectedNodeKey) ??
      null,
    [groups, selectedNodeKey],
  );
  const stripTabs = useMemo(() => {
    if (!selectedItem) return [];
    const shown = shownTabs(selectedItem);
    return selectedItem.tabs.filter(
      (tab) =>
        shown.includes(tab) ||
        (!wholeTable &&
          tab.tabKey === selectedTab?.tabKey &&
          tab.tableName === selectedTab.tableName),
    );
  }, [selectedItem, selectedTab, shownTabs, wholeTable]);
  const itemEmptyTabCount = selectedItem ? selectedItem.tabs.filter((tab) => tab.empty).length : 0;
  const stripVisible = Boolean(
    selectedItem && (stripTabs.length > 1 || wholeTable || itemEmptyTabCount > 0),
  );

  return {
    activePair,
    presentation,
    groups,
    showEmptyTabs,
    selectedNavRef,
    shownTabs,
    shownItems,
    visibleGroups,
    wholeTableName,
    wholeTable,
    selectedEntry,
    emptyTabCount,
    toggleEmptyTabs,
    selectedTab,
    selectedNodeKey,
    globalNavigationDiagnostics,
    table,
    surfaceTable,
    replacement,
    chooseTab,
    choosePair,
    openWholeTable,
    itemLabels,
    openItem,
    selectedItem,
    stripTabs,
    itemEmptyTabCount,
    stripVisible,
  };
}

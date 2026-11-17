import { describe, expect, it } from "vitest";
import type { LocalComparisonPresentation } from "../../features/bundle/presentation";
import type { BrowseState } from "../../features/view-model/commands";
import type { PairPresentation } from "./view-helpers";
import { viewLabel, viewTitle } from "./view-copy";

function pair(pairId: string, before: string | null, current: string | null): PairPresentation {
  return {
    pair: { pair_id: pairId },
    roles: { before, current },
    presentation: null as unknown as LocalComparisonPresentation,
  };
}

const derivationRows: Array<{
  name: string;
  mode: BrowseState["mode"];
  index: number;
  pairId: string;
  before: string | null;
  current: string | null;
  label: string;
  title: string;
}> = [
  {
    name: "HISTORY 忽略角色与下标=0",
    mode: "HISTORY",
    index: 0,
    pairId: "baseline_to_initial",
    before: "baseline",
    current: "initial",
    label: "节点 1 → 节点 2",
    title: "节点 1 → 节点 2",
  },
  {
    name: "HISTORY 下标=2",
    mode: "HISTORY",
    index: 2,
    pairId: "initial_to_modified",
    before: "initial",
    current: "modified",
    label: "节点 3 → 节点 4",
    title: "节点 3 → 节点 4",
  },
  {
    name: "PREVIEW baseline → initial",
    mode: "PREVIEW",
    index: 0,
    pairId: "renamed_first",
    before: "baseline",
    current: "initial",
    label: "原始组态视图",
    title: "已归档数据 → 原始组态备份",
  },
  {
    name: "REVIEW FULL baseline → initial",
    mode: "REVIEW",
    index: 0,
    pairId: "renamed_first",
    before: "baseline",
    current: "initial",
    label: "原始组态视图",
    title: "已归档数据 → 原始组态备份",
  },
  {
    name: "PREVIEW initial → modified",
    mode: "PREVIEW",
    index: 1,
    pairId: "renamed_second",
    before: "initial",
    current: "modified",
    label: "本次组态视图",
    title: "原始组态备份 → 本次归档组态",
  },
  {
    name: "REVIEW FULL initial → modified",
    mode: "REVIEW",
    index: 1,
    pairId: "renamed_second",
    before: "initial",
    current: "modified",
    label: "本次组态视图",
    title: "原始组态备份 → 本次归档组态",
  },
  {
    name: "PREVIEW MODIFIED_ONLY baseline → modified",
    mode: "PREVIEW",
    index: 0,
    pairId: "initial_to_modified",
    before: "baseline",
    current: "modified",
    label: "当前基线 → 本次归档组态",
    title: "当前基线 → 本次归档组态",
  },
  {
    name: "REVIEW MODIFIED_ONLY baseline → modified",
    mode: "REVIEW",
    index: 0,
    pairId: "initial_to_modified",
    before: "baseline",
    current: "modified",
    label: "基线 → 修改",
    title: "提交绑定比较：基线 → 修改",
  },
  {
    name: "PREVIEW、单对、角色不在表内（含 schema-keyless 形态）",
    mode: "PREVIEW",
    index: 0,
    pairId: "left_to_right",
    before: "fixture-history-ref-0",
    current: "fixture-history-ref-1",
    label: "比较视图 1",
    title: "比较对 left_to_right",
  },
  {
    name: "PREVIEW 缺失角色（null）回退",
    mode: "PREVIEW",
    index: 0,
    pairId: "legacy_pair",
    before: null,
    current: null,
    label: "比较视图 1",
    title: "比较对 legacy_pair",
  },
  {
    name: "REVIEW 未知角色回退",
    mode: "REVIEW",
    index: 1,
    pairId: "custom_pair",
    before: "retired",
    current: "exported",
    label: "比较视图 2",
    title: "比较对 custom_pair",
  },
];

describe("comparison view copy", () => {
  it.each(derivationRows)("derives label and title from input roles: $name", (row) => {
    const target = pair(row.pairId, row.before, row.current);
    expect(viewLabel(target, row.index, row.mode)).toBe(row.label);
    expect(viewTitle(target, row.index, row.mode)).toBe(row.title);
  });
});

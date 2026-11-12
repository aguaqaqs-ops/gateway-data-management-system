import { describe, expect, it } from "vitest";
import { duplicateCounts, matches, readState, regionCounts, sorted, stateSearch, visible } from "./model";
import type { Project } from "./model";

const projects: Project[] = [
  { device_key: "dev-1", station_code: "SZ-0142", name: "城南", region1: "江苏", region2: "苏州", pinyin_initials: ["cn", "zn"], pinyin_full: ["chang nan", "zhang nan"], provisioned: true },
  { device_key: "dev-2", station_code: "SZ-0388", name: "城南", region1: "江苏", region2: "苏州", pinyin_initials: ["cn"], pinyin_full: ["chang nan"], provisioned: false },
  { device_key: "dev-3", station_code: "NB-1", name: "宁波站", region1: "浙江", region2: "宁波", pinyin_initials: ["nbz"], pinyin_full: [], provisioned: true }
];

describe("目录查询", () => {
  it.each([["城", "dev-1"], ["sz-0", "dev-1"], ["ZN", "dev-1"], ["ang n", "dev-1"], ["bz", "dev-3"]])("搜索 %s", (query, device) => {
    expect(matches(projects.find((project) => project.device_key === device)!, query)).toBe(true);
  });
  it("站号只按前缀匹配，地区计数与同名按全目录计算", () => {
    expect(matches(projects[0], "0142")).toBe(false);
    expect(regionCounts(projects, "cn").get("江苏")?.get("苏州")).toBe(2);
    expect(regionCounts(projects, "cn").get("浙江")?.get("宁波")).toBe(0);
    expect(duplicateCounts(projects).get("城南")).toBe(2);
    expect(sorted(projects).map((project) => project.station_code)).toEqual(["SZ-0142", "SZ-0388", "NB-1"]);
  });
  it("URL 可往返，并区分当前地区与全局搜索", () => {
    const current = readState("?r1=%E6%B1%9F%E8%8B%8F&r2=%E8%8B%8F%E5%B7%9E&q=cn&scope=region&page=2");
    expect(readState(stateSearch(current))).toEqual(current);
    expect(visible(projects, current)).toHaveLength(2);
    expect(visible(projects, { ...current, q: "nb", scope: "all" })[0].station_code).toBe("NB-1");
    expect(visible(projects, { ...current, q: "nb", scope: "region" })).toHaveLength(0);
    expect(readState("?page=-1").page).toBe(1);
  });
  it("可筛选超过一页的完整名单", () => {
    const many = Array.from({ length: 51 }, (_, index) => ({ ...projects[0], station_code: `SZ-${index}` }));
    const result = visible(many, readState("?r1=%E6%B1%9F%E8%8B%8F&page=2"));
    expect(result).toHaveLength(51);
    expect(result.slice(50, 100)).toHaveLength(1);
  });
});

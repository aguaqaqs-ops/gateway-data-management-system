import type { Page } from "@playwright/test";

const names = ["白洋湾", "滨湖", "沧浪", "城南", "城南", "东环", "枫桥", "观前", "虎丘", "金鸡湖", "娄葑", "木渎", "南环", "盘门", "清源", "上方", "狮山"];
export const projects = names.map((name, index) => ({
  device_key: `dev-${index.toString(16).padStart(16, "0")}`,
  station_code: `SZ-${String(index + 1).padStart(4, "0")}`,
  name: `${name} 110kV 变电站`, region1: "江苏", region2: index < 14 ? "苏州" : "无锡",
  pinyin_initials: [index === 3 || index === 4 ? "cn" : `p${index}`],
  pinyin_full: [index === 3 || index === 4 ? "cheng nan" : `p${String(index).padStart(2, "0")}`],
  provisioned: index !== 12
}));
projects.push({ device_key: "dev-0000000000000100", station_code: "NB-0018", name: "长宁 220kV 变电站", region1: "浙江", region2: "宁波", pinyin_initials: ["cn", "zn"], pinyin_full: ["chang ning", "zhang ning"], provisioned: true });

export async function mockCatalog(page: Page, empty = false): Promise<void> {
  await page.route("**/api/catalog", (route) => empty
    ? route.fulfill({ status: 503, json: { code: "CATALOG_EMPTY", message: "目录尚未导入" } })
    : route.fulfill({ json: { catalog_version: "c-test", imported_at: "2026-11-01T00:00:00Z", projects } }));
}

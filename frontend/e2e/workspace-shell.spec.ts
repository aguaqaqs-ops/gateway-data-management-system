import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

interface FixtureManifest {
  bundle_digest: string;
  closure: {
    entries: Array<{
      kind: string;
      logical_path: string;
      table_bindings?: Array<{ side: string; table_name: string }>;
    }>;
  };
}

test("打开应用显示 FE1 工作台基础与组件预览", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "网关数据工作台", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "比较工作台基础组件", level: 2 })).toBeVisible();
  await expect(page.getByRole("button", { name: "主要操作" })).toBeVisible();
  await expect(page.getByRole("button", { name: "次要操作" })).toBeVisible();
  await expect(page.getByRole("button", { name: "幽灵操作" })).toBeVisible();
  await expect(page.getByRole("button", { name: "危险操作" })).toBeVisible();
  await expect(page.getByText("请先完成上传校验")).toBeVisible();
  await expect(page.getByText("站点A_2026-11-02")).toBeVisible();
  await expect(page.getByLabel("正在加载比较结果")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("BUNDLE_INTEGRITY_MISMATCH");
});

test("确认对话框捕获焦点并要求填写理由", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "预览退回确认" }).click();
  const dialog = page.getByRole("dialog", { name: "退回这次提交？" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "确认退回" })).toBeDisabled();
  await expect(dialog.getByText("填写理由后才能确认")).toBeVisible();
  await page.locator("#review-reason").fill("请补齐变更说明");
  await expect(dialog.getByRole("button", { name: "确认退回" })).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "预览退回确认" })).toBeFocused();
});

test("下载 golden tar 到 OPFS 后从本地懒读 Parquet 且缓存命中不再下载", async ({ page }) => {
  const tar = await readFile("src/test/fixtures/generated/golden-bundle.tar");
  const manifestSize = Number.parseInt(tar.subarray(124, 136).toString("ascii").replace(/\0.*$/, "").trim(), 8);
  const manifest = JSON.parse(tar.subarray(512, 512 + manifestSize).toString("utf8")) as FixtureManifest;
  const currentTable = manifest.closure.entries.find((entry) => entry.kind === "SNAPSHOT_TABLE" && entry.table_bindings?.some((binding) => binding.side === "current"));
  if (!currentTable) throw new Error("golden tar 缺少 current 侧 Parquet 表");
  let downloadCount = 0;
  await page.route("**/fixtures/golden-bundle.tar", async (route) => {
    downloadCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/x-tar",
      headers: { ETag: manifest.bundle_digest, "Content-Length": String(tar.byteLength) },
      body: tar,
    });
  });
  await page.goto("/");

  try {
    const rows = await page.evaluate(async ({ bundleDigest, tablePath }) => {
      const importFeature = (path: string) => import(/* @vite-ignore */ path);
      const local = await importFeature("/src/features/bundle/local-bundle.ts") as typeof import("../src/features/bundle/local-bundle");
      const parquet = await importFeature("/src/features/bundle/parquet-reader.ts") as typeof import("../src/features/bundle/parquet-reader");
      const store = new local.OpfsBundleStore();
      const fetchBundle = () => fetch("/fixtures/golden-bundle.tar");
      const bundle = await local.ensureLocalBundle({ store, expectedBundleDigest: bundleDigest, fetchBundle });
      const tableRows = await parquet.readParquetTable(bundle, tablePath, { columns: ["dev_addr", "description"], rowStart: 0, rowEnd: 2 });
      const cached = await local.ensureLocalBundle({ store, expectedBundleDigest: bundleDigest, fetchBundle: async () => { throw new Error("OPFS cache miss"); } });
      return { rows: tableRows.map((row) => ({ dev_addr: String(row.dev_addr), description: String(row.description) })), cachedDigest: cached.manifest.bundle_digest };
    }, { bundleDigest: manifest.bundle_digest, tablePath: currentTable.logical_path });

    expect(rows.rows).toEqual([
      { dev_addr: "1", description: "线路保护装置 A" },
      { dev_addr: "2", description: "测控装置（升级）" },
    ]);
    expect(rows.cachedDigest).toBe(manifest.bundle_digest);
    expect(downloadCount).toBe(1);
  } finally {
    await page.evaluate(async (bundleDigest) => {
      try {
        const root = await navigator.storage.getDirectory();
        const bundles = await root.getDirectoryHandle("gateway-comparison-bundles-v1");
        await bundles.removeEntry(bundleDigest.replace(/^sha256:/, ""), { recursive: true });
      } catch { /* the bundle may not have been installed */ }
    }, manifest.bundle_digest);
  }
});

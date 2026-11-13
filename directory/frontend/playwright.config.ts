import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: Number(process.env.GATEWAY_FE_TEST_WORKERS || "2"),
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:5173", trace: "off", screenshot: "off", video: "off", ...devices["Desktop Chrome"] },
  webServer: { command: "npm run dev -- --host 127.0.0.1", url: "http://127.0.0.1:5173", reuseExistingServer: false }
});

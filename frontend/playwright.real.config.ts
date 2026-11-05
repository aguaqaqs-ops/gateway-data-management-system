import { defineConfig, devices } from "@playwright/test";

/**
 * FE3a real-backend e2e (frontend kickoff §4).
 * Production build behind vite preview, proxied to the Compose backend
 * (GATEWAY_FRONTEND_BACKEND_ORIGIN=http://backend:8000 inside the toolchain
 * container). One worker, serial; no retries. Identities are injected per
 * browser context via window.__gatewaySession (owner Q5).
 */
export default defineConfig({
  testDir: "./e2e-real",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 300_000,
  reporter: [
    ["list"],
    ["json", { outputFile: process.env.GATEWAY_FE_RESULTS_FILE ?? "test-results/results.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
  },
});

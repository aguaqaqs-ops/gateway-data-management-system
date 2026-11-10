import { resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * FE3a/FE3b real-backend e2e (frontend kickoff §4).
 * Production build behind vite preview, proxied to the Compose backend
 * (GATEWAY_FRONTEND_BACKEND_ORIGIN=http://backend:8000 inside the toolchain
 * container). One worker, serial; no retries. Identities are injected per
 * browser context via window.__gatewaySession (owner Q5).
 *
 * Suite selection mirrors `scripts/run-real-backend-e2e.sh --suite`:
 *   smoke    -> e2e-real/smoke.spec.ts
 *   journeys -> e2e-real/journeys.spec.ts
 *   t1       -> e2e-real/t1.spec.ts
 */
const suite = process.env.GATEWAY_FE_SUITE ?? "smoke";
const testMatch = {
  smoke: /smoke\.spec\.ts$/,
  journeys: /journeys\.spec\.ts$/,
  t1: /t1\.spec\.ts$/,
} satisfies Record<string, RegExp>;

if (!(suite in testMatch)) {
  throw new Error(`GATEWAY_FE_SUITE must be one of ${Object.keys(testMatch).join("|")} (got ${suite})`);
}

const resultsDir = process.env.GATEWAY_FE_RESULTS_DIR;
const outputDir = resolve(resultsDir ?? "test-results", "artifacts");
const resultsFile = process.env.GATEWAY_FE_RESULTS_FILE ?? resolve(resultsDir ?? "test-results", "results.json");

export default defineConfig({
  testDir: "./e2e-real",
  testMatch: testMatch[suite as keyof typeof testMatch],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 300_000,
  outputDir,
  reporter: [
    ["list"],
    ["json", { outputFile: resultsFile }],
  ],
  use: {
    baseURL: process.env.GATEWAY_FE_PREVIEW_URL ?? "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
  },
});

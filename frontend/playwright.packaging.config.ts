import { defineConfig, devices } from "@playwright/test";

/**
 * FE3a M1 packaging memory measurement (frontend kickoff §8.4).
 * Standalone config: production build only, no mock API, upload requests
 * are route-intercepted so no backend is needed and no occupancy marker.
 */
export default defineConfig({
  testDir: "./e2e-packaging",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "off",
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
  },
});

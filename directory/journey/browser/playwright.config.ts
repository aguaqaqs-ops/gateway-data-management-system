import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch: 'journey.spec.ts', workers: 1, fullyParallel: false,
  retries: 0, timeout: 1_800_000, globalTimeout: 1_860_000,
  expect: { timeout: 30_000 }, reporter: [['./safe-reporter.ts']],
  outputDir: '/tmp/directory-journey-test-results',
  use: { browserName: 'chromium', actionTimeout: 30_000, navigationTimeout: 30_000,
    trace: 'off', video: 'off', screenshot: 'off', viewport: { width: 1920, height: 1080 } },
});

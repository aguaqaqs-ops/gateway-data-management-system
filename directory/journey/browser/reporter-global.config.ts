import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch: 'reporter-probe.spec.ts', workers: 1, retries: 0,
  timeout: 30_000, reporter: [['./reporter-probe-observer.ts']],
  globalSetup: './reporter-global-setup.ts', outputDir: '/tmp/directory-reporter-global-results',
  use: { trace: 'off', screenshot: 'off', video: 'off' },
});

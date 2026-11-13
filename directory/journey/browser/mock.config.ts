import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch: 'mock.spec.ts', workers: 1, retries: 0,
  timeout: 90_000, reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'off', video: 'off', screenshot: 'off' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1', url: 'http://127.0.0.1:5173', reuseExistingServer: false },
});

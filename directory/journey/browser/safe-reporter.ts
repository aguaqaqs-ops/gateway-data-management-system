import type { FullResult, Reporter, TestResult } from '@playwright/test/reporter';
import { writeFileSync } from 'node:fs';
// Playwright's default error/JSON reporters include URLs and matcher values.
// Only this fixed status document may leave the browser process on failure.
export default class SafeReporter implements Reporter {
  private passed = false;
  onTestEnd(_test: unknown, result: TestResult) { this.passed = result.status === 'passed' && result.retry === 0; }
  onEnd(result: FullResult) {
    writeFileSync('/evidence/browser-exit.json', JSON.stringify({
      head: process.env.GDDS_JOURNEY_HEAD, session: process.env.GDDS_JOURNEY_SESSION,
      status: result.status, passed: this.passed && result.status === 'passed',
    }) + '\n');
  }
  printsToStdio() { return false; }
}

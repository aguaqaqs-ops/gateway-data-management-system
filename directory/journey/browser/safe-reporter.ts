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
  // Own the stdio channel: false makes Playwright 1.64.1 inject a terminal
  // reporter, which renders errors and URLs. Deliberately discard all chunks.
  printsToStdio() { return true; }
  onStdOut() {}
  onStdErr() {}
  onError() {}
}

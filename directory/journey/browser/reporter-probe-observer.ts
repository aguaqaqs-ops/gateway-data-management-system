import { writeFileSync } from 'node:fs';
import SafeReporter from './safe-reporter.js';

// Test-only observation, without copying the error message or arguments.
export default class ReporterProbeObserver extends SafeReporter {
  private observedErrors = 0;
  onError() {
    this.observedErrors++;
    writeFileSync('/evidence/probe-onerror.json', JSON.stringify({ on_error_calls: this.observedErrors }) + '\n');
    super.onError();
  }
}

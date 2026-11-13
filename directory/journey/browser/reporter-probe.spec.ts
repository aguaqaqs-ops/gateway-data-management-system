import { test, expect } from '@playwright/test';
import { writeFileSync } from 'node:fs';

// Synthetic only: never issued to a backend, and never copied into probe facts.
const canary = 'dir-' + 'x'.repeat(43);
const session = JSON.stringify({ sessions: [{ token: canary, actor_id: 'probe' }] });
const handoff = 'http://127.0.0.1:4173/#gdds-handoff=' + Buffer.from(session).toString('base64url');

test('intentional reporter failure sentinel', () => {
  console.log(session);
  console.error(handoff);
  writeFileSync('/evidence/probe-exercised.json', JSON.stringify({
    ran: true, console_stdout_emitted: true, console_stderr_emitted: true,
    assertion_failure_injected: true,
  }) + '\n');
  expect(handoff + session).toBe('fixed non-secret expected value');
});

test.afterAll(() => { throw new Error(handoff + session); });

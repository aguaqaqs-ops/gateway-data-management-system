import { writeFileSync } from 'node:fs';

export default function globalSetup() {
  const token = 'dir-' + 'y'.repeat(43);
  const document = JSON.stringify({ sessions: [{ token, actor_id: 'global-probe' }] });
  const handoff = 'http://127.0.0.1:4173/#gdds-handoff=' + Buffer.from(document).toString('base64url');
  writeFileSync('/evidence/probe-global-exercised.json', JSON.stringify({ global_setup_ran: true, error_injected: true }) + '\n');
  throw new Error(handoff + document);
}

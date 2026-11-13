import { test, expect, type Page, type Response } from '@playwright/test';
import { existsSync, writeFileSync } from 'node:fs';

const directory = 'http://127.0.0.1:8100';
const facts: Record<string, unknown> = {};
function record(stage: string, values: Record<string, unknown>) {
  facts[stage] = { status: 'passed', ...values };
  writeFileSync('/evidence/browser-facts.json', JSON.stringify(facts) + '\n');
}
async function pictures(page: Page, state: string) {
  // No URL matcher can serialize a secret fragment into an assertion error.
  expect(await page.evaluate(() => location.hash === '')).toBe(true);
  for (const width of [1280, 1920]) {
    await page.setViewportSize({ width, height: 1080 });
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    const grid = page.locator('div.grid-frame[aria-label="比较表格"]');
    if (await grid.count()) await expect(grid).toHaveAttribute('data-rendered', 'true', { timeout: 300_000 });
    await page.screenshot({ path: `/evidence/${state}-${width}.png`, fullPage: true });
  }
}
async function scope(page: Page, station: 'SZ-0142' | 'WX-0207') {
  expect(await page.evaluate((expected) => {
    const session = (window as unknown as { __gatewaySession?: { gatewayDeviceExternalKey: string; businessProjectId: string } }).__gatewaySession;
    const suffix = expected === 'SZ-0142' ? 'fbe8accb4da11574' : '0a5e7c9870eaba0b';
    return location.hash === '' && session?.gatewayDeviceExternalKey === `dev-${suffix}` && session.businessProjectId === `prj-${suffix}`;
  }, station)).toBe(true);
  await expect(page.locator('.device-context')).toContainText(station);
}
async function enter(page: Page, station: string) {
  await page.locator('tbody tr').filter({ hasText: station }).getByRole('button', { name: '进入提交树' }).click();
  await expect(page.getByRole('heading', { name: /组态树/ })).toBeVisible();
}
async function diff(page: Page) {
  await expect(page.locator('section.comparison-content')).toBeVisible({ timeout: 300_000 });
  await expect(page.locator('div.grid-frame[aria-label="比较表格"]')).toHaveAttribute('data-rendered', 'true', { timeout: 300_000 });
}
function post(page: Page, suffix: string): Promise<Response> {
  return page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith(suffix), { timeout: 300_000 });
}

test('directory A upload review B isolation renewal', async ({ page }) => {
  let resourceErrors = 0;
  page.on('pageerror', () => { resourceErrors++; });
  page.on('requestfailed', () => { resourceErrors++; });
  page.on('response', response => {
    if (['document', 'script', 'stylesheet'].includes(response.request().resourceType()) && response.status() >= 400) resourceErrors++;
  });
  await page.goto(`${directory}/?r1=${encodeURIComponent('江苏')}&r2=${encodeURIComponent('苏州')}&q=znbdz&scope=all`);
  expect(await page.evaluate(() => !('__gatewaySession' in window))).toBe(true);
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await expect(page.locator('tbody .dup')).toHaveCount(2);
  await pictures(page, 'directory-search');
  const savedQuery = new URL(page.url()).search;
  expect(resourceErrors).toBe(0);
  record('J2', { static_resources_ok: resourceErrors === 0, no_injected_session: true });
  await enter(page, 'SZ-0142');
  await scope(page, 'SZ-0142');
  await expect(page.getByText('尚无数据', { exact: true })).toBeVisible();
  await pictures(page, 'a-initial');
  await page.reload();
  await scope(page, 'SZ-0142');
  await expect(page.getByText('尚无数据', { exact: true })).toBeVisible();
  record('J3', { fragment_cleared: true, initial: true, refresh_scope: true });

  const expand = page.getByRole('button', { name: '展开详情面板' });
  if (await expand.count()) await expand.click();
  await page.getByTestId('upload-initial-input').setInputFiles('/input/full_initial');
  await page.getByTestId('upload-modified-input').setInputFiles('/input/full_modified');
  const uploadResponse = post(page, '/upload-revisions');
  const previewResponse = post(page, '/preview-operations');
  await page.getByRole('button', { name: '上传并生成预览' }).click();
  expect((await uploadResponse).status()).toBe(201);
  expect((await previewResponse).status()).toBe(202);
  await diff(page);
  const submitResponse = post(page, '/submit-attempts');
  await page.locator('.compare-actions').getByRole('button', { name: '提交', exact: true }).click();
  const submitDialog = page.getByRole('dialog');
  await expect(submitDialog).toBeVisible();
  // Existing FULL input may require explicit identity confirmation.
  for (const checkbox of await submitDialog.getByRole('checkbox').all()) await checkbox.check();
  await submitDialog.getByRole('button', { name: '确认提交', exact: true }).click();
  expect((await submitResponse).status()).toBe(202);
  await expect(page.locator('section[aria-label="提交结果"]')).toContainText('提交成功，已生成待审核提交。', { timeout: 300_000 });
  await submitDialog.getByRole('button', { name: '查看提交', exact: true }).click();
  await diff(page);
  const reviewResponse = post(page, '/review-events');
  await page.locator('.review-actions').getByRole('button', { name: '审核通过', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '确认通过', exact: true }).click();
  const approvedResponse = await reviewResponse;
  expect(approvedResponse.status()).toBe(201);
  const approved = await approvedResponse.json();
  expect(approved.status === 'APPROVED' && approved.event.actor_id === 'test1').toBe(true);
  // Read-only GET of review facts proves submitter and reviewer attribution.
  const submissionId = new URL(page.url()).searchParams.get('submissionId');
  expect(Boolean(submissionId)).toBe(true);
  const actorFacts = await page.evaluate(async (id) => {
    const s = (window as unknown as { __gatewaySession: { accessToken: string; gatewayDeviceExternalKey: string; businessProjectId: string } }).__gatewaySession;
    const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s.gatewayDeviceExternalKey));
    const key = Array.from(new Uint8Array(hash)).map(v => v.toString(16).padStart(2, '0')).join('');
    const response = await fetch(`/v1/submissions/${encodeURIComponent(id!)}/review`, { headers: { Authorization: `Bearer ${s.accessToken}`, 'X-Gateway-Device-Key': key } });
    if (!response.ok) return false;
    const body = await response.json();
    return body.status === 'APPROVED' && body.events.some((e: { event_kind: string; actor_id: string }) => e.event_kind === 'SUBMISSION_FINALIZED' && e.actor_id === 'test1') && body.events.some((e: { event_kind: string; actor_id: string }) => e.event_kind === 'APPROVED' && e.actor_id === 'test1');
  }, submissionId);
  expect(actorFacts).toBe(true);
  await page.reload();
  await scope(page, 'SZ-0142');
  await diff(page);
  await pictures(page, 'a-reviewed');
  const oldToken = await page.evaluate(() => (window as unknown as { __gatewaySession: { accessToken: string } }).__gatewaySession.accessToken);
  record('J4', { ui_upload: true, preview: true, ui_submit: true, ui_approve: true, actor_test1: true, refresh_scope: true });

  await page.getByRole('link', { name: '返回目录', exact: true }).first().click();
  expect(new URL(page.url()).origin).toBe(directory);
  expect(new URL(page.url()).search).toBe(savedQuery);
  await page.getByLabel('搜索项目', { exact: true }).fill('WX-0207');
  await enter(page, 'WX-0207');
  await scope(page, 'WX-0207');
  await expect(page.getByText('尚无数据', { exact: true })).toBeVisible();
  await expect(page.locator('table[aria-label="History 组态树"]')).not.toContainText('待审核');
  await pictures(page, 'b-initial');
  record('J5', { return_query_restored: true, b_initial_only: true, b_scope: true });

  writeFileSync('/control/renew-request', 'renew\n');
  await expect.poll(() => existsSync('/control/renew-complete'), { timeout: 180_000 }).toBe(true);
  await page.getByRole('link', { name: '返回目录', exact: true }).first().click();
  await page.getByLabel('搜索项目', { exact: true }).fill('SZ-0142');
  await enter(page, 'SZ-0142');
  await scope(page, 'SZ-0142');
  expect(await page.evaluate((old) => (window as unknown as { __gatewaySession: { accessToken: string } }).__gatewaySession.accessToken !== old, oldToken)).toBe(true);
  await expect(page.getByText('尚无数据', { exact: true })).toHaveCount(0);
  await expect(page.locator('table[aria-label="History 组态树"]')).toContainText('已通过');
  await pictures(page, 'a-renewed');
  record('J6', { directory_new_token: true, a_data_restored: true });
  expect(resourceErrors).toBe(0);
});

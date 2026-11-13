import { test, expect, type Page } from '@playwright/test';

async function rowVisible(page: Page) {
  const visible = await page.locator('tr[aria-selected="true"]').evaluate(row => {
    const body = row.closest('.table-wrap')!;
    const r = row.getBoundingClientRect();
    const b = body.getBoundingClientRect();
    const header = body.querySelector('thead')!.getBoundingClientRect();
    return document.activeElement === row && r.top >= Math.max(b.top, header.bottom) && r.bottom <= b.bottom;
  });
  expect(visible).toBe(true);
}
for (const width of [1280, 1920]) {
  test(`mock initial error and keyboard boundaries ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const projects = Array.from({ length: 60 }, (_, i) => ({
      device_key: `dev-${i.toString(16).padStart(16, '0')}`, station_code: `FOCUS-${String(i).padStart(3, '0')}`,
      name: `焦点项目 ${String(i).padStart(3, '0')}`, region1: '江苏', region2: '苏州',
      pinyin_initials: ['jd'], pinyin_full: [`jiao dian ${String(i).padStart(3, '0')}`], provisioned: true,
    }));
    await page.route('**/api/catalog', route => route.fulfill({ json: { projects } }));
    await page.route('**/api/handoffs', route => route.fulfill({ status: 409, json: { code: 'SESSION_UPDATING' } }));
    await page.goto('/');
    await page.getByRole('button', { name: '进入提交树' }).first().click();
    await expect(page.getByRole('alert')).toContainText('会话正在更新');
    expect(await page.locator('.table-wrap').evaluate(e => e.scrollTop)).toBe(0);
    await expect(page.locator('tbody tr').first()).toBeInViewport();
    await page.screenshot({ path: `/evidence/mock-error-${width}.png`, fullPage: true });
    await page.getByRole('button', { name: '关闭错误提示' }).click();
    await page.locator('body').click({ position: { x: 2, y: 2 } });
    await page.keyboard.press('ArrowDown');
    await rowVisible(page);
    await page.screenshot({ path: `/evidence/mock-focus-first-${width}.png`, fullPage: true });
    for (let i = 1; i < 50; i++) await page.keyboard.press('ArrowDown');
    await rowVisible(page);
    await expect(page.locator('tr[aria-selected="true"]')).toContainText('FOCUS-049');
    await page.screenshot({ path: `/evidence/mock-focus-last-${width}.png`, fullPage: true });
  });
}

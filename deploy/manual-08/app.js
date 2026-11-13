const enter = document.querySelector('#enter');
const reset = document.querySelector('#reset');
const output = document.querySelector('#status');
const labels = {stopping: '正在停止环境 A', rebuilding: '正在重建环境 A 数据', provisioning: '正在重新开通设备', checking: '正在检查就绪', interrupted: '管理服务中断'};
let running = false;
let entering = false;

async function refresh() {
  try {
    const response = await fetch('/manual-api/status', {cache: 'no-store'});
    if (!response.ok) throw new Error();
    const result = await response.json();
    running = result.state === 'running';
    enter.disabled = running || entering || result.state === 'failed';
    reset.disabled = running;
    output.textContent = running ? `${labels[result.stage] || '正在重置'}，请稍候。`
      : result.state === 'success' ? '重置完成。请关闭旧页面，再从此页进入。'
      : result.state === 'failed' ? `重置未完成（${labels[result.stage] || '执行失败'}）。请查看运维手册后重试。`
      : '可以进入设备或开始重置。';
  } catch {
    running = true;
    enter.disabled = true;
    reset.disabled = true;
    output.textContent = '无法读取管理状态，请联系运维。';
  }
}

reset.addEventListener('click', async () => {
  if (running || !window.confirm('确认清除环境 A 的全部测试业务数据并恢复 INITIAL？环境 B 不受影响。')) return;
  reset.disabled = true;
  enter.disabled = true;
  try {
    const response = await fetch('/manual-api/reset', {method: 'POST', headers: {'X-GDDS-Reset': 'confirm'}});
    if (!response.ok && response.status !== 409) throw new Error();
  } catch { output.textContent = '请求未确认，请检查管理状态。'; }
  await refresh();
});

async function clearPreviousSession() {
  for (const key of Object.keys(sessionStorage)) {
    if (key === 'gdds-gateway-session' || key === 'gateway-preview-operation'
        || key === 'gateway-history-compare-pending-intent' || key.startsWith('gateway-review-history-key:')) sessionStorage.removeItem(key);
  }
  const root = await navigator.storage.getDirectory();
  try { await root.removeEntry('gateway-comparison-bundles-v1', {recursive: true}); }
  catch (error) { if (error.name !== 'NotFoundError') throw error; }
}

enter.addEventListener('click', async () => {
  entering = true;
  enter.disabled = true;
  try {
    await clearPreviousSession();
    const catalog = await fetch('/api/catalog', {cache: 'no-store'});
    if (!catalog.ok) throw new Error();
    const matches = (await catalog.json()).projects.filter((p) => p.station_code === 'TEST-SINGLE-001' && p.provisioned);
    if (matches.length !== 1) throw new Error();
    const response = await fetch('/api/handoffs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({device_key: matches[0].device_key})});
    if (!response.ok) throw new Error();
    const target = new URL((await response.json()).gateway_url);
    if (target.origin !== location.origin || !target.hash.startsWith('#gdds-handoff=')) throw new Error();
    location.assign(target.href);
  } catch {
    output.textContent = '无法进入设备或清理本地缓存；请关闭其他环境 A 页面后重试。';
    entering = false;
    await refresh();
  }
});

await refresh();
setInterval(refresh, 2000);

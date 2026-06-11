import { chromium } from 'file:///C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/playwright@1.59.1/node_modules/playwright/index.mjs';

const input = 'D:/数字分身/图片增强/preview-tune.html';
const out = 'D:/数字分身/图片增强/preview-tune.png';

const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const page = await browser.newPage({
  viewport: { width: 1024, height: 1536 },
  deviceScaleFactor: 2,
});
await page.goto(`file:///${input}`, { waitUntil: 'networkidle' });
await page.screenshot({ path: out, fullPage: false, type: 'png' });

const overflow = await page.evaluate(() => {
  const rows = [];
  document.querySelectorAll('*').forEach((el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const overX = el.scrollWidth - el.clientWidth;
    const overY = el.scrollHeight - el.clientHeight;
    if (overX > 2 || overY > 2) {
      rows.push({
        tag: el.tagName.toLowerCase(),
        cls: el.className || '',
        overX,
        overY,
        rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
        text: (el.textContent || '').trim().slice(0, 60),
      });
    }
  });
  return rows.slice(0, 80);
});
console.log(JSON.stringify({ out, overflow }, null, 2));
await browser.close();

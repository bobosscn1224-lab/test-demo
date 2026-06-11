import { chromium } from 'file:///C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/playwright@1.59.1/node_modules/playwright/index.mjs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const htmlPath = path.join(__dirname, 'index.html');
const outPath = path.join(__dirname, '..', 'N和T专项进展-HTML一比一高清版.png');

const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const page = await browser.newPage({
  viewport: { width: 1024, height: 1536 },
  deviceScaleFactor: 3,
});
await page.goto(`file://${htmlPath.replaceAll('\\', '/')}`, { waitUntil: 'networkidle' });
await page.screenshot({ path: outPath, fullPage: false, type: 'png' });
await browser.close();

console.log(outPath);

import { apiGet, apiPost } from '../services/api';
import type { KnowledgeStats, ScanResult, ScanTaskStatus, KnowledgeResult } from '../types';

let toastTimer: ReturnType<typeof setTimeout> | undefined;
let feishuPreviewDocs: FeishuDoc[] = [];
let feishuPage = 1;
const FEISHU_PAGE_SIZE = 20;

interface FeishuDoc {
  name: string;
  type?: string;
  token?: string;
  url: string;
  imported?: boolean;
  imported_at?: string;
  chunks?: number;
}

interface FeishuImportedDoc extends FeishuDoc {
  imported_at: string;
  chunks: number;
}

interface FeishuPreview {
  folder_token: string;
  docs: FeishuDoc[];
  total_docs: number;
  folders: Array<{ name: string; token: string }>;
  skipped: Array<{ name: string; reason: string }>;
  wiki_spaces?: Array<{ name: string; space_id: string }>;
  wiki_docs?: FeishuDoc[];
  wiki_total_docs?: number;
}

interface FeishuImportResult {
  ok: boolean;
  successes: Array<{ name: string; chunks: number }>;
  failures: Array<{ name: string; reason: string }>;
  total_chunks: number;
  unique_docs: number;
}

interface FeishuDocContentPreview {
  name?: string;
  url: string;
  content_length: number;
  preview: string;
  truncated: boolean;
}

const text = {
  title: '\u77e5\u8bc6\u5e93\u7ba1\u7406',
  scan: '\u626b\u63cf\u7d22\u5f15',
  reindex: '\u91cd\u5efa\u7d22\u5f15',
  upload: '\u4e0a\u4f20\u6587\u4ef6',
  chunks: '\u7d22\u5f15\u5206\u5757',
  docs: '\u6587\u6863\u6570\u91cf',
  dirs: '\u76d1\u63a7\u76ee\u5f55',
  watching: '\u5b9e\u65f6\u76d1\u63a7',
  searchPlaceholder: '\u641c\u7d22\u77e5\u8bc6\u5e93\u5185\u5bb9...',
  searchHint: '\u641c\u7d22\u672c\u5730\u6587\u6863\u548c\u5df2\u5bfc\u5165\u7684\u98de\u4e66\u6587\u6863',
  monitorDirs: '\u76d1\u63a7\u76ee\u5f55',
  loading: '\u52a0\u8f7d\u4e2d...',
  feishuTitle: '\u98de\u4e66\u77e5\u8bc6\u5e93\u5bfc\u5165',
  feishuDesc: '\u4f7f\u7528\u72ec\u7acb\u6388\u6743\u548c\u72ec\u7acb token\uff0c\u4e0d\u5f71\u54cd\u5355\u7bc7\u98de\u4e66\u9605\u8bfb\u3002',
  auth: '\u83b7\u53d6\u6388\u6743\u94fe\u63a5',
  saveCode: '\u4fdd\u5b58\u6388\u6743 code',
  preview: '\u9884\u89c8\u6587\u6863',
  importDocs: '\u5bfc\u5165\u9009\u4e2d\u6587\u6863',
  debug: '\u663e\u793a\u8bca\u65ad',
  importedList: '\u5df2\u5bfc\u5165\u6587\u6863',
  folderToken: '\u53ef\u9009\uff1afolder_token',
  maxDocs: '\u6700\u591a\u7bc7\u6570',
  codePlaceholder: '\u7c98\u8d34\u56de\u8c03 URL \u6216 code',
};

export function renderKnowledgePage(): HTMLElement {
  const container = document.createElement('div');
  container.className = 'knowledge-page';
  container.innerHTML = `
    <div class="kp-header">
      <h2>${text.title}</h2>
      <div class="kp-header-actions">
        <button id="kp-scan-btn" class="kp-btn kp-btn-primary">${text.scan}</button>
        <button id="kp-reindex-btn" class="kp-btn kp-btn-secondary">${text.reindex}</button>
        <button id="kp-upload-btn" class="kp-btn kp-btn-secondary">${text.upload}</button>
        <input type="file" id="kp-file-input" multiple accept=".txt,.md,.pdf,.docx,.xlsx,.pptx,.csv,.py,.js,.ts,.yaml,.json" style="display:none" />
      </div>
    </div>

    <div class="kp-stats-row" id="kp-stats">
      ${statCard('kp-stat-chunks', text.chunks)}
      ${statCard('kp-stat-docs', text.docs)}
      ${statCard('kp-stat-dirs', text.dirs)}
      ${statCard('kp-stat-watching', text.watching)}
    </div>

    <div class="kp-section kp-feishu-section">
      <div class="kp-section-head">
        <div>
          <h3>${text.feishuTitle}</h3>
          <p>${text.feishuDesc}</p>
        </div>
        <button id="kp-feishu-auth-btn" class="kp-btn kp-btn-secondary">${text.auth}</button>
      </div>
      <div class="kp-feishu-grid">
        <input type="text" id="kp-feishu-code" class="kp-input" placeholder="${text.codePlaceholder}" />
        <button id="kp-feishu-save-code-btn" class="kp-btn kp-btn-secondary">${text.saveCode}</button>
        <input type="text" id="kp-feishu-folder" class="kp-input" placeholder="${text.folderToken}" />
        <input type="number" id="kp-feishu-max" class="kp-input" min="1" max="1000" value="500" aria-label="${text.maxDocs}" />
        <button id="kp-feishu-preview-btn" class="kp-btn kp-btn-primary">${text.preview}</button>
        <button id="kp-feishu-import-btn" class="kp-btn kp-btn-secondary" disabled>${text.importDocs}</button>
        <button id="kp-feishu-debug-btn" class="kp-btn kp-btn-secondary">${text.debug}</button>
        <label class="kp-checkbox-label" style="grid-column:1/-1"><input type="checkbox" id="kp-feishu-recurse" checked /> 递归遍历子文件夹</label>
        <label class="kp-checkbox-label" style="grid-column:1/-1"><input type="checkbox" id="kp-feishu-include-wiki" /> 包含 Wiki 空间文档（默认仅 Drive）</label>
        <div style="grid-column:1/-1;display:flex;gap:8px">
          <input type="text" id="kp-feishu-search" class="kp-input" placeholder="按文档名称搜索..." style="flex:1" />
          <button id="kp-feishu-search-btn" class="kp-btn kp-btn-secondary" style="width:80px;flex-shrink:0">搜索</button>
        </div>
        <div style="grid-column:1/-1;display:flex;gap:8px">
          <input type="text" id="kp-feishu-direct-url" class="kp-input" placeholder="输入飞书文档 URL，先预览再决定是否导入..." style="flex:1" />
          <button id="kp-feishu-direct-btn" class="kp-btn kp-btn-primary" style="width:80px;flex-shrink:0">查询</button>
        </div>
        <div id="kp-feishu-direct-preview" style="grid-column:1/-1;display:none"></div>
      </div>
      <div id="kp-feishu-status" class="kp-feishu-status"></div>
      <pre id="kp-feishu-debug" class="kp-feishu-debug" style="display:none"></pre>
      <div id="kp-feishu-results" class="kp-feishu-results"></div>
      <div class="kp-feishu-subtitle">${text.importedList}</div>
      <div id="kp-feishu-imported" class="kp-feishu-results"></div>
    </div>

    <div class="kp-search-bar">
      <input type="text" id="kp-search-input" placeholder="${text.searchPlaceholder}" class="kp-search-input" />
      <span class="kp-search-hint">${text.searchHint}</span>
    </div>

    <div id="kp-search-results" class="kp-results"></div>

    <div class="kp-section">
      <h3>${text.monitorDirs}</h3>
      <div id="kp-dirs-list" class="kp-dirs-list">${text.loading}</div>
    </div>

    <div id="kp-scan-result" class="kp-toast" style="display:none"></div>
  `;

  bindEvents(container);
  loadStats(container);
  loadFeishuStatus(container);
  loadFeishuImported(container);
  window.addEventListener('feishu-kb-oauth', ((event: CustomEvent) => {
    if (event.detail?.ok) {
      setFeishuStatus(container, '\u6388\u6743\u5df2\u4fdd\u5b58\uff0c\u53ef\u4ee5\u9884\u89c8\u98de\u4e66\u6587\u6863\u3002');
      loadFeishuStatus(container);
    } else {
      setFeishuStatus(container, '\u6388\u6743\u56de\u8c03\u5904\u7406\u5931\u8d25\uff0c\u8bf7\u91cd\u65b0\u83b7\u53d6\u6388\u6743\u94fe\u63a5\u3002', true);
    }
  }) as EventListener);

  return container;
}

function statCard(id: string, label: string): string {
  return `
    <div class="kp-stat-card">
      <div class="kp-stat-value" id="${id}">--</div>
      <div class="kp-stat-label">${label}</div>
    </div>
  `;
}

function bindEvents(container: HTMLElement): void {
  container.querySelector('#kp-scan-btn')?.addEventListener('click', () => {
    runScan(container, container.querySelector('#kp-scan-btn') as HTMLButtonElement, false);
  });

  container.querySelector('#kp-reindex-btn')?.addEventListener('click', () => {
    runScan(container, container.querySelector('#kp-reindex-btn') as HTMLButtonElement, true);
  });

  container.querySelector('#kp-upload-btn')?.addEventListener('click', () => {
    container.querySelector('#kp-file-input')?.dispatchEvent(new MouseEvent('click'));
  });

  container.querySelector('#kp-file-input')?.addEventListener('change', async (e) => {
    const input = e.target as HTMLInputElement;
    if (!input.files?.length) return;
    for (const file of Array.from(input.files)) {
      const form = new FormData();
      form.append('file', file);
      try {
        const res = await fetch('/api/knowledge/upload', { method: 'POST', body: form });
        const data = await res.json();
        showToast(container, `${file.name} \u5df2\u7d22\u5f15 (${data.chunks} \u5206\u5757)`);
      } catch {
        showToast(container, `${file.name} \u4e0a\u4f20\u5931\u8d25`, true);
      }
    }
    input.value = '';
    loadStats(container);
  });

  container.querySelector('#kp-feishu-auth-btn')?.addEventListener('click', () => openFeishuAuth(container));
  container.querySelector('#kp-feishu-save-code-btn')?.addEventListener('click', () => saveFeishuCode(container));
  container.querySelector('#kp-feishu-preview-btn')?.addEventListener('click', () => previewFeishu(container));
  container.querySelector('#kp-feishu-search-btn')?.addEventListener('click', () => searchFeishu(container));
  container.querySelector('#kp-feishu-direct-btn')?.addEventListener('click', () => directImportFeishu(container));
  container.querySelector('#kp-feishu-search')?.addEventListener('keydown', (e) => {
    if ((e as KeyboardEvent).key === 'Enter') { (e as KeyboardEvent).preventDefault(); searchFeishu(container); }
  });
  container.querySelector('#kp-feishu-import-btn')?.addEventListener('click', () => importFeishu(container));
  container.querySelector('#kp-feishu-debug-btn')?.addEventListener('click', () => showFeishuDebug(container));

  let searchTimeout: ReturnType<typeof setTimeout>;
  container.querySelector('#kp-search-input')?.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => doSearch(container), 400);
  });
}

async function openFeishuAuth(container: HTMLElement): Promise<void> {
  try {
    const redirectUri = 'http://127.0.0.1:8001/app/app_4k9rvfdqrdezp/feishu-oauth-callback';
    appendFeishuDebug(container, 'Step 1: requesting auth URL...');
    const data = await apiGet<{ url: string; scope: string; redirect_uri: string }>(
      `/knowledge/feishu/auth-url?redirect_uri=${encodeURIComponent(redirectUri)}`,
    );
    appendFeishuDebug(container, `Step 1 result:\n${JSON.stringify(data, null, 2)}`);
    window.open(data.url, '_blank', 'noopener,noreferrer');
    setFeishuStatus(container, `\u5df2\u6253\u5f00\u6388\u6743\u9875\u3002Redirect: ${data.redirect_uri}\uff1bScope: ${data.scope}\uff1bAuth URL: ${data.url}`);
  } catch {
    setFeishuStatus(container, '\u751f\u6210\u6388\u6743\u94fe\u63a5\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u98de\u4e66\u914d\u7f6e\u3002', true);
  }
}

async function saveFeishuCode(container: HTMLElement): Promise<void> {
  const input = container.querySelector('#kp-feishu-code') as HTMLInputElement;
  const code = input.value.trim();
  if (!code) {
    setFeishuStatus(container, '\u8bf7\u5148\u7c98\u8d34\u56de\u8c03 URL \u6216 code\u3002', true);
    return;
  }
  try {
    appendFeishuDebug(container, `Step 2: exchanging pasted code or callback URL:\n${code}`);
    await apiPost('/knowledge/feishu/oauth', { code });
    input.value = '';
    setFeishuStatus(container, '\u6388\u6743\u5df2\u4fdd\u5b58\uff0c\u53ef\u4ee5\u9884\u89c8\u98de\u4e66\u6587\u6863\u3002');
    loadFeishuStatus(container);
  } catch (error) {
    appendFeishuDebug(container, `Step 2 error:\n${formatApiError(error)}`);
    setFeishuStatus(container, `\u4fdd\u5b58\u6388\u6743 code \u5931\u8d25\uff1a${formatApiError(error)}`, true);
  }
}

async function previewFeishu(container: HTMLElement): Promise<void> {
  const folder = (container.querySelector('#kp-feishu-folder') as HTMLInputElement).value.trim();
  const maxDocs = Number((container.querySelector('#kp-feishu-max') as HTMLInputElement).value || 20);
  const recurse = (container.querySelector('#kp-feishu-recurse') as HTMLInputElement).checked;
  const includeWiki = (container.querySelector('#kp-feishu-include-wiki') as HTMLInputElement).checked;
  setFeishuStatus(container, '\u6b63\u5728\u8bfb\u53d6\u98de\u4e66\u76ee\u5f55...');
  appendFeishuDebug(container, `Step 3: preview request\nfolder_token=${folder || '(root)'}\nmax_docs=${maxDocs}\nrecurse=${recurse}`);
  try {
    const preview = await apiPost<FeishuPreview>('/knowledge/feishu/preview', {
      folder_token: folder || null,
      max_docs: maxDocs,
      recurse: recurse,
      include_wiki: includeWiki,
    });
    feishuPreviewDocs = preview.docs.filter(doc => !doc.imported);
    feishuPage = 1;
    renderFeishuPreview(container, preview);
    const wikiCount = preview.wiki_total_docs || 0;
    const spaceCount = (preview.wiki_spaces || []).length;
    const wikiExtra = wikiCount ? ` + Wiki(${spaceCount}\u7a7a\u95f4/${wikiCount}\u7bc7)` : '';
    setFeishuStatus(container, `\u627e\u5230 ${preview.total_docs} \u7bc7\u6587\u6863\uff08Drive${wikiExtra}\uff09\uff0c\u672a\u5bfc\u5165 ${feishuPreviewDocs.length} \u7bc7\u3002`);
  } catch (error) {
    appendFeishuDebug(container, `Step 3 error:\n${formatApiError(error)}`);
    feishuPreviewDocs = [];
    (container.querySelector('#kp-feishu-import-btn') as HTMLButtonElement).disabled = true;
    setFeishuStatus(container, `\u9884\u89c8\u5931\u8d25\uff1a${formatApiError(error)}`, true);
  }
}

async function searchFeishu(container: HTMLElement): Promise<void> {
  const query = (container.querySelector('#kp-feishu-search') as HTMLInputElement).value.trim();
  if (!query) {
    setFeishuStatus(container, '请输入搜索关键词。', true);
    return;
  }
  const maxDocs = Number((container.querySelector('#kp-feishu-max') as HTMLInputElement).value || 200);
  setFeishuStatus(container, `正在搜索：${query}...`);
  try {
    const data = await apiGet<{ query: string; docs: FeishuDoc[]; total: number }>(
      `/knowledge/feishu/search?q=${encodeURIComponent(query)}&max_docs=${maxDocs}`,
    );
    feishuPreviewDocs = data.docs.filter(doc => !doc.imported);
    feishuPage = 1;
    renderFeishuPreviewDocs(container);
    setFeishuStatus(container, `搜索「${query}」找到 ${data.total} 篇文档，未导入 ${feishuPreviewDocs.length} 篇。`);
  } catch (error) {
    setFeishuStatus(container, `搜索失败：${formatApiError(error)}`, true);
  }
}

let directPreviewUrl = '';
let directPreviewName = '';

async function directImportFeishu(container: HTMLElement): Promise<void> {
  const input = container.querySelector('#kp-feishu-direct-url') as HTMLInputElement;
  const url = input.value.trim();
  if (!url) {
    setFeishuStatus(container, '请先粘贴飞书文档 URL。', true);
    return;
  }
  const panel = container.querySelector('#kp-feishu-direct-preview') as HTMLElement;
  setFeishuStatus(container, '正在读取文档...');
  try {
    // First check if already imported
    const imported = await apiGet<{ docs: Array<{ url: string; name: string; chunks: number; imported_at: number }> }>('/knowledge/feishu/imported');
    const already = imported.docs.find((d: { url: string }) => d.url === url);

    const data = await apiPost<{ name: string; url: string; preview: string; content_length: number; truncated: boolean; unsupported_type?: string }>(
      '/knowledge/feishu/doc-preview',
      { url, name: '' },
    );
    directPreviewUrl = url;
    directPreviewName = data.name || url.split('/').pop() || '飞书文档';

    let actionHtml = '';
    if (already) {
      actionHtml = `<div style="margin-top:10px;color:#059669;font-weight:600">已导入 · ${already.chunks} 个分块 · ${new Date(already.imported_at * 1000).toLocaleString('zh-CN')}</div>`;
    } else {
      actionHtml = `<div style="margin-top:10px;display:flex;gap:8px">
          <button id="kp-feishu-do-import" class="kp-btn kp-btn-primary">导入到知识库</button>
          <span id="kp-feishu-import-result" style="font-size:0.85rem;align-self:center"></span>
        </div>`;
    }

    panel.innerHTML = `
      <div class="kp-feishu-content-preview">
        <div class="kp-feishu-content-head">
          <strong>${esc(directPreviewName)}</strong>
          ${already ? '<span class="kp-wiki-badge" style="background:#d1fae5;color:#065f46">已导入</span>' : ''}
          <span>${data.content_length} 字${data.truncated ? ' · 已截断' : ''}</span>
        </div>
        <pre>${esc(data.preview)}</pre>
        ${actionHtml}
      </div>
    `;
    panel.style.display = 'block';
    if (!already) {
      panel.querySelector('#kp-feishu-do-import')?.addEventListener('click', () => doImportDirect(container));
    }
    setFeishuStatus(container, `已读取：${directPreviewName}（${data.content_length} 字）${already ? ' · 已导入过' : ''}`);
  } catch (error) {
    panel.style.display = 'none';
    setFeishuStatus(container, `读取失败：${formatApiError(error)}`, true);
  }
}

async function doImportDirect(container: HTMLElement): Promise<void> {
  if (!directPreviewUrl) return;
  const resultSpan = container.querySelector('#kp-feishu-import-result') as HTMLElement;
  const btn = container.querySelector('#kp-feishu-do-import') as HTMLButtonElement;
  if (btn) { btn.disabled = true; btn.textContent = '导入中...'; }
  try {
    const data = await apiPost<{ ok: boolean; title: string; chunks: number; content_length: number }>(
      '/knowledge/feishu/direct-import',
      { url: directPreviewUrl },
    );
    if (resultSpan) resultSpan.textContent = `已导入，${data.chunks} 个分块`;
    if (btn) { btn.remove(); }
    setFeishuStatus(container, `已导入：${data.title}`);
  } catch (error) {
    if (resultSpan) resultSpan.textContent = `导入失败：${formatApiError(error)}`;
    if (btn) { btn.disabled = false; btn.textContent = '重试导入'; }
  }
}

async function showFeishuDebug(container: HTMLElement): Promise<void> {
  try {
    const data = await apiGet('/knowledge/_feishu/debug');
    appendFeishuDebug(container, `Debug state:\n${JSON.stringify(data, null, 2)}`);
  } catch (error) {
    appendFeishuDebug(container, `Debug error:\n${formatApiError(error)}`);
  }
}

async function importFeishu(container: HTMLElement): Promise<void> {
  const docs = selectedFeishuDocs(container);
  if (!docs.length) {
    setFeishuStatus(container, '\u8bf7\u5148\u9009\u62e9\u8981\u5bfc\u5165\u7684\u6587\u6863\u3002', true);
    return;
  }
  setFeishuStatus(container, '\u6b63\u5728\u5bfc\u5165\u98de\u4e66\u6587\u6863...');
  try {
    const result = await apiPost<FeishuImportResult>('/knowledge/feishu/import', { docs });
    const failed = result.failures.length ? `\uff0c\u5931\u8d25 ${result.failures.length} \u7bc7` : '';
    setFeishuStatus(container, `\u5bfc\u5165\u5b8c\u6210\uff1a\u6210\u529f ${result.successes.length} \u7bc7${failed}\u3002`);
    const importedNames = new Set(result.successes.map(item => item.name));
    feishuPreviewDocs = feishuPreviewDocs.filter(doc => !importedNames.has(doc.name));
    if ((feishuPage - 1) * FEISHU_PAGE_SIZE >= feishuPreviewDocs.length) {
      feishuPage = Math.max(1, feishuPage - 1);
    }
    renderFeishuPreviewDocs(container);
    renderFeishuImportResult(container, result);
    loadFeishuImported(container);
    loadStats(container);
  } catch (error) {
    setFeishuStatus(container, `\u5bfc\u5165\u5931\u8d25\uff1a${formatApiError(error)}`, true);
  }
}

async function loadFeishuStatus(container: HTMLElement): Promise<void> {
  try {
    const data = await apiGet<{ authorized: boolean; scope: string }>('/knowledge/feishu/status');
    setFeishuStatus(container, data.authorized
      ? `\u5df2\u6388\u6743\u3002Scope: ${data.scope}`
      : `\u672a\u6388\u6743\u3002Scope: ${data.scope}`);
  } catch {
    setFeishuStatus(container, '\u65e0\u6cd5\u83b7\u53d6\u98de\u4e66\u5bfc\u5165\u72b6\u6001\u3002', true);
  }
}

async function loadFeishuImported(container: HTMLElement): Promise<void> {
  const target = container.querySelector('#kp-feishu-imported');
  if (!target) return;
  try {
    const data = await apiGet<{ docs: FeishuImportedDoc[]; count: number }>('/knowledge/feishu/imported');
    if (!data.docs.length) {
      target.innerHTML = '<div class="kp-empty">\u6682\u65e0\u5df2\u5bfc\u5165\u98de\u4e66\u6587\u6863</div>';
      return;
    }
    target.innerHTML = data.docs.slice(0, 20).map(doc => `
      <div class="kp-feishu-item">
        <span>${esc(doc.name)}</span>
        <code>${doc.chunks} chunks</code>
      </div>
    `).join('');
  } catch {
    target.innerHTML = '<div class="kp-empty">\u5df2\u5bfc\u5165\u5217\u8868\u52a0\u8f7d\u5931\u8d25</div>';
  }
}

function renderFeishuPreview(container: HTMLElement, preview: FeishuPreview): void {
  feishuPreviewDocs = preview.docs.filter(doc => !doc.imported);
  renderFeishuPreviewDocs(container, preview);
}

function renderFeishuPreviewDocs(container: HTMLElement, preview?: FeishuPreview): void {
  const target = container.querySelector('#kp-feishu-results');
  if (!target) return;
  const totalPages = Math.max(1, Math.ceil(feishuPreviewDocs.length / FEISHU_PAGE_SIZE));
  feishuPage = Math.min(Math.max(1, feishuPage), totalPages);
  const start = (feishuPage - 1) * FEISHU_PAGE_SIZE;
  const pageDocs = feishuPreviewDocs.slice(start, start + FEISHU_PAGE_SIZE);
  const pager = feishuPreviewDocs.length ? `
    <div class="kp-feishu-pager">
      <button class="kp-btn kp-btn-secondary" id="kp-feishu-prev-page" ${feishuPage <= 1 ? 'disabled' : ''}>\u4e0a\u4e00\u9875</button>
      <span>\u7b2c ${feishuPage} / ${totalPages} \u9875\uff0c\u5171 ${feishuPreviewDocs.length} \u7bc7\u672a\u5bfc\u5165</span>
      <button class="kp-btn kp-btn-secondary" id="kp-feishu-next-page" ${feishuPage >= totalPages ? 'disabled' : ''}>\u4e0b\u4e00\u9875</button>
    </div>
  ` : '';
  const docs = pageDocs.map((doc, offset) => {
    const idx = start + offset;
    return `
    <label class="kp-feishu-item kp-feishu-selectable">
      <input type="checkbox" class="kp-feishu-doc-check" data-index="${idx}" />
      <span>${idx + 1}. ${esc(doc.name)} ${(doc as any).source_type === 'wiki' ? '<span class="kp-wiki-badge">Wiki</span>' : ''}</span>
      ${doc.imported ? `<small>\u5df2\u5bfc\u5165 ${esc(doc.imported_at || '')}</small>` : ''}
      <code>${esc(doc.type || '')}</code>
      <button type="button" class="kp-btn kp-btn-secondary kp-feishu-preview-doc" data-index="${idx}">\u9884\u89c8</button>
    </label>
  `;
  }).join('');
  const folders = preview?.folders.length
    ? `<div class="kp-feishu-subtitle">\u5b50\u6587\u4ef6\u5939 (${preview.folders.length})</div>${preview.folders.slice(0, 8).map(f => `<div class="kp-feishu-folder"><span>${esc(f.name)}</span><code>${esc(f.token)}</code></div>`).join('')}`
    : '';
  const wikiSpaces = preview?.wiki_spaces?.length
    ? `<div class="kp-feishu-subtitle">Wiki \u7a7a\u95f4 (${preview.wiki_spaces.length})</div>${preview.wiki_spaces.slice(0, 10).map(s => `<div class="kp-feishu-folder"><span>${esc(s.name)}</span><code>${esc(s.space_id)}</code></div>`).join('')}`
    : '';
  target.innerHTML = `${pager}${wikiSpaces || ''}${folders || ''}${docs || '<div class="kp-empty">\u6ca1\u6709\u672a\u5bfc\u5165\u6587\u6863</div>'}`;
  target.innerHTML += folders;
  target.querySelector('#kp-feishu-prev-page')?.addEventListener('click', () => {
    feishuPage -= 1;
    renderFeishuPreviewDocs(container);
  });
  target.querySelector('#kp-feishu-next-page')?.addEventListener('click', () => {
    feishuPage += 1;
    renderFeishuPreviewDocs(container);
  });
  target.querySelectorAll('.kp-feishu-doc-check').forEach((input) => {
    input.addEventListener('change', () => updateFeishuImportButton(container));
  });
  target.querySelectorAll('.kp-feishu-preview-doc').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const idx = Number((event.currentTarget as HTMLElement).dataset.index);
      previewFeishuDocContent(container, feishuPreviewDocs[idx]);
    });
  });
  updateFeishuImportButton(container);
}

async function previewFeishuDocContent(container: HTMLElement, doc?: FeishuDoc): Promise<void> {
  if (!doc) return;
  const target = container.querySelector('#kp-feishu-results');
  if (!target) return;
  setFeishuStatus(container, `\u6b63\u5728\u9884\u89c8\uff1a${doc.name}`);
  try {
    const data = await apiPost<FeishuDocContentPreview>('/knowledge/feishu/doc-preview', {
      url: doc.url,
      name: doc.name,
    });
    const existing = target.querySelector('.kp-feishu-content-preview');
    existing?.remove();
    const panel = document.createElement('div');
    panel.className = 'kp-feishu-content-preview';
    panel.innerHTML = `
      <div class="kp-feishu-content-head">
        <strong>${esc(doc.name)}</strong>
        <span>${data.content_length} chars${data.truncated ? ' · truncated' : ''}</span>
      </div>
      <pre>${esc(data.preview)}</pre>
    `;
    target.prepend(panel);
    setFeishuStatus(container, `\u5df2\u9884\u89c8\uff1a${doc.name}`);
  } catch (error) {
    setFeishuStatus(container, `\u9884\u89c8\u6587\u6863\u5931\u8d25\uff1a${formatApiError(error)}`, true);
  }
}

function selectedFeishuDocs(container: HTMLElement): FeishuDoc[] {
  return Array.from(container.querySelectorAll<HTMLInputElement>('.kp-feishu-doc-check:checked'))
    .map(input => feishuPreviewDocs[Number(input.dataset.index)])
    .filter((doc): doc is FeishuDoc => Boolean(doc));
}

function updateFeishuImportButton(container: HTMLElement): void {
  const btn = container.querySelector('#kp-feishu-import-btn') as HTMLButtonElement | null;
  if (!btn) return;
  const count = selectedFeishuDocs(container).length;
  btn.disabled = count === 0;
  btn.textContent = count ? `\u5bfc\u5165\u9009\u4e2d\u6587\u6863 (${count})` : text.importDocs;
}

function renderFeishuImportResult(container: HTMLElement, result: FeishuImportResult): void {
  const target = container.querySelector('#kp-feishu-results');
  if (!target) return;
  const successes = result.successes.map(s => `<div class="kp-feishu-item"><span>${esc(s.name)}</span><code>${s.chunks} chunks</code></div>`).join('');
  const failures = result.failures.map(f => `<div class="kp-feishu-error"><span>${esc(f.name)}</span><small>${esc(f.reason)}</small></div>`).join('');
  target.innerHTML = `${successes}${failures}`;
}

function setFeishuStatus(container: HTMLElement, message: string, isError = false): void {
  const el = container.querySelector('#kp-feishu-status');
  if (!el) return;
  el.textContent = message;
  el.className = `kp-feishu-status ${isError ? 'kp-feishu-status-error' : ''}`;
}

function appendFeishuDebug(container: HTMLElement, message: string): void {
  const el = container.querySelector('#kp-feishu-debug') as HTMLElement | null;
  if (!el) return;
  const timestamp = new Date().toLocaleTimeString();
  el.style.display = 'block';
  el.textContent = `${el.textContent ? `${el.textContent}\n\n` : ''}[${timestamp}] ${message}`;
}

function formatApiError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error || '\u672a\u77e5\u9519\u8bef');
}

async function runScan(container: HTMLElement, btn: HTMLButtonElement, force: boolean): Promise<void> {
  const originalText = btn.textContent || (force ? text.reindex : text.scan);
  btn.disabled = true;
  btn.textContent = force ? '\u91cd\u5efa\u4e2d...' : '\u626b\u63cf\u4e2d...';
  try {
    if (force) {
      const task = await apiPost<ScanTaskStatus>('/knowledge/scan?force=true&background=true');
      await pollScanTask(container, task.task_id);
    } else {
      const result = await apiPost<ScanResult>('/knowledge/scan');
      showToast(container, formatScanResult(result, force), result.status !== 'ok' || result.errors > 0);
      loadStats(container);
    }
  } catch {
    showToast(container, force ? '\u91cd\u5efa\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u670d\u52a1' : '\u626b\u63cf\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u670d\u52a1', true);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function pollScanTask(container: HTMLElement, taskId: string): Promise<void> {
  while (true) {
    const task = await apiGet<ScanTaskStatus>(`/knowledge/scan/${taskId}`);
    if (task.state === 'running') {
      showToast(container, formatScanProgress(task), false, true);
      await delay(1500);
      continue;
    }
    showToast(container, formatScanTaskResult(task), task.state === 'failed' || task.errors > 0);
    loadStats(container);
    return;
  }
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function formatScanProgress(task: ScanTaskStatus): string {
  const total = task.total_files || task.scanned || 0;
  const progress = total ? `${task.scanned}/${total}` : String(task.scanned || 0);
  const name = task.current_file ? task.current_file.split(/[\\/]/).pop() : '';
  return `\u91cd\u5efa\u4e2d ${progress}\uff0c\u5df2\u91cd\u5efa ${task.reindexed || 0}\uff0c\u5931\u8d25 ${task.errors || 0}${name ? `\uff0c\u5f53\u524d ${name}` : ''}`;
}

function formatScanTaskResult(task: ScanTaskStatus): string {
  if (task.state === 'failed' && task.status !== 'ok') {
    return task.error || formatScanResult(task, task.force);
  }
  return formatScanResult(task, task.force);
}

function formatScanResult(result: ScanResult, force: boolean): string {
  if (result.status === 'no_dirs') return '\u672a\u914d\u7f6e\u76d1\u63a7\u76ee\u5f55\uff0c\u8bf7\u5148\u8bbe\u7f6e WATCH_DIRS';
  if (result.status === 'rag_not_ready') return 'RAG \u670d\u52a1\u672a\u5c31\u7eea\uff0c\u8bf7\u68c0\u67e5\u6a21\u578b\u548c API Key \u914d\u7f6e';
  if (result.status === 'busy') return '\u5df2\u6709\u7d22\u5f15\u4efb\u52a1\u6b63\u5728\u8fd0\u884c\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5';
  if (force) return `\u91cd\u5efa\u5b8c\u6210: \u626b\u63cf ${result.scanned}, \u91cd\u5efa ${result.reindexed}, \u5931\u8d25 ${result.errors}, \u5f53\u524d\u6587\u6863 ${result.unique_docs}`;
  if (result.added === 0 && result.updated === 0 && result.deleted === 0 && result.errors === 0) {
    return `\u626b\u63cf\u5b8c\u6210: \u65e0\u6587\u4ef6\u53d8\u5316\uff0c\u8df3\u8fc7 ${result.skipped}/${result.scanned} \u4e2a\u6587\u4ef6`;
  }
  return `\u626b\u63cf\u5b8c\u6210: \u65b0\u589e ${result.added}, \u66f4\u65b0 ${result.updated}, \u5220\u9664 ${result.deleted}, \u5931\u8d25 ${result.errors}`;
}

async function loadStats(container: HTMLElement): Promise<void> {
  try {
    const stats = await apiGet<KnowledgeStats>('/knowledge/stats');
    setText(container, '#kp-stat-chunks', String(stats.total_chunks));
    setText(container, '#kp-stat-docs', String(stats.unique_docs));
    setText(container, '#kp-stat-dirs', String(stats.watch_dirs.length));
    setText(container, '#kp-stat-watching', stats.is_watching ? '\u8fd0\u884c\u4e2d' : '\u672a\u542f\u52a8');

    const dirsList = container.querySelector('#kp-dirs-list');
    if (dirsList) {
      dirsList.innerHTML = stats.watch_dirs.length
        ? stats.watch_dirs.map(d => `<div class="kp-dir-item">${esc(d)}</div>`).join('')
        : '<div class="kp-empty">\u672a\u914d\u7f6e\u76d1\u63a7\u76ee\u5f55\uff0c\u8bf7\u5728 .env \u4e2d\u8bbe\u7f6e WATCH_DIRS</div>';
    }
  } catch {
    setText(container, '#kp-stat-chunks', '\u4e0d\u53ef\u7528');
  }
}

async function doSearch(container: HTMLElement): Promise<void> {
  const input = container.querySelector('#kp-search-input') as HTMLInputElement;
  const query = input.value.trim();
  const resultsDiv = container.querySelector('#kp-search-results');
  if (!resultsDiv) return;
  if (!query) {
    resultsDiv.innerHTML = '';
    return;
  }

  try {
    const data = await apiGet<{ results: KnowledgeResult[] }>(`/knowledge/search?q=${encodeURIComponent(query)}`);
    if (!data.results.length) {
      resultsDiv.innerHTML = '<div class="kp-empty">\u672a\u627e\u5230\u76f8\u5173\u5185\u5bb9</div>';
      return;
    }
    resultsDiv.innerHTML = data.results.map(r => `
      <div class="kp-result-item">
        <div class="kp-result-header">
          <span class="kp-result-source">${esc(String(r.metadata.source || '\u672a\u77e5\u6765\u6e90'))}</span>
          <span class="kp-result-score">\u76f8\u5173\u5ea6 ${(r.score * 100).toFixed(0)}%</span>
        </div>
        <div class="kp-result-content">${esc(r.content.substring(0, 300))}${r.content.length > 300 ? '...' : ''}</div>
      </div>
    `).join('');
  } catch {
    resultsDiv.innerHTML = '<div class="kp-empty">\u641c\u7d22\u5931\u8d25</div>';
  }
}

function showToast(container: HTMLElement, message: string, isError = false, persist = false): void {
  const toast = container.querySelector('#kp-scan-result') as HTMLElement;
  if (!toast) return;
  if (toastTimer) clearTimeout(toastTimer);
  toast.textContent = message;
  toast.className = `kp-toast ${isError ? 'kp-toast-error' : 'kp-toast-success'}`;
  toast.style.display = 'block';
  if (!persist) {
    toastTimer = setTimeout(() => { toast.style.display = 'none'; }, 6000);
  }
}

function setText(container: HTMLElement, selector: string, value: string): void {
  const el = container.querySelector(selector);
  if (el) el.textContent = value;
}

function esc(s: string): string {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

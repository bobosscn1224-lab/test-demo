/** Personal Work Platform — top navigation + content area layout. */

import { renderTopNav, getActivePage } from './components/TopNav';
import { renderChatWindow } from './components/ChatWindow';
import { renderKnowledgePage } from './components/KnowledgePage';
import { renderSkillsPage } from './components/SkillsPage';
import { renderBatchPptxPage } from './components/BatchPptxPage';
import { renderReportPage } from './components/ReportPage';
import { renderImageGenPage } from './components/ImageGenPage';
import { renderPptMakerPage } from './components/ppt-maker/index';
import { renderAssetManagePage } from './components/AssetManagePage';
import { renderVideoGenPage } from './components/VideoGenPage';
import { renderProModePage } from './components/pro-mode/index';
import { apiPost } from './services/api';

const panels: Record<string, { el: HTMLElement; render: () => HTMLElement }> = {};
let pendingPage = '';

// ── Global error boundary ─────────────────────────────────────
window.addEventListener('error', (e) => {
  const msg = e.target instanceof HTMLElement ? 'Resource error' : e.message;
  const existing = document.getElementById('global-error-toast');
  if (existing) existing.remove();
  const toast = document.createElement('div');
  toast.id = 'global-error-toast';
  toast.style.cssText =
    'position:fixed;bottom:16px;right:16px;background:#e74c3c;color:#fff;padding:12px 20px;border-radius:8px;z-index:9999;font-size:14px;max-width:400px;cursor:pointer';
  toast.textContent = 'Unexpected error: ' + msg;
  toast.onclick = () => toast.remove();
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 8000);
});

export function renderApp(): HTMLElement {
  const container = document.createElement('div');
  container.className = 'app-container';
  container.style.cssText = 'display:flex;flex-direction:column;height:100vh;overflow:hidden;';

  // ── Top navigation bar ──────────────────────────────────────
  container.appendChild(renderTopNav());

  // ── Content area (below nav) ────────────────────────────────
  const contentArea = document.createElement('div');
  contentArea.id = 'content-area';
  contentArea.style.cssText = 'flex:1;overflow:hidden;min-height:0;';
  container.appendChild(contentArea);

  // ── Handle Feishu OAuth return ──────────────────────────────
  handleFeishuOAuthReturn();

  // ── Default: chat page ──────────────────────────────────────
  switchPage(pendingPage || 'chat', contentArea);

  // ── Listen for navigation events ────────────────────────────
  window.addEventListener('navigate', ((e: CustomEvent) => {
    switchPage(e.detail.page, contentArea);
  }) as EventListener);

  return container;
}

function handleFeishuOAuthReturn(): void {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  const state = params.get('state');
  if (!code || state !== 'knowledge_feishu_import') return;

  pendingPage = 'knowledge';
  apiPost('/knowledge/feishu/oauth', { code })
    .then(() => {
      window.dispatchEvent(new CustomEvent('feishu-kb-oauth', { detail: { ok: true } }));
    })
    .catch(() => {
      window.dispatchEvent(new CustomEvent('feishu-kb-oauth', { detail: { ok: false } }));
    });

  window.history.replaceState({}, document.title, window.location.pathname);
}

// ── Page registry ────────────────────────────────────────────

const PAGE_REGISTRY: Record<string, () => HTMLElement> = {
  chat:      renderChatWindow,
  knowledge: renderKnowledgePage,
  skills:    renderSkillsPage,
  pptx:      renderBatchPptxPage,
  report:    renderReportPage,
  'image-gen': renderImageGenPage,
  'ppt-maker': renderPptMakerPage,
  'asset-manage': renderAssetManagePage,
  'video-gen': renderVideoGenPage,
  'pro-mode': renderProModePage,
};

function switchPage(page: string, contentArea: HTMLElement): void {
  // Hide all panels
  Object.values(panels).forEach(p => { p.el.style.display = 'none'; });

  // Create panel lazily on first visit
  if (!panels[page]) {
    const renderFn = PAGE_REGISTRY[page];
    if (!renderFn) return;

    const panel = document.createElement('div');
    panel.className = 'page-panel';
    panel.id = 'page-' + page;
    panel.style.cssText = 'width:100%;height:100%;overflow:hidden;display:flex;flex-direction:column;';
    panel.appendChild(renderFn());
    contentArea.appendChild(panel);
    panels[page] = { el: panel, render: renderFn };
  }

  // Show target panel — chat uses flex column layout
  panels[page].el.style.display = 'flex';
}

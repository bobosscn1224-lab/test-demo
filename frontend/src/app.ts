import { renderSidebar } from './components/Sidebar';
import { renderChatWindow } from './components/ChatWindow';
import { renderAvatar } from './components/AvatarDisplay';
import { renderKnowledgePage } from './components/KnowledgePage';
import { renderSkillsPage } from './components/SkillsPage';
import { apiPost } from './services/api';

const panels: Record<string, HTMLElement> = {};
let pendingPage = '';

export function renderApp(): HTMLElement {
  const container = document.createElement('div');
  container.className = 'flex h-screen bg-white';

  // Sidebar
  container.appendChild(renderSidebar());

  // Main content area
  const main = document.createElement('div');
  main.className = 'flex-1 flex flex-col';
  main.id = 'main-content';

  // Header with avatar
  const header = document.createElement('div');
  header.className = 'py-3 flex flex-col items-center border-b border-gray-100 bg-white';
  header.id = 'avatar-container';
  main.appendChild(header);

  renderAvatar(header, 'idle');

  // Content area that switches based on navigation
  const contentArea = document.createElement('div');
  contentArea.className = 'flex-1 overflow-hidden flex flex-col';
  contentArea.id = 'content-area';
  main.appendChild(contentArea);

  // Pre-create chat panel (default)
  const chatPanel = createPanel('chat');
  chatPanel.appendChild(renderChatWindow());
  contentArea.appendChild(chatPanel);

  container.appendChild(main);

  handleFeishuOAuthReturn();

  // Default page: chat
  switchPage(pendingPage || 'chat', contentArea, header);

  // Listen for navigation events from sidebar
  window.addEventListener('navigate', ((e: CustomEvent) => {
    switchPage(e.detail.page, contentArea, header);
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

function createPanel(name: string): HTMLElement {
  const el = document.createElement('div');
  el.className = 'page-panel';
  el.id = 'page-' + name;
  el.style.display = 'none';
  el.style.flex = '1';
  el.style.minHeight = '0';
  el.style.overflow = 'hidden';
  panels[name] = el;
  return el;
}

function switchPage(page: string, contentArea: HTMLElement, header: HTMLElement): void {
  // Hide all panels
  Object.values(panels).forEach(p => p.style.display = 'none');

  // Create panel lazily on first visit
  if (!panels[page]) {
    const panel = createPanel(page);
    switch (page) {
      case 'chat':
        panel.appendChild(renderChatWindow());
        break;
      case 'knowledge':
        panel.appendChild(renderKnowledgePage());
        break;
      case 'skills':
        panel.appendChild(renderSkillsPage());
        break;
    }
    contentArea.appendChild(panel);
  }

  // Show only the requested panel — chat uses flex layout to pin input at bottom
  panels[page].style.display = page === 'chat' ? 'flex' : 'block';
  panels[page].style.flexDirection = page === 'chat' ? 'column' : '';
  header.style.display = page === 'chat' ? '' : 'none';
}

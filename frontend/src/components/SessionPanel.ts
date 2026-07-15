/** Collapsible session panel — embedded inside Chat page. */

import { apiGet, apiDelete } from '../services/api';
import type { Session, Message } from '../types';

const PANEL_WIDTH = 260;
const COLLAPSED_WIDTH = 36;

let _currentSessionId: string | null = null;
let _expanded = true;

export function getSessionId(): string | null {
  return _currentSessionId;
}

export function setSessionId(sid: string | null): void {
  _currentSessionId = sid;
}

export function renderSessionPanel(): HTMLElement {
  const container = document.createElement('div');
  container.id = 'session-panel';
  container.style.cssText =
    `width:${PANEL_WIDTH}px;min-width:${PANEL_WIDTH}px;` +
    'background:#f9fafb;border-right:1px solid #e5e7eb;' +
    'display:flex;flex-direction:column;transition:width 0.2s,min-width 0.2s;overflow:hidden;';

  // Toggle button
  const toggleBtn = document.createElement('button');
  toggleBtn.id = 'session-panel-toggle';
  toggleBtn.textContent = '☰';
  toggleBtn.title = '折叠会话列表';
  toggleBtn.style.cssText =
    'border:none;background:transparent;color:#9ca3af;cursor:pointer;' +
    'font-size:16px;padding:8px 10px;text-align:left;flex-shrink:0;';
  toggleBtn.addEventListener('click', () => togglePanel(container));
  container.appendChild(toggleBtn);

  // New chat button
  const newChatBtn = document.createElement('button');
  newChatBtn.id = 'session-panel-new';
  newChatBtn.textContent = '+ 新对话';
  newChatBtn.style.cssText =
    'margin:4px 8px;padding:8px 12px;background:#4f46e5;color:#fff;border:none;' +
    'border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;flex-shrink:0;';
  newChatBtn.addEventListener('click', () => {
    _currentSessionId = null;
    window.dispatchEvent(new CustomEvent('chat-clear'));
    highlightSession(container, null);
  });
  container.appendChild(newChatBtn);

  // Session list (scrollable)
  const list = document.createElement('div');
  list.id = 'session-list';
  list.style.cssText = 'flex:1;overflow-y:auto;min-height:0;';
  container.appendChild(list);

  // Footer actions
  const footer = document.createElement('div');
  footer.style.cssText =
    'border-top:1px solid #e5e7eb;padding:6px 8px;flex-shrink:0;display:flex;gap:4px;';
  footer.innerHTML = `
    <button id="clear-chat-btn" style="flex:1;padding:6px;border:none;background:transparent;
      color:#9ca3af;font-size:12px;cursor:pointer;border-radius:6px;"
      onmouseover="this.style.background='#f3f4f6';this.style.color='#6b7280';"
      onmouseout="this.style.background='transparent';this.style.color='#9ca3af';">
      清空对话</button>`;
  container.appendChild(footer);

  // Bind clear button
  footer.querySelector('#clear-chat-btn')?.addEventListener('click', () => {
    _currentSessionId = null;
    window.dispatchEvent(new CustomEvent('chat-clear'));
    highlightSession(container, null);
  });

  // Load sessions
  loadSessions(container);

  // Listen for external events
  window.addEventListener('sessions-updated', ((e: CustomEvent) => {
    renderList(container, e.detail as Session[]);
  }) as EventListener);

  return container;
}

function togglePanel(container: HTMLElement): void {
  _expanded = !_expanded;
  const w = _expanded ? PANEL_WIDTH : COLLAPSED_WIDTH;
  container.style.width = `${w}px`;
  container.style.minWidth = `${w}px`;

  const toggle = container.querySelector('#session-panel-toggle') as HTMLElement;
  if (toggle) {
    toggle.textContent = _expanded ? '☰' : '▶';
    toggle.title = _expanded ? '折叠会话列表' : '展开会话列表';
  }

  const newBtn = container.querySelector('#session-panel-new') as HTMLElement;
  if (newBtn) {
    newBtn.textContent = _expanded ? '+ 新对话' : '+';
    newBtn.style.padding = _expanded ? '8px 12px' : '8px 6px';
    newBtn.style.fontSize = _expanded ? '13px' : '11px';
  }

  const footer = container.querySelector('#clear-chat-btn') as HTMLElement;
  if (footer) footer.style.display = _expanded ? '' : 'none';
}

async function loadSessions(container: HTMLElement): Promise<void> {
  try {
    const sessions = await apiGet<Session[]>('/sessions');
    renderList(container, sessions);
  } catch {
    const list = container.querySelector('#session-list');
    if (list) list.innerHTML = '<div style="padding:16px;text-align:center;color:#9ca3af;font-size:13px;">暂无对话</div>';
  }
}

function renderList(container: HTMLElement, sessions: Session[]): void {
  const list = container.querySelector('#session-list');
  if (!list) return;

  if (!sessions.length) {
    list.innerHTML = '<div style="padding:16px;text-align:center;color:#9ca3af;font-size:13px;">暂无对话</div>';
    return;
  }

  list.innerHTML = sessions.map(s =>
    `<div class="session-item" data-sid="${s.id}" style="
      padding:8px 12px;cursor:pointer;font-size:13px;color:#374151;
      border-bottom:1px solid #f3f4f6;transition:background 0.1s;
      display:flex;align-items:center;justify-content:space-between;
      ${s.id === _currentSessionId ? 'background:#eef2ff;border-left:3px solid #4f46e5;' : 'border-left:3px solid transparent;'}
    ">
      <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;">${escHtml(s.title)}</span>
      <button class="del-session-btn" data-sid="${s.id}" style="
        opacity:0;border:none;background:transparent;color:#d1d5db;cursor:pointer;
        font-size:14px;padding:2px 4px;border-radius:4px;"
        onmouseover="this.style.color='#ef4444';this.style.background='#fee2e2';"
        onmouseout="this.style.color='#d1d5db';this.style.background='transparent';"
      >×</button>
    </div>`
  ).join('');

  // Click: load session
  list.querySelectorAll('.session-item').forEach(row => {
    row.addEventListener('click', async (e) => {
      const tgt = e.target as HTMLElement;
      if (tgt.closest('.del-session-btn')) return;
      const sid = (row as HTMLElement).dataset.sid!;
      _currentSessionId = sid;
      highlightSession(container, sid);
      try {
        const data = await apiGet<{ messages: Message[] }>('/sessions/' + sid);
        window.dispatchEvent(new CustomEvent('chat-load', {
          detail: { messages: data.messages || [], sessionId: sid }
        }));
      } catch { /* ignore */ }
    });

    // Hover: show delete button
    row.addEventListener('mouseenter', () => {
      const btn = row.querySelector('.del-session-btn') as HTMLElement;
      if (btn) btn.style.opacity = '1';
    });
    row.addEventListener('mouseleave', () => {
      const btn = row.querySelector('.del-session-btn') as HTMLElement;
      if (btn) btn.style.opacity = '0';
    });
  });

  // Delete
  list.querySelectorAll('.del-session-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const sid = (btn as HTMLElement).dataset.sid!;
      try {
        await apiDelete('/sessions/' + sid);
        if (_currentSessionId === sid) {
          _currentSessionId = null;
          window.dispatchEvent(new CustomEvent('chat-clear'));
        }
        loadSessions(container);
      } catch { /* ignore */ }
    });
  });
}

export function highlightSession(container: HTMLElement, sid: string | null): void {
  container.querySelectorAll('.session-item').forEach(row => {
    const isActive = (row as HTMLElement).dataset.sid === sid;
    (row as HTMLElement).style.background = isActive ? '#eef2ff' : '';
    (row as HTMLElement).style.borderLeft = isActive ? '3px solid #4f46e5' : '3px solid transparent';
  });
}

function escHtml(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

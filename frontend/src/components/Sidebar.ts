import { apiGet, apiDelete } from '../services/api';
import type { Session, Message } from '../types';

let currentSessionId: string | null = null;

export function renderSidebar(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'w-64 bg-gray-50 border-r border-gray-200 flex flex-col h-full';

  el.innerHTML = `
    <div class="p-4 border-b border-gray-200">
      <div class="sidebar-nav">
        <button class="sidebar-nav-item active" data-page="chat">对话</button>
        <button class="sidebar-nav-item" data-page="knowledge">知识库</button>
        <button class="sidebar-nav-item" data-page="skills">技能</button>
      </div>
    </div>
    <div class="p-4 border-b border-gray-200">
      <button id="new-chat-btn" class="w-full py-2.5 px-4 bg-indigo-500 text-white rounded-xl hover:bg-indigo-600 transition-colors text-sm font-medium">
        + 新对话
      </button>
    </div>
    <div class="flex-1 overflow-y-auto" id="session-list">
      <div class="p-4 text-center text-gray-400 text-sm">加载中...</div>
    </div>
    <div class="p-3 border-t border-gray-200">
      <button id="clear-chat-btn" class="w-full py-2 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded-lg transition-colors">
        清空当前对话
      </button>
    </div>`;

  bind(el);
  loadSessions(el);
  return el;
}

function bind(el: HTMLElement): void {
  // Nav
  el.querySelectorAll('.sidebar-nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const page = (btn as HTMLElement).dataset.page;
      if (!page) return;
      el.querySelectorAll('.sidebar-nav-item').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      window.dispatchEvent(new CustomEvent('navigate', { detail: { page } }));
    });
  });

  // New chat
  el.querySelector('#new-chat-btn')?.addEventListener('click', () => {
    currentSessionId = null;
    window.dispatchEvent(new CustomEvent('chat-clear'));
    highlightSession(el, null);
  });

  // Clear
  el.querySelector('#clear-chat-btn')?.addEventListener('click', () => {
    currentSessionId = null;
    window.dispatchEvent(new CustomEvent('chat-clear'));
    highlightSession(el, null);
  });

  // Listen for session list updates from ChatWindow
  window.addEventListener('sessions-updated', ((e: CustomEvent) => {
    renderList(el, e.detail as Session[]);
  }) as EventListener);
}

async function loadSessions(el: HTMLElement): Promise<void> {
  try {
    const sessions = await apiGet<Session[]>('/sessions');
    renderList(el, sessions);
  } catch {
    const list = el.querySelector('#session-list');
    if (list) list.innerHTML = '<div class="p-4 text-center text-gray-400 text-sm">暂无对话</div>';
  }
}

function renderList(el: HTMLElement, sessions: Session[]): void {
  const list = el.querySelector('#session-list');
  if (!list) return;

  if (!sessions.length) {
    list.innerHTML = '<div class="p-4 text-center text-gray-400 text-sm">暂无对话</div>';
    return;
  }

  list.innerHTML = sessions.map(s =>
    '<div class="session-item px-4 py-2.5 cursor-pointer hover:bg-gray-100 transition-colors border-b border-gray-100 flex items-center justify-between group' +
    (s.id === currentSessionId ? ' bg-indigo-50 border-l-2 border-l-indigo-400' : '') +
    '" data-sid="' + s.id + '">' +
    '<span class="text-sm text-gray-700 truncate flex-1">' + escHtml(s.title) + '</span>' +
    '<button class="delete-session-btn opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-all ml-2" data-sid="' + s.id + '" title="删除">' +
    '<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
    '<path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg></button></div>'
  ).join('');

  // Click to load
  list.querySelectorAll('.session-item').forEach(row => {
    row.addEventListener('click', async (e) => {
      const tgt = e.target as HTMLElement;
      if (tgt.closest('.delete-session-btn')) return;
      const sid = (row as HTMLElement).dataset.sid!;
      currentSessionId = sid;
      highlightSession(el, sid);
      try {
        const data = await apiGet<{ messages: Message[] }>('/sessions/' + sid);
        window.dispatchEvent(new CustomEvent('chat-load', {
          detail: { messages: data.messages || [], sessionId: sid }
        }));
      } catch { /* ignore */ }
    });
  });

  // Delete
  list.querySelectorAll('.delete-session-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const sid = (btn as HTMLElement).dataset.sid!;
      try {
        await apiDelete('/sessions/' + sid);
        if (currentSessionId === sid) {
          currentSessionId = null;
          window.dispatchEvent(new CustomEvent('chat-clear'));
        }
        loadSessions(el);
      } catch { /* ignore */ }
    });
  });
}

function highlightSession(el: HTMLElement, sid: string | null): void {
  el.querySelectorAll('.session-item').forEach(row => {
    const isActive = (row as HTMLElement).dataset.sid === sid;
    row.classList.toggle('bg-indigo-50', isActive);
    row.classList.toggle('border-l-2', isActive);
    row.classList.toggle('border-l-indigo-400', isActive);
  });
}

function escHtml(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

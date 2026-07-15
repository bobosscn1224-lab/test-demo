import { streamChat, streamUploadChat } from '../services/chat';
import type { StreamCallbacks } from '../services/chat';
import { setAvatarState } from './AvatarDisplay';
import { apiGet } from '../services/api';
import type { Session, Message } from '../types';
import { renderSessionPanel, getSessionId, setSessionId, highlightSession } from './SessionPanel';

interface SkillInfo {
  name: string;
  description: string;
  triggers: string[];
  keywords: string[];
}

function esc(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

let abortCtrl: AbortController | null = null;
let streaming = false;
let chatMode: 'kb_only' | 'enhanced' = 'enhanced';
let _doSend: (() => Promise<void>) | null = null;
let _msgList: HTMLElement | null = null;
let _inputEl: HTMLTextAreaElement | null = null;
let selectedFiles: File[] = [];
let activeSkillName: string | null = null;
let activeSkillStage: string | null = null;
const CHAT_REQUEST_TIMEOUT_MS = 120 * 60 * 1000;

function openImagePreview(src: string, alt: string): void {
  let overlay = document.getElementById('image-preview-overlay') as HTMLElement | null;
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'image-preview-overlay';
    overlay.className = 'image-preview-overlay';
    overlay.innerHTML =
      '<button type="button" class="image-preview-close" aria-label="Close preview">脳</button>' +
      '<img class="image-preview-img" alt="">' +
      '<div class="image-preview-caption"></div>';
    document.body.appendChild(overlay);

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay || (e.target as HTMLElement).classList.contains('image-preview-close')) {
        overlay?.classList.remove('open');
      }
    });

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') overlay?.classList.remove('open');
    });
  }

  const img = overlay.querySelector('.image-preview-img') as HTMLImageElement;
  const caption = overlay.querySelector('.image-preview-caption') as HTMLElement;
  img.src = src;
  img.alt = alt || 'preview';
  caption.textContent = alt || '';
  overlay.classList.add('open');
}

interface WeekData {
  label: string;
  is_current: boolean;
  offset: number;
  start: string;
  end: string;
  monday: string;
  sunday: string;
}

function renderWeekPicker(aid: string, message: string, weeks: WeekData[]): void {
  const bubble = document.getElementById('bubble-' + aid);
  if (!bubble) return;
  const row = bubble.closest('[data-msg-id]');
  if (row) {
    const ti = row.querySelector('.thinking-status');
    if (ti) ti.remove();
  }
  // Clear existing
  bubble.innerHTML = '';

  // Title
  const title = document.createElement('div');
  title.className = 'wp-message';
  title.textContent = message;
  bubble.appendChild(title);

  // Quick-select buttons
  const btnGroup = document.createElement('div');
  btnGroup.className = 'wp-btn-group';
  weeks.forEach(w => {
    const btn = document.createElement('button');
    btn.className = 'wp-week-btn' + (w.is_current ? ' wp-current' : '');
    btn.innerHTML = '<span class="wp-label">' + esc(w.label) + '</span><span class="wp-dates">' + esc(w.monday) + ' — ' + esc(w.sunday) + '</span>';
    btn.addEventListener('click', () => {
      // Set input and send
      if (_inputEl) {
        _inputEl.value = w.start + '到' + w.end;
      }
      _doSend?.();
    });
    btnGroup.appendChild(btn);
  });
  bubble.appendChild(btnGroup);
}

export function renderChatWindow(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'flex flex-col min-h-0';
  el.id = 'chat-window-root';
  el.style.cssText = 'flex:1;display:flex;flex-direction:row;min-height:0;';

  // ── Session panel (left, collapsible) ─────────────────────────
  const sessionPanel = renderSessionPanel();
  el.appendChild(sessionPanel);

  // ── Chat area (right) ─────────────────────────────────────────
  const chatArea = document.createElement('div');
  chatArea.id = 'chat-area';
  chatArea.style.cssText = 'flex:1;display:flex;flex-direction:column;min-width:0;';
  chatArea.innerHTML = `
    <div class="flex-1 overflow-y-auto px-6 py-4" id="msg-list" style="width:100%">
      <div id="msg-empty" class="flex items-center justify-center h-full text-gray-400">
        <div class="text-center">
          <div class="text-6xl mb-4">AI</div>
          <p class="text-xl">你好，我是你的数字分身</p>
          <p class="text-base mt-1">有什么想聊的？</p>
        </div>
      </div>
    </div>
    <div class="border-t border-gray-200 px-4 py-3 bg-white flex-shrink-0">
      <div id="attachment-list" class="chat-attachment-list" style="width:100%;display:none;margin-bottom:6px;"></div>
      <div class="flex gap-2 items-end" style="width:100%;position:relative">
        <input id="file-input" type="file" multiple class="sr-only" accept=".txt,.md,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.webp">
        <button id="attach-btn" type="button" title="上传文件" aria-label="上传文件"
          class="chat-icon-btn flex-shrink-0 self-end mb-0.5">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 1 1-2.83-2.83l8.49-8.48"/></svg>
        </button>
        <textarea id="chat-input" placeholder="输入消息...（Enter 发送，Shift+Enter 换行）" rows="3" autocomplete="off"
         class="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent text-base resize-none"></textarea>
        <div id="skill-picker" class="skill-picker" style="display:none">
          <div class="skill-picker-header">可用技能 — 按 ↑↓ 选择，Enter 确认，Esc 关闭</div>
          <div id="skill-picker-list" class="skill-picker-list"></div>
        </div>
        <div class="flex flex-col items-center gap-1 flex-shrink-0 self-end mb-0.5">
          <label id="mode-toggle-label" class="relative inline-flex items-center cursor-pointer" title="鍒囨崲鍥炵瓟妯″紡">
            <span id="mode-label" class="text-xs text-gray-500 mr-2 w-8 text-right">增强</span>
            <span class="relative w-9 h-5">
              <input id="mode-toggle" type="checkbox" class="sr-only peer">
              <span class="absolute inset-0 bg-indigo-500 rounded-full peer-checked:bg-amber-500 transition-colors"></span>
              <span class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-4"></span>
            </span>
          </label>
        </div>
        <button id="send-btn" class="px-4 py-3 bg-indigo-500 text-white rounded-xl hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0 self-end mb-0.5">
          <svg id="send-icon" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
          <svg id="stop-icon" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" style="display:none" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
        </button>
      </div>
    </div>`;

  el.appendChild(chatArea);

  // Bind session panel to ChatWindow events
  bindChatToSessionPanel(el);

  bind(el);
  return el;
}

/** Wire up session panel ↔ chat window communication. */
function bindChatToSessionPanel(root: HTMLElement): void {
  // When session list updates from ChatWindow's loadSessionList
  // the SessionPanel already listens for 'sessions-updated' events.

  // When chat loads a session, highlight it in the panel
  window.addEventListener('chat-load', ((e: CustomEvent) => {
    const sid = e.detail.sessionId || null;
    setSessionId(sid);
    const panel = document.getElementById('session-panel');
    if (panel) highlightSession(panel, sid);
  }) as EventListener);

  // When chat clears, reset session
  window.addEventListener('chat-clear', () => {
    setSessionId(null);
    const panel = document.getElementById('session-panel');
    if (panel) highlightSession(panel, null);
  });
}

function bind(root: HTMLElement): void {
  const input = root.querySelector('#chat-input') as HTMLTextAreaElement;
  const sendBtn = root.querySelector('#send-btn') as HTMLButtonElement;
  const attachBtn = root.querySelector('#attach-btn') as HTMLButtonElement;
  const fileInput = root.querySelector('#file-input') as HTMLInputElement;
  const attachmentList = root.querySelector('#attachment-list') as HTMLElement;
  _inputEl = input;
  _msgList = root.querySelector('#msg-list') as HTMLElement;

  // ---- Helpers ----
  const list = () => root.querySelector('#msg-list') as HTMLElement;

  _msgList.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    const img = target.closest('.message-content img') as HTMLImageElement | null;
    if (!img) return;
    e.preventDefault();
    openImagePreview(img.currentSrc || img.src, img.alt || '');
  });

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  }

  function renderSelectedFiles(): void {
    if (!attachmentList) return;
    if (!selectedFiles.length) {
      attachmentList.style.display = 'none';
      attachmentList.innerHTML = '';
      return;
    }

    attachmentList.style.display = 'flex';
    attachmentList.innerHTML = selectedFiles.map((file, index) =>
      '<div class="chat-attachment-chip" title="' + esc(file.name) + '">' +
      '<span class="chat-attachment-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 1 1-2.83-2.83l8.49-8.48"/></svg></span>' +
      '<span class="chat-attachment-name">' + esc(file.name) + '</span>' +
      '<span class="chat-attachment-size">' + formatFileSize(file.size) + '</span>' +
      '<button type="button" class="chat-attachment-remove" data-file-index="' + index + '" aria-label="移除文件">×</button>' +
      '</div>'
    ).join('');

    attachmentList.querySelectorAll<HTMLButtonElement>('.chat-attachment-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        const index = Number(btn.dataset.fileIndex);
        selectedFiles = selectedFiles.filter((_, i) => i !== index);
        if (!selectedFiles.length) fileInput.value = '';
        renderSelectedFiles();
      });
    });
  }

  function clearSelectedFiles(): void {
    selectedFiles = [];
    fileInput.value = '';
    renderSelectedFiles();
  }

  function defaultUploadMessage(): string {
    if (activeSkillName === 'ppt_maker') {
      if (activeSkillStage === 'awaiting_collage_for_pages') {
        return '入口3：我上传的是 PPT 整体详细缩略图，请从第3步开始输出分页高清图片风格图。';
      }
      if (activeSkillStage === 'awaiting_page_image_for_editable_ppt') {
        return '入口4：我上传的是某一页高清 PPT 风格图，请从第4步开始制作可编辑 PPT。';
      }
      if (activeSkillStage === 'awaiting_outline_for_visual') {
        return '入口2：我上传的是 PPT 大纲，请从第2步开始制作 PPT 缩略图。';
      }
      if (activeSkillStage === 'awaiting_content') {
        return '入口1：我上传的是用于制作 PPT 的资料，请先生成大纲。';
      }
    }
    return '请阅读我上传的文件。';
  }

  function hideEmpty(): void {
    const e = document.getElementById('msg-empty');
    if (e) e.remove();
  }

  function showEmpty(): void {
    const ml = list();
    ml.innerHTML = '<div id="msg-empty" class="flex items-center justify-center h-full text-gray-400"><div class="text-center"><div class="text-6xl mb-4">AI</div><p class="text-xl">你好，我是你的数字分身</p><p class="text-base mt-1">有什么想聊的？</p></div></div>';
  }

  function scrollEnd(): void {
    const ml = list();
    requestAnimationFrame(() => { ml.scrollTop = ml.scrollHeight; });
  }

  function setStreaming(on: boolean): void {
    streaming = on;
    attachBtn.disabled = on;
    fileInput.disabled = on;
    setAvatarState(on ? 'speaking' : 'idle');
    const si = document.getElementById('send-icon');
    const st = document.getElementById('stop-icon');
    if (si && st) {
      si.style.display = on ? 'none' : '';
      st.style.display = on ? '' : 'none';
    }
  }

  function renderAttachmentHTML(names: string[]): string {
    if (!names.length) return '';
    return '<div class="chat-bubble-attachments">' + names.map(name =>
      '<div class="chat-bubble-attachment"><span>' + esc(name) + '</span></div>'
    ).join('') + '</div>';
  }

  function addUserBubble(id: string, text: string, attachmentNames: string[] = []): void {
    const row = document.createElement('div');
    row.className = 'flex justify-end mb-4';
    row.dataset.msgId = id;
    const body = text ? esc(text) : '已上传文件，请阅读附件内容。';
    row.innerHTML =
      '<div class="max-w-[85%] order-1">' +
      '<div class="px-4 py-2.5 rounded-2xl bg-indigo-500 text-white rounded-br-md">' + body + renderAttachmentHTML(attachmentNames) + '</div>' +
      '</div>' +
      '<div class="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center text-white text-sm flex-shrink-0 ml-2 mt-1">你</div>';
    list().appendChild(row);
  }

  function addAssistantBubble(id: string): HTMLElement {
    const row = document.createElement('div');
    row.className = 'flex justify-start mb-4';
    row.dataset.msgId = id;
    row.innerHTML =
      '<div class="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-sm flex-shrink-0 mr-2 mt-1">AI</div>' +
      '<div class="max-w-[85%]">' +
      '<div class="thinking-status"><span>思考中</span><span class="thinking-dots"><i></i><i></i><i></i></span></div>' +
      '<div class="px-4 py-2.5 rounded-2xl bg-gray-100 text-gray-800 rounded-bl-md message-content" id="bubble-' + id + '">' +
      '<span class="thinking-dots"><i></i><i></i><i></i></span></div>' +
      '</div>';
    list().appendChild(row);
    return row;
  }

  function updateAssistantText(id: string, text: string): void {
    const bubble = document.getElementById('bubble-' + id);
    if (!bubble) return;
    // Remove thinking indicator
    const row = bubble.closest('[data-msg-id]');
    if (row) {
      const ti = row.querySelector('.thinking-status');
      if (ti) ti.remove();
    }
    // Single textContent assignment — much faster than per-line DOM rebuild
    // and avoids visual glitches with long streaming text
    bubble.textContent = text;
  }

  function finalizeAssistant(id: string, text: string): void {
    const bubble = document.getElementById('bubble-' + id);
    if (!bubble) return;
    const row = bubble.closest('[data-msg-id]');
    if (row) {
      const ti = row.querySelector('.thinking-status');
      if (ti) ti.remove();
    }
    if (!text) { bubble.innerHTML = ''; return; }
    // Convert markdown links and bare URLs to clickable HTML.
    let html = text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      // Step 1: markdown links [text](url) → <a>
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" class="msg-link">$1</a>')
      // Step 2: bare URLs NOT already inside <a href= — only match URLs at word boundaries
      .replace(/(?<!href=")(?<!">)(https?:\/\/[^\s<>"']+)/g, '<a href="$1" target="_blank" rel="noopener" class="msg-link">$1</a>');
    bubble.innerHTML = html;
    bubble.style.whiteSpace = 'pre-wrap';
    bubble.style.wordBreak = 'break-word';
  }

  // ---- Send logic ----
  let lastSendTime = 0
  async function send(): Promise<void> {
    if (streaming) return
    // Debounce: prevent rapid-fire sends (< 1 second apart)
    const now = Date.now()
    if (now - lastSendTime < 1000) return
    lastSendTime = now

    const text = input.value.trim();
    const files = selectedFiles.slice();
    if (!text && !files.length) return;
    const message = text || defaultUploadMessage();
    const attachmentNames = files.map(file => file.name);
    input.value = '';
    input.style.height = 'auto';
    clearSelectedFiles();

    hideEmpty();

    const uid = crypto.randomUUID();
    addUserBubble(uid, text, attachmentNames);

    const aid = crypto.randomUUID();
    addAssistantBubble(aid);

    setStreaming(true);
    abortCtrl = new AbortController();
    scrollEnd();

    let full = '';
    let tid: number | undefined;
    const resetTimeout = () => {
      if (tid) window.clearTimeout(tid);
      tid = window.setTimeout(() => {
        abortCtrl?.abort();
        updateAssistantText(aid, full + '\n\n请求超时，请重试');
        setStreaming(false);
      }, CHAT_REQUEST_TIMEOUT_MS);
    };
    resetTimeout();
    try {
      const callbacks: StreamCallbacks = {
        onToken(t) {
          resetTimeout();
          full += t;
          updateAssistantText(aid, full);
          scrollEnd();
        },
        onDone(sid) {
          if (tid) window.clearTimeout(tid);
          if (sid) setSessionId(sid);
          if (full !== '__rendered__') {
            finalizeAssistant(aid, full);
          }
          setStreaming(false);
          loadSessionList();
        },
        onError(err) {
          if (tid) window.clearTimeout(tid);
          full += '\n\n出错了: ' + err;
          finalizeAssistant(aid, full);
          setStreaming(false);
        },
        onSkill(d, sid) {
          resetTimeout();
          if (sid) setSessionId(sid);
          activeSkillName = d.skill || activeSkillName;
          activeSkillStage = ((d.data as any)?.stage as string) || activeSkillStage;
          if ((d.data as any)?.mode === 'ask_date' && (d.data as any)?.weeks) {
            // Render interactive week picker — set marker to prevent onDone from overwriting
            renderWeekPicker(aid, d.message || '请选择要写哪一周的周报：', (d.data as any).weeks as WeekData[]);
            full = '__rendered__';
            setStreaming(false);
          } else {
            full += d.message || '';
            if (d.follow_up_action === 'download' && d.data?.download_url) {
              full += '\n\n[下载文件](' + d.data.download_url + ')';
            }
            finalizeAssistant(aid, full);
            scrollEnd();
          }
        },
        onRich(data) {
          resetTimeout();
          if (data.html) {
            // Replace streaming plain text with rich formatted HTML
            const el = document.getElementById('bubble-' + aid);
            if (el) {
              el.innerHTML = data.html;
              // Make follow-up buttons clickable
              el.querySelectorAll('.btn').forEach(btn => {
                btn.addEventListener('click', () => {
                  const input = document.getElementById('chat-input') as HTMLTextAreaElement;
                  if (input) {
                    input.value = (btn as HTMLElement).innerText.trim();
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    setTimeout(() => {
                      const sendBtn = document.getElementById('send-btn');
                      if (sendBtn) sendBtn.click();
                    }, 100);
                  }
                });
              });
              scrollEnd();
            }
            // Prevent onDone from overwriting the rich HTML with plain text
            full = '__rendered__';
          }
        },
      };
      if (files.length) {
        await streamUploadChat(message, getSessionId(), files, callbacks, abortCtrl.signal, chatMode);
      } else {
        await streamChat(message, getSessionId(), callbacks, abortCtrl.signal, chatMode);
      }
    } catch {
      if (tid) window.clearTimeout(tid);
      if (full) {
        updateAssistantText(aid, full + '\n\n请求中断，请重试');
      }
    } finally {
      if (tid) window.clearTimeout(tid);
      setStreaming(false);
    }
  }

  _doSend = send;

  attachBtn.addEventListener('click', () => {
    if (streaming) return;
    fileInput.click();
  });

  fileInput.addEventListener('change', () => {
    selectedFiles = Array.from(fileInput.files || []);
    renderSelectedFiles();
  });

  sendBtn.addEventListener('click', () => {
    if (streaming) { abortCtrl?.abort(); return; }
    send();
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 150) + 'px';
  });

  // ---- Mode toggle ----
  const modeToggle = root.querySelector('#mode-toggle') as HTMLInputElement;
  const modeLabel = root.querySelector('#mode-label') as HTMLElement;
  if (modeToggle && modeLabel) {
    modeToggle.addEventListener('change', () => {
      chatMode = modeToggle.checked ? 'kb_only' : 'enhanced';
      modeLabel.textContent = modeToggle.checked ? '知识库' : '增强';
    });
  }

  // ---- Slash command skill picker ----
  const skillPicker = root.querySelector('#skill-picker') as HTMLElement;
  const skillPickerList = root.querySelector('#skill-picker-list') as HTMLElement;
  let skillsCache: SkillInfo[] = [];
  let pickerIndex = -1;

  async function loadSkills(): Promise<SkillInfo[]> {
    if (skillsCache.length) return skillsCache;
    try {
      skillsCache = await apiGet<SkillInfo[]>('/skills/list');
    } catch {
      skillsCache = [];
    }
    return skillsCache;
  }

  function showSkillPicker(): void {
    if (!skillPicker) return;
    skillPicker.style.display = 'block';
    pickerIndex = -1;
  }

  function hideSkillPicker(): void {
    if (!skillPicker) return;
    skillPicker.style.display = 'none';
  }

  function renderSkillPickerItems(skills: SkillInfo[], filter: string): number {
    if (!skillPickerList) return 0;
    const q = filter.toLowerCase();
    const filtered = skills.filter(s => {
      if (!q) return true;
      return s.name.toLowerCase().includes(q) ||
             s.description.toLowerCase().includes(q) ||
             s.triggers.some(t => t.toLowerCase().includes(q)) ||
             s.keywords.some(k => k.toLowerCase().includes(q));
    });

    skillPickerList.innerHTML = filtered.map((s, i) =>
      `<div class="skill-picker-item${i === pickerIndex ? ' active' : ''}" data-index="${i}">
        <span class="skill-picker-name">${esc(s.name)}</span>
        <span class="skill-picker-desc">${esc(s.description.substring(0, 60))}${s.description.length > 60 ? '...' : ''}</span>
        <span class="skill-picker-triggers">${s.triggers.slice(0, 3).map(t => esc(t)).join(' · ')}</span>
      </div>`
    ).join('');

    // Click handler
    skillPickerList.querySelectorAll('.skill-picker-item').forEach(item => {
      item.addEventListener('mousedown', (e) => {
        e.preventDefault(); // prevent blur on input
        const idx = Number((item as HTMLElement).dataset.index);
        const skill = filtered[idx];
        if (skill && input) {
          const trigger = skill.triggers[0] || skill.name;
          // Replace the "/" and filter text with the trigger
          const before = input.value.slice(0, slashStartPos);
          input.value = before + trigger + ' ';
          input.focus();
          hideSkillPicker();
        }
      });
    });

    return filtered.length;
  }

  let slashStartPos = -1;
  let pickerVisible = false;

  async function handleSlashInput(): Promise<void> {
    if (!input) return;
    const val = input.value;
    const cursor = input.selectionStart || 0;

    // Check if "/" was just typed or cursor is after a "/"
    const textBeforeCursor = val.slice(0, cursor);

    // Only activate when "/" is the first non-whitespace character
    const slashMatch = textBeforeCursor.match(/^\s*(\/)([\w一-鿿]*)$/);
    if (slashMatch) {
      slashStartPos = (slashMatch.index || 0) + (slashMatch[0].startsWith('/') ? 0 : 1);
      const filter = slashMatch[2] || '';
      const skills = await loadSkills();
      const count = renderSkillPickerItems(skills, filter);
      if (count > 0) {
        showSkillPicker();
        pickerVisible = true;
        return;
      }
    }

    hideSkillPicker();
    pickerVisible = false;
  }

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 150) + 'px';
    handleSlashInput();
  });

  input.addEventListener('keydown', (e) => {
    if (!pickerVisible) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const items = skillPickerList?.querySelectorAll('.skill-picker-item');
      if (items && items.length) {
        pickerIndex = Math.min(pickerIndex + 1, items.length - 1);
        handleSlashInput(); // re-render to update active state
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      pickerIndex = Math.max(pickerIndex - 1, -1);
      handleSlashInput();
    } else if (e.key === 'Enter' && pickerIndex >= 0 && !e.shiftKey) {
      e.preventDefault();
      const items = skillPickerList?.querySelectorAll('.skill-picker-item');
      if (items && items[pickerIndex]) {
        (items[pickerIndex] as HTMLElement).dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      hideSkillPicker();
      pickerVisible = false;
    }
  });

  // Hide picker when clicking outside
  document.addEventListener('click', (e) => {
    if (pickerVisible && skillPicker && input) {
      const target = e.target as HTMLElement;
      if (!skillPicker.contains(target) && target !== input) {
        hideSkillPicker();
        pickerVisible = false;
      }
    }
  });

  // ---- External control ----
  window.addEventListener('chat-clear', () => {
    if (streaming) { abortCtrl?.abort(); setStreaming(false); }
    setSessionId(null);
    activeSkillName = null;
    activeSkillStage = null;
    clearSelectedFiles();
    showEmpty();
  });

  window.addEventListener('chat-load', ((e: CustomEvent) => {
    if (streaming) { abortCtrl?.abort(); setStreaming(false); }
    clearSelectedFiles();
    const msgs = e.detail.messages as Message[];
    setSessionId(e.detail.sessionId || null);
    activeSkillName = null;
    activeSkillStage = null;
    hideEmpty();
    const ml = list();
    ml.innerHTML = msgs.map(m => renderMsgHTML(m)).join('');
    ml.scrollTop = ml.scrollHeight;
  }) as EventListener);
}

function renderMsgHTML(m: Message): string {
  const isUser = m.role === 'user';
  let body: string;
  if (!m.content) {
    body = '';
  } else if (isUser) {
    body = esc(m.content);
  } else {
    // Assistant: use markdown rendering with plain-text fallback
    // Use escaped plain text with line breaks — avoids markdown rendering
    // issues that silently drop content on long assistant messages.
    body = esc(m.content).replace(/\n/g, '<br>');
  }
  const avatar = isUser
    ? '<div class="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center text-white text-sm flex-shrink-0 ml-2 mt-1">你</div>'
    : '<div class="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-sm flex-shrink-0 mr-2 mt-1">AI</div>';
  const cls = isUser ? 'bg-indigo-500 text-white rounded-br-md' : 'bg-gray-100 text-gray-800 rounded-bl-md';
  const think = (!isUser && !m.content)
    ? '<div class="thinking-status"><span>思考中</span><span class="thinking-dots"><i></i><i></i><i></i></span></div>'
    : '';
  const inner = body || (isUser ? '' : '<span class="thinking-dots"><i></i><i></i><i></i></span>');
  return '<div class="flex ' + (isUser ? 'justify-end' : 'justify-start') + ' mb-4" data-msg-id="' + m.id + '">' +
    (isUser ? '' : avatar) +
    '<div class="max-w-[85%] ' + (isUser ? 'order-1' : '') + '">' + think +
    '<div class="px-4 py-2.5 rounded-2xl message-content ' + cls + '" id="bubble-' + m.id + '">' + inner + '</div>' +
    '</div>' + (isUser ? avatar : '') + '</div>';
}

async function loadSessionList(): Promise<void> {
  try {
    const sessions = await apiGet<Session[]>('/sessions');
    window.dispatchEvent(new CustomEvent('sessions-updated', { detail: sessions }));
  } catch { /* ignore */ }
}



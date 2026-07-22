/** Pro Mode — 全局进度反馈系统.
 *
 *  所有调用大模型/生图/生视频等异步操作都通过此模块显示进度，
 *  让用户明确知道"点了按钮，系统正在处理"。
 *
 *  用法：
 *    import { progress } from './progress';
 *
 *    // 方式 1：手动管理
 *    progress.start('gen-frame-1', '生成 Shot 1 关键帧');
 *    progress.update('gen-frame-1', '调用生图模型中...');
 *    progress.done('gen-frame-1', '关键帧已生成');
 *    // 或 progress.fail('gen-frame-1', '生成失败: timeout');
 *
 *    // 方式 2：包装 async 函数（推荐）
 *    const result = await progress.withAsync(
 *      'gen-frame-1', '生成 Shot 1 关键帧',
 *      async () => { return await apiPost(...); }
 *    );
 */

// ── Types ────────────────────────────────────────────────────────

interface ProgressEntry {
  key: string;
  label: string;
  message: string;
  status: 'active' | 'done' | 'failed';
  startTime: number;
  endTime?: number;
}

// ── State ────────────────────────────────────────────────────────

const _entries = new Map<string, ProgressEntry>();
let _panel: HTMLElement | null = null;
let _timer: ReturnType<typeof setInterval> | null = null;

// ── Panel management ─────────────────────────────────────────────

function ensurePanel(): HTMLElement {
  if (_panel && document.body.contains(_panel)) return _panel;

  _panel = document.createElement('div');
  _panel.id = 'pro-mode-progress-panel';
  _panel.style.cssText = [
    'position:fixed', 'bottom:16px', 'right:16px', 'z-index:9999',
    'display:flex', 'flex-direction:column', 'gap:8px',
    'max-width:380px', 'max-height:60vh', 'overflow-y:auto',
    'pointer-events:none',
  ].join(';');
  document.body.appendChild(_panel);

  if (!_timer) {
    _timer = setInterval(renderPanel, 500); // Update elapsed time every 500ms
  }
  return _panel;
}

function removePanelIfEmpty(): void {
  if (_entries.size === 0 && _panel) {
    _panel.remove();
    _panel = null;
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
  }
}

function renderPanel(): void {
  const panel = ensurePanel();
  const now = Date.now();

  // Remove entries that have been done/failed for more than 3 seconds
  let hasActive = false;
  for (const [key, entry] of _entries) {
    if (entry.status !== 'active' && entry.endTime && now - entry.endTime > 3000) {
      _entries.delete(key);
    }
    if (entry.status === 'active') hasActive = true;
  }

  // Rebuild panel content
  panel.innerHTML = '';
  for (const [, entry] of _entries) {
    panel.appendChild(renderEntry(entry, now));
  }

  removePanelIfEmpty();
}

function renderEntry(entry: ProgressEntry, now: number): HTMLElement {
  const elapsed = entry.status === 'active'
    ? now - entry.startTime
    : (entry.endTime || now) - entry.startTime;
  const elapsedStr = formatElapsed(elapsed);

  const colors = {
    active: { bg: '#eef2ff', border: '#c7d2fe', text: '#4f46e5', icon: '⏳' },
    done:   { bg: '#ecfdf5', border: '#bbf7d0', text: '#059669', icon: '✅' },
    failed: { bg: '#fef2f2', border: '#fecaca', text: '#dc2626', icon: '❌' },
  };
  const c = colors[entry.status];

  const el = document.createElement('div');
  el.style.cssText = [
    `background:${c.bg}`, `border:1px solid ${c.border}`, `border-radius:10px`,
    'padding:10px 14px', 'display:flex', 'align-items:flex-start', 'gap:8px',
    'pointer-events:auto', 'box-shadow:0 2px 8px rgba(0,0,0,0.1)',
    entry.status !== 'active' ? 'transition:opacity 0.5s' : '',
  ].join(';');

  el.innerHTML = `
    <div style="font-size:16px;line-height:1.2;flex-shrink:0;">${c.icon}</div>
    <div style="flex:1;min-width:0;">
      <div style="font-size:12px;font-weight:600;color:${c.text};">${escapeHtml(entry.label)}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:2px;">${escapeHtml(entry.message)}</div>
    </div>
    <div style="font-size:11px;color:#9ca3af;font-variant-numeric:tabular-nums;flex-shrink:0;">${elapsedStr}</div>
  `;

  // Add spinner for active entries
  if (entry.status === 'active') {
    const spinner = el.querySelector('div') as HTMLElement;
    spinner.style.cssText += 'animation:pm-spin 1s linear infinite;';
  }

  return el;
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  return `${m}m${rs}s`;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Add spinner keyframe if not already added
function ensureKeyframe(): void {
  if (document.getElementById('pm-progress-keyframe')) return;
  const style = document.createElement('style');
  style.id = 'pm-progress-keyframe';
  style.textContent = '@keyframes pm-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }';
  document.head.appendChild(style);
}

// ── Public API ───────────────────────────────────────────────────

export const progress = {
  /** 开始一个进度条目。key 唯一标识，label 显示操作名称。 */
  start(key: string, label: string, message: string = '处理中...'): void {
    ensureKeyframe();
    _entries.set(key, {
      key, label, message,
      status: 'active',
      startTime: Date.now(),
    });
    renderPanel();
  },

  /** 更新进度消息。 */
  update(key: string, message: string): void {
    const entry = _entries.get(key);
    if (entry) {
      entry.message = message;
      renderPanel();
    }
  },

  /** 标记完成，3 秒后自动淡出。 */
  done(key: string, message: string = '完成'): void {
    const entry = _entries.get(key);
    if (entry) {
      entry.status = 'done';
      entry.message = message;
      entry.endTime = Date.now();
      renderPanel();
    }
  },

  /** 标记失败，3 秒后自动淡出。 */
  fail(key: string, message: string = '失败'): void {
    const entry = _entries.get(key);
    if (entry) {
      entry.status = 'failed';
      entry.message = message;
      entry.endTime = Date.now();
      renderPanel();
    }
  },

  /** 包装 async 函数，自动管理进度。成功返回结果，失败抛出异常。 */
  async withAsync<T>(
    key: string, label: string,
    fn: (update: (msg: string) => void) => Promise<T>,
    initialMessage: string = '处理中...',
  ): Promise<T> {
    this.start(key, label, initialMessage);
    try {
      const result = await fn((msg: string) => this.update(key, msg));
      this.done(key, '完成');
      return result;
    } catch (e: any) {
      this.fail(key, e.message || '失败');
      throw e;
    }
  },
};

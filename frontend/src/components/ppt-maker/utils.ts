/** Shared utility functions for the PPT Maker. */

// Map English backend values → Chinese UI labels
export const LABEL_MAP: Record<string, Record<string, string>> = {
  purpose: { business_report: '业务汇报', project_proposal: '项目方案', product_launch: '产品宣讲', training: '培训辅导', review: '复盘总结', story_pitch: '故事路演', other: '其他' },
  audience: { executives: '老板管理层', clients: '客户合作方', team: '一线团队', investors: '投资人', mixed: '混合' },
  scale: { compact_8_12: '精简8-12页', standard_15_20: '标准15-20页', full_25_35: '完整25-35页' },
  style: { professional: '专业严谨', tech: '科技感', minimal: '简约商务', creative: '创意活泼', bold: '高端大气' },
};

export function _label(cat: string, key: string): string {
  return (LABEL_MAP[cat] || {})[key] || key;
}

export function esc(s: string): string {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

export function btn(html: string, cls: string, click: () => void): HTMLButtonElement {
  const b = document.createElement('button');
  b.innerHTML = html;
  b.className = cls;
  b.addEventListener('click', click);
  return b;
}

export function toast(msg: string, type: 'success' | 'error' = 'success'): void {
  const existing = document.getElementById('ppt-toast');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.id = 'ppt-toast';
  el.style.cssText =
    'position:fixed;bottom:24px;right:24px;padding:10px 20px;border-radius:10px;font-size:14px;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.12);cursor:pointer;max-width:400px;';
  if (type === 'success') {
    el.style.background = '#ecfdf5';
    el.style.color = '#065f46';
    el.style.border = '1px solid #a7f3d0';
  } else {
    el.style.background = '#fef2f2';
    el.style.color = '#991b1b';
    el.style.border = '1px solid #fecaca';
  }
  el.textContent = msg;
  el.onclick = () => el.remove();
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

// ── Loading overlay: shared across all steps ─────────────────────────

let _overlayStyleInjected = false;

export function showLoading(container: HTMLElement, message: string, subMessage?: string): () => void {
  // Inject the spinner keyframe once
  if (!_overlayStyleInjected) {
    _overlayStyleInjected = true;
    const s = document.createElement('style');
    s.textContent = '@keyframes pptSpin{to{transform:rotate(360deg)}}';
    document.head.appendChild(s);
  }

  const overlay = document.createElement('div');
  overlay.className = 'ppt-loading-overlay';
  overlay.style.cssText =
    'position:absolute;inset:0;z-index:40;display:flex;align-items:center;justify-content:center;' +
    'background:rgba(255,255,255,0.85);backdrop-filter:blur(4px);';

  const spinner = document.createElement('div');
  spinner.style.cssText =
    'width:44px;height:44px;border:4px solid #e0e7ff;border-top-color:#4f46e5;border-radius:50%;animation:pptSpin .8s linear infinite;margin:0 auto 12px;';

  const title = document.createElement('p');
  title.textContent = message;
  title.style.cssText = 'font-size:15px;font-weight:600;color:#374151;';

  const sub = document.createElement('p');
  sub.textContent = subMessage || '';
  sub.style.cssText = 'font-size:13px;color:#9ca3af;margin-top:4px;';

  const box = document.createElement('div');
  box.style.textAlign = 'center';
  box.appendChild(spinner);
  box.appendChild(title);
  if (subMessage) box.appendChild(sub);

  overlay.appendChild(box);
  container.appendChild(overlay);

  // Return a cleanup function
  return () => overlay.remove();
}

export function showImagePreview(url: string, caption: string): void {
  // Remove existing overlay
  const existing = document.querySelector('.image-preview-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.className = 'image-preview-overlay open';
  overlay.innerHTML = `
    <button class="image-preview-close">&times;</button>
    <img class="image-preview-img" src="${esc(url)}" alt="${esc(caption)}">
    <div class="image-preview-caption">${esc(caption)}</div>
  `;
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay || (e.target as HTMLElement).classList.contains('image-preview-close')) {
      overlay.remove();
    }
  });
  document.addEventListener('keydown', function closeOnEsc(e) {
    if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', closeOnEsc); }
  });
  document.body.appendChild(overlay);
}

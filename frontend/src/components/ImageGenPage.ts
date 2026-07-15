/** Image Generation Feature Page — direct prompt-to-image with settings. */

import { apiPost } from '../services/api';

interface ImageResult {
  success: boolean;
  image_url?: string;
  download_url?: string;
  prompt?: string;
  error?: string;
  backend?: string;
}

export function renderImageGenPage(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'feature-page';
  el.style.cssText = 'padding:24px;max-width:900px;margin:0 auto;height:100%;overflow-y:auto;';

  el.innerHTML = `
    <h2 style="font-size:20px;font-weight:700;color:#111827;margin-bottom:4px;">🎨 图片生成</h2>
    <p style="color:#6b7280;font-size:14px;margin-bottom:20px;">输入描述词，AI为你生成高质量图片</p>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
      <!-- Left: Input -->
      <div>
        <div style="background:#f9fafb;border-radius:12px;padding:20px;">
          <label style="display:block;font-size:14px;font-weight:600;color:#374151;margin-bottom:8px;">
            ✏️ 图片描述 (Prompt)
          </label>
          <textarea id="image-prompt" rows="4"
            style="width:100%;padding:10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;resize:vertical;"
            placeholder="描述你想生成的画面，例如：一只穿西装的猫在会议室，扁平商务插画风格..."></textarea>

          <label style="display:block;font-size:14px;font-weight:600;color:#374151;margin:16px 0 8px;">
            📐 尺寸比例
          </label>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">
            ${['1:1 正方形','16:9 横版','9:16 竖版'].map(ratio => `
              <label style="display:flex;align-items:center;gap:6px;padding:8px;border:1px solid #d1d5db;
                border-radius:8px;cursor:pointer;font-size:13px;color:#374151;">
                <input type="radio" name="image-ratio" value="${ratio.split(' ')[0]}" ${ratio.startsWith('16:9')?'checked':''}> ${ratio}
              </label>
            `).join('')}
          </div>

          <button id="image-generate-btn"
            style="width:100%;margin-top:20px;padding:12px;background:#4f46e5;color:#fff;border:none;
              border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;">
            🎨 生成图片
          </button>
        </div>
      </div>

      <!-- Right: Preview -->
      <div>
        <div id="image-preview-area"
          style="background:#f9fafb;border-radius:12px;padding:20px;min-height:300px;
            display:flex;align-items:center;justify-content:center;color:#9ca3af;font-size:14px;">
          生成结果将在这里显示
        </div>

        <div id="image-history" style="margin-top:16px;">
          <h3 style="font-size:14px;font-weight:600;color:#374151;margin-bottom:8px;">📋 生成历史</h3>
          <div id="image-history-list" style="display:flex;flex-wrap:wrap;gap:8px;"></div>
        </div>
      </div>
    </div>
  `;

  bindEvents(el);
  return el;
}

function bindEvents(el: HTMLElement): void {
  const history: { url: string; prompt: string }[] = [];

  el.querySelector('#image-generate-btn')?.addEventListener('click', async () => {
    const prompt = (el.querySelector('#image-prompt') as HTMLTextAreaElement)?.value?.trim();
    if (!prompt) return;

    const ratioRadio = el.querySelector('input[name="image-ratio"]:checked') as HTMLInputElement;
    const ratio = ratioRadio?.value || '16:9';

    const preview = el.querySelector('#image-preview-area') as HTMLElement;
    preview.innerHTML = '<div style="color:#4f46e5;">⏳ 正在生成图片...</div>';

    try {
      const data = await apiPost<ImageResult>('/v1/images/generate', { prompt, ratio });
      if (data.success && data.image_url) {
        preview.innerHTML = `
          <div style="text-align:center;">
            <img src="${data.image_url}" alt="${prompt}" style="max-width:100%;max-height:400px;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.1);" />
            <div style="margin-top:8px;font-size:12px;color:#6b7280;">
              ${data.backend ? `后端: ${data.backend}` : ''}
              <a href="${data.download_url}" download style="color:#4f46e5;margin-left:8px;">下载原图</a>
            </div>
          </div>`;

        // Add to history
        history.unshift({ url: data.image_url, prompt });
        renderHistory(el, history);
      } else {
        preview.innerHTML = `<div style="color:#ef4444;text-align:center;">❌ 生成失败：${data.error || '未知错误'}</div>`;
      }
    } catch (e: unknown) {
      preview.innerHTML = `<div style="color:#ef4444;text-align:center;">❌ 请求失败：${e instanceof Error ? e.message : '网络错误'}</div>`;
    }
  });

  // Enter key to generate
  el.querySelector('#image-prompt')?.addEventListener('keydown', (e) => {
    if ((e as KeyboardEvent).key === 'Enter' && (e as KeyboardEvent).ctrlKey) {
      (el.querySelector('#image-generate-btn') as HTMLButtonElement)?.click();
    }
  });
}

function renderHistory(el: HTMLElement, history: { url: string; prompt: string }[]): void {
  const list = el.querySelector('#image-history-list');
  if (!list) return;
  list.innerHTML = history.map((h, i) => `
    <div style="width:80px;height:80px;border-radius:8px;overflow:hidden;cursor:pointer;border:2px solid #e5e7eb;
      flex-shrink:0;" title="${escHtml(h.prompt)}">
      <img src="${h.url}" alt="${escHtml(h.prompt)}" style="width:100%;height:100%;object-fit:cover;"
        onclick="document.querySelector('#image-preview-area')!.innerHTML='<img src=\\'${h.url}\\' style=\\'max-width:100%;max-height:400px;border-radius:8px;\\' />'" />
    </div>
  `).join('');
}

function escHtml(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

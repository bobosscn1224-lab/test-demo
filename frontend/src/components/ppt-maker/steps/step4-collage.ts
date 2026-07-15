/** Step 4: Collage generation and style selection. */

import { apiPost, apiPut } from '../../../services/api';
import { state } from '../state';
import { esc, toast, showImagePreview, showLoading } from '../utils';
import { navigateTo, reRender } from '../navigation';
import { STYLE_OPTIONS } from '../types';
import type { Collage } from '../types';

export function renderStep4(el: HTMLElement): void {
  el.className = 'max-w-5xl mx-auto w-full p-6';

  const hasCollages = state.collages.length > 0;

  const html = `
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-xl font-bold text-gray-800">选择风格方案</h2>
        <p class="text-sm text-gray-500 mt-1">${hasCollages ? '点击选择你喜欢的视觉风格方案' : 'AI 将生成 3 套不同风格的缩略图方案供你选择'}</p>
      </div>
    </div>

    <!-- Progress bar during sequential generation -->
    <div id="ppt-collage-progress" class="hidden mb-4 bg-indigo-50 rounded-lg p-3 flex items-center gap-3">
      <span id="ppt-collage-progress-icon" class="text-lg"></span>
      <div class="flex-1">
        <p id="ppt-collage-progress-text" class="text-sm font-medium text-indigo-700"></p>
        <div class="w-full bg-indigo-200 rounded-full h-1.5 mt-1 overflow-hidden">
          <div id="ppt-collage-progress-bar" class="bg-indigo-500 h-1.5 rounded-full transition-all duration-500" style="width:0%"></div>
        </div>
      </div>
    </div>

    <!-- Model selector (always visible) -->
    <div class="max-w-lg mx-auto mb-4">
      <div class="flex items-center gap-2">
        <span class="text-sm font-semibold text-gray-600">生图模型：</span>
        <select id="ppt-backend-select" class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-indigo-500 bg-white">
          <option value="">自动选择</option>
        </select>
        <span id="ppt-backend-loading" class="text-xs text-gray-400"></span>
      </div>
    </div>

    ${!hasCollages ? `
      <div class="text-center">
        <div class="max-w-lg mx-auto mb-8 bg-white rounded-xl border border-gray-200 p-5 text-left">
          <h3 class="text-sm font-bold text-gray-700 mb-1">选择视觉风格</h3>
          <p class="text-xs text-gray-400 mb-3">AI 将根据你选择的风格偏好生成 3 套不同视觉方向的缩略图</p>
          <div id="ppt-step4-styles" class="grid grid-cols-2 gap-2">
            ${STYLE_OPTIONS.map(so => `
              <label class="ppt-step4-style-opt flex items-center gap-2 px-3 py-2 border-2 rounded-lg cursor-pointer text-sm transition-all ${state.formStyles.includes(so.key) ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'}">
                <input type="checkbox" value="${esc(so.key)}" ${state.formStyles.includes(so.key) ? 'checked' : ''} class="sr-only">
                <span class="font-medium text-xs">${esc(so.label)}</span>
              </label>
            `).join('')}
          </div>
          ${state.formStyles.length > 0 ? `<p class="text-xs text-gray-400 mt-2">已选 ${state.formStyles.length} 种风格</p>` : ''}
        </div>
        <p class="text-gray-500 mb-6">基于大纲和视觉风格偏好，生成 3 套设计方案</p>
        <button id="ppt-gen-collages-btn" class="px-6 py-3 bg-indigo-600 text-white rounded-xl text-base font-semibold hover:bg-indigo-700 transition-colors">生成风格方案</button>
      </div>
    ` : `
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        ${state.collages.filter(c => c && c.label).map((c, i) => {
          const status = (c as any).status || 'done';
          const imgHtml = status === 'pending'
            ? '<div class="flex items-center justify-center bg-gray-100" style="min-height:200px;"><span class="text-gray-400 text-sm">等待生成...</span></div>'
            : status === 'generating'
            ? '<div class="flex items-center justify-center bg-indigo-50" style="min-height:200px;"><span class="text-indigo-500 text-sm">生成中...</span></div>'
            : status === 'failed'
            ? '<div class="flex items-center justify-center bg-red-50" style="min-height:200px;"><span class="text-red-500 text-sm">生成失败</span></div>'
            : '<div class="ppt-collage-img-wrap relative cursor-pointer" data-idx="' + i + '"><img src="' + esc(c.download_url) + '" alt="' + esc(c.label) + '" class="w-full h-auto object-cover" style="min-height:200px;" loading="lazy"><div class="ppt-collage-overlay absolute inset-0 bg-black/0 hover:bg-black/10 transition-colors flex items-center justify-center"><span class="text-white text-sm font-medium bg-black/50 px-3 py-1.5 rounded-lg opacity-0 hover:opacity-100 transition-opacity">查看大图</span></div></div>';
          return '<div class="ppt-collage-card bg-white border-2 rounded-xl overflow-hidden transition-all ' + (state.selectedCollageIdx === i ? 'border-indigo-500 shadow-lg shadow-indigo-100' : 'border-gray-200 hover:border-gray-300') + '" data-idx="' + i + '">'
            + '<div class="p-3 flex items-center justify-between bg-gray-50 border-b border-gray-100">'
            + '<span class="font-semibold text-sm text-gray-700">方案 ' + esc(c.label) + '</span>'
            + (state.selectedCollageIdx === i ? '<span class="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-medium">已选择</span>' : '')
            + '</div>' + imgHtml
            + '<div class="p-3 space-y-2">'
            + '<button class="ppt-select-collage-btn w-full py-2 rounded-lg text-sm font-semibold transition-colors ' + (state.selectedCollageIdx === i ? 'bg-indigo-100 text-indigo-700 cursor-default' : 'bg-indigo-600 text-white hover:bg-indigo-700') + '" data-idx="' + i + '">' + (state.selectedCollageIdx === i ? '当前选择' : '选择此方案') + '</button>'
            + '<input type="text" class="ppt-collage-feedback w-full px-2 py-1.5 border border-gray-200 rounded-lg text-xs focus:outline-none focus:border-amber-400" placeholder="修改意见（可选）" data-label="' + esc(c.label) + '">'
            + '<button class="ppt-regen-collage-btn w-full py-1.5 bg-amber-50 text-amber-700 rounded-lg text-xs font-semibold hover:bg-amber-100 transition-colors" data-label="' + esc(c.label) + '">重新生成此方案</button>'
            + '</div></div>';
        }).join('')}
      </div>
      ${state.selectedCollageIdx !== null ? `
        <div class="mt-6 text-center">
          <button id="ppt-confirm-collage" class="px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors">确认方案，进入逐页生成</button>
        </div>
      ` : ''}
    `}

    <div class="flex items-center gap-3 mt-6 pt-4 border-t border-gray-200">
      <button id="ppt-step4-back" class="px-4 py-2 border border-gray-300 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors">上一步</button>
      ${hasCollages ? `<button id="ppt-regen-collages-btn" class="px-4 py-2 border border-amber-300 rounded-xl text-sm text-amber-700 hover:bg-amber-50 transition-colors">重新生成风格方案</button>` : ''}
      <button id="ppt-toggle-prompts" class="px-4 py-2 border border-gray-300 rounded-xl text-sm text-gray-500 hover:bg-gray-50 transition-colors ml-auto">查看提示词</button>
    </div>

    <div id="ppt-prompts-panel" class="hidden mt-4 space-y-3"></div>
  `;

  el.innerHTML = html;
  bindStep4(el);
}

function bindStep4(el: HTMLElement): void {
  // Load available image backends
  const backendSelect = el.querySelector('#ppt-backend-select') as HTMLSelectElement;
  const backendLoading = el.querySelector('#ppt-backend-loading') as HTMLElement;
  if (backendSelect && backendSelect.options.length <= 1) {
    backendLoading!.textContent = '加载中...';
    fetch('/api/v1/ppt-maker/image-backends')
      .then(r => r.json())
      .then((backends: { key: string; label: string; model: string; desc: string }[]) => {
        backendSelect.innerHTML = '<option value="">自动选择</option>';
        backends.forEach(b => {
          const opt = document.createElement('option');
          opt.value = b.key;
          opt.textContent = `${b.label} (${b.model})`;
          backendSelect.appendChild(opt);
        });
        backendSelect.value = (state as any)._imageBackend || '';
        backendLoading!.textContent = '';
      })
      .catch(() => { backendLoading!.textContent = '加载失败'; });
  }

  backendSelect?.addEventListener('change', async () => {
    (state as any)._imageBackend = backendSelect.value;
    try {
      await apiPut(`/v1/ppt-maker/projects/${state.projectId}/`, { image_backend: backendSelect.value } as any);
    } catch { /* non-critical */ }
  });

  // Style checkboxes
  el.querySelectorAll('#ppt-step4-styles input[type=checkbox]').forEach(cb => {
    cb.addEventListener('change', () => {
      const val = (cb as HTMLInputElement).value;
      if ((cb as HTMLInputElement).checked) {
        if (!state.formStyles.includes(val)) state.formStyles.push(val);
      } else {
        state.formStyles = state.formStyles.filter(s => s !== val);
      }
      reRender();
    });
  });

  // Sequential generation: A -> B -> C, show placeholder cards for pending
  async function generateSequential(): Promise<void> {
    await apiPut(`/v1/ppt-maker/projects/${state.projectId}/`, { styles: state.formStyles });

    // Init placeholder cards so user sees all 3 slots
    state.collages = [
      { label: 'A', status: 'pending', filename: '', download_url: '' },
      { label: 'B', status: 'pending', filename: '', download_url: '' },
      { label: 'C', status: 'pending', filename: '', download_url: '' },
    ];
    reRender();

    const labels = ['A', 'B', 'C'];
    for (let i = 0; i < labels.length; i++) {
      const label = labels[i];

      // Mark current as generating
      const entry = state.collages.find(c => c.label === label);
      if (entry) (entry as any).status = 'generating';
      reRender();

      try {
        const result = await apiPost<{ collages: Collage[] }>(`/v1/ppt-maker/projects/${state.projectId}/collages/${label}`);
        state.collages = result.collages || [];
        // Mark remaining as pending if not yet generated
        for (let j = i + 1; j < labels.length; j++) {
          if (!state.collages.find(c => c.label === labels[j])) {
            state.collages.push({ label: labels[j], status: 'pending', filename: '', download_url: '' });
          }
        }
        reRender();
        if (i === labels.length - 1) {
          toast('三套风格方案已全部生成');
        }
      } catch (e: any) {
        // Mark as failed
        const failed = state.collages.find(c => c.label === label);
        if (failed) (failed as any).status = 'failed';
        toast(`方案 ${label} 生成失败`, 'error');
        reRender();
      }
    }
  }

  el.querySelector('#ppt-gen-collages-btn')?.addEventListener('click', () => generateSequential());

  // Per-collage regenerate with feedback
  async function regenerateSingle(label: string, feedback: string): Promise<void> {
    const progress = document.getElementById('ppt-collage-progress');
    const text = document.getElementById('ppt-collage-progress-text');
    if (progress) progress.classList.remove('hidden');
    if (text) text.textContent = `正在重新生成方案 ${label}...`;

    const result = await apiPut<{ collages: Collage[] }>(
      `/v1/ppt-maker/projects/${state.projectId}/collages/${label}`,
      { feedback },
    );
    state.collages = result.collages || [];
    if (progress) progress.classList.add('hidden');
    toast(`方案 ${label} 已重新生成`);
    reRender();
  }

  // Select collage
  el.querySelectorAll('.ppt-select-collage-btn').forEach(b => {
    b.addEventListener('click', () => {
      const idx = parseInt((b as HTMLElement).dataset.idx!);
      if (state.selectedCollageIdx === idx) return;
      state.selectedCollageIdx = idx;
      reRender();
    });
  });

  // Image preview
  el.querySelectorAll('.ppt-collage-img-wrap').forEach(wrap => {
    wrap.addEventListener('click', () => {
      const idx = parseInt((wrap as HTMLElement).dataset.idx!);
      const c = state.collages[idx];
      if (c && c.download_url) showImagePreview(c.download_url, `方案 ${c.label}`);
    });
  });

  // Per-collage regenerate buttons
  el.querySelectorAll('.ppt-regen-collage-btn').forEach(b => {
    b.addEventListener('click', async () => {
      const label = (b as HTMLElement).dataset.label || '';
      const card = b.closest('.ppt-collage-card') as HTMLElement;
      const feedback = card?.querySelector('.ppt-collage-feedback') as HTMLInputElement;
      (b as HTMLButtonElement).disabled = true;
      try {
        await regenerateSingle(label, feedback?.value?.trim() || '');
      } catch (e: any) {
        toast(`方案 ${label} 重新生成失败：${e.message || e}`, 'error');
      }
      (b as HTMLButtonElement).disabled = false;
    });
  });

  // Confirm collage
  el.querySelector('#ppt-confirm-collage')?.addEventListener('click', async () => {
    if (state.selectedCollageIdx === null) return;
    const btn = el.querySelector('#ppt-confirm-collage') as HTMLButtonElement;
    btn.disabled = true;
    btn.textContent = '保存中...';
    try {
      const labels = ['A', 'B', 'C'];
      await apiPut(`/v1/ppt-maker/projects/${state.projectId}/collages/select/`, { selected_collage: labels[state.selectedCollageIdx] });
      toast('风格方案已确认');
      navigateTo(5);
    } catch (e: any) {
      toast('保存失败：' + (e.message || e), 'error');
      btn.disabled = false;
      btn.textContent = '确认方案，进入逐页生成';
    }
  });

  // Regenerate ALL collages - sequential, DON'T clear state first
  el.querySelector('#ppt-regen-collages-btn')?.addEventListener('click', async () => {
    if (!confirm('确定要重新生成全部风格方案吗？这将替换当前方案 A/B/C。')) return;
    state.selectedCollageIdx = null;
    await generateSequential();
  });

  // Toggle prompt preview
  let promptsLoaded = false;
  el.querySelector('#ppt-toggle-prompts')?.addEventListener('click', async () => {
    const panel = el.querySelector('#ppt-prompts-panel') as HTMLElement;
    const btn = el.querySelector('#ppt-toggle-prompts') as HTMLButtonElement;
    if (!panel.classList.contains('hidden')) {
      panel.classList.add('hidden');
      btn.textContent = '查看提示词';
      return;
    }
    panel.classList.remove('hidden');
    btn.textContent = '隐藏提示词';

    if (!promptsLoaded) {
      panel.innerHTML = '<p class="text-sm text-gray-400">加载中...</p>';
      try {
        const resp = await fetch(`/api/v1/ppt-maker/projects/${state.projectId}/collages/preview`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        const prompts = data.prompts || [];
        panel.innerHTML = prompts.map((p: any) => `
          <details class="bg-white rounded-lg border border-gray-200">
            <summary class="px-4 py-2.5 cursor-pointer text-sm font-semibold text-gray-700 hover:bg-gray-50 flex items-center gap-2">
              <span class="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold">${p.label}</span>
              方案 ${p.label}
              <span class="text-gray-400 font-normal text-xs ml-auto">${p.char_count} 字符</span>
            </summary>
            <pre class="px-4 py-3 text-xs text-gray-600 whitespace-pre-wrap break-all max-h-96 overflow-y-auto border-t border-gray-100 bg-gray-50 rounded-b-lg">${esc(p.prompt)}</pre>
          </details>
        `).join('');
        promptsLoaded = true;
      } catch (e: any) {
        panel.innerHTML = `<p class="text-sm text-red-500">加载失败：${esc(e.message || String(e))}</p>`;
      }
    }
  });

  // Back
  el.querySelector('#ppt-step4-back')?.addEventListener('click', () => { navigateTo(3); });
}

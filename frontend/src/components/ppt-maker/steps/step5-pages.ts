/** Step 5: Single page generation, preview, and regeneration. */

import { apiPost, apiPut } from '../../../services/api';
import { state } from '../state';
import { esc, toast, showImagePreview, showLoading } from '../utils';
import { navigateTo, reRender } from '../navigation';
import type { PageImage } from '../types';

export function renderStep5(el: HTMLElement): void {
  el.className = 'max-w-6xl mx-auto w-full p-6';

  const hasPages = state.pageImages.length > 0;

  const html = `
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-xl font-bold text-gray-800">逐页生成</h2>
        <p class="text-sm text-gray-500 mt-1">${hasPages ? `${state.pageImages.length} 页已生成 · 点击图片查看大图` : '根据确认的大纲和风格逐页生成 PPT 页面'}</p>
      </div>
    </div>

    ${!hasPages ? `
      <div class="text-center py-16">
        <div class="text-6xl mb-4"></div>
        <p class="text-gray-500 mb-2">将根据 ${state.outlinePages.length} 页大纲逐页生成</p>
        <p class="text-sm text-gray-400 mb-6">每页约需 1-3 分钟，共 ${state.outlinePages.length} 页</p>
        <button id="ppt-gen-pages-btn" class="px-6 py-3 bg-indigo-600 text-white rounded-xl text-base font-semibold hover:bg-indigo-700 transition-colors"> 开始逐页生成</button>
      </div>
    ` : `
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" id="ppt-pages-grid">
        ${state.pageImages.filter(p => p && p.page_num).map((p, i) => pageCard(p, i)).join('')}
      </div>
      ${allPagesGenerated() ? `
        <div class="mt-6 text-center">
          <button id="ppt-done-btn" class="px-6 py-2.5 bg-green-600 text-white rounded-xl text-sm font-semibold hover:bg-green-700 transition-colors"> 全部完成，查看结果 </button>
        </div>
      ` : ''}
    `}

    <div class="flex items-center gap-3 mt-6 pt-4 border-t border-gray-200">
      <button id="ppt-step5-back" class="px-4 py-2 border border-gray-300 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors"> 上一步</button>
    </div>

  `;

  el.innerHTML = html;
  bindStep5(el);
}

function pageCard(p: PageImage, idx: number): string {
  const regenInput = state.pageRegenInputs[p.page_num] || '';
  return `
    <div class="ppt-page-card bg-white border border-gray-200 rounded-xl overflow-hidden hover:border-indigo-300 transition-all" data-idx="${idx}">
      <div class="p-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
        <span class="text-xs font-semibold text-gray-600">第 ${p.page_num} 页</span>
      </div>
      <div class="ppt-page-img-wrap relative cursor-pointer" data-idx="${idx}">
        <img src="${esc(p.download_url)}" alt="第 ${p.page_num} 页" class="w-full h-auto object-cover" style="min-height:150px;" loading="lazy">
        <div class="ppt-page-overlay absolute inset-0 bg-black/0 hover:bg-black/10 transition-colors flex items-center justify-center">
          <span class="text-white text-sm font-medium bg-black/50 px-3 py-1.5 rounded-lg opacity-0 hover:opacity-100 transition-opacity"> 查看大图</span>
        </div>
      </div>
      <div class="p-2 space-y-2">
        <input type="text" class="ppt-regen-input w-full px-2 py-1.5 border border-gray-200 rounded-lg text-xs focus:outline-none focus:border-indigo-400" placeholder="修改意见（可选）" value="${esc(regenInput)}">
        <button class="ppt-regen-page-btn w-full py-1.5 bg-indigo-50 text-indigo-700 rounded-lg text-xs font-semibold hover:bg-indigo-100 transition-colors" data-idx="${idx}"> 重新生成此页</button>
      </div>
    </div>
  `;
}

function allPagesGenerated(): boolean {
  return state.pageImages.length > 0 && state.pageImages.length >= state.outlinePages.length;
}

function bindStep5(el: HTMLElement): void {
  // Generate all pages
  el.querySelector('#ppt-gen-pages-btn')?.addEventListener('click', async () => {
    const btn = el.querySelector('#ppt-gen-pages-btn') as HTMLButtonElement;
    btn.disabled = true;
    btn.textContent = '生成中...';
    const done = showLoading(el, 'AI 正在逐页生成…', `共 ${state.outlinePages.length} 页，每页约需 1-3 分钟，请耐心等待`);

    try {
      const result = await apiPost<{ pages: PageImage[]; total: number }>(`/v1/ppt-maker/projects/${state.projectId}/pages/`);
      state.pageImages = result.pages || [];
      state.totalPagesToGenerate = result.total || state.pageImages.length;
      toast('全部页面生成完成');
      reRender();
    } catch (e: any) {
      done();
      toast('生成失败：' + (e.message || e), 'error');
      btn.disabled = false;
      btn.textContent = ' 开始逐页生成';
    }
  });

  // Image preview
  el.querySelectorAll('.ppt-page-img-wrap').forEach(wrap => {
    wrap.addEventListener('click', () => {
      const idx = parseInt((wrap as HTMLElement).dataset.idx!);
      showImagePreview(state.pageImages[idx].download_url, `第 ${state.pageImages[idx].page_num} 页`);
    });
  });

  // Regenerate single page
  el.querySelectorAll('.ppt-regen-page-btn').forEach(b => {
    b.addEventListener('click', async () => {
      const idx = parseInt((b as HTMLElement).dataset.idx!);
      const pageNum = state.pageImages[idx].page_num;
      const btnEl = b as HTMLButtonElement;

      const card = el.querySelector(`.ppt-page-card[data-idx="${idx}"]`);
      let feedback = '';
      if (card) {
        const input = card.querySelector('.ppt-regen-input') as HTMLInputElement;
        feedback = input?.value?.trim() || '';
      }

      btnEl.disabled = true;
      btnEl.textContent = '生成中...';
      const done = showLoading(el, '正在重新生成此页…', '根据修改意见调整页面，约需 1-2 分钟');

      try {
        const result = await apiPut<{ page_num: number; title: string; filename: string; download_url: string }>(
          `/v1/ppt-maker/projects/${state.projectId}/pages/${pageNum}/`,
          { modifications: feedback },
        );
        // Backend returns flat PageUpdateResponse, not wrapped in "page"
        state.pageImages[idx] = {
          page_num: result.page_num,
          title: result.title || state.pageImages[idx]?.title || '',
          filename: result.filename,
          download_url: result.download_url,
        };
        toast(`第 ${pageNum} 页已重新生成`);
        done();
        reRender();
      } catch (e: any) {
        done();
        toast('重新生成失败：' + (e.message || e), 'error');
        btnEl.disabled = false;
        btnEl.textContent = ' 重新生成此页';
      }
    });
  });

  // Sync regen inputs
  el.querySelectorAll('.ppt-regen-input').forEach(input => {
    input.addEventListener('input', () => {
      const card = (input as HTMLElement).closest('.ppt-page-card');
      if (!card) return;
      const idx = parseInt((card as HTMLElement).dataset.idx!);
      state.pageRegenInputs[state.pageImages[idx].page_num] = (input as HTMLInputElement).value;
    });
  });

  // Done
  el.querySelector('#ppt-done-btn')?.addEventListener('click', () => { navigateTo(6); });

  // Back
  el.querySelector('#ppt-step5-back')?.addEventListener('click', () => { navigateTo(4); });
}

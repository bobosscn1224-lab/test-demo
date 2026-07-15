/** Step 6: Completion — download PPTX and start new / return to list. */

import { state, resetForm } from '../state';
import { esc, toast } from '../utils';
import { navigateTo } from '../navigation';

export function renderStep6(el: HTMLElement): void {
  el.className = 'max-w-2xl mx-auto w-full p-6';

  const html = `
    <div class="text-center py-12">
      <div class="text-7xl mb-4"></div>
      <h2 class="text-2xl font-bold text-gray-800 mb-2">PPT 制作完成！</h2>
      <p class="text-gray-500 mb-2">共生成 <span class="font-bold text-indigo-600">${state.pageImages.length}</span> 页</p>
      <p class="text-sm text-gray-400 mb-8">项目 "${esc(state.formName)}" 已准备就绪</p>

      <div class="space-y-3 max-w-sm mx-auto">
        <button id="ppt-download-btn" class="w-full py-3 bg-green-600 text-white rounded-xl text-base font-semibold hover:bg-green-700 transition-colors">
          下载 PPTX 文件
        </button>
        <button id="ppt-download-loading" class="w-full py-3 bg-green-600 text-white rounded-xl text-base font-semibold hidden" disabled>
          <span class="thinking-dots"><i></i><i></i><i></i></span> 正在转换...
        </button>
        <button id="ppt-new-project-btn" class="w-full py-3 border border-gray-300 text-gray-700 rounded-xl text-sm font-semibold hover:bg-gray-50 transition-colors">
          + 开始新项目
        </button>
        <button id="ppt-back-to-list-btn" class="w-full py-2 text-gray-500 text-sm hover:text-gray-700 transition-colors">
           返回项目列表
        </button>
      </div>
    </div>
  `;

  el.innerHTML = html;
  bindStep6(el);
}

function bindStep6(el: HTMLElement): void {
  // Download PPTX
  el.querySelector('#ppt-download-btn')?.addEventListener('click', async () => {
    const btn = el.querySelector('#ppt-download-btn') as HTMLButtonElement;
    const loadingBtn = el.querySelector('#ppt-download-loading') as HTMLButtonElement;
    btn.classList.add('hidden');
    loadingBtn.classList.remove('hidden');
    try {
      // Use existing convert-async endpoint
      const sr = await fetch('/api/v1/pptx/convert-async', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: state.projectId, source: 'ppt-maker' }),
      });
      const { job_id } = await sr.json();
      if (!job_id) throw new Error('Job creation failed');

      // Poll for completion
      let attempts = 0;
      while (attempts < 120) {
        await new Promise(r => setTimeout(r, 2000));
        const jr = await fetch(`/api/v1/pptx/jobs/${job_id}`);
        const job = await jr.json();
        if (job.status === 'completed') {
          window.open(`${window.location.origin}/api/skills/download/${job.combined_pptx_filename}`, '_blank');
          toast('下载已开始');
          btn.classList.remove('hidden');
          loadingBtn.classList.add('hidden');
          return;
        }
        if (job.status === 'failed') {
          throw new Error('转换失败');
        }
        attempts++;
      }
      throw new Error('转换超时');
    } catch (e: any) {
      toast('下载失败：' + (e.message || e), 'error');
      btn.classList.remove('hidden');
      loadingBtn.classList.add('hidden');
    }
  });

  // New project
  el.querySelector('#ppt-new-project-btn')?.addEventListener('click', () => {
    resetForm();
    navigateTo(1);
  });

  // Back to list
  el.querySelector('#ppt-back-to-list-btn')?.addEventListener('click', () => {
    navigateTo(0);
  });
}

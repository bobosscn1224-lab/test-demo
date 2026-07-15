/** PPT Maker — multi-step standalone tool for generating presentations.
 *  Main entry point that composes all step modules.
 */

import { setNavigateTo, setReRender, navigateTo } from './navigation';
import { state, resumeProject } from './state';
import { buildStepBar, updateStepBar } from './step-bar';
import { renderProjectList } from './project-list';
import { renderStep1 } from './steps/step1-create';
import { renderStep2 } from './steps/step2-content';
import { renderStep3 } from './steps/step3-outline';
import { renderStep4 } from './steps/step4-collage';
import { renderStep5 } from './steps/step5-pages';
import { renderStep6 } from './steps/step6-done';
import { apiGet } from '../../services/api';

// ── Style injected once ────────────────────────────────────────────
let _stylesInjected = false;
function _injectStyles(): void {
  if (_stylesInjected) return;
  _stylesInjected = true;
  const s = document.createElement('style');
  s.textContent = `
    @keyframes pptDebugIn { from{opacity:0;transform:translateY(-8px)} to{opacity:1;transform:translateY(0)} }
  `;
  document.head.appendChild(s);
}

export function renderPptMakerPage(): HTMLElement {
  _injectStyles();
  const container = document.createElement('div');
  container.className = 'flex flex-col h-full bg-gray-50';

  const stepBar = buildStepBar(navigateTo);

  // ── Debug bar — subtle link to inspect persisted data ────────────
  const debugBar = document.createElement('div');
  debugBar.className = 'flex items-center justify-end px-4 py-1 bg-gray-100 border-b border-gray-200';
  debugBar.innerHTML = `
    <button id="ppt-debug-toggle" class="text-xs text-gray-400 hover:text-indigo-500 transition-colors flex items-center gap-1">
      <span>📋</span><span>查看持久化数据</span>
    </button>
  `;

  const bodyEl = document.createElement('div');
  bodyEl.className = 'flex-1 overflow-y-auto min-h-0';
  container.appendChild(stepBar);
  container.appendChild(debugBar);
  container.appendChild(bodyEl);

  // ── Debug modal (hidden by default) ───────────────────────────────
  const debugModal = document.createElement('div');
  debugModal.id = 'ppt-debug-modal';
  debugModal.className = 'fixed inset-0 z-[100] flex items-center justify-center hidden';
  debugModal.style.background = 'rgba(0,0,0,0.3)';
  debugModal.innerHTML = `
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-3xl mx-4 max-h-[85vh] flex flex-col" style="animation:pptDebugIn .2s ease-out">
      <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
        <div>
          <h3 class="text-lg font-bold text-gray-800">持久化数据检查器</h3>
          <p class="text-xs text-gray-400 mt-0.5" id="ppt-debug-meta">—</p>
        </div>
        <button id="ppt-debug-close" class="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors text-lg leading-none">&times;</button>
      </div>
      <div class="flex-1 overflow-y-auto p-6">
        <pre id="ppt-debug-content" class="text-xs text-gray-700 font-mono bg-gray-50 rounded-xl p-4 overflow-x-auto whitespace-pre-wrap break-all"></pre>
      </div>
      <div class="px-6 py-3 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
        <span id="ppt-debug-status" class="text-xs text-gray-400"></span>
        <button id="ppt-debug-refresh" class="px-3 py-1.5 text-xs border border-gray-300 rounded-lg text-gray-500 hover:text-indigo-600 hover:border-indigo-300 transition-colors">🔄 刷新</button>
      </div>
    </div>
  `;
  container.appendChild(debugModal);

  // ── Render function ───────────────────────────────────────────────
  function render(): void {
    bodyEl.innerHTML = '';
    switch (state.currentStep) {
      case 0: renderProjectList(bodyEl); break;
      case 1: renderStep1(bodyEl); break;
      case 2: renderStep2(bodyEl); break;
      case 3: renderStep3(bodyEl); break;
      case 4: renderStep4(bodyEl); break;
      case 5: renderStep5(bodyEl); break;
      case 6: renderStep6(bodyEl); break;
    }
    updateStepBar();
  }

  setNavigateTo((step: number) => { state.currentStep = step; render(); });
  setReRender(() => render());

  // ── Debug modal bindings ──────────────────────────────────────────
  const toggle = debugBar.querySelector('#ppt-debug-toggle') as HTMLElement;
  const modal = debugModal;
  const closeBtn = debugModal.querySelector('#ppt-debug-close') as HTMLElement;
  const refreshBtn = debugModal.querySelector('#ppt-debug-refresh') as HTMLElement;
  const contentEl = debugModal.querySelector('#ppt-debug-content') as HTMLElement;
  const metaEl = debugModal.querySelector('#ppt-debug-meta') as HTMLElement;
  const statusEl = debugModal.querySelector('#ppt-debug-status') as HTMLElement;

  async function loadDebugData(): Promise<void> {
    if (!state.projectId) {
      contentEl.innerHTML = '<div class="text-gray-400 text-center py-8">暂无项目 — 请先创建或选择一个项目</div>';
      metaEl.textContent = '无项目';
      statusEl.textContent = '';
      return;
    }
    statusEl.textContent = '加载中...';
    try {
      const d = await apiGet<any>(`/v1/ppt-maker/projects/${state.projectId}/`);
      metaEl.textContent = `${d.id} · ${d.name} · ${d.status} · ${d.outline_mode||'—'} · 风格:${d.narrative_style||'?'} · 框架:${d.narrative_framework||'?'} · 语调:${d.tone||'?'}`;
      statusEl.textContent = new Date().toLocaleTimeString();

      const scaleLabel: Record<string,string> = {compact_8_12:'8-12页',standard_15_20:'15-20页',full_25_35:'25-35页'};
      const statusOrder = ['created','content_added','outline_generated','outline_confirmed','collages_generated','pages_generated','completed'];

      contentEl.innerHTML = `
        <div class="space-y-5 text-sm">

          <!-- ====== STRUCTURE: state machine ====== -->
          <div>
            <h4 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">状态机</h4>
            <div class="flex flex-wrap gap-1.5">
              ${statusOrder.map(s => {
                const idx = statusOrder.indexOf(s);
                const curIdx = statusOrder.indexOf(d.status||'created');
                const done = idx <= curIdx;
                const active = idx === curIdx;
                return `<span class="px-2 py-0.5 rounded-full text-xs font-medium ${active ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-300' : done ? 'bg-green-50 text-green-600' : 'bg-gray-100 text-gray-400'}">${active?'▶ ':''}${s}</span>`;
              }).join('')}
            </div>
          </div>

          <!-- ====== STRUCTURE: step data presence ====== -->
          <div>
            <h4 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">数据完整性</h4>
            <div class="grid grid-cols-2 gap-2">
              ${[
                ['步骤① 需求', 'name&&purpose&&audience&&scale', '项目名、场景、受众、规模'],
                ['步骤① COSTAR', 'narrative_style&&narrative_framework&&objective&&tone', '叙事风格/框架/目标/语调'],
                ['步骤① 补充要求', 'true', '（可选字段）'],
                ['步骤② 素材', 'content_text||(content_files&&content_files.length>0)', '粘贴文本或上传文件'],
                ['步骤③ 大纲', 'outline&&outline.length>100', '大纲文本（>100字符）'],
                ['步骤③ 解析页数', 'pages&&pages.length>0', '结构化页面数组'],
                ['步骤④ 缩略图', 'collages&&collages.length===3', '3套风格方案A/B/C'],
                ['步骤④ 选择方案', 'selected_collage', '已选方案A/B/C'],
                ['步骤⑤ 逐页图', 'pages&&pages.length', '逐页高清图'],
              ].map(([label, cond, hint]) => {
                const ok = _check(d, cond as string);
                return `<div class="flex items-center gap-2 px-3 py-1.5 rounded-lg ${ok ? 'bg-green-50' : 'bg-red-50'}">
                  <span class="text-xs">${ok ? '✅' : '❌'}</span>
                  <span class="text-xs ${ok ? 'text-green-800' : 'text-red-700'} font-medium">${label}</span>
                  ${!ok ? `<span class="text-xs text-red-400">${hint}</span>` : ''}
                </div>`;
              }).join('')}
            </div>
          </div>

          <!-- ====== CONTENT: step 1 briefing ====== -->
          <div>
            <h4 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">步骤① 需求简报</h4>
            <div class="bg-gray-50 rounded-lg p-3 space-y-1.5 text-xs font-mono">
              <div><span class="text-gray-400">项目名：</span><span class="text-gray-700">${_v(d.name)}</span></div>
              <div><span class="text-gray-400">场景：</span><span class="text-gray-700">${_v(d.purpose)}</span></div>
              <div><span class="text-gray-400">受众：</span><span class="text-gray-700">${_v(d.audience)}</span></div>
              <div><span class="text-gray-400">规模：</span><span class="text-gray-700">${_v(d.scale)} ${scaleLabel[d.scale] ? '('+scaleLabel[d.scale]+')' : ''}</span></div>
              <div><span class="text-gray-400">视觉风格：</span><span class="text-gray-700">${(d.styles||[]).join(', ') || '（Step4选择）'}</span></div>
              <div><span class="text-gray-400">叙事风格：</span><span class="text-indigo-600 font-semibold">${{auto:'🤖自动',narrative:'📖叙事故事',data_report:'📊数据汇报',business_proposal:'💼商业方案',technical:'🔧技术拆解'}[d.narrative_style] || d.narrative_style || '—'}</span></div>
              <div><span class="text-gray-400">叙事框架：</span><span class="text-indigo-600 font-semibold">${{auto:'🤖自动',conflict_driven:'⚡冲突驱动',scr:'📋SCR',problem_driven:'🔍问题驱动',opportunity_driven:'🚀机会驱动',abt:'🎬ABT',hook_progressive:'🪝钩子递进'}[d.narrative_framework] || d.narrative_framework || '—'}</span></div>
              <div><span class="text-gray-400">汇报目标：</span><span class="text-gray-700">${{auto:'🤖自动',drive_decision:'✅促成决策',show_results:'📊展示成果',secure_resources:'💰争取资源',build_consensus:'🤝建立共识',transfer_knowledge:'📖传递认知'}[d.objective] || d.objective || '—'}</span></div>
              <div><span class="text-gray-400">语调：</span><span class="text-gray-700">${{auto:'🤖自动',professional:'👔专业严谨',storytelling:'📖生动故事',inspirational:'🔥激励人心',concise:'⚡简洁有力',humorous:'😄幽默风趣'}[d.tone] || d.tone || '—'}</span></div>
              <div><span class="text-gray-400">大纲模式：</span><span class="${d.outline_mode==='enhanced'?'text-indigo-600 font-semibold':'text-gray-700'}">${d.outline_mode==='enhanced'?'✨ 增强':'📋 普通'}</span></div>
              <div><span class="text-gray-400">补充要求：</span><span class="text-gray-700">${d.key_message || '—'}</span></div>
            </div>
          </div>

          <!-- ====== CONTENT: step 2 materials ====== -->
          <div>
            <h4 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">步骤② 素材</h4>
            <div class="bg-gray-50 rounded-lg p-3 space-y-2 text-xs">
              <div><span class="text-gray-400">粘贴文本：</span><span class="text-gray-700">${d.content_text ? d.content_text.length+' 字符' : '❌ 空'}</span></div>
              <div><span class="text-gray-400">上传文件：</span><span class="text-gray-700">${(d.content_files||[]).length} 个</span></div>
              ${(d.content_files||[]).map((f:any) => `<div class="ml-4 text-gray-500 font-mono">${typeof f==='string'?f:f.path||f.name||JSON.stringify(f)}</div>`).join('')}
              ${d.content_text ? `<details class="mt-2"><summary class="cursor-pointer text-indigo-500 hover:text-indigo-600">展开文本内容 (${d.content_text.length} 字符)</summary><pre class="mt-2 text-xs text-gray-600 bg-white rounded-lg p-3 max-h-48 overflow-y-auto whitespace-pre-wrap">${_esc(d.content_text)}</pre></details>` : ''}
            </div>
          </div>

          <!-- ====== CONTENT: step 3 outline ====== -->
          <div>
            <h4 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">步骤③ 大纲</h4>
            <div class="bg-gray-50 rounded-lg p-3 space-y-2 text-xs">
              <div><span class="text-gray-400">大纲长度：</span><span class="text-gray-700">${(d.outline||'').length} 字符</span></div>
              <div><span class="text-gray-400">解析页数：</span><span class="text-gray-700">${(d.outline_pages||d.pages||[]).length} 页</span></div>
              ${(d.outline_pages||d.pages||[]).length > 0 ? `
                <div class="space-y-1 mt-2">
                  ${(d.outline_pages||d.pages||[]).map((p:any) => `
                    <div class="flex items-start gap-2 px-2 py-1 bg-white rounded">
                      <span class="font-mono text-gray-400 w-8 flex-shrink-0">#${p.page_num}</span>
                      <div class="min-w-0">
                        <span class="text-gray-700 font-medium">${_esc(p.title||'—')}</span>
                        <span class="text-gray-400 ml-2">${p.type||'content'}</span>
                        ${p.visual_hint ? `<span class="text-green-500 ml-1" title="有画面构思">🎨</span>` : '<span class="text-red-400 ml-1" title="缺少画面构思">⚠️</span>'}
                        ${p.core_message ? '' : '<span class="text-red-400 ml-1" title="缺少核心信息">⚠️</span>'}
                        ${(p.points||[]).length === 0 ? '<span class="text-red-400 ml-1" title="缺少要点">⚠️</span>' : ''}
                      </div>
                    </div>
                  `).join('')}
                </div>
              ` : '<div class="text-red-400">❌ 未解析出页面</div>'}
              ${d.outline ? `<details class="mt-2"><summary class="cursor-pointer text-indigo-500 hover:text-indigo-600">展开完整大纲文本</summary><pre class="mt-2 text-xs text-gray-600 bg-white rounded-lg p-3 max-h-64 overflow-y-auto whitespace-pre-wrap">${_esc(d.outline)}</pre></details>` : ''}
            </div>
          </div>

          <!-- ====== CONTENT: step 4+ ====== -->
          <div>
            <h4 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">步骤④ 缩略图 & 步骤⑤ 逐页图</h4>
            <div class="bg-gray-50 rounded-lg p-3 space-y-1.5 text-xs font-mono">
              <div><span class="text-gray-400">生成缩略图：</span><span class="text-gray-700">${(d.collages||[]).length} 张</span></div>
              ${(d.collages||[]).map((c:any) => `<div class="ml-4 text-gray-500">${c.label}: ${c.filename||'—'}</div>`).join('')}
              <div><span class="text-gray-400">已选方案：</span><span class="text-gray-700">${d.selected_collage||'❌ 未选择'}</span></div>
              <div><span class="text-gray-400">逐页图：</span><span class="text-gray-700">${(d.page_images||[]).length} 张</span></div>
              <div class="pt-2 border-t border-gray-200 mt-2">
                <button id="ppt-debug-preview-collage" class="px-3 py-1.5 text-xs bg-indigo-50 text-indigo-600 rounded-lg hover:bg-indigo-100 transition-colors font-medium">🔍 预览生图 Prompt（不实际生成）</button>
                <span id="ppt-debug-prompt-status" class="text-xs text-gray-400 ml-2 hidden"></span>
              </div>
              <div id="ppt-debug-collage-prompts" class="hidden mt-2 space-y-3"></div>
            </div>
          </div>

          <!-- ====== RAW JSON fallback ====== -->
          <details>
            <summary class="cursor-pointer text-xs font-bold text-gray-400 uppercase tracking-wider hover:text-gray-500">完整 JSON</summary>
            <pre class="mt-2 text-xs text-gray-600 bg-gray-50 rounded-lg p-3 max-h-96 overflow-auto">${JSON.stringify(d, null, 2)}</pre>
          </details>

        </div>`;
    } catch (e: any) {
      contentEl.innerHTML = `<div class="text-red-500 text-center py-8">加载失败：${_esc(e.message || String(e))}</div>`;
      metaEl.textContent = '错误';
      statusEl.textContent = '加载失败';
    }
  }

  // ── tiny helpers (in scope for loadDebugData) ──────────────────
  function _v(s: any): string { return s ? String(s) : '❌ 未填写'; }
  function _esc(s: string): string { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function _check(d: any, cond: string): boolean {
    try {
      const fn = new Function('d', `with(d){ return !!(${cond}); }`);
      return fn(d);
    } catch { return false; }
  }

  toggle.addEventListener('click', () => {
    modal.classList.remove('hidden');
    loadDebugData();
    refreshBtn.focus();
  });

  closeBtn.addEventListener('click', () => modal.classList.add('hidden'));
  modal.addEventListener('click', (e) => {
    if ((e.target as HTMLElement).id === 'ppt-debug-modal') modal.classList.add('hidden');
  });
  refreshBtn.addEventListener('click', loadDebugData);

  // Preview collage prompts
  const previewBtn = debugModal.querySelector('#ppt-debug-preview-collage') as HTMLElement;
  const promptStatus = debugModal.querySelector('#ppt-debug-prompt-status') as HTMLElement;
  const promptContainer = debugModal.querySelector('#ppt-debug-collage-prompts') as HTMLElement;

  previewBtn?.addEventListener('click', async () => {
    if (!state.projectId) return;
    promptStatus.textContent = '加载中...';
    promptStatus.classList.remove('hidden');
    promptContainer.classList.add('hidden');
    try {
      const data = await apiGet<any>(`/v1/ppt-maker/projects/${state.projectId}/collages/preview`);
      promptStatus.classList.add('hidden');
      promptContainer.classList.remove('hidden');
      promptContainer.innerHTML = `
        <div class="bg-white rounded-lg p-3 text-xs space-y-1 mb-2">
          <span class="text-gray-400">prompt 上下文：</span>
          <span>场景=${data.project_context.purpose||'—'} 受众=${data.project_context.audience||'—'} 规模=${data.project_context.scale||'—'} 风格=[${(data.project_context.styles||[]).join(',')||'—'}] 关键信息=${data.project_context.key_message||'—'} 素材=${data.project_context.content_text_length}字 大纲=${data.project_context.outline_length}字</span>
        </div>
        ${(data.prompts||[]).map((p:any) => `
          <details class="bg-white rounded-lg border border-gray-100">
            <summary class="px-3 py-2 cursor-pointer font-semibold text-xs flex items-center gap-2 hover:bg-gray-50">
              <span class="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold">${p.label}</span>
              <span>方案 ${p.label}</span>
              <span class="text-gray-400 font-normal ml-auto">${p.char_count} 字符</span>
            </summary>
            <pre class="px-4 py-3 text-xs text-gray-700 whitespace-pre-wrap break-all max-h-96 overflow-y-auto border-t border-gray-100 bg-gray-50 rounded-b-lg">${_esc(p.prompt)}</pre>
          </details>
        `).join('')}
        <p class="text-xs text-gray-400 mt-1">⚠️ API 限制 4000 字符，超出部分会被截断</p>
      `;
    } catch (e: any) {
      promptStatus.textContent = '加载失败：' + (e.message || e);
    }
  });

  // Keyboard shortcut: Ctrl+Shift+D to toggle debug panel
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'D') {
      e.preventDefault();
      if (modal.classList.contains('hidden')) {
        modal.classList.remove('hidden');
        loadDebugData();
      } else {
        modal.classList.add('hidden');
      }
    }
  });

  render();
  return container;
}

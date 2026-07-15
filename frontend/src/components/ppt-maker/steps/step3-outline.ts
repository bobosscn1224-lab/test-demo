/** Step 3: Outline — left list + right detail panel (split layout). */

import { apiPost, apiPut } from '../../../services/api';
import { state } from '../state';
import { esc, toast, showLoading } from '../utils';
import { navigateTo, reRender } from '../navigation';
import type { OutlinePage, OutlineResponse } from '../types';

function isSkeletonOnly(): boolean {
  // Skeleton mode stays until ALL pages have real points (not just title repetition)
  const hasPages = state.outlinePages.length > 0;
  const allFilled = hasPages && state.outlinePages.every(p => {
    const pts = p.points || [];
    return pts.length > 0 && pts.some(pt => pt.length > 5); // real content, not empty
  });
  return hasPages && !allFilled;
}

export function renderStep3(el: HTMLElement): void {
  el.className = 'flex flex-col';
  el.style.height = '100%';
  el.style.overflow = 'hidden';

  // Ensure outlinePages items are valid
  state.outlinePages = (state.outlinePages || []).filter(p => p && p.page_num);

  const hasOutline = state.outlinePages.length > 0;
  const skeletonMode = isSkeletonOnly();
  const filledCount = state.outlinePages.filter(p => (p.points||[]).length > 0).length;
  const selectedIdx = state.selectedOutlineIdx ?? 0;
  const selected = state.outlinePages[selectedIdx] || null;

  const html = `
    <!-- Top bar -->
    <div class="flex items-center justify-between px-6 py-3 border-b border-gray-200 bg-white flex-shrink-0">
      <div class="flex items-center gap-3">
        <button id="ppt-step3-back" class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">← 上一步</button>
        <h2 class="text-lg font-bold text-gray-800">PPT 大纲</h2>
        <span class="text-sm text-gray-400">${hasOutline ? `${state.outlinePages.length} 页` : ''}</span>
      </div>
      <div class="flex items-center gap-2">
        ${hasOutline ? `
          <button id="ppt-save-all" class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">💾 暂存</button>
          ${!skeletonMode ? `
            <button id="ppt-refill-all-split" class="px-3 py-1.5 border border-amber-300 rounded-lg text-sm text-amber-700 hover:bg-amber-50 transition-colors">🔄 重新填充全部</button>
            <button id="ppt-confirm-outline" class="px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition-colors">确认大纲</button>
          ` : `<span class="text-xs text-amber-500">⚠️ 填充完成后可确认</span>`}
        ` : ''}
        <button id="ppt-regenerate-outline" class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">${hasOutline ? '重新生成' : '生成大纲'}</button>
      </div>
    </div>

    ${!hasOutline ? `
    <!-- No outline yet -->
    <div class="flex-1 flex items-center justify-center">
      <div class="text-center max-w-md">
        <p class="text-gray-500 mb-4">准备根据你提供的素材和需求生成 PPT 大纲</p>
        <div class="mb-4">
          <p class="text-sm font-semibold text-gray-700 mb-2">选择生成模式</p>
          <div class="flex gap-3 mb-3" id="ppt-outline-mode">
            <label class="ppt-mode-option flex-1 flex flex-col items-center gap-1 px-4 py-3 border-2 rounded-xl cursor-pointer transition-all ${state.outlineMode === 'conservative' ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 bg-white hover:border-gray-300'}">
              <input type="radio" name="outline-mode" value="conservative" ${state.outlineMode === 'conservative' ? 'checked' : ''} class="sr-only">
              <span class="text-sm font-semibold ${state.outlineMode === 'conservative' ? 'text-indigo-700' : 'text-gray-700'}">普通模式</span>
              <span class="text-xs ${state.outlineMode === 'conservative' ? 'text-indigo-500' : 'text-gray-400'}">仅基于素材生成</span>
            </label>
            <label class="ppt-mode-option flex-1 flex flex-col items-center gap-1 px-4 py-3 border-2 rounded-xl cursor-pointer transition-all ${state.outlineMode === 'enhanced' ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 bg-white hover:border-gray-300'}">
              <input type="radio" name="outline-mode" value="enhanced" ${state.outlineMode === 'enhanced' ? 'checked' : ''} class="sr-only">
              <span class="text-sm font-semibold ${state.outlineMode === 'enhanced' ? 'text-indigo-700' : 'text-gray-700'}">✨ 增强模式</span>
              <span class="text-xs ${state.outlineMode === 'enhanced' ? 'text-indigo-500' : 'text-gray-400'}">素材+行业知识</span>
            </label>
          </div>
        </div>
        <button id="ppt-gen-outline-btn" class="px-6 py-3 bg-indigo-600 text-white rounded-xl text-base font-semibold hover:bg-indigo-700 transition-colors">生成大纲</button>
        <div id="ppt-outline-loading" class="mt-6 hidden">
          <div class="flex items-center justify-center gap-2 text-indigo-600">
            <span class="thinking-dots"><i></i><i></i><i></i></span>
            <span class="text-sm">AI 正在分析素材并生成大纲...</span>
          </div>
        </div>
      </div>
    </div>
    ` : skeletonMode ? `
    <!-- ====== SKELETON PHASE: review narrative strategy, then fill page by page ====== -->
    <div class="flex-1 overflow-y-auto">
      <div class="max-w-3xl mx-auto px-6 py-6">
        <div class="bg-indigo-50 border border-indigo-200 rounded-xl p-5 mb-6">
          <h3 class="text-sm font-bold text-indigo-800 mb-2">📋 叙事策略提案</h3>
          <p class="text-xs text-indigo-600 mb-3">AI 已完成整体叙事逻辑设计，共 <span class="font-bold">${state.outlinePages.length}</span> 页。请确认思路后再逐页生成详细内容。</p>

          <!-- Page logic list -->
          <div class="space-y-2" id="ppt-skeleton-cards">
            ${state.outlinePages.map((p, i) => {
              const filled = (p.points||[]).length > 0;
              return `<div class="ppt-skel-card bg-white rounded-lg border border-gray-100 overflow-hidden" data-idx="${i}">
                <div class="ppt-skel-header flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50 transition-colors select-none">
                  <span class="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 ${filled ? 'bg-green-500' : 'bg-indigo-500'}">${p.page_num}</span>
                  <div class="min-w-0 flex-1">
                    <p class="text-sm font-semibold text-gray-800 truncate">${esc(p.title || '第'+p.page_num+'页')}</p>
                    ${p.role ? `<p class="text-xs text-gray-400 mt-0.5 truncate">${esc(p.role)}</p>` : ''}
                  </div>
                  <span class="text-xs flex-shrink-0 ${filled ? 'text-green-600' : 'text-indigo-400'}">${filled ? '✅' : '⏳'}</span>
                  <span class="ppt-skel-chevron text-gray-300 text-sm transition-transform">▶</span>
                </div>
                <div class="ppt-skel-body hidden px-3 pb-3 border-t border-gray-50">
                  ${p.role ? `<div class="mt-2 text-xs"><span class="text-gray-400">角色：</span><span class="text-gray-600">${esc(_clean(p.role))}</span></div>` : ''}
                  ${p.core_message ? `<div class="mt-2 text-xs"><span class="text-gray-400">核心信息：</span><span class="text-gray-700">${esc(_clean(p.core_message))}</span></div>` : ''}
                  ${p.points?.length ? `<div class="mt-2"><p class="text-xs text-gray-400 mb-1">要点：</p><ul class="space-y-1">${p.points.map(pt => `<li class="text-xs text-gray-600 flex gap-1"><span class="text-indigo-300">•</span>${esc(_clean(pt))}</li>`).join('')}</ul></div>` : ''}
                  ${p.visual_hint ? `<div class="mt-2 text-xs"><span class="text-gray-400">视觉建议：</span><span class="text-gray-500">${esc(_clean(p.visual_hint))}</span></div>` : ''}
                  ${!filled ? `<p class="text-xs text-amber-500 mt-2">⏳ 尚未填充详细内容</p>` : ''}
                </div>
              </div>`;
            }).join('')}
          </div>
        </div>

        <!-- Progress -->
        <div class="mb-3">
          <div class="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
            <div class="bg-indigo-500 h-2 rounded-full transition-all duration-300" style="width:${Math.round(filledCount/state.outlinePages.length*100)}%"></div>
          </div>
          <p class="text-xs text-gray-400 mt-1">${filledCount} / ${state.outlinePages.length} 页已填充</p>
        </div>

        ${filledCount < state.outlinePages.length ? `
          <div class="flex gap-3 justify-center">
            <button id="ppt-fill-next-btn" class="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors">▶ 逐页填充内容</button>
            <button id="ppt-fill-all-btn" class="px-5 py-2.5 border border-gray-300 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors">⏩ 一次全部填充</button>
          </div>
        ` : `
          <p class="text-green-600 text-sm font-semibold mb-3">✅ 全部页面已填充完毕</p>
          <div class="flex gap-3 justify-center">
            <button id="ppt-view-outline-btn" class="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors">查看完整大纲</button>
            <button id="ppt-fill-all-btn" class="px-5 py-2.5 border border-gray-300 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors">重新填充全部</button>
          </div>
        `}
      </div>
    </div>
    ` : `
    <!-- Centered split layout — both sides independently scrollable -->
    <div class="flex-1 flex justify-center min-h-0 overflow-hidden">
      <div class="flex w-full max-w-5xl min-h-0">
      <!-- LEFT: page list -->
      <div class="w-56 border-r border-gray-200 overflow-y-auto bg-gray-50 flex-shrink-0" id="ppt-outline-list">
        ${state.outlinePages.map((p, i) => `
          <div class="ppt-outline-item px-4 py-3 border-b border-gray-100 cursor-pointer transition-colors ${i === selectedIdx ? 'bg-indigo-50 border-l-2 border-l-indigo-500' : 'bg-white hover:bg-gray-50 border-l-2 border-l-transparent'}" data-idx="${i}">
            <div class="flex items-center gap-2">
              <span class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0" style="background:${_colorForType(p.type)}">${p.page_num}</span>
              <div class="min-w-0">
                <p class="text-sm font-medium text-gray-800 truncate">${esc(p.title || `第${p.page_num}页`)}</p>
                <p class="text-xs text-gray-400">${esc(p.type)}</p>
              </div>
            </div>
          </div>
        `).join('')}
      </div>

      <!-- RIGHT: page detail -->
      <div class="flex-1 overflow-y-auto ${state.outlineSaved ? 'bg-white' : 'bg-amber-50/30'}" id="ppt-outline-detail">
        <div class="${state.outlineSaved ? '' : 'bg-amber-100 border-b border-amber-300'} px-4 py-2 text-center">
          ${state.outlineSaved
            ? '<span class="text-xs text-gray-400">✏️ 编辑模式 — 修改后点击「💾 暂存」保存全部</span>'
            : '<span class="text-sm text-amber-800 font-medium">👁️ 预览模式 — 浏览内容，可重新生成单页。满意后点击顶部「💾 暂存」进入编辑</span>'}
        </div>
        <div class="p-6 pb-12">
          ${selected ? _detailPanel(selected, selectedIdx) : '<p class="text-gray-400 text-center mt-20">选择左侧页面查看详情</p>'}
        </div>
      </div>
      </div><!-- close inner flex -->
    </div><!-- close centering wrapper -->
    `}

  `;

  el.innerHTML = html;
  bindStep3(el);
}

// Inline keyframe for modal animation — injected once
let _modalStyleInjected = false;
function _injectModalStyle(): void {
  if (_modalStyleInjected) return;
  _modalStyleInjected = true;
  const style = document.createElement('style');
  style.textContent = `
    @keyframes pptModalIn {
      from { opacity: 0; transform: translateY(-12px) scale(.97); }
      to   { opacity: 1; transform: translateY(0) scale(1); }
    }
  `;
  document.head.appendChild(style);
}

// ── Detail panel (right side) ─────────────────────────────────────

function _detailPanel(p: OutlinePage, idx: number): string {
  const typeColor = _colorForType(p.type);
  const canEdit = state.outlineSaved;
  return `
    <div class="max-w-2xl">
      <!-- Page header -->
      <div class="flex items-center gap-3 mb-4">
        <span class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold text-white" style="background:${typeColor}">${p.page_num}</span>
        <span class="px-2 py-0.5 rounded-full text-xs font-medium" style="background:${typeColor}20;color:${typeColor}">${esc(p.type)}</span>
        <span class="text-xs text-gray-400">${p.role ? esc(p.role) : ''}</span>
        ${!canEdit ? '<span class="text-xs text-amber-500 bg-amber-50 px-2 py-0.5 rounded-full">预览模式</span>' : ''}
      </div>

      ${canEdit ? `
        <!-- Editable mode (after save) -->
        <div class="space-y-5">
          <div>
            <label class="block text-sm font-semibold text-gray-600 mb-1">标题</label>
            <input class="ppt-field-title w-full px-4 py-2.5 border border-gray-300 rounded-lg text-lg font-bold focus:outline-none focus:border-indigo-500" value="${esc(p.title)}">
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-600 mb-1">核心信息</label>
            <textarea class="ppt-field-msg w-full px-4 py-3 border border-gray-300 rounded-lg text-sm resize-y focus:outline-none focus:border-indigo-500" rows="4">${esc(p.core_message)}</textarea>
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-600 mb-1">要点（每行一个）</label>
            <textarea class="ppt-field-points w-full px-4 py-3 border border-gray-300 rounded-lg text-sm resize-y focus:outline-none focus:border-indigo-500" rows="6">${esc(p.points.join('\n'))}</textarea>
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-600 mb-1">画面构思和视觉建议</label>
            <textarea class="ppt-field-visual w-full px-4 py-3 border border-gray-300 rounded-lg text-sm resize-y focus:outline-none focus:border-indigo-500" rows="3">${esc(p.visual_hint)}</textarea>
          </div>
          <div class="flex gap-2 pt-4 border-t border-gray-200">
            <textarea class="ppt-regen-feedback flex-1 px-4 py-2.5 border border-gray-300 rounded-lg text-sm resize-none focus:outline-none focus:border-amber-500" rows="3" placeholder="输入修改意见后重新生成..."></textarea>
            <button class="ppt-regen-detail px-5 py-2.5 bg-amber-500 text-white rounded-lg text-sm font-medium hover:bg-amber-600 transition-colors flex-shrink-0">🔄 重新生成</button>
          </div>
        </div>
      ` : `
        <!-- Preview mode (before save) -->
        <h3 class="text-xl font-bold text-gray-900 mb-4">${esc(p.title)}</h3>
        ${p.core_message ? `<div class="bg-indigo-50 border-l-4 border-indigo-400 rounded-r-lg p-5 mb-5"><p class="text-sm font-semibold text-indigo-800 mb-1">核心信息</p><p class="text-sm text-indigo-900 leading-relaxed">${esc(p.core_message)}</p></div>` : ''}
        ${p.points.length > 0 ? `<div class="mb-5"><p class="text-sm font-semibold text-gray-600 mb-2">内容要点</p><ul class="space-y-2">${p.points.map(pt => `<li class="flex items-start gap-2 text-sm text-gray-700 leading-relaxed"><span class="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 flex-shrink-0"></span><span>${esc(pt)}</span></li>`).join('')}</ul></div>` : ''}
        ${p.visual_hint ? `<div class="bg-gray-50 rounded-lg p-4 mb-5"><p class="text-sm font-semibold text-gray-500 mb-1">画面构思和视觉建议</p><p class="text-sm text-gray-600 leading-relaxed">${esc(p.visual_hint)}</p></div>` : ''}
        <div class="flex gap-2 pt-4 border-t border-gray-200">
          <textarea class="ppt-regen-feedback flex-1 px-4 py-2.5 border border-gray-300 rounded-lg text-sm resize-none focus:outline-none focus:border-amber-500" rows="3" placeholder="输入修改意见后重新生成..."></textarea>
          <button class="ppt-regen-detail px-5 py-2.5 bg-amber-500 text-white rounded-lg text-sm font-medium hover:bg-amber-600 transition-colors flex-shrink-0">🔄 重新生成</button>
        </div>
      `}
    </div>
  `;
}

function _colorForType(t: string): string {
  const m: Record<string, string> = { cover: '#3b82f6', toc: '#6b7280', content: '#10b981', summary: '#ec4899' };
  return m[t] || '#6b7280';
}

// ── Bind events ───────────────────────────────────────────────────

// ── Skeleton phase: fill page by page ──────────────────────────────

async function fillNextPage(el: HTMLElement): Promise<void> {
  const nextIdx = state.outlinePages.findIndex(p => (p.points||[]).length === 0);
  if (nextIdx < 0) return;

  const skeleton = JSON.stringify(state.outlinePages.map(p => ({
    page_num: p.page_num, title: p.title, type: p.type,
    role: p.role, core_message: p.core_message,
  })));

  const done = showLoading(el, `正在生成第 ${nextIdx+1} 页…`, `${nextIdx+1} / ${state.outlinePages.length} 页`);
  try {
    const result = await apiPost<OutlineResponse>(
      `/v1/ppt-maker/projects/${state.projectId}/outline/?mode=${state.outlineMode}&stage=fill_page&page_index=${nextIdx}`,
      { skeleton, page_index: nextIdx }
    );
    if (result.pages?.length > 0) {
      const p = result.pages.find(pg => pg.page_num === nextIdx + 1) || result.pages[0];
      _mergePage(state.outlinePages[nextIdx], p);
    }
    done();
    reRender();
  } catch (e: any) {
    done();
    toast(`第 ${nextIdx+1} 页填充失败：${e.message || e}`, 'error');
    reRender();
  }
}

async function fillAllPages(el: HTMLElement, force: boolean = false): Promise<void> {
  const total = state.outlinePages.length;
  const skeleton = JSON.stringify(state.outlinePages.map(p => ({
    page_num: p.page_num, title: p.title, type: p.type,
    role: p.role, core_message: p.core_message,
  })));

  const done = showLoading(el, force ? '正在重新填充全部…' : '正在逐页填充…', `0 / ${total} 页`);
  for (let i = 0; i < total; i++) {
    if (!force && (state.outlinePages[i].points||[]).length > 0) continue; // skip only on initial fill

    // Update loading text
    const overlay = el.querySelector('.ppt-loading-overlay');
    if (overlay) {
      const sub = overlay.querySelector('p:last-child');
      if (sub) sub.textContent = `${i+1} / ${total} 页`;
    }

    try {
      const result = await apiPost<OutlineResponse>(
        `/v1/ppt-maker/projects/${state.projectId}/outline/?mode=${state.outlineMode}&stage=fill_page&page_index=${i}`,
        { skeleton, page_index: i }
      );
      if (result.pages?.length > 0) {
        const p = result.pages.find(pg => pg.page_num === i + 1) || result.pages[0];
        _mergePage(state.outlinePages[i], p);
      }
    } catch (e: any) {
      // Continue with next page even if one fails
      toast(`第 ${i+1} 页填充失败，继续下一页`, 'error');
    }
  }
  done();
  reRender();
}

function bindStep3(el: HTMLElement): void {
  // Skeleton phase: toggle card expand/collapse
  el.querySelectorAll('.ppt-skel-header').forEach(header => {
    header.addEventListener('click', () => {
      const card = header.closest('.ppt-skel-card') as HTMLElement;
      const body = card?.querySelector('.ppt-skel-body') as HTMLElement;
      const chevron = card?.querySelector('.ppt-skel-chevron') as HTMLElement;
      if (body) {
        body.classList.toggle('hidden');
        if (chevron) chevron.textContent = body.classList.contains('hidden') ? '▶' : '▼';
      }
    });
  });
  // Skeleton phase: fill next page
  el.querySelector('#ppt-fill-next-btn')?.addEventListener('click', () => fillNextPage(el));
  // Skeleton phase: fill all pages — force if all already have (stale) points
  el.querySelector('#ppt-fill-all-btn')?.addEventListener('click', () => {
    const allHavePoints = state.outlinePages.every(p => (p.points||[]).length > 0);
    fillAllPages(el, allHavePoints);
  });
  // Skeleton phase: view full outline — force exit skeleton mode
  el.querySelector('#ppt-view-outline-btn')?.addEventListener('click', () => {
    state.outlineSaved = true;
    reRender();
  });

  // Mode toggle
  el.querySelectorAll('input[name="outline-mode"]').forEach(r => {
    r.addEventListener('change', () => {
      state.outlineMode = (r as HTMLInputElement).value;
      reRender();
    });
  });

  // Generate outline — use skeleton stage for page-by-page quality
  el.querySelector('#ppt-gen-outline-btn')?.addEventListener('click', async () => {
    const btn = el.querySelector('#ppt-gen-outline-btn') as HTMLButtonElement;
    btn.disabled = true; btn.textContent = '生成中...';
    const done = showLoading(el, 'AI 正在生成大纲骨架…', '先生成页面结构，再逐页填充详细内容');
    try {
      const result = await apiPost<OutlineResponse>(`/v1/ppt-maker/projects/${state.projectId}/outline/?mode=${state.outlineMode}&stage=skeleton`);
      state.outlinePages = result.pages || [];
      state.selectedOutlineIdx = 0;
      state.outlineSaved = false;  // fresh generation, not saved yet
      if (state.outlinePages.length === 0 && result.outline) {
        state.outlinePages = [{page_num:1, type:'content', title:'大纲原文', role:'', core_message:'', points: result.outline.split('\n').filter(l => l.trim()), visual_hint:''}];
      }
      toast(`大纲已生成，共 ${state.outlinePages.length} 页`);
      reRender();
    } catch (e: any) {
      done();
      toast('生成失败：' + (e.message || e), 'error');
      btn.disabled = false; btn.textContent = '生成大纲';
    }
  });

  // Select page from left list — sync current edits before switching
  el.querySelectorAll('.ppt-outline-item').forEach(item => {
    item.addEventListener('click', () => {
      _syncDetailToState(el);  // save current edits to state
      state.selectedOutlineIdx = parseInt((item as HTMLElement).dataset.idx!);
      reRender();
    });
  });

  // Global save (暂存) — sync detail panel edits to state, then persist all pages
  el.querySelector('#ppt-save-all')?.addEventListener('click', async () => {
    // Sync current detail panel edits to state first
    _syncDetailToState(el);
    try {
      const text = state.outlinePages.map(p =>
        `### 第${p.page_num}页\n**类型**：${p.type}\n**标题**：${p.title}\n**角色**：${p.role}\n**核心信息**：${p.core_message}\n**要点**：\n${p.points.map(pt => `- ${pt}`).join('\n')}\n**视觉建议**：${p.visual_hint}`
      ).join('\n\n');
      await apiPut(`/v1/ppt-maker/projects/${state.projectId}/outline/`, { outline: text });
      state.outlineSaved = true;
      toast('已暂存全部大纲 — 进入编辑模式');
      reRender();  // switch from preview to edit mode
    } catch { toast('暂存失败', 'error'); }
  });

  // Split layout: refill all pages (preserve outline structure)
  el.querySelector('#ppt-refill-all-split')?.addEventListener('click', () => fillAllPages(el, true));

  // Per-page regenerate (class selector, not ID — there are 2 instances)
  el.querySelectorAll('.ppt-regen-detail').forEach(btn => {
    btn.addEventListener('click', async () => {
      const feedbackEl = el.querySelector('.ppt-regen-feedback') as HTMLTextAreaElement;
      const feedback = feedbackEl?.value?.trim() || '';
      (btn as HTMLButtonElement).disabled = true; btn.textContent = '生成中...';
      const done = showLoading(el, '正在重新生成此页…', '根据修改意见调整页面内容');
      try {
        const result = await apiPost<OutlineResponse>(
          `/v1/ppt-maker/projects/${state.projectId}/outline/?mode=${state.outlineMode}&stage=fill_page&page_index=${state.selectedOutlineIdx}`,
          { feedback, page_index: state.selectedOutlineIdx, skeleton: JSON.stringify(state.outlinePages.map(p => ({ page_num: p.page_num, title: p.title, type: p.type, role: p.role, core_message: p.core_message }))) },
        );
        if (result.pages?.length > 0) {
          const idx = state.selectedOutlineIdx ?? 0;
          const newPage = result.pages[0];
          _mergePage(state.outlinePages[idx], newPage);
          toast('已更新');
        }
      } catch (e: any) {
        done();
        toast('重新生成失败：' + (e.message || e), 'error');
      }
      done();
      (btn as HTMLButtonElement).disabled = false; btn.textContent = '🔄 重新生成';
      reRender();
    });
  });

  // Regenerate all — modal rendered to document.body to avoid overflow clipping
  let _regenModal: HTMLElement | null = null;

  const regenBtn = el.querySelector('#ppt-regenerate-outline');
  if (!regenBtn) {
    console.error('CRITICAL: #ppt-regenerate-outline NOT FOUND in DOM');
    return;
  }
  regenBtn.addEventListener('click', () => {
    _injectModalStyle();
    _regenModal = document.createElement('div');
    _regenModal.id = 'ppt-regen-modal';
    _regenModal.style.cssText = 'position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.35);backdrop-filter:blur(2px);';
    _regenModal.innerHTML = `
      <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden" style="animation:pptModalIn .2s ease-out;">
        <div class="px-6 py-5 border-b border-gray-100">
          <h3 class="text-lg font-bold text-gray-800">重新生成大纲</h3>
          <p class="text-sm text-gray-500 mt-1">将基于已有素材和知识库重新生成全部页面</p>
        </div>
        <div class="px-6 py-4 space-y-4">
          <div>
            <label class="block text-sm font-semibold text-gray-700 mb-2">生成模式</label>
            <div class="grid grid-cols-2 gap-3" id="ppt-regen-mode-selector">
              <label class="ppt-regen-mode-opt flex flex-col items-center gap-1 px-4 py-3 border-2 rounded-xl cursor-pointer transition-all ${state.outlineMode === 'conservative' ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 bg-white hover:border-gray-300'}">
                <input type="radio" name="regen-mode" value="conservative" ${state.outlineMode === 'conservative' ? 'checked' : ''} class="sr-only">
                <span class="text-sm font-semibold">📋 普通模式</span>
                <span class="text-xs text-gray-400">仅基于素材和知识库</span>
              </label>
              <label class="ppt-regen-mode-opt flex flex-col items-center gap-1 px-4 py-3 border-2 rounded-xl cursor-pointer transition-all ${state.outlineMode === 'enhanced' ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 bg-white hover:border-gray-300'}">
                <input type="radio" name="regen-mode" value="enhanced" ${state.outlineMode === 'enhanced' ? 'checked' : ''} class="sr-only">
                <span class="text-sm font-semibold">✨ 增强模式</span>
                <span class="text-xs text-gray-400">素材+行业知识补充</span>
              </label>
            </div>
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 mb-2">修改意见（可选）</label>
            <textarea id="ppt-regen-feedback" class="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm resize-none focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all" rows="3" placeholder="例如：增加竞品分析页面、调整叙事节奏、补充数据案例..."></textarea>
          </div>
        </div>
        <div class="px-6 py-4 bg-gray-50 border-t border-gray-100 flex justify-end gap-3">
          <button id="ppt-regen-cancel" class="px-5 py-2.5 border border-gray-300 rounded-xl text-sm font-medium text-gray-600 hover:bg-white transition-colors">取消</button>
          <button id="ppt-regen-confirm" class="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors">确认重新生成</button>
        </div>
      </div>`;

    document.body.appendChild(_regenModal);

    // Mode selector
    _regenModal.querySelectorAll('input[name="regen-mode"]').forEach(r => {
      r.addEventListener('change', () => {
        state.outlineMode = (r as HTMLInputElement).value;
        _regenModal!.querySelectorAll('.ppt-regen-mode-opt').forEach(card => {
          const input = card.querySelector('input') as HTMLInputElement;
          card.classList.toggle('border-indigo-500', input.checked);
          card.classList.toggle('bg-indigo-50', input.checked);
          card.classList.toggle('border-gray-200', !input.checked);
          card.classList.toggle('bg-white', !input.checked);
        });
      });
    });

    // Cancel
    _regenModal.querySelector('#ppt-regen-cancel')?.addEventListener('click', () => _regenModal?.remove());

    // Close on overlay click
    _regenModal.addEventListener('click', (e) => {
      if (e.target === _regenModal) _regenModal?.remove();
    });

    // Confirm regen
    _regenModal.querySelector('#ppt-regen-confirm')?.addEventListener('click', async () => {
      const ta = _regenModal?.querySelector('#ppt-regen-feedback') as HTMLTextAreaElement;
      const feedback = ta?.value?.trim() || '';
      _regenModal?.remove();

      const btn = el.querySelector('#ppt-regenerate-outline') as HTMLButtonElement;
      btn.disabled = true; btn.textContent = '重新生成中...';
      const done = showLoading(el, 'AI 正在重新生成大纲…', '基于素材和知识库重新构建全部页面，请耐心等待');

      try {
        const result = await apiPost<OutlineResponse>(`/v1/ppt-maker/projects/${state.projectId}/outline/?mode=${state.outlineMode}`, { regenerate: true, feedback });
        state.outlinePages = result.pages || [];
        state.selectedOutlineIdx = 0;
        state.outlineSaved = false;
        toast('大纲已重新生成');
        reRender();
      } catch (e: any) {
        done();
        toast('重新生成失败：' + (e.message || e), 'error');
        btn.disabled = false; btn.textContent = '全部重新生成';
      }
    });

    setTimeout(() => {
      const ta = _regenModal?.querySelector('#ppt-regen-feedback') as HTMLTextAreaElement;
      ta?.focus();
    }, 100);
  });



  // Per-page save (暂存此页)
  el.querySelector('.ppt-save-page')?.addEventListener('click', async () => {
    _syncDetailToState(el);
    try {
      const text = state.outlinePages.map(p =>
        `### 第${p.page_num}页\n**类型**：${p.type}\n**标题**：${p.title}\n**角色**：${p.role}\n**核心信息**：${p.core_message}\n**要点**：\n${p.points.map(pt => `- ${pt}`).join('\n')}\n**视觉建议**：${p.visual_hint}`
      ).join('\n\n');
      await apiPut(`/v1/ppt-maker/projects/${state.projectId}/outline/`, { outline: text });
      toast('此页已暂存');
    } catch { toast('暂存失败', 'error'); }
  });

  // Confirm outline
  el.querySelector('#ppt-confirm-outline')?.addEventListener('click', async () => {
    const btn = el.querySelector('#ppt-confirm-outline') as HTMLButtonElement;
    btn.disabled = true; btn.textContent = '保存中...';
    try {
      _syncDetailToState(el);
      const text = state.outlinePages.map(p =>
        `### 第${p.page_num}页\n**标题**：${p.title}\n**核心信息**：${p.core_message}\n**要点**：\n${p.points.map(pt => `- ${pt}`).join('\n')}\n**视觉建议**：${p.visual_hint || ''}`
      ).join('\n\n');
      await apiPut(`/v1/ppt-maker/projects/${state.projectId}/outline/`, { outline: text });
      state.outlineSaved = true;
      toast('大纲已确认');
      navigateTo(4);
    } catch (e: any) {
      toast('保存失败：' + (e.message || e), 'error');
      btn.disabled = false; btn.textContent = '确认大纲';
    }
  });

  // Back — do NOT auto-save; only explicit save persists
  el.querySelector('#ppt-step3-back')?.addEventListener('click', () => { navigateTo(2); });
}

// ── Helpers ───────────────────────────────────────────────────────

function _syncDetailToState(el: HTMLElement): void {
  const idx = state.selectedOutlineIdx ?? 0;
  if (!state.outlinePages[idx]) return;
  const titleEl = el.querySelector('.ppt-field-title') as HTMLInputElement;
  const msgEl = el.querySelector('.ppt-field-msg') as HTMLTextAreaElement;
  const pointsEl = el.querySelector('.ppt-field-points') as HTMLTextAreaElement;
  const visualEl = el.querySelector('.ppt-field-visual') as HTMLTextAreaElement;
  if (titleEl) state.outlinePages[idx].title = titleEl.value;
  if (msgEl) state.outlinePages[idx].core_message = msgEl.value;
  if (pointsEl) state.outlinePages[idx].points = pointsEl.value.split('\n').filter(l => l.trim());
  if (visualEl) state.outlinePages[idx].visual_hint = visualEl.value;
}

// Strip markdown artifacts from displayed text
// Merge new page data into existing — only overwrites non-empty fields
function _mergePage(target: OutlinePage, source: Partial<OutlinePage>): void {
  if (source.title) target.title = source.title;
  if (source.type) target.type = source.type;
  if (source.role) target.role = source.role;
  if (source.core_message) target.core_message = source.core_message;
  if (source.points?.length) target.points = source.points;
  if (source.visual_hint) target.visual_hint = source.visual_hint;
}

function _clean(s: string): string {
  if (!s) return '';
  return s
    .replace(/^\*\*[^*]+\*\*[：:]\s*/g, '')
    .replace(/^#{1,4}\s*/g, '')
    .replace(/\*\*/g, '')
    .trim();
}

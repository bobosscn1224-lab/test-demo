/** Step 1: Project creation / editing form. */

import { apiPost, apiPut } from '../../../services/api';
import { state } from '../state';
import { esc, toast } from '../utils';
import { navigateTo } from '../navigation';
import { SCENARIOS, AUDIENCES, SCALES } from '../types';
import type { Project } from '../types';

export function renderStep1(el: HTMLElement): void {
  el.className = 'max-w-2xl mx-auto w-full p-6';

  const html = `
    <h2 class="text-xl font-bold text-gray-800 mb-1">创建新项目</h2>
    <p class="text-sm text-gray-500 mb-6">填写以下信息，系统将为你生成专业的 PPT 大纲和内容</p>

    <div class="space-y-5">
      <!-- Project Name -->
      <div>
        <label class="block text-sm font-semibold text-gray-700 mb-1.5">项目名称</label>
        <input id="ppt-form-name" type="text" placeholder="例如：2026上半年业务复盘汇报" value="${esc(state.formName)}"
          class="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all">
      </div>

      <!-- Scenario -->
      <div>
        <label class="block text-sm font-semibold text-gray-700 mb-1.5">应用场景</label>
        <select id="ppt-form-scenario" class="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:border-indigo-500 bg-white">
          ${SCENARIOS.map(s => `<option value="${esc(s)}" ${s === state.formScenario ? 'selected' : ''}>${esc(s)}</option>`).join('')}
        </select>
      </div>

      <!-- Audience -->
      <div>
        <label class="block text-sm font-semibold text-gray-700 mb-1.5">目标受众</label>
        <select id="ppt-form-audience" class="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:border-indigo-500 bg-white">
          ${AUDIENCES.map(a => `<option value="${esc(a)}" ${a === state.formAudience ? 'selected' : ''}>${esc(a)}</option>`).join('')}
        </select>
      </div>

      <!-- Scale -->
      <div>
        <label class="block text-sm font-semibold text-gray-700 mb-1.5">篇幅规模</label>
        <div id="ppt-form-scale" class="flex gap-3">
          ${SCALES.map(s => `
            <label class="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 border-2 rounded-xl cursor-pointer text-sm font-medium transition-all ${s === state.formScale ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'}">
              <input type="radio" name="scale" value="${esc(s)}" ${s === state.formScale ? 'checked' : ''} class="sr-only">
              ${esc(s)}
            </label>
          `).join('')}
        </div>
      </div>

      <!-- Narrative Style -->
      <div>
        <label class="block text-sm font-semibold text-gray-700 mb-1.5">叙事风格</label>
        <select id="ppt-form-narrative-style" class="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:border-indigo-500 bg-white">
          <option value="auto" ${state.formNarrativeStyle === 'auto' ? 'selected' : ''}>🤖 自动判断（AI根据素材选择）</option>
          <option value="narrative" ${state.formNarrativeStyle === 'narrative' ? 'selected' : ''}>📖 叙事故事型 — 故事/场景/比喻驱动</option>
          <option value="data_report" ${state.formNarrativeStyle === 'data_report' ? 'selected' : ''}>📊 数据汇报型 — 数据/图表/趋势驱动</option>
          <option value="business_proposal" ${state.formNarrativeStyle === 'business_proposal' ? 'selected' : ''}>💼 商业方案型 — 逻辑/价值/论证驱动</option>
          <option value="technical" ${state.formNarrativeStyle === 'technical' ? 'selected' : ''}>🔧 技术拆解型 — 架构/模块/原理驱动</option>
        </select>
      </div>

      <!-- Narrative Framework -->
      <div>
        <label class="block text-sm font-semibold text-gray-700 mb-1.5">叙事框架</label>
        <select id="ppt-form-narrative-framework" class="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:border-indigo-500 bg-white">
          <option value="auto" ${state.formNarrativeFramework === 'auto' ? 'selected' : ''}>🤖 自动选择（AI选最合适的）</option>
          <option value="conflict_driven" ${state.formNarrativeFramework === 'conflict_driven' ? 'selected' : ''}>⚡ 冲突驱动型 — 威胁→武器→主角行动（最抓眼球）</option>
          <option value="scr" ${state.formNarrativeFramework === 'scr' ? 'selected' : ''}>📋 SCR型 — 现状→复杂因素→方案（麦肯锡经典）</option>
          <option value="problem_driven" ${state.formNarrativeFramework === 'problem_driven' ? 'selected' : ''}>🔍 问题驱动型 — 问题→根因→方案→收益</option>
          <option value="opportunity_driven" ${state.formNarrativeFramework === 'opportunity_driven' ? 'selected' : ''}>🚀 机会驱动型 — 趋势→机会→路径→回报</option>
          <option value="abt" ${state.formNarrativeFramework === 'abt' ? 'selected' : ''}>🎬 ABT型 — And→But→Therefore（三幕简洁）</option>
          <option value="hook_progressive" ${state.formNarrativeFramework === 'hook_progressive' ? 'selected' : ''}>🪝 钩子递进型 — 钩子→冲突→高潮→行动（故事化）</option>
        </select>
      </div>

      <!-- Objective -->
      <div>
        <label class="block text-sm font-semibold text-gray-700 mb-1.5">汇报目标</label>
        <select id="ppt-form-objective" class="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:border-indigo-500 bg-white">
          <option value="auto" ${state.formObjective === 'auto' ? 'selected' : ''}>🤖 自动判断</option>
          <option value="drive_decision" ${state.formObjective === 'drive_decision' ? 'selected' : ''}>✅ 促成决策/批准</option>
          <option value="show_results" ${state.formObjective === 'show_results' ? 'selected' : ''}>📊 展示成果/复盘</option>
          <option value="secure_resources" ${state.formObjective === 'secure_resources' ? 'selected' : ''}>💰 争取资源/预算</option>
          <option value="build_consensus" ${state.formObjective === 'build_consensus' ? 'selected' : ''}>🤝 建立共识/对齐</option>
          <option value="transfer_knowledge" ${state.formObjective === 'transfer_knowledge' ? 'selected' : ''}>📖 传递认知/培训</option>
        </select>
      </div>

      <!-- Tone -->
      <div>
        <label class="block text-sm font-semibold text-gray-700 mb-1.5">语调风格</label>
        <select id="ppt-form-tone" class="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:border-indigo-500 bg-white">
          <option value="auto" ${state.formTone === 'auto' ? 'selected' : ''}>🤖 自动判断</option>
          <option value="professional" ${state.formTone === 'professional' ? 'selected' : ''}>👔 专业严谨</option>
          <option value="storytelling" ${state.formTone === 'storytelling' ? 'selected' : ''}>📖 生动故事化</option>
          <option value="inspirational" ${state.formTone === 'inspirational' ? 'selected' : ''}>🔥 激励人心</option>
          <option value="concise" ${state.formTone === 'concise' ? 'selected' : ''}>⚡ 简洁有力</option>
          <option value="humorous" ${state.formTone === 'humorous' ? 'selected' : ''}>😄 幽默风趣</option>
        </select>
      </div>

      <!-- Key Messages / Additional Requirements -->
      <div>
        <label class="block text-sm font-semibold text-gray-700 mb-1.5">补充要求 <span class="text-gray-400 font-normal">（任何需要特别强调的内容、约束或偏好）</span></label>
        <textarea id="ppt-form-messages" rows="4" placeholder="例如：&#10;· 必须引用 Q2 财报中的营收数据&#10;· 第3页要对比竞品A和竞品B&#10;· 整体控制在10页以内&#10;· 结尾要有明确的预算申请金额"
          class="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all resize-none">${esc(state.formMessages)}</textarea>
      </div>
    </div>

    <!-- Actions -->
    <div class="flex items-center gap-3 mt-6 pt-4 border-t border-gray-200">
      <button id="ppt-step1-back" class="px-4 py-2 border border-gray-300 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors">← 返回列表</button>
      <button id="ppt-step1-create" class="px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">${state.projectId ? '更新并继续' : '创建项目'}</button>
    </div>
  `;

  el.innerHTML = html;
  bindStep1(el);
}

function bindStep1(el: HTMLElement): void {
  el.querySelector('#ppt-step1-back')?.addEventListener('click', () => { navigateTo(0); });

  // Scale radio
  el.querySelectorAll('#ppt-form-scale input[type=radio]').forEach(r => {
    r.addEventListener('change', () => {
      state.formScale = (r as HTMLInputElement).value;
      renderStep1(el);
    });
  });

  // Create button
  el.querySelector('#ppt-step1-create')?.addEventListener('click', async () => {
    const nameEl = el.querySelector('#ppt-form-name') as HTMLInputElement;
    const scenarioEl = el.querySelector('#ppt-form-scenario') as HTMLSelectElement;
    const audienceEl = el.querySelector('#ppt-form-audience') as HTMLSelectElement;
    const messagesEl = el.querySelector('#ppt-form-messages') as HTMLTextAreaElement;

    state.formName = nameEl?.value?.trim() || '';
    state.formScenario = scenarioEl?.value || SCENARIOS[0];
    state.formAudience = audienceEl?.value || AUDIENCES[0];
    state.formMessages = messagesEl?.value?.trim() || '';
    state.formNarrativeStyle = (el.querySelector('#ppt-form-narrative-style') as HTMLSelectElement)?.value || 'auto';
    state.formNarrativeFramework = (el.querySelector('#ppt-form-narrative-framework') as HTMLSelectElement)?.value || 'auto';
    state.formObjective = (el.querySelector('#ppt-form-objective') as HTMLSelectElement)?.value || 'auto';
    state.formTone = (el.querySelector('#ppt-form-tone') as HTMLSelectElement)?.value || 'auto';

    // Validation
    if (!state.formName) { toast('请输入项目名称', 'error'); return; }

    const payload = {
      name: state.formName,
      purpose: state.formScenario,
      audience: state.formAudience,
      scale: state.formScale,
      styles: [] as string[],  // visual styles moved to Step 4
      key_message: state.formMessages,
      narrative_style: state.formNarrativeStyle,
      narrative_framework: state.formNarrativeFramework,
      objective: state.formObjective,
      tone: state.formTone,
    };

    const btn = el.querySelector('#ppt-step1-create') as HTMLButtonElement;
    btn.disabled = true;
    btn.textContent = '处理中...';

    try {
      if (state.projectId) {
        // Update existing
        await apiPut(`/v1/ppt-maker/projects/${state.projectId}/`, payload);
      } else {
        const result = await apiPost<Project>('/v1/ppt-maker/projects/', payload);
        state.projectId = result.id;
      }
      toast('项目信息已保存');
      navigateTo(2);
    } catch (e: any) {
      toast('保存失败：' + (e.message || e), 'error');
      btn.disabled = false;
      btn.textContent = state.projectId ? '更新并继续' : '创建项目';
    }
  });

  // Sync inputs to state on change
  el.querySelector('#ppt-form-name')?.addEventListener('input', (e) => {
    state.formName = (e.target as HTMLInputElement).value;
  });
  el.querySelector('#ppt-form-scenario')?.addEventListener('change', (e) => {
    state.formScenario = (e.target as HTMLSelectElement).value;
  });
  el.querySelector('#ppt-form-audience')?.addEventListener('change', (e) => {
    state.formAudience = (e.target as HTMLSelectElement).value;
  });
  el.querySelector('#ppt-form-messages')?.addEventListener('input', (e) => {
    state.formMessages = (e.target as HTMLTextAreaElement).value;
  });
}

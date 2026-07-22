/** Pro Mode Step 0 — Script Structuring (剧本结构化).
 *
 *  Paste raw story/novel → AI converts to structured shooting script.
 *  Optional: select a template preset for style parameters.
 */

import { apiGet, apiPost } from '../../services/api';
import { getProject, setProject, markStepReady } from './state';
import { navigateToStep } from './index';
import { TEMPLATE_LIST } from './types';
import type { Project } from './types';
import { progress } from './progress';

function h(tag: string, css: string, children?: (Node | string)[], attrs?: Record<string, string>): HTMLElement {
  const el = document.createElement(tag); el.style.cssText = css;
  if (attrs) Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  if (children) children.forEach(c => {
    if (typeof c === 'string') { if (/<[a-zA-Z][^>]*>/.test(c)) el.insertAdjacentHTML('beforeend', c); else el.append(document.createTextNode(c)); }
    else el.append(c);
  });
  return el;
}

let _rootEl: HTMLElement | null = null;
let _selectedTemplate = '';
let _analyzing = false;

export function renderScriptStructuring(): HTMLElement {
  _rootEl = document.createElement('div');
  _rootEl.style.cssText = 'display:flex;flex-direction:column;gap:16px;max-width:800px;';

  const existing = getProject();

  _rootEl.innerHTML = `
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;">
      <h3 style="font-size:18px;font-weight:700;color:#111827;margin:0 0 4px;">📝 步骤 0：剧本结构化</h3>
      <p style="font-size:13px;color:#6b7280;margin:0 0 16px;">粘贴你的小说/故事，AI 自动转为标准短剧剧本。可选模板预设全套风格参数</p>

      <div style="margin-bottom:12px;">
        <label style="display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;">选择短剧模板（可选）</label>
        <div id="ss-templates" style="display:flex;gap:6px;flex-wrap:wrap;"></div>
      </div>

      <div style="margin-bottom:16px;">
        <label style="display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;">原始故事 / 小说文本</label>
        <textarea id="ss-story" rows="14" placeholder="在此粘贴你的短篇故事或小说片段...

AI 将自动：
· 去除心理描写和文学修辞，转为画面语言
· 提取角色外貌特征和场景空间描述
· 按模板风格设置色调/节奏/表演风格
· 生成可直接用于分镜的标准剧本

示例文体：
&#34;那是一个初秋的下午，阳光穿过梧桐叶在校园小径上洒下斑驳的光影。林小晚抱着厚厚的习题册从图书馆出来，迎面撞上了骑单车的陆之昂。习题册散落一地，男生慌忙跳下车帮她捡。&#34;

&#34;对不起对不起！&#34;陆之昂一边捡一边道歉，抬头看到林小晚微红的眼眶，愣住了。&#34;..."

          style="width:100%;padding:12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;resize:vertical;box-sizing:border-box;font-family:inherit;line-height:1.7;"></textarea>
      </div>

      <button id="ss-analyze-btn" style="width:100%;padding:14px;background:#4f46e5;color:#fff;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;">🤖 AI 结构化剧本</button>
      <div id="ss-status" style="margin-top:10px;font-size:13px;text-align:center;color:#6b7280;min-height:20px;"></div>
    </div>
    <div id="ss-result"></div>
  `;

  // Render templates
  renderTemplates();

  // Bind events
  _rootEl.querySelector('#ss-analyze-btn')?.addEventListener('click', handleStructure);

  // If resuming a project, pre-fill
  if (existing) {
    const ta = _rootEl.querySelector('#ss-story') as HTMLTextAreaElement;
    if (ta) ta.value = existing.raw_story || existing.script || '';
    if (existing.template) {
      _selectedTemplate = existing.template;
      renderTemplates();
    }
    if (existing.structured_script) {
      showResult(existing);
    }
  }

  return _rootEl;
}

function renderTemplates(): void {
  const container = _rootEl?.querySelector('#ss-templates') as HTMLElement;
  if (!container) return;
  container.innerHTML = '';

  TEMPLATE_LIST.forEach(t => {
    const active = t.key === _selectedTemplate;
    const chip = h('button',
      `padding:6px 14px;border:2px solid ${active ? '#4f46e5' : '#e5e7eb'};background:${active ? '#eef2ff' : '#fff'};border-radius:20px;font-size:12px;cursor:pointer;color:${active ? '#4f46e5' : '#6b7280'};font-weight:${active ? '600' : '400'};`,
      [`${t.icon} ${t.label}`]
    );
    chip.addEventListener('click', () => {
      _selectedTemplate = t.key === _selectedTemplate ? '' : t.key;
      renderTemplates();
    });
    container.appendChild(chip);
  });
}

async function handleStructure(): Promise<void> {
  if (_analyzing) return;
  const ta = _rootEl?.querySelector('#ss-story') as HTMLTextAreaElement;
  const story = ta?.value?.trim();
  if (!story || story.length < 10) { alert('请输入至少 10 个字符的故事内容'); return; }

  _analyzing = true;
  const btn = _rootEl?.querySelector('#ss-analyze-btn') as HTMLButtonElement;
  if (btn) { btn.disabled = true; btn.textContent = '⏳ AI 结构化中...'; }

  const statusEl = _rootEl?.querySelector('#ss-status') as HTMLElement;

  try {
    const res = await progress.withAsync(
      'script-structure', 'AI 剧本结构化',
      async (update) => {
        update('正在调用 DeepSeek 分析故事结构...');
        const result = await apiPost<{ success: boolean; project: Project }>('/v1/pro-mode/script/structure', {
          story, template: _selectedTemplate,
        });
        update('结构化完成，正在整理结果...');
        return result;
      },
      '正在将故事转为标准短剧剧本...',
    );
    setProject(res.project);
    markStepReady(0);
    showResult(res.project);
    if (statusEl) statusEl.textContent = '✅ 结构化完成！查看下方结果，确认后进入下一步';
  } catch (e: any) {
    if (statusEl) statusEl.textContent = `❌ ${e.message}`;
  } finally {
    _analyzing = false;
    if (btn) { btn.disabled = false; btn.textContent = '🤖 AI 结构化剧本'; }
  }
}

function showResult(project: Project): void {
  const resultEl = _rootEl?.querySelector('#ss-result') as HTMLElement;
  if (!resultEl) return;
  resultEl.innerHTML = '';

  const container = h('div', 'display:flex;flex-direction:column;gap:16px;');

  // Title & summary
  container.appendChild(h('div', 'background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px;', [
    `<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;"><span style="font-size:18px;font-weight:700;color:#111827;">${project.title}</span><span style="font-size:12px;color:#9ca3af;background:#f3f4f6;padding:2px 8px;border-radius:10px;">${project.genre}</span>${project.template ? `<span style="font-size:11px;color:#8b5cf6;background:#faf5ff;padding:2px 8px;border-radius:10px;">📋 ${project.template}模板</span>` : ''}</div>`,
    `<div style="font-size:13px;color:#374151;">${project.summary}</div>`,
  ]));

  // Structured script preview
  const script = project.structured_script || project.script || '';
  container.appendChild(h('div', 'background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;', [
    '<div style="font-size:14px;font-weight:600;color:#111827;margin-bottom:8px;">📄 结构化剧本</div>',
    `<div style="font-size:12px;color:#374151;line-height:1.8;max-height:200px;overflow-y:auto;white-space:pre-wrap;">${script.slice(0, 800)}${script.length > 800 ? '...' : ''}</div>`,
  ]));

  // Character & scene counts
  container.appendChild(h('div', 'display:flex;gap:16px;font-size:13px;color:#6b7280;', [
    `<span>🧑 ${project.characters.length} 角色</span><span>🏞 ${project.scenes.length} 场景</span><span>🎯 ${project.props.length} 关键道具</span><span>🎬 预计 ${(project as any).total_estimated_shots || '?'} 镜</span>`,
  ]));

  // Next step
  const nextBtn = h('button', 'padding:14px 24px;background:#10b981;color:#fff;border:none;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;align-self:flex-end;', ['→ 下一步：资源生成']);
  nextBtn.addEventListener('click', () => { markStepReady(0); navigateToStep(1); });
  container.appendChild(nextBtn);

  resultEl.appendChild(container);
}

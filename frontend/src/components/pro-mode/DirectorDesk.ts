/** Pro Mode Step 4 — Director Desk (导演台).
 *
 *  AI synthesizes all previous work to suggest pace, style, tone, and transitions.
 */

import { apiPost } from '../../services/api';
import { getProject, setProject, markStepReady } from './state';
import { navigateToStep } from './index';
import type { Project, DirectorConfig } from './types';
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

export function renderDirectorDesk(): HTMLElement {
  const root = document.createElement('div');
  root.style.cssText = 'display:flex;flex-direction:column;gap:16px;max-width:700px;';

  root.innerHTML = `
    <div>
      <h3 style="font-size:18px;font-weight:700;color:#111827;margin:0 0 4px;">🎬 步骤 4：导演台</h3>
      <p style="font-size:13px;color:#6b7280;margin:0;">AI 综合分析角色、场景和分镜，提供专业的导演建议</p>
    </div>
  `;

  const project = getProject();
  if (!project || project.shots.length === 0) {
    root.appendChild(h('div', 'text-align:center;padding:40px;color:#f59e0b;font-size:14px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;', ['⚠️ 请先完成步骤 3：分镜计划']));
    return root;
  }

  // ── Generate button ────────────────────────────────────────────
  const suggestSection = h('div', 'background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;');
  suggestSection.innerHTML = `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;"><span style="font-size:14px;font-weight:600;color:#374151;">🤖 AI 导演建议</span><span style="font-size:11px;color:#9ca3af;">基于 ${project.shots.length} 个镜头 · ${project.characters.length} 个角色 · ${project.scenes.length} 个场景</span></div>`;

  const genBtn = h('button', 'width:100%;padding:12px;background:#8b5cf6;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;margin-top:12px;', ['🎬 生成导演建议']);
  genBtn.id = 'dd-gen-btn';
  genBtn.addEventListener('click', handleSuggest);
  suggestSection.appendChild(genBtn);
  suggestSection.appendChild(h('div', 'id="dd-status";margin-top:8px;font-size:12px;text-align:center;color:#6b7280;', []));
  root.appendChild(suggestSection);

  // ── Show existing config if available ──────────────────────────
  if (project.director_config) {
    root.appendChild(renderConfigDisplay(project.director_config));
  }

  // ── Next step ──────────────────────────────────────────────────
  const nextBtn = h('button', 'padding:14px 24px;background:#10b981;color:#fff;border:none;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;align-self:flex-end;', ['→ 下一步：逐镜生成']);
  nextBtn.addEventListener('click', () => { markStepReady(3); navigateToStep(4); });
  root.appendChild(nextBtn);

  return root;
}

async function handleSuggest(): Promise<void> {
  const project = getProject();
  if (!project) return;

  const statusEl = document.getElementById('dd-status');
  const btn = document.querySelector('#dd-gen-btn') as HTMLButtonElement;
  if (btn) { btn.disabled = true; btn.textContent = '⏳ AI 分析中...'; }
  if (statusEl) statusEl.textContent = '⏳ AI 分析中...';

  try {
    const res = await progress.withAsync(
      'director-suggest', 'AI 导演建议',
      async (update) => {
        update('正在综合分析角色、场景和分镜...');
        const result = await apiPost<{ success: boolean; director_config: DirectorConfig }>('/v1/pro-mode/director/suggest', { project_id: project.id });
        update('导演建议已生成');
        return result;
      },
      '正在调用 AI 生成导演建议...',
    );
    project.director_config = res.director_config;
    setProject(project);
    markStepReady(3);
    if (statusEl) statusEl.textContent = '✅ 导演建议已生成';

    // Append config display
    const existingDisplay = document.getElementById('dd-config-display');
    if (existingDisplay) existingDisplay.remove();
    const suggestSection = statusEl?.parentElement;
    if (suggestSection) suggestSection.after(renderConfigDisplay(res.director_config));
  } catch (e: any) {
    if (statusEl) statusEl.textContent = `❌ ${e.message}`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🎬 生成导演建议'; }
  }
}

function renderConfigDisplay(cfg: DirectorConfig): HTMLElement {
  const container = h('div', 'display:flex;flex-direction:column;gap:12px;');
  container.id = 'dd-config-display';

  container.appendChild(h('div', 'background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px;', [
    '<div style="font-size:13px;font-weight:600;color:#166534;margin-bottom:8px;">💡 导演思路概述</div>',
    `<div style="font-size:13px;color:#374151;line-height:1.6;">${cfg.overall_note || '未提供'}</div>`,
  ]));

  const sections: { label: string; icon: string; value: string }[] = [
    { label: '节奏', icon: '🎵', value: cfg.pace },
    { label: '表演风格', icon: '🎭', value: cfg.performance_style },
    { label: '色调方案', icon: '🎨', value: cfg.color_tone },
    { label: '转场风格', icon: '🔀', value: cfg.transitions },
  ];

  sections.forEach(s => {
    container.appendChild(h('div', 'background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;', [
      `<div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:8px;">${s.icon} ${s.label}</div>`,
      `<div style="font-size:13px;color:#374151;line-height:1.6;">${s.value || '未提供'}</div>`,
    ]));
  });

  return container;
}

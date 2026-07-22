/** Pro Mode — main entry point.
 *
 *  Two views: Project Dashboard (default) ↔ Workflow (6 steps: 0-5).
 *  Project state persists via backend API across sessions.
 */

import { getViewMode, setViewMode, getCurrentStep, setCurrentStep, markStepReady, isStepReady, getProject } from './state';
import { STEP_LABELS } from './types';
import { renderProjectList } from './ProjectList';
import { renderScriptStructuring } from './ScriptStructuring';
import { renderResourceGen } from './ResourceGen';
import { renderStoryboardPlanner } from './StoryboardPlanner';
import { renderDirectorDesk } from './DirectorDesk';
import { renderShotGenerator } from './ShotGenerator';
import { renderAutoCompose } from './AutoCompose';
import { apiPatch } from '../../services/api';

function h(tag: string, css: string, children?: (Node | string)[], attrs?: Record<string, string>): HTMLElement {
  const el = document.createElement(tag); el.style.cssText = css;
  if (attrs) Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  if (children) children.forEach(c => {
    if (typeof c === 'string') { if (/<[a-zA-Z][^>]*>/.test(c)) el.insertAdjacentHTML('beforeend', c); else el.append(document.createTextNode(c)); }
    else el.append(c);
  });
  return el;
}

let _stepNavEl: HTMLElement | null = null;
let _contentAreaEl: HTMLElement | null = null;

export function renderProModePage(): HTMLElement {
  const root = document.createElement('div');
  root.style.cssText = 'height:100%;display:flex;flex-direction:column;overflow:hidden;';

  if (getViewMode() === 'list') {
    // ── Project Dashboard (default) ──────────────────────────────
    root.appendChild(renderProjectList());
    return root;
  }

  // ── Workflow View ──────────────────────────────────────────────
  const header = h('div', 'display:flex;align-items:center;justify-content:space-between;padding:16px 24px;border-bottom:1px solid #e5e7eb;flex-shrink:0;', [
    `<div><h2 style="font-size:20px;font-weight:700;color:#111827;margin:0;">🎥 专业模式</h2><p style="color:#6b7280;font-size:13px;margin:4px 0 0;">剧本 → 资源生成 → 分镜 → 导演 → 逐镜生成</p></div>`,
  ]);
  const backBtn = h('button', 'padding:8px 16px;border:1px solid #d1d5db;background:#fff;border-radius:8px;font-size:13px;cursor:pointer;color:#6b7280;', ['← 项目列表']);
  backBtn.addEventListener('click', () => {
    setViewMode('list');
    refreshProModeUI();
  });
  header.appendChild(backBtn);
  root.appendChild(header);

  // Body: step nav + content
  const body = h('div', 'display:flex;flex:1;min-height:0;');
  _stepNavEl = h('div', 'width:260px;flex-shrink:0;border-right:1px solid #e5e7eb;padding:20px 16px;overflow-y:auto;background:#fafbfc;');
  renderStepNav();
  body.appendChild(_stepNavEl);

  _contentAreaEl = h('div', 'flex:1;overflow-y:auto;padding:24px;min-width:0;');
  renderCurrentStep();
  body.appendChild(_contentAreaEl);

  root.appendChild(body);
  return root;
}

// ── Step Navigation ──────────────────────────────────────────────

function renderStepNav(): void {
  if (!_stepNavEl) return;
  _stepNavEl.innerHTML = '';

  _stepNavEl.appendChild(h('div', 'font-size:11px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;', ['工作流步骤']));

  for (let i = 0; i <= 5; i++) {
    const info = STEP_LABELS[i];
    const active = i === getCurrentStep();
    const ready = isStepReady(i);
    const locked = i > 1 && !isStepReady(i - 1) && i > getCurrentStep();

    const stepEl = h('div',
      `display:flex;align-items:center;gap:12px;padding:12px 14px;margin-bottom:4px;border-radius:10px;cursor:pointer;transition:all 0.15s;${
        active ? 'background:#eef2ff;border:2px solid #4f46e5;'
        : ready ? 'background:#fff;border:2px solid #e5e7eb;'
        : locked ? 'background:#fff;border:2px solid #f3f4f6;opacity:0.5;cursor:not-allowed;'
        : 'background:#fff;border:2px solid #e5e7eb;'
      }`,
      [
        `<div style="width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;${
          active ? 'background:#4f46e5;color:#fff;' : ready ? 'background:#10b981;color:#fff;' : 'background:#f3f4f6;'
        }">${ready && !active ? '✓' : info.icon}</div>`,
        `<div style="min-width:0;"><div style="font-size:14px;font-weight:${active ? '700' : '500'};color:${active ? '#4f46e5' : '#374151'};">${info.title}</div><div style="font-size:11px;color:#9ca3af;">${info.desc}</div></div>`,
      ]
    );

    if (!locked) {
      stepEl.addEventListener('click', () => { setCurrentStep(i); renderStepNav(); renderCurrentStep(); });
    }
    _stepNavEl.appendChild(stepEl);
  }
}

// ── Content rendering ────────────────────────────────────────────

function renderCurrentStep(): void {
  if (!_contentAreaEl) return;
  _contentAreaEl.innerHTML = '';

  const step = getCurrentStep();
  let panel: HTMLElement;

  switch (step) {
    case 0: panel = renderScriptStructuring(); break;
    case 1: panel = renderResourceGen(); break;
    case 2: panel = renderStoryboardPlanner(); break;
    case 3: panel = renderDirectorDesk(); break;
    case 4: panel = renderShotGenerator(); break;
    case 5: panel = renderAutoCompose(); break;
    default: panel = h('div', 'text-align:center;padding:60px;color:#9ca3af;', ['未知步骤']);
  }

  _contentAreaEl.appendChild(panel);
  renderStepNav();
}

// ── Public helpers ───────────────────────────────────────────────

export function refreshProModeUI(): void {
  // Find the app container and re-render
  const pageEl = document.getElementById('page-pro-mode');
  if (pageEl) {
    pageEl.innerHTML = '';
    pageEl.appendChild(renderProModePage());
    return;
  }
  renderStepNav();
  renderCurrentStep();
}

export async function navigateToStep(step: number): Promise<void> {
  setCurrentStep(step);
  // Persist step to backend
  const project = getProject();
  if (project) {
    try {
      await apiPatch(`/v1/pro-mode/project/${project.id}/step`, { current_step: step });
    } catch { /* non-critical */ }
  }
  refreshProModeUI();
}

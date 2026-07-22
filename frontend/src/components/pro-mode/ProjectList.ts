/** Pro Mode — Project Dashboard.
 *
 *  Landing page showing all projects. User can create new or resume existing.
 */

import { apiGet, apiDelete } from '../../services/api';
import { getProjectSummaries, setProjectSummaries, setViewMode, setProject, setCurrentStep } from './state';
import { refreshProModeUI } from './index';
import type { Project, ProjectSummary } from './types';

function h(tag: string, css: string, children?: (Node | string)[], attrs?: Record<string, string>): HTMLElement {
  const el = document.createElement(tag); el.style.cssText = css;
  if (attrs) Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  if (children) children.forEach(c => {
    if (typeof c === 'string') { if (/<[a-zA-Z][^>]*>/.test(c)) el.insertAdjacentHTML('beforeend', c); else el.append(document.createTextNode(c)); }
    else el.append(c);
  });
  return el;
}

const STEP_LABELS_ZH: Record<number, string> = {
  0: '📝 剧本结构化', 1: '🎨 资源生成', 2: '📋 分镜计划', 3: '🎬 导演台', 4: '🚀 逐镜生成', 5: '🎞 自动成片',
};

let _rootEl: HTMLElement | null = null;

export function renderProjectList(): HTMLElement {
  const root = document.createElement('div');
  root.style.cssText = 'padding:24px;height:100%;overflow-y:auto;';
  _rootEl = root;

  root.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;">
      <div>
        <h2 style="font-size:20px;font-weight:700;color:#111827;margin:0;">🎥 专业模式</h2>
        <p style="color:#6b7280;font-size:13px;margin:4px 0 0;">剧本 → AI 提取资源 → 批量生图 → 分镜 → 逐镜生成视频</p>
      </div>
      <button id="pl-back-btn" style="padding:8px 16px;border:1px solid #d1d5db;background:#fff;border-radius:8px;font-size:13px;cursor:pointer;color:#6b7280;">← 返回简易模式</button>
    </div>

    <button id="pl-new-btn" style="padding:12px 28px;background:#4f46e5;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;">📝 + 新建短剧项目</button>

    <div id="pl-project-list" style="display:flex;flex-direction:column;gap:12px;">
      <div style="text-align:center;padding:20px;color:#9ca3af;font-size:13px;">加载中...</div>
    </div>
  `;

  // Bind events
  root.querySelector('#pl-back-btn')?.addEventListener('click', () => {
    window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'video-gen' } }));
  });
  root.querySelector('#pl-new-btn')?.addEventListener('click', () => {
    setProject(null);
    setCurrentStep(0);
    setViewMode('workflow');
    refreshProModeUI();
  });

  // Load projects after root is in DOM
  setTimeout(() => loadProjects(root), 0);

  return root;
}

async function loadProjects(root: HTMLElement): Promise<void> {
  const listEl = root.querySelector('#pl-project-list') as HTMLElement;
  if (!listEl) return;

  try {
    const data = await apiGet<{ total: number; projects: ProjectSummary[] }>('/v1/pro-mode/project/list');
    setProjectSummaries(data.projects);

    if (data.projects.length === 0) {
      listEl.innerHTML = `
        <div style="text-align:center;padding:60px 20px;color:#9ca3af;">
          <div style="font-size:48px;margin-bottom:16px;">🎬</div>
          <div style="font-size:15px;font-weight:600;color:#9ca3af;margin-bottom:8px;">还没有项目</div>
          <div style="font-size:13px;">点击上方「+ 新建短剧项目」开始你的第一个作品</div>
        </div>`;
      return;
    }

    listEl.innerHTML = '';
    data.projects.forEach(p => {
      listEl.appendChild(renderProjectCard(p));
    });
  } catch {
    listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#e74c3c;">加载失败</div>';
  }
}

function renderProjectCard(p: ProjectSummary): HTMLElement {
  const stepLabel = STEP_LABELS_ZH[p.current_step] || '📝 剧本分析';
  const totalSteps = 6;
  const progressPct = Math.round((p.current_step / totalSteps) * 100);

  const card = h('div',
    'background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;cursor:pointer;transition:all 0.15s;',
    [
      `<div style="display:flex;align-items:flex-start;justify-content:space-between;">
        <div style="flex:1;min-width:0;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
            <span style="font-size:16px;font-weight:700;color:#111827;">${p.title}</span>
            <span style="font-size:11px;color:#9ca3af;background:#f3f4f6;padding:2px 8px;border-radius:10px;">${p.genre}</span>
          </div>
          <div style="font-size:12px;color:#6b7280;margin-bottom:10px;">${p.summary}</div>
          <div style="display:flex;gap:16px;font-size:11px;color:#9ca3af;">
            <span>🧑 ${p.char_count} 角色</span><span>🏞 ${p.scene_count} 场景</span><span>🎬 ${p.shot_count} 镜头</span>
            <span>${new Date(p.created_at).toLocaleDateString('zh-CN')}</span>
          </div>
        </div>
        <div style="text-align:right;flex-shrink:0;margin-left:16px;">
          <div style="font-size:12px;color:#4f46e5;font-weight:600;margin-bottom:4px;">${stepLabel}</div>
          <div style="width:100px;height:6px;background:#f3f4f6;border-radius:3px;overflow:hidden;">
            <div style="width:${progressPct}%;height:100%;background:#4f46e5;border-radius:3px;"></div>
          </div>
        </div>
      </div>`,
    ]
  );

  // Click to resume project
  card.addEventListener('click', async () => {
    try {
      const data = await apiGet<{ success: boolean; project: Project }>(`/v1/pro-mode/project/${p.id}`);
      setProject(data.project);
      setViewMode('workflow');
      refreshProModeUI();
    } catch (e: any) {
      alert('加载项目失败: ' + e.message);
    }
  });

  // Delete button
  const delBtn = h('button',
    'position:absolute;top:8px;right:8px;border:none;background:transparent;color:#d1d5db;cursor:pointer;font-size:14px;',
    ['🗑']
  );
  delBtn.addEventListener('click', async (e) => {
    e.stopPropagation();
    if (!confirm(`删除项目「${p.title}」？此操作不可恢复。`)) return;
    try {
      await apiDelete(`/v1/pro-mode/project/${p.id}`);
      loadProjects(_rootEl!);
    } catch { alert('删除失败'); }
  });
  card.style.position = 'relative';
  card.appendChild(delBtn);

  return card;
}

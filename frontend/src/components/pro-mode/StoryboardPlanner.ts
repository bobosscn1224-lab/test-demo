/** Pro Mode Step 3 — Storyboard Planner (分镜计划 + 分镜关键帧).
 *
 *  AI breaks the script into shots, linking each to the confirmed resources from Step 2.
 *  Each shot can have a "key frame" image generated for first-frame anchoring in video gen.
 */

import { apiPost, apiPut } from '../../services/api';
import { getProject, setProject, markStepReady } from './state';
import { navigateToStep } from './index';
import type { Project, Shot } from './types';
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

export function renderStoryboardPlanner(): HTMLElement {
  _rootEl = document.createElement('div');
  _rootEl.style.cssText = 'display:flex;flex-direction:column;gap:16px;height:100%;min-height:0;';

  const project = getProject();
  if (!project) {
    _rootEl.appendChild(h('div', 'text-align:center;padding:40px;color:#f59e0b;font-size:14px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;', ['⚠️ 请先完成前面的步骤']));
    return _rootEl;
  }

  _rootEl.innerHTML = `
    <div>
      <h3 style="font-size:18px;font-weight:700;color:#111827;margin:0 0 4px;">📋 步骤 3：分镜计划</h3>
      <p style="font-size:13px;color:#6b7280;margin:0;">AI 根据剧本和已确定的视觉资源，拆解为逐镜分镜表。生成关键帧后作为视频首帧锚定。</p>
    </div>
  `;

  // ── Action buttons ─────────────────────────────────────────────
  const btnRow = h('div', 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;');

  const genBtn = h('button', 'padding:12px 24px;background:#4f46e5;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;', ['🤖 AI 拆解分镜']);
  genBtn.addEventListener('click', handleCreateStoryboard);
  btnRow.appendChild(genBtn);

  // Only show frame buttons if shots exist
  if (project.shots.length > 0) {
    const frameAllBtn = h('button', 'padding:12px 20px;background:#7c3aed;color:#fff;border:none;border-radius:10px;font-size:13px;font-weight:600;cursor:pointer;', ['🖼 批量生成关键帧']);
    frameAllBtn.addEventListener('click', () => handleGenerateAllFrames());
    btnRow.appendChild(frameAllBtn);
  }

  btnRow.appendChild(h('div', 'id="sp-status";font-size:13px;text-align:center;color:#6b7280;min-height:20px;flex:1;', []));
  _rootEl.appendChild(btnRow);

  // ── Shot table area ────────────────────────────────────────────
  const tableSection = h('div', 'flex:1;overflow-y:auto;min-height:0;');
  tableSection.id = 'sp-table-section';
  _rootEl.appendChild(tableSection);

  // If project already has shots, show them
  if (project.shots.length > 0) {
    renderShotTable(project);
  }

  return _rootEl;
}

async function handleCreateStoryboard(): Promise<void> {
  const project = getProject();
  if (!project) return;

  const statusEl = _rootEl?.querySelector('#sp-status') as HTMLElement;
  const btn = _rootEl?.querySelector('button') as HTMLButtonElement;
  if (btn) { btn.disabled = true; btn.textContent = '⏳ AI 拆解中...'; }
  if (statusEl) statusEl.textContent = '⏳ AI 拆解中...';

  try {
    const res = await progress.withAsync(
      'create-storyboard', 'AI 拆解分镜',
      async (update) => {
        update('正在调用 AI 分析剧本和资源...');
        const result = await apiPost<{ success: boolean; project: Project }>('/v1/pro-mode/storyboard/create', { project_id: project.id });
        update(`拆解完成，共 ${result.project.shots.length} 个镜头`);
        return result;
      },
      '正在根据剧本拆解分镜表...',
    );
    setProject(res.project);
    markStepReady(2);
    renderShotTable(res.project);
    if (statusEl) statusEl.textContent = `✅ 拆解完成！共 ${res.project.shots.length} 个镜头`;
  } catch (e: any) {
    if (statusEl) statusEl.textContent = `❌ ${e.message}`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🤖 AI 拆解分镜'; }
  }
}

// ── Frame status helpers ──────────────────────────────────────────

function frameStatusBadge(status?: string): string {
  const map: Record<string, { icon: string; bg: string; color: string; label: string }> = {
    pending:   { icon: '⏸', bg: '#f3f4f6', color: '#9ca3af', label: '待生成' },
    generating:{ icon: '⏳', bg: '#fef3c7', color: '#d97706', label: '生成中' },
    done:      { icon: '✅', bg: '#ecfdf5', color: '#059669', label: '已就绪' },
    failed:    { icon: '❌', bg: '#fef2f2', color: '#dc2626', label: '失败' },
    stale:     { icon: '🔄', bg: '#fff7ed', color: '#ea580c', label: '已过期' },
  };
  const st = map[status || 'pending'] || map.pending;
  return `<span style="display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:${st.bg};color:${st.color};">${st.icon} ${st.label}</span>`;
}

// ── Frame generation ──────────────────────────────────────────────

async function handleGenerateFrame(shotNumber: number): Promise<void> {
  const project = getProject();
  if (!project) return;

  const statusEl = _rootEl?.querySelector('#sp-status') as HTMLElement;
  if (statusEl) statusEl.textContent = `⏳ 生成 Shot ${shotNumber} 关键帧...`;
  const pkey = `gen-frame-${shotNumber}`;
  progress.start(pkey, `生成关键帧：Shot ${shotNumber}`, '调用生图模型中...');

  try {
    const res = await apiPost<{ success: boolean; frame_image_url: string; frame_status: string }>(
      '/v1/pro-mode/storyboard/frame', { project_id: project.id, shot_number: shotNumber }
    );
    // Update local project state
    const shot = project.shots.find(s => s.shot_number === shotNumber);
    if (shot) {
      shot.frame_image_url = res.frame_image_url;
      shot.frame_status = res.frame_status as any;
    }
    if (statusEl) statusEl.textContent = res.success ? `✅ Shot ${shotNumber} 关键帧已生成` : `❌ Shot ${shotNumber} 生成失败`;
    progress.done(pkey, res.success ? '关键帧已生成' : '生成失败');
    renderShotTable(project);
  } catch (e: any) {
    if (statusEl) statusEl.textContent = `❌ ${e.message}`;
    progress.fail(pkey, e.message);
  }
}

async function handleGenerateAllFrames(): Promise<void> {
  const project = getProject();
  if (!project) return;

  const statusEl = _rootEl?.querySelector('#sp-status') as HTMLElement;
  const frameAllBtn = _rootEl?.querySelector('button:nth-of-type(2)') as HTMLButtonElement;
  if (frameAllBtn) { frameAllBtn.disabled = true; frameAllBtn.textContent = '⏳ 批量生成中...'; }
  if (statusEl) statusEl.textContent = '⏳ 批量生成关键帧中（可能需要1-2分钟）...';
  progress.start('gen-all-frames', '批量生成关键帧', '正在逐个生成分镜关键帧...');

  try {
    const res = await apiPost<{ success: boolean; total: number; done: number; project: Project }>(
      '/v1/pro-mode/storyboard/frame-all', { project_id: project.id }
    );
    if (res.project) setProject(res.project);
    if (statusEl) statusEl.textContent = `✅ 关键帧生成完成：${res.done}/${res.total} 成功`;
    progress.done('gen-all-frames', `${res.done}/${res.total} 成功`);
    renderShotTable(res.project || project);
  } catch (e: any) {
    if (statusEl) statusEl.textContent = `❌ ${e.message}`;
    progress.fail('gen-all-frames', e.message);
  } finally {
    if (frameAllBtn) { frameAllBtn.disabled = false; frameAllBtn.textContent = '🖼 批量生成关键帧'; }
  }
}

// ── Render shot table ─────────────────────────────────────────────

function renderShotTable(project: Project): void {
  const section = _rootEl?.querySelector('#sp-table-section') as HTMLElement;
  if (!section) return;
  section.innerHTML = '';

  const shots = project.shots;
  const charMap = new Map(project.characters.map(c => [c.id, c]));
  const sceneMap = new Map(project.scenes.map(s => [s.id, s]));

  section.appendChild(h('div', 'display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;', [
    `<h3 style="font-size:16px;font-weight:600;color:#111827;margin:0;">分镜表 (${shots.length} 镜)</h3>`,
  ]));

  if (shots.length === 0) {
    section.appendChild(h('div', 'text-align:center;padding:40px;color:#9ca3af;font-size:14px;', ['点击上方按钮拆解分镜']));
    return;
  }

  const table = h('div', 'display:flex;flex-direction:column;gap:8px;');
  shots.forEach((shot, idx) => {
    const charNames = shot.character_ids?.map(cid => charMap.get(cid)?.name || cid).join(', ') || '—';
    const sceneName = sceneMap.get(shot.scene_id)?.name || '—';

    const row = h('div', 'background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px;display:flex;gap:10px;align-items:flex-start;');

    row.appendChild(h('div', 'width:36px;height:36px;border-radius:50%;background:#4f46e5;color:#fff;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex-shrink:0;', [String(shot.shot_number)]));

    const content = h('div', 'flex:1;min-width:0;display:flex;flex-direction:column;gap:6px;');

    // Editable fields
    content.innerHTML = `
      <textarea data-idx="${idx}" data-field="description" rows="2" style="width:100%;padding:6px 8px;border:1px solid #e5e7eb;border-radius:6px;font-size:12px;resize:vertical;box-sizing:border-box;">${shot.description || ''}</textarea>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:11px;color:#6b7280;">角色:</span><span style="font-size:12px;color:#4f46e5;background:#eef2ff;padding:2px 8px;border-radius:10px;">${charNames}</span>
        <span style="font-size:11px;color:#6b7280;">场景:</span><span style="font-size:12px;color:#059669;background:#ecfdf5;padding:2px 8px;border-radius:10px;">${sceneName}</span>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <input data-idx="${idx}" data-field="camera" value="${shot.camera || ''}" placeholder="镜头运动" style="flex:2;padding:5px 8px;border:1px solid #e5e7eb;border-radius:6px;font-size:11px;min-width:100px;">
        <input data-idx="${idx}" data-field="duration" type="number" min="4" max="15" value="${shot.duration || 5}" style="flex:1;padding:5px 8px;border:1px solid #e5e7eb;border-radius:6px;font-size:11px;min-width:60px;">
        <input data-idx="${idx}" data-field="mood" value="${shot.mood || ''}" placeholder="情绪" style="flex:1;padding:5px 8px;border:1px solid #e5e7eb;border-radius:6px;font-size:11px;min-width:60px;">
      </div>
      <input data-idx="${idx}" data-field="dialogue" value="${shot.dialogue || ''}" placeholder="对白" style="width:100%;padding:5px 8px;border:1px solid #e5e7eb;border-radius:6px;font-size:11px;box-sizing:border-box;">
    `;

    // Frame image section
    const frameSection = h('div', 'display:flex;gap:8px;align-items:center;margin-top:4px;');

    // Frame thumbnail or placeholder
    if (shot.frame_image_url) {
      frameSection.insertAdjacentHTML('beforeend',
        `<img src="/api/v1${shot.frame_image_url}" style="width:80px;height:45px;object-fit:cover;border-radius:6px;border:1px solid #e5e7eb;" alt="frame">`
      );
    } else {
      frameSection.insertAdjacentHTML('beforeend',
        `<div style="width:80px;height:45px;background:#f9fafb;border:1px dashed #d1d5db;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:10px;color:#9ca3af;">无关键帧</div>`
      );
    }

    // Frame status badge
    frameSection.insertAdjacentHTML('beforeend', frameStatusBadge(shot.frame_status));

    // Generate frame button
    const canGenFrame = !shot.frame_status || ['pending', 'failed', 'stale'].includes(shot.frame_status || '');
    if (canGenFrame) {
      const frameBtn = h('button', 'padding:4px 12px;border:1px solid #7c3aed;background:#f5f3ff;color:#7c3aed;border-radius:6px;font-size:11px;cursor:pointer;font-weight:600;', ['🖼 生成关键帧']);
      frameBtn.addEventListener('click', (e) => { e.stopPropagation(); handleGenerateFrame(shot.shot_number); });
      frameSection.appendChild(frameBtn);
    }

    content.appendChild(frameSection);
    row.appendChild(content);
    table.appendChild(row);
  });

  // Add shot button
  const addBtn = h('button', 'padding:10px;border:2px dashed #d1d5db;background:#fff;border-radius:10px;cursor:pointer;font-size:13px;color:#6b7280;', ['+ 添加镜头']);
  addBtn.addEventListener('click', () => {
    project.shots.push({ shot_number: project.shots.length + 1, description: '', character_ids: [], scene_id: '', prop_ids: [], camera: '', duration: 5, dialogue: '', mood: '' });
    renderShotTable(project);
  });
  table.appendChild(addBtn);

  // Actions
  const actions = h('div', 'display:flex;gap:8px;margin-top:12px;');
  const saveBtn = h('button', 'padding:12px 24px;background:#4f46e5;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;', ['💾 保存分镜']);
  saveBtn.addEventListener('click', () => saveStoryboard(project));
  actions.appendChild(saveBtn);

  const nextBtn = h('button', 'padding:12px 24px;background:#10b981;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;', ['→ 下一步：导演台']);
  nextBtn.addEventListener('click', () => { markStepReady(2); navigateToStep(3); });
  actions.appendChild(nextBtn);
  actions.appendChild(h('div', 'id="sp-save-status";font-size:12px;color:#6b7280;display:flex;align-items:center;margin-left:12px;', []));
  table.appendChild(actions);

  section.appendChild(table);
}

async function saveStoryboard(project: Project): Promise<void> {
  const section = _rootEl?.querySelector('#sp-table-section') as HTMLElement;
  if (!section) return;

  const shots: Shot[] = project.shots.map((shot, idx) => {
    const result: any = { ...shot };
    section.querySelectorAll(`[data-idx="${idx}"]`).forEach((el: any) => {
      const field = el.dataset.field;
      if (field === 'duration') result[field] = parseInt(el.value) || 5;
      else result[field] = el.value;
    });
    return result as Shot;
  });

  const statusEl = section.querySelector('#sp-save-status') as HTMLElement;
  if (statusEl) statusEl.textContent = '⏳ 保存中...';

  try {
    const res = await apiPut<{ success: boolean; project: Project; stale_stats?: any }>(`/v1/pro-mode/storyboard/${project.id}`, { shots });
    setProject(res.project);
    markStepReady(2);
    if (statusEl) {
      const stale = res.stale_stats;
      if (stale && (stale.stale_visual?.length || stale.stale_video?.length)) {
        statusEl.textContent = `✅ 保存成功（${stale.stale_visual.length} 镜画面变更，${stale.stale_video.length} 镜视频需重新生成）`;
      } else {
        statusEl.textContent = '✅ 保存成功';
      }
    }
  } catch (e: any) {
    if (statusEl) statusEl.textContent = `❌ ${e.message}`;
  }
}

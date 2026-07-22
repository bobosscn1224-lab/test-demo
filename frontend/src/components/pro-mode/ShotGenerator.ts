/** Pro Mode Step 5 — Shot-by-Shot Generator (逐镜生成).
 *
 *  Key changes from old version:
 *  - Status is server-authoritative: polls /generate/shot-status/{pid}/{sn} instead of /video-gen/tasks/{task_id}
 *  - Batch generation via /generate/batch
 *  - Shows first-frame anchor (key frame image) when available
 *  - Shows video preview when succeeded
 *  - State persists across page refreshes (backend stores task_id, video_path, etc.)
 */

import { apiGet, apiPost } from '../../services/api';
import { getProject } from './state';
import type { Shot } from './types';
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
let _promptCache: Record<number, string> = {};
let _pollTimer: ReturnType<typeof setInterval> | null = null;

// Status display config
const STATUS_MAP: Record<string, { icon: string; color: string; label: string }> = {
  pending:   { icon: '⏸', color: '#9ca3af', label: '待生成' },
  queued:    { icon: '⏳', color: '#d97706', label: '生成中' },
  succeeded: { icon: '✅', color: '#059669', label: '已完成' },
  failed:    { icon: '❌', color: '#dc2626', label: '失败' },
  stale:     { icon: '🔄', color: '#ea580c', label: '已过期' },
};

export function renderShotGenerator(): HTMLElement {
  _rootEl = document.createElement('div');
  _rootEl.style.cssText = 'display:flex;flex-direction:column;gap:16px;height:100%;min-height:0;';

  const project = getProject();
  if (!project || project.shots.length === 0) {
    _rootEl.appendChild(h('div', 'text-align:center;padding:40px;color:#f59e0b;font-size:14px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;', ['⚠️ 请先完成步骤 3：分镜计划']));
    return _rootEl;
  }

  _rootEl.innerHTML = `
    <div>
      <h3 style="font-size:18px;font-weight:700;color:#111827;margin:0 0 4px;">🚀 步骤 5：逐镜生成</h3>
      <p style="font-size:13px;color:#6b7280;margin:0;">基于分镜表和关键帧，逐个镜头生成视频。有关键帧的镜头自动使用首帧锚定。</p>
    </div>
  `;

  // Summary bar
  const dirCfg = project.director_config;
  const totalShots = project.shots.length;
  const totalDuration = project.shots.reduce((s: number, sh: Shot) => s + (sh.duration || 5), 0);
  const frameReady = project.shots.filter(s => s.frame_status === 'done').length;
  _rootEl.appendChild(h('div', 'background:#eef2ff;border:1px solid #c7d2fe;border-radius:10px;padding:14px;font-size:13px;color:#4f46e5;', [
    `<span style="font-weight:600;">📊 ${totalShots} 镜 · ${totalDuration}s 总时长 · 关键帧 ${frameReady}/${totalShots} · ${project.characters.length} 角色 · ${project.scenes.length} 场景</span>${dirCfg ? ` · 导演：${dirCfg.pace?.slice(0, 20) || '未设置'}` : ''}`,
  ]));

  // Action bar
  const actionBar = h('div', 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;');
  const batchBtn = h('button', 'padding:10px 20px;background:#4f46e5;color:#fff;border:none;border-radius:10px;font-size:13px;font-weight:600;cursor:pointer;', ['🚀 批量生成所有镜头']);
  batchBtn.id = 'sg-batch-btn';
  batchBtn.addEventListener('click', () => handleBatchGenerate());
  actionBar.appendChild(batchBtn);

  actionBar.appendChild(h('div', 'id="sg-global-status";font-size:12px;color:#6b7280;flex:1;', []));
  _rootEl.appendChild(actionBar);

  // Shot list
  const shotList = h('div', 'flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:8px;min-height:0;');
  shotList.id = 'sg-shot-list';
  _rootEl.appendChild(shotList);

  // Load prompts and initial status, then render
  Promise.all([
    loadPrompts(project.shots),
    loadInitialStatus(project.id),
  ]).then(() => {
    renderShotCards(shotList, project.shots);
    // Start polling if any shots are queued
    const hasQueued = project.shots.some(s => s.video_status === 'queued');
    if (hasQueued && !_pollTimer) startPolling();
  });

  return _rootEl;
}

async function loadPrompts(shots: Shot[]): Promise<void> {
  const project = getProject();
  if (!project) return;
  for (const shot of shots) {
    try {
      const data = await apiGet<{ success: boolean; prompt: string; has_first_frame: boolean }>(
        `/v1/pro-mode/generate/shot-prompt/${project.id}/${shot.shot_number}`
      );
      _promptCache[shot.shot_number] = data.prompt;
    } catch {
      _promptCache[shot.shot_number] = shot.description || '(无内容)';
    }
  }
}

async function loadInitialStatus(projectId: string): Promise<void> {
  try {
    const data = await apiGet<{ success: boolean; shots: any[] }>(`/v1/pro-mode/generate/shots-status/${projectId}`);
    const project = getProject();
    if (!project) return;
    for (const s of data.shots) {
      const shot = project.shots.find(sh => sh.shot_number === s.shot_number);
      if (shot) {
        shot.frame_status = s.frame_status;
        shot.frame_image_url = s.frame_image_url;
        shot.video_status = s.video_status;
        shot.video_url = s.video_url;
        shot.last_frame_url = s.last_frame_url;
        shot.error = s.error;
      }
    }
  } catch { /* ignore — will use project's stored state */ }
}

// ── Render ────────────────────────────────────────────────────────

function renderShotCards(container: HTMLElement, shots: Shot[]): void {
  container.innerHTML = '';

  shots.forEach(shot => {
    const prompt = _promptCache[shot.shot_number] || shot.description || '';
    const vStatus = shot.video_status || 'pending';
    const st = STATUS_MAP[vStatus] || STATUS_MAP.pending;

    const card = h('div', 'background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px;display:flex;gap:12px;align-items:flex-start;');

    // Status indicator
    card.appendChild(h('div', `width:40px;height:40px;border-radius:50%;background:${st.color};color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;`, [st.icon]));

    // Content
    const content = h('div', 'flex:1;min-width:0;');

    // Header row
    content.insertAdjacentHTML('beforeend', `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap;">
        <span style="font-size:14px;font-weight:700;color:#111827;">Shot ${shot.shot_number}</span>
        <span style="font-size:11px;color:#9ca3af;">${shot.duration}s · ${shot.camera || '静态'} · ${shot.mood || ''}</span>
        <span style="font-size:11px;font-weight:600;padding:1px 8px;border-radius:10px;background:${st.color}20;color:${st.color};">${st.label}</span>
        ${shot.frame_status === 'done' ? '<span style="font-size:11px;padding:1px 8px;border-radius:10px;background:#7c3aed20;color:#7c3aed;">🎯 首帧锚定</span>' : ''}
      </div>
    `);

    // Frame image thumbnail (if available)
    if (shot.frame_image_url) {
      content.insertAdjacentHTML('beforeend', `
        <div style="margin-bottom:6px;">
          <img src="/api/v1${shot.frame_image_url}" style="width:120px;height:68px;object-fit:cover;border-radius:6px;border:1px solid #e5e7eb;" alt="first frame">
        </div>
      `);
    }

    // Prompt preview
    content.insertAdjacentHTML('beforeend', `
      <div style="font-size:12px;color:#374151;line-height:1.5;background:#fafafa;padding:8px;border-radius:6px;max-height:200px;overflow-y:auto;margin-bottom:6px;white-space:pre-wrap;font-family:monospace;">${prompt}</div>
      <button class="sg-copy-btn" style="padding:2px 10px;border:1px solid #d1d5db;background:#fff;border-radius:4px;font-size:10px;cursor:pointer;margin-bottom:6px;">📋 复制 prompt</button>
    `);

    // Video preview (if succeeded)
    if (vStatus === 'succeeded' && shot.video_url) {
      content.insertAdjacentHTML('beforeend', `
        <div style="margin-bottom:6px;">
          <video src="/api/v1${shot.video_url}" controls style="width:100%;max-width:400px;border-radius:8px;border:1px solid #e5e7eb;"></video>
        </div>
      `);
    }

    // Error message
    if (vStatus === 'failed' && shot.error) {
      content.appendChild(h('div', 'font-size:11px;color:#dc2626;background:#fef2f2;padding:4px 8px;border-radius:4px;margin-bottom:6px;', [`❌ ${shot.error}`]));
    }

    // Action buttons
    if (vStatus === 'pending' || vStatus === 'failed' || vStatus === 'stale') {
      const btn = h('button',
        `padding:6px 14px;border:1px solid ${vStatus === 'failed' ? '#f59e0b' : vStatus === 'stale' ? '#ea580c' : '#4f46e5'};background:${vStatus === 'failed' ? '#fffbeb' : vStatus === 'stale' ? '#fff7ed' : '#eef2ff'};color:${vStatus === 'failed' ? '#d97706' : vStatus === 'stale' ? '#ea580c' : '#4f46e5'};border-radius:6px;font-size:11px;cursor:pointer;font-weight:600;`,
        [vStatus === 'failed' ? '🔄 重试' : vStatus === 'stale' ? '🔄 重新生成' : '🎬 生成此镜']
      );
      btn.addEventListener('click', () => generateShot(shot));
      content.appendChild(btn);
    } else if (vStatus === 'queued') {
      content.appendChild(h('div', 'font-size:11px;color:#d97706;', ['⏳ 生成中，自动轮询...']));
    }

    // Bind copy button
    const copyBtn = content.querySelector('.sg-copy-btn') as HTMLButtonElement;
    if (copyBtn) {
      copyBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(prompt).then(() => {
          copyBtn.textContent = '✅ 已复制';
          setTimeout(() => { copyBtn.textContent = '📋 复制 prompt'; }, 2000);
        }).catch(() => {
          copyBtn.textContent = '❌ 失败';
          setTimeout(() => { copyBtn.textContent = '📋 复制 prompt'; }, 2000);
        });
      });
    }

    card.appendChild(content);
    container.appendChild(card);
  });
}

// ── Actions ───────────────────────────────────────────────────────

async function generateShot(shot: Shot): Promise<void> {
  const project = getProject();
  if (!project) return;

  const statusEl = _rootEl?.querySelector('#sg-global-status') as HTMLElement;
  if (statusEl) statusEl.textContent = `⏳ 提交 Shot ${shot.shot_number}...`;
  const pkey = `gen-shot-${shot.shot_number}`;
  progress.start(pkey, `生成视频：Shot ${shot.shot_number}`, '正在提交到 Seedance...');

  try {
    const res = await apiPost<{ success: boolean; task_id: string; status: string; used_first_frame: boolean }>(
      '/v1/pro-mode/generate/shot', {
        project_id: project.id,
        shot_number: shot.shot_number,
        model: 'fast',
        resolution: '720p',
        ratio: '16:9',
        generate_audio: false,
        return_last_frame: true,
      }
    );

    // Update local state
    shot.task_id = res.task_id;
    shot.video_status = 'queued';
    shot.error = '';
    refreshCards(project.shots);

    if (statusEl) statusEl.textContent = res.used_first_frame ? `✅ Shot ${shot.shot_number} 已提交（首帧锚定）` : `✅ Shot ${shot.shot_number} 已提交`;
    progress.update(pkey, '已提交，等待 Seedance 生成...');

    if (!_pollTimer) startPolling();
  } catch (e: any) {
    shot.video_status = 'failed';
    shot.error = e.message;
    refreshCards(project.shots);
    if (statusEl) statusEl.textContent = `❌ Shot ${shot.shot_number} 提交失败: ${e.message}`;
    progress.fail(pkey, e.message);
  }
}

async function handleBatchGenerate(): Promise<void> {
  const project = getProject();
  if (!project) return;

  const statusEl = _rootEl?.querySelector('#sg-global-status') as HTMLElement;
  const batchBtn = _rootEl?.querySelector('#sg-batch-btn') as HTMLButtonElement;
  if (batchBtn) { batchBtn.disabled = true; batchBtn.textContent = '⏳ 批量提交中...'; }
  if (statusEl) statusEl.textContent = '⏳ 批量提交中...';
  progress.start('batch-gen', '批量生成视频', '正在逐个提交镜头到 Seedance...');

  try {
    const res = await apiPost<{ success: boolean; submitted_count: number; submitted: any[]; skipped: number[]; failed: any[] }>(
      '/v1/pro-mode/generate/batch', {
        project_id: project.id,
        model: 'fast',
        resolution: '720p',
        ratio: '16:9',
        generate_audio: false,
        include_failed: true,
      }
    );

    // Update local state for submitted shots
    for (const sub of res.submitted) {
      const shot = project.shots.find(s => s.shot_number === sub.shot_number);
      if (shot) {
        shot.task_id = sub.task_id;
        shot.video_status = 'queued';
        shot.error = '';
      }
    }
    // Update failed shots
    for (const f of res.failed) {
      const shot = project.shots.find(s => s.shot_number === f.shot_number);
      if (shot) {
        shot.video_status = 'failed';
        shot.error = f.error;
      }
    }

    refreshCards(project.shots);

    const msg = `✅ 批量提交完成：${res.submitted_count} 个已提交，${res.skipped.length} 个跳过，${res.failed.length} 个失败`;
    if (statusEl) statusEl.textContent = msg;
    progress.done('batch-gen', `${res.submitted_count} 个已提交`);

    if (res.submitted_count > 0 && !_pollTimer) startPolling();
  } catch (e: any) {
    if (statusEl) statusEl.textContent = `❌ 批量生成失败: ${e.message}`;
    progress.fail('batch-gen', e.message);
  } finally {
    if (batchBtn) { batchBtn.disabled = false; batchBtn.textContent = '🚀 批量生成所有镜头'; }
  }
}

// ── Server-side polling ───────────────────────────────────────────

function startPolling(): void {
  if (_pollTimer) clearInterval(_pollTimer);

  _pollTimer = setInterval(async () => {
    const project = getProject();
    if (!project) { stopPolling(); return; }

    let hasQueued = false;

    for (const shot of project.shots) {
      if (shot.video_status === 'queued') {
        hasQueued = true;
        try {
          const data = await apiGet<{
            video_status: string; video_url: string; video_path: string;
            last_frame_url: string; error: string;
          }>(`/v1/pro-mode/generate/shot-status/${project.id}/${shot.shot_number}`);

          const prevStatus = shot.video_status;
          shot.video_status = data.video_status as any;
          shot.video_url = data.video_url || '';
          shot.video_path = data.video_path || '';
          shot.last_frame_url = data.last_frame_url || '';
          if (data.error) shot.error = data.error;

          // Update progress when status transitions to terminal
          const pkey = `gen-shot-${shot.shot_number}`;
          if (prevStatus === 'queued' && data.video_status === 'succeeded') {
            progress.done(pkey, '视频生成完成');
          } else if (prevStatus === 'queued' && data.video_status === 'failed') {
            progress.fail(pkey, data.error || '生成失败');
          } else if (data.video_status === 'queued') {
            progress.update(pkey, 'Seedance 生成中...');
          }
        } catch {
          // Network error — keep queued, will retry next interval
        }
      }
    }

    refreshCards(project.shots);

    if (!hasQueued) stopPolling();
  }, 8000); // 8 second interval — server does the real Seedance poll
}

function stopPolling(): void {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

function refreshCards(shots: Shot[]): void {
  const container = document.getElementById('sg-shot-list');
  if (container) renderShotCards(container, shots);
}

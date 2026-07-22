/** Pro Mode Step 5 — Auto Compose (自动成片).
 *
 *  Checks all shots' generation status, builds composed video with subtitles.
 *  Supports partial compose (only ready shots are concatenated; missing ones listed).
 */

import { apiGet, apiPost } from '../../services/api';
import { getProject, markStepReady } from './state';
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

export function renderAutoCompose(): HTMLElement {
  _rootEl = document.createElement('div');
  _rootEl.style.cssText = 'display:flex;flex-direction:column;gap:16px;max-width:800px;';

  const project = getProject();
  if (!project) {
    _rootEl.appendChild(h('div', 'text-align:center;padding:40px;color:#f59e0b;font-size:14px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;', ['⚠️ 请先完成前面步骤']));
    return _rootEl;
  }

  _rootEl.innerHTML = `
    <div>
      <h3 style="font-size:18px;font-weight:700;color:#111827;margin:0 0 4px;">🎞 步骤 6：自动成片</h3>
      <p style="font-size:13px;color:#6b7280;margin:0;">检查所有镜头生成状态，一键拼接 + 字幕 + 导出成片</p>
    </div>
    <div id="ac-status-panel" style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;">
      <div style="text-align:center;padding:20px;color:#9ca3af;">加载中...</div>
    </div>
    <div id="ac-actions" style="display:flex;gap:10px;flex-wrap:wrap;"></div>
  `;

  // Load status
  setTimeout(() => loadComposeStatus(), 0);

  return _rootEl;
}

async function loadComposeStatus(): Promise<void> {
  const project = getProject();
  if (!project) return;

  const panel = _rootEl?.querySelector('#ac-status-panel') as HTMLElement;
  if (!panel) return;

  try {
    const data = await apiGet<{
      success: boolean; total_shots: number; ready_shots: number;
      can_compose: boolean; all_ready: boolean; ffmpeg_available: boolean;
      shots: any[];
    }>(`/v1/pro-mode/compose/status/${project.id}`);

    const pct = data.total_shots > 0 ? Math.round((data.ready_shots / data.total_shots) * 100) : 0;
    const missingShots = data.shots.filter((s: any) => s.status !== 'ready');

    panel.innerHTML = `
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;">
        <div style="width:80px;height:80px;border-radius:50%;background:${data.all_ready ? '#ecfdf5' : data.can_compose ? '#fef3c7' : '#fef2f2'};display:flex;align-items:center;justify-content:center;font-size:32px;">${data.all_ready ? '✅' : data.can_compose ? '⚠️' : '⏳'}</div>
        <div>
          <div style="font-size:16px;font-weight:700;color:#111827;">${data.all_ready ? '全部就绪，可以成片！' : data.can_compose ? '部分镜头就绪，可部分合成' : '镜头尚未生成'}</div>
          <div style="font-size:13px;color:#6b7280;">${data.ready_shots} / ${data.total_shots} 个镜头已就绪${missingShots.length > 0 ? ` · 缺失 ${missingShots.length} 个` : ''}</div>
          <div style="width:200px;height:6px;background:#f3f4f6;border-radius:3px;margin-top:8px;overflow:hidden;">
            <div style="width:${pct}%;height:100%;background:${data.all_ready ? '#10b981' : data.can_compose ? '#f59e0b' : '#dc2626'};border-radius:3px;"></div>
          </div>
        </div>
      </div>
      ${!data.ffmpeg_available ? '<div style="font-size:12px;color:#dc2626;background:#fef2f2;padding:8px;border-radius:6px;margin-bottom:12px;">⚠️ ffmpeg 不可用，请联系管理员安装 ffmpeg 或 imageio-ffmpeg</div>' : ''}
      <div style="display:flex;flex-direction:column;gap:6px;">
        ${data.shots.map((s: any) => `
          <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:${s.status === 'ready' ? '#f0fdf4' : '#fafafa'};border-radius:8px;">
            <span style="font-size:16px;">${s.status === 'ready' ? '✅' : s.status === 'queued' ? '⏳' : s.status === 'failed' ? '❌' : s.status === 'stale' ? '🔄' : '⏸'}</span>
            <span style="font-size:13px;font-weight:600;color:#111827;">Shot ${s.shot_number}</span>
            <span style="font-size:12px;color:#9ca3af;">${s.duration}s</span>
            <span style="font-size:12px;color:#6b7280;flex:1;">${s.description}</span>
            ${s.error ? `<span style="font-size:11px;color:#dc2626;">${s.error.slice(0, 30)}</span>` : ''}
            ${s.dialogue ? `<span style="font-size:11px;color:#8b5cf6;">💬 ${s.dialogue.slice(0,15)}...</span>` : ''}
          </div>
        `).join('')}
      </div>
    `;

    // Actions
    const actions = _rootEl?.querySelector('#ac-actions') as HTMLElement;
    if (!actions) return;
    actions.innerHTML = '';

    if (data.can_compose && data.ffmpeg_available) {
      if (data.all_ready) {
        const buildBtn = h('button', 'padding:14px 32px;background:#dc2626;color:#fff;border:none;border-radius:12px;font-size:16px;font-weight:700;cursor:pointer;', ['🎬 合成成片']);
        buildBtn.addEventListener('click', () => handleBuild(false));
        actions.appendChild(buildBtn);

        const buildSubBtn = h('button', 'padding:14px 24px;background:#fff;color:#4f46e5;border:2px solid #4f46e5;border-radius:12px;font-size:14px;font-weight:600;cursor:pointer;', ['📝 含字幕合成']);
        buildSubBtn.addEventListener('click', () => handleBuild(true));
        actions.appendChild(buildSubBtn);
      } else {
        // Partial compose
        const partialBtn = h('button', 'padding:14px 32px;background:#f59e0b;color:#fff;border:none;border-radius:12px;font-size:16px;font-weight:700;cursor:pointer;', ['🎬 部分合成（仅就绪镜头）']);
        partialBtn.addEventListener('click', () => handleBuild(false));
        actions.appendChild(partialBtn);

        const partialSubBtn = h('button', 'padding:14px 24px;background:#fff;color:#f59e0b;border:2px solid #f59e0b;border-radius:12px;font-size:14px;font-weight:600;cursor:pointer;', ['📝 部分合成+字幕']);
        partialSubBtn.addEventListener('click', () => handleBuild(true));
        actions.appendChild(partialSubBtn);

        actions.insertAdjacentHTML('beforeend', '<span style="font-size:12px;color:#f59e0b;align-self:center;">⚠️ 缺失镜头将被跳过，建议先完成全部生成</span>');
      }
    } else if (!data.ffmpeg_available) {
      actions.innerHTML = '<span style="font-size:13px;color:#dc2626;">⚠️ ffmpeg 不可用，无法合成</span>';
    } else {
      actions.innerHTML = '<span style="font-size:13px;color:#f59e0b;">⚠️ 请先在步骤 5 完成至少一个镜头的视频生成</span>';
    }

    markStepReady(5);
  } catch (e: any) {
    panel.innerHTML = `<div style="text-align:center;padding:20px;color:#e74c3c;">加载失败: ${e.message}</div>`;
  }
}

async function handleBuild(addSubtitles: boolean = false): Promise<void> {
  const project = getProject();
  if (!project) return;

  const panel = _rootEl?.querySelector('#ac-status-panel') as HTMLElement;
  if (panel) panel.innerHTML = '<div style="text-align:center;padding:40px;">⏳ 正在合成视频...</div>';

  // Clear actions
  const actions = _rootEl?.querySelector('#ac-actions') as HTMLElement;
  if (actions) actions.innerHTML = '';

  try {
    const res = await progress.withAsync(
      'compose-build', `合成成片${addSubtitles ? '（含字幕）' : ''}`,
      async (update) => {
        update('正在用 ffmpeg 拼接视频...');
        const result = await apiPost<{
          success: boolean; download_url: string; video_count: number;
          missing_shots: number[]; subtitle_count: number; total_duration: number;
        }>('/v1/pro-mode/compose/build', {
          project_id: project.id,
          add_subtitles: addSubtitles,
          bgm_type: 'auto',
        });
        update(`拼接完成，${result.video_count} 个镜头，${result.total_duration}s`);
        return result;
      },
      '正在合成视频（可能需要 1-3 分钟）...',
    );

    if (res.success) {
      const missingInfo = res.missing_shots.length > 0
        ? `<div style="font-size:12px;color:#f59e0b;margin-top:4px;">⚠️ 跳过了 ${res.missing_shots.length} 个未就绪镜头：Shot ${res.missing_shots.join(', ')}</div>`
        : '';

      panel!.innerHTML = `
        <div style="text-align:center;padding:40px;">
          <div style="font-size:48px;margin-bottom:12px;">🎉</div>
          <div style="font-size:18px;font-weight:700;color:#111827;margin-bottom:8px;">成片合成完成！</div>
          <div style="font-size:13px;color:#6b7280;margin-bottom:4px;">${res.video_count} 个镜头已拼接 · 总时长 ${res.total_duration}s${addSubtitles ? ` · ${res.subtitle_count} 条字幕` : ''}</div>
          ${missingInfo}
          <div style="margin-top:20px;">
            <a href="/api/v1${res.download_url}" download style="display:inline-block;padding:14px 40px;background:#4f46e5;color:#fff;border-radius:12px;text-decoration:none;font-size:16px;font-weight:700;">📥 下载成片</a>
          </div>
        </div>
      `;
    }
  } catch (e: any) {
    if (panel) panel.innerHTML = `<div style="text-align:center;padding:20px;color:#e74c3c;">❌ 合成失败: ${e.message}</div>`;
  }
}

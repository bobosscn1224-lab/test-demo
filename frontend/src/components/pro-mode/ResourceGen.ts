/** Pro Mode Step 2 — Resource Generation (资源生成).
 *
 *  Features:
 *  - Per-card generate button with loading state (fixes "no response" bug)
 *  - Per-character portrait button (only shown when no asset:// ID)
 *  - Per-resource "upload to asset library" button (get asset:// ID for existing images)
 *  - Asset ID status badge on each card
 *  - One-click generate all + pick from library
 */

import { apiGet, apiPost } from '../../services/api';
import { getProject, setProject, markStepReady } from './state';
import { navigateToStep } from './index';
import type { Project, ExtractedCharacter, ExtractedScene, ExtractedProp } from './types';
import { progress } from './progress';

interface AssetItem { asset_id: string; asset_url: string; label: string; category: string; public_url: string; status: string; }

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
let _generating = false;
// Track per-card loading state: `${rtype}:${resourceId}` → true
const _cardLoading = new Set<string>();

export function renderResourceGen(): HTMLElement {
  _rootEl = document.createElement('div');
  _rootEl.style.cssText = 'display:flex;flex-direction:column;gap:16px;max-width:900px;';

  const project = getProject();
  if (!project) {
    _rootEl.appendChild(h('div', 'text-align:center;padding:40px;color:#f59e0b;font-size:14px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;', ['⚠️ 请先完成步骤 1：剧本分析']));
    return _rootEl;
  }

  _rootEl.innerHTML = `
    <div>
      <h3 style="font-size:18px;font-weight:700;color:#111827;margin:0 0 4px;">🎨 步骤 2：资源生成</h3>
      <p style="font-size:13px;color:#6b7280;margin:0;">为角色/场景/道具生成参考图。真人角色需获取素材 ID（asset://）才能在视频生成中保持一致性</p>
    </div>
  `;

  // Toolbar
  const toolbar = h('div', 'display:flex;align-items:center;gap:12px;flex-wrap:wrap;');
  const genAllBtn = h('button', 'padding:12px 24px;background:#8b5cf6;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;', ['🎨 一键生成全部资源图']);
  genAllBtn.addEventListener('click', handleGenerateAll);
  toolbar.appendChild(genAllBtn);

  toolbar.appendChild(h('span', 'font-size:12px;color:#9ca3af;', ['也可点击单个资源卡片上的按钮生成']));
  _rootEl.appendChild(toolbar);
  _rootEl.appendChild(h('div', 'id="rg-status";font-size:13px;text-align:center;color:#6b7280;min-height:20px;', []));

  // Resource cards
  const cardsContainer = h('div', 'display:flex;flex-direction:column;gap:20px;');
  cardsContainer.appendChild(renderResourceCards('🧑 角色', project.characters, 'characters'));
  cardsContainer.appendChild(renderResourceCards('🏞 场景', project.scenes, 'scenes'));
  if (project.props.length > 0) {
    cardsContainer.appendChild(renderResourceCards('🎯 道具', project.props, 'props'));
  }
  _rootEl.appendChild(cardsContainer);

  // Next step
  const nextBtn = h('button', 'padding:14px 24px;background:#10b981;color:#fff;border:none;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;align-self:flex-end;', ['→ 下一步：分镜计划']);
  nextBtn.addEventListener('click', () => { markStepReady(1); navigateToStep(2); });
  _rootEl.appendChild(nextBtn);

  return _rootEl;
}

function renderResourceCards(title: string, items: (ExtractedCharacter | ExtractedScene | ExtractedProp)[], rtype: string): HTMLElement {
  const group = h('div', '');
  group.innerHTML = `<div style="font-size:15px;font-weight:600;color:#111827;margin-bottom:10px;">${title}</div>`;

  const grid = h('div', 'display:flex;flex-wrap:wrap;gap:10px;');
  items.forEach(item => {
    grid.appendChild(renderSingleCard(item, rtype));
  });
  group.appendChild(grid);
  return group;
}

function renderSingleCard(item: ExtractedCharacter | ExtractedScene | ExtractedProp, rtype: string): HTMLElement {
  const cardKey = `${rtype}:${item.id}`;
  const isLoading = _cardLoading.has(cardKey);
  const hasAssetId = !!item.asset_id && item.asset_id.startsWith('asset-');
  const hasLocalId = !!item.asset_id && item.asset_id.startsWith('local-');
  const hasImage = !!item.generated_image_url;
  const isCharacter = rtype === 'characters';

  const statusIcon = item.status === 'done' ? '✅' : item.status === 'generating' ? '⏳' : item.status === 'failed' ? '❌' : '⏸';

  // Image area
  let imgCss: string;
  if (hasImage && item.generated_image_url) {
    imgCss = `height:160px;background:url('${item.generated_image_url}') center/cover;`;
  } else {
    imgCss = 'height:160px;background:#f3f4f6;display:flex;align-items:center;justify-content:center;font-size:40px;';
  }

  const card = h('div',
    `width:220px;background:#fff;border:1px solid ${item.status === 'done' ? '#bbf7d0' : '#e5e7eb'};border-radius:10px;overflow:hidden;display:flex;flex-direction:column;`,
  );

  // Image section
  card.insertAdjacentHTML('beforeend',
    `<div style="${imgCss}">${hasImage ? '' : statusIcon}</div>`
  );

  // Info section
  card.insertAdjacentHTML('beforeend',
    `<div style="padding:10px;">
      <div style="font-size:13px;font-weight:600;color:#111827;">${item.name}</div>
      <div style="font-size:11px;color:#9ca3af;margin:4px 0;">${(item as any).time_of_day || item.description?.slice(0, 30) || ''}</div>
    </div>`
  );

  // Asset ID badge
  if (hasAssetId) {
    card.insertAdjacentHTML('beforeend',
      `<div style="padding:0 10px 4px;"><span style="font-size:10px;padding:2px 8px;border-radius:8px;background:#ecfdf5;color:#059669;font-weight:600;">✅ asset://${item.asset_id}</span></div>`
    );
  } else if (hasLocalId) {
    card.insertAdjacentHTML('beforeend',
      `<div style="padding:0 10px 4px;"><span style="font-size:10px;padding:2px 8px;border-radius:8px;background:#fff7ed;color:#ea580c;font-weight:600;">⚠ 本地ID · 需上传</span></div>`
    );
  } else if (hasImage) {
    card.insertAdjacentHTML('beforeend',
      `<div style="padding:0 10px 4px;"><span style="font-size:10px;padding:2px 8px;border-radius:8px;background:#fef3c7;color:#d97706;font-weight:600;">📷 已有图 · 无素材ID</span></div>`
    );
  }

  // Action buttons
  const actions = h('div', 'display:flex;flex-direction:column;gap:0;padding:0;');

  // Row 1: Generate + Library
  const row1 = h('div', 'display:flex;gap:0;');

  const genBtn = h('button',
    `flex:1;padding:8px 4px;border:none;font-size:11px;font-weight:600;cursor:pointer;${
      isLoading ? 'background:#f3f4f6;color:#9ca3af;cursor:wait;'
      : item.status === 'done' ? 'background:#ecfdf5;color:#059669;'
      : 'background:#eef2ff;color:#4f46e5;'
    }`,
    [isLoading ? '⏳ 生成中...' : item.status === 'done' ? '🔄 重生成' : '🎨 生成']
  );
  if (!isLoading) {
    genBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      handleGenerateSingle(rtype, item.id);
    });
  }
  row1.appendChild(genBtn);

  const libBtn = h('button',
    'flex:1;padding:8px 4px;border:none;background:#fff;color:#6b7280;font-size:11px;cursor:pointer;border-top:1px solid #f3f4f6;',
    ['📂 素材库']
  );
  libBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    showAssetPicker(rtype, item);
  });
  row1.appendChild(libBtn);
  actions.appendChild(row1);

  // Row 2: Character-specific buttons
  if (isCharacter) {
    // For characters: show "获取素材ID" (portrait) button when no asset:// ID
    if (!hasAssetId) {
      const portraitBtn = h('button',
        `width:100%;padding:7px 4px;border:none;font-size:11px;font-weight:600;cursor:pointer;background:#fdf2f8;color:#ec4899;border-top:1px solid #f3f4f6;${
          isLoading ? 'opacity:0.5;cursor:wait;' : ''
        }`,
        [isLoading ? '⏳...' : '🎭 获取素材ID（定妆照）']
      );
      if (!isLoading) {
        portraitBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          handlePortraitSingle(item.id, item.name);
        });
      }
      actions.appendChild(portraitBtn);
    }
  }

  // Row 3: Upload to asset library (for all resources with image but no asset:// ID)
  if (hasImage && !hasAssetId) {
    const uploadBtn = h('button',
      `width:100%;padding:7px 4px;border:none;font-size:11px;font-weight:600;cursor:pointer;background:#f0fdf4;color:#16a34a;border-top:1px solid #f3f4f6;${
        isLoading ? 'opacity:0.5;cursor:wait;' : ''
      }`,
      [isLoading ? '⏳...' : '📤 加入素材库']
    );
    if (!isLoading) {
      uploadBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleUploadAsset(rtype, item.id, item.name);
      });
    }
    actions.appendChild(uploadBtn);
  }

  card.appendChild(actions);
  return card;
}

// ── Actions ───────────────────────────────────────────────────────

function setCardLoading(rtype: string, resourceId: string, loading: boolean): void {
  const key = `${rtype}:${resourceId}`;
  if (loading) _cardLoading.add(key);
  else _cardLoading.delete(key);
  refreshDisplay();
}

function setStatus(text: string): void {
  const el = document.getElementById('rg-status');
  if (el) el.textContent = text;
}

async function handleGenerateSingle(rtype: string, resourceId: string): Promise<void> {
  const project = getProject();
  if (!project) return;

  const resName = ((project as any)[rtype] as any[]).find(r => r.id === resourceId)?.name || resourceId;
  const typeLabel = rtype === 'characters' ? '角色' : rtype === 'scenes' ? '场景' : '道具';
  const pkey = `gen-${rtype}-${resourceId}`;

  // Immediately set loading state on the card
  setCardLoading(rtype, resourceId, true);
  setStatus(`⏳ 正在生成「${resName}」${typeLabel}图...`);
  progress.start(pkey, `生成${typeLabel}图：${resName}`, '调用生图模型中...');

  try {
    const res = await apiPost<{ success: boolean; resource: any }>('/v1/pro-mode/resource/generate', {
      project_id: project.id, resource_type: rtype, resource_id: resourceId,
    });
    // Update local state
    const collection = (project as any)[rtype] as any[];
    const idx = collection.findIndex((r: any) => r.id === resourceId);
    if (idx >= 0) collection[idx] = res.resource;
    setProject(project);
    setStatus(res.success ? '✅ 生成完成' : '❌ 生成失败');
    progress.done(pkey, res.success ? '生成完成' : '生成失败');
  } catch (e: any) {
    setStatus(`❌ 生成失败: ${e.message}`);
    progress.fail(pkey, e.message);
  } finally {
    setCardLoading(rtype, resourceId, false);
  }
}

async function handleGenerateAll(): Promise<void> {
  if (_generating) return;
  const project = getProject();
  if (!project) return;
  _generating = true;
  const genAllBtn = document.querySelector('#rg-toolbar button') as HTMLButtonElement;
  if (genAllBtn) { genAllBtn.disabled = true; genAllBtn.textContent = '⏳ 批量生成中...'; }
  setStatus('⏳ 批量生成中（可能需要 1-3 分钟）...');
  progress.start('gen-all', '批量生成全部资源图', '正在逐个生成角色/场景/道具图...');

  try {
    await apiPost('/v1/pro-mode/resource/generate-all', { project_id: project.id });
    progress.update('gen-all', '生成完成，正在刷新项目数据...');
    const data = await apiGet<{ success: boolean; project: Project }>(`/v1/pro-mode/project/${project.id}`);
    setProject(data.project);
    markStepReady(1);
    setStatus('✅ 资源生成完成！');
    progress.done('gen-all', '全部资源图生成完成');
    refreshDisplay();
  } catch (e: any) {
    setStatus(`❌ ${e.message}`);
    progress.fail('gen-all', e.message);
  } finally {
    _generating = false;
    if (genAllBtn) { genAllBtn.disabled = false; genAllBtn.textContent = '🎨 一键生成全部资源图'; }
  }
}

async function handlePortraitSingle(charId: string, charName: string): Promise<void> {
  const project = getProject();
  if (!project) return;

  const pkey = `portrait-${charId}`;
  setCardLoading('characters', charId, true);
  setStatus(`⏳ 为「${charName}」生成定妆照中（走 icover 审核，约 30-60 秒）...`);
  progress.start(pkey, `生成定妆照：${charName}`, '调用生图模型 + icover 审核中...');

  try {
    const res = await apiPost<{ success: boolean; portrait_url: string; asset_id: string; error?: string }>(
      '/v1/pro-mode/generate/portrait', {
        project_id: project.id, character_ids: [charId],
        style_note: '白色背景，全身照，面部清晰可识别，专业摄影棚灯光',
      }
    );

    if (res.success) {
      progress.update(pkey, '定妆照完成，正在刷新项目...');
      // Reload project to get updated state
      const data = await apiGet<{ success: boolean; project: Project }>(`/v1/pro-mode/project/${project.id}`);
      setProject(data.project);
      markStepReady(1);
      setStatus(`✅ 「${charName}」定妆照完成！asset://${res.asset_id}`);
      progress.done(pkey, `asset://${res.asset_id}`);
    } else {
      setStatus(`❌ 「${charName}」定妆照失败: ${res.error || '未知错误'}`);
      progress.fail(pkey, res.error || '未知错误');
    }
  } catch (e: any) {
    setStatus(`❌ 定妆照失败: ${e.message}`);
    progress.fail(pkey, e.message);
  } finally {
    setCardLoading('characters', charId, false);
  }
}

async function handleUploadAsset(rtype: string, resourceId: string, resName: string): Promise<void> {
  const project = getProject();
  if (!project) return;

  const pkey = `upload-${rtype}-${resourceId}`;
  setCardLoading(rtype, resourceId, true);
  setStatus(`⏳ 正在将「${resName}」上传到素材库...`);
  progress.start(pkey, `上传素材库：${resName}`, '正在上传到 icover 素材库...');

  try {
    const res = await apiPost<{ success: boolean; asset_id: string; is_icover: boolean; error?: string }>(
      '/v1/pro-mode/resource/upload-asset', {
        project_id: project.id, resource_type: rtype, resource_id: resourceId,
      }
    );

    if (res.success) {
      // Update local state
      const collection = (project as any)[rtype] as any[];
      const idx = collection.findIndex((r: any) => r.id === resourceId);
      if (idx >= 0) {
        collection[idx].asset_id = res.asset_id;
      }
      setProject(project);
      setStatus(res.is_icover
        ? `✅ 「${resName}」已上传到 icover 素材库！asset://${res.asset_id}`
        : `✅ 「${resName}」已保存到本地素材库（icover 未配置，使用本地 ID）`
      );
      progress.done(pkey, res.is_icover ? `asset://${res.asset_id}` : '本地素材ID');
    } else {
      setStatus(`❌ 上传失败: ${res.error || '未知错误'}`);
      progress.fail(pkey, res.error || '未知错误');
    }
  } catch (e: any) {
    setStatus(`❌ 上传素材库失败: ${e.message}`);
    progress.fail(pkey, e.message);
  } finally {
    setCardLoading(rtype, resourceId, false);
  }
}

// ── Asset Library Quick Picker ────────────────────────────────────

async function showAssetPicker(rtype: string, resource: any): Promise<void> {
  const project = getProject();
  if (!project || !resource) return;

  const catMap: Record<string, string> = { characters: '数字真人', scenes: '场景', props: '道具' };
  const category = catMap[rtype] || '其他';
  const resName = String(resource.name || resource.id || '资源');

  // Load assets
  let assets: AssetItem[] = [];
  try {
    const data = await apiGet<{ total: number; assets: AssetItem[] }>(`/v1/assets?category=${encodeURIComponent(category)}`);
    assets = (data.assets || []).filter(a => a.status === 'Active');
  } catch { /* ignore */ }

  // Create modal
  const modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:300;display:flex;align-items:center;justify-content:center;';
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

  const dialog = document.createElement('div');
  dialog.style.cssText = 'background:#fff;border-radius:14px;padding:24px;width:520px;max-height:70vh;display:flex;flex-direction:column;';

  // Header
  const header = document.createElement('div');
  header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;';
  header.innerHTML = `<h3 style="font-size:16px;font-weight:600;color:#111827;margin:0;">为「${resName}」选择素材</h3>`;
  const closeBtn = document.createElement('button');
  closeBtn.textContent = '×';
  closeBtn.style.cssText = 'border:none;background:none;font-size:24px;cursor:pointer;color:#9ca3af;';
  closeBtn.addEventListener('click', () => modal.remove());
  header.appendChild(closeBtn);
  dialog.appendChild(header);

  // Grid
  const grid = document.createElement('div');
  grid.style.cssText = 'flex:1;overflow-y:auto;display:flex;flex-wrap:wrap;gap:8px;min-height:120px;align-content:flex-start;';

  if (assets.length === 0) {
    grid.innerHTML = `<div style="width:100%;text-align:center;padding:40px;color:#9ca3af;font-size:13px;">📂 ${category}分类暂无可用素材<br><span style="font-size:11px;">请先生成图片并上传到素材库</span></div>`;
  } else {
    assets.forEach(a => {
      const chip = document.createElement('div');
      chip.style.cssText = 'width:80px;text-align:center;cursor:pointer;padding:6px;border-radius:8px;border:2px solid transparent;';
      chip.innerHTML = `<img src="${a.public_url}" style="width:68px;height:68px;border-radius:6px;object-fit:cover;background:#f3f4f6;" onerror="this.style.display='none'"><div style="font-size:9px;color:#6b7280;margin-top:3px;">${(a.label||'').slice(0, 8)}</div>`;
      chip.addEventListener('click', () => {
        const collection = (project as any)[rtype] as any[];
        const idx = collection.findIndex((r: any) => r.id === resource.id);
        if (idx >= 0) {
          collection[idx].generated_image_url = a.public_url;
          collection[idx].asset_id = a.asset_id;
          collection[idx].status = 'done';
          setProject(project);
        }
        modal.remove();
        refreshDisplay();
      });
      grid.appendChild(chip);
    });
  }
  dialog.appendChild(grid);

  // Cancel button
  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = '取消';
  cancelBtn.style.cssText = 'margin-top:16px;padding:10px;border:1px solid #d1d5db;background:#fff;border-radius:10px;font-size:14px;cursor:pointer;';
  cancelBtn.addEventListener('click', () => modal.remove());
  dialog.appendChild(cancelBtn);

  modal.appendChild(dialog);
  document.body.appendChild(modal);
}

function refreshDisplay(): void {
  if (!_rootEl) return;
  const parent = _rootEl.parentNode;
  if (!parent) return;
  const newContent = renderResourceGen();
  parent.replaceChild(newContent, _rootEl);
  _rootEl = newContent;
}

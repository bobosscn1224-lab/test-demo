/** Digital Human Asset Management Page — upload and manage Seedance reference images (characters, scenes, props). */

import { apiGet, apiDelete } from '../services/api';

interface AssetItem {
  asset_id: string;
  asset_url: string;
  label: string;
  category: string;
  group_id: string;
  public_url: string;
  status: string;
  filename: string;
  created_at: string;
}

const CATEGORIES = ['数字真人', '场景', '道具', '其他'];
const CATEGORY_ICONS: Record<string, string> = { '数字真人': '🧑', '场景': '🏞', '道具': '🎯', '其他': '📦' };
const API_CATEGORY = '数字真人';  // Only this category uses icover API

interface GroupItem {
  group_id: string;
  name: string;
}

export function renderAssetManagePage(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'feature-page';
  el.style.cssText = 'padding:24px;max-width:1100px;margin:0 auto;height:100%;overflow-y:auto;';

  el.innerHTML = `
    <h2 style="font-size:20px;font-weight:700;color:#111827;margin-bottom:4px;">🧑 数字人资产管理</h2>
    <p style="color:#6b7280;font-size:14px;margin-bottom:20px;">
      上传虚拟人/数字人照片，自动入库到 Seedance 素材库，获得可用于视频生成的 asset:// ID
    </p>

    <!-- Upload Section -->
    <div style="background:#f9fafb;border-radius:12px;padding:20px;margin-bottom:20px;">
      <h3 style="font-size:16px;font-weight:600;color:#374151;margin:0 0 16px;">📤 上传新素材</h3>
      <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;">
        <div style="flex:1;min-width:180px;">
          <label style="display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;">选择图片</label>
          <input type="file" id="asset-file-input" accept="image/*"
            style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;">
        </div>
        <div style="flex:1;min-width:130px;">
          <label style="display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;">标签（可选）</label>
          <input type="text" id="asset-label-input" placeholder="例如：艺人A-正面照"
            style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;">
        </div>
        <div style="min-width:100px;">
          <label style="display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;">分类</label>
          <select id="asset-category-select"
            style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;">
            ${CATEGORIES.map(c => `<option value="${c}">${CATEGORY_ICONS[c]} ${c}</option>`).join('')}
          </select>
        </div>
        <button id="asset-upload-btn"
          style="padding:10px 24px;background:#4f46e5;color:#fff;border:none;border-radius:10px;
            font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap;height:42px;">
          🚀 上传并入库
        </button>
      </div>
      <div id="upload-status" style="margin-top:12px;font-size:13px;color:#6b7280;min-height:20px;"></div>
    </div>

    <!-- Toolbar -->
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
      <div style="display:flex;gap:6px;align-items:center;">
        <div id="cat-filter" style="display:flex;gap:4px;">
          ${['全部', ...CATEGORIES].map(c => `<button class="cat-filter-btn" data-cat="${c}"
            style="padding:5px 10px;border:1px solid ${c==='全部'?'#4f46e5':'#e5e7eb'};background:${c==='全部'?'#eef2ff':'#fff'};
              border-radius:16px;font-size:11px;cursor:pointer;color:${c==='全部'?'#4f46e5':'#6b7280'};">${CATEGORY_ICONS[c] || '📋'} ${c}</button>`).join('')}
        </div>
        <button id="refresh-btn"
          style="padding:6px 12px;border:1px solid #d1d5db;background:#fff;border-radius:8px;
            font-size:12px;cursor:pointer;">🔄</button>
      </div>
      <span id="asset-count" style="font-size:13px;color:#6b7280;"></span>
    </div>

    <!-- Asset List -->
    <div id="asset-list" style="display:flex;flex-direction:column;gap:8px;">
      <div style="text-align:center;padding:40px;color:#9ca3af;">正在加载...</div>
    </div>
  `;

  bindEvents(el);
  loadAssets(el);
  return el;
}

let _currentCategory = '全部';

function bindEvents(el: HTMLElement): void {
  // Upload
  el.querySelector('#asset-upload-btn')?.addEventListener('click', () => handleUpload(el));

  // Refresh
  el.querySelector('#refresh-btn')?.addEventListener('click', () => {
    loadAssets(el);
  });

  // Category filter
  el.querySelectorAll('.cat-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      _currentCategory = (btn as HTMLElement).dataset.cat || '全部';
      el.querySelectorAll('.cat-filter-btn').forEach(b => {
        const active = (b as HTMLElement).dataset.cat === _currentCategory;
        (b as HTMLElement).style.borderColor = active ? '#4f46e5' : '#e5e7eb';
        (b as HTMLElement).style.background = active ? '#eef2ff' : '#fff';
        (b as HTMLElement).style.color = active ? '#4f46e5' : '#6b7280';
      });
      loadAssets(el);
    });
  });
}

async function handleUpload(el: HTMLElement): Promise<void> {
  const fileInput = el.querySelector('#asset-file-input') as HTMLInputElement;
  const labelInput = el.querySelector('#asset-label-input') as HTMLInputElement;
  const categorySelect = el.querySelector('#asset-category-select') as HTMLSelectElement;
  const statusEl = el.querySelector('#upload-status') as HTMLElement;
  const btn = el.querySelector('#asset-upload-btn') as HTMLButtonElement;

  const file = fileInput?.files?.[0];
  if (!file) {
    statusEl!.textContent = '⚠️ 请先选择图片文件';
    statusEl!.style.color = '#e74c3c';
    return;
  }

  // Validate extension
  const validExts = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.heic'];
  const ext = '.' + file.name.split('.').pop()?.toLowerCase();
  if (!validExts.includes(ext)) {
    statusEl!.textContent = `⚠️ 不支持的格式 (${ext})，支持: ${validExts.join(', ')}`;
    statusEl!.style.color = '#e74c3c';
    return;
  }

  if (file.size > 30 * 1024 * 1024) {
    statusEl!.textContent = '⚠️ 文件大小超过 30MB 限制';
    statusEl!.style.color = '#e74c3c';
    return;
  }

  // Build form data
  const formData = new FormData();
  formData.append('file', file);

  const label = labelInput?.value?.trim() || '';
  const category = categorySelect?.value || '数字真人';

  if (label) formData.append('label', label);
  formData.append('category', category);

  const url = '/api/v1/assets/upload';

  // Disable button
  btn.disabled = true;
  const isApi = category === API_CATEGORY;
  btn.textContent = '⏳ 上传中...';
  statusEl!.textContent = isApi ? '正在上传并调用 API 入库（约 15-30 秒）...' : '正在上传到本地...';
  statusEl!.style.color = '#6b7280';

  try {
    const res = await fetch(url, { method: 'POST', body: formData });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    statusEl!.innerHTML = `✅ 上传成功！<br>${isApi ? 'Asset ID' : '本地URL'}: <code style="background:#eef2ff;padding:2px 6px;border-radius:4px;font-size:12px;cursor:pointer;" title="点击复制" onclick="navigator.clipboard.writeText('${data.asset_url}');this.textContent='✓ 已复制!';setTimeout(()=>this.textContent='${data.asset_url}',2000)">${data.asset_url}</code>`;
    statusEl!.style.color = '#059669';

    // Reset inputs
    fileInput.value = '';
    labelInput.value = '';

    // Refresh list
    loadAssets(el);
  } catch (e: any) {
    statusEl!.textContent = `❌ 上传失败: ${e.message}`;
    statusEl!.style.color = '#e74c3c';
  } finally {
    btn.disabled = false;
    btn.textContent = '🚀 上传并入库';
  }
}

async function loadAssets(el: HTMLElement): Promise<void> {
  const listEl = el.querySelector('#asset-list') as HTMLElement;
  const countEl = el.querySelector('#asset-count') as HTMLElement;

  try {
    const catParam = _currentCategory && _currentCategory !== '全部' ? `?category=${encodeURIComponent(_currentCategory)}` : '';
    const data = await apiGet<{ total: number; assets: AssetItem[] }>(`/v1/assets${catParam}`);
    countEl.textContent = `共 ${data.total} 个素材`;

    if (data.assets.length === 0) {
      listEl.innerHTML = `
        <div style="text-align:center;padding:60px;color:#9ca3af;">
          <div style="font-size:48px;margin-bottom:12px;">📭</div>
          <div>还没有素材，上传你的第一张数字人照片吧</div>
        </div>`;
      return;
    }

    listEl.innerHTML = data.assets.map(a => renderAssetCard(a)).join('');
    bindAssetCardEvents(el);
  } catch (e: any) {
    listEl.innerHTML = `<div style="text-align:center;padding:40px;color:#e74c3c;">加载失败: ${e.message}</div>`;
  }
}

function renderAssetCard(a: AssetItem): string {
  const statusColor = a.status === 'Active' ? '#059669' : a.status === 'Failed' ? '#e74c3c' : '#d97706';
  const statusBg = a.status === 'Active' ? '#ecfdf5' : a.status === 'Failed' ? '#fef2f2' : '#fffbeb';
  const date = a.created_at ? new Date(a.created_at).toLocaleString('zh-CN') : '';

  const catIcon = CATEGORY_ICONS[a.category] || '📦';
  return `
    <div class="asset-card" data-asset-id="${a.asset_id}" data-asset-url="${a.asset_url}"
      style="display:flex;align-items:center;gap:16px;padding:16px;background:#fff;
        border:1px solid #e5e7eb;border-radius:10px;transition:box-shadow 0.15s;">
      <!-- Preview thumbnail -->
      <div style="width:72px;height:72px;border-radius:8px;overflow:hidden;flex-shrink:0;background:#f3f4f6;
        display:flex;align-items:center;justify-content:center;">
        <img src="${a.public_url}" alt="${a.label}" loading="lazy"
          style="width:100%;height:100%;object-fit:cover;"
          onerror="this.parentElement.textContent='${catIcon}'">
      </div>

      <!-- Info -->
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
          <span style="font-size:15px;font-weight:600;color:#111827;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
            ${escapeHtml(a.label)}
          </span>
          <span style="font-size:10px;padding:2px 8px;border-radius:12px;background:#eef2ff;color:#4f46e5;flex-shrink:0;">
            ${catIcon} ${a.category}
          </span>
          <span style="font-size:11px;padding:2px 8px;border-radius:12px;background:${statusBg};color:${statusColor};flex-shrink:0;">
            ${a.status}
          </span>
        </div>
        <div style="font-size:12px;color:#6b7280;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          <code style="background:#f3f4f6;padding:1px 6px;border-radius:3px;font-size:11px;">${a.asset_url}</code>
        </div>
        <div style="font-size:12px;color:#9ca3af;margin-top:2px;">
          ${a.group_id ? '📁 ' + a.group_id + ' · ' : ''}${a.filename} · ${date}
        </div>
      </div>

      <!-- Actions -->
      <div style="display:flex;gap:6px;flex-shrink:0;">
        <button class="copy-asset-btn" data-url="${a.asset_url}"
          style="padding:6px 12px;border:1px solid #d1d5db;background:#fff;border-radius:6px;
            font-size:12px;cursor:pointer;white-space:nowrap;">📋 复制ID</button>
        <button class="delete-asset-btn" data-id="${a.asset_id}"
          style="padding:6px 12px;border:1px solid #fecaca;background:#fff;color:#dc2626;border-radius:6px;
            font-size:12px;cursor:pointer;white-space:nowrap;">🗑 删除</button>
      </div>
    </div>`;
}

function bindAssetCardEvents(el: HTMLElement): void {
  // Copy asset URL
  el.querySelectorAll('.copy-asset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const url = (btn as HTMLElement).dataset.url || '';
      navigator.clipboard.writeText(url).then(() => {
        const orig = btn.textContent;
        btn.textContent = '✅ 已复制';
        setTimeout(() => { btn.textContent = orig; }, 2000);
      }).catch(() => {
        btn.textContent = '❌ 失败';
        setTimeout(() => { (btn as HTMLElement).textContent = '📋 复制ID'; }, 2000);
      });
    });
  });

  // Delete asset
  el.querySelectorAll('.delete-asset-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const assetId = (btn as HTMLElement).dataset.id || '';
      const card = (btn as HTMLElement).closest('.asset-card');
      if (!confirm(`确认删除素材 ${assetId}？\n\n此操作将同时从 icover.ai 素材库和本地记录中移除。`)) return;

      try {
        await apiDelete(`/v1/assets/${assetId}`);
        card?.remove();
        // Update count
        const remaining = el.querySelectorAll('.asset-card').length;
        const countEl = el.querySelector('#asset-count') as HTMLElement;
        if (countEl) countEl.textContent = `共 ${remaining} 个素材`;

        if (remaining === 0) {
          const listEl = el.querySelector('#asset-list') as HTMLElement;
          listEl.innerHTML = `
            <div style="text-align:center;padding:60px;color:#9ca3af;">
              <div style="font-size:48px;margin-bottom:12px;">📭</div>
              <div>还没有素材，上传你的第一张数字人照片吧</div>
            </div>`;
        }
      } catch (e: any) {
        alert(`删除失败: ${e.message}`);
      }
    });
  });
}

function escapeHtml(s: string): string {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

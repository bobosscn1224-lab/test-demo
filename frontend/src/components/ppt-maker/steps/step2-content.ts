/** Step 2: Content upload — files, text paste, and Feishu integration. */

import { apiPost, apiPut } from '../../../services/api';
import { state } from '../state';
import { esc, toast, showLoading } from '../utils';
import { navigateTo, reRender } from '../navigation';

export function renderStep2(el: HTMLElement): void {
  el.className = 'max-w-3xl mx-auto w-full p-6 relative';

  // Show previously saved content if any
  const savedFiles = state.projectDetail?.content_files || [];
  const hasSavedContent = !!state.pastedText || savedFiles.length > 0;

  const html = `
    <h2 class="text-xl font-bold text-gray-800 mb-1">添加素材</h2>
    <p class="text-sm text-gray-500 mb-6">上传文件、粘贴文本或引用飞书知识库，为 PPT 提供内容来源</p>

    ${hasSavedContent ? `
    <div class="bg-green-50 border border-green-200 rounded-xl p-4 mb-4" id="ppt-saved-content">
      <p class="text-sm font-semibold text-green-800 mb-2">已保存的素材</p>
      ${savedFiles.length > 0 ? `
      <div class="space-y-1 mb-2" id="ppt-saved-files">
        ${savedFiles.map((f: any, i: number) => {
          const name = typeof f === 'string' ? f.split('/').pop() || f.split('\\').pop() || f : (f.name || f.filename || f.path || String(f));
          return `<div class="flex items-center justify-between text-xs text-green-700 py-1">
            <span> ${esc(String(name))}</span>
            <button class="ppt-del-saved text-red-400 hover:text-red-600 ml-2" data-idx="${i}">删除</button>
          </div>`;
        }).join('')}
      </div>` : ''}
      ${state.pastedText ? `
      <div class="flex items-center justify-between text-xs text-green-700 mb-1">
        <span> ${state.pastedText.length} 字符文本</span>
        <button class="ppt-del-text text-red-400 hover:text-red-600 ml-2">删除文本</button>
      </div>` : ''}
      <p class="text-xs text-green-600 mt-2">可以继续追加素材，提交后将与已有内容合并</p>
    </div>
    ` : ''}

    <!-- Tabs -->
    <div class="flex gap-1 mb-4 bg-gray-100 rounded-xl p-1">
      <button class="ppt-tab-btn flex-1 py-2 px-2 rounded-lg text-xs font-medium transition-all ${state.activeContentTab === 'upload' ? 'bg-white text-gray-800 shadow-sm' : 'bg-transparent text-gray-500'}" data-tab="upload">📁 文件</button>
      <button class="ppt-tab-btn flex-1 py-2 px-2 rounded-lg text-xs font-medium transition-all ${state.activeContentTab === 'text' ? 'bg-white text-gray-800 shadow-sm' : 'bg-transparent text-gray-500'}" data-tab="text">📝 文本</button>
      <button class="ppt-tab-btn flex-1 py-2 px-2 rounded-lg text-xs font-medium transition-all ${state.activeContentTab === 'feishu' ? 'bg-white text-gray-800 shadow-sm' : 'bg-transparent text-gray-500'}" data-tab="feishu">🪶 飞书文档</button>
      <button class="ppt-tab-btn flex-1 py-2 px-2 rounded-lg text-xs font-medium transition-all ${state.activeContentTab === 'knowledge' ? 'bg-white text-gray-800 shadow-sm' : 'bg-transparent text-gray-500'}" data-tab="knowledge">📚 知识库</button>
    </div>

    <!-- Tab: Upload -->
    <div id="ppt-tab-upload" class="ppt-tab-content" style="display:block">
      <div id="ppt-upload-zone" class="border-2 border-dashed border-gray-300 rounded-2xl p-10 text-center cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/50 transition-colors">
        <div class="text-5xl mb-3"></div>
        <p class="text-gray-600 font-medium mb-1">点击选择文件 或 拖拽到此处</p>
        <p class="text-sm text-gray-400">支持 PDF / DOC / DOCX / MD / TXT / PNG / JPG</p>
        <input type="file" id="ppt-file-input" multiple accept=".pdf,.doc,.docx,.md,.txt,.png,.jpg,.jpeg" class="hidden">
      </div>
      <div id="ppt-file-list" class="mt-4 space-y-2 hidden"></div>
    </div>

    <!-- Tab: Text -->
    <div id="ppt-tab-text" class="ppt-tab-content" style="display:none">
      <textarea id="ppt-paste-text" rows="12" placeholder="在此粘贴文本内容...&#10;&#10;支持直接粘贴会议纪要、文档内容、数据表格等文本信息"
        class="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all resize-none">${esc(state.pastedText)}</textarea>
      <p class="text-xs text-gray-400 mt-1">已输入 <span id="ppt-text-count">0</span> 字符</p>
    </div>

    <!-- Tab: Feishu Docs -->
    <div id="ppt-tab-feishu" class="ppt-tab-content" style="display:none">
      <div class="space-y-4">
        <p class="text-sm text-gray-600">输入飞书文档 URL，查询预览后可导入到知识库作为 PPT 素材。</p>

        <!-- URL input + query -->
        <div class="flex gap-2">
          <input type="text" id="ppt-feishu-url-input" class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm" placeholder="输入飞书文档/Wiki/妙记 URL...">
          <button id="ppt-feishu-query-btn" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors">查询预览</button>
        </div>

        <!-- Preview panel -->
        <div id="ppt-feishu-preview" class="hidden bg-gray-50 border border-gray-200 rounded-xl p-4">
          <div class="flex items-center justify-between mb-2">
            <span id="ppt-feishu-preview-title" class="text-sm font-semibold text-gray-700"></span>
            <span id="ppt-feishu-preview-status" class="text-xs"></span>
          </div>
          <pre id="ppt-feishu-preview-text" class="text-xs text-gray-600 max-h-40 overflow-y-auto whitespace-pre-wrap bg-white border rounded-lg p-3"></pre>
          <button id="ppt-feishu-import-btn" class="mt-3 px-4 py-1.5 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 transition-colors">导入到知识库</button>
        </div>

        <!-- Imported docs list -->
        <div id="ppt-feishu-imported" class="space-y-1">
          ${(state.importedFeishuDocs || []).map((d: any) => `
            <div class="flex items-center justify-between text-xs bg-green-50 border border-green-200 rounded-lg px-3 py-2">
              <span class="text-green-800 truncate flex-1">✅ ${esc(d.title || d.url)}</span>
              <button class="ppt-del-feishu text-red-400 hover:text-red-600 ml-2 flex-shrink-0" data-idx="${(state.importedFeishuDocs || []).indexOf(d)}">删除</button>
            </div>
          `).join('')}
        </div>
      </div>
    </div>

    <!-- Tab: Knowledge Base Settings -->
    <div id="ppt-tab-knowledge" class="ppt-tab-content" style="display:none">
      <div class="space-y-4">
        <div class="bg-indigo-50 border border-indigo-200 rounded-xl p-5">
          <div class="flex items-center justify-between mb-3">
            <div>
              <p class="text-sm font-semibold text-indigo-800">📚 本地知识库</p>
              <p class="text-xs text-indigo-600 mt-0.5">生成大纲时自动搜索以下知识库目录中的文档</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" id="ppt-kb-toggle" ${state.useKnowledgeBase !== false ? 'checked' : ''} class="sr-only peer">
              <span class="w-9 h-5 bg-gray-300 peer-checked:bg-indigo-500 rounded-full peer transition-colors"></span>
              <span class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-4"></span>
            </label>
          </div>
          <div id="ppt-kb-dirs" class="space-y-1 mb-2">
            ${(state.knowledgeBaseDirs || []).map((d: string) => `
              <div class="flex items-center gap-2 text-xs text-indigo-700">
                <span>📁</span><span class="truncate">${esc(d)}</span>
              </div>
            `).join('')}
          </div>
          <p class="text-xs text-indigo-500">${state.useKnowledgeBase !== false ? '已启用 · 大纲生成时会引用以上知识库内容' : '已禁用 · 大纲生成仅使用你提供的素材'}</p>
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div class="flex items-center gap-3 mt-6 pt-4 border-t border-gray-200">
      <button id="ppt-step2-back" class="px-4 py-2 border border-gray-300 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors"> 上一步</button>
      <button id="ppt-step2-continue" class="px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors">提交素材，继续 </button>
    </div>

  `;

  el.innerHTML = html;
  bindStep2(el);
}

function bindStep2(el: HTMLElement): void {
  let activeTab = 'upload';

  // Knowledge base toggle
  const kbToggle = el.querySelector('#ppt-kb-toggle') as HTMLInputElement;
  kbToggle?.addEventListener('change', () => {
    state.useKnowledgeBase = kbToggle.checked;
    reRender();
  });

  // Tab switching — show upload tab immediately, persist active tab in state
  const showTab = (tab: string) => {
    state.activeContentTab = tab;
    ['upload','text','feishu','knowledge'].forEach(t => {
      const div = el.querySelector(`#ppt-tab-${t}`) as HTMLElement;
      if (div) div.style.display = t === tab ? 'block' : 'none';
    });
  };
  showTab(state.activeContentTab || 'upload');

  el.querySelectorAll('.ppt-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      showTab((btn as HTMLElement).dataset.tab || 'upload');
    });
  });

  // File upload
  const zone = el.querySelector('#ppt-upload-zone')!;
  const input = el.querySelector('#ppt-file-input') as HTMLInputElement;
  const fileList = el.querySelector('#ppt-file-list')!;

  function updateFileUI(): void {
    if (state.contentFiles.length === 0) {
      fileList.classList.add('hidden');
      fileList.innerHTML = '';
    } else {
      fileList.classList.remove('hidden');
      fileList.innerHTML = `
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-semibold text-gray-700">已选择 ${state.contentFiles.length} 个文件</span>
          <button id="ppt-files-clear" class="text-xs text-red-500 hover:text-red-700">清空</button>
        </div>
        ${state.contentFiles.map((f, i) => `
          <div class="flex items-center gap-3 p-2.5 bg-gray-50 rounded-lg text-sm">
            <span class="text-lg"></span>
            <span class="flex-1 text-gray-700 truncate">${esc(f.name)}</span>
            <span class="text-xs text-gray-400">${(f.size / 1024).toFixed(0)} KB</span>
            <button class="ppt-file-remove text-red-400 hover:text-red-600" data-idx="${i}">&times;</button>
          </div>
        `).join('')}
      `;
      el.querySelector('#ppt-files-clear')?.addEventListener('click', () => { state.contentFiles = []; updateFileUI(); });
      el.querySelectorAll('.ppt-file-remove').forEach(b => {
        b.addEventListener('click', () => {
          const idx = parseInt((b as HTMLElement).dataset.idx!);
          state.contentFiles.splice(idx, 1);
          updateFileUI();
        });
      });
    }
  }

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('border-indigo-400', 'bg-indigo-50'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('border-indigo-400', 'bg-indigo-50'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('border-indigo-400', 'bg-indigo-50');
    const dt = (e as DragEvent).dataTransfer;
    if (dt?.files) {
      state.contentFiles.push(...Array.from(dt.files) as File[]);
      updateFileUI();
    }
  });
  input.addEventListener('change', () => {
    if (input.files) { state.contentFiles.push(...Array.from(input.files)); input.value = ''; updateFileUI(); }
  });

  // Text area
  const textArea = el.querySelector('#ppt-paste-text') as HTMLTextAreaElement;
  const textCount = el.querySelector('#ppt-text-count');
  if (textArea && textCount) {
    textArea.addEventListener('input', () => {
      state.pastedText = textArea.value;
      textCount.textContent = String(textArea.value.length);
    });
    textCount.textContent = String(textArea.value.length);
  }

  // Delete saved content: delete a saved file
  el.querySelectorAll('.ppt-del-saved').forEach(btn => {
    btn.addEventListener('click', async () => {
      const idx = parseInt((btn as HTMLElement).dataset.idx!);
      if (!state.projectDetail || !state.projectDetail.content_files) return;
      state.projectDetail.content_files.splice(idx, 1);
      try {
        await apiPut(`/v1/ppt-maker/projects/${state.projectId}/content/`, {
          files: state.projectDetail.content_files,
          text: state.projectDetail.content_text || '',
        });
        toast('文件已删除');
        renderStep2(el);
      } catch (e: any) {
        toast('删除失败：' + (e.message || e), 'error');
      }
    });
  });

  // Delete saved content: clear all text
  el.querySelector('.ppt-del-text')?.addEventListener('click', async () => {
    state.pastedText = '';
    if (state.projectDetail) state.projectDetail.content_text = '';
    try {
      await apiPut(`/v1/ppt-maker/projects/${state.projectId}/content/`, {
        files: state.projectDetail?.content_files || [],
        text: '',
      });
      toast('文本已删除');
      renderStep2(el);
    } catch (e: any) {
      toast('删除失败：' + (e.message || e), 'error');
    }
  });

  // Feishu: query preview
  let feishuPreviewUrl = '';
  el.querySelector('#ppt-feishu-query-btn')?.addEventListener('click', async () => {
    const urlInput = el.querySelector('#ppt-feishu-url-input') as HTMLInputElement;
    const url = urlInput?.value?.trim();
    if (!url) { toast('请输入飞书文档 URL', 'error'); return; }
    feishuPreviewUrl = url;
    const previewPanel = el.querySelector('#ppt-feishu-preview') as HTMLElement;
    const titleEl = el.querySelector('#ppt-feishu-preview-title')!;
    const statusEl = el.querySelector('#ppt-feishu-preview-status')!;
    const textEl = el.querySelector('#ppt-feishu-preview-text')!;
    const importBtn = el.querySelector('#ppt-feishu-import-btn') as HTMLButtonElement;

    previewPanel.classList.remove('hidden');
    titleEl.textContent = '查询中...';
    statusEl.textContent = '';
    textEl.textContent = '';
    importBtn.classList.add('hidden');

    try {
      const r = await fetch('/api/knowledge/feishu/doc-preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url, name: ''}),
      });
      if (!r.ok) throw new Error('查询失败');
      const data = await r.json();
      titleEl.textContent = data.name || '飞书文档';
      statusEl.innerHTML = `<span class="text-green-600">${data.content_length} 字${data.truncated ? '（内容已截断）' : ''}</span>`;
      textEl.textContent = data.preview || '';
      importBtn.classList.remove('hidden');
    } catch (e: any) {
      titleEl.textContent = '查询失败';
      statusEl.textContent = e.message || '请检查 URL 是否正确';
    }
  });

  // Feishu: import
  el.querySelector('#ppt-feishu-import-btn')?.addEventListener('click', async () => {
    if (!feishuPreviewUrl) return;
    const importBtn = el.querySelector('#ppt-feishu-import-btn') as HTMLButtonElement;
    importBtn.disabled = true;
    importBtn.textContent = '导入中...';
    const done = showLoading(el, '正在导入飞书文档…');
    try {
      const r = await fetch('/api/knowledge/feishu/direct-import', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: feishuPreviewUrl}),
      });
      const data = await r.json();
      done();
      if (data.ok) {
        if (!state.importedFeishuDocs) state.importedFeishuDocs = [];
        state.importedFeishuDocs.push({url: feishuPreviewUrl, title: data.title || '飞书文档'});
        toast(`已导入：${data.title || '文档'}（${data.chunks || 0} 个分块）`);
        importBtn.classList.add('hidden');
        reRender();
      } else {
        toast('导入失败', 'error');
        importBtn.disabled = false;
        importBtn.textContent = '重试导入';
      }
    } catch (e: any) {
      done();
      toast('导入失败：' + (e.message || e), 'error');
      importBtn.disabled = false;
      importBtn.textContent = '重试导入';
    }
  });

  // Feishu: delete imported doc
  el.querySelectorAll('.ppt-del-feishu').forEach(b => {
    b.addEventListener('click', () => {
      const idx = parseInt((b as HTMLElement).dataset.idx!);
      state.importedFeishuDocs?.splice(idx, 1);
      reRender();
    });
  });

  // Load knowledge base dirs on first visit
  if (!state.knowledgeBaseDirs?.length) {
    fetch('/api/knowledge/config').then(r => r.json()).then(d => {
      state.knowledgeBaseDirs = d.watch_dirs || [];
    }).catch(() => {});
  }

  // Back
  el.querySelector('#ppt-step2-back')?.addEventListener('click', () => { navigateTo(1); });

  // Continue
  el.querySelector('#ppt-step2-continue')?.addEventListener('click', async () => {
    // Validate: check saved data first (JSON persisted), then current form input
    const hasSaved = (state.projectDetail?.content_files?.length || 0) > 0
                  || !!(state.projectDetail?.content_text);
    const hasNew = state.contentFiles.length > 0 || !!state.pastedText.trim();
    if (!hasSaved && !hasNew) {
      toast('请至少上传一个文件或粘贴一段文本', 'error');
      return;
    }
    const btnEl = el.querySelector('#ppt-step2-continue') as HTMLButtonElement;
    btnEl.disabled = true;
    btnEl.textContent = '提交中...';
    const done = showLoading(el, '正在提交素材…');
    try {
      // Upload new files, preserving original filenames
      const uploadedPaths: {path: string, name: string}[] = [];
      for (const f of state.contentFiles) {
        const fd = new FormData();
        fd.append('file', f);
        const r = await fetch('/api/upload', { method: 'POST', body: fd });
        if (!r.ok) throw new Error('文件上传失败');
        const data = await r.json();
        uploadedPaths.push({path: data.path || '', name: data.filename || f.name});
      }
      await apiPost(`/v1/ppt-maker/projects/${state.projectId}/content/`, {
        files: uploadedPaths,
        text: state.pastedText,
      });
      toast('素材已提交');
      done();
      navigateTo(3);
    } catch (e: any) {
      done();
      toast('提交失败：' + (e.message || e), 'error');
      btnEl.disabled = false;
      btnEl.textContent = '提交素材，继续 ';
    }
  });
}

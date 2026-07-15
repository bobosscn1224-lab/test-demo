import { apiPost } from '../services/api';

export function renderBatchPptxPage(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'flex flex-col h-full bg-white';

  el.innerHTML = `
    <div class="flex-1 overflow-y-auto p-6">
      <div class="max-w-4xl mx-auto">
        <h1 class="text-2xl font-bold text-gray-800 mb-2">图片批量转PPTX</h1>
        <p class="text-sm text-gray-500 mb-6">上传多张PPT视觉稿，按顺序逐页转化，最后合成一个PPTX文件导出</p>

        <div id="batch-upload-zone" class="border-2 border-dashed border-gray-300 rounded-2xl p-10 text-center cursor-pointer hover:border-green-400 hover:bg-green-50 transition-colors mb-6">
          <div class="text-5xl mb-3">📁</div>
          <p class="text-gray-600 font-medium mb-1">点击选择图片 或 拖拽到此处</p>
          <p class="text-sm text-gray-400">支持 PNG / JPG / JPEG，可一次选择多张</p>
          <input type="file" id="batch-file-input" multiple accept="image/png,image/jpeg,image/jpg" class="hidden">
        </div>

        <div id="batch-file-list" class="mb-6 hidden">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-lg font-semibold text-gray-700">已选择 <span id="batch-file-count">0</span> 张图片</h2>
            <button id="batch-clear-btn" class="text-sm text-red-500 hover:text-red-700">清空</button>
          </div>
          <div id="batch-file-items" class="space-y-1 max-h-80 overflow-y-auto"></div>
          <p class="text-xs text-gray-400 mt-2">拖拽文件可调整顺序，PPT 页码按从上到下排列</p>
        </div>

        <button id="batch-convert-btn" disabled
          class="w-full py-3 rounded-xl text-white font-medium transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed bg-green-600 hover:bg-green-700">
          开始转换
        </button>

        <div id="batch-progress" class="mt-6 hidden">
          <div class="flex items-center justify-between mb-2">
            <span id="batch-progress-text" class="text-gray-600 text-sm"></span>
            <span id="batch-progress-pct" class="text-gray-500 text-xs">0%</span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
            <div id="batch-progress-bar" class="bg-green-500 h-3 rounded-full transition-all duration-500" style="width:0%"></div>
          </div>
          <div id="batch-progress-detail" class="mt-3 space-y-1 max-h-48 overflow-y-auto"></div>
        </div>

        <div id="batch-result" class="mt-6 hidden">
          <div id="batch-result-content"></div>
        </div>
      </div>
    </div>
  `;

  bindBatchPage(el);
  return el;
}

function bindBatchPage(el: HTMLElement): void {
  const zone = el.querySelector('#batch-upload-zone')!;
  const input = el.querySelector('#batch-file-input') as HTMLInputElement;
  const fileList = el.querySelector('#batch-file-list')!;
  const fileItems = el.querySelector('#batch-file-items')!;
  const fileCount = el.querySelector('#batch-file-count')!;
  const convertBtn = el.querySelector('#batch-convert-btn') as HTMLButtonElement;
  const progress = el.querySelector('#batch-progress')!;
  const progressText = el.querySelector('#batch-progress-text')!;
  const progressPct = el.querySelector('#batch-progress-pct')!;
  const progressBar = el.querySelector('#batch-progress-bar')!;
  const progressDetail = el.querySelector('#batch-progress-detail')!;
  const result = el.querySelector('#batch-result')!;
  const resultContent = el.querySelector('#batch-result-content')!;
  const clearBtn = el.querySelector('#batch-clear-btn')!;

  let selectedFiles: File[] = [];
  let dragIdx: number | null = null;

  function updateUI(): void {
    const count = selectedFiles.length;
    fileList.classList.toggle('hidden', count === 0);
    fileCount.textContent = String(count);
    convertBtn.disabled = count === 0;
    fileItems.innerHTML = selectedFiles.map((f, i) =>
      `<div class="file-row flex items-center gap-3 p-2 bg-gray-50 rounded-lg cursor-grab hover:bg-gray-100 transition-colors"
           draggable="true" data-file-idx="${i}">
        <span class="drag-handle text-gray-300 text-sm select-none">⠿</span>
        <span class="text-gray-400 w-5 text-right text-xs">${i + 1}</span>
        <span class="flex-1 text-sm text-gray-700 truncate">${f.name}</span>
        <span class="text-xs text-gray-400">${(f.size / 1024).toFixed(0)} KB</span>
        <button data-idx="${i}" class="remove-btn text-red-400 hover:text-red-600 text-lg leading-none">&times;</button>
      </div>`
    ).join('');

    fileItems.querySelectorAll('.file-row').forEach(row => {
      const r = row as HTMLElement;
      r.addEventListener('dragstart', () => { dragIdx = parseInt(r.dataset.fileIdx!); r.classList.add('opacity-50'); });
      r.addEventListener('dragend', () => { dragIdx = null; r.classList.remove('opacity-50'); updateUI(); });
      r.addEventListener('dragover', (e) => { e.preventDefault(); r.classList.add('border-t-2', 'border-green-400'); });
      r.addEventListener('dragleave', () => { r.classList.remove('border-t-2', 'border-green-400'); });
      r.addEventListener('drop', (e) => {
        e.preventDefault(); r.classList.remove('border-t-2', 'border-green-400');
        const to = parseInt(r.dataset.fileIdx!);
        if (dragIdx !== null && dragIdx !== to) { const [m] = selectedFiles.splice(dragIdx, 1); selectedFiles.splice(to, 0, m); }
      });
    });
    fileItems.querySelectorAll('.remove-btn').forEach(btn => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); selectedFiles.splice(parseInt((btn as HTMLElement).dataset.idx!), 1); updateUI(); });
    });
  }

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('border-green-400', 'bg-green-50'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('border-green-400', 'bg-green-50'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault(); zone.classList.remove('border-green-400', 'bg-green-50');
    if (e.dataTransfer?.files) { selectedFiles.push(...Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'))); updateUI(); }
  });
  input.addEventListener('change', () => {
    if (input.files) { selectedFiles.push(...Array.from(input.files).filter(f => f.type.startsWith('image/'))); input.value = ''; updateUI(); }
  });
  clearBtn.addEventListener('click', () => { selectedFiles = []; updateUI(); result.classList.add('hidden'); progress.classList.add('hidden'); });

  convertBtn.addEventListener('click', async () => {
    if (selectedFiles.length === 0) return;
    convertBtn.disabled = true;
    progress.classList.remove('hidden');
    result.classList.add('hidden');
    progressDetail.innerHTML = '';
    const total = selectedFiles.length;

    try {
      // Upload
      progressText.textContent = `上传中 0/${total}`;
      progressPct.textContent = '0%';
      progressBar.style.width = '0%';
      const imagePaths: string[] = [];
      for (let i = 0; i < total; i++) {
        const fd = new FormData(); fd.append('file', selectedFiles[i]);
        const r = await fetch('/api/upload', { method: 'POST', body: fd });
        if (!r.ok) throw new Error('Upload failed');
        imagePaths.push((await r.json()).path || '');
        progressText.textContent = `上传中 ${i + 1}/${total}`;
        progressPct.textContent = `${Math.round((i + 1) / total * 10)}%`;
        progressBar.style.width = `${Math.round((i + 1) / total * 10)}%`;
      }

      // Start async job via new Feature API
      progressText.textContent = `开始转换...`;
      const sr = await fetch('/api/v1/pptx/convert-async', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ images: imagePaths }),
      });
      const { job_id } = await sr.json();
      if (!job_id) throw new Error('Job creation failed');

      // Poll via new Feature API
      while (true) {
        await new Promise(r => setTimeout(r, 1500));
        const jr = await fetch(`/api/v1/pptx/jobs/${job_id}`);
        const job = await jr.json();
        const pct = 10 + Math.round((job.progress || 0) * 0.85);
        progressText.textContent = `${job.status === 'completed' ? '完成' : job.status === 'merging' ? '合并中' : '转化中'} ${job.current}/${job.total}`;
        progressPct.textContent = `${pct}%`;
        progressBar.style.width = `${pct}%`;
        progressDetail.innerHTML = (job.results || []).map((r: any) =>
          `<div class="flex items-center gap-2 text-xs"><span class="text-green-500">✅</span> 第${r.page}页 · ${r.file} · ${r.text_items}字</div>`
        ).join('') + (job.errors || []).map((e: any) =>
          `<div class="flex items-center gap-2 text-xs"><span class="text-red-500">❌</span> 第${e.page}页 · ${e.error}</div>`
        ).join('');

        if (job.status === 'completed') {
          progressText.textContent = `完成 ${total}/${total}`;
          progressPct.textContent = '100%';
          progressBar.style.width = '100%';
          await new Promise(r => setTimeout(r, 600));
          progress.classList.add('hidden');
          resultContent.innerHTML = `
            <div class="p-4 bg-green-50 rounded-xl">
              <h3 class="font-bold text-green-800 mb-2">转换完成！${total} 页全部成功</h3>
              <a href="${window.location.origin}/api/skills/download/${job.combined_pptx_filename}"
                 download="${job.combined_pptx_filename}"
                 class="inline-block px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium">下载完整 PPTX</a>
            </div>`;
          result.classList.remove('hidden');
          break;
        }
        if (job.status === 'failed') {
          progress.classList.add('hidden');
          resultContent.innerHTML = `<div class="p-4 bg-red-50 text-red-700 rounded-xl">转换失败：${(job.errors||[]).map((e:any)=>e.error).join('; ')}</div>`;
          result.classList.remove('hidden');
          break;
        }
      }
    } catch (err: any) {
      progress.classList.add('hidden');
      resultContent.innerHTML = `<div class="p-4 bg-red-50 text-red-700 rounded-xl">${err.message || err}</div>`;
      result.classList.remove('hidden');
    } finally {
      convertBtn.disabled = false;
    }
  });
}

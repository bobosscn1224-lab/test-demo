/** Video Generation Page */

import { apiGet } from '../services/api';

interface AssetItem { asset_id:string;asset_url:string;label:string;category:string;public_url:string;status:string;usage?:string; }

const USAGE_OPTIONS = [
  {value:'character',label:'人物角色',icon:'🧑'},
  {value:'scene',label:'场景背景',icon:'🏞'},
  {value:'prop',label:'道具',icon:'🎯'},
  {value:'style',label:'风格参考',icon:'🎨'},
];
const DEFAULT_USAGE:Record<string,string> = {'数字真人':'character','场景':'scene','道具':'prop','其他':'style'};

const CAT_ICON: Record<string,string> = {'数字真人':'🧑','场景':'🏞','道具':'🎯','其他':'📦','全部':'📋'};
const RATIOS: Record<string,string> = {'16:9':'16:9 横屏','9:16':'9:16 竖屏','1:1':'1:1','4:3':'4:3','3:4':'3:4','21:9':'21:9','adaptive':'自适应'};

let _mode='reference', _selRefs:AssetItem[]=[], _first:AssetItem|null=null, _last:AssetItem|null=null;
let _modalCat='全部', _modalAssets:AssetItem[]=[], _optimized='';
let _pollTimer:ReturnType<typeof setInterval>|null=null;

function h(tag:string,css:string,children?:(Node|string)[],attrs?:Record<string,string>):HTMLElement{
  const el=document.createElement(tag);el.style.cssText=css;
  if(attrs)Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));
  if(children)children.forEach(c=>{if(typeof c==='string'){if(/<[a-zA-Z][^>]*>/.test(c))el.insertAdjacentHTML('beforeend',c);else el.append(document.createTextNode(c));}else el.append(c);});
  return el;
}

export function renderVideoGenPage(): HTMLElement {
  const root = document.createElement('div');
  root.style.cssText = 'padding:24px;height:100%;overflow-y:auto;display:flex;flex-direction:column;';

  root.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
      <div>
        <h2 style="font-size:20px;font-weight:700;color:#111827;margin:0;">🎬 短视频生成</h2>
        <p style="color:#6b7280;font-size:13px;margin:4px 0 0;">Seedance 2.0 · 支持数字人素材引用 · 文生视频 / 图生视频</p>
      </div>
      <div style="display:flex;gap:8px;"><button id="vg-pro-mode-btn" style="padding:8px 16px;border:1px solid #8b5cf6;background:#faf5ff;color:#7c3aed;border-radius:8px;font-size:13px;cursor:pointer;font-weight:600;">🎥 专业模式</button><button id="vg-refresh-btn" style="padding:8px 16px;border:1px solid #d1d5db;background:#fff;border-radius:8px;font-size:13px;cursor:pointer;">🔄 刷新</button></div>
    </div>

    <div style="display:flex;gap:20px;flex:1;min-height:0;">
      <!-- LEFT -->
      <div style="width:420px;flex-shrink:0;display:flex;flex-direction:column;gap:16px;overflow-y:auto;">

        <!-- Mode -->
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
          <h3 style="font-size:14px;font-weight:600;color:#374151;margin:0 0 10px;">🎯 生成模式</h3>
          <div id="mode-selector" style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
            <button class="mode-btn" data-mode="reference" style="padding:8px;border:2px solid #4f46e5;background:#eef2ff;border-radius:8px;cursor:pointer;text-align:left;font-size:12px;color:#4f46e5;font-weight:600;">🖼 参考图生视频</button>
            <button class="mode-btn" data-mode="first_frame" style="padding:8px;border:2px solid #e5e7eb;background:#fff;border-radius:8px;cursor:pointer;text-align:left;font-size:12px;color:#374151;">▶ 首帧生成</button>
            <button class="mode-btn" data-mode="first_last_frame" style="padding:8px;border:2px solid #e5e7eb;background:#fff;border-radius:8px;cursor:pointer;text-align:left;font-size:12px;color:#374151;">⏯ 首尾帧生成</button>
            <button class="mode-btn" data-mode="text" style="padding:8px;border:2px solid #e5e7eb;background:#fff;border-radius:8px;cursor:pointer;text-align:left;font-size:12px;color:#374151;">📝 纯文本生成</button>
          </div>
        </div>

        <!-- Model -->
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
          <h3 style="font-size:14px;font-weight:600;color:#374151;margin:0 0 10px;">🤖 模型选择</h3>
          <div style="display:flex;gap:8px;">
            <label class="model-opt" data-model="fast" style="flex:1;display:flex;flex-direction:column;align-items:center;padding:12px 8px;border:2px solid #4f46e5;border-radius:10px;cursor:pointer;background:#eef2ff;">
              <span style="font-size:18px;">⚡</span><span style="font-size:13px;font-weight:600;color:#4f46e5;">Fast</span><span style="font-size:10px;color:#6b7280;">最大 720p</span></label>
            <label class="model-opt" data-model="standard" style="flex:1;display:flex;flex-direction:column;align-items:center;padding:12px 8px;border:2px solid #e5e7eb;border-radius:10px;cursor:pointer;background:#fff;">
              <span style="font-size:18px;">🎯</span><span style="font-size:13px;font-weight:600;color:#374151;">Standard</span><span style="font-size:10px;color:#6b7280;">最大 1080p</span></label>
            <label class="model-opt" data-model="mini" style="flex:1;display:flex;flex-direction:column;align-items:center;padding:12px 8px;border:2px solid #e5e7eb;border-radius:10px;cursor:pointer;background:#fff;">
              <span style="font-size:18px;">💨</span><span style="font-size:13px;font-weight:600;color:#374151;">Mini</span><span style="font-size:10px;color:#6b7280;">最大 720p</span></label>
          </div>
        </div>

        <!-- Assets -->
        <div id="asset-panel" style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
          <h3 style="font-size:14px;font-weight:600;color:#374151;margin:0 0 4px;">📎 参考素材（最多9张）</h3>
          <p style="font-size:12px;color:#9ca3af;margin:0 0 10px;">选择已入库的素材作为视频参考</p>
          <button id="pick-assets-btn" style="width:100%;padding:10px;border:2px dashed #c7d2fe;background:#eef2ff;color:#4f46e5;border-radius:8px;cursor:pointer;font-size:13px;">📂 从素材库选择素材</button>
          <div id="selected-chips" style="display:flex;flex-wrap:wrap;gap:4px;margin-top:8px;min-height:24px;"></div>
          <div id="frame-selectors" style="display:none;margin-top:8px;padding-top:8px;border-top:1px solid #e5e7eb;">
            <div style="display:flex;gap:8px;">
              <div id="first-frame-picker" style="flex:1;padding:8px;border:1px dashed #d1d5db;border-radius:8px;text-align:center;cursor:pointer;font-size:11px;color:#9ca3af;">▶ 点击选择首帧</div>
              <div id="last-frame-picker" style="flex:1;padding:8px;border:1px dashed #d1d5db;border-radius:8px;text-align:center;cursor:pointer;font-size:11px;color:#9ca3af;display:none;">⏸ 点击选择尾帧</div>
            </div>
          </div>
        </div>

        <!-- Prompt -->
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <h3 style="font-size:14px;font-weight:600;color:#374151;margin:0;">✏️ 提示词</h3>
            <button id="optimize-btn" style="padding:5px 12px;border:1px solid #8b5cf6;background:#faf5ff;color:#7c3aed;border-radius:16px;font-size:12px;cursor:pointer;">✨ AI 优化</button>
            <button id="template-btn" style="padding:5px 12px;border:1px solid #d1d5db;background:#fff;border-radius:16px;font-size:12px;cursor:pointer;color:#6b7280;">📋 模板</button>
          </div>
          <textarea id="vg-prompt" rows="4" maxlength="2000" placeholder="描述你想要的视频内容，例如：图片1中的人物正面微笑，镜头缓慢推近，自然光..." style="width:100%;padding:10px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;resize:vertical;font-family:inherit;line-height:1.5;"></textarea>
          <span id="prompt-count" style="font-size:11px;color:#9ca3af;">0/2000</span>
        </div>

        <!-- Optimized -->
        <div id="optimized-panel" style="display:none;background:#faf5ff;border:2px solid #c4b5fd;border-radius:10px;padding:14px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <h3 style="font-size:13px;font-weight:600;color:#7c3aed;margin:0;">✨ AI 优化结果</h3>
            <span id="optimize-changes" style="font-size:11px;color:#6b7280;"></span></div>
          <div id="optimized-text" style="font-size:12px;color:#374151;line-height:1.6;padding:8px;background:#fff;border-radius:8px;border:1px solid #e5e7eb;max-height:100px;overflow-y:auto;"></div>
          <div style="display:flex;gap:8px;margin-top:10px;">
            <button id="accept-opt-btn" style="flex:1;padding:8px;background:#7c3aed;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;">✅ 采纳</button>
            <button id="reject-opt-btn" style="padding:8px 16px;border:1px solid #d1d5db;background:#fff;border-radius:8px;font-size:13px;cursor:pointer;">保留原文</button>
          </div>
        </div>

        <!-- Settings -->
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
          <h3 style="font-size:14px;font-weight:600;color:#374151;margin:0 0 10px;">⚙️ 参数设置</h3>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div><label style="font-size:12px;font-weight:600;color:#374151;">分辨率</label>
              <select id="vg-resolution" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;margin-top:4px;"><option value="480p">480p</option><option value="720p" selected>720p</option><option value="1080p">1080p</option></select></div>
            <div><label style="font-size:12px;font-weight:600;color:#374151;">画面比例</label>
              <select id="vg-ratio" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;margin-top:4px;">${Object.entries(RATIOS).map(([k,v])=>`<option value="${k}" ${k==='16:9'?'selected':''}>${v}</option>`).join('')}</select></div>
            <div><label style="font-size:12px;font-weight:600;color:#374151;">时长: <span id="duration-val">5</span>秒</label>
              <input type="range" id="vg-duration" min="4" max="15" value="5" step="1" style="width:100%;margin-top:4px;accent-color:#4f46e5;"></div>
            <div style="display:flex;flex-direction:column;gap:6px;justify-content:flex-end;">
              <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;color:#374151;"><input type="checkbox" id="vg-audio" style="width:14px;height:14px;accent-color:#4f46e5;"> 🔊 生成音频</label>
              <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;color:#374151;"><input type="checkbox" id="vg-last-frame" style="width:14px;height:14px;accent-color:#4f46e5;"> 🖼 返回尾帧</label>
            </div>
          </div>
        </div>

        <!-- Generate -->
        <button id="vg-generate-btn" style="width:100%;padding:14px;background:#4f46e5;color:#fff;border:none;border-radius:12px;font-size:16px;font-weight:600;cursor:pointer;">🎬 生成视频</button>
        <div id="vg-status" style="text-align:center;font-size:13px;color:#6b7280;min-height:20px;"></div>
      </div>

      <!-- MIDDLE: Task History (videos + frames) -->
      <div style="width:320px;flex-shrink:0;overflow-y:auto;display:flex;flex-direction:column;gap:8px;">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <h3 style="font-size:13px;font-weight:600;color:#374151;margin:0;">📋 生成历史</h3>
          <button id="vg-refresh-btn2" style="padding:4px 10px;border:1px solid #d1d5db;background:#fff;border-radius:6px;font-size:11px;cursor:pointer;">🔄</button>
        </div>
        <div id="task-history" style="flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:6px;"><div style="text-align:center;padding:30px;color:#9ca3af;font-size:12px;">暂无生成记录</div></div>
      </div>

      <!-- RIGHT: Preview only -->
      <div style="flex:1;display:flex;flex-direction:column;gap:12px;min-width:0;overflow-y:auto;">
        <div style="background:#1a1a2e;border-radius:10px;overflow:hidden;position:relative;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;">
          <div id="video-preview-container" style="text-align:center;color:#9ca3af;"><div style="font-size:48px;margin-bottom:8px;">🎬</div><div style="font-size:13px;color:#d1d5db;">预览区域</div></div>
          <video id="video-player" controls style="display:none;width:100%;height:100%;object-fit:contain;"></video>
          <div id="video-loading" style="display:none;position:absolute;inset:0;background:rgba(0,0,0,0.6);align-items:center;justify-content:center;color:#fff;font-size:16px;flex-direction:column;gap:6px;"><div style="font-size:40px;">⏳</div><div>视频生成中...</div><div id="video-loading-status" style="font-size:12px;color:#d1d5db;"></div></div>
        </div>
        <div id="last-frame-section" style="display:none;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:10px;"><h4 style="font-size:11px;font-weight:600;color:#374151;margin:0 0 6px;">🖼 视频尾帧</h4><img id="last-frame-img" style="max-width:100%;max-height:180px;border-radius:6px;"></div>
        <div id="current-task-info" style="display:none;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:8px 12px;font-size:11px;color:#166534;"></div>
      </div>
    </div>

    <!-- MODAL -->
    <div id="asset-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:200;align-items:center;justify-content:center;">
      <div style="background:#fff;border-radius:16px;padding:24px;width:600px;max-height:70vh;display:flex;flex-direction:column;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="font-size:16px;font-weight:600;color:#111827;margin:0;">选择参考素材</h3>
          <button id="close-modal-btn" style="border:none;background:none;font-size:24px;cursor:pointer;color:#9ca3af;">&times;</button></div>
        <div id="modal-cat-tabs" style="display:flex;gap:4px;margin-bottom:12px;"></div>
        <div id="modal-asset-grid" style="flex:1;overflow-y:auto;display:flex;flex-wrap:wrap;gap:8px;min-height:120px;padding:8px;border:1px solid #e5e7eb;border-radius:8px;background:#fafafa;align-content:flex-start;"><div style="width:100%;text-align:center;padding:20px;color:#9ca3af;">加载中...</div></div>
        <button id="confirm-modal-btn" style="margin-top:16px;padding:10px;background:#4f46e5;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;">✅ 确认选择</button>
      </div>
    </div>

    <!-- Import Frame Modal -->
    <div id="import-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:210;align-items:center;justify-content:center;">
      <div style="background:#fff;border-radius:14px;padding:24px;width:400px;">
        <h3 style="font-size:15px;font-weight:600;color:#111827;margin:0 0 16px;">尾帧入库</h3>
        <div style="margin-bottom:12px;">
          <label style="display:block;font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">素材标签</label>
          <input id="import-label" type="text" placeholder="例如：视频尾帧-场景" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;box-sizing:border-box;">
        </div>
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">分类</label>
          <select id="import-category" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;box-sizing:border-box;">
            <option value="数字真人">🧑 数字真人（需 API 审核）</option>
            <option value="场景">🏞 场景（本地存储）</option>
            <option value="道具">🎯 道具（本地存储）</option>
            <option value="其他">📦 其他（本地存储）</option>
          </select>
        </div>
        <div style="display:flex;gap:8px;">
          <button id="import-cancel-btn" style="flex:1;padding:10px;border:1px solid #d1d5db;background:#fff;border-radius:10px;font-size:14px;cursor:pointer;">取消</button>
          <button id="import-confirm-btn" style="flex:1;padding:10px;background:#4f46e5;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;">确定入库</button>
        </div>
      </div>
    </div>
  `;

  bindEvents(root);
  loadHistory(root);
  return root;
}

// ═══════════════ EVENTS ═══════════════
function bindEvents(root: HTMLElement): void {
  root.querySelectorAll('.mode-btn').forEach(b=>b.addEventListener('click',()=>setMode((b as HTMLElement).dataset.mode||'reference')));
  root.querySelectorAll('.model-opt').forEach(b=>b.addEventListener('click',()=>selectModel((b as HTMLElement).dataset.model||'fast')));
  root.querySelector('#vg-generate-btn')?.addEventListener('click', handleGenerate);
  root.querySelector('#vg-pro-mode-btn')?.addEventListener('click',()=>{window.dispatchEvent(new CustomEvent('navigate',{detail:{page:'pro-mode'}}));});
  root.querySelector('#vg-refresh-btn')?.addEventListener('click',()=>loadHistory(root));
  root.querySelector('#vg-refresh-btn2')?.addEventListener('click',()=>loadHistory(root));
  root.querySelector('#optimize-btn')?.addEventListener('click', handleOptimize);
  root.querySelector('#template-btn')?.addEventListener('click', insertTemplate);
  root.querySelector('#accept-opt-btn')?.addEventListener('click', acceptOpt);
  root.querySelector('#reject-opt-btn')?.addEventListener('click', rejectOpt);
  root.querySelector('#pick-assets-btn')?.addEventListener('click', openModal);
  root.querySelector('#first-frame-picker')?.addEventListener('click',()=>{_mode='first_frame';openModal();});
  root.querySelector('#last-frame-picker')?.addEventListener('click',()=>{_mode='first_last_frame';openModal();});
  root.querySelector('#vg-duration')?.addEventListener('input',function(){const v=root.querySelector('#duration-val');if(v)v.textContent=(this as HTMLInputElement).value;});
  root.querySelector('#vg-prompt')?.addEventListener('input',function(){const c=root.querySelector('#prompt-count');if(c)c.textContent=`${(this as HTMLTextAreaElement).value.length}/2000`;});
  root.querySelector('#close-modal-btn')?.addEventListener('click',()=>{document.getElementById('asset-modal')!.style.display='none';});
  root.querySelector('#confirm-modal-btn')?.addEventListener('click',()=>{document.getElementById('asset-modal')!.style.display='none';refreshChips();});
  root.querySelector('#asset-modal')?.addEventListener('click',e=>{if((e.target as HTMLElement).id==='asset-modal')document.getElementById('asset-modal')!.style.display='none';});

  // Import modal events
  root.querySelector('#import-cancel-btn')?.addEventListener('click', closeImportModal);
  root.querySelector('#import-confirm-btn')?.addEventListener('click', doImportFrame);
  root.querySelector('#import-modal')?.addEventListener('click', e => { if ((e.target as HTMLElement).id === 'import-modal') closeImportModal(); });
}

// ═══════════════ MODE / MODEL ═══════════════
function setMode(m:string):void{_mode=m;_selRefs=[];_first=null;_last=null;
  document.querySelectorAll('.mode-btn').forEach(b=>{const a=(b as HTMLElement).dataset.mode===m;(b as HTMLElement).style.borderColor=a?'#4f46e5':'#e5e7eb';(b as HTMLElement).style.background=a?'#eef2ff':'#fff';(b as HTMLElement).style.color=a?'#4f46e5':'#374151';(b as HTMLElement).style.fontWeight=a?'600':'400';});
  const ap=document.getElementById('asset-panel'),fs=document.getElementById('frame-selectors'),lp=document.getElementById('last-frame-picker');
  if(ap)ap.style.display=m==='text'?'none':'block';if(fs)fs.style.display=(m==='first_frame'||m==='first_last_frame')?'block':'none';if(lp)lp.style.display=m==='first_last_frame'?'block':'none';refreshChips();
}
function selectModel(m:string):void{
  document.querySelectorAll('.model-opt').forEach(b=>{const a=(b as HTMLElement).dataset.model===m;(b as HTMLElement).style.borderColor=a?'#4f46e5':'#e5e7eb';(b as HTMLElement).style.background=a?'#eef2ff':'#fff';(b.querySelector('span:nth-child(2)') as HTMLElement).style.color=a?'#4f46e5':'#374151';});
  const old=document.getElementById('vg-resolution')as HTMLSelectElement;if(!old)return;
  const max=m==='standard'?'1080p':'720p';const all=['480p','720p','1080p'];const avail=all.slice(0,all.indexOf(max)+1);const cur=old.value;
  old.innerHTML=avail.map(r=>`<option value="${r}" ${r===cur||(r==='720p'&&!avail.includes(cur))?'selected':''}>${r}</option>`).join('');
}

// ═══════════════ GENERATE ═══════════════
async function handleGenerate():Promise<void>{
  const prompt=(document.getElementById('vg-prompt')as HTMLTextAreaElement)?.value?.trim();if(!prompt){alert('请输入提示词');return;}
  const model=getActiveModel(),resolution=(document.getElementById('vg-resolution')as HTMLSelectElement)?.value||'720p';
  const ratio=(document.getElementById('vg-ratio')as HTMLSelectElement)?.value||'16:9',duration=parseInt((document.getElementById('vg-duration')as HTMLInputElement)?.value||'5');
  const genAudio=(document.getElementById('vg-audio')as HTMLInputElement)?.checked||false,retLF=(document.getElementById('vg-last-frame')as HTMLInputElement)?.checked||false;
  showLoading();
  try{
    const body:Record<string,any>={prompt,mode:_mode,model,resolution,ratio,duration,generate_audio:genAudio,return_last_frame:retLF,auto_download:true};
    if(_mode==='reference')body.reference_assets=_selRefs.map(a=>a.asset_url);
    else if(_mode==='first_frame'&&_first)body.first_frame_asset=_first.asset_url;
    else if(_mode==='first_last_frame'&&_first&&_last){body.first_frame_asset=_first.asset_url;body.last_frame_asset=_last.asset_url;}
    const res=await fetch('/api/v1/video-gen/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await res.json();if(!res.ok)throw new Error(d.detail||`HTTP ${res.status}`);
    startPoll(d.task_id);
  }catch(e:any){alert('生成失败: '+e.message);hideLoading();}
}
function getActiveModel():string{const el=document.querySelector('.model-opt[style*="background: rgb(238, 242, 255)"]')as HTMLElement||document.querySelector('.model-opt[style*="background:#eef2ff"]')as HTMLElement;return el?.dataset?.model||'fast';}
function showLoading():void{const l=document.getElementById('video-loading')!,p=document.getElementById('video-preview-container')!,v=document.getElementById('video-player')as HTMLVideoElement;l.style.display='flex';p.style.display='none';v.style.display='none';}
function hideLoading():void{const l=document.getElementById('video-loading')!,p=document.getElementById('video-preview-container')!;l.style.display='none';p.style.display='block';}
function startPoll(taskId:string):void{if(_pollTimer)clearInterval(_pollTimer);_pollTimer=setInterval(async()=>{
  try{const d=await apiGet<any>(`/v1/video-gen/tasks/${taskId}`);const ls=document.getElementById('video-loading-status');if(ls)ls.textContent=`任务 ${taskId} · ${d.status}`;
    if(d.status==='succeeded'){clearInterval(_pollTimer!);_pollTimer=null;const vp=document.getElementById('video-player')as HTMLVideoElement;const src=d.local_path?`/api/v1/video-gen/videos/${taskId}`:d.video_url;if(vp&&src){vp.src=src;vp.style.display='block';}hideLoading();
      if(d.last_frame_url){const lfs=document.getElementById('last-frame-section')!,lfi=document.getElementById('last-frame-img')as HTMLImageElement;lfs.style.display='block';lfi.src=d.last_frame_url;}
      const info=document.getElementById('current-task-info')!;info.style.display='block';info.innerHTML=`✅ 完成 · ${d.tokens||'N/A'} tokens · <a href="${d.video_url}" download style="color:#4f46e5;">📥 下载</a>`;loadHistory(document.querySelector('.feature-page')!);}
    else if(d.status==='failed'||d.status==='expired'){clearInterval(_pollTimer!);_pollTimer=null;hideLoading();const info=document.getElementById('current-task-info')!;info.style.display='block';info.style.background='#fef2f2';info.style.borderColor='#fecaca';info.style.color='#dc2626';info.textContent=`❌ ${d.status}: ${d.error||''}`;loadHistory(document.querySelector('.feature-page')!);}}catch{}},10000);}

// ═══════════════ OPTIMIZE ═══════════════
async function handleOptimize():Promise<void>{
  const ta=document.getElementById('vg-prompt')as HTMLTextAreaElement;const p=ta?.value?.trim();if(!p)return;
  const panel=document.getElementById('optimized-panel')!,txt=document.getElementById('optimized-text')!,btn=document.getElementById('optimize-btn')as HTMLButtonElement;
  btn.disabled=true;btn.textContent='⏳';panel.style.display='block';txt.textContent='优化中...';
  try{const refs=_selRefs.map(a=>({label:a.label,category:a.category,asset_url:a.asset_url,usage:a.usage||DEFAULT_USAGE[a.category]||'style'}));const res=await fetch('/api/v1/video-gen/optimize-prompt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:p,reference_assets:refs})});const d=await res.json();if(d.success&&d.optimized){_optimized=d.optimized;txt.textContent=d.optimized;}else txt.textContent='优化失败';}catch(e:any){txt.textContent=`错误: ${e.message}`;}
  btn.disabled=false;btn.textContent='✨ AI 优化';
}

function insertTemplate():void{
  const ta=document.getElementById('vg-prompt')as HTMLTextAreaElement;if(!ta)return;
  const refs=_selRefs.map(a=>`@${a.label}`).join(' ');
  const template=`【镜头目标】\n\n【人物动作】${refs?refs+' ':''}人物正面微笑，眼神看向镜头\n\n【场景】自然光室内环境\n\n【摄像机运动】缓慢推近 (slow push-in)\n\n【光影】柔光从左侧打来，暖色调\n\n【约束】保持人物面部一致，不改变发型，不遮挡面部`;
  if(ta.value.trim()){ta.value=ta.value+'\\n\\n'+template;}else{ta.value=template;}
  ta.focus();ta.dispatchEvent(new Event('input'));
}
function acceptOpt():void{if(!_optimized)return;const ta=document.getElementById('vg-prompt')as HTMLTextAreaElement;if(ta)ta.value=_optimized;document.getElementById('optimized-panel')!.style.display='none';_optimized='';}
function rejectOpt():void{document.getElementById('optimized-panel')!.style.display='none';_optimized='';}

// ═══════════════ MODAL ═══════════════
function openModal():void{const m=document.getElementById('asset-modal')as HTMLElement;if(!m)return;m.style.display='flex';_modalCat='全部';updateModalTabs();loadModalAssets();}
function updateModalTabs():void{const tabs=document.getElementById('modal-cat-tabs');if(!tabs)return;tabs.innerHTML='';['全部','数字真人','场景','道具','其他'].forEach(c=>{const b=h('button',`padding:4px 10px;border:1px solid ${c===_modalCat?'#4f46e5':'#e5e7eb'};background:${c===_modalCat?'#eef2ff':'#fff'};border-radius:14px;font-size:11px;cursor:pointer;color:${c===_modalCat?'#4f46e5':'#6b7280'};`,[`${CAT_ICON[c]||'📋'} ${c}`]);b.addEventListener('click',()=>{_modalCat=c;updateModalTabs();loadModalAssets();});tabs.appendChild(b);});}
async function loadModalAssets():Promise<void>{const grid=document.getElementById('modal-asset-grid');if(!grid)return;grid.innerHTML='<div style="width:100%;text-align:center;padding:20px;color:#9ca3af;">加载中...</div>';try{const p=_modalCat&&_modalCat!=='全部'?`?category=${encodeURIComponent(_modalCat)}`:'';const data=await apiGet<{total:number;assets:AssetItem[]}>(`/v1/assets${p}`);_modalAssets=data.assets.filter(a=>a.status==='Active');if(_modalAssets.length===0){grid.innerHTML='<div style="width:100%;text-align:center;padding:20px;color:#9ca3af;">暂无素材</div>';return;}grid.innerHTML='';_modalAssets.forEach(a=>{const checked=isSelected(a.asset_url);const card=document.createElement('div');card.style.cssText=`width:80px;text-align:center;cursor:pointer;padding:6px;border-radius:8px;border:2px solid ${checked?'#4f46e5':'transparent'};background:${checked?'#eef2ff':'#fff'};`;card.dataset.url=a.asset_url;card.innerHTML=`<img src="${a.public_url}" style="width:68px;height:68px;border-radius:6px;object-fit:cover;background:#f3f4f6;" onerror="this.outerHTML='<div style=\\'width:68px;height:68px;border-radius:6px;background:#f3f4f6;display:flex;align-items:center;justify-content:center;font-size:28px;\\'>${CAT_ICON[a.category]||'📦'}</div>'"><div style="font-size:9px;color:#6b7280;margin-top:3px;">${a.label.slice(0,8)}</div><div style="font-size:8px;color:#9ca3af;">${CAT_ICON[a.category]||'📦'} ${a.category}</div>`;card.addEventListener('click',()=>toggleModalAsset(card,a));grid.appendChild(card);});}catch{grid.innerHTML='<div style="width:100%;text-align:center;padding:20px;color:#e74c3c;">加载失败</div>';}}
function isSelected(url:string):boolean{if(_mode==='reference')return _selRefs.some(a=>a.asset_url===url);if(_mode==='first_frame')return _first?.asset_url===url;if(_mode==='first_last_frame')return _first?.asset_url===url||_last?.asset_url===url;return false;}
function toggleModalAsset(card:HTMLElement,a:AssetItem):void{if(_mode==='reference'){const i=_selRefs.findIndex(x=>x.asset_url===a.asset_url);if(i>=0){_selRefs.splice(i,1);card.style.borderColor='transparent';card.style.background='#fff';}else{if(_selRefs.length>=9){alert('最多9张');return;}a.usage=DEFAULT_USAGE[a.category]||'style';_selRefs.push(a);card.style.borderColor='#4f46e5';card.style.background='#eef2ff';}}else if(_mode==='first_frame'){_first=_first?.asset_url===a.asset_url?null:a;loadModalAssets();}else if(_mode==='first_last_frame'){if(_first?.asset_url===a.asset_url)_first=null;else if(_last?.asset_url===a.asset_url)_last=null;else if(!_first)_first=a;else if(!_last)_last=a;else{_first=null;_last=null;}loadModalAssets();}}

// ═══════════════ CHIPS ═══════════════
function refreshChips():void{const c=document.getElementById('selected-chips');if(!c)return;c.innerHTML='';
  const mk=(a:AssetItem,prefix:string,color:string)=>{const chip=document.createElement('div');chip.style.cssText=`display:inline-flex;align-items:center;gap:8px;padding:6px 10px 6px 6px;background:${color==='#4f46e5'?'#eef2ff':color==='#059669'?'#ecfdf5':'#fffbeb'};border:1px solid ${color==='#4f46e5'?'#c7d2fe':color==='#059669'?'#bbf7d0':'#fde68a'};border-radius:10px;`;
  const thumb=document.createElement('img');thumb.src=a.public_url;thumb.style.cssText='width:40px;height:40px;border-radius:6px;object-fit:cover;background:#f3f4f6;flex-shrink:0;';thumb.addEventListener('error',()=>{thumb.replaceWith(h('div','width:40px;height:40px;border-radius:6px;background:#f3f4f6;display:flex;align-items:center;justify-content:center;font-size:20px;',[CAT_ICON[a.category]||'📦']));});chip.appendChild(thumb);
  const info=document.createElement('div');info.style.cssText='display:flex;flex-direction:column;min-width:0;';const usage=USAGE_OPTIONS.find(u=>u.value===a.usage)||USAGE_OPTIONS[3];
info.innerHTML=`<span style="font-size:12px;font-weight:600;color:${color};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${prefix}${a.label}</span><span class="chip-at" data-label="${a.label}" style="font-size:10px;color:#6b7280;cursor:pointer;text-decoration:underline dotted;">@${a.label}</span><span class="chip-usage" data-url="${a.asset_url}" style="font-size:9px;color:#4f46e5;cursor:pointer;background:#eef2ff;padding:1px 4px;border-radius:8px;display:inline-block;width:fit-content;" title="点击切换用途">${usage.icon} ${usage.label}</span>`;info.querySelector('.chip-at')?.addEventListener('click',()=>{const ta=document.getElementById('vg-prompt')as HTMLTextAreaElement;if(!ta)return;const m=`@${a.label} `,s=ta.selectionStart;ta.value=ta.value.substring(0,s)+m+ta.value.substring(ta.selectionEnd);ta.focus();ta.selectionStart=ta.selectionEnd=s+m.length;});info.querySelector('.chip-usage')?.addEventListener('click',e=>{e.stopPropagation();const cur=a.usage||'style';const idx=USAGE_OPTIONS.findIndex(u=>u.value===cur);const next=USAGE_OPTIONS[(idx+1)%USAGE_OPTIONS.length];a.usage=next.value;refreshChips();});chip.appendChild(info);
  const del=document.createElement('button');del.style.cssText='border:none;background:rgba(0,0,0,0.1);cursor:pointer;color:#666;font-size:14px;width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;';del.textContent='×';del.addEventListener('click',ev=>{ev.stopPropagation();removeAsset(a.asset_url);});chip.appendChild(del);c.appendChild(chip);};
  if(_mode==='reference'){if(_selRefs.length===0)c.innerHTML='<span style="font-size:11px;color:#9ca3af;">未选择素材，点击上方按钮从素材库选择</span>';else _selRefs.forEach(a=>mk(a,'','#4f46e5'));}
  else if(_mode==='first_frame'){if(_first)mk(_first,'首帧: ','#059669');else c.innerHTML='<span style="font-size:11px;color:#f59e0b;">请选择首帧图片</span>';}
  else if(_mode==='first_last_frame'){if(_first)mk(_first,'首帧: ','#059669');if(_last)mk(_last,'尾帧: ','#d97706');if(!_first||!_last)c.appendChild(h('span','font-size:11px;color:#f59e0b;',[!_first?'请选择首帧':'请选择尾帧']));}}
function removeAsset(url:string):void{_selRefs=_selRefs.filter(a=>a.asset_url!==url);if(_first?.asset_url===url)_first=null;if(_last?.asset_url===url)_last=null;refreshChips();}

// ═══════════════ HISTORY (middle panel) ═══════════════
async function loadHistory(root: HTMLElement): Promise<void> {
  const h = root.querySelector('#task-history') as HTMLElement; if (!h) return;
  try {
    const data = await apiGet<{ total: number; tasks: any[] }>('/v1/video-gen/tasks?limit=30');
    if (data.tasks.length === 0) { h.innerHTML = '<div style="text-align:center;padding:30px;color:#9ca3af;font-size:12px;">暂无生成记录</div>'; return; }
    h.innerHTML = '';
    data.tasks.forEach((t: any) => {
      const sc = t.status === 'succeeded' ? '#059669' : t.status === 'failed' ? '#e74c3c' : '#d97706';
      const sb = t.status === 'succeeded' ? '#ecfdf5' : t.status === 'failed' ? '#fef2f2' : '#fffbeb';
      const sl: Record<string, string> = { queued: '排队', running: '生成中', succeeded: '完成', failed: '失败', expired: '过期' };
      const hasV = t.status === 'succeeded' && (t.local_path || t.video_url);
      const vs = hasV ? (t.local_path ? `/api/v1/video-gen/videos/${t.task_id}` : t.video_url) : '';
      const hasF = t.status === 'succeeded' && t.last_frame_url;

      const card = document.createElement('div');
      card.style.cssText = 'padding:8px 10px;background:#fff;border:1px solid #e5e7eb;border-radius:8px;';

      // Header row: status + prompt
      const hdr = document.createElement('div');
      hdr.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:4px;';
      hdr.innerHTML = `<span style="font-size:10px;padding:1px 6px;border-radius:10px;background:${sb};color:${sc};flex-shrink:0;white-space:nowrap;">${sl[t.status] || t.status}</span><span style="font-size:11px;color:#111827;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0;">${(t.prompt || '').slice(0, 30) || '(无提示词)'}</span>`;
      card.appendChild(hdr);

      // Meta row
      const meta = document.createElement('div');
      meta.style.cssText = 'font-size:9px;color:#9ca3af;margin-bottom:4px;';
      meta.textContent = `${t.model} · ${t.duration}s · ${t.tokens || 0}tok`;
      card.appendChild(meta);

      // Actions row
      const acts = document.createElement('div');
      acts.style.cssText = 'display:flex;gap:4px;flex-wrap:wrap;';

      if (hasV) {
        const play = document.createElement('button');
        play.style.cssText = 'padding:3px 8px;border:1px solid #d1d5db;background:#fff;border-radius:4px;cursor:pointer;font-size:10px;'; play.textContent = '▶ 播放';
        play.addEventListener('click', () => {
          const vp = document.getElementById('video-player') as HTMLVideoElement;
          const ph = document.getElementById('video-preview-container')!;
          if (vp && vs) { vp.src = vs; vp.style.display = 'block'; ph.style.display = 'none'; vp.play().catch(() => { }); }
          hideLoading();
        });
        acts.appendChild(play);

        const dl = document.createElement('a');
        dl.style.cssText = 'padding:3px 8px;border:1px solid #d1d5db;background:#fff;border-radius:4px;text-decoration:none;color:#374151;font-size:10px;'; dl.textContent = '📥 下载';
        (dl as HTMLAnchorElement).href = vs; (dl as HTMLAnchorElement).download = ''; acts.appendChild(dl);
      }

      if (hasF) {
        const viewF = document.createElement('button');
        viewF.style.cssText = 'padding:3px 8px;border:1px solid #d1d5db;background:#fff;border-radius:4px;cursor:pointer;font-size:10px;'; viewF.textContent = '🖼 尾帧';
        viewF.addEventListener('click', () => {
          const lfs = document.getElementById('last-frame-section')!, lfi = document.getElementById('last-frame-img') as HTMLImageElement;
          lfs.style.display = 'block'; lfi.src = t.last_frame_url;
        });
        acts.appendChild(viewF);

        const impF = document.createElement('button');
        impF.style.cssText = 'padding:3px 8px;border:1px solid #c7d2fe;background:#eef2ff;color:#4f46e5;border-radius:4px;cursor:pointer;font-size:10px;white-space:nowrap;'; impF.textContent = '+ 入库';
        impF.addEventListener('click', () => {
          showImportModal(t.last_frame_url, `尾帧-${t.task_id.slice(-8)}`, () => loadHistory(root));
        });
        acts.appendChild(impF);
      }

      // Delete
      const del = document.createElement('button');
      del.style.cssText = 'padding:3px 8px;border:1px solid #fecaca;background:#fff;color:#dc2626;border-radius:4px;cursor:pointer;font-size:10px;margin-left:auto;'; del.textContent = '🗑';
      del.addEventListener('click', async () => {
        if (!confirm('删除任务 ' + t.task_id + '?')) return;
        try { await fetch('/api/v1/video-gen/tasks/' + t.task_id, { method: 'DELETE' }); loadHistory(root); } catch (e: any) { alert(e.message); }
      });
      acts.appendChild(del);
      card.appendChild(acts);
      h.appendChild(card);
    });
  } catch { h.innerHTML = '<div style="text-align:center;padding:20px;color:#e74c3c;">加载失败</div>'; }
}

// ═══════════════ IMPORT FRAME MODAL ═══════════════
let _importFrameUrl = '';
let _importCallback: (() => void) | null = null;

function showImportModal(frameUrl: string, defaultLabel: string, callback: () => void): void {
  _importFrameUrl = frameUrl;
  _importCallback = callback;
  const modal = document.getElementById('import-modal')!;
  (document.getElementById('import-label') as HTMLInputElement).value = defaultLabel;
  (document.getElementById('import-category') as HTMLSelectElement).value = '数字真人';
  modal.style.display = 'flex';
}

function closeImportModal(): void {
  document.getElementById('import-modal')!.style.display = 'none';
  _importFrameUrl = '';
  _importCallback = null;
}

async function doImportFrame(): Promise<void> {
  const label = (document.getElementById('import-label') as HTMLInputElement).value.trim() || '视频尾帧';
  const category = (document.getElementById('import-category') as HTMLSelectElement).value;
  try {
    const r = await fetch('/api/v1/video-gen/frames/import', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_url: _importFrameUrl, label, category }),
    });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail);
    closeImportModal();
    alert(`✅ 入库成功！\n${d.asset_url}\n分类: ${d.category}`);
    if (_importCallback) _importCallback();
  } catch (e: any) { alert(`❌ 入库失败: ${e.message}`); }
}

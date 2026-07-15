/** Weekly Report — polished UI with card design & clean tables. */
import { apiGet, apiPost, apiDelete } from '../services/api';

interface WeekOption { label: string; is_current: boolean; offset: number; start: string; end: string; monday: string; sunday: string; }
interface ReportListItem { filename: string; sheet_name: string; date_range: string; created_at: string; download_url: string; }
interface ReportResult { success: boolean; message: string; filename: string; download_url: string; cells_updated: number; sheet_name: string; }
interface DayRow { time_slot: string; plan: string; summary: string; }
interface PreviewData { filename: string; sheet_name: string; date_range: string; days: { day_name: string; date_str: string; rows: DayRow[] }[]; summary_b: string; summary_c: string; }
const DAY_NAMES = ['周一','周二','周三','周四','周五'];
const C = { bg:'#f5f6f8', card:'#fff', primary:'#4f46e5', primaryLight:'#eef2ff', text:'#1e293b', muted:'#64748b', border:'#e2e8f0', green:'#059669', greenBg:'#ecfdf5' };

export function renderReportPage(): HTMLElement { const el=document.createElement('div');el.id='report-root';el.style.cssText=`height:100%;overflow:hidden;background:${C.bg};`;showListView(el);return el; }

// ═══════════════ LIST ═══════════════
async function showListView(el:HTMLElement):Promise<void>{
  el.innerHTML=`<div style="max-width:1280px;margin:0 auto;padding:32px 28px;height:100%;overflow-y:auto;">
    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:28px;">
      <div><h2 style="font-size:22px;font-weight:800;color:${C.text};margin:0;letter-spacing:-0.3px;">📊 周报管理</h2><p style="color:${C.muted};font-size:14px;margin:6px 0 0;">查看历史周报或创建新的周报</p></div>
      <button id="rp-create-btn" style="padding:11px 22px;background:${C.primary};color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;box-shadow:0 2px 8px rgba(79,70,229,0.25);transition:all 0.15s;"
        onmouseover="this.style.transform='translateY(-1px)';this.style.boxShadow='0 4px 14px rgba(79,70,229,0.35)'" onmouseout="this.style.transform='';this.style.boxShadow='0 2px 8px rgba(79,70,229,0.25)'">+ 创建周报</button></div>
    <div id="rp-list-loading" style="text-align:center;color:${C.muted};padding:60px 0;font-size:14px;">加载中...</div>
    <div id="rp-list-content" style="display:none;display:flex;flex-direction:column;gap:10px;"></div></div>`;
  el.querySelector('#rp-create-btn')?.addEventListener('click',()=>showCreateView(el));
  try{
    const reports=await apiGet<ReportListItem[]>('/v1/reports/list');
    const L=el.querySelector('#rp-list-loading') as HTMLElement,Ct=el.querySelector('#rp-list-content') as HTMLElement;
    if(L)L.style.display='none';if(Ct)Ct.style.display='block';
    if(!reports.length){if(Ct)Ct.innerHTML=`<div style="text-align:center;padding:64px 0;color:${C.muted};"><div style="font-size:48px;margin-bottom:12px;">📭</div><div style="font-size:15px;font-weight:500;">暂无周报记录</div><div style="font-size:13px;margin-top:6px;">点击「+ 创建周报」开始撰写</div></div>`;return;}
    const now=new Date();
    const ths=(t:string,w:string)=>`padding:10px 12px;text-align:left;font-weight:600;font-size:12px;color:#64748b;border-bottom:2px solid #e2e8f0;background:#f8fafc;${w?'width:'+w+';':''}`;
    if(Ct)Ct.innerHTML=`
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding:0 4px;">
        <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:${C.muted};cursor:pointer;"><input type="checkbox" id="rp-select-all" style="cursor:pointer;"> 全选</label>
        <span id="rp-selected-count" style="font-size:12px;color:${C.muted};display:none;"></span>
        <button id="rp-batch-delete" style="margin-left:auto;padding:5px 12px;border:1px solid #fca5a5;border-radius:6px;background:#fef2f2;color:#dc2626;font-size:11px;cursor:pointer;display:none;">🗑 删除选中</button></div>
      <div style="background:${C.card};border:1px solid ${C.border};border-radius:12px;overflow:hidden;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;color:${C.text};">
          <thead><tr><th style="${ths('checkbox','36px')}"></th><th style="${ths('周报名')}">周报名</th><th style="${ths('创建日期','120px')}">创建日期</th><th style="${ths('下载','80px')}">下载</th><th style="${ths('删除','60px')}">删除</th></tr></thead>
          <tbody>${reports.map(r=>{const d=new Date(r.created_at);const ds=d.toLocaleDateString('zh-CN');return`<tr class="rp-row" data-fn="${esc(r.filename)}" style="border-bottom:1px solid ${C.border};cursor:pointer;transition:background 0.1s;" onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background=''">
            <td style="padding:10px 12px;text-align:center;" onclick="event.stopPropagation()"><input type="checkbox" class="rp-cb" data-fn="${esc(r.filename)}" style="cursor:pointer;"></td>
            <td style="padding:10px 12px;font-weight:600;" class="rp-name-cell">📋 ${esc(r.sheet_name)} 周报<span style="font-weight:400;color:${C.muted};font-size:11px;margin-left:6px;">${esc(r.filename)}</span></td>
            <td style="padding:10px 12px;font-size:12px;color:${C.muted};">${ds}</td>
            <td style="padding:10px 12px;text-align:center;"><a href="${r.download_url}" download onclick="event.stopPropagation()" style="color:${C.primary};text-decoration:none;font-weight:500;font-size:12px;">⬇</a></td>
            <td style="padding:10px 12px;text-align:center;"><button class="rp-del-btn" data-fn="${esc(r.filename)}" onclick="event.stopPropagation()" style="border:none;background:transparent;color:#9ca3af;cursor:pointer;font-size:14px;padding:2px 6px;border-radius:4px;" onmouseover="this.style.color='#ef4444';this.style.background='#fef2f2'" onmouseout="this.style.color='#9ca3af';this.style.background='transparent'">✕</button></td>
          </tr>`}).join('')}</tbody></table></div>`;

    // Click row → detail view
    Ct.querySelectorAll('.rp-row').forEach(row=>{row.addEventListener('click',(e)=>{const t=e.target as HTMLElement;if(t.closest('a,button,input'))return;showDetailView(el,(row as HTMLElement).dataset.fn||'');});});
    // Delete single
    Ct.querySelectorAll('.rp-del-btn').forEach(btn=>{btn.addEventListener('click',async()=>{const fn=(btn as HTMLElement).dataset.fn||'';if(confirm(`确定删除「${fn}」？此操作不可撤销。`)){await apiDelete(`/v1/reports/${encodeURIComponent(fn)}`);showListView(el);}});});
    // Select all
    const selAll=el.querySelector('#rp-select-all') as HTMLInputElement;const batchBtn=el.querySelector('#rp-batch-delete') as HTMLElement;const countEl=el.querySelector('#rp-selected-count') as HTMLElement;
    function updateSel(){const cbs=Ct.querySelectorAll<HTMLInputElement>('.rp-cb');const sel=Array.from(cbs).filter(c=>c.checked);countEl.textContent=sel.length?`已选 ${sel.length} 项`:'';countEl.style.display=sel.length?'':'none';batchBtn.style.display=sel.length?'':'none';}
    selAll?.addEventListener('change',()=>{Ct.querySelectorAll<HTMLInputElement>('.rp-cb').forEach(c=>c.checked=selAll.checked);updateSel();});
    Ct.addEventListener('change',(e)=>{if((e.target as HTMLElement).classList.contains('rp-cb')){selAll.checked=false;updateSel();}});
    batchBtn?.addEventListener('click',async()=>{const sel=Array.from(Ct.querySelectorAll<HTMLInputElement>('.rp-cb')).filter(c=>c.checked);if(!sel.length)return;if(!confirm(`确定删除选中的 ${sel.length} 份周报？此操作不可撤销。`))return;for(const c of sel){await apiDelete(`/v1/reports/${encodeURIComponent(c.dataset.fn||'')}`);}showListView(el);});
  }catch{const L=el.querySelector('#rp-list-loading') as HTMLElement;if(L)L.textContent='加载失败，请刷新重试';}
}

// ═══════════════ DETAIL ═══════════════
async function showDetailView(el:HTMLElement,filename:string):Promise<void>{
  el.innerHTML=`<div style="display:flex;flex-direction:column;height:100%;">
    <div style="display:flex;align-items:center;gap:14px;padding:12px 24px;background:${C.card};border-bottom:1px solid ${C.border};flex-shrink:0;">
      <button id="rp-back-btn" style="border:none;background:transparent;color:${C.muted};cursor:pointer;font-size:18px;padding:6px 10px;border-radius:8px;transition:all 0.15s;"
        onmouseover="this.style.background='${C.primaryLight}';this.style.color='${C.primary}'" onmouseout="this.style.background='transparent';this.style.color='${C.muted}'">← 返回</button>
      <span style="font-weight:700;font-size:16px;color:${C.text};flex:1;">📋 ${esc(filename)} 预览</span>
      <button id="rp-detail-create-btn" style="padding:7px 18px;background:${C.primary};color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;">+ 新建</button></div>
    <div id="rp-detail-content" style="flex:1;overflow-y:auto;padding:28px 36px;background:${C.bg};"><div style="text-align:center;color:${C.muted};padding:60px 0;">加载中...</div></div></div>`;
  el.querySelector('#rp-back-btn')?.addEventListener('click',()=>showListView(el));
  el.querySelector('#rp-detail-create-btn')?.addEventListener('click',()=>showCreateView(el));
  try{const d=await apiGet<PreviewData>(`/v1/reports/preview/${encodeURIComponent(filename)}`);const ct=el.querySelector('#rp-detail-content') as HTMLElement;if(ct)ct.innerHTML=renderPreviewHTML(d,true);}
  catch{const ct=el.querySelector('#rp-detail-content') as HTMLElement;if(ct)ct.innerHTML=`<div style="text-align:center;color:#ef4444;padding:60px 0;">预览加载失败</div>`;}
}

// ═══════════════ CREATE ═══════════════
function showCreateView(el:HTMLElement):void{
  el.innerHTML=`<div style="display:flex;flex-direction:column;height:100%;">
    <div style="display:flex;align-items:center;gap:14px;padding:10px 24px;background:${C.card};border-bottom:1px solid ${C.border};flex-shrink:0;">
      <button id="rp-cancel-btn" style="border:none;background:transparent;color:${C.muted};cursor:pointer;font-size:18px;padding:6px 10px;border-radius:8px;transition:all 0.15s;"
        onmouseover="this.style.background='${C.primaryLight}';this.style.color='${C.primary}'" onmouseout="this.style.background='transparent';this.style.color='${C.muted}'">← 返回</button>
      <span style="font-weight:700;font-size:16px;color:${C.text};flex:1;">✏️ 创建新周报</span></div>
    <div style="flex:1;display:flex;overflow:hidden;">
      <div id="rp-create-left" style="width:560px;min-width:560px;padding:20px;overflow-y:auto;border-right:1px solid ${C.border};background:${C.card};display:flex;flex-direction:column;gap:14px;">
        <div><label style="font-size:13px;font-weight:700;color:${C.text};margin-bottom:6px;display:block;">📅 选择周范围</label>
          <select id="report-week-select" style="width:100%;padding:9px 12px;border:1px solid ${C.border};border-radius:8px;font-size:13px;background:#fff;color:${C.text};outline:none;"><option>加载中...</option></select></div>
        <div><label style="font-size:13px;font-weight:700;color:${C.text};margin-bottom:6px;display:block;">📄 周报模板</label>
          <div id="rp-template-info" style="display:flex;align-items:center;gap:8px;padding:10px 12px;background:#f8fafc;border:1px solid ${C.border};border-radius:8px;font-size:12px;color:${C.muted};">
            <span>⏳</span><span id="rp-template-label">检测中...</span>
            <button id="rp-template-change" style="margin-left:auto;padding:4px 10px;border:1px solid ${C.border};border-radius:6px;background:#fff;color:${C.muted};font-size:11px;cursor:pointer;white-space:nowrap;">更换</button></div></div>
        <div style="background:${C.primaryLight};border:2px solid #c7d2fe;border-radius:12px;padding:16px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
            <span style="font-size:13px;font-weight:700;color:#3730a3;">⚡ 快速输入本周工作</span>
            <button id="report-auto-fill" style="padding:5px 14px;background:#fff;color:${C.primary};border:1px solid #c7d2fe;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">🤖 自动填报</button></div>
          <textarea id="report-fast-text" rows="9" style="width:100%;padding:10px 12px;border:1px solid #c7d2fe;border-radius:8px;font-size:13px;resize:vertical;line-height:1.65;box-sizing:border-box;background:#fff;color:${C.text};outline:none;"
            placeholder="周一：上午…，下午…&#10;周二：上午…，下午…&#10;…"></textarea></div>
        <details id="report-days-details"><summary style="cursor:pointer;color:${C.muted};font-size:12px;font-weight:600;">📝 按天详细填写（自动填报后在此审核修改）</summary>
          <div id="report-days-container" style="margin-top:8px;display:flex;flex-direction:column;gap:8px;"></div></details>
        <button id="report-generate-btn" style="padding:12px;background:${C.primary};color:#fff;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;box-shadow:0 2px 8px rgba(79,70,229,0.22);transition:all 0.15s;"
          onmouseover="this.style.transform='translateY(-1px)';this.style.boxShadow='0 4px 14px rgba(79,70,229,0.32)'" onmouseout="this.style.transform='';this.style.boxShadow='0 2px 8px rgba(79,70,229,0.22)'">🚀 生成周报</button>
        <div id="report-status" style="font-size:12px;text-align:center;"></div></div>
      <div id="rp-create-right" style="flex:1;padding:24px 28px;overflow-y:auto;background:${C.bg};">
        <div id="rp-preview-empty" style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:${C.muted};font-size:14px;text-align:center;line-height:1.9;">
          <div style="font-size:56px;margin-bottom:8px;opacity:0.35;">📋</div>填写工作内容后生成周报<br>预览将在这里显示</div>
        <div id="rp-preview-content" style="display:none;"></div></div></div></div>`;
  el.querySelector('#rp-cancel-btn')?.addEventListener('click',()=>showListView(el));
  loadCreateForm(el);bindCreateEvents(el);
}

let _selectedTemplate='';
async function loadCreateForm(el:HTMLElement):Promise<void>{const s=el.querySelector('#report-week-select') as HTMLSelectElement;if(!s)return;try{const w=await apiGet<WeekOption[]>('/v1/reports/weeks');s.innerHTML='<option value="">-- 选择周 --</option>';w.forEach(w=>{const o=document.createElement('option');o.value=`${w.start}|${w.end}`;o.textContent=`${w.label}（${w.monday} — ${w.sunday}）`;s.appendChild(o);});const c=w.find(w=>w.is_current);if(c&&!s.value)s.value=`${c.start}|${c.end}`;buildDayInputs(el,(s.value?.split('|')[0])||c?.start||w[0]?.start||'');loadTemplateInfo(el,c?.start||'');s.addEventListener('change',()=>{const[start]=(s.value||'|').split('|');if(start){buildDayInputs(el,start);loadTemplateInfo(el,start);}});
  // Try restore draft from server
  try{const draft=await apiGet<{start_date:string,end_date:string,days:any[][]}>('/v1/reports/draft/load');
    if(draft.days&&draft.days.some((d:any[])=>d&&d.length)){_dayActivities=draft.days;renderAllActivities();updateDayWarnings();const st=document.querySelector('#report-status') as HTMLElement;if(st){st.textContent='📂 已恢复上次的草稿';st.style.color=C.muted;}}}catch{}}catch{s.innerHTML='<option>加载失败</option>';}}
// Auto-save draft on activity change
function autoSaveDraft(el:HTMLElement):void{const s=el.querySelector('#report-week-select') as HTMLSelectElement;if(!s?.value)return;const[start,end]=s.value.split('|');apiPost('/v1/reports/draft/save',{session_id:'default',start_date:start,end_date:end,days:_dayActivities}).catch(()=>{});}
async function loadTemplateInfo(el:HTMLElement,targetStart:string):Promise<void>{const lbl=el.querySelector('#rp-template-label') as HTMLElement;if(!lbl)return;try{const tmps=await apiGet<ReportListItem[]>('/v1/reports/templates');_selectedTemplate='';if(tmps.length){const bd=new Date(targetStart+'T00:00:00');const prev=tmps.find(t=>{const m=t.sheet_name.match(/(\d+)\.(\d+)-(\d+)\.(\d+)/);if(!m)return false;const end=new Date(bd.getFullYear(),parseInt(m[3])-1,parseInt(m[4]));return end<bd;});if(prev){_selectedTemplate=prev.filename;lbl.innerHTML='✅ 自动选中：<b>'+esc(prev.sheet_name)+' 周报</b>';lbl.style.color=C.green;}else if(tmps[0]){_selectedTemplate=tmps[0].filename;lbl.innerHTML='⚠️ 使用最新：<b>'+esc(tmps[0].sheet_name)+' 周报</b>';lbl.style.color='#d97706';}}if(!_selectedTemplate){lbl.textContent='⚠️ 未找到历史周报作为模板';lbl.style.color='#d97706';}}catch{lbl.textContent='加载模板失败';lbl.style.color='#ef4444';}
  el.querySelector('#rp-template-change')?.addEventListener('click',()=>showTemplatePicker(el));}
async function showTemplatePicker(el:HTMLElement):Promise<void>{try{const tmps=await apiGet<ReportListItem[]>('/v1/reports/templates');if(!tmps.length){alert('暂无历史周报可做模板');return;}const items=tmps.map(t=>`<div class="rp-tpl-item" data-fn="${esc(t.filename)}" style="padding:10px 14px;cursor:pointer;border-bottom:1px solid ${C.border};font-size:13px;color:${C.text};transition:background 0.1s;" onmouseover="this.style.background='${C.primaryLight}'" onmouseout="this.style.background=''">📋 <b>${esc(t.sheet_name)}</b> 周报<span style="color:${C.muted};font-size:11px;margin-left:8px;">${esc(t.filename)}</span>${t.filename===_selectedTemplate?' <span style="color:${C.primary};font-weight:600;float:right;">✓ 当前</span>':''}</div>`).join('');const overlay=document.createElement('div');overlay.id='rp-tpl-overlay';overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,0.3);z-index:200;display:flex;align-items:center;justify-content:center;';overlay.innerHTML=`<div style="background:#fff;border-radius:14px;width:520px;max-height:60vh;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,0.2);"><div style="padding:14px 18px;font-weight:700;font-size:15px;border-bottom:1px solid ${C.border};">📄 选择周报模板</div><div style="max-height:45vh;overflow-y:auto;">${items}</div><div style="padding:10px 18px;border-top:1px solid ${C.border};text-align:right;"><button id="rp-tpl-cancel" style="padding:7px 16px;border:1px solid ${C.border};border-radius:8px;background:#fff;color:${C.muted};cursor:pointer;font-size:13px;">取消</button></div></div>`;document.body.appendChild(overlay);overlay.addEventListener('click',e=>{if(e.target===overlay)overlay.remove();});overlay.querySelector('#rp-tpl-cancel')?.addEventListener('click',()=>overlay.remove());overlay.querySelectorAll('.rp-tpl-item').forEach(it=>{it.addEventListener('click',()=>{const fn=(it as HTMLElement).dataset.fn||'';_selectedTemplate=fn;const lbl=el.querySelector('#rp-template-label') as HTMLElement;if(lbl){const t=tmps.find(t=>t.filename===fn);if(t){lbl.innerHTML='✅ 已选择：<b>'+esc(t.sheet_name)+' 周报</b>';lbl.style.color=C.green;}}overlay.remove();});});}catch{alert('加载模板列表失败');}}
let _dayActivities: {period:string,time_start:string,time_end:string,activity:string,result:string}[][] = [[],[],[],[],[]];
function buildDayInputs(el:HTMLElement,sd:string):void{
  const c=el.querySelector('#report-days-container');if(!c)return;
  const s=new Date(sd+'T00:00:00');_dayActivities=[[],[],[],[],[]];
  c.innerHTML=DAY_NAMES.map((n,i)=>{const d=new Date(s);d.setDate(d.getDate()+i);return`<div class="rp-day-card" data-day="${i}" style="background:#fff;border:1px solid ${C.border};border-radius:10px;padding:12px;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
      <span style="font-weight:700;font-size:13px;color:${C.text};">${n}（${d.getMonth()+1}月${d.getDate()}日）</span>
      <span id="rp-warn-${i}" style="font-size:11px;color:#d97706;flex:1;margin:0 8px;"></span>
      <button class="rp-add-act" data-day="${i}" style="padding:3px 10px;border:1px solid ${C.primary};border-radius:5px;background:${C.primaryLight};color:${C.primary};font-size:11px;cursor:pointer;">+ 添加</button>
      <button class="rp-validate-day" data-day="${i}" title="自动修复冲突" style="padding:3px 8px;border:1px solid #f59e0b;border-radius:5px;background:#fffbeb;color:#d97706;font-size:11px;cursor:pointer;">🔍</button>
      <button class="rp-enrich-day" data-day="${i}" title="AI完善当天数据" style="padding:3px 8px;border:1px solid ${C.primary};border-radius:5px;background:${C.primaryLight};color:${C.primary};font-size:11px;cursor:pointer;">✨</button></div>
    <div class="rp-activities" id="rp-acts-${i}"></div></div>`}).join('');
  renderAllActivities();
  // Remove old listener before re-adding (prevent duplicate fires)
  const oldHandler=(c as any)._rpDayHandler;
  if(oldHandler){c.removeEventListener('click',oldHandler);c.removeEventListener('change',oldHandler);}
  const handler=(e:Event)=>{
    const t=e.target as HTMLElement;
    if(e.type==='click'){
      const addBtn=t.closest('.rp-add-act');if(addBtn){const di=parseInt((addBtn as HTMLElement).dataset.day||'0');_dayActivities[di].push({period:'上午',time_start:'',time_end:'',activity:'',result:''});renderActivities(di);return;}
      const delBtn=t.closest('.rp-del-act');if(delBtn){e.stopPropagation();e.preventDefault();const di=parseInt((delBtn as HTMLElement).dataset.day||'0');const ai=parseInt((delBtn as HTMLElement).dataset.idx||'0');if(_dayActivities[di]&&ai>=0&&ai<_dayActivities[di].length){_dayActivities[di].splice(ai,1);renderActivities(di);updateDayWarnings();const st=document.querySelector('#report-status') as HTMLElement;if(st&&_dayActivities[di].length===0){st.textContent='📭 '+DAY_NAMES[di]+' 已清空';st.style.color=C.muted;}}return;}
      const valBtn=t.closest('.rp-validate-day');if(valBtn){e.stopPropagation();const di=parseInt((valBtn as HTMLElement).dataset.day||'0');validateDay(di);return;}
    const enrichBtn=t.closest('.rp-enrich-day');if(enrichBtn){e.stopPropagation();enrichDay(el,parseInt((enrichBtn as HTMLElement).dataset.day||'0'));return;}
    }else if(e.type==='change'){
      if(!t.classList.contains('rp-act-input'))return;
      const di=parseInt(t.dataset.day||'0');const ai=parseInt(t.dataset.idx||'0');const field=t.dataset.field||'';
      if(_dayActivities[di]&&_dayActivities[di][ai]){(_dayActivities[di][ai] as any)[field]=t.tagName==='SELECT'?(t as HTMLSelectElement).value:(t as HTMLInputElement).value;}
    }
  };
  (c as any)._rpDayHandler=handler;
  c.addEventListener('click',handler);c.addEventListener('change',handler);
}
function renderActivities(di:number):void{const c=document.getElementById(`rp-acts-${di}`);if(!c||!_dayActivities[di])return;c.innerHTML=_dayActivities[di].map((a,i)=>`<div style="display:flex;align-items:center;gap:4px;padding:5px 0;border-bottom:1px solid #f1f5f9;">
  <select class="rp-act-input" data-day="${di}" data-idx="${i}" data-field="period" style="padding:4px 2px;border:1px solid ${C.border};border-radius:4px;font-size:11px;width:48px;flex-shrink:0;">${['上午','下午'].map(p=>`<option ${a.period===p?'selected':''}>${p}</option>`).join('')}</select>
  <input class="rp-act-input" data-day="${di}" data-idx="${i}" data-field="time_start" value="${esc(a.time_start)}" placeholder="开始" style="padding:4px 4px;border:1px solid ${C.border};border-radius:4px;font-size:10px;width:42px;flex-shrink:0;">
  <span style="font-size:10px;color:#9ca3af;">-</span>
  <input class="rp-act-input" data-day="${di}" data-idx="${i}" data-field="time_end" value="${esc(a.time_end)}" placeholder="结束" style="padding:4px 4px;border:1px solid ${C.border};border-radius:4px;font-size:10px;width:42px;flex-shrink:0;">
  <input class="rp-act-input" data-day="${di}" data-idx="${i}" data-field="activity" value="${esc(a.activity)}" placeholder="活动" style="padding:4px 6px;border:1px solid ${C.border};border-radius:4px;font-size:11px;flex:1;min-width:0;">
  <input class="rp-act-input" data-day="${di}" data-idx="${i}" data-field="result" value="${esc(a.result)}" placeholder="完成情况" style="padding:4px 6px;border:1px solid ${C.border};border-radius:4px;font-size:11px;flex:1;min-width:0;">
  <button class="rp-del-act" data-day="${di}" data-idx="${i}" style="border:none;background:transparent;color:#9ca3af;cursor:pointer;font-size:14px;flex-shrink:0;">✕</button></div>`).join('');}
function renderAllActivities():void{for(let i=0;i<5;i++)renderActivities(i);updateDayWarnings();}
// Show per-day warning badges
function updateDayWarnings():void{
  for(let i=0;i<5;i++){
    const badge=document.getElementById(`rp-warn-${i}`);if(!badge)continue;
    const acts=_dayActivities[i]||[];if(!acts.length){badge.textContent='';continue;}
    const issues:string[]=[];
    // Quick scan for obvious problems
    for(const a of acts){
      if(!a.time_start&&a.activity)issues.push('缺时间');
      if(a.time_start&&a.time_end&&a.time_start>a.time_end)issues.push('时间倒置');
      if(!a.activity)issues.push('缺内容');
      if(!a.result)issues.push('缺结果');
    }
    // Check overlaps
    const sorted=[...acts].sort((a,b)=>{if(a.period!==b.period)return a.period==='上午'?-1:1;return (a.time_start||'').localeCompare(b.time_start||'');});
    for(let j=1;j<sorted.length;j++){if(sorted[j].period===sorted[j-1].period&&sorted[j-1].time_end&&sorted[j].time_start&&sorted[j-1].time_end>sorted[j].time_start){issues.push('时间重叠');break;}}
    if(issues.length){badge.textContent='⚠️ '+issues.join('·');badge.style.display='';}
    else{badge.textContent='✅';badge.style.display='';}
  }
}
function toMinutes(t:string):number{if(!t)return-1;const[p,q]=t.split(':').map(Number);return p*60+q;}
function fromMinutes(m:number):string{return `${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;}

function validateDay(di:number):string[]{const w:string[]=[];const acts=_dayActivities[di]||[];if(!acts.length)return w;
  // Separate into locked (user-specified time) vs flexible (no time = auto-arrange)
  const locked:{period:string,time_start:string,time_end:string,activity:string,result:string}[]=[];
  const flex:{period:string,time_start:string,time_end:string,activity:string,result:string}[]=[];
  for(const a of acts){
    if(!a.activity)continue;
    if(!a.result&&a.activity){a.result='完成'+a.activity.slice(0,20);}
    if(a.time_start){locked.push({...a});}else{flex.push({...a});}
  }
  // Fix inverted times in locked
  for(const a of locked){if(a.time_start&&a.time_end&&a.time_start>a.time_end){[a.time_start,a.time_end]=[a.time_end,a.time_start];w.push(`「${a.activity}」时间倒置已交换`);}}

  // Place locked activities first, then fill flexible into gaps
  const processPeriod=(period:'上午'|'下午',periodStart:number,periodEnd:number)=>{
    const pLocked=locked.filter(a=>a.period===period).sort((a,b)=>(a.time_start||'').localeCompare(b.time_start||''));
    const pFlex=flex.filter(a=>a.period===period);

    // Find gaps between locked activities
    const gaps:{start:number,end:number}[]=[];
    let cursor=periodStart;
    for(const a of pLocked){
      const s=toMinutes(a.time_start);
      if(s>cursor){gaps.push({start:cursor,end:s});}
      const e=toMinutes(a.time_end||a.time_start);
      cursor=Math.max(cursor,e);
    }
    if(cursor<periodEnd){gaps.push({start:cursor,end:periodEnd});}

    // Fill flexible activities into gaps
    if(pFlex.length>0&&gaps.length>0){
      const totalGapMin=gaps.reduce((s,g)=>s+(g.end-g.start),0);
      const slotMin=Math.max(30,Math.floor(totalGapMin/pFlex.length/30)*30);
      let gi=0,gapCursor=gaps[0]?.start||periodStart;
      for(const a of pFlex){
        // Find next available gap
        while(gi<gaps.length&&gapCursor+slotMin>gaps[gi].end){gi++;gapCursor=gaps[gi]?.start||periodEnd;}
        if(gi>=gaps.length||gapCursor+30>periodEnd)break;
        a.time_start=fromMinutes(gapCursor);
        const endMin=Math.min(gapCursor+slotMin,gaps[gi].end,periodEnd);
        a.time_end=fromMinutes(endMin);
        gapCursor=endMin;
        w.push(`${period}「${a.activity}」自动安排至${a.time_start}-${a.time_end}`);
      }
    }

    // If no gaps (all locked fills period), flex items get compact slots at end
    const unfilled=period==='上午'?morningUnfilled:afternoonUnfilled;
  };

  const morningUnfilled=flex.filter(a=>a.period==='上午'&&!a.time_start);
  const afternoonUnfilled=flex.filter(a=>a.period==='下午'&&!a.time_start);

  processPeriod('上午',540,720);  // 9:00-12:00
  processPeriod('下午',840,1080); // 14:00-18:00

  // Handle any remaining unfilled flexible items by compacting
  const remaining=flex.filter(a=>!a.time_start);
  if(remaining.length){
    // Compact them at the end of their period
    const mRem=remaining.filter(a=>a.period==='上午');
    const aRem=remaining.filter(a=>a.period==='下午');
    if(mRem.length){let t=710;for(const a of mRem){a.time_start=fromMinutes(Math.max(540,t-30*mRem.length));a.time_end=fromMinutes(Math.min(720,t));t-=30;}}
    if(aRem.length){let t=1070;for(const a of aRem){a.time_start=fromMinutes(Math.max(840,t-30*aRem.length));a.time_end=fromMinutes(Math.min(1080,t));t-=30;}}
  }

  const sorted=[...locked,...flex].sort((a,b)=>{if(a.period!==b.period)return a.period==='上午'?-1:1;return (a.time_start||'').localeCompare(b.time_start||'');});
  _dayActivities[di]=sorted;renderActivities(di);updateDayWarnings();

  const st=document.querySelector('#report-status') as HTMLElement;
  if(st){st.innerHTML=w.length?'🔧 '+DAY_NAMES[di]+'：'+w.slice(0,3).join('；'):'✅ '+DAY_NAMES[di]+' 已就绪';st.style.color=w.length?'#d97706':C.green;}
  return w;}
// Enrich single day via LLM
async function enrichDay(el:HTMLElement,di:number):Promise<void>{
  const st=document.querySelector('#report-status') as HTMLElement;if(st){st.textContent='✨ AI 正在完善数据...';st.style.color=C.muted;}
  const acts=_dayActivities[di]||[];const curSel=el.querySelector('#report-week-select') as HTMLSelectElement;
  if(!curSel?.value)return;const[start,end]=curSel.value.split('|');
  try{
    const payload=acts.map(a=>({day_index:di,period:a.period||'上午',time_start:a.time_start||'',time_end:a.time_end||'',activity:a.activity||'',result:a.result||''}));
    const res=await apiPost<{days:{day_index:number,activities:{period:string,time_start:string,time_end:string,activity:string,result:string}[]}[],warnings:string[]}>('/v1/reports/enrich',{activities:payload,start_date:start,end_date:end});
    if(res.days[di]?.activities?.length){_dayActivities[di]=res.days[di].activities;renderAllActivities();validateDay(di);autoSaveDraft(el);if(st){st.textContent=`✨ ${DAY_NAMES[di]} 已完善为 ${_dayActivities[di].length} 项活动`;st.style.color=C.green;}}
    else{if(st){st.textContent='完善失败，请重试';st.style.color='#ef4444';}}
  }catch(e:unknown){if(st){st.textContent=`完善失败：${e instanceof Error?e.message:''}`;st.style.color='#ef4444';}}
}
// Add validate/enrich all to details header
setTimeout(()=>{const hdr=document.querySelector('#report-days-details summary');if(hdr){const vBtn=document.createElement('button');vBtn.textContent='🔍 校验全部';vBtn.style.cssText='margin-left:8px;padding:2px 8px;border:1px solid #f59e0b;border-radius:4px;background:#fffbeb;color:#d97706;font-size:10px;cursor:pointer;';vBtn.onclick=(e)=>{e.preventDefault();e.stopPropagation();const allW:string[]=[];for(let i=0;i<5;i++)allW.push(...validateDay(i).map(w=>DAY_NAMES[i]+'：'+w));updateDayWarnings();const st=document.querySelector('#report-status') as HTMLElement;if(st){if(allW.length){st.innerHTML='🔧 '+allW.join('；');st.style.color='#d97706';}else{st.innerHTML='✅ 全部校验通过';st.style.color=C.green;}}};hdr.appendChild(vBtn);
  const eBtn=document.createElement('button');eBtn.textContent='✨ 完善全部';eBtn.style.cssText='margin-left:4px;padding:2px 8px;border:1px solid '+C.primary+';border-radius:4px;background:'+C.primaryLight+';color:'+C.primary+';font-size:10px;cursor:pointer;';eBtn.onclick=async(e)=>{e.preventDefault();e.stopPropagation();const el2=document.getElementById('report-root')||document.body;for(let i=0;i<5;i++){if(_dayActivities[i]?.length)await enrichDay(el2,i);}autoSaveDraft(el2);};hdr.appendChild(eBtn);}},50);
function bindCreateEvents(el:HTMLElement):void{const sel=el.querySelector('#report-week-select') as HTMLSelectElement,st=el.querySelector('#report-status') as HTMLElement;
  sel?.addEventListener('change',()=>{const[start]=(sel.value||'|').split('|');if(start)buildDayInputs(el,start);});
  // Auto-fill: use LLM to normalize free text → per-day structured content
  el.addEventListener('click',async(e)=>{
    const btn=(e.target as HTMLElement).closest('#report-auto-fill');
    if(!btn)return;e.stopPropagation();
    const raw=(el.querySelector('#report-fast-text') as HTMLTextAreaElement)?.value?.trim()||'';
    if(!raw){st.textContent='请先在快速输入框中填写内容';st.style.color='#d97706';return;}
    if(!sel?.value){st.textContent='请先选择周范围';st.style.color='#d97706';return;}
    const curSel2=el.querySelector('#report-week-select') as HTMLSelectElement;
    st.textContent=`🤖 AI 正在分析（目标周：${curSel2?.value?.split('|')[0]}～${curSel2?.value?.split('|')[1]}）...`;st.style.color=C.muted;
    try{
      const[start,end]=(curSel2?.value||'').split('|');
      const res=await apiPost<{days:{day_index:number,day_name:string,activities:{period:string,time_start:string,time_end:string,activity:string,result:string}[]}[],warnings:string[]}>('/v1/reports/auto-fill',{text:raw,start_date:start,end_date:end});
      let totalActs=0;
      for(const d of res.days){
        if(d.activities&&d.activities.length){
          // Frontend safety net: clip out-of-range times from LLM output
          for(const a of d.activities){
            if(a.period==='上午'){if(!a.time_start||a.time_start<'08:00')a.time_start='09:00';if(!a.time_end||a.time_end>'12:30')a.time_end='10:00';}
            else if(a.period==='下午'){if(!a.time_start||a.time_start<'13:00')a.time_start='14:00';if(!a.time_end||a.time_end>'18:30')a.time_end='15:00';}
          }
          _dayActivities[d.day_index]=d.activities;totalActs+=d.activities.length;
        }
      }
      renderAllActivities();updateDayWarnings();autoSaveDraft(el);
      (el.querySelector('#report-days-details') as HTMLDetailsElement).open=true;
      let msg=`✅ AI 已提取 ${totalActs} 条活动`;let color=C.green;
      if(res.warnings&&res.warnings.length>0){msg+=` | ⚠️ ${res.warnings.join('；')}`;color='#d97706';}
      else if(totalActs===0){msg='⚠️ 未提取到活动，请手动添加';color='#d97706';}
      st.innerHTML=msg;st.style.color=color;
    }catch(e:unknown){st.textContent=`自动填报失败：${e instanceof Error?e.message:'网络错误'}`;st.style.color='#ef4444';}
  });
  // Generate: validate first, then build text from activities
  el.querySelector('#report-generate-btn')?.addEventListener('click',async()=>{
    const curSel=el.querySelector('#report-week-select') as HTMLSelectElement; // re-read live element
    if(!curSel?.value)return;const[start,end]=curSel.value.split('|');
    st.textContent=`目标周：${start}～${end}`;st.style.color=C.muted;
    // Auto-fix time conflicts before generate (don't block)
    for(let i=0;i<5;i++){validateDay(i);}
    // Build activities JSON for new API
    const activities:any[]=[];
    for(let i=0;i<5;i++){for(const a of (_dayActivities[i]||[])){if(a.activity)activities.push({day_index:i,period:a.period,time_start:a.time_start,time_end:a.time_end,activity:a.activity,result:a.result});}}
    if(!activities.length){st.textContent='请先点击「自动填报」或手动添加活动';st.style.color='#d97706';return;}
    st.style.color=C.muted;st.textContent='⏳ 正在生成周报...';const b=el.querySelector('#report-generate-btn') as HTMLButtonElement;b.disabled=true;
    try{const d=await apiPost<ReportResult>('/v1/reports/generate',{start_date:start,end_date:end,activities,template_filename:_selectedTemplate||null});if(d.success){st.style.color=C.green;st.innerHTML=`✅ 生成完成！<a href="${d.download_url}" download style="color:${C.primary};font-weight:600;">下载文件</a>`;loadCreatePreview(el,d.filename);}else{st.style.color='#ef4444';st.textContent=`❌ ${d.message}`;}}catch(e:unknown){st.style.color='#ef4444';st.textContent=`请求失败：${e instanceof Error?e.message:''}`;}b.disabled=false;});}
async function loadCreatePreview(el:HTMLElement,fn:string):Promise<void>{const em=el.querySelector('#rp-preview-empty') as HTMLElement,ct=el.querySelector('#rp-preview-content') as HTMLElement;if(!em||!ct)return;try{const d=await apiGet<PreviewData>(`/v1/reports/preview/${encodeURIComponent(fn)}`);em.style.display='none';ct.style.display='block';ct.innerHTML=renderPreviewHTML(d,true);}catch{em.innerHTML='<div style="color:#ef4444;">预览加载失败</div>';em.style.display='flex';ct.style.display='none';}}

// ═══════════════ PREVIEW ═══════════════
function renderPreviewHTML(d:PreviewData,showCopy:boolean):string{
  const th=(text:string)=>`padding:9px 12px;text-align:left;font-weight:700;font-size:12px;color:#475569;border-bottom:2px solid #cbd5e1;background:#f1f5f9;`;
  const td=(style:string='')=>`padding:10px 12px;border-bottom:1px solid ${C.border};vertical-align:top;${style}`;
  const daysHTML=d.days.map(day=>`
    <div style="margin-bottom:20px;background:${C.card};border:1px solid ${C.border};border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
      <div style="padding:12px 16px;font-weight:700;font-size:14px;color:${C.text};background:#f8fafc;border-bottom:1px solid ${C.border};">${esc(day.date_str||'')} ${esc(day.day_name)}</div>
      <table style="width:100%;border-collapse:collapse;font-size:13px;color:${C.text};">
        <colgroup><col style="width:17%;"><col style="width:41.5%;"><col style="width:41.5%;"></colgroup>
        <thead><tr><th style="${th('')}">时间</th><th style="${th('')}">本周计划</th><th style="${th('')}">本周总结</th></tr></thead>
        <tbody>${day.rows.map((r,i)=>`<tr style="background:${i%2===0?'#fff':'#fafbfc'};"><td style="${td('text-align:center;font-size:12px;color:#64748b;')}">${esc(r.time_slot)}</td><td style="${td('line-height:1.6;')}">${esc(r.plan)||'—'}</td><td style="${td('line-height:1.6;')}">${esc(r.summary)||'—'}</td></tr>`).join('')}</tbody></table></div>`).join('');
  const sum=(d.summary_b||d.summary_c)?(()=>{
    const bLen=(d.summary_b||'').length;const cLen=(d.summary_c||'').length;
    const total=bLen+cLen||1;const bPct=Math.max(30,Math.min(55,Math.round(bLen/total*87)));const cPct=87-bPct;
    return`
    <div style="margin-top:24px;background:${C.card};border:1px solid ${C.border};border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
      <div style="padding:12px 16px;font-weight:700;font-size:14px;color:${C.text};background:#f8fafc;border-bottom:1px solid ${C.border};display:flex;align-items:center;justify-content:space-between;">
        <span>📊 本周总结</span>${showCopy?'<button onclick="window._rpCopySummary()" style="padding:5px 12px;border:1px solid '+C.border+';border-radius:6px;background:#fff;color:'+C.muted+';font-size:11px;cursor:pointer;font-weight:500;">📋 复制</button>':''}</div>
      <table id="rp-summary_table" style="width:100%;border-collapse:collapse;font-size:13px;color:${C.text};">
        <colgroup><col style="width:13%;"><col style="width:${bPct}%;"><col style="width:${cPct}%;"></colgroup>
        <thead><tr><th style="${th('')}">本周计划和目标</th><th style="${th('')}">主要进展和成果</th><th style="${th('')}">下周计划与目标</th></tr></thead>
        <tbody><tr>
          <td style="${td('white-space:pre-wrap;line-height:1.7;font-weight:500;')}">1、流程宣贯<br>2、改善案例<br>3、IT建设<br>4、其他工作</td>
          <td style="${td('white-space:pre-wrap;line-height:1.7;')}">${esc(d.summary_b)||'—'}</td>
          <td style="${td('white-space:pre-wrap;line-height:1.7;')}">${esc(d.summary_c)||'—'}</td>
        </tr></tbody></table></div>`})():'';

  // Register global copy handlers (replaces on every render)
  (window as any)._rpCopyAll = () => _rpCopy('rp-full-content');
  (window as any)._rpCopySummary = () => _rpCopy('rp-summary_table');

  return`<div style="max-width:1100px;margin:0 auto;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
      <h3 style="font-size:17px;font-weight:800;color:${C.text};margin:0;">📊 ${esc(d.date_range)} 周报预览</h3>
      ${showCopy?'<button onclick="window._rpCopyAll()" style="padding:7px 16px;background:'+C.primary+';color:#fff;border:none;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;box-shadow:0 2px 6px rgba(79,70,229,0.2);">📋 复制全部</button>':''}</div>
    <div id="rp-full-content">${daysHTML}${sum}</div></div>`;
}
// Copy with rich formatting — uses DOM selection + execCommand (preserves inline styles)
function _rpCopy(id:string):void{
  const el=document.getElementById(id);
  if(!el){alert('未找到复制内容');return;}
  // Clone the element so we don't mess with the displayed one
  const clone=el.cloneNode(true) as HTMLElement;
  clone.style.cssText='position:fixed;left:0;top:0;width:800px;z-index:99999;background:#fff;padding:8px;';
  document.body.appendChild(clone);
  const range=document.createRange();range.selectNodeContents(clone);
  const sel=window.getSelection();if(sel){sel.removeAllRanges();sel.addRange(range);}
  const ok=document.execCommand('copy');
  document.body.removeChild(clone);
  if(ok){showCopyToast();return;}
  // Fallback: Clipboard API
  const html=el.innerHTML;const plain=el.textContent||'';
  try{navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([html],{type:'text/html'}),'text/plain':new Blob([plain],{type:'text/plain'})})]).then(()=>showCopyToast());}
  catch{const ta=document.createElement('textarea');ta.value=plain;ta.style.cssText='position:fixed;left:0;top:0;';document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);showCopyToast();}
}
(window as any)._rpCopyAll=()=>_rpCopy('rp-full-content');
(window as any)._rpCopySummary=()=>_rpCopy('rp-summary_table');
function showCopyToast(msg?:string,err?:boolean):void{let t=document.getElementById('rp-copy-toast');if(!t){t=document.createElement('div');t.id='rp-copy-toast';t.style.cssText='position:fixed;bottom:28px;left:50%;transform:translateX(-50%);padding:10px 24px;border-radius:10px;font-size:13px;font-weight:500;z-index:9999;pointer-events:none;transition:opacity 0.3s;box-shadow:0 8px 24px rgba(0,0,0,0.18);';document.body.appendChild(t);}
  const m=msg||'✅ 已复制，可直接粘贴到邮件（含格式）';
  t.textContent=m;t.style.background=err?'#fef2f2':'#1e293b';t.style.color=err?'#dc2626':'#fff';t.style.opacity='1';
  setTimeout(()=>{t.style.opacity='0';},2200);}
function esc(s:string):string{if(!s)return'';const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

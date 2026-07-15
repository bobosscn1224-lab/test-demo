import { apiGet, apiPut } from '../services/api';

interface ProxyStatus {
  vpn_connected: boolean;
  vpn_ip: string | null;
  vpn_country: string | null;
  vpn_server: string | null;
  proxy_running: boolean;
  windows_proxy_enabled: boolean;
  last_error: string | null;
  reconnect_count: number;
}

interface ServerInfo {
  id: string;
  label: string;
}

interface ServerListResponse {
  servers: ServerInfo[];
}

let _refreshTimer: ReturnType<typeof setInterval> | null = null;

export function renderProxyControl(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'proxy-control p-3 border-t border-gray-200 bg-gray-50';
  el.innerHTML = `
    <div class="flex items-center justify-between mb-2">
      <span class="text-xs font-medium text-gray-500 uppercase tracking-wider">VPN 代理</span>
      <span class="proxy-overall-dot w-2 h-2 rounded-full bg-gray-300 inline-block" title="检查中..."></span>
    </div>
    <div class="proxy-info text-xs mb-2 hidden">
      <div class="proxy-server text-gray-500 truncate"></div>
      <div class="proxy-ip-country text-gray-400"></div>
    </div>
    <div class="proxy-checks space-y-1 mb-2">
      <div class="flex items-center gap-1.5 text-xs">
        <span class="check-vpn-dot w-1.5 h-1.5 rounded-full inline-block bg-gray-300"></span>
        <span class="text-gray-500">VPN <span class="check-vpn-text">检查中</span></span>
      </div>
      <div class="flex items-center gap-1.5 text-xs">
        <span class="check-tinyproxy-dot w-1.5 h-1.5 rounded-full inline-block bg-gray-300"></span>
        <span class="text-gray-500">tinyproxy <span class="check-tinyproxy-text">检查中</span></span>
      </div>
      <div class="flex items-center gap-1.5 text-xs">
        <span class="check-winproxy-dot w-1.5 h-1.5 rounded-full inline-block bg-gray-300"></span>
        <span class="text-gray-500">系统代理 <span class="check-winproxy-text">检查中</span></span>
      </div>
    </div>
    <div class="proxy-error text-xs text-red-500 mb-2 hidden"></div>
    <div class="mb-2">
      <span class="text-xs text-gray-400">选择服务器</span>
      <select class="server-select w-full text-xs py-1 px-2 rounded border border-gray-200 bg-white text-gray-600 mt-0.5 focus:outline-none focus:border-indigo-400">
      </select>
    </div>
    <div class="flex gap-1.5">
      <button class="proxy-toggle-btn flex-1 py-1.5 px-3 text-xs rounded-lg transition-colors disabled:opacity-50 disabled:cursor-wait"
              disabled>
        <span class="proxy-btn-text">检查中...</span>
      </button>
      <button class="proxy-repair-btn py-1.5 px-2 text-xs rounded-lg bg-amber-50 text-amber-600 hover:bg-amber-100 border border-amber-200 transition-colors disabled:opacity-50 disabled:cursor-wait"
              title="一键修复" disabled>
        🔧
      </button>
    </div>
  `;

  bind(el);
  refreshStatus(el);
  loadServers(el);

  // Auto-refresh every 12 seconds
  if (_refreshTimer) clearInterval(_refreshTimer);
  _refreshTimer = setInterval(() => refreshStatus(el), 12000);

  return el;
}

function bind(el: HTMLElement): void {
  el.querySelector('.proxy-toggle-btn')?.addEventListener('click', () => toggleProxy(el));
  el.querySelector('.proxy-repair-btn')?.addEventListener('click', () => repairProxy(el));
}

function setCheck(el: HTMLElement, prefix: string, ok: boolean, text: string): void {
  const dot = el.querySelector(`.check-${prefix}-dot`) as HTMLElement;
  const label = el.querySelector(`.check-${prefix}-text`) as HTMLElement;
  if (dot) {
    dot.className = `check-${prefix}-dot w-1.5 h-1.5 rounded-full inline-block ${ok ? 'bg-green-500' : 'bg-red-400'}`;
  }
  if (label) {
    label.textContent = text;
    label.className = ok ? 'text-green-600' : 'text-red-500';
  }
}

async function loadServers(el: HTMLElement): Promise<void> {
  const select = el.querySelector('.server-select') as HTMLSelectElement;
  try {
    const data = await apiGet<ServerListResponse>('/proxy/servers');
    select.innerHTML = data.servers.map(s =>
      `<option value="${s.id}">${s.label}</option>`
    ).join('');
    select.disabled = false;
  } catch {
    select.innerHTML = '<option>加载失败</option>';
  }
}

async function refreshStatus(el: HTMLElement): Promise<void> {
  const overallDot = el.querySelector('.proxy-overall-dot') as HTMLElement;
  const info = el.querySelector('.proxy-info') as HTMLElement;
  const serverEl = el.querySelector('.proxy-server') as HTMLElement;
  const ipCountryEl = el.querySelector('.proxy-ip-country') as HTMLElement;
  const btn = el.querySelector('.proxy-toggle-btn') as HTMLButtonElement;
  const btnText = el.querySelector('.proxy-btn-text') as HTMLElement;
  const repairBtn = el.querySelector('.proxy-repair-btn') as HTMLButtonElement;
  const errorEl = el.querySelector('.proxy-error') as HTMLElement;

  try {
    const s = await apiGet<ProxyStatus>('/proxy/status');

    setCheck(el, 'vpn', s.vpn_connected, s.vpn_connected ? `已连接 (${s.vpn_ip || '-'})` : '未连接');
    setCheck(el, 'tinyproxy', s.proxy_running, s.proxy_running ? '运行中' : '已停止');
    setCheck(el, 'winproxy', s.windows_proxy_enabled, s.windows_proxy_enabled ? '已开启' : '已关闭');

    const online = s.vpn_connected && s.proxy_running && s.windows_proxy_enabled;
    overallDot.className = `proxy-overall-dot w-2 h-2 rounded-full inline-block ${online ? 'bg-green-500' : 'bg-red-400'}`;
    overallDot.title = online ? '全部正常' : '部分异常 — 点🔧修复';

    // Error message
    if (s.last_error && !online) {
      errorEl.classList.remove('hidden');
      errorEl.textContent = `⚠ ${s.last_error}`;
    } else {
      errorEl.classList.add('hidden');
    }

    // IP/server info
    if (s.vpn_connected && s.vpn_ip) {
      info.classList.remove('hidden');
      serverEl.textContent = `📍 ${s.vpn_server || 'VPN'}`;
      ipCountryEl.textContent = `${s.vpn_ip} — ${s.vpn_country || ''}`;
    } else {
      info.classList.add('hidden');
    }

    btn.disabled = false;
    btn.className = `proxy-toggle-btn flex-1 py-1.5 px-3 text-xs rounded-lg transition-colors disabled:opacity-50 disabled:cursor-wait ${
      online
        ? 'bg-red-50 text-red-600 hover:bg-red-100 border border-red-200'
        : 'bg-green-50 text-green-600 hover:bg-green-100 border border-green-200'
    }`;
    btnText.textContent = online ? '关闭代理' : '开启代理';

    repairBtn.disabled = false;
  } catch {
    setCheck(el, 'vpn', false, '获取失败');
    setCheck(el, 'tinyproxy', false, '获取失败');
    setCheck(el, 'winproxy', false, '获取失败');
    overallDot.className = 'proxy-overall-dot w-2 h-2 rounded-full inline-block bg-red-400';
    errorEl.classList.remove('hidden');
    errorEl.textContent = '⚠ 无法连接后端服务';
    btn.disabled = false;
    btn.className = 'proxy-toggle-btn flex-1 py-1.5 px-3 text-xs rounded-lg transition-colors bg-gray-100 text-gray-500 hover:bg-gray-200';
    btnText.textContent = '重试';
    repairBtn.disabled = false;
  }
}

async function toggleProxy(el: HTMLElement): Promise<void> {
  const btn = el.querySelector('.proxy-toggle-btn') as HTMLButtonElement;
  const btnText = el.querySelector('.proxy-btn-text') as HTMLElement;
  const repairBtn = el.querySelector('.proxy-repair-btn') as HTMLButtonElement;
  btn.disabled = true;
  repairBtn.disabled = true;

  try {
    // Check current state first
    const s = await apiGet<ProxyStatus>('/proxy/status');
    if (s.vpn_connected) {
      // Currently online → stop
      btnText.textContent = '关闭中...';
      await apiPut<unknown>('/proxy/stop');
    } else {
      // Currently offline → connect to selected server
      btnText.textContent = '连接中...';
      const serverId = (el.querySelector('.server-select') as HTMLSelectElement)?.value || 'us';
      await apiPut<unknown>(`/proxy/connect/${serverId}`);
    }
  } catch {
    // ignore
  }

  await new Promise(r => setTimeout(r, 3000));
  await refreshStatus(el);
}

async function repairProxy(el: HTMLElement): Promise<void> {
  const btn = el.querySelector('.proxy-toggle-btn') as HTMLButtonElement;
  const btnText = el.querySelector('.proxy-btn-text') as HTMLElement;
  const repairBtn = el.querySelector('.proxy-repair-btn') as HTMLButtonElement;
  btn.disabled = true;
  repairBtn.disabled = true;
  btnText.textContent = '修复中...';
  repairBtn.textContent = '⏳';

  try {
    await apiPut<unknown>('/proxy/repair');
  } catch {
    // ignore
  }

  await new Promise(r => setTimeout(r, 5000));
  await refreshStatus(el);
}

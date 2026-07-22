/** Top navigation bar — personal work platform main navigation. */

export interface NavItem {
  page: string;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { page: 'chat',      label: '对话',   icon: '💬' },
  { page: 'knowledge', label: '知识库', icon: '📚' },
  { page: 'report',    label: '周报',   icon: '📊' },
  { page: 'image-gen', label: '图片',   icon: '🎨' },
  { page: 'pptx',      label: 'PPT',    icon: '📽' },
  { page: 'ppt-maker', label: 'PPT制作', icon: '🎨' },
  { page: 'asset-manage', label: '素材', icon: '📦' },
  { page: 'video-gen', label: '视频', icon: '🎬' },
  { page: 'pro-mode', label: '专业模式', icon: '🎥' },
  { page: 'skills',    label: '技能',   icon: '⚡' },
];

let _activePage = 'chat';

export function getActivePage(): string {
  return _activePage;
}

export function renderTopNav(): HTMLElement {
  const nav = document.createElement('nav');
  nav.className = 'top-nav';
  nav.style.cssText =
    'display:flex;align-items:center;height:52px;padding:0 20px;' +
    'background:#fff;border-bottom:1px solid #e5e7eb;' +
    'flex-shrink:0;z-index:100;gap:4px;';

  // Logo
  const logo = document.createElement('span');
  logo.textContent = '🏠';
  logo.style.cssText = 'font-size:20px;margin-right:16px;cursor:pointer;flex-shrink:0;';
  logo.title = '个人工作平台';
  logo.addEventListener('click', () => navigate('chat'));
  nav.appendChild(logo);

  // Nav items
  NAV_ITEMS.forEach(item => {
    const btn = document.createElement('button');
    btn.className = 'top-nav-item';
    btn.dataset.page = item.page;
    btn.textContent = `${item.icon} ${item.label}`;
    btn.style.cssText =
      'display:flex;align-items:center;gap:6px;padding:8px 14px;border:none;' +
      'background:transparent;color:#6b7280;font-size:14px;font-weight:500;' +
      'border-radius:8px;cursor:pointer;transition:all 0.15s;white-space:nowrap;';
    btn.addEventListener('click', () => navigate(item.page));
    nav.appendChild(btn);
  });

  // Right spacer
  const spacer = document.createElement('div');
  spacer.style.cssText = 'flex:1;';
  nav.appendChild(spacer);

  // Restart button
  const restartBtn = document.createElement('button');
  restartBtn.id = 'topnav-restart-btn';
  restartBtn.title = '重启服务器';
  restartBtn.innerHTML = '🔄';
  restartBtn.style.cssText =
    'border:none;background:transparent;color:#9ca3af;cursor:pointer;' +
    'font-size:16px;padding:6px 10px;border-radius:6px;transition:all 0.15s;';
  restartBtn.addEventListener('mouseenter', () => { restartBtn.style.background = '#fef3c7'; restartBtn.style.color = '#d97706'; });
  restartBtn.addEventListener('mouseleave', () => { restartBtn.style.background = 'transparent'; restartBtn.style.color = '#9ca3af'; });
  restartBtn.addEventListener('click', restartServer);
  nav.appendChild(restartBtn);

  // Active indicator update
  updateActive(nav, _activePage);

  // Listen for page changes
  window.addEventListener('navigate', ((e: CustomEvent) => {
    _activePage = e.detail.page;
    updateActive(nav, _activePage);
  }) as EventListener);

  return nav;
}

function navigate(page: string): void {
  _activePage = page;
  window.dispatchEvent(new CustomEvent('navigate', { detail: { page } }));
}

function updateActive(nav: HTMLElement, activePage: string): void {
  nav.querySelectorAll('.top-nav-item').forEach(btn => {
    const page = (btn as HTMLElement).dataset.page;
    const isActive = page === activePage;
    (btn as HTMLElement).style.background = isActive ? '#eef2ff' : 'transparent';
    (btn as HTMLElement).style.color = isActive ? '#4f46e5' : '#6b7280';
    (btn as HTMLElement).style.fontWeight = isActive ? '600' : '500';
  });
}

async function restartServer(): Promise<void> {
  const btn = document.getElementById('topnav-restart-btn');
  if (!btn) return;
  btn.textContent = '⏳';
  (btn as HTMLButtonElement).disabled = true;
  try {
    const res = await fetch('/api/system/restart', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      btn.textContent = '✅';
      setTimeout(() => window.location.reload(), 3000);
    } else {
      btn.textContent = '❌';
      setTimeout(() => { btn.textContent = '🔄'; (btn as HTMLButtonElement).disabled = false; }, 2000);
    }
  } catch {
    btn.textContent = '❌';
    setTimeout(() => { btn.textContent = '🔄'; (btn as HTMLButtonElement).disabled = false; }, 2000);
  }
}

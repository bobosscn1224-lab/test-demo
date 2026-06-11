import { apiGet } from '../services/api';
import type { SkillInfo } from '../types';

const t = {
  title: '\u6280\u80fd\u4e2d\u5fc3',
  subtitle: '\u6570\u5b57\u5206\u8eab\u5df2\u5b89\u88c5\u7684\u5bf9\u8bdd\u6280\u80fd\uff0c\u5728\u5bf9\u8bdd\u4e2d\u8f93\u5165\u89e6\u53d1\u8bcd\u5373\u53ef\u81ea\u52a8\u8c03\u7528\u3002',
  loading: '\u52a0\u8f7d\u4e2d...',
  empty: '\u6682\u672a\u5b89\u88c5\u4efb\u4f55\u6280\u80fd',
  failed: '\u65e0\u6cd5\u52a0\u8f7d\u6280\u80fd\u5217\u8868',
  trigger: '\u89e6\u53d1\u8bcd',
  keyword: '\u5173\u952e\u8bcd',
  enabled: '\u5df2\u542f\u7528',
  howToTitle: '\u5982\u4f55\u89e6\u53d1\u6280\u80fd',
  howToBody: '\u5728\u5bf9\u8bdd\u6846\u91cc\u76f4\u63a5\u8f93\u5165\u5bf9\u5e94\u8bed\u53e5\uff0c\u7cfb\u7edf\u4f1a\u81ea\u52a8\u8bc6\u522b\u5e76\u8fdb\u5165\u5bf9\u5e94\u6280\u80fd\u6d41\u7a0b\u3002',
  howToNote: '\u98de\u4e66\u77e5\u8bc6\u5e93\u5bfc\u5165\u5df2\u79fb\u5230\u77e5\u8bc6\u5e93\u9875\u9762\uff0c\u4e0d\u518d\u4f5c\u4e3a\u5bf9\u8bdd\u6280\u80fd\u89e6\u53d1\u3002',
};

export function renderSkillsPage(): HTMLElement {
  const container = document.createElement('div');
  container.className = 'skills-page';
  container.innerHTML = `
    <div class="sk-header">
      <div>
        <h2>${t.title}</h2>
        <p class="sk-subtitle">${t.subtitle}</p>
      </div>
    </div>

    <div id="sk-list" class="sk-list">
      <div class="sk-loading">${t.loading}</div>
    </div>

    <div class="sk-section">
      <h3>${t.howToTitle}</h3>
      <div class="sk-howto">
        <p>${t.howToBody}</p>
        <ul>
          <li><strong>PPT</strong>: \u5e2e\u6211\u505a PPT / \u6839\u636e\u8fd9\u4e2a\u6587\u6863\u751f\u6210 PPT</li>
          <li><strong>\u5468\u62a5</strong>: \u5e2e\u6211\u5199\u5468\u62a5 / \u751f\u6210\u5468\u62a5</li>
          <li><strong>\u98de\u4e66\u5355\u7bc7\u9605\u8bfb</strong>: \u8bfb\u53d6\u98de\u4e66\u6587\u6863 https://xxx.feishu.cn/docx/xxxxx</li>
        </ul>
        <p class="sk-howto-note">${t.howToNote}</p>
      </div>
    </div>
  `;

  loadSkills(container);
  return container;
}

async function loadSkills(container: HTMLElement): Promise<void> {
  const list = container.querySelector('#sk-list');
  if (!list) return;

  try {
    const skills = await apiGet<SkillInfo[]>('/skills/list');
    if (!skills.length) {
      list.innerHTML = `<div class="sk-empty">${t.empty}</div>`;
      return;
    }

    list.innerHTML = skills.map((skill) => `
      <div class="sk-card">
        <div class="sk-card-icon">${getSkillIcon(skill.name)}</div>
        <div class="sk-card-body">
          <div class="sk-card-name">${getSkillDisplayName(skill.name)}</div>
          <div class="sk-card-desc">${esc(skill.description)}</div>
          <div class="sk-card-triggers">
            <span class="sk-trigger-label">${t.trigger}</span>
            ${skill.triggers.map(trigger => `<span class="sk-trigger-tag">${esc(trigger)}</span>`).join('')}
          </div>
          ${(skill.keywords ?? []).length ? `
          <div class="sk-card-keywords">
            <span class="sk-trigger-label">${t.keyword}</span>
            ${(skill.keywords ?? []).map(keyword => `<span class="sk-trigger-tag sk-trigger-tag-secondary">${esc(keyword)}</span>`).join('')}
          </div>` : ''}
          <div class="sk-card-example">${esc(getSkillExample(skill.name))}</div>
        </div>
        <div class="sk-card-status">
          <span class="sk-badge sk-badge-active">${t.enabled}</span>
        </div>
      </div>
    `).join('');
  } catch {
    list.innerHTML = `<div class="sk-empty">${t.failed}</div>`;
  }
}

function getSkillDisplayName(name: string): string {
  const names: Record<string, string> = {
    weekly_report: '\u5468\u62a5\u751f\u6210',
    ppt_maker: 'PPT \u5236\u4f5c',
    feishu_doc_reader: '\u98de\u4e66\u6587\u6863\u9605\u8bfb',
    chat_analyzer: '\u5bf9\u8bdd\u5206\u6790',
  };
  return names[name] || name;
}

function getSkillExample(name: string): string {
  const examples: Record<string, string> = {
    weekly_report: '\u793a\u4f8b\uff1a\u5e2e\u6211\u5199\u5468\u62a5',
    ppt_maker: '\u793a\u4f8b\uff1a\u5e2e\u6211\u505a PPT\uff0c\u7136\u540e\u4e0a\u4f20\u8d44\u6599\u6216\u8f93\u5165\u5185\u5bb9',
    feishu_doc_reader: '\u793a\u4f8b\uff1a\u8bfb\u53d6\u98de\u4e66\u6587\u6863 https://xxx.feishu.cn/docx/xxxxx',
    chat_analyzer: '\u540e\u53f0\u6280\u80fd\uff1a\u81ea\u52a8\u5206\u6790\u5bf9\u8bdd\uff0c\u4e0d\u9700\u8981\u624b\u52a8\u89e6\u53d1',
  };
  return examples[name] || '\u5728\u5bf9\u8bdd\u6846\u8f93\u5165\u89e6\u53d1\u8bcd\u5373\u53ef\u4f7f\u7528\u3002';
}

function getSkillIcon(name: string): string {
  const icons: Record<string, string> = {
    weekly_report: '\u5468',
    ppt_maker: 'PPT',
    feishu_doc_reader: '\u98de',
    chat_analyzer: '\u6790',
  };
  return icons[name] || '\u6280';
}

function esc(s: string): string {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

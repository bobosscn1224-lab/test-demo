/** Skills Center — lists all registered skills with triggers, descriptions, and usage examples. */

import { apiGet } from '../services/api';
import type { SkillInfo } from '../types';

export function renderSkillsPage(): HTMLElement {
  const container = document.createElement('div');
  container.className = 'skills-page';
  container.style.cssText = 'padding:24px 32px;overflow-y:auto;max-width:1000px;margin:0 auto;width:100%;height:100%;';

  container.innerHTML = `
    <div class="sk-header" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;">
      <div>
        <h2 style="font-size:20px;font-weight:700;color:#111827;margin:0;">⚡ 技能中心</h2>
        <p style="color:#9ca3af;font-size:13px;margin:4px 0 0;">已安装的对话技能，在聊天中输入触发词即可自动调用</p>
      </div>
      <button id="sk-refresh-btn" style="padding:8px 16px;border:1px solid #e5e7eb;border-radius:8px;background:#fff;color:#6b7280;cursor:pointer;font-size:13px;">
        🔄 刷新
      </button>
    </div>

    <div id="sk-list" style="display:flex;flex-direction:column;gap:12px;">
      <div style="text-align:center;color:#9ca3af;padding:24px;font-size:14px;">加载中...</div>
    </div>

    <div style="margin-top:24px;padding-top:20px;border-top:1px solid #e5e7eb;">
      <h3 style="font-size:15px;font-weight:600;color:#374151;margin:0 0 10px;">💡 如何使用技能</h3>
      <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px 16px;font-size:13px;color:#92400e;line-height:1.6;">
        <p style="margin:0 0 8px;">在聊天框直接输入触发词，系统会自动识别并进入对应技能流程：</p>
        <ul style="margin:6px 0 0;padding-left:18px;">
          <li style="margin-bottom:4px;"><strong>周报</strong>：写周报 / 生成周报 / 帮我写周报</li>
          <li style="margin-bottom:4px;"><strong>PPT制作</strong>：做PPT / 生成PPT / 制作PPT</li>
          <li style="margin-bottom:4px;"><strong>图片生成</strong>：生成图片 / 画一张 / AI画图</li>
          <li style="margin-bottom:4px;"><strong>飞书文档</strong>：读取飞书文档 + 链接</li>
          <li style="margin-bottom:4px;"><strong>飞书妙记</strong>：读取妙记 / 会议纪要 + 链接</li>
        </ul>
        <p style="margin:8px 0 0;color:#78350f;font-size:12px;">💡 飞书知识库导入已迁移到知识库页面；周报和图片生成也可直接使用独立功能页面。</p>
      </div>
    </div>
  `;

  loadSkills(container);
  bindEvents(container);
  return container;
}

function bindEvents(container: HTMLElement): void {
  container.querySelector('#sk-refresh-btn')?.addEventListener('click', () => loadSkills(container));
}

async function loadSkills(container: HTMLElement): Promise<void> {
  const list = container.querySelector('#sk-list');
  if (!list) return;

  try {
    const skills = await apiGet<SkillInfo[]>('/skills/list');
    if (!skills.length) {
      list.innerHTML = '<div style="text-align:center;color:#9ca3af;padding:24px;font-size:14px;">暂无可用技能</div>';
      return;
    }

    list.innerHTML = skills.map((skill) => {
      const info = getSkillInfo(skill.name);
      return `
      <div style="display:flex;align-items:flex-start;gap:14px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
        <div style="font-size:24px;flex-shrink:0;width:48px;height:48px;display:flex;align-items:center;justify-content:center;background:#eef2ff;border-radius:10px;">${info.icon}</div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:15px;font-weight:700;color:#1f2937;margin-bottom:2px;">${info.name}</div>
          <div style="font-size:13px;color:#6b7280;margin-bottom:8px;">${esc(skill.description)}</div>
          <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;margin-top:4px;">
            <span style="font-size:11px;color:#9ca3af;margin-right:2px;">触发词</span>
            ${skill.triggers.map(t => `<span style="display:inline-block;background:#ede9fe;color:#5b21b6;padding:2px 8px;border-radius:6px;font-size:11px;">${esc(t)}</span>`).join('')}
          </div>
          ${(skill.keywords ?? []).length ? `
          <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;margin-top:4px;">
            <span style="font-size:11px;color:#9ca3af;margin-right:2px;">关键词</span>
            ${(skill.keywords ?? []).map(k => `<span style="display:inline-block;background:#f3f4f6;color:#6b7280;padding:2px 8px;border-radius:6px;font-size:11px;">${esc(k)}</span>`).join('')}
          </div>` : ''}
          <div style="margin-top:8px;color:#4f46e5;background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px;padding:7px 9px;font-size:12px;">${info.example}</div>
        </div>
        <div style="flex-shrink:0;">
          <span style="display:inline-block;padding:4px 10px;border-radius:20px;font-size:11px;font-weight:600;background:#ecfdf5;color:#065f46;">已启用</span>
        </div>
      </div>`;
    }).join('');
  } catch {
    list.innerHTML = '<div style="text-align:center;color:#ef4444;padding:24px;font-size:14px;">加载失败，请点击刷新重试</div>';
  }
}

// ── Skill metadata ────────────────────────────────────────────

interface SkillMeta {
  name: string;
  icon: string;
  example: string;
}

function getSkillInfo(skillName: string): SkillMeta {
  const registry: Record<string, SkillMeta> = {
    weekly_report: {
      name: '周报生成',
      icon: '📊',
      example: '在聊天框输入「写周报」「生成周报」即可启动。也支持独立页面表单式生成。',
    },
    ppt_maker: {
      name: 'PPT 制作',
      icon: '📽',
      example: '输入「做PPT」或「生成PPT」，上传资料或大纲，通过4步流程生成专业PPT。',
    },
    feishu_doc_reader: {
      name: '飞书文档阅读',
      icon: '📄',
      example: '发送飞书文档/wiki链接即可读取内容，支持总结、分析、生成PPT大纲、保存到知识库。',
    },
    feishu_minutes_reader: {
      name: '飞书妙记阅读',
      icon: '🎙',
      example: '发送飞书妙记链接即可读取会议转写文本，支持总结、提取要点、生成PPT大纲。',
    },
    image_gen: {
      name: 'AI 图片生成',
      icon: '🎨',
      example: '输入「生成图片」「画一张」+ 描述即可生成。也支持独立页面直接生成。',
    },
  };
  return registry[skillName] || {
    name: skillName,
    icon: '⚡',
    example: '在聊天框中输入触发词即可使用此技能。',
  };
}

function esc(s: string): string {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

/** Step 0: Project list rendering, loading, card building, and event binding. */

import { apiGet, apiDelete } from '../../services/api';
import { state, resetForm, resumeProject } from './state';
import { esc, btn, toast } from './utils';
import { navigateTo } from './navigation';
import type { Project } from './types';

export function renderProjectList(el: HTMLElement): void {
  el.className = 'max-w-4xl mx-auto w-full p-6';

  const header = document.createElement('div');
  header.className = 'flex items-center justify-between mb-6';
  header.innerHTML = `
    <div>
      <h2 class="text-xl font-bold text-gray-800">PPT 制作</h2>
      <p class="text-sm text-gray-500 mt-1">管理你的 PPT 项目，逐步完成从需求到成品的全流程</p>
    </div>
  `;
  header.appendChild(btn('+ 新建项目', 'px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors', () => {
    resetForm();
    navigateTo(1);
  }));
  el.appendChild(header);

  const listWrap = document.createElement('div');
  listWrap.id = 'ppt-project-list';
  listWrap.innerHTML = '<div class="text-center text-gray-400 py-12">加载中...</div>';
  el.appendChild(listWrap);

  loadProjects(listWrap);
}

async function loadProjects(listWrap: HTMLElement): Promise<void> {
  try {
    state.projects = await apiGet<Project[]>('/v1/ppt-maker/projects/');
    if (!state.projects.length) {
      listWrap.innerHTML = `
        <div class="text-center py-16">
          <div class="text-6xl mb-4">📽</div>
          <p class="text-gray-500 mb-4">还没有 PPT 项目</p>
          <button id="ppt-create-first" class="px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors">创建第一个项目</button>
        </div>`;
      listWrap.querySelector('#ppt-create-first')?.addEventListener('click', () => {
        resetForm();
        navigateTo(1);
      });
      return;
    }
    listWrap.innerHTML = `<div class="grid gap-3">${state.projects.map(p => projectCard(p)).join('')}</div>`;
    bindProjectCards(listWrap);
  } catch (e: any) {
    listWrap.innerHTML = `<div class="text-center text-red-500 py-12">加载失败：${esc(e.message || e)}</div>`;
  }
}

function projectCard(p: Project): string {
  const statusColors: Record<string, string> = {
    created: '#f3f4f6,#6b7280',
    content_added: '#dbeafe,#1d4ed8',
    outlined: '#fef3c7,#92400e',
    collage_selected: '#ede9fe,#5b21b6',
    pages_generated: '#d1fae5,#065f46',
    done: '#ecfdf5,#065f46',
  };
  const [bg, color] = (statusColors[p.status] || '#f3f4f6,#6b7280').split(',');
  const statusLabel: Record<string, string> = {
    created: '待填写',
    content_added: '已添加素材',
    outlined: '大纲已生成',
    collage_selected: '风格已选',
    pages_generated: '逐页已生成',
    done: '已完成',
  };
  const dateStr = p.created_at ? new Date(p.created_at).toLocaleDateString('zh-CN') : '';
  return `
    <div class="ppt-project-card flex items-center gap-4 bg-white border border-gray-200 rounded-xl p-4 hover:border-indigo-300 hover:shadow-sm transition-all" data-id="${esc(p.id)}">
      <div class="w-10 h-10 rounded-lg flex items-center justify-center text-xl flex-shrink-0" style="background:${bg};color:${color};">📽</div>
      <div class="flex-1 min-w-0">
        <div class="font-semibold text-gray-800 text-sm">${esc(p.name)}</div>
        <div class="flex items-center gap-2 mt-1">
          <span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium" style="background:${bg};color:${color};">${statusLabel[p.status] || p.status}</span>
          ${dateStr ? `<span class="text-xs text-gray-400">${dateStr}</span>` : ''}
        </div>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
        <button class="ppt-continue-btn px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-lg text-xs font-semibold hover:bg-indigo-100 transition-colors" data-id="${esc(p.id)}">继续</button>
        <button class="ppt-delete-btn px-3 py-1.5 bg-red-50 text-red-600 rounded-lg text-xs font-semibold hover:bg-red-100 transition-colors" data-id="${esc(p.id)}">删除</button>
      </div>
    </div>`;
}

function bindProjectCards(listWrap: HTMLElement): void {
  listWrap.querySelectorAll('.ppt-continue-btn').forEach(b => {
    b.addEventListener('click', () => {
      state.projectId = (b as HTMLElement).dataset.id || null;
      if (state.projectId) resumeProject(state.projectId);
    });
  });
  listWrap.querySelectorAll('.ppt-delete-btn').forEach(b => {
    b.addEventListener('click', async () => {
      const id = (b as HTMLElement).dataset.id;
      if (!id || !confirm('确定要删除这个项目吗？')) return;
      try {
        await apiDelete(`/v1/ppt-maker/projects/${id}/`);
        toast('项目已删除');
        loadProjects(document.getElementById('ppt-project-list')!);
      } catch (e: any) {
        toast('删除失败：' + (e.message || e), 'error');
      }
    });
  });
}

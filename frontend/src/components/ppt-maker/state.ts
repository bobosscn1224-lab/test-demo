/** Central state store and state-mutating functions for the PPT Maker. */

import { apiGet } from '../../services/api';
import { reRender } from './navigation';
import { _label, toast } from './utils';
import type { Project, ProjectDetail, OutlinePage, Collage, PageImage } from './types';

export const state = {
  currentStep: 0,
  projectId: null as string | null,
  projects: [] as Project[],
  projectDetail: null as ProjectDetail | null,

  // Step 1 form state
  formName: '',
  formScenario: '业务汇报' as string,
  formAudience: '老板管理层' as string,
  formScale: '精简8-12页' as string,
  formStyles: [] as string[],
  formMessages: '',
  // COSTAR fields
  formNarrativeStyle: 'auto' as string,
  formNarrativeFramework: 'auto' as string,
  formObjective: 'auto' as string,
  formTone: 'auto' as string,

  // Step 2 state
  activeContentTab: 'upload' as string,
  useKnowledgeBase: true,
  knowledgeBaseDirs: [] as string[],
  feishuUrls: [] as string[],
  importedFeishuDocs: [] as {url: string, title: string, content?: string}[],
  contentFiles: [] as File[],
  pastedText: '',

  // Step 3 state
  outlineMode: 'conservative' as string,  // 'conservative' | 'enhanced'
  outlinePages: [] as OutlinePage[],
  outlineSaved: false,  // true once user has explicitly saved
  selectedOutlineIdx: 0 as number,
  editingOutlineIdx: null as number | null,

  // Step 4 state
  collages: [] as Collage[],
  selectedCollageIdx: null as number | null,
  generatingCollages: false,

  // Step 5 state
  pageImages: [] as PageImage[],
  generatingPages: false,
  generatingPageNum: 0,
  totalPagesToGenerate: 0,
  pageRegenInputs: {} as Record<number, string>,

  // Loading flags
  loading: false,
};

export function resetForm(): void {
  state.formName = '';
  state.formScenario = '业务汇报';
  state.formAudience = '老板管理层';
  state.formScale = '精简8-12页';
  state.formStyles = [];
  state.formMessages = '';
  state.formNarrativeStyle = 'auto';
  state.formNarrativeFramework = 'auto';
  state.formObjective = 'auto';
  state.formTone = 'auto';
  state.projectId = null;
  state.projectDetail = null;
  state.contentFiles = [];
  state.pastedText = '';
  state.outlinePages = [];
  state.editingOutlineIdx = null;
  state.collages = [];
  state.selectedCollageIdx = null;
  state.generatingCollages = false;
  state.pageImages = [];
  state.generatingPages = false;
  state.generatingPageNum = 0;
  state.totalPagesToGenerate = 0;
  state.pageRegenInputs = {};
  state.loading = false;
}

export async function resumeProject(id: string): Promise<void> {
  state.loading = true;
  reRender();
  try {
    state.projectDetail = await apiGet<ProjectDetail>(`/v1/ppt-maker/projects/${id}/`);
    // Determine step from status
    const statusStep: Record<string, number> = {
      created: 1,
      content_added: 2,
      outline_generated: 3,
      outline_confirmed: 3,
      collages_generated: 4,
      pages_generated: 5,
      completed: 6,
    };
    state.currentStep = statusStep[state.projectDetail.status] ?? 1;
    // Restore form state — map English backend values to Chinese UI labels
    state.formName = state.projectDetail.name || '';
    if (state.projectDetail.purpose) state.formScenario = _label('purpose', state.projectDetail.purpose);
    if (state.projectDetail.audience) state.formAudience = _label('audience', state.projectDetail.audience);
    if (state.projectDetail.scale) state.formScale = _label('scale', state.projectDetail.scale);
    if (state.projectDetail.styles) state.formStyles = state.projectDetail.styles.map((s: string) => _label('style', s));
    if (state.projectDetail.key_message) state.formMessages = state.projectDetail.key_message;
    if (state.projectDetail.narrative_style) state.formNarrativeStyle = state.projectDetail.narrative_style;
    if (state.projectDetail.narrative_framework) state.formNarrativeFramework = state.projectDetail.narrative_framework;
    if (state.projectDetail.objective) state.formObjective = state.projectDetail.objective;
    if (state.projectDetail.tone) state.formTone = state.projectDetail.tone;
    if (state.projectDetail.image_backend) (state as any)._imageBackend = state.projectDetail.image_backend;
    // Restore step 2 content
    if (state.projectDetail.content_text) state.pastedText = state.projectDetail.content_text;
    if (state.projectDetail.content_files?.length) {
      state.contentFiles = [];  // clear any temp files, show saved ones
    }
    // Restore outline pages — from new outline_pages field, or legacy pages, or parse text
    if (state.projectDetail.outline_pages?.length) {
      state.outlinePages = state.projectDetail.outline_pages;
    } else if (state.projectDetail.pages?.length) {
      // Legacy compat
      state.outlinePages = state.projectDetail.pages.filter(
        (p: any) => p.type || p.points || p.core_message
      );
    }
    if (state.outlinePages.length === 0 && state.projectDetail.outline) {
      state.outlinePages = _parseOutlineText(state.projectDetail.outline);
    }
    if (state.outlinePages.length > 0) {
      state.outlineSaved = true;
    }

    // Restore page images — from new page_images field, or legacy pages
    if (state.projectDetail.page_images?.length) {
      state.pageImages = state.projectDetail.page_images.map((p: any) => ({
        page_num: p.page_num || p.index || 0,
        title: p.title || '',
        filename: p.filename || '',
        download_url: p.download_url || `/api/skills/download/${p.filename}`,
      }));
    } else if (state.projectDetail.pages?.length) {
      const imgEntries = state.projectDetail.pages.filter(
        (p: any) => p.filename && !p.type && !p.points
      );
      if (imgEntries.length > 0) {
        state.pageImages = imgEntries.map((p: any) => ({
          page_num: p.page_num || p.index || 0,
          title: p.title || '',
          filename: p.filename || '',
          download_url: p.download_url || `/api/skills/download/${p.filename}`,
        }));
      }
    }
    if (state.projectDetail.outline_mode) {
      state.outlineMode = state.projectDetail.outline_mode;
    }
    if (state.projectDetail.collages?.length) {
      state.collages = state.projectDetail.collages.map((c: any) => ({
        ...c,
        download_url: c.download_url || `/api/skills/download/${c.filename}`,
      }));
    }
    // selected_collage is "A"/"B"/"C" — convert to index
    if (state.projectDetail.selected_collage) {
      const labels = ['A', 'B', 'C'];
      state.selectedCollageIdx = labels.indexOf(state.projectDetail.selected_collage);
      if (state.selectedCollageIdx < 0) state.selectedCollageIdx = null;
    }
    state.loading = false;
    reRender();
  } catch (e: any) {
    state.loading = false;
    toast('加载项目失败：' + (e.message || e), 'error');
    reRender();
  }
}

// ── Outline text parser (fallback when project.pages has no structured data)

function _parseOutlineText(text: string): OutlinePage[] {
  const pages: OutlinePage[] = [];
  // Split by "### 第N页" or "第N页" markers
  const sections = text.split(/\n(?=#{1,4}\s*第\s*\d+\s*页|第\s*\d+\s*页[:：])/);
  for (const section of sections) {
    const trimmed = section.trim();
    if (!trimmed || trimmed.length < 10) continue;
    const numMatch = trimmed.match(/第\s*(\d+)\s*页/);
    if (!numMatch) continue;
    const pageNum = parseInt(numMatch[1]);
    // Extract title: first meaningful line after the page marker
    const lines = trimmed.split('\n').filter(l => l.trim());
    const titleLine = lines.find(l => l.includes('标题') || l.includes('**')) || lines[0] || '';
    const title = titleLine.replace(/^#{1,4}\s*第\s*\d+\s*页[:：]?\s*/, '').replace(/\*\*/g, '').trim() || `第${pageNum}页`;
    pages.push({
      page_num: pageNum,
      type: pageNum === 1 ? 'cover' : 'content',
      title,
      role: '',
      core_message: '',
      points: [],
      visual_hint: '',
    });
  }
  return pages.sort((a, b) => a.page_num - b.page_num);
}

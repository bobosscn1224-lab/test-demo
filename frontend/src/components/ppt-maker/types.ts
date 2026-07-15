/** Shared types and constants for the PPT Maker multi-step tool. */

// ── Interfaces (must match backend models.py) ──────────────────────────
//
// State machine: created → content_added → outline_generated
//   → outline_confirmed → collages_generated → pages_generated → completed

export interface Project {
  id: string;
  name: string;
  purpose: string;
  audience: string;
  scale: string;
  styles: string[];
  key_message: string;
  narrative_style: string;
  narrative_framework: string;
  objective: string;
  tone: string;
  status: string;
  created_at: string;
  updated_at: string;
  outline: string;
  outline_mode: string;
  selected_collage: string;
  content_text: string;
  content_files: any[];
  outline_pages: OutlinePage[];
  collages: any[];
  page_images: any[];
  pages: any[];  // legacy
}

export interface OutlinePage {
  page_num: number;
  type: string;
  title: string;
  role: string;
  core_message: string;
  points: string[];
  visual_hint: string;
}

export interface OutlineResponse {
  success: boolean;
  project_id: string;
  outline: string;
  pages: OutlinePage[];
  message: string;
}

export interface Collage {
  label: string;
  filename: string;
  download_url: string;
}

export interface PageImage {
  page_num: number;
  title: string;
  filename: string;
  download_url: string;
}

export type ProjectDetail = Project;

// ── Constants ───────────────────────────────────────────────────────────

export const STEPS = [
  { index: 0, label: '项目',  icon: '📋' },
  { index: 1, label: '需求',  icon: '📝' },
  { index: 2, label: '素材',  icon: '📎' },
  { index: 3, label: '大纲',  icon: '📑' },
  { index: 4, label: '风格',  icon: '🎨' },
  { index: 5, label: '逐页',  icon: '🖼' },
  { index: 6, label: '完成',  icon: '✅' },
];

export const SCENARIOS = ['业务汇报', '项目方案', '产品宣讲', '培训辅导', '复盘总结', '故事路演', '其他'];
export const AUDIENCES = ['老板管理层', '客户合作方', '一线团队', '投资人', '混合'];
export const SCALES = ['精简8-12页', '标准15-20页', '完整25-35页'];
export const STYLE_OPTIONS = [
  { key: '专业严谨', label: '专业严谨', desc: 'consulting report style' },
  { key: '科技感',   label: '科技感',   desc: 'tech keynote style' },
  { key: '简约商务', label: '简约商务', desc: 'editorial business' },
  { key: '创意活泼', label: '创意活泼', desc: 'creative bold' },
  { key: '高端大气', label: '高端大气', desc: 'luxury premium' },
];

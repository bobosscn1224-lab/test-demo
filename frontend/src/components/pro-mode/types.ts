/** Pro Mode — shared TypeScript types.
 *
 *  Workflow: Script → Extract Resources → Generate Images → Storyboard → Director → Shot-by-Shot
 */

// ── Step 1: Script Analysis ──────────────────────────────────────

export interface ExtractedCharacter {
  id: string;
  name: string;
  description: string;
  traits: string[];
  image_prompt: string;
  generated_image_url: string;
  asset_id: string;
  status: 'pending' | 'generating' | 'done' | 'failed';
}

export interface ExtractedScene {
  id: string;
  name: string;
  description: string;
  time_of_day: string;
  image_prompt: string;
  generated_image_url: string;
  asset_id: string;
  status: 'pending' | 'generating' | 'done' | 'failed';
}

export interface ExtractedProp {
  id: string;
  name: string;
  description: string;
  image_prompt: string;
  generated_image_url: string;
  asset_id: string;
  status: 'pending' | 'generating' | 'done' | 'failed';
}

export interface Project {
  id: string;
  title: string;
  genre: string;
  summary: string;
  script: string;
  characters: ExtractedCharacter[];
  scenes: ExtractedScene[];
  props: ExtractedProp[];
  shots: Shot[];
  director_config: DirectorConfig | null;
  current_step: number;
  created_at: string;
  updated_at: string;
  // ── Optional fields (used by specific steps) ──
  raw_story?: string;
  template?: string;
  structured_script?: string;
  consistency_bible?: string;
  composed_video_path?: string;
}

// ── Project Summary (for dashboard list) ─────────────────────────

export interface ProjectSummary {
  id: string;
  title: string;
  genre: string;
  summary: string;
  char_count: number;
  scene_count: number;
  shot_count: number;
  current_step: number;
  created_at: string;
}

// ── Step 3: Storyboard ───────────────────────────────────────────

export interface Shot {
  shot_number: number;
  description: string;
  character_ids: string[];
  scene_id: string;
  prop_ids: string[];
  camera: string;
  duration: number;
  dialogue: string;
  mood: string;
  // ── 镜头级状态机字段（后端维护，前端只读回传）──
  frame_status?: 'pending' | 'generating' | 'done' | 'failed' | 'stale';
  frame_image_url?: string;
  video_status?: 'pending' | 'queued' | 'succeeded' | 'failed' | 'stale';
  task_id?: string;
  video_path?: string;
  video_url?: string;
  last_frame_url?: string;
  error?: string;
}

// ── Step 4: Director ─────────────────────────────────────────────

export interface DirectorConfig {
  pace: string;
  performance_style: string;
  color_tone: string;
  transitions: string;
  overall_note: string;
}

// ── Step 5: Generation ───────────────────────────────────────────

export interface ShotTask {
  shot_number: number;
  task_id?: string;
  status: 'pending' | 'queued' | 'succeeded' | 'failed' | 'stale';
  prompt?: string;
  error?: string;
  video_url?: string;
  video_path?: string;
  last_frame_url?: string;
  frame_image_url?: string;
  frame_status?: 'pending' | 'generating' | 'done' | 'failed' | 'stale';
}

// ── Step labels ──────────────────────────────────────────────────

export const STEP_LABELS: Record<number, { icon: string; title: string; desc: string }> = {
  0: { icon: '📝', title: '剧本结构化', desc: '小说→标准剧本+模板' },
  1: { icon: '🎨', title: '资源生成', desc: '定妆照+场景+道具' },
  2: { icon: '📋', title: '分镜计划', desc: '逐镜拆解+关联资源' },
  3: { icon: '🎬', title: '导演台', desc: 'AI 综合导演建议' },
  4: { icon: '🚀', title: '逐镜生成', desc: '一镜一镜生成视频' },
  5: { icon: '🎞', title: '自动成片', desc: '拼接+字幕+导出' },
};

export const TEMPLATE_LIST = [
  { key: '', label: '无模板（自由创作）', icon: '✨' },
  { key: '甜恋', label: '甜恋', icon: '💕' },
  { key: '悬疑', label: '悬疑', icon: '🔍' },
  { key: '校园', label: '校园', icon: '🏫' },
  { key: '都市', label: '都市', icon: '🏙' },
  { key: '古风', label: '古风', icon: '🏯' },
  { key: '治愈', label: '治愈', icon: '🌿' },
];

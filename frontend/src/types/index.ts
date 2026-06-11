export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  audioPath?: string;
  createdAt?: string;
}

export interface Session {
  id: string;
  title: string;
  personaId?: string;
  isArchived: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface Persona {
  id: string;
  name: string;
  slug: string;
  description: string;
  avatarUrl: string;
  voiceId: string;
  isActive: boolean;
  configJson: Record<string, unknown>;
}

export interface SSEChatEvent {
  type: 'token' | 'done' | 'error';
  data: string;
}

export interface ChatDoneData {
  sessionId: string;
  tokensIn?: number;
  tokensOut?: number;
}

export interface KnowledgeStats {
  status: string;
  total_chunks: number;
  unique_docs: number;
  watch_dirs: string[];
  is_watching: boolean;
}

export interface KnowledgeResult {
  content: string;
  metadata: Record<string, unknown>;
  score: number;
}

export interface ScanResult {
  status: string;
  added: number;
  updated: number;
  reindexed: number;
  skipped: number;
  scanned: number;
  total_files?: number;
  deleted: number;
  errors: number;
  failed_files?: string[];
  total_chunks: number;
  unique_docs: number;
}

export interface ScanTaskStatus extends ScanResult {
  task_id: string;
  state: 'running' | 'completed' | 'failed';
  force: boolean;
  current_file?: string;
  error?: string;
  started_at?: string;
  updated_at?: string;
  finished_at?: string;
}

export interface SkillInfo {
  name: string;
  description: string;
  triggers: string[];
  keywords?: string[];
}

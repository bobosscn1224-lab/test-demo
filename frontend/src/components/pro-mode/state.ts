/** Pro Mode — centralized state (project-based, with persistence). */

import type { Project } from './types';

// ── View mode: list (dashboard) or workflow ──────────────────────
let _viewMode: 'list' | 'workflow' = 'list';

export function getViewMode(): 'list' | 'workflow' { return _viewMode; }
export function setViewMode(mode: 'list' | 'workflow'): void { _viewMode = mode; }

// ── Current step (1-5) ──────────────────────────────────────────
let _currentStep = 0;

export function getCurrentStep(): number { return _currentStep; }
export function setCurrentStep(step: number): void { if (step >= 0 && step <= 5) _currentStep = step; }

const _stepReady: Record<number, boolean> = { 0: false, 1: false, 2: false, 3: false, 4: false, 5: false };
export function isStepReady(step: number): boolean { return _stepReady[step] ?? false; }
export function markStepReady(step: number): void { _stepReady[step] = true; }

// ── Current project ──────────────────────────────────────────────
let _project: Project | null = null;

export function getProject(): Project | null { return _project; }
export function setProject(p: Project | null): void {
  _project = p;
  // When loading a project, restore step readiness based on current_step
  if (p) {
    _currentStep = p.current_step || 1;
    for (let i = 0; i <= 5; i++) _stepReady[i] = (i < (p.current_step || 0));
  }
}

// ── Project summaries (for dashboard) ────────────────────────────
export interface ProjectSummary {
  id: string; title: string; genre: string; summary: string;
  char_count: number; scene_count: number; shot_count: number;
  current_step: number; created_at: string;
}

let _projects: ProjectSummary[] = [];

export function getProjectSummaries(): ProjectSummary[] { return _projects; }
export function setProjectSummaries(list: ProjectSummary[]): void { _projects = list; }

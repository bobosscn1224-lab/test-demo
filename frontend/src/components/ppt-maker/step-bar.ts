/** Step indicator bar — build + update. */

import { state } from './state';
import { STEPS } from './types';

export function buildStepBar(navigate: (step: number) => void): HTMLElement {
  const bar = document.createElement('div');
  bar.id = 'ppt-step-bar';
  bar.className = 'flex items-center gap-1 px-4 py-3 bg-white border-b border-gray-200 flex-shrink-0 overflow-x-auto';
  STEPS.forEach((s, i) => {
    const btn = document.createElement('button');
    btn.className = 'ppt-step-btn flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors border';
    btn.style.cssText = 'background:#f3f4f6;color:#9ca3af;border-color:#e5e7eb;cursor:default;';
    btn.textContent = `${s.icon} ${s.label}`;
    btn.dataset.step = String(i);
    btn.addEventListener('click', () => {
      if (i <= state.currentStep) {
        navigate(i);
      }
    });
    bar.appendChild(btn);

    if (i < STEPS.length - 1) {
      const arrow = document.createElement('span');
      arrow.className = 'text-gray-300 text-xs flex-shrink-0';
      arrow.textContent = '→';
      arrow.dataset.arrow = String(i);
      bar.appendChild(arrow);
    }
  });
  return bar;
}

export function updateStepBar(): void {
  const bar = document.getElementById('ppt-step-bar');
  if (!bar) return;
  const btns = bar.querySelectorAll('.ppt-step-btn');
  const arrows = bar.querySelectorAll('[data-arrow]');
  btns.forEach((btn, i) => {
    const b = btn as HTMLElement;
    if (i === state.currentStep) {
      b.style.background = '#eef2ff';
      b.style.color = '#4f46e5';
      b.style.borderColor = '#a5b4fc';
      b.style.cursor = 'default';
      b.style.fontWeight = '700';
    } else if (i < state.currentStep) {
      b.style.background = '#ecfdf5';
      b.style.color = '#065f46';
      b.style.borderColor = '#a7f3d0';
      b.style.cursor = 'pointer';
      b.style.fontWeight = '600';
    } else {
      b.style.background = '#f3f4f6';
      b.style.color = '#9ca3af';
      b.style.borderColor = '#e5e7eb';
      b.style.cursor = 'default';
      b.style.fontWeight = '500';
    }
  });
  arrows.forEach((a, i) => {
    const el = a as HTMLElement;
    el.style.color = i < state.currentStep ? '#6ee7b7' : '#d1d5db';
  });
}

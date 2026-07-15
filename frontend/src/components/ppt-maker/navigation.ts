/** Navigation helpers to avoid circular dependencies between step modules. */

let _navigateTo: ((step: number) => void) | null = null;
let _reRender: (() => void) | null = null;

export function setNavigateTo(fn: (step: number) => void): void { _navigateTo = fn; }
export function navigateTo(step: number): void { _navigateTo?.(step); }

export function setReRender(fn: () => void): void { _reRender = fn; }
export function reRender(): void { _reRender?.(); }

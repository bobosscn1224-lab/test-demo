export type AvatarState = 'idle' | 'speaking' | 'listening';

const ANIM_CLASS: Record<AvatarState, string> = {
  idle: 'avatar-idle',
  speaking: 'avatar-speaking',
  listening: 'avatar-listening',
};

const STATUS_TEXT: Record<AvatarState, string> = {
  idle: '在线',
  speaking: '正在说话...',
  listening: '正在聆听...',
};

export function renderAvatar(container: HTMLElement, state: AvatarState = 'idle'): void {
  container.innerHTML = `
    <div class="flex flex-col items-center gap-1.5">
      <div id="avatar-anim" class="relative w-16 h-16 ${ANIM_CLASS[state]}">
        <div class="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-2xl font-bold shadow-md">
          🤖
        </div>
      </div>
      <div class="text-xs text-gray-400" id="avatar-status">${STATUS_TEXT[state]}</div>
    </div>
  `;
}

export function setAvatarState(state: AvatarState): void {
  const anim = document.getElementById('avatar-anim');
  if (anim) {
    anim.className = `relative w-16 h-16 ${ANIM_CLASS[state]}`;
  }
  const status = document.getElementById('avatar-status');
  if (status) {
    status.textContent = STATUS_TEXT[state];
  }
}

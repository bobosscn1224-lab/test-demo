import type { Message } from '../types';

function esc(s: string): string {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function formatMarkdown(text: string): string {
  return esc(text)
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

export function createUserBubble(msg: Message): HTMLElement {
  const row = document.createElement('div');
  row.className = 'flex justify-end mb-4';
  row.dataset.messageId = msg.id;

  const wrapper = document.createElement('div');
  wrapper.className = 'max-w-[75%] order-1';

  const bubble = document.createElement('div');
  bubble.className = 'px-4 py-2.5 rounded-2xl bg-indigo-500 text-white rounded-br-md';
  bubble.textContent = msg.content;

  const avatar = document.createElement('div');
  avatar.className = 'w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center text-white text-sm flex-shrink-0 ml-2 mt-1';
  avatar.textContent = '👤'; // 👤

  wrapper.appendChild(bubble);
  row.appendChild(wrapper);
  row.appendChild(avatar);
  return row;
}

export function createAssistantBubble(msg: Message, isStreaming: boolean): HTMLElement {
  const row = document.createElement('div');
  row.className = 'flex justify-start mb-4';
  row.dataset.messageId = msg.id;

  const avatar = document.createElement('div');
  avatar.className = 'w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-sm flex-shrink-0 mr-2 mt-1';
  avatar.textContent = '🤖'; // 🤖

  const wrapper = document.createElement('div');
  wrapper.className = 'max-w-[75%]';

  if (isStreaming && !msg.content) {
    const thinking = document.createElement('div');
    thinking.className = 'thinking-status';
    thinking.innerHTML = '<span>思考中</span><span class="thinking-dots"><i></i><i></i><i></i></span>';
    wrapper.appendChild(thinking);
  }

  const bubble = document.createElement('div');
  bubble.className = 'px-4 py-2.5 rounded-2xl bg-gray-100 text-gray-800 rounded-bl-md message-content';
  bubble.id = 'bubble-' + msg.id;

  if (msg.content) {
    bubble.innerHTML = isStreaming ? esc(msg.content).replace(/\n/g, '<br>') : formatMarkdown(msg.content);
  } else {
    bubble.innerHTML = '<span class="thinking-dots"><i></i><i></i><i></i></span>';
  }

  wrapper.appendChild(bubble);
  row.appendChild(avatar);
  row.appendChild(wrapper);
  return row;
}

export function updateStreamingBubble(msgId: string, content: string): void {
  const bubble = document.getElementById('bubble-' + msgId);
  if (!bubble) return;

  // Remove thinking indicator if present
  const row = bubble.closest('[data-message-id]');
  if (row) {
    const thinking = row.querySelector('.thinking-status');
    if (thinking) thinking.remove();
  }

  // Plain text during streaming — no markdown, no innerHTML risks
  bubble.textContent = '';
  const lines = content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (i > 0) bubble.appendChild(document.createElement('br'));
    bubble.appendChild(document.createTextNode(lines[i]));
  }
}

export function finalizeStreamingBubble(msgId: string, content: string): void {
  const bubble = document.getElementById('bubble-' + msgId);
  if (!bubble) return;

  // Remove thinking indicator
  const row = bubble.closest('[data-message-id]');
  if (row) {
    const thinking = row.querySelector('.thinking-status');
    if (thinking) thinking.remove();
  }

  // Final render with markdown
  bubble.innerHTML = content ? formatMarkdown(content) : '';
}

export function renderMessageHTML(msg: Message): string {
  const isUser = msg.role === 'user';
  const empty = !msg.content;
  const body = empty ? '' : (isUser ? esc(msg.content) : formatMarkdown(msg.content));

  const avatar = isUser
    ? '<div class="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center text-white text-sm flex-shrink-0 ml-2 mt-1">👤</div>'
    : '<div class="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-sm flex-shrink-0 mr-2 mt-1">🤖</div>';

  const bubbleClass = isUser
    ? 'bg-indigo-500 text-white rounded-br-md'
    : 'bg-gray-100 text-gray-800 rounded-bl-md';

  const think = (!isUser && empty)
    ? '<div class="thinking-status"><span>思考中</span><span class="thinking-dots"><i></i><i></i><i></i></span></div>'
    : '';

  const inner = body || (isUser ? '' : '<span class="thinking-dots"><i></i><i></i><i></i></span>');

  return [
    '<div class="flex ' + (isUser ? 'justify-end' : 'justify-start') + ' mb-4" data-message-id="' + msg.id + '">',
    isUser ? '' : avatar,
    '<div class="max-w-[75%] ' + (isUser ? 'order-1' : '') + '">',
    think,
    '<div class="px-4 py-2.5 rounded-2xl message-content ' + bubbleClass + '" id="bubble-' + msg.id + '">' + inner + '</div>',
    '</div>',
    isUser ? avatar : '',
    '</div>',
  ].join('');
}

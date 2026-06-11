function safeCallback(fn: () => void): void {
  try { fn(); } catch { /* callback error must not break the stream */ }
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onDone: (sessionId: string) => void;
  onError: (error: string) => void;
  onSkill: (data: { skill: string; message: string; data?: Record<string, unknown>; follow_up_action?: string }, sessionId: string) => void;
}

async function consumeChatStream(response: Response, callbacks: StreamCallbacks): Promise<void> {
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finished = false;
  let lastSessionId = '';
  let sawDone = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;

      let event;
      try {
        event = JSON.parse(line.slice(6));
      } catch {
        continue; // skip parse errors for incomplete chunks
      }

      if (event.type === 'token') {
        safeCallback(() => callbacks.onToken(event.data));
      } else if (event.type === 'done') {
        finished = true;
        sawDone = true;
        const sid = (event.data && typeof event.data === 'object') ? event.data.session_id : '';
        lastSessionId = sid || lastSessionId;
        safeCallback(() => callbacks.onDone(sid || ''));
      } else if (event.type === 'error') {
        finished = true;
        safeCallback(() => callbacks.onError(String(event.data || '')));
      } else if (event.type === 'skill') {
        finished = true;
        const sid = (event.data && typeof event.data === 'object') ? (event.data.session_id as string || '') : '';
        lastSessionId = sid || event.session_id || lastSessionId;
        safeCallback(() => callbacks.onSkill(event, lastSessionId));
      }
    }
  }

  if (!finished) {
    callbacks.onError('Stream ended unexpectedly');
  } else if (!sawDone) {
    safeCallback(() => callbacks.onDone(lastSessionId));
  }
}

export async function streamChat(
  message: string,
  sessionId: string | null,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  mode?: string,
): Promise<void> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId, mode: mode || 'enhanced' }),
    signal,
  });

  await consumeChatStream(response, callbacks);
}

export async function streamUploadChat(
  message: string,
  sessionId: string | null,
  files: File[],
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  mode?: string,
): Promise<void> {
  const form = new FormData();
  form.append('message', message);
  if (sessionId) form.append('session_id', sessionId);
  form.append('mode', mode || 'enhanced');
  files.forEach(file => form.append('files', file, file.name));

  const response = await fetch('/api/chat/upload-and-chat', {
    method: 'POST',
    body: form,
    signal,
  });

  await consumeChatStream(response, callbacks);
}

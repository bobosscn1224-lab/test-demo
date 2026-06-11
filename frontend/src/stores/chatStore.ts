import type { Message, Session } from '../types';

type Listener = () => void;

class ChatStore {
  _messages: Message[] = [];
  _sessions: Session[] = [];
  _currentSessionId: string | null = null;
  _isStreaming = false;

  private listeners: Set<Listener> = new Set();

  getMessages(): Message[] {
    return [...this._messages];
  }

  getSessions(): Session[] {
    return [...this._sessions];
  }

  getCurrentSessionId(): string | null {
    return this._currentSessionId;
  }

  get isStreaming(): boolean {
    return this._isStreaming;
  }

  setSessions(sessions: Session[]): void {
    this._sessions = sessions;
    this.notify();
  }

  setSessionId(id: string | null): void {
    this._currentSessionId = id;
  }

  setMessages(messages: Message[]): void {
    this._messages = messages;
    this.notify();
  }

  clearMessages(): void {
    this._messages = [];
    this._currentSessionId = null;
    this.notify();
  }

  // Internal: called by ChatWindow during streaming to update last assistant message in store
  _updateLastAssistant(content: string): void {
    if (this._messages.length === 0) return;
    const last = this._messages[this._messages.length - 1];
    if (last.role !== 'assistant') return;
    this._messages[this._messages.length - 1] = { ...last, content };
    this.notify();
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    this.listeners.forEach((fn) => fn());
  }
}

export const chatStore = new ChatStore();

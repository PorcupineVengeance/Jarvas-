export type User = { id: string; name: string; email?: string | null };
export type Session = { authenticated: boolean; user?: User };
export type Task = { id: string; title: string; description?: string | null; status: string; priority: string; due_at?: string | null; created_at: string; updated_at: string };
export type MemoryItem = { id: string; category: string; content: string; created_at: string; updated_at: string };
export type Integration = { id: string; name: string; configured: boolean; status: string; detail: string };
export type AppStatus = { status: string; api_connection: boolean; time: string; cpu_percent: number; memory_percent: number; disk_percent: number; active_tasks: number; active_processes: Array<{ name: string; memory_mb: number }>; worker_count: number; connected_integrations: string[]; database: { connected: boolean }; providers: { llm: boolean; llm_name: string; transcription: boolean; text_to_speech: boolean }; microphone: { available: boolean | null; detail: string }; metrics_scope: string };
export type ChatMessage = { id: string; role: 'user' | 'assistant'; content: string };
export type Tool = { id: string; name: string; description: string; permission: string; write: boolean; input_schema: Record<string, unknown> };
export type FileRecord = { id: string; filename: string; content_type: string; size_bytes: number; created_at: string; asset_path: string };
export type RealtimeEvent = { type: string; [key: string]: unknown };

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...init, headers: { ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...init.headers } });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const data = await response.json(); message = data.detail || data.message || message; } catch { /* keep the generic HTTP message */ }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  authConfig: () => request<{ available: boolean; provider: string; reason: string | null }>('/api/auth/config'),
  session: () => request<Session>('/api/auth/session'),
  login: () => { window.location.assign(`/api/auth/login?origin=${encodeURIComponent(window.location.origin)}`); },
  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  status: () => request<AppStatus>('/api/system/status'),
  integrations: () => request<{ items: Integration[]; checked_at: string }>('/api/integrations'),
  tools: () => request<{ tools: Tool[]; notice: string }>('/api/tools'),
  executeTool: (toolId: string, arguments_: Record<string, unknown>, confirmed = false) => request<{ execution_id: string; status: string; tool_id: string; result: unknown }>('/api/automation/execute', { method: 'POST', body: JSON.stringify({ tool_id: toolId, arguments: arguments_, confirmed }) }),
  tasks: () => request<Task[]>('/api/tasks'),
  createTask: (body: { title: string; description?: string; priority: string; due_at?: string }) => request<Task>('/api/tasks', { method: 'POST', body: JSON.stringify(body) }),
  updateTask: (id: string, body: Partial<Pick<Task, 'title' | 'description' | 'status' | 'priority' | 'due_at'>>) => request<Task>(`/api/tasks/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteTask: (id: string) => request<{ ok: boolean }>(`/api/tasks/${encodeURIComponent(id)}`, { method: 'DELETE', body: JSON.stringify({ confirmed: true }) }),
  memories: (query?: string) => request<MemoryItem[]>(`/api/memory${query ? `?query=${encodeURIComponent(query)}` : ''}`),
  createMemory: (body: { category: string; content: string }) => request<MemoryItem>('/api/memory', { method: 'POST', body: JSON.stringify(body) }),
  updateMemory: (id: string, body: { category?: string; content?: string }) => request<MemoryItem>(`/api/memory/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteMemory: (id: string) => request<{ ok: boolean }>(`/api/memory/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  conversations: () => request<Array<{ id: string; title: string; created_at: string; updated_at: string }>>('/api/chat/conversations'),
  conversation: (id: string) => request<{ id: string; title: string; messages: ChatMessage[] }>(`/api/chat/conversations/${encodeURIComponent(id)}`),
  streamChat: async (body: { message: string; conversation_id?: string; client_message_id: string; mode: string }, onEvent: (event: string, data: Record<string, unknown>) => void, signal?: AbortSignal) => {
    const response = await fetch('/api/chat', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, body: JSON.stringify(body), signal });
    if (!response.ok) {
      let message = `Chat failed (${response.status}).`;
      try { const data = await response.json(); message = data.detail || message; } catch { /* ignore malformed error body */ }
      throw new ApiError(message, response.status);
    }
    if (!response.body) throw new ApiError('Streaming is not available in this browser.', 501);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const consume = (frame: string) => {
      let event = 'message';
      let dataText = '';
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        if (line.startsWith('data:')) dataText += line.slice(5).trim();
      }
      if (dataText) {
        try { onEvent(event, JSON.parse(dataText) as Record<string, unknown>); }
        catch { onEvent('error', { message: 'The server sent an invalid response event.' }); }
      }
    };
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const frames = buffer.split(/\r?\n\r?\n/);
        buffer = frames.pop() || '';
        frames.forEach(consume);
        if (done) break;
      }
      if (buffer.trim()) consume(buffer);
    } finally {
      if (signal?.aborted) void reader.cancel().catch(() => undefined);
      reader.releaseLock();
    }
  },
  transcribe: async (file: File, languageHint = '') => {
    const body = new FormData(); body.append('file', file); body.append('language_hint', languageHint);
    return request<{ text: string; language?: string; duration?: number; segments: unknown[] }>('/api/voice/transcribe', { method: 'POST', body });
  },
  speak: async (text: string, voice: string, speed: number, signal?: AbortSignal) => {
    const response = await fetch('/api/voice/speak', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, voice, speed }), signal });
    if (!response.ok) { let message = `Speech generation failed (${response.status}).`; try { message = (await response.json()).detail || message; } catch { /* keep default */ } throw new ApiError(message, response.status); }
    return response.blob();
  },
  files: () => request<FileRecord[]>('/api/files'),
  uploadFile: (file: File) => { const body = new FormData(); body.append('file', file); return request<FileRecord>('/api/files', { method: 'POST', body }); },
  file: (id: string) => request<{ id: string; filename: string; extracted_text: string; asset_path: string }>(`/api/files/${encodeURIComponent(id)}`),
  summarizeFile: (id: string) => request<{ file_id: string; filename: string; summary: string; source_scope: string }>(`/api/files/${encodeURIComponent(id)}/summarize`, { method: 'POST', body: JSON.stringify({}) }),
  saveReport: (filename: string, content: string) => request<FileRecord>('/api/files/reports', { method: 'POST', body: JSON.stringify({ filename, content }) }),
  deleteFile: (id: string) => request<{ ok: boolean; deletion: string; detail: string }>(`/api/files/${encodeURIComponent(id)}`, { method: 'DELETE', body: JSON.stringify({ confirmed: true }) }),
  connectRealtime: (onEvent: (event: RealtimeEvent) => void) => {
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${scheme}//${window.location.host}/api/ws`);
    socket.addEventListener('message', (event) => { try { onEvent(JSON.parse(event.data) as RealtimeEvent); } catch { onEvent({ type: 'error', message: 'The server sent an invalid event.' }); } });
    return socket;
  },
};

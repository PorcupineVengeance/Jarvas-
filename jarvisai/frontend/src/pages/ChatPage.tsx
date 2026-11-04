import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { LoaderCircle, MessageSquarePlus, RotateCcw, ShieldCheck, ArrowUp, CircleStop } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api, type ChatMessage } from '../lib/api';

type Conversation = { id: string; title: string; created_at: string; updated_at: string };
type PendingRetry = { message: string; id: string } | null;
const MODES = [['auto', 'Auto'], ['normal', 'Normal'], ['research', 'Research'], ['assistant', 'Assistant'], ['developer', 'Developer'], ['automation', 'Automation'], ['focus', 'Focus']];

export default function ChatPage() {
  const location = useLocation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const streamController = useRef<AbortController | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [draft, setDraft] = useState('');
  const [mode, setMode] = useState(localStorage.getItem('jarvis.mode') || 'auto');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [retry, setRetry] = useState<PendingRetry>(null);
  const [loaded, setLoaded] = useState(true);
  useEffect(() => { void api.conversations().then(setConversations).catch(() => setConversations([])); }, []);
  useEffect(() => {
    const requested = (location.state as { conversationId?: string } | null)?.conversationId;
    if (requested && requested !== conversationId) {
      setConversationId(requested); setLoaded(false);
      void api.conversation(requested).then((data) => { setMessages(data.messages); setLoaded(true); }).catch((e) => { setError(e.message); setLoaded(true); });
    }
  }, [location.state, conversationId]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }); }, [messages, busy]);
  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    const clientId = retry?.message === text ? retry.id : crypto.randomUUID();
    const userId = `u-${clientId}`;
    const assistantId = `a-${clientId}`;
    setMessages((current) => [...current.filter((item) => item.id !== userId && item.id !== assistantId), { id: userId, role: 'user', content: text }, { id: assistantId, role: 'assistant', content: '' }]);
    setDraft(''); setBusy(true); setError(''); setProgress('Thinking through your request…');
    const controller = new AbortController(); streamController.current = controller;
    let failed = false;
    try {
      await api.streamChat({ message: text, conversation_id: conversationId, client_message_id: clientId, mode }, (event, data) => {
        if (event === 'delta' && typeof data.text === 'string') {
          setProgress('');
          setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, content: item.content + data.text } : item));
        } else if (event === 'status' && typeof data.status === 'string') {
          setProgress(data.status);
        } else if (event === 'done') {
          if (typeof data.conversation_id === 'string') setConversationId(data.conversation_id);
        } else if (event === 'error') {
          failed = true;
          const message = typeof data.message === 'string' ? data.message : 'The response was interrupted.';
          setError(message);
          setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, content: item.content || `I couldn’t complete that request. ${message}` } : item));
        }
      }, controller.signal);
      if (failed) { setDraft(text); setRetry({ message: text, id: clientId }); }
      else { setRetry(null); void api.conversations().then(setConversations).catch(() => undefined); }
    } catch (e) {
      if (controller.signal.aborted) {
        setDraft(text); setRetry({ message: text, id: clientId }); setError('Response stopped. Your prompt is saved and ready to retry.');
      } else {
        setMessages((current) => [...current.filter((item) => item.id !== assistantId), { id: userId, role: 'user', content: text }]);
        setDraft(text); setRetry({ message: text, id: clientId });
        setError(e instanceof Error ? e.message : 'The request failed. Your prompt is ready to retry.');
      }
    } finally { if (streamController.current === controller) streamController.current = null; setBusy(false); setProgress(''); }
  };
  const stop = () => { streamController.current?.abort(); };
  useEffect(() => {
    const prompt = (location.state as { prompt?: string } | null)?.prompt;
    if (prompt && loaded && !busy) {
      window.history.replaceState({}, document.title, location.pathname);
      setLoaded(false); void send(prompt);
    }
  }, [location.state, loaded, busy]);
  const submit = (event: FormEvent) => { event.preventDefault(); void send(draft); };
  const onKey = (event: KeyboardEvent<HTMLTextAreaElement>) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send(draft); } };
  const newChat = () => { setConversationId(undefined); setMessages([]); setError(''); setRetry(null); setLoaded(true); };
  return <div className="chat-layout">
    <aside className="chat-history panel"><div className="panel-title"><div className="title-icon"><MessageSquarePlus size={17} /></div><h2>Conversations</h2><button className="subtle-link" onClick={newChat} aria-label="New conversation"><MessageSquarePlus size={16} /></button></div>
      <button className={`history-item${!conversationId ? ' selected' : ''}`} onClick={newChat}><span className="history-bullet" /><span>New conversation</span></button>
      {conversations.map((conversation) => <button key={conversation.id} className={`history-item${conversation.id === conversationId ? ' selected' : ''}`} onClick={() => { setConversationId(conversation.id); setLoaded(false); void api.conversation(conversation.id).then((data) => { setMessages(data.messages); setLoaded(true); }).catch((e) => { setError(e.message); setLoaded(true); }); }}><span className="history-bullet" /><span>{conversation.title}</span></button>)}
    </aside>
    <section className="chat-main panel">
      <div className="chat-topline"><div><span className="eyebrow">SECURE SESSION</span><h2>Assistant conversation</h2></div><div className="mode-select"><label htmlFor="chat-mode">Mode</label><select id="chat-mode" value={mode} onChange={(event) => { setMode(event.target.value); localStorage.setItem('jarvis.mode', event.target.value); }} aria-label="Assistant mode">{MODES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div></div>
      <div className="message-stream" ref={scrollRef} aria-live="polite">
        {messages.length === 0 && <div className="chat-empty"><div className="empty-orbit"><ShieldCheck size={26} /></div><span className="eyebrow">PRIVATE ASSISTANT</span><h3>What would you like to work through?</h3><p>Ask a question, set a task, or switch modes for research and development help. JARVIS will be clear about which services are connected.</p></div>}
        {messages.map((message) => <article key={message.id} className={`message ${message.role}`}><div className="message-avatar">{message.role === 'assistant' ? 'J' : 'YOU'}</div><div className="message-body"><div className="message-meta">{message.role === 'assistant' ? 'JARVIS' : 'YOU'} <span>{message.role === 'assistant' && busy && message.id.startsWith('a-') ? (progress || 'RESPONDING').toUpperCase() : ''}</span></div>{message.role === 'assistant' ? message.content ? <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div> : busy ? <div className="thinking-line"><LoaderCircle size={15} className="spin" /> {progress || 'Thinking through your request…'}</div> : null : <p>{message.content}</p>}</div></article>)}
        {error && <div className="chat-error" role="alert"><span>{error}</span><button onClick={() => void send(draft)} disabled={!draft.trim() || busy}><RotateCcw size={14} /> Retry</button></div>}
      </div>
      <form className="chat-composer" onSubmit={submit}><textarea aria-label="Message JARVIS" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={onKey} placeholder="Message JARVIS… (Enter to send, Shift+Enter for a new line)" rows={1} maxLength={12_000} disabled={busy} />{busy ? <button type="button" className="secondary-button chat-stop" onClick={stop} aria-label="Stop response"><CircleStop size={17} />Stop</button> : <button type="submit" className="primary-button" disabled={!draft.trim()} aria-label="Send message"><ArrowUp size={19} /></button>}</form>
      <div className="composer-foot"><span><ShieldCheck size={13} /> Private to your account</span><span>{draft.length.toLocaleString()} / 12,000</span></div>
    </section>
  </div>;
}

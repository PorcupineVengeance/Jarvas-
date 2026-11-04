import { FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, AudioLines, Check, ChevronRight, FileText, MessageSquareText, Plus, Send, Settings2, ShieldAlert, Sparkles, X } from 'lucide-react';
import { api, type AppStatus, type Task, type User } from '../lib/api';

function Meter({ label, value, display }: { label: string; value?: number; display: string }) {
  const safeValue = Math.max(0, Math.min(100, value ?? 0));
  return <div className="meter-row"><span className="meter-label">{label}</span><div className="meter-track"><span style={{ width: `${safeValue}%` }} /></div><strong>{display}</strong></div>;
}

function NewTaskDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (task: Task) => void }) {
  const [title, setTitle] = useState('');
  const [priority, setPriority] = useState('normal');
  const [dueAt, setDueAt] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    setSaving(true); setError('');
    try { const task = await api.createTask({ title: title.trim(), priority, ...(dueAt ? { due_at: new Date(dueAt).toISOString() } : {}) }); onCreated(task); onClose(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Task could not be saved.'); }
    finally { setSaving(false); }
  };
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <form className="modal-card panel" onSubmit={submit} aria-labelledby="task-title">
      <div className="modal-heading"><div><span className="eyebrow">PRODUCTIVITY</span><h2 id="task-title">Create task</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={18} /></button></div>
      <label className="field-label" htmlFor="task-name">Task name</label><input id="task-name" autoFocus maxLength={250} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="What needs to get done?" />
      <label className="field-label" htmlFor="task-priority">Priority</label><select id="task-priority" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select>
      <label className="field-label" htmlFor="task-deadline">Deadline (optional)</label><input id="task-deadline" type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} />
      {error && <p className="error-text">{error}</p>}
      <div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={!title.trim() || saving}><Plus size={16} />{saving ? 'Saving…' : 'Create task'}</button></div>
    </form>
  </div>;
}

export default function HomePage({ user }: { user: User }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [statusError, setStatusError] = useState('');
  const [modal, setModal] = useState(false);
  const [draft, setDraft] = useState('');
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const [nextStatus, nextTasks] = await Promise.all([api.status(), api.tasks()]);
        if (active) { setStatus(nextStatus); setTasks(nextTasks.filter((task) => task.status !== 'completed' && task.status !== 'cancelled')); setStatusError(''); }
      } catch (e) { if (active) setStatusError(e instanceof Error ? e.message : 'System status unavailable.'); }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 20_000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  const ready = status?.status === 'online';
  const sendPrompt = () => { const text = draft.trim(); if (!text) return; navigate('/chat', { state: { prompt: text } }); };
  const actions = [
    { title: 'Open Chat', icon: MessageSquareText, onClick: () => navigate('/chat') },
    { title: 'Open Files', icon: FileText, onClick: () => navigate('/tools', { state: { focus: 'files' } }) },
    { title: 'Voice', icon: AudioLines, onClick: () => navigate('/voice') },
    { title: 'Settings', icon: Settings2, onClick: () => navigate('/settings') },
  ];
  return <div className="home-layout">
    <section className="hero-console" aria-label="JARVIS console">
      <div className="hud-stage">
        <div className="hud-trace hud-trace-left" aria-hidden="true" /><div className="hud-trace hud-trace-right" aria-hidden="true" />
        <div className="hud-ring"><span className="ring-orbit ring-orbit-one" /><span className="ring-orbit ring-orbit-two" /><span className="ring-segment ring-segment-a" /><span className="ring-segment ring-segment-b" /><span className="ring-segment ring-segment-c" /><span className="ring-segment ring-segment-d" />
          <div className="hud-core"><span className="core-kicker"><Sparkles size={12} /> PERSONAL INTELLIGENCE</span><strong>JARVIS</strong><span className="core-caption">YOUR AI ASSISTANT</span><span className="core-rule" /></div>
        </div>
        <div className="hud-caption"><span>CORE SYSTEM</span><i /> <span>READY TO ASSIST</span></div>
      </div>
      <div className="command-dock panel">
        <button className="dock-voice" onClick={() => navigate('/voice')} aria-label="Open voice input"><AudioLines size={23} /><span className="voice-bars"><i /><i /><i /><i /><i /></span></button>
        <form className="dock-form" onSubmit={(event) => { event.preventDefault(); sendPrompt(); }}>
          <label className="sr-only" htmlFor="home-prompt">Ask JARVIS</label><input id="home-prompt" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ready when you are…" maxLength={12_000} />
          <button className="send-button" type="submit" disabled={!draft.trim()} aria-label="Send prompt"><Send size={19} /></button>
        </form>
      </div>
      <div className="greeting-strip"><span><Sparkles size={14} /> {user.name ? `Standing by, ${user.name.split(' ')[0]}.` : 'Standing by.'}</span><span>Private session <ShieldAlert size={13} /></span></div>
    </section>
    <aside className="right-rail">
      <section className="panel status-card">
        <div className="panel-title"><div className="title-icon"><Activity size={19} /></div><h2>System Status</h2><span className={`status-dot ${ready ? '' : 'status-warn'}`} title={ready ? 'Backend and database available' : 'Checking or degraded'} /></div>
        <Meter label="CPU Usage" value={status?.cpu_percent} display={status ? `${Math.round(status.cpu_percent)}%` : '—'} />
        <Meter label="Memory" value={status?.memory_percent} display={status ? `${Math.round(status.memory_percent)}%` : '—'} />
        <Meter label="Disk" value={status?.disk_percent} display={status ? `${Math.round(status.disk_percent)}%` : '—'} />
        <div className="network-row"><span>AI Provider</span><strong className={status?.providers.llm ? 'text-green' : 'text-muted'}><i className={`mini-dot ${status?.providers.llm ? '' : 'offline'}`} />{status?.providers.llm ? status.providers.llm_name : 'Unavailable'}</strong></div>
        <div className="network-row"><span>Network</span><strong className={status?.api_connection && status.database.connected ? 'text-green' : 'text-muted'}><i className={`mini-dot ${status?.api_connection && status.database.connected ? '' : 'offline'}`} />{status?.api_connection && status.database.connected ? 'Connected' : 'Unavailable'}</strong></div>
        <div className="network-row"><span>Tasks in progress</span><strong>{status ? status.active_tasks : '—'}</strong></div>
        <div className="network-row"><span>Processes / workers</span><strong>{status ? `${status.active_processes.length} / ${status.worker_count}` : '—'}</strong></div>
        {statusError && <div className="inline-note" role="status">{statusError}</div>}
      </section>
      <section className="panel quick-card">
        <div className="panel-title"><div className="title-icon bolt-icon"><Sparkles size={18} /></div><h2>Quick Actions</h2></div>
        <div className="quick-grid">{actions.map(({ title, icon: Icon, onClick }) => <button className="quick-action" key={title} onClick={onClick}><Icon size={22} /><span>{title}</span></button>)}</div>
      </section>
      <section className="panel tasks-card">
        <div className="panel-title"><div className="title-icon"><Check size={18} /></div><h2>Open Tasks</h2><button className="subtle-link" onClick={() => setModal(true)} aria-label="Add task"><Plus size={16} /></button></div>
        {tasks.length ? <ul className="mini-task-list">{tasks.slice(0, 3).map((task) => <li key={task.id}><span className={`task-priority priority-${task.priority}`} /><span>{task.title}</span><button onClick={async () => { try { const updated = await api.updateTask(task.id, { status: 'completed' }); setTasks((current) => current.filter((item) => item.id !== updated.id)); } catch (error) { setStatusError(error instanceof Error ? error.message : 'Task could not be updated.'); } }} aria-label={`Complete ${task.title}`}><Check size={14} /></button></li>)}</ul> : <p className="empty-state">No open tasks. Add one when you're ready.</p>}
        <button className="text-link" onClick={() => navigate('/tools')}>Manage tasks <ChevronRight size={14} /></button>
      </section>
    </aside>
    {modal && <NewTaskDialog onClose={() => setModal(false)} onCreated={(task) => setTasks((current) => [task, ...current])} />}
  </div>;
}

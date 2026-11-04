import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Activity, AlertTriangle, Check, Clock3, CloudUpload, Download, File, FileText, LoaderCircle, Pencil, Plus, Search, ShieldCheck, Trash2, Wrench, X } from 'lucide-react';
import { api, type FileRecord, type Integration, type MemoryItem, type Task, type Tool } from '../lib/api';

type Summary = { fileId: string; filename: string; text: string; sourceScope: string };

function toIso(value: string) { return value ? new Date(value).toISOString() : undefined; }
function asLocalDate(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export default function ToolsPage() {
  const location = useLocation();
  const [tools, setTools] = useState<Tool[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [memoryText, setMemoryText] = useState('');
  const [memoryCategory, setMemoryCategory] = useState('note');
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDue, setTaskDue] = useState('');
  const [search, setSearch] = useState('');
  const [uploading, setUploading] = useState(false);
  const [processingFile, setProcessingFile] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [editingMemory, setEditingMemory] = useState<string | null>(null);
  const [editMemoryText, setEditMemoryText] = useState('');
  const [editMemoryCategory, setEditMemoryCategory] = useState('note');
  const [editingTask, setEditingTask] = useState<string | null>(null);
  const [editTaskTitle, setEditTaskTitle] = useState('');
  const [editTaskDue, setEditTaskDue] = useState('');
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [extractedText, setExtractedText] = useState('');
  const [summary, setSummary] = useState<Summary | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    const results = await Promise.allSettled([api.tools(), api.integrations(), api.files(), api.memories(), api.tasks()]);
    if (results[0].status === 'fulfilled') setTools(results[0].value.tools);
    if (results[1].status === 'fulfilled') setIntegrations(results[1].value.items);
    if (results[2].status === 'fulfilled') setFiles(results[2].value);
    if (results[3].status === 'fulfilled') setMemories(results[3].value);
    if (results[4].status === 'fulfilled') setTasks(results[4].value);
    const failed = results.find((item): item is PromiseRejectedResult => item.status === 'rejected');
    if (failed) setError(failed.reason instanceof Error ? failed.reason.message : 'Some tools could not load.');
    setLoading(false);
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if ((location.state as { focus?: string } | null)?.focus === 'files' && !loading) document.getElementById('file-upload')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [location.state, loading]);

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file) return;
    setUploading(true); setError(''); setNotice('');
    try { const saved = await api.uploadFile(file); setFiles((items) => [saved, ...items]); setNotice(`${saved.filename} uploaded and indexed.`); }
    catch (e) { setError(e instanceof Error ? e.message : 'Upload failed.'); }
    finally { setUploading(false); event.target.value = ''; }
  };
  const addMemory = async (event: FormEvent) => {
    event.preventDefault(); if (!memoryText.trim()) return; setError('');
    try { const item = await api.createMemory({ category: memoryCategory, content: memoryText.trim() }); setMemories((items) => [item, ...items]); setMemoryText(''); setNotice('Memory saved to your account.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Memory could not be saved.'); }
  };
  const addTask = async (event: FormEvent) => {
    event.preventDefault(); if (!taskTitle.trim()) return; setError('');
    try { const item = await api.createTask({ title: taskTitle.trim(), priority: 'normal', ...(taskDue ? { due_at: toIso(taskDue) } : {}) }); setTasks((items) => [item, ...items]); setTaskTitle(''); setTaskDue(''); setNotice('Task created.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Task could not be created.'); }
  };
  const deleteMemory = async (item: MemoryItem) => {
    if (!window.confirm(`Delete the saved memory “${item.content.slice(0, 100)}”?`)) return;
    try { await api.deleteMemory(item.id); setMemories((items) => items.filter((row) => row.id !== item.id)); setNotice('Memory deleted.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Memory could not be deleted.'); }
  };
  const beginMemoryEdit = (item: MemoryItem) => { setEditingMemory(item.id); setEditMemoryText(item.content); setEditMemoryCategory(item.category); };
  const saveMemoryEdit = async (event: FormEvent, item: MemoryItem) => {
    event.preventDefault();
    try { const updated = await api.updateMemory(item.id, { category: editMemoryCategory, content: editMemoryText.trim() }); setMemories((rows) => rows.map((row) => row.id === item.id ? updated : row)); setEditingMemory(null); setNotice('Memory updated.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Memory could not be updated.'); }
  };
  const deleteFile = async (item: FileRecord) => {
    if (!window.confirm(`Hide ${item.filename} from your JARVIS file list? The storage provider does not expose physical deletion.`)) return;
    try { await api.deleteFile(item.id); setFiles((items) => items.filter((row) => row.id !== item.id)); if (expandedFile === item.id) setExpandedFile(null); setNotice('File hidden from the application index. Stored bytes may remain.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'File could not be hidden.'); }
  };
  const showExtractedText = async (item: FileRecord) => {
    if (expandedFile === item.id) { setExpandedFile(null); return; }
    setProcessingFile(item.id); setError('');
    try { const data = await api.file(item.id); setExtractedText(data.extracted_text || 'No extractable text was found.'); setExpandedFile(item.id); }
    catch (e) { setError(e instanceof Error ? e.message : 'Document text could not be loaded.'); }
    finally { setProcessingFile(''); }
  };
  const summarize = async (item: FileRecord) => {
    setProcessingFile(item.id); setError(''); setSummary(null);
    try { const result = await api.summarizeFile(item.id); setSummary({ fileId: item.id, filename: result.filename, text: result.summary, sourceScope: result.source_scope }); }
    catch (e) { setError(e instanceof Error ? e.message : 'Document summary could not be generated.'); }
    finally { setProcessingFile(''); }
  };
  const saveSummary = async () => {
    if (!summary) return;
    setProcessingFile(summary.fileId); setError('');
    const safeName = summary.filename.replace(/[^a-z0-9._-]+/gi, '-').replace(/^-+|-+$/g, '').slice(0, 140) || 'document';
    const content = `# Summary: ${summary.filename}\n\n${summary.text}\n\n---\n${summary.sourceScope}\n`;
    try { const saved = await api.saveReport(`jarvis-${safeName}-summary.md`, content); setFiles((items) => [saved, ...items]); setNotice(`${saved.filename} saved to your file workspace.`); }
    catch (e) { setError(e instanceof Error ? e.message : 'Report could not be saved.'); }
    finally { setProcessingFile(''); }
  };
  const finishTask = async (item: Task) => {
    try { const updated = await api.updateTask(item.id, { status: 'completed' }); setTasks((rows) => rows.map((row) => row.id === item.id ? updated : row)); setNotice('Task marked complete.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Task could not be updated.'); }
  };
  const startTaskEdit = (item: Task) => { setEditingTask(item.id); setEditTaskTitle(item.title); setEditTaskDue(asLocalDate(item.due_at)); };
  const saveTaskEdit = async (event: FormEvent, item: Task) => {
    event.preventDefault();
    try { const updated = await api.updateTask(item.id, { title: editTaskTitle.trim(), due_at: editTaskDue ? toIso(editTaskDue) : null }); setTasks((rows) => rows.map((row) => row.id === item.id ? updated : row)); setEditingTask(null); setNotice('Task updated.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Task could not be updated.'); }
  };
  const deleteTask = async (item: Task) => {
    if (!window.confirm(`Delete the task “${item.title}”? This cannot be undone.`)) return;
    try { await api.deleteTask(item.id); setTasks((rows) => rows.filter((row) => row.id !== item.id)); setNotice('Task deleted.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Task could not be deleted.'); }
  };

  const statusLabel = (item: Integration) => item.status.replaceAll('_', ' ');
  const visibleMemories = useMemo(() => memories.filter((item) => !search || `${item.category} ${item.content}`.toLowerCase().includes(search.toLowerCase())), [memories, search]);
  return <div className="page-stack tools-page">
    <div className="section-heading"><div><span className="eyebrow">CAPABILITIES</span><h2>Tools & workspace</h2><p>What is available right now, and what still needs a connection.</p></div><button className="secondary-button" onClick={() => void load()}><Activity size={15} /> Refresh status</button></div>
    {(error || notice) && <div className={error ? 'notice-error' : 'notice-success'} role={error ? 'alert' : 'status'}>{error || notice}</div>}
    <div className="tools-grid">
      <section className="panel tool-section"><div className="section-title"><Wrench size={18} /><div><h3>Registered tools</h3><p>Only allow-listed operations can run.</p></div></div>
        {loading ? <div className="loading-inline"><LoaderCircle className="spin" size={17} /> Loading tools…</div> : tools.map((tool) => <div className="tool-row" key={tool.id}><span className={`tool-icon ${tool.write ? 'tool-write' : ''}`}><Wrench size={16} /></span><div className="tool-copy"><strong>{tool.name}</strong><span>{tool.description}</span><small><code>{tool.id}</code> · {tool.permission} · {tool.write ? 'change' : 'read only'}</small></div><span className="readiness-chip ready"><i />Registered</span></div>)}
        <div className="safety-note"><ShieldCheck size={16} /><span>No arbitrary shell access or personal desktop control is available from this hosted app.</span></div>
      </section>
      <section className="panel tool-section"><div className="section-title"><Activity size={18} /><div><h3>Connections</h3><p>Verified provider status, not demo data.</p></div></div>
        {integrations.map((item) => <div className="integration-row" key={item.id}><span className={`integration-indicator ${item.configured ? 'connected' : ''}`} /><div><strong>{item.name}</strong><span>{item.detail}</span></div><em className={item.configured ? 'connected-text' : ''}>{statusLabel(item)}</em></div>)}
      </section>
    </div>
    <div className="tools-grid lower-tools">
      <section className="panel tool-section" id="file-area"><div className="section-title"><FileText size={18} /><div><h3>File workspace</h3><p>PDF, DOCX, XLSX, CSV, TXT, JSON and Markdown.</p></div></div>
        <label className={`upload-zone${uploading ? ' uploading' : ''}`} htmlFor="file-upload"><input id="file-upload" type="file" accept=".pdf,.docx,.xlsx,.csv,.txt,.json,.md,.markdown" onChange={upload} disabled={uploading} /><span className="upload-icon">{uploading ? <LoaderCircle size={22} className="spin" /> : <CloudUpload size={22} />}</span><strong>{uploading ? 'Uploading and indexing…' : 'Choose a file to upload'}</strong><small>Validated and stored in project object storage when available.</small></label>
        <div className="file-list">{files.length ? files.map((item) => <div className="file-entry" key={item.id}><div className="file-row"><File size={16} /><div><strong>{item.filename}</strong><small>{(item.size_bytes / 1024).toFixed(1)} KB · {new Date(item.created_at).toLocaleDateString()}</small></div><a href={`/api/files/${encodeURIComponent(item.id)}/download`} aria-label={`Download ${item.filename}`}><Download size={15} /></a><button onClick={() => void showExtractedText(item)} aria-label={`Read extracted text from ${item.filename}`} disabled={processingFile === item.id}>{processingFile === item.id ? <LoaderCircle size={15} className="spin" /> : <FileText size={15} />}</button><button onClick={() => void summarize(item)} aria-label={`Summarize ${item.filename}`} disabled={processingFile === item.id}><span>Summarize</span></button><button onClick={() => void deleteFile(item)} aria-label={`Hide ${item.filename}`}><Trash2 size={15} /></button></div>{expandedFile === item.id && <pre className="file-extraction">{extractedText || 'No extractable text was found.'}</pre>}</div>) : <p className="empty-state">No uploaded files. Uploads require the managed object-storage service.</p>}</div>
        {summary && <div className="document-summary"><div className="panel-title"><div><span className="eyebrow">DOCUMENT SUMMARY</span><strong>{summary.filename}</strong></div><button className="subtle-link" onClick={() => setSummary(null)} aria-label="Close summary"><X size={16} /></button></div><pre>{summary.text}</pre><small>{summary.sourceScope}</small><button className="secondary-button" onClick={() => void saveSummary()} disabled={processingFile === summary.fileId}><Download size={15} />Save downloadable report</button></div>}
      </section>
      <section className="panel tool-section"><div className="section-title"><ShieldCheck size={18} /><div><h3>Personal memory</h3><p>Saved only when you choose. Credentials are rejected.</p></div></div>
        <form className="inline-form memory-form" onSubmit={addMemory}><select aria-label="Memory category" value={memoryCategory} onChange={(event) => setMemoryCategory(event.target.value)}><option value="note">Note</option><option value="preference">Preference</option><option value="instruction">Instruction</option><option value="project">Project</option><option value="contact">Contact</option><option value="task">Task</option><option value="other">Other</option></select><textarea aria-label="Memory to save" value={memoryText} onChange={(event) => setMemoryText(event.target.value)} placeholder="Save a preference or useful detail…" rows={2} maxLength={4000} /><button className="primary-button" disabled={!memoryText.trim()}><Plus size={15} />Save</button></form>
        <div className="memory-search"><Search size={15} /><input aria-label="Search memories" placeholder="Filter saved memories" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
        <div className="memory-list">{visibleMemories.length ? visibleMemories.slice(0, 20).map((item) => <div className="memory-row" key={item.id}>{editingMemory === item.id ? <form className="memory-edit-form" onSubmit={(event) => void saveMemoryEdit(event, item)}><select aria-label="Edit memory category" value={editMemoryCategory} onChange={(event) => setEditMemoryCategory(event.target.value)}><option value="note">Note</option><option value="preference">Preference</option><option value="instruction">Instruction</option><option value="project">Project</option><option value="contact">Contact</option><option value="task">Task</option><option value="other">Other</option></select><textarea aria-label="Edit saved memory" value={editMemoryText} onChange={(event) => setEditMemoryText(event.target.value)} rows={3} maxLength={4000} /><div className="memory-edit-actions"><button className="primary-button" disabled={!editMemoryText.trim()}><Check size={14} />Save</button><button type="button" className="secondary-button" onClick={() => setEditingMemory(null)}>Cancel</button></div></form> : <><div><span className="memory-tag">{item.category}</span><p>{item.content}</p></div><div className="row-actions"><button onClick={() => beginMemoryEdit(item)} aria-label="Edit memory"><Pencil size={15} /></button><button onClick={() => void deleteMemory(item)} aria-label="Delete memory"><Trash2 size={15} /></button></div></>}</div>) : <p className="empty-state">No saved memories match this filter.</p>}</div>
      </section>
    </div>
    <section className="panel task-section"><div className="section-title"><Clock3 size={18} /><div><h3>Tasks</h3><p>Persistent task records; reminders require published scheduling.</p></div></div><form className="task-create-row" onSubmit={addTask}><input aria-label="New task title" value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} placeholder="Add a task…" maxLength={250} /><label className="sr-only" htmlFor="task-due">Optional deadline</label><input id="task-due" type="datetime-local" aria-label="Optional task deadline" value={taskDue} onChange={(event) => setTaskDue(event.target.value)} /><button className="primary-button" disabled={!taskTitle.trim()}><Plus size={16} />Create</button></form><div className="task-list">{tasks.slice(0, 30).map((task) => <div className="task-entry" key={task.id}>{editingTask === task.id ? <form className="task-edit-form" onSubmit={(event) => void saveTaskEdit(event, task)}><input aria-label="Edit task title" maxLength={250} required value={editTaskTitle} onChange={(event) => setEditTaskTitle(event.target.value)} /><input aria-label="Edit task deadline" type="datetime-local" value={editTaskDue} onChange={(event) => setEditTaskDue(event.target.value)} /><button className="primary-button"><Check size={14} />Save</button><button type="button" className="secondary-button" onClick={() => setEditingTask(null)}>Cancel</button></form> : <div className="task-row"><span className={`task-priority priority-${task.priority}`} /><span>{task.title}{task.due_at && <small className="task-due">Due {new Date(task.due_at).toLocaleString()}</small>}</span><label className="sr-only" htmlFor={`priority-${task.id}`}>Priority for {task.title}</label><select id={`priority-${task.id}`} className="priority-select" value={task.priority} onChange={async (event) => { try { const updated = await api.updateTask(task.id, { priority: event.target.value }); setTasks((rows) => rows.map((row) => row.id === task.id ? updated : row)); } catch (e) { setError(e instanceof Error ? e.message : 'Priority could not be updated.'); } }}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select><span className="task-status">{task.status.replace('_', ' ')}</span>{task.status !== 'completed' && <button onClick={() => void finishTask(task)} aria-label={`Complete ${task.title}`}><Check size={15} /></button>}<button onClick={() => startTaskEdit(task)} aria-label={`Edit ${task.title}`}><Pencil size={15} /></button><button onClick={() => void deleteTask(task)} aria-label={`Delete ${task.title}`}><Trash2 size={15} /></button></div>}</div>)}{!tasks.length && <p className="empty-state">No tasks yet.</p>}</div><div className="safety-note"><AlertTriangle size={15} /><span>Task deletion requires confirmation. Scheduled notifications are not enabled until a published callback is registered.</span></div>
    </section>
  </div>;
}

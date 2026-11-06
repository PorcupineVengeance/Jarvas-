import { FormEvent, useEffect, useRef, useState, type CSSProperties } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Activity, AudioLines, Check, ChevronRight, CircleStop, Download, FileText, MessageSquareText, Mic, Monitor, Plus, Send, Settings2, ShieldAlert, Sparkles, Volume2, X } from 'lucide-react';
import { api, type AppStatus, type Task, type User } from '../lib/api';
import { isJarvisDesktop } from '../lib/desktop';
import { browserSpeechSupported, ensureMicrophonePermissionCached, forSpeech, getPreferredVoice, playAudioBlob, setVoiceBusy, shouldUseServerStt, speakWithBrowser, startBrowserListen, startVoiceCapture, type LiveListenHandle, type RecordingHandle } from '../lib/voiceConversation';

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
    try {
      const task = await api.createTask({ title: title.trim(), priority, ...(dueAt ? { due_at: new Date(dueAt).toISOString() } : {}) });
      onCreated(task);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Task could not be saved.');
    } finally {
      setSaving(false);
    }
  };
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <form className="modal-card panel" onSubmit={submit} aria-labelledby="task-title">
      <div className="modal-heading"><div><span className="eyebrow">PRODUCTIVITY</span><h2 id="task-title">Create task</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={18} /></button></div>
      <label className="field-label" htmlFor="task-name">Task name</label>
      <input id="task-name" autoFocus maxLength={250} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="What needs to get done?" />
      <label className="field-label" htmlFor="task-priority">Priority</label>
      <select id="task-priority" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select>
      <label className="field-label" htmlFor="task-deadline">Deadline (optional)</label>
      <input id="task-deadline" type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} />
      {error && <p className="error-text">{error}</p>}
      <div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={!title.trim() || saving}><Plus size={16} />{saving ? 'Saving…' : 'Create task'}</button></div>
    </form>
  </div>;
}

type Phase = 'idle' | 'listening' | 'transcribing' | 'thinking' | 'speaking';

export default function HomePage({ user }: { user: User }) {
  const navigate = useNavigate();
  const location = useLocation();
  const inputRef = useRef<HTMLInputElement>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const speakAbortRef = useRef<AbortController | null>(null);
  const recordingRef = useRef<RecordingHandle | LiveListenHandle | null>(null);
  const voiceLoopRef = useRef(false);
  const listenTokenRef = useRef(0);
  const beginListeningRef = useRef<() => Promise<void>>(async () => undefined);
  const conversationIdRef = useRef<string | undefined>();
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [statusError, setStatusError] = useState('');
  const [modal, setModal] = useState(false);
  const [draft, setDraft] = useState('');
  const [voiceMode, setVoiceMode] = useState(false);
  const [conversationId, setConversationId] = useState<string>();
  const [phase, setPhase] = useState<Phase>('idle');
  const [chatError, setChatError] = useState('');
  const [level, setLevel] = useState(0);
  const [voiceHint, setVoiceHint] = useState('');
  const emptyListenRef = useRef(0);
  const phaseRef = useRef<Phase>('idle');
  const runChatTurnRef = useRef<(text: string, options?: { continueListening?: boolean }) => Promise<void>>(async () => undefined);
  const speakReplyRef = useRef<(text: string) => Promise<void>>(async () => undefined);
  const layoutRef = useRef<HTMLDivElement>(null);

  useEffect(() => { conversationIdRef.current = conversationId; }, [conversationId]);
  useEffect(() => { phaseRef.current = phase; }, [phase]);

  useEffect(() => {
    const root = layoutRef.current;
    if (!root) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      root.style.setProperty('--mx', '0');
      root.style.setProperty('--my', '0');
      return;
    }
    let raf = 0;
    let targetX = 0;
    let targetY = 0;
    let curX = 0;
    let curY = 0;
    const onMove = (event: PointerEvent) => {
      const rect = root.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      targetX = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      targetY = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    };
    const onLeave = () => {
      targetX = 0;
      targetY = 0;
    };
    const tick = () => {
      curX += (targetX - curX) * 0.09;
      curY += (targetY - curY) * 0.09;
      root.style.setProperty('--mx', curX.toFixed(4));
      root.style.setProperty('--my', curY.toFixed(4));
      raf = window.requestAnimationFrame(tick);
    };
    root.addEventListener('pointermove', onMove);
    root.addEventListener('pointerleave', onLeave);
    raf = window.requestAnimationFrame(tick);
    return () => {
      window.cancelAnimationFrame(raf);
      root.removeEventListener('pointermove', onMove);
      root.removeEventListener('pointerleave', onLeave);
    };
  }, []);

  useEffect(() => {
    // Ensure wake-word can re-arm after a remount / interrupted call.
    setVoiceBusy(false);
    voiceLoopRef.current = false;
  }, []);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const [nextStatus, nextTasks] = await Promise.all([api.status(), api.tasks()]);
        if (!alive) return;
        setStatus(nextStatus);
        setTasks(nextTasks.filter((task) => task.status !== 'completed' && task.status !== 'cancelled'));
        setStatusError('');
      } catch (e) {
        if (alive) setStatusError(e instanceof Error ? e.message : 'System status unavailable.');
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 20_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
      voiceLoopRef.current = false;
      recordingRef.current?.stop();
      chatAbortRef.current?.abort();
      speakAbortRef.current?.abort();
    };
  }, []);

  const ready = status?.status === 'online';
  const llmReady = Boolean(status?.providers.llm);
  const sttReady = Boolean(status?.providers.transcription);
  const ttsReady = Boolean(status?.providers.text_to_speech);
  const busy = phase !== 'idle';

  const speakReply = async (text: string) => {
    const spoken = forSpeech(text, 1200);
    if (!spoken) return;
    setPhase('speaking');
    setVoiceBusy(true);
    setLevel(0.45);
    speakAbortRef.current?.abort();
    const local = new AbortController();
    speakAbortRef.current = local;
    const pulse = window.setInterval(() => {
      setLevel(0.35 + Math.random() * 0.55);
    }, 120);
    try {
      if (ttsReady) {
        try {
          const blob = await api.speak(spoken, getPreferredVoice(), 1.08, local.signal);
          if (local.signal.aborted) return;
          await playAudioBlob(blob, 1, local.signal);
          return;
        } catch (e) {
          if (local.signal.aborted) return;
          console.warn('Server TTS failed, using browser voice', e);
        }
      }
      await speakWithBrowser(spoken, local.signal);
    } catch (e) {
      if (!local.signal.aborted) {
        setChatError(e instanceof Error ? e.message : 'Speech playback failed. Check that your system volume is up.');
      }
    } finally {
      window.clearInterval(pulse);
      if (speakAbortRef.current === local) speakAbortRef.current = null;
    }
  };

  // Home is voice-first: never render reply text here — always speak the full finished answer.
  const runChatTurn = async (text: string, options?: { continueListening?: boolean }) => {
    const continueListening = options?.continueListening ?? false;
    if (!llmReady) {
      setChatError('The AI provider is not connected.');
      setPhase('idle');
      return;
    }
    chatAbortRef.current?.abort();
    const clientId = crypto.randomUUID();
    setPhase('thinking');
    setChatError('');
    const controller = new AbortController();
    chatAbortRef.current = controller;
    let failed = false;
    let fullAnswer = '';
    try {
      await api.streamChat(
        { message: text, conversation_id: conversationIdRef.current, client_message_id: clientId, mode: 'voice' },
        (event, data) => {
          if (event === 'delta' && typeof data.text === 'string') {
            fullAnswer += data.text;
          } else if (event === 'done' && typeof data.conversation_id === 'string') {
            setConversationId(data.conversation_id);
            conversationIdRef.current = data.conversation_id;
          } else if (event === 'error') {
            failed = true;
            setChatError(typeof data.message === 'string' ? data.message : 'The response was interrupted.');
          }
        },
        controller.signal,
      );
      if (!failed) {
        let finalText = fullAnswer.trim();
        // One automatic retry if the provider streamed no visible text.
        if (!finalText) {
          fullAnswer = '';
          await api.streamChat(
            { message: text, client_message_id: crypto.randomUUID(), mode: 'voice' },
            (event, data) => {
              if (event === 'delta' && typeof data.text === 'string') fullAnswer += data.text;
              else if (event === 'done' && typeof data.conversation_id === 'string') {
                setConversationId(data.conversation_id);
                conversationIdRef.current = data.conversation_id;
              } else if (event === 'error') {
                failed = true;
                setChatError(typeof data.message === 'string' ? data.message : 'The response was interrupted.');
              }
            },
            controller.signal,
          );
          finalText = fullAnswer.trim();
        }
        if (!failed && !finalText) {
          setChatError('JARVIS returned an empty reply. Please try again.');
          failed = true;
        } else if (!failed) {
          await speakReply(finalText);
        }
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        setChatError(e instanceof Error ? e.message : 'The request failed.');
        failed = true;
      }
    } finally {
      if (chatAbortRef.current === controller) chatAbortRef.current = null;
      setPhase('idle');
      setLevel(0);
      setVoiceBusy(Boolean(continueListening && voiceLoopRef.current && !failed));
      if (continueListening && voiceLoopRef.current && !failed) {
        window.setTimeout(() => { if (voiceLoopRef.current) void beginListeningRef.current(); }, 280);
      } else {
        setVoiceBusy(false);
        if (!voiceLoopRef.current) window.setTimeout(() => inputRef.current?.focus(), 40);
      }
    }
  };

  const beginListening = async () => {
    if (!llmReady) {
      setChatError('AI is still connecting — wait a second for Systems Online, then tap again.');
      return;
    }
    // Cancel any in-flight listen before starting a new turn.
    recordingRef.current?.stop();
    recordingRef.current = null;
    const token = ++listenTokenRef.current;
    setVoiceMode(true);
    voiceLoopRef.current = true;
    setVoiceBusy(true);
    setChatError('');
    setVoiceHint('Listening — speak, then TAP AGAIN when done');
    setPhase('listening');
    setLevel(0.2);
    try {
      await ensureMicrophonePermissionCached();
    } catch (e) {
      if (listenTokenRef.current !== token) return;
      setPhase('idle');
      setChatError(
        e instanceof Error
          ? e.message
          : 'Microphone blocked. Allow mic for JARVIS/Electron in macOS System Settings → Privacy & Security → Microphone.',
      );
      voiceLoopRef.current = false;
      setVoiceMode(false);
      setVoiceBusy(false);
      setVoiceHint('');
      return;
    }
    if (listenTokenRef.current !== token || !voiceLoopRef.current) return;

    try {
      let text = '';
      let serverStt = shouldUseServerStt(sttReady);
      if (!serverStt) {
        try {
          const voice = await api.status();
          serverStt = shouldUseServerStt(Boolean(voice.providers.transcription));
        } catch { /* keep prior */ }
      }
      if (serverStt) {
        const handle = await startVoiceCapture({
          maxMs: 45_000,
          silenceMs: 1600,
          minMs: 1800,
          onLevel: setLevel,
        });
        recordingRef.current = handle;
        const file = await handle.promise;
        recordingRef.current = null;
        if (listenTokenRef.current !== token || !voiceLoopRef.current) return;
        setPhase('transcribing');
        setVoiceHint('Got it — transcribing…');
        const result = await api.transcribe(file);
        text = result.text.trim();
      } else if (browserSpeechSupported()) {
        const handle = startBrowserListen({
          endSilenceMs: 1100,
          maxMs: 20_000,
          onPartial: (value) => {
            setLevel(value ? Math.min(1, 0.35 + value.length * 0.02) : 0.18);
          },
        });
        recordingRef.current = handle;
        text = (await handle.promise).trim();
        recordingRef.current = null;
      } else {
        throw new Error('Speech recognition is unavailable and server STT is not configured.');
      }

      if (listenTokenRef.current !== token || !voiceLoopRef.current) return;
      if (!text) {
        setChatError('I didn’t catch any words. Tap the orb, speak clearly, then tap again when finished.');
        setVoiceHint('Tap orb to try again');
        setPhase('listening');
        setLevel(0.12);
        recordingRef.current = null;
        return;
      }
      emptyListenRef.current = 0;
      setDraft('');
      setChatError('');
      setVoiceHint('Thinking…');
      await runChatTurn(text, { continueListening: true });
    } catch (e) {
      recordingRef.current = null;
      if (listenTokenRef.current !== token) return;
      const message = e instanceof Error ? e.message : 'Voice capture failed.';
      // Stay in the call — never bounce back to idle home on a soft failure.
      if (voiceLoopRef.current) {
        setChatError(message);
        setVoiceHint('Tap orb to try again — or End call');
        setPhase('listening');
        setLevel(0.12);
        return;
      }
      setPhase('idle');
      setLevel(0);
      setVoiceBusy(false);
    }
  };
  beginListeningRef.current = beginListening;
  runChatTurnRef.current = runChatTurn;
  speakReplyRef.current = speakReply;

  useEffect(() => {
    const handleWake = (command?: string) => {
      const busyPhase = phaseRef.current;
      if (voiceLoopRef.current || busyPhase === 'thinking' || busyPhase === 'transcribing' || busyPhase === 'speaking') return;
      const queuedCommand = (command || window.sessionStorage.getItem('jarvis.wakeCommand') || '').trim();
      window.sessionStorage.removeItem('jarvis.wakeCommand');
      window.sessionStorage.removeItem('jarvis.startVoice');
      if (queuedCommand) {
        // “Hey JARVIS what’s the weather” → answer immediately.
        setVoiceMode(true);
        voiceLoopRef.current = true;
        void runChatTurnRef.current(queuedCommand, { continueListening: true });
        return;
      }
      // Bare “Hey/Yo JARVIS” → acknowledge, then listen for the request.
      void (async () => {
        setVoiceMode(true);
        voiceLoopRef.current = true;
        setVoiceHint('Yes, sir?');
        try {
          await speakReplyRef.current('Yes, sir?');
        } catch { /* ignore ack failures */ }
        if (voiceLoopRef.current) void beginListeningRef.current();
      })();
    };

    const onWake = (event: Event) => {
      const detail = (event as CustomEvent<{ command?: string }>).detail;
      handleWake(detail?.command);
    };
    window.addEventListener('jarvis:wake', onWake);
    return () => window.removeEventListener('jarvis:wake', onWake);
  }, []);

  useEffect(() => {
    const queued = window.sessionStorage.getItem('jarvis.startVoice') === '1'
      || Boolean((location.state as { startVoice?: boolean } | null)?.startVoice);
    if (!queued) return;
    const command = window.sessionStorage.getItem('jarvis.wakeCommand') || '';
    window.sessionStorage.removeItem('jarvis.startVoice');
    window.setTimeout(() => {
      if (voiceLoopRef.current) return;
      window.dispatchEvent(new CustomEvent('jarvis:wake', { detail: { command } }));
    }, 120);
  }, [location.state]);

  const stopEverything = () => {
    voiceLoopRef.current = false;
    listenTokenRef.current += 1;
    emptyListenRef.current = 0;
    recordingRef.current?.stop();
    recordingRef.current = null;
    chatAbortRef.current?.abort();
    speakAbortRef.current?.abort();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    setPhase('idle');
    setLevel(0);
    setVoiceBusy(false);
    setVoiceHint('');
  };

  const onCoreClick = () => {
    setChatError('');
    if (phase === 'listening') {
      if (recordingRef.current) {
        // User finished speaking — process this turn.
        setVoiceHint('Processing your speech…');
        emptyListenRef.current = 0;
        recordingRef.current.stop();
      } else {
        // Listening UI open but no active recorder (e.g. empty last turn) — start fresh.
        void beginListening();
      }
      return;
    }
    if (phase === 'speaking') {
      speakAbortRef.current?.abort();
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
      setPhase('idle');
            if (voiceMode) {
        voiceLoopRef.current = true;
        void beginListening();
      }
      return;
    }
    if (phase === 'thinking' || phase === 'transcribing') {
      // Keep the call alive while JARVIS is working.
      return;
    }
    void beginListening();
  };

  const sendText = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    const keepVoice = voiceMode;
    if (!keepVoice) voiceLoopRef.current = false;
    else {
      recordingRef.current?.stop();
      recordingRef.current = null;
    }
    setDraft('');
    await runChatTurn(text, { continueListening: keepVoice });
  };

  const endVoiceCall = () => {
    stopEverything();
    setVoiceMode(false);
    setChatError('');
      };

  const onDesktop = isJarvisDesktop() || Boolean(status?.desktop?.is_desktop);
  const downloads = status?.desktop?.downloads;
  const preferWindows = typeof navigator !== 'undefined' && /win/i.test(navigator.platform || navigator.userAgent || '');
  const desktopDownload = preferWindows
    ? (downloads?.windows || downloads?.mac || '')
    : (downloads?.mac || downloads?.windows || '');
  const actions = [
    { title: 'Open Chat', icon: MessageSquareText, onClick: () => navigate('/chat', conversationId ? { state: { conversationId } } : undefined) },
    { title: 'Open Files', icon: FileText, onClick: () => navigate('/tools', { state: { focus: 'files' } }) },
    { title: 'Voice', icon: AudioLines, onClick: () => navigate('/voice') },
    { title: 'Settings', icon: Settings2, onClick: () => navigate('/settings') },
    onDesktop
      ? { title: 'Desktop', icon: Monitor, onClick: () => navigate('/settings') }
      : {
          title: 'Get Desktop',
          icon: Download,
          onClick: () => {
            if (desktopDownload) window.open(desktopDownload, '_blank', 'noopener,noreferrer');
            else navigate('/settings');
          },
        },
  ];

  const hudState = phase === 'listening' ? 'listening' : phase === 'speaking' ? 'speaking' : phase === 'thinking' || phase === 'transcribing' ? 'working' : 'idle';
  const hint =
    phase === 'listening' ? 'Listening'
      : phase === 'transcribing' ? 'Processing'
        : phase === 'thinking' ? 'Thinking'
          : phase === 'speaking' ? 'Speaking'
            : voiceMode ? 'Connected'
              : 'Tap to talk';

  return <div ref={layoutRef} className={`home-layout home-machine${voiceMode ? ' home-voice-mode' : ''}`}>
    <section className="hero-console" aria-label="JARVIS console">
      <div className="hud-stage">
        <div className="hud-ambient" aria-hidden="true">
          <span className="hud-grid" />
          <span className="hud-scan" />
          <span className="hud-scan hud-scan-delay" />
          <span className="hud-particle p1" /><span className="hud-particle p2" /><span className="hud-particle p3" />
          <span className="hud-particle p4" /><span className="hud-particle p5" /><span className="hud-particle p6" />
          <span className="hud-radar" />
          <span className="hud-radar hud-radar-outer" />
          <span className="hud-crosshair" />
        </div>

        <div className="hud-sat-field" aria-hidden="true">
          <div className="hud-sat hud-sat-left depth-far">
            <div className="hud-mini-radar"><i /></div>
            <div className="hud-gauge-row">
              <span /><span /><span /><span /><span />
            </div>
            <div className="hud-float-chip">
              <em>ARTIFICIAL INTELLIGENCE</em>
              <strong>SCANNING…</strong>
            </div>
            <div className="hud-readout">
              <span>78.1</span><span>16.1</span><span>6.6</span>
            </div>
          </div>
          <div className="hud-sat hud-sat-right depth-mid">
            <div className="hud-gear-dial">
              <span className="gear-ring" /><span className="gear-core" />
            </div>
            <div className="hud-wave">
              <svg viewBox="0 0 120 28" preserveAspectRatio="none" aria-hidden="true">
                <polyline points="0,14 8,14 12,6 16,22 20,10 24,18 28,14 36,14 40,4 44,24 48,12 52,16 56,14 68,14 72,8 76,20 80,10 84,18 88,14 100,14 104,7 108,21 112,12 116,16 120,14" />
              </svg>
            </div>
            <div className="hud-bar-chart">
              <i style={{ '--h': '.45' } as CSSProperties} /><i style={{ '--h': '.7' } as CSSProperties} />
              <i style={{ '--h': '.35' } as CSSProperties} /><i style={{ '--h': '.9' } as CSSProperties} />
              <i style={{ '--h': '.55' } as CSSProperties} /><i style={{ '--h': '.75' } as CSSProperties} />
              <i style={{ '--h': '.4' } as CSSProperties} /><i style={{ '--h': '.85' } as CSSProperties} />
            </div>
            <div className="hud-float-chip right">
              <em>PREPARATION COMPLETE</em>
              <strong>CORE ONLINE</strong>
            </div>
          </div>
        </div>

        <div className="hud-trace hud-trace-left" aria-hidden="true" />
        <div className="hud-trace hud-trace-right" aria-hidden="true" />

        {voiceMode ? (
          <div className="voice-call-badge" aria-live="polite">
            <span className={`voice-call-pulse state-${hudState}`} />
            <strong>{phase === 'listening' ? 'Listening — tap again when done' : phase === 'speaking' ? 'JARVIS speaking' : phase === 'thinking' || phase === 'transcribing' ? 'Thinking' : 'Voice call'}</strong>
            <button type="button" onClick={endVoiceCall} aria-label="End voice call"><X size={14} /></button>
          </div>
        ) : null}
        {chatError ? <div className="voice-error-banner" role="alert">{chatError}</div> : null}

        <button
          type="button"
          className={`hud-ring hud-trigger state-${hudState}`}
          onClick={onCoreClick}
          aria-label={phase === 'listening' ? 'Finish speaking' : phase === 'speaking' ? 'Interrupt JARVIS' : 'Start voice conversation with JARVIS'}
          aria-pressed={phase === 'listening' || voiceMode}
          style={{ ['--voice-level' as string]: String(Math.max(level, voiceMode ? 0.15 : 0)) }}
        >
          <span className="ring-orbit ring-orbit-one" aria-hidden="true" />
          <span className="ring-orbit ring-orbit-two" aria-hidden="true" />
          <span className="ring-orbit ring-orbit-three" aria-hidden="true" />
          <span className="ring-segment ring-segment-a" aria-hidden="true" />
          <span className="ring-segment ring-segment-b" aria-hidden="true" />
          <span className="ring-segment ring-segment-c" aria-hidden="true" />
          <span className="ring-segment ring-segment-d" aria-hidden="true" />
          <span className="ring-tick" aria-hidden="true" />
          <div className="hud-core">
            {!voiceMode && <span className="core-kicker"><Sparkles size={12} /> PERSONAL INTELLIGENCE</span>}
            <span className="voice-orb-glow" aria-hidden="true" style={{ ['--voice-level' as string]: String(Math.max(level, 0.12)) }} />
            <strong className="core-brand">JARVIS</strong>
            {!voiceMode && <span className="core-caption">YOUR AI ASSISTANT</span>}
            {!voiceMode && <span className="core-rule" />}
            <span className="core-hint">{hint}</span>
            {(phase === 'listening' || phase === 'speaking' || voiceMode) && (
              <span className="voice-level-meter" aria-hidden="true">
                <i style={{ transform: `scaleY(${0.25 + level * 0.75})` }} />
                <i style={{ transform: `scaleY(${0.35 + level * 0.9})` }} />
                <i style={{ transform: `scaleY(${0.2 + level})` }} />
                <i style={{ transform: `scaleY(${0.4 + level * 0.8})` }} />
                <i style={{ transform: `scaleY(${0.25 + level * 0.7})` }} />
              </span>
            )}
            {phase === 'speaking' && <span className="core-phase-icon" aria-hidden="true"><Volume2 size={16} /></span>}
            {phase === 'listening' && <span className="core-phase-icon" aria-hidden="true"><Mic size={16} /></span>}
          </div>
        </button>

        <div className="hud-caption">
          <span>{voiceMode ? 'VOICE CALL' : 'CORE SYSTEM'}</span>
          <i />
          <span>{phase === 'listening' ? 'LISTENING' : phase === 'speaking' ? 'SPEAKING' : phase === 'thinking' || phase === 'transcribing' ? 'THINKING' : voiceMode ? 'CONNECTED' : 'READY TO ASSIST'}</span>
        </div>
      </div>

      <div className={`command-dock panel${voiceMode ? ' voice-dock' : ''}`}>
        <button
          className={`dock-voice${phase === 'listening' || voiceMode ? ' is-hot' : ''}`}
          onClick={() => {
            if (voiceMode && phase === 'listening') {
              if (recordingRef.current) {
                setVoiceHint('Processing your speech…');
                emptyListenRef.current = 0;
                recordingRef.current.stop();
              } else {
                void beginListening();
              }
            } else if (voiceMode) endVoiceCall();
            else void beginListening();
          }}
          aria-label={voiceMode ? (phase === 'listening' ? 'Finish speaking' : 'End voice call') : 'Start voice conversation'}
          disabled={phase === 'transcribing' || phase === 'thinking'}
        >
          {voiceMode && phase !== 'listening' ? <CircleStop size={23} /> : <Mic size={23} />}
          <span className="voice-bars"><i /><i /><i /><i /><i /></span>
        </button>
        {!voiceMode ? (
          <form className="dock-form" onSubmit={(event) => { event.preventDefault(); void sendText(draft); }}>
            <label className="sr-only" htmlFor="home-prompt">Ask JARVIS</label>
            <input
              ref={inputRef}
              id="home-prompt"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Tap JARVIS to talk, or type here (he will speak the answer)…"
              maxLength={12_000}
              disabled={phase === 'thinking' || phase === 'transcribing'}
              autoComplete="off"
            />
            {busy
              ? <button className="send-button stop-button" type="button" onClick={stopEverything} aria-label="Stop"><CircleStop size={19} /></button>
              : <button className="send-button" type="submit" disabled={!draft.trim() || !llmReady} aria-label="Send prompt"><Send size={19} /></button>}
          </form>
        ) : (
          <div className="voice-dock-status">
            <span>{voiceHint || (phase === 'listening' ? 'Speak — then tap the orb when done' : phase === 'speaking' ? 'Speaking out loud — tap orb to interrupt' : phase === 'thinking' || phase === 'transcribing' ? 'Thinking…' : 'Connected')}</span>
            <button type="button" className="end-call-button" onClick={endVoiceCall}>End call</button>
          </div>
        )}
      </div>

      <div className="greeting-strip">
        <span>
          <Sparkles size={14} />
          {voiceMode
            ? 'Voice only — JARVIS talks out loud, no on-screen transcript.'
            : (user.name ? `Standing by, ${user.name.split(' ')[0]}. Tap the orb to talk.` : 'Standing by. Tap the orb to talk.')}
        </span>
        <span>
          {conversationId ? (
            <button type="button" className="text-link" onClick={() => navigate('/chat', { state: { conversationId } })}>Open Chat for text</button>
          ) : (
            <>Private session <ShieldAlert size={13} /></>
          )}
        </span>
      </div>
      {chatError && <div className="home-inline-error" role="alert">{chatError}</div>}
    </section>

    <aside className="right-rail">
      <section className="panel machine-panel status-card">
        <span className="machine-scan" aria-hidden="true" />
        <span className="machine-corner tl" aria-hidden="true" /><span className="machine-corner tr" aria-hidden="true" />
        <span className="machine-corner bl" aria-hidden="true" /><span className="machine-corner br" aria-hidden="true" />
        <div className="panel-title"><div className="title-icon is-live"><Activity size={19} /></div><h2>System Status</h2><span className={`status-dot ${ready ? '' : 'status-warn'}`} title={ready ? 'Backend and database available' : 'Checking or degraded'} /></div>
        <Meter label="CPU Usage" value={status?.cpu_percent} display={status ? `${Math.round(status.cpu_percent)}%` : '—'} />
        <Meter label="Memory" value={status?.memory_percent} display={status ? `${Math.round(status.memory_percent)}%` : '—'} />
        <Meter label="Disk" value={status?.disk_percent} display={status ? `${Math.round(status.disk_percent)}%` : '—'} />
        <div className="network-row"><span>AI Provider</span><strong className={status?.providers.llm ? 'text-green' : 'text-muted'}><i className={`mini-dot ${status?.providers.llm ? '' : 'offline'}`} />{status?.providers.llm ? status.providers.llm_name : 'Unavailable'}</strong></div>
        <div className="network-row"><span>Voice I/O</span><strong className={browserSpeechSupported() || (sttReady && ttsReady) ? 'text-green' : 'text-muted'}><i className={`mini-dot ${browserSpeechSupported() || (sttReady && ttsReady) ? '' : 'offline'}`} />{browserSpeechSupported() ? 'Browser mic ready' : sttReady && ttsReady ? 'STT + TTS ready' : 'Incomplete'}</strong></div>
        <div className="network-row"><span>Network</span><strong className={status?.api_connection && status.database.connected ? 'text-green' : 'text-muted'}><i className={`mini-dot ${status?.api_connection && status.database.connected ? '' : 'offline'}`} />{status?.api_connection && status.database.connected ? 'Connected' : 'Unavailable'}</strong></div>
        <div className="network-row"><span>Tasks in progress</span><strong>{status ? status.active_tasks : '—'}</strong></div>
        <div className="data-ticker" aria-hidden="true"><span>SYS · LINK · CORE · READY · SYS · LINK · CORE · READY · SYS · LINK · CORE · READY · SYS · LINK · CORE · READY · </span></div>
        {statusError && <div className="inline-note" role="status">{statusError}</div>}
      </section>
      <section className="panel machine-panel quick-card">
        <span className="machine-scan" aria-hidden="true" />
        <span className="machine-corner tl" aria-hidden="true" /><span className="machine-corner tr" aria-hidden="true" />
        <span className="machine-corner bl" aria-hidden="true" /><span className="machine-corner br" aria-hidden="true" />
        <div className="panel-title"><div className="title-icon bolt-icon is-live"><Sparkles size={18} /></div><h2>Quick Actions</h2></div>
        <div className="quick-grid">{actions.map(({ title, icon: Icon, onClick }) => <button className="quick-action" key={title} onClick={onClick}><Icon size={22} /><span>{title}</span></button>)}</div>
      </section>
      <section className="panel machine-panel tasks-card">
        <span className="machine-scan" aria-hidden="true" />
        <span className="machine-corner tl" aria-hidden="true" /><span className="machine-corner tr" aria-hidden="true" />
        <span className="machine-corner bl" aria-hidden="true" /><span className="machine-corner br" aria-hidden="true" />
        <div className="panel-title"><div className="title-icon is-live"><Check size={18} /></div><h2>Open Tasks</h2><button className="subtle-link" onClick={() => setModal(true)} aria-label="Add task"><Plus size={16} /></button></div>
        {tasks.length ? <ul className="mini-task-list">{tasks.slice(0, 3).map((task) => <li key={task.id}><span className={`task-priority priority-${task.priority}`} /><span>{task.title}</span><button onClick={async () => { try { const updated = await api.updateTask(task.id, { status: 'completed' }); setTasks((current) => current.filter((item) => item.id !== updated.id)); } catch (error) { setStatusError(error instanceof Error ? error.message : 'Task could not be updated.'); } }} aria-label={`Complete ${task.title}`}><Check size={14} /></button></li>)}</ul> : <p className="empty-state">No open tasks. Add one when you're ready.</p>}
        <button className="text-link" onClick={() => navigate('/tools')}>Manage tasks <ChevronRight size={14} /></button>
      </section>
    </aside>
    {modal && <NewTaskDialog onClose={() => setModal(false)} onCreated={(task) => setTasks((current) => [task, ...current])} />}
  </div>;
}

import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AudioLines, CircleStop, LoaderCircle, MessageSquareText, Mic, MicOff, Play, ShieldCheck, Volume2, VolumeX, X } from 'lucide-react';
import { api, type Integration } from '../lib/api';
import {
  browserSpeechSupported,
  ensureMicrophonePermissionCached,
  getPreferredVoice,
  playAudioBlob,
  setPreferredVoice,
  speakWithBrowser,
  startBrowserListen,
  startVoiceCapture,
  forSpeech,
  type LiveListenHandle,
  type RecordingHandle,
} from '../lib/voiceConversation';

type Phase = 'idle' | 'listening' | 'transcribing' | 'thinking' | 'speaking';
const FISH_VOICE = getPreferredVoice();

export default function VoicePage() {
  const navigate = useNavigate();
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const audio = useRef<HTMLAudioElement | null>(null);
  const objectUrl = useRef<string | null>(null);
  const ttsAbort = useRef<AbortController | null>(null);
  const chatAbort = useRef<AbortController | null>(null);
  const speakAbort = useRef<AbortController | null>(null);
  const recordingTimeout = useRef<number | null>(null);
  const recordingRef = useRef<RecordingHandle | LiveListenHandle | null>(null);
  const voiceLoopRef = useRef(false);
  const listenTokenRef = useRef(0);
  const conversationIdRef = useRef<string | undefined>();
  const beginRef = useRef<() => Promise<void>>(async () => undefined);

  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [languageHint, setLanguageHint] = useState('');
  const [ttsText, setTtsText] = useState('');
  const [voice, setVoice] = useState(FISH_VOICE);
  const [speed, setSpeed] = useState(1);
  const [volume, setVolume] = useState(1);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [level, setLevel] = useState(0);
  const [inCall, setInCall] = useState(false);
  const [llmReady, setLlmReady] = useState(false);
  const [ttsReadyStatus, setTtsReadyStatus] = useState(false);
  const [showLab, setShowLab] = useState(false);

  useEffect(() => {
    void api.integrations().then((data) => setIntegrations(data.items)).catch(() => setIntegrations([]));
    void api.status().then((s) => {
      setLlmReady(Boolean(s.providers.llm));
      setTtsReadyStatus(Boolean(s.providers.text_to_speech));
    }).catch(() => undefined);
    return () => {
      voiceLoopRef.current = false;
      listenTokenRef.current += 1;
      recordingRef.current?.stop();
      chatAbort.current?.abort();
      speakAbort.current?.abort();
      if (recordingTimeout.current) window.clearTimeout(recordingTimeout.current);
      if (recorder.current?.state === 'recording') { recorder.current.onstop = null; recorder.current.stop(); }
      stream.current?.getTracks().forEach((track) => track.stop());
      ttsAbort.current?.abort();
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      audio.current?.pause();
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    };
  }, []);

  const sttReady = integrations.find((item) => item.id === 'speech_to_text')?.configured ?? false;
  const ttsReady = integrations.find((item) => item.id === 'text_to_speech')?.configured ?? ttsReadyStatus;

  const speakReply = async (text: string) => {
    const spoken = forSpeech(text);
    if (!spoken) return;
    setPhase('speaking');
    speakAbort.current?.abort();
    const controller = new AbortController();
    speakAbort.current = controller;
    try {
      if (ttsReady) {
        try {
          const blob = await api.speak(spoken, voice.trim() || getPreferredVoice(), Math.min(Math.max(speed, 1.05), 1.15), controller.signal);
          if (controller.signal.aborted) return;
          await playAudioBlob(blob, volume, controller.signal);
          return;
        } catch {
          if (controller.signal.aborted) return;
        }
      }
      await speakWithBrowser(spoken, controller.signal);
    } finally {
      if (speakAbort.current === controller) speakAbort.current = null;
    }
  };

  const runTurn = async (text: string) => {
    setPhase('thinking');
    setError('');
    chatAbort.current?.abort();
    const controller = new AbortController();
    chatAbort.current = controller;
    let answer = '';
    let failed = false;
    try {
      await api.streamChat(
        { message: text, conversation_id: conversationIdRef.current, client_message_id: crypto.randomUUID(), mode: 'voice' },
        (event, data) => {
          if (event === 'delta' && typeof data.text === 'string') {
            answer += data.text;
          } else if (event === 'done' && typeof data.conversation_id === 'string') conversationIdRef.current = data.conversation_id;
          else if (event === 'error') {
            failed = true;
            setError(typeof data.message === 'string' ? data.message : 'Conversation failed.');
          }
        },
        controller.signal,
      );
      if (!failed) {
        if (!answer.trim()) {
          answer = '';
          await api.streamChat(
            { message: text, client_message_id: crypto.randomUUID(), mode: 'voice' },
            (event, data) => {
              if (event === 'delta' && typeof data.text === 'string') answer += data.text;
              else if (event === 'done' && typeof data.conversation_id === 'string') conversationIdRef.current = data.conversation_id;
              else if (event === 'error') {
                failed = true;
                setError(typeof data.message === 'string' ? data.message : 'Conversation failed.');
              }
            },
            controller.signal,
          );
        }
        if (!failed && !answer.trim()) {
          setError('JARVIS returned an empty reply. Please try again.');
          failed = true;
        } else if (!failed) {
          await speakReply(answer);
        }
      }
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Conversation failed.');
      failed = true;
    } finally {
      if (chatAbort.current === controller) chatAbort.current = null;
      setPhase('idle');
      setLevel(0);
      if (!failed && voiceLoopRef.current) {
        window.setTimeout(() => { if (voiceLoopRef.current) void beginRef.current(); }, 160);
      }
    }
  };

  const beginCallListen = async () => {
    if (!llmReady) { setError('The AI provider is not connected.'); return; }
    recordingRef.current?.stop();
    recordingRef.current = null;
    const token = ++listenTokenRef.current;
    setInCall(true);
    voiceLoopRef.current = true;
    setError('');
    setPhase('listening');
    setLevel(0.12);
    try {
      await ensureMicrophonePermissionCached();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Microphone permission is required.');
      setPhase('idle');
      setInCall(false);
      voiceLoopRef.current = false;
      return;
    }
    if (listenTokenRef.current !== token || !voiceLoopRef.current) return;
    try {
      let text = '';
      if (browserSpeechSupported()) {
        const handle = startBrowserListen({
          endSilenceMs: 280,
          maxMs: 12_000,
          onPartial: (value) => setLevel(value ? Math.min(1, 0.35 + value.length * 0.02) : 0.18),
        });
        recordingRef.current = handle;
        text = (await handle.promise).trim();
        recordingRef.current = null;
      } else {
        if (!sttReady) throw new Error('Speech recognition is unavailable in this browser, and server STT is not configured.');
        setPhase('transcribing');
        const handle = await startVoiceCapture({ maxMs: 12_000, silenceMs: 700, onLevel: setLevel });
        recordingRef.current = handle;
        const file = await handle.promise;
        recordingRef.current = null;
        if (listenTokenRef.current !== token || !voiceLoopRef.current) return;
        const result = await api.transcribe(file);
        text = result.text.trim();
      }
      if (listenTokenRef.current !== token || !voiceLoopRef.current) return;
      if (!text) {
        setPhase('listening');
        window.setTimeout(() => { if (voiceLoopRef.current) void beginRef.current(); }, 400);
        return;
      }
      await runTurn(text);
    } catch (e) {
      recordingRef.current = null;
      if (listenTokenRef.current !== token) return;
      const message = e instanceof Error ? e.message : 'Voice capture failed.';
      if (/no-speech|aborted|network|Speech recognition failed/i.test(message) && voiceLoopRef.current) {
        window.setTimeout(() => { if (voiceLoopRef.current) void beginRef.current(); }, 500);
        return;
      }
      setError(message);
      setPhase('idle');
      setInCall(false);
      voiceLoopRef.current = false;
    }
  };
  beginRef.current = beginCallListen;

  const endCall = () => {
    voiceLoopRef.current = false;
    listenTokenRef.current += 1;
    recordingRef.current?.stop();
    recordingRef.current = null;
    chatAbort.current?.abort();
    speakAbort.current?.abort();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    setInCall(false);
    setPhase('idle');
    setLevel(0);
  };

  const onOrbClick = () => {
    if (phase === 'listening') { recordingRef.current?.stop(); return; }
    if (phase === 'speaking') {
      speakAbort.current?.abort();
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
      if (inCall) { voiceLoopRef.current = true; void beginCallListen(); }
      return;
    }
    if (phase === 'thinking' || phase === 'transcribing') { endCall(); return; }
    void beginCallListen();
  };

  const startRecording = async () => {
    setError(''); setNotice(''); setTranscript('');
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { setError('This browser does not support microphone recording.'); return; }
    if (!sttReady && !browserSpeechSupported()) { setError('Speech transcription is not configured.'); return; }
    if (browserSpeechSupported() && !sttReady) {
      setBusy(true);
      try {
        await ensureMicrophonePermissionCached();
        const handle = startBrowserListen({});
        setRecording(true);
        recordingRef.current = handle;
        const text = await handle.promise;
        recordingRef.current = null;
        setRecording(false);
        setTranscript(text);
        setNotice(text ? 'Transcription complete (browser speech).' : 'No speech detected.');
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Transcription failed.');
        setRecording(false);
      } finally { setBusy(false); }
      return;
    }
    try {
      const deviceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = deviceStream;
      const preferred = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : undefined;
      const instance = new MediaRecorder(deviceStream, preferred ? { mimeType: preferred } : undefined);
      chunks.current = [];
      instance.ondataavailable = (event) => { if (event.data.size) chunks.current.push(event.data); };
      instance.onstop = async () => {
        if (recordingTimeout.current) window.clearTimeout(recordingTimeout.current);
        recordingTimeout.current = null;
        deviceStream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks.current, { type: instance.mimeType || 'audio/webm' });
        const file = new File([blob], `jarvis-recording.${blob.type.includes('mp4') ? 'm4a' : 'webm'}`, { type: blob.type });
        if (!file.size) { setError('No audio was captured. Try recording again.'); return; }
        setBusy(true);
        try { const result = await api.transcribe(file, languageHint.trim()); setTranscript(result.text); setNotice(`Transcription complete${result.language ? ` · ${result.language}` : ''}.`); }
        catch (e) { setError(e instanceof Error ? e.message : 'Transcription failed.'); }
        finally { setBusy(false); }
      };
      recorder.current = instance;
      instance.start(250);
      setRecording(true);
      recordingTimeout.current = window.setTimeout(() => { if (instance.state === 'recording') { setNotice('Maximum recording time reached.'); instance.stop(); setRecording(false); } }, 120_000);
    } catch (e) {
      setError(e instanceof DOMException && e.name === 'NotAllowedError' ? 'Microphone permission was denied.' : 'The microphone could not be started.');
    }
  };

  const stopRecording = () => {
    if (recordingTimeout.current) window.clearTimeout(recordingTimeout.current);
    recordingTimeout.current = null;
    if (recorder.current?.state === 'recording') { recorder.current.stop(); setRecording(false); }
    recordingRef.current?.stop();
  };

  const playSpeech = async () => {
    if (!ttsText.trim()) return;
    setBusy(true); setError(''); setNotice('');
    const controller = new AbortController(); ttsAbort.current = controller;
    try {
      if (ttsReady) {
        const blob = await api.speak(ttsText.trim(), voice.trim() || getPreferredVoice(), speed, controller.signal);
        if (controller.signal.aborted) return;
        if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
        objectUrl.current = URL.createObjectURL(blob);
        const player = new Audio(objectUrl.current);
        player.volume = Math.max(0, Math.min(1, volume));
        player.onended = () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current); objectUrl.current = null; audio.current = null; };
        audio.current = player;
        await player.play();
        setNotice('Speech playback started.');
      } else {
        await speakWithBrowser(ttsText.trim(), controller.signal);
        setNotice('Played with browser voice (server TTS unavailable).');
      }
    } catch (e) {
      if (controller.signal.aborted) setNotice('Speech generation stopped.');
      else setError(e instanceof Error ? e.message : 'Speech could not be played.');
    } finally { if (ttsAbort.current === controller) ttsAbort.current = null; setBusy(false); }
  };

  const stopSpeech = () => {
    ttsAbort.current?.abort();
    audio.current?.pause();
    if (audio.current) { audio.current.currentTime = 0; audio.current.onended = null; audio.current = null; }
    if (objectUrl.current) { URL.revokeObjectURL(objectUrl.current); objectUrl.current = null; }
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    setNotice('Speech stopped.');
  };

  const hudState = phase === 'listening' ? 'listening' : phase === 'speaking' ? 'speaking' : phase === 'thinking' || phase === 'transcribing' ? 'working' : 'idle';
  const statusLabel = phase === 'listening' ? 'Listening' : phase === 'speaking' ? 'Speaking' : phase === 'thinking' || phase === 'transcribing' ? 'Thinking' : inCall ? 'Connected' : 'Ready';

  return <div className={`voice-page${inCall ? ' is-live' : ''}`}>
    <section className={`voice-hero state-${hudState}${inCall ? ' in-call' : ''}`} aria-label="JARVIS voice call">
      <div className="voice-hero-ambient" aria-hidden="true">
        <span className="voice-hero-scan" />
        <span className="voice-hero-ring r1" /><span className="voice-hero-ring r2" /><span className="voice-hero-ring r3" />
      </div>

      <header className="voice-hero-top">
        <div>
          <span className="eyebrow">VOICE</span>
          <h2>JARVIS</h2>
        </div>
        <span className={`voice-live-chip ${llmReady ? 'ready' : 'unready'}`}>
          <i className={inCall ? 'is-live' : ''} />
          {inCall ? statusLabel : llmReady ? 'Online' : 'Offline'}
        </span>
      </header>

      <button
        type="button"
        className={`voice-orb hud-trigger state-${hudState}`}
        onClick={onOrbClick}
        style={{ ['--voice-level' as string]: String(Math.max(level, inCall ? 0.14 : 0.08)) }}
        aria-label={inCall ? 'Voice call control' : 'Start voice call'}
      >
        <span className="ring-orbit ring-orbit-one" aria-hidden="true" />
        <span className="ring-orbit ring-orbit-two" aria-hidden="true" />
        <span className="ring-orbit ring-orbit-three" aria-hidden="true" />
        <span className="voice-orb-glow" aria-hidden="true" />
        <strong>JARVIS</strong>
        <span className="core-hint">{statusLabel}</span>
        <span className="voice-level-meter" aria-hidden="true">
          <i style={{ transform: `scaleY(${0.3 + level * 0.7})` }} />
          <i style={{ transform: `scaleY(${0.4 + level * 0.85})` }} />
          <i style={{ transform: `scaleY(${0.25 + level})` }} />
          <i style={{ transform: `scaleY(${0.45 + level * 0.75})` }} />
          <i style={{ transform: `scaleY(${0.3 + level * 0.65})` }} />
        </span>
      </button>

      <p className="voice-hero-copy">
        {inCall
          ? (phase === 'listening' ? 'Speak naturally, then pause.' : phase === 'speaking' ? 'JARVIS is talking — tap the orb to interrupt.' : 'Working…')
          : 'Tap the orb to talk. JARVIS replies out loud — no transcript on this screen.'}
      </p>

      <div className="voice-call-actions">
        {!inCall
          ? <button className="primary-button" onClick={() => void beginCallListen()} disabled={!llmReady || busy}><Mic size={16} />Start call</button>
          : <button className="danger-button" onClick={endCall}><X size={16} />End call</button>}
        {conversationIdRef.current ? (
          <button className="secondary-button" onClick={() => navigate('/chat', { state: { conversationId: conversationIdRef.current } })}>
            <MessageSquareText size={15} /> Chat history
          </button>
        ) : null}
      </div>

      {(error || notice) && !showLab && (
        <div className={`voice-hero-notice ${error ? 'is-error' : ''}`} role={error ? 'alert' : 'status'}>{error || notice}</div>
      )}
    </section>

    <div className="voice-lab-toggle-row">
      <button type="button" className={`voice-lab-toggle${showLab ? ' open' : ''}`} onClick={() => setShowLab((value) => !value)} aria-expanded={showLab}>
        <AudioLines size={16} />
        {showLab ? 'Hide lab tools' : 'Lab tools'}
        <span>STT · TTS preview</span>
      </button>
      <span className="voice-privacy-inline"><MicOff size={13} /> Mic only while the call is open</span>
    </div>

    {showLab && (
      <div className="voice-lab">
        <section className="panel voice-card recording-card">
          <div className="voice-card-head">
            <div className="voice-orbit"><Mic size={22} /></div>
            <div>
              <span className="eyebrow">SPEECH TO TEXT</span>
              <h3>Transcribe</h3>
            </div>
          </div>
          <div className={`record-status ${recording ? 'is-recording' : ''}`}><span className="status-dot" />{recording ? 'Recording' : busy ? 'Processing…' : 'Idle'}</div>
          <label className="field-label" htmlFor="language-hint">Language hint</label>
          <input id="language-hint" value={languageHint} onChange={(event) => setLanguageHint(event.target.value)} maxLength={80} placeholder="Optional — e.g. English" />
          <div className="voice-controls">
            <button className={recording ? 'danger-button' : 'primary-button'} onClick={recording ? stopRecording : () => void startRecording()} disabled={busy || inCall}>
              {busy ? <LoaderCircle size={17} className="spin" /> : recording ? <CircleStop size={17} /> : <Mic size={17} />}
              {recording ? 'Stop' : busy ? 'Working…' : 'Record'}
            </button>
            <span className="microphone-note"><ShieldCheck size={14} /> Permission required</span>
          </div>
          {transcript ? (
            <div className="transcript-box">
              <div className="panel-title">
                <span className="eyebrow">RESULT</span>
                <div className="transcript-actions">
                  <button className="subtle-link" onClick={() => void navigator.clipboard?.writeText(transcript)}>Copy</button>
                  <button className="secondary-button" onClick={() => navigate('/chat', { state: { prompt: transcript } })}><MessageSquareText size={13} /> Chat</button>
                </div>
              </div>
              <p>{transcript}</p>
            </div>
          ) : null}
        </section>

        <section className="panel voice-card speech-card">
          <div className="voice-card-head">
            <div className="voice-orbit muted-orbit"><Volume2 size={22} /></div>
            <div>
              <span className="eyebrow">TEXT TO SPEECH</span>
              <h3>Preview voice</h3>
            </div>
          </div>
          <label htmlFor="tts-text" className="field-label">Sample line</label>
          <textarea id="tts-text" rows={3} maxLength={5000} placeholder="Type a short line to preview…" value={ttsText} onChange={(event) => setTtsText(event.target.value)} />
          <div className="voice-settings-grid">
            <label className="field-label" htmlFor="tts-voice">Voice ID
              <input id="tts-voice" value={voice} onChange={(event) => { setVoice(event.target.value); setPreferredVoice(event.target.value); }} maxLength={80} />
            </label>
            <label className="field-label" htmlFor="tts-speed">Speed <span>{speed.toFixed(1)}×</span>
              <input id="tts-speed" type="range" min="0.5" max="2" step="0.1" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} />
            </label>
            <label className="field-label" htmlFor="tts-volume">Volume <span>{Math.round(volume * 100)}%</span>
              <input id="tts-volume" type="range" min="0" max="1" step="0.05" value={volume} onChange={(event) => setVolume(Number(event.target.value))} />
            </label>
          </div>
          <div className="voice-controls">
            <button className="primary-button" onClick={() => void playSpeech()} disabled={!ttsText.trim() || busy || inCall}><Play size={16} />{busy ? 'Preparing…' : 'Play'}</button>
            <button className="secondary-button" onClick={stopSpeech}><VolumeX size={16} />Stop</button>
          </div>
          <span className="provider-footnote">{ttsReady ? 'Fish Audio connected' : 'Browser voice fallback'}</span>
        </section>
      </div>
    )}

    {(error || notice) && showLab && <div className={error ? 'notice-error' : 'notice-success'} role={error ? 'alert' : 'status'}>{error || notice}</div>}
  </div>;
}

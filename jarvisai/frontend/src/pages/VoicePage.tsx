import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AudioLines, CircleStop, LoaderCircle, MessageSquareText, Mic, MicOff, Play, ShieldCheck, Volume2, VolumeX } from 'lucide-react';
import { api, type Integration } from '../lib/api';

export default function VoicePage() {
  const navigate = useNavigate();
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const audio = useRef<HTMLAudioElement | null>(null);
  const objectUrl = useRef<string | null>(null);
  const ttsAbort = useRef<AbortController | null>(null);
  const recordingTimeout = useRef<number | null>(null);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [languageHint, setLanguageHint] = useState('');
  const [ttsText, setTtsText] = useState('');
  const [voice, setVoice] = useState('alloy');
  const [speed, setSpeed] = useState(1);
  const [volume, setVolume] = useState(1);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    void api.integrations().then((data) => setIntegrations(data.items)).catch(() => setIntegrations([]));
    return () => {
      if (recordingTimeout.current) window.clearTimeout(recordingTimeout.current);
      if (recorder.current?.state === 'recording') { recorder.current.onstop = null; recorder.current.stop(); }
      stream.current?.getTracks().forEach((track) => track.stop());
      ttsAbort.current?.abort();
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      audio.current?.pause();
    };
  }, []);
  const sttReady = integrations.find((item) => item.id === 'speech_to_text')?.configured ?? false;
  const ttsReady = integrations.find((item) => item.id === 'text_to_speech')?.configured ?? false;
  const startRecording = async () => {
    setError(''); setNotice(''); setTranscript('');
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { setError('This browser does not support microphone recording.'); return; }
    if (!sttReady) { setError('Speech transcription is not configured. Configure the managed speech service before recording.'); return; }
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
        catch (e) { setError(e instanceof Error ? e.message : 'Transcription failed. Your recording was not sent again automatically.'); }
        finally { setBusy(false); }
      };
      recorder.current = instance;
      instance.start(250);
      setRecording(true);
      recordingTimeout.current = window.setTimeout(() => { if (instance.state === 'recording') { setNotice('Maximum recording time reached; sending this recording for transcription.'); instance.stop(); setRecording(false); } }, 120_000);
    } catch (e) {
      setError(e instanceof DOMException && e.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow microphone access in your browser to use voice input.' : 'The microphone could not be started. Check device availability and permissions.');
    }
  };
  const stopRecording = () => { if (recordingTimeout.current) window.clearTimeout(recordingTimeout.current); recordingTimeout.current = null; if (recorder.current?.state === 'recording') { recorder.current.stop(); setRecording(false); } };
  const playSpeech = async () => {
    if (!ttsReady) { setError('Text-to-speech is not configured. Add a supported provider through protected project settings.'); return; }
    if (!ttsText.trim()) return;
    setBusy(true); setError(''); setNotice('');
    const controller = new AbortController(); ttsAbort.current = controller;
    try {
      const blob = await api.speak(ttsText.trim(), voice.trim() || 'alloy', speed, controller.signal);
      if (controller.signal.aborted) return;
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = URL.createObjectURL(blob);
      const player = new Audio(objectUrl.current);
      player.volume = Math.max(0, Math.min(1, volume));
      player.onended = () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current); objectUrl.current = null; audio.current = null; };
      audio.current = player;
      await player.play();
      setNotice('Speech playback started. Use Stop to interrupt it.');
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
    setNotice('Speech stopped.');
  };
  return <div className="page-stack voice-page">
    <div className="section-heading"><div><span className="eyebrow">VOICE INTERACTION</span><h2>Speak naturally.</h2><p>Microphone access stays under your control. JARVIS listens only while you start a recording.</p></div><span className={`readiness-chip ${sttReady ? 'ready' : 'unready'}`}><i />{sttReady ? 'Transcription connected' : 'Transcription not configured'}</span></div>
    <div className="voice-grid">
      <section className="panel voice-card recording-card"><div className="voice-orbit"><AudioLines size={28} /></div><span className="eyebrow">SPEECH TO TEXT</span><h3>Voice input</h3><p>Record a single phrase or request, then stop to send it for transcription. No continuous listening is active.</p><div className={`record-status ${recording ? 'is-recording' : ''}`}><span className="status-dot" />{recording ? 'Recording · microphone active' : busy ? 'Processing recording…' : 'Microphone idle'}</div>
        <label className="field-label" htmlFor="language-hint">Language context (optional)</label><input id="language-hint" value={languageHint} onChange={(event) => setLanguageHint(event.target.value)} maxLength={80} placeholder="e.g. English, Spanish, or a domain term" />
        <div className="voice-controls"><button className={recording ? 'danger-button' : 'primary-button'} onClick={recording ? stopRecording : startRecording} disabled={busy || (!sttReady && !recording)}>{busy ? <LoaderCircle size={17} className="spin" /> : recording ? <CircleStop size={17} /> : <Mic size={17} />}{recording ? 'Stop & transcribe' : busy ? 'Processing…' : 'Start recording'}</button><span className="microphone-note"><ShieldCheck size={14} /> Browser permission required</span></div>
        {transcript && <div className="transcript-box"><div className="panel-title"><span className="eyebrow">TRANSCRIPT</span><div className="transcript-actions"><button className="subtle-link" onClick={() => void navigator.clipboard?.writeText(transcript)} title="Copy transcript">Copy</button><button className="secondary-button" onClick={() => navigate('/chat', { state: { prompt: transcript } })}><MessageSquareText size={13} /> Send to Chat</button></div></div><p>{transcript}</p></div>}
      </section>
      <section className="panel voice-card speech-card"><div className="voice-orbit muted-orbit"><Volume2 size={27} /></div><span className="eyebrow">TEXT TO SPEECH</span><h3>Voice output</h3><p>Generate audio only when a supported TTS provider is connected.</p><label htmlFor="tts-text" className="field-label">Text to speak</label><textarea id="tts-text" rows={5} maxLength={5000} placeholder="Enter text to speak…" value={ttsText} onChange={(event) => setTtsText(event.target.value)} />
        <div className="voice-settings-grid"><label className="field-label" htmlFor="tts-voice">Voice identifier<input id="tts-voice" value={voice} onChange={(event) => setVoice(event.target.value)} maxLength={80} placeholder="Provider voice name" /></label><label className="field-label" htmlFor="tts-speed">Speed <span>{speed.toFixed(1)}×</span><input id="tts-speed" type="range" min="0.5" max="2" step="0.1" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} /></label><label className="field-label" htmlFor="tts-volume">Playback volume <span>{Math.round(volume * 100)}%</span><input id="tts-volume" type="range" min="0" max="1" step="0.05" value={volume} onChange={(event) => setVolume(Number(event.target.value))} /></label></div>
        <div className="voice-controls"><button className="primary-button" onClick={() => void playSpeech()} disabled={!ttsReady || !ttsText.trim() || busy}><Play size={16} />{busy ? 'Preparing…' : 'Play speech'}</button><button className="secondary-button" onClick={stopSpeech}><VolumeX size={16} />Stop</button></div><span className="provider-footnote">{ttsReady ? 'Provider connection verified. Natural pauses depend on the selected service.' : 'TTS endpoint and protected provider key are required.'}</span>
      </section>
    </div>
    {(error || notice) && <div className={error ? 'notice-error' : 'notice-success'} role={error ? 'alert' : 'status'}>{error || notice}</div>}
    <section className="panel privacy-banner"><MicOff size={17} /><div><strong>Privacy first</strong><span>Continuous listening and wake-word detection are off. Recording audio is sent only after you stop; the recording itself is not retained by JARVIS.</span></div></section>
  </div>;
}

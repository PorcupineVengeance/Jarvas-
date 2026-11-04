import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AudioLines, Check, LockKeyhole, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import { api, type Integration, type User } from '../lib/api';
import { DEFAULT_FISH_VOICE, getPreferredVoice, setPreferredVoice } from '../lib/voiceConversation';

const modes = [
  ['auto', 'Auto', 'Choose a helpful mode based on the request'],
  ['normal', 'Normal', 'Everyday conversation and questions'],
  ['research', 'Research', 'Evidence-conscious analysis and source handling'],
  ['assistant', 'Assistant', 'Personal assistance and daily tasks'],
  ['developer', 'Developer', 'Programming, debugging and technical work'],
  ['automation', 'Automation', 'Approved, permission-checked actions'],
  ['focus', 'Focus', 'Concise answers with minimal interruptions'],
];

export default function SettingsPage({ user }: { user: User }) {
  const [mode, setMode] = useState(localStorage.getItem('jarvis.mode') || 'auto');
  const [voiceId, setVoiceId] = useState(getPreferredVoice());
  const [savedVoice, setSavedVoice] = useState(false);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const navigate = useNavigate();
  useEffect(() => { void api.integrations().then((result) => setIntegrations(result.items)).catch(() => undefined); }, []);
  const tts = integrations.find((item) => item.id === 'text_to_speech');
  const wake = integrations.find((item) => item.id === 'wake_word');
  const llm = integrations.find((item) => item.id === 'llm');
  const stt = integrations.find((item) => item.id === 'speech_to_text');
  const research = integrations.find((item) => item.id === 'research');

  const saveVoice = () => {
    setPreferredVoice(voiceId.trim() || DEFAULT_FISH_VOICE);
    setVoiceId(getPreferredVoice());
    setSavedVoice(true);
    window.setTimeout(() => setSavedVoice(false), 1800);
  };

  return <div className="page-stack settings-page">
    <div className="section-heading"><div><span className="eyebrow">PREFERENCES</span><h2>Settings</h2><p>Control how JARVIS responds and when it can use your devices.</p></div></div>

    <section className="panel settings-section">
      <div className="section-title"><SlidersHorizontal size={18} /><div><h3>Assistant mode</h3><p>Choose a default interaction style. You can also switch modes from Chat.</p></div></div>
      <label className="field-label" htmlFor="default-mode">Default mode</label>
      <select id="default-mode" className="settings-select" value={mode} onChange={(event) => { setMode(event.target.value); localStorage.setItem('jarvis.mode', event.target.value); }}>
        {modes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <p className="setting-help">{modes.find(([value]) => value === mode)?.[2]}</p>
    </section>

    <section className="panel settings-section">
      <div className="section-title"><AudioLines size={18} /><div><h3>Voice & privacy</h3><p>Microphone access is requested only when you start a call or recording.</p></div></div>
      <div className="setting-row">
        <div><strong>Continuous listening</strong><span>{wake?.configured ? 'Wake-word provider is connected. Continuous listening remains off by default.' : 'Off — wake-word stays disabled unless enabled in the backend.'}</span></div>
        <button type="button" className="toggle-button" aria-label="Continuous listening off" aria-pressed={false} disabled title="Continuous listening stays off for privacy">Off</button>
      </div>
      <div className="setting-row">
        <div><strong>Speech transcription</strong><span>{stt?.detail || 'Checking provider status…'}</span></div>
        <span className={`readiness-chip ${stt?.configured ? 'ready' : 'unready'}`}><i />{stt?.configured ? 'Connected' : 'Not configured'}</span>
      </div>
      <div className="setting-row">
        <div><strong>Text to speech</strong><span>{tts?.configured ? 'Fish Audio (or configured TTS) is connected.' : 'Unavailable until a supported provider is configured.'}</span></div>
        <span className={`readiness-chip ${tts?.configured ? 'ready' : 'unready'}`}><i />{tts?.configured ? 'Connected' : 'Not configured'}</span>
      </div>
      <label className="field-label" htmlFor="settings-voice">Fish Audio voice ID</label>
      <div className="settings-inline-row">
        <input id="settings-voice" className="settings-select" value={voiceId} onChange={(event) => setVoiceId(event.target.value)} maxLength={80} placeholder={DEFAULT_FISH_VOICE} />
        <button type="button" className="primary-button" onClick={saveVoice}>{savedVoice ? <><Check size={15} /> Saved</> : 'Save voice'}</button>
      </div>
      <p className="setting-help">Used for home and voice-page talk-back. Default: <code>{DEFAULT_FISH_VOICE}</code></p>
      <div className="safety-note"><ShieldCheck size={15} /><span>Voice calls do not show transcripts on screen. Utility recordings are sent only after you stop.</span></div>
    </section>

    <section className="panel settings-section">
      <div className="section-title"><SlidersHorizontal size={18} /><div><h3>AI provider</h3><p>Provider selection is configured server-side, never in the browser bundle.</p></div>
        <span className={`readiness-chip ${llm?.configured ? 'ready' : 'unready'}`}><i />{llm?.status || 'Checking'}</span>
      </div>
      <p className="setting-help">{llm?.detail || 'Provider status is loading.'} Research: {research?.configured ? research.detail : 'not configured'}.</p>
    </section>

    <section className="panel settings-section">
      <div className="section-title"><LockKeyhole size={18} /><div><h3>Account & security</h3><p>Signed in as {user.name}{user.email ? ` · ${user.email}` : ''}. Sessions are validated by the backend.</p></div></div>
      <p className="setting-help">JARVIS does not expose server keys to the browser. Provider secrets stay in protected project settings.</p>
      <div className="settings-actions">
        <button className="secondary-button" onClick={() => navigate('/voice')}><AudioLines size={15} /> Open Voice</button>
        <button className="secondary-button" onClick={() => navigate('/about')}><ShieldCheck size={15} /> Security and limitations</button>
      </div>
    </section>
  </div>;
}

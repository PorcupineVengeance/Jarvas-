import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Apple, AudioLines, Check, Download, FolderOpen, Globe2, LockKeyhole, Monitor, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import { api, type DesktopInfo, type Integration, type User } from '../lib/api';
import {
  detectBrowserCapabilities,
  getBrowserPermissions,
  requestBrowserPermission,
  setBrowserPermission,
  type BrowserPermissionKey,
  type BrowserPermissions,
} from '../lib/browserAccess';
import { isJarvisDesktop, pickDesktopFolders, revealDesktopDataDir } from '../lib/desktop';
import { DEFAULT_FISH_VOICE, getPreferredVoice, isWakeWordEnabled, setPreferredVoice, setWakeWordEnabled } from '../lib/voiceConversation';

const BROWSER_PERM_ROWS: Array<{ key: BrowserPermissionKey; title: string; help: string }> = [
  { key: 'geolocation', title: 'Location (GPS)', help: 'Precise weather and “where am I” using your browser location.' },
  { key: 'notifications', title: 'Notifications', help: 'Allow JARVIS to show browser notifications when you ask.' },
  { key: 'clipboard', title: 'Clipboard', help: 'Copy or read clipboard text when you request it.' },
  { key: 'battery', title: 'Battery status', help: 'Report charge level when this browser supports it.' },
  { key: 'share', title: 'Share sheet', help: 'Open the device share menu with links or text.' },
  { key: 'wake_lock', title: 'Keep screen awake', help: 'Prevent sleep while voice/chat needs the screen.' },
  { key: 'files', title: 'Local file picker', help: 'Let JARVIS ask you to upload files from this device.' },
  { key: 'camera', title: 'Camera capture', help: 'Take a photo with your camera and upload it to JARVIS.' },
  { key: 'screen_capture', title: 'Screen capture', help: 'Capture your screen/tab when you approve the browser prompt.' },
  { key: 'vibrate', title: 'Vibration', help: 'Haptic buzz on phones for alerts (when supported).' },
  { key: 'downloads', title: 'File downloads', help: 'Save notes or text files JARVIS generates onto this device.' },
];

const modes = [
  ['auto', 'Auto', 'Choose a helpful mode based on the request'],
  ['normal', 'Normal', 'Everyday conversation and questions'],
  ['research', 'Research', 'Evidence-conscious analysis and source handling'],
  ['assistant', 'Assistant', 'Personal assistance and daily tasks'],
  ['developer', 'Developer', 'Programming, debugging and technical work'],
  ['automation', 'Automation', 'Approved, permission-checked actions'],
  ['focus', 'Focus', 'Concise answers with minimal interruptions'],
];

const DEFAULT_FOLDERS = ['~/Desktop', '~/Documents', '~/Downloads'];

function DesktopDownloadCard({ info }: { info: DesktopInfo | null }) {
  if (isJarvisDesktop() || info?.is_desktop) {
    return (
      <section className="panel settings-section">
        <div className="section-title">
          <Monitor size={18} />
          <div>
            <h3>Desktop connected</h3>
            <p>You are running JARVIS Desktop. Computer control is managed below.</p>
          </div>
          <span className="readiness-chip ready"><i />Local</span>
        </div>
        <p className="setting-help">{info?.notice || 'This install can help with apps and files you authorize.'}</p>
      </section>
    );
  }

  const mac = info?.downloads.mac;
  const win = info?.downloads.windows;
  const configured = Boolean(info?.downloads.configured && (mac || win));

  return (
    <section className="panel settings-section">
      <div className="section-title">
        <Download size={18} />
        <div>
          <h3>Get Desktop</h3>
          <p>Install JARVIS on your laptop so it can open apps, folders, and help with everyday tasks — only where you allow.</p>
        </div>
      </div>
      <div className="desktop-download-row">
        {mac ? (
          <a className="primary-button desktop-download-link" href={mac}><Apple size={15} /> Download for macOS</a>
        ) : (
          <button type="button" className="secondary-button" disabled title="Publish a release and set JARVIS_DESKTOP_DOWNLOAD_BASE"><Apple size={15} /> macOS build</button>
        )}
        {win ? (
          <a className="primary-button desktop-download-link" href={win}><Monitor size={15} /> Download for Windows</a>
        ) : (
          <button type="button" className="secondary-button" disabled title="Publish a release and set JARVIS_DESKTOP_DOWNLOAD_BASE"><Monitor size={15} /> Windows build</button>
        )}
      </div>
      <p className="setting-help">
        {configured
          ? 'Installers come from your configured release URL. Prefer the official download for your OS.'
          : 'Set JARVIS_DESKTOP_DOWNLOAD_BASE to your GitHub Releases (or CDN) URL that hosts JARVIS-mac.dmg and JARVIS-win.exe. Until then, build locally with desktop/scripts/build-desktop.sh.'}
      </p>
    </section>
  );
}

export default function SettingsPage({ user }: { user: User }) {
  const [mode, setMode] = useState(localStorage.getItem('jarvis.mode') || 'auto');
  const [voiceId, setVoiceId] = useState(getPreferredVoice());
  const [savedVoice, setSavedVoice] = useState(false);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [desktopInfo, setDesktopInfo] = useState<DesktopInfo | null>(null);
  const [computerControl, setComputerControl] = useState(true);
  const [liveWeb, setLiveWeb] = useState(true);
  const [bluetooth, setBluetooth] = useState(false);
  const [fullDeviceAccess, setFullDeviceAccess] = useState(false);
  const [allowedPaths, setAllowedPaths] = useState<string[]>(DEFAULT_FOLDERS);
  const [pathDraft, setPathDraft] = useState('');
  const [desktopBusy, setDesktopBusy] = useState(false);
  const [desktopMessage, setDesktopMessage] = useState('');
  const [desktopError, setDesktopError] = useState('');
  const [wakeWord, setWakeWord] = useState(() => isWakeWordEnabled());
  const [desktopHydrated, setDesktopHydrated] = useState(false);
  const [browserPerms, setBrowserPerms] = useState<BrowserPermissions>(() => getBrowserPermissions());
  const [browserCaps] = useState(() => detectBrowserCapabilities());
  const [browserBusyKey, setBrowserBusyKey] = useState<BrowserPermissionKey | null>(null);
  const [browserMessage, setBrowserMessage] = useState('');
  const dirtyRef = useRef(false);
  const saveTimerRef = useRef<number | null>(null);
  const navigate = useNavigate();
  const showBrowserPermissions = !isJarvisDesktop();

  const markDesktopDirty = () => {
    dirtyRef.current = true;
  };

  useEffect(() => {
    let cancelled = false;
    void api.integrations().then((result) => {
      if (!cancelled) setIntegrations(result.items);
    }).catch(() => undefined);
    void api.desktopInfo().then((info) => {
      if (cancelled) return;
      setDesktopInfo(info);
      // Never clobber toggles the user already flipped while this request was in flight.
      if (dirtyRef.current) {
        setDesktopHydrated(true);
        return;
      }
      if (info.is_desktop) {
        const prefs = info.preferences;
        setComputerControl(prefs?.computer_control ?? info.computer_control);
        setLiveWeb(prefs?.live_web ?? info.live_web ?? true);
        setBluetooth(prefs?.bluetooth ?? info.bluetooth ?? false);
        setFullDeviceAccess(prefs?.full_device_access ?? info.full_device_access ?? false);
        setAllowedPaths(prefs?.allowed_paths?.length ? prefs.allowed_paths : info.allowed_paths.length ? info.allowed_paths : DEFAULT_FOLDERS);
      } else {
        setLiveWeb(info.live_web ?? true);
      }
      setDesktopHydrated(true);
    }).catch(() => {
      if (!cancelled) setDesktopHydrated(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const tts = integrations.find((item) => item.id === 'text_to_speech');
  const wake = integrations.find((item) => item.id === 'wake_word');
  const llm = integrations.find((item) => item.id === 'llm');
  const weather = integrations.find((item) => item.id === 'weather');
  const stt = integrations.find((item) => item.id === 'speech_to_text');
  const research = integrations.find((item) => item.id === 'research');
  const computer = integrations.find((item) => item.id === 'computer_control');
  const showDesktopPermissions = isJarvisDesktop() || Boolean(desktopInfo?.is_desktop);

  const saveVoice = () => {
    setPreferredVoice(voiceId.trim() || DEFAULT_FISH_VOICE);
    setVoiceId(getPreferredVoice());
    setSavedVoice(true);
    window.setTimeout(() => setSavedVoice(false), 1800);
  };

  const saveDesktopPermissions = async (opts?: { silent?: boolean }) => {
    if (!showDesktopPermissions && !desktopInfo?.is_desktop && !isJarvisDesktop()) return;
    setDesktopBusy(true);
    if (!opts?.silent) {
      setDesktopError('');
      setDesktopMessage('');
    }
    try {
      const result = await api.updateDesktopSettings({
        computer_control: computerControl,
        live_web: liveWeb,
        bluetooth,
        full_device_access: fullDeviceAccess,
        allowed_paths: allowedPaths,
      });
      dirtyRef.current = false;
      setDesktopMessage(result.message || 'Permissions saved.');
      setComputerControl(result.computer_control);
      setLiveWeb(result.live_web ?? liveWeb);
      setBluetooth(result.bluetooth ?? bluetooth);
      setFullDeviceAccess(result.full_device_access ?? fullDeviceAccess);
      setAllowedPaths(result.allowed_paths);
      const info = await api.desktopInfo();
      setDesktopInfo(info);
    } catch (e) {
      setDesktopError(e instanceof Error ? e.message : 'Could not save desktop permissions.');
    } finally {
      setDesktopBusy(false);
    }
  };

  // Persist toggles automatically so On/Off doesn't snap back when leaving Settings.
  useEffect(() => {
    if (!desktopHydrated || !showDesktopPermissions || !dirtyRef.current) return;
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(() => {
      void saveDesktopPermissions({ silent: true });
    }, 350);
    return () => {
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- persist when permission fields change
  }, [computerControl, liveWeb, bluetooth, fullDeviceAccess, allowedPaths, desktopHydrated, showDesktopPermissions]);

  const addPath = () => {
    const next = pathDraft.trim();
    if (!next || allowedPaths.includes(next)) return;
    markDesktopDirty();
    setAllowedPaths((current) => [...current, next]);
    setPathDraft('');
  };

  const pickFolders = async () => {
    const picked = await pickDesktopFolders();
    if (!picked.length) return;
    markDesktopDirty();
    setAllowedPaths((current) => {
      const merged = [...current];
      for (const path of picked) {
        if (!merged.includes(path)) merged.push(path);
      }
      return merged;
    });
  };

  return <div className="page-stack settings-page">
    <div className="section-heading"><div><span className="eyebrow">PREFERENCES</span><h2>Settings</h2><p>Control how JARVIS responds and when it can use your devices.</p></div></div>

    <DesktopDownloadCard info={desktopInfo} />

    {showDesktopPermissions && (
      <section className="panel settings-section">
        <div className="section-title">
          <FolderOpen size={18} />
          <div>
            <h3>Desktop permissions</h3>
            <p>Authorize what JARVIS may do on this computer. Toggles save automatically. Destructive deletes still ask for confirmation.</p>
          </div>
          <span className={`readiness-chip ${computerControl ? 'ready' : 'unready'}`}><i />{computerControl ? 'Enabled' : 'Off'}</span>
        </div>
        <div className="setting-row">
          <div><strong>Computer control</strong><span>{computer?.detail || 'Open apps, URLs, authorized folders, and screenshots.'}</span></div>
          <button
            type="button"
            className="toggle-button"
            aria-pressed={computerControl}
            onClick={() => {
              markDesktopDirty();
              setComputerControl((value) => {
                const next = !value;
                if (!next) setFullDeviceAccess(false);
                return next;
              });
            }}
          >
            {computerControl ? 'On' : 'Off'}
          </button>
        </div>
        <div className="setting-row">
          <div>
            <strong>Full device access</strong>
            <span>
              {fullDeviceAccess
                ? 'JARVIS may use your entire user home folder, report storage, and open system settings (privacy, storage, display, etc.). Other users and protected system roots stay blocked.'
                : 'Off. Turn on for home-wide files, storage reports, and OS settings — required for “control my laptop” style requests.'}
            </span>
          </div>
          <button
            type="button"
            className="toggle-button"
            aria-pressed={fullDeviceAccess}
            disabled={!computerControl}
            onClick={() => {
              markDesktopDirty();
              setFullDeviceAccess((value) => {
                const next = !value;
                if (next) {
                  setComputerControl(true);
                  setAllowedPaths((current) => {
                    const extras = ['~', '~/Desktop', '~/Documents', '~/Downloads', '~/Pictures', '~/Music', '~/Movies'];
                    const merged = [...current];
                    for (const item of extras) {
                      if (!merged.includes(item)) merged.push(item);
                    }
                    return merged;
                  });
                }
                return next;
              });
            }}
          >
            {fullDeviceAccess ? 'On' : 'Off'}
          </button>
        </div>
        <div className="setting-row">
          <div>
            <strong>Live web & weather</strong>
            <span>
              {liveWeb
                ? 'JARVIS may search the web, read public pages, and fetch live weather (Open-Meteo) to answer you.'
                : 'Off. JARVIS will not call live web or weather tools until you allow it.'}
            </span>
          </div>
          <button
            type="button"
            className="toggle-button"
            aria-pressed={liveWeb}
            onClick={() => {
              markDesktopDirty();
              setLiveWeb((value) => !value);
            }}
          >
            {liveWeb ? 'On' : 'Off'}
          </button>
        </div>
        <div className="setting-row">
          <div>
            <strong>Bluetooth accessories</strong>
            <span>
              {bluetooth
                ? 'JARVIS may list, connect, and disconnect paired Bluetooth devices on this computer.'
                : 'Off. Turn on to let JARVIS manage paired headphones, speakers, keyboards, and similar devices.'}
              {' '}On macOS, connect/disconnect also needs <code>brew install blueutil</code>.
            </span>
          </div>
          <button
            type="button"
            className="toggle-button"
            aria-pressed={bluetooth}
            onClick={() => {
              markDesktopDirty();
              setBluetooth((value) => !value);
            }}
          >
            {bluetooth ? 'On' : 'Off'}
          </button>
        </div>
        <label className="field-label" htmlFor="allowed-path">
          {fullDeviceAccess ? 'Allowed folders (full home already included)' : 'Allowed folders'}
        </label>
        {fullDeviceAccess && (
          <p className="setting-help">Full device access already covers your user home. Extra folders below are optional.</p>
        )}
        <ul className="allowed-path-list">
          {allowedPaths.map((path) => (
            <li key={path}>
              <code>{path}</code>
              <button type="button" className="subtle-link" onClick={() => { markDesktopDirty(); setAllowedPaths((current) => current.filter((item) => item !== path)); }} aria-label={`Remove ${path}`}>Remove</button>
            </li>
          ))}
        </ul>
        <div className="settings-inline-row">
          <input id="allowed-path" className="settings-select" value={pathDraft} onChange={(event) => setPathDraft(event.target.value)} placeholder="~/Projects or absolute path" maxLength={500} />
          <button type="button" className="secondary-button" onClick={addPath} disabled={!pathDraft.trim()}>Add</button>
          {isJarvisDesktop() && <button type="button" className="secondary-button" onClick={() => void pickFolders()}><FolderOpen size={15} /> Browse</button>}
        </div>
        <div className="settings-actions">
          <button type="button" className="primary-button" disabled={desktopBusy} onClick={() => { markDesktopDirty(); void saveDesktopPermissions(); }}>
            {desktopBusy ? 'Saving…' : 'Save now'}
          </button>
          {isJarvisDesktop() && (
            <button type="button" className="secondary-button" onClick={() => void revealDesktopDataDir()}>Open data folder</button>
          )}
        </div>
        {desktopMessage && <p className="setting-help success-text">{desktopMessage}</p>}
        {desktopError && <p className="error-text">{desktopError}</p>}
        <div className="safety-note"><ShieldCheck size={15} /><span>Hosted web JARVIS never controls your laptop. Only this desktop app can. Full device access covers your user home — not other accounts or silent system-wide root control. Deletes still need confirmation.</span></div>
      </section>
    )}

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
        <div>
          <strong>Hey / Yo JARVIS wake words</strong>
          <span>
            {wakeWord
              ? 'Always listens in the background (even when the window is in the tray). Say “Hey JARVIS” or “Yo JARVIS” to come online. Say “sign off”, “go off”, or “go offline” to return to standby until you call him again.'
              : 'Off for privacy. Turn on to wake JARVIS with “Hey JARVIS” or “Yo JARVIS” from standby.'}
            {wake?.configured ? ' Server flag is also enabled.' : ''}
          </span>
        </div>
        <button
          type="button"
          className="toggle-button"
          aria-label={wakeWord ? 'Wake words on' : 'Wake words off'}
          aria-pressed={wakeWord}
          onClick={() => {
            const next = !wakeWord;
            setWakeWord(next);
            setWakeWordEnabled(next);
          }}
        >
          {wakeWord ? 'On' : 'Off'}
        </button>
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

    {!showDesktopPermissions && (
      <section className="panel settings-section">
        <div className="section-title">
          <Globe2 size={18} />
          <div>
            <h3>Live web & weather</h3>
            <p>Server-side live lookup. On Desktop, manage this under Desktop permissions.</p>
          </div>
          <span className={`readiness-chip ${research?.configured ? 'ready' : 'unready'}`}><i />{research?.configured ? 'Allowed' : 'Off / unavailable'}</span>
        </div>
        <p className="setting-help">
          {research?.detail || 'Checking…'} {weather?.detail ? `Weather: ${weather.detail}` : ''}
        </p>
      </section>
    )}

    {showBrowserPermissions && (
      <section className="panel settings-section">
        <div className="section-title">
          <Monitor size={18} />
          <div>
            <h3>Browser device access</h3>
            <p>Maximize what web JARVIS can do on this phone or laptop browser. OS app control still needs Desktop.</p>
          </div>
          <span className="readiness-chip ready"><i />Web</span>
        </div>
        {BROWSER_PERM_ROWS.map((row) => {
          const supported = Boolean((browserCaps as Record<string, boolean>)[row.key] ?? true);
          const on = browserPerms[row.key];
          return (
            <div className="setting-row" key={row.key}>
              <div>
                <strong>{row.title}</strong>
                <span>{supported ? row.help : 'Not supported in this browser.'}</span>
              </div>
              <button
                type="button"
                className="toggle-button"
                aria-pressed={on}
                disabled={!supported || browserBusyKey === row.key}
                onClick={() => {
                  const next = !on;
                  setBrowserPerms(setBrowserPermission(row.key, next));
                  setBrowserMessage('');
                  if (next) {
                    setBrowserBusyKey(row.key);
                    void requestBrowserPermission(row.key).then((result) => {
                      setBrowserMessage(result.detail);
                      setBrowserBusyKey(null);
                    });
                  }
                }}
              >
                {on ? 'On' : 'Off'}
              </button>
            </div>
          );
        })}
        {browserMessage && <p className="setting-help success-text">{browserMessage}</p>}
        <div className="safety-note"><ShieldCheck size={15} /><span>Browser permissions stay on this device. JARVIS asks the browser for each capability and never pretends to control your full OS from the website.</span></div>
      </section>
    )}

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

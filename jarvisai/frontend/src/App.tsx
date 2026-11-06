import { useEffect, useState, type FormEvent } from 'react';
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Activity, Apple, AudioLines, CalendarDays, ChevronRight, CircleHelp, Download, Home, LogOut, MessageSquareText, Mic, Monitor, Settings2, ShieldCheck, Wrench } from 'lucide-react';
import { api, ApiError, type Session, type User } from './lib/api';
import { isJarvisDesktop } from './lib/desktop';
import { isWakeWordEnabled, setWakeWordEnabled, startWakeWordMonitor, type WakeWordHandle } from './lib/voiceConversation';
import HomePage from './pages/HomePage';
import ChatPage from './pages/ChatPage';
import VoicePage from './pages/VoicePage';
import ToolsPage from './pages/ToolsPage';
import SettingsPage from './pages/SettingsPage';
import AboutPage from './pages/AboutPage';

const navigation = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/chat', label: 'Chat', icon: MessageSquareText },
  { to: '/voice', label: 'Voice', icon: AudioLines },
  { to: '/tools', label: 'Tools & Files', icon: Wrench },
  { to: '/settings', label: 'Settings', icon: Settings2 },
  { to: '/about', label: 'About', icon: CircleHelp },
];

function BrandMark() {
  return <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 40 48"><path d="M20 2 30 17l-2 11-8 7-8-7-2-11L20 2Z" /><path d="m7 23-5 7 14 16-1-12L7 23Zm26 0 5 7-14 16 1-12 8-11Z" /></svg></span>;
}

function SignIn({
  loading,
  available,
  provider,
  localAvailable,
  supabaseAvailable,
  downloads,
  onLocalLogin,
  onAuthenticated,
}: {
  loading: boolean;
  available: boolean;
  provider: string;
  localAvailable: boolean;
  supabaseAvailable: boolean;
  downloads?: { mac: string | null; windows: string | null; configured: boolean } | null;
  onLocalLogin: () => Promise<void>;
  onAuthenticated: (user: User, openAccess?: boolean) => void;
}) {
  const [mode, setMode] = useState<'signup' | 'login'>('signup');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const start = () => {
    setError('');
    try { api.login(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Sign-in could not be started.'); }
  };
  const startLocal = async () => {
    setError('');
    setBusy(true);
    try { await onLocalLogin(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Local sign-in failed.'); }
    finally { setBusy(false); }
  };
  const submitEmailAuth = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setNotice('');
    setBusy(true);
    try {
      if (mode === 'signup') {
        const result = await api.signup({ name: name.trim(), email: email.trim(), password });
        if (result.needs_confirmation) {
          setNotice(result.message || 'Confirm your email, then sign in.');
          setMode('login');
          return;
        }
        if (result.user) onAuthenticated(result.user, Boolean(result.open_access));
        return;
      }
      const result = await api.loginPassword({ email: email.trim(), password });
      onAuthenticated(result.user, Boolean(result.open_access));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Authentication failed.');
    } finally {
      setBusy(false);
    }
  };
  const oauthReady = available && provider.toLowerCase().includes('manus');
  const showDownloads = !isJarvisDesktop() && Boolean(downloads);
  return <main className="signin-screen">
    <div className="signin-card panel">
      <BrandMark />
      <div className="eyebrow">PERSONAL INTELLIGENCE SYSTEM</div>
      <h1>JARVIS</h1>
      <p>Create an account or sign in to use your private assistant. Download the desktop app anytime.</p>

      {supabaseAvailable && (
        <>
          <div className="signin-mode-tabs" role="tablist" aria-label="Account mode">
            <button type="button" className={mode === 'signup' ? 'active' : ''} onClick={() => { setMode('signup'); setError(''); setNotice(''); }} role="tab" aria-selected={mode === 'signup'}>Sign up</button>
            <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => { setMode('login'); setError(''); setNotice(''); }} role="tab" aria-selected={mode === 'login'}>Sign in</button>
          </div>
          <form className="signin-form" onSubmit={(event) => void submitEmailAuth(event)}>
            {mode === 'signup' && (
              <label className="signin-field">
                <span>Name</span>
                <input value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" required minLength={2} maxLength={120} placeholder="Your name" />
              </label>
            )}
            <label className="signin-field">
              <span>Email</span>
              <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required maxLength={254} placeholder="you@example.com" />
            </label>
            <label className="signin-field">
              <span>Password</span>
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} required minLength={8} maxLength={128} placeholder="At least 8 characters" />
            </label>
            <button className="primary-button signin-button" type="submit" disabled={loading || busy}>
              <ShieldCheck size={17} />
              {busy ? (mode === 'signup' ? 'Creating account…' : 'Signing in…') : (mode === 'signup' ? 'Create account' : 'Sign in')}
            </button>
          </form>
        </>
      )}

      {oauthReady && <button className="primary-button signin-button" onClick={start} disabled={loading || busy}><ShieldCheck size={17} />Continue with Manus</button>}
      {localAvailable && !supabaseAvailable && <button className="primary-button signin-button" onClick={() => void startLocal()} disabled={loading || busy}><ShieldCheck size={17} />{busy ? 'Starting local session…' : 'Continue locally'}</button>}
      {!available && !localAvailable && !supabaseAvailable && <p className="error-text">Sign-in is not configured. Add Supabase Auth keys or enable local auth.</p>}
      {notice && <p className="setting-help success-text">{notice}</p>}
      {error && <p className="error-text">{error}</p>}

      {showDownloads && (
        <div className="signin-download">
          <div className="signin-download-title"><Download size={14} /> Get JARVIS Desktop</div>
          <div className="desktop-download-row signin-download-row">
            {downloads?.mac ? (
              <a className="secondary-button desktop-download-link" href={downloads.mac}><Apple size={15} /> macOS</a>
            ) : (
              <button type="button" className="secondary-button" disabled title="Publish JARVIS-mac.dmg and set JARVIS_DESKTOP_DOWNLOAD_BASE"><Apple size={15} /> macOS</button>
            )}
            {downloads?.windows ? (
              <a className="secondary-button desktop-download-link" href={downloads.windows}><Monitor size={15} /> Windows</a>
            ) : (
              <button type="button" className="secondary-button" disabled title="Publish JARVIS-win.exe and set JARVIS_DESKTOP_DOWNLOAD_BASE"><Monitor size={15} /> Windows</button>
            )}
          </div>
          {!downloads?.configured && <p className="setting-help">Download links appear after you host installers and set <code>JARVIS_DESKTOP_DOWNLOAD_BASE</code>.</p>}
        </div>
      )}

      <div className="signin-note"><span className="status-dot" /> Passwords are handled by Supabase. JARVIS only keeps a signed session cookie.</div>
    </div>
  </main>;
}

function AppLayout({ user, onSignOut, openAccess }: { user: User; onSignOut: () => void; openAccess: boolean }) {
  const location = useLocation();
  const navigate = useNavigate();
  const pageTitle = navigation.find((item) => item.to === location.pathname)?.label ?? 'Home';
  const [clock, setClock] = useState(new Date());
  const [wakeArmed, setWakeArmed] = useState(() => isWakeWordEnabled());
  const [wakeStatus, setWakeStatus] = useState('idle');
  const [sttReady, setSttReady] = useState(false);
  useEffect(() => { const timer = window.setInterval(() => setClock(new Date()), 1000); return () => window.clearInterval(timer); }, []);

  useEffect(() => {
    // Desktop: arm Hey/Yo JARVIS once (also re-enables if it was left off during earlier fixes).
    try {
      if (window.jarvisDesktop?.isDesktop && localStorage.getItem('jarvis.wake_word_v3') !== '1') {
        setWakeWordEnabled(true);
        setWakeArmed(true);
        localStorage.setItem('jarvis.wake_word_v3', '1');
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void api.integrations().then((result) => {
      setSttReady(Boolean(result.items.find((item) => item.id === 'speech_to_text')?.configured));
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    const onPref = (event: Event) => {
      const detail = (event as CustomEvent<{ enabled?: boolean }>).detail;
      setWakeArmed(Boolean(detail?.enabled));
    };
    const onStatus = (event: Event) => {
      const detail = (event as CustomEvent<{ state?: string }>).detail;
      if (detail?.state) setWakeStatus(detail.state);
    };
    window.addEventListener('jarvis:wake-word-pref', onPref);
    window.addEventListener('jarvis:wake-status', onStatus);
    return () => {
      window.removeEventListener('jarvis:wake-word-pref', onPref);
      window.removeEventListener('jarvis:wake-status', onStatus);
    };
  }, []);

  useEffect(() => {
    if (!wakeArmed) return;
    let handle: WakeWordHandle | null = null;
    let cancelled = false;
    const arm = () => {
      if (cancelled) return;
      // Never hold the mic while a voice call is already using it.
      if ((window as Window & { __jarvisVoiceBusy?: boolean }).__jarvisVoiceBusy) return;
      handle?.stop();
      setWakeStatus('arming');
      handle = startWakeWordMonitor({
        sttReady,
        transcribe: async (file) => (await api.transcribe(file)).text,
        onWake: (_heard, command) => {
          if (command) window.sessionStorage.setItem('jarvis.wakeCommand', command);
          else window.sessionStorage.removeItem('jarvis.wakeCommand');
          window.sessionStorage.setItem('jarvis.startVoice', '1');
          if (location.pathname !== '/') navigate('/');
          window.dispatchEvent(new CustomEvent('jarvis:wake', { detail: { command } }));
        },
      });
    };
    const disarm = () => {
      handle?.stop();
      handle = null;
      setWakeStatus('paused');
    };
    const onBusy = () => disarm();
    const onIdle = () => {
      // Clear sticky busy flag that can block re-arm after a failed call.
      (window as Window & { __jarvisVoiceBusy?: boolean }).__jarvisVoiceBusy = false;
      arm();
    };
    window.addEventListener('jarvis:voice-busy', onBusy);
    window.addEventListener('jarvis:voice-idle', onIdle);
    // Clear any leftover busy state from a previous session in this window.
    (window as Window & { __jarvisVoiceBusy?: boolean }).__jarvisVoiceBusy = false;
    void navigator.mediaDevices?.getUserMedia?.({ audio: true })
      .then((stream) => {
        stream.getTracks().forEach((track) => track.stop());
        arm();
      })
      .catch(() => {
        setWakeStatus('mic-blocked');
        arm();
      });
    return () => {
      cancelled = true;
      disarm();
      window.removeEventListener('jarvis:voice-busy', onBusy);
      window.removeEventListener('jarvis:voice-idle', onIdle);
    };
  }, [wakeArmed, sttReady, navigate, location.pathname]);

  return <div className="app-frame machine-shell">
    <div className="frame-outline" aria-hidden="true" />
    <div className="shell-grid" aria-hidden="true" />
    <aside className="sidebar">
      <div className="sidebar-energy" aria-hidden="true" />
      <Link to="/" className="brand-lockup" aria-label="JARVIS home">
        <BrandMark /><span className="brand-name">JARVIS</span><span className="brand-caption">AI ASSISTANT</span>
      </Link>
      <div className="side-divider"><span>COMMAND</span></div>
      <nav className="primary-nav" aria-label="Primary navigation">
        {navigation.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
          <Icon size={20} strokeWidth={1.8} /><span>{label}</span>{to === location.pathname && <span className="nav-indicator" />}
        </NavLink>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="online-card"><div className="online-row"><span className="status-dot" /><span>Session Active</span></div><small>{user.name || 'Operator'}</small></div>
        {wakeArmed && (
          <div
            className="wake-armed-chip"
            title={
              wakeStatus === 'mic-blocked'
                ? 'Microphone permission needed'
                : wakeStatus === 'capturing' || wakeStatus === 'heard' || wakeStatus === 'wake'
                  ? 'Heard you — starting'
                  : 'Say Hey JARVIS or Yo JARVIS'
            }
          >
            <Mic size={13} />
            <span>
              {wakeStatus === 'mic-blocked'
                ? 'Mic blocked — enable in Settings'
                : wakeStatus === 'capturing'
                  ? 'Hearing you…'
                  : wakeStatus === 'wake' || wakeStatus === 'heard'
                    ? 'Waking JARVIS…'
                    : wakeStatus === 'error' || wakeStatus === 'unavailable'
                      ? 'Wake unavailable — check mic'
                      : 'Listening for “Hey / Yo JARVIS”'}
            </span>
          </div>
        )}
        {!openAccess && <button className="logout-button" onClick={onSignOut}><LogOut size={15} /> Sign out</button>}
      </div>
    </aside>
    <main className="main-panel">
      <header className="topbar">
        <div className="page-intro"><span className="accent-stem" /><div><h1>Hello, {user.name?.split(' ')[0] || 'Operator'}.</h1><p>{location.pathname === '/' ? 'How can I help you today?' : pageTitle}</p></div></div>
        <div className="topbar-right">
          <div className="datetime-card machine-chip"><span className="chip-pulse" aria-hidden="true" /><CalendarDays size={20} /><div><span>{clock.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}</span><strong>{clock.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</strong></div></div>
        </div>
      </header>
      <div className="route-content"><Routes>
        <Route path="/" element={<HomePage user={user} />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/voice" element={<VoicePage />} />
        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/settings" element={<SettingsPage user={user} />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes></div>
      <footer className="app-footer"><span><Activity size={13} /> JARVIS PERSONAL ASSISTANT</span><span>API &nbsp;·&nbsp; <a href="/docs" target="_blank" rel="noreferrer">OpenAPI docs <ChevronRight size={12} /></a></span></footer>
    </main>
  </div>;
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState('');
  const [loginAvailable, setLoginAvailable] = useState(false);
  const [localAvailable, setLocalAvailable] = useState(false);
  const [supabaseAvailable, setSupabaseAvailable] = useState(false);
  const [downloads, setDownloads] = useState<{ mac: string | null; windows: string | null; configured: boolean } | null>(null);
  const [openAccess, setOpenAccess] = useState(true);
  const [authProvider, setAuthProvider] = useState('none');
  const navigate = useNavigate();
  const refreshSession = async () => {
    setLoading(true);
    try {
      const next = await api.session();
      setSession(next);
      setOpenAccess(Boolean(next.open_access));
      setAuthError('');
    } catch (error) {
      setAuthError(error instanceof ApiError ? error.message : 'The session service is unavailable.');
      // Only fall back to an open session when the host still reports open access.
      setSession({ authenticated: false });
      setOpenAccess(false);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void refreshSession(); }, []);
  useEffect(() => {
    void api.authConfig().then((config) => {
      setLoginAvailable(config.available);
      setLocalAvailable(Boolean(config.local_available || config.provider.toLowerCase().includes('local')));
      setSupabaseAvailable(Boolean(config.supabase_available || config.provider.toLowerCase().includes('supabase')));
      setOpenAccess(Boolean(config.open_access ?? false));
      setAuthProvider(config.provider);
      if (config.downloads) setDownloads(config.downloads);
    }).catch(() => {
      setLoginAvailable(false);
      setLocalAvailable(false);
      setSupabaseAvailable(false);
      setOpenAccess(false);
    });
  }, []);
  const signOut = async () => { try { await api.logout(); } catch { /* local session gate still clears */ } setSession({ authenticated: false }); navigate('/'); };
  const localLogin = async () => {
    const result = await api.localLogin();
    setSession({ authenticated: true, open_access: Boolean(result.open_access), user: result.user });
  };
  const onAuthenticated = (user: User, nextOpenAccess?: boolean) => {
    setSession({ authenticated: true, open_access: Boolean(nextOpenAccess), user });
    setOpenAccess(Boolean(nextOpenAccess));
  };
  if (loading) return <main className="loading-screen"><div className="loading-orbit" /><p>Starting JARVIS…</p></main>;
  if ((!session?.authenticated || !session.user) && !openAccess) {
    return <>
      <SignIn
        loading={loading}
        available={loginAvailable}
        provider={authProvider}
        localAvailable={localAvailable}
        supabaseAvailable={supabaseAvailable}
        downloads={downloads}
        onLocalLogin={localLogin}
        onAuthenticated={onAuthenticated}
      />
      {authError && <div className="auth-notice" role="status">{authError}</div>}
    </>;
  }
  const user = session?.user ?? { id: 'local-operator', name: 'Operator', email: null };
  // Do not key AppLayout on location.key — that remounts the whole shell on every
  // route change and immediately kills active voice calls (looks like “quitting to home”).
  return <AppLayout user={user} onSignOut={signOut} openAccess={openAccess || Boolean(session?.open_access)} />;
}

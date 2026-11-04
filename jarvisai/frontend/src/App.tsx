import { useEffect, useState } from 'react';
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Activity, AudioLines, CalendarDays, ChevronRight, CircleHelp, Home, LogOut, MessageSquareText, Settings2, ShieldCheck, Wrench } from 'lucide-react';
import { api, ApiError, type Session, type User } from './lib/api';
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

function SignIn({ loading, available, provider, localAvailable, onLocalLogin }: { loading: boolean; available: boolean; provider: string; localAvailable: boolean; onLocalLogin: () => Promise<void> }) {
  const [error, setError] = useState('');
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
  const oauthReady = available && provider.toLowerCase().includes('manus');
  return <main className="signin-screen">
    <div className="signin-card panel">
      <BrandMark />
      <div className="eyebrow">PERSONAL INTELLIGENCE SYSTEM</div>
      <h1>JARVIS</h1>
      <p>Your command console is ready. Sign in to access your private assistant workspace.</p>
      {oauthReady && <button className="primary-button signin-button" onClick={start} disabled={loading || busy}><ShieldCheck size={17} />Continue with Manus</button>}
      {localAvailable && <button className="primary-button signin-button" onClick={() => void startLocal()} disabled={loading || busy}><ShieldCheck size={17} />{busy ? 'Starting local session…' : 'Continue locally'}</button>}
      {!available && !localAvailable && <p className="error-text">Sign-in is not configured. Enable local auth or Manus OAuth in the backend environment.</p>}
      {error && <p className="error-text">{error}</p>}
      <div className="signin-note"><span className="status-dot" /> Your session is verified server-side. No credentials are stored in the browser.</div>
    </div>
  </main>;
}

function AppLayout({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const location = useLocation();
  const pageTitle = navigation.find((item) => item.to === location.pathname)?.label ?? 'Home';
  const [clock, setClock] = useState(new Date());
  useEffect(() => { const timer = window.setInterval(() => setClock(new Date()), 1000); return () => window.clearInterval(timer); }, []);
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
        <div className="online-card"><div className="online-row"><span className="status-dot" /><span>Session Active</span></div><small>{user.name || 'Signed in'}</small></div>
        <button className="logout-button" onClick={onSignOut}><LogOut size={15} /> Sign out</button>
      </div>
    </aside>
    <main className="main-panel">
      <header className="topbar">
        <div className="page-intro"><span className="accent-stem" /><div><h1>Hello, {user.name?.split(' ')[0] || 'Operator'}.</h1><p>{location.pathname === '/' ? 'How can I help you today?' : pageTitle}</p></div></div>
        <div className="topbar-right">
          <div className="datetime-card machine-chip"><span className="chip-pulse" aria-hidden="true" /><CalendarDays size={20} /><div><span>{clock.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}</span><strong>{clock.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</strong></div></div>
          <div className="window-controls" aria-hidden="true"><i /><i /><i /></div>
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
  const [authProvider, setAuthProvider] = useState('none');
  const location = useLocation();
  const navigate = useNavigate();
  const refreshSession = async () => {
    setLoading(true);
    try { setSession(await api.session()); setAuthError(''); }
    catch (error) { setAuthError(error instanceof ApiError ? error.message : 'The session service is unavailable.'); setSession({ authenticated: false }); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refreshSession(); }, []);
  useEffect(() => {
    void api.authConfig().then((config) => {
      setLoginAvailable(config.available);
      setLocalAvailable(Boolean(config.local_available || config.provider.toLowerCase().includes('local')));
      setAuthProvider(config.provider);
    }).catch(() => { setLoginAvailable(false); setLocalAvailable(false); });
  }, []);
  const signOut = async () => { try { await api.logout(); } catch { /* local session gate still clears */ } setSession({ authenticated: false }); navigate('/'); };
  const localLogin = async () => {
    const result = await api.localLogin();
    setSession({ authenticated: true, user: result.user });
  };
  if (loading) return <main className="loading-screen"><div className="loading-orbit" /><p>Verifying your JARVIS session…</p></main>;
  if (!session?.authenticated || !session.user) return <><SignIn loading={loading} available={loginAvailable} provider={authProvider} localAvailable={localAvailable} onLocalLogin={localLogin} />{authError && <div className="auth-notice" role="status">{authError}</div>}</>;
  return <AppLayout user={session.user} onSignOut={signOut} key={location.key} />;
}

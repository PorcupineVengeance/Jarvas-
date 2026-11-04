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

function SignIn({ loading, available }: { loading: boolean; available: boolean }) {
  const [error, setError] = useState('');
  const start = () => {
    setError('');
    try { api.login(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Sign-in could not be started.'); }
  };
  return <main className="signin-screen">
    <div className="signin-card panel">
      <BrandMark />
      <div className="eyebrow">PERSONAL INTELLIGENCE SYSTEM</div>
      <h1>JARVIS</h1>
      <p>Your command console is ready. Sign in to access your private assistant workspace.</p>
      <button className="primary-button signin-button" onClick={start} disabled={loading || !available}><ShieldCheck size={17} />{available ? 'Continue with Manus' : 'Sign-in unavailable'}</button>
      {!available && <p className="error-text">Manus OAuth is not configured in this runtime. Configure the project's OAuth settings to enable sign-in.</p>}
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
  return <div className="app-frame">
    <div className="frame-outline" aria-hidden="true" />
    <aside className="sidebar">
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
          <div className="datetime-card"><CalendarDays size={20} /><div><span>{clock.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}</span><strong>{clock.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</strong></div></div>
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
  const location = useLocation();
  const navigate = useNavigate();
  const refreshSession = async () => {
    setLoading(true);
    try { setSession(await api.session()); setAuthError(''); }
    catch (error) { setAuthError(error instanceof ApiError ? error.message : 'The session service is unavailable.'); setSession({ authenticated: false }); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refreshSession(); }, []);
  useEffect(() => { void api.authConfig().then((config) => setLoginAvailable(config.available)).catch(() => setLoginAvailable(false)); }, []);
  const signOut = async () => { try { await api.logout(); } catch { /* local session gate still clears */ } setSession({ authenticated: false }); navigate('/'); };
  if (loading) return <main className="loading-screen"><div className="loading-orbit" /><p>Verifying your JARVIS session…</p></main>;
  if (!session?.authenticated || !session.user) return <><SignIn loading={loading} available={loginAvailable} />{authError && <div className="auth-notice" role="status">{authError}</div>}</>;
  return <AppLayout user={session.user} onSignOut={signOut} key={location.key} />;
}

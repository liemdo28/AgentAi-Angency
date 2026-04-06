import React, { useState, useEffect, useCallback, createContext, useContext } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Issues from './pages/Issues';
import IssueDetail from './pages/IssueDetail';
import Routines from './pages/Routines';
import Goals from './pages/Goals';
import Projects from './pages/Projects';
import Stores from './pages/Stores';
import OrgChart from './pages/OrgChart';
import Costs from './pages/Costs';
import Activity from './pages/Activity';
import Approvals from './pages/Approvals';
import Settings from './pages/Settings';
import { getStats } from './api';
import './styles.css';

// ── Theme Context ─────────────────────────────────────────────
const ThemeContext = createContext({
  theme: 'dark',
  setTheme: () => {},
  accent: '#6c5ce7',
  setAccent: () => {},
});

export const useTheme = () => useContext(ThemeContext);

function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => localStorage.getItem('agentai-theme') || 'dark');
  const [accent, setAccentState] = useState(() => localStorage.getItem('agentai-accent') || '#6c5ce7');

  const setTheme = useCallback((t) => {
    setThemeState(t);
    localStorage.setItem('agentai-theme', t);
    document.documentElement.setAttribute('data-theme', t);
  }, []);

  const setAccent = useCallback((a) => {
    setAccentState(a);
    localStorage.setItem('agentai-accent', a);
    document.documentElement.style.setProperty('--user-accent', a);
  }, []);

  // Sync on mount (in case React hydrates after the inline script)
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.style.setProperty('--user-accent', accent);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, accent, setAccent }}>
      {children}
    </ThemeContext.Provider>
  );
}

// ── Simple SVG icons ──────────────────────────────────────────
const Icon = ({ name }) => {
  const icons = {
    dashboard: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/><rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>,
    issues: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5"/><path d="M8 5v3l2 2"/></svg>,
    routines: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" fill="none"/><circle cx="5" cy="4" r="1.5"/><circle cx="10" cy="8" r="1.5"/><circle cx="7" cy="12" r="1.5"/></svg>,
    goals: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5"/><circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.5"/><circle cx="8" cy="8" r="1"/></svg>,
    org: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><rect x="5" y="1" width="6" height="4" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2"/><rect x="1" y="11" width="5" height="4" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2"/><rect x="10" y="11" width="5" height="4" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2"/><path d="M8 5v3M8 8H3.5v3M8 8h4.5v3" stroke="currentColor" strokeWidth="1.2" fill="none"/></svg>,
    costs: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1v14M5 4h5a2 2 0 010 4H6a2 2 0 000 4h5" stroke="currentColor" strokeWidth="1.5" fill="none"/></svg>,
    activity: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M1 8h3l2-5 3 10 2-5h4" stroke="currentColor" strokeWidth="1.5" fill="none"/></svg>,
    approvals: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M4 8l3 3 5-6" stroke="currentColor" strokeWidth="2" fill="none"/></svg>,
    projects: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><rect x="2" y="2" width="12" height="12" rx="2" fill="none" stroke="currentColor" strokeWidth="1.3"/><path d="M2 6h12" stroke="currentColor" strokeWidth="1.3"/><circle cx="4.5" cy="4" r="0.8"/><circle cx="7" cy="4" r="0.8"/></svg>,
    stores: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M2 6l1-4h10l1 4M2 6v8h12V6M4 14v-4h4v4M10 9h2v2h-2z" stroke="currentColor" strokeWidth="1.2" fill="none"/></svg>,
    settings: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.5"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.5 1.5M11.5 11.5L13 13M13 3l-1.5 1.5M4.5 11.5L3 13" stroke="currentColor" strokeWidth="1.2"/></svg>,
  };
  return icons[name] || null;
};

// ── Page title from pathname ──────────────────────────────────
const PAGE_TITLES = {
  '/': 'Overview',
  '/issues': 'Issues',
  '/routines': 'Routines',
  '/goals': 'Goals',
  '/projects': 'Projects',
  '/stores': 'Stores',
  '/org': 'Org Chart',
  '/costs': 'Costs',
  '/activity': 'Activity',
  '/approvals': 'Approvals',
  '/settings': 'Settings',
};

function ContentHeader() {
  const location = useLocation();
  const { theme, setTheme } = useTheme();

  const basePath = '/' + (location.pathname.split('/')[1] || '');
  const title = PAGE_TITLES[basePath] || 'AgentAI';

  const toggleTheme = () => setTheme(theme === 'dark' ? 'light' : 'dark');

  return (
    <div className="content-header">
      <span className="content-header-title">{title}</span>
      <div className="content-header-actions">
        <button onClick={toggleTheme} className="btn btn-ghost btn-sm">
          {theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19'}
        </button>
      </div>
    </div>
  );
}

function AppShell() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    getStats().then(setStats).catch(() => {});
    const t = setInterval(() => getStats().then(setStats).catch(() => {}), 5000);
    return () => clearInterval(t);
  }, []);

  const running = stats?.tasks?.running ?? 0;

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">AI</div>
          <span className="sidebar-logo-text">AgentAI</span>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-section-title">Work</div>
          <NavLink to="/issues"><Icon name="issues" /> Issues {running > 0 && <span className="badge-live">{running} live</span>}</NavLink>
          <NavLink to="/routines"><Icon name="routines" /> Routines</NavLink>
          <NavLink to="/goals"><Icon name="goals" /> Goals</NavLink>
        </div>

        <div className="sidebar-divider" />

        <div className="sidebar-section">
          <div className="sidebar-section-title">Company</div>
          <NavLink to="/" end><Icon name="dashboard" /> Overview</NavLink>
          <NavLink to="/projects"><Icon name="projects" /> Projects</NavLink>
          <NavLink to="/stores"><Icon name="stores" /> Stores</NavLink>
          <NavLink to="/org"><Icon name="org" /> Org Chart</NavLink>
          <NavLink to="/costs"><Icon name="costs" /> Costs</NavLink>
          <NavLink to="/activity"><Icon name="activity" /> Activity</NavLink>
          <NavLink to="/approvals">
            <Icon name="approvals" /> Approvals
            {stats?.tasks?.pending > 0 && <span className="sidebar-badge">{stats.tasks.pending}</span>}
          </NavLink>
        </div>

        <div className="sidebar-divider" />

        <div className="sidebar-section">
          <NavLink to="/settings"><Icon name="settings" /> Settings</NavLink>
        </div>
      </nav>

      <main className="content">
        <ContentHeader />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/issues" element={<Issues />} />
          <Route path="/issues/:id" element={<IssueDetail />} />
          <Route path="/routines" element={<Routines />} />
          <Route path="/goals" element={<Goals />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/stores" element={<Stores />} />
          <Route path="/org" element={<OrgChart />} />
          <Route path="/costs" element={<Costs />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/approvals" element={<Approvals />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AppShell />
      </ThemeProvider>
    </BrowserRouter>
  );
}

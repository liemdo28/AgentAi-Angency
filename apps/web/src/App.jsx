import React, { useState, useEffect, useCallback, createContext, useContext } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Issues from './pages/Issues';
import IssueDetail from './pages/IssueDetail';
import Routines from './pages/Routines';
import Goals from './pages/Goals';
import Projects from './pages/Projects';
import IntegrationOps from './pages/IntegrationOps';
import Stores from './pages/Stores';
import Departments from './pages/Departments';
import OrgChart from './pages/OrgChart';
import Costs from './pages/Costs';
import Activity from './pages/Activity';
import Approvals from './pages/Approvals';
import Settings from './pages/Settings';
import DevPanel from './pages/DevPanel';
import { getStats } from './api';
import './styles.css';

// ── Theme Context ─────────────────────────────────────────────
const ThemeContext = createContext({
  theme: 'dark',
  setTheme: () => {},
  accent: '#43b581',
  setAccent: () => {},
});

export const useTheme = () => useContext(ThemeContext);

function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => localStorage.getItem('agentai-theme') || 'dark');
  const [accent, setAccentState] = useState(() => localStorage.getItem('agentai-accent') || '#43b581');

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
    pulse: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M1 9h3l1.4-4 3.2 7 2-4H15" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round"/><circle cx="5.4" cy="5" r="0.8"/><circle cx="8.6" cy="12" r="0.8"/></svg>,
    stores: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M2 6l1-4h10l1 4M2 6v8h12V6M4 14v-4h4v4M10 9h2v2h-2z" stroke="currentColor" strokeWidth="1.2" fill="none"/></svg>,
    shield: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1l5 2v4c0 3.3-1.9 6-5 8-3.1-2-5-4.7-5-8V3l5-2z" stroke="currentColor" strokeWidth="1.2" fill="none"/><path d="M5.5 8l1.6 1.6L10.8 6" stroke="currentColor" strokeWidth="1.2" fill="none"/></svg>,
    settings: <svg className="sidebar-icon" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.5"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.5 1.5M11.5 11.5L13 13M13 3l-1.5 1.5M4.5 11.5L3 13" stroke="currentColor" strokeWidth="1.2"/></svg>,
  };
  return icons[name] || null;
};

// ── Page title from pathname ──────────────────────────────────
const PAGE_META = {
  '/': {
    title: 'Overview',
    section: 'Command Center',
    subtitle: 'Live operating surface for workload, workforce, and company health.',
  },
  '/issues': {
    title: 'Issues',
    section: 'Work Queue',
    subtitle: 'Create requests, inspect workflows, and drive agent execution from one place.',
  },
  '/routines': {
    title: 'Routines',
    section: 'Automation Cadence',
    subtitle: 'See when teams and connectors are scheduled to run across the day.',
  },
  '/goals': {
    title: 'Goals',
    section: 'Company Planning',
    subtitle: 'Track objectives, ownership, and execution progress across the agency.',
  },
  '/projects': {
    title: 'Projects',
    section: 'Project Control',
    subtitle: 'Monitor projects, launch QA loops, and route operational follow-up.',
  },
  '/integration-ops': {
    title: 'Integration Ops',
    section: 'Edge Operations',
    subtitle: 'Watch remote machines, download health, QuickBooks syncs, and dispatch actions.',
  },
  '/stores': {
    title: 'Stores',
    section: 'Location Network',
    subtitle: 'Review brand locations, live marketing data, and store-level sync status.',
  },
  '/departments': {
    title: 'Departments',
    section: 'Governance',
    subtitle: 'Manage departments, permissions, policy execution, and audit visibility.',
  },
  '/org': {
    title: 'Org Chart',
    section: 'Agent Workforce',
    subtitle: 'Understand the runtime organization, capabilities, and current load.',
  },
  '/costs': {
    title: 'Costs',
    section: 'Spend Control',
    subtitle: 'Compare budget, spend, and remaining runway across the active roster.',
  },
  '/activity': {
    title: 'Activity',
    section: 'Timeline',
    subtitle: 'Review system events, approvals, executions, and operational history.',
  },
  '/approvals': {
    title: 'Approvals',
    section: 'Decision Queue',
    subtitle: 'Review pending approvals and governed actions before they move forward.',
  },
  '/dev': {
    title: 'Dev Agent',
    section: 'Engineering Ops',
    subtitle: 'Run guided development actions against tracked projects from the control plane.',
  },
  '/settings': {
    title: 'Settings',
    section: 'System Configuration',
    subtitle: 'Tune appearance, orchestration defaults, and runtime environment details.',
  },
};

const WORLD_CLOCKS = [
  { key: 'vn', label: 'VN', timeZone: 'Asia/Ho_Chi_Minh' },
  { key: 'san_antonio', label: 'San Antonio', timeZone: 'America/Chicago' },
  { key: 'stockton', label: 'Stockton', timeZone: 'America/Los_Angeles' },
];

function WorldClocks() {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="world-clocks" aria-label="World clocks">
      {WORLD_CLOCKS.map((clock) => {
        const value = new Intl.DateTimeFormat('en-US', {
          timeZone: clock.timeZone,
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        }).format(now);

        return (
          <div key={clock.key} className="clock-chip">
            <span className="clock-label">{clock.label}</span>
            <span className="clock-value">{value}</span>
          </div>
        );
      })}
    </div>
  );
}

function ContentHeader() {
  const location = useLocation();
  const { theme, setTheme } = useTheme();

  const basePath = '/' + (location.pathname.split('/')[1] || '');
  const meta = PAGE_META[basePath] || {
    title: 'AgentAI',
    section: 'Control Plane',
    subtitle: 'Operational visibility across your AI agency.',
  };

  const toggleTheme = () => setTheme(theme === 'dark' ? 'light' : 'dark');

  return (
    <div className="content-header">
      <div className="content-header-copy">
        <div className="content-header-section">{meta.section}</div>
        <div className="content-header-title">{meta.title}</div>
        <div className="content-header-subtitle">{meta.subtitle}</div>
      </div>
      <div className="content-header-actions">
        <WorldClocks />
        <button onClick={toggleTheme} className="btn btn-ghost btn-sm">
          {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
        </button>
      </div>
    </div>
  );
}

function AppShell() {
  const [stats, setStats] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    getStats().then(setStats).catch(() => {});
    const t = setInterval(() => getStats().then(setStats).catch(() => {}), 5000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  const running = stats?.tasks?.running ?? 0;
  const pending = stats?.tasks?.pending ?? 0;
  const failed = stats?.tasks?.failed ?? 0;

  return (
    <div className="app-shell">
      <div
        className={`sidebar-backdrop ${sidebarOpen ? 'is-open' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />

      <nav className={`sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="sidebar-top">
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">AI</div>
            <div className="sidebar-logo-copy">
              <span className="sidebar-logo-text">AgentAI</span>
              <span className="sidebar-logo-sub">Control Plane</span>
            </div>
          </div>

          <button className="sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation">
            x
          </button>
        </div>

        <div className="sidebar-status">
          <div className="sidebar-status-title">Live System</div>
          <div className="sidebar-status-grid">
            <div className="sidebar-status-card">
              <span className="sidebar-status-label">Running</span>
              <strong>{running}</strong>
            </div>
            <div className="sidebar-status-card">
              <span className="sidebar-status-label">Pending</span>
              <strong>{pending}</strong>
            </div>
            <div className="sidebar-status-card">
              <span className="sidebar-status-label">Failed</span>
              <strong>{failed}</strong>
            </div>
          </div>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-section-title">Work</div>
          <NavLink to="/issues"><Icon name="issues" /> Issues {running > 0 && <span className="badge-live">{running} live</span>}</NavLink>
          <NavLink to="/routines"><Icon name="routines" /> Routines</NavLink>
          <NavLink to="/goals"><Icon name="goals" /> Goals</NavLink>
          <NavLink to="/dev"><Icon name="activity" /> Dev Agent</NavLink>
        </div>

        <div className="sidebar-divider" />

        <div className="sidebar-section">
          <div className="sidebar-section-title">Company</div>
          <NavLink to="/" end><Icon name="dashboard" /> Overview</NavLink>
          <NavLink to="/projects"><Icon name="projects" /> Projects</NavLink>
          <NavLink to="/integration-ops"><Icon name="pulse" /> Integration Ops</NavLink>
          <NavLink to="/stores"><Icon name="stores" /> Stores</NavLink>
          <NavLink to="/departments"><Icon name="shield" /> Departments</NavLink>
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

        <div className="sidebar-footer">
          <div className="sidebar-footer-label">Agency Pulse</div>
          <div className="sidebar-footer-value">
            {running > 0 ? `${running} workflows moving` : 'No live runs right now'}
          </div>
        </div>
      </nav>

      <main className="content">
        <div className="content-topbar">
          <button className="nav-toggle btn btn-ghost btn-sm" onClick={() => setSidebarOpen(true)}>
            Menu
          </button>
        </div>
        <ContentHeader />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/issues" element={<Issues />} />
          <Route path="/issues/:id" element={<IssueDetail />} />
          <Route path="/routines" element={<Routines />} />
          <Route path="/goals" element={<Goals />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/integration-ops" element={<IntegrationOps />} />
          <Route path="/stores" element={<Stores />} />
          <Route path="/departments" element={<Departments />} />
          <Route path="/org" element={<OrgChart />} />
          <Route path="/costs" element={<Costs />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/approvals" element={<Approvals />} />
          <Route path="/dev" element={<DevPanel />} />
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

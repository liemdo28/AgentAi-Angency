import React, { useState, useEffect } from 'react';
import { getStats, triggerCycle, listTasks, listRuntimeAgents } from '../api';

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [recentTasks, setRecentTasks] = useState([]);
  const [agents, setAgents] = useState([]);
  const [cycling, setCycling] = useState(false);

  const load = () => {
    getStats().then(setStats).catch(() => {});
    listTasks().then(t => setRecentTasks(t.slice(0, 8))).catch(() => {});
    listRuntimeAgents().then(setAgents).catch(() => {});
  };

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);

  const runCycle = async () => {
    setCycling(true);
    try { await triggerCycle(); await load(); } finally { setCycling(false); }
  };

  if (!stats) return <div className="page"><div className="empty-state">Loading...</div></div>;

  const total = Object.values(stats.tasks).reduce((a, b) => a + b, 0);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Overview</h1>
        <div className="page-header-actions">
          {stats.tasks.running > 0 && <span className="badge-live">{stats.tasks.running} live</span>}
          <button className="btn btn-primary" onClick={runCycle} disabled={cycling}>
            {cycling ? 'Running...' : 'Run Cycle'}
          </button>
        </div>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-label">Total Issues</div>
          <div className="stat-value accent">{total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Pending</div>
          <div className="stat-value yellow">{stats.tasks.pending}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Running</div>
          <div className="stat-value blue">{stats.tasks.running}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Completed</div>
          <div className="stat-value green">{stats.tasks.success}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Failed</div>
          <div className="stat-value red">{stats.tasks.failed}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Agents</div>
          <div className="stat-value">{agents.length}</div>
          <div className="stat-sub">{agents.length} active</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Spend</div>
          <div className="stat-value">${stats.total_cost_usd}</div>
          <div className="stat-sub">this period</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Goals</div>
          <div className="stat-value accent">{stats.goals}</div>
        </div>
      </div>

      <div className="section-title">Recent Issues</div>
      <div className="issue-list">
        {recentTasks.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">~</div>
            No issues yet. Create one from the Issues page.
          </div>
        )}
        {recentTasks.map((t, i) => (
          <div className="issue-row" key={t.id}>
            <div className={`issue-status-dot ${t.status}`} />
            <span className="issue-id">#{String(i + 1).padStart(4, '0')}</span>
            <span className="issue-title">{t.title}</span>
            <div className="issue-meta">
              <span className="issue-agent">{t.assigned_agent_id}</span>
              <span className="issue-date">{t.created_at?.slice(0, 10)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

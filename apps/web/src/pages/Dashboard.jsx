import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getStats,
  triggerCycle,
  listTasks,
  listRuntimeAgents,
  getMarketingStores,
  triggerMarketingSync,
  getMarketingSummary,
} from '../api';

function formatMoney(value) {
  return `$${Number(value || 0).toLocaleString()}`;
}

function formatStamp(value) {
  if (!value) return 'No sync data yet';
  return value.slice(0, 10);
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [recentTasks, setRecentTasks] = useState([]);
  const [agents, setAgents] = useState([]);
  const [cycling, setCycling] = useState(false);
  const [stores, setStores] = useState([]);
  const [storesSyncing, setStoresSyncing] = useState(false);
  const [marketingSummary, setMarketingSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const load = () => {
    getStats().then(setStats).catch(() => {});
    listTasks().then((items) => setRecentTasks(items.slice(0, 8))).catch(() => {});
    listRuntimeAgents().then(setAgents).catch(() => {});
    getMarketingStores().then(r => setStores(r?.stores || r || [])).catch(() => setStores([]));
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const runCycle = async () => {
    setCycling(true);
    try {
      await triggerCycle();
      await load();
    } finally {
      setCycling(false);
    }
  };

  const syncAllStores = async () => {
    setStoresSyncing(true);
    try {
      await triggerMarketingSync();
      await load();
    } finally {
      setStoresSyncing(false);
    }
  };

  const fetchMarketingSummary = async () => {
    setSummaryLoading(true);
    try {
      const data = await getMarketingSummary();
      setMarketingSummary(data);
    } catch {
      setMarketingSummary({ error: 'Failed to load summary' });
    } finally {
      setSummaryLoading(false);
    }
  };

  if (!stats) {
    return <div className="page"><div className="empty-state">Loading command center...</div></div>;
  }

  const total = Object.values(stats.tasks).reduce((sum, value) => sum + value, 0);
  const taskMax = Math.max(stats.tasks.pending, stats.tasks.running, stats.tasks.success, stats.tasks.failed, 1);
  const busyAgentIds = new Set(
    recentTasks.filter((task) => task.assigned_agent_id && task.status === 'running').map((task) => task.assigned_agent_id)
  );

  const agentsByLevel = agents.reduce((acc, agent) => {
    const level = agent.level || 'unknown';
    if (!acc[level]) acc[level] = [];
    acc[level].push(agent);
    return acc;
  }, {});

  const levelOrder = ['c-suite', 'director', 'head', 'specialist'];
  const levelLabels = {
    'c-suite': 'C-Suite',
    director: 'Directors',
    head: 'Heads',
    specialist: 'Specialists',
    unknown: 'Other',
  };
  const levelColors = {
    'c-suite': 'var(--red)',
    director: 'var(--orange)',
    head: 'var(--blue)',
    specialist: 'var(--green)',
    unknown: 'var(--text-muted)',
  };

  const barStyle = (value, color) => ({
    height: `${Math.max((value / taskMax) * 160, 8)}px`,
    width: '100%',
    background: color,
    borderRadius: '12px 12px 0 0',
    transition: 'height 0.25s ease',
  });

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Command Center</h1>
          <div className="page-subtitle">
            A single operating surface for workload health, active agents, sync coverage, and the next actions that matter.
          </div>
        </div>
        <div className="page-header-actions">
          {stats.tasks.running > 0 && <span className="badge-live">{stats.tasks.running} live</span>}
          <button className="btn btn-ghost" onClick={fetchMarketingSummary} disabled={summaryLoading}>
            {summaryLoading ? 'Loading summary...' : 'Marketing Summary'}
          </button>
          <button className="btn btn-primary" onClick={runCycle} disabled={cycling}>
            {cycling ? 'Running...' : 'Run Cycle'}
          </button>
        </div>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-label">Total Workload</div>
          <div className="stat-value accent">{total}</div>
          <div className="stat-sub">tasks across all queues</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Pending</div>
          <div className="stat-value yellow">{stats.tasks.pending}</div>
          <div className="stat-sub">waiting for execution</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Running</div>
          <div className="stat-value blue">{stats.tasks.running}</div>
          <div className="stat-sub">currently in motion</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Completed</div>
          <div className="stat-value green">{stats.tasks.success}</div>
          <div className="stat-sub">resolved successfully</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Failed</div>
          <div className="stat-value red">{stats.tasks.failed}</div>
          <div className="stat-sub">needs recovery loop</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Live Agents</div>
          <div className="stat-value">{agents.length}</div>
          <div className="stat-sub">{busyAgentIds.size} busy right now</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Spend</div>
          <div className="stat-value">{formatMoney(stats.total_cost_usd)}</div>
          <div className="stat-sub">current reporting period</div>
        </div>
      </div>

      <div className="two-col-layout">
        <div className="stack">
          <section className="surface-panel">
            <div className="surface-header">
              <div>
                <div className="surface-title">Task Pipeline</div>
                <div className="surface-subtitle">Distribution of work by lifecycle state.</div>
              </div>
            </div>

            <div className="dashboard-bars">
              {[
                { label: 'Pending', value: stats.tasks.pending, color: 'var(--yellow)' },
                { label: 'Running', value: stats.tasks.running, color: 'var(--blue)' },
                { label: 'Success', value: stats.tasks.success, color: 'var(--green)' },
                { label: 'Failed', value: stats.tasks.failed, color: 'var(--red)' },
              ].map((bar) => (
                <div key={bar.label} className="dashboard-bar-card">
                  <div className="dashboard-bar-value" style={{ color: bar.color }}>{bar.value}</div>
                  <div className="dashboard-bar-rail">
                    <div style={barStyle(bar.value, bar.color)} />
                  </div>
                  <div className="dashboard-bar-label">{bar.label}</div>
                </div>
              ))}
            </div>

            <div className="dashboard-distribution">
              {total > 0 && (
                <>
                  <div style={{ width: `${(stats.tasks.pending / total) * 100}%`, background: 'var(--yellow)' }} />
                  <div style={{ width: `${(stats.tasks.running / total) * 100}%`, background: 'var(--blue)' }} />
                  <div style={{ width: `${(stats.tasks.success / total) * 100}%`, background: 'var(--green)' }} />
                  <div style={{ width: `${(stats.tasks.failed / total) * 100}%`, background: 'var(--red)' }} />
                </>
              )}
            </div>
          </section>

          <section className="surface-panel">
            <div className="surface-header">
              <div>
                <div className="surface-title">Recent Issues</div>
                <div className="surface-subtitle">Newest requests and workflow items entering the system.</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => navigate('/issues')}>
                Open Queue
              </button>
            </div>

            <div className="issue-list">
              {recentTasks.length === 0 && (
                <div className="empty-state">
                  <div className="empty-state-icon">~</div>
                  No issues yet. Create one from the Issues page.
                </div>
              )}
              {recentTasks.map((task, index) => (
                <div
                  className="issue-row"
                  key={task.id}
                  onClick={() => navigate(`/issues/${task.id}`)}
                >
                  <div className={`issue-status-dot ${task.status}`} />
                  <span className="issue-id">#{String(index + 1).padStart(4, '0')}</span>
                  <span className="issue-title">{task.title}</span>
                  <div className="issue-meta">
                    <span className="issue-agent">{task.assigned_agent_id}</span>
                    <span className="issue-date">{task.created_at?.slice(0, 10)}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="stack">
          <section className="surface-panel">
            <div className="surface-header">
              <div>
                <div className="surface-title">Agent Workforce</div>
                <div className="surface-subtitle">Runtime coverage by organizational level.</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => navigate('/org')}>
                View Org
              </button>
            </div>

            <div className="workforce-list">
              {levelOrder.filter((level) => agentsByLevel[level]).map((level) => (
                <div key={level} className="workforce-row">
                  <div className="workforce-name">
                    <span className="workforce-dot" style={{ background: levelColors[level] }} />
                    <span>{levelLabels[level]}</span>
                  </div>
                  <div className="workforce-meter">
                    <div
                      className="workforce-meter-fill"
                      style={{
                        width: `${Math.min((agentsByLevel[level].length / Math.max(agents.length, 1)) * 100, 100)}%`,
                        background: colorMix(levelColors[level]),
                      }}
                    />
                    <span className="workforce-meter-value">{agentsByLevel[level].length}</span>
                  </div>
                  <div className="workforce-busy">
                    {agentsByLevel[level].filter((agent) => busyAgentIds.has(agent.agent_id || agent.id)).length} busy
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="surface-panel">
            <div className="surface-header">
              <div>
                <div className="surface-title">Quick Actions</div>
                <div className="surface-subtitle">Jump to the most common operator workflows.</div>
              </div>
            </div>

            <div className="quick-action-list">
              <button className="quick-action-button" onClick={() => navigate('/issues')}>
                <strong>New Request</strong>
                <span>Open the queue and create a new issue or workflow.</span>
              </button>
              <button className="quick-action-button" onClick={runCycle} disabled={cycling}>
                <strong>{cycling ? 'Running cycle...' : 'Run Cycle'}</strong>
                <span>Kick the orchestrator to advance pending work immediately.</span>
              </button>
              <button className="quick-action-button" onClick={() => navigate('/projects')}>
                <strong>Review Projects</strong>
                <span>Check project status, QA loops, and machine-linked follow-up.</span>
              </button>
            </div>

            {marketingSummary && (
              <div className="dashboard-summary-box">
                {marketingSummary.error ? (
                  <span style={{ color: 'var(--red)' }}>{marketingSummary.error}</span>
                ) : (
                  <pre>{typeof marketingSummary === 'string' ? marketingSummary : JSON.stringify(marketingSummary, null, 2)}</pre>
                )}
              </div>
            )}
          </section>

          <section className="surface-panel">
            <div className="surface-header">
              <div>
                <div className="surface-title">Store Status</div>
                <div className="surface-subtitle">Latest sync activity for connected marketing stores.</div>
              </div>
              <button className="btn btn-primary btn-sm" onClick={syncAllStores} disabled={storesSyncing}>
                {storesSyncing ? 'Syncing...' : 'Sync All'}
              </button>
            </div>

            <div className="project-feed">
              {stores.length === 0 && (
                <div className="project-feed-empty">No marketing stores connected yet.</div>
              )}
              {stores.map((store) => {
                const revenue = store.data?.revenue ?? store.revenue;
                return (
                  <div key={store.id || store.label} className="project-feed-row">
                    <div>
                      <div className="project-feed-title">{store.label || store.name || store.id}</div>
                      <div className="project-feed-sub">{formatStamp(store.last_updated)}</div>
                    </div>
                    <div className="dashboard-store-value">
                      {revenue != null ? formatMoney(revenue) : '--'}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function colorMix(color) {
  return `color-mix(in srgb, ${color} 26%, transparent)`;
}

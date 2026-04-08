import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStats, triggerCycle, listTasks, listRuntimeAgents, getMarketingStores, triggerMarketingSync, getMarketingSummary, getLlmStats } from '../api';

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
    listTasks().then(t => setRecentTasks(t.slice(0, 8))).catch(() => {});
    listRuntimeAgents().then(setAgents).catch(() => {});
    getMarketingStores().then(setStores).catch(() => setStores([]));
  };

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);

  const runCycle = async () => {
    setCycling(true);
    try { await triggerCycle(); await load(); } finally { setCycling(false); }
  };

  const syncAllStores = async () => {
    setStoresSyncing(true);
    try { await triggerMarketingSync(); await load(); } finally { setStoresSyncing(false); }
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

  if (!stats) return <div className="page"><div className="empty-state">Loading...</div></div>;

  const total = Object.values(stats.tasks).reduce((a, b) => a + b, 0);
  const taskMax = Math.max(stats.tasks.pending, stats.tasks.running, stats.tasks.success, stats.tasks.failed, 1);

  // Group agents by level
  const agentsByLevel = agents.reduce((acc, a) => {
    const level = a.level || 'unknown';
    if (!acc[level]) acc[level] = [];
    acc[level].push(a);
    return acc;
  }, {});

  const levelOrder = ['c-suite', 'director', 'head', 'specialist'];
  const levelColors = { 'c-suite': '#e74c3c', director: '#e67e22', head: '#3498db', specialist: '#2ecc71', unknown: '#95a5a6' };

  // Find agents with tasks assigned
  const busyAgentIds = new Set(recentTasks.filter(t => t.assigned_agent_id && t.status === 'running').map(t => t.assigned_agent_id));

  const barStyle = (value, color) => ({
    height: `${Math.max((value / taskMax) * 120, 4)}px`,
    width: '100%',
    background: color,
    borderRadius: '3px 3px 0 0',
    transition: 'height 0.3s ease',
    minHeight: '4px',
  });

  const miniBarStyle = (value, color) => ({
    flex: 1,
    height: `${Math.max((value / taskMax) * 20, 2)}px`,
    background: color,
    borderRadius: '2px',
    transition: 'height 0.3s ease',
  });

  return (
    <div className="page">
      <div className="page-header">
        <h1>Command Center</h1>
        <div className="page-header-actions">
          {stats.tasks.running > 0 && <span className="badge-live">{stats.tasks.running} live</span>}
          <button className="btn btn-primary" onClick={runCycle} disabled={cycling}>
            {cycling ? 'Running...' : 'Run Cycle'}
          </button>
        </div>
      </div>

      {/* Stats Row */}
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
          <div className="stat-sub">{busyAgentIds.size} busy</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Spend</div>
          <div className="stat-value">${stats.total_cost_usd}</div>
          <div className="stat-sub">this period</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Tasks</div>
          <div className="stat-value accent">{total}</div>
          <div style={{ display: 'flex', gap: '3px', alignItems: 'flex-end', marginTop: '6px', height: '22px' }}>
            <div style={miniBarStyle(stats.tasks.pending, '#f1c40f')} title={`Pending: ${stats.tasks.pending}`} />
            <div style={miniBarStyle(stats.tasks.running, '#3498db')} title={`Running: ${stats.tasks.running}`} />
            <div style={miniBarStyle(stats.tasks.success, '#2ecc71')} title={`Success: ${stats.tasks.success}`} />
            <div style={miniBarStyle(stats.tasks.failed, '#e74c3c')} title={`Failed: ${stats.tasks.failed}`} />
          </div>
        </div>
      </div>

      {/* Two Column Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: '16px', marginTop: '8px' }}>

        {/* LEFT COLUMN */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

          {/* Task Pipeline Chart */}
          <div className="card" style={{ padding: '20px' }}>
            <div className="section-title" style={{ marginBottom: '16px' }}>Task Pipeline</div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '24px', height: '140px', padding: '0 12px' }}>
              {[
                { label: 'Pending', value: stats.tasks.pending, color: '#f1c40f' },
                { label: 'Running', value: stats.tasks.running, color: '#3498db' },
                { label: 'Success', value: stats.tasks.success, color: '#2ecc71' },
                { label: 'Failed', value: stats.tasks.failed, color: '#e74c3c' },
              ].map(bar => (
                <div key={bar.label} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                  <span style={{ fontSize: '13px', fontWeight: 600, color: bar.color }}>{bar.value}</span>
                  <div style={barStyle(bar.value, bar.color)} />
                  <span style={{ fontSize: '11px', opacity: 0.7, marginTop: '4px' }}>{bar.label}</span>
                </div>
              ))}
            </div>
            {/* Horizontal proportion bar */}
            <div style={{ display: 'flex', height: '6px', borderRadius: '3px', overflow: 'hidden', marginTop: '16px', background: 'var(--card-border)' }}>
              {total > 0 && <>
                <div style={{ width: `${(stats.tasks.pending / total) * 100}%`, background: '#f1c40f' }} />
                <div style={{ width: `${(stats.tasks.running / total) * 100}%`, background: '#3498db' }} />
                <div style={{ width: `${(stats.tasks.success / total) * 100}%`, background: '#2ecc71' }} />
                <div style={{ width: `${(stats.tasks.failed / total) * 100}%`, background: '#e74c3c' }} />
              </>}
            </div>
          </div>

          {/* Store Status */}
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div className="section-title" style={{ margin: 0 }}>Store Status</div>
              <button className="btn btn-primary" onClick={syncAllStores} disabled={storesSyncing} style={{ fontSize: '12px', padding: '4px 12px' }}>
                {storesSyncing ? 'Syncing...' : 'Sync All'}
              </button>
            </div>
            {stores.length === 0 ? (
              <div className="empty-state" style={{ padding: '20px' }}>
                <div className="empty-state-icon">~</div>
                No marketing stores connected.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {stores.map(store => (
                  <div key={store.id || store.name} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '10px 12px', borderRadius: '6px', background: 'var(--bg)', border: '1px solid var(--card-border)',
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>{store.name || store.id}</div>
                      <div style={{ fontSize: '11px', opacity: 0.6, marginTop: '2px' }}>
                        {store.last_updated ? `Updated ${store.last_updated.slice(0, 10)}` : 'No sync data'}
                      </div>
                    </div>
                    {store.revenue !== undefined && store.revenue !== null && (
                      <div style={{ fontWeight: 700, fontSize: '14px', color: '#2ecc71' }}>
                        ${typeof store.revenue === 'number' ? store.revenue.toLocaleString() : store.revenue}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

          {/* Agent Workforce */}
          <div className="card" style={{ padding: '20px' }}>
            <div className="section-title" style={{ marginBottom: '12px' }}>Agent Workforce</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {levelOrder.filter(l => agentsByLevel[l]).map(level => (
                <div key={level} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{
                    width: '8px', height: '8px', borderRadius: '50%', background: levelColors[level],
                    flexShrink: 0, boxShadow: `0 0 6px ${levelColors[level]}44`,
                  }} />
                  <span style={{ fontSize: '12px', textTransform: 'capitalize', width: '70px', opacity: 0.8 }}>{level}</span>
                  <div style={{
                    flex: 1, height: '20px', background: 'var(--bg)', borderRadius: '4px', overflow: 'hidden',
                    position: 'relative', border: '1px solid var(--card-border)',
                  }}>
                    <div style={{
                      width: `${Math.min((agentsByLevel[level].length / Math.max(agents.length, 1)) * 100, 100)}%`,
                      height: '100%', background: `${levelColors[level]}33`, borderRadius: '4px',
                      minWidth: agentsByLevel[level].length > 0 ? '20px' : '0',
                    }} />
                    <span style={{
                      position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)',
                      fontSize: '11px', fontWeight: 600,
                    }}>
                      {agentsByLevel[level].length}
                    </span>
                  </div>
                  <span style={{ fontSize: '11px', opacity: 0.5, width: '40px', textAlign: 'right' }}>
                    {agentsByLevel[level].filter(a => busyAgentIds.has(a.agent_id || a.id)).length} busy
                  </span>
                </div>
              ))}
              {/* Unknown / other levels */}
              {Object.keys(agentsByLevel).filter(l => !levelOrder.includes(l)).map(level => (
                <div key={level} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{
                    width: '8px', height: '8px', borderRadius: '50%', background: levelColors.unknown,
                    flexShrink: 0,
                  }} />
                  <span style={{ fontSize: '12px', textTransform: 'capitalize', width: '70px', opacity: 0.8 }}>{level}</span>
                  <span style={{ fontSize: '12px', fontWeight: 600 }}>{agentsByLevel[level].length}</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: '1px solid var(--card-border)', fontSize: '12px', opacity: 0.6 }}>
              {agents.length} total agents | {busyAgentIds.size} with active tasks
            </div>
          </div>

          {/* Quick Actions */}
          <div className="card" style={{ padding: '20px' }}>
            <div className="section-title" style={{ marginBottom: '12px' }}>Quick Actions</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button className="btn" onClick={() => navigate('/issues')} style={{ width: '100%', textAlign: 'left', padding: '10px 14px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ width: '20px', textAlign: 'center', opacity: 0.6 }}>+</span>
                <span>New Request</span>
              </button>
              <button className="btn" onClick={runCycle} disabled={cycling} style={{ width: '100%', textAlign: 'left', padding: '10px 14px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ width: '20px', textAlign: 'center', opacity: 0.6 }}>&#9654;</span>
                <span>{cycling ? 'Running...' : 'Run Cycle'}</span>
              </button>
              <button className="btn" onClick={() => navigate('/org')} style={{ width: '100%', textAlign: 'left', padding: '10px 14px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ width: '20px', textAlign: 'center', opacity: 0.6 }}>&#9733;</span>
                <span>View Org Chart</span>
              </button>
              <button
                className="btn"
                onClick={fetchMarketingSummary}
                disabled={summaryLoading}
                style={{ width: '100%', textAlign: 'left', padding: '10px 14px', display: 'flex', alignItems: 'center', gap: '10px' }}
              >
                <span style={{ width: '20px', textAlign: 'center', opacity: 0.6 }}>&#9672;</span>
                <span>{summaryLoading ? 'Loading...' : 'Marketing Summary'}</span>
              </button>
            </div>
            {marketingSummary && (
              <div style={{
                marginTop: '12px', padding: '12px', borderRadius: '6px',
                background: 'var(--bg)', border: '1px solid var(--card-border)', fontSize: '12px',
              }}>
                {marketingSummary.error ? (
                  <span style={{ color: '#e74c3c' }}>{marketingSummary.error}</span>
                ) : (
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit', lineHeight: 1.5 }}>
                    {typeof marketingSummary === 'string' ? marketingSummary : JSON.stringify(marketingSummary, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Issues - Full Width */}
      <div style={{ marginTop: '16px' }}>
        <div className="section-title">Recent Issues</div>
        <div className="issue-list">
          {recentTasks.length === 0 && (
            <div className="empty-state">
              <div className="empty-state-icon">~</div>
              No issues yet. Create one from the Issues page.
            </div>
          )}
          {recentTasks.map((t, i) => (
            <div
              className="issue-row"
              key={t.id}
              style={{ cursor: 'pointer' }}
              onClick={() => navigate(`/issues/${t.id}`)}
            >
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
    </div>
  );
}

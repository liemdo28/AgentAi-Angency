import React, { useEffect, useState } from 'react';
import { executeSmartIssue, listProjects } from '../api';

const TYPE_COLORS = {
  python: '#3572A5',
  node: '#68A063',
  html: '#E34C26',
  php: '#4F5D95',
};

const CATEGORY_LABELS = {
  core: 'Core',
  website: 'Website',
  operations: 'Operations',
  analytics: 'Analytics',
  reviews: 'Reviews',
};

function getStatusInfo(project) {
  const s = (project.status || '').toLowerCase();
  if (s === 'online' || s === 'running') {
    return { cls: 'status-running', label: 'Running' };
  }
  if (s === 'idle' || s === 'stopped') {
    return { cls: 'status-idle', label: 'Idle' };
  }
  return { cls: 'status-offline', label: 'Offline' };
}

function truncatePath(p, maxLen = 40) {
  if (!p || p.length <= maxLen) return p;
  return '...' + p.slice(-(maxLen - 3));
}

function formatDate(value) {
  if (!value) return '-';
  return value.slice(0, 10);
}

function formatTime(value) {
  if (!value) return '-';
  return value.replace('T', ' ').replace('Z', ' UTC').slice(0, 19);
}

export default function Projects() {
  const [projects, setProjects] = useState([]);
  const [filter, setFilter] = useState('');
  const [busySuggestionId, setBusySuggestionId] = useState('');

  const load = () => listProjects().then(setProjects).catch(() => {});

  useEffect(() => {
    load();
  }, []);

  const categories = [...new Set(projects.map((p) => p.category))];
  const filtered = filter ? projects.filter((p) => p.category === filter) : projects;

  const countByStatus = (label) => projects.filter((p) => getStatusInfo(p).label === label).length;
  const runningCount = countByStatus('Running');
  const idleCount = countByStatus('Idle');
  const offlineCount = countByStatus('Offline');

  const handleSuggestion = async (suggestion) => {
    if (!suggestion?.prompt) return;
    setBusySuggestionId(suggestion.id);
    try {
      await executeSmartIssue(suggestion.prompt);
      window.alert(`Created workflow tasks for: ${suggestion.title}`);
    } catch (error) {
      window.alert(`Could not create workflow tasks: ${error.message}`);
    } finally {
      setBusySuggestionId('');
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h1>Projects</h1>
          <span className="text-secondary" style={{ fontSize: 13 }}>
            {runningCount}/{projects.length} running
          </span>
        </div>
        <div className="tab-bar">
          <button className={`tab-btn ${filter === '' ? 'active' : ''}`} onClick={() => setFilter('')}>
            All
          </button>
          {categories.map((c) => (
            <button key={c} className={`tab-btn ${filter === c ? 'active' : ''}`} onClick={() => setFilter(c)}>
              {CATEGORY_LABELS[c] || c}
            </button>
          ))}
        </div>
      </div>

      <div className="stats-row" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="stat-card">
          <div className="stat-label">Running</div>
          <div className="stat-value green">{runningCount}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Idle</div>
          <div className="stat-value">{idleCount}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Offline</div>
          <div className="stat-value red">{offlineCount}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Uncommitted</div>
          <div className="stat-value yellow">{projects.filter((p) => p.dirty).length}</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))', gap: 12 }}>
        {filtered.map((p) => {
          const status = getStatusInfo(p);
          const ops = p.integration_ops;
          const opsProfile = p.ops_profile || {};
          const latestDownload = ops?.latest_downloads || [];
          const latestQbSync = ops?.latest_qb_sync || [];
          const suggestions = ops?.ai_suggestions || [];
          const profileSignals = opsProfile.signals || [];
          const profileSuggestions = opsProfile.suggestions || [];

          return (
            <div key={p.id} className="org-card project-card" style={{ textAlign: 'left', padding: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 10 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>{p.name}</div>
                  <div className="text-dim" style={{ fontSize: 12 }}>{p.id}</div>
                </div>
                <span className={status.cls}>{status.label}</span>
              </div>

              <div className="text-secondary" style={{ fontSize: 12, marginBottom: 12, lineHeight: 1.5 }}>
                {p.description}
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 10 }}>
                {p.tech?.map((t) => (
                  <span
                    key={t}
                    style={{
                      fontSize: 10,
                      padding: '2px 6px',
                      borderRadius: 3,
                      background: 'var(--bg-surface2)',
                      color: 'var(--text-secondary)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    {t}
                  </span>
                ))}
              </div>

              <div style={{ borderTop: '1px solid var(--border)', paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {p.local_path && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span className="text-dim">Path</span>
                    <span className="mono" title={p.local_path} style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {truncatePath(p.local_path)}
                    </span>
                  </div>
                )}
                {p.branch && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span className="text-dim">Branch</span>
                    <span className="mono" style={{ color: 'var(--accent)' }}>{p.branch}</span>
                  </div>
                )}
                {p.last_commit && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span className="text-dim">Latest</span>
                    <span className="text-secondary" style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.last_commit}
                    </span>
                  </div>
                )}
                {p.last_commit_date && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span className="text-dim">Date</span>
                    <span className="text-secondary">{formatDate(p.last_commit_date)}</span>
                  </div>
                )}
                {p.dirty && (
                  <div style={{ fontSize: 11, color: 'var(--yellow)', marginTop: 2 }}>
                    Uncommitted changes
                  </div>
                )}
                {p.port && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span className="text-dim">Port</span>
                    <span className="mono">{p.port}</span>
                  </div>
                )}
                {p.github && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span className="text-dim">GitHub</span>
                    <a
                      href={`https://github.com/${p.github}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: 'var(--blue)', textDecoration: 'none', fontFamily: 'var(--mono)', fontSize: 12 }}
                    >
                      {p.github.includes('/') ? p.github.split('/').pop() : p.github}
                    </a>
                  </div>
                )}
              </div>

              {ops && (
                <div className="project-ops">
                  <div className="project-ops-grid">
                    <div className="project-mini-stat">
                      <div className="project-mini-label">Last Download</div>
                      <div className="project-mini-value">{formatDate(ops.summary?.last_download_at)}</div>
                    </div>
                    <div className="project-mini-stat">
                      <div className="project-mini-label">Last QB Sync</div>
                      <div className="project-mini-value">{formatDate(ops.summary?.last_qb_sync_at)}</div>
                    </div>
                    <div className="project-mini-stat">
                      <div className="project-mini-label">Download Gaps</div>
                      <div className="project-mini-value">{ops.summary?.download_gap_count ?? 0}</div>
                    </div>
                    <div className="project-mini-stat">
                      <div className="project-mini-label">QB Gaps</div>
                      <div className="project-mini-value">{ops.summary?.qb_gap_count ?? 0}</div>
                    </div>
                  </div>

                  <div className="project-section-title">Latest Download Activity</div>
                  <div className="project-feed">
                    {latestDownload.length === 0 && <div className="project-feed-empty">No successful downloads found yet.</div>}
                    {latestDownload.map((item) => (
                      <div key={`${item.store}-${item.report_key}-${item.business_date}`} className="project-feed-row">
                        <div>
                          <div className="project-feed-title">{item.store} · {item.report_label}</div>
                          <div className="project-feed-sub">{item.business_date || 'Unknown date'} · {formatTime(item.saved_at)}</div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="project-section-title">Latest QB Sync Activity</div>
                  <div className="project-feed">
                    {latestQbSync.length === 0 && <div className="project-feed-empty">No successful QB sync runs found yet.</div>}
                    {latestQbSync.map((item) => (
                      <div key={`${item.store}-${item.source_name}-${item.date}`} className="project-feed-row">
                        <div>
                          <div className="project-feed-title">{item.store} · {item.source_name || 'Unknown'}</div>
                          <div className="project-feed-sub">{item.date || 'Unknown date'} · {formatTime(item.completed_at)}</div>
                        </div>
                        <span className="badge success">{item.status}</span>
                      </div>
                    ))}
                  </div>

                  <div className="project-section-title">AI Next Actions</div>
                  <div className="project-suggestion-list">
                    {suggestions.length === 0 && <div className="project-feed-empty">No suggestions right now.</div>}
                    {suggestions.map((suggestion) => (
                      <div key={suggestion.id} className="project-suggestion-card">
                        <div className="project-feed-title">{suggestion.title}</div>
                        <div className="project-feed-sub">{suggestion.description}</div>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => handleSuggestion(suggestion)}
                          disabled={busySuggestionId === suggestion.id}
                        >
                          {busySuggestionId === suggestion.id ? 'Creating...' : suggestion.action_label}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {!ops && opsProfile && (
                <div className="project-ops">
                  <div className="project-ops-grid">
                    <div className="project-mini-stat">
                      <div className="project-mini-label">Profile</div>
                      <div className="project-mini-value">{opsProfile.kind || '-'}</div>
                    </div>
                    <div className="project-mini-stat">
                      <div className="project-mini-label">Signals</div>
                      <div className="project-mini-value">{profileSignals.length}</div>
                    </div>
                  </div>

                  <div className="project-section-title">Ops Signals</div>
                  <div className="project-feed">
                    {profileSignals.length === 0 && <div className="project-feed-empty">No signals yet.</div>}
                    {profileSignals.map((item) => (
                      <div key={`${p.id}-${item.label}`} className="project-feed-row">
                        <div>
                          <div className="project-feed-title">{item.label}</div>
                          <div className="project-feed-sub">{item.value}</div>
                        </div>
                        <span className={`badge ${item.status === 'ok' ? 'success' : item.status === 'warning' ? 'pending' : 'failed'}`}>
                          {item.status}
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="project-section-title">AI Next Actions</div>
                  <div className="project-suggestion-list">
                    {profileSuggestions.length === 0 && <div className="project-feed-empty">No suggestions right now.</div>}
                    {profileSuggestions.map((suggestion) => (
                      <div key={suggestion.id} className="project-suggestion-card">
                        <div className="project-feed-title">{suggestion.title}</div>
                        <div className="project-feed-sub">{suggestion.description}</div>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => handleSuggestion(suggestion)}
                          disabled={busySuggestionId === suggestion.id}
                        >
                          {busySuggestionId === suggestion.id ? 'Creating...' : suggestion.action_label}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  right: 0,
                  width: 4,
                  height: '100%',
                  borderRadius: '0 10px 10px 0',
                  background: TYPE_COLORS[p.type] || 'var(--text-muted)',
                }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { executeSmartIssue, listProjects, runProjectLiveQa, runProjectQaSimulation } from '../api';

const QA_STORAGE_KEY = 'agentai.projects.qaRuns.v2';
const TYPE_COLORS = { python: '#3572A5', node: '#68A063', html: '#E34C26', php: '#4F5D95' };
const CATEGORY_LABELS = { core: 'Core', website: 'Website', operations: 'Operations', analytics: 'Analytics', reviews: 'Reviews' };

function getStatusInfo(project) {
  const status = (project.status || '').toLowerCase();
  if (status === 'online') return { cls: 'status-running', label: 'Live' };
  if (status === 'running') return { cls: 'status-running', label: 'Running' };
  if (status === 'idle' || status === 'stopped') return { cls: 'status-idle', label: 'Idle' };
  return { cls: 'status-offline', label: 'Offline' };
}

function formatScore(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  return `${value.toFixed(2)}/10`;
}

function formatDate(value) {
  return value ? value.slice(0, 10) : '-';
}

function formatTime(value) {
  return value ? value.replace('T', ' ').replace('Z', ' UTC').slice(0, 19) : '-';
}

function loadStoredQaRuns() {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(QA_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function dedupeSuggestions(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = item?.id || item?.title;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function loopBadge(loop) {
  const status = loop?.status;
  if (status === 'passed') return { cls: 'success', label: 'PASS' };
  if (status === 'escalated') return { cls: 'failed', label: 'CEO' };
  if (status === 'retesting') return { cls: 'pending', label: 'RETEST' };
  if (status === 'fixing') return { cls: 'pending', label: 'FIXING' };
  if (status === 'failed') return { cls: 'failed', label: 'FAILED' };
  return { cls: 'pending', label: 'QUEUE' };
}

function summaryStats(project, opsProfile, signalCount) {
  const items = [
    { label: 'Category', value: CATEGORY_LABELS[project.category] || project.category || 'General' },
    { label: 'Type', value: project.type || 'generic' },
    { label: 'Profile', value: (opsProfile.kind || 'generic').replace(/_/g, ' ') },
    { label: 'Signals', value: String(signalCount) },
  ];
  if (project.latency_ms != null) items.push({ label: 'Latency', value: `${project.latency_ms}ms` });
  else if (project.port) items.push({ label: 'Port', value: String(project.port) });
  else if (project.branch) items.push({ label: 'Branch', value: project.branch });
  return items;
}

export default function Projects() {
  const [projects, setProjects] = useState([]);
  const [filter, setFilter] = useState('');
  const [busySuggestionId, setBusySuggestionId] = useState('');
  const [successMsg, setSuccessMsg] = useState(null);
  const [qaRuns, setQaRuns] = useState(loadStoredQaRuns);
  const [liveQaRuns, setLiveQaRuns] = useState({});
  const navigate = useNavigate();

  const load = () => listProjects().then(setProjects).catch(() => {});

  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (typeof window !== 'undefined') window.localStorage.setItem(QA_STORAGE_KEY, JSON.stringify(qaRuns));
  }, [qaRuns]);

  const categories = [...new Set(projects.map((project) => project.category))];
  const filtered = filter ? projects.filter((project) => project.category === filter) : projects;
  const countByStatus = (label) => projects.filter((project) => getStatusInfo(project).label === label).length;
  const liveCount = projects.filter((project) => ['online', 'running'].includes((project.status || '').toLowerCase())).length;

  const handleSuggestion = async (suggestion, project) => {
    if (!suggestion?.prompt) return;
    setBusySuggestionId(suggestion.id);
    setSuccessMsg(null);
    try {
      if (suggestion.action_type === 'qa_simulation') {
        const result = await runProjectQaSimulation(project.id, {
          goal: suggestion.prompt,
          tester_count: 1000,
          max_iterations: 100,
          pass_threshold: 8.5,
        });
        setQaRuns((current) => ({ ...current, [project.id]: result }));
        return;
      }
      if (suggestion.action_type === 'qa_live') {
        const result = await runProjectLiveQa(project.id, {
          pass_threshold: 8.5,
          timeout_ms: 15000,
          auto_create_fix_tasks: true,
          max_retest_cycles: 5,
        });
        setLiveQaRuns((current) => ({ ...current, [project.id]: result }));
        load();
        return;
      }
      const result = await executeSmartIssue(suggestion.prompt);
      setSuccessMsg({ projectId: project.id, text: suggestion.title, taskCount: result.total_created || 0, phases: result.total_phases || 0 });
      setTimeout(() => setSuccessMsg(null), 8000);
    } catch (error) {
      if (suggestion.action_type === 'qa_simulation') {
        setQaRuns((current) => ({ ...current, [project.id]: { error: error.message || 'Simulation failed.' } }));
      } else if (suggestion.action_type === 'qa_live') {
        setLiveQaRuns((current) => ({ ...current, [project.id]: { error: error.message || 'Live browser QA failed.' } }));
      } else {
        setSuccessMsg({ projectId: project.id, text: `Error: ${error.message}`, taskCount: 0, phases: 0, isError: true });
        setTimeout(() => setSuccessMsg(null), 5000);
      }
    } finally {
      setBusySuggestionId('');
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <h1>Projects</h1>
            <span className="text-secondary" style={{ fontSize: 13 }}>{liveCount}/{projects.length} live</span>
          </div>
          <div className="page-subtitle">
            Review tracked repositories, open the right actions quickly, and keep QA signal visible at the project level.
          </div>
        </div>
        <div className="tab-bar">
          <button className={`tab-btn ${filter === '' ? 'active' : ''}`} onClick={() => setFilter('')}>All</button>
          {categories.map((category) => (
            <button key={category} className={`tab-btn ${filter === category ? 'active' : ''}`} onClick={() => setFilter(category)}>
              {CATEGORY_LABELS[category] || category}
            </button>
          ))}
        </div>
      </div>

      <div className="stats-row projects-stats-row">
        <div className="stat-card"><div className="stat-label">Live / Running</div><div className="stat-value green">{liveCount}</div></div>
        <div className="stat-card"><div className="stat-label">Idle</div><div className="stat-value">{countByStatus('Idle')}</div></div>
        <div className="stat-card"><div className="stat-label">Offline</div><div className="stat-value red">{countByStatus('Offline')}</div></div>
        <div className="stat-card"><div className="stat-label">Uncommitted</div><div className="stat-value yellow">{projects.filter((project) => project.dirty).length}</div></div>
      </div>

      <div className="projects-grid">
        {filtered.map((project) => {
          const status = getStatusInfo(project);
          const ops = project.integration_ops;
          const opsProfile = project.ops_profile || {};
          const profileSignals = opsProfile.signals || [];
          const suggestions = dedupeSuggestions([...(ops?.ai_suggestions || []), ...(opsProfile.suggestions || [])]);
          const primarySuggestions = suggestions.slice(0, 2);
          const secondarySuggestions = suggestions.slice(2);
          const qaRun = qaRuns[project.id];
          const liveQaRun = liveQaRuns[project.id];
          const liveQaLoop = liveQaRun?.loop_summary || project.live_qa_loop;
          const liveBadge = loopBadge(liveQaLoop);

          return (
            <article key={project.id} className="org-card project-card" style={{ textAlign: 'left', padding: 18 }}>
              <div className="project-head">
                <div className="project-head-copy">
                  <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>{project.name}</div>
                  <div className="text-dim" style={{ fontSize: 12 }}>{project.id}</div>
                </div>
                <div className="project-head-status">
                  {project.latency_ms != null && <span className="mono project-latency">{project.latency_ms}ms</span>}
                  <span className={status.cls}>{status.label}</span>
                </div>
              </div>

              {project.url && (
                <a href={project.url} target="_blank" rel="noopener noreferrer" className={`project-url ${status.label === 'Live' || status.label === 'Running' ? 'is-live' : ''}`}>
                  <span className="project-url-dot" />
                  <span>{project.url.replace(/^https?:\/\//, '')}</span>
                </a>
              )}

              <div className="text-secondary" style={{ fontSize: 12, lineHeight: 1.5 }}>{project.description}</div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {project.tech?.map((tech) => (
                  <span key={tech} style={{ fontSize: 10, padding: '2px 6px', borderRadius: 3, background: 'var(--bg-surface2)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                    {tech}
                  </span>
                ))}
              </div>

              <div className="project-summary-grid">
                {summaryStats(project, opsProfile, profileSignals.length).map((item) => (
                  <div key={`${project.id}-${item.label}`} className="project-mini-stat">
                    <div className="project-mini-label">{item.label}</div>
                    <div className="project-mini-value">{item.value}</div>
                  </div>
                ))}
              </div>

              <div className="project-section-title">Primary Actions</div>
              <div className="project-suggestion-list">
                {primarySuggestions.length === 0 && <div className="project-feed-empty">No priority actions right now.</div>}
                {primarySuggestions.map((suggestion) => (
                  <div key={suggestion.id} className="project-suggestion-card">
                    <div className="project-feed-title">{suggestion.title}</div>
                    <div className="project-feed-sub">{suggestion.description}</div>
                    <button className="btn btn-ghost btn-sm" onClick={() => handleSuggestion(suggestion, project)} disabled={busySuggestionId === suggestion.id}>
                      {busySuggestionId === suggestion.id ? (suggestion.action_type === 'qa_simulation' || suggestion.action_type === 'qa_live' ? 'Running...' : 'Creating...') : suggestion.action_label}
                    </button>
                  </div>
                ))}
              </div>

              <div className="project-inline-actions">
                <button className="btn btn-ghost btn-sm" onClick={() => navigate('/issues')}>Open Issues</button>
                {project.github && <a href={`https://github.com/${project.github}`} target="_blank" rel="noopener noreferrer" className="project-inline-link">Open Repo</a>}
              </div>

              {successMsg && successMsg.projectId === project.id && (
                <div style={{ padding: '8px 12px', borderRadius: 'var(--radius)', background: successMsg.isError ? 'var(--red-bg)' : 'var(--green-bg)', border: `1px solid ${successMsg.isError ? 'rgba(255,107,107,0.3)' : 'rgba(81,207,102,0.3)'}`, fontSize: 12, color: successMsg.isError ? 'var(--red)' : 'var(--green)' }}>
                  {successMsg.isError ? successMsg.text : `Workflow created - ${successMsg.taskCount} tasks across ${successMsg.phases} phases.`}
                </div>
              )}

              {liveQaLoop && (
                <details className="project-panel" open>
                  <summary className="project-panel-summary">
                    <div>
                      <div className="project-panel-title">Live QA Loop</div>
                      <div className="project-panel-sub">Current browser QA status, retest cycles, and escalation path.</div>
                    </div>
                    <span className={`badge ${liveBadge.cls}`}>{liveBadge.label}</span>
                  </summary>
                  <div className="project-panel-body">
                    <div className="project-ops-grid">
                      <div className="project-mini-stat"><div className="project-mini-label">Status</div><div className="project-mini-value">{liveQaLoop.label}</div></div>
                      <div className="project-mini-stat"><div className="project-mini-label">Retests</div><div className="project-mini-value">{liveQaLoop.retest_attempts}/{liveQaLoop.max_retest_cycles}</div></div>
                      <div className="project-mini-stat"><div className="project-mini-label">Pending</div><div className="project-mini-value">{liveQaLoop.pending_tasks}</div></div>
                      <div className="project-mini-stat"><div className="project-mini-label">Escalated</div><div className="project-mini-value">{liveQaLoop.escalated ? 'YES' : 'NO'}</div></div>
                    </div>
                    {liveQaLoop.latest_retest && (
                      <div className="project-feed">
                        <div className="project-feed-row">
                          <div>
                            <div className="project-feed-title">Latest retest - Attempt {liveQaLoop.latest_retest.attempt || liveQaLoop.retest_attempts}</div>
                            <div className="project-feed-sub">{liveQaLoop.latest_retest.summary || 'Retest result stored in the loop.'}</div>
                          </div>
                          <span className={`badge ${liveQaLoop.latest_retest.passed ? 'success' : 'pending'}`}>{formatScore(liveQaLoop.latest_retest.score)}</span>
                        </div>
                      </div>
                    )}
                    {(liveQaLoop.active_tasks || []).length > 0 && (
                      <div className="project-feed">
                        {liveQaLoop.active_tasks.map((task) => (
                          <div key={task.id} className="project-feed-row">
                            <div>
                              <div className="project-feed-title">{task.title}</div>
                              <div className="project-feed-sub">{task.assigned_agent_id}</div>
                            </div>
                            <span className={`badge ${task.status === 'success' ? 'success' : task.status === 'failed' ? 'failed' : 'pending'}`}>{task.status}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </details>
              )}

              {liveQaRun && (
                <details className="project-panel" open>
                  <summary className="project-panel-summary">
                    <div>
                      <div className="project-panel-title">Latest Live QA Run</div>
                      <div className="project-panel-sub">Immediate browser run result before refresh.</div>
                    </div>
                    <span className={`badge ${liveQaRun.error ? 'failed' : liveQaRun.passed ? 'success' : 'failed'}`}>{liveQaRun.error ? 'error' : liveQaRun.passed ? 'pass' : 'retry'}</span>
                  </summary>
                  <div className="project-panel-body">
                    {liveQaRun.error ? (
                      <div className="project-feed-empty" style={{ color: 'var(--red)' }}>Live browser QA failed: {liveQaRun.error}</div>
                    ) : (
                      <>
                        <div className="project-ops-grid">
                          <div className="project-mini-stat"><div className="project-mini-label">Live QA Score</div><div className="project-mini-value">{formatScore(liveQaRun.final_score)}</div></div>
                          <div className="project-mini-stat"><div className="project-mini-label">Gate</div><div className="project-mini-value">{liveQaRun.passed ? 'PASS' : 'REMEDIATE'}</div></div>
                          <div className="project-mini-stat"><div className="project-mini-label">Target</div><div className="project-mini-value">{liveQaRun.target_url ? liveQaRun.target_url.replace(/^https?:\/\//, '') : '-'}</div></div>
                          <div className="project-mini-stat"><div className="project-mini-label">Followup</div><div className="project-mini-value">{liveQaRun.followup_goal ? 'Created' : 'Not needed'}</div></div>
                        </div>
                        <div className="project-feed">
                          <div className="project-feed-row">
                            <div>
                              <div className="project-feed-title">{liveQaRun.summary}</div>
                              <div className="project-feed-sub">{(liveQaRun.profiles || []).map((profile) => profile.name).join(' - ') || 'No viewport profiles completed'}</div>
                            </div>
                            <span className={`badge ${liveQaRun.passed ? 'success' : 'failed'}`}>{liveQaRun.passed ? 'pass' : 'retry'}</span>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                </details>
              )}

              {qaRun && (
                <details className="project-panel" open>
                  <summary className="project-panel-summary">
                    <div>
                      <div className="project-panel-title">QA Simulation</div>
                      <div className="project-panel-sub">Tester score, release gate, findings, and recent loops.</div>
                    </div>
                    <span className={`badge ${qaRun.error ? 'failed' : qaRun.passed ? 'success' : 'failed'}`}>{qaRun.error ? 'error' : qaRun.passed ? 'pass' : 'retry'}</span>
                  </summary>
                  <div className="project-panel-body">
                    {qaRun.error ? (
                      <div className="project-feed-empty" style={{ color: 'var(--red)' }}>QA simulation failed: {qaRun.error}</div>
                    ) : (
                      <>
                        <div className="project-ops-grid">
                          <div className="project-mini-stat"><div className="project-mini-label">Tester Score</div><div className="project-mini-value">{formatScore(qaRun.final_score)}</div></div>
                          <div className="project-mini-stat"><div className="project-mini-label">Loops Used</div><div className="project-mini-value">{qaRun.iterations_run}/{qaRun.max_iterations}</div></div>
                          <div className="project-mini-stat"><div className="project-mini-label">Tester Gate</div><div className="project-mini-value">{qaRun.passed ? 'PASS' : 'RETRY'}</div></div>
                          <div className="project-mini-stat"><div className="project-mini-label">Handoff</div><div className="project-mini-value">{qaRun.final_report?.handoff_target === 'CEO -> user/admin' ? 'CEO' : 'Rework'}</div></div>
                        </div>
                        <div className="project-feed">
                          <div className="project-feed-row">
                            <div>
                              <div className="project-feed-title">{qaRun.final_report?.summary}</div>
                              <div className="project-feed-sub">{qaRun.ceo_summary}</div>
                            </div>
                            <span className={`badge ${qaRun.passed ? 'success' : 'failed'}`}>{qaRun.final_report?.qa_gate}</span>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                </details>
              )}

              <details className="project-panel">
                <summary className="project-panel-summary">
                  <div>
                    <div className="project-panel-title">Project Context</div>
                    <div className="project-panel-sub">Workspace info, ops signals, activity, and more actions.</div>
                  </div>
                  <span className="project-panel-caret">Details</span>
                </summary>
                <div className="project-panel-body">
                  <div className="project-feed">
                    {project.local_path && (
                      <div className="project-feed-row">
                        <div>
                          <div className="project-feed-title">Path</div>
                          <div className="project-feed-sub">{project.local_path}</div>
                        </div>
                      </div>
                    )}
                    {project.last_commit && (
                      <div className="project-feed-row">
                        <div>
                          <div className="project-feed-title">Latest Commit</div>
                          <div className="project-feed-sub">{project.last_commit} - {formatDate(project.last_commit_date)}</div>
                        </div>
                      </div>
                    )}
                    {profileSignals.map((item) => (
                      <div key={`${project.id}-${item.label}`} className="project-feed-row">
                        <div>
                          <div className="project-feed-title">{item.label}</div>
                          <div className="project-feed-sub">{item.value}</div>
                        </div>
                        <span className={`badge ${item.status === 'ok' ? 'success' : item.status === 'warning' ? 'pending' : 'failed'}`}>{item.status}</span>
                      </div>
                    ))}
                    {(ops?.latest_downloads || []).slice(0, 2).map((item) => (
                      <div key={`${item.store}-${item.report_key}-${item.business_date}`} className="project-feed-row">
                        <div>
                          <div className="project-feed-title">{item.store} - {item.report_label}</div>
                          <div className="project-feed-sub">{item.business_date || 'Unknown date'} - {formatTime(item.saved_at)}</div>
                        </div>
                      </div>
                    ))}
                    {(secondarySuggestions || []).map((suggestion) => (
                      <div key={suggestion.id} className="project-suggestion-card">
                        <div className="project-feed-title">{suggestion.title}</div>
                        <div className="project-feed-sub">{suggestion.description}</div>
                        <button className="btn btn-ghost btn-sm" onClick={() => handleSuggestion(suggestion, project)} disabled={busySuggestionId === suggestion.id}>
                          {busySuggestionId === suggestion.id ? (suggestion.action_type === 'qa_simulation' || suggestion.action_type === 'qa_live' ? 'Running...' : 'Creating...') : suggestion.action_label}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </details>

              <div style={{ position: 'absolute', top: 0, right: 0, width: 4, height: '100%', borderRadius: '0 10px 10px 0', background: TYPE_COLORS[project.type] || 'var(--text-muted)' }} />
            </article>
          );
        })}
      </div>
    </div>
  );
}

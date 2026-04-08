import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { listTasks, cancelTask, planSmartIssue, executeSmartIssue, executeTask } from '../api';

const PHASE_COLORS = { 1: 'var(--blue)', 2: 'var(--accent)', 3: 'var(--green)' };
const PHASE_ICONS = { 1: '\u{1F50D}', 2: '\u26A1', 3: '\u{1F680}' };

export default function Issues() {
  const [tasks, setTasks] = useState([]);
  const [filter, setFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [inputText, setInputText] = useState('');
  const [plan, setPlan] = useState(null);
  const [planning, setPlanning] = useState(false);
  const [executing, setExecuting] = useState(false);
  const navigate = useNavigate();

  const load = () => listTasks(filter || undefined).then(setTasks).catch(() => {});
  useEffect(() => { load(); }, [filter]);

  // Plan workflow from natural language
  const handlePlan = async () => {
    if (!inputText.trim()) return;
    setPlanning(true);
    setPlan(null);
    try {
      const result = await planSmartIssue(inputText.trim());
      setPlan(result);
    } catch (e) {
      console.error(e);
    } finally {
      setPlanning(false);
    }
  };

  // Execute: create goal + all tasks
  const handleExecute = async () => {
    if (!inputText.trim()) return;
    setExecuting(true);
    try {
      await executeSmartIssue(inputText.trim());
      setPlan(null);
      setInputText('');
      setShowCreate(false);
      load();
    } catch (e) {
      console.error(e);
    } finally {
      setExecuting(false);
    }
  };

  const handleCancel = async (e, id) => {
    e.stopPropagation();
    await cancelTask(id);
    load();
  };

  const [executingGroup, setExecutingGroup] = useState(null); // goalId being executed
  const [executingTask, setExecutingTask] = useState(null);   // single task id

  const running = tasks.filter(t => t.status === 'running').length;

  const handleExecuteAll = async (goalId, goalTasks) => {
    const pending = goalTasks.filter(t => t.status === 'pending' || t.status === 'failed');
    if (pending.length === 0) return;
    setExecutingGroup(goalId);
    for (const t of pending) {
      setExecutingTask(t.id);
      try { await executeTask(t.id); } catch {}
    }
    setExecutingGroup(null);
    setExecutingTask(null);
    load();
  };

  const handleExecuteOne = async (e, taskId) => {
    e.stopPropagation();
    setExecutingTask(taskId);
    try { await executeTask(taskId); } catch {}
    setExecutingTask(null);
    load();
  };

  // Group tasks by goal for display
  const goalGroups = {};
  const ungrouped = [];
  tasks.forEach(t => {
    if (t.goal_id) {
      if (!goalGroups[t.goal_id]) goalGroups[t.goal_id] = [];
      goalGroups[t.goal_id].push(t);
    } else {
      ungrouped.push(t);
    }
  });

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <h1>Issues</h1>
            {running > 0 && <span className="badge-live">{running} live</span>}
          </div>
          <div className="page-subtitle">
            Turn natural-language requests into routed workflows, preview the plan, and run each task through the right AI team.
          </div>
        </div>
        <div className="page-header-actions">
          <div className="tab-bar">
            {['', 'pending', 'running', 'success', 'failed'].map(s => (
              <button key={s} className={`tab-btn ${filter === s ? 'active' : ''}`} onClick={() => setFilter(s)}>
                {s || 'All'}
              </button>
            ))}
          </div>
          <button className="btn btn-primary" onClick={() => { setShowCreate(!showCreate); setPlan(null); }}>
            + New Request
          </button>
        </div>
      </div>

      {/* ── Smart Issue Creator ─────────────────────────────── */}
      {showCreate && (
        <div className="create-panel" style={{ marginBottom: 20 }}>
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>What do you need?</div>
            <div className="text-secondary" style={{ fontSize: 12, marginBottom: 10 }}>
              Describe your request in natural language. The system will analyze it and assign the right agents automatically.
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <textarea
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              placeholder='e.g. "I need a professional post to promote Sushi for April" or "Run Facebook ads for Bakudan Ramen with $500 budget"'
              rows={3}
              style={{ flex: 1, resize: 'vertical', fontFamily: 'var(--font)', fontSize: 13 }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handlePlan(); } }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <button className="btn btn-ghost" onClick={handlePlan} disabled={planning || !inputText.trim()}>
                {planning ? 'Analyzing...' : 'Preview Plan'}
              </button>
              {plan && (
                <button className="btn btn-primary" onClick={handleExecute} disabled={executing}>
                  {executing ? 'Creating...' : `Execute (${plan.total_tasks} tasks)`}
                </button>
              )}
            </div>
          </div>

          {/* ── Workflow Plan Preview ─────────────────────────── */}
          {plan && (
            <div style={{ marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>{plan.template_name}</span>
                  <span className="text-dim" style={{ marginLeft: 8, fontSize: 12 }}>
                    {plan.total_tasks} tasks across {plan.estimated_agents} agents
                  </span>
                </div>
                {plan.template && (
                  <span style={{
                    fontSize: 10, padding: '2px 8px', borderRadius: 4,
                    background: 'var(--accent-bg)', color: 'var(--accent)',
                    fontWeight: 600, textTransform: 'uppercase',
                  }}>
                    {plan.template} template
                  </span>
                )}
              </div>

              <div className="text-secondary" style={{ fontSize: 12, marginBottom: 16 }}>{plan.summary}</div>

              {/* Phases */}
              {plan.phases.map(phase => (
                <div key={phase.phase} style={{ marginBottom: 16 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
                    fontSize: 12, fontWeight: 600, color: PHASE_COLORS[phase.phase] || 'var(--text)',
                  }}>
                    <span>{PHASE_ICONS[phase.phase] || ''}</span>
                    <span>Phase {phase.phase}: {phase.name}</span>
                    <span style={{
                      fontSize: 10, background: 'var(--bg-surface2)', color: 'var(--text-muted)',
                      padding: '1px 6px', borderRadius: 3,
                    }}>
                      {phase.tasks.length} tasks
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {phase.tasks.map((task, ti) => (
                      <div key={ti} style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 12px',
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius)',
                        borderLeft: `3px solid ${PHASE_COLORS[phase.phase] || 'var(--border)'}`,
                      }}>
                        <div style={{
                          width: 28, height: 28, borderRadius: '50%',
                          background: 'var(--accent-bg)', color: 'var(--accent)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 10, fontWeight: 700, flexShrink: 0,
                        }}>
                          {(task.agent_title || '').slice(0, 2).toUpperCase()}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 500 }}>{task.title}</div>
                          {task.tools && task.tools.length > 0 && (
                            <div style={{ display: 'flex', gap: 3, marginTop: 3, flexWrap: 'wrap' }}>
                              {task.tools.slice(0, 3).map(tool => (
                                <span key={tool} style={{
                                  fontSize: 9, padding: '1px 5px', borderRadius: 3,
                                  background: 'var(--bg-surface2)', color: 'var(--text-muted)',
                                }}>{tool}</span>
                              ))}
                            </div>
                          )}
                        </div>
                        <span className="issue-agent">{task.agent_id}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Task List (grouped by goal) ──────────────────────── */}
      <div className="issue-list">
        {tasks.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">~</div>
            No issues yet. Click "+ New Request" to describe what you need.
          </div>
        )}

        {/* Grouped workflows */}
        {Object.entries(goalGroups).map(([goalId, goalTasks]) => {
          const done = goalTasks.filter(t => t.status === 'success').length;
          const total = goalTasks.length;
          const pct = total > 0 ? Math.round((done / total) * 100) : 0;
          // Get workflow name from first task's context
          const firstCtx = (() => { try { return typeof goalTasks[0]?.context_json === 'string' ? JSON.parse(goalTasks[0].context_json) : goalTasks[0]?.context_json; } catch { return {}; } })();
          const request = firstCtx?.original_request || goalTasks[0]?.title || 'Workflow';

          return (
            <div key={goalId}>
              {/* Workflow header */}
              <div style={{
                padding: '10px 16px',
                background: 'var(--bg-surface2)',
                borderBottom: '1px solid var(--border)',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{request.length > 60 ? request.slice(0, 60) + '...' : request}</span>
                  <span className="text-dim" style={{ fontSize: 11 }}>{done}/{total} done</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 60, height: 4, background: 'var(--bg-hover)', borderRadius: 2 }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: 'var(--green)', borderRadius: 2 }} />
                  </div>
                  <span className="mono text-dim" style={{ fontSize: 11 }}>{pct}%</span>
                  {done < total && (
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleExecuteAll(goalId, goalTasks)}
                      disabled={executingGroup === goalId}
                      style={{ marginLeft: 4 }}
                    >
                      {executingGroup === goalId ? `Running ${executingTask?.slice(0,4)}...` : `Execute All (${total - done})`}
                    </button>
                  )}
                </div>
              </div>

              {/* Sub-tasks */}
              {goalTasks.map((t, i) => {
                const ctx = (() => { try { return typeof t.context_json === 'string' ? JSON.parse(t.context_json) : t.context_json; } catch { return {}; } })();
                return (
                  <div className="issue-row" key={t.id} onClick={() => navigate(`/issues/${t.id}`)}
                    style={{ paddingLeft: 32 }}>
                    <div className={`issue-status-dot ${t.status}`} />
                    {ctx?.phase_name && (
                      <span style={{
                        fontSize: 9, padding: '1px 5px', borderRadius: 3,
                        background: PHASE_COLORS[ctx?.phase] ? `color-mix(in srgb, ${PHASE_COLORS[ctx?.phase]} 15%, transparent)` : 'var(--bg-surface2)',
                        color: PHASE_COLORS[ctx?.phase] || 'var(--text-muted)',
                        fontWeight: 600, whiteSpace: 'nowrap',
                      }}>P{ctx?.phase}</span>
                    )}
                    <span className="issue-title">{t.title}</span>
                    <div className="issue-meta">
                      <span className="issue-agent">{t.assigned_agent_id}</span>
                      <span className={`badge ${t.status}`}>{t.status}</span>
                      {(t.status === 'pending' || t.status === 'failed') && (
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={e => handleExecuteOne(e, t.id)}
                          disabled={executingTask === t.id}
                          style={{ marginLeft: 2 }}
                        >
                          {executingTask === t.id ? 'AI...' : 'Run'}
                        </button>
                      )}
                      {(t.status === 'pending' || t.status === 'running') && (
                        <button className="btn btn-danger btn-sm" onClick={e => handleCancel(e, t.id)}>Cancel</button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}

        {/* Ungrouped tasks */}
        {ungrouped.map((t, i) => (
          <div className="issue-row" key={t.id} onClick={() => navigate(`/issues/${t.id}`)}>
            <div className={`issue-status-dot ${t.status}`} />
            <span className="issue-id">#{String(i + 1).padStart(4, '0')}</span>
            <span className="issue-title">{t.title}</span>
            <div className="issue-meta">
              <span className="issue-agent">{t.assigned_agent_id}</span>
              <span className={`badge ${t.status}`}>{t.status}</span>
              {(t.status === 'pending' || t.status === 'running') && (
                <button className="btn btn-danger btn-sm" onClick={e => handleCancel(e, t.id)}>Cancel</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

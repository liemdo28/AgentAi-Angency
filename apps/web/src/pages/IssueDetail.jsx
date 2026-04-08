import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getTask, listJobs, cancelTask, executeTask } from '../api';

export default function IssueDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [task, setTask] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState(null);

  const load = useCallback(() => {
    getTask(id).then(setTask).catch(() => navigate('/issues'));
    listJobs(id).then(setJobs).catch(() => {});
  }, [id, navigate]);

  useEffect(() => { load(); }, [load]);

  if (!task) return <div className="page"><div className="empty-state">Loading...</div></div>;

  const handleCancel = async () => {
    await cancelTask(id);
    setTask({ ...task, status: 'cancelled' });
  };

  const handleExecute = async () => {
    setExecuting(true);
    setExecResult(null);
    try {
      const result = await executeTask(id);
      setExecResult(result);
      // Reload task + jobs to see updated status
      load();
    } catch (err) {
      setExecResult({ status: 'error', output: err.message });
    } finally {
      setExecuting(false);
    }
  };

  const canExecute = task.status === 'pending' || task.status === 'failed';
  const canCancel = task.status === 'pending' || task.status === 'running';

  // Parse context for extra info
  let context = task.context_json || {};
  if (typeof context === 'string') {
    try { context = JSON.parse(context); } catch { context = {}; }
  }

  return (
    <div className="page">
      <div style={{ marginBottom: 16 }}>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/issues')}>Back to Issues</button>
      </div>

      <div className="issue-detail">
        {/* ── Main Panel ──────────────────────────── */}
        <div className="issue-detail-main">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <div className={`issue-status-dot ${task.status}`} style={{ width: 20, height: 20 }} />
            <h1 style={{ fontSize: 18, fontWeight: 700, flex: 1 }}>{task.title}</h1>
            {canExecute && (
              <button
                className="btn btn-primary"
                onClick={handleExecute}
                disabled={executing}
                style={{ flexShrink: 0 }}
              >
                {executing ? 'Running AI...' : 'Execute with AI'}
              </button>
            )}
          </div>

          {task.description && (
            <div style={{ marginBottom: 20, color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6 }}>
              {task.description}
            </div>
          )}

          {/* Phase info if part of a workflow */}
          {context.phase_name && (
            <div style={{
              marginBottom: 16, padding: '8px 12px',
              background: 'var(--accent-bg)', border: '1px solid rgba(108,92,231,0.2)',
              borderRadius: 'var(--radius)', fontSize: 12,
            }}>
              <strong>Phase {context.phase}:</strong> {context.phase_name}
              {context.original_request && (
                <div className="text-secondary" style={{ marginTop: 4 }}>
                  Original request: "{context.original_request}"
                </div>
              )}
            </div>
          )}

          {/* ── AI Result ─────────────────────────── */}
          {execResult && (
            <div style={{
              marginBottom: 20, padding: 16,
              background: execResult.status === 'success' ? 'var(--green-bg)' : 'var(--red-bg)',
              border: `1px solid ${execResult.status === 'success' ? 'rgba(81,207,102,0.3)' : 'rgba(255,107,107,0.3)'}`,
              borderRadius: 'var(--radius-lg)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{
                  fontSize: 12, fontWeight: 600,
                  color: execResult.status === 'success' ? 'var(--green)' : 'var(--red)',
                }}>
                  AI {execResult.status === 'success' ? 'Completed' : 'Failed'}
                </span>
                <div style={{ display: 'flex', gap: 8 }}>
                  {execResult.provider && (
                    <span className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      via {execResult.provider}
                    </span>
                  )}
                  {execResult.tokens_est > 0 && (
                    <span className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      ~{execResult.tokens_est} tokens
                    </span>
                  )}
                </div>
              </div>
              <div style={{
                fontSize: 13, lineHeight: 1.7, color: 'var(--text)',
                whiteSpace: 'pre-wrap', fontFamily: 'var(--font)',
                maxHeight: 500, overflowY: 'auto',
              }}>
                {execResult.output}
              </div>
            </div>
          )}

          {/* ── Previous Job Results ──────────────── */}
          {jobs.filter(j => j.output_json).map(j => {
            let output = j.output_json;
            if (typeof output === 'string') {
              try { output = JSON.parse(output); } catch { output = null; }
            }
            if (!output || !output.output) return null;
            return (
              <div key={j.id} style={{
                marginBottom: 12, padding: 14,
                background: 'var(--bg-surface2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: 600 }}>
                    Job result — {output.agent_title || j.agent_id}
                  </span>
                  <span className="mono text-dim" style={{ fontSize: 11 }}>
                    {output.provider && `via ${output.provider}`}
                    {output.tokens_est > 0 && ` ~${output.tokens_est} tok`}
                  </span>
                </div>
                <div style={{
                  fontSize: 13, lineHeight: 1.7, color: 'var(--text-secondary)',
                  whiteSpace: 'pre-wrap', maxHeight: 300, overflowY: 'auto',
                }}>
                  {output.output}
                </div>
              </div>
            );
          })}

          {/* ── Execution Trace ───────────────────── */}
          <div className="section-title mt-4">Execution Trace</div>
          <div className="trace-list">
            <div className="trace-item">
              <span className="trace-time">{task.created_at?.slice(11, 19) || '00:00:00'}</span>
              <div className="trace-dot system" />
              <div className="trace-content"><strong>Issue created</strong> — assigned to <code>{task.assigned_agent_id}</code></div>
            </div>
            {task.started_at && (
              <div className="trace-item">
                <span className="trace-time">{task.started_at?.slice(11, 19)}</span>
                <div className="trace-dot" />
                <div className="trace-content"><strong>Execution started</strong> — agent picked up the task</div>
              </div>
            )}
            {jobs.map(j => (
              <div className="trace-item" key={j.id}>
                <span className="trace-time">{j.completed_at?.slice(11, 19) || '...'}</span>
                <div className={`trace-dot ${j.status === 'success' ? 'success' : 'error'}`} />
                <div className="trace-content">
                  <strong>Job {j.status}</strong> — agent: {j.agent_id}
                  {j.cost > 0 && <span className="text-dim"> (${j.cost.toFixed(4)})</span>}
                  {j.error_message && <div style={{ color: 'var(--red)', fontSize: 12, marginTop: 4 }}>{j.error_message}</div>}
                </div>
              </div>
            ))}
            {task.completed_at && (
              <div className="trace-item">
                <span className="trace-time">{task.completed_at?.slice(11, 19)}</span>
                <div className={`trace-dot ${task.status === 'success' ? 'success' : 'error'}`} />
                <div className="trace-content"><strong>Issue {task.status}</strong></div>
              </div>
            )}
          </div>
        </div>

        {/* ── Sidebar ────────────────────────────── */}
        <div className="issue-detail-sidebar">
          <div className="issue-prop">
            <div className="issue-prop-label">Status</div>
            <div className="issue-prop-value"><span className={`badge ${task.status}`}>{task.status}</span></div>
          </div>
          <div className="issue-prop">
            <div className="issue-prop-label">Agent</div>
            <div className="issue-prop-value mono">{task.assigned_agent_id}</div>
          </div>
          <div className="issue-prop">
            <div className="issue-prop-label">Priority</div>
            <div className="issue-prop-value">{task.priority >= 3 ? 'Urgent' : task.priority === 2 ? 'Normal' : 'Low'}</div>
          </div>
          <div className="issue-prop">
            <div className="issue-prop-label">Type</div>
            <div className="issue-prop-value">{task.task_type || 'default'}</div>
          </div>
          <div className="issue-prop">
            <div className="issue-prop-label">Retries</div>
            <div className="issue-prop-value">{task.retry_count}</div>
          </div>
          <div className="issue-prop">
            <div className="issue-prop-label">Goal</div>
            <div className="issue-prop-value mono">{task.goal_id?.slice(0, 8) || 'none'}</div>
          </div>
          <div className="issue-prop">
            <div className="issue-prop-label">Created</div>
            <div className="issue-prop-value">{task.created_at?.replace('T', ' ').slice(0, 19)}</div>
          </div>
          <div className="issue-prop">
            <div className="issue-prop-label">Jobs</div>
            <div className="issue-prop-value">{jobs.length} execution(s)</div>
          </div>

          {/* Context tools */}
          {context.tools && context.tools.length > 0 && (
            <div className="issue-prop">
              <div className="issue-prop-label">Tools</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 4 }}>
                {context.tools.map(t => (
                  <span key={t} style={{
                    fontSize: 10, padding: '2px 6px', borderRadius: 3,
                    background: 'var(--bg-surface2)', color: 'var(--text-muted)',
                  }}>{t}</span>
                ))}
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div className="mt-4" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {canExecute && (
              <button
                className="btn btn-primary"
                style={{ width: '100%' }}
                onClick={handleExecute}
                disabled={executing}
              >
                {executing ? 'Running AI...' : 'Execute with AI'}
              </button>
            )}
            {canCancel && (
              <button className="btn btn-danger" style={{ width: '100%' }} onClick={handleCancel}>
                Cancel Issue
              </button>
            )}
            {task.status === 'success' && (
              <div style={{
                textAlign: 'center', padding: 8,
                background: 'var(--green-bg)', borderRadius: 'var(--radius)',
                color: 'var(--green)', fontSize: 12, fontWeight: 600,
              }}>
                Completed
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

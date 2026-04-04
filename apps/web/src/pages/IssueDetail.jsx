import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getTask, listJobs, cancelTask } from '../api';

export default function IssueDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [task, setTask] = useState(null);
  const [jobs, setJobs] = useState([]);

  useEffect(() => {
    getTask(id).then(setTask).catch(() => navigate('/issues'));
    listJobs(id).then(setJobs).catch(() => {});
  }, [id]);

  if (!task) return <div className="page"><div className="empty-state">Loading...</div></div>;

  const handleCancel = async () => {
    await cancelTask(id);
    setTask({ ...task, status: 'cancelled' });
  };

  return (
    <div className="page">
      <div style={{ marginBottom: 16 }}>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/issues')}>Back to Issues</button>
      </div>

      <div className="issue-detail">
        <div className="issue-detail-main">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <div className={`issue-status-dot ${task.status}`} style={{ width: 20, height: 20 }} />
            <h1 style={{ fontSize: 18, fontWeight: 700 }}>{task.title}</h1>
          </div>

          {task.description && (
            <div style={{ marginBottom: 20, color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6 }}>
              {task.description}
            </div>
          )}

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

          {(task.status === 'pending' || task.status === 'running') && (
            <div className="mt-4">
              <button className="btn btn-danger" style={{ width: '100%' }} onClick={handleCancel}>
                Cancel Issue
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

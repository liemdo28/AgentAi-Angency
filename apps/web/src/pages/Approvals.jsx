import React, { useState, useEffect } from 'react';
import { listApprovals, resolveApproval, listTasks } from '../api';

function formatDate(value) {
  if (!value) return '-';
  return value.replace('T', ' ').replace('Z', ' UTC').slice(0, 19);
}

export default function Approvals() {
  const [approvals, setApprovals] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [filter, setFilter] = useState('pending');
  const [resourceType, setResourceType] = useState('all');

  const load = () => {
    listApprovals(filter, resourceType === 'all' ? undefined : resourceType).then(setApprovals).catch(() => {});
    listTasks().then(setTasks).catch(() => {});
  };

  useEffect(() => { load(); }, [filter, resourceType]);

  const getTaskTitle = (taskId) => {
    const t = tasks.find(t => t.id === taskId);
    return t ? t.title : taskId?.slice(0, 8);
  };

  const handleResolve = async (id, status) => {
    await resolveApproval(id, { status, approved_by: 'board_operator' });
    load();
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>Approval Queue</h1>
        <div className="tab-bar">
          {['pending', 'approved', 'rejected', 'all'].map(s => (
            <button key={s} className={`tab-btn ${filter === s ? 'active' : ''}`} onClick={() => setFilter(s)}>
              {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
        <div className="tab-bar">
          {['all', 'task', 'department_action'].map(s => (
            <button key={s} className={`tab-btn ${resourceType === s ? 'active' : ''}`} onClick={() => setResourceType(s)}>
              {s === 'department_action' ? 'Governance' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {approvals.length === 0 && (
        <div className="empty-state" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
          <div className="empty-state-icon">~</div>
          {filter === 'all' ? 'No approvals in this view' : `No ${filter} approvals`}
        </div>
      )}

      {approvals.map(a => (
        <div className="approval-card" key={a.id}>
          <div className="approval-header">
            <div>
              <div className="approval-task">{getTaskTitle(a.task_id)}</div>
              <div className="approval-meta">
                Requested by <strong>{a.requested_by}</strong> at {formatDate(a.created_at)}
              </div>
              {a.resource_type === 'department_action' && (
                <div className="text-dim mt-2" style={{ fontSize: 12 }}>
                  {a.approval_level} approval · {a.policy_code || 'no policy'} · {a.request?.action || 'department action'}
                </div>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className={`badge ${a.status}`}>{a.status}</span>
              {a.status === 'pending' && (
                <div className="approval-actions">
                  <button className="btn btn-success btn-sm" onClick={() => handleResolve(a.id, 'approved')}>Approve</button>
                  <button className="btn btn-danger btn-sm" onClick={() => handleResolve(a.id, 'rejected')}>Reject</button>
                </div>
              )}
            </div>
          </div>
          {a.reason && <div className="text-dim mt-2" style={{ fontSize: 12 }}>Reason: {a.reason}</div>}
          {a.approved_by && a.status !== 'pending' && (
            <div className="text-dim mt-2" style={{ fontSize: 12 }}>
              {a.status === 'approved' ? 'Approved' : 'Rejected'} by {a.approved_by} at {formatDate(a.resolved_at)}
            </div>
          )}
          {a.request?.edge_command?.machine_id && (
            <div className="text-dim mt-2" style={{ fontSize: 12 }}>
              Edge target: {a.request.edge_command.project_id} · {a.request.edge_command.machine_name || a.request.edge_command.machine_id} · {a.request.edge_command.command_type}
            </div>
          )}
          {(a.decision?.task || a.decision?.edge_command || a.execution?.task || a.execution?.edge_command) && (
            <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
              <div className="text-secondary" style={{ fontSize: 11, marginBottom: 8 }}>Execution Timeline</div>
              <div className="trace-list">
                <div className="trace-item">
                  <span className="trace-time">{a.created_at?.slice(11, 19) || '--:--:--'}</span>
                  <div className="trace-dot system" />
                  <div className="trace-content">
                    <strong>Approval requested</strong>
                    <div className="text-dim" style={{ fontSize: 12 }}>{a.request?.action || a.resource_id}</div>
                  </div>
                </div>
                {a.resolved_at && (
                  <div className="trace-item">
                    <span className="trace-time">{a.resolved_at?.slice(11, 19) || '--:--:--'}</span>
                    <div className={`trace-dot ${a.status === 'approved' ? 'success' : 'error'}`} />
                    <div className="trace-content">
                      <strong>{a.status === 'approved' ? 'Approval granted' : 'Approval rejected'}</strong>
                      <div className="text-dim" style={{ fontSize: 12 }}>
                        {a.approved_by || 'system'} · {a.approval_level}
                      </div>
                    </div>
                  </div>
                )}
                {(a.execution?.task || a.decision?.task) && (
                  <div className="trace-item">
                    <span className="trace-time">{(a.execution?.executed_at || a.resolved_at || '').slice(11, 19) || '--:--:--'}</span>
                    <div className="trace-dot system" />
                    <div className="trace-content">
                      <strong>Execution task queued</strong>
                      <div className="text-dim" style={{ fontSize: 12 }}>
                        {(a.execution?.task || a.decision?.task)?.title || 'Governed action'} · status {(a.execution?.task || a.decision?.task)?.status || 'pending'}
                      </div>
                    </div>
                  </div>
                )}
                {(a.execution?.edge_command || a.decision?.edge_command) && (
                  <div className="trace-item">
                    <span className="trace-time">{(a.execution?.executed_at || a.resolved_at || '').slice(11, 19) || '--:--:--'}</span>
                    <div className="trace-dot pending" />
                    <div className="trace-content">
                      <strong>Edge command queued</strong>
                      <div className="text-dim" style={{ fontSize: 12 }}>
                        {(a.execution?.edge_command || a.decision?.edge_command)?.machine_name || (a.execution?.edge_command || a.decision?.edge_command)?.machine_id}
                        {' · '}
                        {(a.execution?.edge_command || a.decision?.edge_command)?.command_type}
                        {' · status '}
                        {(a.execution?.edge_command || a.decision?.edge_command)?.status || 'pending'}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

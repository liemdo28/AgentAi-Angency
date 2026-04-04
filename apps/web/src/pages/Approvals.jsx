import React, { useState, useEffect } from 'react';
import { listApprovals, resolveApproval, listTasks } from '../api';

export default function Approvals() {
  const [approvals, setApprovals] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [filter, setFilter] = useState('pending');

  const load = () => {
    listApprovals(filter).then(setApprovals).catch(() => {});
    listTasks().then(setTasks).catch(() => {});
  };

  useEffect(() => { load(); }, [filter]);

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
          {['pending', 'approved', 'rejected'].map(s => (
            <button key={s} className={`tab-btn ${filter === s ? 'active' : ''}`} onClick={() => setFilter(s)}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {approvals.length === 0 && (
        <div className="empty-state" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
          <div className="empty-state-icon">~</div>
          No {filter} approvals
        </div>
      )}

      {approvals.map(a => (
        <div className="approval-card" key={a.id}>
          <div className="approval-header">
            <div>
              <div className="approval-task">{getTaskTitle(a.task_id)}</div>
              <div className="approval-meta">
                Requested by <strong>{a.requested_by}</strong> at {a.created_at?.slice(0, 16).replace('T', ' ')}
              </div>
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
              {a.status === 'approved' ? 'Approved' : 'Rejected'} by {a.approved_by} at {a.resolved_at?.slice(0, 16).replace('T', ' ')}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

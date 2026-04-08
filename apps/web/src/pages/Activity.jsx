import React, { useState, useEffect } from 'react';
import { getActivity } from '../api';

export default function Activity() {
  const [jobs, setJobs] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [approvals, setApprovals] = useState([]);

  useEffect(() => {
    getActivity()
      .then((payload) => {
        setJobs(payload.jobs || []);
        setTasks(payload.tasks || []);
        setApprovals(payload.approvals || []);
      })
      .catch(() => {});
  }, []);

  // Build activity feed from tasks + approvals + jobs, sorted by time
  const feed = [
    ...tasks.map(t => ({
      type: 'task',
      time: t.created_at,
      title: `Issue created: ${t.title}`,
      detail: `Assigned to ${t.assigned_agent_id}`,
      status: t.status,
      dotType: 'system',
    })),
    ...tasks.filter(t => t.started_at).map(t => ({
      type: 'started',
      time: t.started_at,
      title: `${t.assigned_agent_id} started: ${t.title}`,
      detail: `Priority ${t.priority}`,
      status: t.status,
      dotType: '',
    })),
    ...tasks.filter(t => t.completed_at).map(t => ({
      type: 'completed',
      time: t.completed_at,
      title: `Issue ${t.status}: ${t.title}`,
      detail: `Agent: ${t.assigned_agent_id}`,
      status: t.status,
      dotType: t.status === 'success' ? 'success' : 'error',
    })),
    ...jobs.map(j => ({
      type: 'job',
      time: j.completed_at || j.started_at,
      title: `Job ${j.status} by ${j.agent_id}`,
      detail: j.cost > 0 ? `Cost: $${j.cost.toFixed(4)}` : 'No cost recorded',
      status: j.status,
      dotType: j.status === 'success' ? 'success' : 'error',
    })),
    ...approvals.map((a) => ({
      type: 'approval_requested',
      time: a.created_at,
      title: `Approval requested: ${a.request?.action || a.resource_id}`,
      detail: `${a.approval_level} · ${a.requested_by}${a.request?.edge_command?.machine_id ? ` · ${a.request.edge_command.machine_name || a.request.edge_command.machine_id}` : ''}`,
      status: a.status,
      dotType: 'pending',
    })),
    ...approvals.filter((a) => a.resolved_at).map((a) => ({
      type: 'approval_resolved',
      time: a.resolved_at,
      title: `Approval ${a.status}: ${a.request?.action || a.resource_id}`,
      detail: `${a.approved_by || 'system'} · ${a.policy_code || 'no policy'}`,
      status: a.status,
      dotType: a.status === 'approved' ? 'success' : 'error',
    })),
    ...approvals.filter((a) => (a.execution?.task || a.decision?.task)?.id).map((a) => {
      const task = a.execution?.task || a.decision?.task;
      return {
        type: 'approval_task_execution',
        time: a.execution?.executed_at || a.resolved_at,
        title: `Governance task queued: ${task?.title || a.request?.action || a.resource_id}`,
        detail: `Task status ${task?.status || 'pending'} · approval ${a.id.slice(0, 8)}`,
        status: task?.status || 'pending',
        dotType: 'system',
      };
    }),
    ...approvals.filter((a) => (a.execution?.edge_command || a.decision?.edge_command)?.id).map((a) => {
      const edgeCommand = a.execution?.edge_command || a.decision?.edge_command;
      return {
        type: 'approval_edge_execution',
        time: edgeCommand?.updated_at || edgeCommand?.created_at || a.execution?.executed_at || a.resolved_at,
        title: `Edge command ${edgeCommand?.status || 'queued'}: ${edgeCommand?.command_type}`,
        detail: `${edgeCommand?.machine_name || edgeCommand?.machine_id} · ${edgeCommand?.project_id}`,
        status: edgeCommand?.status || 'pending',
        dotType: edgeCommand?.status === 'success' ? 'success' : edgeCommand?.status === 'failed' ? 'error' : 'pending',
      };
    }),
  ].sort((a, b) => (b.time || '').localeCompare(a.time || '')).slice(0, 50);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Activity</h1>
          <div className="page-subtitle">
            A chronological operating log across tasks, jobs, approvals, and governed executions.
          </div>
        </div>
        <span className="text-secondary" style={{ fontSize: 13 }}>{feed.length} events</span>
      </div>

      <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '16px 20px' }}>
        {feed.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">~</div>
            No activity recorded yet
          </div>
        )}
        <div className="trace-list">
          {feed.map((item, i) => (
            <div className="trace-item" key={i}>
              <span className="trace-time">{item.time?.slice(11, 19) || '??:??:??'}</span>
              <div className={`trace-dot ${item.dotType}`} />
              <div className="trace-content">
                <strong>{item.title}</strong>
                <div className="text-dim" style={{ fontSize: 12, marginTop: 2 }}>{item.detail}</div>
                <div className="text-dim" style={{ fontSize: 11 }}>{item.time?.slice(0, 10)}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

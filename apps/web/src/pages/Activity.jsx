import React, { useState, useEffect } from 'react';
import { listJobs, listTasks } from '../api';

export default function Activity() {
  const [jobs, setJobs] = useState([]);
  const [tasks, setTasks] = useState([]);

  useEffect(() => {
    listJobs().then(setJobs).catch(() => {});
    listTasks().then(setTasks).catch(() => {});
  }, []);

  // Build activity feed from jobs + tasks, sorted by time
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
  ].sort((a, b) => (b.time || '').localeCompare(a.time || '')).slice(0, 50);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Activity</h1>
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

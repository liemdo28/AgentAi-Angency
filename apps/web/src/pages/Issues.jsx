import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { listTasks, createTask, cancelTask, listRuntimeAgents } from '../api';

export default function Issues() {
  const [tasks, setTasks] = useState([]);
  const [agents, setAgents] = useState([]);
  const [filter, setFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', assigned_agent_id: '', description: '', priority: 2, task_type: 'default' });
  const navigate = useNavigate();

  const load = () => {
    listTasks(filter || undefined).then(setTasks).catch(() => {});
    listRuntimeAgents().then(setAgents).catch(() => {});
  };

  useEffect(() => { load(); }, [filter]);

  const handleCreate = async (e) => {
    e.preventDefault();
    await createTask(form);
    setForm({ title: '', assigned_agent_id: '', description: '', priority: 2, task_type: 'default' });
    setShowCreate(false);
    load();
  };

  const handleCancel = async (e, id) => {
    e.stopPropagation();
    await cancelTask(id);
    load();
  };

  const running = tasks.filter(t => t.status === 'running').length;

  const priorityIcon = (p) => {
    if (p >= 3) return <span className="issue-priority p1" title="Urgent">!!!</span>;
    if (p === 2) return <span className="issue-priority p2" title="Normal">!!</span>;
    return <span className="issue-priority p3" title="Low">!</span>;
  };

  return (
    <div className="page">
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h1>Issues</h1>
          {running > 0 && <span className="badge-live">{running} live</span>}
        </div>
        <div className="page-header-actions">
          <div className="tab-bar">
            {['', 'pending', 'running', 'success', 'failed'].map(s => (
              <button key={s} className={`tab-btn ${filter === s ? 'active' : ''}`} onClick={() => setFilter(s)}>
                {s || 'All'}
              </button>
            ))}
          </div>
          <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>+ Issue</button>
        </div>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="create-panel">
          <div className="form-row">
            <div className="form-group" style={{ flex: 2 }}>
              <label>Title</label>
              <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="What needs to be done?" required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Assign Agent</label>
              <select value={form.assigned_agent_id} onChange={e => setForm({ ...form, assigned_agent_id: e.target.value })} required>
                <option value="">Select agent...</option>
                {agents.map(a => <option key={a.id} value={a.id}>{a.id}</option>)}
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group" style={{ flex: 2 }}>
              <label>Description</label>
              <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Additional context..." />
            </div>
            <div className="form-group">
              <label>Priority</label>
              <select value={form.priority} onChange={e => setForm({ ...form, priority: parseInt(e.target.value) })}>
                <option value={3}>Urgent</option>
                <option value={2}>Normal</option>
                <option value={1}>Low</option>
              </select>
            </div>
            <div className="form-group">
              <label>Type</label>
              <select value={form.task_type} onChange={e => setForm({ ...form, task_type: e.target.value })}>
                <option value="default">Default</option>
                <option value="send_email">Send Email</option>
                <option value="deploy">Deploy</option>
                <option value="research">Research</option>
                <option value="creative">Creative</option>
              </select>
            </div>
            <button type="submit" className="btn btn-primary">Create</button>
          </div>
        </form>
      )}

      <div className="issue-list">
        {tasks.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">~</div>
            No issues found
          </div>
        )}
        {tasks.map((t, i) => (
          <div className="issue-row" key={t.id} onClick={() => navigate(`/issues/${t.id}`)}>
            <div className={`issue-status-dot ${t.status}`} />
            <span className="issue-id">#{String(i + 1).padStart(4, '0')}</span>
            <span className="issue-title">{t.title}</span>
            <div className="issue-meta">
              {priorityIcon(t.priority)}
              <span className="issue-agent">{t.assigned_agent_id}</span>
              {t.retry_count > 0 && <span className="badge failed" style={{ fontSize: 10 }}>retry {t.retry_count}</span>}
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

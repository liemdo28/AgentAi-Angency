import React, { useState, useEffect } from 'react';
import { listGoals, createGoal, listTasks } from '../api';

export default function Goals() {
  const [goals, setGoals] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', owner: '' });

  const load = () => {
    listGoals().then(setGoals).catch(() => {});
    listTasks().then(setTasks).catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    await createGoal(form);
    setForm({ title: '', description: '', owner: '' });
    setShowCreate(false);
    load();
  };

  // Build goal cascade: goal -> tasks under that goal
  const goalTree = goals.map(g => {
    const goalTasks = tasks.filter(t => t.goal_id === g.id);
    const done = goalTasks.filter(t => t.status === 'success').length;
    const total = goalTasks.length;
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    return { ...g, tasks: goalTasks, done, total, pct };
  });

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Goals</h1>
          <div className="page-subtitle">
            Keep company objectives, owners, and execution progress visible in one compact planning stack.
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>+ Goal</button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="create-panel">
          <div className="form-row">
            <div className="form-group" style={{ flex: 2 }}>
              <label>Title</label>
              <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Company objective..." required />
            </div>
            <div className="form-group">
              <label>Owner</label>
              <input value={form.owner} onChange={e => setForm({ ...form, owner: e.target.value })} placeholder="Agent or person" />
            </div>
            <button type="submit" className="btn btn-primary">Create</button>
          </div>
          <div className="form-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Description</label>
              <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="What does success look like?" rows={2} style={{ width: '100%' }} />
            </div>
          </div>
        </form>
      )}

      <div className="goal-cascade">
        {goalTree.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">~</div>
            No goals yet. Create your first company objective.
          </div>
        )}
        {goalTree.map(g => (
          <React.Fragment key={g.id}>
            {/* Goal level */}
            <div className="goal-item">
              <div className="goal-icon mission">M</div>
              <span className="goal-title" style={{ fontWeight: 600 }}>{g.title}</span>
              {g.owner && <span className="text-dim" style={{ fontSize: 12 }}>{g.owner}</span>}
              <div className="goal-progress">
                <div className="goal-progress-fill" style={{ width: `${g.pct}%` }} />
              </div>
              <span className="goal-pct">{g.pct}%</span>
            </div>

            {/* Description sub-item */}
            {g.description && (
              <div className="goal-item" style={{ paddingLeft: 40, opacity: 0.7 }}>
                <div className="goal-indent" />
                <div className="goal-icon project">P</div>
                <span className="goal-title text-secondary">{g.description}</span>
              </div>
            )}

            {/* Task sub-items */}
            {g.tasks.map(t => (
              <div className="goal-item" key={t.id} style={{ paddingLeft: 64 }}>
                <div className="goal-indent" />
                <div className="goal-indent" />
                <div className={`issue-status-dot ${t.status}`} style={{ width: 14, height: 14 }} />
                <span className="goal-title">{t.title}</span>
                <span className="issue-agent">{t.assigned_agent_id}</span>
                <span className={`badge ${t.status}`}>{t.status}</span>
              </div>
            ))}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

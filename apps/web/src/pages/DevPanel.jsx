import React, { useState, useEffect } from 'react';
import { listProjects, createTask, executeTask } from '../api';

const ACTIONS = [
  { key: 'review_code', label: 'Review Code', hasInput: false },
  { key: 'analyze_structure', label: 'Analyze Structure', hasInput: false },
  { key: 'git_status', label: 'Check Git Status', hasInput: false },
  { key: 'deploy', label: 'Deploy Check', hasInput: false },
  { key: 'fix_bug', label: 'Fix Bug', hasInput: true, placeholder: 'Describe the bug...' },
  { key: 'write_code', label: 'Write Code', hasInput: true, placeholder: 'Describe the feature...' },
];

export default function DevPanel() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState('');
  const [actionKey, setActionKey] = useState(ACTIONS[0].key);
  const [description, setDescription] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    listProjects()
      .then((data) => {
        const list = Array.isArray(data) ? data : data?.projects || [];
        setProjects(list);
        if (list.length > 0) setProjectId(String(list[0].id));
      })
      .catch(() => {});
  }, []);

  const selectedAction = ACTIONS.find(a => a.key === actionKey);

  const handleRun = async () => {
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      const action = ACTIONS.find(a => a.key === actionKey);
      const task = await createTask({
        title: `[Dev Agent] ${action.label} for ${projectId}`,
        assigned_agent_id: 'dev-agent',
        description: description || action.label,
        context_json: { action: actionKey, project_id: projectId },
      });
      const execResult = await executeTask(task.id);
      setResult(execResult);
    } catch (e) {
      setError(e.message || 'Execution failed');
    }
    setRunning(false);
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>Dev Agent</h1>
        <span className="text-secondary" style={{ fontSize: 13 }}>
          Run dev operations on your projects
        </span>
      </div>

      <div className="org-card" style={{ padding: 24, marginBottom: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              Project
            </label>
            <select
              value={projectId}
              onChange={e => setProjectId(e.target.value)}
              style={{
                width: '100%', padding: '8px 12px', borderRadius: 8,
                border: '1px solid var(--border)', background: 'var(--bg-card)',
                color: 'var(--text-primary)', fontSize: 13,
              }}
            >
              {projects.length === 0 && <option value="">Loading projects...</option>}
              {projects.map(p => (
                <option key={p.id} value={p.id}>{p.name || p.id}</option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              Action
            </label>
            <select
              value={actionKey}
              onChange={e => { setActionKey(e.target.value); setDescription(''); }}
              style={{
                width: '100%', padding: '8px 12px', borderRadius: 8,
                border: '1px solid var(--border)', background: 'var(--bg-card)',
                color: 'var(--text-primary)', fontSize: 13,
              }}
            >
              {ACTIONS.map(a => (
                <option key={a.key} value={a.key}>{a.label}</option>
              ))}
            </select>
          </div>
        </div>

        {selectedAction?.hasInput && (
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              Description
            </label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder={selectedAction.placeholder}
              rows={4}
              style={{
                width: '100%', padding: '8px 12px', borderRadius: 8,
                border: '1px solid var(--border)', background: 'var(--bg-card)',
                color: 'var(--text-primary)', fontSize: 13, resize: 'vertical',
                fontFamily: 'inherit',
              }}
            />
          </div>
        )}

        <button
          className="btn btn-primary"
          onClick={handleRun}
          disabled={running || !projectId}
        >
          {running ? 'Running...' : 'Run'}
        </button>
      </div>

      {error && (
        <div className="org-card" style={{ padding: 18, borderLeft: '3px solid #ef4444' }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: '#ef4444', marginBottom: 4 }}>Error</div>
          <div style={{ fontSize: 13 }}>{error}</div>
        </div>
      )}

      {result && (
        <div className="org-card" style={{ padding: 18, marginTop: 12 }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8, color: 'var(--text-secondary)' }}>Result</div>
          <pre style={{
            whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 13,
            lineHeight: 1.6, margin: 0, fontFamily: 'monospace',
            background: 'var(--bg-main)', padding: 14, borderRadius: 8,
            maxHeight: 500, overflow: 'auto',
          }}>
            {typeof result === 'string' ? result : JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { getStats, listRuntimeAgents } from '../api';
import { useTheme } from '../App';

const ACCENT_SWATCHES = [
  { color: '#6c5ce7', label: 'Purple' },
  { color: '#4dabf7', label: 'Blue' },
  { color: '#22b8cf', label: 'Teal' },
  { color: '#51cf66', label: 'Green' },
  { color: '#ff922b', label: 'Orange' },
  { color: '#ff6b6b', label: 'Red' },
  { color: '#e64980', label: 'Pink' },
  { color: '#5c7cfa', label: 'Indigo' },
];

export default function Settings() {
  const [stats, setStats] = useState(null);
  const [agents, setAgents] = useState([]);
  const { theme, setTheme, accent, setAccent } = useTheme();

  useEffect(() => {
    getStats().then(setStats).catch(() => {});
    listRuntimeAgents().then(setAgents).catch(() => {});
  }, []);

  const resetDefaults = () => {
    setTheme('dark');
    setAccent('#6c5ce7');
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <div className="page-subtitle">
            Configure the visual system, runtime defaults, and infrastructure facts behind the control plane.
          </div>
        </div>
      </div>

      <div className="settings-grid">
        {/* Appearance card - first in grid, spans full width */}
        <div className="settings-card" style={{ gridColumn: '1 / -1' }}>
          <h3>Appearance</h3>

          {/* Theme toggle */}
          <div className="settings-item">
            <span className="settings-key">Theme</span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                className={`btn btn-sm ${theme === 'dark' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setTheme('dark')}
              >
                Dark
              </button>
              <button
                className={`btn btn-sm ${theme === 'light' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setTheme('light')}
              >
                Light
              </button>
            </div>
          </div>

          {/* Accent color swatches */}
          <div className="settings-item">
            <span className="settings-key">Accent Color</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {ACCENT_SWATCHES.map(s => (
                <button
                  key={s.color}
                  className={`accent-dot ${accent === s.color ? 'selected' : ''}`}
                  style={{ background: s.color }}
                  title={s.label}
                  onClick={() => setAccent(s.color)}
                >
                  {accent === s.color && (
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M4 8l3 3 5-6" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Reset */}
          <div style={{ marginTop: 12 }}>
            <button className="btn btn-ghost btn-sm" onClick={resetDefaults}>
              Reset to defaults
            </button>
          </div>
        </div>

        <div className="settings-card">
          <h3>Orchestrator</h3>
          <div className="settings-item">
            <span className="settings-key">Cycle Interval</span>
            <span className="settings-val">10s</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Max Concurrent</span>
            <span className="settings-val">5</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Stale Task Threshold</span>
            <span className="settings-val">48h</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Status</span>
            <span className="badge active">Running</span>
          </div>
        </div>

        <div className="settings-card">
          <h3>Policy Engine</h3>
          <div className="settings-item">
            <span className="settings-key">Default Budget Limit</span>
            <span className="settings-val">$50.00</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Max Retries</span>
            <span className="settings-val">3</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Approval Required For</span>
            <span className="settings-val">send_email, deploy, budget_change, client_communication</span>
          </div>
        </div>

        <div className="settings-card">
          <h3>Database</h3>
          <div className="settings-item">
            <span className="settings-key">Engine</span>
            <span className="settings-val">SQLite WAL</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Path</span>
            <span className="settings-val">data/agency.db</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Total Jobs</span>
            <span className="settings-val">{stats?.jobs ?? '...'}</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Total Goals</span>
            <span className="settings-val">{stats?.goals ?? '...'}</span>
          </div>
        </div>

        <div className="settings-card">
          <h3>Agents</h3>
          <div className="settings-item">
            <span className="settings-key">Runtime Agents</span>
            <span className="settings-val">{agents.length}</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Departments</span>
            <span className="settings-val">{agents.filter(a => a.type === 'DepartmentAgent').length}</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Connectors</span>
            <span className="settings-val">{agents.filter(a => a.id.startsWith('connector-')).length}</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Workflow</span>
            <span className="settings-val">{agents.filter(a => a.type === 'WorkflowAgent').length}</span>
          </div>
        </div>

        <div className="settings-card">
          <h3>API Endpoints</h3>
          <div className="settings-item">
            <span className="settings-key">Agency API</span>
            <span className="settings-val">:8000</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Control Plane API</span>
            <span className="settings-val">:8002</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Dashboard</span>
            <span className="settings-val">:3000</span>
          </div>
        </div>

        <div className="settings-card">
          <h3>Escalation</h3>
          <div className="settings-item">
            <span className="settings-key">Auto-escalate After</span>
            <span className="settings-val">48h</span>
          </div>
          <div className="settings-item">
            <span className="settings-key">Notify Roles</span>
            <span className="settings-val">ceo, operations_leader</span>
          </div>
        </div>
      </div>
    </div>
  );
}

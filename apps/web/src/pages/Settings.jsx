import React, { useState, useEffect } from 'react';
import { getStats, listRuntimeAgents } from '../api';

export default function Settings() {
  const [stats, setStats] = useState(null);
  const [agents, setAgents] = useState([]);

  useEffect(() => {
    getStats().then(setStats).catch(() => {});
    listRuntimeAgents().then(setAgents).catch(() => {});
  }, []);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      <div className="settings-grid">
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
          <div className="settings-item">
            <span className="settings-key">Existing Dashboard</span>
            <span className="settings-val">:8080</span>
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

import React, { useState, useEffect } from 'react';
import { listRuntimeAgents, listAgents, getStats } from '../api';

export default function Costs() {
  const [rtAgents, setRtAgents] = useState([]);
  const [dbAgents, setDbAgents] = useState([]);
  const [stats, setStats] = useState(null);
  const [period, setPeriod] = useState('mtd');

  useEffect(() => {
    listRuntimeAgents().then(setRtAgents).catch(() => {});
    listAgents().then(setDbAgents).catch(() => {});
    getStats().then(setStats).catch(() => {});
  }, []);

  // Merge runtime agents with DB cost data
  const agentCosts = rtAgents.map(ra => {
    const dbEntry = dbAgents.find(da => da.id === ra.id) || {};
    const budget = dbEntry.budget_limit || 50;
    const used = dbEntry.total_cost || 0;
    const pct = budget > 0 ? (used / budget) * 100 : 0;
    return { ...ra, budget, used, pct };
  });

  const totalBudget = agentCosts.reduce((s, a) => s + a.budget, 0);
  const totalUsed = agentCosts.reduce((s, a) => s + a.used, 0);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Costs</h1>
          <div className="page-subtitle">
            Compare budget allocation, actual spend, and remaining runway across the full runtime roster.
          </div>
        </div>
        <div className="tab-bar">
          {[['mtd', 'Month to Date'], ['7d', 'Last 7 Days'], ['30d', 'Last 30 Days']].map(([k, l]) => (
            <button key={k} className={`tab-btn ${period === k ? 'active' : ''}`} onClick={() => setPeriod(k)}>{l}</button>
          ))}
        </div>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-label">Total Budget</div>
          <div className="stat-value">${totalBudget.toFixed(2)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Spend</div>
          <div className="stat-value yellow">${totalUsed.toFixed(2)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Remaining</div>
          <div className="stat-value green">${(totalBudget - totalUsed).toFixed(2)}</div>
        </div>
      </div>

      <div className="cost-table">
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Type</th>
              <th>Budget</th>
              <th>Used</th>
              <th>Usage</th>
              <th>Remaining</th>
            </tr>
          </thead>
          <tbody>
            {agentCosts.map(a => (
              <tr key={a.id}>
                <td>
                  <div style={{ fontWeight: 500 }}>{a.id}</div>
                  <div className="text-dim" style={{ fontSize: 11 }}>{a.description}</div>
                </td>
                <td><span className="badge active">{a.type}</span></td>
                <td className="cost-amount">${a.budget.toFixed(2)}</td>
                <td className="cost-amount">${a.used.toFixed(2)}</td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div className="budget-bar">
                      <div
                        className={`budget-bar-fill ${a.pct > 80 ? 'high' : a.pct > 50 ? 'medium' : 'low'}`}
                        style={{ width: `${Math.min(a.pct, 100)}%` }}
                      />
                    </div>
                    <span className="mono text-dim">{a.pct.toFixed(0)}%</span>
                  </div>
                </td>
                <td className="cost-amount">${(a.budget - a.used).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

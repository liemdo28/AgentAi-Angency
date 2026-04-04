import React, { useState, useEffect } from 'react';
import { listRuntimeAgents, listTasks } from '../api';

// Map agent IDs to org structure
const ORG_LEVELS = [
  { level: 'C-Suite', filter: id => id === 'workflow' },
  { level: 'Directors', filter: id => ['dept-account', 'dept-strategy', 'dept-finance', 'dept-operations'].includes(id) },
  { level: 'Department Heads', filter: id => ['dept-creative', 'dept-media', 'dept-data', 'dept-tech', 'dept-production'].includes(id) },
  { level: 'Specialists', filter: id => ['dept-sales', 'dept-crm_automation', 'connector-marketing', 'connector-review', 'connector-taskflow'].includes(id) },
];

const ROLE_NAMES = {
  'workflow': 'CEO Agent',
  'dept-account': 'Account Director',
  'dept-strategy': 'Strategy Director',
  'dept-finance': 'CFO Agent',
  'dept-operations': 'COO Agent',
  'dept-creative': 'Creative Lead',
  'dept-media': 'Media Lead',
  'dept-data': 'Data Lead',
  'dept-tech': 'CTO Agent',
  'dept-production': 'Production Lead',
  'dept-sales': 'Sales Specialist',
  'dept-crm_automation': 'CRM Specialist',
  'connector-marketing': 'Marketing Ops',
  'connector-review': 'Review Ops',
  'connector-taskflow': 'TaskFlow Ops',
};

export default function OrgChart() {
  const [agents, setAgents] = useState([]);
  const [tasks, setTasks] = useState([]);

  useEffect(() => {
    listRuntimeAgents().then(setAgents).catch(() => {});
    listTasks().then(setTasks).catch(() => {});
  }, []);

  const getTaskCount = (agentId) => tasks.filter(t => t.assigned_agent_id === agentId && t.status !== 'cancelled').length;
  const isActive = (agentId) => tasks.some(t => t.assigned_agent_id === agentId && t.status === 'running');

  return (
    <div className="page">
      <div className="page-header">
        <h1>Org Chart</h1>
        <span className="text-secondary" style={{ fontSize: 13 }}>{agents.length} agents deployed</span>
      </div>

      <div className="org-chart">
        {ORG_LEVELS.map((level, li) => {
          const levelAgents = agents.filter(a => level.filter(a.id));
          if (levelAgents.length === 0) return null;

          return (
            <React.Fragment key={level.level}>
              {li > 0 && <div className="org-connector" />}
              <div className="section-title" style={{ textAlign: 'center' }}>{level.level}</div>
              <div className="org-level">
                {levelAgents.map(a => (
                  <div className={`org-card ${a.id === 'workflow' ? 'ceo' : ''}`} key={a.id}>
                    <div className="org-avatar">
                      {(ROLE_NAMES[a.id] || a.id).slice(0, 2).toUpperCase()}
                    </div>
                    <div className="org-name">{ROLE_NAMES[a.id] || a.id}</div>
                    <div className="org-role">{a.type}</div>
                    <div className="org-issues">
                      <span className={`org-status-dot ${isActive(a.id) ? 'active' : 'idle'}`} />
                      {getTaskCount(a.id)} issues
                    </div>
                  </div>
                ))}
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

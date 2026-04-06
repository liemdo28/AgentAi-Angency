import React, { useState, useEffect } from 'react';
import { listRuntimeAgents, listTasks } from '../api';

const LEVEL_ORDER = ['c-suite', 'director', 'head', 'specialist'];
const LEVEL_LABELS = {
  'c-suite': 'C-Suite',
  'director': 'Directors',
  'head': 'Department Heads',
  'specialist': 'Specialists',
};

function getModelBadgeClass(model) {
  if (!model) return '';
  const m = model.toLowerCase();
  if (m.includes('sonnet')) return 'sonnet';
  if (m.includes('haiku')) return 'haiku';
  if (m.includes('opus')) return 'opus';
  if (m.includes('gpt')) return 'gpt';
  return 'haiku'; // fallback
}

function getModelLabel(model) {
  if (!model) return '?';
  const m = model.toLowerCase();
  if (m.includes('sonnet')) return 'sonnet';
  if (m.includes('haiku')) return 'haiku';
  if (m.includes('opus')) return 'opus';
  if (m.includes('gpt-4')) return 'gpt-4';
  if (m.includes('gpt')) return 'gpt';
  // Return last meaningful segment
  const parts = model.split(/[-/]/);
  return parts[parts.length - 1] || model;
}

export default function OrgChart() {
  const [agents, setAgents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [expandedId, setExpandedId] = useState(null);

  useEffect(() => {
    listRuntimeAgents().then(setAgents).catch(() => {});
    listTasks().then(setTasks).catch(() => {});
  }, []);

  const getTaskCount = (agentId) => tasks.filter(t => t.assigned_agent_id === agentId && t.status !== 'cancelled').length;
  const isActive = (agentId) => tasks.some(t => t.assigned_agent_id === agentId && t.status === 'running');

  // Group agents by level field from API; fall back to old heuristic
  const grouped = {};
  agents.forEach(a => {
    const level = a.level || inferLevel(a);
    if (!grouped[level]) grouped[level] = [];
    grouped[level].push(a);
  });

  // Sort levels by known order, unknown levels go at the end
  const sortedLevels = Object.keys(grouped).sort((a, b) => {
    const ai = LEVEL_ORDER.indexOf(a);
    const bi = LEVEL_ORDER.indexOf(b);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  return (
    <div className="page">
      <div className="page-header">
        <h1>Org Chart</h1>
        <span className="text-secondary" style={{ fontSize: 13 }}>{agents.length} agents deployed</span>
      </div>

      <div className="org-chart">
        {sortedLevels.map((level, li) => {
          const levelAgents = grouped[level];
          if (!levelAgents || levelAgents.length === 0) return null;

          return (
            <React.Fragment key={level}>
              {li > 0 && <div className="org-connector" />}
              <div className="section-title" style={{ textAlign: 'center' }}>
                {LEVEL_LABELS[level] || level}
              </div>
              <div className="org-level">
                {levelAgents.map(a => {
                  const title = a.title || a.id;
                  const expanded = expandedId === a.id;
                  const toolCount = a.tools?.length ?? 0;

                  return (
                    <div
                      className={`org-card ${level === 'c-suite' ? 'ceo' : ''}`}
                      key={a.id}
                      onClick={() => setExpandedId(expanded ? null : a.id)}
                      style={{ minWidth: expanded ? 260 : 180 }}
                    >
                      <div className="org-avatar">
                        {title.slice(0, 2).toUpperCase()}
                      </div>
                      <div className="org-name">{title}</div>
                      <div className="org-role">{a.type}</div>

                      {/* Model badge + tool count */}
                      <div style={{ marginTop: 6, display: 'flex', justifyContent: 'center', gap: 6, flexWrap: 'wrap' }}>
                        {a.model && (
                          <span className={`model-badge ${getModelBadgeClass(a.model)}`}>
                            {getModelLabel(a.model)}
                          </span>
                        )}
                        {toolCount > 0 && (
                          <span style={{
                            fontSize: 10, padding: '1px 7px', borderRadius: 4,
                            background: 'var(--bg-surface2)', color: 'var(--text-muted)',
                            fontFamily: 'var(--mono)',
                          }}>
                            {toolCount} tools
                          </span>
                        )}
                      </div>

                      <div className="org-issues">
                        <span className={`org-status-dot ${isActive(a.id) ? 'active' : 'idle'}`} />
                        {getTaskCount(a.id)} issues
                      </div>

                      {/* Expanded detail */}
                      {expanded && (
                        <div style={{ marginTop: 12, textAlign: 'left', borderTop: '1px solid var(--border)', paddingTop: 10 }}>
                          {a.responsibilities && a.responsibilities.length > 0 && (
                            <div style={{ marginBottom: 8 }}>
                              <div style={{ fontSize: 10, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4, letterSpacing: '0.04em', fontWeight: 600 }}>
                                Responsibilities
                              </div>
                              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                {a.responsibilities.map((r, i) => <li key={i}>{r}</li>)}
                              </ul>
                            </div>
                          )}
                          {a.kpis && a.kpis.length > 0 && (
                            <div>
                              <div style={{ fontSize: 10, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4, letterSpacing: '0.04em', fontWeight: 600 }}>
                                KPIs
                              </div>
                              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                {a.kpis.map((k, i) => <li key={i}>{k}</li>)}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

// Fallback heuristic when the API does not return a level field
function inferLevel(agent) {
  const id = agent.id || '';
  if (id === 'workflow') return 'c-suite';
  if (['dept-account', 'dept-strategy', 'dept-finance', 'dept-operations'].includes(id)) return 'director';
  if (id.startsWith('dept-')) return 'head';
  return 'specialist';
}

import React, { useState, useEffect } from 'react';
import { listRuntimeAgents } from '../api';

const SCHEDULES = {
  'workflow':            [{ start: 0, end: 24, label: 'Always On', type: 'always' }],
  'dept-account':        [{ start: 9, end: 12, label: 'Morning review' }, { start: 14, end: 17, label: 'Client updates' }],
  'dept-strategy':       [{ start: 10, end: 13, label: 'Strategy session' }],
  'dept-creative':       [{ start: 10, end: 15, label: 'Content creation' }],
  'dept-media':          [{ start: 8, end: 10, label: 'Campaign check' }, { start: 16, end: 18, label: 'Report gen' }],
  'dept-data':           [{ start: 6, end: 8, label: 'Data sync' }, { start: 12, end: 14, label: 'Analysis' }, { start: 20, end: 22, label: 'Nightly ETL' }],
  'dept-finance':        [{ start: 9, end: 11, label: 'Cost review' }, { start: 17, end: 18, label: 'Daily close' }],
  'dept-operations':     [{ start: 7, end: 9, label: 'Health check' }, { start: 18, end: 20, label: 'SLA review' }],
  'dept-tech':           [{ start: 2, end: 4, label: 'Backup' }, { start: 11, end: 13, label: 'Deploy window' }, { start: 22, end: 23, label: 'Monitor' }],
  'dept-production':     [{ start: 13, end: 16, label: 'Asset production' }],
  'dept-sales':          [{ start: 9, end: 11, label: 'Lead scoring' }, { start: 15, end: 17, label: 'Outreach' }],
  'dept-crm_automation': [{ start: 8, end: 9, label: 'Email send' }, { start: 20, end: 21, label: 'Drip check' }],
  'connector-marketing': [{ start: 7, end: 9, label: 'Social posting' }, { start: 19, end: 21, label: 'Perf sync' }],
  'connector-review':    [{ start: 10, end: 12, label: 'Review monitor' }, { start: 22, end: 23, label: 'Digest' }],
  'connector-taskflow':  [{ start: 8, end: 9, label: 'Task sync' }, { start: 17, end: 18, label: 'Status update' }],
  'dev-agent':           [{ start: 1, end: 3, label: 'CI check' }, { start: 14, end: 16, label: 'Code review' }],
};

const LEVEL_COLORS = {
  'c-suite':    { bg: 'rgba(108,92,231,0.25)', border: 'rgba(108,92,231,0.5)', text: '#a78bfa' },
  'director':   { bg: 'rgba(77,171,247,0.2)', border: 'rgba(77,171,247,0.45)', text: '#4dabf7' },
  'head':       { bg: 'rgba(81,207,102,0.2)', border: 'rgba(81,207,102,0.45)', text: '#51cf66' },
  'specialist': { bg: 'rgba(255,146,43,0.2)', border: 'rgba(255,146,43,0.4)', text: '#ff922b' },
};

const HOURS = Array.from({ length: 24 }, (_, i) => i);

export default function Routines() {
  const [agents, setAgents] = useState([]);
  const currentHour = new Date().getHours();
  const currentMin = new Date().getMinutes();
  const nowPct = ((currentHour + currentMin / 60) / 24) * 100;

  useEffect(() => {
    listRuntimeAgents().then(setAgents).catch(() => {});
  }, []);

  const scheduledAgents = agents.filter(a => SCHEDULES[a.id]);

  // Group by level
  const groups = {};
  scheduledAgents.forEach(a => {
    const level = a.level || 'specialist';
    if (!groups[level]) groups[level] = [];
    groups[level].push(a);
  });

  const levelOrder = ['c-suite', 'director', 'head', 'specialist'];
  const levelLabels = { 'c-suite': 'C-Suite', 'director': 'Directors', 'head': 'Dept Heads', 'specialist': 'Specialists' };

  const activeNow = scheduledAgents.filter(a => {
    const blocks = SCHEDULES[a.id] || [];
    return blocks.some(b => currentHour >= b.start && currentHour < b.end);
  });

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <h1>Routines</h1>
            {activeNow.length > 0 && <span className="badge-live">{activeNow.length} active now</span>}
          </div>
          <div className="page-subtitle">
            Understand when automated work is supposed to happen and who is active at the current hour.
          </div>
        </div>
        <span className="badge active" style={{ fontSize: 12 }}>Beta</span>
      </div>

      {/* Stats */}
      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-label">Scheduled Agents</div>
          <div className="stat-value accent">{scheduledAgents.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Active Now</div>
          <div className="stat-value green">{activeNow.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Routines</div>
          <div className="stat-value">{Object.values(SCHEDULES).flat().length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Current Hour</div>
          <div className="stat-value blue">{currentHour}:00</div>
        </div>
      </div>

      {/* Timeline */}
      <div className="heartbeat">
        {/* Hour header */}
        <div className="heartbeat-header">
          {HOURS.map(h => (
            <span className="heartbeat-hour" key={h} style={
              h === currentHour
                ? { color: 'var(--accent)', fontWeight: 700, fontSize: 11 }
                : h % 6 === 0 ? { fontWeight: 600, color: 'var(--text-secondary)' } : {}
            }>
              {h}h
            </span>
          ))}
        </div>

        {/* Grouped lanes */}
        {levelOrder.map(level => {
          const levelAgents = groups[level];
          if (!levelAgents || levelAgents.length === 0) return null;
          const lc = LEVEL_COLORS[level] || LEVEL_COLORS.specialist;

          return (
            <div key={level}>
              {/* Level divider */}
              <div style={{
                padding: '8px 0 4px',
                fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                letterSpacing: '0.06em', color: lc.text, opacity: 0.8,
              }}>
                {levelLabels[level] || level}
              </div>

              {levelAgents.map(a => {
                const blocks = SCHEDULES[a.id] || [];
                const title = a.title || a.id.replace('dept-', '').replace('connector-', '');
                const isAnyActive = blocks.some(b => currentHour >= b.start && currentHour < b.end);

                return (
                  <div className="heartbeat-lane" key={a.id} style={{ padding: '5px 0' }}>
                    {/* Agent label */}
                    <div className="heartbeat-agent-label" title={`${a.title} (${a.id})`} style={{
                      display: 'flex', alignItems: 'center', gap: 6, width: 140,
                    }}>
                      <span style={{
                        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                        background: isAnyActive ? 'var(--green)' : 'var(--text-muted)',
                        boxShadow: isAnyActive ? '0 0 6px rgba(81,207,102,0.5)' : 'none',
                      }} />
                      <span style={{
                        fontSize: 12, fontWeight: isAnyActive ? 600 : 400,
                        color: isAnyActive ? 'var(--text)' : 'var(--text-secondary)',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {title}
                      </span>
                    </div>

                    {/* Track */}
                    <div className="heartbeat-track" style={{ height: 32, marginLeft: 4 }}>
                      {/* Now line */}
                      <div style={{
                        position: 'absolute', left: `${nowPct}%`,
                        top: -2, bottom: -2, width: 2,
                        background: 'var(--accent)', borderRadius: 1,
                        zIndex: 3, opacity: 0.6,
                      }} />

                      {/* Hour grid lines */}
                      {[6, 12, 18].map(h => (
                        <div key={h} style={{
                          position: 'absolute', left: `${(h / 24) * 100}%`,
                          top: 0, bottom: 0, width: 1,
                          background: 'var(--border)', opacity: 0.4,
                        }} />
                      ))}

                      {/* Blocks */}
                      {blocks.map((b, bi) => {
                        const left = (b.start / 24) * 100;
                        const width = ((b.end - b.start) / 24) * 100;
                        const isNow = currentHour >= b.start && currentHour < b.end;

                        return (
                          <div
                            key={bi}
                            title={`${b.label} (${b.start}:00 - ${b.end}:00)`}
                            style={{
                              position: 'absolute', left: `${left}%`, width: `${width}%`,
                              top: 3, bottom: 3, borderRadius: 5,
                              background: isNow ? lc.bg.replace(/[\d.]+\)$/, '0.4)') : lc.bg,
                              border: `1.5px solid ${isNow ? lc.text : lc.border}`,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              fontSize: 10, fontWeight: isNow ? 600 : 500,
                              color: isNow ? lc.text : `color-mix(in srgb, ${lc.text} 70%, var(--text-muted))`,
                              whiteSpace: 'nowrap', overflow: 'hidden', padding: '0 6px',
                              boxShadow: isNow ? `0 0 8px ${lc.bg}` : 'none',
                              transition: 'all 0.2s',
                            }}
                          >
                            {width > 5 ? b.label : ''}
                          </div>
                        );
                      })}

                      {/* Active pulse dot */}
                      {isAnyActive && (
                        <div style={{
                          position: 'absolute', left: `${nowPct}%`, top: '50%',
                          transform: 'translate(-50%, -50%)', width: 8, height: 8,
                          borderRadius: '50%', background: lc.text, zIndex: 4,
                          boxShadow: `0 0 8px ${lc.text}`,
                          animation: 'pulse 2s infinite',
                        }} />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}

        {scheduledAgents.length === 0 && (
          <div className="empty-state">No scheduled routines configured</div>
        )}
      </div>

      {/* Active now list */}
      {activeNow.length > 0 && (
        <div className="mt-4">
          <div className="section-title">Active Right Now</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
            {activeNow.map(a => {
              const blocks = SCHEDULES[a.id] || [];
              const active = blocks.find(b => currentHour >= b.start && currentHour < b.end);
              const lc = LEVEL_COLORS[a.level || 'specialist'] || LEVEL_COLORS.specialist;
              return (
                <div key={a.id} style={{
                  padding: '10px 14px', borderRadius: 'var(--radius)',
                  background: lc.bg, border: `1px solid ${lc.border}`,
                  display: 'flex', alignItems: 'center', gap: 10,
                }}>
                  <span style={{
                    width: 10, height: 10, borderRadius: '50%', background: lc.text,
                    boxShadow: `0 0 8px ${lc.text}`, animation: 'pulse 2s infinite',
                  }} />
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: lc.text }}>{a.title || a.id}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{active?.label || 'Active'}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

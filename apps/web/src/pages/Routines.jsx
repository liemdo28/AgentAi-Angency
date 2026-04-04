import React, { useState, useEffect } from 'react';
import { listRuntimeAgents } from '../api';

// Simulated schedule data (in production this comes from the DB)
const SCHEDULES = {
  'workflow': [
    { start: 0, end: 24, label: 'Always On', active: true },
  ],
  'dept-account': [
    { start: 9, end: 12, label: 'Morning review' },
    { start: 14, end: 17, label: 'Client updates' },
  ],
  'dept-creative': [
    { start: 10, end: 15, label: 'Content creation' },
  ],
  'dept-media': [
    { start: 8, end: 10, label: 'Campaign check' },
    { start: 16, end: 18, label: 'Report generation' },
  ],
  'dept-data': [
    { start: 6, end: 8, label: 'Data sync' },
    { start: 12, end: 14, label: 'Analysis' },
    { start: 20, end: 22, label: 'Nightly ETL' },
  ],
  'dept-sales': [
    { start: 9, end: 11, label: 'Lead scoring' },
    { start: 15, end: 17, label: 'Outreach' },
  ],
  'connector-marketing': [
    { start: 7, end: 9, label: 'Social posting' },
    { start: 19, end: 21, label: 'Performance sync' },
  ],
  'connector-review': [
    { start: 10, end: 12, label: 'Review monitoring' },
    { start: 22, end: 23, label: 'Digest' },
  ],
};

const HOURS = Array.from({ length: 24 }, (_, i) => i);

export default function Routines() {
  const [agents, setAgents] = useState([]);
  const currentHour = new Date().getHours();

  useEffect(() => {
    listRuntimeAgents().then(setAgents).catch(() => {});
  }, []);

  const scheduledAgents = agents.filter(a => SCHEDULES[a.id]);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Routines</h1>
        <span className="badge active" style={{ fontSize: 12 }}>Beta</span>
      </div>

      <p className="text-secondary mb-4" style={{ fontSize: 13 }}>
        Heartbeat timeline showing when scheduled agents activate throughout the day.
      </p>

      <div className="heartbeat">
        <div className="heartbeat-header">
          {HOURS.map(h => (
            <span className="heartbeat-hour" key={h} style={h === currentHour ? { color: 'var(--accent)', fontWeight: 700 } : {}}>
              {h}h
            </span>
          ))}
        </div>

        {scheduledAgents.map(a => {
          const blocks = SCHEDULES[a.id] || [];
          return (
            <div className="heartbeat-lane" key={a.id}>
              <div className="heartbeat-agent-label" title={a.id}>{a.id.replace('dept-', '').replace('connector-', '')}</div>
              <div className="heartbeat-track">
                {/* Current time indicator */}
                <div style={{
                  position: 'absolute',
                  left: `${(currentHour / 24) * 100}%`,
                  top: 0, bottom: 0, width: 1,
                  background: 'var(--accent)',
                  opacity: 0.4,
                  zIndex: 2,
                }} />

                {blocks.map((b, bi) => {
                  const left = (b.start / 24) * 100;
                  const width = ((b.end - b.start) / 24) * 100;
                  const isNow = currentHour >= b.start && currentHour < b.end;
                  return (
                    <div
                      key={bi}
                      className="heartbeat-block"
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                        background: isNow ? 'rgba(81, 207, 102, 0.15)' : undefined,
                        borderColor: isNow ? 'rgba(81, 207, 102, 0.3)' : undefined,
                        color: isNow ? 'var(--green)' : undefined,
                      }}
                      title={b.label}
                    >
                      {width > 6 && b.label}
                    </div>
                  );
                })}

                {/* Active dots */}
                {blocks.map((b, bi) => {
                  const isNow = currentHour >= b.start && currentHour < b.end;
                  if (!isNow) return null;
                  return (
                    <div
                      key={`dot-${bi}`}
                      className="heartbeat-dot active"
                      style={{ left: `${(currentHour / 24) * 100}%` }}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}

        {scheduledAgents.length === 0 && (
          <div className="empty-state">No scheduled routines configured</div>
        )}
      </div>
    </div>
  );
}

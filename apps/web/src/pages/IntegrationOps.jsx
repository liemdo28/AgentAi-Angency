import React, { useEffect, useState } from 'react';
import { createProjectCommand, executeSmartIssue, listProjects, updateProjectMachineControl } from '../api';

function formatDate(value) {
  if (!value) return '-';
  return value.slice(0, 10);
}

function formatDateTime(value) {
  if (!value) return '-';
  return value.replace('T', ' ').replace('Z', ' UTC').slice(0, 19);
}

function formatClock(clock) {
  if (!clock) return '-';
  return `${clock.display} (${clock.location})`;
}

export default function IntegrationOps() {
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busySuggestionId, setBusySuggestionId] = useState('');
  const [busyCommandId, setBusyCommandId] = useState('');
  const [busyMachineId, setBusyMachineId] = useState('');
  const [busyMachineCommandKey, setBusyMachineCommandKey] = useState('');
  const [selectedMachineId, setSelectedMachineId] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const projects = await listProjects();
      setProject(projects.find((item) => item.id === 'integration-full') || null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load().catch(() => {});
    const t = setInterval(() => load().catch(() => {}), 15000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!project) return;
    const ops = project.integration_ops || {};
    const remoteNodes = ops.remote_nodes || [];
    const preferred =
      remoteNodes.find((node) => node.online && !node.paused)?.machine_id ||
      remoteNodes[0]?.machine_id ||
      ops.source_machine_id ||
      '';
    setSelectedMachineId((current) => {
      if (current && remoteNodes.some((node) => node.machine_id === current)) return current;
      return preferred;
    });
  }, [project]);

  const handleSuggestion = async (suggestion) => {
    if (!suggestion?.prompt) return;
    setBusySuggestionId(suggestion.id);
    try {
      await executeSmartIssue(suggestion.prompt);
      window.alert(`Created workflow tasks for: ${suggestion.title}`);
    } catch (error) {
      window.alert(`Could not create workflow tasks: ${error.message}`);
    } finally {
      setBusySuggestionId('');
    }
  };

  const buildCommandRequest = (suggestion, machineId, machineName) => {
    if (!suggestion || !machineId) return null;
    if (suggestion.kind === 'download_gap' || suggestion.kind === 'download_retry') {
      return {
        machine_id: machineId,
        machine_name: machineName || 'Integration machine',
        command_type: 'download_missing_reports',
        title: suggestion.title,
        source_suggestion_id: suggestion.id,
        payload: {
          store: suggestion.store,
          start_date: suggestion.start_date,
          end_date: suggestion.end_date,
          report_types: suggestion.report_types || [],
          upload_to_gdrive: true,
        },
      };
    }
    if (suggestion.kind === 'qb_gap' || suggestion.kind === 'qb_failed') {
      return {
        machine_id: machineId,
        machine_name: machineName || 'Integration machine',
        command_type: 'catch_up_qb_sync',
        title: suggestion.title,
        source_suggestion_id: suggestion.id,
        payload: {
          store: suggestion.store,
          start_date: suggestion.start_date,
          end_date: suggestion.end_date,
          source: 'gdrive',
          source_filter: suggestion.source_filter || 'toast',
          preview: false,
          strict_mode: true,
        },
      };
    }
    return null;
  };

  const handleQueueCommand = async (suggestion, machineId, machineName) => {
    const payload = buildCommandRequest(suggestion, machineId, machineName);
    if (!payload) {
      window.alert('This suggestion cannot be converted into a machine command yet.');
      return;
    }
    setBusyCommandId(suggestion.id);
    try {
      await createProjectCommand('integration-full', payload);
      window.alert(`Queued command for ${machineName || machineId}`);
      await load();
    } catch (error) {
      window.alert(`Could not queue command: ${error.message}`);
    } finally {
      setBusyCommandId('');
    }
  };

  const handleMachineCommand = async (node, commandType, title, payload = {}) => {
    const key = `${node.machine_id}:${commandType}`;
    setBusyMachineCommandKey(key);
    try {
      await createProjectCommand('integration-full', {
        machine_id: node.machine_id,
        machine_name: node.machine_name || node.machine_id,
        command_type: commandType,
        title,
        payload,
      });
      await load();
    } catch (error) {
      window.alert(`Could not queue machine command: ${error.message}`);
    } finally {
      setBusyMachineCommandKey('');
    }
  };

  const handleMachineControl = async (machineId, data) => {
    setBusyMachineId(machineId);
    try {
      await updateProjectMachineControl('integration-full', machineId, data);
      await load();
    } catch (error) {
      window.alert(`Could not update machine control: ${error.message}`);
    } finally {
      setBusyMachineId('');
    }
  };

  if (loading && !project) {
    return <div className="page"><div className="empty-state">Loading integration operations…</div></div>;
  }

  if (!project) {
    return <div className="page"><div className="empty-state">Integration project not found.</div></div>;
  }

  const ops = project.integration_ops || {};
  const summary = ops.summary || {};
  const clocks = ops.world_clocks || [];
  const latestDownloads = ops.latest_downloads || [];
  const latestQbSync = ops.latest_qb_sync || [];
  const latestAttempts = ops.latest_qb_attempts || [];
  const suggestions = ops.ai_suggestions || [];
  const remoteNodes = ops.remote_nodes || [];
  const recentCommands = ops.recent_commands || [];
  const machineOptions = remoteNodes.length
    ? remoteNodes
    : (ops.source_machine_id
        ? [{
            machine_id: ops.source_machine_id,
            machine_name: ops.source_machine_name || ops.source_machine_id,
            online: true,
            runtime: ops.runtime || {},
          }]
        : []);
  const selectedMachine =
    machineOptions.find((node) => node.machine_id === selectedMachineId) ||
    machineOptions[0] ||
    null;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Integration Ops</h1>
          <div className="text-secondary" style={{ fontSize: 13, marginTop: 4 }}>
            Live operating view for Toast download and QuickBooks sync health.
          </div>
        </div>
        <div className="page-header-actions">
          <button className="btn btn-ghost" onClick={() => load().catch(() => {})}>Refresh</button>
        </div>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-label">Stores Tracked</div>
          <div className="stat-value accent">{summary.stores_tracked ?? 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Last Download</div>
          <div className="stat-value blue">{formatDate(summary.last_download_at)}</div>
          <div className="stat-sub">{formatDateTime(summary.last_download_at)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Last QB Sync</div>
          <div className="stat-value green">{formatDate(summary.last_qb_sync_at)}</div>
          <div className="stat-sub">{formatDateTime(summary.last_qb_sync_at)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Download Gaps</div>
          <div className="stat-value yellow">{summary.download_gap_count ?? 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">QB Gaps</div>
          <div className="stat-value yellow">{summary.qb_gap_count ?? 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Failed QB Runs</div>
          <div className="stat-value red">{summary.failed_qb_count ?? 0}</div>
        </div>
      </div>

      <div className="integration-layout">
        <div className="integration-main">
          <div className="integration-panel">
            <div className="section-title">World Clocks</div>
            <div className="integration-clock-grid">
              {clocks.map((clock) => (
                <div key={clock.key} className="integration-clock-card">
                  <div className="integration-clock-label">{clock.label}</div>
                  <div className="integration-clock-value">{clock.time}</div>
                  <div className="integration-clock-sub">{formatClock(clock)}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="integration-panel">
            <div className="section-title">Latest Download Activity</div>
            <div className="project-feed">
              {latestDownloads.length === 0 && <div className="project-feed-empty">No successful downloads found yet.</div>}
              {latestDownloads.map((item) => (
                <div key={`${item.store}-${item.report_key}-${item.business_date}`} className="project-feed-row">
                  <div>
                    <div className="project-feed-title">{item.store} · {item.report_label}</div>
                    <div className="project-feed-sub">{item.business_date || 'Unknown date'} · {formatDateTime(item.saved_at)}</div>
                  </div>
                  <span className="badge success">downloaded</span>
                </div>
              ))}
            </div>
          </div>

          <div className="integration-panel">
            <div className="section-title">Latest QB Sync Activity</div>
            <div className="project-feed">
              {latestQbSync.length === 0 && <div className="project-feed-empty">No successful QB sync runs found yet.</div>}
              {latestQbSync.map((item) => (
                <div key={`${item.store}-${item.source_name}-${item.date}`} className="project-feed-row">
                  <div>
                    <div className="project-feed-title">{item.store} · {item.source_name || 'Unknown source'}</div>
                    <div className="project-feed-sub">{item.date || 'Unknown date'} · {formatDateTime(item.completed_at)}</div>
                  </div>
                  <span className="badge success">{item.status}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="integration-side">
          <div className="integration-panel">
            <div className="section-title">AI Next Actions</div>
            <div className="settings-item" style={{ marginBottom: 12, alignItems: 'center' }}>
              <span className="settings-key">Dispatch To</span>
              <select
                className="filter-select"
                value={selectedMachineId}
                onChange={(event) => setSelectedMachineId(event.target.value)}
                style={{ maxWidth: 260 }}
              >
                {machineOptions.length === 0 && <option value="">No remote worker online</option>}
                {machineOptions.map((node) => (
                  <option key={node.machine_id} value={node.machine_id}>
                    {node.machine_name || node.machine_id}
                    {node.online ? ' · online' : ' · offline'}
                  </option>
                ))}
              </select>
            </div>
            <div className="project-suggestion-list">
              {suggestions.length === 0 && <div className="project-feed-empty">No suggestions right now.</div>}
              {suggestions.map((suggestion) => (
                <div key={suggestion.id} className="project-suggestion-card">
                  <div className="project-feed-title">{suggestion.title}</div>
                  <div className="project-feed-sub">{suggestion.description}</div>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => handleSuggestion(suggestion)}
                    disabled={busySuggestionId === suggestion.id}
                  >
                    {busySuggestionId === suggestion.id ? 'Creating...' : suggestion.action_label}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => handleQueueCommand(suggestion, selectedMachine?.machine_id, selectedMachine?.machine_name)}
                    disabled={!selectedMachine?.machine_id || busyCommandId === suggestion.id}
                    style={{ marginTop: 8 }}
                  >
                    {busyCommandId === suggestion.id ? 'Queueing...' : `Send to ${selectedMachine?.machine_name || 'machine'}`}
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="integration-panel">
            <div className="section-title">Latest QB Attempt</div>
            <div className="project-feed">
              {latestAttempts.length === 0 && <div className="project-feed-empty">No QB attempts found yet.</div>}
              {latestAttempts.map((item) => (
                <div key={`${item.store}-${item.source_name}-${item.status}-${item.date}`} className="project-feed-row">
                  <div>
                    <div className="project-feed-title">{item.store} · {item.source_name || 'Unknown source'}</div>
                    <div className="project-feed-sub">{item.date || 'Unknown date'} · {formatDateTime(item.completed_at)}</div>
                    {item.error_message && <div className="project-feed-sub">{item.error_message}</div>}
                  </div>
                  <span className={`badge ${item.status === 'success' ? 'success' : item.status === 'failed' ? 'failed' : 'pending'}`}>
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="integration-panel">
            <div className="section-title">Source</div>
            <div className="settings-item">
              <span className="settings-key">Project</span>
              <span className="settings-val">{project.name}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">Mode</span>
              <span className="settings-val">{ops.source_mode || 'local'}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">Machine</span>
              <span className="settings-val">{ops.source_machine_name || '-'}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">Machine ID</span>
              <span className="settings-val">{ops.source_machine_id || '-'}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">Branch</span>
              <span className="settings-val">{project.branch || '-'}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">GitHub</span>
              <span className="settings-val">{project.github || '-'}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">Snapshot</span>
              <span className="settings-val">{formatDateTime(ops.generated_at)}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">Received</span>
              <span className="settings-val">{formatDateTime(ops.source_received_at)}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">Runtime Mode</span>
              <span className="settings-val">{ops.runtime?.mode || '-'}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">Worker State</span>
              <span className="settings-val">{ops.runtime?.worker_status || '-'}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">Active Command</span>
              <span className="settings-val">{ops.runtime?.active_command_type || '-'}</span>
            </div>
            <div className="settings-item">
              <span className="settings-key">Headless Downloads</span>
              <span className="settings-val">{ops.runtime?.headless_downloads ? 'enabled' : 'disabled'}</span>
            </div>
          </div>

          <div className="integration-panel">
            <div className="section-title">Observed Machines</div>
            <div className="project-feed">
              {remoteNodes.length === 0 && (
                <div className="project-feed-empty">No remote publishers yet. Local snapshot fallback is active.</div>
              )}
              {remoteNodes.map((node) => (
                <div key={node.machine_id || node.machine_name} className="project-feed-row">
                  <div>
                    <div className="project-feed-title">{node.machine_name || 'Unknown machine'}</div>
                    <div className="project-feed-sub">
                      {(node.source_type || 'integration-full')} · Snapshot: {formatDateTime(node.received_at)}
                    </div>
                    <div className="project-feed-sub">
                      Last seen: {formatDateTime(node.last_seen_at)} · {node.online ? 'online' : 'offline'}
                    </div>
                    <div className="project-feed-sub">
                      Mode: {node.runtime?.mode || 'gui'} · Worker: {node.runtime?.worker_status || 'idle'}
                      {node.runtime?.active_command_type ? ` · Active: ${node.runtime.active_command_type}` : ''}
                    </div>
                    <div className="project-feed-sub">
                      Browser: {node.runtime?.headless_downloads ? 'headless' : 'visible'} · Snapshot interval: {node.runtime?.snapshot_interval_seconds || '-'}s
                      {node.runtime?.last_snapshot_published_at ? ` · Published: ${formatDateTime(node.runtime.last_snapshot_published_at)}` : ''}
                    </div>
                    <div className="project-feed-sub">
                      Download gaps: {node.summary?.download_gap_count ?? 0} · QB gaps: {node.summary?.qb_gap_count ?? 0}
                    </div>
                    {(node.paused || node.draining || node.pause_reason) && (
                      <div className="project-feed-sub">
                        {node.paused ? 'paused' : 'active'} · {node.draining ? 'draining' : 'dispatching'}
                        {node.pause_reason ? ` · ${node.pause_reason}` : ''}
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => handleMachineControl(node.machine_id, { paused: !node.paused, pause_reason: node.paused ? '' : 'Paused from Integration Ops' })}
                        disabled={busyMachineId === node.machine_id}
                      >
                        {node.paused ? 'Resume' : 'Pause'}
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => handleMachineControl(node.machine_id, { draining: !node.draining, cancel_pending: !node.draining })}
                        disabled={busyMachineId === node.machine_id}
                      >
                        {node.draining ? 'Clear Drain' : 'Drain Queue'}
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => handleMachineCommand(node, 'publish_snapshot_now', `Publish snapshot · ${node.machine_name || node.machine_id}`)}
                        disabled={busyMachineCommandKey === `${node.machine_id}:publish_snapshot_now`}
                      >
                        {busyMachineCommandKey === `${node.machine_id}:publish_snapshot_now` ? 'Queueing...' : 'Snapshot Now'}
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => handleMachineCommand(node, 'run_environment_diagnostics', `Self check · ${node.machine_name || node.machine_id}`)}
                        disabled={busyMachineCommandKey === `${node.machine_id}:run_environment_diagnostics`}
                      >
                        {busyMachineCommandKey === `${node.machine_id}:run_environment_diagnostics` ? 'Queueing...' : 'Self Check'}
                      </button>
                    </div>
                  </div>
                  <span className={`badge ${node.online ? 'success' : 'pending'}`}>{node.machine_id || 'node'}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="integration-panel">
            <div className="section-title">Command Queue</div>
            <div className="project-feed">
              {recentCommands.length === 0 && (
                <div className="project-feed-empty">No queued commands yet.</div>
              )}
              {recentCommands.map((command) => (
                <div key={command.id} className="project-feed-row">
                  <div>
                    <div className="project-feed-title">{command.title || command.command_type}</div>
                    <div className="project-feed-sub">
                      {command.machine_name || command.machine_id} · {formatDateTime(command.created_at)}
                    </div>
                    <div className="project-feed-sub">
                      Attempts: {command.attempt_count ?? 0}/{command.max_attempts ?? 0}
                      {command.lease_expires_at ? ` · Lease: ${formatDateTime(command.lease_expires_at)}` : ''}
                    </div>
                    {command.error_message && <div className="project-feed-sub">{command.error_message}</div>}
                  </div>
                  <span className={`badge ${command.status === 'success' ? 'success' : command.status === 'failed' ? 'failed' : 'pending'}`}>
                    {command.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

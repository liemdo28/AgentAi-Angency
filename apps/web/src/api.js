const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

// Dashboard
export const getStats = () => request('/dashboard/stats');
export const triggerCycle = () => request('/orchestrator/cycle', { method: 'POST' });

// Goals
export const listGoals = () => request('/goals');
export const createGoal = (data) => request('/goals', { method: 'POST', body: JSON.stringify(data) });

// Tasks / Issues
export const listTasks = (status) => request(`/tasks${status ? `?status=${status}` : ''}`);
export const getTask = (id) => request(`/tasks/${id}`);
export const createTask = (data) => request('/tasks', { method: 'POST', body: JSON.stringify(data) });
export const cancelTask = (id) => request(`/tasks/${id}/cancel`, { method: 'POST' });

// Agents
export const listAgents = () => request('/agents');
export const listRuntimeAgents = () => request('/agents/runtime');
export const listAgentRoles = () => request('/agents/roles');
export const registerAgent = (data) => request('/agents', { method: 'POST', body: JSON.stringify(data) });

// Jobs
export const listJobs = (taskId) => request(`/jobs${taskId ? `?task_id=${taskId}` : ''}`);

// Approvals
export const listApprovals = (status = 'pending') => request(`/approvals?status=${status}`);
export const requestApproval = (taskId) => request(`/approvals/${taskId}/request`, { method: 'POST' });
export const resolveApproval = (id, data) =>
  request(`/approvals/${id}/resolve`, { method: 'POST', body: JSON.stringify(data) });

// Smart Issues
export const planSmartIssue = (text) => request('/issues/plan', { method: 'POST', body: JSON.stringify({ text }) });
export const executeSmartIssue = (text) => request('/issues/execute', { method: 'POST', body: JSON.stringify({ text, auto_create: true }) });

// Activity
export const getActivity = () => request('/activity');

// Projects
export const listProjects = () => request('/projects');
export const getProject = (id) => request(`/projects/${id}`);
export const checkProjectHealth = (id) => request(`/projects/${id}/health`);
export const listProjectCommands = (id, machineId) => request(`/projects/${id}/commands${machineId ? `?machine_id=${machineId}` : ''}`);
export const createProjectCommand = (id, data) => request(`/projects/${id}/commands`, { method: 'POST', body: JSON.stringify(data) });
export const listProjectMachines = (id) => request(`/projects/${id}/machines`);
export const updateProjectMachineControl = (id, machineId, data) =>
  request(`/projects/${id}/machines/${machineId}/control`, { method: 'POST', body: JSON.stringify(data) });

// Stores
export const listStores = () => request('/stores');
export const getStore = (id) => request(`/stores/${id}`);

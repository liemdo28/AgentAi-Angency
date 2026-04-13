const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { const body = await res.json(); detail = body.detail || body.message || JSON.stringify(body); } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
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
export const listApprovals = (status = 'pending', resourceType) =>
  request(`/approvals?status=${status}${resourceType ? `&resource_type=${encodeURIComponent(resourceType)}` : ''}`);
export const requestApproval = (taskId) => request(`/approvals/${taskId}/request`, { method: 'POST' });
export const resolveApproval = (id, data) =>
  request(`/approvals/${id}/resolve`, { method: 'POST', body: JSON.stringify(data) });
export const listGovernanceApprovals = (status = 'pending') => request(`/approvals?status=${status}&resource_type=department_action`);

// Smart Issues
export const planSmartIssue = (text) => request('/issues/plan', { method: 'POST', body: JSON.stringify({ text }) });
export const executeSmartIssue = (text) => request('/issues/execute', { method: 'POST', body: JSON.stringify({ text, auto_create: true }) });

// Activity
export const getActivity = () => request('/activity');

// Projects
export const listProjects = () => request('/projects');
export const getProject = (id) => request(`/projects/${id}`);
export const runProjectQaSimulation = (id, data) => request(`/projects/${id}/qa-simulate`, { method: 'POST', body: JSON.stringify(data) });
export const runProjectLiveQa = (id, data) => request(`/projects/${id}/qa-live`, { method: 'POST', body: JSON.stringify(data) });
export const checkProjectLiveStatus = (id) => request(`/projects/${id}/live-status`);
export const checkProjectHealth = (id) => request(`/projects/${id}/health`);
export const listProjectCommands = (id, machineId) => request(`/projects/${id}/commands${machineId ? `?machine_id=${machineId}` : ''}`);
export const createProjectCommand = (id, data) => request(`/projects/${id}/commands`, { method: 'POST', body: JSON.stringify(data) });
export const listProjectMachines = (id) => request(`/projects/${id}/machines`);
export const updateProjectMachineControl = (id, machineId, data) =>
  request(`/projects/${id}/machines/${machineId}/control`, { method: 'POST', body: JSON.stringify(data) });

// Department governance
export const listPermissions = (module) => request(`/permissions${module ? `?module=${encodeURIComponent(module)}` : ''}`);
export const listDepartments = (params = {}) => {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
  ).toString();
  return request(`/departments${query ? `?${query}` : ''}`);
};
export const getDepartment = (id) => request(`/departments/${id}`);
export const createDepartment = (data) => request('/departments', { method: 'POST', body: JSON.stringify(data) });
export const updateDepartment = (id, data) => request(`/departments/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const lockDepartment = (id) => request(`/departments/${id}/lock`, { method: 'POST' });
export const unlockDepartment = (id) => request(`/departments/${id}/unlock`, { method: 'POST' });
export const hideDepartment = (id) => request(`/departments/${id}/hide`, { method: 'POST' });
export const unhideDepartment = (id) => request(`/departments/${id}/unhide`, { method: 'POST' });
export const deleteDepartment = (id) => request(`/departments/${id}`, { method: 'DELETE' });
export const restoreDepartment = (id) => request(`/departments/${id}/restore`, { method: 'POST' });
export const getDepartmentPermissions = (id) => request(`/departments/${id}/permissions`);
export const updateDepartmentPermissions = (id, data) =>
  request(`/departments/${id}/permissions`, { method: 'PUT', body: JSON.stringify(data) });
export const getStoreDepartments = (storeId) => request(`/stores/${storeId}/departments`);
export const getStoreDepartmentPermissions = (storeId, departmentId) => request(`/stores/${storeId}/departments/${departmentId}/permissions`);
export const updateStoreDepartments = (storeId, data) =>
  request(`/stores/${storeId}/departments`, { method: 'PUT', body: JSON.stringify(data) });
export const updateStoreDepartmentPermissions = (storeId, departmentId, data) =>
  request(`/stores/${storeId}/departments/${departmentId}/permissions`, { method: 'PUT', body: JSON.stringify(data) });
export const listPolicies = (params = {}) => {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
  ).toString();
  return request(`/policies${query ? `?${query}` : ''}`);
};
export const createPolicy = (data) => request('/policies', { method: 'POST', body: JSON.stringify(data) });
export const updatePolicy = (id, data) => request(`/policies/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const activatePolicy = (id) => request(`/policies/${id}/activate`, { method: 'POST' });
export const deactivatePolicy = (id) => request(`/policies/${id}/deactivate`, { method: 'POST' });
export const evaluatePolicy = (data) => request('/policies/evaluate', { method: 'POST', body: JSON.stringify(data) });
export const requestGovernedAction = (data) => request('/governance/actions/request', { method: 'POST', body: JSON.stringify(data) });
export const listPolicyVersions = (id) => request(`/policies/${id}/versions`);
export const rollbackPolicyVersion = (policyId, versionId) => request(`/policies/${policyId}/versions/${versionId}/rollback`, { method: 'POST' });
export const listPolicySimulations = (params = {}) => {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
  ).toString();
  return request(`/policies/simulations${query ? `?${query}` : ''}`);
};
export const listAuditLogs = (params = {}) => {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
  ).toString();
  return request(`/audit-logs${query ? `?${query}` : ''}`);
};

// Task Execution
export const executeTask = (id) => request(`/tasks/${id}/execute`, { method: 'POST' });

// Marketing Sync
export const getMarketingStores = () => request('/marketing/stores');
export const getMarketingStore = (id) => request(`/marketing/stores/${id}`);
export const triggerMarketingSync = (storeId) => request(`/marketing/sync${storeId ? `?store_id=${storeId}` : ''}`, { method: 'POST' });
export const getMarketingSummary = () => request('/marketing/summary');
export const getMarketingHealth = () => request('/marketing/health');

// LLM Stats
export const getLlmStats = () => request('/llm/stats');

// Stores
export const listStores = () => request('/stores');
export const getStore = (id) => request(`/stores/${id}`);


// ── Posts Review & Approval ────────────────────────────────────────────────
export const generatePost = (data) =>
  request('/posts/generate', { method: 'POST', body: JSON.stringify(data) });

export const listReviewQueue = (params = {}) => {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v != null && v !== '')
  ).toString();
  return request(`/posts/review-queue${qs ? `?${qs}` : ''}`);
};

export const getPostStats = () => request('/posts/stats');

export const getPost = (id) => request(`/posts/${id}`);

export const approvePost = (id, data) =>
  request(`/posts/${id}/approve`, { method: 'POST', body: JSON.stringify(data) });

export const rejectPost = (id, data) =>
  request(`/posts/${id}/reject`, { method: 'POST', body: JSON.stringify(data) });

export const requestRevision = (id, data) =>
  request(`/posts/${id}/request-revision`, { method: 'POST', body: JSON.stringify(data) });

export const regeneratePost = (id, data) =>
  request(`/posts/${id}/regenerate`, { method: 'POST', body: JSON.stringify(data) });

export const publishPost = (id) =>
  request(`/posts/${id}/publish`, { method: 'POST' });

export const getPostLogs = (id) => request(`/posts/${id}/logs`);

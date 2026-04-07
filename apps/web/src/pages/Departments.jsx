import React, { useEffect, useMemo, useState } from 'react';
import {
  activatePolicy,
  createDepartment,
  createPolicy,
  deactivatePolicy,
  deleteDepartment,
  evaluatePolicy,
  getDepartmentPermissions,
  getStoreDepartmentPermissions,
  getStoreDepartments,
  hideDepartment,
  listAuditLogs,
  listDepartments,
  listPermissions,
  listPolicies,
  listPolicySimulations,
  listPolicyVersions,
  listStores,
  lockDepartment,
  requestGovernedAction,
  rollbackPolicyVersion,
  restoreDepartment,
  unhideDepartment,
  unlockDepartment,
  updateDepartment,
  updateDepartmentPermissions,
  updatePolicy,
  updateStoreDepartmentPermissions,
  updateStoreDepartments,
} from '../api';

const STATUS_TABS = ['all', 'active', 'locked', 'hidden', 'deleted', 'store_assignment', 'policies', 'audit'];
const EXECUTION_MODES = ['disabled', 'suggest_only', 'semi_auto', 'full_auto'];

const EMPTY_DEPARTMENT = {
  code: '',
  name: '',
  description: '',
  category: 'general',
  status: 'active',
  allow_store_assignment: true,
  allow_ai_agent_execution: true,
  allow_human_assignment: true,
  requires_ceo_visibility_only: false,
  execution_mode: 'suggest_only',
  parent_department_id: '',
};

const EMPTY_POLICY = {
  policy_code: '',
  policy_name: '',
  scope_type: 'department',
  target_type: 'department_code',
  target_id: '',
  condition_json: '{"all":[{"field":"action","op":"eq","value":"reviews.reply.publish"}]}',
  effect: 'require_approval',
  approval_chain_json: '["store_manager"]',
  escalation_json: '{"target":"store_manager"}',
  audit_required: true,
  priority: 100,
  is_active: true,
  effective_from: '',
  effective_to: '',
};

function statusClass(status) {
  if (status === 'active') return 'success';
  if (status === 'locked' || status === 'hidden') return 'pending';
  if (status === 'deleted') return 'failed';
  return 'pending';
}

function formatDate(value) {
  if (!value) return '-';
  return value.replace('T', ' ').replace('Z', ' UTC').slice(0, 19);
}

export default function Departments() {
  const [tab, setTab] = useState('all');
  const [departments, setDepartments] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [stores, setStores] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [simulations, setSimulations] = useState([]);
  const [policyVersions, setPolicyVersions] = useState([]);
  const [selectedDepartmentId, setSelectedDepartmentId] = useState('');
  const [selectedStoreId, setSelectedStoreId] = useState('');
  const [storeMatrix, setStoreMatrix] = useState([]);
  const [selectedStoreDepartmentId, setSelectedStoreDepartmentId] = useState('');
  const [storePermissionState, setStorePermissionState] = useState(null);
  const [search, setSearch] = useState('');
  const [departmentForm, setDepartmentForm] = useState(EMPTY_DEPARTMENT);
  const [policyForm, setPolicyForm] = useState(EMPTY_POLICY);
  const [policyEvalForm, setPolicyEvalForm] = useState({
    actor_type: 'agent',
    actor_id: 'agent-review-01',
    actor_role: 'department_head',
    store_id: '',
    department_id: '',
    action: 'reviews.reply.publish',
    permission_key: 'reviews.reply',
    context_json: '{"rating":2,"sentiment":"negative"}',
  });
  const [policyEvalResult, setPolicyEvalResult] = useState(null);
  const [saving, setSaving] = useState(false);

  const selectedDepartment = useMemo(
    () => departments.find((item) => item.id === selectedDepartmentId) || null,
    [departments, selectedDepartmentId]
  );

  const filteredDepartments = useMemo(() => {
    if (tab === 'all') return departments;
    if (['active', 'locked', 'hidden', 'deleted'].includes(tab)) {
      return departments.filter((item) => item.status === tab);
    }
    return departments;
  }, [departments, tab]);

  const loadCore = async (currentSearch = search) => {
    const [departmentData, policyData, auditData, storeData] = await Promise.all([
      listDepartments({ search: currentSearch }),
      listPolicies(),
      listAuditLogs({ limit: 40 }),
      listStores(),
    ]);
    setDepartments(departmentData);
    setPolicies(policyData);
    setAuditLogs(auditData);
    setStores(storeData);
    setSimulations(await listPolicySimulations({ limit: 20 }));
    if (!selectedDepartmentId && departmentData[0]) {
      setSelectedDepartmentId(departmentData[0].id);
    }
    if (!selectedStoreId && storeData[0]) {
      setSelectedStoreId(storeData[0].id);
    }
  };

  useEffect(() => {
    listPermissions().then(setPermissions).catch(() => {});
    loadCore().catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedDepartmentId) return;
    getDepartmentPermissions(selectedDepartmentId).then(setPermissions).catch(() => {});
  }, [selectedDepartmentId]);

  useEffect(() => {
    if (!selectedStoreId) return;
    getStoreDepartments(selectedStoreId).then(setStoreMatrix).catch(() => {});
  }, [selectedStoreId, departments.length]);

  useEffect(() => {
    if (!selectedStoreId || !selectedStoreDepartmentId) {
      setStorePermissionState(null);
      return;
    }
    getStoreDepartmentPermissions(selectedStoreId, selectedStoreDepartmentId)
      .then(setStorePermissionState)
      .catch(() => setStorePermissionState(null));
  }, [selectedStoreId, selectedStoreDepartmentId]);

  useEffect(() => {
    if (selectedDepartment) {
      setDepartmentForm({
        code: selectedDepartment.code,
        name: selectedDepartment.name,
        description: selectedDepartment.description || '',
        category: selectedDepartment.category || 'general',
        status: selectedDepartment.status || 'active',
        allow_store_assignment: !!selectedDepartment.allow_store_assignment,
        allow_ai_agent_execution: !!selectedDepartment.allow_ai_agent_execution,
        allow_human_assignment: !!selectedDepartment.allow_human_assignment,
        requires_ceo_visibility_only: !!selectedDepartment.requires_ceo_visibility_only,
        execution_mode: selectedDepartment.execution_mode || 'suggest_only',
        parent_department_id: selectedDepartment.parent_department_id || '',
      });
      setPolicyEvalForm((prev) => ({ ...prev, department_id: selectedDepartment.id }));
    }
  }, [selectedDepartment]);

  useEffect(() => {
    if (!policies.length) {
      setPolicyVersions([]);
      return;
    }
    listPolicyVersions(policies[0].id).then(setPolicyVersions).catch(() => setPolicyVersions([]));
  }, [policies]);

  const refreshStoreMatrix = async () => {
    if (!selectedStoreId) return;
    const matrix = await getStoreDepartments(selectedStoreId);
    setStoreMatrix(matrix);
  };

  const handleDepartmentSubmit = async () => {
    setSaving(true);
    try {
      if (selectedDepartment) {
        await updateDepartment(selectedDepartment.id, departmentForm);
      } else {
        await createDepartment(departmentForm);
      }
      setDepartmentForm(EMPTY_DEPARTMENT);
      setSelectedDepartmentId('');
      await loadCore();
    } catch (error) {
      window.alert(error.message);
    } finally {
      setSaving(false);
    }
  };

  const handlePermissionToggle = async (permissionKey, allowed) => {
    if (!selectedDepartment) return;
    const next = permissions.map((item) =>
      item.permission_key === permissionKey ? { key: item.permission_key, allowed } : { key: item.permission_key, allowed: item.allowed }
    );
    try {
      const updated = await updateDepartmentPermissions(selectedDepartment.id, { permissions: next });
      setPermissions(updated);
      await loadCore();
    } catch (error) {
      window.alert(error.message);
    }
  };

  const handleLifecycle = async (action, departmentId) => {
    try {
      if (action === 'lock') await lockDepartment(departmentId);
      if (action === 'unlock') await unlockDepartment(departmentId);
      if (action === 'hide') await hideDepartment(departmentId);
      if (action === 'unhide') await unhideDepartment(departmentId);
      if (action === 'delete') await deleteDepartment(departmentId);
      if (action === 'restore') await restoreDepartment(departmentId);
      await loadCore();
    } catch (error) {
      window.alert(error.message);
    }
  };

  const handleStoreMatrixToggle = (departmentId, field, value) => {
    setStoreMatrix((current) =>
      current.map((item) => (item.department_id === departmentId ? { ...item, [field]: value } : item))
    );
  };

  const saveStoreMatrix = async () => {
    try {
      await updateStoreDepartments(selectedStoreId, {
        departments: storeMatrix.map((item) => ({
          department_id: item.department_id,
          enabled: !!item.enabled,
          locked: !!item.locked,
          hidden: !!item.hidden,
          deleted: !!item.deleted,
          custom_policy_enabled: !!item.custom_policy_enabled,
          execution_mode: item.execution_mode || null,
        })),
      });
      await refreshStoreMatrix();
      await loadCore();
    } catch (error) {
      window.alert(error.message);
    }
  };

  const handleStorePermissionToggle = (permissionKey, allowed) => {
    setStorePermissionState((current) => {
      if (!current) return current;
      return {
        ...current,
        permissions: current.permissions.map((item) =>
          item.permission_key === permissionKey
            ? { ...item, allowed, source: allowed === item.default_allowed ? 'default' : 'override' }
            : item
        ),
      };
    });
  };

  const saveStorePermissionOverrides = async () => {
    if (!selectedStoreId || !selectedStoreDepartmentId || !storePermissionState) return;
    try {
      await updateStoreDepartmentPermissions(selectedStoreId, selectedStoreDepartmentId, {
        permissions: storePermissionState.permissions.map((item) => ({
          key: item.permission_key,
          allowed: !!item.allowed,
          source: item.allowed === item.default_allowed ? 'default' : 'override',
        })),
      });
      const refreshed = await getStoreDepartmentPermissions(selectedStoreId, selectedStoreDepartmentId);
      setStorePermissionState(refreshed);
      await refreshStoreMatrix();
    } catch (error) {
      window.alert(error.message);
    }
  };

  const handlePolicySubmit = async () => {
    try {
      const payload = {
        ...policyForm,
        condition_json: JSON.parse(policyForm.condition_json || '{}'),
        approval_chain_json: JSON.parse(policyForm.approval_chain_json || '[]'),
        escalation_json: JSON.parse(policyForm.escalation_json || '{}'),
        effective_from: policyForm.effective_from || null,
        effective_to: policyForm.effective_to || null,
      };
      const existing = policies.find((item) => item.policy_code === payload.policy_code);
      if (existing) {
        await updatePolicy(existing.id, payload);
      } else {
        await createPolicy(payload);
      }
      setPolicyForm(EMPTY_POLICY);
      await loadCore();
    } catch (error) {
      window.alert(`Policy save failed: ${error.message}`);
    }
  };

  const handlePolicyEvaluate = async () => {
    try {
      const result = await evaluatePolicy({
        ...policyEvalForm,
        store_id: policyEvalForm.store_id || null,
        permission_key: policyEvalForm.permission_key || null,
        context: JSON.parse(policyEvalForm.context_json || '{}'),
      });
      setPolicyEvalResult(result);
    } catch (error) {
      window.alert(`Evaluation failed: ${error.message}`);
    }
  };

  const handleGovernedRequest = async () => {
    try {
      const result = await requestGovernedAction({
        ...policyEvalForm,
        task_id: null,
        store_id: policyEvalForm.store_id || null,
        permission_key: policyEvalForm.permission_key || null,
        context: JSON.parse(policyEvalForm.context_json || '{}'),
      });
      setPolicyEvalResult(result);
      setSimulations(await listPolicySimulations({ limit: 20 }));
    } catch (error) {
      window.alert(`Request failed: ${error.message}`);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Department Governance</h1>
          <div className="text-secondary" style={{ fontSize: 13 }}>
            Department master, store assignment, permission matrix, policy engine, and audit trail
          </div>
        </div>
        <div className="page-header-actions">
          <button className="btn btn-ghost" onClick={() => loadCore()}>Refresh</button>
        </div>
      </div>

      <div className="stats-row" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="stat-card"><div className="stat-label">Departments</div><div className="stat-value accent">{departments.length}</div></div>
        <div className="stat-card"><div className="stat-label">Active</div><div className="stat-value green">{departments.filter((d) => d.status === 'active').length}</div></div>
        <div className="stat-card"><div className="stat-label">Locked / Hidden</div><div className="stat-value yellow">{departments.filter((d) => ['locked', 'hidden'].includes(d.status)).length}</div></div>
        <div className="stat-card"><div className="stat-label">Policies</div><div className="stat-value blue">{policies.length}</div></div>
      </div>

      <div className="tab-bar">
        {STATUS_TABS.map((item) => (
          <button key={item} className={`tab-btn ${tab === item ? 'active' : ''}`} onClick={() => setTab(item)}>
            {item === 'store_assignment' ? 'Store Assignment' : item === 'audit' ? 'Audit Logs' : item === 'policies' ? 'Policies' : item.charAt(0).toUpperCase() + item.slice(1)}
          </button>
        ))}
      </div>

      {tab !== 'store_assignment' && tab !== 'policies' && tab !== 'audit' && (
        <>
          <div className="create-panel" style={{ marginBottom: 16 }}>
            <div className="form-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Search</label>
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find department by name, code, or description" />
              </div>
              <button className="btn btn-ghost" onClick={() => loadCore(search)}>Apply</button>
              <button className="btn btn-ghost" onClick={() => { setSearch(''); loadCore(''); }}>Clear</button>
            </div>
          </div>

          <div className="governance-layout">
            <div className="governance-panel">
              <div className="section-title">Department Master</div>
              <div className="governance-table">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Code</th>
                      <th>Status</th>
                      <th>Visibility</th>
                      <th>AI Mode</th>
                      <th>Stores</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredDepartments.map((item) => (
                      <tr key={item.id} className={selectedDepartmentId === item.id ? 'selected' : ''}>
                        <td>
                          <button className="link-button" onClick={() => setSelectedDepartmentId(item.id)}>{item.name}</button>
                        </td>
                        <td className="mono">{item.code}</td>
                        <td><span className={`badge ${statusClass(item.status)}`}>{item.status}</span></td>
                        <td>{item.requires_ceo_visibility_only ? 'CEO only' : 'Standard'}</td>
                        <td>{item.execution_mode}</td>
                        <td>{item.assigned_stores_count || 0}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            {item.status === 'active' && <button className="btn btn-ghost btn-sm" onClick={() => handleLifecycle('lock', item.id)}>Lock</button>}
                            {item.status === 'locked' && <button className="btn btn-ghost btn-sm" onClick={() => handleLifecycle('unlock', item.id)}>Unlock</button>}
                            {item.status !== 'hidden' && item.status !== 'deleted' && <button className="btn btn-ghost btn-sm" onClick={() => handleLifecycle('hide', item.id)}>Hide</button>}
                            {item.status === 'hidden' && <button className="btn btn-ghost btn-sm" onClick={() => handleLifecycle('unhide', item.id)}>Unhide</button>}
                            {item.status !== 'deleted' && <button className="btn btn-danger btn-sm" onClick={() => handleLifecycle('delete', item.id)}>Delete</button>}
                            {item.status === 'deleted' && <button className="btn btn-success btn-sm" onClick={() => handleLifecycle('restore', item.id)}>Restore</button>}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="governance-side">
              <div className="settings-card">
                <h3>{selectedDepartment ? 'Edit Department' : 'Create Department'}</h3>
                <div className="form-group"><label>Code</label><input value={departmentForm.code} onChange={(e) => setDepartmentForm({ ...departmentForm, code: e.target.value })} /></div>
                <div className="form-group mt-2"><label>Name</label><input value={departmentForm.name} onChange={(e) => setDepartmentForm({ ...departmentForm, name: e.target.value })} /></div>
                <div className="form-group mt-2"><label>Description</label><textarea rows={3} value={departmentForm.description} onChange={(e) => setDepartmentForm({ ...departmentForm, description: e.target.value })} /></div>
                <div className="form-row mt-2">
                  <div className="form-group" style={{ flex: 1 }}><label>Category</label><input value={departmentForm.category} onChange={(e) => setDepartmentForm({ ...departmentForm, category: e.target.value })} /></div>
                  <div className="form-group" style={{ flex: 1 }}><label>Status</label><select value={departmentForm.status} onChange={(e) => setDepartmentForm({ ...departmentForm, status: e.target.value })}><option value="active">active</option><option value="locked">locked</option><option value="hidden">hidden</option><option value="deleted">deleted</option></select></div>
                </div>
                <div className="form-group mt-2"><label>Execution Mode</label><select value={departmentForm.execution_mode} onChange={(e) => setDepartmentForm({ ...departmentForm, execution_mode: e.target.value })}>{EXECUTION_MODES.map((mode) => <option key={mode} value={mode}>{mode}</option>)}</select></div>
                <div className="governance-checklist mt-4">
                  {[
                    ['allow_store_assignment', 'Allow store assignment'],
                    ['allow_ai_agent_execution', 'Allow AI agent execution'],
                    ['allow_human_assignment', 'Allow human assignment'],
                    ['requires_ceo_visibility_only', 'CEO-only visibility'],
                  ].map(([key, label]) => (
                    <label key={key} className="governance-check-item">
                      <input type="checkbox" checked={!!departmentForm[key]} onChange={(e) => setDepartmentForm({ ...departmentForm, [key]: e.target.checked })} />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                  <button className="btn btn-primary" onClick={handleDepartmentSubmit} disabled={saving}>{saving ? 'Saving...' : selectedDepartment ? 'Update Department' : 'Create Department'}</button>
                  <button className="btn btn-ghost" onClick={() => { setSelectedDepartmentId(''); setDepartmentForm(EMPTY_DEPARTMENT); }}>Reset</button>
                </div>
              </div>

              <div className="settings-card">
                <h3>Permission Editor</h3>
                {!selectedDepartment && <div className="project-feed-empty">Select a department to manage its permission baseline.</div>}
                {selectedDepartment && (
                  <div className="permission-grid">
                    {permissions.map((item) => (
                      <label key={item.permission_key} className="governance-check-item">
                        <input type="checkbox" checked={!!item.allowed} onChange={(e) => handlePermissionToggle(item.permission_key, e.target.checked)} />
                        <span>
                          <strong>{item.permission_key}</strong>
                          <div className="text-secondary" style={{ fontSize: 11 }}>{item.module} · {item.action}</div>
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {tab === 'store_assignment' && (
        <div className="governance-layout">
          <div className="governance-panel">
            <div className="page-header" style={{ marginBottom: 16 }}>
              <div>
                <div className="section-title">Store Department Matrix</div>
                <div className="text-secondary" style={{ fontSize: 12 }}>Choose what each store uses, what is locked, and what stays hidden.</div>
              </div>
              <div className="form-group" style={{ minWidth: 220 }}>
                <label>Store</label>
                <select value={selectedStoreId} onChange={(e) => setSelectedStoreId(e.target.value)}>
                  {stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
                </select>
              </div>
            </div>
            <div className="governance-table">
              <table>
                <thead>
                  <tr>
                    <th>Department</th>
                    <th>Enabled</th>
                    <th>Locked</th>
                    <th>Hidden</th>
                    <th>Custom Policy</th>
                    <th>Mode</th>
                  </tr>
                </thead>
                <tbody>
                  {storeMatrix.map((item) => (
                    <tr key={`${selectedStoreId}-${item.department_id}`}>
                      <td>
                        <button className="link-button" style={{ fontWeight: 600 }} onClick={() => setSelectedStoreDepartmentId(item.department_id)}>
                          {item.department_name}
                        </button>
                        <div className="text-secondary" style={{ fontSize: 11 }}>{item.department_code}</div>
                      </td>
                      <td><input type="checkbox" checked={!!item.enabled} onChange={(e) => handleStoreMatrixToggle(item.department_id, 'enabled', e.target.checked)} /></td>
                      <td><input type="checkbox" checked={!!item.locked} onChange={(e) => handleStoreMatrixToggle(item.department_id, 'locked', e.target.checked)} /></td>
                      <td><input type="checkbox" checked={!!item.hidden} onChange={(e) => handleStoreMatrixToggle(item.department_id, 'hidden', e.target.checked)} /></td>
                      <td><input type="checkbox" checked={!!item.custom_policy_enabled} onChange={(e) => handleStoreMatrixToggle(item.department_id, 'custom_policy_enabled', e.target.checked)} /></td>
                      <td>
                        <select value={item.execution_mode || 'suggest_only'} onChange={(e) => handleStoreMatrixToggle(item.department_id, 'execution_mode', e.target.value)}>
                          {EXECUTION_MODES.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: 14 }}>
              <button className="btn btn-primary" onClick={saveStoreMatrix}>Save Store Matrix</button>
            </div>
          </div>

          <div className="governance-side">
            <div className="settings-card">
              <h3>Store Permission Override</h3>
              {!selectedStoreDepartmentId && <div className="project-feed-empty">Choose a department row to edit store-level permission overrides.</div>}
              {storePermissionState && (
                <>
                  <div className="project-feed-sub" style={{ marginBottom: 12 }}>
                    {selectedStoreId} · {selectedStoreDepartmentId}
                  </div>
                  <div className="permission-grid" style={{ maxHeight: 420, overflowY: 'auto' }}>
                    {storePermissionState.permissions.map((item) => (
                      <label key={item.permission_key} className="governance-check-item">
                        <input type="checkbox" checked={!!item.allowed} onChange={(e) => handleStorePermissionToggle(item.permission_key, e.target.checked)} />
                        <span>
                          <strong>{item.permission_key}</strong>
                          <div className="text-secondary" style={{ fontSize: 11 }}>
                            {item.module} · base {item.default_allowed ? 'allow' : 'deny'} · {item.source}
                          </div>
                        </span>
                      </label>
                    ))}
                  </div>
                  <div style={{ marginTop: 14 }}>
                    <button className="btn btn-primary" onClick={saveStorePermissionOverrides}>Save Permission Overrides</button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {tab === 'policies' && (
        <div className="governance-layout">
          <div className="governance-panel">
            <div className="section-title">Policy Registry</div>
            <div className="project-feed">
              {policies.map((item) => (
                <div key={item.id} className="project-feed-row">
                  <div>
                    <div className="project-feed-title">{item.policy_name}</div>
                    <div className="project-feed-sub">{item.policy_code} · {item.scope_type} · {item.effect} · priority {item.priority}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span className={`badge ${item.is_active ? 'success' : 'pending'}`}>{item.is_active ? 'active' : 'inactive'}</span>
                    {item.is_active ? (
                      <button className="btn btn-ghost btn-sm" onClick={() => deactivatePolicy(item.id).then(() => loadCore())}>Deactivate</button>
                    ) : (
                      <button className="btn btn-success btn-sm" onClick={() => activatePolicy(item.id).then(() => loadCore())}>Activate</button>
                    )}
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() =>
                        setPolicyForm({
                          policy_code: item.policy_code,
                          policy_name: item.policy_name,
                          scope_type: item.scope_type,
                          target_type: item.target_type,
                          target_id: item.target_id,
                          condition_json: JSON.stringify(item.condition || {}, null, 2),
                          effect: item.effect,
                          approval_chain_json: JSON.stringify(item.approval_chain || [], null, 2),
                          escalation_json: JSON.stringify(item.escalation || {}, null, 2),
                          audit_required: !!item.audit_required,
                          priority: item.priority || 100,
                          is_active: !!item.is_active,
                          effective_from: item.effective_from || '',
                          effective_to: item.effective_to || '',
                        })
                      }
                    >
                      Edit
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        const latestVersion = policyVersions.find((version) => version.snapshot?.policy_code === item.policy_code);
                        if (!latestVersion) {
                          window.alert('No version available to rollback.');
                          return;
                        }
                        rollbackPolicyVersion(item.id, latestVersion.id).then(() => loadCore()).catch((error) => window.alert(error.message));
                      }}
                    >
                      Rollback
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="governance-side">
            <div className="settings-card">
              <h3>Policy Builder</h3>
              <div className="form-group"><label>Policy Code</label><input value={policyForm.policy_code} onChange={(e) => setPolicyForm({ ...policyForm, policy_code: e.target.value })} /></div>
              <div className="form-group mt-2"><label>Policy Name</label><input value={policyForm.policy_name} onChange={(e) => setPolicyForm({ ...policyForm, policy_name: e.target.value })} /></div>
              <div className="form-row mt-2">
                <div className="form-group" style={{ flex: 1 }}><label>Scope</label><select value={policyForm.scope_type} onChange={(e) => setPolicyForm({ ...policyForm, scope_type: e.target.value })}><option value="company">company</option><option value="store">store</option><option value="department">department</option><option value="role">role</option><option value="action">action</option></select></div>
                <div className="form-group" style={{ flex: 1 }}><label>Effect</label><select value={policyForm.effect} onChange={(e) => setPolicyForm({ ...policyForm, effect: e.target.value })}><option value="allow">allow</option><option value="deny">deny</option><option value="require_approval">require_approval</option><option value="require_ceo_approval">require_ceo_approval</option><option value="suggest_only">suggest_only</option><option value="auto_execute">auto_execute</option><option value="escalate">escalate</option></select></div>
              </div>
              <div className="form-row mt-2">
                <div className="form-group" style={{ flex: 1 }}><label>Target Type</label><input value={policyForm.target_type} onChange={(e) => setPolicyForm({ ...policyForm, target_type: e.target.value })} /></div>
                <div className="form-group" style={{ flex: 1 }}><label>Target ID</label><input value={policyForm.target_id} onChange={(e) => setPolicyForm({ ...policyForm, target_id: e.target.value })} /></div>
              </div>
              <div className="form-group mt-2"><label>Condition JSON</label><textarea rows={5} value={policyForm.condition_json} onChange={(e) => setPolicyForm({ ...policyForm, condition_json: e.target.value })} /></div>
              <div className="form-group mt-2"><label>Approval Chain JSON</label><textarea rows={3} value={policyForm.approval_chain_json} onChange={(e) => setPolicyForm({ ...policyForm, approval_chain_json: e.target.value })} /></div>
              <div className="form-group mt-2"><label>Escalation JSON</label><textarea rows={3} value={policyForm.escalation_json} onChange={(e) => setPolicyForm({ ...policyForm, escalation_json: e.target.value })} /></div>
              <div className="form-row mt-2">
                <div className="form-group" style={{ flex: 1 }}><label>Priority</label><input type="number" value={policyForm.priority} onChange={(e) => setPolicyForm({ ...policyForm, priority: Number(e.target.value) })} /></div>
                <div className="form-group" style={{ flex: 1 }}><label>Active</label><select value={policyForm.is_active ? 'true' : 'false'} onChange={(e) => setPolicyForm({ ...policyForm, is_active: e.target.value === 'true' })}><option value="true">true</option><option value="false">false</option></select></div>
              </div>
              <div style={{ marginTop: 16 }}>
                <button className="btn btn-primary" onClick={handlePolicySubmit}>Save Policy</button>
              </div>
            </div>

            <div className="settings-card">
              <h3>Policy Evaluate</h3>
              <div className="form-row">
                <div className="form-group" style={{ flex: 1 }}><label>Actor Role</label><input value={policyEvalForm.actor_role} onChange={(e) => setPolicyEvalForm({ ...policyEvalForm, actor_role: e.target.value })} /></div>
                <div className="form-group" style={{ flex: 1 }}><label>Store</label><select value={policyEvalForm.store_id} onChange={(e) => setPolicyEvalForm({ ...policyEvalForm, store_id: e.target.value })}><option value="">None</option>{stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select></div>
              </div>
              <div className="form-group mt-2"><label>Department</label><select value={policyEvalForm.department_id} onChange={(e) => setPolicyEvalForm({ ...policyEvalForm, department_id: e.target.value })}>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
              <div className="form-group mt-2"><label>Action</label><input value={policyEvalForm.action} onChange={(e) => setPolicyEvalForm({ ...policyEvalForm, action: e.target.value })} /></div>
              <div className="form-group mt-2"><label>Permission Key</label><input value={policyEvalForm.permission_key} onChange={(e) => setPolicyEvalForm({ ...policyEvalForm, permission_key: e.target.value })} /></div>
              <div className="form-group mt-2"><label>Context JSON</label><textarea rows={4} value={policyEvalForm.context_json} onChange={(e) => setPolicyEvalForm({ ...policyEvalForm, context_json: e.target.value })} /></div>
              <div style={{ marginTop: 16 }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button className="btn btn-primary" onClick={handlePolicyEvaluate}>Evaluate</button>
                  <button className="btn btn-ghost" onClick={handleGovernedRequest}>Request Approval / Run</button>
                </div>
              </div>
              {policyEvalResult && (
                <div className="project-suggestion-card" style={{ marginTop: 14 }}>
                  <div className="project-feed-title">{policyEvalResult.decision || policyEvalResult.status}</div>
                  <div className="project-feed-sub">Matched policy: {(policyEvalResult.matched_policy || policyEvalResult.evaluation?.matched_policy) || 'none'}</div>
                  <div className="project-feed-sub">Escalation: {(policyEvalResult.escalation || policyEvalResult.evaluation?.escalation) || 'none'}</div>
                  <div className="project-feed-sub">Execution mode: {(policyEvalResult.execution_mode || policyEvalResult.evaluation?.execution_mode) || '-'}</div>
                  {policyEvalResult.approval && <div className="project-feed-sub">Approval queued: {policyEvalResult.approval.approval_level} · {policyEvalResult.approval.id.slice(0, 8)}</div>}
                </div>
              )}
            </div>

            <div className="settings-card">
              <h3>Policy Versions</h3>
              <div className="project-feed">
                {policyVersions.length === 0 && <div className="project-feed-empty">No version history yet.</div>}
                {policyVersions.slice(0, 6).map((item) => (
                  <div key={item.id} className="project-feed-row">
                    <div>
                      <div className="project-feed-title">v{item.version_number} · {item.snapshot?.policy_name || item.snapshot?.policy_code}</div>
                      <div className="project-feed-sub">{item.change_note || 'Policy updated'} · {formatDate(item.created_at)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'audit' && (
        <div className="governance-layout">
          <div className="governance-panel">
            <div className="section-title">Audit Trail</div>
            <div className="project-feed">
              {auditLogs.map((item) => (
                <div key={item.id} className="project-feed-row">
                  <div>
                    <div className="project-feed-title">{item.action}</div>
                    <div className="project-feed-sub">{item.actor_type}:{item.actor_id} · {item.resource_type} · {formatDate(item.created_at)}</div>
                  </div>
                  <span className={`badge ${item.status === 'success' ? 'success' : item.status === 'blocked' ? 'failed' : 'pending'}`}>{item.status}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="governance-side">
            <div className="settings-card">
              <h3>Policy Simulations</h3>
              <div className="project-feed">
                {simulations.length === 0 && <div className="project-feed-empty">No simulations yet.</div>}
                {simulations.map((item) => (
                  <div key={item.id} className="project-feed-row">
                    <div>
                      <div className="project-feed-title">{item.action}</div>
                      <div className="project-feed-sub">{item.actor_role || item.actor_type} · {item.department_id || 'n/a'} · {formatDate(item.created_at)}</div>
                    </div>
                    <span className={`badge ${item.result?.decision === 'deny' || item.result?.decision?.includes('approval') ? 'pending' : 'success'}`}>
                      {item.result?.decision || 'allow'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

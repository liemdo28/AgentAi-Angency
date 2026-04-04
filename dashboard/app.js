// ========================================
// Agency Command Center - Dashboard App
// ========================================

// API Configuration - Update these URLs for your environment
const API_CONFIG = {
  // Unified Dashboard API (recommended - aggregates all data)
  unified: {
    baseUrl: 'http://localhost:8001',  // Unified API hub
    timeout: 10000
  },
  // Individual APIs (fallback)
  agency: {
    baseUrl: 'http://localhost:8000',
    timeout: 5000
  },
};

// Project definitions
const PROJECTS = [
  {
    id: 'agentai-agency',
    name: 'AgentAI Agency',
    description: 'AI-powered agency brain - manages all departments and workflows',
    status: 'unknown',
    stores: [],
    tags: ['AI', 'Automation', 'Internal'],
    apiEndpoint: '/status',
    apiTasksEndpoint: '/tasks',
    lastUpdated: null,
    metrics: {
      departments: 11,
      activeTasks: 0,
      pendingHandoffs: 0,
      avgScore: 0,
      passRate: 0
    }
  },
  {
    id: 'dashboard-taskflow',
    name: 'Dashboard TaskFlow',
    description: 'Task management system for internal team (PHP/MySQL)',
    status: 'unknown',
    stores: ['Team'],
    tags: ['Task', 'Team', 'PHP'],
    apiEndpoint: null,
    lastUpdated: null,
    metrics: {
      totalTasks: 0,
      completedToday: 0,
      overdueTasks: 0,
      teamMembers: 0
    }
  },
  {
    id: 'marketing',
    name: 'Marketing & Growth',
    description: 'Campaign analytics + branch sales data (marketing.bakudanramen.com)',
    status: 'unknown',
    stores: ['B1 - THE RIM', 'B2 - STONE OAK', 'B3 - BANDERA'],
    tags: ['Analytics', 'Marketing', 'Sales'],
    apiEndpoint: null,
    lastUpdated: null,
    metrics: {
      totalRevenue: 0,
      roas: 0,
      activeCampaigns: 0,
      branchesLoaded: 0
    }
  },
  {
    id: 'review-management',
    name: 'Review Management MCP',
    description: 'Google & Yelp auto-reply (Bakudan + Raw Sushi)',
    status: 'unknown',
    stores: ['Bakudan', 'Raw Sushi'],
    tags: ['Reviews', 'Automation', 'MCP'],
    apiEndpoint: null,
    lastUpdated: null,
    metrics: {
      googleReviews: 0,
      yelpReviews: 0,
      responsesSent: 0,
      lastChecked: null
    }
  },
  {
    id: 'integration-full',
    name: 'Integration Full (Toast-QB)',
    description: 'ToastPOS ↔ QuickBooks sync (Bakudan, Raw, Copper, IFT)',
    status: 'unknown',
    stores: ['Bakudan', 'Raw', 'Copper', 'IFT'],
    tags: ['POS', 'Sync', 'Finance'],
    apiEndpoint: null,
    lastUpdated: null,
    metrics: {
      lastSync: null,
      ordersSynced: 0,
      errors: 0,
      syncStatus: 'unknown'
    }
  }
];

// Store definitions
const STORES = [
  {
    id: 'B1',
    name: 'Bakudan 1 - THE RIM',
    location: 'San Antonio, TX',
    storeGroup: 'Bakudan',
    status: 'unknown',
    metrics: { revenue: 0, orders: 0, roas: 0, reviews: 0 }
  },
  {
    id: 'B2',
    name: 'Bakudan 2 - STONE OAK',
    location: 'San Antonio, TX',
    storeGroup: 'Bakudan',
    status: 'unknown',
    metrics: { revenue: 0, orders: 0, roas: 0, reviews: 0 }
  },
  {
    id: 'B3',
    name: 'Bakudan 3 - BANDERA',
    location: 'San Antonio, TX',
    storeGroup: 'Bakudan',
    status: 'unknown',
    metrics: { revenue: 0, orders: 0, roas: 0, reviews: 0 }
  },
  {
    id: 'RAW',
    name: 'Raw Sushi - Stockton',
    location: 'Stockton, CA',
    storeGroup: 'Raw Sushi',
    status: 'unknown',
    metrics: { revenue: 0, orders: 0, roas: 0, reviews: 0 }
  },
  {
    id: 'COPPER',
    name: 'Copper',
    location: 'San Antonio, TX',
    storeGroup: 'Other',
    status: 'unknown',
    metrics: { revenue: 0, orders: 0, roas: 0, reviews: 0 }
  },
  {
    id: 'IFT',
    name: 'IFT',
    location: 'Texas',
    storeGroup: 'Other',
    status: 'unknown',
    metrics: { revenue: 0, orders: 0, roas: 0, reviews: 0 }
  }
];

// Activity log
const activities = [];

// State
let currentFilter = 'all';
let currentStoreFilter = 'all';
let apiErrors = {};

// Time
function initTime() {
  updateTime();
  setInterval(updateTime, 1000);
}

function updateTime() {
  const now = new Date();
  const timeEl = document.getElementById('current-time');
  const dateEl = document.getElementById('current-date');

  if (timeEl) {
    timeEl.textContent = now.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  }

  if (dateEl) {
    dateEl.textContent = now.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  }
}

// Navigation
function initNavigation() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const view = item.dataset.view;

      // Update active state
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');

      // Switch tab content
      switchTab(view);

      // Update page title
      const pageTitle = document.querySelector('.page-title');
      const pageSubtitle = document.querySelector('.page-subtitle');

      const titles = {
        'overview': { title: 'Overview', subtitle: 'Real-time status across all projects and stores' },
        'projects': { title: 'Projects', subtitle: 'Detailed status and metrics for each project' },
        'analytics': { title: 'Analytics', subtitle: 'Performance insights and trends' },
        'stores': { title: 'Stores', subtitle: 'All store locations and their status' },
        'team': { title: 'Team', subtitle: 'Team performance and assignments' },
        'actions': { title: 'Action Center', subtitle: 'Run actions and manage jobs across all projects' },
        'settings': { title: 'Settings', subtitle: 'Configure integrations and API tokens' }
      };

      const info = titles[view] || { title: view.charAt(0).toUpperCase() + view.slice(1), subtitle: '' };

      if (pageTitle) pageTitle.textContent = info.title;
      if (pageSubtitle) pageSubtitle.textContent = info.subtitle;
    });
  });
}

// Tab switching
function switchTab(view) {
  // Hide all sections
  document.querySelectorAll('.main-content > section').forEach(s => {
    if (!s.classList.contains('stats-grid')) s.style.display = 'none';
  });

  // Show relevant sections
  const tabMap = {
    'overview': ['overview', 'stores', 'jobs', 'logs'].map(id => document.getElementById('tab-' + id) || document.querySelector(`[id$="-section"]`)),
    'projects': [],
    'analytics': [],
    'stores': [],
    'team': [],
    'actions': ['jobs', 'logs'],
    'settings': [],
  };

  // Always show overview sections on overview
  if (view === 'overview') {
    document.querySelectorAll('.main-content > section').forEach(s => {
      if (s.id && s.id.startsWith('tab-')) {
        s.style.display = s.id === 'tab-jobs' || s.id === 'tab-logs' ? 'none' : 'block';
      }
    });
  }

  // Show jobs + logs on actions tab
  if (view === 'actions') {
    const jobsTab = document.getElementById('tab-jobs');
    const logsTab = document.getElementById('tab-logs');
    if (jobsTab) jobsTab.style.display = 'block';
    if (logsTab) logsTab.style.display = 'block';
    loadJobs();
    loadLogs();
  }

  // Show specific tab content
  if (view === 'analytics') {
    const tab = document.getElementById('tab-analytics');
    if (tab) tab.style.display = 'block';
  }
  if (view === 'team') {
    const tab = document.getElementById('tab-team');
    if (tab) tab.style.display = 'block';
  }
  if (view === 'settings') {
    const tab = document.getElementById('tab-settings');
    if (tab) tab.style.display = 'block';
  }
}

// Filters
function initFilters() {
  document.querySelectorAll('.filter-tab[data-filter]').forEach(tab => {
    tab.addEventListener('click', () => {
      currentFilter = tab.dataset.filter;
      document.querySelectorAll('.filter-tab[data-filter]').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      renderProjects();
    });
  });

  document.querySelectorAll('.filter-tab[data-store]').forEach(tab => {
    tab.addEventListener('click', () => {
      currentStoreFilter = tab.dataset.store;
      document.querySelectorAll('.filter-tab[data-store]').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      renderStores();
    });
  });
}

// Load data from various sources
async function loadData() {
  // Try unified API first
  const unifiedData = await loadUnifiedData();

  if (unifiedData) {
    // Use unified API data
    updateFromUnifiedData(unifiedData);
    addActivity('success', 'Unified API', 'Connected - all projects loaded');
  } else {
    // Fallback to individual APIs
    await Promise.allSettled([
      loadAgencyStatus(),
      loadTaskFlowStatus(),
      loadGrowthDashboard(),
      loadReviewStatus(),
      loadIntegrationStatus()
    ]);
  }

  renderProjects();
  renderStores();
  updateStats();
  renderActivity();
}

// Load from unified API
async function loadUnifiedData() {
  try {
    const res = await fetchWithTimeout(`${API_CONFIG.unified.baseUrl}/overview`, {}, 5000);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn('Unified API not available:', e.message);
  }
  return null;
}

// Update project data from unified API
function updateFromUnifiedData(data) {
  if (!data || !data.projects) return;

  // Update projects
  data.projects.forEach(p => {
    const project = PROJECTS.find(proj => proj.id === p.id);
    if (project) {
      project.status = p.status || 'unknown';
      project.lastUpdated = new Date();
      project.metrics = { ...project.metrics, ...p.metrics };
    }
  });

  // Update stores
  if (data.stores) {
    data.stores.forEach(s => {
      const store = STORES.find(st => st.id === s.id);
      if (store) {
        store.status = s.status || 'unknown';
      }
    });
  }

  // Update alerts
  if (data.alerts) {
    data.alerts.forEach(alert => {
      addActivity(alert.severity === 'error' ? 'error' :
                  alert.severity === 'warning' ? 'warning' : 'info',
                  alert.title, alert.description);
    });
  }
}

// Helper: fetch with timeout
async function fetchWithTimeout(url, options = {}, timeout = 5000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}

// Load agency status from FastAPI
async function loadAgencyStatus() {
  const project = PROJECTS.find(p => p.id === 'agentai-agency');
  const baseUrl = API_CONFIG.agency.baseUrl;

  try {
    // Try to fetch status
    const statusRes = await fetchWithTimeout(`${baseUrl}/status`, {}, 3000);

    if (statusRes.ok) {
      const statusData = await statusRes.json();

      // Try to fetch tasks count
      let activeTasks = 0;
      try {
        const tasksRes = await fetchWithTimeout(`${baseUrl}/tasks`, {}, 3000);
        if (tasksRes.ok) {
          const tasksData = await tasksRes.json();
          activeTasks = Array.isArray(tasksData) ? tasksData.filter(t =>
            !['passed', 'done', 'failed', 'cancelled'].includes(t.status)
          ).length : 0;
        }
      } catch {}

      project.status = 'online';
      project.lastUpdated = new Date();
      project.metrics.activeTasks = activeTasks;
      project.metrics.pendingHandoffs = statusData.pending || statusData.draft || 0;
      project.metrics.avgScore = statusData.avg_score || 0;
      project.metrics.passRate = statusData.pass_rate || 0;

      addActivity('success', 'AgentAI Agency', `Connected - ${activeTasks} active tasks`);
    } else {
      project.status = 'warning';
      project.lastUpdated = new Date();
      addActivity('warning', 'AgentAI Agency', `API returned ${statusRes.status}`);
    }
  } catch (e) {
    project.status = 'offline';
    project.lastUpdated = new Date();
    apiErrors['agentai-agency'] = e.message;
    addActivity('error', 'AgentAI Agency', `Cannot connect - ${e.message}`);
  }
}

// Load taskflow status
async function loadTaskFlowStatus() {
  const project = PROJECTS.find(p => p.id === 'dashboard-taskflow');

  try {
    // Try to fetch from DreamHost API
    const res = await fetchWithTimeout('https://dashboard.bakudanramen.com/api/stats', {}, 5000);
    if (res.ok) {
      const data = await res.json();
      project.status = 'online';
      project.metrics.totalTasks = data.total || 0;
      project.metrics.completedToday = data.completed_today || 0;
      project.metrics.overdueTasks = data.overdue || 0;
      project.metrics.teamMembers = data.users || 0;
      addActivity('success', 'TaskFlow Dashboard', 'Connected to DreamHost');
    } else {
      // Use fallback - try to check if site is up
      project.status = 'warning';
      addActivity('warning', 'TaskFlow Dashboard', 'Using fallback data');
    }
  } catch (e) {
    project.status = 'offline';
    apiErrors['dashboard-taskflow'] = e.message;
  }

  // Always set lastUpdated
  project.lastUpdated = new Date();

  // Fallback data if no API
  if (project.status === 'offline' || project.status === 'warning') {
    project.metrics.totalTasks = project.metrics.totalTasks || 0;
    project.metrics.completedToday = project.metrics.completedToday || 0;
    project.metrics.overdueTasks = project.metrics.overdueTasks || 0;
  }
}

// Load marketing + growth dashboard data (via unified API)
async function loadMarketingGrowth() {
  const project = PROJECTS.find(p => p.id === 'marketing');

  try {
    const res = await fetchWithTimeout('/api/branch-state.php', {}, 5000);
    if (res.ok) {
      const data = await res.json();

      let totalRev = 0;
      let branchesLoaded = 0;

      if (data.branches && Array.isArray(data.branches)) {
        data.branches.forEach(branch => {
          if (branch.state && branch.state.salesRows) {
            branchesLoaded++;
            const revenue = branch.state.salesRows.reduce((sum, row) => {
              return sum + (parseFloat(row.revenue) || 0);
            }, 0);
            totalRev += revenue;
          }
        });
      }

      project.status = 'online';
      project.metrics.totalRevenue = totalRev;
      project.metrics.branchesLoaded = branchesLoaded;
      project.lastUpdated = new Date();

      addActivity('info', 'Marketing & Growth', `${branchesLoaded} branches loaded`);
    } else {
      project.status = 'warning';
    }
  } catch (e) {
    project.status = 'warning';
    project.metrics.branchesLoaded = 0;
    project.metrics.totalRevenue = 0;
  }

  project.lastUpdated = project.lastUpdated || new Date();
}

// Load review management status
async function loadReviewStatus() {
  const project = PROJECTS.find(p => p.id === 'review-management');

  try {
    // Try to check logs or state file
    const res = await fetchWithTimeout('../../review-management-mcp/logs/last-run.txt', {}, 3000);
    if (res.ok) {
      const text = await res.text();
      project.status = 'online';
      project.metrics.lastChecked = new Date(text.trim());

      // Try to read pending reviews
      const pendingRes = await fetch('../../review-management-mcp/logs/pending-reviews.md', {});
      if (pendingRes.ok) {
        const pending = await pendingRes.text();
        project.metrics.googleReviews = (pending.match(/Google/g) || []).length;
        project.metrics.yelpReviews = (pending.match(/Yelp/g) || []).length;
      }

      addActivity('success', 'Review MCP', 'Auto-replies running');
    }
  } catch (e) {
    // MCP might not be running - check if it's installed
    project.status = 'warning';
    apiErrors['review-management'] = e.message;
  }

  project.lastUpdated = new Date();
}

// Load integration status
async function loadIntegrationStatus() {
  const project = PROJECTS.find(p => p.id === 'integration-full');

  try {
    // Check for local sync state
    // In production, this would check QuickBooks logs or API
    project.status = 'warning';
    project.metrics.syncStatus = 'Needs verification';
    project.metrics.lastSync = new Date(Date.now() - 86400000); // 1 day ago
    project.metrics.ordersSynced = 0;
    project.metrics.errors = 0;
    project.lastUpdated = new Date();

    addActivity('warning', 'Integration Toast-QB', 'Requires manual verification');
  } catch (e) {
    project.status = 'offline';
    apiErrors['integration-full'] = e.message;
    project.lastUpdated = new Date();
  }
}

// Render projects
function renderProjects() {
  const grid = document.getElementById('projects-grid');
  if (!grid) return;

  let filteredProjects = PROJECTS;

  if (currentFilter === 'active') {
    filteredProjects = PROJECTS.filter(p => p.status === 'online');
  } else if (currentFilter === 'warning') {
    filteredProjects = PROJECTS.filter(p => p.status === 'warning');
  } else if (currentFilter === 'offline') {
    filteredProjects = PROJECTS.filter(p => p.status === 'offline' || p.status === 'error');
  }

  grid.innerHTML = filteredProjects.map(project => `
    <div class="project-card" onclick="openProjectModal('${project.id}')">
      <div class="project-card-header">
        <div class="project-info">
          <div class="project-name">${project.name}</div>
          <div class="project-desc">${project.description}</div>
        </div>
        <div class="project-status ${project.status}">
          <span class="status-dot ${project.status === 'online' ? '' : project.status}"></span>
          ${project.status.charAt(0).toUpperCase() + project.status.slice(1)}
        </div>
      </div>

      <div class="project-metrics">
        ${renderProjectMetrics(project)}
      </div>

      <div class="project-footer">
        <div class="project-tags">
          ${project.tags.map(tag => `<span class="project-tag">${tag}</span>`).join('')}
          ${project.stores.map(store => `<span class="project-tag">${store}</span>`).join('')}
        </div>
        <div class="project-last-updated">
          ${project.lastUpdated ? formatRelativeTime(project.lastUpdated) : 'Never'}
        </div>
      </div>
    </div>
  `).join('');
}

// Render project metrics based on type
function renderProjectMetrics(project) {
  const s = project.metrics;
  const statusColor = project.status === 'offline' ? 'var(--status-error)' :
                      project.status === 'warning' ? 'var(--status-warning)' : 'inherit';

  switch (project.id) {
    case 'agentai-agency':
      return `
        <div class="metric">
          <div class="metric-value">${s.departments || 11}</div>
          <div class="metric-label">Departments</div>
        </div>
        <div class="metric">
          <div class="metric-value" style="color: ${statusColor}">${s.activeTasks || 0}</div>
          <div class="metric-label">Active Tasks</div>
        </div>
        <div class="metric">
          <div class="metric-value">${s.pendingHandoffs || 0}</div>
          <div class="metric-label">Pending Handoffs</div>
        </div>
        <div class="metric">
          <div class="metric-value">${s.passRate || 0}%</div>
          <div class="metric-label">Pass Rate</div>
        </div>
      `;
    case 'dashboard-taskflow':
      return `
        <div class="metric">
          <div class="metric-value">${s.totalTasks || 0}</div>
          <div class="metric-label">Total Tasks</div>
        </div>
        <div class="metric">
          <div class="metric-value" style="color: var(--status-online)">${s.completedToday || 0}</div>
          <div class="metric-label">Done Today</div>
        </div>
        <div class="metric">
          <div class="metric-value" style="color: ${s.overdueTasks > 0 ? 'var(--status-warning)' : 'inherit'}">${s.overdueTasks || 0}</div>
          <div class="metric-label">Overdue</div>
        </div>
        <div class="metric">
          <div class="metric-value">${s.teamMembers || 0}</div>
          <div class="metric-label">Team Members</div>
        </div>
      `;
    case 'marketing':
      return `
        <div class="metric">
          <div class="metric-value">$${formatNumber(s.totalRevenue || 0)}</div>
          <div class="metric-label">Revenue (7D)</div>
        </div>
        <div class="metric">
          <div class="metric-value">${s.roas || 0}x</div>
          <div class="metric-label">Avg ROAS</div>
        </div>
        <div class="metric">
          <div class="metric-value">${s.activeCampaigns || 0}</div>
          <div class="metric-label">Campaigns</div>
        </div>
        <div class="metric">
          <div class="metric-value">${s.branchesLoaded || 0}/3</div>
          <div class="metric-label">Branches Loaded</div>
        </div>
      `;
    case 'review-management':
      return `
        <div class="metric">
          <div class="metric-value">${s.googleReviews || 0}</div>
          <div class="metric-label">Google Reviews</div>
        </div>
        <div class="metric">
          <div class="metric-value">${s.yelpReviews || 0}</div>
          <div class="metric-label">Yelp Reviews</div>
        </div>
        <div class="metric">
          <div class="metric-value" style="color: var(--status-online)">${s.responsesSent || 0}</div>
          <div class="metric-label">AI Responses</div>
        </div>
        <div class="metric">
          <div class="metric-value">${s.lastChecked ? formatRelativeTime(s.lastChecked) : 'N/A'}</div>
          <div class="metric-label">Last Checked</div>
        </div>
      `;
    case 'integration-full':
      const syncStatusColor = s.errors > 0 ? 'var(--status-warning)' :
                              s.syncStatus === 'healthy' ? 'var(--status-online)' : 'inherit';
      return `
        <div class="metric">
          <div class="metric-value">${s.ordersSynced ? formatNumber(s.ordersSynced) : 0}</div>
          <div class="metric-label">Orders Synced</div>
        </div>
        <div class="metric">
          <div class="metric-value" style="color: ${syncStatusColor}">${s.errors || 0}</div>
          <div class="metric-label">Errors</div>
        </div>
        <div class="metric">
          <div class="metric-value">${s.lastSync ? formatRelativeTime(s.lastSync) : 'Never'}</div>
          <div class="metric-label">Last Sync</div>
        </div>
        <div class="metric">
          <div class="metric-value">${s.syncStatus || 'Unknown'}</div>
          <div class="metric-label">Status</div>
        </div>
      `;
    default:
      return '';
  }
}

// Render stores
function renderStores() {
  const grid = document.getElementById('stores-grid');
  if (!grid) return;

  let filteredStores = STORES;

  if (currentStoreFilter !== 'all') {
    filteredStores = STORES.filter(s =>
      s.id === currentStoreFilter ||
      (currentStoreFilter === 'B1' && ['B1'].includes(s.id)) ||
      (currentStoreFilter === 'B2' && ['B2'].includes(s.id)) ||
      (currentStoreFilter === 'B3' && ['B3'].includes(s.id))
    );
  }

  grid.innerHTML = filteredStores.map(store => `
    <div class="store-card">
      <div class="store-header">
        <div>
          <div class="store-name">${store.name}</div>
          <div class="store-location">${store.location}</div>
        </div>
        <div class="store-status ${store.status}"></div>
      </div>
      <div class="store-metrics">
        <div class="store-metric">
          <div class="store-metric-value">$${formatNumber(store.metrics.revenue)}</div>
          <div class="store-metric-label">Revenue (7D)</div>
        </div>
        <div class="store-metric">
          <div class="store-metric-value">${store.metrics.orders}</div>
          <div class="store-metric-label">Orders</div>
        </div>
        <div class="store-metric">
          <div class="store-metric-value">${store.metrics.roas}x</div>
          <div class="store-metric-label">ROAS</div>
        </div>
        <div class="store-metric">
          <div class="store-metric-value">${store.metrics.reviews}</div>
          <div class="store-metric-label">Reviews</div>
        </div>
      </div>
    </div>
  `).join('');
}

// Update stats
function updateStats() {
  const activeProjects = PROJECTS.filter(p => p.status === 'online').length;
  const storesOnline = STORES.filter(s => s.status === 'online').length;

  // Calculate total revenue from stores
  const totalRevenue = STORES.reduce((sum, s) => sum + s.metrics.revenue, 0);

  // Calculate pending tasks
  const pendingTasks = PROJECTS.reduce((sum, p) =>
    sum + (p.metrics.activeTasks || 0) + (p.metrics.overdueTasks || 0), 0
  );

  document.getElementById('stat-projects-active').textContent = `${activeProjects}/${PROJECTS.length}`;
  document.getElementById('stat-stores-online').textContent = `${storesOnline}/${STORES.length}`;
  document.getElementById('stat-total-revenue').textContent = `$${formatNumber(totalRevenue)}`;
  document.getElementById('stat-tasks-pending').textContent = pendingTasks;
}

// Render activity
function renderActivity() {
  const feed = document.getElementById('activity-feed');
  if (!feed) return;

  if (activities.length === 0) {
    feed.innerHTML = `
      <div class="activity-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12,6 12,12 16,14"/>
        </svg>
        <p>Activity logs will appear here as events occur</p>
      </div>
    `;
    return;
  }

  feed.innerHTML = activities.slice(0, 20).map(activity => `
    <div class="activity-item">
      <div class="activity-icon ${activity.type}">
        ${getActivityIcon(activity.type)}
      </div>
      <div class="activity-content">
        <div class="activity-title">${activity.title}</div>
        <div class="activity-desc">${activity.desc}</div>
      </div>
      <div class="activity-time">${formatRelativeTime(activity.time)}</div>
    </div>
  `).join('');
}

// Add activity
function addActivity(type, title, desc) {
  activities.unshift({
    type,
    title,
    desc,
    time: new Date()
  });

  // Keep only last 50 activities
  if (activities.length > 50) {
    activities.pop();
  }

  renderActivity();
}

// Get activity icon SVG
function getActivityIcon(type) {
  switch (type) {
    case 'success':
      return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"/></svg>';
    case 'warning':
      return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
    case 'error':
      return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
    default:
      return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';
  }
}

// Open project modal
function openProjectModal(projectId) {
  const project = PROJECTS.find(p => p.id === projectId);
  if (!project) return;

  const modal = document.getElementById('project-modal');
  const title = document.getElementById('modal-title');
  const body = document.getElementById('modal-body');

  title.textContent = project.name;
  body.innerHTML = renderProjectDetail(project);

  modal.classList.add('active');
}

// Render project detail in modal
function renderProjectDetail(project) {
  // Build action buttons based on project type
  const actionButtons = getProjectActions(project.id);

  return `
    <div style="margin-bottom: 24px;">
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
        <div class="project-status ${project.status}">
          <span class="status-dot ${project.status}"></span>
          ${project.status.charAt(0).toUpperCase() + project.status.slice(1)}
        </div>
        <span style="color: var(--text-muted); font-size: 13px;">
          Last updated: ${project.lastUpdated ? formatRelativeTime(project.lastUpdated) : 'Never'}
        </span>
      </div>
      <p style="color: var(--text-secondary); line-height: 1.6;">${project.description}</p>
    </div>

    ${actionButtons.length > 0 ? `
    <h4 style="font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">QUICK ACTIONS</h4>
    <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px;">
      ${actionButtons.map(btn => {
        if (btn.requiresFile) {
          return `
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="file" id="action-file-${btn.id.replace('.','-')}" accept=".csv,.xlsx,.xls,.txt,.json,.jpg,.jpeg,.png" style="display:none;" />
          <button class="btn btn-secondary" onclick="document.getElementById('action-file-${btn.id.replace('.','-')}').click()">
            ${btn.icon} Upload File
          </button>
          <button class="btn btn-primary" onclick="handleUploadAction('${project.id}', '${btn.id}', '${btn.name}', 'action-file-${btn.id.replace('.','-')}')">
            Send
          </button>
        </div>`;
        }
        return `
        <button class="btn btn-secondary" onclick="executeAction('${project.id}', '${btn.id}', '${btn.name}')">
          ${btn.icon} ${btn.name}
        </button>`;
      }).join('')}
    </div>
    ` : ''}

    <h4 style="font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">METRICS</h4>
    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 24px;">
      ${renderProjectMetrics(project)}
    </div>

    <h4 style="font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">STORES</h4>
    <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px;">
      ${project.stores.map(store => `<span class="project-tag" style="padding: 6px 12px;">${store}</span>`).join('')}
    </div>

    <h4 style="font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">TAGS</h4>
    <div style="display: flex; flex-wrap: wrap; gap: 8px;">
      ${project.tags.map(tag => `<span class="project-tag">${tag}</span>`).join('')}
    </div>

    <div style="margin-top: 24px; display: flex; gap: 12px;">
      <button class="btn btn-secondary" onclick="closeModal()">Close</button>
      <button class="btn btn-primary" onclick="viewAllActions('${project.id}')">
        All Actions
      </button>
    </div>
  `;
}

// Get quick actions for each project type
function getProjectActions(projectId) {
  const icons = {
    sync: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23,4 23,10 17,10"/><polyline points="1,20 1,14 7,14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>',
    refresh: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23,4 23,10 17,10"/><polyline points="1,20 1,14 7,14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>',
    health: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
    tasks: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9,11 12,14 22,4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
    review: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/></svg>',
    upload: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17,8 12,3 7,8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
  };

  const actions = {
    'agentai-agency': [
      { id: 'agency.refresh', name: 'Refresh' },
      { id: 'agency.tasks', name: 'Tasks' },
      { id: 'agency.handoffs', name: 'Handoffs' },
    ],
    'dashboard-taskflow': [
      { id: 'taskflow.fetch_stats', name: 'Fetch Stats' },
      { id: 'taskflow.list_tasks', name: 'List Tasks' },
      { id: 'taskflow.sync_team', name: 'Sync Team' },
    ],
    'marketing': [
      { id: 'marketing.health', name: 'Health' },
      { id: 'marketing.branch_state', name: 'Branch Data' },
      { id: 'marketing.analytics', name: 'Analytics' },
      { id: 'marketing.sync_campaigns', name: 'Sync Campaigns' },
    ],
    'review-management': [
      { id: 'reviews.refresh', name: 'Check Reviews' },
      { id: 'reviews.list_pending', name: 'Pending' },
      { id: 'reviews.responses', name: 'Responses' },
    ],
    'integration-full': [
      { id: 'integration.sync', name: 'Sync Now' },
      { id: 'integration.verify', name: 'Verify' },
      { id: 'integration.export', name: 'Export' },
    ],
    'marketing': [
      { id: 'marketing.upload', name: 'Upload File', requiresFile: true },
      { id: 'marketing.health', name: 'Health' },
      { id: 'marketing.sync_campaigns', name: 'Sync' },
      { id: 'marketing.pull_report', name: 'Report' },
    ],
  };

  const projectActions = actions[projectId] || [];
  return projectActions.map(a => ({
    ...a,
    icon: icons[a.id.split('.')[1]] || icons.refresh,
  }));
}

// Navigate to all actions view
function viewAllActions(projectId) {
  closeModal();
  // Switch to actions tab
  document.querySelectorAll('.nav-item').forEach(i => {
    if (i.dataset.view === 'actions') {
      i.click();
    }
  });
}

// Navigate to project
function navigateToProject(projectId) {
  const paths = {
    'agentai-agency': '../../',
    'dashboard-taskflow': 'https://dashboard.bakudanramen.com',
    'marketing': 'https://marketing.bakudanramen.com',
    'review-management': '../../review-management-mcp/',
    'integration-full': '../../integration-full/desktop-app/'
  };

  const path = paths[projectId];
  if (path) {
    // For local paths, just show a message
    addActivity('info', 'Navigation', `Opening ${projectId}...`);
  }
  closeModal();
}

// Close modal
function closeModal(event) {
  if (event && event.target !== event.currentTarget) return;
  document.getElementById('project-modal').classList.remove('active');
}

// Refresh all
async function refreshAll() {
  addActivity('info', 'Refresh', 'Updating all project statuses...');

  // Try to force refresh unified API
  try {
    await fetchWithTimeout(`${API_CONFIG.unified.baseUrl}/refresh`, {
      method: 'POST'
    }, 5000);
  } catch (e) {
    console.warn('Unified API refresh failed:', e.message);
  }

  await loadData();
  addActivity('success', 'Refresh', 'All project statuses updated');
}

// Utility functions
function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}

function formatRelativeTime(date) {
  if (!date) return 'Never';

  const now = new Date();
  const diff = now - date;
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (seconds < 60) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return date.toLocaleDateString();
}


// ========================================
// Action Center - Job Queue & Actions
// ========================================

let currentJobFilter = 'all';

// Load jobs from unified API
async function loadJobs() {
  const grid = document.getElementById('jobs-grid');
  if (!grid) return;

  try {
    const statusFilter = currentJobFilter !== 'all' ? `?status=${currentJobFilter}` : '';
    const res = await fetchWithTimeout(`${API_CONFIG.unified.baseUrl}/jobs${statusFilter}`, {}, 5000);

    if (res.ok) {
      const data = await res.json();
      renderJobs(data.jobs || []);
    } else {
      renderJobsEmpty('Failed to load jobs');
    }
  } catch (e) {
    renderJobsEmpty('Unified API not available');
  }
}

// Render jobs list
function renderJobs(jobs) {
  const grid = document.getElementById('jobs-grid');
  if (!grid) return;

  if (jobs.length === 0) {
    grid.innerHTML = `
      <div class="activity-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <polygon points="13,2 3,14 12,14 11,22 21,10 12,10 13,2"/>
        </svg>
        <p>No jobs found. Run an action from a project card.</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = jobs.map(job => `
    <div class="job-card" data-job-id="${job.id}">
      <div class="job-header">
        <div class="job-status ${job.status}">
          <span class="status-dot ${job.status === 'success' ? '' : job.status}"></span>
          ${job.status.toUpperCase()}
        </div>
        <span class="job-time">${formatRelativeTime(new Date(job.requested_at))}</span>
      </div>
      <div class="job-info">
        <span class="job-project">${job.project_id}</span>
        <span class="job-action">${job.action_id}</span>
      </div>
      ${job.error_message ? `<div class="job-error">${job.error_message}</div>` : ''}
      ${job.status === 'running' ? `
        <div class="job-progress">
          <div class="progress-bar"></div>
        </div>
      ` : ''}
      <div class="job-footer">
        <span class="job-duration">${job.duration_ms ? (job.duration_ms / 1000).toFixed(1) + 's' : '-'}</span>
        <button class="btn btn-secondary" onclick="openJobDetail('${job.id}')">View</button>
      </div>
    </div>
  `).join('');
}

function renderJobsEmpty(msg) {
  const grid = document.getElementById('jobs-grid');
  if (!grid) return;
  grid.innerHTML = `
    <div class="activity-empty">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
        <polygon points="13,2 3,14 12,14 11,22 21,10 12,10 13,2"/>
      </svg>
      <p>${msg}</p>
    </div>
  `;
}

// Open job detail modal
async function openJobDetail(jobId) {
  try {
    const res = await fetchWithTimeout(`${API_CONFIG.unified.baseUrl}/jobs/${jobId}`, {}, 5000);
    if (res.ok) {
      const data = await res.json();
      showJobModal(data.job, data.logs || []);
    }
  } catch (e) {
    addActivity('error', 'Job Detail', `Failed to load: ${e.message}`);
  }
}

// Show job detail in modal
function showJobModal(job, logs) {
  const modal = document.getElementById('project-modal');
  const title = document.getElementById('modal-title');
  const body = document.getElementById('modal-body');

  title.textContent = `Job: ${job.action_id}`;
  body.innerHTML = `
    <div style="margin-bottom:24px;">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
        <div class="project-status ${job.status}">
          <span class="status-dot ${job.status}"></span>
          ${job.status.toUpperCase()}
        </div>
        <span style="color:var(--text-muted);font-size:13px;">
          ${job.duration_ms ? 'Duration: ' + (job.duration_ms/1000).toFixed(1) + 's' : 'In progress...'}
        </span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px;">
        <div class="metric"><div class="metric-value">${job.project_id}</div><div class="metric-label">Project</div></div>
        <div class="metric"><div class="metric-value">${job.action_id}</div><div class="metric-label">Action</div></div>
        <div class="metric"><div class="metric-value">${job.requested_by}</div><div class="metric-label">Requested By</div></div>
        <div class="metric"><div class="metric-value">${job.retry_count}/${job.max_retries}</div><div class="metric-label">Retries</div></div>
      </div>
      ${job.error_message ? `<div style="background:var(--status-error-bg);border:1px solid var(--status-error);border-radius:8px;padding:12px;margin-bottom:16px;color:var(--status-error);font-size:13px;">${job.error_message}</div>` : ''}
      ${job.result && job.result.data ? `<div style="background:var(--bg-tertiary);border-radius:8px;padding:12px;margin-bottom:16px;"><pre style="font-size:12px;color:var(--text-secondary);margin:0;white-space:pre-wrap;">${JSON.stringify(job.result.data, null, 2)}</pre></div>` : ''}
    </div>
    <h4 style="font-size:14px;font-weight:600;margin-bottom:12px;color:var(--text-secondary);">LOGS</h4>
    <div style="max-height:300px;overflow-y:auto;background:var(--bg-tertiary);border-radius:8px;padding:12px;">
      ${logs.length === 0 ? '<p style="color:var(--text-muted);font-size:13px;">No logs</p>' :
        logs.map(log => `
          <div style="display:flex;gap:12px;padding:8px 0;border-bottom:1px solid var(--border-primary);font-size:12px;">
            <span style="color:var(--text-muted);font-family:var(--font-mono);min-width:60px;">${log.level.toUpperCase()}</span>
            <span style="color:var(--text-secondary);flex:1;">${log.message}</span>
            <span style="color:var(--text-muted);">${formatRelativeTime(new Date(log.created_at))}</span>
          </div>
        `).join('')}
    </div>
    <div style="margin-top:20px;display:flex;gap:12px;">
      <button class="btn btn-secondary" onclick="closeModal()">Close</button>
      ${['pending', 'retrying'].includes(job.status) ? `<button class="btn btn-primary" onclick="runJob('${job.id}')">Run Now</button>` : ''}
      ${['pending', 'retrying'].includes(job.status) ? `<button class="btn btn-secondary" onclick="cancelJob('${job.id}')" style="color:var(--status-error);">Cancel</button>` : ''}
    </div>
  `;

  modal.classList.add('active');
}

// Handle file upload action: validate file, then submit with FormData
async function handleUploadAction(projectId, actionId, actionName, fileInputId) {
  const fileInput = document.getElementById(fileInputId);
  const file = fileInput?.files?.[0];

  if (!file) {
    addActivity('warning', 'Upload', 'Please select a file first');
    return;
  }

  addActivity('info', 'Upload', `Uploading ${file.name} to ${actionName}...`);

  const formData = new FormData();
  formData.append('file', file, file.name);

  try {
    const url = `${API_CONFIG.unified.baseUrl}/projects/${projectId}/actions/${actionId}`;
    const res = await fetchWithTimeout(url, {
      method: 'POST',
      body: formData,
    }, 120000);

    if (res.ok) {
      const data = await res.json();
      addActivity('success', 'Upload', `${file.name} queued (Job: ${data.job_id})`);
      closeModal();
      // Switch to actions tab to see job progress
      document.querySelectorAll('.nav-item').forEach(i => {
        if (i.dataset.view === 'actions') i.click();
      });
    } else {
      const err = await res.json().catch(() => ({}));
      addActivity('error', 'Upload', `Failed: ${err.detail || res.statusText}`);
    }
  } catch (e) {
    addActivity('error', 'Upload', `Upload failed: ${e.message}`);
  }
}

// Execute action from project card (optionally with file upload)
async function executeAction(projectId, actionId, actionName, fileInputEl) {
  addActivity('info', 'Action', `Running ${actionName} on ${projectId}...`);

  try {
    let url = `${API_CONFIG.unified.baseUrl}/projects/${projectId}/actions/${actionId}`;
    let options = { method: 'POST' };

    // Check if this action requires a file
    const fileActionIds = ['marketing.upload'];
    const needsFile = fileActionIds.includes(actionId);
    const file = fileInputEl?.files?.[0];

    if (needsFile || file) {
      // Use FormData for file upload
      const formData = new FormData();
      if (file) formData.append('file', file, file.name);
      options = {
        method: 'POST',
        body: formData,
        // Don't set Content-Type — browser sets it with boundary
      };
    }

    const res = await fetchWithTimeout(url, options, 60000);

    if (res.ok) {
      const data = await res.json();
      addActivity('success', 'Action', `${actionName} queued (Job: ${data.job_id})`);
      // Refresh jobs list if on actions tab
      if (document.querySelector('.nav-item.active')?.dataset.view === 'actions') {
        loadJobs();
        loadLogs();
      }
    } else {
      const err = await res.json().catch(() => ({}));
      addActivity('error', 'Action', `Failed: ${err.detail || res.statusText}`);
    }
  } catch (e) {
    addActivity('error', 'Action', `${actionName} failed: ${e.message}`);
  }
}

// Trigger job manually
async function runJob(jobId) {
  try {
    const res = await fetchWithTimeout(
      `${API_CONFIG.unified.baseUrl}/jobs/${jobId}/run`,
      { method: 'POST' },
      5000
    );
    if (res.ok) {
      addActivity('success', 'Job', `Job ${jobId} triggered`);
      closeModal();
      loadJobs();
    }
  } catch (e) {
    addActivity('error', 'Job', `Failed to trigger: ${e.message}`);
  }
}

// Cancel job
async function cancelJob(jobId) {
  try {
    const res = await fetchWithTimeout(
      `${API_CONFIG.unified.baseUrl}/jobs/${jobId}/cancel`,
      { method: 'POST' },
      5000
    );
    if (res.ok) {
      addActivity('warning', 'Job', `Job ${jobId} cancelled`);
      closeModal();
      loadJobs();
    }
  } catch (e) {
    addActivity('error', 'Job', `Failed to cancel: ${e.message}`);
  }
}

// Load audit logs
async function loadLogs() {
  const feed = document.getElementById('logs-feed');
  if (!feed) return;

  try {
    const res = await fetchWithTimeout(`${API_CONFIG.unified.baseUrl}/logs?limit=50`, {}, 5000);
    if (res.ok) {
      const data = await res.json();
      renderLogs(data.logs || []);
    }
  } catch (e) {
    renderLogs([]);
  }
}

function renderLogs(logs) {
  const feed = document.getElementById('logs-feed');
  if (!feed) return;

  if (logs.length === 0) {
    feed.innerHTML = `
      <div class="activity-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14,2 14,8 20,8"/>
        </svg>
        <p>No audit logs yet</p>
      </div>
    `;
    return;
  }

  feed.innerHTML = logs.map(log => `
    <div class="activity-item">
      <div class="activity-icon ${log.level === 'error' ? 'error' : log.level === 'warning' ? 'warning' : log.level === 'info' ? 'info' : 'success'}">
        ${getActivityIcon(log.level)}
      </div>
      <div class="activity-content">
        <div class="activity-title">${log.message}</div>
        ${log.job_id ? `<div class="activity-desc">Job: ${log.job_id}</div>` : ''}
      </div>
      <div class="activity-time">${formatRelativeTime(new Date(log.created_at))}</div>
    </div>
  `).join('');
}

// Job filter init
function initJobFilters() {
  document.querySelectorAll('.filter-tab[data-job-filter]').forEach(tab => {
    tab.addEventListener('click', () => {
      currentJobFilter = tab.dataset.jobFilter;
      document.querySelectorAll('.filter-tab[data-job-filter]').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      loadJobs();
    });
  });

  document.querySelectorAll('.filter-tab[data-log-filter]').forEach(tab => {
    tab.addEventListener('click', () => {
      // Future: implement log filtering
      tab.classList.add('active');
    });
  });
}

// ── Job Polling ────────────────────────────────────────────────────────────────
// Auto-refresh running/pending jobs. Fast poll when active, slow when idle.

let pollTimer = null;

async function pollJobs() {
  // Only poll if we're on the actions tab or have active jobs showing
  const isOnActionsTab = document.querySelector('.nav-item.active')?.dataset.view === 'actions';
  if (!isOnActionsTab) {
    scheduleNextPoll(30000);
    return;
  }

  try {
    const statusFilter = currentJobFilter !== 'all' ? `?status=${currentJobFilter}` : '';
    const res = await fetchWithTimeout(
      `${API_CONFIG.unified.baseUrl}/jobs${statusFilter}`,
      {}, 5000
    );

    if (res.ok) {
      const data = await res.json();
      renderJobs(data.jobs || []);

      // Adaptive poll interval: 5s if jobs are active, 20s if idle
      const hasActive = (data.jobs || []).some(j =>
        ['pending', 'running', 'retrying'].includes(j.status)
      );
      const isOnActionsTabNow = document.querySelector('.nav-item.active')?.dataset.view === 'actions';
      if (isOnActionsTabNow) {
        scheduleNextPoll(hasActive ? 5000 : 20000);
      }
    }
  } catch (e) {
    console.warn('Job polling failed:', e.message);
    scheduleNextPoll(15000);
  }
}

function scheduleNextPoll(delayMs) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(pollJobs, delayMs);
}

// Visibility API: pause polling when tab hidden, resume when visible
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    clearTimeout(pollTimer);
    pollTimer = null;
  } else {
    // Resume polling on visibility
    const isOnActionsTab = document.querySelector('.nav-item.active')?.dataset.view === 'actions';
    if (isOnActionsTab) scheduleNextPoll(2000); // poll soon after focus
  }
});

// Add init to DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
  initTime();
  initFilters();
  initNavigation();
  initJobFilters();
  loadData();
  setInterval(refreshAll, 30000);
  // Start polling
  scheduleNextPoll(3000);
});

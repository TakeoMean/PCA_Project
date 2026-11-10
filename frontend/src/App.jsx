import { useEffect, useMemo, useState } from 'react';
import { Bar } from 'react-chartjs-2';
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
} from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

const API_URL = import.meta.env.VITE_API_URL || '';
const LEVELS = ['Low', 'Moderate', 'High', 'Critical'];
const CATEGORIES = ['Cybersecurity', 'Technical', 'Operational', 'Financial', 'Human', 'Environmental', 'Supplier'];
const EMPTY_TREATMENT = {
  strategy: 'Reduce',
  treatment_plan: '',
  expected_result: '',
  resources_required: '',
  start_date: '',
  due_date: '',
};
const EMPTY_USER = {
  username: '',
  email: '',
  full_name: '',
  password: '',
  role: 'Risk Manager',
  department_id: '',
};

function App() {
  const [token, setToken] = useState(localStorage.getItem('smca_token') || '');
  const [user, setUser] = useState(null);
  const [view, setView] = useState('dashboard');
  const [dashboard, setDashboard] = useState(null);
  const [risks, setRisks] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [activities, setActivities] = useState([]);
  const [treatments, setTreatments] = useState([]);
  const [users, setUsers] = useState([]);
  const [userDirectory, setUserDirectory] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [selectedRiskId, setSelectedRiskId] = useState('');
  const [selectedRiskDepartmentId, setSelectedRiskDepartmentId] = useState('');
  const [treatmentForm, setTreatmentForm] = useState(EMPTY_TREATMENT);
  const [riskFilter, setRiskFilter] = useState({ query: '', level: 'All', category: 'All' });
  const [userForm, setUserForm] = useState(EMPTY_USER);
  const [loginForm, setLoginForm] = useState({ username: 'admin', password: 'admin123' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const permissions = user?.permissions || [];
  const can = (permission) => permissions.includes(permission);
  const canApprove = can('treatments:approve');
  const canManageTreatments = can('treatments:manage');
  const canManageUsers = can('users:manage');

  const apiFetch = async (path, options = {}) => {
    const headers = { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) };
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers,
      body: options.body && typeof options.body !== 'string' ? JSON.stringify(options.body) : options.body,
    });
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      const message = typeof payload === 'object' ? payload.detail : payload;
      throw new Error(message || `Request failed (${response.status})`);
    }
    return payload;
  };

  const refreshCore = async () => {
    const [summary, riskRows, departmentRows, activityRows, treatmentRows, logRows, directoryRows] = await Promise.all([
      apiFetch('/api/dashboard/summary'),
      apiFetch('/api/risks'),
      apiFetch('/api/departments'),
      apiFetch('/api/activities'),
      apiFetch('/api/risk-treatments'),
      can('audit:read') ? apiFetch('/api/audit-logs') : Promise.resolve([]),
      apiFetch('/api/user-directory'),
    ]);
    setDashboard(summary);
    setRisks(riskRows);
    setDepartments(departmentRows);
    setActivities(activityRows);
    setTreatments(treatmentRows);
    setAuditLogs(logRows);
    setUserDirectory(directoryRows);
  };

  const refreshUsers = async () => {
    if (!canManageUsers) return;
    const [userRows, roleRows] = await Promise.all([apiFetch('/api/users'), apiFetch('/api/roles')]);
    setUsers(userRows);
    setAvailableRoles(roleRows);
  };

  const [availableRoles, setAvailableRoles] = useState([]);

  const loadSession = async () => {
    if (!token) return;
    try {
      const currentUser = await apiFetch('/api/me');
      setUser(currentUser);
    } catch (loadError) {
      localStorage.removeItem('smca_token');
      setToken('');
      setUser(null);
      setError(loadError.message);
    }
  };

  useEffect(() => {
    loadSession();
  }, [token]);

  useEffect(() => {
    if (!user) return;
    setError('');
    Promise.all([refreshCore(), refreshUsers()]).catch((loadError) => setError(loadError.message));
  }, [user]);

  const login = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const payload = await apiFetch('/api/auth/login', {
        method: 'POST',
        body: { username: loginForm.username, password: loginForm.password },
      });
      localStorage.setItem('smca_token', payload.access_token);
      setToken(payload.access_token);
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setBusy(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('smca_token');
    setToken('');
    setUser(null);
    setDashboard(null);
    setView('dashboard');
  };

  const withFeedback = async (operation, successMessage) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await operation();
      await refreshCore();
      if (canManageUsers) await refreshUsers();
      setNotice(successMessage);
    } catch (operationError) {
      setError(operationError.message);
    } finally {
      setBusy(false);
    }
  };

  const submitRisk = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(event.currentTarget);
    const payload = Object.fromEntries(data.entries());
    payload.department_id = Number(payload.department_id);
    payload.activity_id = payload.activity_id ? Number(payload.activity_id) : null;
    payload.probability = Number(payload.probability);
    payload.impact = Number(payload.impact);
    payload.owner_id = payload.owner_id ? Number(payload.owner_id) : null;
    await withFeedback(async () => {
      await apiFetch('/api/risks', { method: 'POST', body: payload });
      form.reset();
    }, 'Risk added to the register.');
  };

  const submitTreatment = async (event) => {
    event.preventDefault();
    if (!selectedRiskId) {
      setError('Choose a risk before proposing a treatment plan.');
      return;
    }
    const body = {
      ...treatmentForm,
      start_date: treatmentForm.start_date ? new Date(treatmentForm.start_date).toISOString() : null,
      due_date: treatmentForm.due_date ? new Date(treatmentForm.due_date).toISOString() : null,
    };
    await withFeedback(async () => {
      await apiFetch(`/api/risks/${selectedRiskId}/treatments`, { method: 'POST', body });
      setTreatmentForm(EMPTY_TREATMENT);
    }, 'Treatment plan proposed. It is now waiting for review.');
  };

  const reviewTreatment = (treatmentId, decision) => withFeedback(async () => {
    const comment = window.prompt(`Add a review note for this ${decision}.`);
    if (!comment || comment.trim().length < 3) throw new Error('A review note of at least 3 characters is required.');
    await apiFetch(`/api/risk-treatments/${treatmentId}/decision`, {
      method: 'POST',
      body: { decision, comment: comment.trim() },
    });
  }, `Treatment plan ${decision === 'approve' ? 'approved' : 'rejected'}.`);

  const changeTreatmentStatus = (treatment, nextStatus) => withFeedback(async () => {
    const body = { status: nextStatus };
    if (nextStatus === 'Completed') {
      const probability = Number(window.prompt('Residual probability (1-5):'));
      const impact = Number(window.prompt('Residual impact (1-5):'));
      if (!Number.isInteger(probability) || probability < 1 || probability > 5 || !Number.isInteger(impact) || impact < 1 || impact > 5) {
        throw new Error('Enter residual probability and impact from 1 to 5.');
      }
      body.residual_probability = probability;
      body.residual_impact = impact;
    }
    await apiFetch(`/api/risk-treatments/${treatment.id}/status`, { method: 'PATCH', body });
  }, `Treatment plan marked ${nextStatus.toLowerCase()}.`);

  const submitAction = (event, treatmentId) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(event.currentTarget);
    const payload = Object.fromEntries(data.entries());
    payload.owner_id = payload.owner_id ? Number(payload.owner_id) : null;
    payload.start_date = payload.start_date ? new Date(payload.start_date).toISOString() : null;
    payload.due_date = payload.due_date ? new Date(payload.due_date).toISOString() : null;
    return withFeedback(async () => {
      await apiFetch(`/api/risk-treatments/${treatmentId}/actions`, { method: 'POST', body: payload });
      form.reset();
    }, 'Treatment action added.');
  };

  const updateAction = (actionId, status) => withFeedback(
    async () => {
      const body = { status };
      if (status === 'Completed') {
        const result = window.prompt('Record the result of this action.');
        if (!result || !result.trim()) throw new Error('An action result is required before completion.');
        body.result = result.trim();
      }
      await apiFetch(`/api/treatment-actions/${actionId}`, { method: 'PATCH', body });
    },
    `Action marked ${status.toLowerCase()}.`,
  );

  const submitUser = (event) => {
    event.preventDefault();
    const payload = {
      ...userForm,
      department_id: userForm.department_id ? Number(userForm.department_id) : null,
    };
    return withFeedback(async () => {
      await apiFetch('/api/users', { method: 'POST', body: payload });
      setUserForm(EMPTY_USER);
    }, 'User account created.');
  };

  const updateUser = (userId, changes) => withFeedback(
    () => apiFetch(`/api/users/${userId}`, { method: 'PATCH', body: changes }),
    'User access updated.',
  );

  const exportReport = async (format) => {
    try {
      const response = await fetch(`${API_URL}/api/reports/export?format=${format}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || 'Report export failed.');
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `smca-risk-report.${format === 'excel' ? 'xlsx' : 'pdf'}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (exportError) {
      setError(exportError.message);
    }
  };

  const filteredRisks = useMemo(() => risks.filter((risk) => {
    const term = riskFilter.query.trim().toLowerCase();
    return (!term || `${risk.code} ${risk.name} ${risk.department}`.toLowerCase().includes(term))
      && (riskFilter.level === 'All' || risk.level === riskFilter.level)
      && (riskFilter.category === 'All' || risk.category === riskFilter.category);
  }), [risks, riskFilter]);

  const categoryChart = useMemo(() => {
    const counts = dashboard?.breakdown || {};
    return {
      labels: Object.keys(counts),
      datasets: [{
        data: Object.values(counts),
        backgroundColor: ['#3867d6', '#20a39e', '#e4a11b', '#e66b5b', '#9b6bd3', '#48a9a6', '#65758b'],
        borderRadius: 6,
        maxBarThickness: 36,
      }],
    };
  }, [dashboard]);

  const navigation = [
    { id: 'dashboard', title: 'Overview', icon: '◫' },
    { id: 'risks', title: 'Risk register', icon: '◈' },
    { id: 'treatments', title: 'Treatment plans', icon: '✓' },
    { id: 'departments', title: 'Organisation', icon: '⌂' },
    ...(canManageUsers ? [{ id: 'users', title: 'People & access', icon: '♙' }] : []),
    ...(can('reports:read') ? [{ id: 'reports', title: 'Reports & audit', icon: '▤' }] : []),
  ];

  if (!token || !user) {
    return (
      <div className="login-screen">
        <section className="login-aside">
          <div className="brand-lockup"><span className="brand-mark">C</span><span>Continuity<span className="brand-light">OS</span></span></div>
          <div className="login-message">
            <p className="eyebrow">BUSINESS CONTINUITY · RISK INTELLIGENCE</p>
            <h1>Stay ready.<br />Keep moving.</h1>
            <p>One clear view of your organisation's resilience, risk exposure and response plans.</p>
          </div>
          <span className="login-foot">SMCA · ISO 22301 aligned workspace</span>
        </section>
        <form className="login-card" onSubmit={login}>
          <div className="brand-lockup mobile-brand"><span className="brand-mark">C</span><span>Continuity<span className="brand-light">OS</span></span></div>
          <p className="eyebrow">WELCOME BACK</p>
          <h2>Sign in to your workspace</h2>
          <p className="subtle">Use your organisation account to continue.</p>
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <label>Username<input autoComplete="username" value={loginForm.username} onChange={(event) => setLoginForm({ ...loginForm, username: event.target.value })} /></label>
          <label>Password<input type="password" autoComplete="current-password" value={loginForm.password} onChange={(event) => setLoginForm({ ...loginForm, password: event.target.value })} /></label>
          <button className="button button-primary button-wide" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          <p className="login-hint">Demo account: <strong>admin</strong> / <strong>admin123</strong></p>
        </form>
      </div>
    );
  }

  return (
    <div className="workspace">
      <aside className="sidebar">
        <div className="brand-lockup"><span className="brand-mark">C</span><span>Continuity<span className="brand-light">OS</span></span></div>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          {navigation.map((item) => (
            <button key={item.id} className={view === item.id ? 'nav-item selected' : 'nav-item'} onClick={() => setView(item.id)}>
              <span className="nav-icon">{item.icon}</span>{item.title}
              {item.id === 'treatments' && treatments.some((plan) => plan.status === 'Proposed') && <span className="nav-badge">{treatments.filter((plan) => plan.status === 'Proposed').length}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note"><span className="status-dot" />Workspace protected</div>
          <div className="profile-card">
            <div className="avatar">{user.full_name?.slice(0, 1).toUpperCase()}</div>
            <div className="profile-copy"><strong>{user.full_name}</strong><span>{user.role}</span></div>
            <button className="icon-button logout-button" title="Sign out" onClick={logout}>↗</button>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs">ContinuityOS <span>/</span> {navigation.find((item) => item.id === view)?.title || 'Workspace'}</div>
          <div className="topbar-right">
            <span className="today-label">{new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</span>
            <div className="avatar avatar-small">{user.full_name?.slice(0, 1).toUpperCase()}</div>
          </div>
        </header>

        <div className="page-content">
          {error && <div className="alert alert-error" role="alert"><span>{error}</span><button onClick={() => setError('')}>×</button></div>}
          {notice && <div className="alert alert-success" role="status"><span>{notice}</span><button onClick={() => setNotice('')}>×</button></div>}

          {view === 'dashboard' && dashboard && (
            <>
              <div className="page-heading">
                <div><p className="eyebrow">MONITORING</p><h1>Good day, {user.full_name.split(' ')[0]}</h1><p className="subtle">A live view of business continuity risk and response activity.</p></div>
                {can('risks:create') && <button className="button button-primary" onClick={() => setView('risks')}>＋ Add a risk</button>}
              </div>
              <div className="metric-grid">
                <MetricCard label="Total risks" value={dashboard.total_risks} note="Across accessible departments" icon="◈" tone="blue" />
                <MetricCard label="Critical risks" value={dashboard.critical} note="Immediate attention required" icon="!" tone="red" />
                <MetricCard label="Plans in progress" value={dashboard.treatments_in_progress} note={`${dashboard.treatments_completed} completed`} icon="↗" tone="teal" />
                <MetricCard label="Overdue actions" value={dashboard.actions_overdue} note={`${dashboard.treatments_overdue} plans past due`} icon="◷" tone="amber" />
              </div>
              <div className="dashboard-grid">
                <section className="panel chart-panel">
                  <PanelTitle title="Risk distribution" detail="Open risks by category" />
                  <div className="chart-container">
                    {Object.keys(dashboard.breakdown || {}).length > 0
                      ? <Bar data={categoryChart} options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#edf1f5' } } } }} />
                      : <EmptyState title="No risk data yet" detail="Create a risk to start building your dashboard." />}
                  </div>
                </section>
                <section className="panel posture-panel">
                  <PanelTitle title="Treatment posture" detail="Plan completion rate" />
                  <div className="completion-value">{dashboard.treatment_completion_rate}<span>%</span></div>
                  <div className="progress-track"><div className="progress-fill" style={{ width: `${dashboard.treatment_completion_rate}%` }} /></div>
                  <div className="posture-legend">
                    <span><i className="legend-dot dot-critical" />Critical <strong>{dashboard.critical}</strong></span>
                    <span><i className="legend-dot dot-high" />High <strong>{dashboard.high}</strong></span>
                    <span><i className="legend-dot dot-moderate" />Moderate <strong>{dashboard.moderate}</strong></span>
                    <span><i className="legend-dot dot-low" />Low <strong>{dashboard.low}</strong></span>
                  </div>
                </section>
              </div>
              <section className="panel table-panel">
                <PanelTitle title="Priority risks" detail="Recently identified risks and their current severity" action={<button className="text-button" onClick={() => setView('risks')}>View register →</button>} />
                <RiskTable risks={dashboard.recent_risks.map((item) => ({ ...item, department: risks.find((risk) => risk.code === item.code)?.department || '—' }))} />
              </section>
            </>
          )}

          {view === 'risks' && (
            <>
              <div className="page-heading">
                <div><p className="eyebrow">RISK INTELLIGENCE</p><h1>Risk register</h1><p className="subtle">Identify, assess and prioritise risks that could disrupt your critical activities.</p></div>
              </div>
              {can('risks:create') && (
                <details className="panel form-panel">
                  <summary className="form-summary"><span><strong>Register a new risk</strong><small>Capture a risk and its initial likelihood and impact.</small></span><span className="summary-plus">＋</span></summary>
                  <form className="form-grid" onSubmit={submitRisk}>
                    <FormField label="Risk ID"><input name="code" placeholder="RISK-004" required /></FormField>
                    <FormField label="Risk name"><input name="name" placeholder="e.g. Production service outage" required /></FormField>
                    <FormField label="Category"><select name="category">{CATEGORIES.map((category) => <option key={category}>{category}</option>)}</select></FormField>
                    <FormField label="Department"><select name="department_id" required value={selectedRiskDepartmentId || user.department_id || ''} onChange={(event) => setSelectedRiskDepartmentId(event.target.value)}><option value="" disabled>Choose department</option>{departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}</select></FormField>
                    <FormField label="Activity"><select name="activity_id"><option value="">Select activity</option>{activities.filter((activity) => String(activity.department_id) === String(selectedRiskDepartmentId || user.department_id || '')).map((activity) => <option key={activity.id} value={activity.id}>{activity.name}</option>)}</select></FormField>
                    <FormField label="Owner"><select name="owner_id" defaultValue={user.id}><option value="">Assign to me</option>{userDirectory.map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></FormField>
                    <FormField label="Threat"><input name="threat" placeholder="Threat or trigger" /></FormField>
                    <FormField label="Vulnerability"><input name="vulnerability" placeholder="Existing weakness" /></FormField>
                    <FormField label="Probability (1–5)"><select name="probability" defaultValue="3">{[1, 2, 3, 4, 5].map((score) => <option key={score} value={score}>{score}</option>)}</select></FormField>
                    <FormField label="Impact (1–5)"><select name="impact" defaultValue="3">{[1, 2, 3, 4, 5].map((score) => <option key={score} value={score}>{score}</option>)}</select></FormField>
                    <FormField label="Description" className="field-wide"><textarea name="description" rows="3" required placeholder="Describe the event and the business context." /></FormField>
                    <FormField label="Potential consequences" className="field-wide"><textarea name="consequence" rows="2" placeholder="Operational, financial, legal or reputational impact." /></FormField>
                    <div className="form-actions"><button className="button button-primary" disabled={busy}>Save risk</button></div>
                  </form>
                </details>
              )}
              <section className="panel table-panel">
                <div className="table-toolbar">
                  <div><h2>All risks <span className="count-pill">{filteredRisks.length}</span></h2><p className="subtle">Scores are calculated as probability × impact.</p></div>
                  <div className="filters">
                    <input aria-label="Search risks" placeholder="Search risks…" value={riskFilter.query} onChange={(event) => setRiskFilter({ ...riskFilter, query: event.target.value })} />
                    <select aria-label="Filter by severity" value={riskFilter.level} onChange={(event) => setRiskFilter({ ...riskFilter, level: event.target.value })}><option>All</option>{LEVELS.map((level) => <option key={level}>{level}</option>)}</select>
                    <select aria-label="Filter by category" value={riskFilter.category} onChange={(event) => setRiskFilter({ ...riskFilter, category: event.target.value })}><option>All</option>{CATEGORIES.map((category) => <option key={category}>{category}</option>)}</select>
                  </div>
                </div>
                <RiskTable risks={filteredRisks} detailed />
              </section>
            </>
          )}

          {view === 'treatments' && (
            <>
              <div className="page-heading">
                <div><p className="eyebrow">RESPONSE & RECOVERY</p><h1>Treatment plans</h1><p className="subtle">Propose, review and track actions that reduce business continuity risk.</p></div>
                {canManageTreatments && <span className="workflow-key"><span>1</span> Proposed <i>→</i> <span>2</span> Approved <i>→</i> <span>3</span> In progress <i>→</i> <span>4</span> Completed</span>}
              </div>
              {canManageTreatments && (
                <details className="panel form-panel">
                  <summary className="form-summary"><span><strong>Propose a treatment plan</strong><small>Plans require manager approval before work can begin.</small></span><span className="summary-plus">＋</span></summary>
                  <form className="form-grid" onSubmit={submitTreatment}>
                    <FormField label="Risk"><select value={selectedRiskId} onChange={(event) => setSelectedRiskId(event.target.value)} required><option value="">Select a risk</option>{risks.map((risk) => <option key={risk.id} value={risk.id}>{risk.code} · {risk.name}</option>)}</select></FormField>
                    <FormField label="Strategy"><select value={treatmentForm.strategy} onChange={(event) => setTreatmentForm({ ...treatmentForm, strategy: event.target.value })}>{['Avoid', 'Reduce', 'Transfer', 'Accept'].map((strategy) => <option key={strategy}>{strategy}</option>)}</select></FormField>
                    <FormField label="Start date"><input type="date" value={treatmentForm.start_date} onChange={(event) => setTreatmentForm({ ...treatmentForm, start_date: event.target.value })} /></FormField>
                    <FormField label="Target date"><input type="date" value={treatmentForm.due_date} onChange={(event) => setTreatmentForm({ ...treatmentForm, due_date: event.target.value })} /></FormField>
                    <FormField label="Treatment plan" className="field-wide"><textarea rows="3" required minLength="10" value={treatmentForm.treatment_plan} onChange={(event) => setTreatmentForm({ ...treatmentForm, treatment_plan: event.target.value })} placeholder="Describe the planned response." /></FormField>
                    <FormField label="Expected outcome"><textarea rows="2" value={treatmentForm.expected_result} onChange={(event) => setTreatmentForm({ ...treatmentForm, expected_result: event.target.value })} placeholder="How will this reduce exposure?" /></FormField>
                    <FormField label="Resources required"><textarea rows="2" value={treatmentForm.resources_required} onChange={(event) => setTreatmentForm({ ...treatmentForm, resources_required: event.target.value })} placeholder="People, budget, systems or suppliers." /></FormField>
                    <div className="form-actions"><button className="button button-primary" disabled={busy}>Submit for review</button></div>
                  </form>
                </details>
              )}
              <div className="treatment-summary">
                {['Proposed', 'Approved', 'In progress', 'Completed'].map((state) => <div className="status-summary-card" key={state}><span className={`status-mark status-${statusClass(state)}`} /><span>{state}</span><strong>{treatments.filter((item) => item.status === state).length}</strong></div>)}
              </div>
              <div className="treatment-list">
                {treatments.length === 0 && <section className="panel"><EmptyState title="No treatment plans yet" detail="Propose a response plan for one of the risks in your register." /></section>}
                {treatments.map((treatment) => (
                  <TreatmentCard
                    key={treatment.id}
                    treatment={treatment}
                    canApprove={canApprove}
                    canManage={canManageTreatments}
                    busy={busy}
                    users={userDirectory}
                    currentUserId={user.id}
                    onReview={reviewTreatment}
                    onPlanStatus={changeTreatmentStatus}
                    onAddAction={submitAction}
                    onActionStatus={updateAction}
                  />
                ))}
              </div>
            </>
          )}

          {view === 'departments' && (
            <>
              <div className="page-heading"><div><p className="eyebrow">ORGANISATION CONTEXT</p><h1>Departments & activities</h1><p className="subtle">Explore the teams and critical activities represented in the workspace.</p></div></div>
              <div className="department-grid">
                {departments.map((department) => (
                  <section className="panel department-card" key={department.id}>
                    <div className="department-icon">{department.name.slice(0, 1)}</div>
                    <div><h2>{department.name}</h2><p>{department.description || 'No description'}</p></div>
                    <div className="department-activities"><strong>{department.activity_count}</strong><span>activities</span></div>
                    {activities.filter((activity) => activity.department_id === department.id).map((activity) => <div className="activity-row" key={activity.id}><span>↳</span>{activity.name}</div>)}
                  </section>
                ))}
              </div>
            </>
          )}

          {view === 'users' && canManageUsers && (
            <>
              <div className="page-heading"><div><p className="eyebrow">IDENTITY & ACCESS</p><h1>People & access</h1><p className="subtle">Assign least-privilege roles to people in your continuity workspace.</p></div></div>
              <div className="role-grid">
                {availableRoles.map((role) => <section className="panel role-card" key={role.id}><div className="role-card-heading"><span className="role-symbol">♙</span><strong>{role.name}</strong></div><p>{role.description}</p><div className="permission-tags">{role.permissions.map((permission) => <span key={permission}>{permission.split(':')[0]}</span>)}</div></section>)}
              </div>
              <details className="panel form-panel">
                <summary className="form-summary"><span><strong>Invite a user</strong><small>Create an account and choose its access role.</small></span><span className="summary-plus">＋</span></summary>
                <form className="form-grid" onSubmit={submitUser}>
                  <FormField label="Full name"><input required value={userForm.full_name} onChange={(event) => setUserForm({ ...userForm, full_name: event.target.value })} /></FormField>
                  <FormField label="Username"><input minLength="3" required value={userForm.username} onChange={(event) => setUserForm({ ...userForm, username: event.target.value })} /></FormField>
                  <FormField label="Email"><input type="email" required value={userForm.email} onChange={(event) => setUserForm({ ...userForm, email: event.target.value })} /></FormField>
                  <FormField label="Temporary password"><input type="password" minLength="10" required value={userForm.password} onChange={(event) => setUserForm({ ...userForm, password: event.target.value })} /></FormField>
                  <FormField label="Role"><select value={userForm.role} onChange={(event) => setUserForm({ ...userForm, role: event.target.value })}>{availableRoles.map((role) => <option key={role.id}>{role.name}</option>)}</select></FormField>
                  <FormField label="Department"><select value={userForm.department_id} onChange={(event) => setUserForm({ ...userForm, department_id: event.target.value })}><option value="">No department</option>{departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}</select></FormField>
                  <div className="form-actions"><button className="button button-primary" disabled={busy}>Create account</button></div>
                </form>
              </details>
              <section className="panel table-panel"><PanelTitle title="Workspace members" detail={`${users.length} accounts`} /><div className="data-table-wrap"><table className="data-table"><thead><tr><th>Member</th><th>Role</th><th>Department</th><th>Status</th><th>Access</th></tr></thead><tbody>{users.map((member) => <tr key={member.id}><td><strong>{member.full_name}</strong><small className="table-subline">{member.email}</small></td><td><select className="role-select" aria-label={`Role for ${member.full_name}`} value={member.role} disabled={member.id === user.id || busy} onChange={(event) => updateUser(member.id, { role: event.target.value })}>{availableRoles.map((role) => <option key={role.id}>{role.name}</option>)}</select></td><td>{member.department}</td><td><span className={`status-chip ${member.is_active ? 'status-completed' : 'status-rejected'}`}>{member.is_active ? 'Active' : 'Inactive'}</span></td><td><button className="text-button" disabled={member.id === user.id || busy} onClick={() => updateUser(member.id, { is_active: !member.is_active })}>{member.is_active ? 'Deactivate' : 'Reactivate'}</button></td></tr>)}</tbody></table></div></section>
            </>
          )}

          {view === 'reports' && (
            <>
              <div className="page-heading"><div><p className="eyebrow">GOVERNANCE</p><h1>Reports & audit</h1><p className="subtle">Export the current risk register or review recent workspace activity.</p></div></div>
              <section className="panel export-panel"><div><h2>Risk register report</h2><p className="subtle">Generate a report using the risks visible to your account.</p></div><div className="export-actions"><button className="button button-secondary" onClick={() => exportReport('pdf')}>↓ Export PDF</button><button className="button button-primary" onClick={() => exportReport('excel')}>↓ Export Excel</button></div></section>
              <section className="panel table-panel"><PanelTitle title="Recent activity" detail="Audit trail · latest 100 events" /><div className="data-table-wrap"><table className="data-table"><thead><tr><th>Event</th><th>Details</th><th>Risk</th><th>By</th><th>When</th></tr></thead><tbody>{auditLogs.map((log) => <tr key={log.id}><td><span className="audit-event">{log.action.replaceAll('_', ' ')}</span></td><td>{log.details}</td><td>{log.risk_code || '—'}</td><td>{log.user}</td><td>{log.created_at ? new Date(log.created_at).toLocaleString() : '—'}</td></tr>)}</tbody></table></div>{auditLogs.length === 0 && <EmptyState title="No activity recorded" detail="Important changes will appear here." />}</section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function MetricCard({ label, value, note, icon, tone }) {
  return <section className={`metric-card metric-${tone}`}><div className="metric-top"><span>{label}</span><span className="metric-icon">{icon}</span></div><strong>{value}</strong><small>{note}</small></section>;
}

function PanelTitle({ title, detail, action }) {
  return <div className="panel-title"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>{action}</div>;
}

function FormField({ label, className = '', children }) {
  return <label className={`form-field ${className}`}><span>{label}</span>{children}</label>;
}

function EmptyState({ title, detail }) {
  return <div className="empty-state"><span className="empty-mark">◌</span><strong>{title}</strong><span>{detail}</span></div>;
}

function RiskTable({ risks, detailed = false }) {
  if (risks.length === 0) return <EmptyState title="No matching risks" detail="Try changing your filters or add a new risk." />;
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead><tr><th>Risk</th>{detailed && <th>Department</th>}<th>Category</th><th>Score</th><th>Severity</th>{detailed && <th>Owner</th>}</tr></thead>
        <tbody>{risks.map((risk) => <tr key={risk.code}><td><strong>{risk.code}</strong><span className="table-subline">{risk.name}</span></td>{detailed && <td>{risk.department}</td>}<td>{risk.category}</td><td><span className="score-pill">{risk.score ?? '—'}/25</span></td><td><Severity level={risk.level} /></td>{detailed && <td>{risk.owner}</td>}</tr>)}</tbody>
      </table>
    </div>
  );
}

function Severity({ level }) {
  return <span className={`severity severity-${(level || 'unassessed').toLowerCase()}`}><i />{level || 'Unassessed'}</span>;
}

function statusClass(status) {
  return (status || '').toLowerCase().replaceAll(' ', '-');
}

function TreatmentCard({
  treatment,
  canApprove,
  canManage,
  busy,
  users,
  currentUserId,
  onReview,
  onPlanStatus,
  onAddAction,
  onActionStatus,
}) {
  const canWork = canManage && ['Approved', 'In progress'].includes(treatment.status);
  return (
    <section className="panel treatment-card">
      <div className="treatment-card-head">
        <div><span className="risk-reference">{treatment.risk_code} · {treatment.risk_name}</span><h2>{treatment.strategy} risk</h2></div>
        <span className={`status-chip status-${statusClass(treatment.status)}`}>{treatment.status}</span>
      </div>
      <p className="treatment-description">{treatment.treatment_plan}</p>
      <div className="treatment-meta">
        <span><small>Plan owner</small><strong>{treatment.created_by}</strong></span>
        <span><small>Target date</small><strong>{treatment.due_date ? new Date(treatment.due_date).toLocaleDateString() : 'Not set'}</strong></span>
        <span><small>Expected outcome</small><strong>{treatment.expected_result || 'Not specified'}</strong></span>
        <span><small>Residual exposure</small><strong>{treatment.residual_score ? `${treatment.residual_score}/25 · ${treatment.residual_risk}` : treatment.residual_risk}</strong></span>
      </div>
      {treatment.review_comment && <div className="review-note"><strong>Review note</strong><span>{treatment.review_comment}{treatment.reviewed_by ? ` · ${treatment.reviewed_by}` : ''}</span></div>}
      {treatment.status === 'Proposed' && canApprove && <div className="decision-actions"><span>Manager review required</span><div><button className="button button-secondary" disabled={busy} onClick={() => onReview(treatment.id, 'reject')}>Reject</button><button className="button button-primary" disabled={busy} onClick={() => onReview(treatment.id, 'approve')}>Approve plan</button></div></div>}
      {treatment.status === 'Proposed' && canManage && <button className="text-button cancel-plan" disabled={busy} onClick={() => onPlanStatus(treatment, 'Cancelled')}>Withdraw proposal</button>}
      {treatment.status === 'Approved' && canManage && <div className="decision-actions"><span>Approved and ready for delivery</span><button className="button button-primary" disabled={busy} onClick={() => onPlanStatus(treatment, 'In progress')}>Start plan</button></div>}

      {treatment.actions.length > 0 && <div className="action-list"><div className="action-list-title">Delivery actions <span>{treatment.actions.filter((action) => action.status === 'Completed').length}/{treatment.actions.length} done</span></div>      {treatment.actions.map((action) => <div className="action-row" key={action.id}><span className={`action-check ${action.status === 'Completed' ? 'checked' : ''}`}>{action.status === 'Completed' ? '✓' : '·'}</span><div className="action-copy"><strong>{action.title}</strong><small>{action.owner} · Due {action.due_date ? new Date(action.due_date).toLocaleDateString() : 'not set'}{action.overdue ? ' · Overdue' : ''}</small>{action.result && <small className="action-result">{action.result}</small>}</div><span className={`action-status action-${statusClass(action.status)}`}>{action.status}</span>{(canManage || Number(action.owner_id) === currentUserId) && action.status !== 'Completed' && <select aria-label={`Update ${action.title}`} value={action.status} onChange={(event) => onActionStatus(action.id, event.target.value)}><option value="Planned">Planned</option><option value="In progress">In progress</option><option value="Blocked">Blocked</option><option value="Completed">Completed</option></select>}</div>)}</div>}

      {canWork && <form className="action-form" onSubmit={(event) => onAddAction(event, treatment.id)}>
        <div className="action-form-heading"><strong>Add delivery action</strong><span>Break the plan into accountable steps.</span></div>
        <div className="action-form-grid">
          <input name="title" required minLength="3" placeholder="Action title" />
          <select name="owner_id" defaultValue=""><option value="">Unassigned owner</option>{users.map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select>
          <input name="due_date" type="date" aria-label="Action due date" />
          <input name="expected_result" placeholder="Expected result" />
          <input name="resources_required" placeholder="Resources needed" />
          <button className="button button-secondary" disabled={busy}>＋ Add action</button>
        </div>
      </form>}

      {treatment.status === 'In progress' && canManage && <div className="decision-actions finish-actions"><span>Reassess residual risk after all actions are complete.</span><button className="button button-primary" disabled={busy || treatment.actions.some((action) => action.status !== 'Completed')} title={treatment.actions.some((action) => action.status !== 'Completed') ? 'Complete all actions first' : ''} onClick={() => onPlanStatus(treatment, 'Completed')}>Complete & reassess</button></div>}
      {['Approved', 'In progress'].includes(treatment.status) && canManage && <button className="text-button cancel-plan" disabled={busy} onClick={() => onPlanStatus(treatment, 'Cancelled')}>Cancel plan</button>}
    </section>
  );
}

export default App;

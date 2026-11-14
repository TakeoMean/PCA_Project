import { useEffect, useMemo, useState } from 'react';
import { apiFetch } from './api';
import { FormField, Modal } from './components/Common';
import BiaView from './views/BiaView';
import CartographyView from './views/CartographyView';
import ControlsView from './views/ControlsView';
import DashboardView from './views/DashboardView';
import IncidentsView from './views/IncidentsView';
import OrganizationView from './views/OrganizationView';
import ReportsView from './views/ReportsView';
import RiskDetailModal from './views/RiskDetailModal';
import RisksView from './views/RisksView';
import SmcaView from './views/SmcaView';
import TreatmentsView from './views/TreatmentsView';
import UsersView from './views/UsersView';

const EMPTY_DATA = [];

function App() {
  const [sessionLoading, setSessionLoading] = useState(true);
  const [user, setUser] = useState(null);
  const [view, setView] = useState(() => new URLSearchParams(window.location.search).get('view') || 'dashboard');
  const [dashboard, setDashboard] = useState(null);
  const [risks, setRisks] = useState(EMPTY_DATA);
  const [departments, setDepartments] = useState(EMPTY_DATA);
  const [activities, setActivities] = useState(EMPTY_DATA);
  const [resources, setResources] = useState(EMPTY_DATA);
  const [treatments, setTreatments] = useState(EMPTY_DATA);
  const [users, setUsers] = useState(EMPTY_DATA);
  const [userDirectory, setUserDirectory] = useState(EMPTY_DATA);
  const [roles, setRoles] = useState(EMPTY_DATA);
  const [auditLogs, setAuditLogs] = useState(EMPTY_DATA);
  const [scope, setScope] = useState(null);
  const [bia, setBia] = useState(EMPTY_DATA);
  const [controls, setControls] = useState(EMPTY_DATA);
  const [cartography, setCartography] = useState(EMPTY_DATA);
  const [methodology, setMethodology] = useState(null);
  const [dependencies, setDependencies] = useState(EMPTY_DATA);
  const [threats, setThreats] = useState(EMPTY_DATA);
  const [incidents, setIncidents] = useState(EMPTY_DATA);
  const [indicators, setIndicators] = useState(EMPTY_DATA);
  const [alerts, setAlerts] = useState(EMPTY_DATA);
  const [selectedRiskId, setSelectedRiskId] = useState(() => {
    const value = Number(new URLSearchParams(window.location.search).get('risk'));
    return Number.isInteger(value) && value > 0 ? value : null;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });

  const permissions = user?.permissions || [];
  const can = (permission) => permissions.includes(permission);

  const loadCurrentUser = async () => {
    try {
      const current = await apiFetch('/api/me');
      setUser(current);
      setPasswordOpen(Boolean(current.must_change_password));
      return current;
    } catch {
      setUser(null);
      return null;
    } finally {
      setSessionLoading(false);
    }
  };

  const refreshCore = async () => {
    if (!user) return;
    const [
      summary, riskRows, departmentRows, activityRows, resourceRows, treatmentRows,
      directoryRows, scopeRow, biaRows, controlRows, mapRows, methodRow,
      dependencyRows, threatRows, incidentRows, indicatorRows, alertRows, logRows,
      userRows, roleRows,
    ] = await Promise.all([
      apiFetch('/api/dashboard/summary'),
      apiFetch('/api/risks'),
      apiFetch('/api/departments'),
      apiFetch('/api/activities'),
      apiFetch('/api/resources'),
      apiFetch('/api/risk-treatments'),
      apiFetch('/api/user-directory'),
      apiFetch('/api/smca/scope'),
      apiFetch('/api/bia'),
      apiFetch('/api/risk-controls'),
      apiFetch('/api/cartography'),
      apiFetch('/api/methodology'),
      apiFetch('/api/activity-dependencies'),
      apiFetch('/api/threat-library'),
      apiFetch('/api/incidents'),
      apiFetch('/api/risk-indicators'),
      apiFetch('/api/alerts'),
      can('audit:read') ? apiFetch('/api/audit-logs?limit=300') : Promise.resolve([]),
      can('users:manage') ? apiFetch('/api/users') : Promise.resolve([]),
      can('users:manage') ? apiFetch('/api/roles') : Promise.resolve([]),
    ]);
    setDashboard(summary);
    setRisks(riskRows);
    setDepartments(departmentRows);
    setActivities(activityRows);
    setResources(resourceRows);
    setTreatments(treatmentRows);
    setUserDirectory(directoryRows);
    setScope(scopeRow);
    setBia(biaRows);
    setControls(controlRows);
    setCartography(mapRows);
    setMethodology(methodRow);
    setDependencies(dependencyRows);
    setThreats(threatRows);
    setIncidents(incidentRows);
    setIndicators(indicatorRows);
    setAlerts(alertRows);
    setAuditLogs(logRows);
    setUsers(userRows);
    setRoles(roleRows);
  };

  useEffect(() => { loadCurrentUser(); }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (view === 'dashboard') url.searchParams.delete('view');
    else url.searchParams.set('view', view);
    if (selectedRiskId) url.searchParams.set('risk', String(selectedRiskId));
    else url.searchParams.delete('risk');
    window.history.replaceState({}, '', url);
  }, [view, selectedRiskId]);

  useEffect(() => {
    if (!user) return;
    setError('');
    refreshCore().catch((loadError) => setError(loadError.message));
  }, [user?.id]);

  const run = async (operation, successMessage, refresh = true) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await operation();
      if (refresh) await refreshCore();
      if (successMessage) setNotice(successMessage);
      return result;
    } catch (operationError) {
      setError(operationError.message || 'Une erreur est survenue.');
      return null;
    } finally {
      setBusy(false);
    }
  };

  const login = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await apiFetch('/api/auth/login', { method: 'POST', body: loginForm });
      await loadCurrentUser();
      setLoginForm({ username: '', password: '' });
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } finally {
      setUser(null);
      setDashboard(null);
      setSelectedRiskId(null);
      setView('dashboard');
    }
  };

  const changePassword = (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    if (values.new_password !== values.confirm_password) {
      setError('La confirmation ne correspond pas au nouveau mot de passe.');
      return Promise.resolve();
    }
    return run(async () => {
      await apiFetch('/api/auth/change-password', { method: 'POST', body: { current_password: values.current_password, new_password: values.new_password } });
      const current = await apiFetch('/api/me');
      setUser(current);
      setPasswordOpen(false);
    }, 'Mot de passe mis à jour.', false);
  };

  const openRisk = (value) => {
    const id = typeof value === 'object' ? value?.id : value;
    if (id) setSelectedRiskId(Number(id));
  };

  const selectedRisk = useMemo(() => risks.find((risk) => risk.id === selectedRiskId) || null, [risks, selectedRiskId]);

  const navigation = user ? [
    { id: 'dashboard', title: 'Tableau de bord', icon: '◫' },
    { id: 'smca', title: 'Parcours SMCA', icon: '◎' },
    { id: 'risks', title: 'Registre des risques', icon: '◇' },
    { id: 'cartography', title: 'Cartographie 5×5', icon: '▦' },
    { id: 'bia', title: 'BIA & dépendances', icon: '⌁' },
    { id: 'controls', title: 'Contrôles', icon: '✓' },
    { id: 'treatments', title: 'Plans de traitement', icon: '↗', badge: treatments.filter((item) => item.status === 'Proposed').length },
    { id: 'incidents', title: 'Incidents & KRI', icon: '⚑', badge: incidents.filter((item) => ['Open', 'Investigating'].includes(item.status)).length },
    { id: 'organization', title: 'Organisation', icon: '⌂' },
    ...(can('users:manage') ? [{ id: 'users', title: 'Utilisateurs', icon: '♙' }] : []),
    ...(can('reports:read') ? [{ id: 'reports', title: 'Rapports & audit', icon: '▤' }] : []),
  ] : [];

  if (sessionLoading) return <div className="app-loading"><div className="brand-mark">C</div><span>Chargement de ContinuityOS…</span></div>;

  if (!user) {
    return <div className="login-screen"><section className="login-aside"><div className="brand-lockup"><span className="brand-mark">C</span><span>Continuity<span className="brand-light">OS</span></span></div><div className="login-message"><p className="eyebrow">CONTINUITÉ D’ACTIVITÉ · RISQUES</p><h1>Anticiper.<br />Cartographier.<br />Agir.</h1><p>Un espace unique pour piloter le SMCA, de la BIA jusqu’au suivi du risque résiduel.</p></div><span className="login-foot">Processus aligné sur les principes ISO 22301</span></section><form className="login-card" onSubmit={login}><div className="brand-lockup mobile-brand"><span className="brand-mark">C</span><span>Continuity<span className="brand-light">OS</span></span></div><p className="eyebrow">ESPACE SÉCURISÉ</p><h2>Connexion</h2><p className="subtle">Utilisez le compte fourni par votre organisation.</p>{error && <div className="alert alert-error" role="alert">{error}</div>}<label>Nom d’utilisateur<input autoComplete="username" required value={loginForm.username} onChange={(event) => setLoginForm({ ...loginForm, username: event.target.value })} /></label><label>Mot de passe<input type="password" autoComplete="current-password" required value={loginForm.password} onChange={(event) => setLoginForm({ ...loginForm, password: event.target.value })} /></label><button className="button button-primary button-wide" disabled={busy}>{busy ? 'Connexion…' : 'Se connecter'}</button></form></div>;
  }

  return <div className="workspace">
    <aside className="sidebar"><div className="brand-lockup"><span className="brand-mark">C</span><span>Continuity<span className="brand-light">OS</span></span></div><div className="workspace-label">ESPACE SMCA</div><nav className="side-nav" aria-label="Navigation principale">{navigation.map((item) => <button key={item.id} className={view === item.id ? 'nav-item selected' : 'nav-item'} onClick={() => setView(item.id)}><span className="nav-icon">{item.icon}</span>{item.title}{item.badge > 0 && <span className="nav-badge">{item.badge}</span>}</button>)}</nav><div className="sidebar-bottom"><div className="sidebar-note"><span className="status-dot" />Session protégée</div><div className="profile-card"><div className="avatar">{user.full_name?.slice(0, 1).toUpperCase()}</div><div className="profile-copy"><strong>{user.full_name}</strong><span>{user.role}</span></div><button className="icon-button logout-button" title="Se déconnecter" onClick={logout}>↗</button></div></div></aside>
    <main className="main-area"><header className="topbar"><div className="breadcrumbs">ContinuityOS <span>/</span> {navigation.find((item) => item.id === view)?.title}</div><div className="topbar-right">{alerts.length > 0 && <button className="notification-button" onClick={() => setView('dashboard')} title="Voir les alertes">● <span>{alerts.length}</span></button>}<span className="today-label">{new Date().toLocaleDateString('fr-FR', { weekday: 'short', month: 'short', day: 'numeric' })}</span><button className="avatar avatar-small" onClick={() => setPasswordOpen(true)} title="Changer le mot de passe">{user.full_name?.slice(0, 1).toUpperCase()}</button></div></header><div className="page-content">{error && <div className="alert alert-error" role="alert"><span>{error}</span><button onClick={() => setError('')}>×</button></div>}{notice && <div className="alert alert-success" role="status"><span>{notice}</span><button onClick={() => setNotice('')}>×</button></div>}
      {view === 'dashboard' && dashboard && <DashboardView user={user} dashboard={dashboard} alerts={alerts} risks={risks} onView={setView} onRisk={openRisk} canCreate={can('risks:create')} />}
      {view === 'smca' && <SmcaView scope={scope} methodology={methodology} bia={bia} risks={risks} controls={controls} treatments={treatments} threats={threats} canEdit={can('departments:write')} busy={busy} run={run} apiFetch={apiFetch} />}
      {view === 'risks' && <RisksView risks={risks} departments={departments} activities={activities} users={userDirectory} threats={threats} canCreate={can('risks:create')} busy={busy} apiFetch={apiFetch} run={run} onRisk={openRisk} />}
      {view === 'cartography' && <CartographyView cartography={cartography} departments={departments} onRisk={openRisk} />}
      {view === 'bia' && <BiaView bia={bia} activities={activities} dependencies={dependencies} canManage={can('bia:manage')} busy={busy} apiFetch={apiFetch} run={run} />}
      {view === 'controls' && <ControlsView controls={controls} risks={risks} users={userDirectory} canManage={can('controls:manage')} busy={busy} apiFetch={apiFetch} run={run} onRisk={openRisk} />}
      {view === 'treatments' && <TreatmentsView treatments={treatments} risks={risks} users={userDirectory} canManage={can('treatments:manage')} canApprove={can('treatments:approve')} currentUserId={user.id} busy={busy} apiFetch={apiFetch} run={run} onRisk={openRisk} />}
      {view === 'incidents' && <IncidentsView incidents={incidents} indicators={indicators} risks={risks} departments={departments} canManage={can('incidents:manage')} canIndicator={can('indicators:manage')} busy={busy} apiFetch={apiFetch} run={run} onRisk={openRisk} />}
      {view === 'organization' && <OrganizationView departments={departments} activities={activities} resources={resources} canEdit={can('departments:write')} busy={busy} apiFetch={apiFetch} run={run} />}
      {view === 'users' && can('users:manage') && <UsersView users={users} roles={roles} departments={departments} currentUserId={user.id} busy={busy} apiFetch={apiFetch} run={run} />}
      {view === 'reports' && can('reports:read') && <ReportsView auditLogs={auditLogs} run={run} />}
    </div></main>

    {selectedRisk && <RiskDetailModal risk={selectedRisk} departments={departments} activities={activities} users={userDirectory} controls={controls} indicators={indicators} incidents={incidents} auditLogs={auditLogs} canEdit={can('risks:create')} canAssess={can('risks:assess')} canControl={can('controls:manage')} canIndicator={can('indicators:manage')} busy={busy} apiFetch={apiFetch} run={run} onClose={() => setSelectedRiskId(null)} />}
    {passwordOpen && <Modal title={user.must_change_password ? 'Changement de mot de passe obligatoire' : 'Changer le mot de passe'} subtitle="Choisissez un mot de passe unique d’au moins 10 caractères." onClose={() => !user.must_change_password && setPasswordOpen(false)}><form className="modal-form single-column" onSubmit={changePassword}><FormField label="Mot de passe actuel"><input name="current_password" type="password" required autoComplete="current-password" /></FormField><FormField label="Nouveau mot de passe"><input name="new_password" type="password" required minLength="10" autoComplete="new-password" /></FormField><FormField label="Confirmation"><input name="confirm_password" type="password" required minLength="10" autoComplete="new-password" /></FormField><div className="form-actions">{!user.must_change_password && <button type="button" className="button button-secondary" onClick={() => setPasswordOpen(false)}>Annuler</button>}<button className="button button-primary" disabled={busy}>Mettre à jour</button></div></form></Modal>}
  </div>;
}

export default App;

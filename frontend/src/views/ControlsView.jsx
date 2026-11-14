import { useMemo, useState } from 'react';
import { EmptyState, FormField, PanelTitle, StatusChip } from '../components/Common';
import { formatDate, formObject, isoOrNull, numberOrNull } from '../riskUtils';

const CONTROL_LABELS = { Implemented: 'Mis en œuvre', Planned: 'Planifié', 'Needs improvement': 'À améliorer', Inactive: 'Inactif' };

export default function ControlsView({ controls, risks, users, canManage, busy, apiFetch, run, onRisk }) {
  const [riskId, setRiskId] = useState('');
  const [filter, setFilter] = useState('All');
  const visible = useMemo(() => controls.filter((item) => filter === 'All' || item.status === filter), [controls, filter]);

  const submit = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = formObject(form);
    payload.effectiveness = Number(payload.effectiveness);
    payload.owner_id = numberOrNull(payload.owner_id);
    payload.last_tested_at = isoOrNull(payload.last_tested_at);
    payload.next_test_date = isoOrNull(payload.next_test_date);
    return run(async () => {
      await apiFetch(`/api/risks/${riskId}/controls`, { method: 'POST', body: payload });
      form.reset();
      setRiskId('');
    }, 'Contrôle ajouté.');
  };

  return <>
    <div className="page-heading"><div><p className="eyebrow">MESURES DE MAÎTRISE</p><h1>Contrôles et preuves</h1><p className="subtle">Évaluez l’efficacité des contrôles préventifs, détectifs et correctifs.</p></div></div>
    {canManage && <details className="panel form-panel"><summary className="form-summary"><span><strong>Ajouter un contrôle</strong><small>Assignez un responsable, une efficacité et une date de test.</small></span><span className="summary-plus">＋</span></summary><form className="form-grid" onSubmit={submit}><FormField label="Risque"><select required value={riskId} onChange={(event) => setRiskId(event.target.value)}><option value="" disabled>Choisir</option>{risks.map((item) => <option value={item.id} key={item.id}>{item.code} · {item.name}</option>)}</select></FormField><FormField label="Nom"><input name="name" required /></FormField><FormField label="Type"><select name="control_type"><option value="Preventive">Préventif</option><option value="Detective">Détectif</option><option value="Corrective">Correctif</option></select></FormField><FormField label="Responsable"><select name="owner_id"><option value="">Non assigné</option>{users.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select></FormField><FormField label="Efficacité"><select name="effectiveness" defaultValue="3">{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value}/5</option>)}</select></FormField><FormField label="Statut"><select name="status">{Object.entries(CONTROL_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></FormField><FormField label="Dernier test"><input type="date" name="last_tested_at" /></FormField><FormField label="Prochain test"><input type="date" name="next_test_date" /></FormField><FormField label="Description" className="field-wide"><textarea name="description" rows="2" required /></FormField><FormField label="Référence de preuve" className="field-wide"><input name="evidence_reference" /></FormField><div className="form-actions"><button className="button button-primary" disabled={busy || !riskId}>Ajouter</button></div></form></details>}
    <section className="panel table-panel"><div className="table-toolbar"><PanelTitle title={`${visible.length} contrôle(s)`} detail="Les contrôles échus apparaissent en priorité." /><select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="All">Tous les statuts</option>{Object.entries(CONTROL_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></div><div className="control-grid">{visible.sort((a, b) => String(a.next_test_date || '').localeCompare(String(b.next_test_date || ''))).map((item) => { const overdue = item.next_test_date && new Date(item.next_test_date) < new Date(); return <article className={`control-card ${overdue ? 'control-overdue' : ''}`} key={item.id}><header><button className="risk-reference" onClick={() => onRisk(item.risk_id)}>{item.risk_code} · {item.risk_name}</button><StatusChip status={item.status} /></header><h2>{item.name}</h2><p>{item.description}</p><div className="control-meta"><span><small>Type</small><strong>{item.control_type}</strong></span><span><small>Efficacité</small><strong>{item.effectiveness}/5</strong></span><span><small>Responsable</small><strong>{item.owner}</strong></span><span><small>Prochain test</small><strong>{formatDate(item.next_test_date)}{overdue ? ' · ÉCHU' : ''}</strong></span></div>{item.evidence_reference && <small>Preuve : {item.evidence_reference}</small>}{canManage && <div className="control-actions"><select value={item.status} onChange={(event) => run(() => apiFetch(`/api/risk-controls/${item.id}`, { method: 'PATCH', body: { status: event.target.value } }), 'Statut du contrôle mis à jour.')}>{Object.entries(CONTROL_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select><select value={item.effectiveness} onChange={(event) => run(() => apiFetch(`/api/risk-controls/${item.id}`, { method: 'PATCH', body: { effectiveness: Number(event.target.value) } }), 'Efficacité mise à jour.')}>{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value}/5</option>)}</select></div>}</article>; })}</div>{!visible.length && <EmptyState title="Aucun contrôle" detail="Ajoutez les mesures existantes ou prévues pour chaque risque." />}</section>
  </>;
}


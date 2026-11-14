import { useMemo, useState } from 'react';
import { EmptyState, FormField, Modal, PanelTitle, StatusChip } from '../components/Common';
import { STATUS_LABELS, formatDate, formObject, isoOrNull, numberOrNull } from '../riskUtils';

const EMPTY_PLAN = { strategy: 'Reduce', treatment_plan: '', expected_result: '', resources_required: '', start_date: '', due_date: '' };

export default function TreatmentsView({ treatments, risks, users, canManage, canApprove, currentUserId, busy, apiFetch, run, onRisk }) {
  const [riskId, setRiskId] = useState('');
  const [plan, setPlan] = useState(EMPTY_PLAN);
  const [review, setReview] = useState(null);
  const [residual, setResidual] = useState(null);
  const [actionResult, setActionResult] = useState(null);
  const [filter, setFilter] = useState('All');

  const visible = useMemo(() => treatments.filter((item) => filter === 'All' || item.status === filter), [treatments, filter]);
  const statusCounts = Object.fromEntries(['Proposed', 'Approved', 'In progress', 'Completed', 'Rejected'].map((status) => [status, treatments.filter((item) => item.status === status).length]));

  const submitPlan = (event) => {
    event.preventDefault();
    const body = { ...plan, start_date: isoOrNull(plan.start_date), due_date: isoOrNull(plan.due_date) };
    return run(async () => {
      await apiFetch(`/api/risks/${riskId}/treatments`, { method: 'POST', body });
      setPlan(EMPTY_PLAN);
      setRiskId('');
    }, 'Plan soumis pour validation.');
  };

  const submitReview = (event) => {
    event.preventDefault();
    const current = review;
    const comment = new FormData(event.currentTarget).get('comment');
    return run(async () => {
      await apiFetch(`/api/risk-treatments/${current.treatment.id}/decision`, { method: 'POST', body: { decision: current.decision, comment } });
      setReview(null);
    }, current.decision === 'approve' ? 'Plan approuvé.' : 'Plan rejeté.');
  };

  const submitResidual = (event) => {
    event.preventDefault();
    const payload = formObject(event.currentTarget);
    payload.status = 'Completed';
    payload.residual_probability = Number(payload.residual_probability);
    payload.residual_impact = Number(payload.residual_impact);
    const treatment = residual;
    return run(async () => {
      await apiFetch(`/api/risk-treatments/${treatment.id}/status`, { method: 'PATCH', body: payload });
      setResidual(null);
    }, 'Plan clôturé et risque résiduel évalué.');
  };

  const changePlanStatus = (treatment, status) => run(
    () => apiFetch(`/api/risk-treatments/${treatment.id}/status`, { method: 'PATCH', body: { status } }),
    `Plan marqué « ${status} ».` ,
  );

  const submitAction = (event, treatmentId) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = formObject(form);
    payload.owner_id = numberOrNull(payload.owner_id);
    payload.start_date = isoOrNull(payload.start_date);
    payload.due_date = isoOrNull(payload.due_date);
    return run(async () => { await apiFetch(`/api/risk-treatments/${treatmentId}/actions`, { method: 'POST', body: payload }); form.reset(); }, 'Action ajoutée.');
  };

  const changeAction = (action, status) => {
    if (status === 'Completed') {
      setActionResult(action);
      return Promise.resolve();
    }
    return run(() => apiFetch(`/api/treatment-actions/${action.id}`, { method: 'PATCH', body: { status } }), `Action marquée « ${status} ».`);
  };

  const completeAction = (event) => {
    event.preventDefault();
    const result = new FormData(event.currentTarget).get('result');
    const action = actionResult;
    return run(async () => {
      await apiFetch(`/api/treatment-actions/${action.id}`, { method: 'PATCH', body: { status: 'Completed', result } });
      setActionResult(null);
    }, 'Action terminée avec son résultat.');
  };

  return <>
    <div className="page-heading"><div><p className="eyebrow">TRAITEMENT ET AMÉLIORATION</p><h1>Plans de traitement</h1><p className="subtle">Séparation des responsabilités, actions mesurables et réévaluation résiduelle.</p></div><select className="page-filter" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="All">Tous les statuts</option>{Object.keys(statusCounts).map((status) => <option value={status} key={status}>{STATUS_LABELS[status] || status} ({statusCounts[status]})</option>)}</select></div>
    <div className="treatment-summary">{Object.entries(statusCounts).map(([status, count]) => <article className="status-summary-card" key={status}><span className={`status-dot status-dot-${status.toLowerCase().replaceAll(' ', '-')}`} /><strong>{STATUS_LABELS[status] || status}</strong><b>{count}</b></article>)}</div>
    {canManage && <details className="panel form-panel"><summary className="form-summary"><span><strong>Proposer un plan</strong><small>Le plan devra être validé par une autre personne autorisée.</small></span><span className="summary-plus">＋</span></summary><form className="form-grid" onSubmit={submitPlan}><FormField label="Risque"><select required value={riskId} onChange={(event) => setRiskId(event.target.value)}><option value="" disabled>Choisir</option>{risks.filter((risk) => !['Closed', 'Archived'].includes(risk.status)).map((risk) => <option value={risk.id} key={risk.id}>{risk.code} · {risk.name}</option>)}</select></FormField><FormField label="Stratégie"><select value={plan.strategy} onChange={(event) => setPlan({ ...plan, strategy: event.target.value })}><option value="Avoid">Éviter</option><option value="Reduce">Réduire</option><option value="Transfer">Transférer</option><option value="Accept">Accepter</option></select></FormField><FormField label="Début"><input type="date" value={plan.start_date} onChange={(event) => setPlan({ ...plan, start_date: event.target.value })} /></FormField><FormField label="Échéance"><input type="date" value={plan.due_date} onChange={(event) => setPlan({ ...plan, due_date: event.target.value })} /></FormField><FormField label="Plan de traitement" className="field-wide"><textarea required minLength="10" rows="3" value={plan.treatment_plan} onChange={(event) => setPlan({ ...plan, treatment_plan: event.target.value })} /></FormField><FormField label="Résultat attendu" className="field-wide"><textarea rows="2" value={plan.expected_result} onChange={(event) => setPlan({ ...plan, expected_result: event.target.value })} /></FormField><FormField label="Ressources nécessaires" className="field-wide"><textarea rows="2" value={plan.resources_required} onChange={(event) => setPlan({ ...plan, resources_required: event.target.value })} /></FormField><div className="form-actions"><button className="button button-primary" disabled={busy || !riskId}>Soumettre pour validation</button></div></form></details>}
    <div className="treatment-list">{visible.map((treatment) => <TreatmentCard key={treatment.id} treatment={treatment} users={users} currentUserId={currentUserId} canManage={canManage} canApprove={canApprove} busy={busy} onRisk={onRisk} onReview={setReview} onStatus={(status) => status === 'Completed' ? setResidual(treatment) : changePlanStatus(treatment, status)} onAddAction={submitAction} onActionStatus={changeAction} />)}</div>
    {!visible.length && <section className="panel"><EmptyState title="Aucun plan" detail="Proposez un traitement depuis un risque prioritaire." /></section>}

    {review && <Modal title={review.decision === 'approve' ? 'Approuver le plan' : 'Rejeter le plan'} subtitle={`${review.treatment.risk_code} · ${review.treatment.risk_name}`} onClose={() => setReview(null)}><form className="modal-form single-column" onSubmit={submitReview}><FormField label="Commentaire de revue"><textarea name="comment" required minLength="3" rows="5" autoFocus /></FormField><div className="form-actions"><button type="button" className="button button-secondary" onClick={() => setReview(null)}>Annuler</button><button className={`button ${review.decision === 'approve' ? 'button-primary' : 'button-danger'}`} disabled={busy}>Confirmer</button></div></form></Modal>}
    {residual && <Modal title="Clôturer et réévaluer" subtitle="Toutes les actions sont terminées : évaluez l’exposition résiduelle." onClose={() => setResidual(null)}><form className="modal-form form-grid" onSubmit={submitResidual}><FormField label="Probabilité résiduelle"><select name="residual_probability" defaultValue="2">{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value}</option>)}</select></FormField><FormField label="Impact résiduel"><select name="residual_impact" defaultValue="2">{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value}</option>)}</select></FormField><div className="form-actions"><button type="button" className="button button-secondary" onClick={() => setResidual(null)}>Annuler</button><button className="button button-primary" disabled={busy}>Clôturer le plan</button></div></form></Modal>}
    {actionResult && <Modal title="Résultat de l’action" subtitle={actionResult.title} onClose={() => setActionResult(null)}><form className="modal-form single-column" onSubmit={completeAction}><FormField label="Résultat obtenu"><textarea name="result" required rows="5" autoFocus placeholder="Décrivez la preuve, le résultat du test et les écarts éventuels." /></FormField><div className="form-actions"><button type="button" className="button button-secondary" onClick={() => setActionResult(null)}>Annuler</button><button className="button button-primary" disabled={busy}>Terminer l’action</button></div></form></Modal>}
  </>;
}

function TreatmentCard({ treatment, users, currentUserId, canManage, canApprove, busy, onRisk, onReview, onStatus, onAddAction, onActionStatus }) {
  const completed = treatment.actions.filter((item) => item.status === 'Completed').length;
  const blocked = treatment.actions.filter((item) => item.status === 'Blocked').length;
  const overdue = treatment.actions.filter((item) => item.overdue).length;
  const progress = treatment.actions.length ? Math.round(completed * 100 / treatment.actions.length) : 0;
  const canWork = canManage && ['Approved', 'In progress'].includes(treatment.status);
  const planOverdue = treatment.due_date && new Date(treatment.due_date) < new Date() && ['Approved', 'In progress'].includes(treatment.status);
  return <section className="panel treatment-card"><div className="treatment-card-head"><div><button className="risk-reference" onClick={() => onRisk(treatment.risk_id)}>{treatment.risk_code} · {treatment.risk_name}</button><h2>{treatment.strategy} · plan de traitement</h2></div><StatusChip status={treatment.status} /></div>{(planOverdue || blocked) && <div className="treatment-alert">{planOverdue && <span>Échéance du plan dépassée</span>}{blocked > 0 && <span>{blocked} action(s) bloquée(s)</span>}</div>}<p className="treatment-description">{treatment.treatment_plan}</p><div className="treatment-meta"><span><small>Proposé par</small><strong>{treatment.created_by}</strong></span><span><small>Échéance</small><strong>{formatDate(treatment.due_date)}</strong></span><span><small>Résultat attendu</small><strong>{treatment.expected_result || 'Non précisé'}</strong></span><span><small>Risque résiduel</small><strong>{treatment.residual_score ? `${treatment.residual_score}/25 · ${treatment.residual_risk}` : 'Non évalué'}</strong></span></div>{treatment.review_comment && <div className="review-note"><strong>Décision de revue</strong><span>{treatment.review_comment} · {treatment.reviewed_by}</span></div>}{treatment.status === 'Proposed' && canApprove && <div className="decision-actions"><span>Validation indépendante requise</span><div><button className="button button-secondary" disabled={busy} onClick={() => onReview({ treatment, decision: 'reject' })}>Rejeter</button><button className="button button-primary" disabled={busy} onClick={() => onReview({ treatment, decision: 'approve' })}>Approuver</button></div></div>}{treatment.status === 'Proposed' && canManage && <button className="text-button danger-text" onClick={() => onStatus('Cancelled')}>Retirer la proposition</button>}{treatment.status === 'Approved' && canManage && <div className="decision-actions"><span>Plan approuvé, prêt à démarrer</span><button className="button button-primary" onClick={() => onStatus('In progress')}>Démarrer</button></div>}
    {(treatment.actions.length > 0 || canWork) && <div className="action-list"><div className="action-list-title"><span>Actions de mise en œuvre</span><span>{completed}/{treatment.actions.length} terminée(s){blocked ? ` · ${blocked} bloquée(s)` : ''}{overdue ? ` · ${overdue} en retard` : ''}</span></div>{treatment.actions.length > 0 && <div className="action-progress"><div className="progress-track"><div className="progress-fill" style={{ width: `${progress}%` }} /></div><span>{progress}%</span></div>}{treatment.actions.map((action) => <div className={`action-row ${action.overdue ? 'action-row-overdue' : ''}`} key={action.id}><span className={`action-check ${action.status === 'Completed' ? 'checked' : ''}`}>{action.status === 'Completed' ? '✓' : '·'}</span><div className="action-copy"><strong>{action.title}</strong><small>{action.owner} · échéance {formatDate(action.due_date)}{action.overdue ? ' · EN RETARD' : ''}</small>{action.expected_result && <small>Résultat attendu : {action.expected_result}</small>}{action.result && <small className="action-result">Résultat : {action.result}</small>}</div><StatusChip status={action.status} />{(canManage || Number(action.owner_id) === currentUserId) && action.status !== 'Completed' && <select aria-label={`Statut de ${action.title}`} value={action.status} onChange={(event) => onActionStatus(action, event.target.value)}><option>Planned</option><option>In progress</option><option>Blocked</option><option>Completed</option></select>}</div>)}</div>}
    {canWork && <form className="action-form" onSubmit={(event) => onAddAction(event, treatment.id)}><div className="action-form-heading"><strong>Ajouter une action</strong><span>Responsable, échéance et résultat mesurable obligatoires.</span></div><div className="action-form-grid"><input name="title" required minLength="3" placeholder="Action" /><select name="owner_id" required defaultValue=""><option value="" disabled>Responsable</option>{users.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select><input name="start_date" type="date" aria-label="Date de début" /><input name="due_date" type="date" required aria-label="Échéance" /><input name="expected_result" required placeholder="Critère de réussite" /><input name="resources_required" placeholder="Ressources" /><button className="button button-secondary" disabled={busy}>＋ Ajouter</button></div></form>}
    {treatment.status === 'In progress' && canManage && <div className="decision-actions finish-actions"><span>La clôture exige toutes les actions terminées.</span><button className="button button-primary" disabled={!treatment.actions.length || treatment.actions.some((item) => item.status !== 'Completed')} onClick={() => onStatus('Completed')}>Clôturer et réévaluer</button></div>}{['Approved', 'In progress'].includes(treatment.status) && canManage && <button className="text-button danger-text" onClick={() => onStatus('Cancelled')}>Annuler le plan</button>}</section>;
}

